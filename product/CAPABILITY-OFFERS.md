# Capability Defaults — apply the strong version, don't make the creator ask for it

**Never make the creator REQUEST quality.** The elevated build is the DEFAULT, not an upgrade
she has to know to ask for. The rows below are the DEFAULTS the engine applies automatically
for each format. Apply them, then say in ONE line what you did and how to change it. Do NOT
ask "would you like movement / a grade / animated cards?" as a gate — just do the format-fit
default. The creator does not know the menu, so waiting for her to ask means she never gets it.

**What the engine still ASKS (the only either/ors it can't infer):** register
(teaching / confessional) and the doneness / finish route. Those two genuinely change the build
and are not derivable, so surface them as a clean pick-one. Everything else, apply by default.

**Two things govern what the default IS** (they protect measured results and her control):
- **Register** — confessional stays lean (near-zero graphics, the highest-reach register);
  teaching gets the loaded treatment. "Apply by default" never means dumping graphics on a
  confessional reel.
- **Doneness / route** — motion and baked animation default ON the rendered routes
  (medium / well-done / Animation), never the CapCut-editable route, where they stay the
  creator's to add in CapCut (baking there would remove her control). **A color grade is the
  one rendered-route treatment that is NOT a default (locked): optional and available, applied
  only when she asks for one by name** (cinematic / warm / cool / film / mono, footage only,
  never the graphics — `product/video_grade.py`). Offer it in one line; never apply it unasked.
  Mechanism when she says yes: `GRADE=<look>` in the environment of `product/build-reel-mp4.py`
  (the well-done finish), or `python3 product/reel_render.py composite ... --grade <look>` (the
  fast re-stack). A misspelled look refuses loudly instead of shipping the reel ungraded.

**Dialing it up or down within a register (how the creator asks for "more"):** register sets
the baseline; the creator nudges intensity with plain words and the engine just acts, no menu.
- **MORE** — "dress it up", "add more effects / more graphics", "more movement", "make it
  richer / fancier / more produced / more dynamic", "punch it up", "give it more", "spice it up".
- **LESS** — "keep it clean", "strip it back", "simpler", "less", "pull it back", "too much".

A **richer confessional** adds MOTION and POLISH only: more text animation, movement / Ken Burns,
a held word, matched SFX, a subtle grade. It NEVER adds the teaching STRUCTURE that breaks the
confessional contract — no summary card, no checklist or ranked list, no closing takeaway, and the
hook still never mirrors the spoken line. "Richer" changes the finish, not the register. (If she
actually wants the teaching treatment, that is a register switch: "make this a teaching one.")

**When to apply + tell her:** at the style-plan hand-off, at any "what's next / move on"
moment, and when a rough cut is approved and the creative plan begins.

**The browsable menu:** when a creator wants to explore what is possible (or you want to
show them), OPEN **`product/effects-library.html`** for them — do not just name the file,
they will never go find it. Always launch it in their real browser, never the Browser pane
(the pane cannot play the library's sounds): `bash scripts/open-library.sh` on a Mac and on
Windows (never a bare `open`: Safari will not play the sounds of a page opened as a file, and the
script serves it so every browser does). It works in a plain terminal too, so it always opens
regardless of surface. It is an
interactive wall of every effect with live previews, grouped by category, with tap-to-copy
names, and five tabs (Effects / Commands / Studio / Sounds / How it works). A creator with a vision browses it,
finds the look, and asks for it by name. It is driven by the **`library` skill**. Triggers to
open it: "library" or "/library", "show me what you can do", "show me the effects / options",
"what can this do", or any moment they seem unsure what to ask for. It lives on the laptop, no
PDFs, nothing to install. Onboarding opens it once so they know it exists. The offers below are the same menu, surfaced one gate at a time.

**How to surface (don't interrogate):** apply the default, then note it in ONE plain line and
say she can change it ("I put a slow push-in on your shots and animated the hook — say the word
to swap either"). Never a wall of "do you want X?" questions. Present only what fits the chosen
format AND doneness. If she wants to browse or steer, OPEN the effects library for her (below).

---

## Yap (talking head)
- **Movement (automatic, tell her what you did):** every Yap gets a slow zoom-in on the opening clip plus gentle jump-cut punch-ins on later cuts, applied by the engine in finalize (`capcut_motion.py`) so the frame never sits dead still. Do NOT ask "want movement?" as a gate. Say it in one line and offer the change: "I put a slow zoom-in on your opener and subtle punch-ins on the cuts. Want them stronger, softer, or off? Just say." It only touches clips nobody already zoomed, so an explicit zoom she set is kept. To dial it: change the punch cadence/scale or intro-zoom amounts in `capcut_motion.py` (`PUNCH_EVERY_NTH`, `PUNCH_SCALE_POOL`, `INTRO_ZOOM_*`), or pass a `punch` dict to `add_cut` for hand-placed pushes.
- **Text motion:** "Your hook and takeover animate with `<effect>` right now. Want a different style? I can show the menu."
- **[Teaching / loaded only] Motion cards:** "Want animated stat cards, a ranked list, a comparison split, or a count-up for the numbers?"
- **[Teaching / loaded only] Transitions:** "Want velocity-matched transitions between cutaways, or keep hard cuts?"

## Voiceover
- **Movement:** ON by default — a gentle Ken Burns move (alternating push-in/out) rides every hold. Offer the opt-out: "Want to lock the shots still instead?"  _(default: Ken Burns on; `--motion still` locks it)_
- **Grade:** "Want a cinematic color grade on the b-roll?"
- **Mix:** "Want the music carved under your voice for a cleaner mix, or keep the flat bed?"
- **Transitions:** "Want soft transitions between shots (a gentle zoom-through), or keep hard cuts on the VO cadence?"

## Animation (footageless)
- **Motion feel:** "Want the whole piece to move as one continuous camera with matched transitions between scenes?"  _(default: on)_
- **Source imagery:** "Want generated backgrounds / icons in the frames, or type-only?"
- **Voice vs music:** "Run it on your voiceover, or music-only and beat-synced?"
- **Data:** "Any numbers worth animating (a count-up or a chart hit)?"

## B-Roll Reels
- **Hook motion:** "Want the hook to animate on (letters rise, soft blur), or a flat native-look bake?"  _(default: flat)_
- **Movement:** "Want a slow push-in on the clips?"
- **Grade:** "Want a cinematic color grade?"

## Finish (any format)
- **Cover:** "Want a cover frame picked and titled?"
- **Sound:** "Want a matched SFX pass, or a music bed?"

---

Each offer is one line, default marked, only when the format and doneness support it. The
goal is discovery without interrogation: the creator learns what is possible at the exact
moment the choice matters.
