#!/usr/bin/env python3
"""Regression guard for audio_levels — the shared module every format uses to decide how loud a cue is.

The bug this locks down: SFX level used to be a bare `gain_db` offset (or a bare `volume` multiplier),
applied to whatever level the file happened to have. The bundled SFX span ~20 dB of intrinsic level, so one
number made `pop` audible and `keyboard_typing` inaudible — and it failed SILENTLY, shipping reels with no
sound design.

Run: python3 product/tests/test_audio_levels.py
"""
import os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import audio_levels as AL

import capcut_sfx   # resolve cues the way the ENGINE does, so this is valid on a buyer machine too
SFX_DIR = os.path.join(os.path.dirname(HERE), "creative-vault", "sfx")
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def main():
    # The creator's own sfx/ ships EMPTY by design, so glob it AND fall back to the engine's palette
    # (which layers in the bundled Pixabay library). Otherwise this test only passes on the author's machine.
    files = sorted(set(glob.glob(os.path.join(SFX_DIR, "*.mp3"))) | set(capcut_sfx.palette().values()))
    if not files:
        print("no SFX resolvable at all — neither the local folder nor the bundled library")
        return 1
    print(f"audio_levels regression ({len(files)} bundled SFX)\n")

    # 1. the library really does span a wide intrinsic range — this is WHY a fixed offset cannot work.
    peaks = {f: AL.peak_dbfs(f) for f in files}
    peaks = {f: v for f, v in peaks.items() if v is not None}
    spread = max(peaks.values()) - min(peaks.values())
    check("library has a real level spread (a fixed offset cannot work)", spread > 4.0,
          f"spread only {spread:.1f} dB")

    # 2. THE CORE GUARANTEE: after auto-levelling, every cue lands at the same peak, whichever file.
    prog_peak = -1.0
    landed, clamped = {}, {}
    for f in peaks:
        g, lands, was_clamped = AL.sfx_landing(f, prog_peak)
        landed[f] = lands
        clamped[f] = was_clamped
    # A file too quiet to reach target is clamped ON PURPOSE (boosting it further raises its noise floor).
    # The guarantee is: everything that CAN hit target does, and anything that cannot is flagged.
    ok = {f: v for f, v in landed.items() if not clamped[f]}
    land_spread = max(ok.values()) - min(ok.values())
    check("every reachable cue auto-levels to the SAME peak (<=0.5 dB spread)", land_spread <= 0.5,
          f"still {land_spread:.1f} dB apart")
    check("cues too quiet to reach target are FLAGGED, not silently short",
          all(clamped[f] == (peaks[f] + AL.GAIN_MAX_DB < -7.0 - 0.05) for f in peaks))

    # 3. cues land where we asked: programme peak + duck
    target = prog_peak + AL.SFX_DUCK_DB
    worst = max(abs(landed[f] - target) for f in landed if not clamped[f])
    check(f"cues land at programme{AL.SFX_DUCK_DB:+.0f} dB = {target:.1f} dBFS", worst <= 0.5,
          f"off by {worst:.1f} dB")

    # 4. no cue lands inaudible (the actual shipped failure: >12 dB under the programme)
    quietest = min(landed.values())
    check("no cue lands inaudible vs the programme", quietest - prog_peak > -12.0,
          f"quietest is {quietest - prog_peak:.1f} dB under")

    # 5. with NO programme reference it still normalises (removes the spread on its own)
    solo = {f: AL.sfx_landing(f, None) for f in peaks}
    solo_ok = [v[1] for v in solo.values() if not v[2]]
    check("normalises even with no programme reference",
          (max(solo_ok) - min(solo_ok)) <= 0.5)

    # 6. an explicit level is still honoured, and gains stay in a sane band
    check("gain is clamped to a sane band",
          all(AL.GAIN_MIN_DB <= AL.sfx_gain_db(f, prog_peak) <= AL.GAIN_MAX_DB for f in peaks))
    check("to_linear round-trips 0 dB to unity", abs(AL.to_linear(0.0) - 1.0) < 1e-6)
    check("to_linear(-6 dB) is about 0.5", abs(AL.to_linear(-6.0) - 0.501) < 0.01)

    # 7. a bed is matched by MEAN, not peak (a continuous signal)
    bed = files[0]
    bg = AL.bed_gain_db(bed, -15.0)
    bed_lands = (AL.mean_dbfs(bed) or 0) + bg
    check("bed lands under the programme mean by the duck amount",
          abs(bed_lands - (-15.0 + AL.BED_DUCK_DB)) <= 0.5,
          f"landed {bed_lands:.1f} dBFS")

    print()
    if fails:
        print(f"FAILED: {len(fails)} — {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
