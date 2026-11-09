#!/usr/bin/env python3
"""Words that belong to whoever owns an engine stay out of the table every buyer receives.

presets/caption-corrections.json ships to every buyer, and it had been carrying one owner's personal
flag words. Those now live in _local/caption-corrections.json, which the ship build leaves out and no
update touches, and the two tools that read the table lay it over the shared one:

  kept-words.py   applies its fixes and flags, between the shared table and the job's own file
  flag-words.py   counts its words as already accounted for, so they are not raised as suspects
                  (it reads the same three files kept-words lays, the job's own file included)

So an engine that has the file behaves exactly as it did when those words sat in the shared table, and
an engine without it (every buyer's) simply never hears of them.

Run:  python3 product/tests/test_owner_corrections.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


OWNER = {"auto": {"kiddoco": "KiddoCo"}, "flag": ["crumbwise"]}
SPOKEN = ["welcome", "to", "kiddoco", "where", "the", "crumbwise", "gang", "meets"]

tmp = tempfile.mkdtemp()
try:
    eng = os.path.join(tmp, "engine")
    shutil.copytree(SCRIPTS, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    os.makedirs(os.path.join(eng, "presets"))
    shutil.copy(os.path.join(ROOT, "presets", "caption-corrections.json"),
                os.path.join(eng, "presets", "caption-corrections.json"))
    job = os.path.join(eng, "projects", "my-reel")
    write(os.path.join(job, "transcript", "words.json"),
          {"clips": [{"clip": "take.mov", "words": [{"w": w, "start": i * 0.4, "end": i * 0.4 + 0.3}
                                                   for i, w in enumerate(SPOKEN)]}]})
    write(os.path.join(job, "transcript", "cuts.json"), {"segments": [{"clip": "take.mov", "start": 0, "end": 4}]})
    out = os.path.join(job, "outputs", "my-reel.transcript.json")
    os.makedirs(os.path.dirname(out))
    env = dict(os.environ)
    env.pop("CAPTION_CORRECTIONS", None)
    env.pop("REELS_CAPTION_CORRECTIONS", None)

    def export():
        r = subprocess.run([sys.executable, os.path.join(eng, ".claude/skills/rough-cut/scripts/kept-words.py"),
                            os.path.join(job, "transcript", "words.json"), os.path.join(job, "transcript", "cuts.json"),
                            out], capture_output=True, text=True, env=env, encoding="utf-8")
        with open(out, encoding="utf-8") as fh:
            return r, [w["text"] for w in json.load(fh)["words"]]

    def known():
        """The words flag-words.py counts as already handled for this job's transcript."""
        sys.path.insert(0, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "scan_t", os.path.join(eng, ".claude/skills/rough-cut/scripts/flag-words.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.handled_words(out)

    # a buyer's engine: no _local, so the owner's words mean nothing to it
    r, words = export()
    check("without _local: the owner's fix is not applied", "kiddoco" in words and "KiddoCo" not in words, str(words))
    check("without _local: the owner's flag is not raised", "crumbwise" not in r.stdout, r.stdout)
    check("without _local: nothing mentions an owner file", " yours " not in r.stdout, r.stdout)
    check("without _local: the scan does not know the owner's words",
          not {"kiddoco", "crumbwise"} & known())

    # the owner's engine: _local/caption-corrections.json laid over the shared table
    write(os.path.join(eng, "_local", "caption-corrections.json"), OWNER)
    r, words = export()
    check("with _local: the owner's fix is applied", "KiddoCo" in words, str(words))
    check("with _local: the owner's flag is raised", "⚠ REVIEW" in r.stdout and "crumbwise" in r.stdout, r.stdout)
    check("with _local: the log names the owner file",
          re.search(r" yours \S*_local[/\\]caption-corrections\.json", r.stdout), r.stdout)
    check("with _local: the scan counts the owner's words as handled", {"kiddoco", "crumbwise"} <= known())

    # the job's own file still wins over the owner's: promoting a flagged word to a fix takes it off the list
    write(os.path.join(job, "corrections.local.json"), {"auto": {"crumbwise": "CrumbWise"}})
    r, words = export()
    check("the job's own file still lays over the owner's", "CrumbWise" in words and "REVIEW" not in r.stdout,
          f"{words} {r.stdout}")
    check("the scan counts the job's own fixes as handled (as heard and as written)", {"crumbwise"} <= known())

    # a name heard as several words: the job's phrase fix writes it, and the scan stops raising it
    write(os.path.join(job, "corrections.local.json"),
          {"auto": {"crumbwise": "CrumbWise"}, "phrases": {"gang meets": "GangMeets!"}})
    r, words = export()
    check("a phrase fix writes the name", "GangMeets!" in words, str(words))
    check("the scan counts a word a phrase writes as handled", "gangmeets" in known())
    os.remove(os.path.join(job, "corrections.local.json"))

    # a table named in the environment: REELS_CAPTION_CORRECTIONS, and the older CAPTION_CORRECTIONS still
    alt = os.path.join(tmp, "elsewhere", "corrections.json")
    write(alt, {"auto": {"gang": "GANG"}})
    for name in ("REELS_CAPTION_CORRECTIONS", "CAPTION_CORRECTIONS"):
        env[name] = alt
        r, words = export()
        check(f"{name} names the shared table", "GANG" in words and alt in r.stdout, f"{words} {r.stdout}")
        env.pop(name)
    env["REELS_CAPTION_CORRECTIONS"] = alt
    env["CAPTION_CORRECTIONS"] = os.path.join(tmp, "no-such-table.json")
    r, words = export()
    check("REELS_CAPTION_CORRECTIONS wins over the older name", "GANG" in words, str(words))
    env.pop("REELS_CAPTION_CORRECTIONS"); env.pop("CAPTION_CORRECTIONS")

    # the ship build leaves _local/ out and updates never touch it (seller-side files; absent from a bundle)
    ship = os.path.join(ROOT, "make-ship.sh")
    if os.path.exists(ship):
        with open(ship, encoding="utf-8") as fh:
            check("make-ship.sh leaves _local/ out of the buyer bundle", "--exclude='_local/'" in fh.read())
    upd = os.path.join(ROOT, "make-update.py")
    if os.path.exists(upd):
        with open(upd, encoding="utf-8") as fh:
            check("update patches never carry _local/", '"_local/"' in fh.read())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else "owner corrections: laid over the shared table, never shipped")
sys.exit(1 if fails else 0)
