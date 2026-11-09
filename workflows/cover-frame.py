# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""
cover-frame.py — pick the best COVER frames from a reel, by expression. The
tedious part of a thumbnail, done for you.

A reel cover is a still pulled from her own footage (see product/FLOW.md → Cover
/ thumbnail). Finding a good one by hand means scrubbing the whole clip looking
for the frame where her eyes are open, she's facing camera, it's sharp (not a
motion-blur mid-word), and the expression pops — then avoiding the twenty frames
that look almost the same. This does that first pass: it samples the reel densely,
detects her face (OpenCV YuNet, the same model head-framing.py uses), SCORES every
frame, throws out the blinks / blurry / turned-away ones, and hands back a short
list of clean candidates SPREAD across the reel so you get real variety, not six
copies of the same second.

It does NOT slap a title on them and it does NOT pick the final one — that stays
a human call (FLOW.md keeps the cover phased: options first ⏸ she picks, then the
title ⏸ she picks, then build). This just kills the scrubbing.

What each frame is scored on (all from what YuNet actually gives — no guessing):
  • face confidence   — is there clearly a face
  • size              — is it big enough to be the subject (not a far b-roll shot)
  • sharpness         — Laplacian variance on the face; rejects motion blur / mid-word
  • facing            — eyes level + nose centered between them → looking at camera
  • eyes open         — contrast inside each eye patch (open eye shows iris/white;
                        a blink goes smooth + skin-flat). A heuristic, weighted, honest.
  • expression        — mouth-corner spread vs face width → a little life / smile,
                        not a flat resting face

Usage:
  uv run workflows/cover-frame.py projects/<job>/outputs/<job>.final.mp4
      → writes the top candidates as clean full-frame JPEGs (NO title) to
        projects/<job>/thumbnails/candidates/cover-01.jpg … and cover-scores.json
      → prints them ranked so you can show her a numbered set to pick from

  options:
    --n 6            how many candidates to return (default 6)
    --min-gap 1.5    seconds any two candidates must be apart (spread; default 1.5)
    --job-dir DIR    where to write (default: alongside the video, ../thumbnails)
    --contact out.jpg   also write a labeled contact sheet of the picks
    --json           print the scores as JSON to stdout (for the skill to read)

