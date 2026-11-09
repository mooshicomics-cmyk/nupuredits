#!/usr/bin/env python3
"""flag-words.py: the few words of a reel's script worth reading twice, sorted by which word-fix table a fix
would go in.

    python3 .claude/skills/rough-cut/scripts/flag-words.py projects/<job>
    python3 .claude/skills/rough-cut/scripts/flag-words.py projects/<job>/outputs/<job>.transcript.json --json

Run it on a job right after the stitch. A transcriber's new mishear is nearly always a name it has not met
(a guest, a product, a word she made up), one or two among hundreds of good words, and a misheard name
comes out as a spelling nothing else knows. So every word of her script is asked who vouches for it, and
only the words nobody vouches for are listed:

  her word fixes    one of her tables (kept-words.py lays them: shared, yours, this reel) puts it right,
                    writes it, or lists it to check
  the transcriber   the speech model's own vocabulary holds it as one whole lowercase word: Whisper
                    learned it as an everyday word, so it wrote it on purpose
  the wordlist      the system wordlist has it, or has it once an -s, -ed or -ing comes off
  her own words     SAID_RIGHT below: everyday words from real reels that neither of those knows
  a number          anything with a digit in it; a number is never a name heard wrong

A hyphenated or dotted word is vouched for piece by piece ("b-roll", "a.m"), and a word with an
apostrophe by what comes before it ("Kajabi's" is asked about "Kajabi").

Nothing is changed here, and a name she said right is listed too: this list is for reading. Each word comes
with how many of her other reels (the job folders beside this one) say it, because that decides the table:
a word her other reels share is fixed once for all of them; a word only this reel has is fixed for this reel.
"""
import glob
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print → or ×
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from transcript_language import classify, english_wordlist   # both live in this folder

HERE = Path(__file__).resolve().parent
TAG = "[flag-words]"
HOW_TO_RUN = ("flag-words.py needs a job: python3 flag-words.py projects/<job>  (or the script itself, "
              "projects/<job>/outputs/<job>.transcript.json); add --json for the list as JSON")

# Endings taken off before the wordlist is asked again, each with what the plain word may have ended in
# ("making" was "make"). These are the only endings that three or more different words of real reels
# needed after the wordlist and the speech model's vocabulary had both been asked; every other inflected
# word in them was already known whole. A plain word must be three letters or more to count: the wordlist
# also lists every single letter and a crowd of two-letter abbreviations.
ENDINGS = (("s", ""), ("ed", ""), ("ing", ""), ("ing", "e"))
SHORTEST_PLAIN = 3

# Everyday words from real reels, spelled right, that neither the wordlist nor the speech model's
# vocabulary knows (with ENDINGS, their plurals and past forms are covered too).
SAID_RIGHT = {
    "async", "carousel", "crossfade", "demoted", "editable", "gumball", "inundated", "multitask", "naptime",
    "obsessively", "orphanage", "outgrew", "outran", "outsource", "popsicle", "prebuilt", "replicable",
    "signup", "solopreneur", "sustainably", "takeover", "techie", "viewport", "voiceover", "waitlist",
    "whiteboard",
}


