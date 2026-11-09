# vibe: the personality pass (tasteful, never AI)

Load `craft-floor.md` first. `vibe` adds ONE tasteful, memorable touch to a moment that earns it. It is the
"feels like her, not a template" verb. It is the hardest to get right and the easiest to overdo, so the whole
playbook is built to keep it feeling human.

## vibe IS delight (impeccable's `delight`, applied to a reel)

`vibe` is the reel version of impeccable's **delight** — NOT "add a set thing" (an emoji, a sparkle). Those are
just examples. Delight is: **read the actual content, find the ONE moment that earns a touch, and act in
context.** The method, every time:

1. **Find the opportunity.** Read the transcript + register + what's already on screen. Look for a moment worth
   accenting: the emotional turn, the punchline, an emphasis word, the win, a beat of tension, a list item. Do
   NOT manufacture a flourish for an ordinary line. Most beats get nothing; ONE beat might earn something.
2. **State one thesis** (one sentence): what should the viewer FEEL here, and why does that belong in HER reel.
3. **Choose the smallest touch that delivers it, derived from HER world** (her doodles, her fonts, a real emoji,
   the pack accent), never a stock catalog. Proportional to the moment — a big turn can carry more, a routine
   line carries nothing.
4. **Protect the content.** The touch never covers the words or the face, never competes for the first look,
   never makes the reel feel busy or AI-made. If it would fight the register, it doesn't go in.

Everything below (the touch vocabulary, the register rule, placement) is HOW you execute that method — a palette
to draw from with judgment, never a checklist to apply.

## The one rule that keeps it human

