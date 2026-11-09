# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
vo-splice.py — rough-cut the VOICEOVER. Drop the deleted lines, splice the kept audio clean, apply the
register's PACING to the gaps between lines, and re-derive word timings. The VO parallel to the Yaps'
`stitch-cut.sh` — because the recording is never perfect.

  • --cut "3,5"      delete those transcript lines (1-based, matching the style-plan widget) — bad takes / filler
  • --pace punchy    TRIM the dead space between lines (tight, energetic)   [gap floor ~0.14s]
  • --pace emotional KEEP the breathing room (let each line land)           [natural pauses]

Reads   projects/<job>/audio/vo.*  +  projects/<job>/vo-grid.json
Writes  projects/<job>/audio/vo.clean.wav        (the spliced clean voiceover — the new spine)
        projects/<job>/vo-grid.clean.json        (re-timed words/phrases for the captions + cut grid)
vo-build.py prefers these `.clean` files when present.

Usage:
  uv run product/vo-splice.py --job my-reel --cut "3" --pace emotional
  uv run product/vo-splice.py --job my-reel --pace punchy          # no deletes, just tighten the gaps
"""
import argparse, json, os, re, subprocess, tempfile, sys, glob
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUNCHY_GAP = 0.14   # floor gap between lines when punchy (trim dead space to this)


def normalize(src, dst, target, ceiling=-3.0):
    """Bring the spliced VO up with a STATIC chain, held under a TRUE-PEAK ceiling so it cannot redline.

    A phone voice memo lands anywhere from -38 LUFS (recorded across the room) to -16 (held close), and the
    VO path had no leveling at all, so a quiet memo shipped a reel nobody could hear. The Yap path uses a
    fixed +10 dB amplify, which only works because that mic sits at a known distance; a voiceover has no
    such guarantee. So the gain is MEASURED per take.

    Loudness alone is not enough, and chasing it is how this went wrong the first time. A take recorded
    across a quiet room has a big peak-to-loudness ratio, so dragging it to the -14 LUFS social norm drove
    true peak to -1 dBTP and left the whole programme redlining once a music bed sat on top. The gain is
    therefore the SMALLER of what loudness wants and what the peak ceiling allows, and the limiter is a
    safety net for stray transients rather than the thing doing the work. Still static: no compressor
    riding the level, so it cannot pump.
    """
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", src, "-map", "0:a:0?", "-af", "loudnorm=print_format=summary",
                        "-f", "null", "-"], capture_output=True, text=True)
    lufs = re.search(r"Input Integrated:\s*(-?[\d.]+)", r.stderr)
    tp = re.search(r"Input True Peak:\s*(-?[\d.]+)", r.stderr)
    measured = float(lufs.group(1)) if lufs else None
    peak = float(tp.group(1)) if tp else None
    if measured is None:
        gain, why = 0.0, "loudness probe failed, left as recorded"
    else:
        want_loud = target - measured
        want_peak = (ceiling - peak) if peak is not None else want_loud
        gain = max(-6.0, min(30.0, want_loud, want_peak))
        why = ("held back by the peak ceiling" if want_peak < want_loud else "set by loudness")
    limit = 10 ** (ceiling / 20.0)          # the limiter catches strays; it is not the level control
    subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-map", "0:a:0?", "-af",
                    f"volume={gain:.2f}dB,alimiter=limit={limit:.4f}:level=disabled",
                    "-c:a", "pcm_s16le", "-y", dst], check=True)
    return gain, measured, peak, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--cut", default="")                 # "3,5" line numbers to delete
    ap.add_argument("--pace", default="emotional", choices=["punchy", "emotional"])
    ap.add_argument("--target", type=float, default=-18.0,
                    help="integrated LUFS to aim for (default -18; the peak ceiling can hold it lower)")
    ap.add_argument("--ceiling", type=float, default=-3.0,
                    help="true-peak ceiling in dBTP (default -3, so a music bed on top still has room)")
    ap.add_argument("--pad", type=float, default=0.05)   # small lead/tail so words don't clip
    args = ap.parse_args()

    jd = f"{REPO}/projects/{args.job}"
    if not os.path.exists(f"{jd}/vo-grid.json"):
        sys.exit(f"no vo-grid.json in projects/{args.job}/ — run vo-cutgrid first:  uv run product/vo-cutgrid.py --job {args.job}")
    grid = json.load(open(f"{jd}/vo-grid.json", encoding="utf-8"))
    phrases = grid["phrases"]
    vo = next((p for e in ("m4a","wav","mp3","aac","mov","mp4","caf") for p in [f"{jd}/audio/vo.{e}"] if os.path.exists(p)), None)
    if not vo: sys.exit(f"no VO audio in {jd}/audio/")

    cut = set(int(x) for x in args.cut.replace(" ", "").split(",") if x.strip())
    kept = [(i, p) for i, p in enumerate(phrases) if (i + 1) not in cut]
    if not kept: sys.exit("every line was cut — nothing left")

    def gap_for(orig):                                   # pacing knob
        return min(orig, PUNCHY_GAP) if args.pace == "punchy" else max(0.0, orig)

    kept_idx = {i for i, _ in kept}
    tmp = tempfile.mkdtemp(); parts = []; new_words = []; new_phrases = []; t = 0.0
    for idx, (i, p) in enumerate(kept):
        # Each kept line gets a small pad either side so no word is clipped. Two neighbouring lines that are
        # BOTH kept can sit closer than two pads (a quick run-on), and padding each on its own then stitched
        # the voice between them in twice. Split that gap at its midpoint instead; a wider gap is untouched.
        head = tail = args.pad
        if i - 1 in kept_idx and p["a"] - phrases[i - 1]["b"] < 2 * args.pad - 1e-9:
            head = max(0.0, (p["a"] - phrases[i - 1]["b"]) / 2)
        if i + 1 in kept_idx and phrases[i + 1]["a"] - p["b"] < 2 * args.pad - 1e-9:
            tail = max(0.0, (phrases[i + 1]["a"] - p["b"]) / 2)
        a = max(0.0, p["a"] - head); b = p["b"] + tail; seg_dur = b - a
        seg = f"{tmp}/seg{idx:03d}.wav"
        subprocess.run(["ffmpeg","-v","error","-ss",f"{a:.3f}","-i",vo,"-map","0:a:0?","-t",f"{seg_dur:.3f}",
                        "-ar","48000","-ac","2","-y",seg], check=True)
        parts.append(seg)
        pw = []
        for w in p["words"]:
            nw = {"w": w["w"], "a": round(t + (w["a"] - a), 2), "b": round(t + (w["b"] - a), 2)}
            new_words.append(nw); pw.append(nw)
        new_phrases.append({"text": p["text"], "a": round(t + (p["a"] - a), 2),
                            "b": round(t + (p["b"] - a), 2), "words": pw})
        t += seg_dur
        if idx < len(kept) - 1:                          # pace-controlled silence before the next line
            g = gap_for(kept[idx+1][1]["a"] - p["b"])
            if g > 0.01:
                sil = f"{tmp}/sil{idx:03d}.wav"
                subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","anullsrc=r=48000:cl=stereo",
                                "-t",f"{g:.3f}","-y",sil], check=True)
                parts.append(sil); t += g

    lst = f"{tmp}/l.txt"; open(lst, "w", encoding="utf-8").write("".join(f"file '{p}'\n" for p in parts))
    out_audio = f"{jd}/audio/vo.clean.wav"
    raw_audio = f"{jd}/audio/vo.spliced.raw.wav"
    subprocess.run(["ffmpeg","-v","error","-f","concat","-safe","0","-i",lst,"-c:a","pcm_s16le","-y",raw_audio], check=True)
    gain, measured, peak, why = normalize(raw_audio, out_audio, args.target, args.ceiling)

    clean = {"duration": round(t, 2), "transcript": " ".join(w["w"] for w in new_words),
             "words": new_words, "phrases": new_phrases,
             "cuts": [round(p["a"], 2) for p in new_phrases],
             "pace": args.pace, "cut_lines": sorted(cut)}
    json.dump(clean, open(f"{jd}/vo-grid.clean.json", "w", encoding="utf-8"), indent=2)

    orig = grid.get("duration", phrases[-1]["b"])
    print(f"spliced VO: kept {len(kept)}/{len(phrases)} lines"
          + (f", cut {sorted(cut)}" if cut else "") + f", {args.pace} pacing")
    print(f"  duration {orig:.1f}s -> {t:.1f}s  ({'-' if t<orig else '+'}{abs(orig-t):.1f}s)")
    print(f"  level {measured:.1f} LUFS / {peak:.1f} dBTP -> {measured+gain:.1f} LUFS / "
          f"{peak+gain:.1f} dBTP  (static {gain:+.1f} dB, {why})"
          if measured is not None else "  level: loudness probe failed, left as recorded")
    print(f"  -> audio/vo.clean.wav  +  vo-grid.clean.json  (vo-build uses these next)")


if __name__ == "__main__":
    main()
