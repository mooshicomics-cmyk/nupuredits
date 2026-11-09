#!/usr/bin/env python3
"""Guard: every named grade look is a filter string this machine's ffmpeg actually accepts, and no
grade is ever applied unless asked for.

Why a real ffmpeg run and not a string check: a filter that parses on one build and not another is
exactly the cross-device failure this engine keeps hitting. Each look is run through ffmpeg on a
one-second synthetic clip to a null sink. If a look fails here, it would fail on a buyer's reel.

Run: python3 product/tests/test_video_grade.py
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import video_grade as VG

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def main():
    print("video grade\n")
    for off in ("", None, "none", "off", "NO"):
        check(f"no grade for {off!r}", VG.grade_filter(off) is None)
    try:
        VG.grade_filter("cinematik")
        check("unknown look fails loud", False, "no exception raised")
    except ValueError:
        check("unknown look fails loud", True)

    have_ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
    check("ffmpeg present", have_ffmpeg)
    if not have_ffmpeg:
        print("\n  (skipping live filter checks: ffmpeg not on PATH)")
    else:
        for look in VG.LOOKS:
            f = VG.grade_filter(look)
            r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=10:duration=1",
                                "-vf", f, "-f", "null", "-"], capture_output=True, text=True)
            check(f"look '{look}' renders through this ffmpeg", r.returncode == 0, r.stderr.strip()[-200:])

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
