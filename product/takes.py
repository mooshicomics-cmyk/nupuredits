#!/usr/bin/env python3
"""takes.py — the deterministic take-chooser (build #1 of the decision refactor).

Why this exists
---------------
A Yap is one script said several times over. The engine's job is to keep the cleanest full delivery
of each line and drop the rest. Today that decision is partly deterministic (transcript-cut.py keeps
the LAST take of each line) and partly model judgment per run, which is why the same footage can cut
two ways. This module makes the whole take decision deterministic, measured on her transcript AND the
waveform, so the same footage always chooses the same takes. REE's stitch still owns the millisecond
edges (snap-to-sound / close-pauses / trim-restarts); this only chooses WHICH takes play.

The machine (studied from a best-in-class peer engine, built as OUR own, tuned to HER footage — never
its numbers; see dev-tools/ENGINE-IMPROVEMENTS.md §1):
  1. sentences      — words into sentences (punctuation, or a gap longer than a breath)
  2. lines          — sentences that say nearly the same thing are takes of one line
  3. retakes        — fold the reworded / shorter / broken-off retakes whole-sentence likeness misses
  4. flaws          — what's wrong with each take, measured: restart, dragged word (voiced ms vs HER
                      pace), broken-off last word, fillers, no sound under it (needs the waveform)
  5. run-throughs   — did she say the whole script several times? which take belongs to which pass
  6. spine          — when she did, keep ONE pass (loudest on most lines, else her last full pass);
                      when she didn't (her usual single-pass style), there is no spine and we keep the
                      last clean take of each line. Graceful either way — never a dead end.

Status: PROPOSAL stage. Reads words.json, proposes the cut, diffs against the existing cut. Meant to
feed REE's real stitch for a full-pipeline proof, not a bare preview.

usage:
  takes.py pace [<job>]            her measured talking pace (a clip's own, or the whole corpus)
  takes.py <job> [--print]         propose the cut; --print lists kept pieces
  takes.py <job> --diff            how it differs from the job's existing cuts.json
  takes.py <job> --why             explain every take decision (kept / dropped / spine)
  takes.py <job> --write PATH      write the proposed cut (segments) as a cuts.json
  takes.py <job> [--no-audio]      skip the waveform (drag/silent/spine energy degrade to transcript-only)
"""
import json, os, sys, re, glob, array, shutil, statistics, subprocess, unicodedata, importlib.util
from difflib import SequenceMatcher

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── dials ────────────────────────────────────────────────────────────────────────────────────────
# Structural defaults carried over from the studied machine, each to be fit to you against the scorecard
# (§0), never by feel. Pace is measured from HER words at runtime; the rest are structural ratios.
SENTENCE_GAP_MS          = 600
UTTERANCE_BREAK_PAUSE_MS = 600

LINE_SAME_RATIO   = 0.55   # difflib ratio over normalised tokens: takes of one line
LINE_CONTAINED_SHARE = 0.85
LINE_CONTAINED_MIN_TOKENS = 3
LINE_SAID_AGAIN_RATIO = 0.80

# retake folding (studied peer values; structural, tune against her reels)
RETAKE_WINDOW     = 5      # a retake lands within this many sentences of its line
RETAKE_PREFIX_MIN = 2
RETAKE_LONG_OPEN  = 5
RETAKE_OPEN_MIN   = 3
RETAKE_COVER      = 0.6
RETAKE_INSIDE_COVER = 0.8
RETAKE_INSIDE_MIN = 5
RETAKE_INSIDE_LONGER = 2.5
RETAKE_OPEN_SLACK = 2

# run-throughs / spine
CUT_RUN_REPEAT_GAP   = 4   # a line said again ≥ this many takes later = she went back to the top
CUT_RUN_NOISY_TIMES  = 2   # a line with > this × the usual number of takes never anchors a run or votes
CUT_SPINE_FULL       = 0.5 # a run counts only if it says ≥ this share of the fullest run's lines
CUT_SPINE_LOUD_SHARE = 0.4 # energy wins if loudest on ≥ this share of voted lines, else her last full run

