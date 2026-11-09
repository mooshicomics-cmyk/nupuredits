# accent: color that reads (inside the pack's fixed palette)

Load `craft-floor.md` and `scale.md` first. `accent` is the color verb, but it is NOT palette design. The
style pack already fixes the palette: white text plus one accent. `accent` works inside that. It does two
things, and only two: it makes sure the text READS against the footage behind it, and it gets the accent
SHADE right. This is the one Studio verb that has no real twin in impeccable (impeccable's colorize builds a
palette from scratch; here the palette is locked and the job is legibility within it).

## What it holds

1. **Legibility over footage (the real problem).** Text sits on moving video. If the footage behind a line is
   the same value as the text, or busy, the line disappears for a beat. `accent` makes it read: lean on
   weight, the pack's shadow/scrim, or nudging the line off the busiest part of the frame. This is a floor
   (`craft-floor.md` Verify #4), not a taste call. Borrowed lightly from impeccable's readability thinking:
   the test is "can you read every word on the worst frame it sits over," not a strict contrast ratio. We are
   not chasing ADA numbers, we are making sure a scroller can read it. **This applies to the words that carry
   meaning: captions, hook, message.** A decorative or animated flourish can favor the look over contrast;
   video is a look first. Fight for the caption's legibility, let the decoration breathe.
2. **The accent shade.** One accent carries emphasis (the pack default, or the creator's own color). `accent`
   tunes that shade so it pops against the footage without going neon or muddy, and keeps it to ONE word or
   phrase. More accent is less emphasis.

## Set or change the accent color

Each style pack already ships its OWN accent (Editorial pink, Butter marigold, Playful
mustard) — that is the working default and it is ALWAYS present. `default_accent` in
`product/creative-vault/user-style.json` is an OPTIONAL personal override: one color that replaces the pack
accent across every pack, for a creator who wants a single brand color everywhere. **Null is fine and is the
normal state** — it simply falls back to the pack's own accent. Do NOT block or nag for it before a build;
only set it if the creator explicitly asks for one color across all packs.

- **`/studio accent <color>`** (a hex, or a color they name) sets it. Ask ONE thing: "just this reel, or your
  new default?"
  - **This reel only:** use it for this build (pass it as the per-reel accent, which wins over everything), and
    leave the saved default alone.
  - **New default:** write it to `default_accent` in `user-style.json` (push the old value into `history`), so
    every future reel uses it until they change it again. Changing it is a one-liner, any time.
- The pack's own `accent_color` is only the fallback when the creator has not chosen one. Never impose it.

## The pack palettes (the fixed ground you work within)

Each pack ships white text plus one default accent, and the creator can override the accent with their own
color. Defaults today: Editorial pink (`#ffadbf`), Butter marigold (`#fdc341`), Playful mustard (`#F5C518`).
The global default when a pack sets none is white. `accent` never invents a second accent or a new palette; it adjusts the one that exists.

## How to think

Play the line over the actual footage it rides, not a flat background. Watch the busiest and the lightest
frames it covers. If it holds up there, it holds everywhere. If it drops out, that is the fix: more weight,
the scrim, or a small move, before touching the color itself.

## The moves

- **Make it read first.** Weight, shadow/scrim, or position. Legibility beats a prettier shade every time.
- **Then tune the shade.** Push the accent until it separates cleanly from the footage without shouting. Keep
  it the pack's one accent.
- **Keep emphasis to one thing.** One accent word or phrase per moment.

## Per path (from `fidelity.md`)

- Engine text color + the accent shade: exact on MP4/medium; exact for engine-authored text on raw.
- Native line-caption color + keyword highlight on raw are the creator's in-app choice. `accent` advises the
  readable option (which keyword to highlight, keep the highlight the pack accent) rather than setting it.

## Finish

Hand off to **glow** for the final read.
