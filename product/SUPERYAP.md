# SUPERYAP.md — building a teaching (loaded) Yap

> The **loaded** yap. Engine: `superyap.py` (raw CapCut text). Spec: `superyap.json`. Clean Yap counterpart:
> `CLEANYAP.md` (its locked defaults, text-injection contract and magnet rules apply here too and are not
> repeated). "Super Yap" is an internal name: to her it is just a **Yap**, built loaded because the register
> is **teaching**. Ask the animation style up front (`CLAUDE.md`, formats).

## First: which builder? (the doneness decides, not the format)

| Doneness | What builds it | Section |
|--|--|--|
| **raw** | a short driver that imports `superyap` (editable CapCut text) | **Raw** below |
| **medium** | `build-reel-type.py` → `separate_layers.sh` → CapCut (rendered effects on named layers) | **Medium** below |
| **well-done** | `build-reel-type.py` → `reel_render.py` → `build-reel-mp4.py`, then `capcut_handoff.py` if she wants CapCut too | `FLOW.md` |

Karaoke captions, full-screen rendered takeovers, count-up cards, stars and the breakaway card exist only in
`build-reel-type.py`. A reel that has them (every spoken-cue reel, including `FIRST-REEL-SCRIPT.md`) is
**medium or well-done**. Never hand-write a `superyap` driver for a medium reel.

Before any route: the creative plan is approved, `uv run workflows/subject-zones.py
projects/<job>/outputs/<job>.mp4` has measured her, `python3 product/favorites.py show` has been read, the
VectCut engine is running (port 9001, `SETUP.md` §1b), and CapCut is **quit**.

## Medium

1. **The caption plan.** `build-reel-type.py` reads `projects/<job>/caption-plan.json`, never
   `graphics-plan.json`. For a spoken-cue reel: `python3 product/spoken_cues.py <job>` (report), then
   `--write`. Otherwise, translate each approved beat into the keys documented at the top of
   `product/build-reel-type.py` (hook, `takeover_keys`, `caption_treatments`, `elements` with `counter` /
   `star`, `breakaways`, `sfx`, `punch`). Sounds come from `python3 product/capcut_sfx.py --list`; rotate the
   clicks (no two consecutive entrances on the same sound; the typing sound stays on the hook).
2. **Build the composition** (no render): `JOB=<job> STYLE_PACK=<Pack> python3 product/build-reel-type.py`.
3. **Beat sheet** ⏸ (`beat-sheet` skill). Nothing renders until she says it looks good.
4. **Which layers:** `./product/separate_layers.sh --list <job> <Pack>`, shown as ONE checkbox list. On
   medium, tick every layer by default (each kind of element on its own named track is what medium means), and
   give the cost in the same breath: one render per ticked layer.
5. **Render and hand over:** `./product/separate_layers.sh <job> <Pack> <ticked,layers>`. Each layer renders
   through the gated `reel_render.py`, then `capcut_handoff.py` writes the next free draft version: her cut
   on the main track, each layer on its own named track, each sound cue on its own clip. The main track comes
   in one clip per kept line (split where the rough cut joined them), so every cut is there to trim. A karaoke
   line that must land frame-exact is burned into the footage first with `product/burn_layers.py`.
6. Hand-off lines as in `CLAUDE.md` (keep it crisp, the hashtag).

Punch-in windows in the plan arrive as zoomed pieces of her cut, held on her face (plain clip zooms she
can change in CapCut). No other camera move is added on this route.

## Raw

A driver in the job folder (`projects/<job>/build.py`), run from the engine root with the venv-capcut
interpreter (`product/engine/VectCutAPI/venv-capcut/bin/python`; on Windows `...\Scripts\python.exe`). Every
number below comes from the pack, her taught preferences or her measured footage, never typed.

