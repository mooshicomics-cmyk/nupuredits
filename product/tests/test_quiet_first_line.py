#!/usr/bin/env python3
"""A short, quiet first line the listener's voice detector skipped is heard again and kept (ISS-99 part 2).

scripts/quiet_first_line.py, with stand-ins for the second listen (no model is loaded or downloaded):
  1. a lead-in with voice in it, and words found there: they go in front, in order, on the clip's own timeline
     (the stretch's start added back), marked heard_again, and the words after them stay exactly as they were
  2. a silent lead-in: never listened to again, the transcript unchanged
  3. the second listen finds nothing: the words unchanged (the clip only marked as checked)
  4. a word the second listen hands back over silence, or on top of her first heard word, is never kept
  5. a click is not voice; a first word under a second in is never looked at; a checked clip is never heard twice
  6. the file pass: exit 3 with nothing to do, exit 0 and the new transcript written when a line was kept
  7. word-timings.sh, handing back a heard job, runs the pass once in the speech tools' Python (a stand-in venv
     with a stand-in faster_whisper), keeps the old transcript in history/, and says so in one plain line
  8. the listener also stamped the skipped line's words on the next take: that take is heard again and its own
     words replace the repeat; a real retake (heard saying the line again) keeps its words; a transcript an earlier
     engine fixed gets only this check, once

Run:  python3 product/tests/test_quiet_first_line.py
"""
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


try:
    import quiet_first_line as q
except ImportError as e:
    check("scripts/quiet_first_line.py is there to bring a skipped first line back", False, str(e))
    print("\nFAILED: " + "; ".join(fails))
    sys.exit(1)

RATE = q.rw.RATE


def audio(seconds, *voiced):
    """Mono samples: a faint room hum, with (start, end, amplitude) stretches of a 220 Hz voice-like tone."""
    out = []
    for i in range(int(seconds * RATE)):
        t = i / RATE
        v = 0.0003 * math.sin(2 * math.pi * 50 * t)
        for t0, t1, amp in voiced:
            if t0 <= t < t1:
                v += amp * math.sin(2 * math.pi * 220 * t)
        out.append(v)
    return out


HEARD = [{"word": "so", "start": 3.0, "end": 3.3, "score": 0.9}, {"word": "today", "start": 3.4, "end": 3.9, "score": 0.9},
         {"word": "we", "start": 4.0, "end": 4.2, "score": 0.9}]
QUIET_LINE = audio(5.5, (0.5, 1.3, 0.02), (3.0, 5.0, 0.3))     # a line about 24 dB under her voice, then 1.7 s quiet
SILENT_LEAD = audio(5.5, (3.0, 5.0, 0.3))
CLICK = audio(5.5, (0.8, 0.84, 0.3), (3.0, 5.0, 0.3))


class Ear:
    """The second listen's stand-in: hands back fixed words (seconds into what it is given) and keeps a record."""
    def __init__(self, words):
        self.words, self.calls = words, []

    def __call__(self, samples, language):
        self.calls.append((len(samples), language))
        return [dict(w) for w in self.words]


def clip(words=HEARD):
    return {"clip": "IMG_0001.MOV", "words": [dict(w) for w in words]}


print("1. a quiet first line, and the second listen hears it")
ear = Ear([{"word": "okay", "start": 0.32, "end": 0.62, "score": 0.8}, {"word": "real", "start": 0.66, "end": 0.9, "score": 0.7},
           {"word": "talk", "start": 0.94, "end": 1.28, "score": 0.75}])
c = clip()
ran, kept = q.recover_clip(c, QUIET_LINE, ear, "en")
voice = q.voice_in(q.rw.envelope(QUIET_LINE), 3.0)
w0, w1 = q.window_for(voice, 3.0)
check("the lead-in's voice is found where it is (about 0.5-1.3 s)", len(voice) == 1 and abs(voice[0][0] - 0.5) < 0.03
      and abs(voice[0][1] - 1.3) < 0.03, voice)
check("only that stretch, padded, is listened to again, once, in the clip's language",
      len(ear.calls) == 1 and abs(ear.calls[0][0] - (w1 - w0) * RATE) <= 1 and ear.calls[0][1] == "en", ear.calls)
