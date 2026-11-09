# Short-form layout sheet (9:16 reels)

A 9:16 reel changes two things, where graphics sit and where captions sit, and nothing else. The road
itself is the phase table in [CLAUDE.md](../CLAUDE.md): inbox → job, rough cut, creative plan, one build pass,
finish, export.

- **Frame:** 9:16 vertical, always **1080 × 1920**.
- **Destinations:** Instagram Reels, TikTok and YouTube Shorts, all three from one edit.
- **Length:** whatever is left once every line has earned its place (the `rough-cut` skill's rule). Most of
  her reels land between about 45 seconds and 2 minutes, and that is a result, never a target: graphics and
  captions never stretch a reel to a length.

---

## The safe box: the one layout rule never to break

**The top 270 px and bottom 300 px hold NO key visuals, only background or filler.** The face, the captions
and every key visual (graphics, hero text, numbers, logos, hook cards) must sit **inside the safe box: y
`270 → 1620`**. The two bands may carry background, grid, glow or B-roll bleed, nothing the viewer actually
needs, because the app draws its own header, buttons and caption text over them.

| Band | Size | What covers it |
|------|------|----------------|
| **Top** | **270 px** | status bar / platform header (Reels reserves 14% = 269 px) |
| **Bottom** | **300 px** | caption UI, username, audio tag, CTA, progress bar |

**Where the numbers come from:** `product/safe_zones.py`, and the engine CHECKS every placement against them
at build time, so never hardcode a band again. The top is the strictest band across Reels, TikTok and Shorts
(Meta reserves the **top 14% and bottom 20%** of a Reel). The bottom 300 is the creator's explicit, locked
call, looser than every platform's published band; `violations(..., platform="reels")` still checks one
platform's real band when asked. Per platform: Reels `269 → 1536` · TikTok `260 → 1440` · Shorts
`180 → 1540`. TikTok's bottom is heavier still, and it adds a right-hand action rail: keep wide elements left
of x`900`, where TikTok and Reels stack their action buttons.

**Why it is measured rather than eyeballed:** the render, the preview and CapCut all show the frame with
nothing on top of it. The app's own header and buttons only appear on her phone, once the reel is posted, so
the build checks every placement against the numbers instead of trusting how the frame looks.

Inside the box: the hook card sits inside its top, graphics sit in the open space around her, and the face is
framed inside it.

---

## Which look: the register points the way

A short-form talking head takes one of two looks. Both start from the same rough cut, full frame, and differ only
in the creative plan. The register usually settles it: **teaching** carries graphics through the reel, **Clean
Captions** is the trimmed-back look, right for a confessional reel. If it doesn't, ask one line: *"graphics
through it, or just the hook card?"*

---

## Teaching, graphics through it (graphics-plan's `reel-teaching`)

**Her full-frame talking head, with graphics in the open space around her.** Most teaching beats get a graphic:
the hook, every concrete claim, every stat, the payoff.

- **Reframe to 9:16:** crop to 1080×1920 if the footage isn't already.
- **Graphics (creative plan + build):** plan first with `graphics-plan` (which lines get a graphic, which stay plain), then build
  in HyperFrames in her style pack. Every graphic sits in the open space around her, read from this job's
  `subject-zones.json` (`workflows/subject-zones.py`), never over her face, and inside the safe box above.
  A beat that wants motion with no real footage behind it can be generated as a clip first, then composited like
  any part.
- **Captions:** through her style pack or CapCut's Auto Captions, in their own band. Feed the derived
  transcript; never re-transcribe.

---

## Clean Captions, the trimmed-back look (graphics-plan's `reel-clean`)

**Her full-frame talking head with a single hook card at the start, then nothing over her but captions.**
The lightest finish.
A single reel captions through her style pack or CapCut's Auto Captions (`product/FLOW.md`). The burn-in
builder in [`presets/clean-captions-style.md`](../presets/clean-captions-style.md) is what `pull-reels` uses when
asked for `--captions clean`, and what it falls back to for any clip whose style-pack captions (its default,
in beta) cannot finish.

- **Reframe to 9:16:** crop to 1080×1920 if the footage isn't already.
- **Graphics (creative plan + build):** a single **hook card** (locked look: `presets/clean-captions-style.md`) pinned to
  the **top** of the safe zone. It opens the reel and comes down once the hook has done its job (that file
  says exactly when); from there on it is her footage and the captions. No other graphics, no B-roll, no
  lower-thirds.
- **Captions:** **low, under the face**, inside the caption-safe band (locked look:
  `presets/clean-captions-style.md`). Feed the derived transcript; never re-transcribe.

---

## The engine adds no pitch

Any ask belongs to her script, said in her own words; the captions carry it as she said it. The engine adds
none of its own: no follow prompt, no link callout, no closing pitch card (CLAUDE.md, "What ends up on
screen").
