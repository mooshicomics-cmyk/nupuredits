# Creative Vault — COMPONENTS library

> The menu of reusable **motion-graphic building blocks** I compose reels from — especially the **loaded (teaching) Yap** treatment.
> A component = a designed, animated overlay/element with a defined **look + animation + paired sound +
> when-to-use**. New ideas get added here (the creator's directive: *"keep adding motion graphics to super yaps —
> use your full capabilities, not just my limited understanding of what's possible."*).
>
> **On every loaded (teaching) Yap I run a creative-direction pass** (read the transcript → pitch per-beat components →
> the creator approves) — see `../../superyap.json`. Confessional Yaps stay minimal; this menu is for the
> loaded treatment + teaching reels.

## Component schema
`name` · `what` (the look) · `animation` (+ resource_id from `../animations.json`) · `sound` (from
`../sfx.json`, paired to the motion) · `when` (content trigger) · `engine` (CapCut-native = editable ·
HyperFrames = rendered .mov overlay) · `status` (ready | to-develop).

---

## Text / overlay components
- **Hook card** — the pack's hook font, top, white. anim: Random Typewriter + typing SFX. when: opener. engine: CapCut. **ready**
- **Thought bubble** — the pack's thought font aside, above head. anim: rotate (Cheeky Bounce / Chalky Scribble…) + paired sound. when: reactions, deeper thoughts. engine: CapCut. **ready**
- **Typing / message bubble** — white rounded chat bubble, "…" typing indicator → text types in. anim: dots pulse → typewriter. sound: Keyboard Typing (stops when typing stops). when: confessional/DM-style opener, "hear me out". engine: CapCut or HyperFrames. **to-develop** (demoed 2026-07-29)
- **Chat thread exchange** — two-sided message bubbles appearing in sequence. when: recreating a convo / DM / text she got. engine: HyperFrames. **to-develop**
- **Crossed-out words (kinetic strike)** — loud words punch on stacked, then strike-through/dissolve. sound: type/pop in, erase/woosh out. when: rejecting a list ("hustle. climb. chase." → not that). engine: CapCut or HyperFrames. **ready** — strike-wipe proven on the example intro (an accent-color line scaleX 0→1, transform-origin left; struck word dims to ~42% white).
- **Kinetic hook intro** — the hook line as a designed HyperFrames build: the pack's hook font staggered **fragment stack** → **accent-color strike-wipe** through the "cancel" word (it dims) → payoff word lands with an **accent-color + scale punch**. Own overlay layer (`intro-kinetic`). when: opener showcase / any hook rendered kinetically. engine: **HyperFrames** (`projects/*/hf-intro/`). **ready** ("amazing" 2026-07-30).
- **Kinetic single-word snap captions** — one word at a time, the pack's caption font, low ~70%, **tight tracking** (the pack's own, negative), NO punctuation, white + keyword accents in the accent color. NO overlap (each clears as next appears). engine: HyperFrames overlay (`cap-single`). **ready**.
- **The pack's accent-font sentence-build (karaoke)** — sentence reveals word-by-word IN PLACE (fixed layout, no rearranging), ≤2 lines, with a **highlight in the accent color on the current word as spoken**; KEEPS punctuation. engine: HyperFrames overlay (`cap-build`). **ready**.
- **Kinetic takeover (the pack's takeover font)** — full-screen big text, **every word on its own line (vertical stack)**, whole phrase HELD (words lift in then all stay), vertically centered, NO punctuation, **key word in the accent color** (e.g. "nothing"). when: punch line. engine: HyperFrames overlay (`cap-takeover`). **ready**.
- **Callout / arrow label** — hand-drawn arrow + label pointing at something on screen. when: highlight a detail in footage/screenshot. engine: HyperFrames. **to-develop**
- **Lower third / name bar** — name+role bar lower-left. when: intro, credentials. engine: CapCut. **to-develop**
- **Stat card** — big number, in the pack's colors (white, ink and the accent). anim: bounce in + ka-ching/coin. when: a number she says ($300, 30K). engine: CapCut. **ready**
- **Notes-app / journal card** — a phone-notes or paper-journal card, text writes on. sound: pencil write-on. when: reflective/scripture beats, a list she's "writing". engine: HyperFrames. **to-develop**
- **Search-bar / UI reveal** — a search bar or app UI types a query. when: "I googled…", showing a tool. engine: HyperFrames. **to-develop**
- **Photo thought bubble** — a real photo inside a thought bubble. when: a memory/example she references. engine: CapCut. **to-develop**

## Footage / motion components
- **Slow keyframed zoom-in opener** — subtle push-in on the opening clip. when: yap opener, ESP confessional. engine: CapCut keyframes. **ready** (style default)
- **Jump-cut punch-ins** — scale 1.06–1.08 on accent beats. when: rhythm. engine: CapCut. **ready**
- **Full-screen word takeover (the pack's takeover font)** — each word appears as spoken, stacked, large. when: a punch line. engine: CapCut. **ready**
- **Full-screen ILLUSTRATIVE takeover / storyline** — a rendered illustrated scene that tells a mini-story under the VO (not just words). when: a vivid narrative beat. engine: **HyperFrames** (uses the 0.9.6 animation rules/blueprints). **to-develop**
- **B-roll cutaway / margins burst** — muted b-roll from a good moment; "margins of motherhood" → cooking/laundry/coffee/laptop burst. engine: CapCut. **ready**
- **Animate-her-assets** — her own doodles / product covers / screenshots slide/zoom/pop on as individual editable layers (never baked). Source: `~/brand-assets` (see brand asset catalog — 55-icon doodle pack, GROW screenshots, product covers). when: she names an example object. engine: CapCut (+ HyperFrames for complex motion). **ready (asset-dependent)**

## Add-as-we-go
_New components get appended here with look + animation(+id) + paired sound + when-to-use + status._
