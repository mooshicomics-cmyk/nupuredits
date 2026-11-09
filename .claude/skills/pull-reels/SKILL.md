---
name: pull-reels
description: "Finds the reels hiding inside a long video she already put out (a Live replay, a podcast episode, a course lesson, a long YouTube video) and builds the ones she picks. Transcribes it once, ranks every moment that could stand as its own reel, tags each one teaching or confessional, and waits for her picks. Each pick then builds like any reel the engine makes: the rough-cut stitch and sound, a 9:16 frame around her face (or the whole shot over a soft blur), captions and a hook card in her style pack. The long video itself is never re-edited. Triggers: pull reels, pull reels from my live, pull reels from <video>, find the reels in this, what reels are in this video, get reels out of my replay, mine this video for reels, reels from my podcast, reels from this lesson, make reels out of this long video."
---

# Pull Reels

She already said it once, on a Live, a podcast, a lesson. Some of those minutes are reels as good as anything
she would film on purpose. This skill finds them, lets her choose, and builds the ones she chooses through the
same engine as every other reel. The long video stays exactly as it went out.

**You direct. Claude edits** holds here too: Claude does the listening and the ranking, she does the picking.
Nothing renders before she has picked.

---

## Phase 1 · The video comes in

1. **Use the version that went out.** A Live replay, the exported podcast, the published lesson. Never the raw
   recording of a job that was edited before it went out: the edit moved everything, so the raw timings point
   at the wrong words.
2. **Make the job.** `projects/<video-name>-reels/`, with the video in `raw/`. Hardlink it if it already lives in
   this engine, copy it if it does not, and never move her original (the same intake rule as `inbox/`).
3. **Transcribe it once.**

   ```bash
   bash .claude/skills/rough-cut/scripts/word-timings.sh projects/<job>
   ```

   A long video is slow through WhisperX large-v3. That is worth it, and it only happens once: the run skips
   itself when `transcript/words.json` exists (`--force` redoes it). Every reel pulled later reads this one
   transcript.

## Phase 2 · Finding the reels (the judgment)

Read the whole transcript the way her audience would meet each moment: scrolling, cold, with no idea a longer
video exists. Every candidate goes through the same doctrine a filmed reel does, in this order.

**Register first.** Is this moment teaching or confessional? Tag it, because it decides everything after:
how the reel ends, what the hook card does, and how much goes on screen. The register rules in `CLAUDE.md` apply
unchanged. A confessional reel stays lean.

**Then the opener.** The first sentence predicts the reel (the opener rule in `CLAUDE.md`). On a long video
the best opening line is often a minute in, so the reel starts there, and the setup only comes back in if the
reel needs it. Never open on a warm-up ("so", "okay so today", "let me tell you"), and never on a number about
her: move the proof later, the way the rule says.

**Then the landing.** A teaching reel lands on the thing she wants them to keep. A confessional reel lands on
the line that names the feeling; it does not need to wrap it up. If a moment never lands, it is not a reel, however
good the opener is.

**Then everything that points elsewhere.** A Live is full of lines that only work live: "if you just joined",
"I'll get to your question", "like I said at the start", reading a comment, a screen she is sharing. Cut them
out of the reel. If the moment falls apart without one, leave the moment.

**Then the cut.** A pulled reel is cut as tight as any rough cut. Its pieces can come from anywhere in the
moment, filler and side roads removed. A line she said twice keeps the last take, as always.

**How many.** No quota. Every moment that passes, strongest first, and she picks. If she named a number, give
her that many plus the next two as spares.

**How long.** The tightest cut that delivers, the same as every reel (`workflows/short-form.md`). A reel that
wants to run past about a minute is often two reels; say so instead of padding one.

## Phase 3 · Her picks ⏸

Write two files into the job folder, then stop.

**`reels-plan.md`** is what she reads. One row per candidate, strongest first:

| # | hook card | name | from | length | opens on | why it stands alone |
|---|---|---|---|---|---|---|

