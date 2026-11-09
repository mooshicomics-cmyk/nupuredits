#!/usr/bin/env python3
"""A line the cut plays twice is captioned twice.

A line copied to the front of the reel as a cold-open hook is heard twice: once as the hook, once where she
said it. kept-words used to place each spoken word only once across the whole cut (to keep a word the cut
split between two abutting spans from doubling), so the second play had no words in her script and no
captions. Now a word is held to one placement only when the span that placed it is the one just before and
this span carries the same take on; any other span that plays the footage again places it again.
Run: python3 product/tests/test_kept_words_replays.py
"""
import json, os, subprocess, sys, tempfile, importlib.util

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
sys.path.insert(0, _SCRIPTS)            # kept-words imports its neighbour transcript_language
_p = os.path.join(_SCRIPTS, "kept-words.py")
_spec = importlib.util.spec_from_file_location("kept_words", _p)
kw = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(kw)

fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


# Her take: "money is not the goal. freedom is the goal." with the second sentence at 10-12 s.
WORDS = [
    {"word": "money", "start": 0.5, "end": 0.9}, {"word": "is", "start": 1.0, "end": 1.1},
    {"word": "not", "start": 1.2, "end": 1.4}, {"word": "the", "start": 1.5, "end": 1.6},
    {"word": "goal.", "start": 1.7, "end": 2.1},
    {"word": "freedom", "start": 10.1, "end": 10.6}, {"word": "is", "start": 10.7, "end": 10.8},
    {"word": "the", "start": 10.9, "end": 11.0}, {"word": "goal.", "start": 11.1, "end": 11.6},
]
HEARD = {"clips": [{"clip": "talk.mp4", "words": WORDS}]}


def place(segments, plain=False, words=None):
    heard = HEARD if words is None else {"clips": [{"clip": "talk.mp4", "words": words}]}
    by_name, by_stem = kw.index_clips(heard)
    cuts = {"segments": [dict(clip="talk.mp4", start=s, end=e) for s, e in segments]}
    return (kw.place_plain if plain else kw.place_on_cut)(cuts, by_name, by_stem)


for plain in (False, True):
    route = "simple route" if plain else "full route"
    # The cold open: 10-12 copied to the front, then the whole take from the top.
    got = place([(10.0, 12.0), (0.0, 12.0)], plain=plain)
    texts = [w["text"] for w in got]
    check(f"{route}: the copied hook line is in her script on both plays",
          texts == ["freedom", "is", "the", "goal.", "money", "is", "not", "the", "goal.", "freedom", "is", "the", "goal."],
          texts)
    first = [w for w in got if w["text"] == "freedom"]
    check(f"{route}: each play sits where it plays (0.1 s as the hook, 12.1 s in the body)",
          [w["start"] for w in first] == [0.1, 12.1], [w["start"] for w in first])

    # A rewind: the take, then its last line again.
    texts = [w["text"] for w in place([(0.0, 12.0), (10.0, 12.0)], plain=plain)]
    check(f"{route}: a rewound line is captioned again", texts.count("freedom") == 2, texts)

    # A line moved (not copied) is still placed once.
    texts = [w["text"] for w in place([(10.0, 12.0), (0.0, 3.0)], plain=plain)]
    check(f"{route}: a line moved to the front (not copied) is placed once", texts.count("freedom") == 1, texts)

# A seam the cut put inside a word: still one word, placed once (the case the old rule existed for).
split = [{"word": "freedom", "start": 10.1, "end": 10.6}]
texts = [w["text"] for w in place([(9.0, 10.35), (10.35, 12.0)], words=split)]
check("a word split between two abutting spans of one take is placed once", texts == ["freedom"], texts)

# snap-to-sound pads both edges and the frame grid moves them: a few frames of overlap is still one take.
short = [{"word": "I", "start": 5.0, "end": 5.04}]
texts = [w["text"] for w in place([(0.0, 5.06), (4.98, 9.0)], words=short)]
check("a short word inside a padded seam (a few frames of overlap) is placed once", texts == ["I"], texts)

# A word the cut runs through a chain of short spans of one take is one play, placed once.
long_word = [{"word": "sooo", "start": 4.9, "end": 5.4}]
texts = [w["text"] for w in place([(0.0, 5.0), (5.0, 5.1), (5.1, 9.0)], words=long_word)]
check("a word running through a chain of short spans is placed once", texts == ["sooo"], texts)

# End to end: the script stitch-cut.sh runs writes both plays into outputs/<job>.transcript.json.
d = tempfile.mkdtemp(prefix="kw-replay-")
wj, cj, out = (os.path.join(d, n) for n in ("words.json", "cuts.json", "out.transcript.json"))
json.dump(HEARD, open(wj, "w", encoding="utf-8"))
json.dump({"segments": [{"clip": "talk.mp4", "start": 10.0, "end": 12.0},
                        {"clip": "talk.mp4", "start": 0.0, "end": 12.0}]}, open(cj, "w", encoding="utf-8"))
for extra in ([], ["--plain"]):
    p = subprocess.run([sys.executable, _p, *extra, wj, cj, out], capture_output=True, text=True,
                       env=dict(os.environ, REELS_CAPTION_CORRECTIONS=os.path.join(d, "none.json")))
    try:
        words = json.load(open(out, encoding="utf-8"))["words"]
    except Exception as exc:                # noqa: BLE001
        words = []
        print(p.stdout, p.stderr)
    check(f"kept-words.py {' '.join(extra) or '(full)'}: her script has the hook line twice",
          [w["text"] for w in words].count("freedom") == 2, [w["text"] for w in words])

if fails:
    sys.exit(f"\n{len(fails)} failed")
print("\n✓ kept-words: every play of a line is in her script; one play of a word is placed once")
