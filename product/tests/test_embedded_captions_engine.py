#!/usr/bin/env python3
"""test_embedded_captions_engine.py — the embedded-captions skill runs inside the engine, under the engine's rules.

Upstream, the skill looks for a HyperFrames source checkout or a plugin install, so inside the engine it could not
start at all. And when it did render, it ran its two passes at the same time, never ran HyperFrames' own check
(which calls the skill's own <video> tag an error), built every project 1280x720 unless told otherwise, and sat
captions 96px from the bottom, under Instagram's caption and buttons. What must hold:
  1. hf-cli.cjs hands out product/hf_npx.cjs, which runs the version product.json pins.
  2. render-and-composite.sh runs the engine's gate before each pass and never runs two renders at once.
  3. The a-roll <video> carries data-start in every template (HyperFrames owns its playback; the check passes).
  4. No size named = the source video's shape (a 9:16 clip -> 1080x1920).
  5. On a portrait reel every bottom-measured caption clears product/safe_zones.py's bottom band and corner
     furniture clears its top band; a landscape project is placed exactly as upstream places it.
  6. prepare.sh installs the caption helpers when missing and never says ready without safe-zones.json.

Run: python3 product/tests/test_embedded_captions_engine.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SKILL = os.path.join(ROOT, ".claude", "skills", "embedded-captions")
SCRIPTS = os.path.join(SKILL, "scripts")
FIXTURE = os.path.join(SCRIPTS, "fixtures", "heroless")
sys.path.insert(0, os.path.join(ROOT, "product"))
import safe_zones  # noqa: E402


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as fh:
        return fh.read()


@unittest.skipUnless(shutil.which("node"), "needs node")
class Cli(unittest.TestCase):
    def test_hf_cli_hands_out_the_engine_bridge(self):
        r = subprocess.run(["node", os.path.join(SCRIPTS, "hf-cli.cjs")], capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if k != "HYPERFRAMES_ROOT"}, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(r.stdout.strip()), os.path.realpath(os.path.join(ROOT, "product", "hf_npx.cjs")))

    def test_bridge_runs_the_pinned_version(self):
        pin = json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8"))["hyperframes"]
        r = subprocess.run(["node", "-e", f'console.log(require({json.dumps(os.path.join(ROOT, "product", "hf_npx.cjs"))}).pin())'],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), pin)
        src = read(ROOT, "product", "hf_npx.cjs")
        for flag in ("HYPERFRAMES_NO_TELEMETRY", "DO_NOT_TRACK", "HYPERFRAMES_SKIP_SKILLS"):
            self.assertIn(flag, src)
        self.assertIn('"cmd", ["/c", "npx"', src)   # the Windows argv npx_run.npx_argv() uses


class Render(unittest.TestCase):
    def test_gate_before_every_pass_and_one_render_at_a_time(self):
        sh = read(SCRIPTS, "render-and-composite.sh")
        self.assertIsNone(re.search(r"hf_render_dir [^\n]*&\s*$", sh, re.M), "a render is started in the background")
        self.assertNotRegex(sh, r"wait \"\$(BG|FG|BASE|RAIL)_PID\"")
        self.assertEqual(sh.count('engine_gate "'), 5)   # bg + fg, base + rail, single
        self.assertIn("product/reel_gate.py", sh)
        for label in ("the background pass", "the foreground pass", "the base pass", "the rail pass", "the composition"):
            gate = sh.index(label)
            self.assertLess(gate, sh.index("hf_render_dir", gate), label)

    def test_a_roll_video_has_a_start_everywhere(self):
        for rel in (("scripts", "make-theme.cjs"), ("modes", "cinematic", "engine.html"),
                    ("modes", "cinematic", "cinematic-cream", "template.html")):
            src = read(SKILL, *rel)
            tag = re.search(r'<video[^>]*id="a-roll"[^>]*>|<video\s+id="a-roll"[\s\S]*?></video>', src)
            self.assertTrue(tag, rel)
            self.assertIn('data-start="0"', tag.group(0), rel)


@unittest.skipUnless(shutil.which("node") and shutil.which("ffmpeg"), "needs node and ffmpeg")
class Placement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def compile(self, **theme):
        p = os.path.join(self.tmp, "p")
        shutil.rmtree(p, ignore_errors=True)
        shutil.copytree(FIXTURE, p)
        t = json.load(open(os.path.join(p, "theme.json"), encoding="utf-8"))
        for k in ("width", "height"):
            t.pop(k, None)
        t.update(theme)
        json.dump(t, open(os.path.join(p, "theme.json"), "w", encoding="utf-8"))
        return p

    def run_theme(self, p):
        r = subprocess.run(["node", os.path.join(SCRIPTS, "make-theme.cjs"), p], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def rail_top(self, p):
        m = re.search(r"\.rail \{ position:absolute; left:[\d.]+px; top:([\d.]+)px", read(p, "rail.html"))
        return float(m.group(1))

    def test_portrait_rail_clears_the_bottom_band(self):
        p = self.compile(dna="anchor", width=1080, height=1920)
        self.run_theme(p)
        dna = json.load(open(os.path.join(SKILL, "themes", "anchor.json"), encoding="utf-8"))
        top = self.rail_top(p)
        self.assertLessEqual(top + dna["body"]["fontPx"] * 1.3, safe_zones.BOTTOM)
        self.assertEqual(top, safe_zones.BOTTOM - dna["body"]["bottomPx"])

    def test_landscape_is_placed_as_upstream(self):
        p = self.compile(dna="anchor", width=1280, height=720)
        self.run_theme(p)
        dna = json.load(open(os.path.join(SKILL, "themes", "anchor.json"), encoding="utf-8"))
        self.assertEqual(self.rail_top(p), 720 - dna["body"]["bottomPx"])

    def test_portrait_corner_furniture_clears_the_top_band(self):
        p = self.compile(dna="vhs", width=1080, height=1920)
        self.run_theme(p)
        rail = read(p, "rail.html")
        m = re.search(r"#osdplay \{ left:36px; top:(\d+)px", rail)
        self.assertGreaterEqual(int(m.group(1)), safe_zones.TOP)
        m = re.search(r"#osdts \{ right:36px; bottom:(\d+)px", rail)
        self.assertGreaterEqual(int(m.group(1)), 1920 - safe_zones.BOTTOM)

    def test_no_size_follows_the_source_video(self):
        p = self.compile(dna="anchor")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=180x320:d=1", "-y",
                        os.path.join(p, "source.mp4")], check=True, timeout=60)
        self.run_theme(p)
        self.assertRegex(read(p, "rail.html"), r'data-width="1080"\s+data-height="1920"')


class Prepare(unittest.TestCase):
    def test_helpers_installed_and_ready_only_with_safe_zones(self):
        sh = read(SCRIPTS, "prepare.sh")
        self.assertIn("sharp@0.35.3 puppeteer@25.8.0 gsap@3.15.0", sh)
        self.assertIn('if [[ ! -s "$PROJECT/safe-zones.json" ]]', sh)
        self.assertLess(sh.index('rm -f "$PROJECT/safe-zones.json"'), sh.index('node "$SD/safe-zones.cjs"'))


class Settings(unittest.TestCase):
    def test_init_never_installs_global_skills(self):
        env = json.loads(read(ROOT, ".claude", "settings.json"))["env"]
        self.assertEqual(env.get("HYPERFRAMES_SKIP_SKILLS"), "1")
        import settings_persist
        self.assertEqual(settings_persist.ENGINE_ENV.get("HYPERFRAMES_SKIP_SKILLS"), "1")


if __name__ == "__main__":
    unittest.main()
