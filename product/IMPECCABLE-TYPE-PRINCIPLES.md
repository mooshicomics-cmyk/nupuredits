# Impeccable type principles — the cross-reference for WELL-DONE type

Pulled from the **impeccable** design system (`typeset` · `layout` · `adapt` · `craft-floor`) and adapted to
the reel context. **Cross-reference these on EVERY well-done type judgment** (build-reel-type.py) — the
well-done path is where I can see and self-verify the render, so every sizing/placement/hierarchy call is
checked against this before it's called done. (Raw/CapCut inherits the same INTENT but I can't self-verify its
render; there the creator's eyes + Text-panel screenshots close the loop.)

Where an impeccable *default* conflicts with the creator's **committed** reel design, the committed design wins
(impeccable itself: "a committed visual world overrides anything here"). Those overrides are called out below.

## 1. Hierarchy (typeset)
- **Roles must be distinguishable at a glance, without reading the words.** headline ≫ eyebrow/subhead ≫ caption.
- **Adjacent sizes/weights must carry different jobs** — if two roles are too close in size, the hierarchy fails.
- **Deliberate scale, not arbitrary values.** Everything steps from the headline anchor (see the gold standard).
- **Combine size + weight + space + color** — never ask size alone to do all the work.
- Fewest roles that make the hierarchy unmistakable. Don't add a font/role without a job only it can do.

## 2. Readability (typeset + craft-floor)
- **Meaning-bearing text must read over the footage.** Light type on busy/video → compensate: soft shadow,
  a touch more tracking, one step more weight if the face needs it. This is the real job of a shadow here.
- **Tune line-height to the face + width + contrast, not a universal ratio.** (Our tight `TIGHT_LH` is per-pack.)
- **Contrast floor:** the words a viewer must READ have to clear the background. Decoration may favor the look.
- Never make type decorative at the expense of comprehension.

## 3. Layout + placement (layout)
- **Squint test:** blur the frame — the headline still leads, the supporting line supports, groups read in
  reading order. If the eye lands on the wrong thing first, it's wrong.
- **Group by proximity.** The eyebrow/headline/subhead read as ONE unit — tight within the group, generous
  separation from the caption. Never equal spacing everywhere.
- **Rhythm = deliberate contrast** between tight and generous intervals, not one value repeated.
- **Spatial thesis first:** name where the eye goes (hook → face → caption); type accents that path.
- **Optical corrections only after inspecting the rendered result** — trust the frame, not the math. (This is
  why well-done is verified from the rendered frame, not just computed sizes.)

## 4. Craft floor (craft-floor)
- **Shadows carry an offset + a soft blur.** A zero-offset colored halo is decoration; a harsh hard shadow
  fights display fonts (per the creator, softened for Playful). Keep it soft.
- **Spacing:** tight groups, generous separation; more space above a heading than below it.
- **Balanced headings, no orphan words** — a lone last word is a defect (enforced by the measured balance pass).
- **Obvious scale + weight steps**; tracking has a floor (~-0.04em) so it never crams.

## 5. Reel adaptations (adapt + committed design)
- **This is 9:16 short-form over footage**, not a page. Text is bursts, read in ~1–2s. Bigger, fewer words,
  higher contrast than a web surface — adapt for the context, don't scale a page down.
- **Safe zone is a hard floor** (x150–930, y270–1620); the head is never covered by meaning-bearing text.
- **Committed override — the eyebrow/subhead is intentional.** Impeccable bans a "kicker/eyebrow above a
  heading"; the reel design deliberately uses it as a supporting line (reading-order split hook). It is kept,
  sized clearly subordinate to the headline, and treated as a real role — the ban does NOT apply here.
- **Supporting line = ONE line, full-width, when it stays readable**; if one line would be too small, wrap to a
  **balanced two lines (no orphan)** — two readable lines beat one cramped line. Never let it go tiny (floor).
- **Captions read low, below the chin.**

## The habit
Before a well-done render is "done," cross-reference it against the above from the RENDERED frame: hierarchy
holds (roles obvious at a glance), squint test passes (right thing leads), meaning-bearing text reads over the
footage, headline balanced with no orphans, the group is grouped (proximity + rhythm), shadow is soft, and the
supporting line is readable (one line or balanced two, never tiny). If any fails, fix it before handoff.
