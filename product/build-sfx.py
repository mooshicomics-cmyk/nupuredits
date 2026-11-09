#!/usr/bin/env python3
"""build-sfx.py — INJECT the matched SFX pass into the migrated CapCut draft (confessional = light touch).
Her approved CapCut palette only, sound-matched to motion, VARIED takeovers (not repetitive). Each SFX CLIP is
named by its sound (the creator's naming rule). Audio track default-named so it ripples with the magnet. CapCut QUIT.
Job/target: CAPCUT_DRAFT env var = the draft folder to build into (required); CAPCUT_TEMPLATE env var =
the draft to borrow the audio template from (required).
NOTE: the SFX placement list (PAL/SFX below) still holds the example reel's exact timings — not yet generalized.

Plan (confessional/tender vibe):
  3.0  aside "no one ever says this"        -> Decision Click (soft)
  10.9/11.9/12.9/14.2  the 4 excuses pop in -> Mouse Click x4
  31.3 takeover "nothing touches Tuesday"   -> Fuwa Swipe   (light)
  59.7 HERO "this is the life"              -> Woosh        (deeper — the peak)
  72.3 takeover "worth choosing"            -> Decision Click (soft, resolved close)
  Ugly Dave builds -> SILENT (karaoke carries them).
"""
import json, os, glob, copy, uuid, shutil, re, subprocess, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
def _require_env(name, hint):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"[build-sfx] Set {name}=<{hint}> before running "
                 f"(e.g. {name}=MyProject python3 product/build-sfx.py). "
                 f"Refusing to silently fall back to a bundled sample reel.")
    return v

