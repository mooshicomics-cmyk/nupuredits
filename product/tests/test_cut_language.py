#!/usr/bin/env python3
"""A reel in another alphabet must survive the rough cut, and the checks must know it is not English.

THE BUG THIS EXISTS FOR. The cutter's tokenizer kept only [a-z0-9], so every line of a Russian, Greek,
Arabic, Hebrew, Hindi, Chinese or Japanese transcript came out with no tokens at all, and the cutter
dropped every line: a rough cut of zero seconds. The language check had the same blind spot. It looks
for accented Latin letters and Spanish or French function words, finds neither in Cyrillic or CJK, and
answered "english", so the listen-back forced English (Whisper then TRANSLATES the audio and reports the
creator's own words as mismatches), the word scan flagged every word, and the on-screen copy check
refused correctly translated cards.

What is pinned here:
  1. On ASCII text the new tokenizers keep exactly what the old [a-z0-9] ones kept (English cuts and
     English listen-backs cannot move).
  2. A transcript in each of seven other alphabets keeps its lines, and still drops the earlier take of
     a line said twice.
  3. The language check calls those transcripts not-English, still calls English English (a quoted name
     in another alphabet included) and still calls Spanish not-English.
  4. The listen-back's tokenizer keeps Cyrillic words, and the on-screen copy check passes a Russian card
     on a Russian reel while still refusing an English one.

Run:  python3 product/tests/test_cut_language.py
"""
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
CHECK = os.path.join(ROOT, ".claude", "skills", "graphics-plan", "scripts", "check-plan-language.py")
sys.path.insert(0, SCRIPTS)
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import transcript_language as tl  # noqa: E402
tcut = load("transcript_cut", "transcript-cut.py")
vcut = load("verify_cut", "verify-cut.py")

# ---------------------------------------------------------------- 1. ASCII behaves exactly as before
rng = random.Random(7)
alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,;:!?'\"-_()[]/&%$#@*\t"
for _ in range(3000):
    words = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 9))) for _ in range(rng.randint(1, 8))]
    sent = [(w, 0.0, 0.1) for w in words]
    old_toks = re.sub(r"[^a-z0-9 ]", "", " ".join(words).lower()).split()
    if tcut.toks(sent) != old_toks:
        check("transcript-cut tokens are unchanged on ASCII text", False, repr(words))
        break
    text = " ".join(words)
    low = text.lower()
    for k, v in vcut._CONTRACT.items():
        low = re.sub(r"\b" + k + r"\b", v, low)
    old_norm = [t for t in re.sub(r"[^a-z0-9' ]", " ", low).split() if t]
    if vcut.norm_tokens(text) != old_norm:
        check("verify-cut tokens are unchanged on ASCII text", False, repr(text))
        break

# ---------------------------------------------------------------- 2. other alphabets keep their lines
LINES = {
    "ru": ["Сегодня я расскажу вам о своей работе.", "Я ушла с работы в прошлом году.",
           "Я ушла с работы в прошлом году.", "Это было самое трудное решение в моей жизни."],
    "el": ["Σήμερα θα σας πω για τη δουλειά μου.", "Άφησα τη δουλειά μου πέρσι.",
           "Άφησα τη δουλειά μου πέρσι.", "Ήταν η πιο δύσκολη απόφαση της ζωής μου."],
    "ar": ["اليوم سأحكي لكم عن عملي.", "تركت عملي في العام الماضي.", "تركت عملي في العام الماضي.",
           "كان أصعب قرار في حياتي."],
    "he": ["היום אספר לכם על העבודה שלי.", "עזבתי את העבודה בשנה שעברה.", "עזבתי את העבודה בשנה שעברה.",
           "זו הייתה ההחלטה הקשה בחיי."],
    "hi": ["आज मैं आपको अपने काम के बारे में बताऊंगी।", "मैंने पिछले साल नौकरी छोड़ दी।",
           "मैंने पिछले साल नौकरी छोड़ दी।", "यह मेरी ज़िंदगी का सबसे कठिन फ़ैसला था।"],
    "zh": ["今天我想跟你们聊聊我的工作。", "我去年辞职了。", "我去年辞职了。", "这是我人生中最难的决定。"],
    "ja": ["今日は私の仕事について話します。", "去年、仕事を辞めました。", "去年、仕事を辞めました。",
           "人生で一番難しい決断でした。"],
}


