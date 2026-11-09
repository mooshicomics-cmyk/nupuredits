---
name: rough-cut
description: "The cut every Yap starts from: her talking footage, trimmed to the lines she meant to say. Her transcript decides what stays (never the volume), the last take of a line she said twice is the one kept, a line where she names an effect is never cut, and the stitch cleans double-takes and clipped words by their real sound. She reviews it in the style plan before anything else is built. Triggers: let's make a Yap, edit this reel, edit my newest clip, edit the clip called <name>, cut my newest project, cut this down, take out the bad takes, clean up my footage, rough cut. Also handles what the visual editor page tells her to type, in any session: \"show me my looks\" (or \"looks\", \"move on to my looks\"), \"update my edit\", \"notes\", \"render\" (or \"export\"), \"sent\", \"text only\" (or \"the original widget\"), \"open my editor\" (or \"open my visual editor\", \"show me the visual editor\"), \"switch my reel to <pack>\", and \"fill my b-roll\" (a voiceover reel's clips)."
---

# Rough Cut

Her clips go in. The same footage comes back shorter, with the **kept-words transcript**: the finished script
that every later phase (creative plan, build, captions, export) treats as truth. Only the cut happens here.
Graphics, captions, music and zooms all wait until she has approved it.

The road is always **transcribe → transcript-cut → stitch**. Inside the stitch: trim-restarts → snap-to-sound →
close-pauses → frame grid → master. Then she watches it in the style plan.

---

## The order is locked (it is the course's order): reel or YouTube first, then one question at most before the cut

**The very first thing, before anything else in this skill:** `python3 product/frame.py ask <her clip>`. Exit 1 prints
nothing: carry on. Exit 0 prints ONE clickable multiple choice (AskUserQuestion) from her footage's shape, reel or
YouTube video: ask it exactly as printed, unless she already said which. Record it as soon as the job has its name:
`python3 product/frame.py choose <job> reel|youtube`, and say the line it prints. It decides the frame everywhere after,
on both roads: the visual editor and the original widget. A YouTube video is edited the same way as a reel; nothing uploads.

