#!/usr/bin/env python3
"""kept-words.py — her script: the words her cut keeps, timed to the cut, with her word fixes in.

    python3 .claude/skills/rough-cut/scripts/kept-words.py <words.json> <cuts.json> <out.json> [word-fix table .json]
    python3 .claude/skills/rough-cut/scripts/kept-words.py --plain <words.json> <cuts.json> <out.json>

The rough cut's kept-words transcript is the finished script every later phase treats as truth: the
style plan shows it, graphics-plan writes against it, captions draw it, every format reads it. It is
written here, as outputs/<job>.transcript.json, from two things the stitch already has:

  what she said    transcript/words.json, WhisperX's words with times on her raw clips
  what the cut is  cuts.json, the spans of those clips the cut keeps, in the order they play

Nothing is listened to again. Each kept word moves from its clip's clock to the cut's clock by
subtraction, and a word the cut dropped stays behind. stitch-cut.sh runs this after every stitch,
your-turn.py after she hand-trims in CapCut, and respell.sh after a word fix is added.

Her word fixes are laid into the words on the way out, so a misheard name is put right in one place
and every reader downstream sees it right. Three tables can hold them; each is laid over the one before
it, so the later table wins on a word both name:

  shared     presets/caption-corrections.json, in every copy of the engine (a table named on the
             command line or in $REELS_CAPTION_CORRECTIONS takes its place)
  yours      _local/caption-corrections.json, words that are hers alone; never shipped, never updated
  this reel  projects/<job>/word-fixes.json, a fix that is only right in this one video

A table has three parts, all optional:
  "words"    one word as heard -> the one word it should read; its punctuation stays where it was
  "phrases"  several words as heard -> what they should read, sharing out the time they took
  "check"    real words that are sometimes a mishear: never changed, but listed (⚠ REVIEW) on every
             run so someone reads them where she said them. A word a later table puts right is dropped
             from this list.

Output: {text, language_code, language_verdict, engine, words: [{text, start, end, type}]}, seconds on
the cut's clock. The language is read off the words (transcript_language.py), never assumed.

Never a dead end. A span, a word, a clip entry or a word-fix table that cannot be read is skipped with one
plain line saying so, never the whole script: captions and the creative plan have nothing to read without
this file. --plain is the simplest working route, for when the full one still stops: every word whose start
falls inside a kept span, moved onto the cut's clock exactly as below, with no word fixes and no language
read off the words. stitch-cut.sh reaches for it on its own and says so.
"""
import json
import math
import os
import re
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print → or ⚠
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# Lives in this folder. Guarded, so a broken copy of it costs only the language reading, never her script.
try:
    from transcript_language import classify
except Exception as exc:                         # noqa: BLE001 (any failure to load means the same thing)
    classify = None
    _CLASSIFY_WHY = f"{type(exc).__name__}: {exc}"

USAGE = ("usage: kept-words.py <words.json> <cuts.json> <out.json> [word-fix table .json]\n"
         "       kept-words.py --plain <words.json> <cuts.json> <out.json>")
ENGINE_NOTE = "whisperx-large-v3, remapped onto the cut timeline rather than transcribed again"
PLAIN_ENGINE_NOTE = ENGINE_NOTE + " (simple route: words inside the kept spans, no word fixes)"
TAG = "[kept-words]"

# What was skipped on this run and why, said after the summary. Empty on a normal run, so a normal run
# prints exactly what it always has.
NOTES = []


def note(message):
    if message not in NOTES:
        NOTES.append(message)


def _seconds(value):
    """A time as float seconds, or None when it is missing or not a number. JSON from an older or hand-edited
    file can carry a time as a string ("1.2"), a null or a NaN; a string still reads, the rest mean "no time"."""
    if value is None or isinstance(value, bool):
        return None
    try:
        t = float(value)
    except (TypeError, ValueError):
        return None
    return t if math.isfinite(t) else None


