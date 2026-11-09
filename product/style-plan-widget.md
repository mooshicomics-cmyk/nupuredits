# The style plan — LOCKED spec + paste-ready functional widget

> The one canonical definition of the rough-cut review step, the **style plan** (formerly "cut sheet" —
> renamed for creators 2026-08-01). Rule 2 in `CLAUDE.md` points here. **Preferred path: generate it with
> `product/build-style-plan.py <job-dir>`** — the generator bakes in the canvas-blank fail-safe (build doc)
> and never mis-replaces a token, so hand-assembly can't drift. The generator holds the only copy of the widget;
> `style-plan-widget-build.md` holds the rules it follows. Only the cut (from
> `cuts.json`) changes per job. Format-agnostic: the SAME style plan is used for **Yap, Voiceover, and
> Animation** — there is no per-format variant.

> **Two ways to review (2026-10-13).** This file is the ORIGINAL WIDGET (text only) style plan. Its upgrade is the **visual editor**
> (`product/visual_editor.py`, page `product/visual-editor/editor.html`): her script in her own browser, played in
> her cut's order, edits sent straight to the engine with a receipt and a copy-paste fallback. `rough-cut` asks
> which she wants ("the visual editor or the original widget?", saved as `review.style_plan_mode`). Everything below
> applies when she picks the original widget (or says "text only").

## The contract (do not drift)

**COST POLICY — widget FIRST, lean table on every RE-CUT (2026-08-25).** The interactive `show_widget`
is ~25K output tokens per render (~15x a plain markdown table), and re-rendering it on every re-cut is
the single biggest avoidable cost in the cut stage. So: the **first** time a cut is reviewed, deliver the
full interactive widget (the delightful reveal). For **every re-cut after that**, deliver the **lean
markdown table** (below) instead — same information, ~1.5K tokens, the user replies with edits by line
number. This keeps the beautiful first look and kills the repeat-render tax that quietly drains a creator's
monthly usage. (Applies identically to the shipped engine — leaner shipped = more reels/month.)

**HER ON/OFF SWITCH (v2.1).** The widget is ON by default and she can switch it off. Before a FIRST review,
run `python3 product/build-style-plan.py --which`:
- `widget-first` (she has never chosen): run `python3 product/learned.py add review.style_plan widget` FIRST
  (it records the choice so the line below never shows again), then give the widget, then ONE plain line in
  the final message after it: "The visual style plan stays on. Untick the box at the bottom of it anytime and
  you'll get a lighter table instead."
- `widget`: the widget, no extra line.
- `table`: the lean table below instead, ending with "Want the visual style plan back? Just say so."

The widget carries a ticked box, "Show me this visual style plan on every new reel." When her message contains
"Style plan: show me the simple table from now on", run `python3 product/learned.py add review.style_plan table`
and confirm in one short line. When she asks for the visual plan back, `learned.py add review.style_plan widget`.
It is an ordinary learned preference: `/learn list` shows it, `/learn forget` clears it back to the default.
Re-cuts are the lean table either way.

Every rough-cut review is **two things, in this order**, in the chat — **on EVERY format (Yap,
Voiceover, Animation), no exceptions:**

> 🔴 **ORDER INSIDE THE TURN: every command first, then `show_widget`, then the final message (link last).**
> The app folds any text written BEFORE a tool call into the turn's tool-activity group; only the text
> after the LAST tool call stays visible. A link written before the widget is folded away and she never sees
> it, and a bookkeeping command run after the widget (`learned.py`, a log line) buries everything above it.
> So: `--which`, `learned.py`, `style_plan_link.py`, `build-style-plan.py` all run BEFORE `show_widget`;
> `show_widget` is the turn's last tool call; then ONE final message holds what she is looking at, the
> length, and the link as the last line.

1. The cut review itself:
   - **First review of a given reel → the interactive `show_widget`** (the style plan) built by `build-style-plan.py`.
   - **Every re-cut review after that → the LEAN MARKDOWN TABLE** (format below), NOT the widget.
   - **🔴 EXACTLY ONE style plan on screen per review.** Call `show_widget` a SINGLE time for a first review — never twice, never a re-issue "to be safe," and never the widget PLUS the plain-text/table version in the same turn (they are an either/or: widget when `show_widget` works, plain-text only as the no-widget fallback). Two style plans for one review is the bug to prevent. **If `build-style-plan.py` prints `STYLE PLAN TABLE INSTEAD OF THE WIDGET`**, the widget could not be built this time: skip `show_widget`, give her the lean table it printed (format below), say in one calm line that the visual plan couldn't be drawn this time, and end with the link as always.
