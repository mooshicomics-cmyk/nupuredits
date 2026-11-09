#!/usr/bin/env python3
"""The wide frame (product/frame.py) is opt-in by a switch in _local/: with it off, nothing about a build changes,
even on a wide clip; with it on, a wide job draws at 1920x1080 and a tall one stays tall."""
import os, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import frame


def numbers(**env):
    code = "import safe_zones as s; print(s.W, s.H, s.TOP, s.BOTTOM, s.LEFT, s.RIGHT, s.RIGHT_RAIL, s.TEXT_SCALE, s.LOW_BAND)"
    clean = {k: v for k, v in os.environ.items() if k != "REEL_FRAME"}
    return subprocess.run([sys.executable, "-c", code], cwd=PRODUCT, env=dict(clean, **env), capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout.strip()


class WideFrame(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jd = os.path.join(self.tmp, "projects", "a-job")
        os.makedirs(os.path.join(self.jd, "outputs"))
        self.cut = os.path.join(self.jd, "outputs", "a-job.mp4")
        open(self.cut, "w", encoding="utf-8").close()
        self.switch = mock.patch.object(frame, "SWITCH", os.path.join(self.tmp, "wide-video"))
        self.switch.start()
        frame._seen.clear()

    def tearDown(self):
        self.switch.stop()

    def dims(self, w, h):
        return mock.patch.dict(sys.modules, {"probe": mock.Mock(display_dims=lambda p: (w, h))})

    def test_tall_numbers_never_move(self):
        self.assertEqual(numbers(), "1080 1920 270 1620 90 990 900 1.0 None")

    def test_a_builder_told_wide_draws_wide(self):
        self.assertTrue(numbers(REEL_FRAME="1920x1080").startswith("1920 1080 110 1010 100 1820 1820 0.8 (785,"))

    def test_switch_off_keeps_a_wide_clip_tall(self):
        with self.dims(1920, 1080):
            self.assertEqual(frame.size(self.jd), frame.TALL)
            self.assertEqual(frame.env(self.jd), {})

    def test_switch_on_goes_by_the_clip(self):
        open(frame.SWITCH, "w", encoding="utf-8").close()
        with self.dims(1920, 1080):
            self.assertEqual(frame.size(os.path.join(self.jd, "hf-graphics", "_looks", "x")), frame.WIDE)
            self.assertEqual(frame.env(self.jd), {"REEL_FRAME": "1920x1080"})
        frame._seen.clear()
        with self.dims(1080, 1920):
            self.assertEqual(frame.size(self.jd), frame.TALL)

    def test_calling_a_wide_clip_a_reel_keeps_it_tall(self):
        open(frame.SWITCH, "w", encoding="utf-8").close()
        with self.dims(1920, 1080):
            frame.choose(self.jd, "reel")
            self.assertEqual(frame.size(self.jd), frame.TALL)
            frame.choose(self.jd, "youtube")
            self.assertEqual(frame.size(self.jd), frame.WIDE)

    def test_the_first_question_follows_the_footage_and_asks_once(self):
        with self.dims(1920, 1080):
            self.assertIsNone(frame.ask(self.jd), "switch off: nothing asked")
            open(frame.SWITCH, "w", encoding="utf-8").close()
            q = frame.ask(self.jd)
            self.assertTrue(q["options"][0]["label"].startswith("YouTube"), q)
            frame.choose(self.jd, "youtube")
            self.assertIsNone(frame.ask(self.jd), "answered: never asked again")
        with self.dims(1080, 1920):
            os.remove(os.path.join(self.jd, "format.json"))
            self.assertTrue(frame.ask(self.jd)["options"][0]["label"].startswith("Vertical"))
            self.assertIn("horizontal clip", frame.choose(self.jd, "youtube"))


if __name__ == "__main__":
    unittest.main()
