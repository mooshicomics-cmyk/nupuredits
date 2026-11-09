# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'", "numpy"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""face_cover.py: Cover a face. Her kids stay in the reel; their faces don't show.

The visual editor's Visuals tab has a "Cover a face" tool. She taps the faces to hide, picks a cover for each (a
blur, a pixelate, an emoji, or a sticker of her own), and checks the few moments the engine flags. It's opt-in twice
over: nothing happens unless she opens the tool, and inside it nothing is covered until she taps a face. Faces from
every video in her reel are listed together, grouped by video, and she picks across all of them. This file is the
engine side of that:

    uv run product/face_cover.py find <job>      follow every face through her clips -> review/faces.json
    uv run product/face_cover.py bake <job> <base.mp4> <out.mp4>   her covers built into the cut's footage (Finish)
    uv run product/face_cover.py status <job>    what's there: faces found, covers on

How a face is followed: the engine's own face model (YuNet, the one subject-zones and chin-lock use) runs on
every frame of her ORIGINAL clips at full width, because a toddler across the room is a small face and the page's
preview copy is a quarter of the size. Sightings string into one track per person. Where a face is lost (turned
into her mom's chest, behind a shoulder, out of focus) every frame still gets a box: a short gap is drawn straight
across, and a long one rides along with whoever stayed in view (a baby in a carrier moves with her mom) and is
marked "held", which the page lists under "Check these moments". She is the one who looks; she drags a cover back
if it slipped, and that fix is kept here and used by the bake exactly as the page drew it.

Everything is in the PREVIEW's seconds and its canvas (review/script.json "clips" offsets and "canvas"): the page
plays the preview, so a box drawn on the page is a box in the bake. The bake maps her cut's time back through the
cut's own pieces (script.json "segs") to find each frame's box.

Her choices live in review/face-cover.json (written by the page through the editor server). Each cover she can
see is a picture: the page draws the emoji or her sticker into a square PNG (review/face-cover-<id>.png) and the
bake lays that same PNG, so the export matches the preview on every computer with no emoji font needed. Blur and
pixelate are made from her footage itself.
"""
import hashlib, json, os, subprocess, sys, time

try:                                   # the editor server and Finish read her covers with plain Python (no numpy);
    import numpy as np                 # finding and baking run through `uv run`, which brings numpy and OpenCV
except ImportError:
    np = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "assets", "models", "face_detection_yunet_2023mar.onnx")
FPS = 30.0            # the preview's frame rate (visual_editor.make_preview): one track entry per preview frame
DW = 1080             # detect at full width
MIN_SCORE = 0.55      # what the detector reports; a track must also be sure on the whole (SURE)
SURE = 0.72           # a track's median sureness: posters, hands and carrier prints come in under this
SHORT_GAP = 12        # frames: shorter gaps are drawn straight across ("filled")
MIN_SEEN = 12         # a track seen fewer times than this is a passing false hit
STICKER_SPAN = 2.2    # a sticker PNG covers a square this many cover-radii wide (the page draws it the same way)
SEEN, FILLED, HELD = 0, 1, 2


def job_dir(job):
    return os.path.join(ROOT, "projects", job)


def _read(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _atomic(path, data):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ── finding faces ──────────────────────────────────────────────────────────────────────────────────────────────
def _upright_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:stream_side_data=rotation:stream_tags=rotate", "-of", "json", path],
                       capture_output=True, text=True, timeout=60)
    st = json.loads(r.stdout)["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    rot = abs(int(float((st.get("tags") or {}).get("rotate", 0) or
                        next((d.get("rotation", 0) for d in st.get("side_data_list", []) if "rotation" in d), 0))))
    return (h, w) if rot % 180 == 90 else (w, h)


def _frames(path, w, h):
    """Her clip upright (ffmpeg applies the phone's rotation) at the preview's 30 fps, w x h, as BGR arrays."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={FPS:g},scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    size = w * h * 3
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


def _detect(path, w, h, progress=None):
    import cv2
    det = cv2.FaceDetectorYN_create(MODEL, "", (w, h), score_threshold=MIN_SCORE)
    out = []
    for img in _frames(path, w, h):
        r = det.detect(img)[1]
        out.append([] if r is None else [(float(x), float(y), float(bw), float(bh), float(s)) for x, y, bw, bh, *_, s in r])
        if progress and len(out) % 30 == 0:
            progress(len(out))
    return out


def _link(dets):
    """Greedy frame-to-frame linking: the nearest face of a like size, allowing for a little drift while lost."""
    tracks, live = [], []
    for f, faces in enumerate(dets):
        faces = sorted(faces, key=lambda d: -d[4])
        used = set()
        for t in live:
            lf, (x, y, w, h, _) = t["last"]
            vx, vy = t.get("v", (0, 0))
            gap = f - lf
            px, py = x + w / 2 + vx * gap, y + h / 2 + vy * gap
            best, bd = None, None
            for i, (dx, dy, dw, dh, ds) in enumerate(faces):
                if i in used:
                    continue
                d = np.hypot(dx + dw / 2 - px, dy + dh / 2 - py) / max(w, dw)
                if d < 0.9 + 0.04 * min(gap, 30) and max(w, dw) / min(w, dw) < 1.8 and (bd is None or d < bd):
                    best, bd = i, d
            if best is not None:
                used.add(best)
                nb = faces[best]
                t["v"] = ((nb[0] + nb[2] / 2 - (x + w / 2)) / gap * 0.5 + vx * 0.5,
                          (nb[1] + nb[3] / 2 - (y + h / 2)) / gap * 0.5 + vy * 0.5)
                t["seen"][f] = nb
                t["last"] = (f, nb)
        for i, d in enumerate(faces):
            if i not in used:
                t = {"seen": {f: d}, "last": (f, d)}
                tracks.append(t)
                live.append(t)
        live = [t for t in live if f - t["last"][0] <= 60]
    return [t["seen"] for t in tracks]


def _same_person(a, b):
    """(Almost) never on screen together, and close in place wherever they come close in time: one face that kept
    turning away and coming back."""
    if len(set(a) & set(b)) > 2:
        return False
    ka = np.array(sorted(a))
    near = []
    for f in b:
        j = int(ka[np.argmin(np.abs(ka - f))])
        if abs(j - f) > 45:
            continue
        A, B = a[j], b[f]
        near.append(np.hypot(A[0] + A[2] / 2 - B[0] - B[2] / 2, A[1] + A[3] / 2 - B[1] - B[3] / 2) / max(A[2], B[2]))
    return len(near) >= 2 and float(np.median(near)) < 1.6


def _same_beside(a, b, others):
    """Lost for longer: the same person if she comes back in the same spot beside someone seen at both ends, at the
    same size relative to them (a baby facing her mom's chest for eight seconds)."""
    if set(a) & set(b):
        return False
    if max(a) > min(b):
        a, b = b, a
    if max(a) > min(b):
        return False
    ea, sb = max(a), min(b)
    for c in others:
        if c is a or c is b:
            continue
        ca = [c[k] for k in range(ea - 10, ea + 1) if k in c]
        cb = [c[k] for k in range(sb, sb + 11) if k in c]
        if not ca or not cb:
            continue
        ca, cb, A, B = ca[-1], cb[0], a[ea], b[sb]

        def rel(f, c):
            return ((f[0] + f[2] / 2 - c[0] - c[2] / 2) / c[2], (f[1] + f[3] / 2 - c[1] - c[3] / 2) / c[2], f[2] / c[2])
        ra, rb = rel(A, ca), rel(B, cb)
        if np.hypot(ra[0] - rb[0], ra[1] - rb[1]) < 1.5 and max(ra[2], rb[2]) / min(ra[2], rb[2]) < 2:
            return True
    return False


def _merge(tracks):
    tracks = sorted(tracks, key=lambda s: -len(s))
    changed = True
    while changed:
        changed = False
        for a in tracks:
            for b in tracks:
                if a is not b and (_same_person(a, b) or _same_beside(a, b, tracks)):
                    a.update(b)
                    tracks.remove(b)
                    changed = True
                    break
            if changed:
                break
    return tracks


def _fill(seen, n, everyone):
    """Every frame of the clip gets a box: [cx, cy, w, h, state] in detection pixels."""
    keys = sorted(seen)
    out = [None] * n
    for k in keys:
        x, y, w, h, _ = seen[k]
        out[k] = [x + w / 2, y + h / 2, w, h, SEEN]
    marks = [-1] + keys + [n]
    for a, b in zip(marks, marks[1:]):
        if b - a <= 1:
            continue
        A = out[a] if a >= 0 else None
        B = out[b] if b < n else None
        state = FILLED if (A and B and b - a <= SHORT_GAP) else HELD
        comp = None
        if A and B and state == HELD:                    # ride with someone seen at both ends and through most of it
            for o in everyone:
                if o is not seen and a in o and b in o and sum(1 for k in range(a + 1, b) if k in o) > 0.6 * (b - a - 1):
                    comp = o
                    break
        for k in range(a + 1, b):
            if A and B:
                u = (k - a) / (b - a)
                box = [A[i] + (B[i] - A[i]) * u for i in range(4)]
                if comp:
                    near = [comp[j] for j in (k, k - 1, k + 1, k - 2, k + 2) if j in comp]
                    if near:
                        c, ca, cb = near[0], comp[a], comp[b]
                        offa = (A[0] - (ca[0] + ca[2] / 2), A[1] - (ca[1] + ca[3] / 2))
                        offb = (B[0] - (cb[0] + cb[2] / 2), B[1] - (cb[1] + cb[3] / 2))
                        box[0] = c[0] + c[2] / 2 + offa[0] + (offb[0] - offa[0]) * u
                        box[1] = c[1] + c[3] / 2 + offa[1] + (offb[1] - offa[1]) * u
            else:
                box = list((A or B)[:4])
            out[k] = box + [state]
    arr = np.array([o[:4] for o in out], float)          # a light glide, so a cover never jitters
    k = 5
    pad = np.pad(arr, ((k // 2, k // 2), (0, 0)), mode="edge")
    sm = np.stack([np.convolve(pad[:, i], np.ones(k) / k, mode="valid") for i in range(4)], 1)
    return [list(map(float, sm[i])) + [out[i][4]] for i in range(n)]


def _thumb(path, t, box, w, h):
    """A round-ready square of one face, from its biggest, surest sighting, for the page's picker."""
    import base64
    import cv2
    img = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={w}:{h}",
                          "-f", "image2pipe", "-vcodec", "mjpeg", "-"], capture_output=True).stdout
    a = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_COLOR)
    if a is None:
        return None
    cx, cy, bw, bh = box[:4]
    s = max(bw, bh) * 1.9
    x0, y0 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
    crop = a[y0:int(min(h, cy + s / 2)), x0:int(min(w, cx + s / 2))]
    if crop.size == 0:
        return None
    crop = cv2.resize(crop, (160, 160))
    return "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])[1]).decode()


def _status(jd, **kw):
    path = os.path.join(jd, "review", "faces-status.json")
    _atomic(path, dict(_read(path, {}) or {}, **kw, at=time.strftime("%Y-%m-%d %H:%M:%S")))


def find(job, log=print):
    """Every face in her clips, followed frame by frame, into review/faces.json (preview seconds, canvas-normalized)."""
    jd = job_dir(job)
    sc = _read(os.path.join(jd, "review", "script.json"))
    if not sc:
        raise SystemExit("No script for this reel yet: open the visual editor on it first.")
    W, H = sc["canvas"]["w"], sc["canvas"]["h"]
    clips = sc["clips"]
    raws = []
    for c in clips:
        p = os.path.join(jd, "raw", c["name"])
        if not os.path.isfile(p):
            raise SystemExit(f"Her clip {c['name']} isn't in this reel's raw folder, so its faces can't be found.")
        raws.append(p)
    durs = []
    for p in raws:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True)
        durs.append(float(r.stdout.strip() or 0))
    N = int(round((clips[-1]["offset"] + durs[-1]) * FPS)) + 1
    total = sum(durs) * FPS
    _status(jd, state="running", done=0, total=int(total), message=None)
    faces, done = [], 0
    for ci, (c, p) in enumerate(zip(clips, raws)):
        rw, rh = _upright_size(p)
        dw = min(DW, rw) if rw <= rh else int(round(min(DW, rh) * rw / rh))   # the shorter side at most 1080
        dw -= dw % 2
        dh = int(round(dw * rh / rw)); dh -= dh % 2
        dets = _detect(p, dw, dh, progress=lambda k: _status(jd, done=done + k))
        done += len(dets)
        n = len(dets)
        tracks = [t for t in _merge([t for t in _link(dets) if len(t) >= 3 and
                                     float(np.median([d[4] for d in t.values()])) >= SURE]) if len(t) >= MIN_SEEN]
        # where this clip sits on the preview canvas (scaled to fit, padded), so boxes land where the page draws
        s = min(W / dw, H / dh)
        ox, oy = (W - dw * s) / 2, (H - dh * s) / 2
        start = int(round(c["offset"] * FPS))
        for t in sorted(tracks, key=lambda t: -len(t)):
            boxes = _fill(t, n, tracks)
            best = max(t, key=lambda k: t[k][2] * t[k][4])
            track = [None] * N
            for k, b in enumerate(boxes):
                g = start + k
                if 0 <= g < N:
                    track[g] = [round((ox + b[0] * s) / W, 4), round((oy + b[1] * s) / H, 4),
                                round(b[2] * s / W, 4), round(b[3] * s / H, 4), b[4]]
            faces.append({"id": len(faces) + 1, "clip": ci, "seen": len(t), "frames": n, "best": start + best,
                          "thumb": _thumb(p, best / FPS, boxes[best], dw, dh), "track": track})
        log(f"  {c['name']}: {len(tracks)} face{'s' if len(tracks) != 1 else ''}")
    # opt-in: no face is guessed at or covered here; she picks every one on the page, across all her videos
    out = {"version": 1, "fps": FPS, "frames": N, "canvas": {"w": W, "h": H}, "clips": [c["name"] for c in clips], "faces": faces,
           "made_for": hashlib.sha1(json.dumps(clips, sort_keys=True).encode()).hexdigest()[:12]}
    _atomic(os.path.join(jd, "review", "faces.json"), out)
    _status(jd, state="done", done=int(total), faces=len(faces))
    return out


# ── her covers, as the page set them ───────────────────────────────────────────────────────────────────────────
def _fix_at(fixes, k):
    """Her drags are keyframes (the page's fixAt, kept identical): between two within 3 s it moves smoothly from
    one to the other; past the last it holds 1 s, then eases away over half a second."""
    if not fixes:
        return 0.0, 0.0
    keys = sorted(int(q) for q in fixes)
    lo = max((q for q in keys if q <= k), default=None)
    hi = min((q for q in keys if q >= k), default=None)
    span, fade, hold = FPS * 3, FPS * 0.5, FPS * 1.0
    if lo is not None and hi is not None and hi - lo <= span:
        if hi == lo:
            return tuple(fixes[str(lo)])
        u = (k - lo) / (hi - lo)
        a, b = fixes[str(lo)], fixes[str(hi)]
        return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
    near = lo if lo is not None and (hi is None or k - lo < hi - k) else hi
    dist = abs(k - near)
    w = 1.0 if dist <= hold else max(0.0, 1 - (dist - hold) / fade)
    return fixes[str(near)][0] * w, fixes[str(near)][1] * w


def covers_on(jd):
    """The faces she covered, each with its track and her settings; [] when Cover a face isn't in use."""
    found, mine = _read(os.path.join(jd, "review", "faces.json")), _read(os.path.join(jd, "review", "face-cover.json"))
    if not found or not mine or mine.get("made_for") != found.get("made_for"):
        return []
    tracks = {f["id"]: f for f in found["faces"]}
    return [dict(c, track=tracks[int(fid)]["track"], id=int(fid)) for fid, c in (mine.get("faces") or {}).items()
            if c.get("on") and int(fid) in tracks]


def signature(jd):
    """Changes whenever anything that shows in the covered footage changes (a new pick, a drag, a sticker)."""
    h = hashlib.sha1()
    for f in ("faces.json", "face-cover.json"):
        try:
            h.update(open(os.path.join(jd, "review", f), "rb").read())
        except OSError:
            pass
    for c in covers_on(jd):
        png = os.path.join(jd, "review", f"face-cover-{c['id']}.png")
        if os.path.isfile(png):
            h.update(open(png, "rb").read())
    return h.hexdigest()[:12]


def _cut_to_preview(segs):
    """Cut seconds -> preview seconds, through the cut's own pieces (what the page plays, in order)."""
    edges, acc = [], 0.0
    for g in segs:
        d = float(g["e"]) - float(g["s"])
        edges.append((acc, acc + d, float(g["s"])))
        acc += d

    def at(t):
        for a, b, s in edges:
            if t < b:
                return s + max(0.0, t - a)
        a, b, s = edges[-1]
        return s + (b - a)
    return at


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                        "-of", "json", path], capture_output=True, text=True)
    st = json.loads(r.stdout)["streams"][0]
    n, d = st["r_frame_rate"].split("/")
    return int(st["width"]), int(st["height"]), float(n) / float(d)


