---
name: chin-lock
description: "Keep captions (or any on-screen element) a set distance UNDER the creator's chin, measured frame by frame so it follows her when she moves. Use when she says: chin lock, lock it under my chin, keep the captions under my chin, follow my chin, captions X px under my chin, the captions should move with me. OFF BY DEFAULT: only when the creator asks for it by name. Never turn it on yourself because she moves in a shot. Rendered routes only: on the CapCut-editable route she places text in CapCut."
---

# Chin lock: captions that stay under her chin

> **Off by default. She turns it on.** Never add chin lock to a reel she did not ask it for, even on a shot where
> she moves. The normal caption placement (one measured spot under her chin) is the default; chin lock, which
> moves the captions with her, runs only when she asks for it.

A caption placed from one measurement is right only while she holds still. When she moves, a fixed spot ends up
on her face or far below her. Chin lock reads her chin on EVERY frame of the caption's window with the same face
model subject-zones uses, smooths it, and gives the element's top edge per frame: chin + offset.

## Run it

```bash
uv run product/chin_lock.py projects/<job>/outputs/<job>.mp4 --from <t0> --to <t1> --offset <px>
```

- `--from / --to`: the seconds on the cut when THAT caption (or chunk) is on screen. Lock each caption chunk over
  its own window, never over the whole reel: she can be in two very different places within one line.
- `--offset`: px between her chin and the TOP of the caption's letters. The creator's number wins; if she has not
  given one, 40.
- It prints `hold` (she stayed within 12px: one steady position, placed under the LOWEST her chin got) or `follow`
  (per-frame keys, 3-frame smoothed, so the caption glides with her).
- `--json keys.json` saves the keys; `--gsap "#sel" --comp-start <comp start on the cut> --box-offset <px>` prints
  ready-made `tl.set(sel,{top:…},t)` lines for a HyperFrames composition. `--box-offset` converts "top of the
  letters" to the element's CSS top (e.g. a box whose text baseline sits 108px below its top, with 53px ink above
  the baseline, is `--box-offset -55`).

## Inside a caption build

For phrase captions built by `product/build-reel-type.py`, set `"caption_chin_lock": {"offset": <px>}` in the
job's `caption-plan.json`, only when she asked for chin lock. The build measures every phrase's own window in one batch run (`--windows`), places each
phrase by the top of its tallest letter (the keyword face counts when a word can switch to it) and makes it follow
or hold on its own. Render that layer with `reel_render.py ... --no-subject`: the subject check compares against one
box covering everywhere she appears across the whole take, so a caption correctly under her chin in one shot can
fall inside that box from another.

## Rules

- **Measure, never type the number.** A chin position is always read off the footage for the caption's own window.
- **Hold when she is still.** Do not add motion she is not making; `hold` is the default for a still take.
- **Taller accent words count.** When a word can switch to a bigger face (a serif accent, a karaoke spotlight),
  measure the offset to the TALLEST version's ink so the gap holds when it flips.
- **Never over her face.** If no face is found anywhere in the window, the tool stops: place that one by hand.
- Rendered routes only. The CapCut-editable route has the creator place text in CapCut.
