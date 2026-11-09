#!/usr/bin/env python3
"""test_draft_safety.py — regression guard for the CapCut recycle→restore→duplicate round trip.

This area produced two silent-failure bugs in a row that both "looked correct" on read-through (QA
2026-09-06): recycle() discarded the exact registry entry so a draft could never reappear (Bug #7), and the
first restore() used a glob whose literal '[recycled ...]' brackets matched zero files (Bug #7a). Both were
caught only by running the REAL round trip. This test IS that round trip, automated, including the bracket
edge case explicitly — so neither can regress silently again.

Runs entirely on a temp CapCut root (monkeypatches draft_safety.CAP) with the quit-guard bypassed. No real
CapCut, no real drafts. Run: python3 product/tests/test_draft_safety.py
"""
import os, json, glob, tempfile, shutil, importlib.util
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

_spec = importlib.util.spec_from_file_location(
    "draft_safety", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "draft_safety.py"))
ds = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ds)


def _make_draft(cap, name, draft_id):
    """A minimal on-disk draft + its root_meta_info registry entry (the real field shape)."""
    fold = os.path.join(cap, name)
    os.makedirs(fold, exist_ok=True)
    json.dump({"tracks": []}, open(os.path.join(fold, "draft_info.json"), "w", encoding="utf-8"))
    json.dump({"draft_id": draft_id, "draft_name": name},
              open(os.path.join(fold, "draft_meta_info.json"), "w", encoding="utf-8"))
    return {
        "draft_name": name, "draft_id": draft_id, "draft_root_path": cap,
        "draft_fold_path": fold, "draft_json_file": os.path.join(fold, "draft_info.json"),
        "draft_cover": os.path.join(fold, "draft_cover.jpg"), "tm_draft_modified": 111,
    }


def _registry(cap):
    return json.load(open(os.path.join(cap, "root_meta_info.json"), encoding="utf-8"))["all_draft_store"]


def _names(cap):
    return {e["draft_name"] for e in _registry(cap)}


def run():
    os.environ["CAPCUT_ALLOW_OPEN"] = "1"   # bypass the CapCut-running guard: this uses a temp registry
    cap = tempfile.mkdtemp(prefix="draftsafety-test-")
    ds.CAP = cap                            # every function reads the module global — reassign it to the temp root
    try:
        rp = os.path.join(cap, "root_meta_info.json")
        e_keep = _make_draft(cap, "Reel", "ID-KEEP")
        e_gone = _make_draft(cap, "Reel 1.1", "ID-GONE")
        json.dump({"all_draft_store": [e_keep, e_gone]}, open(rp, "w", encoding="utf-8"))

        # ── 1. recycle: folder moves to the bin, registry entry removed, EXACT entry stashed as a sidecar ──
        dst = ds.recycle("Reel 1.1")
        assert not os.path.isdir(os.path.join(cap, "Reel 1.1")), "recycled folder must leave CAP"
        assert "Reel 1.1" not in _names(cap), "recycled draft must leave the registry"
        assert "Reel" in _names(cap), "recycle must not touch OTHER drafts"
        assert os.path.isdir(dst) and "[recycled " in os.path.basename(dst) and dst.endswith("]"), \
            f"recycled folder name must carry the literal bracket tag, got {dst!r}"
        sidecar = json.load(open(os.path.join(dst, ds._ENTRY_SIDECAR), encoding="utf-8"))
        assert sidecar["entry"] == e_gone, "sidecar must hold the EXACT removed registry entry (Bug #7)"

        # ── 1a. bracket edge case: glob CANNOT find it, our listdir matcher CAN (Bug #7a) ──
        assert glob.glob(os.path.join(cap, ".recycle_bin", "Reel 1.1 [recycled *]")) == [], \
            "sanity: glob with literal brackets matches nothing — that was the Bug #7a trap"
        assert ds._find_recycled("Reel 1.1") == dst, "listdir/startswith matcher MUST find the bracketed folder"

        # ── 2. restore: folder + EXACT entry come back, sidecar cleaned up ──
        back = ds.restore_draft("Reel 1.1")
        assert os.path.isdir(back) and back == os.path.join(cap, "Reel 1.1"), "folder must return to CAP/<name>"
        assert not os.path.exists(os.path.join(dst, ds._ENTRY_SIDECAR)), "sidecar must be cleaned up"
        assert not os.path.isdir(dst), "recycled folder must no longer exist after restore"
        restored = next(e for e in _registry(cap) if e["draft_name"] == "Reel 1.1")
        assert restored == e_gone, "restored registry entry must be IDENTICAL to the original (byte-for-byte)"

        # ── 3. restore refuses to clobber a LIVE draft of the same name ──
        ds.recycle("Reel 1.1")
        _make_draft(cap, "Reel 1.1", "ID-LIVE-AGAIN")   # a live draft reclaims the name
        try:
            ds.restore_draft("Reel 1.1"); assert False, "restore over a live draft must raise"
        except RuntimeError:
            pass
        shutil.rmtree(os.path.join(cap, "Reel 1.1"))     # clear the live one, then the restore succeeds
        ds.restore_draft("Reel 1.1")
        assert "Reel 1.1" in _names(cap)

        # ── 4. no-sidecar fallback (a draft recycled BEFORE the fix shipped) still re-registers ──
        d2 = ds.recycle("Reel 1.1")
        os.remove(os.path.join(d2, ds._ENTRY_SIDECAR))   # simulate a pre-fix recycle: no sidecar
        ds.restore_draft("Reel 1.1")
        rec = next(e for e in _registry(cap) if e["draft_name"] == "Reel 1.1")
        assert rec["draft_id"] == "ID-GONE", "fallback must recover the real draft_id from draft_meta_info.json"
        assert rec["draft_fold_path"] == os.path.join(cap, "Reel 1.1"), "fallback must rewrite the fold path"

        # ── 5. duplicate: a real copy + its own registry entry, original untouched ──
        new = ds.duplicate_draft("Reel")
        assert new == "Reel 1.1" or new.startswith("Reel "), f"duplicate should pick a version name, got {new}"
        # 'Reel 1.1' already exists from the restore, so next_version skips it:
        assert os.path.isdir(os.path.join(cap, new)) and os.path.isdir(os.path.join(cap, "Reel")), \
            "both the copy and the ORIGINAL must exist"
        dup = next(e for e in _registry(cap) if e["draft_name"] == new)
        assert dup["draft_id"] != e_keep["draft_id"], "the duplicate must get a FRESH draft_id, not the source's"
        assert dup["draft_fold_path"] == os.path.join(cap, new), "duplicate entry must point at the copy's folder"
        try:
            ds.duplicate_draft("Reel", new); assert False, "duplicating onto an existing name must refuse"
        except RuntimeError:
            pass

        print("✓ draft_safety: recycle→restore byte-for-byte (sidecar + fallback), bracket-safe lookup, "
              "refuse-clobber, duplicate registers a fresh copy")
    finally:
        shutil.rmtree(cap, ignore_errors=True)
        os.environ.pop("CAPCUT_ALLOW_OPEN", None)


if __name__ == "__main__":
    run()
