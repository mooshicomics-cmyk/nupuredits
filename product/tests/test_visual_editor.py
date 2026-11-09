#!/usr/bin/env python3
"""test_visual_editor.py — the style plan's visual editor can be trusted without anyone watching it.

Covered here:
  1. the page plays HER CUT IN ITS OWN ORDER: a line moved later in the cut plays where it sits, cut words show
     where she said them, every word appears exactly once; lines break at jumps
  2. apply: a word she cuts splits its piece at the right edges; a word she brings back becomes its own piece,
     no_trim (her call beats the double-take pass), butted against its neighbours' real edges, in the right
     place in the cut; choices are absolute (cutting a cut word or keeping a kept word changes nothing)
  3. refusals, each with a reason and nothing cut: the transcript changed, wrong reel, edits past the end,
     every word cut, a piece with no words under it, a piece from a clip that isn't in the transcript
  4. the paste fallback reads back exactly what the page wrote (ranges, spaces, "none"), and refuses junk
  5. the receipt: stable for the same edits, different for different ones; a hand-changed save is refused
  6. the server's save: only meaningful edits are kept, written atomically with a receipt; apply reads it once
     and sets it aside so a second "sent" can't apply it again
  7. the server itself: answers /ping, serves byte ranges, refuses a write from any other page (Host / Origin),
     refuses paths outside a reel's review/ folder
  8. two clips: the order and the pieces stay on the right clip

Run:  python3 product/tests/test_visual_editor.py
"""
import http.client, json, os, re, shutil, sys, tempfile, threading, time
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import visual_editor as ve  # noqa: E402


def _fake_sub(run):
    """A stand-in subprocess whose stitch answers through `run(cmd, **k)`: the stitch is started with Popen (so it can
    be timed out and logged), and this hands that start to the test's own run()."""
    import subprocess as _sp

    class _P:
        def __init__(self, cmd, **k):
            k = {key: v for key, v in k.items() if key not in ("stdout", "stderr", "stdin", "text", "encoding", "errors",
                                                             "start_new_session", "creationflags")}
            self.returncode, self.stdout, self.pid = run(cmd, **k).returncode, iter(()), 0

        def wait(self, timeout=None):
            return self.returncode

    return type("S", (), {"run": staticmethod(run), "Popen": _P, "PIPE": _sp.PIPE, "STDOUT": _sp.STDOUT,
                          "DEVNULL": _sp.DEVNULL, "TimeoutExpired": _sp.TimeoutExpired})

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-400:]) if detail else ''}")


def refuses(name, fn, *a, **k):
    try:
        fn(*a, **k)
    except ve.Refuse as e:
        check(name, bool(str(e).strip()), "empty reason")
        return str(e)
    check(name, False, "did not refuse")
    return ""


TMP = tempfile.mkdtemp(prefix="ve-test-")
SRV_JOB, LOOK_JOB = "srvjob", "lookjob"     # throwaway reels the server tests serve from TMP
tempfile.tempdir = TMP                       # apply's scratch plan lands here, never in the real scratch folder
ve.USER_STYLE = os.path.join(TMP, "user-style.json")   # her real default pack never decides a test reel's pack
QUIET = lambda *a, **k: None

# ten words, one every second: w0 at 0.0-0.6, w1 at 1.0-1.6, ...
WORDS = [{"word": f"w{i}" + ("." if i in (2, 6, 9) else ""), "start": i * 1.0, "end": i * 1.0 + 0.6} for i in range(10)]


def make_job(name, segs, clips=None):
    jd = os.path.join(TMP, name)
    os.makedirs(os.path.join(jd, "transcript"), exist_ok=True)
    clips = clips or [{"clip": "a.mov", "path": "", "duration": 10, "words": WORDS}]
    json.dump({"clips": clips}, open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    json.dump({"segments": segs}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    return jd


def seg(a, b, clip="a.mov", **kw):
    return {"clip": clip, "start": a, "end": b, "transcript": "", **kw}


# the engine's cut: w0-w2, w5-w6, w8-w9, then w3 MOVED to the end; w4 and w7 cut
SEGS = [seg(-0.04, 2.64, keep_edges=True), seg(4.96, 6.64), seg(7.96, 9.64), seg(2.96, 3.64)]


def model(jd):
    _, clips, segs, wid, cid = ve.load(jd)
    words = ve.kept_quiet(ve.words_of(clips), clips, segs)
    seg_of = ve.membership(words, clips, segs)
    order, moved = ve.display_order(words, segs, seg_of)
    return words, segs, seg_of, order, moved, wid


def test_order():
    jd = make_job("order", SEGS)
    words, segs, seg_of, order, moved, _ = model(jd)
    check("order: the cut's order, moved line last", order == [0, 1, 2, 4, 5, 6, 7, 8, 9, 3], order)
    check("order: the moved piece is marked", moved == {3}, moved)
    check("order: every word once", sorted(order) == list(range(10)))
    check("membership: cut words belong to no piece", seg_of[4] is None and seg_of[7] is None, seg_of)
    lines = ve.lines_of(words, order, seg_of, moved)
    check("lines: the moved word is a line of its own", lines[-1] == [3], lines)
    check("lines: sentence ends break lines", [0, 1, 2] in lines, lines)
    # a cold open: the last piece placed first
    jd2 = make_job("coldopen", [seg(7.96, 9.64), seg(-0.04, 2.64), seg(4.96, 6.64)])
    _, _, _, order2, moved2, _ = model(jd2)
    check("cold open: plays first, rest follows in footage order", order2[:2] == [8, 9] and order2[2:5] == [0, 1, 2], order2)
    check("cold open: only the opener is marked moved", moved2 == {0}, moved2)
    check("cold open: every word once", sorted(order2) == list(range(10)))


def test_apply():
    jd = make_job("apply", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    _, _, _, _, _, wid = model(jd)
    base = {"job": "apply", "id": wid}
    out = ve.apply_edits(jd, {**base, "cut": [1], "back": []}, stitch=False, log=QUIET)
    check("cut: the piece splits in two", len(out) == 5, out)
    a, b = out[0], out[1]
    check("cut: first piece keeps its start, ends just after w0", a["start"] == -0.04 and abs(a["end"] - 0.64) < 1e-6, a)
    check("cut: second piece starts just before w2, keeps its end", abs(b["start"] - 1.96) < 1e-6 and b["end"] == 2.64, b)
    check("cut: split pieces lose keep_edges", "keep_edges" not in a and "keep_edges" not in b, (a, b))
    check("cut: transcripts follow the words", a["transcript"] == "w0" and b["transcript"] == "w2.", (a, b))
    check("look-only: the live scratch plan is never touched", not os.path.exists(os.path.join(TMP, "reels-editing-engine", "apply", "cuts.json")))
    check("look-only: the plan is written beside the page instead",
          json.load(open(os.path.join(jd, "review", "cut-plan-preview.json"), encoding="utf-8"))["segments"] == out)

    out = ve.apply_edits(jd, {**base, "cut": [], "back": [4]}, stitch=False, log=QUIET)
    check("back: one new piece", len(out) == 5, out)
    p = out[1]
    check("back: placed right after the piece before it", p["transcript"] == "w4", out)
    check("back: marked no_trim (her call wins)", p.get("no_trim") is True, p)
    check("back: never overlaps its neighbours", p["start"] >= out[0]["end"] and p["end"] <= out[2]["start"], out)
    check("back: the moved piece stays last", out[-1]["start"] == 2.96, out)

    out = ve.apply_edits(jd, {**base, "cut": [], "back": [7]}, stitch=False, log=QUIET)
    check("back w7: lands between w5-w6 and w8-w9", [s["transcript"] for s in out].index("w7") == 2, out)

    out = ve.apply_edits(jd, {**base, "cut": [4, 7], "back": [0, 5]}, stitch=False, log=QUIET)
    check("absolute: cutting cut words / keeping kept words changes nothing",
          [(s["start"], s["end"]) for s in out] == [(s["start"], s["end"]) for s in SEGS], out)

    out = ve.apply_edits(jd, {**base, "cut": [0, 1, 2], "back": []}, stitch=False, log=QUIET)
    check("cut a whole piece: it goes", len(out) == 3 and out[0]["start"] == 4.96, out)

    refuses("refuse: transcript changed", ve.apply_edits, jd, {"job": "apply", "id": "zzzzzz", "cut": [1], "back": []}, stitch=False, log=QUIET)
    refuses("refuse: another reel's edits", ve.apply_edits, jd, {"job": "other", "id": wid, "cut": [1], "back": []}, stitch=False, log=QUIET)
    refuses("refuse: edits past the end", ve.apply_edits, jd, {**base, "cut": [99], "back": []}, stitch=False, log=QUIET)
    refuses("refuse: every word cut", ve.apply_edits, jd, {**base, "cut": list(range(10)), "back": []}, stitch=False, log=QUIET)


def test_touching_words():
    tight = [{"word": "here", "start": 0.925, "end": 1.145}, {"word": "we", "start": 1.165, "end": 1.385},
             {"word": "go.", "start": 1.405, "end": 1.465}, {"word": "last", "start": 2.046, "end": 2.286},
             {"word": "week", "start": 2.346, "end": 2.566}]
    jd = make_job("touching", [seg(2.0, 2.6)], clips=[{"clip": "a.mov", "words": tight}])
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    wid = model(jd)[5]
    out = ve.apply_edits(jd, {"job": "touching", "id": wid, "cut": [], "back": [0]}, stitch=False, log=QUIET)
    check("touching: a restored word never reaches into the next word", out[0]["end"] <= 1.155 + 1e-9, out[0])
    check("touching: but keeps its full pad where there is room", abs(out[0]["start"] - 0.885) < 1e-9, out[0])
    jd2 = make_job("touching2", [seg(0.885, 1.505)], clips=[{"clip": "a.mov", "words": tight}])
    os.makedirs(os.path.join(jd2, "review"), exist_ok=True)
    out = ve.apply_edits(jd2, {"job": "touching2", "id": model(jd2)[5], "cut": [1], "back": []}, stitch=False, log=QUIET)
    check("touching: cutting a word keeps none of it on either side",
          out[0]["end"] <= 1.155 + 1e-9 and out[1]["start"] >= 1.395 - 1e-9, out)


def test_kept_quiet():
    # a quiet stretch she kept with a click (a pause held on purpose): hers, never refused. It shows as quiet beats
    # after every word (no word's number moves), plays where it sits in the cut, and survives her next Send exactly.
    jd = make_job("silent", SEGS[:3] + [seg(9.7, 12.2, keep_edges=True)] + SEGS[3:])
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    words, segs, seg_of, order, moved, wid = model(jd)
    beats = [i for i, w in enumerate(words) if w.get("q")]
    check("quiet: kept beats sit after every word", beats and beats[0] == 10 and words[9]["t"] == "w9.", beats)
    check("quiet: beats cover the piece, about a second each",
          words[beats[0]]["s"] == 9.7 and words[beats[-1]]["e"] == 12.2 and all(seg_of[i] == 3 for i in beats), [words[i] for i in beats])
    check("quiet: it plays where it sits in the cut", order.index(beats[0]) == order.index(9) + 1, order)
    check("quiet: it is its own line", any(l == beats for l in ve.lines_of(words, order, seg_of, moved)))
    out = ve.apply_edits(jd, {"job": "silent", "id": wid, "cut": [], "back": []}, stitch=False, log=QUIET)
    q = [p for p in out if abs(float(p["start"]) - 9.7) < 1e-6]
    check("quiet: a Send keeps it exactly as she set it", q and abs(float(q[0]["end"]) - 12.2) < 1e-6 and q[0].get("keep_edges"), out)
    check("quiet: the word beside it keeps its pad", abs(float(out[2]["end"]) - 9.64) < 1e-6, out)


def test_touching_pieces():
    # two pieces of one clip that touch or overlap (a word she brought back beside a line she said twice): the later
    # piece's word sits in the earlier piece's edge, so the earlier one holds it. The later piece is still hers: quiet
    # beats, never "Piece 2 of the cut has no words under it" (2026-10-17, her bring-back of "Margarita." refused)
    jd = make_job("touching-pieces", [seg(-0.04, 2.64), seg(1.96, 2.62), seg(4.96, 6.64)])
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    try:
        words, segs, seg_of, order, moved, wid = model(jd)
    except ve.Refuse as e:
        check("touching pieces: never refused", False, e)
        return
    check("touching pieces: every piece holds something", all(k in seg_of for k in range(3)), seg_of)
    check("touching pieces: the word keeps its number and its first piece", seg_of[2] == 0 and words[2]["t"] == "w2.", seg_of)
    beats = [i for i, w in enumerate(words) if w.get("q")]
    check("touching pieces: the later piece shows as quiet beats after every word", beats and beats[0] == 10
          and all(seg_of[i] == 1 for i in beats), [words[i] for i in beats])
    check("touching pieces: every word once", sorted(order) == list(range(len(words))), order)
    out = ve.apply_edits(jd, {"job": "touching-pieces", "id": wid, "cut": [], "back": [4]}, stitch=False, log=QUIET)
    check("touching pieces: a Send with a word brought back goes through", len(out) >= 3, out)


def test_long_stamp():
    # a word stamped over a pause ("internet." held 5 s) belongs to the piece that plays it, read at its real length
    long = [dict(w) for w in WORDS]
    long[2] = {"word": "w2.", "start": 2.0, "end": 7.3}          # a sentence end stretched over the quiet after it
    jd = make_job("longstamp", [seg(-0.04, 2.64)], clips=[{"clip": "a.mov", "path": "", "duration": 10, "words": long}])
    words, segs, seg_of, order, moved, _ = model(jd)
    check("long stamp: the stretched word is in the piece that plays it", seg_of[2] == 0, seg_of[:4])
    check("long stamp: read at its real length", words[2]["e"] - words[2]["s"] <= 0.6 + 1e-9, words[2])


def test_refusals():
    refuses("refuse: a piece from a clip not in the transcript", model, make_job("broll", SEGS + [seg(0, 2, clip="b-roll.mov")]))
    refuses("refuse: no rough cut yet", ve.load, make_job("nocut", SEGS) and os.remove(os.path.join(TMP, "nocut", "transcript", "cuts.json")) or os.path.join(TMP, "nocut"))


def test_code():
    p = ve.parse_code("STYLE PLAN EDITS · my-reel · v1a2b3c · 1:22\ncut: 3, 10-12, 40\nkeep: none\n")
    check("code: reads job + id", p["job"] == "my-reel" and p["id"] == "1a2b3c", p)
    check("code: reads ranges", p["cut"] == [3, 10, 11, 12, 40] and p["back"] == [], p)
    p = ve.parse_code("  style plan edits · my-reel · v1a2b3c · 1:22\n\nCUT:none\nKeep:  7-8 ")
    check("code: tolerant of case and spacing", p["cut"] == [] and p["back"] == [7, 8], p)
    refuses("code: junk is refused", ve.parse_code, "please cut line 4")
    a = ve.receipt({"job": "r", "id": "x", "cut": [1, 2], "back": []})
    check("receipt: stable", a == ve.receipt({"job": "r", "id": "x", "cut": [1, 2], "back": [], "length": "1:00"}))
    check("receipt: changes with the edits", a != ve.receipt({"job": "r", "id": "x", "cut": [1], "back": []}))


def test_speed_zoom():
    """A clip's Speed and Zoom move from her page: set on the piece holding the word the page sends, kept through
    every later Send (and through her cuts and trims in that clip), taken off by Normal / No zoom, checked on save,
    shown back to the page, read from the paste code, and counted at the length the clip PLAYS."""
    jd = make_job("fx", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    _, _, _, _, _, wid = model(jd)
    base = {"job": "fx", "id": wid, "cut": [], "back": []}
    zin = {"from": 1.15, "to": 1.0}
    out = ve.apply_edits(jd, {**base, "fx": {"1": {"speed": 2, "zoom": zin}}}, stitch=False, log=QUIET)
    check("fx: the clip holding word 1 gets its speed and zoom", out[0].get("speed") == 2.0 and out[0].get("zoom") == zin, out[0])
    check("fx: no other clip does", not any(p.get("speed") or p.get("zoom") for p in out[1:]), out)
    json.dump({"segments": out}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    _, _, _, _, _, wid = model(jd); base["id"] = wid
    out2 = ve.apply_edits(jd, {**base, "cut": [1]}, stitch=False, log=QUIET)
    check("fx: a later Send that cuts a word in that clip keeps both on each piece",
          [p.get("speed") for p in out2[:2]] == [2.0, 2.0] and all(p.get("zoom") == zin for p in out2[:2]), out2[:3])
    out3 = ve.apply_edits(jd, {**base, "trims": {"s": {}, "e": {"2": 2.8}}}, stitch=False, log=QUIET)
    check("fx: a trimmed edge keeps them too", out3[0].get("speed") == 2.0 and out3[0].get("zoom") == zin, out3[0])
    out4 = ve.apply_edits(jd, {**base, "holes": [{"c": 0, "s": 1.7, "e": 1.9}]}, stitch=False, log=QUIET)
    check("fx: a cut by time inside it leaves both halves sped and zoomed",
          [p.get("speed") for p in out4[:2]] == [2.0, 2.0] and out4[1].get("zoom") == zin, out4[:2])
    out5 = ve.apply_edits(jd, {**base, "fx": {"0": {"speed": 1, "zoom": None}}}, stitch=False, log=QUIET)
    check("fx: Normal and No zoom take them off", "speed" not in out5[0] and "zoom" not in out5[0], out5[0])
    stale = dict(out[0], played=9.9)
    json.dump({"segments": [stale] + out[1:]}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    _, _, _, _, _, wid = model(jd); base["id"] = wid
    out6 = ve.apply_edits(jd, base, stitch=False, log=QUIET)
    check("fx: an old played length never rides along (the stitch measures it again)", "played" not in out6[0], out6[0])
    check("fx: only numbers in range get through",
          ve.fx_of({"fx": {"3": {"speed": 50}, "4": {"zoom": {"from": 0.2, "to": 1}}, "x": {"speed": 2}, "5": {"speed": 1.5}}}) == {5: {"speed": 1.5}})
    check("fx: a zoom from 1 to 1 is no zoom", ve.fx_of({"fx": {"2": {"zoom": {"from": 1, "to": 1}}}}) == {2: {"zoom": None}})
    check("fx: the receipt changes with them", ve.receipt({**base, "fx": {"1": {"speed": 2}}}) != ve.receipt(base))
    code = ve.parse_code("STYLE PLAN EDITS · fx · v" + wid[:6] + " · 0:07\ncut: none\nkeep: none\nfx: 1 x2 z1.15-1, 5 x1 znone")
    check("fx: the paste code reads them back", code.get("fx") == {"1": {"speed": 2.0, "zoom": zin}, "5": {"speed": 1.0, "zoom": None}}, code)
    import visual_editor_server as srv
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "fx", "id": wid, "cut_id": "c", "words": [{"k": True}] * 10, "clips": [{}]})
    srv.save(jd, {"job": "fx", "id": wid, "cut": [], "back": [], "fx": {"1": {"speed": 2, "zoom": zin}, "99": {"speed": 2}}})
    saved = json.load(open(os.path.join(jd, "transcript", "script-review.json"), encoding="utf-8"))
    check("fx: the server's save keeps them, checked, and only for this reel's words", saved.get("fx") == {"1": {"speed": 2.0, "zoom": zin}}, saved)
    os.remove(os.path.join(jd, "transcript", "script-review.json"))
    json.dump({"segments": out}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    json.dump({"reading": {"source": {"w": 1000, "h": 2000}}, "subject_src_px": {"left": 400, "right": 600, "head_top": 400, "chin_bottom": 800}},
              open(os.path.join(jd, "subject-zones.json"), "w", encoding="utf-8"))
    os.makedirs(os.path.join(jd, "raw"), exist_ok=True); open(os.path.join(jd, "raw", "a.mov"), "wb").close()
    keep = (ve._duration, ve._canvas, ve.looks_manifest, ve.timeline_assets)
    ve._duration, ve._canvas, ve.looks_manifest, ve.timeline_assets = (lambda p: 10.0), (lambda p: (1080, 1920)), (lambda jd: None), (lambda jd, d: None)
    try:
        data = ve.build_script(jd)
    finally:
        ve._duration, ve._canvas, ve.looks_manifest, ve.timeline_assets = keep
    check("fx: the page is told each clip's speed and zoom", data["segs"][0].get("sp") == 2.0 and data["segs"][0].get("z") == dict(zin, ease="inOut")
          and "sp" not in data["segs"][1], data["segs"][:2])
    check("fx: and where a zoom holds still (her face)", data.get("focus") == {"x": 0.5, "y": 0.3}, data.get("focus"))
    ramp = {"from": 2.6, "to": 1.4, "ease": "out"}
    check("fx: a speed ramp gets through, and a flat one is just a speed",
          ve.fx_of({"fx": {"1": {"speed": ramp}, "2": {"speed": {"from": 2, "to": 2}}}}) == {1: {"speed": ramp}, 2: {"speed": 2.0}})
    outr = ve.apply_edits(jd, {**base, "fx": {"1": {"speed": ramp, "zoom": {"from": 1.3, "to": 1.0, "ease": "out"}}}}, stitch=False, log=QUIET)
    check("fx: a ramp is one clip: its shape kept, its average as the speed (2.6 + (1.4 - 2.6) x 2/3 = 1.8)",
          outr[0].get("ramp") == ramp and abs(outr[0].get("speed", 0) - 1.8) < 1e-6 and outr[0].get("zoom") == {"from": 1.3, "to": 1.0, "ease": "out"}, outr[0])
    outr2 = ve.apply_edits(jd, {**base, "fx": {"1": {"speed": 1.5}}}, stitch=False, log=QUIET)
    check("fx: a plain speed after a ramp drops the ramp", outr2[0].get("speed") == 1.5 and "ramp" not in outr2[0], outr2[0])
    from cut_placement import played_length
    check("fx: a sped clip counts at the length it plays", abs(played_length({"start": 0, "end": 2, "speed": 2}) - 1.0) < 1e-9
          and played_length({"start": 0, "end": 2, "speed": 2, "played": 1.001}) == 1.001)


def test_lock_kept_for_her():
    """A change Claude makes to her cut FOR her (restitch after her notes, clip-fx for a Speed or Zoom she asked for)
    keeps her lock-in, stamped with the new cut; only her own Send reopens phase 1. Runs after test_save_and_apply,
    with its stand-ins for the stitch and the script."""
    jd = make_job("lockkept", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    _, _, _, _, _, wid = model(jd)
    ph = os.path.join(jd, "review", "phase.json")
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "lockkept", "id": wid, "cut_id": "newcut", "words": []})
    ve._atomic_json(ph, {"phase": "looks", "cut_locked_at": "then", "cut_id": "oldcut"})
    ve.restitch(jd, log=QUIET)
    d = json.load(open(ph, encoding="utf-8")) if os.path.exists(ph) else {}
    check("lock kept: a restitch for her notes keeps her cut locked in, on the new cut",
          d.get("phase") == "looks" and d.get("cut_id") == "newcut" and d.get("cut_locked_at") == "then", d)
    ve._atomic_json(ph, {"phase": "looks", "cut_id": "oldcut"})
    ve.clip_fx(jd, 1, speed=2, zoom="out", log=QUIET)
    plan = json.load(open(os.path.join(TMP, "reels-editing-engine", "lockkept", "cuts.json"), encoding="utf-8"))["segments"]
    d = json.load(open(ph, encoding="utf-8")) if os.path.exists(ph) else {}
    check("clip-fx: clip 1 gets the speed and the zoom-out, through the page's own road",
          plan[0].get("speed") == 2.0 and plan[0].get("zoom") == {"from": 1.15, "to": 1.0} and "speed" not in plan[1], plan[:2])
    check("clip-fx: and her lock-in stays", d.get("phase") == "looks" and d.get("cut_id") == "newcut", d)
    refuses("clip-fx: a clip that isn't there is refused", ve.clip_fx, jd, 9, speed=2, log=QUIET)
    os.remove(ph)
    ve.restitch(jd, log=QUIET)
    check("lock kept: a cut that was never locked stays unlocked", not os.path.exists(ph))
    import visual_editor_server as srv
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "lockkept", "id": wid, "cut_id": "newcut", "words": [{"k": True}] * 10, "clips": [{}]})
    ve._atomic_json(ph, {"phase": "looks", "cut_id": "newcut"})
    srv.save(jd, {"job": "lockkept", "id": wid, "cut": [1], "back": []})
    check("her own Send still reopens her cut", not os.path.exists(ph))


def test_lines_keep_lock():
    """Splitting or combining her script lines (Cut or Visuals) never changes her cut and never unlocks it or her looks."""
    jd = make_job("lineslock", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    words, segs, seg_of, order, moved, wid = model(jd)
    lines = ve.lines_of(words, order, seg_of, moved)
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "lineslock", "id": wid, "cut_id": "c1", "lines": lines, "words": []})
    ve._atomic_json(os.path.join(jd, "review", "looks.json"), {"layers": []})
    ph = os.path.join(jd, "review", "phase.json")
    ve._atomic_json(ph, {"phase": "render", "cut_id": "c1"})
    cuts = open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8").read()
    keep = (ve.looks_manifest, ve.timeline_assets)
    ve.looks_manifest, ve.timeline_assets = (lambda jd: None), (lambda jd, d: None)
    try:
        r = ve.edit_lines(jd, "split", lines[0][1])
        after = json.load(open(ph, encoding="utf-8"))
        check("lines: a split regroups her lines", len(r["lines"]) == len(lines) + 1, r["lines"])
        check("lines: and keeps her looks locked in (and her cut)", after == {"phase": "render", "cut_id": "c1"}, after)
        ve.restore_lines(jd, r["undo"])
        check("lines: its Undo keeps the lock too", json.load(open(ph, encoding="utf-8")) == {"phase": "render", "cut_id": "c1"})
        check("lines: her cut is never touched", open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8").read() == cuts)
    finally:
        ve.looks_manifest, ve.timeline_assets = keep


def test_lines_before_looks():
    """Splitting or combining a line while she is still on her cut (no looks.json yet) just regroups her lines."""
    jd = make_job("linesfresh", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    words, segs, seg_of, order, moved, wid = model(jd)
    lines = ve.lines_of(words, order, seg_of, moved)
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "linesfresh", "id": wid, "cut_id": "c1", "lines": lines, "words": []})
    keep = (ve.looks_manifest, ve.timeline_assets)
    ve.looks_manifest, ve.timeline_assets = (lambda jd: None), (lambda jd, d: None)
    try:
        r = ve.edit_lines(jd, "split", lines[0][1])
        check("lines on a fresh cut: a split works before any look exists", len(r["lines"]) == len(lines) + 1, r["lines"])
    finally:
        ve.looks_manifest, ve.timeline_assets = keep


def test_pack_on_fresh_reel():
    """Switching the whole reel to another pack on a reel with nothing drawn yet (a b-roll reel, no hook: no looks.json)
    switches it and says nothing was redrawn, instead of crashing on the missing file (a tester's store-run reel)."""
    import stylepack
    jd = make_job("packfresh", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    words, segs, seg_of, order, moved, wid = model(jd)
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "packfresh", "id": wid, "cut_id": "c1",
                                                                "lines": ve.lines_of(words, order, seg_of, moved), "words": []})
    pk = stylepack.names()[0]
    try:
        r = ve.set_pack(jd, pk)
        ok = r.get("pack") == pk and r.get("redrawn") == [] and r.get("kept") == []
    except Exception as e:
        ok, r = False, repr(e)
    check("pack on a fresh reel: switches, nothing to redraw, no crash", ok, r)
    check("pack on a fresh reel: the reel remembers its pack", ve._reel_pack(jd) == pk)


