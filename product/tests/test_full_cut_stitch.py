#!/usr/bin/env python3
"""Guards: the full-quality cut is made when her cut changed, stops when she says stop, and never runs a 4K take out of
memory for hours (buyer reports, 2026-10-22 and 2026-10-23).

  1. A ZOOM KEEPS THE LENGTH. With no stamp on the rough-cut video, base_is_stale measured its length only, so a
     punch-in added by a lean round (clip-fx, restitch, her Send) left the old video "current", and Finish exported
     the reel from before the zoom. Now: a lean round stamps a video that still matches before it changes the cut;
     an unstamped video older than a cut carrying a zoom or framing is behind; the full stitch stamps what it made;
     and `finish-cut --full` makes it again whatever the video looks like.
  2. STOP DURING THE FULL-QUALITY CUT. _run_stitch never looked at review/finish.stop, so Stop on her Finish tab did
     nothing for three hours. Now the stitch ends whole (ffmpeg included), she is told plainly it stopped, and
     Finish records a stop, not a failure.
  3. SIGNAL 9 IS NOT THE ENCODER. A render the computer ended (out of memory) was retried on libx264 with the same
     graph, then again on the edges as written. Now it is said plainly and nothing else is tried.
  4. A CUT THAT JUMPS BACK in a file reads each forward run of pieces from its own seeked input, so nothing waits in
     memory; every in and out point stays on the same frame. A cut in filming order keeps one plain input per file.
  5. THE NEWER PLAN WINS. A scratch plan left from an earlier stitch no longer undoes an edit made since to the
     job's saved transcript/cuts.json; a fresh scratch plan still wins as before.

Run: python3 product/tests/test_full_cut_stitch.py
"""
import json, os, re, shutil, stat, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve
import finish

fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def executable(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def age(path, secs):
    """Set a file's time `secs` from now (negative: in the past)."""
    t = time.time() + secs
    os.utime(path, (t, t))


tmp = tempfile.mkdtemp()
real_duration, real_run_stitch, real_root = ve._duration, ve._run_stitch, ve.ROOT
try:
    # ── 1. a zoom keeps the length ────────────────────────────────────────────────────────────────────────────────
    ve._duration = lambda p: 2.0                              # the video plays exactly as long as the cut
    jd = os.path.join(tmp, "reel")
    mp4 = os.path.join(jd, "outputs", "reel.mp4")
    cuts = os.path.join(jd, "transcript", "cuts.json")
    PLAIN = {"segments": [{"clip": "a.mov", "start": 1.0, "end": 2.0}, {"clip": "a.mov", "start": 3.0, "end": 4.0}]}
    ZOOMED = {"segments": [dict(PLAIN["segments"][0], zoom={"from": 1.0, "to": 1.15}), PLAIN["segments"][1]]}

    def reel(plan):
        shutil.rmtree(jd, ignore_errors=True)
        write_json(cuts, plan)
        os.makedirs(os.path.dirname(mp4))
        with open(mp4, "wb") as fh:
            fh.write(b"\0" * 2048)
        age(cuts, -180)                                       # the stitch saved the plan, then levelled the video
        age(mp4, -120)                                        # (minutes before any edit below)

    reel(PLAIN)
    check("1: an unstamped video that matches the cut is current", not ve._base_stale(jd))
    write_json(cuts, ZOOMED)                                  # a lean zoom round from before this fix: no stamp
    check("1: an unstamped video older than a cut with a zoom is behind (Finish makes it again)", ve._base_stale(jd))
    write_json(cuts, {"segments": [dict(PLAIN["segments"][0], scale=1.2, x=0.1), PLAIN["segments"][1]]})
    check("1: a framing (scale, x) counts as a zoom", ve._base_stale(jd))

    reel(PLAIN)
    calls = []

    def fake_stitch(jd_, env, timeout=None, stop=None):       # the lean round writes the zoom into the saved cut
        calls.append(env.get("FLAT_RENDER"))
        write_json(cuts, ZOOMED)
        age(cuts, -600)                                       # even older than the video: only the stamp can tell
        return 0, []
    ve._run_stitch = fake_stitch
    ve._stitch(jd, lean=True, log=lambda *a: None)
    check("1: the lean round ran", calls == ["0"], str(calls))
    check("1: a lean round stamps the video it leaves behind", os.path.exists(os.path.join(jd, "review", "base-cut.json")))
    check("1: so the zoom marks it behind, though the length and the file times say nothing", ve._base_stale(jd))

    def full_stitch(jd_, env, timeout=None, stop=None):       # the full stitch: a new video of the zoomed cut
        calls.append(env.get("FLAT_RENDER"))
        with open(mp4, "wb") as fh:
            fh.write(b"\1" * 4096)
        return 0, []
    ve._run_stitch = full_stitch
    ve._stitch(jd, lean=False, log=lambda *a: None)
    check("1: after the full stitch the video is current", not ve._base_stale(jd))

    # finish-cut: skipped when the video matches; --full (force) makes it all the same
    made = []
    saved = (ve._line_up_sound, ve.build_script, ve._cut_id)
    ve._line_up_sound, ve.build_script, ve._cut_id = (lambda jd_, log=print: {}), (lambda job: None), (lambda jd_: "c")
    ve._run_stitch = lambda jd_, env, timeout=None, stop=None: (made.append(stop), full_stitch(jd_, env))[1]
    try:
        ve.finish_cut(jd, log=lambda *a: None)
        check("1: finish-cut on a current video makes nothing", made == [], str(made))
        ve.finish_cut(jd, log=lambda *a: None, force=True)
        check("1: finish-cut --full stitches again", len(made) == 1, str(made))
        check("1: the chat's finish-cut is not stopped by an old stop file", made[:1] == [None], str(made))
    finally:
        ve._line_up_sound, ve.build_script, ve._cut_id = saved
    with open(os.path.join(ROOT, "product", "visual_editor.py"), encoding="utf-8") as fh:
        check("1: the finish-cut command hands --full on", "finish_cut(a.job, force=a.full)" in fh.read())
    with open(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh"), encoding="utf-8") as fh:
        check("1: every full stitch stamps the video it made", "visual_editor._stamp_base" in fh.read())

    # ── 2. Stop during the full-quality cut ───────────────────────────────────────────────────────────────────────
    ve._run_stitch, ve._duration = real_run_stitch, real_duration
    eng = os.path.join(tmp, "engine")
    pidf = os.path.join(tmp, "child.pid")
    executable(os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh"),
               "#!/bin/bash\nsleep 300 &\n" f"echo $! > '{pidf}'\n" "echo '[stitch] encoding'\nwait\n")
    ve.ROOT = eng
    stop = os.path.join(jd, "review", "finish.stop")
    if os.path.exists(stop):
        os.remove(stop)

    def press_stop():
        time.sleep(1.5)
        with open(stop, "w", encoding="utf-8") as fh:
            fh.write("now")
    threading.Thread(target=press_stop, daemon=True).start()
    t0 = time.time()
    rc, tail = ve._run_stitch(jd, dict(os.environ, FLAT_RENDER="1"), stop=stop)
    check("2: her Stop ends the full-quality cut", rc == ve.STOPPED, f"rc {rc!r}")
    check("2: within seconds, not when it finishes", time.time() - t0 < 15, f"{time.time() - t0:.1f}s")
    with open(os.path.join(jd, "review", "last-stitch.log"), encoding="utf-8") as fh:
        check("2: the log says she stopped it", "she pressed Stop" in fh.read())
    if os.name != "nt" and os.path.exists(pidf):              # (a Git Bash pid is not a Windows one)
        with open(pidf, encoding="utf-8") as fh:
            child = int(fh.read().strip())
        time.sleep(0.3)
        gone = False
        try:
            os.kill(child, 0)
        except OSError:
            gone = True
        if not gone:                                          # a zombie the test's own shell never reaped is gone too
            st = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True).stdout.strip()
            gone = st.startswith("Z") or not st
        check("2: and everything it started ends with it (ffmpeg's place)", gone, f"pid {child} still running")

    ve._run_stitch = lambda jd_, env, timeout=None, stop=None: (ve.STOPPED, [])
    try:
        ve._stitch(jd, lean=False, log=lambda *a: None, stop=stop)
        check("2: a stopped stitch raises", False)
    except ve.Stopped as e:
        check("2: she is told plainly it stopped", "stopped" in str(e) and "saved" in str(e), str(e))

    # Finish turns it into a stop (state "stopped"), never a failure
    ve.ROOT = real_root
    seen = {}

    def stopped_cut(job, log=print, exact=False, force=False, stoppable=False):
        seen["stoppable"] = stoppable
        raise ve.Stopped("You stopped making your full-quality cut, so it stopped there.")
    saved = (ve.finish_cut, ve.base_is_stale)
    ve.finish_cut, ve.base_is_stale = stopped_cut, (lambda job: True)
    try:
        finish._run_finish(jd, "mp4", lambda *a: None)
        check("2: Finish stops", False)
    except finish.Stopped as e:
        check("2: Finish's own cut listens for her Stop", seen.get("stoppable") is True, str(seen))
        check("2: and records a stop in her words", "stopped" in str(e), str(e))
    except Exception as e:
        check("2: Finish turns the stop into its own Stopped", False, repr(e))
    finally:
        ve.finish_cut, ve.base_is_stale = saved

    # ── 3, 4, 5: the stitch itself, in a throwaway copy of the engine ─────────────────────────────────────────────
    FFMPEG = shutil.which("ffmpeg")
    if os.name == "nt" or not FFMPEG or not shutil.which("ffprobe") or not shutil.which("bash"):
        print("  (3-5 skipped: they need bash, ffmpeg and ffprobe, and a POSIX shell for the stand-in encoder)")
    else:
        eng = os.path.join(tmp, "engine2")
        for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "product/video_encoder.py", "product/hdr.py",
                    "product/probe.py", "product/swap.py"):
            if os.path.exists(os.path.join(ROOT, rel)):
                os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
        shutil.copytree(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"),
                        os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        reports = os.path.join(tmp, "reports.log")
        executable(os.path.join(eng, "product", "make-handoff.py"),
                   f"import sys\nopen({reports!r}, 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n")
        stitch = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")
        # A stand-in ffmpeg in front of the real one: the render (the one call with a graph) is logged, and with
        # FAKE_KILL=1 the system ends it the way it ends a process that ran the computer out of memory.
        bindir = os.path.join(tmp, "bin")
        renders = os.path.join(tmp, "renders.log")
        executable(os.path.join(bindir, "ffmpeg"),
                   "#!/bin/bash\n"
                   "for a in \"$@\"; do case \"$a\" in -filter_complex|-/filter_complex|-filter_complex_script)\n"
                   f"  printf '%s\\n' \"$*\" >> {renders!r}\n"
                   "  if [ \"${FAKE_KILL:-0}\" = 1 ]; then kill -9 $$; fi;; esac; done\n"
                   f"exec {FFMPEG!r} \"$@\"\n")
        clip = os.path.join(tmp, "clip.mp4")
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x284:rate=30:duration=12",
                        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=12", "-c:v", "libx264",
                        "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)
        IN_ORDER = {"segments": [{"clip": "clip.mp4", "start": 1.0, "end": 2.5}, {"clip": "clip.mp4", "start": 2.5, "end": 4.0},
                                 {"clip": "clip.mp4", "start": 6.2, "end": 7.4}]}
        JUMPY = {"segments": [{"clip": "clip.mp4", "start": 8.4, "end": 9.6},       # the cold open, from late in the take
                              {"clip": "clip.mp4", "start": 1.0, "end": 2.5}, {"clip": "clip.mp4", "start": 2.5, "end": 4.0},
                              {"clip": "clip.mp4", "start": 10.1, "end": 11.0},
                              {"clip": "clip.mp4", "start": 5.0, "end": 6.0, "zoom": {"from": 1.0, "to": 1.15}}]}

        def job(scratch_plan, saved_plan=None, words=False):
            jd2 = os.path.join(eng, "projects", "reel")
            shutil.rmtree(jd2, ignore_errors=True)
            os.makedirs(os.path.join(jd2, "raw"))
            os.link(clip, os.path.join(jd2, "raw", "clip.mp4"))
            if saved_plan is not None:
                write_json(os.path.join(jd2, "transcript", "cuts.json"), saved_plan)
            if words:
                write_json(os.path.join(jd2, "transcript", "words.json"), {"clips": [{"clip": "clip.mp4", "words": [
                    {"w": f"w{n}", "start": n * 0.5 + 0.05, "end": n * 0.5 + 0.4, "prob": 0.9} for n in range(24)]}]})
            scratch = os.path.join(tmp, "scratch", "reels-editing-engine", "reel")
            shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
            os.makedirs(scratch)
            if scratch_plan is not None:
                write_json(os.path.join(scratch, "cuts.json"), scratch_plan)
            for f in (renders, reports):
                if os.path.exists(f):
                    os.remove(f)
            return jd2, scratch

        def run(**extra):
            env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                       REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                       VERIFY_CUT="0", VOICE_LEVEL="0", TRIM_RESTARTS="0", SNAP="0")
            for k in ("FLAT_RENDER", "VENC", "FAKE_KILL", "CLOSE_PAUSES"):
                env.pop(k, None)
            env.update(extra)
            return subprocess.run(["bash", stitch, os.path.join(eng, "projects", "reel")], cwd=eng, env=env,
                                  capture_output=True, text=True, encoding="utf-8")

        def read(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()

        # 3. signal 9: said plainly, no libx264 retry, no second plan, no hardware report
        jd2, _ = job(IN_ORDER, words=True)
        r = run(FAKE_KILL="1", VENC="h264_videotoolbox")
        check("3: a render the computer ended exits 137", r.returncode == 137, f"rc {r.returncode}\n{r.stderr[-800:]}")
        check("3: and says so plainly", "signal 9" in r.stderr and "out of memory" in r.stderr, r.stderr[-600:])
        check("3: never 'the hardware encoder failed', never a libx264 retry",
              "retrying on the software encoder" not in r.stderr, r.stderr[-600:])
        check("3: (the dead-air pass ran, so there was a second plan it could have tried)", "[pauses]" in r.stderr,
              r.stderr[-600:])
        check("3: never the same graph again on the edges as written", "once more" not in r.stderr, r.stderr[-600:])
        check("3: the render ran once", os.path.exists(renders) and len(read(renders).splitlines()) == 1,
              read(renders) if os.path.exists(renders) else "no render")
        check("3: and no hardware report", not os.path.exists(reports), read(reports) if os.path.exists(reports) else "")
        check("3: nothing saved over the job's cut", not os.path.exists(os.path.join(jd2, "transcript", "cuts.json")))

        # 4. reading order: a cut in filming order keeps one plain input; one that jumps back seeks its runs
        jd2, scratch = job(IN_ORDER)
        r = run(VENC="libx264")
        check("4: a cut in filming order renders", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-600:]}")
        argv = read(renders) if os.path.exists(renders) else ""
        check("4: with one input per file, read from the top", argv.count(" -i ") == 1 and " -ss " not in argv, argv)

        jd2, scratch = job(JUMPY)
        r = run(VENC="libx264")
        check("4: a cut that jumps back renders", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-600:]}")
        argv = read(renders) if os.path.exists(renders) else ""
        seeks = [int(m or 0) for m in re.findall(r"(?:-ss (\d+) )?-i ", argv)]   # per input: where it starts reading
        # 8.4 and 10.1 are one forward run, 1.0 to 6.0 the other: two inputs, each from 2 s before its first piece
        check("4: each forward run of it is its own input", seeks == [6, 0], f"{seeks} {argv}")
        edl = json.loads(read(os.path.join(jd2, "transcript", "cuts.json")))["segments"]
        graph = read(os.path.join(scratch, "graph.txt"))
        trims = re.findall(r"\[(\d+):v\][^;]*?trim=([\d.e-]+):([\d.e-]+)", graph)
        on_clock = len(trims) == len(edl) and all(
            abs(float(a) + seeks[int(k)] - s["start"]) < 1e-9 and abs(float(b) + seeks[int(k)] - s["end"]) < 1e-9
            for (k, a, b), s in zip(trims, edl))
        check("4: every in and out point is the same frame on its input's clock", on_clock, f"{trims} {edl}")
        played = sum(float(s["end"]) - float(s["start"]) for s in edl)
        got = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              os.path.join(jd2, "outputs", "reel.mp4")], capture_output=True, text=True).stdout.strip()
        check("4: and the cut plays its full length", got and abs(float(got) - played) < 0.1, f"{got} vs {played:.3f}")

        # 5. the newer plan wins
        OLD = {"segments": [{"clip": "clip.mp4", "start": 1.0, "end": 2.0}]}
        EDITED = {"segments": [{"clip": "clip.mp4", "start": 1.0, "end": 2.0}, {"clip": "clip.mp4", "start": 6.0, "end": 7.0}]}
        jd2, scratch = job(OLD, saved_plan=EDITED)
        age(os.path.join(scratch, "cuts.json"), -120)          # left by an earlier stitch; the edit came after
        r = run(FLAT_RENDER="0")
        kept = json.loads(read(os.path.join(jd2, "transcript", "cuts.json")))["segments"]
        check("5: an edit to the saved plan since the last stitch is stitched", r.returncode == 0 and len(kept) == 2,
              f"rc {r.returncode} {kept}\n{r.stderr[-400:]}")
        check("5: and it says which plan it used", "newer than the one waiting in the scratch folder" in r.stderr, r.stderr[-400:])

        jd2, scratch = job(EDITED, saved_plan=OLD)
        age(os.path.join(jd2, "transcript", "cuts.json"), -120)  # a fresh plan (her Send, Finish's copy) after the save
        r = run(FLAT_RENDER="0")
        kept = json.loads(read(os.path.join(jd2, "transcript", "cuts.json")))["segments"]
        check("5: a fresh scratch plan still wins", r.returncode == 0 and len(kept) == 2, f"rc {r.returncode} {kept}")
        check("5: without a word about the saved one", "newer than the one waiting" not in r.stderr, r.stderr[-400:])
finally:
    ve._duration, ve._run_stitch, ve.ROOT = real_duration, real_run_stitch, real_root
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"full-quality cut: {len(fails)} failed")
    sys.exit(1)
print("full-quality cut: made when the cut changed, stopped when she says stop, never run out of memory for hours")
