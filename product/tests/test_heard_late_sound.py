#!/usr/bin/env python3
"""A reel heard before the sound line-up existed, lined up the next time it is cut (a buyer, 2026-10-22).

Engine 2.3.6 heard an iPhone clip whose sound starts 0.7 s after its picture: the words went down on the sound's
clock, the stitch trims on the file's, and the reel came out choppy, a sliver of the word before repeating. 2.3.7
lines such a clip up at intake, but a job heard before that handed its old transcript back and av_sync refused to
touch it, so after the update her re-cut was just as choppy. Now product/av_sync.py `catch_up` lines the clip up
and moves that clip's stored word and cut times by its lead, once, keeping her hand fixes and her cut.

The clip is built for real with ffmpeg (the SoundStartsLate harness in test_buyer_reports_2026_10_21.py): picture
from 0, two tone bursts (her two words) at 0.3 s and 1.2 s of the sound's own clock, which the file places 0.703 s in.

Run: python3 product/tests/test_heard_late_sound.py
"""
import array, hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
W, H = 64, 64
LEAD = 0.703
WORDS = [("hello", 0.3, 0.6), ("there", 1.2, 1.5)]      # where the tone bursts are, on the sound's own clock


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def first_sound(path):
    """Where the first burst starts, in seconds of the file's sound decoded from its start: the transcript's clock."""
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar",
                          "48000", "-"], capture_output=True, check=True).stdout
    samples = array.array("h", pcm)
    return next(i for i, x in enumerate(samples) if abs(x) > 500) / 48000.0


