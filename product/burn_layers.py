#!/usr/bin/env python3
"""burn_layers.py: burn short transparent layers (karaoke lines, a baked moment) INTO her footage at their own
times, each scaled to the footage's own size first.

WHY THIS EXISTS. A layer is rendered at the reel canvas (1080x1920); her footage is often bigger (a 1728x3072
phone cut, a 4K clip). Laid on with a plain overlay=0:0, the layer sits unscaled in the top-left corner: small,
off-centre and over her face, while the beat sheet (drawn on a 1080 frame) looked right. It happened on a real
reel's karaoke. `reel_render.py composite` scales correctly but takes only full-length layers; this takes short
ones at their start times and keeps the footage at its full resolution, which is what CapCut's main track wants.

Why burn at all: CapCut does not always play a transparent overlay exactly as rendered (a karaoke line drifted
and glitched), so a moment that must land frame-exact goes INTO the footage clip. Text she will want to retype
stays a separate layer.

    python3 product/burn_layers.py --base <footage.mp4> --layer <a.mov>@<start> [--layer ...] -o <out.mp4>

Layers are laid bottom to top in the order given. The audio is copied untouched. A layer whose shape does not
match the footage's (a 16:9 layer on 9:16 footage) is refused: scaling it would stretch it.
"""
import argparse, os, subprocess, sys

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _dims(path):
    try:
        from probe import display_dims          # her footage: its DISPLAYED size (a rotated phone clip)
        w, h = display_dims(path)
        if w:
            return int(w), int(h)
    except Exception:
        pass
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "csv=p=0", path]).decode().strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def parse_layer(spec):
    path, _, start = spec.rpartition("@")
    if not path:                                  # no @: starts at 0
        path, start = spec, "0"
    return os.path.abspath(path), float(start)


def plan(base, layers, grade=None, watermark_png=None):
    """The ffmpeg argv for burning `layers` [(path, start)] into `base`, her logo frame last when given.
    Raises ValueError on a bad layer."""
    bw, bh = _dims(base)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", base]
    for path, start in layers:
        if not os.path.exists(path):
            raise ValueError(f"no layer at {path}")
        lw, lh = _dims(path)
        if abs(lw / lh - bw / bh) > 0.01:
            raise ValueError(f"{os.path.basename(path)} is {lw}x{lh} but the footage is {bw}x{bh}: a different "
                             f"shape, so scaling it would stretch it. Render it at the footage's shape.")
        cmd += ["-itsoffset", f"{start:.3f}", "-i", path]
    # an optional color grade (product/video_grade.py) goes on her FOOTAGE only, before any layer is laid on:
    # the graphics keep the pack's exact colors. One encode, same as without it.
    import video_grade
    g = video_grade.grade_filter(grade) if grade else None
    fc, prev = f"[0:v]{g + ',' if g else ''}format=yuv420p[v0]", "v0"
    for i, _ in enumerate(layers, 1):
        # sized evenly to cover her footage and trimmed at the middle: footage a hair off 9:16 sits inside the frame in
        # the visual editor and in CapCut, so every graphic lands on her where the page showed it. Stretched to the
        # footage's shape it came out squeezed up a little (2026-10-28). An exact 9:16 footage: the same plain scale.
        fc += (f";[{i}:v]scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=lanczos,crop={bw}:{bh}[s{i}];"
               f"[{prev}][s{i}]overlay=0:0:eof_action=pass[v{i}]")
        prev = f"v{i}"
    if watermark_png:                                   # her logo, over everything, for the whole reel
        n = len(layers) + 1
        cmd += ["-loop", "1", "-i", watermark_png]
        fc += f";[{n}:v]scale={bw}:{bh}:flags=lanczos[w];[{prev}][w]overlay=0:0:shortest=1[vw]"
        prev = "vw"
    return cmd + ["-filter_complex", fc, "-map", f"[{prev}]", "-map", "0:a?", "-c:v", "libx264", "-crf", "14",
                  "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart"], (bw, bh)


def main():
    ap = argparse.ArgumentParser(description="Burn short transparent layers into footage, scaled to the footage.")
    ap.add_argument("--base", required=True, help="her footage (the cut CapCut's main track will play)")
    ap.add_argument("--layer", action="append", required=True, metavar="FILE@START",
                    help="a transparent layer and the second it starts (repeatable, bottom to top)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--grade", default=None, help="an optional color grade on the footage (product/video_grade.py looks)")
    ap.add_argument("--watermark", metavar="PACK", help="also lay her logo (the one she turned on for this pack)")
    a = ap.parse_args()
    base = os.path.abspath(a.base)
    if not os.path.exists(base):
        sys.exit(f"  ⛔ no footage at {base}")
    layers = [parse_layer(s) for s in a.layer]
    wpng = None
    if a.watermark:
        import watermark
        spec = watermark.get(a.watermark)
        if spec:
            wpng = watermark.frame_png(spec, os.path.abspath(a.output) + ".watermark.png")
        else:
            print(f"  (no logo is turned on for {a.watermark}, so none is added)")
    try:
        cmd, (bw, bh) = plan(base, layers, grade=a.grade, watermark_png=wpng)
    except ValueError as e:
        sys.exit(f"  ⛔ {e}")
    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".part.mp4"                        # never half-write a file a draft may already point at
    try:                                           # the Finish tab's bar follows the burn (a no-op from the chat)
        import export_progress
        _d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", base],
                                  capture_output=True, text=True).stdout.strip() or 0)
        cmd = cmd[:4] + export_progress.ffmpeg_args(_d) + cmd[4:]
    except Exception:
        pass
    r = subprocess.run(cmd + [tmp])
    if r.returncode:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(f"  ⛔ ffmpeg failed (exit {r.returncode}); nothing was written")
    os.replace(tmp, out)
    if wpng and os.path.exists(wpng):
        os.remove(wpng)
    print(f"  ✓ burned {len(layers)} layer(s) into the footage at {bw}x{bh}, each scaled to fit → "
          f"{os.path.relpath(out)}")


if __name__ == "__main__":
    main()
