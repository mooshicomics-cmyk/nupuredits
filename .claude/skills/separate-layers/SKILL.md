---
name: separate-layers
description: "Put the kinds of element she picks on their OWN CapCut tracks, so she can move, retime or switch one off without dragging the rest. Shows her a checkbox list of what THIS reel can separate (captions, hook, vibe, label, takeover, breakaway, elements), then renders only the ones she ticks. Use when she says: separate layers, separate the layers, split the layers, each element on its own layer, captions on their own layer, split the hook out, give me the animations separately, I can't move the overlay without moving the captions, everything is on one track, I need control over every asset. NEVER answer any of those with 'that route is baked' or by telling her to start over on a different finish."
---

# Separate layers — she ticks what she wants on its own CapCut track

## The rule this skill exists to enforce

**If she asks for things separated, say yes.** Do not make her take a different route for it, do not tell
her the route is baked, and do not tell her to rebuild on a different finish. That is a dead end and
[`CLAUDE.md`](../../../CLAUDE.md) ("🚪 NO ROUTE IS A DEAD END") forbids it. Answer with what she can have.

This came from the first PC tester, who had three reels in progress, could not move an overlay without
dragging the captions with it, and was ready to quit. The capability was already half there and not
reachable by asking. This skill is the front door.

## The flow — always two steps, never one

### Step 1. Ask what is in HER reel, then show her the checkboxes

```bash
./product/separate_layers.sh --list <JOB> <PACK>
```

No render, no cost. It reads the overlay she already has and reports only the layers that are really in
it, with how many pieces and when they are on screen:

```
  Layers available in my-reel (Butter):
    [x] captions  the spoken-word captions                    79 clip(s), 0.0s–82.2s
    [x] hook      the opening hook                             1 clip(s), 0.0s–5.0s
    [ ] label     the corner label                             1 clip(s), 0.0s–15.0s
    [ ] takeover  the full-screen word takeovers               2 clip(s), 21.0s–24.6s
    [ ] breakaway the breakaway card                           1 clip(s), 10.5s–12.4s
    [ ] elements  stars, counters and badges                   3 clip(s), 0.0s–17.0s
```

**Surface that to her as a checkbox list, defaults already ticked, per the locked phase-gate rule
(CLAUDE.md: a clean prompt with the likely default marked, NEVER buried in a paragraph).** Say the cost
in the same breath: **each ticked layer is one render, plus one more for the rest when anything is left
unticked.**

**Never offer a fixed menu of six.** The available layers differ per reel — one reel offers captions and
hook, another offers five. If you offer her something her reel does not contain, she ticks it and gets
nothing back. The list command is the only source of truth for what to show.

### Step 2. Render only what she ticked

```bash
./product/separate_layers.sh <JOB> <PACK> captions,hook,takeover
```

Each ticked layer renders to its own transparent `.mov` under `projects/<JOB>/layers/`, then all of them
go to CapCut via `capcut_handoff.py --layer <name>=<file>`, which puts each on its own named track.

