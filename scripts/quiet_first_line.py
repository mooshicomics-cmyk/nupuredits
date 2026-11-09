#!/usr/bin/env python3
"""quiet_first_line.py — a short, quiet first line the listener skipped, heard again and kept.

WHY THIS EXISTS (ISS-99). Both listeners run a voice detector before they write anything down: WhisperX its own,
faster-whisper its vad_filter. A short, quiet first line followed by a long silence can fall under it whole, so the
transcript starts at her second line and the rough cut never sees the first. The listen-back (verify-cut.py) heard
it missing, but nothing brought it back.

WHAT IT DOES, once per clip, after every fresh listen (and once on a transcript heard before this existed):
  1. a clip whose first word starts LEAD_GAP seconds or more into the audio has its lead-in read (ffmpeg, the
     lead-in only) and measured the way scripts/restamp_words.py measures loudness (6 ms frames, 36 ms held)
  2. voice there is a stretch at least VOICE_MIN long, VOICE_DB over the lead-in's own background and within
     SPEAKING_RANGE_DB of her first heard words. A silent lead-in, a click or a short breath ends it here.
  3. just that stretch (padded a little) is heard again by faster-whisper with its voice detector OFF. It sits in
     both speech-tools venvs (WhisperX is built on it), so one pass serves the WhisperX and the Intel route alike.
  4. a word it hands back is kept only when it lies over the voice that was measured, before her first heard word,
     with some confidence: the detector is off, so a word over silence is imagined, never heard, and goes.
     Kept words go in front of the clip's words, shifted onto the clip's own timeline, marked "heard_again".
  5. nothing heard: the transcript stays exactly as it was. The clip carries "lead_in_checked" (the number of
     words kept) once the second pass has run, so it is never listened to twice.
  6. the same voice detector that dropped the line can make the listener stamp ITS text on the next take instead
     (ISS-99: "Aqui va el hook." written over the take that says "Aqui van los subtitulos..."), so once a line is
     kept, the first heard words are compared with it. When they say the same thing, that stretch is heard again
     the same way (voice detector off) and, when it says something else, its words are replaced with what was
     heard ("relistened"). When it says the same thing again, she really said the line twice (a retake), and the
     words stay. Without this the transcript held the line twice and the cut kept the LAST take: the wrong one.

    <speech-tools python> scripts/quiet_first_line.py <words.json> <media_dir> <out.json>

Exit 0 with <out.json> written when a clip was listened to again, 3 when there was nothing to do, anything else on
an error (word-timings.sh treats every outcome as best-effort: a transcript is never held back by this pass).
Only the second pass needs faster-whisper, imported when a clip needs it, so the engine's tests run the rest
without the speech tools.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import restamp_words as rw  # noqa: E402  (envelope, decode, quiet-run helpers: one way of measuring loudness)

LEAD_GAP = 1.0            # seconds: a first word starting this late leaves room for a line before it
EDGE = 0.15               # the last stretch before the first word is its own onset (stamps run late), not lead-in
REFERENCE = 2.0           # seconds of her first heard words that set her speaking level
VOICE_DB = 10.0           # voice is this far over the lead-in's background (its 10th percentile)...
SPEAKING_RANGE_DB = 35.0  # ...and no more than this far under her speaking level
VOICE_MIN = 0.30          # seconds of voice in total, or it was a click or a breath
BRIDGE = 0.30             # voice runs closer than this are one stretch (the gaps between words)
PAD = 0.30                # the second pass hears this much either side of the voice
MIN_SCORE = 0.30          # the second pass's own confidence in a word it keeps
MIN_OVERLAP = 0.30        # share of a kept word's span that lies over the measured voice
VOICE_SLACK = 0.10        # its time stamps sit a little off the voice; this much either side still counts
PEAK = 0.5                # a quiet stretch is raised to this peak before it is heard (the words never change)
DUP_WORDS = 12            # how many of her first heard words can be the recovered line stamped again (its length)


def say(line):
    print(line, file=sys.stderr)


def voice_in(db, first_start):
    """The voiced stretches [(t0, t1), ...] in the lead-in before `first_start`, from envelope() readings that run
    from the clip's start through her first heard words. [] when the lead-in holds no voice."""
    frame = rw.FRAME
    upto = int((first_start - EDGE) / frame)
    lead = db[:max(0, upto)]
    if len(lead) < rw.HOLD_FRAMES:
        return []
    heard = db[int(first_start / frame):int((first_start + REFERENCE) / frame)]
    speaking = rw._pct(heard, rw.SPEAKING_PCT) if len(heard) >= 5 else max(lead)
    threshold = max(rw._pct(lead, rw.FLOOR_PCT) + VOICE_DB, speaking - SPEAKING_RANGE_DB)
    runs, k, n = [], 0, len(lead)
    while k < n:
        if lead[k] >= threshold:
            j = k
            while j < n and lead[j] >= threshold:
                j += 1
            if j - k >= rw.HOLD_FRAMES:
                runs.append([k * frame, j * frame])
            k = j
        else:
            k += 1
    stretches = []
    for t0, t1 in runs:
        if stretches and t0 - stretches[-1][1] < BRIDGE:
            stretches[-1][1] = t1
        else:
            stretches.append([t0, t1])
    if sum(t1 - t0 for t0, t1 in stretches) < VOICE_MIN:
        return []
    return [(round(t0, 3), round(t1, 3)) for t0, t1 in stretches]


