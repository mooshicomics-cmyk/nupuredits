# FLOW.md — the reel-build flow (every route, one build)

How a reel is built end to end, across every option. Every engine build and every course lesson follows it.
(History behind these rules is kept seller-side; this file is the rules.)

## The principle

**Everything is built in ONE pass, before CapCut opens the draft.** CapCut is polish only. So: **collect every
creative choice → build once → finish.** No creative choice comes after the build, and none comes before the
rough cut: the choices are collected at the creative plan, after she has approved her cut (the course's order). CapCut must be quit for every
draft write. If a pick changes after she is in CapCut, follow `CLAUDE.md` rule 7 (layer on top with CapCut
quit, or duplicate to a new version); never replace her draft.

Gate decisions (the doneness route, the register) come as ONE clean pick-one prompt with the likely default
marked, never prose (`CLAUDE.md` rule 1). **The doneness pick-one ("how done do you want it") belongs to the
original widget road only.** A reel on the visual editor (`product/review_route.py <job>` says `editor`) is asked
the register and nothing else: where it goes is her Finish tab.

## The four outputs

The same house treatments (the pack looks: palettes, tone-on-tone, blocks, multicolor, stars/doodles/borders,
grain, animated type, motion graphics) run at every level; what changes is how they are delivered. **Any render
above raw uses the pack looks.**

| Output | Delivery | She still edits | Her creative input |
|--|--|--|--|
| **🥩 raw** (Route C) | CapCut draft; treatments only as far as CapCut does natively (accent text, pack colors, native animations). No rendered overlays. | Everything | Plan → approve |
| **🥩 medium** (Route B) | Editable CapCut base + treatments as rendered `.mov` overlays (takeovers, multicolor text). Claude also adds SFX, gifs/bubbles and clip scaling in CapCut. | Everything; type moves as a block | Plan → approve |
| **🥩 well-done** (Route A) | A finished baked video (`build-reel-type.py`). Claude watches and self-checks it before handing over. | Nothing | Plan → approve → iterate |
| **✋ Hands-Off Edit** | The same baked video, one click: after the rough cut is approved, Claude makes every call. | Nothing | None past the rough cut |

Well-done and Hands-Off are the same output; the only difference is who decides.

**Across all levels:**
- **Default to the full library; she subtracts.** Apply graphics, motion, animated text, SFX and pack
  treatments proactively, fit to the register (confessional gets almost nothing, teaching earns designed
  moments). The plan reads "here's the treatment I'm applying, tell me what to pull", not "pick from these".
  Never strip effects to be safe.
- **Color grading stays hers in CapCut.** Grade only when she asks for one by name.

## Steps 1–3, same for everyone

1. **Rough cut** (`rough-cut`). All beat cuts happen in the style plan, never in CapCut.
2. **Style pack**: Editorial / Playful / Butter, or one she built. Chosen once, reused; sets fonts, sizes, accent.
   For any above-raw graphics build, **load ONLY the chosen pack's `product/creative-vault/design/<Pack>.design.md`**.
3. **Format**: **Yap** (graphics load follows the register) · **Voiceover** (audio-first cut engine,
   `product/VO-REEL.md`) · **Animation** (no filming; designed frames over her VO or music, never an AI voice) ·
   **B-Roll Reels** (`broll-reels`). The doneness routes below apply to all of them.

**Treatment (how loaded) and doneness (how baked) are independent.** A trimmed-back Yap can be raw, medium or
well-done. Ask both, at the creative plan; never assume confessional means raw.

## How to ask: the steak question (verbatim, one short line each)

- **🥩 raw**: editable CapCut draft: hook, thoughts and bumper text you can retype; pack colors and native
  touches as far as CapCut goes.
- **🥩 medium**: CapCut draft with the designed look rendered on named `.mov` layers you move, resize and
  toggle but don't retype; I also add your SFX and gifs in CapCut.
- **🥩 well-done**: a fully baked video; the type is rendered in. **Ask whether she also wants it in CapCut**; if
  so, hand over a project beside the MP4 (her cut on the main track, graphics over it, each sound cue on its own
  clip): `uv run product/capcut_handoff.py <JOB> --overlay <overlay>`. The MP4 stays the deliverable.

Never frame it abstractly ("editable text vs rendered kinetic layers"). **✋ Hands-Off** is offered separately,
not as a steak: "approve the rough cut, then I take it from there and hand you a finished MP4."

**Captions ask (raw and medium only, at the style plan):** "Do you want me to build the captions, or are you
running CapCut's Auto Captions?" If her: "styled text layers in CapCut (editable) or a rendered overlay (baked
look)?" Well-done and Hands-Off bake captions in, no ask.

## The routes

