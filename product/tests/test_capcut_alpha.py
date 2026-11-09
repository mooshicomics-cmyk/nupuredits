#!/usr/bin/env python3
"""Transparent overlays must reach CapCut as STRAIGHT ProRes 4444 by default, on Mac and Windows.

CapCut composites ProRes 4444 alpha as straight (out = colour x a + under x (1 - a)), measured side by side in real
drafts on 2026-10-02 and again on 2026-10-28 (CapCut 9.5.0: a 60% beige veil, a 35% white patch, a pink glow and a
card shadow; the straight copy matched the reference, the premultiplied copy came out grey with a dark ring).
StraightByDefault locks that default; the Straight and DraftGuardrail classes lock the route itself. A WebM with
transparency loses its alpha in CapCut (clear areas turn black), so it is converted.

CAPCUT_ALPHA_PREMULT=1 premultiplies instead, for a CapCut shown side by side to read premultiplied; the
PremultipliedOptIn class keeps that route working.

This also guards the parts around it: a render goes in as a cleaned copy of the same name (the hue noise in its
faintest edge pixels greyed, so no rainbow ring in CapCut; its real colour and clear pixels kept), the render itself
is never changed, the clean never costs her a layer when it can't run, a copy the old premultiply step made is turned back to straight, a prepared layer is not redone,
and a draft she may have opened is never changed in place.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
TOL = 3          # 8-bit readback through yuva 4:4:4 may round a channel a step or two
W, H = 108, 192
SRC = "color=c=0xFFEB7D@0.84:s={w}x{h}:d=0.4:r=30,format=rgba,pad={W}:{H}:0:0:color=black@0"

if HAVE_FFMPEG:
    import capcut_alpha
    import capcut_media


def _straight(path, audio=False):
    """A straight-alpha ProRes 4444 clip, the way a render arrives: the left half butter yellow at alpha ~214,
    the right half fully clear. QuickTime inside whatever the name says (VectCut copies an overlay in as
    video_<id>.mp4)."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", SRC.format(w=W // 2, h=H, W=W, H=H)]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.4", "-c:a", "pcm_s16le"]
    cmd += ["-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-pix_fmt", "yuva444p12le",
            "-f", "mov", path]
    subprocess.run(cmd, check=True)
    return path


def _old_premultiplied(src, path):
    """What v2.0.18-v2.0.20 wrote: the straight clip premultiplied and tagged."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a?", "-vf",
                    "format=gbrap16le,premultiply=inplace=1,format=yuva444p12le", "-c:v", "prores_ks",
                    "-profile:v", "4444", "-alpha_bits", "16", "-c:a", "copy",
                    "-metadata", f"comment={capcut_alpha.TAG}", "-f", "mov", path], check=True)
    return path


def _webm(path):
    """A transparent VP9 WebM, the way HyperFrames' remove-background writes a cutout."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", SRC.format(w=W // 2, h=H, W=W, H=H),
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "1M", "-auto-alt-ref", "0",
                    "-f", "webm", path], check=True)
    return path


