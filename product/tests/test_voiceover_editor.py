#!/usr/bin/env python3
"""Guards: a voiceover edited in the visual editor (her voice on Cut, her b-roll on Visuals).

  start     her recording becomes raw/vo.mp4: a black 9:16 picture exactly as long as her voice, her sound in it,
            the recording kept in audio/; a file with no sound, or a reel that already has footage, is refused
  pace      punchy or emotional only, saved for the cut
  folders   the Fill sheet lists her inbox folders that hold clips (one folder down too), never a hidden one
  fill      one clip after another from 0:00 to the end: no black between lines, a line too short for a clip of its
            own stays on the clip before it, a line with two clips splits on a word, a clip she put on herself is
            never covered, and what the last fill laid is taken off first (hers stay)
  gaps      a stretch with no clip is found (the Finish warning), a breath shorter than VO_GAP_MIN is not
  todo      her Fill request lands on Claude's list once, and leaves it when taken or done
  lines     numbered as her page numbers them
  head      a talking head: b-roll only on the lines she picked (picked lines in a row play as one stretch), a line
            she didn't pick refused, never marked a voiceover, no lines picked refused
  sound     a cut from one clip to the next gets no sound of its own on a voiceover (a Yap's cutaway still does)

Run: python3 product/tests/test_voiceover_editor.py
"""
import json, os, shutil, subprocess, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402
import sound_plan  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True, capture_output=True)


def probe(path, entries, stream="v:0"):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries, "-of", "csv=p=0", path],
                          capture_output=True, text=True).stdout.strip()


tmp = tempfile.mkdtemp(prefix="vo-editor-")
NAMES = ("ROOT", "job_dir", "vo_lines", "_cut_len", "media_path", "place_media", "cutaway_set", "swap", "looks_manifest",
         "_cutaway_spans", "word_cut_times", "_inbox_root", "media_of", "_fill_runs", "_cutaway_source", "_clip_len", "_best_moment")
