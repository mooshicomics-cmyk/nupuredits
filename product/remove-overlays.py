#!/usr/bin/env python3
"""remove-overlays.py — remove named OVERLAY video tracks from the migrated CapCut draft (both the root
and the Timelines/* copies), so we can re-inject fresh caption/intro layers. CapCut MUST be quit.

Usage:
    CAPCUT_DRAFT="<draft folder name>" python3 remove-overlays.py [track ...]

    CAPCUT_DRAFT is REQUIRED (the CapCut draft folder under
    ~/Movies/CapCut/User Data/Projects/com.lveditor.draft). There is NO default draft — a missing or
    unknown draft is a hard error, never a silent no-op (a silent default could modify the WRONG project).
    Positional args = the overlay track names to remove; with none given, the standard injected set
    (cap-single cap-build cap-takeover intro-kinetic) is used and echoed so it is never silent.

Matching is finalize-proof: finalize's magnet blanks every non-main track name to "", so besides the track
name we also match a PIP overlay by flag==2 + its material_name (which build-overlay stamps and the magnet
never clears). Name-only matching silently removed 0 on any finalized draft (Bug #6).
"""
import json, os, glob, subprocess, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capcut_ripple import enforce_maintrack_ripple   # re-anchor the magnet after removing tracks

# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
DEFAULT_NAMES = {"cap-single", "cap-build", "cap-takeover", "intro-kinetic"}  # the standard injected overlay set


def _is_overlay_to_remove(t, names, mat_name):
    """True if `t` is an injected overlay VIDEO track the caller asked to remove. Matched by track name
    (works BEFORE finalize) OR by the finalize-proof PIP signal: finalize's magnet
    (capcut_ripple.enforce_maintrack_ripple) BLANKS every non-main track's name to "", so on any draft this
    engine has actually finalized, name-matching alone finds nothing (it silently removed 0 — Bug #6). A PIP
    overlay is `flag==2`, and build-overlay.py stamps `material_name=<track>` on the overlay's own video
    material, which the magnet never touches — so match on that too. The base footage track is flag 0 and its
    material_name is not in `names`, so it is always kept."""
    if t.get("type") != "video":
        return False
    if t.get("name") in names:
        return True
    if t.get("flag") == 2:
        seg_mats = {mat_name.get(s.get("material_id"), "") for s in t.get("segments", [])}
        if seg_mats & names:
            return True
    return False


def tracks_after_removal(d, names):
    """The draft's tracks minus the overlay tracks named in `names`. Pure — no file I/O (testable)."""
    mat_name = {m.get("id"): m.get("material_name", "")
                for m in d.get("materials", {}).get("videos", []) if isinstance(m, dict)}
    return [t for t in d.get("tracks", []) if not _is_overlay_to_remove(t, names, mat_name)]


def clean(path, names):
    d = json.load(open(path, encoding="utf-8"))
    before = len(d["tracks"])
    d["tracks"] = tracks_after_removal(d, names)
    removed = before - len(d["tracks"])
    enforce_maintrack_ripple(d)                        # re-anchor the magnet after removing overlay tracks
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return removed


def _require_draft():
    """Resolve the target draft folder from CAPCUT_DRAFT and FAIL LOUDLY if it is unset or does not exist.
    A destructive-capable tool must never fall back to a bundled sample or exit 0 having silently done
    nothing to (or worse, the wrong) draft — that is exactly how a wrong invocation could modify a
    different customer project (handoff §2.11)."""
    draft = os.environ.get("CAPCUT_DRAFT")
    if not draft:
        sys.exit("[remove-overlays] Set CAPCUT_DRAFT=<the CapCut draft folder name> before running "
                 "(e.g. CAPCUT_DRAFT=\"my-reel 1.2\" python3 remove-overlays.py cap-single ...). "
                 "Refusing to silently fall back to a bundled sample reel.")
    d = f"{CAP}/{draft}"
    if not os.path.isdir(d):
        sys.exit(f"[remove-overlays] draft {draft!r} not found at {d} — nothing removed. "
                 f"Check the draft folder name (CAPCUT_DRAFT). Refusing to exit silently.")
    return draft, d


def main(argv):
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return
    # The shared guard, on both platforms. The Windows branch that stood here returned straight after asking
    # tasklist, so on a PC this removed nothing and still exited 0, whether CapCut was open or not.
    _ds.require_capcut_quit("remove overlay tracks from this draft")
    draft, D = _require_draft()
    names = set(argv) or set(DEFAULT_NAMES)
    files = _ds.draft_json_copies(D, require=False)
    if not files:
        sys.exit(f"[remove-overlays] draft {draft!r} exists at {D} but has no CapCut timeline JSON "
                 f"({' or '.join(_ds.DRAFT_JSON_NAMES)}) — nothing to do.")
    print(f"[remove-overlays] draft={draft!r} · removing overlay tracks {sorted(names)} · {len(files)} file(s)")
    total = 0
    for f in files:
        n = clean(f, names)
        total += n
        print(f"  removed {n} overlay track(s) -> {f}")
    print(f"[remove-overlays] done · draft={draft!r} · tracks removed={total}")


if __name__ == "__main__":
    main(sys.argv[1:])
