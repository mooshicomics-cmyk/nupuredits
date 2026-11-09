#!/usr/bin/env python3
"""vo-ambience.py — lay the REAL house sound from the b-roll back under a finished Voiceover reel.

A VO reel's picture is reframed b-roll, and reframing drops the source audio — so the finished reel is
voice + music over silent pictures. For a documentary-style VO (running water, dishes, a broom) that
texture is a large part of what sells "this actually happened in one stretch." This rebuilds an ambience
track from the SAME windows the shot plan used, so every sound lands on the shot that made it, and mixes
it in underneath.

Level is MEASURED, never a fixed gain: it reads the finished reel's integrated loudness and places the
ambience a set number of LU below it, so a quiet house and a loud one both land in the same place.
Shots with no audio stream (rendered graphics, screen demos) contribute silence.

Every piece is exactly as long as its shot is in the picture, so each sound stays on the shot that made
it all the way down the reel: vo-build renders whole frames at 30 fps (a 0.55 s shot is 17 frames), holds
a clip's last frame when a shot asks for more than the clip has, and uses the pace's burst length when the
shot plan names none. Pass the same --pace the reel was built with.

  python3 product/vo-ambience.py --job <job> [--pace punchy|emotional] [--under 20] [--in final.mp4] [--out final.amb.mp4]

Reads   projects/<job>/shot-plan.json   (burst + holds, in timeline order)
Writes  projects/<job>/audio/ambience.wav  +  the mixed video
"""
import argparse, json, os, re, subprocess, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
FPS = 30                                          # vo-build renders every shot at this rate
PACE_BURST = {"punchy": 0.35, "emotional": 0.55}  # vo-build's burst length when the plan names none


def _shot_len(dur):
    """How long vo-build's picture actually holds a shot of `dur` seconds: it renders whole frames, keeping
    each frame that starts before the requested length, which ffmpeg rounds to the nearest frame. A 0.55 s
    burst is 17 frames (0.567 s) and a 0.35 s one 11 (0.367 s). Cutting the ambience to the raw `dur`
    instead let every piece drift a little further off its shot."""
    us = round(float(f"{dur:.3f}") * 1_000_000)    # vo-build passes -t with three decimals
    return max(1, (us * FPS + 500_000) // 1_000_000) / FPS


def _has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                          "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return out.startswith("audio")


def _lufs(path):
    """Integrated loudness via ffmpeg's loudnorm analysis (measured, never assumed)."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-map", "0:a:0?", "-af", "loudnorm=print_format=summary",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"Input Integrated:\s*(-?[\d.]+)", r.stderr)
    return float(m.group(1)) if m else None


def build(job, under=20.0, src=None, out=None, pace="emotional"):
    jd = f"{REPO}/projects/{job}"
    plan = json.load(open(f"{jd}/shot-plan.json", encoding="utf-8"))
    # the burst length vo-build used: the plan's own, else the pace's (this read 0.35 on every pace, while an
    # emotional build holds each burst shot 0.55 s, so every later sound landed early)
    stab = float(plan["burst_stab"]) if "burst_stab" in plan else PACE_BURST[pace]
    segs = [(b["path"], float(b["in"]), stab) for b in plan.get("burst", [])] + \
           [(h["path"], float(h["in"]), float(h["out"]) - float(h["in"])) for h in plan["holds"]]

    tmp = tempfile.mkdtemp()
    parts, silent = [], 0
    for i, (path, tin, dur) in enumerate(segs):
        p = f"{tmp}/a{i:03d}.wav"
        length = _shot_len(dur)
        if _has_audio(path):
            # apad + -t: a clip whose sound ends before its shot does (vo-build holds the picture's last frame
            # there) still gives a piece exactly as long as the shot, so nothing after it slides earlier
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tin}", "-t", f"{length}", "-i", path, "-map", "0:a:0?",
                            "-vn", "-ac", "2", "-ar", str(SR), "-af", "apad", "-t", f"{length}",
                            "-c:a", "pcm_s16le", "-y", p], check=True)
        else:
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            f"anullsrc=r={SR}:cl=stereo", "-t", f"{length}", "-c:a", "pcm_s16le", "-y", p],
                           check=True)
            silent += 1
        parts.append(p)

    lst = f"{tmp}/list.txt"
    open(lst, "w", encoding="utf-8").write("".join(f"file '{p}'\n" for p in parts))
    amb = f"{jd}/audio/ambience.wav"
    os.makedirs(f"{jd}/audio", exist_ok=True)
    # tiny crossfades are not worth the complexity here; a hard butt-join on a bed this quiet is inaudible
    subprocess.run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-af", "afade=t=in:d=0.4,highpass=f=90", "-c:a", "pcm_s16le", "-y", amb], check=True)

    if not src:
        return amb, None, silent, len(segs)

    prog, ambl = _lufs(src), _lufs(amb)
    if prog is None or ambl is None:
        gain = -26.0
        note = "loudness probe failed — fell back to a conservative fixed trim"
    else:
        gain = round(prog - under - ambl, 2)
        note = f"programme {prog:.1f} LUFS · ambience {ambl:.1f} LUFS · placed {under:.0f} LU under"
    out = out or src.replace(".mp4", ".amb.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-i", amb,
                    "-filter_complex",
                    f"[1:a]volume={gain}dB,alimiter=limit=0.85[a1];[0:a][a1]amix=inputs=2:duration=first:"
                    f"dropout_transition=0:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-y", out], check=True)
    return amb, (out, gain, note), silent, len(segs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--pace", default="emotional", choices=["punchy", "emotional"],
                    help="the pace the reel was built with (vo-build --pace); sets the burst length when the "
                         "shot plan names none")
    ap.add_argument("--under", type=float, default=20.0, help="LU below the programme (default 20)")
    ap.add_argument("--in", dest="src", default=None, help="finished reel to mix into")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    amb, mixed, silent, total = build(a.job, a.under, a.src, a.out, pace=a.pace)
    print(f"ambience -> {amb}   ({total} shots, {silent} silent)")
    if mixed:
        out, gain, note = mixed
        print(f"mixed    -> {out}   gain {gain:+.1f} dB   ({note})")
