---
name: build-a-look
description: Workshop a NEW look with her and save it to her lookbook, from the idea she left on the visual editor's "Build a new look" (or one she describes in chat). Use when she says "sandbox" (her Sandbox button in Visuals, three quick sketches she picks from, remixes or locks in), "build my look", "build a new look", "design a new look", "new look", "I have an idea for a look", or the page tells her to type build my look. Not for a whole style pack (that is style-pack) or for tweaking a look already on a line (that is Refine on the page).
---

# Build a new look

She picked a line on the visual editor, said what she's picturing, and typed **build my look**. You design it
WITH her, on her own footage, until she loves it; then it joins her lookbook for this pack and works on any line
of any reel. One question at a time, short, plain words. HyperFrames is never named to her.

**She is on her page, not in the chat, so her page says it too.** The news lands there by itself: `sandbox-takes`
("Your three sketches are in your Sandbox"), `place-look` ("Your new look is on your line") and `look-request ... done`
("in your lookbook") each pop a Chef Claude card on her page. When you ASK her something (what you heard, her notes
on a draft, what to call it, a pick-one), ALSO put it on her page first, then ask in the chat:
`python3 product/visual_editor.py tell <job> "<the question, one plain line>" --chat` (before the question box: a
command after it waits until she answers). The card says her answer goes in the chat.

## Sandbox: three quick sketches (her Sandbox button, then "sandbox" in the chat)

She pressed **Sandbox** in Visuals and said what she's picturing, in her own words ("on lines 4 and 5, a card
that says $300 and counts up, behind my head"). There is no line attached: **her words say where**, and her
playhead rides along for "right here". `look-requests` marks it `sandbox`; `todo` says `SANDBOX` (first round) or
`SANDBOX REMIX, round N` (what to change, and which sketch it starts from).

0. **Say you're on it, first thing:** `python3 product/visual_editor.py sandbox-working <job> <idea-id>`. Her page
   flips to "I'm working on your sandbox now. Keep working. I'll let you know when it's ready for your review.", so she
   closes it and carries on. (Her sketches landing clears it.)
1. **Read it.** `python3 product/visual_editor.py look-requests <job>`, the still, and the cut's words with their
   times (`projects/<job>/outputs/<job>.transcript.json`). Work out the moment (start and end in cut seconds,
   from the lines or words she named, or her playhead) and whether it goes behind her.
2. **Three sketches, cheap on purpose.** Three genuinely different directions on her idea (not three tints of
   one): small, quick HyperFrames designs in her pack, same contract as a new design (section 3: pack colors and
   fonts, her words in slots, fitted sizes, timing from the moment, her assets only, clear of her face per
   `subject-zones.json`). No impeccable pass, no render: they are sketches. Name each by round and number:
   ```bash
   mkdir -p projects/<job>/hf-graphics/_looks/_new/<idea-id>
   cp -R product/lookbook-designs/starter projects/<job>/hf-graphics/_looks/_new/<idea-id>/r1-1   # r1-2, r1-3
   # edit each into its direction (index.html + design.json, with a descriptive "name" and a one-line "about"
   # she reads under it), then save it under that same name:
   python3 product/lookbook.py save-design projects/<job>/hf-graphics/_looks/_new/<idea-id>/r1-1 --pack <pack> --name "Card pop orbit" --id my-sandbox-<idea-id>-r1-1 --sample <idea-id>
   python3 product/visual_editor.py sandbox-takes <job> <idea-id> --start <s> --end <s> [--behind] my-sandbox-<idea-id>-r1-1 my-sandbox-<idea-id>-r1-2 my-sandbox-<idea-id>-r1-3
   ```
   **Give every sketch a real name in design.json `"name"`:** 2 to 4 words that describe the LOOK itself, in
   sentence case ("Card pop orbit", "Sticky note slap", "Wall of reels"). Never "Sketch 1", never "Starter card", never
   her idea's first words. It is the name her page suggests when she locks the sketch in (and the look's id follows
   it), so "So I'm gonna be editing this in CapCut t" never becomes the name of a look. Her page numbers the tiles
   Sketch 1 to 3 on its own.
   **Words she wants on it that she doesn't say** (handles, names, an aside) go in the `note` slot (`"slots":
   ["note"]`, `"note": "..."` in design.json). A sketch like that, or one with no words at all, carries its own words
   and places on a quiet stretch (a b-roll reel with no talking) with no `--text`.
   **Her own image or GIF:** an idea from the Image picker carries `"media"` (a file in her favorites, e.g.
   `gifs/Name.gif`, or a one-off in her inbox, `inbox:<path in inbox/>`; `python3 -c "import sys; sys.path.insert(0,
   'product'); import visual_editor as v; print(v.media_path('<id>'))"` gives its path; her words may list more after "and also these from my favorites:"). Build every sketch around that
   file, as an overlay on her footage, never replacing it: copy it into the sketch folder's `assets/` (a GIF as a
   looping clear video: `ffmpeg -stream_loop -1 -i <gif> -t <dur> -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 30
   -an assets/media.webm`, played by a muted `<video class="clip" data-start data-duration>` the timeline drives; an
   image as `<img>`), and animate a wrapper around it, the way her words say. The file travels with the design, so a
   sketch she keeps for her lookbook keeps its image.
   `--start/--end` are required when she named no line. Saving a sketch checks the design rules only (fast); the
   full check runs on the one she locks in.