First run auto-installs OpenCV via uv (one time, needs internet). No face found in
enough frames (faceless VO reel, heavy b-roll) → it says so and writes nothing,
rather than returning junk.
"""
import argparse, importlib.util, json, os, subprocess, sys, tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The engine's one face reader: the same detector, model and score floor that measure her for placement, and the
# same reading of a phone's rotation tag, so a cover is judged on the frame she actually sees.
_spec = importlib.util.spec_from_file_location(
    "head_framing", os.path.join(os.path.dirname(os.path.abspath(__file__)), "head-framing.py"))
head_framing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(head_framing)
MODEL = head_framing.YUNET

# how densely to look, and the floors below which a frame is not a usable cover
STEP_S = 0.4            # sample a frame every this many seconds
MAX_SAMPLES = 240       # cap so a long reel stays fast
FACE_CONF_FLOOR = 0.75  # YuNet score below this = not a clean face, drop it
MIN_FACE_FRAC = 0.06    # face box height / frame height below this = too small, drop


def sample_times(dur):
    n = min(MAX_SAMPLES, max(1, int(dur / STEP_S)))
    return [dur * (i + 0.5) / n for i in range(n)]


def grab(video, t, path):
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
                    "-frames:v", "1", "-q:v", "2", "-y", path],
                   capture_output=True)


def eye_openness(gray, ex, ey, face_h):
    """Proxy: an open eye shows iris/sclera contrast; a blink is smooth + skin-flat.
    Std-dev of a small patch around the eye landmark, normalized. Heuristic, not truth."""
    import numpy as np
    r = max(4, int(face_h * 0.06))
    y0, y1 = max(0, ey - r), min(gray.shape[0], ey + r)
    x0, x1 = max(0, ex - r), min(gray.shape[1], ex + r)
    patch = gray[y0:y1, x0:x1]
    if patch.size == 0:
        return 0.0
    return float(np.std(patch))


def score_frame(img):
    """Detect the largest face, return (score 0..1, detail dict) or None if no clean face."""
    import cv2, numpy as np
    h, w = img.shape[:2]
    found = cv2.FaceDetectorYN_create(MODEL, "", (w, h), score_threshold=head_framing.YUNET_MIN_SCORE).detect(img)[1]
    if found is None or not len(found):
        return None
    d = max(found, key=lambda face: face[2] * face[3])       # her: the largest face in the frame
    fx, fy, fw, fh = float(d[0]), float(d[1]), float(d[2]), float(d[3])
    conf = float(d[14])
    # landmarks: 4-5 right eye, 6-7 left eye, 8-9 nose, 10-11 r mouth, 12-13 l mouth
    reye, leye = (d[4], d[5]), (d[6], d[7])
    nose = (d[8], d[9])
    rmouth, lmouth = (d[10], d[11]), (d[12], d[13])

    if conf < FACE_CONF_FLOOR or fh / h < MIN_FACE_FRAC:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # sharpness on the face box only (motion blur mid-word tanks this)
    y0, y1 = max(0, int(fy)), min(h, int(fy + fh))
    x0, x1 = max(0, int(fx)), min(w, int(fx + fw))
    face_gray = gray[y0:y1, x0:x1]
    sharp = float(cv2.Laplacian(face_gray, cv2.CV_64F).var()) if face_gray.size else 0.0

    # facing: eyes level (small vertical delta) + nose centered between the eyes
    eye_dx = abs(leye[0] - reye[0]) or 1.0
    level = 1.0 - min(1.0, abs(leye[1] - reye[1]) / eye_dx)           # 1 = eyes level
    eye_mid_x = (leye[0] + reye[0]) / 2
    centered = 1.0 - min(1.0, abs(nose[0] - eye_mid_x) / (eye_dx / 2))  # 1 = nose centered
    facing = (level + centered) / 2

    # eyes open (proxy), averaged across both eyes, normalized to a soft 0..1
    eo = (eye_openness(gray, int(reye[0]), int(reye[1]), fh)
          + eye_openness(gray, int(leye[0]), int(leye[1]), fh)) / 2
    eyes_open = min(1.0, eo / 45.0)

    # expression: mouth-corner spread vs face width (a little life beats a flat face)
    mouth_w = abs(lmouth[0] - rmouth[0])
    expression = min(1.0, (mouth_w / fw) / 0.5)

    # sharpness is unbounded; squash to 0..1 with a soft knee (~150 var = crisp)
    sharp_n = min(1.0, sharp / 150.0)
    size_n = min(1.0, (fh / h) / 0.35)

    total = float(0.16 * conf + 0.22 * sharp_n + 0.20 * facing
                  + 0.22 * eyes_open + 0.10 * expression + 0.10 * size_n)
    detail = {"conf": round(float(conf), 3), "sharpness": round(float(sharp), 1),
              "sharp_n": round(float(sharp_n), 3), "facing": round(float(facing), 3),
              "eyes_open": round(float(eyes_open), 3),
              "expression": round(float(expression), 3),
              "size": round(float(size_n), 3), "score": round(total, 4)}
    return total, detail


def pick_spread(scored, n, min_gap):
    """Greedy: take the highest score, then the next-highest at least min_gap seconds
    from every pick already taken. Gives variety across the reel, not a cluster."""
    picked = []
    for t, det, path in sorted(scored, key=lambda s: -s[1]["score"]):
        if all(abs(t - pt) >= min_gap for pt, _, _ in picked):
            picked.append((t, det, path))
        if len(picked) >= n:
            break
    return sorted(picked, key=lambda s: -s[1]["score"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--min-gap", type=float, default=1.5)
    ap.add_argument("--job-dir", default=None)
    ap.add_argument("--contact", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(MODEL):
        print(f"✗ face model missing at {MODEL}", file=sys.stderr)
        sys.exit(1)

    import cv2  # noqa: triggers the uv install on first run

    w, h, dur = head_framing.probe(args.video)
    times = sample_times(dur)
    if not args.json:
        print(f"source: {w}x{h}  {dur:.1f}s  ·  sampling {len(times)} frames")

    tmp = tempfile.mkdtemp()
    scored = []
    for i, t in enumerate(times):
        f = os.path.join(tmp, f"s{i:04d}.jpg")
        grab(args.video, t, f)
        img = cv2.imread(f)
        if img is None:
            continue
        res = score_frame(img)
        if res is None:
            continue
        total, det = res
        det["t"] = round(t, 2)
        scored.append((t, det, f))

    if len(scored) < 1:
        print("✗ no clean face frames found — this reads as faceless / heavy b-roll. "
              "Pick a cover by eye, or point me at a talking-head clip.", file=sys.stderr)
        sys.exit(1)

    picks = pick_spread(scored, args.n, args.min_gap)

    out_dir = args.job_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(args.video))),
        "thumbnails", "candidates")
    os.makedirs(out_dir, exist_ok=True)

    results = []
    for rank, (t, det, src) in enumerate(picks, 1):
        dst = os.path.join(out_dir, f"cover-{rank:02d}.jpg")
        # re-grab at full quality straight from the source at the exact time
        grab(args.video, t, dst)
        det["rank"] = rank
        det["file"] = dst
        results.append(det)

    payload = {"video": os.path.abspath(args.video),
               "source": {"w": w, "h": h, "dur": round(dur, 2)},
               "sampled": len(times), "face_frames": len(scored),
               "candidates": results}
    with open(os.path.join(out_dir, "cover-scores.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    if args.contact:
        import numpy as np
        cols = min(3, len(results))
        rows = (len(results) + cols - 1) // cols
        cell_w, cell_h = 360, 640
        sheet = np.full((rows * cell_h, cols * cell_w, 3), 30, np.uint8)
        for idx, det in enumerate(results):
            im = cv2.imread(det["file"])
            if im is None:
                continue
            im = cv2.resize(im, (cell_w, cell_h))
            cv2.putText(im, f"#{det['rank']}  {det['score']:.2f}", (12, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            r, c = divmod(idx, cols)
            sheet[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w] = im
        cv2.imwrite(args.contact, sheet)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"\nfound {len(scored)} face frames, picked {len(results)} spread "
              f">= {args.min_gap}s apart:\n")
        for det in results:
            print(f"  #{det['rank']}  score {det['score']:.2f}  @ {det['t']:.1f}s   "
                  f"(sharp {det['sharp_n']:.2f} · facing {det['facing']:.2f} · "
                  f"eyes {det['eyes_open']:.2f} · expr {det['expression']:.2f})   "
                  f"{os.path.relpath(det['file'], REPO)}")
        print(f"\nclean stills (no title) → {os.path.relpath(out_dir, REPO)}")
        print("next: show her the numbered set, she picks one, THEN do the title.")


if __name__ == "__main__":
    main()
