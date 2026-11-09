#!/usr/bin/env python3
"""frame.py: the frame a video's looks are built on. Tall 1080x1920, or wide 1920x1080 when the wide switch is on,
the footage is wide and she confirmed it's a YouTube video (edited the same way as a reel; nothing here uploads).

    python3 product/frame.py ask <clip or job>            the very first question of an edit, or exit 1 with nothing to ask
    python3 product/frame.py choose <job> reel|youtube    record her answer (format.json in the job)
    python3 product/frame.py on | off | status            the switch

The switch is a file in _local/, which never ships, so every other engine stays exactly as it was. Builders run as
their own process and read the frame through safe_zones (REEL_FRAME in their environment, see env() and adopt()); a
long-running process asks size() and zones() per job.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SWITCH = os.path.join(ROOT, "_local", "wide-video")
TALL, WIDE = (1080, 1920), (1920, 1080)
_seen = {}


def on():
    return os.path.isfile(SWITCH)


def _job_dir(path):
    """The job folder of anything inside it (a look's page, a render, the job folder itself)."""
    parts = os.path.abspath(path).split(os.sep)
    if "hf-graphics" in parts:
        return os.sep.join(parts[:parts.index("hf-graphics")]) or os.sep
    if "projects" in parts and len(parts) > parts.index("projects") + 1:
        return os.sep.join(parts[:parts.index("projects") + 2])
    return os.path.abspath(path)


def _clip(jd):
    cut = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    if os.path.isfile(cut):
        return cut
    raw = os.path.join(jd, "raw")
    try:
        clips = sorted(f for f in os.listdir(raw) if f.lower().endswith((".mp4", ".mov", ".m4v")))
    except OSError:
        clips = []
    return os.path.join(raw, clips[0]) if clips else None


def choice(path):
    """What she confirmed for this job at the start of the edit: "reel", "youtube", or None if she hasn't been asked."""
    import json
    try:
        return json.load(open(os.path.join(_job_dir(path), "format.json"), encoding="utf-8")).get("format")
    except (OSError, ValueError, AttributeError):
        return None


def is_wide(path):
    """True when the switch is on, she didn't call this one a reel, and its cut or clip displays wider than tall."""
    if not on() or choice(path) == "reel":
        return False
    clip = _clip(_job_dir(path))
    if not clip:
        return False
    key = (clip, os.path.getmtime(clip))
    if key not in _seen:
        sys.path.insert(0, HERE)
        from probe import display_dims
        w, h = display_dims(clip)
        _seen[key] = bool(w and h and w > h)
    return _seen[key]


def size(path):
    return WIDE if is_wide(path) else TALL


def env(path):
    """What a builder needs in its environment to draw this job's frame."""
    if not is_wide(path):
        return {}
    out = {"REEL_FRAME": "%dx%d" % WIDE}
    try:                                                      # captions on this video take the band's lowest stretch
        import json
        looks = json.load(open(os.path.join(_job_dir(path), "review", "looks.json"), encoding="utf-8"))
        if any(L.get("captions") for L in looks.get("layers", [])):
            out["REEL_HAS_CAPTIONS"] = "1"
    except (OSError, ValueError):
        pass
    return out


def adopt(args=None):
    """For a tool handed a composition or a clip rather than a job: draw on that file's frame. Call it before importing
    safe_zones. Does nothing with the switch off."""
    if not on() or os.environ.get("REEL_FRAME"):
        return
    job = os.environ.get("JOB_DIR") or (os.path.join(ROOT, "projects", os.environ["JOB"]) if os.environ.get("JOB") else None)
    here = [job] if job else [p for p in (sys.argv[0], os.getcwd()) if os.sep + "projects" + os.sep in os.path.abspath(p)]
    for p in here:                                            # a builder named its job, or a driver lives in its folder
        if is_wide(p):
            os.environ["REEL_FRAME"] = "%dx%d" % WIDE
            return
    for a in (args if args is not None else sys.argv[1:]):
        if not os.sep in a and os.path.isdir(os.path.join(ROOT, "projects", a)):   # a job named on the command line
            if is_wide(os.path.join(ROOT, "projects", a)):
                os.environ["REEL_FRAME"] = "%dx%d" % WIDE
                return
            continue
        page = os.path.join(a, "index.html") if os.path.isdir(a) else a
        try:
            if page.lower().endswith(".html"):
                head = open(page, encoding="utf-8", errors="replace").read()
                if 'data-width="%d" data-height="%d"' % WIDE in head:
                    os.environ["REEL_FRAME"] = "%dx%d" % WIDE
                    return
            elif page.lower().endswith((".mp4", ".mov", ".m4v")) and os.path.isfile(page):
                sys.path.insert(0, HERE)
                from probe import display_dims
                w, h = display_dims(page)
                if w and h and w > h:
                    os.environ["REEL_FRAME"] = "%dx%d" % WIDE
                    return
        except (OSError, ValueError):
            continue


def head_in(path, start, dur):
    """Where her head goes during these seconds of her cut: {"left", "right", "head_top", "chin_bottom"} on the wide
    frame, or None when it can't be read. The track (product/head_track.py) is made once per cut. A single stray reading
    is left out: the next-furthest of each edge decides."""
    jd = _job_dir(path)
    sys.path.insert(0, HERE)
    import json, shutil, subprocess
    import caption_scenes
    p = os.path.join(jd, "review", "head-track.json")
    cur = caption_scenes._cut_id(jd)

    def read():
        try:
            d = json.load(open(p, encoding="utf-8"))
            return d["samples"] if d.get("cut_id") == cur else None
        except (OSError, ValueError, KeyError):
            return None
    samples = read()
    if samples is None and shutil.which("uv"):
        try:
            subprocess.run(["uv", "run", os.path.join(HERE, "head_track.py"), jd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
        except (OSError, subprocess.SubprocessError):
            pass
        samples = read()
    now = [s for s in samples or [] if start - 0.2 <= s[0] <= start + dur + 0.2]
    if not now:
        return None
    far = lambda i, hi: sorted(s[i] for s in now)[(-2 if hi else 1) if len(now) > 4 else (-1 if hi else 0)]
    return {"left": far(1, False), "right": far(2, True), "head_top": far(3, False), "chin_bottom": far(4, True)}


def brightness_grid(path, t, w=48, h=27):
    """How bright the picture is around one moment of her cut, as rows of 0-255: what a look's words would land on."""
    jd = _job_dir(path)
    import subprocess
    video = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    if not os.path.isfile(video):
        return None
    try:
        buf = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % max(0.0, t), "-i", video, "-frames:v", "1", "-vf", "scale=%d:%d" % (w, h),
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [list(buf[y * w:(y + 1) * w]) for y in range(h)] if len(buf) >= w * h else None


def zones(path):
    """safe_zones' numbers for this job, for a process serving more than one job."""
    sys.path.insert(0, HERE)
    import safe_zones
    return safe_zones.numbers(wide=is_wide(path))


def _shape(path):
    """"wide" or "tall" from how a clip, or a job's clip, displays; None when there is nothing to read."""
    sys.path.insert(0, HERE)
    from probe import display_dims
    clip = path if os.path.isfile(path) else _clip(path if os.path.isdir(path) else os.path.join(ROOT, "projects", path))
    if not clip:
        return None
    w, h = display_dims(clip)
    return ("wide" if w > h else "tall") if w and h else None


def ask(path):
    """The first question of an edit: her footage says which, she confirms. None when the switch is off or she answered."""
    if not on():
        return None
    job = path if os.path.isdir(path) else os.path.join(ROOT, "projects", path)
    if os.path.isdir(job) and choice(job):
        return None
    wide = _shape(path) == "wide"
    reel = {"label": "Vertical reel" + ("" if wide else " (Recommended)"), "description": "9:16, for Reels, Shorts and TikTok" + (". This footage is horizontal, so it gets reframed." if wide else ".")}
    tube = {"label": "YouTube video" + (" (Recommended)" if wide else ""), "description": "16:9 horizontal, for YouTube" + ("." if wide else ". This footage is vertical, so it needs a horizontal clip.")}
    return {"question": ("This footage is horizontal, so it looks like a YouTube video. Is that right?" if wide else "This footage is vertical, so it looks like a reel. Is that right?"),
            "header": "Format", "options": [tube, reel] if wide else [reel, tube]}


def choose(job, fmt):
    """Her answer, kept with the job. YouTube on vertical footage stays vertical: there's no wide picture to build on."""
    import json
    jd = job if os.path.isabs(job) else os.path.join(ROOT, "projects", job)
    os.makedirs(jd, exist_ok=True)
    with open(os.path.join(jd, "format.json"), "w", encoding="utf-8") as f:
        json.dump({"format": fmt}, f)
    if fmt == "youtube" and _shape(jd) == "tall":
        return "This footage is vertical, so a YouTube edit needs a horizontal clip. Drop one in and I'll use that."
    return "This one's a YouTube video: 16:9, horizontal." if fmt == "youtube" else "This one's a vertical reel."


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "ask":
        import json
        q = ask(sys.argv[2])
        if not q:
            sys.exit(1)
        print(json.dumps(q, indent=1))
        sys.exit(0)
    if cmd == "choose":
        if len(sys.argv) != 4 or sys.argv[3] not in ("reel", "youtube"):
            sys.exit("python3 product/frame.py choose <job> reel|youtube")
        print(choose(sys.argv[2], sys.argv[3]))
        sys.exit(0)
    if cmd == "on":
        os.makedirs(os.path.dirname(SWITCH), exist_ok=True)
        open(SWITCH, "a", encoding="utf-8").close()
    elif cmd == "off" and on():
        os.remove(SWITCH)
    print("wide video is", "on" if on() else "off")
