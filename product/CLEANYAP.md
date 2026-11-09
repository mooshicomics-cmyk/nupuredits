# CLEANYAP.md — the Clean Yap format

> The **trimmed-back** yap. Separate lane from Super Yap (`superyap.py`, loaded). Engine: `cleanyap.py`.
> Machine spec: `cleanyap.json`. There is no ready-made per-reel driver to copy: `cleanyap.py` is a library
> with no command-line entry point, so each reel gets a short driver that calls its functions (see **Run**).
>
> **Naming note:** "Clean Yap" / "Super Yap" are INTERNAL treatment names only — the engine picks between
> them automatically off the video's register (confessional → clean, teaching → super). The creator-facing
> format is just **"Yap"**; they never choose a tier.

A **Clean Yap** = the locked rough cut, full-screen 9:16, + **one hook** + **thought bubbles** (the pack's thought font)
+ **matched SFX**. Everything stays individually editable in CapCut. **Nothing loaded** — no full-screen
takeover, no doodle stickers, no b-roll bursts, no stat cards, no closing/summary card. Two registers:
**confessional** (almost no graphics) or **teaching** (a little more). Captions are native CapCut Auto
Captions, run in-app by the creator.

## Locked defaults

**Cut** — the locked rough cut, full-screen. Add **jump cuts**: gentle scale push-ins (1.06–1.08) on
accent beats for rhythm. Confessional stays calmer; still add a few.

**Hook** — the pack's hook font, white, at the top in the measured open zone above her (see **Placement**),
lowercase/title, **never all caps, no em dash**.
Intro = **Random Typewriter** (type-on **1.0–1.5s**, default **1.25s**) → outro Slide Left.
🛑 **HOLD the hook** — do NOT drop it too early. Keep it up through the opening beats (~5–7s).

**Thought bubbles** — the pack's thought font, white, size 12. **ABOVE her head, in the measured open zone
(see Placement), never across her face.** **Tight line spacing** (`line_spacing = -0.15`; the engine default
0.02 reads too loose); finalize gives it to any text set in the pack's thought font, and a spacing she taught
with `/learn` wins. Intro Bounce In (stand-in for her Cheeky Bounce, she swaps in-app) → outro **Text Fade**, a
silent fade. Content is deep
and in-voice; any scripture must be **biblically accurate** (she vets). A **front engagement bubble**
(e.g. `what would you call this?`) near the top pulls viewer comments.

**SFX** — **from the engine's own sound library ONLY**: `python3 product/capcut_sfx.py --list` names every cue
it can play (`--paths` for the files): her favorites first, then her own `sfx/` folder, then the bundled set.
Never a CapCut cache hash (it exists only on the machine it came from) and never a glob. Non-cartoon unless she
asks (no glitter/pop). Sound matches motion — trim to the exact animation length. **Each text gets an intro
sound; the exits stay silent** (a bubble fades out with no sound; a soft woosh is a rare accent, never on every
exit). Typewriter on the hook, click/decision on bubble entrances.
- **🔁 VARY the entrance sounds — LOCKED (ship rule, the creator): never the same click on every bubble.**
  Rotate across her click palette (**Mouse Click · Decision Click · Pop**, etc.) so no two consecutive
  entrances share a sound and no single sound repeats mechanically down the reel. Redundant identical clicks
  read cheap. Keyboard Typing stays reserved for the hook. This applies to the shippable engine too — the
  SFX builder must rotate, not repeat.

**Captions** — native Auto Captions, Bold Text-Popup + keyword highlight, whole reel. Never injected.

**Layers** — footage 0 · baked emoji (img_) 12000 · text 15000.

**Placement** — where anything sits around her is MEASURED, never typed and never copied from another reel:
`uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4` measures her, then
`subject_place.y_for(subject_place.load("projects/<job>"), role="hook")` (or `role="thought"`) hands back the
`transform_y` for the open zone above her. `finalize` moves type that lands on her face to the nearest open zone,
then builds either way and says what it couldn't move.

## Text-injection contract — LOCKED (prevents shipped corruption)

Every builder that injects a CapCut text element by cloning the captured shell
(`creative-vault/caption-templates/text-templates.json`) MUST do BOTH of these, or text ships broken.
Applies to `build-captions.py`, `build-graphics.py`, `patch-an example reel.py`, and any future text
builder. (Regression found 2026-08-02 — hook + thoughts rendered with the font/size/color switching
mid-line and running off the frame. Root-caused + fixed in all of the above + the template itself.)

1. **Collapse to ONE style span.** The shell's `content.styles` can carry MULTIPLE ranges (a real
   caption has per-word color/size). If you only rewrite `styles[0]` and set its range to `[0, len(text)]`
   but leave `styles[1..]`, those stale ranges (e.g. `[13,26]`, `[26,39]`) land *inside* your new text and
   override its size/color mid-line. **Always** `c["styles"] = [styles[0]]` after setting the one span.
   Symptom if skipped: "half the line is a different font/color and switches." (Short one-word captions
   hide it — the stale ranges fall past the end of the text — so it only shows on real sentences.)
   The one deliberate exception comes after the collapse: finalize gives Greek / Cyrillic / accented letters
   the pack font lacks a span of their own in the bundled companion face (`script_fonts.capcut_companions`),
   contiguous and same-styled, ranges in UTF-16 units as CapCut counts them. Never collapse those back.

