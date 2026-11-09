# CAPABILITIES — the full scope of what this editor can do for the creator's reels

> Read this so I never under-sell or forget a capability. If the creator describes something and I think "can I
> do that?" — the answer is almost always YES; check here first. Everything is EDITABLE-first in CapCut, never
> replaces a draft she may have opened (CLAUDE.md rule 7), and follows the PROCESS ORDER below.

## ⛔ BUILD ORDER — ALL reel types (CLAUDE.md rules 1 and 7, the phases in CLAUDE.md)
1. **Inbox → job** — the clip is copied into its job folder; the original is never touched.
2. **Rough cut** (transcribe → de-dup takes → kill dead air → splice) → ⏸ **style plan** (her trims, her approval).
3. **Creative plan** — route + captions (**ASK: native CapCut captions OR kinetic-type build**) + SFX + graphics +
   b-roll + copy, as ONE plan, with the register and doneness as clean pick-ones → ⏸ **one approval**.
4. **ONE build pass** — cut, text, SFX, graphics and animations built TOGETHER, before CapCut ever opens the draft.
5. **Hand off with instructions** → **the creator finishes** — polish, Auto Captions, grade if she wants one,
   export. (Your step.)
Hard rules: plan → approve → build once, never guess-build-rebuild. SFX and animation are NOT a separate later
phase: they go in the one build. Never replace a draft she may have opened: a later change is LAYERED on top
(CapCut quit first) or built into a NEW version (`<base> 1.1 → 1.2`). Approve gates ⏸.