# flaws
BROKEN_WORD_PROBABILITY = 0.40  # a final word the aligner only half-heard (ends a broken-off take)
DRAG_MIN_MS  = 600              # a word under this is never "dragged"
DRAG_TIMES   = 3.0              # ...and must also run ≥ this × HER median voiced-ms-per-letter in this clip
CORPUS_MS_PER_LETTER = 50.0     # fallback pace when a clip is too short to measure (her corpus median)

# filler core (kept in sync with transcript-cut.py; full multilingual sets live there)
FILLER_WORDS = frozenset({"um", "uh", "uhm", "umm", "ah", "em", "er", "erm", "hmm", "mm"})
FILLER_ONLY = FILLER_WORDS | frozenset({"so","and","but","like","okay","ok","yeah","well","i","you","it","the","a",
                                        "este","eh","pues","bueno","entonces","o","sea","osea","y","pero","vale"})
WARMUP = {"here","we","go","okay","ok","alright","all","right","ready","lets","let's","let","s","and","action",
          "three","two","one","3","2","1","um","uh","so","start","starting","rolling","recording","test","testing"}
LEAD_INS = frozenset({"okay","ok","so","and","um","uh","now","alright","yeah","well","oh"})
# A one- or two-word "sentence" that is ONLY a connective ("Unless.", "Because.", "But when.") is the
# broken-off start of the line she then restarts — never a real beat. A content word held alone
# ("Never.", "Done.") is NOT in here and stays.
DANGLING = frozenset({"unless","because","and","but","so","or","if","when","while","which","where",
                      "though","although","since","then","that","as"})
AMOUNT = re.compile(r"^\W*(?:[$€£¥]\d[\d,.]*[kKmMbB]?|\d[\d,.]*\s*(?:%|[kKmMbB])|\d{1,3}(?:,\d{3})+(?:\.\d+)?)\W*$")

ENVELOPE_FRAME_MS = 20


