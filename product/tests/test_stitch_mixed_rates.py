#!/usr/bin/env python3
"""A cut that mixes frame rates (an iPhone's 59.94 one day and 60 the next) stitches into a clean render.

ISS-121: the stitch used to re-time each sped segment onto its OWN clip's rate and hand concat each clip's own
frame times, so a cut that joined 59.94 and 60 fps clips put two frames on one tick of the output ("non
monotonically increasing dts") and the render failed its integrity check on both encoders. Now every sped
segment is re-timed onto the cut's one rate (its first clip's) and one fps filter follows a mixed-rate join.

  1. a cut joining a 60000/1001 fps clip and a 60 fps clip, one segment sped to 1.03, renders and passes the
     stitch's own integrity check (exit 0, the base cut written)
  2. on the render's own frame grid its frame times strictly increase (no two frames on one tick), and it
     decodes start to end without an error
  3. the render is on the cut's one rate (the first clip's, 60000/1001)
  4. the graph re-times the sped segment on that rate and adds exactly one rate filter after the join
  5. a cut on one rate gets no rate filter after the join at all

Runs from a throwaway copy of the engine with short generated clips; nothing real is touched.

Run:  python3 product/tests/test_stitch_mixed_rates.py
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from fractions import Fraction

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


JOB = "mixed-rates"
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
# Not on Windows, like test_stitch_outputs.py: the stitch's Python there cannot run the bash ffmpeg wrapper below.
if os.name == "nt" or not FFMPEG or not FFPROBE or not shutil.which("bash"):
    print("stitch mixed rates: skipped (needs bash, ffmpeg and ffprobe; not run on Windows)")
    sys.exit(0)

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

    # ffmpeg is wrapped only to keep the graph the stitch hands it (it goes over in a file)
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    graph_log = os.path.join(tmp, "graph.log")
    executable(os.path.join(bindir, "ffmpeg"), "#!/bin/bash\n"
               f"p=; for a in \"$@\"; do case \"$p\" in -/filter_complex|-filter_complex_script) "
               f"cat \"$a\" >> {graph_log!r}; echo >> {graph_log!r};; esac; p=\"$a\"; done\n"
               f"exec {FFMPEG!r} \"$@\"\n")

    def make_clip(name, rate, freq, seconds):
        path = os.path.join(tmp, name)
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=96x64:rate={rate}:duration={seconds}",
                        "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000:duration={seconds}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", "-y", path], check=True)
        return path

    # The fault shows once enough of the 60 fps clip sits in the 59.94 cut for the two clocks to drift a whole
    # frame apart: 1 / (60 - 59.94) is about 17 s, so the 60 fps clip runs 21 s (tiny frames keep it quick).
    clips = {"a.mp4": make_clip("a.mp4", "60000/1001", 330, 3), "b.mp4": make_clip("b.mp4", "60", 440, 21)}

    # The cut opens on the 59.94 clip (so that is the cut's rate), then plays the 60 fps clip, one stretch sped up.
    MIXED = {"segments": [
        {"clip": "a.mp4", "start": 0.20, "end": 1.60, "transcript": "one"},
        {"clip": "b.mp4", "start": 0.30, "end": 8.00, "transcript": "two", "speed": 1.03},
        {"clip": "a.mp4", "start": 1.80, "end": 2.70, "transcript": "three"},
        {"clip": "b.mp4", "start": 8.20, "end": 20.50, "transcript": "four"},
    ]}
    ONE_RATE = {"segments": [dict(s, clip="b.mp4") for s in MIXED["segments"]]}
    jd = os.path.join(eng, "projects", JOB)
    scratch = os.path.join(tmp, "scratch", "reels-editing-engine", JOB)
    mp4 = os.path.join(jd, "outputs", JOB + ".mp4")

    def job(plan):
        shutil.rmtree(jd, ignore_errors=True)
        shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        os.makedirs(scratch)
        for name, path in clips.items():
            shutil.copy(path, os.path.join(jd, "raw", name))
        with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1)
        if os.path.exists(graph_log):
            os.remove(graph_log)

    def run():
        # No transcript, so none of the listening passes runs: the plan goes straight to the render.
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                   REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                   VERIFY_CUT="0", VENC="libx264", TRIM_RESTARTS="0", SNAP="0", CLOSE_PAUSES="0")
        for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "WARM_MASTER"):
            env.pop(k, None)
        return subprocess.run(["bash", stitch, "projects/" + JOB], cwd=eng, env=env, capture_output=True,
                              text=True, encoding="utf-8")

    def graph():
        if not os.path.exists(graph_log):
            return ""
        with open(graph_log, encoding="utf-8") as fh:
            return fh.read()

    def probe(*args):
        return subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", *args, mp4],
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    print("1-4. a cut joining 59.94 and 60 fps clips, one segment sped to 1.03")
    job(MIXED)
    r = run()
    check("it renders and passes the stitch's integrity check", r.returncode == 0 and os.path.exists(mp4),
          f"exit {r.returncode}: {r.stderr[-500:]}")
    if os.path.exists(mp4):
        rate = probe("-show_entries", "stream=r_frame_rate", "-of", "csv=p=0")
        check("it is on the cut's one rate, the first clip's (60000/1001)", rate == "60000/1001", rate)
        # Each frame's time, as a tick of the render's own frame grid (what a player and the muxer count in).
        fps = Fraction(rate or "1")
        times = [Fraction(t) for t in probe("-show_entries", "packet=dts_time", "-of", "csv=p=0").split()
                 if t not in ("", "N/A")]
        ticks = [round(t * fps) for t in times]
        dup = next((i for i in range(1, len(ticks)) if ticks[i] <= ticks[i - 1]), None)
        check("on its own frame grid every frame's time strictly increases (no two frames on one tick)",
              len(ticks) > 1000 and dup is None, f"{len(ticks)} frames; tick {ticks[dup] if dup else ''} repeats")
        scan = subprocess.run([FFMPEG, "-v", "error", "-i", mp4, "-f", "null", "-"], capture_output=True, text=True)
        check("it decodes start to end without a single error", scan.returncode == 0 and not scan.stderr.strip(),
              scan.stderr[-300:])
    g = graph()
    check("the sped segment is re-timed on the cut's rate", "setpts=(PTS-STARTPTS)/1.03,fps=60000/1001," in g, g[:300])
    check("one rate filter follows the join", g.count("concat=n=4:v=1:a=0,fps=60000/1001[vc]") == 1, g[-300:])

    print("5. the same cut on one rate")
    job(ONE_RATE)
    r = run()
    check("it renders", r.returncode == 0 and os.path.exists(mp4), r.stderr[-500:])
    check("no rate filter after the join", "concat=n=4:v=1:a=0[vc]" in graph(), graph()[-300:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "stitch mixed rates: a 59.94 + 60 fps cut renders clean"))
sys.exit(1 if fails else 0)
