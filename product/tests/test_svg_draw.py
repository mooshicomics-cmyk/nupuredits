#!/usr/bin/env python3
"""Regression guard: a line drawn on with round caps never shows dots before it draws.

The bug this locks down: an arrow drawn on the usual way (stroke-dasharray = L, stroke-dashoffset = L, tween
to 0) with round caps paints a dot at each end of the path BEFORE it draws: the two dots at an arrowhead's barb
tips, seen on reel after reel. product/svg_draw.py builds the dash so nothing shows (draw_on_attrs), and
reel_render.py / reel_gate.py refuse a composition set up the old way.

What must hold: the old setup is caught (path, polyline, circle; attribute or style form), draw_on_attrs passes,
a plain dashed or moving dotted line is left alone, butt caps are left alone, and both refusals are wired in.

Run: python3 product/tests/test_svg_draw.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import svg_draw as S

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


svg = lambda inner: f'<svg width="1080" height="1920">{inner}</svg>'
old_head = svg('<path id="ah" d="M1,1 L5,5 L9,1" stroke-width="6" stroke-linecap="round" '
               'stroke-dasharray="52.0" stroke-dashoffset="52.0"/>')
check("old arrowhead setup is caught", [i for i, _ in S.problems(old_head)] == ["ah"])
check("style-attribute form is caught", len(S.problems(svg(
    '<polyline id="u" points="0,0 9,9" style="stroke-width:5;stroke-linecap:round;stroke-dasharray:80;'
    'stroke-dashoffset:80"/>'))) == 1)
check("circle draw-on is caught", len(S.problems(svg(
    '<circle id="c" r="40" stroke-width="4" stroke-linecap="round" stroke-dasharray="251" stroke-dashoffset="251"/>'))) == 1)
check("draw_on_attrs passes", S.problems(svg(
    f'<path id="ap" d="M0,0 L9,9" stroke-width="6" stroke-linecap="round" {S.draw_on_attrs(120, 6)}/>')) == [])
check("a plain dashed line is left alone", S.problems(svg(
    '<path d="M0,0 L99,0" stroke-width="3" stroke-linecap="round" stroke-dasharray="6 8"/>')) == [])
check("a moving dotted pattern is left alone", S.problems(svg(
    '<path d="M0,0 L99,0" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 6" stroke-dashoffset="2"/>')) == [])
check("butt caps are left alone", S.problems(svg(
    '<path d="M0,0 L99,0" stroke-width="6" stroke-dasharray="99" stroke-dashoffset="99"/>')) == [])
check("message names the element and the fix", "#ah" in S.message(S.problems(old_head))
      and "draw_on_attrs" in S.message(S.problems(old_head)))
for f in ("reel_render.py", "reel_gate.py"):
    src = open(os.path.join(PRODUCT, f), encoding="utf-8").read()
    check(f"{f} refuses on it", "svg_draw.check_comp(" in src and "svg_draw.message(" in src)

print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILED'}")
sys.exit(1 if fails else 0)
