#!/usr/bin/env python3
"""Word-fix tables: today's names are read, and so is everything a job or an engine kept from before.

  this reel   projects/<job>/word-fixes.json; a job folder's older corrections.local.json is still read, and
              where a job has both, word-fixes.json is laid last
  parts       "words" / "phrases" / "check"; inside one table the older "auto" / "flag" are read too, "auto"
              laid over "words" (an update that merged a table keeps her own entries under the name she used)
  readers     kept-words.py lays them into her script; flag-words.py counts their words as vouched for;
              respell.sh rebuilds her script with them and never touches the cut

Also flag-words' own rules: a number, the part of a word before its apostrophe, the pieces of a hyphenated word.

Run:  python3 product/tests/test_word_fix_tables.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(label)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def load(name, file):
    sys.path.insert(0, SCRIPTS)
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SPOKEN = ["meet", "kiddoco", "and", "crumbwise", "at", "gang", "meets", "today"]

tmp = tempfile.mkdtemp()
try:
    eng = os.path.join(tmp, "engine")
    shutil.copytree(SCRIPTS, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(eng, "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    write(os.path.join(eng, "presets", "caption-corrections.json"), {"words": {"today": "TODAY"}, "check": []})
    job = os.path.join(eng, "projects", "my-reel")
    write(os.path.join(job, "transcript", "words.json"),
          {"clips": [{"clip": "take.mov", "words": [{"w": w, "start": i * 0.4, "end": i * 0.4 + 0.3}
                                                   for i, w in enumerate(SPOKEN)]}]})
    write(os.path.join(job, "transcript", "cuts.json"), {"segments": [{"clip": "take.mov", "start": 0, "end": 4}]})
    out = os.path.join(job, "outputs", "my-reel.transcript.json")
    os.makedirs(os.path.dirname(out))                 # the stitch makes it; this job was never stitched
    env = {k: v for k, v in os.environ.items() if k not in ("REELS_CAPTION_CORRECTIONS", "CAPTION_CORRECTIONS")}

    def respell():
        r = subprocess.run(["bash", os.path.join(eng, ".claude/skills/rough-cut/scripts/respell.sh"), job],
                           capture_output=True, text=True, env=env, encoding="utf-8")
        with open(out, encoding="utf-8") as fh:
            return r, [w["text"] for w in json.load(fh)["words"]]

    print("1. the job's own table, by either name")
    write(os.path.join(job, "corrections.local.json"), {"auto": {"kiddoco": "KiddoCo"}, "flag": ["crumbwise"]})
    r, words = respell()
    check("an older corrections.local.json is still read (auto)", "KiddoCo" in words, words)
    check("...and its flag list still prints for review", "⚠ REVIEW" in r.stdout and "crumbwise" in r.stdout, r.stdout)
    check("the shared table's current part name is read", "TODAY" in words, words)
    write(os.path.join(job, "word-fixes.json"), {"words": {"kiddoco": "KIDDOCO", "crumbwise": "CrumbWise"},
                                                 "phrases": {"gang meets": "GangMeets"}})
    r, words = respell()
    check("word-fixes.json is laid over the older file", "KIDDOCO" in words and "KiddoCo" not in words, words)
    check("a word it puts right drops off the check list", "CrumbWise" in words and "REVIEW" not in r.stdout, r.stdout)
    check("its phrases are read", "GangMeets" in words, words)
    os.remove(os.path.join(job, "corrections.local.json"))
    r, words = respell()
    check("word-fixes.json alone", "KIDDOCO" in words and "GangMeets" in words, words)

    print("2. both part names inside one table")
    kw = load("kept_words_t", "kept-words.py")
    both = os.path.join(tmp, "both.json")
    write(both, {"words": {"canva": "Canva", "etsy": "Etsy"}, "auto": {"etsy": "ETSY"}, "check": ["cloud"],
                 "flag": ["notion", "cloud"]})
    table = kw.read_table(both)
    check("words and auto are both read", table["words"].get("canva") == "Canva", table)
    check("auto is laid over words in the same table", table["words"].get("etsy") == "ETSY", table)
    check("check and flag are both read, each word once", table["check"] == ["cloud", "notion"], table)

    print("3. flag-words counts every table's words, under either name, as vouched for")
    fw = load("flag_words_t", "flag-words.py")
    handled = fw.accounted_for([("this reel", both)])
    check("a heard word, a written word and a check word", {"canva", "etsy", "notion", "cloud"} <= handled, handled)
    v = fw.Vouchers({"meet", "and", "at", "make"}, set(), {"kajabi"})
    check("a number is never listed", v.vouched("130k") and v.vouched("2"))
    check("an apostrophe word is asked about what comes before it", v.vouched("kajabi's") and not v.vouched("zorbly's"))
    check("a hyphenated word is vouched for piece by piece", v.vouched("meet-and") and not v.vouched("meet-zorbly"))
    check("an ending comes off before the wordlist is asked", v.vouched("meets") and v.vouched("making"))
    check("a plain word shorter than three letters does not vouch", not fw.Vouchers({"ab"}, set(), set()).vouched("abs"))
    check("SAID_RIGHT vouches", v.vouched("waitlist") and v.vouched("waitlists"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "word-fix tables: every name read, the new ones laid last"))
sys.exit(1 if fails else 0)
