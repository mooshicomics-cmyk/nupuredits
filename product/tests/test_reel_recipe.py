#!/usr/bin/env python3
""""Turn this into a prompt I can reuse": the recipe states only what the job recorded, never the hook copy."""
import importlib.util, json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "product", f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Recipe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.r = _load("reel_recipe")
        self.r.ROOT = self.tmp
        self.r._capcut_versions = lambda job: []
        os.makedirs(os.path.join(self.tmp, "product", "creative-vault"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def job(self, name, plan=None, final=False, shots=None, built=()):
        jd = os.path.join(self.tmp, "projects", name); os.makedirs(os.path.join(jd, "outputs"))
        if plan is not None:
            json.dump(plan, open(os.path.join(jd, "caption-plan.json"), "w", encoding="utf-8"))
        if shots is not None:
            json.dump(shots, open(os.path.join(jd, "shot-plan.json"), "w", encoding="utf-8"))
        if final:
            open(os.path.join(jd, "outputs", f"{name}.final.mp4"), "w", encoding="utf-8").close()
        for b in built:
            os.makedirs(os.path.join(jd, f"hf-reel-type-{b}"))

    def test_teaching_well_done(self):
        self.job("tips", {"register": "teaching", "duration": 62, "hook": ["a", "b"], "hook_emphasis": "second",
                          "hook_end": 8, "caption_mode": "build", "takeover_keys": [1, 2, 3],
                          "elements": [{"kind": "counter"}], "sfx": [{}] * 12, "music": {"file": "x"}},
                 final=True, built=("butter",))
        text = self.r.prompt(self.r.facts("tips"))
        self.assertIn("Type: teaching", text)
        self.assertIn("well-done, just the finished video", text)
        self.assertIn("my Butter pack", text)
        self.assertIn("a small line over a big one", text)
        self.assertIn("counts up", text)
        self.assertIn("Sound effects: moderate", text)
        self.assertIn("music bed", text)

    def test_never_copies_hook_words(self):
        self.job("secret", {"register": "confessional", "hook": ["THE SECRET LINE", "x"], "hook_end": 8})
        text = self.r.prompt(self.r.facts("secret"))
        self.assertNotIn("THE SECRET LINE", text)
        self.assertIn("[the tension or promise", text)

    def test_voiceover(self):
        self.job("vo", shots={"shots": [1, 2, 3]}, final=True)
        text = self.r.prompt(self.r.facts("vo"))
        self.assertIn("voiceover reel", text)
        self.assertIn("shot plan", text)
        self.assertNotIn("rough cut", text)

    def test_nothing_recorded_stays_open(self):
        self.job("bare")
        text = self.r.prompt(self.r.facts("bare"))
        self.assertIn("[raw / medium / well-done / hands-off]", text)
        self.assertNotIn("ON SCREEN", text)

    def test_unknown_job(self):
        with self.assertRaises(SystemExit):
            self.r.facts("nope")


if __name__ == "__main__":
    unittest.main()
