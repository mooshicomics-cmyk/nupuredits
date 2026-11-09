#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get numpy 1
# ///
"""sync_camera.py: line a second camera up with her footage by sound, and say whose mic carries each line.

A second phone filming the same moment (the other person's face, a wide shot) is the PIP the `pip` command in
workflows/capcut-live.py lays over her cut. Both cameras heard the same room, so their sound lines them up:

  1. Sync. Every main clip her cut list uses is cross-correlated against the second camera's sound (GCC-PHAT:
     FFT cross-correlation with every frequency weighted equally, 8 kHz mono, speech band), then each of the
     strongest whole-clip peaks is re-checked in 10 s chunks along the clip, each chunk searched close to it. A
     clip is LOCKED when most matching chunks agree within 13 ms. The whole-clip peak can be weak (only 1.2x the
     next one, a distant second mic) and the clip still lock chunk-wise; a clip filmed while the second camera
     was off locks nothing and gets null. Never a guessed offset.
  2. Whose mic. For every kept line both cameras cover, the second camera's level is compared with hers,
     relative to the median of all lines. A line where the second camera is at least 10 dB hotter than usual is
     the other person talking (their phone is their mic), so the PIP's sound plays and her clip goes quiet
     there; everywhere else the PIP is muted and her mic carries the line. A line that changes speaker
     part-way is flagged with the word gap to split it at.

Writes, in projects/<job>/assets/pip/ (the second camera is COPIED there; the original is never moved):
  sync.json        {pip, pip_duration, offsets: {main clip: pip time at that clip's t=0, or null}, checks}
                   pip_t = main_t + offset
  mic-report.json  one row per kept line: levels, the mic that carries it, coverage, a split point if mixed

  uv run product/sync_camera.py <job> <second-camera file>
      --pip-mic <clip>   the second camera's mic carries EVERY line of that main clip (its phone was simply the
                         better mic for both people there); repeat for more clips
      --hotter <dB>      how much hotter than usual the second camera must be to carry a line (default 10)
      --split-mixed      split each mixed line in transcript/cuts.json at its word gap (contiguous source,
                         keep_edges), the old list kept in transcript/history/; the rough cut is then re-stitched
      --dry-run          measure and print, write nothing

A line in cuts.json carrying "pip_audio": true / false is her call and always wins over the measurement.
Then: uv run workflows/capcut-live.py pip "<draft>" <job>
"""
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

REPO = Path(__file__).resolve().parent.parent
RATE = 8000                    # Hz: plenty for speech timing, light enough for an hour of second camera
BAND = (100.0, 3800.0)         # the speech band the correlation listens to
CHUNK_S = 10.0                 # each clip is re-checked in chunks this long
LOCK_SPREAD_S = 0.013          # chunk offsets agreeing this closely (well under half a frame) = locked
CHUNK_RATIO = 2.5              # a chunk matches when its peak is this many times the next best one (a real
                               # match measured 3.4x and up even on a distant mic; a wrong offset never passed 1.5x)
AGREE_SHARE = 0.6              # ... and most matching chunks must sit inside that 13 ms window
CANDIDATES = 5                 # whole-clip peaks re-checked chunk by chunk
SEARCH_S = 1.0                 # how far from a candidate each chunk is searched
EXCLUDE_S = 0.05               # around a peak, ignored when looking for the next best one
SILENT_DB = -55.0              # a chunk or line quieter than this has nothing to hear
HOTTER_DB = 10.0               # second camera this much hotter than usual = the other person's line
MIN_RUN_S = 0.4               # a speaker change needs a run of words at least this long (or two words)
MIN_COVER_S = 0.25             # a line the second camera covers for less than this is not covered


# ── sound ────────────────────────────────────────────────────────────────────────────────────────────────

