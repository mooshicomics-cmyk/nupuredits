---
name: capcut
description: "Where a reel lands unless she asked for a finished render: an editable CapCut draft she keeps working in, each kept line its own clip with graphics and text layered above. Every write happens with CapCut closed, a draft she has opened is layered on top of or moved to a new version (never replaced), the magnet is fixed after her first open, and the export can be run for her on a Mac. Triggers: I'll polish it in CapCut, give me the CapCut draft, add this to my CapCut draft, make a new CapCut version, my clips won't snap together, CapCut's closed go, do the CapCut export for me, add his camera as a PIP, put my second camera in the corner."
---

# CapCut

Raw and medium end here, and well-done can too (`CLAUDE.md`, "NO ROUTE IS A DEAD END"). It is the main road,
not a fallback. Everything goes through **`workflows/capcut-live.py`** (its own `uv` header; run it with no
arguments for the command list). It takes the job as an argument on a PC too, so never hand-write a per-reel
build script.

## Her draft is hers

**CapCut is closed for every write** (`CLAUDE.md` rule 7, enforced by `draft_safety.require_capcut_quit`).
CapCut saves its in-memory copy over the files when it quits, so anything written while it is open is lost.

- **Don't hijack her screen.** Before any write (a build, a layer, `fix-magnet`), tell her it needs CapCut closed,
  ask her to quit it and say go, and wait for the go. Never quit CapCut for her. Never `open` or `start` it
  unprompted afterwards: tell her the draft is ready and let her open it.
- What the tool does if CapCut is still open: on a Mac it asks CapCut to quit (it saves first), writes, and
  relaunches, about 15s a round, so batch related edits into ONE call. On Windows it never closes CapCut (only
  a forced kill works there, and that loses unsaved work): the write refuses until she closes it.
- **Never send her into CapCut mid-job** while the build still has writes left (a font to pull down, a quick look
  at the draft): finish every write first, then hand it over. If she must open it, she closes it fully before the
  next write. On Windows a CapCut reopened mid-job can hang and stay stuck until a full restart.
- **Microsoft Store Claude app (Windows):** builds land in `projects/_capcut-staging/`, which CapCut never reads,
  so an open CapCut does not block them (one plain line says so). Only **Add to CapCut** needs CapCut closed.
- Driving the open app never writes the file.

**Never replace a draft she may have opened.** CapCut keeps no history, so a replace wipes her edits for good.
- **Layer on top:** `layer`, `text`, `move`, `remove`, `place-plan` and `pip` read the draft as she left
  it and add to it.
- **New version:** `new-draft` is for a fresh draft only and refuses a name that exists. A from-scratch rebuild
  goes to `draft_safety.next_version` (`<base> 1.1 → 1.2`).
- **She wants every element separate:** that is the `separate-layers` skill, not a rebuild here.

**Nothing gets posted by accident.** CapCut's after-export share screen is modal and posts to TikTok/YouTube.
The tool escapes it; **never click through it.**

## Making the draft

The job is the newest `projects/` folder unless she names one. It needs `transcript/cuts.json` and `raw/`. No
rough cut yet: make one with **`FLAT_RENDER=0`** (the cut list in about 8s, no flat render; a CapCut job never gets
one).

```
uv run workflows/capcut-live.py new-draft <job> [--name <draft>]
```
Every cut becomes its own clip, placed exactly, playing the take its line names. The canvas follows the footage
(an upright phone clip gives 9:16). Drafts live under `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/`
(or the Windows equivalent). Her raw clips are **hardlinked** into `<draft>/Resources/`: CapCut is sandboxed to
`~/Movies`, and anything outside opens as red "File not accessible". CapCut snaps cuts to its 30fps grid
(≤17ms each), which is fine.

## Layering on top (CapCut closed)

```
uv run workflows/capcut-live.py place-plan <draft> <job>     # every graphic in graphics-plan.json, one cache cycle
uv run workflows/capcut-live.py layer      <draft> <graphic.mov> --at 2.5 [--layer N] [--dur 4]
uv run workflows/capcut-live.py text       <draft> "text" --at 12 --dur 2 [--pack <pack>] [--role caption]
uv run workflows/capcut-live.py move       <draft> --track overlay --index 1 --scale 0.75 --y -0.2
uv run workflows/capcut-live.py remove     <draft> --track overlay --index 2
uv run workflows/capcut-live.py pip        <draft> <job> [--scale S]                  # her second camera, synced
```
- A graphic is its own video track (`flag: 2`); ProRes 4444 alpha stays see-through. One CapCut track never
  plays two clips at once. With no `--layer`, a graphic takes the lowest layer free for its whole span.
  `--layer N` is a place in the stack (1 = just above her footage): if that track is busy then, the graphic
  gets a new track at that place and everything above moves up one.
- Text is set in her style pack: the role's font, size, color, letter case and height (`--role` caption,
  headline, thought, takeover or accent; caption by default). The pack is `--pack`, else `STYLE_PACK`, else her
  saved default; with none it stops and asks. A text clip never overlaps another on one track.
- `move` writes scale, position (as a fraction of the canvas), rotation and opacity exactly. It is the
  only route that holds: CapCut's inspector ignores synthesized keystrokes.
