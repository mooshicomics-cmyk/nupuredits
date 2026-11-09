#!/usr/bin/env python3
"""test_nofw_restamp.py — an Intel Mac's transcript gets its pauses back before anything cuts from it.

The Intel-Mac listener (faster-whisper, no alignment pass) stamps a word said after a pause as starting inside the
pause: a median 363 ms early on the creator's own takes, and 87 in 100 word pairs touching with no gap. A cut made
from those stamps opened on dead air, a breath or the tail of a dropped retake, and a buyer heard her line start
chopped. scripts/restamp_words.py measures each pause from the clip's audio and moves the boundary onto it.

Checked here, on made-up loudness so it needs neither the speech tools nor numpy:
  - a pause folded into the next word is measured back out, both edges on the quiet
  - a click in the middle of a pause does not split it
  - a pause in a noisy room (quiet only 12 dB under the voice) is still found, through the background line
  - running speech, and a dip shorter than a held gap, are left exactly as transcribed
  - a word always keeps at least the shortest word's length of itself
  - transcribe-nofw.py writes re-stamped words, and writes them as heard if the audio cannot be read
  - a transcript saved before this fix is repaired once when the rough cut reuses it, and only on the Intel route
  - a word the voice detector carried a whole pause away goes back onto its voice, and one that cannot be placed
    (or is stamped out of order) is named on the screen; a folded pause or a word said before a pause never moves

Run:  python3 product/tests/test_nofw_restamp.py
"""
import importlib.util
import json
import math
import os
import random
import sys
import tempfile
import shutil
import subprocess
import types
import wave
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import restamp_words as rw   # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def loudness(spans, length, quiet=-60.0):
    """A dB-per-frame envelope: `quiet` everywhere, each (start, end, level) span at its level."""
    db = [quiet] * int(round(length / rw.FRAME))
    for a, b, level in spans:
        for k in range(int(round(a / rw.FRAME)), min(len(db), int(round(b / rw.FRAME)))):
            db[k] = level
    return db


def near(x, y, tol=rw.FRAME * 1.5):
    return abs(x - y) <= tol