def window_for(voice, first_start):
    """(start, end) in seconds of the stretch the second pass hears: the voice, padded, inside the lead-in."""
    return max(0.0, voice[0][0] - PAD), min(first_start - 0.01, voice[-1][1] + PAD)


def merge(words, found, offset, first_start, voice):
    """The clip's words with the second pass's `found` words in front. `found` times are seconds into the heard
    stretch, which starts `offset` seconds into the clip. Returns (words, how many were kept); nothing kept leaves
    a plain copy of `words`."""
    kept = []
    for w in sorted(found, key=lambda w: float(w.get("start", 0.0))):
        text = str(w.get("word", "")).strip()
        try:
            t0, t1 = float(w["start"]) + offset, float(w["end"]) + offset
            score = float(w.get("score", 1.0))
        except (KeyError, TypeError, ValueError):
            continue
        if not text or t1 <= t0 or score < MIN_SCORE:
            continue
        if (t0 + t1) / 2 >= first_start:
            continue                                   # her first heard word, heard twice
        over = sum(max(0.0, min(t1, b + VOICE_SLACK) - max(t0, a - VOICE_SLACK)) for a, b in voice)
        if over < MIN_OVERLAP * (t1 - t0):
            continue                                   # over silence: imagined, not heard
        t1 = min(t1, first_start - 0.01)
        if kept:
            t0 = max(t0, kept[-1]["end"])              # in order, never on top of each other
        if t1 <= t0:
            continue
        kept.append({"word": text, "start": round(t0, 3), "end": round(t1, 3), "score": round(score, 3),
                     "heard_again": True})
    return kept + [dict(w) for w in words], len(kept)


def _plain(text):
    """A word as it is said, for comparing two listens: no case, no accents, no punctuation."""
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(ch for ch in text if ch.isalnum())


def said_again(line, heard):
    """How many of `heard` (her first heard words) say exactly `line` (the words recovered in front of them), 0 when
    they say something else. Compared as one run of letters, so "hook." and "hook" or a split word still match."""
    want = "".join(_plain(w.get("word", "")) for w in line)
    if not want:
        return 0
    got = ""
    for n, w in enumerate(heard[:DUP_WORDS], 1):
        got += _plain(w.get("word", ""))
        if len(got) >= len(want):
            return n if got == want else 0
    return 0


