# scale: the relative system (Studio never reasons in fixed pixels)

10px on one caption is not 10px of visual weight on another. Different fonts, weights, and footage make the
same number land differently. So Studio sizes and spaces everything RELATIVE to an anchor, the way the engine
already does. This file is how a "bigger hook" or a "tighter caption" means the right thing every time.

## The anchor

**The hook is the anchor.** It is the loudest thing in frame, the size everything else is judged against. Set
the hook first, to the conviction the reel wants, then step everything else DOWN from it in proportion:

- **hook**, the anchor. Loud. Owns the top.
- **takeover / stat**, a step down. Big, but the hook still leads when both are near.
- **caption**, comfortably readable, clearly subordinate. It never competes with the spoken moment.
- **thought / aside**, the quietest text role.

Steps between roles are a **ratio, not a pixel gap** (roughly 1.125 to 1.2 between neighbors is a normal,
readable spread). Judge it by "can you tell the order at a glance," not by the numbers.

## How the engine already does relative sizing (build on this, do not fight it)

Every element's size is **the pack's unit size times a scale**, then **auto-fit down** to stay in the safe
band. It is already relative:

- Pack unit sizes live in `style-packs.json` per element (e.g. takeover 26 to 36 depending on pack).
- The render paths multiply by `SIZE_SCALE` (default 6.0 px per pack unit) to get pixels, then measure and
  **shrink to fit** the safe zone so nothing overflows (`build-reel-type.py` `fit_hook` / `fit_stack` /
  `fit_wrap`). The hook size is measured per pack, not estimated.
- Position is relative too: an element's `y` maps to the frame by **`center_px = 960 - (y x 960)`**
  (`LAYOUT-STANDARDS.md`). y is a fraction of half-height, so it holds its place regardless of font.

**What this means for a Studio command:** you adjust the RELATION (make the hook the clear anchor, give the
caption more room, tighten the leading), and the engine's scale-times-fit machinery renders it safely on each
path. You are never writing a caption pixel size by hand.

## The two relative knobs

Think in two multipliers over the pack's base, the same primitives impeccable uses:

- **scale**, an overall size multiplier on a role's base (a bigger or smaller hook, a bigger caption),
  applied on top of the pack unit, then auto-fit still protects the safe zone.
- **density**, the spacing and line-height feel. Higher density = tighter leading and gaps; lower = more
  breathing room. This is what "line-height that breathes but stays one thought" tunes.

Per-reel framing nudges (`hook_lift_px` / `caption_lift_px`) shift a role up or down for one reel WITHOUT
changing the pack, so a one-off fix never mutates the creator's whole look.

## Define by constraint and intent, never by a fixed number

When you set a standard, phrase it as a target to exercise judgment against:

- Good: "two stacked caption lines breathe enough not to feel cramped, never so airy they read as separate
  thoughts."
- Good: "the hook is unmistakably the loudest thing; the caption is clearly the quiet supporting line."
- Avoid: "line-height 1.15," "caption 42px." Those are outputs of the judgment, not the rule.

The fixed numbers live in exactly one place, the **Verify** list in `craft-floor.md` (the safe zone), because
those are mechanical limits. Everything else is relative and rebuttable.
