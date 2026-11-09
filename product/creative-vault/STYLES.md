# Creative Direction Vault — STYLES (the creator's shot list)

> The running list of what the creator likes, each resolved to its **ID tag / hash / setting** so builds apply it
> exactly (no guessing, no stand-ins). the creator says what she likes → I note it here and write the ID.
> Machine data lives in the JSONs next to this file (`animations.json`, and later `sfx.json` and
> `palettes.json`). **Read this vault before building.** The rules of HOW I work are in `CLAUDE.md`.

Legend: 🎬 animation · 🔊 sfx · 🔤 font · 🎨 color · 📐 setting · 📖 rule

---

## Yap — trimmed-back treatment (confessional) — locked

- 📐 **Cut:** locked rough cut + jump cuts (scale push-ins 1.06–1.08 on accent beats). Confessional stays calm.
- 🎬 **Opener = slow keyframed zoom-in** on the first footage clip (studied from the creator's own edit
  2026-07-29): **scale 1.06 → 1.22 over ~1.4s** at the clip start, then holds 1.22. Subtle push-in that
  pulls the viewer in on the first line. Apply as a clean-yap style default, **especially confessional**.
  (`KFTypeScaleX` keyframes on the opening segment; base scale ends 1.22.)
- 🔤 **Hook:** the pack's hook font, white, top (y≈0.62), lowercase, no em dash. **size 17** (the creator set). Holds through the opening — don't drop early.
- 🔤 **Thoughts:** the pack's thought font, white, above your head (y≈0.66). **size 15**, **line_spacing −0.13** (the creator set in-app).
- 🎬 **Text animations — ROTATE for variety** (never the same on every element). Her set + IDs (`animations.json`):
  - in: **Chalky Scribble** `7540595903808277777` · **Slide Left** `6798332871267324423` · **Slide Right** `6798333076469453320` · **Cheeky Bounce** `7527870705392717057` · Random Typewriter (hook) `7145435525799744002`
  - out: **Slide Left** `6763873602476446221` · **Slide Right** `6798333350487527950` · **Erase** `7642247005737061652` · **Text Fade** `7646372829113371912`
  - ❓ "click in" — confirm which (closest: Cursor Drag-In `7628816706219052308`).
- 🔊 **SFX — from the engine's own sound library, her favorites first**, non-cartoon: `python3 product/favorites.py show`
  for her shelf and her rules, `python3 product/capcut_sfx.py --list` for the whole library (ask the engine; never
  conclude a sound is missing from a glob). Keyboard typing on the typewriter hook · a soft click on a bubble
  entrance (vary it, never the same click twice) · a soft woosh as a rare outro. The mood rules outrank her shelf:
  a somber reel stays near-silent.
- 📐 **Captions:** native Auto Captions, Bold Text-Popup + keyword highlight (bold-white + yellow keyword). the creator runs in-app.
- 📖 **Register:** confessional = almost no graphics, no closing card; teaching = a little more.
- 📖 **Layers / ripple:** overlays + SFX must follow main-track ripple (magnet: `maintrack_adsorb=true` + `free_render_index_mode_on=false`; audio tracks default-named). No compounding/grouping.

## Sound ↔ animation pairing (LOCKED — the craft rules)

- 📖 **Alternate animations** across elements — variety, never the same anim on every bubble.
- 📖 **The sound voices the motion — pair them:**
  - Chalk bubble / **Chalky Scribble** animation → **write-on / pencil writing** sound.
  - **Typewriter / Random Typewriter** animation → **typewriter / keyboard typing** sound.
- 📖 **Write-on & type-on animations run 1–1.5s**, and the **sound STARTS and STOPS with the animation
  movement** — trim the SFX to the EXACT animation length (sound ends exactly when the motion ends).

- 📖 **Trimmed-back bubble default (locked):** bubble ENTRANCE → **Mouse Click** · bubble EXIT →
  **fade out (Text Fade) with NO sound**. Vary the entrance ANIMATION (Cheeky Bounce / Slide L/R) but keep
  the entrance sound the mouse click. Hook keeps her Typewriter + Keyboard Typing.
- 🛑 **DON'T overuse the woosh** (Fuwa/Woosh). A woosh on every exit reads spammy — the creator called this out.
  Wooshes are a rare accent, not a default. Most exits are silent fades.
