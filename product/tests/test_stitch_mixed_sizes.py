#!/usr/bin/env python3
"""A cut whose clips come in different picture sizes, or in a vertical shape that is not 9:16, stitches into one
9:16 picture; and a sound track that comes out short of the picture is healed, or the stitch says why not.

Buyer report (2026-10-26, v2.3.15): three phone clips at 1408x1872, 1504x2000 and 1600x2128 (all about 3:4) in one
rough cut. concat refused to join pictures of different sizes ("Input link in0:v0 parameters (size 1504x2000, SAR
0:1) do not match ... (1408x1872 ...)"), the software fallback failed the same way, and the stitch refused to ship
the cut. Once his own patch let them join, the cut came out 3:4, so subject-zones refused it ("not the 9:16
authoring aspect") and nothing could be placed around him. And the stitch said "the sound track came out 100 ms
short of the picture" and then "the sound could not be rebuilt on its own", with no reason given.

  1. three vertical clips of three sizes, about 3:4 (his, scaled down): the stitch exits 0, the cut is exactly
     9:16 (subject-zones' own test passes), each piece fills the frame (no bars), and it decodes start to end
  2. one 3:4 clip alone: the cut is 9:16 too
  3. a cut whose clips already share one 9:16 size: no size filter in the graph, the cut keeps that size
  4. a landscape cut of two sizes: it joins on the bigger frame (the reframe to 9:16 comes later, as before)
  5. a clip whose sound stops 100 ms before its picture, cut to its very end: the sound track runs the
     picture's length, and the stitch never says the sound "could not be rebuilt"
  6. when the sound-only rebuild does fail, the warning says why (ffmpeg's own words), never nothing

Runs from a throwaway copy of the engine with short generated clips; nothing real is touched. Not run on Windows,
like test_stitch_mixed_rates.py: the stitch's Python there cannot run the bash ffmpeg wrapper.

Run:  python3 product/tests/test_stitch_mixed_sizes.py
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
JOB = "mixed-sizes"
SLACK = 1024 / 48000 + 1 / 24          # the stitch's own SYNC_SLACK: one AAC frame and one video frame
fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def executable(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def size(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    try:
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0                    # a half-written file (a stitch that stopped): no size to read


def stream(path, kind):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", f"{kind}:0", "-show_entries", "stream=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout.split()
    return float(out[0]) if out else None


def main():
    if os.name == "nt" or not FFMPEG or not FFPROBE or not shutil.which("bash"):
        print("stitch mixed sizes: skipped (needs bash, ffmpeg and ffprobe; not run on Windows)")
        return 0
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

        # ffmpeg is wrapped to keep the graph the stitch hands it, and (BREAK_SOUND_ONLY=1) to make the sound-only
        # rebuild fail the way a real ffmpeg failure would, with its reason on stderr
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        graph_log = os.path.join(tmp, "graph.log")
        executable(os.path.join(bindir, "ffmpeg"), "#!/bin/bash\n"
                   "p=; for a in \"$@\"; do case \"$p\" in -/filter_complex|-filter_complex_script) "
                   f"cat \"$a\" >> {graph_log!r}; echo >> {graph_log!r};; esac; p=\"$a\";\n"
                   "  case \"$a\" in *sound-only.m4a) if [ -n \"${BREAK_SOUND_ONLY:-}\" ]; then "
                   "echo 'Error initializing filter: stand-in sound fault' >&2; exit 1; fi;; esac; done\n"
                   f"exec {FFMPEG!r} \"$@\"\n")

        def make_clip(name, w, h, seconds, sound_short=0.0):
            path = os.path.join(tmp, name)
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30:duration={seconds}",
                            "-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=48000:duration={seconds - sound_short}",
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-y", path], check=True)
            return path

        jd = os.path.join(eng, "projects", JOB)
        scratch = os.path.join(tmp, "scratch", "reels-editing-engine", JOB)
        mp4 = os.path.join(jd, "outputs", JOB + ".mp4")

        def run(clips, plan, **extra):
            shutil.rmtree(jd, ignore_errors=True)
            shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
            os.makedirs(os.path.join(jd, "raw"))
            os.makedirs(os.path.join(jd, "transcript"))
            os.makedirs(scratch)
            for c in clips:
                shutil.copy(c, os.path.join(jd, "raw", os.path.basename(c)))
            with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
                json.dump({"segments": plan}, fh, indent=1)
            if os.path.exists(graph_log):
                os.remove(graph_log)
            env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                       REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                       VERIFY_CUT="0", VENC="libx264", TRIM_RESTARTS="0", SNAP="0", CLOSE_PAUSES="0", VOICE_LEVEL="0",
                       **extra)
            for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "WARM_MASTER"):
                env.pop(k, None)
            for k in ("BREAK_SOUND_ONLY",):
                if k not in extra:
                    env.pop(k, None)
            return subprocess.run(["bash", stitch, "projects/" + JOB], cwd=eng, env=env, capture_output=True,
                                  text=True, encoding="utf-8")

        def graph():
            return open(graph_log, encoding="utf-8").read() if os.path.exists(graph_log) else ""

        def clean(path):
            scan = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True, text=True)
            return scan.returncode == 0 and not scan.stderr.strip()

        def seg(clip, a, b):
            return {"clip": clip, "start": a, "end": b, "transcript": "x"}

        print("1. three vertical clips of three sizes, about 3:4")
        a = make_clip("a.mp4", 176, 234, 3)     # his 1408x1872, 1504x2000, 1600x2128, an eighth the size
        b = make_clip("b.mp4", 188, 250, 3)
        c = make_clip("c.mp4", 200, 266, 3)
        r = run([a, b, c], [seg("a.mp4", 0.2, 1.4), seg("b.mp4", 0.3, 1.5), seg("c.mp4", 0.4, 1.6)])
        check("the stitch exits 0 with the cut written", r.returncode == 0 and os.path.exists(mp4),
              f"exit {r.returncode}: {r.stderr[-600:]}")
        if os.path.exists(mp4):
            w, h = size(mp4)
            check(f"the cut is 9:16 by subject-zones' own test ({w}x{h})", w and abs(1080 / w - 1920 / h) <= 1e-3)
            check(f"on the biggest 9:16 frame its clips fill ({w}x{h}, want 144x256)", (w, h) == (144, 256))
            check("it decodes start to end", clean(mp4))
        g = graph()
        check("each piece is scaled to cover and cropped, never barred", g.count("crop=144:256") == 3 and "pad=" not in g,
              g[:400])
        check("the stitch says what it did", "every piece goes onto one 144x256 frame" in r.stderr, r.stderr[-400:])

        print("2. one 3:4 clip alone")
        r = run([c], [seg("c.mp4", 0.2, 1.4), seg("c.mp4", 1.6, 2.8)])
        check("the stitch exits 0", r.returncode == 0 and os.path.exists(mp4), f"exit {r.returncode}: {r.stderr[-600:]}")
        if os.path.exists(mp4):
            w, h = size(mp4)
            check(f"the cut is 9:16 ({w}x{h})", w and abs(1080 / w - 1920 / h) <= 1e-3)

        print("3. clips that already share one 9:16 size")
        d = make_clip("d.mp4", 144, 256, 3)
        e = make_clip("e.mp4", 144, 256, 3)
        r = run([d, e], [seg("d.mp4", 0.2, 1.4), seg("e.mp4", 0.3, 1.5)])
        check("the stitch exits 0", r.returncode == 0 and os.path.exists(mp4), f"exit {r.returncode}: {r.stderr[-600:]}")
        g = graph()
        check("no size filter in the graph", "crop=" not in g and "pad=" not in g, g[:400])
        if os.path.exists(mp4):
            check("the cut keeps its size", size(mp4) == (144, 256), str(size(mp4)))
        check("and nothing is said about sizes", "one 144x256 frame" not in r.stderr, r.stderr[-300:])

        print("4. a landscape cut of two sizes")
        f = make_clip("f.mp4", 256, 144, 3)
        g2 = make_clip("g.mp4", 320, 180, 3)
        r = run([f, g2], [seg("f.mp4", 0.2, 1.4), seg("g.mp4", 0.3, 1.5)])
        check("the stitch exits 0", r.returncode == 0 and os.path.exists(mp4), f"exit {r.returncode}: {r.stderr[-600:]}")
        if os.path.exists(mp4):
            check("it joins on the bigger frame", size(mp4) == (320, 180), str(size(mp4)))

        print("5. a clip whose sound stops 100 ms before its picture, cut to its very end")
        s1 = make_clip("s1.mp4", 144, 256, 3, sound_short=0.1)
        s2 = make_clip("s2.mp4", 144, 256, 3, sound_short=0.1)
        r = run([s1, s2], [seg("s1.mp4", 0.5, 3.0), seg("s2.mp4", 0.5, 3.0)])
        check("the stitch exits 0", r.returncode == 0 and os.path.exists(mp4), f"exit {r.returncode}: {r.stderr[-600:]}")
        if os.path.exists(mp4):
            v, au = stream(mp4, "v"), stream(mp4, "a")
            check(f"the sound track runs the picture's length (picture {v}, sound {au})",
                  v and au and abs(au - v) <= SLACK)
        check("it never gives up on the sound", "could not be rebuilt" not in r.stderr, r.stderr[-500:])

        print("6. the sound-only rebuild fails")
        # the full render's sound cut short (the drift test's stand-in), and the rebuild then refused by ffmpeg
        fault = os.path.join(bindir, "ffmpeg")
        body = open(fault, encoding="utf-8").read()
        executable(fault, body.replace(f"exec {FFMPEG!r} \"$@\"\n",
                   "full=0; out=; for a in \"$@\"; do [ \"$a\" = '[vc]' ] && full=1; out=\"$a\"; done\n"
                   f"{FFMPEG!r} \"$@\" || exit $?\n"
                   "if [ \"$full\" = 1 ]; then\n"
                   f"  {FFMPEG!r} -v error -y -i \"$out\" -map 0:v -map 0:a -c:v copy -af atrim=0:1.5 -c:a aac \"$out.cut.mp4\" "
                   "&& mv -f \"$out.cut.mp4\" \"$out\"\nfi\n"))
        r = run([d, e], [seg("d.mp4", 0.2, 1.4), seg("e.mp4", 0.3, 1.5)], BREAK_SOUND_ONLY="1")
        check("the stitch still exits 0 with the cut kept", r.returncode == 0 and os.path.exists(mp4),
              f"exit {r.returncode}: {r.stderr[-600:]}")
        warn = next((ln for ln in r.stderr.splitlines() if "could not be rebuilt" in ln), "")
        check("the warning gives ffmpeg's reason", "stand-in sound fault" in warn, r.stderr[-600:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("FAILED: " + "; ".join(fails) if fails else
                  "stitch mixed sizes: one 9:16 picture from clips of any size, and the sound runs the picture's length"))
    return 1 if fails else 0


def test_stitch_mixed_sizes():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
