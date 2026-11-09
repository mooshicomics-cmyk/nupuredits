# VO-REEL.md — the Voiceover format spec + flow (Family B)

> The canonical spec for the **Voiceover** format — no talking-head monologue, her **voiceover is the spine** and
> her **b-roll is dressed onto it**, cut sentimental / cinematic / emotional. This is one of the three formats
> alongside Yap + Animation. It has its OWN cut engine (audio-first), so it branches from `FLOW.md`
> at step 1. Locked with the creator via the `vo-sim` dry run (2026-08-04). Pairs with
> capcut ripple needs one pass build, reel build flow routes, the `reference-reel` skill.

## What it is (and the naming fix)
A Yap is *one talking-head take → cut down.* A Voiceover **inverts** that: a voiceover track is the spine,
and b-roll clips are arranged/trimmed **to the VO's cadence.** Two inputs, not one.

> **Not "faceless."** Call it **voiceover-led / no-talking-head.** Her b-roll often includes her (holding
> the baby, cooking, at the laptop) — there just isn't a monologue to camera. So `cover-frame.py` CAN find
> a face here; don't tell the creator covers won't work.

## Steps 1–3 differ from the Yaps; 4–7 rejoin

### 0 · Intake — the VO **and ASK where the footage is**
(a) the **VO audio** → `projects/<job>/audio/vo.*` (a clean recording, or a clip we strip the audio from).
(b) **ASK where her footage lives — always. Two options (she picks):**
  - **This reel's footage** — a folder she points at (or `projects/<job>/broll/`) with clips for THIS reel.
  - **Her general b-roll library** — a standing folder she reuses across reels (a "b-roll assets folder"
    she configures once; e.g. `~/Movies/b-roll` with a `clip-catalog.md`). Reused every reel until she changes it.
  Whichever she picks becomes `broll-select.py --lib <that folder>`. **Never assume a location — ask.**
- **She does NOT pre-curate.** She dumps what she already has (long, messy, more than she needs) and **the
  engine picks the best of it** (step 2.5). "Use the footage you already have."
- **Recommend 5–8+ usable clips** so selection has range, but there's no hard requirement.
- **Footage-vs-VO check:** warn if total usable b-roll < VO length × 1.2 (need trim + selection headroom).

### 1 · Transcribe the VO → the CUT GRID (the new step-1 engine)
WhisperX on the VO audio → word-level timings + the script. Derive **cut points** from:
- **phrase / sentence boundaries** (where a thought lands),
- **pauses** > ~350 ms (natural breath = natural cut),
- **emphasis** words (optional punch-in).
This replaces the Yaps' transcript-dedup — nothing is being cut for filler; we're finding the *musical
beats of the VO* to change shots on. Output: `projects/<job>/vo-grid.json` (cut times + phrase text).

### 2 · REGISTER + cadence — "punchy or emotional?" (the VO's teaching-vs-confessional)
**ASK the register up front, one line: "punchy or emotional?"** (the VO parallel to the Yap's "teaching
or confessional?"). It's a *smart feature* — infer a default from the delivery + words (fast, listy,
high-energy → punchy; slow, tender, reflective → emotional) and confirm. The register drives the PACING,
especially **the dead space between spoken lines** (the splice, step 3):
- **PUNCHY** → **trim the dead space.** Tighten inter-line gaps to a floor (~0.10–0.15s), faster shot
  changes, a sharper hook-burst. Tight and energetic.
- **EMOTIONAL** → **leave breathing room.** Preserve (or gently extend) the natural pauses between lines,
  longer holds, a gentler open. Let each line land.
Same knob touches the burst intensity (punchy = sharper, emotional = gentle) and hold length.

