#!/usr/bin/env python3
"""On-screen copy must follow the speaker's language, and the check must have teeth.

Captions come from the transcript so they follow the speaker on their own. Hooks and cards are
written fresh and default to English. A reel shipped with Spanish captions under an English hook
card. The rule was already written in CLAUDE.md and in graphics-plan/SKILL.md when that happened,
which is the point of these tests: a rule that only lives in prose is not enforced.
"""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "graphics-plan", "scripts")
CHECK = os.path.join(SCRIPTS, "check-plan-language.py")
SEGMENT = os.path.join(SCRIPTS, "beat-lines.py")

PASS, WRONG_LANGUAGE, CANNOT_CHECK = 0, 1, 2


def run_check(plan):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(plan, fh)
        path = fh.name
    try:
        r = subprocess.run([sys.executable, CHECK, path], capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr)
    finally:
        os.unlink(path)


def beat(i, on_screen=None, **kw):
    b = {"id": i, "element": "word-card", "zone": "open"}
    if on_screen is not None:
        b["on_screen"] = on_screen
    b.update(kw)
    return b


class TheGate(unittest.TestCase):
    def test_english_reel_passes_and_says_nothing_alarming(self):
        rc, out = run_check({"language": {"verdict": "english", "code": "en"},
                             "beats": [beat(1, "I quit my job")]})
        self.assertEqual(rc, PASS)
        self.assertNotIn("REFUSED", out)

    def test_spanish_reel_with_english_copy_is_refused(self):
        rc, out = run_check({"language": {"verdict": "non_english", "code": None},
                             "beats": [beat(1, "I quit my job"),
                                       beat(4, "Three things nobody tells you")]})
        self.assertEqual(rc, WRONG_LANGUAGE)
        self.assertIn("REFUSED", out)
        self.assertIn("I quit my job", out)      # names the strings to rewrite

    def test_spanish_reel_with_spanish_copy_passes(self):
        rc, out = run_check({"language": {"verdict": "non_english", "code": None},
                             "beats": [beat(1, "Dejé mi trabajo"),
                                       beat(4, "¿Qué nadie te dice?")]})
        self.assertEqual(rc, PASS, out)

    def test_graphics_with_no_on_screen_copy_cannot_be_checked(self):
        rc, out = run_check({"language": {"verdict": "non_english"},
                             "beats": [beat(1, idea="big kinetic hook card")]})
        self.assertEqual(rc, CANNOT_CHECK)
        self.assertIn("on_screen", out)

    def test_a_face_beat_carries_no_graphic(self):
        """`element` names what a beat shows; "face" means it stays on her and has no copy to check."""
        rc, _ = run_check({"language": {"verdict": "non_english"},
                           "beats": [{"id": 1, "element": "face", "why": "her moment"}]})
        self.assertEqual(rc, PASS)

    def test_a_plan_already_on_disk_reads_the_same(self):
        """A plan written by an earlier engine marks its beats with `graphic` true/false; it is read as it was."""
        rc, out = run_check({"language": {"verdict": "non_english"},
                             "beats": [{"id": 1, "graphic": True, "content": "big kinetic hook card"}]})
        self.assertEqual(rc, CANNOT_CHECK)
        self.assertIn("on_screen", out)
        rc, _ = run_check({"language": {"verdict": "non_english"},
                           "beats": [{"id": 1, "graphic": False, "reason": "her moment"}]})
        self.assertEqual(rc, PASS)

    def test_undetermined_language_does_not_silently_pass(self):
        rc, _ = run_check({"language": {"verdict": "unknown"},
                           "beats": [beat(1, "hello")]})
        self.assertEqual(rc, CANNOT_CHECK)

    def test_english_prose_describing_a_spanish_card_is_not_a_defect(self):
        """`idea` is written for a human and is deliberately not checked."""
        rc, _ = run_check({"language": {"verdict": "non_english"},
                           "beats": [beat(1, "Dejé mi trabajo",
                                          idea="big kinetic hook, hard cut on the last word")]})
        self.assertEqual(rc, PASS)


class TheStamp(unittest.TestCase):
    def scaffold_for(self, words, **transcript):
        d = tempfile.mkdtemp()
        w = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.35} for i, t in enumerate(words.split())]
        src = os.path.join(d, "x.transcript.json")
        payload = {"text": words, "words": w}
        payload.update(transcript)
        with open(src, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        out = os.path.join(d, "scaffold.json")
        subprocess.run([sys.executable, SEGMENT, src, "--out", out], capture_output=True, text=True)
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    SPANISH = ("Dejé mi trabajo porque ya no podía más con todo esto y la verdad es que fue muy "
               "difícil pero también fue lo mejor que hice para mi familia y para mí misma aquí estamos")

    def test_the_plan_is_born_knowing_its_language(self):
        s = self.scaffold_for("This is a perfectly ordinary English sentence about work and kids.",
                              language_code="en", language_verdict="english")
        self.assertEqual(s["language"]["verdict"], "english")

    def test_a_legacy_hardcoded_en_does_not_win_over_the_words(self):
        """Transcripts before v1.0.70 stamped language_code 'en' on every job including Spanish ones,
        because nothing ever detected. A bare 'en' with no verdict is evidence of an old transcript,
        not evidence of English."""
        s = self.scaffold_for(self.SPANISH, language_code="en")     # no language_verdict
        self.assertEqual(s["language"]["verdict"], "non_english")
        self.assertIn("predates", s["language"]["source"])

    def test_it_never_guesses_a_language_code(self):
        s = self.scaffold_for(self.SPANISH, language_code="en")
        self.assertIsNone(s["language"]["code"])

    def test_every_beat_can_record_its_on_screen_copy(self):
        s = self.scaffold_for("One two three four five six seven eight nine ten eleven twelve.",
                              language_code="en", language_verdict="english")
        self.assertIn("on_screen", s["beats"][0])

    def test_every_beat_carries_the_plan_fields_blank(self):
        s = self.scaffold_for("One two three four five six seven eight nine ten eleven twelve.",
                              language_code="en", language_verdict="english")
        for field in ("element", "zone", "idea", "on_screen", "why"):
            self.assertIn(field, s["beats"][0])
            self.assertIsNone(s["beats"][0][field])


class TheCommandLine(unittest.TestCase):
    def test_the_scaffold_goes_where_out_says_and_nowhere_else(self):
        d = tempfile.mkdtemp()
        src = os.path.join(d, "x.transcript.json")
        with open(src, "w", encoding="utf-8") as fh:
            json.dump({"words": [{"text": "Hello there.", "start": 0.0, "end": 0.6}]}, fh)
        out = os.path.join(d, "deep", "plan.json")
        r = subprocess.run([sys.executable, SEGMENT, src, "--out", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(r.stdout, "")
        r = subprocess.run([sys.executable, SEGMENT, src, os.path.join(d, "second.json")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage: beat-lines.py <job> [--out FILE]", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "second.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
