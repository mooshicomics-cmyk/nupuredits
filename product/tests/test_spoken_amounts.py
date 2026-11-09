#!/usr/bin/env python3
"""Guards: a spoken amount is never clipped. The aligner cannot time digits, so "$27,000" is ONE stamp over
"twenty-seven ... thousand ... dollars", with quiet inside it and an end stamp that can sit a whole word early.

  planner   a pause beside an amount never splits a line (up to 1.5 s), a period after one doesn't either when
            the next line follows inside that pause, and the long-word guard never shortens an amount
  snap      an amount's out-point is the last sound before the next word (no stamp cap, no move cap), its
            in-point the first sound after the word before, and its quiet inside is never read as a second take
  plain     an ordinary word keeps the old rules: a 0.78 s pause still splits a line

Run: python3 product/tests/test_spoken_amounts.py
"""
import importlib.util, json, math, os, shutil, struct, sys, tempfile, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ENGINE, ".claude", "skills", "rough-cut", "scripts")

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def voice_wav(path, spans, length):
    """A mono 16 kHz file: a voiced tone during each (start, end), near-silence elsewhere."""
    rate = 16000
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = bytearray()
        for k in range(int(length * rate)):
            t = k / rate
            on = any(a <= t < b for a, b in spans)
            v = 0.3 * math.sin(2 * math.pi * 190 * t) if on else 0.0003 * math.sin(2 * math.pi * 50 * t)
            frames += struct.pack("<h", int(v * 32767))
        w.writeframes(bytes(frames))


def main():
    tc = load("transcript_cut", "transcript-cut.py")
    sn = load("snap_to_sound", "snap-to-sound.py")
    # planner
    W = [("We", 20.89, 20.99), ("brought", 21.17, 21.65), ("in", 21.75, 22.07), ("$27,000", 22.09, 24.67),
         ("a", 25.45, 25.61), ("month", 25.75, 26.05)]
    tmp0 = tempfile.mkdtemp(prefix="amounts0-")

    def cut(words, name):
        job = os.path.join(tmp0, name); os.makedirs(os.path.join(job, "transcript"), exist_ok=True)
        json.dump({"clips": [{"file": "c.mp4", "words": [{"word": w, "start": a, "end": b} for w, a, b in words]}]},
                  open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8"))
        out = tc.build(job, "c.mp4", False)
        shutil.rmtree(os.path.join(tempfile.gettempdir(), "reels-editing-engine", name), ignore_errors=True)
        return out
    segs = cut(W, "amt-a")
    check("planner: the pause after an amount (where 'dollars' is) is never cut out of the line",
          len(segs) == 1 and segs[0]["start"] <= 20.9 and segs[0]["end"] >= 26.0, segs)
    retake = [("I", 1.0, 1.1), ("made", 1.2, 1.5), ("$27,000", 1.6, 3.0), ("I", 3.8, 3.9), ("made", 4.0, 4.3),
              ("$27,000", 4.4, 5.8), ("last", 5.9, 6.2), ("month.", 6.3, 6.7)]
    segs = cut(retake, "amt-b")
    check("planner: a retake of a line with an amount is still found (only the last take stays)",
          len(segs) == 1 and segs[0]["start"] >= 3.7 and "last month" in segs[0]["transcript"], segs)
    countdown = [("3,", 0.5, 0.8), ("2,", 1.4, 1.7), ("1,", 2.3, 2.6), ("Here's", 3.8, 4.1), ("the", 4.2, 4.3), ("thing.", 4.4, 4.9)]
    segs = cut(countdown, "amt-c")
    check("planner: a counted-in warm-up (3, 2, 1) is not an amount, so it's cut as before", all("3," not in x["transcript"] for x in segs), segs)
    year = [("In", 1.0, 1.2), ("2024.", 1.3, 1.9), ("Everything", 3.3, 3.8), ("changed.", 3.9, 4.4)]
    segs = cut(year, "amt-d")
    check("planner: a year is said inside its stamp: the pause after it is cut as any pause", len(segs) == 2, segs)
    shutil.rmtree(tmp0, ignore_errors=True)
    P = [("I", 0.0, 0.2), ("stumbled", 0.3, 0.7), ("into", 0.8, 1.0), ("money", 1.1, 1.5), ("a", 2.28, 2.4), ("month", 2.5, 2.8)]
    check("plain: an ordinary word's 0.78 s pause still splits", len(tc.sentences(P)) == 2, tc.sentences(P))
    tmp = tempfile.mkdtemp(prefix="amounts-")
    try:
        job = os.path.join(tmp, "amount-test-reel")
        os.makedirs(os.path.join(job, "transcript"))
        words = [{"word": w, "start": s, "end": e} for w, s, e in
                 [("I", 0.5, 0.6), ("made", 0.7, 0.9), ("$27,000.", 1.0, 3.6), ("A", 4.4, 4.5), ("month", 4.6, 4.9),
                  ("later", 5.0, 5.3)]]
        json.dump({"clips": [{"file": "clip.mp4", "words": words}]}, open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8"))
        segs = tc.build(job, "clip.mp4", False)
        check("planner: a period after an amount doesn't cut the pause where its words are", len(segs) == 1
              and segs[0]["start"] <= 0.5 and segs[0]["end"] >= 5.3, segs)
        words = [{"word": w, "start": a, "end": b} for w, a, b in [("I", 0.5, 0.6), ("made", 0.7, 0.9), ("$27,000", 1.0, 3.6)]]
        json.dump({"clips": [{"file": "clip.mp4", "words": words}]}, open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8"))
        segs = tc.build(job, "clip.mp4", False)
        check("planner: a line ending on an amount keeps its whole long stamp and a short tail after it",
              segs and 3.6 + 0.5 <= segs[-1]["end"] <= 3.6 + 0.7, segs)
        # snap, on audio shaped like the real clip: "twenty-seven" | quiet | "thousand" | quiet | "dollars" | ... "a"
        wav = os.path.join(tmp, "clip.wav")
        voice_wav(wav, [(0.10, 0.40), (0.50, 1.50), (2.00, 2.50), (2.90, 3.40), (4.50, 4.70)], 5.2)
        ws = [{"word": "made", "start": 0.10, "end": 0.40}, {"word": "$27,000", "start": 0.55, "end": 2.45},
              {"word": "a", "start": 4.50, "end": 4.70}]
        vm = sn.VoiceMap(wav, ws)
        check("snap: an amount's quiet inside is never a second take", vm.fold(1) is None, vm.fold(1))
        out, note = sn.place_out(vm, 1, 2.45, one_word=False)
        check("snap: an amount ends after its last spoken word, before the next word", 3.40 <= out < 4.50, (out, note))
        cut_in, note = sn.place_in(vm, 1, 0.55)
        check("snap: an amount starts on its first sound, after the word before", 0.40 <= cut_in <= 0.50, (cut_in, note))
        # the same shape under an ordinary long word is still read as two takes (the old rule stands)
        plain = [dict(ws[0]), {"word": "listen", "start": 0.55, "end": 2.45}, dict(ws[2])]
        check("plain: an ordinary long word with quiet inside is still two takes", sn.VoiceMap(wav, plain).fold(1) is not None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(os.path.join(tempfile.gettempdir(), "reels-editing-engine", "amount-test-reel"), ignore_errors=True)
    if fails:
        print(f"test_spoken_amounts: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_spoken_amounts: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