**Nothing she did not tick is lost.** Every other layer `--list` showed renders once more, all together, as
one extra layer called `rest` on its own track. It sits above her layers when the reel draws its topmost
element above all of them (the usual case: captions and hook are the reel's lowest layers), below them
otherwise. Say so when you hand over: "everything else is together on one more track".

Before the first render the runner checks that the editing engine is running and CapCut is closed, and
stops right there if not, so minutes of rendering are never thrown away at the hand-over. Every render goes
through `product/reel_render.py` (the gated renderer); one that stops says why, and its full log is at
`projects/<JOB>/layers/<layer>.render.log`. A layer is held to the same checks as the full reel. A render that
came out empty stops it: tell her the reason in plain words and fix it the way you would for the full render,
never by skipping the gate. Text sitting on her face is said and the layer still renders: tell her which one,
and offer to move it.

Two things the runner does on its own, so do not add them by hand:
- **A layer made only of full-screen moments** (`takeover`, `breakaway`, or a `rest` holding nothing else)
  covers her face by design, so it renders without the face check (`--no-subject`) and says so in one line.
  Every other check still runs on it, and any layer with anything else in it keeps the face check.
- **A type build that fails** is said in plain words with its real reason. A crash in the engine (an error
  with a file and line) is the engine's problem, not her reel's: run `/report-a-problem` with those lines
  rather than rebuilding. The build's own words are in `projects/<JOB>/layers/<layer>.build.log`.

On a computer short of memory, pass renderer options through with `REEL_RENDER_EXTRA`, e.g.
`REEL_RENDER_EXTRA="--low-memory" ./product/separate_layers.sh <JOB> <PACK> <layers>`. Unset, nothing changes.

Running it with no layer list is refused on purpose, with a pointer back to `--list`. Do not work around
that by guessing a set for her.

## The layers

| Layer | What is on it |
|---|---|
| `captions` | the spoken-word type: karaoke, build and snap captions |
| `hook` | the opening hook (`hookwrap` / `hooksplit` / `hookarc`) |
| `vibe` | the vibe element: sparkles, bubble, doodle, emoji |
| `label` | the persistent corner label |
| `takeover` | the full-screen word takeovers |
| `breakaway` | a breakaway card that owns the screen |
| `elements` | the element library: stars, counters, badges |

`captions` and `hook` are pre-ticked because they are the two people actually reposition by hand.
Everything else is opt-in so a long reel does not quietly become six renders.

A layer this reel does not have is **skipped, not rendered empty** — the builder exits 3 and the runner
says so. Do not report a skipped layer as a failure.

## What it costs, honestly

**One render per ticked layer, plus one more for everything left unticked.** Six ticked is six renders;
three ticked on a reel that has five is four. The **captions** layer captures only the stretches it is on
screen (`product/render_spans.py`: a caption layer blank for half the reel costs about half a render), and
still comes back as one full-length file at the right times. Every other layer (hook, takeover, cards, rest)
still renders across the whole comp. So:

- Tell her the count before you start. Three ticks is three renders, four when the reel has more layers
  (the `rest`).
- Only the captions are trimmed to where they show. Do NOT tell her the other layers are.
- If she is watching her usage, pair this with `sandbox this section`: get one piece right first, lock in
  the style, and only then separate the layers.

## After she edits a layer in CapCut

She tweaks by hand, then says **"your turn"** — the [`your-turn`](../your-turn/SKILL.md) skill reads her
cut back and rebuilds on top of what she did, instead of her asking the engine to redo work she already
finished by hand. Say that out loud when handing the layers over; it is the other half of the round trip.

## Rules

- **CapCut must be QUIT** before the handoff writes the draft. CapCut's next save silently overwrites
  anything written while it is open. Same rule as every other draft write in this engine. The runner checks
  it (and the editing engine) before the first render.
- **Never overwrite a draft she has hand-edited.** The handoff builds its own draft.
- Run the magnet fail-safe after the first open, per the [`capcut`](../capcut/SKILL.md) skill.
- The runner rebuilds the normal full overlay when it finishes, so the project is not left holding the
  last single-layer HTML. If you call `build-reel-type.py` with `LAYER=<name>` by hand, rebuild with
  `LAYER=all` yourself afterward.

## How this works (for the next person editing it)

Layers are read off `data-track-index`, which every clip emitter in
[`product/build-reel-type.py`](../../../product/build-reel-type.py) already stamps. Nothing is re-tagged.
The map is `_GROUP_TRACKS` near the bottom of that file: captions=1, hook=2, vibe=3, label=4, takeover=5,
breakaway=6, elements 7+i. `LAYER=hook` and `LAYER=front` keep their original behind-mode meaning untouched, because
[`product/studio_behind.sh`](../../../product/studio_behind.sh) depends on them.
[`product/layer_probe.py`](../../../product/layer_probe.py) builds the checkbox list by parsing the
generated `index.html`, so it costs nothing and cannot offer a layer the reel does not have.

Adding a layer is a one-line change to `_GROUP_TRACKS`, a matching line in `layer_probe.py`
(`GROUP_TRACKS` + `BLURB`), and a row in the table above. **Those two maps must stay in step.**