2. A **markdown video link in the chat text** — path to the rough-cut MP4 **relative to the working
   directory (the engine root)**, e.g. `▶ [<job>.mp4](projects/<job>/outputs/<job>.mp4) — 1:18`. This
   opens the side-panel player **so she can WATCH the rough cut before approving**. It goes in the turn's
   FINAL message, AFTER the review, as the last thing said, always. **NEVER** a `SendUserFile`,
   inline-render, or attach card, and **NEVER `open` the MP4 with a shell command** (that launches
   QuickTime or another external app). The markdown link is the only way you surface the cut; it plays in
   the side panel, in place.
   > 🔴 **Generate the link, don't hand-type it** — `python3 product/style_plan_link.py <job>` prints the
   > exact markdown, computed from the engine root and **existence-checked**, and REFUSES a missing or
   > wrongly-prefixed path. `build-style-plan.py` prints it for you too. Validate any link you already
   > wrote with `python3 product/style_plan_link.py --check "<href>"`.
   > **Do NOT prefix the engine folder name** (`ai-edit-engine/…`): the session's working directory IS
   > the engine folder, so a link resolves from there; prefixing it doubles the path to
   > `…/ai-edit-engine/ai-edit-engine/projects/…` and the preview fails with "Couldn't load this preview
   > / file may have been deleted or moved." The href is just `projects/<job>/outputs/<job>.mp4`.

**Lean re-cut table** — plain markdown the app renders for ~1/15th the tokens; the user replies with edits
by line number (no interactive controls):

```
| # | line | dur |
|---|------|-----|
| 1 | so if you wanna know how i edit my yaps… | 8.1s |
| 2 | and no, i did not hire an editor… | 3.9s |
| … | … | … |

**total: 1:25 · reply with cuts/notes by line number**
```

An italic section label (Hook / Setup / …) may head a group of rows. Keep the same line numbering the
widget would use so her edits map straight back to `cuts.json`.

**Layout is fixed — one row per kept line:**
- **LEFT** — two icon buttons in a HORIZONTAL row: attach (`ti-paperclip`) + notes (`ti-message`).
- **MIDDLE** — line number + the transcript line (+ inline fields when opened). An optional subtle,
  sentence-case section tag above a group of rows (Hook / Setup / …) is allowed.
- **RIGHT** — duration + trash toggle (`ti-trash`), in a horizontal row.
- **Header** — a counter (`kept · trashed · notes`) on the left, and a live **length meter** on the right
  that turns **green in the 0:45–1:30 sweet spot** (amber above 1:30, neutral below 0:45).
- **Footer** — `Send my edits ↗` (primary) + `Reset`, in a horizontal row.

**Icons:** Tabler **outline** webfont only — `ti-paperclip`, `ti-message`, `ti-trash`,
`ti-arrow-up-right`, `ti-refresh` (already loaded in `show_widget`; do NOT hand-draw SVG icon paths, the
platform blocks them, and NEVER use emoji). Buttons always in HORIZONTAL rows, never stacked.


**Building it:** always `python3 product/build-style-plan.py projects/<job>` (it also prints the verified
video link). The button rules, the canvas-blank fail-safe and the paste-ready skeleton live in
[`product/style-plan-widget-build.md`](style-plan-widget-build.md): read that only if the generator cannot run
or you are changing it.

## Wiring it to the re-cut

When she hits **Send my edits**, the returned message names the line numbers to cut. **If she says she sent
them but nothing arrived** (or replies "sent" with no edits), don't ask her to redo them: call
`read_widget_context` with the show_widget tool's full name (in the desktop app, `mcp__visualize__show_widget`).
The widget shares her marks with the app, which hands them over with her next message. If that comes back
empty, the copy box under the widget still holds the message (it survives a reload); ask her to paste it. Two copies of the cut
exist, and each has one job:

- **`projects/<job>/transcript/cuts.json`** is the cut the last splice saved, and the one the style plan was
  built from, so her line N is its segment N (same order as `SEGS`). **Make her edits here**
  (delete/adjust).
- **`<temp dir>/reels-editing-engine/<job>/cuts.json`** (`<temp dir>` = Python's `tempfile.gettempdir()`) is
  the plan `stitch-cut.sh` actually stitches, and whatever it stitches it saves over the copy above. So **copy the
  edited file over it before splicing**, or the next splice stitches the old plan and saves it over her edits:

  ```bash
  python3 -c "import os,shutil,sys,tempfile; d=os.path.join(tempfile.gettempdir(),'reels-editing-engine',sys.argv[1]); os.makedirs(d,exist_ok=True); shutil.copy(os.path.join('projects',sys.argv[1],'transcript','cuts.json'),d)" <job>
  ```

Then re-run `stitch-cut.sh` and show the updated cut with a fresh style plan. (If the scratch folder has been
cleared, `stitch-cut.sh` stitches the saved copy by itself and says so.) Notes/references that aren't "cut this"
are creative direction — carry them into the plan.

> Internal data/filenames (`cuts.json`, `stitch-cut.sh`, the `rough-cut` skill) keep their names — the
> "style plan" rename is creator-facing wording only, not code churn.
