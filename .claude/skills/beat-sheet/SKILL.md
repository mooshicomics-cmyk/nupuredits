---
name: beat-sheet
description: "The beat sheet: every key moment of the reel as a numbered still with a legend stamped on it (beat, time, what it is, the words, how it moves), shown AFTER the creative plan is approved and BEFORE anything renders, so she approves the design on stills and gives notes by beat number. Offered on every build, every route, even a reel with only a hook and captions. Use when the creative plan is approved and the build is about to render or write the CapCut draft, or when she says: show me the beat sheet, beat sheet, can I get a beat sheet, show me the beats, let me see it before you render, storyboard it, show me the storyboard, storyboard, beat 4 change this, change beat 12, sandbox beat 7, let me see beat 7 move, sandbox this section."
user-invocable: true
argument-hint: "[job]"
---

# Beat sheet: approve the design on stills, then render once

Rendering motion is the slow, expensive step, and a wrong word found in a finished render costs the whole
render again. So before anything renders, she gets the reel's key moments as stills: the real design on her
real footage, numbered, each with a legend under it. She marks it up by number ("beat 4, bigger", "beat 9,
different photo"), the beats she names get fixed, and only an approved sheet goes to the render.

This is the one preview sheet the engine makes on purpose (CLAUDE.md rule 5). It replaces finding mistakes in
a render; it is not a self-check.

## Where it sits

```
rough cut ⏸ style plan  →  creative plan ⏸ approve  →  build the layers  →  ⏸ BEAT SHEET  →  render / CapCut draft
```

Every route and every format, however light. A confessional raw reel may have two beats (the hook and a
caption): that is a beat sheet. A loaded teaching reel may have twenty.

- **Hands-Off Edit gets the same buttons.** Claude still makes every call; she just gets to look before it
  renders. "Skip it this time" keeps Hands-Off fully hands-off.
- **After the beat sheet, not before:** "sandbox beat 7" shows one beat MOVING before the whole reel renders
  (step 6). Stills cannot show motion; the sandbox can.

## 1. Offer it

Run `python3 .claude/skills/beat-sheet/scripts/beat-sheet.py --which`:
- `ask` (the default): ask as a **CLICKABLE multiple choice she taps** (the pick-one selector /
  AskUserQuestion), never a prose question she types an answer to. Put everything she needs inside the question
  and the option descriptions; the app hides text written right before a choice box.

  **"Want to see your beat sheet before I render?"**
  1. **Show me the beat sheet (Recommended)**: every moment as a numbered still, notes by beat number, nothing rendered yet.
  2. **Always show it**: show the beat sheet on every reel and stop asking.
  3. **Skip it this time**: render now.
  4. **Stop asking me**: skip the beat sheet from now on (say "show me the beat sheet" anytime to get it back).

  Option 2 → `python3 product/learned.py add review.beat_sheet always`, then make it.
  Option 4 → `python3 product/learned.py add review.beat_sheet skip`, then build.
- `always`: make it, no question.
- `skip`: build without it, and say once at handoff that "show me the beat sheet" still works.

She can also say it in words anytime: "always show me the beat sheet" → `always`; "stop offering the beat
sheet" → `skip`. Confirm in one line. `/learn forget` puts it back to asking.

## 2. Build the layers, render nothing

Run the build exactly as the route says, up to the point where it would render or write the draft, and stop:

- **Well-done / Animation:** the scripts that WRITE compositions (`build-reel-type.py`, the graphics in
  `hf-graphics/<name>/`, captions). No `reel_render.py render`, no MP4.
- **Medium:** the same compositions for each named `.mov` layer. No render, no CapCut write.
- **Raw:** nothing is rendered on this route, so there are no layers. Each beat carries a `mock` of the
  CapCut text instead (below), drawn in her pack's fonts. Say once that CapCut sets the final type.

## 3. Pick the beats

One beat per thing that appears on screen, in order: the hook, a subhead or thought, ONE beat showing the
caption look, every graphic the creative plan placed, every takeover or breakaway, the end card or CTA. Don't
pad it with plain face moments; don't leave out anything she will see.

For each beat, `t` is the moment the element has fully LANDED (its entrance done, usually ~0.6 s after it
starts), never mid-animation. Write what a still cannot show in `motion`, in plain words.

`projects/<job>/beat-sheet/beats.json`:

```json
{
  "job": "the-pricing-one",
  "route": "well-done",
  "pack": "Butter",
  "base": "projects/the-pricing-one/outputs/the-pricing-one.mp4",
  "layers": [
    {"dir": "hf-reel-type-butter"},
    {"dir": "hf-graphics/03-count-up", "offset": 5.40}
  ],
  "beats": [
    {"t": 1.9, "kind": "hook", "says": "the hourly CEILING",
     "motion": "builds a word at a time, CEILING lands last in yellow, holds to 6s"},
    {"t": 6.2, "kind": "count-up", "says": "$2,000",
     "motion": "ticks up from $0 as she says it, a bar fills under it"},
    {"t": 14.0, "kind": "captions", "says": "read-along captions",
     "motion": "one word at a time, low, instant on and off"}
  ]
}
```

- `base` defaults to `outputs/<job>.mp4`, the rough cut. Point it at the cut this reel is actually built on.
- `layers`: every composition, bottom to top, folder relative to the job. `offset` is where that layer starts
  in the reel (a graphic built from 0 that plays at its beat's `start`); leave it out for a full-length layer.
- `n` numbers itself 1, 2, 3 in time order. Keep the numbers stable once she has seen the sheet: a new beat
  takes the next free number, so "beat 7" always means the same thing.
- **Raw route:** no `layers`; each beat gets
  `"mock": [{"role": "headline", "text": "the hourly ceiling", "y": 0.30}]`.
  `role` is a pack role (`headline`, `takeover`, `caption`, `accent_caption`, `thought_bubble`); `y` is the
  centre as a fraction of the height (from the plan's placement); optional `px`, `"color": "accent"`.

## 4. Make it and hand it over

```bash
python3 .claude/skills/beat-sheet/scripts/beat-sheet.py <job>
```

A few seconds per layer (stills, never a render). It writes **`beat-sheet/beat-sheet.html`, the beat sheet she
reviews**: a director's cut, three stills to a row, each with its beat, time, words and one short motion line
under it, tap to enlarge, no note boxes (her notes come in the chat by beat number). Keep each beat's `says` and
`motion` to one short line so the page reads at a glance. It also writes `beats/NN.jpg` (each beat full size),
`beat-sheet.md`, and `beat-sheet.jpg`, a single-image fallback used ONLY when there is no side browser.

**🔴 The HTML page in the app's side browser IS the beat sheet, every time. Never link the `.jpg` in chat** (it
opens as one flat image, which is not the review she asked for). Opening the page costs no extra tokens: open
it, never read it back. The side browser turns a `file://` page into a size-capped snapshot, so serve it: a
`.claude/launch.json` entry named `engine-projects` that runs
`python3 -m http.server <port> --bind 127.0.0.1 --directory <engine>/projects` (`python` on Windows; add the
entry if missing, with this engine's own absolute path), `preview_start` it, then `navigate` to
`http://localhost:<port>/<job>/beat-sheet/beat-sheet.html`. After `--only`, `navigate` to the same URL again to
reload it. Only when there is no side browser at all: hand over the printed fallback image link instead.

Hand it over short, as the turn's final message (the app folds text written before a tool call): how many beats,
that it is open in the side browser, then **"Nothing is rendered yet. Tell me what to change by beat number, like
'beat 4, bigger.' Say 'looks good' and I'll render it."** No image link.
Don't open the stills to check them yourself (rule 5); the script says when a layer or frame failed.

**When the stills can't be made, the review still happens.** A layer it could not take stills of (no Node on
this computer, a snapshot that hung) is left off and the script says so in one line: pass that line on as it is.
If it prints a line starting **`TEXT BEAT SHEET`**, there are no stills this time: read the `beat-sheet.md` it
names and show that table in the chat, with one calm line before it saying the stills couldn't be made this time
and why (the reason it printed). Then hand over exactly as above: notes by beat number, "looks good" renders.
Don't stop the build over it and don't investigate; it is logged for /report-a-problem.

## 5. Her notes, then the render

- Change only the beats she names, in the plan and the composition, then
  `beat-sheet.py <job> --only 4,9` and show the sheet again. Beats she didn't name stay exactly as they were.
- A note about motion ("make beat 6 slower") can't show on a still: change it, update that beat's `motion`
  line, and say it will show in the render (or offer to sandbox that beat).
- A note that is really a cut change goes back to the style plan, not here.
- "Looks good" / "render it" / "build it" → the normal render or CapCut write for the route. That approval is
  the build gate; don't ask again. **On the visual editor path** (`python3 product/review_route.py <job>` says `editor`): don't render
  here. Run `python3 product/visual_editor.py looks <job>` and tell her the looks are on her page and that the
  **Finish** tab renders them (CapCut or an MP4). One render, from one place.

Log each note she gives here for the end-of-reel checklist (the `learn` skill, "Teach my style from this
reel"): `python3 product/teach_style.py note <job> "<her words>" --from "beat sheet"`. If a correction will
recur ("you always put the count-up too low"), offer to make it her default now (rule 6).

## 6. Sandbox a beat (see it move)

"sandbox beat 7", "sandbox this section", "let me see beat 7 move", "show me that part moving":

```bash
python3 .claude/skills/beat-sheet/scripts/sandbox.py <job> --beat 7            # ~3 s around the beat
python3 .claude/skills/beat-sheet/scripts/sandbox.py <job> --from 71.5 --to 75  # any stretch she names
```

Every layer is cut down to just that stretch (widened to whole words and cards) and rendered on its own, then
stacked over that slice of her cut with her audio: seconds, not the minutes a full render takes. Each try is
kept as `beat-sheet/sandbox/beat-07-vN.mp4`. Hand back ONE line and the printed link, last.

- She tweaks ("slower", "try the bold one"): change the composition for that beat only, run it again. Her
  approved beats are never touched.
- **"use that same look on the rest of the reel"**: carry the change to every matching moment (same element,
  same pack), update their `motion` lines, then the ONE full render. Offer the beat sheet again first if the
  change touched other beats she already approved.
- Raw route: nothing to sandbox (CapCut animates that text); the script says so.
- A layer that won't render is left out of the clip in one line. With no Node, or no layer rendering at all, it
  hands back that beat's still from the beat sheet instead: pass on its line and the link it prints.
- It is a preview. It skips the render gate; the final render still runs it.
