#!/usr/bin/env python3
"""export_progress.py — how far along a long export step is, so the Finish tab's bar moves with the real work.

finish.py gives each long step's child the env REE_PROGRESS=<file>. The child says where it is inside that step:
  stage(lo, hi, step)     its next stretch is lo..hi of the step (an encode, a conversion), with a plain label
  ffmpeg_args(expected)   extra ffmpeg args: the encode writes its out_time as it goes, read against `expected` seconds
  inner(frac)             a loop that counts its own frames says how far through the current stretch it is
finish.py reads it back with read(path) -> (0..1 of the step, label). No env: every call is a no-op, so a builder run
from the chat or a lean Send is unchanged.

The cost helpers are rough seconds on a recent Mac, used only to WEIGHT steps against each other (one export's
bar), never shown as a time: measured on a 10-minute 3072x1728 clip cut to 1:53 (2026-10-23).
"""
import json, os, time

ENV = "REE_PROGRESS"


def _path(p=None):
    return p or os.environ.get(ENV) or None


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _write(d, p=None):
    p = _path(p)
    if not p:
        return
    try:
        cur = dict(_load(p), **d, at=time.time())
        tmp = f"{p}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f)
        os.replace(tmp, p)
    except Exception:
        pass                                                  # the bar is a courtesy: it never stops an export


def reset(p):
    """A new step: nothing said yet (finish.py, at each step's start)."""
    for f in (p, p + ".ffmpeg"):
        try:
            os.remove(f)
        except OSError:
            pass


_WIN = [0.0, 1.0]                                             # this process's share of the step (window())


def window(lo, hi):
    """The caller's share of the step: a stage() said inside it (capcut_tail inside capcut_handoff) lands in lo..hi."""
    _WIN[:] = [float(lo), float(hi)]


def stage(lo, hi, step=None):
    a, b = _WIN
    _write({"lo": a + (b - a) * float(lo), "hi": a + (b - a) * float(hi), "inner": 0.0, "ffmpeg": None,
            "expected": None, **({"step": step} if step else {})})


def inner(frac):
    _write({"inner": max(0.0, min(1.0, float(frac)))})


def ffmpeg_args(expected_s, path=None):
    """["-progress", file, "-nostats"] for an encode of `expected_s` seconds of output, or [] with no export running
    (path: the progress file, for a caller in finish.py's own process; children read it from the env)."""
    p = _path(path)
    try:
        expected_s = float(expected_s or 0)
    except (TypeError, ValueError):
        expected_s = 0.0
    if not p or expected_s <= 0:
        return []
    fp = p + ".ffmpeg"
    try:
        open(fp, "w", encoding="utf-8").close()                                 # a retry on another encoder starts its count again
    except OSError:
        return []
    _write({"ffmpeg": fp, "expected": expected_s, "inner": 0.0}, p)
    return ["-progress", fp, "-nostats"]


def _ffmpeg_frac(fp, expected):
    """ffmpeg appends key=value blocks; the newest out_time_us is how much of the output exists."""
    try:
        with open(fp, "rb") as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 4096))
            tail = f.read().decode("utf-8", "replace")
        for line in reversed(tail.splitlines()):
            if line.startswith("out_time_us="):
                v = line.split("=", 1)[1].strip()
                if v.lstrip("-").isdigit():
                    return max(0.0, int(v) / 1e6 / float(expected))
    except Exception:
        pass
    return None


def read(p):
    """(how far through its step the child is, 0..1, or None when it hasn't said; its label or None)."""
    d = _load(p) if p else {}
    if not d:
        return None, None
    i = float(d.get("inner") or 0.0)
    if d.get("ffmpeg") and d.get("expected"):
        f = _ffmpeg_frac(d["ffmpeg"], d["expected"])
        if f is not None:
            i = max(i, f)
    lo, hi = float(d.get("lo", 0.0)), float(d.get("hi", 1.0))
    return lo + (hi - lo) * min(1.0, i), d.get("step")


# ── rough cost of each kind of work, in seconds (weights only) ─────────────────────────────────────────────────
def encode_cost(read_s, mpx, out_s):
    """An ffmpeg cut from her raw clips: it decodes every second up to the last kept moment (read_s, at mpx
    megapixels) and encodes out_s seconds. 600 s of 5.3 MP read for a 113 s cut took about 5 minutes."""
    return 0.09 * max(0.0, read_s) * max(0.5, mpx) + 0.2 * max(0.0, out_s)


def render_cost(dur_s):
    """A HyperFrames look at 30 fps: 3,383 caption frames took about a minute."""
    return 4.0 + 0.02 * 30 * max(0.0, dur_s)


def alpha_cost(dur_s):
    """A look's straight-alpha ProRes copy for CapCut (capcut_alpha), a frame at a time through numpy."""
    return 0.06 * 30 * max(0.0, dur_s)


def reencode_cost(out_s):
    """A 1080 encode of an already-cut video (the 1080 copy, the CapCut tail join, the burn, the phone copy)."""
    return 0.6 * max(0.0, out_s)


def mpx(path):
    """A clip's picture size in megapixels (decode cost), 2.1 (1080p) when it can't be read."""
    import subprocess
    try:
        o = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height", "-of", "json", path], capture_output=True, text=True).stdout or "{}")
        st = (o.get("streams") or [{}])[0]
        return max(0.1, int(st["width"]) * int(st["height"]) / 1e6)
    except Exception:
        return 2.1


def cut_cost(jd):
    """(cost of her full-quality cut from the raw clips, its length in seconds, her clips' megapixels): every clip is
    read up to its last kept moment."""
    try:
        segs = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    except Exception:
        segs = []
    out_s = sum(max(0.0, float(s["end"]) - float(s["start"])) / float(s.get("speed") or 1) for s in segs if "end" in s) or 60.0
    far = {}
    for s in segs:
        if "end" in s:
            far[s.get("clip")] = max(far.get(s.get("clip"), 0.0), float(s["end"]))
    clip = next(iter(far), None)
    raw = clip if clip and os.path.isabs(clip) else os.path.join(jd, "raw", clip or "")
    m = mpx(raw) if clip and os.path.isfile(raw) else 2.1
    return encode_cost(sum(far.values()), m, out_s), out_s, m


def tail_cost(jd, out_s, m):
    """The CapCut draft's extra footage after her last line (capcut_tail): her last clip read to its end, then her cut
    joined to it again. 0 when it's already made for this cut."""
    try:
        segs = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
        end = float(segs[-1]["end"])
    except Exception:
        return reencode_cost(out_s)
    name = os.path.basename(os.path.normpath(jd))
    try:
        stamp = json.load(open(os.path.join(jd, "outputs", f"{name}.capcut.json"), encoding="utf-8"))
        if float(stamp.get("end", -1)) == end and os.path.isfile(os.path.join(jd, "outputs", f"{name}.capcut.mp4")):
            return 1.0
    except Exception:
        pass
    return encode_cost(end, m, 4.0) + reencode_cost(out_s)

