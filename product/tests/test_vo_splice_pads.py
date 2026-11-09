#!/usr/bin/env python3
"""The voiceover splice never plays the same stretch of voice twice.

THE BUG THIS EXISTS FOR. vo-splice.py pads every kept line by 0.05 s on each side so no word's attack or
decay gets clipped. It padded each line on its own, so two kept lines that sat closer together than two
pads (a quick run-on, "...kitchen.It took...") both reached into the gap between them: the end of one
line and the start of the next were each stitched in twice, up to 100 ms of repeated voice at the join.
Now two neighbouring kept lines split the gap between them at its midpoint, and a gap wider than two pads
is left exactly as it was.

How it is checked: the voiceover is a sample ramp (each sample one step louder than the one before), so
every sample says where in the recording it came from. After the splice, every kept stretch must carry on
from a LATER point of the recording than the stretch before it ended on. Any replayed audio shows up as
the ramp stepping backwards. No transcription and no model: a copy of vo-splice.py, a synthetic grid,
ffmpeg, about two seconds.

Run: python3 product/tests/test_vo_splice_pads.py
"""
import json, os, shutil, struct, subprocess, sys, tempfile, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SR = 48000
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def ramp_wav(path, seconds):
    """Mono 16-bit at 48 kHz whose sample n holds the value n - 28800: strictly rising, one step per sample."""
    n = int(seconds * SR)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", i - 28800) for i in range(n)))


def runs(path):
    """The non-silent stretches of channel 0, as (first sample index, sample values). The inserted silences are
    hundreds of zero samples long; the ramp itself only touches zero for a sample or two where it crosses it."""
    with wave.open(path, "rb") as w:
        ch, raw = w.getnchannels(), w.readframes(w.getnframes())
    vals = [struct.unpack_from("<h", raw, i * 2 * ch)[0] for i in range(len(raw) // (2 * ch))]
    out, start, i = [], 0, 0
    while i < len(vals):
        if vals[i] == 0:
            j = i
            while j < len(vals) and vals[j] == 0:
                j += 1
            if j - i >= 20:                     # a real silence: close the stretch before it
                if i > start:
                    out.append((start, vals[start:i]))
                start = j
            i = j
        else:
            i += 1
    if start < len(vals):
        out.append((start, vals[start:]))
    return [r for r in out if len(r[1]) > 50]


def splice(grid, pace="emotional", cut=""):
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "product"))
        os.makedirs(os.path.join(tmp, "projects", "j", "audio"))
        shutil.copy(os.path.join(ROOT, "product", "vo-splice.py"), os.path.join(tmp, "product", "vo-splice.py"))
        ramp_wav(os.path.join(tmp, "projects", "j", "audio", "vo.wav"), 1.2)
        with open(os.path.join(tmp, "projects", "j", "vo-grid.json"), "w", encoding="utf-8") as fh:
            json.dump(grid, fh)
        r = subprocess.run([sys.executable, os.path.join(tmp, "product", "vo-splice.py"), "--job", "j",
                            "--pace", pace, "--cut", cut], capture_output=True, text=True)
        if r.returncode != 0:
            return None, None, r.stderr[-400:]
        with open(os.path.join(tmp, "projects", "j", "vo-grid.clean.json"), encoding="utf-8") as fh:
            clean = json.load(fh)
        return runs(os.path.join(tmp, "projects", "j", "audio", "vo.spliced.raw.wav")), clean, ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def phrase(text, a, b):
    return {"text": text, "a": a, "b": b, "words": [{"w": text, "a": a, "b": b}]}


def main():
    # A and B sit 0.02 s apart (closer than two 0.05 s pads); B and C sit 0.20 s apart (room for both pads).
    grid = {"duration": 1.2, "phrases": [phrase("one", 0.10, 0.50), phrase("two", 0.52, 0.80),
                                          phrase("three", 1.00, 1.15)]}
    for pace in ("emotional", "punchy"):
        rs, clean, err = splice(grid, pace)
        check(f"{pace}: the splice ran", rs is not None, err)
        if rs is None:
            continue
        check(f"{pace}: three kept stretches, one per line", len(rs) == 3, f"got {len(rs)}")
        if len(rs) != 3:
            continue
        pos, rs = [p for p, _ in rs], [r for _, r in rs]
        # the ramp comes back scaled by the mono->stereo upmix, so turn each sample value back into the
        # recording time it came from, and measure how much of the recording any join plays a second time
        scale = (rs[0][-1] - rs[0][0]) / max(1, len(rs[0]) - 1)
        heard = lambda v: (v / scale + 28800) / SR  # sample value back to recording time
        replay = [heard(rs[i - 1][-1]) - heard(rs[i][0]) for i in range(1, len(rs))]
        check(f"{pace}: no stretch of voice is played twice (every join moves forward in the recording)",
              all(r < 0.0005 for r in replay), "replayed at each join: " + ", ".join(f"{r * 1000:.0f} ms" for r in replay))
        check(f"{pace}: the close join is split at its midpoint (0.51 s)",
              abs(heard(rs[0][-1]) - 0.51) < 0.002 and abs(heard(rs[1][0]) - 0.51) < 0.002,
              f"line one ends at {heard(rs[0][-1]):.4f}s, line two starts at {heard(rs[1][0]):.4f}s")
        check(f"{pace}: a join with room for both pads keeps the full 0.05 s each side",
              abs(heard(rs[1][-1]) - 0.85) < 0.002 and abs(heard(rs[2][0]) - 0.95) < 0.002,
              f"line two ends at {heard(rs[1][-1]):.4f}s, line three starts at {heard(rs[2][0]):.4f}s")
        # the re-timed words still point at the audio they belong to: each line's first word sits in the output
        # where its stretch starts, plus however much of the recording before the word that stretch carries
        for k in (1, 2):
            want = pos[k] / SR + (grid["phrases"][k]["a"] - heard(rs[k][0]))
            got = clean["phrases"][k]["a"]
            check(f"{pace}: line {k + 1}'s re-timed start points at its own audio", abs(got - want) < 0.006,
                  f"grid says {got:.3f}s, the audio is at {want:.3f}s")

    # a cut line in between: the neighbours are not adjacent, nothing about their pads changes
    rs, clean, err = splice(grid, "emotional", cut="2")
    check("with the middle line cut, the two kept lines are both there and move forward",
          rs is not None and len(rs) == 2 and rs[1][1][0] > rs[0][1][-1], err)

    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
