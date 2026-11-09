#!/usr/bin/env python3
"""Guard: a sound on a look's entrance that has barely started by the end of the motion (a riser, a slow swell, a
whoosh with a soft lead-in) plays through its loudest moment instead of being cut to the motion's length, which
left only its silent start and she heard nothing. A hit that is loud from the first frame is still cut to the
motion. Runs on generated tones in a temp folder, with the level cache pointed there too."""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sound_plan as SP  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main():
    if not shutil.which("ffmpeg"):
        print("test_sound_slow_start: skipped (ffmpeg not installed)")
        return 0
    tmp = tempfile.mkdtemp()
    saved = (SP.LEVELS, SP._levels_mem)
    SP.LEVELS, SP._levels_mem = os.path.join(tmp, "levels.json"), None
    fails = []
    try:
        riser = os.path.join(tmp, "riser.wav")       # 1.5 s of near-silence, then 1 s of full tone
        ff("-f", "lavfi", "-i", "sine=frequency=500:duration=1.5", "-f", "lavfi", "-i", "sine=frequency=500:duration=1",
           "-filter_complex", "[0]volume=-50dB[a];[a][1]concat=n=2:v=0:a=1", riser)
        hit = os.path.join(tmp, "hit.wav")           # loud from the start
        ff("-f", "lavfi", "-i", "sine=frequency=500:duration=2", hit)
        t = SP._trim_for("pop", 0.25, 2.5, riser)
        ok = t is not None and 1.5 <= t <= 2.5
        print(f"  {'PASS' if ok else 'FAIL'}  a late-peaking sound plays through its loudest moment ({t})")
        ok or fails.append("riser")
        t = SP._trim_for("pop", 0.25, 2.0, hit)
        ok = t == 0.25
        print(f"  {'PASS' if ok else 'FAIL'}  a sound loud from the start is still cut to the motion ({t})")
        ok or fails.append("hit")
        t = SP._trim_for("pop", 0.25, 2.5)
        ok = t == 0.25
        print(f"  {'PASS' if ok else 'FAIL'}  with no file, the motion's length as before ({t})")
        ok or fails.append("nofile")
    finally:
        SP.LEVELS, SP._levels_mem = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