# ============================================================ part 1: what she said, on the cut's clock
# A span that starts a few ms inside a word the cut dropped (snap-to-sound pads every edge) catches a
# scrap of it. Under 50 ms none of that word is heard, so it stays out of her script.
SLIVER = 0.05

# Two spans of one clip that play one after the other and run forward through her footage are one take
# continued (a seam the cut put inside a word): a word they share is ONE play of it and is placed once.
# Edges padded by snap-to-sound and moved to the frame grid can overlap by a few frames; more overlap than
# this means the second span plays footage again (a line copied to the front as a hook, a rewind).
SEAM_OVERLAP = 0.1


def continues(before, now):
    """True when span `now` (clip, start, end) carries on the take span `before` played just ahead of it."""
    if before is None or _stem(before[0]) != _stem(now[0]):
        return False
    return now[1] >= before[1] and now[1] >= before[2] - SEAM_OVERLAP


def placed_already(taken, word, n, before, now):
    """The word was already placed for THIS play of it: by the span just before, which this span continues.
    Placed by any other span, this is the line played again (a cold-open copy, a rewind), so it is placed
    again here and the second play is captioned too."""
    return taken.get(id(word)) == n - 1 and continues(before, now)

# The cut can name a proxy (talk-1080.MOV) of the full-size clip the words were heard from (talk.MOV).
# Both are the same footage, so the proxy's tag is dropped before the two names are compared.
PROXY_TAGS = ("2160", "1440", "1080", "720", "540", "480", "360", "proxy", "review", "preview")
PROXY_TAIL = re.compile(r"-(?:%s)$" % "|".join(PROXY_TAGS), re.IGNORECASE)


def _stem(name):
    """A clip's name without its folder, extension or proxy tag: /raw/talk-1080.MOV -> talk."""
    return PROXY_TAIL.sub("", os.path.splitext(os.path.basename(name))[0])


def index_clips(heard):
    """-> ({file name: its raw words}, {stem: its raw words}) for every clip that was transcribed.

    The lists are the originals, never copies: a word reached from two spans is recognised by being the
    same object, so it must stay the same object whichever way the cut reaches it.

    A clip entry with no name can still be used when it is the only one (the cut can only mean it); with
    several, nothing says which footage it is, so it is left out with a note."""
    clips = heard.get("clips") if isinstance(heard, dict) else None
    if not isinstance(clips, list):
        note("words.json lists no clips, so there are no words to place")
        clips = []
    by_name = {}
    for n, entry in enumerate(clips, 1):
        if not isinstance(entry, dict):
            note(f"clip entry {n} in words.json is not a clip, so it is left out")
            continue
        words = entry.get("words", [])
        if not isinstance(words, list):
            note(f"clip entry {n} in words.json has no word list, so it is left out")
            continue
        name = entry.get("clip")
        if not isinstance(name, str) or not name:
            if len(clips) != 1:
                note(f"clip entry {n} in words.json has no clip name, so its words are left out")
                continue
            name = ""
        by_name[os.path.basename(name)] = words
    by_stem = {_stem(name): words for name, words in by_name.items()}
    return by_name, by_stem


def _matches_a_clip(name, by_name, by_stem):
    """Whether words_for_clip can find the transcribed clip a cut span names (by name, stem, or as the only one)."""
    return (os.path.basename(name) in by_name or by_stem.get(_stem(name)) is not None
            or len(by_name) == 1)


def words_for_clip(name, by_name, by_stem):
    """The raw words behind the clip a cut span names; [] when none can be matched."""
    base = os.path.basename(name)
    if base in by_name:
        return by_name[base]
    same_footage = by_stem.get(_stem(name))
    if same_footage is not None:
        return same_footage
    if len(by_name) == 1:           # only one clip was ever transcribed, so the cut can only mean it
        return next(iter(by_name.values()))
    return []


def _segments(cuts):
    """The cut's spans: {"segments": [...]}, or a bare list of them as an older EDL wrote it."""
    if isinstance(cuts, list):
        return cuts
    segments = cuts.get("segments") if isinstance(cuts, dict) else None
    return segments if isinstance(segments, list) else []


