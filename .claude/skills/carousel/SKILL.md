---
name: carousel
description: "The Carousel Kit. Make an Instagram carousel in her style pack, from an idea, a script, or one of her reels. Triggers: make a carousel, turn this reel into a carousel, carousel post, swipe post."
---

# Carousel Kit

**From the visual editor:** she pressed **Make a carousel** under Your snaps on her page, so the newest `projects/*/review/kit-request.json` (`ls -t projects/*/review/kit-request.json | head -1`) names the reel, the snaps she ticked (an empty list = no snaps, the engine picks her best stills) and any photos she added from her favorites, her inbox or her computer (`photos`). Make it from that reel; `carousel.py frames <job> --from <reel>` uses exactly her ticked frames, her starred cover first, then her photos (`photo-NN`), then the engine's own picks for whatever room is left, and marks the request used. Her photos are hers to feature: never drop one to make room for an engine pick.

Words first, then design. Layout, photo placement, export and the editor are all done by
`workflows/carousel/carousel.py`; never write slide HTML by hand and never open the slide PNGs one by one.
Run it as `uv run workflows/carousel/carousel.py <cmd> <job>`. The job folder is `projects/<job>/carousel/`.

## Flow (chat only)

1. **Start.** An idea, a Script Desk script / hook library entry (only if the Script Kit is installed;
   never block without it), or a reel: `carousel.py words <job>` prints that reel's transcript.
   New job name: short kebab-case from the topic + `-carousel` (a story from the same reel is `-story`, so they never collide).
2. **Goal.** Ask one question at a time, only what you can't fill from `brand-kit.md` (and its "What you sell" section) or the Script Kit:
   who it's for, and how it should end (closer type below).
3. **Script.** Send it in chat: each slide's role, eyebrow, headline, support line, then the caption.
   She approves or says what to change. Nothing is designed yet.
4. **"Ready for me to design it?"** (or she says "design it").
5. **Look.** "Photo based, graphic based, or a mix?" Photo/mix: photos go in `inbox/` like footage
   (HEIC is fine), then `carousel.py photos <job> [files]`. It prints each photo's new name: use those
   names in plan.json. A proof screenshot goes through this step too.
   **From a reel with no photos:** `carousel.py frames <job> --from <reel job>` pulls her best stills from the reel
   (sharp, face in frame, spread out) into photos/ as frame-01.jpg …; use those names. **Her snaps go first:**
   frames she grabbed with Snap in the visual editor come in as snap-01.jpg … (her starred cover first, then reel
   order), full quality; the engine's own picks only fill the rest. Use her starred snap for the hook slide.
6. Write `plan.json`, then `carousel.py build <job> --pack <her pack> --look <photo|graphic|mix>`
   and `carousel.py render <job>`. Show **only** `beat-sheet.jpg`, plus any `check:` lines in plain words.
   A `font:` line means her pack font isn't on this computer yet and a free stand-in was used: tell her
   which one, and that adding it in CapCut fixes it on the next build. Slides are JPG (`--png` if she asks).
7. **"Does this look good? Export as is, or open it in the editor?"** As is: `carousel.py deliver <job>` copies
   the slides + `caption.txt` to a folder in Downloads and opens it; tell her the folder name. Editor:
   `carousel.py edit <job>` (run it in the background; it opens the browser). Its Export button shows progress,
   saves to the same Downloads folder, and offers Show in Finder, Download all and Copy caption.

Pack = her default pack (the one every reel uses; a Brand Kit pack once she makes one), so her carousels match her
reels. `carousel.py build` uses it when `--pack` is left off. No default yet: ask which pack (Butter, Editorial,
Playful or one of hers).

## The shape

hook → reframe → proof → points → turn → closer. Points: as many as needed, one idea each (they share one
layout automatically). The proof is the big moment: a number, or a screenshot from the inbox.
The turn zooms out from her story to THEIR life.

## plan.json