def _kept_words():
    """kept-words.py, which owns the word-fix tables: one place decides which tables a job reads."""
    spec = importlib.util.spec_from_file_location("kept_words", HERE / "kept-words.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ============================================================================ who vouches for a word
def _hub():
    """Where the speech model's files are cached (the Hugging Face cache the transcriber downloads into)."""
    if os.environ.get("HF_HUB_CACHE"):
        return os.environ["HF_HUB_CACHE"]
    return os.path.join(os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"),
                        "hub")


def transcriber_words():
    """The speech model's whole lowercase words, read from its tokenizer in the local cache; empty when no
    Whisper model has been downloaded here. Every multilingual Whisper size shares one vocabulary, and the
    transcriber's own large-v3 is preferred when several are cached."""
    found = sorted(glob.glob(os.path.join(_hub(), "models--*whisper*", "snapshots", "*", "tokenizer.json")))
    found.sort(key=lambda path: ("large-v3" not in path, path.split(os.sep)[-4].endswith(".en"), path))
    for path in found:
        try:
            with open(path, encoding="utf-8") as fh:
                vocab = json.load(fh)["model"]["vocab"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        # A token that starts a word carries a leading space, written "Ġ" in this vocabulary's byte alphabet.
        return {tok[1:] for tok in vocab if tok.startswith("Ġ") and tok[1:].isalpha() and tok[1:].islower()}
    return set()


class Vouchers:
    """Everything that can vouch for a word: the wordlist, the speech model's vocabulary, SAID_RIGHT, and the
    words her word-fix tables already speak for."""

    def __init__(self, wordlist, model_words, handled):
        self.known = set(wordlist) | set(model_words) | SAID_RIGHT
        self.handled = set(handled)

    def _plain(self, piece):
        if piece in self.known:
            return True
        for ending, was in ENDINGS:
            stem = piece[:-len(ending)] + was
            if piece.endswith(ending) and len(stem) >= SHORTEST_PLAIN and stem in self.known:
                return True
        return False

    def vouched(self, key):
        """True when something vouches for this lowercased word; it is then left off the list."""
        if not key or key in self.handled or any(ch.isdigit() for ch in key):
            return True
        head = re.split(r"['’]", key)[0]
        if head != key and (not head or head in self.handled):
            return True
        pieces = [p for p in re.split(r"[-.]", head) if p]
        return all(self._plain(p) for p in pieces)


# ===================================================================== what her fixes already cover
_EDGES = re.compile(r"^\W+|\W+$")       # marks around a word: "(really?!" -> "really"
_MARKS = re.compile(r"\W")              # "G.P.T." reads as gpt once its marks go


def _forms(word):
    """A word a fix writes, in the two shapes a script can show it: as written, and without marks."""
    core = _EDGES.sub("", str(word)).lower()
    return {core, _MARKS.sub("", core)}


def accounted_for(files):
    """Every word her word-fix tables speak for: a word a fix replaces, any word a fix writes (one word or a
    phrase), and every word listed to check."""
    kept_words, words = _kept_words(), set()
    for _layer, path in files:
        table = kept_words.read_table(path)
        for heard, meant in table["words"].items():
            words.add(heard.lower())
            words |= _forms(meant)
        for meant in table["phrases"].values():
            for part in str(meant).split():
                words |= _forms(part)
        words.update(word.lower() for word in table["check"])
    words.discard("")
    return words


def handled_words(transcript):
    """Every word the word-fix tables of this transcript's job already speak for (empty with none)."""
    return accounted_for(_kept_words().fix_files(transcript))


# ============================================================================== reading her script
def script_path(arg):
    """A job folder stands for the script in it; anything else is the script itself."""
    given = Path(arg)
    return given / "outputs" / (given.name + ".transcript.json") if given.is_dir() else given


def to_read(spoken, vouchers):
    """-> [{word, times, first_at, heard_in}, ...] for the words nobody vouches for, in the order she first
    said them. heard_in is that first time with three words either side."""
    listed = {}
    for i, token in enumerate(spoken):
        core = _EDGES.sub("", token)
        key = core.lower()
        if vouchers.vouched(key):
            continue
        if key not in listed:
            listed[key] = {"word": core, "times": 0, "first_at": i, "heard_in": " ".join(spoken[max(0, i - 3):i + 4])}
        listed[key]["times"] += 1
    return list(listed.values())


def _job_folder(script):
    """projects/<job> when the script sits in projects/<job>/outputs/, else None."""
    above = Path(script).resolve().parents
    return above[1] if len(above) >= 3 and above[2].name == "projects" else None


def add_other_reels(script, entries):
    """Give each entry "other_reels": how many other job folders' scripts say the word. None when the script
    is not inside a projects/<job>/outputs/ folder, so there are no other reels to ask."""
    job = _job_folder(script)
    counts = {e["word"].lower(): (0 if job is not None else None) for e in entries}
    if job is not None and counts:
        for folder in sorted(job.parent.iterdir()):
            if folder == job:
                continue
            said = set()
            for other in folder.glob("outputs/*.transcript.json"):
                try:
                    with open(other, encoding="utf-8") as fh:
                        said |= {_EDGES.sub("", w.get("text", "")).lower() for w in json.load(fh).get("words", [])}
                except (OSError, ValueError, AttributeError):
                    continue
            for key in counts:
                counts[key] += key in said
    for e in entries:
        e["other_reels"] = counts[e["word"].lower()]
    return entries


# ======================================================================================= saying it
def _not_run(script, as_json, why, language=None):
    """Say the check did not run and why, rather than hand back a list it had no business making."""
    if not as_json:
        print(f"{TAG} {why}", file=sys.stderr)
        return
    payload = {"script": str(script), "to_read": [], "not_run": why}
    if language is not None:
        payload["language"] = language        # quotes her own words, so they print as written
    print(json.dumps(payload, indent=2, ensure_ascii=language is None))


def _line(e):
    times = f"×{e['times']}" if e["times"] > 1 else "once"
    return f"    {e['word']}  ({times})  \"{e['heard_in']}\""


def print_report(script, spoken, entries, files):
    job = _job_folder(script)
    where = f"projects/{job.name}" if job is not None else "<job folder>"
    print(f"{TAG} {script}: {len(spoken)} words, {len(entries)} to read twice")
    if not entries:
        print(f"{TAG} something vouches for every word.")
        return
    shared = [e for e in entries if e["other_reels"]]
    alone = [e for e in entries if not e["other_reels"]]
    hers = any(layer == "yours" for layer, _ in files)
    if shared:
        n = max(e["other_reels"] for e in shared)
        print(f"\n  said in her other reels too (up to {n}): a fix goes in presets/caption-corrections.json"
              + (", or _local/caption-corrections.json when the word is hers alone" if hers else ""))
        for e in shared:
            print(_line(e) + f"  {e['other_reels']} other reel" + ("" if e["other_reels"] == 1 else "s"))
    if alone:
        head = "only in this reel" if job is not None else "in this script"
        print(f"\n  {head}: a fix goes in {where}/word-fixes.json")
        for e in alone:
            print(_line(e))
    print("\nRead each where she said it; a name she said right needs nothing. Put a real mishear right in "
          "its table: \"words\" for one word heard wrong, \"phrases\" for a name heard as several words, "
          "\"check\" for a real word you cannot call either way (listed on every run). Then rewrite the "
          f"script, leaving the cut as it is: bash .claude/skills/rough-cut/scripts/respell.sh {where}")


def main():
    args = sys.argv[1:]
    named = [arg for arg in args if not arg.startswith("--")]
    if not named:
        sys.exit(HOW_TO_RUN)
    as_json = "--json" in args
    script = script_path(named[0])
    if not script.exists():
        sys.exit(f"{TAG} there is no script at {script} yet (the rough cut's stitch writes it)")
    with open(script, encoding="utf-8") as fh:
        spoken = [w.get("text", "") for w in json.load(fh).get("words", [])]

    wordlist = english_wordlist()
    if not wordlist:
        # The speech model's vocabulary alone leaves out too many plain words, so without a wordlist the list
        # would be mostly false alarms. Saying so beats a screen of them.
        _not_run(script, as_json, "this computer has no English wordlist (/usr/share/dict/words), "
                                  "so no words were checked")
        return

    # The wordlist and the vocabulary are English. On a reel in another language they would list her own
    # ordinary words as errors (a bilingual reel once had 28 plain Spanish words listed), so a script that
    # is not confidently English is left alone.
    language = classify(spoken)
    if not language["english_only_checks_ok"]:
        _not_run(script, as_json, f"her script reads as {language['verdict']} ({language['reason']}), and this "
                                  f"check only knows English, so none of her words were checked", language)
        return

    files = _kept_words().fix_files(script)
    vouchers = Vouchers(wordlist, transcriber_words(), accounted_for(files))
    entries = add_other_reels(script, to_read(spoken, vouchers))
    if as_json:
        print(json.dumps({"script": str(script), "words": len(spoken), "to_read": entries}, indent=2))
    else:
        print_report(script, spoken, entries, files)


if __name__ == "__main__":
    main()
