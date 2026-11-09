---
name: trial-reels
description: "Trial reels: 3 genuinely different edits of her finished reel (a different opening line pulled to the front, a different length, a different look and hook), ready to post as Instagram trial reels so she learns which version pulls. Never just a new hook card on the same footage: Instagram reads that as a repost. On a visual editor reel each trial is its own copy of the reel, re-cut, with her looks following her words, exported through Finish (MP4 or CapCut), and openable in her editor. Use when she says: trial reels, make trial reels, make me some trial reels, spare hooks, test my hook, test different hooks, A/B my hook, try other openings, alternate versions of this reel, which hook works better, give me versions to test. Only for a FINISHED reel (a CapCut draft or an MP4)."
---

# Trial reels: one finished reel, three real re-edits

Instagram's trial reels show a reel to people who don't follow her yet, so posting a few versions tells her which one
pulls without touching her main feed. **A trial must be a genuinely different edit.** The same footage with a new text
card reads to Instagram as the same reel posted again, so on a talking-head reel the face, voice and cut have to change
too (her rule, 2026-10-17). Everything stays true to what she said: lines are moved or left out, never invented.

## 1. What this reel is

```bash
python3 product/trial_reels.py status <job>
```

| `how` | the reel | each trial |
|---|---|---|
| `editor` | her visual editor reel, exported from Finish | **a real re-edit**: its own reel folder `projects/<job>-trial-b/`, re-cut (a different opening, lines left out), her looks moved with her words, optionally another pack or captions, a new hook, then exported through Finish. She can open it in her editor to change anything ("open <job>-trial-b") |
| `capcut` + `recut: true` | a CapCut draft from its own build script, finished by her in CapCut (`draft`: the newest version she edited there) | **a real re-edit of HER draft** (`product/capcut_recut.py`): a new CapCut draft `<reel> trial B`, her draft only read. Every layer she has (grade, compound, graphics, cutouts, sounds) is cut with her clips, the way CapCut splits a clip: a later clip moved to the front, clips left out. The hook is drawn in a style she set herself in CapCut (`hook_from`: her draft's own hook block, else a hook at the top of another of her drafts, the pack's fonts first), only the words changed, as editable text. Wrong draft? `--draft "<name>"` / `--hook-from "<name>"` on `status` or `write` |
| `capcut`, no `recut` | a CapCut draft from its build script, but her draft isn't on this computer | hook swap only: say plainly it changes the hook card and nothing else, so Instagram may treat it as a repost. Offer to bring the reel into her visual editor for real re-edits |
| `well-done` | a baked MP4 | the same: hook swap only, with the same plain warning |
| `null` | not finished yet | say so in one line and offer to finish it first |

`editor` with `exported: false`: she exports from Finish first. (A reel she opened in the editor but finished as a
CapCut draft reads as `capcut` with `editor_unexported: true`: her draft is the reel.)

## 2. Plan three different edits

Read `workflows/capcut-export/WRITING-THE-HOOK.md` and the reel's lines:

```bash
python3 product/trial_reels.py lines <job>      # her cut, numbered, as she approved it
```

On a `capcut` reel with `recut`, the numbers are her draft's clips (each holds the words she says in it): `open` and
`drop` name clips, and the cut only ever falls where she cut.

Lines are fragments: a sentence usually spans several. Every trial differs from her reel on **at least three** of these,
and the three trials differ from each other:

- **open**: a run of lines from later in the reel moved to the very front (`"50-51"`), a whole sentence that grabs on
  its own and makes sense before the rest. Moved, never repeated. The strongest axis: lead with it on every trial.
- **drop**: runs of lines left out (`["42-46"]`) for a tighter cut. Side roads, a second example, a long middle. Never
  the line that pays the reel off, never a line her other lines depend on.
- **look, inside her brand**: a fast pass with a few tweaks, never a look she doesn't use. A caption style from her
  pack's lookbook (`captions`), a different hook shape, or (`pack`) another of HER packs: one she's chosen on her own
  reels, saved a lookbook in, or made. `write` refuses anything else.
