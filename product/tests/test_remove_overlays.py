#!/usr/bin/env python3
"""test_remove_overlays.py — regression guard for finalize-proof overlay matching (Bug #6).

finalize's magnet (capcut_ripple.enforce_maintrack_ripple) blanks every non-main track's name to "", so
remove-overlays' old name-only match found nothing on any real (finalized) draft — it silently removed 0.
This proves the matcher removes a finalized overlay (name "" + flag==2 + material_name) while keeping the
footage track and unrelated overlays. Pure — no CapCut, no files. Run: python3 product/tests/test_remove_overlays.py
"""
import os, importlib.util
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

_spec = importlib.util.spec_from_file_location(
    "remove_overlays", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "remove-overlays.py"))
ro = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ro)


def _draft():
    """A draft AS FINALIZE LEFT IT: the footage track anchored (name "", flag 0) and the injected caption
    overlay with its name blanked by the magnet (name "", flag 2) but its material_name intact."""
    return {
        "materials": {"videos": [
            {"id": "matFOOT", "material_name": "video_0"},          # footage material
            {"id": "matCAP",  "material_name": "captions_overlay"},  # the injected overlay's material
            {"id": "matGIF",  "material_name": "gif_overlay"},       # a second, unrelated overlay
        ]},
        "tracks": [
            {"type": "video", "flag": 0, "name": "", "is_default_name": False,   # MAIN footage (keep)
             "segments": [{"material_id": "matFOOT"}]},
            {"type": "video", "flag": 2, "name": "", "is_default_name": True,    # caption overlay (remove)
             "segments": [{"material_id": "matCAP"}]},
            {"type": "video", "flag": 2, "name": "", "is_default_name": True,    # gif overlay (keep — not asked)
             "segments": [{"material_id": "matGIF"}]},
            {"type": "audio", "flag": 0, "name": "", "segments": [{"material_id": "matA"}]},  # audio (keep)
        ],
    }


def run():
    d = _draft()

    # name-only match (the old behavior) would find NOTHING here — every non-main name is "":
    old = [t for t in d["tracks"] if t.get("type") == "video" and t.get("name") in {"captions_overlay"}]
    assert old == [], "sanity: on a finalized draft, name-only matching finds nothing — that was Bug #6"

    # the fix matches the finalized overlay by flag==2 + material_name:
    kept = ro.tracks_after_removal(d, {"captions_overlay"})
    kept_mats = [t["segments"][0]["material_id"] for t in kept if t["type"] == "video"]
    assert "matCAP" not in kept_mats, "captions_overlay track MUST be removed on a finalized draft"
    assert "matFOOT" in kept_mats, "footage track must always be kept"
    assert "matGIF" in kept_mats, "an overlay NOT named must be kept"
    assert any(t["type"] == "audio" for t in kept), "audio track must be kept"
    assert len(kept) == len(d["tracks"]) - 1, "exactly one track removed"

    # still works the old way too (a not-yet-finalized draft that still has a real track name):
    d2 = _draft(); d2["tracks"][1]["name"] = "captions_overlay"; d2["tracks"][1]["flag"] = 0
    kept2 = ro.tracks_after_removal(d2, {"captions_overlay"})
    assert all(t["segments"][0]["material_id"] != "matCAP" for t in kept2 if t["type"] == "video"), \
        "pre-finalize name match must still work"

    # removing multiple named overlays at once:
    kept3 = ro.tracks_after_removal(_draft(), {"captions_overlay", "gif_overlay"})
    vmats = [t["segments"][0]["material_id"] for t in kept3 if t["type"] == "video"]
    assert vmats == ["matFOOT"], f"both named overlays removed, footage kept, got {vmats}"

    print("✓ remove-overlays: matches finalized overlays by flag==2 + material_name, keeps footage/audio/unnamed")


def run_safety():
    """FAIL-LOUD contract (handoff §2.11): the tool must never fall back to a bundled sample draft or exit 0
    having silently done nothing. `_require_draft` must raise SystemExit when CAPCUT_DRAFT is unset and when
    the named draft folder does not exist."""
    import os as _os

    saved = _os.environ.pop("CAPCUT_DRAFT", None)
    try:
        # unset -> hard error (never a "Kids" default)
        try:
            ro._require_draft(); assert False, "unset CAPCUT_DRAFT must raise SystemExit, not default"
        except SystemExit as e:
            assert "CAPCUT_DRAFT" in str(e), f"error must name the missing env var, got {e!r}"

        # set but nonexistent folder -> hard error (never exit 0 silently)
        _os.environ["CAPCUT_DRAFT"] = "definitely-not-a-real-draft-xyz-0000"
        try:
            ro._require_draft(); assert False, "missing draft folder must raise SystemExit, not no-op"
        except SystemExit as e:
            assert "not found" in str(e), f"error must say the draft was not found, got {e!r}"
    finally:
        _os.environ.pop("CAPCUT_DRAFT", None)
        if saved is not None:
            _os.environ["CAPCUT_DRAFT"] = saved

    # --help returns without doing any work (no env, no CapCut check reached)
    ro.main(["--help"])
    print("✓ remove-overlays: fails loudly on unset/unknown draft; --help is a safe no-op")


if __name__ == "__main__":
    run()
    run_safety()