- 📖 win → ka-ching/coin.
- ⚠️ **Patching an animation by resource_id: use the COMPLETE cache path** (`…/effect/<rid>/<hash>`), not
  just `…/effect/<rid>` — the trailing hash folder is required or CapCut can't resolve it and the element
  renders with NO animation. Clone the full animation object from a draft (`scripts` extract), don't hand-build the path.

## Kinetic Type Overlays — locked (proven on the example reel, "STELLAR" + "amazing" 2026-07-30)

Custom per-moment captions that native CapCut can't do (sentence build-in-place, karaoke highlight,
per-moment font/size/position). Rendered in HyperFrames → transcoded to **qtrle (argb) .mov** →
injected as **flag=2 PIP overlay tracks**. Generator `product/build-hf-captions.py`, injector
`product/build-overlay.py`, swap/remove `product/remove-overlays.py`.
**⛔ ALWAYS ASK first (every text-on-video moment): "kinetic type overlay OR native CapCut captions?"**

- 📖 **SPLIT each style onto its OWN overlay layer** so the creator can reposition/retime/toggle each independently
  in CapCut: `cap-single` · `cap-build` · `cap-takeover` · `intro-kinetic` (each its own flag=2 PIP track,
  ascending render_index). Generator takes `HF_MODE=single|build|takeover` to emit one style at a time.
- 📖 **NO SENTENCE PUNCTUATION** on single-word snaps + full-screen takeovers (the creator never punctuates) — but
  **KEEP APOSTROPHES** ("it's", "that's", "you're"). `strip_punct()` removes periods/commas/?!/quotes only.
  The pack's accent-font sentence-build keeps ALL punctuation.
- 📖 **NO OVERLAP (hard):** within a layer, clamp every clip's end to the next clip's start; NEVER let a
  min-duration floor push one word/sentence on top of the next. One clears as the next appears. (Old floor +
  last-word tail were stacking words — fixed with a no-overlap pass.)
- 📖 **SNAP CAPTIONS = NO ANIMATION (locked).** The read-along/snap word must **cut in instantly and
  hold until the next word** — no fade-in, no fade-out, no pop, no rise. Per-word fades FLICKER when she
  talks fast (words land too close together). Instant on at the word, instant off exactly when the next word
  turns on (no gap) = clean, flicker-free. (Build/karaoke + takeover keep their motion; only the snap
  read-along is animation-free.) Enforced in `build-reel-type.py` (Route A base template).
- 📐 **IG Reels safe zone (always):** all kinetic text inside x **150–930** (clear of the right action rail
  ~960+) and y **270–1620**. Text blocks centered with ≥130–160px side margins, builds chunked to ≤2 lines.
- 🔤 **Font by job (every font from the active style pack, never a personal default):** **the pack's caption font** =
  single-word snap read-along (low ~70%, TIGHT tracking; "bring in the character spacing" = TIGHTEN/pull
  characters together = NEGATIVE tracking, not wider) · **the pack's accent font** = intimate sentence-build
  word-by-word revealing IN PLACE with a **karaoke highlight in the accent color on the current word as she says
  it** (≤2 lines) · **the pack's display font** = full-screen takeover + the hook.
- 🎬 **Takeover layout (locked):** keep the WHOLE phrase on screen and stack **every word on its own
  line (vertical stack)**, vertically centered, held the whole time she says it (words lift in, then all
  stay). Highlight the key word in **the accent color** (e.g. "nothing" in "And nothing touches that Tuesday").
  NOT chunked to 2 lines — one word per line, however many words.
- 🎨 **The accent color** = keyword accents (snap), the karaoke highlight (build), the payoff word (intro), and
  the takeover key word. It is this reel's own accent if one was set, else her saved `default_accent`
  (`/studio accent`), else the pack's own `accent_color`: never a free hex, and never a personal color.
- 📖 **Captions run EVERYWHERE — never blank a section** (no "yield" gaps). the creator caught the money/cash value/
  a soul reframe (~37–42s) having NO captions because a designed card was "covering" it; she removes those
  cards, so the section went bare. Keep kinetic captions running through it (separate layer she can still
  toggle); if a designed card doubles up, offer to hide/remove the card, don't blank the captions.
