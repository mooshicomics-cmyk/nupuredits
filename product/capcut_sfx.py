#!/usr/bin/env python3
"""capcut_sfx.py — PORTABLE, shared SFX injector for every format. Ships self-contained.

the creator's ship rule (2026-08-02): "this all needs to be baked into the system. we can't be grabbing for my
assets on another user's macbook — it won't be there." So SFX are built ONLY from repo-bundled resources:
  • sound files → `product/creative-vault/sfx/*.mp3` (bundled, license note below)
  • audio-material structure → `product/creative-vault/caption-templates/audio-template.json` (captured once)
NO dependency on any other CapCut draft or the user's CapCut cache — works on a fresh buyer's machine.

⚠️ SFX LICENSING (parallels personal fonts vs ship fonts): the bundled files are the creator's CapCut favorites,
fine for HER reels; the SHIPPED kit needs a license-clear SFX pack (or per-style-pack SFX). Swap the files
in `creative-vault/sfx/`; the engine is source-agnostic. Rotate sounds so nothing repeats (see CLEANYAP.md).
"""
import json, math, os, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copy, re, shutil, subprocess, uuid
import audio_levels   # SHARED: the one place a cue's level is decided

_HERE = os.path.dirname(os.path.abspath(__file__))
SFX_DIR = os.path.join(_HERE, "creative-vault", "sfx")
# Sounds read out of her CapCut favorites project. Lives in _local/ so an update can never remove them.
FAVORITES_DIR = os.path.join(os.path.dirname(_HERE), "_local", "sounds")
_TMPL = os.path.join(_HERE, "creative-vault", "caption-templates", "audio-template.json")
US = 1_000_000

def _nid(): return uuid.uuid4().hex
def _NID(): return str(uuid.uuid4()).upper()
def _dur_us(p):
    return int(round(float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p])) * US))

# The creator's own sfx/ folder ships EMPTY (CapCut's sounds are not redistributable). But the vendored
# HyperFrames toolkit already bundles a 21-file SFX library under the Pixabay Content License — free for
# commercial use, no attribution required — and it ALREADY ships in the buyer bundle. So a buyer is never
# without sound effects: their own folder wins, and anything it does not have falls back to that library.
_HF_SFX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".claude", "skills", "media-use", "audio", "assets", "sfx")

# Cue names used by the reel engines -> nearest face in the bundled Pixabay library.
_ALIAS = {
    "woosh": "whoosh", "pop_whoosh": "pop-whoosh", "fuwa_swipe": "fuwa-short-wind-noise-swipe-etc",
    "mouse_click": "click", "decision_click": "click", "cute_pop": "pop",
    "keyboard_typing": "typing", "cha_ching": "chime",
    "mouse-click": "click-soft",   # the library's name for the toolkit's click-soft file
}

# Stand-ins for the owner's own CapCut sounds, which never ship (licensed for use inside CapCut only). Engine
# code names a few of them (the first-reel script's takeover and count-up, two old swipe names), and on an
# engine without them those names resolved to nothing, so the cue played silent. Each falls back to the
# shipped sound that does the same job. Applied LAST and only where the name is still missing: wherever the
# real file is present (her own engine, or a buyer who added it), the real file wins.
_STAND_INS = {
    "pop-whoosh": "whoosh", "pop_whoosh": "whoosh",                  # a takeover landing
    "coin-earn": "coin-drops",                                       # a count-up landing (public-domain)
    "fuwa_swipe": "quick-wind", "fuwa-short-wind-noise-swipe-etc": "quick-wind",   # a soft swipe
}

def _scan(d):
    """Stem -> file path, for every audio file under d — RECURSIVE, so a subfolder (e.g. the
    approved/ pool, organized under sfx/approved/ rather than dumped flat) is actually
    discoverable. A file sitting in a subfolder that palette() never looks inside is a file the
    engine cannot use, which is worse than not having it."""
    if not os.path.isdir(d):
        return {}
    out = {}
    for root, _dirs, files in os.walk(d):
        for f in files:
            if f.lower().endswith((".mp3", ".wav", ".m4a")):
                out[os.path.splitext(f)[0]] = os.path.join(root, f)
    return out

_INDEX = os.path.join(_HERE, "creative-vault", "sfx", "sfx-index.json")

def _index():
    """The creator's curation, or {} if the index is absent (never a hard failure)."""
    try:
        with open(_INDEX, encoding="utf-8") as f:
            return json.load(f).get("sounds", {}) or {}
    except Exception:
        return {}

def disabled():
    """Cue names the creator switched OFF by ear. A disabled cue must never be CHOSEN.

    This lived only in the sound skill's prose, which meant nothing enforced it: a cue could come
    back through the _ALIAS fallback or a stale plan and the creator would hear a sound she had
    already rejected. It is checked here so the rule survives whoever is doing the picking."""
    return {k for k, v in _index().items() if v.get("enabled") is False}

