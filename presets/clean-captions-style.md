# Clean Captions

Her style pack in its lightest form, set straight into a reel pulled from a long video: her words as short
captions under her chin for the whole reel, and her hook across the top while the opening plays. Every
piece is a still image, so there is no animation and nothing to render, and the pass always finishes.

It belongs to `pull-reels` alone. A reel gets it when she asks (`--captions clean`, or `"captions": "clean"`
on one reel), or when its style-pack captions could not finish (the beta default), so no pulled reel comes
out without captions. A single reel never comes through here: it is captioned by its style pack, or by
CapCut's Auto Captions on the CapCut route. The code is
[`presets/clean-captions/build.py`](clean-captions/build.py).

## Whose look it is

The pack decides every face, size and color, by job, the same as on every other route. Which pack: `--pack`,
else `STYLE_PACK`, else her saved default (`product/creative-vault/user-style.json`).

| Job | With her pack | With no pack (the starter look) |
|---|---|---|
| Hook headline | the pack's `headline` face, case and size, in `welldone.hook_color` | Inter Black, as written, white |
| Eyebrow / subhead | the pack's subhead face (`subhead_font_file`, else `subhead_source`), in `welldone.subhead_color` | Inter Bold, white |
| Captions | the pack's `caption` face and case at its designed size (`size` × `single_scale`) | Inter SemiBold, as spoken, white, 66px |
| Shadow | the pack's `welldone.text_shadow` | three shadows in the engine's ink `#111111`: a tight edge, a short drop, a soft spread |

A long video is often pulled before she has picked a pack, so the starter look is what most of these reels
wear: white type kept readable on any background by its shadow, never by a box (`presets/type-and-look.md`).
The day she picks a pack, the next burn-in wears it with nothing else to change. If the pack cannot be drawn
on this computer (an unknown name, or a face with no file), the run uses the starter look and gives the
reason in one line; a face with a bundled stand-in uses the stand-in and says so.

Captions never go below the pack's designed size or the legibility floor (`safe_zones.MIN_PX`). A size she
taught (`caption.size_scale`, through `learn`) scales them.

## The captions

**On for the whole reel**, first word to last, underneath the hook while it is up.

**Placement.** At the top of the open zone below her, as this job's `subject-zones.json` measured it: the
same line the pack route uses. A zone she taught (`caption.zone`) takes the look's own height instead, and so
does a job with no measurement (the pack's caption `y`; y1152 for the starter look). Always inside the safe
bands (`product/safe_zones.py`).

**Phrasing.** One short phrase at a time, kept to one line. A phrase closes at a pause mark (a comma, a
colon) or the end of a thought, at five words (six when the sixth finishes the thought, so no word sits
alone), or before a word that would wrap it. Each phrase stays up until the next arrives, so the screen never
blinks empty mid-reel, and the last one stays 0.6 s past her final word. Trailing commas and periods are
dropped on screen; `?` and `!` stay.

**The words** are the rough cut's kept-words transcript, `outputs/<job>.transcript.json`, already timed to the
audio that ships, so the phrases land on her voice without hand nudging. Every word in it is shown, however
short, because the cut already chose what she kept, and each run reports how many of her words the phrases
carry. Nothing is transcribed again. Before a word is drawn it passes through the `auto` table in
[`caption-corrections.json`](caption-corrections.json), which fixes a misheard name or its capitals on screen
only. A new mishear goes into that file.

## The hook

**Shape.** One of the three shapes in
[`WRITING-THE-HOOK.md`](../workflows/capcut-export/WRITING-THE-HOOK.md), chosen by how many lines the copy has:
one line is a **hook card**; two lines are **eyebrow + headline** (the default: small first line, big
second); two lines with `--hook-emphasis first` are **headline + subhead** (big first line, quiet second).
Only the emphasis moves, never the reading order. The headline is fitted to the safe width, on one line while
it stays at the pack's `head_one_min` or larger, else on two balanced lines with no orphan. The quiet line
steps down by the pack's own caption-to-headline ratio, never under 40px and never as loud as the headline.

**Copy.** Written for the screen, not lifted from the transcript: lowercase, casual, in her voice, by the
rules in `WRITING-THE-HOOK.md`. Give it per reel with `--hook "..."` (a line break splits the two lines). No
copy, no hook: the captions run alone.

**Position.** First ink at y280, the line just under the 270px top band that the pack route also uses, the
same size and place on every reel unless she asks otherwise. The run reads this job's `subject-zones.json`
and raises two things for her to decide, without changing the render: the hook overlaps her head because she
sits high in the frame, or the hook runs past two lines.

**When it leaves.** Near the 8 s mark that is the hook block's usual hold (`hook_end` in
`WRITING-THE-HOOK.md`), at the start of the sentence after the nearest break, so it never leaves mid-thought.
A reel's plan can set the exact moment (`hook_end`, given as `--hook-end SECONDS`), and words she says to close
the hook out loud (`HOOK_CUE_WORDS`) take it down as she moves past the first one.

## How the layers are made

The reel is stacked the way `reel_render.py composite` stacks a rendered one: the cut at the bottom, then a
hook layer and a caption layer, each the full 1080x1920 canvas. Pillow draws every still in the pack's own
font files with the pack's own shadow; each layer is a run of those stills, each held for its stretch, read by
ffmpeg as a single input. That keeps it to two inputs however many phrases the reel has, and needs no
HyperFrames render (the engine's ffmpeg is built without a text filter, so type is never drawn by ffmpeg).

## Running it by hand

`pull-reels` runs it for every reel it captions. By hand it needs the rough cut done first, which leaves
`outputs/<job>.mp4` and `outputs/<job>.transcript.json` in the job.

- **The finished reel:**
  `python3 presets/clean-captions/build.py projects/<job> --hook "your hook" -o projects/<job>/outputs/<job>.final.mp4`
- **Just the opening**, to try hook copy quickly: add `--preview 30` and leave out `-o`. The preview lands in
  the engine's scratch folder under the system temp folder (`reels-editing-engine/<job>/clean-captions/`),
  beside the layers and `captions.json`, which lists every phrase with its times.
- **Another look:** `--pack <Pack>`, or `--pack starter` for the starter look on purpose.

Each run prints the look it used, where the captions sit, when the hook leaves and why, and the word count.
The output always goes to its own file. `outputs/<job>.mp4` stays uncaptioned, so the next run starts from
clean footage.

## When she asks for a change

| She wants | Change |
|---|---|
| a different look | pick or switch her style pack (`--pack`, or her saved default), or make one of her own with `product/pack_write.py` |
| bigger or smaller captions | teach it (`learn`: `caption.size_scale`), so every route follows |
| the captions somewhere else | teach the zone (`learn`: `caption.zone`) |
| a different hook, shape or exit | `--hook`, `--hook-emphasis`, `--hook-end`, per run |
| a hook every reel gets, or her closing words | `HOOK_COPY` / `HOOK_CUE_WORDS` near the top of the builder (Part B of the brand kit writes these) |
| a different starter look | `STARTER` in the builder: an engine change, not a per-reel one |
