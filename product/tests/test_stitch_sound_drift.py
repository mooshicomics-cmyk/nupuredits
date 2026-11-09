#!/usr/bin/env python3
"""A stitch whose sound track comes out shorter than its picture heals itself; sound-check names it right.

Buyer reports (launch week, 2026-10-19): a rough cut came out with the picture whole and the sound track ending
early, no dead air at any joint, so her words ran ahead of her mouth toward the end. The stitch's self-heal only
checked the FILE's length (its longest stream), so it passed, and sound-check blamed a changed cut plan and said
"stitch again", which made the same file. Each buyer's Claude patched it by hand.

  1. a normal stitch: sound and picture tracks agree, and no sound rebuild happens
  2. a render whose sound track comes out 0.5 s short (an ffmpeg stand-in cuts it): the stitch notices, renders
     the sound graph alone (no picture chain in it), remuxes it under the picture, exits 0, and the tracks agree
  3. sound-check on a cut whose sound track ends early says the render lost sound, not that the plan changed;
     on a cut whose plan really changed it still says the plan changed

Runs from a throwaway copy of the engine with short generated clips; nothing real is touched.

Run:  python3 product/tests/test_stitch_sound_drift.py
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
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def executable(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


JOB = "sound-drift"
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
# Not on Windows, like test_stitch_mixed_rates.py: the stitch's Python there cannot run the bash ffmpeg wrapper.
if os.name == "nt" or not FFMPEG or not FFPROBE or not shutil.which("bash"):
    print("stitch sound drift: skipped (needs bash, ffmpeg and ffprobe; not run on Windows)")
    sys.exit(0)


def stream(path, kind):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", f"{kind}:0", "-show_entries", "stream=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout.split()
    return float(out[0]) if out else None


tmp = os.path.realpath(tempfile.mkdtemp())
try:
    eng = os.path.join(tmp, "engine")
    for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh",
                "product/video_encoder.py", "product/hdr.py", "product/probe.py"):
        if os.path.exists(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
    scripts = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts")
    shutil.copytree(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"), scripts,
                    ignore=shutil.ignore_patterns("__pycache__"))
    stitch = os.path.join(scripts, "stitch-cut.sh")

    # The stand-in for the fault: when FAULT is set, the full render (the one that maps the picture, [vc]) has its
    # sound track cut 0.5 s short after ffmpeg writes it. Every other ffmpeg run is the real one, untouched.
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    graph_log = os.path.join(tmp, "graph.log")
    executable(os.path.join(bindir, "ffmpeg"), "#!/bin/bash\n"
               "full=0; p=; out=\n"
               "for a in \"$@\"; do\n"
               f"  case \"$p\" in -/filter_complex|-filter_complex_script) cat \"$a\" >> {graph_log!r}; echo >> {graph_log!r};; esac\n"
               "  [ \"$a\" = '[vc]' ] && full=1; p=\"$a\"; out=\"$a\"\n"
               "done\n"
               f"{FFMPEG!r} \"$@\" || exit $?\n"
               "if [ \"$full\" = 1 ] && [ -n \"${FAULT:-}\" ]; then\n"
               f"  d=$({FFPROBE!r} -v error -select_streams a:0 -show_entries stream=duration -of default=nw=1:nk=1 \"$out\")\n"
               "  t=$(python3 -c \"print($d - 0.5)\")\n"
               f"  {FFMPEG!r} -v error -y -i \"$out\" -map 0:v -map 0:a -c:v copy -af \"atrim=0:$t\" -c:a aac \"$out.cut.mp4\" "
               "&& mv -f \"$out.cut.mp4\" \"$out\"\n"
               "fi\n")

    def make_clip(name, seconds):
        path = os.path.join(tmp, name)
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=96x64:rate=30:duration={seconds}",
                        "-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={seconds}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", "-y", path], check=True)
        return path

    clip = make_clip("a.mp4", 8)
    PLAN = {"segments": [{"clip": "a.mp4", "start": 0.20, "end": 2.40, "transcript": "one"},
                         {"clip": "a.mp4", "start": 3.00, "end": 5.10, "transcript": "two"},
                         {"clip": "a.mp4", "start": 5.50, "end": 7.60, "transcript": "three"}]}
    jd = os.path.join(eng, "projects", JOB)
    scratch = os.path.join(tmp, "scratch", "reels-editing-engine", JOB)
    mp4 = os.path.join(jd, "outputs", JOB + ".mp4")

    def run(fault):
        shutil.rmtree(jd, ignore_errors=True)
        shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        os.makedirs(scratch)
        shutil.copy(clip, os.path.join(jd, "raw", "a.mp4"))
        with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump(PLAN, fh, indent=1)
        if os.path.exists(graph_log):
            os.remove(graph_log)
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                   REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                   VERIFY_CUT="0", VENC="libx264", TRIM_RESTARTS="0", SNAP="0", CLOSE_PAUSES="0", VOICE_LEVEL="0")
        for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "WARM_MASTER", "FAULT"):
            env.pop(k, None)
        if fault:
            env["FAULT"] = "1"
        return subprocess.run(["bash", stitch, "projects/" + JOB], cwd=eng, env=env, capture_output=True,
                              text=True, encoding="utf-8")

    SLACK = 1024 / 48000 + 1 / 24

    print("1. a normal stitch")
    r = run(False)
    check("it renders", r.returncode == 0 and os.path.exists(mp4), f"exit {r.returncode}: {r.stderr[-500:]}")
    if os.path.exists(mp4):
        v, a = stream(mp4, "v"), stream(mp4, "a")
        check("sound and picture tracks agree", v and a and abs(a - v) <= SLACK, f"picture {v}, sound {a}")
    check("no sound rebuild on a clean render", "building the sound again" not in r.stderr, r.stderr[-400:])

    print("2. the render's sound track comes out 0.5 s short")
    r = run(True)
    check("the stitch still exits 0 with the cut written", r.returncode == 0 and os.path.exists(mp4),
          f"exit {r.returncode}: {r.stderr[-500:]}")
    check("it says the sound came out short and rebuilds it", "came out" in r.stderr and "short of the picture" in r.stderr
          and "building the sound again on its own" in r.stderr, r.stderr[-600:])
    check("it says they now match", "they now match" in r.stderr, r.stderr[-400:])
    if os.path.exists(mp4):
        v, a = stream(mp4, "v"), stream(mp4, "a")
        check("after the heal the sound track runs the picture's length", v and a and abs(a - v) <= SLACK,
              f"picture {v}, sound {a}")
        scan = subprocess.run([FFMPEG, "-v", "error", "-i", mp4, "-f", "null", "-"], capture_output=True, text=True)
        check("the healed cut decodes start to end", scan.returncode == 0 and not scan.stderr.strip(), scan.stderr[-300:])
    sg = os.path.join(scratch, "graph-sound.txt")
    sound_graph = open(sg, encoding="utf-8").read() if os.path.exists(sg) else ""
    check("the rebuild's graph is the sound chains alone (ends in the master, no picture chain)",
          sound_graph.rstrip().endswith("[ao]") and "[vc]" not in sound_graph and "[v0]" not in sound_graph
          and "acrossfade" in sound_graph, sound_graph[-300:])
    leftovers = [f for f in os.listdir(os.path.dirname(mp4)) if "resound" in f]
    check("no rebuild file left beside the cut", not leftovers, str(leftovers))

    print("3. sound-check reads a short sound track as the render, not a changed plan")
    sc = os.path.join(scripts, "sound-check.py")

    def sound_check(audio_s, plan_end):
        sj = os.path.join(tmp, "sc", JOB)
        shutil.rmtree(os.path.join(tmp, "sc"), ignore_errors=True)
        os.makedirs(os.path.join(sj, "outputs"))
        os.makedirs(os.path.join(sj, "transcript"))
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30:duration=4",
                        "-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={audio_s}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-y",
                        os.path.join(sj, "outputs", JOB + ".mp4")], check=True)
        with open(os.path.join(sj, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump({"segments": [{"clip": "a.mp4", "start": 0.0, "end": plan_end}]}, fh)
        return subprocess.run([sys.executable, sc, sj], capture_output=True, text=True, encoding="utf-8").stdout

    out = sound_check(3.5, 4.0)
    check("a sound track 0.5 s short of the picture is named as the render losing sound",
          "sound came out short in the render" in out and "plan changed" not in out, out[-500:])
    out = sound_check(4.0, 4.6)
    check("a plan that really changed is still named as a changed plan", "plan changed" in out, out[-500:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "stitch sound drift: a short sound track is rebuilt under the picture"))
sys.exit(1 if fails else 0)
