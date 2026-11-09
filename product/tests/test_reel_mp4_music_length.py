#!/usr/bin/env python3
"""test_reel_mp4_music_length.py — the well-done bake lays the music bed under the whole reel.

build-reel-mp4.py trims the bed to the reel's length, read from caption-plan.json "duration". That field is
optional and real plans leave it out; the length then came out as 0, the bed was trimmed to 0.1 s, and the
finished reel had no music at all, with nothing said. With no "duration" the bed now runs the length of the
base cut, measured with ffprobe. A plan that has a "duration" is untouched: it still decides where the bed
ends.

Runs the real bake in a scratch copy of the engine (its product/*.py), on a tiny silent base cut, so the
only sound in the finished file is the bed.

Run:  python3 product/tests/test_reel_mp4_music_length.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-300:]) if detail else ''}")


def rms_db(path, start, end):
    """RMS level (dBFS) of the file's audio between start and end; very low when silent."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-af", f"atrim={start}:{end},astats", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"RMS level dB:\s*(-?inf|-?[\d.]+)", r.stderr)
    if not m:
        return None
    v = m[-1]                                    # the Overall block comes last
    return -999.0 if "inf" in v else float(v)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_reel_mp4_music_length: skipped (ffmpeg/ffprobe not installed)")
        return 0
    tmp = tempfile.mkdtemp(prefix="reel-mp4-music-")
    try:
        eng = os.path.join(tmp, "engine")
        os.makedirs(os.path.join(eng, "product"))
        for f in os.listdir(PRODUCT):
            if f.endswith(".py"):
                shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
        job = os.path.join(eng, "projects", "job")
        for sub in ("outputs", "audio"):
            os.makedirs(os.path.join(job, sub))
        base = os.path.join(job, "outputs", "job.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=gray:s=108x192:d=4:r=30",
                        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", base], check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                        "-af", "volume=-12dB", os.path.join(job, "audio", "bed.wav")], check=True)
        overlay = os.path.join(tmp, "overlay.mov")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=black@0.0:s=108x192:d=1:r=30,format=yuva444p10le",
                        "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", overlay], check=True)
        music = {"file": "bed.wav", "at": 0.5, "fade_in": 0.1, "fade_out": 0.3, "gain_db": 0, "loop": False}

        def bake(plan, name):
            with open(os.path.join(job, "caption-plan.json"), "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            out = os.path.join(tmp, name)
            env = dict(os.environ, JOB="job", OVERLAY=overlay, OUT=out, VENC="libx264",
                       PYTHONDONTWRITEBYTECODE="1")
            r = subprocess.run([sys.executable, os.path.join(eng, "product", "build-reel-mp4.py")],
                               capture_output=True, text=True, env=env, timeout=600)
            return r.returncode, r.stdout + r.stderr, out

        rc, said, out = bake({"music": music}, "no-duration.mp4")
        check("a plan with no duration still bakes", rc == 0 and os.path.exists(out), said)
        lvl = rms_db(out, 1.0, 3.5)
        check("with no duration in the plan, the bed runs under the rest of the reel",
              lvl is not None and lvl > -40, lvl)

        handoff = next((l for l in said.splitlines() if "capcut_handoff.py" in l), "")
        check("the CapCut step it prints runs as printed: under uv, handed this bake's overlay",
              "uv run product/capcut_handoff.py job" in handoff and "--overlay" in handoff
              and os.path.basename(overlay) in handoff, handoff)

        rc, said, out = bake({"music": music, "duration": 2.0}, "with-duration.mp4")
        check("a plan with a duration bakes", rc == 0 and os.path.exists(out), said)
        during, after = rms_db(out, 1.0, 1.6), rms_db(out, 2.4, 3.8)
        check("a plan's own duration still decides where the bed ends",
              during is not None and during > -40 and after is not None and after < -80, (during, after))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_reel_mp4_music_length: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_reel_mp4_music_length: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
