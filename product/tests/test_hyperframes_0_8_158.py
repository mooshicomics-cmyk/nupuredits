#!/usr/bin/env python3
"""test_hyperframes_0_8_158.py — what moving the HyperFrames pin from 0.8.43 to 0.8.158 asked of the engine.

Three things HyperFrames changed that the engine had to meet (the off-frame text gate's new sample-list format is
covered in test_offframe_text.py):
  1. `check` now writes its own records into the composition (.hyperframes/), so a render cache keyed on every
     file in the folder never hit again. The hash leaves that folder out, and so does the isolated render copy.
  2. Every render ends with a line advertising HyperFrames' desktop app. The toolkit is never named to her, so
     that one line is kept out of what the render prints, whole or arriving in pieces; progress bars still pass.
  3. A new per-clip editor hint (nested_structure_needs_subcomposition) is counted as noise, not a finding.
And the pin itself: product.json, npx_run's last-resort fallback and every shipped package.json agree.

Run: python3 product/tests/test_hyperframes_0_8_158.py
"""
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import reel_render as RR  # noqa: E402

OLD_PIN = "0.8.43"   # the pin this release moved off (spelled apart so the ship gate never reads it as a pin)
AD = (b"   Keep editing by chatting with Framey in the HyperFrames desktop app \xe2\x86\x92 "
      b"https://hyperframes.dev/studio/download\n")


class Cache(unittest.TestCase):
    def test_check_records_do_not_change_the_hash(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                fh.write("<div></div>")
            before = RR.comp_hash(d)
            os.makedirs(os.path.join(d, ".hyperframes", "artifacts", "checks"))
            with open(os.path.join(d, ".hyperframes", "artifacts", "checks", "a1.json"), "w", encoding="utf-8") as fh:
                fh.write("{}")
            self.assertEqual(RR.comp_hash(d), before)
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                fh.write("<div>changed</div>")
            self.assertNotEqual(RR.comp_hash(d), before)   # a real change still counts
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_isolated_copy_leaves_the_check_records_behind(self):
        src = open(os.path.join(PRODUCT, "reel_render.py"), encoding="utf-8").read()
        self.assertIn('shutil.ignore_patterns(".reel_render", "renders", ".hyperframes", ".DS_Store")', src)


class Promo(unittest.TestCase):
    def test_ad_line_is_dropped_and_the_rest_passes(self):
        buf = b"Rendering frame 9/10\r   10.8 MB \xc2\xb7 2.5s video\n" + AD + b"done\n"
        out, held = RR._without_promo(buf)
        self.assertNotIn(b"Framey", out)
        self.assertIn(b"Rendering frame 9/10\r", out)
        self.assertIn(b"10.8 MB", out)
        self.assertIn(b"done\n", out)
        self.assertEqual(held, b"")

    def test_ad_arriving_in_pieces_never_slips_out(self):
        shown, held = b"", b""
        for piece in (AD[:20], AD[20:45], AD[45:]):
            out, held = RR._without_promo(held + piece)
            shown += out
        self.assertEqual(shown, b"")
        self.assertEqual(held, b"")

    def test_progress_bar_is_not_held_for_a_line_end(self):
        out, held = RR._without_promo(b"Capturing frame 3/90 [===   ")
        self.assertEqual(out, b"Capturing frame 3/90 [===   ")
        self.assertEqual(held, b"")


    def test_both_render_paths_filter_the_ad(self):
        src = open(os.path.join(PRODUCT, "reel_render.py"), encoding="utf-8").read()
        self.assertEqual(src.count("_without_promo(shown + chunk)"), 2)   # watched and STALL_SECONDS=0 paths


class Noise(unittest.TestCase):
    def test_new_editor_hint_is_noise(self):
        self.assertIn("nested_structure_needs_subcomposition", RR._NOISE_KINDS)


class Pin(unittest.TestCase):
    def test_every_pin_agrees(self):
        pin = json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8"))["hyperframes"]
        # 0.8.155+ only: 0.8.81-0.8.154 blank the right 8 px of a 1080-wide MP4 (fixed upstream in 0.8.155)
        self.assertGreaterEqual(tuple(int(x) for x in pin.split(".")), (0, 8, 155), pin)
        self.assertIn(f'return "{pin}"', open(os.path.join(PRODUCT, "npx_run.py"), encoding="utf-8").read())
        for pj in glob.glob(os.path.join(PRODUCT, "**", "package.json"), recursive=True):
            if "node_modules" in pj:
                continue
            txt = open(pj, encoding="utf-8").read()
            if "hyperframes@" in txt:
                self.assertIn(f"hyperframes@{pin} ", txt, pj)
                self.assertNotIn("hyperframes@" + OLD_PIN, txt, pj)

    def test_setup_and_studio_read_the_pin(self):
        for rel in ("check-setup.sh", "product/studio_behind.sh"):
            self.assertNotIn("0.8.43", open(os.path.join(ROOT, rel), encoding="utf-8").read(), rel)


if __name__ == "__main__":
    unittest.main()