def relisten(words, at, count, samples, hear, language):
    """words[at:at + count] were stamped with the recovered line's text: hear that stretch again with the voice
    detector off. Returns the words heard there (on the clip's timeline, marked), or None to leave them as they are:
    nothing heard, or the same line heard (she said it twice)."""
    dup = words[at:at + count]
    prev_end = float(words[at - 1]["end"]) if at else 0.0
    nxt = float(words[at + count]["start"]) if at + count < len(words) else None
    w0 = max(prev_end, float(dup[0]["start"]) - PAD)
    w1 = float(dup[-1]["end"]) + PAD
    if nxt is not None:
        w1 = min(w1, nxt - 0.01)
    w1 = min(w1, len(samples) / rw.RATE)
    if w1 - w0 < 0.1:
        return None
    found = hear(samples[int(w0 * rw.RATE):int(w1 * rw.RATE)], language) or []
    new = []
    for w in sorted(found, key=lambda w: float(w.get("start", 0.0))):
        text = str(w.get("word", "")).strip()
        try:
            t0, t1 = float(w["start"]) + w0, float(w["end"]) + w0
            score = float(w.get("score", 1.0))
        except (KeyError, TypeError, ValueError):
            continue
        if not text or t1 <= t0 or score < MIN_SCORE:
            continue
        if nxt is not None and (t0 + t1) / 2 >= nxt:
            continue                                   # the word after the stretch, heard again
        t0 = max(t0, new[-1]["end"] if new else prev_end)
        if nxt is not None:
            t1 = min(t1, nxt - 0.01)
        if t1 <= t0:
            continue
        new.append({"word": text, "start": round(t0, 3), "end": round(t1, 3), "score": round(score, 3),
                    "heard_again": True, "relistened": True})
    if not new or "".join(_plain(w["word"]) for w in new) == "".join(_plain(w.get("word", "")) for w in dup):
        return None
    return new


def recover_clip(clip, samples, hear, language=None):
    """One clip: (did the second pass run, words kept). `samples` are mono floats at rw.RATE from the clip's start
    through at least its first word; `hear(samples, language)` is the second pass (words with times in seconds into
    the samples it is handed). The clip's words change only when the second pass keeps a word."""
    if not needs_listen(clip):
        return False, 0
    words = clip["words"]
    if "lead_in_checked" in clip:
        # Recovered by an engine from before step 6: only the check for the line stamped on the next take is left.
        kept = int(clip["lead_in_checked"])
        _line_twice(clip, kept, samples, hear, language)
        return True, 0
    first_start = float(words[0]["start"])
    voice = voice_in(rw.envelope(samples), first_start)
    if not voice:
        return False, 0
    w0, w1 = window_for(voice, first_start)
    found = hear(samples[int(w0 * rw.RATE):int(w1 * rw.RATE)], language)
    clip["words"], kept = merge(words, found or [], w0, first_start, voice)
    clip["lead_in_checked"] = kept
    if kept:
        _line_twice(clip, kept, samples, hear, language)
    return True, kept


def needs_listen(clip):
    """True when a clip still has a pass to run: a lead-in never checked (step 1), or a line kept by an engine from
    before step 6 that was never compared with the take after it."""
    words = clip.get("words") or []
    if not words:
        return False
    if "lead_in_checked" in clip:
        try:
            kept = int(clip["lead_in_checked"] or 0)
        except (TypeError, ValueError):
            return False
        return 0 < kept < len(words) and "line_twice_checked" not in clip
    return float(words[0]["start"]) >= LEAD_GAP


def _line_twice(clip, kept, samples, hear, language):
    """Step 6 on one clip whose first `kept` words were recovered: the take after them heard again when the
    listener stamped the same line on it. Marks the clip "line_twice_checked" so it is done once."""
    words = clip["words"]
    clip["line_twice_checked"] = True
    same = said_again(words[:kept], words[kept:])
    if not same:
        return
    new = relisten(words, kept, same, samples, hear, language)
    if new:
        clip["relistened"] = {"was": " ".join(str(w.get("word", "")) for w in words[kept:kept + same]),
                              "now": " ".join(w["word"] for w in new)}
        words[kept:kept + same] = new


def clip_language(clip, diagnostics):
    """The language to hear the lead-in in: the one she named, else this clip's, else the job's main one. A short
    quiet stretch is too little for Whisper to tell the language from, so it is never left to guess when known."""
    named = os.environ.get("REELS_ENGINE_LANGUAGE", "").strip().lower()
    if named:
        return named
    for heard in (clip.get("languages"), (diagnostics or {}).get("detected_languages")):
        if isinstance(heard, dict) and heard:
            return next(iter(heard))
    return None


