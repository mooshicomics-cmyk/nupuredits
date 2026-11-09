#!/usr/bin/env python3
"""snap-to-sound.py: a long word drawn out with a pause inside is one take, and two pieces of the same take never
share a slice of the pause between them.

A buyer report (2026-10-10, a 176-piece how-to cut), both found by the buyer's Claude:
  - "confines," (1.48 s, said once, drawn out) had a held quiet inside it, so the snap read it as two takes folded
    into one word and opened the next piece on the "second take": the cut clipped the word and she stretched the
    clip back by hand in CapCut
  - neighbouring pieces of the same take that each reached into one short pause both kept a slice of it, so that
    slice played twice: a small stutter at the join

  fold      a real restart (a short first take, then the whole word again) still reads as two takes; a long word
            whose part after the pause is only its tail does not
  overlap   two same-take neighbours that reached into the same pause meet in the middle of it, the report says so;
            pieces the plan itself overlapped (a replay) are left as planned

Made-up clips (voice-like noise at speaking level, room tone between), helpers from test_snap_unheard.

Run: python3 product/tests/test_snap_overlap_and_fold.py
"""
import importlib.util, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_snap_unheard as su  # noqa: E402

spec = importlib.util.spec_from_file_location("snap_to_sound", su.SNAP)
snap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap)

fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {str(detail)[:400]}"))
    if not cond:
        fails.append(label)


W = lambda t, s, e: {"word": t, "start": s, "end": e, "score": 0.9}
tmp = tempfile.mkdtemp(prefix="snap-fold-")
try:
    print("fold")
    p = os.path.join(tmp, "restart.wav")
    su.clip(p, [(0.30, 0.55, -18.0), (0.70, 1.60, -18.0)])            # "con-" ... "confines"
    check("a restart (a short first take, then the whole word) is still two takes",
          snap.VoiceMap(p, [W("confines,", 0.30, 1.60)]).fold(0) is not None)
    p = os.path.join(tmp, "drawn.wav")
    su.clip(p, [(0.30, 1.40, -18.0), (1.51, 1.78, -18.0)])            # "confi......nes", said once
    check("a long word whose part after the pause is only its tail is one take",
          snap.VoiceMap(p, [W("confines,", 0.30, 1.78)]).fold(0) is None)

    print("overlap")
    raw = os.path.join(tmp, "raw"); os.makedirs(raw)
    su.clip(os.path.join(raw, "a.wav"), [(0.30, 1.00, -18.0), (1.20, 1.90, -18.0)])
    words = [W("first", 0.32, 0.98), W("second", 1.22, 1.88)]
    lookup = lambda clip: words
    # Stand-ins for the measured placement: each edge reaches 0.15 s into the pause, so the two pieces overlap there
    snap.place_out = lambda voice, i, cut, one_word: (cut + 0.15, "reached out")
    snap.place_in = lambda voice, i, cut: (cut - 0.15, "reached in")
    snap._unheard = lambda path, words, kept, side, t, limit: (t, None)
    segs = [{"clip": "a.wav", "start": 0.28, "end": 1.02}, {"clip": "a.wav", "start": 1.10, "end": 1.90}]
    placed, lines, _ = snap.snap(segs, raw, lookup)
    check("two same-take neighbours that reached into one pause meet in the middle of it",
          abs(placed[0]["end"] - placed[1]["start"]) < 1e-9 and abs(placed[0]["end"] - 1.06) < 0.0015,
          (placed, lines))
    check("the report says so", any("would play twice" in l for l in lines), lines)
    check("their outer edges are where the snap put them",
          abs(placed[0]["start"] - 0.13) < 0.0015 and abs(placed[1]["end"] - 2.05) < 0.0015, placed)
    replay = [{"clip": "a.wav", "start": 0.28, "end": 1.02}, {"clip": "a.wav", "start": 0.90, "end": 1.90}]
    placed, lines, _ = snap.snap(replay, raw, lookup)
    check("pieces the plan itself overlapped (a replay) are left to the plan",
          placed[0]["end"] > placed[1]["start"] and not any("would play twice" in l for l in lines), placed)
    other = [{"clip": "a.wav", "start": 0.28, "end": 1.02}, {"clip": "b.wav", "start": 1.10, "end": 1.90}]
    shutil.copy(os.path.join(raw, "a.wav"), os.path.join(raw, "b.wav"))
    placed, lines, _ = snap.snap(other, raw, lookup)
    check("pieces from different clips are never touched", not any("would play twice" in l for l in lines), lines)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "snap overlap and fold: one take stays one take, no slice plays twice"))
sys.exit(1 if fails else 0)