- **hook**: new hook words (and shape) by WRITING-THE-HOOK.md, a different angle from her reel's hook. Never mirroring
  the new opening line.

Read the new opening against the line that follows it in the plan: the reel has to still make sense in its new order.

## 3. She picks

ONE question box, `multiSelect: true`: "Which trial reels should I make?" One option per trial. The label is the new
opening line, in quotes. The description lists the rest ("5 lines out · Editorial pack · hook: …"). Her reel is version
A; it isn't an option. "Other" lets her change one. Nothing is made unless she ticks it.

## 4. Make them: hands-off, tweakable, then one export

```bash
python3 product/trial_reels.py write <job> -  <<'JSON'
[{"open": "50-51", "drop": ["42-46"], "captions": "phrase", "hook": "first line / second line",
  "shape": "eyebrow-headline", "angle": "her own line, pulled to the front"}]
JSON
python3 product/trial_reels.py make <job>                  # prepares each trial in seconds, nothing rendered
python3 product/trial_reels.py export <job> [--only b,c] [--to mp4|capcut]   # renders them
```

- `write` refuses an editor-reel or CapCut re-cut trial with no different edit (only a hook), a plan naming lines the
  reel doesn't have or leaving fewer than two lines, and a pack or caption style outside her brand.
- **A CapCut reel (`recut`)**: `make` writes each trial straight into its own CapCut draft, `<reel> trial B` (a name
  already taken goes to `<reel> trial B 1.1`, never replaced), in seconds, nothing rendered. CapCut has to be quit
  first (it refuses otherwise and says so). `pack` / `captions` don't apply: her draft's own look is the trial's look.
  Hand each over as its draft name; she exports it from CapCut like the reel.
  - **Her music bed is never cut with her clips** (the song would jump at every cut): it's laid again from where
    her song starts, one continuous play under the whole trial, her level and volume shape kept, on the bottom track.
  - **The hook never sits on one of her graphics in its spot**: measured from the graphics' own frames, a graphic
    already on screen as the trial opens plays first and the hook comes in as it ends, and the hook ends as the next
    one comes in (the editor road's rule). `make` says when and how long it's on; with no clear stretch it goes in
    at the start anyway and says so once.
  - **An older trial draft whose song jumps**: `python3 product/capcut_recut.py rebed "<trial draft>" "<trial draft>
    1.1" --song-from "<her finished draft>"`: a new version with the song laid fresh and nothing else changed, so
    anything she did in that trial (a hook she moved) stays.
- **`make` is the hands-off pass.** Each trial becomes its own reel (`<job>-trial-b`): her reel copied (footage linked,
  never written), re-cut with her edges exactly as she approved them (only the order changes), her looks moved with
  her words, the new captions / hook drawn. Seconds per trial. A look whose words are no longer in the cut is left off
  and named.
- **Then she can tweak any trial in her editor before export** ("open <job>-trial-b"); it's a normal reel. Hand her
  the trials as ready to watch, and offer to export them all.
- **`export`** renders each trial: every look it shares with her reel reuses the render her reel already has, only
  changed looks render, the cut is made at 1080 x 1920 (what Instagram plays), then her editor's own Finish (MP4, or
  CapCut with `--to capcut`). A few minutes a trial, said before it starts. One at a time; never two renders at once.
- A trial that stops says why. It's saved as its own reel; she can open it in her editor to fix it there.

## 5. Hand them over

One line per trial: what's different, then its MP4 as a markdown link (relative to the engine root) or its CapCut
draft name, and that she can open it in her editor ("open <job>-trial-b") to change anything. Then, in plain words: post each as a **trial reel** in Instagram (turn
on Trial when she shares it), give them a couple of days, and the one that holds viewers longest is her opening.
Same "keep it crisp" export note as any reel.

When she comes back with a winner ("B won", "the label one did best"): offer, once, to keep what won as a rule for
her next hooks (`python3 product/teach_style.py keep <job> "<what won, in her words>"`, the Part C bullet that's
read before planning). Never a remembered hook itself: a hook is written for its reel.

## What this does not do

- It never posts. Posting stays hers.
