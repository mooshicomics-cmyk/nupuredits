#!/usr/bin/env python3
"""gif_dropins.py — layer reaction GIFs / sticker clips onto a CapCut draft the RIGHT way.

THE METHOD (locked): a GIF is DROPPED ONTO THE TIMELINE as its OWN native PIP clip — the gif converted to
a see-through ProRes 4444 clip at its own size (capcut_alpha.looped_clip: straight alpha, what CapCut keeps the
transparency of), LOOPED for as long as it is on screen, scaled down, positioned, MUTED, on its own overlay
track. Additive: existing footage / SFX / text tracks are never touched, and the change is built into a NEW
version so the original is preserved. (It was an opaque mp4 looped at most five times: a see-through GIF sat
in a black box, and a long drop-in ended early, 2026-10-28.)

DO NOT composite a gif onto a full-frame transparent/black canvas. That lays a 1080x1920 rectangle over the
footage; if the alpha is lost even once it becomes an opaque BLACK block covering the whole frame for the
gif's duration. A drop-in is just the gif clip itself — no canvas.

Usage (library):
    from gif_dropins import layer_gif_dropins
    plan = [{"gif": "/path/a.gif", "at": 2.3, "dur": 1.33},
            {"gif": "/path/b.gif", "at": 13.0, "dur": 3.5, "loop": False}, ...]   # loop False: plays once
    new_name = layer_gif_dropins("My Reel", plan)          # -> "My Reel 1.1", original untouched

Usage (CLI):
    python3 gif_dropins.py "<draft name>" plan.json [--scale 0.30] [--in-place]

CapCut MUST be quit (enforced). Requires ffmpeg + ffprobe.
"""
import os, sys, json, copy, uuid, shutil, subprocess
import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draft_safety
import capcut_media
from capcut_ripple import enforce_maintrack_ripple   # re-assert the main-track magnet before saving (locked: every draft writer)

CAP = draft_safety.CAP
US = 1_000_000
DEFAULT_SCALE = 0.30            # on-screen size; the creator scales to taste in CapCut
DEFAULT_TRANSFORM = (0.0, 0.45) # centered X, raised toward the top (units of half-canvas; +Y = up)

# Gif entrance/exit uses CapCut's built-in SLIDE animation PRESETS. NEVER keyframe a gif's position to
# slide it — CapCut glitches on keyframed gifs. Presets are the normal, stable way (material_animations).
_SLIDE_IN  = {"R": ("Slide Right", "6798333076469453320"), "L": ("Slide Left", "6798332871267324423")}
_SLIDE_OUT = {"R": ("Slide Right", "6798333350487527950"), "L": ("Slide Left", "6798332972098392584")}

def _slide_material(side, dur_us, both=True):
    """A material_animations entry: CapCut Slide-in (+ Slide-out for clips >=1.3s), 0.5s each."""
    def a(name, num, ty, st, du):
        return {"anim_adjust_params": None, "platform": "all", "panel": "video", "material_type": "video",
                "name": name, "id": num, "type": ty, "resource_id": num, "start": st, "duration": du}
    D = 500000
    anims = [a(*_SLIDE_IN[side], "in", 0, D)]
    if both and dur_us / 1_000_000 >= 1.3:
        anims.append(a(*_SLIDE_OUT[side], "out", max(0, dur_us - D), D))
    return {"id": _nid(), "type": "sticker_animation", "multi_language_current": "none", "animations": anims}


def _nid(): return uuid.uuid4().hex
def _NID(): return str(uuid.uuid4()).upper()


def _to_clip(gif, dur, loop, out):
    """GIF -> native-size see-through clip (no canvas, no audio), looped to fill `dur` seconds (one play when
    `loop` is False). The same converter every CapCut build uses for a GIF (capcut_alpha.looped_clip, cached)."""
    import capcut_alpha
    shutil.copyfile(capcut_alpha.looped_clip(gif, dur if loop else None), out)


def _probe(p):
    import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from probe import probe as _hf_probe          # rotation-aware displayed size + duration
    r = _hf_probe(p)
    return int(r["width"]), int(r["height"]), float(r["duration"])