| Route | Finish | Type / treatments | Built by |
|--|--|--|--|
| **C · raw** | CapCut draft | hook + thoughts as editable CapCut text; native Auto Captions (or per the ask); SFX and graphics ride along | VectCut: `cleanyap.py` / `superyap.py` (`add_text`) |
| **B · medium** | CapCut draft | rendered type on named `.mov` layers; SFX/gifs | VectCut base + `build-hf-captions.py` → render → qtrle/argb → `build-overlay.py <mov> "<Layer Name>" <render_index> <spans.json>`. Karaoke, rendered takeovers, count-ups, stars, breakaways (every spoken-cue reel): `product/SUPERYAP.md` Medium |
| **A · well-done** | MP4, never opens CapCut | everything baked: hook, thoughts, captions, SFX, graphics | HyperFrames + ffmpeg (`build-reel-type.py`, `build-reel-mp4.py`) |
| **✋ Hands-Off** | MP4 | same as well-done, decided autonomously | same |

**Route B named layers:** each type role is its own dead-space-trimmed `.mov` on its own named track
(e.g. Captions · accent font · Takeover · Hook) so she can move, toggle or delete each one. Built in the one
pass; adding one later only with CapCut quit (`build-overlay.py` enforces it).

**Course note, not a live question:** on raw she can ask Claude to build captions as editable text, but they
are one-off text pieces without CapCut's auto-highlight or karaoke. Teach it in the lesson; keep it out of the flow.

## On the visual editor (the default review): one page, one render

When she reviews on the visual editor page (`rough-cut`'s style plan pick), the routes above collapse into the
page's Finish tab: **CapCut** (her cut on the main track, each look its own rendered layer, each sound its own
clip: the medium shape) or **an MP4** (everything baked: the well-done shape). The creative plan asks only the
register; the looks are drawn (never rendered) and play live on the page; Sound fills its own defaults; the
beat sheet (the page calls it the Storyboard) lives on the Finish tab; `product/finish.py` does the one render, whether she presses Export or types
"render". The raw route (CapCut's own editable text) stays a chat route she asks for by name.
A fourth Finish destination is the **Edits app** (Instagram's): `product/edits_handoff.py` stages the cut + the
same rendered looks and the `edits-export` skill drives them into the app live (its `.mcomp` archive is off in
public MCP mode, so there is no file to author). Like Resolve, it is **medium only** and **style-preserving**:
the packs' fonts are CapCut-native, so a raw build in Edits (or Resolve) would drop the look. Say that trade-off
once at the handoff if she asks for raw there, and point her at CapCut (or a future Edits-native pack) for raw.
**One-shot (`autopilot`):** the same path with no stops, ending in a finished draft or MP4 and the page open.
**The road is locked per reel** (`product/review_route.py <job>`): once she opts in it reads `editor` and nothing
below this heading runs for that reel (the widget builder and the Clean/Super Yap builders refuse it) unless she
asks for the original widget for that reel by name.

## Then every route converges

SFX (on/off, light/heavy; **rotate the clicks**, never the same twice) and graphics ride in the same build →
**approve the whole plan (one gate)** → **one build pass** (cut + zoom + type + graphics + SFX + animation),
which stops before it renders for the **beat sheet** (`beat-sheet` skill: numbered stills, her notes by beat
number, every route, even a two-beat reel, Hands-Off included; "sandbox beat N" shows one beat moving) → finish: Route A exports the MP4; Routes B/C open CapCut once for polish (native captions on Route C) and export.

## Cover / thumbnail (optional, phased)

A cover is a frame from her footage plus a title. Never pick both in one shot:
1. `uv run workflows/cover-frame.py projects/<job>/outputs/<job>.final.mp4` (the `cover-thumbnail` skill) writes
   the top clean frames to `thumbnails/candidates/`. Send them numbered. ⏸ she picks.
2. Title options: short, punchy, curiosity, tied to anything visible. ⏸ she picks.
3. Build: title in the pack's headline font + accent color, anchored **top (above head) or center, never
   bottom**, one accent word, a scrim or highlight for legibility. ffmpeg frame → PIL title overlay.

## Non-negotiables (every route)

- **Raw gets NO rendered vibe/flourish overlay** (no rendered underline, circle, stars, kinetic doodles). Those
  belong to medium, or are skipped.
- **One route per project.** Never flip a reel between levels in place (different builders, conflicting state).
  A level change = duplicate the footage into a new, renamed project and build fresh.
- Beat cuts happen in the style plan, not CapCut.
- **Captions yield to any full-screen takeover or breakaway, on both sides**: they clear before it starts and wait
  out its held tail; a breakaway's guard widens by its fade (`build-reel-type.py` `_yield` + `_BK_GUARD`).
- **The motion-graphic breakaway is standard on every above-raw output** (`CP["breakaways"]` in
  `build-reel-type.py`): a full-screen pack card that pushes in (1.06→1), an accent bar wipe, staggered
  `back.out` line landings, a late accent pop on the emphasis word. Never a flat fade. Raw has none.
- Every added layer is individually named and editable, never grouped (except Route A, a full render by definition).
- Every finalize runs the base guardrails: magnet on all tracks, text safety + 9:16 wrap.
