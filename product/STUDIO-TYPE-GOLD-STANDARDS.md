# Studio type gold standards — well-done + CapCut, per pack

The locked findings from the Butter calibration (originally run as the Minimal pack) + the per-pack builds (2026-08-08). **Two independent
outputs, each with its own gold standard; the PACK holds the shared typeset rules + color that both read.**
Reference reel = `studio-calib` (`projects/studio-calib/`), the long split hook "you can love being home /
and miss who you used to be" + "a phrase from your own transcript" takeover.

## Cross-pack rules (true for EVERY pack — stated ONCE here, referenced from each pack)
These are role rules, not taste — and they are the exact tangle that shipped wrong renders. They hold
identically across Editorial, Playful, and Butter.
- **Captions sit UNDER THE CHIN (lower third) — never on / over the chin.** Over-footage captions seat below
  the chin with a NEGATIVE `caption_lift_px` (a positive lift would ride up onto the face). Below-chin is the
  locked caption home in every pack; the safe zone still holds.
- **Karaoke font is a DELIBERATE per-pack choice** — set via each pack's `karaoke_font_file`, else it defaults
  to that pack's `accent_caption`. It is NOT automatically the caption(single) font. Per pack:
  **Editorial karaoke = Prosecco** (its script accent face — a locked call; `karaoke_weight 400` so the script does
  not faux-bold), **Playful karaoke = Ugly Dave**, **Butter karaoke = Inter Medium** (the static
  `Inter-Medium.ttf`, NOT the variable Inter-VF).
- **Fonts are assigned strictly BY ROLE** — headline · takeover · caption (single) · karaoke · eyebrow/accent ·
  card-kicker. **Never assume a role inherits another role's font.** Karaoke ≠ accent; single ≠ karaoke by
  default; takeover ≠ headline.
- **Showcase / demo captions name the STYLE** ("this is a karaoke caption"), they are NOT the creator's
  transcribed speech. Demo frames label the treatment; real jobs caption the real transcript.

## The split-hook structure (shared, `hooksplit.py`)
Long hook → two length-balanced halves at a natural break (reading order fixed: first half always on top).
Emphasized half = the loud headline; the other = the quiet line — an EYEBROW above (emphasis on 2nd half) or
a SUBHEAD below (emphasis on 1st). Which half is emphasized is decided in the style plan.

> **Cross-reference for every well-done judgment: [`IMPECCABLE-TYPE-PRINCIPLES.md`](IMPECCABLE-TYPE-PRINCIPLES.md).**
> The impeccable text/layout/readability/placement guidelines (typeset · layout · adapt · craft-floor), pulled
> and adapted to the reel context. Since the well-done render is self-verifiable, every sizing/placement/
> hierarchy call is checked against it from the rendered frame before it's called done.

