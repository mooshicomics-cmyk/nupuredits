#!/usr/bin/env python3
"""Guards: the north star for sound. Her voice lands at -16 LUFS with true peak <= -1.5 dBTP, by one static gain;
a sound effect sits by its loudest moment under her voice; a short trimmed sound still measures.

  voice     a hot cut (about -9 LUFS) comes out at -16 +- 0.5 LUFS, true peak <= -1.4 dBTP; a second run leaves it
  sfx       a cue's loudest moment lands SFX_UNDER_VOICE_LU under the voice, never a peak above the cap
  short     a 0.3 s trimmed sound still has a loudness to measure (trimmed before the pad)

Run: python3 product/tests/test_voice_level.py
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import audio_levels as al  # noqa: E402
import voice_level as vl  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def make(path, src, secs, gain_db=0.0, extra=""):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}:duration={secs}",
                    "-af", f"volume={gain_db}dB{extra}", "-c:a", "aac", "-b:a", "192k", path], check=True)


def main():
    tmp = tempfile.mkdtemp(prefix="voice-level-")
    try:
        cut = os.path.join(tmp, "cut.mp4")                          # a voice-like signal, mastered hot
        make(cut, "anoisesrc=color=pink:amplitude=0.6", 8, 0.0, ",highpass=f=120,lowpass=f=6000")
        r = vl.level(cut)
        i, p = vl.measure(cut)
        check("voice: a hot cut lands at -16 LUFS", r["changed"] and abs(i - al.VOICE_TARGET_LUFS) <= 0.5, (r, i))
        check("voice: its true peak stays under the ceiling", p is not None and p <= al.TRUE_PEAK_CEILING_DBTP + 0.1, p)
        check("voice: a second run leaves it as it is", vl.level(cut)["changed"] is False)
        fx = os.path.join(tmp, "pop.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=900:duration=0.5",
                        "-af", "volume=-2dB", fx], check=True)
        mm = al.momentary_max_lufs(fx, 0.3)
        check("short: a 0.3 s trimmed sound still measures", mm is not None, mm)
        g = al.sfx_gain_for(fx, cut, 0.3)
        lands = mm + g if mm is not None else None
        pk = al.peak_dbfs(fx, 0.3) + g
        on_target = lands is not None and abs(lands - (i + al.SFX_UNDER_VOICE_LU)) <= 0.6
        check("sfx: its loudest moment sits under her voice, or its peak at the cap",
              on_target or abs(pk - al.SFX_PEAK_CAP_DBFS) <= 0.2, (lands, i, pk))
        check("sfx: never a peak above the cap", pk <= al.SFX_PEAK_CAP_DBFS + 0.2, pk)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_voice_level: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_voice_level: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
