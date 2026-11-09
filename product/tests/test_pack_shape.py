#!/usr/bin/env python3
"""Guards: the brand slots beyond fonts and colors (product/pack_shape.py) are bounded, and a pack that sets none of
them draws exactly what it drew before they existed.

  limits    corners 0 to 80 (999 = pill), card padding 24 to 120, three named shadows, a cubic-bezier only, label
            spacing 0 to 0.3em, at most 3 extra colors, an apart pair of two real roles
  defaults  the fallbacks ARE the builder's old literals (count-up card 28px corners, 34px 40px padding, its shadow;
            the label pill's 4px), and a shipped pack's count-up card still draws them with its own ease
  apart     two never-touch colors are caught on a card in either order, and only those two
  designs   her own designs get every pk- shape variable, a PkLabel / PkDetail face (the caption face when the pack
            has none) and window.pkEase
  ease      the cubic-bezier is a real curve: 0 at 0, 1 at 1, rising in between

Run: python3 product/tests/test_pack_shape.py
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import pack_shape as ps  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    # limits
    check("limits: a corner past 80 is refused, 999 or more is a pill", ps.check("radius_card", 81)[1] and ps.check("radius_card", 1200)[0] == 999)
    check("limits: card padding 24 to 120", ps.check("pad_card", 23)[1] and ps.check("pad_card", 121)[1] and ps.check("pad_card", 72)[0] == 72)
    check("limits: a shadow is named, never raw CSS", ps.check("shadow_card", "0 0 4px red")[1] and ps.check("shadow_card", "soft")[0] == "soft")
    check("limits: ease is a cubic-bezier only", ps.check("ease", "power2.out")[1] and ps.check("ease", "cubic-bezier(2, 0, 0, 1)")[1]
          and ps.check("ease", "cubic-bezier(0.16,1,0.3,1)")[0] == "cubic-bezier(0.16, 1, 0.3, 1)")
    check("limits: label spacing 0 to 0.3em", ps.check("label_tracking", 0.31)[1] and ps.check("label_tracking", 0.2)[0] == 0.2)
    block = {"extra_colors": {"a": "#111111", "b": "#222222", "c": "#333333", "d": "#444444", "bad": "red"}, "apart": "accent/accent"}
    check("limits: at most 3 extra colors, hexes only", ps.extra_colors(block) == {"a": "#111111", "b": "#222222", "c": "#333333"}, ps.extra_colors(block))
    check("limits: an apart pair needs two different roles", ps.apart(block) is None and ps.apart({"apart": ["muted", "accent"]}) == ("muted", "accent"))
    # defaults
    check("defaults: the builder's old literals", ps.shape({}) == ps.DEFAULTS and ps.DEFAULTS["radius_card"] == 28 and ps.DEFAULTS["pad_card"] == 40
          and round(ps.DEFAULTS["pad_card"] * 0.85) == 34 and ps.SHADOWS[ps.DEFAULTS["shadow_card"]] == "0 14px 44px rgba(0,0,0,.26)"
          and ps.DEFAULTS["radius_label"] == 4 and ps.ease({}) is None and ps.numbers({}) == "count-up")
    check("defaults: a bad value in a pack degrades to the default, never a broken card", ps.shape({"shape": {"radius_card": 500.5, "pad_card": 3}})["pad_card"] == 40)
    # apart
    pal = {"accent": "#BD1B1B", "muted": "#395848", "light": "#F8F6EE"}
    check("apart: caught in either order", ps.touches(pal, ("accent", "muted"), "#bd1b1b", "#395848") and ps.touches(pal, ("accent", "muted"), "#395848", "#BD1B1B"))
    check("apart: only those two", not ps.touches(pal, ("accent", "muted"), "#BD1B1B", "#F8F6EE") and not ps.touches(pal, None, "#BD1B1B", "#395848"))
    # designs: every pk- shape variable, in a shipped pack too
    v = "".join(ps.css_vars({}))
    check("designs: every shape variable is always set", all(f"--pk-{k}:" in v for k in ("radius-card", "radius-label", "radius-frame", "pad-card",
                                                                                       "shadow-card", "rule", "ease")), v)
    try:
        import lookbook
        tmp = tempfile.mkdtemp(prefix="pk-skin-")
        skin = lookbook._skin("Butter", tmp)
        check("designs: a shipped pack's skin carries the shape variables, PkLabel/PkDetail faces and pkEase",
              "--pk-radius-card:28px" in skin and "font-family:PkLabel" in skin and "font-family:PkDetail" in skin and "window.pkEase" in skin, skin[:200])
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        check("designs: the skin builds", False, repr(e))
    # a shipped pack's count-up card draws exactly the old card
    try:
        d = tempfile.mkdtemp(prefix="pk-counter-")
        r = subprocess.run([sys.executable, os.path.join(PRODUCT, "lookbook.py"), "draw", "counter", d, "--text", "I made 5000 dollars",
                            "--dur", "3", "--pack", "Butter"], capture_output=True, text=True, timeout=180)
        page = next((os.path.join(a, f) for a, _, fs in os.walk(d) for f in fs if f == "index.html"), None)
        html = open(page, encoding="utf-8").read() if page else ""
        check("defaults: Butter's count-up card is the card it always was",
              "border-radius:28px;padding:34px 40px;" in html and "box-shadow:0 14px 44px rgba(0,0,0,.26);" in html
              and 'ease:"back.out(1.6)"' in html and "pkEase" not in html, (r.stdout + r.stderr)[-300:])
        shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        check("defaults: Butter's count-up card draws", False, repr(e))
    # ease: a real curve
    node = shutil.which("node")
    if node:
        js = ps.ease_js("cubic-bezier(0.16, 1, 0.3, 1)") + "console.log(JSON.stringify([0,.25,.5,.75,1].map(pkEase)));"
        out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30).stdout.strip()
        try:
            ys = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", out)]
            check("ease: 0 at 0, 1 at 1, rising", len(ys) == 5 and ys[0] == 0 and ys[-1] == 1 and all(a <= b for a, b in zip(ys, ys[1:])), out)
        except ValueError:
            check("ease: runs", False, out)
    if fails:
        print(f"test_pack_shape: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_pack_shape: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
