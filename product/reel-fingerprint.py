#!/usr/bin/env python3
"""
reel-fingerprint.py — distill a reference reel into its editing FINGERPRINT.

Reference-reel analysis tool (ships with the kit). Pull an inspo reel by link via Apify (BYOK),
then fingerprint its editing style to inform your own edit.

Takes a LOCAL clip (already downloaded into projects/<job>/references/) and prints an ANONYMIZED
fingerprint: cut cadence, hook-burst pattern, rhythm shape, and source-music BPM.
It reads only the video's rhythm math — never the creator's identity, never their footage.

Usage:
    python3 reel-fingerprint.py projects/<job>/references/ref-001.mp4
    python3 reel-fingerprint.py projects/<job>/references/ref-002.mp4 --threshold 0.3 --json

Deps: ffmpeg + ffprobe (already in the pipeline). BPM is optional — install librosa
      (`pip install librosa`) to enable it; without it the tool still works, BPM shows
      "unavailable".
"""
import argparse
import json
import subprocess
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import statistics
import tempfile
import os


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration_res_fps(path):
    r = run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration:stream=width,height,avg_frame_rate",
        "-of", "json", path,
    ])
    data = json.loads(r.stdout or "{}")
    dur = float(data.get("format", {}).get("duration", 0) or 0)
    st = (data.get("streams") or [{}])[0]
    w, h = st.get("width"), st.get("height")
    try:   # DISPLAYED size (rotation applied): a vertical phone clip must fingerprint as portrait
        import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from probe import display_dims as _dd
        w, h = _dd(path)
    except Exception:
        pass
    fr = st.get("avg_frame_rate", "0/1")
    try:
        n, d = fr.split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    except Exception:
        fps = 0.0
    return dur, w, h, fps


def detect_cuts(path, threshold):
    r = run([
        "ffmpeg", "-hide_banner", "-i", path,
        "-filter:v", f"select='gt(scene,{threshold})',metadata=print",
        "-an", "-f", "null", "-",
    ])
    cuts = []
    for line in r.stderr.splitlines():
        if "pts_time:" in line:
            try:
                cuts.append(float(line.split("pts_time:")[1].split()[0]))
            except Exception:
                pass
    return sorted(cuts)


def estimate_bpm(path):
    try:
        import librosa  # noqa
    except Exception:
        return None, "unavailable (pip install librosa to enable)"
    try:
        import librosa
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "a.wav")
            run(["ffmpeg", "-hide_banner", "-y", "-i", path, "-map", "0:a:0?", "-ac", "1", "-ar", "22050", wav])
            y, sr = librosa.load(wav, sr=22050)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            return round(float(tempo), 1), None
    except Exception as e:
        return None, f"error: {e}"


def classify(clip_durs, opening_hold, hook_burst_count):
    if len(clip_durs) < 2:
        return "single-shot / no cuts", "—"
    mean = statistics.mean(clip_durs)
    stdev = statistics.pstdev(clip_durs)
    cv = stdev / mean if mean else 0  # coefficient of variation

    if hook_burst_count >= 5:
        shape = "explosive open + dwell (bimodal)"
    elif cv >= 0.7:
        shape = "high-variance / punchy"
    elif cv <= 0.4 and opening_hold >= 2.5:
        shape = "even & steady (breathes)"
    else:
        shape = "mixed / moderate"

    # mood lean
    if hook_burst_count >= 5 or (cv >= 0.7 and mean <= 2.5):
        mood = "UPBEAT / high-energy"
    elif cv <= 0.45 and opening_hold >= 2.5:
        mood = "SENTIMENTAL / calm"
    else:
        mood = "neutral / mid-energy"
    return shape, mood


def ending_trend(clip_durs):
    # Look at the tail (last third, min 4 clips), drop the very last segment which is
    # often a trailing hold/fade that isn't a real content beat. Use the linear slope.
    if len(clip_durs) < 5:
        return "—"
    tail = clip_durs[-max(4, len(clip_durs) // 3):]
    tail = tail[:-1] if len(tail) > 4 else tail  # drop trailing segment when we can spare it
    n = len(tail)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(tail) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1
    slope = sum((xs[i] - mx) * (tail[i] - my) for i in range(n)) / denom
    if slope > 0.15:
        return "DECELERATES (slows to land the beat)"
    if slope < -0.15:
        return "accelerates (tightens at the end)"
    return "holds steady"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="local video file (e.g. projects/<job>/references/ref-001.mp4)")
    ap.add_argument("--threshold", type=float, default=0.3, help="scene-cut sensitivity (0.2 loose – 0.4 strict)")
    ap.add_argument("--json", action="store_true", help="also write <clip>.fingerprint.json")
    args = ap.parse_args()

    if not os.path.exists(args.clip):
        print(f"file not found: {args.clip}", file=sys.stderr)
        sys.exit(1)

    label = os.path.splitext(os.path.basename(args.clip))[0]  # anonymized code, e.g. ref-001
    dur, w, h, fps = probe_duration_res_fps(args.clip)
    cuts = detect_cuts(args.clip, args.threshold)

    boundaries = [0.0] + cuts + [dur]
    clip_durs = [round(boundaries[i + 1] - boundaries[i], 2) for i in range(len(boundaries) - 1)]
    n_clips = len(clip_durs)
    n_cuts = len(cuts)
    avg_clip = round(dur / n_clips, 2) if n_clips else dur
    cuts_per_10s = round(n_cuts / dur * 10, 1) if dur else 0
    opening_hold = round(cuts[0], 2) if cuts else round(dur, 2)
    hook_burst_count = sum(1 for c in cuts if c <= 2.0)
    shape, mood = classify(clip_durs, opening_hold, hook_burst_count)
    ending = ending_trend(clip_durs)
    bpm, bpm_note = estimate_bpm(args.clip)

    burst_line = (
        f"YES — {hook_burst_count} cuts in first 2s (~{round(2.0/hook_burst_count,2)}s each), then settle"
        if hook_burst_count >= 5 else
        f"no — first cut at {opening_hold}s (slow open)"
    )

    print("")
    print(f"  🎬 REEL FINGERPRINT — {label}")
    print( "  " + "─" * 46)
    print(f"  duration        {dur:.1f}s   ({w}x{h}, {fps:.2f}fps)")
    print(f"  clips / cuts    {n_clips} clips, {n_cuts} cuts")
    print(f"  avg clip        {avg_clip}s   ({cuts_per_10s} cuts / 10s)")
    print(f"  opening hold    {opening_hold}s")
    print(f"  hook burst      {burst_line}")
    print(f"  rhythm shape    {shape}")
    print(f"  ending          {ending}")
    print(f"  mood lean       {mood}")
    print(f"  source BPM      {bpm if bpm is not None else bpm_note}")
    print( "  " + "─" * 46)
    print(f"  clip lengths    {clip_durs}")
    print("")

    if args.json:
        out = {
            "label": label, "duration_s": round(dur, 2), "width": w, "height": h, "fps": round(fps, 2),
            "clips": n_clips, "cuts": n_cuts, "avg_clip_s": avg_clip, "cuts_per_10s": cuts_per_10s,
            "opening_hold_s": opening_hold, "hook_burst_cuts_first_2s": hook_burst_count,
            "rhythm_shape": shape, "ending_trend": ending, "mood_lean": mood,
            "source_bpm": bpm, "clip_lengths_s": clip_durs, "scene_threshold": args.threshold,
        }
        jpath = args.clip + ".fingerprint.json"
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"  → wrote {jpath}\n")


if __name__ == "__main__":
    main()
