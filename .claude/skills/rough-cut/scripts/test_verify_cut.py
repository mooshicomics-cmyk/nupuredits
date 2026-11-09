#!/usr/bin/env python3
"""test_verify_cut.py — regression guard for the cut-verifier fail-safe (verify-cut.py).

Proves the two detectors catch the exact 2026-08-12 bugs (a WhisperX-mis-stamped stumble that leaked
into the cut, and a multi-word audio/plan mismatch) AND do NOT false-fire on an intentional spaced
repeat ("closer and closer"). Pure — exercises find_problems() with synthetic token streams, no ASR.

Run: python3 test_verify_cut.py
"""
import os, importlib.util
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

_spec = importlib.util.spec_from_file_location(
    "verify_cut", os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-cut.py"))
vc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(vc)


def toks(words):
    return [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(words)]


def run():
    bounds = [(30.0, 18)]

    # 1. STUMBLE: rendered audio has a doubled "thing" the plan spells once ("here's the thing thing")
    intended = "and here's the thing you're probably".split()
    itag = [18] * len(intended)
    rtok = toks("and here's the thing thing you're probably".split())
    fl = vc.find_problems(intended, itag, rtok, bounds)
    assert any(f["kind"] == "stumble" for f in fl), f"must catch the doubled-word stumble, got {fl}"

    # 2. MISALIGNMENT: the cut plays multi-word different audio than the plan text
    intended = "your target is not profitable".split(); itag = [17] * 5
    rtok = toks("your target is most aligned today".split())
    fl = vc.find_problems(intended, itag, rtok, bounds)
    assert any(f["kind"] == "mismatch" for f in fl), f"must catch the audio!=plan mismatch, got {fl}"

    # 3. NO FALSE POSITIVE on an intentional spaced repeat ("closer and closer")
    intended = "every dart lands closer and closer to this center".split()
    itag = [20] * len(intended)
    rtok = toks(intended)
    fl = vc.find_problems(intended, itag, rtok, bounds)
    assert fl == [], f"intentional spaced repeat must NOT flag, got {fl}"

    # 4. Clean exact match → nothing
    intended = "one's throwing everything one's throwing nothing".split()
    itag = [10] * len(intended)
    fl = vc.find_problems(intended, itag, toks(intended), bounds)
    assert fl == [], f"clean cut must pass, got {fl}"

    # 5. A repeat the plan wrote as ONE hyphenated word is how she said it (Bulgarian "много-много",
    #    "a lot"); the same repeat written spaced in the plan is still a stumble.
    plan = "когато плетеш много-много от конци".split()
    intended = [t for w in plan for t in vc.norm_tokens(w)]
    itag = [7] * len(intended)
    fl = vc.find_problems(intended, itag, toks(intended), bounds, vc.hyphen_repeats(plan))
    assert fl == [], f"hyphenated reduplication must NOT flag, got {fl}"
    intended = "and the the thing".split()
    fl = vc.find_problems(intended, [3] * 4, toks(intended), bounds, vc.hyphen_repeats(intended))
    assert any(f["kind"] == "stumble" for f in fl), f"a spaced repeat in the plan is still a stumble, got {fl}"

    print("✓ verify-cut: catches stumble + mismatch, ignores intentional spaced repeats")


if __name__ == "__main__":
    run()