def is_enabled(name):
    return name not in disabled()

def selectable(pal=None):
    """palette() minus the disabled cues — THE set to pick from. Use this for any sound SELECTION;
    `palette()` stays complete so an existing plan naming a retired cue still resolves (loudly)
    instead of silently losing its audio."""
    off = disabled()
    return {k: v for k, v in (pal or palette()).items() if k not in off}

def palette():
    """Name stem -> file path. Layered so a cue always resolves to SOMETHING:
    1. the bundled Pixabay library (ships, free for commercial use)
    2. its aliases, so engine cue names (woosh, decision_click, ...) resolve to a real file
    3. the creator's/buyer's own product/creative-vault/sfx/ — always wins where present."""
    hf = _scan(_HF_SFX)
    pal = dict(hf)
    for cue, target in _ALIAS.items():
        if cue not in pal and target in hf:
            pal[cue] = hf[target]
    pal.update(_scan(SFX_DIR))          # the buyer's own files override the fallback
    pal.update(_scan(FAVORITES_DIR))    # her favorites project (product/favorites.py) outranks everything
    for cue, target in _STAND_INS.items():
        if cue not in pal and target in pal:
            pal[cue] = pal[target]
    return pal

def resolve_cue(name, pal=None):
    """A cue name is EITHER a bundled/vault stem OR a direct path to an audio file.
    Direct paths let a per-reel library (e.g. an Epidemic pull for one job) be placed without
    polluting the reusable vault in creative-vault/sfx. Returns (src_path, stem, ext) or None."""
    if pal is None:
        pal = palette()
    if name in pal:
        if not is_enabled(name):
            # resolve it anyway (a stale plan should not lose its audio silently) but never quietly
            print(f"  ! cue '{name}' was switched off by the creator — placing it because the plan "
                  f"asks for it by name. Pick from capcut_sfx.selectable() to avoid this.")
        src = pal[name]
        return src, name, os.path.splitext(src)[1].lower() or ".mp3"
    if os.path.isfile(name):
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(os.path.basename(name))[0])
        return name, stem, os.path.splitext(name)[1].lower() or ".mp3"
    return None


def _token(d):
    """The draft's path placeholder token — read from an existing media material (per-draft, portable)."""
    for cat in ("videos", "audios", "images"):
        for m in d.get("materials", {}).get(cat, []) or []:
            mm = re.search(r'placeholder_([0-9A-Fa-f-]+)_', str(m.get("path", "")))
            if mm:
                return mm.group(1)
    return None

# How close two cues may land, per the density she has taught. "Lighter" does not mean quieter — it means
# FEWER: a wider gap drops the cues that were stacking up, so the ones that survive are the ones that land
# on a real beat. This is the mechanical half of "keep the sound effects lighter".
_DENSITY_GAP = {"lighter": 0.55, "normal": 0.16, "heavier": 0.08}


def plan_sfx(placements, onsets=None, alternates=None, snap_window=0.18, min_gap=None):
    """Enforce the two things the sound pass keeps UNDER-delivering, mechanically so prose can't skip them:
    ON-BEAT landing and NO back-to-back repeats. Pure list -> list; call it right before add_sfx.

    The creator's exact complaints this fixes: cues that were "just dropped in, not on a beat of emphasis"
    and "the same effect over and over with not enough variation." Selecting varied sounds is still the
    sound pass's job (that's where the library search happens); this is the safety net that guarantees the
    result actually lands on the beat and never stutters the same file twice in a row.

    - placements: [(name, start, trim, volume), ...] the pass proposed (any order; sorted here by start).
    - onsets:     sorted word-onset times in TIMELINE seconds (words.json mapped through the cut list). Each
                  cue's start snaps to the nearest onset within snap_window; farther than that, it stays put
                  (better slightly off than yanked onto the wrong word). None = no snapping.
    - alternates: optional {name: [interchangeable names]} of SAME-ROLE sounds (e.g. two different whooshes).
                  When a cue would repeat the previous cue's file back-to-back, it rotates to an alternate.
                  Without an alternate for that name, the repeat is LEFT (never silently wrong) and counted.
    - min_gap:    drop a cue landing within this of the previous KEPT cue, so stacked hits don't turn to mush.
                  None (the default) takes it from the density she has TAUGHT (`/learn sfx.density
                  lighter|normal|heavier`), else 0.16. Pass a number to pin it for one reel.

    Returns (cleaned_placements, notes) where notes = {"snapped": n, "rotated": n, "dropped": n,
    "unresolved_repeats": n} for a one-line build log."""
    alternates = alternates or {}
    if min_gap is None:                      # caller did not pin it -> use the density she taught
        try:
            import learned
            min_gap = _DENSITY_GAP.get(learned.get("sfx.density", "normal"), 0.16)
        except Exception:
            min_gap = 0.16
    ps = sorted(placements, key=lambda p: p[1])
    snapped = rotated = dropped = unresolved = 0
    out = []
    for name, start, trim, vol in ps:
        # 1) snap to the nearest emphasis onset within the window
        if onsets:
            near = min(onsets, key=lambda o: abs(o - start))
            if abs(near - start) <= snap_window and abs(near - start) > 1e-6:
                start = near
                snapped += 1
        # 2) declutter: too close on top of the last kept cue
        if out and abs(start - out[-1][1]) < min_gap:
            dropped += 1
            continue
        # 3) no identical file twice in a row — rotate to a same-role alternate when one exists
        if out and name == out[-1][0]:
            alt = next((a for a in alternates.get(name, []) if a != name), None)
            if alt:
                name = alt
                rotated += 1
            else:
                unresolved += 1
        out.append((name, start, trim, vol))
    return out, {"snapped": snapped, "rotated": rotated, "dropped": dropped,
                 "unresolved_repeats": unresolved}