def _ramp_area(ease, u):
    """The integral of a speed ramp's ease from 0 to u (stitch-cut.sh SPEED RAMPS: in = u², out = 1 - (1 - u)²,
    inOut = smoothstep, linear = u)."""
    if ease == "linear":
        return u * u / 2
    if ease == "in":
        return u ** 3 / 3
    if ease == "out":
        return u - (1 - (1 - u) ** 3) / 3
    return u ** 3 - u ** 4 / 2


def ramp_at(ramp, x):
    """For a ramped span: the fraction of its PLAYED time at which it reaches fraction x of its footage (the footage
    runs fast where the speed is high, so a word lands earlier there than a straight division says)."""
    a, b, e = float(ramp["from"]), float(ramp["to"]), ramp.get("ease")
    avg = a + (b - a) * _ramp_area(e, 1.0)
    lo, hi = 0.0, 1.0
    x = min(max(x, 0.0), 1.0)
    for _ in range(40):
        mid = (lo + hi) / 2
        if (a * mid + (b - a) * _ramp_area(e, mid)) / avg < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def kept_spans(cuts):
    """Yield (clip, start, end, lands_at, at) for each span the cut keeps, in playing order; at(t) is where footage
    time t of that span lands on the cut's clock (through its speed, or its speed ramp).

    lands_at is where the span starts on the cut's clock. A span with no length takes no time and is
    skipped. A span with a "speed" (set in CapCut, read back by your-turn) plays length / speed long.
    A span missing its clip, start or end is skipped with a note: the render could not have played it
    either, so it takes no time on the cut."""
    lands_at = 0.0
    for n, segment in enumerate(_segments(cuts), 1):
        try:
            clip = segment["clip"]
            start, end = float(segment["start"]), float(segment["end"])
            speed = float(segment.get("speed", 1.0) or 1.0)
        except (KeyError, TypeError, ValueError, AttributeError):
            note(f"kept span {n} could not be read (it needs a clip, a start and an end), so its words are left out")
            continue
        if not isinstance(clip, str) or not all(math.isfinite(v) for v in (start, end, speed)):
            note(f"kept span {n} could not be read (it needs a clip, a start and an end), so its words are left out")
            continue
        if end - start <= 0:
            continue
        if speed <= 0:
            note(f"kept span {n} has a speed of {speed:g}, so its words are timed at normal speed")
            speed = 1.0
        # the stitch holds a sped span to whole frames and saves that length as "played": the cut's clock runs on it
        try:
            played = float(segment.get("played") or 0) if speed != 1.0 or segment.get("ramp") else 0.0
        except (TypeError, ValueError):
            played = 0.0
        length = played if played > 0 else (end - start) / speed
        ramp = segment.get("ramp") if isinstance(segment.get("ramp"), dict) else None
        if ramp:                                            # a speed ramp: a moment lands where the eased curve reaches it
            at = (lambda t, s0=start, s1=end, la=lands_at, ln=length, r=ramp: la + ramp_at(r, (t - s0) / (s1 - s0)) * ln)
        else:
            at = (lambda t, s0=start, la=lands_at, v=speed: la + (t - s0) / v)
        yield clip, start, end, lands_at, at
        lands_at += length


def _spoken(word):
    text = word.get("word", word.get("w", ""))
    return "" if text is None else str(text).strip()


def _word_times(word, unreadable):
    """(start, end) of one raw word in seconds, or (None, None) when it has none. A word with no time was
    never aligned and is simply passed over; one whose time is there but is not a number is counted, so
    the run can say how many it had to leave out."""
    if not isinstance(word, dict):
        unreadable.append(word)
        return None, None
    raw_start, raw_end = word.get("start"), word.get("end")
    begins, ends = _seconds(raw_start), _seconds(raw_end)
    if (begins is None and raw_start is not None) or (ends is None and raw_end is not None):
        unreadable.append(word)
    return begins, ends


