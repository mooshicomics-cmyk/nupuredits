#!/usr/bin/env python3
"""Guards: a design can carry words she wrote that she doesn't say (the note slot), e.g. an aside on a note card.

  shown     __NOTE__ draws design.json "note", whatever line the design lands on; her spoken line still fills its own slots
  refused   a design that lists the note slot with no "note" is refused, so a card never comes out blank
  hand      PkThought (the pack's thought-bubble hand) is a pack face a design may use

Run: python3 product/tests/test_design_note.py
"""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import lookbook, stylepack  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


pack = next((p for p in ("Butter", "Editorial", "Playful") if p in stylepack.names()), stylepack.names()[0])
tmp = tempfile.mkdtemp(prefix="design-note-")
try:
    d = os.path.join(tmp, "note"); shutil.copytree(os.path.join(PRODUCT, "lookbook-designs", "starter"), d)
    hp = os.path.join(d, "index.html")
    h = open(hp, encoding="utf-8").read().replace("__LINE1__", "<b style=\"font-family:PkThought\">__NOTE__</b> __LINE1__", 1)
    open(hp, "w", encoding="utf-8").write(h)
    mp = os.path.join(d, "design.json"); meta = json.load(open(mp, encoding="utf-8"))
    meta["slots"] = list(meta.get("slots") or ["text"]) + ["note"]
    json.dump(meta, open(mp, "w", encoding="utf-8"))
    probs = lookbook.check_design(d, pack, render_check=False)
    check(any('"note"' in p for p in probs), f"refused: a note slot with no note should be refused, got {probs}")
    meta["note"] = "i charged $75 for 30 minutes"
    json.dump(meta, open(mp, "w", encoding="utf-8"))
    probs = lookbook.check_design(d, pack, render_check=False)
    check(probs == [], f"hand: a design with its note and PkThought should pass the rules, got {probs}")
    r = lookbook.draw_design(d, os.path.join(tmp, "out"), "one on one coaching", 3.0, pack, "c0")
    out = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    check("i charged $75 for 30 minutes" in out, "shown: the note isn't on the card")
    check("coaching" in out, "shown: her spoken line should still fill its slots")
    check("__NOTE__" not in out, "shown: the note slot was left unfilled")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_design_note: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_design_note: all {n} checks passed")
