#!/usr/bin/env python3
"""build-captions.py (the opt-in editable CapCut captions): no caption runs into the next, and a re-run replaces
its own track instead of stacking another one.

Buyer reports (launch week, 2026-10-19), each hand-patched by the buyer's Claude:
  - the last clip of a line hung on +0.7 s (build) / +0.4 s (single) / +0.8 s (takeover) past its last word with
    no clamp, so it sat on screen over the next line's first caption; the 0.12 s minimum did the same to quick words
  - a re-run looked for its old track by the name "captions", but the magnet (capcut_ripple) blanks every
    non-main track's name, so each run added another full captions track on top of the last

  1. every clip ends at or before the next clip starts (a takeover's stacked words share one end, which stops at
     the next line); a line with nothing after it keeps its full hang-on; a quick word is cut at the next word
  2. three runs over one draft leave only this run's captions tracks, holding this run's clips only; a takeover's
     stacked words (on screen together) each get a track, since a CapCut track holds one clip at a time
  3. a draft captioned before the fix (a nameless text track at render_index 16000) is replaced too; her own
     text track is left alone, and so are her texts' materials
  4. the words are timed on the rough cut; when she has stretched or trimmed a clip in CapCut since, each caption
     goes where her draft now plays that word (a buyer's ran 0.73 s early after one stretch), and a word she
     trimmed away is left out

Nothing real is touched: the builder runs on an in-memory draft in a throwaway folder.

Run:  python3 product/tests/test_build_captions_clamp.py
"""
import copy
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
fails = []
US = 1_000_000


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


JOB = "zz-test-build-captions-clamp"
os.environ.update(JOB=JOB, STYLE_PACK=os.environ.get("TEST_STYLE_PACK", "Butter"))
try:
    spec = importlib.util.spec_from_file_location("build_captions", os.path.join(PRODUCT, "build-captions.py"))
    bc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bc)
except SystemExit as e:   # no caption templates / pack on this copy: nothing to build captions with
    print(f"build-captions clamp: skipped ({e})")
    sys.exit(0)