**`vibe` never ships gritty AI-looking art.** It reaches for things that read as intentional: real emoji, her
own supplied doodles, OR **clean generated vector doodles** (daisy, marker sparkle, marker underline) — the
engine's built-in set, approved 2026-08-08 as clean enough to ship. (Earlier rule said "never draw one";
that was too strict — clean minimal vectors are fine, only gritty/messy generated art is out.) **Doodles default
to WHITE** (2026-08-08), not the accent, unless a pack or reel says otherwise. Everything it reaches for is
either real, hers, or a clean built-in vector:
- her own **doodle / illustration pack** (PNG files she supplies, per the engine rule "illustrations come from
  her"). Until those files exist, vibe uses the touches below and asks her to drop doodles she wants.
- **real emoji** (Apple emoji, baked as PNG via `emoji-to-png.py`), one at a time, matched to the mood.
- **real gifs** she picks (suggest 2-3 from a source; she chooses; never auto-drop).
- the pack's **fonts** (handwritten, script, serif) and its **one accent color**.

And two habits keep it from feeling scattered or random:
- **It proposes, she approves.** vibe reads a beat and offers a touch ("this line feels excited, a hand-drawn
  sparkle on the hook, or your daisy in the corner?"). She picks. Her taste stays in the loop.
- **One touch per earned moment.** Not a sprinkle. A touch appears because THAT beat earns it.

## The touch vocabulary (a palette, NOT a checklist)

These are the KINDS of touches she likes, gathered from her reels and mockups. They are taste direction to
draw from with judgment, not a list to apply every time and not literal requirements of the command. Most
reels use ONE touch, chosen for the beat. Many use none. When in doubt, less.

- **Sparkles:** a real ✨ emoji (playful / text-message feel), or a hand-drawn marker sparkle from her pack
  (Playful). Small, clustered near a headline or scattered around the subject. (REJECTED 2026-08-08: the
  elegant 4-point diamond glyph — she vetoed it, do not offer it.)
- **An emphasis word:** one word in italic + the accent color (Editorial serif). (REJECTED 2026-08-08: the
  filled-plus-hollow font pairing — she vetoed it, do not offer it.)
- **Hand-drawn accents (from her pack):** a daisy / flower outline in a corner, a squiggle underline, or a
  scratchy marker underline in her accent color, under a headline.
- **A real emoji**, one, matched to the feeling (a ✨ on a headline, a ❤️ on a tender beat, a 🤩 on a win).
- **An iMessage-style text bubble** aside with an emoji (playful).
- **A word on an arc / curve** (playful hook).
- **A gif** she picks, for a beat that wants motion and humor.

## Motion (every touch animates ON naturally — 2026-08-08)

A vibe touch never hard-pops into place. It arrives the way a hand would make it, matched to what it is:
- **Strokes DRAW ON.** A marker underline, a squiggle, a daisy — the line strokes on left-to-right / petal-by-
  petal (SVG `stroke-dashoffset` write-on). Implemented for the marker underline and daisy; use the same for
  any stroked doodle.
- **Sparkles TWINKLE** on (quick scale + a little rotate, staggered across the cluster), not a flat fade.
- **Emoji / bubble SETTLE** — a soft scale/slide with a gentle overshoot (ease like `back.out`), then rest.
  A bubble slides up into place the way an iMessage bubble does.
- **Timing:** the touch lands AFTER the hook/line it accents has arrived, so it reads as a reaction, not a
  competitor. Keep it quick (~0.3–0.5s) and never looping-distracting.
The write-on/draw-on is the signature — it's what makes the touch feel human-made instead of stuck-on.

## The register rule (this is what scales it, and what makes it feel intentional)

How much vibe does is set by the emotional register, not by taste in the moment. Ask or infer the register,
then hold the right restraint:

- **Playful / upbeat (talking head):** the most room. Chunky handwritten hook, hand-drawn sparkles, an arc, one
  warm accent, a kinetic pop on the emphasis word. You can layer two small touches if the beat is big.
- **Editorial / elegant:** refined, not loud. Serif, ONE italic-accent emphasis word, one pair of elegant
  diamond sparkles. Restraint reads as taste here.
- **Teaching:** structure supports the point. A number that pops, a checkmark, a labeled stat card, a clean
  numbered list, or a **full-screen accent-color takeover** for a list item (the whole frame goes the pack
  accent with one big bold number or word, then back to footage). Uses the existing takeover mechanism. More
  than confessional, tasteful not cluttered, and every element earns its place.
- **Confessional:** almost nothing. A small quiet caption in a soft, muted accent, and usually not even that.
  No sparkles, no doodles, no emoji. **The restraint IS the touch.** (Her rule: confessional gets no graphics.)
- **VO / sentimental (b-roll):** soft flowing script captions over the b-roll, gentle. Emotional, never
  decorative. No playful sparkle here.

If a touch would fight the register (a sparkle on a confessional grief beat), you do not add it. The register
wins.

**Treatment intensity sets the room too.** A **loaded (teaching) Yap** gives vibe the most room
to layer, a **trimmed-back (confessional) Yap** stays minimal. Loaded is never the same as cluttered: even a loaded Yap holds the
one-touch-per-beat discipline.

## Placement (be mindful of what is already there)

- **Never place a touch on top of existing graphics or text.** A sparkle, doodle, or emoji goes in the
  NEGATIVE SPACE around the hook, caption, and thoughts, never over them. Read where the text already sits and
  find the gap.
- **Decorative touches MAY sit outside the safe zone.** Unlike meaning-bearing text, a sparkle or doodle can
  reach into the top and bottom bands and the corners, right to the frame edge. It is decoration, not a
  message. The only hard limits: never cover the speaker's face, and never cover the words.
- **Meaning-bearing text still obeys the safe zone and stays legible** (`craft-floor.md`). The exemption is for
  decoration only.

### Compose the touch, do not drop it (the layout sense, shared with `tidy`)

Place a decorative touch the way a designer composes a frame, never at a fixed pixel. These are impeccable's
layout principles, applied to aesthetics:
- **Squint test.** With the frame blurred, the hook still leads and the caption still reads. The touch is a
  SUPPORTING accent, never something that competes for the first look. If your eye lands on the sparkle before
  the words, it is wrong.
- **Spatial thesis first.** Name where the eye goes (hook, then face, then caption). The touch accents that
  path, it does not redirect it. It sits in the quiet space the composition already leaves open.
- **Group it.** A cluster is ONE visual unit, close together, not scattered evenly. Rhythm comes from tight
  versus generous spacing, never the same gap everywhere.
- **Optically correct.** Trust the rendered frame, not the math. Place it, look, nudge. That propose - render -
  adjust loop is the method, not a fallback.
- **Balance the weight.** If the hook is heavy top-left, a small touch top-right settles the frame. Read the
  existing weight before adding.
- **Anchor to the element, not the frame.** A sparkle that accents the headline HUGS the headline's corner,
  close to the words, not floating up in the frame corner. The frame edge and the safe-zone box are NOT
  elements. Position relative to the text you are decorating, then let it breathe just past that text.

## Per path (from `fidelity.md`)

On MP4 and medium, vibe's touches are baked in exactly. On the raw CapCut path, engine-placed overlays (an
emoji PNG, a doodle, a `.mov` sparkle) drop in; anything that is really an in-app move, vibe hands over as the
exact step rather than pretending it did it.

## Finish

Hand off to **glow**.
