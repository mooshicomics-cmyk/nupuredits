---
name: edits-kit
description: >-
  Turn the Instagram Edits Kit on or off — the switch that makes Instagram's Edits app the creator's DEFAULT
  output. Use when she says "Turn on my Instagram Edits Kit", "turn on the edits kit", "use Edits as my
  default", "I'm editing in Edits now", "make Edits my default output" (ON), or "turn off my Instagram Edits
  Kit", "go back to normal", "use CapCut again" (OFF). When ON: every export defaults to the Edits app
  (medium), the rough cut transcribes in Edits (fast "lean mode") when connected, and the engine opens Edits
  for her. Reversible. Her choice, not the engine's out-of-the-box default. Needs the app installed and the
  MCP token connected once. ALSO self-heals a broken connection: use when she says "my Edits tools won't load",
  "reconnect Edits", "reconnect it", "Edits won't connect", or when Claude has told her the connection isn't
  working.
---

# Instagram Edits Kit — the switch

One phrase makes Edits her default output everywhere — widget, visual editor, or YouTube/horizontal — the same
medium handoff the engine does to CapCut and Resolve. It's **her** default, not the ship default; fresh
installs stay on WhisperX + CapCut. Fully reversible.

## Turn it ON — "Turn on my Instagram Edits Kit"

1. `python3 product/edits_mode.py on`
2. `python3 product/edits_open.py` — open the Edits app for her (she never has to).
3. Confirm plainly, something like:
   > "Instagram Edits Kit is on. From now on your reels export to the Edits app as **medium** (your cut plus
   > every look as its own movable layer, so your style holds). When Edits is connected I'll also transcribe
   > your cut in Edits — it's faster — and fall back to WhisperX if it isn't. I'll open Edits for you when a
   > step needs it. Say **'turn off my Instagram Edits Kit'** any time to go back to CapCut."

**First time only** (the app isn't connected yet): she installs the Edits app, then connects its MCP once so
the engine can drive it. **Connect THROUGH the engine's shim, never with a direct `--transport http` add.** The
direct connection loads zero Edits tools on Claude Code 2.1.301 (the Edits server's `tools/list` carries a
`resultType` key that version rejects for missing `ttlMs`/`cacheScope`); `product/edits_mcp_shim.py` forwards to
the same local app and cleans that one key so every tool loads. Get the exact line from the engine (it fills in
the shim's absolute path and `python`/`python3` for her platform):

```bash
python3 product/edits_connect.py --token <token>
```

**Where her token comes from — her course library, never from the seller directly.** The access token lives in the **Instagram Edits Kit**
in her course hub. Give her the direct link so it's one click: **log into your course hub here:
https://www.yourbrand.com/login — you'll see the Instagram Edits Kit, and it walks you through getting your
access token** (the kit shows her the `Authorization: Bearer <token>` value). Always hand her that login link when
she needs the token — never "ask the seller" or "they'll give it to you." Once she has it, run the
command above to print the ready line, and have her paste it into a terminal. After that, the phrase alone switches
everything on and the engine opens the app itself. To disconnect later: `python3 product/edits_connect.py --remove`.

(If she has already connected Edits the OLD direct way and tools won't load, that's this exact bug: remove it
with `claude mcp remove metapilot-native --scope user`, then reconnect through the shim as above.)

**If Edits can't be opened or connected** (the launch fails, or the metapilot MCP isn't loaded in this client):
turn the kit on anyway, but tell her it's on *pending connection* — until Edits is connected, her exports fall
back to **CapCut** (medium) and her cut transcribes with **WhisperX**, exactly as before, so nothing strands
her. Once she connects it, the kit is fully live. (No route is a dead end — see the `edits-export` skill.)

## Reconnect — "my Edits tools won't load" / "reconnect it"

If she connected Edits before this version (the old direct `--transport http` way) and Claude now says the
connection isn't working / the tools won't load, it's the Claude Code 2.1.301 × Edits `tools/list` mismatch, not
her. ONE command fixes it in place, keeping her token (she re-enters nothing):

```bash
python3 product/edits_connect.py --reconnect
```

It reads the token already in her config, removes the broken server, re-adds it through
`product/edits_mcp_shim.py`, and checks that the tools load. Then say what it did in one warm line (e.g. "Fixed
it. Edits is reconnected and your tools are loading now."). If it printed a manual line instead (it couldn't
find the token), hand her that line and ask for the Edits-kit token. Never leave her on the broken connection.

## Turn it OFF — "turn off my Instagram Edits Kit"

1. `python3 product/edits_mode.py off`
2. Confirm: "Back to your normal defaults — WhisperX for the cut, CapCut for export. Your reels aren't changed."

## What the switch changes (handled by the builders, not by hand)

- **Export default**: `edits_mode.default_route()` returns `edits`, so Finish/Export defaults to the Edits app
  (medium) from every road. She can still pick another destination per reel.
- **Transcription**: `edits_mode.transcribe_engine()` returns `edits`, so the rough cut transcribes in Edits
  (lean mode) when the app is connected — the acoustic cut (`snap-to-sound`, `trim-restarts`) is unchanged, so
  it's leaner and faster but just as dialed-in. WhisperX stays the silent fallback when Edits isn't connected
  or the audio is hard.
- **Raw is never offered in Edits** (pack fonts are CapCut-native). If she wants raw with her style, that's
  CapCut; see the `edits-export` skill for the one-line explanation at the handoff.

The mode persists in `_local/edits-mode.json` (protected, never ships, survives updates). Check it any time:
`python3 product/edits_mode.py status`.
