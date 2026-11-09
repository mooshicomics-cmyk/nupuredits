#!/usr/bin/env python3
"""/studio document — generate STUDIO-SYSTEM.md from the ACTUAL engine.

The reel-engine analog of impeccable's `document` command: reads the live config (style-packs.json), the
Studio skill (commands), and the standards docs, and emits ONE source-of-truth system document that stays in
sync with what's really built. Re-run any time the engine grows: `python product/studio_document.py`.
"""
import json, os, re, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = json.load(open(f"{ROOT}/product/creative-vault/style-packs.json", encoding="utf-8"))["packs"]
SKILL = open(f"{ROOT}/.claude/skills/studio/SKILL.md", encoding="utf-8").read()
OUT = f"{ROOT}/product/STUDIO-SYSTEM.md"


def pack_table():
    rows = ["| Pack | Headline font | Accent | Subhead source | Well-done tuned | CapCut tuned |",
            "|---|---|---|---|---|---|"]
    for name, p in PACKS.items():
        hl = p.get("elements", {}).get("headline", {})
        rows.append(f"| **{name}** | {hl.get('font','?')} | `{p.get('accent_color','?')}` | "
                    f"{p.get('subhead_source','-')} | {'✅' if p.get('welldone') else '·'} | "
                    f"{'✅' if p.get('capcut') else '·'} |")
    return "\n".join(rows)


def command_table():
    rows = ["| Command | What it does |", "|---|---|"]
    seen = set()
    for m in re.finditer(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*`?(reference/[\w.-]+)`?\s*\|\s*(.+?)\s*\|\s*$", SKILL, re.M):
        verb = m.group(1).strip()
        if verb in seen:
            continue
        seen.add(verb)
        desc = re.sub(r"\s+", " ", m.group(3)).strip()
        if len(desc) > 150:
            desc = desc[:147].rstrip() + "…"
        rows.append(f"| `/studio {verb}` | {desc} |")
    return "\n".join(rows)


def menu_block():
    m = re.search(r"## The menu.*?```(.*?)```", SKILL, re.S)
    if not m:
        return "(menu not found)"
    lines = m.group(1).strip("\n").splitlines()
    return "\n".join(l[2:] if l.startswith("  ") else l for l in lines).strip("\n")


DOC = f"""# STUDIO SYSTEM — the reel engine, documented

> AUTO-GENERATED from the live engine by `product/studio_document.py`. Re-run to refresh. Do not hand-edit;
> edit the source (style-packs.json / the Studio skill / the standards docs) and regenerate.
> Generated {datetime.date.today().isoformat()}.

This is the one source of truth for what the reel engine can do. The CORE product is deliberately simple —
fast, done-for-you, you never have to know this menu. This document is the reference behind it (and the
community's teaching hub / "here's the ceiling" showcase).

## Formats
- **Clean Yap** — trimmed-back talking head: hook + Ugly Dave thought bubbles + matched SFX over full-screen footage. Fully editable in CapCut.
- **Super Yap** — the loaded version: same base + doodles / illustrations / animations / full-screen moments (HyperFrames overlays).
- **VO Reel** — faceless, voiceover-led: her VO over her b-roll, cut to the VO cadence.

All 9:16 · 1080×1920 · editable-first in CapCut.

## Doneness (a separate axis from format)
- **Well-done** — baked MP4 (self-verifiable, pixel-guaranteed). `build-reel-type.py` → HyperFrames render.
- **Medium** — CapCut + rendered `.mov` overlays.
- **Raw** — fully editable CapCut draft (native text + Auto Captions).

## Style packs (live from `style-packs.json`)
{pack_table()}

Buyers can build their own with the `style-pack` skill (3 fonts + accent, layout stays locked).

## Type gold standards (LOCKED)
Two independent outputs, each with its own standard; the pack holds the shared typeset rules + color both read.
Full spec: `STUDIO-TYPE-GOLD-STANDARDS.md` · impeccable cross-reference: `IMPECCABLE-TYPE-PRINCIPLES.md` ·
per-cell lock status: `STUDIO-CALIB-STATUS.md`.
- **Well-done:** measure the real font · headline = the anchor, sized big + balance-wrapped ≤2 lines, no orphans · everything sizes down · one tight line-height · captions below the chin · safe zone.
- **CapCut:** native pack sizes + the 720 box, let CapCut auto-wrap · per-pack `capcut` block for exact size/tracking/line-spacing.

## Studio commands (live from the Studio skill)
```
{menu_block()}
```

{command_table()}

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
"""

open(OUT, "w", encoding="utf-8").write(DOC)
print(f"wrote {OUT} ({len(DOC.splitlines())} lines) · {len(PACKS)} packs · "
      f"{DOC.count('| `/studio')} commands documented")
