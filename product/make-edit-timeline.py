#!/usr/bin/env python3
"""make-edit-timeline.py — generate a CORRECT edit-timeline.json for the COMMON case.

WHY THIS EXISTS
  build-hf-captions.py (the kinetic-caption engine) reads projects/<job>/edit-timeline.json to
  learn where every spoken word lands on the FINAL-CUT timeline. The only other writer of
  edit-timeline.json was a spoken-hook-excision tool (prep-reel.py, not part of the shipped engine)
  whose first step UNCONDITIONALLY DELETES the first clip on the main track, so on a normal job it
  would silently drop the real opening line. And a normal rough cut (the `rough-cut` skill path)
  never produces edit-timeline.json at all — it produces transcript/cuts.json and the derived
  outputs/<job>.transcript.json. So the caption path was effectively broken for a normal cut.

  This generator closes that gap: it builds a CORRECT edit-timeline.json for the COMMON case —
  KEEP EVERY CLIP, drop nothing — straight from the rough cut's own outputs. No CapCut draft
  required. (The hook-excision case, which drops the opening clip on purpose, is not this tool's job.)

SCHEMA PRODUCED (exactly what build-hf-captions.py consumes)
  {
    "total_s": <float>,                       # timeline length in seconds (inspection only)
    "beats": [                                # one beat per kept segment, in order
      {
        "clip":     <int>,                    # segment index
        "tl_start": <float>,                  # beat start on the final-cut timeline (seconds)
        "tl_end":   <float>,                  # beat end on the final-cut timeline (seconds)
        "scale":    1.0,                      # no zoom info in a plain cut -> 1.0
        "text":     <str>,                    # the beat's spoken text (readability)
        "words": [ {"w": <str>, "t": <float>, "e": <float>}, ... ]   # per-word TIMELINE timings
      }, ...
    ]
  }
  build-hf-captions.py only ever reads beats[*].words[*] as {w, t, e} (it flattens every beat's
  words and sorts by t). "w" keeps original casing + punctuation (the caption engine lowercases
  and strips punctuation itself, and splits sentences on trailing . ! ?). t/e are seconds on the
  final-cut timeline — i.e. positions in the exported video the caption overlay sits on top of.

SOURCES (rough-cut outputs)
  projects/<job>/transcript/cuts.json            — the kept segments, in order. Their durations,
                                                   summed, define each beat's [tl_start, tl_end].
  projects/<job>/outputs/<job>.transcript.json   — the DERIVED transcript: the kept words already
                                                   re-based to the final-cut timeline. This is the
                                                   authoritative word-timing source and is preferred.
  projects/<job>/transcript/words.json           — FALLBACK only (raw WhisperX word timings in
                                                   source-clip time). If the derived transcript is
                                                   missing, words are re-based per segment the same
                                                   way the hook-excision tool did.

Usage:  python3 product/make-edit-timeline.py <job>
Deterministic (no random, no date). Stdlib only.
"""
import json, os, glob, sys

ROOT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
US = 1_000_000   # CapCut microsecond unit (only touched on the words.json fallback path)


def _load_cuts(job, root):
    """Return the list of kept segments from transcript/cuts.json, in order."""
    p = f"{root}/projects/{job}/transcript/cuts.json"
    if not os.path.exists(p):
        raise SystemExit(f"cuts.json not found: {p}\nRun the rough-cut skill first (it writes transcript/cuts.json).")
    d = json.load(open(p, encoding="utf-8"))
    segs = d["segments"] if isinstance(d, dict) else d
    if not segs:
        raise SystemExit(f"the cut list is empty, nothing to keep: {p}")
    return segs


def _find_derived_transcript(job, root):
    """Prefer outputs/<job>.transcript.json; else the first outputs/*.transcript.json in the job."""
    exact = f"{root}/projects/{job}/outputs/{job}.transcript.json"
    if os.path.exists(exact):
        return exact
    hits = sorted(glob.glob(f"{root}/projects/{job}/outputs/*.transcript.json"))
    return hits[0] if hits else None


