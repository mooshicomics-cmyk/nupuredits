#!/usr/bin/env python3
"""snap-to-sound.py: the stitch's second pass, which moves each cut boundary onto her actual voice.

    snap-to-sound.py <raw clips folder> <words.json> <cut plan .json> <where the snapped plan goes>

stitch-cut.sh runs it between trim-restarts.py and the frame grid. In: the raw clips, the WhisperX word
timings and the cut plan. Out: the same plan with its boundaries moved, written to <out_cuts.json> on every
run that finishes (an unchanged copy when nothing moved, so the stitch reads it without a second check). The
report of what moved goes to stderr. It uses the Python standard library only.

The words in the plan are final by the time this runs, so it keeps every one and changes only where each
segment starts and stops:

    boundary    measured edge                                         where the cut goes
    in-point    the voice starting after the last held quiet          42 ms before that edge
    out-point   the voice stopping before the next held quiet         60 ms after that edge

The edges come from the raw audio's loudness, read in 6 ms steps, not from the transcript. On her footage
WhisperX puts a word's start stamp a median 39 ms after her voice begins and its end stamp a median 75 ms
before it stops, so a cut on the stamps would take the front off a word and the tail off another. Each margin
covers the soft sound around a word (a breath into it, the ring after it) and adds half a frame, so the
frame grid that follows never rounds a cut back into her voice. A boundary never moves past a neighbouring
word's stamp or beyond the quiet it found, and where no held quiet exists (running speech) it stays where
the plan put it. Whatever it moves lands on the sound of the word the plan already chose.

How it works: a word's edges depend only on the word, its neighbours' stamps and the clip, never on where the
plan cut it. So each clip becomes a VoiceMap that measures a word's onset, offset and hidden second take the
first time a boundary asks for one and keeps the answer. Each boundary is then placed against that
measurement, within the limits below. Three cases it treats differently:
  - "keep_edges": true on a segment pins both its boundaries
  - two segments from one clip that meet in the raw are one take split on purpose; that joint is not moved
  - a spoken amount ("$27,000", "40%"): one stamp over several spoken words ("twenty-seven ... thousand ...
    dollars"), because the aligner cannot time digits. Its quiet inside is never a second take, and its edges
    are the first sound after the word before it and the last sound before the word after it, never the quiet
    beside its stamp (which can sit a whole word inside it)
  - a word she said twice that WhisperX returned as one long word ("Listen... listen," heard as one), found
    by held quiet inside the word's span: at the start of a segment the in-point moves to the second take,
    at the end the out-point lands after the first, and in the middle of a segment it is reported with the
    time to split at
"""
import array, itertools, json, math, os, re, statistics, subprocess, sys, time
try:                                       # os.replace that waits out Windows holding the plan open for a moment
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "product"))
    from swap import replace as swap_in
except ImportError:
    swap_in = os.replace

for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print ✓ or →
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# Every timing below was measured, not chosen: 85 minutes of real talking-head takes (26 files, 8,016
# words), their pauses and their restarts. Each comment names the statistic it is; which percentile was
# settled by replaying real cuts and counting clipped words, stray breaths and false repeats, so that no count
# came out worse than the numbers it replaced. Re-measure on footage rather than tuning one of these by ear.
# The ones that are not a statistic of her footage say which rule of this pass they follow.

# ── reading the voice ──────────────────────────────────────────────────────────────────────────────────
RATE = 16000            # Hz: the rate the transcriber listens at (Whisper and its aligner both read 16 kHz), so
                        # the stamps and these readings come from the same samples
SILENCE_FLOOR = 1e-9    # added before the log so digital silence stays a finite number
FRAME = 0.006           # 96 samples: one full cycle of the voice at its low regular pitch (5th percentile,
                        # 172 Hz), in whole ms, so voiced sound never ripples into false quiet
QUIET_DB = 16.0         # under the word's own level by this much = quiet: 95 in 100 word frames stay above it
HOLD_FRAMES = 6         # 36 ms of quiet in a row is a gap: longer than the dips inside 85 of 100 words
LEVEL_SPAN = 0.08       # a boundary word's own level is read over this much of it, inward from the stamp the
                        # boundary sits on (the start stamp for an in-point, the end stamp for an out-point)
FOLD_LEAD = 0.05        # the fold scan's read begins this far before the word's start stamp. No quiet before
                        # the stamp can count, so this only sets where the 6 ms readings fall

# ── where the cut lands ────────────────────────────────────────────────────────────────────────────────
ROOM_BEFORE = 0.042     # the breathy attack before an onset (93rd percentile, 24 ms) plus half a frame
DECAY_AFTER = 0.060     # the ring-out after an offset (75th percentile, 42 ms) plus half a frame; longer
                        # ring-outs run on into the breath that follows
CLEAR_OF_NEXT = FRAME   # an out-point stays one reading inside the quiet it found, ahead of whatever sound
                        # comes after that quiet: the readings cannot place that sound any closer

