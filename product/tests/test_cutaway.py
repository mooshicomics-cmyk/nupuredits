#!/usr/bin/env python3
"""Guards: a b-roll cutaway in the visual editor (the Media button with a video).

  picker    a video counts as media only from her favorites' broll drawer or her inbox; a .mov in graphics stays a
            see-through graphic, never a cutaway
  source    her clip is kept with the reel whole, upright, in her cut's frame, its own sound kept (so she can slip
            to any moment and turn its sound on)
  best      the engine's pick skips the clip's dark opening for the stretch that's actually usable
  span      a cutaway ends on a word and never runs longer than her clip
  draw      the page plays exactly the window it will export: full frame, muted unless she turned the sound on
  set       slip is clamped to the clip; start/end move it; too short or longer than the clip is refused; where she
            moved it stays
  export    cutaways stack right on her footage (under every card and her captions) and go in as footage; their
            sound, when on, is mixed into the MP4 even with no other sound on the reel

Run: python3 product/tests/test_cutaway.py
"""
import json, os, shutil, subprocess, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402
import finish  # noqa: E402

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


# picker: which files count as a cutaway
check(ve._media_kind("x.mov", "graphics") is None, "picker: a .mov in graphics must stay a graphic, never a cutaway")
check(ve._media_kind("x.mp4", "broll") == "Video", "picker: an .mp4 in broll is b-roll")
check(ve._media_kind("x.MOV", "inbox") == "Video", "picker: a .MOV in her inbox is b-roll")
check(ve._media_kind("x.gif", "gifs") == "GIF" and ve._media_kind("x.txt", "broll") is None, "picker: images keep their kinds")
check(ve._drawer_for(".mov") == "broll" and ve._drawer_for(".png") == "graphics", "picker: a dropped clip files into broll")

