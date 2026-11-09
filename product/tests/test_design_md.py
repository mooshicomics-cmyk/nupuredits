#!/usr/bin/env python3
"""Guards: a DESIGN.md becomes her pack exactly the way product/DESIGN-MD-SPEC.md says (product/design_md.py).

  reading  the spec's own format, inline maps, quoted hexes and comments; a look's name never swallows its body
  web      the common web shape maps onto the spec (heading/body fonts, primary/secondary colors), web-only fields
           are named once as dropped, and only what's truly missing (mood, an accent font) is asked
  checks   a shipped pack's name, a bad hex, an exact palette whose words won't read, an unknown field and an out-of-
           range value all stop the write with the reason; hooks and cards keep separate case settings
  website  a real web design system (display-xl tiers, eyebrow/mono fonts, colors named by what they are, an rgba,
           a never-touch rule in prose, px corners, a card's padding, a card lift, a cubic-bezier) reads cleanly
  framework the Brand Kit's shape (label/detail fonts, extra + apart colors, rounded, spacing, elevation, motion)
           is read in full, each slot inside its limits, and lands on the pack
Nothing here writes a pack (the write path is the engine's own pack_write, guarded by its own tests).

Run: python3 product/tests/test_design_md.py
"""
import os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import design_md as dm  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def design(tmp, name, text):
    d = os.path.join(tmp, name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "DESIGN.md"), "w", encoding="utf-8").write(text)
    return d


NATIVE = """---
name: My Pack   # her name for it
mood: warm calm clean
base: Butter
fonts:
  headline: { family: "Font A" }
  caption:  { family: Font B }
  accent:   { family: Font C }
colors:
  primary: "#C2527A"
  secondary: "#F4C2C2"
type:
  hook_case: lower
  card_case: upper
  card_tracking: -0.03
hook_color: white
card: { ground: dark, ink: light, rule: true }
---

## Look: Receipt card
kind: Card
slots: number, label

## Look: Big word
kind: Full screen
"""

WEB = """---
name: Acme
description: calm and modern
colors:
  primary: "#1D4ED8"
  secondary: "#F59E0B"
  background: "#111111"
  border: "#E5E7EB"
typography:
  heading: { fontFamily: "Font A, sans-serif" }
  body: { fontFamily: Font B }
rounded: 8px
components:
  button: primary
---
"""


SITE = """---
name: Acme Home
description: "Warm and calm. One path."
colors:
  accent-red: "#bd1b1b"
  sage-forest: "#395848"
  brass: "#9c7c4d"
  canvas-white: "#ffffff"
  warm-cream: "#f8f6ee"
  warm-wheat: "#eee3ba"
  text-ink: "#1e1e1e"
  text-walnut: "#4d3b2d"
  text-muted: "rgba(30,30,30,0.66)"
  hairline-black: "#000000"
typography:
  display-xl:
    fontFamily: "Font A, Georgia, serif"
    fontSize: "clamp(3.75rem, 9vw, 6.5rem)"
  display-sm:
    fontFamily: "Font A, Georgia, serif"
  eyebrow:
    fontFamily: "Font D, sans-serif"
    fontWeight: 700
    letterSpacing: "0.2em"
  body:
    fontFamily: "Font B, sans-serif"
  body-sm:
    fontFamily: "Font B, sans-serif"
  mono:
    fontFamily: "Font E, monospace"
  hand:
    fontFamily: "Font C, cursive"
rounded:
  pill: "100px"
  card: "20px"
  field: "50px"
spacing:
  section-y: "112px"
components:
  button-primary:
    backgroundColor: "{colors.accent-red}"
  card:
    padding: "48px 40px"
---

## Colors

**The No-Pairing Rule.** Red and green never touch. A red element never sits on cream bands either way.

## Elevation & Depth

- **Card lift** (`box-shadow: 0 18px 44px rgba(30,30,30,0.09)`): a soft diffuse shadow.
Structure is drawn with the 1px black hairline. Arrivals use `cubic-bezier(0.16, 1, 0.3, 1)`; the numbers count up once.
"""

