#!/bin/bash
# /studio behind — render with an element (the hook) BEHIND the subject.
# Stacks: footage -> hook overlay -> subject cutout -> front overlay (captions/takeover/vibe).
# usage: studio_behind.sh <JOB> <PACK> <footage> <out.mp4> [duration]
set -e

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

JOB=$1; PACK=$2; FOOT=$3; OUT=$4; DUR=${5:-9}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OD="$ROOT/projects/$JOB/hf-reel-type-$(echo $PACK | tr 'A-Z' 'a-z')"
WORK="$ROOT/projects/$JOB/behind"; mkdir -p "$WORK"
# Each layer renders through product/reel_render.py, the engine's gated renderer: the composition is checked
# first, an isolated copy is rendered (a failed render can no longer delete the composition), and a failure
# says why instead of ending the script in silence. The hook sits BEHIND her on purpose, so its layer skips
# the subject check, which exists to stop exactly that overlap everywhere else. Each layer build also removes
# the other layer's elements on purpose, leaving their animations aiming at nothing, so the renderer is told
# that is deliberate (REEL_ALLOW_DEAD_TARGETS=1); every other check still runs.
render_layer () { # $1=LAYER  $2=out.mov  [more reel_render flags]
  local layer="$1" out="$2" log rc; shift 2
  JOB="$JOB" STYLE_PACK="$PACK" HOOK_SPLIT="${HOOK_SPLIT:-0}" LAYER="$layer" \
    python3 "$ROOT/product/build-reel-type.py" >/dev/null 2>&1 || {
      rc=$?
      echo "  ⛔ the $layer layer did not build (exit $rc). Run JOB=$JOB STYLE_PACK=$PACK LAYER=$layer python3 product/build-reel-type.py to see why."
      exit $rc
    }
  log="$WORK/$layer.render.log"
  set +e
  REEL_ALLOW_DEAD_TARGETS=1 python3 "$ROOT/product/reel_render.py" render "$OD" -o "$out" "$@" >"$log" 2>&1
  rc=$?
  set -e
  if [ $rc -ne 0 ]; then
    echo "  ⛔ the $layer layer did not render (exit $rc). The last of what it said:"
    tail -n 15 "$log" | sed 's/^/       /'
    echo "     All of it: $log"
    exit $rc
  fi
}
# 1) normalized 9:16 footage + subject matte (skip if cutout already present + fresh)
if [ ! -f "$WORK/fg.mp4" ] || [ "$FOOT" -nt "$WORK/fg.mp4" ]; then
  ffmpeg -y -i "$FOOT" -t "$DUR" -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1" -an "$WORK/fg.mp4" >/dev/null 2>&1
fi
if [ ! -f "$WORK/cutout.webm" ] || [ "$WORK/fg.mp4" -nt "$WORK/cutout.webm" ]; then
  # through product/bg_remove.py, the one way the engine runs remove-background: its folder made first, a stalled
  # run stopped whole and said plainly (never a hang), the cutout put in place only once it is whole
  python3 "$ROOT/product/bg_remove.py" "$WORK/fg.mp4" "$WORK/cutout.webm" >/dev/null || {
    echo "  ⛔ her cutout was not made (the reason is above), so the behind render stopped here."
    exit 1
  }
fi
# 2) render the two overlay layers
render_layer hook  "$WORK/hook.mov" --no-subject
render_layer front "$WORK/front.mov"
# 3) stack them with the cutout in the middle
ffmpeg -y -i "$WORK/fg.mp4" -i "$WORK/hook.mov" -c:v libvpx-vp9 -i "$WORK/cutout.webm" -i "$WORK/front.mov" -filter_complex \
"[0:v][1:v]overlay=0:0:format=auto[a];[a][2:v]overlay=0:0:format=auto[b];[b][3:v]overlay=0:0:format=auto,trim=0:${DUR},setpts=PTS-STARTPTS[v]" \
  -map "[v]" -an -t "$DUR" -c:v libx264 -pix_fmt yuv420p -crf 18 "$OUT" >/dev/null 2>&1
echo "behind render -> $OUT"
