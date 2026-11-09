#!/usr/bin/env python3
"""pack_recipe.py — the engine behind `/studio recipe`: turn a buyer's 2 colors + mood + 3 fonts + a name
into a COMPLETE, contrast-checked style pack, printed as paste-ready blocks for the two files a pack lives in.

The basic `style-pack` skill only writes fonts into style-packs.json. A pack that also works in medium /
well-done / Hands-Off needs a full palette in pack_palettes.py too (ground, ink, the 5 palette roles, the
card theme, treatments, elements). This derives all of that from two seed colors + a mood, guarantees the
legibility floors (meaning-bearing text always clears contrast on its ground), and prints:
  1) the STYLE-PACKS.JSON pack block (element sizes cloned from a base pack; fonts, accent and case are hers)
  2) the PACK_PALETTES.PY entries (one line to add to each dict)
Claude (running /studio recipe) then refines it through the impeccable design system + a preview render
before locking. This helper is the safe scaffold; impeccable makes it beautiful.

  python3 product/pack_recipe.py --name "Sunrise" \
      --main "Clash Display" --caption "Inter" --accent "Caveat" \
      --primary "#E8502E" --secondary "#F5C518" --mood "warm playful bold" [--base Playful] [--dark-ground]
"""
import argparse, json, os, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PACKS_JSON = os.path.join(ROOT, "product", "creative-vault", "style-packs.json")

# ---- color math (RGB blend + darken + WCAG contrast) -------------------------------------------------
def _hex(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))

def _to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in rgb)

def _blend(a, b, t):
    ra, rb = _hex(a), _hex(b)
    return _to_hex(tuple(ra[i] * (1 - t) + rb[i] * t for i in range(3)))

def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def _lum(hexc):
    r, g, b = _hex(hexc)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)

def _darken(hexc, f):
    return _to_hex(tuple(v * f for v in _hex(hexc)))

def text_safe(color, ground, target=4.5):
    """Darken (or lighten toward the ground's opposite) until `color` clears `target` contrast on `ground`."""
    # try darkening first (works when ground is light)
    f = 1.0
    while f > 0.12:
        v = _darken(color, f)
        if contrast(v, ground) >= target:
            return v
        f -= 0.04
    # ground is dark: lighten toward white instead
    t = 0.0
    while t < 0.9:
        v = _blend(color, "#FFFFFF", t)
        if contrast(v, ground) >= target:
            return v
        t += 0.05
    return _darken(color, 0.12)


MOOD_STRUCTURE = [  # (keywords, card structure, elements, treatment-verb)
    (("play", "bold", "fun", "punch", "loud", "brutal", "candy", "energ"), "block", ["block", "grain"], "solid color-blocks with thick ink borders + hard offset shadows"),
    (("refined", "elegant", "editor", "classic", "literary", "quiet", "soft", "minimal chic"), "editorial", ["rule"], "thin hairline rules + a script accent word, flat, no shadows"),
    (("clean", "modern", "minimal", "simple", "calm", "mellow"), "minimal", ["block"], "one solid block-behind-word + a hairline rule, no shadows"),
]

def pick_structure(mood):
    m = (mood or "").lower()
    for keys, struct, elems, verb in MOOD_STRUCTURE:
        if any(k in m for k in keys):
            return struct, elems, verb
    return "editorial", ["rule"], "thin hairline rules, flat, no shadows"  # safe default


def build(name, primary, secondary, mood, dark_ground):
    struct, elements, verb = pick_structure(mood)
    # ground + ink
    if dark_ground:
        ground = _darken(secondary, 0.28) if _lum(secondary) > 0.15 else _darken(primary, 0.28)
        ink = "#FFFFFF" if contrast("#FFFFFF", ground) >= 7 else _blend(primary, "#FFFFFF", 0.85)
    else:
        ground = _blend(secondary, "#FFFFFF", 0.90)   # a light, warm tint of the secondary (keeps their color present)
        ink = "#1a1a17" if contrast("#1a1a17", ground) >= 8 else _darken(primary, 0.22)
    accent = primary                                  # the saturated pop (fill / block / over-footage keyword)
    pop2 = secondary
    muted = _blend(primary, ink, 0.5)                 # a harmonizing mid
    light = ground
    dark = ink
    hands_off_accent = text_safe(accent, ground, 4.5) # the meaning-bearing text version of the accent

    palette = {"light": light, "dark": dark, "muted": muted, "accent": accent, "pop2": pop2}
    # card theme per structure (mirrors the shape of the shipped pack that uses that structure)
    if struct == "block":
        card = {"structure": "block", "ground": "pop2", "ink": "dark", "block_fill": "accent",
                "block_border": "dark", "block_shadow": "dark", "head_scale": 1.3,
                "kicker_role": "kicker", "kicker_color": "light", "monogram": None}
    elif struct == "minimal":
        card = {"structure": "minimal", "ground": "light", "ink": "dark", "accent": "dark",
                "kicker_role": "kicker", "kicker_color": "dark", "rule": True, "rule_color": "dark",
                "monogram": None}
    else:
        card = {"structure": "editorial", "ground": "dark", "ink": "light", "accent": "accent",
                "kicker_role": "label", "kicker_color": "accent", "script_role": "script",
                "rule": True, "rule_color": "accent", "monogram": None}
    return {
        "ground": ground, "ink": ink, "hands_off_accent": hands_off_accent, "palette": palette,
        "card": card, "elements": elements, "structure": struct,
        "treatment": f"{name}: {verb}. Ground {ground} · ink {ink} · accent {accent} · second pop {pop2}. "
                     f"Type = the pack's main font as the loud display, caption font as the read-along, accent font for kickers/asides.",
    }


