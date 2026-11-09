#!/usr/bin/env python3
"""caption_guard.py — prove a graphics layer never lands on the caption band. Deterministic, no eyeballing.

Reels fail this the same way every time: a full-screen graphic is authored against an assumed caption
height, someone checks three frames of the render, and the two collide somewhere in between. Caption line
COUNT varies through a reel, so spot-checking frames cannot catch it — the band has to be treated as a
reserved box and the graphic layer measured against it across the whole timeline.

This alpha-extracts the transparent graphics layer, crops to the caption band rows, and reports the share
of that box the graphic actually covers, frame by frame. Anything over the threshold is a collision with a
timestamp, before a single second of compositing.

  python3 product/caption_guard.py <graphics.mov> --band-top 1200 --band-bottom 1400 [--max 0.02] [--strict]

`hyperframes check` validates the composition's own canvas; it cannot see a caption track that is drawn
later by a different tool. This is that missing half.
"""
import argparse, os, re, subprocess, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_zones


def coverage(layer, band_top, band_bottom, left=None, right=None):
    """-> [(t_seconds, covered_fraction)] for every frame of the layer over the band box."""
    left = safe_zones.LEFT if left is None else left
    right = safe_zones.RIGHT if right is None else right
    w, h = right - left, band_bottom - band_top
    if h <= 0:
        raise SystemExit("band-bottom must be below band-top")
    # format=gray FIRST: these layers render as 12-bit yuva444p12le, so a raw threshold compares against a
    # 0..4095 range and reads every stray alpha value as solid. Normalise to 8-bit before thresholding.
    vf = (f"alphaextract,format=gray,crop={w}:{h}:{left}:{band_top},"
          f"lutyuv=y='if(gt(val,32),255,0)',signalstats,metadata=print:key=lavfi.signalstats.YAVG")
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", layer, "-vf", vf, "-f", "null", "-"],
                       capture_output=True, text=True)
    out, t = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1)); continue
        m = re.search(r"YAVG=([\d.]+)", line)
        if m and t is not None:
            out.append((t, float(m.group(1)) / 255.0))
    if not out:
        raise SystemExit(f"could not read alpha from {layer} — is it a transparent .mov (qtrle/prores4444)?")
    return out


def report(layer, band_top, band_bottom, max_cov=0.02, left=None, right=None):
    cov = coverage(layer, band_top, band_bottom, left, right)
    bad = [(t, c) for t, c in cov if c > max_cov]
    peak = max(cov, key=lambda x: x[1])
    name = os.path.basename(layer)
    if not bad:
        print(f"✅ caption band is clear: {name} peaks at {peak[1]*100:.2f}% of the band "
              f"(y {band_top}..{band_bottom}) at t={peak[0]:.2f}s, limit {max_cov*100:.0f}%")
        return 0
    # collapse consecutive frames into ranges so the report reads like an edit note
    runs, start, prev = [], bad[0][0], bad[0][0]
    for t, _ in bad[1:]:
        if t - prev > 0.2:
            runs.append((start, prev)); start = t
        prev = t
    runs.append((start, prev))
    print(f"⛔ {name} lands on the caption band (y {band_top}..{band_bottom}) in "
          f"{len(runs)} place(s), peak {peak[1]*100:.1f}% at t={peak[0]:.2f}s:")
    for a, b in runs:
        worst = max((c for t, c in bad if a <= t <= b), default=0)
        print(f"     {a:6.2f}s → {b:6.2f}s   up to {worst*100:.1f}% covered")
    print("   Fix = move the graphic above the band or shorten it, then re-render the layer.")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("layer")
    ap.add_argument("--band-top", type=int, required=True)
    ap.add_argument("--band-bottom", type=int, required=True)
    ap.add_argument("--max", dest="max_cov", type=float, default=0.02,
                    help="allowed fraction of the band box a graphic may cover (default 0.02)")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any collision")
    a = ap.parse_args()
    rc = report(a.layer, a.band_top, a.band_bottom, a.max_cov)
    sys.exit(rc if a.strict else 0)
