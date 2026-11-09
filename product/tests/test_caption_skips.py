#!/usr/bin/env python3
"""Her captions step aside while a takeover (or any look showing her words) plays, on the CAPTIONS' own clock.

A caption layer added at her first word starts after 0:00 (offset 1.588 s on a real reel); its page's timeline
counts from that offset, so a step-aside written in reel seconds landed late by exactly that much and a caption
("let") showed over the takeover (2026-10-17).
"""
import os, re, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {detail}")


def sets(page):
    return [(float(a), float(b)) for a, b in re.findall(r'autoAlpha:0\},([\d.]+)\);tl\.set\("#root",\{autoAlpha:1\},([\d.]+)', open(page, encoding="utf-8").read())]


if __name__ == "__main__":
    jd = tempfile.mkdtemp(prefix="cap-skips-")
    os.makedirs(os.path.join(jd, "caps"))
    page = os.path.join(jd, "caps", "index.html")
    open(page, "w", encoding="utf-8").write('<html><body><div id="root"></div></body></html>')
    ve._apply_skips(jd, "caps", "cap-all-single-word", [(14.83, 16.26), (0.5, 1.0)], offset=1.588)
    got = sets(page)
    check("skips: on the captions' own clock (reel time minus the layer's offset)",
          len(got) == 1 and abs(got[0][0] - 13.242) < 1e-3 and abs(got[0][1] - 14.672) < 1e-3, got)
    ve._apply_skips(jd, "caps", "cap-all-single-word", [(14.83, 16.26)])
    got = sets(page)
    check("skips: a caption layer at 0:00 is unchanged", got == [(14.83, 16.26)], got)
    check("skips: rewriting replaces, never stacks", open(page, encoding="utf-8").read().count('id="ve-skips"') == 1)
    # a highlight change redraws her added captions over her whole cut as it is today (first word to last), never
    # from a stale start (2026-10-17: every caption late by 1.6 s; then her first line lost its captions)
    import json
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    json.dump({"pack": "Butter", "layers": [{"name": "cap-all", "captions": True, "offset": 1.588, "dur": 80.0}]},
              open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    seen = []
    real = (ve.job_dir, ve.redraw_line_highlights, ve._adds, ve.place_look, ve._line_words)
    ve.job_dir = lambda job: jd
    ve.redraw_line_highlights = lambda job: []
    ve._adds = lambda d: {"cap-all": {"look": "single-word"}}
    ve._line_words = lambda d, a, b: [{"w": "we", "t": 0.933, "e": 1.093}, {"w": "thing.", "t": 88.0, "e": 88.4}]
    ve.place_look = lambda job, key, s0, e0, look, copy=None: seen.append((key, s0, e0, look)) or {}
    try:
        ve.redraw_captions("j")
    finally:
        ve.job_dir, ve.redraw_line_highlights, ve._adds, ve.place_look, ve._line_words = real
    check("redraw: added captions laid over her whole cut from her first word", seen == [("cap-all", 0.933, 88.4, "single-word")], seen)
    # THE YIELD RULE: a takeover owns its own words and is gone before her next word (never the old 1 s floor + tail)
    real = (ve.job_dir, ve._swap_pack, ve.word_cut_times, ve._line_words, ve._draw_choice, ve._span_words, ve._span_anchor, ve.swap, ve._atomic_json)
    got = {}
    ve.job_dir = lambda job: jd
    ve._swap_pack = lambda d, looks: ("Butter", None)
    ve.word_cut_times = lambda d: {0: (14.95, 15.2), 1: (15.65, 15.91), 2: (16.15, 16.3)}
    ve._line_words = lambda d, a, b: [{"w": "same", "t": 0.1, "e": 0.3}]
    ve._draw_choice = lambda jd_, l, rel, comp, text, dur, *a, **k: got.update(dur=dur) or {"dir": rel}
    ve._span_words = lambda *a: []
    ve._span_anchor = lambda *a: None
    ve.swap = lambda job, key, look: {}
    ve._atomic_json = lambda path, data: got.update(line=data) if path.endswith("line.json") else None
    try:
        ve.place_look("j", "add-w0", 14.95, 15.91, "takeover")
    finally:
        ve.job_dir, ve._swap_pack, ve.word_cut_times, ve._line_words, ve._draw_choice, ve._span_words, ve._span_anchor, ve.swap, ve._atomic_json = real
    end = got["line"]["offset"] + got["line"]["dur"]
    check("yield: a takeover is gone before her next word", end <= 16.15 - 0.02 + 1e-6, got)
    import lookbook as _lb
    check("yield: a takeover starts before her captions would show its first word early",
          got["line"]["offset"] <= 14.95 - _lb.CAPTION_LEAD_S + 1e-6, got)
    # her whole-reel captions are anchored to her first and last kept words, never to a stale second on the clock
    real = (ve.job_dir, ve.looks_manifest, ve._line_words, ve.place_look)
    called = []
    ve.job_dir = lambda job: jd
    ve.looks_manifest = lambda d: {"layers": [{"name": "cap-all", "captions": True, "offset": 1.588, "dur": 80}]}
    ve._line_words = lambda d, a, b: [{"w": "we", "t": 0.933, "e": 1.093}, {"w": "thing.", "t": 88.0, "e": 88.4}]
    ve.place_look = lambda job, key, s0, e0, look, copy=None: called.append((key, s0, e0, look)) or {}
    try:
        ve.set_captions("j", "single-word")
    finally:
        ve.job_dir, ve.looks_manifest, ve._line_words, ve.place_look = real
    check("captions: laid over her whole cut from her first word, not the old start", called == [("cap-all", 0.933, 88.4, "single-word")], called)
    # centered captions sit one locked spot per scene, 60 px under her chin: the scene list maps onto a look's clock
    import hashlib
    os.makedirs(os.path.join(jd, "transcript"), exist_ok=True)
    open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8").write('{"segments": []}')
    cid = hashlib.sha1(open(os.path.join(jd, "transcript", "cuts.json"), "rb").read()).hexdigest()[:10]
    json.dump({"cut_id": cid, "gap": 100, "scenes": [[0.0, 12.0, 1136], [12.0, 30.0, 940]]},
              open(os.path.join(jd, "review", "caption-scenes.json"), "w", encoding="utf-8"))
    tr = ve._caption_track(jd, 1.0, 20.0)
    import lookbook as _lbs
    _L = _lbs.CAPTION_LEAD_S
    check("scenes: each scene's spot on the look's own clock, moved as early as the captions, centre half a caption under the top",
          tr == [[0.0, round(11.0 - _L, 3), 1181], [round(11.0 - _L, 3), round(29.0 - _L, 3), 985]], tr)
    import caption_scenes
    check("scenes: 100 px under her chin, a new spot only past a real jump", caption_scenes.CAPTION_GAP == 100 and caption_scenes.SCENE_JUMP >= 80)
    # the spot follows where her chin USUALLY is, never the one lean that got lowest (2026-10-21: a lean to her laptop
    # dragged a 19 s scene's captions to y1819)
    # (that lean's piece read lowest 1759 but middle 928: the spot reads the middles, weighted by how long each plays)
    _sc = {"sum": 927 * 17.0 + 928 * 1.4, "w": 18.4}
    check("scenes: one lean down does not drag the scene's spot", abs(caption_scenes.typical(_sc) - 927) < 2)
    import lookbook
    check("drop in: on the takeover's animation menu", "drop-in" in [e["id"] for e in lookbook.effects_for("takeover", "Butter")])
    if fails:
        print(f"test_caption_skips: {len(fails)} of {total} checks FAILED")
        sys.exit(1)
    print(f"test_caption_skips: all {total} checks passed")