# Case is HERS, never the base pack's. The clone is for layout (sizes, positions, tracking, line height); Butter's
# headline and takeover are ALL CAPS, so a pack cloned from Butter used to come out shouting in caps she never chose
# (and kept doing it after she made that pack her default). The headline + takeover take her answer, and with no
# answer her words stay exactly as she typed them. Captions keep the clone's case unless she names one.
LOUD_ROLES = ("headline", "takeover")
CASE_CHOICES = ("upper", "as-written", "lower", "title", "sentence")
DEFAULT_CASE = "as-written"


def norm_case(rule):
    """Any spelling of a case ('ALL CAPS', 'as typed', 'uppercase', 'none') -> upper / as-written / lower / title / sentence."""
    try:
        import stylepack
        return stylepack.normalize_case(rule, default=DEFAULT_CASE)
    except Exception:
        r = "".join(ch for ch in str(rule or "").lower() if ch.isalpha())
        return {"upper": "upper", "uppercase": "upper", "caps": "upper", "allcaps": "upper",
                "lower": "lower", "lowercase": "lower", "title": "title", "titlecase": "title"}.get(r, DEFAULT_CASE)


def clone_element_block(base_name, main, caption, accent, accent_color, case=DEFAULT_CASE, caption_case=None):
    """Clone the base pack's element sizes/tracking/line height (the LOCKED layout) and swap in her fonts and case.

    `case` is her headline + takeover case: one rule for both, or {role: rule} per role. The default keeps her words
    as she typed them, so nothing inherits the base pack's case by accident. `case=None` keeps the base's case, for a
    caller that sets each role's case itself afterwards (canva_to_pack reads it off her own Canva pages).
    `caption_case` sets the caption's case; None keeps the clone's."""
    cfg = json.load(open(PACKS_JSON, encoding="utf-8"))
    packs = cfg.get("packs", {})
    base_key = next((k for k in packs if k.lower() == base_name.lower()), None)
    if not base_key:
        sys.exit(f"pack-recipe: base pack '{base_name}' not found. Available: {', '.join(packs.keys())}")
    import copy
    block = copy.deepcopy(packs[base_key])
    role_font = {"headline": main, "takeover": main, "caption": caption,
                 "thought_bubble": accent, "accent_caption": accent}
    for el_name, el in (block.get("elements") or {}).items():
        if isinstance(el, dict) and el_name in role_font:
            el["font"] = role_font[el_name]
            el["file"] = ""   # resolved by name from CapCut/system at build; leave file blank for the buyer's font
    els = block.get("elements") or {}
    if case is not None:
        per_role = case if isinstance(case, dict) else {r: case for r in LOUD_ROLES}
        for r, rule in per_role.items():
            if isinstance(els.get(r), dict):
                els[r]["case"] = norm_case(rule)
    if caption_case is not None and isinstance(els.get("caption"), dict):
        els["caption"]["case"] = norm_case(caption_case)
    block["accent_color"] = accent_color
    # A base pack can also PIN a font outside its elements, at the pack's top level: Playful pins the eyebrow
    # to Ugly Dave, Butter pins the eyebrow to Bloop and the karaoke line to Inter (build-reel-type, hooksplit
    # and the b-roll resolver all read them there). Those are the BASE pack's typefaces, not this pack's, and
    # inheriting one silently swaps in a font the creator never chose. Drop them so each role resolves from
    # this pack's own three fonts.
    for k in ("subhead_font_file", "subhead_font_name", "karaoke_font_file", "karaoke_font_name"):
        block.pop(k, None)
    # Same for the base pack's own hook + eyebrow COLORS (Butter's rendered hook is its butter yellow). Colors
    # are the creator's, and a recipe sets neither, so the rendered hook falls back to the engine's white.
    for k in ("hook_color", "subhead_color"):
        (block.get("welldone") or {}).pop(k, None)
    # The clone still carries the BASE pack's top-level fonts dict + vibe string; overwrite both so the
    # emitted block advertises the buyer's fonts, not the base pack's.
    block["fonts"] = {"main": main, "accent": accent, "caption": caption}
    block["vibe"] = "custom pack built with /studio recipe"
    for k in list(block.keys()):
        if k.startswith("_"):   # drop base pack's private notes; recipe adds its own
            block.pop(k)
    block["_recipe"] = f"Built with /studio recipe. Layout cloned from {base_key}; fonts + accent are the creator's."
    block["in_launch_kit"] = False
    return block


