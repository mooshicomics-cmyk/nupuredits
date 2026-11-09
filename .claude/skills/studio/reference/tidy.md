# tidy: layout, spacing, and placement

Load `craft-floor.md` and `scale.md` first. `tidy` is the verb that makes the frame feel composed: every
element in its band, spacing with rhythm, nothing crowding the speaker. It holds the safe zone so text is
readable and never on the face.

## What it holds

- **Placement in the right band.** The hook and thoughts ride ABOVE the head. The captions ride UNDER the
  chin. A takeover sits centered. If an element drifts out of its band, `tidy` seats it back (per-reel with
  `hook_lift_px` / `caption_lift_px`, without changing the pack).
- **The safe zone, held.** Nothing readable in the top band, the caption band near the bottom (hold above
  y 1620, see the floor), or the right icon rail. This is the hard rule, not a preference.
- **Spacing with rhythm, not uniform gaps.** Group what belongs together, separate what does not, and let the
  intervals contrast (a little tighter inside a group, more generous between groups). More space above a
  heading than below it. Even spacing everywhere reads flat; deliberate contrast reads composed.

## How to think (the squint test)

Look at a held frame with the detail blurred. Can you still read the structure: one clear top element, one
clear caption line, the face unblocked? If two things fight for the same spot, or an element hugs the face or
an edge, that is what `tidy` fixes. Diagnose the structure before moving any single box.

## The moves

- **Reseat to the band.** Put each role back on its y (hook above head, caption under chin), using the pack's
  y and the per-reel lift, never a hand-picked pixel. The head position is measured (`workflows/head-framing.py`),
  so anchor to it rather than guessing where the head is.
- **Open or close the rhythm.** Adjust the spacing between roles so the grouping reads. This is the `density`
  idea from `scale.md`, applied to gaps rather than leading.
- **Pull anything off the face or the edges** back inside the safe zone. If the creator wants an element
  somewhere the floor forbids, say so and offer the nearest placement that clears it.

## Per path (from `fidelity.md`)

- Engine text (hook / thought / takeover): placement is exact on all three paths.
- Line captions: exact on MP4/medium. On raw they are native Auto Captions, so `tidy` hands over the exact
  in-app nudge (drag the caption line to just under the chin, keep it inside the safe band) rather than
  claiming to have moved them.

## Finish

Hand off to **glow** for the final read.