def decode(path):
    """Mono float32 at RATE, via ffmpeg."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", str(RATE),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw[:len(raw) // 4 * 4], dtype="<f4").astype(np.float32)


def level_db(pcm, start_s, end_s):
    """RMS level in dBFS of pcm between two times; None when the window falls outside it."""
    lo, hi = max(0, int(round(start_s * RATE))), min(len(pcm), int(round(end_s * RATE)))
    if hi - lo < RATE * 0.05:
        return None
    seg = pcm[lo:hi].astype(np.float64)
    return float(20 * np.log10(np.sqrt(np.mean(seg * seg)) + 1e-9))


# ── sync ─────────────────────────────────────────────────────────────────────────────────────────────────

def _nfft(n):
    return 1 << (int(n) - 1).bit_length()


def xcorr(a, b, b_spectrum=None):
    """GCC-PHAT of a against b, as (lags, strengths): at lag k, b[i + k] lines up with a[i]. Every frequency in the
    speech band counts the same (PHAT), so a quiet, distant second mic still lines up on the shape of the sound."""
    n = _nfft(len(a) + len(b))
    cross = np.conj(np.fft.rfft(a, n)) * (b_spectrum(n) if b_spectrum else np.fft.rfft(b, n))
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    cross[(freqs < BAND[0]) | (freqs > BAND[1])] = 0
    cross /= np.abs(cross) + 1e-12
    r = np.fft.irfft(cross, n)
    # irfft(conj(A) B)[k] = sum a[i] b[i + k]: lag k >= 0 sits at k, lag -k at n - k
    return (np.arange(-(len(a) - 1), len(b)),
            np.abs(np.concatenate([r[n - (len(a) - 1):], r[:len(b)]])))


def peaks(lags, vals, count=1):
    """The `count` strongest peaks at least EXCLUDE_S apart, as [(lag, ratio over the next best peak)]."""
    vals = vals.copy()
    found = []
    for _ in range(count + 1):
        if not len(vals) or vals.max() <= 0:
            break
        best = int(np.argmax(vals))
        found.append((int(lags[best]), float(vals[best])))
        vals[np.abs(lags - lags[best]) <= EXCLUDE_S * RATE] = 0
    return [(lag, strength / found[i + 1][1] if i + 1 < len(found) and found[i + 1][1] > 0 else float("inf"))
            for i, (lag, strength) in enumerate(found[:count])]


class Reference:
    """The second camera's sound, with its spectrum kept per FFT size so it is only ever transformed once."""

    def __init__(self, pcm):
        self.pcm = pcm
        self._spectra = {}

    def spectrum(self, n):
        if n not in self._spectra:
            self._spectra[n] = np.fft.rfft(self.pcm, n)
        return self._spectra[n]


def check_locally(main, ref, candidate, chunk):
    """Each chunk of the clip searched within SEARCH_S of the candidate offset: [(chunk start, offset, ratio)]."""
    pip, out, t0 = ref.pcm, [], 0.0
    duration = len(main) / RATE
    while t0 + chunk <= duration + 1e-6:
        piece = main[int(t0 * RATE):int((t0 + chunk) * RATE)]
        loudness = level_db(piece, 0, chunk)
        lo = max(0, int((t0 + candidate - SEARCH_S) * RATE))
        hi = min(len(pip), int((t0 + candidate + chunk + SEARCH_S) * RATE))
        if loudness is not None and loudness > SILENT_DB and hi - lo >= 2 * RATE:
            lags, vals = xcorr(piece, pip[lo:hi])
            offsets = (lo + lags) / RATE - t0               # pip_t - main_t for each lag
            near = np.abs(offsets - candidate) <= SEARCH_S
            if near.any():
                (lag, ratio), = peaks(lags[near], vals[near])
                out.append((round(t0, 2), (lo + lag) / RATE - t0, ratio))
        t0 += chunk
    return out


def densest(values, width):
    """The largest run of values that fit inside one window `width` wide (sorted)."""
    values, best = sorted(values), []
    for i, low in enumerate(values):
        run = [v for v in values[i:] if v - low <= width]
        if len(run) > len(best):
            best = run
    return best


