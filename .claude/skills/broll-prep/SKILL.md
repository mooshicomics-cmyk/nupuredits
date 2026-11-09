---
name: broll-prep
description: "Prep a folder of long clips into short, grabbable b-roll pieces the SMART way: watch the footage, pull the 3-4 BEST 6-9s moments per clip where the subject is in frame and something's happening, name them by real content, ask before batching. Subject-quality first, not blind chopping. Triggers: broll prep, prep broll, prep my b-roll, prep clips for broll, chop these into broll, best moments for broll, pull broll grabs, make broll grabs, trim a bunch to 6-9 seconds, grab the good bits."
---

# B-Roll Prep — pull the best moments, don't blind-chop

Turns a pile of long clips into a tidy folder of short b-roll grabs. The point is
**subject quality, not timing.** Watch the footage, keep the moments worth keeping,
throw away the rest. One organized folder, named by what's actually in each clip.

**This is a b-roll ROUGH-CUT batch, and you say so at handoff.** The output is prep
grabs to speed a build (great right before a Voiceover build), not final b-roll.
Trim points, exact in/out, and final selects are the creator's to refine in the
editor. Setting that expectation is part of the deliverable, not a caveat.

## The rules that decide a grab (locked with the creator)

1. **Pull the 3-4 BEST 6-9s moments per clip** where **something is actually
   happening.** Not every 8 seconds — the good ones.
2. **Subject must be in frame** to count. A moment where the person drifts out of
   frame is not a grab. **Exception: a landscape / scenery clip** — there the scene
   IS the subject, so no person is needed.
3. **If people are in it, maximize that moment.** Extend/center on the people beat.
4. **Length is flexible, 3-10s, target 6-9s.** Cut where the subject reads best, not
   on a fixed grid. A 12s clip is usually 2x6s, but 8s+4s if the subject needs the
   split there. **Subject takes priority over even timing.**
5. **Name by real content.** Filenames lie (a "stroller" clip was really laptop work;
   a "toddler" clip was really making coffee). Watch first, name by what's in frame.
6. **Ask clarifying questions before batching.** General enough to fit any footage,
   granular enough to guarantee quality (see the question bank below).

## Workflow

**Step 1 — Scan the footage (always, before any cutting).**
Probe durations/codecs, then extract timecoded contact sheets and READ them so the
picks are based on what's in the frame, not the filename.

```bash
# durations + codec (spot Cinematic-mode -E pairs, HDR, etc.)
for f in <dir>/*; do case "$f" in *.MOV|*.mov|*.MP4|*.mp4) ;; *) continue;; esac; \
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; \
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$f"; done
# contact sheet (this ffmpeg build has NO drawtext; track time from grid position:
# fps=1 -> cell index = seconds; fps=1/5 -> cell index*5 = seconds)
ffmpeg -hide_banner -loglevel error -i "<clip>" -vf "fps=1,scale=320:-1,tile=6x6" -frames:v 5 sheet_%02d.jpg
```
Use a coarser `fps=1/5` for multi-minute clips. Read every sheet.

**iPhone Cinematic mode imports as a pair: prep the `E` twin, never the raw one.** `IMG_1234.MOV` is the raw
capture (a `dish` depth track beside a flat picture) and `IMG_E1234.MOV` the rendered one with the blur baked
in; a stream-copied grab of the raw one is flat. Check with
`ffprobe -v error -show_entries stream=codec_tag_string -of csv=p=0 "<clip>" | grep -q dish`; when it
carries the track and its `E` twin is in the folder, grab from the twin only. If the twin is missing, say so
before cutting. `broll-select.py` makes the same call on anything it is pointed at.

**Step 2 — Read each clip and classify.** For each: is it *person-driven* (need the
subject in frame) or *landscape/scenery* (scene is the subject)? Where are the good
moments? Where does the subject leave frame (drop those)? Note mislabels.

