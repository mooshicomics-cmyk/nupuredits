#!/usr/bin/env python3
"""Re-cutting a finished CapCut draft (product/capcut_recut.py), the way CapCut itself splits a clip.

These checks run on a synthetic draft (no CapCut, no real drafts touched):
  * clip_edges reads her clips from inside a compound main clip;
  * recut() to "3,1" (a later clip moved to the front, one left out): every track has no overlaps, the main track is
    contiguous from 0, every material a piece names exists, every id is unique, the compound stays shared while each
    piece gets its own copy of every other material, keyframes are re-based to the piece with a value pinned at each
    cut edge, an in-animation / fade-in stays only on the piece holding the clip's real start and an out-animation /
    fade-out only on the piece holding its real end; the original draft is never changed;
  * the magnet anchors her footage track (capcut_ripple, given the main track), never the busiest overlay;
  * her music bed is never cut with her clips: laid fresh, one continuous play, her volume shape, the bottom track;
    an older trial's jumping bed is replaced the same way (fresh_bed);
  * the hook takes a stretch with no graphic in its spot (hook_window, graphic_spans);
  * her own hook block is found, lifted off and cloned back with new words (add_hook, from a draft on disk);
  * trial_reels turns an open / drop plan into her clip runs.

Run: python3 product/tests/test_capcut_recut.py
"""
import copy, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import capcut_recut as cr
import draft_safety
fails = []
S = 1_000_000


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))
    else:
        print(f"  ok   {name}")


def tr(start, dur):
    return {"start": int(start * S), "duration": int(dur * S)}


def text_mat(mid, text):
    return {"id": mid, "type": "text", "content": json.dumps(
        {"text": text, "styles": [{"range": [0, len(text)], "font": {"path": "/fonts/Hook.ttf"}, "size": 12}]})}


def synthetic():
    d = _synthetic()
    d["materials"]["audios"].append(d.pop("_song"))
    return d


def _synthetic():
    inner = {"tracks": [{"id": "inner-v", "type": "video", "segments": [
        {"id": "in1", "material_id": "iv", "target_timerange": tr(0, 2), "source_timerange": tr(10, 2)},
        {"id": "in2", "material_id": "iv", "target_timerange": tr(2, 3), "source_timerange": tr(20, 3)},
        {"id": "in3", "material_id": "iv", "target_timerange": tr(5, 4), "source_timerange": tr(30, 4)}]}],
        "materials": {"videos": [{"id": "iv", "path": "/raw.mp4"}]}}
    return {
        "id": "TIMELINE-1", "duration": 9 * S,
        "materials": {
            "videos": [{"id": "vid-compound", "type": "video"}, {"id": "vid-ov", "type": "video"}],
            "drafts": [{"id": "draft-1", "draft": inner}],
            "speeds": [{"id": "speed-1", "speed": 1.0}],
            "canvases": [{"id": "canvas-ov"}],
            "texts": [text_mat("text-1", "a caption"), text_mat("hook-1", "her old hook")],
            "material_animations": [{"id": "anim-1", "animations": [{"type": "in", "id": "a-in"}, {"type": "out", "id": "a-out"}]}],
            "audios": [{"id": "aud-1"}],
            "audio_fades": [{"id": "fade-1", "fade_in_duration": 100000, "fade_out_duration": 100000}],
        },
        "_song": {"id": "song", "type": "extract_music", "path": "/music/song.mp3", "name": "song.mp3", "duration": 60 * S},
        "tracks": [
            {"id": "t-main", "type": "video", "segments": [
                {"id": "main", "material_id": "vid-compound", "extra_material_refs": ["draft-1", "speed-1"],
                 "target_timerange": tr(0, 9), "source_timerange": tr(0, 9), "speed": 1.0}]},
            {"id": "t-ov", "type": "video", "segments": [
                {"id": "ov", "material_id": "vid-ov", "extra_material_refs": ["canvas-ov"],
                 "target_timerange": tr(1, 7), "source_timerange": tr(0, 7), "speed": 1.0,
                 "common_keyframes": [{"id": "kfg", "property_type": "KFTypeScaleX", "keyframe_list": [
                     {"id": "k1", "time_offset": 0, "values": [1.0]},
                     {"id": "k2", "time_offset": 7 * S, "values": [2.0]}]}]}]},
            {"id": "t-text", "type": "text", "segments": [
                {"id": "txt", "material_id": "text-1", "extra_material_refs": ["anim-1"],
                 "target_timerange": tr(0, 9), "clip": {"transform": {"x": 0, "y": -0.5}, "scale": {"x": 1, "y": 1}}}]},
            {"id": "t-hook", "type": "text", "segments": [
                {"id": "hook", "material_id": "hook-1", "extra_material_refs": [],
                 "target_timerange": tr(0, 3), "clip": {"transform": {"x": 0, "y": 0.7}, "scale": {"x": 1, "y": 1}}}]},
            {"id": "t-sfx", "type": "audio", "segments": [
                {"id": "sfx", "material_id": "aud-1", "extra_material_refs": ["fade-1"],
                 "target_timerange": tr(4, 2), "source_timerange": tr(0, 2), "speed": 1.0}]},
            {"id": "t-bed", "type": "audio", "segments": [
                {"id": "bed", "material_id": "song", "extra_material_refs": [], "volume": 0.2,
                 "target_timerange": tr(0, 9), "source_timerange": tr(2, 9), "speed": 1.0,
                 "common_keyframes": [{"id": "kfv", "property_type": "KFTypeVolume", "keyframe_list": [
                     {"id": "v1", "time_offset": 0, "values": [0.3]},
                     {"id": "v2", "time_offset": 6 * S, "values": [0.2]}]}]}]},
        ],
    }


