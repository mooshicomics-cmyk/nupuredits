---
name: edits-export
description: >-
  Send a finished visual-editor reel to Instagram's Edits app as a MEDIUM build (her cut as the footage, every
  look on top as its own movable layer), the same way the engine hands off to CapCut and DaVinci Resolve. Use
  when the chosen Finish destination is the Edits app, or when she says "export to edits", "put it in edits",
  "open it in the edits app", "send this to edits", "finish in edits", or picks "Edits app" on the Finish tab.
  Also handles the raw-vs-medium question for Edits: Edits is medium only, because the style packs use
  CapCut-native fonts; this skill explains that at the handoff. The Edits app must be running.
---

# Edits-app export (MEDIUM)

Edits is a destination, exactly like CapCut and Resolve. The engine's brain still did the cut and the looks;
this skill lands them in the Edits app. **Medium only.** Her cut becomes the footage on the main track, and
each look rides on top as its own movable, hideable layer.

## Why medium, not raw (say this if she asks for raw in Edits)

The style packs were authored for CapCut's fonts. Their exact look only survives when it is **rendered** and
carried in as a layer (medium). A **raw** (native, retypeable) export in Edits would drop the pack styling,
because Edits types with Edits' own fonts. So:

> "I'll send this to Edits as **medium** so your look holds. A **raw** version there would lose your pack
> styling, because those fonts are CapCut's. If you want raw with your style, use CapCut. For a raw build
> that's styled *in Edits*, you'd build a style pack around fonts native to the Edits app."

Keep it to that trade-off (style preservation vs. editability). Don't turn it into a lesson. Raw in Resolve
is off for the same reason.

## If Edits can't be reached — fall back, NEVER a dead end

The engine's law: **no route is a dead end** — the reel always lands somewhere editable. Before driving,
confirm the Edits app is reachable: run `product/edits_open.py`, then poll the metapilot `appState` tool until
it answers. If it does NOT answer (the Edits MCP isn't loaded in this Claude Code client, the app won't open,
or `appState`/the editor tools keep failing after one retry), do NOT leave the reel un-exported:

1. Fall back to **CapCut, medium** — the same designed look, every look its own named layer:
   `python3 product/finish.py run <job> capcut` (editor road), or the chat CapCut medium handoff
   (`product/capcut_handoff.py`).
2. Say it once, plainly: "The Edits app isn't connected here, so I put your reel in **CapCut** instead — same
   medium look, every layer yours. To connect Edits, log into your course hub here:
   **https://www.yourbrand.com/login** and open the **Instagram Edits Kit** (that's where your access token
   is, and it walks you through connecting). Then say *export to edits* and
   I'll send it there." The token comes from her course library, never from the seller — point her there, don't ask her for it.

**If Edits IS connected but its tools won't load** (`claude mcp list` shows metapilot-native "Connected · tools
fetch failed"), it's the Claude Code 2.1.301 × Edits `tools/list` mismatch: she connected the old direct way.
`claude mcp remove metapilot-native --scope user`, then reconnect through the shim with
`python3 product/edits_connect.py --token <token>` (see the `edits-kit` skill). The shim cleans the response so
the tools load. Until then the CapCut fallback above keeps her unblocked.

This is the Edits kit's readiness rule: a missing or unloadable Edits MCP degrades to CapCut; it never strands
her. Under the **Instagram Edits Kit default** the same holds — if the kit is on but Edits isn't connected,
export falls back to CapCut and transcription to WhisperX, each said once.

## Step 1 — prep (deterministic)

**Already staged by the editor?** If the agent's todo shows **`[edits-drive]`** (the creator pressed Export → Edits
on the Finish tab, so `finish.py` already staged it and dropped `projects/<job>/outputs/edits/drive-pending.json`),
SKIP this prep — the manifest already exists. Go straight to Step 2 with it, and in Step 3 delete the marker so
the todo clears. Only run the prep below for a standalone/chat export where nothing is staged yet.

Run the finish route; it renders the looks (shared with the other routes), stages the media where the
sandboxed app can read it, and writes the build manifest:

```bash
python3 product/finish.py run <job> edits
```