def place_on_cut(cuts, by_name, by_stem):
    """Every word the cut keeps, on the cut's clock, in the order the cut plays them.

    A word that overlaps a kept span is kept, trimmed to the span. Where two spans of one clip meet
    inside a word, that word overlaps both; it is still one word and is placed once. A span that plays
    her footage again (a line copied to the front as a hook, a rewind) places its words again: every
    play of a line is heard, so every play is in her script and gets its captions.

    Each span's words are gathered on their own and only then added, so a span that stops partway is
    left out whole with a note, and every other span still lands in her script."""
    placed, taken, unreadable, unmatched = [], {}, [], {}   # taken: word -> the span that last placed it
    planned = {}                            # each span's edges as the plan wrote them, before snap / frame grid moved them
    for seg in _segments(cuts):
        try:
            planned[(seg["clip"], round(float(seg["start"]), 3))] = seg.get("_snapped_from") or {}
        except (KeyError, TypeError, ValueError, AttributeError):
            pass

    def commit(found, n=0):
        for word, starts, ends in found:
            taken[id(word)] = n
            placed.append({"text": _spoken(word), "start": round(starts, 3), "end": round(ends, 3), "type": "word"})

    before = None                           # the span played just ahead of this one: (clip, start, end)
    for n, (clip, start, end, lands_at, at) in enumerate(kept_spans(cuts), 1):
        now, prev = (clip, start, end), before
        before = now
        if not _matches_a_clip(clip, by_name, by_stem):
            unmatched[os.path.basename(clip)] = unmatched.get(os.path.basename(clip), 0) + 1
            continue
        try:
            found, here = [], set()
            pf = planned.get((clip, round(start, 3)), {})
            p0, p1 = pf.get("start"), pf.get("end")
            for word in words_for_clip(clip, by_name, by_stem):
                begins, ends = _word_times(word, unreadable)
                if begins is None or ends is None:
                    continue                # never aligned (or unreadable), so it has no time to move
                if ends <= start or begins >= end:
                    continue                # entirely outside this span
                kept_by_plan = ((p0 is not None and begins >= float(p0) - 0.005) and   # the plan's own span holds it:
                                (p1 is None or ends <= float(p1) + 0.005))          # a short word ("I", "a") the
                if (begins < start or ends > end) and min(ends, end) - max(begins, start) < SLIVER and not kept_by_plan:   # edge
                    continue                # only a scrap of a dropped word reaches the span      # snapped past is hers
                if id(word) in here:
                    continue
                if placed_already(taken, word, n, prev, now):
                    taken[id(word)] = n     # the same play runs on through this span (a chain of short spans)
                    continue
                here.add(id(word))
                found.append((word, at(max(begins, start)), at(min(ends, end))))
        except Exception as exc:            # noqa: BLE001 (one span's trouble never costs the others)
            note(f"the words of kept span {n} ({os.path.basename(clip)}) could not be placed "
                 f"({type(exc).__name__}: {exc}), so that span is left out of her script")
            continue
        commit(found, n)

    # Her voice laid on its own track (a J-cut lead-in, audio split off its clip in CapCut, read back by
    # your-turn as "audio_overlays") is heard on the cut too, so its words belong in her script. A word
    # already placed from its own video span is not placed twice.
    overlays = cuts.get("audio_overlays", []) if isinstance(cuts, dict) else []
    for n, lay in enumerate(overlays if isinstance(overlays, list) else [], 1):
        try:
            start, end, at = float(lay["start"]), float(lay["end"]), float(lay["target_start"])
            found, here = [], set()
            for word in words_for_clip(lay["clip"], by_name, by_stem):
                begins, ends = _word_times(word, unreadable)
                if begins is None or ends is None or id(word) in taken or id(word) in here:
                    continue
                if (min(ends, end) - max(begins, start)) < 0.5 * (ends - begins):
                    continue                # mostly outside the laid track: only a sliver of it is heard
                here.add(id(word))
                found.append((word, at + max(begins, start) - start, at + min(ends, end) - start))   # plays at 1x
        except Exception as exc:            # noqa: BLE001
            note(f"laid voice track {n} could not be read ({type(exc).__name__}: {exc}), so its words are left out")
            continue
        commit(found, -1)                   # a laid voice track is never a span of its own

    for name, count in unmatched.items():
        note(f"no transcript for the clip {name}, so the {count} kept span(s) from it carry no words in her script")
    if unreadable:
        note(f"{len(set(map(id, unreadable)))} word(s) in words.json had a time that is not a number, so they are left out")

    placed.sort(key=lambda w: w["start"])
    return [w for w in placed if w["text"]]


