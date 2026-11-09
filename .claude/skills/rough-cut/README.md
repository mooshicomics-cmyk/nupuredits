# rough-cut: setup notes

**What it does.** The cut every Yap starts from, right after her clip comes in from `inbox/`. Claude
transcribes each raw talking-head clip with WhisperX (large-v3 for the words, wav2vec2 alignment for word-level
timing), lets the transcript decide which lines stay (the last take of a repeated line, every spoken cue; filler,
dead air, stutters and false starts come out) and stitches what's left with FFmpeg. She reviews it in the style
plan; graphics, captions and music come after she approves.

**The sound** gets one fixed lift and then a ceiling: +10 dB amplify → voice master → −1 dBFS limiter by
default, or the flat −6 dBFS limiter with `WARM_MASTER=0`. That static chain is deliberate. It is NOT dynamic
loudnorm, whose gain keeps moving and makes the level audibly swell and dip between phrases.

**Say any of these to start it:** "let's make a Yap", "edit this reel", "edit my newest clip", "edit the latest
project", "cut this down", "take out the bad takes", "rough cut".

## What it needs

**1. Two system tools, both required.** `uv` builds and manages the Python venv, and `ffmpeg` (which includes
`ffprobe`) does every media operation. On an Apple Silicon Mac they come from Homebrew:

```
brew install uv ffmpeg
```

A **true Intel Mac** can't use that line (Homebrew's installer now aborts on anything that isn't arm64), so run
`bash scripts/intel-mac-install.sh all` there instead (see `product/INTEL-MAC-ROUTE.md`). `./check-setup.sh`
works out which machine it is on and prints the right one.

**2. A Python venv, built on the first transcription.** The first time it runs, `word-timings.sh` builds a
persistent WhisperX venv at `~/.cache/reels-editing-engine/whisperx-venv`, which pulls in PyTorch and the WhisperX
package: expect several GB and several minutes, depending on the connection. **On an Intel Mac it builds a
faster-whisper venv at `~/.cache/reels-editing-engine/fasterwhisper-venv` instead** (~175 MB, no PyTorch),
because WhisperX needs a torch version that has no Intel-Mac build. It produces the same `words.json` and the same
diagnostics, just without the wav2vec2 alignment pass. Let the build finish. If it gets interrupted, the script
spots the half-built venv through its ready marker (`.speech-tools-ready`), wipes it, and rebuilds it cleanly on the next
run. From then on every run reuses the built venv and starts in seconds.

**3. Model weights, also on the first transcription.** The `large-v3` ASR model and the wav2vec2 alignment model
download from Hugging Face, and the library caches them locally after that first pull. Between them, plan for
3-5 GB of disk.

**4. Clips inside a job folder** under `projects/`:

```
reels-editing-engine/
└── projects/
    └── <job-name>/
        ├── raw/          ← the clips go here (.mov .mp4 .mkv .m4v)
        └── outputs/      ← the finished MP4 lands here (created automatically)
```

Make the `projects/<job-name>/raw/` path and drop the clips in; `outputs/` gets created for you.

## Where things land

The transcript (`words.json`) and the cut plan (`cuts.json`) persist **durably** in
`projects/<job-name>/transcript/`. That folder is the source of truth, reused across runs, so a re-run never
transcribes twice. Working copies and other scratch go to `<temp dir>/reels-editing-engine/<job-name>/`
(`<temp dir>` is Python's `tempfile.gettempdir()`: `$TMPDIR` under `/var/folders` on macOS, not `/tmp`). macOS
clears that folder on its own schedule, so never rely on anything living only there.

The finished cut is written to:

```
projects/<job-name>/outputs/<job-name>.mp4
```

The style plan is the report: the raw length against the cut length, one row per kept line, and a link to the
cut that plays in the side panel.

## Using the folder somewhere else

It is a normal skill folder. Put it in a skills directory:
- `<project>/.claude/skills/rough-cut/` for a single project, or
- `~/.claude/skills/rough-cut/` to have it everywhere.

When you copy or zip it for someone else, leave out `__pycache__/` and `.DS_Store`.
