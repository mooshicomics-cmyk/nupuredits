#!/usr/bin/env python3
"""A preference taught for ONE kind of reel applies to that kind, and only that kind.

Scoped records ("only my confessional reels") were saved correctly and then never applied, because no
builder ever said what it was building. The course promises this works, so it is guarded two ways: the
matching itself, and every builder naming its build BEFORE its first preference read.
"""
import importlib.util, json, os, re, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "product", f"{name}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Scope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.L = _load("learned")
        self.L.STORE = os.path.join(self.tmp, "learned.json")
        self.L.ROOT = self.tmp
        self.L._CTX.clear()
        os.makedirs(os.path.join(self.tmp, "product", "creative-vault"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scoped_applies_only_to_its_register(self):
        self.L.add("sfx.density", "lighter", scope={"register": "confessional"})
        self.L.context_for_build("yap", register="confessional")
        self.assertEqual(self.L.get("sfx.density", "normal"), "lighter")
        self.L._CTX.clear()
        self.L.context_for_build("yap", register="teaching")
        self.assertEqual(self.L.get("sfx.density", "normal"), "normal")

    def test_unknown_register_never_guesses(self):
        self.L.add("sfx.density", "lighter", scope={"register": "confessional"})
        self.L.context_for_build("yap")
        self.assertEqual(self.L.get("sfx.density", "normal"), "normal")

    def test_the_reels_plan_wins_over_the_builder_default(self):
        job = os.path.join(self.tmp, "projects", "j"); os.makedirs(job)
        with open(os.path.join(job, "caption-plan.json"), "w", encoding="utf-8") as fh:
            json.dump({"register": "teaching"}, fh)
        ctx = self.L.context_for_build("yap", register="confessional", job_dir=job)
        self.assertEqual(ctx["register"], "teaching")

    def test_pack_falls_back_to_her_default(self):
        with open(os.path.join(self.tmp, "product", "creative-vault", "user-style.json"), "w", encoding="utf-8") as fh:
            json.dump({"default_pack": "Butter"}, fh)
        self.L.add("caption.size_scale", 1.2, scope={"pack": "Butter"})
        self.L.context_for_build("yap")
        self.assertAlmostEqual(self.L.get("caption.size_scale", 1.0), 1.2)

    def test_unscoped_still_applies_everywhere(self):
        self.L.add("sfx.density", "heavier")
        self.L.context_for_build("voiceover")
        self.assertEqual(self.L.get("sfx.density", "normal"), "heavier")

    def test_more_specific_wins(self):
        self.L.add("sfx.density", "heavier")
        self.L.add("sfx.density", "lighter", scope={"register": "confessional"})
        self.L.context_for_build("yap", register="confessional")
        self.assertEqual(self.L.get("sfx.density", "normal"), "lighter")


class EveryBuilderNamesItsBuild(unittest.TestCase):
    """Static guard: the context call comes before the first preference read in each builder."""

    def first(self, src, patterns):
        hits = [m.start() for p in patterns for m in re.finditer(p, src)]
        return min(hits) if hits else None

    def check(self, path, ctx_patterns, read_patterns):
        src = open(os.path.join(ROOT, "product", path), encoding="utf-8").read()
        ctx, read = self.first(src, ctx_patterns), self.first(src, read_patterns)
        self.assertIsNotNone(ctx, f"{path} never names its build")
        self.assertIsNotNone(read, f"{path} has no preference read (test is stale)")
        return src

    def test_build_reel_type(self):
        src = open(os.path.join(ROOT, "product", "build-reel-type.py"), encoding="utf-8").read()
        self.assertLess(src.index("context_for_build("), src.index("text_effects.resolve("))

    def test_vo_build(self):
        src = open(os.path.join(ROOT, "product", "vo-build.py"), encoding="utf-8").read()
        self.assertIn('context_for_build("voiceover"', src)

    def test_capcut_builders(self):
        for name in ("cleanyap.py", "superyap.py"):
            src = open(os.path.join(ROOT, "product", name), encoding="utf-8").read()
            self.assertIn("def learning_context(", src, name)
            # every function that reads a preference names the build first
            for m in re.finditer(r"\n(def \w+\([^)]*\):.*?)(?=\ndef |\Z)", src, re.S):
                body = m.group(1)
                if 'learned.get("' in body and not body.startswith("def learning_context"):
                    self.assertIn("learning_context()", body.split('learned.get("')[0],
                                  f"{name}: {body.splitlines()[0]} reads a preference before naming the build")


if __name__ == "__main__":
    unittest.main()
