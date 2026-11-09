# captions: swap ONE line's on-screen treatment (single / karaoke / takeover)

Load `craft-floor.md` and `scale.md` first. These verbs change how a SPECIFIC transcript line is displayed,
without touching the rest of the reel. The reel has a default caption mode (single or karaoke); these let the
creator override one line to any of the three treatments — or, extensibly, any future preset layout.

## The three treatments (what they're called)

- **single** — single-word captions: one word snaps on at a time, centered low. Clean, minimal read-along.
- **karaoke** — the whole line sits and the active word highlights word-by-word as it's spoken (accent on the
  current word). More energy.
- **takeover** — full-screen takeover: one big word or phrase fills the screen on that beat (the emphasis
  punch). The line is pulled out of the caption band and shown as a centered stack.

## How to invoke

`/studio <treatment> <line>` — the treatment verb + the transcript line (or a distinctive phrase from it):

- `/studio karaoke you keep going anyway` → that line builds karaoke; the rest of the reel stays default.
- `/studio takeover this changed everything` → that line becomes a full-screen takeover.
- `/studio single and it never got easier` → force that one line to single-word (e.g. inside a karaoke reel).

Match on the phrase; the span extends to the end of its sentence, so a few distinctive words are enough.

## What it does (engine)

Writes a `caption_treatments` entry `{ "text": "<phrase>", "mode": "single|karaoke|takeover" }` into the
reel's caption plan. The well-done engine (`build-reel-type.py`) finds that line's word span and renders it in
the chosen mode while every other line keeps the default. **takeover** joins the takeover keys (full-screen
stack, pulled from the caption band); **single/karaoke** stamp a per-word mode override on that span only.
Multiple treatments can stack (karaoke one line, takeover another). Extensible: a new preset layout becomes a
new `mode` value with its own renderer.

## Hold the floor

- The line still obeys the safe zone and never covers the face. A takeover is a centered stack sized to the
  safe width (measured, never estimated); single/karaoke ride the caption band under the chin.
- Don't over-takeover: full-screen takeovers are the emphasis punch — one or two per reel, on the line that
  earns it, not every line. More takeovers = less impact (same spirit as one accent, see `craft-floor.md`).
- Meaning-bearing text stays legible over the footage (weight/shadow); that floor applies to all three.

## Per path (from `fidelity.md`)

- **Well-done MP4:** all three land exactly — engine-rendered, self-verifiable. This is the pixel-guaranteed path.
- **Medium (CapCut + `.mov`):** the treated line renders in the overlay; note it moves as a block.
- **Raw (editable CapCut):** captions are the creator's native Auto Captions, so `single`/`karaoke` on raw is
  an advised in-app move (Auto Captions style), not an engine set. A **takeover** line CAN ship as a real
  engine overlay even on raw, since it's an authored element, not a native caption. Say plainly which is which.

## Finish

Hand off to **glow** for the final read.