check("three words kept", ran and kept == 3 and c["lead_in_checked"] == 3, (ran, kept, c.get("lead_in_checked")))
check("in front, in order", [w["word"] for w in c["words"]] == ["okay", "real", "talk", "so", "today", "we"],
      [w["word"] for w in c["words"]])
check("each on the clip's timeline: its time in the stretch plus where the stretch starts",
      [w["start"] for w in c["words"][:3]] == [round(w0 + s, 3) for s in (0.32, 0.66, 0.94)]
      and [w["end"] for w in c["words"][:3]] == [round(w0 + e, 3) for e in (0.62, 0.9, 1.28)],
      (w0, c["words"][:3]))
check("marked as heard again, with their own confidence", all(w.get("heard_again") for w in c["words"][:3])
      and c["words"][0]["score"] == 0.8, c["words"][:3])
check("the words she was already heard saying are untouched", c["words"][3:] == HEARD, c["words"][3:])
starts = [w["start"] for w in c["words"]]
check("the whole clip still runs forward in time", starts == sorted(starts)
      and all(a["end"] <= b["start"] for a, b in zip(c["words"], c["words"][1:])), starts)

print("2. a silent lead-in")
ear = Ear([{"word": "thank", "start": 0.1, "end": 0.4, "score": 0.9}])
c = clip()
ran, kept = q.recover_clip(c, SILENT_LEAD, ear)
check("never listened to again", not ear.calls and not ran, ear.calls)
check("the transcript unchanged", c == clip(), c)

print("3. the second listen finds nothing")
ear = Ear([])
c = clip()
ran, kept = q.recover_clip(c, QUIET_LINE, ear)
check("it listened once", len(ear.calls) == 1, ear.calls)
check("the words unchanged", c["words"] == HEARD, c["words"])
check("the clip is marked checked, with nothing kept", c.get("lead_in_checked") == 0, c)

print("4. words the second listen imagines are never kept")
ear = Ear([{"word": "you", "start": 1.55, "end": 1.85, "score": 0.95},       # over the silence after the line
           {"word": "so", "start": 2.8, "end": 2.95, "score": 0.9},          # her first heard word again (past the stretch)
           {"word": "mm", "start": 0.4, "end": 0.6, "score": 0.1}])          # over the voice, but barely sure of it
c = clip()
ran, kept = q.recover_clip(c, QUIET_LINE, ear)
check("none of them kept, the words unchanged", kept == 0 and c["words"] == HEARD, c["words"][:3])
words, n = q.merge(HEARD, [{"word": "so", "start": 2.9, "end": 3.2, "score": 0.9}], 0.0, 3.0, [(2.8, 3.2)])
check("a word centred on her first heard word is that word again, not a new one", n == 0 and words == HEARD, words)

print("5. what is never looked at")
ear = Ear([{"word": "okay", "start": 0.32, "end": 0.62, "score": 0.8}])
c = clip()
q.recover_clip(c, CLICK, ear)
check("a click in the lead-in is not voice", not ear.calls and c == clip(), ear.calls)
early = [dict(w, start=w["start"] - 2.5, end=w["end"] - 2.5) for w in HEARD]
c = clip(early)
q.recover_clip(c, QUIET_LINE, ear)
check("a first word under a second in: nothing to look for", not ear.calls and c == clip(early), ear.calls)
c = clip()
q.recover_clip(c, QUIET_LINE, ear)
q.recover_clip(c, QUIET_LINE, ear)
check("a clip is heard again once, never twice", len(ear.calls) == 1 and len(c["words"]) == len(HEARD) + 1, ear.calls)

