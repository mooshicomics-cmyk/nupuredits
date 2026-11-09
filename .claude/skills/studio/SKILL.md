---
name: studio
description: The craft layer. Named finishing commands that hold reel typography, layout, motion, and color to a consistent standard so the same corrections never get typed twice. Use when the creator says "/studio", "/studio font", "/studio tidy", "/studio accent", "/studio glow" (v1 verbs), or asks to clean up / fix / polish the look of a reel's text, spacing, animation, or color. Studio adjusts design INTENT and each render path honors it its own way. It does not decide the creative direction; it keeps whatever is built from ever being sloppy.
user-invocable: true
argument-hint: "[font|tidy|accent|glow · hush|punch · single|karaoke|takeover · vibe · inspo] [hook|caption|takeover|thought · a line · or a reel link]"
---

# Studio: the craft layer

Studio is the finishing suite for reels. It sits UNDERNEATH the three doneness levels (raw / medium /
well-done) and keeps the reel from being sloppy no matter which one the creator picks. It encodes taste as
named commands so the creator never hand-coaches the same fix again.

**What Studio is not:** it is not a creative-direction tool and it is not "skills vs freedom." The creator
still decides teaching vs confessional, which format (Yap / Voiceover / Animation), which style pack, which doneness. Studio only
holds the *craft* consistent within whatever they chose. Think of it as the difference between "what to make"
(theirs) and "make sure it is not wrong on the first render" (Studio's job).

**Naming ethic (hold this):** Studio does the work; it is honest that AI is doing it. No "handcrafted /
handmade / by hand" language anywhere. The command names signal the OUTCOME, never the literal task, so the
creator can be a feeling-informer, not an executor.

## How to invoke

`/studio <verb>` acts on the whole reel. `/studio <verb> <element>` targets ONE role (hook, caption,
takeover, thought). With no verb, read the situation and suggest the one that fits, like a good editor would.

Examples (teach these):
- `/studio hush hook` -> make the hook quieter: smaller, so it takes fewer lines
- `/studio punch hook` -> make the hook bolder: bigger
- `/studio font caption` -> fix just the caption's size and wrapping
- `/studio tidy caption` -> reseat just the caption in its band

**Wrapping principle (hold this everywhere): fill the line, break only when you must.** Lines use the width
on purpose; they never break narrow for no reason. NEVER shrink the hook just to avoid a break, a longer hook
that fills the screen is fine. Size is the creator's call via `hush` / `punch`, never an automatic shrink.

## The menu (DISPLAY this when the creator types `/studio` with no verb)

Show it like a little control panel, the way impeccable lists its commands, so they can pick by feeling. Print
it, then ask which they want or read the reel and suggest the one that fits:

```
  /studio font      text hierarchy + sizing          e.g.  /studio font      ·  /studio hush hook
  /studio tidy      layout, spacing, placement       e.g.  /studio tidy caption
  /studio accent    color that reads over footage    e.g.  /studio accent
  /studio punch     make one thing bolder / bigger   e.g.  /studio punch hook
  /studio hush      make one thing quieter / smaller e.g.  /studio hush hook
  /studio single    a line -> single-word captions    e.g.  /studio single <line>
  /studio karaoke   a line -> karaoke word-build       e.g.  /studio karaoke <line>
  /studio takeover  a line -> full-screen takeover     e.g.  /studio takeover <line>
  /studio behind    put the hook (or a gif) BEHIND you e.g.  /studio behind hook
  /studio inspo     borrow style from a reel you love e.g.  /studio inspo <link>
  /studio recipe    build your OWN pro style pack      e.g.  /studio recipe
  /studio vibe      one tasteful personality touch    e.g.  /studio vibe
  /studio ultra vibe  stack every effect that fits (max styling) e.g. /studio ultra vibe
  /studio glow      the final ship pass              e.g.  /studio glow
  /studio document  regenerate the system source-doc e.g.  /studio document
  /studio reset     revert to the launch baseline    e.g.  /studio reset
  (soon: flow)

  tip: add an element to target just that one -> /studio <verb> <hook | caption | takeover | thought>
```

## The verbs

Each verb owns one playbook in `reference/`. Load that file when the verb runs. Every verb ends by handing
off to **glow** (the terminal ship pass), the same way a real finish always ends with one last look.

**v1, the core four (these map to the four corrections that keep coming up):**

| Verb | Playbook | Holds |
|---|---|---|
| **font** | `reference/font.md` | Text hierarchy + sizing. Hook not too tall, nothing running off screen, captions readable but never competing with the spoken moment. The #1 recurring fix. |
| **tidy** | `reference/tidy.md` | Layout, spacing, placement. Holds the safe zone (text stays readable, never overlaps the face). |
| **accent** | `reference/accent.md` | Color that READS. Adjusts the accent shade + text-over-footage legibility, INSIDE the chosen style pack's fixed palette. |
| **glow** | `reference/glow.md` | The final ship pass. Catches the small alignment and spacing misses before export. |
| **hush** | `reference/hush.md` | Dial one element DOWN (quieter, smaller). `/studio hush hook` = a smaller hook, fewer lines. |
| **punch** | `reference/punch.md` | Dial one element UP (bolder, bigger). `/studio punch hook` = a bigger hook. |
| **single / karaoke / takeover** | `reference/captions.md` | Swap ONE transcript line's on-screen treatment: single-word snap · karaoke word-build · full-screen takeover. `/studio karaoke <line>`. Per-line, rest of the reel unchanged; extensible to any preset layout. |
| **behind** | `reference/behind.md` | Put the hook (or a gif) BEHIND the subject — her silhouette occludes it (text-behind-head look). Mattes her out + composites. `/studio behind hook`. |
| **document** | `reference/document.md` | Regenerate `STUDIO-SYSTEM.md` from the LIVE engine (packs, commands, standards) — the reel-engine analog of impeccable's `document`. The one source of truth + community teaching hub. `/studio document`. |
| **reset** | `reference/reset.md` | Revert the built-in packs + design settings to the LAUNCH BASELINE (how it shipped). Keeps your own custom packs + backs up current first. `/studio reset`. |
| **inspo** | `reference/inspo.md` | Turn a reel you love into a pick-list of borrowable style elements (type, effects, animation, pacing, color, captions, sound), pulled via Apify. `/studio inspo <link>`, or name what to match: `/studio inspo <link> match the sound effects`. Study the format, never the concept. Ends by OFFERING to keep what they picked (a named pack via `recipe`, an animation or a density via `/learn`) so a borrowed look outlives the one reel. |
| **recipe** | `reference/recipe.md` | Build the creator's OWN complete pack (the pro version of the `style-pack` skill): 3 fonts + 2 colors + a mood + a name → a contrast-checked palette AND a designed card theme via `product/pack_recipe.py`, refined through impeccable, written into `style-packs.json` + `pack_palettes.py` so it works in every doneness. `/studio recipe`. |
| **vibe** | `reference/vibe.md` | Personality pass. ONE tasteful, real touch (emoji, doodle, sparkle, handwritten note) matched to the beat and register. Never AI-generated: it proposes, you approve. |
| **ultra vibe** | `reference/ultravibe.md` | The MAXED styling pass. Stacks as many HyperFrames effects as tastefully fit (element library: stars/blocks/marks · karaoke captions + keyword highlight · a designed full-screen takeover on the key beat · grain · motion moments), pack- and register-aware, impeccable-gated. The "show me the ceiling" command. **NOT for raw** (native CapCut can't house it) — lives on **medium → hands-off**. |

**Coming next (same spine, not built yet):** flow (motion).


## Before any verb touches a render: load two files

- **`reference/craft-floor.md`**, the quality floor. Hard rules (pass/fail: the safe zone, no face overlap,
  legibility minimum) and soft rules (everything aesthetic, rebuttable by the creator's intent). The floor
  holds the mechanics; it never picks the direction.
- **`reference/scale.md`**, the relative system. Studio never reasons in fixed pixels. The hook is the anchor
  and everything sizes in proportion to it. Read this so a "bigger caption" means the right thing on any font,
  any footage.

**When rendering WELL-DONE, also cross-reference `product/IMPECCABLE-TYPE-PRINCIPLES.md`** — the impeccable
text/layout/readability/placement guidelines (typeset · layout · adapt · craft-floor), adapted to the reel.
The well-done render is self-verifiable, so check every sizing/placement/hierarchy call against it from the
rendered frame (hierarchy obvious at a glance, squint test, readable over footage, balanced no orphans, grouped
with rhythm, soft shadow) before it's done. Raw/CapCut carries the same intent but is verified by the creator's
eyes + a Text-panel screenshot, not a self-render.

## The honest promise: read `reference/fidelity.md`

Studio commands adjust design intent; each render path honors that intent as far as its engine allows. You may
promise the SAME INTENT everywhere, but not identical pixels across paths. The floor is met on all three; only
the MP4 path is pixel-guaranteed. `reference/fidelity.md` is the exact per-path, per-verb contract. Never
promise a creator more than the path they picked can deliver.

## Architecture note (for whoever extends this)

Studio is a house design brain with reels as the first surface, not a reel-only tool. The **taste core**
(`scale.md` + the soft rules in `craft-floor.md`) is format-agnostic: hierarchy, proportion, rhythm, weight,
color-as-role. The **reel adapter** is only the reel-specific hard rules (the 9:16 safe zone, the speaker's
head). A future surface (carousel, print) adds its own thin adapter and reuses the core. Do not hardcode reel
assumptions into the core.