def _pixel(path, x=W // 4):
    """(r, g, b, a) of one pixel on the middle row of the first frame (default: in the coloured half)."""
    buf = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
    i = ((H // 2) * W + x) * 4
    return tuple(buf[i:i + 4])


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _streams(path):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt",
                           "-of", "csv=p=0", path], capture_output=True, text=True).stdout


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class Straight(unittest.TestCase):
    """The CAPCUT_ALPHA_PREMULT=0 route: straight ProRes 4444, only faint and dark edge pixels scaled."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {"REEL_CAPCUT_ALPHA_CACHE": os.path.join(self.tmp, "cache"),
                                                 "CAPCUT_ALPHA_PREMULT": "0"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assertStraight(self, path, ref):
        r, g, b, a = _pixel(path)
        R, G, B, A = ref
        self.assertTrue(0 < a < 255, "must stay semi-transparent")
        self.assertAlmostEqual(a, A, delta=2, msg="alpha itself must not change")
        self.assertGreater(max(r, g, b), a + TOL, f"{(r, g, b, a)}: premultiplied, CapCut shows it dark")
        for c, C in zip((r, g, b), (R, G, B)):
            self.assertAlmostEqual(c, C, delta=6, msg=f"{(r, g, b)} vs the render {(R, G, B)}")
        self.assertEqual(_pixel(path, x=3 * W // 4)[3], 0, "a clear pixel must stay clear")

    def test_a_render_goes_in_as_a_cleaned_copy_of_the_same_name(self):
        for name in ("captions.mov", "video_03202325ff9fd73a.mp4"):
            src = _straight(os.path.join(self.tmp, name))
            before, ref = _sha(src), _pixel(src)
            out = capcut_alpha.for_capcut(src)
            self.assertNotEqual(out, src, name)
            self.assertEqual(os.path.basename(out), name)
            self.assertEqual(_sha(src), before, "the render itself is never changed")
            self.assertFalse(capcut_alpha.needs_preparing(out), "a cleaned copy is not cleaned again")
            for c, C in zip(_pixel(out)[:3], ref[:3]):
                self.assertAlmostEqual(c, C, delta=6, msg="real colour (alpha ~214) is kept")
            self.assertEqual(_pixel(out, x=3 * W // 4)[3], 0, "a clear pixel stays clear")

    def test_faint_edge_hue_noise_is_greyed(self):
        """you 2026-10-18: a rainbow ring around every card in CapCut, from random hues at alpha <= 16/255."""
        src = os.path.join(self.tmp, "shadow.mov")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"color=c=0xFF0000@0.03:s={W}x{H}:d=0.2:r=30,format=rgba", "-c:v", "prores_ks",
                        "-profile:v", "4444", "-alpha_bits", "16", "-pix_fmt", "yuva444p12le", "-f", "mov", src], check=True)
        r, g, b, a = _pixel(capcut_alpha.for_capcut(src))
        self.assertLess(a, capcut_alpha.EDGE_A, "fixture must be a faint pixel")
        self.assertLessEqual(max(r, g, b) - min(r, g, b), 6, f"a faint pixel's hue is noise: grey it, got {(r, g, b)}")

    def test_a_long_layer_with_faint_edges_finishes(self):
        """you 2026-10-23: her export froze at 0% CPU in this step. The Finish bar's frame counter shared a name with
        the edge blend's array, so the first faint frame past 15 raised, and the loop then waited on a decoder still
        blocked writing a full pipe. A layer with faint edges well past 15 frames must come out whole, its frame count
        reported to the bar, and a failure mid-loop must end both ffmpegs rather than hang."""
        import threading
        src = os.path.join(self.tmp, "long-edges.mov")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"color=c=0xFFEB7D@0.04:s={W}x{H}:d=2:r=30,format=rgba", "-c:v", "prores_ks",
                        "-profile:v", "4444", "-alpha_bits", "16", "-pix_fmt", "yuva444p12le", "-f", "mov", src], check=True)
        import export_progress
        said = []
        got = {}

        def go():
            with mock.patch.object(export_progress, "inner", side_effect=lambda f: said.append(f)):
                got["rc"] = capcut_alpha._clean_edges(src, os.path.join(self.tmp, "long-out.mov"))
        t = threading.Thread(target=go, daemon=True)
        t.start(); t.join(60)
        self.assertFalse(t.is_alive(), "the edge clean hung on a layer with faint edges past 15 frames")
        self.assertEqual(got.get("rc", (1,))[0], 0, f"it should finish cleanly, got {got}")
        self.assertTrue(said and 0 < said[-1] <= 1.0 and said == sorted(said), f"frames counted for the bar, got {said}")

        def boom(f):
            raise RuntimeError("mid-loop failure")
        got.clear()

        def fail():
            with mock.patch.object(export_progress, "inner", side_effect=boom):
                try:
                    capcut_alpha._clean_edges(src, os.path.join(self.tmp, "long-out2.mov"))
                except RuntimeError as e:
                    got["err"] = str(e)
        t = threading.Thread(target=fail, daemon=True)
        t.start(); t.join(60)
        self.assertFalse(t.is_alive(), "a failure mid-loop must end both ffmpegs, never wait on a full pipe")
        self.assertEqual(got.get("err"), "mid-loop failure")

    def test_a_soft_look_keeps_its_brightness(self):
        """you 2026-11-01, measured in her real CapCut exports: scaling soft pixels by their alpha put a dark halo
        round glows and veils, so a faint or mid-tone colour keeps its brightness. Only a faint pixel's hue goes."""
        for colour, floor in (("0xFFFFFF@0.10", 245), ("0xFFFFFF@0.5", 245), ("0x6E4D8B@0.40", 70)):
            src = os.path.join(self.tmp, "soft.mov")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                            f"color=c={colour}:s={W}x{H}:d=0.2:r=30,format=rgba", "-c:v", "prores_ks",
                            "-profile:v", "4444", "-alpha_bits", "16", "-pix_fmt", "yuva444p12le", "-f", "mov", src], check=True)
            got = _pixel(capcut_alpha.for_capcut(src))
            self.assertGreaterEqual(min(got[:3]), floor, f"{colour} darkened to {got}")
            os.remove(src)

    def test_a_hard_edge_keeps_its_colour(self):
        """you 2026-11-01: type in CapCut had choppy edges, like a bad background removal. The soft-shadow rules were
        darkening the smoothing pixels on the edge of type and shapes. A pixel with a jump in alpha beside it is an
        edge, whatever its alpha and however dark its colour: it keeps its colour. A soft fade is still greyed."""
        for colour, edge_a in (((0, 122, 255), 100), ((255, 255, 255), 30)):
            row = bytearray()
            for x in range(W):                                # clear, one edge pixel on the middle column, solid
                row += bytes(colour) + bytes([0 if x < W // 4 else edge_a if x == W // 4 else 255])
            src = os.path.join(self.tmp, f"edge-{edge_a}.mov")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                            "-r", "30", "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16",
                            "-pix_fmt", "yuva444p12le", "-f", "mov", src], input=bytes(row) * H * 6, check=True)
            ref = _pixel(src)
            self.assertAlmostEqual(ref[3], edge_a, delta=2, msg="fixture: the pixel under test is the edge")
            got = _pixel(capcut_alpha.for_capcut(src))
            self.assertAlmostEqual(got[3], ref[3], delta=2, msg="alpha itself must not change")
            for c, C in zip(got[:3], ref[:3]):
                self.assertAlmostEqual(c, C, delta=6, msg=f"edge pixel darkened: {got} vs the render {ref}")
        import numpy as np
        step = 5 * 257.0                                      # a shadow's slow fade: 5/255 a pixel is no edge
        fade = np.tile(np.arange(0, 40, dtype=np.float32) * step, (8, 1))
        self.assertFalse(capcut_alpha._hard_edge(fade).any(), "a soft fade must stay under the shadow rules")

    def test_the_clean_never_costs_a_layer(self):
        src = _straight(os.path.join(self.tmp, "layer.mov"))
        with mock.patch.object(capcut_alpha, "_clean_edges", side_effect=RuntimeError("no numpy here")):
            self.assertEqual(capcut_alpha.for_capcut(src), src, "can't clean: the render goes in as it is")

    def test_old_premultiplied_copy_is_turned_back_to_straight(self):
        src = _straight(os.path.join(self.tmp, "render.mov"))
        old = _old_premultiplied(src, os.path.join(self.tmp, "video_17c7880777128018.mp4"))
        self.assertIs(capcut_alpha.straight_evidence(old), False, "fixture must be premultiplied")
        out = capcut_alpha.for_capcut(old)
        self.assertNotEqual(out, old)
        self.assertEqual(os.path.basename(out), "video_17c7880777128018.mp4", "the material path must not move")
        self.assertFalse(capcut_alpha.is_tagged(out))
        self.assertStraight(out, _pixel(src))
        with mock.patch.object(capcut_alpha, "prepare", side_effect=AssertionError("prepared twice")):
            self.assertEqual(capcut_alpha.for_capcut(old), out, "an unchanged layer is prepared once")
            self.assertEqual(capcut_alpha.for_capcut(out), out, "a prepared copy is left as it is")

    def test_transparent_webm_becomes_straight_prores(self):
        """CapCut drops VP9 alpha (everything clear turns black), so a cutout WebM is converted."""
        web = _webm(os.path.join(self.tmp, "cutout.webm"))
        self.assertTrue(capcut_alpha.needs_preparing(web), "a WebM's alpha hides in a side channel: probe it")
        out = capcut_alpha.for_capcut(web)
        self.assertNotEqual(out, web)
        self.assertIn("prores", _streams(out))
        self.assertIn("yuva444p", _streams(out))
        ref = _pixel(_straight(os.path.join(self.tmp, "ref.mov")))
        r, g, b, a = _pixel(out)
        self.assertAlmostEqual(a, ref[3], delta=4, msg="the WebM's alpha must survive")
        self.assertGreater(max(r, g, b), a + TOL, "converted straight, not premultiplied")
        self.assertEqual(_pixel(out, x=3 * W // 4)[3], 0, "clear must stay clear, not black")

    def test_sound_on_a_transparent_clip_survives(self):
        src = _straight(os.path.join(self.tmp, "with_sound.mov"), audio=True)
        out = capcut_alpha.for_capcut(_old_premultiplied(src, os.path.join(self.tmp, "video_with_sound.mp4")))
        self.assertIn("audio", _streams(out), "preparing must not silently drop the clip's sound")

    def test_render_itself_is_never_changed(self):
        src = _straight(os.path.join(self.tmp, "r.mov"))
        old = _old_premultiplied(src, os.path.join(self.tmp, "old.mov"))
        before = _sha(old)
        capcut_alpha.for_capcut(old)
        self.assertEqual(_sha(old), before)

    def test_stills_and_opaque_clips_are_untouched(self):
        png = os.path.join(self.tmp, "sticker.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"color=c=0xFFEB7D@0.5:s={W}x{H}:d=0.04,format=rgba", "-frames:v", "1", png], check=True)
        mov = os.path.join(self.tmp, "footage.mov")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=red:s={W}x{H}:d=0.4",
                        "-c:v", "prores_ks", "-profile:v", "2", mov], check=True)
        web = os.path.join(self.tmp, "opaque.webm")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=red:s={W}x{H}:d=0.4",
                        "-c:v", "libvpx-vp9", "-b:v", "200k", web], check=True)
        for f in (png, mov, web):
            before = _sha(f)
            self.assertEqual(capcut_alpha.for_capcut(f), f, f)
            self.assertEqual(_sha(f), before)


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class DraftGuardrail(unittest.TestCase):
    """capcut_media.ensure_shippable is the one place every finalized draft passes through."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {"REEL_CAPCUT_ALPHA_CACHE": os.path.join(self.tmp, "cache"),
                                                 "CAPCUT_ALPHA_PREMULT": "0"})
        self._env.start()
        self.D = os.path.join(self.tmp, "draft")
        os.makedirs(os.path.join(self.D, "assets", "video"))
        with open(os.path.join(self.D, "draft_meta_info.json"), "w", encoding="utf-8") as f:
            json.dump({"draft_materials": []}, f)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _draft(self, path):
        return {"materials": {"videos": [{"id": "m1", "path": path}], "audios": []},
                "tracks": [{"type": "video", "segments": [{"material_id": "m1"}]}]}

    def test_render_in_a_fresh_draft_gets_its_edges_cleaned_in_place(self):
        local = _straight(os.path.join(self.D, "assets", "video", "video_17c7880777128018.mp4"))
        ref = _pixel(local)
        self.assertEqual(capcut_media.ensure_shippable(self._draft(local), self.D, fresh=True), [])
        self.assertFalse(capcut_alpha.needs_preparing(local), "the draft's own copy is the cleaned one")
        for c, C in zip(_pixel(local)[:3], ref[:3]):
            self.assertAlmostEqual(c, C, delta=6)

    def test_old_premultiplied_asset_in_a_fresh_draft_is_restored(self):
        ref = _pixel(_straight(os.path.join(self.tmp, "render.mov")))
        local = _old_premultiplied(os.path.join(self.tmp, "render.mov"),
                                   os.path.join(self.D, "assets", "video", "video_aa.mp4"))
        d = self._draft(local)
        self.assertEqual(capcut_media.ensure_shippable(d, self.D, fresh=True), [])
        self.assertTrue(os.path.isfile(local), "same name, same material")
        self.assertFalse(capcut_alpha.is_tagged(local))
        r, g, b, a = _pixel(local)
        self.assertGreater(max(r, g, b), a + TOL)
        self.assertAlmostEqual(a, ref[3], delta=2)
        once = _sha(local)
        self.assertEqual(capcut_media.ensure_shippable(d, self.D, fresh=True), [])
        self.assertEqual(_sha(local), once, "a second finalize pass must leave it alone")

    def test_webm_cutout_copied_in_from_outside(self):
        web = _webm(os.path.join(self.tmp, "cutout.webm"))
        before = _sha(web)
        d = self._draft(web)
        self.assertEqual(capcut_media.ensure_shippable(d, self.D), [])
        local = os.path.join(self.D, "assets", "video", "cutout.mov")
        self.assertTrue(os.path.isfile(local), "the converted cutout is QuickTime and named .mov")
        self.assertTrue(d["materials"]["videos"][0]["path"].endswith("/assets/video/cutout.mov"))
        self.assertIn("yuva444p", _streams(local))
        self.assertEqual(_pixel(local, x=3 * W // 4)[3], 0, "clear must stay clear, not black")
        self.assertEqual(_sha(web), before)

    def test_a_draft_she_may_have_opened_is_not_changed_in_place(self):
        local = _old_premultiplied(_straight(os.path.join(self.tmp, "r.mov")),
                                   os.path.join(self.D, "assets", "video", "layer.mov"))
        before = _sha(local)
        self.assertEqual(capcut_media.ensure_shippable(self._draft(local), self.D), [])
        self.assertEqual(_sha(local), before, "a media change on an opened draft belongs in a new version")


class Wiring(unittest.TestCase):
    """Every route into a draft passes through the transparency step; the bake does not."""

    def src(self, name):
        with open(os.path.join(PRODUCT, name), encoding="utf-8") as f:
            return f.read()

    def test_fresh_builds_prepare_inside_the_draft(self):
        for f in ("cleanyap.py", "superyap.py"):
            self.assertIn("ensure_shippable(d, D, fresh=True)", self.src(f), f)

    def test_superyap_prepares_alpha_before_the_draft_is_written(self):
        src = self.src("superyap.py")
        fix = src.index("ensure_shippable(d, D, fresh=True)")
        write = src.index("json.dump(d, open(p,", fix)
        self.assertLess(fix, write, "the transparency pass must run before the draft JSON is written")

    def test_writers_that_skip_finalize_prepare_it_themselves(self):
        for f in ("build-overlay.py", "capcut-slip-reel.py"):
            self.assertIn("capcut_alpha.for_capcut(", self.src(f), f)

    def test_the_bake_reads_straight_alpha_untouched(self):
        for f in ("build-reel-mp4.py", "reel_render.py"):
            self.assertNotIn("capcut_alpha", self.src(f), f)

    def test_straight_is_the_default_on_every_platform(self):
        """No env var (or an empty or 0 one) means straight; only an explicit 1/true/yes/on premultiplies. Nothing
        in the module branches on the platform, so Mac and Windows take the same route."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAPCUT_ALPHA_PREMULT", None)
            self.assertFalse(capcut_alpha.premult_all(), "unset must mean straight")
            for v, want in (("", False), ("0", False), ("off", False), ("1", True), ("on", True), ("true", True)):
                os.environ["CAPCUT_ALPHA_PREMULT"] = v
                self.assertIs(capcut_alpha.premult_all(), want, repr(v))
        src = self.src("capcut_alpha.py")
        for plat in ("sys.platform", "platform.system", "os.name =="):
            self.assertNotIn(plat, src.split("def _uv")[0], "the alpha route must not depend on the platform")


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class PremultipliedOptIn(unittest.TestCase):
    """The CAPCUT_ALPHA_PREMULT=1 route, for a CapCut shown side by side to composite premultiplied (out = colour +
    (1 - a) x under). A buyer's 60% beige veil (245,244,233 at alpha 154) drawn that way from a straight file reads
    white over a dark desk, so on this route every layer goes in premultiplied and draws the intended ~162."""

    VEIL = "F5F4E9"          # 245,244,233: her paper veil
    A = 154 / 255.0          # 60%
    UNDER = 37               # the dark desk under it (from her numbers: 162 = 0.6 x 245 + 0.4 x under)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {"REEL_CAPCUT_ALPHA_CACHE": os.path.join(self.tmp, "cache"),
                                                 "CAPCUT_ALPHA_PREMULT": "1"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def veil(self, name="video_77f954fcaa454881.mp4", comment=None):
        path = os.path.join(self.tmp, name)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
               f"color=c=0x{self.VEIL}@{self.A:.4f}:s={W // 2}x{H}:d=0.2:r=30,format=rgba,pad={W}:{H}:0:0:color=black@0",
               "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-pix_fmt", "yuva444p12le"]
        if comment:
            cmd += ["-metadata", f"comment={comment}"]
        subprocess.run(cmd + ["-f", "mov", path], check=True)
        return path

    def capcut_draws(self, path):
        """What CapCut puts on screen over the desk: colour + (1 - a) x under, clipped (premultiplied compositing)."""
        r, g, b, a = _pixel(path)
        return tuple(min(255, round(c + (1 - a / 255.0) * self.UNDER)) for c in (r, g, b)), a

    def assertLooksRight(self, path):
        (r, g, b), a = self.capcut_draws(path)
        want = [round(int(self.VEIL[i:i + 2], 16) * self.A + (1 - self.A) * self.UNDER) for i in (0, 2, 4)]
        self.assertAlmostEqual(a, 154, delta=2, msg="the veil's alpha itself must not change")
        for got, w in zip((r, g, b), want):
            self.assertAlmostEqual(got, w, delta=6, msg=f"CapCut draws {(r, g, b)}, the veil should read {want}")
        self.assertLessEqual(max(_pixel(path)[:3]), a + TOL, "premultiplied: colour never exceeds alpha")
        self.assertEqual(_pixel(path, x=3 * W // 4)[3], 0, "a clear pixel must stay clear")

    def test_her_veil_from_a_fresh_render(self):
        src = self.veil()
        before = _sha(src)
        self.assertGreaterEqual(min(self.capcut_draws(src)[0]), 245, "fixture: handed over straight, it is white")
        out = capcut_alpha.for_capcut(src)
        self.assertNotEqual(out, src)
        self.assertEqual(os.path.basename(out), os.path.basename(src), "the material name must not move")
        self.assertEqual(_sha(src), before, "the render itself is never changed")
        self.assertTrue(capcut_alpha.is_tagged(out), "tagged premultiplied")
        self.assertLooksRight(out)
        with mock.patch.object(capcut_alpha, "prepare", side_effect=AssertionError("prepared twice")):
            self.assertEqual(capcut_alpha.for_capcut(src), out, "an unchanged layer is prepared once")
            self.assertEqual(capcut_alpha.for_capcut(out), out, "a premultiplied copy is never premultiplied again")

    def test_her_straight_tagged_clip_is_not_skipped(self):
        """Her clip carried comment capcut-alpha:straight, so v2.3.15 called it ready and passed it over."""
        src = self.veil(comment=capcut_alpha.STRAIGHT_TAG)
        self.assertTrue(capcut_alpha.needs_preparing(src))
        self.assertLooksRight(capcut_alpha.for_capcut(src))

    def test_her_clip_inside_a_fresh_draft_is_fixed_in_place(self):
        D = os.path.join(self.tmp, "draft")
        os.makedirs(os.path.join(D, "assets", "video"))
        with open(os.path.join(D, "draft_meta_info.json"), "w", encoding="utf-8") as f:
            json.dump({"draft_materials": []}, f)
        local = self.veil(name=os.path.join("draft", "assets", "video", "video_77f954fcaa454881.mp4"),
                          comment=capcut_alpha.STRAIGHT_TAG)
        d = {"materials": {"videos": [{"id": "m1", "path": local}], "audios": []},
             "tracks": [{"type": "video", "segments": [{"material_id": "m1"}]}]}
        self.assertEqual(capcut_media.ensure_shippable(d, D, fresh=True), [])
        self.assertLooksRight(local)
        once = _sha(local)
        self.assertEqual(capcut_media.ensure_shippable(d, D, fresh=True), [])
        self.assertEqual(_sha(local), once, "a second finalize pass must leave it alone")

    def test_no_numpy_still_premultiplies(self):
        """When the numpy edge clean can't run on this computer, ffmpeg premultiplies: never a straight layer."""
        src = self.veil(name="layer.mov")
        with mock.patch.object(capcut_alpha, "_clean_edges", side_effect=RuntimeError("no numpy here")), \
                mock.patch.object(capcut_alpha, "_have_numpy", return_value=True):
            out = capcut_alpha.for_capcut(src)
        self.assertNotEqual(out, src, "the layer must not go in straight")
        self.assertLooksRight(out)

    def test_webm_cutout_becomes_premultiplied_prores(self):
        web = _webm(os.path.join(self.tmp, "cutout.webm"))
        out = capcut_alpha.for_capcut(web)
        self.assertIn("prores", _streams(out))
        r, g, b, a = _pixel(out)
        self.assertTrue(0 < a < 255)
        self.assertLessEqual(max(r, g, b), a + TOL, f"premultiplied, got {(r, g, b, a)}")
        self.assertEqual(_pixel(out, x=3 * W // 4)[3], 0, "clear must stay clear, not black")

    def test_the_old_premultiplied_copy_is_kept_as_it_is(self):
        old = _old_premultiplied(_straight(os.path.join(self.tmp, "r.mov")), os.path.join(self.tmp, "old.mov"))
        self.assertFalse(capcut_alpha.needs_preparing(old))
        self.assertEqual(capcut_alpha.for_capcut(old), old)

    def test_straight_opt_out_still_works(self):
        src = self.veil(name="opt-out.mov")
        with mock.patch.dict(os.environ, {"CAPCUT_ALPHA_PREMULT": "0"}):
            straight = capcut_alpha.for_capcut(src)
        self.assertGreater(max(_pixel(straight)[:3]), _pixel(straight)[3] + TOL, "straight when she opts out")
        self.assertNotEqual(straight, capcut_alpha.for_capcut(src), "the two routes are cached apart")


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg + ffprobe")
class StraightByDefault(unittest.TestCase):
    """2026-10-28 side by side on CapCut 9.5.0: the straight copy of a 60% beige veil, a 35% white patch, a pink glow
    and a card shadow matched the reference; the premultiplied copy was grey and muddy. With no env var set (what
    every buyer has), a render goes in straight, and a copy the premultiplied route made is turned back."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {"REEL_CAPCUT_ALPHA_CACHE": os.path.join(self.tmp, "cache")})
        self._env.start()
        os.environ.pop("CAPCUT_ALPHA_PREMULT", None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def veil(self, name):
        return PremultipliedOptIn.veil(self, name=name)

    VEIL, A = PremultipliedOptIn.VEIL, PremultipliedOptIn.A

    def test_a_light_veil_goes_in_straight(self):
        out = capcut_alpha.for_capcut(self.veil("veil.mov"))
        r, g, b, a = _pixel(out)
        self.assertAlmostEqual(a, 154, delta=2, msg="the veil's alpha itself must not change")
        self.assertGreater(min(r, g, b), a + TOL, f"straight: the veil keeps its full colour, got {(r, g, b, a)}")
        self.assertFalse(capcut_alpha.is_tagged(out), "never tagged premultiplied by default")

    def test_a_premultiplied_copy_is_turned_back_to_straight(self):
        src = self.veil("pm-src.mov")
        with mock.patch.dict(os.environ, {"CAPCUT_ALPHA_PREMULT": "1"}):
            pm = capcut_alpha.for_capcut(src)
        self.assertTrue(capcut_alpha.is_tagged(pm))
        moved = os.path.join(self.tmp, "pm-copy.mov")
        shutil.copy(pm, moved)
        back = capcut_alpha.for_capcut(moved)
        r, g, b, a = _pixel(back)
        self.assertGreater(min(r, g, b), a + TOL, f"turned back to straight, got {(r, g, b, a)}")


if __name__ == "__main__":
    unittest.main()