- **hook card**: the card as it will show, its two lines split with `/`.
- **from**: where it starts in the long video, as she would scrub to it (`21:07`).
- **opens on**: the first spoken words, so she hears the opener before she picks it.
- **why it stands alone**: starts with the register (`teaching:` / `confessional:`), then one line on why it
  needs nothing else.
- A ⚠️ goes on any pick that is a judgment call (it only lands for someone who already follows her, it names a hard topic, a
  line had to move to obey the opener rule), with the reason. Never hide a doubtful pick by leaving it out.

Above the table: how long the video runs, how many reels it holds, and the two or three strongest. Then wait.
She picks by number or name, or changes a hook, a start, an end. Changes go into the plan, never straight into a
build.

**`reels-plan.json`** is what the builder reads (fields below). It holds the same reels in the same order.

## Phase 4 · Building her picks

Trim `reels-plan.json` to her picks, or name the picks on the command line, then:

```bash
python3 .claude/skills/pull-reels/scripts/cut-shorts.py build <job>                    # every reel in the plan
python3 .claude/skills/pull-reels/scripts/cut-shorts.py build <job> <name> [<name> ...]  # only these
```

`set-up` in place of `build` makes the folders and stops. Every reel becomes an ordinary job folder at
`projects/<job>/reels/<name>/`, and builds in four steps:

1. **The cut.** `stitch-cut.sh`, the rough-cut stitch itself: restarts trimmed, every boundary snapped to the
   sound, the static audio chain, `sound-check.py`'s report. If sound-check says the limiter is working hard,
   rebuild just that reel at the gain it names: `VOICE_GAIN_DB=<gain> python3 … build <job> <name>`.
2. **The frame.** A 9:16 1080x1920 base. The wide cut is kept beside it as `outputs/<name>.wide.mp4`.
3. **The type.** Captions from the first word to the last, plus the hook card.
4. **The export.** `outputs/<name>.final.mp4`, with a copy in `~/Downloads` (or `REELS_EXPORT_DIR`).

One reel failing never stops the rest. The run names every failure at the end.

### Framing: around her, or the whole shot

| | What she gets | When |
|---|---|---|
| `fill` (default) | Full screen, cropped around her face (`workflows/head-framing.py`); the middle of the frame when no face is found, which is normal while she shares a screen | She is the shot |
| `fit` | The whole wide frame, nothing cropped, over a blurred and slightly darkened copy of itself | What matters sits off to the side, or the room is part of the story |

Vertical footage is used as it is either way. When the source is wide and she has not said, ask once, as a
pick-one with `fill` marked as the default. One reel can differ from the batch: `"framing": "fit"` on that reel in
the plan, so a rebuild keeps it. `--framing fit` sets the whole batch.

### Type: her style pack, with a safety net

By default every reel is typed in her style pack (beta), exactly as a finished single reel is:

- `subject-zones.py` measures where she is in THIS reel, so captions sit just under her chin and nothing lands on
  her. On a `fit` reel it measures the sharp picture only, never the blurred copy behind it.
- The plan's `hook` becomes the pack's hook card, held for `hook_end` seconds.
- When she is framed so high that the card would sit on her head, the card moves into the open room under her
  chin and the captions wait until it comes down. This is automatic; the build says so in one line.
- `build-reel-type.py` → `reel_render.py` (every render check) → `build-reel-mp4.py` bakes it onto the base.

The pack is her saved default (`product/creative-vault/user-style.json`), or `--pack <Pack>` for this batch.

**The safety net.** If the pack route cannot finish a reel for any reason (no pack chosen yet, a render check
refused, anything), that reel gets Clean Captions instead and the build says why, in one line. A reel never comes
out uncaptioned. Tell her which reels fell back, and why, in plain words.

`--captions clean` (or `"captions": "clean"` on one reel) asks for Clean Captions on purpose: plain line
captions and one hook card. It is quicker, since nothing renders.

