#!/usr/bin/env python3
"""stitch-cut.sh must fail loudly, never hand over a cut it did not make, and never save a stale plan.

Every case below shipped as a quiet success:

  1. BOTH ENCODERS FAIL, NOTHING WRITTEN. The integrity check looked at whatever sat at the output path,
     so the PREVIOUS run's cut passed it: "✓ software-encoder fallback produced a clean render", exit 0.
  2. VOICE_GAIN_DB SET BUT EMPTY. The toggles line said VOICE_GAIN_DB=10 while the graph said "volume=dB",
     which ffmpeg refuses (and then case 1 took over).
  3. FLAT_RENDER=0 WITH A PLAN THAT CANNOT BE BUILT. The failure was swallowed, and a snapped EDL left in the
     scratch folder by an earlier run was saved over the job's cut, exit 0.
  4. THE SCRATCH PLAN IS GONE (the OS clears that folder). The run died with "missing", although the
     job's saved plan was right there; now it stitches that one and says so.
  5. A NON-HARDWARE FAILURE (a clip that is not there) was reported as "render failed the integrity
     check" and filed a hardware report. Only exit 3 means that.
  6. A JOB WITH SEVERAL CLIPS printed "quick-restart pass CRASHED" on every stitch; the pass simply reads
     one-clip jobs only, and now the stitch says so plainly.
  7. The restart pass's ⚠ lines (re-listen here) were thrown away on success; now they are passed on.

It runs stitch-cut.sh from a throwaway copy of the engine with a short generated clip, so nothing real is
touched, and the hardware-report tool is a stand-in that only records that it was called.

Run:  python3 product/tests/test_stitch_failures.py
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def executable(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


FFMPEG = shutil.which("ffmpeg")
if os.name == "nt" or not FFMPEG or not shutil.which("ffprobe") or not shutil.which("bash"):
    print("stitch failures: skipped (needs bash, ffmpeg and ffprobe, and a POSIX shell for the stand-in encoder)")
    sys.exit(0)

tmp = tempfile.mkdtemp()
try:
    eng = os.path.join(tmp, "engine")
    for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "product/video_encoder.py", "product/hdr.py", "product/probe.py"):
        os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
    shutil.copytree(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"),
                    os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    reports = os.path.join(tmp, "reports.log")
    executable(os.path.join(eng, "product", "make-handoff.py"),
               f"import sys\nopen({reports!r}, 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n")
    stitch = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")

    # A stand-in ffmpeg in front of the real one: records every call, and with FAKE_RENDER_FAIL=1 fails the
    # stitch itself (the only call carrying a filter graph) the way a dead encoder does, writing nothing.
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    argv_log = os.path.join(tmp, "ffmpeg.log")
    executable(os.path.join(bindir, "ffmpeg"),
               "#!/bin/bash\n"
               f"printf '%s\\n' \"$*\" >> {argv_log!r}\n"
               # a graph handed over in a file (-/filter_complex, -filter_complex_script) is logged too
               f"p=; for a in \"$@\"; do case \"$p\" in -/filter_complex|-filter_complex_script) "
               f"cat \"$a\" >> {argv_log!r}; echo >> {argv_log!r};; esac; p=\"$a\"; done\n"
               "if [ \"${FAKE_RENDER_FAIL:-0}\" = 1 ]; then for a in \"$@\"; do case \"$a\" in "
               "-filter_complex|-/filter_complex|-filter_complex_script) "
               "echo 'stand-in encoder failure' >&2; exit 1;; esac; done; fi\n"
               f"exec {FFMPEG!r} \"$@\"\n")

    media = os.path.join(tmp, "media")
    os.makedirs(media)
    clip = os.path.join(media, "clip.mp4")
    stale = os.path.join(media, "stale.mp4")
    for path, secs in ((clip, 4), (stale, 2.2)):
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=30:duration={secs}",
                        "-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={secs}",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", path], check=True)

    SAVED = {"segments": [{"clip": "clip.mp4", "start": 0.5, "end": 1.5, "transcript": "saved one"},
                          {"clip": "clip.mp4", "start": 2.0, "end": 3.2, "transcript": "saved two"}]}
    PLAN = {"segments": [{"clip": "clip.mp4", "start": 0.4, "end": 1.4, "transcript": "plan one"},
                         {"clip": "clip.mp4", "start": 2.1, "end": 3.3, "transcript": "plan two"}]}
    WORDS1 = {"clips": [{"clip": "clip.mp4", "words": [{"w": "hello", "start": 0.5, "end": 0.9, "prob": 0.9}]}]}
    WORDS2 = {"clips": [{"clip": "clip.mp4", "words": []}, {"clip": "other.mp4", "words": []}]}

    def job(scratch_plan=PLAN, words=None, stale_render=False):
        """The job folder my-reel (under projects/) with the saved cut, a fresh scratch folder holding scratch_plan (None: none)."""
        jd = os.path.join(eng, "projects", "my-reel")
        shutil.rmtree(jd, ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        os.link(clip, os.path.join(jd, "raw", "clip.mp4"))
        with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump(SAVED, fh, indent=1)
        if words is not None:
            with open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8") as fh:
                json.dump(words, fh)
        if stale_render:
            os.makedirs(os.path.join(jd, "outputs"))
            shutil.copy(stale, os.path.join(jd, "outputs", "my-reel.mp4"))
        scratch = os.path.join(tmp, "scratch", "reels-editing-engine", "my-reel")
        shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
        os.makedirs(scratch)
        if scratch_plan is not None:
            with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
                json.dump(scratch_plan, fh, indent=1)
        for f in (argv_log, reports):
            if os.path.exists(f):
                os.remove(f)
        return jd, scratch

    def run(venv="/nonexistent-venv", **env_extra):
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                   REELS_ENGINE_WHISPERX_VENV=venv, REELS_ENGINE_NOFW_VENV="/nonexistent-venv", VERIFY_CUT="0")
        for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "SNAP", "TRIM_RESTARTS", "WARM_MASTER", "VENC", "FAKE_RENDER_FAIL"):
            env.pop(k, None)
        env.update(env_extra)
        return subprocess.run(["bash", stitch, "/".join(("projects", "my-reel"))], cwd=eng, env=env, capture_output=True,
                              text=True, encoding="utf-8")

    def read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def called(path):
        return read(path) if os.path.exists(path) else ""

    def times(path):
        with open(path, encoding="utf-8") as fh:
            return [(round(s["start"], 2), round(s["end"], 2)) for s in json.load(fh)["segments"]]

    # 1. both encoders fail and write nothing, with the previous cut still at the output path
    jd, _ = job(stale_render=True)
    old_mp4 = open(os.path.join(jd, "outputs", "my-reel.mp4"), "rb").read()
    saved = read(os.path.join(jd, "transcript", "cuts.json"))
    r = run(VENC="h264_nvenc", FAKE_RENDER_FAIL="1")
    check("1: a render nothing wrote exits 3", r.returncode == 3, f"rc {r.returncode}\n{r.stderr[-600:]}")
    check("1: and never claims the previous cut as a clean render", "clean render" not in r.stderr, r.stderr[-400:])
    check("1: and says the file is the previous cut", "previous cut" in r.stderr, r.stderr[-400:])
    check("1: the old file is left exactly as it was",
          open(os.path.join(jd, "outputs", "my-reel.mp4"), "rb").read() == old_mp4)
    check("1: nothing is saved over the job's cut", read(os.path.join(jd, "transcript", "cuts.json")) == saved)
    check("1: the hardware report is filed for this one", len(called(reports).splitlines()) == 1, called(reports))

    # 2. VOICE_GAIN_DB set but empty is the default +10 dB, in the graph as in the toggles line
    job()
    r = run(VOICE_GAIN_DB="")
    log = called(argv_log)
    check("2: an empty VOICE_GAIN_DB renders", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-600:]}")
    check("2: with +10 dB in the graph, never 'volume=dB'", "volume=10dB" in log and "volume=dB" not in log, log[-300:])

    # 3. FLAT_RENDER=0, a plan that cannot be built, and a stale snapped EDL from an earlier run in the scratch folder
    bad = json.loads(json.dumps(PLAN))
    bad["segments"][0]["clip"] = "not-there.mp4"
    jd, scratch = job(scratch_plan=bad)
    with open(os.path.join(scratch, "cuts.snapped.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": [{"clip": "stale.mp4", "start": 1.0, "end": 2.0}]}, fh)
    saved = read(os.path.join(jd, "transcript", "cuts.json"))
    r = run(FLAT_RENDER="0")
    check("3: a FLAT_RENDER=0 run that cannot build the cut exits non-zero", r.returncode != 0, r.stderr[-400:])
    check("3: and says so in one plain line", "✗ could not build the cut" in r.stderr, r.stderr[-400:])
    check("3: and never saves a stale EDL over the job's cut", read(os.path.join(jd, "transcript", "cuts.json")) == saved)

    # 4. the scratch plan is gone: the job's saved plan is stitched instead, and it says so
    jd, _ = job(scratch_plan=None)
    r = run(FLAT_RENDER="0")
    check("4: no scratch plan: stitches the saved one", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-400:]}")
    check("4: and says which plan it used", "no cut plan waiting in the scratch folder" in r.stderr, r.stderr[-400:])
    check("4: the saved cut comes back unchanged", times(os.path.join(jd, "transcript", "cuts.json")) ==
          [(0.5, 1.5), (2.0, 3.2)], str(times(os.path.join(jd, "transcript", "cuts.json"))))

    # 5. a clip that is not there is not a hardware failure
    job(scratch_plan=bad)
    r = run()
    check("5: a missing clip exits non-zero", r.returncode not in (0, 3), f"rc {r.returncode}")
    check("5: as 'could not build the cut', not an integrity failure",
          "could not build the cut (reason above)" in r.stderr and "integrity" not in r.stderr, r.stderr[-400:])
    check("5: and files no hardware report", called(reports) == "", called(reports))

    # 6. a job with two clips: the restart pass does not run, said plainly, never "CRASHED"
    venv = os.path.join(tmp, "venv-real")
    os.makedirs(os.path.join(venv, "bin"))
    executable(os.path.join(venv, "bin", "python"), f"#!/bin/sh\nexec {sys.executable!r} \"$@\"\n")
    job(words=WORDS2)
    r = run(venv=venv, FLAT_RENDER="0", SNAP="0")
    check("6: a two-clip job still stitches", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-400:]}")
    check("6: and says plainly the restart pass reads one-clip jobs only",
          "one-clip jobs only" in r.stderr and "2-clip" in r.stderr and "CRASHED" not in r.stderr, r.stderr[-500:])

    # 7. the restart pass's ⚠ re-listen lines reach the log
    loud = os.path.join(tmp, "venv-warns")
    os.makedirs(os.path.join(loud, "bin"))
    executable(os.path.join(loud, "bin", "python"),
               "#!/bin/sh\necho '  ⚠ low-confidence cut 1.00->2.00 (avg word prob 0.20 < 0.5) — RE-LISTEN before render' >&2\n"
               "exit 0\n")
    job(words=WORDS1)
    r = run(venv=loud, FLAT_RENDER="0", SNAP="0")
    check("7: the restart pass's ⚠ lines are passed on",
          "[trim-restarts] ⚠ low-confidence cut 1.00->2.00" in r.stderr, r.stderr[-500:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else "stitch failures: loud, honest, and nothing stale is saved")
sys.exit(1 if fails else 0)