def test_task_queue():
    """Her page's task queue: each thing she sent Claude moves Sent -> Has it (claimed) -> Working (a Sandbox idea Claude
    started) -> Done (resolve, sketches landing, look-request done), one round at a time; resolve never says "Fixed:" twice."""
    jd = make_job("queue", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    ve._atomic_json(os.path.join(jd, "transcript", "script-notes.json"), {"notes": [
        {"id": "n1", "w": 1, "text": "speed up this clip", "status": "open", "at": now},
        {"id": "n2", "w": 5, "text": "[Look: Takeover] smaller please", "status": "open", "at": now}]})
    ve._atomic_json(os.path.join(jd, "review", "look-requests.json"), {"requests": [
        {"id": "ab12cd", "w": 0, "idea": "For the line \"w0\": a sticky note slaps on", "status": "open", "mode": "sandbox", "round": 1, "at": now}]})
    ve._atomic_json(os.path.join(jd, "review", "looks-manifest-stub.json"), {})
    lm = ve.looks_manifest; ve.looks_manifest = lambda jd: None
    try:
        q = ve.task_queue(jd)
        st = {x["id"]: x["state"] for x in q["items"]}
        check("queue: everything she sent is listed, waiting", st == {"n1": "sent", "n2": "sent", "ab12cd": "sent"} and q["done"] == 0 and q["total"] == 3, q)
        lab = {x["id"]: x["label"] for x in q["items"]}
        check("queue: each row has a short label of its own", lab["n1"] == "speed up this clip" and lab["n2"] == "smaller please"
              and lab["ab12cd"] == "Sandbox: a sticky note slaps on", lab)
        ve.claim(jd, [{"id": "n1"}, {"id": "ab12cd"}])
        st = {x["id"]: x["state"] for x in ve.task_queue(jd)["items"]}
        check("queue: what Claude took says Claude has it", st["n1"] == "has" and st["ab12cd"] == "has" and st["n2"] == "sent", st)
        ve.sandbox_working(jd, "ab12cd")
        check("queue: a Sandbox idea Claude started says Working", {x["id"]: x["state"] for x in ve.task_queue(jd)["items"]}["ab12cd"] == "working")
        ve.resolve(jd, "n1", "Fixed: Fixed: it plays twice as fast now")
        n1 = json.load(open(os.path.join(jd, "transcript", "script-notes.json"), encoding="utf-8"))["notes"][0]
        check("resolve: the reply never carries its own Fixed: (the page adds one)", n1["reply"] == "it plays twice as fast now" and n1.get("done_at"), n1)
        q = ve.task_queue(jd)
        check("queue: a resolved note is Done and counts toward the round", {x["id"]: x["state"] for x in q["items"]}["n1"] == "done" and q["done"] == 1 and q["total"] == 3, q)
        reqs = ve._requests(jd); reqs[0].update(status="takes", done_at=now); reqs[0].pop("working", None)
        ve._atomic_json(ve._requests_path(jd), {"requests": reqs})
        ve.resolve(jd, "n2", "Done. Smaller.")
        q = ve.task_queue(jd)
        check("queue: sketches landed + every note resolved = the whole round done", q["done"] == q["total"] == 3, q)
        check("queue: a note's steps are Sent, Has it, Done; an idea's add Working",
              {x["id"]: x["steps"] for x in q["items"]} == {"n1": ["sent", "has", "done"], "n2": ["sent", "has", "done"], "ab12cd": ["sent", "has", "working", "done"]})
        old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 600))
        d = json.load(open(os.path.join(jd, "transcript", "script-notes.json"), encoding="utf-8"))
        for n in d["notes"]:
            n["at"] = n["done_at"] = old
        ve._atomic_json(os.path.join(jd, "transcript", "script-notes.json"), d)
        reqs = ve._requests(jd); reqs[0].update(at=old, done_at=old); ve._atomic_json(ve._requests_path(jd), {"requests": reqs})
        check("queue: a finished round goes away on its own", ve.task_queue(jd)["total"] == 0)
        ve.sandbox_remix(jd, "ab12cd", "make it bigger")
        q = ve.task_queue(jd)
        check("queue: a remix is a new round of its own", q["total"] == 1 and q["items"][0]["label"].startswith("Sandbox remix 1") and q["items"][0]["state"] in ("sent", "has"), q)
    finally:
        ve.looks_manifest = lm


def test_no_refusals():
    """Her choices are done, never refused (you: refusing her choices makes it harder): a line edit that's already that
    way is a quiet no-op, Export locks in what wasn't and says open notes in one line, Lock in my looks locks her cut
    too, stepping back to where she is changes nothing, Keep on a look with nothing refined keeps it as it is."""
    import visual_editor_server as srv
    jd = make_job("norefuse", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    words, segs, seg_of, order, moved, wid = model(jd)
    lines = ve.lines_of(words, order, seg_of, moved)
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"job": "norefuse", "id": wid, "cut_id": "c1", "lines": lines, "words": [{"k": True}] * 10, "clips": [{}]})
    ve._atomic_json(os.path.join(jd, "review", "looks.json"), {"layers": []})
    keep = (ve.looks_manifest, ve.timeline_assets, srv.run_in_background)
    ve.looks_manifest, ve.timeline_assets = (lambda jd: None), (lambda jd, d: None)
    started = []
    srv.run_in_background = lambda job, kind, fn, **k: started.append(kind)
    try:
        r = ve.edit_lines(jd, "split", lines[0][0])
        check("no refusal: splitting where a line already starts changes nothing, quietly", r["lines"] == lines and r["undo"] is None, r)
        r = ve.edit_lines(jd, "join", lines[-1][-1])
        check("no refusal: combining the last line with nothing below changes nothing, quietly", r["lines"] == lines and r["undo"] is None)
        ph = os.path.join(jd, "review", "phase.json")
        ve._atomic_json(os.path.join(jd, "transcript", "script-notes.json"), {"notes": [{"id": "n1", "w": 1, "text": "x", "status": "open"}]})
        out = srv.start_finish(jd, {"route": "mp4"})
        phd = json.load(open(ph, encoding="utf-8"))
        check("no refusal: Export with her cut not locked in locks it in and exports", out.get("started") and started == ["finish"]
              and phd.get("phase") == "render", (out, phd))
        check("no refusal: an open note is said in one line, never a stop", "open note" in (out.get("said") or ""), out)
        try:
            srv.back_to(jd, {"id": wid, "to": "looks"}); srv.back_to(jd, {"id": wid, "to": "looks"}); ok = True
        except ve.Refuse:
            ok = False
        check("no refusal: stepping back to where she already is changes nothing", ok)
        rk = ve.refine_apply(jd, "add-w1", "line")
        check("no refusal: Keep with nothing refined keeps the look as it is", rk.get("unchanged") is True, rk)
    finally:
        ve.looks_manifest, ve.timeline_assets, srv.run_in_background = keep


def test_save_and_apply():
    import visual_editor_server as srv
    jd = make_job("saveflow", SEGS)
    words, segs, seg_of, order, moved, wid = model(jd)
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    ve._atomic_json(os.path.join(jd, "review", "script.json"),
                    {"job": "saveflow", "id": wid, "cut_id": "c", "words": [{"k": s is not None} for s in seg_of]})
    out = srv.save(jd, {"job": "saveflow", "id": wid, "cut": [1, 4], "back": [4, 0, 7], "length": "0:07"})
    saved = json.load(open(os.path.join(jd, "transcript", "script-review.json"), encoding="utf-8"))
    check("save: only meaningful edits kept", saved["cut"] == [1] and saved["back"] == [4, 7], saved)
    check("save: receipt matches the edits", out["receipt"] == ve.receipt(saved) == saved["receipt"], (out, saved))
    refuses("save: stale page refused", srv.save, jd, {"job": "saveflow", "id": "old", "cut": [], "back": []})
    refuses("save: wrong reel refused", srv.save, jd, {"job": "other", "id": wid, "cut": [], "back": []})
    ve.apply(jd, stitch=False, log=QUIET)
    check("apply (look only): the sent edits stay put", os.path.exists(os.path.join(jd, "transcript", "script-review.json")))
    ve.subprocess = _fake_sub(lambda *a, **k: type("R", (), {"returncode": 0})())
    ve.build_script = lambda job: None
    ve.apply(jd, stitch=True, log=QUIET)
    check("apply: the plan is written where the stitch reads it",
          os.path.exists(os.path.join(TMP, "reels-editing-engine", "saveflow", "cuts.json")))
    check("apply: the save is set aside after use", not os.path.exists(os.path.join(jd, "transcript", "script-review.json"))
          and os.path.exists(os.path.join(jd, "review", "applied", saved["receipt"] + ".json")))
    refuses("apply: a second 'sent' with nothing new is refused", ve.apply, jd, stitch=False, log=QUIET)
    srv.save(jd, {"job": "saveflow", "id": wid, "cut": [1], "back": [], "length": "0:07"})
    p = os.path.join(jd, "transcript", "script-review.json")
    d = json.load(open(p, encoding="utf-8")); d["cut"] = [2]; json.dump(d, open(p, "w", encoding="utf-8"))
    refuses("apply: a hand-changed save is refused", ve.apply, jd, stitch=False, log=QUIET)


