# font: text hierarchy and sizing (the #1 recurring fix)

Load `craft-floor.md` and `scale.md` first. `font` is the verb that makes the text right the first time: the
hook is the loudest thing and never too tall, nothing runs off screen, and the caption is readable but never
competes with the spoken moment. It is the fix the creator was tired of typing.

## What it holds

Three things go wrong most, and `font` owns all three:

1. **Hook too tall.** The hook eats too much vertical room, crowds the head, or the leading is so loose the
   lines drift apart. Fix: bring the hook back to the anchor size the frame wants and tighten the leading to
   "one thought," see `scale.md`.
2. **Hook runs off screen.** A long hook clips the safe-zone edge. Fix: it auto-fits DOWN and wraps on
   engine-injected breaks so it lands inside x 150 to 930. Never let it reach the edge.
3. **Caption competing or mispositioned.** The caption is as loud as the hook, or drifts off its band, or
   overlaps the face. Fix: size it clearly below the hook, hold it in its band under the chin, keep it a
   comfortable measure.

## How to think (the glance test)

Before changing anything, look at one held frame the way a scroller will: with the detail blurred, can you
still tell the order, hook first, caption second? If two roles read as equal weight, the hierarchy is broken
and that is the real fix, not nudging a number. Decide the RELATION first (see `scale.md`), then let the
engine's size-times-fit machinery render it.

## The moves (what to actually turn)

Work in the pack's relative terms, never a hand-set caption pixel:

- **Reset the anchor.** Set the hook to the size the reel wants, then let everything step down from it. The
  hook size is measured per pack, not estimated (`build-reel-type.py`), so trust the measurement and adjust
  the intent.
- **Tighten or open the leading** toward the "breathe but stay one thought" target. On MP4/medium this is
  authored directly. On raw it is set for thoughts today; for other roles, advise the creator or wire the
  per-element line-spacing in finalize if the reel needs it.
- **Fix overflow by fitting down and wrapping**, never by trusting CapCut to reflow (it does not, it needs the
  break injected, `capcut_text.py`).
- **Reseat a role in its band** with `hook_lift_px` / `caption_lift_px` for this one reel, without touching the
  pack, if the framing (head height) calls for it.

## Per path (from `fidelity.md`)

- **Hook / thought / takeover:** controllable on all three paths. Size and position land exactly on every
  path; full line-height on MP4/medium; size + position + wrap on raw.
- **Line captions:** exact on MP4/medium. On raw they are the creator's native Auto Captions, so `font` hands
  over the exact in-app move (Bold Text popup, size, nudge just under the chin, stay in the safe band) instead
  of claiming to have sized them.

## Hard floor (never break, from `craft-floor.md`)

Text inside x 150 to 930, y 270 to 1620. Never on the face. Nothing off screen. If the creator wants a hook so
big it would clip or cover the face, say so and offer the largest size that clears the floor.

## Finish

Hand off to **glow** for the final read, so any last off-by-a-little in spacing or alignment is caught before
export.