# ── how far WhisperX's stamps drift from the sound ─────────────────────────────────────────────────────
# Start stamps ran a median 39 ms after the sound began and end stamps a median 75 ms before it stopped. An
# edge found past the outlier fence of that drift (upper quartile + 1.5 x the spread between the quartiles)
# is a breath or a noise taken for the word, so the caps stop there: without them a cut placed out in a long
# pause could walk onto an inhale and open the reel on it.
REACH = 0.756           # search past the stamp far enough to find the quiet beside 99 in 100 edges (end side,
                        # 719 ms) plus one hold, so an edge past a cap is clamped to the cap, never missed
LEAD_CAP = 0.228        # an in-point stays this close to its first word's stamp: start fence + ROOM_BEFORE
TAIL_CAP = 0.318        # an out-point stays this close to its last word's stamp: end fence + DECAY_AFTER
MOVE_CAP = 0.420        # a planned cut further than this from where the measurement would put it was put there
                        # on purpose, so the plan stands: real cuts never needed a move past 416 ms, and the
                        # ones they placed on purpose sit 837 ms or more away
EDGE_TO_EDGE = 0.005    # a gap this small between two stamps means nothing was measured there
STAMP_SLOP = 0.02       # one step of the aligner, which times words on a 20 ms grid: a neighbour's stamp is only
                        # known to that
ABUT = 0.042            # same-clip segments closer than one frame at 23.976 fps (the slowest a phone films) in
                        # the raw have nothing between them to cut: one take split on purpose

# ── a restart folded into one word ─────────────────────────────────────────────────────────────────────
MERGE_MIN_SPAN = 0.822  # only a word longer than 995 in 1000 words is scanned for a hidden second take, so
                        # a held opener ("Alors,", "So...") is never mistaken for two takes
MERGE_QUIET = 0.102     # held quiet this long INSIDE one word means two takes: longer than the quiet inside
                        # 98 in 100 ordinary words, shorter than the pause in 45 of 52 measured restarts
FOLD_TAKE = 0.102       # the shortest take of a word (10th percentile of retaken words, 100 ms), whole frames:
                        # a first take must run this long before its quiet, and a kept take must leave this much
FOLD_END_SLACK = 0.072  # end stamps run a median 75 ms early, so quiet ending this far past one is still inside
FOLD_LEVEL_RANK = 0.8   # a folded word is judged against its 80th-percentile reading: the gaps being looked
                        # for may fill up to a fifth of the span without pulling that level down into them
FOLD_REPEAT = 0.4       # a restart says the word again WHOLE, so its last take runs at least this share of the
                        # first take (end slack included): 64 of 65 one-word restarts in her jobs do (2026-10-19).
                        # One long word drawn out with a pause inside ("confines,", 1.48 s, its last part 0.27 s
                        # after about 1.1 s) is one take, and a buyer's cut clipped it as two (2026-10-10)

# ── a spoken amount ────────────────────────────────────────────────────────────────────────────────────
AMOUNT = re.compile(r"^\W*(?:[$€£¥]\d[\d,.]*[kKmMbB]?|\d[\d,.]*\s*(?:%|[kKmMbB])|\d{1,3}(?:,\d{3})+(?:\.\d+)?)\W*$")   # an amount ("$27,000", "40%", "3.5k", "27,000"): its spoken unit isn't timed
AMOUNT_REACH = 1.5      # how far past (or before) an amount's stamp its spoken words can run; the same pause
                        # transcript-cut.py never cuts beside an amount (measured: "dollars" began 0.43 s past
                        # a "$27,000" stamp, after 0.35 s of quiet)
AMOUNT_VOICE_DB = 10.0  # her voice, not a click or a breath: within this much of the amount's own level. An amount's edges
                        # reach far, so a quieter sound out there (a click 10+ dB under her) must never pull them
AMOUNT_CLEAR = 0.08     # an amount's edges stay this far from a neighbour's stamp: end stamps run early and start
                        # stamps late (the median drift above, rounded up), so the stamp itself sits in that word
AMOUNT_LEVEL_RANK = 0.8 # an amount is judged against its 80th-percentile reading, like a folded word: its own
                        # quiet stretches may fill a good part of the span

# ── the plan ───────────────────────────────────────────────────────────────────────────────────────────
PLAN_DECIMALS = 3       # cuts.json carries times to the millisecond
MOVED_MS = 1            # a boundary that moved by more than this many ms counts as moved (and is marked)


def _say(line):
    print(line, file=sys.stderr)


def _text(word):
    return word.get("word", word.get("w", ""))


def spoken_amount(word):
    """True for a stamp over a spoken amount ("$27,000", "40%", "3.5k")."""
    return bool(AMOUNT.match(_text(word)))


def _within(t, low, high):
    """t held inside [low, high]; low wins if the two cross."""
    return max(low, min(t, high))


def _hold_reach():
    """One reading short of a full hold, in seconds: a held quiet that begins less than this before an end stamp
    is still going at the stamp. It is where an offset's quiet may begin at the earliest, and so the earliest
    an out-point may land, even where the next word's stamp overlaps this one's."""
    return round((HOLD_FRAMES - 1) * FRAME, PLAN_DECIMALS)


# ── her voice, read from the raw clip ──────────────────────────────────────────────────────────────────