**Cadence — the hook-burst opener, ADAPTIVE to clip count:** rapid cuts across the first ~2s, then settle
to ~one shot-change per VO phrase. The burst **adapts to how many clips exist** (the `vo-sim` finding):
- **6+ clips** → true rapid burst, ~10 cuts, a different clip per stab (~0.2s each).
- **3–5 clips** → burst uses **punch-in reframes + different MOMENTS** of the clips (each stab gets a
  distinct scale/position so it doesn't read as the same frame flashing). Micro-cuts, not repetition.
- **< 3 clips** → **skip the burst**, open on one strong held shot (a burst would look broken).
- **Optional real-cadence source:** point at an inspo reel via the `reference-reel` skill →
  `reel-fingerprint.py` reads its exact cut cadence / hook-burst / BPM → match that rhythm instead of the
  default. (Format only, never the concept.)

### 2.5 · Auto-select the best b-roll (from what she already has) — ✅ BUILT: `product/broll-select.py`
`uv run product/broll-select.py --lib <her footage> --job <job>` reads her whole library and **picks the
best of what's there** — she never hand-curates. Extends `cover-frame.py` from stills to clips; writes
`projects/<job>/broll-select.json` + a labeled `broll-candidates.jpg` contact sheet. For each clip:
- **Score usable quality per moment** — slide a window across the clip and score each: **sharpness**
  (Laplacian variance — rejects blur), **exposure** (histogram not crushed-dark or blown), **stability**
  (frame-to-frame motion — rejects shaky/whip sections), **FLICKER** (per-frame mean-brightness variance —
  rejects clips that strobe from LED/fluorescent lighting or dappled tree light; these read as persistent
  flicker in the cut and are otherwise invisible in a still), **subject presence** (YuNet face when
  relevant). Pick the **best window** of each clip, not the whole thing.
  > **Flicker = HARD REJECT the window (per-window, NOT per-clip). Do NOT deflicker.** Measure it as
  > OSCILLATION (rapid back-and-forth) of whole-frame mean AND horizontal-band (row-std) brightness at
  > NATIVE fps — that's what separates real flicker from smooth motion / single-step cuts (which do not
  > oscillate). A clip can flicker in one window and be clean in another (flicker at 0 s and 7 s, clean at
  > 3 s) — so reject the WINDOW and pick a clean one from the same clip if it has one.
  > **ffmpeg `deflicker` is a trap:** it fixes only the whole-frame average, so a whole-frame check reads
  > "rescued" while the clip still LOCALLY band-flickers (often worse). It fooled both the tool and the
  > reviewer on a real clip (locked). Removed. If every window of a clip oscillates, drop the clip.
- **NEVER trust catalog/clip labels for a timestamp's content — SAMPLE the actual window.** Labels are
  per-clip, and some are wrong: a clip catalogued "holding toddler" can turn out to be a screen-grab, and
  another can be an outdoor path at 6 s, not the "holding toddler" its label implies. A long clip holds many
  scenes. The selector must extract frames at the chosen window and have Claude read them to confirm the
  shot actually matches the beat — the label and the timestamp are not enough.
- **Tag each clip's ENERGY** — motion magnitude (frame differencing): *calm/still* vs *active/busy*. This is
  what matches a clip to a beat automatically (hook-burst + "world moving" want active; tender holds want calm).
- **Rank + shortlist** — the top windows by quality, enough to cover every beat with variety, dropping the
  weak/dupe/too-dark clips. Writes `broll-select.json`: per clip a `windows[]` list of up to 3 clean,
  non-overlapping windows at two lengths (`kind: "burst"` short for the opener, `kind: "hold"` longer for
  beats that sit on a shot), each with its own quality/energy/flicker status. Top-level fields still carry
  the single best window for back-compat. **Author the shot plan from `windows[]`, not the top-level pick.**
- **Selection runs over PREPPED grabs, never raw clips (locked 2026-09-14).** Run the `broll-prep` skill
  first: it reads timecoded contact sheets and pulls the best 3-4 moments per clip as short named grabs.
  Selecting straight off long raw takes lands on the dull middle of a good clip, and a clip carrying an arc
  (a sink going from full to clean) has to be sampled ACROSS that arc or the story disappears from the
  picture. The order is prep → select → plan.
- **Semantic pairing stays human-in-the-loop, honestly.** Quality + energy are computed. WHICH shot suits
  WHICH line (baby vs laptop vs kitchen) is proposed by Claude **reading the shortlisted frames** (a contact
  sheet, like the `vo-sim`) and confirmed in the style plan. Don't claim the engine "understands" content —
  it finds the good, sharp, well-exposed moments and matches energy; the creator's eye confirms meaning.