def all_refs(d):
    for t in d["tracks"]:
        for s in t["segments"]:
            for r in [s.get("material_id")] + list(s.get("extra_material_refs") or []):
                if r:
                    yield s, r


def ids(d):
    out = [t["id"] for t in d["tracks"]] + [s["id"] for t in d["tracks"] for s in t["segments"]]
    out += [m["id"] for v in d["materials"].values() if isinstance(v, list) for m in v]
    out += [k["id"] for t in d["tracks"] for s in t["segments"] for g in s.get("common_keyframes") or []
            for k in g["keyframe_list"]]
    return out


def segs(d, tid):
    return sorted(next(t for t in d["tracks"] if t["id"] == tid)["segments"], key=lambda s: s["target_timerange"]["start"])


def test_recut():
    d = synthetic()
    before = copy.deepcopy(d)
    edges = cr.clip_edges(d)
    check("clip edges come from inside the compound", edges == [(0, 2 * S), (2 * S, 5 * S), (5 * S, 9 * S)], edges)
    pieces = cr.pieces_from_lines(d, "3,1")
    check("'3,1' names clip 3 then clip 1", pieces == [(5 * S, 9 * S), (0, 2 * S)], pieces)
    r = cr.recut(d, pieces, seed="trial")
    check("her draft is never changed", d == before)
    check("the new length is the pieces' length", r["duration"] == 6 * S, r["duration"])

    overlaps = []
    for t in r["tracks"]:
        ss = sorted(t["segments"], key=lambda s: s["target_timerange"]["start"])
        for a, b in zip(ss, ss[1:]):
            if a["target_timerange"]["start"] + a["target_timerange"]["duration"] > b["target_timerange"]["start"]:
                overlaps.append((t["id"], a["id"], b["id"]))
    check("no segment overlaps another on its track", not overlaps, overlaps)

    main = segs(r, "t-main")
    cursor, gaps = 0, []
    for s in main:
        if s["target_timerange"]["start"] != cursor:
            gaps.append((cursor, s["target_timerange"]["start"]))
        cursor = s["target_timerange"]["start"] + s["target_timerange"]["duration"]
    check("the main track is contiguous from 0 to the end", not gaps and cursor == r["duration"], (gaps, cursor))
    check("each main piece plays the right stretch of her reel",
          [s["source_timerange"] for s in main] == [tr(5, 4), tr(0, 2)], [s["source_timerange"] for s in main])

    pool = cr._pool(r)
    missing = [(s["id"], ref) for s, ref in all_refs(r) if ref not in pool]
    check("every material a segment names exists", not missing, missing)
    every = ids(r)
    dup = sorted({i for i in every if every.count(i) > 1})
    check("every id is unique", not dup, dup)
    check("the compound stays one shared draft, each piece has its own speed",
          all("draft-1" in s["extra_material_refs"] for s in main) and len(r["materials"]["drafts"]) == 1
          and len({s["extra_material_refs"][1] for s in main}) == 2 and "speed-1" not in pool, [s["extra_material_refs"] for s in main])
    unused = [m["id"] for k, v in r["materials"].items() if isinstance(v, list) and k != "drafts"
              for m in v if m["id"] not in {ref for _s, ref in all_refs(r)}]
    check("no original material is left behind unused", not unused, unused)

    ov = segs(r, "t-ov")
    check("the overlay is cut into two pieces where it crosses the clips",
          [(s["target_timerange"], s["source_timerange"]) for s in ov] == [(tr(0, 3), tr(4, 3)), (tr(5, 1), tr(0, 1))],
          [(s["target_timerange"], s["source_timerange"]) for s in ov])
    k_a = ov[0]["common_keyframes"][0]["keyframe_list"]
    k_b = ov[1]["common_keyframes"][0]["keyframe_list"]
    check("keyframes are re-based to their piece, the ramp pinned at the cut edge",
          [k["time_offset"] for k in k_a] == [0, 3 * S] and abs(k_a[0]["values"][0] - (1 + 4 / 7)) < 1e-9
          and k_a[1]["values"] == [2.0], k_a)
    check("a piece that ends mid-ramp holds the ramp's value there",
          [k["time_offset"] for k in k_b] == [0, 1 * S] and k_b[0]["values"] == [1.0]
          and abs(k_b[1]["values"][0] - (1 + 1 / 7)) < 1e-9, k_b)
    check("every keyframe sits inside its piece",
          all(0 <= k["time_offset"] <= s["target_timerange"]["duration"] for s in ov for k in s["common_keyframes"][0]["keyframe_list"]))

    import capcut_ripple
    m = copy.deepcopy(r)
    capcut_ripple.enforce_maintrack_ripple(m, main=cr.main_track(m))
    anchor = [t["id"] for t in m["tracks"] if t.get("is_default_name") is False]
    check("the magnet anchors her footage track, not the busiest overlay",
          anchor == ["t-main"] and not capcut_ripple.verify_maintrack_anchor(m, main=cr.main_track(m)), anchor)

    bed = segs(r, "t-bed")
    kv = bed[0]["common_keyframes"][0]["keyframe_list"]
    check("her music bed is laid fresh: one continuous play from where her song starts, under the whole re-cut",
          len(bed) == 1 and bed[0]["target_timerange"] == tr(0, 6) and bed[0]["source_timerange"] == tr(2, 6), bed)
    check("the bed keeps her volume shape and goes on the bottom track",
          [(k["time_offset"], k["values"]) for k in kv] == [(0, [0.3]), (6 * S, [0.2])] and r["tracks"][-1]["id"] == "t-bed", kv)
    check("a short sound effect is never taken for a bed", [t["id"] for t in cr.bed_tracks(d)] == ["t-bed"])

    txt = segs(r, "t-text")
    anims = [[a["type"] for a in pool[s["extra_material_refs"][0]][1]["animations"]] for s in txt]
    check("the out-animation stays on the piece holding the clip's end, the in-animation on its start",
          anims == [["out"], ["in"]], anims)
    sfx = segs(r, "t-sfx")
    fades = [(pool[s["extra_material_refs"][0]][1]["fade_in_duration"], pool[s["extra_material_refs"][0]][1]["fade_out_duration"]) for s in sfx]
    check("a sound cut at its start loses its fade-in and keeps its fade-out",
          len(sfx) == 1 and sfx[0]["target_timerange"] == tr(0, 1) and fades == [(0, 100000)], (sfx, fades))


