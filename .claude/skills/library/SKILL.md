---
name: library
description: Open the in-engine Effects Library — the interactive reference wall of every effect (with live previews), every command to say (tap to copy), and how it all works (the cheat cards). Use when the creator says "/library", "library", "open the library", "show me what you can do", "show me the effects" or "the options", "what can you do" / "what can this do", "the HyperFrames catalog", "more effects", or seems unsure what to ask for. It lives on their laptop and opens in a browser — nothing to install.
---

# Library — open the Effects Library

The engine ships an interactive reference page at **`product/effects-library.html`**. It has
five tabs:

- **Effects** — every effect in one place: the engine's own looks and the whole HyperFrames catalog,
  organized by what she wants to do on a line (Words, Moments, Footage, Scenes, Sound), one home each.
  It opens on the **Recommendations** category (named for the engine's creator): the engine's own looks, the
  ones it uses on its own, each with a live preview, sorted by kind. Every category shows those first, then the HyperFrames pieces she asks for
  by name (tap a tile for its demo full size; demos play from the internet). A heart on every card keeps
  it in **My Favorites**, saved to `favorites/effects.json`, which no update touches; `python3
  product/favorites.py show` lists them, so offer her hearted effects first where one fits. Tap a name to
  copy it. Color grades open full size to compare (flip, drag, or hold before/after).
- **Commands** — the exact words to say (steer this reel, dress it up or down, train it, save a
  look, bring your own). Tap a command to copy it.
- **Studio** — every `/studio` finishing command, grouped (fix the look, change one line's captions,
  add personality, borrow or build a style, finish and reset), each with what you get. Tap one to copy it.
- **Sounds** — every sound effect the engine can pick, filtered by what it is for and how it feels.
  Press play to hear one; tap its name to copy it.
- **How it works** — the cheat-card concepts (build in layers, teaching vs confessional,
  doneness, and that the good stuff is automatic).

## What to do

Open the page for the creator. Do NOT just name the file path — they will not go find it.

**Always open it in her own browser, never the app's Browser pane / preview surface.** The pane loads a
local file as a one-off snapshot, cut off from the engine folder, so every sound's play button fails
silently there (the animations still run, which hides it). In her own browser the page reads straight
from the folder and the sounds play. Run:

   ```bash
   bash scripts/open-library.sh
   ```

   Never a bare `open product/effects-library.html`. On a Mac the script serves the page from her own
   computer (http://127.0.0.1, only the library's own files, stops by itself after an hour), because
   Safari will not play the sounds of a page opened as a file, and it opens in whichever browser she
   already uses. On Windows it opens the file in her default browser, which plays them. It works from any
   terminal, so the page always opens regardless of how she runs Claude Code.

To open straight to one tab, name it: `bash scripts/open-library.sh studio` (also `commands`, `sounds`,
`concepts`). Use `studio` when she asks what the /studio commands are.

Then say, in one warm line, what it is: "Here's your whole menu — every effect in one place, the exact
words to say, and how it all works. Heart the ones you love, tap what you want, and just ask me for it by name."

## Three things the creator almost never knows they own

Say these out loud when you open the page, because a capability nobody knows about is the same as one
that does not exist:

- **Her own sounds.** Drop `.mp3` files into `product/creative-vault/sfx/` and they join the pool the
  engine picks from. `python3 product/capcut_sfx.py --list` shows what is in there now. Or the easy way:
  a CapCut project of her favorite sounds, then "study my CapCut draft called <name>"
  (`python3 product/favorites.py learn "<name>"`). Those win over everything bundled.
- **Her own fonts.** Any font she owns, through her style pack. "Build my own style pack."
- **Her own named animations.** `/learn effect` names a look she likes so she can ask for it by name.

All three are hers: they survive every engine update, and none of them ship with the engine.

## The HyperFrames catalog (the bigger shelf behind this page)

Her engine is built on HyperFrames, and every item in its catalog is hers to ask for by name: caption
styles, VFX, transitions, social cards, data, effects, overlays. When she asks for "more effects", "the
HyperFrames catalog", or names something she saw there, open it in her own browser (`open` on Mac, `cmd //c
start ""` on Windows): `https://www.hyperframes.dev/?view=catalog`. Then: "Tap Try it on anything, then
tell me its name and the line you want it on." Catalog items need medium or well done. How the engine
builds one is in CLAUDE.md, "The HyperFrames catalog is hers to use, by name".

## Notes

- The page is self-opening and needs no install (browser + `open` are already on every Mac). It
  loads its animation library and fonts from the internet, which the creator always has while
  using the engine; offline it still opens and reads, the live previews just pause.
- Onboarding (`set-me-up`) opens it once so the creator knows it exists. This skill reopens it any
  time they ask.
- Creator-facing and brand-clean: the page carries no personal name, brand, or paths.
