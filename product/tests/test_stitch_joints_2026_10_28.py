#!/usr/bin/env python3
"""Guards: a buyer's 19-piece confessional cut (2026-10-28), where the engine told her to report a broken stitch and
to type a crossfade into cuts.json herself.

  typical joint   a working crossfade on her sound left the typical joint 1 dB under its quieter side, with no joint
                  dipping on its own, and sound-check called the stitch broken (/report-a-problem). The reel-level
                  line now needs the typical joint REEL_MEDIAN_DB (3 dB) under; a faded-edge stitch still trips it
  one joint       a click at a joint: the stitch gives that joint the 30 ms crossfade sound-check names, renders
                  the sound alone again under the same picture, and records "xfade" in the saved cut, so sound-check
                  has nothing to ask of her; a clean cut is left exactly as it was. Made on the grouped path (more
                  pieces than STITCH_GROUP, as her cut was), inside a group and where two groups meet, and as one graph.
                  A joint the longer run-on makes worse (it reaches her next word in the take) keeps its own crossfade,
                  marked "_xfade_worse", and sound-check names the next fix there instead

Runs on generated sound and short generated clips in a temporary folder; nothing real is touched.

Run: python3 product/tests/test_stitch_joints_2026_10_28.py
"""
import json, math, os, random, shutil, struct, subprocess, sys, tempfile, wave

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
SC = os.path.join(SCRIPTS, "sound-check.py")
RATE = 48000
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {str(detail)[-600:]}"))
    if not cond:
        fails.append(name)


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(round(s * 32767))))) for s in samples))


if not FFMPEG or not FFPROBE:
    print("buyer reports 2026-10-28: skipped (needs ffmpeg and ffprobe)")
    sys.exit(0)

