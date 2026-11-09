#!/usr/bin/env python3
"""The transcriber must never be told what language the creator speaks.

THE BUG THIS EXISTS FOR. Both transcription routes once pinned language="en" before hearing a second
of audio. Whisper does not argue with that: it TRANSLATES instead of transcribing, so a reel filmed
in Spanish came back as fluent English the creator never said, and every caption and graphic
downstream was built from the translation. It survived three rounds of investigation because every
file the engine checked was downstream of the same bad transcription, so they all agreed with each
other. A tester watching her own video is what broke it open.

Fixed in v1.0.70 for 41 languages. This guards the fix at the source, because the failure is silent:
nothing errors, nothing looks wrong, and the only symptom is a creator reading words she never said.

Deliberately source-level, not a transcription run. A real audio fixture would need a model download
and minutes per run, and would not catch the thing that actually went wrong, which was one argument
in one call being copied from another route without questioning it.
"""
import os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# Every place a transcription model is asked to do work.
ROUTES = (
    ".claude/skills/rough-cut/scripts/word-timings.sh",   # WhisperX (Apple Silicon / PC)
    "scripts/transcribe-nofw.py",                       # faster-whisper (Intel Mac)
)

# A literal language on a transcribe/load call. Allows language=None and a variable such as
# _FORCED_LANG, which is the opt-in override a creator sets deliberately.
PINNED = re.compile(r"""language(?:_code)?\s*=\s*['"][a-z]{2}['"]""", re.I)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def code_lines(src):
    """Comments explain the old bug on purpose, so judge code only."""
    for i, line in enumerate(src.splitlines(), 1):
        bare = line.split("#", 1)[0]
        if bare.strip():
            yield i, bare


class NeverPinned(unittest.TestCase):
    def test_no_route_hardcodes_a_language(self):
        for rel in ROUTES:
            for i, line in code_lines(read(rel)):
                m = PINNED.search(line)
                self.assertIsNone(
                    m,
                    f"{rel}:{i} pins a language: {line.strip()!r}\n"
                    f"The transcriber must detect it. Pinning translates the creator instead of "
                    f"transcribing her. Use language=None, or the REELS_ENGINE_LANGUAGE override.")

    def test_the_override_defaults_to_unset(self):
        """REELS_ENGINE_LANGUAGE is a creator correcting a wrong guess. It must never default to a
        language, or it becomes the hardcoded pin again wearing a different name."""
        src = read(ROUTES[0])
        m = re.search(r"_FORCED_LANG\s*=\s*(.+)", src)
        self.assertIsNotNone(m, "REELS_ENGINE_LANGUAGE override not found")
        expr = m.group(1)
        self.assertIn("or None", expr, f"override must fall back to None, got: {expr.strip()}")
        self.assertIsNone(re.search(r"""get\([^)]*,\s*['"][a-z]{2}['"]""", expr),
                          f"override has a language default: {expr.strip()}")

    def test_intel_route_still_detects_per_segment(self):
        """multilingual=True decides per segment. Without it, auto-detect locks the whole clip to the
        dominant language and renders a code-switched reel as a paraphrase of the other half."""
        # Code lines only. The comment above that call also says "multilingual=True", so searching
        # the whole file passes on the documentation while the argument itself is gone — which is
        # exactly what this test did until it was checked against a real mutation.
        src = read("scripts/transcribe-nofw.py")
        in_code = any("multilingual=True" in line for _i, line in code_lines(src))
        self.assertTrue(in_code, "the Intel route lost per-segment detection")

    def test_the_canonical_transcript_reports_a_real_verdict(self):
        """kept-words once wrote language_code 'en' on every job with no detection at all.
        Everything downstream believed it."""
        src = read(".claude/skills/rough-cut/scripts/kept-words.py")
        self.assertIn("classify(", src, "the transcript's language is not being measured")
        for i, line in code_lines(src):
            if '"language_code"' in line:
                self.assertIsNone(
                    re.search(r'"language_code"\s*:\s*["\'][a-z]{2}["\']', line),
                    f"kept-words.py:{i} writes a literal language_code: {line.strip()!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