Output feeds step 3 pre-filled. She can always add "use this specific clip here" or swap in the style plan.

### 3 · STYLE PLAN widget — rough-cut the VO **and** direct the footage (⏸ she approves) — the SAME widget + rough cut as the Yaps
**The VO is a raw recording — assume it has bad takes, stumbles, filler, repeats. It is NOT perfect.** So
the VO gets the **same rough-cut treatment as a Yap**: deliver the **exact same style-plan widget** (the
locked one — delete/trash + note + attach + length meter + kept·cut·notes counters, NO per-format variant),
showing the **VO transcript LINE BY LINE** (from `vo-grid.json`). In one gate she does both jobs:
- **DELETE the bad lines** (trash) — cut stumbles / filler / worse takes. Kept lines = the clean VO.
- **DIRECT the footage** — on any line, a NOTE ("use the baby clip here") or an attached clip. Her pick wins.
- **Any kept line she leaves blank, CLAUDE picks the footage** (best window from `broll-select.json`).
- With the markdown video link in the turn's final message, after the widget, same as the Yaps (text
  above a tool call is folded away in the app) — ALWAYS, never deferred. A VO has
  no picture at this gate, so `product/vo-listen.py` renders the spliced VO as a 9:16 follow-along MP4
  (line number + text + beat tag on screen) purely so she can LISTEN to the cut and call edits by line
  number. Splice with your recommended cuts first, render, then link it. She reviews by ear, not by
  reading a transcript and guessing.
