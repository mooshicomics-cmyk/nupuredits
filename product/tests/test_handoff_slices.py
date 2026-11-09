#!/usr/bin/env python3
"""Regression guard: the CapCut handoff lays her cut as one clip per kept line, not one long clip.

The bug this locks down: on the medium route the main track arrived as a single clip of the whole cut, so there
were no cuts to see, trim or move, while every route promises each kept line its own clip. capcut_handoff.py now
splits the main track where the rough cut joined one line to the next (transcript/cuts.json).

What must hold: the split points are the running sum of the kept lines' lengths; a plan that does not add up to
the footage (a different base) gives no split; a punch-in piece is cut at the points inside it and keeps its
zoom; --one-clip exists.

Run: python3 product/tests/test_handoff_slices.py
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import capcut_handoff as H

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


jd = tempfile.mkdtemp()
os.makedirs(os.path.join(jd, "transcript"))
segs = [{"clip": "a.mp4", "start": 1.0, "end": 3.5}, {"clip": "a.mp4", "start": 5.0, "end": 6.0},
        {"clip": "a.mp4", "start": 9.0, "end": 11.25}]
with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
    json.dump({"segments": segs}, fh)
pts = H.slice_points(jd, 5.75)
check("split where each line ends", pts == [2.5, 3.5], str(pts))
check("a base of another length stays one clip", H.slice_points(jd, 40.0) == [])
check("no plan, no split", H.slice_points(tempfile.mkdtemp(), 5.75) == [])
pieces = H.split_at([(0.0, 2.0, 1.0, 0, 0), (2.0, 5.75, 1.1, 0.1, -0.2)], pts)
check("pieces cut at the points inside them", [(round(a, 2), round(b, 2)) for a, b, *_ in pieces]
      == [(0.0, 2.0), (2.0, 2.5), (2.5, 3.5), (3.5, 5.75)], str(pieces))
check("a punch-in piece keeps its zoom on every part", all(p[2] == 1.1 for p in pieces[1:]))
sped = [dict(segs[0], speed=2, played=1.25)] + segs[1:]          # her page's Speed: the first line plays 1.25 s, not 2.5
with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
    json.dump({"segments": sped}, fh)
pts2 = H.slice_points(jd, 4.5)
check("a sped line counts at the length it plays, so the main track still splits in sync", pts2 == [1.25, 2.25], str(pts2))
check("--one-clip is offered", "--one-clip" in open(os.path.join(PRODUCT, "capcut_handoff.py"), encoding="utf-8").read())

print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILED'}")
sys.exit(1 if fails else 0)
