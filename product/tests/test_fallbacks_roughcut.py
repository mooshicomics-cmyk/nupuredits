#!/usr/bin/env python3
"""The rough cut is never a dead end: when a step's usual path fails and a working route exists, the cut takes it,
finishes, logs one line, and (when the cause is the computer) remembers it so the next cut goes straight there.

  1. QUICK RESTARTS. Speech tools that can't load torch (exit 69), a native crash (139), the faster-whisper mark
     beside the WhisperX venv, or a computer with only the faster-whisper venv: the stitch goes on without the
     pass, logs it once, remembers it, and later stitches skip it with one plain line. Only a real Intel Mac
     gets the Intel message. A real crash on this reel stays loud and is never remembered. A rebuilt venv
     (a new ready record) tries again. trim-restarts.py says "can't run" with its own exit code, reads the
     job's real footage folder, and never waits on the terminal or forever on ffmpeg.
  2. BOUNDARY SNAP. When it does not finish, the stitch uses the authored edges and logs it.
  3. THE RENDER. A render that stops on the snapped plan is run once more on the plan as written, and only that
     run's EDL is saved. Never after her Ctrl-C (130), never when the snap did not run.
  4. VERIFY-CUT. The listen-back uses the first interpreter that can load faster_whisper (not merely the first
     that exists), remembers it, forgets it when it fails, and a listen-back that runs too long is skipped.
  5. CLEAN_CUT. Matches the stitch: a computer that can't run the restart pass, a multi-clip job and an
     unfinished snap are skipped with a note, still clean; it passes the full job path to trim-restarts.

Everything runs in throwaway folders with stand-in interpreters and REELS_ENGINE_LOCAL pointed at a scratch
folder, so nothing real is touched.

Run:  python3 product/tests/test_fallbacks_roughcut.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def executable(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tmp = tempfile.mkdtemp()
LOCAL = os.path.join(tmp, "local")
os.environ["REELS_ENGINE_LOCAL"] = LOCAL     # every note/remember in this process and its children goes here
LOG = os.path.join(LOCAL, "fallbacks.log")
PIVOTS = os.path.join(LOCAL, "pivots.json")


def reset_local():
    shutil.rmtree(LOCAL, ignore_errors=True)


def pivots():
    try:
        return json.loads(read(PIVOTS) or "{}")
    except ValueError:
        return {}


FFMPEG = shutil.which("ffmpeg")
HAVE_STITCH = os.name != "nt" and FFMPEG and shutil.which("ffprobe") and shutil.which("bash")

try:
    # ══ trim-restarts.py on its own (row 1) ═════════════════════════════════════════════════════════════
    tr_path = os.path.join(SCRIPTS, "trim-restarts.py")
    job0 = os.path.join(tmp, "plain-job")
    os.makedirs(os.path.join(job0, "transcript"))
    with open(os.path.join(job0, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": [{"clip": "clip.mp4", "start": 0.5, "end": 1.5}]}, fh)
    with open(os.path.join(job0, "transcript", "words.json"), "w", encoding="utf-8") as fh:
        json.dump({"clips": [{"clip": "clip.mp4", "words": [{"w": "hi", "start": 0.5, "end": 0.9}]}]}, fh)

    # torch missing: its own exit code and a plain sentence, never an AttributeError further down
    r = subprocess.run([sys.executable, "-c",
                        "import sys, runpy; sys.modules['torch'] = None; path = sys.argv[1]; "
                        "sys.argv = [path, sys.argv[2]]; runpy.run_path(path, run_name='__main__')", tr_path, job0],
                       capture_output=True, text=True, encoding="utf-8")
    check("1: trim-restarts without torch exits 69", r.returncode == 69, f"rc {r.returncode} {r.stderr[-300:]}")
    check("1: and says the computer's speech tools can't run it",
          "speech tools can't run this pass" in r.stderr and "AttributeError" not in r.stderr, r.stderr[-300:])

    # its ffmpeg read: the job's real footage folder (no raw/ here), -nostdin, a timeout
    tr = load("trim_restarts_t", tr_path)
    check("1: media_dir is the job folder when there is no raw/", tr.media_dir(job0) == job0)
    os.makedirs(os.path.join(tmp, "raw-job", "raw"))
    check("1: media_dir is raw/ when intake made one",
          tr.media_dir(os.path.join(tmp, "raw-job")) == os.path.join(tmp, "raw-job", "raw"))
    seen = {}

    class Stop(Exception):
        pass

    def fake_run(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        raise Stop()

    tr._IMPORT_ERR = None
    tr.subprocess = types.SimpleNamespace(run=fake_run, DEVNULL=subprocess.DEVNULL,
                                          TimeoutExpired=subprocess.TimeoutExpired)
    old_argv = sys.argv
    sys.argv = ["trim-restarts.py", job0, "--cuts", os.path.join(job0, "transcript", "cuts.json")]
    try:
        tr.main()
    except Stop:
        pass
    finally:
        sys.argv = old_argv
    argv = seen.get("argv") or []
    check("1: ffmpeg reads the clip where the job keeps it", os.path.join(job0, "clip.mp4") in argv, str(argv))
    check("1: ffmpeg runs with -nostdin and a timeout", "-nostdin" in argv and seen["kw"].get("timeout"), str(seen))

    def fake_timeout(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

    tr.subprocess.run = fake_timeout
    sys.argv = ["trim-restarts.py", job0, "--cuts", os.path.join(job0, "transcript", "cuts.json")]
    try:
        tr.main()
        msg = ""
    except SystemExit as e:
        msg = str(e.code)
    finally:
        sys.argv = old_argv
    check("1: a stuck ffmpeg stops the pass with a plain reason", "still reading the sound" in msg, msg)

    # ══ stitch-cut.sh (rows 1, 2, 3) ══════════════════════════════════════════════════════════════════════
    if not HAVE_STITCH:
        print("stitch parts skipped (needs bash, ffmpeg and ffprobe on a POSIX system)")
    else:
        eng = os.path.join(tmp, "engine")
        for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_fallbacks.sh", "scripts/_mac-arch.sh",
                    "product/video_encoder.py", "product/hdr.py", "product/probe.py", "product/fallbacks.py"):
            os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
        shutil.copytree(SCRIPTS, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        executable(os.path.join(eng, "product", "make-handoff.py"), "import sys\n")
        eng_scripts = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts")
        stitch = os.path.join(eng_scripts, "stitch-cut.sh")
        snap_py = os.path.join(eng_scripts, "snap-to-sound.py")
        real_snap = read(snap_py)

        # stand-ins: uname/sysctl say which Mac this is; ffmpeg can fail the stitch once or with a given code
        bindir = os.path.join(tmp, "bin")
        real_uname = shutil.which("uname")
        executable(os.path.join(bindir, "uname"),
                   "#!/bin/bash\n"
                   "if [ \"$1\" = -m ] && [ -n \"${FAKE_MACHINE:-}\" ]; then echo \"$FAKE_MACHINE\"; exit 0; fi\n"
                   f"exec {real_uname!r} \"$@\"\n")
        executable(os.path.join(bindir, "sysctl"),
                   "#!/bin/bash\n[ \"$*\" = '-n hw.optional.arm64' ] && { [ \"${FAKE_MACHINE:-}\" = arm64 ] && echo 1; exit 0; }\n"
                   "exec /usr/sbin/sysctl \"$@\"\n")
        once = os.path.join(tmp, "fail-once")
        executable(os.path.join(bindir, "ffmpeg"),
                   "#!/bin/bash\n"
                   # the stitch's own call: its graph inline (-filter_complex) or from a file (-/filter_complex,
                   # -filter_complex_script), whichever this ffmpeg is handed
                   "for a in \"$@\"; do case \"$a\" in -filter_complex|-/filter_complex|-filter_complex_script)\n"
                   f"  if [ -e {once!r} ]; then rm -f {once!r}; echo 'stand-in encoder failure' >&2; exit \"${{FAKE_FAIL_RC:-1}}\"; fi\n"
                   ";; esac; done\n"
                   f"exec {FFMPEG!r} \"$@\"\n")

        media = os.path.join(tmp, "media")
        os.makedirs(media)
        clip = os.path.join(media, "clip.mp4")
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=4",
                        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)

        PLAN = {"segments": [{"clip": "clip.mp4", "start": 0.4, "end": 1.4, "transcript": "plan one"},
                             {"clip": "clip.mp4", "start": 2.1, "end": 3.3, "transcript": "plan two"}]}
        WORDS = {"clips": [{"clip": "clip.mp4", "words": [{"w": "hello", "start": 0.5, "end": 0.9, "prob": 0.9}]}]}

        wx = os.path.join(tmp, "wx-venv")
        fw = os.path.join(tmp, "fw-venv")
        tr_calls = os.path.join(tmp, "tr-calls.log")
        FAKE_TR = ("#!/bin/bash\n"
                   f"echo \"$*\" >> {tr_calls!r}\n"
                   "case \"${FAKE_TR:-ok}\" in\n"
                   "  tools) echo \"trim-restarts: this computer's speech tools can't run this pass (ModuleNotFoundError: No module named 'torch')\" >&2; exit 69 ;;\n"
                   "  segv) exit 139 ;;\n"
                   "  crash) echo 'Traceback (most recent call last):' >&2; echo \"KeyError: 'segments'\" >&2; exit 1 ;;\n"
                   "esac\nexit 0\n")

        def venvs(wx_py=True, fw_py=False, ready_mtime=1_700_000_000):
            for d in (wx, fw):
                shutil.rmtree(d, ignore_errors=True)
            for f in (wx + ".use-faster-whisper",):
                if os.path.exists(f):
                    os.remove(f)
            if wx_py:
                executable(os.path.join(wx, "bin", "python"), FAKE_TR)
                rec = os.path.join(wx, ".speech-tools-ready")
                with open(rec, "w", encoding="utf-8") as fh:
                    fh.write("cpu\n")
                os.utime(rec, (ready_mtime, ready_mtime))
            if fw_py:
                executable(os.path.join(fw, "bin", "python"), "#!/bin/bash\nexit 0\n")

        def job(plan=PLAN):
            jd = os.path.join(eng, "projects", "my-reel")
            shutil.rmtree(jd, ignore_errors=True)
            os.makedirs(os.path.join(jd, "raw"))
            os.makedirs(os.path.join(jd, "transcript"))
            os.link(clip, os.path.join(jd, "raw", "clip.mp4"))
            with open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8") as fh:
                json.dump(WORDS, fh)
            scratch = os.path.join(tmp, "scratch", "reels-editing-engine", "my-reel")
            shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
            os.makedirs(scratch)
            with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
                json.dump(plan, fh, indent=1)
            for f in (tr_calls, once):
                if os.path.exists(f):
                    os.remove(f)
            return jd, scratch

        def run(**env_extra):
            env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), PATH=bindir + os.pathsep + os.environ["PATH"],
                       REELS_ENGINE_WHISPERX_VENV=wx, REELS_ENGINE_NOFW_VENV=fw, VERIFY_CUT="0",
                       REELS_ENGINE_LOCAL=LOCAL, FAKE_MACHINE="arm64")
            for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "SNAP", "TRIM_RESTARTS", "WARM_MASTER", "VENC", "FAKE_TR",
                      "FAKE_FAIL_RC"):
                env.pop(k, None)
            env.update(env_extra)
            return subprocess.run(["bash", stitch, os.path.join(eng, "projects", "my-reel")], cwd=eng, env=env,
                                  capture_output=True, text=True, encoding="utf-8")

        def tr_ran():
            return os.path.exists(tr_calls)

        PLAIN = "this computer's speech tools can't run the quick-restart pass"

        # 1a. torch will not load: the cut finishes, the switch is logged and remembered ...
        reset_local(); venvs(); job()
        r = run(FAKE_TR="tools", SNAP="0", FLAT_RENDER="0")
        check("1a: a computer whose tools can't run the pass still stitches", r.returncode == 0,
              f"rc {r.returncode}\n{r.stderr[-600:]}")
        check("1a: and says so in one plain line, no CRASHED", PLAIN in r.stderr and "CRASHED" not in r.stderr,
              r.stderr[-600:])
        check("1a: the switch is logged", "trim-restarts:" in read(LOG), read(LOG))
        check("1a: and remembered for this build of the tools",
              pivots().get("trim-restarts.unavailable", {}).get("value") == ".speech-tools-ready@1700000000",
              str(pivots()))
        # ... so the next stitch skips it straight away, one line, nothing new in the log
        log_before = read(LOG)
        job()
        r = run(FAKE_TR="tools", SNAP="0", FLAT_RENDER="0")
        check("1a: a later stitch never tries the pass again", not tr_ran(), read(tr_calls))
        check("1a: and says so in one plain line", r.returncode == 0 and r.stderr.count(PLAIN) == 1, r.stderr[-600:])
        check("1a: without another log line", read(LOG) == log_before, read(LOG))
        # a rebuilt venv (new ready record) clears the memory: the pass is tried again
        venvs(ready_mtime=1_800_000_000); job()
        r = run(FAKE_TR="ok", SNAP="0", FLAT_RENDER="0")
        check("1a: rebuilt speech tools get the pass back", tr_ran() and "✓ quick-restart" in r.stderr, r.stderr[-600:])

        # 1b. a native crash (segfault, exit 139) is the computer too
        reset_local(); venvs(); job()
        r = run(FAKE_TR="segv", SNAP="0", FLAT_RENDER="0")
        check("1b: a native crash still stitches, plainly", r.returncode == 0 and PLAIN in r.stderr, r.stderr[-600:])
        check("1b: and is remembered", "trim-restarts.unavailable" in pivots(), str(pivots()))
        check("1b: the log names the crash", "crashed (exit 139)" in read(LOG), read(LOG))

        # 1c. a real crash on this reel stays loud and is never remembered
        reset_local(); venvs(); job()
        r = run(FAKE_TR="crash", SNAP="0", FLAT_RENDER="0")
        check("1c: a real crash is still reported as one", "CRASHED" in r.stderr and "KeyError" in r.stderr,
              r.stderr[-600:])
        check("1c: and not remembered", "trim-restarts.unavailable" not in pivots(), str(pivots()))

        # 1d. word-timings.sh moved this computer to faster-whisper: the pass is not even tried
        reset_local(); venvs(); job()
        open(wx + ".use-faster-whisper", "w", encoding="utf-8").close()
        r = run(FAKE_TR="ok", SNAP="0", FLAT_RENDER="0")
        check("1d: the faster-whisper mark skips the pass", not tr_ran() and PLAIN in r.stderr, r.stderr[-600:])
        check("1d: logged and remembered once", "faster-whisper" in read(LOG) and "trim-restarts.unavailable" in pivots(),
              read(LOG))

        # 1e. only the faster-whisper venv here: a PC or Apple-chip Mac gets the neutral line, an Intel Mac its own
        reset_local(); venvs(wx_py=False, fw_py=True); job()
        r = run(SNAP="0", FLAT_RENDER="0", FAKE_MACHINE="arm64")
        check("1e: not an Intel Mac: the neutral line, never 'Intel Mac'",
              PLAIN in r.stderr and "Intel Mac" not in r.stderr, r.stderr[-600:])
        if subprocess.run([real_uname, "-s"], capture_output=True, text=True).stdout.strip() == "Darwin":
            reset_local(); job()
            r = run(SNAP="0", FLAT_RENDER="0", FAKE_MACHINE="x86_64")
            check("1e: a real Intel Mac keeps its own message", "does not run on an Intel Mac" in r.stderr
                  and PLAIN not in r.stderr, r.stderr[-600:])
            check("1e: the Intel route is not a fallback (nothing logged)", read(LOG) == "", read(LOG))

        # 2. the snap does not finish: the authored edges are stitched, and the switch is logged
        reset_local(); venvs(); job()
        executable(snap_py, "import sys\nsys.stderr.write('snap stand-in: could not read the audio\\n')\nsys.exit(1)\n")
        r = run(FLAT_RENDER="0", TRIM_RESTARTS="0")
        jd = os.path.join(eng, "projects", "my-reel")
        saved = json.loads(read(os.path.join(jd, "transcript", "cuts.json")) or "{}")
        check("2: a snap that does not finish still stitches", r.returncode == 0, f"rc {r.returncode}\n{r.stderr[-500:]}")
        check("2: on the edges as written", [(round(s["start"], 1), round(s["end"], 1)) for s in saved.get("segments", [])]
              == [(0.4, 1.4), (2.1, 3.3)], str(saved))
        check("2: and the switch is logged", "snap-to-sound:" in read(LOG), read(LOG))
        check("2: nothing is remembered (it is about the reel)", pivots() == {}, str(pivots()))

        # 3. the render stops on the snapped plan: built once more on the plan as written
        executable(snap_py,
                   "import json, sys\nplan = json.load(open(sys.argv[3]))\n"
                   "for s in plan['segments']: s['start'] += 0.1\n"
                   "json.dump(plan, open(sys.argv[4], 'w'))\n")
        reset_local(); venvs(); jd, scratch = job()
        open(once, "w", encoding="utf-8").close()                              # the first render (the snapped plan) fails
        r = run(TRIM_RESTARTS="0", VENC="libx264")
        saved = json.loads(read(os.path.join(jd, "transcript", "cuts.json")) or "{}")
        check("3: a render that stops on the snapped plan is built on the written one", r.returncode == 0
              and "once more on the edges as written" in r.stderr, f"rc {r.returncode}\n{r.stderr[-700:]}")
        check("3: the saved EDL is the retry's, not the snapped attempt's",
              [round(s["start"], 1) for s in saved.get("segments", [])] == [0.4, 2.1], str(saved))
        check("3: the cut was rendered", os.path.exists(os.path.join(jd, "outputs", "my-reel.mp4")))
        check("3: and the switch is logged", "stitch:" in read(LOG), read(LOG))
        # her Ctrl-C (130) stops it, no retry
        reset_local(); venvs(); jd, _ = job()
        open(once, "w", encoding="utf-8").close()
        r = run(TRIM_RESTARTS="0", VENC="libx264", FAKE_FAIL_RC="130")
        check("3: exit 130 stays a stop, no retry", r.returncode == 130 and "once more" not in r.stderr,
              f"rc {r.returncode}\n{r.stderr[-500:]}")
        # no snap, no other plan: the failure stands
        reset_local(); venvs(); jd, _ = job()
        open(once, "w", encoding="utf-8").close()
        r = run(TRIM_RESTARTS="0", VENC="libx264", SNAP="0")
        check("3: with the snap off there is no retry", r.returncode != 0 and "once more" not in r.stderr,
              f"rc {r.returncode}\n{r.stderr[-500:]}")
        with open(snap_py, "w", encoding="utf-8") as fh:
            fh.write(real_snap)

    # ══ verify-cut.py (row 4) ═════════════════════════════════════════════════════════════════════════════
    reset_local()
    sys.path.insert(0, SCRIPTS)
    vc = load("verify_cut_t", os.path.join(SCRIPTS, "verify-cut.py"))
    va, vb = os.path.join(tmp, "venv-a"), os.path.join(tmp, "venv-b")
    probes = os.path.join(tmp, "probes.log")
    executable(os.path.join(va, "bin", "python"), f"#!/bin/bash\necho a >> {probes!r}\nexit 1\n")
    executable(os.path.join(vb, "bin", "python"), f"#!/bin/bash\necho b >> {probes!r}\nexit 0\n")
    os.environ["REELS_ENGINE_WHISPERX_VENV"], os.environ["REELS_ENGINE_NOFW_VENV"] = va, vb
    try:
        py = vc._speech_venv_py()
        check("4: the first venv that can load faster_whisper is used, not the first that exists",
              py == os.path.join(vb, "bin", "python"), str(py))
        check("4: skipping the first is logged", "verify-cut:" in read(LOG), read(LOG))
        check("4: and the working one remembered", pivots().get("verify-cut.python", {}).get("value") == py, str(pivots()))
        os.remove(probes)
        check("4: a later run does not probe again", vc._speech_venv_py() == py and not os.path.exists(probes),
              read(probes))

        # it stops working: forgotten, so the next run asks every venv again
        calls = []

        def fake_run(argv, **kw):
            calls.append((argv, kw))
            if argv[0] == "ffmpeg":
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 1, "", "No module named 'faster_whisper'")

        vc.subprocess = types.SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired,
                                              CompletedProcess=subprocess.CompletedProcess)
        try:
            vc._retranscribe(os.path.join(tmp, "x.mp4"), "base")
            raised = False
        except RuntimeError:
            raised = True
        check("4: a failed listen-back raises (main prints SKIPPED)", raised)
        check("4: and forgets the interpreter", "verify-cut.python" not in pivots(), str(pivots()))
        ff = next((c for c in calls if c[0][0] == "ffmpeg"), None)
        check("4: its ffmpeg runs with -nostdin and a timeout", ff and "-nostdin" in ff[0] and ff[1].get("timeout"),
              str(ff))
        asr = next((c for c in calls if c[0][0] != "ffmpeg"), None)
        check("4: the listen-back itself has a timeout", asr and asr[1].get("timeout"), str(asr))

        # a listen-back that runs too long (a stalled model download) is skipped in one plain line
        def slow_run(argv, **kw):
            if argv[0] == "ffmpeg":
                return subprocess.CompletedProcess(argv, 0, "", "")
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

        vc.subprocess.run = slow_run
        vjob = os.path.join(tmp, "vjob")
        os.makedirs(os.path.join(vjob, "outputs"))
        os.makedirs(os.path.join(vjob, "transcript"))
        open(os.path.join(vjob, "outputs", "vjob.mp4"), "wb").close()
        with open(os.path.join(vjob, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump({"segments": [{"clip": "a.mp4", "start": 0, "end": 2, "transcript": "hello there friend"}]}, fh)
        err = io.StringIO()
        sys.argv = ["verify-cut.py", vjob]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = vc.main()
        sys.argv = old_argv
        check("4: a timed-out listen-back is skipped, the cut stands", rc == 0 and "skipped this time" in err.getvalue(),
              err.getvalue())
        check("4: and logged", "took longer than" in read(LOG), read(LOG))
    finally:
        os.environ.pop("REELS_ENGINE_WHISPERX_VENV", None)
        os.environ.pop("REELS_ENGINE_NOFW_VENV", None)

    # ══ clean_cut.py (row 5) ══════════════════════════════════════════════════════════════════════════════
    reset_local()
    cc = load("clean_cut_t", os.path.join(ROOT, "product", "clean_cut.py"))
    cjob = os.path.join(tmp, "cjob")            # no words.json: the snap cannot finish here
    os.makedirs(os.path.join(cjob, "transcript"))
    with open(os.path.join(cjob, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": [{"clip": "clip.mp4", "start": 0.4, "end": 1.4}]}, fh)
    cwx = os.path.join(tmp, "cc-wx")
    cc_calls = os.path.join(tmp, "cc-calls.log")

    def cc_venv(mode):
        executable(os.path.join(cwx, "bin", "python"),
                   f"#!/bin/bash\necho \"$*\" >> {cc_calls!r}\n"
                   "case " + mode + " in\n"
                   "  tools) echo \"trim-restarts: this computer's speech tools can't run this pass\" >&2; exit 69 ;;\n"
                   "  multi) echo 'trim-restarts: this job has 2 clips, but this pass reads only the first.' >&2; exit 1 ;;\n"
                   "  crash) echo \"KeyError: 'segments'\" >&2; exit 1 ;;\nesac\nexit 0\n")
        cc.VENV = os.path.join(cwx, "bin", "python")
        if os.path.exists(cc_calls):
            os.remove(cc_calls)

    def run_clean():
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cc.clean_cut(cjob)
        return err.getvalue()

    cc_venv("tools")
    said = run_clean()
    check("5: tools that can't run the pass are skipped, still clean", cc.clean_cut.failed == [], said)
    check("5: and said plainly", "speech tools can't run this pass" in said, said)
    check("5: the full job path goes to trim-restarts", read(cc_calls).split()[-1:] == [cjob], read(cc_calls))
    check("5: remembered under the stitch's key", "trim-restarts.unavailable" in pivots(), str(pivots()))
    check("5: an unfinished snap keeps the authored edges, still clean",
          "edges kept as authored" in said and "snap-to-sound:" in read(LOG), said + read(LOG))
    cc_venv("ok")
    said = run_clean()
    check("5: the remembered pivot skips the pass next time", not os.path.exists(cc_calls) and cc.clean_cut.failed == [],
          read(cc_calls))
    reset_local()
    cc_venv("multi")
    said = run_clean()
    check("5: a multi-clip job is skipped with a note, not failed", cc.clean_cut.failed == [] and "one-clip" in said, said)
    cc_venv("crash")
    said = run_clean()
    check("5: a real crash on this reel is still a failure", cc.clean_cut.failed == ["trim-restarts"], said)
    check("5: and is not remembered", "trim-restarts.unavailable" not in pivots(), str(pivots()))
    cc_venv("ok")
    open(cwx + ".use-faster-whisper", "w", encoding="utf-8").close()
    said = run_clean()
    check("5: the faster-whisper mark skips the pass", not os.path.exists(cc_calls) and cc.clean_cut.failed == [], said)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"FAILED: {len(fails)} — " + "; ".join(fails))
    sys.exit(1)
print("rough-cut fallbacks: every step finishes the cut, logs the switch, and remembers the computer's limits")