def place_plain(cuts, by_name, by_stem):
    """The simplest working route: every word whose start falls inside a kept span, moved onto the cut's
    clock the same way place_on_cut moves it (the span's place on the cut, plus how far into the span the
    word starts, over the span's speed), its end held to the span's end. No sliver rule and no laid voice
    tracks: this is what stitch-cut.sh writes when the full route will not finish, so it is kept small.
    A span that plays her footage again places its words again, as place_on_cut does."""
    placed, taken, unreadable = [], {}, []
    before = None
    for n, (clip, start, end, lands_at, at) in enumerate(kept_spans(cuts), 1):
        now, prev = (clip, start, end), before
        before = now
        for word in words_for_clip(clip, by_name, by_stem):
            try:
                begins, ends = _word_times(word, unreadable)
                if begins is None or not (start <= begins < end):
                    continue
                if placed_already(taken, word, n, prev, now):
                    taken[id(word)] = n
                    continue
                ends = begins if ends is None else min(max(ends, begins), end)
                text = _spoken(word)
            except Exception:               # noqa: BLE001 (one odd word never costs the rest)
                continue
            taken[id(word)] = n
            placed.append({"text": text, "start": round(at(begins), 3), "end": round(at(ends), 3), "type": "word"})
    placed.sort(key=lambda w: w["start"])
    return [w for w in placed if w["text"]]


# ======================================================================= part 2: her word fixes
SHARED = ("presets", "caption-corrections.json")    # under the engine root, in every copy
YOURS = ("_local", "caption-corrections.json")      # under the engine root, never shipped
THIS_REEL = "word-fixes.json"                       # in the job folder
THIS_REEL_EARLIER = "corrections.local.json"         # the same file under the name a job folder had before

# A table's parts, and the names each part was written under before. A job folder or an engine kept from
# an earlier version can hold either, so both are read; in one table the earlier name is laid last, since
# an update that merged a table keeps her own entries under the name she wrote them with.
WORDS_KEYS = ("words", "auto")
CHECK_KEYS = ("check", "flag")

# One token as three parts: what leads it, the word, what trails it ("(really?!" -> "(", "really", "?!").
# The caption builders split tokens with this same pattern, so a fix lands on the word they draw.
TOKEN = re.compile(r"^(\W*)(.*?)(\W*)$")


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _engine_roots(out_path):
    """Where the engine may be: above <engine>/projects/<job>/outputs/<file> first, then above this
    script at <engine>/.claude/skills/rough-cut/scripts/. The job's own layout comes first, so an engine
    unpacked anywhere still finds its files."""
    roots = []
    above_out = Path(out_path).resolve().parents
    if len(above_out) >= 4:
        roots.append(above_out[3])
    above_me = Path(__file__).resolve().parents
    if len(above_me) >= 5:
        roots.append(above_me[4])
    return roots


def _shared_file(out_path, explicit):
    """The shared table: the one named on the command line, then $REELS_CAPTION_CORRECTIONS, then the
    engine her script is written into, then the engine this script belongs to. A named file that does
    not exist is passed over, not treated as an error."""
    options = [Path(explicit)] if explicit else []
    # CAPTION_CORRECTIONS: older name, still accepted
    named = os.environ.get("REELS_CAPTION_CORRECTIONS") or os.environ.get("CAPTION_CORRECTIONS")
    if named:
        options.append(Path(named))
    options += [root.joinpath(*SHARED) for root in _engine_roots(out_path)]
    return next((option for option in options if option.exists()), None)


