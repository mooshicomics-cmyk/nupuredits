---
name: Butter (Hands-Off Edit brand spec)
source: style-packs.json · Butter
unit: brand identity — atoms only; frame treatments live in the frame layer
principle: atoms are the pack's (fonts + accent + type discipline); ground + composition are the frame layer's
---

# Butter — design.md

> **Butter = the former Minimal, renamed + re-tuned (2026-08-09).** New Inter Black type + a mellow
> pale-lemon / cobalt palette. The concept is a **literal stick of butter** — soft, cute, buttery. Mellow
> palette + BlockFrame type discipline + Bloop for the cute accent. (The legacy pre-refinement navy+yellow
> "Minimal" look is superseded by everything below.)

## Butter identity (current spec)
**Governing rule:** this look is THE house style for **any HyperFrames MP4 render above raw** (medium-well +
well-done), not just Hands-Off. Raw / CapCut-editable path is untouched.
- **ground / light:** `#fffdd7` pale-lemon · **ink / dark:** `#317ae1` vivid cobalt · **primary accent (fill):** `#fdc341` marigold
- **palette (4 roles):** light `#fffdd7` · dark `#317ae1` · muted `#5c91e6` light cobalt · accent `#fdc341` marigold · pop2 `#fdc341`
- **treatments:** cobalt UPPERCASE Inter Black display on pale-lemon, marigold as a block/fill, Bloop for the cute kicker/eyebrow, a thin cobalt hairline rule; flat, no WordArt shadows.
- **TASTE RULE (all packs):** the ground elevates · ONE accent per slide · multicolor is a RARE treatment, not a default · female-creator aesthetic, never kiddie · no WordArt shadows.
- **frame templates:** `product/creative-vault/hands-off/butter/index.html` (the renderable source).

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

## Palette + CONTRAST (meaning-bearing text is always legible)
- ground: `#fffdd7` (pale-lemon) · ink: `#317ae1` (vivid cobalt) · muted: `#5c91e6` (light cobalt)
- **cobalt ink on pale-lemon** reads strong for display; it clears the large-display floor. For SMALL
  meaning-bearing text, prefer more weight or flip to lemon/white text on a cobalt block.
- **reel accent (over footage): `#FBE96B`** (`hook_color`) — a clear lemon-butter that reads over varied
  footage in the Yap/Voiceover lanes. LIGHT on purpose.
- **marigold `#fdc341` is a FILL, not text.** On the pale-lemon ground it barely separates (both warm +
  light), so put marigold in a BLOCK / rule / stat-cell with cobalt or ink text on it — never marigold text on
  the light ground. Meaning-bearing text is cobalt-on-lemon or lemon/white-on-cobalt. One accent moment per
  beat; never a rainbow.

## Palette — 4-role model (light · dark · muted · accent)
Every frame draws from these four roles (both a light AND a dark are always available — the ground goes either
way per the beat):
- **light** `#fffdd7` (ground / on-dark text) · **dark** `#317ae1` (ground / ink / on-light text)
- **muted** `#5c91e6` — the harmonizing mid: secondary blocks, depth, a quiet second beat (never competes with the accent)
- **accent (pop)** `#fdc341` marigold — the saturated hit. It is a **FILL / BLOCK / FULL-BLEED BACKGROUND**, or
  text ONLY on a dark (cobalt) ground.
- **second pop** `#fdc341` — Butter runs a single warm accent; the second pop is the same marigold, still rationed.
**The accent can BE the background** (full-bleed marigold ground + cobalt/ink text — the "big claim" treatment),
the cleanest home for a warm accent. Never marigold as body text on the light ground.

## Typography — fonts assigned BY ROLE (the identity)
Never let a role inherit another role's font. Butter's roles:
- **headline + takeover:** **Inter Black (900)** (`Inter-Black.otf`) — case UPPER, tight line-height (locked gold standard 0.92), tracking **-0.05em**
- **caption (single) + karaoke:** **Inter Medium (500)** (`Inter-Medium.ttf`, a STATIC file, via `karaoke_font_file`) — case lower
- **eyebrow / card-kicker:** **Bloop** (`Bloop.ttf`)
- **label:** **Space Grotesk** (`SpaceGrotesk-VF.ttf`)

> **Caption-font note:** the caption is the STATIC `Inter-Medium.ttf`, NOT the variable `Inter-VF.ttf`.
> `Inter-VF.ttf` was retired as the caption font because CapCut resolved the variable font to its lightest
> instance, "Inter Thin"; the static Medium renders at the intended weight 500.

