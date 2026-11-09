# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""
head-framing.py: where she is in the frame, measured from her footage, so nothing about her placement is typed
in by hand or copied from another job.

What reads it:
  - the 9:16 crop. A source that is not 1080x1920 (a 16:9 recording, a long video pull-reels works from) is
    cropped full height around her face first; pull-reels' cut-shorts.py reads that crop from head-framing.json.
  - placement around her. workflows/subject-zones.py (the head-to-chin box and the open zones every route places
    text in) and product/chin_lock.py load this file's detector rather than keeping their own.
  - zoom anchors (--windows / --range). A push-in scales about the frame centre, so each shot gets her face
    position for that shot, and the zoom closes in on her instead of the middle of the room.

How her head is found. Stills are taken evenly through the cut and YuNet (model in assets/models/) boxes her face
in each. The box stops at her brow; text placed off it would sit in her hair. So the crown is read separately:
the stills are brought to the reel's height, the room is what the stills agree on pixel by pixel (she moves, the
wall does not), and above her face, in a window sized from her own face box, the first row that holds an
unbroken stretch of her is the top of her head. Comparing against the room rather than hunting for an edge is
what keeps it working when her hair and the wall behind her are close in colour. A phone that drifts (in a hand,
on a couch arm) moves the room too, so the stills are first laid back onto one another using the room above her;
a selfie whose room swings past her is left unread (ROOM_MOVING_SHARE) and subject-zones allows HANDHELD_HAIR above
the box instead. Every figure is a median over the stills, so one take sitting a little differently does not move
it. Where each number comes from: dev-tools/framing/DERIVATION.md.

  measure   uv run workflows/head-framing.py projects/<job>/outputs/<job>.mp4
            her face, her hair line and any 9:16 crop, kept with the job in head-framing.json
  anchors   uv run workflows/head-framing.py <base-cut.mp4> --windows @projects/<job>/caption-plan.json \\
                --out projects/<job>/face-anchors.json
            uv run workflows/head-framing.py <base-cut.mp4> --range 4.3,6.1        (one window)
  --annotate OUT.PNG on measure also saves a frame with the measurement drawn onto it.