real = {k: getattr(ve, k) for k in NAMES}
real_sp_job_dir, real_sp_all_looks = sound_plan.job_dir, sound_plan._all_looks
try:
    # ── start: her recording on a black picture ──────────────────────────────────────────────────────────────────
    ve.ROOT = tmp
    os.makedirs(os.path.join(tmp, "projects"))
    rec = os.path.join(tmp, "my voiceover.m4a")
    ff("-f", "lavfi", "-i", "sine=f=220:d=3.4", "-c:a", "aac", rec)
    d = ve.vo_start("kitchen-reset", rec, "emotional")
    jd = os.path.join(tmp, "projects", "kitchen-reset")
    raw = os.path.join(jd, "raw", "vo.mp4")
    check(os.path.isfile(raw) and os.path.isfile(os.path.join(jd, "audio", "vo.m4a")), "start: raw/vo.mp4 and her recording in audio/")
    check(probe(raw, "stream=width,height") == "1080,1920", f"start: a 9:16 picture, got {probe(raw, 'stream=width,height')}")
    check(abs(ve._clip_len(raw) - 3.4) < 0.1, f"start: as long as her voice, got {ve._clip_len(raw):.2f}s")
    check(bool(probe(raw, "stream=index", "a")), "start: her voice is in the clip the rough cut cuts")
    y = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", raw, "-frames:v", "1", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    check("YAVG" not in y or float(y.split("YAVG=")[-1].split()[0]) < 20, f"start: the picture is black, got {y[-80:]}")
    vo = ve.voiceover_of(jd)
    check(vo and vo.get("voiceover") and vo.get("pace") == "emotional" and vo.get("source") == "my voiceover.m4a", f"start: voiceover.json, got {vo}")
    mute = os.path.join(tmp, "silent.mp4")
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=1:r=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", mute)
    for what, args in (("no sound", ("another-one", mute)), ("not a reel name", ("../out", rec)), ("bad pace", ("third", rec, "loud"))):
        try:
            ve.vo_start(*args); check(False, f"start: {what} must be refused")
        except ve.Refuse:
            pass
    os.makedirs(os.path.join(tmp, "projects", "a-yap", "raw")); open(os.path.join(tmp, "projects", "a-yap", "raw", "IMG_1.mov"), "w", encoding="utf-8").close()
    try:
        ve.vo_start("a-yap", rec); check(False, "start: a reel with footage must never get a voiceover laid in it")
    except ve.Refuse:
        pass

    # ── pace ─────────────────────────────────────────────────────────────────────────────────────────────────────
    ve.job_dir = lambda j: jd
    check(ve.vo_pace("kitchen-reset", "punchy")["pace"] == "punchy", "pace: saved")
    try:
        ve.vo_pace("kitchen-reset", "slow"); check(False, "pace: only punchy or emotional")
    except ve.Refuse:
        pass

    # ── folders ──────────────────────────────────────────────────────────────────────────────────────────────────
    inbox = os.path.join(tmp, "inbox"); ve._inbox_root = lambda: os.path.realpath(inbox)
    for f in ("Kitchen/a.mp4", "Kitchen/grabs/b.mov", "Kitchen/deep/er/c.mp4", "Notes/n.txt", ".hidden/x.mp4", "loose.mp4"):
        os.makedirs(os.path.dirname(os.path.join(inbox, f)), exist_ok=True); open(os.path.join(inbox, f), "w", encoding="utf-8").close()
    fs = ve.footage_folders()
    check([f["id"] for f in fs] == ["Kitchen"] and fs[0]["clips"] == 2, f"folders: only folders with clips, one level down, got {fs}")
    check(sorted(c["id"] for c in ve._folder_clips("Kitchen")) == ["inbox:Kitchen/a.mp4", "inbox:Kitchen/grabs/b.mov"], "folders: her clips as Media ids")
    for bad in ("Notes", "../projects", "Gone"):
        try:
            ve._check_folder(bad); check(False, f"folders: {bad!r} must be refused")
        except ve.Refuse:
            pass

    # ── fill ─────────────────────────────────────────────────────────────────────────────────────────────────────
    ve.vo_lines = lambda jd_: [{"line": 1, "start": 0.1, "end": 2.0, "text": "one"}, {"line": 2, "start": 2.3, "end": 2.6, "text": "I read it."},
                               {"line": 3, "start": 2.8, "end": 7.9, "text": "a long line"}, {"line": 4, "start": 8.2, "end": 9.8, "text": "the end"}]
    ve._cut_len = lambda jd_: 10.0
    ve.word_cut_times = lambda jd_: {i: (2.8 + i * 0.5, 2.8 + i * 0.5 + 0.4) for i in range(11)}
    ve.media_path = lambda m: m
    hers = [(8.6, 9.2, "add-hers")]
    auto = {"add-old": {"auto": True}, "add-hers": {}}
    placed, slipped, removed = [], [], []
    ve._cutaway_spans = lambda jd_: [(0.0, 1.0, "add-old")] * ("add-old" in auto) + hers
    ve.media_of = lambda jd_, k: auto.get(k, {"file": f"assets/media/{k}.mp4"})

    def fake_place(job, s, e, media, made=None, slip=None, window=None):
        k = f"add-{len(placed)}"; placed.append((round(s, 3), round(e, 3), media, made, slip)); return {"layer": k}
    ve.place_media = fake_place
    converted = []
    ve._cutaway_source = lambda jd_, key, src, made=None, window=None: converted.append((src, window)) or f"assets/media/{key}-{src}.mp4"
    ve._clip_len = lambda src: 10.0
    ve._best_moment = lambda src, dur, clip, frames: 1.5

    def fake_runs(jd_, picks=None):                          # each line one word, runs split on lines she didn't tick
        runs, cur = [], []
        for l in ve.vo_lines(jd_):
            if picks is not None and l["line"] not in picks:
                if cur:
                    runs.append(cur); cur = []
                continue
            cur.append((l["line"], l["start"], l["end"], l["text"], l["line"]))
        return runs + ([cur] if cur else [])
    ve._fill_runs = fake_runs
    ve.cutaway_set = lambda job, k, slip=None: slipped.append((k, slip))
    ve.swap = lambda job, k, look: removed.append(k) or auto.pop(k, None)
    ve.looks_manifest = lambda jd_: None
    plan = {"fills": [{"line": 1, "clips": [{"media": "A"}]}, {"line": 2, "clips": [{"media": "B"}]},
                      {"line": 3, "clips": [{"media": "C", "slip": 4.0}, {"media": "A"}]}, {"line": 4, "media": "D"}]}
    out = ve.broll_fill("kitchen-reset", plan, log=lambda *a: None)
    spans = [(s, e) for s, e, _, _, _ in placed]
    check(removed == ["add-old"], f"fill: what the last fill laid comes off first, hers stays, got {removed}")
    check(spans[0][0] == 0.0, f"fill: the first clip starts at 0:00, got {spans}")
    check(all(abs(a[1] - b[0]) < 1e-6 for a, b in zip(spans, spans[1:3])), f"fill: one after another, no black between, got {spans}")
    check("B" not in [p[2] for p in placed] and spans[0][1] == 2.8, f"fill: a line too short for a clip of its own stays on the one before, got {placed}")
    check([p[2] for p in placed[1:3]] == ["C", "A"] and 2.8 < spans[1][1] < 7.9, f"fill: a line with two clips splits on a word, got {placed}")
    check(sorted(c[0] for c in converted) == ["A", "C", "D"] and placed[2][3] == placed[0][3],
          f"fill: each clip made once (all at once, before placing) and shared, got {converted} {placed}")
    check(placed[1][4] == 4.0 and placed[0][4] == 1.5 and not slipped,
          f"fill: her moment in the clip is set as it's placed (never drawn twice), the engine's pick otherwise, got {placed}")
    check(spans[2][1] == 8.6 and placed[-1][:3] == (9.2, 10.0, "D"),
          f"fill: around a clip she put on herself, never over it (the sliver before it stays on the clip it touches), got {placed}")
    check("gaps" in out, "fill: says what's still uncovered")

    # ── gaps ─────────────────────────────────────────────────────────────────────────────────────────────────────
    ve._cutaway_spans = lambda jd_: [(0.0, 3.0, "a"), (3.1, 6.0, "b"), (7.5, 9.0, "c")]
    check(ve.vo_gaps(jd) == [[6.0, 7.5], [9.0, 10.0]], f"gaps: the black stretches, not a 0.1 s breath, got {ve.vo_gaps(jd)}")

    # ── todo ─────────────────────────────────────────────────────────────────────────────────────────────────────
    ve.broll_fill_request("kitchen-reset", "Kitchen", "  kitchen   first ")
    req = json.load(open(os.path.join(jd, "review", "broll-fill.json"), encoding="utf-8"))
    check(req["folder"] == "Kitchen" and req["text"] == "kitchen first" and ve.voiceover_of(jd)["folder"] == "Kitchen", f"todo: her request, got {req}")
    items = [t for t in ve.todo("kitchen-reset") if t["kind"] == "broll-fill"]
    check(len(items) == 1 and "inbox/Kitchen" in items[0]["text"] and "kitchen first" in items[0]["text"], f"todo: on Claude's list, got {items}")
    ve.claim("kitchen-reset", items)
    check(not [t for t in ve.todo("kitchen-reset") if t["kind"] == "broll-fill"], "todo: taken = off the list (never handed over twice)")
    check(any(x["kind"] == "broll-fill" for x in ve.task_queue("kitchen-reset")["items"]), "todo: her page's queue shows it")

    # ── lines: numbered as her page numbers them (a line the engine cut still counts) ───────────────────────────
    yd = os.path.join(tmp, "projects", "a-yap"); os.makedirs(os.path.join(yd, "review"), exist_ok=True)
    json.dump({"lines": [[0, 1], [2], [3, 4]], "words": [{"t": w} for w in "so here it is now".split()]},
              open(os.path.join(yd, "review", "script.json"), "w", encoding="utf-8"))
    ve.word_cut_times = lambda jd_: {0: (0.0, 0.4), 1: (0.5, 0.9), 3: (1.0, 1.4), 4: (1.5, 1.9)}
    got = real["vo_lines"](yd)
    check([(l["line"], l["text"]) for l in got] == [(1, "so here"), (3, "is now")], f"lines: her page's numbers, got {got}")

    # ── a talking head: b-roll only on the lines she picked ─────────────────────────────────────────────────────
    ve.job_dir = lambda j: yd
    ve.vo_lines = lambda jd_: [{"line": 1, "start": 0.1, "end": 2.0, "text": "a"}, {"line": 2, "start": 2.3, "end": 4.0, "text": "b"},
                               {"line": 4, "start": 4.3, "end": 4.6, "text": "c"}, {"line": 5, "start": 5.0, "end": 7.0, "text": "d"},
                               {"line": 6, "start": 7.2, "end": 9.0, "text": "e"}]
    try:
        ve.broll_fill_request("a-yap", "Kitchen"); check(False, "head: no lines picked must be refused (her face would be gone)")
    except ve.Refuse:
        pass
    r = ve.broll_fill_request("a-yap", "Kitchen", lines=[2, "4", 5, 99, "x"])
    check(r.get("lines") == [2, 4, 5] and not ve.voiceover_of(yd), f"head: her picks kept, nothing made up, never marked a voiceover, got {r}")
    items = [t for t in ve.todo("a-yap") if t["kind"] == "broll-fill"]
    check(items and "lines 2, 4, 5 only" in items[0]["text"], f"head: Claude's list names her lines, got {items}")
    check(ve._fill_folder(yd) == "Kitchen", "head: Media lists her fill folder first")
    placed.clear(); slipped.clear(); hers.clear(); auto.clear()
    ve._cutaway_spans = lambda jd_: list(hers)
    try:
        ve.broll_fill("a-yap", {"fills": [{"line": 1, "media": "A"}]}, log=lambda *a: None); check(False, "head: a line she didn't pick must be refused")
    except ve.Refuse:
        pass
    out = ve.broll_fill("a-yap", {"fills": [{"line": 2, "media": "A"}, {"line": 4, "media": "B"}, {"line": 5, "media": "C"}]}, log=lambda *a: None)
    spans = [(s, e, m) for s, e, m, _, _ in placed]
    check(spans[0] == (2.3, 4.3, "A") and spans[1] == (4.3, 5.0, "B") and spans[2] == (5.0, 7.0, "C"),
          f"head: her picked lines in a row play as one stretch (line 3 was cut), and stop at her last pick, got {spans}")
    check(spans[0][0] > 2.0 and spans[-1][1] < 7.2 and out["gaps"] == [], f"head: her face stays on the lines she didn't pick, got {spans} {out['gaps']}")
    placed.clear()
    ve.broll_fill_request("a-yap", "Kitchen", lines=[4])
    ve.broll_fill("a-yap", {"fills": [{"line": 4, "media": "B"}]}, log=lambda *a: None)
    check([(s, e) for s, e, _, _, _ in placed] == [(4.3, 4.6)], f"head: a short line on its own still gets its clip, got {placed}")

    # ── beats: where one shot ends and the next begins (the cut rules) ──────────────────────────────────────────
    w = lambda i, s, e, t, ln: (i, s, e, t, ln)
    words = [w(0, 0.0, 0.3, "Do", 1), w(1, 0.35, 0.7, "you", 1), w(2, 0.75, 1.1, "know", 1), w(3, 1.15, 1.5, "my", 1),
             w(4, 1.55, 2.0, "secret?", 1), w(5, 2.4, 2.8, "I", 2), w(6, 2.85, 3.3, "cook", 2), w(7, 3.35, 3.7, "every", 2),
             w(8, 3.75, 4.2, "night.", 2), w(9, 4.6, 5.0, "Then", 3), w(10, 5.05, 5.5, "I", 3), w(11, 5.55, 6.0, "clean", 3),
             w(12, 6.05, 6.4, "the", 3), w(13, 6.45, 7.0, "whole", 3), w(14, 7.05, 7.6, "kitchen,", 3), w(15, 7.65, 8.0, "and", 3),
             w(16, 8.05, 8.6, "then", 4), w(17, 8.65, 9.2, "I", 4), w(18, 9.25, 9.9, "rest.", 4)]
    ve._fill_runs = lambda jd_, picks=None: [words]
    ve.job_dir = lambda j: jd
    json.dump({"voiceover": True, "pace": "punchy"}, open(os.path.join(jd, "voiceover.json"), "w", encoding="utf-8"))
    bs = ve.vo_beats(jd)
    check([b["hook"] for b in bs[:2]] == [True, True] and all(b["end"] - b["start"] < 1.2 for b in bs[:2]),
          f"beats: a voiceover opens on quick cuts, got {[(b['start'], b['end'], b['hook']) for b in bs]}")
    check(all(b["end"] - b["start"] >= ve.BEAT_MIN - 0.01 for b in bs if not b["hook"]), f"beats: no shot under the floor, got {bs}")
    check(all(b["end"] - b["start"] <= ve.BEAT_HOLD["punchy"][1] * 1.3 + 0.01 for b in bs), f"beats: no shot past the pace's hold, got {bs}")
    ends = [b["text"].split()[-1] for b in bs[:-1]]
    check(not any(ve._LEADS_ON.match(t) for t in ends), f"beats: never a cut right after a word that leads on, got {ends}")
    check(any(b["text"].endswith(("night.", "secret?", "kitchen,")) for b in bs), f"beats: cuts land on sentence ends and pauses, got {ends}")
    check(any(len(b["lines"]) > 1 for b in bs), f"beats: a shot can run across a line break, got {[b['lines'] for b in bs]}")
    json.dump({"voiceover": True, "pace": "emotional"}, open(os.path.join(jd, "voiceover.json"), "w", encoding="utf-8"))
    calm = [b for b in ve.vo_beats(jd) if not b["hook"]]
    check(len(calm) < len([b for b in bs if not b["hook"]]), f"beats: emotional holds longer (fewer shots), got {len(calm)}")
    check(ve._window_for(20.0, 5.0, 2.0) is None, "window: a short clip is kept whole")
    check(ve._window_for(117.0, 60.0, 2.0) == (54.0, 14.0) and ve._window_for(117.0, 2.0, 2.0) == (0.0, 10.0),
          f"window: a long clip keeps its moment plus room either side, got {ve._window_for(117.0, 60.0, 2.0)}")

    # ── sound: a clip change on a voiceover is an edit, not a motion ─────────────────────────────────────────────
    sound_plan.job_dir = lambda j: jd
    sound_plan._all_looks = lambda jd_: [{"name": "add-w1", "offset": 1.0, "dur": 2.0, "cutaway": {"slip": 0}}]
    check(sound_plan.moments("kitchen-reset") == [], "sound: no sound row for a clip change on a voiceover")
    os.remove(os.path.join(jd, "voiceover.json"))
    check(len(sound_plan.moments("kitchen-reset")) == 1, "sound: a Yap's cutaway still gets its sound row")
finally:
    for k, v in real.items():
        setattr(ve, k, v)
    sound_plan.job_dir, sound_plan._all_looks = real_sp_job_dir, real_sp_all_looks
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_voiceover_editor: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_voiceover_editor: all {n} checks passed")
