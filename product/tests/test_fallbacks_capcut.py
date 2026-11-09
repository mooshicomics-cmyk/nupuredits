#!/usr/bin/env python3
"""test_fallbacks_capcut.py — never a dead end on the way to a CapCut draft.

One test (or more) per row of the fallback brief that lands in the CapCut builders and the editing engine:
   6  the editing engine is off: it is turned on (detached, no Terminal window) and the build carries on; one that
      will not start points at /report-a-problem; a connection lost mid-draft is never retried into a partial draft
   7  a save that runs past the wait is followed through /query_draft_status; any other slow call gets one longer try
   8  a missing config.json is written (port 9001) by the launcher, and the engine's own default is 9001 too
   9  a workspace that will not run or load is moved aside and rebuilt once (remembered); the launcher runs setup once
  10  a draft name already taken builds straight to the next version; hers is untouched
  11  iPhone HDR footage is converted and the build goes on; a conversion that fails keeps the refusal
  12  a missing sticker or sound cue is skipped with a line; a takeover with no font takes the pack's
  13  "Add to CapCut.bat" tries the engine's own Python before anything that can be the Store stand-in
  29  setup: winget / the direct Mac route for FFmpeg, a private Python when there is no 3.10+, a pip that will not
      upgrade itself is not fatal, Apple's python3 placeholder is never run
  31  smoke-test.sh does not call a missing VectCut config.json a failure

Nothing real is started: VectCut is a tiny local stand-in server, every tool the shell scripts reach for is a fake
on PATH, and CapCut's folders live in a temp HOME.
Run: python3 product/tests/test_fallbacks_capcut.py
"""
import http.server
import importlib.util
import io
import contextlib
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
VC = os.path.join(PRODUCT, "engine", "VectCutAPI")
FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")

# One temp HOME for the whole run, set BEFORE the builders are imported (CapCut's folder is read at import).
HOME = os.path.realpath(tempfile.mkdtemp(prefix="fallbacks-capcut-"))
os.environ["HOME"] = HOME
os.environ["LOCALAPPDATA"] = os.path.join(HOME, "AppData", "Local")
os.environ["REEL_NO_DEFAULT_MOTION"] = "1"
LOCAL = os.path.join(HOME, "_local")
os.environ["REELS_ENGINE_LOCAL"] = LOCAL
sys.path.insert(0, PRODUCT)


# ---- a stand-in for `requests`: the real API surface the engine code touches, over urllib -------------------
class _Resp:
    def __init__(self, code, body):
        self.status_code, self.text = code, body

    def json(self):
        return json.loads(self.text)


def _fake_requests():
    m = types.ModuleType("requests")
    ex = types.ModuleType("requests.exceptions")

    class RequestException(Exception):
        pass

    class ConnectionError(RequestException):  # noqa: A001
        pass

    class Timeout(RequestException):
        pass

    ex.RequestException, ex.ConnectionError, ex.Timeout = RequestException, ConnectionError, Timeout
    m.exceptions = ex
    m.handler = None          # a test can answer calls itself: handler(url, json, timeout) -> _Resp or raise

    def post(url, json=None, timeout=None):
        if m.handler:
            return m.handler(url, json, timeout)
        req = urllib.request.Request(url, data=__import__("json").dumps(json or {}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return _Resp(r.status, r.read().decode())
        except urllib.error.HTTPError as e:
            return _Resp(e.code, e.read().decode())
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            raise ConnectionError(str(e))
        except socket.timeout as e:
            raise Timeout(str(e))

    m.post = post
    return m


REQ = _fake_requests()
sys.modules["requests"] = REQ
sys.modules["requests.exceptions"] = REQ.exceptions

import fallbacks  # noqa: E402
import vectcut_engine as VE  # noqa: E402


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as fh:
        return fh.read()


def log_text():
    try:
        return read(os.path.join(LOCAL, "fallbacks.log"))
    except OSError:
        return ""


def reset_engine_state():
    VE._STATE.update(checked=False, launched=False, reached=False)
    REQ.handler = None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"/the/engine")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"success": True, "output": {"draft_id": "dfd_test"}}).encode())


