#!/usr/bin/env bash
# Modified by Homewell LLC, 2026, for The Reels Editing Engine: this copy installs the caption helpers when
# missing and only says ready once safe-zones.json exists. Original: HyperFrames v0.8.158,
# skills/embedded-captions/scripts/prepare.sh.
# prepare.sh — one-command pre-processing for a captions project.
#
#   bash prepare.sh <project-dir>
#
# Runs the three deterministic pre-steps with maximum parallelism:
#   matte.cjs (CPU-heavy ONNX)  ∥  transcribe.cjs (whisper)   → then safe-zones.cjs
# (matte and transcribe are independent; safe-zones needs the matte's frames_fg.)
# Replaces hand-running steps 2 / 3 / 3b — one call, nothing forgotten, ~the cost
# of the slower of the two instead of their sum.
#
# After this completes the project has: frames_bg/ frames_fg/ matte.fps
# transcript.json safe-zones.json — everything the authoring step needs.
set -euo pipefail

PROJECT="${1:?usage: prepare.sh <project-dir>}"
PROJECT="$(cd "$PROJECT" && pwd)"
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The measuring helpers need Sharp, Puppeteer and GSAP in the caption project (TOOLKIT.md "Runtime
# prerequisites", same pinned versions). Installed here when missing, so a project can never get past this step
# without them: without Sharp, safe-zones used to print its complaint and the step still said "ready".
if [[ ! -d "$PROJECT/node_modules/sharp" || ! -d "$PROJECT/node_modules/puppeteer" || ! -d "$PROJECT/node_modules/gsap" ]]; then
  echo "[prepare] installing the caption helpers into the project (Sharp, Puppeteer, GSAP; once per project) …"
  npm install --prefix "$PROJECT" --save-dev --save-exact --no-audit --no-fund \
    sharp@0.35.3 puppeteer@25.8.0 gsap@3.15.0 > "$PROJECT/_prepare_npm.log" 2>&1 || {
    tail -8 "$PROJECT/_prepare_npm.log" >&2
    echo "[prepare] the caption helpers would not install (reason above; full log: $PROJECT/_prepare_npm.log)" >&2
    exit 1; }
fi

echo "[prepare] matte ∥ transcribe ∥ envelope …"
MLOG="$PROJECT/_prepare_matte.log"; TLOG="$PROJECT/_prepare_transcribe.log"; ELOG="$PROJECT/_prepare_envelope.log"
node "$SD/matte.cjs" "$PROJECT"      > "$MLOG" 2>&1 &  MPID=$!
node "$SD/transcribe.cjs" "$PROJECT" > "$TLOG" 2>&1 &  TPID=$!
node "$SD/audio-envelope.cjs" "$PROJECT" > "$ELOG" 2>&1 &  EPID=$!

MRC=0; TRC=0
wait "$MPID" || MRC=$?
wait "$TPID" || TRC=$?
wait "$EPID" || echo "[prepare] (envelope skipped — hero amplitude falls back to neutral)" >&2
# surface both logs (they contain the guards' warnings — near-silent audio, tail trim)
sed 's/^/  [matte] /'      "$MLOG" | tail -6
sed 's/^/  [transcribe] /' "$TLOG" | tail -12
if (( MRC != 0 )); then echo "[prepare] matte FAILED (rc=$MRC) — see $MLOG" >&2; exit "$MRC"; fi
if (( TRC != 0 )); then echo "[prepare] transcribe FAILED (rc=$TRC) — see $TLOG" >&2; exit "$TRC"; fi

echo "[prepare] safe-zones …"
rm -f "$PROJECT/safe-zones.json"   # an old one must never stand in for this run's
node "$SD/safe-zones.cjs" "$PROJECT"
if [[ ! -s "$PROJECT/safe-zones.json" ]]; then
  echo "[prepare] safe-zones did not write safe-zones.json (reason above), so the project is NOT ready" >&2
  exit 1
fi

echo "[prepare] ✅ ready: frames_fg/ transcript.json safe-zones.json — author next (see SKILL.md step 4)"
