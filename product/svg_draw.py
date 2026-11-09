#!/usr/bin/env python3
"""svg_draw.py: draw a line on (an arrow, an underline, a circle) without stray dots, and a check that refuses
any line set up the way that leaves them.

THE BUG. The usual draw-on is `stroke-dasharray = L; stroke-dashoffset = L`, then tween the offset to 0. With
ROUND line caps (the friendly hand-drawn look every arrow here uses), that start state is not empty: the dash
pattern ends exactly at the path's first point and the next dash begins exactly at its last point, and each of
those zero-length dashes is still painted as a round cap. So before the line draws, a DOT sits at each end. On
an arrowhead (one barb, the tip, the other barb) that is two dots at the barb tips, on screen until the head
draws. It looked like a mistake every time, on every reel.

THE FIX. A gap at least a cap wider than the path, and a starting offset past the dash's end, so every point of
the path sits inside the gap before it draws:
    stroke-dasharray = "L  2L+W",  stroke-dashoffset = L + W      (W = stroke width)
Tween the offset to 0 exactly as before. `draw_on_attrs(L, W)` returns those two attributes.

THE CHECK. `problems(html)` finds every <path>/<line>/<polyline>/<polygon>/<circle>/<ellipse>/<rect> with a round
(or square) cap and a dash set up the old way (one dash value, offset not past it by a cap), and reel_render.py
and reel_gate.py refuse to render a composition that has one. `message()` says which element and the fix.

  python3 product/svg_draw.py <composition dir or index.html>     (report)
"""
import os, re, sys

for stream in (sys.stdout, sys.stderr):   # ✓ and ⛔ need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

__all__ = ["draw_on_attrs", "problems", "check_comp", "message"]


def draw_on_attrs(length, stroke_width):
    """The two SVG attributes for a dot-free draw-on of a path `length` long, drawn `stroke_width` wide.
    Animate stroke-dashoffset to 0 to draw it."""
    L, W = float(length), float(stroke_width)
    return f'stroke-dasharray="{L:.1f} {2 * L + W:.1f}" stroke-dashoffset="{L + W:.1f}"'


_TAG = re.compile(r"<(path|line|polyline|polygon|circle|ellipse|rect)\b([^>]*)>", re.I | re.S)


def _attr(attrs, name):
    m = re.search(r'\b' + re.escape(name) + r'\s*=\s*"([^"]*)"', attrs, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'style\s*=\s*"[^"]*\b' + re.escape(name) + r'\s*:\s*([^;"]+)', attrs, re.I)
    return m.group(1).strip() if m else None


def _nums(v):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", v or "")]


def problems(html):
    """[(element id or tag, why)] for every stroke set up to leave round-cap dots before it draws."""
    out = []
    for m in _TAG.finditer(html):
        tag, attrs = m.group(1).lower(), m.group(2)
        cap = (_attr(attrs, "stroke-linecap") or "butt").lower()
        dash = _nums(_attr(attrs, "stroke-dasharray"))
        if cap == "butt" or not dash:
            continue
        off = _nums(_attr(attrs, "stroke-dashoffset"))
        w = (_nums(_attr(attrs, "stroke-width")) or [1.0])[0]
        dash_len = dash[0]
        gap = dash[1] if len(dash) > 1 else dash[0]
        start = off[0] if off else 0.0
        if start <= 0:
            continue                                   # drawn from the start: not a draw-on, nothing hidden
        # hidden-at-start needs the WHOLE path inside the gap: offset past the dash's end by a cap, and a gap
        # longer than the path plus that cap. dash_len stands in for the path length (the draw-on convention).
        if start < dash_len * 0.9:
            continue                                   # a moving dotted/dashed pattern, not a hidden draw-on
        if start < dash_len + w * 0.5 or gap < dash_len + w:
            ident = _attr(attrs, "id") or tag
            out.append((ident, f"dasharray {' '.join(f'{x:g}' for x in dash)} with dashoffset {start:g} and "
                               f"{cap} caps paints a dot at each end before it draws"))
    return out


def check_comp(comp_dir_or_html):
    p = comp_dir_or_html
    if os.path.isdir(p):
        p = os.path.join(p, "index.html")
    try:
        with open(p, encoding="utf-8") as fh:
            return problems(fh.read())
    except OSError:
        return []


def message(items):
    lines = [f"\n  ⛔ {len(items)} drawn line(s) would show stray dots before they draw (round caps on a dash "
             f"draw-on) — REFUSING to render:"]
    for ident, why in items[:8]:
        lines.append(f"       #{ident}: {why}")
    lines.append("     Fix: build the dash with product/svg_draw.draw_on_attrs(length, stroke_width) "
                 "(gap 2L+W, start offset L+W), then tween stroke-dashoffset to 0 as before.")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    found = check_comp(sys.argv[1])
    print(message(found) if found else "  ✓ no drawn line leaves dots before it draws")
    sys.exit(1 if found else 0)
