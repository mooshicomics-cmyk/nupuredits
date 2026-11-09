# inspo: turn a reel you love into a pick-list of what to borrow

`/studio inspo <link>` (also triggered by "**watch this reel**," "watch <link>," "here is some inspo," "I love
how this reel is edited," "match this reel," "match the effects / text styling / animation / sound effects
in <link>"). "Watch" always means run inspo, never open the in-app browser. The creator sends a reel
they love, you WATCH it, and you hand back a short multiple-choice list of the style elements it uses, so they
tell you exactly which ones they want for their own reel. You study the FORMAT, never the concept or the words.

## The rule that makes it safe

**Borrow the craft, never the content.** You take pacing, type energy, delight touches, motion, color, and the feel of the sound. You
never take their topic, their script, or their story, and you never name the original creator in anything that
ships or posts. This is the same rule as the `reference-reel` skill, which does the pulling.

## Flow

1. **Watch it via Apify (never the in-app browser, it login-walls).** Hand off to the `reference-reel` skill:
   it pulls the public reel by link with the creator's own Apify key (a few cents, say so first), downloads the
   video + audio to `projects/<job>/references/`, and runs `product/reel-fingerprint.py` for the editing
   fingerprint (cut cadence, hook burst, rhythm, ending). Also pull a few frames to read the graphics.
2. **Identify the borrowable elements** across these lanes, from what you actually saw:
   - **Type + fonts**, hook energy (chunky handwritten? clean serif? all caps?), filled vs outline/hollow,
     any font PAIRING (two fonts working together), case, an emphasis word.
   - **Delight touches** (these feed `vibe`), sparkles (glyph / emoji / hand-drawn), emoji, hand-drawn
     doodles, a handwritten note, a text-message bubble, a squiggle or marker underline.
   - **Motion + pacing**, hook burst opener or a slow hold? cut cadence, hold-then-punch, kinetic type
     effect, a zoom or push-in.
   - **Color**, the one accent and how it is used.
   - **Caption energy**, big single words? karaoke build? where they sit.
   - **Sound**, is there a music bed and how fast (the fingerprint's BPM), how busy the sound effects are
     (a hit on every cut, only on text pops, or almost none), and what KIND of sound goes with what motion
     (a pop when text lands, a whoosh on a transition, a click on a UI moment). You cannot hear the audio,
     so do not pretend to name exact sounds: read what you can from the frames at each cut and text pop plus
     the music read, then ASK her one line, "what did you like about the sound?", and let her answer fill
     the gaps. Never reuse their audio files or their music; you are matching the feel, with her library.

   **If they name what to match** ("match the effects", "just the text styling", "the animation and the
   sound effects"), lead with those lanes, go deeper on them, and skip the rest unless they ask. Only when
   they say "all of it" or name nothing do you list every lane.
3. **Hand back a multiple-choice list, grouped by lane, numbered,** and ask them to pick the ones they want.
   Keep each item short and concrete ("chunky yellow handwritten hook," not "nice typography"). Offer "all of
   a lane" and "none" as easy options. The point: know EXACTLY what they liked, not a vague "make it like this."
4. **Turn the picks into a build directive.** Their choices map to real engine moves: a matching style pack,
   the specific delight touches `vibe` should reach for, the cut cadence / hook-burst for the rough cut, the
   accent color, the nearest named text animation from the effects catalog for the motion they picked, and
   for sound: the matching sound JOB from the engine's own library (`python3 product/capcut_sfx.py --list`,
   her favorites first via `python3 product/favorites.py show`), a density (`lighter / normal / heavier`) and
   a music bed only if the reference had one. Say plainly when the engine can only get close. Confirm the
   plan, then build.

## The list format (mirror this)

> Here is what this reel is doing. Pick the ones you want for yours:
> **Type**  1) chunky handwritten hook in one bold color  2) filled + hollow font pairing on a key phrase
> **Delight**  3) small hand-drawn sparkle on the headline  4) a text-bubble aside with an emoji
> **Motion**  5) slow hold on the opener, then punchy middle  6) kinetic pop on the emphasis word
> **Color**  7) one warm accent (their yellow)
> **Sound**  8) a soft pop every time text lands, nothing on the cuts  9) a quiet upbeat music bed
> Reply with the numbers, or "all type," "just delight," etc.

## Guardrails

- Public data only, via Apify (BYOK). Never log in, never scrape private accounts, never open Instagram in the
  in-app browser to "watch."
- FORMAT not concept. Never reuse their words, hook, or story.
- Reference clips stay local and neutral-coded; never name the original creator in anything shipped or posted.

## Finish

Once they pick, the elements route into the normal build (pack + `vibe` touches + cut cadence), and it ends,
like every verb, at **glow**.

### Then offer to keep it

Inspo used to end there, which meant a look they loved lasted exactly one reel and had to be re-derived from
the link every time. Once the reel is built and they like it, **offer to keep it, in one line** — and only
offer what they actually picked:

- fonts + colors → **`/studio recipe`** (or "save this as my pack"), which writes a named pack that survives
  every update.
- a text animation they liked → **`/learn effect "<their name for it>"`**, built from whichever catalog
  effect you used to get there. Name it in THEIR words, not the engine's id.
- density, caption scale, SFX weight, the opener push-in → **`/learn`**, scoped to the register the reel was
  in, because a lean confessional look is usually not what they want on a teaching reel.

Offer once, warmly, and drop it if they say no. Never save any of this without being told — a preference
applies itself to every future reel, so it is theirs to choose, not yours to assume.
