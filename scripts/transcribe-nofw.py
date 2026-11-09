#!/usr/bin/env python3
"""The Intel-Mac listener: faster-whisper only (no torch, no whisperx), writing the engine's words.json.
Also the stand-in on any machine where WhisperX itself crashes as it loads (word-timings.sh: FW_ONLY_MARK).

word-timings.sh sends an Intel Mac here because WhisperX needs torch~=2.8 and torch's last macOS x86_64 wheel
is 2.2.2: the whisperx venv cannot be built on that machine at all. faster-whisper runs on CTranslate2, which
still ships Intel-Mac wheels, and times each word itself.

Compared with the whisperx route: no wav2vec2 alignment pass, so word times come from Whisper's own
cross-attention, the same JSON shape, ~175 MB of packages instead of ~3 GB. Those word times fold each pause
into the word after it, so every clip's words are re-stamped from the clip's own audio before they are written
(scripts/restamp_words.py says why and how it was measured).

Usage: python transcribe-nofw.py <out.json> <clip> [clip ...]
"""
import json, os, platform, sys, time

from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import restamp_words  # noqa: E402


def say(line):
    print(line, file=sys.stderr)


# ── This machine ──────────────────────────────────────────────────────────────────────────────────────────

def _physical_cores():
    try:
        import subprocess
        out = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return int(out)
    except Exception:
        return 0


def machine():
    """Logical and physical core counts, whether this is a true Intel Mac, and whether it counts as weak.

    The whisperx route's `os.cpu_count() <= 4` counts LOGICAL cores, which misreads the very machine this file
    is for: a 1.4 GHz quad-core i5 with hyperthreading reports 8 and would be handed `medium` on a chip that
    cannot carry it. So physical cores are counted here, and a true Intel Mac is weak whatever the count says:
    with no Apple Silicon int8 acceleration the ceiling is low on any of them."""
    logical = os.cpu_count() or 4
    physical = _physical_cores() or logical
    intel_mac = (sys.platform == "darwin" and platform.machine() not in ("arm64", "aarch64"))
    return logical, physical, intel_mac, (intel_mac or physical <= 4)


# ── Hearing one clip ──────────────────────────────────────────────────────────────────────────────────────

# REELS_ENGINE_LANGUAGE=<code> names the language when detection is wrong, the same switch the whisperx route reads.
FORCED_LANG = os.environ.get("REELS_ENGINE_LANGUAGE", "").strip().lower() or None
# The language WhisperX already heard in this reel, set by word-timings.sh only when it hands over a reel in a
# language with no word aligner (Haitian Creole). WhisperX hears a whole clip in one language, so this pass does
# too: deciding per segment, Kreyòl stretches can be heard as French and written down as French.
HEARD_LANG = os.environ.get("REELS_ENGINE_HEARD_LANGUAGE", "").strip().lower() or None


def load_model(model_name):
    """The model from this machine's own cache when it is there, with no network at all; online only when it is
    not. Without local_files_only every load asks Hugging Face for the newest revision first, and a broken IPv6
    route turns that one question into a ten-minute hang at 0% CPU with the model already on disk."""
    try:
        return WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True)
    except Exception:
        return WhisperModel(model_name, device="cpu", compute_type="int8")


def audio_stream_count(path):
    """How many audio streams the clip carries, from ffprobe; None when ffprobe could not read it."""
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                            "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    return len([ln for ln in r.stdout.splitlines() if ln.strip()]) if r.returncode == 0 else None


def clip_seconds(path):
    """The clip's length from its container, 0.0 when it cannot be told."""
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60)
        return max(0.0, float(r.stdout.strip()))
    except Exception:
        return 0.0


def transcribe(model, path):
    # The language is not pinned unless she named it: this is the route most likely to carry footage that is
    # not English. multilingual=True decides per SEGMENT rather than once per file, which a reel that switches
    # language needs; detection alone locks the clip to its main language and turns the rest into a paraphrase
    # of what she meant instead of what she said. Older builds lack the argument, hence the second call.
    lang = FORCED_LANG or HEARD_LANG
    try:
        if lang is None:
            return model.transcribe(path, language=None, multilingual=True, word_timestamps=True, vad_filter=True)
        return model.transcribe(path, language=lang, word_timestamps=True, vad_filter=True)
    except TypeError:
        return model.transcribe(path, language=lang, word_timestamps=True, vad_filter=True)


