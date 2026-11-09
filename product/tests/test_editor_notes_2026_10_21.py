#!/usr/bin/env python3
"""Guards: her editor notes from 2026-10-21, each fixed in the engine.

  takes her line    a design that takes her captions' place (hides_captions) with only a note slot shows the line she
                    is saying on every reel, never the words of the reel it was saved on ("I can't believe this is
                    real." over a different line)
  keeps its note    a design with a slot of its own for her words (a checklist) keeps its note: the heading is hers
  no stray slash    a design saved without a "first / second" note gets her line whole (a typing design put the "/"
                    on screen); one saved with it still splits at her first pause
  her breaks win    words given with " / " breaks keep them (her three-line CTA)
  redraw stale      a drawing records the note it showed, so one drawn with words that aren't her line is redrawn
  leaves on time    a look that shows her words leaves as she starts her next word, so that word's captions show
                    ("Just kidding." held 0.4 s and "today" never showed) (visual_editor.looks_manifest)
  typed emoji       an emoji she types is the emoji a pop shows (she asked for a winking face)
  split follows     on a line split, a look given its own words goes to the half where she says them
                    (visual_editor.edit_lines)

Run: python3 product/tests/test_editor_notes_2026_10_21.py
"""
import inspect, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import lookbook  # noqa: E402
import visual_editor  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


line = "AI can make your videos look more like you than ever."
stack = {"slots": ["note"], "note": "a line from another reel.", "hides_captions": True}
checklist = {"slots": ["text", "note"], "note": "your personal", "hides_captions": True}
cta = {"slots": ["note"], "note": "comment keyword / and i will send it", "note_follows_line": True}

check(lookbook.follows_line(stack), "takes her line: a caption-replacing design with only a note follows the line")
check(lookbook._fill_values(line, stack)["note"] == line, "takes her line: the typed stack shows her line, whole")
check(not lookbook.follows_line(checklist), "keeps its note: a design with a text slot is not a line follower")
check(lookbook._fill_values(line, checklist)["note"] == "your personal", "keeps its note: the checklist heading stays hers")
check("/" not in lookbook._fill_values(line, stack)["note"], "no stray slash: a design saved without a break gets no '/'")
check(" / " in lookbook._fill_values("first part, second part", cta)["note"], "no stray slash: a split design still splits")
three = "We've given over $15,000 / to single moms and / orphaned children,"
check(lookbook._fill_values(three, cta)["note"] == three, "her breaks win: her own ' / ' breaks are kept as given")
check(lookbook.own_words({"design": True, "id": "x"}, "nope") is None, "own_words: an unreadable design is not a fixed-words look")

check(lookbook.emoji_for("\U0001F61C") == "\U0001F61C" and lookbook.emoji_for("just kidding \U0001F61C") == "\U0001F61C",
      "typed emoji: an emoji she types is the one a pop shows")
check(lookbook.emoji_for("nothing here") == "\u2728", "typed emoji: no emoji and no match still falls back to sparkles")
src = inspect.getsource(lookbook.draw_design)
check('"note": v.get("note"' in src, "redraw stale: a design drawing records the note it showed")
src = inspect.getsource(visual_editor._design_newer)
check("follows_line" in src and 'rec.get("note")' in src, "redraw stale: a line-following drawing with other words is redrawn")
src = inspect.getsource(visual_editor.looks_manifest)
check("_nx[0][\"t\"]" in src and "_hides_captions(jd, l)" in src, "leaves on time: word looks end at her next word")
src = inspect.getsource(visual_editor.edit_lines)
check("copy_" in src and "ov.index(max(ov))" in src, "split follows: a look with its own words goes to the half that says them")

if fails:
    for f in fails:
        print("  FAIL ", f)
    print(f"test_editor_notes_2026_10_21: {len(fails)} of {n} checks FAILED")
    sys.exit(1)
print(f"test_editor_notes_2026_10_21: all {n} checks passed")
