#!/usr/bin/env python3
"""The rough cut drops Spanish filler fragments the way it drops "um" and "so", and keeps real Spanish lines.

The cutter's filler list was English only, so a Spanish take kept its "Este..." and "O sea." fragments. Only a
fragment of one or two words that are ALL filler is dropped, so a real line that starts with one ("este reel es
para ti", "o sea que sí") always stays.

Run: python3 product/tests/test_spanish_fillers.py   (Windows: python)
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CUT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "transcript-cut.py")
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:300]})"))
    if not cond:
        fails.append(name)


LINES = ["Este reel es para ti.", "Este...", "Hoy te enseño cómo edito mis videos.", "O sea.",
         "Pues.", "O sea que sí se puede.", "Bueno.", "Y eso es todo por hoy."]
tmp = tempfile.mkdtemp(prefix="spanish-fillers-")
try:
    job = os.path.join(tmp, "projects", "mi-reel")
    os.makedirs(os.path.join(job, "transcript"))
    t, words = 0.3, []
    for line in LINES:
        for w in line.split():
            words.append({"w": w, "start": round(t, 2), "end": round(t + 0.3, 2), "prob": 0.95}); t += 0.35
        t += 0.8
    with open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8") as fh:
        json.dump({"clips": [{"clip": "clip.mov", "words": words}]}, fh, ensure_ascii=False)
    env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"))
    os.makedirs(env["TMPDIR"])
    r = subprocess.run([sys.executable, CUT, job, "--print"], capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    check("the cut runs", r.returncode == 0, r.stderr[-400:])
    with open(os.path.join(job, "transcript", "cuts.json"), encoding="utf-8") as fh:
        kept = " | ".join(s["transcript"] for s in json.load(fh)["segments"])
    for filler in ("Este...", "O sea.", "Pues.", "Bueno."):
        check(f"the filler fragment {filler!r} is dropped", f"| {filler} |" not in f"| {kept} |", kept)
    for line in ("Este reel es para ti.", "Hoy te enseño cómo edito mis videos.", "O sea que sí se puede.",
                 "Y eso es todo por hoy."):
        check(f"the real line {line!r} stays", line in kept, kept)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "Spanish fillers go, Spanish lines stay"))
sys.exit(1 if fails else 0)
