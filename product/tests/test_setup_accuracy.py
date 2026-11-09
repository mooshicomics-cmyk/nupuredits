#!/usr/bin/env python3
"""test_setup_accuracy.py: what setup tells a buyer matches what the engine really needs and does.

  1. uv stays a real requirement in check-setup.sh. The rough cut can fetch uv for itself, but only while
     it builds the speech tools; the measuring tools every route runs (workflows/subject-zones.py and the
     other PEP 723 scripts) go through `uv run`, and nothing fetches uv for those. Its row says so, and no
     longer advertises uvx, which nothing needs without a fallback.
  2. Windows installs that can go in for her account only do (--scope user), so winget asks for no
     administrator Yes: Python and Git. Node stays machine-wide (its only per-user package is a bare zip
     that names node alone, not npx). ffmpeg and uv are portable packages winget already keeps per user.
     The three first-run flags stay on every line.
  3. scripts/smoke-test.sh writes its failure report with the shell alone, so a computer whose Python is
     broken still gets one, with her home folder taken out of every path.
  4. Nothing installs from product/engine/VectCutAPI/requirements-lock.txt.

Run: python3 product/tests/test_setup_accuracy.py   (non-zero on failure)
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POSIX = os.name != "nt" and shutil.which("bash") is not None
SYS_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
FIRST_RUN_FLAGS = "--accept-source-agreements --accept-package-agreements --disable-interactivity"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, body, executable=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    if executable:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def check_setup_fn_script(names):
    """The named functions from check-setup.sh, cut out so they can run on their own."""
    cs = read(os.path.join(ROOT, "check-setup.sh"))
    out = ""
    for name in names:
        start = cs.index("\n" + name) + 1
        out += cs[start:cs.index("\n}\n", start) + 3]
    return out


@unittest.skipUnless(POSIX, "runs check-setup.sh's own functions in bash")
class WindowsInstallLines(unittest.TestCase):
    def _win_line(self, key):
        cs = read(os.path.join(ROOT, "check-setup.sh"))
        flags = re.search(r'^WINGET_FLAGS="[^"]*"$', cs, re.M).group(0)
        fns = re.search(r"^winget_line\(\).*$", cs, re.M).group(0)
        script = (f"engine_dir() {{ echo '{ROOT}'; }}\nOS=win\nMACROUTE=\n{flags}\n{fns}\n"
                  + check_setup_fn_script(["direct_remembered() {", "install_cmd() {"]) + f"install_cmd {key}\n")
        with tempfile.TemporaryDirectory() as local:
            env = dict(os.environ, REELS_ENGINE_LOCAL=local)
            return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True,
                                  encoding="utf-8").stdout.strip()

    def test_python_installs_for_her_account_only(self):
        line = self._win_line("python3")
        self.assertTrue(line.startswith("winget install -e " + FIRST_RUN_FLAGS), line)
        self.assertIn("--id Python.Python.3.12", line)
        self.assertTrue(line.endswith("--scope user"), line)

    def test_the_other_lines_keep_their_flags_and_add_no_scope(self):
        for key, pkg in (("ffmpeg", "Gyan.FFmpeg"), ("uv", "astral-sh.uv"), ("node", "OpenJS.NodeJS.LTS")):
            line = self._win_line(key)
            self.assertEqual(line, f"winget install -e {FIRST_RUN_FLAGS} --id {pkg}", key)


class SetMeUpLines(unittest.TestCase):
    def setUp(self):
        self.skill = read(os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md"))
        self.winget = [ln for ln in self.skill.splitlines() if "winget install" in ln]

    def test_python_line_is_per_user_with_every_flag(self):
        py = [ln for ln in self.winget if "Python.Python.3.12" in ln]
        self.assertTrue(py)
        for ln in py:
            self.assertIn(FIRST_RUN_FLAGS, ln)
            self.assertIn("--scope user", ln)

    def test_every_git_line_is_per_user(self):
        git = [ln for ln in self.winget if "Git.Git" in ln]
        cs_git = [ln for ln in read(os.path.join(ROOT, "check-setup.sh")).splitlines() if "Git.Git" in ln]
        self.assertTrue(git and cs_git)
        for ln in git + cs_git:
            self.assertIn("--scope user", ln)

    def test_node_stays_machine_wide(self):
        node = [ln for ln in self.winget if "OpenJS.NodeJS.LTS" in ln]
        self.assertTrue(node)
        self.assertFalse(any("--scope" in ln for ln in node), node)


class UvRow(unittest.TestCase):
    def test_uv_is_still_needed_after_the_rough_cut(self):
        # The reason uv still counts: the placement measurement every route runs is a `uv run` script.
        zones = read(os.path.join(ROOT, "workflows", "subject-zones.py"))
        self.assertTrue(zones.startswith("# /// script"), "subject-zones.py is no longer a uv script; revisit")
        cs = read(os.path.join(ROOT, "check-setup.sh"))
        row = [ln for ln in cs.splitlines() if ln.startswith("need uv ")]
        self.assertEqual(len(row), 1)
        self.assertIn("measuring tools", row[0])
        self.assertNotIn("uvx", row[0])

    @unittest.skipUnless(POSIX, "runs check-setup.sh")
    def test_missing_uv_is_one_counted_row_with_its_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=os.path.join(tmp, "home"), PATH=SYS_PATH, REELS_ENGINE_LOCAL=tmp)
            r = subprocess.run(["bash", os.path.join(ROOT, "check-setup.sh")], cwd=ROOT, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=180)
            out = r.stdout.splitlines()
            rows = [i for i, ln in enumerate(out) if "the transcriber helper (uv)" in ln]
            self.assertTrue(rows, r.stdout[-2000:])
            if "✓" in out[rows[0]]:
                # The PATH shim also looks in Homebrew's folders, so a machine with uv there finds it.
                self.skipTest("this machine has uv where the PATH shim looks")
            self.assertIn("is not on this machine yet", out[rows[0]])
            self.assertIn("uv", out[rows[0] + 1])   # the install line, alone on the next line


@unittest.skipUnless(POSIX, "runs smoke-test.sh in bash")
class SmokeReportWithoutPython(unittest.TestCase):
    def test_verdict_runs_no_python(self):
        src = read(os.path.join(ROOT, "scripts", "smoke-test.sh"))
        verdict = src[src.index("# ── verdict"):]
        code = [ln for ln in verdict.splitlines() if not ln.lstrip().startswith("#")]
        calls = [ln for ln in code if re.search(r"(^|[\s;(&|])python3?\s", ln)]
        self.assertEqual(calls, [])

    def test_a_failed_run_writes_its_report_with_python_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = os.path.join(tmp, "eng")
            for rel in ("scripts/smoke-test.sh", "scripts/_python3-shim.sh", "scripts/_path-shim.sh"):
                os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
            # make-handoff.py is only read for the support address; anything that RUNS it fails loudly.
            write(os.path.join(eng, "product", "make-handoff.py"),
                  'SUPPORT_EMAIL = "support@example.test"\nraise SystemExit("make-handoff ran")\n')
            # A template pointing into her home folder: a counted failure, and a path the report must redact.
            home = "/Users/your-name"
            write(os.path.join(eng, "product", "creative-vault", "t.json"), f'{{"m": "{home}/clip.mov"}}\n')
            # Every Python on PATH refuses to run and leaves a trace.
            fake = os.path.join(tmp, "bin")
            trace = os.path.join(tmp, "python-ran")
            for name in ("python3", "python", "py"):
                write(os.path.join(fake, name), f'#!/bin/sh\necho "$0 $*" >> "{trace}"\nexit 1\n', True)
            env = {k: v for k, v in os.environ.items() if k not in ("USERPROFILE", "LOCALAPPDATA", "APPDATA")}
            env.update(HOME=home, PATH=fake + ":" + SYS_PATH, TMPDIR=tmp,
                       _P3_APPLE_PY=os.path.join(tmp, "no-apple-python"), _P3_SYS_ROOT=os.path.join(tmp, "nosys"))
            r = subprocess.run(["bash", os.path.join(eng, "scripts", "smoke-test.sh")], cwd=eng, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("make-handoff ran", r.stdout + r.stderr)
            reports = os.listdir(os.path.join(eng, "_handoff"))
            self.assertEqual(len(reports), 1, reports)
            self.assertTrue(re.match(r"HANDOFF-smoke-test-\d{8}-\d{6}\.md$", reports[0]), reports)
            body = read(os.path.join(eng, "_handoff", reports[0]))
            self.assertIn("## What failed", body)
            self.assertIn("capcut_font_doctor.py missing", body)
            self.assertIn("template path(s)", body)
            self.assertIn("## Machine", body)
            self.assertIn("~/clip.mov", body)
            self.assertNotIn(home, body)
            self.assertIn("support@example.test", r.stdout)
            self.assertIn(os.path.join("_handoff", reports[0]), r.stdout)


class VectCutLockFile(unittest.TestCase):
    def test_nothing_installs_from_the_lock_file(self):
        vc = os.path.join(ROOT, "product", "engine", "VectCutAPI")
        readers = [os.path.join(vc, f) for f in os.listdir(vc)
                   if f.endswith((".sh", ".command", ".bat", ".py", ".ps1"))]
        readers += [os.path.join(ROOT, f) for f in ("make-ship.sh", "check-ship.sh", "check-setup.sh")]
        readers += [os.path.join(ROOT, "scripts", f) for f in os.listdir(os.path.join(ROOT, "scripts"))
                    if f.endswith((".sh", ".py"))]
        hits = [p for p in readers if os.path.isfile(p) and "requirements-lock" in read(p)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