The order, every reel: **her clip → the rough cut → she reviews it (the style plan) → the creative plan (teaching or
confessional asked there) → the build → the beat sheet → finish → export.** Past that first question, nothing about the
reel is asked before the cut: not the style format (a talking clip is a Yap; her footage says which, see CLAUDE.md), not teaching or
confessional (the creative plan's question, `graphics-plan`, after she has approved her cut), not the finish route,
the doneness or the style pack.

**The one question before the cut: phase by phase or autopilot, only once she can use autopilot.** Run
`python3 product/review_gate.py start` while her clips copy and transcribe. If she already said which ("autopilot",
"just edit it", "phase by phase", "walk me through it"), don't ask: record it with `python3 product/review_gate.py start
phase|autopilot` (the review gate reads it, so it is never skipped). Otherwise it prints nothing to ask until she has finished a reel in the visual editor (autopilot edits from
those); then it prints ONE clickable multiple choice (AskUserQuestion), saying what's new the first time. Ask it
exactly as printed, then record her pick with `python3 product/review_gate.py start phase|autopilot`. Autopilot loads
the `autopilot` skill.

## Where a job comes from (inbox → job)

**First, file her inbox:** `python3 product/inbox_sort.py`. It copies every sound, song, GIF, graphic, photo and font
she dropped in `inbox/` into the right drawer of `favorites/` and leaves footage for the step below. If it filed or
recognized anything, say its message as it prints (it tells her which inbox files are safe to delete). Nothing new:
say nothing about it. After the clip below is copied into the reel, tell her in one line that her clip is saved in
the reel's folder, so the inbox copy is safe to delete whenever she likes.

| She says | The clip |
|---|---|
| "edit this reel" / "let's make a Yap" (no path) | the newest video in `inbox/`, **copied** into a new `projects/<job>/raw/`, never moved. Empty inbox: tell her warmly and ask her to drop a clip in. |
| "edit the clip called ___" | that clip from `inbox/`, copied the same way |
| "edit the latest project" | the newest job folder |
| "cut [job]" / "edit the reel in [folder]" | that folder, or that path |

- **iPhone HDR clips are converted before anything else.** Right after the copy, run
  `python3 product/hdr.py <job>`. If it prints a heads-up, say that message to her word for word (it names how
  long, and which clips in a mixed folder), THEN run `python3 product/hdr.py <job> --apply`, then carry on. It
  runs on every new job, every time HDR is found: an HDR clip left as it is comes out grey and washed out in
  CapCut, and capcut-live and the builders refuse a draft that would play one. Her clips in `inbox/` are never
  touched; the job's HDR copies are kept in `projects/<job>/hdr-originals/`.
- **Sound and picture on one clock, right after the HDR step:** `python3 product/av_sync.py <job> --apply`. A clip
  whose sound starts after its picture (an iPhone clip copied out of Photos: 0.7 s) gets silence laid in front of its
  sound in the job's copy, the picture untouched, so the transcript and the cut agree and no cut lands early. Say
  its ✓ line in one plain sentence when it prints one; nothing printed but "nothing to line up" means say nothing.
  A reel heard before this existed (an older engine: choppy, a sliver of the word before repeating) catches up by
  itself the next time it is cut, re-cut, opened in her visual editor or exported from Finish (word-timings.sh,
  stitch-cut.sh, clean_cut and the editor all run it): the clip is lined up and that clip's word and cut times
  move by its lead, her hand fixes, trims and kept words with them, the old copies in `transcript/history/`.
  Never re-transcribe it for this. The ✓ line is the same one plain sentence.
- **The job's name** follows CLAUDE.md ("Naming a job"): what she would call the reel out loud, a few kebab-case
  words (`the-pricing-one`). The topic usually isn't clear before the transcript exists: start under a working
  name (`reel-in-progress`), and rename the job folder to the real name right after transcription, before anything else
  points at it (no draft, no page yet).
- **`intent.md`** holds what the reel is about. Write it yourself from the transcript (what it opens on, what they
  walk away with). Ask only if the transcript truly can't tell you (a near-silent clip, music only).
- **iPhone Cinematic mode: always cut the rendered `IMG_E….MOV` twin.** The raw `IMG_….MOV` carries a `dish`
  depth track that ffmpeg drops, so it cuts flat. Check:
  `ffprobe -v error -show_entries stream=codec_tag_string -of csv=p=0 "$CLIP" | grep -q dish && echo "RAW cinematic - use the E twin"`.
  Twin missing → say so before cutting (it has not been exported from Photos yet). Keep the raw file.
- **Filmed on a second phone too** (the other person's face, a wide shot): that file is never her footage, so it
  never goes in `raw/` (it would be cut as hers). Cut her clips as usual; once the cut is approved,
  `uv run product/sync_camera.py <job> <their file>` copies it to `assets/pip/` and syncs it by sound, and the
  `capcut` skill's `pip` lays it over her cut ("sync my second camera", "add his camera as a PIP").
- **A voiceover she wants to edit in her visual editor** (the `voiceover-reel` skill sends it here when she picks the
  editor road): her recording is the clip. `python3 product/visual_editor.py vo-start <job> <her recording>` copies it
  to `audio/`, lays it on a black 9:16 picture as `raw/vo.mp4` and marks the reel (`voiceover.json`). Skip the HDR,
  sync, Cinematic and second-camera steps (there is no footage). After transcription ask the voiceover's ONE
  question, punchy or emotional (your read marked from her delivery), and record it with `python3
  product/visual_editor.py vo-pace <job> punchy|emotional` BEFORE `transcript-cut.py`: emotional keeps her pauses up
  to about a second, punchy trims them tight. Then the cut, the stitch and the review gate exactly as for a Yap.
  On the Cut tab her phone shows a blank screen that says her clips go on in Visuals; never call it a fault. Don't
  ask where her b-roll is now: she picks the folder on Visuals (**Fill with my b-roll**), and **Media** still puts
  any clip on any line by hand.
- **The job folder:** `raw/` (any clip names, any count), `transcript/` (the durable `words.json` and
  `cuts.json`), `outputs/`, and optional `intent.md`, `audio/`, `assets/`, `thumbnails/`.

---

## What the cut keeps

**🔴 Her transcript decides the cut, never the volume.** `scripts/transcript-cut.py` reads her WhisperX words
as sentences and is the cutter: it drops earlier takes, restarts and false-start fragments as it cuts. Loudness
never chooses which lines survive. Once the words are chosen, sound has two small jobs: shortening dead air
inside a kept line, and telling snap-to-sound where a kept line's first and last words actually sound. It never
carries an edge off to some other quiet spot. Speed is never a reason either: every reel in a batch is cut
from its own transcript.

**Her last take wins.** A line she said more than once keeps the LAST delivery. Don't weigh takes against each
other. When two different phrasings say the same thing, the tighter one stays.

**Spoken cues stay.** A line where she names an effect and points at the line itself ("this is where the hook
goes", "this line is a karaoke caption") is a direction for the build, never meta-talk to trim.
`product/FIRST-REEL-SCRIPT.md` is made of them, and `product/spoken_cues.py` finds them after the cut.

**The cut opens on the hook.** Everything she says before it goes (the warm-up, the "okay so"). What that first
line has to do is the opener rule in CLAUDE.md.

**A clip with no talking is kept whole.** Her kids in the store, a vlog moment: the transcriber still returns
phantom words from the background sound ("Stavros Stavros"). Transcription marks such a clip silent and sets those
aside (`product/quiet_clips.py`: sparse AND unsure, so a real sentence is never dropped), and transcript-cut keeps
the whole clip. In the visual editor it reads as "No talking" lines she cuts by the second.

**Her rhythm stays.** A one- or two-word fragment that is only filler (the `FILLER_ONLY` words in
`transcript-cut.py`: um, uh, so, like, okay, yeah, well…) drops on its own. Filler inside a kept line is a
judgment call: a "like" that is her cadence stays; a "like", "you know" or "basically" that only pads goes, and
so does a trailing "so yeah".

**Also out, every time you build `cuts.json`:**
- every earlier take of a restarted line, stutters and false starts
- silences over 0.4 s
- side roads that serve neither what the reel opens on nor what she wants them to keep (`intent.md`)
- production noise: her checking the set mid-take ("let me make sure my sound is on", "Test."), a cough

**A line that reads wrong may be a mishear** (Notion → "motion"). Check the sound before cutting it.

**Every line earns its place.** If the reel would not miss it, it goes. Length is an outcome of that, never a
target (0:45 to 1:30 is where a cut usually lands). Register (teaching or confessional) is asked at the creative plan and changes how
loaded the graphics get, not this cut.

---

## The run

### 1. Transcribe once, for the whole reel

`bash .claude/skills/rough-cut/scripts/word-timings.sh <job_dir>` (WhisperX large-v3 + wav2vec2 alignment).
It saves `projects/<job>/transcript/words.json` and reuses it from then on (`--force` only if the footage
changed); nothing later transcribes again. About 10–20 s per 30 s of clip; with more than 3 min of footage, run
it with `run_in_background: true` and Monitor.

### 2. Write the cut

**One clip (the everyday case):** `python3 .claude/skills/rough-cut/scripts/transcript-cut.py <job> --print`.
It writes `projects/<job>/transcript/cuts.json` plus the scratch copy
`<temp dir>/reels-editing-engine/<job>/cuts.json`, which is the one the stitch reads. Hold the printed kept
lines against "What the cut keeps" and make any changes in **the scratch copy**.

**More than one clip:** write the scratch `cuts.json` by hand from the per-clip `words` arrays in
`<temp dir>/reels-editing-engine/<job>/words.json`:

```json
{ "segments": [ { "clip": "kitchen-take.mov", "start": 3.42, "end": 7.10, "transcript": "nobody tells you the first year is the hardest" } ] }
```

Segments play in list order. Give every one its `transcript`. trim-restarts doesn't run on a job with
several clips (the stitch says so), so listen for restarts yourself.

**Edges.** Start a segment 0.04 s before its first kept word's start stamp and end it 0.04 s after its last kept
word's end stamp, never inside a word. Where she pauses beside the word, snap-to-sound reads her voice and moves
the edge itself (the in-point 42 ms before her voice starts, the out-point 60 ms after it stops); where she runs
straight into the next word there is no quiet to read, the edge stays where you wrote it, and those 40 ms are
its only margin. A `[snap]` line reading `the plan cut N ms of "word"` is an edge it moved back out of her
voice. `SNAP=0` turns the pass off for one run; `"keep_edges": true` keeps one segment's edges exactly as
written. **Two takes in one word:** WhisperX can return a quick restart as a single long word ("Listen...
listen," as one). snap-to-sound looks inside every word longer than 0.82 s; at a segment's edge it keeps only
the take she meant, and in the middle of a segment it prints the time to split at, and you split there.

**Mis-stamped ends:** a kept segment far longer than its words is a WhisperX end stamped too late. Pull the
out-point back to the real last word. The re-listen backs this up.

### 3. Stitch with `stitch-cut.sh`

- **CapCut finish:** `FLAT_RENDER=0 bash .claude/skills/rough-cut/scripts/stitch-cut.sh <job_dir>`. About 8 s: snap,
  frame grid, EDL and corrected transcript, no encode. Go straight to the timeline (`capcut`).
- **HyperFrames render, no timeline:** `bash .claude/skills/rough-cut/scripts/stitch-cut.sh <job_dir>` builds
  `outputs/<job>.mp4` in one FFmpeg filtergraph (always in the background). The sound stays PCM until one
  master on the assembled track (+10 dB → voice master → −1 dBFS limiter; `WARM_MASTER=0` = flat +10 dB →
  −6 dBFS), then one AAC encode. Never encode per segment, never "optimize" to `-c copy`.

What runs inside it, and what you never rebuild by hand:
- **trim-restarts** (`scripts/trim-restarts.py`, MFCC + subsequence-DTW) removes restarts the transcript can't
  see. It cuts clean repeats and refuses rephrases. The stitch runs it with the WhisperX venv. Preview only:
  `~/.cache/reels-editing-engine/whisperx-venv/bin/python .claude/skills/rough-cut/scripts/trim-restarts.py <job> --print`.
  A real hand run needs `--cuts <temp dir>/reels-editing-engine/<job>/cuts.json`, or it overwrites the scratch
  plan. **Intel Mac: there is no venv, so this pass cannot run.** The stitch says so once. Don't hunt for a
  substitute (`product/INTEL-MAC-ROUTE.md`).
- **snap-to-sound** (`scripts/snap-to-sound.py`) sets each edge on the word's real sound ("Edges" above).
- **close-pauses** (`scripts/close-pauses.py`) listens to every kept piece and closes any held silence over 0.7 s
  to a natural beat, however the cut was made (a hand-written cut, a word stamp stretched over a pause, quiet before
  a line's first word). Pinned pieces (`keep_edges`: her editor edges, a clip with no talking) and `no_trim` words
  stay as they are; a your-turn cut skips it. `CLOSE_PAUSES=0` turns it off for one stitch.
- **clean_cut**: a cut that goes around `stitch-cut.sh` (cold-open, rewind, VHS, any bespoke stitch), or any
  hand edit to `cuts.json`, runs **`python3 product/clean_cut.py <job>`** before stitching
  (`from clean_cut import clean_cut` in a custom builder). Never trim a double-take or an edge by eye.

The stitch also writes **`outputs/<job>.transcript.json`**: the caption transcript mapped onto the cut, with no
second transcription. Captions, graphics and the finish all read it, and it is the one place her word fixes are
laid in (kept-words.py): `"words"` and `"phrases"` put a misheard word or name right without a sound, and
`"check"` words are printed for you as `⚠ REVIEW` to read where she said them. The tables, each laid over the
one before: `presets/caption-corrections.json` (every reel), `_local/caption-corrections.json` (the owner's own
words, never shipped), `projects/<job>/word-fixes.json` (this reel only). A mishear that keeps coming back
belongs in the shared table.

**Changing a stitched cut:** edit `projects/<job>/transcript/cuts.json`, copy it over the scratch plan, and
stitch again (an edit to the saved copy alone is undone by the next stitch):

```bash
python3 -c "import os,shutil,sys,tempfile; d=os.path.join(tempfile.gettempdir(),'reels-editing-engine',sys.argv[1]); os.makedirs(d,exist_ok=True); shutil.copy(os.path.join('projects',sys.argv[1],'transcript','cuts.json'),d)" <job>
```

Nothing may live only in `<temp dir>` (`tempfile.gettempdir()`; on macOS that is `$TMPDIR`, which macOS clears).
The durable copies are `projects/<job>/transcript/words.json` and `cuts.json`.

### 4. Catch new mishears (every job, right after the stitch)

`python3 .claude/skills/rough-cut/scripts/flag-words.py projects/<job>` lists the words nothing vouches for
(not her word fixes, not the speech model's own vocabulary, not the system wordlist) and says so in one line
when there are none. It sorts them by whether her other reels say them too, which is where the fix goes: a
word other reels share → `presets/caption-corrections.json` (or `_local/caption-corrections.json` when it is
hers alone); a word only this reel has → `projects/<job>/word-fixes.json`. A word heard wrong goes under
`"words"`; a name heard as several words ("square space") under `"phrases"`. A name already spelled right
needs nothing. Unsure → put it under `"check"` and mention it, never guess. Then
`bash .claude/skills/rough-cut/scripts/respell.sh projects/<job>` rewrites the script at once: the cut never
moves, and a `"phrases"` fix only re-spaces the words inside the time its own words had.

### 5. The re-listen (automatic after every render)

The stitch runs `verify-cut.py` after a render (`VERIFY_CUT=0` skips): an independent ASR pass that flags
misalignment and back-to-back stumbles. **Read only its summary.** On a ⚠: re-transcribe that raw window, find
the clean take's real times, fix the segment (as in "Changing a stitched cut"), stitch again.

- **At most two full re-listens per script.** verify-cut keeps the count. When the second still flags spots,
  stop fixing: hand the cut over and list those spots for her (line and time) with the style plan. A third run
  on the same script skips itself and prints them again. A change she asks for after her review is a new
  script: `verify-cut.py <job> --again` starts a fresh count.
- **verify-cut picks its own model:** one already on this computer before a download, and no bigger than
  `small` on 8 GB of memory or less. It names the model in one line. Never re-run `word-timings.sh` to re-check
  a window.
- Re-checking a short window: use `small` with `condition_on_previous_text=False` (smaller models invent
  repeats on short clips; larger ones swap on 8 GB); for where speech starts or stops, measure the RMS envelope,
  not ASR. A kept segment that trim-restarts flags under `0.5` confidence → re-listen there first.

---

## Her review: the style plan

The style plan is where she sees the cut (CLAUDE.md rule 2, spec in
[`product/style-plan-widget.md`](../../../product/style-plan-widget.md)). It is also the whole report: there is
no separate summary block.

**The visual editor or the original widget.** The style plan comes two ways. The **visual editor** (beta) is the
upgrade to the widget: her whole reel on one page in her own browser. She taps words to cut them or bring them back,
hears the cut instantly in her cut's order, swaps looks and sounds line by line and exports from its Finish tab, so a
review costs a command and a link instead of a widget. The **original widget** is the style plan in the chat, steps
1-4 below, exactly as the course videos show it ("text only" is the same thing). Every creator gets the choice, because
the course videos show the widget; the course lesson "The visual editor" walks her through the new one.

- **The review gate is the step after every rough cut, phase by phase** (the stitch's last line names it; autopilot
  never stops here, it opens the editor on her Sound tab): `python3 product/review_gate.py <job>` prints the exact
  clickable question (AskUserQuestion) or where her saved default goes. Ask it exactly as printed (nothing written
  before the box shows), then record her pick with `python3 product/review_gate.py <job> editor|widget`: it saves
  locks the reel's road and prints what to ASK or SAY and what comes NEXT. Her register answer: `python3
  product/review_gate.py <job> --register teaching|confessional`. Never skip it, never ask it in prose. The cases:
  - Her saved default (`visual` or `text`): straight there, no review question (`visual` still gets the
    teaching-or-confessional pick-one below, right before it opens).
  - Otherwise: "Your rough cut is done. Would you like to try the new visual editor? It's an improved editing
    experience, giving you more visual control and faster results, and it uses fewer of your Claude tokens. Or would you
    like to continue with the original widget?" **Try the new visual editor (Early access, in beta)** · **Continue with the original widget**. Picking the editor
    gets ONE more clickable multiple choice, exactly as `pick` prints it: "Before you switch over: do you want to make
    the visual editor your new default, or just try it out this one time?" **Make the visual editor my new default** ·
    **Let me try it once before deciding**. Record it: `python3 product/review_gate.py <job> --default always|once` (always =
    her default from now on; once = this reel only, asked again next reel); it prints the register question next.
    Picking the widget = this reel on the widget; the question comes back next reel.
- **Her words decide, any time, in any session** (they outrank the saved default, for this reel):
  - "the original widget", "the old widget", "the widget", "the old style plan", "text only", "in the chat" =
    the original widget for this reel (steps 1-4; if her editor page has unsent changes she pastes STYLE PLAN EDITS,
    apply them first, below). When the editor is her default, asking for the widget switches her back for good:
    `learned.py add review.style_plan_mode text`, and say "Switched you back to the original widget. The visual
    editor is there whenever you want it: just type "open my visual editor"." (Also when she adds "always", "from now
    on" or "stop asking".)
  - "the visual editor", "open the editor", "open my visual editor", "show me the visual editor", "where's the visual
    editor", "the new one" = `open` below. With "always" / "from now on" = also
    `learned.py add review.style_plan_mode visual`.
  - Never argue for either one. Both are complete; the choice is hers.
- **Once she picks the visual editor, that reel stays on it to the end.** `open` locks it
  (`python3 product/review_route.py <job>` says `editor`), and every later step follows the editor road: "looks",
  the Sound tab, the Storyboard and the export on her Finish tab, `finish.py` for "render". Never slip back to the
  widget, a creative-plan table to approve in the chat, the doneness pick-one, or a Clean/Super Yap CapCut build
  (those builders refuse a locked reel). Only her own words for THIS reel switch it: run `python3
  product/review_route.py <job> widget`, then give the widget. Picking the original widget = `python3
  product/review_route.py <job> widget` too, so the record matches her pick.
- **Before the editor opens: teaching or confessional.** Picking the visual editor (or her saved default `visual`)
  always gets ONE more **clickable multiple choice** first, "Before I open your editor: is this a teaching or a confessional reel?",
  your read marked (Recommended) from the gate's lean and the kept words, with one line of why. Record it:
  `python3 product/review_gate.py <job> --register <it>`. It is the register the creative plan
  uses when she says "show me my looks" (`graphics-plan` takes it as answered). The original widget never gets this
  question here: on the widget road it stays at the creative plan.
- **Visual:** `python3 product/visual_editor.py open <job>` (makes the preview copy once, about half a minute,
  then opens her browser; the visual editor is in **beta**). If it exits 2, say its one-line reason and give the
  text-only style plan instead. Your final message STARTS with the `EDITOR LINK:` line `open` prints, pasted into
  the chat word for word (it is a markdown link; never skip it, never reword it: her browser often opens behind
  this window, and that link is how she gets in), then what she is looking at and how phase 1 goes, "edit, press **Send my cut** (your cut updates right
  there, in seconds), and when it feels right press **Lock in my cut**". The first time she opens it, the page greets
  her with what replaced the widget and a few quick tips (they replay from **Show me around**), so don't re-explain
  the page in the chat. No rough-cut link yet: the page IS the
  preview (a lean one, said on the page). **Then surface the re-listen's flagged spots:** run
  `python3 product/relisten_flags.py <job>` and, whenever it prints any, include its lines in that same message
  so she ear-checks them on the page before the cut moves on. It prints nothing when the cut is clean, so it runs
  every time. Never present the cut as clean while it prints spots.
- **She asks how to do something on the page, or whether it can** (trim dead space, remove a pause, move or swap a
  look, nudge a sound, export): read [`product/VISUAL-EDITOR-GUIDE.md`](../../../product/VISUAL-EDITOR-GUIDE.md)
  and answer from it, with the exact button or gesture. Never tell her the page can't do something it does, and
  never move a reel off the editor to CapCut for a job the page does. Trimming dead space at a clip's start or end
  is on the page's timeline, like CapCut (drag the clip's edge, or **Cut before / after playhead**, Q / W); a pause
  in the middle of a line is **Split** at the playhead (B) and then dragging the two new edges together. A note
  (**Awkward pause**) or her ask in the chat still works: you split the clip and `restitch` ("She types notes", below).
- **Phase 1 runs on her page, not in the chat.** Send runs the lean round itself (seconds: her edits, clean edges,
  captions, no video encode); the page switches to the new cut by itself. Words she brought back are kept from the
  double-take pass. **Lock in my cut** locks phase 1 in at once: what she set on her page IS her cut (she reviewed it
  by ear, so no second cleaning pass and no stumble check). Its full-quality video is made ONCE, at Finish, together
  with her looks and sounds (`finish.py` → `finish_cut(exact=True)`), so she never waits between layers. If she says "sent" anyway:
  `python3 product/visual_editor.py status <job>` and tell her where it stands (usually: already updated on her page).
- **She types "open my editor", "open my visual editor" or "show me the visual editor"** (the page says to after the
  editor rested while she was away; the engine tells her to whenever she can't find it): `python3
  product/visual_editor.py open` opens her most recent reel with a rough cut (or `open <job>` for the one she names).
  It works from any session, even on a reel she started in the widget. Her unsent edits come back from the
  page itself; everything she sent, swapped or added is already saved in the reel. Paste the `EDITOR LINK:` line it
  prints into the chat word for word, every time (whether or not her browser came up), plus one line: if it ever
  disappears, double-click "Open my visual editor.html" in her engine folder. No rough cut yet = it says so: make the
  cut first.
- **She can't see or reach the editor** ("where's the visual editor", "I can't find it", "it never opened", "I only
  got the widget", "the page won't load"): open it for her (above), then tell her in one line that from now on she
  can just type "open my visual editor" or "show me the visual editor" any time. It is almost always an engine that
  came in through /update from before the editor (fresh installs meet it after their first cut): the update's
  rundown only covered the newest version, and the chat she updated in started on her older instructions, so also
  suggest a new chat. If it still won't open, give her that tip with the original widget for this reel, and
  `/report-a-problem` for the rest.
- **She types "text only" or "the original widget"** (the page's safety panel tells her to, when it can't load):
  give the original widget (steps 1-4). If she pastes text starting STYLE PLAN EDITS with it, apply that first (below), so nothing she
  did on the page is lost.
- **She wants a different style pack mid-build** ("switch it to Editorial", or the Lookbook's pack tabs): `python3
  product/visual_editor.py pack <job> <Pack>` (the page's "Use <Pack> for this reel" button does the same). Every look
  she picked from the lookbook redraws in that pack at the same moments; graphics made just for this reel stay as
  built. From then on `review/pack.json` is her pack for this reel: anything you draw or redo uses it.
- **The watcher: her page moves the edit along without her typing anything.** Right after you hand her the editor
  (and again after every round you finish for it), start it IN THE BACKGROUND (Bash with run_in_background):
  `python3 product/visual_editor.py wait <job>`. It returns the moment she leaves Claude something on her page (a note,
  a Sandbox idea, a new look, looks to redo), already claimed, so her card says "Sent to Claude" and then "Claude is on
  your changes". When it returns, do exactly those items the way "update my edit" does (Sandbox ideas: the
  `build-a-look` skill; `[make-looks]` = she locked in her cut: do the "show me my looks" step below; `[fill:…]` =
  her voiceover's b-roll: the "fill my b-roll" step below). Start it again
  the moment it returns (before doing the items), so anything she sends meanwhile is still picked up; it refuses a
  second watcher for the same reel, so starting it twice is harmless. "WAIT: nothing new" = it timed out after about an hour: start it again,
  say nothing. "STOP: her page has been closed" = her page was closed or untouched for 30 minutes: do NOT start it
  again and say nothing; "open my editor" (or her next ask about the reel) starts it again. "stop listening" from her
  = stop it and don't restart it. Never run it in the foreground; never start two for one reel.
- **She typed in the chat panel (the watcher hands you a `[chat:…]` item).** She messaged you right on her page, in
  the chat beside the preview. Do what she asked on the reel the way "update my edit" does, then reply to her IN THE
  CHAT: `python3 product/visual_editor.py tell <job> "<one short line>" --chat`. Her message and your reply sit
  together in that thread; the todo line quotes exactly what she typed. This is a normal conversation, so answer in her
  voice, one plain line, and let the reel change itself be the proof.
- **She is on her page, not in the chat: whatever you have for her goes to her page too (`tell`).** Once her editor
  is open for a reel, every time your reply ASKS her something (a pick-one, an approval, "which take?", "ready to
  render?") or HANDS her something that isn't on the page by itself, first run
  `python3 product/visual_editor.py tell <job> "<one plain line>" [--chat] [--go sandbox|notes|cut|visuals|sound|finish]`.
  Her page shows it in the chat panel beside the preview (on every tab) as a message from you, and the bell keeps it;
  in another tab the tab's title says so, plus a browser notification (when she allowed it) and the soft chime.
  `--chat` = it's a reply in the back-and-forth and reads as one ("Teaching or confessional? Tell me in the chat."); `--go` = its button takes her where the news
  is. Run it BEFORE the question box (a command after the box waits until she answers). One line, her words, no
  jargon. It prints whether her page is open. Don't `tell` what the engine already pops by itself: sketches landing
  (`sandbox-takes`), a note fixed (`resolve`), a new look placed or kept (`place-look`, `look-request ... done`), her
  looks made (`looks`, the first time for a cut), an export done or stopped (Finish). The chat's question box and
  permission prompts also pop a plain "Claude has a question for you" on their own (the `editor-says.sh` hook) and
  take it down when she answers; your `tell` is the specific line, so say it when you can.
- **She asks to layer her page edits into her CapCut version** (the page says "ask Claude in the chat" after a CapCut
  export, when she wants what she changed there kept): never rebuild from the page. With CapCut quit
  (`draft_safety.require_capcut_quit()`), copy her newest version: `python3 -c "import sys; sys.path.insert(0,'product');
  import draft_safety as d; print(d.duplicate_draft('<base> <N.M>'))"` (her draft stays untouched; the copy is the next
  number). For each look she changed on the page, render it (`python3 product/reel_render.py render <comp_dir> -o
  projects/<job>/hf-graphics/finish/<layer>.mov`) and put it on its own track in the copy: `JOB=<job> CAPCUT_DRAFT='<copy>'
  python3 product/build-overlay.py projects/<job>/hf-graphics/finish/<layer>.mov <layer>` (updates that track in place,
  keeping her CapCut position, size and keyframes; adds it if new). A look she took off: `CAPCUT_DRAFT='<copy>' python3
  product/remove-overlays.py <layer>`. Sounds and cut changes aren't carried this way: name them, and she sets them in
  CapCut (or she exports a fresh version from the page). Say which version holds it, then the usual handoff lines.