# ── effect-cue exemption (a line that names an effect is never dropped) ────────────────────────────
_CUE = None
def _cue_reader():
    try:
        spec = importlib.util.spec_from_file_location("spoken_cues", os.path.join(ENG, "product", "spoken_cues.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.names_an_effect
    except Exception:
        return lambda text: False
def names_an_effect(wtexts):
    global _CUE
    if _CUE is None: _CUE = _cue_reader()
    return _CUE(" ".join(wtexts))


# ── words ──────────────────────────────────────────────────────────────────────────────────────────
def load_words(job):
    """First clip's words as {text, start_ms, end_ms, prob}. One-clip jobs (the everyday path)."""
    d = json.load(open(f"{job}/transcript/words.json", encoding="utf-8"))
    cw = d["clips"][0]["words"] if isinstance(d, dict) and "clips" in d else d
    out = []
    for x in cw:
        t = x.get("word", x.get("w", "")); s = x.get("start", x.get("s")); e = x.get("end", x.get("e"))
        if s is None or e is None: continue
        out.append({"text": t, "start_ms": int(round(s * 1000)), "end_ms": int(round(e * 1000)),
                    "prob": x.get("score", x.get("probability"))})
    return out


def _normal(text):
    return "".join(c for c in unicodedata.normalize("NFC", (text or "").lower()) if unicodedata.category(c)[0] in "LMN")

def _letters(text):
    return max(1, len(_normal(text)))

def is_amount(text):
    return bool(AMOUNT.match(text or ""))

def is_filler(w):
    return w["text"].strip(" ,.?!…-").lower() in FILLER_WORDS


# ── the waveform envelope (reused decode pattern from snap-to-sound.py; measurement only) ──────────
class Envelope:
    """Loudness per frame and the level below which a frame is silence, for one clip."""
    def __init__(self, db, floor):
        self.db = db; self.floor = floor
    def is_silent(self, f):
        return f < 0 or f >= len(self.db) or self.db[f] < self.floor
    def loudness(self, start_ms, end_ms):
        a = start_ms // ENVELOPE_FRAME_MS
        fr = range(a, min(max(end_ms // ENVELOPE_FRAME_MS, 1), len(self.db)))
        voiced = [self.db[f] for f in fr if self.db[f] >= self.floor]
        return round(sum(voiced) / len(voiced), 1) if voiced else self.floor
    def voiced_ms(self, start_ms, end_ms):
        a = start_ms // ENVELOPE_FRAME_MS
        fr = range(a, min(max(end_ms // ENVELOPE_FRAME_MS, 1), len(self.db)))
        return sum(ENVELOPE_FRAME_MS for f in fr if self.db[f] >= self.floor)


def build_envelope(clip_path):
    """16 kHz mono f32 → per-frame RMS dBFS → an Envelope. None when the audio can't be read (the
    chooser then degrades to transcript-only drag/silent and no energy vote). Never a dead end."""
    if not clip_path or not os.path.exists(clip_path):
        return None
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", clip_path, "-ac", "1", "-ar", "16000",
           "-f", "f32le", "-"]
    try:
        pcm = subprocess.run(cmd, capture_output=True, timeout=300).stdout
    except Exception:
        return None
    samples = array.array("f")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % samples.itemsize])
    if not samples:
        return None
    import math
    per = int(16000 * ENVELOPE_FRAME_MS / 1000)   # samples per frame
    db = []
    for i in range(0, len(samples), per):
        chunk = samples[i:i + per]
        if not chunk:
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        db.append(20 * math.log10(rms) if rms > 1e-7 else -120.0)
    if not db:
        return None
    # noise floor: a touch above the quiet end of the clip, with an absolute safety net. Voiced frames
    # (her words) sit well above it; her room tone below. Relative, so a quiet clip still separates.
    ranked = sorted(db)
    p15 = ranked[int(0.15 * len(ranked))]
    floor = max(-55.0, p15 + 6.0)
    return Envelope(db, floor)


# ── sentences ───────────────────────────────────────────────────────────────────────────────────
def sentences(words, gap_ms=SENTENCE_GAP_MS):
    out = []; first = 0
    for i, w in enumerate(words):
        gap = (words[i + 1]["start_ms"] - w["end_ms"]) if i + 1 < len(words) else None
        if gap is None or gap > gap_ms or w["text"].rstrip().endswith((".", "?", "!")):
            out.append((first, i)); first = i + 1
    return out

def sent_tokens(words, sent):
    return [t for t in (_normal(words[i]["text"]) for i in range(sent[0], sent[1] + 1)) if t]

def sent_text(words, sent):
    return " ".join(words[i]["text"] for i in range(sent[0], sent[1] + 1)).strip()

# keep `toks` as an alias some callers/tests use
def toks(words_or_sent, sent=None):
    if sent is None:  # called as toks(list_of_word_dicts)
        return [t for t in (_normal(w["text"]) for w in words_or_sent) if t]
    return sent_tokens(words_or_sent, sent)


# ── pace ────────────────────────────────────────────────────────────────────────────────────────
def measure_pace(words, envelope=None):
    """Her median ms-per-letter in THIS clip. Measured on VOICED ms when the waveform is available
    (the stamp swallows the pause after a word), else on the stamp span. Corpus fallback for short
    clips. The yardstick the drag rubric measures each word against."""
    vals = []
    for w in words:
        if is_amount(w["text"]): continue
        n = _letters(w["text"])
        if n < 2: continue
        dur = envelope.voiced_ms(w["start_ms"], w["end_ms"]) if envelope else (w["end_ms"] - w["start_ms"])
        if dur > 0: vals.append(dur / n)
    return statistics.median(vals) if len(vals) >= 20 else CORPUS_MS_PER_LETTER

def corpus_pace():
    vals = []
    for wf in glob.glob(os.path.join(ENG, "projects", "*", "transcript", "words.json")):
        try: d = json.load(open(wf, encoding="utf-8"))
        except Exception: continue
        for c in (d.get("clips") or []) if isinstance(d, dict) else []:
            for w in c.get("words", []):
                if w.get("start") is None or w.get("end") is None or is_amount(w.get("word", "")): continue
                n = _letters(w.get("word", "")); dur = (w["end"] - w["start"]) * 1000
                if n >= 2 and dur > 0: vals.append(dur / n)
    return {"n": len(vals), "median": statistics.median(vals) if vals else None,
            "mean": statistics.mean(vals) if vals else None}


# ── lines: takes of one line ──────────────────────────────────────────────────────────────────────
def _contained(short, long):
    """`short` is a fragment of `long`: nearly ALL of short appears as one contiguous run inside long.
    A short saying must be fully present (so "where I was stuck" is NOT "contained" in "where I was,
    what worked," — they only share the opener "where I was"; they are parallel list items). Only a
    longer saying may drop a word or two of fuzz."""
    if not short or len(short) >= len(long): return False
    need = max(LINE_CONTAINED_MIN_TOKENS, len(short) - len(short) // 6)
    m = SequenceMatcher(None, short, long).find_longest_match(0, len(short), 0, len(long))
    return m.size >= need

# Function words carry no line identity: an overlap made only of these is not a shared line. (A
# shared CONTENT phrase like her "in the margins of motherhood" must NOT force a join either — that
# is handled by the ratio staying below LINE_SAME_RATIO for genuinely different lines; this set only
# stops a gluey SHORT overlap from faking a high ratio.)
GLUE = frozenset("""a an the and or but so if then as of to in on at by for with from into about up out over
i im ive me my we our you your he she it its they them this that these those there here what which who
is am are was were be been do does did have has had will would can could should may might must not no yes
just only also too very really even still all any some each more most now one okay ok yeah oh well like
where when why how whom whose there here""".split())

def _joins(a, b):
    """Two sayings are takes of one line when one contains the other, or they are alike overall AND
    share at least one real (non-glue) word in the match. A middling difflib ratio propped up only by
    scattered glue words ("and", "I") is NOT a shared line — that is what pulled "And then I thought,"
    into the "I don't think it was luck" line (85k, 2026-11-03)."""
    if _contained(a, b) or _contained(b, a):
        return True
    sm = SequenceMatcher(None, a, b)
    if sm.ratio() < LINE_SAME_RATIO:
        return False
    matched = [a[m.a + k] for m in sm.get_matching_blocks() for k in range(m.size)]
    return any(t not in GLUE for t in matched)

def group_lines(sents, T):
    """Greedy, time-ordered: a sentence joins the line it belongs with (`_joins`), the best-matching
    one when several, else opens a new line. Returns lists of sentence indexes."""
    groups = []
    for i, mine in enumerate(T):
        if not mine: continue
        best, best_r = None, -1.0
        for g in groups:
            if not any(_joins(mine, T[j]) for j in g):
                continue
            r = max(SequenceMatcher(None, mine, T[j]).ratio() for j in g)
            if r > best_r:
                best, best_r = g, r
        (groups.append([i]) if best is None else best.append(i))
    return groups


# ── retakes: fold the ones whole-sentence likeness misses ──────────────────────────────────────────
def _body(toks_):
    n = 0
    while n < len(toks_) and toks_[n] in LEAD_INS: n += 1
    return toks_[n:]

def _opening(a, b):
    best = (0, 0, 0)
    for i in range(min(RETAKE_OPEN_SLACK + 1, len(a))):
        for j in range(min(RETAKE_OPEN_SLACK + 1, len(b))):
            n = 0
            while i + n < len(a) and j + n < len(b) and a[i + n] == b[j + n]: n += 1
            if n > best[0] or (n == best[0] and i + j < best[1] + best[2]): best = (n, i, j)
    return best

def _covered(a, b):
    if not a: return 0.0
    blocks = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(m.size for m in blocks) / len(a)

def is_retake(earlier, later):
    """Whether the earlier saying (tokens) is a take of the later one's line."""
    a, b = _body(earlier), _body(later)
    if not a or not b: return False
    if a == b: return len(a) >= RETAKE_PREFIX_MIN
    n, i, j = _opening(a, b)
    if i == 0 and n == len(a): return len(a) >= RETAKE_PREFIX_MIN   # broke off and started over
    if n == len(b): return False                                    # the later one breaks off inside hers
    if n >= RETAKE_LONG_OPEN: return True
    if (n >= RETAKE_OPEN_MIN and len(b) >= len(a) * RETAKE_COVER and _covered(a, b) >= RETAKE_COVER
            and _covered(a[i + n:], b[j + n:]) >= RETAKE_COVER):
        return True
    return (len(a) >= RETAKE_INSIDE_MIN and len(a) < len(b) <= len(a) * RETAKE_INSIDE_LONGER
            and _covered(a, b) >= RETAKE_INSIDE_COVER)

def retakes(sents, T):
    """earlier sentence index -> the later one whose line it is a take of."""
    out = {}
    for i in range(len(sents)):
        if i in out: continue
        for j in range(i + 1, min(len(sents), i + 1 + RETAKE_WINDOW)):
            if is_retake(T[i], T[j]): out[i] = j; break
    return out


# ── flaws (measured) ────────────────────────────────────────────────────────────────────────────
def dragged_words(words, envelope, pace):
    """Indexes of words she stretched out ("tiiime"): voiced ms ≥ max(DRAG_MIN_MS, DRAG_TIMES × her
    median ms/letter × letters). Measured on sound inside the word when the waveform is there, else
    on the stamp span (coarser)."""
    out = set()
    thr_letter = DRAG_TIMES * pace
    for i, w in enumerate(words):
        if is_amount(w["text"]): continue
        dur = envelope.voiced_ms(w["start_ms"], w["end_ms"]) if envelope else (w["end_ms"] - w["start_ms"])
        if dur >= max(DRAG_MIN_MS, thr_letter * _letters(w["text"])): out.add(i)
    return out

def flaws_of(words, sent, envelope, drags, is_first_real):
    tk = sent_tokens(words, sent)
    wtexts = [words[i]["text"] for i in range(sent[0], sent[1] + 1)]
    cue = names_an_effect(wtexts)
    pairs = list(zip(tk, tk[1:]))
    restart = len(pairs) != len(set(pairs)) and len(tk) >= 3
    drag = sum(1 for i in range(sent[0], sent[1] + 1) if i in drags)
    last = words[sent[1]]
    broken = (last["text"].rstrip().endswith("...")
              or (last.get("prob") is not None and last["prob"] < BROKEN_WORD_PROBABILITY
                  and not last["text"].rstrip().endswith((".", "?", "!"))))
    fillers = sum(1 for i in range(sent[0], sent[1] + 1) if is_filler(words[i]))
    if envelope is not None:
        a, b = sent[0], sent[1]
        fr = range(words[a]["start_ms"] // ENVELOPE_FRAME_MS,
                   max(words[a]["start_ms"] // ENVELOPE_FRAME_MS + 1, words[b]["end_ms"] // ENVELOPE_FRAME_MS))
        silent = all(envelope.is_silent(f) for f in fr)
        loud = envelope.loudness(words[a]["start_ms"], words[b]["end_ms"])
    else:
        silent = False; loud = 0.0
    n = len(tk)
    filler_only = (not cue) and 1 <= n <= 2 and all(t in FILLER_ONLY or t in DANGLING for t in tk)
    warmup = (not cue) and is_first_real and 1 <= n <= 5 and all(t in WARMUP for t in tk)
    junk = (not cue) and (filler_only or warmup or silent)
    return {"restart": restart, "drags": drag, "broken": broken and not cue, "fillers": fillers,
            "silent": silent, "loud": loud, "cue": cue, "n_tok": n,
            "filler_only": filler_only, "warmup": warmup, "junk": junk}

def _flaw_words(f):
    bits = []
    if f["broken"]: bits.append("last word broken off")
    if f["restart"]: bits.append("a restart inside it")
    if f["drags"]: bits.append(f"{f['drags']} dragged word{'s' if f['drags']>1 else ''}")
    if f["silent"]: bits.append("no sound under it")
    return ", ".join(bits) or "clean"

def is_disqualifying(f):
    """A flaw that makes a take lose to a clean sibling of the same line."""
    return f["broken"] or f["restart"] or f["silent"] or f["drags"] > 0


ABANDONED_SHARE = 0.72   # a sibling shorter than this fraction of a fuller take is an abandoned start

def fragments_in_line(g, T):
    """Takes in one line that are an abandoned start of a fuller sibling, not a delivery of their own:
    a near-contiguous fragment of it, or a short restart-prefix that breaks off, AND substantially
    shorter. These lose to the fuller take regardless of order, so "her last take wins" never keeps the
    stub "You unlock something," over the finished "you unlock something in the minds of the people
    standing around you." A near-equal-length reword clears the gate and stays a real take."""
    frag = set()
    for a in g:
        ta = T[a]
        if not ta: continue
        for b in g:
            if b == a: continue
            tb = T[b]
            if len(ta) >= ABANDONED_SHARE * len(tb): continue
            n = min(len(ta), len(tb), 4)
            restart_prefix = n >= 3 and ta[:n] == tb[:n]
            short_run = 1 <= len(ta) <= 2 and len(tb) >= len(ta) + 2 and any(tb[k:k + len(ta)] == ta for k in range(len(tb) - len(ta) + 1))
            if restart_prefix or _contained(ta, tb) or short_run:
                frag.add(a); break
    return frag


# ── run-throughs + spine ────────────────────────────────────────────────────────────────────────
def noisy_lines(line_takes):
    counts = [len(t) for t in line_takes if len(t) > 1]
    if not counts: return set()
    usual = statistics.median(counts)
    return {n for n, t in enumerate(line_takes) if len(t) > CUT_RUN_NOISY_TIMES * usual}

def run_throughs(line_takes):
    noisy = noisy_lines(line_takes)
    order = sorted((s, n) for n, tk in enumerate(line_takes) for s in tk)
    if not order: return {}, noisy
    opener = order[0][1]; run_starts = [0]; seen = {}
    for pos, (s, n) in enumerate(order):
        if n not in noisy and n in seen and pos - seen[n] >= CUT_RUN_REPEAT_GAP:
            back = [q for q in range(seen[n] + 1, pos + 1) if order[q][1] == opener and q > run_starts[-1]]
            if back:
                begin = back[0]
            else:
                begin = pos
                while begin - 1 > max(seen[n], run_starts[-1]):
                    m = order[begin - 1][1]
                    if m not in noisy and not any(order[q][1] == m for q in range(run_starts[-1], begin - 1)): break
                    begin -= 1
            run_starts.append(begin); seen = {order[q][1]: q for q in range(begin, pos)}
        seen[n] = pos
    bounds = run_starts + [len(order)]
    return {order[q][0]: r for r, (a, b) in enumerate(zip(bounds, bounds[1:])) for q in range(a, b)}, noisy

def spine(line_takes, run_of, noisy, loud_of):
    """The run-through that plays, or None (not a set of run-throughs → keep last-take). `loud_of`:
    sentence index -> take loudness_db (for the energy vote); empty ⇒ last-full-run only."""
    from collections import Counter
    said = Counter(r for n, tk in enumerate(line_takes) if n not in noisy for r in {run_of.get(s, 0) for s in tk})
    if len(said) < 2: return None
    fullest = max(said.values())
    if fullest < CUT_SPINE_FULL * (len(line_takes) - len(noisy)): return None
    full = sorted(r for r, c in said.items() if c >= CUT_SPINE_FULL * fullest)
    if len(full) < 2: return None
    votes = Counter(); voted = 0
    for n, tk in enumerate(line_takes):
        if n in noisy or len({run_of.get(s, 0) for s in tk}) < 2: continue
        voted += 1
        if loud_of:
            loudest = max(tk, key=lambda s: (loud_of.get(s, -120.0), s))
            votes[run_of.get(loudest, 0)] += 1
    if voted < CUT_SPINE_FULL * fullest: return None
    best = max(full, key=lambda r: (votes[r], r))
    if loud_of and best != full[-1] and voted and votes[best] >= CUT_SPINE_LOUD_SHARE * voted:
        return {"run": best, "why": "energy", "voted": voted, "loudest": votes[best]}
    return {"run": full[-1], "why": "last", "voted": voted, "loudest": votes[full[-1]]}


# ── the proposal ──────────────────────────────────────────────────────────────────────────────────
def propose(job, use_audio=True):
    words = load_words(job)
    envelope = build_envelope(_resolve_clip_path(job)) if use_audio else None
    pace = measure_pace(words, envelope)
    S = sentences(words)
    T = [sent_tokens(words, s) for s in S]

    # flaws per sentence (first-real for warm-up)
    drags = dragged_words(words, envelope, pace)
    flaws = []; seen_real = False
    for i, s in enumerate(S):
        f = flaws_of(words, s, envelope, drags, is_first_real=not seen_real)
        flaws.append(f)
        if not f["junk"]: seen_real = True

    # lines, then fold the retakes whole-sentence likeness missed
    groups = group_lines(S, T)
    line_of = {s: gi for gi, g in enumerate(groups) for s in g}
    rt = retakes(S, T)
    for earlier, later in rt.items():
        ge, gl = line_of.get(earlier), line_of.get(later)
        if ge is not None and gl is not None and ge != gl:
            groups[gl].extend(groups[ge]); groups[ge] = []
            for s in groups[gl]: line_of[s] = gl
    groups = [sorted(g) for g in groups if g]
    # re-sort lines by first take time so run-throughs/order read in recording order
    groups.sort(key=lambda g: g[0])
    line_takes = [tuple(g) for g in groups]

    # run-throughs + spine (energy vote needs per-take loudness)
    loud_of = {i: flaws[i]["loud"] for i in range(len(S))} if envelope is not None else {}
    run_of, noisy = run_throughs(line_takes)
    sp = spine(line_takes, run_of, noisy, loud_of)
    spine_run = sp["run"] if sp else None

    kept = []; decisions = []
    for gi, g in enumerate(groups):
        real = [s for s in g if not flaws[s]["junk"]]
        if not real:
            decisions.append({"line": gi, "takes": g, "kept": None,
                              "why": "all takes are filler / warm-up / no clean speech"})
            continue
        # an abandoned start (a fragment of a fuller sibling) is not a candidate: the fuller take wins
        frag = fragments_in_line(g, T)
        pool = [s for s in real if s not in frag] or real
        note = ""
        # spine: keep takes performed inside the chosen run-through; a line the spine never says goes
        if spine_run is not None and gi not in noisy:
            in_spine = [s for s in pool if run_of.get(s) == spine_run]
            if in_spine:
                pool = in_spine; note = f" (spine run {spine_run})"
            elif len({run_of.get(s) for s in g}) >= 2:
                decisions.append({"line": gi, "takes": g, "kept": None,
                                  "why": f"the run-through that plays (run {spine_run}) never says this line"})
                continue
        # last clean take in the pool; else the latest take (last-take), flaw-aware
        clean = [s for s in pool if not is_disqualifying(flaws[s])]
        if clean:
            pick = clean[-1]
            why = ("only take, clean" if len(real) == 1 else "last clean take") + note
        else:
            pick = pool[-1]
            why = f"every take flawed; kept the last — {_flaw_words(flaws[pick])}" + note
        kept.append(pick)
        dropped = [s for s in g if s != pick]
        decisions.append({"line": gi, "takes": g, "kept": pick, "dropped": dropped, "why": why})

    kept.sort()
    clip = _resolve_clip(job)
    segs = [{"clip": clip, "start": round(words[S[s][0]]["start_ms"] / 1000, 3),
             "end": round(words[S[s][1]]["end_ms"] / 1000, 3),
             "transcript": sent_text(words, S[s])} for s in kept]
    meta = {"pace": pace, "spine": sp, "runs": (max(run_of.values()) + 1) if run_of else 0,
            "audio": envelope is not None}
    return segs, decisions, S, flaws, meta


def _resolve_clip(job):
    try:
        d = json.load(open(f"{job}/transcript/words.json", encoding="utf-8"))
        return os.path.basename(d["clips"][0]["clip"])
    except Exception:
        return os.path.basename(job.rstrip("/\\")) + ".MOV"

def _resolve_clip_path(job):
    name = _resolve_clip(job)
    for cand in (f"{job}/raw/{os.path.splitext(name)[0]}-1080.MOV", f"{job}/raw/{name}"):
        if os.path.exists(cand): return cand
    hits = glob.glob(f"{job}/raw/*")
    return hits[0] if hits else None


# ── diff / explain / CLI ──────────────────────────────────────────────────────────────────────────
def _norm_text(t):
    return [x for x in (_normal(w) for w in (t or "").split()) if x]

def _match(target, pool):
    for cand in pool:
        if not target or not cand: continue
        if target == cand or SequenceMatcher(None, target, cand).ratio() >= 0.8 \
           or _contained(target, cand) or _contained(cand, target): return True
    return False

def diff_against_existing(job, segs):
    path = f"{job}/transcript/cuts.json"
    if not os.path.exists(path): return None
    existing = json.load(open(path, encoding="utf-8")).get("segments", [])
    ex = [_norm_text(s.get("transcript", "")) for s in existing]
    pr = [_norm_text(s["transcript"]) for s in segs]
    return {"existing": existing,
            "added": [i for i, t in enumerate(pr) if not _match(t, ex)],
            "dropped": [i for i, t in enumerate(ex) if not _match(t, pr)]}


def job_dir(arg):
    job = arg.rstrip("/\\")
    if job.startswith(("projects/", "projects\\")): job = job[len("projects/"):]
    if job.startswith("/") or os.path.isabs(job): return job
    if os.path.isdir(os.path.join(job, "transcript")): return os.path.abspath(job)
    return os.path.join(ENG, "projects", job)


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    if sys.argv[1] == "pace":
        if len(sys.argv) > 2:
            job = job_dir(sys.argv[2]); words = load_words(job)
            env = build_envelope(_resolve_clip_path(job))
            p = measure_pace(words, env)
            print(f"{os.path.basename(job.rstrip('/'))}: median {p:.1f} ms/letter ({'voiced' if env else 'stamp span, no audio'})")
            print(f"  → 'dragged' at ≥ {DRAG_TIMES:.0f}× = {DRAG_TIMES*p:.0f} ms/letter AND ≥ {DRAG_MIN_MS} ms total")
        else:
            c = corpus_pace()
            print(f"corpus: {c['n']} words, median {c['median']:.1f} ms/letter, mean {c['mean']:.1f}" if c["median"] else "no transcripts")
        return

    job = job_dir(sys.argv[1]); name = os.path.basename(job.rstrip("/\\"))
    if not os.path.exists(f"{job}/transcript/words.json"): sys.exit(f"takes: no transcript/words.json under {job}")
    segs, decisions, S, flaws, meta = propose(job, use_audio="--no-audio" not in sys.argv)
    tot = sum(x["end"] - x["start"] for x in segs)
    sp = meta["spine"]
    spine_line = (f"spine: run {sp['run']} by {sp['why']} (voted {sp['voted']})" if sp
                  else f"no spine ({meta['runs']} run-through{'s' if meta['runs']!=1 else ''} found; keeping last-take)")
    print(f"{name}: {len(segs)} pieces from {len(S)} takes | pace {meta['pace']:.0f} ms/letter | "
          f"{'audio' if meta['audio'] else 'NO audio'} | {spine_line} | {tot:.1f}s ({int(tot//60)}:{int(tot%60):02d})")

    if "--diff" in sys.argv:
        d = diff_against_existing(job, segs)
        if d is None: print("  (no existing cuts.json to diff against)"); return
        if not d["added"] and not d["dropped"]: print("  same lines kept as the existing cut."); return
        for i in d["dropped"]: print(f"  − existing keeps, chooser drops: {d['existing'][i].get('transcript','')[:72]!r}")
        for i in d["added"]: print(f"  + chooser keeps, existing drops: {segs[i]['transcript'][:72]!r}")
    if "--why" in sys.argv:
        for dec in decisions:
            if dec["kept"] is None:
                print(f"  DROP line: {sent_text(load_words(job), S[dec['takes'][0]])[:50]!r} — {dec['why']}"); continue
            if not dec.get("dropped"): continue
            print(f"  line {dec['line']}: kept {dec['kept']} — {dec['why']}")
            for s in dec["dropped"]:
                print(f"      drop take {s} ({_flaw_words(flaws[s])}): {sent_text(load_words(job), S[s])[:46]!r}")
    if "--print" in sys.argv:
        for i, x in enumerate(segs, 1): print(f"{i:2d}|{x['end']-x['start']:4.1f}s| {x['transcript']}")
    if "--write" in sys.argv:
        out = sys.argv[sys.argv.index("--write") + 1]
        json.dump({"segments": segs}, open(out, "w", encoding="utf-8"), indent=2)
        print(f"  wrote {out}")


if __name__ == "__main__":
    main()
