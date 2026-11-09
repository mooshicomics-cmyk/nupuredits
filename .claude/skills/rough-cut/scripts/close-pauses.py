#!/usr/bin/env python3
"""close-pauses.py: the stitch's dead-air pass. No kept piece of her cut holds a long silence, however the plan
was made (transcript-cut.py, a cut Claude wrote by hand, a resumed or older cut).
    close-pauses.py <raw clips folder> <words.json> <cut plan .json> <where the tightened plan goes>
stitch-cut.sh runs it right after snap-to-sound.py. It listens to each piece's own audio (the transcript's
stamps can't be trusted here: WhisperX stretches a word across a pause, and a pause can sit before a line's
first word where no gap between words ever shows it) and closes every held silence longer than MAX_QUIET:
    in the middle of a piece   the piece becomes two, KEEP_AFTER of quiet after her voice stops and KEEP_BEFORE
                               before it starts again, so the beat between them still breathes
    at a piece's start / end   the edge moves in to KEEP_BEFORE before her voice / KEEP_AFTER after it
Left exactly as planned:
  - a piece with "keep_edges" (her own edges from the visual editor, a clip with no talking kept whole) or
    "no_trim" (words she brought back): her call stands
  - a silence holding a transcribed word of ordinary length (a soft word the meter reads as quiet is still a word)
  - a silence beside a spoken amount ("$27,000 ... a month later"): its spoken words sit in that pause
  - a piece whose sound has no clear voice-against-quiet contrast (a loud room): nothing can be measured there
Every line it changes is reported; CLOSE_PAUSES=0 in the stitch skips it. Standard library plus ffmpeg only.
"""
import importlib.util, json, os, statistics, sys
try:                                       # os.replace that waits out Windows holding the plan open for a moment
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "product"))
    from swap import replace as swap_in
except ImportError:
    swap_in = os.replace
for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print ✓ or →
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("snap_to_sound", os.path.join(HERE, "snap-to-sound.py"))
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)            # one reader of her voice: the same decode, frames and transcript lookup

MAX_QUIET = 0.70     # a held silence longer than this is dead air; a comma, a breath or a beat for effect is shorter
EMO_QUIET = 1.20     # an emotional voiceover (voiceover.json "pace", product/visual_editor.py vo-pace): her held beats stay
KEEP_AFTER = 0.12    # quiet kept after her voice stops: the ring-out (snap's DECAY_AFTER) plus a little air
KEEP_BEFORE = 0.08   # quiet kept before her voice starts: the breathy attack (snap's ROOM_BEFORE) plus a little air
VOICE_RANK = 0.9     # her voice level in a piece: its 90th-percentile reading
QUIET_UNDER = 25.0   # quiet = this far under her voice (dB)
NOISE_OVER = 6.0     # ...and at least this far over the room's own floor (10th percentile), so hum is never voice
MIN_CONTRAST = 15.0  # voice and floor closer than this: a loud room, nothing to measure, the piece stays
MAX_WORD = 0.80      # a transcribed word longer than this inside a silence was stretched over it by the aligner
AMOUNT_NEAR = 1.5    # a silence this close to a spoken amount is where its spoken words sit (snap's AMOUNT_REACH)
MIN_PIECE = 0.12     # never leave a piece shorter than this


def _quiet_runs(path, a, b):
    """Held silences in [a, b] longer than MAX_QUIET, as (start, end), or None when nothing can be measured."""
    st = snap.Stretch(path, a, b)
    if len(st.db) < 10:
        return None
    ranked = sorted(st.db)
    voice, floor = ranked[int(VOICE_RANK * (len(ranked) - 1))], ranked[int(0.1 * (len(ranked) - 1))]
    if voice - floor < MIN_CONTRAST:
        return None
    line = max(voice - QUIET_UNDER, floor + NOISE_OVER)
    return [(s, e) for s, e in st.holds(line) if e - s > MAX_QUIET]


def _blocked(words, s, e):
    """Why a silence must stay (a real word inside it, or an amount beside it), or None."""
    for w in words:
        ws, we = float(w["start"]), float(w["end"])
        if ws < e and we > s and we - ws <= MAX_WORD and min(we, e) - max(ws, s) > 0.05:
            return f'"{snap._text(w)}" is said in it'
        if snap.AMOUNT.match(snap._text(w)) and ws - AMOUNT_NEAR < e and we + AMOUNT_NEAR > s:
            return f'it sits beside the amount "{snap._text(w)}"'
    return None