tmp = tempfile.mkdtemp(prefix="cutaway-")
real = (ve.job_dir, ve.place_look, ve._adds, ve._save_entry, ve._apply_nudge, ve.word_cut_times)
try:
    jd = os.path.join(tmp, "reel"); os.makedirs(os.path.join(jd, "outputs"))
    # her cut: 10 s, 1080x1920, a steady voice-level tone
    ff("-f", "lavfi", "-i", "color=c=gray:s=1080x1920:d=10:r=30", "-f", "lavfi", "-i", "sine=f=220:d=10",
       "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(jd, "outputs", "reel.mp4"))
    # her b-roll: a landscape phone clip, 2 s of black first (unusable), then 4 s of moving picture, with sound
    src = os.path.join(tmp, "coffee pour.mov")
    ff("-f", "lavfi", "-i", "color=c=black:s=1920x1080:d=2:r=30", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:d=4:r=30",
       "-f", "lavfi", "-i", "sine=f=880:d=6", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", src)

    # source: kept whole, in her cut's frame, sound kept
    rel = ve._cutaway_source(jd, "add-w1", src)
    kept = os.path.join(jd, rel)
    check(rel.startswith("assets/media/add-w1-") and os.path.isfile(kept), f"source: kept with the reel, got {rel}")
    check(probe(kept, "stream=width,height") == "1080,1920", f"source: filled to her cut's frame, got {probe(kept, 'stream=width,height')}")
    clip = ve._clip_len(kept)
    check(abs(clip - 6.0) < 0.15, f"source: the WHOLE clip is kept (to slip into), got {clip:.2f}s")
    check(bool(probe(kept, "stream=index", "a")), "source: her clip's own sound is kept, for when she turns it on")

    # best: never the black opening
    best = ve._best_slip(kept, 2.0, clip)
    check(1.8 <= best <= clip - 2.0 + 0.01, f"best: should skip the black opening, got slip {best}")
    check(ve._best_slip(kept, clip, clip) == 0.0, "best: a cutaway as long as the clip has nowhere to slip")

    # span: on a word, never longer than the clip
    words = {i: (i * 1.0, i * 1.0 + 0.6) for i in range(10)}
    ve.word_cut_times = lambda jd_: words
    s0, e0 = ve._cutaway_span(jd, 1.0, 9.6, 3.0)
    check(s0 == 1.0 and abs(e0 - 3.6) < 1e-6, f"span: ends on the last word that fits in a 3 s clip, got {s0}-{e0}")
    check(ve._cutaway_span(jd, 1.0, 2.6, 6.0) == (1.0, 2.6), "span: a stretch the clip covers stays as she placed it")

    # draw: exactly the window, muted by default
    look = os.path.join(jd, "hf-graphics", "_looks", "add-w1"); os.makedirs(look)
    rec = {"media": "broll/coffee pour.mov", "name": "coffee pour", "kind": "Video", "file": rel, "clip_dur": clip,
           "slip": 2.5, "best": best, "sound": False, "effect": "cut", "lead": 0.0}
    json.dump(rec, open(os.path.join(look, "media.json"), "w", encoding="utf-8"))
    r = ve._draw_media(jd, "add-w1", rec["media"], 1.6)
    page = os.path.join(jd, r["dir"]); win = os.path.join(page, "assets", "media.mp4")
    html = open(os.path.join(page, "index.html"), encoding="utf-8").read()
    check(abs(ve._clip_len(win) - 1.6) < 0.1, f"draw: the window is the cutaway's length, got {ve._clip_len(win):.2f}s")
    check(not probe(win, "stream=index", "a"), "draw: muted by default (no sound in the window)")
    check("object-fit:cover" in html and 'tl.set("#media",{autoAlpha:1},0)' in html and "drop-shadow" not in html,
          "draw: full frame, on with her word, no card styling")
    lj = json.load(open(os.path.join(page, "look.json"), encoding="utf-8"))
    check(lj.get("video") and lj.get("slip") == 2.5 and lj.get("box") == {"left": 0, "top": 0, "w": 1080, "h": 1920}, f"draw: look.json, got {lj}")
    check(ve.cutaway_file(jd, r["dir"]) == win, "draw: the export finds the cutaway's own clip")
    rec.update(slip=99, sound=True, effect="fade"); json.dump(rec, open(os.path.join(look, "media.json"), "w", encoding="utf-8"))
    ve._draw_media(jd, "add-w1", rec["media"], 1.6)
    lj = json.load(open(os.path.join(page, "look.json"), encoding="utf-8"))
    check(abs(lj["slip"] - (clip - 1.6)) < 0.01, f"draw: a slip past the clip's end is clamped, got {lj['slip']}")
    check(bool(probe(win, "stream=index", "a")) and lj.get("gain_db") is not None, "draw: sound on puts her clip's sound in, leveled")
    check("autoAlpha:0},{autoAlpha:1,duration:0.25" in open(os.path.join(page, "index.html"), encoding="utf-8").read(), "draw: fade fades")

    # set: slip, start/end, sound; refusals; nudge kept
    adds = {"add-w1": {"look": "media", "dir": r["dir"], "offset": 1.0, "dur": 1.6, "span": [1.0, 2.6], "nudge": [0, 40]}}
    placed = []
    ve.job_dir = lambda j: jd
    ve._adds = lambda jd_: adds
    ve.place_look = lambda job, key, s, e, lk: placed.append((key, s, e, lk)) or adds[key].update(nudge=None) or {}
    ve._save_entry = lambda jd_, k, e: adds.__setitem__(k, e)
    ve._apply_nudge = lambda *a: None
    out = ve.cutaway_set("reel", "add-w1", slip=1.0, sound=False, effect="cut")
    m = ve.media_of(jd, "add-w1")
    check(m["slip"] == 1.0 and m["sound"] is False and m["effect"] == "cut" and placed[-1] == ("add-w1", 1.0, 2.6, "media"),
          f"set: slip and sound saved, same place, got {m} {placed}")
    check(adds["add-w1"].get("nudge") == [0, 40], "set: where she moved it was lost")
    ve.cutaway_set("reel", "add-w1", start=0.0, end=3.6)
    check(placed[-1][1:3] == (0.0, 3.6) and ve.media_of(jd, "add-w1")["lead"] == -1.0,
          f"set: start a word earlier, end two words later, got {placed[-1]}")
    # her length, as near as her clip allows: never a refusal (2026-10-17), and it says what it did
    for what, kw, ok in (("too short", dict(start=1.0, end=1.3), lambda d: d >= ve.CUTAWAY_MIN - 0.01),
                         ("longer than the clip", dict(start=0.0, end=9.6), lambda d: d <= clip + 0.05)):
        try:
            got = ve.cutaway_set("reel", "add-w1", **kw)
            check(ok(placed[-1][2] - placed[-1][1]) and got.get("said"), f"set: {what} is made as near as it can be and said, got {placed[-1]} {got.get('said')}")
        except ve.Refuse as e:
            check(False, f"set: {what} was refused ({e}); her choice is made as near as it can be")
    try:
        ve.cutaway_set("reel", "add-w1", effect="spin"); check(False, "set: a cutaway only cuts or fades")
    except ve.Refuse:
        pass
    adds["add-w1"].update(offset=1.0, dur=1.6, span=[1.0, 2.6])
    ve.cutaway_set("reel", "add-w1", best=True)
    check(ve.media_of(jd, "add-w1")["slip"] >= 1.8, "set: Engine's pick goes back to the best moment for this length")

    # export: stacking and sound
    finish_doc = finish._looks_doc
    try:
        for d in ("a", "b", "c"):
            os.makedirs(os.path.join(jd, "L", d)); open(os.path.join(jd, "L", d, "index.html"), "w", encoding="utf-8").write("x")
        finish._looks_doc = lambda jd_: {"layers": [{"name": "card", "dir": "L/a", "offset": 0.5}, {"name": "cap", "dir": "L/b", "offset": 0, "captions": True},
                                                    {"name": "broll", "dir": "L/c", "offset": 1.0, "cutaway": {}}]}
        check([x[0] for x in finish.plan(jd)] == ["broll", "card", "cap"], f"export: b-roll right on her footage, got {[x[0] for x in finish.plan(jd)]}")
    finally:
        finish._looks_doc = finish_doc
    lay = os.path.join(tmp, "broll.mp4")
    finish._cutaway_out(jd, win, lay, None)
    check(os.path.isfile(lay) and finish._has_audio(lay), "export: the cutaway goes in as itself, sound and all")
    vid = os.path.join(tmp, "final.mp4"); shutil.copyfile(os.path.join(jd, "outputs", "reel.mp4"), vid)
    mixed = finish._mix_sound(os.path.join(tmp, "no-sound-plan"), vid, extra=[(lay, 1.0)])
    check(mixed and os.path.isfile(mixed) and abs(ve._clip_len(mixed) - 10.0) < 0.2,
          f"export: her b-roll's sound is mixed in even on a reel with no other sound, got {mixed}")
finally:
    ve.job_dir, ve.place_look, ve._adds, ve._save_entry, ve._apply_nudge, ve.word_cut_times = real
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_cutaway: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_cutaway: all {n} checks passed")
