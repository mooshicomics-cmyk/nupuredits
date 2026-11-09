#!/usr/bin/env bash
# Pre-encode a durable full-raw ProRes 422 master for a job, UPRIGHT + SDR, at projects/<job>/<job>.prores.mov.
# It only needs the raw, so it can run in the BACKGROUND at intake, in parallel with word-timings.sh.
#
#   bash workflows/capcut-export/prewarm-prores.sh <job> &     # parallel with:
#   bash .claude/skills/rough-cut/scripts/word-timings.sh projects/<job>
#
# Nothing in the engine reads this file any more: the per-reel generator that did was retired, the CapCut
# builders take the H.264/HEVC cut, and an OPAQUE ProRes is refused on a CapCut timeline
# (capcut_media.ensure_shippable). Keep it for hand work that wants an intermediate master.
set -e
JOB="$1"; [ -z "$JOB" ] && { echo "usage: prewarm-prores.sh <job>"; exit 1; }
# The engine folder is wherever this script lives, not a fixed path in one person's home folder.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; JOBDIR="$REPO/projects/$JOB"
OUT="$JOBDIR/$JOB.prores.mov"
[ -f "$OUT" ] && { echo "[prores] already encoded: $OUT"; exit 0; }
RAW=$(ls "$JOBDIR"/raw/*.{mov,MOV,mp4,MP4,m4v,M4V} 2>/dev/null | head -1)
[ -z "$RAW" ] && { echo "no raw in $JOBDIR/raw"; exit 1; }
echo "[prores] encoding $OUT (upright, SDR) from $(basename "$RAW")…"
ffmpeg -v warning -stats -i "$RAW" -map 0:v:0 -map 0:a:0 \
  -c:v prores_ks -profile:v 2 -pix_fmt yuv422p10le -c:a pcm_s16le "$OUT" -y
echo "[prores] done → $OUT"