def tighten(segs, media_dir, words_for):
    """The plan with its dead air closed. Returns (segments, report lines, seconds taken out)."""
    out, lines, saved = [], [], 0.0
    for seg in segs:                            # each clip's sound is decoded once, over all its pieces (snap.want)
        snap.want(seg["clip"] if os.path.isabs(seg["clip"]) else os.path.join(media_dir, seg["clip"]),
                  float(seg["start"]), float(seg["end"]))
    for j, seg in enumerate(segs):
        if seg.get("keep_edges") or seg.get("no_trim") or seg.get("zoom"):   # a zoom move runs the clip as she set it
            out.append(seg); continue
        clip = seg["clip"]
        path = clip if os.path.isabs(clip) else os.path.join(media_dir, clip)
        a, b = float(seg["start"]), float(seg["end"])
        if not os.path.exists(path) or b - a <= MAX_QUIET:
            out.append(seg); continue
        runs = _quiet_runs(path, a, b)
        if not runs:
            out.append(seg); continue
        words = [w for w in words_for(clip) if "start" in w and "end" in w]
        cuts = []                               # the stretches to take out of this piece
        for s, e in runs:
            why = _blocked(words, s, e)
            if why:
                lines.append(f"[pauses] seg{j}  {e - s:.1f} s of quiet at {s:.2f} s stays: {why}")
                continue
            lo = a if s - a < 0.03 else s + KEEP_AFTER      # quiet from the piece's very start: trim the head
            hi = b if b - e < 0.03 else e - KEEP_BEFORE     # quiet to the piece's very end: trim the tail
            if hi - lo > 0.05:
                cuts.append((lo, hi))
        if not cuts:
            out.append(seg); continue
        keep, at = [], a
        for lo, hi in cuts:
            if lo - at >= MIN_PIECE:
                keep.append((at, lo))
            at = hi
        if b - at >= MIN_PIECE:
            keep.append((at, b))
        if not keep:                            # all quiet: never drop a piece the plan chose, leave it be
            out.append(seg); continue
        for ks, ke in keep:
            text = " ".join(snap._text(w) for w in words if min(float(w["end"]), ke) - max(float(w["start"]), ks) > 0.05)
            piece = {k: v for k, v in seg.items() if k not in ("start", "end", "transcript", "_snapped_from")}
            piece.update(start=round(ks, 3), end=round(ke, 3), transcript=text or seg.get("transcript", ""))
            out.append(piece)
        took = (b - a) - sum(ke - ks for ks, ke in keep)
        saved += took
        lines.append(f"[pauses] seg{j}  {took:.1f} s of dead air out ({len(cuts)} silence{'s' if len(cuts) != 1 else ''}"
                     f" over {MAX_QUIET:.1f} s), now {len(keep)} piece{'s' if len(keep) != 1 else ''}")
    return out, lines, saved


def main():
    if len(sys.argv) != 5:
        sys.exit("usage: close-pauses.py <raw clips folder> <words.json> <cut plan .json> <where the tightened plan goes>")
    media_dir, transcript_path, plan_path, out_path = sys.argv[1:]
    global MAX_QUIET
    try:
        vo = json.load(open(os.path.join(os.path.dirname(os.path.abspath(media_dir)), "voiceover.json"), encoding="utf-8"))
        if vo.get("pace") == "emotional":
            MAX_QUIET = EMO_QUIET
    except Exception:
        pass
    plan = snap._read(plan_path)
    words_for, _ = snap._transcript_lookup(snap._read(transcript_path))
    segs, lines, saved = tighten(plan.get("segments", []), media_dir, words_for)
    for line in lines:
        snap._say(line)
    payload = dict(plan, segments=segs)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
    swap_in(tmp, out_path)                      # one atomic swap, so the stitch never reads half a plan
    snap._say(f"[pauses] {'no dead air over %.1f s in the cut' % MAX_QUIET if not saved else '%.1f s of dead air taken out' % saved}"
              f"; the plan is {out_path}")


if __name__ == "__main__":
    main()
