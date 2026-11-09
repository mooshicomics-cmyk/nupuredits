#!/usr/bin/env python3
"""build-overlay.py — inject a transparent kinetic-caption .mov (qtrle/argb) onto the migrated CapCut
draft as full-frame OVERLAY video clip(s) on a flag=2 PIP track (above the footage), muted.

Dead-space trimming: if a spans file is given (list of [start,end] seconds of ACTIVE text), lay ONE segment
per span so long empty stretches (>DEAD_GAP) leave the track clear — the creator can grab layers below. Without a
spans file, the render's own <mov>.spans.json (written by reel_render.py for a caption layer rendered only where
it is on screen, product/render_spans.py) gives the spans; without either, one full-length segment.

IDEMPOTENT set-overlay (§20): if the named track already exists, this UPDATES IT IN PLACE — repoints the
media and PRESERVES the creator's in-app work (transform/scale/rotation/keyframes/material refs/labels/
stacking). It creates a fresh track only when none exists. So it is safe to re-run and does NOT need
remove-overlays.py first (the old delete-then-add reset her hand-set scale/offset to defaults — never again).

Usage: build-overlay.py <mov> <track_name> [render_index] [spans.json]   (CapCut MUST be quit)
Job/target: JOB env var = project slug under projects/ (required); CAPCUT_DRAFT env var = the CapCut
draft folder name (required). Clones the footage video material + its helper materials per segment.
"""
import json, os, glob, copy, uuid, shutil, subprocess, sys, re
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
def _require_env(name, hint):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"[build-overlay] Set {name}=<{hint}> before running "
                 f"(e.g. {name}=MyProject python3 product/build-overlay.py ...). "
                 f"Refusing to silently fall back to a bundled sample reel.")
    return v

JOB   = _require_env("JOB", "your project slug under projects/")   # projects/<JOB>
DRAFT = _require_env("CAPCUT_DRAFT", "the CapCut draft folder")     # CapCut draft folder
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
D = f"{CAP}/{DRAFT}"
SRC   = sys.argv[1] if len(sys.argv) > 1 else f"projects/{JOB}/{JOB}-captions-transparent.mov"
TRACK = sys.argv[2] if len(sys.argv) > 2 else "captions_overlay"
RIDX  = int(sys.argv[3]) if len(sys.argv) > 3 else 14000
SPANS_FILE = sys.argv[4] if len(sys.argv) > 4 else ""
NAME = os.path.basename(SRC)
US = 1_000_000

def dur_us(p): return int(round(float(subprocess.check_output(
    ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]))*US))
def NID(): return str(uuid.uuid4()).upper()
def nid(): return uuid.uuid4().hex

def _find_overlay_track(d, track_name):
    """The existing overlay track for this layer, or None. Matched by track name, OR (finalize-proof, since
    the magnet blanks non-main track names to "") by flag==2 + material_name — the same matcher family as
    remove-overlays.py."""
    mat_name = {m.get("id"): m.get("material_name", "")
                for m in d.get("materials", {}).get("videos", []) if isinstance(m, dict)}
    for t in d.get("tracks", []):
        if t.get("type") != "video":
            continue
        if t.get("name") == track_name:
            return t
        if t.get("flag") == 2 and any(mat_name.get(s.get("material_id"), "") == track_name
                                      for s in t.get("segments", [])):
            return t
    return None


def _clamp_span(a, b, ov_dur):
    a_us = max(0, int(round(a * US))); L = int(round((b - a) * US))
    if a_us + L > ov_dur:
        L = ov_dur - a_us
    return a_us, L


