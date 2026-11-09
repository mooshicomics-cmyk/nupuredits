#!/usr/bin/env python3
"""patch-zooms.py — SURGICAL: add jump-cut punches + a slow keyframed zoom to the creator's TRIMMED CapCut
draft. Preserves her trims and her own zooms (only touches clips still at scale 1.0). CapCut MUST be quit.
Job/target: CAPCUT_DRAFT env var = the CapCut draft folder name (required; there is no default draft).
NOTE: the PUNCH clip indices and SLOW_IDX are still one reel's exact clip numbers — not generalized (see FLAG).
"""
import json, os, glob, uuid, copy, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capcut_ripple import enforce_maintrack_ripple   # re-anchor the magnet after any surgical draft write

DRAFT = os.environ.get("CAPCUT_DRAFT", "")       # CapCut draft folder (required: checked before anything runs)
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
D = f"{CAP}/{DRAFT}"
US = 1_000_000

# jump-cut punches (static scale) on ACCENT clips currently at 1.0 — spread to alternate with her zooms
PUNCH = {2: 1.07, 6: 1.06, 9: 1.09, 12: 1.06, 18: 1.08, 22: 1.06, 26: 1.08, 30: 1.10}
SLOW_IDX = 1                 # slow keyframed zoom on clip index 1 (the line straight after the hook)
ZOOM_FROM, ZOOM_TO, ZOOM_SECS = 1.06, 1.22, 1.4

def NID(): return str(uuid.uuid4()).upper()

def kf(time_us, val):
    return {"id": NID(), "curveType": "Line", "time_offset": int(time_us),
            "left_control": {"x": 0.0, "y": 0.0}, "right_control": {"x": 0.0, "y": 0.0},
            "values": [val], "string_value": "", "graphID": ""}

def patch(path):
    d = json.load(open(path, encoding="utf-8"))
    foot = max([t for t in d["tracks"] if t["type"] == "video"], key=lambda t: len(t["segments"]))
    segs = foot["segments"]
    n_punch = 0
    for i, val in PUNCH.items():
        if i < len(segs):
            sc = segs[i].setdefault("clip", {}).setdefault("scale", {"x": 1.0, "y": 1.0})
            if abs(sc.get("x", 1.0) - 1.0) < 1e-6:          # only if she left it at 1.0
                sc["x"] = val; sc["y"] = val; n_punch += 1
    # slow keyframed zoom on clip SLOW_IDX
    if SLOW_IDX < len(segs):
        s = segs[SLOW_IDX]
        src0 = s["source_timerange"]["start"]
        # keyframe BOTH axes together — a lone ScaleX keyframe warps the footage once uniform_scale is off
        s["common_keyframes"] = [{
            "id": NID(), "material_id": "", "property_type": prop,
            "keyframe_list": [kf(src0, ZOOM_FROM), kf(src0 + ZOOM_SECS * US, ZOOM_TO)]
        } for prop in ("KFTypeScaleX", "KFTypeScaleY")]
        s.setdefault("clip", {})["scale"] = {"x": ZOOM_TO, "y": ZOOM_TO}   # hold end value
    enforce_maintrack_ripple(d)                        # keep the magnet alive after a surgical patch
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return n_punch

if __name__ == "__main__":
    if not DRAFT:   # a surgical patch with a default target could land on the wrong project
        sys.exit("⛔ Set CAPCUT_DRAFT=<the CapCut draft folder to patch> first, e.g. "
                 "CAPCUT_DRAFT=\"my-reel 1.2\" python3 product/patch-zooms.py. Nothing was patched.")
    import draft_safety; draft_safety.require_capcut_quit("patch this draft")   # else CapCut's next save wipes it
    files = _ds.draft_json_copies(D, require=False)
    if not files:   # never print "done" on a draft that does not exist (it used to)
        sys.exit(f"⛔ no CapCut draft at {D} (no {' or '.join(_ds.DRAFT_JSON_NAMES)}). "
                 f"Check CAPCUT_DRAFT — nothing was patched.")
    for f in files:
        n = patch(f)
        print(f"patched {f}: {n} jump-cut punches + slow zoom on clip {SLOW_IDX}")
    print("done — jump-cut zooms + slow push-in added; her trims & own zooms preserved.")
