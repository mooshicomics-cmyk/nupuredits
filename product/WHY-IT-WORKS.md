# Why it works this way

The reasons behind the engine's fixed choices, for whoever is about to change one. `CLAUDE.md` says what to
do every session; this says why, so a problem that was already solved stays solved. Each section ends with
the file that owns the choice; the numbers live there, next to their own reasoning.

---

## One hearing of her words

**Her footage is transcribed once per job.** The first rough cut keeps the transcript in the job's
`transcript/` folder, and every later run is handed that copy back instead of listening again: the listener
is slow, it hears the same audio the same way each time, and one transcript is what keeps the cut and
everything drawn from it in agreement. Footage that really changed is heard again with `--force`.

**The script the rest of the engine reads is arithmetic, not a second hearing.** After every stitch the kept
words are moved from each raw clip's clock onto the cut's clock using the cut plan (`cuts.json`) and written
as `outputs/<job>.transcript.json`. The style plan, the graphics plan, every caption route and every format
read that file, so a word fix made there shows up everywhere at once. Fixes come from the corrections tables
(shared, hers in `_local/`, and one per job) and are laid in as the script is written; the raw transcript is
never edited, so a new fix is applied by writing the script again, with nothing re-cut or re-heard
(`recorrect.sh`).

**Every play of a line is in her script.** A line copied to the front as a hook, or played again as a
rewind, is heard twice, so its words are placed twice and both plays get their captions. A word is held to
one place only where the cut put a seam inside it: two spans of one take, played one after the other, that
both reach into the same word. That is one play of it, placed once.

Owned by: the `rough-cut` skill's `word-timings.sh`, `kept-words.py` and `recorrect.sh`.

---

## A cut that matches its plan to the frame

**Every boundary sits on a frame of its own clip.** Picture can only change on a frame, sound can change on
any sample. A boundary left between frames gives that segment slightly more sound than picture, or less, and
the joins absorb the difference a little at a time until the end of the reel sits visibly off its
transcript. Snapped first, the plan and the finished timeline are the same numbers, so captions, graphics
and CapCut placement all take their times straight from the plan.

**Joints are faded, briefly, over her real room tone.** At each joint the outgoing sound carries on a few
milliseconds past its cut and fades out while the next segment fades in, at equal power. The waveform has no
step to click and the room never drops to silence. The fade spans one full cycle of a low speaking voice, so
no cycle is cut part-way; measured on real joints, longer fades reach into her next sound more often. A
joint whose cut-in caught a word already starting can take a longer fade of its own in the plan
(`"xfade"`), without moving anything on the timeline; the stitch hears its own joints and gives one that clicks or
dips that longer fade by itself, then hears it again. Only the very start and the very end of the file fade to silence.

**One fixed gain, then a fixed chain.** Nothing in the master follows her level over time, so a quiet line
stays quieter than a loud one, as she said it. The limiter at the end looks ahead, and its delay is taken
back out so the sound stays on the picture.

**Every stitch is listened back to.** `sound-check.py` hears each joint for a click, a dip or dead air,
checks the sound runs exactly as long as the plan, and reports when the limiter is working harder than her
recordings normally make it, naming the lower gain to try. It only reports; it never fails a build.

Owned by: the `rough-cut` skill's `stitch-cut.sh` (snap, joints, master), checked by its `sound-check.py`.

---

## Graphics placed around her, by measurement

Each job's footage is measured once (`workflows/subject-zones.py` writes `subject-zones.json`: her head to
chin, and the open zones around her), and every graphic and caption is placed from that, inside the safe
bands from `product/safe_zones.py`. The same reel framed differently gets different numbers, which is why no
placement is ever typed or copied from another job. The box is where her head usually is, not her furthest
reach. A layer that lands on her is said loudly and still rendered (`product/subject_guard.py`), and `finalize`
moves CapCut text off her to the nearest open zone, then builds either way (`product/subject_place.py`): she
always gets her reel, and a check is a warning, never a wall.

Owned by: `workflows/subject-zones.py`, `product/safe_zones.py`, and the two guards above.

---

## A change costs one layer

A rendered reel is a stack: her base cut, then one transparent layer per job (captions, hook, cards and the
rest). The time a render takes goes into capturing frames, so no quality setting makes a whole re-render
cheap; the only saving is not repeating work. So every layer renders through `product/reel_render.py render`,
which caches by a hash of the layer's source and returns at once when nothing changed, and
`reel_render.py composite` re-stacks the base and every layer in one ffmpeg pass. Her base cut and every layer she already
approved are never rendered again. The working method is in
[`workflows/graphics-part-by-part.md`](../workflows/graphics-part-by-part.md).

Owned by: `product/reel_render.py`.

---

## A check that finishes in its time

**The pre-render check samples transitions up to a cap.** `hyperframes check --at-transitions` looks at every
tween start and end plus the midpoint between each pair, and HyperFrames gives the whole browser check a
fixed 120 s, page load included. A layer with a caption on every word has hundreds of one-word clips and
700+ boundaries, which never fit, so the check ran out of time and said nothing useful. Capped, HyperFrames
keeps an even stride across the whole layer and says how many moments it left out (that line is the cap
working, never a fault): 100 on Apple Silicon, 60 on other machines, 40 at 8 GB or less, since a slower
machine spends longer on each moment. A check that still runs out of time is said as that, the time the
check had on this computer, and the layer renders as placed.

Owned by: `product/npx_run.py` (`hf_check_max_transition_samples`, override
`REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES`, 0 = no cap), guarded by `product/tests/test_hf_check_argv.py`.

---

## Clean Captions are stills

Reels pulled from a long video by `pull-reels` can be captioned without any render: the hook and the
captions are drawn as still images in the pack's own fonts and shadow, two layers over the cut, so the pass
always finishes. It reads the rough cut (`outputs/<job>.mp4`) and always writes to a file of its own, so that
cut stays uncaptioned for the next run. Everything else about it is in
[`presets/clean-captions-style.md`](../presets/clean-captions-style.md).

Owned by: `presets/clean-captions/build.py`.

---

## A finished job keeps what a rebuild reads

Revisions part by part and "your turn" both rebuild from the job folder, so what a finished job keeps is
decided by what those rebuilds open, never by age or size.

- `scripts/name-final.sh <job>` names the reel she posts, `outputs/<job>.final.mp4`, and lists what the job
  keeps: the base cut, the transcript, the plans, `subject-zones.json` and `hf-graphics/`. It only reports
  until `--apply`.
- `scripts/free-space.sh` looks only at what the engine can make again from what stays in the job: a
  composition's `renders/`, the renderer's leftover scratch from a stopped render, and `node_modules` beside its
  `package.json`. It adds up what they hold; `--apply` removes them. Her footage, everything in `outputs/`, the
  CapCut staging folder, anything a CapCut draft still plays, and the sources her graphics were built from are out
  of its reach.

Owned by: `scripts/name-final.sh` and `scripts/free-space.sh`.