def inject(path, ov_dur, spans):
    """Idempotent set-overlay: if the named track already exists, UPDATE IT IN PLACE — repoint its segments at
    the new media and PRESERVE the creator's in-app work (clip transform/scale/rotation/flip/alpha, keyframes,
    material refs, render_index, volume, color labels, stacking order). Only create a fresh track when none
    exists. Never delete-and-recreate a layer the creator may have touched (§20 / capcut never replace rebuild).
    Returns (n_segments, mode) where mode is 'created' | 'updated-in-place' | 'rebuilt-carry-forward' |
    'skipped-empty'."""
    d = json.load(open(path, encoding="utf-8"))
    idx = {m["id"]: (cat, m) for cat, l in d["materials"].items() if isinstance(l, list) for m in l if isinstance(m, dict) and "id" in m}
    # A draft can hold MORE THAN ONE timeline-JSON copy and not all of them carry the footage: a PC that has
    # run an older engine keeps an empty draft_info.json stub next to the real draft_content.json CapCut
    # writes (the same Mac/Windows naming drift draft_safety.draft_json_name() exists for). That stub has no
    # video track to key the overlay off, and max() over nothing used to raise ValueError and take the whole
    # pad-and-inject run down mid-reel. There is nothing to do to a file with no footage in it, so say so and
    # move on to the copy that does have it.
    candidates = [t for t in d["tracks"] if t["type"] == "video" and t.get("segments")]
    if not candidates:
        return 0, "skipped-empty"
    foot = max(candidates, key=lambda t: len(t["segments"]))
    seg_t = foot["segments"][0]
    vm_t = idx[seg_t["material_id"]][1]
    # overlay .mov path must match the footage material's path SCHEME so CapCut resolves it:
    #  • old template-injection drafts → a ##_draftpath_placeholder_<UUID>_## token
    #  • VectCutAPI drafts (cleanyap/superyap, current engine) → an ABSOLUTE path into the draft's assets/
    mph = re.search(r'placeholder_([0-9A-F-]+)_', vm_t["path"])
    ovpath = (f"##_draftpath_placeholder_{mph.group(1)}_##/assets/video/{NAME}" if mph
              else f"{D}/assets/video/{NAME}")
    # one shared video material (the new overlay .mov), repointed into the draft
    m = copy.deepcopy(vm_t); mid = nid()
    m.update(id=mid, unique_id="", local_id="", material_id="",
             path=ovpath, media_path="", material_name=TRACK, duration=ov_dur,
             width=1080, height=1920, has_audio=False)

    from capcut_ripple import enforce_maintrack_ripple
    existing = _find_overlay_track(d, TRACK)
    if existing is not None and existing.get("segments"):
        # ── IN-PLACE UPDATE (§20): the creator may have scaled/moved/keyframed this layer in CapCut. Repoint
        # the media and clamp timeranges, but keep every other field of her segments. This is the fix for the
        # confirmed regression where a re-inject reset her 57.4% scale + offset back to y=0 / scale=1.0.
        d["materials"]["videos"].append(m)
        old = existing["segments"]
        if len(old) == len(spans):
            for s, (a, b) in zip(old, spans):
                a_us, L = _clamp_span(a, b, ov_dur)
                if L <= 0:
                    continue
                s["material_id"] = mid
                s["source_timerange"] = {"start": a_us, "duration": L}
                tt = s.get("target_timerange") or {"start": a_us, "duration": L}
                tt["duration"] = L; s["target_timerange"] = tt   # keep her moved start; clamp only the length
            mode, n = "updated-in-place", len(old)
        else:
            # span layout changed → segments must be rebuilt, but carry the layer's transform + keyframes
            # forward from the first existing segment instead of starting from CapCut defaults (§20.4B).
            tmpl = copy.deepcopy(old[0])
            new_segs = []
            for a, b in spans:
                a_us, L = _clamp_span(a, b, ov_dur)
                if L <= 0:
                    continue
                s = copy.deepcopy(tmpl); s["id"] = NID(); s["material_id"] = mid
                refs = []                                        # helper materials get fresh clones per segment
                for r in tmpl.get("extra_material_refs", []):
                    if r in idx:
                        cat, ht = idx[r]; h = copy.deepcopy(ht); h["id"] = NID() if "-" in ht["id"] else nid()
                        d["materials"][cat].append(h); refs.append(h["id"])
                s["extra_material_refs"] = refs
                s["source_timerange"] = {"start": a_us, "duration": L}
                s["target_timerange"] = {"start": a_us, "duration": L}
                new_segs.append(s)                               # tmpl's clip/scale/keyframes are preserved
            existing["segments"] = new_segs
            mode, n = "rebuilt-carry-forward", len(new_segs)
        enforce_maintrack_ripple(d)
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        return n, mode

    # ── CREATE (no existing track): a brand-new layer, so default transform is correct.
    d["materials"]["videos"].append(m)
    segs = []
    for a, b in spans:
        a_us, L = _clamp_span(a, b, ov_dur)
        if L <= 0:
            continue
        refs = []
        for r in seg_t["extra_material_refs"]:
            cat, ht = idx[r]
            h = copy.deepcopy(ht); h["id"] = NID() if "-" in ht["id"] else nid()
            d["materials"][cat].append(h); refs.append(h["id"])
        s = copy.deepcopy(seg_t); s["id"] = NID(); s["material_id"] = mid; s["extra_material_refs"] = refs
        s["target_timerange"] = {"start": a_us, "duration": L}
        s["source_timerange"] = {"start": a_us, "duration": L}
        s["clip"]["scale"] = {"x": 1.0, "y": 1.0}; s["clip"]["transform"] = {"x": 0.0, "y": 0.0}
        s["volume"] = 0.0; s["last_nonzero_volume"] = 0.0
        s["render_index"] = RIDX; s["common_keyframes"] = []; s["keyframe_refs"] = []
        segs.append(s)
    d["tracks"].append({"type": "video", "attribute": 0, "flag": 2, "id": NID(),
                        "is_default_name": False, "name": TRACK, "segments": segs})
    enforce_maintrack_ripple(d)                 # magnet ALL tracks (overlays/text/b-roll) + audio to main track
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return len(segs), "created"

