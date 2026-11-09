#!/usr/bin/env python3
"""test_render_proves_itself.py — regression guard for the SILENT RENDER FAILURE.

The incident (2026-09-16, first PC tester): a render passed the gate, reported success, and the
overlay contained only the hook, captions and takeover — every note and graphic missing. The engine
then told her v4 was built and good WITHOUT A FRAME EVER BEING LOOKED AT. She found it herself.

Why nothing caught it: `hyperframes check` validates the COMPOSITION and passes before a single
frame is rendered, and the two output checks that did exist only asked "does this file carry real
alpha" and "is anything outside the safe zone". Both pass on a file that simply lost its content.

So the render now has to prove itself: read the rendered FILE at the times the plan says an element
is on screen, and refuse when it is blank there.

Run:  python3 product/tests/test_render_proves_itself.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reel_render as rr


def _overlay(path, visible_until, dur=6):
    """A real transparent ProRes 4444 whose ALPHA is opaque only up to `visible_until`.
    (Painting with drawbox alone is not enough — it writes luma and leaves alpha clear, which is
    invisible in exactly the way this check is looking for.)"""
    fc = ("[0:v]format=gray[m0];"
          f"[m0]drawbox=x=80:y=200:w=200:h=120:color=white:t=fill:enable='lt(t,{visible_until})'[mask];"
          "[1:v][mask]alphamerge[o]")
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", f"color=black:s=360x640:d={dur}:r=30",
                    "-f", "lavfi", "-i", f"color=white:s=360x640:d={dur}:r=30",
                    "-filter_complex", fc, "-map", "[o]",
                    "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", path],
                   check=True)
    return path


def main():
    if not rr._dur.__module__:          # ffmpeg/ffprobe absent: nothing to assert about
        return
    tmp = tempfile.mkdtemp(prefix="render-proof-")
    job = os.path.join(tmp, "projects", "job")
    comp = os.path.join(job, "comp")
    os.makedirs(comp)
    with open(os.path.join(job, "caption-plan.json"), "w", encoding="utf-8") as fp:
        json.dump({"elements": [{"kind": "note", "at": 1.0}, {"kind": "note", "at": 4.0}]}, fp)

    good = _overlay(os.path.join(tmp, "good.mov"), 6)
    bad = _overlay(os.path.join(tmp, "bad.mov"), 2)

    ok, _lines = rr._verify_render_has_content(good, comp)
    assert ok, "a healthy render must not be refused — a false alarm here blocks real work"
    print("✓ a healthy render passes")

    ok, lines = rr._verify_render_has_content(bad, comp)
    assert not ok, "a render that dropped a planned element was reported as fine"
    assert any("4.0" in l for l in lines), f"the failure must name WHEN it is empty: {lines}"
    print("✓ a render missing a planned element is refused, and says at what timestamp")

    # the plan is found by walking up from the composition, so no caller has to pass it
    assert rr._plan_expect_times(comp) == [1.0, 4.0]
    print("✓ the plan's on-screen times are discovered from the job folder")

    # a completely empty render is refused even with no plan to compare against
    empty = _overlay(os.path.join(tmp, "empty.mov"), 0)
    ok, lines = rr._verify_render_has_content(empty, os.path.join(tmp, "nowhere"))
    assert not ok, "an entirely empty render must never be reported as finished"
    print("✓ an entirely empty render is refused even with no plan present")

    print("\nrender proves itself: all checks passed")


if __name__ == "__main__":
    main()
