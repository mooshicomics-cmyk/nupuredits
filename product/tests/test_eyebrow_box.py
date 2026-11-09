#!/usr/bin/env python3
"""Guards: a split hook's quiet line (eyebrow / subhead) keeps its own size, sits in a box as wide as the big line,
and stays on ONE line when its words fit that width.

The wrap it guards: with her face zones the hook sits smaller above your head, and every pack forced a short eyebrow
("this is a sample") onto two lines just to draw it bigger. Seen in 5 of 6 packs before the fix.

Run: python3 product/tests/test_eyebrow_box.py
"""
import json, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lookbook, stylepack  # noqa: E402

fails, n = [], 0
ZONES = {"subject": {"head_top": 560, "chin_bottom": 1040, "left": 300, "right": 780}}   # a close-up, like hers
tmp = tempfile.mkdtemp(prefix="eyebrow-")
try:
    for pk in stylepack.names():
        for zones in (None, ZONES):
            n += 1
            r = lookbook.draw("eyebrow-headline", os.path.join(tmp, f"{pk}-{bool(zones)}"),
                              "this is a sample for the claude reels editing", 3.14, pk, zones=zones)
            html = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
            q = re.search(r'<div class="hkquiet"[^>]*font-size:(\d+)px;width:(\d+)px[^>]*>(.*?)</div>', html)
            h = re.search(r'<div class="hkhead"[^>]*font-size:(\d+)px', html)
            where = f"{pk} ({'face zones' if zones else 'no zones'})"
            if not q or not h:
                fails.append(f"{where}: no eyebrow box"); continue
            if "<br>" in q.group(3):
                fails.append(f"{where}: a short eyebrow wrapped to two lines")
            if int(q.group(1)) >= int(h.group(1)):
                fails.append(f"{where}: eyebrow {q.group(1)}px isn't quieter than the headline {h.group(1)}px")
            if not 100 <= int(q.group(2)) <= 1080:
                fails.append(f"{where}: eyebrow box {q.group(2)}px isn't the big line's width")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_eyebrow_box: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_eyebrow_box: all {n} checks passed")