def _yours_file(out_path):
    return next((root.joinpath(*YOURS) for root in _engine_roots(out_path)
                 if root.joinpath(*YOURS).exists()), None)


def _this_reel_files(out_path):
    """The job's own table(s): <job>/outputs/<file> puts the job two levels up. Where a job folder holds the
    table under both names, the current one is laid last."""
    above = Path(out_path).resolve().parents
    if len(above) < 2:
        return []
    return [above[1] / name for name in (THIS_REEL_EARLIER, THIS_REEL) if (above[1] / name).exists()]


def fix_files(out_path, explicit=None):
    """-> [(layer, path), ...]: the word-fix files this job reads, in the order they are laid down."""
    found = [("shared", _shared_file(out_path, explicit)), ("yours", _yours_file(out_path))]
    found += [("this reel", path) for path in _this_reel_files(out_path)]
    return [(layer, path) for layer, path in found if path is not None]


def read_table(path):
    """One word-fix table as {"words": {heard: written}, "phrases": {heard: written}, "check": [word, ...]},
    whichever names its parts were written under."""
    table = _read_json(path)
    words = {}
    for key in WORDS_KEYS:
        words.update(table.get(key) or {})
    check = []
    for key in CHECK_KEYS:
        check += [word for word in table.get(key) or [] if word not in check]
    return {"words": words, "phrases": dict(table.get("phrases") or {}), "check": check}


def _lowered(mapping):
    """The same mapping keyed in lowercase. Two spellings of one key: the later one wins."""
    return {key.lower(): value for key, value in mapping.items()}


def lay_fixes(files):
    """-> (swaps, check, phrases), keys lowercased, each table laid over the ones before it.

    A table that cannot be read (broken JSON, a part of the wrong shape) is passed over with a note; the
    other tables still apply, and her script is never held back for one."""
    swaps, check, phrases = {}, set(), {}
    for layer, path in files:
        try:
            table = read_table(path)
            words = {str(k).lower(): str(v) for k, v in table["words"].items()}
            flagged = {str(word).lower() for word in table["check"]}
            phrased = {str(k).lower(): v for k, v in table["phrases"].items()}
        except Exception as exc:            # noqa: BLE001
            note(f"the word-fix table ({layer}) could not be read ({type(exc).__name__}: {exc}), "
                 f"so its fixes are not laid this time: {path}")
            continue
        swaps.update(words)
        check = (check | flagged) - set(swaps)
        phrases.update(phrased)
    return swaps, check, phrases


def corrections_for(out_path, explicit=None):
    """-> (swaps, check, phrases) for the job her script is written into: every table, laid."""
    return lay_fixes(fix_files(out_path, explicit))


def fix_tokens(words, swaps, check):
    """The one-word fixes, made in place. -> ([(as heard, as written), ...], [words to check, ...])."""
    fixed, doubtful = [], []
    for word in words:
        lead, core, trail = TOKEN.match(word["text"]).groups()
        key = core.lower()
        if key in swaps:
            word["text"] = lead + swaps[key] + trail
            fixed.append((core, swaps[key]))
        elif key in check:
            doubtful.append(core)
    return fixed, doubtful


def _respell(span, parts):
    """The written words, sharing out exactly the time the heard ones covered.

    The first starts where the span started and the last ends where it ended, so no caption edge and no
    cut moves; the time between is split evenly, since a fix can change how many words there are.
    Punctuation that trailed the last heard word trails the last written one."""
    start, end = span[0]["start"], span[-1]["end"]
    trail = TOKEN.match(span[-1]["text"]).group(3)
    step = (end - start) / len(parts) if parts else 0
    last = len(parts) - 1
    return [{
        "text": part + (trail if j == last else ""),
        "start": round(start + j * step, 3),
        "end": end if j == last else round(start + (j + 1) * step, 3),
        "type": "word",
    } for j, part in enumerate(parts)]