"""
import argparse, json, os, statistics, subprocess, sys
from pathlib import Path
from typing import NamedTuple
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ENGINE, "product"))
import probe as _probe                  # the engine's one way to ask a video its size (rotation applied)

# ---- the frame every number here is expressed in ---------------------------------------------------------
REEL_W, REEL_H = 1080, 1920
# How far her face centre may travel up and down across one cut, in heights of her own face, before the reading
# says so: past what 9 in 10 of her takes do (dev-tools/screen/DERIVATION.md). A share of her face rather than
# px, so a 4K cut and a 1080 one are held to the same thing.
DRIFT_SHARE = 1.5
# Stills read across a whole cut: the fewest whose medians (face centre, head top) land inside the clearance type
# keeps from her (safe_zones.MIN_PX["caption"], 58 px) of the cut's own median 19 times in 20, on 9 in 10 of her
# cuts, given how much each of her cuts moves from still to still.
STILLS = 15

# ---- the detector ---------------------------------------------------------------------------------------
YUNET = os.path.join(ENGINE, "assets", "models", "face_detection_yunet_2023mar.onnx")
# The detector's score floor: on her own takes, the floor that misses the fewest of her on-camera frames
# while taking the fewest boxes larger than hers that are not her (dev-tools/screen/DERIVATION.md).
YUNET_MIN_SCORE = 0.6

# ---- the top of her head -----------------------------------------------------------------------------------
# Read on stills brought to the reel's height (a larger source is scaled down to it), so a 4K cut and a 1080 one
# are read alike. Each number is measured on her own cuts against a portrait matte of the same stills.
CROWN_RISE = 0.91     # the window reaches this many face-box heights above the box top (her highest, steady takes)
CROWN_ACROSS = 1.13   # and this many face-box widths either side of the box centre (where the crown sits across)
APART = 24            # a pixel is her, not the room, once any one channel sits this far from the room
CROWN_RUN = 0.15      # a row is her head once it holds an unbroken stretch of her this share of the face width
CROWN_MARGIN = 0.02   # the head top sits this many face-box heights above the highest crown row read
WINDOW_EDGE = 1       # a crown found within this many rows of the window's top is the room changing, not her hair
# The room has to hold still for any of that. Handheld, the phone moves and the room moves with it, so the whole
# window "differs from the room" and the answer was the top of the window (a hair line 400px into the ceiling).
# Measured on real reels beside her head, above her face: tripod or propped takes change 0-1% of those pixels
# still to still, a handheld selfie 64%. Past this share the hair is left unread.
ROOM_MOVING_SHARE = 0.25
HANDHELD_HAIR = 0.25           # handheld: her hair starts this share of the face box's height above its top
                               # (0.22 measured by hand on a real handheld take; a little more for volume)
# A phone on a couch arm or in a hand drifts even when the take is not a selfie: tens of px over a second or
# two. A plain wall looks the same wherever it lands, so the check above sees a still room, but every edge in
# it (blind slats, a door frame, a window) sits somewhere new in each still. The room smears those edges and
# each one reads as her: measured on a real take in front of window blinds, the hair came back at the top of
# the window, 200px above where it starts. So before the room is taken, every still is laid back onto one
# reference still, using only the room ABOVE her face: that is the part the crown search compares, and it is
# mostly one wall, whereas the couch in front of it sits nearer the phone and slides by a different amount (fit
# to the whole frame, the couch won and left a door jamb 20px off). A still that will not lay onto that room
# (a punch-in, another shot) is left out rather than compared against a room it does not show.
ALIGN_WIDTH = 540              # stills are matched at this width: the room's edges survive it, and it is quick
ALIGN_MIN_ROWS = 24            # rows of room above her face (at that width) needed before a fit is attempted
ALIGN_EDGE = 80                # Sobel strength (a step of ~20 grey levels) that makes a pixel one of the room's edges
ALIGN_MIN_EDGES = 200          # fewer edges than this above her and there is nothing a drift could smear: no fit
ALIGN_AGREE = 0.80             # share of those edges a laid still must line up with to count as the same room
                               # (product/tests/test_drifting_room_hair.py: drifting stills do, a punch-in does not)
ALIGN_STILL = 10.0             # source px: when no laid still moved more than this, the stills are used as decoded.
                               # Measured: tripod takes fit to 0-5 (her hair drags a still fit a few px), a
                               # drifting handheld take to 29-35. Below this the reading is the plain one.


# ---------------------------------------------------------------------------------------------------------
# READING THE CUT

def shown_size(video):
    """(width, height, seconds) of the cut as it DISPLAYS: a phone filmed upright is often stored 1920x1080 with a
    rotation tag, and ffmpeg hands every decoded frame over the right way up. Read through product/probe.py. The
    seconds are the picture's own: a cut's sound can run on past its last frame, and a still asked for there
    decodes nothing (the file's length stands in when the stream does not give one). Exits with a plain line when
    the file is missing or is not a video ffprobe can read."""
    if not os.path.isfile(video):
        sys.exit(f"[head-framing] no such file: {video}")
    got = _probe.probe(video)
    if not got["width"] or not got["height"]:
        sys.exit(f"[head-framing] no video stream in {video}")
    seconds = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=duration", "-of", "default=nw=1:nk=1", video],
                             capture_output=True, text=True).stdout.strip()
    try:
        seconds = float(seconds)
    except ValueError:
        seconds = got["duration"]
    return got["width"], got["height"], seconds


probe = shown_size                     # the name cover-frame.py and product/chin_lock.py call it by


def still_at(video, at, w, h):
    """The frame shown at `at` seconds, as a BGR array straight off ffmpeg's pipe, or None past the end."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", video, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(raw) != w * h * 3:
        return None
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def stills(video, size, count=None, start=None, end=None):
    """`count` stills (STILLS by default) spread evenly over [start, end] of the video (the whole of it when no
    stretch is given, or when the stretch is empty or backwards). They split the stretch into count + 1 equal
    gaps, so neither its first nor its last frame is read: a cut's ends are where a fade or a stray frame sits.
    A time ffmpeg cannot decode is skipped, so fewer can come back. `size` is shown_size()'s answer."""
    w, h, seconds = size
    count = count or STILLS
    lo = 0.0 if start is None else max(0.0, float(start))
    hi = seconds if end is None else min(seconds, float(end))
    if not hi > lo:
        lo, hi = 0.0, seconds
    got = (still_at(video, lo + (hi - lo) * (k + 1) / (count + 1), w, h) for k in range(count))
    return [s for s in got if s is not None]


# ---------------------------------------------------------------------------------------------------------
# HER FACE

class Face(NamedTuple):
    """One face box standing for a run of stills: centre, size and top, each the median of the boxes (the top can
    be set to the highest instead, for a worst case)."""
    cx: float
    cy: float
    w: float
    h: float
    top: float


def box_per_still(frames):
    """For each still, her face box as float (x, y, w, h) in that still's px, or None where YuNet finds no face.
    Index for index with the stills.

    She is the one nearest the phone, so the largest box stands for her first. A still where YuNet finds more
    than one face then keeps the box nearest her typical face across the take (size and place), not simply the
    largest: a false "face" on her hands or shirt can come out bigger than her own, and the largest one once
    stretched a buyer's measured head from her hair to her forearms."""
    import cv2, math
    if not frames:
        return []
    h, w = frames[0].shape[:2]
    yunet = cv2.FaceDetectorYN_create(YUNET, "", (w, h), score_threshold=YUNET_MIN_SCORE)
    found_per = []
    for frame in frames:
        found = yunet.detect(frame)[1]
        found_per.append([tuple(float(v) for v in d[:4]) for d in found] if found is not None and len(found) else [])
    largest = [max(f, key=lambda b: b[2] * b[3]) if f else None for f in found_per]
    seen = [b for b in largest if b is not None]
    if not seen:
        return largest
    face = typical_face(seen)

    def off(b):   # how far a box is from her typical face: size ratio plus distance, in her own face sizes
        x, y, bw, bh = b
        return (abs(math.log(max(bh, 1.0) / max(face.h, 1.0)))
                + abs(x + bw / 2 - face.cx) / max(face.w, 1.0) + abs(y + bh / 2 - face.cy) / max(face.h, 1.0))
    return [min(f, key=off) if len(f) > 1 else (f[0] if f else None) for f in found_per]


def her_boxes(frames):
    """The face boxes of the stills that show one (box_per_still without the misses)."""
    return [b for b in box_per_still(frames) if b is not None]


def typical_face(boxes):
    """The Face standing for these boxes."""
    mid = statistics.median
    return Face(cx=mid(x + bw / 2 for x, _y, bw, _bh in boxes), cy=mid(y + bh / 2 for _x, y, _bw, bh in boxes),
                w=mid(bw for _x, _y, bw, _bh in boxes), h=mid(bh for _x, _y, _bw, bh in boxes),
                top=mid(y for _x, y, _bw, _bh in boxes))


def face_reading(boxes, frames_read):
    """Her face across a cut, from the boxes the detector found -> a dict, or None when too few stills show
    her for any of it to be trusted (fewer than half of those read). Position and size are medians, so one
    take sitting differently does not move them. `travel` is how far the face centre went up and down
    between the highest and lowest stills, in px and as a share of her face's height, which is the same
    whatever the source size."""
    if not boxes or len(boxes) * 2 < frames_read:
        return None
    face = typical_face(boxes)
    centres = sorted(y + bh / 2 for _x, y, _bw, bh in boxes)
    travel = centres[-1] - centres[0]
    return {"centre": [round(face.cx), round(face.cy)], "size": [round(face.w), round(face.h)], "top": face.top,
            "face": face, "travel_px": round(travel), "travel_share": round(travel / face.h, 3) if face.h else 0.0,
            "seen_in": [len(boxes), frames_read]}


# ---------------------------------------------------------------------------------------------------------
# THE TOP OF HER HEAD

def crown_rows(frames, face):
    """Per still, the row (in the stills' own px) where the top of her head is: the first row of the window above
    her face that holds an unbroken stretch of her CROWN_RUN of a face wide. A still where no row does adds
    nothing, nor does one whose stretch is the window's own top row (something in the room changed there, so the
    reading says nothing about her hair; unread_stills() names it). Nothing comes back at all when the room will
    not hold still (see ROOM_MOVING_SHARE). `face` is a Face in the stills' px; its top is where the window ends."""
    look = _look(frames, face)
    if look["unsteady"]:
        return []
    return [row for row in _rows(look) if row is not None and row != "top"]


def _rows(look):
    """Per still: its crown row in the stills' px, None (no row, or another shot) or "top" (the window's top row)."""
    left, right, top, bottom = look["window"]
    need = max(1, round(CROWN_RUN * look["face_w"] * look["k"]))
    out = []
    for apart in look["apart"]:
        row = None if apart is None else _first_stretch(apart[top:bottom, left:right], need)
        out.append(None if row is None else "top" if row <= WINDOW_EDGE else (top + row) / look["k"])
    return out


def room_unsteady(frames, face):
    """The test crown_rows() applies before reading anything, for a caller that needs to say WHY the hair went
    unread."""
    return _look(frames, face)["unsteady"]


def unread_stills(frames, face):
    """Indices of the stills crown_rows() could not read her hair in: another shot (a punch-in, a cut to another
    take, whose room is not the one compared) or a reading stopped at the window's top row. A caller taking the
    worst case over the take has to cover them some other way. Asks the comparison crown_rows() just made."""
    look = _look(frames, face)
    return [i for i, (apart, row) in enumerate(zip(look["apart"], _rows(look))) if apart is None or row == "top"]


def hair_line(frames, face):
    """The median crown row, or None when fewer than half the stills showed one."""
    rows = crown_rows(frames, face)
    return statistics.median(rows) if len(rows) >= len(frames) / 2 else None


def _first_stretch(window, need):
    """Index of the first row of a bool window holding a run of True at least `need` long, or None."""
    import numpy as np
    if window.size == 0:
        return None
    edges = np.diff(np.pad(window.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    for r in np.flatnonzero(window.sum(axis=1) >= need):
        starts, stops = np.flatnonzero(edges[r] == 1), np.flatnonzero(edges[r] == -1)
        if (stops - starts).max() >= need:
            return int(r)
    return None


_LOOKED = {}                           # the last comparison made: crown_rows() and its helpers ask back to back


def _look(frames, face):
    """Everything the crown search needs about these stills, worked out once: the scale k that brings them to the
    reel's height (never up), the window above her face in those px, a bool map per still of where it is apart
    from the room (None for a still from another shot), and whether the room itself moves."""
    import cv2
    key = (id(frames), len(frames), tuple(face))
    if _LOOKED.get("key") == key and _LOOKED.get("frames") is frames:
        return _LOOKED["look"]
    h, w = frames[0].shape[:2]
    k = min(1.0, REEL_H / h)
    work = frames if k == 1.0 else [cv2.resize(f, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
                                    for f in frames]
    wh, ww = work[0].shape[:2]
    top = int(face.top * k)
    window = (max(0, int((face.cx - CROWN_ACROSS * face.w) * k)), min(ww, int((face.cx + CROWN_ACROSS * face.w) * k)),
              max(0, int((face.top - CROWN_RISE * face.h) * k)), max(0, min(wh, top)))
    apart = _apart_from_room(work, top, k)
    look = {"k": k, "window": window, "face_w": face.w, "apart": apart, "unsteady": _unsteady(apart, *window)}
    _LOOKED.clear()
    _LOOKED.update(key=key, frames=frames, look=look)
    return look


def _apart_from_room(work, face_top, k=1.0):
    """Per still, an HxW bool map of where it is APART from the empty room, or None for a still that does not show
    that room (see _laid). The room is the per-pixel median of the stills; when the phone drifted, or a punch-in
    or another shot is mixed in, it is taken over the stills laid onto the reference (a sharp room rather than a
    smeared one) and laid back onto each still before comparing, so every answer stays in that still's own px,
    beside the face found there. The strip along the frame edge some stills never saw is not judged."""
    import cv2, numpy as np
    path = _laid(work, face_top, k)
    if path is None:
        room = np.median(np.stack([f.astype(np.float32) for f in work]), axis=0)
        return [np.abs(f.astype(np.float32) - room).max(axis=2) >= APART for f in work]
    lays, most = path
    h, w = work[0].shape[:2]
    room = np.median(np.stack([cv2.warpAffine(f, lay, (w, h), flags=cv2.INTER_LINEAR,
                                              borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
                               for f, lay in zip(work, lays) if lay is not None]), axis=0)
    rim = int(np.ceil(most)) + 2
    out = []
    for f, lay in zip(work, lays):
        if lay is None:
            out.append(None)           # not the same room: nothing to compare it against
            continue
        back = cv2.warpAffine(room, cv2.invertAffineTransform(lay), (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
        apart = np.abs(f.astype(np.float32) - back).max(axis=2) >= APART
        apart[:rim], apart[-rim:], apart[:, :rim], apart[:, -rim:] = False, False, False, False
        out.append(apart)
    return out


def _unsteady(apart, left, right, top, bottom):
    """True when the room itself still changes from still to still (a handheld selfie, where the room swings past
    her and cannot be laid in place), judged on the strips beside the crown window, where only the room is. With
    no strip to judge by, the room is taken as still. When most stills could not be laid onto the room at all,
    it moves too."""
    import numpy as np
    seen = [a for a in apart if a is not None]
    if len(seen) < len(apart) / 2:
        return True
    if bottom <= top or (left <= 0 and right >= seen[0].shape[1]):
        return False
    shares = []
    for a in seen:
        beside = np.concatenate([a[top:bottom, :left].ravel(), a[top:bottom, right:].ravel()])
        if beside.size:
            shares.append(float(beside.mean()))
    return bool(shares) and statistics.median(shares) > ROOM_MOVING_SHARE


def _laid(work, face_top, k=1.0):
    """Per still, the 2x3 transform (in these stills' px) that lays it onto a reference still from the shot most of
    them show, or None for a still from another shot (a punch-in, a cut to another take); and the most any laid
    still moved. The whole answer is None when no laid still moved more than ALIGN_STILL, or when the room above
    her has no edges for a drift to smear: the stills are then compared exactly as decoded.

    Fitted on the room above face_top only, densely (every pixel votes, not a few corners: a plain wall and a run
    of identical slats give a corner matcher almost nothing to hold on to). A phase correlation finds the slide
    and ECC refines it into a move and turn. Whether the still really shows the same room is judged on the room's
    edges, the share of them that line up once it is laid in place, rather than on ECC's own score: that is a
    correlation, which her head swaying through the top of the fit can drag below what a genuinely different
    shot scores. A laid pixel lines up when it lands within one plate pixel of where the reference has it: its grey
    residue is under the change the reference makes across one pixel there (Sobel's response is 8 times that), and
    never less than the weakest edge's (ALIGN_EDGE). `k` is the scale the stills were brought to, so ALIGN_STILL
    keeps its source px."""
    import cv2, numpy as np
    h, w = work[0].shape[:2]
    bottom = min(h, int(face_top))
    s = min(1.0, ALIGN_WIDTH / w)
    if bottom * s < ALIGN_MIN_ROWS:
        return None                    # too little room above her to fit anything to: read the stills as decoded

    def plate(f):
        grey = cv2.cvtColor(f[:bottom], cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(cv2.resize(grey, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                                .astype(np.float32), (0, 0), 1.0)

    def back(p, seen):
        return cv2.warpAffine(p, seen, (p.shape[1], p.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)

    plates = [plate(f) for f in work]
    stop = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
    grow = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    to_plate = np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]])
    corners = np.float32([[0, 0], [w, 0], [0, h], [w, h]])

    def lay_onto(ref):
        """Every still laid onto `ref` (None where it will not lie there), and the most any of them moved. None
        when the room above her has too few edges for a drift to smear."""
        strength = np.hypot(cv2.Sobel(ref, cv2.CV_32F, 1, 0), cv2.Sobel(ref, cv2.CV_32F, 0, 1))
        edges = strength > ALIGN_EDGE
        within = np.maximum(strength, ALIGN_EDGE) / 8                 # grey change over one plate px (Sobel = 8x)
        rim = max(8, int(np.ceil(40 * s)))                            # the rim a drift of ~40px pulls in from outside
        edges[:rim], edges[-rim:], edges[:, :rim], edges[:, -rim:] = False, False, False, False
        if np.count_nonzero(edges) < ALIGN_MIN_EDGES:
            return None
        hann = cv2.createHanningWindow((ref.shape[1], ref.shape[0]), cv2.CV_32F)
        path, most = [], 0.0
        for p in plates:
            (dx, dy), _ = cv2.phaseCorrelate(ref, p, hann)
            seen = np.float32([[1, 0, dx], [0, 1, dy]])               # where the reference's room sits in this still
            try:
                seen = cv2.findTransformECC(ref, p, seen, cv2.MOTION_EUCLIDEAN, stop, None, 5)[1]
                # Once more, leaving out whatever did not line up: her, mostly. A head swaying through the top
                # of the fit otherwise drags the answer a px or two toward wherever she went.
                off = cv2.dilate((np.abs(ref - back(p, seen)) >= within).astype(np.uint8), grow)
                use = cv2.warpAffine(1 - off, seen, (p.shape[1], p.shape[0]), flags=cv2.INTER_NEAREST,
                                     borderValue=1)
                seen = cv2.findTransformECC(ref, p, seen, cv2.MOTION_EUCLIDEAN, stop, use, 5)[1]
                agree = float((np.abs(ref - back(p, seen)) < within)[edges].mean())
            except cv2.error:
                agree = 0.0                                           # ECC gave up: not the same room
            if agree < ALIGN_AGREE:
                path.append(None)
                continue
            seen_full = np.linalg.inv(to_plate) @ np.vstack([seen, [0, 0, 1]]) @ to_plate
            lay = np.linalg.inv(seen_full)[:2].astype(np.float32)
            most = max(most, float(np.abs(corners @ lay[:, :2].T + lay[:, 2] - corners).max()))
            path.append(lay)
        return path, most

    # The room is whichever shot most of the stills show. The middle one usually does, but a window that crosses
    # a cut or a punch-in can put it in the minority, so the quarter points get a turn before the room is called
    # one that will not hold still.
    n, fit = len(plates), None
    for pick in dict.fromkeys((n // 2, n // 4, (3 * n) // 4)):
        fit = lay_onto(plates[pick]) or fit
        if fit and sum(lay is not None for lay in fit[0]) >= n / 2:
            break
    if fit is None:
        return None                    # no edges above her in any of them: nothing a drift could smear
    path, most = fit
    if most / k <= ALIGN_STILL:
        # The phone held still, so the stills are compared exactly as decoded, every one of them. A still the fit
        # would not lay in place is NOT left out here: against a plain or blurred room her own hair holds most of
        # the edges, and a still where she only sits higher reads as "another shot" when it is not.
        return None
    return path, most


# ---------------------------------------------------------------------------------------------------------
# MEASURE: the whole cut, for the 9:16 crop and placement around her

def _even(v):
    return round(v / 2) * 2


def reel_window(w, h, face_x):
    """Where a source that is not 1080x1920 is cut down to the reel's 9:16 first -> {"window": [x, y, w, h] in
    source px, "ffmpeg": the filter that does it}. Full height, 9:16 wide (kept even), centred on her face and
    slid back inside the frame at an edge. pull-reels' cut-shorts.py runs the "ffmpeg" filter as written."""
    cw = _even(h * 9 / 16)
    x = max(0, min(w - cw, round(face_x - cw / 2)))
    return {"window": [x, 0, cw, h], "ffmpeg": f"crop={cw}:{h}:{x}:0,scale={REEL_W}:{REEL_H}"}


def _header(video, w, h):
    """What every JSON written here opens with: which cut was read, and its size as it plays."""
    return {"cut": str(Path(video).resolve()), "size": [w, h]}


def _job_folder(video):
    """The job a base cut belongs to (projects/<job>/outputs/<job>.mp4 -> projects/<job>), else None."""
    home = Path(video).resolve().parent
    return home.parent if home.name == "outputs" else None


def _say(line):
    print(f"[head-framing] {line}")


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
    print(f"wrote {path}")


def measure(video, annotate=None):
    """Her face, her hair line and (for a source that is not already 1080x1920) the 9:16 window, measured
    across the whole cut. The answer is head-framing.json next to the job when the cut is a job's base cut
    (projects/<job>/outputs/<job>.mp4); it is returned either way."""
    size = shown_size(video)
    w, h, dur = size
    frames = stills(video, size)
    boxes = her_boxes(frames)
    face = face_reading(boxes, len(frames))
    _say(f"{os.path.basename(video)}: {w}x{h}, {dur:.1f} s, her face in {len(boxes)} of {len(frames)} stills read")
    if face is None:
        _say("too few stills show her face to place anything from them, so nothing is written. "
             "Frame this cut by eye, or measure a stretch where she is on camera.")
        sys.exit(1)
    _say(f"face centre x{face['centre'][0]} y{face['centre'][1]}, {face['size'][0]}x{face['size'][1]} px, "
         f"up and down by {face['travel_px']} px ({face['travel_share']:.2f} of her face height)")
    if face["travel_share"] > DRIFT_SHARE:
        _say(f"note: she moves up and down more across this cut than in nearly all of her takes (past "
             f"{DRIFT_SHARE:g} of her face height), so one placement may not suit every take. Look over each "
             f"take in the draft.")

    record = _header(video, w, h)
    record["her_face"] = {k: face[k] for k in ("centre", "size", "travel_px", "travel_share", "seen_in")}
    # The crown is read in the source's own pixels, beside the face found there; the record carries it in the
    # 1080x1920 reel frame, which is the full-height window scaled to 1920 tall when a crop comes first.
    hair_here = hair_line(frames, face["face"])
    if (w, h) != (REEL_W, REEL_H):
        record["reframe"] = reel_window(w, h, face["centre"][0])
        _say(f"not a 1080x1920 cut, so the reel takes this window of it first: {record['reframe']['ffmpeg']}")
    if hair_here is None:
        _say("hair line: not readable here (a hood, a hat, or a handheld take); the face box stands for her head")
    else:
        record["hair_top"] = round(hair_here * REEL_H / h)
        _say(f"hair line: y{record['hair_top']} in the reel frame")

    job = _job_folder(video)
    if job is not None:                               # a job's base cut: the answer lives with the job
        _write_json(job / "head-framing.json", record)
    if annotate:
        her = (face["centre"][0] - face["size"][0] / 2, face["centre"][1] - face["size"][1] / 2,
               face["centre"][0] + face["size"][0] / 2, face["centre"][1] + face["size"][1] / 2)
        mark_up(frames[len(frames) // 2], annotate, her=her, hair_y=hair_here)
    return record


# How the readings are drawn for a check by eye (--annotate here and in subject-zones.py): the platform's
# bands from product/safe_zones.py veiled in grey when the frame is 9:16, her measured box and hair line in
# magenta, and any open band tinted green with its name. Colours are BGR.
_HER = (255, 0, 255)
_OPEN = (80, 200, 80)


def mark_up(img, path, her=None, hair_y=None, open_bands=(), tag="head-framing"):
    """Draw a reading onto one source frame and save it to path. `her` is (x0, y0, x1, y1) and `hair_y` a row,
    both in that frame's own pixels; `open_bands` is [(name, x0, y0, x1, y1)] in the same pixels."""
    import cv2
    import safe_zones
    out = img.copy()
    hh, ww = out.shape[:2]
    if abs(ww / hh - safe_zones.W / safe_zones.H) < 1e-3:
        k = hh / safe_zones.H
        veil = out.copy()
        for y0, y1 in ((0, safe_zones.TOP * k), (safe_zones.BOTTOM * k, hh)):
            cv2.rectangle(veil, (0, int(y0)), (ww, int(y1)), (128, 128, 128), -1)
        out = cv2.addWeighted(veil, 0.45, out, 0.55, 0)
    for name, x0, y0, x1, y1 in open_bands:
        tint = out.copy()
        cv2.rectangle(tint, (int(x0), int(y0)), (int(x1), int(y1)), _OPEN, -1)
        out = cv2.addWeighted(tint, 0.30, out, 0.70, 0)
        cv2.putText(out, name, (int(x0) + 10, int(y0) + 40), cv2.FONT_HERSHEY_DUPLEX, 1.1, _OPEN, 2)
    if her is not None:
        cv2.rectangle(out, (int(her[0]), int(her[1])), (int(her[2]), int(her[3])), _HER, 4)
    if hair_y is not None:
        for x in range(0, ww, 40):                    # dashed, so it reads as a line across the frame
            cv2.line(out, (x, int(hair_y)), (min(ww, x + 24), int(hair_y)), _HER, 4)
    cv2.imwrite(path, out)
    print(f"[{tag}] drawn on a frame: {path}")


# ---------------------------------------------------------------------------------------------------------
# PER-SHOT ZOOM ANCHORS: so a push-in closes on her
#
# A zoom scales about the FRAME CENTER. When she does not sit dead center, a centre-anchored
# push-in enlarges the middle of the room and slides her toward the edge — the "it zoomed off to the
# side" bug. The motion planners therefore need the face position IN THE SHOT BEING ZOOMED, not one
# median for the whole cut: she re-frames between takes (measured on the first PC test reel:
# the face moved 0.14 of the frame width, x=0.508 on one take and x=0.652 on another), so a single
# anchor for the whole reel is wrong for every shot but one.
#
# Coordinates come back NORMALISED (0..1 of the source frame, origin top-left) so each consumer can
# convert into its own units: pixels for the ffmpeg bake, half-canvas units for a CapCut draft.
WINDOW_FRAMES = 5              # stills per window; a window is short, and 5 is enough for a median
WINDOW_MIN_FACES = 2           # below this a "median" is one lucky still: fall back rather than trust it
STILL = 0.04                   # face wanders less than this within the window: trust the median fully
ROAMING = 0.15                 # ... and beyond this, a single anchor means nothing, so do not correct


def _normalised(face, w, h, found, of):
    return {"x": round(face.cx / w, 4), "y": round(face.cy / h, 4), "frames": found, "of": of}


def _confidence(boxes, w):
    """How much this window's median is worth trusting, 0..1, from how far the face WANDERS inside
    it. A static anchor can only hold a subject who stays put: if she moves during the shot, the
    median is stale by the time the zoom lands and the correction pushes the wrong way — verified on
    a real clip where a full correction pushed the subject past centre the other way.

    Spread is measured ROBUSTLY (median absolute deviation), not max-minus-min. Traced frame by
    frame, a real shot sat at x=0.666 for 1.4s and then jumped once: max-minus-min called that 0.138
    of wandering and would have switched the fix off, while the MAD was 0.006 — the face is in one
    place and one sample is not. Worst-case spread is the wrong question; "is she mostly in one
    place?" is the right one, and a handful of samples makes the worst case almost meaningless."""
    xs = sorted((x + bw / 2) / w for x, _y, bw, _bh in boxes)
    if len(xs) < 2:
        return 1.0, 0.0
    med = statistics.median(xs)
    spread = 2.0 * statistics.median([abs(x - med) for x in xs])   # a robust stand-in for the face's range
    if spread <= STILL:
        conf = 1.0
    elif spread >= ROAMING:
        conf = 0.0
    else:
        conf = (ROAMING - spread) / (ROAMING - STILL)
    return round(conf, 3), round(spread, 4)


def window_anchor(video, size, t0, t1, n=WINDOW_FRAMES):
    """Median face centre within [t0,t1], normalised. None when this window has too few detections
    to be worth trusting. One hit out of five is not a median — it is a single still, and a false
    positive there aims the zoom at the wrong part of the room. Measured on real footage: a window
    detecting 1/5 returned x=0.21 while every solid window on the same clip sat at 0.54-0.64. Below
    WINDOW_MIN_FACES the caller falls back to the whole-cut median, which is at least a real one."""
    w, h, _dur = size
    frames = stills(video, size, count=n, start=t0, end=t1)
    if not frames:
        return None
    boxes = her_boxes(frames)
    if len(boxes) < WINDOW_MIN_FACES:
        return None
    got = _normalised(typical_face(boxes), w, h, len(boxes), len(frames))
    got["confidence"], got["spread_x"] = _confidence(boxes, w)
    return got


def anchors(video, windows, out=None):
    """One anchor per window, with an honest fallback chain: the window's own face, else the
    whole-cut median, else frame centre. Every row says which it used, so a build can never
    silently pass off a centre zoom as an anchored one."""
    size = shown_size(video)
    w, h, dur = size
    _say(f"{os.path.basename(video)}: {w}x{h}, {dur:.1f} s, {len(windows)} window{'s' if len(windows) != 1 else ''} to anchor")

    frames = stills(video, size)
    boxes = her_boxes(frames)
    whole = None
    if boxes:
        whole = _normalised(typical_face(boxes), w, h, len(boxes), len(frames))
        whole["confidence"], whole["spread_x"] = _confidence(boxes, w)
        whole["confidence"] = round(whole["confidence"] * 0.5, 3)   # a whole-cut median is a guess for any one shot
        print(f"whole-cut median face: ({whole['x']:.3f}, {whole['y']:.3f})  "
              f"from {whole['frames']}/{whole['of']} stills")
    else:
        print("⚠ no face anywhere in the cut - every window falls back to frame centre")

    rows = []
    for a, b in windows:
        got, src = window_anchor(video, size, a, b), "window"
        if got is None and whole is not None:
            got, src = dict(whole), "whole-cut"
        if got is None:
            got, src = {"x": 0.5, "y": 0.5, "frames": 0, "of": 0,
                        "confidence": 0.0, "spread_x": 0.0}, "frame-centre"
        rows.append({"start": round(float(a), 3), "end": round(float(b), 3),
                     "anchor": [got["x"], got["y"]], "source": src,
                     "confidence": got.get("confidence", 0.0),
                     "spread_x": got.get("spread_x", 0.0),
                     "frames": got["frames"], "of": got["of"]})
        note = ""
        if src != "window":
            note = f"  (too few detections; using the {src})"
        elif got["confidence"] < 0.99:
            note = (f"  (she moves {got['spread_x']:.2f} of the frame inside this window - "
                    f"correcting at {got['confidence'] * 100:.0f}%)")
        print(f"  {a:7.2f}-{b:7.2f}s  anchor=({got['x']:.3f}, {got['y']:.3f})  "
              f"[{src} {got['frames']}/{got['of']}]{note}")

    xs = [r["anchor"][0] for r in rows]
    spread = round(max(xs) - min(xs), 4) if len(xs) > 1 else 0.0
    if len(xs) > 1:
        print(f"face moves {spread:.3f} of the frame width across these windows - "
              f"{'per-shot anchors matter on this footage' if spread >= 0.05 else 'fairly still'}")

    doc = dict(_header(video, w, h), whole_cut=whole, x_spread=spread, windows=rows)
    if out:
        _write_json(out, doc)
    else:
        print(json.dumps(doc, indent=2))
    return doc


def parse_windows(spec):
    """--windows takes inline JSON or @file. The file can be a bare [[a,b],...] list, a caption-plan.json
    (its punch.windows), or this tool's own output (windows[].start/end)."""
    if spec.startswith("@"):
        with open(spec[1:], encoding="utf-8") as fp:
            data = json.load(fp)
    else:
        data = json.loads(spec)
    if isinstance(data, dict):
        data = (data.get("punch") or {}).get("windows") or data.get("windows") or []
    return [(float(row["start"]), float(row["end"])) if isinstance(row, dict)
            else (float(row[0]), float(row[1])) for row in data]


def _range_window(spec):
    """--range 4.3,6.1 (or 4.3:6.1) as one window."""
    return tuple(float(v) for v in spec.replace(":", ",").split(",")[:2])


def main():
    ap = argparse.ArgumentParser(description="Where she is in a cut: her face, her hair line, the 9:16 crop, "
                                             "and per-window zoom anchors.")
    ap.add_argument("cut", nargs="?", help="the cut to read, normally projects/<job>/outputs/<job>.mp4")
    ap.add_argument("--annotate", metavar="OUT_PNG")
    ap.add_argument("--windows", metavar="JSON",
                    help="per-shot zoom anchors: [[start,end],...] inline, or @plan.json")
    ap.add_argument("--range", metavar="A,B", help="a single window, in seconds")
    ap.add_argument("--out", metavar="OUT_JSON", help="write the anchors here instead of stdout")
    args = ap.parse_args()
    if args.windows or args.range:
        if not args.cut:
            ap.error("give the video to measure alongside --windows/--range")
        wins = parse_windows(args.windows) if args.windows else [_range_window(args.range)]
        anchors(args.cut, wins, out=args.out)
    elif args.cut:
        measure(args.cut, args.annotate)
    else:
        ap.error("point it at a base cut to measure")


if __name__ == "__main__":
    main()