2. **9:16 wrap — HARD-wrap long text with `\n`; CapCut will NOT auto-wrap a single long line.**
   Instagram reel = 1080×1920. `line_max_width`/`fixed_width` alone do **not** break a one-line string
   (that's why the hook ran off frame). The shipped-correct an example reel draft carries manual `\n` breaks
   (`the quiet pull\nno one talks about`). So insert hard breaks via `capcut_text.wrap_text(text, size)`
   (calibrated: ~18 chars/line at size 17, inverse-scaled), AND set the box config:
   ```
   m["fixed_width"] = -1.0            # NEVER a positive px value (forces an oversized box → off frame)
   m["line_max_width"] = 0.82         # 82% frame-width backstop
   m["force_apply_line_max_width"] = False
   ```
   **Sizes + line height — the creator's dialed-in values (2026-08-02), baked into `cleanyap.py`:**
   - **Hook = length-adaptive** via `cleanyap.hook_size(text)` so it wraps to ≤3 lines: ≤20 chars→17,
     ≤40→16, ≤64→**14**, else 13 (she sized a 59-char POV hook to 14). Never a fixed 17 for a long hook.
   - **Thought bubbles in the pack's thought font, size 12** (`SIZE_THOUGHT=12` — 15 read oversized) with **line height
     `LINE_SPACING_THOUGHT = -0.15`** (`thought_size()` / `thought_line_spacing()`: a value she taught wins).
   - Wrap is **balanced** (`capcut_text.wrap_text`) — fewest lines, evened, no lonely one-word last line.

3. **Accent = the CLIENT's color, never hardcoded butter.** Ship builders resolve the emphasis/accent
   color via `packbuild.accent_color(pack)` (per-pack, creator-set; falls back to **white**, never a yellow).
   the creator's butter `#FFFFC2` is passed explicitly on HER own reels only. **If a highlight can't be applied
   cleanly, default to WHITE** — `sanitize_draft_text` collapses corrupt spans to one WHITE span.

Both guards are SHARED and run in EVERY engine's finalize (`cleanyap.py`, `superyap.py`, future VO), never
per-format copies: `capcut_text.sanitize_draft_text(d)` (spans + wrap + white fallback) and
`capcut_ripple.enforce_maintrack_ripple(d)` (magnet). New injectors: build text via
`capcut_text.make_text_material()` so it's born correct. The shell in `text-templates.json` is normalized
to a single span + wrap config, and `capture-templates.py` re-normalizes on re-derivation — but the rules
above are the guarantee.

## Main-track ripple (the "magnet") — REQUIRED on every format

> **🔑 THE ACTUAL RIPPLE FIX: quit CapCut before every draft write, and build in ONE pass.**
> The magnet FLAGS below were always correct — they were never the problem. What broke those ~5 reels was
> writing to a draft while CapCut was OPEN: CapCut's next save overwrote the file and the engine's tracks were
> silently gone, which LOOKED like "they don't ripple". A creator-run magnet test on v1.7 confirmed
> engine-injected tracks DO ripple with the main track when written with CapCut quit. So: cut + text + SFX +
> anim in ONE coherent build (ref `product/superyap.py`), hand off once, and QUIT CapCut before any later
> write (every writer enforces it). See capcut ripple needs one pass build,
> capcut quit before any draft write. The flags below are still enforced as the floor.

Native CapCut ripples the overlays/SFX when you edit the main track (delete/trim → everything after
shifts, overlays follow). Our builds **must** match that. ONE shared enforcement —
**`product/capcut_ripple.py` → `enforce_maintrack_ripple(d)`** — called by every build path
(`cleanyap.py` + `superyap.py` finalize, `patch-ripple-snap.py`, `build-overlay/sfx/music/captions/graphics.py`):

```
d["free_render_index_mode_on"] = False   # linked render mode
d["config"]["maintrack_adsorb"] = True   # the magnet
d["config"]["use_float_render"] = False  # never free-float render
# ANCHOR RULE: main footage track is_default_name=False (keeps identity = the adsorb anchor);
#   EVERY non-main track (video overlays, text, b-roll, AND audio) is_default_name=True (floats +
#   adsorbs). Call LAST in finalize, AFTER per-track render_index is set (z-order is on the segment).
```

> ⚠️ **THE ANCHOR (root-caused 2026-08-12 — magnet silently dead on a real cut).** All the flags above can
> be set correctly and the magnet STILL does nothing if the MAIN footage track is `is_default_name=True`.
> `True` = an auto-named, identity-less floating track. If the main track floats, there is no anchor to
> adsorb TO and nothing ripples. Native CapCut cuts where the magnet works have **main = `is_default_name`
> False, overlays = True**. This is SEPARATE from the one-pass-build fix (build order was already right).
> `capcut_ripple.verify_maintrack_anchor(d)` is the fail-safe — both engines RAISE on a broken anchor so it
> can never ship silently again; regression test `product/tests/test_maintrack_anchor.py`; ship-gate §12.

⚠️ **Hardened 2026-08-02 (the creator, after forcing it 3×): magnet ALL tracks, not just audio.** The old code
default-named only audio, so custom-named VIDEO/TEXT/B-ROLL overlays never adsorbed. Now every non-main
track does. Do NOT re-add inline audio-only snippets — always call the shared fn.

## Workflow rules

- **Lock the cut FIRST**, then dress with overlays/SFX (they're added after the cut is final).
- **NEVER compound or group clips** (destroys her per-layer editability).
- **NEVER rebuild over her live CapCut edits.** If she re-trims after dressing, re-read the live draft
  and re-align overlays — or rebuild only when she okays a reset.
- Build with the venv-capcut interpreter: `product/engine/VectCutAPI/venv-capcut/bin/python` on a Mac,
  `product\engine\VectCutAPI\venv-capcut\Scripts\python.exe` on Windows (a venv puts it in `Scripts\` there,
  not `bin/`). **CapCut must be quit before finalize**.

## Run

There is no example driver in this folder to copy, by design. Write a short driver for the reel in its
own job folder (for example `projects/<job>/build.py`) that imports `cleanyap` and calls, in this order:

1. `call("create_draft", name=..., width=CANVAS_W, height=CANVAS_H)` (the module's own canvas: a wide job's is wide), then `add_cut(did, cuts, rawdir)` to lay the locked cut.
2. `add_text(...)` and `add_png(...)` for the overlays in the graphics plan. Name the hook's track `hook` (a second hook line `subhead`, an eyebrow `eyebrow`): trial reels (`product/trial_reels.py`) find the hook by its track name to build a trial with only its words changed. (A Clean Yap builds as `confessional` for her saved preferences unless the job's `caption-plan.json` says otherwise; a driver that knows better calls `cleanyap.learning_context(register="teaching")` first.)
3. The sounds: write the cues into `caption-plan.json` `"sfx"` (`{"file": <name from `python3 product/capcut_sfx.py --list`>, "at": <cut seconds>, "trim": <motion length>}`, after `capcut_sfx.plan_sfx`), then `add_sound_plan(did, job)` places them. That is what lets her switch a sound off or swap it in the visual editor's Sound section (`product/sound_plan.py`) and have the next build honor it. (`add_sfx(did, path, at, dur)` still places one sound by hand; a hand loop never sees her edits.)
4. `finalize(did, name, font_map, pack=<the reel's pack>)` with CapCut quit. (`pack` is what gives the pack's
   thought font its tight line spacing; fonts taken from `thought_font(pack)` are recognised without it.)

Run it with the venv-capcut interpreter for this machine (see the line above), from the engine root.

A **teaching** (loaded) Yap, or any medium reel with rendered effects, follows `product/SUPERYAP.md` instead.