def fix_phrases(words, phrases):
    """The several-word fixes. -> (the new word list, [(as heard, as written), ...]).

    A name heard as ordinary words ("chat gpt") cannot be written as one token, so it is matched as a run
    of lowercased word cores: a comma or a capital never blocks it. Longer phrases are tried first, so a
    phrase beats its own opening words; the pass moves left to right and never revisits what it wrote,
    so overlapping phrases cannot fight and every run gives the same result."""
    if not phrases or not words:
        return words, []
    wanted = [(key, key.split()) for key in sorted(phrases, key=lambda k: len(k.split()), reverse=True)]
    wanted = [(key, tokens) for key, tokens in wanted if tokens]     # a blank key matches nothing
    cores = [TOKEN.match(w["text"]).group(2).lower() for w in words]
    result, applied = [], []
    i = 0
    while i < len(words):
        hit = next(((key, tokens) for key, tokens in wanted if cores[i:i + len(tokens)] == tokens), None)
        if hit is None:
            result.append(words[i])
            i += 1
            continue
        key, tokens = hit
        result.extend(_respell(words[i:i + len(tokens)], str(phrases[key]).split()))
        applied.append((key, phrases[key]))
        i += len(tokens)
    return result, applied


# ========================================================================= part 3: write and say
SPACE_BEFORE_MARK = re.compile(r"\s+([,.!?;:])")    # what a join leaves: "so , anyway" -> "so, anyway"


def heard_language(words_json, heard):
    """The one language the listener heard across every clip, or None. This is detection, not a guess: WhisperX
    names the language it heard (in the diagnostics beside words.json), and the faster-whisper route names it
    per clip inside words.json itself. None when the clips disagree, or nothing was recorded."""
    try:
        langs = set()
        with_lang = [c.get("languages") for c in (heard.get("clips") or []) if isinstance(c, dict)]
        if with_lang and all(with_lang):
            # Usually {code: probability}; a single code written as a plain string is that code, never its
            # first letter.
            langs = {l if isinstance(l, str) else next(iter(l)) for l in with_lang}
        else:
            diag = _read_json(os.path.join(os.path.dirname(os.path.abspath(words_json)),
                                           ".transcribe-diagnostics.json"))
            langs = set((diag.get("language_forced") and [diag["language_forced"]])
                        or (diag.get("detected_languages") or {}))
        return str(next(iter(langs))).lower() if len(langs) == 1 else None
    except Exception:                       # noqa: BLE001 (nothing recorded = nothing detected)
        return None


def _read_language(texts):
    """transcript_language.classify, or "unknown" with no code when it cannot run: a missing reading
    never stops her script, and an unknown code is never filled in by guessing."""
    if classify is not None:
        try:
            return classify(texts)
        except Exception as exc:            # noqa: BLE001
            note(f"the language could not be read off the words ({type(exc).__name__}: {exc}), so it is left unknown")
    else:
        note(f"the language reader did not load ({_CLASSIFY_WHY}), so the language is left unknown")
    return {"language_code": None, "verdict": "unknown"}


def write_script(out_path, words, heard_lang=None, engine=ENGINE_NOTE, read_words=True):
    text = SPACE_BEFORE_MARK.sub(r"\1", " ".join(w["text"] for w in words)).strip()
    # Every caption and graphic downstream trusts the language recorded here. The words are read for it
    # (transcript_language.py), and when they are not confidently English the code stays empty rather than
    # guessed: a guessed code is as wrong as a hardcoded one, only pointed somewhere else. What the listener
    # DETECTED is not a guess, though: a German reel full of English loanwords read as "mixed" with no code,
    # while WhisperX had heard de at 1.00, and the captions could not tell it was German. So one language
    # heard across every clip, other than English, is recorded as the reel's language.
    if read_words:
        language = _read_language([w["text"] for w in words])
        code, verdict, source = language["language_code"], language["verdict"], "read off the words"
    else:                                   # the plain route reads nothing it does not have to
        code, verdict, source = None, "unknown", "not read (simple route)"
    if heard_lang and heard_lang != "en":
        code, verdict, source = heard_lang, "non_english", "heard by the listener"
    # Written beside the target and swapped in whole, so a run that stops partway never leaves half a file
    # (or a broken one) where captions will look for her script.
    partial = f"{out_path}.partial"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)   # a missing outputs/ is no reason to stop
    with open(partial, "w", encoding="utf-8") as fh:
        json.dump({
            "text": text,
            "language_code": code,
            "language_verdict": verdict,
            "language_source": source,
            "engine": engine,
            "words": words,
        }, fh, indent=2)
    os.replace(partial, out_path)