3. **Start the watcher again** if it isn't running (`rough-cut`, "The watcher"), then **tell her, one line:** "Your three sketches are in your Sandbox. Hover to play, tap one, then Lock it in, or
   Remix." Her page shows them side by side by itself, and `sandbox-takes` already popped a card there with the way
   to her Sandbox (no `tell` needed). Nothing on her reel changes until she locks one in.
4. **Remix** (round N): read what she wants changed and which sketch it starts from, make three new sketches
   (`r<N>-1..3`), and `sandbox-takes` them; the last round's sketches clear away on their own.
5. **Lock it in** happens on her page (it asks: her lookbook for every reel, or just this reel). In the chat ("lock
   in sketch 2, just this reel"): `python3 product/visual_editor.py sandbox-keep <job> <idea-id> oneoff|reuse
   my-sandbox-<idea-id>-r<N>-2 "<her name for it>"`. A `SANDBOX FIX` in `todo` means the full check refused the one
   she locked in: fix that sketch, save it again with `--sample`, and tell her to press Lock it in again. Cancel:
   `sandbox-drop <job> <idea-id>`.

A look she keeps in her lookbook is one of her own looks from then on: it shows under Swap on every reel, and the
creative plan reaches for her own looks first, so her lookbook grows with every reel. A one-off never shows anywhere
else.

## 1. Read her idea

```bash
python3 product/visual_editor.py look-requests <job>
```

Each idea prints its id, her line's words, what she's picturing, and a still of that moment. **Read the still**
(it is a file path) so you see her framing before you design anything. No idea on the page? She can describe it
here; ask which line, then use that line's words.

Say back what you heard in one or two sentences ("A sticky note that slaps on, your words in the handwriting
font, a little tilt. On 'because when one of us wins'.") and ask only what you truly can't decide. A question
goes on her page too (`tell <job> "..." --chat`, above).

## 2. Lookbook first: is it one of her looks with changes?

`python3 product/lookbook.py list --pack <pack>`. If her idea is one of those looks with a different animation,
size or words, it is NOT a new design: put that look on her line and send her to **Refine** on the page
(animation, words, a note to you), then **Save to my pack**. Say so in one line and stop here.

```bash
python3 product/visual_editor.py place-look <job> <idea-id> <look-id>
```

## 3. A new design: start from the starter, on her line

```bash
mkdir -p projects/<job>/hf-graphics/_looks/_new/<idea-id>
cp -R product/lookbook-designs/starter projects/<job>/hf-graphics/_looks/_new/<idea-id>/design
```

Edit `design/index.html` and `design/design.json` into her idea. Read `.claude/skills/motion-graphics/TOOLKIT.md`
and `.claude/skills/reel-layout-rules/SKILL.md` first, and run the `impeccable` critique on the design before she
sees it. The contract (the starter shows every piece; `check-design` enforces it):

- **It wears the pack, never its own skin.** Colors only as `var(--pk-light|dark|muted|accent|pop2|hook|subhead)`
  (plus black/white for shadows), fonts only `PkHeadline` / `PkTakeover` / `PkCaption` / `PkAccent`, case as
  `text-transform: var(--pk-case-…)`, tracking as `var(--pk-track-…)`, shadow as `var(--pk-shadow)`. That is what
  keeps every look one coherent pack (one yellow, one case) and lets it follow her pack if she changes it.
- **Her words go in slots, never typed in:** `__TEXT__`, or `__LINE1__`/`__LINE2__` (small line, big words), or
  `__NUMBER__`/`__LABEL__` (a count-up; `__NUMBER_VALUE__` inside the script). List the ones it uses in
  `design.json` `slots`.
- **A look is a TEMPLATE: it never keeps the words of the reel it was made on.** `save-design` strips a baked
  `note` to a placeholder (keeps the sample under `note_sample` for the preview); every word comes from the reel
  it's placed on, every time (you: "everything should adapt to the reel"). A **checklist's items go in `__TEXT__`
  comma-separated**, and the template splits on commas keeping the FULL item per line (never reduce to the last
  word, never split on spaces/slashes); its heading is the `note` slot (or her spoken line for a `note_follows_line`
  design), passed as `"heading / item, item, item"`.
- **Font follows the pack by default; an override is allowed.** The template names only the pack roles
  (`PkHeadline`...), so it stays check-clean. She can wear one of HER own fonts over a role on a placed look with
  no template change — Refine `font`/`font_role` (the `/refine` endpoint's `font`), resolved to a real font in
  `favorites/fonts` / `assets/fonts` only (an unknown name is refused, the pack face stays). Never bake a non-pack
  font into the template.
- **Sizes are fitted, never guessed:** a slot that must fit gets `"fit": {"<slot>": {"role": "headline",
  "box_w": <px>, "max_px": <px>, "max_lines": <n>}}` and `font-size: __PX_<SLOT>__px`. The engine fits her words
  in the pack's own font and never goes below what reads on a phone.
- **Timing from the line:** root `data-composition-id="__COMP__" data-duration="__DUR__"`, the timeline registered
  as `window.__timelines["__COMP__"]`, intros with `tl.fromTo`, every exit ending in a `tl.set` kill, the exit
  timed from `__DUR__`. **Every piece leaves when its moment does:** a piece the script places (a click ring, a
  burst, a frame around a clip) starts hidden and is hidden again when its part ends, never parked at `left:0;top:0`
  or left standing after the thing it framed (`check-design` refuses a parked one).
- **Her assets only.** An illustration or sticker comes from her `assets/` (copy it into the design folder). Never
  draw or generate one. No web links: everything lives in the folder.
- `kind` is `Hook`, `Card` or `Full screen`. Caption styles stay the four the engine makes.

## 4. Show her, on her footage

```bash
python3 product/lookbook.py check-design projects/<job>/hf-graphics/_looks/_new/<idea-id>/design --pack <pack>
python3 product/lookbook.py save-design projects/<job>/hf-graphics/_looks/_new/<idea-id>/design --pack <pack> --name "<Name> (draft)"
python3 product/visual_editor.py place-look <job> <idea-id> my-<name>-draft
```

`check-design` draws it short and long in her pack and runs the render check; fix everything it says before
saving. `place-look` puts the draft on her line: the page shows it live over her footage (Move, Swap and the rest
all work on it), and pops "Your new look is on your line" there. Tell her in one line to press play on that line,
then take her notes in the chat (`tell <job> "Your draft is on your line. Tell me in the chat what to change." --chat`
when you're waiting on them). Each round:
edit, `save-design` with the same draft name, `place-look` again. Never more than one draft at a time.

## 5. She loves it: into her lookbook

Ask what she'd call it (her words, short), on her page too: `tell <job> "What should we call your new look? Tell me
in the chat." --chat`. Then:

```bash
python3 product/lookbook.py save-design projects/<job>/hf-graphics/_looks/_new/<idea-id>/design --pack <pack> --name "<Her name>"
python3 product/visual_editor.py place-look <job> <idea-id> my-<her-name>
python3 product/lookbook.py remove-design my-<name>-draft --pack <pack>
python3 product/visual_editor.py look-request <job> <idea-id> done my-<her-name>
```

Tell her it's in her lookbook now: it shows under Swap on any line and in the Lookbook, in this pack, on every reel.
If she drops the idea: `remove-design` the draft, `look-request <job> <idea-id> dropped`, and put the line back
the way it was (Swap's trash on the page, or tell her where).
