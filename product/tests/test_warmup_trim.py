#!/usr/bin/env python3
"""Guard: a filming warm-up at the very start ("we go", "here we go", "okay three two one") is the camera rolling,
not the reel, so the transcript cut drops it. A real first line ("Hi, I'm you") is never dropped, and a warm-up
phrase said later, mid-reel, stays (it's part of what she said).

Run: python3 product/tests/test_warmup_trim.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CUT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "transcript-cut.py")
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({detail})"))
    if not cond:
        fails.append(name)


def kept(lines):
    tmp = tempfile.mkdtemp(prefix="warmup-")
    try:
        job = os.path.join(tmp, "projects", "my-reel")
        os.makedirs(os.path.join(job, "transcript"))
        t, words = 0.3, []
        for line in lines:
            for w in line.split():
                words.append({"w": w, "start": round(t, 2), "end": round(t + 0.3, 2), "prob": 0.95}); t += 0.35
            t += 0.8
        with open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8") as fh:
            json.dump({"clips": [{"clip": "clip.mov", "words": words}]}, fh)
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch")); os.makedirs(env["TMPDIR"])
        r = subprocess.run([sys.executable, CUT, job, "--print"], capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
        if r.returncode:
            return None, r.stderr[-300:]
        with open(os.path.join(job, "transcript", "cuts.json"), encoding="utf-8") as fh:
            return " | ".join(s["transcript"] for s in json.load(fh)["segments"]), ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


k, err = kept(["we go.", "Last week I made over half a million dollars.", "From a single digital product."])
check("a warm-up at the very start is dropped", k is not None and "we go" not in k and "Last week" in k, k or err)
k, err = kept(["Okay three two one.", "This is how I edit every reel.", "It takes me ten minutes."])
check("a countdown warm-up is dropped", k is not None and "three two one" not in k and "This is how" in k, k or err)
k, err = kept(["Hi, I'm you.", "This is how I edit every reel.", "And here we go.", "It takes me ten minutes."])
check("a real first line stays, and a warm-up phrase mid-reel stays", k is not None and "Hi, I'm you." in k and "here we go" in k, k or err)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "warm-ups go, real lines stay"))
sys.exit(1 if fails else 0)