- `--track` is `footage` (her footage, the magnet's track; `main` also works), `overlay` or `text`. `--force` on
  `layer` and `text` places a duplicate on purpose; without it an interrupted run cannot land twice.
- **A second camera** (another phone on the same moment, usually the other person's face) goes in as a PIP in
  two steps. First `uv run product/sync_camera.py <job> <their file>`: it copies the file into
  `assets/pip/`, lines each of her clips up with it by sound (`sync.json`; a clip it never heard gets null, never
  a guess) and decides whose mic carries each kept line (`mic-report.json`: the second phone 10 dB+ hotter than
  usual = the other person talking). Show her the mic table it prints. A line that changes speaker part-way is
  flagged with its word gap; `--split-mixed` splits it in the cut list, and the rough cut is then re-stitched and
  built as the next draft version. `--pip-mic <clip>` gives a whole clip to the second phone's mic when it was
  simply the better mic there; `"pip_audio": true/false` on a line in `cuts.json` is her call and always wins.
  Then `pip <draft> <job>` lays one PIP clip over every footage clip from a synced take, frame-matched (her
  clip's source + the offset), on its own track just above her footage so graphics stay on top, sized to fit the
  open band below her from `subject-zones.json` (up to 90%; `--scale` when she wants it another size). The PIP's
  sound plays where its mic carries the line and her clip goes quiet there; elsewhere the PIP is muted. It
  follows the footage track as it stands, so a draft she trimmed stays in step. It is additive (CapCut closed,
  `building_on`) and refuses a draft that already has that camera.
- **Any other edit to the draft JSON must clear `Timelines/` and the `.bak`** (as `building_on()` does), or CapCut
  ignores it. `building_on()` also fills a null `source_timerange`, which would wedge the export. A wedged export:
  `kill -9` CapCut, delete `Timelines/`, relaunch.

## The magnet, after her first open

CapCut's first open builds a `Timelines/<id>/draft_info.json` cache and resets the main-track anchor there,
so the magnet can only be fixed after that open. This is the last step of every handoff, the VectCut builds
included:
```bash
uv run workflows/capcut-live.py fix-magnet "<Draft Name>"      # CapCut closed: anchors every copy, then reopens it
uv run workflows/capcut-live.py check-magnet "<Draft Name>"    # non-zero if any copy is still broken
```
**Never hand over a draft until `check-magnet` passes**, and never "fix" the magnet by baking graphics into
her footage. `fix-magnet` reopens CapCut and the draft by itself on a Mac, so say so when you ask for her go. Why
it happens: "THE TIMELINES RESET" in `product/capcut_ripple.py`.

## Driving the open app (Mac)

This works through CapCut's own accessibility ids: find the element, act, read the app's state back to confirm.
**It takes her mouse, keyboard and focus a few seconds at a time, so say so first if she is at the machine.**
**It needs macOS Accessibility permission for the app Claude runs in** (System Settings > Privacy & Security >
Accessibility, then quit and reopen that app). Without it CapCut reads as empty and every live command stops
with a message that says so; help her switch it on, never treat it as a broken draft or a CapCut update.
Building drafts with CapCut closed never needs it.
Keys only reach CapCut while it is frontmost (`bring_forward()` waits until it is). The live commands were read
on CapCut 9.5.0: every id they use, the export dialog's own buttons included, is in the live map at the top of
the live section. They wait for what they need (the home screen, the editor, the dialog, the playhead, the
exported file) rather than for fixed times, so a slow machine only makes them slower, and a wait that runs out
says what never appeared. If a command stops working after a CapCut update, run `ids --map` (read only) on the
home screen, in the editor and with the export dialog open (repair C in `product/CAPCUT-SELF-HEAL-PLAYBOOK.md`)
before treating the tool as broken. On Windows these commands say they are Mac-only.

```
uv run workflows/capcut-live.py open <draft>                 # whole-name match: "Reel 1.1" never opens "Reel 1.12"
uv run workflows/capcut-live.py timeline --draft <draft>     # JSON: each track, exact clip times, unsaved changes
uv run workflows/capcut-live.py go-to 18.5 --draft <draft>   # lands on the exact frame, calibrating itself
uv run workflows/capcut-live.py split 9.0 | delete 2 | undo | redo | marker | fit-timeline | play | playhead | clips
uv run workflows/capcut-live.py export [--to <dir>] [--timeout 600]
```
`export` works CapCut's export dialog (default 1080p HEVC mp4 into `~/Downloads`, cloud sync off), pressing its
buttons by their ids; a dialog that does not show them stops the export and points at `ids --map`, and nothing is
clicked at a guessed spot. It holds the screen only until the dialog's Export button is pressed, then watches the
file, and calls it done only once it has stopped growing for 10 s. Remind her once of the
crisp-export settings (`CLAUDE.md`, "Keep it crisp").

## "My project isn't in CapCut" (Windows)

Check two things before any repair. `python product/capcut_installs.py` answers `both`, `store-only`,
`desktop` or `none`. `both`: she is looking in the Microsoft Store CapCut, which keeps a separate list; open the
right one for her with `python product/capcut_installs.py --open` (also what "open my CapCut" means, on a PC or a Mac).
`store-only`: she needs the free desktop CapCut from capcut.com, opened once. Then
`python product/capcut_store_redirect.py`: `redirected: yes` means the project builds in
`projects/_capcut-staging/`; the engine adds it to CapCut itself when the build ends with CapCut closed, and a
build that said "One more step" left it waiting for her to double-click **Add to CapCut.bat**. Only after both come back clean is it
a draft problem (`product/CAPCUT-SELF-HEAL-PLAYBOOK.md`).

## After she has the reel

If `workflows/carousel/` exists, ask once: "Want a carousel or a story from this reel too?" (the Carousel Kit
and Story Kit). Yes: run that skill on this job.

## What else lands here

The styled Yap drafts come from the VectCut builders (`product/cleanyap.py` / `superyap.py`). A baked
well-done reel comes in through `uv run product/capcut_handoff.py <JOB>`. Both get the magnet step. The tool
reads the same `transcript/cuts.json` the rough cut writes.