def sync_clip(main, ref):
    """Offset (seconds, pip_t = main_t + offset) of one main clip, or None, plus the evidence.

    The whole clip against the whole second camera names a few candidates; a distant second mic can leave the
    right one barely above the noise (1.2x), so each candidate is then re-checked chunk by chunk, every chunk
    searched only close to it. The right offset makes chunk after chunk peak sharply (3x and up) at the same
    place; a wrong one never does."""
    duration = len(main) / RATE
    if duration < 2 or len(ref.pcm) < 2 * RATE:
        return None, {"locked": False, "why": "too short to line up by sound"}
    lags, vals = xcorr(main, ref.pcm, ref.spectrum)
    candidates = peaks(lags, vals, CANDIDATES)
    chunk = max(2.0, min(CHUNK_S, duration / 2))
    best = None
    for lag, whole_ratio in candidates:
        found = check_locally(main, ref, lag / RATE, chunk)
        sure = [offset for _, offset, ratio in found if ratio >= CHUNK_RATIO]
        if not sure:
            continue
        agreeing = densest(sure, LOCK_SPREAD_S)
        if best is None or len(agreeing) > len(best["agreeing"]):
            best = {"whole": lag / RATE, "whole_ratio": whole_ratio, "chunks": len(found), "sure": sure,
                    "agreeing": agreeing}
    if best is None:
        lag, whole_ratio = candidates[0] if candidates else (0, 0.0)
        return None, {"whole_clip_offset": round(lag / RATE, 3), "whole_clip_ratio": round(min(whole_ratio, 999), 2),
                      "locked": False,
                      "why": "no stretch of this clip matches the second camera (filmed while it was off, or too "
                             "far away to hear the same room)"}
    agreeing = best["agreeing"]
    spread = agreeing[-1] - agreeing[0]
    locked = len(agreeing) >= 2 and len(agreeing) >= AGREE_SHARE * len(best["sure"])
    check = {"whole_clip_offset": round(best["whole"], 3), "whole_clip_ratio": round(min(best["whole_ratio"], 999), 2),
             "chunks": best["chunks"], "chunks_sure": len(best["sure"]), "chunks_agreeing": len(agreeing),
             "spread_ms": round(spread * 1000, 1), "locked": locked}
    if not locked:
        check["why"] = (f"only {len(agreeing)} of its {len(best['sure'])} matching chunks agree within "
                        f"{LOCK_SPREAD_S * 1000:.0f} ms")
        return None, check
    offset = float(np.median(agreeing))
    check["overlap_s"] = round(max(0.0, min(duration, len(ref.pcm) / RATE - offset) - max(0.0, -offset)), 2)
    return round(offset, 3), check


# ── whose mic ────────────────────────────────────────────────────────────────────────────────────────────

def _runs(labels):
    runs = []
    for i, label in labels:
        if runs and runs[-1][0] == label:
            runs[-1][1].append(i)
        else:
            runs.append((label, [i]))
    return runs