(Standalone / the **widget (chat) road**: `python3 product/edits_handoff.py <job>` — it auto-detects the road:
her page's looks on the editor road (`review/looks.json`), or on the widget road the same transparent graphics
overlay CapCut lays over the footage (newest `renders/*.mov`) as one Edits layer, with `outputs/<job>.mp4` as
the cut. The widget road doesn't go through `finish.py`, so use this standalone call for it.)

Then read `projects/<job>/outputs/edits/manifest.json`. It is the contract for the drive:
`base.media` (the staged cut), `base.cut` (false = one pre-cut clip), `overlays[]`
(`{name, path, startSeconds, x, y, scale, durationSeconds, endSeconds}`), `cut_total`, `project_name`.

## Step 2 — drive the Edits app (metapilot-native MCP)

The Edits app can't import a project file (its `.mcomp` is off in public MCP mode), so build it live. **The app
is a single shared instance and the MCP can drop its editor tools on reconnect — verify the active project
(`state`/`clips`: duration ≈ cut_total) before every mutation.**

1. `newProject` → note the project id. **Then set the frame to match the cut:** if the manifest `aspect` is
   `16:9` (a horizontal / YouTube cut), `setAspectRatio` to 16:9 BEFORE importing — Edits projects default to
   9:16, so a horizontal cut would otherwise letterbox or crop. For `9:16` leave the default.
2. `importMedia(base.media)` → the cut, one clip on the main track. Confirm `state.duration` ≈ `cut_total`.
3. **If `base.cut` is false (the normal editor case): no cutting** — the clip is already the finished cut.
   (Only when `base.cut` is true do you `splitAt(clipId, base.splits)` then ripple-delete the pieces whose
   start matches `base.drops`.)
4. For each `overlay`, in order (captions stack last, on top):
   `addOverlay(path, startSeconds, x, y, scale)` → the look as its own layer.
   If `endSeconds > cut_total` (a look's tail runs past the footage), `trim(id, side="right",
   deltaSeconds = endSeconds - cut_total)` so it ends flush.
5. `renameProject(id, project_name)`, then `saveProject`.

The overlays are full-canvas 1080×1920 with alpha, so `x=0.5, y=0.5, scale=1.0` (centre, full size) — no
transform. Ripple tier 1 is on by default; leave it.

## Step 3 — verify + hand back

`captureFrame(times="...")` at one or two look moments to confirm the layers composite (don't drive the UI or
over-verify beyond that). Then tell her plainly: it's in the Edits app as `<project_name>`, medium, with N
movable look layers, open it and press play. Say once, if a look sits near her face: "Let me know if anything
feels too close to your face, or if you'd like a layer moved" — each look is its own layer, so it's a one-call
nudge.

**Clear the drive marker** so her Finish tab/todo stops asking: `rm -f projects/<job>/outputs/edits/drive-pending.json`.
Her Finish tab already shows the CapCut-style handoff (the project named, **Open the Edits app** — not a folder);
you don't post a separate "it's in Edits" card on the page for an editor-road export, just the chat line above.

## After the handoff — offer to make Edits her default (first times only)

Once the reel is in the Edits app, check `python3 product/edits_mode.py should-offer` (prints `yes` only when
the **Instagram Edits Kit** is NOT already her default AND she hasn't said no before; the editor road also
flags this as `offer_default` on the Finish result). On `yes`, after you've told her the reel is in Edits, ask
ONE clean pick-one, warm and short, in her words:

> "Want me to make the Edits app your default? I'll turn on your Instagram Edits Kit so every reel goes
> straight here, and your edits run even faster next time."

- **Yes, make it my default** → `python3 product/edits_mode.py on`, then say it's on in one line (every export
  and the rough cut now default to Edits, WhisperX/CapCut still the backup).
- **Not sure, ask me next time** → do nothing; the offer simply comes back after her next Edits export.
- **No thanks** → `python3 product/edits_mode.py decline` (it won't ask again; she can still turn the kit on by
  name any time).

Never ask when `should-offer` prints `no`. Never ask twice in one handoff. This is the only pitch the engine
makes here; keep it to the one pick-one.

## Gotchas (seen live)

- **Sandbox**: the app only reads staged paths (manifest `staging_dir`, under `~/Movies`). Never pass a job-
  folder path straight to `importMedia`/`addOverlay`.
- **Flaky MCP / shared app**: the active project can switch on reconnect; re-`openProject`(the project id) and
  re-check `state` before any destructive call. Never cut or delete on a project whose duration isn't `cut_total`.
- **Caption font** on styled captions is the look's own (rendered in). Don't add native `generateCaptions` on
  top of a medium build — the karaoke look already carries the captions.
