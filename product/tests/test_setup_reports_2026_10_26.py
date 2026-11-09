#!/usr/bin/env python3
"""Setup and first-run problem reports (sweep of 2026-10-26), each guarded where it went wrong.

1. WINDOWS ARM64: the speech tools could never install. The Intel-Mac onnxruntime cap leaked off the Mac (no
   sw_vers read as macOS 10, so 'onnxruntime<=1.16.3', which has no Windows ARM64 wheel), and the venv was built on
   an ARM Python the native wheels do not exist for. Now the caps are a Mac's only and a Windows ARM PC builds
   on uv's x64 Python 3.11.
2. LOOKS FAILED ON "No module named 'PIL'": the editor ran on Apple's /usr/bin/python3 (no Pillow). The look
   builder now runs on a Python that has Pillow, the editor's server moves onto one, the Mac shim prefers one,
   and with none anywhere the raw error becomes a plain sentence.
3. check-setup said transcription and the brand kit were "not installed" after both were set up.
4. A variable font file (Caveat-VF.ttf), bundled by the engine and added in CapCut, read "not installed yet".
5. The Intel (faster-whisper) first run quoted torch and ~3 GB + ~3 GB; it installs a few hundred MB.
6. The render browser was marked ready on the download alone, before it had ever started.
7. ISS-77: a check whose page would not load stopped the reel before the render's software-drawing and
   localhost-wrapper retries could run. The check now takes the same ladder and remembers what loads.

Run: python3 -m pytest product/tests/test_setup_reports_2026_10_26.py -q
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PRODUCT = os.path.join(ROOT, "product")
sys.path.insert(0, PRODUCT)
WT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
MACARCH = os.path.join(ROOT, "scripts", "_mac-arch.sh")
SHIM = os.path.join(ROOT, "scripts", "_python3-shim.sh")
CHECK_SETUP = os.path.join(ROOT, "check-setup.sh")
POSIX = os.name != "nt" and shutil.which("bash") is not None


def write_exec(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def pieces(path, *names):
    """Each `name() {...}` function or `NAME=` line, exactly as written in the shell file."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for name in names:
        if name.endswith("()"):
            i = src.index("\n" + name + " {") + 1
            out.append(src[i:src.index("\n}\n", i) + 3])
        else:
            i = src.index("\n" + name) + 1
            out.append(src[i:src.index("\n", i) + 1])
    return "\n".join(out)


def bash(script, env=None, cwd=None):
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, cwd=cwd, timeout=60)
    return r.returncode, r.stdout, r.stderr


