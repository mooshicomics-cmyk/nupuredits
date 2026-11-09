#!/usr/bin/env python3
"""Never a dead end at setup: the backup routes for the speech tools' builder, one failed Homebrew install, and
the steps that used to wait forever.

  27  word-timings.sh with no uv: uv is fetched into ~/.local/bin; when it cannot be, or `uv venv` will not
      build (twice, or from the signed Python under Smart App Control), Python's own venv + pip build it with
      every pin, the switch is logged, and a mark beside the venv sends later builds straight there.
  28  An Apple-chip Mac whose Homebrew works but one `brew install` failed: set-me-up installs that tool by the
      direct route (MAC_DIRECT_ROUTE=1), which never pins a Mac that has Homebrew; check-setup.sh counts it
      as present and, for a remembered tool that is missing, prints the direct line instead of brew's.
  30  post-update.py's `browser ensure` and check-setup.sh's Defender question are time-limited, and
      set-me-up says the browser fetch is optional.

Everything runs on throwaway copies of the engine with stand-ins for uv, Python, curl, npx and powershell, so
nothing is downloaded or installed.

Run:  python3 product/tests/test_fallbacks_setup.py
"""
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
import unittest
import contextlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
JOB = "tx-job"   # the stand-in job word-timings.sh is pointed at
WT_DIR = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
SKILL = os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md")
SYS_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
POSIX = os.name != "nt" and shutil.which("bash") is not None


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_exec(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def lines(path):
    return read(path).splitlines() if os.path.exists(path) else []


# The venv interpreter stand-in: logs every call, answers pip and import probes, writes an empty transcript.
VENV_PY = """#!/bin/bash
printf '%s\\n' "$*" >> "$VENV_LOG"
case "$1" in
  -) cat >/dev/null; [ -n "${2:-}" ] && printf '{"clips": []}\\n' > "$2"; exit 0 ;;
  -m) exit 0 ;;
  -c) case "$2" in *torch.cuda*) exit 1 ;; esac; exit 0 ;;
esac
exit 0
"""

# A base Python (python3.11 by name, or the signed python.exe): answers the version probe, and `-m venv DIR`
# makes a venv holding the stand-in above.
BASE_PY = """#!/bin/bash
printf 'base %s\\n' "$*" >> "$CALL_LOG"
case "$1" in
  -c) exit 0 ;;
  -m) [ "$2" = venv ] && { mkdir -p "$3/bin"; cp "$VENVPY_SRC" "$3/bin/python"; exit 0; } ;;
esac
exit 0
"""

# uv that works for everything except making a venv.
UV_VENV_FAILS = """#!/bin/bash
printf 'uv %s\\n' "$*" >> "$CALL_LOG"
[ "$1" = venv ] && { echo "error: uv could not make the venv (stand-in)" >&2; exit 2; }
exit 0
"""

# uv that works: `uv venv DIR` makes a venv holding the stand-in.
UV_OK = """#!/bin/bash
printf 'uv %s\\n' "$*" >> "$CALL_LOG"
if [ "$1" = venv ]; then mkdir -p "$2/bin"; cp "$VENVPY_SRC" "$2/bin/python"; fi
exit 0
"""


@unittest.skipUnless(POSIX, "needs bash and a POSIX shell for the stand-ins")
class Row27NoUv(unittest.TestCase):
    """word-timings.sh builds the speech tools whether or not uv is here."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        t = self.tmp
        self.eng = os.path.join(t, "engine")
        for rel in ("scripts/_python3-shim.sh", "scripts/_mac-arch.sh", "scripts/_win-sac.sh",
                    "scripts/transcribe-nofw.py"):
            os.makedirs(os.path.dirname(os.path.join(self.eng, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(self.eng, rel))
        # No PATH repair in the stand-in engine: the real one would find this machine's own uv in Homebrew's
        # folder, and these runs are about a machine that has none.
        with open(os.path.join(self.eng, "scripts", "_path-shim.sh"), "w", encoding="utf-8") as fh:
            fh.write("# stand-in: no PATH repair\n")
        shutil.copytree(WT_DIR, os.path.join(self.eng, ".claude", "skills", "rough-cut", "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.wt = os.path.join(self.eng, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
        self.home = os.path.join(t, "home")
        self.fake = os.path.join(t, "bin")
        self.venvpy = os.path.join(t, "venvpy")
        write_exec(self.venvpy, VENV_PY)
        write_exec(os.path.join(self.fake, "nvidia-smi"), "#!/bin/sh\nexit 1\n")
        # python3 for the shims' scratch-folder question: the interpreter running this test
        write_exec(os.path.join(self.fake, "python3"), f"#!/bin/sh\nexec '{sys.executable}' \"$@\"\n")
        self.venv = os.path.join(self.home, ".cache", "reels-editing-engine", "whisperx-venv")
        self.call_log = os.path.join(t, "calls.log")
        self.venv_log = os.path.join(t, "venv.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def curl_installs_uv(self):
        """curl hands back an installer script that drops a working uv into ~/.local/bin."""
        src = os.path.join(self.tmp, "uv-ok")
        write_exec(src, UV_OK)
        write_exec(os.path.join(self.fake, "curl"), f"""#!/bin/sh
echo "curl $*" >> "$CALL_LOG"
echo 'mkdir -p "$HOME/.local/bin" && cp "{src}" "$HOME/.local/bin/uv"'
""")

    def curl_fails(self):
        write_exec(os.path.join(self.fake, "curl"), "#!/bin/sh\necho \"curl $*\" >> \"$CALL_LOG\"\nexit 7\n")

    def run_wt(self, extra=None):
        job = os.path.join(self.eng, "projects", "tx-job")
        shutil.rmtree(job, ignore_errors=True)
        os.makedirs(os.path.join(job, "raw"))
        open(os.path.join(job, "raw", "IMG_0001.MOV"), "w", encoding="utf-8").close()
        for p in (self.call_log, self.venv_log):
            if os.path.exists(p):
                os.remove(p)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("REELS_ENGINE", "UV_"))}
        env.update(HOME=self.home, TMPDIR=os.path.join(self.tmp, "scratch"), PATH=self.fake + ":" + SYS_PATH,
                   CALL_LOG=self.call_log, VENV_LOG=self.venv_log, VENVPY_SRC=self.venvpy)
        env.update(extra or {})
        os.makedirs(env["TMPDIR"], exist_ok=True)
        r = subprocess.run(["bash", self.wt, os.path.join("projects", JOB), "--force"], cwd=self.eng, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        return r, lines(self.call_log), lines(self.venv_log)

    def fallbacks_log(self):
        return lines(os.path.join(self.eng, "_local", "fallbacks.log"))

    def pip_installs(self, venv_calls):
        return [c for c in venv_calls if c.startswith("-m pip install") and "--upgrade pip" not in c]

    def test_27_uv_missing_is_fetched_into_local_bin(self):
        self.curl_installs_uv()
        r, calls, _ = self.run_wt()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertTrue(any(c.startswith("curl ") and "-m 600" in c and "astral.sh/uv/install.sh" in c for c in calls), calls)
        self.assertTrue(any(c.startswith("uv venv ") for c in calls), "the uv it fetched built the venv")
        self.assertTrue(any(c.startswith("uv pip install") and "whisperx==3.8.6" in c for c in calls), calls)
        self.assertTrue(any("transcriber: uv was not on this computer; installed it to ~/.local/bin" in ln
                            for ln in self.fallbacks_log()), self.fallbacks_log())
        self.assertFalse(os.path.exists(self.venv + ".no-uv"), "uv works here: nothing to remember")

    def test_27_uv_will_not_install_builds_with_python_venv_and_pip_and_remembers(self):
        self.curl_fails()
        write_exec(os.path.join(self.fake, "python3.11"), BASE_PY)
        r, calls, venv_calls = self.run_wt()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("base -m venv " + self.venv, calls)
        installs = self.pip_installs(venv_calls)
        wx = [c for c in installs if "whisperx==3.8.6" in c]
        self.assertTrue(wx, installs)
        self.assertIn("torch==2.8.0 torchaudio==2.8.0", wx[0], "TORCH_PIN rides along on the pip route")
        if os.uname().sysname == "Darwin":
            self.assertIn("--only-binary av", wx[0], "AV_WHEEL rides along on the pip route")
        self.assertTrue(os.path.exists(self.venv + ".no-uv"))
        self.assertTrue(any("uv was not on this computer and would not install; built the speech tools with "
                            "Python's own venv and pip" in ln for ln in self.fallbacks_log()), self.fallbacks_log())
        self.assertEqual(read(os.path.join(self.venv, ".speech-tools-ready")), "cpu\n")
        # The next build on this computer goes straight to the plain route: no download attempt first.
        shutil.rmtree(self.venv)
        r2, calls2, venv_calls2 = self.run_wt()
        self.assertEqual(r2.returncode, 0, r2.stderr[-1500:])
        self.assertFalse([c for c in calls2 if c.startswith("curl ")], calls2)
        self.assertIn("base -m venv " + self.venv, calls2)
        self.assertTrue(self.pip_installs(venv_calls2))

    def test_27_uv_venv_failing_twice_moves_to_python_venv(self):
        write_exec(os.path.join(self.fake, "uv"), UV_VENV_FAILS)
        write_exec(os.path.join(self.fake, "python3.11"), BASE_PY)
        r, calls, venv_calls = self.run_wt()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(len([c for c in calls if c.startswith("uv venv ")]), 2, "uv gets its two tries first")
        self.assertIn("base -m venv " + self.venv, calls)
        self.assertFalse([c for c in calls if c.startswith("uv pip install")], "every install went to the venv's pip")
        self.assertTrue([c for c in self.pip_installs(venv_calls) if "whisperx==3.8.6" in c], venv_calls)
        self.assertTrue(os.path.exists(self.venv + ".no-uv"))
        self.assertTrue(any("transcriber: uv venv failed twice; built the speech tools with Python's own venv and pip"
                            in ln for ln in self.fallbacks_log()), self.fallbacks_log())

    def test_27_smart_app_control_signed_python_builds_its_own_venv(self):
        """Windows under Git Bash with Smart App Control on: `uv venv --python <signed>` fails, so the signed
        Python's own venv is used, with the Smart App Control pins. Never a Python 3.12 fallback."""
        write_exec(os.path.join(self.fake, "uv"), UV_VENV_FAILS)
        write_exec(os.path.join(self.fake, "uname"),
                   "#!/bin/sh\ncase \"$1\" in -m) echo x86_64 ;; *) echo MINGW64_NT-10.0-26200 ;; esac\n")
        write_exec(os.path.join(self.fake, "reg"),
                   "#!/bin/sh\necho\necho '    VerifiedAndReputablePolicyState    REG_DWORD    0x1'\n")
        lad = os.path.join(self.tmp, "lad")
        signed = os.path.join(lad, "Programs", "Python", "Python311", "python.exe")
        write_exec(signed, BASE_PY)
        r, calls, venv_calls = self.run_wt({"LOCALAPPDATA": lad})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn(f"uv venv {self.venv} --python {signed}", calls)
        self.assertIn("base -m venv " + self.venv, calls)
        wx = [c for c in self.pip_installs(venv_calls) if "whisperx==3.7.9" in c]
        self.assertTrue(wx, venv_calls)
        self.assertIn("pandas==2.2.3", wx[0], "the Smart App Control pins ride along")
        self.assertIn("torch==2.8.0", wx[0])
        self.assertTrue(any("uv venv would not build from the signed Python" in ln for ln in self.fallbacks_log()))
        self.assertNotIn("3.12", read(self.wt).split("use_signed_python_if_blocked() {")[1].split("\n}\n")[0])

    def test_27_source_keeps_every_install_line_and_pivot_rebuild_can_fail_soft(self):
        src = read(os.path.join(WT_DIR, "word-timings.sh"))
        self.assertIn("make_venv || return 1", src, "the faster-whisper rebuild says no instead of dying under set -e")
        self.assertIn("if ! make_venv; then", src)
        self.assertIn('uv() { uv_by_pip "$@"; }', src)
        self.assertIn("type -P uv", src, "the stand-in function never counts as a real uv")
        self.assertIn('ensure_uv     # this venv may have been built before uv went missing', src)


@unittest.skipUnless(POSIX, "needs bash")
class Row28OneBrewInstallFails(unittest.TestCase):

    def test_28_set_me_up_says_what_to_do(self):
        sk = read(SKILL)
        part = sk[sk.index("If Homebrew works but ONE `brew install` fails"):]
        part = part[:part.index("\n---")]
        self.assertIn("MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh <tool>", part)
        self.assertIn('python3 product/fallbacks.py note set-me-up "', part)
        self.assertIn('python3 product/fallbacks.py remember setup.direct.<tool> 1 "brew install failed"', part)
        self.assertIn("python3 product/fallbacks.py get setup.direct.<tool>", part)
        self.assertIn("does not pin", part)
        # the Intel / no-Homebrew route is untouched
        self.assertIn("Run `MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all` FOR her.", sk)

    def _mac(self, tmp, with_brew):
        eng, fake, home = (os.path.join(tmp, d) for d in ("eng", "fake", "home"))
        os.makedirs(os.path.join(eng, "scripts"))
        for n in ("intel-mac-install.sh", "_mac-arch.sh"):
            shutil.copy(os.path.join(ROOT, "scripts", n), os.path.join(eng, "scripts", n))
        write_exec(os.path.join(fake, "uname"), "#!/bin/sh\ncase \"$1\" in -m) echo arm64 ;; *) echo Darwin ;; esac\n")
        write_exec(os.path.join(fake, "sw_vers"), "#!/bin/sh\necho 15.1\n")
        write_exec(os.path.join(fake, "sysctl"), "#!/bin/sh\ncase \"$2\" in hw.optional.arm64) echo 1 ;; *) echo 8 ;; esac\n")
        if with_brew:
            write_exec(os.path.join(fake, "brew"), "#!/bin/sh\nexit 0\n")
        pin = os.path.join(home, ".local", "share", "reels-editing-engine", "mac-route")
        env = {k: v for k, v in os.environ.items() if not k.startswith("MAC_")}
        env.update(HOME=home, PATH=fake + ":" + SYS_PATH, MAC_DIRECT_ROUTE="1", MAC_ROUTE_PIN=pin,
                   MAC_INTEL_BIN=os.path.join(home, ".local", "bin"), _MA_SYS_ROOT=os.path.join(tmp, "sysroot"),
                   TMPDIR=tmp)
        # an unknown tool: the run goes through the route and pin decisions, then stops before downloading
        r = subprocess.run(["bash", "scripts/intel-mac-install.sh", "not-a-tool"], cwd=eng, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        return r, pin

    def test_28_direct_route_runs_on_apple_chip_and_never_pins_a_mac_with_homebrew(self):
        with tempfile.TemporaryDirectory() as tmp:
            r, pin = self._mac(tmp, with_brew=True)
            self.assertIn("unknown tool", r.stderr, r.stdout + r.stderr)   # it ran, it did not refuse the Mac
            self.assertNotIn("Use the normal setup (Homebrew)", r.stdout + r.stderr)
            self.assertFalse(os.path.exists(pin), "a Mac whose Homebrew works stays on Homebrew")
        with tempfile.TemporaryDirectory() as tmp:   # control: no Homebrew at all, the CLT fallback pins
            r, pin = self._mac(tmp, with_brew=False)
            self.assertTrue(os.path.exists(pin), r.stdout + r.stderr)

    def _install_cmd(self, key, local):
        """check-setup.sh's install line for one tool on a Homebrew Mac, its own functions run on their own."""
        cs = read(os.path.join(ROOT, "check-setup.sh"))
        fns = ""
        for name in ("direct_remembered() {", "install_cmd() {"):
            start = cs.index("\n" + name) + 1
            fns += cs[start:cs.index("\n}\n", start) + 3]
        script = f"engine_dir() {{ echo '{ROOT}'; }}\nOS=mac\nMACROUTE=brew\n{fns}\ninstall_cmd {key}\n"
        env = dict(os.environ, REELS_ENGINE_LOCAL=local)
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True,
                              encoding="utf-8").stdout.strip()

    def test_28_check_setup_offers_the_direct_line_for_a_remembered_tool_only(self):
        sys.path.insert(0, os.path.join(ROOT, "product"))
        try:
            import fallbacks
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as local:
            old = os.environ.get("REELS_ENGINE_LOCAL")
            os.environ["REELS_ENGINE_LOCAL"] = local
            try:
                self.assertEqual(self._install_cmd("ffmpeg", local), "brew install ffmpeg")
                fallbacks.remember("setup.direct.ffmpeg", "1", "brew install failed")
                fallbacks.remember("setup.direct.python", "1", "brew install failed")
            finally:
                if old is None:
                    os.environ.pop("REELS_ENGINE_LOCAL", None)
                else:
                    os.environ["REELS_ENGINE_LOCAL"] = old
            self.assertTrue(self._install_cmd("ffmpeg", local).startswith(
                "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh ffmpeg"))
            self.assertTrue(self._install_cmd("python3", local).startswith(
                "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh python3"))
            self.assertEqual(self._install_cmd("node", local), "brew install node", "only the remembered tools")

    def test_28_tools_in_local_bin_count_as_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            for t in ("ffmpeg", "ffprobe", "uv"):
                write_exec(os.path.join(home, ".local", "bin", t), "#!/bin/sh\nexit 0\n")
            env = dict(os.environ, HOME=home, PATH=SYS_PATH, REELS_ENGINE_LOCAL=tmp)
            r = subprocess.run(["bash", os.path.join(ROOT, "check-setup.sh")], cwd=ROOT, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
            for label in ("the clip reader (ffprobe", "the video engine (ffmpeg)", "the transcriber helper (uv)"):
                row = [ln for ln in r.stdout.splitlines() if label in ln]
                self.assertTrue(row and "✓" in row[0], (label, r.stdout[-2500:]))


class Row30TimeLimits(unittest.TestCase):

    def _post_update(self):
        spec = importlib.util.spec_from_file_location("post_update_t", os.path.join(ROOT, "scripts", "post-update.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @unittest.skipUnless(POSIX, "the stand-in npx is a shell script")
    def test_30_browser_ensure_that_hangs_is_stopped_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = os.path.join(tmp, "eng")
            os.makedirs(os.path.join(eng, "product"))
            shutil.copy(os.path.join(ROOT, "product", "fallbacks.py"), os.path.join(eng, "product", "fallbacks.py"))
            with open(os.path.join(eng, "product.json"), "w", encoding="utf-8") as fh:
                json.dump({"hyperframes": "0.8.43"}, fh)
            fake = os.path.join(tmp, "bin")
            child_pid = os.path.join(tmp, "child.pid")
            # npx starts the real download as a child of its own, then waits on it: both must go.
            write_exec(os.path.join(fake, "npx"), f"#!/bin/sh\nsleep 60 &\necho $! > '{child_pid}'\nwait\n")
            mod = self._post_update()
            mod.ROOT = eng
            mod.BROWSER_ENSURE_TIMEOUT = 2
            old_path, old_local = os.environ["PATH"], os.environ.get("REELS_ENGINE_LOCAL")
            os.environ["PATH"] = fake + os.pathsep + old_path
            os.environ.pop("REELS_ENGINE_SKIP_BROWSER_ENSURE", None)
            os.environ["REELS_ENGINE_LOCAL"] = os.path.join(eng, "_local")
            out = io.StringIO()
            t0 = time.monotonic()
            try:
                with contextlib.redirect_stdout(out):
                    mod.ensure_render_browser()
            finally:
                os.environ["PATH"] = old_path
                if old_local is None:
                    os.environ.pop("REELS_ENGINE_LOCAL", None)
                else:
                    os.environ["REELS_ENGINE_LOCAL"] = old_local
            self.assertLess(time.monotonic() - t0, 30)
            self.assertIn("fetched on the first render", out.getvalue())
            self.assertFalse(os.path.exists(os.path.join(eng, "_local", "hf-browser-0.8.43.ok")))
            log = lines(os.path.join(eng, "_local", "fallbacks.log"))
            self.assertTrue(any("post-update: the render browser download" in ln for ln in log), log)
            time.sleep(0.5)
            pid = int(read(child_pid).strip())
            alive = subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0
            self.assertFalse(alive, "the download npx started was stopped with it")

    def test_30_post_update_default_limit_is_set(self):
        self.assertEqual(self._post_update().BROWSER_ENSURE_TIMEOUT,
                         int(os.environ.get("REELS_ENGINE_BROWSER_ENSURE_TIMEOUT") or 900))

    @unittest.skipUnless(POSIX, "simulates Git Bash with stand-ins")
    def test_30_check_setup_defender_question_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "bin")
            write_exec(os.path.join(fake, "uname"), "#!/bin/sh\ncase \"$1\" in -m) echo x86_64 ;; *) echo MINGW64_NT-10.0 ;; esac\n")
            write_exec(os.path.join(fake, "powershell.exe"), "#!/bin/sh\nsleep 60\necho 1\n")
            # Windows' own timeout.exe is a pause, not GNU timeout: it must not be mistaken for one.
            write_exec(os.path.join(fake, "timeout"), "#!/bin/sh\necho 'ERROR: Invalid syntax.' >&2\nexit 1\n")
            env = dict(os.environ, HOME=os.path.join(tmp, "home"), PATH=fake + ":" + SYS_PATH,
                       REELS_ENGINE_PS_TIMEOUT="2", REELS_ENGINE_LOCAL=tmp)
            t0 = time.monotonic()
            r = subprocess.run(["bash", os.path.join(ROOT, "check-setup.sh")], cwd=ROOT, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=90)
            self.assertLess(time.monotonic() - t0, 45, "the Defender question no longer holds the checklist")
            self.assertIn("did not say whether Controlled Folder Access is on", r.stdout, r.stdout[-2000:])

    def test_30_set_me_up_calls_browser_ensure_optional_and_bounded(self):
        sk = read(SKILL)
        part = sk[sk.index("### 2. Bootstrap the render engine"):]
        part = part[:part.index("\n- ")]
        self.assertIn("It is optional and it never blocks setup", part)
        self.assertIn("600000", part)
        self.assertIn("download by itself on her first render", part)
        self.assertIn('python3 product/fallbacks.py note set-me-up', part)


if __name__ == "__main__":
    unittest.main(verbosity=2)
