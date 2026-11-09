#!/usr/bin/env python3
"""pack_palettes.py — the ONE source of truth for the locked per-pack palettes + treatments.

Imported by BOTH `hands_off_pack_to_design.py` (design.md generation) and `build-reel-type.py` (the render
engine's element library), so the two can never drift. Signed off with the creator 2026-08-09.

GOVERNING RULE: these looks are THE house style for any HyperFrames MP4 render ABOVE raw (medium + well-done +
Hands-Off + Animation). Raw = native CapCut, untouched. TASTE RULE: the ground elevates · ONE accent per slide ·
multicolor is a RARE treatment · female-creator aesthetic, never kiddie · no WordArt shadows.
"""

INK, INK2 = "#111111", "#2A2A2A"

# Per-pack GROUND — the solid ground for FULL-FRAME lanes (Hands-Off / Animation). Over-footage lanes
# (Yap/Voiceover well-done + medium) use the footage as the ground; the accent/elements sit on top.
GROUNDS = {
    "Editorial": "#F2EDE4",  # oat cream (green/pink/cream, locked 2026-08-09)
    "Butter":   "#fffdd7",  # Mellow PALE-BUTTER ground (vivid cobalt ink · marigold blooms), 2026-08-09
    "Playful":   "#F2EDE4",  # oat cream (brutalist framework, locked 2026-08-09)
}
GROUND = GROUNDS["Editorial"]  # legacy default

# Primary MEANING-BEARING accent per pack — text-safe on that pack's ground.
HANDS_OFF_ACCENT = {
    "Butter":   "#fdc341",  # butter-yellow karaoke keyword (2026-08-09)
    "Editorial": "#d27e96",  # dusty pink accent (green/pink/cream)
    "Playful":   "#E85A1F",  # orange, reads on cream
}

# APPROVED per-pack palettes: light · dark · muted(mid) · accent(primary pop) · pop2(second accent, rationed).
PALETTE = {
    "Editorial": {"light": "#F2EDE4", "dark": "#212c1b", "muted": "#7A8C6A", "accent": "#ffadbf", "pop2": "#d27e96"},  # green/pink/cream (exact hexes 2026-08-10): light-pink #ffadbf highlight · deep-pink #d27e96  # green/pink/cream (locked 2026-08-09)
    "Butter":   {"light": "#fffdd7", "dark": "#317ae1", "muted": "#5c91e6", "accent": "#fdc341", "pop2": "#fdc341"},  # Mellow: pale-butter · vivid-cobalt ink · mid cobalt (clears 3:1 on the pale ground; was #6f9be8 at 2.69:1) · marigold sun
    "Playful":   {"light": "#F2EDE4", "dark": "#1C2418", "muted": "#1F8A4C", "accent": "#F5C518", "pop2": "#FF6B8A"},
}
# Playful COVER only — the rare "multicolor-per-letter" treatment draws from this candy set (never every slide).
CANDY = {"Playful": ["#FF6B8A", "#1F8A4C", "#E85A1F", "#F5C518"]}

# Per-pack TREATMENT vocabulary (the approved look — what makes each pack itself).
TREATMENTS = {
    "Editorial": "Poppins uppercase mono chrome (topbar + monogram circle) + 2px pink hairline rules + Playfair display + Prosecco script accent word + KPI stat figure; flat, no shadows; green/pink/cream.",
    "Butter":   "\"Butter\" (Mellow palette + BlockFrame type): PALE-LEMON #fffdd7 ground, VIVID-COBALT #317ae1 ink + rules, MARIGOLD #fdc341 sun blooms + marigold keyword. Type = UPPERCASE Inter-900 display (-0.03em) as the loud graphic + lowercase Inter-500 captions (the calm) + BLOOP cute hand-drawn eyebrow/kicker. 1px cobalt hairlines, NO shadows/rounded. Pale-lemon + vivid cobalt + marigold.",
    "Playful":   "brutalist color-blocks (pink/green/orange/yellow) with thick ink borders + hard OFFSET shadows (sticker style, not WordArt); Soup Du Jour chunky display; Ugly Dave hand-drawn kickers; Noto uppercase labels; cream ground.",
}

