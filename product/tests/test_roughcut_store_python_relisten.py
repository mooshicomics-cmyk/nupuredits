#!/usr/bin/env python3
"""The speech tools start from any Python, and the cut's re-listen ends.

  1. STORE PYTHON. product/venv_spawn.py is the one way the engine starts the speech venv's Python. When the
     venv's launcher stops with "No Python at ..." (exit 103), the same tools are started through their base
     Python, found where another packaged app's private copy of AppData put it, with the venv's packages (its
     .pth files included); the switch is logged once and remembered, and later runs go straight there. Under a
     Store Python that cannot see the venv's home, the doomed first try is skipped. A real failure is never
     retried; nothing found means the original failure comes back unchanged. Every spawner goes through it.
     check-setup.sh and the problem report each name a Store Python in one line.
  2. THE LISTEN-BACK MODEL. A model already on this computer beats a download, 8 GB of memory or less never gets
     more than small, and the pick is said in one line.
  3. THE CAP. At most two full re-listens per script: the second names the spots to hand over, a third run skips
     itself and lists them, a rewritten script or --again starts over.

Everything runs in throwaway folders with stand-in interpreters and REELS_ENGINE_LOCAL pointed at a scratch
folder, so nothing real is touched.

Run:  python3 product/tests/test_roughcut_store_python_relisten.py
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
import types

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PRODUCT = os.path.join(ROOT, "product")
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def executable(path, body):
    write(path, body)
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


tmp = tempfile.mkdtemp(prefix="store-relisten-")
LOCAL = os.path.join(tmp, "_local")
os.environ["REELS_ENGINE_LOCAL"] = LOCAL
LOG = os.path.join(LOCAL, "fallbacks.log")
saved_env = {k: os.environ.get(k) for k in ("APPDATA", "LOCALAPPDATA", "UV_PYTHON_INSTALL_DIR", "HF_HUB_CACHE")}


def pivots():
    try:
        return json.loads(read(os.path.join(LOCAL, "pivots.json")) or "{}")
    except Exception:
        return {}


def reset_local():
    shutil.rmtree(LOCAL, ignore_errors=True)


try:
    sys.path.insert(0, PRODUCT)
    import venv_spawn as vs

    # ══ 1. Store Python ═══════════════════════════════════════════════════════════════════════════════════
    store_exe = ("C:\\Users\\her\\AppData\\Local\\Microsoft\\WindowsApps\\"
                 "PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\\python.exe")
    check("1: the Store Python is recognised by its WindowsApps executable",
          vs.is_store_python(store_exe, "C:\\somewhere"))
    check("1: or by its PythonSoftwareFoundation install folder",
          vs.is_store_python("C:\\x\\python.exe",
                             "C:\\Program Files\\WindowsApps\\PythonSoftwareFoundation.Python.3.13_3.13.1_x64__qbz5n2kfra8p0"))
    check("1: a python.org or uv Python is not",
          not vs.is_store_python("C:\\Users\\her\\AppData\\Roaming\\uv\\python\\cpython-3.11.17\\python.exe",
                                 "C:\\Users\\her\\AppData\\Roaming\\uv\\python\\cpython-3.11.17"))
    check("1: nor this computer's own Python", not vs.is_store_python())
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "venv_spawn.py"), "--is-store-python"],
                       capture_output=True, text=True)
    check("1: the command-line check says no here (exit 1)", r.returncode == 1, f"rc {r.returncode} {r.stderr}")

    # A venv whose launcher cannot find its home, exactly as the Store Python's child sees it: the home is under
    # (fake) AppData\Roaming, and the real interpreter sits in another app's private copy under LocalCache.
    appdata, localapp = os.path.join(tmp, "Roaming"), os.path.join(tmp, "Local")
    os.environ["APPDATA"], os.environ["LOCALAPPDATA"] = appdata, localapp
    os.environ.pop("UV_PYTHON_INSTALL_DIR", None)
    home = os.path.join(appdata, "uv", "python", "cpython-3.11.17-test")
    hidden = os.path.join(localapp, "Packages", "Some.App_abc123", "LocalCache", "Roaming",
                          "uv", "python", "cpython-3.11.17-test")
    os.makedirs(hidden)
    real_base = os.path.realpath(getattr(sys, "_base_executable", None) or sys.executable)
    os.symlink(real_base, os.path.join(hidden, "python3"))
    venv = os.path.join(tmp, "wx-venv")
    major_minor = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site_dir = os.path.join(venv, "lib", major_minor, "site-packages")
    write(os.path.join(site_dir, "marker_mod.py"), "WHERE = 'venv'\n")
    extra = os.path.join(tmp, "pth-extra")
    write(os.path.join(extra, "pth_mod.py"), "OK = True\n")
    write(os.path.join(site_dir, "extra.pth"), extra + "\n")
    write(os.path.join(venv, "pyvenv.cfg"), f"home = {home}\ninclude-system-site-packages = false\n")
    launcher_calls = os.path.join(tmp, "launcher.log")
    py = os.path.join(venv, "bin", "python")
    executable(py, f"#!/bin/bash\necho x >> {launcher_calls!r}\n"
                   f"echo 'No Python at \"{home}/python.exe\"' >&2\nexit 103\n")
    script = os.path.join(tmp, "tool.py")
    write(script, "import sys, marker_mod, pth_mod\nprint(marker_mod.WHERE, pth_mod.OK, sys.argv[1:])\n"
                  "sys.exit(int(sys.argv[2]) if len(sys.argv) > 2 else 0)\n")

    calls = []

    def runner(argv, **kw):
        calls.append(argv)
        return subprocess.run(argv, **kw)

    check("1: the venv's home is not visible from here", not vs.home_visible(py))
    check("1: its base Python is found in the other app's private copy",
          vs.base_python(py) == os.path.join(hidden, "python3"), str(vs.base_python(py)))

    reset_local()
    r = vs.run(py, [script, "a"], runner=runner, step="trim-restarts", capture_output=True, text=True)
    check("1: after 'No Python at' (103) the tools run through their base Python",
          r.returncode == 0 and r.stdout.strip() == "venv True ['a']", f"rc {r.returncode} {r.stdout!r} {r.stderr[-300:]}")
    check("1: the launcher was tried once first", len(calls) == 2 and calls[0][0] == py, str(calls))
    check("1: the switch is logged in one line", "trim-restarts:" in read(LOG) and "No Python at" in read(LOG),
          read(LOG))
    check("1: and remembered for this computer", pivots().get("windows.store-python-spawn", {}).get("value") == "base",
          str(pivots()))

    calls.clear()
    os.remove(launcher_calls)
    r = vs.run(py, ["-c", "import marker_mod, sys; print(marker_mod.WHERE, sys.argv[1:])", "x", "y"],
               runner=runner, capture_output=True, text=True)
    check("1: remembered: the next run goes straight to the base Python",
          not os.path.exists(launcher_calls) and calls and calls[0][0] == os.path.join(hidden, "python3"), str(calls))
    check("1: '-c' code runs there with its arguments", r.stdout.strip() == "venv ['x', 'y']", r.stdout + r.stderr)
    rc = vs.call(py, [script, "b", "7"], runner=subprocess.run, stdout=subprocess.DEVNULL)
    check("1: an exit code comes back unchanged", rc == 7, str(rc))
    seen = {}

    def env_runner(argv, **kw):
        seen.update(kw.get("env") or {})
        return subprocess.CompletedProcess(argv, 0, "", "")

    os.environ["PYTHONHOME"] = "/nowhere"
    try:
        vs.run(py, [script], runner=env_runner)
    finally:
        os.environ.pop("PYTHONHOME", None)
    check("1: the base Python runs without PYTHONHOME and without the user's own packages",
          "PYTHONHOME" not in seen and seen.get("PYTHONNOUSERSITE") == "1", str({k: seen.get(k) for k in
                                                                                ("PYTHONHOME", "PYTHONNOUSERSITE")}))

    def timeout_runner(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

    try:
        vs.run(py, [script], runner=timeout_runner, timeout=5)
        timed = False
    except subprocess.TimeoutExpired:
        timed = True
    check("1: a timeout reaches the caller as before", timed)

    # Under a Store Python that cannot see the home, the doomed first try is skipped altogether.
    reset_local()
    calls.clear()
    os.remove(launcher_calls) if os.path.exists(launcher_calls) else None
    real_is_store = vs.is_store_python
    vs.is_store_python = lambda *a, **k: True
    try:
        r = vs.run(py, [script, "c"], runner=runner, step="verify-cut", capture_output=True, text=True)
        check("1: a Store parent that cannot see the home starts the base Python first",
              r.stdout.strip() == "venv True ['c']" and not os.path.exists(launcher_calls), str(calls))
        check("1: logged and remembered", "verify-cut:" in read(LOG) and "Microsoft Store" in read(LOG)
              and "windows.store-python-spawn" in pivots(), read(LOG))
        # a home it CAN see: the venv's own launcher is used, as on every other computer
        reset_local()
        write(os.path.join(venv, "pyvenv.cfg"), f"home = {hidden}\n")
        calls.clear()
        vs.run(py, [script], runner=runner, capture_output=True, text=True)
        check("1: a Store parent that can see the home uses the venv's own launcher first", calls[0][0] == py,
              str(calls))
    finally:
        vs.is_store_python = real_is_store
        write(os.path.join(venv, "pyvenv.cfg"), f"home = {home}\n")

    # Nothing to switch to: the original failure comes back unchanged and nothing is remembered.
    reset_local()
    shutil.rmtree(os.path.join(localapp, "Packages"))
    r = vs.run(py, [script], runner=subprocess.run, capture_output=True, text=True)
    check("1: with no base Python anywhere the launcher's own failure is returned",
          r.returncode == 103 and "No Python at" in r.stderr, f"rc {r.returncode}")
    check("1: and nothing is remembered", "windows.store-python-spawn" not in pivots(), str(pivots()))
    # A real failure of the tool is never run twice.
    failing = os.path.join(tmp, "fail-venv", "bin", "python")
    write(os.path.join(tmp, "fail-venv", "pyvenv.cfg"), f"home = {home}\n")
    executable(failing, f"#!/bin/bash\necho x >> {launcher_calls!r}\necho 'KeyError: segments' >&2\nexit 1\n")
    os.remove(launcher_calls) if os.path.exists(launcher_calls) else None
    r = vs.run(failing, [script], runner=subprocess.run, capture_output=True, text=True)
    check("1: a real failure is not retried", r.returncode == 1 and read(launcher_calls).count("x") == 1,
          read(launcher_calls))

    # Every place the engine starts the speech venv's Python goes through the helper.
    for rel in ("product/clean_cut.py", "product/gen-music.py", "product/vo-cutgrid.py",
                ".claude/skills/rough-cut/scripts/verify-cut.py"):
        src = read(os.path.join(ROOT, rel))
        check(f"1: {rel} starts the speech tools through venv_spawn", "venv_spawn.run(" in src
              or "venv_spawn.call(" in src)
    cc = load("clean_cut_store", os.path.join(PRODUCT, "clean_cut.py"))
    got = []

    def fake_spawn_run(p, args, runner=None, step="", **kw):
        got.append((p, args, step))
        return subprocess.CompletedProcess([p, *args], 0, "", "")

    cjob = os.path.join(tmp, "cjob")
    write(os.path.join(cjob, "transcript", "cuts.json"),
          json.dumps({"segments": [{"clip": "clip.mp4", "start": 0.4, "end": 1.4}]}))
    cvenv = os.path.join(tmp, "cc-venv", "bin", "python")
    executable(cvenv, "#!/bin/bash\nexit 0\n")
    cc.VENV = cvenv
    cc.venv_spawn = types.SimpleNamespace(run=fake_spawn_run)
    reset_local()
    with contextlib.redirect_stderr(io.StringIO()):
        cc.clean_cut(cjob)
    check("1: clean_cut starts trim-restarts through venv_spawn with the full job path",
          got and got[0][0] == cvenv and got[0][1][-1] == cjob and got[0][1][0].endswith("trim-restarts.py")
          and got[0][2] == "trim-restarts", str(got))

    cs = read(os.path.join(ROOT, "check-setup.sh"))
    check("1: check-setup.sh names a Store Python in one line",
          "venv_spawn.py\" --is-store-python" in cs and cs.count("Python (Microsoft Store)") == 1)
    pe = read(os.path.join(PRODUCT, "problem_evidence.py"))
    check("1: the problem report names a Store Python", "venv_spawn.is_store_python()" in pe
          and "Microsoft Store Python" in pe)
    r = subprocess.run(["bash", "-n", os.path.join(ROOT, "check-setup.sh")], capture_output=True, text=True)
    check("1: check-setup.sh still parses", r.returncode == 0, r.stderr)

    # ══ 2. The listen-back model ══════════════════════════════════════════════════════════════════════════
    reset_local()
    sys.path.insert(0, SCRIPTS)
    vc = load("verify_cut_store", os.path.join(SCRIPTS, "verify-cut.py"))
    only = lambda *names: (lambda m: m in names)   # noqa: E731
    check("2: English, nothing downloaded, plenty of memory: base", vc.pick_model("en", 16, only())[0] == "base")
    check("2: English with medium already here: medium, not a download",
          vc.pick_model("en", 16, only("medium"))[0] == "medium")
    m, why = vc.pick_model("en", 8, only("medium", "large-v3"))
    check("2: 8 GB never gets medium or large-v3", m == "base", m)
    check("2: and says why in plain words", "8 GB of memory" in why, why)
    check("2: 8 GB with small already here: small", vc.pick_model("en", 8, only("small", "medium"))[0] == "small")
    check("2: another language, nothing downloaded: small", vc.pick_model(None, 16, only())[0] == "small")
    check("2: another language with medium here: medium", vc.pick_model(None, 16, only("medium"))[0] == "medium")
    check("2: another language on 8 GB: small", vc.pick_model(None, 8, only("medium"))[0] == "small")
    check("2: unknown memory is treated as enough", vc.pick_model("en", None, only("medium"))[0] == "medium")
    hub = os.path.join(tmp, "hub")
    os.environ["HF_HUB_CACHE"] = hub
    write(os.path.join(hub, "models--Systran--faster-whisper-medium", "snapshots", "abc", "model.bin"), "x")
    os.makedirs(os.path.join(hub, "models--Systran--faster-whisper-small", "snapshots", "abc"))
    check("2: a finished download counts as here", vc.model_cached("medium"))
    check("2: a broken-off one does not", not vc.model_cached("small") and not vc.model_cached("base"))
    ram = vc.total_ram_gb()
    check("2: this computer's memory can be read", ram is None or ram > 0.5, str(ram))

    # ══ 3. The cap ═══════════════════════════════════════════════════════════════════════════════════════
    vjob = os.path.join(tmp, "vjob")
    write(os.path.join(vjob, "outputs", "vjob.mp4"), "")
    plan = "so here is the one thing nobody tells you about pricing your very first offer when you start out"

    def set_plan(text):
        write(os.path.join(vjob, "transcript", "cuts.json"),
              json.dumps({"segments": [{"clip": "a.mp4", "start": 0, "end": 6, "transcript": text}]}))

    heard = []

    def fake_retranscribe(mp4, model, lang="en"):
        heard.append(model)
        words = plan.split()
        words.insert(3, words[3])          # a stumble: "the the"
        return [(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate(words)]

    vc._retranscribe = fake_retranscribe
    vc.total_ram_gb = lambda: 8.0
    os.environ["HF_HUB_CACHE"] = os.path.join(tmp, "empty-hub")

    def main(*extra):
        out, err = io.StringIO(), io.StringIO()
        old = sys.argv
        sys.argv = ["verify-cut.py", vjob, *extra]
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = vc.main()
        finally:
            sys.argv = old
        return rc, out.getvalue(), err.getvalue()

    set_plan(plan)
    rc, out, err = main()
    check("3: the first listen flags the stumble", rc == 3 and "STUMBLE" in out and len(heard) == 1, out)
    check("3: the model is named in one line", err.count("listening back with the base model") == 1
          and "8 GB of memory" in err, err)
    check("3: the first listen asks for a fix", "run this again" in out and "the last one" not in out, out)
    rc, out, err = main()
    check("3: the second listen is the last one and says to hand it over",
          rc == 3 and len(heard) == 2 and "re-listen 2 of 2" in out and "hand the cut over" in out, out)
    rc, out, err = main()
    check("3: a third run on the same script does not listen again", len(heard) == 2, str(heard))
    check("3: it says so and lists what is still flagged",
          rc == 3 and "skipped" in out and "STUMBLE" in out, out)
    set_plan(plan.replace("very first", "first"))   # a fix that drops one word: still the same script
    main()
    check("3: a small fix to the same script still counts", len(heard) == 2, str(heard))
    main("--again")
    check("3: --again starts a fresh count", len(heard) == 3, str(heard))
    set_plan("a completely different script about something else she said on another day entirely")
    main()
    main()
    check("3: a rewritten script gets its own two listens", len(heard) == 5, str(heard))
    rc, out, err = main("--model", "small")
    check("3: the cap holds whatever model is asked for", len(heard) == 5, str(heard))
    os.remove(os.path.join(vjob, "transcript", ".verify-cut-listens.json"))
    main("--model", "small")
    check("3: a model asked for is used as is", heard[-1] == "small", str(heard))

    # The listen-back itself starts through venv_spawn (and skips the count when it cannot listen).
    spawned = []

    def stub_spawn(p, args, runner=None, step="", **kw):
        spawned.append((p, args[0], step, kw.get("timeout")))
        return subprocess.CompletedProcess([p, *args], 0, "[]\n", "")

    vc2 = load("verify_cut_store2", os.path.join(SCRIPTS, "verify-cut.py"))
    vc2.venv_spawn = types.SimpleNamespace(run=stub_spawn)
    vc2._speech_venv_py = lambda: "/venv/bin/python"
    vc2.subprocess = types.SimpleNamespace(
        run=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", ""),
        TimeoutExpired=subprocess.TimeoutExpired, CompletedProcess=subprocess.CompletedProcess)
    vc2._retranscribe(os.path.join(tmp, "x.mp4"), "base")
    check("3: the listen-back starts through venv_spawn, with its timeout",
          spawned and spawned[0][:3] == ("/venv/bin/python", "-c", "verify-cut") and spawned[0][3], str(spawned))

    skill = read(os.path.join(SCRIPTS, "..", "SKILL.md"))
    check("3: SKILL.md section 5 caps the loop at two full re-listens",
          "At most two full re-listens" in skill and "until clean" not in skill)
finally:
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"FAILED: {len(fails)} — " + "; ".join(fails))
    sys.exit(1)
print("store python + re-listen: the speech tools start from any Python, and the cut's re-listen ends")
