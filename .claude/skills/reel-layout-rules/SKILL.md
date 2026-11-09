---
name: reel-layout-rules
description: "The layout law for every rendered reel (scale, size, placement, centering, fill, color source). Load and resolve it BEFORE authoring graphics in any format on a rendered route (medium / well-done / Animation / baked overlay). Resolves the HyperFrames sizing rules for the actual draft canvas so nothing is placed by eye; the pre-render gate enforces it."
---

# Reel layout rules: read before you draw anything

Layout is numeric and fully determined. Measure it from here every build; never reconstruct a type scale from
memory or place by eye.

| Layer | What | Source | May change |
|---|---|---|---|
| **1 · rules** | scale, size, placement, layout, hierarchy, motion | HyperFrames docs + this skill | never |
| **2 · platform** | Instagram Reels UI safe zones | `product/safe_zones.py` | the only thing allowed to clip Layer 1 |
| **3 · dressing** | fonts, colors, radius, shadow, texture | the active pack (`pack_palettes.py`, `style-packs.json`) | how it LOOKS, never where or how big |

**A style pack never moves or resizes anything.** Moves/resizes = Layer 1; recolors/re-fonts = Layer 3.

**Rendered routes only** (medium, well-done, Animation, any baked `.mov`). On raw she sizes native CapCut text
herself; `reel_layout.governs_geometry(route)` says so.

## Step 1: resolve the numbers for THIS build

Never assume 1080×1920:

```bash
python3 -c "import product.reel_layout as rl; print(rl.resolve(draft_info_path='<draft>/draft_info.json', pack='<Pack>', fmt='<yap|voiceover|animation|broll>', register='<teaching|confessional>', route='<route>').describe())"
```

It prints the safe box, canvas center, per-role type floors, fill targets, the pack palette and the centering
rule, scaled to the real canvas. Author against those numbers.

## The rules

- **In-feed sizes** (`hyperframes-creative/references/typography.md`): body ≥32px, headlines ≥90px, data
  labels ≥24px at 1080 (`reel_layout.floor_px` scales them). A floor to clear, never a target.
- **Fill the content area** (`hyperframes/references/frame-worker-core.md`): compose the whole frame; hook/hero
  ≥95% of safe width, text cards ≥70%; compact badges opt out explicitly. A small content-hugging card means
  the type is too small.
- **Compute headline sizes** with `product/reel-graphics-base/fit-size.js`
  `fitSize(el, {maxWidth: safe_w, min: floor, max, family, peakScale})` (waits for fonts, refuses a fallback
  font, folds in the animation peak). Same fit-to-width on every headline-class element.
- **Center with `.rl-center`** from `product/reel-graphics-base/reel-layout.css`, never
  `transform: translateX(-50%)` (GSAP overwrites it). Text cards use `.rl-card`.
- **Everything proportional**: fractions of canvas width or the pack type scale, `fit-content` cards, placement
  from the measured subject band or a grid fraction. No typed absolute px, with one exception below.
- **Extreme weight contrast, tight display tracking** (300 vs 900; −0.03 to −0.05em). The locked hook is Inter
  Black 900, uppercase, ≈−0.05em, shadow only, never a card or plate. Inter here is a deliberate pack choice;
  don't swap it out.
- **Every color from the pack** (`reel_layout.LayoutContext.palette()`). A needed shade is derived from pack
  tokens, validated, and promoted back into the pack, never invented per reel.

**Traps:**
- **Percentage `padding-top/bottom` resolves against WIDTH**, not height (62% on 1080×1920 = 670px, ~35% down).
  For a vertical position use absolute px or `top:` with `.rl-center`.
- **Compound/ZWJ emoji (skin tone, gender, family, flags) render as flat blobs.** Single-codepoint emoji are
  fine; otherwise use an inline SVG.
- **A selector that matches nothing fails silently**; `reel_gate.py`/`reel_render.py` refuse it and print the
  selector. Fix the selector, never delete the animation.
- **Drawing a line on (arrow, underline, circle)?** Build the dash with `product/svg_draw.draw_on_attrs(length,
  width)`, then tween `stroke-dashoffset` to 0. The usual `dasharray = offset = length` with round caps paints a
  dot at each end before the line draws (two dots on every arrowhead); `reel_gate.py`/`reel_render.py` refuse it.
  Karaoke that swaps a word's face swaps it instantly on her onset, never as overlapping crossfades.
- **Burning a layer INTO her footage** (karaoke that must land frame-exact, a baked moment): `python3
  product/burn_layers.py --base <cut.mp4> --layer <x.mov>@<start> -o <out.mp4>`. It scales each 1080x1920 layer
  to the footage's own size; never hand-roll an ffmpeg overlay (unscaled, it lands small and top-left on her face).
- **`hyperframes snapshot` clears its folder each call**: pass `--at 9,43,46` in one call.
- **Never hand-roll captions.** `product/build-hf-captions.py` ships `single`, `build` (karaoke highlight) and
  `takeover`, writing words as escaped HTML. A generated JS literal, if ever needed, comes from `json.dumps`.

## Step 2: gate and render

`python3 product/reel_gate.py <composition> --pack <Pack> --route <route>` wraps `hyperframes check` (lint,
runtime, layout/overflow, motion, contrast, sampled across the timeline and every transition seam, plus
off-frame). Exit 0 = safe to render. Then **render through
`python3 product/reel_render.py render <comp> -o <out.mov>`** (`--strict` for every-word-must-read comps), which
runs the gate itself and caches by content hash; re-stack one changed layer with `reel_render.py composite`.
Intentional tight stacking carries `data-layout-allow-overlap`. Never call a fix done without `check` clean.

**A clean gate is the floor, not proof.** On a pack or element you have not shipped before, look at one rendered
frame before trusting a green check (a new pack's breakaway once passed `check` with its lines crossing).