def test_hook():
    d = synthetic()
    check("her own hook block is found (top of the frame, first second)", cr.hook_texts(d) == ["her old hook"], cr.hook_texts(d))
    w = copy.deepcopy(d)
    check("lifting it takes its segment, its track and its material", cr.strip_hook(w) == 1
          and "t-hook" not in [t["id"] for t in w["tracks"]] and "hook-1" not in cr._pool(w)
          and "text-1" in cr._pool(w))
    cap = tempfile.mkdtemp(prefix="recut-test-")
    old = draft_safety.CAP
    try:
        draft_safety.CAP = cap
        os.makedirs(os.path.join(cap, "Her Hook"))
        json.dump(d, open(draft_safety.draft_json(os.path.join(cap, "Her Hook")), "w", encoding="utf-8"))
        r = cr.recut(w, cr.pieces_from_lines(w, "3,1"), seed="trial")
        placed = cr.add_hook(r, ["the new words"], "Her Hook", None, seed="trial:hook", clear=False)["placed"]
        hooks = cr.hook_segments(r)
        check("the new hook goes in at the front, in her style, as long as hers held",
              placed == ["the new words"] and cr.hook_texts(r) == ["the new words"]
              and hooks[0][1]["target_timerange"] == tr(0, 3) and hooks[0][1]["clip"]["transform"]["y"] == 0.7, hooks)
        style = json.loads(cr._pool(r)[hooks[0][1]["material_id"]][1]["content"])["styles"][0]
        check("only the words change: her font and size carry over", style["font"]["path"] == "/fonts/Hook.ttf"
              and style["size"] == 12 and style["range"] == [0, len("the new words")], style)
        every = ids(r)
        check("ids stay unique with the hook added", len(every) == len(set(every)))
        r2 = cr.recut(w, cr.pieces_from_lines(w, "3,1"), seed="trial")
        r2["tracks"].append({"id": "t-card", "type": "text", "segments": [
            {"id": "card", "material_id": "text-1", "target_timerange": tr(0, 6),
             "clip": {"transform": {"x": 0, "y": 0.7}, "scale": {"x": 1, "y": 1}}}]})
        hk = cr.add_hook(r2, ["the new words"], "Her Hook", None, seed="t2:hook", low_zone={"top": 1000, "bottom": 1250},
                         when_covered="below")
        y = next(s for t in r2["tracks"] if t.get("name") == "hook" for s in t["segments"])["clip"]["transform"]["y"]
        check("a graphic in the hook's top spot: the hook moves under her chin for its full length (when_covered=below)",
              hk["spot"] == "below" and hk["start"] == 0 and hk["dur"] == 3 * S and abs(y - (960 - 1090) / 960) < 1e-3, (hk, y))
        hk = cr.add_hook(cr.recut(w, cr.pieces_from_lines(w, "3,1"), seed="trial"), ["x"], "Her Hook", None,
                         seed="t3:hook", low_zone={"top": 1000, "bottom": 1250}, when_covered="below")
        check("with its top spot clear, the hook stays on top", hk["spot"] == "top", hk)
        try:
            cr.add_hook(r, ["one", "two"], "Her Hook", None)
            check("more lines than her hook has is refused", False)
        except cr.Refuse:
            check("more lines than her hook has is refused", True)
    finally:
        draft_safety.CAP = old
        shutil.rmtree(cap, ignore_errors=True)


