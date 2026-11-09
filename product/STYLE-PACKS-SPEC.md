# Style Packs — Single Source of Truth (SPEC)

> The definitive catalog of the launch style packs + the type engine's knobs. If a fact about a pack's fonts,
> colors, sizes, or treatments lives anywhere, it lives here. Generated/verified 2026-08-09.
>
> **Architecture in one line:** THEME is per-pack and distinct (colors + fonts + card recipe); BUILD LOGIC is one
> shared engine (`build-reel-type.py`) that animates + fits everything identically. Tuning a pack = editing config
> (`style-packs.json` + `pack_palettes.py`), never the engine. See `STUDIO-TYPE-GOLD-STANDARDS.md` for the gold-standard
> formulas and the memory `theme-vs-build-architecture`.

## The three launch packs: Editorial · Playful · Butter. Vintage and Minimal are discarded (Minimal was renamed to Butter).

Everything below is the ACTUAL current config (verified against `style-packs.json` + `pack_palettes.py` + files in
`assets/fonts/`). All font files confirmed present.

### 1 · Editorial — green / pink / cream, literary
- **Fonts (BY ROLE — never inherit):** headline/hook `Playfair Display` (PlayfairDisplay-VF.ttf) · caption/single `Poppins` (Poppins-SemiBold.ttf) ·
  **karaoke `Prosecco`** (defaults to `accent_caption`; `karaoke_weight 400` so the script does not faux-bold) · takeover `Prosecco` (Prosecco.ttf, script) · eyebrow/accent_caption `Prosecco` · card-kicker `Poppins` (breakaway label).
- **Palette:** ground `#F2EDE4` oat cream · ink `#1a1a17` near-black body · dark/display `#212c1b` forest green (also the breakaway card ground) · green-deep `#243a21` · green-lite `#3a5a36` · sage `#7A8C6A` · deep-pink `#d27e96` (readable on cream) · light-pink `#ffadbf` (over-footage highlight / accent on the green card).
- **Over-footage keyword** (`accent_color`) = `#ffadbf` light pink (the highlight). **On-cream design-frame text accent** (`HANDS_OFF_ACCENT`) = `#d27e96` deep pink (readable on cream).
- **Well-done tuning:** `eyebrow_scale 1.35 · build_scale 0.8` (karaoke −20%) · `single_scale 0.765` (−23.5%) · `single_tracking −0.02` ·
  karaoke = `Prosecco` (defaults to `accent_caption`, no override) · `karaoke_weight 400` (Prosecco not faux-bold) · `headline_weight 800` (bolder Playfair hook) · `subhead_weight normal` (lighter Prosecco eyebrow).
- **Breakaway (CARD_THEME):** structure `editorial` · GREEN ground `#212c1b` (`dark`) · cream ink (`light`) · light-pink `#ffadbf` accent (kicker/rule/emphasis word) · Poppins label kicker · light-pink hairline rule · script accent word available.
- **Style card (marketing sheet):** CREAM ground, green Playfair title, pink accents (2026-08-10; an all-green-ground sheet was rejected). Distinct from the in-reel breakaway card, which IS green-ground.

### 2 · Playful — brutalist candy blocks
- **Fonts:** headline `Soup Du Jour` (SoupDuJour.ttf) · takeover `Soup Du Jour Hollow` (SoupDuJourHollow.ttf) ·
  captions/single + accent_caption/karaoke + eyebrow `Ugly Dave` (UglyDaveAlternates.otf).
- **Palette:** ground `#F2EDE4` cream · ink `#1C2418` · accent `#F5C518` yellow · muted `#1F8A4C` green · pop2 `#FF6B8A` pink · CANDY = pink/green/orange/yellow.
- **Over-footage keyword** (`accent_color`) = `#F5C518` yellow. **On-cream design-frame text accent** (`HANDS_OFF_ACCENT`) = `#E85A1F` orange
  — DELIBERATE split: yellow can't be read as text on cream, so full-frame/hands-off cards use orange; over footage (white base) the keyword is yellow.