She approves once → **SPLICE the kept VO** (drop the trashed lines' time ranges from the VO audio, concat,
re-derive word timings by arithmetic remap — same as the Yaps' `stitch-cut.sh`) = the clean VO spine + updated
cut grid. Then Claude writes `shot-plan.json` from her notes + auto-fills.
> Two jobs, one widget, one ⏸: **rough-cut the voice (delete bad takes) + direct the footage (notes).**
> No silent guessing, and no assuming the recording is clean.

### 4 · Build the cut — ONE pass (the assembler — TO BUILD)
The one missing piece. Contract (pinned by `vo-sim`):
> **In:** VO audio + `broll/` + the approved shot EDL. **Out:** a 9:16 **1080×1920** timeline — each clip
> trimmed to its `[in,out]` and placed at its timeline slot; the hook-burst micro-cut segment; the **VO as
> one continuous spine audio** (never chopped with the video); music bed under it; delivered per the steak
> route. Same one-pass rule as the Yaps (build everything before CapCut opens it). Scale each 1440×2560
> source to 1080×1920, face/subject-centered.

### 4b · Graphics ride ON the footage, never instead of it (locked 2026-09-14)

A screen demo, a card, a transcript panel or a persistent banner is a **TRANSPARENT layer composited over
b-roll that keeps playing underneath**. A graphic that replaces the picture for its whole length is the bug,
not the feature (creator, 2026-09-14: she pictured the animation happening ON the footage).

- Build every graphic as **ONE composition the length of the reel**, a clip per beat at its real
  `data-start`, transparent background. One render, one gate, one layer.
- Panels get a **scrim derived from the pack's own dark** (e.g. `--ink` at 88%) so her footage still reads
  through. Never an invented hex — the palette rule in `reel-layout-rules` applies to the scrim too.
- Stack it: `python3 product/reel_render.py composite --base <job>.vo.mp4 --layers graphics.mov -o <ov>.mp4`.
- 🔴 **Prove it never lands on the captions BEFORE compositing:**
  `python3 product/caption_guard.py <layer.mov> --band-top <t> --band-bottom <b>`. `hyperframes check`
  validates a composition's own canvas; it cannot see a caption track drawn later by a different tool, and
  caption line COUNT varies through a reel, so spot-checking frames misses the collision every time.
- The shot plan still needs a real footage hold for every phrase, graphic beats included.

### 5 · Text on screen — SAME kinetic engine + SAME 3 style packs, restrained (NOT a new build)
Text is `build-hf-captions.py` (the kinetic-caption engine — creator-facing name: **animated captions**),
fed by the **VO's own WhisperX word timings** from step 1, the exact input it already consumes
(`edit-timeline.json` + `caption-plan.json`). **For VO reels the caption set is exactly TWO modes — the
alternates — nothing else (vo-sim 2026-08-04):**
- **`build` (karaoke build) = the default** — the sentence builds **word-by-word IN PLACE**, positions
  stable (no reflow), accent highlight riding the current word. It "naturally fits" and reads calm, not
  fussy. This carries most of the reel.
- **`takeover` (full-screen) = the emphasis alternate** — every word its own line, vertical stack, hero
  word biggest, for the 1–2 peak moments. Alternate between build and takeover; that's the whole toolkit.
- **NO hook card on a VO reel** (unlike the Yaps). The opening line is just the first karaoke build.
- **NO `single`-snap** on VO reels. Build + takeover only.
- **Or NONE** — a pure-cinematic VO reel with just VO + music is a legitimate choice. Ask.
- **NEVER whole-block fade/pop captions** — reads as distracting flicker (vo-sim). The build IS the motion.

**The look comes from the creator's chosen STYLE PACK, not fixed fonts — same switch as the Yaps.** Pass
`STYLE_PACK=Editorial|Playful|Butter` and the engine rebuilds fonts + size + case + line-height +
drop-shadow from `style-packs.json`, mapping pack roles to the modes: **snap←`caption` · build←`accent_caption`
· takeover/hero←`takeover`**. Each pack gives the reel its own personality (proven end-to-end,
2026-08-04): **Editorial** = elegant serif/script (Playfair/Prosecco) · **Playful** = bold Soup du Jour
takeover + Noto Sans Adlam body · **Butter** = Inter Black UPPERCASE takeover + Inter Medium body. Layout +
karaoke behavior stay locked; only fonts/case/size change. (Font-licensing caveat: some pack display fonts are CapCut-native only; `capcut_userfonts` resolves
them from the creator's machine, we ship only OFL. See `FONT-SOURCES.md`.)

**ACCENT COLOR = the creator's own choice, OR none — NEVER an imposed default (2026-08-04).** The karaoke
highlight + takeover hero use the creator's brand hex, or **no accent at all** (all-white captions — the
word-build carries the motion, the takeover uses size alone). Do not hardcode a color. A pack's `accent_color`
(Editorial light pink `#ffadbf`, Butter marigold `#fdc341`, Playful yellow `#F5C518`, from `style-packs.json`)
is only a *suggested* default the creator overrides — and a pack default can read "neon" over some footage, so
always ask/confirm. Whatever color one creator picks stays hers; it never becomes the ship default.

**The one VO-specific text rule (the real difference from a Yap):** a Yap's text sits over a stable
talking-head; VO text sits over **moving, varied-brightness b-roll**, so it needs a **legibility treatment**
(soft drop-shadow / subtle scrim, prefer the calmer region of the frame). Inherited verbatim from the pack
system: lowercase except "God", no sentence punctuation on snap/takeover, **name every layer**, the **IG safe
zone** (x 150–930, y 270–1620). No face to avoid → more vertical freedom, but stay in the safe box.
Register follows the reel: **confessional/sentimental → sparse**; teaching-style VO (rare) can carry more.
Always ASK "animated captions or none, and which pack?" — never default to busy, never assume her pack.
- **Text MUST auto-fit (wrap + shrink to length within the safe zone) — never a fixed width.** The real
  engine does this by construction; the `vo-sim` throwaway skipped it and text ran off frame (caught
  2026-08-04). This is why production text goes through
  `build-hf-captions`, not any hand-rolled overlay.
- **Sentimental VO = SMALL + ELEGANT + LIGHT, never large + heavy.** A big heavy weight (e.g. Poppins-Black)
  fights the mood; use the pack's elegant/serif role, small (~50px on 1080). (vo-sim 2026-08-04.)
- **NO caption fades on VO reels** — the karaoke word-build IS the motion; a whole-block fade reads fussy
  (the earlier fade call was reversed 2026-08-04). Words appear at their real timestamps, stable positions.
- **Caption typography rules (vo-sim 2026-08-04): (1) NO orphans** — never leave a lonely one-word last
  line; a balanced wrap pulls a word down from the line above (the engine's `wrap_text` already does this —
  apply it to VO captions too). **(2) Readable, not tiny** — elegant-small, but not so small it's hard to
  read (~56–64px build on 1080). **(3) Shadow = soft AND dark** — a strongly-blurred, fairly opaque dark
  glow behind the type; soft edges (no hard offset) but dark enough to stay legible over bright/busy b-roll.
- **Hook-burst intensity scales to MOOD, not just clip count.** A sentimental reel wants a gentle opener
  (few slow stabs), not a rapid strobe — 8 cuts in 2s + exposure mismatch read as flicker. Sentimental =
  4-ish slower stabs (or open on a held shot). Reserve the fast burst for high-energy reels. (vo-sim.)
- **Cut-to-cut brightness jumps at a hard cut** can read as a flash. Handle it by SELECTION (pick windows
  of similar exposure for adjacent beats) and, if needed, short cross-dissolves on tender holds — **not**
  a grade (the grade was removed). Native clip color stays.

### 6 · Music bed
`vo-build.py --music <track>` lays a **cinematic / sentimental bed** under the VO (auto-leveled by
`audio_levels.py`, its mean 15 dB under the VO's; the VO stays on top). This format leans on music more than the Yaps.

### 7 · Cover + export
`cover-frame.py` on the finished reel (it CAN find a face here). Then finalize per the steak route.
- **Doneness:** VO reels default to **Route A / well-done (baked MP4)** , music + b-roll + VO, little
  editable text to preserve.
- **Route B/C = the SLIP finish (`product/capcut-slip-reel.py`, shipped v1.0.54).** Choose it when she wants
  editable captions on top, or when she wants to pick a different moment inside any shot by hand. It hands
  the whole reel to CapCut with **every beat as a compound clip holding its WHOLE source**, only the chosen
  window on the timeline. She double-clicks a beat, drags the clip inside, and a different moment plays
  while the beat keeps its position and length. That is a slip, and CapCut ships no slip tool of its own.
  Two things make it safe to slip freely: the **voiceover is one unbroken audio track**, so nothing she does
  to the picture can pull it out of sync, and **graphics are timed to the VOICE, not the picture**, so
  slipping a shot never drags a caption with it. Offer this route whenever the b-roll choice is the part she
  is least sure about, because it is the one finish that leaves that decision open after the build.
  Run it with the VectCut venv python and CapCut QUIT. It refuses to overwrite an existing draft name.

## Other requirements (surfaced 2026-08-04 — the flow needs more than cut + captions)
- **~~Color grade to unify footage~~ — REMOVED (2026-08-04: "i dont like the color grade feature").**
  A grey-world unify-grade was built + tested in the throwaway; she rejected it. **Keep each clip's NATIVE
  color — no grade by default.** Don't re-add it. (If cut-to-cut brightness ever reads as a flash, handle it
  with selection/deflicker, not a grade.)
- **Reframe / orientation.** Existing b-roll comes in mixed orientations + resolutions → reframe each to
  **9:16 1080×1920, subject-centered**. `head-framing.py` already does face-centered 9:16; center-crop the rest.
- **Motion on holds (Ken Burns) — ✅ BUILT + DEFAULT ON (2026-09-03).** A held shot reads dead if static.
  `vo-build.py` now rides a gentle Ken-Burns move (alternating push-in/out) on every hold by default;
  `--motion still` locks them all, and a shot can pin its own via shot-plan `"kb": "in"|"out"|"still"`.
  (VO defaults to motion. Offer the still opt-out per reel — see `CAPABILITY-OFFERS.md`.)
- **Transitions.** Yaps hard-cut. VO wants a small vocabulary: hard cuts in the hook-burst, gentle
  dissolves on tender holds. A decision + small build (baked or CapCut transition).
- **Speed / fill.** When a beat is longer than a clip's best window: slow-mo to fill (cinematic) vs pick a
  longer clip. Decision.
- **VO audio cleanup + music ducking.** VO gets the `rough-cut` static normalize/limiter chain; the music
  bed **ducks under the VO** (`background-music` ducking, opt-in). Mostly reuse.
- **Story arc.** Shot order should build emotionally, not random — Claude proposes an arc from the frames,
  she confirms in the style plan. Human-in-loop.
- **Optional: cut on the MUSIC beat.** Cinematic reels often cut on BPM, not just VO phrases —
  `reel-fingerprint.py` gives BPM. Optional enhancement.
- No sales CTA / no summary card (Edit-engine boundary + confessional contract) — end on the payoff line.

## What still needs building (honest gap list)
1. ~~**VO cut-grid analyzer** (step 1)~~ — ✅ **BUILT** `product/vo-cutgrid.py` (faster-whisper → words +
   phrases on pause/sentence/clause boundaries → `vo-grid.json`; feeds cut grid AND karaoke captions;
   tested on a real voiceover).
2. ~~**B-roll auto-selector** (step 2.5)~~ — ✅ **BUILT** `product/broll-select.py` (quality/energy +
   oscillation-based native-fps flicker HARD-REJECT, no deflicker; JSON + contact sheet; tested 2026-08-04).
3. **Shot→beat planner** (step 3) — maps the selected windows to the cut grid, fills the style-plan segments.
   Light (consumes 1 + 2). The pairing itself stays a human/Claude call (content meaning).
4b. ~~**VO ROUGH-CUT + splice**~~ — ✅ **BUILT** `product/vo-splice.py`. Drops the deleted lines from the VO
   audio, concats, re-derives word timings (→ `audio/vo.clean.wav` + `vo-grid.clean.json`, which `vo-build`
   prefers). **`--pace punchy` trims inter-line gaps to a ~0.14s floor; `--pace emotional` keeps the
   pauses.** Proven on a real 8 s voiceover: cutting a line re-times the transcript; punchy 8.3→7.8s vs
   emotional 8.1s.
   (Register = "punchy or emotional?", the VO's teaching-vs-confessional.)
4. ~~**The reel builder / assembler** (step 4)~~ — ✅ **BUILT** `product/vo-build.py` (reframe + hook-burst +
   phrase holds + VO spine + music + karaoke-build/takeover captions per STYLE_PACK + accent, one pass; no
   grade, no deflicker). Triggered by the **`voiceover-reel` skill** ("make my voiceover reel"). Built + ran
   end-to-end on a real voiceover reel. Ken-Burns push-in on holds is now DEFAULT ON
   (2026-09-03, `--motion`). Optional later: gentle transitions.
   The editable-CapCut finish now EXISTS: `product/capcut-slip-reel.py` (v1.0.54), captions via
   `build-hf-captions`, every beat a slippable compound. See Doneness above.
   **The shot→beat pairing (step 3) stays a human/Claude call** (read `broll-candidates.jpg`, author
   `shot-plan.json`) — content meaning isn't auto-derivable.
Text on screen is NOT a build — it's `build-hf-captions.py` fed by the VO word timings (see step 5).
Everything else (transcribe, reference-reel cadence, style-plan widget, background-music, cover-frame,
export, steak routes) already ships.

## Locked decisions (from `vo-sim`, 2026-08-04)
- **Creator-facing name = "Voiceover"** (internal code/filenames keep "VO Reel"/"faceless" — label rule
  skill naming). The kinetic-type look is creator-facing **"animated captions."**
- **The VISUAL is b-roll** (confirmed) — her voice over her own footage, cinematic. Animated text is
  *optional captions on top*, not the video. (Not an animated-text-driven format.)
- **Animated text ships in the 3 STYLE PACKS, not her fonts.** `STYLE_PACK=Editorial|Playful|Butter`
  drives fonts/size/case/shadow (same switch as the Yaps); a creator's personal fonts and colors live in a
  pack of her own (`_local/style-packs.json`), never in the shipped three. ASK which pack; never assume one.
- **Use her EXISTING b-roll — the engine picks the best of what she has.** No hand-curating, no shooting to
  a shot list. Auto-select scores quality per moment + energy; Claude proposes semantic pairing from the
  frames; she confirms in the style plan. (The headline promise of the format.)
- Adaptive hook-burst by clip count (6+ / 3–5 / <3). · Recommend 5–8+ clips, not required.
- "Voiceover-led," not "faceless." Covers work when a face is in the b-roll.
- Cut grid = VO phrase/pause boundaries (audio-first), not transcript-dedup.
- Footage-vs-VO warning at < VO × 1.2. · Default doneness = Route A well-done.
