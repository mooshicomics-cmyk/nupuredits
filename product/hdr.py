"""hdr.py — tell HDR phone footage apart from SDR, and bring it back to SDR before anything is built on it.

An iPhone films BT.2020 + HLG by default (PQ from a Dolby Vision export), 10-bit. Treated as SDR it renders
washed out and flat: lifted blacks, grey shirts, pale skin. CapCut draws it that way too when a draft points at
the phone clip and marks it SDR. Detect it from the stream's own color tags and convert it before the cut.

Two ways in:
  * The whole clip, once, at intake (`python3 product/hdr.py <job>` then `--apply`): every HDR clip in
    projects/<job>/raw/ becomes a standard-color copy under the same name, so the transcript, the cut and every
    CapCut draft built from raw/ see normal color. The HDR copy is kept in projects/<job>/hdr-originals/.
    On a Mac this is Apple's own converter (`avconvert`, the mapping the phone itself uses for "Most
    Compatible"); anywhere else it is ffmpeg with HDR2SDR below.
  * A filter on the way through (HDR2SDR), for builders that read a clip directly (vo-build.py, bake-hook.py,
    and stitch-cut.sh for a clip that skipped intake).

HDR2SDR is the `colorspace` filter because every ffmpeg the engine installs has it (some builds lack zscale
and libplacebo). It is driven by the stream's own tags, so it holds for any buyer's footage. HLG converts
correctly; PQ only approximately (no true tone map), which the callers say out loud.

    from hdr import HDR2SDR, hdr_kind
    pre = f"{HDR2SDR}," if hdr_kind(src) else ""      # prepend to the clip's -vf chain
"""
import json
import math
import os
import platform
import shutil
import subprocess
import sys

HDR2SDR = ("colorspace=ispace=bt2020nc:itrc=bt2020-10:iprimaries=bt2020:"
           "space=bt709:trc=bt709:primaries=bt709")

VIDEO_EXT = (".mov", ".mp4", ".m4v")
KEPT = "hdr-originals"          # where a job's HDR copies go once their standard-color copies take their place

# Seconds of converting per second of footage, for the time the heads-up promises. Apple's converter measured
# 0.26 on a 2019 Intel MacBook Pro (460 s of iPhone HLG in about two minutes) and 0.25 on an Apple-chip Mac (a
# 20 s clip in 5 s); ffmpeg's software path 0.75 on that Apple-chip Mac for a 1080x1920 clip, so a PC is given
# twice that, and a 4K clip (four times the pixels to decode) twice again.
APPLE_RATE = 0.3
FFMPEG_RATE = 1.5
FFMPEG_4K = 2.0

HEADS_UP = (
    "Quick heads-up before I start. Your iPhone filmed these clips in HDR, a bright color format that comes out "
    "grey and washed out in CapCut unless it's converted first. So I'm converting them to normal color now. That "
    "adds about {minutes} to this edit. Your original clips stay untouched.\n"
    "To skip this wait next time, turn HDR off on your iPhone: Settings, Camera, Record Video, then turn off HDR "
    "Video. If you film in the Edits app, turn off its HDR switch too."
)


def hdr_kind(src):
    """'hlg' (iPhone default) | 'pq' (Dolby Vision export) | 'bt2020' | None, from the stream's color tags."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer,color_primaries",
             "-of", "default=nw=1:nk=1", src], text=True)
        out = (out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)).lower()
    except Exception:
        return None
    if "arib-std-b67" in out: return "hlg"
    if "smpte2084" in out: return "pq"
    if "bt2020" in out: return "bt2020"
    return None


def _clip_facts(path):
    """(seconds, width, height) of a clip, from one ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True)
    try:
        d = json.loads(out.stdout or "{}")
        s = (d.get("streams") or [{}])[0]
        return float(d.get("format", {}).get("duration") or 0), int(s.get("width") or 0), int(s.get("height") or 0)
    except (ValueError, TypeError):
        return 0.0, 0, 0


def videos(folder):
    """The video files directly inside `folder`, by name."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if n.lower().endswith(VIDEO_EXT) and not n.startswith(".") and os.path.isfile(os.path.join(folder, n))]


def hdr_clips(folder):
    """[{path, name, kind, seconds, width, height}] for every HDR clip in the folder."""
    found = []
    for path in videos(folder):
        kind = hdr_kind(path)
        if kind:
            seconds, w, h = _clip_facts(path)
            found.append({"path": path, "name": os.path.basename(path), "kind": kind,
                          "seconds": seconds, "width": w, "height": h})
    return found


def apple_converter():
    """Apple's converter, on a Mac that has it, else None."""
    return shutil.which("avconvert") if sys.platform == "darwin" else None


def minutes_needed(clips, apple=None):
    """Whole minutes, at least one, that converting these clips should take on this machine."""
    apple = apple_converter() if apple is None else apple
    total = 0.0
    for c in clips:
        if apple:
            total += APPLE_RATE * c["seconds"]
        else:
            big = c["width"] * c["height"] > 1080 * 1920 * 1.5
            total += FFMPEG_RATE * (FFMPEG_4K if big else 1.0) * c["seconds"]
    return max(1, math.ceil(total / 60))


