# Text Layouts — the templated pattern library (LAYOUT is fixed · STYLE is swappable)

> **The rule:** the LAYOUT (structure + behavior + animation) is permanent and always available. The STYLE
> (fonts, colors, sizes) comes from a swappable **STYLE PACK**. Choosing a new look = swapping the pack's
> tokens; the layouts never change. This is how we template the creator's reels so a creator can pick fonts/colors per
> "style pack" and still get the same proven layouts. (the creator's directive 2026-07-30; see reel build formula.)

Engine for the kinetic layouts: `product/build-hf-captions.py`. It rebuilds its `STYLE` tokens from the active
pack in `style-packs.json` on every build (the `STYLE = {…}` near the top is only a placeholder, and a build with no
pack fails loud). Title = `projects/*/hf-intro/`. Thought bubble = native CapCut component. All read the SAME
style tokens.

---

## The 5 layouts (always available)

| # | Layout | Role / when | Behavior (FIXED) | Default font | Accent |
|---|--------|-------------|------------------|--------------|--------|
| 1 | **Title** | opener / hook, showcase | staggered **fragment build**, a strike-wipe through the "cancel" word, payoff word color+scale punch | `title` (the pack's hook font) | accent word |
| 2 | **Caption** (snap) | read-along under the face | ONE word at a time, low ~70%, TIGHT tracking, no overlap, no punctuation (keep apostrophes) | `caption` (the pack's caption font) | keyword words |
| 3 | **Thought bubble** | asides / inner voice, above the head | short aside, entrance animation (Cheeky Bounce / Slide) + mouse-click, silent fade out | `thought` (the pack's thought font) | — |
| 4 | **Line-build + karaoke** | intimate/reflective beats | sentence builds word-by-word REVEALING IN PLACE (≤2 lines), **karaoke highlight on the current word** | `build` (the pack's accent font) | current word |
| 5 | **Full-screen takeover** | punch line / climax | whole phrase, **every word its own line (vertical stack)**, held; **hero variant = biggest**, accent on the key word | `takeover` (the pack's takeover font) | key word (+ hero) |

Universal across all 5: IG-safe zone (x150–930, y270–1620) · lowercase except God/Bible/Lord · captions run
everywhere · named layer (track + clip) · dead-space >3s trimmed · verify in browser before render · SFX stay
native. (Full rules: [`STYLES.md` → Kinetic Type Overlays](STYLES.md).)

**Positioning — from the pack's real `y`, NEVER hand-picked (locked 2026-08-03).** Each element's vertical
place comes from its `y` in `style-packs.json`, mapped to the 1080×1920 canvas as
`center_px = 960 − y × 960` (CapCut normalized, +up). So hook `y≈0.59` → ~394px (**above the head**),
caption `y≈−0.2` → ~1152px (**chest, under the chin**), takeover `y=0` → 960 (**center**). Element SIZE is
`pack size × SIZE_SCALE (6.0)` but **auto-fits down** to stay inside the safe band — a long hook shrinks so
it never fills the screen, a long takeover shrinks so the word-stack never runs off screen. Do NOT type CSS
`top:%`/sizes by hand. **Base template for the baked-MP4 (Route A) path:
`product/build-reel-type.py`** (transcript + pack → transparent overlay); verify against a face frame with
`PREVIEW_BG=<frame.jpg>` before rendering.

---

## STYLE PACK — the swappable tokens

A pack is a named entry in `product/creative-vault/style-packs.json`: its fonts BY ROLE (headline, caption,
accent caption, thought bubble, takeover), each role's size, tracking, line height, case and `y`, and its
`accent_color`. Swapping the pack re-skins every layout at once; the builders turn those into the tokens the
layouts read:

```
fonts:  { caption, build, takeover }                   # from the pack's caption / accent_caption / takeover
faces:  [ (family, file), … ]                          # @font-face for the pack's own font files
color:  { base, accent, dim }                          # white text · the accent color · dimmed/cancelled
size:   { caption, build, takeover, hero }             # from each role's size in the pack
track:  { caption, takeover }                          # from each role's tracking (caption = TIGHT/negative)
```

The accent is this reel's own if one was set, else her saved `default_accent` (`/studio accent`), else the pack's
own `accent_color`. Every font comes from the pack: there is no default typeface.

### Making a new style pack
1. Say **"build my own style pack"** (the `style-pack` skill). It walks the fonts by role and the accent color and
   writes a new named pack the engine can use from then on. Never hand-edit a `STYLE` block to make one.
2. LAYOUTS stay untouched — never edit behavior/positions to restyle.
3. Packs are "themes" (palette + font pairing), decoupled from the layout system. The creator picks one per reel
   and can switch any time.
