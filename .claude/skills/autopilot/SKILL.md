---
name: autopilot
description: The one-shot edit. Edits a new reel straight through, from the reels she finished in the visual editor and her taught preferences, with no stops; then opens the visual editor on her Sound tab with every layer built (she can go back to any layer, and exports from its Finish tab). Use when she picks "Autopilot" at the start of a reel (`review_gate.py start`), or says "autopilot", "just edit it", "edit it all the way through", "do it all", "don't ask me, just edit", "one-shot edit", "one click edit". Same tools, same checks, same full quality as walking through; only the pauses are gone.
---

# Autopilot

**The one thing asked first, even here:** `python3 product/frame.py ask <her clip>`, reel or YouTube, as the `rough-cut` skill says. Exit 1 means nothing to ask.

She drops a clip and gets back a finished draft on her visual editor: rough cut, looks and sounds, with every choice
made from what she has already shown the engine. No stops: not after the cut, not for the register. Nothing about quality or precision changes: the same transcription,
the same edge-accurate cut, the same render checks, the same placement around her face. What goes away is waiting
on her. Everything stays hers to change afterward on the visual editor.

**The rule for every step: never ask a question you can answer yourself.** A fact in her files, her transcript,
her past reels or her taught preferences is answered, not asked. The only questions left are what only she knows
(listed under "When you do stop"). Every message ends with one line that starts **Next:**.

## 0. What autopilot runs on

```bash
python3 product/choices.py defaults
```

It prints the pack (the one on her most recent reel) and the finish route (the one she picked most), each with the
reason, and which reels it learned from. Her taught preferences (`product/learned.py`), her lookbook (looks first)
and her favorite sounds (`product/favorites.py show`) apply on their own, exactly as when walking through.
**No past reels at all** → there is nothing to run autopilot from: say so in one line and walk through this one
(`rough-cut`); it becomes her first piece of history.

## 1. The rough cut (`rough-cut`, straight through)

First, if she asked for autopilot in her own words (rather than picking it from `review_gate.py start`), record it:
`python3 product/review_gate.py start autopilot`, so the review gate after the cut carries on instead of asking.

Follow `rough-cut` exactly (intake, HDR, transcribe, transcript-cut, stitch, mishears, re-listen), with these
answered instead of asked:
- **The job name:** from her transcript, what she'd call it out loud.
- **`intent.md`:** write it from the transcript (what it opens on, what they walk away with).
- **HDR heads-up:** still say the message `hdr.py` prints, then run `--apply` and carry on.
- **New mishears:** fix the obvious ones (a name in her brand kit, her product) and list them in the summary.

## 2. No stop after the cut

Autopilot never asks the review question (the widget can't show a finished build; she picked autopilot knowing it
opens her finished draft in the visual editor). `python3 product/review_gate.py <job>` says so too. Lock the reel to
the editor: `python3 product/review_route.py <job> editor`.

## 3. Teaching or confessional, read from her words (no stop)

```bash
python3 product/choices.py register <job>
```

It prints the lean in her words. Read the kept-words transcript too and decide (teaching = steps, numbers, how-to:
more looks; confessional = her story, a feeling: lean). Never carry one from another reel. Say which in the final
message, one line, with how to change it.

## 4. The creative plan and the looks (`graphics-plan`, no approval stop)

Follow `graphics-plan` with her register (lookbook first, spoken cues kept, hook copy from
`workflows/capcut-export/WRITING-THE-HOOK.md`). Write the plan files as usual; do not pause for approval.
1. The one full-quality cut: when `python3 product/visual_editor.py check-base <job>` exits 1, run
   `python3 product/visual_editor.py finish-cut <job>`; a fresh stitch nobody edited is already it, so then just lock
   it (`finish-cut` returns at once, and it marks the cut locked on her page).
2. Place the looks the plan names with `visual_editor.py place` in her pack; the hook (its own copy) is drawn with
   `lookbook.py draw` into its own folder under `hf-graphics/` and windowed. Every gate a walk-through build has
   (rule 9 geometry, `subject-zones.json`), never a bespoke render. Every graphic, placed or drawn, shows on her page
   as a look card she can swap, move or remove. Then `python3
   product/visual_editor.py looks <job>`. Her Sound tab fills its own defaults (her favorites, her CapCut shelf, her
   Epidemic downloads, the library).
3. **No render, no CapCut draft.** The export is hers: the Finish tab's Export (CapCut or MP4), or "render" in the
   chat. The beat sheet is skipped: the page is her review. No color grade.

## 5. Record it, then open her editor (and start the watcher)

After `open`, start the watcher in the background exactly as `rough-cut` says ("The watcher"):
`python3 product/visual_editor.py wait <job>`. From then on her notes and Sandbox ideas reach you without her typing.

```bash
python3 product/choices.py record <job> pack=<pack> register=<register> format=<format> mode=autopilot
python3 product/visual_editor.py open <job> --autopilot
```

It opens on her **Sound** tab (every layer built and locked in), with one note on the page: "Autopilot built your
whole reel. Want a different cut? Go back to Cut." The tabs are layers: going back and changing one (her cut, a look)
locks the ones after it until she locks that one in, and then they re-sync to it on their own.

Then one short message:
- what you chose and why, one line each: pack, teaching or confessional, the hook
- anything you fixed on your own (mishears)
- FIRST, the `EDITOR LINK:` line `open` printed, pasted word for word (it is the markdown link to her page; her
  browser often opens behind this window, so it is never skipped), and that everything is on it
- how to change any of it: on the page (Swap, Move, Refine, Highlight, trim, Sound), then **Export** on the
  Finish tab: CapCut or an MP4 (her usual is <route>, `choices.py defaults`)
- **Next:** one line

## When you do stop (only these)

- **A default is missing** (a brand-new engine with no past pack): ONE pick-one for that choice only.
- **Something failed** that a check could not fix: say it plainly and what you need.

Anything else (a font, a placement, a sound, which take) is answered by the engine's rules and her history.