def start_server(port):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class _Proc:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def write_exe(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ==== row 6: the editing engine is off =========================================================================
class Row6EngineOff(unittest.TestCase):
    def setUp(self):
        reset_engine_state()
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.real_launch, self.real_wait, self.real_poll = VE.launch, VE.LAUNCH_WAIT, VE.POLL
        VE.POLL = 0.05
        self.srv = None

    def tearDown(self):
        VE.launch, VE.LAUNCH_WAIT, VE.POLL = self.real_launch, self.real_wait, self.real_poll
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
        reset_engine_state()

    def test_an_engine_that_is_off_is_turned_on_and_the_build_carries_on(self):
        launched = []

        def launch():
            launched.append(1)
            self.srv = start_server(self.port)      # what the launcher does: the engine comes up a moment later
            return _Proc(None)
        VE.launch = launch
        with contextlib.redirect_stderr(io.StringIO()) as said:
            j = VE.post(self.base, "create_draft", {"width": 1080})
        self.assertTrue(j.get("success"), j)
        self.assertEqual(launched, [1])
        self.assertIn("turning it on", said.getvalue())
        self.assertNotIn("⛔", said.getvalue())
        self.assertIn("capcut-draft: the editing engine was off; turned it on", log_text())
        # a second call in the same build does not look again or launch again
        VE.post(self.base, "add_text", {"draft_id": "dfd_test"})
        self.assertEqual(launched, [1])

    def test_a_refused_first_call_turns_it_on_and_tries_once_more(self):
        self.srv = None
        VE._STATE["checked"] = True                  # the up-front look already happened (and found it on)
        calls = []

        def launch():
            calls.append("launch")
            self.srv = start_server(self.port)
            return _Proc(None)
        VE.launch = launch
        with contextlib.redirect_stderr(io.StringIO()):
            j = VE.post(self.base, "create_draft", {})
        self.assertTrue(j.get("success"))
        self.assertEqual(calls, ["launch"])

    def test_an_engine_that_will_not_start_points_at_report_a_problem(self):
        VE.launch = lambda: _Proc(1)                 # the launcher ran and ended without a server
        VE.LAUNCH_WAIT = 0.3
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(VE.NotRunning) as cm:
                VE.post(self.base, "create_draft", {})
        msg = str(cm.exception)
        self.assertIn("/report-a-problem", msg)
        self.assertIn("start-editor", msg)
        self.assertIsInstance(cm.exception, RuntimeError)   # every builder's `except RuntimeError` still catches it

    def test_a_connection_lost_mid_draft_is_never_retried_into_a_partial_draft(self):
        VE._STATE.update(checked=True, reached=True, launched=True)   # it answered earlier in this build
        sent = []
        REQ.handler = lambda url, data, timeout: (sent.append(url), (_ for _ in ()).throw(
            REQ.exceptions.ConnectionError("refused")))[1]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(VE.NotRunning) as cm:
                VE.post(self.base, "add_video", {"draft_id": "dfd_test"})
        self.assertIn("partway", str(cm.exception))
        self.assertEqual(len(sent), 1, "the call must not be sent again to an engine that lost the draft")

    def test_the_launcher_runs_detached_with_no_terminal_window(self):
        seen = {}
        real = subprocess.Popen

        def fake_popen(args, **kw):
            seen["args"], seen["kw"] = args, kw
            return _Proc(None)
        subprocess.Popen = fake_popen
        try:
            VE.launch()
        finally:
            subprocess.Popen = real
        if os.name == "nt":
            self.assertEqual(seen["args"][:2], ["cmd", "/c"])
        else:
            self.assertEqual(seen["args"], ["bash", VE.start_file()])
            self.assertTrue(seen["kw"].get("start_new_session"))
        self.assertIs(seen["kw"]["stdin"], subprocess.DEVNULL)
        cmd = read(os.path.join(VC, "start-editor.command"))
        self.assertNotIn("open -a Terminal", cmd)
        self.assertIn("exec ./venv-capcut/bin/python capcut_server.py", cmd)
        src = read(os.path.join(PRODUCT, "vectcut_engine.py"))
        self.assertIn("CREATE_NO_WINDOW", src)

    def test_every_draft_builder_goes_through_the_engine_backups(self):
        for f in ("cleanyap.py", "superyap.py", "capcut_handoff.py"):
            src = read(os.path.join(PRODUCT, f))
            self.assertIn("vectcut_engine.post(", src, f)
            self.assertNotIn("timeout=180)", src, f"{f} still calls VectCut directly")


# ==== row 7: slow calls ==========================================================================================
class Row7SlowCalls(unittest.TestCase):
    def setUp(self):
        reset_engine_state()
        VE._STATE.update(checked=True)
        self.real_poll = VE.POLL
        VE.POLL = 0.01

    def tearDown(self):
        VE.POLL = self.real_poll
        reset_engine_state()

    def test_a_save_that_runs_past_the_wait_is_followed_until_it_finishes(self):
        looks = []

        def handler(url, data, timeout):
            if url.endswith("/save_draft"):
                raise REQ.exceptions.Timeout("read timed out")
            if url.endswith("/query_draft_status"):
                self.assertEqual(data, {"task_id": "dfd_big"})
                looks.append(1)
                st = "completed" if len(looks) >= 3 else "processing"
                return _Resp(200, json.dumps({"success": True, "output": {"status": st, "draft_url": "u"}}))
            raise AssertionError(url)
        REQ.handler = handler
        with contextlib.redirect_stderr(io.StringIO()):
            j = VE.post("http://x", "save_draft", {"draft_id": "dfd_big", "draft_folder": "/f"})
        self.assertTrue(j["success"])
        self.assertEqual(len(looks), 3)
        self.assertIn("save_draft ran past 180s; followed it", log_text())

    def test_a_save_the_engine_says_failed_is_a_failed_call(self):
        def handler(url, data, timeout):
            if url.endswith("/save_draft"):
                raise REQ.exceptions.Timeout("read timed out")
            return _Resp(200, json.dumps({"success": True, "output": {"status": "failed", "message": "disk full"}}))
        REQ.handler = handler
        with contextlib.redirect_stderr(io.StringIO()):
            j = VE.post("http://x", "save_draft", {"draft_id": "d"})
        self.assertFalse(j["success"])
        self.assertIn("disk full", j["error"])

    def test_any_other_slow_call_gets_one_longer_try(self):
        waits = []

        def handler(url, data, timeout):
            waits.append(timeout)
            if len(waits) == 1:
                raise REQ.exceptions.Timeout("read timed out")
            return _Resp(200, json.dumps({"success": True, "output": {}}))
        REQ.handler = handler
        with contextlib.redirect_stderr(io.StringIO()):
            j = VE.post("http://x", "add_video", {"draft_id": "d"})
        self.assertTrue(j["success"])
        self.assertEqual(waits, [VE.TIMEOUT, VE.RETRY_TIMEOUT])

    def test_a_retry_turned_away_for_overlap_means_the_first_try_landed(self):
        n = []

        def handler(url, data, timeout):
            n.append(1)
            if len(n) == 1:
                raise REQ.exceptions.Timeout("read timed out")
            return _Resp(200, json.dumps({"success": False, "error": "New segment overlaps with existing segment"}))
        REQ.handler = handler
        with contextlib.redirect_stderr(io.StringIO()):
            j = VE.post("http://x", "add_video", {"draft_id": "d"})
        self.assertTrue(j["success"])
        self.assertIn("the first try had landed", log_text())

    def test_two_timeouts_stop_with_a_plain_message(self):
        def handler(url, data, timeout):
            raise REQ.exceptions.Timeout("read timed out")
        REQ.handler = handler
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(VE.TooSlow) as cm:
                VE.post("http://x", "add_video", {"draft_id": "d"})
        self.assertIn("/report-a-problem", str(cm.exception))


# ==== shell layouts for rows 8, 9, 29 =============================================================================
def engine_layout(tmp, setup_stub=None):
    """A copy of the engine's VectCut folder and the shared shell helpers, with a no-op PATH shim (the real one
    would pull this machine's own Homebrew tools in front of the fakes)."""
    root = os.path.join(tmp, "engine")
    vc = os.path.join(root, "product", "engine", "VectCutAPI")
    os.makedirs(vc)
    os.makedirs(os.path.join(root, "scripts"))
    for f in ("start-editor.command", "setup-editor-engine.sh", "requirements.txt"):
        shutil.copy(os.path.join(VC, f), os.path.join(vc, f))
    for f in ("_fallbacks.sh", "_python3-shim.sh", "_mac-arch.sh"):
        shutil.copy(os.path.join(ROOT, "scripts", f), os.path.join(root, "scripts", f))
    shutil.copy(os.path.join(PRODUCT, "fallbacks.py"), os.path.join(root, "product", "fallbacks.py"))
    with open(os.path.join(root, "scripts", "_path-shim.sh"), "w", encoding="utf-8") as fh:
        fh.write('[ -n "${FAKE_WINGET_BIN:-}" ] && [ -x "$FAKE_WINGET_BIN/ffmpeg" ] && PATH="$FAKE_WINGET_BIN:$PATH"\n:\n')
    if setup_stub is not None:
        write_exe(os.path.join(vc, "setup-editor-engine.sh"), setup_stub)
    return root, vc


# A stand-in python: `-c` answers (a version line when asked to print), `-m venv DIR` makes a workspace whose
# python is GOOD_VENV_PY, `-m pip ...` succeeds unless the pip upgrade is told to fail.
GOOD_VENV_PY = """#!/bin/bash
if [ "$1" = -c ]; then case "$2" in *print*) echo 3.11.9 ;; esac; exit 0; fi
if [ "$1" = -m ] && [ "$2" = pip ]; then
  case "$*" in *--upgrade\\ pip*) [ -n "${PIP_UPGRADE_FAILS:-}" ] && exit 1 ;; esac
  exit 0
fi
[ "$1" = capcut_server.py ] && { echo "Running on http://127.0.0.1:9001"; exit 0; }
exit 0
"""
FAKE_PY3 = """#!/bin/bash
if [ "$1" = -m ] && [ "$2" = venv ]; then
  mkdir -p "$3/bin" && cp "$GOOD_VENV_PY_FILE" "$3/bin/python" && chmod +x "$3/bin/python"; exit 0
fi
if [ "$1" = -c ]; then case "$2" in *print*) echo 3.11.9 ;; esac; exit 0; fi
exit 0
"""


class ShellCase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="fb-capcut-sh-"))
        self.bin = os.path.join(self.tmp, "fakebin")
        self.local = os.path.join(self.tmp, "_local")
        self.good = os.path.join(self.tmp, "good-venv-python")
        write_exe(self.good, GOOD_VENV_PY)
        for tool in ("ffmpeg", "ffprobe", "node", "npx", "npm", "uv", "git", "lsof"):
            write_exe(os.path.join(self.bin, tool), "#!/bin/bash\nexit 1\n" if tool == "lsof" else "#!/bin/bash\nexit 0\n")
        # a quiet Homebrew whose shellenv adds nothing, so this Mac's real Homebrew python is never picked up
        write_exe(os.path.join(self.bin, "brew"), "#!/bin/bash\nexit 0\n")
        write_exe(os.path.join(self.bin, "python3"), FAKE_PY3)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, **extra):
        e = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": self.tmp, "REELS_ENGINE_LOCAL": self.local,
             "GOOD_VENV_PY_FILE": self.good, "PYTHON": sys.executable, "TMPDIR": self.tmp,
             "LOCALAPPDATA": os.path.join(self.tmp, "AppData", "Local")}
        e.update(extra)
        return e

    def run_sh(self, script, cwd, **extra):
        return subprocess.run(["bash", script], cwd=cwd, env=self.env(**extra), capture_output=True, text=True,
                              timeout=120)

    def log(self):
        try:
            return read(os.path.join(self.local, "fallbacks.log"))
        except OSError:
            return ""

    def pivots(self):
        try:
            return json.loads(read(os.path.join(self.local, "pivots.json")))
        except OSError:
            return {}