- **Well-done tuning:** `headline_maxh 0.9 · eyebrow_scale 1.5 · caption_scale 1.45` (bigger captions) · `line_height 0.78` · `eyebrow_gap 18` ·
  `text_shadow 0 3px 30px rgba(0,0,0,.55)` · `takeover_white true` · `subhead_weight normal` · `build_scale 1.34` ·
  `karaoke_weight 400` + `single_weight 400` (Ugly Dave not faux-bold) · `hook_maxw 840` (hook pulled narrower — was too wide).
- **Breakaway (CARD_THEME):** structure `block` · PINK ground (`pop2`) · YELLOW candy block (`accent` fill) · ink border + hard 20px offset shadow ·
  ink display · Ugly Dave kicker (rotated, cream).

### 3 · Butter — Mellow palette + BlockFrame type
- **Concept:** "Butter" — a literal stick of butter (soft, cute, buttery). Mellow palette + BlockFrame's Inter/Space-Grotesk type rules + Bloop for cute.
- **Fonts:** headline + takeover `Inter` **Black/900** (Inter-Black.otf) · captions/single + karaoke `Inter` **Medium/500** (Inter-Medium.ttf, static — CapCut was defaulting the VF to "Inter Thin") ·
  eyebrow `Bloop` (Bloop.ttf, cute hand-drawn) · card kicker `Bloop` (accent_caption). Inter is OFL and ships; Bloop
  does NOT ship (its license is unconfirmed): it resolves by name from the creator's CapCut, and a finished video
  uses a bundled stand-in (and says so) until it is there.
- **Palette:** ground/light `#fffdd7` pale-lemon · ink/dark `#317ae1` vivid cobalt · muted `#5c91e6` · accent `#fdc341` marigold · pop2 `#fdc341`.
- **Over-footage keyword + on-frame accent:** `#fdc341` marigold (both).
- **BlockFrame TYPE RULES (applied):** display = **UPPERCASE Inter 900, −0.05em** · captions = **lowercase Inter 500** (the calm) · eyebrow = Bloop (cute).
- **Well-done tuning (current):** `karaoke_weight 500 · single_weight 500` · `build_scale 0.85 · single_scale 0.85` (captions smaller) · `headline_tracking −0.05` (tightened — the tighter CapCut feel was preferred) ·
  `eyebrow_scale 1.35` (bigger Bloop eyebrow) · `subhead_weight normal · subhead_tracking 0` ·
  `hook_color #FBE96B` (clear lemon-butter — the pale `#fffdd7` read MUDDY over footage) · **`subhead_color #ffffff`** (eyebrow WHITE, headline stays butter-yellow) ·
  `head_one_min 80 + hook_maxw 950` (headline forced to ONE line). Picked over a warmer "Summer Love" honey/sky-blue alt.
