#!/usr/bin/env python3
"""Hands-Off Edit — convert a locked style pack into a design.md (brand spec).

Your style-packs.json packs ALREADY hold the atoms (fonts, accent, type discipline). This mechanically
lifts each into a design.md — the brand-identity input the frame layer (frame treatments) reads. Run:
  python product/hands_off_pack_to_design.py            # all packs -> product/creative-vault/design/<pack>.design.md
"""
import json, os, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from pack_palettes import GROUNDS, GROUND, INK, INK2, HANDS_OFF_ACCENT, PALETTE, CANDY, TREATMENTS  # single source of truth
PACKS = json.load(open(f"{ROOT}/product/creative-vault/style-packs.json", encoding="utf-8"))["packs"]
OUTDIR = f"{ROOT}/product/creative-vault/design"; os.makedirs(OUTDIR, exist_ok=True)

# Palettes/grounds/accents/treatments now live in pack_palettes.py (imported above) — one source of truth.

# legacy alias for the palette-range section
COMPLEMENTARY = {k: [("muted mid", v["muted"]), ("second pop", v.get("pop2", v["accent"]))] for k, v in PALETTE.items()}

# ---- color contrast (WCAG relative luminance) — so meaning-bearing text is always legible ----
def _lin(c): c = c / 255; return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
def _lum(hexc):
    h = hexc.lstrip("#"); r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
def contrast(a, b):
    la, lb = _lum(a), _lum(b); hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)
def _darken(hexc, f):
    h = hexc.lstrip("#"); r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % (int(r*f), int(g*f), int(b*f))
def text_safe(accent, ground, target=4.5):
    """Return a darkened accent variant that clears `target` contrast on `ground` for meaning-bearing text.
    The pale accent stays for FILLS/decoration; this variant is for accent TEXT."""
    f = 1.0
    while f > 0.15:
        v = _darken(accent, f)
        if contrast(v, ground) >= target:
            return v, round(f, 2)
        f -= 0.05
    return _darken(accent, 0.15), 0.15