def mic_report(cuts, offsets, main_pcm, pip_pcm, words_of, hotter=HOTTER_DB, pip_mic_clips=()):
    """One row per kept line: how loud each camera is, and whose mic carries it."""
    pip_len = len(pip_pcm) / RATE
    rows = []
    for i, cut in enumerate(cuts):
        clip, start, end = cut["clip"], float(cut["start"]), float(cut["end"])
        row = {"line": i, "clip": clip, "start": round(start, 4), "end": round(end, 4),
               "transcript": cut.get("transcript", ""), "covered": "none", "mic": "main"}
        offset = offsets.get(clip)
        if offset is not None and clip in main_pcm:
            cover = min(end + offset, pip_len) - max(start + offset, 0.0)
            if cover >= MIN_COVER_S:
                row["covered"] = "full" if cover >= (end - start) - 1e-3 else "partial"
                row["main_db"] = level_db(main_pcm[clip], start, end)
                row["pip_db"] = level_db(pip_pcm, start + offset, end + offset)
        rows.append(row)

    diffs = [r["pip_db"] - r["main_db"] for r in rows
             if r.get("main_db") is not None and r.get("pip_db") is not None and r["main_db"] > SILENT_DB]
    usual = float(np.median(diffs)) if diffs else 0.0
    for row, cut in zip(rows, cuts):
        if row.get("main_db") is not None and row.get("pip_db") is not None:
            row["hotter_db"] = round(row["pip_db"] - row["main_db"] - usual, 1)
            row["main_db"], row["pip_db"] = round(row["main_db"], 1), round(row["pip_db"], 1)
        if row["covered"] == "none":
            row["why"] = "the second camera does not cover this line"
            continue
        if "pip_audio" in cut:
            row["mic"] = "pip" if cut["pip_audio"] else "main"
            row["why"] = "set in the cut list"
        elif row["clip"] in pip_mic_clips:
            row["mic"], row["why"] = "pip", "the second camera's mic carries this whole clip (--pip-mic)"
        elif row.get("hotter_db") is not None and row["hotter_db"] >= hotter:
            row["mic"], row["why"] = "pip", f"the second camera is {row['hotter_db']:.0f} dB hotter than usual"
        mixed = _mixed(cut, offsets[row["clip"]], main_pcm[row["clip"]], pip_pcm, words_of(row["clip"]),
                       usual, hotter)
        if mixed:
            row["mixed"] = mixed
    return {"usual_db": round(usual, 1), "hotter_db": hotter, "lines": rows}


def _mixed(cut, offset, main, pip, words, usual, hotter):
    """Does the speaker change part-way through this line? Each word is heard on both mics, then runs of words are
    judged as a whole: a run counts only when it is at least two words or MIN_RUN_S long, and its whole stretch
    must still read as one speaker, so one loud word (a laugh, a bump) never splits a line."""
    start, end = float(cut["start"]), float(cut["end"])
    inside = [w for w in words if w.get("start") is not None and w.get("end") is not None
              and w["start"] >= start - 0.05 and w["end"] <= end + 0.05]

    def hot(a, b):
        mine, theirs = level_db(main, a, b), level_db(pip, a + offset, b + offset)
        if mine is None or theirs is None or mine <= SILENT_DB:
            return None
        return theirs - mine - usual

    def core(w):
        # A word's core: the transcript stretches a line's last word over whatever sound follows it, often the
        # other person already talking ("extra." read as theirs on its tail and as hers on its first 60%).
        return min(w["end"], w["start"] + max(0.15, 0.6 * (w["end"] - w["start"])))

    labels = []
    for i, w in enumerate(inside):
        h = hot(w["start"], core(w)) if w["end"] - w["start"] >= 0.1 else None
        if h is not None and h >= hotter:
            labels.append((i, "pip"))
        elif h is not None and h < hotter / 2:
            labels.append((i, "main"))
    runs = _runs(labels)
    while len(runs) > 1:                                 # fold the shortest too-small run into its neighbours
        small = [r for r in runs if len(r[1]) < 2 and core(inside[r[1][-1]]) - inside[r[1][0]]["start"] < MIN_RUN_S]
        if not small:
            break
        weakest = min(small, key=lambda r: core(inside[r[1][-1]]) - inside[r[1][0]]["start"])
        runs = _runs([(i, run[0]) for run in runs if run is not weakest for i in run[1]])
    if len(runs) < 2:
        return None
    for label, ids in runs:                              # each run, heard whole, must still be its speaker
        h = hot(inside[ids[0]]["start"], core(inside[ids[-1]]))
        if h is None or (label == "pip") != (h >= hotter):
            return None
    if len(runs) > 2:
        return {"switches": len(runs) - 1, "split_at": None,
                "why": "the speaker changes more than once in this line; split it by hand if it matters"}
    last = runs[0][1][-1]
    split = round((inside[last]["end"] + inside[last + 1]["start"]) / 2, 4)
    return {"switches": 1, "split_at": split, "first": runs[0][0], "second": runs[1][0],
            "first_words": " ".join(w["word"] for w in inside[:last + 1]),
            "second_words": " ".join(w["word"] for w in inside[last + 1:])}


