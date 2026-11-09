#!/usr/bin/env python3
"""capcut_motion.py — DEFAULT camera motion for every Yap (shared, single source).

Why this exists: a static talking head reads flat. The strong-default rule (CLAUDE.md "APPLY THE STRONG
DEFAULTS — never make the creator REQUEST quality") says movement is ON by default, not an upgrade she has
to ask for. So every Clean/Super Yap gets, for free:
  • a slow keyframed ZOOM-IN on the opening clip (the push-in that pulls a scroller in), and
  • gentle JUMP-CUT PUNCHES on a rotating cadence of later clips (subtle scale bumps at the cut, so the
    frame never sits dead still and each new beat has a little energy).

It is ADDITIVE and RESPECTFUL: it only ever touches a footage clip that is still at scale 1.0, at
transform 0/0, with no keyframes — i.e. one nobody has already zoomed OR repositioned on purpose. If a
per-reel build passes its own `punch` dict to add_cut, or the creator set her own zoom or nudged a clip
across in CapCut, this skips it. So the default never fights an explicit choice.

EVERY ZOOM REFRAMES ON THE FACE IN THAT SHOT (2026-09-17). A scale keyframe alone zooms about the FRAME
CENTRE, so a creator who does not sit dead centre gets enlarged-middle-of-the-room and slid toward the
edge on every push-in — reported from the first PC test reel as "the zooms go off to the side", and this
module was centre-anchored in exactly that way (it set scale and never touched clip.transform). It now
writes a matching clip.transform, keyframed in lockstep with the intro zoom, so the face holds its
position while the frame closes in. Anchors are PER SHOT, never one median for the reel: a creator
re-frames between takes (measured 0.14 of the frame width on that reel), so a single anchor is wrong
for every shot but one. Pass `anchors` from workflows/head-framing.py --windows. With no anchors it
still centre-anchors, exactly as before, but it says so instead of pretending.

UNITS: clip.transform is in HALF-CANVAS units (pyJianYingDraft segment.py: "单位为半个画布宽"), so
[-1, 1] spans the frame, and +y is UP. To hold a point at half-canvas offset d while scaling by S,
shift by d*(1-S) — which is also why |transform| can never exceed S-1 for a face inside the frame,
so no edge is ever exposed.

The mechanics (which track is the footage anchor, how a scale keyframe is shaped, the uniform_scale render
bug) match patch-zooms.py and the finalize scale-guardrail — this generalizes that one-off so every build
gets it, instead of it living as a hardcoded per-reel script. Call apply_default_motion(d) in finalize
BEFORE the scale guardrail loop (the guardrail then flips uniform_scale off so the motion actually renders).
"""
import json, os, shutil, subprocess, tempfile, uuid

US = 1_000_000

# Opening push-in: scale the first clip from FROM -> TO over SECS, then hold TO. Slow and small on purpose
# (a shove, not a rocket). Matches the creator's locked intro-zoom values.
INTRO_ZOOM_FROM, INTRO_ZOOM_TO, INTRO_ZOOM_SECS = 1.06, 1.22, 1.4

# Jump-cut punches: a gentle static scale bump at the cut. EVERY_NTH controls the cadence (every 3rd clip
# after the opener, tasteful — not every cut, which reads seasick). SCALE_POOL rotates so two consecutive
# punches never share an amount (variation; the same bump repeated reads as a glitch, not a choice).
PUNCH_EVERY_NTH = 3
PUNCH_START_INDEX = 2                       # leave clip 0 (intro zoom) and clip 1 (settle) alone
PUNCH_SCALE_POOL = (1.07, 1.09, 1.06, 1.08)


def _nid():
    return str(uuid.uuid4()).upper()


def _kf(time_us, val):
    """One scale keyframe in CapCut's shape (mirrors patch-zooms.kf)."""
    return {"id": _nid(), "curveType": "Line", "time_offset": int(time_us),
            "left_control": {"x": 0.0, "y": 0.0}, "right_control": {"x": 0.0, "y": 0.0},
            "values": [val], "string_value": "", "graphID": ""}


def anchor_transform(fx, fy, scale, strength=1.0):
    """Half-canvas (x, y) that holds the point (fx, fy) — normalised 0..1 of the frame, origin
    top-left — fixed while the clip scales by `scale` about the frame centre. (0.5, 0.5) gives
    (0, 0): a centred face needs no correction, so this is a no-op on centred footage.

    `strength` (0..1) blends the anchor back toward the frame centre, and 0 is a plain centre zoom.
    It carries how much the measurement is worth trusting: a static anchor only holds a subject who
    holds still, so on footage where she moves during the shot a FULL correction can frame her worse
    than none — verified on a real clip where the subject moved 0.14 of the frame width inside one
    second and a full correction pushed her past centre the other way. Damping keeps the fix where
    it helps and makes it fade out where it cannot."""
    k = max(0.0, min(1.0, float(strength)))
    fx = 0.5 + k * (float(fx) - 0.5)
    fy = 0.5 + k * (float(fy) - 0.5)
    dx = 2.0 * (float(fx) - 0.5)            # half-canvas offset from centre, +x right
    dy = -2.0 * (float(fy) - 0.5)           # ... +y UP, so screen-down is negative
    k = 1.0 - float(scale)
    lim = abs(float(scale) - 1.0)           # past this the scaled clip no longer covers the frame
    return (round(max(-lim, min(lim, dx * k)), 6),
            round(max(-lim, min(lim, dy * k)), 6))