```json
{"keyword": "PLAN", "photos": ["hook.jpg", "second.jpg", "points.jpg"],
 "slides": [
  {"role": "hook", "eyebrow": "how i'd", "headline": "plan a week of meals", "support": "in 3 steps..."},
  {"role": "reframe", "eyebrow": "a year ago", "lead": "dinner was a 5pm panic.", "headline": "now it's done by sunday.", "support": "here's what changed..."},
  {"role": "proof", "eyebrow": "every week", "number": "4 hours", "label": "back on my weekdays.", "support": "here's exactly how."},
  {"role": "point", "eyebrow": "step one", "headline": "shop once.", "support": "what do you already cook on repeat?"},
  {"role": "turn", "eyebrow": "not a planner?", "line": "you don't need a system.\nyou just need a sunday."},
  {"role": "closer", "intro": "hey, i'm sam.", "lead": "comment", "action": "plan", "action_style": "button", "support": "and i'll send you my planner."}],
 "caption": "..."}
```
Optional per slide: `"photo": "<file>"`, `"look": "photo"`, proof `"screenshot": "<file in photos/>"` instead of
`number`. `photos` order: hook, reframe/proof, the points' shared photo. Closer `action_style`: `button` or `big`.

Her text size and spacing, for the whole carousel (top level of plan.json, all optional; leave them out and it
builds as before): "make the small text bigger" → `"body_boost": 1.2` (and `"eye_boost"` for the eyebrows, 0.6 to
2.0); the line under the cover's headline → `"hook_support_size": 60` (px); "tighten the headline" →
`"headline_line_height": 0.9`; the eyebrow closer to the headline → `"eyebrow_gap": 10` (px, default 22) and
`"eyebrow_line_height"`.

## Your brand kit grows as you go

`brand-kit.md` has a section **"What you sell, and how your DMs work"**. Read it before asking anything.
If it's missing (older install), append `workflows/carousel/brand-kit-section.md` to the end of Part A, just
above "# Part B", without touching anything else. Never write a double-angle-bracket placeholder there
(the fresh-install check counts them).

- **Already built a Homebase elsewhere?** When the section is still empty, check for `brand-homebase.md` one folder
  up or in a sibling Startup Mom product (same search as the homebase skill, Step 0). Pre-fill "What you sell" and
  "Your freebie" from its What You Sell / freebie answers and tell her where they came from. Never name an
  unreleased product.
- **Skip what's answered.** DM tool, what her business sells and her freebie: never ask again once they're filled.
- **Looks:** if a usual look is set, ask one yes/no instead of the open question: "Same look as last time
  (photo, Butter)?"
- **Keywords:** if she reuses a saved keyword, offer its saved DM ("Send the same DM as last time?") rather
  than writing a new one.
- **Save as you go.** Right after she answers a DM tool, offer, freebie, keyword or look question, write it
  into that section in her words (keywords: one line, newest first, as `KEYWORD`: what it sends · the link
  · the DM · first used on <job>, <date>). Tell her once, in one line: "Saved to your brand kit, so I won't
  ask again." Only save what she said. Never invent or guess a link or a price.
- **If she changes something** ("I stopped using ManyChat"), update the line and say so.

## Keyword + DM (whenever there's a keyword)

DM tool from the brand kit section; if it's not there yet, ask "Do you use ManyChat, or another tool that answers
DMs for you?" and save the answer. Then what the DM should send (the link or the thing; a saved keyword already
has one), and write the DM in her voice. Put `"manychat": true|false` and `"dm": "<the message>"` in plan.json.
The export window and `before-you-post.txt` then tell her exactly what to set up and post. Never invent a link.

## Closer (one ask, never stacked)

keyword DM (comment WORD) · product ("it's called ___, link in my bio") · freebie · follow ("i share ___,
follow along") · save ("save this for ___", `big`) · share · question · quiet (emotional posts: a closing line,
no ask). **No offer:** default to save, offer follow. The keyword goes in the caption too.

## Copy rules

Headline + support line per slide, one idea per slide, no slide repeats the last. End a line in "..." only
where the next slide pays it off. Nothing named before the turn. Caption never repeats the hook. Her voice
from `brand-kit.md`. No em dashes.

## Edits by chat

Change words or photos in `plan.json`, re-run build + render, show the new beat sheet. A build replaces
editor tweaks (the old version is kept as `carousel.prev.json`), so after she has used the editor, make word
changes in the editor or tell her first. "Draw on it" works: she sends a marked-up slide, you change the plan.
