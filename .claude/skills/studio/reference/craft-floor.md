# craft-floor: the quality floor (load before any Studio verb renders)

Two lists. **Verify** is the hard floor: fixed thresholds for things that are mechanically or perceptually
wrong, pass/fail, no brief earns them back. **Defaults** is the soft floor: the aesthetic starting points,
every one of them rebuttable by what the creator actually wants. The floor holds the mechanics. It never picks
the direction.

## Verify (hard rules: pass/fail, non-negotiable)

These are measurable limits on human perception and the platform frame. A reel that breaks one is wrong, not
stylish.

1. **Safe zone (validated against the platforms, not just our files).** Every piece of text and every key
   graphic stays inside **x 150 to 930** and **y 270 to 1620** on the 1080x1920 frame. The y band is the
   engine's single source, `product/safe_zones.py`; Studio keeps the tighter side margins on top of it.
   - Left/right margins (150px each) are at or more conservative than the platform (right icon rail
     ~90-120px, left ~60px).
   - **The top (270px) is the strictest platform band** (Meta's 14%). An earlier top of 200 shipped a
     persistent label under Instagram's Reels header, invisible in the render and only visible in the app.
     Never put readable text above y 270.
   - **The bottom (300px clear, y 1620) is the creator's explicit call (locked)**, deliberately looser than
     every platform's published band (Reels ~384, TikTok ~480, Shorts ~380). Today's reels sit well inside
     it anyway: captions at y~1120-1200, the hook top-anchored at y~280. When a reel is cut for ONE platform,
     `safe_zones.violations(..., platform=...)` measures against that platform's real band.
   (Engine encodings: `safe_zones.py` is the source; `LAYOUT-STANDARDS.md`, `build-hf-captions.py` and
   `CLAUDE.md` echo it. Studio does not keep a second bottom number.)
2. **No face overlap.** Text never sits on the speaker's face. The hook and thoughts ride ABOVE the head; the
   captions ride BELOW the chin. If a size makes text collide with the face, the size is wrong, shrink or move
   it. (The head position is measured, not guessed: `workflows/head-framing.py`.)
3. **Nothing runs off screen.** If a line would cross the safe-zone edge, it auto-fits DOWN or wraps. A hook
   that clips the frame edge fails. (Encoded: auto-fit in `build-reel-type.py`; engine-injected line breaks in
   `capcut_text.py`.)
4. **Meaning-bearing text is legible over footage.** The words a viewer has to READ, captions, the hook, any
   on-screen message, must read against the moving background they sit on. If the footage behind such a line is
   busy or the same value as the text, it needs its scrim / weight / shadow, or it fails. This is the real job
   of `/studio accent`. **Scope note:** this floor is for text that carries meaning. It does NOT apply to
   decorative or animated flourishes, where the aesthetic can win (see Defaults). Captions must be readable
   first; a background animation does not.

## Defaults (soft rules: the starting point, rebuttable by intent)

These are where the reel gets its look. They are defaults, not bans. The creator's own direction can earn any
of them back. Reaching for one when the choice is actually free means you were not deciding, you were coasting.

- **Hierarchy: the hook is the loudest thing in frame.** Everything else sizes down from it. The caption is
  comfortably readable and never competes with the spoken moment. (This is a proportion, not a number, see
  `scale.md`.)
- **Line-height that breathes but stays one thought.** Two stacked lines should never feel cramped, and never
  so airy they read as two separate ideas. Tune it by feel against that target, not to a fixed value. (The
  packs ship a starting `line_height` per element; Playful runs tighter at 0.9.)
- **Caption measure stays comfortable.** Roughly a phrase per line, not edge-to-edge, not one lonely word.
  Wrap early rather than let a line reach the safe-zone edge.
- **One accent, not a rainbow.** Within a style pack the palette is white text plus one accent. Emphasis is
  one word or one phrase carrying the accent, not several. More color is less emphasis.
- **Case and weight come from the pack**, not from taste in the moment. Change them only when the creator asks.
- **Decorative and animated elements can favor the aesthetic over strict contrast.** A flourish, a moving
  accent, a stylized moment does not have to hit the legibility floor the way captions do. Video is a look
  first. Reserve the hard readability rule for the words that carry meaning; let the decoration breathe.
- **Decoration can sit OUTSIDE the safe zone. Text cannot.** A sparkle, doodle, or flourish carries no meaning
  to lose, so it may reach into the top and bottom bands and the corners, right to the frame edge. Text and any
  meaning-bearing graphic always stay inside the safe zone. Decoration also never covers the face or the words.

## The boundary

The floor holds the mechanics. It never picks the direction. If the creator's intent conflicts with a default
here, the intent wins and you honor it, as long as no **Verify** rule breaks. If honoring the intent would
break a Verify rule (text off screen, on the face, unreadable), say so plainly and offer the nearest version
that clears the floor.
