# Second pass: change one layer, never the whole reel

The **second pass** is where she asks for a graphic to go, move, change or come back, and none of that should
cost a full render. The cost does not shrink with settings: on a measured 30s composition HyperFrames' check
takes about 40s and the render about 60s, and neither `-q draft` nor `--gpu` changes that, because the time
goes into capturing frames. The only speedup is not repeating work. Re-render the one layer that changed, then
re-stack it over everything else. Her base cut (`outputs/<job>.mp4`) is never re-rendered here, and neither is
any layer she has already approved.

---

## What the engine runs: `reel_render.py`

Every rendered layer goes through one wrapper (CLAUDE.md rule 9). It renders a layer, stacks layers, and
refuses anything that would ship broken.

```bash
python3 product/reel_render.py render <comp_dir> -o <layer.mov>            # gated + cached
python3 product/reel_render.py composite --base <footage> --layers <a.mov> <b.mov> --audio <x> -o <out.mp4>
```

**`render`**, in the order it works:
1. **Refuses on a missing font file** the composition points at, before spending a minute on a render that
   would ship in a substitute face.
2. **Skips everything when nothing changed.** It hashes the composition's source (plus the measured subject
   box and any loosened-check setting), and if that hash matches the last clean render whose output still
   exists, it says so and returns at once.
3. **Gates with HyperFrames' own check** (`check --at-transitions --frame-check`, the same check
   `product/reel_gate.py` runs), sampled across the timeline and at every transition seam. Errors refuse the
   render; `--strict` refuses on warnings too (use it whenever every word must read). From the same output it
   also refuses an animation aimed at nothing. Text past the frame edge is said loudly and rendered as placed
   (`--strict` refuses it).
4. **Renders, then checks the result:** readable content outside the safe zone (`product/safe_zones.py`),
   type sitting on her (`product/subject_guard.py`, said and delivered, never refused), a render that came out
   empty, and a `.mov` whose alpha is not real.
5. **Caption layers render only where they are on screen** (`product/render_spans.py`), stitched back into one
   full-length file with `<out>.spans.json` beside it. If that can't be done it renders full length and says
   so in one line; that is normal, not a fault.

**`composite`** is the cheap ffmpeg stack, about 15s: the base, then each transparent layer in order, plus an
optional audio track. It locks a variable-frame-rate base to its own rate, stacks every layer with
`eof_action=pass` (see "In the stack" below), and grades the footage only when she asked for a look
(`--grade`). A layer with no alpha gets a warning, because it would cover the whole base.

`product/build-reel-mp4.py` stays the plan-driven well-done finish (it bakes the punch-ins and matched SFX from
`caption-plan.json`). `composite` is the fast re-stack for one changed layer, not a replacement for it.

---

## Change one layer

The layers are the ones `separate-layers` names: **captions, hook, vibe, label, takeover, breakaway, elements**,
plus **rest** for whatever she left together. `./product/separate_layers.sh --list <JOB> <PACK>` shows which of
them THIS reel has; never assume the set.

- **One element of the type overlay changed** (a hook, a takeover, a count-up in `caption-plan.json`): edit the
  plan, rebuild that layer (`JOB=<job> STYLE_PACK=<Pack> LAYER=<layer> python3 product/build-reel-type.py`),
  render it with `reel_render.py render`, re-run `composite`. Rebuild with `LAYER=all` afterwards so the job
  folder holds the full overlay again (`separate_layers.sh` does both for you).
- **One planned graphic changed** (a beat in `graphics-plan.json`): re-render only that beat's composition to
  `assets/<id>.mov`, then re-stack. On the CapCut route, swap it in place with `build-overlay.py`, which keeps her
  scale, position and keyframes, into a new draft version whenever she may have opened the draft (rule 7).
- **She wants pieces on their own tracks:** that is `separate-layers`, never a reason to re-render the reel.

**What stays durable.** `projects/<job>/hf-graphics/` and the type overlay's `hf-reel-type-<pack>/` are the build
itself, together with `caption-plan.json`, `graphics-plan.*`, `subject-zones.json` and `layers/`. Never keep any
of it only in `/tmp`, which macOS clears on its own schedule. Only render output, footage slices and font copies
are regenerable.

---

## Where a layer goes wrong

Each of these has happened in this engine's own builds. Most now have a guard; the ones with none are on you
while authoring.

### In a composition

- ⭐ **An emoji character can hang a render with no error.** The renderer's browser goes looking for a
  color-emoji font it never finishes loading, and the layer just stops progressing. Keep emoji out of the
  markup: draw the idea in the pack's own faces, or make the glyph an image once and place that,
  `python3 workflows/emoji-to-png.py coffee=☕ alarm=⏰ --job <job>`.
  **Guard:** `reel_render.py` watches the renderer, and after ten quiet minutes writes a stall report to
  `_handoff/` without stopping anything; `/report-a-problem` (`collect-report.sh --render`) gathers what the
  render did. A layer taking far longer than a sibling of the same length is the first sign: look for an
  emoji in it.
- ⭐ **An exit belongs inside its clip.** The clip is hidden the moment its window ends, so a fade still running
  then is cut off. Size the window to hold the whole exit, then hide the element with a `tl.set` at the next
  clip's start (CLAUDE.md rule 9). **Guard:** the check flags an exit with no `tl.set`; a window that is merely
  too short is not flagged.
- ⭐ **Center with `.rl-center`, never with a CSS transform.** GSAP takes over an element's transform, so a
  stylesheet `translate` on anything it animates is folded into the tween and the element lands off its mark.
  `.rl-center` (`product/reel-graphics-base/reel-layout.css`) centers with `inset` and margins instead, and a
  starting pose goes in `tl.set` or `tl.fromTo`. **Guard:** none; it renders, just in the wrong place.
- **Most check warnings are editor hints.** `reel_render.py` counts warnings by kind and marks the ones that
  are only editor or style hints (`_NOISE_KINDS`), then lists every real ✗ (contrast, overlap, overflow) on a
  REVIEW line. Read the REVIEW lines; the counted hints need nothing.

### Her footage stays out of the browser

A composition only ever carries type and graphics. Movement on her footage is done where it can be exact:
punch-ins in `build-reel-mp4.py` as a pre-scaled copy of the footage switched on for its window (a punch-in is
a cut, and this keeps one clean scale for the whole window), and on the CapCut route in `capcut_motion.py`.

When the Voiceover build moves b-roll in ffmpeg (`product/vo-build.py`):

- **`zoompan` makes one output frame per input frame** (`d=1`), so a clip at any rate but the reel's plays fast
  or slow under a zoom. A clip not already near 30 fps is brought to 30 before the zoom.
- **A shot asked to run past the end of its clip comes back short**, and every later shot lands early against
  the voiceover. The build holds the clip's last frame for the missing time and names the `out` to fix in
  `shot-plan.json`.

### In the stack

- ⭐ **Every overlay is released when its input ends** (`eof_action=pass`). Left at ffmpeg's default, a layer
  that ends early keeps its last frame on screen for the rest of the reel. `reel_render.py composite`,
  `build-reel-mp4.py` and Clean Captions all set it, which is why a stack is never hand-rolled.
- **A base at a variable frame rate is locked to the layers' rate.** A raw phone clip reports one rate and
  plays another; `composite` compares the two exactly and, when they differ, fixes the base to the rate of the
  first layer so every graphic stays on its frame. Footage that went through the rough cut is constant already.
- **The HyperFrames version is pinned** (`0.9.6`, in `product.json`). `reel_render.py` and `reel_gate.py` read
  the pin; never call `npx hyperframes` without it.
