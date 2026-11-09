#!/usr/bin/env python3
"""Guard: a look she kept for one reel can join her lookbook for every reel (teach my style's "keep these looks").

  one-offs    one_off_looks lists her looks kept for that reel only, never sandbox sketches or other reels' looks
  keep        keep_everywhere drops only_reel, so the look shows on every reel; a second call changes nothing

Run: python3 product/tests/test_lookbook_keep_everywhere.py
"""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lookbook  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


tmp = tempfile.mkdtemp(prefix="keep-everywhere-")
old = lookbook.ROOT
try:
    lookbook.ROOT = tmp
    os.makedirs(os.path.join(tmp, "_local", "lookbooks"))
    book = {"looks": [{"id": "my-wall", "name": "Wall", "design": True, "only_reel": "reel-a"},
                      {"id": "my-sketch", "name": "Sketch", "design": True, "only_reel": "reel-a", "sample": "abc"},
                      {"id": "my-other", "name": "Other", "design": True, "only_reel": "reel-b"},
                      {"id": "my-every", "name": "Every", "design": True}]}
    json.dump(book, open(os.path.join(tmp, "_local", "lookbooks", "Butter.json"), "w", encoding="utf-8"))
    ids = [l["id"] for l in lookbook.one_off_looks("Butter", "reel-a")]
    check(ids == ["my-wall"], f"one-offs: only reel-a's kept look, got {ids}")
    check(lookbook.keep_everywhere("Butter", "my-wall"), "keep: it changed")
    check("only_reel" not in lookbook.book_entry("Butter", "my-wall"), "keep: only_reel is gone")
    check(not lookbook.keep_everywhere("Butter", "my-wall"), "keep: a second call changes nothing")
    check(not lookbook.keep_everywhere("Butter", "my-every"), "keep: a look already on every reel is left alone")
    check(lookbook.book_entry("Butter", "my-other").get("only_reel") == "reel-b", "keep: other reels' looks untouched")
finally:
    lookbook.ROOT = old
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"FAIL {len(fails)}/{n}"); [print(" -", f) for f in fails]; sys.exit(1)
print(f"ok {n} checks")
