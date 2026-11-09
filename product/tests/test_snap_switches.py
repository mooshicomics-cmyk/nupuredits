#!/usr/bin/env python3
"""The boundary snap's switches.

  1. snap-to-sound.py leaves a segment's edges alone for "keep_edges": true.
  2. Its report lines start with [snap].
  3. stitch-cut.sh turns the snap off for SNAP=0. On a your-turn cut the snap is off unless SNAP=1 forces it.
  4. Its own lines start with [stitch].
  5. A word said twice that came back as one long word: a segment opens on the second take, ends after the
     first, and one that holds it in the middle is told where to split.

Run:  python3 product/tests/test_snap_switches.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

JOB = "my-reel"   # a stand-in job folder the test builds

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


FFMPEG = shutil.which("ffmpeg")
if os.name == "nt" or not FFMPEG or not shutil.which("ffprobe") or not shutil.which("bash"):
    print("snap switches: skipped (needs bash, ffmpeg and ffprobe)")
    sys.exit(0)

tmp = tempfile.mkdtemp()
try:
    # a clip with a clear word in the middle: quiet, a tone from 1.0 to 2.0 s, quiet
    clip = os.path.join(tmp, "clip.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=3",
                    "-af", "volume='if(between(t,1,2),1,0.001)':eval=frame",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)
    WORDS = {"clips": [{"clip": "clip.mp4", "words": [{"w": "hello", "start": 1.08, "end": 1.9, "prob": 0.9}]}]}
    SEG = {"clip": "clip.mp4", "start": 1.0, "end": 1.95, "transcript": "hello"}

    # ── 1 and 2: snap-to-sound.py on its own ──────────────────────────────────────────────────────────────
    media = os.path.join(tmp, "media")
    os.makedirs(media)
    os.link(clip, os.path.join(media, "clip.mp4"))
    words_path = os.path.join(tmp, "words.json")
    json.dump(WORDS, open(words_path, "w", encoding="utf-8"))

    def snap(**extra):
        plan = os.path.join(tmp, "cuts.json")
        out = os.path.join(tmp, "cuts.out.json")
        json.dump({"segments": [dict(SEG, **extra)]}, open(plan, "w", encoding="utf-8"))
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "snap-to-sound.py"), media, words_path, plan, out],
                           capture_output=True, text=True, encoding="utf-8")
        seg = json.load(open(out, encoding="utf-8"))["segments"][0] if os.path.exists(out) else {}
        return r, seg

    r, seg = snap(keep_edges=True)
    check("1: keep_edges: true runs clean", r.returncode == 0, r.stderr[-400:])
    check("1: keep_edges: true leaves the edges as authored", (seg.get("start"), seg.get("end")) == (1.0, 1.95), str(seg))
    check("1: keep_edges: true is reported as kept edges", "edges as planned (keep_edges)" in r.stderr, r.stderr[-400:])
    r, seg = snap(keep_edges=False)
    check("1: keep_edges: false snaps as usual", "edges as planned" not in r.stderr and "head" in r.stderr, r.stderr[-400:])
    r, _ = snap()
    lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
    check("2: every report line starts with [snap]", lines and all(ln.startswith("[snap]") for ln in lines), r.stderr)

    # ── 5: a word said twice, heard as one ────────────────────────────────────────────────────────────────
    # "so" 0.3-0.6, then "listen" said twice (1.0-1.45 and 1.65-2.1) stamped as ONE word 1.05-2.05, then "now".
    fold_clip = os.path.join(media, "fold.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=3.2",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=3.2",
                    "-af", "volume='if(between(t,0.3,0.6)+between(t,1,1.45)+between(t,1.65,2.1)+between(t,2.4,2.7),"
                    "1,0.001)':eval=frame", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    "-y", fold_clip], check=True)
    fold_words = os.path.join(tmp, "fold-words.json")
    json.dump({"clips": [{"clip": "fold.mp4", "words": [
        {"w": "so", "start": 0.32, "end": 0.58}, {"w": "listen", "start": 1.05, "end": 2.05},
        {"w": "now", "start": 2.42, "end": 2.68}]}]}, open(fold_words, "w", encoding="utf-8"))
    fold_plan, fold_out = os.path.join(tmp, "fold-cuts.json"), os.path.join(tmp, "fold-cuts.out.json")
    json.dump({"segments": [{"clip": "fold.mp4", "start": 1.0, "end": 2.1},      # opens on "listen"
                            {"clip": "fold.mp4", "start": 0.3, "end": 2.1},      # ends on "listen"
                            {"clip": "fold.mp4", "start": 0.3, "end": 2.7}]},    # "listen" in the middle
              open(fold_plan, "w", encoding="utf-8"))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "snap-to-sound.py"), media, fold_words, fold_plan,
                        fold_out], capture_output=True, text=True, encoding="utf-8")
    check("5: runs clean", r.returncode == 0, r.stderr[-400:])
    segs = json.load(open(fold_out, encoding="utf-8"))["segments"] if os.path.exists(fold_out) else [{}] * 3
    check("5: a segment that opens on the word opens on its second take", 1.55 < segs[0].get("start", 0) < 1.65,
          str(segs[0]))
    check("5: a segment that ends on the word ends after its first take", 1.45 < segs[1].get("end", 0) < 1.55,
          str(segs[1]))
    check("5: both are reported as said twice", r.stderr.count("said twice") == 2, r.stderr[-600:])
    check("5: a segment holding it in the middle keeps both takes", (segs[2].get("start", 0) < 0.32
                                                                     and segs[2].get("end", 0) > 2.68), str(segs[2]))
    check("5: ...and is told where to split", "[snap] seg2  ⚠" in r.stderr and "start the next at 1.6" in r.stderr,
          r.stderr[-600:])

    # ── 3 and 4: stitch-cut.sh decides whether the snap runs ──────────────────────────────────────────────
    eng = os.path.join(tmp, "engine")
    for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "product/video_encoder.py", "product/hdr.py", "product/probe.py"):
        os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
    shutil.copytree(SCRIPTS, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    stitch = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")

    def stitch_run(your_turn=False, **env_extra):
        jd = os.path.join(eng, "projects", JOB)
        shutil.rmtree(jd, ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        os.link(clip, os.path.join(jd, "raw", "clip.mp4"))
        json.dump(WORDS, open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
        json.dump({"segments": [SEG]}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
        if your_turn:
            open(os.path.join(jd, "transcript", ".your-turn-cut"), "w", encoding="utf-8").close()
        shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
        os.makedirs(os.path.join(tmp, "scratch"))
        env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), FLAT_RENDER="0", TRIM_RESTARTS="0", VERIFY_CUT="0",
                   REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv")
        for k in ("SNAP", "VOICE_GAIN_DB", "WARM_MASTER", "VENC"):
            env.pop(k, None)
        env.update(env_extra)
        return subprocess.run(["bash", stitch, f"projects/{JOB}"], cwd=eng, env=env, capture_output=True,
                              text=True, encoding="utf-8")

    cases = [
        ("nothing set: the snap runs", {}, False, True, "SNAP=1"),
        ("SNAP=0 turns it off", {"SNAP": "0"}, False, False, "SNAP=0"),
        # the toggles line is printed before the your-turn default is applied, so it still reads SNAP=1 here
        ("a your-turn cut keeps her edges", {}, True, False, "SNAP=1"),
        ("SNAP=1 forces the snap on a your-turn cut", {"SNAP": "1"}, True, True, "SNAP=1"),
    ]
    for label, env_extra, your_turn, snapped, shown in cases:
        r = stitch_run(your_turn=your_turn, **env_extra)
        check(f"3: {label}: stitches", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-500:]}")
        check(f"3: {label}: snap {'ran' if snapped else 'skipped'}", ("[snap] seg0" in r.stderr) == snapped,
              r.stderr[-500:])
        check(f"3: {label}: toggles line shows {shown}", f"toggles: TRIM_RESTARTS=0 {shown} " in r.stderr,
              r.stderr[:300])
        check(f"4: {label}: own lines say [stitch]", "[stitch] toggles" in r.stderr and "[splice]" not in r.stderr,
              r.stderr[:300])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else "snap switches: keep_edges, SNAP and the said-twice rule do what they say")
sys.exit(1 if fails else 0)
