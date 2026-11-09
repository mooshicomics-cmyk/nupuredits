#!/usr/bin/env python3
"""Guards: her image can leave its own way, at her word ("slide out at the word revenue").

  exit      each exit leaves the frame (a slide clears the edge by its own width), "slide" picks the nearer side,
            fade fades; it starts 0.12s before the look's end, like the slide entrances
  fits      on a short stretch every entrance shrinks to land before the exit; a long stretch keeps it whole
  at        media_exit(at=<her word's time>) ends the look so the exit starts exactly as she says the word,
            keeps where she moved it, and remembers the exit in media.json; too soon after it comes in is refused

Run: python3 product/tests/test_media_exit.py
"""
import json, os, re, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


box = {"left": 334, "top": 1100, "w": 412, "h": 300}
r = ve._media_exit("slide-right", box, 1.6)
x = float(re.search(r"x:(-?\d+)", r).group(1))
check(box["left"] + x >= 1080, f"exit: slide-right should clear the right edge, got {r}")
check("1.480" in r, f"exit: should start 0.12s before the end, got {r}")
l = ve._media_exit("slide-left", box, 1.6)
check(box["left"] + box["w"] + float(re.search(r"x:(-?\d+)", l).group(1)) <= 0, f"exit: slide-left should clear the left edge, got {l}")
check("x:" in ve._media_exit("slide", box, 1.6, dx=60) and "-" not in re.search(r"x:(-?\d+)", ve._media_exit("slide", box, 1.6, dx=60)).group(1),
      "exit: slide from right of center should go out the right")
check(re.search(r"x:-", ve._media_exit("slide", box, 1.6, dx=-200)), "exit: slide from left of center should go out the left")
check("autoAlpha:0" in ve._media_exit("fade", box, 1.6), "exit: fade should fade")
check("y:-" in ve._media_exit("slide-up", box, 1.6), "exit: slide-up should go up")

# fits: on a short stretch every entrance lands before its exit starts (a 0.85s drop on a one-second GIF never showed)
for eff, _ in ve.MEDIA_EFFECTS:
    intro, outro = ve._media_moves(eff, box, 0.751)
    d = float(re.search(r"duration:([0-9.]+)", intro).group(1))
    leave = float(re.search(r",([0-9.]+)\);$", outro).group(1))
    check(0.08 + d < leave, f"fits: {eff} still arriving ({0.08 + d:.2f}s) when it starts leaving ({leave:.2f}s)")
check("duration:0.85" in ve._media_moves("drop", box, 3.0)[0], "fits: a long stretch keeps the full entrance")
# reveals: every entrance names autoAlpha in its destination too, or HyperFrames' check refuses the render (a cold
# render worker restores the hidden start and the picture can stay invisible); it stopped her CapCut export
for eff, _ in ve.MEDIA_EFFECTS:
    intro = ve._media_moves(eff, box, 3.0)[0]
    to = re.search(r'fromTo\("#media",\{[^}]*\},\{([^}]*)\}', intro)
    check(bool(to) and "autoAlpha:1" in to.group(1), f"reveals: {eff}'s entrance shows it in its destination")

tmp = tempfile.mkdtemp(prefix="media-exit-")
real = (ve.job_dir, ve.place_look, ve._adds, ve._save_entry, ve._apply_nudge)
try:
    jd = os.path.join(tmp, "reel"); os.makedirs(os.path.join(jd, "hf-graphics", "_looks", "add-w28"))
    json.dump({"media": "gifs/x.gif", "effect": "zoom"}, open(os.path.join(jd, "hf-graphics", "_looks", "add-w28", "media.json"), "w", encoding="utf-8"))
    adds = {"add-w28": {"look": "media", "dir": "d", "offset": 11.384, "dur": 3.512, "span": [11.504, 14.546], "nudge": [30, 103]}}
    placed = []
    ve.job_dir = lambda j: jd
    ve._adds = lambda jd_: adds
    ve.place_look = lambda job, key, s, e, look: placed.append((key, s, e, look)) or adds[key].update(nudge=None) or {}
    ve._save_entry = lambda jd_, k, e: adds.__setitem__(k, e)
    ve._apply_nudge = lambda *a: None
    ve.media_exit.__wrapped__("x", "add-w28", "slide", 12.891) if hasattr(ve.media_exit, "__wrapped__") else ve.media_exit("x", "add-w28", "slide", 12.891)
    check(placed and abs(placed[0][2] - 13.331) < 0.001 and placed[0][1] == 11.384, f"at: should keep its start and end the stretch so the exit starts at the word, got {placed}")
    check(json.load(open(os.path.join(jd, "hf-graphics", "_looks", "add-w28", "media.json"), encoding="utf-8"))["exit"] == "slide", "at: the exit isn't remembered")
    check(adds["add-w28"].get("nudge") == [30, 103], "at: where she moved it was lost")
    gone = adds.pop("add-w28"); placed.clear()
    try:
        ve.media_exit("x", "add-w28", "slide", 12.891); check(False, "at: an image whose place can't be read should be refused")
    except ve.Refuse:
        check(not placed, f"at: a refused exit must not move the image, got {placed}")
    adds["add-w28"] = gone
    try:                                                     # her moment, as close as it can be: never a refusal (2026-10-17)
        n0 = len(placed); ve.media_exit("x", "add-w28", "slide", 11.6)
        check(len(placed) > n0, "at: leaving right after it comes in is placed, as close to her moment as it can be")
    except ve.Refuse as e:
        check(False, f"at: leaving right after it comes in was refused ({e}); it should leave right after it lands")
finally:
    ve.job_dir, ve.place_look, ve._adds, ve._save_entry, ve._apply_nudge = real
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_media_exit: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_media_exit: all {n} checks passed")
