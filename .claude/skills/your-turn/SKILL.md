---
name: your-turn
description: "The CapCut round trip. When the creator has fixed one snag by hand on the rough-cut timeline in CapCut, this reads her trimmed cut back in and makes it the new source of truth, so the full styled build (zooms, punch-ins, SFX) rebuilds on top of HER cut, on a fresh draft version. Her hand-trim is never overwritten. Use when she says: your turn, okay your turn, your turn now, grab it, take it from here, i trimmed it in capcut, i fixed the snag, pull my cut back, grab my cut. Only for a Yap rough-cut draft that uses her raw clips; it refuses a rendered-base draft."
---

# Your turn: pull the creator's hand-trimmed cut back into the engine

The everyday case: the cut is 95% right, but there is one spot the tools cannot nail (a stumble the
transcript reads as clean, a breath that should go). Rather than fight it, the creator opens the rough
cut in CapCut, trims that one spot by hand, and hands it back. This reads her trimmed timeline, rewrites
`cuts.json` to match, and sets up the clean styled rebuild.

**Why this is safe (and why we never patch her draft directly):** her in-app edits live only inside that
draft, CapCut keeps no version history, and anything written to a draft while CapCut is OPEN is silently
overwritten by CapCut's next save. So we do NOT edit her draft in place. We read her trim back OUT, make it
the cut, and rebuild the full styled reel fresh, to a NEW version. Her trimmed draft is left untouched.
(Engine-injected tracks DO ripple with the main-track magnet as long as CapCut was quit when they were
written; the earlier "they float instead of rippling" claim was disproven by a live test.) See
capcut ripple needs one pass build, capcut never replace rebuild, capcut quit before any draft write.

## The flow

1. **She trims the snag in CapCut, saves, and QUITS CapCut.** The reader edits the draft JSON, so CapCut
   has to be closed or it clobbers the change. If she left it open, ask her to save and quit first.
2. **Read her cut back:**
   ```bash
   python3 .claude/skills/rough-cut/scripts/your-turn.py <job>
   ```
   Dry run: it finds the CapCut draft built from this job's raw clips, prints her cut (segment count,
   total length, each kept line), and how it differs from the current cut. If it cannot find the draft,
   pass `--draft <name>` (the folder name under CapCut's Projects dir). A line printed with
   "⚠ low-confidence timestamps" under it has a label read from shaky word timings: trust the clip, not
   that label (the warning is shown there only, never written into the cut).
3. **Show her the pulled cut and confirm it is what she meant.** Then apply:
   ```bash
   python3 .claude/skills/rough-cut/scripts/your-turn.py <job> --apply
   ```
   This backs up the old cut to `cuts.pre-your-turn.json`, writes the new `cuts.json`, and re-derives the
   aligned transcript (`kept-words.py`), so graphics-plan and captions read her cut correctly. It
   also copies her cut over the scratch plan `stitch-cut.sh` stitches, so a splice after this stitches HER cut,
   not the one from before her trim. It says ✓ for the boundary clean-up only when `clean_cut` really
   finished; a ⚠ there names the step that did not, and the command to run once it is fixed.
4. **Rebuild the styled reel on the new cut** through the normal Yap build (`cleanyap` / `superyap`).
   The rebuild goes to a **NEW draft version** (`draft_safety.next_version`), never over her trimmed one.
   From here it is a normal one-pass build: zooms, punch-ins, matched SFX, all of it.

## What it supports

- **Yes:** a rough-cut Yap draft whose footage is the job's raw clips (the draft the engine hands her).
  Her segment source ranges are already in raw-clip time, so her trim reads back with no conversion.
- **No:** a draft built from a pre-rendered base (a `*.NOTEXT.mp4` render, a baked MP4). The script
  refuses it with a clear message rather than guessing a wrong cut.

## Rules

- **CapCut must be quit** before reading. Never edit a draft's JSON while the app is open.
- **Never overwrite her hand-trimmed draft.** The rebuild is a new version, always.
- **Her trim wins — now enforced, not just asked.** Once pulled, her cut is the source of truth. `--apply`
  drops a `transcript/.your-turn-cut` marker; the next `stitch-cut.sh` sees it and auto-disables the
  restart-detector (`trim-restarts`) so the styled rebuild can't silently re-cut over her trim. A fresh
  rough cut clears the marker. (Override with `TRIM_RESTARTS=1` only if you truly want it to re-run.)
- This skill only pulls the cut back and re-derives the transcript. The styling happens in the normal
  build step that follows.
