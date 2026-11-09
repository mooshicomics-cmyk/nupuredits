#!/usr/bin/env python3
"""Guard: any spelling of a pack's case rule is read for what it means, and one that names no case never rewrites her
words (three buyers' Claudes hand-patched "as_is" / "asis" falling through to lowercase, 2026-10).

Run: python3 product/tests/test_case_spellings.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stylepack as sp

cases = {"as_is": "Gott sagt", "asis": "Gott sagt", "As Written": "Gott sagt", "as-said": "Gott sagt", "none": "Gott sagt",
         "something new": "Gott sagt", "UPPERCASE": "GOTT SAGT", "caps": "GOTT SAGT", "Lower": "gott sagt",
         "lowercase": "gott sagt", "Title Case": "Gott Sagt", None: "gott sagt"}
fails = [f"{r!r}: {sp.apply_case('Gott sagt', r)!r} != {want!r}" for r, want in cases.items()
         if sp.apply_case("Gott sagt", r) != want]
if sp.case_rule("as_is") != "as-written":
    fails.append(f"case_rule('as_is') = {sp.case_rule('as_is')!r}")
if sp.case_rule("lower", "caption", {"caption_case": "As_Is"}) != "as-written":
    fails.append("a plan's own spelling is not normalized")
if sp.case_rule("lowercase", lang="de") != "as-written":
    fails.append("lowercase on a German reel is not made safe")
print(f"{len(cases) + 3 - len(fails)}/{len(cases) + 3} passed")
for f in fails:
    print("  FAIL", f)
sys.exit(1 if fails else 0)
