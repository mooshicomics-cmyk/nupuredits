#!/usr/bin/env python3
"""test_set_overlay.py — regression guard for §20: updating an overlay layer must PRESERVE the creator's
in-app CapCut work (transform/scale/keyframes), not reset it to defaults.

The bug this locks down: build-overlay.py used to delete the overlay track and recreate it from scratch on
every update, silently resetting her hand-set scale (57.4%) + offset back to y=0 / scale=1.0. build-overlay
is now an idempotent set-overlay: update-in-place when the track exists, create only when it does not.

Run: JOB=x CAPCUT_DRAFT=x python3 product/tests/test_set_overlay.py  (the env is set below before import)
"""
import os, sys, json, tempfile, importlib.util

os.environ.setdefault("JOB", "unit-test")
os.environ.setdefault("CAPCUT_DRAFT", "unit-test-draft")
sys.argv = ["build-overlay.py", "/tmp/unit-test/captions.mov", "captions_overlay"]

_spec = importlib.util.spec_from_file_location(
    "build_overlay", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build-overlay.py"))
bo = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bo)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from capcut_ripple import enforce_maintrack_ripple   # magnet the fixture drafts (same rule every draft-writer follows)
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _draft_with_tweaked_overlay():
    """A draft where the creator has ALREADY scaled + offset + keyframed the caption overlay in CapCut."""
    foot_mat = {"id": "matFOOT", "path": "/abs/footage.mov", "material_name": "video_0",
                "extra_material_refs": [], "duration": 90_000_000, "width": 1080, "height": 1920}
    ov_mat = {"id": "matOV", "path": "/abs/old-captions.mov", "material_name": "captions_overlay",
              "extra_material_refs": [], "duration": 90_000_000, "width": 1080, "height": 1920}
    def fseg(i):
        return {"id": f"F{i}", "material_id": "matFOOT", "extra_material_refs": [],
                "target_timerange": {"start": i*1000, "duration": 1000},
                "source_timerange": {"start": i*1000, "duration": 1000},
                "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}},
                "common_keyframes": [], "keyframe_refs": [], "volume": 1.0}
    tweaked = {"id": "OVSEG", "material_id": "matOV", "extra_material_refs": [],
               "target_timerange": {"start": 0, "duration": 90_000_000},
               "source_timerange": {"start": 0, "duration": 90_000_000},
               # THE CREATOR'S HAND WORK — must survive an update:
               "clip": {"scale": {"x": 0.574, "y": 0.574}, "transform": {"x": 0.0, "y": -240.0}},
               "common_keyframes": [{"id": "KF1", "property_type": "KFTypeScaleX", "keyframe_list": [1, 2]}],
               "keyframe_refs": [], "volume": 0.0, "render_index": 14000,
               "segment_color_tag": 3, "desc": "my hero graphics"}
    return {
        "materials": {"videos": [foot_mat, ov_mat]},
        "tracks": [
            {"type": "video", "flag": 0, "name": "", "is_default_name": False, "segments": [fseg(0), fseg(1)]},
            {"type": "video", "flag": 2, "name": "captions_overlay", "is_default_name": False, "segments": [tweaked]},
        ],
    }


def run():
    d = _draft_with_tweaked_overlay()
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(d, tf); tf.close()

    # UPDATE the caption layer with a new .mov (same one span) — this is the re-inject that used to nuke her work.
    n, mode = bo.inject(tf.name, ov_dur=90_000_000, spans=[(0.0, 90.0)])
    out = json.load(open(tf.name, encoding="utf-8"))
    os.unlink(tf.name)

    assert mode == "updated-in-place", f"existing track must update IN PLACE, got mode={mode!r}"
    ov = [t for t in out["tracks"] if t["type"] == "video" and any(s.get("desc") == "my hero graphics" for s in t["segments"])]
    assert ov, "the creator's overlay segment must still exist after the update"
    seg = ov[0]["segments"][0]
    assert seg["clip"]["scale"]["x"] == 0.574, f"her SCALE must be preserved, got {seg['clip']['scale']}"
    assert seg["clip"]["transform"]["y"] == -240.0, f"her OFFSET must be preserved, got {seg['clip']['transform']}"
    assert seg["common_keyframes"], "her KEYFRAMES must be preserved"
    assert seg["segment_color_tag"] == 3 and seg["desc"] == "my hero graphics", "her label/notes must be preserved"
    # and the media was actually repointed to the NEW overlay material (material_name kept for re-find):
    new_mid = seg["material_id"]
    new_mat = next(m for m in out["materials"]["videos"] if m["id"] == new_mid)
    assert new_mat["material_name"] == "captions_overlay", "repointed material must keep the track's material_name"
    assert new_mat["id"] != "matOV", "must point at the NEW material, not the old one"
    print("✓ set-overlay: updating an existing layer preserves scale/offset/keyframes/labels, repoints media in place")

    # And a NON-existent track creates fresh (mode 'created'):
    d2 = _draft_with_tweaked_overlay()
    d2["tracks"] = [d2["tracks"][0]]                      # drop the overlay track → nothing to update
    tf2 = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(d2, tf2); tf2.close()
    n2, mode2 = bo.inject(tf2.name, ov_dur=90_000_000, spans=[(0.0, 90.0)])
    os.unlink(tf2.name)
    assert mode2 == "created", f"a missing track must be CREATED, got mode={mode2!r}"
    print("✓ set-overlay: a missing layer is created fresh (mode 'created')")


if __name__ == "__main__":
    run()
