#!/usr/bin/env python3
"""A phone that drifts in front of window blinds still measures her hair where it starts, not at the blinds.

The crown search compares each still with the room (what the stills agree on, pixel by pixel). A phone on a couch arm or
in a hand drifts a few tens of px over a second or two. Beside her head there was only plain wall, which looks
the same wherever it lands, so the room read as still. Behind her head were blinds and a door jamb: every slat
and edge landed somewhere new in each frame, the median smeared them, and each one read as her. On a real take
the hair came back at the top of the search band, about 200px above where it starts (measured against a person
segmentation of the same clip), which reported no room above your head when there was plenty.

Now the frames are laid back onto the middle one, fitted on the room above her face, before the room is taken.
A still take skips that step and is measured exactly as before, and a frame that shows a different room (a
punch-in) is left out instead of being compared against a room it does not show.

Needs numpy and OpenCV (the engine's measuring tools run with both); the frames are drawn here.

Run: python3 product/tests/test_drifting_room_hair.py   (Windows: python)
"""
import importlib.util, os, sys

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
    import cv2
except ImportError:
    print("test_drifting_room_hair: skipped (numpy / OpenCV are not installed for this Python)")
    sys.exit(0)

spec = importlib.util.spec_from_file_location("head_framing_under_test",
                                              os.path.join(ROOT, "workflows", "head-framing.py"))
hf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hf)

H, W, PAD = 960, 1080, 60
HAIR, FACE_TOP, FACE_CX = 500, 620, 540          # her hair starts at y500; the face box begins at y620
FACE = hf.Face(cx=FACE_CX, cy=FACE_TOP + 120, w=200, h=240, top=FACE_TOP)


def room():
    """Plain wall, with blinds and a door jamb behind where her head will be. Bigger than the frame, so it can drift."""
    r = np.full((H + 2 * PAD, W + 2 * PAD, 3), 205, np.uint8)
    top, bottom, left, right = PAD + 140, PAD + 760, PAD + 260, PAD + 820
    r[top - 40:top, left - 14:right + 14] = 235                   # the header rail the slats hang from
    r[top - 42:top - 40, left - 14:right + 14] = 140
    for y in range(top, bottom, 22):
        r[y:y + 11, left:right] = 238                              # slats
        r[y + 11:y + 13, left:right] = 150                         # the shadow under each one
    for x in range(left + 70, right, 140):
        r[top:bottom, x:x + 3] = 120                               # the cords
    r[:, left - 14:left] = 110                                     # the jamb either side
    r[:, right:right + 14] = 110
    return r


def take(drift, punch_in=False):
    """16 frames of her swaying and bobbing (her hair never higher than HAIR), with the room sliding behind her
    by up to `drift` px."""
    rng = np.random.default_rng(3)
    r, frames = room(), []
    for i in range(16):
        dx, dy = round(PAD - drift / 2 + drift * i / 15), PAD - round(drift / 9 * i / 15)
        f = r[dy:dy + H, dx:dx + W].copy()
        if punch_in and i == 15:
            f = cv2.resize(f[96:H - 96, 108:W - 108], (W, H))     # a zoomed-in shot of the same room
        sway, bob = round(90 * np.sin(2 * np.pi * i / 16)), round(10 * (1 - np.cos(2 * np.pi * i / 16)))
        f[HAIR + bob:H, 440 + sway:640 + sway] = (60, 110, 190)    # her: hair, face, shoulders
        noise = rng.normal(0, 2, f.shape)
        frames.append(np.clip(f + noise, 0, 255).astype(np.uint8))
    return frames


def reads_her(tops, at_least):
    """Most frames found her, the highest at her hair line, and none of them above it."""
    return len(tops) >= at_least and abs(min(tops) - HAIR) <= 3 and max(tops) <= HAIR + 24


print("1. a still take is measured exactly as decoded")
still = take(0)
check("no drift, so the stills are not laid onto one another", hf._laid(still, FACE_TOP) is None)
tops = hf.crown_rows(still, FACE)
check(f"its hair reads at y{HAIR}", reads_her(tops, 12), tops)

print("\n2. a drifting phone in front of blinds")
drifting = take(36)
check("the room beside her head looks still (the plain wall hides the drift)",
      hf.room_unsteady(drifting, FACE) is False)
tops = hf.crown_rows(drifting, FACE)
check(f"her hair reads at y{HAIR}, and no frame reads it up in the blinds", reads_her(tops, 12), tops)

print("\n3. a punch-in inside the window")
punched = take(36, punch_in=True)
path = hf._laid(punched, FACE_TOP)
check("the zoomed frame is left out instead of laid onto a room it does not show",
      path is not None and path[0][15] is None and all(p is not None for p in path[0][:15]),
      None if path is None else [p is None for p in path[0]])
tops = hf.crown_rows(punched, FACE)
check(f"the rest still read her hair at y{HAIR}", reads_her(tops, 11), tops)
check("and it is named as unread, so a worst case can cover it another way",
      hf.unread_stills(punched, FACE) == [15], hf.unread_stills(punched, FACE))

print("\n4. the room changes right up to the top of the window (a lamp comes on above her)")
lit = take(0)
win_top = max(0, int(FACE_TOP - hf.CROWN_RISE * FACE.h))
lit[7][:HAIR, :] = np.clip(lit[7][:HAIR, :].astype(int) + 60, 0, 255).astype(np.uint8)
tops = hf.crown_rows(lit, FACE)
check(f"no frame reads her hair at the window's top (y{win_top})", min(tops) > win_top + hf.WINDOW_EDGE, tops)
check(f"the rest still read her hair at y{HAIR}", reads_her(tops, 12), tops)
check("the lit frame is named as unread", hf.unread_stills(lit, FACE) == [7], hf.unread_stills(lit, FACE))

print("\n" + ("FAILED: " + "; ".join(fails) if fails else f"all {total} checks passed: a drifting room is laid in place"))
sys.exit(1 if fails else 0)
