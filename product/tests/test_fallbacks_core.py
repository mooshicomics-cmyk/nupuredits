#!/usr/bin/env python3
"""test_fallbacks_core.py — the shared half of every backup route (product/fallbacks.py, scripts/_fallbacks.sh).

Every step that pivots to a working route writes the same one-line record and the same per-computer memory, and
the problem report attaches both. These lock down the contract the steps lean on:
  * a note is one line in the word-timings.sh format, and never raises, even when _local cannot be written
  * a remembered pivot survives a new process, and a damaged pivots.json reads as "nothing learned yet"
  * the shell helper writes the same log line with no Python at all, and reads/writes the same pivots
  * collect-report.sh attaches both records

Run: python3 product/tests/test_fallbacks_core.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import fallbacks  # noqa: E402

LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\dZ  [\w.-]+: .+$")


class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.local = os.path.join(self.tmp, "_local")
        os.environ["REELS_ENGINE_LOCAL"] = self.local

    def tearDown(self):
        os.environ.pop("REELS_ENGINE_LOCAL", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_note_is_one_line_in_the_shared_format(self):
        fallbacks.note("verify-cut", "first venv would not load\nfaster-whisper; used the other one")
        lines = open(fallbacks.log_path(), encoding="utf-8").read().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], LINE)
        self.assertIn("verify-cut: first venv would not load faster-whisper", lines[0])

    def test_note_never_raises(self):
        # _local is a FILE here, so the folder cannot be made: the note is dropped, her edit is not.
        open(self.local, "w", encoding="utf-8").close()
        fallbacks.note("x", "y")
        fallbacks.remember("k", 1)
        self.assertIsNone(fallbacks.remembered("k"))

    def test_remember_survives_a_new_process(self):
        fallbacks.remember("render.low-memory", True, why="render ran out of memory")
        out = subprocess.run([sys.executable, os.path.join(PRODUCT, "fallbacks.py"), "get", "render.low-memory"],
                             capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "True")
        fallbacks.forget("render.low-memory")
        self.assertIsNone(fallbacks.remembered("render.low-memory"))

    def test_damaged_pivots_read_as_nothing_learned(self):
        os.makedirs(self.local)
        with open(fallbacks.pivots_path(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertIsNone(fallbacks.remembered("anything"))
        fallbacks.remember("a", "b")   # and writing over it repairs it
        self.assertEqual(fallbacks.remembered("a"), "b")

    def test_shell_helper_matches(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("no bash")
        script = (f'. "{ROOT}/scripts/_fallbacks.sh"; export REELS_ENGINE_ROOT="{ROOT}"; '
                  'note_fallback stitch "snap-to-sound did not finish; spliced the cuts as written"; '
                  'remember_pivot trim-restarts.unavailable 1 "torch would not load"; '
                  'remembered_pivot trim-restarts.unavailable')
        r = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.stdout.strip(), "1")
        line = open(fallbacks.log_path(), encoding="utf-8").read().splitlines()[-1]
        self.assertRegex(line, LINE)
        self.assertEqual(fallbacks.remembered("trim-restarts.unavailable"), "1")

    def test_shell_helper_without_root_is_harmless(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("no bash")
        env = {k: v for k, v in os.environ.items() if k not in ("REELS_ENGINE_LOCAL", "REELS_ENGINE_ROOT",
                                                                 "ENGINE_ROOT")}
        r = subprocess.run([bash, "-c", f'set -eu; . "{ROOT}/scripts/_fallbacks.sh"; note_fallback a b; '
                                        'remembered_pivot k || echo none'], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "none")

    def test_report_attaches_both(self):
        sh = open(os.path.join(ROOT, "scripts", "collect-report.sh"), encoding="utf-8").read()
        self.assertIn("_local/fallbacks.log", sh)
        self.assertIn("_local/pivots.json", sh)
        self.assertIn("fallbacks.py\" list", sh)


if __name__ == "__main__":
    unittest.main()
