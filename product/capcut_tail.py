#!/usr/bin/env python3
"""capcut_tail.py — the footage her CapCut draft cuts its clips from, with room after the last one.

Her draft's main-track clips are cut from one copy of her finished cut. That copy ended on her last word, so the last
clip sat on the file's final frame and CapCut would not let her drag it longer (every other clip could, into the
footage after it). Reported 2026-10-16: "the last clip should still be able to extend."

So the copy gets a TAIL: the next few seconds of her own clip after the last kept line, made by the engine's own
stitch (same framing, same color, same master), level-matched to her cut on the overlap, with her Filter baked in
when she picked one. The clips keep exactly their times; the tail just sits past the end, ready if she drags into it.
Nothing is ever added to the reel itself: the tail plays only if she extends the clip.

    from capcut_tail import tailed_base
    path, tail = tailed_base(job_dir, base, base_seconds, grade=None)   # tail = seconds after the cut (0 = none)

Cached next to the reel's outputs (outputs/<job>.capcut.mp4 + .capcut.json): made again only when the cut changes.
Anything that goes wrong hands back the plain cut, so a draft is never held up by it.
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

HANDLE = 2.0        # seconds of her clip after the last kept line, when the clip has them
SHORTEST = 0.1      # less than this past the line isn't worth a tail


def _probe(path, entries, stream="format"):
    args = ["ffprobe", "-v", "error"] + (["-select_streams", "v:0", "-show_entries", f"stream={entries}"]
                                         if stream == "v" else ["-show_entries", f"format={entries}"]) + ["-of", "json", path]
    out = json.loads(subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or "{}")
    return (out.get("streams") or [{}])[0] if stream == "v" else out.get("format", {})


def _rms_db(path, start=None, dur=None):
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats"] + (["-ss", f"{start:.3f}"] if start is not None else []) \
        + ["-i", path, "-map", "0:a:0?"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-vn", "-af", "volumedetect", "-f", "null", os.devnull]
    err = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = re.findall(r"mean_volume:\s*(-?[\d.]+) dB", err)
    return float(m[-1]) if m else None


def _last_segment(jd, bdur):
    try:
        segs = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    except Exception:
        return None
    from cut_placement import played_length                  # a sped clip counts at the length it plays
    lens = [played_length(s) for s in segs if "start" in s and "end" in s]
    if not segs or abs(sum(lens) - bdur) > 0.1:        # a baked or re-timed base: not her plain cut, no tail
        return None
    return segs[-1]


def tailed_base(jd, base, bdur, grade=None, log=print):
    """(path, tail seconds): her cut with her own footage after the last line, or (base, 0.0) when there's none."""
    try:
        return _tailed(jd, base, bdur, grade, log)
    except Exception as e:                              # never holds up her draft
        log(f"  (no extra footage after your last clip this time: {e})")
        return base, 0.0