def layer_gif_dropins(draft_name, plan, scale=DEFAULT_SCALE, transform=DEFAULT_TRANSFORM,
                      track_prefix="gif", make_version=True, slide=True):
    """Layer each gif in `plan` onto `draft_name` as a native muted PIP clip at its beat. Returns the draft
    that was written (a NEW version by default; the original is never modified). `plan` items:
    {"gif": path, "at": seconds, "dur": seconds, "loop": bool(optional)}."""
    draft_safety.require_capcut_quit("layer gif drop-ins")
    # A Mac that keeps the engine out of Movies: bring a draft she has into the staging folder first (a copy;
    # hers is never changed). Everywhere else this answers CAP/<draft_name> and does nothing.
    __import__("capcut_store_redirect").stage_existing(draft_name, CAP)
    target = draft_safety.duplicate(draft_name) if make_version else draft_name
    D = os.path.join(CAP, target)
    p = _ds.draft_json(D)
    d = json.load(open(p, encoding="utf-8"))
    os.makedirs(f"{D}/assets/video", exist_ok=True)

    # template: clone a FULL-FRAME FOOTAGE segment (never a gif/overlay track — a consolidated gif track can
    # have MORE segments than the 1-seg footage, and cloning it would inherit that gif's rotation/scale).
    vids = [t for t in d["tracks"] if t["type"] == "video" and t["segments"]]
    if not vids:
        raise RuntimeError("no footage video track to layer onto")
    idx = {m["id"]: (cat, m) for cat, l in d["materials"].items() if isinstance(l, list)
           for m in l if isinstance(m, dict) and "id" in m}
    def _fullframe(seg):
        m = idx.get(seg.get("material_id"), (None, {}))[1]
        return m.get("width", 0) >= 1080 and m.get("height", 0) >= 1920
    _allsegs = [(t, s) for t in vids for s in t["segments"]]
    seg_t = (next((s for t, s in _allsegs if t.get("flag") == 0 and _fullframe(s)), None)
             or next((s for t, s in _allsegs if _fullframe(s)), None)
             or vids[0]["segments"][0])
    vm_t = idx[seg_t["material_id"]][1]

    for i, item in enumerate(plan):
        gif = item["gif"]; at = float(item["at"]); dur = float(item["dur"]); loop = bool(item.get("loop", True))
        mp4 = f"{D}/assets/video/{track_prefix}_{i}.mov"
        _to_clip(gif, dur, loop, mp4)
        w, h, real = _probe(mp4)
        L = int(round(min(real, dur) * US))
        # native video material (the see-through gif clip) — NOT a full-frame canvas
        m = copy.deepcopy(vm_t); mid = _nid()
        m.update(id=mid, unique_id="", local_id="", material_id="", path=mp4, media_path="",
                 material_name=f"{track_prefix}_{i}", duration=L, width=w, height=h, has_audio=False)
        d["materials"]["videos"].append(m)
        # PIP segment: source starts at 0 (short clip plays from its start), scaled + positioned, muted
        refs = []
        for r in seg_t.get("extra_material_refs", []):
            cat, ht = idx[r]; h2 = copy.deepcopy(ht)
            h2["id"] = _NID() if "-" in ht["id"] else _nid()
            d["materials"][cat].append(h2); refs.append(h2["id"])
        s = copy.deepcopy(seg_t); s["id"] = _NID(); s["material_id"] = mid; s["extra_material_refs"] = refs
        s["target_timerange"] = {"start": int(round(at * US)), "duration": L}
        s["source_timerange"] = {"start": 0, "duration": L}
        s.setdefault("clip", {})["scale"] = {"x": scale, "y": scale}
        s["clip"]["transform"] = {"x": float(transform[0]), "y": float(transform[1])}
        s["clip"]["rotation"] = 0.0                     # LOCKED: drop-ins are never tilted (clone can inherit a tilt)
        if isinstance(s.get("uniform_scale"), dict):
            s["uniform_scale"]["on"] = False           # so clip.scale actually renders (locked CapCut bug)
        s["volume"] = 0.0; s["last_nonzero_volume"] = 0.0
        s["render_index"] = 16000 + i; s["common_keyframes"] = []; s["keyframe_refs"] = []
        if slide:   # CapCut Slide preset (alternating L/R), NEVER position keyframes
            mat = _slide_material("R" if i % 2 == 0 else "L", L)
            d["materials"].setdefault("material_animations", []).append(mat)
            s["extra_material_refs"] = list(s["extra_material_refs"]) + [mat["id"]]
        d["tracks"].append({"type": "video", "attribute": 0, "flag": 2, "id": _NID(),
                            "is_default_name": False, "name": f"{track_prefix}_{i}", "segments": [s]})

    probs = capcut_media.ensure_shippable(d, D)
    if probs:
        raise RuntimeError("media won't link/import:\n  - " + "\n  - ".join(probs))
    enforce_maintrack_ripple(d)                 # base guardrail: magnet ALL tracks (incl. the new GIF PIP) + audio to the main track
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return target


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) < 2:
        raise SystemExit('usage: gif_dropins.py "<draft name>" plan.json [--scale 0.30] [--in-place]')
    name, plan_path = args[0], args[1]
    sc = DEFAULT_SCALE
    for f in flags:
        if f.startswith("--scale"):
            sc = float(f.split("=", 1)[1]) if "=" in f else float(args[2])
    plan = json.load(open(plan_path, encoding="utf-8"))
    out = layer_gif_dropins(name, plan, scale=sc, make_version=("--in-place" not in flags))
    print(f"layered {len(plan)} gif drop-in(s) -> '{out}' (native PIP clips, muted; original preserved)")
