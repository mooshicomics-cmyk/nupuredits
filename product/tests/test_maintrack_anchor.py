#!/usr/bin/env python3
"""test_maintrack_anchor.py — regression guard for the CapCut magnet (main-track ripple).

Root cause (2026-08-12): the magnet needs an ANCHOR. The main footage track must be
`is_default_name=False` (fixed identity) while overlay/text/audio tracks are `is_default_name=True`
(floating, adsorbing). A prior version set the MAIN track to True, so CapCut had no anchor and NOTHING
rippled — even though every magnet flag was set. It shipped clean-looking and the bug was silent.

This test runs the SHIPPED enforce/verify and proves: (1) a correctly enforced draft passes, and (2) the
exact planted regression is caught. Wired into the ship gate so it can never regress unnoticed.

Run standalone:  python3 product/tests/test_maintrack_anchor.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from capcut_ripple import enforce_maintrack_ripple, verify_maintrack_anchor
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _draft():
    # a realistic multi-segment cut: main footage + audio(sfx) + text + one video overlay (b-roll)
    return {"tracks": [
        {"type": "video", "name": "", "is_default_name": True, "flag": 0, "segments": [0] * 28},
        {"type": "audio", "name": "sfx0", "is_default_name": False, "segments": [0] * 6},
        {"type": "text",  "name": "t_abc", "is_default_name": False, "segments": [0]},
        {"type": "video", "name": "broll", "is_default_name": False, "flag": 2, "segments": [0] * 2},
    ]}


def run():
    # 1. enforce → correctly anchored, magnet on, passes verify
    d = _draft(); enforce_maintrack_ripple(d)
    assert verify_maintrack_anchor(d) == [], "enforced build must pass verify"
    main = max((t for t in d["tracks"] if t["type"] == "video"), key=lambda t: len(t["segments"]))
    assert main["is_default_name"] is False, "main must be the anchor (False)"
    assert all(t["is_default_name"] is True for t in d["tracks"] if t is not main), "overlays must float (True)"
    assert d["config"]["maintrack_adsorb"] is True and d["free_render_index_mode_on"] is False

    # 2. plant the anchor regression → must be caught
    d = _draft(); enforce_maintrack_ripple(d)
    max((t for t in d["tracks"] if t["type"] == "video"), key=lambda t: len(t["segments"]))["is_default_name"] = True
    assert any("MAIN track is_default_name" in p for p in verify_maintrack_anchor(d)), "must catch anchor regression"

    # 3. plant a magnet-config regression → must be caught
    d = _draft(); enforce_maintrack_ripple(d); d["config"]["maintrack_adsorb"] = False
    assert any("maintrack_adsorb" in p for p in verify_maintrack_anchor(d)), "must catch magnet-config regression"

    # 4. enforce is idempotent (running it twice stays anchored + never raises)
    d = _draft(); enforce_maintrack_ripple(d); enforce_maintrack_ripple(d)
    assert verify_maintrack_anchor(d) == [], "enforce must be idempotent"

    # 5. self-verify must NOT false-raise on an audio-only draft (nothing to anchor)
    audio_only = {"tracks": [{"type": "audio", "name": "a", "is_default_name": False, "segments": [0]}]}
    enforce_maintrack_ripple(audio_only)  # must not raise

    print("✓ maintrack anchor: fix correct + fail-safe catches the planted regression + self-verify guards every path")


if __name__ == "__main__":
    run()
