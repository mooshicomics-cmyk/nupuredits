#!/usr/bin/env python3
# /// script
# dependencies = ["opencv-python-headless", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]
# ///
"""caption_scenes.py: where centered captions sit, scene by scene: CAPTION_GAP px under her chin, locked.

Centered captions (single word, karaoke, phrase, spotlight) never follow her chin frame by frame (no bouncing). They
hold ONE spot, and that spot is measured again only when the scene really changes: she sits down, moves to the couch,
the camera is set up somewhere else. Each piece of her cut is read with the face model chin_lock uses (YuNet), on the
editor's light preview copy of her footage. Pieces that hold her in about the same place join into one scene; a jump
of more than SCENE_JUMP px in where her chin sits starts a new scene. Each scene's spot is under where her chin
USUALLY is in it (each piece's middle reading, averaged by how long the piece plays), never the lowest it got: one
lean down to her laptop used to drag a whole scene's captions to the bottom of the frame.

  uv run product/caption_scenes.py <job>          writes projects/<job>/review/caption-scenes.json and prints it

Output: {"cut_id", "gap", "scenes": [[cut_t0, cut_t1, top_px], ...]} in cut seconds and 1080x1920 px (top_px =
where the top of the caption letters goes). Cached by cut: run again after her cut changes. A piece with no face
read joins the scene around it. (2026-10-17: "significant scene changes should reassess a new locked location
for the scene change. not track my chin's motion" · "true for everyone using center aligned captions". 2026-10-21:
"100 PX below my chin on average", every reel, "stationary and intentional placement per scene".)
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAPTION_GAP = 100     # px between where her chin usually is and the top of the caption letters
SCENE_JUMP = 110      # px her chin must move between pieces to count as a new scene (a lean is not a scene change)
STEP = 1.0 / 6        # seconds between the frames read inside a piece

WIDE_CAPTION_Y = 950                                          # on the 1920x1080 frame, inside the 5% title-safe margin


def _cut_id(jd):
    with open(os.path.join(jd, "transcript", "cuts.json"), "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


def pieces(jd):
    """[(cut_t0, cut_t1, preview_t0, preview_t1)] for every piece of her cut, in cut order."""
    segs = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    try:
        clips = {c["name"]: float(c.get("offset") or 0) for c in
                 json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")).get("clips", [])}
    except Exception:
        clips = {}
    out, t = [], 0.0
    for s in segs:
        a, b = float(s["start"]), float(s["end"])
        played = float(s.get("played") or (b - a) / float(s.get("speed") or 1.0))
        off = clips.get(s.get("clip"), 0.0)
        out.append((round(t, 3), round(t + played, 3), a + off, b + off))
        t += played
    return out


def chin_of(video, t0, t1):
    """The lowest her chin gets in [t0, t1] of the video, and its median, in 1080x1920 px; (None, None) if no face."""
    import cv2
    sys.path.insert(0, HERE)
    import chin_lock
    hf = chin_lock.head_framing
    w, h, _ = hf.probe(video)
    k = 1920.0 / h
    cap = cv2.VideoCapture(video)
    yunet = cv2.FaceDetectorYN_create(hf.YUNET, "", (w, h), score_threshold=hf.YUNET_MIN_SCORE)
    ys, t = [], t0
    while t <= t1 + 1e-6:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        if frame.shape[1] != w or frame.shape[0] != h:
            frame = cv2.resize(frame, (w, h))
        found = yunet.detect(frame)[1]
        if found is not None and len(found):
            d = max(found, key=lambda d: d[2] * d[3])
            ys.append((float(d[1]) + float(d[3])) * k)
        t += STEP
    cap.release()
    if not ys:
        return None, None
    ys.sort()
    return ys[-1], ys[len(ys) // 2]


def scenes(jd, video=None):
    video = video or os.path.join(jd, "review", "preview.mp4")
    sys.path.insert(0, HERE)
    import frame
    if frame.is_wide(jd):                                     # a wide video keeps one spot: the lower third, not under a chin
        ps = pieces(jd)
        return [[ps[0][0], ps[-1][1], WIDE_CAPTION_Y]] if ps else []
    rows = []
    for c0, c1, p0, p1 in pieces(jd):
        low, mid = chin_of(video, p0, p1)
        rows.append([c0, c1, low, mid])
    out, cur = [], None
    for c0, c1, low, mid in rows:
        if cur is not None and (mid is None or cur["mid"] is None or abs(mid - cur["mid"]) <= SCENE_JUMP):
            cur["t1"] = c1
            if mid is not None:
                cur["mid"] = cur["mid"] if cur["mid"] is not None else mid
                cur["sum"] += mid * (c1 - c0); cur["w"] += c1 - c0
            continue
        if cur is not None:
            out.append(cur)
        cur = {"t0": c0, "t1": c1, "mid": mid, "sum": (mid or 0) * (c1 - c0), "w": (c1 - c0) if mid is not None else 0.0}
    if cur is not None:
        out.append(cur)
    return [[s["t0"], s["t1"], round(typical(s) + CAPTION_GAP)] for s in out if s["w"] > 0]


def typical(scene):
    """Where her chin usually is in a scene: each piece's middle reading, weighted by how long that piece plays."""
    return scene["sum"] / scene["w"]


def write(jd):
    res = {"cut_id": _cut_id(jd), "gap": CAPTION_GAP, "scenes": scenes(jd)}
    p = os.path.join(jd, "review", "caption-scenes.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    os.replace(tmp, p)
    return res


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    job = sys.argv[1]
    jd = job if os.path.isdir(job) else os.path.join(ROOT, "projects", job)
    print(json.dumps(write(jd), indent=1))
