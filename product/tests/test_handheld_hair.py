#!/usr/bin/env python3
"""A handheld take is measured where she really is, not 400px up in the ceiling.

The crown search compares each still with the room (what the stills agree on, pixel by pixel), which only works
while the room holds still. Handheld, the phone moves and the room moves with it, so the whole search band read as
"her" and the hair top came back as the top of the band: on a real handheld selfie, y150 for hair that starts
near y566, and every placement around her was judged against that. A room that slides as one piece is laid
back in place first (test_drifting_room_hair.py). One that will not hold together, because the phone walks and
the near and far parts of the room slide by different amounts, is caught on the strips beside the band where
only the room is: the hair is left unread, and subject-zones falls back to the face box plus a measured hair
allowance, saying so. A still room is read exactly as before.

Needs numpy (the engine's measuring tools run with it); the face detector and the frame grabs are stood in.

Run: python3 product/tests/test_handheld_hair.py   (Windows: python)
"""
import statistics, contextlib, importlib.util, io, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:200]})"))
    if not cond:
        fails.append(name)


try:
    import numpy as np
except ImportError:
    print("test_handheld_hair: skipped (numpy is not installed for this Python)")
    sys.exit(0)


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hf = load("head_framing_under_test", os.path.join("workflows", "head-framing.py"))
sz = load("subject_zones_under_test", os.path.join("workflows", "subject-zones.py"))

H, W = 960, 1080                                   # a reel's width: the room shows beside her head
rng = np.random.default_rng(7)
wall = rng.integers(0, 255, size=(H + 200, W + 200, 3)).astype(np.uint8)   # a busy room, bigger than the frame


def take(motion):
    """16 frames: a still figure in the middle, and a room that is still, slides as one piece ("pan"), or slides
    by different amounts near and far ("walk", the parallax of a phone carried through a room)."""
    frames = []
    for i in range(16):
        dx, dy = ((i * 37) % 180, (i * 23) % 180) if motion != "still" else (100, 100)
        f = wall[dy:dy + H, dx:dx + W].copy()
        if motion == "walk":
            nx, ny = (i * 71) % 180, (i * 53) % 180
            f[:, W // 2:] = wall[ny:ny + H, nx + W // 2:nx + W]      # the far side of the room, sliding its own way
        f[300:960, 440:640] = (90, 120, 200)          # her: head and shoulders, the same in every frame
        frames.append(f)
    return frames


print("1. is the room still?")
face = hf.Face(cx=540, cy=540, w=200, h=240, top=420)       # her face box inside the figure
check("a tripod take's room holds still", hf.room_unsteady(take("still"), face) is False)
check("a room that slides as one piece is laid back in place", hf.room_unsteady(take("pan"), face) is False)
check("a handheld walk's room moves", hf.room_unsteady(take("walk"), face) is True)

print("\n2. subject-zones on a handheld take")
tmp = tempfile.mkdtemp(prefix="handheld-hair-")
try:
    out = os.path.join(tmp, "job", "outputs")
    os.makedirs(out)
    video = os.path.join(out, "job.mp4")
    fz = sz.head_framing
    boxes = [(400.0, 500.0 + 20 * (i % 3), 280.0, 480.0) for i in range(16)]
    real = (fz.shown_size, fz.stills, fz.box_per_still, fz.crown_rows, fz.room_unsteady, fz.unread_stills)
    fz.unread_stills = lambda imgs, face: []
    fz.shown_size = lambda v: (1080, 1920, 10.0)
    fz.stills = lambda v, size, **k: ["frame"] * 16
    fz.box_per_still = lambda imgs: list(boxes)
    try:
        for label, moves, want_src, want_top in (
                ("handheld", True, "handheld", statistics.median(y - hf.HANDHELD_HAIR * bh for x, y, bw, bh in boxes)),
                ("hair unreadable on a still take", False, "hair unmeasurable", statistics.median(y for x, y, bw, bh in boxes))):
            fz.crown_rows = lambda imgs, face: []
            fz.room_unsteady = lambda imgs, face, _m=moves: _m
            with contextlib.redirect_stdout(io.StringIO()):
                rec = sz.measure(video)
            check(f"{label}: head top = {want_top:.0f}", rec["subject"]["head_top"] == round(want_top), rec["subject"])
            check(f"{label}: the reason is written down", want_src in rec["head_top_source"], rec["head_top_source"])
        fz.crown_rows = lambda imgs, face: [300] * 16
        fz.room_unsteady = lambda *a, **k: False
        with contextlib.redirect_stdout(io.StringIO()):
            rec = sz.measure(video)
        crown = round(300 - hf.CROWN_MARGIN * 480)     # the usual crown read, lifted by the margin (face 480 tall)
        check(f"a still take whose hair reads keeps the hair line: head top = {crown}", rec["subject"]["head_top"] == crown
              and "read against the room" in rec["head_top_source"], rec["subject"])
        with open(os.path.join(tmp, "job", "subject-zones.json"), encoding="utf-8") as fh:
            check("the whole-reel measurement is written", json.load(fh)["subject"]["head_top"] == crown)
        # A punch-in inside the take is left out of the hair search, and out of the box: the head top is where she
        # usually is (one odd frame never moves it), and the source says so.
        fz.unread_stills = lambda imgs, face: [3]
        fz.box_per_still = lambda imgs: boxes[:3] + [(400.0, 250.0, 280.0, 480.0)] + boxes[4:]
        with contextlib.redirect_stdout(io.StringIO()):
            rec = sz.measure(video)
        want = crown
        check(f"a frame from another shot is left out: head top = {want}", rec["subject"]["head_top"] == want,
              rec["subject"])
        check("the left-out frame is written down", "could not read" in rec["head_top_source"], rec["head_top_source"])
    finally:
        fz.shown_size, fz.stills, fz.box_per_still, fz.crown_rows, fz.room_unsteady, fz.unread_stills = real
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "a handheld take is measured where she is"))
sys.exit(1 if fails else 0)
