#!/usr/bin/env python3
"""test_hands_off_templates.py — the shipped Hands-Off frame templates pass the engine's own render gate.

product/creative-vault/hands-off/{editorial,butter,playful}/index.html are the proven, renderable source the
Hands-Off lane builds from, so each one has to clear product/reel_gate.py (HyperFrames' own `check`) exactly as a
buyer's render would. Editorial used to fail it on text contrast, and butter and playful passed with contrast
misses still listed. What must hold:
  1. reel_gate exits 0 on a copy of every template (never run in place: `check` writes .hyperframes/ there).
  2. HyperFrames' contrast section lists no misses (no ✗ line) for any of them.
  3. Every timed clip carries an id (a stable edit target), and no template silences the check with
     data-layout-allow-* attributes.

The gate needs Node (npx runs the pinned HyperFrames); without it the gate tests skip cleanly.
Run: python3 product/tests/test_hands_off_templates.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HANDS_OFF = os.path.join(ROOT, "product", "creative-vault", "hands-off")
TEMPLATES = ("editorial", "butter", "playful")


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as fh:
        return fh.read()


class TemplateSource(unittest.TestCase):
    def test_every_clip_has_an_id_and_nothing_is_silenced(self):
        for name in TEMPLATES:
            html = read(HANDS_OFF, name, "index.html")
            clips = re.findall(r'<div class="clip"[^>]*>', html)
            self.assertEqual(len(clips), 4, name)
            for tag in clips:
                self.assertRegex(tag, r'\bid="[a-z0-9-]+"', f"{name}: {tag}")
            self.assertNotIn("data-layout-allow", html, name)


@unittest.skipUnless(shutil.which("node") and shutil.which("npx"), "needs node and npx")
class TemplatesPassTheGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="hands-off-gate-")
        # Anything the engine notes per machine goes to a throwaway folder, never the real _local/.
        cls.env = dict(os.environ, REELS_ENGINE_LOCAL=os.path.join(cls.tmp, "_local"),
                       HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _gate(self, name):
        copy = os.path.join(self.tmp, name)
        shutil.copytree(os.path.join(HANDS_OFF, name), copy,
                        ignore=shutil.ignore_patterns(".hyperframes", "node_modules"))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "product", "reel_gate.py"), copy],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=self.env, timeout=900)
        return r.returncode, r.stdout + r.stderr

    def test_each_template_passes(self):
        # One render-side check at a time (the engine never runs HyperFrames concurrently).
        for name in TEMPLATES:
            with self.subTest(template=name):
                code, out = self._gate(name)
                self.assertEqual(code, 0, f"{name} failed the gate:\n{out[-4000:]}")
                contrast = out.split("Contrast", 1)[-1].split("Snapshots", 1)[0]
                self.assertNotIn("✗", contrast, f"{name} still has contrast misses:\n{contrast}")


if __name__ == "__main__":
    unittest.main()
