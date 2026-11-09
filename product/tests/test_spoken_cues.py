#!/usr/bin/env python3
"""The first-reel script must build every effect it names, on the line that names it.

A buyer's first reel is the first-reel script: every line names an effect. If a line is missed, or the
plan's phrase does not match what build-reel-type.py sees in the transcript, that effect silently does not
render on the one reel meant to show her everything. These tests pin the cue reader to the script and to
the renderer's own word matching.
"""
import importlib.util, os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
_spec = importlib.util.spec_from_file_location("spoken_cues", os.path.join(ROOT, "product", "spoken_cues.py"))
sc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sc)

ZONES = {"roomier_side": "right", "face": {"top": 480, "bottom": 970},
         "zones": {"above": {"top": 270, "bottom": 284, "usable": False},
                   "below": {"top": 1031, "bottom": 1620, "usable": True},
                   "left": {"usable": False, "center_x_px": 140},
                   "right": {"usable": False, "center_x_px": 908}}}


def words_for(lines):
    t, out = 0.2, []
    for line in lines:
        for w in line.split():
            out.append({"text": w, "start": round(t, 3), "end": round(t + 0.28, 3)}); t += 0.33
        t += 0.3
    return out


def script_lines():
    with open(os.path.join(ROOT, "product", "FIRST-REEL-SCRIPT.md"), encoding="utf-8") as fh:
        txt = fh.read()
    return re.findall(r"^\d+\. (.+)$", txt, re.M)


def full_menu_lines():
    """The first-reel script plus the two effects it no longer films (star, thought bubble), placed where the
    old 11-line script had them, so the whole vocabulary stays covered."""
    lines = script_lines()
    i = next(n for n, l in enumerate(lines) if "breaks away" in l)
    return lines[:i] + ["Here's a star, popping on.", "And here's a little thought bubble."] + lines[i:]


class FirstReelScript(unittest.TestCase):
    def test_every_named_effect_is_heard(self):
        cues = sc.detect(words_for(script_lines()))
        self.assertEqual([c[0] for c in cues],
                         ["hook", "single", "karaoke", "takeover", "counter", "punch", "breakaway"])

    def test_plan_places_everything(self):
        w = words_for(script_lines())
        plan, notes, skipped = sc.build_plan("t", w, sc.detect(w), ZONES)
        self.assertEqual(skipped, [])
        self.assertEqual(plan["elements"][0]["to"], 300)
        for k in ("hook", "caption_treatments", "takeover_keys", "breakaways", "punch", "sfx"):
            self.assertIn(k, plan)

    def test_full_menu_still_heard_and_placed(self):
        w = words_for(full_menu_lines())
        cues = sc.detect(w)
        self.assertEqual([c[0] for c in cues],
                         ["hook", "single", "karaoke", "takeover", "counter", "punch", "star", "bubble", "breakaway"])
        plan, notes, skipped = sc.build_plan("t", w, cues, ZONES)
        self.assertEqual(skipped, [])
        for k in ("hook", "caption_treatments", "takeover_keys", "breakaways", "punch", "vibe", "sfx"):
            self.assertIn(k, plan)

    def test_effects_clear_before_the_next_lands(self):
        w = words_for(full_menu_lines())
        cues = sc.detect(w)
        plan, *_ = sc.build_plan("t", w, cues, ZONES)
        starts = [float(r[0]["start"]) for _e, r, _l in cues]
        for el in plan["elements"]:
            nxt = min((s for s in starts if s > el["at"]), default=99)
            self.assertLessEqual(el["at"] + el["duration"], nxt)
        self.assertLessEqual(plan["vibe"]["out"], min(s for s in starts if s > plan["vibe"]["at"]))


class Matching(unittest.TestCase):
    def test_phrases_use_the_renderers_normalisation(self):
        w = words_for(["And this is a full-screen take over."])
        plan, *_ = sc.build_plan("t", w, sc.detect(w), ZONES)
        self.assertEqual(plan["takeover_keys"], ["and this is a fullscreen take over"])

    def test_number_in_the_next_sentence(self):
        w = words_for(["Here's a count-up.", "$5,000."])
        plan, *_ = sc.build_plan("t", w, sc.detect(w), ZONES)
        self.assertEqual(plan["elements"][0]["to"], 5000)
        self.assertEqual(plan["elements"][0]["prefix"], "$")

    def test_ordinary_sentences_are_not_cues(self):
        lines = ["I got hooked on this show.", "My kids took over the kitchen.", "She is a star."]
        self.assertEqual(sc.detect(words_for(lines)), [])

    def test_cue_words_normalise_exactly_as_the_renderer_does(self):
        # The plan's phrases are looked for in build-reel-type.py's token stream. When its matcher learned
        # digits and every script, this copy still kept a-z alone, so "$300" vanished from the plan while the
        # renderer kept "300", and no cue line holding a number or an accent could ever match.
        import ast, unicodedata
        with open(os.path.join(ROOT, "product", "build-reel-type.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        keep = [n for n in tree.body if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_APOSTROPHES"
                for t in n.targets)) or (isinstance(n, ast.FunctionDef) and n.name == "norm")]
        g = {"unicodedata": unicodedata}
        exec(compile(ast.Module(body=keep, type_ignores=[]), "build-reel-type.py", "exec"), g)
        for w in ["$300", "20,000", "está", "Ça", "don\u2019t", "it\u02bcs", "\u201cquoted\u201d", "count-up", "Hook."]:
            self.assertEqual(sc.norm_word(w), g["norm"](w), w)

    def test_a_requested_list_of_effects_is_heard_clause_by_clause(self):
        # Said on a real test reel: one sentence, five effects, no clause pointing at itself.
        line = ("I want to see a hook above my head, single word captions under my chin, a line of karaoke "
                "captions, a full screen takeover, and then a count up.")
        cues = sc.detect(words_for([line]))
        self.assertEqual([c[0] for c in cues], ["hook", "single", "karaoke", "takeover", "counter"])
        self.assertEqual(sc.line_text(cues[0][1]), "hook above my head,")      # the request words are not the hook
        self.assertEqual(sc.line_text(cues[4][1]), "count up.")
        starts = [c[1][0]["start"] for c in cues]
        self.assertEqual(starts, sorted(starts))                            # each on its own words, in order
        self.assertEqual([c[0] for c in sc.detect(words_for(["Give me a hook and a karaoke line."]))], ["hook", "karaoke"])

    def test_a_request_is_not_a_cue_without_an_effect_named_plainly(self):
        lines = ["I want to take over the family business.", "I want to see my kids grow up, and then take a nap.",
                 "Give me a star for trying.", "I would like to count on you."]
        self.assertEqual(sc.detect(words_for(lines)), [])

    def test_unmeasured_footage_is_refused_not_guessed(self):
        w = words_for(["Here's a star, popping on."])
        plan, _n, skipped = sc.build_plan("t", w, sc.detect(w), None)
        self.assertNotIn("elements", plan)
        self.assertEqual(skipped[0][0], "star")


if __name__ == "__main__":
    unittest.main()
