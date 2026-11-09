#!/usr/bin/env python3
"""Guards: an MP4 export burns her looks onto a 1080-wide copy of her cut (finish._export_base).

  copy      a cut wider than 1080 gets outputs/<job>.1080.mp4 at 1080x1920 with bt709 tags; her own cut is untouched
  reuse     the same cut again: the copy is reused, nothing re-encoded; a changed cut makes a new one
  small     a cut already 1080 wide (or smaller) is used as it is
  hatch     REE_FULL_RES_EXPORT=1 burns onto the full-size cut as before
  fallback  an encoder that fails both ways: the full-size cut, with one plain line, never a stop

Run: python3 product/tests/test_export_1080.py
"""
import json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import finish  # noqa: E402
import video_encoder  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


def clip(path, w, h, d=2):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:d={d}:r=30", "-f", "lavfi",
                    "-i", f"sine=f=440:d={d}", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
                   check=True, capture_output=True)


def probe(path, what):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", f"stream={what}", "-of",
                           "csv=p=0", path], capture_output=True, text=True).stdout.strip()


tmp = tempfile.mkdtemp(prefix="export1080-")
try:
    jd = os.path.join(tmp, "reel"); os.makedirs(os.path.join(jd, "outputs"))
    base = os.path.join(jd, "outputs", "reel.mp4")
    clip(base, 1728, 3072)
    before = os.stat(base).st_mtime_ns
    eb, note = finish._export_base(jd, base)
    check(eb.endswith("reel.1080.mp4") and note is None, f"copy: should burn onto the 1080 copy, got {eb} {note}")
    check(probe(eb, "width,height") == "1080,1920", f"copy: 1080x1920, got {probe(eb, 'width,height')}")
    check(probe(eb, "color_space") == "bt709", "copy: bt709 tags, or a browser can show black frames")
    check(os.stat(base).st_mtime_ns == before, "copy: her own cut must never change (CapCut keeps it full size)")
    m1 = os.stat(eb).st_mtime_ns
    eb2, _ = finish._export_base(jd, base)
    check(eb2 == eb and os.stat(eb).st_mtime_ns == m1, "reuse: the same cut should reuse the copy")
    time.sleep(1.1); clip(base, 1728, 3072, d=3)                    # her cut changed
    eb3, _ = finish._export_base(jd, base)
    check(abs(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", eb3],
                                   capture_output=True, text=True).stdout) - 3) < 0.2, "reuse: a changed cut should make a new copy")
    small = os.path.join(jd, "outputs", "small.mp4"); clip(small, 1080, 1920)
    check(finish._export_base(jd, small) == (small, None), "small: a 1080 cut is used as it is")
    os.environ["REE_FULL_RES_EXPORT"] = "1"
    check(finish._export_base(jd, base) == (base, None), "hatch: REE_FULL_RES_EXPORT=1 should keep the full-size cut")
    del os.environ["REE_FULL_RES_EXPORT"]
    os.remove(eb3)
    real = (video_encoder.pick_encoder, video_encoder.software_encoder)
    video_encoder.pick_encoder = lambda **k: ["-c:v", "no_such_encoder_nvenc"]
    video_encoder.software_encoder = lambda **k: ["-c:v", "no_such_encoder"]
    try:
        fb, line = finish._export_base(jd, base)
    finally:
        video_encoder.pick_encoder, video_encoder.software_encoder = real
    check(fb == base and line and "full-size" in line, f"fallback: the full-size cut with one plain line, got {fb} {line}")
    check(not os.path.exists(eb3 + ".part.mp4"), "fallback: no half-written copy left behind")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_export_1080: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_export_1080: all {n} checks passed")
