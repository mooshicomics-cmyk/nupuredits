#!/usr/bin/env python3
"""Buyer problem reports from the 2026-10-21 support sweep, each guarded where it went wrong.

1. LOCK IN MY CUT NEVER CAME BACK. The transcriber handed back a lone "?" (French " ?") as its own 20 ms word. On her
   page it was a word she could cut, but the stitch can't cut less than a frame, so its cut never took: the page
   always had an edit to send, Lock in never showed, and every Send reopened the cut. Punctuation now rides on the
   word beside it (visual_editor.words_of). The page itself is walked in editor_journey.js (REPORTED 2026-10-21).
2. CAPTIONS ON A LINE WITH A CENSORED WORD PLAYED ON EVEN SPACING. "f**k" in her transcript read as two words against
   the look's text (which drops "*"), so nothing matched and every word fell to 0.25 s steps (lookbook._words). And a
   look whose words stayed the same but whose timing moved was never redrawn (visual_editor._draw_choice).
3. THE UPDATER STOPPED AT THE CHECKSUM. A network filter handed Python a damaged zip without an error, so the curl
   fallback never ran. A checksum mismatch now asks once more through curl (apply-update.py _download_verified).

Run: python3 product/tests/test_buyer_reports_2026_10_21_sweep.py   (Windows: python)
"""
import importlib.util, io, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))

for _s in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print every character
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

import lookbook  # noqa: E402
import visual_editor as ve  # noqa: E402


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def clip(name, words, dur=12.0):
    return {"clip": name, "duration": dur, "words": [{"word": w, "start": s, "end": e} for w, s, e in words]}


class LonePunctuation(unittest.TestCase):
    def test_a_lone_question_mark_rides_on_the_word_before_it(self):
        ws = ve.words_of([clip("a.mov", [("c'est", 7.5, 7.8), ("vrai", 7.85, 8.2), ("?", 8.213, 8.233), ("oui", 8.6, 8.9)])])
        self.assertEqual([w["t"] for w in ws], ["c'est", "vrai?", "oui"])
        self.assertEqual((ws[1]["s"], ws[1]["e"]), (7.85, 8.2), "the word keeps its own timing")

    def test_punctuation_first_in_a_clip_rides_on_the_word_after_it(self):
        ws = ve.words_of([clip("a.mov", [("hola", 0.2, 0.5)]), clip("b.mov", [("¿", 0.1, 0.11), ("qué", 0.12, 0.4), ("...", 0.4, 0.41)])])
        self.assertEqual([(w["t"], w["c"]) for w in ws], [("hola", 0), ("¿qué...", 1)])

    def test_never_rides_across_clips(self):
        ws = ve.words_of([clip("a.mov", [("yes", 0.2, 0.5)]), clip("b.mov", [("!", 0.0, 0.02), ("no", 0.1, 0.4)])])
        self.assertEqual([w["t"] for w in ws], ["yes", "!no"])

    def test_no_word_is_only_punctuation(self):
        ws = ve.words_of([clip("a.mov", [("one", 0.1, 0.3), ("—", 0.3, 0.31), ("?", 0.31, 0.32), ("two", 0.4, 0.6)])])
        self.assertTrue(all(any(ch.isalnum() for ch in w["t"]) for w in ws), ws)
        self.assertEqual(len(ws), 2)


class CensoredWordTiming(unittest.TestCase):
    WORDS = [{"w": "what", "t": 0.0, "e": 0.25}, {"w": "the", "t": 0.31, "e": 0.42}, {"w": "f**k", "t": 0.47, "e": 0.9},
             {"w": "is", "t": 1.3, "e": 1.4}, {"w": "this", "t": 1.45, "e": 1.8}]

    def test_a_censored_word_keeps_her_real_timings(self):
        ws = lookbook._words("what the f**k is this", 2.5, self.WORDS)
        self.assertEqual([w["t"] for w in ws], [0.0, 0.31, 0.47, 1.3, 1.45], "her timings, not even spacing")

    def test_other_copy_still_spreads_evenly(self):
        ws = lookbook._words("a different line", 2.5, self.WORDS)
        self.assertEqual(len(ws), 3)


