#!/usr/bin/env python3
"""The favorites project: the sounds she puts on the shelf become the sounds the engine reaches for.

The course teaches this step by name ("study my CapCut draft called my sound palette"), so it has to
work the same way for every buyer: find the project, take only the sounds she picked (never the
footage's own audio, never a music track), make them resolvable by the engine, and keep her rules.
"""
import importlib.util, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))


def _touch(path):
    with open(path, "wb") as fh:
        fh.write(b"x")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "product", f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Favorites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cap = os.path.join(self.tmp, "drafts"); self.cache = os.path.join(self.tmp, "cache")
        os.makedirs(self.cache)
        self.fav = _load("favorites")
        self.fav.ds.CAP = self.cap
        self.fav.ROOT = os.path.join(self.tmp, "engine")
        self.fav.LOCAL = os.path.join(self.fav.ROOT, "_local")
        self.fav.SOUNDS = os.path.join(self.fav.LOCAL, "sounds")
        self.fav.STATE = os.path.join(self.fav.LOCAL, "favorites.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def draft(self, name, audios):
        d = os.path.join(self.cap, name); os.makedirs(os.path.join(d, "assets", "audio"), exist_ok=True)
        mats, segs = [], []
        for i, (title, kind, where, secs) in enumerate(audios):
            if where == "draft":
                _touch(os.path.join(d, "assets", "audio", f"a{i}.mp3"))
                path = f"##_draftpath_placeholder_ABC-123_##/assets/audio/a{i}.mp3"
            else:
                path = os.path.join(self.cache, f"c{i}.mp3"); _touch(path)
            mats.append({"id": f"m{i}", "name": title, "type": kind, "path": path, "duration": int(secs * 1e6)})
            segs.append({"material_id": f"m{i}", "target_timerange": {"start": i * 1_000_000}})
        info = {"materials": {"audios": mats}, "tracks": [{"type": "audio", "segments": segs}]}
        with open(os.path.join(d, self.fav.ds.draft_json_name(d)), "w", encoding="utf-8") as fh:
            json.dump(info, fh)
        return d

    def test_learns_only_her_picks(self):
        self.draft("My Sound Palette", [
            ("Soft pop(12345)", "sound", "cache", 0.4),
            ("whoosh-from-pixabay.mp3", "extract_music", "draft", 0.8),
            ("video_1", "video_original_sound", "draft", 30),
            ("Chill beat", "music", "cache", 60),
        ])
        msg, code = self.fav.learn("my sound palette", ["vary these"])
        self.assertEqual(code, 0, msg)
        st = self.fav.load()
        self.assertEqual([s["name"] for s in st["sounds"]], ["soft-pop", "whoosh-from-pixabay"])
        self.assertEqual(st["rules"], ["vary these"])
        self.assertIn("music tracks", msg)
        for s in st["sounds"]:
            self.assertTrue(os.path.isfile(os.path.join(self.fav.ROOT, s["file"])))

    def test_a_sound_taken_off_the_shelf_leaves_the_library(self):
        self.draft("shelf", [("A one", "sound", "cache", 0.3), ("B two", "sound", "cache", 0.3)])
        self.fav.learn("shelf", [])
        shutil.rmtree(os.path.join(self.cap, "shelf"))
        self.draft("shelf", [("A one", "sound", "cache", 0.3)])
        self.fav.learn("shelf", [])
        self.assertEqual(sorted(os.listdir(self.fav.SOUNDS)), ["a-one.mp3"])
        self.assertEqual(self.fav.load()["sounds"][0]["name"], "a-one")

    def test_ambiguous_and_missing_names_ask_instead_of_guessing(self):
        self.draft("palette 1", [("x", "sound", "cache", 0.3)])
        self.draft("palette 2", [("y", "sound", "cache", 0.3)])
        self.assertEqual(self.fav.learn("palette", [])[1], 2)
        self.assertEqual(self.fav.learn("nothing like it", [])[1], 2)

    def test_the_engine_reaches_her_sounds_first(self):
        sfx = _load("capcut_sfx")
        mine = os.path.join(self.tmp, "mine"); os.makedirs(mine)
        _touch(os.path.join(mine, "pop.mp3"))
        sfx.FAVORITES_DIR = mine
        self.assertEqual(sfx.palette()["pop"], os.path.join(mine, "pop.mp3"))


if __name__ == "__main__":
    unittest.main()
