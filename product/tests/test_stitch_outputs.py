#!/usr/bin/env python3
"""What the stitch and the word timings hand back, and what they leave in the scratch folder.

  1. stdout is the path of what the run made: the base cut after a render, the saved EDL (transcript/cuts.json)
     after FLAT_RENDER=0. The cut's length is in the log line that names it.
  2. The scratch folder holds cuts.edges.json (the plan after the boundary snap) and edl.json (the plan on the
     frame grid), and the saved transcript/cuts.json is that EDL byte for byte.
  3. A stale EDL from an earlier run is never saved over the job's cut, under either name it has had.
  4. The master's limiter is written with only the settings it changes: the ceiling, level=false, latency=true.
  5. word-timings.sh, handing back a job that was heard before, prints the job's own transcript path.

Runs from a throwaway copy of the engine with a short generated clip; nothing real is touched.

Run:  python3 product/tests/test_stitch_outputs.py
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
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def executable(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


JOB = "my-reel"                      # the throwaway job every step below builds
FFMPEG = shutil.which("ffmpeg")
if os.name == "nt" or not FFMPEG or not shutil.which("ffprobe") or not shutil.which("bash"):
    print("stitch outputs: skipped (needs bash, ffmpeg and ffprobe)")
    sys.exit(0)

tmp = os.path.realpath(tempfile.mkdtemp())   # the scripts print real paths (macOS /var is /private/var)
try:
    eng = os.path.join(tmp, "engine")
    for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh", "product/video_encoder.py", "product/hdr.py", "product/probe.py"):
        if os.path.exists(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
    scripts = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts")
    shutil.copytree(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"), scripts,
                    ignore=shutil.ignore_patterns("__pycache__"))
    stitch = os.path.join(scripts, "stitch-cut.sh")

    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    argv_log = os.path.join(tmp, "ffmpeg.log")
    executable(os.path.join(bindir, "ffmpeg"), "#!/bin/bash\n"
               f"printf '%s\\n' \"$*\" >> {argv_log!r}\n"
               # a graph handed over in a file (-/filter_complex, -filter_complex_script) is logged too
               f"p=; for a in \"$@\"; do case \"$p\" in -/filter_complex|-filter_complex_script) "
               f"cat \"$a\" >> {argv_log!r}; echo >> {argv_log!r};; esac; p=\"$a\"; done\n"
               f"exec {FFMPEG!r} \"$@\"\n")

    clip = os.path.join(tmp, "clip.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)

    PLAN = {"segments": [{"clip": "clip.mp4", "start": 0.4, "end": 1.4, "transcript": "one"},
                         {"clip": "clip.mp4", "start": 2.1, "end": 3.3, "transcript": "two"}]}
    WORDS = {"clips": [{"clip": "clip.mp4", "duration": 4.0, "words": [
        {"word": "one", "start": 0.5, "end": 1.3, "score": 0.9}, {"word": "two", "start": 2.2, "end": 3.2, "score": 0.9}]}]}
    jd = os.path.join(eng, "projects", JOB)
    scratch = os.path.join(tmp, "scratch", "reels-editing-engine", JOB)

    def job(plan=PLAN, stale=False):
        shutil.rmtree(jd, ignore_errors=True)
        shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        os.makedirs(scratch)
        os.link(clip, os.path.join(jd, "raw", "clip.mp4"))
        for path, doc in ((os.path.join(jd, "transcript", "words.json"), WORDS),
                          (os.path.join(jd, "transcript", "cuts.json"), PLAN),
                          (os.path.join(scratch, "cuts.json"), plan)):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=1)
        if stale:
            for name in ("edl.json", "cuts.snapped.json"):
                with open(os.path.join(scratch, name), "w", encoding="utf-8") as fh:
                    json.dump({"segments": [{"clip": "stale.mp4", "start": 1.0, "end": 2.0}]}, fh)
        if os.path.exists(argv_log):
            os.remove(argv_log)

    def run(**env_extra):
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                   REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                   VERIFY_CUT="0", VENC="libx264")
        for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "SNAP", "TRIM_RESTARTS", "WARM_MASTER"):
            env.pop(k, None)
        env.update(env_extra)
        return subprocess.run(["bash", stitch, "projects/" + JOB], cwd=eng, env=env, capture_output=True,
                              text=True, encoding="utf-8")

    def read(path):
        with open(path, "rb") as fh:
            return fh.read()

    print("1-2. an EDL-only stitch")
    job()
    r = run(FLAT_RENDER="0")
    kept = os.path.join(jd, "transcript", "cuts.json")
    check("it stitches", r.returncode == 0, r.stderr[-600:])
    check("stdout is the saved EDL's path, and only that", r.stdout.strip() == kept, repr(r.stdout))
    check("the scratch folder holds the snapped plan as cuts.edges.json",
          os.path.exists(os.path.join(scratch, "cuts.edges.json")), os.listdir(scratch))
    check("and the frame-grid EDL as edl.json", os.path.exists(os.path.join(scratch, "edl.json")), os.listdir(scratch))
    check("transcript/cuts.json is edl.json byte for byte", read(kept) == read(os.path.join(scratch, "edl.json")))
    check("nothing under the earlier names", not {"cuts.refined.json", "cuts.snapped.json"} & set(os.listdir(scratch)),
          os.listdir(scratch))

    print("1, 4. a rendered stitch, both masters")
    for warm, ceiling in (("1", "0.89"), ("0", "0.501")):
        job()
        r = run(WARM_MASTER=warm)
        mp4 = os.path.join(jd, "outputs", JOB + ".mp4")
        check(f"WARM_MASTER={warm}: it renders", r.returncode == 0 and os.path.exists(mp4), r.stderr[-600:])
        check(f"WARM_MASTER={warm}: stdout is the base cut's path, and only that", r.stdout.strip() == mp4, repr(r.stdout))
        check(f"WARM_MASTER={warm}: the log names it with its length",
              any(l.startswith(f"[stitch] wrote {mp4} (") and l.endswith(" s)") for l in r.stderr.splitlines()),
              r.stderr[-400:])
        graph = open(argv_log, encoding="utf-8").read() if os.path.exists(argv_log) else ""
        check(f"WARM_MASTER={warm}: limiter = alimiter=limit={ceiling}:level=false:latency=true",
              f"alimiter=limit={ceiling}:level=false:latency=true[ao]" in graph, graph[-300:])

    print("3. a stale EDL under either name never reaches the job's cut")
    bad = json.loads(json.dumps(PLAN))
    bad["segments"][0]["clip"] = "not-there.mp4"
    job(plan=bad, stale=True)
    saved = read(os.path.join(jd, "transcript", "cuts.json"))
    r = run(FLAT_RENDER="0")
    check("a plan that cannot be built exits non-zero", r.returncode != 0, r.stderr[-400:])
    check("and the job's cut is untouched", read(os.path.join(jd, "transcript", "cuts.json")) == saved)
    check("and stdout stays empty", r.stdout.strip() == "", repr(r.stdout))

    print("6. an HDR clip that skipped intake is converted in the stitch, not only re-tagged")
    job()
    hlg = os.path.join(tmp, "clip-hlg.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", clip, "-vf",
                    "colorspace=all=bt2020:format=yuv420p10:iall=bt709,"
                    "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc",
                    "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1",
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "-c:a", "copy", hlg], check=True)
    os.remove(os.path.join(jd, "raw", "clip.mp4"))
    shutil.copy(hlg, os.path.join(jd, "raw", "clip.mp4"))
    r = run()
    graph = open(argv_log, encoding="utf-8").read() if os.path.exists(argv_log) else ""
    check("it renders", r.returncode == 0, r.stderr[-600:])
    check("each segment of the HDR clip is converted first", graph.count("[0:v]colorspace=ispace=bt2020nc") == 2,
          graph[-400:])
    job()
    run()
    graph = open(argv_log, encoding="utf-8").read() if os.path.exists(argv_log) else ""
    check("a standard-colour clip is not", "colorspace=ispace" not in graph, graph[-300:])

    print("7. a clip she sped up and gave a zoom move (her page's Speed and Zoom)")
    fx = json.loads(json.dumps(PLAN))
    fx["segments"][0].update(speed=2, zoom={"from": 1.15, "to": 1.0})
    job(plan=fx)
    with open(os.path.join(jd, "subject-zones.json"), "w", encoding="utf-8") as fh:   # her head measured left of centre
        json.dump({"reading": {"source": {"w": 320, "h": 240}},
                   "subject_src_px": {"left": 40, "right": 120, "head_top": 20, "chin_bottom": 100}}, fh)
    r = run(SNAP="0", TRIM_RESTARTS="0")
    mp4 = os.path.join(jd, "outputs", JOB + ".mp4")
    graph = open(argv_log, encoding="utf-8").read() if os.path.exists(argv_log) else ""
    check("it renders", r.returncode == 0 and os.path.exists(mp4), r.stderr[-600:])
    check("the sped clip's sound is re-timed (atempo) and its picture too (setpts / 2)",
          "atempo=2.000000" in graph and "setpts=(PTS-STARTPTS)/2" in graph, graph[-600:])
    check("the zoom move is a per-frame perspective, bicubic, eased from 1.15 to 1.0 over the clip's 15 frames",
          "perspective=" in graph and "eval=frame" in graph and "interpolation=cubic" in graph
          and "(1.15000+(-0.15000)*((min(1,in/14))*(min(1,in/14))*(3-2*(min(1,in/14)))))" in graph, graph[-900:])
    check("it holds still on her face (subject-zones.json), not the frame's middle", "0.25000*W" in graph and "0.25000*H" in graph,
          graph[-900:])
    check("only the clip with a zoom gets one", graph.count("perspective=") == 1, graph.count("perspective="))
    edl = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    check("the saved cut keeps both, and the sped clip's played length", edl[0].get("speed") == 2
          and edl[0].get("zoom") == {"from": 1.15, "to": 1.0} and abs(edl[0].get("played", 0) - 0.5) < 0.02, edl[0])
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                         capture_output=True, text=True).stdout.strip()
    check("the render runs the sped length (0.5 s + 1.2 s)", abs(float(out or 0) - 1.7) < 0.08, out)
    cap = json.load(open(os.path.join(jd, "outputs", JOB + ".transcript.json"), encoding="utf-8"))
    two = [w for w in cap.get("words", []) if w.get("text") == "two"]
    check("the words after it land where they play (kept-words maps through the speed)",
          two and abs(float(two[0]["start"]) - (0.5 + 0.1)) < 0.06, two)

    print("8. one fluid clip that eases from fast to slower (a speed ramp), with an eased zoom-out")
    rp = json.loads(json.dumps(PLAN))
    rp["segments"][0].update(speed={"from": 2.6, "to": 1.4, "ease": "out"}, zoom={"from": 1.3, "to": 1.0, "ease": "out"})
    job(plan=rp)
    r = run(SNAP="0", TRIM_RESTARTS="0")
    graph = open(argv_log, encoding="utf-8").read() if os.path.exists(argv_log) else ""
    check("it renders", r.returncode == 0 and os.path.exists(mp4), r.stderr[-800:])
    check("the ramp is one clip, its footage re-timed along the eased curve (no pieces)", "while(lt(ld(3),32)" in graph
          and graph.count("[0:v]") == 2 and "atempo=1.800000" in graph, graph[-1200:])
    check("the zoom-out eases out too", "(1.30000+(-0.30000)*(1-(1-(min(1,in/" in graph, graph[-900:])
    edl = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    check("the saved cut keeps the ramp, its average as the speed, and the played length (1.0 s / 1.8 on whole frames)",
          edl[0].get("ramp") == {"from": 2.6, "to": 1.4, "ease": "out"} and abs(edl[0].get("speed", 0) - 1.8) < 1e-6
          and abs(edl[0].get("played", 0) - 17 / 30) < 0.002, edl[0])
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                         capture_output=True, text=True).stdout.strip()
    check("the render runs the ramped length (0.567 s + 1.2 s)", abs(float(out or 0) - (17 / 30 + 1.2)) < 0.08, out)

    print("5. word-timings.sh handing back a heard job")
    job()
    env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), REELS_ENGINE_FORCE_NOFW="")
    env.pop("REELS_ENGINE_FORCE_NOFW")
    r = subprocess.run(["bash", os.path.join(scripts, "word-timings.sh"), "projects/" + JOB], cwd=eng, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    canon = os.path.join(jd, "transcript", "words.json")
    check("it hands the transcript back", r.returncode == 0, r.stderr[-400:])
    check("stdout is the job's own transcript path", r.stdout.strip() == canon, repr(r.stdout))
    check("its log lines carry its own name", r.stderr.startswith("[word-timings] "), r.stderr[:200])
    check("the scratch copy is still written", read(os.path.join(scratch, "words.json")) == read(canon))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nthe render's Python never reuses a helper's name for a value (a framed or sped segment calls it later)")
import ast
src = read(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")).decode("utf-8")
body = src.split("<<'PY'", 1)[1].split("\nPY\n", 1)[0].split("\n", 1)[1]
tree = ast.parse(body)
helpers = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def outside_functions(node):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.Lambda)):
            continue
        yield child
        yield from outside_functions(child)


reused = sorted({t.id for n in outside_functions(tree) if isinstance(n, (ast.Assign, ast.For, ast.AugAssign))
                 for t in ast.walk(n.targets[0] if isinstance(n, ast.Assign) else n.target)
                 if isinstance(t, ast.Name) and t.id in helpers})
check(f"no helper name is assigned at the top level ({len(helpers)} helpers)", not reused, ", ".join(reused))

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "stitch outputs: each run hands back the file it made"))
sys.exit(1 if fails else 0)