def faster_whisper_ear(diagnostics):
    """The second pass: faster-whisper with its voice detector off, the model the listener used (the same files,
    already on this machine), loaded the first time a clip needs it."""
    diagnostics = diagnostics or {}
    model_name = (os.environ.get("REELS_ENGINE_WHISPER_MODEL", "").strip() or diagnostics.get("model") or "small")
    tiers = [("cuda", "float16")] if diagnostics.get("device") == "cuda" else []
    tiers.append(("cpu", "int8"))
    model = []

    def load():
        from faster_whisper import WhisperModel
        last = None
        for device, ctype in tiers:
            for local in (True, False):      # this machine's own copy first: no network question on every load
                try:
                    return WhisperModel(model_name, device=device, compute_type=ctype, local_files_only=local)
                except Exception as e:       # broad: a CUDA mismatch surfaces as OSError or ImportError too
                    last = e
        raise last

    def hear(samples, language):
        import numpy as np
        if not model:
            model.append(load())
        x = np.asarray(samples, dtype=np.float32)
        peak = float(np.abs(x).max()) if len(x) else 0.0
        if 0.0 < peak < PEAK:
            x = x * (PEAK / peak)
        args = dict(language=language, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
        try:
            segments, _ = model[0].transcribe(x, **args)
        except TypeError:                    # an older build without one of the switches
            args.pop("condition_on_previous_text")
            segments, _ = model[0].transcribe(x, **args)
        return [{"word": str(w.word).strip(), "start": float(w.start), "end": float(w.end),
                 "score": float(getattr(w, "probability", 1.0))}
                for seg in segments for w in (seg.words or []) if w.start is not None and w.end is not None]
    return hear


def recover(words_path, media_dir, out_path, hear=None, decode=None):
    with open(words_path, encoding="utf-8") as f:
        data = json.load(f)
    diagnostics = None
    try:
        with open(os.path.join(os.path.dirname(words_path), ".transcribe-diagnostics.json"), encoding="utf-8") as f:
            diagnostics = json.load(f)
    except (OSError, ValueError):
        pass
    hear = hear or faster_whisper_ear(diagnostics)
    decode = decode or rw.decode
    listened = 0
    for clip in data.get("clips", []):
        words = clip.get("words") or []
        if not needs_listen(clip):
            continue
        media = os.path.join(media_dir, os.path.basename(clip.get("clip", "")))
        if not os.path.exists(media):
            media = clip.get("path", "")
        if not media or not os.path.exists(media):
            continue
        name = os.path.basename(media)
        # through her first heard line too, so a take stamped with the recovered words can be heard again (step 6)
        heard = words[int(clip.get("lead_in_checked") or 0):] if "lead_in_checked" in clip else words
        upto = max(float(heard[0]["start"]) + REFERENCE, float(heard[:DUP_WORDS][-1]["end"]) + PAD)
        try:
            ran, kept = recover_clip(clip, decode(media, upto), hear, clip_language(clip, diagnostics))
        except Exception as e:
            # The speech tools would not listen again here: the transcript stays as it was, and so does the clip
            # (no mark), so a later run can still try.
            say(f"[word-timings]    (could not listen again to the start of {name}: {type(e).__name__}: {e})")
            break
        if not ran:
            continue
        listened += 1
        if kept:
            line = " ".join(w["word"] for w in clip["words"][:kept])
            say(f"[word-timings] found a quiet first line the listener skipped in {name}; kept it: \"{line}\"")
        if clip.get("relistened"):
            say(f"[word-timings] the listener had also written that line over the next take in {name}; heard it again: "
                f"\"{clip['relistened']['now']}\" (it had \"{clip['relistened']['was']}\")")
    if not listened:
        return 3
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, out_path)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: quiet_first_line.py <words.json> <media_dir> <out.json>")
    sys.exit(recover(*sys.argv[1:]))
