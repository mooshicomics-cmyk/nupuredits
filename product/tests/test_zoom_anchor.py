#!/usr/bin/env python3
"""test_zoom_anchor.py — regression guard for FACE-ANCHORED ZOOMS.

The bug this locks down (first PC test reel, 2026-09-17): every zoom was anchored to the FRAME
CENTRE. `product/capcut_motion.py` wrote clip.scale and never clip.transform; `product/build-reel-mp4.py`
cropped at `(zw - W) // 2`. A creator who does not sit dead centre therefore got enlarged-middle-of-the-
room and slid toward the edge on every push-in — reported as "the zooms go off to the side", and the
single worst creative complaint of that build. Her measured face sat at x=0.62 and moved 0.14 of the
frame width between takes, which is also why ONE anchor for the whole reel is not a fix.

Run:  python3 product/tests/test_zoom_anchor.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capcut_motion as cm
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

US = 1_000_000
FACES = [(0.619, 0.409), (0.508, 0.445), (0.652, 0.422), (0.9, 0.1), (0.5, 0.5)]
SCALES = [1.06, 1.09, 1.22, 1.5, 1.9]


def _draft(n):
    return {"materials": {"videos": []}, "tracks": [{"type": "video", "segments": [
        {"material_id": "", "source_timerange": {"start": 0, "duration": 2 * US},
         "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}},
         "common_keyframes": []} for _ in range(n)]}]}


def test_anchor_holds_the_face_still():
    """The whole point: at any scale, the anchored point must not move."""
    for fx, fy in FACES:
        for S in SCALES:
            tx, ty = cm.anchor_transform(fx, fy, S)
            # frame-normalised: scale about centre, then shift by transform/2 (transform is
            # HALF-canvas units, and +y is UP while screen y runs down)
            x = 0.5 + (fx - 0.5) * S + tx / 2.0
            y = 0.5 + (fy - 0.5) * S - ty / 2.0
            assert abs(x - fx) < 1e-6 and abs(y - fy) < 1e-6, \
                f"face moved: ({fx},{fy}) at {S} landed at ({x:.4f},{y:.4f})"
            assert abs(tx) <= S - 1 + 1e-9 and abs(ty) <= S - 1 + 1e-9, \
                f"transform {tx},{ty} at scale {S} would expose a frame edge"
    assert cm.anchor_transform(0.5, 0.5, 1.22) == (0.0, 0.0), "a centred face must need no correction"
    print("✓ anchor_transform holds the face still at every scale, without exposing an edge")


def test_zoom_writes_position_on_the_scale_clock():
    """A keyframed zoom must keyframe POSITION too, at the same times — otherwise the face drifts
    across the push-in even when the end state is right."""
    d = _draft(12)
    cm.apply_default_motion(d, anchors=(0.619, 0.409))
    kfs = d["tracks"][0]["segments"][0]["common_keyframes"]
    props = {k["property_type"] for k in kfs}
    assert {"KFTypeScaleX", "KFTypeScaleY", "KFTypePositionX", "KFTypePositionY"} <= props, \
        f"intro zoom is missing position keyframes: {sorted(props)}"
    times = {p: [k["time_offset"] for k in kf["keyframe_list"]]
             for p in props for kf in kfs if kf["property_type"] == p}
    assert times["KFTypePositionX"] == times["KFTypeScaleX"], \
        "position keyframes must ride the same clock as the scale keyframes"
    assert times["KFTypePositionY"] == times["KFTypeScaleY"]
    print("✓ the intro zoom keyframes position in lockstep with scale")


def test_every_default_move_is_anchored():
    d = _draft(12)
    z, p = cm.apply_default_motion(d, anchors=(0.619, 0.409))
    segs = d["tracks"][0]["segments"]
    moved = [i for i, s in enumerate(segs) if s["clip"]["scale"]["x"] != 1.0 or s["common_keyframes"]]
    assert len(moved) == z + p > 0
    for i in moved:
        tr = segs[i]["clip"].get("transform", {})
        assert tr.get("x") or tr.get("y"), f"clip {i} was zoomed but left centre-anchored"
    print(f"✓ all {len(moved)} default moves carry a face anchor")


def test_per_shot_anchors_differ():
    """One anchor for the whole reel is not the fix: she re-frames between takes."""
    d = _draft(12)
    per_shot = {0: (0.35, 0.40), 2: (0.62, 0.41), 5: (0.51, 0.45), 8: (0.70, 0.38), 11: (0.62, 0.41)}
    cm.apply_default_motion(d, anchors=per_shot)
    segs = d["tracks"][0]["segments"]
    xs = {i: segs[i]["clip"]["transform"]["x"] for i in per_shot if segs[i]["clip"].get("transform")}
    assert len(set(round(v, 5) for v in xs.values())) > 1, "every shot got the same correction"
    assert xs[0] > 0, "a face LEFT of centre must be corrected the other way"
    assert xs[2] < 0, "a face RIGHT of centre must be pulled back left"
    print("✓ anchors are per shot, and correct in both directions")


def test_creator_edits_are_never_clobbered():
    d = _draft(12)
    segs = d["tracks"][0]["segments"]
    segs[0]["clip"]["transform"] = {"x": -0.30, "y": 0.0}      # she nudged this clip by hand
    segs[2]["clip"]["scale"] = {"x": 1.5, "y": 1.5}            # she zoomed this one by hand
    z, _p = cm.apply_default_motion(d, anchors=(0.62, 0.41))
    assert z == 0, "added an intro zoom over a clip the creator had already repositioned"
    assert segs[0]["clip"]["transform"] == {"x": -0.30, "y": 0.0}
    assert segs[2]["clip"]["scale"] == {"x": 1.5, "y": 1.5}
    print("✓ hand-positioned and hand-zoomed clips are left alone")


def test_idempotent():
    d = _draft(12)
    first = cm.apply_default_motion(d, anchors=(0.62, 0.41))
    second = cm.apply_default_motion(d, anchors=(0.62, 0.41))
    assert first != (0, 0) and second == (0, 0), "a second pass must add nothing"
    print("✓ idempotent")


def test_bake_crop_keeps_the_face_put():
    """The ffmpeg lane, same guarantee: crop a 1/z window at fx*(W-cw) and the face keeps its
    place in the output. The old centre crop is included to show it does not."""
    W, H, z = 1080, 1920, 1.22
    cw, ch = int(round(W / z)) // 2 * 2, int(round(H / z)) // 2 * 2
    worst_new = worst_old = 0.0
    for fx, fy in FACES:
        cx = max(0, min(W - cw, int(round(fx * (W - cw)))))
        cy = max(0, min(H - ch, int(round(fy * (H - ch)))))
        worst_new = max(worst_new, abs((fx * W - cx) / cw - fx) * W, abs((fy * H - cy) / ch - fy) * H)
        ox, oy = (W - cw) // 2, (H - ch) // 2
        worst_old = max(worst_old, abs((fx * W - ox) / cw - fx) * W)
    assert worst_new < 1.5, f"anchored crop moved the face {worst_new:.1f}px"
    assert worst_old > 20, "expected the centre crop to visibly drift an off-centre face"
    print(f"✓ anchored crop holds the face within {worst_new:.1f}px "
          f"(the old centre crop drifted it up to {worst_old:.0f}px)")


def test_strength_damps_toward_a_plain_centre_zoom():
    """A static anchor only holds a subject who holds still. When the measurement cannot be trusted
    — she moves during the shot, or only the whole-cut median was available — the correction has to
    fade out rather than commit. Verified the hard way: at 160% a full correction from a stale
    anchor pushed the subject PAST centre the other way, framing her worse than no correction."""
    fx, fy, S = 0.66, 0.41, 1.6
    full = cm.anchor_transform(fx, fy, S, 1.0)
    half = cm.anchor_transform(fx, fy, S, 0.5)
    none = cm.anchor_transform(fx, fy, S, 0.0)
    assert none == (0.0, 0.0), "strength 0 must be an ordinary centre zoom"
    assert abs(half[0]) < abs(full[0]) and abs(half[1]) < abs(full[1]), "strength must damp"
    assert abs(round(half[0] - full[0] / 2, 6)) < 1e-6, "damping should be linear in strength"
    print("✓ low confidence damps the correction back toward a centre zoom")


def test_anchor_entries_may_carry_confidence():
    d = _draft(12)
    cm.apply_default_motion(d, anchors=(0.66, 0.41, 0.0))     # measured, but not trustworthy
    segs = d["tracks"][0]["segments"]
    assert all(not s["clip"].get("transform", {}).get("x") for s in segs), \
        "a zero-confidence anchor must not move anything"
    d2 = _draft(12)
    cm.apply_default_motion(d2, anchors=(0.66, 0.41, 1.0))
    assert d2["tracks"][0]["segments"][0]["clip"]["transform"]["x"] < 0
    print("✓ anchors carry a confidence, and a worthless one is ignored")


if __name__ == "__main__":
    for fn in (test_anchor_holds_the_face_still, test_zoom_writes_position_on_the_scale_clock,
               test_every_default_move_is_anchored, test_per_shot_anchors_differ,
               test_creator_edits_are_never_clobbered, test_idempotent,
               test_bake_crop_keeps_the_face_put, test_strength_damps_toward_a_plain_centre_zoom,
               test_anchor_entries_may_carry_confidence):
        fn()
    print("\nzoom anchor: all checks passed")
