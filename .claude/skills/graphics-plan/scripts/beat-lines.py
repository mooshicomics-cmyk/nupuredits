#!/usr/bin/env python3
"""beat-lines.py: the creative plan's starting sheet, her finished script numbered into beats.

    beat-lines.py <job> [--out FILE]

<job> is the reel's job name (its folder under projects/), that folder given as a path, or a kept-words
transcript file. The script it reads is the one the rough cut leaves at outputs/<job>.transcript.json: every
word she kept, with its start and end in seconds on the cut.

A beat is the stretch of script one graphic can ride on. It opens where one of her sentences opens and
closes where that sentence closes, so a card arrives with the thought it belongs to. A sentence that runs
past BEAT_SECONDS or BEAT_WORDS (below) is cut in two at the widest silence inside it, and each half is
measured again. Every beat carries its id, its start and end on the cut and the words in it, followed by
the plan's decision fields, empty: the graphics-plan skill decides those.

With --out the scaffold is written to FILE and the beat sheet printed for reading. Without it the scaffold
goes to stdout and the sheet to stderr, so the output can be piped.
"""
import contextlib
import json
import os
import sys

# The language verdict is computed by the rough cut and lives there. Import it rather than owning a
# second copy of the heuristic: two language detectors that disagree is worse than none.
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))     # scripts/ sits four levels down
sys.path.insert(0, os.path.join(HERE, "..", "..", "rough-cut", "scripts"))
classify = None                        # stays None on an older engine or a moved skill: never block here
with contextlib.suppress(Exception):
    from transcript_language import classify

# A Windows console writes cp1252 and stops on the · in a status line or a letter of her script, so both
# streams speak UTF-8.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# How much of her script one beat may hold before it is divided at her longest pause inside it. Both are the
# 95th percentile of her own sentences (seconds from first word to last, and word count) across her kept-words
# transcripts: a sentence longer than 19 in 20 of hers carries more than one thing to show.
BEAT_SECONDS = 7.6
BEAT_WORDS = 27
CLOSERS = ".!?"             # what ends a sentence
TRAILING = "\"'’”)"   # quotes and brackets that can sit after the full stop

# The decisions graphics-plan writes into each beat, blank here. `element` is what the line puts on screen:
# a kind from the skill's table (word-card, number-card, list ...) or "face" when it stays on her. `zone` is
# where it goes: "open" (whichever open zone this job's subject-zones.json has), one zone by name (above,
# below, left, right), or "top" for the hook block. `idea` is the direction for whoever builds it; `on_screen`
# is the literal copy, the one field check-plan-language.py can judge; `why` is the reason, kept on plain
# beats too.
PLAN_FIELDS = ("element", "zone", "idea", "on_screen", "why")


def locate_transcript(target):
    """The transcript file itself, or the one inside the job's folder (by path, or by name under projects/)."""
    if target.endswith(".json"):
        return target
    folder = target.rstrip(os.sep)
    by_name = os.path.join(ENGINE, "projects", folder)
    if not os.path.isdir(folder) and os.path.isdir(by_name):
        folder = by_name
    named = os.path.join(folder, "outputs", os.path.basename(folder) + ".transcript.json")
    if os.path.exists(named):
        return named
    for base, _dirs, files in os.walk(folder):
        for name in files:
            if name.endswith(".transcript.json"):
                return os.path.join(base, name)
    sys.exit(f"There is no transcript under {target} yet. Run the rough cut first.")


def spoken_words(path):
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    kept = [w for w in payload.get("words", []) if str(w.get("text", "")).strip()]
    if not kept:
        sys.exit(f"{path} carries no words.")
    return kept


def ends_a_sentence(word):
    return str(word.get("text", "")).strip().rstrip(TRAILING).endswith(tuple(CLOSERS))


# A transcript with NO sentence punctuation at all (the Intel route's transcriber can return bare words) has
# nowhere to split, so the whole reel came out as one sentence: one beat before the length split, and one cue
# where the speaker said seven. Spoken sentences still end in a pause, so on such a transcript a sentence
# closes at a pause instead. "A pause" is measured against this speaker's own rhythm, because the cut has
# already tightened the gaps: PAUSE_FACTOR times her typical gap between words, never under PAUSE_MIN.
PAUSE_MIN = 0.18            # seconds; shorter than this is the space between words, not between sentences
PAUSE_MAX = 0.45            # seconds; a gap this long always closes a sentence on an unpunctuated transcript
PAUSE_FACTOR = 3.0


def is_punctuated(words):
    """True when anything in the transcript ends a sentence. One full stop is enough to trust the text."""
    return any(ends_a_sentence(w) for w in words)


def _gap(prev, word):
    try:
        return float(word["start"]) - float(prev["end"])
    except (KeyError, TypeError, ValueError):
        return 0.0