## Type discipline (carries from the locked gold standards)
Measure the real font, never estimate. Headline is the anchor, sized big, balance-wrapped to <=2 lines with NO
orphan words; everything sizes DOWN from it. One tight line-height. **Captions sit UNDER THE CHIN (lower third), never on/over it** — over-footage captions seat below the chin with a NEGATIVE `caption_lift_px` (a positive lift rides up onto the face). Safe zone
x150-930 / y270-1620. Supporting line prefers ONE line; two balanced if needed, never tiny.

### Well-done tuning (the `welldone` block in `style-packs.json`)
`headline_tracking -0.05` · `single_tracking -0.02` (captions tightened; this ONE value drives BOTH single and
karaoke caption letter-spacing) · `karaoke_weight 500` · `single_weight 500` · `build_scale 0.85` ·
`single_scale 0.85` · `eyebrow_scale 1.35` · `hook_color #FBE96B` (clear lemon-butter over footage) ·
`subhead_color #ffffff` (WHITE eyebrow; the headline stays butter-yellow) · `subhead_weight normal` ·
`head_one_min 80` · `hook_maxw 950`.

## Motion (Hands-Off Edit)
Everything animates ON naturally — strokes draw on, sparkles twinkle, emoji/bubble settle, cards slide/pop
snappy. A touch lands AFTER the beat it accents. Quick (~0.3-0.5s), never looping-distracting.

## Breakaway card theme
Structure **minimal** (centered type): pale-lemon ground, cobalt ink UPPERCASE Inter display, the key word in
**italic**, a Bloop cobalt **BOLD** kicker (`kicker_weight 800`), and a cobalt hairline rule.

## Composition (frame layer reads this)
Flat color-blocked frames, one idea per frame, focal 3-5x its neighbors, sparse frames 45-60% empty. Accent
rationed. Designed frames use the ground + ink + the pack accent + the pack's display font.

## Structural elements — visual interest (tuned to Butter's feel, gated by impeccable)
A frame is not just text on the ground. Bring in tasteful STRUCTURAL elements for visual interest — and note
they double as the contrast fix (marigold becomes a block behind cobalt text). Vocabulary, expressed in
Butter's soft/buttery character:
- **Block behind text** — a solid fill (accent `#fdc341` or ink `#317ae1`) with legible text on it (cobalt/ink
  on the marigold block, lemon/white on the cobalt block). THE "square/rectangle behind the text" — the primary
  visual-interest + contrast device. A proven favorite; use it where a beat wants weight.
- **Kicker chip** — a small Bloop label above the headline. **Rule / underline** — a thin cobalt hairline
  under the focal. **Stat block** — the number in a filled block, or oversized with a rule.
- **Featured emphasis — ONE per frame** gets extra weight: Butter is a soft/clean pack, so favor a refined
  rule / subtle fill over a hard shadow.
Character rule: refined packs (Editorial) → thin rules, subtle fills, NO hard shadows, generous space. Bold
packs (Playful) → solid blocks + hard offset shadows (no blur), thicker borders. Butter sits soft + clean —
blocks + hairlines, never hard WordArt shadows. **Match the pack's feel; never force one pack's ornament onto another.**
Impeccable gate on EVERY element: it earns its place (one idea per frame), only ONE featured element, contrast
holds on the block, **no gradient / no blur-halo** (soft shadow at most), restraint over decoration. If an
element doesn't serve hierarchy or legibility, cut it.

## Craft floor — CROSS-REFERENCE IMPECCABLE (readable · legible · beautiful · tasteful)
Every rendered Hands-Off frame is checked against the impeccable design system
(`product/IMPECCABLE-TYPE-PRINCIPLES.md` + the impeccable skill's craft-floor) BEFORE it is called done. The
render is well-done / self-verifiable, so verify from the RENDERED frame, not the math:
- **Hierarchy at a glance** — one focal element dominates (3-5x its neighbors); roles read without reading the words.
- **Squint test** — blur the frame: the right thing leads, the supporting line supports, groups read in order.
- **Contrast floor** — meaning-bearing text clears the ground (cobalt-on-lemon, ink/cobalt-on-marigold, lemon-on-cobalt);
  decoration may favor the look, the words a viewer must READ may not.
- **Balanced, no orphan words** (measured); tracking has a floor so it never crams.
- **Grouped by proximity + rhythm** — tight within a group, generous between; never uniform spacing everywhere.
- **Silence** — sparse frames read 45-60% empty; only genuinely dense frames (stat grid, ledger) run tight.
- **Restraint / delight** — one idea per frame, accent rationed, one featured emphasis; **soft shadow only, no
  gradient, no blur-halo**; a touch appears because the beat earns it.
- **Optical corrections from the rendered frame**, not the math.
If any fails, fix it before it ships. Beautiful + tasteful is a GATE here, not a hope.
