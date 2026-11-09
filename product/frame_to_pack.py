#!/usr/bin/env python3
"""frame_to_pack.py — turn a HyperFrames FRAME.md into a working reel style pack.

This is the bridge between hyperframes.dev/design and the reel engine. The creator picks or
fine-tunes a frame on the site (or uses one of the bundled presets), downloads the frame pack,
and this maps its designed atoms onto the pack format the engine renders with:

    FRAME.md  colors: + typography:
        -> semantic roles (ink / canvas / accent / accent2, display / body / mono)
        -> style-packs.json element block  +  pack_palettes.py entries

The mapping is a faithful Python port of the SAME role logic the HyperFrames workflows already
use (`.claude/skills/product-launch-video/scripts/lib/tokens.mjs`), so a frame produces the same
ink/canvas/accent here as it does for that pipeline. One mapping, consistent everywhere.

The frame's own ground and ink WIN — they are designed values, not guesses, so we never recompute
them. pack_recipe.py supplies the derived roles (muted, pop2), the card theme, and the contrast
floors, and every result is re-checked against the frame's real ground.

Usage:
    python3 product/frame_to_pack.py --frame editorial-forest --name "Forest"
    python3 product/frame_to_pack.py --frame ~/Downloads/my-frame-pack/FRAME.md --name "Mine" \
        --accent-font "Ugly Dave"
"""
import argparse, json, os, re, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))
import pack_recipe as pr
try:
    import capcut_userfonts as _cf
except Exception:
    _cf = None


def resolve_font(name):
    """Find the real font file for a family name (bundled / CapCut / system). '' when absent -
    the engine then tells the creator to add it rather than faking one."""
    if not name or _cf is None:
        return ""
    try:
        # a family the engine bundles (Caveat ships as Caveat-VF.ttf) is that file, named the way every shipped pack
        # names its bundled fonts (relative to assets/fonts); it was never looked for, so it read "not installed"
        bundled = _cf.bundled_font_for(name)
        if bundled:
            return os.path.basename(bundled)
        return _cf.resolve_font_file(name) or ""
    except Exception:
        return ""

PRESETS = os.path.join(ROOT, ".claude", "skills", "hyperframes-creative", "frame-presets")

# ── the tokens.mjs port ───────────────────────────────────────────────────────
HEX6 = re.compile(r"^#?([0-9a-fA-F]{6})$")
UA_DEFAULT = {c.upper() for c in
              ["#0000EE", "#0000FF", "#0000CC", "#1A0DAB", "#551A8B", "#EE0000"]}
STATUS_KEY = re.compile(
    r"(?:^|[-_])(?:positive|negative|success|error|warning|danger|good|bad|up|down|"
    r"info|neutral|alert|caution|critical)(?:[-_]|$)", re.I)
INK_KEY = re.compile(r"(?:^|[-_])ink(?:[-_]|$)|black|charcoal|^text(?:-dark)?$|outline|noir", re.I)
CANVAS_KEY = re.compile(r"cream|paper|canvas|white|bg|ground|surface|base|sand|parchment|"
                        r"off-?white|bone", re.I)


