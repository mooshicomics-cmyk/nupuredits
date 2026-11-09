#!/usr/bin/env python3
"""Guards: a change on one line never reworks anything else.

  stamp      a word the engine cut that WhisperX stamped 6 s long ("And" glued onto a pause) comes back as one
             word's length, beside the word after it; a sentence's last word keeps its start; an amount and a
             normal word keep their stamps; the page's words and her send both use this rule
  highlight  her highlighted words follow their WORDS when her cut changes, never the cut time they had when she
             picked them; a word her cut took out shows no highlight

Run: python3 product/tests/test_cut_edits_stay_put.py
"""
import inspect, json, os, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    s, e = ve.word_span({"t": "And", "s": 34.205, "e": 40.467})
    check("stamp: a 6 s 'And' comes back as one word, right before the next word", 40.0 < s < e == 40.467 and e - s < 0.7, (s, e))
    s, e = ve.word_span({"t": "cool.", "s": 3.3, "e": 7.9})
    check("stamp: a sentence's last word keeps its start", s == 3.3 and e - s < 0.7, (s, e))
    check("stamp: an amount keeps its whole stamp", ve.word_span({"t": "$27,000", "s": 8.2, "e": 11.4}) == (8.2, 11.4))
    check("stamp: a normal word keeps its stamp", ve.word_span({"t": "launch", "s": 1.0, "e": 1.45}) == (1.0, 1.45))
    src = inspect.getsource(ve.apply_edits)
    check("stamp: her send uses the rule for words the engine cut", "word_span(w, last=" in src and "seg_of[i] is None" in src)
    check("stamp: the page's words use the same rule", "if seg_of[i] is not None else word_span(w, last=" in open(ve.__file__, encoding="utf-8").read())
    s, e = ve.word_span({"t": "so", "s": 10.0, "e": 14.0}, last=True)
    check("stamp: the last word of a clip keeps its start (its tail is silence)", s == 10.0 and e - s < 0.7, (s, e))

    src = inspect.getsource(ve._draw_media)
    check("picture: a picture keeps the box it was placed with (a new face reading never resizes it)",
          'box = m.get("box")' in src and "dict(m, box=box)" in src)
    jd = tempfile.mkdtemp(prefix="stay-put-")
    os.makedirs(os.path.join(jd, "transcript"))
    json.dump({"items": [{"i": 27, "text": "$27,000", "t": 8.207, "on": True}, {"i": 40, "text": "And", "t": 34.2, "on": True},
                         {"i": 50, "text": "room.", "t": 60.0, "on": True}]},
              open(os.path.join(jd, "transcript", "accents.json"), "w", encoding="utf-8"))
    real = ve.word_cut_times
    ve.word_cut_times = lambda _jd: {27: (14.5, 15.2), 50: (66.0, 66.4)}     # her cut moved: word 27 now plays at 14.5 s; 40 is cut
    try:
        got = {a["w"]: a["t"] for a in ve._her_accents(jd)}
        check("highlight: a highlight follows its word to its new time", got.get("$27,000") == 14.5 and got.get("room.") == 66.0, got)
        check("highlight: a word her cut took out shows no highlight", "And" not in got, got)
    finally:
        ve.word_cut_times = real
        shutil.rmtree(jd, ignore_errors=True)
    if fails:
        print(f"test_cut_edits_stay_put: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_cut_edits_stay_put: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