def test_music_and_hook_room():
    d = synthetic()
    r = cr.recut(d, cr.pieces_from_lines(d, "3,1"), seed="trial")
    # an older trial whose bed was cut with the clips: two jumping pieces, each its own copy of the song
    t = next(t for t in r["tracks"] if t["id"] == "t-bed")
    a, b = copy.deepcopy(t["segments"][0]), copy.deepcopy(t["segments"][0])
    a.update(id="j1", material_id="songA", target_timerange=tr(0, 4), source_timerange=tr(30, 4))
    b.update(id="j2", material_id="songB", target_timerange=tr(4, 2), source_timerange=tr(5, 2))
    t["segments"] = [a, b]
    r["materials"]["audios"] += [dict(id="songA", type="extract_music", path="/music/song.mp3", duration=60 * S),
                                 dict(id="songB", type="extract_music", path="/music/song.mp3", duration=60 * S)]
    check("a bed cut into jumping pieces is still found (one song, many copies)", cr.bed_tracks(r) == [t])
    name = cr.fresh_bed(r, d)
    beds = cr.bed_tracks(r)
    pool = cr._pool(r)
    check("rebed: the jumping bed comes off and her song goes back whole, on the bottom track",
          name == "song.mp3" and len(beds) == 1 and len(beds[0]["segments"]) == 1
          and beds[0]["segments"][0]["source_timerange"] == tr(2, 6) and r["tracks"][-1] is beds[0]
          and "songA" not in pool and "songB" not in pool, [s["source_timerange"] for x in beds for s in x["segments"]])
    check("rebed leaves no missing material and no repeated id",
          not [ref for _s, ref in all_refs(r) if ref not in pool] and len(ids(r)) == len(set(ids(r))))

    busy = [(int(2.17 * S), int(5.2 * S)), (int(7.5 * S), 10 * S)]
    check("the hook takes the clear stretch at the start and ends as a graphic comes in",
          cr.hook_window(busy, 8 * S, 30 * S) == (0, int(2.17 * S)))
    check("a graphic on screen as the reel opens plays first, the hook comes in as it ends",
          cr.hook_window([(0, 2 * S)], 8 * S, 30 * S) == (2 * S, 8 * S))
    check("no clear stretch = no room", cr.hook_window([(0, 29 * S)], 8 * S, 30 * S)[1] < cr.HOOK_MIN)
    card = {"id": "t-card", "type": "text", "segments": [
        {"id": "card", "material_id": "text-1", "target_timerange": tr(2, 2),
         "clip": {"transform": {"x": 0, "y": 0.65}, "scale": {"x": 1, "y": 1}}}]}
    d2 = synthetic()
    d2["tracks"].append(card)
    spans = cr.graphic_spans(d2, (200, 470), 9 * S, None, skip={"hook"})
    check("a card in the hook's spot counts as busy; her captions low in the frame don't",
          spans == [(2 * S, 4 * S)], spans)


