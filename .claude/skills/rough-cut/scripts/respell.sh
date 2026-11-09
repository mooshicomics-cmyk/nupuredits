#!/usr/bin/env bash
# respell.sh: put a job's script back together with today's word fixes, without cutting or listening again.
#
#   bash .claude/skills/rough-cut/scripts/respell.sh projects/<job>
#
# Use it after adding a fix that should reach a reel already stitched (a name flag-words.py raised, a
# word in the shared table, the job's own word-fixes.json). Her script is outputs/<job>.transcript.json,
# and everything it holds can be rebuilt from two files the job keeps: transcript/words.json (what she
# said, with times on the raw clips) and transcript/cuts.json (which spans of those clips play). kept-words.py
# rebuilds it from them and lays every word fix in. Where a word plays and for how long stays the same.
#
# Exit 1 with one line on stderr when the job has never been transcribed or its cut cannot be found;
# otherwise whatever kept-words.py exits with.
set -euo pipefail

# The engine's shims sit in <engine>/scripts; walk up to them. The python3 shim picks the real interpreter on
# Windows (where the bare name opens the Microsoft Store) and changes nothing elsewhere; the path shim gives
# scratch_root, the folder the stitch works in.
_up="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
until [ "$_up" = "/" ]; do
  if [ -f "$_up/scripts/_python3-shim.sh" ]; then
    . "$_up/scripts/_python3-shim.sh"
    if [ -f "$_up/scripts/_path-shim.sh" ]; then . "$_up/scripts/_path-shim.sh"; fi
    break
  fi
  _up="$(dirname "$_up")"
done; unset _up

JOB_DIR="${1:?usage: respell.sh projects/<job>}"
JOB="$(basename "$JOB_DIR")"
HEARD="$JOB_DIR/transcript/words.json"
CUT="$JOB_DIR/transcript/cuts.json"
SCRIPT="$JOB_DIR/outputs/$JOB.transcript.json"
say() { printf '[respell] %s\n' "$*" >&2; }

if [ ! -f "$HEARD" ]; then
  say "$JOB has not been transcribed ($HEARD is missing), so it has no script yet. Run the rough cut first."
  exit 1
fi

# Older stitches left the cut only in the scratch folder, which the system empties when it likes. If this
# job's cut is still there, give the job its own copy first.
if [ ! -f "$CUT" ]; then
  WORKING="$(scratch_root)/$JOB/cuts.json"
  if [ ! -f "$WORKING" ]; then
    say "$JOB has no saved cut ($CUT) and none left in the scratch folder either. Stitch it once more (stitch-cut.sh keeps the cut in the job), then run this again."
    exit 1
  fi
  mkdir -p "$(dirname "$CUT")"
  cp "$WORKING" "$CUT"
  say "saved the cut from the scratch folder into the job: $WORKING → $CUT"
fi

python3 "$(cd "$(dirname "$0")" && pwd)/kept-words.py" "$HEARD" "$CUT" "$SCRIPT"
