# STUDIO SYSTEM — the reel engine, documented

> AUTO-GENERATED from the live engine by `product/studio_document.py`. Re-run to refresh. Do not hand-edit;
> edit the source (style-packs.json / the Studio skill / the standards docs) and regenerate.
> Generated 2026-08-10.

This is the one source of truth for what the reel engine can do. The CORE product is deliberately simple —
fast, done-for-you, you never have to know this menu. This document is the reference behind it (and the
community's teaching hub / "here's the ceiling" showcase).

## Formats
- **Clean Yap** — trimmed-back talking head: hook + thought bubbles (the pack's thought font) + matched SFX over full-screen footage. Fully editable in CapCut.
- **Super Yap** — the loaded version: same base + doodles / illustrations / animations / full-screen moments (HyperFrames overlays).
- **VO Reel** — faceless, voiceover-led: her VO over her b-roll, cut to the VO cadence.

All 9:16 · 1080×1920 · editable-first in CapCut.

## Doneness (a separate axis from format)
- **Well-done** — baked MP4 (self-verifiable, pixel-guaranteed). `build-reel-type.py` → HyperFrames render.
- **Medium** — CapCut + rendered `.mov` overlays.
- **Raw** — fully editable CapCut draft (native text + Auto Captions).

## Style packs (live from `style-packs.json`)
| Pack | Headline font | Accent | Subhead source | Well-done tuned | CapCut tuned |
|---|---|---|---|---|---|
| **Editorial** | Playfair Display | `#ffadbf` | accent_caption | ✅ | ✅ |
| **Butter** | Inter | `#fdc341` | caption | ✅ | ✅ |
| **Playful** | Soup Du Jour | `#F5C518` | accent_caption | ✅ | ✅ |

Creators can build their own with the `style-pack` skill (3 fonts + accent, layout stays locked).

## Type gold standards (LOCKED)
Two independent outputs, each with its own standard; the pack holds the shared typeset rules + color both read.
Full spec: `STUDIO-TYPE-GOLD-STANDARDS.md` · impeccable cross-reference: `IMPECCABLE-TYPE-PRINCIPLES.md` ·
per-cell lock status: `STUDIO-CALIB-STATUS.md`.
- **Well-done:** measure the real font · headline = the anchor, sized big + balance-wrapped ≤2 lines, no orphans · everything sizes down · one tight line-height · captions below the chin · safe zone.
- **CapCut:** native pack sizes + the 720 box, let CapCut auto-wrap · per-pack `capcut` block for exact size/tracking/line-spacing.

## Studio commands (live from the Studio skill)
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

| Command | What it does |
|---|---|
| `/studio font` | Text hierarchy + sizing. Hook not too tall, nothing running off screen, captions readable but never competing with the spoken moment. The #1 recurr… |
| `/studio tidy` | Layout, spacing, placement. Holds the safe zone (text stays readable, never overlaps the face). |
| `/studio accent` | Color that READS. Adjusts the accent shade + text-over-footage legibility, INSIDE the chosen style pack's fixed palette. |
| `/studio glow` | The final ship pass. Catches the small alignment and spacing misses before export. |
| `/studio hush` | Dial one element DOWN (quieter, smaller). `/studio hush hook` = a smaller hook, fewer lines. |
| `/studio punch` | Dial one element UP (bolder, bigger). `/studio punch hook` = a bigger hook. |
| `/studio single / karaoke / takeover` | Swap ONE transcript line's on-screen treatment: single-word snap · karaoke word-build · full-screen takeover. `/studio karaoke <line>`. Per-line, r… |
| `/studio behind` | Put the hook (or a gif) BEHIND the subject — her silhouette occludes it (text-behind-head look). Mattes her out + composites. `/studio behind hook`. |
| `/studio document` | Regenerate `STUDIO-SYSTEM.md` from the LIVE engine (packs, commands, standards) — the reel-engine analog of impeccable's `document`. The one source… |
| `/studio reset` | Revert the built-in packs + design settings to the LAUNCH BASELINE (how it shipped). Keeps your own custom packs + backs up current first. `/studio… |
| `/studio inspo` | Turn a reel you love into a pick-list of borrowable style elements, pulled via Apify. `/studio inspo <link>`. Study the format, never the concept. |
| `/studio recipe` | Build the creator's OWN complete pack (the pro version of `style-pack`): 3 fonts + 2 colors + a mood + a name → a contrast-checked palette + designed card theme via `product/pack_recipe.py`, written into `style-packs.json` + `pack_palettes.py` so it works in every doneness. `.claude/skills/studio/reference/recipe.md`. |
| `/studio vibe` | Personality pass. ONE tasteful, real touch (emoji, doodle, sparkle, handwritten note) matched to the beat and register. Never AI-generated: it prop… |
| `/studio ultra vibe` | The MAXED styling pass. Stacks as many HyperFrames effects as tastefully fit (element library: stars/blocks/marks · karaoke captions + keyword high… |

## Vibe palette (the delight pass — proposes, you approve)
Real elements only, animated ON naturally (draw-on / twinkle / settle), one touch per earned beat, by register:
real emoji · sparkles (✨) · **daisy · marker sparkle · marker underline** (clean white vector doodles, draw-on) ·
emphasis word (italic) · accent underline · word-on-arc · **blue iMessage bubble** · full-screen takeover.
Rejected: ✦ diamond sparkle, solid+hollow pairing. Full playbook: `.claude/skills/studio/reference/vibe.md`.

## Motion-graphic library (starter — grows in the community)
Reel-ready animated overlays the plan pitches from: **count-up stat · 3-step build · myth→truth · lower-third
label** (+ growing: animated timeline, checklist, headline card). Teaching-register / Super Yap. Built via the
`motion-graphics` + `faceless-explainer` skills; placed by `graphics-plan`.

## Behind / gif
- **`/studio behind`** — put the hook (or a gif) BEHIND the subject; her silhouette occludes it. Mattes her out (`remove-background`) + 3-layer composite. `reference/behind.md`.
- **`/studio gif`** *(building)* — pulls the right gif from her inbox `gif/` folder by beat/emotion; gifs may cover her face.

## Fidelity (what each path can deliver)
- **Well-done MP4:** everything, exact. The pixel-guaranteed path.
- **Medium:** overlays baked into a `.mov`, moves as a block.
- **Raw CapCut:** decorative touches drop in as imported overlay clips; text-native (italic/underline) map to CapCut text styles; some effects are baked-overlay only. (Full port of all features to raw = in progress.)

## What's core vs community
- **Core product:** fast, done-for-you. The engine proposes; you feel yes/no. You never manage this menu.
- **Continuing platform / community:** the full library, the effect menu, beat-sync, explainer moments, recipes, and this document — released at your pace, taught together.