def case_line(block):
    """One plain line saying the case each loud role and the captions came out in, for the build summary."""
    els = block.get("elements") or {}
    say = {"upper": "ALL CAPS", "as-written": "as she types it", "lower": "lowercase", "title": "Title Case",
           "sentence": "Sentence case"}
    return " · ".join(f"{r} {say.get(norm_case(els[r].get('case')), els[r].get('case'))}"
                      for r in (*LOUD_ROLES, "caption") if isinstance(els.get(r), dict))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",

                   help="apply the pack to style-packs.json + pack_palettes.py instead of printing it to paste by hand")

    ap.add_argument("--force", action="store_true", help="with --write: replace a pack of the same name")
    ap.add_argument("--name", required=True)
    ap.add_argument("--main", required=True, help="main/display font name")
    ap.add_argument("--caption", required=True, help="caption/read-along font name")
    ap.add_argument("--accent", required=True, help="accent/kicker font name")
    ap.add_argument("--primary", required=True, help="their primary color (the pop) as #hex")
    ap.add_argument("--secondary", required=True, help="their secondary color as #hex")
    ap.add_argument("--mood", default="", help="2-3 mood words, e.g. 'warm playful bold'")
    ap.add_argument("--base", default="Editorial", help="pack to clone the locked element sizes from (default Editorial)")
    ap.add_argument("--dark-ground", action="store_true", help="use a dark ground (default is a light tint)")
    ap.add_argument("--case", default=DEFAULT_CASE,
                    help="her headline + takeover case: upper (ALL CAPS) or as-written (the way she types it, the "
                         "default); lower / title / sentence (a capital on the first word) also work. Never taken "
                         "from the base pack")
    ap.add_argument("--caption-case", default=None, help="the captions' case (default: the base layout's)")
    a = ap.parse_args()

    r = build(a.name, a.primary, a.secondary, a.mood, a.dark_ground)
    accent_color = r["hands_off_accent"]  # over-footage keyword uses the text-safe accent by default
    block = clone_element_block(a.base, a.main, a.caption, a.accent, r["palette"]["accent"],
                                case=a.case, caption_case=a.caption_case)

    # contrast report
    g = r["ground"]
    print("── RECIPE for pack:", a.name, "──")
    print(f"  structure: {r['structure']}  ·  mood: {a.mood or '(none)'}  ·  base layout: {a.base}")
    print(f"  ground {g} · ink {r['ink']}  (ink on ground {contrast(r['ink'], g)}:1 {'OK' if contrast(r['ink'],g)>=7 else 'LOW'})")
    print(f"  accent {r['palette']['accent']}  ·  text-safe accent {r['hands_off_accent']} (on ground {contrast(r['hands_off_accent'], g)}:1 {'OK' if contrast(r['hands_off_accent'],g)>=4.5 else 'LOW — will darken more'})")
    print(f"  fonts: main={a.main} · caption={a.caption} · accent={a.accent}")
    print(f"  case: {case_line(block)}")
    print()
    print("═══ 1) ADD THIS PACK BLOCK to product/creative-vault/style-packs.json  (inside \"packs\": { ... }) ═══")
    _entry = json.dumps({a.name: block}, indent=2).split("\n")
    print("\n".join(_entry[1:-1]))   # drop the outer { and }; leaves a valid "Name": { ... } entry to paste
    print()
    print("═══ 2) ADD THESE ENTRIES to product/pack_palettes.py  (one line per dict) ═══")
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
    print("Next: paste both blocks in, then refine through the impeccable design system and render one")
    print("preview caption before locking. Fonts resolve by name from the buyer's CapCut/system at build")
    print("(run product/capcut_font_doctor.py if one does not pull).")


if __name__ == "__main__":
    main()