- 📖 **Lowercase EVERYTHING except "God", "Bible" and "Lord"** (`case_fix()` keeps those three capitalized).
  Applies to all caption layers. Every other proper noun (Tuesday, say) goes lowercase too.
- 🎬 **HERO line = the single most prominent line** ("THIS IS THE LIFE. THIS IS IT."): biggest style, ALL
  CAPS, its own takeover. **Extract just the PHRASE, not the whole run-on sentence it sits in** (`HERO_KEYS`
  matched as a word-run anywhere in the stream; the rest of that sentence stays normal snaps). Her brand:
  lowercase for intimacy, CAPS for the one big emphasis.
- 📖 **Fix content in the TIMELINE, not by ear:** she'll correct caption text ("bless"→"blessed", add
  "and people") — edit `edit-timeline.json` word(s), it flows to every layer. On-screen text is HERS to set,
  even if it differs slightly from the raw transcript.
- 🪚 **Trim overlay DEAD SPACE (>3s):** inject ONE overlay segment PER active-text span (generator writes
  `<mode>-spans.json`, merging gaps ≤3s; injector `build-overlay.py <mov> <track> <ridx> <spans.json>`
  lays a segment per span, source==target time). Long empty stretches leave the track CLEAR so the creator can grab
  layers below. One .mov material, N segments.
- 📖 **Timeline height / rows:** in CapCut **position + scale are PER-CLIP, not per-track** — consolidating
  caption types onto fewer rows would NOT lose independent placement. the creator still prefers **one row per caption
  type** (snap / build / takeover / intro = 4 rows); dead-space trimming keeps those rows manageable. Offer
  consolidation (interval-pack to fewer rows) only if she asks again.
- 📖 **NAME every layer for editing** — human-readable on BOTH the track name AND the clip's `material_name`
  (CapCut can blank the track name on migration, so the clip label is what reliably shows). Kinetic layers:
  **Captions** (snap) · **the pack's accent font** (build) · **Takeover** · **Title** (kinetic hook
  intro). **SFX too:** label each SFX clip by its sound (**Keyboard Typing** / **Mouse Click** / **Decision
  Click** …). ⚠️ Audio tracks were kept DEFAULT-named for the magnet ripple — if naming a SFX *track* breaks
  ripple, keep the name on the CLIP only (verify live). Injector sets `material_name=<track label>`.
- 🎬 **Kinetic hook intro** (showcase, `projects/example-reel/hf-intro/`): the pack's hook font staggered **fragment build**
  (her signature stack) → **accent-color strike-wipe** cuts through the "cancel" word (word dims to ~42% white) →
  the payoff word lands with an **accent-color + scale punch**. Reusable pattern for any hook.