def design_md(name, p):
    e = p.get("elements", {})
    hl, cap, acc = e.get("headline", {}), e.get("caption", {}), e.get("accent_caption", e.get("caption", {}))
    accent = p.get("accent_color", "#111111")
    ho_accent = HANDS_OFF_ACCENT.get(name) or text_safe(accent, GROUND)[0]
    pal = PALETTE.get(name, {})
    comp = COMPLEMENTARY.get(name, [])
    comp_block = "\n".join(
        f"- **{nm}** `{hx}` — on ground {contrast(hx, GROUND)}:1"
        + (" ✅ text-safe" if contrast(hx, GROUND) >= 4.4 else " (block-fill / large-display only)")
        for nm, hx in comp) or "- (none yet — add complementary shades that fit the vibe)"
    return f"""---
name: {name} (Hands-Off Edit brand spec)
source: style-packs.json · {name}
unit: brand identity — atoms only; frame treatments live in the frame layer
principle: atoms are the pack's (fonts + accent + type discipline); ground + composition are the frame layer's
---

# {name} — design.md

## ✅ APPROVED LOCK (renders signed off 2026-08-09)
**Governing rule:** this look is THE house style for **any HyperFrames MP4 render above raw** (medium-well +
well-done), not just Hands-Off. Raw / CapCut-editable path is untouched.
- **ground:** `{GROUNDS.get(name, GROUND)}` · **ink:** `{INK}` · **primary accent (text-safe on ground):** `{ho_accent}` ({contrast(ho_accent, GROUNDS.get(name, GROUND))}:1)
- **palette (4 roles):** light `{pal.get('light','?')}` · dark `{pal.get('dark','?')}` · muted `{pal.get('muted','?')}` · accent `{pal.get('accent','?')}` · pop2 `{pal.get('pop2','?')}`{(' · candy set ' + ' '.join(CANDY[name])) if name in CANDY else ''}
- **treatments (approved):** {TREATMENTS.get(name, '(see below)')}
- **TASTE RULE (all packs):** the ground elevates · ONE accent per slide · multicolor is a RARE treatment, not a default · female-creator aesthetic, never kiddie · no WordArt shadows.
- **frame templates:** `product/creative-vault/hands-off/{name.lower()}/index.html` (the proven, renderable source).

## Creative direction — Hands-Off = YOU direct (2026-08-09)
Hands-Off Edit is not template-filling. Act as the **creative director**: read the beat and decide the
treatment, the emphasis word, the one structural element, what stays silent. Use judgment — and when you are
unsure about a call (hierarchy, spacing, a color pairing, whether an element earns its place, motion), consult
the **FULL impeccable system** (the `impeccable` skill: typeset · layout · adapt · colorize · delight ·
craft-floor), not just the type doc. Impeccable is the authority you defer to; this design.md is the pack's
identity you direct within. Then self-verify the rendered frame against it before it ships.

## Voice (your brand, all packs share)
Big sister across the table, not a guru on a stage. Tender, hopeful, never hustle. Short punchy lines.
Lowercase for intimacy, CAPS for emphasis. NO em dashes, ever. Restraint over noise — confessional beats get
almost nothing; teaching beats can carry a designed moment. Lead with hope, never make her feel behind.

## Palette + CONTRAST (computed — meaning-bearing text is always legible)
- ground: `{GROUND}` (warm editorial paper) · ink: `{INK}` · ink-2: `{INK2}`  (ink on ground: **{contrast(INK, GROUND)}:1** ✅)
- **reel accent (over footage): `{accent}`** — LIGHT on purpose; light reads best over varied footage in the Yap/Voiceover lanes. On this SOLID ground its contrast is only **{contrast(accent, GROUND)}:1** {'✅' if contrast(accent, GROUND) >= 4.5 else '⚠️ too low for text here'}, so it is a FILL/decoration color in Hands-Off, not a text color.
- **Hands-Off accent (on grounds): `{ho_accent}`** — a richer sibling of the reel accent, chosen for visibility on the ground ("pale yellow can bring in mustard"). Contrast on ground **{contrast(ho_accent, GROUND)}:1** {'✅ text-safe' if contrast(ho_accent, GROUND) >= 4.4 else '(large-display only)'}. Use THIS for accent words / stats / meaning-bearing accent text in designed frames.
- **rule (LOCKED — the honest one):** the ACCENT IS A FILL, not text. On a light ground most of the packs' accents
  (even richer siblings) don't clear the 4.5:1 text floor, so put the accent in a BLOCK / rule / stat-cell and
  set INK on it; use CREAM on ink/dark blocks. Meaning-bearing text is ink-on-light or cream-on-dark — full
  stop. An accent-colored WORD is allowed only with a genuinely deep shade that clears 4.5:1 (here: {', '.join(nm for nm,hx in comp if contrast(hx,GROUND)>=4.5) or 'none of the mid-tones — use ink'}). One accent moment per beat; never a rainbow.
- **ground is per-pack (design call, TBD with the creator):** cream suits refined packs (Editorial); a BRIGHT accent
  (Butter yellow, Playful mustard) reads far better and bolder on a DARK ground (yellow-on-charcoal). Pick the
  ground that lets the pack's accent sing and fits its vibe — don't force one ground on every pack.

## Palette — HeyGen 4-role model (light · dark · muted · accent)
Every frame draws from these four roles (both a light AND a dark are always available — the ground goes either
way per the beat):
- **light** `{pal.get('light','?')}` (ground / on-dark text) · **dark** `{pal.get('dark','?')}` (ground / ink / on-light text)
- **muted** `{pal.get('muted','?')}` — the harmonizing mid: secondary blocks, depth, a quiet second beat (never competes with the accent)
- **accent (pop)** `{pal.get('accent','?')}` — the saturated hit. It is a **FILL / BLOCK / FULL-BLEED BACKGROUND**, or text ONLY on a dark ground. Contrasts: ink on accent {contrast(INK, pal.get('accent','#000'))}:1 · accent on dark {contrast(pal.get('accent','#000'), pal.get('dark','#000'))}:1 · cream on dark {contrast(pal.get('light','#fff'), pal.get('dark','#000'))}:1.
- **second pop** `{pal.get('pop2','?')}` — optional; only high-energy packs use a second accent, still rationed.
**The accent can BE the background** (full-bleed accent ground + ink text — the "big claim" treatment), the
cleanest home for a bright accent. Never pale accent as body text on a light ground.

## Palette range — complementary colors that fit {name}'s vibe (Hands-Off only)
The reel lane uses ONE accent (light, over footage). Hands-Off designed frames get a curated RANGE — the
primary Hands-Off accent plus harmonizing colors + shades for block fills, a secondary accent, and depth.
Primary: `{ho_accent}`. Complementary (fits {name}'s vibe):
{comp_block}
**Usage (impeccable-gated):** 2-3 colors per frame, NEVER all at once — the collision is rationed. One primary
carries emphasis; complements are supporting fills / a second beat / depth. Text on any color must clear the
contrast floor (4.5:1, or 3:1 for very large display) — light colors become block fills with dark text, not
text themselves. Fit the vibe: {name} leans {'refined + muted' if name=='Editorial' else 'clean + grounded' if name=='Butter' else 'punchy + high-energy'}.

## Typography (the pack's fonts — the identity)
- display / headline: **{hl.get('font','?')}** — case {hl.get('case','?')}, tight line-height (locked gold standard 0.92), tracking {hl.get('tracking','0')}
- caption / read-along: **{cap.get('font','?')}**
- accent / label: **{acc.get('font','?')}**

## Type discipline (carries from the locked gold standards)
Measure the real font, never estimate. Headline is the anchor, sized big, balance-wrapped to <=2 lines with NO
orphan words; everything sizes DOWN from it. One tight line-height. Captions below the chin. Safe zone
x150-930 / y270-1620. Supporting line prefers ONE line; two balanced if needed, never tiny.

## Motion (Hands-Off Edit)
Everything animates ON naturally — strokes draw on, sparkles twinkle, emoji/bubble settle, cards slide/pop
snappy. A touch lands AFTER the beat it accents. Quick (~0.3-0.5s), never looping-distracting.

## Composition (frame layer reads this)
Flat color-blocked frames, one idea per frame, focal 3-5x its neighbors, sparse frames 45-60% empty. Accent
rationed. Designed frames use the ground + ink + the pack accent + the pack's display font.

## Structural elements — visual interest (tuned to {name}'s feel, gated by impeccable)
A frame is not just text on the ground. Bring in tasteful STRUCTURAL elements for visual interest — and note
they double as the contrast fix (a light accent becomes a block behind dark text). Vocabulary, expressed in
{name}'s character:
- **Block behind text** — a solid fill (accent `{accent}` or ink `{INK}`) with legible text on it (ink on the
  accent block, cream on the ink block). THE "square/rectangle behind the text" — the primary visual-interest +
  contrast device. A proven favorite; use it where a beat wants weight.
- **Kicker chip** — a small inverted label above the headline. **Rule / underline** — a thin accent or ink line
  under the focal. **Stat block** — the number in a filled block, or oversized with a rule.
- **Featured emphasis — ONE per frame** gets extra weight: a hard offset shadow (no blur) if the pack is BOLD,
  a refined rule/thin border if the pack is QUIET.
Character rule: refined packs (Editorial) → thin rules, subtle fills, NO hard shadows, generous space. Bold
packs (Playful) → solid blocks + hard offset shadows (no blur), thicker borders. **Match the pack's feel;
never force one pack's ornament onto another.**
Impeccable gate on EVERY element: it earns its place (one idea per frame), only ONE featured element, contrast
holds on the block, **no gradient / no blur-halo** (soft shadow at most), restraint over decoration. If an
element doesn't serve hierarchy or legibility, cut it.

## Craft floor — CROSS-REFERENCE IMPECCABLE (readable · legible · beautiful · tasteful)
Every rendered Hands-Off frame is checked against the impeccable design system
(`product/IMPECCABLE-TYPE-PRINCIPLES.md` + the impeccable skill's craft-floor) BEFORE it is called done. The
render is well-done / self-verifiable, so verify from the RENDERED frame, not the math:
- **Hierarchy at a glance** — one focal element dominates (3-5x its neighbors); roles read without reading the words.
- **Squint test** — blur the frame: the right thing leads, the supporting line supports, groups read in order.
- **Contrast floor** — meaning-bearing text clears the ground (accent-on-cream, ink-on-accent, cream-on-green);
  decoration may favor the look, the words a viewer must READ may not.
- **Balanced, no orphan words** (measured); tracking has a floor so it never crams.
- **Grouped by proximity + rhythm** — tight within a group, generous between; never uniform spacing everywhere.
- **Silence** — sparse frames read 45-60% empty; only genuinely dense frames (stat grid, ledger) run tight.
- **Restraint / delight** — one idea per frame, accent rationed, one featured emphasis; **soft shadow only, no
  gradient, no blur-halo**; a touch appears because the beat earns it.
- **Optical corrections from the rendered frame**, not the math.
If any fails, fix it before it ships. Beautiful + tasteful is a GATE here, not a hope.
"""

if __name__ == "__main__":
    for name, p in PACKS.items():
        open(f"{OUTDIR}/{name}.design.md", "w", encoding="utf-8").write(design_md(name, p))
    print(f"wrote {len(PACKS)} design.md files -> {OUTDIR}")
    for f in sorted(os.listdir(OUTDIR)): print("  ", f)
