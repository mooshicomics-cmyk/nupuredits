#!/usr/bin/env bash
# lay-bed.sh: puts her music under a finished cut and writes a new file beside it (the skill names it
# outputs/<job>.bed.mp4).
#
#   lay-bed.sh <video> <music> <out> [--bed-db N] [--lift] [--fade-in SECONDS] [--transcript FILE]
#
# <video> and <out> are .mp4 files, <music> an .mp3, .wav or .m4a. What each setting does, and what happens
# when it is left out:
#   --bed-db N        the music's gain in dB, applied exactly as typed (MUSIC_BED_DB in the environment does
#                     the same; a value on the command line wins). Left out, bed-plan.py measures the cut and the
#                     track and sets the gain from product/audio_levels.py, the bed rule the rendered route
#                     uses, so the song's own loudness never changes where it lands under her.
#   --lift            raises the music in the pauses of her transcript and brings it back down before her next
#                     word (bed-plan.py writes the curve). Without it the gain never moves.
#   --fade-in S       a fade from silence over the first S seconds. Without it the music starts at full bed level.
#   --transcript FILE the transcript --lift reads; by default the one the rough cut left beside the video.
set -euo pipefail
export PYTHONUTF8=1
# The python3 shim: on Windows the name `python3` is a Microsoft Store decoy. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USAGE="usage: lay-bed.sh <video> <music> <out> [--bed-db N] [--lift] [--fade-in SECONDS]"

CUT="" TRACK="" DEST="" transcript=""
named_bed="" named_lift="" named_fade=""
while [ $# -gt 0 ]; do
  case "$1" in
    --bed-db|--fade-in|--transcript)
      [ $# -ge 2 ] || { echo "[lay-bed] $1 needs a value" >&2; exit 1; }
      case "$1" in --bed-db) named_bed="$2" ;; --fade-in) named_fade="$2" ;; *) transcript="$2" ;; esac
      shift 2; continue ;;
    --bed-db=*)  named_bed="${1#*=}" ;;
    --fade-in=*) named_fade="${1#*=}" ;;
    --lift)    named_lift="on" ;;
    --no-lift) named_lift="off" ;;
    --*) echo "[lay-bed] unknown setting '$1'. $USAGE" >&2; exit 1 ;;
    *)
      if   [ -z "$CUT" ];   then CUT="$1"
      elif [ -z "$TRACK" ]; then TRACK="$1"
      elif [ -z "$DEST" ];  then DEST="$1"
      else echo "[lay-bed] unexpected '$1': settings are named. $USAGE" >&2; exit 1; fi ;;
  esac
  shift
done
# A setting on the command line beats the environment.
BED_GAIN="${named_bed:-${MUSIC_BED_DB:-}}"
LIFT="${named_lift:-off}"
FADE_IN="${named_fade:-0}"
[ -n "$CUT" ]   || { echo "$USAGE" >&2; exit 1; }
[ -n "$TRACK" ] || { echo "[lay-bed] no music file given. $USAGE" >&2; exit 1; }
[ -n "$DEST" ]  || { echo "[lay-bed] no output file given. $USAGE" >&2; exit 1; }

# Only the sound is rebuilt; the picture is copied as it is. The bed is one gain on the track (and the lift's
# curve when asked for), the track looped to the cut's length, a closing fade so the song never stops
# mid-note, and the rough cut's own −1 dBFS limiter on the sum. Nothing after it follows the level over time,
# the same static rule as the rough cut's chain (CLAUDE.md: never loudnorm).

[ -f "$CUT" ]   || { echo "[lay-bed] cannot find the video: $CUT" >&2; exit 1; }
[ -f "$TRACK" ] || { echo "[lay-bed] cannot find the music: $TRACK" >&2; exit 1; }

TAIL=1.2   # seconds of fade at the end

# How the bed sits: its gain (measured unless she set one) and, with --lift, where it rises.
plan_args=("$CUT" "$TRACK")
[ -n "$BED_GAIN" ] && plan_args+=(--bed-db "$BED_GAIN")
[ "$LIFT" = "on" ] && plan_args+=(--lift)
[ -n "$transcript" ] && plan_args+=(--transcript "$transcript")
plan="$(python3 "$HERE/bed-plan.py" "${plan_args[@]}")"
read -r _ GAIN GAIN_HOW <<<"$(printf '%s\n' "$plan" | grep '^GAIN ')"
LIFT_EXPR="$(printf '%s\n' "$plan" | sed -n 's/^LIFT //p')"

duration_of() { ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"; }

# Where the closing fade starts, so that it ends exactly on the last frame (never before 0).
length="$(duration_of "$CUT")"
tail_at="$(awk -v len="$length" -v t="$TAIL" 'BEGIN { s = len - t; printf "%.3f", (s < 0 ? 0 : s) }')"

# The music's own chain, input 1: resampled, set to the bed level, faded in only when a fade was asked
# for, and faded out at the tail.
fading_in() { awk -v f="$FADE_IN" 'BEGIN { exit !(f > 0) }'; }
music_bed() {
  local chain="[1:a]aresample=48000,volume=${GAIN}dB"
  if [ "$LIFT_EXPR" != "-" ]; then chain="${chain},volume='${LIFT_EXPR}':eval=frame"; fi
  if fading_in; then chain="${chain},afade=t=in:st=0:d=${FADE_IN}"; fi
  printf '%s' "${chain},afade=t=out:st=${tail_at}:d=${TAIL}[bed]"
}

# The bed meets the voice (input 0): added together, then the rough cut's own limiter (stitch-cut.sh,
# limiter("0.89")): the same −1 dBFS ceiling, make-up gain off, and its look-ahead delay taken back out so
# the mix stays on the picture (left in, it lands 5 ms late). amix hears the voice first, so the voice's
# length decides the mix's length.
meet="[0:a][bed]amix=inputs=2:duration=first:normalize=0[blend]"
finish="alimiter=limit=0.89:level=false:latency=true"
if [ "$LIFT_EXPR" != "-" ]; then held="rising in her pauses"; else held="one steady level"; fi
graph="$(music_bed);${meet};[blend]${finish},asetpts=PTS-STARTPTS[mixed]"

# The music loops for as long as the video runs; -shortest ends the file with the picture. The sound is
# written the way every other engine pass writes it (stitch-cut.sh AUDIO_OUT, build-reel-mp4.py): AAC 256k,
# 48 kHz, stereo, the index up front.
sources=(-i "$CUT" -stream_loop -1 -i "$TRACK")
audio_out=(-c:a aac -b:a 256k -ar 48000 -ac 2)
ffmpeg -nostdin -hide_banner -loglevel error -y "${sources[@]}" \
  -filter_complex "$graph" -map 0:v -map "[mixed]" -map_chapters -1 -c:v copy "${audio_out[@]}" -movflags +faststart -shortest "$DEST"

if fading_in; then entry="fading in over ${FADE_IN}s"; else entry="in from the first frame"; fi
echo "[lay-bed] wrote $DEST: music bed at ${GAIN} dB (${GAIN_HOW}), ${held}, ${entry}" >&2
ffprobe -hide_banner -loglevel error -show_entries format=duration -of default=nw=1:nk=1 "$DEST" >&2