class LateJob:
    """A heard job as 2.3.6 left it: a late clip and a normal one, their words, her cut and its scratch copy."""
    def setUp(self):
        import av_sync
        self.av = av_sync
        self.tmp = tempfile.mkdtemp()
        # the scratch folder the stitch reads (tempfile.gettempdir()) and the fallbacks log, both inside this test
        self._env = mock.patch.dict(os.environ, {"REELS_ENGINE_LOCAL": os.path.join(self.tmp, "_local"),
                                                 "TMPDIR": self.tmp})
        self._env.start()
        self._tempdir = mock.patch.object(tempfile, "tempdir", self.tmp)
        self._tempdir.start()
        self.job = os.path.join(self.tmp, "the-photos-one")
        raw = os.path.join(self.job, "raw")
        os.makedirs(raw)
        v, a = os.path.join(self.tmp, "v.mov"), os.path.join(self.tmp, "a.m4a")
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=red:s={W}x{H}:d=3:r=30", "-c:v", "libx264", v])
        bursts = "+".join(f"between(t,{s},{e})" for _, s, e in WORDS)
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.2",
             "-af", f"volume='if({bursts},1,0)':eval=frame", "-c:a", "aac", a])
        self.late = os.path.join(raw, "IMG_0001.MOV")                  # copied out of Photos: sound 0.703 s late
        run(["ffmpeg", "-v", "error", "-y", "-i", v, "-itsoffset", str(LEAD), "-i", a, "-map", "0:v", "-map", "1:a",
             "-c", "copy", self.late])
        self.ok = os.path.join(raw, "IMG_0002.MOV")                    # a clip already on one clock
        run(["ffmpeg", "-v", "error", "-y", "-i", v, "-i", a, "-map", "0:v", "-map", "1:a", "-c", "copy", self.ok])
        self.wp = os.path.join(self.job, "transcript", "words.json")
        self.cp = os.path.join(self.job, "transcript", "cuts.json")
        self.scratch = os.path.join(self.tmp, "reels-editing-engine", "the-photos-one")
        words = lambda: [{"word": t, "start": s, "end": e, "score": 0.9} for t, s, e in WORDS]
        dump(self.wp, {"clips": [
            {"clip": "IMG_0001.MOV", "path": self.late, "duration": 3.0, "strays_checked": 0, "lead_in_checked": 0,
             "words": words()},
            {"clip": "IMG_0002.MOV", "path": self.ok, "duration": 3.0, "strays_checked": 0, "lead_in_checked": 0,
             "words": words()}]})
        # her cut as 2.3.6 left it: one piece the snap moved (planned on her words), one with her own dragged edges
        self.plan = {"segments": [
            {"clip": "IMG_0001.MOV", "start": 0.95, "end": 1.31, "transcript": "hello",
             "_snapped_from": {"start": 0.26, "end": 0.64}},
            {"clip": "IMG_0001.MOV", "start": 1.18, "end": 1.55, "transcript": "there", "keep_edges": True},
            {"clip": "IMG_0002.MOV", "start": 0.26, "end": 0.64, "transcript": "hello"}]}
        dump(self.cp, self.plan)
        dump(os.path.join(self.scratch, "cuts.json"), self.plan)

    def tearDown(self):
        self._tempdir.stop()
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def history(self):
        h = os.path.join(self.job, "transcript", "history")
        return sorted(os.listdir(h)) if os.path.isdir(h) else []


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class HeardBeforeTheLineUp(LateJob, unittest.TestCase):
    def test_lined_up_and_her_words_and_cut_move_with_it(self):
        before_ok, old_id = sha(self.ok), self.av._sha10(self.wp)
        said = []
        moved = self.av.catch_up(self.job, say=said.append)
        self.assertEqual(list(moved), ["IMG_0001.MOV"], "only the late clip moves")
        lead = moved["IMG_0001.MOV"]
        self.assertAlmostEqual(lead, LEAD, delta=0.04)
        self.assertLess(abs(self.av.audio_lead(self.late)), self.av.LEAD_LIMIT, "the clip itself is lined up")
        self.assertEqual(sha(self.ok), before_ok, "a clip already on one clock is not touched")

        clips = load(self.wp)["clips"]
        late_words, ok_words = clips[0]["words"], clips[1]["words"]
        for (t, s, e), w in zip(WORDS, late_words):
            self.assertAlmostEqual(w["start"], s + lead, places=3)
            self.assertAlmostEqual(w["end"], e + lead, places=3)
            self.assertEqual(w["word"], t, "her words themselves (and any hand fix) are kept")
        self.assertEqual([(w["start"], w["end"]) for w in ok_words], [(s, e) for _, s, e in WORDS])
        self.assertAlmostEqual(clips[0]["sound_lined_up"], lead, places=3)
        self.assertNotIn("sound_lined_up", clips[1])
        # the proof: decoded the way the listener and the snap read it, her first word is now where the words say
        self.assertAlmostEqual(first_sound(self.late), late_words[0]["start"], delta=0.06)

        for path in (self.cp, os.path.join(self.scratch, "cuts.json")):
            segs = load(path)["segments"]
            self.assertAlmostEqual(segs[0]["start"], 0.26 + lead, places=3, msg="snapped: back to its planned edges")
            self.assertAlmostEqual(segs[0]["end"], 0.64 + lead, places=3)
            self.assertAlmostEqual(segs[1]["start"], 1.18 + lead, places=3, msg="her own edges move as they are")
            self.assertAlmostEqual(segs[1]["end"], 1.55 + lead, places=3)
            self.assertTrue(segs[1]["keep_edges"])
            self.assertEqual((segs[2]["start"], segs[2]["end"]), (0.26, 0.64), "the other clip's piece stays")
        self.assertEqual([h.split(".")[0] for h in self.history()], ["cuts", "words"], "both kept before changing")
        rec = load(os.path.join(self.job, "transcript", ".sound-lined-up.json"))
        self.assertEqual(rec["ids"][old_id]["to"], self.av._sha10(self.wp))
        self.assertTrue(any("✓ IMG_0001.MOV" in s for s in said), said)
        with open(os.path.join(self.tmp, "_local", "fallbacks.log"), encoding="utf-8") as f:
            self.assertIn("av-sync: IMG_0001.MOV", f.read(), "logged for /report-a-problem")

    def test_never_moved_twice(self):
        self.av.catch_up(self.job, say=lambda m: None)
        words, cuts, hist = sha(self.wp), sha(self.cp), self.history()
        said = []
        self.assertEqual(self.av.catch_up(self.job, say=said.append, quiet=True), {})
        self.assertEqual(self.av.main([self.job, "--apply", "--quiet"]), 0)
        self.assertEqual((sha(self.wp), sha(self.cp), self.history()), (words, cuts, hist))
        self.assertEqual(said, [], "nothing late, nothing said")

    def test_a_run_cut_off_after_the_swap_finishes_next_time(self):
        lead = self.av.audio_lead(self.late)
        dump(os.path.join(self.job, "transcript", ".sound-lined-up.json"), {"pending": {"IMG_0001.MOV": lead}})
        self.av.line_up(self.late)                                    # lined up, then the run stopped
        plan = dict(self.plan, _sound_lined_up={"IMG_0001.MOV": lead})   # ...after it had moved the saved cut too
        shifted = json.loads(json.dumps(plan))
        self.av.shift_cut(shifted, {"IMG_0001.MOV": lead})            # a no-op: the mark says it was moved
        self.assertEqual(shifted["segments"], self.plan["segments"])
        dump(self.cp, plan)
        moved = self.av.catch_up(self.job, say=lambda m: None)
        self.assertAlmostEqual(moved["IMG_0001.MOV"], lead, places=3)
        self.assertAlmostEqual(load(self.wp)["clips"][0]["words"][0]["start"], 0.3 + lead, places=3)
        self.assertEqual(load(self.cp)["segments"][0]["start"], 0.95, "the saved cut is never moved a second time")
        self.assertAlmostEqual(load(os.path.join(self.scratch, "cuts.json"))["segments"][0]["start"], 0.26 + lead,
                               places=3, msg="the scratch plan it had not reached yet is")
        self.assertEqual(load(os.path.join(self.job, "transcript", ".sound-lined-up.json"))["pending"], {})

    def test_a_clip_that_cannot_be_lined_up_is_said_once_and_left(self):
        words, cuts = sha(self.wp), sha(self.cp)
        said = []
        with mock.patch.object(self.av, "line_up", side_effect=RuntimeError("could not line up the sound of IMG_0001.MOV")):
            self.assertEqual(self.av.catch_up(self.job, say=said.append, quiet=True), {})
            self.assertEqual(self.av.catch_up(self.job, say=said.append, quiet=True), {})
        self.assertEqual(len([s for s in said if "⚠" in s]), 1, said)
        self.assertEqual((sha(self.wp), sha(self.cp)), (words, cuts), "her reel is left exactly as it was")
        with open(os.path.join(self.tmp, "_local", "fallbacks.log"), encoding="utf-8") as f:
            self.assertIn("could not be lined up", f.read())
        os.utime(self.late, (1, 1))                                   # the file changed: tried again
        self.assertIn("IMG_0001.MOV", self.av.catch_up(self.job, say=lambda m: None))

    def test_a_clip_with_no_talking_keeps_its_cut(self):
        data = load(self.wp)
        data["clips"][0].update(silent=True, heard_in_noise=data["clips"][0].pop("words"), words=[])
        dump(self.wp, data)
        moved = self.av.catch_up(self.job, say=lambda m: None)
        lead = moved["IMG_0001.MOV"]
        self.assertAlmostEqual(load(self.wp)["clips"][0]["heard_in_noise"][0]["start"], 0.3 + lead, places=3)
        self.assertEqual(load(self.cp)["segments"], self.plan["segments"], "its pieces are seconds of the file")

    def test_a_your_turn_cut_keeps_her_capcut_edges(self):
        open(os.path.join(self.job, "transcript", ".your-turn-cut"), "w", encoding="utf-8").close()
        lead = self.av.catch_up(self.job, say=lambda m: None)["IMG_0001.MOV"]
        seg = load(self.cp)["segments"][0]
        self.assertAlmostEqual(seg["start"], 0.95 + lead, places=3, msg="her edge, moved as it is, never re-planned")

    def test_main_on_a_heard_job_now_lines_it_up(self):
        self.assertEqual(self.av.main([self.job]), 0)                 # without --apply: says so, changes nothing
        self.assertGreater(self.av.audio_lead(self.late), self.av.LEAD_LIMIT)
        self.assertEqual(self.av.main([self.job, "--apply"]), 0)
        self.assertIn("sound_lined_up", load(self.wp)["clips"][0])

    def test_her_page_from_before_the_line_up_still_sends(self):
        """A cut she sent from a page made on the old transcript: its edges move with her words, never refused."""
        import visual_editor as ve
        old_id = self.av._sha10(self.wp)
        lead = self.av.catch_up(self.job, say=lambda m: None)["IMG_0001.MOV"]
        new_id = self.av._sha10(self.wp)
        self.assertEqual(self.av.moved_since(self.job, old_id, new_id), {"IMG_0001.MOV": round(lead, 4)})
        self.assertEqual(self.av.moved_since(self.job, new_id, new_id), {})
        self.assertIsNone(self.av.moved_since(self.job, "abcdef0123", new_id))
        payload = {"job": "the-photos-one", "id": old_id, "cut": [], "back": [],
                   "trims": {"s": {"0": 0.27}, "e": {}}, "holes": [{"c": 0, "s": 1.25, "e": 1.35}]}
        out = ve.apply_edits(self.job, payload, stitch=False, log=lambda *a: None)
        late = [p for p in out if p["clip"] == "IMG_0001.MOV"]
        self.assertAlmostEqual(late[0]["start"], 0.27 + lead, places=3, msg="her trim, still just before her word")
        self.assertTrue(any(abs(p["end"] - (1.25 + lead)) < 1e-3 for p in late), f"her time cut moved too: {late}")
        with self.assertRaises(ve.Refuse):                            # a page from some other transcript: refused
            ve.apply_edits(self.job, dict(payload, id="abcdef0123"), stitch=False, log=lambda *a: None)


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class WordTimingsHandsBackALinedUpJob(LateJob, unittest.TestCase):
    """The shell road: a re-cut in the chat runs word-timings.sh, which hands a heard job back after catching it up."""

    def test_hand_back_catches_up(self):
        env = dict(os.environ, TMPDIR=self.tmp, REELS_ENGINE_LOCAL=os.path.join(self.tmp, "_local"),
                   REELS_ENGINE_WHISPERX_VENV=os.path.join(self.tmp, "no-venv"),
                   REELS_ENGINE_NOFW_VENV=os.path.join(self.tmp, "no-venv"))
        r = subprocess.run(["bash", os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh"),
                            self.job], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(r.stdout.strip().splitlines()[-1], self.wp, "the job's transcript handed back")
        self.assertIn("✓ IMG_0001.MOV", r.stderr)
        self.assertIn("sound_lined_up", load(self.wp)["clips"][0])
        self.assertLess(abs(__import__("av_sync").audio_lead(self.late)), 0.05)


class Wired(unittest.TestCase):
    def test_every_road_to_a_cut_reaches_it(self):
        wt = read(".claude/skills/rough-cut/scripts/word-timings.sh")
        hb = wt[wt.index("hand_back_if_heard() {"):]
        hb = hb[:hb.index("\n}\n")]
        self.assertIn("catch_up_sound", hb)
        self.assertLess(hb.index("catch_up_sound"), hb.index('cp "$CANON" "$SCRATCH_WORDS"'), "before it is handed back")
        self.assertIn('av_sync.py" "$JOB_DIR" --apply --quiet', wt)
        st = read(".claude/skills/rough-cut/scripts/stitch-cut.sh")
        self.assertIn('av_sync.py" "$JOB_DIR" --apply --quiet', st)
        self.assertLess(st.index("av_sync.py"), st.index('cp "$JOB_DIR/transcript/cuts.json" "$CUTS"'),
                        "before the stitch picks its plan")
        self.assertIn("av_sync.catch_up(jd", read("product/clean_cut.py"))
        ve = read("product/visual_editor.py")
        prep = ve[ve.index("def prepare(job"):ve.index("data = build_script(job)", ve.index("def prepare(job"))]
        self.assertIn("_line_up_sound(jd", prep)
        app = ve[ve.index("def apply(job"):ve.index("def _notes_path")]
        self.assertLess(app.index("_line_up_sound(jd"), app.index("apply_edits(job, payload, stitch=True"))
        self.assertIn("av_sync.moved_since(", ve)
        fin = ve[ve.index("def finish_cut(job"):ve.index("def _bash()")]
        self.assertLess(fin.index("_line_up_sound(jd"), fin.index("already = "), "Finish never reuses a choppy base video")
        self.assertIn("av_sync.py", read(".claude/skills/rough-cut/SKILL.md").split("A reel heard before this")[0][-600:])


if __name__ == "__main__":
    unittest.main()