- **Breakaway (CARD_THEME):** structure `minimal` (→ centered-type branch) · PALE-LEMON ground (`light` #fffdd7) · cobalt ink · UPPERCASE Inter display (`headline_case upper`, `−0.03em`) ·
  italic key word (`emphasis_italic`) · Bloop kicker BOLD (`kicker_weight 800`) · cobalt hairline rule.

## Engine knob reference (tune packs without touching the engine)

All read from a pack's `welldone` block (`style-packs.json`) unless noted. Defaults keep legacy behavior.

**Hook:**
- `hook_color` — rendered hook text color (default `#fff`). Butter = `#FBE96B`.
- `headline_weight` — CSS weight for the hook headline (default none). Editorial = `800`.
- `hook_maxw` — hook width cap in px (default `HOOK_W`=960). Lower = narrower / into the safe zone (SAFE_W=780). Playful 840, Butter 950.
- `headline_tracking` — em letter-spacing on the split headline. `headline_maxh`, `eyebrow_scale`, `eyebrow_gap`, `line_height` tune the split fit.
- Split hook: a long hook auto-splits into big headline + small eyebrow; the headline PREFERS ONE LINE (`_HEAD_ONE_MIN`=100), else wraps balanced to 2.

**Eyebrow / subhead:** `subhead_source` (which element font, default `caption`) · `subhead_font_file`/`subhead_font_name` (override, e.g. Bloop) ·
`subhead_weight` (`normal` for hand-drawn faces) · `subhead_tracking` (em, e.g. 0.08 for Space Grotesk labels).

**Captions (karaoke vs single are independent):**
- `caption_scale` (base) · `build_scale` (karaoke size) · `single_scale` (single size) — ABSOLUTE mults; for a base-1.45 pack "−15%" = 1.45×0.85=1.232.
- `karaoke_weight` / `single_weight` (default `600`; use `400`/`500` for single-weight faces so they don't faux-bold).
- `single_tracking` (em) · `karaoke_font_file`/`karaoke_font_name` (karaoke font override, so karaoke differs from the kicker — Butter: Inter Medium karaoke / Bloop kicker; **Editorial: Prosecco karaoke (defaults to `accent_caption`) — a pack MAY use its accent/script face for karaoke**).
- **Caption placement (cross-pack LOCK):** captions sit UNDER THE CHIN (lower third), never on/over it; over-footage captions seat below the chin with a NEGATIVE `caption_lift_px` (a positive lift rides up onto the face). Every pack.
- **Karaoke font (cross-pack):** karaoke is a deliberate per-pack choice — `karaoke_font_file` if set, else defaults to that pack's `accent_caption`. Editorial=Prosecco (script), Playful=Ugly Dave, Butter=Inter Medium.
- **Clean style-shift handoff (automatic):** each caption segment's last clip is clamped to the next segment's first-word time −0.04s, so karaoke↔single never overlap.

**Takeover:** `takeover_scale` · `takeover_white` (all-white, no accent keyword).

**Breakaway card (CARD_THEME in `pack_palettes.py`, per-plan overridable):**
- `structure` (`editorial` centered-type+rule / `block` candy-block+shadow / `minimal` → centered-type) ·
  `ground`/`ink`/`accent` (role names) · `kicker_role` (`kicker`→accent_caption font, `label`→caption) · `kicker_color` · `kicker_weight` (bolder kicker) ·
  `rule`/`rule_color` · `headline_tracking` · `headline_case` (`upper`) · `emphasis_italic` (italic key word) or color · `block_fill`/`block_border`/`block_shadow`.
- Per-breakaway plan overrides: `kicker_font_file` (e.g. compare Bloop vs Space Grotesk), `ground`/`ink`/`kicker`, `lines`, `emphasis`, `size`.
- **Motion (shared):** dissolve in/out + push-in (scale 1.06→1) + staggered `back.out` reveals + accent-bar wipe + emphasis pop. Speed = `_BK_FADE` (engine, currently **0.16**). Captions yield the whole window (`_BK_GUARD = _BK_FADE + 0.12`).

## Fast build / preview workflow (efficiency)

The HyperFrames render is the cost (~55s for a full reel). To iterate fast WITHOUT quality loss:
1. `DUR_OVERRIDE=<sec>` env caps the rendered length for preview (e.g. 12.5–15s) → ~3–4× faster. **Never ship a DUR_OVERRIDE'd render.**
2. One MIX render shows every treatment at once: set `caption_mode:"build"` + a `caption_treatments:[{text,mode:"single"}]` line + a `breakaways:[...]` beat + `hook_long`/`hook_emphasis` → hook → karaoke → single → animated breakaway in one clip.
3. Verify by extracting frames with ffmpeg (`-ss T -frames:v 1`) and viewing — don't re-watch full clips.
4. Command shape: `PRODUCER_BROWSER_GPU_MODE=hardware DUR_OVERRIDE=15 JOB=<job> STYLE_PACK=<Pack> HOOK_SPLIT=1 python3 product/build-reel-type.py` →
   `python3 product/reel_render.py render projects/<job>/hf-reel-type-<pack> -o <out.mov>` → ffmpeg overlay composite over the base cut.
5. `pack_palettes.py` is imported by BOTH the render engine and the design.md generator — one edit, both stay in sync.

## Env / invocation
`JOB` (job folder) · `STYLE_PACK` (Editorial|Playful|Butter) · `HOOK_SPLIT=1` (long-hook → headline+eyebrow) ·
`CAPTION_MODE` (build|single, else from plan) · `DUR_OVERRIDE` (preview) · `LAYER` (hook|front, for behind-head cutout) ·
`PRODUCER_BROWSER_GPU_MODE=hardware` (mac HW encode). Plan = `projects/<job>/caption-plan.json`.