def heads_up(clips, all_names, apple=None):
    """The message she reads before any converting starts, naming the HDR clips when only some are."""
    m = minutes_needed(clips, apple)
    text = HEADS_UP.format(minutes=f"{m} minute" if m == 1 else f"{m} minutes")
    if len(clips) < len(all_names):
        names = ", ".join(c["name"] for c in clips)
        text += f"\n(The HDR ones: {names}. The rest are already normal color.)"
    return text


def _apple(apple, src, dst):
    """Apple's converter, `src` to `dst`. -> True when it wrote the copy."""
    r = subprocess.run([apple, "--source", src, "--output", dst, "--preset", "Preset1920x1080", "--replace"],
                       capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(dst)


def _apple_on_plain_copy(apple, src, dst):
    """Apple's converter on a copy of `src` holding only its first video and first audio stream (stream copy, so
    the picture and its HDR tags are untouched). The copy lives in a temp folder that is always removed."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="hdr-remux-")
    try:
        plain = os.path.join(tmp, "clip" + (os.path.splitext(src)[1] or ".mov"))
        rm = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                             "-c", "copy", plain], capture_output=True, text=True)
        return rm.returncode == 0 and os.path.exists(plain) and _apple(apple, plain, dst)
    except OSError:
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def to_sdr(src, dst):
    """Write a standard-color copy of `src` at `dst` (same container as dst's extension). -> converter used."""
    apple = apple_converter()
    if apple:
        if _apple(apple, src, dst):
            return "apple"
        # A long iPhone take also carries metadata tracks (mebx: focus, stabilization, location) that Apple's
        # converter can stop on ("The operation could not be completed"). Copy out only the picture and the first
        # sound, untouched, and give Apple's converter that: its colors match the phone, and the ffmpeg fallback
        # below comes out visibly paler (a buyer's long takes, 2026-10-23).
        if _apple_on_plain_copy(apple, src, dst):
            return "apple"
        sys.stderr.write(f"[hdr] Apple's converter could not read {os.path.basename(src)}; using ffmpeg instead\n")
    # 1080 wide at most (the reel's own width), the clip's own shape, HDR2SDR before anything else touches it.
    # FIRST audio stream only: a newer iPhone .mov also carries a spatial-audio track (APAC) ffmpeg cannot decode,
    # and a broad `0:a?` selected it -> "no decoder found for: none" and no copy at all (measured).
    vf = f"{HDR2SDR},scale='min(1080,iw)':-2:flags=lanczos,format=yuv420p"
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                        "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                        "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", dst], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(f"could not convert {os.path.basename(src)}: {r.stderr.strip()[-300:]}")
    return "ffmpeg"


def convert_job(job_dir, say=print):
    """Turn every HDR clip in the job's raw/ into a standard-color copy under the same name; the HDR copy moves to
    hdr-originals/. A copy whose length differs from its source by more than a frame is refused, so the transcript
    and the cut stay true. -> the names converted."""
    raw = os.path.join(job_dir, "raw")
    kept = os.path.join(job_dir, KEPT)
    done = []
    for c in hdr_clips(raw):
        stem, ext = os.path.splitext(c["name"])
        tmp = os.path.join(raw, f".{stem}.sdr{ext}")
        say(f"[hdr] converting {c['name']} ({c['kind'].upper()}, {c['seconds']:.0f} s) to normal color")
        how = to_sdr(c["path"], tmp)
        seconds, _w, _h = _clip_facts(tmp)
        if abs(seconds - c["seconds"]) > 0.05 or hdr_kind(tmp):
            os.remove(tmp)
            raise RuntimeError(f"the normal-color copy of {c['name']} did not come out right "
                               f"({seconds:.2f} s against {c['seconds']:.2f} s); the clip is left as it was")
        os.makedirs(kept, exist_ok=True)
        os.replace(c["path"], os.path.join(kept, c["name"]))
        os.replace(tmp, c["path"])
        say(f"[hdr] ✓ {c['name']} is normal color now ({'Apple' if how == 'apple' else 'ffmpeg'}); "
            f"the HDR copy is in {KEPT}/")
        done.append(c["name"])
    return done


def _job_dir(arg):
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "projects", arg)


def main(argv):
    for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("usage: hdr.py <job> [--apply]   (without --apply: say whether any clip is HDR, and the heads-up)")
    job = _job_dir(args[0])
    raw = os.path.join(job, "raw")
    clips = hdr_clips(raw)
    if "--apply" not in argv:
        if not clips:
            print("[hdr] every clip is normal color; nothing to convert")
            return 0
        print(heads_up(clips, [os.path.basename(p) for p in videos(raw)]))
        return 0
    if not clips:
        print("[hdr] every clip is normal color; nothing to convert")
        return 0
    try:
        convert_job(job)
    except RuntimeError as e:
        sys.exit(f"[hdr] ✗ {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
