#!/usr/bin/env python3
"""iPhone HDR footage is found, announced and converted before it can reach a cut or a CapCut draft.

  1. product/hdr.py finds the HDR clips in a job's raw/ and only those.
  2. The heads-up is the approved wording, with the minutes filled in, and names the HDR clips in a mixed folder.
  3. --apply turns each HDR clip into a normal-colour copy under the same name, the same length, and keeps the
     HDR copy in hdr-originals/. The ffmpeg path's colours come back to the standard-colour original instead of
     the grey, washed look a re-tag gives. On a Mac with Apple's converter, that path is checked too.
  4. A CapCut draft that would still play an HDR file is named by capcut_color.hdr_media(), so the builders and
     capcut-live new-draft refuse it.

Runs on short generated clips in a throwaway folder; nothing real is touched.

Run:  python3 product/tests/test_hdr_footage.py
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "product"))
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
if not FFMPEG or not shutil.which("ffprobe"):
    print("hdr footage: skipped (needs ffmpeg and ffprobe)")
    sys.exit(0)

spec = importlib.util.spec_from_file_location("hdr_under_test", os.path.join(ROOT, "product", "hdr.py"))
hdr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hdr)
import capcut_color  # noqa: E402

APPROVED = ("Quick heads-up before I start. Your iPhone filmed these clips in HDR, a bright color format that comes "
            "out grey and washed out in CapCut unless it's converted first. So I'm converting them to normal color "
            "now. That adds about {m} to this edit. Your original clips stay untouched.\n"
            "To skip this wait next time, turn HDR off on your iPhone: Settings, Camera, Record Video, then turn off "
            "HDR Video. If you film in the Edits app, turn off its HDR switch too.")


def make_sdr(path):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=270x480:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=3", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "aac", "-shortest", path], check=True)


def make_hlg(src, path):
    """The same picture carried in BT.2020 and tagged the way an iPhone tags HLG."""
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-vf",
                    "colorspace=all=bt2020:format=yuv420p10:iall=bt709,"
                    "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc",
                    "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1",
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                    "-c:a", "copy", path], check=True)


def pixels(path, extra_vf=""):
    """One mid-clip frame as tiny RGB bytes, the clip's own tags honoured unless `extra_vf` overrides them."""
    vf = (extra_vf + "," if extra_vf else "") + "scale=27:48,format=rgb24"
    return subprocess.run([FFMPEG, "-v", "error", "-ss", "1.5", "-i", path, "-frames:v", "1", "-vf", vf,
                           "-f", "rawvideo", "-"], capture_output=True, check=True).stdout