def _seg_anchor(anchors, i):
    """(fx, fy, strength) for segment i, or None. Accepts a list parallel to the segments, a dict
    keyed by index, or one anchor to use for every clip. An entry may be (fx, fy) — trusted fully —
    or (fx, fy, strength), where strength is how far to apply the correction."""
    if anchors is None:
        got = None
    elif isinstance(anchors, dict):
        got = anchors.get(i)
    elif len(anchors) in (2, 3) and all(isinstance(v, (int, float)) for v in anchors):
        got = anchors
    else:
        got = anchors[i] if i < len(anchors) else None
    if not got:
        return None
    return (got[0], got[1], got[2] if len(got) > 2 else 1.0)


ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _material_paths(d):
    return {v.get("id"): (v.get("path") or "") for v in d.get("materials", {}).get("videos", [])}


def measure_anchors(d, indices, root=ENGINE):
    """Measure a face anchor for each listed footage segment, IN THAT SEGMENT'S OWN SOURCE RANGE.

    The draft already knows everything needed: the material path per segment and the source
    timerange the segment plays, so the caller does not have to carry a video path around. Windows
    on the same source clip are measured in one pass.

    Best-effort by design. No uv, no head-framing.py, a compound clip with no path on disk, a source
    that has moved, a face that cannot be found — any of those simply leaves that segment out, and
    the caller falls back to a centre anchor and says so. A zoom anchor must never fail a build."""
    ff = os.path.join(root, "workflows", "head-framing.py")
    if not indices or not os.path.exists(ff) or not shutil.which("uv"):
        return {}
    foot = _footage_track(d)
    if not foot:
        return {}
    segs, paths = foot["segments"], _material_paths(d)

    by_path = {}
    for i in indices:
        if i >= len(segs):
            continue
        src = segs[i].get("source_timerange") or {}
        path = paths.get(segs[i].get("material_id"), "")
        if not path or not os.path.exists(path) or not src.get("duration"):
            continue
        t0 = src.get("start", 0) / US
        by_path.setdefault(path, []).append((i, t0, t0 + src["duration"] / US))

    out = {}
    for path, rows in by_path.items():
        tmp = os.path.join(tempfile.mkdtemp(), "anchors.json")
        try:
            subprocess.run(["uv", "run", ff, path, "--windows",
                            json.dumps([[a, b] for _i, a, b in rows]), "--out", tmp],
                           check=True, timeout=900,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            got = json.load(open(tmp, encoding="utf-8")).get("windows", [])
        except (subprocess.SubprocessError, OSError, ValueError):
            continue
        if len(got) != len(rows):
            continue
        for (i, _a, _b), r in zip(rows, got):
            out[i] = (float(r["anchor"][0]), float(r["anchor"][1]),
                      float(r.get("confidence", 1.0)))
    return out


def _footage_track(d):
    """The main footage track = the video track with the MOST segments (same anchor rule the magnet uses)."""
    vids = [t for t in d.get("tracks", []) if t.get("type") == "video" and t.get("segments")]
    return max(vids, key=lambda t: len(t["segments"])) if vids else None


def _untouched(seg):
    """True only if this clip is still at scale 1.0 AND transform 0/0 with no scale or position
    keyframes — i.e. nobody zoomed or repositioned it on purpose, so a default is safe to add.
    Preserves any explicit punch/zoom a build set, and any clip the creator has nudged by hand
    (on the first PC test reel she had repositioned 9 of 20 segments herself)."""
    clip = seg.get("clip", {})
    sc = clip.get("scale", {})
    if abs(sc.get("x", 1.0) - 1.0) > 1e-6 or abs(sc.get("y", 1.0) - 1.0) > 1e-6:
        return False
    tr = clip.get("transform", {})
    if abs(tr.get("x", 0.0)) > 1e-6 or abs(tr.get("y", 0.0)) > 1e-6:
        return False
    return not any(k.get("property_type") in ("KFTypeScaleX", "KFTypeScaleY",
                                              "KFTypePositionX", "KFTypePositionY")
                   for k in seg.get("common_keyframes", []))


def apply_default_motion(d, intro_zoom=True, punches=True, anchors="auto"):
    """Add the default intro zoom + jump-cut punches to the footage track, in place. Returns
    (n_zoom, n_punch) for logging. Idempotent by construction: a clip it already moved is no longer at
    scale 1.0, so a second call skips it.

    `anchors` gives the face position per footage segment, normalised 0..1 of the frame — a list
    parallel to the segments, a dict keyed by index, or one (fx, fy) for all of them. The default
    "auto" measures them off the footage the draft already points at, so the CapCut routes get
    reframed zooms without the caller doing anything. Pass None to skip measuring; every zoom is
    then centre-anchored, which drifts an off-centre creator toward the edge, and it says so."""
    # HANDS OFF when the footage is being handed over for her to move herself. A draft built as a
    # companion to a finished reel exists so SHE can keyframe her own zooms on the footage track, and a
    # default push-in there is not a helpful head start, it is something to undo on every clip. The first
    # PC tester's own saved preference says it outright: baked zooms read as distracting to her, whichever
    # kind, so deliver the reel without them and let her keyframe zooms herself.
    if os.environ.get("REEL_NO_DEFAULT_MOTION") == "1":
        print("[motion] default camera moves OFF (REEL_NO_DEFAULT_MOTION=1) — the footage is hers to zoom.")
        return (0, 0)

    foot = _footage_track(d)
    if not foot:
        return (0, 0)
    segs = foot["segments"]
    n_zoom = n_punch = n_anchored = 0

    if anchors == "auto":
        want = ([0] if intro_zoom else []) + \
               (list(range(PUNCH_START_INDEX, len(segs), PUNCH_EVERY_NTH)) if punches else [])
        want = [i for i in want if i < len(segs) and _untouched(segs[i])]
        if want:
            print(f"[motion] measuring a face anchor for {len(want)} clip(s) ...")
        anchors = measure_anchors(d, want) or None

    # 1) slow keyframed zoom-in on the opening clip. KEYFRAME BOTH AXES in lockstep: the finalize scale
    #    guardrail turns uniform_scale OFF whenever a scale keyframe is present (so the zoom renders at all),
    #    which makes X and Y independent — so animating only ScaleX stretches the footage horizontally
    #    (aspect warp). Writing an identical ScaleY keyframe keeps the zoom square. (fix: single-axis warp)
    if intro_zoom and segs and _untouched(segs[0]):
        s = segs[0]
        src0 = s.get("source_timerange", {}).get("start", 0)
        t_end = src0 + INTRO_ZOOM_SECS * US
        kfs = s.get("common_keyframes", [])
        for prop in ("KFTypeScaleX", "KFTypeScaleY"):
            kfs.append({"id": _nid(), "material_id": "", "property_type": prop,
                        "keyframe_list": [_kf(src0, INTRO_ZOOM_FROM), _kf(t_end, INTRO_ZOOM_TO)]})
        # Position rides WITH the scale: the face has to hold still while the frame closes in, so the
        # correction is keyframed at the same two times, not set once at the end.
        a0 = _seg_anchor(anchors, 0)
        if a0 and a0[2] > 0:
            x_from, y_from = anchor_transform(a0[0], a0[1], INTRO_ZOOM_FROM, a0[2])
            x_to, y_to = anchor_transform(a0[0], a0[1], INTRO_ZOOM_TO, a0[2])
            for prop, v0, v1 in (("KFTypePositionX", x_from, x_to), ("KFTypePositionY", y_from, y_to)):
                kfs.append({"id": _nid(), "material_id": "", "property_type": prop,
                            "keyframe_list": [_kf(src0, v0), _kf(t_end, v1)]})
            s.setdefault("clip", {})["transform"] = {"x": x_to, "y": y_to}
            n_anchored += 1
        s["common_keyframes"] = kfs
        s.setdefault("clip", {})["scale"] = {"x": INTRO_ZOOM_TO, "y": INTRO_ZOOM_TO}   # hold end value (both axes)
        n_zoom = 1

    # 2) rotating jump-cut punches on later clips (only ones still untouched)
    if punches:
        for i in range(PUNCH_START_INDEX, len(segs), PUNCH_EVERY_NTH):
            if not _untouched(segs[i]):
                continue
            val = PUNCH_SCALE_POOL[n_punch % len(PUNCH_SCALE_POOL)]
            clip = segs[i].setdefault("clip", {})
            sc = clip.setdefault("scale", {"x": 1.0, "y": 1.0})
            sc["x"] = val
            sc["y"] = val
            ai = _seg_anchor(anchors, i)
            if ai and ai[2] > 0:        # a static bump still enlarges about the centre without this
                tx, ty = anchor_transform(ai[0], ai[1], val, ai[2])
                clip["transform"] = {"x": tx, "y": ty}
                n_anchored += 1
            n_punch += 1

    moved = n_zoom + n_punch
    if moved and not n_anchored:
        print("[motion] WARNING: no face anchors - all %d moves are CENTRED on the frame. If the "
              "creator does not sit centre, every push-in slides her toward the edge. Measure with: "
              "uv run workflows/head-framing.py <base> --windows @caption-plan.json "
              "--out projects/<job>/face-anchors.json" % moved)
    elif n_anchored:
        print(f"[motion] {n_anchored}/{moved} moves reframed on her face in that shot")
    return (n_zoom, n_punch)