tmp = os.path.realpath(tempfile.mkdtemp())
try:
    # ------------------------------------------------------------ typical joint
    print("typical joint")

    def tone(n, seed):
        """Steady room tone with a voice-like hum on it, the sound her joints sat in (never gated quiet)."""
        rnd = random.Random(seed)
        return [0.02 * (rnd.random() * 2 - 1) + 0.03 * math.sin(2 * math.pi * 180 * k / RATE) for k in range(n)]

    def reel(name, sag):
        """18 joints, each cut sitting `sag` (a gain, one cycle wide) under the sound on both sides of it."""
        lengths = [0.5] * 19
        x = tone(int(sum(lengths) * RATE), 3)
        for j in range(1, 19):
            c = int(j * 0.5 * RATE)
            for k in range(-288, 288):
                x[c + k] *= sag
        jd = os.path.join(tmp, name)
        os.makedirs(os.path.join(jd, "outputs"))
        os.makedirs(os.path.join(jd, "transcript"))
        write_wav(os.path.join(tmp, name + ".wav"), x)
        subprocess.run([FFMPEG, "-v", "error", "-i", os.path.join(tmp, name + ".wav"), "-c:a", "aac", "-b:a", "256k",
                        "-ar", "48000", "-ac", "2", "-y", os.path.join(jd, "outputs", name + ".mp4")], check=True)
        segs = [{"clip": "take.mov", "start": round(i * 0.5, 6), "end": round(i * 0.5 + 0.5, 6),
                 "transcript": f"line {i}"} for i in range(19)]
        with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump({"segments": segs}, fh)
        r = subprocess.run([sys.executable, SC, jd], capture_output=True, text=True, encoding="utf-8",
                           env={k: v for k, v in os.environ.items() if k not in ("VOICE_GAIN_DB", "WARM_MASTER")})
        return r.stdout + r.stderr

    out = reel("one-db", 0.85)      # about 1.4 dB under: her reading
    check("a typical joint 1 dB under its quieter side is not a broken stitch",
          "⚠ joints" not in out and "/report-a-problem" not in out, out)
    check("and every one of its joints carries the sound through", "✓ joints: 18 heard" in out, out)
    out = reel("faded", 0.55)       # about 5 dB under at every joint, none 7 dB on its own: the faded-edge fault
    check("the same sag 5 dB deep at every joint is still the stitch broken",
          "⚠ joints: the typical cut sits" in out and "/report-a-problem" in out and "listen:" not in out, out)

    # ------------------------------------------------------------ one joint
    print("one joint")
    if os.name == "nt" or not shutil.which("bash"):
        # Like test_stitch_sound_drift.py: the stitch runs under bash, and its Windows run has its own gate.
        print("  (the stitch half is skipped here: it needs bash, and is not run on Windows)")
    else:
        eng = os.path.join(tmp, "engine")
        for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh",
                    "product/video_encoder.py", "product/hdr.py", "product/probe.py", "product/swap.py"):
            if os.path.exists(os.path.join(ROOT, rel)):
                os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
        shutil.copytree(SCRIPTS, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        stitch = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")

        # A 300 Hz voice over a faint room (ten whole cycles to a frame at 30 fps, so every joint meets in phase) and,
        # for the clicks, a 2 ms burst right where the second and the third piece start: the attack a cut-in caught
        # already under way. Through the 6 ms crossfade it stands about 6x over the sound around it; the 30 ms one
        # fades it in about five times more gently, under the bar of 2. With STITCH_GROUP=2 the first joint sits
        # inside a group and the second is where two groups meet. `next_word` puts a loud burst 15 ms past the first
        # piece's out-point, what she said next in the take: the 6 ms run-on never reaches it, the 30 ms one does.
        def clip(name, burst, next_word=False):
            rnd = random.Random(5)
            x = [0.05 * math.sin(2 * math.pi * 300 * k / RATE) + 0.002 * (rnd.random() * 2 - 1) for k in range(8 * RATE)]
            for b in ((int(3.0 * RATE) + 24, int(5.5 * RATE) + 24) if burst else ()):
                for k in range(b, b + 96):
                    x[k] += 0.03 * (rnd.random() * 2 - 1)
            if next_word:
                b = int(2.415 * RATE)
                for k in range(b, b + 96):
                    x[k] += 0.3 * (rnd.random() * 2 - 1)
            wav = os.path.join(tmp, name + ".wav")
            write_wav(wav, x)
            path = os.path.join(tmp, name + ".mp4")
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30:duration=8",
                            "-i", wav, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-b:a", "256k", "-shortest", "-y", path], check=True)
            return path

        PLAN = {"segments": [{"clip": "a.mp4", "start": 0.20, "end": 2.40, "transcript": "one"},
                             {"clip": "a.mp4", "start": 3.00, "end": 5.10, "transcript": "two goes here"},
                             {"clip": "a.mp4", "start": 5.50, "end": 7.60, "transcript": "three"}]}

        def run(job, src, group="2"):
            jd = os.path.join(eng, "projects", job)
            scratch = os.path.join(tmp, "scratch", "reels-editing-engine", job)
            os.makedirs(os.path.join(jd, "raw"))
            os.makedirs(os.path.join(jd, "transcript"))
            os.makedirs(scratch)
            shutil.copy(src, os.path.join(jd, "raw", "a.mp4"))
            with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
                json.dump(PLAN, fh, indent=1)
            env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), STITCH_GROUP=group,
                       REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                       VERIFY_CUT="0", VENC="libx264", TRIM_RESTARTS="0", SNAP="0", CLOSE_PAUSES="0", VOICE_LEVEL="0")
            for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "WARM_MASTER"):
                env.pop(k, None)
            r = subprocess.run(["bash", stitch, "projects/" + job], cwd=eng, env=env, capture_output=True,
                               text=True, encoding="utf-8")
            with open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8") as fh:
                saved = json.load(fh)["segments"]
            return r, saved, os.path.join(jd, "outputs", job + ".mp4")

        r, saved, mp4 = run("clean-joints", clip("clean", False))
        check("a clean cut renders on the grouped path", r.returncode == 0 and "made in 2 groups" in r.stderr
              and os.path.exists(mp4), r.stderr)
        check("and its joints are left exactly as they were", all("xfade" not in s for s in saved)
              and "crossfades over" not in r.stderr and "✓ joints: 2 heard" in r.stderr, r.stderr)

        click = clip("click", True)
        for job, group, path in (("click-joint", "2", "the grouped path"), ("click-one-graph", "0", "one graph")):
            r, saved, mp4 = run(job, click, group)
            check(f"{path}: the click cut renders", r.returncode == 0 and os.path.exists(mp4), r.stderr)
            check(f"{path}: the stitch gives each clicking joint a 30 ms crossfade on its own",
                  "✓ joint 1 at 2.20s, into segments[1]" in r.stderr and "✓ joint 2 at 4.30s, into segments[2]" in r.stderr
                  and r.stderr.count("crossfades over 30 ms") == 2 and r.stderr.count("hears clean now") == 2, r.stderr)
            check(f"{path}: the saved cut records it on those joints", saved[1].get("xfade") == 0.03
                  and saved[2].get("xfade") == 0.03 and "xfade" not in saved[0], json.dumps(saved)[:400])
            check(f"{path}: sound-check then has nothing to ask of her", "listen:" not in r.stderr
                  and '"xfade"' not in r.stderr and "✓ joints: 2 heard" in r.stderr, r.stderr)
            if os.path.exists(mp4):
                def stream(kind):
                    o = subprocess.run([FFPROBE, "-v", "error", "-select_streams", f"{kind}:0", "-show_entries",
                                        "stream=duration", "-of", "default=nw=1:nk=1", mp4], capture_output=True,
                                       text=True)
                    return float(o.stdout.split()[0])
                check(f"{path}: the picture and the rebuilt sound still agree",
                      abs(stream("a") - stream("v")) <= 1024 / RATE + 1 / 24, f"{stream('a')} vs {stream('v')}")
                leftovers = [f for f in os.listdir(os.path.dirname(mp4)) if "resound" in f]
                check(f"{path}: no rebuild file left beside the cut", not leftovers, str(leftovers))

        r, saved, mp4 = run("click-next-word", clip("next-word", True, next_word=True))
        check("a joint the longer crossfade makes worse keeps its own", r.returncode == 0
              and "· joint 1 at 2.20s, into segments[1]" in r.stderr and "made it worse, so it keeps its own" in r.stderr
              and "xfade" not in saved[1] and saved[1].get("_xfade_worse") == 0.03, r.stderr)
        check("and the joint it helps keeps the longer one", "✓ joint 2 at 4.30s, into segments[2]" in r.stderr
              and saved[2].get("xfade") == 0.03 and "_xfade_worse" not in saved[2] and "xfade" not in saved[0],
              json.dumps(saved)[:400])
        check("sound-check names the next fix for the joint it made worse, never the crossfade just tried",
              "listen: joint 1 at 2.20s" in r.stderr and '"xfade": 0.030' not in r.stderr
              and "it made it worse) and stitch again" in r.stderr and "listen: joint 2" not in r.stderr, r.stderr)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else f"buyer reports 2026-10-28: all {total} checks pass")
sys.exit(1 if fails else 0)
