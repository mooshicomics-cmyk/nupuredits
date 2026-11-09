#!/usr/bin/env python3
"""Clean Captions lands its layers where they were drawn, whatever size the cut is.

The preset draws every caption and the hook on the 1080x1920 reel canvas and overlays them at those
x,y. It used to lay them straight over the cut at its own size, so on a 1728x3072 cut off a 4K phone the
caption meant for y1500 of 1080x1920 sat at y1500 of 3072: small, high (about 49% down, not 78%) and left
of centre, with the hook as far off. The cut is now scaled to the canvas first. This builds the preset
(in its starter look, so a saved pack never moves the numbers) on synthetic cuts of several sizes and reads
where the caption and the hook actually landed.

Run: python3 product/tests/test_clean_captions_canvas.py
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
import safe_zones
from PIL import Image

BUILD = os.path.join(ROOT, "presets", "clean-captions", "build.py")
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + detail) if detail else ''}")


def white_box(img, top, bottom):
    """Bounding box (x0, y0, x1, y1) of the near-white pixels between rows top and bottom, or None."""
    band = img.crop((0, top, img.width, bottom)).convert("L").point(lambda v: 255 if v > 200 else 0)
    box = band.getbbox()
    return None if box is None else (box[0], box[1] + top, box[2], box[3] + top)


def build_on(size, work):
    """Build the preset on a black cut of this size, one caption word on screen at 0.5s -> that frame."""
    w, h = size
    job = f"cc-canvas-{w}x{h}"
    outputs = os.path.join(work, job, "outputs")
    os.makedirs(outputs)
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r=30:d=1.5",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    os.path.join(outputs, f"{job}.mp4")], check=True)
    with open(os.path.join(outputs, f"{job}.transcript.json"), "w", encoding="utf-8") as fh:
        json.dump({"words": [{"text": "edit.", "start": 0.2, "end": 0.8, "type": "word"}]}, fh)
    out = os.path.join(work, f"{job}.final.mp4")
    subprocess.run([sys.executable, BUILD, os.path.join(work, job), "--hook-text", "We learned how to yap.",
                    "--hook-end", "1.2", "--pack", "starter", "--out", out], check=True, capture_output=True)
    frame = os.path.join(work, f"{job}.png")
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.5",
                    "-i", out, "-frames:v", "1", frame], check=True)
    return Image.open(frame)


# where the starter look centres its captions with nothing measured, read from the builder itself so a
# changed look never goes stale here
_spec = importlib.util.spec_from_file_location("clean_captions_build", BUILD)
_cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cc)
CAP_Y = _cc.CAPTION_HOME_Y
work = tempfile.mkdtemp(prefix="cc-canvas-")
try:
    for size in ((1728, 3072), (1080, 1920), (720, 1280)):
        tag = f"{size[0]}x{size[1]} cut"
        img = build_on(size, work)
        check(f"{tag}: the finished reel is 1080x1920", img.size == (1080, 1920), f"{img.size}")
        img = img.convert("RGB").resize((1080, 1920))   # as a phone shows it, so a miss reads in canvas terms
        cap = white_box(img, 1000, safe_zones.BOTTOM)
        check(f"{tag}: the caption is on screen low in the frame", cap is not None)
        if cap:
            cx, cy = (cap[0] + cap[2]) / 2, (cap[1] + cap[3]) / 2
            check(f"{tag}: the caption is centred left to right", abs(cx - 540) <= 20, f"centre x{cx:.0f}, box {cap}")
            check(f"{tag}: the caption sits on y{CAP_Y}", abs(cy - CAP_Y) <= 25, f"centre y{cy:.0f}, box {cap}")
        hook = white_box(img, 0, 1000)
        check(f"{tag}: the hook is on screen", hook is not None)
        if hook:
            check(f"{tag}: the hook starts just under the top band",
                  safe_zones.TOP <= hook[1] <= safe_zones.TOP + 20, f"box {hook}")
            check(f"{tag}: the hook is centred left to right", abs((hook[0] + hook[2]) / 2 - 540) <= 4, f"box {hook}")
finally:
    shutil.rmtree(work, ignore_errors=True)

if fails:
    print(f"test_clean_captions_canvas: FAILED {len(fails)}/{total}: " + " | ".join(fails))
    sys.exit(1)
print(f"test_clean_captions_canvas: all {total} checks passed")
