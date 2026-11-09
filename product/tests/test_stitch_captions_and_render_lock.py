#!/usr/bin/env python3
"""The stitch always leaves a caption transcript or says plainly why not; two renders never run at once.

  1. KEPT-WORDS NEVER DROPS THE WHOLE SCRIPT FOR ONE BAD PIECE. A span with no clip or no start, a word
     whose time is a string or a null, a clip name nobody transcribed, an EDL written as a bare list, a
     broken word-fix table: each used to stop kept-words.py with a traceback and no transcript. Now the
     piece is skipped with one "note:" line and the rest of her script is written. A clean run prints no
     note at all, so its output is what it always was.
  2. --plain, the simplest working route: every word inside a kept span, moved onto the cut the same way.
  3. stitch-cut.sh never ends quietly without a transcript: with no words.json it says how the rough cut
     makes one; when the full route stops it writes the plain one and logs a fallback line; when words.json
     cannot be read it moves a transcript left from an earlier cut aside and says so.
  4. Every HyperFrames render holds ONE lock for the computer (product/render_lock.py; the same protocol in
     product/hf_npx.cjs, so Python and Node renders wait on each other): a second render waits (one line, then one a
     minute), never stops the first; a lock left by a render that is gone is taken over with a note; Ctrl-C
     while waiting is a stop that leaves the other render's lock alone; the retries sit inside the one lock
     and a cache hit is answered before it.

Nothing real is touched: a throwaway engine copy, a temp _local and a temp lock folder.

Run:  python3 product/tests/test_stitch_captions_and_render_lock.py
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
KEPT_WORDS = os.path.join(SCRIPTS, "kept-words.py")
JOB = "my-reel"
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if isinstance(data, str):
            fh.write(data)
        else:
            json.dump(data, fh)


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


tmp = os.path.realpath(tempfile.mkdtemp())
try:
    # ── 1 + 2: kept-words.py on its own ─────────────────────────────────────────────────────────────────
    print("kept-words.py")
    jd = os.path.join(tmp, "eng", "projects", JOB)
    out = os.path.join(jd, "outputs", f"{JOB}.transcript.json")
    words_path = os.path.join(jd, "transcript", "words.json")
    cuts_path = os.path.join(jd, "transcript", "cuts.json")
    no_table = os.path.join(tmp, "no-such-table.json")

    def kept(words, cuts, *flags):
        write_json(words_path, words)
        write_json(cuts_path, cuts)
        if os.path.exists(out):
            os.remove(out)
        env = dict(os.environ, REELS_CAPTION_CORRECTIONS=no_table, PYTHONUTF8="1")
        argv = [sys.executable, KEPT_WORDS, *flags, words_path, cuts_path, out]
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env)
        got = read_json(out) if os.path.exists(out) else None
        return r, got

    def texts(got):
        return [w["text"] for w in got["words"]] if got else None

    WORDS = {"clips": [{"clip": "talk.MOV", "words": [
        {"word": "so", "start": 0.1, "end": 0.3}, {"word": "here", "start": 0.4, "end": 0.7},
        {"word": "is", "start": 0.8, "end": 1.0}, {"word": "dropped", "start": 2.0, "end": 2.5},
        {"word": "the", "start": 3.1, "end": 3.3}, {"word": "thing.", "start": 3.4, "end": 3.9}]}]}
    CUTS = {"segments": [{"clip": "talk-1080.MOV", "start": 0.05, "end": 1.1},
                         {"clip": "talk.MOV", "start": 3.0, "end": 4.0}]}
    r, got = kept(WORDS, CUTS)
    check("a clean run writes her script", r.returncode == 0 and texts(got) == ["so", "here", "is", "the", "thing."],
          r.stderr[-400:])
    check("a clean run prints no note", "note:" not in r.stdout, r.stdout)
    check("words land on the cut's clock", got and got["words"][3]["start"] == round(1.05 + 0.1, 3), got and got["words"][3])
    check("the engine line is unchanged on a clean run",
          got and got["engine"] == "whisperx-large-v3, remapped onto the cut timeline rather than transcribed again")

    bad = [
        ("a span with no clip", WORDS, {"segments": [{"start": 0, "end": 1.1}, CUTS["segments"][1]]},
         ["the", "thing."], "kept span 1 could not be read"),
        ("a span with a null start", WORDS, {"segments": [{"clip": "talk.MOV", "start": None, "end": 1},
                                                          CUTS["segments"][1]]}, ["the", "thing."], "kept span 1"),
        ("a word timed as a string", {"clips": [{"clip": "talk.MOV", "words": [
            {"word": "so", "start": "0.1", "end": "0.3"}, {"word": "odd", "start": "soon", "end": 0.6}]}]},
         {"segments": [{"clip": "talk.MOV", "start": 0, "end": 1}]}, ["so"], "time that is not a number"),
        ("a clip nobody transcribed", {"clips": [WORDS["clips"][0], {"clip": "b.mp4", "words": []}]},
         {"segments": [{"clip": "zzz.mp4", "start": 0, "end": 1}, CUTS["segments"][1]]}, ["the", "thing."],
         "no transcript for the clip zzz.mp4"),
        ("an EDL written as a bare list", WORDS, CUTS["segments"], ["so", "here", "is", "the", "thing."], None),
        ("an empty EDL", WORDS, {"segments": []}, [], None),
        ("odd unicode in a word", {"clips": [{"clip": "talk.MOV", "words": [
            {"word": "café 😀", "start": 0.1, "end": 0.4}, {"word": "​zw", "start": 0.5, "end": 0.7}]}]},
         {"segments": [{"clip": "talk.MOV", "start": 0, "end": 1}]}, ["café 😀", "​zw"], None),
        ("words.json with no clips key", {"words": []}, CUTS, [], "lists no clips"),
    ]
    for label, words, cuts, want, says in bad:
        r, got = kept(words, cuts)
        check(f"{label}: her script is still written", r.returncode == 0 and texts(got) == want,
              f"rc={r.returncode} got={texts(got)} {r.stderr[-300:]}")
        if says:
            check(f"{label}: says what it left out", says in r.stdout, r.stdout)

    # A broken word-fix table in the job folder is passed over, never the script.
    write_json(os.path.join(jd, "word-fixes.json"), '{"words": {"so": "SO"')
    r, got = kept(WORDS, CUTS)
    check("a broken word-fix table: her script is still written", r.returncode == 0 and texts(got) and texts(got)[0] == "so",
          r.stderr[-300:])
    check("a broken word-fix table: says so", "word-fix table (this reel) could not be read" in r.stdout, r.stdout)
    write_json(os.path.join(jd, "word-fixes.json"), {"words": {"so": "SO"}})
    r, got = kept(WORDS, CUTS)
    check("a good word-fix table still applies", texts(got) and texts(got)[0] == "SO", texts(got))
    os.remove(os.path.join(jd, "word-fixes.json"))

    # A language recorded as a plain string is that language, never its first letter.
    r, got = kept({"clips": [dict(WORDS["clips"][0], languages="de")]}, CUTS)
    check("a language written as a string is read whole", got and got["language_code"] == "de", got and got["language_code"])

    r, got = kept(WORDS, CUTS, "--plain")
    check("--plain writes the words inside the kept spans", r.returncode == 0 and texts(got) == ["so", "here", "is", "the", "thing."],
          r.stderr[-300:])
    check("--plain says it took the simple route", "the simple way" in r.stdout and "simple route" in got["engine"])
    r, got = kept("not json at all", CUTS)
    check("unreadable words.json: a one-line stop, no traceback, no file",
          r.returncode != 0 and "Traceback" not in r.stderr and "could not be read" in r.stderr and got is None,
          r.stderr[-300:])

    # ── 3: the stitch's caption block ───────────────────────────────────────────────────────────────────
    print("stitch-cut.sh caption transcript")
    FFMPEG = shutil.which("ffmpeg")
    if os.name == "nt" or not FFMPEG or not shutil.which("ffprobe") or not shutil.which("bash"):
        print("  skipped (needs bash, ffmpeg and ffprobe)")
    else:
        eng = os.path.join(tmp, "engine")
        for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh",
                    "scripts/_fallbacks.sh", "product/video_encoder.py", "product/hdr.py", "product/probe.py", "product/fallbacks.py"):
            if os.path.exists(os.path.join(ROOT, rel)):
                os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
        scripts = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts")
        shutil.copytree(SCRIPTS, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        stitch = os.path.join(scripts, "stitch-cut.sh")
        local = os.path.join(tmp, "local")
        clip = os.path.join(tmp, "clip.mp4")
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=4",
                        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=4", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)
        PLAN = {"segments": [{"clip": "clip.mp4", "start": 0.4, "end": 1.4}, {"clip": "clip.mp4", "start": 2.1, "end": 3.3}]}
        GOOD = {"clips": [{"clip": "clip.mp4", "words": [{"w": "hello", "start": 0.5, "end": 0.9},
                                                         {"w": "there", "start": 2.2, "end": 2.6}]}]}
        sjd = os.path.join(eng, "projects", JOB)
        caps = os.path.join(sjd, "outputs", f"{JOB}.transcript.json")

        def stitch_job(words=None, earlier=False):
            shutil.rmtree(sjd, ignore_errors=True)
            shutil.rmtree(os.path.join(tmp, "scratch"), ignore_errors=True)
            shutil.rmtree(local, ignore_errors=True)
            os.makedirs(os.path.join(sjd, "raw"))
            os.link(clip, os.path.join(sjd, "raw", "clip.mp4"))
            write_json(os.path.join(sjd, "transcript", "cuts.json"), PLAN)
            write_json(os.path.join(tmp, "scratch", "reels-editing-engine", JOB, "cuts.json"), PLAN)
            if words is not None:
                write_json(os.path.join(sjd, "transcript", "words.json"), words)
            if earlier:
                write_json(caps, {"text": "from an earlier cut", "words": []})
            env = dict(os.environ, TMPDIR=os.path.join(tmp, "scratch"), REELS_ENGINE_LOCAL=local,
                       REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                       VERIFY_CUT="0", FLAT_RENDER="0", SNAP="0", TRIM_RESTARTS="0",
                       REELS_CAPTION_CORRECTIONS=no_table)
            r = subprocess.run(["bash", stitch, "/".join(("projects", JOB))], cwd=eng, env=env,
                               capture_output=True, text=True, encoding="utf-8")
            log = os.path.join(local, "fallbacks.log")
            with open(log, encoding="utf-8") if os.path.exists(log) else io.StringIO("") as fh:
                return r, fh.read()

        r, log = stitch_job(GOOD)
        check("stitch, normal: builds the caption transcript",
              r.returncode == 0 and "built the caption transcript →" in r.stderr and os.path.exists(caps)
              and [w["text"] for w in read_json(caps)["words"]] == ["hello", "there"], r.stderr[-600:])
        check("stitch, normal: no fallback logged", "kept-words" not in log, log)

        r, log = stitch_job(None)
        check("stitch, no words.json: says plainly there is no transcript and how to make one",
              r.returncode == 0 and "no caption transcript for this cut: there are no word timings" in r.stderr
              and "word-timings.sh" in r.stderr, r.stderr[-600:])

        # The full route stops (a stand-in failure planted in the throwaway copy); the plain route writes it.
        kw_copy = os.path.join(scripts, "kept-words.py")
        with open(kw_copy, encoding="utf-8") as fh:
            original = fh.read()
        with open(kw_copy, "w", encoding="utf-8") as fh:
            fh.write(original.replace("def main():\n", "def main():\n    if '--plain' not in sys.argv:\n"
                                      "        raise RuntimeError('stand-in failure')\n", 1))
        r, log = stitch_job(GOOD)
        check("stitch, full route stops: the plain route writes the transcript",
              r.returncode == 0 and "the simple way" in r.stderr and os.path.exists(caps)
              and [w["text"] for w in read_json(caps)["words"]] == ["hello", "there"], r.stderr[-600:])
        check("stitch, full route stops: one fallback line is logged", "kept-words:" in log and "simple way" in log, log)
        with open(kw_copy, "w", encoding="utf-8") as fh:
            fh.write(original)

        r, log = stitch_job("{ not json", earlier=True)
        aside = caps[:-len(".json")] + ".earlier-cut.json"
        check("stitch, unreadable words.json: says plainly there is no transcript",
              r.returncode == 0 and "no caption transcript for this cut: the word timings or the cut could not be read"
              in r.stderr, r.stderr[-600:])
        check("stitch, unreadable words.json: the earlier cut's transcript is moved aside",
              not os.path.exists(caps) and os.path.exists(aside) and "moved aside" in r.stderr)
        check("stitch, unreadable words.json: logged for the report", "no caption transcript" in log, log)

    # ── 4: the render lock ──────────────────────────────────────────────────────────────────────────────
    print("render lock (product/render_lock.py, reel_render.py, hf_npx.cjs)")
    lock_dir = os.path.join(tmp, "locks")
    os.environ["REEL_RENDER_LOCK_DIR"] = lock_dir
    os.environ["REELS_ENGINE_LOCAL"] = os.path.join(tmp, "local-render")
    os.environ["REEL_RENDER_LOCK_POLL"] = "0.2"
    os.environ["REEL_RENDER_LOCK_SAY_EVERY"] = "1"
    sys.path.insert(0, os.path.join(ROOT, "product"))
    spec = importlib.util.spec_from_file_location("reel_render_under_test", os.path.join(ROOT, "product", "reel_render.py"))
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)
    import render_lock as RL
    lock = os.path.join(lock_dir, "render.lock")
    HF_NPX = os.path.join(ROOT, "product", "hf_npx.cjs")
    PY_HOLD = ("import sys, time\n"
               f"sys.path.insert(0, {os.path.join(ROOT, 'product')!r})\n"
               "import render_lock\n"
               "render_lock.acquire(sys.argv[1]); print('held', flush=True); time.sleep(float(sys.argv[2]))\n"
               "render_lock.release(True)\n")
    NODE_HOLD = (f"const h = require({json.dumps(HF_NPX)});\n"
                 "h.acquireLock(process.argv[1]).then(() => { console.log('held');\n"
                 "  setTimeout(() => { h.releaseLock(); process.exit(0); }, parseFloat(process.argv[2]) * 1000); });\n")
    NODE_TAKE = (f"const h = require({json.dumps(HF_NPX)});\n"
                 "h.acquireLock(process.argv[1]).then((took) => { console.log('took ' + took); h.releaseLock(); });\n")
    have_node = bool(shutil.which("node")) and os.name != "nt"   # the stand-in npx and SIGINT are POSIX

    def wait_held(p):
        return p.stdout.readline().strip() == "held"

    def py_take(what):
        buf = io.StringIO()
        t0 = time.monotonic()
        with redirect_stdout(buf):
            took = RL.acquire(what)
        return took, time.monotonic() - t0, buf.getvalue()

    check("reel_render takes the shared lock", rr._take_render_lock("a") and os.path.exists(lock)
          and read_json(lock)["pid"] == os.getpid())
    check("the same render asking again holds it deeper, never waits", rr._take_render_lock("a"))
    rr._release_render_lock(all_levels=True)
    check("release: the lock is gone", not os.path.exists(lock))
    with RL.held("ctx") as took:
        check("the context manager holds it", took and read_json(lock)["what"] == "ctx")
    check("and lets it go", not os.path.exists(lock))

    # A lock left by a render that is no longer running is taken over, with a note.
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    write_json(lock, {"pid": gone.pid, "started": time.time() - 30, "what": "old"})
    took, _, said = py_take("b")
    check("a lock left behind is taken over", took and read_json(lock)["pid"] == os.getpid(), said)
    check("taking it over is said in one line", "left behind" in said, said)
    RL.release(True)

    # Python waits on Python.
    holder = subprocess.Popen([sys.executable, "-c", PY_HOLD, "first", "2.5"], stdout=subprocess.PIPE, text=True)
    check("a first render holds the lock", wait_held(holder))
    took, waited, said = py_take("second")
    holder.wait()
    check("the second render waited for the first", took and waited >= 1.5 and holder.returncode == 0, f"{waited:.1f}s")
    check("waiting is said once, plainly",
          said.count("Another render is running on this computer (first); this one starts when it finishes.") == 1, said)
    check("a progress line while it waits", "Still waiting for the other render" in said, said)
    check("and when it starts", "The other render finished; rendering now" in said, said)
    RL.release(True)

    # Ctrl-C while waiting is a stop, and the other render's lock is left exactly as it was.
    write_json(lock, {"pid": os.getppid(), "started": time.time(), "what": "other"})
    real_sleep = RL.time.sleep
    def ctrl_c(_s):
        raise KeyboardInterrupt
    RL.time.sleep = ctrl_c
    buf, code = io.StringIO(), None
    try:
        with redirect_stdout(buf):
            RL.acquire("third")
    except SystemExit as e:
        code = e.code
    finally:
        RL.time.sleep = real_sleep
    check("Ctrl-C while waiting stops (exit 130)", code == 130, buf.getvalue())
    check("the other render's lock is untouched", os.path.exists(lock) and read_json(lock)["what"] == "other")
    os.remove(lock)

    # No lock folder can be made: the render goes ahead without one, said in one line.
    blocker = os.path.join(tmp, "a-file")
    write_json(blocker, "x")
    os.environ["REEL_RENDER_LOCK_DIR"] = os.path.join(blocker, "sub")
    took, _, said = py_take("x")
    check("an unwritable lock folder never stops a render", took is False and "rendering without waiting" in said, said)
    os.environ["REEL_RENDER_LOCK_DIR"] = lock_dir

    if not have_node:
        print("  Node checks skipped (no node on PATH)")
    else:
        # Python waits on a Node-held lock.
        holder = subprocess.Popen(["node", "-e", NODE_HOLD, "node-first", "2.5"], stdout=subprocess.PIPE, text=True)
        check("Node holds the lock", wait_held(holder) and read_json(lock)["what"] == "node-first")
        took, waited, said = py_take("python-second")
        holder.wait()
        check("Python waits for a Node render", took and waited >= 1.5
              and "Another render is running on this computer (node-first)" in said, said)
        RL.release(True)

        # Node waits on a Python-held lock, through the real `render` path (a stand-in npx records the call).
        bindir = os.path.join(tmp, "fake-npx")
        os.makedirs(bindir, exist_ok=True)
        calls = os.path.join(tmp, "npx-calls.log")
        with open(os.path.join(bindir, "npx"), "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/sh\necho \"$*\" >> {calls!r}\nexit 0\n")
        os.chmod(os.path.join(bindir, "npx"), 0o755)
        node_env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        holder = subprocess.Popen([sys.executable, "-c", PY_HOLD, "python-first", "2.5"], stdout=subprocess.PIPE, text=True)
        check("Python holds the lock", wait_held(holder))
        t0 = time.monotonic()
        r = subprocess.run(["node", HF_NPX, "render", "--dir", os.path.join(tmp, "proj"), "-o", "out.mp4"],
                           capture_output=True, text=True, encoding="utf-8", env=node_env)
        waited = time.monotonic() - t0
        holder.wait()
        check("a Node render waits for a Python render, then renders", r.returncode == 0 and waited >= 1.5
              and "Another render is running on this computer (python-first)" in r.stdout
              and "Still waiting for the other render" in r.stdout and "rendering now" in r.stdout
              and os.path.exists(calls) and " render " in open(calls, encoding="utf-8").read(), r.stdout + r.stderr)
        check("the Node render lets the lock go", not os.path.exists(lock))

        # Snapshots and checks never take the lock.
        write_json(lock, {"pid": os.getppid(), "started": time.time(), "what": "busy"})
        t0 = time.monotonic()
        r = subprocess.run(["node", HF_NPX, "snapshot", "--dir", "x"], capture_output=True, text=True,
                           encoding="utf-8", env=node_env, timeout=30)
        check("a Node snapshot never waits on the lock", r.returncode == 0 and time.monotonic() - t0 < 1.5
              and "Another render" not in r.stdout, r.stdout)

        # Ctrl-C while a Node render waits: a stop (130), the other render's lock untouched.
        p = subprocess.Popen(["node", HF_NPX, "render", "--dir", "y"], stdout=subprocess.PIPE, text=True,
                             encoding="utf-8", env=node_env)
        time.sleep(1.0)
        p.send_signal(2)
        out_txt, _ = p.communicate(timeout=20)
        check("Ctrl-C while a Node render waits stops it (130)", p.returncode == 130 and "Stopped while waiting" in out_txt,
              f"{p.returncode} {out_txt}")
        check("and the other render's lock is untouched", read_json(lock)["what"] == "busy")

        # Stale across languages: Node takes over a lock a dead Python render left ...
        write_json(lock, {"pid": gone.pid, "started": time.time() - 30, "what": "dead python"})
        r = subprocess.run(["node", "-e", NODE_TAKE, "node-new"], capture_output=True, text=True, encoding="utf-8")
        check("Node takes over a lock a gone Python render left", "took true" in r.stdout and "left behind" in r.stdout,
              r.stdout + r.stderr)
        # ... and Python takes over a lock a killed Node render left.
        holder = subprocess.Popen(["node", "-e", NODE_HOLD, "node-killed", "60"], stdout=subprocess.PIPE, text=True)
        check("Node holds the lock before it is killed", wait_held(holder))
        holder.kill()
        holder.wait()
        took, waited, said = py_take("python-after")
        check("Python takes over a lock a killed Node render left", took and "left behind" in said
              and read_json(lock)["pid"] == os.getpid() and waited < 5, said)
        RL.release(True)
        check("both sides log the takeover for the report",
              open(os.path.join(tmp, "local-render", "fallbacks.log"), encoding="utf-8").read().count("render-lock:") >= 3)

    # On Windows, Node reads a lock owner's start time from PowerShell (Git Bash's ps cannot see Windows
    # programs). Stood in for here on any machine: the pid is this test's own (alive), the lock is old.
    if shutil.which("node"):
        WIN_STUB = (f"const h = require({json.dumps(HF_NPX)});\n"
            "const mode = process.argv[1]; let seen = null;\n"
            "h.hooks.platform = () => 'win32';\n"
            "h.hooks.spawnSync = (cmd, args, opts) => { seen = {cmd, args, opts};\n"
            "  if (mode === 'timeout') return {error: Object.assign(new Error('t'), {code: 'ETIMEDOUT'}), status: null};\n"
            "  if (mode === 'error') return {status: 1, stdout: ''};\n"
            "  const t = mode === 'younger' ? Date.now() - 10000 : Date.now() - 4000000;\n"
            "  return {status: 0, stdout: new Date(t).toISOString().replace(/\\.(\\d{3})Z$/, '.$10000Z') + '\\r\\n'}; };\n"
            "const rec = {pid: parseInt(process.argv[2], 10), started: Date.now() / 1000 - 3600, what: 'x'};\n"
            "console.log(JSON.stringify({why: h.staleReason(rec, ''), seen}));\n")
        def win_look(mode):
            r = subprocess.run(["node", "-e", WIN_STUB, mode, str(os.getpid())], capture_output=True, text=True,
                               encoding="utf-8")
            return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {"why": None, "err": r.stderr}
        got = win_look("younger")
        check("Windows (stubbed): a pid that started after the lock is someone else's, so the lock is stale",
              "belongs to another program" in (got.get("why") or ""), got)
        seen = got.get("seen") or {}
        check("Windows (stubbed): asks PowerShell, non-interactive, with a short timeout",
              seen.get("cmd") == "powershell" and "-NoProfile" in seen.get("args", [])
              and "-NonInteractive" in seen.get("args", []) and 0 < (seen.get("opts") or {}).get("timeout", 0) <= 10000
              and "StartTime.ToUniversalTime().ToString('o')" in " ".join(seen.get("args", [])), seen)
        check("Windows (stubbed): the real owner (started before the lock) keeps it", win_look("older").get("why") == "")
        check("Windows (stubbed): no answer in time is 'cannot tell', not stale, and nothing throws",
              win_look("timeout").get("why") == "" and win_look("error").get("why") == "")

    # Where the lock sits in cmd_render: after the cache hit (which never waits) and around every attempt.
    with open(os.path.join(ROOT, "product", "reel_render.py"), encoding="utf-8") as fh:
        src = fh.read()
    body = src[src.index("def cmd_render(a):"):src.index("def _dur(path):")]
    cache_hit = body.index("unchanged since last clean render")
    take = body.index("_take_render_lock(")
    release = body.index("_release_render_lock(")
    attempts = [i for i in range(len(body)) if body.startswith("_render_full(", i) or body.startswith("_render_by_spans(", i)]
    check("a cache hit is answered before the lock", cache_hit < take)
    check("every render attempt (spans, full, the three retries) is inside the one lock",
          len(attempts) == 5 and all(take < i < release for i in attempts), attempts)
    with open(os.path.join(ROOT, "product", "render_lock.py"), encoding="utf-8") as fh:
        rl_src = fh.read()
    check("os.kill is never used to test a process on Windows",
          "os.name == \"nt\"" in rl_src[rl_src.index("def pid_running"):rl_src.index("def pid_age_seconds")])
    # Every other place that runs `hyperframes render` takes the same lock.
    for rel in ("product/hf_render.py", "product/render-check.py", "product/intel-render-diagnostic.py",
                ".claude/skills/beat-sheet/scripts/sandbox.py"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            check(f"{rel} renders inside the shared lock", "render_lock.held(" in fh.read())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    sys.exit(f"\n{len(fails)} failed")
print("\n✓ the stitch always leaves a caption transcript or says why not; one render at a time on this computer")