def test_trial_plan():
    import trial_reels as t
    check("an open + drop plan becomes her clip runs",
          t._runs(t._recut_order(31, "18-20", ["13-17"])) == "18-20,1-12,21-31")
    check("a single clip and a tail", t._runs(t._recut_order(5, 4, [2])) == "4,1,3,5")
    for bad in (("40", None), ("3", ["3"])):
        try:
            t._recut_order(31, *bad)
            check(f"a bad plan {bad} is refused", False)
        except t.Refuse:
            check(f"a bad plan {bad} is refused", True)


def test_no_slivers():
    """you 2026-10-19: 'glitched moments where cuts were not perfect': a graphic running across a cut must not be
    left as a few frames on the other side. Clip 2 (2-5 s) then clip 3 (5-9 s) from 2.1 s: the overlay (1-8 s) is
    kept; a short card ending at 2.2 s would leave 0.1 s after the cut, so it is left out. Her footage never is."""
    d = synthetic()
    d["materials"]["videos"].append({"id": "vid-card", "type": "video"})
    d["tracks"].append({"id": "t-card", "type": "video", "segments": [
        {"id": "card", "material_id": "vid-card", "extra_material_refs": [],
         "target_timerange": tr(1.4, 0.8), "source_timerange": tr(0, 0.8), "speed": 1.0}]})
    r = cr.recut(d, [(int(2.1 * S), 9 * S)], seed="sliver")
    card = segs(r, "t-card")
    check("a graphic cut down to a sliver at the cut is left out", card == [], [s["target_timerange"] for s in card])
    check("her footage is never dropped", sum(s["target_timerange"]["duration"] for s in segs(r, "t-main")) == int(6.9 * S),
          [s["target_timerange"] for s in segs(r, "t-main")])


def main():
    test_recut()
    test_hook()
    test_music_and_hook_room()
    test_trial_plan()
    test_no_slivers()
    print("\nPASS" if not fails else f"\nFAIL ({len(fails)}): {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
