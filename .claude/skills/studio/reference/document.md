# document: generate the system source-of-truth doc

Load nothing else. `document` is the reel-engine analog of impeccable's `document` command. It reads the LIVE
engine and writes ONE synced source-of-truth doc, `product/STUDIO-SYSTEM.md`.

## Run
```
python product/studio_document.py
```
It reads `product/creative-vault/style-packs.json` (packs), the Studio skill (commands), and the standards
docs, then emits `product/STUDIO-SYSTEM.md`. Never hand-edit the output — edit the source and regenerate.

## What it's for
- The single reference behind the product (the CORE stays simple; this is what's under it).
- The community teaching hub + the "here's the ceiling" showcase.
- Kept in sync as the engine grows (new pack, new command → re-run, the doc updates itself).

## When to run
After any change to the packs, the Studio commands, the vibe palette, or the standards — regenerate so the
doc never drifts from reality.