**Step 3 — Ask before batching.** Surface the genuine forks as a clean pick-one
prompt (AskUserQuestion). **Always ask the first two**, then pick from the bank what the footage raises:
  - **Most clips, or only the good ones?** "Only the good ones" = the subject-first workflow here (fewer,
    every one usable). "As many as possible" = the blind even-slice fallback below (more clips, the
    creator culls by eye). This is the fork that decides the whole batch, so never assume it.
  - **How long per clip?** Default 6s when the grabs are headed for hook reels (text-over-b-roll), 6-9s
    for a Voiceover build.
  - Talking-to-camera clips: are they gestures that work silent, or spoken a-roll to skip?
  - People appear only at the edge of frame: grab those moments, or keep clean subject footage?
  - Mislabeled files: name grabs by real content? (almost always yes)
  - How many grabs / target length, if the creator hasn't already said.
Don't ask what the footage already answers. Do ask when subject-in-frame vs
maximize-the-people pull opposite ways.

**Step 4 — Cut the chosen windows, lossless.** Stream-copy each window (no re-encode,
no HDR/color risk; keyframes are dense so `-ss` before `-i` lands within ~1s). Name by
content, pooled + zero-padded. Park anything under 3s in `_too-short/` (never lose it).

```bash
ffmpeg -nostdin -hide_banner -loglevel error -y -ss <start> -i "<src>" -t <dur> -c copy -map 0 grabs/<content-name>-NN<ext>
```
**`-nostdin` is not optional when this runs inside a `while read` loop over a cut list.** Without it ffmpeg
eats bytes off the loop's stdin, so lines get mangled or skipped and grabs go missing with NO error. Cut
points also land on the nearest keyframe at or before `-ss`, so when junk sits immediately before an
in-point (a camera-settle head), snap the in-point FORWARD to the next keyframe instead
(`ffprobe -select_streams v:0 -skip_frame nokey -show_entries frame=best_effort_timestamp_time`), and set
`-t` from the actual start so the OUT point stays where you planned it.

**Step 5 — QA + hand off.** Pull each grab's middle frame into one contact sheet and
confirm the subject is in frame in every grab before handing off. Write a
`MANIFEST.txt` (content group -> grabs, sources, flags). Send the folder + QA sheet.

**Where the footage lives.** The default source is **`inbox/b-roll/`**: the creator makes a folder called
`b-roll` inside her inbox and drops the long clips there, so b-roll never mixes with her talking footage. If it
doesn't exist yet, create it and tell her to drop clips in. A pointed folder or loose clips in `inbox/` still work.

**Where the grabs land.** Always `<source folder>/grabs/` (for the default, `inbox/b-roll/grabs/`), so the
next step can find them and never mistakes the long originals for b-roll.

**Handoff — say what's next.** After the QA sheet, tell the creator the two things she can do with the grabs,
in plain words: **"Want hooks baked onto these? Say: make b-roll reels"** (the `broll-reels` skill picks up
this `grabs/` folder), or use them as the footage for a Voiceover reel. Don't leave her with a folder and no
next step.

**Step 6 — score the grabs for the Voiceover build (when this prep is for a VO reel).** Prep decides
WHAT is worth keeping (subject, content); the selector decides WHERE in each grab the picture is best
(sharpness, exposure, stillness, flicker) and offers several windows per grab, at burst and hold
lengths, so the shot plan can pair every beat with the best part of a clip:

```bash
uv run product/broll-select.py --lib <grabs folder> --job <job>
```
It reads the grabs folder, skips `_too-short/`, keeps every usable grab (no cap), and writes
`projects/<job>/broll-select.json` + `broll-candidates.jpg` (one tile per window). The VO shot plan is
authored FROM those windows, never from raw in-points guessed off a contact sheet.

## Fast fallback: blind even-slice

When the creator explicitly wants a dumb, exhaustive slice (every ~8s, no curation) —
e.g. a huge dump where they'll grab by eye later — the helper does that in one pass:

```bash
python3 product/broll_prep.py "<folder>"   # --dry-run, --seconds, --min, --max, --folders
```

This is the FALLBACK, not the default. The default is the subject-first workflow above.
