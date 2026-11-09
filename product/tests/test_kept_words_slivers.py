#!/usr/bin/env python3
"""A cut that lands a few ms inside a dropped word must not carry that word into the script.

snap-to-sound pads every boundary outward (in = onset - 42 ms), so a kept span can start a hair before
the previous, cut-away word has officially ended. kept-words used to keep ANY overlap, which put a 5 ms
"ça." from a dropped first take into the finished script and the captions. A scrap under 50 ms is
dropped; a word the span holds whole is kept at any length, and so is a long word the cut only trims.
Run: python3 product/tests/test_kept_words_slivers.py
"""
import os, sys, importlib.util

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
sys.path.insert(0, _SCRIPTS)            # kept-words imports its neighbour transcript_language
_p = os.path.join(_SCRIPTS, "kept-words.py")
_spec = importlib.util.spec_from_file_location("kept_words", _p)
kw = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(kw)

fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def texts(words, segments):
    heard = {"clips": [{"clip": "a.mp4", "words": words}]}
    by_name, by_stem = kw.index_clips(heard)
    cuts = {"segments": [dict(clip="a.mp4", start=s, end=e) for s, e in segments]}
    return [w["text"] for w in kw.place_on_cut(cuts, by_name, by_stem)]


# The French test clip: the first take's "ça." was stretched to 4.272, the kept take starts at 4.252.
raw = [
    {"w": "truc.", "start": 1.318, "end": 1.767},
    {"w": "ça.", "start": 3.552, "end": 4.272},
    {"w": "Personne", "start": 4.292, "end": 4.732},
    {"w": "ne", "start": 4.772, "end": 4.852},
]
got = texts(raw, [(0.131, 1.901), (4.252, 4.9)])
check("a 20 ms scrap of a cut-away word is dropped", "ça." not in got)
check("the kept words are all there", got == ["truc.", "Personne", "ne"])

# A short word the span holds whole is real, however short it is.
check("a whole 30 ms word inside the span is kept",
      texts([{"w": "a", "start": 1.00, "end": 1.03}], [(0.5, 2.0)]) == ["a"])

# A long, stretched word the cut only trims keeps its place: most of it is still heard.
check("a stretched word the cut trims is kept",
      texts([{"w": "système.", "start": 11.014, "end": 12.414}], [(10.134, 11.514)]) == ["système."])

# A word split across two abutting spans is still placed once, by the span that holds most of it.
split = texts([{"w": "maman.", "start": 6.153, "end": 6.433}], [(5.0, 6.16), (6.16, 7.0)])
check("a word split by a scrap at one span is placed once, by the other", split == ["maman."])

# A short word the PLAN kept ("I", "a", 40 ms long) stays in her script even when snap-to-sound and the frame grid
# move the span's start a few ms inside it: the span's own planned edges (_snapped_from) hold it.
heard = {"clips": [{"clip": "a.mp4", "words": [{"word": "see", "start": 3.5, "end": 3.9},
                                               {"word": "I", "start": 4.057, "end": 4.097},
                                               {"word": "want", "start": 4.117, "end": 4.338}]}]}
bn, bs = kw.index_clips(heard)
got = [w["text"] for w in kw.place_on_cut({"segments": [{"clip": "a.mp4", "start": 4.067, "end": 4.4,
                                                          "_snapped_from": {"start": 4.057, "end": 4.338}}]}, bn, bs)]
check("a short word the plan kept stays when the edge snaps a few ms inside it", got == ["I", "want"])
got = [w["text"] for w in kw.place_on_cut({"segments": [{"clip": "a.mp4", "start": 4.067, "end": 4.4,
                                                          "_snapped_from": {"start": 4.117, "end": 4.338}}]}, bn, bs)]
check("a scrap of a word the plan dropped still stays out", got == ["want"])

if fails:
    sys.exit(f"\n{len(fails)} failed")
print("\n✓ kept-words: cut-away scraps stay out of the script; real words survive")
