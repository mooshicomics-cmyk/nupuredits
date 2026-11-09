# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "pillow-heif", "opencv-python-headless", "numpy",
#   "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]
# ///
#!/usr/bin/env python3
"""Carousel engine: packs, fonts, type fitting, layout rules, photo crops, and a real export when Chrome is here.

Run: uv run workflows/carousel/tests/test_carousel.py   (the export tests also need Chrome, Edge or the HyperFrames browser)
"""
import importlib.util, json, os, random, re, shutil, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAROUSEL = HERE.parent
ENGINE = CAROUSEL.parent.parent


def load(simulate_buyer=True):
    """A fresh copy of carousel.py. Buyer mode by default: tests must pass on a machine without licensed fonts."""
    os.environ["CAROUSEL_SIMULATE_BUYER"] = "1" if simulate_buyer else "0"
    spec = importlib.util.spec_from_file_location("carousel_ut", CAROUSEL / "carousel.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def plan(points=3):
    slides = [{"role": "hook", "eyebrow": "how i'd", "headline": "launch big online", "support": "in 3 steps..."},
              {"role": "reframe", "headline": "now i'm doing it.", "support": "here's the proof..."},
              {"role": "proof", "eyebrow": "in 48 hours", "number": "$250,000", "label": "from one launch."}]
    heads = ["listen.", "your tech stack.", "automate everything.", "rest.", "repeat it every single week."]
    slides += [{"role": "point", "eyebrow": f"step {i + 1}", "headline": heads[i], "support": "one idea."} for i in range(points)]
    slides += [{"role": "turn", "line": "you don't need to know how.\nyou need to know what to say."},
               {"role": "closer", "intro": "hey.", "lead": "comment", "action": "launch", "support": "free kit."}]
    return {"keyword": "LAUNCH", "slides": slides, "caption": "comment LAUNCH for the kit."}


def story_plan():
    return {"format": "story", "keyword": "LAUNCH", "slides": [
        {"role": "hook", "headline": "ok i have to tell you what happened this week"},
        {"role": "text", "line": "have you ever wanted to launch something online?", "bg": "color",
         "sticker": {"type": "poll", "options": ["yes", "not yet"]}},
        {"role": "proof", "number": "$250,000", "label": "in 48 hours."},
        {"role": "ask", "lead": "i wrote it all down.", "action": "LAUNCH", "support": "and i'll send it to you"}]}


class Packs(unittest.TestCase):
    def setUp(self): self.c = load()

    def test_fonts_come_from_the_style_pack(self):
        """Every carousel font is the pack's own element font (or that element's own stand-in), so a pack the
        creator builds herself carries over with no carousel setup."""
        sys.path.insert(0, str(ENGINE / "product")); import stylepack
        for pack in self.c.packs():
            P = stylepack.load(pack); els = P["elements"]
            want = {"CDisp": els["headline"]["font"], "CBody": els["caption"]["font"], "CTurn": els["thought_bubble"]["font"],
                    "CEye": P.get("subhead_font_name") or els["accent_caption"]["font"]}
            got = {fam: f["name"] for fam, f in self.c.resolve_fonts(pack).items()}
            self.assertEqual(got, want, pack)

    def test_buyer_never_gets_a_licensed_file(self):
        for pack in self.c.packs():
            for fam, f in self.c.resolve_fonts(pack).items():
                self.assertTrue(Path(f["path"]).exists(), f"{pack} {fam}")
                self.assertTrue(self.c.ships(Path(f["path"]).name), f"{pack} {fam} uses licensed {f['path']}")

    def test_every_pack_defines_every_variable_the_css_uses(self):
        used = set(re.findall(r"var\(--([a-z-]+)\)", (CAROUSEL / "editor" / "slide.css").read_text())) - {"ov", "sh"}
        for pack in self.c.packs():
            self.assertEqual(used - set(self.c.theme(pack)["vars"]), set(), pack)

    def test_buyer_mode_reports_stand_ins(self):
        standins = {fam for fam, f in self.c.resolve_fonts("Playful").items() if f["standin"]}
        self.assertTrue({"CDisp", "CTurn"} <= standins)


class Type(unittest.TestCase):
    def setUp(self): self.c = load()

    def test_headlines_fit_the_safe_width(self):
        for pack in self.c.packs():
            for text in ["automate everything.", "supercalifragilistic", "a b c d e f g h i j k l m n o p"]:
                size, lines = self.c.fit(text, pack, 150, 3)
                self.assertLessEqual(self.c.wrap(text, pack, size, self.c.TEXT_W * .97)[1], self.c.TEXT_W * .97, (pack, text))

    def test_fit_respects_max_lines_and_never_grows(self):
        size, lines = self.c.fit("now i'm doing it.", "Butter", 150, 1)
        self.assertEqual(len(lines), 1); self.assertLessEqual(size, 150)

    def test_forced_line_breaks_are_kept(self):
        self.assertEqual(self.c.wrap("we're\ncapable.", "Butter", 100, 900)[0], ["we're", "capable."])


class Rules(unittest.TestCase):
    def setUp(self): self.c = load()

    def test_kind_matrix(self):
        k = self.c.kind_for
        self.assertEqual([k(r, "mix", True) for r in ("hook", "proof", "point", "turn", "closer")],
                         ["photo", "card", "photo", "card", "photo"])
        self.assertEqual({k(r, "photo", True) for r in self.c.ROLES}, {"photo"})
        self.assertEqual(k("hook", "graphic", True), "ground")
        self.assertEqual(k("hook", "photo", False), "ground")     # no photos at all: never an empty photo slide

    def test_validate_names_the_slide(self):
        bad = {"slides": [{"role": "hook"}, {"role": "proof"}, {"role": "nope"}]}
        with self.assertRaises(SystemExit) as e: self.c.validate(bad)
        for want in ("slide 1 (hook) needs headline", "slide 2 (proof) needs number or screenshot", "slide 3: role"):
            self.assertIn(want, str(e.exception))

    def test_lint(self):
        self.assertEqual(self.c.lint(plan()), [])
        p = plan(); p["caption"] = "no keyword — here"; p["slides"].append(dict(p["slides"][-1]))
        for s in p["slides"][:4]: s["support"] = "more..."
        flags = " | ".join(self.c.lint(p))
        for want in ("em dash", "end in '...'", "exactly one closer", "keyword LAUNCH"): self.assertIn(want, flags)


class Crops(unittest.TestCase):
    def setUp(self): self.c = load()

    def covers(self, c):
        s = c["scale"]
        return (c["w"] * s >= self.c.W - .5 and c["h"] * s >= self.c.H - .5
                and -.5 <= c["x"] <= c["w"] * s - self.c.W + .5 and -.5 <= c["y"] <= c["h"] * s - self.c.H + .5)

    def test_place_face_never_leaves_a_gap(self):
        rng = random.Random(7)
        for _ in range(500):
            w, h = rng.choice([(1365, 2048), (3024, 4032), (2048, 1365), (1080, 1350)])
            cover = max(self.c.W / w, self.c.H / h)
            c = {"w": w, "h": h, "scale": cover * rng.uniform(1, 1.4), "x": 0, "y": 0,
                 "fc": [rng.uniform(0, w), rng.uniform(0, h), rng.uniform(50, h / 3)]}
            self.c.place_face(c, rng.uniform(-200, self.c.H + 200))
            self.assertTrue(self.covers(c), c)


class Build(unittest.TestCase):
    """End to end in a scratch engine folder, every pack x look, buyer fonts only."""
    def setUp(self):
        from PIL import Image
        self.c = load(); self.tmp = Path(tempfile.mkdtemp()); self.c.ENGINE = self.tmp
        self.c.face_of = lambda path: None                       # keep the test free of the face model
        self.job = "ut-job"; d = self.c.cdir(self.job); (d / "photos").mkdir(parents=True)
        for n in ("a", "b", "c"): Image.new("RGB", (1365, 2048), (120, 90, 80)).save(d / "photos" / f"{n}.jpg")
        (d / "plan.json").write_text(json.dumps({**plan(), "photos": ["a.jpg", "b.jpg", "c.jpg"]}))

    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_pack_and_look(self):
        for pack in self.c.packs():
            for look in ("photo", "graphic", "mix"):
                self.c.cmd_build(self.job, pack, look)
                st = json.loads((self.c.cdir(self.job) / "carousel.json").read_text())
                self.assertEqual(len(st["slides"]), len(plan()["slides"]))
                if look == "graphic": self.assertNotIn("photo", {s["kind"] for s in st["slides"]})
                sizes = {re.search(r"class='d' style='font-size:(\d+)px", s["content"]).group(1)
                         for s in st["slides"] if s["role"] == "point"}
                self.assertEqual(len(sizes), 1, f"{pack}/{look}: points must share one headline size")
                for s in st["slides"]:
                    if s["kind"] == "photo": self.assertTrue(Crops.covers(self, s["crop"]))

    def test_her_text_size_and_spacing(self):
        """plan.json body_boost / eye_boost / hook_support_size / headline_line_height / eyebrow_gap change the
        carousel's text (two buyers' Claudes hand-added these, 2026-10-19); left out, it builds exactly as before."""
        def build(**extra):
            p = {**plan(), "photos": ["a.jpg", "b.jpg", "c.jpg"], **extra}
            (self.c.cdir(self.job) / "plan.json").write_text(json.dumps(p))
            self.c.cmd_build(self.job, "Butter", "graphic")
            return json.loads((self.c.cdir(self.job) / "carousel.json").read_text())
        sizes = lambda st, cls: [int(x) for s in st["slides"] for x in re.findall(r"class='" + cls + r"' style='font-size:(\d+)px", s["content"])]
        plain = build()
        self.assertNotIn("eye-gap", plain["theme"]["vars"])
        boosted = build(body_boost=1.3, eye_boost=1.2, headline_line_height=0.88, eyebrow_gap=8, eyebrow_line_height=1.0)
        for a, b in zip(sizes(plain, "b"), sizes(boosted, "b")):
            self.assertAlmostEqual(b / a, 1.3, delta=0.03)
        for a, b in zip(sizes(plain, "eye"), sizes(boosted, "eye")):
            self.assertAlmostEqual(b / a, 1.2, delta=0.03)
        v = boosted["theme"]["vars"]
        self.assertEqual((v["disp-lh"], v["eye-gap"], v["eye-lh"]), ("0.88", "8px", "1.0"))
        hook = lambda st: next(s["content"] for s in st["slides"] if s["role"] == "hook")
        sup = build(hook_support_size=70)
        self.assertGreater(int(re.findall(r"class='b' style='font-size:(\d+)px", hook(sup))[0]),
                           int(re.findall(r"class='b' style='font-size:(\d+)px", hook(plain))[0]))
        self.assertEqual(build(body_boost=9)["theme"]["vars"].get("eye-gap"), None)   # out of range is held, not refused
        self.assertEqual(sizes(build(), "b"), sizes(plain, "b"))                       # and the next plain build is plain again
        css = (CAROUSEL / "editor" / "slide.css").read_text()
        self.assertIn("var(--eye-gap,22px)", css); self.assertIn("var(--eye-lh,1.05)", css)

    def test_missing_photo_is_a_clear_error(self):
        p = json.loads((self.c.cdir(self.job) / "plan.json").read_text()); p["photos"] = ["nope.jpg"]
        (self.c.cdir(self.job) / "plan.json").write_text(json.dumps(p))
        with self.assertRaises(SystemExit) as e: self.c.cmd_build(self.job, "Butter", "mix")
        self.assertIn("nope.jpg", str(e.exception))

    def test_exports_follow_the_engine_export_folder(self):
        self.c.cmd_build(self.job, "Butter", "mix")
        os.environ["REELS_EXPORT_DIR"] = str(self.tmp / "exports")
        try: self.assertEqual(self.c.delivery_dir(self.job), self.tmp / "exports" / "ut-job-carousel")
        finally: del os.environ["REELS_EXPORT_DIR"]

    def test_bad_job_name_is_refused(self):
        with self.assertRaises(SystemExit): self.c.cdir("../escape")

    def test_real_export(self):
        try: self.c.chrome()
        except SystemExit: self.skipTest("no Chrome or Edge on this machine")
        from PIL import Image
        p = json.loads((self.c.cdir(self.job) / "plan.json").read_text())
        p["slides"] = p["slides"][:2] + p["slides"][-1:]; (self.c.cdir(self.job) / "plan.json").write_text(json.dumps(p))
        self.c.cmd_build(self.job, "Editorial", "mix"); self.c.cmd_render(self.job, "jpg")
        out = self.c.cdir(self.job) / "slides"
        self.assertEqual(sorted(f.name for f in out.iterdir()), ["slide-1.jpg", "slide-2.jpg", "slide-3.jpg"])
        for f in out.iterdir(): self.assertEqual(Image.open(f).size, (1080, 1350))
        self.assertTrue((self.c.cdir(self.job) / "beat-sheet.jpg").exists())

        # the layout check must catch a font file that is really gone (and only that one)
        sp = self.c.cdir(self.job) / "carousel.json"; st = json.loads(sp.read_text())
        st["theme"]["fonts"]["CTurn"] = str(self.tmp / "gone.ttf"); sp.write_text(json.dumps(st))
        srv = self.c.serve(self.job, port := self.c.free_port())
        try: rep = self.c.check(self.job, port)
        finally: srv.shutdown()
        self.assertEqual(rep["missing_fonts"], ["CTurn"])


class Story(unittest.TestCase):
    """The Story Kit: 1080x1920 frames, words inside Instagram's safe zone, sticker spaces never exported."""
    def setUp(self):
        from PIL import Image
        self.c = load(); self.tmp = Path(tempfile.mkdtemp()); self.c.ENGINE = self.tmp
        self.c.face_of = lambda path: None
        self.job = "ut-story"; d = self.c.cdir(self.job); (d / "photos").mkdir(parents=True)
        for n in ("a", "b"): Image.new("RGB", (1365, 2048), (120, 90, 80)).save(d / "photos" / f"{n}.jpg")
        (d / "plan.json").write_text(json.dumps({**story_plan(), "photos": ["a.jpg", "b.jpg"]}))

    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def test_validate_and_lint(self):
        self.c.validate(story_plan()); self.assertEqual(self.c.lint(story_plan()), [])
        bad = story_plan(); bad["slides"].append({"role": "ask", "action": "MORE"}); bad["slides"][0]["headline"] = "word " * 30
        flags = " | ".join(self.c.lint(bad))
        self.assertIn("one ask", flags); self.assertIn("words", flags)
        with self.assertRaises(SystemExit): self.c.validate({"format": "story", "slides": [{"role": "point", "headline": "x"}]})

    def test_posting_notes_read_the_frames_even_after_editing(self):
        st = {"format": "story", "keyword": "LAUNCH", "manychat": True, "dm": "here it is",
              "slides": [{"content": "<div class='mid'>hi</div>"},
                         {"content": self.c.sticker({"type": "poll", "options": ["yes", "no"]})},
                         # the editor's browser rewrites markup with double quotes and inline styles
                         {"content": '<div class="stk question" style="translate: 4px 0px"><b>Question box goes here</b><small>(not in the export)</small></div>'}]}
        notes = " | ".join(self.c.posting_notes(st))
        for want in ("frame 1 first", "Frame 2: add a poll sticker", "(yes / no)", "Frame 3: add a question box sticker", "ManyChat", "LAUNCH"):
            self.assertIn(want, notes)
        self.assertNotIn("not in the export", notes)

    def test_every_pack_style_and_background(self):
        for pack in self.c.packs():
            for style in ("native", "pack"):
                for bg in ("photo", "color"):
                    self.c.cmd_build(self.job, pack, "mix", style, bg)
                    st = json.loads((self.c.cdir(self.job) / "carousel.json").read_text())
                    self.assertEqual((st["format"], st["size"]["h"]), ("story", 1920))
                    self.assertIn("class='stk poll'", st["slides"][1]["content"])
                    for sl in st["slides"]:
                        if sl["kind"] == "photo": self.assertGreaterEqual(sl["crop"]["h"] * sl["crop"]["scale"], 1920 - .5)

    def test_export_leaves_sticker_spaces_out(self):
        try: self.c.chrome()
        except SystemExit: self.skipTest("no Chrome or Edge on this machine")
        from PIL import Image, ImageStat
        self.c.cmd_build(self.job, "Butter", "mix", "pack", "color"); self.c.cmd_render(self.job, "jpg")
        out = self.c.cdir(self.job) / "slides"
        self.assertEqual(Image.open(out / "slide-1.jpg").size, (1080, 1920))
        srv = self.c.serve(self.job, port := self.c.free_port())
        try: rep = self.c.check(self.job, port)
        finally: srv.shutdown()
        self.assertEqual([f for s in rep["slides"] for f in s["flags"]], [], "words or sticker spaces under Instagram's buttons")
        # where the dashed poll space sits in the editor, the exported frame is plain background
        frame = Image.open(out / "slide-2.jpg").convert("L")
        bands = [frame.crop((240, y, 840, y + 40)) for y in range(1000, 1500, 40)]
        self.assertGreater(sum(ImageStat.Stat(b).stddev[0] < 2 for b in bands), 3, "the sticker outline was exported")


if __name__ == "__main__":
    unittest.main(verbosity=2)