def _tailed(jd, base, bdur, grade, log):
    last = _last_segment(jd, bdur)
    if not last:
        return base, 0.0
    clip = last["clip"]
    raw = clip if os.path.isabs(clip) else os.path.join(jd, "raw", clip)
    if not os.path.isfile(raw):
        raw = os.path.join(jd, clip)
    if not os.path.isfile(raw):
        return base, 0.0
    start, end = float(last["start"]), float(last["end"])
    v = _probe(raw, "r_frame_rate", "v")
    num, den = (int(x) for x in str(v.get("r_frame_rate", "30/1")).split("/"))
    frame = den / num if num else 1 / 30
    tail = min(HANDLE, float(_probe(raw, "duration").get("duration", 0)) - end - frame)
    if tail < SHORTEST:
        return base, 0.0
    tail = round(int(tail / frame) * frame, 4)          # whole frames of her clip

    name = os.path.basename(os.path.normpath(jd))
    out = os.path.join(jd, "outputs", f"{name}.capcut.mp4")
    stamp = os.path.join(jd, "outputs", f"{name}.capcut.json")
    key = {"base": os.path.basename(base), "size": os.path.getsize(base), "mtime": int(os.path.getmtime(base)),
           "start": start, "end": end, "tail": tail, "grade": grade or None, "v": 1}
    try:
        if json.load(open(stamp, encoding="utf-8")) == key and os.path.isfile(out):
            return out, tail
    except Exception:
        pass

    tmp = tempfile.mkdtemp(prefix="capcut-tail-")
    tj = os.path.join(tmp, f"{name}-capcut-tail")
    work = os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(tj))
    try:
        os.makedirs(os.path.join(tj, "transcript")); os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "cuts.json"), "w", encoding="utf-8") as f:   # her last line, run on into the tail
            json.dump({"segments": [{"clip": os.path.abspath(raw), "start": start, "end": end + tail,
                                     "keep_edges": True, "transcript": ""}]}, f)
        try:                                           # the Finish tab's bar: her clip read to its end, then the join
            import export_progress
        except ImportError:
            export_progress = None
        if export_progress:
            export_progress.stage(0.0, 0.6)
        env = dict(os.environ, TRIM_RESTARTS="0", VERIFY_CUT="0", VOICE_LEVEL="0", SNAP="0")
        bash = shutil.which("bash") or "bash"
        r = subprocess.run([bash, os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh"), tj],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        made = os.path.join(tj, "outputs", os.path.basename(tj) + ".mp4")
        if r.returncode != 0 or not os.path.isfile(made):
            raise RuntimeError("the stitch couldn't make it")
        line = end - start
        a, b = _rms_db(base, bdur - line, line), _rms_db(made, 0, line)   # the same words in both: match the level
        gain = round(a - b, 2) if a is not None and b is not None else 0.0
        bv = _probe(base, "width,height,r_frame_rate,pix_fmt", "v")
        w, h, rate = int(bv["width"]), int(bv["height"]), bv.get("r_frame_rate", "30/1")
        import video_grade, video_encoder
        g = video_grade.grade_filter(grade) if grade else None
        vt = f"[1:v]trim=start={line:.4f},setpts=PTS-STARTPTS,scale={w}:{h},setsar=1,fps={rate}" + (f",{g}" if g else "") + "[tv]"
        at = f"[1:a]atrim=start={line:.4f},asetpts=PTS-STARTPTS,volume={gain}dB,aresample=48000[ta]"
        base_av = f"[0:v]setsar=1,fps={rate}[bv];[0:a]aresample=48000[ba]"
        graph = f"{base_av};{vt};{at};[bv][ba][tv][ta]concat=n=2:v=1:a=1[v][a]"
        part = out + ".tmp.mp4"
        venc = video_encoder.pick_encoder(vbr="20M", crf=14)
        if export_progress:
            export_progress.stage(0.6, 1.0)
        for enc in ([venc, video_encoder.software_encoder(14)] if video_encoder.is_hardware(venc) else [venc]):
            cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"] + (export_progress.ffmpeg_args(bdur + tail) if export_progress else []) + ["-i", base, "-i", made,
                   "-filter_complex", graph, "-map", "[v]", "-map", "[a]"] + enc + ["-c:a", "aac", "-b:a", "320k",
                                                                                     "-movflags", "+faststart", part]
            rr = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if rr.returncode == 0 and os.path.isfile(part):
                break
        else:
            raise RuntimeError("the footage couldn't be joined")
        os.replace(part, out)                           # in one step: a draft that links it never sees half a file
        with open(stamp, "w", encoding="utf-8") as f:
            json.dump(key, f)
        log(f"  your last clip has {tail:.1f}s of your footage after it, so you can drag it longer in CapCut")
        return out, tail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); ap.add_argument("--grade")
    a = ap.parse_args()
    jd = a.job if os.path.isdir(a.job) else os.path.join(ROOT, "projects", a.job)
    base = os.path.join(jd, "outputs", os.path.basename(os.path.normpath(jd)) + ".mp4")
    bdur = float(_probe(base, "duration").get("duration", 0))
    print(tailed_base(jd, base, bdur, a.grade))