- 🛠️ **Pipeline:** HF `render --format mov --quality high` → `ffmpeg -c:v qtrle -pix_fmt argb` (NOT ProRes
  4444 — CapCut can't read its alpha; qtrle argb it CAN on Mac) → inject full-frame, muted, t=0.
- ⚠️ **CapCut BLANKS injected track names on migration** — when swapping, remove leftovers by blank-name +
  content, not just the name I gave them.
- 📖 **Verify the composition in the BROWSER before the expensive render:** open the HF `index.html`, drive
  the paused GSAP timeline (`window.__timelines["<id>"].time(t)`), screenshot the climax → confirm
  layout/fonts/colors. This is design-QA of my OWN composition (cheap, de-risks the render), NOT the banned
  CapCut-UI over-verification.
- 📖 **SFX stay NATIVE editable CapCut audio even with baked caption overlays** — the overlay is muted VIDEO;
  SFX are AUDIO on their own default-named (rippling) tracks, anchored to the SAME word timings the captions
  use → frame-accurate sound-matches-motion. NEVER bake SFX into the overlay. Baked WORDS can't be nudged in
  CapCut, so a word re-time = re-render + re-place SFX; the SFX themselves stay freely draggable.

## Yap — loaded treatment (teaching)
- Everything in the trimmed-back treatment + doodle stickers, takeover (the pack's takeover font), stat cards, b-roll, punch-ins. Engine: `superyap.py`.

## Behavioral rules
- 📖 **Never replace a draft she may have opened** (CLAUDE.md rule 7): change it by LAYERING on top, or by building
  the change into a NEW version (`<base> 1.1 → 1.2 → 1.3`) so the original stays untouched; to change an existing
  overlay layer, update it in place with `build-overlay.py`. CapCut must be quit before ANY draft write. Preserve
  her edits; improve the ENGINE for next time.
- 📖 Never revert her CapCut edits — observe what she changed, pick up where she left off.
- 📖 Plan → approve → build once. Deliver complete, not pieces.

---

## Green screen explainer — locked (named by the creator 2026-09-23, proven on the launch-site reel)

A format, not a treatment. She is **matted out of her own footage** and composited **over** the thing she
is talking about, so the screen behind her does exactly what she says as she says it.

- **Layer order is the format** — footage (continuous, never chopped) → screens → her cutout → captions →
  text. Anything that shares the frame with her goes BEHIND her; her matte rides on top. That ordering is
  what makes it read as her standing in front of the work rather than a picture-in-picture.
- **The screens are the real thing, driven to the audio.** Her actual page or app inlined in a HyperFrames
  composition and scrubbed on the timeline, plus UI mockups built to match the real product, each arriving
  on the line that names it. Never a screen recording — the timing has to hit her words, and a recording
  cannot be re-timed to them.
- **An oversized cursor carries the eye and causes the beats** (`oversized-cursor` skill). Every click
  lands TIP-ON the control it is clicking — measure the button's centre in the composition, subtract the
  arrow's 21%/14% tip offset. A cursor clicking near a button reads as broken.
- **Framing:** punch the named element into the open band ABOVE her head, fitted on WIDTH, never centred
  in frame. A full-frame plate is for the opener and the demo run; the punch-in is for the beats.
- **Plates leave by fading, never by `enable=` cutting out** — a one-frame vanish reads as a glitch.
- **Every layer is normalised to the 1080x1920 authoring canvas before compositing.** Her camera/graded
  footage is not that size, and ffmpeg takes its canvas from the base input, so skipping this pastes every
  overlay into a corner at the wrong scale and makes every placement in the engine look wrong at once.
- **It ports to CapCut with each element on its own track** — `capcut_handoff.py --layer NAME=FILE`.
  Screens and her cutout must stay adjacent and in that order or she disappears behind the screens.

## Highlight style captions — locked (named by the creator 2026-09-23)

> **The spec is a file, not prose:** `caption-templates/highlight-style.json` carries the exact sizes,
> colours and rules; `caption-templates/highlight-picker.md` carries the word-picker workflow and
> `highlight-picker.template.html` the widget itself. Load those when she says "highlight captions" —
> she approved this scale and type treatment exactly ("I love it"), so it is not to be re-derived.

The read-along, with a rare accent that does the pointing.

- **Base:** one word at a time, the pack's caption font (hers: Helvetica) in WHITE, under her chin, at the
  measured position from `subject-zones.json` — never a remembered number.
- **Accent:** the pack's accent serif in ITALIC, in the pack's accent colour (hers: Instrument Serif
  italic, butter yellow), and **visibly larger than the base — a serif reads smaller than a grotesque at
  the same px, so matching the number makes the accent look like a mistake.** Hers: 72px base / 104px accent.
- 📖 **The accent goes on the word carrying the CLAIM — the noun, the number, the payoff. NEVER the verb
  that delivers it and never a connector.** "I trained CLAUDE", not "I TRAINED Claude". "from SCRATCH",
  "in one AFTERNOON", "a REAL BUSINESS". The test: is this the word you want them to be impressed by?
- 📖 **Rare, and never two in a row.** Roughly one per spoken sentence that has a claim in it, and never
  on adjacent words unless they are one phrase ("real business"). Two serif words back to back read as a
  font change, not an accent.
- 📖 **Accents run THROUGH a UI demo too** (creator's call, reversing an earlier guess that the screen
  was already doing the pointing). While she narrates a walkthrough, the accent goes on the word that
  NAMES what the screen is doing as it does it — `crossfade`, `slider`, `nudge`, `forever` — so the
  type and the screen land together. This is where the accent earns the most; do not skip it.
- 📖 **An acronym or a word she says in caps keeps its case** (MCP, WEBSITE). Her captions are lowercase
  for intimacy; a lowercased acronym reads as a typo, not as style.

---

## Add-as-we-go
_New styles the creator mentions get appended here with their ID tag. (Say "add to the vault: …")_
