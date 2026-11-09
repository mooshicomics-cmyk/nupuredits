#!/usr/bin/env python3
"""Guard: her moved copy of a section look follows later fixes to its original (2026-10-19: her GIF library
kept the old stop-and-start glide because her copy was made before the fix).

  stale     a fix to the original (newer page) reaches her copy, and her move is put back on it
  current   an unchanged original leaves her copy alone (no rewrite)

Run: python3 product/tests/test_moved_copy_follows.py
"""
import os, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


tmp = tempfile.mkdtemp(prefix="moved-copy-")
try:
    PAGE = '<!doctype html><html><head></head><body><div id="root" data-composition-id="be" data-duration="2" data-width="1080" data-height="1920">{}</div></body></html>'
    os.makedirs(os.path.join(tmp, "hf-graphics", "sec"))
    open(os.path.join(tmp, "hf-graphics", "sec", "index.html"), "w", encoding="utf-8").write(PAGE.format("OLD"))
    src, rel = os.path.join(tmp, "hf-graphics", "sec"), "hf-graphics/_looks/sec/_original"
    shutil.copytree(src, os.path.join(tmp, rel)); ve._stamp_copy(src, os.path.join(tmp, rel))
    ve._apply_nudge(tmp, rel, [0, 40])
    moved = open(os.path.join(tmp, rel, "index.html"), encoding="utf-8").read()
    check(not ve._refresh_moved_copy(tmp, "hf-graphics/sec", rel, [0, 40]), "current: an unchanged original leaves her copy alone")
    check(open(os.path.join(tmp, rel, "index.html"), encoding="utf-8").read() == moved, "current: her copy is byte-for-byte the same")
    time.sleep(1.1)
    open(os.path.join(src, "index.html"), "w", encoding="utf-8").write(PAGE.format("FIXED"))
    check(ve._refresh_moved_copy(tmp, "hf-graphics/sec", rel, [0, 40]), "stale: a fixed original refreshes her copy")
    now = open(os.path.join(tmp, rel, "index.html"), encoding="utf-8").read()
    check("FIXED" in now and "OLD" not in now, "stale: her copy carries the fix")
    check(now.count("40") >= 1 and moved.count("40") >= 1 and (moved.split("FIXED")[0] if "FIXED" in moved else moved) != "", "stale: her move is back on it")
    check(not ve._refresh_moved_copy(tmp, "hf-graphics/sec", rel, [0, 40]), "stale: refreshed once, then left alone")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"FAIL {len(fails)}/{n}"); [print(" -", f) for f in fails]; sys.exit(1)
print(f"ok {n} checks")
