#!/usr/bin/env python3
"""The journey test's reel: a short talking clip, its transcript and its cut, made fresh in a throwaway folder.

Small on purpose (a 12 s, 360x640 clip made by ffmpeg) and shaped like the reels that broke the editor:
  - line 1 "this is the hook line."            a plain kept clip
  - "um"                                        a word the engine cut (she can bring it back)
  - line 2 "here is my second thought about pricing."   a clip sped up to 1.5x
  - a quiet piece                               a kept stretch with no words under it (a pause she held)
  - line 3 "check the internet."                "internet." stamped over a 2.2 s pause (a long-stamped word), zoom in
  - line 4 "then we speed it up?"               a speed RAMP (fast, easing to normal); its "?" comes in as its own
                                                20 ms token, the way a transcriber hands back French " ?"

The voice is tone bursts exactly where the words are said (silence in the quiet piece and after "internet"), so the
waveform, the edge passes and the page's playback all have real sound to work with.

Also the engine's stand-in for a lean stitch (`fake_stitch`): the cut plan apply_edits wrote becomes the reel's cut
and its kept-words transcript, in about a second, with no venv, no encode and nothing written outside the reel.

Seller-and-buyer safe: no names, no real reels. Used by test_editor_journey.py.
"""
import json, math, os, shutil, struct, subprocess, time, wave

JOB = "journeyjob"
DUR = 12.0
RATE = 22050

# (word, start, end, sound_end): sound_end < end only for a stamp glued over a pause
WORDS = [
    ("this", 0.30, 0.55), ("is", 0.60, 0.75), ("the", 0.80, 0.95), ("hook", 1.00, 1.40), ("line.", 1.45, 1.90),
    ("um", 2.10, 2.35),
    ("here", 2.60, 2.85), ("is", 2.90, 3.05), ("my", 3.10, 3.25), ("second", 3.30, 3.70), ("thought", 3.75, 4.10),
    ("about", 4.15, 4.45), ("pricing.", 4.50, 5.00),
    ("check", 6.70, 7.00), ("the", 7.05, 7.15), ("internet.", 7.20, 9.40, 7.75),
    ("then", 9.60, 9.85), ("we", 9.90, 10.05), ("speed", 10.10, 10.45), ("it", 10.50, 10.60), ("up", 10.65, 11.10),
    ("?", 11.10, 11.12),
]
RAMP = {"from": 2.5, "to": 1.0, "ease": "out"}
SEGMENTS = [
    {"clip": "a.mov", "start": 0.20, "end": 1.98},
    {"clip": "a.mov", "start": 2.52, "end": 5.05, "speed": 1.5},
    {"clip": "a.mov", "start": 5.05, "end": 6.62},                                       # the quiet piece
    {"clip": "a.mov", "start": 6.62, "end": 9.50, "zoom": {"from": 1.0, "to": 1.15, "ease": "inOut"}},
    {"clip": "a.mov", "start": 9.52, "end": 11.20, "ramp": RAMP},
]


# ── the same speed math the page (editor.html cutIn) and the stitch use ───────────────────────────────────────────
def _area(e, u):
    return {"linear": u * u / 2, "in": u ** 3 / 3, "out": u - (1 - (1 - u) ** 3) / 3}.get(e, u ** 3 - u ** 4 / 2)


def ramp_avg(r):
    return r["from"] + (r["to"] - r["from"]) * _area(r.get("ease", "inOut"), 1)


def _ramp_src(r, u):
    return (r["from"] * u + (r["to"] - r["from"]) * _area(r.get("ease", "inOut"), u)) / ramp_avg(r)


def seg_speed(s):
    if isinstance(s.get("ramp"), dict):
        return ramp_avg(s["ramp"])
    return float(s.get("speed", 1.0) or 1.0)


def cut_in(s, t):
    """Footage second t inside segment s -> seconds into that segment on the cut."""
    a, b = float(s["start"]), float(s["end"])
    d = (b - a) / seg_speed(s)
    if isinstance(s.get("ramp"), dict):
        x, lo, hi = min(1.0, max(0.0, (t - a) / max(1e-6, b - a))), 0.0, 1.0
        for _ in range(40):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if _ram(s, m) < x else (lo, m)
        return (lo + hi) / 2 * d
    return (t - a) / seg_speed(s)


def _ram(s, u):
    return _ramp_src(s["ramp"], u)


