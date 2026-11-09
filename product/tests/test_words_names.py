#!/usr/bin/env python3
"""words.json names: a transcript written with WhisperX's own names ("word", "score") cuts exactly like one
written with the older ones ("w", "prob"), so every job made before keeps working.

  writers   word-timings.sh and transcribe-nofw.py write "word" and "score".
  readers   the cutter and the transcript builder read either.

Run: python3 product/tests/test_words_names.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


SENTENCES = [
    "So today I want to tell you something.", "Okay let me start over.",
    "Today I want to tell you about the week after a launch.", "Um.",
    "Nobody posts about the crash.", "It is real and it is normal.",
]


def words(new):
    out, t = [], 0.5
    for s in SENTENCES:
        for tok in s.split():
            out.append({("word" if new else "w"): tok, "start": round(t, 3), "end": round(t + 0.3, 3),
                        ("score" if new else "prob"): 0.9})
            t += 0.35
        t += 0.6
    return out


def job(tmp, name, new):
    d = os.path.join(tmp, "projects", name)
    os.makedirs(os.path.join(d, "transcript"))
    os.makedirs(os.path.join(d, "raw"))
    open(os.path.join(d, "raw", "take.mp4"), "wb").close()
    with open(os.path.join(d, "transcript", "words.json"), "w", encoding="utf-8") as fh:
        json.dump({"clips": [{"clip": "take.mp4", "path": "raw/take.mp4", "duration": 30.0,
                              "words": words(new)}]}, fh)
    return d


def run(argv):
    r = subprocess.run([sys.executable, *argv], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="words-names-")
    try:
        old, new = job(tmp, "older-names", False), job(tmp, "whisperx-names", True)
        rc_o, out_o = run([os.path.join(SCRIPTS, "transcript-cut.py"), old, "--print"])
        rc_n, out_n = run([os.path.join(SCRIPTS, "transcript-cut.py"), new, "--print"])
        check("both transcripts cut", rc_o == 0 and rc_n == 0, (out_o, out_n))
        check("the cut is the same whichever names the transcript uses",
              out_o.replace("older-names", "J") == out_n.replace("whisperx-names", "J"), (out_o, out_n))
        check("the cut actually kept words", "Nobody posts about the crash" in out_n, out_n)
        for f in ("word-timings.sh", os.path.join("..", "..", "..", "..", "scripts", "transcribe-nofw.py")):
            src = open(os.path.join(SCRIPTS, f), encoding="utf-8").read()
            check(f"{os.path.basename(f)} writes WhisperX's names", '"word":' in src and '"score":' in src
                  and '"w":' not in src and '"prob":' not in src)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_words_names: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_words_names: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
