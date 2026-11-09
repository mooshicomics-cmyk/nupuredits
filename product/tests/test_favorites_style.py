#!/usr/bin/env python3
""""Learn this style, start incorporating it": a CapCut reel she loves becomes how her builds animate.

The course teaches the phrase, so it has to do what the card says for every buyer: read the project she
named without touching it, fold its text animations into the builds (including CapCut animations the editor
engine has no name for, swapped in at finalize), set her sound density, and never touch her sounds shelf or
a stand-in animation a reel asked for on purpose.
"""
import importlib.util, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "product", f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


POP_UP_ID = "7145435451946439170"          # in the editor engine's catalog (intro)
CHEEKY_ID = "7527870705392717057"          # a newer CapCut animation the engine has no name for


def _text(mid, text, size):
    content = {"styles": [{"fill": {"content": {"solid": {"color": [1, 0.8, 0]}}}, "size": size,
                           "font": {"path": "/fonts/MyHook.ttf"}}], "text": text}
    return {"id": mid, "content": json.dumps(content)}


class LearnStyle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cap = os.path.join(self.tmp, "drafts")
        self.fav = _load("favorites")
        self.fav.ds.CAP = self.cap
        self.fav.ROOT = os.path.join(self.tmp, "engine")
        self.fav.LOCAL = os.path.join(self.fav.ROOT, "_local")
        self.fav.SOUNDS = os.path.join(self.fav.LOCAL, "sounds")
        self.fav.STATE = os.path.join(self.fav.LOCAL, "favorites.json")
        import learned
        self.learned = learned
        self._store = learned.STORE
        learned.STORE = os.path.join(self.tmp, "learned.json")
        self.anim_file = os.path.join(self.tmp, "cache", "effect", CHEEKY_ID, "abc")
        os.makedirs(os.path.dirname(self.anim_file))
        with open(self.anim_file, "w", encoding="utf-8") as fh:
            fh.write("x")

    def tearDown(self):
        self.learned.STORE = self._store
        shutil.rmtree(self.tmp, ignore_errors=True)

    def loved_reel(self, name="my best reel", seconds=20, sounds=4):
        d = os.path.join(self.cap, name); os.makedirs(d)
        texts = [_text("t0", "the hook", 40), _text("t1", "an aside", 18), _text("t2", "another", 18)]
        anims = [
            {"id": "g0", "animations": [{"id": POP_UP_ID, "type": "in", "name": "Pop Up", "resource_id": POP_UP_ID,
                                         "path": "/nowhere", "duration": 500000, "start": 0}]},
            {"id": "g1", "animations": [{"id": CHEEKY_ID, "type": "out", "name": "Cheeky Bounce",
                                         "resource_id": CHEEKY_ID, "path": self.anim_file, "duration": 400000,
                                         "start": 0, "request_id": "r1", "category_name": "Favorites"}]},
            {"id": "g2", "animations": [{"id": CHEEKY_ID, "type": "out", "name": "Cheeky Bounce",
                                         "resource_id": CHEEKY_ID, "path": self.anim_file, "duration": 400000,
                                         "start": 0}]},
        ]
        tsegs = [{"material_id": f"t{i}", "extra_material_refs": [f"g{i}"],
                  "target_timerange": {"start": [0, 5_000_000, 9_000_000][i]}} for i in range(3)]
        asegs = [{"material_id": f"a{i}", "target_timerange": {"start": i * 1_000_000}} for i in range(sounds)]
        info = {"duration": seconds * 1_000_000,
                "materials": {"texts": texts, "material_animations": anims,
                              "audios": [{"id": f"a{i}", "type": "sound"} for i in range(sounds)]},
                "tracks": [{"type": "text", "segments": tsegs}, {"type": "audio", "segments": asegs}]}
        with open(os.path.join(d, self.fav.ds.draft_json_name(d)), "w", encoding="utf-8") as fh:
            json.dump(info, fh)
        return d

    def test_folds_in_placeable_and_newer_animations(self):
        self.loved_reel()
        msg, code = self.fav.learn_style("my best reel")
        self.assertEqual(code, 0, msg)
        self.assertEqual(self.fav.style_animation("hook", "in"), "Pop_Up")          # named directly
        self.assertEqual(self.fav.style_animation("text", "out"), "Fade_Out")       # stand-in for Cheeky Bounce
        self.assertTrue(self.fav.style_needs_swap("text", "out"))
        self.assertIn("Cheeky Bounce", msg)

    def test_sound_density_is_taught(self):
        self.loved_reel(seconds=20, sounds=8)      # 4 per 10s -> heavier
        self.fav.learn_style("my best reel")
        self.assertEqual(self.learned.get("sfx.density", "normal"), "heavier")

    def test_shelf_untouched(self):
        self.fav.save({"draft": "shelf", "sounds": [{"name": "pop", "file": "_local/sounds/pop.mp3", "seconds": 0.3}],
                       "rules": ["no whooshes"]})
        self.loved_reel()
        self.fav.learn_style("my best reel")
        st = self.fav.load()
        self.assertEqual(st["draft"], "shelf")
        self.assertEqual(st["rules"], ["no whooshes"])
        self.assertEqual(len(st["sounds"]), 1)

    def test_swap_only_touches_text_the_build_animated(self):
        self.loved_reel()
        self.fav.learn_style("my best reel")
        built = {"materials": {
                     "texts": [{"id": "x0", "content": json.dumps({"text": "my aside"})},
                               {"id": "x1", "content": json.dumps({"text": "asked for fade"})}],
                     "material_animations": [
                         {"id": "h0", "animations": [{"type": "out", "name": "Fade Out", "start": 0}]},
                         {"id": "h1", "animations": [{"type": "out", "name": "Fade Out", "start": 0}]}]},
                 "tracks": [{"type": "text", "segments": [
                     {"material_id": "x0", "extra_material_refs": ["h0"]},
                     {"material_id": "x1", "extra_material_refs": ["h1"]}]}]}
        n = self.fav.apply_style_swaps(built, {"my aside": "text"})
        self.assertEqual(n, 1)
        swapped = built["materials"]["material_animations"][0]["animations"][0]
        self.assertEqual(swapped["name"], "Cheeky Bounce")
        self.assertEqual(swapped["resource_id"], CHEEKY_ID)
        self.assertNotIn("request_id", swapped)
        self.assertEqual(built["materials"]["material_animations"][1]["animations"][0]["name"], "Fade Out")

    def test_missing_cache_is_left_out_not_faked(self):
        self.loved_reel()
        os.remove(self.anim_file)
        msg, _ = self.fav.learn_style("my best reel")
        self.assertIsNone(self.fav.style_animation("text", "out"))
        self.assertIn("Cheeky Bounce", msg)

    def test_forget_style(self):
        self.loved_reel()
        self.fav.learn_style("my best reel")
        st = self.fav.load(); st.pop("style"); self.fav.save(st)
        self.assertIsNone(self.fav.style_animation("hook", "in"))

    def test_unknown_project(self):
        os.makedirs(self.cap)
        msg, code = self.fav.learn_style("nope")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
