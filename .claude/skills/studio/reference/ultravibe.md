# /studio ultra vibe — the maxed styling pass

`vibe` adds ONE tasteful touch. **`ultra vibe` stacks as many HyperFrames effects as tastefully fit**, to
optimize the styling of a reel. It's the "show me the ceiling" command: the full designed treatment, applied
proactively (default-to-full, she subtracts — default full capability subtractive).

## ULTRA means ULTRA — the whole HyperFrames toolkit, NOT a fixed list (2026-08-09, LOCKED)
**Do not limit yourself to the effects named below.** They are a STARTING palette, not the ceiling. Ultra vibe
is the max-effort styling pass: run it like a **`/talking-head-recut` at "ultra" effort** — the full HyperFrames
creation stack (the intent layer + `talking-head-recut` + `motion-graphics` + `faceless-explainer`) — but themed
to HER packs (her palette, fonts, treatments, the taste rule). Act as the CREATIVE DIRECTOR: read the transcript
beat by beat and reach for WHATEVER effect that beat earns, including combinations we have not explicitly listed.
If HyperFrames can render it and it serves the beat in her style, it is in scope.

The arsenal to pull from (examples, keep discovering more):
- **Full-screen MOTION-GRAPHIC BREAKAWAYS** — cut from her face to a fully-designed card / animated moment in her
  pack (a claim card, a stat card, a step 1→2→3, a myth→truth flip, an animated headline), then cut back. This is
  the Hands-Off designed frame used INSIDE a footage reel. She loves this ("breaks away to a motion graphic").
  Captions + audio behavior must yield under it (see timing).
- **Number/count-up animations** on any stat or number in the transcript.
- **Text-behind-the-head** (`/studio behind` — matte + composite), **picture-in-picture**, **transcript-synced
  designed cards** (talking-head-recut), **animated explainer sequences** (timeline/flow/list).
- **The element library** (stars/blocks/marks), **karaoke + keyword highlight**, **a designed takeover**,
  **grain**, **hook punch**, **flow/entrance motion**.

## Timing — effects must not collide (2026-08-09)
When a full-screen moment owns the screen (takeover OR a motion-graphic breakaway), **captions yield on BOTH
sides** — they clear before it starts AND wait out its full held tail, then resume. This is LOCKED for ALL
takeovers, not just ultra vibe (it lives in the core caption logic of `build-reel-type.py` — `_yield` clamps a
caption's start past any takeover window it lands in, and its end before any takeover it would bleed into;
takeover window = first spoken word → last word + 0.8s hold). Breakaways get the same treatment when built.
Never let a caption sit on top of a takeover/breakaway. Two effects never fight for the same pixels on a beat.

**⚠️ SMOOTHNESS IS THE MECHANISM (2026-08-09).** Every transition must feel as smooth as native HyperFrames.
The current yield HARD-cuts captions off/on around a takeover/breakaway — that reads harsh and is wrong. Captions
must EASE out before a full-screen moment and EASE back after (short crossfade, not a snap), and ALL cut rhythms
(footage→card, card→footage, caption→caption) must be smooth/eased, matching how HyperFrames moves. That smooth
motion is the whole point of rendering through HyperFrames — never let a boundary snap. FIX before this ships
(the `_yield` clamps need a fade ramp on both edges; breakaway/takeover fades already ease, captions must too).

## Where it runs (LOCKED)
- **NOT raw.** Native CapCut can't house rendered overlays / designed takeovers / grain. On raw, ultra vibe
  degrades to whatever survives natively (accent color, a native anim) and says so — it does not pretend.
- **Medium → well-done → Hands-Off** is its home. Medium delivers the stack as rendered `.mov` overlays on the
  editable CapCut base; well-done / Hands-Off bake it. This is exactly the "the rich stuff lives above raw"
  message the course primes early.

## What it stacks (from the effect library the engine now supports)
Pull from these, choosing what the beats + the pack earn — never all-at-once-everywhere:
- **Element library** (`caption-plan.json` → `elements[]`): pack-signature shapes, colored from the LOCKED
  palette (`pack_palettes.py`), placed in SAFE zones (top band / corners, never over the face).
  Butter → blocks · Editorial → thin rules · Playful → blocks + color. Kinds: `star`, `block`, `rule`, and
  `counter` (a count-up card: `from`/`to`/`label`, pack colors, thousands grouping; this is the "stat count-up" the
  library advertises, on the finished-video route). Each pops/draws on at its `at` and holds for `duration`
  (written the natural way: how long it stays on screen).
- **Karaoke captions** (`caption_mode:"build"`) + **keyword highlight** (`keywords[]`) — energy + emphasis.
- **A designed full-screen TAKEOVER** on THE key beat (`takeover_keys`) — one big landing, not many.
- **Grain** — retro film texture (Playful), added at the composite stage over footage (or the frame ground
  in full-frame lanes).
- **Hook punch** (`hook_scale`) — size the hook up to the band ceiling (over footage it must clear the face).
- **Motion moments** (count-ups, a marked stat) where the transcript has a number/stat.

## The rules (impeccable-gated — maximal, never chaotic)
- **Taste still governs.** "As many as REASONABLY fit to OPTIMIZE styling" = make it look as good as possible,
  not cram. Cross-reference the impeccable system (`product/IMPECCABLE-TYPE-PRINCIPLES.md`): hierarchy at a glance,
  contrast floor, one accent per moment, grouped with rhythm, silence where a beat is bare. If an effect doesn't
  serve the beat, cut it.
- **Register-aware.** Teaching / explainer → load it up. Confessional → still ultra *for that register*: fewer,
  quieter, the face and the words lead. Never bury a vulnerable beat under graphics.
- **Face is sacred.** Elements in safe zones; a takeover only where briefly covering the face is fine (a punch
  beat), and captions yield under it.
- **Contrast holds over footage.** Light pack accents (Editorial pink) can wash out on busy
  footage — deepen the shade, add the drop shadow, or move the accent into a block so the text always wins.
- **Propose, then subtract.** Like vibe: ultra vibe lays the full stack into the creative plan; she pulls what
  she doesn't want. She never has to know a feature exists to get it.

## How it builds
Ultra vibe authors the effect stack INTO the reel's `caption-plan.json` (`elements` / `takeover_keys` /
`caption_mode` / `keywords` / `hook_scale`), then the normal build runs: `build-reel-type.py` renders the type +
element overlay, and the composite step lays it over the footage (adding grain). Same one-pass build as every
other finish — ultra vibe just fills the plan richly. Ends by handing to **glow** (the ship pass) like every verb.

## Fidelity by path
Medium = the stack as named `.mov` layers she can move/toggle (not retype) + her SFX/gifs. Well-done / Hands-Off =
fully baked. Raw = degraded-and-honest (see above). Per caption ask raw medium, captions on raw/medium are
still her me-or-CapCut choice.
