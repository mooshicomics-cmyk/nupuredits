#!/usr/bin/env python3
"""bed-plan.py — decide how a music bed sits under her voice, for lay-bed.sh.

Two answers, printed one per line for the shell to read:

  GAIN <dB> <how>     the gain the music gets. Measured by default: the track's mean is set BED_DUCK_DB under
                      the cut's mean (product/audio_levels.py, the same rule the rendered route uses), so a quiet
                      track and a loud one both land at the same place behind her. A level she asked for
                      (--bed-db N) is used as given.
  LIFT <expr | ->     with --lift, an ffmpeg volume expression that raises the music in the gaps between her words
                      and holds it at the bed level while she talks. The gaps come from her own transcript of the
                      cut (outputs/<job>.transcript.json beside the video), so the music moves exactly where she
                      stops, never late the way a level detector does. "-" when there is no lift to apply.

  python3 bed-plan.py <video> <music> [--bed-db N] [--lift] [--transcript <file>]

Anything it could not do (no transcript, a track it could not measure) is said in one line on stderr, and the
bed still goes down: flat and at a measured or fixed level.
"""
import json, os, sys
for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print every character in a status line
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ENGINE, "product"))
from audio_levels import BED_DUCK_DB, GAIN_MAX_DB, GAIN_MIN_DB, mean_dbfs   # noqa: E402

LIFT_DB = 6.0        # how far the music rises in a pause, over its level under her voice
MIN_GAP = 0.8        # a pause shorter than this is breath, not room: the music stays put
RAMP = 0.3           # seconds the music takes to rise or settle, so a lift never jumps


def _say(msg):
    print(f"[lay-bed] {msg}", file=sys.stderr)


def transcript_for(video, given=None):
    """The cut's kept-words transcript: the one named, else <video stem>.transcript.json beside the video."""
    if given:
        return given if os.path.exists(given) else None
    stem = os.path.splitext(video)[0]
    for suffix in (".transcript.json",):
        if os.path.exists(stem + suffix):
            return stem + suffix
    return None


def spoken_spans(path):
    """(start, end) of every stretch she is speaking, in cut seconds, with breaths inside a stretch folded in."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    words = data.get("words", []) if isinstance(data, dict) else data
    spans = []
    for w in sorted((w for w in words if w.get("start") is not None and w.get("end") is not None),
                    key=lambda w: float(w["start"])):
        a, b = float(w["start"]), float(w["end"])
        if spans and a - spans[-1][1] < MIN_GAP:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


def pauses(spans, length):
    """The open stretches between her words (and before the first, after the last) long enough to lift in."""
    edges, t = [], 0.0
    for a, b in spans:
        if a - t >= MIN_GAP:
            edges.append((t, a))
        t = max(t, b)
    if length - t >= MIN_GAP:
        edges.append((t, length))
    return edges


def lift_expression(gaps):
    """volume expression: 1 under her voice, rising to LIFT_DB over RAMP inside each pause and back before she
    speaks again. Each pause contributes a trapezoid; pauses never overlap, so they simply add."""
    if not gaps:
        return None
    k = 10 ** (LIFT_DB / 20) - 1
    terms = [f"clip((t-{a:.3f})/{RAMP},0,1)*clip(({b:.3f}-t)/{RAMP},0,1)" for a, b in gaps]
    return f"1+{k:.4f}*({'+'.join(terms)})"


def duration(video):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", video], capture_output=True, text=True, encoding="utf-8")
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def main(argv):
    if len(argv) < 2:
        sys.exit("usage: bed-plan.py <video> <music> [--bed-db N] [--lift] [--transcript <file>]")
    video, music = argv[0], argv[1]
    rest = argv[2:]
    asked = rest[rest.index("--bed-db") + 1] if "--bed-db" in rest else None
    given = rest[rest.index("--transcript") + 1] if "--transcript" in rest else None

    if asked not in (None, ""):
        print(f"GAIN {float(asked):.1f} set")
    else:
        programme, track = mean_dbfs(video), mean_dbfs(music)
        if programme is None or track is None:
            _say("could not measure the cut or the track, so the music sits at -18 dB")
            print("GAIN -18.0 fallback")
        else:
            # bed_gain_db's own rule (track mean lands BED_DUCK_DB under the cut's mean), on the measurement
            # already in hand, so the track is read once
            gain = max(GAIN_MIN_DB, min(GAIN_MAX_DB, programme + BED_DUCK_DB - track))
            print(f"GAIN {gain:.1f} measured")

    expr = None
    if "--lift" in rest:
        path = transcript_for(video, given)
        length = duration(video)
        if not path:
            _say("no transcript of this cut beside it, so the music stays at one level (no lift in the pauses)")
        elif length is None:
            _say("could not read the cut's length, so the music stays at one level")
        else:
            expr = lift_expression(pauses(spoken_spans(path), length))
            if expr is None:
                _say("she talks the whole way through, so there is no pause for the music to lift in")
    print(f"LIFT {expr or '-'}")


if __name__ == "__main__":
    main(sys.argv[1:])