# ── CARD THEME (the THEME layer) ──────────────────────────────────────────────────────────────────────────────
# Each pack's DISTINCT full-screen designed-card recipe — used by the breakaway (and, when built, Hands-Off /
# Animation full frames). This is the ONLY thing that differs per pack when the engine draws a card. The BUILD
# LOGIC that animates it (dissolve + push-in, staggered back.out reveals, accent-mark wipe, emphasis pop) and the
# caption-yield around it live ONCE in the engine and are IDENTICAL for every pack (rule 2026-08-09: themes
# distinct, build consistent). NO fabricated brand: `monogram` is a slot that renders ONLY if a client supplies a
# real logo/monogram — never invent one to fill space.
#   structure  which card layout the engine draws ("editorial" = centered type + hairline rule · "block" =
#              bordered candy-block with a hard offset shadow · "minimal" = solid block-behind-word on dark ·
#              (Vintage discarded; role name only). Font ROLES resolve to the pack's loaded fonts in the engine
#              (headline/label/script/kicker), so the theme never hardcodes a font name.
#   colors are ROLE names (accent/muted/pop2/dark/light) resolved through resolve_color for that pack.
CARD_THEME = {
    # Breakaway grounds default to FULL COLOR (2026-08-09: "breakaway animation full color" — a cream/light
    # ground reads as washed-out "white"; only the HOOK stays white, sitting over footage). Every card color is a
    # theme role here so the build never hardcodes one. A per-beat cream/light card is still available by passing
    # ground/ink on that breakaway in the plan.
    "Editorial": {
        "structure": "editorial",
        "ground": "dark", "ink": "light", "accent": "accent",   # FOREST-green ground · cream ink · pink accent
        "kicker_role": "label", "kicker_color": "accent",       # Poppins uppercase kicker, pink on green
        "script_role": "script",       # Prosecco — the one accent word may go script+pink (rare, tasteful)
        "rule": True, "rule_color": "accent",                   # pink hairline rule under the headline (wipes in)
        "monogram": None,              # client logo slot only — never fabricated
    },
    "Playful": {
        "structure": "block",
        "ground": "pop2", "ink": "dark",                        # PINK ground · ink display type (brutalist candy clash)
        "block_fill": "accent", "block_border": "dark", "block_shadow": "dark", "head_scale": 1.3,   # yellow block · ink border · hard offset shadow · bigger animated type
        "kicker_role": "kicker", "kicker_color": "light",       # Ugly Dave kicker (rotated), cream on the pink ground
        "monogram": None,
    },
    "Butter": {
        "structure": "minimal",
        # "Butter" breakaway = PALE-LEMON (#fffdd7 light) ground + COBALT ink UPPERCASE Inter-900 display (headline_case
        # upper, -0.03em); the key word goes ITALIC; a BOLD Bloop cobalt kicker (kicker_weight 800); a 1px cobalt hairline
        # rule. Full-color marigold card is available per beat via ground:"accent". (See STYLE-PACKS-SPEC.md.)
        "ground": "light", "ink": "dark", "accent": "dark",
        "kicker_role": "kicker", "kicker_color": "dark", "kicker_weight": "800",   # Bloop COBALT kicker (BOLD) on the pale-lemon panel
        "rule": True, "rule_color": "dark",
        "headline_tracking": "-0.03em", "headline_case": "upper", "emphasis_italic": True,
        "monogram": None,
    },
}

# The signature element(s) each pack reaches for first (the element library picks from these by pack).
PACK_ELEMENTS = {
    "Editorial": ["rule"],                    # thin refined marks only
    "Butter":   ["block"],                   # geometric blocks
    "Playful":   ["block", "grain"],          # color blocks + grain (multicolor lives in the type, not elements)
}


def _lum(hexcolor):
    h = str(hexcolor).lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(fg, bg):
    """WCAG contrast ratio between two #hex colors (1.0 .. 21.0)."""
    try:
        la, lb = _lum(fg), _lum(bg)
    except Exception:
        return 21.0
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def text_safe(pack, fg, bg, px):
    """Return (color, changed). If `fg` text at `px` on `bg` fails the WCAG floor (3:1 at >= 24px, 4.5:1 below),
    swap to the pack's `dark` on a light ground or `light` on a dark ground so the build never reaches the render
    gate with a legibility error. Results over perfection: a plan can name any token, the build keeps it legible."""
    floor = 3.0 if px >= 24 else 4.5
    if contrast_ratio(fg, bg) >= floor:
        return fg, False
    pal = PALETTE.get(pack, PALETTE["Editorial"])
    alt = pal.get("dark", INK) if _lum(bg) > 0.4 else pal.get("light", "#FFFFFF")
    if contrast_ratio(alt, bg) < floor:
        alt = INK if _lum(bg) > 0.4 else "#FFFFFF"
    return alt, True


def resolve_color(pack, name, default="#FFFFFF"):
    """Map a role name ('accent'/'muted'/'pop2'/'dark'/'light') to the pack's hex, or pass a raw #hex through."""
    if not name:
        return default
    if str(name).startswith("#"):
        return name
    return PALETTE.get(pack, {}).get(name, default)


def _merge_local():
    """A pack the creator built in the copy the engine ships from keeps its palette in
    `_local/pack-palettes.json` (git-ignored, never shipped), where pack_write puts it, so it can never ride
    into a buyer's bundle. Merged here the way stylepack merges `_local/style-packs.json`, so every reader
    sees it. Shape: {"PALETTE": {"<pack>": {...}}, "GROUNDS": {...}, ...}. Missing or unreadable: nothing."""
    import json, os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_local", "pack-palettes.json")
    try:
        with open(path, encoding="utf-8") as fh:
            local = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(local, dict):
        return
    for table_name, table in (("GROUNDS", GROUNDS), ("HANDS_OFF_ACCENT", HANDS_OFF_ACCENT), ("PALETTE", PALETTE),
                              ("TREATMENTS", TREATMENTS), ("PACK_ELEMENTS", PACK_ELEMENTS), ("CARD_THEME", CARD_THEME)):
        extra = local.get(table_name)
        if isinstance(extra, dict):
            table.update(extra)


_merge_local()


# ── preview overlay ──────────────────────────────────────────────────────────────────────────────────────
# A look not saved yet (the Brand Kit's three directions) is drawn by the real builders through this: a process
# started with REEL_PREVIEW_PACKS=<json> sees those packs' entries; every other process, and this file, never do.
def _preview_overlay():
    import json as _json, os as _os
    path = _os.environ.get("REEL_PREVIEW_PACKS")
    if not path or not _os.path.isfile(path):
        return
    for _name, _entries in (_json.load(open(path, encoding="utf-8")).get("palettes") or {}).items():
        for _dict in ("GROUNDS", "HANDS_OFF_ACCENT", "PALETTE", "TREATMENTS", "PACK_ELEMENTS", "CARD_THEME"):
            if _dict in _entries:
                globals()[_dict][_name] = _entries[_dict]


_preview_overlay()