# ==== row 8: config.json ===========================================================================================
class Row8Config(ShellCase):
    def test_the_launcher_writes_a_missing_config_on_port_9001(self):
        root, vc = engine_layout(self.tmp)
        os.makedirs(os.path.join(vc, "venv-capcut", "bin"))
        shutil.copy(self.good, os.path.join(vc, "venv-capcut", "bin", "python"))
        r = self.run_sh(os.path.join(vc, "start-editor.command"), vc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = json.loads(read(os.path.join(vc, "config.json")))
        self.assertEqual(cfg["port"], 9001)
        self.assertIn("capcut-draft: the editing engine had no config.json", self.log())
        # and hers is never overwritten
        with open(os.path.join(vc, "config.json"), "w", encoding="utf-8") as fh:
            fh.write('{"port": 9001, "mine": true}')
        self.run_sh(os.path.join(vc, "start-editor.command"), vc)
        self.assertTrue(json.loads(read(os.path.join(vc, "config.json")))["mine"])

    def test_the_engine_itself_defaults_to_9001_without_a_config(self):
        d = os.path.join(self.tmp, "vc")
        os.makedirs(os.path.join(d, "settings"))
        shutil.copy(os.path.join(VC, "settings", "local.py"), os.path.join(d, "settings", "local.py"))
        spec = importlib.util.spec_from_file_location("vc_local", os.path.join(d, "settings", "local.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.PORT, 9001)
        self.assertEqual(mod.DRAFT_DOMAIN, "http://localhost:9001")

    def test_the_windows_launcher_writes_it_too(self):
        bat = read(os.path.join(VC, "start-editor.bat"))
        self.assertIn('if not exist "config.json"', bat)
        self.assertIn('"port": 9001', bat)


# ==== row 9: a broken workspace ====================================================================================
class Row9Workspace(ShellCase):
    def test_a_workspace_whose_python_will_not_run_is_rebuilt_and_remembered(self):
        root, vc = engine_layout(self.tmp)
        write_exe(os.path.join(vc, "venv-capcut", "bin", "python"), "#!/bin/bash\nexit 1\n")   # Python gone from under it
        r = self.run_sh(os.path.join(vc, "setup-editor-engine.sh"), vc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Moving it aside", r.stdout)
        self.assertEqual(read(os.path.join(vc, "venv-capcut", "bin", "python")), GOOD_VENV_PY)
        self.assertEqual([n for n in os.listdir(vc) if n.startswith("venv-capcut.broken")], [],
                         "the broken copy is cleared once the rebuild works")
        self.assertIn("editor-setup: the editing engine's workspace would not run", self.log())
        self.assertIn("vectcut.venv-rebuilt", self.pivots())

    def test_a_workspace_that_runs_but_will_not_load_its_tools_is_rebuilt_once(self):
        root, vc = engine_layout(self.tmp)
        write_exe(os.path.join(vc, "venv-capcut", "bin", "python"),
                  '#!/bin/bash\n[ "$1" = -c ] && case "$2" in *flask*) exit 1 ;; esac\nexit 0\n')
        r = self.run_sh(os.path.join(vc, "setup-editor-engine.sh"), vc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("its tools would not load", r.stdout)
        self.assertIn("vectcut.venv-rebuilt", self.pivots())

    def test_a_working_workspace_is_kept_exactly(self):
        root, vc = engine_layout(self.tmp)
        os.makedirs(os.path.join(vc, "venv-capcut", "bin"))
        shutil.copy(self.good, os.path.join(vc, "venv-capcut", "bin", "python"))
        with open(os.path.join(vc, "venv-capcut", "hers.txt"), "w", encoding="utf-8"):
            pass
        r = self.run_sh(os.path.join(vc, "setup-editor-engine.sh"), vc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already exists and runs. Keeping it.", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(vc, "venv-capcut", "hers.txt")))
        self.assertEqual(self.pivots(), {})

    def test_the_launcher_runs_setup_once_when_the_workspace_will_not_load(self):
        count = os.path.join(self.tmp, "setup-runs")
        stub = (f'#!/bin/bash\necho run >> "{count}"\necho "Setting up your editing engine."\n'
                f'mkdir -p venv-capcut/bin && cp "$GOOD_VENV_PY_FILE" venv-capcut/bin/python\n')
        root, vc = engine_layout(self.tmp, setup_stub=stub)
        r = self.run_sh(os.path.join(vc, "start-editor.command"), vc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(count).count("run"), 1)
        self.assertIn("Running on http://127.0.0.1:9001", r.stdout)
        self.assertIn("start-editor ran its setup once", self.log())

    def test_a_setup_that_cannot_fix_it_runs_once_and_points_at_report_a_problem(self):
        count = os.path.join(self.tmp, "setup-runs")
        root, vc = engine_layout(self.tmp, setup_stub=f'#!/bin/bash\necho run >> "{count}"\nexit 1\n')
        r = self.run_sh(os.path.join(vc, "start-editor.command"), vc)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(read(count).count("run"), 1, "never a loop")
        self.assertIn("/report-a-problem", r.stdout)


# ==== row 29: setup takes the working route =======================================================================
class Row29Setup(ShellCase):
    def _working_venv(self, vc):
        os.makedirs(os.path.join(vc, "venv-capcut", "bin"))
        shutil.copy(self.good, os.path.join(vc, "venv-capcut", "bin", "python"))

    def test_windows_without_ffmpeg_installs_it_with_winget(self):
        root, vc = engine_layout(self.tmp)
        self._working_venv(vc)
        for t in ("ffmpeg", "ffprobe"):
            os.remove(os.path.join(self.bin, t))
        winbin = os.path.join(self.tmp, "winget-ffmpeg")
        write_exe(os.path.join(self.bin, "uname"), "#!/bin/bash\necho MINGW64_NT-10.0\n")
        write_exe(os.path.join(self.bin, "winget"),
                  f'#!/bin/bash\necho "$*" > "{self.tmp}/winget-args"\nmkdir -p "{winbin}"\n'
                  f'printf "#!/bin/bash\\nexit 0\\n" > "{winbin}/ffmpeg"; cp "{winbin}/ffmpeg" "{winbin}/ffprobe"\n'
                  f'chmod +x "{winbin}"/*\n')
        r = self.run_sh(os.path.join(vc, "setup-editor-engine.sh"), vc, FAKE_WINGET_BIN=winbin)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--id Gyan.FFmpeg", read(os.path.join(self.tmp, "winget-args")))
        self.assertIn("editor-setup: FFmpeg was missing; setup installed it itself", self.log())

    def test_a_mac_without_homebrew_takes_the_direct_route_for_ffmpeg(self):
        if sys.platform != "darwin":
            self.skipTest("the direct route is the Mac branch")
        root, vc = engine_layout(self.tmp)
        self._working_venv(vc)
        for t in ("ffmpeg", "ffprobe", "brew"):
            os.remove(os.path.join(self.bin, t))
        write_exe(os.path.join(root, "scripts", "intel-mac-install.sh"),
                  f'#!/bin/bash\necho "$MAC_DIRECT_ROUTE $1" > "{self.tmp}/direct-args"\nmkdir -p "$HOME/.local/bin"\n'
                  'for t in ffmpeg ffprobe; do printf "#!/bin/bash\\nexit 0\\n" > "$HOME/.local/bin/$t"; '
                  'chmod +x "$HOME/.local/bin/$t"; done\n')
        r = self.run_sh(os.path.join(vc, "setup-editor-engine.sh"), vc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(os.path.join(self.tmp, "direct-args")).strip(), "1 ffmpeg")
        self.assertNotIn("brew.sh", r.stdout)

    def test_a_pip_that_will_not_upgrade_itself_is_not_fatal(self):
        root, vc = engine_layout(self.tmp)
        self._working_venv(vc)
        r = self.run_sh(os.path.join(vc, "setup-editor-engine.sh"), vc, PIP_UPGRADE_FAILS="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Editing engine ready", r.stdout)

    def _functions(self, *names):
        src = read(os.path.join(VC, "setup-editor-engine.sh"))
        out = []
        for n in names:
            i = src.index(f"\n{n}() ") + 1
            j = src.index("\n}\n", i) + 3
            out.append(src[i:j])
        return "\n".join(out)

    def test_no_python_310_gets_a_private_one_instead_of_stopping(self):
        root = os.path.join(self.tmp, "r")
        write_exe(os.path.join(root, "scripts", "ensure-python.sh"),
                  f'#!/bin/bash\necho "installing a private Python" >&2\necho "{self.bin}/py311"\n')
        write_exe(os.path.join(self.bin, "py311"), "#!/bin/bash\nexit 0\n")
        script = ("set -euo pipefail\nOSK=other; THIS_MACHINE=computer\n" + f'_R="{root}"\n'
                  + self._functions("is_py310", "get_python") + '\nget_python && echo "PYBIN=$PYBIN"\n')
        r = subprocess.run(["bash", "-c", script], env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertIn(f"PYBIN={self.bin}/py311", r.stdout, r.stderr)

    def test_apples_python3_placeholder_is_never_run(self):
        ran = os.path.join(self.tmp, "placeholder-ran")
        stub_dir = os.path.join(self.tmp, "usrbin")
        write_exe(os.path.join(stub_dir, "python3"), f'#!/bin/bash\ntouch "{ran}"\nexit 1\n')
        script = ("OSK=mac\n" + self._functions("is_apple_placeholder")
                  + f'\nmac_clt_stub() {{ [ "$1" = "{stub_dir}/python3" ]; }}\n'
                  + f'PATH="{stub_dir}:$PATH"\nis_apple_placeholder python3 && echo SKIPPED\n')
        r = subprocess.run(["bash", "-c", script], env=self.env(), capture_output=True, text=True, timeout=30)
        self.assertIn("SKIPPED", r.stdout)
        self.assertFalse(os.path.exists(ran))
        src = read(os.path.join(VC, "setup-editor-engine.sh"))
        self.assertIn("is_apple_placeholder \"$cand\" && continue", src)
        self.assertIn("ensure-python.sh", src)
        self.assertNotIn("Please install Homebrew first", src)

    def test_the_setup_script_parses(self):
        for f in ("setup-editor-engine.sh", "start-editor.command"):
            r = subprocess.run(["bash", "-n", os.path.join(VC, f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + r.stderr)


# ==== row 31: smoke test ===========================================================================================
class Row31Smoke(unittest.TestCase):
    def test_a_missing_vectcut_config_is_not_a_failure(self):
        src = read(os.path.join(ROOT, "scripts", "smoke-test.sh"))
        lines = [ln for ln in src.splitlines() if "config.json" in ln and not ln.lstrip().startswith("#")]
        self.assertTrue(lines)
        self.assertFalse(any('bad "' in ln for ln in lines), lines)
        r = subprocess.run(["bash", "-n", os.path.join(ROOT, "scripts", "smoke-test.sh")], capture_output=True)
        self.assertEqual(r.returncode, 0)


# ==== row 13: "Add to CapCut.bat" ==================================================================================
class Row13StoreBat(unittest.TestCase):
    def test_the_engines_own_python_is_tried_first(self):
        import capcut_store_redirect as store
        bat = store._BAT
        own = bat.index(r"venv-capcut\Scripts\python.exe")
        self.assertLess(own, bat.index("where py"))
        self.assertLess(own, bat.index("\npython install_to_capcut.py"))
        self.assertIn('"%REE_PY%" -c ""', bat, "the engine's Python is run once before it is trusted")
        self.assertTrue(bat.isascii())


# ==== the builders: rows 10, 11, 12 =================================================================================
if "PIL" not in sys.modules:
    try:
        import PIL.Image  # noqa: F401
    except Exception:
        pil = types.ModuleType("PIL"); pil.Image = types.ModuleType("PIL.Image")
        sys.modules["PIL"], sys.modules["PIL.Image"] = pil, pil.Image

import draft_safety  # noqa: E402
draft_safety.capcut_running = lambda: False
draft_safety._snap_file = lambda: os.path.join(HOME, ".draft-snapshots.json")
import capcut_front  # noqa: E402
capcut_front.capcut_running = lambda: False
import learned  # noqa: E402
learned.STORE = os.path.join(HOME, "learned.json")
import cleanyap, superyap, packbuild, hdr  # noqa: E402,E401

BUTTER = [packbuild.role("Butter", "headline")["font_path"], packbuild.role("Butter", "thought")["font_path"]]
TEXTS = ["why your\nreels are stuck", "start with a cold\nopen instead"]


def make_clip(path, hlg=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sdr = path if not hlg else path + ".sdr.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=108x192:rate=30:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-colorspace", "bt709", sdr], check=True)
    if hlg:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", sdr, "-vf",
                        "colorspace=all=bt2020:format=yuv420p10:iall=bt709,"
                        "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc",
                        "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1",
                        "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                        path], check=True)
        os.remove(sdr)
    return path


def vectcut_draft(mod, did, clip_src, copy=True):
    """A draft as VectCut leaves it after save_draft (the same shape test_finalize_guards.py builds). copy=False:
    the draft plays her file where it is, outside the draft."""
    folder = os.path.join(mod.CAP, did)
    os.makedirs(os.path.join(folder, "assets", "video"))
    clip = os.path.join(folder, "assets", "video", os.path.basename(clip_src)) if copy else clip_src
    if copy:
        shutil.copyfile(clip_src, clip)
    texts = [{"id": f"T{i}", "type": "text", "line_spacing": 0.02, "alignment": 0,
              "content": json.dumps({"text": t, "styles": [{"range": [0, len(t)], "size": 12,
                                                            "font": {"path": "Inter_Black", "id": ""}}]})}
             for i, t in enumerate(TEXTS)]
    seg = {"id": "S0", "material_id": "V0", "extra_material_refs": [], "render_index": 0,
           "source_timerange": {"start": 0, "duration": 2_000_000},
           "target_timerange": {"start": 0, "duration": 2_000_000},
           "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}},
           "uniform_scale": {"on": True, "value": 1.0}, "common_keyframes": []}
    tsegs = [{"id": f"TS{i}", "material_id": f"T{i}", "extra_material_refs": [], "render_index": 15000,
              "source_timerange": {"start": 0, "duration": 900_000},
              "target_timerange": {"start": i * 1_000_000, "duration": 900_000},
              "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.5}}} for i in range(2)]
    d = {"id": did, "duration": 2_000_000, "fps": 30.0, "config": {}, "canvas_config": {"width": 1080, "height": 1920},
         "materials": {"videos": [{"id": "V0", "path": clip, "material_name": os.path.basename(clip),
                                   "duration": 2_000_000, "width": 108, "height": 192, "type": "video"}],
                       "audios": [], "texts": texts, "material_animations": []},
         "tracks": [{"id": "MAIN", "type": "video", "flag": 0, "name": "", "is_default_name": True, "segments": [seg]},
                    {"id": "TXT", "type": "text", "flag": 0, "name": "", "is_default_name": True, "segments": tsegs}]}
    with open(draft_safety.draft_json(folder), "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    with open(os.path.join(folder, "draft_meta_info.json"), "w", encoding="utf-8") as fh:
        json.dump({"draft_id": "META-ID", "draft_materials": []}, fh)
    return folder


def fresh_cap(mod):
    shutil.rmtree(mod.CAP, ignore_errors=True)
    os.makedirs(mod.CAP)
    capcut_front.CAP = mod.CAP
    capcut_front.META = os.path.join(mod.CAP, "root_meta_info.json")
    capcut_front.STATE_DIR = HOME
    capcut_front.STATE = os.path.join(HOME, "capcut-front.json")
    with open(os.path.join(mod.CAP, "root_meta_info.json"), "w", encoding="utf-8") as fh:
        json.dump({"all_draft_store": [], "draft_ids": 0, "root_path": mod.CAP}, fh)


def finalize(mod, did, name, clip_src, copy=True):
    vectcut_draft(mod, did, clip_src, copy)
    real_call = mod.call
    mod.call = lambda ep, _strict=True, **k: {"success": True, "output": {}}
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            got = mod.finalize(did, name, dict(zip(TEXTS, BUTTER)), fallback_font=BUTTER[0])
    finally:
        mod.call = real_call
    return got, out.getvalue()


def registered_names(mod):
    meta = json.loads(read(os.path.join(mod.CAP, "root_meta_info.json")))
    return [e.get("draft_name") for e in meta.get("all_draft_store", [])]


@unittest.skipUnless(FFMPEG, "needs ffmpeg and ffprobe")
class Row10NameTaken(unittest.TestCase):
    def test_a_taken_name_builds_to_the_next_version_and_hers_is_untouched(self):
        clip = make_clip(os.path.join(HOME, "media", "clip.mp4"))
        for mod in (cleanyap, superyap):
            with self.subTest(mod.__name__):
                fresh_cap(mod)
                got, _ = finalize(mod, "dfd_cat_1790000001_first", "My Reel 1.1", clip)   # her draft
                self.assertEqual(got, "My Reel 1.1")
                hers = draft_safety.draft_json(os.path.join(mod.CAP, "My Reel 1.1"))
                before = read(hers, "rb")
                got, said = finalize(mod, "dfd_cat_1790000002_again", "My Reel 1.1", clip)
                self.assertEqual(got, "My Reel 1.2")
                self.assertIn('"My Reel 1.1" is already a project in CapCut, so this build is "My Reel 1.2"', said)
                self.assertEqual(read(hers, "rb"), before, "her draft must never be touched")
                self.assertTrue(os.path.isdir(os.path.join(mod.CAP, "My Reel 1.2")))
                self.assertIn("My Reel 1.2", registered_names(mod))
                self.assertFalse(os.path.isdir(os.path.join(mod.CAP, "dfd_cat_1790000002_again")))
        self.assertIn("draft name 'My Reel 1.1' was already taken; built to 'My Reel 1.2' instead", log_text())


@unittest.skipUnless(FFMPEG, "needs ffmpeg and ffprobe")
class Row11HDR(unittest.TestCase):
    def setUp(self):
        self.real_apple, self.real_to_sdr = hdr.apple_converter, hdr.to_sdr
        hdr.apple_converter = lambda: None          # the ffmpeg path, the one every PC takes

    def tearDown(self):
        hdr.apple_converter, hdr.to_sdr = self.real_apple, self.real_to_sdr

    def test_add_cut_converts_the_jobs_hdr_clips_before_laying_the_cut(self):
        for mod in (cleanyap, superyap):
            with self.subTest(mod.__name__):
                job = os.path.join(HOME, "projects", f"hdr-{mod.__name__}")
                raw = make_clip(os.path.join(job, "raw", "IMG_1.MOV"), hlg=True)
                seen = []
                real_place = mod.cut_placement.place
                mod.cut_placement.place = lambda call, did, cuts, rawdir, punch: seen.append(hdr.hdr_kind(raw))
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        mod.add_cut("dfd", [], os.path.join(job, "raw"))
                finally:
                    mod.cut_placement.place = real_place
                self.assertEqual(seen, [None], "the cut must be laid on the normal-colour copy")
                self.assertEqual(hdr.hdr_kind(os.path.join(job, "hdr-originals", "IMG_1.MOV")), "hlg")
        self.assertIn("HDR clip(s) reached a CapCut build; converted them", log_text())

    def test_an_hdr_file_left_in_the_draft_is_converted_and_the_build_goes_on(self):
        clip = make_clip(os.path.join(HOME, "media", "hlg.mov"), hlg=True)
        for mod in (cleanyap, superyap):
            with self.subTest(mod.__name__):
                fresh_cap(mod)
                got, _ = finalize(mod, "dfd_cat_1790000003_hdr", "HDR Reel 1.1", clip)
                self.assertEqual(got, "HDR Reel 1.1")
                d = json.loads(read(draft_safety.draft_json(os.path.join(mod.CAP, got))))
                for v in d["materials"]["videos"]:
                    self.assertIsNone(hdr.hdr_kind(v["path"]), v["path"])
        self.assertEqual(hdr.hdr_kind(clip), "hlg", "the source outside the draft is never changed")

    def test_her_own_hdr_file_outside_the_draft_is_never_changed(self):
        clip = make_clip(os.path.join(HOME, "media", "hers-hlg.mov"), hlg=True)
        before = read(clip, "rb")
        fresh_cap(cleanyap)
        got, _ = finalize(cleanyap, "dfd_cat_1790000005_hdr", "Her HDR 1.1", clip, copy=False)
        self.assertEqual(read(clip, "rb"), before, "her own file must never be rewritten")
        d = json.loads(read(draft_safety.draft_json(os.path.join(cleanyap.CAP, got))))
        for v in d["materials"]["videos"]:
            self.assertNotEqual(v["path"], clip)
            self.assertIsNone(hdr.hdr_kind(v["path"]), v["path"])

    def test_a_conversion_that_fails_keeps_the_refusal(self):
        clip = make_clip(os.path.join(HOME, "media", "hlg2.mov"), hlg=True)

        def broken(src, dst):
            raise RuntimeError("no encoder")
        hdr.to_sdr = broken
        for mod in (cleanyap, superyap):
            with self.subTest(mod.__name__):
                fresh_cap(mod)
                with self.assertRaises(RuntimeError) as cm:
                    finalize(mod, "dfd_cat_1790000004_hdr", "Still HDR 1.1", clip)
                self.assertIn("hdr.py <job> --apply", str(cm.exception))
                self.assertFalse(os.path.isdir(os.path.join(mod.CAP, "Still HDR 1.1")))


class Row12OptionalItems(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.real = (cleanyap.call, superyap.call)
        cleanyap.call = superyap.call = lambda ep, _strict=True, **k: self.sent.append(ep) or {"success": True}

    def tearDown(self):
        cleanyap.call, superyap.call = self.real

    def test_a_missing_sticker_is_skipped_and_the_rest_builds(self):
        for mod in (cleanyap, superyap):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                got = mod.add_png("d", os.path.join(HOME, "nope", "doodle.png"), 0, 1, 0, 0, "img_1")
            self.assertIsNone(got)
            self.assertIn("sticker skipped", out.getvalue())
        self.assertEqual(self.sent, [])
        self.assertIn("sticker 'doodle.png' was missing", log_text())

    def test_a_real_sticker_still_goes_in(self):
        try:
            from PIL import Image
            p = os.path.join(HOME, "real.png")
            Image.new("RGBA", (10, 10)).save(p)
        except Exception:
            self.skipTest("needs Pillow")
        cleanyap.add_png("d", p, 0, 1, 0, 0, "img_1")
        self.assertEqual(self.sent, ["add_image"])

    def test_a_missing_sound_cue_is_skipped(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            got = cleanyap.add_sfx("d", os.path.join(HOME, "nope", "whoosh.wav"), 1.0, 0.3)
        self.assertIsNone(got)
        self.assertIn("sound cue skipped", out.getvalue())
        self.assertEqual(self.sent, [])

    def test_a_takeover_with_no_font_takes_the_packs_own(self):
        fonts = []
        real_ctx, real_add = superyap.learned.context, superyap.add_text
        superyap.learned.context = lambda: {"pack": "Butter"}
        superyap.add_text = lambda did, t, s, e, fp, *a, **k: fonts.append(fp)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                superyap.takeover("d", [("one", 0.0), ("two", 0.5)], 1.0, 30, 0.2, "tk")
        finally:
            superyap.learned.context, superyap.add_text = real_ctx, real_add
        self.assertEqual(set(fonts), {packbuild.role("Butter", "takeover")["font_path"]})

    def test_a_takeover_with_no_pack_at_all_still_stops(self):
        real_ctx, real_style = superyap.learned.context, superyap._USER_STYLE
        superyap.learned.context = lambda: {}
        superyap._USER_STYLE = os.path.join(HOME, "no-user-style.json")
        try:
            with self.assertRaises(RuntimeError):
                superyap.takeover("d", [("one", 0.0)], 1.0, 30, 0.2, "tk")
        finally:
            superyap.learned.context, superyap._USER_STYLE = real_ctx, real_style
        self.assertEqual(self.sent, [])

    def test_no_style_pack_chosen_still_raises(self):
        real = cleanyap.default_pack
        cleanyap.default_pack = lambda: None
        try:
            with self.assertRaises(ValueError):
                cleanyap.hook_font(None)
        finally:
            cleanyap.default_pack = real


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(HOME, ignore_errors=True)
