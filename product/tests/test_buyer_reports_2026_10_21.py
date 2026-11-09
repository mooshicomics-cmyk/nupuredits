#!/usr/bin/env python3
"""Buyer problem reports from 2026-10-21, each guarded where it went wrong.

1. INTEL MAC SETUP STUCK ON FFPROBE. evermeet.cx answered HTTP 429 "Too Many Connections" for over an hour and it was
   the only Intel source. The second pinned source, the retry and the log line are run end to end on a simulated
   Intel Mac in test_mac_route.py ("4a"); this file only pins that the installer still carries both.
2. EVERY CUT LANDED 0.7 S EARLY. An iPhone clip copied out of Photos had its sound start 0.703 s after its picture.
   The words are on the sound's clock, the stitch trims on the file's: product/av_sync.py lines the job's copy up.
3. A WHITE HALO AND A DOTTED OUTLINE ON SOFT TEXT EDGES IN CAPCUT. Read at the time as a mid-tone shadow's colour being
   added on top; the scaling that answered it was taken out on 2026-11-01, measured wrong in real CapCut exports. With
   no numpy in the interpreter, the clean never ran at all, with nothing said: that half still stands.
4. VOICE LEVELING SKIPPED ON WINDOWS. os.replace raised PermissionError (WinError 5) while the fresh MP4 was still
   held open for a moment, and the .level.tmp.mp4 was left behind.

Run: python3 product/tests/test_buyer_reports_2026_10_21.py
"""
import array, hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
HAVE_UV = bool(shutil.which("uv"))
W, H = 64, 64

