#!/usr/bin/env python3
"""Guard: an animation aimed at an element that does not exist REFUSES the render.

The bug this prevents: a word-by-word caption highlight targeted `.card[data-card-id="ka1"] ...` while the
DOM element carried `data-card-id="card-ka1"` (the prefix is added when the id is built from the short
name). The selector matched zero elements, so the highlight never ran. `hyperframes check` reports this --
correctly -- as a runtime console warning, and warnings pass unless --strict is given, so the composition
was declared clean, rendered fine, and came out silently missing its highlight. About a dozen seven-minute
renders went by before a human watching the output noticed.

A selector that resolves to nothing is never what anybody meant, so the gate promotes that one warning
class to a refusal. This test pins the parsing; the A/B against a real `hyperframes check` run lives in
the report notes (broken comp -> refused naming both selectors, corrected comp -> clean).

Run: python3 product/tests/test_dead_animation_targets.py
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))

spec = importlib.util.spec_from_file_location("rr", os.path.join(ROOT, "product", "reel_render.py"))
rr = importlib.util.module_from_spec(spec); spec.loader.exec_module(rr)
dead = rr._dead_animation_targets

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


# verbatim shape of what `hyperframes check` printed for the real composition
REAL = """Runtime
  ⚠ console_warning: GSAP target .card[data-card-id="ka1"] #card-ka1-w0 not found. https://gsap.com
    index.html [data-composition-id] t=0s
  ⚠ console_warning: GSAP target  not found. https://gsap.com
    index.html [data-composition-id] t=0s
  ⚠ console_warning: GSAP target .card[data-card-id="ka1"] #card-ka1-w1 not found. https://gsap.com
    index.html [data-composition-id] t=0s
  0 error(s), 6 warning(s), 0 info(s)
"""

CLEAN = """Lint
  ⚠ studio_missing_editable_id: <div data-start="0"> has no id.
Runtime
  ◇ 0 errors, 0 warnings
Layout
  ◇ 0 issues across 9 sample(s)
Contrast
  ◇ 10/10 text checks pass WCAG AA
◇  Check passed
"""


def main():
    print("dead animation targets\n")
    got = dead(REAL)
    check("the broken selectors are found", len(got) == 3, f"got {got}")
    check("the real selector is reported verbatim, so it can be searched for",
          '.card[data-card-id="ka1"] #card-ka1-w0' in got, str(got))
    check("both distinct word selectors are reported",
          '.card[data-card-id="ka1"] #card-ka1-w1' in got, str(got))
    check("an unnamed target is still reported rather than dropped", "(unnamed target)" in got, str(got))
    check("repeats across samples collapse to one entry each", len(got) == len(set(got)))

    # the whole point: no false positives, or every build stops
    check("a clean check reports nothing", dead(CLEAN) == [], str(dead(CLEAN)))
    check("empty output reports nothing", dead("") == [])
    check("a warning that merely mentions gsap is not treated as a dead target",
          dead("  ⚠ console_warning: gsap.min.js loaded from cdn https://gsap.com\n") == [])
    check("prose containing the words 'not found' is not a dead target",
          dead("  ⚠ asset_missing: file logo.png not found on disk\n") == [])

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