def _dbfs(chunk):
    """dBFS of the RMS of one analysis frame. Added up one sample at a time, in order: the builtin sum()
    rounds differently from a running total, and the numbers here must not move."""
    energy = 0.0
    for v in chunk:
        energy += v * v
    return 20 * math.log10(math.sqrt(energy / len(chunk)) + SILENCE_FLOOR)


# ── reading the clip once ──────────────────────────────────────────────────────────────────────────────
# Every boundary used to start its own ffmpeg on the raw clip, two to five per piece: on a 65-piece cut of one 4K
# phone clip on Windows that was several hundred ffmpeg runs, each opening and seeking a multi-GB file, with no time
# limit on any of them, so "Send my cut" ran past its 15 minutes (buyer report, 2026-10-21). Now each clip's sound
# is decoded ONCE, over the stretch the plan uses (want()), and every reading is a slice of that. A reading outside
# it is decoded on its own, as before. Every decode has a time limit, and the whole pass has a budget (SNAP_BUDGET_S,
# snap() below): past it, the pieces not yet placed keep their edges as planned, which is a working cut.
DECODE_TIMEOUT = 300    # s: reading a long phone clip's sound takes seconds; past this, ffmpeg is stuck (a clip on a
                        # drive that went to sleep), the same limit trim-restarts.py gives its own read
DECODE_PAD = 2.0        # s read past each end of the plan's stretch: every reading reaches at most REACH (0.756 s),
                        # AMOUNT_REACH (1.5 s) or UNHEARD_REACH + 0.3 (0.9 s) past a cut, so the pad is that plus margin
SNAP_BUDGET = 240       # s for the whole pass (SNAP_BUDGET_S overrides): with one decode per clip a 65-piece cut of a
                        # 4K clip takes seconds, so this only ever stops a pass that is stuck
_wanted = {}            # clip path -> (from, to) the plan uses, seconds
_decoded = {}           # clip path -> (first sample, samples, whether the decode ran to the clip's end) or None
_deadline = [None]      # time.monotonic() past which no new decode starts (the pass's budget), None for no budget
_unreadable = []        # (clip, why) for every clip whose sound could not be read in time, for the report


def want(path, t_from, t_to):
    """Note that the plan reads `path` from t_from to t_to, so its sound is decoded once over all of it."""
    lo, hi = _wanted.get(path, (t_from, t_to))
    _wanted[path] = (min(lo, t_from), max(hi, t_to))


def _decode_timeout():
    if _deadline[0] is None:
        return DECODE_TIMEOUT
    return max(1.0, min(DECODE_TIMEOUT, _deadline[0] - time.monotonic()))


def _decode(path, t0, dur):
    """16 kHz mono f32 samples of `path` from t0 for dur seconds (dur None: to the end), first audio stream.
    An empty array when ffmpeg fails or runs past its time limit (noted once per clip for the report)."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error"] + (["-ss", f"{t0:.3f}"] if t0 > 0 else [])
    cmd += (["-t", f"{dur:.3f}"] if dur is not None else []) + ["-i", path]
    cmd += ["-map", "0:a:0?", "-vn", "-af", "pan=mono|c0=c0", "-ar", str(RATE), "-f", "f32le", "-"]
    samples = array.array("f")
    if any(c == path for c, _ in _unreadable):           # one stuck read per clip, never one per boundary
        return samples
    if _deadline[0] is not None and time.monotonic() >= _deadline[0]:
        if not any(c == path for c, _ in _unreadable):
            _unreadable.append((path, "the snap's time budget ran out first"))
        return samples
    try:
        limit = _decode_timeout()
        pcm = subprocess.run(cmd, capture_output=True, timeout=limit).stdout
    except subprocess.TimeoutExpired:
        if not any(c == path for c, _ in _unreadable):
            _unreadable.append((path, f"ffmpeg was still reading it after {limit:.0f} s"))
        return samples
    except OSError as e:
        if not any(c == path for c, _ in _unreadable):
            _unreadable.append((path, f"ffmpeg could not run ({e})"))
        return samples
    samples.frombytes(pcm[:len(pcm) - len(pcm) % samples.itemsize])
    return samples


def _clip_sound(path):
    """The clip's sound over the stretch the plan uses, decoded the first time it is asked for."""
    if path not in _decoded:
        lo, hi = _wanted.get(path, (0.0, None))
        lo = max(0.0, round(lo - DECODE_PAD, 3))
        dur = None if hi is None else round(hi + DECODE_PAD - lo, 3)
        pcm = _decode(path, lo, dur)
        first = round(lo * RATE)
        # fewer samples than asked: the clip ended (or nothing could be read), so nothing lies past them either
        ran_out = dur is None or len(pcm) < round(dur * RATE) - RATE // 100
        _decoded[path] = (first, pcm, ran_out)
    return _decoded[path]