def cut_transcript(segments, words):
    """The kept-words transcript in cut seconds (what the rough cut's outputs/<job>.transcript.json holds)."""
    out, acc = [], 0.0
    for s in segments:
        a, b = float(s["start"]), float(s["end"])
        for w in words:
            mid = (w[1] + min(w[2], w[3] if len(w) > 3 else w[2])) / 2
            if a - 0.02 <= mid <= b + 0.02 and w[1] >= a - 0.05:
                st = acc + cut_in(s, max(a, w[1]))
                en = acc + cut_in(s, min(b, w[3] if len(w) > 3 else w[2]))
                out.append({"text": w[0], "start": round(st, 3), "end": round(max(en, st + 0.05), 3), "type": "word"})
        acc += (b - a) / seg_speed(s)
    return {"words": out, "text": " ".join(w["text"] for w in out)}


def _voice(path):
    """Tone bursts where each word is said; silence everywhere else."""
    n = int(DUR * RATE)
    buf = bytearray(n * 2)
    for w in WORDS:
        a, b = w[1], (w[3] if len(w) > 3 else w[2])
        for k in range(int(a * RATE), min(n, int(b * RATE))):
            x = (k - a * RATE) / RATE
            env = min(1.0, x / 0.02, (b - k / RATE) / 0.02)
            v = int(9000 * env * math.sin(2 * math.pi * (180 + 40 * math.sin(x * 9)) * x))
            struct.pack_into("<h", buf, k * 2, v)
    with wave.open(path, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(RATE); f.writeframes(bytes(buf))


def make_reel(projects):
    """projects/<JOB>/ with raw/a.mov, its transcript, its cut and the rough cut's outputs. Returns the job folder."""
    jd = os.path.join(projects, JOB)
    for d in ("raw", "transcript", "review", "outputs"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    wav = os.path.join(jd, "voice.wav")
    _voice(wav)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=360x640:rate=30:duration={DUR}",
                    "-i", wav, "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    os.path.join(jd, "raw", "a.mov")], check=True)
    os.remove(wav)
    ws = [{"word": w[0], "start": w[1], "end": w[2]} for w in WORDS]
    json.dump({"clips": [{"clip": "a.mov", "path": "", "duration": DUR, "words": ws}]},
              open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    segs = [dict(s, transcript="", **({"speed": round(ramp_avg(s["ramp"]), 4)} if "ramp" in s else {})) for s in SEGMENTS]
    json.dump({"segments": segs}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    shutil.copyfile(os.path.join(jd, "raw", "a.mov"), os.path.join(jd, "outputs", JOB + ".mp4"))
    json.dump(cut_transcript(segs, WORDS), open(os.path.join(jd, "outputs", JOB + ".transcript.json"), "w", encoding="utf-8"))
    return jd


def fake_stitch(ve, delay=1.2):
    """A stand-in for the lean stitch (stitch-cut.sh with FLAT_RENDER=0): the plan apply_edits wrote becomes the
    reel's cut and its kept-words transcript. Every page and engine rule around it stays the real one."""
    import tempfile

    def _stitch(jd, lean, log=print, env=None, keep_phase=False, stop=None):
        for f in (("last-problem.json",) if keep_phase else ("phase.json", "last-problem.json")):
            try:
                os.remove(os.path.join(jd, "review", f))
            except OSError:
                pass
        plan = os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(jd), "cuts.json")
        segs = json.load(open(plan, encoding="utf-8"))["segments"]
        time.sleep(delay)                                    # long enough for the page to show "Updating your cut"
        ve._atomic_json(os.path.join(jd, "transcript", "cuts.json"), {"segments": segs})
        ws = [(w["word"], w["start"], w["end"]) + ((7.75,) if w["word"] == "internet." else ())
              for w in json.load(open(os.path.join(jd, "transcript", "words.json"), encoding="utf-8"))["clips"][0]["words"]]
        ve._atomic_json(os.path.join(jd, "outputs", os.path.basename(jd) + ".transcript.json"), cut_transcript(segs, ws))
    return _stitch


if __name__ == "__main__":                                   # make one to look at: python3 editor_journey_fixture.py <dir>
    import sys
    t = time.time()
    print(make_reel(sys.argv[1] if len(sys.argv) > 1 else "."), f"{time.time() - t:.1f}s")
