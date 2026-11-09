# LAYOUT STANDARDS — the ONE contract every reel format ships to (LOCKED 2026-08-03)

> Every type-producing path — **Yap, Voiceover, and Animation** — MUST follow these. They are
> verified before every release, not just documented. If you add or change a type engine, it conforms
> to this or the release check fails.

## 1. Position comes from the pack's real `y` — NEVER hand-picked
Each element's vertical place = its `y` in `style-packs.json`, mapped to the 1080×1920 canvas:

```
center_px = 960 − (y × 960)     # CapCut normalized, + = up ; element is CENTER-anchored at center_px
```

- **hook** (headline `y≈0.56–0.59`) → ~394–422px = **above the head**
- **caption / snap** (`y≈−0.17 to −0.25`) → ~1120–1200px = **chest, under the chin**
- **takeover** (`y=0`) → 960 = **center**
- **thought bubble** (`y≈0.63–0.69`) → ~300–360px = above the head

**No hardcoded `top:NN%` or pixel positions in any type engine.** (The old `top:70%/62%/50%` was the bug.)

## 2. Size = pack size × SIZE_SCALE(6.0), AUTO-FIT down to the safe band
Start at the pack size; shrink only to fit. A long hook shrinks so it **never fills the screen**; a long
takeover word-stack shrinks so it **never runs off screen**. Safe zone always: x 150–930, **y 270–1620** (bottom = the creator's explicit 300px call; `product/safe_zones.py` is the
source; the top is the strictest platform band). The old top of 200 was too generous and a persistent label shipped underneath Instagram's Reels header because of it.
A platform-UI collision cannot be seen in the render or in QuickTime, only in the app after posting, so the
build now checks every placement against these bands and says so.

## 3. Captions — two modes; snap = NO ANIMATION
- **single** (snap read-along): instant cut-in, hold until the next word, **no fade/pop/rise**. Per-word
  fades FLICKER on fast speech.
- **build** (karaoke line-build): sentence reveals word-by-word IN PLACE (≤4 words/chunk, ≤2 lines), the
  current word highlights in the pack accent then returns to white. Build + takeover KEEP their motion —
  only the snap read-along is animation-free. Choose per reel via `caption_mode` (or `CAPTION_MODE` env).

## 3b. Hook sizing = MEASURED, not guessed; each fragment on ONE line
The hook fits so **each fragment is one line** (no mid-fragment wrap = clean breaks). Font-width varies wildly
by pack (Playfair wide, Opera Cake condensed, Soup Du Jour display), so the max no-wrap size is **measured in
the browser**, not estimated, and pinned per pack in `caption-plan.json` `hook_size_by_pack`. A long hook caps
the size in every font — **display packs (Playful) want a SHORT 2–4 word hook** (`hook_by_pack`), or they stay
small. The hook is TOP-anchored in the above-head band (top ~280px, grows down within ~330px).

## 4. Per-reel framing nudges (optional), in `caption-plan.json`
`hook_lift_px` / `caption_lift_px` (px up) shift the hook/captions for a creator's specific framing without
changing the pack. Default 0.

## 5. Accent = the pack's own `accent_color`, swappable per user
Never impose one color. Each pack ships a default (Editorial pink `#ffadbf`, Butter marigold `#fdc341`,
Playful mustard `#F5C518`); the creator can override.

## 6. Verify before the expensive render
Regenerate with `PREVIEW_BG=<a face frame>.jpg`, open the composition, seek the timeline, screenshot
hook/caption/takeover against the face. Cheap; catches placement before a full render.

## Conformance by path (keep this table honest)
- **`build-reel-type.py`** (Route A baked MP4) — conforms. VALIDATED on an example reel (Butter, Editorial,
  Playful), 2026-08-03.
- **`build-hf-captions.py`** (Route B / 🥩 medium, CapCut overlays) — positions now from pack `y` (§1);
  snap already no-anim (§3). **The engine ALWAYS auto-injects the type as named layers (`build-overlay.py`) —
  NEVER hand the user a manual drag.** The injector needs a CapCut-migrated draft + CapCut quit, so the flow
  is: build base → user opens it once (migrates) → **PROMPT THE USER TO QUIT CAPCUT** → inject named layers →
  user reopens. Prompting to close CapCut is an expected step, not a failure.
- **`cleanyap.py` / `superyap.py`** (Route C CapCut text) — position hook/thought/takeover via
  `packbuild.role` pack `y` (§1). Line captions = native CapCut Auto Captions (creator nudges under the
  chin in-app). Conforms for what the engine controls.
- **Voiceover** — ⚠ NOT BUILT YET (in design). When built it MUST follow this doc; the ship gate
  will hold it to §1/§3 the moment a VO type engine exists.