# ── 1. Windows ARM64 ────────────────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(POSIX, "needs bash")
class WindowsArmSpeechTools(unittest.TestCase):
    def pins(self, kernel, macos=None):
        stubs = f'uname() {{ case "$1" in -m) echo x86_64;; *) echo {kernel};; esac; }}\n'
        stubs += (f"sw_vers() {{ echo {macos}; }}\n" if macos else "sw_vers() { return 127; }\n")
        stubs += "mac_sysctl() { return 1; }\n"
        rc, out, err = bash(stubs + f". '{MACARCH}'\n" + 'echo "[$(mac_intel_onnx_pin)][$(mac_intel_extra_pins)]"')
        self.assertEqual(rc, 0, err)
        return out.strip()

    def test_her_report_no_mac_pin_off_a_mac(self):
        self.assertEqual(self.pins("MINGW64_NT-10.0-26100"), "[][]")
        self.assertEqual(self.pins("Linux"), "[][]")

    def test_an_intel_mac_keeps_its_measured_bands(self):
        self.assertEqual(self.pins("Darwin", "10.15.7"), "[onnxruntime<=1.16.3][ctranslate2<=4.6.0 av<=13.1.0]")
        self.assertEqual(self.pins("Darwin", "12.7"), "[onnxruntime<=1.19.2][]")
        self.assertEqual(self.pins("Darwin", "13.7.8"), "[onnxruntime<=1.23.2][]")

    def test_the_faster_whisper_install_on_windows_carries_no_onnxruntime_cap(self):
        log = tempfile.mktemp()
        stubs = f'''
GPU_CUDA=0; NOFW=1; WINDOWS_SHELL=1; SAC_PINS=""; VENV=/v
uname() {{ echo MINGW64_NT-10.0; }}
sw_vers() {{ return 127; }}
mac_sysctl() {{ return 1; }}
. '{MACARCH}'
venv_py() {{ echo py; }}
uv() {{ echo "uv $*" >> '{log}'; }}
'''
        body = pieces(WT, "CT2_WIN_CPU_PIN=", "CT2_WIN_CPU_TRY=", "ct2_pin()", "install_listener()")
        rc, _, err = bash(stubs + body + "install_listener\n")
        try:
            calls = open(log, encoding="utf-8").read().splitlines()
        finally:
            if os.path.exists(log):
                os.remove(log)
        self.assertEqual(rc, 0, err)
        self.assertEqual(calls, ["uv pip install --python py faster-whisper ctranslate2==4.4.0 setuptools<81"])
        self.assertNotIn("onnxruntime", err)

    def uv_python(self, arch_env, reg_says=""):
        """The Python make_venv asks uv for, on a Git Bash with these PROCESSOR_* values and this registry answer."""
        tmp = tempfile.mkdtemp()
        try:
            fake = os.path.join(tmp, "bin")
            write_exec(os.path.join(fake, "reg"), f"#!/bin/sh\necho '    PROCESSOR_ARCHITECTURE    REG_SZ    {reg_says}'\n")
            log = os.path.join(tmp, "uv.log")
            stubs = f'''
PATH="{fake}:$PATH"
uname() {{ echo MINGW64_NT-10.0; }}
unset PROCESSOR_ARCHITEW6432 PROCESSOR_ARCHITECTURE
{arch_env}
WINDOWS_SHELL=1; SAC_PY=""; NO_UV=0; WORK="{tmp}"; VENV="{tmp}/venv"
ensure_uv() {{ :; }}
uv() {{ echo "uv $*" >> '{log}'; [ "$1" = venv ] && mkdir -p "$2"; return 0; }}
'''
            body = pieces(WT, "win_is_arm64()", 'UV_PY="3.11"', "if win_is_arm64; then", "make_venv()")
            rc, _, err = bash(stubs + body + "make_venv\n")
            self.assertEqual(rc, 0, err)
            return open(log, encoding="utf-8").read().splitlines()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_snapdragon_pc_builds_on_the_x64_python(self):
        x64 = "cpython-3.11-windows-x86_64-none"
        for env in ("export PROCESSOR_ARCHITECTURE=ARM64", "export PROCESSOR_ARCHITECTURE=AMD64"):
            calls = self.uv_python(env, reg_says="ARM64")    # an x64 Git Bash under emulation says AMD64 itself
            self.assertIn(f"uv python install {x64}", calls, env)
            self.assertTrue(any(c.startswith("uv venv ") and c.endswith(f"--python {x64}") for c in calls), calls)

    def test_an_ordinary_pc_is_unchanged(self):
        calls = self.uv_python("export PROCESSOR_ARCHITECTURE=AMD64", reg_says="AMD64")
        self.assertIn("uv python install 3.11", calls)
        self.assertTrue(any(c.startswith("uv venv ") and c.endswith("--python 3.11") for c in calls), calls)


# ── 2. Pillow ───────────────────────────────────────────────────────────────────────────────────────────
def _fake_python(path, real, has_pil=True, record=None):
    """A python3 stand-in: runs the real interpreter, says no to `import PIL` when has_pil is False, and notes
    every script it runs in `record`."""
    rec = f'[ -n "$1" ] && [ "$1" != -c ] && echo "$1" >> \'{record}\'\n' if record else ""
    nopil = "" if has_pil else 'case "$2" in *"import PIL"*) exit 1;; esac\n'
    write_exec(path, f"#!/bin/sh\n{nopil}{rec}exec '{real}' \"$@\"\n")