def spans_for(src, spans_file, ov_dur, footage_clips=None):
    """[(start, end), ...] seconds to lay: the spans file when one is given; else the render's own sidecar (a
    caption layer rendered only where it is on screen carries <mov>.spans.json, render_spans.py; the .mov is
    still full length, so each stretch goes at its own time); else the whole .mov as one segment, as before.
    The sidecar's stretches are used only while the footage track keeps MORE clips than this layer would get:
    the magnet (capcut_ripple.enforce_maintrack_ripple) anchors to the video track with the most clips, and a
    caption layer must never become it. With fewer footage clips the whole .mov goes in as one segment."""
    if spans_file and os.path.exists(spans_file):
        return json.load(open(spans_file, encoding="utf-8"))
    import render_spans
    segs = render_spans.segments(src)
    if segs and (footage_clips is None or len(segs) < footage_clips):
        print(f"  laying {len(segs)} segment(s), one per stretch this layer is on screen (from its .spans.json)")
        return [(a, a + d) for a, d in segs]
    return [(0.0, ov_dur / US)]


def footage_clips(draft_dir):
    """How many clips the draft's footage track holds (the video track with the most), or None if unreadable."""
    for f in _ds.draft_json_copies(draft_dir, require=False):
        try:
            d = json.load(open(f, encoding="utf-8"))
            n = max((len(t.get("segments", [])) for t in d.get("tracks", []) if t.get("type") == "video"), default=0)
            if n:
                return n
        except Exception:
            continue
    return None


if __name__ == "__main__":
    import draft_safety
    draft_safety.require_capcut_quit("layer this overlay onto the draft")   # else CapCut's next save wipes it
    # FAIL LOUD on a missing target (§16.2): never create a draft implicitly. A wrong CAPCUT_DRAFT used to
    # sail through here and os.makedirs below would spawn a junk draft folder (a 347MB orphan in one case).
    if not os.path.isdir(D):
        sys.exit(f"[build-overlay] draft {DRAFT!r} not found at {D} — refusing to create it. "
                 f"Check CAPCUT_DRAFT; this tool only updates an existing draft, it never makes one.")
    # RULE 7 net for the layering path: warn (do not hard-refuse — this add is ADDITIVE, its own track, and
    # does not touch her existing edits) if she has edited the draft in CapCut since it was built, so a clean
    # version history is a choice she can make. edited_in_capcut can over-warn (QA #9), which is exactly why
    # this warns-and-proceeds instead of blocking. capcut never replace rebuild
    _edited, _why = draft_safety.edited_in_capcut(DRAFT, why=True)
    if _edited:
        _next = draft_safety.next_version(draft_safety.base_of(DRAFT))
        print(f"⚠ {DRAFT!r} looks edited in CapCut since it was built ({_why}). Layering on is safe (this is "
              f"additive, its own track), but for a clean version history, build to {_next!r} instead.")
    os.makedirs(f"{D}/assets/video", exist_ok=True)
    # CapCut reads overlay alpha as straight, like the render, so a render goes in as it is; a WebM (CapCut
    # drops its alpha) or an old premultiplied copy comes back as straight ProRes 4444. SRC is never changed.
    import capcut_alpha
    shutil.copy(capcut_alpha.for_capcut(SRC), f"{D}/assets/video/{NAME}")
    ov = dur_us(SRC)
    spans = spans_for(SRC, SPANS_FILE, ov, footage_clips(D))
    done = 0
    for f in _ds.draft_json_copies(D, require=False):
        n, mode = inject(f, ov, spans)
        note = {"updated-in-place": "media swapped IN PLACE — your transform / scale / keyframes / labels preserved",
                "rebuilt-carry-forward": "span layout changed → segments rebuilt, carrying your transform + keyframes forward",
                "created": "new track created",
                "skipped-empty": "no footage in this timeline copy — nothing to layer onto, left untouched"}[mode]
        print(f"set-overlay {NAME} -> {n} segment(s) on '{TRACK}' ({note}) -> {f}")
        if mode != "skipped-empty":
            done += 1
    if not done:
        sys.exit(f"[build-overlay] {DRAFT!r} has no timeline with footage on it, so there is nothing to layer "
                 f"{TRACK!r} onto. Build the reel's base draft first, then layer this on.")
    print(f"done — {TRACK}: {len(spans)} active span(s); idempotent set-overlay (safe to re-run, never resets your CapCut edits).")