def add_sfx(d, draft_dir, placements, programme=None, keep_existing=False):
    """Add SFX from BUNDLED resources only. placements = list of (name, start_seconds, trim_seconds, volume);
    `name` is a bundled file stem (e.g. 'mouse_click'). Copies each needed file into the draft's
    assets/audio, clones the bundled audio template per hit, and puts all of them on ONE new audio track.
    Idempotent: replaces prior 'sfx_' audio. Returns count placed. Portable — no other-draft / cache dependency.

    keep_existing=True is the ADDITIVE case, for a draft she already has: nothing already in the draft is
    removed (every earlier 'sfx_' sound stays where it is), and a new sound file never takes the file name of a
    different one already in the draft. Without it (the default every builder relies on), a rebuild replaces
    the 'sfx_' sounds an earlier pass placed instead of doubling them.

    LEVEL: pass `volume=None` on a placement (recommended) to AUTO-LEVEL it via the shared `audio_levels`
    module — the bundled SFX span ~20 dB of intrinsic level, so a hand-picked multiplier makes one cue slap
    and another inaudible. `programme` = path to the cut, so cues can be placed under the real voice level;
    without it they still normalise to a canonical peak, which alone removes the spread. An explicit numeric
    volume is always honoured."""
    tmpl = json.load(open(_TMPL, encoding="utf-8"))
    pal = palette()
    token = _token(d)
    aud_dir = os.path.join(draft_dir, "assets", "audio")
    os.makedirs(aud_dir, exist_ok=True)

    # idempotent: strip only OUR prior sfx (material name starts 'sfx_'); leave any music bed intact
    if not keep_existing:
        sfx_ids = {m["id"] for m in d["materials"].get("audios", []) if str(m.get("name", "")).startswith("sfx_")}
        for t in [t for t in d["tracks"] if t["type"] == "audio"]:
            t["segments"] = [s for s in t["segments"] if s.get("material_id") not in sfx_ids]
        d["materials"]["audios"] = [m for m in d["materials"].get("audios", []) if m["id"] not in sfx_ids]
        d["tracks"] = [t for t in d["tracks"] if not (t["type"] == "audio" and not t["segments"])]
    for cat in ("audios", "speeds", "placeholder_infos", "sound_channel_mappings", "vocal_separations"):
        d["materials"].setdefault(cat, [])

    # A MISSING SOUND MUST NOT KILL THE BUILD. The sfx folder ships EMPTY on purpose (CapCut's sounds are
    # not redistributable — see ASSETS-INSTALL.md), so a buyer who has not added sounds yet would otherwise
    # lose an entire finished reel over an optional asset they were never told was required first. Skip the
    # cue, say exactly how to fix it, and finish the reel.
    _res = {n: resolve_cue(n, pal) for n in {p[0] for p in placements}}
    missing = sorted(n for n, r in _res.items() if r is None)
    if missing:
        print(f"[sfx] skipping {len(missing)} cue(s) with no sound file: {', '.join(missing)}")
        if not pal:
            print(f"[sfx] no sound effects installed yet. Drop .mp3 files into {SFX_DIR} and rebuild to get them.")
        placements = [p for p in placements if _res.get(p[0])]
        if not placements:
            print("[sfx] no cues left to place — finishing the reel without sound effects.")
            return 0

    file_dur, _fname, _fsrc = {}, {}, {}
    for name in {p[0] for p in placements}:
        src, stem, ext = _res[name]
        fn = f"sfx_{stem}{ext}"
        if keep_existing:        # an sfx_ file already in the draft plays for a cue that stays: never overwrite it
            import filecmp
            n = 2
            while (os.path.exists(os.path.join(aud_dir, fn))
                   and not filecmp.cmp(src, os.path.join(aud_dir, fn), shallow=False)):
                fn = f"sfx_{stem}_{n}{ext}"
                n += 1
        _fname[name] = fn; _fsrc[name] = src
        shutil.copyfile(src, os.path.join(aud_dir, fn))
        file_dur[name] = _dur_us(os.path.join(aud_dir, fn))

    track = {"type": "audio", "attribute": 0, "flag": 0, "id": _NID(),
             "is_default_name": True, "name": "", "segments": []}
    _ppeak = audio_levels.peak_dbfs(programme) if programme else None
    _rows = []
    for name, start, trim, vol in placements:
        fn = _fname[name]
        if vol is None:                      # AUTO: measure this cue, place it under the programme
            vol = audio_levels.sfx_volume_for(_fsrc[name], programme, trim)   # the north star: under her voice
            _rows.append({"file": _fsrc[name], "gain_db": 20 * math.log10(max(vol, 1e-6)), "how": "auto"})
        else:
            _rows.append({"file": _fsrc[name], "gain_db": 20 * math.log10(max(float(vol), 1e-6)), "how": "manual"})
        m = copy.deepcopy(tmpl["material"]); mid = _nid()
        m["id"] = mid; m["unique_id"] = ""; m["music_id"] = mid; m["local_material_id"] = mid
        m["name"] = fn
        # VectCutAPI drafts (cleanyap/superyap, current engine) carry no placeholder token (_token -> None);
        # use the ABSOLUTE path into the draft's assets dir. Legacy template drafts keep the token form.
        # (Same VectCutAPI-vs-placeholder fix as build-overlay.py — shared module, so it lands everywhere.)
        m["path"] = (f"##_draftpath_placeholder_{token}_##/assets/audio/{fn}" if token
                     else os.path.join(draft_dir, "assets", "audio", fn))
        m["duration"] = file_dur[name]; m["wave_points"] = []
        d["materials"]["audios"].append(m)
        refs = []
        for h in tmpl["helpers"]:
            hm = copy.deepcopy(h["material"])
            hm["id"] = _NID() if "-" in h["material"]["id"] else _nid()
            d["materials"].setdefault(h["category"], []).append(hm); refs.append(hm["id"])
        s = copy.deepcopy(tmpl["segment"]); s["id"] = _NID(); s["material_id"] = mid
        s["extra_material_refs"] = refs
        tu = min(int(trim * US), file_dur[name])
        s["source_timerange"] = {"start": 0, "duration": tu}
        s["target_timerange"] = {"start": int(start * US), "duration": tu}
        s["volume"] = vol; s["last_nonzero_volume"] = vol
        s["common_keyframes"] = []; s["keyframe_refs"] = []
        track["segments"].append(s)
    d["tracks"].append(track)
    audio_levels.report(_rows, programme_peak_db=_ppeak, prefix="[sfx]")
    return len(placements)


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────────
# Why this exists: the sound pass used to FIND the library by globbing "product/creative-vault/sfx/" as a
# relative path. On one real build a long run of directory changes had left the working directory three
# folders deeper than the engine root, every glob came back with nothing, and the reel was handed over
# silent with "no sound effects available" — while 239 files sat exactly where they were supposed to be.
# Nothing about the library was wrong; the question was asked from the wrong place. palette() has always
# resolved from this file's own location, so it cannot be asked from the wrong place. This makes that
# answer available from a shell, from any directory, so nothing has to glob for sound again.
#
#   python3 product/capcut_sfx.py --list            every cue name the engine can play, one per line
#   python3 product/capcut_sfx.py --list --paths    cue name and the file it resolves to
#   python3 product/capcut_sfx.py --list --json     the whole map, for a script
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("--list", "-l"):
        print(__doc__.strip().split("\n")[0])
        print("\nUsage: capcut_sfx.py --list [--paths | --json]")
        sys.exit(0 if not args else 2)
    pal = palette()
    if not pal:
        # The bundled libraries ship with the engine, so an empty answer here is a real fault worth naming
        # loudly — unlike a zero from a glob, which only ever meant somebody asked from the wrong folder.
        print("NO SOUNDS FOUND. Both bundled libraries are missing from this install:", file=sys.stderr)
        print(f"  {SFX_DIR}", file=sys.stderr)
        print(f"  {_HF_SFX}", file=sys.stderr)
        print("Re-download the engine zip, or say \"/report-a-problem\".", file=sys.stderr)
        sys.exit(1)
    if "--json" in args:
        print(json.dumps(pal, indent=2, sort_keys=True))
    elif "--paths" in args:
        for k in sorted(pal):
            print(f"{k}\t{pal[k]}")
    else:
        for k in sorted(pal):
            print(k)
