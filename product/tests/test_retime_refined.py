#!/usr/bin/env python3
"""Guards: a look she refined waits for Claude after a cut change only when ITS words moved.

  still    its first word sits where the look starts: nothing for Claude (looks-retimed stays empty)
  moved    its first word moved past the drift allowance: Claude redoes it
  cut      its first word was cut: Claude redoes it
  kept     a look she placed (a GIF she asked to start later, a look she trimmed) moves by exactly how far its own
           words moved, her start and length kept; moved twice, it never moves twice as far; a cut inside its
           words rebuilds it on its words, never on the word in its name

Run: python3 product/tests/test_retime_refined.py
"""
import json, os, shutil, sys, tempfile
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


def run_place(times, entry):
    jd = tempfile.mkdtemp(prefix="retime-keep-")
    os.makedirs(os.path.join(jd, "review"))
    os.makedirs(os.path.join(jd, entry["dir"]), exist_ok=True)   # its drawing is on her reel (a gone one is never moved)
    json.dump({"layers": []}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    json.dump({"cut_id": "c2", "order": [], "words": []}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    calls = []
    real = (ve.job_dir, ve.word_cut_times, ve._adds, ve.redraw_captions, ve.looks_manifest, ve.place_look)
    ve.job_dir = lambda job: jd
    ve.word_cut_times = lambda _jd: times
    ve._adds = lambda _jd: {"add-w41": dict(entry)}
    ve.redraw_captions = lambda job: {}
    ve.looks_manifest = lambda _jd: None
    ve.place_look = lambda job, key, s0, e0, look: calls.append((round(s0, 3), round(e0, 3)))
    try:
        ve.retime_adds("x")
        return calls
    finally:
        ve.job_dir, ve.word_cut_times, ve._adds, ve.redraw_captions, ve.looks_manifest, ve.place_look = real
        shutil.rmtree(jd, ignore_errors=True)


def run(times, entry):
    jd = tempfile.mkdtemp(prefix="retime-refined-")
    os.makedirs(os.path.join(jd, "review"))
    os.makedirs(os.path.join(jd, entry["dir"]), exist_ok=True)   # its drawing is on her reel (a gone one is never moved)
    json.dump({"layers": []}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    json.dump({"cut_id": "c2", "order": [], "words": []}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    real = (ve.job_dir, ve.word_cut_times, ve._adds, ve.redraw_captions, ve.looks_manifest, ve.place_look)
    ve.job_dir = lambda job: jd
    ve.word_cut_times = lambda _jd: times
    ve._adds = lambda _jd: {"add-w27": dict(entry)}
    ve.redraw_captions = lambda job: {}
    ve.looks_manifest = lambda _jd: None
    ve.place_look = lambda *a, **k: None
    try:
        ve.retime_adds("x")
        return ve.looks_to_redo(jd)
    finally:
        ve.job_dir, ve.word_cut_times, ve._adds, ve.redraw_captions, ve.looks_manifest, ve.place_look = real
        shutil.rmtree(jd, ignore_errors=True)


def main():
    refined = {"look": "takeover", "dir": "hf-graphics/_looks/add-w27/refined-1/hf-reel-type-butter", "offset": 8.087, "dur": 3.05}
    check("still: a refined look whose words never moved needs nothing from Claude",
          run({27: (8.207, 8.9), 28: (8.95, 9.3)}, refined) == [])
    check("moved: a refined look whose first word moved waits for Claude",
          run({27: (12.4, 13.0)}, refined) == ["add-w27"])
    check("cut: a refined look whose first word was cut waits for Claude",
          run({28: (8.95, 9.3)}, refined) == ["add-w27"])
    gif = {"look": "media", "dir": "hf-graphics/_looks/add-w41/media/hf-reel-type-media", "offset": 15.75, "dur": 2.35,
           "span": [15.75, 18.1], "words": [44, 51], "anchor": [15.70, 17.90]}
    later = {41: (16.15, 16.4), 44: (16.70, 17.0), 51: (18.90, 19.3)}       # her cut grew by 1 s before this line
    check("kept: a GIF she set to start later moves by exactly how far its words moved, start and length kept",
          run_place(later, gif) == [(16.75, 19.1)], run_place(later, gif))
    check("kept: words that didn't move leave it exactly where it is", run_place({44: (15.70, 16.0), 51: (17.90, 18.3)}, gif) == [])
    moved_once = dict(gif, span=[16.75, 19.1], anchor=[16.70, 18.90])          # what the first move wrote
    check("kept: moved again with nothing new, it stays put (never twice as far)", run_place(later, moved_once) == [])
    inside = {41: (15.15, 15.4), 44: (15.70, 16.0), 51: (17.20, 17.6)}         # she cut words inside its own stretch
    got = run_place(inside, gif)
    check("kept: a cut inside its words rebuilds it from its own first word, never the word in its name",
          got and got[0][0] == 15.70, got)
    if fails:
        print(f"test_retime_refined: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_retime_refined: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