def test_lean():
    jd = make_job("lean", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    wid = model(jd)[5]
    seen = []
    class R:  # a stand-in stitch that records how it was asked to run, and whether the page was told
        returncode = 0
    def run(cmd, **k):
        f = os.path.join(jd, "review", ".applying")
        seen.append((k.get("env", {}).get("FLAT_RENDER"), json.load(open(f, encoding="utf-8"))["kind"] if os.path.exists(f) else None))
        return R()
    real_sub, real_build = ve.subprocess, ve.build_script
    ve.subprocess = _fake_sub(run); ve.build_script = lambda job: None
    try:
        ve.apply(jd, code=f"STYLE PLAN EDITS · lean · v{wid[:6]} · 0:07\ncut: 1\nkeep: none", log=QUIET)
        check("lean: 'sent' runs the stitch WITHOUT the video encode", seen[-1][0] == "0", seen)
        check("lean: the page is told it's a quick update", seen[-1][1] == "lean", seen)
        check("lean: the note clears when it's done", not os.path.exists(os.path.join(jd, "review", ".applying")))
        ve.base_is_stale = (lambda real: (lambda job: False))(ve.base_is_stale)
        ve.finish_cut(jd, log=QUIET)
        check("finish-cut: ONE full stitch, with the video", seen[-1][0] == "1", seen)
        check("finish-cut: the page is told it's the full-quality one", seen[-1][1] == "full", seen)
        def boom(cmd, **k):
            return type("R", (), {"returncode": 2})()
        ve.subprocess = _fake_sub(boom)
        refuses("a failed stitch says so, and nothing is lost", ve.apply, jd, code=f"STYLE PLAN EDITS · lean · v{wid[:6]}\ncut: 2", log=QUIET)
        check("a failed stitch still clears the page's note", not os.path.exists(os.path.join(jd, "review", ".applying")))
    finally:
        ve.subprocess, ve.build_script = real_sub, real_build
        import importlib; importlib.reload(ve)
        ve.USER_STYLE = os.path.join(TMP, "user-style.json")   # the reload put her real default pack back


def test_stale_base():
    jd = make_job("stale", SEGS)
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    planned = sum(x["end"] - x["start"] for x in SEGS)
    check("stale: no rough-cut video at all counts as behind", ve.base_is_stale(jd) is True)
    open(os.path.join(jd, "outputs", "stale.mp4"), "wb").write(b"x")
    real = ve._duration
    try:
        ve._duration = lambda p: planned + 0.013
        check("stale: a full stitch (a few ms off) matches", ve.base_is_stale(jd) is False)
        ve._duration = lambda p: planned + 0.6
        check("stale: after a lean edit the old video is behind", ve.base_is_stale(jd) is True)
    finally:
        ve._duration = real


def test_server():
    import visual_editor_server as srv
    proj = os.path.join(TMP, "projects"); os.makedirs(os.path.join(proj, "srvjob", "review"), exist_ok=True)
    open(os.path.join(proj, "srvjob", "review", "preview.mp4"), "wb").write(bytes(range(256)) * 4)
    open(os.path.join(proj, "secret.txt"), "w", encoding="utf-8").write("private")
    srv.PROJECTS = proj
    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def req(method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        h = {"Host": f"127.0.0.1:{port}", **(headers or {})}
        c.request(method, path, body=body, headers=h)
        r = c.getresponse(); data = r.read(); c.close()
        return r.status, data

    check("server: ping", req("GET", "/ping")[0] == 200)
    check("server: reads from any other address are refused", req("GET", "/ping", {"Host": "evil.example:80"})[0] == 403)
    json.dump({"cut_id": "abc"}, open(os.path.join(proj, "srvjob", "review", "script.json"), "w", encoding="utf-8"))
    st, data = req("GET", "/status?job=srvjob")
    check("server: status says which cut, and not making one", st == 200 and json.loads(data)["cut_id"] == "abc" and json.loads(data)["making"] is False, data)
    json.dump({"kind": "x", "pid": os.getpid(), "at": __import__("time").time()}, open(os.path.join(proj, "srvjob", "review", ".applying"), "w", encoding="utf-8"))
    st_ = json.loads(req("GET", "/status?job=srvjob")[1])
    check("server: status says a new cut is being made, and which kind", st_["making"] is True and st_["kind"] == "x", st_)
    st, data = req("GET", f"/projects/{SRV_JOB}/review/preview.mp4", {"Range": "bytes=10-19"})
    check("server: byte ranges", st == 206 and data == bytes(range(10, 20)), (st, data[:20]))
    check("server: no climbing out of review/", req("GET", f"/projects/{SRV_JOB}/review/..%2F..%2Fsecret.txt")[0] == 404)
    os.makedirs(os.path.join(TMP, "projects", "srvjob", "review", "strip"), exist_ok=True)
    open(os.path.join(TMP, "projects", "srvjob", "review", "strip", "w0.jpg"), "wb").write(b"jpg")
    check("server: the timeline's line stills are served", req("GET", f"/projects/{SRV_JOB}/review/strip/w0.jpg")[0] == 200)
    check("server: no climbing out of strip/", req("GET", f"/projects/{SRV_JOB}/review/strip/..%2F..%2F..%2Fsecret.txt")[0] == 404)
    check("server: no other folders", req("GET", "/projects/" + "secret.txt")[0] == 404)
    body = json.dumps({"job": "srvjob", "id": "x", "cut": [], "back": []})
    st, _ = req("POST", "/save?job=srvjob", {"Content-Type": "application/json", "Origin": "https://evil.example",
                                             "Content-Length": str(len(body))}, body)
    check("server: a write from another site is refused", st == 403, st)
    st, _ = req("POST", "/save?job=srvjob", {"Content-Type": "application/json", "Host": "localhost:1",
                                             "Content-Length": str(len(body))}, body)
    check("server: a write naming another host is refused", st == 403, st)
    # a second Send (or any look change) while her cut is still updating: "hold on", never "your export is running"
    h = {"Content-Type": "application/json", "Content-Length": str(len(body))}
    real_jd = srv.ve.job_dir
    srv.ve.job_dir = lambda job: os.path.join(proj, "srvjob") if os.path.basename(str(job)) == "srvjob" else real_jd(job)
    with srv._guard:
        srv._running.add("srvjob"); srv._bg_kind["srvjob"] = "lean"
    try:
        st, data = req("POST", "/save?job=srvjob", h, body)
        j = json.loads(data)
        check("server: a Send while her cut is updating is a busy 'hold on' (the page's calm toast), not an export refusal",
              st == 409 and j.get("busy") is True and "export" not in j.get("error", "").lower(), (st, j))
        st, data = req("POST", "/swap?job=srvjob", h, body)
        check("server: a look change while her cut is updating waits too, as busy", st == 409 and json.loads(data).get("busy") is True, (st, data))
        with srv._guard:
            srv._bg_kind["srvjob"] = "finish"
        st, data = req("POST", "/save?job=srvjob", h, body)
        check("server: a change during a real export still says the export is running", st == 409 and "export is running" in json.loads(data).get("error", ""), (st, data))
    finally:
        with srv._guard:
            srv._running.discard("srvjob"); srv._bg_kind.pop("srvjob", None)
        srv.ve.job_dir = real_jd
    httpd.shutdown()


def test_lock_and_names():
    jd = make_job("locky", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    with ve._making(jd, "lean"):
        check("lock: the page sees a change is running", ve.making_now(jd) == "lean")
        refuses("lock: a second change at the same time is refused", lambda: ve._making(jd, "full").__enter__())
    check("lock: released when done", ve.making_now(jd) == "" and not os.path.exists(os.path.join(jd, "review", ".applying")))
    json.dump({"kind": "lean", "pid": 999999, "at": __import__("time").time()}, open(os.path.join(jd, "review", ".applying"), "w", encoding="utf-8"))
    check("lock: a crashed update's flag is cleared, never 'updating' forever", ve.making_now(jd) == "" and not os.path.exists(os.path.join(jd, "review", ".applying")))
    with ve._making(jd, "lean"):
        pass
    check("lock: usable again after a crash", ve.making_now(jd) == "")
    # the exact stale check
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    open(os.path.join(jd, "outputs", "locky.mp4"), "wb").write(b"video")
    ve._stamp_base(jd)
    check("stale: the video stamped with this cut matches", ve.base_is_stale(jd) is False)
    c = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8")); c["segments"][0]["end"] += 0.001
    json.dump(c, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    check("stale: even a 1 ms change to the cut is caught", ve.base_is_stale(jd) is True)
    # names
    real_root = ve.ROOT
    try:
        ve.ROOT = TMP; os.makedirs(os.path.join(TMP, "projects", "mi-próximo reel's"), exist_ok=True)
        check("names: any language and punctuation", ve.job_dir("mi-próximo reel's").endswith("mi-próximo reel's"))
        refuses("names: never a path that climbs out", ve.job_dir, "../projects")
        refuses("names: never an engine folder by the same name", ve.job_dir, "product")
    finally:
        ve.ROOT = real_root


def test_page_flow():
    import time as _t
    import visual_editor_server as srv
    srv.ve = ve
    jd = make_job("flow", SEGS)
    words, segs, seg_of, order, moved, wid = model(jd)
    ve._atomic_json(os.path.join(jd, "review", "script.json"),
                    {"job": "flow", "id": wid, "cut_id": "c1", "words": [{"k": x is not None, "t": "w", "s": 0, "c": 0} for x in seg_of],
                     "lines": [[0, 1, 2], [3], [4], [5, 6], [7], [8, 9]], "clips": [{"name": "a.mov", "offset": 0}]})
    calls = []
    real = (ve.apply, ve.base_is_stale, ve.finish_cut)
    try:
        ve.apply = lambda job, **k: calls.append("lean")
        real_finish_cut = ve.finish_cut                      # the real one, for the Finish check below
        ve.finish_cut = lambda job, **k: calls.append("full")
        srv.save(jd, {"job": "flow", "id": wid, "cut": [1], "back": []})
        srv.run_in_background(jd, "lean", lambda: (ve.apply(jd), _t.sleep(0.3)))
        try:
            srv.run_in_background(jd, "lean", lambda: None); busy = False
        except srv.Busy:
            busy = True
        _t.sleep(0.5)
        check("page flow: Send runs the lean round on its own", calls == ["lean"], calls)
        ve.base_is_stale = lambda job: False
        r = srv.ready(jd, {"id": wid})
        check("page flow: cut's ready with nothing to re-make is instant", r == {"locked": True, "instant": True}, r)
        check("page flow: the cut is marked locked in", json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8"))["phase"] == "looks")
        ve.base_is_stale = lambda job: True
        os.remove(os.path.join(jd, "review", "phase.json"))
        r = srv.ready(jd, {"id": wid}); _t.sleep(0.2)
        check("page flow: after edits, Lock in my cut is still instant: no full cut until Finish (her page IS the cut)",
              r == {"locked": True, "instant": True} and "full" not in calls and os.path.exists(os.path.join(jd, "review", "phase.json")), (r, calls))
        check("captions step aside once for overlapping looks (a karaoke running into a takeover never brings them back mid-takeover)",
              ve._merge_spans([(47.487, 50.707), (43.373, 47.713), (58.8, 62.9), (62.9, 63.5)]) == [(43.373, 50.707), (58.8, 63.5)],
              ve._merge_spans([(47.487, 50.707), (43.373, 47.713), (58.8, 62.9), (62.9, 63.5)]))
        # her images and GIFs: only from her favorites drawers, only images, a dropped file filed in the right drawer
        import base64
        froot = tempfile.mkdtemp(prefix="favs-"); real_root = ve.ROOT; ve.ROOT = froot
        try:
            os.makedirs(os.path.join(froot, "favorites", "gifs")); open(os.path.join(froot, "favorites", "gifs", "Wow GIF by Someone.gif"), "wb").write(b"GIF89a")
            open(os.path.join(froot, "secret.txt"), "w", encoding="utf-8").write("x")
            items = ve.favorite_media()
            bad = []
            for mid in ("../secret.txt", "gifs/../../secret.txt", "sounds/x.gif", "gifs/missing.gif"):
                try:
                    ve.favorite_path(mid); bad.append(mid)
                except ve.Refuse:
                    pass
            up = ve.favorite_upload("sticker.png", "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode())
            try:
                ve.favorite_upload("notes.txt", base64.b64encode(b"hi").decode()); bad.append("txt upload")
            except ve.Refuse:
                pass
        finally:
            ve.ROOT = real_root
        check("image picker: her favorites only (names cleaned), nothing outside them, uploads filed by kind",
              [(i["id"], i["name"], i["kind"]) for i in items] == [("gifs/Wow GIF by Someone.gif", "Wow", "GIF")] and not bad
              and up["id"] == "graphics/sticker.png", (items, bad, up))
        # a look that shows the words she's saying takes the captions' place; one with its own copy doesn't
        sd = tempfile.mkdtemp(prefix="says-"); rl = ve._line_words
        os.makedirs(os.path.join(sd, "a")); os.makedirs(os.path.join(sd, "b"))
        open(os.path.join(sd, "a", "index.html"), "w", encoding="utf-8").write('<style>.x{}</style><div><span>let me</span> <span>break it down.</span></div><script>tl.to("#x")</script>')
        open(os.path.join(sd, "b", "index.html"), "w", encoding="utf-8").write('<div>you are missing the room</div>')
        ve._line_words = lambda jd_, a, b: [{"w": w} for w in "let me break it down.".split()]
        try:
            says = (ve._says_her_words(sd, {"dir": "a", "offset": 0, "dur": 2}), ve._says_her_words(sd, {"dir": "b", "offset": 0, "dur": 2}))
        finally:
            ve._line_words = rl; shutil.rmtree(sd, ignore_errors=True)
        check("captions step aside for a look that shows her words (a Sandbox design too), not for a hook with its own copy", says == (True, False), says)
        # "It's okay": a finding she meant stays quiet while the line keeps that look (a redraw keeps it); on her face, Finish lets it through
        ok_dir = tempfile.mkdtemp(prefix="okay-"); os.makedirs(os.path.join(ok_dir, "review"))
        json.dump({"layers": [{"name": "add-w5", "look": "spotlight", "dir": "hf-graphics/_looks/add-w5/x"}]}, open(os.path.join(ok_dir, "review", "looks.json"), "w", encoding="utf-8"))
        rj = ve.job_dir; ve.job_dir = lambda j: ok_dir
        try:
            ve.check_ok("anyjob", "add-w5", "face")
            same = ve.checks_ok(ok_dir, [{"name": "add-w5", "look": "spotlight", "dir": "hf-graphics/_looks/add-w5/y"}])   # redrawn: same look
            moved = ve.checks_ok(ok_dir, [{"name": "add-w5", "look": "takeover", "dir": "hf-graphics/_looks/add-w5/z"}])  # swapped
            import finish as _fin
            let_through = "add-w5" in _fin.allowed(ok_dir)
            try:
                ve.check_ok("anyjob", "add-w5", "nonsense"); bad = True
            except ve.Refuse:
                bad = False
        finally:
            ve.job_dir = rj; shutil.rmtree(ok_dir, ignore_errors=True)
        check("it's okay: quiet through a redraw, checked again after a swap, on her face let through Finish, only real checks", same == {"add-w5|face": True}
              and moved == {} and let_through and not bad, (same, moved, let_through))
        # size and turn: around the look's own center, the move landing after them; a plain move stays a plain move
        nd = tempfile.mkdtemp(prefix="nudge-"); os.makedirs(os.path.join(nd, "p"))
        open(os.path.join(nd, "p", "index.html"), "w", encoding="utf-8").write("<html><head></head><body><div id=root></div></body></html>")
        ve._apply_nudge(nd, "p", [10, -20, 1.5, -12, 540, 1175]); full = open(os.path.join(nd, "p", "index.html"), encoding="utf-8").read()
        ve._apply_nudge(nd, "p", [4, 6]); plain = open(os.path.join(nd, "p", "index.html"), encoding="utf-8").read()
        shutil.rmtree(nd, ignore_errors=True)
        check("move: size and turn around its center, then the move; a plain move has no size or turn",
              "transform:translate(10px,-20px) rotate(-12.00deg) scale(1.500);transform-origin:540px 1175px;" in full
              and "transform:translate(4px,6px);" in plain and "rotate" not in plain and plain.count('id="ve-nudge"') == 1, (full[-160:], plain[-120:]))
        box = {"left": 400, "top": 1100, "w": 280, "h": 280}
        moves = {k: ve._media_moves(k, box, 3.0) for k, _ in ve.MEDIA_EFFECTS}
        num = lambda js, k: float(re.search(k + r":(-?\d+(?:\.\d+)?)", js).group(1))
        sl, sr, dr, ri = (num(moves["slide-left"][0], "x"), num(moves["slide-right"][0], "x"), num(moves["drop"][0], "y"), num(moves["rise"][0], "y"))
        check("images: slides start fully outside the frame even made 4x bigger, and leave the way they came; every entrance draws",
              box["left"] + sl + box["w"] * 4 < 0 and box["left"] + sr > 1080 and box["top"] + dr + box["h"] * 4 < 0 and box["top"] + ri > 1920
              and f"x:{int(sl)}" in moves["slide-left"][1] and "bounce.out" in moves["drop"][0]
              and all(a.startswith("tl.") and b.startswith("tl.") for a, b in moves.values()), (sl, sr, dr, ri))
        # the watcher: returns (claimed) the moment her page has something Claude hasn't taken; nothing = [] at the timeout
        wd = tempfile.mkdtemp(prefix="watch-"); os.makedirs(os.path.join(wd, "review"))
        rj, rt = ve.job_dir, ve.todo; ve.job_dir = lambda j: wd
        try:
            ve.todo = lambda j: []
            none = ve.wait_for_her("x", timeout=0.3, every=0.1)
            ve.todo = lambda j: [{"kind": "cut-note", "id": "n1", "text": "bigger"}, {"kind": "redo-look", "layer": "h01-hook"}]
            got = ve.wait_for_her("x", timeout=2, every=0.05)
            claimed = json.load(open(os.path.join(wd, "review", "claude-working.json"), encoding="utf-8"))["ids"]
            handoff = ve.watching(wd)                                    # handed to Claude: her page still says Claude has it
            again = ve.wait_for_her("x", timeout=0.3, every=0.1)        # the same items, already Claude's: it keeps waiting
            gone = not os.path.exists(os.path.join(wd, "review", "claude-watching.json"))
        finally:
            ve.job_dir, ve.todo = rj, rt; shutil.rmtree(wd, ignore_errors=True)
        check("watcher: after it hands Claude her items the page still counts Claude as watching (never 'type update my edit'), and the next watcher starts",
              handoff and again == [], (handoff, again))
        check("watcher: nothing new = [] at its timeout; new items come back claimed; items Claude already has don't wake it",
              none == [] and len(got) == 2 and claimed == ["n1", "redo:h01-hook"] and again == [] and gone, (none, got, claimed, again))
        # the failsafe: a look she added plays on its own words; one that isn't, is found, whatever a marker says
        rw = (ve.word_cut_times, ve._adds)
        ve.word_cut_times = lambda jd_: {10: (5.0, 5.3), 20: (9.0, 9.4)}
        ve._adds = lambda jd_: {"add-w10": {"look": "takeover", "span": [5.0, 7.0]}, "add-w20": {"look": "takeover", "span": [12.0, 14.0]},
                                "add-w30": {"look": "karaoke", "span": [20.0, 22.0]}, "cap-all": {"look": "phrase", "span": [0, 30]},
                                "add-w40": {"look": "_off", "span": [1, 2]}, "add-w11": {"look": "hook", "words": [20, 20], "span": [9.0, 9.4]}}
        try:
            d = ve.drifted_adds(jd)
        finally:
            ve.word_cut_times, ve._adds = rw
        check("failsafe: a look off its words (or on cut words) is found; one on its words (its name's or its span's first), captions and removed looks aren't",
              sorted(d) == ["add-w20", "add-w30"], d)
        # Finish makes the cut she set, exactly: no second cleaning pass, no stumble check, her layer kept
        seen, st = {}, {"stale": True}
        real = (ve._stitch, ve.base_is_stale, ve.build_script)
        ve._stitch = lambda jd_, lean, log=print, env=None, keep_phase=False, stop=None: (seen.update(lean=lean, env=env, keep_phase=keep_phase), st.update(stale=False))
        ve.base_is_stale = lambda job: st["stale"]; ve.build_script = lambda job: None
        ve._atomic_json(os.path.join(jd, "review", "phase.json"), {"phase": "render"})
        try:
            real_finish_cut(jd, log=lambda *a: None, exact=True)
        finally:
            ve._stitch, ve.base_is_stale, ve.build_script = real
        check("finish: her cut is encoded exactly as she set it (no re-clean, no stumble check), her layer kept",
              seen.get("lean") is False and seen.get("env") == {"TRIM_RESTARTS": "0", "SNAP": "0", "VERIFY_CUT": "0"} and seen.get("keep_phase") is True
              and json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8"))["phase"] == "render", seen)
        srv.save(jd, {"job": "flow", "id": wid, "cut": [2], "back": []})
        check("page flow: editing again re-opens the cut phase", not os.path.exists(os.path.join(jd, "review", "phase.json")))
        out = srv.save_notes(jd, {"id": wid, "notes": [{"id": "n1", "w": 3, "text": "Sounds clipped"}, {"id": "bad/id", "w": 3, "text": "x"},
                                                        {"id": "n2", "w": 999, "text": "past the end"}, {"id": "n3", "w": 4, "text": "  "}]})
        check("notes: only good notes are kept", [n["id"] for n in out] == ["n1"], out)
        r = srv.ready(jd, {"id": wid})
        check("notes: Lock in locks in even with a note open (her call; the fix keeps her lock), and says how many are open",
              r.get("locked") is True and r.get("notes_open") == 1, r)
        os.remove(os.path.join(jd, "review", "phase.json"))          # (the flow below starts from an unlocked cut again)
        ve.resolve(jd, "n1", "Let the end of the word ring out a little longer.")
        out = srv.save_notes(jd, {"id": wid, "notes": [{"id": "n1", "w": 3, "text": "Sounds clipped"}]})
        check("notes: my fix survives her page re-sending the note", out[0]["status"] == "fixed" and "ring out" in out[0]["reply"], out)
        out = srv.save_notes(jd, {"id": wid, "notes": [{"id": "n1", "w": 3, "text": "Still clipped at the end"}]})
        check("notes: rewriting a fixed note opens it again", out[0]["status"] == "open" and out[0]["reply"] == "", out)
        check("notes: listed for me with the line", ve.notes(jd)[0]["line"] == 2, ve.notes(jd))
        refuses("notes: a stale page can't save notes", srv.save_notes, jd, {"id": "old", "notes": []})
    finally:
        ve.apply, ve.base_is_stale, ve.finish_cut = real
    check("page flow: two updates never run at once", busy is True)


def test_windows_bash():
    real_name, real_which, real_exists = ve.os.name, ve.shutil.which, ve.os.path.exists
    try:
        ve.os.name = "nt"
        ve.shutil.which = lambda n: r"C:\Windows\System32\bash.exe" if n == "bash" else None
        ve.os.path.exists = lambda p: False
        refuses("windows: WSL's bash is never used for the stitch", ve._bash)
        ve.shutil.which = lambda n: {"bash": r"C:\Windows\System32\bash.exe", "git": r"C:\Program Files\Git\cmd\git.exe"}.get(n)
        ve.os.path.exists = lambda p: p.endswith("Git\\bin\\bash.exe") or p.endswith("Git/bin/bash.exe") or p.endswith(r"Git\bin\bash.exe")
        got = ve._bash()
        check("windows: Git Bash is found next to git", got.lower().replace("/", "\\").endswith(r"git\bin\bash.exe"), got)
    finally:
        ve.os.name, ve.shutil.which, ve.os.path.exists = real_name, real_which, real_exists


def test_two_clips():
    w2 = [{"word": f"x{i}", "start": i * 1.0, "end": i * 1.0 + 0.6} for i in range(4)]
    clips = [{"clip": "a.mov", "words": WORDS[:4]}, {"clip": "b.mov", "words": w2}]
    jd = make_job("twoclips", [seg(-0.04, 1.64), seg(0.96, 3.64, clip="b.mov")], clips=clips)
    words, segs, seg_of, order, moved, wid = model(jd)
    check("two clips: footage order across clips", order == [0, 1, 2, 3, 4, 5, 6, 7], order)
    check("two clips: membership per clip", seg_of[4] is None and seg_of[5] == 1, seg_of)
    out = ve.apply_edits(jd, {"job": "twoclips", "id": wid, "cut": [], "back": [4]}, stitch=False, log=QUIET)
    check("two clips: a restored word stays on its own clip", any(s["clip"] == "b.mov" and s["transcript"] == "x0" for s in out), out)


def test_trims():
    jd = make_job("trims", SEGS); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    _, _, _, _, _, wid = model(jd)
    base = {"job": "trims", "id": wid, "cut": [], "back": []}
    # her drag: let w5 breathe in at 4.70, tighten w6's tail to 6.62
    out = ve.apply_edits(jd, {**base, "trims": {"s": {"5": 4.70}, "e": {"6": 6.62}}}, stitch=False, log=QUIET)
    p = out[1]
    check("trim: the start is exactly where she dropped it", p["start"] == 4.7, p)
    check("trim: the end is exactly where she dropped it", p["end"] == 6.62, p)
    check("trim: a dragged edge is pinned (keep_edges)", p.get("keep_edges") is True, p)
    check("trim: untouched pieces keep their edges", out[2]["start"] == 7.96 and out[2]["end"] == 9.64, out[2])
    check("trim: no helper fields leak into the plan", all("_w" not in x for x in out), out)
    # dragged too far: never into the cut word before (w4 ends 4.6) or past its own word
    out = ve.apply_edits(jd, {**base, "trims": {"s": {"5": 3.0}, "e": {"6": 9.0}}}, stitch=False, log=QUIET)
    check("trim: a start can't reach into the word before", abs(out[1]["start"] - 4.6) < 1e-9, out[1])
    check("trim: an end can't reach into the word after", abs(out[1]["end"] - 7.0) < 1e-9, out[1])
    out = ve.apply_edits(jd, {**base, "trims": {"s": {"5": 5.9}, "e": {"6": 5.1}}}, stitch=False, log=QUIET)
    check("trim: a start never swallows its own word", abs(out[1]["start"] - 5.55) < 1e-9, out[1])
    check("trim: an end never swallows its own word", abs(out[1]["end"] - 6.05) < 1e-9, out[1])
    # the reel's very first word: room before it, never below zero
    out = ve.apply_edits(jd, {**base, "trims": {"s": {"0": -2.0}}}, stitch=False, log=QUIET)
    check("trim: the first word can't start before the footage", out[0]["start"] == 0.0, out[0])
    # a trim on a word that isn't at a piece's edge does nothing
    out = ve.apply_edits(jd, {**base, "trims": {"s": {"1": 0.8}}}, stitch=False, log=QUIET)
    check("trim: a word inside a piece is ignored", [(x["start"], x["end"]) for x in out] == [(x["start"], x["end"]) for x in SEGS], out)
    # trims ride with cuts: cut w1, then trim the new piece's start (w2)
    out = ve.apply_edits(jd, {**base, "cut": [1], "trims": {"s": {"2": 1.80}}}, stitch=False, log=QUIET)
    check("trim + cut: the split piece takes her edge", out[1]["start"] == 1.8 and out[1].get("keep_edges") is True, out[1])
    # CapCut-style: dragging w6's end OUT over the struck w7 pulls it into that clip, pause and all
    out = ve.apply_edits(jd, {**base, "back": [7], "trims": {"e": {"7": 7.62}}}, stitch=False, log=QUIET)
    check("stretch end: one clip, not a separate piece", len(out) == 4 and out[1]["transcript"].endswith("w7"), out)
    check("stretch end: keeps its start, ends where she dropped it", out[1]["start"] == 4.96 and out[1]["end"] == 7.62, out[1])
    check("stretch end: her words are safe from the restart pass", out[1].get("no_trim") is True, out[1])
    out = ve.apply_edits(jd, {**base, "back": [7]}, stitch=False, log=QUIET)
    check("tap-back (no drag): stays its own piece", len(out) == 5, out)
    out = ve.apply_edits(jd, {**base, "back": [4], "trims": {"s": {"4": 3.9}}}, stitch=False, log=QUIET)
    check("stretch start: w4 joins the clip after it", len(out) == 4 and out[1]["transcript"].startswith("w4"), out)
    check("stretch start: starts where she dropped it, keeps its end", out[1]["start"] == 3.9 and out[1]["end"] == 6.64, out[1])
    # and inward: dragging the start in past w5 cuts it, the edge lands on w6
    out = ve.apply_edits(jd, {**base, "cut": [5], "trims": {"s": {"6": 5.8}}}, stitch=False, log=QUIET)
    check("tighten: the passed word is cut, the edge is hers", out[1]["transcript"] == "w6." and out[1]["start"] == 5.8, out[1])
    # a SPLIT on the timeline: an end edge on w5 and a start edge on w6 cuts the piece in two at her spot
    out = ve.apply_edits(jd, {**base, "trims": {"e": {"5": 5.8}, "s": {"6": 5.8}}}, stitch=False, log=QUIET)
    check("split: one piece becomes two at her spot", len(out) == 5 and out[1]["end"] == 5.8 and out[2]["start"] == 5.8
          and out[1]["transcript"] == "w5" and out[2]["transcript"] == "w6.", out)
    check("split: both new edges are pinned", out[1].get("keep_edges") is True and out[2].get("keep_edges") is True, out[1:3])
    check("split: the rest of the cut is untouched", out[1]["start"] == 4.96 and out[2]["end"] == 6.64 and out[3]["start"] == 7.96, out)
    # ...and dragging the two new edges together closes the pause between w5 and w6
    out = ve.apply_edits(jd, {**base, "trims": {"e": {"5": 5.65}, "s": {"6": 5.95}}}, stitch=False, log=QUIET)
    check("split: closing the gap drops the pause", out[1]["end"] == 5.65 and out[2]["start"] == 5.95, out[1:3])
    # an edge partway into a word (a smooth drag, like CapCut) is kept where she put it
    out = ve.apply_edits(jd, {**base, "trims": {"s": {"5": 5.3}}}, stitch=False, log=QUIET)
    check("trim: an edge can sit inside the word", out[1]["start"] == 5.3, out[1])
    # the code carries edges, and the receipt changes with them
    c = ve.parse_code("STYLE PLAN EDITS · trims · v1a2b3c · 0:07\ncut: none\nkeep: none\nedges: 5s=4.700, 6e=6.62\n")
    check("code: reads edges", c["trims"] == {"s": {5: 4.7}, "e": {6: 6.62}}, c)
    a = ve.receipt({"job": "r", "id": "x", "cut": [], "back": []})
    check("receipt: changes with a trim", a != ve.receipt({"job": "r", "id": "x", "cut": [], "back": [], "trims": {"s": {"5": 4.7}, "e": {}}}))
    # the server keeps only sane trims
    import visual_editor_server as srv
    words, segs, seg_of, order, moved, wid = model(jd)
    ve._atomic_json(os.path.join(jd, "review", "script.json"),
                    {"job": "trims", "id": wid, "cut_id": "c", "words": [{"k": s is not None} for s in seg_of]})
    r = srv.save(jd, {**base, "length": "0:07", "trims": {"s": {"5": 4.7, "99": 1.0, "x": 2}, "e": {"6": -1, "2": 2.62}}})
    saved = json.load(open(os.path.join(jd, "transcript", "script-review.json"), encoding="utf-8"))
    check("save: trims kept, nonsense dropped", saved.get("trims") == {"s": {"5": 4.7}, "e": {"2": 2.62}}, saved)
    check("save: the count says how many edges", r["trims"] == 2, r)
    # a split ANYWHERE (mid-word, a clip's opening quiet) then a side deleted: that exact stretch comes out
    out = ve.apply_edits(jd, {**base, "holes": [{"c": 0, "s": 5.3, "e": 6.64}]}, stitch=False, log=QUIET)
    check("cut by time: the piece ends exactly where she split it", len(out) == 4 and out[1]["start"] == 4.96 and out[1]["end"] == 5.3
          and out[1].get("keep_edges") is True, out)
    out = ve.apply_edits(jd, {**base, "holes": [{"c": 0, "s": 5.5, "e": 5.9}]}, stitch=False, log=QUIET)
    check("cut by time: a stretch from the middle leaves two pieces", len(out) == 5 and out[1]["end"] == 5.5 and out[2]["start"] == 5.9, out)
    out = ve.apply_edits(jd, {**base, "holes": [{"c": 0, "s": 4.0, "e": 5.0}]}, stitch=False, log=QUIET)
    check("cut by time: the opening quiet of a clip goes", out[1]["start"] == 5.0 and out[1]["end"] == 6.64, out[1])
    out = ve.apply_edits(jd, {**base, "holes": [{"c": 9, "s": 4.0, "e": 5.0}, {"c": 0, "s": 1, "e": "x"}]}, stitch=False, log=QUIET)
    check("cut by time: nonsense is ignored", [(x["start"], x["end"]) for x in out] == [(x["start"], x["end"]) for x in SEGS], out)
    c = ve.parse_code("STYLE PLAN EDITS · trims · v1a2b3c · 0:07\ncut: none\nkeep: none\nholes: 0:5.3-6.64, 0:1.0-1.2\n")
    check("code: reads stretches cut by time", c.get("holes") == [{"c": 0, "s": 5.3, "e": 6.64}, {"c": 0, "s": 1.0, "e": 1.2}], c)
    check("receipt: changes with a stretch cut by time", a != ve.receipt({"job": "r", "id": "x", "cut": [], "back": [], "holes": [{"c": 0, "s": 1, "e": 2}]}))
    ve._atomic_json(os.path.join(jd, "review", "script.json"),
                    {"job": "trims", "id": wid, "cut_id": "c", "clips": [{"name": "a.mov", "offset": 0}], "words": [{"k": s is not None} for s in seg_of]})
    srv.save(jd, {**base, "length": "0:07", "holes": [{"c": 0, "s": 5.3, "e": 6.64}, {"c": 3, "s": 1, "e": 2}, {"c": 0, "s": 2, "e": 1}]})
    saved = json.load(open(os.path.join(jd, "transcript", "script-review.json"), encoding="utf-8"))
    check("save: stretches kept, nonsense dropped", saved.get("holes") == [{"c": 0, "s": 5.3, "e": 6.64}], saved)


def test_looks():
    import visual_editor_server as srv
    proj = os.path.join(TMP, "projects"); jd = os.path.join(proj, "lookjob"); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    comp = lambda name, dur: ('<!doctype html><html><head><script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
                              f'</head><body><div id="root" data-composition-id="{name}" data-start="0" data-duration="{dur}" '
                              'data-width="1080" data-height="1920"></div></body></html>')
    for rel, dur in (("hf-graphics/a01-hook", 4), ("hf-graphics/k01-karaoke", 2.5), ("hf-graphics/b01-behind", 3), ("hf-captions", 60)):
        os.makedirs(os.path.join(jd, rel, "assets"), exist_ok=True)
        open(os.path.join(jd, rel, "index.html"), "w", encoding="utf-8").write(comp(os.path.basename(rel), dur))
    open(os.path.join(jd, "hf-graphics", "a01-hook", "assets", "f.ttf"), "wb").write(b"font")
    open(os.path.join(jd, "raw-secret.txt"), "w", encoding="utf-8").write("private")
    # a flat windows list (one build style), a plan list with a behind-her layer (another)
    json.dump({"a01-hook": [0.0, 4.0], "k01-karaoke": [30.5, 2.5]}, open(os.path.join(jd, "hf-graphics", "windows.json"), "w", encoding="utf-8"))
    json.dump([{"name": "b01-behind", "at": 12.0, "dur": 3, "layer": "behind"}], open(os.path.join(jd, "hf-graphics", "plan.json"), "w", encoding="utf-8"))
    json.dump({"beats": [{"id": 1, "start": 0.1, "end": 4, "element": "word-card", "on_screen": "hi"}, {"id": 2, "element": "face"}]},
              open(os.path.join(jd, "graphics-plan.json"), "w", encoding="utf-8"))
    d = ve.looks_manifest(jd)
    by = {l["name"]: l for l in d["layers"]}
    check("looks: every graphic listed once", sorted(by) == ["a01-hook", "b01-behind", "hf-captions", "k01-karaoke"], sorted(by))
    check("looks: each starts where the build put it in the cut", by["k01-karaoke"]["offset"] == 30.5 and by["b01-behind"]["offset"] == 12.0, by)
    check("looks: her original captions step aside while a karaoke plays (never two sets of words)",
          [30.5, 33.0] in [list(x) for x in by["hf-captions"].get("skips", [])], by["hf-captions"].get("skips"))
    check("looks: its length and size come from the composition", by["k01-karaoke"]["dur"] == 2.5 and by["a01-hook"]["w"] == 1080, by)
    check("looks: a behind-her layer is marked (the page says so)", by["b01-behind"]["behind"] is True and by["a01-hook"]["behind"] is False, by)
    check("looks: whole-reel captions start at 0", by["hf-captions"]["offset"] == 0.0, by)
    check("looks: face beats are not looks", [b["id"] for b in d["beats"]] == [1], d["beats"])
    v0 = by["k01-karaoke"].get("v")
    check("looks: each look carries its page version (a redraw in the same folder is a new address)", all(isinstance(l.get("v"), int) for l in d["layers"]), d["layers"])
    time.sleep(0.02); hp = os.path.join(jd, "hf-graphics", "k01-karaoke", "index.html")
    open(hp, "a", encoding="utf-8").write("\n<!-- redrawn -->"); os.utime(hp, None)
    check("looks: redrawn in place, its version moves on", {l["name"]: l for l in ve.looks_manifest(jd)["layers"]}["k01-karaoke"].get("v") != v0)
    # the beat sheet's words describe each moment; where a graphic plays stays the build's (its copy may be older)
    os.makedirs(os.path.join(jd, "beat-sheet"), exist_ok=True)
    json.dump({"route": "medium", "pack": "Butter", "layers": [{"dir": "hf-graphics/k01-karaoke", "offset": 31.0}],
               "beats": [{"t": 31.5, "kind": "karaoke", "says": "x", "motion": "y", "n": 1}]}, open(os.path.join(jd, "beat-sheet", "beats.json"), "w", encoding="utf-8"))
    d = ve.looks_manifest(jd)
    check("looks: the build's timing wins over the beat sheet's copy", {l["name"]: l["offset"] for l in d["layers"]}["k01-karaoke"] == 30.5, d["layers"])
    km = next((m for m in d["moments"] if m.get("layer") == "k01-karaoke"), {})
    check("looks: the beat sheet's words come along", km.get("kind") == "karaoke" and km.get("says") == "x" and d["pack"] == "Butter", d)
    check("looks: every graphic has a card, even one the beat sheet missed",
          {m.get("layer") for m in d["moments"]} >= {"a01-hook", "b01-behind", "k01-karaoke"}
          and len([m for m in d["moments"] if m.get("layer") == "k01-karaoke"]) == 1, d["moments"])
    # a look drawn into its own folder is named by the folder, never by its page (hf-reel-type-<pack>), and gets a card
    hd = os.path.join(jd, "hf-graphics", "h09-hook", "hf-reel-type-butter")
    os.makedirs(hd, exist_ok=True)
    shutil.copy(os.path.join(jd, "hf-graphics", "a01-hook", "index.html"), os.path.join(hd, "index.html"))
    wp = os.path.join(jd, "hf-graphics", "windows.json")
    w0 = open(wp, encoding="utf-8").read() if os.path.exists(wp) else None
    wj = json.loads(w0) if w0 else {"windows": {}}
    wj.setdefault("windows", {})["h09-hook/hf-reel-type-butter"] = [40.0, 44.0]
    json.dump(wj, open(wp, "w", encoding="utf-8"))
    d = ve.looks_manifest(jd)
    hl = next((l for l in d["layers"] if l["dir"].endswith("h09-hook/hf-reel-type-butter")), {})
    check("looks: a drawn look is named by its folder, swappable, with a card", hl.get("name") == "h09-hook" and hl.get("swappable")
          and any(m.get("layer") == "h09-hook" for m in d["moments"]) and not hl.get("captions"), (hl, d["moments"]))
    shutil.rmtree(os.path.join(jd, "hf-graphics", "h09-hook"))
    if w0 is None: os.remove(wp)
    else: open(wp, "w", encoding="utf-8").write(w0)
    # no graphics at all: no list (and a stale one goes)
    bare = os.path.join(proj, "bare"); os.makedirs(os.path.join(bare, "review"), exist_ok=True)
    open(os.path.join(bare, "review", "looks.json"), "w", encoding="utf-8").write("{}")
    check("looks: nothing built, nothing listed", ve.looks_manifest(bare) is None and not os.path.exists(os.path.join(bare, "review", "looks.json")))

    # the server plays them: offline animation library, files inside the graphics folders only
    srv.PROJECTS = proj
    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def get(path):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
        r = c.getresponse(); data = r.read(); c.close()
        return r.status, data
    st, html = get(f"/projects/{LOOK_JOB}/hf-graphics/a01-hook/index.html")
    check("looks server: serves a graphic", st == 200 and b"data-composition-id" in html, st)
    check("looks server: swaps the online library for the local copy", b"/vendor/gsap.min.js" in html and b"jsdelivr" not in html, html[:200])
    check("looks server: the local copy is there", get("/vendor/gsap.min.js")[0] == 200)
    check("looks server: a graphic's own fonts load", get(f"/projects/{LOOK_JOB}/hf-graphics/a01-hook/assets/f.ttf") == (200, b"font"))
    check("looks server: whole-reel captions too", get(f"/projects/{LOOK_JOB}/hf-captions/index.html")[0] == 200)
    check("looks server: no climbing out", get(f"/projects/{LOOK_JOB}/hf-graphics/..%2Fraw-secret.txt")[0] == 404
          and get(f"/projects/{LOOK_JOB}/hf-graphics/../raw-secret.txt")[0] == 404)
    check("looks server: no other folders", get(f"/projects/{LOOK_JOB}/raw/x.mov")[0] == 404)
    st, data = get("/status?job=lookjob")
    check("looks server: status says when the looks last changed", st == 200 and json.loads(data).get("looks_at"), data)
    httpd.shutdown()

    # accents: a per-reel captions build (its word list beside it) and the engine's own captions builder
    cap = os.path.join(jd, "hf-graphics", "captions"); os.makedirs(cap, exist_ok=True)
    open(os.path.join(cap, "index.html"), "w", encoding="utf-8").write(
        "<html><head><style>@font-face{font-family:S;src:url('assets/serif.ttf');}.s{font-family:S;color:#FFEB7D;letter-spacing:-0.02em;}</style></head>"
        '<body><div id="root" data-composition-id="captions" data-start="0" data-duration="60" data-width="1080" data-height="1920">'
        '<div class="t" id="w0" style="top:1px;font-size:100px;opacity:0">hi</div><div class="t s" id="w1" style="top:1px;font-size:130px;opacity:0">there</div></div></body></html>')
    json.dump([{"text": "hi", "serif": False, "start": 1.0}, {"text": "there", "serif": True, "start": 1.5}], open(os.path.join(jd, "hf-graphics", "captions.json"), "w", encoding="utf-8"))
    a = ve._caption_words(jd, {"dir": "hf-graphics/captions", "name": "captions", "offset": 0.0})
    check("accents: each caption word, where it shows, and the engine's picks", [(w["sel"], w["t"], w["on"]) for w in a["words"]] == [("#w0", 1.0, False), ("#w1", 1.5, True)], a)
    check("accents: the pack's one accent look (font, color, size)", a["cls"] == "s" and a["color"] == "#FFEB7D" and a["scale"] == 1.3
          and a["font"] == "hf-graphics/captions/assets/serif.ttf", a)
    gen = os.path.join(jd, "hf-captions")
    open(os.path.join(gen, "index.html"), "w", encoding="utf-8").write('<style>.cap.kw{color:#E8B563;}</style><div class="clip cap" data-start="2.00" data-duration="0.4">so</div>'
                                                      '<div class="clip cap kw" data-start="2.50" data-duration="0.4">big</div>')
    g = ve._caption_words(jd, {"dir": "hf-captions", "name": "hf-captions", "offset": 0.0})
    check("accents: the engine's captions builder is read too", [(w["t"], w["text"], w["on"]) for w in g["words"]] == [(2.0, "so", False), (2.5, "big", True)] and g["cls"] == "kw", g)
    json.dump({"job": "lookjob", "id": "zz", "words": [{"t": "hi"}, {"t": "there"}, {"t": "you"}]}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    srv.save_accents(jd, {"id": "zz", "items": [{"i": 0, "t": 1.0, "on": True, "text": "hi"}, {"i": 1, "t": 1.5, "on": False, "text": "there"}, {"i": 99, "t": 1, "on": True}]})
    saved = json.load(open(os.path.join(jd, "transcript", "accents.json"), encoding="utf-8"))
    check("accents: her choices saved, nonsense dropped", [(x["i"], x["on"]) for x in saved["items"]] == [(0, True), (1, False)], saved)
    refuses("accents: a stale page is refused", srv.save_accents, jd, {"id": "old", "items": []})
    ve.looks_manifest(jd)
    rep = ve.accents_report(jd)
    check("accents: the build list = engine picks + hers on − hers off", "1.000  hi" in rep and "there" not in rep, rep)

    # "My looks are ready" only after the cut is locked, and it moves her to the render step
    r0 = srv.looks_ready(jd, {"id": "zz"})                        # her press locks in her cut too when it wasn't yet
    ph0 = json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8"))
    check("looks ready: before the cut is locked, it locks both in (never a refusal)", r0.get("locked") and ph0.get("phase") == "render" and ph0.get("cut_locked_at"), ph0)
    json.dump({"phase": "looks", "cut_id": "c"}, open(os.path.join(jd, "review", "phase.json"), "w", encoding="utf-8"))
    refuses("looks ready: a stale page is refused", srv.looks_ready, jd, {"id": "old"})
    srv.looks_ready(jd, {"id": "zz"})
    ph = json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8"))
    check("looks ready: on to render, keeping what it knew", ph["phase"] == "render" and ph["cut_id"] == "c", ph)


def test_build_lists_beat_stale_sheet():
    """A graphic re-timed (or put behind her) in the build's windows.json after the beat sheet was made: the page and
    her captions' step-aside follow the build, never the beat sheet's old copy (2026-10-20, a reel's karaoke moved
    35.47 -> 35.30 kept the captions on the old time; a behind-her-head look came back in front)."""
    jd = os.path.join(TMP, "projects", "stalesheet")
    comp = lambda name, dur: (f'<div id="root" data-composition-id="{name}" data-start="0" data-duration="{dur}" '
                              'data-width="1080" data-height="1920"></div>')
    for rel, dur in (("hf-graphics/14-karaoke", 2.5), ("hf-graphics/11b-caption-behind-head", 3), ("hf-graphics/02-card", 2),
                     ("hf-graphics/_looks/x", 2), ("hf-captions", 60)):
        os.makedirs(os.path.join(jd, rel), exist_ok=True)
        open(os.path.join(jd, rel, "index.html"), "w", encoding="utf-8").write(comp(os.path.basename(rel), dur))
    os.makedirs(os.path.join(jd, "review"), exist_ok=True); os.makedirs(os.path.join(jd, "beat-sheet"), exist_ok=True)
    json.dump({"layers": [{"dir": "hf-graphics/02-card", "offset": 5.0}, {"dir": "hf-graphics/14-karaoke", "offset": 35.47},
                          {"dir": "hf-graphics/11b-caption-behind-head", "offset": 20.0}, {"dir": "hf-graphics/_looks/x", "offset": 1.0}],
               "beats": [{"t": 35.6, "kind": "karaoke", "says": "", "motion": ""}]},
              open(os.path.join(jd, "beat-sheet", "beats.json"), "w", encoding="utf-8"))
    json.dump([{"name": "14-karaoke", "at": 35.30}, {"name": "11b-caption-behind-head", "at": 21.0, "layer": "behind"}],
              open(os.path.join(jd, "hf-graphics", "windows.json"), "w", encoding="utf-8"))
    ve.looks_manifest(jd)
    d = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    by = {l["name"]: l for l in d["layers"]}
    check("stale sheet: a re-timed graphic plays where the build says", by["14-karaoke"]["offset"] == 35.3, by["14-karaoke"])
    check("stale sheet: captions step aside at the new time", [35.3, 37.8] in [list(x) for x in by["hf-captions"].get("skips", [])],
          by["hf-captions"].get("skips"))
    check("stale sheet: behind her head stays behind", by["11b-caption-behind-head"]["behind"] is True
          and by["11b-caption-behind-head"]["offset"] == 21.0, by["11b-caption-behind-head"])
    check("stale sheet: a graphic only the sheet lists keeps its time", by["02-card"]["offset"] == 5.0, by.get("02-card"))
    check("stale sheet: listed once each, the sheet's order kept, her added looks never from the sheet",
          [l["name"] for l in d["layers"] if l["name"] != "hf-captions"] == ["02-card", "14-karaoke", "11b-caption-behind-head"], d["layers"])
    # a plain windows dict says nothing about behind: a plan list's behind flag stands
    json.dump([{"name": "11b-caption-behind-head", "at": 21.0, "layer": "behind"}], open(os.path.join(jd, "hf-graphics", "plan.json"), "w", encoding="utf-8"))
    json.dump({"14-karaoke": [35.30, 2.5], "11b-caption-behind-head": [21.0, 3]}, open(os.path.join(jd, "hf-graphics", "windows.json"), "w", encoding="utf-8"))
    by = {l["name"]: l for l in ve.looks_manifest(jd)["layers"]}
    check("stale sheet: a windows dict keeps the plan's behind flag", by["11b-caption-behind-head"]["behind"] is True
          and by["14-karaoke"]["offset"] == 35.3, by)


def test_lookbook_and_swap():
    import lookbook
    ids = [l["id"] for l in lookbook.looks("Butter") if l.get("from") == "pack"]   # her own saved looks are hers, not the pack's
    check("lookbook: the looks every pack already has", ids == ["hook", "eyebrow-headline", "headline-subhead", "takeover", "breakaway",
                                                              "counter", "karaoke", "single-word", "phrase", "spotlight"], ids)
    zones = {"subject": {"head_top": 486, "chin_bottom": 879, "left": 388, "right": 710},
             "zones": {"above": {"top": 270, "bottom": 428, "room_px": 158, "center_px": 349, "usable": True},
                       "below": {"top": 937, "bottom": 1620, "room_px": 683, "center_px": 1278, "usable": True},
                       "left": {"room_px": 240, "usable": True}, "right": {"room_px": 222, "usable": True}}}
    pages = {}
    for lid in ids:
        r = lookbook.draw(lid, os.path.join(TMP, "looks", lid), "Here is the number: $300 this month", 3.0, "Butter", zones, comp_id=f"t-{lid}")
        page = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read(); pages[lid] = page
        check(f"lookbook {lid}: drawn by the engine's builder, with its timeline", f'data-composition-id="t-{lid}"' in page and f'window.__timelines["t-{lid}"]' in page, page[:160])
        check(f"lookbook {lid}: its fonts travel with it", os.path.isdir(os.path.join(r["dir"], "fonts")) and os.listdir(os.path.join(r["dir"], "fonts")))
    check("lookbook: the two-part hooks really are two parts", 'id="hooksplit"' in pages["eyebrow-headline"] and 'id="hooksplit"' in pages["headline-subhead"]
          and 'id="hooksplit"' not in pages["hook"])
    check("lookbook: eyebrow+headline and headline+subhead differ", pages["eyebrow-headline"] != pages["headline-subhead"])
    check("lookbook: a count-up counts to her number", "300" in pages["counter"])
    for name, fn in (("an unknown look", lambda: lookbook.find("nope")),
                     ("a count-up on a line with no number", lambda: lookbook.draw("counter", os.path.join(TMP, "looks", "c2"), "no digits here", 2.0, "Butter"))):
        try:
            fn(); check(f"lookbook: {name} is refused", False, "did not refuse")
        except lookbook.Refuse:
            check(f"lookbook: {name} is refused", True)

    # swapping one line's look, and putting the original back
    jd = os.path.join(TMP, "projects", "swapjob"); os.makedirs(os.path.join(jd, "review"), exist_ok=True); os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    os.makedirs(os.path.join(jd, "hf-graphics", "k01-line"), exist_ok=True)
    open(os.path.join(jd, "hf-graphics", "k01-line", "index.html"), "w", encoding="utf-8").write(
        '<div id="root" data-composition-id="k01-line" data-start="0" data-duration="2.5" data-width="1080" data-height="1920"></div>')
    json.dump({"k01-line": [10.0, 2.5]}, open(os.path.join(jd, "hf-graphics", "windows.json"), "w", encoding="utf-8"))
    json.dump({"words": [{"text": "you", "start": 10.1, "end": 10.3}, {"text": "win", "start": 10.4, "end": 10.7}, {"text": "later", "start": 20, "end": 20.3}]},
              open(os.path.join(jd, "outputs", "swapjob.transcript.json"), "w", encoding="utf-8"))
    ve.looks_manifest(jd)
    menu = ve.swap_menu(jd, "k01-line")
    check("swap menu: every line look, its caption styles included, drawn on THIS line's words", menu["text"] == "you win"
          and len([l for l in menu["looks"] if l.get("from", "pack") == "pack"]) == 10
          and sum(1 for l in menu["looks"] if l.get("kind") == "Captions") == 4 and
          all(os.path.isfile(os.path.join(jd, l["dir"], "index.html")) for l in menu["looks"] if l["dir"]), menu["text"])
    cl = [l for l in menu["looks"] if l["id"] == "counter"][0]
    check("swap menu: a look that doesn't fit still shows, with a warning", cl["dir"] and cl.get("warn", "").startswith("No number"), cl)
    check("swap menu: the original is offered first, to go back", menu["original"]["dir"] == "hf-graphics/k01-line" and menu["current"] is None, menu["original"])
    ve.swap(jd, "k01-line", "takeover")
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("swap: the new look plays in place, same moment", L["dir"].endswith("_looks/k01-line/takeover/hf-reel-type-butter") and L["offset"] == 10.0 and L["look"] == "takeover", L)
    check("swap: her build's own graphic is untouched", os.path.isfile(os.path.join(jd, "hf-graphics", "k01-line", "index.html")))
    ve.swap(jd, "k01-line", None)
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("swap back: the original again", L["dir"] == "hf-graphics/k01-line" and "look" not in L, L)
    refuses("swap: a look not drawn for this line is refused", ve.swap, jd, "k01-line", "no-such-look")
    # adding a look to a line that has none, and taking it off again
    am = ve.add_menu(jd, "add-L3", 20.0, 20.3)
    check("add: the line's own words, its line looks and its caption styles (karaoke etc., under Captions)", am["text"] == "later"
          and any(l["id"] == "karaoke" and l.get("kind") == "Captions" for l in am["looks"]), am["text"])
    ve.swap(jd, "add-L3", "hook")
    d = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    added = [l for l in d["layers"] if l["name"] == "add-L3"]
    check("add: the look joins the reel at that line", added and added[0]["look"] == "hook" and abs(added[0]["offset"] - 19.88) < 0.01, added)
    check("add: it gets its own card", any(m.get("layer") == "add-L3" for m in d["moments"]), d["moments"])
    ve.swap(jd, "add-L3", None)
    check("add: taking it off leaves the line as it was", not any(l["name"] == "add-L3" for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]))
    # switching the whole reel to another pack mid-build, and back: same look, same moment, the new pack's drawing
    ve.swap(jd, "add-L3", None); ve.place_look(jd, "add-L3", 20.0, 20.3, "hook")
    out = ve.set_pack(jd, "Editorial")
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}
    check("pack switch: the reel is in the new pack", json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["pack"] == "Editorial", out)
    check("pack switch: her added look is redrawn in it, same moment", "add-L3" in out["redrawn"] and L["add-L3"]["dir"].endswith("hf-reel-type-editorial")
          and abs(L["add-L3"]["offset"] - 19.88) < 0.01, L.get("add-L3"))
    check("pack switch: her build's own graphic stays as it is", "k01-line" in out["kept"] and L["k01-line"]["dir"] == "hf-graphics/k01-line", out)
    ve.set_pack(jd, "Butter")
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}
    check("pack switch back: the old pack's drawing again, never the other one", L["add-L3"]["dir"].endswith("hf-reel-type-butter"), L["add-L3"])
    refuses("pack switch: a pack this engine doesn't have is refused", ve.set_pack, jd, "No Such Pack")
    ve.swap(jd, "add-L3", None)
    # a look she moved keeps its place when it is drawn again (a re-time, a pack switch, the final pass)
    ve.place_look(jd, "add-L3", 20.0, 20.3, "hook")
    sp_ = os.path.join(jd, "review", "swaps.json"); sd = json.load(open(sp_, encoding="utf-8"))
    sd["adds"]["add-L3"]["nudge"] = [10, -40]; json.dump(sd, open(sp_, "w", encoding="utf-8"))
    ve.place_look(jd, "add-L3", 20.0, 20.3, "hook")
    check("move: a look drawn again keeps where she moved it", json.load(open(sp_, encoding="utf-8"))["adds"]["add-L3"].get("nudge") == [10, -40],
          json.load(open(sp_, encoding="utf-8"))["adds"]["add-L3"])
    ve.swap(jd, "add-L3", None)
    # a whole-reel type page built as captions alone IS her captions (never a second set on top); one with a hook is not
    for nm, meta, html_ in (("capsonly", {"layer": "captions"}, '<div class="phrase" id="ph1">hi</div>'),
                            ("withhook", {"layer": "all"}, '<div id="hookwrap">big</div><div class="phrase">hi</div>'),
                            ("oldcaps", None, '<div class="phrase" id="ph1">hi</div>'),
                            ("oldhook", None, '<div id="hookwrap">x</div><div class="clip cap">hi</div>')):
        d_ = os.path.join(TMP, "cap-kind", nm); os.makedirs(d_, exist_ok=True)
        open(os.path.join(d_, "index.html"), "w", encoding="utf-8").write(html_)
        if meta:
            json.dump(meta, open(os.path.join(d_, "meta.json"), "w", encoding="utf-8"))
    ck = {nm: ve._captions_only(os.path.join(TMP, "cap-kind"), nm) for nm in ("capsonly", "withhook", "oldcaps", "oldhook")}
    check("captions: a captions-only page is her captions; a page with a hook is not (new and older pages)",
          ck == {"capsonly": True, "withhook": False, "oldcaps": True, "oldhook": False}, ck)
    # her highlights are written into her copy of the captions (and taken back out cleanly), never doubled
    hp = os.path.join(TMP, "acc", "index.html"); os.makedirs(os.path.dirname(hp), exist_ok=True)
    open(hp, "w", encoding="utf-8").write('<html><body><span id="w3" style="font-size:60px">hi</span></body></html>')
    ve._apply_accents(TMP, "acc", [("#w3", True, False)], "s", 1.2); ve._apply_accents(TMP, "acc", [("#w3", True, False)], "s", 1.2)
    h = open(hp, encoding="utf-8").read()
    check("highlights: written once into her copy, with the word and its look", h.count('id="ve-accents"') == 1 and '"#w3"' in h and '"s"' in h, h[-300:])
    ve._apply_accents(TMP, "acc", [], "s", 1.2)
    check("highlights: none left = the script comes back out", "ve-accents" not in open(hp, encoding="utf-8").read())
    # a captions swap draws HER words for the whole reel, never the hook's on-screen line
    lp = os.path.join(jd, "review", "looks.json"); d = json.load(open(lp, encoding="utf-8"))
    d["layers"].append({"name": "captions", "dir": "hf-graphics/k01-line", "offset": 0.0, "dur": 21.0, "captions": True})
    d["beats"] = [{"start": 0.0, "on_screen": "HOOK WORDS ONLY"}]
    json.dump(d, open(lp, "w", encoding="utf-8"))
    seen, real_draw = [], ve._draw_choice
    ve._draw_choice = lambda jd_, l, rel, comp, text, *a, **k: seen.append(text) or {"id": l["id"], "dir": None}
    try:
        ve.swap_menu(jd, "captions")
    finally:
        ve._draw_choice = real_draw
    check("captions swap: drawn on every word she says, not the hook's line", seen and all(t == "you win later" for t in seen), seen)


def test_line_edits():
    base = [[0, 1, 2], [3, 4], [5, 6, 7]]
    ap = ve.apply_line_edits
    check("lines: no edits = the engine's lines", ap(base, {"split": [], "join": []}) == base)
    check("lines: split starts a new line at that word", ap(base, {"split": [1], "join": []}) == [[0], [1, 2], [3, 4], [5, 6, 7]])
    check("lines: join runs a line into the next", ap(base, {"split": [], "join": [4]}) == [[0, 1, 2], [3, 4, 5, 6, 7]])
    check("lines: both at once", ap(base, {"split": [6], "join": [2]}) == [[0, 1, 2, 3, 4], [5], [6, 7]])
    check("lines: a word no longer in the script is ignored", ap(base, {"split": [99], "join": [7, 98]}) == base)


def test_designs():
    import lookbook
    real_root = lookbook.ROOT
    lookbook.ROOT = os.path.join(TMP, "designroot")
    try:
        st = os.path.join(real_root, "product", "lookbook-designs", "starter")
        check("designs: the starter meets the contract", lookbook.check_design(st, "Butter", render_check=False) == [],
              lookbook.check_design(st, "Butter", render_check=False))
        bad = os.path.join(TMP, "baddesign"); shutil.copytree(st, bad)
        h = open(os.path.join(bad, "index.html"), encoding="utf-8").read()
        h = h.replace("var(--pk-light)", "#ff00aa").replace("PkAccent", "Comic Sans MS").replace("__LINE1__", "Hello there")
        h = h.replace('<script src="https://cdn', '<link href="https://example.com/x.css"><script src="https://cdn')
        open(os.path.join(bad, "index.html"), "w", encoding="utf-8").write(h)
        probs = " ".join(lookbook.check_design(bad, "Butter", render_check=False))
        check("designs: its own color is refused (it wears the pack)", "#ff00aa" in probs, probs)
        check("designs: its own font is refused", "Comic Sans MS" in probs, probs)
        check("designs: a slot that never shows her words is refused", "line1" in probs, probs)
        check("designs: a web link is refused (works offline)", "offline" in probs, probs)
        r = lookbook.draw_design(st, os.path.join(TMP, "dd"), "because when one of us wins we all do", 3.0, "Butter", "dd1")
        page = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
        check("designs: her words land in the slots", "because when" in page and "__LINE" not in page and "__PX_" not in page, page[:300])
        check("designs: the pack's skin is put in (fonts beside it, colors as variables)",
              'id="pk-skin"' in page and "--pk-accent:#fdc341" in page and os.path.isdir(os.path.join(r["dir"], "fonts")))
        check("designs: timing and id from the line", 'data-composition-id="dd1"' in page and 'data-duration="3.00"' in page)
        real_check = lookbook.check_design
        lookbook.check_design = lambda src, pack, render_check=True: real_check(src, pack, render_check=False)
        did = lookbook.save_design(st, "Butter", "Sticky note (draft)")
        lookbook.check_design = real_check
        check("designs: saved into her lookbook for this pack", did == "my-sticky-note-draft" and any(l["id"] == did and l.get("design") for l in lookbook.looks("Butter")))
        r2 = lookbook.draw(did, os.path.join(TMP, "dd2"), "a short line", 2.0, "Butter")
        check("designs: a saved design draws like any other look", os.path.isfile(os.path.join(r2["dir"], "index.html")))
        check("designs: removing a draft takes it out of the lookbook", lookbook.remove_design("Butter", did) and not any(l["id"] == did for l in lookbook.looks("Butter")))
    finally:
        lookbook.ROOT = real_root


def test_unlock_on_edit():
    jd = os.path.join(TMP, "unlockjob"); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    ph = os.path.join(jd, "review", "phase.json")
    json.dump({"phase": "render", "cut_id": "c1"}, open(ph, "w", encoding="utf-8"))
    ve.reopen_looks(jd)
    check("unlock: a look change after locking puts her back on Looks", json.load(open(ph, encoding="utf-8")) == {"phase": "looks", "cut_id": "c1"})
    ve.reopen_looks(jd)
    check("unlock: nothing to undo when looks aren't locked", json.load(open(ph, encoding="utf-8"))["phase"] == "looks")
    os.remove(ph); ve.reopen_looks(jd)
    check("unlock: never locks or creates a phase by itself", not os.path.exists(ph))


def test_measured_warnings():
    import lookbook
    long = "Because when one of us wins, we all do. and here's"
    ws = [{"w": w, "t": i * 0.3} for i, w in enumerate(long.split())]
    d = os.path.join(TMP, "warns")
    eh = ve._draw_choice(d, lookbook.find("eyebrow-headline", "Butter"), "a/eh", "c-eh", long, 4.0, "Butter", None, ws)
    hk = ve._draw_choice(d, lookbook.find("hook", "Butter"), "a/hk", "c-hk", long, 4.0, "Butter", None, ws)
    check("warnings: a long headline that still fits big gets no warning", not eh.get("warn"), eh.get("warn"))
    check("warnings: a one-line hook squeezed below the readable size warns", bool(hk.get("warn")), hk)


def test_sweep_fixes():
    # a short reel (under 30 s): its whole-reel captions are never a line's look, so lines can still get one
    jd = os.path.join(TMP, "projects", "shortreel"); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    for rel, dur in (("hf-captions", 20), ("hf-graphics/k01-line", 2.0)):
        os.makedirs(os.path.join(jd, rel), exist_ok=True)
        open(os.path.join(jd, rel, "index.html"), "w", encoding="utf-8").write(f'<div id="root" data-composition-id="{os.path.basename(rel)}" data-duration="{dur}" data-width="1080" data-height="1920"></div>')
    json.dump({"k01-line": [5.0, 2.0]}, open(os.path.join(jd, "hf-graphics", "windows.json"), "w", encoding="utf-8"))
    d = ve.looks_manifest(jd); by = {l["name"]: l for l in d["layers"]}
    check("short reel: whole-reel captions aren't a line's look", by["hf-captions"]["swappable"] is False and by["hf-captions"]["captions"] is True, by["hf-captions"])
    check("short reel: a line's own graphic still is", by["k01-line"]["swappable"] is True, by["k01-line"])
    # a move on a swap whose page is gone never lands on her build's own page
    json.dump({"swaps": {"k01-line": {"look": "hook", "dir": "hf-graphics/_looks/k01-line/hook/hf-reel-type-butter", "nudge": [0, 50]}}, "adds": {}},
              open(os.path.join(jd, "review", "swaps.json"), "w", encoding="utf-8"))
    d = ve.looks_manifest(jd); L = {l["name"]: l for l in d["layers"]}["k01-line"]
    page = open(os.path.join(jd, "hf-graphics", "k01-line", "index.html"), encoding="utf-8").read()
    check("move: her build's page is never written", "ve-nudge" not in page and L["dir"] == "hf-graphics/k01-line", L)
    # moving something she never swapped: the move lands on a copy, her build stays untouched
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    json.dump({"swaps": {}, "adds": {}}, open(os.path.join(jd, "review", "swaps.json"), "w", encoding="utf-8")); ve.looks_manifest(jd)
    json.dump({"job": "shortreel", "id": "z", "words": []}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    ve.nudge(jd, "k01-line", 10, -30)
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("move original: lands on her copy", L["dir"].endswith("_looks/k01-line/_original") and L["nudge"] == [10, -30]
          and "ve-nudge" in open(os.path.join(jd, L["dir"], "index.html"), encoding="utf-8").read(), L)
    check("move original: her build untouched", "ve-nudge" not in open(os.path.join(jd, "hf-graphics", "k01-line", "index.html"), encoding="utf-8").read())
    ve.swap(jd, "k01-line", None)
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("trash: the untouched original is back", L["dir"] == "hf-graphics/k01-line", L)
    # delete an original off her video (her build untouched), then bring it back; behind-your-head is remembered
    ve.swap(jd, "k01-line", "_off")
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("delete: an original comes off her video", L.get("off") is True and os.path.isfile(os.path.join(jd, "hf-graphics", "k01-line", "index.html")), L)
    ve.swap(jd, "k01-line", None)
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("bring back: it plays again", not L.get("off"), L)
    real_can = ve.can_behind
    ve.can_behind = lambda: False
    refuses("behind: not offered until the engine has the cutout tool", lambda: ve.set_behind(jd, "k01-line", True))
    check("behind: the page is told it can't", json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")).get("can_behind") in (False, True))
    ve.can_behind = lambda: True
    ve.set_behind(jd, "k01-line", True)
    L = {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"]
    check("behind: remembered for the render", L.get("behind") is True, L)
    ve.swap(jd, "k01-line", "_off"); ve.swap(jd, "k01-line", None)
    check("behind: survives other changes", {l["name"]: l for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]}["k01-line"].get("behind") is True)
    ve.can_behind = real_can
    import shutil as _sh
    real_which = _sh.which
    _sh.which = lambda x: "/usr/bin/npx"
    check("behind: offered wherever HyperFrames' remove-background can run (the cutout the final render uses)", ve.can_behind() is True)
    _sh.which = lambda x: None
    check("behind: not offered without Node's npx", ve.can_behind() is False)
    _sh.which = real_which
    # writers never share a temp file
    import threading as th
    target = os.path.join(TMP, "atomic", "x.json"); errs = []
    def w(k):
        try:
            for _ in range(20):
                ve._atomic_json(target, {"k": k})
        except Exception as e:
            errs.append(e)
    ts = [th.Thread(target=w, args=(k,)) for k in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]
    check("save: six writers at once, no clash, valid file", not errs and json.load(open(target, encoding="utf-8"))["k"] in range(6), errs)


def test_todo():
    # "update my edit": everything waiting for Claude, in order; looks to redo only for her CURRENT cut
    jd = os.path.join(TMP, "projects", "todojob")
    for d in ("review", "transcript"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    json.dump({"cut_id": "c2", "words": [{"t": "hi", "s": 1.0, "c": 0}, {"t": "there", "s": 1.4, "c": 0}], "lines": [[0, 1]],
               "clips": [{"name": "a.mp4", "offset": 0.0}]}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    real = ve.job_dir
    ve.job_dir = lambda job: jd
    try:
        check("todo: nothing waiting = empty", ve.todo("todojob") == [])
        json.dump({"notes": [{"id": "n1", "w": 1, "text": "[Look: Hook] make it white", "status": "open"},
                             {"id": "n2", "w": 0, "text": "sounds clipped", "status": "open"},
                             {"id": "n3", "w": 0, "text": "old", "status": "fixed"},
                             {"id": "n4", "w": 0, "text": "[Sound · every reel] quieter whooshes", "status": "open"}]}, open(os.path.join(jd, "transcript", "script-notes.json"), "w", encoding="utf-8"))
        json.dump({"requests": [{"id": "r1", "w": 0, "status": "open", "words": "hi there", "idea": "sparkle"},
                                {"id": "r2", "w": 1, "status": "draft"}]}, open(os.path.join(jd, "review", "look-requests.json"), "w", encoding="utf-8"))
        json.dump({"cut_id": "c1", "refresh": ["k01-line"]}, open(os.path.join(jd, "review", "looks-retimed.json"), "w", encoding="utf-8"))
        kinds = [(x["kind"], x.get("id") or x.get("layer")) for x in ve.todo("todojob")]
        check("todo: cut notes, look notes, section notes, then ideas; fixed notes and drafts left out", kinds == [("cut-note", "n2"), ("look-note", "n1"), ("reel-note", "n4"), ("idea", "r1")], kinds)
        check("todo: looks to redo from an older cut don't count", ve.looks_to_redo(jd) == [])
        json.dump({"cut_id": "c2", "refresh": ["k01-line"]}, open(os.path.join(jd, "review", "looks-retimed.json"), "w", encoding="utf-8"))
        kinds = [x["kind"] for x in ve.todo("todojob")]
        check("todo: looks built for her old cut come after the notes", kinds == ["cut-note", "look-note", "reel-note", "redo-look", "idea"], kinds)
        real_m = ve.looks_manifest
        ve.looks_manifest = lambda jd_: None
        try:
            ve.looks_current("todojob")
        finally:
            ve.looks_manifest = real_m
        import finish
        check("stop: nothing to stop when nothing is rendering", finish.stop("todojob") is False)
        finish._save(jd, state="running", step="Rendering your captions")
        check("stop: a running render gets the stop", finish.stop("todojob") is True and finish._stopped(jd))
        os.remove(finish._stop_path(jd))
        finish._save(jd, state="running", step="Building your CapCut draft")
        try:
            finish.stop("todojob"); check("stop: never mid-way through writing her CapCut draft", False)
        except finish.Refuse:
            check("stop: never mid-way through writing her CapCut draft", not finish._stopped(jd))
        check("filter: none until she picks one", ve.grade_of(jd) is None)
        json.dump({"layers": []}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))   # a reel with looks to export
        fp0 = finish.fingerprint(jd)
        ve.reopen_looks = lambda jd_: None
        ve.set_grade("todojob", "warm")
        check("filter: her pick is kept for this reel", ve.grade_of(jd) == "warm")
        check("filter: picking one makes an older export out of date", finish.fingerprint(jd) != fp0)
        ve.set_grade("todojob", None)
        check("filter: none takes it off", ve.grade_of(jd) is None)
        try:
            ve.set_grade("todojob", "sparkly"); check("filter: an unknown one is refused", False)
        except ve.Refuse:
            check("filter: an unknown one is refused", True)
        check("looks-current: the preview is current again", ve.looks_to_redo(jd) == [] and json.load(open(os.path.join(jd, "review", "looks-cut.json"), encoding="utf-8"))["cut_id"] == "c2")
    finally:
        ve.job_dir = real


def test_review_mode():
    """The editor or the original widget: her saved default wins, then one "keep using it?" after her first reel."""
    import first_use, learned
    real = (ve.ROOT, first_use.STATE, learned.value)
    root = os.path.join(TMP, "mode-root")
    saved = {"v": "ask"}

    def finished(job, test=False):
        rd = os.path.join(root, "projects", job, "review"); os.makedirs(rd, exist_ok=True)
        json.dump({"state": "done"}, open(os.path.join(rd, "finish.json"), "w", encoding="utf-8"))
        if test:
            open(os.path.join(rd, ".test-reel"), "w", encoding="utf-8").close()
    try:
        ve.ROOT, first_use.STATE = root, os.path.join(root, "_local", "first-use.json")
        learned.value = lambda field, default=None: saved["v"]
        check("mode: nothing finished in the editor yet = the pick-one", ve.review_mode() == "ask")
        finished("a-test-copy", test=True)
        check("mode: a test reel's export doesn't count as hers", ve.review_mode() == "ask")
        finished("her-reel")
        check("mode: after her first reel finished in the editor = keep using it?", ve.review_mode() == "keep")
        d = first_use._load(); d[ve.KEEP_KEY] = "today"; first_use._save(d)
        check("mode: keep is asked once, never again", ve.review_mode() == "ask")
        for v in ("visual", "text"):
            saved["v"] = v
            check(f"mode: her saved default ({v}) skips every question", ve.review_mode() == v)
    finally:
        ve.ROOT, first_use.STATE, learned.value = real


def test_route_lock():
    """Once a reel is on the editor it stays there: the widget and the old builders refuse it."""
    import review_route, subprocess
    jd = os.path.join(TMP, "locked-reel"); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    check("route: a reel that never chose is unset", review_route.get(jd) == "unset")
    review_route.set_route(jd, "editor")
    check("route: opting in locks it to the editor", review_route.get(jd) == "editor")
    try:
        review_route.refuse_if_editor(jd, "the original widget"); refused = False
    except SystemExit as e:
        refused = "visual editor" in str(e) and "review_route.py" in str(e)
    check("route: an editor reel refuses the old road, with the way back", refused)
    bsp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build-style-plan.py")
    r = subprocess.run([sys.executable, bsp, jd], capture_output=True, text=True)
    check("route: the widget builder refuses an editor reel", r.returncode != 0 and "visual editor" in r.stderr, r.stderr[-300:])
    import inspect
    check("route: opening the editor is what locks the reel",
          "set_route(job_dir(job), \"editor\")" in inspect.getsource(ve.open_editor))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fin = lambda f: open(os.path.join(here, f), encoding="utf-8").read().split("def finalize(", 1)[1].split("\ndef ", 1)[0]
    check("route: the Clean and Super Yap builders check the lock",
          "refuse_if_editor" in fin("cleanyap.py") and "refuse_if_editor" in fin("superyap.py"))
    os.environ["REE_EDITOR_FINISH"] = "1"
    try:
        review_route.refuse_if_editor(jd, "x"); through = True
    except SystemExit:
        through = False
    finally:
        os.environ.pop("REE_EDITOR_FINISH", None)
    check("route: the editor's own export (Finish tab) is let through", through)
    fsrc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "finish.py"), encoding="utf-8").read()
    check("route: finish.py marks its export as the editor's", 'os.environ["REE_EDITOR_FINISH"] = "1"' in fsrc)
    review_route.set_route(jd, "widget")
    try:
        review_route.refuse_if_editor(jd, "x"); ok = True
    except SystemExit:
        ok = False
    check("route: her words switch it back (widget), and then nothing refuses", ok and review_route.get(jd) == "widget")


def test_older_reel_words():
    """A reel transcribed before the word field was renamed ("w") still opens in the editor."""
    old = [{"clip": "a.mp4", "words": [{"w": "Hello", "start": 0.1, "end": 0.4}, {"w": "there.", "start": 0.5, "end": 0.9}]}]
    new = [{"clip": "a.mp4", "words": [{"word": "Hello", "start": 0.1, "end": 0.4}, {"word": "there.", "start": 0.5, "end": 0.9}]}]
    check("older reels: the editor reads words saved the old way", [w["t"] for w in ve.words_of(old)] == ["Hello", "there."])
    check("older reels: and the new way, the same", ve.words_of(old) == ve.words_of(new))


def test_first_look_on_fresh_reel():
    """The first look placed on a reel with no looks list yet starts the list (it used to crash)."""
    import lookbook
    jd = make_job("fresh-looks", SEGS)
    lp = os.path.join(jd, "review", "looks.json")
    if os.path.exists(lp):
        os.remove(lp)
    real = (ve._draw_choice, ve.swap, ve._line_words, lookbook.find)
    seen = {}
    try:
        ve._draw_choice = lambda jd_, l, rel, name, text, dur, pack, zones, words, accents=None, track=None: (seen.update(pack=pack), {"dir": rel})[1]
        ve.swap = lambda job, key, lid: {"swapped": key, "look": lid}
        ve._line_words = lambda jd_, a, b: [{"w": "Hello"}]
        lookbook.find = lambda lid, pack=None: {"id": lid}
        try:
            out = ve.place_look(jd, "add-w0", 0.1, 1.0, "hook"); ok = out.get("swapped") == "add-w0"
        except FileNotFoundError:
            ok = False
        check("looks: the first look on a fresh reel starts its list instead of crashing", ok, seen)
    finally:
        ve._draw_choice, ve.swap, ve._line_words, lookbook.find = real


def test_sandbox():
    """Her sandbox: one idea in her words, three cheap sketches that never touch her reel, remix for another round,
    lock one in (it goes on her reel at its moment) and keep it for every reel or just this one."""
    import lookbook
    real_root = lookbook.ROOT
    real = (lookbook.check_design, ve.place_look, ve.swap, ve._reel_pack_for, ve._draw_choice, ve.set_behind, ve.can_behind,
            ve.word_cut_times, ve._line_words, ve._frame_at)
    lroot = os.path.join(TMP, "lb-root"); os.makedirs(lroot, exist_ok=True)
    jd = make_job("sandbox-reel", SEGS)
    placed, behinds, checks = [], [], []
    try:
        lookbook.ROOT = lroot
        lookbook.check_design = lambda src, pack, render_check=True: (checks.append(render_check), [])[1]
        ve.place_look = lambda job, key, a, b, look: (placed.append((key, look)), {"warn": None})[1]
        ve.swap = lambda job, key, look: placed.append((key, look))
        ve._reel_pack_for = lambda jd_: "Butter"
        ve._draw_choice = lambda jd_, l, rel, comp, text, dur, pack, zones, words, accents=None, track=None: {"id": l["id"], "dir": rel, "comp": comp, "dur": dur}
        ve.set_behind = lambda job, key, on: behinds.append((key, on)); ve.can_behind = lambda: True
        ve.word_cut_times = lambda jd_: {0: (0.1, 0.4), 1: (0.5, 0.9), 5: (2.0, 2.4), 6: (2.5, 2.9)}
        ve._line_words = lambda jd_, a, b: [{"w": "Hello", "s": a, "e": b}]
        ve._frame_at = lambda *a, **k: "frame.jpg"
        ve._atomic_json(os.path.join(jd, "review", "script.json"), {"words": [{"t": "Hello"}] * 8})
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lookbook-designs", "starter")
        r = ve.new_look_request(jd, None, None, None, "on lines 4 and 5, a count-up card behind my head", mode="sandbox", at=2.1)
        rid = r["id"]
        check("sandbox: an idea needs no line, and her playhead rides along", r["w"] is None and r.get("playhead") == 2.1, r)
        for k in (1, 2, 3):
            lookbook.save_design(src, "Butter", f"Sketch {k}", sample=rid, design_id=f"my-sandbox-{rid}-take-{k}")
        check("sandbox: sketches stay cheap (no render check until she locks one in)", checks and not any(checks), checks)
        ids = [l["id"] for l in lookbook.looks("Butter", job="sandbox-reel")]
        check("sandbox: sketches never show in her lists", not any(i.startswith("my-sandbox-") for i in ids), ids)
        out = ve.sandbox_takes(jd, rid, [f"my-sandbox-{rid}-take-{k}" for k in (1, 2, 3)], start=2.0, end=3.2, behind=True)
        check("sandbox: three sketches are drawn for her panel", len(out["sketches"]) == 3 and out["status"] == "takes", out.get("sketches"))
        check("sandbox: her reel is untouched until she locks one in", placed == [] and behinds == [], (placed, behinds))
        check("sandbox: her words set the moment, not a line", out["place"] == {"key": "add-w5", "start": 2.0, "end": 3.2, "behind": True}, out.get("place"))
        import editor_says
        said = editor_says.pending(jd)
        check("sandbox: her page pops 'your sketches are in your Sandbox', with the way there",
              said and said[-1]["go"] == "sandbox" and "3 sketches" in said[-1]["text"] and not said[-1]["chat"], said)
        ve.sandbox_remix(jd, rid, "like sketch 2 but bigger", f"my-sandbox-{rid}-take-2")
        todo = [t for t in ve.todo(jd) if t.get("id") == rid]
        check("sandbox: remix sends round 2 to Claude, with what to change and where from",
              todo and todo[0].get("round") == 2 and todo[0]["remixes"][-1] == {"text": "like sketch 2 but bigger", "from": f"my-sandbox-{rid}-take-2"}, todo)
        for k in (4, 5, 6):
            lookbook.save_design(src, "Butter", f"Sketch {k}", sample=rid, design_id=f"my-sandbox-{rid}-take-{k}")
        ve.sandbox_takes(jd, rid, [f"my-sandbox-{rid}-take-{k}" for k in (4, 5, 6)])
        left = [l["id"] for l in lookbook.looks("Butter", hidden=True) if l["id"].startswith("my-sandbox-")]
        check("sandbox: a new round replaces the last one's sketches", sorted(left) == sorted(f"my-sandbox-{rid}-take-{k}" for k in (4, 5, 6)), left)
        checks.clear()
        r = ve.sandbox_keep(jd, rid, "oneoff", "Count card", look_id=f"my-sandbox-{rid}-take-5")
        check("sandbox: locking in runs the full check", checks == [True], checks)
        check("sandbox: the sketch she picked goes on her reel at its moment, behind her", placed[-1] == ("add-w5", r["look"]) and behinds[-1] == ("add-w5", True), (placed, behinds))
        mine = [l["id"] for l in lookbook.looks("Butter", job="sandbox-reel")]
        other = [l["id"] for l in lookbook.looks("Butter", job="another-reel")]
        check("sandbox: 'just this reel' shows on this reel only", r["look"] in mine and r["look"] not in other, (mine, other))
        check("sandbox: the other sketches are cleared away", not any(l["id"].startswith("my-sandbox-") for l in lookbook.looks("Butter", hidden=True)))
        r2 = ve.new_look_request(jd, None, None, None, "a big title card", mode="sandbox", at=0.2)
        lookbook.save_design(src, "Butter", "Sketch 1", sample=r2["id"], design_id=f"my-sandbox-{r2['id']}-take-1")
        ve.sandbox_takes(jd, r2["id"], [f"my-sandbox-{r2['id']}-take-1"], start=0.1, end=0.9)
        r = ve.sandbox_keep(jd, r2["id"], "reuse", "Big card", look_id=f"my-sandbox-{r2['id']}-take-1")
        check("sandbox: 'save to my lookbook' shows on every reel", r["look"] in [l["id"] for l in lookbook.looks("Butter", job="another-reel")])
        r3 = ve.new_look_request(jd, None, None, None, "x", mode="sandbox", at=0.2)
        r4 = ve.new_look_request(jd, None, None, None, "a different idea", mode="sandbox", at=0.3)
        gone = [x for x in ve._requests(jd) if x["id"] == r3["id"]][0]
        check("sandbox: one at a time (a new idea replaces one nobody has started on)", gone["status"] == "dropped", gone["status"])
        lookbook.check_design = lambda src, pack, render_check=True: ["#t 2.61:1 (need 3:1)"] if render_check else []
        lookbook.save_design(src, "Butter", "Sketch 1", sample=r4["id"], design_id=f"my-sandbox-{r4['id']}-take-1")
        ve.sandbox_takes(jd, r4["id"], [f"my-sandbox-{r4['id']}-take-1"], start=0.1, end=0.9)
        try:
            ve.sandbox_keep(jd, r4["id"], "reuse", "x", look_id=f"my-sandbox-{r4['id']}-take-1"); said = ""
        except ve.Refuse as e:
            said = str(e)
        fix = [t for t in ve.todo(jd) if t.get("id") == r4["id"]]
        check("sandbox: a sketch that breaks a design rule is still kept as she picked it, and its detail lands on Claude's list",
              said == "" and fix and fix[0].get("fix"), said)
    finally:
        lookbook.ROOT = real_root
        (lookbook.check_design, ve.place_look, ve.swap, ve._reel_pack_for, ve._draw_choice, ve.set_behind, ve.can_behind,
         ve.word_cut_times, ve._line_words, ve._frame_at) = real

def test_sandbox_names_and_quiet():
    """2026-10-18, her b-roll reel with no talking: a locked-in sketch is named for what it IS ("Card pop orbit"), never
    her idea's first words, and its id follows; a sketch whose words are its own note places on a quiet stretch."""
    import lookbook, shutil
    real_root = lookbook.ROOT
    real = (lookbook.check_design, ve.place_look, ve.swap, ve._reel_pack_for, ve._draw_choice, ve.set_behind,
            ve.word_cut_times, ve._line_words, ve._frame_at, ve._swap_pack)
    lroot = os.path.join(TMP, "lb-root-names"); os.makedirs(lroot, exist_ok=True)
    jd = make_job("names-reel", SEGS)
    starter = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lookbook-designs", "starter")

    def sketch(folder, meta, html=None):
        d = os.path.join(TMP, "sketches", folder)
        shutil.rmtree(d, ignore_errors=True); shutil.copytree(starter, d)
        json.dump(meta, open(os.path.join(d, "design.json"), "w", encoding="utf-8"))
        if html:
            open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(html)
        return d
    placed = []
    try:
        lookbook.ROOT = lroot
        lookbook.check_design = lambda src, pack, render_check=True: []
        ve.place_look = lambda job, key, a, b, look: (placed.append((key, look)), {"warn": None})[1]
        ve.swap = lambda job, key, look: {"swapped": key, "look": look}
        ve._reel_pack_for = lambda jd_: "Butter"
        ve._draw_choice = lambda jd_, l, rel, comp, text, dur, pack, zones, words, accents=None, track=None: {"id": l["id"], "dir": rel, "comp": comp, "dur": dur, "text": text}
        ve.set_behind = lambda job, key, on: None
        ve.word_cut_times = lambda jd_: {0: (0.1, 0.4), 1: (0.5, 0.9), 5: (2.0, 2.4)}
        ve._line_words = lambda jd_, a, b: []                  # no talking: the cut has no words here
        ve._frame_at = lambda *a, **k: "frame.jpg"
        ve._atomic_json(os.path.join(jd, "review", "script.json"), {"words": [{"t": "Hello"}] * 8})
        r = ve.new_look_request(jd, None, None, None, "So I'm gonna be editing this in CapCut this needs to be a muted clip",
                                mode="sandbox", at=0.1)
        rid = r["id"]
        orbit = sketch("orbit", {"name": "Card pop orbit", "about": "Cards pop up around you, then orbit.", "kind": "Card",
                                 "slots": ["note"], "note": "@one @two @three @four"},
                       '<div id="root" data-composition-id="__COMP__" data-duration="__DUR__"><span>__NOTE__</span></div>')
        plain = sketch("plain", {"name": "Sketch 2", "about": "The front half of the ring: cards in front of you.",
                                 "kind": "Card", "slots": ["line1", "line2"]})
        lookbook.save_design(orbit, "Butter", "Sketch 1", sample=rid, design_id=f"my-sandbox-{rid}-r1-1")
        lookbook.save_design(plain, "Butter", "Sketch 2", sample=rid, design_id=f"my-sandbox-{rid}-r1-2")
        out = ve.sandbox_takes(jd, rid, [f"my-sandbox-{rid}-r1-1", f"my-sandbox-{rid}-r1-2"], start=0.0, end=2.4)
        sug = [t.get("suggest") for t in out["sketches"]]
        check("sandbox names: each sketch suggests a name that says what the look is (its design.json name, else its about)",
              sug == ["Card pop orbit", "Front half of the ring"], sug)
        check("sandbox names: the tiles are still numbered for picking", [t["name"] for t in out["sketches"]] == ["Sketch 1", "Sketch 2"])
        k = ve.sandbox_keep(jd, rid, "oneoff", None, look_id=f"my-sandbox-{rid}-r1-1")
        check("sandbox names: locked in with no name typed, it's named for the look and its id follows (never her idea's words)",
              k["look"] == f"my-card-pop-orbit-{rid}" and lookbook.book_entry("Butter", k["look"])["name"] == "Card pop orbit", k["look"])
        # the real place_look, on a stretch with no words under it
        ve.place_look = real[1]
        ve._swap_pack = lambda jd_, looks: ("Butter", None)
        try:
            got = ve.place_look(jd, "add-w0", 0.0, 2.4, k["look"]); said = ""
        except ve.Refuse as e:
            got, said = {}, str(e)
        check("quiet stretch: a look whose words are its own note places with no --text (it carries its own words)",
              said == "" and got.get("swapped") == "add-w0", said or got)
        lookbook.save_design(plain, "Butter", "Lines card", design_id="my-lines-card")
        try:
            ve.place_look(jd, "add-w1", 0.0, 2.4, "my-lines-card"); said = ""
        except ve.Refuse as e:
            said = str(e)
        check("quiet stretch: a look that shows her spoken words still needs words (or a --text)", "no words" in said, said)
    finally:
        lookbook.ROOT = real_root
        (lookbook.check_design, ve.place_look, ve.swap, ve._reel_pack_for, ve._draw_choice, ve.set_behind,
         ve.word_cut_times, ve._line_words, ve._frame_at, ve._swap_pack) = real


def test_lone_word_lines():
    """A lone word before a pause ("I ... built this") joins the line it leads into, never a line of its own."""
    W = lambda t, a, b: {"t": t, "c": 0, "s": a, "e": b}
    words = [W("Claude's", 0.0, 0.3), W("my", 0.35, 0.5), W("editor.", 0.55, 0.9), W("I", 0.92, 0.94),
             W("built", 5.0, 5.2), W("this.", 5.25, 5.6), W("Then", 5.7, 5.9), W("a", 6.0, 6.1), W("pause,", 6.15, 6.4),
             W("here", 10.0, 10.2), W("now.", 10.25, 10.5)]
    lines = ve.lines_of(words, list(range(len(words))), [0] * len(words), set())
    text = [" ".join(words[i]["t"] for i in l) for l in lines]
    check("lines: a lone 'I' before a pause rides into its sentence", "I built this." in text, text)
    check("lines: a real pause after several words still starts a new line", "Then a pause," in text and "here now." in text, text)


def test_nothing_lost():
    """Her work survives: replaced looks come back exactly, saves never land on another look, a bad read never
    writes an empty file, the sandbox only ever removes its own sketches, and two writers take turns."""
    import lookbook
    real_root = lookbook.ROOT
    lroot = os.path.join(TMP, "lb-safe"); os.makedirs(lroot, exist_ok=True)
    jd = make_job("safe-reel", SEGS)
    real = (ve.looks_manifest,)
    try:
        lookbook.ROOT = lroot
        ve.looks_manifest = lambda jd_: None
        # a refined, moved look on an added line, then replaced by Swap: Bring back restores it exactly
        mine = {"look": "hook", "dir": "hf-graphics/_looks/add-w0/refined-1/hf-reel-type-butter", "offset": 0.0, "dur": 2.0, "nudge": [12, -40]}
        ve._atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": {}, "adds": {"add-w0": mine}, "behind": {}})
        page = os.path.join(jd, "hf-graphics", "_looks", "add-w0", "takeover", "hf-reel-type-butter"); os.makedirs(page, exist_ok=True)
        open(os.path.join(page, "index.html"), "w", encoding="utf-8").write("<html></html>")
        ve._atomic_json(os.path.join(jd, "hf-graphics", "_looks", "add-w0", "line.json"), {"offset": 0.0, "dur": 2.0})
        ve.swap(jd, "add-w0", "takeover")
        check("safety: a swap keeps her refined look in the history first", ve.can_bring_back(jd, "add-w0"))
        ve.bring_back(jd, "add-w0")
        check("safety: Bring back restores it exactly (refine and her move)", ve._adds(jd)["add-w0"] == mine, ve._adds(jd).get("add-w0"))
        ve.bring_back(jd, "add-w0")
        check("safety: Bring back twice is a toggle, never a loss", ve._adds(jd)["add-w0"]["look"] == "takeover")
        ve.swap(jd, "add-w0", None)
        check("safety: removing a look keeps it for Bring back", ve.can_bring_back(jd, "add-w0") and "add-w0" not in ve._adds(jd))
        # an add on an empty line: Undo takes it off again
        page2 = os.path.join(jd, "hf-graphics", "_looks", "add-w3", "hook", "hf-reel-type-butter"); os.makedirs(page2, exist_ok=True)
        open(os.path.join(page2, "index.html"), "w", encoding="utf-8").write("<html></html>")
        ve._atomic_json(os.path.join(jd, "hf-graphics", "_looks", "add-w3", "line.json"), {"offset": 1.0, "dur": 2.0})
        ve.swap(jd, "add-w3", "hook"); ve.bring_back(jd, "add-w3")
        check("safety: Undo after adding a look takes it off", "add-w3" not in ve._adds(jd))
        # saves never land on a different look
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lookbook-designs", "starter")
        real_check = lookbook.check_design; lookbook.check_design = lambda src_, pack, render_check=True: []
        try:
            a = lookbook.save_design(src, "Butter", "Big card"); b = lookbook.save_design(src, "Butter", "Big card")
            check("safety: a second 'Big card' gets its own id, the first is untouched", a == "my-big-card" and b == "my-big-card-2", (a, b))
            s1 = lookbook.save_design(src, "Butter", "Sketch 1", sample="idea1", design_id="my-sandbox-idea1-r1-1")
            s2 = lookbook.save_design(src, "Butter", "Sketch 1", sample="idea1", design_id="my-sandbox-idea1-r1-1")
            check("safety: Claude fixing a sketch saves over that same sketch", s1 == s2 == "my-sandbox-idea1-r1-1", (s1, s2))
            l1 = lookbook.save_look("Butter", "hook", "My hook"); l2 = lookbook.save_look("Butter", "hook", "My hook")
            check("safety: two unnamed refines become two saved looks", l1 != l2, (l1, l2))
            # the sandbox refuses her real design as a sketch, and never removes one
            reqs = [{"id": "idea2", "w": 0, "start": 0.1, "end": 1.0, "words": "Hello", "idea": "x", "mode": "sandbox", "status": "open"}]
            ve._atomic_json(ve._requests_path(jd), {"requests": reqs})
            real_rp = ve._reel_pack_for; ve._reel_pack_for = lambda jd_: "Butter"
            try:
                try:
                    ve.sandbox_takes(jd, "idea2", [a], start=0.1, end=1.0); took = True
                except ve.Refuse:
                    took = False
                check("safety: the sandbox won't take one of her real designs as a sketch", not took)
                ve._clear_sketch("Butter", "idea2", a)
                check("safety: clearing sketches never deletes her own design", lookbook.book_entry("Butter", a) is not None)
            finally:
                ve._reel_pack_for = real_rp
        finally:
            lookbook.check_design = real_check
        # a lookbook that can't be read is never overwritten with an empty one
        bp = lookbook._book_path("Butter"); before = open(bp, encoding="utf-8").read()
        open(bp, "w", encoding="utf-8").write("{ not json")
        try:
            lookbook.save_look("Butter", "hook", "Another"); wrote = True
        except lookbook.Refuse:
            wrote = False
        check("safety: an unreadable lookbook stops the save instead of emptying it", not wrote and open(bp, encoding="utf-8").read() == "{ not json")
        open(bp, "w", encoding="utf-8").write(before)
        sp = os.path.join(jd, "review", "swaps.json"); keep = open(sp, encoding="utf-8").read()
        open(sp, "w", encoding="utf-8").write("{ not json")
        try:
            ve.set_behind(jd, "add-w0", True); wrote = True
        except ve.Refuse:
            wrote = False
        check("safety: an unreadable looks file stops 'behind you' instead of emptying her swaps", not wrote and open(sp, encoding="utf-8").read() == "{ not json")
        open(sp, "w", encoding="utf-8").write(keep)
        # the reel lock: taken and given back; a lock left by a writer that died is broken
        lf = os.path.join(jd, "review", ".write.lock")
        open(lf, "w", encoding="utf-8").write("99999999")
        ve.swap(jd, "add-w3", None)
        check("safety: a lock left by a writer that died doesn't block her", not os.path.exists(lf))
    finally:
        lookbook.ROOT = real_root
        (ve.looks_manifest,) = real


def test_music_level_sticks():
    """The music bed is heard (10 dB under her voice, not 15), and Louder / Quieter on one reel becomes her level."""
    import audio_levels, learned
    check("music: the default bed sits 10 dB under her voice", audio_levels.BED_DUCK_DB == -10.0)
    real = learned.value
    try:
        learned.value = lambda field, default=None, **k: (7.0, {"field": field}) if field == "sound.music_under_voice_db" else real(field, default, **k)
        check("music: the level she taught is the one every build uses", audio_levels.bed_duck_db() == -7.0)
        learned.value = lambda field, default=None, **k: (default, None)
        check("music: no taught level = the engine's default", audio_levels.bed_duck_db() == -10.0)
    finally:
        learned.value = real
    check("music: her level is a real preference field", "sound.music_under_voice_db" in learned.FIELDS)


def test_lead_in_words():
    """A line never ends on a word that leads into the next one: across a jump in the cut, "takeover, and | then a
    count up" reads "takeover," / "and then a count up."; an article before a cut goes with its noun; a moved piece
    keeps its own words."""
    t = ["a", "full", "screen", "takeover,", "and", "then", "a", "count", "up."]
    words = [{"t": w, "c": 0, "s": i * 1.0, "e": i * 1.0 + 0.5} for i, w in enumerate(t)]
    seg_of = [0, 0, 0, 0, 0, 1, 1, 1, 1]
    order = [0, 1, 2, 3, 4, 6, 7, 8]                     # "then" cut: a jump after "and"
    got = [" ".join(t[i] for i in ids) for ids in ve.lines_of(words, order, seg_of, set())]
    check("lines: a lead-in word before a jump starts the next line", got == ["a full screen takeover,", "and a count up."], got)
    t2 = ["under", "my", "chin,", "a", "line", "of", "captions."]
    w2 = [{"t": w, "c": 0, "s": i * 1.0 + (2.0 if i >= 4 else 0), "e": i * 1.0 + 0.5 + (2.0 if i >= 4 else 0)} for i, w in enumerate(t2)]
    got = [" ".join(t2[i] for i in ids) for ids in ve.lines_of(w2, list(range(7)), [0] * 7, set())]
    check("lines: an article before a long pause goes with its noun", got == ["under my chin,", "a line of captions."], got)
    got = [" ".join(t[i] for i in ids) for ids in ve.lines_of(words, order, seg_of, {1})]
    check("lines: a word never leaves its piece for a piece she moved", got[0].endswith("and"), got)
    t3 = ["above", "my", "head,", "single", "word", "captions."]
    w3 = [{"t": w, "c": 0, "s": i * 0.5, "e": i * 0.5 + 0.4} for i, w in enumerate(t3)]
    got = [" ".join(t3[i] for i in ids) for ids in ve.lines_of(w3, list(range(6)), [0, 0, 0, 1, 1, 1], set())]
    check("lines: a cut right after a clause starts a new line", got == ["above my head,", "single word captions."], got)
    got = [" ".join(t3[i] for i in ids) for ids in ve.lines_of(w3, list(range(6)), [0] * 6, set())]
    check("lines: a comma with no cut after it keeps the line whole", got == ["above my head, single word captions."], got)
    import lookbook
    check("cards: a hook or takeover never ends on a comma; captions keep her punctuation",
          lookbook.shown_text({"layer": "hook"}, "a hook above my head,") == "a hook above my head"
          and lookbook.shown_text({"layer": "takeover"}, "a full screen takeover;") == "a full screen takeover"
          and lookbook.shown_text({"layer": "hook"}, "did it work?") == "did it work?"
          and lookbook.shown_text({"layer": "captions"}, "under my chin,") == "under my chin,")


def test_her_default_pack():
    """A reel with no pack of its own (a fresh editor reel, nothing built) opens in HER default pack, never Butter
    by fiat; the reel's own pack and a pack she switched to on the page still win."""
    import stylepack
    have = stylepack.names()
    other = next(p for p in have if p != "Butter")
    real = ve._default_pack
    try:
        ve._default_pack = lambda: other
        check("fresh reel opens in her default pack", ve._swap_pack(TMP, {"pack": None}) == (other, None))
        check("the reel's own pack still wins", ve._swap_pack(TMP, {"pack": "Butter"})[0] == "Butter")
        check("a missing reel pack falls back to hers", ve._swap_pack(TMP, {"pack": "NoSuchPack"})[0] == other)
        ve._default_pack = lambda: "NoSuchPack"
        check("a default that isn't in this engine falls to Butter", ve._swap_pack(TMP, {"pack": None})[0] == "Butter")
        ve._default_pack = lambda: None
        check("no default chosen falls to Butter", ve._swap_pack(TMP, {"pack": None})[0] == "Butter")
    finally:
        ve._default_pack = real
    # the Lookbook's "Make it my default": saved where every build reads it, history kept, a bad name refused
    real_path = ve.USER_STYLE
    ve.USER_STYLE = os.path.join(TMP, "user-style.json")
    try:
        json.dump({"_doc": "kept", "default_pack": None, "default_accent": "#123456", "history": []}, open(ve.USER_STYLE, "w", encoding="utf-8"))
        check("make default saves", ve.set_default_pack(other) == {"default": other} and ve._default_pack() == other)
        d = json.load(open(ve.USER_STYLE, encoding="utf-8"))
        check("make default keeps her other fields", d.get("_doc") == "kept" and d.get("default_accent") == "#123456" and d["history"] == [None], d)
        ve.set_default_pack(other)
        check("the same pack twice adds no history", json.load(open(ve.USER_STYLE, encoding="utf-8"))["history"] == [None])
        refuses("an unknown pack is refused", ve.set_default_pack, "NoSuchPack")
        check("a refused pack changes nothing", ve._default_pack() == other)
        check("a fresh reel opens in the new default", ve._swap_pack(TMP, {"pack": None})[0] == other)
    finally:
        ve.USER_STYLE = real_path


def test_tour_and_fresh_stills():
    """The tour is remembered by the engine (four marks at once, none lost; a bad tab refused), and a timeline still
    made from an older preview is remade, never shown as if it were her current cut."""
    import subprocess as sp, threading
    real = ve.TOUR_FILE
    ve.TOUR_FILE = os.path.join(TMP, "_local", "editor-tour.json")
    try:
        ts = [threading.Thread(target=ve.tour_mark, args=(t, f"v{t[:2]}")) for t in ve.TOUR_TABS]
        [t.start() for t in ts]; [t.join() for t in ts]
        check("tour: four marks at once, none lost", ve.tour_seen() == {t: f"v{t[:2]}" for t in ve.TOUR_TABS}, ve.tour_seen())
        refuses("tour: a tab that isn't a tour is refused", ve.tour_mark, "nope", "abc")
    finally:
        ve.TOUR_FILE = real
    jd = os.path.join(TMP, "projects", "stilljob"); review = os.path.join(jd, "review"); os.makedirs(review, exist_ok=True)
    pv = os.path.join(review, "preview.mp4")
    mk = lambda color: sp.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=108x192:d=2", "-pix_fmt", "yuv420p", pv], capture_output=True)
    mk("red")
    data = {"words": [{"s": 0.5, "e": 0.9}]}
    check("still: made", ve.make_still(jd, data, 0) and ve._still_fresh(review, 0, data))
    first = open(os.path.join(review, "strip", "w0.jpg"), "rb").read()
    import time as _t; _t.sleep(1.1); mk("blue")                 # a re-cut: the preview is rebuilt
    check("still: an older preview's still is no longer fresh", not ve._still_fresh(review, 0, data))
    check("still: it is remade from the new preview", ve.make_still(jd, data, 0) and ve._still_fresh(review, 0, data)
          and open(os.path.join(review, "strip", "w0.jpg"), "rb").read() != first)
    data2 = {"words": [{"s": 1.4, "e": 1.8}]}                     # the same word index now sits somewhere else
    check("still: a word that moved gets a new still", not ve._still_fresh(review, 0, data2))


def test_her_picks_stay():
    """Her rule (2026-10-17): what she picks with a click on Visuals or Sound is locked in. A split or combine carries her
    picture, her refine and her highlights along (never a refusal, never redrawn plain); a cut change slides her refined
    look with its words (never left for Claude, never blocking her export); Finish's redraw of a stale look keeps where
    she moved it; a sound on a look she set stays hers; a word sound comes back with its word; a new song keeps her
    level; and an export that drops a sound says so."""
    import lookbook, finish, sound_plan
    jd = make_job("her-picks", SEGS)
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    words = [{"t": f"w{i}", "c": 0, "s": i * 1.0, "e": i * 1.0 + 0.6} for i in range(6)]
    json.dump({"id": "hp1", "job": "her-picks", "cut_id": "c1", "lines": [[0, 1, 2], [3, 4, 5]], "words": words},
              open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    json.dump({"layers": [], "pack": "Butter"}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    times = {i: (i * 1.0, i * 1.0 + 0.6) for i in range(6)}
    drew, media = [], []

    def fake_draw(look_id, out_dir, text, dur, pack, zones=None, words=None, comp_id=None, size=None, effect=None, accents=None, track=None):
        drew.append({"look": look_id, "dir": out_dir, "text": text, "size": size, "effect": effect, "accents": accents})
        page = os.path.join(out_dir, "hf-reel-type-butter"); os.makedirs(page, exist_ok=True)
        open(os.path.join(page, "index.html"), "w", encoding="utf-8").write(
            f'<html><head></head><body><div id="root" data-composition-id="{comp_id}"></div></body></html>')
        rec = {"look": look_id, "pack": pack, "text": text, "dur": round(dur, 3), "size": size, "effect": effect, "accents": []}
        json.dump(rec, open(os.path.join(out_dir, "look.json"), "w", encoding="utf-8"))
        json.dump(dict(rec, words=[]), open(os.path.join(page, "look.json"), "w", encoding="utf-8"))
        return {"dir": page, "id": comp_id, "dur": dur}

    def fake_media(jd_, key, media_id, dur, effect=None, page=None):
        m = ve.media_of(jd_, key) or {}
        media.append({"key": key, "dur": round(dur, 3), "effect": m.get("effect")})
        page = page or os.path.join(jd_, "hf-graphics", "_looks", key, "media", "hf-reel-type-media")
        os.makedirs(page, exist_ok=True)
        open(os.path.join(page, "index.html"), "w", encoding="utf-8").write("<html><head></head><body></body></html>")
        return {"dir": os.path.relpath(page, jd_).replace(os.sep, "/")}

    real = (lookbook.draw, ve._draw_media, ve.word_cut_times, ve._line_words, ve._her_accents, ve.looks_manifest, ve._swap_pack,
            ve.timeline_assets, ve._stale_look, lookbook.ROOT)
    lroot = os.path.join(TMP, "lb-picks"); os.makedirs(lroot, exist_ok=True)
    try:
        lookbook.ROOT = lroot
        lookbook.draw, ve._draw_media = fake_draw, fake_media
        ve.word_cut_times = lambda jd_: dict(times)
        ve._line_words = lambda jd_, a, b: [{"w": f"w{i}", "t": round(i * 1.0 - a, 3), "e": round(i * 1.0 + 0.6 - a, 3)}
                                           for i, (s, e) in times.items() if a - 0.05 <= s < b]
        ve._her_accents = lambda jd_: [{"w": "w4", "t": times[4][0]}] if 4 in times else []
        ve.looks_manifest = lambda jd_: None
        ve._swap_pack = lambda jd_, looks: ("Butter", None)
        ve.timeline_assets = lambda jd_, data: None
        # her picture on line 1 (moved, with the entrance she picked) and her refined takeover on line 2 (her words)
        L = os.path.join(jd, "hf-graphics", "_looks")
        fake_media(jd, "add-w0", "photos/x.png", 3.0)
        ve._atomic_json(os.path.join(L, "add-w0", "media.json"), {"media": "photos/x.png", "kind": "Image", "effect": "spin",
                                                                 "box": {"left": 100, "top": 400, "w": 300, "h": 300}})
        rdir = os.path.join(L, "add-w3", "refined-1")
        fake_draw("takeover", rdir, "MY OWN WORDS", 3.0, "Butter", comp_id="add-w3-takeover", size=1.3, effect="typewriter")
        adds = {"add-w0": {"look": "media", "dir": "hf-graphics/_looks/add-w0/media/hf-reel-type-media", "offset": 0.0, "dur": 2.6,
                           "span": [0.0, 2.6], "words": [0, 2], "anchor": [0.0, 2.0], "nudge": [40, -80]},
                "add-w3": {"look": "takeover", "dir": "hf-graphics/_looks/add-w3/refined-1/hf-reel-type-butter", "offset": 2.88,
                           "dur": 3.07, "span": [3.0, 5.6], "words": [3, 5], "anchor": [3.0, 5.0], "nudge": [0, 120]}}
        ve._atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": {}, "adds": adds, "behind": {}})
        try:
            r = ve.edit_lines(jd, "split", 1, looks=[{"layer": "add-w0", "start": 0.0, "end": 0.6}]); ok = True
        except ve.Refuse as e:
            r, ok = str(e), False
        a0 = ve._adds(jd).get("add-w0") or {}
        check("her picks: splitting a line that carries her picture goes through (never 'not in your lookbook')", ok, r)
        check("her picks: her picture follows the split with the entrance she picked and where she moved it",
              a0.get("look") == "media" and a0.get("nudge") == [40, -80] and media and media[-1]["key"] == "add-w0"
              and media[-1]["effect"] == "spin" and abs(a0.get("dur", 0) - 0.6) < 0.01, (a0, media[-1:]))
        drew.clear()
        try:
            ve.edit_lines(jd, "join", 2, looks=[{"layer": "add-w3", "start": 1.0, "end": 5.6}]); ok = True
        except ve.Refuse as e:
            ok = str(e)
        a3 = ve._adds(jd).get("add-w3") or {}
        d3 = drew[-1] if drew else {}
        check("her picks: a combine keeps her refine (size, animation, the words she typed), still marked refined",
              ok is True and d3.get("size") == 1.3 and d3.get("effect") == "typewriter" and d3.get("text") == "MY OWN WORDS"
              and "/refined-" in a3.get("dir", ""), (ok, d3, a3.get("dir")))
        check("her picks: her highlight rides along on the redrawn takeover", any(x["w"] == "w4" for x in d3.get("accents") or []), d3)
        page3 = open(os.path.join(jd, a3["dir"], "index.html"), encoding="utf-8").read() if a3.get("dir") else ""
        check("her picks: where she moved it stays on the new drawing", "translate(0px,120px)" in page3, page3[-200:])
        # a cut change moves all of its words by +2 s: her refined look slides with them, nobody has to redo it
        ve._atomic_json(os.path.join(jd, "review", "looks-cut.json"), {"cut_id": "c1", "times": {str(w): a for w, (a, b) in times.items()}})
        before = dict(ve._adds(jd)["add-w3"])
        for w in list(times):
            times[w] = (times[w][0] + 2.0, times[w][1] + 2.0)
        drew.clear()
        out = ve.retime_adds(jd)
        a3 = ve._adds(jd)["add-w3"]
        check("her picks: after a cut change her refined look slides with its words, refine intact (no redraw)",
              "add-w3" in out["moved"] and abs(a3["offset"] - (before["offset"] + 2.0)) < 0.01 and a3["dir"] == before["dir"]
              and not any(d["dir"].startswith(os.path.join(L, "add-w3")) for d in drew), (out, a3))
        check("her picks: her refined look never lands on Claude's redo list (so it never stops her export)",
              "add-w3" not in ve.looks_to_redo(jd), ve.looks_to_redo(jd))
        # Finish: a stale look she swapped in and moved is drawn again from its own record, and her move stays on it
        hdir = os.path.join(L, "h1", "hook")
        fake_draw("hook", hdir, "Hi there", 2.0, "Butter", comp_id="h1-hook", size=1.2, effect="pop-in")
        ve._atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": {"h1": {"look": "hook", "dir": "hf-graphics/_looks/h1/hook/hf-reel-type-butter",
                                                                                  "nudge": [30, 60]}}, "adds": {}, "behind": {}})
        ve._stale_look = lambda d, design=None: True
        drew.clear()
        real_ld = finish._looks_doc
        finish._looks_doc = lambda jd_: {"layers": [], "pack": "Butter"}
        try:
            finish._refresh_stale(jd, jd)
        except Exception as e:
            check("her picks: Finish's redraw of a stale look runs", False, e)
        finally:
            finish._looks_doc = real_ld
        hp = open(os.path.join(hdir, "hf-reel-type-butter", "index.html"), encoding="utf-8").read()
        check("her picks: Finish's redraw of a stale look keeps where she moved it", "translate(30px,60px)" in hp, hp[-200:])
        check("her picks: ... and its own words, size and animation", drew and drew[-1]["text"] == "Hi there" and drew[-1]["size"] == 1.2
              and drew[-1]["effect"] == "pop-in", drew[-1:])
    finally:
        (lookbook.draw, ve._draw_media, ve.word_cut_times, ve._line_words, ve._her_accents, ve.looks_manifest, ve._swap_pack,
         ve.timeline_assets, ve._stale_look, lookbook.ROOT) = real

    # a reel with no look on it yet (no looks list written): Split and a pack switch work, never a crash (a buyer's
    # editor crashed on Split here, 2026-10-17)
    fresh = make_job("her-picks-fresh", SEGS)
    os.makedirs(os.path.join(fresh, "review"), exist_ok=True)
    json.dump({"id": "hp2", "job": "her-picks-fresh", "cut_id": "c1", "lines": [[0, 1, 2], [3, 4, 5]], "words": words},
              open(os.path.join(fresh, "review", "script.json"), "w", encoding="utf-8"))
    rt = ve.timeline_assets
    try:
        ve.timeline_assets = lambda jd_, data: None
        try:
            r = ve.edit_lines(fresh, "split", 1)
            ok = r.get("lines") == [[0], [1, 2], [3, 4, 5]]
        except Exception as e:
            ok, r = False, f"{type(e).__name__}: {e}"
        check("fresh reel: Split works before her first look (no looks list yet)", ok, r)
        try:
            r = ve.set_pack(fresh, "Butter"); ok = r.get("pack") == "Butter"
        except Exception as e:
            ok, r = False, f"{type(e).__name__}: {e}"
        check("fresh reel: switching the pack works before her first look", ok, r)
    finally:
        ve.timeline_assets = rt

    # ── Sound ──
    sj = make_job("her-sounds", SEGS)
    os.makedirs(os.path.join(sj, "review"), exist_ok=True)
    mine, eng = os.path.join(sj, "mine.wav"), os.path.join(sj, "engine.wav")
    for f in (mine, eng):
        open(f, "wb").write(b"RIFF")
    ve._atomic_json(sound_plan.sound_json(sj), {"version": 1, "cues": [], "music": {}, "sfx_enabled": True, "added": [
        {"id": "look:L1", "anchor": {"layer": "L1", "at": "entrance"}, "file": mine, "name": "mine", "on": True, "how": "hers"},
        {"id": "look:L2", "anchor": {"layer": "L2", "at": "entrance"}, "file": mine, "name": "default", "on": True, "how": "default"}]})
    sreal = (sound_plan.moments, sound_plan._trim_for, sound_plan._measure)
    try:
        sound_plan.moments = lambda jd_: [{"layer": "L1", "t": 2.0, "kind": "pop", "motion_s": 0.3, "look_name": "Hook", "timing": "tween"},
                                          {"layer": "L2", "t": 6.0, "kind": "pop", "motion_s": 0.3, "look_name": "Card", "timing": "tween"}]
        sound_plan._trim_for = lambda *a, **k: None
        sound_plan._measure = lambda *a, **k: 0.5
        out, _m = sound_plan.for_build(sj, [{"file": eng, "at": 2.1}, {"file": eng, "at": 6.1}], None, say=QUIET)
        got = [(c.get("file"), c.get("_sound")) for c in out]
        check("her sound: a look whose sound she set keeps HER sound when an engine cue lands near it later",
              (mine, "look") in got and got.count((eng, None)) == 2, got)
        check("her sound: an engine default on a look still steps aside for a planned cue (no doubled engine sounds)",
              sum(1 for f, k in got if f == mine) == 1, got)
    finally:
        sound_plan.moments, sound_plan._trim_for, sound_plan._measure = sreal
    # her cut changed on a reel with no looks: her word sounds still move (and say so if they can't)
    called = []
    rr = (sound_plan.retime_added, ve.word_cut_times)
    try:
        sound_plan.retime_added = lambda jd_, t: called.append(dict(t)) or 0
        ve.word_cut_times = lambda jd_: {0: (0.0, 0.6)}
        nolooks = make_job("her-sounds-nolooks", SEGS); os.makedirs(os.path.join(nolooks, "review"), exist_ok=True)
        ve._atomic_json(sound_plan.sound_json(nolooks), {"version": 1, "added": []})
        ve.retime_adds(nolooks)
        check("her sound: her word sounds follow a cut change even on a reel with no looks", called == [{0: (0.0, 0.6)}], called)
    finally:
        sound_plan.retime_added, ve.word_cut_times = rr
    # a new song keeps the level she set: the same step from the engine's own level
    old_f, new_f = os.path.join(sj, "old-song.m4a"), os.path.join(sj, "new-song.m4a")
    for f in (old_f, new_f):
        open(f, "wb").write(b"x")
    saved = {}
    mreal = (sound_plan.read, sound_plan.resolve_choice, sound_plan.auto_bed_gain, sound_plan._save, sound_plan._programme)
    try:
        sound_plan.read = lambda j: {"cues": [], "music": {"file": old_f, "edits": {"level_db": -20.0, "file": old_f}}}
        sound_plan.resolve_choice = lambda cid, kind, jd_: {"id": cid, "file": new_f, "name": "new", "source": "library"}
        sound_plan.auto_bed_gain = lambda path, prog, bd=None: -10.0 if path == old_f else -16.0
        sound_plan._save = lambda jd_, plan, **k: saved.update(plan=plan)
        sound_plan._programme = lambda jd_: None
        sound_plan.set_music(sj, choice_id="new-song")
        lv = ((saved.get("plan") or {}).get("music") or {}).get("edits", {}).get("level_db")
        check("her sound: a new song keeps the level she set (her step under the engine's level carries over)", lv == -26.0, lv)
    finally:
        (sound_plan.read, sound_plan.resolve_choice, sound_plan.auto_bed_gain, sound_plan._save, sound_plan._programme) = mreal
    # an export whose Sound edits can't be read still exports, and says plainly that her sound didn't go in
    breal = sound_plan.base
    try:
        sound_plan.base = lambda jd_: (_ for _ in ()).throw(ValueError("damaged plan"))
        r = finish._mix_sound(sj, os.path.join(sj, "nothing.mp4"))
        notes = finish.status(sj).get("sound_notes") or []
        check("her sound: an export that couldn't read her Sound edits says so (never a silent drop)",
              r is None and len(notes) == 1 and "damaged plan" in notes[0], notes)
    finally:
        sound_plan.base = breal


def test_claude_says():
    """Claude's message for her open page (product/editor_says.py): `tell`, the cards the engine pops by itself, the
    server's part (status, the quiet background-tab check, closing one), and the chat's hooks."""
    import subprocess, editor_says as es
    import visual_editor_server as srv
    proj = os.path.join(TMP, "projects")
    jd = os.path.join(proj, "saysjob")
    real_root = es.ROOT
    es.ROOT = TMP                                        # its marker and its reels: the throwaway folder, never the engine's
    for d in ("review", "transcript"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    # the store: one plain line; the same news within minutes is one card; a hook never doubles Claude's own words
    m = es.tell(jd, "  Your sketches   are in. ", go="sandbox", kind="sandbox")
    check("says: one plain line, the way there kept", m["text"] == "Your sketches are in." and m["go"] == "sandbox" and not m["chat"], m)
    check("says: a made-up destination is dropped, never a broken button", es.tell(jd, "x", go="nowhere")["go"] is None)
    es.seen(jd)
    es.tell(jd, "Your note is fixed: a", group="note", merged="{n} of your notes are fixed.")
    es.tell(jd, "Your note is fixed: b", group="note", merged="{n} of your notes are fixed.")
    p = es.pending(jd)
    check("says: notes fixed together are one card", [x["text"] for x in p] == ["2 of your notes are fixed."], p)
    es.tell(jd, "Teaching or confessional? Pick one in the chat.", chat=True, kind="chat")
    check("says: the hook's 'question for you' never doubles Claude's own chat card",
          es.tell(jd, "Claude has a question for you.", chat=True, soft=True) is None)
    check("says: answering in the chat takes the chat card down (and only that one)",
          es.seen(jd, only_chat=True) == 1 and [x["text"] for x in es.pending(jd)] == ["2 of your notes are fixed."], es.pending(jd))
    for i in range(12):
        es.tell(jd, f"m{i}")
    check("says: a reel keeps only its newest few", len(es._load(jd)) == es.KEEP, len(es._load(jd)))
    old = es._load(jd); old[-1]["at"] -= es.SHOW_S + 5; es._save(jd, old)
    check("says: a message from hours ago never pops", old[-1]["id"] not in [x["id"] for x in es.pending(jd)])
    es.seen(jd)
    try:
        es.tell(jd, "   ")
        check("says: an empty message is refused", False)
    except ValueError:
        check("says: an empty message is refused", True)
    # the engine says it by itself
    json.dump({"notes": [{"id": "n1", "w": 0, "text": "sounds clipped", "status": "open"}]},
              open(os.path.join(jd, "transcript", "script-notes.json"), "w", encoding="utf-8"))
    ve.resolve(jd, "n1", "Fixed: trimmed that breath")
    p = es.pending(jd)
    check("says: a fixed note is one plain message, in Claude's words, saying what changed (no 'see my notes' button)",
          p and p[-1]["text"] == "Done: trimmed that breath" and not p[-1].get("go"), p)
    es.seen(jd)
    json.dump({"requests": [{"id": "r1", "w": 0, "status": "open", "idea": "sparkle", "start": 0, "end": 1}]},
              open(os.path.join(jd, "review", "look-requests.json"), "w", encoding="utf-8"))
    real_m = ve.looks_manifest
    ve.looks_manifest = lambda jd_: None
    try:
        ve.look_request_status(jd, "r1", "draft", "my-sparkle")
        ve.look_request_status(jd, "r1", "done", "my-sparkle")
        p = es.pending(jd)
        check("says: her new look on her line, then in her lookbook: one card, the newest",
              len(p) == 1 and "lookbook" in p[0]["text"] and p[0]["go"] == "visuals", p)
        es.seen(jd)
        ve.look_request_status(jd, "r1", "dropped")
        check("says: a dropped idea says nothing", es.pending(jd) == [])
    finally:
        ve.looks_manifest = real_m
    import finish
    finish._tell_done(jd, {"result": {"route": "mp4", "file": "x"}})
    check("says: an export done pops her page", (es.pending(jd) or [{}])[-1].get("kind") == "finish", es.pending(jd))
    es.seen(jd)
    finish._tell_done(jd, {"result": None})
    check("says: an export with no result says nothing", es.pending(jd) == [])
    # Claude's own words, from the chat: `tell`
    env = dict(os.environ, VE_SERVER_STATE=os.path.join(TMP, "no-server.json"))
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "visual_editor.py"), "tell", jd, "Your", "three", "sketches", "are", "in.", "--chat"],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    p = es.pending(jd)
    check("says: `tell <job> \"...\" --chat` leaves her page a chat card", r.returncode == 0 and p and p[-1]["text"] == "Your three sketches are in." and p[-1]["chat"], (r.stdout, r.stderr, p))
    check("says: `tell` says plainly when her page isn't open", "isn't open" in r.stdout, r.stdout)
    # the server: status carries them, a background tab checks quietly, closing one is for good
    srv.PROJECTS = proj
    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def req(method, path, body=None, origin=True):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        h = {"Host": f"127.0.0.1:{port}"}
        if body is not None:
            body = json.dumps(body); h.update({"Content-Type": "application/json", "Content-Length": str(len(body))})
            h["Origin"] = f"http://127.0.0.1:{port}" if origin is True else origin
        c.request(method, path, body=body, headers=h)
        r_ = c.getresponse(); data = r_.read(); c.close()
        return r_.status, data
    try:
        json.dump({"cut_id": "abc"}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
        st = json.loads(req("GET", "/status?job=saysjob")[1])
        mid = (st.get("says") or [{}])[-1].get("id")
        check("says: her page's status beat carries Claude's message", mid and st["says"][-1]["chat"], st.get("says"))
        srv._SEEN_JOB.pop("saysjob", None)
        q = json.loads(req("GET", "/says?job=saysjob")[1])
        ping = json.loads(req("GET", "/ping")[1])
        check("says: a background tab's quiet check gets them, counts the page as open, and never as her using it",
              [x["id"] for x in q["says"]] == [mid] and "saysjob" in ping.get("pages", {}) and "saysjob" not in srv._SEEN_JOB, (q, ping))
        check("says: closing it from another site is refused", req("POST", "/says-seen?job=saysjob", {"ids": [mid]}, origin="https://evil.example")[0] == 403
              and json.loads(req("GET", "/status?job=saysjob")[1]).get("says"))
        check("says: her page closes it", req("POST", "/says-seen?job=saysjob", {"ids": [mid]})[0] == 200)
        check("says: once she closes it, it never pops again", json.loads(req("GET", "/status?job=saysjob")[1]).get("says") == [])
        old_state = es.SERVER_STATE
        es.SERVER_STATE = os.path.join(TMP, "says-server.json")
        json.dump({"port": port}, open(es.SERVER_STATE, "w", encoding="utf-8"))
        try:
            check("says: the hooks know which reels have their page open", "saysjob" in [os.path.basename(x) for x in es.open_pages()], es.open_pages())
            es.hook("ask")
            p = es.pending(jd)
            check("says: the question box waiting in the chat pops her open page", p and p[-1]["chat"] and "question" in p[-1]["text"], p)
            check("says: a chat card up leaves the answered hook its marker", os.path.isfile(os.path.join(jd, "review", es.MARK)))
            es.hook("answered")
            check("says: she answered in the chat: the card comes down, and the marker with it",
                  es.pending(jd) == [] and not os.path.exists(os.path.join(jd, "review", es.MARK)))
        finally:
            es.SERVER_STATE = old_state
    finally:
        httpd.shutdown()
        es.ROOT = real_root
    hook = os.path.join(os.path.dirname(PRODUCT), ".claude", "hooks", "editor-says.sh")
    for ev in ("ask", "answered"):
        r = subprocess.run(["bash", hook, ev], capture_output=True, text=True, encoding="utf-8", timeout=20)
        check(f"says: the {ev} hook is silent and never fails the chat", r.returncode == 0 and not r.stdout and not r.stderr, (r.returncode, r.stdout, r.stderr))
    for prompt, wants in (("can you open my Visual Editor?", True), ("edit my newest clip", False)):
        r = subprocess.run(["bash", hook, "answered"], capture_output=True, text=True, encoding="utf-8", timeout=20,
                           input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt}))
        check(f"says: asking for the visual editor puts the open-and-paste note in the chat ({prompt!r})",
              r.returncode == 0 and ("EDITOR LINK" in r.stdout) == wants and not r.stderr, (r.returncode, r.stdout, r.stderr))
    r = subprocess.run(["bash", hook, "answered"], capture_output=True, text=True, encoding="utf-8", timeout=20,
                       input=json.dumps({"hook_event_name": "PostToolUse", "tool_input": {"question": "try the visual editor?"}}))
    check("says: a question box that names the editor never triggers the note", r.returncode == 0 and not r.stdout, r.stdout)


def test_stretched_last_word():
    """A sentence's last word stamped far past her voice ("moment." 0.98 s) in a piece whose edge snapped to the real
    sound: its middle is outside the piece, but the piece plays it and her captions keep it. The page must show it kept,
    never struck through (2026-10-18, a tester's reel); a scrap under SLIVER of a dropped word stays cut."""
    words = [{"word": "the", "start": 0.0, "end": 0.1}, {"word": "moment.", "start": 0.12, "end": 1.1},
             {"word": "Yeah,", "start": 1.3, "end": 1.5}, {"word": "this", "start": 1.52, "end": 1.7}]
    jd = make_job("stretched", [seg(-0.04, 0.5), seg(1.48, 1.74)],
                  clips=[{"clip": "a.mov", "path": "", "duration": 2, "words": words}])
    _, _, seg_of, _, _, _ = model(jd)
    check("stretched stamp: a word the piece plays is kept", seg_of[1] == 0, seg_of)
    check("stretched stamp: a 20 ms scrap of a dropped word stays cut", seg_of[2] is None, seg_of)


def test_design_flags():
    """A design of hers can ask the captions to step aside (design.json hides_captions), and a design changed after
    it was drawn on a line is drawn again on the next Swap (2026-10-18, a tester's reel)."""
    import lookbook, time
    jd = os.path.join(TMP, "flags"); pack = "Butter"; look = "my-flag-test-zz"
    src = os.path.join(TMP, "flags-design"); os.makedirs(src, exist_ok=True)
    real = lookbook.design_dir
    lookbook.design_dir = lambda p, l: src
    try:
        page_dir = os.path.join(jd, "hf-graphics", "_looks", "add-w0", look, "hf-reel-type-butter")
        os.makedirs(page_dir, exist_ok=True)
        json.dump({"look": look, "pack": pack}, open(os.path.join(page_dir, "look.json"), "w", encoding="utf-8"))
        json.dump({"name": "x", "hides_captions": True}, open(os.path.join(src, "design.json"), "w", encoding="utf-8"))
        open(os.path.join(src, "index.html"), "w", encoding="utf-8").write("<p>x</p>")
        time.sleep(0.02)
        page = os.path.join(page_dir, "index.html"); open(page, "w", encoding="utf-8").write("<p>drawn</p>")
        l = {"dir": os.path.relpath(page_dir, jd), "look": look}
        check("flags: a design that asks hides the captions", ve._hides_captions(jd, l))
        check("flags: drawn after the design = not stale", not ve._design_newer(page))
        time.sleep(0.02); open(os.path.join(src, "index.html"), "w", encoding="utf-8").write("<p>y</p>")
        check("flags: design changed after drawing = drawn again", ve._design_newer(page))
        json.dump({"name": "x"}, open(os.path.join(src, "design.json"), "w", encoding="utf-8"))
        check("flags: no setting = captions stay (her rule)", not ve._hides_captions(jd, l))
        # a fingerprint beats file times: a page moved (rewritten) after the design changed is still stale
        json.dump({"look": look, "pack": pack, "design_sig": "old0000"}, open(os.path.join(page_dir, "look.json"), "w", encoding="utf-8"))
        time.sleep(0.02); open(page, "w", encoding="utf-8").write("<p>drawn, then moved</p>")
        check("flags: a page drawn from an older design is stale even after a move made it newer", ve._design_newer(page))
        json.dump({"look": look, "pack": pack, "design_sig": lookbook.design_sig(src)}, open(os.path.join(page_dir, "look.json"), "w", encoding="utf-8"))
        check("flags: a page drawn from this design is current", not ve._design_newer(page))
    finally:
        lookbook.design_dir = real


def test_caption_moves():
    """Her captions moved for one stretch only (a card sits where they do): that stretch replaces the scene spot, the
    rest keeps its own (2026-10-18, a tester reel: "captions on this need to be higher")."""
    jd = os.path.join(TMP, "capmoves"); os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    scenes = [[0.0, 4.0, 1100], [4.0, 16.0, 1197], [16.0, 20.0, 977]]
    check("caption moves: none = the scenes as they are", ve._with_caption_moves(jd, scenes) == scenes)
    json.dump({"moves": [[11.6, 16.35, 1036]]}, open(os.path.join(jd, "review", "caption-moves.json"), "w", encoding="utf-8"))
    got = ve._with_caption_moves(jd, scenes)
    check("caption moves: the stretch takes its spot, the scenes around it keep theirs",
          got == [[0.0, 4.0, 1100], [4.0, 11.6, 1197], [11.6, 16.35, 1036], [16.35, 20.0, 977]], got)


def test_open_without_a_reel():
    """"open my visual editor" / "show me the visual editor" with no reel named opens her most recent reel with a rough
    cut, and with none yet says how to get one (2026-10-20: buyers on v2.3.5 couldn't find the editor)."""
    real_root, real_open = ve.ROOT, ve.open_editor
    root = tempfile.mkdtemp(prefix="latest-")
    try:
        ve.ROOT = root
        msg = refuses("open, no reel: no rough cut yet is said", ve.latest_reel)
        check("open, no reel: the refusal hands her the phrase", "open my visual editor" in msg, msg)
        for name, t in (("older", 1000), ("newer", 2000), ("no-cut", 3000)):
            tr = os.path.join(root, "projects", name, "transcript"); os.makedirs(tr)
            json.dump({"clips": []}, open(os.path.join(tr, "words.json"), "w", encoding="utf-8"))
            if name != "no-cut":
                cp = os.path.join(tr, "cuts.json"); json.dump({"segments": []}, open(cp, "w", encoding="utf-8"))
                os.utime(cp, (t, t))
        check("open, no reel: her most recent reel with a rough cut", ve.latest_reel() == "newer", ve.latest_reel())
        opened = []
        ve.open_editor = lambda job, browser=True, autopilot=False: opened.append(job) or "http://127.0.0.1/editor/"
        real_argv = sys.argv
        try:
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):     # the address it prints is not test output
                sys.argv = ["visual_editor.py", "open", "--no-browser"]
                ve.main()
                sys.argv = ["visual_editor.py", "open", "older", "--no-browser"]
                ve.main()
        finally:
            sys.argv = real_argv
        check("open, no reel: the command line opens the newest, a named reel opens that one",
              opened == ["newer", "older"], opened)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                sys.argv = ["visual_editor.py", "open", "--no-browser"]
                ve.main()
        finally:
            sys.argv = real_argv
        check("open: prints the EDITOR LINK line every time, as a markdown link",
              "EDITOR LINK: [Open your visual editor](http://127.0.0.1/editor/)" in out.getvalue(), out.getvalue())
        ve.write_link_page("http://127.0.0.1:5123/editor/?job=newer")
        page = open(os.path.join(root, ve.LINK_PAGE), encoding="utf-8").read()
        check("open: writes the double-click page into the engine folder, pointing at her editor",
              '"http://127.0.0.1:5123/editor/?job=newer"' in page and '"http://127.0.0.1:5123/ping"' in page
              and "open my visual editor" in page, page[:300])
    finally:
        ve.ROOT, ve.open_editor = real_root, real_open
        shutil.rmtree(root, ignore_errors=True)
    src = open(ve.__file__, encoding="utf-8").read()
    check("the page server gets ~20s to start (a first start on Windows / Intel ran past 5s)", ve.SERVER_WAIT_S >= 15)
    check("on Windows the page server breaks away from Claude's command job, never DETACHED_PROCESS (console flashes)",
          "0x01000000" in src.split("def ensure_server", 1)[1].split("def latest_reel", 1)[0]
          and "0x00000008" not in src.split("def ensure_server", 1)[1].split("def latest_reel", 1)[0])
    check("the page-couldn't-start refusal hands her the phrase",
          "open my visual editor" in open(ve.__file__, encoding="utf-8").read().split("def ensure_server", 1)[1].split("def latest_reel", 1)[0])


def main():
    try:
        for t in (test_order, test_apply, test_speed_zoom, test_lines_keep_lock, test_lines_before_looks, test_pack_on_fresh_reel, test_task_queue, test_no_refusals, test_touching_words, test_kept_quiet, test_touching_pieces, test_long_stamp, test_refusals, test_code, test_save_and_apply, test_lock_kept_for_her, test_lean, test_stale_base, test_server, test_lock_and_names, test_page_flow, test_windows_bash, test_two_clips, test_trims, test_looks, test_build_lists_beat_stale_sheet, test_lookbook_and_swap, test_sweep_fixes, test_line_edits, test_measured_warnings, test_unlock_on_edit, test_designs, test_todo, test_review_mode, test_route_lock, test_older_reel_words, test_first_look_on_fresh_reel, test_sandbox, test_sandbox_names_and_quiet, test_lone_word_lines, test_nothing_lost, test_music_level_sticks, test_lead_in_words, test_her_default_pack, test_tour_and_fresh_stills, test_her_picks_stay, test_claude_says, test_stretched_last_word, test_design_flags, test_caption_moves, test_open_without_a_reel):
            t()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if fails:
        print(f"test_visual_editor: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_visual_editor: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