## B-Roll Reels (bring-your-own filmed footage — the `broll-reels` skill)
- A batch format: the creator drops a folder of their OWN filmed b-roll (~5s vertical clips with negative
  space for text) in `inbox/` and says "make b-roll reels." **No filming and NO AI generation here** — the
  footage is theirs (the Content Crafting Engine's `ai-broll` avatar side is the one that generates footage).
- The flow: organize + label the clips → write niche-fit hooks → bake the hook (headline + optional accent
  turn) into each clip in the CHOSEN style pack's fonts + color → output a numbered posting queue with
  paste-ready captions. Posting stays manual.
- Uses the SAME style packs as the rest of the engine (Editorial / Playful / Butter, resolved from
  `style-packs.json`); no fonts ship, licensed pack fonts resolve from the creator's CapCut (CapCut Pro).

## Reel analysis (comparative / style-matching)
- **Pull any inspo IG Reel / TikTok by link with the Apify tool** → download
  the actual video + audio → ffmpeg contact sheet + listen → analyze the caption/animation/pacing style.
- 🚫 **NEVER use the in-app browser to "watch" Instagram** — it login-walls and shows nothing. Use the
  Apify downloader. (I keep forgetting this — STOP.)

## Cover / thumbnail — best frame BY EXPRESSION (`cover-thumbnail` skill)
- **`uv run workflows/cover-frame.py projects/<job>/outputs/<job>.final.mp4`** samples the reel densely,
  detects the face (YuNet, bundled), and **scores every frame** — face confidence, size, sharpness (kills
  motion-blur/mid-word), facing (eyes level + nose centered), eyes-open (blink filter, heuristic),
  expression (mouth-corner spread) — then writes the top CLEAN stills (no title) to
  `thumbnails/candidates/` + `cover-scores.json`, spread across the reel (`--min-gap`). Kills the scrubbing.
- **PHASED (like the reel):** frame options ⏸ she picks → title options ⏸ she picks → build title onto the
  frame (headline font + accent, anchored TOP/center NEVER bottom, one accent word, scrim for legibility).
- Reel COVER only (poster frame in the grid). Short-form kit = **no YouTube thumbnails, no face-ref lib.**
  Faceless VO/heavy-b-roll → picker writes nothing on purpose; pick by eye. Eyes-open/expression are
  heuristics — clean shortlist, human makes the final call. See `product/FLOW.md` → Cover / thumbnail.

## TEXT & CAPTIONS (full range — NOT just native Auto Captions)
- **SPLIT overlays by STYLE (the creator's call 2026-07-30):** render ONE transparent overlay per style (e.g.
  cap-single / cap-build / cap-takeover, and each graphic type) → inject each on its OWN flag=2 PIP track
  so the creator can reposition/retime/toggle each style INDEPENDENTLY in CapCut. Generator takes `HF_MODE=single|
  build|takeover` to emit one style; inject with `build-overlay.py <mov> <track> <render_index>`.
- **IG REELS SAFE ZONE for kinetic type (the creator — text ran into the Reels UI):** keep ALL overlay
  text inside x **150..930** (clear of the right action rail ~960+) and y **270..1620**. Text blocks are
  centered with ≥150px side margins; chunk builds to ≤2 lines WITHIN that width. Baked into
  `build-hf-captions.py` CSS. Same top-270/bottom-300 rule as `workflows/short-form.md`.
- **GOTCHA — CapCut BLANKS track names on migration:** removing injected tracks by name misses them after
  CapCut has opened/migrated the draft (name becomes ""). Remove leftover injected clips by blank-name +
  content, not just the name I gave them. (Caused leftover captions to persist.)
- **KINETIC-TYPE OVERLAY pipeline (CONFIRMED WORKING — "STELLAR" 2026-07-30):** for sleek custom kinetic
  captions that native CapCut can't do (sentence build-in-place, karaoke highlight, per-moment fonts),
  render a HyperFrames composition → **transcode to qtrle (QuickTime Animation, argb) .mov — NOT ProRes
  4444 (CapCut can't read its alpha; qtrle it CAN on Mac)** → INJECT onto the migrated draft as a flag=2
  PIP overlay track (`product/build-hf-captions.py` + `build-overlay.py`; clone footage video
  material+helpers+segment, repoint path, full-frame, muted). Import via the engine, not a manual drag.
- **Custom KINETIC captions** (injected designed text, my default for her): per-moment control of FONT,
  POSITION, size, color, and animation. I can do: **single big emphasis words** (the pack's display font, centered/large,
  held alone); **sentences appearing WORD-BY-WORD** (each word popped on at its exact WhisperX timestamp) in
  the pack's accent font for intimate/reflective beats; **clean read-along** (the pack's caption font) low for
  straight-talk; captions that **move position** by moment (not locked at the bottom); keyword accents in the
  accent color. Font changes with the FEELING (font-by-job, every font from the active pack: the pack's hook font
  = punch/conviction, the pack's accent font = intimate, the pack's caption font = read-along).
  I have her word-level timings from the trimmed-timeline reconstruction, so word-by-word is exact.
  **Locked TEXT RULES (STYLES.md → Kinetic Type Overlays):** keep apostrophes, strip only sentence
  punctuation on snap+takeover (build keeps all); lowercase everything except God/Bible/Lord; NO overlap;
  captions run everywhere; takeover = every word its own line (vertical stack), hero line = biggest CAPS; the
  accent color on keyword/highlight/payoff; dead-space >3s trimmed; NAME every layer (track + clip); fix text in
  edit-timeline.json not by ear. Engine `build-hf-captions.py` (per-reel config block + universal rules).
- **Native CapCut Auto Captions** — the uniform karaoke track (Bold Text-Popup + keyword highlight), when
  she wants one consistent caption style the whole reel. Use ONLY when uniform is the goal.
- **Hook card** (the pack's hook font, top), **thought bubbles** (the pack's thought font, above head), all from the component menu.

## GRAPHICS / COMPONENTS (see components/README.md — grows)
Hook card · thought bubble · **typing/message bubble** (iMessage-style, dots→types on) · **chat thread** ·
**crossed-out words / kinetic strike** (e.g. money/cash value → a soul) · callout/arrow · lower third ·
stat card · notes/journal card · search-bar/UI reveal · photo thought bubble. New ones get added on request.

## GIF / STICKER DROP-INS (reaction gifs, `product/gif_dropins.py`)
Drop a folder of reaction GIFs into `inbox/` ("layer these in where they make sense") and each is placed on
its beat as its OWN native PIP clip — the gif converted to a see-through clip that loops for as long as it is
on screen, scaled down, positioned (upper by default), MUTED, on its own overlay track. A GIF any CapCut build
adds as a picture is turned into the same looping clip at finalize (CapCut holds a picture's first frame). Additive (footage / SFX / text untouched), built into a NEW
version so the original is preserved. **A gif is DROPPED ON THE TIMELINE — never composited onto a
full-frame black/transparent canvas** (that lays an opaque rectangle over the footage). Size/position are a
starting point the creator drags in CapCut. Entrance/exit motion uses CapCut's built-in SLIDE animation
PRESETS (alternating left/right), NEVER position keyframes (CapCut glitches on keyframed gifs).

## MOTION / FOOTAGE
Jump-cut zoom punches · slow keyframed zoom-in opener · punch-ins · full-screen word takeover (the pack's takeover font) ·
**full-screen ILLUSTRATIVE takeover with a storyline** (HyperFrames) · b-roll cutaways / margins burst ·
**animate HER assets** (doodles / product covers / screenshots from ~/brand-assets) on screen as
individual editable layers (slide/zoom/pop, never baked).

## ENGINE / TECH
- **HyperFrames 0.9.6** — 48 animation rules, 22 blueprints, **AI image gen + AI VIDEO gen** (heygen/ltx).
  Renders rich motion graphics as .mov overlays.
- **VectCutAPI** (:9001) — builds/edits CapCut drafts (text, SFX, animations, custom fonts, jump cuts).
- **Injection into migrated/hand-edited CapCut drafts** — clone valid material/segment/animation/audio
  structures (the safe way; VectCutAPI can't touch a migrated draft). Use the COMPLETE cache path for
  animations (`…/effect/<id>/<hash>`).
- **Her real animations by resource_id** (`animations.json`) + **sounds from the engine's library, her favorites
  first** (`python3 product/favorites.py show`, `python3 product/capcut_sfx.py --list`). Sound-matches-motion,
  trimmed to the animation. Her real Cheeky Bounce, Chalky Scribble, etc.
- **Reconstruct the on-timeline transcript** from her trimmed clips' source windows + raw words.json, so
  captions/graphics anchor to YOUR edit, not the old cut.

## SOUND
From the engine's sound library, her own favorites first (`python3 product/favorites.py show`: her shelf and her
rules; the mood rules still outrank it, so a somber reel stays near-silent). Matched to motion; bubbles fade
silent; woosh is a rare accent; VARY the clicks (rotate them, never the same twice). **Built in the SAME pass as
the cut + text, before the CapCut handoff** (CLAUDE.md rules 1 and 7). A sound added after she has edited is
LAYERED on, with CapCut quit, and ripples like any other track; her draft is never replaced to add it.
- **Background MUSIC = generate it FREE & LOCAL (no account, no cloud).** MusicGen runs on the
  WhisperX venv (found automatically); generator `product/gen-music.py <job> [seconds]` writes option
  clips to `projects/<job>/audio/` to try a vibe (the model's license is non-commercial, so the posted reel
  uses a track she has rights to, or music she adds inside CapCut) (mood prompts baked in). Audition short seed clips → pick → render full
  length → lay the flat −18 dB bed with the `background-music` skill. Confessional = minimal/ambient, NO
  hopeful/uplifting bed. (HeyGen library retrieval is the alternative but needs a sign-in — local gen is the
  default so nothing to pay/sign up for.)
- **SFX are ALWAYS native editable CapCut audio — NEVER baked into a caption overlay.** The kinetic-type
  overlays are silent (muted, volume 0) VIDEO; SFX are AUDIO on their own default-named tracks that ripple
  with the magnet. Splitting captions into layers does NOT change SFX injection — inject them exactly as
  before (the creator can mute/drag/trim/swap each). Baking SFX into the .mov would lock them = violates
  everything-editable. Bonus: caption reveals AND SFX read the SAME word timings (`edit-timeline.json`), so
  sound-matches-motion is frame-accurate by construction. Caveat: baked WORDS can't be nudged in CapCut, so
  if the creator re-times a word I re-render + re-place SFX; the SFX themselves you can always drag freely.

## TIMELINE MARKERS (native `time_marks`, confirmed 2026-07-30)
CapCut supports timeline markers via the top-level **`time_marks`** field in draft_info.json (it's `None`
in all of the creator's drafts — you've never used one). VectCutAPI has NO marker helper, so inject markers by
writing `time_marks` directly (same JSON-injection path as overlays, CapCut quit). **Exact per-marker
object shape is not yet confirmed** — no populated example exists in her drafts or the VectCutAPI templates
(only empty `[]`). To lock the schema: have the creator drop ONE marker in CapCut, save, then diff. Uses: cut
points, hook-end, SFX cue points, section labels for her while editing.

## HOW I BUILD
Plan → (her go) → build once → **never replace a draft she may have opened** (layer on top with CapCut quit, or
build a new version) → preserve her CapCut edits → she reviews.
Every reel: use the vault (STYLES.md, animations.json, sfx.json, components/) so it's consistent + excellent.