def bake(job, base, out, log=print):
    """Her covers built into the cut's footage (Finish, both routes, the way her Filter is). Writes out; returns it."""
    import cv2
    jd = job_dir(job)
    covers = covers_on(jd)
    if not covers:
        raise SystemExit("No face is covered on this reel.")
    sc = _read(os.path.join(jd, "review", "script.json"))
    to_preview = _cut_to_preview(sc["segs"])
    W, H, fps = _probe(base)
    stickers = {}
    for c in covers:
        if c.get("kind") not in ("blur", "pixel"):
            png = cv2.imread(os.path.join(jd, "review", f"face-cover-{c['id']}.png"), cv2.IMREAD_UNCHANGED)
            if png is None or png.ndim != 3 or png.shape[2] != 4:
                raise SystemExit(f"The cover for face {c['id']} is missing. Pick it again on the page, then export.")
            stickers[c["id"]] = png
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import video_encoder                                  # the shared, PC-safe encoder (NVENC / VideoToolbox / libx264)
    tmp = out + ".part.mp4"

    def one_pass(venc):
        dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", base, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{fps:.6f}",
                                "-i", "-", "-i", base, "-map", "0:v", "-map", "1:a?", *venc, "-pix_fmt", "yuv420p",
                                "-c:a", "copy", "-movflags", "+faststart", tmp], stdin=subprocess.PIPE)
        size, i = W * H * 3, 0
        try:
            while True:
                buf = dec.stdout.read(size)
                if len(buf) < size:
                    break
                img = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
                k = int(round(to_preview(i / fps) * FPS))
                for c in covers:
                    tr = c["track"]
                    b = tr[k] if 0 <= k < len(tr) else None
                    if not b:
                        continue
                    dx, dy = _fix_at(c.get("fixes") or {}, k)
                    cx, cy = (b[0] + dx) * W, (b[1] + dy) * H
                    r = max(b[2] * W, b[3] * H) * float(c.get("size") or 1.65) / 2
                    _draw(img, c.get("kind"), stickers.get(c["id"]), cx, cy, r)
                enc.stdin.write(img.tobytes())
                i += 1
            enc.stdin.close()
        except (BrokenPipeError, OSError):                # the encoder stopped early: said below by its exit code
            pass
        enc.wait()
        dec.stdout.close()
        dec.wait()
        return i if enc.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0 else None

    venc = video_encoder.pick_encoder(vbr="20M", crf=14, preset="veryfast")
    i = one_pass(venc)
    if i is None and video_encoder.is_hardware(venc):     # a hardware encoder that won't start: software, every build has it
        i = one_pass(video_encoder.software_encoder(crf=14, preset="veryfast"))
    if i is None:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise SystemExit("The covered footage couldn't be written.")
    os.replace(tmp, out)
    log(f"  covered {len(covers)} face{'s' if len(covers) != 1 else ''} across {i} frames")
    return out


