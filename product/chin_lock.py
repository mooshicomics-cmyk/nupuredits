#!/usr/bin/env python3
# /// script
# dependencies = ["opencv-python-headless", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""chin_lock.py — keep a caption (or any element) a fixed distance UNDER the creator's chin, frame by frame.

A caption placed from one measurement sits right only if she holds still. When she moves (leans in, settles onto a
couch, walks toward the camera) a fixed spot ends up on her face or far below her. Chin lock reads her chin on EVERY
frame of the window with the same face model subject-zones uses (YuNet, assets/models), fills any missed frame by
interpolation, smooths it so the element glides instead of jittering, and returns where the element's top should be
at each moment: chin + offset, in 1080x1920 authoring px.

If she barely moves over the window (the chin stays within --hold px), it returns ONE steady position instead (the
lowest the chin got + offset), so a still take never gets a wobbling caption.

  uv run product/chin_lock.py <cut.mp4> --from 7.10 --to 7.98 --offset 40
  uv run product/chin_lock.py <cut.mp4> --from 7.10 --to 7.98 --offset 40 --json keys.json
  uv run product/chin_lock.py <cut.mp4> --from 7.10 --to 7.98 --offset 40 --gsap "#c0" --comp-start 6.84 --box-offset -55
  uv run product/chin_lock.py <cut.mp4> --windows wins.json --offset 80 --json keys.json    # many windows, one run

--from/--to are seconds on the cut (the stitched reel), --offset is px between her chin and the element's TOP ink
edge. --gsap prints GSAP `tl.set(sel,{top:…},t)` lines in the composition's local time (--comp-start is when the
composition starts on the cut) with --box-offset added, for elements whose CSS top is not their ink top.
Rendered routes only: the CapCut-editable route places text in CapCut.
"""
import argparse, importlib.util, json, os, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("head_framing", os.path.join(HERE, "..", "workflows", "head-framing.py"))
head_framing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(head_framing)

AUTH_W, AUTH_H = 1080, 1920


def chin_track(video, t0, t1):
    """[(t_on_cut, chin_y_authoring_px or None)] for every frame in [t0, t1]."""
    import cv2
    w, h, _ = head_framing.probe(video)
    if abs(AUTH_W / w - AUTH_H / h) > 1e-3:
        sys.exit(f"✗ {w}x{h} is not 9:16, so its pixels do not map onto the 1080x1920 frame. Lock against the "
                 f"finished cut (projects/<job>/outputs/<job>.mp4).")
    k = AUTH_H / h
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000)
    yunet = cv2.FaceDetectorYN_create(head_framing.YUNET, "", (w, h), score_threshold=head_framing.YUNET_MIN_SCORE)
    out, t = [], t0
    while t <= t1 + 1e-6:
        ok, frame = cap.read()
        if not ok:
            break
        if frame.shape[1] != w or frame.shape[0] != h:
            frame = cv2.resize(frame, (w, h))
        found = yunet.detect(frame)[1]
        if found is not None and len(found):
            d = max(found, key=lambda d: d[2] * d[3])
            out.append((round(t, 3), (float(d[1]) + float(d[3])) * k))
        else:
            out.append((round(t, 3), None))
        t += 1.0 / fps
    cap.release()
    return out


def _fill(track):
    """Linear-interpolate frames where no face was found; edges take the nearest found value."""
    ys = [y for _, y in track]
    known = [i for i, y in enumerate(ys) if y is not None]
    if not known:
        sys.exit("✗ no face found anywhere in that window: nothing to lock to. Place this one by eye.")
    for i, y in enumerate(ys):
        if y is None:
            lo = max((j for j in known if j < i), default=None)
            hi = min((j for j in known if j > i), default=None)
            if lo is None: ys[i] = ys[hi]
            elif hi is None: ys[i] = ys[lo]
            else: ys[i] = ys[lo] + (ys[hi] - ys[lo]) * (i - lo) / (hi - lo)
    return [(t, y) for (t, _), y in zip(track, ys)]


def lock(video, t0, t1, offset=40, smooth=3, hold=12):
    """{'mode': 'hold'|'follow', 'keys': [{'t','chin','y'}]} — y = where the element's top ink edge goes."""
    track = _fill(chin_track(video, t0, t1))
    ys = [y for _, y in track]
    half = smooth // 2
    sm = [sum(ys[max(0, i - half):i + half + 1]) / len(ys[max(0, i - half):i + half + 1]) for i in range(len(ys))]
    if max(sm) - min(sm) <= hold:          # she is still: one steady spot, never above her lowest chin
        c = max(sm)
        return {"mode": "hold", "offset": offset, "keys": [{"t": track[0][0], "chin": round(c), "y": round(c + offset)}]}
    return {"mode": "follow", "offset": offset,
            "keys": [{"t": t, "chin": round(c), "y": round(c + offset)} for (t, _), c in zip(track, sm)]}