def _rgb(v):
    m = HEX6.match(str(v).strip())
    if not m:
        return None
    n = int(m.group(1), 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def lum(v):
    c = _rgb(v)
    return None if c is None else 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def chroma(v):
    c = _rgb(v)
    return -1 if c is None else max(c) - min(c)


def parse_colors(md):
    """[key, value] pairs under the top-level `colors:` block, until dedent."""
    out, inblk = [], False
    for line in md.splitlines():
        if re.match(r"^colors:\s*$", line):
            inblk = True
            continue
        if not inblk:
            continue
        if re.match(r"^\S", line):
            break
        m = re.match(r'^\s+([\w-]+):\s*(?:"([^"]+)"|\'([^\']+)\'|'
                     r'(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|[^#\s][^#\n]*?))\s*(?:#.*)?$', line)
        if m:
            out.append((m.group(1), (m.group(2) or m.group(3) or m.group(4)).strip()))
    return out


def parse_fonts(md):
    """role -> fontFamily under `typography:`; then pick display / body / mono."""
    roles, inblk = {}, False
    for line in md.splitlines():
        if re.match(r"^typography:\s*$", line):
            inblk = True
            continue
        if not inblk:
            continue
        if re.match(r"^\S", line):
            break
        m = re.match(r'^\s+([\w-]+):\s*\{[^}]*fontFamily:\s*"([^"]+)"', line)
        if m:
            roles[m.group(1)] = m.group(2)
    vals = list(roles.values())
    body = roles.get("body") or roles.get("subtitle") or (vals[0] if vals else None)
    display = next((roles[k] for k in
                    ("display", "headline", "card-headline", "section-headline",
                     "quote-display", "h1", "h2", "title", "hero") if k in roles), body)
    mono = next((roles[k] for k in
                 ("mono", "mono-tag", "mono-chrome", "mono-tick", "code", "data", "pagenum",
                  "label", "caption-mono", "chrome", "tag", "meta")
                 if k in roles), None)
    return {"display": display, "body": body, "mono": mono, "roles": roles}


def hue(v):
    c = _rgb(v)
    if c is None:
        return None
    r, g, b = [x / 255 for x in c]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return None
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def semantic_colors(colors):
    """ink / canvas / display-dark / accent pair.

    Validated against the three packs the creator built by hand from these same frames:
      · Editorial Forest -> her dark #212c1b came from green-deep #243a21 (chroma 25),
        NOT the neutral ink #1a1a17 (chroma 3).
      · Biennale Yellow  -> her dark #317ae1 came from ink #1B2566, which is itself a
        highly chromatic indigo (chroma 75), so it wins either way.
      · BlockFrame       -> only a pure black #000000 exists, so the neutral is correct.
    Hence: the pack's DISPLAY dark is the darkest color carrying real chroma; a neutral
    near-black is the fallback, never the preference.
    """
    if not colors:
        return {}
    hexes = [(k, v) for k, v in colors if lum(v) is not None]
    if not hexes:
        return {}
    by_lum = sorted(hexes, key=lambda kv: lum(kv[1]))
    named = lambda rx: next((kv for kv in colors if rx.search(kv[0])), None)

    csts = [kv for kv in hexes if CANVAS_KEY.search(kv[0])]
    soft = [kv for kv in csts if str(kv[1]).upper() not in ("#FFFFFF", "#FFF")]
    canvas = (max(soft or csts, key=lambda kv: lum(kv[1]))[1] if csts else by_lum[-1][1])
    neutral_ink = (named(INK_KEY) or by_lum[0])[1]

    # the DISPLAY dark: darkest color with real chroma, else the neutral ink
    darks = [kv for kv in by_lum if lum(kv[1]) < 120 and kv[1] != canvas]
    reads = lambda c: pr.contrast(c, canvas) >= 7.0      # body-text floor against the real ground
    chromatic = [kv for kv in darks if chroma(kv[1]) >= 20 and reads(kv[1])]
    plain = [kv for kv in darks if reads(kv[1])]
    display_dark = (chromatic[0][1] if chromatic
                    else (plain[0][1] if plain else (darks[0][1] if darks else neutral_ink)))

    # accent family: loudest color, then its own lighter / deeper siblings in the SAME hue.
    # The frames ship both (pink + pink-deep), and the creator used the light one over footage and
    # the deep one as the on-cream text accent. Prefer the designed pair over recomputing.
    cands = [(k, v) for k, v in colors
             if v not in (neutral_ink, canvas, display_dark)
             and str(v).upper() not in UA_DEFAULT
             and not STATUS_KEY.search(k)
             and lum(v) is not None]
    cands = [kv for kv in cands if chroma(kv[1]) >= 30]   # a near-neutral is never an accent
    cands.sort(key=lambda kv: chroma(kv[1]), reverse=True)
    if not cands:
        return {"ink": display_dark, "neutral_ink": neutral_ink, "canvas": canvas,
                "accent": display_dark, "accent_deep": display_dark, "accent2": display_dark}
    lead = cands[0]
    lh = hue(lead[1])
    family = [kv for kv in cands
              if lh is None or hue(kv[1]) is None
              or min(abs(hue(kv[1]) - lh), 360 - abs(hue(kv[1]) - lh)) <= 32]
    family.sort(key=lambda kv: chroma(kv[1]), reverse=True)
    accent_light = family[0][1]                      # loudest -> the over-footage keyword
    family.sort(key=lambda kv: lum(kv[1]))
    accent_deep = family[0][1]                       # darkest sibling -> the on-cream candidate
    others = [v for k, v in cands if v not in (accent_deep, accent_light)]
    return {"ink": display_dark, "neutral_ink": neutral_ink, "canvas": canvas,
            "accent": accent_light, "accent_deep": accent_deep,
            "accent2": others[0] if others else accent_deep}


# ── the frame's own letter case ───────────────────────────────────────────────
# The case is the creator's design, never the base layout's. A frame marks it on each type role
# (`heading-xl: { ..., upper: true }`, `h1: { ..., lower: true }`, or a textTransform), so read it from
# the roles that set headlines; when the frame sets neither, her words stay the way she typed them.
_HEAD_ROLE = re.compile(r"display|headline|heading|hero|title|^h[1-3]$|quote", re.I)


def frame_case(md):
    """'upper' / 'lower' when most of the frame's headline roles are set that way, else 'as-written'."""
    seen, inblk = [], False
    for line in md.splitlines():
        if re.match(r"^typography:\s*$", line):
            inblk = True
            continue
        if not inblk:
            continue
        if re.match(r"^\S", line):
            break
        m = re.match(r"^\s+([\w-]+):\s*\{([^}]*)\}", line)
        if m and _HEAD_ROLE.search(m.group(1)):
            body = m.group(2)
            if re.search(r"\bupper:\s*true\b|textTransform:\s*\"?uppercase", body, re.I):
                seen.append("upper")
            elif re.search(r"\blower:\s*true\b|textTransform:\s*\"?lowercase", body, re.I):
                seen.append("lower")
            else:
                seen.append("as-written")
    for rule in ("upper", "lower"):
        if seen and seen.count(rule) * 2 > len(seen):
            return rule
    return "as-written"


# ── which locked layout to clone ──────────────────────────────────────────────
# The base only supplies sizes / positions (the LOCKED layout), never the case. Pick the one whose
# character is nearest the frame so the numbers suit the type.
def pick_base(md, fonts):
    text = md.lower()
    disp = (fonts.get("display") or "").lower()
    if re.search(r"neobrutal|brutalist|maximal|candy|offset shadow|sticker|poster|slab", text):
        return "Playful"
    if re.search(r"serif|editorial|literary|catalogue|broadsheet|newsprint", text) or "serif" in disp:
        return "Editorial"
    return "Butter"


def mood_from_frame(md):
    """Pull the description line for the mood words pack_recipe uses to pick a card structure."""
    m = re.search(r"^description:\s*>?\s*$", md, re.M)
    desc = ""
    if m:
        for line in md[m.end():].splitlines():
            if re.match(r"^\S", line):
                break
            desc += " " + line.strip()
    else:
        m2 = re.search(r"^description:\s*(.+)$", md, re.M)
        desc = m2.group(1) if m2 else ""
    return " ".join(desc.split())[:220]


def resolve_frame(arg):
    """A bundled preset name, a folder, or a direct path to a FRAME.md."""
    cands = [arg,
             os.path.join(arg, "FRAME.md"),
             os.path.join(PRESETS, arg, "FRAME.md"),
             os.path.join(PRESETS, arg.lower().replace(" ", "-"), "FRAME.md")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    sys.exit(f"could not find a FRAME.md for {arg!r}\n"
             f"  bundled presets: {', '.join(sorted(os.listdir(PRESETS)))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True,
                    help="preset name (e.g. editorial-forest), a frame-pack folder, or a FRAME.md path")
    ap.add_argument("--name", required=True, help="what to call the new pack")
    ap.add_argument("--main-font", default=None,
                    help="override the frame's display font (e.g. the frame says Barlow but CapCut "
                         "has Barlow Condensed)")
    ap.add_argument("--caption-font", default=None,
                    help="override the frame's body/caption font")
    ap.add_argument("--accent-font", default=None,
                    help="the personality font (thought bubbles / kickers). Defaults to the frame's "
                         "mono role, else its body font.")
    ap.add_argument("--base", default=None, choices=["Editorial", "Playful", "Butter"],
                    help="which pack's LOCKED layout to clone (auto-picked from the frame if omitted)")
    ap.add_argument("--dark-ground", action="store_true")
    ap.add_argument("--case", default=None,
                    help="her headline + takeover case: upper (ALL CAPS) or as-written (the way she types it). "
                         "Default: what the frame itself sets (caps when its headlines are upper), never the base pack's")
    ap.add_argument("--caption-case", default=None, help="the captions' case (default: the base layout's)")
    ap.add_argument("--write", action="store_true",

                   help="apply the pack to style-packs.json + pack_palettes.py instead of printing it to paste by hand")

    ap.add_argument("--force", action="store_true", help="with --write: replace a pack of the same name")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead")
    a = ap.parse_args()

    path = resolve_frame(a.frame)
    md = open(path, encoding="utf8").read()
    colors = parse_colors(md)
    if not colors:
        sys.exit(f"no `colors:` block found in {path}")
    fonts = parse_fonts(md)
    sem = semantic_colors(colors)
    base = a.base or pick_base(md, fonts)
    mood = mood_from_frame(md)
    # a frame names ideal families; what the buyer actually added in CapCut may differ, and
    # CapCut is the one that has to have it. Explicit overrides win.
    if a.main_font:
        fonts["display"] = a.main_font
    if a.caption_font:
        fonts["body"] = a.caption_font
    accent_font = a.accent_font or fonts.get("mono") or fonts.get("body")

    # pack_recipe supplies the derived roles + card theme + treatment from the two loudest
    # colors; then the frame's OWN designed ground and ink overwrite the computed ones.
    r = pr.build(a.name, sem["accent"], sem["accent2"], mood, a.dark_ground)
    ground_designed = sem["canvas"]
    ink_designed = sem["ink"]
    r["palette"]["light"] = ground_designed
    r["palette"]["dark"] = ink_designed
    r["ground"] = ground_designed
    r["ink"] = ink_designed
    # pack_recipe wrote the treatment prose from its COMPUTED ground/ink, which the two lines above
    # have just replaced with the frame's real ones. Re-point the prose at the same hexes the rest of
    # the pack uses, or TREATMENTS advertises a ground nothing else renders — and it is what feeds the
    # Hands-Off design brief (hands_off_pack_to_design.py), the one lane with no eyes on it.
    r["treatment"] = re.sub(r"Ground \S+ · ink \S+",
                            f"Ground {ground_designed} · ink {ink_designed}", r["treatment"])
    # the over-footage keyword stays the loud accent; the on-cream one must READ on the
    # frame's real ground, so re-derive it against that ground rather than the computed one.
    # the frame usually ships a designed deep sibling (pink-deep, green-deep). Use it when it
    # clears 4.5:1 on the real ground; only fall back to darkening when it does not.
    deep = sem.get("accent_deep") or sem["accent"]
    LARGE_TEXT = 3.0   # the accent only ever sets kickers / emphasis words at display size
    r["hands_off_accent"] = (deep if pr.contrast(deep, ground_designed) >= LARGE_TEXT
                             else pr.text_safe(sem["accent"], ground_designed, LARGE_TEXT))

    case = a.case or frame_case(md)
    block = pr.clone_element_block(base, fonts["display"], fonts["body"],
                                   accent_font, r["palette"]["accent"],
                                   case=case, caption_case=a.caption_case)
    # resolve each role's real font FILE (bundled / CapCut / system). A blank file means the
    # creator has not added it yet, and the engine says so instead of substituting.
    missing = []
    for el_name, fam in (("headline", fonts["display"]), ("takeover", fonts["display"]),
                         ("caption", fonts["body"]), ("thought_bubble", accent_font),
                         ("accent_caption", accent_font)):
        el = (block.get("elements") or {}).get(el_name)
        if isinstance(el, dict):
            f = resolve_font(fam)
            el["file"] = f
            if not f and fam and fam not in missing:
                missing.append(fam)

    # Keep the base's welldone tuning (scales, line-height, shadow) - it is the locked
    # layout's companion and the legibility floors catch anything too small. The base's pinned
    # fonts (they sit at the pack's top level, not in welldone: Playful's eyebrow is Ugly Dave,
    # Butter's eyebrow is Bloop and its karaoke line Inter) and its hook colors are already
    # dropped by the clone, so every role resolves from this pack's own fonts and colors.
    block["welldone"] = block.get("welldone") or {}

    block["vibe"] = f"from the {os.path.basename(os.path.dirname(path))} frame"
    block["_recipe"] = (f"Built by frame_to_pack from the "
                        f"{os.path.basename(os.path.dirname(path))} frame. Layout cloned from "
                        f"{base}; colors and fonts are the frame's. A first draft - refine before locking.")

    c_ink = pr.contrast(ink_designed, ground_designed)
    c_acc = pr.contrast(r["hands_off_accent"], ground_designed)

    if a.json:
        print(json.dumps({"name": a.name, "frame": path, "base": base,
                          "ground": ground_designed, "ink": ink_designed,
                          "palette": r["palette"], "hands_off_accent": r["hands_off_accent"],
                          "fonts": {"main": fonts["display"], "caption": fonts["body"],
                                    "accent": accent_font},
                          "missing_fonts": missing,
                          "case": {k: ((block.get("elements") or {}).get(k) or {}).get("case")
                                   for k in ("headline", "takeover", "caption")},
                          "contrast": {"ink_on_ground": c_ink, "accent_on_ground": c_acc},
                          "block": block}, indent=2))
        return

    print(f"── FRAME → PACK: {a.name} ──")
    print(f"  source: {path}")
    print(f"  cloned layout: {base}   ·   card structure: {r['structure']}")
    print(f"  ground {ground_designed} · ink {ink_designed}   "
          f"(ink on ground {c_ink}:1 {'OK' if c_ink >= 7 else 'LOW'})")
    print(f"  accent {r['palette']['accent']} (over footage) · text-safe {r['hands_off_accent']} "
          f"(on ground {c_acc}:1 {'OK' if c_acc >= 3.0 else 'LOW'})")
    print(f"  fonts: main={fonts['display']} · caption={fonts['body']} · accent={accent_font}")
    print(f"  case: {pr.case_line(block)}"
          + ("" if a.case else "   (from the frame; --case upper or --case as-written changes it)"))
    if missing:
        print(f"  ⚠ not installed yet: {', '.join(missing)} — add each in CapCut once "
              f"(they are Google Fonts, free), then re-run. Nothing is faked.")
    else:
        print("  ✓ every font resolved to a real file")
    print()
    print('═══ 1) ADD TO product/creative-vault/style-packs.json  (inside "packs": { ... }) ═══')
    print("\n".join(json.dumps({a.name: block}, indent=2).split("\n")[1:-1]))
    print()
    print("═══ 2) ADD TO product/pack_palettes.py ═══")
    print(f'  GROUNDS["{a.name}"] = "{r["ground"]}"')
    print(f'  HANDS_OFF_ACCENT["{a.name}"] = "{r["hands_off_accent"]}"')
    print(f'  PALETTE["{a.name}"] = {r["palette"]!r}')
    print(f'  TREATMENTS["{a.name}"] = {r["treatment"]!r}')
    print(f'  PACK_ELEMENTS["{a.name}"] = {r["elements"]!r}')
    print(f'  CARD_THEME["{a.name}"] = {r["card"]!r}')
    print()
    if a.write:
        import pack_write
        try:
            print(pack_write.apply(a.name, block, r, force=a.force))
        except pack_write.PackWriteError as e:
            print(f"  \u26d4 not written: {e}")
            return
        print(f"  next: preview it \u2014 python3 product/build-pack-showcase.py {a.name} && "
              f"python3 product/reel_render.py render projects/_pack-preview/{a.name} "
              f"-o projects/_pack-preview/{a.name}/preview.mp4")
        print()
    print("Fonts resolve by NAME at build time from the buyer's CapCut / system fonts. The frame's")
    print("fonts are Google Fonts, so they are free to install; add each in CapCut once (same as")
    print("setup) or run product/capcut_font_doctor.py if one does not pull.")


if __name__ == "__main__":
    main()
