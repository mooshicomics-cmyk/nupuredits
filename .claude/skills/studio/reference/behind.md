# behind: put an element BEHIND the subject (text-behind-head / gif-behind)

Load `craft-floor.md` first. `behind` renders the reel so a chosen element — the **hook** by default, or a
**gif**, doodle, or graphic — sits BEHIND the creator, with her silhouette occluding it. The premium
"text-behind-subject" reel look. The hook stays in its NORMAL spot (readable); she just passes in front of it
where they overlap.

## How to invoke
`/studio behind` (defaults to the hook) · `/studio behind hook` · later: `/studio behind gif`.

## How it works (`product/studio_behind.sh`)
Three layers, stacked in z-order **footage → BEHIND element → subject cutout → front elements**:
1. **Matte the subject** — `python3 product/bg_remove.py fg.mp4 cutout.webm` (HyperFrames' remove-background at
   the pin, u2net human seg, ~0.25s/frame, one pass per reel; cached). Never run remove-background by hand:
   without its output folder it waits forever, and `bg_remove.py` makes the folder and stops a stalled run.
2. **Render the overlay in two halves** via `build-reel-type.py` with `LAYER=hook` (behind) and `LAYER=front`
   (captions/takeover/vibe, in front). This is why the layer filter exists.
3. **Composite** footage → hook overlay → cutout → front overlay.

## TWO ffmpeg alpha gotchas (both cost real debugging — do NOT lose these)
- **ProRes 4444 overlay (`yuva444p12le`):** ffmpeg's default `overlay` mishandles the 12-bit alpha over 8-bit
  footage and the layer vanishes. Use **`overlay=0:0:format=auto`** on every overlay.
- **VP9 webm alpha (the cutout):** ffmpeg's default `vp9` decoder **silently drops the alpha channel**, so the
  cutout composites fully opaque and paints over everything behind it. Force **`-c:v libvpx-vp9`** on the
  `cutout.webm` input. (This was the "hook disappeared" bug — the opaque cutout was covering it with
  footage-colored pixels, so it looked like plain footage.)

## Placement / floor
- Keep the hook in its normal band (readable). The occlusion happens naturally where she overlaps it — best on
  framing where her head/shoulders reach into the hook, or when she leans up.
- **A gif behind the head is the SAME pipeline** — the gif is just the BEHIND layer instead of (or with) the
  hook. Gifs are allowed to cover her face (2026-08-08); the hook is not.

## Per path (fidelity)
Well-done / medium: baked exactly. Raw CapCut: the cutout + behind element ship as imported overlay clips
(CapCut can layer them), so it works on raw too, just not as re-editable native text.

## Finish
Hand off to **glow**.