print("6. the file pass")
tmp = os.path.realpath(tempfile.mkdtemp())
try:
    media = os.path.join(tmp, "raw")
    os.makedirs(media)
    open(os.path.join(media, "IMG_0001.MOV"), "wb").close()     # only its presence matters: decode is a stand-in
    src, out = os.path.join(tmp, "words.json"), os.path.join(tmp, "out.json")
    with open(os.path.join(tmp, ".transcribe-diagnostics.json"), "w", encoding="utf-8") as fh:
        json.dump({"model": "large-v3", "detected_languages": {"es": 1}}, fh)
    decoded = []

    def decode(path, seconds):
        decoded.append(seconds)
        return SILENT_LEAD[:int(seconds * RATE)]

    with open(src, "w", encoding="utf-8") as fh:
        json.dump({"clips": [clip()]}, fh)
    rc = q.recover(src, media, out, hear=Ear([]), decode=decode)
    check("nothing to do: exit 3, nothing written", rc == 3 and not os.path.exists(out), rc)
    check("only the lead-in (and her first heard line) is read", decoded and abs(decoded[0] - 5.0) < 1e-6, decoded)

    def decode(path, seconds):
        return QUIET_LINE[:int(seconds * RATE)]

    ear = Ear([{"word": "hola", "start": 0.32, "end": 0.7, "score": 0.8}])
    rc = q.recover(src, media, out, hear=ear, decode=decode)
    with open(out, encoding="utf-8") as fh:
        got = json.load(fh)["clips"][0]
    check("a line kept: exit 0, the new transcript written", rc == 0 and got["words"][0]["word"] == "hola"
          and got["words"][1:] == HEARD and got["lead_in_checked"] == 1, (rc, got["words"][:2]))
    check("heard in the job's own language when the clip names none", ear.calls and ear.calls[0][1] == "es", ear.calls)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("8. the listener also wrote the skipped line over the next take (ISS-99)")
# Her real first line "okay real talk" at 0.5-1.3 s went unheard, and the listener stamped those same words on the
# next take, which really says "here are captions" (3.0-3.9 s). Kept as it was, the transcript held the line twice
# and the cut kept the LAST one: the take that says something else.


