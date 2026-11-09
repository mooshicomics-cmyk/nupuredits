#!/usr/bin/env python3
"""
broll_prep.py — batch-slice long clips into short, grabbable b-roll pieces.

Point it at a folder of raw clips and it chops each one into consecutive
~N-second segments (default 8s, landing inside a 6-9s grab window), names them
cleanly, and drops them in one organized output folder ready to scrub through.

Method: stream-copy segmenting (no re-encode). It's instant and lossless.
iPhone/modern HEVC keyframes are frequent, so cuts land within ~1s of target
and every segment starts on a clean keyframe (no frozen first frame).

Rules that keep the output tidy:
  - A clip already <= --max seconds is copied whole as one grab (nothing to cut).
  - A clip shorter than --min seconds can't yield a real grab -> parked in
    _too-short/ (never dropped, just set aside and flagged).
  - Trailing slivers shorter than --min are discarded (junk tails, not grabs).
  - Remaining pieces are renumbered contiguously, zero-padded: <clip>-p01.mov ...

Usage:
    python product/broll_prep.py <input_dir> [options]

Options:
    -s, --seconds N   target segment length in seconds        (default 8)
        --min N       shortest piece to keep as a grab        (default 4)
        --max N       clips <= this are copied whole, not cut (default 9)
    -o, --out DIR     output folder            (default: <input_dir>/grabs)
        --folders     one subfolder per source clip (default: one flat folder)
        --dry-run     print the plan, write nothing

No creator/brand references live here — safe to ship.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}


def probe_duration(path: Path) -> float:
    """Seconds of the file, or 0.0 if unreadable."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def find_clips(input_dir: Path):
    return sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.name.startswith(".")
    )


def slice_clip(src: Path, target: int, work: Path):
    """Stream-copy-segment src into work/part_XXXX<ext>. Returns sorted parts."""
    work.mkdir(parents=True, exist_ok=True)
    pattern = str(work / f"part_%04d{src.suffix.lower()}")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src), "-c", "copy", "-map", "0",
         "-f", "segment", "-segment_time", str(target),
         "-reset_timestamps", "1", pattern],
        check=True,
    )
    return sorted(work.glob(f"part_*{src.suffix.lower()}"))


def main():
    ap = argparse.ArgumentParser(add_help=True, description="Batch-slice clips into short b-roll grabs.")
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("-s", "--seconds", type=int, default=8)
    ap.add_argument("--min", type=float, default=4.0, dest="min_keep")
    ap.add_argument("--max", type=float, default=9.0, dest="max_whole")
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--folders", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    in_dir = args.input_dir.expanduser().resolve()
    if not in_dir.is_dir():
        sys.exit(f"Not a folder: {in_dir}")

    out_dir = (args.out.expanduser().resolve() if args.out
               else in_dir / "grabs")
    clips = find_clips(in_dir)
    if not clips:
        sys.exit(f"No video files found in {in_dir}")

    print(f"Input : {in_dir}")
    print(f"Output: {out_dir}")
    print(f"Target: ~{args.seconds}s segments | keep >= {args.min_keep:g}s | copy whole <= {args.max_whole:g}s")
    print(f"Clips : {len(clips)}\n")

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    total_grabs = 0
    too_short = []

    for src in clips:
        stem = src.stem
        dur = probe_duration(src)
        dest = (out_dir / stem) if args.folders else out_dir

        # too short to be a grab -> park it, don't lose it
        if dur and dur < args.min_keep:
            too_short.append((src.name, dur))
            print(f"  {src.name:38s} {dur:6.1f}s  -> too short, parked in _too-short/")
            if not args.dry_run:
                park = out_dir / "_too-short"
                park.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, park / src.name)
            continue

        # already grabbable -> copy whole as one piece
        if dur <= args.max_whole:
            name = f"{stem}-p01{src.suffix.lower()}"
            print(f"  {src.name:38s} {dur:6.1f}s  -> 1 grab (already in range)")
            total_grabs += 1
            manifest.append((src.name, dur, 1))
            if not args.dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest / name)
            continue

        # long clip -> slice
        est = max(1, int(dur // args.seconds))
        if args.dry_run:
            print(f"  {src.name:38s} {dur:6.1f}s  -> ~{est} grabs")
            total_grabs += est
            manifest.append((src.name, dur, est))
            continue

        work = out_dir / f".work_{stem}"
        try:
            parts = slice_clip(src, args.seconds, work)
            kept = [p for p in parts if probe_duration(p) >= args.min_keep]
            width = max(2, len(str(len(kept))))
            dest.mkdir(parents=True, exist_ok=True)
            for i, part in enumerate(kept, 1):
                final = dest / f"{stem}-p{str(i).zfill(width)}{src.suffix.lower()}"
                shutil.move(str(part), final)
            dropped = len(parts) - len(kept)
            tail = f" ({dropped} sliver dropped)" if dropped else ""
            print(f"  {src.name:38s} {dur:6.1f}s  -> {len(kept)} grabs{tail}")
            total_grabs += len(kept)
            manifest.append((src.name, dur, len(kept)))
        finally:
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)

    # manifest
    if not args.dry_run:
        lines = ["B-ROLL GRABS — source -> pieces", "=" * 40, ""]
        for name, dur, n in manifest:
            lines.append(f"{name}  ({dur:.1f}s)  ->  {n} grab(s)")
        if too_short:
            lines += ["", "Too short to grab (parked in _too-short/):"]
            for name, dur in too_short:
                lines.append(f"  {name}  ({dur:.1f}s)")
        lines += ["", f"TOTAL: {total_grabs} grabs from {len(manifest)} clips"]
        (out_dir / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nDone. {total_grabs} grabs" + (f", {len(too_short)} parked" if too_short else "") +
          ("  (dry run — nothing written)" if args.dry_run else f"\n{out_dir}"))


if __name__ == "__main__":
    main()