class TimingOnlyRedraw(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.look = lookbook.find("hook", "Butter")
        self.text = "the line she says"
        self.words = [{"w": w, "t": 0.1 + 0.3 * k, "e": 0.35 + 0.3 * k} for k, w in enumerate(self.text.split())]
        self.rel = "hf-graphics/_looks/k01/hook"
        d = os.path.join(self.tmp, self.rel)
        self.page = os.path.join(d, "hf-reel-type-butter")
        os.makedirs(self.page)
        with open(os.path.join(self.page, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<div></div>")
        dump({"look": "hook", "pack": "Butter", "text": lookbook.shown_text(self.look, self.text), "dur": 2.0, "accents": [], "track": None},
             os.path.join(d, "look.json"))
        self.drawn_with(self.words)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def drawn_with(self, words):
        rec = {"look": "hook", "pack": "Butter", "words": [{"w": w["w"], "t": w["t"], "e": w["e"]} for w in lookbook.drawn_words(self.look, self.text, 2.0, words)]}
        dump(rec, os.path.join(self.page, "look.json"))

    def draws(self, words):
        with mock.patch.object(ve, "_stale_look", return_value=False), mock.patch.object(lookbook, "draw") as draw:
            ve._draw_choice(self.tmp, self.look, self.rel, "c-k01", self.text, 2.0, "Butter", None, words)
        return draw.call_count

    def test_same_words_same_timing_is_not_redrawn(self):
        self.assertEqual(self.draws(self.words), 0)

    def test_same_words_moved_timing_is_redrawn(self):
        moved = [dict(w, t=w["t"] + 0.2, e=w["e"] + 0.2) for w in self.words]
        self.assertEqual(self.draws(moved), 1)

    def test_a_page_with_no_record_of_its_timing_is_left_as_it_is(self):
        dump({"look": "hook", "pack": "Butter"}, os.path.join(self.page, "look.json"))
        self.assertEqual(self.draws([dict(w, t=w["t"] + 0.2) for w in self.words]), 0)


class DamagedDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        eng = Path(self.tmp) / "engine"
        (eng / "scripts").mkdir(parents=True)
        for f in ("apply-update.py", "update_signature.py"):
            shutil.copy(os.path.join(ROOT, "scripts", f), eng / "scripts" / f)
        (eng / "product.json").write_text(json.dumps(
            {"engine": "ai-edit-engine", "version": "2.2.2", "update_url": "https://feed.invalid/v2"}), encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"apply_update_{os.path.basename(self.tmp)}", eng / "scripts" / "apply-update.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.good = os.urandom(200_000)
        self.src = Path(self.tmp) / "pkg.zip"
        self.src.write_bytes(self.good)
        self.expected = self.mod.sha256(self.src)
        self.dest = eng / "_updates" / "pkg.zip"
        self.dest.parent.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def python_hands_back(self, body):
        self.mod.urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(body)

    def test_a_damaged_zip_is_fetched_again_through_curl(self):
        if not shutil.which("curl"):
            self.skipTest("no curl on this computer (macOS and Windows 10+ always have one)")
        self.python_hands_back(self.good[:1000] + b"filtered")
        self.assertTrue(self.mod._download_verified(self.src.as_uri(), self.dest, self.expected))
        self.assertEqual(self.dest.read_bytes(), self.good)

    def test_damaged_both_ways_gives_up_and_leaves_nothing(self):
        self.python_hands_back(b"filtered")
        ran = []
        self.mod._curl_get = lambda url, timeout, dest=None: (ran.append(url), Path(dest).write_bytes(b"filtered too"), True)[-1]
        self.assertFalse(self.mod._download_verified("https://feed.invalid/v2/pkg.zip", self.dest, self.expected))
        self.assertEqual(len(ran), 1, "curl is asked once, not in a loop")
        self.assertFalse(self.dest.exists())

    def test_an_intact_download_never_runs_curl(self):
        self.python_hands_back(self.good)
        ran = []
        self.mod._curl_get = lambda *a, **k: ran.append(a)
        self.assertTrue(self.mod._download_verified("https://feed.invalid/v2/pkg.zip", self.dest, self.expected))
        self.assertEqual(ran, [])

    def test_fetch_uses_it(self):
        src = (Path(ROOT) / "scripts" / "apply-update.py").read_text(encoding="utf-8")
        self.assertIn("_download_verified(zip_url, dest, expected)", src)


if __name__ == "__main__":
    unittest.main()