class Ears:
    """The second listen's stand-in, one answer per listen, in order (the lead-in first)."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, samples, language):
        self.calls.append((len(samples), language))
        return [dict(w) for w in (self.answers.pop(0) if self.answers else [])]


LINE = [{"word": "okay", "start": 0.32, "end": 0.62, "score": 0.8}, {"word": "real", "start": 0.66, "end": 0.9, "score": 0.7},
        {"word": "talk,", "start": 0.94, "end": 1.28, "score": 0.75}]
STAMPED = [{"word": "Okay", "start": 3.0, "end": 3.3, "score": 0.9}, {"word": "real", "start": 3.35, "end": 3.6, "score": 0.9},
           {"word": "talk.", "start": 3.62, "end": 3.9, "score": 0.9}, {"word": "we", "start": 4.0, "end": 4.2, "score": 0.9}]
TAKE = [{"word": "here", "start": 0.31, "end": 0.55, "score": 0.9}, {"word": "are", "start": 0.58, "end": 0.7, "score": 0.9},
        {"word": "captions", "start": 0.72, "end": 1.15, "score": 0.9}]
ear = Ears(LINE, TAKE)
c = clip(STAMPED)
ran, kept = q.recover_clip(c, QUIET_LINE, ear, "es")
said = [w["word"] for w in c["words"]]
check("the line is kept in front, and the next take heard again in its own language",
      kept == 3 and len(ear.calls) == 2 and ear.calls[1][1] == "es", (kept, ear.calls))
check("the take now says what it says, never the line a second time",
      said == ["okay", "real", "talk,", "here", "are", "captions", "we"], said)
take = c["words"][3:6]
check("its words sit on the take's own time, on the clip's timeline, marked as heard again",
      all(w.get("heard_again") for w in take) and 2.95 <= take[0]["start"] < take[-1]["end"] <= 4.0 - 0.01,
      take)
check("the words after it stay exactly as they were", c["words"][6:] == STAMPED[3:], c["words"][6:])
starts = [w["start"] for w in c["words"]]
check("the clip still runs forward in time", starts == sorted(starts)
      and all(a["end"] <= b["start"] for a, b in zip(c["words"], c["words"][1:])), starts)

ear = Ears(LINE, [dict(w, word=t) for w, t in zip(TAKE, ("okay", "real", "talk"))])
c = clip(STAMPED)
q.recover_clip(c, QUIET_LINE, ear, "en")
check("a take that really says the line again (a retake) keeps its words",
      [w["word"] for w in c["words"]] == ["okay", "real", "talk,", "Okay", "real", "talk.", "we"],
      [w["word"] for w in c["words"]])

ear = Ears(LINE, [])
c = clip(STAMPED)
q.recover_clip(c, QUIET_LINE, ear, "en")
check("nothing heard on the second listen: the take keeps its words", [w["word"] for w in c["words"]][3:] ==
      [w["word"] for w in STAMPED], [w["word"] for w in c["words"]])

ear = Ears(LINE, TAKE)
c = clip([dict(w) for w in STAMPED[3:]])                         # no repeat: "we" right after the line
c["words"] = [dict(w, start=w["start"] - 1.0, end=w["end"] - 1.0) for w in STAMPED]
c["words"][0]["word"] = "so"
q.recover_clip(c, QUIET_LINE, ear, "en")
check("a take that starts differently is never listened to a second time", len(ear.calls) == 1, ear.calls)

# A transcript an earlier engine already put the line back into: the repeat is found and fixed once, the lead-in
# itself never heard again.
older = clip([dict(w, start=round(w["start"] + 0.2, 3), end=round(w["end"] + 0.2, 3), heard_again=True) for w in LINE]
             + STAMPED)
older["lead_in_checked"] = 3
ear = Ears(TAKE)
q.recover_clip(older, QUIET_LINE, ear, "en")
check("a transcript fixed by an earlier engine: only the repeated take is heard again, and it is fixed",
      len(ear.calls) == 1 and [w["word"] for w in older["words"]][3:6] == ["here", "are", "captions"],
      ([w["word"] for w in older["words"]], ear.calls))
q.recover_clip(older, QUIET_LINE, ear, "en")
check("and never twice", len(ear.calls) == 1, ear.calls)

tmp = os.path.realpath(tempfile.mkdtemp())
try:
    media = os.path.join(tmp, "raw")
    os.makedirs(media)
    open(os.path.join(media, "IMG_0001.MOV"), "wb").close()
    src, out = os.path.join(tmp, "words.json"), os.path.join(tmp, "out.json")
    long_take = STAMPED[:3] + [{"word": f"w{i}", "start": 4.0 + 0.3 * i, "end": 4.2 + 0.3 * i, "score": 0.9}
                               for i in range(12)]
    with open(src, "w", encoding="utf-8") as fh:
        json.dump({"clips": [clip(long_take)]}, fh)
    asked = []

    def decode(path, seconds):
        asked.append(seconds)
        return QUIET_LINE[:int(seconds * RATE)]

    rc = q.recover(src, media, out, hear=Ears(LINE, TAKE), decode=decode)
    got = json.load(open(out, encoding="utf-8"))["clips"][0] if os.path.exists(out) else {}
    check("the file pass reads far enough to hear the take again, and fixes it",
          rc == 0 and asked and asked[0] >= 3.9 and [w["word"] for w in got.get("words", [])][3:6] == ["here", "are", "captions"],
          (rc, asked, [w["word"] for w in got.get("words", [])][:7]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("7. word-timings.sh, handing back a heard job")
FFMPEG = shutil.which("ffmpeg")
try:
    import numpy  # noqa: F401  (the stand-in venv is this Python; the real ones always carry numpy)
    have_numpy = True
except ImportError:
    have_numpy = False
if os.name == "nt" or not FFMPEG or not shutil.which("bash") or not have_numpy:
    print("  skipped (needs bash, ffmpeg and numpy; not run on Windows)")
else:
    tmp = os.path.realpath(tempfile.mkdtemp())
    try:
        eng = os.path.join(tmp, "engine")
        for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh", "scripts/restamp_words.py",
                    "scripts/quiet_first_line.py", "scripts/transcribe-nofw.py"):
            if os.path.exists(os.path.join(ROOT, rel)):
                os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
        scripts = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts")
        shutil.copytree(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"), scripts,
                        ignore=shutil.ignore_patterns("__pycache__"))
        # The speech tools' stand-in: a venv whose python is this one, with a faster_whisper that hears fixed words.
        venv, mods, log = os.path.join(tmp, "venv"), os.path.join(tmp, "mods"), os.path.join(tmp, "heard.log")
        os.makedirs(os.path.join(venv, "bin"))
        os.makedirs(os.path.join(mods, "faster_whisper"))
        open(os.path.join(venv, ".speech-tools-ready"), "w", encoding="utf-8").write("cpu\n")
        py = os.path.join(venv, "bin", "python")
        with open(py, "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/bash\nPYTHONPATH={mods!r} exec {sys.executable!r} \"$@\"\n")
        os.chmod(py, os.stat(py).st_mode | stat.S_IXUSR)
        with open(os.path.join(mods, "faster_whisper", "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write(
                "from types import SimpleNamespace as N\n"
                "class WhisperModel:\n"
                "    def __init__(self, name, **kw):\n"
                "        self.name = name\n"
                "    def transcribe(self, audio, **kw):\n"
                f"        open({log!r}, 'a', encoding='utf-8').write(f\"{{self.name}} vad_filter={{kw.get('vad_filter')}} {{len(audio)}}\\n\")\n"
                "        ws = [N(word=' okay', start=0.32, end=0.62, probability=0.8), N(word=' real', start=0.66, end=0.9, probability=0.8),\n"
                "              N(word=' talk', start=0.94, end=1.28, probability=0.8)]\n"
                "        return iter([N(words=ws)]), N(language='en')\n")
        jd = os.path.join(eng, "projects", "quiet-start")
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        expr = ("if(between(t,0.5,1.3),0.02*sin(2*PI*220*t),if(between(t,3,5),0.3*sin(2*PI*220*t),"
                "0.0003*sin(2*PI*50*t)))")
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d=5.5",
                        "-c:a", "aac", "-y", os.path.join(jd, "raw", "IMG_0001.MOV")], check=True)
        canon = os.path.join(jd, "transcript", "words.json")
        with open(canon, "w", encoding="utf-8") as fh:
            json.dump({"clips": [dict(clip(), duration=5.5)]}, fh)
        with open(os.path.join(jd, "transcript", ".transcribe-diagnostics.json"), "w", encoding="utf-8") as fh:
            json.dump({"model": "large-v3", "device": "cpu", "detected_languages": {"en": 1}}, fh)
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), REELS_ENGINE_WHISPERX_VENV=venv,
                   REELS_ENGINE_NOFW_VENV=venv)
        for k in ("REELS_ENGINE_FORCE_NOFW", "REELS_ENGINE_LANGUAGE", "REELS_ENGINE_WHISPER_MODEL"):
            env.pop(k, None)

        def hand_back():
            return subprocess.run(["bash", os.path.join(scripts, "word-timings.sh"), os.path.relpath(jd, eng)], cwd=eng,
                                  env=env, capture_output=True, text=True, encoding="utf-8")

        r = hand_back()
        with open(canon, encoding="utf-8") as fh:
            words = json.load(fh)["clips"][0]["words"]
        heard = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        check("it hands the transcript back", r.returncode == 0 and r.stdout.strip() == canon, r.stderr[-500:])
        check("the lead-in was listened to again with the voice detector off, on the listener's own model",
              len(heard) == 1 and heard[0].startswith("large-v3 vad_filter=False "), heard)
        check("the quiet first line is in the job's transcript, in front",
              [w["word"] for w in words] == ["okay", "real", "talk", "so", "today", "we"], [w["word"] for w in words])
        check("one plain line says so", "found a quiet first line the listener skipped in IMG_0001.MOV; kept it" in r.stderr,
              r.stderr[-500:])
        hist = os.path.join(jd, "transcript", "history")
        before = []
        for name in sorted(os.listdir(hist)) if os.path.isdir(hist) else []:
            with open(os.path.join(hist, name), encoding="utf-8") as fh:
                before.append([w["word"] for w in json.load(fh)["clips"][0]["words"]])
        check("the transcript it replaced is kept in history/", ["so", "today", "we"] in before, before)
        r = hand_back()
        heard = open(log, encoding="utf-8").read().splitlines()
        check("handed back again: never listened to twice", r.returncode == 0 and len(heard) == 1, heard)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "quiet first line: a skipped opening line comes back, nothing invented"))
sys.exit(1 if fails else 0)