FRAME = NATIVE.replace('''colors:
  primary: "#C2527A"
  secondary: "#F4C2C2"''', '''description: "One-line north star."
colors:
  light: "#F8F6EE"
  dark: "#1E1E1E"
  muted: "#395848"
  accent: "#BD1B1B"
  pop2: "#EEE3BA"
  extra: { brass: "#9C7C4D" }
  apart: "accent/muted"''').replace('''  accent:   { family: Font C }''', '''  accent:   { family: Font C }
  label:    { family: Font D }
  detail:   { family: Font E }''').replace('''  card_tracking: -0.03''', '''  card_tracking: -0.03
  caption_case: lower
  label_case: upper
  label_tracking: 0.2
  emphasis: italic
  emphasis_words: 2-3
  emphasis_punctuation: true''').replace('''card: { ground: dark, ink: light, rule: true }''', '''card: { ground: light, ink: dark, rule: true }
rounded: { card: 40, label: 999, frame: 0 }
spacing: { card_pad: 72 }
elevation: { card: lift, rule: hairline }
motion:
  ease: "cubic-bezier(0.16, 1, 0.3, 1)"
  hook: soft-blur-in
  takeover: rise
  pace: unhurried
  sfx: lighter
  opener_zoom: false
  numbers: count-up''')