def split_mixed(cuts, report):
    """The cut list with every one-switch mixed line split at its word gap: contiguous source, keep_edges, so the
    stitch leaves the seam exactly where the speaker changes."""
    out, split = [], 0
    by_line = {row["line"]: row for row in report["lines"]}
    for i, cut in enumerate(cuts):
        mixed = (by_line.get(i) or {}).get("mixed") or {}
        at = mixed.get("split_at")
        if at is None or not (float(cut["start"]) < at < float(cut["end"])):
            out.append(cut)
            continue
        base = {k: v for k, v in cut.items() if k not in ("_refine", "pip_audio")}
        out.append({**base, "end": at, "transcript": mixed["first_words"], "keep_edges": True})
        out.append({**base, "start": at, "transcript": mixed["second_words"], "keep_edges": True})
        split += 1
    return out, split


# ── the job ──────────────────────────────────────────────────────────────────────────────────────────────

def job_dir_of(job):
    path = Path(job).expanduser()
    if path.is_dir() and (path / "transcript").is_dir():
        return path.resolve()
    return REPO / "projects" / job


def second_camera(job_dir, given):
    """The second camera's file inside assets/pip/, copied there if it was somewhere else."""
    pip_dir = job_dir / "assets" / "pip"
    path = Path(given).expanduser()
    for candidate in (path, pip_dir / path.name, REPO / "inbox" / path.name):
        if candidate.is_file():
            return candidate.resolve(), pip_dir / candidate.name
    sys.exit(f"can't find the second camera's file: {given}")


def main_paths(job_dir, clips):
    """Each main clip's file: the transcript's own path when it still exists, else raw/<clip>."""
    words = {}
    words_file = job_dir / "transcript" / "words.json"
    if words_file.exists():
        for entry in json.loads(words_file.read_text(encoding="utf-8")).get("clips", []):
            words[entry["clip"]] = entry
    paths = {}
    for clip in clips:
        listed = Path((words.get(clip) or {}).get("path") or "")
        paths[clip] = listed if listed.name and listed.is_file() else job_dir / "raw" / clip
    return paths, words


def keep_history(cuts_file):
    hist = cuts_file.parent / "history"
    hist.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    kept = hist / f"cuts.{stamp}.json"
    if kept.exists():
        kept = hist / f"cuts.{stamp}.{os.getpid()}.json"
    shutil.copy2(cuts_file, kept)
    return kept


def print_report(report):
    print(f"\nwhose mic (second camera vs hers, relative to the usual {report['usual_db']:+.1f} dB):")
    for row in report["lines"]:
        hot = f"{row['hotter_db']:+5.1f} dB" if row.get("hotter_db") is not None else "   —    "
        who = {"pip": "SECOND CAMERA", "main": "hers"}[row["mic"]]
        cover = "" if row["covered"] == "full" else f"  [{row['covered']} cover]"
        print(f"  {row['line']:3d}  {hot}  {who:13s}  {row['transcript'][:52]}{cover}")
        mixed = row.get("mixed")
        if mixed and mixed.get("split_at") is not None:
            print(f"        ↳ changes speaker at {mixed['split_at']:.2f}s: \"{mixed['first_words']}\" | "
                  f"\"{mixed['second_words']}\"")
        elif mixed:
            print(f"        ↳ {mixed['why']}")