DRAFT    = _require_env("CAPCUT_DRAFT", "the CapCut draft folder to build into")     # CapCut draft to build into
TEMPLATE = _require_env("CAPCUT_TEMPLATE", "the draft to borrow the audio template from")  # draft to borrow audio template from
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
KD = f"{CAP}/{DRAFT}"; NA = f"{CAP}/{TEMPLATE}"
CACHE = (os.path.join(os.environ["LOCALAPPDATA"], "CapCut/User Data/Cache/music")
         if os.name == "nt" else
         os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/music"))
US = 1_000_000

# her palette (name -> (cache hash, full natural length µs))
PAL = {
    "Mouse Click":    ("d91f21d1c2b6ec21cf77a8d7185bdb47", 182993),
    "Decision Click": ("d7084c064481b95a03c976f57346848a", 496009),
    "Fuwa Swipe":     ("cc87eee8c1f4464dd0f467ae9347d6d8", 861995),
    "Woosh":          ("7785b04dd58d6f7a816e7d9744448ae5", 392993),
}
# placements: (sound_name, timeline_at_s, volume) — VARIED takeovers so it never feels repetitive
SFX = [
    ("Decision Click", 3.0,  0.55),
    ("Mouse Click",   10.9,  0.60), ("Mouse Click", 11.9, 0.60),
    ("Mouse Click",   12.9,  0.60), ("Mouse Click", 14.2, 0.60),
    ("Fuwa Swipe",    31.3,  0.55),
    ("Woosh",         59.7,  0.62),
    ("Decision Click",72.3,  0.55),
]

def NID(): return str(uuid.uuid4()).upper()
def nid(): return uuid.uuid4().hex

def templates_from(na):
    aud = na["materials"]["audios"][0]
    seg = next(s for t in na["tracks"] if t["type"] == "audio" for s in t["segments"])
    idx = {m["id"]: (cat, m) for cat, l in na["materials"].items() if isinstance(l, list) for m in l if isinstance(m, dict) and "id" in m}
    helpers = [idx[r] for r in seg["extra_material_refs"]]
    return aud, seg, helpers

def inject(path, na, ph, available):
    d = json.load(open(path, encoding="utf-8"))
    aud_t, seg_t, helpers = templates_from(na)
    track = {"type": "audio", "attribute": 0, "flag": 0, "id": NID(), "is_default_name": True, "name": "", "segments": []}
    injected = 0
    for name, at, vol in SFX:
        if name not in available:      # sound not in this machine's CapCut cache — skip it, don't crash
            continue
        h, dur = available[name]; fn = f"{h}.mp3"
        m = copy.deepcopy(aud_t); mid = nid()
        # SFX path must match the footage media-path SCHEME so CapCut resolves it:
        #  • old template-injection drafts → a ##_draftpath_placeholder_<UUID>_## token (ph set)
        #  • VectCutAPI drafts (cleanyap/superyap, current engine) → an ABSOLUTE path into the draft's assets/
        apath = (f"##_draftpath_placeholder_{ph}_##/assets/audio/{fn}" if ph
                 else f"{KD}/assets/audio/{fn}")
        m.update(id=mid, unique_id="", music_id=mid, local_material_id=mid, name=name,
                 path=apath, duration=dur, wave_points=[])
        d["materials"]["audios"].append(m)
        refs = []
        for cat, ht in helpers:
            hh = copy.deepcopy(ht); hh["id"] = NID() if "-" in ht["id"] else nid()
            d["materials"][cat].append(hh); refs.append(hh["id"])
        s = copy.deepcopy(seg_t); s["id"] = NID(); s["material_id"] = mid; s["extra_material_refs"] = refs
        s["source_timerange"] = {"start": 0, "duration": dur}
        s["target_timerange"] = {"start": int(at*US), "duration": dur}
        s["volume"] = vol; s["last_nonzero_volume"] = vol; s["common_keyframes"] = []; s["keyframe_refs"] = []
        track["segments"].append(s); injected += 1
    d["tracks"].append(track)
    from capcut_ripple import enforce_maintrack_ripple
    enforce_maintrack_ripple(d)                 # magnet ALL tracks (overlays/text/b-roll) + audio to main track
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return injected

if __name__ == "__main__":
    import draft_safety
    draft_safety.require_capcut_quit("layer SFX onto the draft")   # else CapCut's next save wipes it
    _ed, _why = draft_safety.edited_in_capcut(DRAFT, why=True)     # rule-7 net (warn, not block — additive)
    if _ed:
        _nv = draft_safety.next_version(draft_safety.base_of(DRAFT))
        print(f"⚠ {DRAFT!r} looks edited in CapCut since it was built ({_why}). This add is additive/safe, "
              f"but for a clean version history build to {_nv!r} instead.")
    na = json.load(open(_ds.draft_json(NA), encoding="utf-8"))
    kd = json.load(open(_ds.draft_json(KD), encoding="utf-8"))
    # footage media-path scheme: old template drafts carry a ##_draftpath_placeholder_<UUID>_## token;
    # VectCutAPI drafts (cleanyap/superyap, current engine) use ABSOLUTE paths into the draft's assets/.
    # Support both — ph is the token if present, else None (→ inject writes an absolute path into KD).
    ph = None
    for m in kd["materials"]["videos"]:
        mm = re.search(r'placeholder_([0-9A-F-]+)_', m.get("path", ""))
        if mm:
            ph = mm.group(1); break
    os.makedirs(f"{KD}/assets/audio", exist_ok=True)
    # These are CapCut-NATIVE library sounds, cached per machine at ~/.../CapCut/User Data/Cache/music.
    # Copy from the BUYER's own cache when present; a sound that isn't cached yet just means they haven't
    # used it in CapCut. Skip those gracefully — NEVER crash the whole pass (fresh installs have an empty cache).
    available = {}
    for name, (h, dur) in PAL.items():
        src = f"{CACHE}/{h}.mp3"
        if os.path.exists(src):
            shutil.copy(src, f"{KD}/assets/audio/{h}.mp3"); available[name] = (h, dur)
    missing = [n for n in PAL if n not in available]
    if missing:
        print(f"⚠ not in this machine's CapCut cache, skipping: {', '.join(missing)}")
        print("  these are CapCut's own sounds — add each once in CapCut (search its name in the audio panel)")
        print("  and it caches locally, then it'll drop in automatically next time.")
    if not available:
        print("No matched SFX are cached on this machine yet, so I'm skipping the SFX pass. Your reel is "
              "totally fine without it — add your go-to sounds in CapCut once, then re-run and they'll place "
              "themselves. (Expected on a fresh install.)")
        raise SystemExit(0)
    total = 0
    for path in _ds.draft_json_copies(KD, require=False):
        n = inject(path, na, ph, available); total = n
        print(f"injected {n} SFX (named clips) -> {path}")
    print(f"done — SFX pass complete ({total} placed). Audio track ripples; clips named by sound.")