def apart(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


tmp = os.path.realpath(tempfile.mkdtemp())
try:
    sdr = os.path.join(tmp, "sdr.mov")
    hlg = os.path.join(tmp, "hlg.mov")
    make_sdr(sdr)
    make_hlg(sdr, hlg)

    def job(*clips):
        jd = os.path.join(tmp, "job")
        shutil.rmtree(jd, ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        for name, src in clips:
            shutil.copy(src, os.path.join(jd, "raw", name))
        return jd

    print("1. which clips are HDR")
    jd = job(("IMG_1.MOV", hlg), ("IMG_2.MOV", sdr))
    found = hdr.hdr_clips(os.path.join(jd, "raw"))
    check("the HLG clip is found, and only it", [c["name"] for c in found] == ["IMG_1.MOV"], found)
    check("as HLG", found and found[0]["kind"] == "hlg", found)

    print("\n2. the heads-up")
    names = ["IMG_1.MOV", "IMG_2.MOV"]
    one = hdr.heads_up(found, names, apple=False)
    check("it is the approved wording, with the minutes filled in",
          one.startswith(APPROVED.format(m="1 minute")), one)
    check("a mixed folder names the HDR clips", "(The HDR ones: IMG_1.MOV. The rest are already normal color.)" in one,
          one)
    alone = hdr.heads_up(found, ["IMG_1.MOV"], apple=False)
    check("an all-HDR folder gets the wording alone", alone == APPROVED.format(m="1 minute"), alone)
    long = [dict(found[0], seconds=600.0)]
    check("ten minutes of 1080p footage: about 15 minutes on a PC, 3 with Apple's converter",
          hdr.minutes_needed(long, apple=False) == 15 and hdr.minutes_needed(long, apple=True) == 3,
          (hdr.minutes_needed(long, apple=False), hdr.minutes_needed(long, apple=True)))
    four_k = [dict(found[0], seconds=600.0, width=2160, height=3840)]
    check("a 4K clip is given longer on a PC", hdr.minutes_needed(four_k, apple=False) == 30,
          hdr.minutes_needed(four_k, apple=False))

    print("\n3. converting")
    real_apple = hdr.apple_converter
    hdr.apple_converter = lambda: None                      # the path every PC takes
    try:
        jd = job(("IMG_1.MOV", hlg), ("IMG_2.MOV", sdr))
        done = hdr.convert_job(jd, say=lambda line: None)
    finally:
        hdr.apple_converter = real_apple
    raw1 = os.path.join(jd, "raw", "IMG_1.MOV")
    check("only the HDR clip is converted", done == ["IMG_1.MOV"], done)
    check("its copy keeps the name and is normal colour", os.path.exists(raw1) and hdr.hdr_kind(raw1) is None,
          hdr.hdr_kind(raw1))
    check("the HDR copy is kept in hdr-originals/",
          hdr.hdr_kind(os.path.join(jd, "hdr-originals", "IMG_1.MOV")) == "hlg")
    check("the same length", abs(hdr._clip_facts(raw1)[0] - hdr._clip_facts(hlg)[0]) < 0.05,
          (hdr._clip_facts(raw1)[0], hdr._clip_facts(hlg)[0]))
    original = pixels(sdr)
    converted = apart(pixels(raw1), original)
    retagged = apart(pixels(hlg, "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709"), original)
    check(f"its colours come back to the original (off by {converted:.1f}) instead of the washed re-tag "
          f"(off by {retagged:.1f})", converted < 6 and retagged > 3 * converted, (converted, retagged))
    check("a second look finds nothing left to convert", hdr.hdr_clips(os.path.join(jd, "raw")) == [])
    # A newer iPhone adds a spatial-audio track (APAC) after the stereo one; ffmpeg cannot decode it, so taking
    # every audio track failed the whole copy on a PC. Only the first is taken.
    two = os.path.join(tmp, "two-audio.MOV")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", hlg, "-f", "lavfi", "-i",
                    "sine=frequency=550:sample_rate=48000:duration=3", "-map", "0", "-map", "1:a", "-c", "copy",
                    "-c:a:1", "aac", "-shortest", two], check=True)
    hdr.apple_converter = lambda: None
    try:
        jd = job(("IMG_3.MOV", two))
        hdr.convert_job(jd, say=lambda line: None)
    finally:
        hdr.apple_converter = real_apple
    tracks = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                             "-of", "csv=p=0", os.path.join(jd, "raw", "IMG_3.MOV")],
                            capture_output=True, text=True).stdout.split()
    check("a clip with a second audio track converts, keeping only the first", len(tracks) == 1, tracks)
    hdr_src = open(os.path.join(ROOT, "product", "hdr.py"), encoding="utf-8").read()
    check("the PC path never takes every audio track", '"0:a:0?"' in hdr_src and '"0:a?"' not in hdr_src)

    if hdr.apple_converter():
        jd = job(("IMG_1.MOV", hlg))
        hdr.convert_job(jd, say=lambda line: None)
        raw1 = os.path.join(jd, "raw", "IMG_1.MOV")
        check("on this Mac, Apple's converter makes a normal-colour copy of the same length",
              hdr.hdr_kind(raw1) is None and abs(hdr._clip_facts(raw1)[0] - hdr._clip_facts(hlg)[0]) < 0.05,
              (hdr.hdr_kind(raw1), hdr._clip_facts(raw1)))

    print("\n4. a CapCut draft never plays an HDR file marked SDR")
    draft = {"materials": {"videos": [{"type": "video", "path": hlg}, {"type": "video", "path": sdr},
                                      {"type": "photo", "path": hlg}]}}
    check("the HDR video file is named, and nothing else", capcut_color.hdr_media(draft) == [hlg],
          capcut_color.hdr_media(draft))
    msg = capcut_color.CONVERT_FIRST.format(name="IMG_1.MOV")
    check("the refusal says how to fix it", "python3 product/hdr.py <job> --apply" in msg, msg)
    src = open(os.path.join(ROOT, "workflows", "capcut-live.py"), encoding="utf-8").read()
    check("capcut-live new-draft checks every clip it lays down", "CONVERT_FIRST" in src and "hdr_kind" in src)
    for builder in ("cleanyap.py", "superyap.py"):
        b = open(os.path.join(ROOT, "product", builder), encoding="utf-8").read()
        check(f"{builder} refuses a draft with an HDR file", "capcut_color.hdr_media(d)" in b)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "hdr footage: found, announced, converted, and kept out of CapCut drafts"))
sys.exit(1 if fails else 0)
