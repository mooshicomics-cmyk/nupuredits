#!/usr/bin/env python3
"""The cut tools must say what actually happened: no ✓ for a step that failed, no "no restarts" for a
pass that cut some, no warning stored as if it were speech, no crash on a silent file.

  1. your-turn --apply printed a ✓ for clean_cut without reading clean_cut.failed.
  2. your-turn stored its "⚠ low-confidence timestamps" warning INSIDE the cut's transcript text, which
     verify-cut then compares against the audio and the style plan shows as her words.
  3. your-turn wrote only transcript/cuts.json; stitch-cut.sh stitches the scratch copy, so the next splice
     put the cut from before her trim back. --apply now mirrors it into the scratch folder.
  4. clean_cut reported "no restarts" after every successful restart pass, including ones that cut, and
     dropped the pass's ⚠ re-listen lines.
  5. sound-check judged every cut against the -6 dBFS ceiling while the default master limits at -1 dBFS,
     so a normal render read as a hot one; a digitally silent render crashed it (the log of zero), and so
     did VOICE_GAIN_DB=inf or nan on a hot one.

Everything runs on generated media in a temporary folder. CapCut is never looked at: the running-check
is stubbed, and the draft is a folder made here.

Run:  python3 product/tests/test_cut_messages.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
sys.path.insert(0, os.path.join(ROOT, "product"))
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FFMPEG = shutil.which("ffmpeg")
if os.name == "nt" or not FFMPEG:
    print("cut messages: skipped (needs ffmpeg, and a POSIX system for the stand-in restart pass)")
    sys.exit(0)

tmp = tempfile.mkdtemp()
try:
    # ------------------------------------------------------------ your-turn: 1, 2 and 3
    job = os.path.join(tmp, "my-reel")
    os.makedirs(os.path.join(job, "raw"))
    os.makedirs(os.path.join(job, "transcript"))
    clip = os.path.join(job, "raw", "take.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)
    words = [{"w": w, "start": s, "end": s + 0.3, "prob": p} for w, s, p in
             (("first", 0.5, 0.95), ("line.", 0.9, 0.95), ("shaky", 3.1, 0.2), ("second", 3.5, 0.3))]
    with open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8") as fh:
        json.dump({"clips": [{"clip": "take.mp4", "words": words}]}, fh)
    with open(os.path.join(job, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": [{"clip": "take.mp4", "start": 0.4, "end": 5.5, "transcript": "before her trim"}]}, fh)
    draft = os.path.join(tmp, "draft")
    os.makedirs(draft)
    segs = [{"material_id": "m", "source_timerange": {"start": 400000, "duration": 900000},
             "target_timerange": {"start": 0, "duration": 900000}},
            {"material_id": "m", "source_timerange": {"start": 3000000, "duration": 900000},
             "target_timerange": {"start": 900000, "duration": 900000}}]
    with open(os.path.join(draft, "draft_info.json"), "w", encoding="utf-8") as fh:
        json.dump({"materials": {"videos": [{"id": "m", "path": clip}]},
                   "tracks": [{"type": "video", "segments": segs}]}, fh)

    import draft_safety  # noqa: E402
    draft_safety._registry_draft_json_name = lambda: None     # never read CapCut's own registry here
    scratch_root = os.path.join(tmp, "scratch")
    os.makedirs(scratch_root)

    def your_turn(clean_failed):
        """Run your-turn --apply with clean_cut replaced by a stand-in that reports clean_failed."""
        def stand_in(_job):
            stand_in.failed = list(clean_failed)
            return []
        stand_in.failed = []
        sys.modules["clean_cut"] = types.SimpleNamespace(clean_cut=stand_in)
        yt = load("your_turn", os.path.join(SCRIPTS, "your-turn.py"))
        yt.capcut_running = lambda: False
        yt.CAPCUT_ROOT = os.path.join(tmp, "no-capcut-here")
        saved_tempdir, tempfile.tempdir = tempfile.tempdir, scratch_root
        saved_argv, sys.argv = sys.argv, ["your-turn.py", job, "--draft", draft, "--apply"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                yt.main()
        finally:
            tempfile.tempdir, sys.argv = saved_tempdir, saved_argv
            sys.modules.pop("clean_cut", None)
        return out.getvalue()

    printed = your_turn(clean_failed=["snap-to-sound"])
    check("1: a failed clean_cut step is never reported with a ✓", "✓ clean_cut" not in printed, printed[-400:])
    check("1: it names the step that did not finish", "snap-to-sound did not finish" in printed, printed[-400:])
    printed = your_turn(clean_failed=[])
    # A your-turn cut is HER timeline, so a clean run keeps her edges exactly (no snap); see your-turn.py.
    check("1: a clean run still says ✓", "✓ clean_cut: your edges kept exactly" in printed, printed[-400:])

    with open(os.path.join(job, "transcript", "cuts.json"), encoding="utf-8") as fh:
        pulled = json.load(fh)["segments"]
    check("2: the low-confidence warning is printed beside the line",
          "⚠ low-confidence timestamps" in printed, printed[-600:])
    check("2: and never stored in the cut's transcript text",
          all("⚠" not in s["transcript"] and "low-confidence" not in s["transcript"] for s in pulled),
          str([s["transcript"] for s in pulled]))
    check("2: the stored text is exactly the words in her range", [s["transcript"] for s in pulled] ==
          ["first line.", "shaky second"], str([s["transcript"] for s in pulled]))

    mirror = os.path.join(scratch_root, "reels-editing-engine", "my-reel", "cuts.json")
    check("3: --apply refreshes the scratch plan stitch-cut.sh stitches", os.path.exists(mirror))
    if os.path.exists(mirror):
        with open(mirror, encoding="utf-8") as fh:
            check("3: with HER cut, not the one from before her trim",
                  [(s["start"], s["end"]) for s in json.load(fh)["segments"]] ==
                  [(s["start"], s["end"]) for s in pulled])

    # ------------------------------------------------------------ clean_cut: 4
    cc = load("clean_cut_real", os.path.join(ROOT, "product", "clean_cut.py"))
    for f in ("transcript/.your-turn-cut",):
        p = os.path.join(job, f)
        if os.path.exists(p):
            os.remove(p)

    def restart_pass(cut_seconds, warn):
        """A stand-in for the restart pass: trims cut_seconds off the cut's last segment, prints warn."""
        fake = os.path.join(tmp, f"fake-trim-{cut_seconds}")
        cuts = os.path.join(job, "transcript", "cuts.json")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(f"#!{sys.executable}\nimport json, sys\np = {cuts!r}\n"
                     "d = json.load(open(p, encoding='utf-8'))\n"
                     f"d['segments'][-1]['end'] -= {cut_seconds}\n"
                     "json.dump(d, open(p, 'w', encoding='utf-8'))\n"
                     f"sys.stderr.write({warn!r})\n")
        os.chmod(fake, 0o755)
        return fake

    def run_clean(fake):
        cc.VENV = fake
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cc.clean_cut(job)
        return err.getvalue()

    said = run_clean(restart_pass(0, ""))
    check("4: a pass that removed nothing says it ran and found nothing",
          "trim-restarts: ran, found no quick restarts to remove" in said, said)
    said = run_clean(restart_pass(0.5, "  ⚠ low-confidence cut 3.00->4.00 (avg word prob 0.25 < 0.5) — RE-LISTEN\n"))
    check("4: a pass that cut says how much", "trim-restarts: ran, removed 0.50s" in said, said)
    check("4: and passes its ⚠ lines on", "⚠ low-confidence cut 3.00->4.00" in said, said)
    check("4: never 'no restarts' after a pass that cut", "no restarts" not in said, said)

    # ------------------------------------------------------------ sound-check: 5
    aqa = os.path.join(SCRIPTS, "sound-check.py")

    def render(name, audio_filter):
        jd = os.path.join(tmp, name)
        os.makedirs(os.path.join(jd, "outputs"))
        os.makedirs(os.path.join(jd, "transcript"))
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=30:d=3",
                        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=3",
                        "-filter_complex", f"[1:a]{audio_filter},pan=stereo|c0=c0|c1=c0[a]", "-map", "0:v",
                        "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
                        "-y", os.path.join(jd, "outputs", name + ".mp4")], check=True)
        with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump({"segments": [{"clip": "x.mov", "start": 0, "end": 1.5},
                                    {"clip": "x.mov", "start": 2, "end": 3.5}]}, fh)
        return jd

    def listen(jd, **env):
        e = dict(os.environ)
        e.pop("VOICE_GAIN_DB", None)
        e.pop("WARM_MASTER", None)
        e.update(env)
        r = subprocess.run([sys.executable, aqa, jd], capture_output=True, text=True, env=e, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    normal = render("normal", "volume=12dB")     # peaks near -6 dBFS: on the -6 dBFS ceiling, 5 dB under -1 dBFS
    silent = render("silent", "volume=0")
    rc, out = listen(normal)
    check("5: a -1 dBFS master is judged at -1 dBFS, not -6", rc == 0 and "⚠ limiter" not in out, out[-500:])
    rc, out = listen(normal, WARM_MASTER="0")
    check("5: WARM_MASTER=0 still judges at -6 dBFS", rc == 0 and "⚠ limiter" in out, out[-500:])
    rc, out = listen(silent)
    check("5: a silent render is reported, not a crash", rc == 0 and "SILENT" in out and "Traceback" not in out,
          out[-500:])
    for bad in ("inf", "nan"):
        rc, out = listen(normal, WARM_MASTER="0", VOICE_GAIN_DB=bad)
        check(f"5: VOICE_GAIN_DB={bad} is named, not a crash",
              rc == 0 and "Traceback" not in out and "not a level in dB" in out, out[-500:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else "cut messages: every step says what actually happened")
sys.exit(1 if fails else 0)