def _levels(path, t_from, t_to):
    """Loudness of `path` from t_from to t_to, one dBFS reading per FRAME, first audio channel only.

    Returns (t0, readings): t0 is where reading 0 begins, which is t_from held at zero or later. Any
    samples left over after the last whole frame are dropped. The samples are a slice of the clip's one decode
    (_clip_sound); a stretch outside it is decoded on its own."""
    t0 = max(0.0, t_from)
    a = round(round(t0, 3) * RATE)
    n = max(0, round(round(t_to - t0, 3) * RATE))
    first, pcm, ran_out = _clip_sound(path)
    if a >= first and (a + n <= first + len(pcm) or ran_out):
        samples = pcm[a - first:a - first + n]
    else:
        samples = _decode(path, t0, t_to - t0)
    width = int(FRAME * RATE)
    return t0, [_dbfs(samples[k * width:(k + 1) * width]) for k in range(len(samples) // width)]


class Stretch:
    """One read of a clip's loudness: reading k covers the FRAME starting at t0 + k * FRAME."""

    def __init__(self, path, t_from, t_to):
        self.t0, self.db = _levels(path, t_from, t_to)

    def time(self, k):
        return self.t0 + k * FRAME

    def index(self, t):
        """The reading nearest time t (can be negative or past the end)."""
        return round((t - self.t0) / FRAME)

    def holds(self, line):
        """Every held quiet in this stretch: an unbroken run of HOLD_FRAMES or more readings under `line`,
        as (time it begins, time the sound comes back), earliest first."""
        found, k = [], 0
        for quiet, run in itertools.groupby(self.db, key=lambda db: db < line):
            length = sum(1 for _ in run)
            if quiet and length >= HOLD_FRAMES:
                found.append((self.time(k), self.time(k + length)))
            k += length
        return found


class Edge:
    """A measured word edge: `voice` is where her sound starts (onset) or stops (offset); `quiet` is the far
    end of the held quiet beside it (where that quiet began, or where the next sound comes in)."""
    __slots__ = ("voice", "quiet")

    def __init__(self, voice, quiet):
        self.voice, self.quiet = voice, quiet


RUNNING = "running"     # a measurement that read the audio fine and found no held quiet beside the word


class VoiceMap:
    """One raw clip and its transcribed words. Each word's onset, offset and fold are measured the first
    time a boundary asks for them and kept, so a word read from two sides is decoded once."""

    def __init__(self, path, words):
        self.path, self.words = path, words
        self._kept = {}

    def _once(self, what, i):
        key = (what, i)
        if key not in self._kept:
            self._kept[key] = getattr(self, "_measure_" + what)(i)
        return self._kept[key]

    def onset(self, i):
        """Edge where word i's voice starts, RUNNING, or None when nothing could be read."""
        return self._once("onset", i)

    def offset(self, i):
        """Edge where word i's voice stops, RUNNING, or None when nothing could be read."""
        return self._once("offset", i)

    def fold(self, i):
        """(end of the first take, start of the last take) when word i is several takes in one, else None."""
        return self._once("fold", i)

    def prev_end(self, i):
        """The end stamp of the word before word i; the clip's start when there is none."""
        return self.words[i - 1]["end"] if i else 0.0

    def next_start(self, i):
        """The start stamp of the word after word i, or None for the clip's last word."""
        return self.words[i + 1]["start"] if i + 1 < len(self.words) else None

    def _amount_line(self, read, word):
        """The quiet line for a spoken amount: under its 80th-percentile reading by QUIET_DB."""
        lo, hi = max(0, read.index(word["start"])), max(1, read.index(word["end"]))
        span = sorted(read.db[lo:hi]) or sorted(read.db)
        return span[int(AMOUNT_LEVEL_RANK * (len(span) - 1))] - AMOUNT_VOICE_DB

    def _measure_onset(self, i):
        word = self.words[i]
        prev_end = self.prev_end(i)
        if spoken_amount(word):
            # its first spoken word can sit before the stamp: the FIRST sound after the word before it
            floor = max(word["start"] - AMOUNT_REACH, prev_end + AMOUNT_CLEAR if i else 0.0, 0.0)
            read = Stretch(self.path, floor, word["end"])
            if not read.db:
                return None
            line = self._amount_line(read, word)
            first = next((k for k, db in enumerate(read.db) if db >= line), None)
            return RUNNING if first is None else Edge(read.time(first), read.time(0))
        # The search starts at the previous word's end stamp, so it never reaches back into that word. That
        # protects only a MEASURED stamp: a transcript made without forced alignment (the Intel-Mac route,
        # product/INTEL-MAC-ROUTE.md) stamps words edge to edge, so a word's start swallows the pause before
        # it and a search from the previous end finds no quiet at all. Where the stamps touch, the whole REACH
        # is searched instead; that is safe because the onset comes from the LAST held quiet before the word,
        # never from one further back. Aligned transcripts never have stamps this close.
        floor = word["start"] - REACH
        if word["start"] - prev_end >= EDGE_TO_EDGE:
            floor = max(prev_end - STAMP_SLOP, floor)
        read = Stretch(self.path, max(floor, 0.0), word["start"] + LEVEL_SPAN)
        k = read.index(word["start"])
        if len(read.db) < k + HOLD_FRAMES:
            return None
        quiet = read.holds(statistics.median(read.db[k:]) - QUIET_DB)
        if not quiet:
            return RUNNING
        began, voice = quiet[-1]
        return Edge(voice, began)

    def _measure_offset(self, i):
        word = self.words[i]
        if spoken_amount(word):
            # its last spoken words can run past the stamp: the LAST sound before the word after it
            until = word["end"] + AMOUNT_REACH
            if self.next_start(i) is not None:
                until = min(until, self.next_start(i) - AMOUNT_CLEAR)
            read = Stretch(self.path, word["start"], max(until, word["end"]))
            if not read.db:
                return None
            line = self._amount_line(read, word)
            last = next((k for k in range(len(read.db) - 1, -1, -1) if read.db[k] >= line), None)
            return RUNNING if last is None else Edge(read.time(last + 1), read.time(len(read.db)))
        until = word["end"] + REACH
        after = self.next_start(i)
        if after is not None:
            until = min(until, after + STAMP_SLOP)
        read = Stretch(self.path, word["end"] - LEVEL_SPAN, until)
        k = max(HOLD_FRAMES, read.index(word["end"]))
        if len(read.db) < k + HOLD_FRAMES:
            return None
        # The quiet has to hold across the end stamp; one that begins earlier than that is a dip inside the word.
        earliest = word["end"] - _hold_reach()
        quiet = [q for q in read.holds(statistics.median(read.db[:k]) - QUIET_DB) if q[0] >= earliest]
        if not quiet:
            return RUNNING
        voice, sound_back = quiet[0]
        return Edge(voice, sound_back)

    def _measure_fold(self, i):
        word = self.words[i]
        if word["end"] - word["start"] < MERGE_MIN_SPAN or spoken_amount(word):   # an amount's quiet is its own
            return None
        # read one hold past the latest a take's gap may end, so a quiet that keeps going is seen to keep going
        read = Stretch(self.path, word["start"] - FOLD_LEAD, word["end"] + FOLD_END_SLACK + HOLD_FRAMES * FRAME)
        lo = max(0, read.index(word["start"]))
        hi = max(lo + 1, read.index(word["end"]))
        if len(read.db) < lo + int((FOLD_TAKE + MERGE_QUIET) / FRAME):   # no room for a take and its gap
            return None
        ranked = sorted(read.db[lo:hi])
        gaps = [(a, b) for a, b in read.holds(ranked[int(FOLD_LEVEL_RANK * len(ranked))] - QUIET_DB)
                if a > word["start"] + FOLD_TAKE and b < word["end"] + FOLD_END_SLACK and b - a >= MERGE_QUIET]
        if not gaps:
            return None
        first_take_ends, last_take_starts = gaps[0][0], gaps[-1][1]
        first_take = first_take_ends - word["start"]
        last_take = word["end"] + FOLD_END_SLACK - last_take_starts
        if last_take < FOLD_REPEAT * first_take:   # the part after the pause is the end of the word, not the word again
            return None
        return first_take_ends, last_take_starts


# ── placing one boundary against the measurement ───────────────────────────────────────────────────────
# Each returns (time, note). The note is what the report says about that edge; None says nothing.

def _into_voice_ms(later, earlier):
    """How far apart two times are in ms (a planned cut sitting inside her voice), when that is more than
    one reading; None for less, which the readings cannot tell from nothing."""
    ms = (later - earlier) * 1000
    return ms if ms > FRAME * 1000 else None


def _settle(cut, t, found, clipped_ms, word):
    """The placed time t, unless it would travel past MOVE_CAP from the planned cut; then the plan stands."""
    if abs(t - cut) > MOVE_CAP:
        return cut, f"{found} is past the move cap, kept"
    if clipped_ms:
        return t, f'{found}; the plan cut {clipped_ms:.0f} ms of "{_text(word)}"'
    return t, found


_UNREAD = {None: None, RUNNING: "no held quiet beside it, kept"}


def place_in(voice, i, cut):
    """The in-point of a segment whose first kept word is word i of `voice`; `cut` is the planned one."""
    word = voice.words[i]
    fold = voice.fold(i)
    if fold:
        # Open on the LAST take, the one she meant, as long as it leaves a whole take of the word. The word's
        # own span bounds this move, so MOVE_CAP does not apply.
        opening, last_room = fold[1] - ROOM_BEFORE, word["end"] - FOLD_TAKE
        if opening < last_room and cut < last_room:
            return max(opening, cut), f'said twice: "{_text(word)}", opens on the second take at {fold[1]:.3f}'
    edge = voice.onset(i)
    if not isinstance(edge, Edge):
        return cut, _UNREAD[edge]
    if spoken_amount(word):          # the amount's own measured edge wins: no stamp cap, no move cap
        return max(edge.voice - ROOM_BEFORE, edge.quiet), f"a spoken amount, voice from {edge.voice:.3f}"
    t = _within(max(edge.voice - ROOM_BEFORE, edge.quiet), word["start"] - LEAD_CAP, word["start"] + STAMP_SLOP)
    return _settle(cut, t, f"voice from {edge.voice:.3f}", _into_voice_ms(cut, edge.voice), word)


def place_out(voice, i, cut, one_word):
    """The out-point of a segment whose last kept word is word i of `voice`; `cut` is the planned one. A
    one-word segment has already opened on that word's last take, so its fold is not looked at again here."""
    word = voice.words[i]
    fold = None if one_word else voice.fold(i)
    if fold:
        # Close after the FIRST take (the rest is the restart), as long as a whole take of the word is kept.
        closing, first_room = fold[0] + DECAY_AFTER, word["start"] + FOLD_TAKE
        if closing > first_room and cut > first_room:
            return min(closing, cut), f'said twice: "{_text(word)}", ends on the first take at {fold[0]:.3f}'
    edge = voice.offset(i)
    if not isinstance(edge, Edge):
        return cut, _UNREAD[edge]
    if spoken_amount(word):          # the amount's own measured edge wins: no stamp cap, no move cap
        return (max(min(edge.voice + DECAY_AFTER, edge.quiet), word["end"] - _hold_reach()),
                f"a spoken amount, voice to {edge.voice:.3f}")
    limits = [edge.quiet - CLEAR_OF_NEXT, word["end"] + TAIL_CAP]
    if voice.next_start(i) is not None:
        limits.append(voice.next_start(i) - STAMP_SLOP)
    t = _within(edge.voice + DECAY_AFTER, word["end"] - _hold_reach(), min(limits))
    return _settle(cut, t, f"voice to {edge.voice:.3f}", _into_voice_ms(edge.voice, cut), word)


# ── which transcript belongs to which clip ─────────────────────────────────────────────────────────────

# A review proxy ("<job>-1080.MOV") and the original it was made from share one timeline, so the words
# transcribed from either one fit both.
_PROXY_SUFFIX = re.compile(r'-(?:2160|1440|1080|720|540|480|360|proxy|review|preview)$', re.I)


def _stem(name):
    return _PROXY_SUFFIX.sub('', os.path.splitext(os.path.basename(name))[0])


def _transcript_lookup(transcript):
    """(words_for, has_clips): words_for(clip) finds the transcribed words that belong to a cut's clip.

    Exact file name first, then the name with any proxy suffix stripped, then, for a single-clip job, the only
    transcript there is. A cut made on a review proxy and a transcript made on the original must still meet,
    or every segment would go out with its edges unsnapped."""
    by_name = {os.path.basename(entry["clip"]): entry.get("words", []) for entry in transcript.get("clips", [])}
    by_stem = {_stem(name): words for name, words in by_name.items()}

    def words_for(clip):
        name = os.path.basename(clip)
        if name in by_name:
            return by_name[name]
        words = by_stem.get(_stem(clip))
        if words is not None:
            return words
        if len(by_name) == 1:
            return next(iter(by_name.values()))
        return []

    return words_for, bool(by_name)


# ── the plan ───────────────────────────────────────────────────────────────────────────────────────────

def _one_take(a, b):
    """True when segment b picks up in the raw where segment a left off (same clip, within ABUT): one take
    split into two timeline clips on purpose, so neither side of that joint is moved."""
    return (os.path.basename(a["clip"]) == os.path.basename(b["clip"])
            and abs(float(b["start"]) - float(a["end"])) < ABUT)


def _kept_words(words, cut_in, cut_out):
    """Indexes of the words a segment keeps: every word whose stamps overlap it."""
    return [i for i, word in enumerate(words) if cut_in < word["end"] and word["start"] < cut_out]


def _held_because(seg, path, words, kept):
    """Why a segment's edges stay exactly as planned, or None when they are placed."""
    if seg.get("keep_edges"):
        return "keep_edges"
    if not words:
        return "no words for this clip"
    if not kept:
        return "no words inside it"
    if not os.path.exists(path):
        return "clip not found"
    return None


def _edge_text(side, planned, placed, note):
    shift = round((placed - planned) * 1000) + 0     # + 0 turns a -0 into 0
    return f"{side} {placed:.3f} ({shift:+d} ms{': ' + note if note else ''})"


def _split_hints(j, voice, kept):
    """A second take hidden in a word away from either edge needs a split a person makes: say where."""
    hints = []
    for i in kept[1:-1]:
        fold = voice.fold(i)
        if fold:
            word = voice.words[i]
            hints.append(f'[snap] seg{j}  ⚠ "{_text(word)}" at {word["start"]:.2f} s is two takes (the second from '
                         f"{fold[1]:.2f} s) and this segment keeps both; to keep only the second, end a segment "
                         f"before the word and start the next at {fold[1] - ROOM_BEFORE:.2f} s")
    return hints


def _today(seg):
    """A copy of one plan segment, with the record an earlier engine wrote of where a snap moved it kept in its
    place under today's name (_snapped_from {start, end})."""
    if not isinstance(seg.get("_refine"), dict) or "_snapped_from" in seg:
        return dict(seg)
    return {("_snapped_from" if k == "_refine" else k):
            ({"start": v.get("orig_start"), "end": v.get("orig_end")} if k == "_refine" else v)
            for k, v in seg.items()}


# ── the fail-safe: no cut opens or closes inside sound that no word accounts for ─────────────────────────
# The caps above keep an edge off a breath, and a stamp the listener got wrong can then leave an edge inside her
# voice: 2026-10-16 an "and" stamped on the ring of the word before it (really said 0.5 s later) left the next
# piece opening 140 ms into it, and the cut played half a word. So after each edge is placed, the sound right at it
# is read: voice running across the edge, which no word of the transcript covers, is a word the listener misplaced,
# and the edge moves out to the quiet beyond it. Voice that IS a word (one the plan dropped) stays out: that is
# the plan's call, and it is named. Never past a neighbouring piece that plays beside it, never further than this:
UNHEARD_REACH = 0.60    # seconds: the longest stray voice an edge reaches out to keep (a short word and its ring)
UNHEARD_LOUD_DB = 3.0   # the sound at the edge must stand this far over the quiet line to count as voice
UNHEARD_VOICE_DB = 10.0 # ...and the stray stretch's middle reading must sit within this much of her own level: a word,
                        # never the ring of the last one, a breath or the room (the AMOUNT_VOICE_DB rule)


def _unheard(path, words, kept, side, t, limit):
    """(new time, note) for one placed edge: moved out over stray voice, or (t, None) when the edge is clear.
    `limit` is the furthest it may go (a neighbouring piece's edge in this clip, or None)."""
    edge_word = words[kept[0] if side == "head" else kept[-1]]     # her own level: the kept word at this edge
    w0, w1 = float(edge_word["start"]), float(edge_word["end"])
    lo = min(w0, t) - UNHEARD_REACH - 0.3 if side == "head" else min(w0, t - 0.3)
    hi = max(w1, t + 0.3) if side == "head" else max(w1, t) + UNHEARD_REACH + 0.3
    read = Stretch(path, lo, hi)
    if len(read.db) < 10:
        return t, None
    own = read.db[read.index(w0):read.index(max(w1, w0 + 0.05))]
    if not own:
        return t, None
    ranked = sorted(read.db)
    line = max(sorted(own)[int(0.8 * (len(own) - 1))] - QUIET_DB, ranked[int(0.1 * (len(ranked) - 1))] + 8.0)
    k = read.index(t)
    at_edge = read.db[max(0, k - 4):k] if side == "head" else read.db[k:k + 4]
    if not at_edge or max(at_edge) < line + UNHEARD_LOUD_DB:
        return t, None                                             # quiet at the edge: nothing cut off
    holds = read.holds(line)
    if side == "head":
        before = [h for h in holds if h[1] <= t + FRAME]
        if not before:
            return t, None
        q0, q1 = before[-1]
        span = (q1, t)
        new = max(q0, q1 - ROOM_BEFORE)
    else:
        after = [h for h in holds if h[0] >= t - FRAME]
        if not after:
            return t, None
        q0, q1 = after[0]
        span = (t, q0)
        new = min(q1, q0 + DECAY_AFTER)
    if span[1] - span[0] < 0.03 or span[1] - span[0] > UNHEARD_REACH:
        return t, None
    stray = read.db[read.index(span[0]):read.index(span[1])]
    if not stray or sorted(stray)[len(stray) // 2] < sorted(own)[int(0.8 * (len(own) - 1))] - UNHEARD_VOICE_DB:
        return t, None                                             # the ring of a word or the room, not a word
    keep = set(kept)
    owner = [i for i, w in enumerate(words) if i not in keep
             and w["start"] < span[1] - STAMP_SLOP and w["end"] > span[0] + STAMP_SLOP]
    if owner:
        return t, f'⚠ cut inside "{_text(words[owner[0]])}", a word the plan dropped; left as planned'
    if limit is not None:
        new = max(new, limit) if side == "head" else min(new, limit)
    if abs(new - t) * 1000 <= MOVED_MS:
        return t, None
    return new, f"moved over {abs(new - t) * 1000:.0f} ms of her voice no word accounts for (a misplaced word)"


def snap(segs, media_dir, words_for):
    """Every segment of the plan with its boundaries placed. Returns (segments, report lines, moved count)."""
    joined = {j for j, (a, b) in enumerate(zip(segs, segs[1:])) if _one_take(a, b)}   # j: between j and j+1
    maps, placed, lines, moved = {}, [], [], 0
    for segment in segs:                                  # each clip's sound is decoded once, over all its pieces
        clip = segment["clip"]
        want(clip if os.path.isabs(clip) else os.path.join(media_dir, clip),
             float(segment["start"]), float(segment["end"]))
    for j, segment in enumerate(segs):
        out = _today(segment)
        placed.append(out)
        clip = segment["clip"]
        path = clip if os.path.isabs(clip) else os.path.join(media_dir, clip)
        words = words_for(clip)
        planned = (float(segment["start"]), float(segment["end"]))
        kept = _kept_words(words, *planned)
        held = _held_because(segment, path, words, kept)
        if not held and _deadline[0] is not None and time.monotonic() >= _deadline[0]:
            held = "out of time: the snap's budget ran out, so this piece keeps the edges as written"
        if held:
            lines.append(f"[snap] seg{j}  edges as planned ({held})")
            continue

        if clip not in maps:
            maps[clip] = VoiceMap(path, words)
        voice = maps[clip]
        head = ((planned[0], "joined to the take before it") if j - 1 in joined
                else place_in(voice, kept[0], planned[0]))
        tail = ((planned[1], "joined to the take after it") if j in joined
                else place_out(voice, kept[-1], planned[1], one_word=len(kept) == 1))
        crossed = tail[0] <= head[0]
        if crossed:
            head, tail = (planned[0], None), (planned[1], None)
        # the fail-safe above: an edge left inside stray voice moves out to the quiet, never over a neighbour
        same = lambda o: o.get("clip") == clip
        prev_end = float(placed[-2]["end"]) if j and same(placed[-2]) else None
        next_start = float(segs[j + 1]["start"]) if j + 1 < len(segs) and same(segs[j + 1]) else None
        if j - 1 not in joined and not crossed:
            limit = prev_end if prev_end is not None and prev_end <= head[0] else None
            t, note = _unheard(path, words, kept, "head", head[0], limit)
            if note:
                head = (t, note)
        if j not in joined and not crossed:
            limit = next_start if next_start is not None and next_start >= tail[0] else None
            t, note = _unheard(path, words, kept, "tail", tail[0], limit)
            if note:
                tail = (t, note)
        out["start"] = round(head[0], PLAN_DECIMALS)
        out["end"] = round(tail[0], PLAN_DECIMALS)
        if any(abs(t - p) * 1000 > MOVED_MS for t, p in zip((head[0], tail[0]), planned)):
            moved += 1
            out["_snapped_from"] = {"start": planned[0], "end": planned[1]}
        lines.append(f"[snap] seg{j}  {_edge_text('head', planned[0], out['start'], head[1])}   "
                     f"{_edge_text('tail', planned[1], out['end'], tail[1])}"
                     + ("   the measured edges crossed, so both stay as planned" if crossed else ""))
        lines.extend(_split_hints(j, voice, kept))
    # Two pieces of the same take, one after the other on the timeline, that each reached into the same short pause
    # (the tail's decay out, the head's room in) now share a slice of it, which plays twice: a small stutter at the
    # join (a buyer's 176-piece cut had 25, 2026-10-10). They meet in the middle of the overlap instead. Pieces the
    # plan itself overlapped (a replay) are the plan's call and stay as they are.
    for j in range(len(placed) - 1):
        a, b = placed[j], placed[j + 1]
        if (os.path.basename(a["clip"]) != os.path.basename(b["clip"])
                or float(segs[j]["end"]) > float(segs[j + 1]["start"]) or float(a["end"]) <= float(b["start"])):
            continue
        meet = round((float(a["end"]) + float(b["start"])) / 2, PLAN_DECIMALS)
        if not float(a["start"]) < meet < float(b["end"]):
            continue
        over = (float(a["end"]) - float(b["start"])) * 1000
        for k, key in ((j, "end"), (j + 1, "start")):
            placed[k].setdefault("_snapped_from", {"start": float(segs[k]["start"]), "end": float(segs[k]["end"])})
            placed[k][key] = meet
        lines.append(f"[snap] seg{j}/seg{j + 1}  both reached into the same pause ({over:.0f} ms would play twice); "
                     f"they now meet at {meet:.3f}")
    return placed, lines, moved


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    if len(sys.argv) != 5:
        sys.exit("usage: snap-to-sound.py <raw clips folder> <words.json> <cut plan .json> <where the snapped plan goes>")
    media_dir, transcript_path, plan_path, out_path = sys.argv[1:]
    try:
        budget = float(os.environ.get("SNAP_BUDGET_S") or SNAP_BUDGET)
    except ValueError:
        budget = SNAP_BUDGET
    if budget > 0:
        _deadline[0] = time.monotonic() + budget
    started = time.monotonic()
    plan = _read(plan_path)
    words_for, has_clips = _transcript_lookup(_read(transcript_path))
    segs = plan.get("segments", [])

    placed, lines, moved = snap(segs, media_dir, words_for)
    for line in lines:
        _say(line)
    for clip, why in _unreadable:
        _say(f"[snap] ⚠ the sound of {os.path.basename(clip)} could not be read ({why}), so its pieces keep the "
             f"edges as written")

    payload = dict(plan)
    payload["segments"] = placed
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    swap_in(tmp, out_path)   # one atomic swap, so the stitch never reads half a plan

    # A segment whose clip has no words in the transcript goes out unsnapped, which means clipped onsets.
    # When it is every segment, the clip names in the plan and in words.json point at different files.
    total = len(segs)
    orphans = sum(1 for seg in segs if has_clips and not words_for(seg["clip"]))
    if orphans:
        _say(f"[snap] 🔴 {orphans} of {total} segments ({100 * orphans / max(1, total):.0f}%) found no words for "
             f"their clip in the transcript, so their edges stay where the plan put them and her first and last "
             f"words may be clipped. Make the clip names in the cut list and in words.json name the same "
             f"footage.")
    else:
        _say(f"[snap] ✓ the transcript has words for every segment's clip ({total})")
    _say(f"[snap] {moved} of {total} segments moved in {time.monotonic() - started:.1f} s; the snapped plan is {out_path}")


if __name__ == "__main__":
    main()