def unit_part():
    # "so" 0.20-0.50, a pause, "then" 1.10-1.50. Transcribed with the pause folded into "then".
    db = loudness([(0.20, 0.50, -20.0), (1.10, 1.50, -20.0)], 2.5)
    words = [{"word": "so", "start": 0.20, "end": 0.48}, {"word": "then", "start": 0.48, "end": 1.50}]
    out, moved = rw.restamp(words, db)
    check("a folded pause is measured back out", moved == 1, moved)
    check("the earlier word ends where the quiet begins", near(out[0]["end"], 0.50), out[0])
    check("the later word starts where the quiet ends", near(out[1]["start"], 1.10), out[1])
    check("the far edges are left alone", out[0]["start"] == 0.20 and out[1]["end"] == 1.50, out)
    check("the words given are not changed in place", words[1]["start"] == 0.48)

    # The same pause with a click in the middle of it.
    db = loudness([(0.20, 0.50, -20.0), (0.78, 0.80, -25.0), (1.10, 1.50, -20.0)], 2.5)
    out, _ = rw.restamp(words, db)
    check("a click inside a pause does not split it",
          near(out[0]["end"], 0.50) and near(out[1]["start"], 1.10), out)

    # A noisy room: the pause sits only 12 dB under the voice, above the 16 dB line.
    db = loudness([(0.20, 0.50, -28.0), (1.10, 1.50, -28.0)], 6.0, quiet=-40.0)
    out, moved = rw.restamp(words, db)
    check("a pause in a noisy room is found through the background line",
          moved == 1 and near(out[1]["start"], 1.10), out)

    # Running speech: no quiet anywhere between the words.
    db = loudness([(0.20, 1.50, -20.0)], 2.5)
    out, moved = rw.restamp(words, db)
    check("running speech is left exactly as transcribed", moved == 0 and out == words, out)

    # A 24 ms dip (shorter than the 36 ms hold) between two words is not a pause.
    db = loudness([(0.20, 0.50, -20.0), (0.524, 1.50, -20.0)], 2.5)
    out, moved = rw.restamp(words, db)
    check("a dip shorter than a held gap is not a pause", moved == 0 and out == words, out)

    # Quiet that only begins inside the later word's last 102 ms would leave it shorter than any word.
    db = loudness([(0.20, 1.42, -20.0)], 2.5)
    out, moved = rw.restamp(words, db)
    check("a word keeps at least the shortest word's length",
          all(w["end"] - w["start"] >= 0.02 for w in out) and out[1]["start"] <= out[1]["end"] - rw.SHORTEST_WORD + 1e-9,
          out)

    check("one word or none is no work", rw.restamp(words[:1], db)[1] == 0 and rw.restamp([], db) == ([], 0))

    # The envelope itself: a 440 Hz tone at amplitude 0.1 reads about -23 dBFS, silence reads far below.
    tone = [0.1 * math.sin(2 * math.pi * 440 * n / rw.RATE) for n in range(rw.RATE // 4)]
    env = rw.envelope(tone + [0.0] * (rw.RATE // 4))
    check("the envelope reads a tone at its level", -24.5 < env[5] < -21.5, env[5])
    check("and silence far under it", env[-5] < -100, env[-5])


def listener_part():
    """transcribe-nofw.py, with stand-ins for faster-whisper: what it writes, and what it does when the audio
    cannot be read."""
    rng = random.Random(7)

    def samples():
        out = []
        for n in range(int(2.5 * rw.RATE)):
            t = n / rw.RATE
            speaking = 0.20 <= t < 0.50 or 1.10 <= t < 1.50
            out.append((0.2 * math.sin(2 * math.pi * 200 * t) if speaking else 0.0) + rng.uniform(-1e-4, 1e-4))
        return out

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = object
    audio = types.ModuleType("faster_whisper.audio")
    state = {"fail": False}

    def decode_audio(path, sampling_rate=16000):
        if state["fail"]:
            raise RuntimeError("no audio stream")
        return samples()
    audio.decode_audio = decode_audio
    fake.audio = audio
    sys.modules["faster_whisper"], sys.modules["faster_whisper.audio"] = fake, audio
    try:
        spec = importlib.util.spec_from_file_location("transcribe_nofw", os.path.join(SCRIPTS, "transcribe-nofw.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        W = types.SimpleNamespace
        class Model:
            def transcribe(self, path, **kw):
                seg = W(language="en", words=[W(word=" So", start=0.20, end=0.48, probability=0.9),
                                              W(word=" then", start=0.48, end=1.50, probability=0.9)])
                return iter([seg]), W(duration=2.5, language="en")

        entry, _ = mod.hear(Model(), "clip.mov")
        ws = entry["words"]
        check("the listener writes re-stamped words", entry["restamped"] == 1 and near(ws[1]["start"], 1.10), entry)
        check("in the same shape as before", set(ws[0]) == {"word", "start", "end", "score"}, ws[0])

        state["fail"] = True
        entry, _ = mod.hear(Model(), "clip.mov")
        check("audio it cannot read leaves the words as heard",
              entry["restamped"] is None and entry["words"][1]["start"] == 0.48, entry)

        tmp = tempfile.mkdtemp(prefix="nofw-restamp-")
        result = {"clips": [dict(entry, restamped=3), dict(entry, restamped=None)]}
        mod.write_diagnostics(os.path.join(tmp, "words.json"), result, "small", 8, 4, True, True, 1.0, 2.5)
        diag = json.load(open(os.path.join(tmp, ".transcribe-diagnostics.json"), encoding="utf-8"))
        check("the hardware diagnostic counts the measured pauses", diag.get("restamped_pairs") == 3, diag)
    finally:
        sys.modules.pop("faster_whisper", None)
        sys.modules.pop("faster_whisper.audio", None)


def speech_wav(path, spans, length):
    """A 16 kHz mono WAV: a 200 Hz voice inside each (start, end) span, near-silence elsewhere."""
    rng = random.Random(3)
    frames = bytearray()
    for n in range(int(length * rw.RATE)):
        t = n / rw.RATE
        v = (0.3 * math.sin(2 * math.pi * 200 * t) if any(a <= t < b for a, b in spans) else 0.0) + rng.uniform(-3e-4, 3e-4)
        frames += int(max(-1, min(1, v)) * 32767).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rw.RATE); w.writeframes(bytes(frames))


def repair_part():
    """restamp_words.py repair, and word-timings.sh calling it when the rough cut reuses a saved transcript."""
    if not shutil.which("ffmpeg"):
        print("  (repair part skipped: ffmpeg not installed)")
        return
    tmp = tempfile.mkdtemp(prefix="restamp-repair-")
    try:
        # Twelve words, each followed by a 0.5 s pause, stamped the way the Intel listener stamps them: touching,
        # every pause folded into the next word.
        spans, words, t = [], [], 0.3
        for i in range(12):
            spans.append((t, t + 0.4))
            words.append({"word": f"w{i}", "start": round(t - (0.5 if i else 0.0), 3), "end": round(t + 0.38, 3),
                          "score": 0.9})
            t += 0.9
        for a, b in zip(words, words[1:]):
            b["start"] = a["end"]
        os.makedirs(os.path.join(tmp, "raw"))
        speech_wav(os.path.join(tmp, "raw", "take.wav"), spans, t + 0.5)
        wj, out = os.path.join(tmp, "words.json"), os.path.join(tmp, "out.json")
        with open(wj, "w", encoding="utf-8") as f:
            json.dump({"clips": [{"clip": "take.wav", "path": "/nowhere/take.wav", "words": words}]}, f)
        run = lambda *a: subprocess.run([sys.executable, os.path.join(SCRIPTS, "restamp_words.py"), "repair", *a],
                                        capture_output=True, text=True)
        r = run(wj, os.path.join(tmp, "raw"), out)
        check("an older Intel transcript is repaired", r.returncode == 0 and os.path.exists(out), r.stderr)
        if r.returncode == 0:
            clip = json.load(open(out, encoding="utf-8"))["clips"][0]
            ws = clip["words"]
            check("its pauses are back", clip["restamped"] >= 10 and all(b["start"] - a["end"] > 0.3 for a, b in zip(ws, ws[1:])),
                  [(round(a["end"], 2), round(b["start"], 2)) for a, b in zip(ws, ws[1:])][:4])
            check("each word now starts on its sound", all(near(w["start"], s0, 0.02) for w, (s0, _) in zip(ws[1:], spans[1:])),
                  [(w["start"], s0) for w, (s0, _) in zip(ws[1:4], spans[1:4])])
            r2 = run(out, os.path.join(tmp, "raw"), os.path.join(tmp, "again.json"))
            check("a repaired transcript is never repaired twice", r2.returncode == 3, r2.returncode)
        aligned = [dict(w) for w in words]
        for w, (a, b) in zip(aligned, spans):
            w["start"], w["end"] = a + 0.01, b - 0.01
        with open(wj, "w", encoding="utf-8") as f:
            json.dump({"clips": [{"clip": "take.wav", "words": aligned}]}, f)
        check("an aligned transcript is left alone", run(wj, os.path.join(tmp, "raw"), out + "2").returncode == 3)

        # The shell side: word-timings.sh's repair step, run on its own with the real script behind it.
        bash = shutil.which("bash")
        if not bash:
            return
        sh = open(os.path.join(ROOT, ".claude/skills/rough-cut/scripts/word-timings.sh"), encoding="utf-8").read()
        import re
        fns = "".join(re.search(rf"^{n}\(\) \{{.*?^\}}\n", sh, re.S | re.M).group(0)
                      for n in ("repair_older_intel_transcript", "keep_previous_transcript"))
        job = os.path.join(tmp, "job")
        os.makedirs(os.path.join(job, "transcript"))
        canon = os.path.join(job, "transcript", "words.json")

        def step(nofw):
            with open(canon, "w", encoding="utf-8") as f:
                json.dump({"clips": [{"clip": "take.wav", "words": words}]}, f)
            harness = (f'set -e\nENGINE_ROOT="{ROOT}"; NOFW={nofw}; CANON="{canon}"; JOB_DIR="{job}"; '
                       f'MEDIA_DIR="{os.path.join(tmp, "raw")}"; WORK="{tmp}"\n'
                       f'python3 () {{ command "{sys.executable}" "$@"; }}\n' + fns + "repair_older_intel_transcript\n")
            r = subprocess.run([bash, "-c", harness], capture_output=True, text=True)
            return r.returncode, json.load(open(canon, encoding="utf-8"))["clips"][0]
        rc, clip = step(1)
        check("on the Intel route, the rough cut repairs the saved transcript before reusing it",
              rc == 0 and clip.get("restamped", 0) >= 10, (rc, clip.get("restamped")))
        hist = os.path.join(job, "transcript", "history")
        check("and keeps the old one in history first", os.path.isdir(hist) and len(os.listdir(hist)) == 1)
        rc, clip = step(0)
        check("on every other route the saved transcript is handed back untouched", rc == 0 and "restamped" not in clip)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def strays_part():
    """Every route: a short, unsure word squeezed onto the word before it moves onto its real voice after the pause;
    a breath in the pause, a sure word, or a word with no pause after it never moves."""
    W = lambda t, s, e, sc=0.9: {"word": t, "start": s, "end": e, "score": sc}
    # "takeover," rings to 1.00; quiet 1.00-1.45; "and then" voice 1.45-1.95; "then" stamped 1.80
    db = loudness([(0.0, 1.0, -18.0), (1.45, 1.95, -22.0), (1.95, 2.4, -20.0)], 3.0)
    words = [W("takeover,", 0.3, 0.96), W("and", 0.97, 1.03, 0.001), W("then", 1.80, 1.95), W("a", 1.97, 2.0), W("count", 2.05, 2.4)]
    out, moved = rw.strays(words, db)
    check("strays: the squeezed 'and' moves onto its real voice after the pause",
          moved == 1 and near(out[1]["start"], 1.45, 0.03) and out[1]["end"] <= 1.80 and out[1]["was"] == [0.97, 1.03], out[1])
    check("strays: its neighbours stay exactly as heard", out[0] == words[0] and out[2] == words[2])
    sure = [dict(w) for w in words]; sure[1]["score"] = 0.8
    check("strays: a word the listener was sure of never moves", rw.strays(sure, db)[1] == 0)
    breath = loudness([(0.0, 1.0, -18.0), (1.55, 1.62, -50.0), (1.80, 2.4, -20.0)], 3.0)
    check("strays: a breath in the pause is not a word", rw.strays(words, breath)[1] == 0)
    tight = [W("takeover,", 0.3, 0.96), W("and", 0.97, 1.03, 0.001), W("then", 1.10, 1.3)]
    check("strays: a word with no real pause after it stays", rw.strays(tight, db)[1] == 0)
    # the mirror: squeezed onto the word AFTER it, the real word an island between two quiets
    db2 = loudness([(0.0, 1.0, -18.0), (1.30, 1.55, -22.0), (2.0, 2.6, -18.0)], 3.0)
    words2 = [W("chin,", 0.3, 1.0), W("a", 1.95, 1.99, 0.001), W("line", 2.0, 2.6)]
    out2, moved2 = rw.strays(words2, db2)
    check("strays: squeezed onto the next word, it moves back onto its own voice", moved2 == 1 and near(out2[1]["start"], 1.30, 0.03) and near(out2[1]["end"], 1.55, 0.03), out2[1])


def jumps_part():
    """A word the voice detector carried a whole pause away (a buyer's Intel Mac, 2026-10-13: "Two" stamped 30.47 s,
    said 35.70 s, and nothing flagged it) goes back onto its voice; one that cannot be placed is named, never used
    silently. A folded pause, a word said before a long pause and running speech are left exactly as they are."""
    W = lambda t, s, e, sc=0.9: {"word": t, "start": s, "end": e, "score": sc}
    room = -62.0
    # "ago" said 29.60-30.40; 5 s of quiet; "Two" said 35.70-35.95, "years" 36.00-36.40
    db = loudness([(29.0, 30.40, -20.0), (35.70, 35.95, -21.0), (36.00, 36.40, -20.0)], 40.0, quiet=room)
    heard = [W("years", 29.0, 29.55), W("ago", 29.60, 30.40), W("Two", 30.47, 30.70), W("years", 35.62, 36.40)]
    out, moved, suspects = rw.jumps(heard, db)
    check("jumps: a word carried a pause early goes back onto its voice",
          moved == 1 and near(out[2]["start"], 35.70, 0.03) and out[2]["was"] == [30.47, 30.70], out[2])
    check("jumps: and keeps its own length there", near(out[2]["end"] - out[2]["start"], 0.23, 0.01), out[2])
    check("jumps: the next word starts after it", out[3]["start"] >= out[2]["end"] and out[3]["end"] == 36.40, out[3])
    check("jumps: the words before it stay exactly as heard", out[:2] == heard[:2])
    check("jumps: nothing left to flag once it is placed", suspects == [], suspects)
    check("jumps: the words given are not changed in place", heard[2]["start"] == 30.47)
    # the same clip after the pauses went back first (a transcript heard before this existed): "years" swallowed
    # Two's voice, starting at 35.70
    swallowed = [dict(w) for w in heard]; swallowed[3]["start"] = 35.70; swallowed[2]["end"] = 30.70
    out, moved, _ = rw.jumps(swallowed, db)
    check("jumps: also when the next word's stamp swallowed its voice",
          moved == 1 and near(out[2]["start"], 35.70, 0.03) and out[3]["start"] >= out[2]["end"] > 35.85, out[2:])
    # the mirror: carried LATE, onto the head of the line after it, its voice the end of the line before
    db2 = loudness([(10.0, 11.0, -20.0), (11.05, 11.30, -21.0), (14.50, 15.2, -20.0)], 20.0, quiet=room)
    late = [W("so", 10.0, 11.0), W("much", 14.20, 14.45), W("then", 14.50, 15.2)]
    out, moved, _ = rw.jumps(late, db2)
    check("jumps: a word carried a pause late goes back onto the end of its line",
          moved == 1 and near(out[1]["end"], 11.30, 0.03) and out[1]["start"] >= out[0]["end"], out[:2])
    # NOT a jump: a pause folded into a word's start (its stamp still ends on its voice)
    db3 = loudness([(0.2, 0.5, -20.0), (2.6, 3.0, -20.0), (3.05, 3.5, -20.0)], 6.0, quiet=room)
    folded = [W("so", 0.2, 0.48), W("then", 0.48, 3.0), W("we", 3.05, 3.5)]
    out, moved, suspects = rw.jumps(folded, db3)
    check("jumps: a folded pause is not a jump (restamp's job), and is not flagged",
          moved == 0 and out == folded and suspects == [], (moved, suspects))
    # NOT a jump: the last word before a long pause, said where it is stamped
    db4 = loudness([(0.2, 1.0, -20.0), (4.0, 4.6, -20.0)], 6.0, quiet=room)
    said = [W("done", 0.2, 1.0), W("next", 4.0, 4.6)]
    out, moved, suspects = rw.jumps(said, db4)
    check("jumps: a word said before a long pause stays, unflagged", moved == 0 and out == said and suspects == [])
    # running speech is never touched
    db5 = loudness([(0.0, 3.0, -20.0)], 4.0, quiet=room)
    run_on = [W(f"w{k}", k * 0.3, k * 0.3 + 0.28) for k in range(10)]
    check("jumps: running speech is left alone", rw.jumps(run_on, db5)[:2] == (run_on, 0) and rw.jumps(run_on, db5)[2] == [])
    # cannot be placed: over silence beside a long pause, but no voice on either side to put it on
    db6 = loudness([(29.0, 30.40, -20.0), (35.70, 35.80, -21.0)], 40.0, quiet=room)
    lost = [W("years", 29.0, 29.55), W("ago", 29.60, 30.40), W("Two", 30.47, 30.70), W("it", 35.70, 35.80)]
    out, moved, suspects = rw.jumps(lost, db6)
    check("jumps: a word over silence it cannot place is FLAGGED, by name and time",
          moved == 0 and [x["word"] for x in suspects] == ["Two"] and suspects[0]["start"] == 30.47, suspects)
    # out of order: stamped seconds before the word ahead of it ends
    disordered = [W("so", 10.0, 10.4), W("we", 10.45, 10.7), W("then", 5.20, 5.5), W("go", 10.8, 11.0)]
    db7 = loudness([(10.0, 11.0, -20.0)], 12.0, quiet=room)
    _, _, suspects = rw.jumps(disordered, db7)
    check("jumps: a word stamped out of order is FLAGGED", any(x["word"] == "then" and "before" in x["why"] for x in suspects),
          suspects)

    # the Intel listener runs it on every fresh listen, before the pauses go back
    def samples():
        rng = random.Random(11)
        out = []
        for n in range(int(40 * rw.RATE)):
            t = n / rw.RATE
            speaking = 29.0 <= t < 30.40 or 35.70 <= t < 35.95 or 36.00 <= t < 36.40
            out.append((0.2 * math.sin(2 * math.pi * 200 * t) if speaking else 0.0) + rng.uniform(-1e-4, 1e-4))
        return out
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = object
    audio = types.ModuleType("faster_whisper.audio")
    audio.decode_audio = lambda path, sampling_rate=16000: samples()
    fake.audio = audio
    sys.modules["faster_whisper"], sys.modules["faster_whisper.audio"] = fake, audio
    try:
        spec = importlib.util.spec_from_file_location("transcribe_nofw_j", os.path.join(SCRIPTS, "transcribe-nofw.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        S = types.SimpleNamespace

        class Model:
            def transcribe(self, path, **kw):
                seg = S(language="en", words=[S(word=f" {w['word']}", start=w["start"], end=w["end"], probability=0.9)
                                             for w in heard])
                return iter([seg]), S(duration=40.0, language="en")
        entry, _ = mod.hear(Model(), "take.mov")
        two = entry["words"][2]
        check("listener: the Intel route writes the jumped word on its voice, and marks the clip checked",
              near(two["start"], 35.70, 0.03) and entry.get("jumps_checked") == 1 and "suspect_words" not in entry,
              {k: entry.get(k) for k in ("jumps_checked", "suspect_words", "restamped")} | {"two": two})
    finally:
        sys.modules.pop("faster_whisper", None)
        sys.modules.pop("faster_whisper.audio", None)

    # a transcript heard before this existed (already re-stamped, strays already checked) gets the check once,
    # through the pass every route runs when the rough cut reuses it
    if not shutil.which("ffmpeg"):
        print("  (jumps file part skipped: ffmpeg not installed)")
        return
    tmp = tempfile.mkdtemp(prefix="restamp-jumps-")
    try:
        os.makedirs(os.path.join(tmp, "raw"))
        speech_wav(os.path.join(tmp, "raw", "take.wav"), [(29.0, 30.40), (35.70, 35.95), (36.00, 36.40)], 40.0)
        wj, out_p = os.path.join(tmp, "words.json"), os.path.join(tmp, "out.json")
        with open(wj, "w", encoding="utf-8") as f:
            json.dump({"clips": [{"clip": "take.wav", "words": swallowed, "restamped": 133, "strays_checked": 0}]}, f)
        run = lambda src, dst: subprocess.run([sys.executable, os.path.join(SCRIPTS, "restamp_words.py"), "strays",
                                               src, os.path.join(tmp, "raw"), dst], capture_output=True, text=True)
        r = run(wj, out_p)
        clip = json.load(open(out_p, encoding="utf-8"))["clips"][0] if r.returncode == 0 else {}
        ws = clip.get("words") or [{}] * 4
        check("saved transcript: the jumped word is moved, and the screen says so",
              r.returncode == 0 and near(ws[2].get("start", 0), 35.70, 0.03) and clip.get("jumps_checked") == 1
              and "moved 'Two' from 30.47 s" in r.stderr, (r.returncode, r.stderr[-300:], ws[2]))
        r2 = run(out_p, os.path.join(tmp, "again.json"))
        check("saved transcript: checked once, never twice", r2.returncode == 3, (r2.returncode, r2.stderr[-200:]))
        with open(wj, "w", encoding="utf-8") as f:   # an aligned clip (no "restamped"): the sound placed it already
            json.dump({"clips": [{"clip": "take.wav", "words": swallowed, "strays_checked": 0}]}, f)
        check("saved transcript: an aligned clip is never checked for jumps", run(wj, out_p).returncode == 3)
        with open(wj, "w", encoding="utf-8") as f:
            json.dump({"clips": [{"clip": "take.wav", "words": lost, "restamped": 3, "strays_checked": 0}]}, f)
        speech_wav(os.path.join(tmp, "raw", "take.wav"), [(29.0, 30.40), (35.70, 35.80)], 40.0)
        r3 = run(wj, out_p)
        clip = json.load(open(out_p, encoding="utf-8"))["clips"][0] if r3.returncode == 0 else {}
        check("saved transcript: one it cannot place is named on the screen and kept in suspect_words",
              "check 'Two' at 30.47 s by ear" in r3.stderr and [x["word"] for x in clip.get("suspect_words", [])] == ["Two"],
              (r3.returncode, r3.stderr[-300:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    unit_part()
    listener_part()
    repair_part()
    strays_part()
    jumps_part()
    if fails:
        print(f"test_nofw_restamp: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_nofw_restamp: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
