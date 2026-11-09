#!/usr/bin/env python3
"""Four buyer problem reports from 2026-10-12, each guarded where it went wrong.

1. CAPTIONS IN GERMAN. A pack's "case": "lower" turned "Gott" into "gott" and misspelled every noun on a German
   reel. Lowercase and title case are English styles: on a reel in another language they keep her words as
   written, and her plan can still set the case per reel (caption_case / takeover_case / headline_case).
2. THE REEL'S LANGUAGE. WhisperX heard de at 1.00, yet the transcript said language_code null / "mixed" (German
   with English loanwords), so nothing downstream could tell the reel was German. One language heard across
   every clip is now recorded as the reel's language.
3. A WINDOWS PC WHERE WHISPERX CRASHES. CTranslate2 4.8 segfaulted loading any model on a 13th-gen Intel laptop,
   and with that pinned, WhisperX still crashed at its voice-detection step. The pin stays, a crash moves the
   job to faster-whisper (which loaded clean there), and the machine is remembered.
4. A TEN-MINUTE HANG ON A MAC. faster-whisper asked Hugging Face for a newer model on every load, and a broken
   IPv6 route hung that question at 0% CPU with the model already downloaded. Cached models load offline first.

Source-level where a real run needs a model download or a crashing machine (the crash path was run by hand with
a stand-in Python that segfaults: the job finished on faster-whisper and the second run skipped WhisperX).
"""
import json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"))

import stylepack  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def job(tmp, name, transcript=None, diagnostics=None):
    """A job folder holding only what job_language() reads."""
    d = os.path.join(tmp, name)
    os.makedirs(os.path.join(d, "outputs"))
    os.makedirs(os.path.join(d, "transcript"))
    if transcript is not None:
        with open(os.path.join(d, "outputs", f"{name}.transcript.json"), "w", encoding="utf-8") as fh:
            json.dump(transcript, fh)
    if diagnostics is not None:
        with open(os.path.join(d, "transcript", ".transcribe-diagnostics.json"), "w", encoding="utf-8") as fh:
            json.dump(diagnostics, fh)
    return d


class CaptionCase(unittest.TestCase):
    def test_german_keeps_its_capitals(self):
        rule = stylepack.case_rule("lower", "caption", {}, "de")
        self.assertEqual(stylepack.apply_case("Gott", rule), "Gott")

    def test_english_keeps_the_pack_style(self):
        self.assertEqual(stylepack.apply_case("Gott", stylepack.case_rule("lower", "caption", {}, None)), "gott")

    def test_upper_is_a_style_in_any_language(self):
        self.assertEqual(stylepack.case_rule("upper", "takeover", {}, "de"), "upper")

    def test_her_plan_wins_in_any_language(self):
        plan = {"caption_case": "lower", "headline_case": "as-written"}
        self.assertEqual(stylepack.case_rule("lower", "caption", plan, "de"), "lower")
        self.assertEqual(stylepack.case_rule("upper", "headline", plan, None), "as-written")

    def test_every_builder_goes_through_the_rule(self):
        """The bug lived in three builders, not one: fixing only the rendered route left the others lowercasing."""
        self.assertIn("stylepack.case_rule", read("product/build-reel-type.py"))
        self.assertIn("stylepack.case_rule", read("product/build-hf-captions.py"))
        self.assertIn("stylepack.case_rule", read("product/packbuild.py"))
        import packbuild
        self.assertEqual(packbuild.caseit("Entscheidung", "lower", "de"), "Entscheidung")
        self.assertEqual(packbuild.caseit("Entscheidung", "lower"), "entscheidung")


class ReelLanguage(unittest.TestCase):
    def test_a_mixed_verdict_with_one_heard_language_is_that_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = job(tmp, "de-reel", {"language_code": None, "language_verdict": "mixed"},
                    {"detected_languages": {"de": 1}})
            self.assertEqual(stylepack.job_language(d), "de")

    def test_english_and_unknown_are_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(stylepack.job_language(job(tmp, "en", {"language_code": "en"})))
            self.assertIsNone(stylepack.job_language(job(tmp, "bare")))

    def test_kept_words_records_what_the_listener_heard(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "kept_words", os.path.join(ROOT, ".claude/skills/rough-cut/scripts/kept-words.py"))
        kw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kw)
        with tempfile.TemporaryDirectory() as tmp:
            words = os.path.join(tmp, "words.json")
            with open(os.path.join(tmp, ".transcribe-diagnostics.json"), "w", encoding="utf-8") as fh:
                json.dump({"detected_languages": {"de": 2}}, fh)
            self.assertEqual(kw.heard_language(words, {"clips": [{"words": []}]}), "de")
            # the faster-whisper route records the language per clip, inside words.json itself
            self.assertEqual(kw.heard_language(words, {"clips": [{"languages": {"fr": 3}}]}), "fr")
            self.assertIsNone(kw.heard_language(words, {"clips": [{"languages": {"fr": 1}},
                                                                  {"languages": {"en": 1}}]}))


class Transcriber(unittest.TestCase):
    SH = ".claude/skills/rough-cut/scripts/word-timings.sh"

    def test_windows_processor_installs_pin_ctranslate2(self):
        src = read(self.SH)
        self.assertIn('CT2_WIN_CPU_PIN="ctranslate2==4.4.0 setuptools<81"', src)
        # whisperx_pin choosing the whisperx it allows; the processor install and its fallback; the listen-back
        # install; the in-place repair and its fallback; the faster-whisper route's install; and since 2026-10-22 the
        # NVIDIA install and its fallback (4.8 crashed there too)
        self.assertEqual(len(re.findall(r"\$\(ct2_pin\)", src)), 9, "every Windows install carries the pin")
        self.assertIn("\npin_ct2_in_place\n", src, "an existing venv is swapped in place")

    def test_a_native_crash_falls_back_to_faster_whisper(self):
        src = read(self.SH)
        self.assertRegex(src, r"132\|134\|136\|138\|139\)")
        self.assertIn('<<\'PY\' || rc=$?', src, "the WhisperX run's exit code is caught, not fatal")
        self.assertIn('FW_ONLY_MARK=".whisperx-crashed"', src)

    def test_cached_models_load_without_the_network(self):
        self.assertIn("local_files_only=True", read(self.SH))
        self.assertIn("model_cache_only=True", read(self.SH))
        for rel in ("scripts/transcribe-nofw.py", ".claude/skills/rough-cut/scripts/verify-cut.py",
                    "product/vo-cutgrid.py"):
            self.assertIn("local_files_only=True", read(rel), rel)


class CapCutOnAMac(unittest.TestCase):
    def test_open_is_not_windows_only(self):
        src = read("product/capcut_installs.py")
        self.assertIn('sys.platform == "darwin"', src)
        self.assertIn("/Applications/CapCut.app", src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