def lock_many(video, windows, offset=40, smooth=3, hold=12):
    """lock() over many (t0, t1) windows in one run: [result or None]. A window with no face anywhere comes back
    None (that one element is placed some other way) instead of stopping the whole batch."""
    out = []
    for t0, t1 in windows:
        try:
            out.append(lock(video, float(t0), float(t1), offset, smooth, hold))
        except SystemExit:
            out.append(None)
    return out


def gsap_lines(result, selector, comp_start, box_offset=0):
    return [f'tl.set("{selector}",{{top:{k["y"] + box_offset}}},{max(0.0, k["t"] - comp_start):.3f});'
            for k in result["keys"]]


def main():
    ap = argparse.ArgumentParser(description="Keep an element a fixed distance under her chin, frame by frame.")
    ap.add_argument("video")
    ap.add_argument("--from", dest="t0", type=float)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--windows", help="batch: a JSON file of [[t0, t1], ...]; writes a list of results to --json")
    ap.add_argument("--offset", type=int, default=40, help="px between her chin and the element's top ink edge")
    ap.add_argument("--smooth", type=int, default=3, help="frames of smoothing (odd number)")
    ap.add_argument("--hold", type=int, default=12, help="if the chin moves less than this, hold one position")
    ap.add_argument("--json", help="write the result here")
    ap.add_argument("--gsap", help="print GSAP tl.set lines for this selector")
    ap.add_argument("--comp-start", type=float, default=0.0, help="when the composition starts on the cut")
    ap.add_argument("--box-offset", type=int, default=0, help="added to y for elements whose CSS top is not their ink top")
    a = ap.parse_args()
    if a.windows:
        if not a.json:
            sys.exit("✗ --windows needs --json <out> for the results")
        wins = json.load(open(a.windows, encoding="utf-8"))
        rs = lock_many(a.video, wins, a.offset, a.smooth, a.hold)
        json.dump(rs, open(a.json, "w", encoding="utf-8"), indent=1)
        miss = sum(r is None for r in rs)
        print(f"chin lock: {len(rs) - miss} of {len(rs)} window(s) locked"
              + (f", {miss} with no face found (placed the usual way)" if miss else ""), file=sys.stderr)
        return
    if a.t0 is None or a.t1 is None:
        sys.exit("✗ give --from and --to (or --windows for a batch)")
    r = lock(a.video, a.t0, a.t1, a.offset, a.smooth, a.hold)
    if a.json:
        json.dump(r, open(a.json, "w", encoding="utf-8"), indent=1)
    ys = [k["y"] for k in r["keys"]]
    print(f"chin lock: {r['mode']} · {len(r['keys'])} key(s) · element top y{min(ys)}–y{max(ys)} "
          f"({a.offset}px under her chin)", file=sys.stderr)
    if a.gsap:
        print("\n".join(gsap_lines(r, a.gsap, a.comp_start, a.box_offset)))


if __name__ == "__main__":
    main()