def main():
    tmp = tempfile.mkdtemp(prefix="design-md-")
    real_font, real_langs = dm._font, dm.her_languages
    dm._font = lambda folder, fam: ("/fonts/" + fam + ".ttf", "installed")     # every font "installed"
    dm.her_languages = lambda: []
    try:
        p = dm.plan(design(tmp, "native", NATIVE))
        check("reading: name without its comment", p["name"] == "My Pack", p["name"])
        check("reading: fonts by name, inline maps, quotes", [x["family"] for x in p["fonts"].values()] == ["Font A", "Font B", "Font C"], p["fonts"])
        check("reading: a look's name is only its name", p["looks"] == ["Receipt card", "Big word"], p["looks"])
        check("checks: a clean native design has nothing to fix", not (p["problems"] or p["missing"] or p["unknown"]), p)
        check("hooks and cards keep separate case", "elements.headline.case=lower" in p["sets"] and "card.headline_case=upper" in p["sets"], p["sets"])
        check("card tracking in em, hook color white", "card.headline_tracking=-0.03em" in p["sets"] and "welldone.hook_color=#ffffff" in p["sets"], p["sets"])
        w = dm.plan(design(tmp, "web", WEB))
        check("web: heading and body fonts map", w["fonts"].get("headline", {}).get("family") == "Font A" and w["fonts"].get("caption", {}).get("family") == "Font B", w["fonts"])
        check("web: seeds and a dark ground from the background", w["seeds"]["primary"] == "#1D4ED8" and w["seeds"]["dark_ground"] is True, w["seeds"])
        check("web: web-only fields named once as dropped", {"rounded", "components", "border"} <= set(w["dropped"]), w["dropped"])
        check("web: only mood and an accent font are asked", len(w["missing"]) == 2 and not w["problems"] and not w["unknown"], w)
        bad = dm.plan(design(tmp, "bad", NATIVE.replace("name: My Pack", "name: Butter").replace('"#C2527A"', '"pink"')
                             .replace("hook_case: lower", "hook_case: shouty").replace("base: Butter", "base: Butter\nsparkle: yes")))
        txt = " ".join(bad["problems"])
        check("checks: a shipped pack's name is refused", "one of the engine's own packs" in txt, txt)
        check("checks: a color that isn't a hex is refused", "primary #hex" in txt, txt)
        check("checks: an unknown case value is refused", "hook_case" in txt, txt)
        check("checks: an unknown field is asked about, never dropped", bad["unknown"] == ["sparkle"], bad["unknown"])
        pal = dm.plan(design(tmp, "pal", NATIVE.replace('''  primary: "#C2527A"
  secondary: "#F4C2C2"''', '''  light: "#FFFFFF"
  dark: "#EEEEEE"
  muted: "#999999"
  accent: "#FF0000"
  pop2: "#00FF00"''')))
        check("checks: an exact palette whose words won't read is refused, with the nearest that reads",
              any("4.5:1" in x and "nearest" in x for x in pal["problems"]), pal["problems"])
        ex = dm.plan(design(tmp, "exact", NATIVE), exact=True)
        check("exact colors: her hexes are said back as kept, and a text-only shade is named with its hex",
              any("stay exactly" in n and "#C2527A" in n for n in ex["notes"]) and not ex["problems"], ex["notes"])
        exp = dm.plan(design(tmp, "exactpal", NATIVE.replace('''  primary: "#C2527A"
  secondary: "#F4C2C2"''', '''  light: "#FFFFFF"
  dark: "#EEEEEE"
  muted: "#999999"
  accent: "#FF0000"
  pop2: "#00FF00"''')), exact=True)
        check("exact colors: a palette whose words won't read keeps her color and asks which shade words use",
              any("stays exactly as is for graphics" in x and "Say which" in x for x in exp["problems"]), exp["problems"])
        st = dm.plan(design(tmp, "site", SITE))
        fam = {k: v["family"] for k, v in st["fonts"].items()}
        check("website: headline from the largest display tier, label (eyebrow) and detail (mono) fonts found",
              fam == {"headline": "Font A", "caption": "Font B", "accent": "Font C", "label": "Font D", "detail": "Font E"}, fam)
        check("website: colors named by what they are land on the five roles",
              st["palette"] == {"light": "#F8F6EE", "dark": "#1E1E1E", "muted": "#395848", "accent": "#BD1B1B", "pop2": "#EEE3BA"}, st["palette"])
        check("website: the rest are extras (never pure white or black), an rgba is left out, not an error",
              st["extra"] == {"brass": "#9C7C4D", "walnut": "#4D3B2D"} and "text-muted" in st["dropped"] and not st["problems"], (st["extra"], st["dropped"], st["problems"]))
        check("website: a never-touch rule in her words becomes apart (by hue word, over a name in passing)", st["apart"] == ["accent", "muted"], st["apart"])
        check("website: a wide-tracked eyebrow is a caps label at its spacing", st["label"] == {"case": "upper", "tracking": 0.2}, st["label"])
        check("website: web px corners double for reels, a pill stays a pill; card padding doubles; lift, hairline, ease",
              st["shape"] == {"radius_card": 40, "radius_label": 999, "pad_card": 80, "shadow_card": "lift", "rule": "hairline"}
              and st["motion"].get("ease") == "cubic-bezier(0.16, 1, 0.3, 1)", (st["shape"], st["motion"]))
        check("website: size tiers of a font already used are not called dropped; web layout is",
              not {"display-sm", "body-sm", "display-xl", "eyebrow", "mono"} & set(st["dropped"]) and {"components", "spacing"} <= set(st["dropped"]), st["dropped"])
        check("website: only the mood is asked, nothing unknown", len(st["missing"]) == 1 and "mood" in st["missing"][0] and not st["unknown"], (st["missing"], st["unknown"]))
        fr = dm.plan(design(tmp, "frame", FRAME))
        check("framework: every field read, nothing unknown or wrong", not (fr["problems"] or fr["missing"] or fr["unknown"]), fr)
        check("framework: slots land within their limits",
              fr["shape"] == {"radius_card": 40, "radius_label": 999, "radius_frame": 0, "pad_card": 72, "shadow_card": "lift", "rule": "hairline"}
              and fr["motion"] == {"ease": "cubic-bezier(0.16, 1, 0.3, 1)", "numbers": "count-up", "pace": "unhurried"}
              and fr["extra"] == {"brass": "#9C7C4D"} and fr["apart"] == ["accent", "muted"]
              and fr["copy"] == {"emphasis_words": "2-3", "emphasis_punctuation": True}
              and ("effects.takeover", "rise") in fr["learn"] and ("sfx.density", "lighter") in fr["learn"] and ("motion.opener_zoom", False) in fr["learn"],
              (fr["shape"], fr["motion"], fr["learn"]))
        _pf, fb, _rf, _sf = dm.make(design(tmp, "framemk", FRAME))
        lab = (fb.get("elements") or {}).get("label") or {}
        check("framework: the pack carries the label/detail fonts, shape, motion, extras, apart and description",
              lab.get("font") == "Font D" and lab.get("case") == "upper" and lab.get("tracking") == 0.2
              and (fb["elements"].get("detail") or {}).get("font") == "Font E" and fb.get("shape", {}).get("pad_card") == 72
              and fb.get("motion", {}).get("ease") and fb.get("extra_colors") == {"brass": "#9C7C4D"} and fb.get("apart") == ["accent", "muted"]
              and fb.get("description") == "One-line north star.", {k: fb.get(k) for k in ("shape", "motion", "extra_colors", "apart", "description")})
        lim = dm.plan(design(tmp, "lim", FRAME.replace("label_tracking: 0.2", "label_tracking: 0.5").replace("card: 40,", "card: 120,")
                             .replace("card_pad: 72", "card_pad: 300").replace("card: lift", "card: 0 0 9px red")
                             .replace('ease: "cubic-bezier(0.16, 1, 0.3, 1)"', 'ease: "bounce"').replace('apart: "accent/muted"', 'apart: "accent/accent"')
                             .replace('extra: { brass: "#9C7C4D" }', 'extra: { a: "#111111", b: "#222222", c: "#333333", d: "#444444" }')))
        txt = " ".join(lim["problems"])
        check("limits: tracking, corners, padding, a raw shadow, a non-curve ease, a bad apart and too many extras are each refused",
              all(x in txt for x in ("label_tracking", "rounded.card", "card_pad", "elevation.card", "motion.ease", "colors.apart", "at most 3")), txt)
        clash = dm.plan(design(tmp, "clash", FRAME.replace("card: { ground: light, ink: dark, rule: true }", "card: { ground: accent, ink: light }")
                               .replace('apart: "accent/muted"', 'apart: "accent/light"')))
        check("apart: a card that puts the two never-touch colors together is refused", any("never touch" in x for x in clash["problems"]), clash["problems"])
        real_mk = dm._font
        dm._font = lambda folder, fam: (f"/fonts/{fam}.ttf", "on your computer")
        try:
            _p3, b3, _r3, s3 = dm.make(design(tmp, "sub", NATIVE))                    # a Butter base
        finally:
            dm._font = real_mk
        check("fonts: the subhead/eyebrow line wears her ACCENT font on a Butter base",
              b3.get("subhead_font_file") == "SYSTEM:Font C" and b3.get("subhead_font_name") == "Font C"
              and b3.get("karaoke_font_file") == "SYSTEM:Font B", {k: b3.get(k) for k in ("subhead_source", "subhead_font_file", "karaoke_font_file")})
        p_, block, recipe, sysf = dm.make(design(tmp, "mk", NATIVE))
        check("make: the whole pack built, nothing saved", p_["name"] == "My Pack" and block.get("fonts", {}).get("main") == "Font A"
              and recipe.get("palette", {}).get("accent") == "#C2527A", (block.get("fonts"), recipe.get("palette")))
        try:
            dm.write(design(tmp, "bad2", NATIVE.replace("name: My Pack", "name: Butter")))
            check("write: refuses before touching any pack file", False, "wrote")
        except dm.Problem:
            check("write: refuses before touching any pack file", True)
    finally:
        dm._font, dm.her_languages = real_font, real_langs
        shutil.rmtree(tmp, ignore_errors=True)
    # a font installed on her computer but not in CapCut yet is found in the system font folders
    src = next((f for f in ("/System/Library/Fonts/Supplemental/Georgia.ttf", "/Library/Fonts/Georgia.ttf",
                            r"C:\Windows\Fonts\georgia.ttf") if os.path.isfile(f)), None)
    if src:
        fd = tempfile.mkdtemp(prefix="fonts-")
        shutil.copyfile(src, os.path.join(fd, "Georgia-Regular.ttf"))
        real_dirs = dm._font_dirs
        dm._font_dirs = lambda: [fd]
        try:
            check("fonts: one on her computer (not in CapCut yet) is found", dm._system_font("Georgia") == os.path.join(fd, "Georgia-Regular.ttf"))
            check("fonts: a font she doesn't have is never guessed", dm._system_font("Totally Made Up Sans") is None)
            # a pack built from computer fonts points every element at them, so the build never draws a stand-in
            import pack_write
            dm._font = real_font
            dd = design(tempfile.mkdtemp(prefix="sysfont-"), "g", NATIVE.replace('"Font A"', "Georgia").replace("Font B", "Georgia").replace("Font C", "Georgia"))
            p2, block2, _r2, sys2 = dm.make(dd)
            refs = pack_write.system_font_refs(block2)
            els = block2.get("elements") or {}
            check("fonts: every element the found font drives points at it (SYSTEM:)",
                  refs == ["Georgia"] and all(str((els.get(e) or {}).get("file", "")).startswith("SYSTEM:") for e in
                  ("headline", "takeover", "caption", "thought_bubble", "accent_caption")) and block2.get("karaoke_font_file") == "SYSTEM:Georgia"
                  and str(block2.get("subhead_font_file", "")).startswith("SYSTEM:") and "Georgia" in sys2, (refs, {e: (els.get(e) or {}).get("file") for e in els}))
        finally:
            dm._font_dirs = real_dirs
            shutil.rmtree(fd, ignore_errors=True)
    if fails:
        print(f"test_design_md: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_design_md: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
