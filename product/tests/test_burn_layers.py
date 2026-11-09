#!/usr/bin/env python3
"""Regression guard: a layer burned into her footage lands where it was designed, at its own time.

The bug this locks down: a 1080x1920 karaoke layer was burned into 1728x3072 footage with a plain overlay, so it
sat unscaled in the top-left corner, small and over her face. product/burn_layers.py scales every layer to the
footage's size first and lays it at its start time.

What must hold (real ffmpeg, tiny synthetic clips): a mark drawn at a known spot on a 9:16 layer lands at the
same RELATIVE spot on bigger 9:16 footage; it is absent before its start time and present after; the audio
survives; a layer of a different shape is refused with a plain reason; nothing is written on a refusal.

Run: python3 product/tests/test_burn_layers.py
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import burn_layers as B

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
    print("  SKIP  ffmpeg not installed here; nothing to check")
    sys.exit(0)

tmp = tempfile.mkdtemp()
run = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
base = os.path.join(tmp, "base.mp4")              # "footage": 432x768 black, 3 s, with a tone
run("-f", "lavfi", "-i", "color=black:s=432x768:r=30:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3",
    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", base)
layer = os.path.join(tmp, "layer.mov")            # "reel canvas": 270x480, white box at x 135-175, y 300-340, 1 s
run("-f", "lavfi", "-i", "color=black@0.0:s=270x480:r=30:d=1,format=rgba", "-f", "lavfi", "-i",
    "color=white:s=40x40:r=30:d=1,format=rgba", "-filter_complex", "[0][1]overlay=135:300:format=auto",
    "-c:v", "qtrle", "-pix_fmt", "argb", layer)     # (drawbox leaves alpha at 0: the mark must be overlaid)
wide = os.path.join(tmp, "wide.mov")
run("-f", "lavfi", "-i", "color=black@0.0:s=480x270:r=30:d=1,format=rgba", "-c:v", "qtrle", wide)


def pixel(path, t, x, y):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", path, "-frames:v", "1",
                                   "-vf", f"format=gray,crop=2:2:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    return raw[0] if raw else -1


out = os.path.join(tmp, "out.mp4")
subprocess.run([sys.executable, os.path.join(PRODUCT, "burn_layers.py"), "--base", base,
                "--layer", f"{layer}@1.0", "-o", out], check=True, capture_output=True)
# the box centre on the layer is (155, 320) of 270x480 -> on 432x768 footage (x1.6) it is (248, 512)
check("the mark lands at the scaled spot", pixel(out, 1.5, 248, 512) > 200, f"got {pixel(out, 1.5, 248, 512)}")
check("not at the unscaled top-left spot", pixel(out, 1.5, 155, 320) < 60)
check("absent before its start time", pixel(out, 0.5, 248, 512) < 60)
check("gone after it ends", pixel(out, 2.6, 248, 512) < 60)
streams = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of",
                                   "csv=p=0", out]).decode().split()
check("audio survives", "audio" in streams)
r = subprocess.run([sys.executable, os.path.join(PRODUCT, "burn_layers.py"), "--base", base,
                    "--layer", f"{wide}@0", "-o", os.path.join(tmp, "bad.mp4")], capture_output=True, text=True)
check("a different-shaped layer is refused", r.returncode != 0 and "stretch" in (r.stdout + r.stderr))
check("nothing written on a refusal", not os.path.exists(os.path.join(tmp, "bad.mp4")))
# Footage a hair wider than 9:16 (432x756, inside the 1% let through): the visual editor shows it fitted inside the 9:16
# frame with the looks over the whole frame, and CapCut does the same. The burn used to stretch the layer to the
# footage's shape (every graphic squeezed up a little, 2026-10-28); now it is sized evenly to cover the footage and
# trimmed at the middle, so each mark lands on her footage where the editor showed it.
base2 = os.path.join(tmp, "base2.mp4")
run("-f", "lavfi", "-i", "color=black:s=432x756:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", base2)
line = os.path.join(tmp, "line.mov")               # a thin white line across the layer at y 459-461 of 480
run("-f", "lavfi", "-i", "color=black@0.0:s=270x480:r=30:d=2,format=rgba", "-f", "lavfi", "-i",
    "color=white:s=270x2:r=30:d=2,format=rgba", "-filter_complex", "[0][1]overlay=0:459:format=auto",
    "-c:v", "qtrle", "-pix_fmt", "argb", line)
out2 = os.path.join(tmp, "out2.mp4")
subprocess.run([sys.executable, os.path.join(PRODUCT, "burn_layers.py"), "--base", base2,
                "--layer", f"{line}@0", "-o", out2], check=True, capture_output=True)
# as the editor shows it: the footage fits the frame's width (x0.625), 3.75 px down -> layer y 460 is footage y 730
check("footage a hair off 9:16: a mark lands where the editor showed it", pixel(out2, 1.0, 200, 729) > 200,
      f"got {pixel(out2, 1.0, 200, 729)}")
check("...not squeezed up the old way (y 724)", pixel(out2, 1.0, 200, 723) < 60, f"got {pixel(out2, 1.0, 200, 723)}")
check("FILE@START parses, a bare FILE starts at 0",
      B.parse_layer("/x/a.mov@12.5") == ("/x/a.mov", 12.5) and B.parse_layer("/x/a.mov")[1] == 0.0)
shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILED'}")
sys.exit(1 if fails else 0)
