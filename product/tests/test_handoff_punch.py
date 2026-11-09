#!/usr/bin/env python3
"""The medium route's CapCut draft keeps the plan's punch-ins.

separate_layers.sh hands each rendered layer to capcut_handoff.py, which laid her cut as ONE clip at 1.0, so a
"this is a punch-in" line arrived unzoomed (first-reel, v2.2.8). With --punch the caption plan's windows become
their own pieces of the main track at the plan's scale, held on her face, and the pieces still tile the cut
exactly so every graphic above stays in sync.

Run: python3 product/tests/test_handoff_punch.py   (Windows: python)
"""
import importlib.util, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:200]})"))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("capcut_handoff", os.path.join(ROOT, "product", "capcut_handoff.py"))
ch = importlib.util.module_from_spec(spec); spec.loader.exec_module(ch)
import capcut_motion


def tiles(pieces, dur):
    t = 0.0
    for s, e, *_ in pieces:
        if abs(s - t) > 1e-6 or e <= s:
            return False
        t = e
    return abs(t - dur) < 1e-6


tmp = tempfile.mkdtemp(prefix="handoff-punch-")
try:
    jd = os.path.join(tmp, "my-reel"); os.makedirs(jd)
    plan_p = os.path.join(jd, "caption-plan.json")

    p = ch.footage_pieces(jd, "/nonexistent.mp4", 20.0)
    check("no caption plan: one clip at 1.0", p == [(0.0, 20.0, 1.0, 0.0, 0.0)], p)

    json.dump({"punch": {"scale": 1.10, "windows": [[4.0, 6.0], [12.5, 14.0]],
                         "anchors": [[0.62, 0.41, 1.0], [0.5, 0.5]]}}, open(plan_p, "w", encoding="utf-8"))
    p = ch.footage_pieces(jd, "/nonexistent.mp4", 20.0)
    check("two windows: five pieces that tile the cut", len(p) == 5 and tiles(p, 20.0), p)
    check("the windows are the zoomed pieces", [x[2] for x in p] == [1.0, 1.1, 1.0, 1.1, 1.0], p)
    want = capcut_motion.anchor_transform(0.62, 0.41, 1.10, 1.0)
    check("an off-centre face shifts the zoom onto her", (p[1][3], p[1][4]) == want and want != (0.0, 0.0), (p[1], want))
    check("a centred face needs no shift", (p[3][3], p[3][4]) == (0.0, 0.0), p[3])

    json.dump({"punch": {"scale": 1.08, "windows": [[19.0, 25.0], [2.0, 5.0], [4.0, 6.0]],
                         "anchors": [[0.5, 0.5]] * 3}}, open(plan_p, "w", encoding="utf-8"))
    p = ch.footage_pieces(jd, "/nonexistent.mp4", 20.0)
    check("overlapping and past-the-end windows are clipped, never stacked", tiles(p, 20.0)
          and all(x[1] <= 20.0 for x in p), p)

    json.dump({"punch": {"scale": 1.0, "windows": [[4.0, 6.0]]}}, open(plan_p, "w", encoding="utf-8"))
    check("a 1.0 'punch' is no punch", ch.footage_pieces(jd, "/nonexistent.mp4", 20.0) == [(0.0, 20.0, 1.0, 0.0, 0.0)])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

sl = open(os.path.join(ROOT, "product", "separate_layers.sh"), encoding="utf-8").read()
check("separate_layers.sh asks the handoff for the punch-ins", "capcut_handoff.py" in sl and "--punch" in sl)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "the medium route keeps the plan's punch-ins, held on her face"))
sys.exit(1 if fails else 0)