def words_for(code):
    """WhisperX-shaped words: space-separated tokens, or one character per word for Chinese/Japanese."""
    out, t, starts = [], 0.5, []
    for line in LINES[code]:
        starts.append(t)
        toks = [c for c in line if not c.isspace()] if code in ("zh", "ja") else line.split()
        for tok in toks:
            out.append({"w": tok, "start": round(t, 3), "end": round(t + 0.25, 3), "prob": 0.9})
            t += 0.3
        t += 1.0
    return out, starts


with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, TMPDIR=tmp, TEMP=tmp, TMP=tmp)
    for code in LINES:
        job = os.path.join(tmp, f"reel-{code}")
        os.makedirs(os.path.join(job, "transcript"))
        words, starts = words_for(code)
        with open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8") as fh:
            json.dump({"clips": [{"clip": "take.mov", "words": words}]}, fh, ensure_ascii=False)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "transcript-cut.py"), job],
                           capture_output=True, text=True, env=env, encoding="utf-8")
        try:
            with open(os.path.join(job, "transcript", "cuts.json"), encoding="utf-8") as fh:
                segs = json.load(fh)["segments"]
        except (OSError, ValueError, KeyError):
            segs = []
        kept = {round(s["start"], 1) for s in segs}
        check(f"{code}: transcript-cut keeps the lines", r.returncode == 0 and len(segs) >= 3,
              f"rc {r.returncode}, {len(segs)} segments: {r.stderr[-200:]}")
        check(f"{code}: the earlier take of the repeated line goes, the last one stays",
              round(starts[1], 1) not in kept and round(starts[2], 1) in kept, f"kept starts {sorted(kept)}")
        verdict = tl.classify([w["w"] for w in words])
        check(f"{code}: not English, no guessed code",
              verdict["verdict"] in ("non_english", "mixed") and not verdict["english_only_checks_ok"]
              and verdict["language_code"] is None, str(verdict))

# ---------------------------------------------------------------- 3. English and Spanish read as before
ENGLISH = ("so this is the part nobody tells you about building something while the kids are home and "
           "the laundry is still sitting there waiting for me to fold it before dinner").split()
SPANISH = ("Dejé mi trabajo porque ya no podía más con todo esto y la verdad es que fue muy difícil pero "
           "también fue lo mejor que hice para mi familia y para mí misma aquí estamos").split()
v = tl.classify(ENGLISH)
check("English reads as English", v["verdict"] == "english" and v["language_code"] == "en", str(v))
v = tl.classify(ENGLISH + ["Москва"])
check("an English transcript quoting one word in another alphabet is still English", v["verdict"] == "english", str(v))
v = tl.classify(SPANISH)
check("Spanish still reads as not English", v["verdict"] == "non_english" and not v["english_only_checks_ok"], str(v))

# ---------------------------------------------------------------- 4. listen-back tokens, on-screen copy
check("verify-cut keeps Cyrillic words", vcut.norm_tokens("Я ушла с работы") == ["я", "ушла", "с", "работы"],
      str(vcut.norm_tokens("Я ушла с работы")))


def plan_check(plan):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False)
        path = fh.name
    try:
        return subprocess.run([sys.executable, CHECK, path], capture_output=True, text=True,
                              encoding="utf-8").returncode
    finally:
        os.unlink(path)


RUSSIAN_REEL = {"verdict": "non_english", "code": None}
beat = lambda i, text: {"id": i, "graphic": "text", "kind": "kinetic-type", "on_screen": text}  # noqa: E731
check("a Russian card on a Russian reel passes the on-screen copy check",
      plan_check({"language": RUSSIAN_REEL, "beats": [beat(1, "Я ушла с работы")]}) == 0)
check("an English card on a Russian reel is still refused",
      plan_check({"language": RUSSIAN_REEL, "beats": [beat(1, "I quit my job")]}) == 1)

print(("FAILED: " + "; ".join(fails)) if fails else "cut language: other alphabets keep their lines and their language")
sys.exit(1 if fails else 0)