def pause_threshold(words):
    """The gap, in seconds, that counts as a sentence break for this speaker."""
    gaps = sorted(g for g in (_gap(a, b) for a, b in zip(words, words[1:])) if g > 0)
    typical = gaps[len(gaps) // 2] if gaps else 0.0
    return min(PAUSE_MAX, max(PAUSE_MIN, PAUSE_FACTOR * typical))


def sentences_from(words):
    """Walk the words once, closing a sentence every time one ends. On a transcript with no sentence
    punctuation anywhere, a sentence ends at a pause instead (see PAUSE_MIN)."""
    words = list(words)
    by_pause = not is_punctuated(words)
    limit = pause_threshold(words) if by_pause else None
    run = []
    for word in words:
        if by_pause and run and _gap(run[-1], word) >= limit:
            yield run
            run = []
        run.append(word)
        if not by_pause and ends_a_sentence(word):
            yield run
            run = []
    if run:
        yield run


def widest_breath(run):
    """Index of the word that opens the longest silence inside this run, or None."""
    widest, where = -1.0, None
    for i in range(1, len(run)):
        silence = float(run[i]["start"]) - float(run[i - 1]["end"])
        if silence > widest:
            widest, where = silence, i
    return where


def oversized(run):
    return (float(run[-1]["end"]) - float(run[0]["start"])) > BEAT_SECONDS or len(run) > BEAT_WORDS


def broken_down(run):
    """Break an overlong run at its breaths until every piece can hold one graphic.

    Worked as a stack rather than by recursion: the pieces come out in spoken order, and a pathological
    script cannot blow the interpreter's stack on the way.
    """
    pieces, pending = [], [run]
    while pending:
        piece = pending.pop()
        cut = widest_breath(piece) if oversized(piece) else None
        if cut is None or cut <= 0 or cut >= len(piece):
            pieces.append(piece)
        else:
            pending.extend((piece[cut:], piece[:cut]))   # pushed reversed so order survives the pop
    return pieces


def resolve_language(path, words):
    """What language is this reel, and how sure are we?

    Every string written into the graphics plan goes ON SCREEN, so the plan has to be born knowing
    the language. It used to require a lookup in a second file that a planner had to remember, and a
    lookup you have to remember is one that gets skipped. A real reel shipped with Spanish captions
    under an English hook card because of exactly that.

    ONE TRAP WORTH KNOWING. Transcripts written before v1.0.70 carry `language_code: "en"` on every
    job, including Spanish ones, because that field was a hardcoded string and no detection ever
    happened. So a bare "en" with no `language_verdict` beside it is not evidence of English, it is
    evidence of an old transcript. In that case the words get re-read here rather than trusted.
    """
    payload = {}
    with contextlib.suppress(Exception), open(path, encoding="utf-8") as fh:
        payload = json.load(fh)

    verdict = payload.get("language_verdict")
    code = payload.get("language_code")

    if verdict:                                    # written by a transcript that actually detected
        return {"code": code, "verdict": verdict, "source": "transcript",
                "english_only_ok": verdict == "english"}

    if classify is not None:                       # legacy transcript: re-read the words
        fresh = classify([str(w.get("text", "")) for w in words])
        return {"code": fresh["language_code"], "verdict": fresh["verdict"],
                "source": "re-read here (transcript predates language detection)",
                "english_only_ok": fresh["english_only_checks_ok"]}

    return {"code": None, "verdict": "unknown", "source": "undetermined",
            "english_only_ok": True}


def as_beat(number, piece):
    """One scaffold row: where the beat sits and what is said in it, then the creative fields, empty."""
    row = {
        "id": number,
        "start": round(float(piece[0]["start"]), 2),
        "end": round(float(piece[-1]["end"]), 2),
        "line": " ".join(str(w["text"]).strip() for w in piece),
    }
    row.update(dict.fromkeys(PLAN_FIELDS))       # blank: graphics-plan decides them
    return row


def build_beats(words):
    pieces = [piece for sentence in sentences_from(words) for piece in broken_down(sentence)]
    return [as_beat(number, piece) for number, piece in enumerate(pieces, start=1)]


USAGE = "usage: beat-lines.py <job> [--out FILE]"


def read_args(args):
    """(job, out file or None). The one option is --out; anything else stops with the usage line."""
    target, destination, rest = None, None, list(args)
    while rest:
        word = rest.pop(0)
        if word == "--out":
            if not rest:
                sys.exit(f"--out needs a file to write. {USAGE}")
            destination = rest.pop(0)
        elif word.startswith("--out="):
            destination = word.split("=", 1)[1]
        elif word.startswith("-") or target is not None:
            sys.exit(f"beat-lines.py does not take {word!r}. {USAGE}")
        else:
            target = word
    if not target:
        sys.exit(USAGE)
    return target, destination


def clock(seconds):
    """A time on the cut as she would scrub to it: 0:03.52."""
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def main(args):
    target, destination = read_args(args)
    source = locate_transcript(target)
    words = spoken_words(source)
    beats = build_beats(words)
    language = resolve_language(source, words)
    job = os.path.basename(source)
    job = job[:-len(".transcript.json")] if job.endswith(".transcript.json") else os.path.splitext(job)[0]
    # The scaffold is graphics-plan.json itself with every decision left blank, `format` included, so the
    # creative plan fills it in rather than copying it across. The language rides in it from the start: every
    # `on_screen` string written into a beat lands in frame and must be in THIS language, not the planner's.
    scaffold = {"job": job, "format": None, "duration": round(float(words[-1]["end"]), 2),
                "language": language, "beats": beats}

    if destination:
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        with open(destination, "w", encoding="utf-8") as fh:
            json.dump(scaffold, fh, indent=2)

    say = lambda line: print(line, file=sys.stderr)
    say(f"[beat-lines] {job}: {len(beats)} beats across {clock(scaffold['duration'])}, read from {source}")
    if not is_punctuated(words):
        say("[beat-lines] This transcript has no sentence punctuation, so sentences were split at the "
            "speaker's pauses instead.")
    if language["verdict"] != "english":
        say(f"[beat-lines] LANGUAGE: {language['verdict']}"
            + (f" ({language['code']})" if language.get("code") else "")
            + f" · {language['source']}")
        say("[beat-lines] Every on-screen string in this plan must be written in that language.")
        say("[beat-lines] Captions follow the speaker on their own. Hook and card copy does not.")
    for beat in beats:
        say(f"  {beat['id']:>3}  {clock(beat['start'])} to {clock(beat['end'])}  {beat['line']}")
    if destination:
        say(f"[beat-lines] the scaffold is at {destination}")
    else:
        print(json.dumps(scaffold, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