- **She types "update my edit"** (the page's "Your preview is waiting on N changes" card hands her that line):
  first start the watcher in the background (`python3 product/visual_editor.py wait <job>`, as in "The watcher"
  above; never ask, she wants it on every time), then `python3 product/visual_editor.py todo <job>` lists everything waiting for you, in order: cut notes, look notes, section notes,
  looks you built for her old cut, new-look ideas. Do each the way its own step below says (cut notes as "notes";
  a look note: change that look, then `resolve`; a reel note (Visuals, Sound, Finish): do it, through `learn` when it says "every reel", then `resolve`; a look to redo: rebuild it on her new cut as in the looks step,
  then `visual_editor.py looks-current <job>` once every one is redone; an idea: the `build-a-look` skill). Her
  page picks each change up by itself; end by saying what's next. Nothing left = say her preview is up to date.
- **She types "fill my b-roll"** (her Visuals tab hands her that line after she picks a folder on **Fill with my
  b-roll**, or the watcher hands you `[fill:…]`): her folder (in `inbox/`), what she said and, on a talking head, the
  lines she ticked are in `review/broll-fill.json`, and the todo line quotes them. A voiceover gets a clip on every
  line. **A talking head gets b-roll ONLY on the lines she ticked** (her page's line numbers, the same numbers
  `vo-lines` prints); her face stays on the rest, and `broll-fill` refuses a line she didn't tick. Say in one line that this one takes a little longer,
  because every clip gets watched. Then:
  1. **Watch her clips, two passes.** `python3 product/visual_editor.py vo-sheets <job>`: contact sheets of every
     clip in her folder (seconds; each frame fetched by jumping to it), one row per clip, the second under each
     frame. READ them; never pick from a file name. That decides which clip goes where. Then, for a clip whose exact
     moment matters (an action, a reveal), a closer look: `vo-sheets <job> <media id> <from> <to>`. Never hand-roll
     ffmpeg contact sheets (they play the whole clip through: a folder of long phone clips took minutes). A
     `clip-catalog.md` in the folder: read it first and only watch clips not in it. No grab files and no question
     batch: her instructions box already said what she wants.
  2. **Her shots:** `python3 product/visual_editor.py vo-beats <job>`: her words cut into shots by the cut rules
     (a cut on a word end, best at a sentence end, then a pause, then a comma; never right after a word that leads
     on; how long a shot holds follows her pace, punchy 1.4 to 2.6 s, emotional 2.6 to 4.8 s; a voiceover opens on a
     burst of quick cuts). A shot can run across a line break; that's the point. On a talking head, only her ticked
     lines. (`vo-lines` still lists her lines and her folder's clips with their lengths.)
  3. **Match by meaning**, shot by shot, her words first: a clip that shows what the shot says, energy matched (a
     fast shot on a moving clip, a held one on a still clip), no clip twice in a row, the strongest shot on the hook
     and the payoff on the last. When a clip's action needs longer than one shot (a box opening, a lid coming up),
     give it two or three beats together (`"beats": [8, 9]`). Pick the moment in each clip (`slip`, seconds into
     her clip; the subject in frame, nothing flickering); leave it out and the engine picks the clip's best moment.
     Never a clip shorter than its shot (that leaves black): `vo-lines` gives each clip's length.
  4. **Lay them on:** write the plan (`{"fills": [{"beat": 1, "clips": [{"media": "inbox:<folder>/<file>", "slip":
     4.5}]}, {"beats": [8, 9], "media": "...", "slip": 0.3}, ...]}`; `"line": n` and `"start"`/`"end"` still work)
     to the temp dir and run `python3 product/visual_editor.py broll-fill <job> <plan.json>`. It makes every clip
     first, side by side, keeping only the stretch around its moment (about 30 seconds for 30 clips), then lays them
     on. On a voiceover every clip runs on to the next one, so the breath between shots never goes black; on a
     talking head the shots in one run of ticked lines play back to back. A fill again replaces only what the last
     fill laid (never a clip she put on with Media). It prints anything still uncovered on a voiceover: cover it or
     say it.
  5. Her page picks them up by itself (each one is an ordinary cutaway she slips, trims or swaps). Say what went where
     in two or three lines, then offer the clip catalog ONE time (`voiceover-reel` step 3c, same wording).
  If her captions aren't on yet, the looks step comes next as usual; on a voiceover the captions follow the
  `voiceover-reel` rules (karaoke build + one takeover, no hook card).
- **She types "notes":** `python3 product/visual_editor.py notes <job>` lists each open note with its line, word and
  footage time. Fix each in the scratch plan (copy `transcript/cuts.json` into `<temp dir>/reels-editing-engine/<job>/`
  first): *sounds clipped* = move that piece's edge 60-120 ms away from the word (never into the next word), or give
  it `"keep_edges": true` / `"xfade": 0.030` as sound-check advises; *awkward pause* = split the piece around the
  gap; *wrong take* = use the other take from `transcript/words.json`. Then `python3 product/visual_editor.py restitch
  <job>` (a lean round, seconds) and `python3 product/visual_editor.py resolve <job> <note-id> "<one plain sentence of
  what you did>"`; the page shows "Fixed: …" on the line and pops it as a card (several fixed together are one card). A note you can't fix (a mumble in the audio itself): say
  so plainly in the resolve sentence. Then tell her to listen on the page and press **Lock in my cut** when happy.
- **A note tagged "every reel"** (the page writes `[Cut · every reel]`, `[Visuals · every reel]`, `[Sound · every reel]`
  … when she ticks *Make this my default for every reel*): make the change on this reel as usual, THEN make it real
  for every reel. If it is something the engine can remember (`product/learned.py` FIELDS: sizes, placement zones,
  caption size, SFX density, the opener zoom, named text effects, review choices), save it with the `learn` skill
  (`learned.py` + brand-kit Part C) and say in the resolve sentence what will happen on her next reel. A favorite
  sound or look belongs in her favorites folder or lookbook instead (put it there). Anything else can't be carried
  to the next reel safely (register, route, hook copy, a placement number): resolve with one plain sentence saying
  why, and that it was done for this reel. Never tick it off silently.
- **She types "show me my looks"** (or "looks", "move on to my looks", "on to the visuals", or says the cut looks good, with no beat sheet open: after a beat sheet, "looks good" is
  the `beat-sheet` skill's): open notes come first. On the page path her locked-in cut IS the cut: never run
  `finish-cut` here (Finish makes the video, exactly as she set it), and place looks on her kept-words transcript,
  which the page's Send already rewrote; `subject-zones.json` from the rough-cut video is still right (same footage,
  same framing). Then phase 2 (the creative plan). The rough-cut link (step 4) is for the text-only review only;
  on the page path the page is the preview. Off the page (the widget road), never build looks or a CapCut draft on
  a stale base cut: `check-base` exits 1 → `finish-cut` first.
  **On the page path the creative plan asks ONE thing: teaching or confessional.** There is no raw / medium /
  well-done pick-one: where the reel goes is her Finish tab (CapCut or an MP4), and the looks are drawn now and
  rendered there. The pack: `review/pack.json`, else `python3 product/choices.py defaults`; with neither (her first
  reel), ONE pick-one for the pack. Build the looks with exactly these, nothing hand-rolled (they draw, never
  render, and key each look to its words so it follows every later cut change):
  `python3 product/visual_editor.py place <job> <look> <start> <end>` for each beat of `graphics-plan.json` (cut
  seconds; the look's id from `lookbook.py list --pack <pack>`; a hook look (hook, eyebrow + headline, headline +
  subhead) needs `--text "eyebrow / headline"`: its own punchy reframe written to `WRITING-THE-HOOK.md`, never her
  spoken sentence, and `place` draws nothing without it), and `python3 product/visual_editor.py captions
  <job> <style>` for her captions. The page updates by itself.
  If she asks for type she can retype in CapCut (the raw route, CapCut's own text), that is the chat route: say
  so, and build it the text-only way.
- **Her looks show on the same page (phase 2, rendered routes).** Once the build has written the graphics
  (`hf-graphics/`, `hf-captions/`, `hf-reel-type-*/`) and, when offered, the beat sheet, run
  `python3 product/visual_editor.py looks <job>`. Her open page picks them up by itself and plays every graphic
  live over the lean preview, timed to the cut, with each line's look described under it, and (the first `looks` for
  her current cut) pops "Your looks are ready" on her page. No render, no tokens. Tell her in one line: "Your looks are on your page. Press play to watch them." What the lean preview can't
  show (behind-her-head) plays in front of her with a plain note saying the final render puts it behind; never
  call that a fault. Run `looks` again after any graphics change and the page refreshes in place.
- **Accents on the page:** in the looks step she taps a word → **Accent** (or `A`); the pack's ONE accent look
  shows on it live in the script and the captions, and saves to `transcript/accents.json` by itself.
- **Rendering runs from the page now.** The tabs are layers, Cut · Visuals · Sound · Finish (a change to one locks the
  ones after it until she locks it in), the main button walks her forward, and in **Finish** she picks Into CapCut or
  Export an MP4 and presses Export; `product/finish.py` renders each look in `review/looks.json` through
  `reel_render.py` (every check), then `capcut_handoff.py --layer NAME=FILE@START` or `burn_layers.py` plus a
  phone copy. Finish refuses while notes are open, so handle them when she types notes. While she reviews her cut,
  Lock in my cut is instant (the video is made at Finish). If she changes her cut after her looks exist, the layers after Cut lock until she locks the cut in again; then the page moves every look she added with its words by itself (`visual_editor.py`'s retime_adds). Looks you built for the old cut need you: the card then says so and hands her "update my edit" (above).
- **She types "render" in the chat instead** (the page marks phase 3): first
  `python3 product/visual_editor.py notes <job>` and handle every open note (look notes start "[Look: …]": change that
  look, then `resolve`); she never has to type "notes" for these. Then
  `python3 product/visual_editor.py accents <job>`; if it lists changes, rebuild the captions with exactly that
  accent list (a per-reel build: its `hf-graphics/picks.json` "accents" start times; the engine's builders: the
  plan's accent words), then `python3 product/finish.py run <job> capcut` (or `mp4` for an exported file, her
  pick on the Finish tab when she made one), exactly what the page's Export button does: same checks, same CapCut
  versioning, same sounds. Never hand-roll a render or a handoff beside it.
  **Render the graphics `review/looks.json` lists**, not the original build's list: a line she swapped carries the
  new look's folder (`hf-graphics/_looks/<line>/<look>/`, drawn by `product/lookbook.py`) at the same moment. Her
  original build's files are never changed by a swap, and "Your original" in the Swap menu puts one back.
- **Swap a look / See all:** each look card on the page has **Swap look** (her lookbook drawn on that line, live:
  `visual_editor.py`'s `swap_menu` / `swap`) and the header has **See all looks** (every look numbered, like the
  beat sheet; notes by number come to the chat). Neither needs you; they run on the page. Her notes on a look come by line number in the chat.
  If she cuts a word during the looks step and sends it, the page goes back to the cut step; rebuild the
  affected graphics on the new cut, then `looks` again.
- **Nothing arrived, or she pastes text starting STYLE PLAN EDITS:** that is the fallback from "Copy your cut".
  Pipe it in exactly as pasted: `printf '%s' '<her text>' | python3 product/visual_editor.py apply <job> --code -`.
- If apply refuses (the transcript changed since the page was made, edits from another reel), say its reason in
  one line; nothing has been cut. Notes she types by line number in the chat still work the text-only way.

1. **Bookkeeping first.** Run `python3 product/build-style-plan.py --which` (and any `learned.py` step it
   asks for), plus `python3 product/spoken_cues.py <job>`, before the review goes up.
2. **One style plan per review, exactly.** First review → the widget from
   `python3 product/build-style-plan.py projects/<job>` (or the lean table if she switched the widget off).
   Every re-cut → the lean table (`# | line | dur` plus the total). The lean table is also the fallback when
   `show_widget` isn't available. **🔴 One `show_widget` call, never twice, never widget plus table.** Then wait
   for her edits.
3. **What it carries:** the raw length and the cut length · each spoken cue `spoken_cues.py` heard, with a note
   that you'll build it on its line · one row per kept line · a ⚠️ on any row you would cut, with the reason in
   a few words.
4. **Your words go in the turn's FINAL message, after the widget.** Text written before a tool call is folded
   away in the app. Open with what she is looking at (*"This is just your clips cut down. No graphics or
   captions yet, that's next."*), then **the re-listen's flagged spots** from `python3 product/relisten_flags.py
   <job>` (run it with the bookkeeping in step 1, before the widget, since no tool call may follow it): whenever
   it prints any, include its lines here so she can ear-check them, and never call the cut clean while it does;
   it prints nothing on a clean cut, so it costs nothing to run every time. Then **end on the markdown link to
   the cut** from `python3 product/style_plan_link.py <job>`, the last thing said. It opens the side-panel
   player. No tool call after the widget, never a SendUserFile/attach card, never `open` the MP4.

---

## What comes next

Once she approves: creative plan (`graphics-plan`, where the register is asked) → the build → captions →
optional music → export (`scripts/name-final.sh`). Finish specs: `workflows/short-form.md` (reframe, safe zones)
and `product/FLOW.md` (the route she picked). Captions follow the route: CapCut Auto Captions on the CapCut
route (she runs them); on raw or medium the engine can build them; well-done bakes them. Every caption reads
`outputs/<job>.transcript.json`, never a second transcription. `presets/clean-captions/build.py` is the older
path (`pull-reels --captions clean` and its fallback only). Posting stays with her.
