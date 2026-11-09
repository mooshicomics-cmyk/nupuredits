#!/usr/bin/env python3
"""Guards: a look with a heading of its own over her words (a checklist) gets the heading of the reel it lands on.

  heading     "heading / item, item, item" draws THAT heading over those items (2026-10-21: a saved checklist said
              the heading from the reel it was made on over every new list)
  no heading  without one it keeps the heading it was saved with, and `place` says so
  ticked      each item ticks when she says it, matched to her real word timings even when the list is copy
  stays put   a page drawn that way is not seen as "timing moved" on the next look at it
  refine      Refine › Words shows "heading / her list", so the heading is editable there
  swap        a slot swapped to another look never carries the old look's copy along; the same look keeps it, and a
              hook's reframe still carries to another hook

Run: python3 product/tests/test_design_heading.py
"""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import lookbook, stylepack  # noqa: E402
import visual_editor as ve  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


TPL = """<!doctype html><html><head><style>#head{font-size:__PX_NOTE__px}</style></head><body>
<div id="root" data-composition-id="__COMP__" data-start="0" data-duration="__DUR__" data-width="1080" data-height="1920">
<div id="head">__NOTE__</div><div id="list" data-line="__TEXT__"></div></div>
<script>window.__timelines=window.__timelines||{};const D=__DUR__, SAID=__SAID__;
window.__timelines["__COMP__"]=gsap.timeline({paused:true});</script></body></html>"""
META = {"name": "Checklist", "kind": "Card", "slots": ["text", "note"], "note": "the old reel",
        "fit": {"note": {"role": "thought", "box_w": 820, "max_px": 104, "max_lines": 1}}, "hides_captions": True}

pack = next((p for p in ("Butter", "Editorial", "Playful") if p in stylepack.names()), stylepack.names()[0])
tmp = tempfile.mkdtemp(prefix="design-heading-")
real_dir = lookbook.design_dir
try:
    lookbook.design_dir = lambda p, i: os.path.join(tmp, "book", p, i)   # never her real lookbook
    src = lookbook.design_dir(pack, "my-list")
    os.makedirs(src)
    open(os.path.join(src, "index.html"), "w", encoding="utf-8").write(TPL)
    json.dump(META, open(os.path.join(src, "design.json"), "w", encoding="utf-8"))

    check(lookbook.has_heading(META), "heading: a text + note design (not a line follower) has a heading")
    check(not lookbook.has_heading({"slots": ["note"], "note": "x", "hides_captions": True}), "heading: a note-only design has none")
    v = lookbook._fill_values("laundry day / wash, dry, and fold", META)
    check(v["note"] == "laundry day" and v["text"] == "wash, dry, and fold", f"heading: split wrong {v['note']!r} / {v['text']!r}")
    check(lookbook._fill_values("wash, dry, and fold", META)["note"] == "the old reel", "no heading: the saved heading stays")

    said = "first I wash it, then I dry it, and then I fold it".split()
    words = [{"w": w, "t": round(0.2 + k * 0.3, 2), "e": round(0.45 + k * 0.3, 2)} for k, w in enumerate(said)]
    r = lookbook.draw_design(src, os.path.join(tmp, "out"), "laundry day / wash, dry, fold", 3.8, pack, "c0", words=words)
    out = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    check('<div id="head">laundry day</div>' in out, "heading: this reel's heading is not on the card")
    check('data-line="wash, dry, fold"' in out, "heading: the list is not the items she gave")
    check("the old reel" not in out, "heading: the old reel's heading is still on the card")
    t = {w["w"]: w["t"] for w in words}
    rec = json.load(open(os.path.join(r["dir"], "look.json"), encoding="utf-8"))
    check(rec["said"] == [t["wash"], t["dry"], t["fold"]], f"ticked: items not timed to her words {rec['said']}")
    look = {"id": "my-list", "design": True, "name": "Checklist", "about": "", "kind": "Card", "home": pack}
    check(not ve._timing_moved(r["dir"], look, "laundry day / wash, dry, fold", 3.8, pack, words), "stays put: redrawn for nothing")
    check(lookbook.words_to_edit(look, pack, "wash, dry, fold", "the old reel") == "the old reel / wash, dry, fold",
          "refine: Words should show the heading in front of her list")
    check(lookbook.words_to_edit(look, pack, "laundry day / wash, dry, fold", "laundry day") == "laundry day / wash, dry, fold",
          "refine: a heading already there is not doubled")
    builder = lookbook.find("takeover", pack)
    check(lookbook.words_to_edit(builder, pack, "her words", "x") == "her words", "refine: a builder look's words are unchanged")
finally:
    lookbook.design_dir = real_dir
    shutil.rmtree(tmp, ignore_errors=True)

# swap: the copy a slot keeps (visual_editor._kept_copy)
real = (ve._entry, lookbook.find)
hooks = {"hook", "eyebrow-headline"}
try:
    lookbook.find = lambda i, p=None, **k: {"id": i, "layer": "hook" if i in hooks else "design"}
    ve._entry = lambda jd, key: ({"look": "my-list", "copy": "the setup / wash, dry, fold"}, "adds")
    check(ve._kept_copy("jd", "add-w3", "my-list", {"id": "my-list"}, pack) == "the setup / wash, dry, fold", "swap: the same look keeps its copy")
    check(ve._kept_copy("jd", "add-w3", "my-line", {"id": "my-line"}, pack) is None, "swap: another look took the old copy along")
    ve._entry = lambda jd, key: ({"look": "hook", "copy": "a reframe"}, "adds")
    check(ve._kept_copy("jd", "add-w3", "eyebrow-headline", {"id": "eyebrow-headline", "layer": "hook"}, pack) == "a reframe",
          "swap: a hook's reframe should carry to another hook")
    check(ve._kept_copy("jd", "cap-w3", "hook", {"layer": "hook"}, pack) is None, "swap: only an added look keeps copy")
finally:
    ve._entry, lookbook.find = real

if fails:
    print("test_design_heading: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_design_heading: all {n} checks passed")