def main():
    ap = argparse.ArgumentParser(description="Sync a second camera to her footage by sound.")
    ap.add_argument("job")
    ap.add_argument("camera")
    ap.add_argument("--pip-mic", action="append", default=[])
    ap.add_argument("--hotter", type=float, default=HOTTER_DB)
    ap.add_argument("--split-mixed", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    job_dir = job_dir_of(args.job)
    cuts_file = job_dir / "transcript" / "cuts.json"
    if not cuts_file.exists():
        sys.exit(f"this job has no cut list yet ({cuts_file}). The rough cut comes first.")
    cut_list = json.loads(cuts_file.read_text(encoding="utf-8"))
    cuts = cut_list["segments"]
    source, home = second_camera(job_dir, args.camera)
    clips = list(dict.fromkeys(cut["clip"] for cut in cuts))
    unknown = [c for c in args.pip_mic if c not in clips]
    if unknown:
        sys.exit(f"--pip-mic names a clip the cut list does not use: {', '.join(unknown)}")
    paths, words = main_paths(job_dir, clips)

    print(f"listening to the second camera: {source.name}")
    ref = Reference(decode(source))
    pip_duration = len(ref.pcm) / RATE
    offsets, checks, main_pcm = {}, {}, {}
    for clip in clips:
        if not paths[clip].is_file():
            sys.exit(f"can't find the main clip {clip} (looked for {paths[clip]})")
        main_pcm[clip] = decode(paths[clip])
        offsets[clip], checks[clip] = sync_clip(main_pcm[clip], ref)
        check = checks[clip]
        if offsets[clip] is None:
            print(f"  {clip}: not in the second camera ({check['why']})")
        else:
            print(f"  {clip}: locked at {offsets[clip]:+.3f}s  ({check['chunks_agreeing']} of {check['chunks']} "
                  f"chunks agree within {check['spread_ms']:.0f} ms; whole-clip peak {check['whole_clip_ratio']}x)")
    if not any(v is not None for v in offsets.values()):
        sys.exit("none of her clips lines up with the second camera, so there is nothing to sync. Nothing written.")

    def words_of(clip):
        return (words.get(clip) or {}).get("words") or []

    report = mic_report(cuts, offsets, main_pcm, ref.pcm, words_of, args.hotter, set(args.pip_mic))
    split = 0
    if args.split_mixed:
        new_cuts, split = split_mixed(cuts, report)
        if split:
            cuts = new_cuts
            report = mic_report(cuts, offsets, main_pcm, ref.pcm, words_of, args.hotter, set(args.pip_mic))
    print_report(report)

    sync = {"pip": home.name, "pip_duration": round(pip_duration, 3),
            "method": "audio cross-correlation (GCC-PHAT, 8 kHz mono), checked in 10 s chunks along each clip, "
                      f"spread <= {LOCK_SPREAD_S * 1000:.0f} ms",
            "offsets": offsets, "checks": checks,
            "note": "offset = PIP time at main clip t=0, so pip_t = main_t + offset. null = no overlap found."}
    report["pip"] = home.name
    if args.dry_run:
        print("\n(dry run: nothing written)")
        return
    home.parent.mkdir(parents=True, exist_ok=True)
    if source != home.resolve():
        shutil.copy2(source, home)                      # a copy: her original stays where she put it
    (home.parent / "sync.json").write_text(json.dumps(sync, indent=2) + "\n", encoding="utf-8")
    (home.parent / "mic-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    print(f"\nwrote {home.parent / 'sync.json'} and mic-report.json")
    if split:
        kept = keep_history(cuts_file)
        cut_list["segments"] = cuts
        cuts_file.write_text(json.dumps(cut_list, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"split {split} mixed line(s) in the cut list (the previous list is kept at {kept}). "
              "Re-stitch the rough cut and build the draft as a new version before laying the PIP.")
    heard = sum(1 for row in report["lines"] if row["mic"] == "pip")
    print(f"next: uv run workflows/capcut-live.py pip \"<draft>\" {args.job}   "
          f"(the second camera's mic carries {heard} line(s))")


if __name__ == "__main__":
    main()
