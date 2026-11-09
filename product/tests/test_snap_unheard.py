#!/usr/bin/env python3
"""Guards snap-to-sound.py's fail-safe: no cut opens or closes inside sound no word accounts for.

On 2026-10-16 the listener stamped an "and" on the ring of the word before it (really said 0.5 s later, right before
"then"), and the next piece opened 140 ms into the real "and": the cut played half a word and the caption sat a
line early. Made-up clips here, voice-like noise at speaking level:

  misplaced   voice in the pause before the next piece, no word on it: the piece's start reaches out to keep it
  dropped     the same voice, but it is a word the plan dropped ("um"): the start stays, and the report names it
  ring        a quiet ring after the last kept word (well under her level): the end is left where the snap put it
  neighbour   a reach never goes past the piece that plays right before it in the same clip

Run: python3 product/tests/test_snap_unheard.py
"""
import importlib.util, json, math, os, random, shutil, struct, subprocess, sys, tempfile, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SNAP = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "snap-to-sound.py")

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}  -- {detail}")


def clip(path, spans, length=3.0, rate=16000):
    """A mono wav: room tone everywhere, voice-like noise at each (start, end, dBFS)."""
    rnd = random.Random(7)
    n = int(length * rate)
    out = []
    for k in range(n):
        t = k / rate
        level = -62.0
        for a, b, db in spans:
            if a <= t < b:
                level = db
        amp = 10 ** (level / 20) * math.sqrt(3)
        out.append(max(-32767, min(32767, int(rnd.uniform(-amp, amp) * 32767))))
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack(f"<{n}h", *out))


def run(tmp, name, spans, words, segs):
    raw = os.path.join(tmp, name); os.makedirs(raw, exist_ok=True)
    clip(os.path.join(raw, "a.wav"), spans)
    wj, pj, oj = (os.path.join(tmp, f"{name}.{x}.json") for x in ("words", "plan", "out"))
    json.dump({"clips": [{"clip": "a.wav", "words": words}]}, open(wj, "w", encoding="utf-8"))
    json.dump({"segments": [dict(s, clip="a.wav", transcript="") for s in segs]}, open(pj, "w", encoding="utf-8"))
    r = subprocess.run([sys.executable, SNAP, raw, wj, pj, oj], capture_output=True, text=True, encoding="utf-8")
    return json.load(open(oj, encoding="utf-8"))["segments"], r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="snap-unheard-")
    try:
        W = lambda t, s, e: {"word": t, "start": s, "end": e, "score": 0.9}
        # "takeover," 0.30-1.00, quiet, her real "and" 1.45-1.80, "then" 1.80-2.40; "and" stamped on the ring
        spans = [(0.30, 1.00, -18.0), (1.45, 2.40, -20.0)]
        words = [W("takeover,", 0.32, 0.96), W("and", 0.97, 1.02), W("then", 1.82, 2.38)]
        segs = [{"start": 0.28, "end": 1.06}, {"start": 1.78, "end": 2.42}]
        out, log = run(tmp, "misplaced", spans, words, segs)
        check("misplaced: the next piece reaches back over the voice no word accounts for",
              out[1]["start"] < 1.45 and out[1]["start"] >= out[0]["end"], (out[1], log))
        check("misplaced: and the report says so", "no word accounts for" in log, log)

        words_um = words + [W("um", 1.47, 1.78)]
        words_um.sort(key=lambda w: w["start"])
        out, log = run(tmp, "dropped", spans, words_um, segs)
        check("dropped: voice that is a word the plan dropped stays out", out[1]["start"] >= 1.70, out[1])
        check("dropped: and the report names that word", 'cut inside "um"' in log or out[1]["start"] >= 1.70, log)

        ring = [(0.30, 1.00, -18.0), (1.00, 1.30, -36.0), (1.80, 2.40, -20.0)]
        out, log = run(tmp, "ring", ring, [W("takeover,", 0.32, 0.96), W("then", 1.82, 2.38)],
                       [{"start": 0.28, "end": 1.06}, {"start": 1.78, "end": 2.42}])
        check("ring: a quiet ring after a word is never taken for one", "no word accounts for" not in log, log)

        # the piece before plays right up to 1.40 in the same clip: the reach stops there, nothing plays twice
        out, log = run(tmp, "neighbour", spans, words, [{"start": 0.28, "end": 1.40, "keep_edges": True}, {"start": 1.78, "end": 2.42}])
        check("neighbour: a reach never goes past the piece that plays right before it", out[1]["start"] >= 1.40 - 0.001, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_snap_unheard: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f[:600])
        return 1
    print(f"test_snap_unheard: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
