#!/bin/bash

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

# After the buyer deletes unwanted *-FINAL.mp4 from clips-final/, this drops those rows from
# HOOK-MAP.tsv, cleans the orphaned raw clip + still, and rebuilds POST/ (renumbered 01..N)
# + POST-THESE.md from the survivors. Idempotent.
# USAGE:  reconcile.sh [WORKDIR]   (WORKDIR = the buyer's per-run folder; defaults to the current dir)
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKDIR="${1:-$PWD}"
cd "$WORKDIR" || { echo "reconcile: cannot cd to WORKDIR '$WORKDIR'" >&2; exit 1; }
[ -f HOOK-MAP.tsv ] || { echo "reconcile: no HOOK-MAP.tsv in '$WORKDIR'" >&2; exit 1; }
kept=0; dropped=0
{ head -1 HOOK-MAP.tsv; } > HOOK-MAP.new
# `|| [ -n "$clip" ]`: a HOOK-MAP whose last row has no trailing newline still keeps that row
while IFS=$'\t' read -r clip hook aside keyword pos || [ -n "$clip" ]; do
  [ "$clip" = "clip" ] && continue
  [ -z "$clip" ] && continue
  if [ -f "clips-final/${clip}-FINAL.mp4" ]; then
    printf '%s\t%s\t%s\t%s\t%s\n' "$clip" "$hook" "$aside" "$keyword" "$pos" >> HOOK-MAP.new
    kept=$((kept+1))
  else
    dropped=$((dropped+1))
    echo "dropped: $clip"
    rm -f "clips/${clip}.mp4" "stills/${clip}.png"    # tidy orphans (still recoverable from raw if needed)
  fi
done < HOOK-MAP.tsv
mv HOOK-MAP.new HOOK-MAP.tsv
# wipe + rebuild POST so numbering is contiguous
rm -f POST/*.mp4 POST/*.txt
python3 "$SKILL_DIR/build-posts.py" "$WORKDIR"
echo "---- kept $kept, dropped $dropped ; posting queue renumbered 01..$kept ----"