```python
import json, os, sys
sys.path.insert(0, "product")
import cleanyap as C, superyap as S          # C: pack fonts, sizes, SFX; S: the loaded builder
import packbuild, capcut_text, capcut_sfx, subject_place, draft_safety, stylepack

JOB, PACK = "<job>", "<Pack>"
J = os.path.abspath(f"projects/{JOB}")
C.learning_context(register="teaching", pack=PACK)   # BOTH engines: sizes from C must read teaching prefs
S.learning_context(register="teaching", pack=PACK)
zones = subject_place.load(J)                         # subject-zones.json; y_for raises if never measured
NAME = draft_safety.next_version(JOB)                 # never reuse a draft name
fonts = {}                                            # exact on-screen text -> font file, for finalize

draft_safety.require_capcut_quit(f"build {NAME}")
did = S.call("create_draft", width=S.CANVAS_W, height=S.CANVAS_H)["output"]["draft_id"]

# 1. The cut. punch = {segment index: scale}, 1.06-1.10, only on the plan's punch-in lines. finalize adds the
#    default opener zoom and jump-cut punches to every clip still at 1.0.
S.add_cut(did, json.load(open(f"{J}/transcript/cuts.json", encoding="utf-8")), f"{J}/raw", punch={})

# 2. B-roll cutaways: muted, from a good in-clip moment (src > 0), never frame 0.
# S.add_broll(did, f"{J}/broll/<clip>.mp4", at, src, dur)

# 3. Her stickers / screenshots: track name MUST start "img_" (that is what lifts it above the footage).
# S.add_png(did, f"{J}/assets/<file>.png", start, end, x, y, "img_<name>")

# 4. Hook: the pack's headline font, length-adaptive size, hard-wrapped, in the measured zone above her.
hook = "<approved hook copy>"
hf, hs = C.hook_font(PACK), C.hook_size(hook)
hook = capcut_text.wrap_text(hook, hs, hf)
S.add_text(did, hook, 0.0, 7.0, hf, hs, 0.0, subject_place.y_for(zones, role="hook"), "hook",
           intro="Random Typewriter", outro="Slide Left")
fonts[hook] = hf

# 5. Thought bubbles: the pack's thought font and case, size 12 unless taught, never across her face.
#    LANG keeps her own capitals on a reel not in English (lowercase misspells every German noun).
tf, ts, tcase = C.thought_font(PACK), C.thought_size(), packbuild.role(PACK, "thought")["case"]
LANG = stylepack.job_language(J)
for text, a, b in []:                                 # [(copy, start, end), ...] from the plan
    t = capcut_text.wrap_text(packbuild.caseit(text, tcase, LANG), ts, tf)
    S.add_text(did, t, a, b, tf, ts, 0.0, subject_place.y_for(zones, role="thought"), "thoughts",
               intro="Bounce In", outro="Fade Out")   # VectCut's names; "Text Fade" is not one of them
    fonts[t] = tf

# 6. Takeover: one sentence = one takeover, each word appears as spoken and holds to `end`, stacked and centred,
#    no animation. Word times from outputs/<job>.transcript.json. Size and step come from the pack.
tk = packbuild.role(PACK, "takeover")
for words, end in []:                                 # [([(word, t), ...], end), ...]
    words = [(packbuild.caseit(w, tk["case"], LANG), t) for w, t in words]
    S.takeover(did, words, end, tk["size"], tk["step"] or 0.17, "tk", takeover_font=tk["font_path"])
    fonts.update({w: tk["font_path"] for w, _ in words})

# 7. Sound: every text entrance gets an intro sound, exits stay silent. plan_sfx snaps to the beat and
#    rotates repeats; names from `capcut_sfx.py --list`. Overlapping cues go on track="sfx2".
#    The cues go into caption-plan.json "sfx" first, so the visual editor's Sound section lists them and her
#    swaps / offs (review/sound.json, product/sound_plan.py) reach this build; add_sound_plan places them in lanes.
cues, _ = capcut_sfx.plan_sfx([], alternates={})      # [(name, at, trim, None), ...], {name: [same-role names]}
_cp = json.load(open(f"{J}/caption-plan.json", encoding="utf-8")) if os.path.exists(f"{J}/caption-plan.json") else {}
_cp["sfx"] = [{"file": nm, "at": round(at, 3), "trim": trim} for nm, at, trim, _v in cues]
json.dump(_cp, open(f"{J}/caption-plan.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
C.add_sound_plan(did, J, programme=f"{J}/outputs/{JOB}.mp4")

# 8. Finalize: fonts, layer order, b-roll mute, magnet, wrap/span repair, subject check, register.
S.finalize(did, NAME, fonts, fallback_font=hf, job=J, pack=PACK)
```

**Rules the driver relies on:**
- **Layer order** is set in finalize from track names: footage 0 · `broll` 8000 · `img_*` 12000 · text on
  top. Time-pack: elements that never overlap share a track; never a tower of one-clip tracks, never compound
  or group.
- **Fonts** are patched by exact text (case-insensitive), so every text you add goes in `fonts`. Two
  elements with the same words get the same font: reword one or accept it.
- **Wrap:** hard-wrap every multi-word text with `capcut_text.wrap_text(text, size, font)` before adding
  it; CapCut will not wrap one long line. finalize keeps your breaks and repairs spans.
- **Placement:** every `transform_y` comes from `subject_place.y_for`. When her framing leaves no room above
  her it raises and names the usable zones; pass one (`zone="below"`), never a typed number. finalize
  moves type that lands on her face to the nearest open zone (`subject_place.auto_clear`), builds either way, and
  says what it couldn't move. A takeover covers her on purpose: only when the plan has one, run with
  `SUBJECT_ALLOW_OVERLAP=1` (nothing moved) and say so.
- **Order of work:** the beat sheet comes before this driver runs. A rebuild is a new version; never write
  into a draft she has opened (`CLAUDE.md` rule 7).