These reels are finished files, so the CapCut question is not asked one reel at a time. Any one of them can
still go to CapCut afterwards (see After).

## Phase 5 · Her second look

She watches them. Every change goes into `reels-plan.json` (a later start, a different hook, a reel dropped)
and only what changed rebuilds, named after the job: `build <job> <name>`.

---

## `reels-plan.json`

```json
{
  "job": "spring-launch-live-reels",
  "source": "raw/spring-launch-live.mp4",
  "reels": [
    {
      "rank": 1,
      "name": "the-quiet-week-after",
      "register": "confessional",
      "opens_on": "Nobody tells you the week after is the hard part.",
      "stands_alone": "names the crash after a big week, lands on the line about sleep",
      "hook": ["the week after", "nobody posts about"],
      "hook_end": 8.0,
      "length": 31.4,
      "segments": [
        { "start": 1312.40, "end": 1329.95, "transcript": "the opener and the two lines that set it up" },
        { "start": 1336.10, "end": 1349.95, "transcript": "the landing, with the comment she read aloud cut out" }
      ]
    }
  ]
}
```

| Field | What it holds |
|---|---|
| `rank` | Its place in the plan, strongest first. Matches the `#` in `reels-plan.md`. |
| `name` | The reel's job name: a few kebab-case words for what it is about. Unique across every job in the engine (see Watch for). |
| `register` | `teaching` or `confessional`. |
| `opens_on` | The first spoken words of the reel, as cut. |
| `stands_alone` | One line on why it needs nothing else. |
| `hook` | The hook card, one string per line, two lines at most, written to `workflows/capcut-export/WRITING-THE-HOOK.md`: never her spoken opener, a label she can repeat, and on a confessional reel it names the tension without resolving it. Leave it out or `[]` for no card; captions run either way. |
| `hook_end` | When the card comes down, in seconds into the REEL, not into the long video. `8.0` is the engine's usual hold. |
| `length` | Total reel length in seconds (the segments added up). For her table; the builder works it out itself. |
| `segments` | The cut, in the ordinary `cuts.json` shape and in seconds into the LONG video. `xfade` and `keep_edges` work as they do in any cut; `clip` is filled in for you. |
| `framing` | Optional, this reel only: `fill` or `fit`. |
| `captions` | Optional, this reel only: `pack` or `clean`. |

---

## Watch for

- **Two clocks.** `segments` count seconds into the long video; `hook_end` counts seconds into the reel. Mixing
  them puts the card over the wrong words.
- **Reel names share space with every job.** The scratch folder (`<temp dir>/reels-editing-engine/<name>/`, from
  Python's `tempfile.gettempdir()`, which is not `/tmp` on macOS) and the `~/Downloads` copy are keyed on the name
  alone. A reel named like an existing job overwrites its scratch and its export.
- **A rebuild starts from the plan.** The plan is the record. Anything hand-edited in a reel's folder is
  rewritten the next time that reel builds, except a word fix (below).
- **A word the transcript misheard** in one reel goes in that reel's own `reels/<name>/word-fixes.json`,
  the same per-job word fix every reel has. The builder never touches that file, so the fix survives rebuilds.
- **A shared screen gets the middle of the frame** on `fill`. If the part worth seeing is off to one side, give
  that reel `"framing": "fit"`.

---

## After

Each reel is an ordinary job folder, so every other skill works on it as is: `background-music`, a
`graphics-plan` pass for a teaching reel that deserves the loaded treatment, or a CapCut handoff when she wants
to keep working on one in CapCut. The handoff reads a top-level job's file names, so give a reel its own:

```bash
uv run product/capcut_handoff.py <job>/reels/<name> --base outputs/<name>.mp4 --overlay outputs/<name>.captions.mov --name <name>
```

(`--overlay` only for a reel typed in her pack; a Clean Captions reel has no separate overlay.) Posting stays
hers, as everywhere in the engine.