## Long headline → ASK the creator which of 3 routes (never auto-shrink-mangle)
When a single headline is long enough that it can't sit as a balanced ≤2 lines without orphaning or spilling
past the top safe band (worst in the big-face packs — Playful 31 native, or Butter / Inter-Black
uppercase — because the identical wrap runs against a fixed box at that pack's native size), that is NOT a bug
to fix by shrinking. **Stop and ASK which route they want:**
1. **Headline + subhead split** — recast the long hook into the split prefab (headline ≤2 lines + a quiet
   supporting line). All the packs have this prefab.
2. **Shorten the hook** — trim the copy so it fits one clean ≤2-line headline.
3. **Full-bleed over the face (intentional aesthetic)** — let the big headline run down over her face on
   purpose, the same way the full-screen hollow takeover does. Covering the face is a legit CHOICE here, not a
   defect — it just has to be chosen, never defaulted into silently.
Applies to BOTH outputs (well-done + CapCut). Do not auto-pick; surface the 3 and let the creator choose.
Locked 2026-08-08.

## WELL-DONE gold standard (baked MP4, `build-reel-type.py`)
 Core: **measure the real font, never estimate**; headline is the anchor,
sized BIG and balance-wrapped to ≤2 lines with **no orphan words**; everything sizes DOWN from it; **one tight
line-height** (`TIGHT_LH` 0.92, per-pack override); captions below the chin; safe zone. **Layout beats the
exact number:** the eyebrow/subhead reads as ONE line, sizing down within a range to fill the safe width rather
than stacking (impeccable — a supporting line shouldn't wrap); packs whose eyebrow already fits are untouched.

### Per-pack well-done tuning (the `welldone` block in `style-packs.json`)
Fonts render at different visual sizes, so each pack nudges. Knobs (all optional, default = Butter):
`headline_maxh` · `eyebrow_scale` · `caption_scale` · `line_height` · `headline_tracking` · `eyebrow_gap` ·
`text_shadow` · `takeover_scale` (fraction of safe width the takeover fills) · `takeover_white` ·
`subhead_weight`.

| Pack | Eyebrow font | Accent | Notable well-done tuning |
|---|---|---|---|
| **Butter** | Bloop (`subhead_font_file`) | #fdc341 marigold | `headline_tracking -0.05`, `single_tracking -0.02` (one value drives single + karaoke captions), `build_scale`/`single_scale 0.85`, `eyebrow_scale 1.35`, `hook_color #FBE96B`, `subhead_color #ffffff` (white eyebrow; headline stays butter-yellow), `head_one_min 80`, `hook_maxw 950` |
| **Editorial** | Prosecco (accent) | #ffadbf light-pink (over-footage highlight); #d27e96 deep-pink on cream | `eyebrow_scale 1.35` (script reads small); **karaoke = Prosecco** (its script accent face; `karaoke_weight 400`) |
| **Playful** | **Ugly Dave** (`subhead_font_file`) | #F5C518 mustard | solid Soup Du Jour hook; HOLLOW = takeover only (all white, maxed to safe width); `line_height .78` (Soup Du Jour's line box is tall — 0.9 still drifts, the two headline lines must sit as one tight block) + `eyebrow_gap 18` (big font bleeds); softer `text_shadow`; `subhead_weight normal` (no faux-bold on Ugly Dave) |

### Pack-level rules (shared — carry to BOTH engines)
- `subhead_source` (which element the eyebrow uses) + optional `subhead_font_file` (any font, e.g. Ugly Dave).
- `accent_color` (the headline/highlight color).
- Font-role assignment (Playful: headline = solid Soup Du Jour, takeover = hollow Soup Du Jour — HOLLOW is
  takeover-only, large, ONE word per line, never a hook/sentence).
- **Font-family collision:** two variants sharing a display name (Soup Du Jour solid + hollow) must be keyed
  by FILE, not name, or the loader collides them (the takeover fell back to solid). Fixed in `face()`.

## CAPCUT gold standard (raw/editable, `hooksplit.hook_spec` → `studio_calib_draft.py`)
 Core: **native pack sizes + the 720 box, let CapCut auto-wrap** (do NOT inject
the baked engine's big-size/line-break logic — CapCut units are far larger and explode). Reads the SAME
pack-level rules (subhead font, accent color, font roles) so each pack's fonts + accents (Editorial Prosecco
+ pink, Playful Ugly Dave + yellow/mustard, Butter Bloop + marigold) all carry over. Deterministic + repeatable; only limitation is I can't self-verify CapCut's render,
so it needs one open per pack.

## Status (2026-08-08) — LOCKED
> **Launch reconcile (2026-08-09):** launch packs are now **Editorial · Playful · Butter**. Vintage was cut
> from the launch (its calibration notes below are historical only). **Butter = the former Minimal, re-tuned**
> (new Inter Black type + pale-lemon/cobalt palette), so any cell locked under "Minimal" predates the Butter
> refinement — re-confirm against the current Butter tuning.
- **Well-done: Editorial · Playful · Butter — all LOCKED.** Passed a final test on brand-new hook +
  subhead + caption content with zero hand-tuning (the gold standard generalizes, not memorized to one hook).
- **CapCut: Editorial · Playful LOCKED (Editorial dialed 2026-08-08; creator doing one final confirming pass); Butter re-tuned — its CapCut still rides base defaults + `hook_color`, confirm on open.** Playful confirmed perfect as-built. **Editorial was NOT actually dialed** — it
  was the only pack shipping with no `capcut` block, riding base defaults (headline 20), so on the split its
  small narrow headline got out-widthed by the one-line Prosecco supporting line. Editorial `capcut` block dialed
  from the creator's Text-panel screenshots: **split headline** Playfair 28, **single headline** Playfair 22
  (the single is the whole hook so it wants to be smaller than the 28 split-half), both **Character −1
  (letter_spacing −0.06) / Line −6 (line_spacing −0.27)** pink; **subhead** Prosecco **11 / Char 0 / Line 0**
  white. Block: `{headline_size 28, single_headline_size 22, headline_tracking −0.06, headline_line_spacing
  −0.27, subhead_size 11}`. **Unit-mapping note (learned the hard way):** CapCut's "Line" field ≈ line_spacing
  × ~22, so line_spacing −0.18 shows as Line −4, and **−0.27 → Line −6** (my first bake used −0.18 thinking it
  round-tripped to −6 — it didn't; the −6 in the first screenshot was a manual edit). The single-headline path
  (studio_calib base `T()`) now pulls the same capcut headline_tracking + headline_line_spacing as the split so
  they can't drift; single size via `single_headline_size` (fallback native), kept OFF the shared native size
  that well-done's eyebrow ratio reads. Pending creator confirm that Line now reads −6. (Prior "all four locked"
  was an overclaim; corrected 2026-08-08.)
- **Per-pack knobs** (all saved in `style-packs.json`): `welldone` block (scale/leading/shadow/takeover) +
  `capcut` block (headline_size, headline_tracking, headline_line_spacing, subhead_size, eyebrow_lift,
  caption_size). CapCut tuning method: **screenshot the CapCut Text panel** → read exact size/Character/Line →
  set the number (the creator can't-see-canvas bridge; now a taught course move, script item 8).
- `vibe` = impeccable's **delight** (identify the opportune enhancement per content, act in context);
  `vibe.md` rewritten to match.
