---
name: story
description: "The Story Kit. Make an Instagram story sequence in her style pack or the native Instagram look, from an idea, a script, a reel or a carousel. Triggers: make a story, turn this into a story, story sequence, IG stories."
---

# Story Kit

**From the visual editor:** she pressed **Make a story** under Your snaps on her page, so the newest `projects/*/review/kit-request.json` (`ls -t projects/*/review/kit-request.json | head -1`) names the reel, the snaps she ticked (an empty list = no snaps, the engine picks her best stills) and any photos she added from her favorites, her inbox or her computer (`photos`). Make it from that reel; `carousel.py frames <job> --from <reel>` uses exactly her ticked frames, her starred cover first, then her photos (`photo-NN`), then the engine's own picks for whatever room is left, and marks the request used. Her photos are hers to feature: never drop one to make room for an engine pick.

Words first, then design. Same engine as the Carousel Kit: `uv run workflows/carousel/carousel.py <cmd> <job>`, job
folder `projects/<job>/carousel/`. Never write frame HTML by hand; never open the frames one by one.

## Why it sells (say this once, in your words, when it helps her choose the ask)

Stories go to people who already follow her, so they are her warmest audience. Instagram shows stories first from the
accounts each person interacts with (likes, replies), so a reply both starts a conversation and keeps her near the
front of their row. Ask for a reply before a link tap.

## Flow (chat only)

1. **Start.** An idea, a script, or "turn this reel / carousel into a story" (`carousel.py words <job>` for a reel's
   transcript; a carousel's `plan.json` for a carousel). New job name: short kebab-case + `-story`.
2. **Goal**, one question at a time, only what `brand-kit.md` (and its "What you sell" section) doesn't answer:
   - What should people do at the end?
   - DM tool, only if the brand kit section doesn't have it: "Do you use ManyChat, or another tool that answers DMs
     for you?" Yes: pick a keyword it sends from. No: still use a keyword, and say kindly that she'll answer replies
     by hand.
   - "Want me to hold a spot for a poll or an Ask Me Anything box?"
3. **Script** in chat, frame by frame: the words, plus any sticker spot with its exact wording. She approves or edits.
4. **"Ready for me to design it?"** (or she says "design it").
5. **Look:** "Native Instagram, or your style pack?" then "A photo behind it, or a solid color from your style pack?"
   Photos: inbox, then `carousel.py photos <job> [files]`; use the printed names. From a reel with no photos:
   `carousel.py frames <job> --from <reel job>` pulls her best stills from it.
6. Write `plan.json`, then `carousel.py build <job> [--pack <pack>] --style <native|pack> --bg <photo|color>` and
   `carousel.py render <job>`. Left off, `--pack` is her default pack (the one her reels use, a Brand Kit pack once
   she makes one), so stories match her reels. Show **only** `beat-sheet.jpg`, plus any `check:` / `font:` lines in plain words
   (a `font:` line: her pack font isn't on this computer yet, a free stand-in was used, adding it in CapCut fixes it).
7. **"Export as is, or open it in the editor?"** As is: `carousel.py deliver <job>` (a folder in Downloads, opened
   for her). Editor: `carousel.py edit <job>` in the background. Remind her to add each sticker in Instagram where
   the space was left; the spaces never appear in the exported frames.

## Shape (3 to 7 frames)

hook → optional warm-up (a poll: an easy first tap) → the story, one idea a frame → optional proof → ONE ask, last.

## plan.json

```json
{"format": "story", "keyword": "LAUNCH", "photos": ["one.jpg", "two.jpg"],
 "slides": [
  {"role": "hook", "headline": "ok i have to tell you what happened this week"},
  {"role": "text", "line": "have you ever wanted to launch something online?", "bg": "color",
   "sticker": {"type": "poll", "options": ["yes, so bad", "not yet"]}},
  {"role": "text", "line": "three months ago i was studying other people's launches.\nthis week i did my own."},
  {"role": "proof", "number": "$250,000", "label": "in 48 hours. from one launch."},
  {"role": "ask", "lead": "i wrote down exactly what i'd do.", "action": "LAUNCH", "support": "and i'll send it to you"}]}
```
Roles: `hook` (headline), `text` (line), `proof` (number or `screenshot`), `ask` (action and/or lead; `cta` defaults to
"reply"). Any frame: `"bg": "photo"|"color"`, `"photo": "<file>"`, `"sticker": {"type": poll|question|link|countdown|slider|quiz,
"prompt": "...", "options": [...]}`. Photos are used in order across the photo frames.

## The ask (one)

reply keyword (default) · reply anything (no offer) · question box / AMA · poll · link sticker (only when the thing is
a page) · countdown (launch or deadline).

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

## Copy rules

About 20 words a frame. One idea a frame, no repeats. A voice memo to a friend, in her voice from `brand-kit.md`.
Nothing sold before the last frame. Never make her audience feel behind. No em dashes.

## Edits by chat

Change `plan.json`, re-run build + render, show the new beat sheet. A build replaces editor tweaks (kept as
`carousel.prev.json`), so after she's used the editor, tell her first.
