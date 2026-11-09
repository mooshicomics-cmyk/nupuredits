#!/usr/bin/env python3
"""voice_level.py — put her rough cut's voice at the engine's north star: -16 LUFS integrated, true peak <= -1.5 dBTP.

One measured STATIC gain for the whole cut (never loudness normalisation, which rides the level line by line), then
a true-peak limiter (4x oversampled) that only catches stray peaks. The video stream is copied untouched, and the
file is replaced in one step (a temp file + product/swap.py, which waits out the moment Windows still holds a fresh
MP4 open), so a CapCut draft that hard-links the cut never sees half a file. Everything else (sound effects, the music bed, the preview) is levelled against this voice.

    python3 product/voice_level.py <cut.mp4>            level it (prints before -> after)
    python3 product/voice_level.py <cut.mp4> --check    measure only

Targets and sources: product/audio_levels.py (VOICE_TARGET_LUFS, TRUE_PEAK_CEILING_DBTP).
"""
import json, os, re, subprocess, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audio_levels  # noqa: E402
try:
    from swap import replace as swap_in  # noqa: E402  (os.replace that waits out Windows holding the fresh MP4 open)
except ImportError:
    swap_in = os.replace

TOLERANCE_LU = 0.5          # within this of the target (and under the ceiling) = already right: left alone


def measure(path):
    """(integrated LUFS, true peak dBTP) of a file's audio, or (None, None)."""
    try:
        out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0?", "-vn",
                              "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", os.devnull],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600).stderr
    except Exception:
        return None, None
    i = re.findall(r"\bI:\s*(-?[\d.]+) LUFS", out)
    p = re.findall(r"\bPeak:\s*(-?[\d.]+) dBFS", out)
    return (float(i[-1]) if i else None), (float(p[-1]) if p else None)


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def level(path, target=audio_levels.VOICE_TARGET_LUFS, ceiling=audio_levels.TRUE_PEAK_CEILING_DBTP):
    """Level the cut in place. Returns {"before", "after", "gain_db", "changed"}."""
    i0, p0 = measure(path)
    if i0 is None or i0 < -60:
        return {"before": i0, "after": i0, "gain_db": 0.0, "changed": False, "why": "no voice to measure"}
    gain = round(target - i0, 2)
    if abs(gain) <= TOLERANCE_LU and (p0 is None or p0 <= ceiling + 0.1):
        return {"before": i0, "after": i0, "peak": p0, "gain_db": 0.0, "changed": False}
    lim = round(10 ** (ceiling / 20.0), 4)
    af = f"volume={gain}dB,aresample=192000,alimiter=limit={lim}:level=false:latency=true,aresample=48000"
    tmp = path + ".level.tmp.mp4"
    _drop(tmp)                  # one an earlier run could not swap in (a locked file on Windows) is never reused
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-map", "0:v?", "-map", "0:a:0",
           "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.isfile(tmp):
        _drop(tmp)
        return {"before": i0, "after": i0, "gain_db": 0.0, "changed": False, "why": (r.stderr or "ffmpeg failed").strip()[-200:]}
    try:
        swap_in(tmp, path)
    except OSError as e:
        _drop(tmp)
        return {"before": i0, "after": i0, "gain_db": 0.0, "changed": False,
                "why": f"the cut stayed in use by another program, so it was not swapped: {e}"[:200]}
    i1, p1 = measure(path)
    return {"before": i0, "after": i1, "peak": p1, "gain_db": gain, "changed": True}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = argv[0]
    if not os.path.isfile(path):
        print(f"voice_level: no file at {path}", file=sys.stderr)
        return 2
    if "--check" in argv:
        i, p = measure(path)
        print(json.dumps({"lufs": i, "true_peak": p, "target": audio_levels.VOICE_TARGET_LUFS}))
        return 0
    r = level(path)
    if r["changed"]:
        print(f"  ✓ voice level: {r['before']:.1f} → {r['after']:.1f} LUFS (one static {r['gain_db']:+.1f} dB), "
              f"true peak {r['peak']:.1f} dBTP")
    else:
        print(f"  ✓ voice level: {r['before']} LUFS, left as it is" + (f" ({r['why']})" if r.get("why") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
