#!/usr/bin/env python3
"""Buyer problem reports from 2026-10-13/14, each guarded where it went wrong.

1. VOICE DETECTION WOULD NOT LOAD. whisperx was installed unpinned, so the resolver walked back to whichever
   whisperx fit the other pins and took the newest torch with it: a processor-only Windows PC (ctranslate2 4.4.0)
   got whisperx 3.4.5 with torch 2.14 and torchaudio 2.11 (no AudioMetaData; the checkpoint refused), and a CUDA
   PC, whose torch went in first, drifted the same way. torch is pinned to 2.8.0 with the newest whisperx each
   machine's pins allow, a driver too old for that torch's GPU build installs for the processor, and a venv that
   already drifted is put back once, in place.
2. FONTS NEVER FOUND WITH CAPCUT FROM CAPCUT.COM. The font resolver read only the App Store sandbox, which a
   capcut.com install does not have. Both installs keep User Data in ~/Movies (the sandbox's Movies is a link).
3. A ONE-WORD EFFECT CUE CUT. Pausing before the effect ("this is a... takeover") left "takeover" as its own
   one-word sentence, and the orphan-fragment rule dropped it.
4. SOUND-CHECK'S -3 ms "THE PLAN CHANGED". The length check allowed one AAC frame long but under a sample short,
   so a clip whose sound ends a few ms before its picture read as a stale render.

Source-level for the installer (a real run needs a PC and a 3 GB download; its branches were run by hand with a
stand-in uv, Python and nvidia-smi).
"""
import contextlib, importlib.util, io, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
sys.path.insert(0, os.path.join(ROOT, "product"))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Transcriber(unittest.TestCase):
    SH = ".claude/skills/rough-cut/scripts/word-timings.sh"

    def test_every_install_names_its_whisperx_and_torch(self):
        src = read(self.SH)
        self.assertIn('TORCH_PIN="torch==2.8.0 torchaudio==2.8.0"', src)
        for v in ("whisperx==3.4.5", "whisperx==3.7.9", "whisperx==3.8.6"):
            self.assertIn(v, src)
        installs = [ln for ln in src.splitlines()
                    if "uv pip install" in ln and not ln.strip().startswith("#") and "whisperx" in ln]
        self.assertGreaterEqual(len(installs), 3, installs)
        for ln in installs:
            self.assertIn("$TORCH_PIN", ln, "torch is pinned on every whisperx install, the fallback included")
        self.assertTrue(any("$(whisperx_pin) $TORCH_PIN" in ln for ln in installs))

    def test_cuda_torch_is_the_pinned_one_on_a_channel_that_has_it(self):
        src = read(self.SH)
        self.assertIn('$TORCH_PIN $tv --extra-index-url', src)
        self.assertNotRegex(src, r"CUDA_CHAN=cu1(18|21|24)\b", "torch 2.8.0 has no build on these channels")

    def test_a_drifted_venv_is_put_back(self):
        src = read(self.SH)
        self.assertIn("\npin_whisperx_in_place\npin_ct2_in_place\n", src)
        self.assertIn("mm(p) >= (2, 9)", src, "only the drifted shape is touched")


class NeverADeadEnd(unittest.TestCase):
    """Her edit never stops at the transcriber: WhisperX that will not install or run hands the reel to
    faster-whisper, every later reel goes straight there, and the switch is in the problem report.
    (Every branch was run by hand under bash with a stand-in Python and uv.)"""
    SH = Transcriber.SH

    def test_a_failed_install_pivots(self):
        src = read(self.SH)
        self.assertIn('pivot_to_faster_whisper "WhisperX would not install on this computer"', src)
        self.assertIn("install_listener || true", src, "a failed step is judged by what imports, not by exit")

    def test_an_error_or_crash_pivots_and_is_remembered(self):
        src = read(self.SH)
        self.assertIn("1|132|134|136|138|139)", src)
        self.assertIn('elif pivot_to_faster_whisper "$why"; then', src)
        self.assertIn('[ -e "$VENV$PIVOT_SUFFIX" ]', src, "later reels go straight to the route that worked")

    def test_the_report_carries_every_switch(self):
        self.assertIn("_local/fallbacks.log", read(self.SH))
        self.assertIn("_local/fallbacks.log", read("scripts/collect-report.sh"))


class FontsOnEitherCapCut(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "the Mac paths")
    def test_mac_reads_user_data_from_movies(self):
        cu = load("capcut_userfonts_t", os.path.join(ROOT, "product", "capcut_userfonts.py"))
        home = os.path.expanduser("~/Movies/CapCut/User Data")
        self.assertEqual(cu._USERFD, os.path.join(home, "Config/userFontData"))
        self.assertEqual(cu._CATALOG, os.path.join(home, "Cache/effect"))
        self.assertNotIn("Containers", cu._USERFD)


class CueWordsStay(unittest.TestCase):
    def test_a_lone_effect_word_survives_the_fragment_rule(self):
        tc = load("transcript_cut_t", os.path.join(SCRIPTS, "transcript-cut.py"))
        W, t = [], 0.0
        for line in ["This is a", "takeover", "And here's a", "count-up", "um", "the"]:
            for w in line.split():
                W.append((w, t, t + 0.3)); t += 0.35
            t += 0.8
        S = tc.sentences(W)
        kept = [" ".join(w for (w, _, _) in s) for i, s in enumerate(S)
                if i not in tc.drop_set(S, [tc.toks(s) for s in S])]
        self.assertIn("takeover", kept)
        self.assertIn("count-up", kept)
        self.assertNotIn("um", kept)
        self.assertNotIn("the", kept)


class LengthWithinAFrame(unittest.TestCase):
    def say(self, pcm_len, planned):
        sc = load("sound_check_t", os.path.join(SCRIPTS, "sound-check.py"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sc.hear_length([0] * pcm_len, planned, 20, [], "job")
        return out.getvalue()

    def test_a_few_ms_short_is_a_match(self):
        self.assertIn("✓ length", self.say(48000 * 10 - 144, 10.0))   # -3 ms

    def test_a_frame_off_is_still_caught(self):
        self.assertIn("⚠ length", self.say(48000 * 10 - 1600, 10.0))  # -33 ms
        self.assertIn("⚠ length", self.say(48000 * 10 + 1600, 10.0))


if __name__ == "__main__":
    unittest.main()
