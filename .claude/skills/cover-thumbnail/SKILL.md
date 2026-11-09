---
name: cover-thumbnail
description: Make a reel COVER / thumbnail — the still that shows in the grid and as the reel's poster frame. Use when the creator says "make a thumbnail", "make a cover", "pick a cover frame", "cover photo", "best frame for the cover", "thumbnail for this reel", or asks which frame to use as the cover. Pulls the best candidate frames FROM her own footage by expression (eyes open, facing camera, sharp, alive), shows a numbered set to pick from, THEN adds the title. Phased — never pick the frame AND the title in one shot.
---

# Cover / thumbnail — the best frame from her footage, then a title

A reel cover is one **still pulled from her own footage** with a short title on top. It's the frame that
shows in the Instagram grid, and the poster frame for the reel. This is **phased on purpose** — you never pick the
frame and slap a title on in one shot. Options first, she picks, then the title, she picks, then build.
(Same rule as `product/FLOW.md` → "Cover / thumbnail".)

> This is the reel COVER: the poster frame that shows in the grid. It is chosen from the finished reel
> itself, so there is nothing to collect or prepare beforehand.

## Her snaps come first
If she snapped frames in the visual editor (`projects/<job>/thumbnails/snaps/`, indexed in `snaps.json` with
each snap's place in the reel and the one she **starred as her cover**), start there: a starred snap IS the
frame (skip Phase 1 and say which one you're using); unstarred snaps join the numbered set ahead of the
picker's. They are full-quality stills from her original clip, so use the file as it is. "Make a carousel from
my snaps" uses the same files, in her reel order (`at`).

## Phase 1 — photo options (the tedious part, automated)
Run the picker on the finished reel:

```
uv run workflows/cover-frame.py projects/<job>/outputs/<job>.final.mp4 --n 6
```

It samples the reel densely, detects her face (OpenCV YuNet — the model already bundled), **scores every
frame** on: face confidence, size, sharpness (kills motion-blur / mid-word frames), facing (eyes level +
nose centered = looking at camera), eyes-open (blink filter — a heuristic, honest), and expression
(a little life beats a flat resting face). It throws out the blurry / blinking / turned-away frames and
writes the top candidates as **clean full-frame JPEGs (NO title)** to
`projects/<job>/thumbnails/candidates/cover-01.jpg …` plus `cover-scores.json`.

- Show her the **numbered set** (the clean stills, no title) and let her pick. ⏸ **She picks the frame.**
- If she wants to see them side by side, add `--contact sheet.jpg` for a labeled contact sheet.
- **Eyes-open / expression are heuristics, not truth** — the picker gets you a clean shortlist fast so
  she isn't scrubbing the whole reel to find a good frame; the final call is always hers.
- Faceless VO reel / heavy b-roll → it says "no clean face frames" and writes nothing. That's correct;
  pick a cover by eye or use a strong b-roll still.

## Phase 2 — title / hook options
Only after she's picked the frame. Short, punchy, curiosity — a different job than the spoken hook (don't
mirror the audio). Tie into anything already visible in the frame (a whiteboard, a number, her hands).
Offer a few. ⏸ **She picks the title.**

## Phase 3 — build the cover
Build the title onto the chosen frame:
- Title in the pack's headline font + accent color, straight from her `brand-kit.md` / chosen style pack
  (e.g. a highlight-bar / marker-note treatment if that's her look).
- Anchor the title **TOP (above your head) or center — NEVER bottom** (the grid and UI crop the bottom).
- One accent word. Add a scrim or highlight bar behind the text for legibility.
- The frame is already a still, so draw the title onto it with Pillow, in the pack's own font file (the
  engine's ffmpeg is built without a text filter). Save the cover as
  `projects/<job>/thumbnails/<job>-cover.jpg`.

## Rules
- **Phased, always.** Frame options ⏸ → title options ⏸ → build. Never collapse it.
- **Her footage only.** The cover frame comes from her own reel, never a generated or stock image.
- **Title placement TOP or CENTER, never bottom.** One accent word. Legible over the frame.
- She may name which draft/clip to pull the frame from — honor it, point the picker at that file.