def _beats_from_cuts(segs):
    """Build the beat skeleton (metadata + empty word lists) by packing segment durations end to end."""
    beats, t = [], 0.0
    for i, s in enumerate(segs):
        dur = float(s["end"]) - float(s["start"])
        if dur < 0:
            dur = 0.0
        tl_start = round(t, 2)
        tl_end = round(t + dur, 2)
        beats.append({
            "clip": i,
            "tl_start": tl_start,
            "tl_end": tl_end,
            "scale": 1.0,
            "text": (s.get("transcript") or s.get("text") or "").strip(),
            "words": [],
        })
        t += dur
    return beats


def _assign_words_from_derived(beats, tr_path):
    """Distribute the derived transcript's already-timeline-based words into the beats.

    The derived transcript is authoritative: its start/end are seconds on the final-cut timeline.
    We walk words in order and advance the beat pointer as we cross each beat's tl_end, so every
    word lands in exactly one beat and NONE is ever dropped (the last beat catches any tail)."""
    tr = json.load(open(tr_path, encoding="utf-8"))
    raw = tr["words"] if isinstance(tr, dict) else tr
    words = []
    for w in raw:
        txt = (w.get("text") if "text" in w else w.get("word", w.get("w", ""))) or ""
        if not txt.strip():
            continue
        if "start" not in w or "end" not in w:
            continue
        words.append({"w": txt, "t": round(float(w["start"]), 2), "e": round(float(w["end"]), 2)})
    words.sort(key=lambda x: x["t"])
    bi = 0
    for w in words:
        while bi < len(beats) - 1 and w["t"] >= beats[bi]["tl_end"]:
            bi += 1
        beats[bi]["words"].append(w)
    return sum(len(b["words"]) for b in beats)


def _assign_words_from_raw(beats, segs, job, root):
    """FALLBACK: re-base raw WhisperX word timings (transcript/words.json) per segment, exactly as
    the hook-excision tool did — but keeping EVERY clip (no drop). Used only when the derived
    transcript is missing."""
    wp = f"{root}/projects/{job}/transcript/words.json"
    if not os.path.exists(wp):
        raise SystemExit(
            f"No word timings available for job '{job}'.\n"
            f"Missing both the derived transcript (outputs/{job}.transcript.json) and {wp}.\n"
            f"Run the rough-cut skill first.")
    wd = json.load(open(wp, encoding="utf-8"))
    clips = wd if isinstance(wd, list) else wd.get("clips", [wd])
    by_name = {}
    for c in clips:
        by_name[c.get("clip")] = c.get("words", [])
    default_words = clips[0].get("words", []) if clips else []
    n = 0
    for beat, s in zip(beats, segs):
        ss = float(s["start"]); se = float(s["end"]); ts = beat["tl_start"]
        src = by_name.get(s.get("clip"), default_words)
        kept = [w for w in src if w["start"] >= ss - 0.05 and w["end"] <= se + 0.15]
        beat["words"] = [
            {"w": w["w"], "t": round(ts + (w["start"] - ss), 2), "e": round(ts + (w["end"] - ss), 2)}
            for w in kept
        ]
        n += len(beat["words"])
    return n


def build(job, root=None, write=True):
    """Build (and by default write) edit-timeline.json for the common case. Returns the dict.

    Prefers the derived transcript for word timings; falls back to raw words.json. Never drops a
    clip. Safe to call from build-hf-captions.py when edit-timeline.json is missing."""
    root = root or ROOT_DEFAULT
    segs = _load_cuts(job, root)
    beats = _beats_from_cuts(segs)
    tr_path = _find_derived_transcript(job, root)
    if tr_path:
        _assign_words_from_derived(beats, tr_path)
        src = os.path.relpath(tr_path, root)
    else:
        _assign_words_from_raw(beats, segs, job, root)
        src = f"projects/{job}/transcript/words.json (fallback)"
    last_word_e = max((w["e"] for b in beats for w in b["words"]), default=0.0)
    total_s = round(max(beats[-1]["tl_end"] if beats else 0.0, last_word_e), 2)
    out = {"total_s": total_s, "beats": beats}
    if write:
        op = f"{root}/projects/{job}/edit-timeline.json"
        json.dump(out, open(op, "w", encoding="utf-8"), indent=1)
        nwords = sum(len(b["words"]) for b in beats)
        print(f"wrote {op}  ({total_s}s, {len(beats)} beats, {nwords} words)  source: {src}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 product/make-edit-timeline.py <job>")
    build(sys.argv[1])
