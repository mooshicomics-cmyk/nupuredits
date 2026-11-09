#!/usr/bin/env python3
"""Guards: her logo watermark (product/watermark.py) is opt-in, measured and the same on every route.

  off      no watermark saved: nothing is added anywhere (the CapCut call never happens)
  place    every corner sits inside the safe area and never in the right-hand button rail
  frame    the baked frame is full size, transparent, with the logo at its box (and its opacity)
  burn     burn_layers --watermark lays it into a real video, in its corner
  capcut   the draft gets ONE image clip on its own track for the whole cut, centred on the same box
  store    a solid-background logo is flagged; bottom-right is refused; a pack's own watermark wins over "*"

Run: python3 product/tests/test_watermark.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import watermark as wm  # noqa: E402
import safe_zones  # noqa: E402
from PIL import Image  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="wm-test-")
    real = (wm.STORE, wm.LOGOS, wm.ROOT)
    try:
        wm.STORE, wm.LOGOS, wm.ROOT = os.path.join(tmp, "_local", "watermark.json"), os.path.join(tmp, "logos"), tmp
        calls = []
        check("off: nothing saved, nothing added", wm.get("Butter") is None and not wm.add_to_capcut(lambda *a, **k: calls.append(k), "d", "Butter", 30.0) and not calls)
        logo = os.path.join(tmp, "logo.png")
        im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
        for x in range(400):
            for y in range(200):
                im.putpixel((x, y), (232, 80, 46, 255))
        im.save(logo)
        note = wm.set_watermark("Butter", logo, "top-left", 150, 1.0)
        check("store: a see-through-capable PNG with solid pixels is flagged", note is not None)
        alpha = Image.new("RGBA", (400, 200), (0, 0, 0, 0)); alpha.paste((232, 80, 46, 255), (40, 40, 360, 160))
        alpha.save(logo)
        check("store: a transparent logo is not flagged", wm.set_watermark("Butter", logo, "top-left", 150, 1.0) is None)
        try:
            wm.set_watermark("Butter", logo, "bottom-right"); br = True
        except ValueError:
            br = False
        check("store: bottom-right (the button corner) is refused", not br)
        for c in wm.CORNERS:
            spec = dict(wm.get("Butter"), corner=c)
            x, y, w, h = wm.box(spec)
            inside = x >= safe_zones.LEFT and x + w <= safe_zones.RIGHT and y >= safe_zones.TOP and y + h <= safe_zones.BOTTOM
            check(f"place: {c} inside the safe area", inside, (x, y, w, h))
            check(f"place: {c} clear of the button rail", x + w <= getattr(safe_zones, "RIGHT_RAIL", 900), (x, w))
        wm.set_watermark("*", logo, "top-right", 120, 0.5)
        check("store: a pack's own watermark wins over every-pack", wm.get("Butter")["corner"] == "top-left")
        check("store: every-pack covers a pack with none", wm.get("Editorial")["corner"] == "top-right")
        spec = wm.get("Butter")
        fp = wm.frame_png(spec, os.path.join(tmp, "frame.png"))
        fr = Image.open(fp)
        x, y, w, h = wm.box(spec)
        check("frame: full size and transparent", fr.size == (1080, 1920) and fr.getpixel((5, 5))[3] == 0)
        px = fr.getpixel((x + w // 2, y + h // 2))
        check("frame: the logo sits at its box", px[3] > 200 and px[0] > 200, px)
        half = wm.frame_png(wm.get("Editorial"), os.path.join(tmp, "half.png"))
        hx, hy, hw, hh = wm.box(wm.get("Editorial"))
        check("frame: opacity carried", 100 < Image.open(half).getpixel((hx + hw // 2, hy + hh // 2))[3] < 160)
        calls = []
        ok = wm.add_to_capcut(lambda ep, **k: calls.append((ep, k)), "did", "Butter", 42.5)
        check("capcut: one image clip, its own track, the whole cut", ok and len(calls) == 1 and calls[0][0] == "add_image"
              and calls[0][1]["track_name"] == "watermark" and calls[0][1]["start"] == 0 and calls[0][1]["end"] == 42.5, calls)
        k = calls[0][1]
        cx = 540 + k["transform_x"] * 540; cy = 960 - k["transform_y"] * 960
        check("capcut: centred on the same box as the baked frame", abs(cx - (x + w / 2)) < 1 and abs(cy - (y + h / 2)) < 1, (cx, cy))
        if shutil.which("ffmpeg"):
            base = os.path.join(tmp, "base.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x101010:s=1080x1920:d=1:r=30",
                            "-pix_fmt", "yuv420p", base], check=True)
            lay = os.path.join(tmp, "empty.png"); Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(lay)
            mov = os.path.join(tmp, "empty.mov")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", "1", "-i", lay, "-c:v", "qtrle", mov], check=True)
            import importlib.util
            sp = importlib.util.spec_from_file_location("burn", os.path.join(PRODUCT, "burn_layers.py"))
            burn = importlib.util.module_from_spec(sp); sp.loader.exec_module(burn)
            cmd, _ = burn.plan(base, [(mov, 0.0)], watermark_png=fp)
            out = os.path.join(tmp, "out.mp4")
            r = subprocess.run(cmd + [out], capture_output=True, text=True)
            check("burn: ffmpeg ran", r.returncode == 0, r.stderr[-300:])
            if r.returncode == 0:
                still = os.path.join(tmp, "still.png")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", out, "-frames:v", "1", still], check=True)
                p = Image.open(still).convert("RGB").getpixel((x + w // 2, y + h // 2))
                check("burn: the logo is in its corner of the video", p[0] > 180 and p[1] < 140, p)
                d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                                         capture_output=True, text=True).stdout or 0)
                check("burn: the looped logo never makes the video longer", d < 1.3, d)
    finally:
        wm.STORE, wm.LOGOS, wm.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"watermark: {total - len(fails)}/{total} checks pass")
    for f in fails:
        print("  FAIL", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
