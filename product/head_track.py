#!/usr/bin/env python3
# /// script
# dependencies = ["opencv-python-headless", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]
# ///
"""head_track.py: where a wide video's head goes, over her whole cut, so a look can stay clear of it for the seconds it
is on screen (frame.head_in). Read off the preview copy every STEP seconds and cached by cut in review/head-track.json:
[[cut_t, left, right, head_top, chin], ...] in px on the 1920x1080 frame, ears allowed for.

  uv run product/head_track.py <job or job folder>
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
STEP = 0.25      # a head doesn't cross the frame in a quarter of a second, and four a second stays quick on a long take
EARS = 0.20      # the face box stops at the cheeks: this much of its width again on each side takes in her ears


def track(jd):
    import cv2
    import caption_scenes, chin_lock
    hf = chin_lock.head_framing
    video = os.path.join(jd, "review", "preview.mp4")
    w, h, _ = hf.probe(video)
    kx, ky = 1920.0 / w, 1080.0 / h
    cap = cv2.VideoCapture(video)
    yunet = cv2.FaceDetectorYN_create(hf.YUNET, "", (w, h), score_threshold=hf.YUNET_MIN_SCORE)
    out = []
    for c0, c1, p0, p1 in caption_scenes.pieces(jd):
        t = p0
        while t < p1:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h))
            found = yunet.detect(frame)[1]
            if found is not None and len(found):
                d = max(found, key=lambda d: d[2] * d[3])
                x, y, fw, fh = map(float, d[:4])
                out.append([round(c0 + (t - p0) * (c1 - c0) / max(1e-6, p1 - p0), 2), round((x - EARS * fw) * kx), round((x + fw + EARS * fw) * kx),
                            round(y * ky), round((y + fh) * ky)])
            t += STEP
    cap.release()
    return out


def write(jd):
    import caption_scenes
    p = os.path.join(jd, "review", "head-track.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"cut_id": caption_scenes._cut_id(jd), "samples": track(jd)}, f)
    os.replace(tmp, p)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    job = sys.argv[1]
    write(job if os.path.isdir(job) else os.path.join(ROOT, "projects", job))