def _draw(img, kind, sticker, cx, cy, r):
    import cv2
    H, W = img.shape[:2]
    if kind in ("blur", "pixel"):
        x0, y0, x1, y1 = int(cx - r), int(cy - r), int(cx + r), int(cy + r)
        X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if X1 <= X0 or Y1 <= Y0:
            return
        roi = img[Y0:Y1, X0:X1]
        n = 7 if kind == "blur" else 11                   # the page's own recipe: shrink the face to n x n, grow it back
        full = cv2.copyMakeBorder(roi, Y0 - y0, y1 - Y1, X0 - x0, x1 - X1, cv2.BORDER_REPLICATE)
        small = cv2.resize(full, (n, n), interpolation=cv2.INTER_AREA)
        big = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_CUBIC if kind == "blur" else cv2.INTER_NEAREST)
        if kind == "blur":
            big = cv2.GaussianBlur(big, (0, 0), max(1.0, r / 10))
        big = big[Y0 - y0:Y0 - y0 + (Y1 - Y0), X0 - x0:X0 - x0 + (X1 - X0)]
        mask = np.zeros((Y1 - Y0, X1 - X0), np.uint8)
        cv2.ellipse(mask, (int(cx - X0), int(cy - Y0)), (int(r * .86), int(r)), 0, 0, 360, 255, -1, cv2.LINE_AA)
        a = (mask.astype(np.float32) / 255)[..., None]
        img[Y0:Y1, X0:X1] = (big * a + roi * (1 - a)).astype(np.uint8)
        return
    if sticker is None:
        return
    side = int(round(r * STICKER_SPAN))
    if side < 2:
        return
    st = cv2.resize(sticker, (side, side), interpolation=cv2.INTER_AREA)
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    X0, Y0, X1, Y1 = max(0, x0), max(0, y0), min(W, x0 + side), min(H, y0 + side)
    if X1 <= X0 or Y1 <= Y0:
        return
    s = st[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0].astype(np.float32)
    a = s[..., 3:4] / 255
    img[Y0:Y1, X0:X1] = (s[..., :3] * a + img[Y0:Y1, X0:X1] * (1 - a)).astype(np.uint8)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, job = argv[0], argv[1]
    if cmd == "find":
        out = find(job)
        print(f"Found {len(out['faces'])} face{'s' if len(out['faces']) != 1 else ''}.")
    elif cmd == "bake":
        bake(job, argv[2], argv[3])
    elif cmd == "status":
        jd = job_dir(job)
        found = _read(os.path.join(jd, "review", "faces.json"))
        print(json.dumps({"faces": len(found["faces"]) if found else None, "covered": [c["id"] for c in covers_on(jd)]}))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