class PillowPython(unittest.TestCase):
    def setUp(self):
        import graphics_python
        self.gp = graphics_python
        self.gp.find_other.cache_clear()
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")

    def tearDown(self):
        self.gp.find_other.cache_clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_python_without_pillow_draws_with_the_one_setup_installed(self):
        good = os.path.join(self.home, ".local", "bin", "python3")
        _fake_python(good, sys.executable)
        with mock.patch.dict(os.environ, {"HOME": self.home, "_P3_SYS_ROOT": os.path.join(self.tmp, "none")}), \
             mock.patch.object(self.gp, "here_has_pil", return_value=False):
            self.assertEqual(self.gp.python(), good)

    def test_one_with_pillow_is_kept_and_none_anywhere_keeps_this_one(self):
        self.assertEqual(self.gp.python(), sys.executable)   # the test's own Python has Pillow
        with mock.patch.dict(os.environ, {"HOME": self.home, "_P3_SYS_ROOT": os.path.join(self.tmp, "none")}), \
             mock.patch.object(self.gp, "here_has_pil", return_value=False):
            self.assertEqual(self.gp.python(), sys.executable)

    @unittest.skipUnless(POSIX and shutil.which("ffmpeg"), "draws a real look")
    def test_her_report_the_lookbook_draws_on_a_python_with_pillow(self):
        import lookbook
        good = os.path.join(self.home, ".local", "bin", "python3")
        record = os.path.join(self.tmp, "ran.txt")
        _fake_python(good, sys.executable, record=record)
        out = os.path.join(self.tmp, "look", "takeover")
        with mock.patch.dict(os.environ, {"HOME": self.home, "_P3_SYS_ROOT": os.path.join(self.tmp, "none")}), \
             mock.patch.object(lookbook.graphics_python, "here_has_pil", return_value=False):
            lookbook.draw("takeover", out, "this is the hook line", 2.0, "Butter")
        self.assertTrue(os.path.isfile(os.path.join(out, "hf-reel-type-butter", "index.html")))
        self.assertIn(lookbook.BUILDER, open(record, encoding="utf-8").read())

    @unittest.skipUnless(POSIX, "needs a shell builder stand-in")
    def test_no_pillow_anywhere_is_said_plainly(self):
        import lookbook
        builder = os.path.join(self.tmp, "builder.py")
        with open(builder, "w", encoding="utf-8") as f:
            f.write("raise ModuleNotFoundError(\"No module named 'PIL'\")\n")
        with mock.patch.object(lookbook, "BUILDER", builder):
            with self.assertRaises(lookbook.Refuse) as cm:
                lookbook.draw("takeover", os.path.join(self.tmp, "look2"), "this is the hook line", 2.0, "Butter")
        self.assertEqual(str(cm.exception), self.gp.NO_PIL_MESSAGE)

    @unittest.skipUnless(POSIX, "re-exec is POSIX")
    def test_the_editor_server_moves_onto_a_python_with_pillow(self):
        good = os.path.join(self.home, ".local", "bin", "python3")
        record = os.path.join(self.tmp, "ran.txt")
        _fake_python(good, sys.executable, record=record)
        nopil = os.path.join(self.tmp, "apple", "python3")
        _fake_python(nopil, sys.executable, has_pil=False)
        probe = os.path.join(self.tmp, "probe.py")
        with open(probe, "w", encoding="utf-8") as f:
            f.write(f"import sys; sys.path.insert(0, {PRODUCT!r})\nimport graphics_python\n"
                    "graphics_python.here_has_pil = lambda: __import__('os').environ.get('REELS_ENGINE_GRAPHICS_REEXEC') == '1'\n"
                    "graphics_python.reexec_if_needed()\nprint('ran on', sys.argv[0])\n")
        env = dict(os.environ, HOME=self.home, _P3_SYS_ROOT=os.path.join(self.tmp, "none"))
        env.pop("REELS_ENGINE_GRAPHICS_REEXEC", None)
        r = subprocess.run([nopil, probe], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(probe, open(record, encoding="utf-8").read(), "it re-ran itself on the Python with Pillow")
        src = open(os.path.join(PRODUCT, "visual_editor_server.py"), encoding="utf-8").read()
        main = src[src.index('if __name__ == "__main__":'):]
        self.assertLess(main.index("reexec_if_needed()"), main.index("main()"))

    @unittest.skipUnless(POSIX, "simulates a Mac")
    def test_the_mac_shim_prefers_a_python_with_pillow_over_apples(self):
        good = os.path.join(self.home, ".local", "bin", "python3")
        _fake_python(good, sys.executable)
        fake = os.path.join(self.tmp, "bin")
        apple = os.path.join(fake, "python3")                 # stands in for /usr/bin/python3, first on PATH
        _fake_python(apple, sys.executable, has_pil=False)
        dev = os.path.join(self.tmp, "dev")
        write_exec(os.path.join(dev, "usr", "bin", "python3"), "#!/bin/sh\nexit 0\n")
        write_exec(os.path.join(fake, "xcode-select"), f"#!/bin/sh\necho '{dev}'\n")
        write_exec(os.path.join(fake, "uname"), "#!/bin/sh\necho Darwin\n")
        env = dict(os.environ, HOME=self.home, PATH=f"{fake}:/usr/bin:/bin", _P3_APPLE_PY=apple,
                   _P3_SYS_ROOT=os.path.join(self.tmp, "none"))
        rc, out, err = bash(f". '{SHIM}'; python3 -c 'import PIL; print(\"pil ok\")'; echo \"real=$_P3_REAL\"", env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn("pil ok", out)
        self.assertIn(f"real={good}", out)


# ── 3. check-setup's "On first use" ─────────────────────────────────────────────────────────────────────
@unittest.skipUnless(POSIX, "needs bash")
class CheckSetupFirstUse(unittest.TestCase):
    def ask(self, home, repo, fn):
        body = pieces(CHECK_SETUP, "speech_tools_done()", "speech_model_here()", "brand_kit_done()")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HF_", "REELS_ENGINE_"))}
        env["HOME"] = home
        rc, _, _ = bash(f'REPO="{repo}"\n' + body + f"{fn}\n", env=env)
        return rc == 0

    def test_her_report_set_up_reads_as_set_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, repo = os.path.join(tmp, "home"), os.path.join(tmp, "repo")
            venv = os.path.join(home, ".cache", "reels-editing-engine", "fasterwhisper-venv")
            os.makedirs(venv)
            os.makedirs(os.path.join(home, ".cache", "huggingface", "hub", "models--Systran--faster-whisper-small"))
            os.makedirs(repo)
            with open(os.path.join(repo, "brand-kit.md"), "w", encoding="utf-8") as f:
                f.write("# Brand kit\nName: Jane\nHow to use: write {{this}} where a field goes\n")
            self.assertFalse(self.ask(home, repo, "speech_tools_done"), "no record yet: a half build is not done")
            with open(os.path.join(venv, ".speech-tools-ready"), "w", encoding="utf-8") as f:
                f.write("cpu\n")
            self.assertTrue(self.ask(home, repo, "speech_tools_done"))
            self.assertTrue(self.ask(home, repo, "speech_model_here"))
            self.assertTrue(self.ask(home, repo, "brand_kit_done"))

    def test_a_new_machine_still_reads_as_to_come(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, repo = os.path.join(tmp, "home"), os.path.join(tmp, "repo")
            os.makedirs(home)
            os.makedirs(repo)
            with open(os.path.join(repo, "brand-kit.md"), "w", encoding="utf-8") as f:
                f.write("Name: {{your name}}\nHandle: <<handle>>\n")
            self.assertFalse(self.ask(home, repo, "speech_tools_done"))
            self.assertFalse(self.ask(home, repo, "speech_model_here"))
            self.assertFalse(self.ask(home, repo, "brand_kit_done"))
            os.remove(os.path.join(repo, "brand-kit.md"))
            self.assertFalse(self.ask(home, repo, "brand_kit_done"))

    def test_the_section_no_longer_calls_everything_not_installed(self):
        src = open(CHECK_SETUP, encoding="utf-8").read()
        self.assertNotIn('"not installed here; each happens once"', src)
        self.assertRegex(src, r"if speech_tools_done; then")
        self.assertRegex(src, r"if brand_kit_done; then")


# ── 4. variable font files ──────────────────────────────────────────────────────────────────────────────
class VariableFontFiles(unittest.TestCase):
    def setUp(self):
        import capcut_userfonts as cf
        self.cf = cf
        self.tmp = tempfile.mkdtemp()
        cf._family_cache.clear()
        self.patches = [mock.patch.object(cf, "_USERFD", os.path.join(self.tmp, "none", "userFontData")),
                        mock.patch.object(cf, "_CATALOG", os.path.join(self.tmp, "none")),
                        mock.patch.object(cf, "_OVERRIDES", os.path.join(self.tmp, "none.json")),
                        mock.patch.object(cf, "_LIBFON", os.path.join(self.tmp, "Fonts")),
                        mock.patch.object(cf, "_catalog_cache", {})]
        for p in self.patches:
            p.start()
        os.makedirs(os.path.join(self.tmp, "Fonts"))
        self.caveat = os.path.join(ROOT, "assets", "fonts", "Caveat-VF.ttf")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.cf._family_cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_her_report_caveat_vf_in_capcuts_folder_is_found(self):
        dst = os.path.join(self.tmp, "Fonts", "Caveat-VF.ttf")
        shutil.copy(self.caveat, dst)
        self.assertEqual(self.cf.resolve_font_file("Caveat"), dst)

    def test_a_bracketed_variable_file_and_an_oddly_named_one_are_found(self):
        dst = os.path.join(self.tmp, "Fonts", "Caveat[wght].ttf")
        shutil.copy(self.caveat, dst)
        self.assertEqual(self.cf.resolve_font_file("Caveat"), dst)
        os.remove(dst)
        self.cf._family_cache.clear()
        odd = os.path.join(self.tmp, "Fonts", "handwriting-from-google.ttf")
        shutil.copy(self.caveat, odd)
        if self.cf.ImageFont is not None:                     # matched on its own name table
            self.assertEqual(self.cf.resolve_font_file("Caveat"), odd)

    def test_frame_to_pack_names_the_bundled_file(self):
        import frame_to_pack
        self.assertEqual(frame_to_pack.resolve_font("Caveat"), "Caveat-VF.ttf")
        self.assertEqual(frame_to_pack.resolve_font("Not A Real Family"), "")
        import stylepack
        self.assertTrue(os.path.isfile(stylepack._abs(frame_to_pack.resolve_font("Caveat"))))


# ── 5. the faster-whisper first-run message ─────────────────────────────────────────────────────────────
@unittest.skipUnless(POSIX, "needs bash")
class FasterWhisperFirstRun(unittest.TestCase):
    def first_run(self, nofw):
        stubs = f'''
NOFW={nofw}; GPU_CUDA=0; VENV=/tmp/never; WORK=/tmp
has_verified_record() {{ return 1; }}
use_signed_python_if_blocked() {{ :; }}
make_venv() {{ return 0; }}
install_listener() {{ return 0; }}
mark_ready() {{ :; }}
note_fallback() {{ :; }}
PYBIN=true
'''
        body = pieces(WT, "announce_download()", "build_if_unfinished()")
        rc, _, err = bash(stubs + body + "build_if_unfinished\n")
        self.assertEqual(rc, 0, err)
        return err

    def test_her_report_the_intel_route_quotes_its_own_download(self):
        err = self.first_run(1)
        self.assertNotIn("bring torch", err)
        self.assertNotIn("~3 GB", err)
        self.assertIn("faster-whisper", err)
        self.assertIn("~300 MB", err)
        self.assertIn("~0.5 GB", err)

    def test_the_whisperx_route_still_says_its_size(self):
        err = self.first_run(0)
        self.assertIn("bring torch", err)
        self.assertIn("~3 GB", err)


# ── 6. the render browser's ready mark ──────────────────────────────────────────────────────────────────
@unittest.skipUnless(POSIX, "the stand-in npx and browser are shell scripts")
class RenderBrowserReadyMark(unittest.TestCase):
    def ensure(self, browser_body):
        tmp = tempfile.mkdtemp()
        try:
            eng = os.path.join(tmp, "eng")
            os.makedirs(os.path.join(eng, "product"))
            for f in ("fallbacks.py", "render_browser.py"):
                shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
            with open(os.path.join(eng, "product.json"), "w", encoding="utf-8") as fh:
                json.dump({"hyperframes": "0.8.181"}, fh)
            fake = os.path.join(tmp, "bin")
            write_exec(os.path.join(fake, "npx"), "#!/bin/sh\necho 'Browser found. Ready to render.'\nexit 0\n")
            home = os.path.join(tmp, "home")
            if browser_body is not None:
                write_exec(os.path.join(home, ".cache", "hyperframes", "chrome", "chrome-headless-shell", "mac-1",
                                        "chrome-headless-shell-mac-x64", "chrome-headless-shell"), browser_body)
            spec = importlib.util.spec_from_file_location("post_update_t26", os.path.join(ROOT, "scripts", "post-update.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.ROOT = eng
            sys.modules.pop("render_browser", None)
            out = io.StringIO()
            env = {"PATH": fake + os.pathsep + os.environ["PATH"], "HOME": home,
                   "REELS_ENGINE_LOCAL": os.path.join(eng, "_local")}
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
                os.environ.pop("REELS_ENGINE_SKIP_BROWSER_ENSURE", None)
                import render_browser
                with mock.patch.object(render_browser, "LAUNCH_TIMEOUTS", (3, 3)):
                    mod.ensure_render_browser()
            sys.modules.pop("render_browser", None)
            return os.path.exists(os.path.join(eng, "_local", "hf-browser-0.8.181.ok")), out.getvalue()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_browser_that_starts_is_marked_ready(self):
        marked, out = self.ensure("#!/bin/sh\necho 'Google Chrome for Testing 152.0.7977.30'\n")
        self.assertTrue(marked, out)
        self.assertIn("render engine: ready.", out)

    def test_her_report_a_browser_that_does_not_start_is_not_marked(self):
        marked, out = self.ensure("#!/bin/sh\nsleep 30\n")
        self.assertFalse(marked, out)
        self.assertIn("would not start yet", out)
        marked, out = self.ensure("#!/bin/sh\necho 'dyld: Symbol not found' >&2\nexit 134\n")
        self.assertFalse(marked, out)
        self.assertIn("exit 134", out)

    def test_a_browser_that_cannot_be_found_is_not_called_ready(self):
        marked, out = self.ensure(None)
        self.assertFalse(marked, out)
        self.assertNotIn("render engine: ready.", out)

    def test_set_me_up_marks_it_the_same_way(self):
        skill = open(os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md"), encoding="utf-8").read()
        self.assertNotIn("echo ok > _local/hf-browser-", skill)
        self.assertIn("product/render_browser.py --mark-ready", skill)


# ── 7. ISS-77: the check gets the render's ladder ───────────────────────────────────────────────────────
NAV_FAIL = "Error: Navigation timeout of 120000 ms exceeded\n"
PASSED = "◇  Check passed\n"


class CheckLadder(unittest.TestCase):
    def setUp(self):
        import npx_run
        self.nr = npx_run
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"REELS_ENGINE_LOCAL": self.tmp})
        self.env.start()
        for k in ("PRODUCER_BROWSER_GPU_MODE", "HYPERFRAMES_BROWSER_PATH", "PRODUCER_HEADLESS_SHELL_PATH",
                  "PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS", "REELS_ENGINE_HF_NAV_TIMEOUT_MS"):
            os.environ.pop(k, None)
        self.wrap = os.path.join(self.tmp, "chrome-localhost-wrapper.sh")

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, loads_when):
        calls = []

        def once(argv, env, timeout):
            calls.append({k: env.get(k) for k in ("PRODUCER_BROWSER_GPU_MODE", "HYPERFRAMES_BROWSER_PATH",
                                                   "PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS")})
            return (0, PASSED, "") if loads_when(env) else (1, NAV_FAIL, "")
        with mock.patch.object(self.nr, "_run_once", once), \
             mock.patch.object(self.nr, "_localhost_wrapper", lambda: self.wrap), \
             contextlib.redirect_stderr(io.StringIO()):
            res = self.nr.run_hf_check(["npx", "hyperframes", "check"], echo=False)
        return res, calls

    def test_her_report_software_drawing_is_tried_on_the_check_and_remembered(self):
        import fallbacks
        res, calls = self.run_check(lambda env: env.get("PRODUCER_BROWSER_GPU_MODE") == "software")
        self.assertEqual(res.status, "ran")
        self.assertEqual(len(calls), 3, calls)              # default budget, longer budget, then software
        self.assertEqual(calls[-1]["PRODUCER_BROWSER_GPU_MODE"], "software")
        self.assertTrue(fallbacks.remembered("render.gpu-software"), "the render goes straight to it")
        self.assertTrue(fallbacks.remembered("check.gpu-software"))
        res, calls = self.run_check(lambda env: env.get("PRODUCER_BROWSER_GPU_MODE") == "software")
        self.assertEqual(len(calls), 1, "a later check starts with what loads here")

    def test_then_the_localhost_wrapper_in_the_drawing_it_had(self):
        import fallbacks
        res, calls = self.run_check(lambda env: env.get("HYPERFRAMES_BROWSER_PATH") == self.wrap)
        self.assertEqual(res.status, "ran")
        self.assertEqual([c["PRODUCER_BROWSER_GPU_MODE"] for c in calls], [None, None, "software", None])
        self.assertEqual(calls[-1]["HYPERFRAMES_BROWSER_PATH"], self.wrap)
        self.assertTrue(fallbacks.remembered("render.localhost-wrapper"))
        self.assertFalse(fallbacks.remembered("render.gpu-software"), "software did not help, so it is not kept")

    def test_nothing_loads_then_it_is_still_a_nav_stop_with_every_route_tried(self):
        res, calls = self.run_check(lambda env: False)
        self.assertEqual(res.status, "nav")
        self.assertEqual(len(calls), 4)
        self.assertTrue({"nav", "gpu-software", "localhost-wrapper"} <= res.tried)

    def test_the_gate_is_never_skipped(self):
        res, _ = self.run_check(lambda env: False)
        self.assertNotEqual(res.status, "ran")
        self.assertNotEqual(res.rc, 0)


if __name__ == "__main__":
    unittest.main()
