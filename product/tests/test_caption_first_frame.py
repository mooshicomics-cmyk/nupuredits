#!/usr/bin/env python3
"""Guard: a caption group shown from its layer's very first frame renders (2026-10-18: "I'll send you the" was
missing from her export). A hide and a show both at 0.00 is a tie the preview and the renderer break differently, so
the builder writes only the show for a group that starts at 0, and never a 0.00 hide/show pair anywhere.

Run: python3 product/tests/test_caption_first_frame.py
"""
import ast, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "build-reel-type.py")
fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


tree = ast.parse(open(SRC, encoding="utf-8").read())
fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "_show_at")
ns = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), SRC, "exec"), ns)
show = ns["_show_at"]
check(show("#ph0", 0.0) == 'tl.set("#ph0",{autoAlpha:1},0);', f"start 0: only the show, got {show('#ph0', 0.0)}")
check(show("#ph1", 0.57) == 'tl.set("#ph1",{autoAlpha:0},0);tl.set("#ph1",{autoAlpha:1},0.57);', "later start: hidden, then shown")
src = open(SRC, encoding="utf-8").read()
check(not re.search(r"autoAlpha:0\}\},0\);tl\.set\(\"#\{(wid|gid)\}\",\{\{autoAlpha:1\}\}", src),
      "no caption writer builds the hide-at-0 + show pair by hand any more (use _show_at)")

if fails:
    print(f"FAIL {len(fails)}/{n}"); [print(" -", f) for f in fails]; sys.exit(1)
print(f"ok {n} checks")