import swap  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class IntelSecondSource(unittest.TestCase):
    def test_installer_has_a_pinned_second_intel_source(self):
        src = read("scripts/intel-mac-install.sh")
        self.assertIn("https://www.osxexperts.net/${1}80intel.zip", src)
        body = src[src.index("_osxexperts_sha256() {"):]
        self.assertEqual(len(re.findall(r'echo "[0-9a-f]{64}"', body[:body.index("\n}\n")])), 2, "both zips pinned")
        self.assertIn('note_fallback intel-mac-install', src, "the switch is logged for /report-a-problem")
        self.assertNotIn("python3", src[src.index("_intel_zip() {"):src.index("_sha256() {")],
                         "no Python on a fresh Intel Mac: the fallback is pure shell")


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class SoundStartsLate(unittest.TestCase):
    """The clip as Photos hands it over: picture from 0, a tone (her first word) from the sound's first sample, which
    the file places 0.703 s in."""
    LEAD = 0.703

    def setUp(self):
        import av_sync
        self.av = av_sync
        self.tmp = tempfile.mkdtemp()
        self.job = os.path.join(self.tmp, "the-photos-one")
        os.makedirs(os.path.join(self.job, "raw"))
        v0, v, a = (os.path.join(self.tmp, n) for n in ("v0.mov", "v.mov", "a.m4a"))
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=red:s={H}x{W}:d=3:r=30", "-c:v", "libx264", v0])
        run(["ffmpeg", "-v", "error", "-y", "-display_rotation", "90", "-i", v0, "-c", "copy", v])   # stored sideways
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.2", "-c:a", "aac", a])
        self.inbox = os.path.join(self.tmp, "IMG_0001.MOV")
        run(["ffmpeg", "-v", "error", "-y", "-i", v, "-itsoffset", str(self.LEAD), "-i", a, "-map", "0:v", "-map", "1:a",
             "-c", "copy", self.inbox])
        self.clip = os.path.join(self.job, "raw", "IMG_0001.MOV")
        shutil.copy2(self.inbox, self.clip)                                  # intake copies, never moves
        self.ok = os.path.join(self.job, "raw", "IMG_0002.MOV")
        run(["ffmpeg", "-v", "error", "-y", "-i", v, "-i", a, "-map", "0:v", "-map", "1:a", "-c", "copy", self.ok])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def first_sound(self, path):
        """Where the tone starts, in seconds of the file's sound as decoded from its start: the transcript's clock."""
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar",
                              "48000", "-"], capture_output=True, check=True).stdout
        samples = array.array("h", pcm)
        return next(i for i, x in enumerate(samples) if abs(x) > 500) / 48000.0

    def rotation(self, path):
        return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream_side_data=rotation", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()

    def test_the_late_clip_is_found_and_the_normal_one_is_not(self):
        late = self.av.late_clips(os.path.join(self.job, "raw"))
        self.assertEqual([c["name"] for c in late], ["IMG_0001.MOV"])
        self.assertAlmostEqual(late[0]["lead"], self.LEAD, delta=0.04)

    def test_lined_up_the_transcript_clock_is_the_file_clock(self):
        before_ok, before_inbox = sha(self.ok), sha(self.inbox)
        self.assertLess(self.first_sound(self.clip), 0.05, "before: her first word is at 0 on the sound's own clock")
        self.assertEqual(self.av.main([self.job, "--apply"]), 0)
        self.assertLess(abs(self.av.audio_lead(self.clip)), self.av.LEAD_LIMIT)
        self.assertAlmostEqual(self.first_sound(self.clip), self.LEAD, delta=0.03,
                               msg="after: the words are heard where the file plays them, so a cut on them lands true")
        self.assertEqual(self.rotation(self.clip), self.rotation(self.inbox), "the picture keeps its rotation")
        self.assertEqual(self.av._frames(self.clip), self.av._frames(self.inbox), "every frame of picture kept")
        self.assertEqual(sha(self.ok), before_ok, "a clip already on one clock is not touched")
        self.assertEqual(sha(self.inbox), before_inbox, "her original is never touched")
        self.assertEqual([f for f in os.listdir(os.path.join(self.job, "raw")) if f.startswith(".")], [], "no temp left")

    def test_a_heard_job_is_lined_up_with_its_words(self):
        """2026-10-22: a heard job is no longer left on the old clock (that kept a buyer's reel choppy after the
        update): its words move with it. The whole catch-up is in test_heard_late_sound.py."""
        os.makedirs(os.path.join(self.job, "transcript"))
        wp = os.path.join(self.job, "transcript", "words.json")
        with open(wp, "w", encoding="utf-8") as fh:
            json.dump({"clips": [{"clip": "IMG_0001.MOV", "words": [{"word": "hi", "start": 0.0, "end": 0.4}]}]}, fh)
        before = sha(self.clip)
        with mock.patch.dict(os.environ, {"REELS_ENGINE_LOCAL": os.path.join(self.tmp, "_local")}):
            self.assertEqual(self.av.main([self.job, "--apply"]), 0)
        self.assertNotEqual(sha(self.clip), before)
        with open(wp, encoding="utf-8") as fh:
            w = json.load(fh)["clips"][0]
        self.assertAlmostEqual(w["words"][0]["start"], w["sound_lined_up"], places=3, msg="her word moved by the lead")

    def test_relisten_lines_up_only(self):
        os.makedirs(os.path.join(self.job, "transcript"))
        open(os.path.join(self.job, "transcript", "words.json"), "w", encoding="utf-8").close()
        before = sha(self.clip)
        self.assertEqual(self.av.main([self.job, "--apply", "--relisten"]), 0)
        self.assertNotEqual(sha(self.clip), before, "word-timings lines it up right before it listens again")

    def test_wired_into_intake_and_the_listener(self):
        self.assertIn("python3 product/av_sync.py <job> --apply", read(".claude/skills/rough-cut/SKILL.md"))
        wt = read(".claude/skills/rough-cut/scripts/word-timings.sh")
        self.assertIn("hand_back_if_heard\ngather_footage\nline_up_sound\n", wt, "only before a fresh listen")
        self.assertIn('av_sync.py" "$JOB_DIR" --apply --relisten', wt)


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class SoftEdgesInCapCut(unittest.TestCase):
    def setUp(self):
        import capcut_alpha
        self.ca = capcut_alpha
        self.tmp = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {"REEL_CAPCUT_ALPHA_CACHE": os.path.join(self.tmp, "cache"),
                                                 "REELS_ENGINE_LOCAL": os.path.join(self.tmp, "_local"),
                                                 "CAPCUT_ALPHA_PREMULT": "0"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def patch(self, rgb, alpha, name=None):
        path = os.path.join(self.tmp, name or f"{rgb}-{alpha}.mov")
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x{rgb}@{alpha}:s={W}x{H}:d=0.2:r=30,format=rgba",
             "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-pix_fmt", "yuva444p12le", "-f", "mov", path])
        return path

    def pixel(self, path):
        buf = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba",
                              "-"], capture_output=True, check=True).stdout
        i = ((H // 2) * W + W // 2) * 4
        return tuple(buf[i:i + 4])

    def test_a_midtone_shadow_keeps_its_colour(self):
        """The buyer's plum shadow (110,77,139). Scaling it by its alpha was taken out on 2026-11-01: in real CapCut
        exports the scaled shadow came out too dark, and the plain one matched the look painted on the footage, with
        no halo."""
        r, g, b, a = self.pixel(self.ca.for_capcut(self.patch("6E4D8B", 0.4)))
        self.assertAlmostEqual(a, 102, delta=3)
        self.assertAlmostEqual(b, 139, delta=6, msg=f"plum at 40% keeps its colour, got {(r, g, b, a)}")

    def test_a_faint_glow_sliver_keeps_its_brightness(self):
        """A butter glow's outer sliver: its hue may fade to grey (the rainbow rule), but it never goes dark."""
        r, g, b, a = self.pixel(self.ca.for_capcut(self.patch("FFEB7D", 0.15)))
        self.assertGreaterEqual(max(r, g, b), 235, f"a glow's sliver must not turn into a dark ring, got {(r, g, b, a)}")

    def test_the_measured_case_still_goes_in_straight(self):
        """CapCut, 2026-10-02: white at 35% alpha shows right STRAIGHT, and premultiplied as a dark grey disc."""
        r, g, b, a = self.pixel(self.ca.for_capcut(self.patch("FFFFFF", 0.35)))
        self.assertGreaterEqual(min(r, g, b), 245, f"white type's soft edge stays white, got {(r, g, b, a)}")

    def test_premultiply_everything_is_opt_in_and_cached_apart(self):
        src = self.patch("FFFFFF", 0.35, "opt-in.mov")
        straight = self.ca.for_capcut(src)
        with mock.patch.dict(os.environ, {"CAPCUT_ALPHA_PREMULT": "1"}):
            every = self.ca.for_capcut(src)
        self.assertNotEqual(straight, every, "the opt-in never reuses the straight copy")
        r, g, b, a = self.pixel(every)
        self.assertLessEqual(max(r, g, b), a + 3, f"premultiplied when asked, got {(r, g, b, a)}")

    def test_recipe_moved_so_old_copies_are_redone(self):
        self.assertNotEqual(self.ca.RECIPE, "v5-dark-edges-premult")

    @unittest.skipUnless(HAVE_UV, "needs uv")
    def test_no_numpy_here_uv_brings_it(self):
        with mock.patch.object(self.ca, "_have_numpy", return_value=False), \
             mock.patch.object(self.ca, "_clean_edges", side_effect=AssertionError("must not run in this Python")):
            out = self.ca.for_capcut(self.patch("6E4D8B", 0.4, "via-uv.mov"))
        self.assertNotEqual(out, os.path.join(self.tmp, "via-uv.mov"), "cleaned through uv, not put in as rendered")
        self.assertEqual(self.ca._probe(out)["comment"], self.ca.STRAIGHT_TAG, "the clean really ran")

    def test_no_numpy_and_no_uv_says_so_once_and_logs_it(self):
        src = self.patch("6E4D8B", 0.4, "no-tools.mov")
        printed = []
        with mock.patch.object(self.ca, "_have_numpy", return_value=False), \
             mock.patch.object(self.ca, "_uv", return_value=None), \
             mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
            self.assertEqual(self.ca.for_capcut(src), src, "never a missing layer")
        said = [p for p in printed if "as rendered" in p]
        self.assertEqual(len(said), 1, printed)
        self.assertIn("numpy", said[0])
        with open(os.path.join(self.tmp, "_local", "fallbacks.log"), encoding="utf-8") as f:
            self.assertIn("capcut-alpha: no-tools.mov", f.read())


class LockedForAMoment(unittest.TestCase):
    def test_replace_waits_out_a_brief_lock(self):
        with mock.patch.object(swap.os, "replace", side_effect=[PermissionError(13, "Access is denied"),
                                                                PermissionError(13, "Access is denied"), None]) as rep, \
             mock.patch.object(swap.time, "sleep") as slept:
            swap.replace("a", "b")
        self.assertEqual(rep.call_count, 3)
        self.assertEqual(slept.call_count, 2)

    def test_replace_gives_up_with_the_real_error(self):
        with mock.patch.object(swap.os, "replace", side_effect=PermissionError(13, "Access is denied")), \
             mock.patch.object(swap.time, "sleep"):
            with self.assertRaises(PermissionError):
                swap.replace("a", "b")

    def test_every_swap_in_the_stitch_chain_waits(self):
        for rel in ("product/voice_level.py", "product/clean_cut.py",
                    ".claude/skills/rough-cut/scripts/snap-to-sound.py",
                    ".claude/skills/rough-cut/scripts/close-pauses.py",
                    ".claude/skills/rough-cut/scripts/trim-restarts.py"):
            src = read(rel)
            self.assertNotRegex(src, r"(?m)^[^#\n]*\bos\.replace\(", rel)
        st = read(".claude/skills/rough-cut/scripts/stitch-cut.sh")
        self.assertIn("swap_in(resound, out_path)", st)
        self.assertIn('swap_in(edl_path + ".tmp", edl_path)', st)

    @unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
    def test_voice_level_cleans_up_when_the_cut_stays_locked(self):
        import voice_level
        tmp = tempfile.mkdtemp()
        try:
            cut = os.path.join(tmp, "cut.mp4")
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2:r=30", "-f", "lavfi",
                 "-i", "sine=frequency=300:duration=2", "-af", "volume=-30dB", "-c:v", "libx264", "-c:a", "aac", "-shortest", cut])
            stale = cut + ".level.tmp.mp4"
            open(stale, "w", encoding="utf-8").close()                         # left by an earlier run that hit the lock
            before = sha(cut)
            with mock.patch.object(voice_level, "swap_in", side_effect=PermissionError(13, "Access is denied")):
                r = voice_level.level(cut)
            self.assertFalse(r["changed"])
            self.assertIn("in use", r["why"])
            self.assertFalse(os.path.exists(stale), "no .level.tmp.mp4 left behind")
            self.assertEqual(sha(cut), before, "the cut is whole, as it was")
            r = voice_level.level(cut)                       # the lock gone: leveled
            self.assertTrue(r["changed"], r)
            self.assertFalse(os.path.exists(stale))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
