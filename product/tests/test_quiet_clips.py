#!/usr/bin/env python3
"""Guards: a clip she filmed with no talking in it (product/quiet_clips.py).

  decide     the measured cases: two store-noise clips are quiet; real talking, a sentence said once in a long clip,
             and a soft sentence are not
  mark       a quiet clip is saved silent, its phantom words set aside (never a cut, never a caption); idempotent
  cut        the rough cut keeps a quiet clip whole
  editor     the editor shows it as one-second beats (no text), five to a line, and her cut of them comes back as
             pieces with no transcript and pinned edges
  page       the page says "No talking", counts seconds not words, and never warns about clipping a breath

Run: python3 product/tests/test_quiet_clips.py
"""
import json, os, shutil, subprocess, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import quiet_clips as qc  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


def W(word, s, e, score):
    return {"word": word, "start": s, "end": e, "score": score}


# ── decide: the cases measured on her reels ──
stavros = {"clip": "store.mov", "duration": 21.1, "words": [W("Stavros", 7.3, 7.8, 0.44), W("Stavros", 7.9, 8.5, 0.44)]}
credit = {"clip": "aisle.mp4", "duration": 10.0, "words": [W("Undertexter", 7.35, 7.78, 0.215), W("av", 7.82, 7.88, 0.248),
                                                           W("Nicolai", 7.92, 8.08, 0.072), W("Winther", 8.12, 8.36, 0.248)]}
talking = {"clip": "yap.mov", "duration": 20.8, "words": [W(f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.83) for i in range(39)]}
one_line = {"clip": "vlog.mov", "duration": 30.0, "words": [W(x, 3 + i * 0.4, 3.35 + i * 0.4, 0.8) for i, x in enumerate("look how big she is".split())]}
soft = {"clip": "soft.mov", "duration": 6.0, "words": [W(x, i * 0.4, i * 0.4 + 0.3, 0.4) for i, x in enumerate("this one is my favorite part".split())]}
check(qc.is_silent(stavros) and qc.is_silent(credit), "decide: store noise must read as no talking")
check(qc.is_silent({"clip": "x", "duration": 5, "words": []}), "decide: a clip with no words has no talking")
check(not qc.is_silent(talking), "decide: real talking is never quiet")
check(not qc.is_silent(one_line), "decide: one real sentence in a long clip is kept (sparse but sure)")
check(not qc.is_silent(soft), "decide: a soft sentence said at a talking pace is kept (unsure but not sparse)")
check(not qc.is_silent({"clip": "old", "duration": 30, "words": [{"word": "hi", "start": 1, "end": 1.3}]}),
      "decide: an older transcript without scores is trusted")

# ── mark: saved silent, phantom words set aside, idempotent ──
tmp = tempfile.mkdtemp(prefix="quiet-")
try:
    p = os.path.join(tmp, "words.json")
    json.dump({"clips": [json.loads(json.dumps(stavros)), json.loads(json.dumps(talking))]}, open(p, "w", encoding="utf-8"))
    check(qc.mark(p) == ["store.mov"], "mark: only the quiet clip is marked")
    d = json.load(open(p, encoding="utf-8"))
    c0, c1 = d["clips"]
    check(c0.get("silent") is True and c0["words"] == [] and [w["word"] for w in c0["heard_in_noise"]] == ["Stavros", "Stavros"],
          "mark: a quiet clip has no words (never a caption) and keeps what was heard aside")
    check(len(c1["words"]) == 39 and "silent" not in c1, "mark: a talking clip is untouched")
    check(qc.mark(p) == [] and json.load(open(p, encoding="utf-8")) == d, "mark: running it again changes nothing")
    check(qc.is_silent(c0), "mark: a marked clip stays quiet")

    # ── cut: the rough cut keeps a quiet clip whole ──
    job = os.path.join(tmp, "quiet-job")
    os.makedirs(os.path.join(job, "transcript"))
    json.dump({"clips": [c0]}, open(os.path.join(job, "transcript", "words.json"), "w", encoding="utf-8"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "transcript-cut.py"),
                        job, "--clip", "store.mov"], capture_output=True, text=True, encoding="utf-8")
    segs = json.load(open(os.path.join(job, "transcript", "cuts.json"), encoding="utf-8"))["segments"] if r.returncode == 0 else []
    check(len(segs) == 1 and segs[0]["start"] == 0.0 and abs(segs[0]["end"] - 21.07) < 0.05 and segs[0]["keep_edges"]
          and segs[0]["transcript"] == "", f"cut: a quiet clip is kept whole, got {segs} {r.stderr[-300:]}")
    check("no talking in this clip" in r.stdout, "cut: the cut says the clip had no talking")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── editor: beats, five to a line ──
import visual_editor as ve  # noqa: E402
beats = qc.quiet_beats({"clip": "q", "duration": 12.3}, 0)
check(len(beats) == 12 and beats[-1]["s"] == 11.0 and beats[0] == {"t": "", "c": 0, "s": 0.0, "e": 1.0, "q": True} and beats[-1]["e"] == 12.3,
      f"editor: one beat a second, the last takes the remainder (no sliver), got {len(beats)}")
ws = ve.words_of([{"clip": "q", "duration": 12.3, "silent": True, "words": []}, talking])
check(sum(1 for w in ws if w.get("q")) == 12 and sum(1 for w in ws if not w.get("q")) == 39,
      "editor: a quiet clip comes in as beats, a talking clip as its words")
check(not any(w["t"] for w in ws if w.get("q")), "editor: a beat never carries a word she didn't say")
ws_q = ve.words_of([{"clip": "q", "duration": 12.3, "silent": True, "words": []}])
lines = ve.lines_of(ws_q, list(range(len(ws_q))), [0] * len(ws_q), set())
check([len(l) for l in lines] == [5, 5, 2], f"editor: quiet footage reads as five-second lines, got {[len(l) for l in lines]}")
src = open(os.path.join(PRODUCT, "visual_editor.py"), encoding="utf-8").read()
check(src.count('if words[i]["t"])') >= 2 and src.count('all(words[i].get("q") for i in r)') >= 2,
      "editor: her cut of quiet seconds comes back with no transcript text and pinned edges")

# ── page ──
page = open(os.path.join(PRODUCT, "visual-editor", "editor.html"), encoding="utf-8").read()
check("No talking · ${" in page, "page: a quiet line says No talking and how long")
check('second${n === 1 ? "" : "s"}` : n === 1' in page, "page: cutting quiet footage counts seconds, not words")
check("!W[a].q && !W[b].q" in page, "page: no 'said in one breath' warning between seconds of no talking")
check("of no talking changed" in page, "page: the changes chip counts seconds of no talking apart from words")

if fails:
    print("test_quiet_clips: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_quiet_clips: all {n} checks passed")
