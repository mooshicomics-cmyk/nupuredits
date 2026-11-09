#!/usr/bin/env python3
"""Never a dead end at the review steps: the beat sheet, the sandbox and the style plan.

22. The beat sheet with no Node: stills without the graphics layers (remembered as beat-sheet.no-node, forgotten
    once Node is back), a hung snapshot (not remembered), no ffmpeg (black frames), and a missing font file.
23. No Pillow, or the stills breaking anywhere after the beats are read: the text beat sheet (beat-sheet.md)
    and a TEXT BEAT SHEET line, so her approval step still happens. A broken single-image sheet keeps the page.
24. The sandbox: a layer that will not render is left out (never rendered the same way twice), a layer with no
    index.html is left out, no Node hands back the beat's still, and a render is only stopped when it goes quiet.
25. The style plan: "JOB" in her words or the job name stays as written, a damaged sections file only costs the
    tags, and a widget that will not build becomes the lean table with a marker line.
26. The preview link without ffprobe: the link, without its length.

Stand-ins only (fake subprocess results, monkeypatched modules, temp dirs): nothing renders, nothing touches
the real _local/ (REELS_ENGINE_LOCAL points at a scratch folder).

Run: python3 product/tests/test_fallbacks_review.py
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
JOB_J = "j"   # the stand-in job the style-plan link tests name
PRODUCT = os.path.join(ROOT, "product")
SKILL = os.path.join(ROOT, ".claude", "skills", "beat-sheet", "scripts")
sys.path.insert(0, PRODUCT)

import npx_run   # noqa: E402

LOCAL = tempfile.mkdtemp(prefix="fb-review-local-")
os.environ["REELS_ENGINE_LOCAL"] = LOCAL
import fallbacks   # noqa: E402
from PIL import Image, ImageFont   # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def log_text():
    try:
        return open(fallbacks.log_path(), encoding="utf-8").read()
    except OSError:
        return ""


def reset_local():
    for f in ("fallbacks.log", "pivots.json"):
        try:
            os.remove(os.path.join(LOCAL, f))
        except OSError:
            pass


@contextlib.contextmanager
def patched(obj, **attrs):
    old = {k: getattr(obj, k) for k in attrs}
    for k, v in attrs.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


def run_main(mod, argv):
    out = io.StringIO()
    with patched(sys, argv=argv), contextlib.redirect_stdout(out):
        mod.main()
    return out.getvalue()


class FakeRun:
    """Stands in for subprocess.run: ffmpeg writes a real frame, npx does whatever the test says."""

    def __init__(self, npx=None, ffmpeg="ok"):
        self.npx, self.ffmpeg, self.calls = npx, ffmpeg, []

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        if argv[0] == "ffmpeg":
            if self.ffmpeg == "missing":
                raise FileNotFoundError("ffmpeg")
            Image.new("RGB", (540, 960), "#336699").save(argv[-1])
            return subprocess.CompletedProcess(argv, 0, "", "")
        if self.npx == "hang":
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
        if self.npx == "unread-video":                      # HyperFrames' own words, with every still saved
            out = argv[argv.index("-o") + 1]
            os.makedirs(out, exist_ok=True)
            times = argv[argv.index("--at") + 1].split(",")
            for i, _ in enumerate(times):
                Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(os.path.join(out, f"frame-{i:02d}.png"))
            return subprocess.CompletedProcess(argv, 1, "", f"✗ {len(times)} video frame(s) could not be read, so those "
                                               f"videos are black or stale in the snapshots saved to {out}.")
        return subprocess.CompletedProcess(argv, 1, "", "snapshot failed")


class BeatSheetCase(unittest.TestCase):
    def setUp(self):
        reset_local()
        self.bs = load("beat_sheet_under_test", os.path.join(SKILL, "beat-sheet.py"))
        self.root = tempfile.mkdtemp(prefix="fb-review-root-")
        self.job = "the-test-one"
        jd = os.path.join(self.root, "projects", self.job)
        os.makedirs(os.path.join(jd, "outputs"))
        os.makedirs(os.path.join(jd, "beat-sheet"))
        os.makedirs(os.path.join(jd, "hf-layer"))
        open(os.path.join(jd, "outputs", f"{self.job}.mp4"), "wb").close()
        with open(os.path.join(jd, "hf-layer", "index.html"), "w", encoding="utf-8") as fh:
            fh.write('<div data-duration="20"></div>')
        self.spec = {"layers": [{"dir": "hf-layer"}],
                     "beats": [{"t": 1.5, "kind": "hook", "says": "the JOB i left", "motion": "pops in"},
                               {"t": 4.0, "kind": "captions", "says": "read-along", "motion": "word by word",
                                "mock": [{"role": "caption", "text": "read along"}]}]}
        self.write_spec()
        self.sheet_dir = os.path.join(jd, "beat-sheet")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_spec(self):
        with open(os.path.join(self.root, "projects", self.job, "beat-sheet", "beats.json"), "w", encoding="utf-8") as fh:
            json.dump(self.spec, fh)

    def go(self, fake, npx="/usr/local/bin/npx"):
        with patched(self.bs, ROOT=self.root), patched(self.bs.subprocess, run=fake), \
                patched(npx_run, npx_path=lambda: npx):
            return run_main(self.bs, ["beat-sheet.py", self.job])


class Row22BeatSheetNoNode(BeatSheetCase):
    def test_22_no_node_makes_stills_without_the_layer_and_remembers(self):
        fake = FakeRun()
        out = self.go(fake, npx=None)
        self.assertIn("graphics layers are not on these stills", out)
        self.assertTrue(os.path.exists(os.path.join(self.sheet_dir, "beats", "01.jpg")))
        self.assertTrue(os.path.exists(os.path.join(self.sheet_dir, "beat-sheet.html")))
        self.assertNotIn("TEXT BEAT SHEET", out)
        self.assertFalse(any(c[0][0] != "ffmpeg" for c in fake.calls), "npx must not be tried without Node")
        self.assertIn("beat-sheet: Node (npx) is missing", log_text())
        self.assertTrue(fallbacks.remembered("beat-sheet.no-node"))
        self.assertEqual(out.count("graphics layers are not on these stills"), 1)

    def test_22_node_back_forgets_the_pivot(self):
        fallbacks.remember("beat-sheet.no-node", True, "test")
        out = self.go(FakeRun())
        self.assertIsNone(fallbacks.remembered("beat-sheet.no-node"))
        self.assertIn("✓ beat sheet", out)

    def test_22_hung_snapshot_leaves_the_layer_off_and_is_not_remembered(self):
        fake = FakeRun(npx="hang")
        out = self.go(fake)
        self.assertIn("left off these stills", out)
        self.assertIn("✓ beat sheet", out)
        self.assertIn("snapshot of", log_text())
        self.assertIsNone(fallbacks.remembered("beat-sheet.no-node"))
        npx_calls = [kw for argv, kw in fake.calls if argv[0] != "ffmpeg"]
        self.assertTrue(npx_calls and npx_calls[0].get("timeout", 0) >= 300)

    def test_22_an_unreadable_video_keeps_the_stills_and_says_so(self):
        out = self.go(FakeRun(npx="unread-video"))
        self.assertIn("could not be read, so it shows black or out of date", out)
        self.assertNotIn("could not take stills", out)
        self.assertIn("✓ beat sheet", out)
        self.assertIn("its stills were kept", log_text())

    def test_22_a_snapshot_that_failed_any_other_way_leaves_the_layer_off(self):
        out = self.go(FakeRun())
        self.assertIn("could not take stills", out)
        self.assertIn("✓ beat sheet", out)

    def test_22_no_ffmpeg_draws_on_black(self):
        fake = FakeRun(ffmpeg="missing")
        out = self.go(fake)
        self.assertIn("ffmpeg is not on this computer", out)
        self.assertEqual(out.count("ffmpeg is not on this computer"), 1)
        self.assertTrue(os.path.exists(os.path.join(self.sheet_dir, "beats", "02.jpg")))
        self.assertIn("ffmpeg is not installed", log_text())

    def test_22_ffmpeg_gets_nostdin_and_a_timeout(self):
        fake = FakeRun()
        self.go(fake)
        argv, kw = next(c for c in fake.calls if c[0][0] == "ffmpeg")
        self.assertIn("-nostdin", argv)
        self.assertTrue(kw.get("timeout"))

    def test_22_missing_font_falls_back_to_a_bundled_face(self):
        f = self.bs.font("/nowhere/NoSuchFont.ttf", 50)
        self.assertEqual(getattr(f, "size", None), 50)

    def test_22_old_pillow_default_font_has_no_size(self):
        class Bitmap:   # old Pillow's default: a bitmap face with no .size
            pass

        def old_default(*a, **kw):
            if kw or a:
                raise TypeError("load_default() takes no arguments")
            return Bitmap()

        def no_truetype(*a, **kw):
            raise OSError("cannot open resource")

        with patched(ImageFont, truetype=no_truetype, load_default=old_default):
            f = self.bs.font("/nowhere/x.ttf", 58)
        self.assertIsInstance(f, Bitmap)
        self.assertEqual(self.bs.size_of(f, 58), 58)


class Row23TextBeatSheet(BeatSheetCase):
    def test_23_no_pillow_gives_the_text_beat_sheet(self):
        with patched(self.bs, Image=None):
            out = self.go(FakeRun())
        self.assertIn("TEXT BEAT SHEET", out)
        md = open(os.path.join(self.sheet_dir, "beat-sheet.md"), encoding="utf-8").read()
        self.assertIn("| 1 | 0:01.5 | hook | the JOB i left | pops in |", md)
        self.assertIn("beat-sheet: Pillow is not installed", log_text())

    def test_23_a_crash_in_the_stills_gives_the_text_beat_sheet(self):
        def boom(*a, **kw):
            raise RuntimeError("draw broke")
        with patched(self.bs, stamp=boom):
            out = self.go(FakeRun())
        self.assertIn("TEXT BEAT SHEET", out)
        self.assertTrue(os.path.exists(os.path.join(self.sheet_dir, "beat-sheet.md")))
        self.assertIn("the stills broke (RuntimeError: draw broke)", log_text())

    def test_23_contact_sheet_crash_keeps_the_page(self):
        def boom(*a, **kw):
            raise MemoryError("too big")
        with patched(self.bs, contact_sheet=boom):
            out = self.go(FakeRun())
        self.assertIn("page (the beat sheet", out)
        self.assertNotIn("fallback image", out)
        self.assertNotIn("TEXT BEAT SHEET", out)
        self.assertTrue(os.path.exists(os.path.join(self.sheet_dir, "beat-sheet.html")))
        self.assertIn("single-image sheet broke", log_text())

    def test_23_markdown_is_written_before_the_stills(self):
        seen = {}

        def look(*a, **kw):
            seen["md"] = os.path.exists(os.path.join(self.sheet_dir, "beat-sheet.md"))
            raise RuntimeError("stop")
        with patched(self.bs, legend_height=look):
            self.go(FakeRun())
        self.assertTrue(seen.get("md"))


class Row24Sandbox(unittest.TestCase):
    def setUp(self):
        reset_local()
        self.sb = load("sandbox_under_test", os.path.join(SKILL, "sandbox.py"))
        self.root = tempfile.mkdtemp(prefix="fb-review-sb-")
        self.job = "sb-job"
        jd = self.jd = os.path.join(self.root, "projects", self.job)
        os.makedirs(os.path.join(jd, "outputs"))
        os.makedirs(os.path.join(jd, "beat-sheet", "beats"))
        open(os.path.join(jd, "outputs", f"{self.job}.mp4"), "wb").close()
        for d in ("good", "bad"):
            os.makedirs(os.path.join(jd, d))
            open(os.path.join(jd, d, "index.html"), "w", encoding="utf-8").close()
        os.makedirs(os.path.join(jd, "empty"))   # no index.html
        self.spec = {"layers": [{"dir": "bad"}, {"dir": "good"}],
                     "beats": [{"t": 3.0, "kind": "hook"}, {"t": 9.0, "kind": "card"}]}
        self.write_spec()
        self.renders = []
        self.ffmpeg = []

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_spec(self):
        with open(os.path.join(self.jd, "beat-sheet", "beats.json"), "w", encoding="utf-8") as fh:
            json.dump(self.spec, fh)

    def fake_render(self, comp, out):
        self.renders.append(os.path.basename(comp.rstrip(os.sep)) if "span-" not in comp else "span:" + comp)
        if "/bad" in comp or comp.endswith("bad") or "span-0" in comp:
            raise RuntimeError("render failed")
        open(out, "wb").close()

    def fake_run(self, argv, **kw):
        self.ffmpeg.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def go(self, window=(None, 0.0, None), npx="/usr/local/bin/npx", argv=None):
        with patched(self.sb, ROOT=self.root, render=self.fake_render, layer_window=lambda comp, a, b: window,
                     npx_path=lambda: npx), patched(self.sb.subprocess, run=self.fake_run):
            return run_main(self.sb, argv or ["sandbox.py", self.job, "--beat", "1"])

    def test_24_whole_layer_failing_is_dropped_not_rendered_twice(self):
        out = self.go()
        self.assertEqual(self.renders.count("bad"), 1)
        self.assertIn("bad would not render", out)
        self.assertIn("✓ sandbox", out)
        stack = self.ffmpeg[-1]
        self.assertEqual(stack.count("-i"), 2)   # her cut + the one good layer
        self.assertIn("sandbox: bad would not render", log_text())

    def test_24_span_then_whole_failing_is_dropped(self):
        def span_comp(comp, out_dir, a, b):
            os.makedirs(out_dir, exist_ok=True)
            return out_dir
        with patched(self.sb.RS, span_comp=span_comp):
            out = self.go(window=((0, 30), 0.0, 1.0))
        self.assertIn("rendering it whole", out)
        self.assertIn("bad would not render", out)
        self.assertEqual(self.renders.count("bad"), 1)   # the one whole try after the span try

    def test_24_missing_index_html_skips_the_layer(self):
        self.spec["layers"] = [{"dir": "empty"}, {"dir": "good"}]
        self.write_spec()
        with patched(self.sb, ROOT=self.root, render=self.fake_render, npx_path=lambda: "/x/npx"), \
                patched(self.sb.RS, read_clips=lambda html: None), patched(self.sb.subprocess, run=self.fake_run):
            out = run_main(self.sb, ["sandbox.py", self.job, "--beat", "1"])
        self.assertIn("empty has no index.html", out)
        self.assertIn("✓ sandbox", out)
        self.assertIn("no index.html", log_text())

    def test_24_no_node_hands_back_the_still(self):
        Image.new("RGB", (10, 10)).save(os.path.join(self.jd, "beat-sheet", "beats", "01.jpg"))
        out = self.go(npx=None)
        self.assertIn("01.jpg", out)
        self.assertIn("No moving preview this time", out)
        self.assertEqual(self.renders, [])
        self.assertIn("sandbox: Node (npx) is missing", log_text())

    def test_24_no_node_and_no_still_stops_with_the_node_message(self):
        with self.assertRaises(SystemExit) as cm:
            self.go(npx=None)
        self.assertIn("Node is not installed", str(cm.exception))

    def test_24_every_layer_failing_hands_back_the_still(self):
        Image.new("RGB", (10, 10)).save(os.path.join(self.jd, "beat-sheet", "beats", "01.jpg"))
        self.spec["layers"] = [{"dir": "bad"}]
        self.write_spec()
        out = self.go()
        self.assertIn("none of this moment's graphics layers would render", out)
        self.assertEqual(self.ffmpeg, [])

    def _script(self, body):
        p = os.path.join(self.root, "fake-render.py")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return p

    def test_24_a_quiet_render_is_stopped(self):
        script = self._script("import time\ntime.sleep(60)\n")
        out = os.path.join(self.root, "x.mov")
        t0 = time.monotonic()
        with patched(self.sb, STALL=3, npx_argv=lambda *a: [sys.executable, script]):
            with self.assertRaises(RuntimeError) as cm:
                self.sb.render("comp", out)
        self.assertIn("went quiet", str(cm.exception))
        self.assertLess(time.monotonic() - t0, 30)

    def test_24_a_render_still_counting_frames_is_never_stopped(self):
        script = self._script(
            "import sys, time\n"
            "for i in range(5):\n"
            "    print(f'Streaming frame {i}/5', flush=True); time.sleep(1.5)\n"
            "open(sys.argv[-1], 'wb').close()\n")
        out = os.path.join(self.root, "y.mov")
        with patched(self.sb, STALL=3, npx_argv=lambda *a: [sys.executable, script, *a]):
            self.sb.render("comp", out)   # 7.5 s of work, never quiet for 3 s: must finish
        self.assertTrue(os.path.exists(out))


class Row25StylePlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsp = load("build_style_plan_under_test", os.path.join(PRODUCT, "build-style-plan.py"))

    def setUp(self):
        reset_local()
        self.jd = tempfile.mkdtemp(prefix="fb-review-sp-")
        os.makedirs(os.path.join(self.jd, "transcript"))

    def tearDown(self):
        shutil.rmtree(self.jd, ignore_errors=True)

    def cuts(self, segs):
        with open(os.path.join(self.jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump({"segments": segs}, fh)

    def test_25_job_in_her_words_and_in_the_job_name_stays(self):
        self.cuts([{"start": 0, "end": 2, "transcript": "i quit my JOB"},
                   {"start": 2, "end": 4, "transcript": "literally __SEGS__ and __JOB__"}])
        w = self.bsp.build(self.jd, "my-JOB-reel")
        self.assertIn('"i quit my JOB"', w)
        self.assertIn("i quit my JOB", w)
        self.assertIn("literally __SEGS__ and __JOB__", w)
        self.assertIn('id="sp-my-JOB-reel"', w)
        self.assertIn("style-plan:my-JOB-reel:", w)
        tpl = self.bsp._TEMPLATE
        self.assertNotIn("JOB", tpl.replace("__JOB__", ""), "every JOB in the template is the __JOB__ token")

    def test_25_damaged_sections_file_costs_only_the_tags(self):
        self.cuts([{"start": 0, "end": 2, "transcript": "hello"}])
        with open(os.path.join(self.jd, "transcript", "style-plan-sections.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            w = self.bsp.build(self.jd, "j")
        self.assertIn("hello", w)
        self.assertIn("without section tags", err.getvalue())
        self.assertIn("style-plan: style-plan-sections.json would not read", log_text())

    def test_25_widget_crash_gives_the_lean_table_and_a_marker(self):
        self.cuts([{"start": 0, "end": 2.5, "transcript": 5}, {"start": 3, "end": 4, "transcript": "two"}])
        env = dict(os.environ, REELS_ENGINE_LOCAL=LOCAL)
        for flags in ([], ["-O"]):
            r = subprocess.run([sys.executable, *flags, os.path.join(PRODUCT, "build-style-plan.py"), self.jd,
                                "--job", "j"], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("STYLE PLAN TABLE INSTEAD OF THE WIDGET", r.stderr)
            self.assertIn("| 1 | 5 | 2.5s |", r.stdout)
            self.assertIn("| 2 | two | 1.0s |", r.stdout)
            self.assertIn("total: 0:04", r.stdout)
        self.assertIn("style-plan: the widget would not build", log_text())

    def test_25_missing_cuts_json_still_stops(self):
        with self.assertRaises(OSError):
            self.bsp.build(self.jd, "j")


class Row26PreviewLink(unittest.TestCase):
    def setUp(self):
        reset_local()
        self.spl = load("style_plan_link_under_test", os.path.join(PRODUCT, "style_plan_link.py"))
        self.root = tempfile.mkdtemp(prefix="fb-review-link-")
        os.makedirs(os.path.join(self.root, "projects", "j", "outputs"))
        open(os.path.join(self.root, "projects", "j", "outputs", "j.mp4"), "wb").close()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def emit_with(self, run):
        with patched(self.spl, ROOT=self.root), patched(self.spl.subprocess, run=run):
            return self.spl.emit("j")

    def test_26_no_ffprobe_gives_the_link_without_length(self):
        def missing(*a, **kw):
            raise FileNotFoundError("ffprobe")
        link = self.emit_with(missing)
        self.assertEqual(link, f"▶ [j.mp4](projects/{JOB_J}/outputs/j.mp4)")
        self.assertIn("style-plan-link: ffprobe is not installed", log_text())

    def test_26_unreadable_mp4_or_hang_gives_the_link_without_length(self):
        def garbage(argv, **kw):
            self.assertTrue(kw.get("timeout"))
            return subprocess.CompletedProcess(argv, 1, "", "moov atom not found")

        def hang(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
        self.assertEqual(self.emit_with(garbage), f"▶ [j.mp4](projects/{JOB_J}/outputs/j.mp4)")
        self.assertEqual(self.emit_with(hang), f"▶ [j.mp4](projects/{JOB_J}/outputs/j.mp4)")
        self.assertNotIn("ffprobe is not installed", log_text())

    def test_26_with_ffprobe_the_length_is_there(self):
        ok = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "78.4\n", "")
        self.assertEqual(self.emit_with(ok), f"▶ [j.mp4](projects/{JOB_J}/outputs/j.mp4) — 1:18")

    def test_26_build_style_plan_prints_the_link_when_ffprobe_is_missing(self):
        # End to end through build-style-plan.py with an empty PATH (no ffprobe anywhere). The job has to live
        # under the real engine's projects/ for the link to resolve, so it is made and removed here.
        made_projects = not os.path.isdir(os.path.join(ROOT, "projects"))
        job = f"_fb-review-test-{os.getpid()}"
        jd = os.path.join(ROOT, "projects", job)
        try:
            os.makedirs(os.path.join(jd, "transcript"))
            os.makedirs(os.path.join(jd, "outputs"))
            open(os.path.join(jd, "outputs", f"{job}.mp4"), "wb").close()
            with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
                json.dump({"segments": [{"start": 0, "end": 1, "transcript": "hi"}]}, fh)
            empty = tempfile.mkdtemp(prefix="fb-review-path-")
            env = dict(os.environ, PATH=empty, REELS_ENGINE_LOCAL=LOCAL)
            r = subprocess.run([sys.executable, os.path.join(PRODUCT, "build-style-plan.py"), jd],
                               capture_output=True, text=True, env=env)
            shutil.rmtree(empty, ignore_errors=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"▶ [{job}.mp4](projects/{job}/outputs/{job}.mp4)", r.stderr)
        finally:
            shutil.rmtree(jd, ignore_errors=True)
            if made_projects:
                try:
                    os.rmdir(os.path.join(ROOT, "projects"))   # only if nothing else landed in it meanwhile
                except OSError:
                    pass


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(LOCAL, ignore_errors=True)