def hear(model, path):
    """One clip's words.json entry, with the languages its segments were heard in. A clip filmed with no audio
    stream at all (faster-whisper's decoder raises on one) comes back with no words, the entry a clip with no
    talking gets; product/quiet_clips.py marks it silent so the cut keeps it whole."""
    try:
        segments, info = transcribe(model, path)
    except Exception:
        if audio_stream_count(path) != 0:
            raise
        say(f"[word-timings]    {os.path.basename(path)} has no sound in it: kept as a clip with no talking")
        seconds = clip_seconds(path)
        return {"clip": os.path.basename(path), "path": path, "duration": round(seconds, 3),
                "languages": {}, "words": [], "restamped": 0}, seconds
    words, seg_languages = [], {}
    for seg in segments:
        lang = getattr(seg, "language", None) or getattr(info, "language", None)
        if lang:
            seg_languages[lang] = seg_languages.get(lang, 0) + 1
        words.extend({"word": str(w.word).strip(),
                      "start": round(float(w.start), 3),
                      "end": round(float(w.end), 3),
                      "score": round(float(getattr(w, "probability", 1.0)), 3)}
                     for w in (seg.words or []) if w.start is not None and w.end is not None)
    words, restamped, checked = put_pauses_back(path, words)
    return {
        "clip": os.path.basename(path),
        "path": path,
        "duration": round(float(info.duration), 3),
        # What was heard, per segment: the record that would have caught a Spanish reel labelled English.
        "languages": dict(sorted(seg_languages.items(), key=lambda kv: -kv[1])),
        "words": words,
        # Word pairs whose boundary was measured from the audio (None: the re-stamp could not run).
        "restamped": restamped,
        # A word the voice detector carried a whole pause away, moved back ("jumps_checked": how many), and any word
        # whose time still cannot be trusted ("suspect_words", named on the screen): restamp_words.jumps.
        **checked,
    }, float(info.duration)


def put_pauses_back(path, words):
    """The words with each pause measured into place from the clip's own audio, after any word the voice detector
    carried a whole pause away is moved back onto its voice (restamp_words.jumps). Returns (words, restamped,
    checked): checked holds "jumps_checked" and, when a word's time still cannot be trusted, "suspect_words", which
    are named on the screen. Best effort: on any failure the words go out exactly as transcribed, which is what this
    route wrote before."""
    try:
        from faster_whisper.audio import decode_audio
        db = restamp_words.envelope(decode_audio(path, sampling_rate=restamp_words.RATE))
        clip = {"clip": os.path.basename(path), "words": words}
        restamp_words.check_jumps(clip, db)
        checked = {k: clip[k] for k in ("jumps_checked", "suspect_words") if k in clip}
        words, restamped = restamp_words.restamp(clip["words"], db)
        return words, restamped, checked
    except Exception as e:
        say(f"[word-timings]    (word timings left as heard: {e})")
        return words, None, {}


# ── Diagnostics ───────────────────────────────────────────────────────────────────────────────────────────

def write_diagnostics(out_path, result, model_name, logical, physical, intel_mac, weak, wall_seconds,
                      clip_seconds):
    """The same file the whisperx route writes, so `python3 product/make-handoff.py hardware-diagnostic` reads
    this route with no changes. It is the only way the cost of an Intel Mac per minute of footage is ever
    learned: there is no Intel machine on the engine's side to measure. Best-effort: never fails a run."""
    diag_path = os.path.join(os.path.dirname(out_path), ".transcribe-diagnostics.json")
    try:
        scores = [w["score"] for c in result["clips"] for w in c["words"]]
        # Each clip's main language, counted the way the whisperx route counts them: the house rule reads
        # detected_languages before writing any on-screen word.
        detected = {}
        for c in result["clips"]:
            main = next(iter(c.get("languages") or {}), None)
            if main:
                detected[main] = detected.get(main, 0) + 1
        diag = {
            "engine": "faster-whisper",   # the whisperx route writes no such key: that is how they are told apart
            "engine_reason": os.environ.get("REELS_ENGINE_NOFW_REASON")
                             or "no torch on this machine (Intel Mac, or torch unavailable)",
            "detected_languages": dict(sorted(detected.items(), key=lambda kv: -kv[1])),
            "language_forced": FORCED_LANG,
            "language_heard_by_whisperx": HEARD_LANG,
            "device": "cpu", "model": model_name, "compute_type": "int8",
            "cpu_logical_cores": logical,
            "cpu_physical_cores": physical,
            "is_apple_silicon": not intel_mac,
            "is_weak_cpu": weak,
            "platform": sys.platform, "machine": platform.machine(),
            "wall_seconds": wall_seconds,
            "total_clip_seconds": round(clip_seconds, 1),
            "realtime_ratio": round(wall_seconds / clip_seconds, 2) if clip_seconds > 0 else None,
            "avg_word_confidence": round(sum(scores) / len(scores), 3) if scores else None,
            "restamped_pairs": sum(c.get("restamped") or 0 for c in result["clips"]),
        }
        os.makedirs(os.path.dirname(diag_path) or ".", exist_ok=True)
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(diag, f, indent=2)
    except Exception:
        pass


def main(out_path, clip_paths):
    logical, physical, intel_mac, weak = machine()
    # REELS_ENGINE_WHISPER_MODEL overrides, for anyone who would rather wait for full quality.
    model_name = os.environ.get("REELS_ENGINE_WHISPER_MODEL", "").strip() or ("small" if weak else "medium")
    say(f"[word-timings] loading faster-whisper {model_name} (cpu, int8, {physical} cores / {logical} threads)")
    model = load_model(model_name)

    started, clip_seconds, clips = time.monotonic(), 0.0, []
    for path in clip_paths:
        say(f"[word-timings] {os.path.basename(path)}")
        entry, seconds = hear(model, path)
        clips.append(entry)
        clip_seconds += seconds
    result = {"clips": clips}

    # utf-8 on purpose: Windows text mode would write cp1252, which cannot hold an accented word.
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    say(f"[word-timings] wrote {out_path}")
    write_diagnostics(out_path, result, model_name, logical, physical, intel_mac, weak,
                      round(time.monotonic() - started, 1), clip_seconds)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