tmp = tempfile.mkdtemp()
try:
    bc.ROOT = tmp
    jd = os.path.join(tmp, "projects", JOB)
    os.makedirs(jd)

    def W(w, t, e):
        return {"w": w, "t": t, "e": e}

    LINES = [
        [W("this", 0.00, 0.30), W("is", 0.30, 0.55), W("it.", 0.60, 1.00)],                 # single, next at 1.20
        [W("we", 1.20, 1.40), W("grow", 1.45, 1.90), W("here.", 1.95, 2.50)],               # build, next at 2.80
        [W("big", 2.80, 3.00), W("takeover", 3.05, 3.30), W("moment.", 3.35, 3.60)],        # takeover, next at 3.90
        [W("quick", 3.90, 3.94), W("words", 3.95, 4.20), W("done.", 4.25, 4.50)],           # single, the last line
    ]
    with open(os.path.join(jd, "edit-timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"beats": [{"words": [w for line in LINES for w in line]}]}, fh)
    bc.BUILD_RANGES = [(1.1, 1.3)]
    bc.TAKEOVER_KEYS = ["takeover"]

    print("1. no caption runs into the next")
    clips = bc.build_clips()
    spans = [(s["target_timerange"]["start"], s["target_timerange"]["start"] + s["target_timerange"]["duration"],
              json.loads(m["content"])["text"]) for m, _a, s in clips]
    starts = sorted({a for a, _b, _t in spans})
    over = [(t, b / US, nxt / US) for a, b, t in spans for nxt in [next((x for x in starts if x > a), None)]
            if nxt is not None and b > nxt and t not in ("big", "takeover", "moment.")]
    check("every single / build clip ends at or before the next clip starts", not over, str(over))
    end_of = {t: b / US for a, b, t in spans}
    check("a single line's last word stops where the next line starts (not +0.4 s past it)",
          abs(end_of["it."] - 1.20) < 1e-6, end_of["it."])
    check("a build line's last clip stops where the next line starts (not +0.7 s past it)",
          abs(end_of["we grow here."] - 2.80) < 1e-6, end_of["we grow here."])
    take = [b / US for a, b, t in spans if t in ("big", "takeover", "moment.")]
    check("a takeover's stacked words all end together, where the next line starts (not +0.8 s past it)",
          len(take) == 3 and all(abs(b - 3.90) < 1e-6 for b in take), str(take))
    check("a quick word under the 0.12 s minimum is cut at the next word", abs(end_of["quick"] - 3.95) < 1e-6,
          end_of["quick"])
    check("the last line, with nothing after it, keeps its full hang-on", abs(end_of["done."] - 4.90) < 1e-6,
          end_of["done."])
    check("every caption material carries the builder's tag", all(m.get("name") == bc.CAPTION_TAG for m, _a, _s in clips))

    print("2-3. re-runs replace the builder's own track, never stack another")
    tpl_seg, tpl_mat = bc.TPL["segment"], bc.TPL["material"]

    def her_text(i, ridx):
        m = copy.deepcopy(tpl_mat); m["id"] = f"hers-{i}"; m["name"] = ""
        s = copy.deepcopy(tpl_seg); s["id"] = f"HERSEG-{i}"; s["material_id"] = m["id"]; s["render_index"] = ridx
        s["extra_material_refs"] = []
        s["target_timerange"] = {"start": i * US, "duration": US}
        return m, s

    legacy_m, legacy_s = her_text(0, 16000)
    legacy_m["id"] = "legacy-0"; legacy_s["material_id"] = "legacy-0"           # an old run, before the tag
    mine_m, mine_s = her_text(1, 15000)                                          # a title she added herself
    video = {"id": "vid-1", "type": "video", "material_name": "her.mp4", "path": "/x/her.mp4", "duration": 6 * US}
    draft = {"tracks": [{"type": "video", "flag": 0, "id": "MAIN", "name": "", "segments": [
                {"id": "VSEG", "material_id": "vid-1", "render_index": 0, "extra_material_refs": [],
                 "target_timerange": {"start": 0, "duration": 6 * US},
                 "source_timerange": {"start": 0, "duration": 6 * US}}]},
                        {"type": "text", "flag": 0, "id": "LEGACY", "name": "", "is_default_name": True, "segments": [legacy_s]},
                        {"type": "text", "flag": 0, "id": "HERS", "name": "", "is_default_name": True, "segments": [mine_s]}],
             "materials": {"videos": [video], "texts": [legacy_m, mine_m], "material_animations": []},
             "config": {}, "canvas_config": {"width": 1080, "height": 1920}}
    path = os.path.join(tmp, "draft_content.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(draft, fh)
    try:
        for _ in range(3):
            bc.inject(path)
    except Exception as e:   # the shared draft guards may want more of a real draft than this one carries
        check("inject runs on a minimal draft", False, repr(e))
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    texts = [t for t in d["tracks"] if t.get("type") == "text"]
    ours = bc.find_caption_tracks(d)
    # the takeover's three stacked words share the screen, so they need three tracks; nothing else needs more than one
    check("after three runs there are only this run's captions tracks (one per stacked takeover word)",
          len(ours) == 3, f"{len(ours)} found")
    check("they hold this run's clips only", sum(len(t["segments"]) for t in ours) == len(clips),
          f"{sum(len(t['segments']) for t in ours)} vs {len(clips)}")
    clash = []
    for t in ours:
        segs = sorted(t["segments"], key=lambda x: x["target_timerange"]["start"])
        clash += [(a["id"], b["id"]) for a, b in zip(segs, segs[1:])
                  if a["target_timerange"]["start"] + a["target_timerange"]["duration"] > b["target_timerange"]["start"]]
    check("no track holds two clips at once (CapCut can't)", not clash, clash)
    check("every caption but the stacked takeover words sits on the first track",
          len(ours[0]["segments"]) == len(clips) - 2 if ours else False)
    check("the pre-fix nameless captions track is gone", not any(t.get("id") == "LEGACY" for t in d["tracks"]))
    check("her own text track is untouched", any(t.get("id") == "HERS" and t["segments"][0]["id"] == "HERSEG-1"
                                                 for t in texts))
    ids = {m["id"] for m in d["materials"]["texts"]}
    check("her text stays in the materials; the old captions' texts are gone", "hers-1" in ids and "legacy-0" not in ids)
    check("no orphaned caption texts pile up across runs",
          len([m for m in d["materials"]["texts"] if m.get("name") == bc.CAPTION_TAG]) == len(clips))
    check("no other text tracks (hers + the captions tracks)", len(texts) == 1 + len(ours), str([t.get("id") for t in texts]))

    print("4. captions follow her CapCut timeline")
    os.makedirs(os.path.join(jd, "transcript"), exist_ok=True)
    with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": [{"clip": "a.mp4", "start": 0.0, "end": 2.0}, {"clip": "a.mp4", "start": 3.0, "end": 5.0}]}, fh)
    vids = [{"id": "va", "type": "video", "path": "/footage/a.mp4", "material_name": "a.mp4"}]
    def seg(src0, src1, tgt0):
        return {"id": NIDs.pop(), "material_id": "va", "source_timerange": {"start": int(src0 * US), "duration": int((src1 - src0) * US)},
                "target_timerange": {"start": int(tgt0 * US), "duration": int((src1 - src0) * US)}, "speed": 1.0}
    NIDs = [f"S{i}" for i in range(10)]
    same = {"tracks": [{"type": "video", "segments": [seg(0.0, 2.0, 0.0), seg(3.0, 5.0, 2.0)]}], "materials": {"videos": vids}}
    check("a draft that plays the cut as built changes nothing", bc.draft_clock(same, tmp) is None)
    # she stretched the first clip 0.73 s at a double take, and trimmed 0.4 s off the second one's start
    hers = {"tracks": [{"type": "video", "segments": [seg(0.0, 2.73, 0.0), seg(3.4, 5.0, 2.73)]}], "materials": {"videos": vids}}
    clock = bc.draft_clock(hers, tmp)
    check("a draft she trimmed in CapCut gets its own clock", clock is not None)
    if clock:
        check("a word in the first clip stays put", abs(clock(0.5) - 0.5) < 1e-6, clock(0.5))
        check("a word after her stretch moves with it", abs(clock(2.6) - (2.73 + 0.2)) < 1e-6, clock(2.6))
        check("a word inside the bit she trimmed shows from the clip's first frame", abs(clock(2.1) - 2.73) < 1e-6, clock(2.1))
    far = {"tracks": [{"type": "video", "segments": [seg(0.0, 2.0, 0.0), seg(4.8, 5.0, 2.0)]}], "materials": {"videos": vids}}
    clock = bc.draft_clock(far, tmp)
    check("a word she trimmed well away is left out", clock is not None and clock(2.1) is None)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "build-captions clamp: captions never overlap, re-runs replace their own track"))
sys.exit(1 if fails else 0)
