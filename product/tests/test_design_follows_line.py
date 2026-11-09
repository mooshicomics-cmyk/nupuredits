#!/usr/bin/env python3
"""Guards: a look she saved whose words were her spoken line follows the line on every new reel, like a caption style.

  follows   a design saved with her spoken line as its note (line_text matches) is marked note_follows_line
  aside     a note she typed that she doesn't say (an aside) is never marked: it stays the same on every line
  new line  drawn on a new reel, a following design shows THAT reel's line ("first / second" at its first pause mark),
            never the reel it was made on (2026-10-20: her comment CTA kept saying the old reel's keyword)
  timed     her word timings fill __SAID__, and a hard-coded SAID array from the old reel is replaced too
  no slot   a following design needs no fixed note to pass the rules

Run: python3 product/tests/test_design_follows_line.py
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
tmp = tempfile.mkdtemp(prefix="design-follows-")
real_dir = lookbook.design_dir
try:
    lookbook.design_dir = lambda p, i: os.path.join(tmp, "book", p, i)   # never her real lookbook
    d = os.path.join(tmp, "cta"); shutil.copytree(os.path.join(PRODUCT, "lookbook-designs", "starter"), d)
    hp = os.path.join(d, "index.html")
    h = open(hp, encoding="utf-8").read().replace("__LINE1__", "<span id=\"src\">__NOTE__</span> __LINE1__", 1)
    h = h.replace("</script>", "\nconst SAID = [0.10, 0.44, 1.06];\nconst SAID2 = __SAID__;\n</script>", 1)
    open(hp, "w", encoding="utf-8").write(h)
    mp = os.path.join(d, "design.json"); meta = json.load(open(mp, encoding="utf-8"))
    meta["slots"] = list(meta.get("slots") or ["text"]) + ["note"]
    meta["note"] = "comment ready / and i will DM you exactly what i built"
    json.dump(meta, open(mp, "w", encoding="utf-8"))

    check(lookbook.note_is_spoken(meta["note"], "Comment Ready and I will DM you exactly what I built"), "follows: her spoken line should match")
    check(not lookbook.note_is_spoken("I can't believe this is real.", "Oh my god, oh my god, oh my"), "aside: a typed line should not match")

    os.makedirs(os.path.join(tmp, "book", pack), exist_ok=True)
    dst = lookbook.design_dir(pack, "my-cta"); shutil.copytree(d, dst)
    check(lookbook.follow_line(pack, "my-cta", "Comment Ready and I will DM you exactly what I built"), "follows: should be marked")
    m2 = json.load(open(os.path.join(dst, "design.json"), encoding="utf-8"))
    check(m2.get("note_follows_line") is True, "follows: design.json not marked")
    m2.pop("note", None); json.dump(m2, open(os.path.join(dst, "design.json"), "w", encoding="utf-8"))
    check(lookbook.check_design(dst, pack, render_check=False) == [], "no slot: a following design should need no fixed note")
    m2["note"] = meta["note"]; json.dump(m2, open(os.path.join(dst, "design.json"), "w", encoding="utf-8"))

    aside = os.path.join(tmp, "book", pack, "my-aside"); shutil.copytree(d, aside)
    am = json.load(open(os.path.join(aside, "design.json"), encoding="utf-8")); am["note"] = "I can't believe this is real."
    json.dump(am, open(os.path.join(aside, "design.json"), "w", encoding="utf-8"))
    check(not lookbook.follow_line(pack, "my-aside", "Oh my god, oh my god, oh my"), "aside: an aside should never be marked")

    words = [{"w": w, "t": t, "e": t + 0.2} for w, t in zip("Comment engine, I'll send it right to you.".split(),
                                                             (0.24, 0.74, 1.74, 1.94, 2.16, 2.24, 2.44, 2.58))]
    r = lookbook.draw_design(dst, os.path.join(tmp, "out"), "Comment engine, I'll send it right to you.", 3.0, pack, "c0", words=words)
    out = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    check("Comment engine / I&#x27;ll send it right to you." in out, "new line: should show this reel's line, split at its pause")
    check("comment ready" not in out, "new line: the old reel's words are still on the card")
    check("const SAID = [0.24, 0.74, 1.74" in out, "timed: the old reel's SAID array was not replaced")
    check("const SAID2 = [0.24" in out and "__SAID__" not in out, "timed: __SAID__ not filled with her timings")
finally:
    lookbook.design_dir = real_dir
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_design_follows_line: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_design_follows_line: all {n} checks passed")