def _pairs(pairs):
    return ", ".join(f"{a}→{b}" for a, b in sorted(set(pairs)))


def say_notes():
    for message in NOTES:
        print(f"{TAG} note: {message}")


def say(out_path, words, files, fixed, rephrased, doubtful):
    print(f"{TAG} her script: {len(words)} words on the cut → {out_path}")
    if files:
        print(f"{TAG} word fixes laid from: " + " · ".join(f"{layer} {path}" for layer, path in files))
    else:
        print(f"{TAG} no word-fix file found, so every word stays as heard")
    if fixed:
        print(f"{TAG}   one word: {_pairs(fixed)}")
    if rephrased:
        print(f"{TAG}   several words: {_pairs(rephrased)}")
    if doubtful:
        print(f"{TAG} ⚠ REVIEW where she said them (real words, sometimes misheard): "
              + ", ".join(sorted(set(doubtful))))


def _read_input(path, what):
    """One input file, or a plain one-line stop naming it. Exit 2 = an input could not be read, which no
    route here can get past; stitch-cut.sh tells her how the rough cut makes a fresh one."""
    try:
        return _read_json(path)
    except Exception as exc:                # noqa: BLE001
        sys.exit(f"{TAG} {what} could not be read ({type(exc).__name__}: {exc}): {path}")


def main_plain(words_json, cuts_json, out_path):
    heard = _read_input(words_json, "the word timings (words.json)")
    cuts = _read_input(cuts_json, "the cut (cuts.json)")
    words = place_plain(cuts, *index_clips(heard))
    write_script(out_path, words, heard_language(words_json, heard), engine=PLAIN_ENGINE_NOTE, read_words=False)
    print(f"{TAG} her script, the simple way (words inside the kept spans, no word fixes): "
          f"{len(words)} words on the cut → {out_path}")
    say_notes()


def main():
    args = sys.argv[1:]
    if args[:1] == ["--plain"]:
        if len(args) != 4:
            sys.exit(USAGE)
        return main_plain(*args[1:])
    if len(args) not in (3, 4):
        sys.exit(USAGE)
    words_json, cuts_json, out_path = args[:3]
    explicit = args[3] if len(args) == 4 else None

    heard = _read_input(words_json, "the word timings (words.json)")
    cuts = _read_input(cuts_json, "the cut (cuts.json)")
    files = fix_files(out_path, explicit)
    swaps, check, phrases = lay_fixes(files)
    words = place_on_cut(cuts, *index_clips(heard))

    # One-word fixes first, then phrases, so a phrase is matched against the script as it reads once the
    # one-word fixes are in, not against the raw transcription. Fixes are a polish on her words, never a
    # reason to have none: if laying them stops, her script goes out as heard, with a note.
    fixed, doubtful, rephrased = [], [], []
    try:
        trial = [dict(w) for w in words]
        fixed, doubtful = fix_tokens(trial, swaps, check)
        trial, rephrased = fix_phrases(trial, phrases)
        words = trial
    except Exception as exc:                # noqa: BLE001
        fixed, doubtful, rephrased = [], [], []
        note(f"her word fixes could not be laid ({type(exc).__name__}: {exc}), so every word stays as heard")

    write_script(out_path, words, heard_language(words_json, heard))
    say(out_path, words, files, fixed, rephrased, doubtful)
    say_notes()


if __name__ == "__main__":
    main()
