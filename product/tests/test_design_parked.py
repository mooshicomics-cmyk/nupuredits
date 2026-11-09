#!/usr/bin/env python3
"""Guard: a design never leaves a piece parked in the top-left corner (you: "there's a random circle in the left corner").

  parked    a small piece placed at left:0;top:0 that no script ever moves or hides is refused by check_design
  moved     the same piece animated by the timeline ("#ring", or a numbered set built as "#b"+k) passes
  hidden    a piece that starts hidden (opacity:0) passes, and so does a full-frame ground

Run: python3 product/tests/test_design_parked.py
"""
import os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import lookbook, stylepack  # noqa: E402

fails, n = [], 0
pack = next((p for p in ("Butter", "Editorial", "Playful") if p in stylepack.names()), stylepack.names()[0])
tmp = tempfile.mkdtemp(prefix="design-parked-")


def probs_with(markup, script=""):
    d = os.path.join(tmp, str(len(os.listdir(tmp))))
    shutil.copytree(os.path.join(PRODUCT, "lookbook-designs", "starter"), d)
    hp = os.path.join(d, "index.html")
    h = open(hp, encoding="utf-8").read()
    h = h.replace("</body>", markup + "</body>", 1)
    h = h.replace('window.__timelines["__COMP__"]', script + 'window.__timelines["__COMP__"]', 1)
    open(hp, "w", encoding="utf-8").write(h)
    return [p for p in lookbook.check_design(d, pack, render_check=False) if "top-left" in p]


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


try:
    ring = '<div id="ring" style="position:absolute;left:0;top:0;width:70px;height:70px"></div>'
    check(probs_with(ring), "parked: an unanimated ring at 0,0 should be refused")
    check(not probs_with(ring, 'tl.fromTo("#ring",{autoAlpha:0},{autoAlpha:1},0.5);'), "moved: an animated ring should pass")
    bits = '<i id="b0" style="position:absolute;left:0;top:0;width:34px"></i><i id="b1" style="position:absolute;left:0;top:0;width:34px"></i>'
    check(not probs_with(bits, 'for(let k=0;k<2;k++){tl.to("#b"+k,{x:9},0.2);}'), "moved: a numbered set built as \"#b\"+k should pass")
    check(not probs_with('<div id="g" style="position:absolute;left:0;top:0;opacity:0;width:40px"></div>'), "hidden: a piece that starts hidden should pass")
    check(not probs_with('<div id="bg" style="position:absolute;left:0;top:0;width:1080px;height:1920px"></div>'), "hidden: a full-frame ground should pass")
    # a real brand's colour named in design.json "brand_colors" passes; the same colour unnamed is still flagged
    import json as _json
    d = os.path.join(tmp, "brand"); shutil.copytree(os.path.join(PRODUCT, "lookbook-designs", "starter"), d)
    hp = os.path.join(d, "index.html"); _h = open(hp, encoding="utf-8").read()
    open(hp, "w", encoding="utf-8").write(_h.replace("#bar{", "#bar{color:rgb(218,118,86);", 1))
    pal = lambda: [p for p in lookbook.check_design(d, pack, render_check=False) if "Colors come from the pack" in p]
    check(pal(), "brand: an unnamed off-pack colour is flagged")
    mp = os.path.join(d, "design.json"); m = _json.load(open(mp, encoding="utf-8")); m["brand_colors"] = {"Claude": "rgb(218, 118, 86)"}
    _json.dump(m, open(mp, "w", encoding="utf-8"))
    check(not pal(), "brand: a colour named in brand_colors passes")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"FAIL {len(fails)}/{n}"); [print(" -", f) for f in fails]; sys.exit(1)
print(f"ok {n} checks")
