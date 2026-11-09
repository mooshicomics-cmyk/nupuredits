#!/usr/bin/env bash
# word-timings.sh — her footage, heard once, as timed words.
#
# Every clip in the job is listened to and written down word by word, each word with the moment it starts and
# ends. That file is what the rough cut cuts on, what the captions are timed to and what graphics-plan reads,
# so a job is heard exactly once and every later step works from the page, never from the footage.
#
#   bash .claude/skills/rough-cut/scripts/word-timings.sh <job_dir>            # hands back the job's transcript if it has one
#   bash .claude/skills/rough-cut/scripts/word-timings.sh <job_dir> --force    # listens again (the footage changed)
#
# out:  <job_dir>/transcript/words.json                       the job's own copy, and the one line on stdout; the copy
#                                                             it replaces moves to transcript/history/
#       <job_dir>/transcript/.transcribe-diagnostics.json     what this machine did and how fast (the hardware report reads it)
#       <temp dir>/reels-editing-engine/<job>/words.json      the same words in the scratch folder, where the stitch looks
#                                                             when a job has no transcript/ of its own
#
# The file reads in the order a run happens:
#   this machine     which listener can run here, and what Windows / Git Bash needs first
#   the job          the clip folder, the transcript it may already have, the footage to hear
#   speech tools     the venv: found (older installs too), kept, rebuilt once for a GPU, or built
#   listening        WhisperX, or faster-whisper on an Intel Mac; the language is detected, never assumed
#   keeping it       the old transcript to history/, the new one saved, the diagnostics beside it
# and the run itself is the short list of calls at the bottom.

set -euo pipefail

# ════ This machine ═══════════════════════════════════════════════════════════════════════════════════════

# Every Python step prints ✓ / ⚠ / → status marks. Windows' legacy console codepage cannot encode them and
# the step dies with UnicodeEncodeError partway through; UTF-8 everywhere costs macOS nothing.
export PYTHONUTF8=1
# Git Bash names the kernel MINGW64_NT-… or MSYS_NT-…, Cygwin CYGWIN_NT-…; every Windows-only step keys off this.
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WINDOWS_SHELL=1 ;; *) WINDOWS_SHELL=0 ;; esac
# A Windows PC on an ARM chip (Snapdragon). The speech tools' native parts publish Windows wheels for x64 only
# (CTranslate2, torch at the pinned version), so a venv on an ARM Python can never install them: a buyer's first
# rough cut stopped on exactly that (2026-10-24). Windows 11 on ARM runs x64 programs itself, so the venv is built
# on uv's x64 Python 3.11 there and installs the same wheels every other Windows PC gets. An x64 Git Bash under
# that emulation reports AMD64 for itself, so the machine's own value is read from the registry when needed.
win_is_arm64() {
  [ "$WINDOWS_SHELL" = 1 ] || return 1
  case "${PROCESSOR_ARCHITEW6432:-} ${PROCESSOR_ARCHITECTURE:-}" in *ARM64*|*arm64*) return 0 ;; esac
  command -v reg >/dev/null 2>&1 || return 1
  MSYS2_ARG_CONV_EXCL='*' reg query 'HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' \
    /v PROCESSOR_ARCHITECTURE 2>/dev/null | grep -qi 'ARM64'
}
# The Python every uv venv here is built on: "3.11", or the x64 build of it on a Windows ARM PC.
UV_PY="3.11"
if win_is_arm64; then UV_PY="cpython-3.11-windows-x86_64-none"; fi
# The model download links files into its cache, and a link on Windows needs Developer Mode or admin rights
# (WinError 1314). Copies work for everyone.
[ "$WINDOWS_SHELL" = 1 ] && export HF_HUB_DISABLE_SYMLINKS=1
# CTranslate2 4.8.x crashes (segmentation fault, exit 139) loading ANY Whisper model on a Windows PC's processor:
# reproduced by a buyer on a 13th-gen Intel laptop with every model size and compute type, and forcing the CPU
# instruction set (CT2_FORCE_CPU_ISA=AVX2 / GENERIC) made no difference. 4.4.0 loads clean on the same machine;
# its pkg_resources import needs setuptools<81. Only a processor-only Windows PC gets the pin: 4.4.0 is built
# for cuDNN 8 and CUDA torch ships cuDNN 9, and Smart App Control keeps the pins measured for it (_win-sac.sh).
# 4.8.0's changelog turned on PACKED_GEMM by default for Intel MKL, the likely cause, and 4.7.2 is the last release
# before it. 4.7.2 lets whisperx 3.8.6 (the tested set) in, where 4.4.0 holds whisperx at 3.4.5, but it has not run
# on that laptop yet. So it is tried first and 4.4.0 stays the measured way back: when the newer set will not
# install, or WhisperX crashes or errors on its first load, this PC moves to 4.4.0 + whisperx 3.4.5 in the same run
# and a mark beside the venv sends every later build straight there (back_to_measured_set, below).
# CT2_WIN_CPU_MEASURED=1 picks the measured set: that mark, a working venv already on 4.4.0 (never rebuilt to
# try), or the faster-whisper venv, which loaded clean on 4.4.0 on that same machine.
# An NVIDIA PC is no exception (a buyer, 2026-10-22: GTX laptop, Windows 11, the tested set's 4.8.1): WhisperX
# crashed loading on the card, then faster-whisper crashed on the processor in the same venv, exit 139 both times,
# and the rough cut stopped. Its WhisperX venv gets 4.7.2 too, which is built for CUDA 12 and cuDNN 9 like the
# pinned torch (4.4.0 is not, so the measured set stays processor-only), and its faster-whisper venv, which only
# ever runs on the processor (transcribe-nofw.py), gets 4.4.0 like everyone else's.
CT2_WIN_CPU_PIN="ctranslate2==4.4.0 setuptools<81"
CT2_WIN_CPU_TRY="ctranslate2==4.7.2"   # no pkg_resources import any more, so setuptools is free
ct2_pin() {
  [ "$WINDOWS_SHELL" = 1 ] && [ -z "${SAC_PINS:-}" ] || return 0
  if [ "${NOFW:-0}" = 1 ]; then echo "$CT2_WIN_CPU_PIN"
  elif [ "${GPU_CUDA:-0}" -ne 0 ]; then echo "$CT2_WIN_CPU_TRY"
  elif [ "${CT2_WIN_CPU_MEASURED:-0}" = 1 ]; then echo "$CT2_WIN_CPU_PIN"
  else echo "$CT2_WIN_CPU_TRY"; fi
}
# The listener's versions, pinned. Unpinned, the resolver walked back to whichever whisperx fit the other pins
# and took the newest torch with it: a processor-only Windows PC got whisperx 3.4.5 with torch 2.14 and
# torchaudio 2.11 (a buyer report, 2026-10-13), and a CUDA PC, whose torch goes in first, went the same way.
# torchaudio 2.9+ has no AudioMetaData, so pyannote's voice detection cannot load, and newer torch refuses its
# checkpoint. torch 2.8.0 is the set measured working: whisperx 3.8.6 with pyannote 4 on a Mac, 3.7.9 with
# pyannote 3.4 under Smart App Control. Each Windows pin set gets the newest whisperx it allows: from 3.5 whisperx
# needs ctranslate2 4.5+, and from 3.8 pyannote 4, which needs matplotlib 3.10+.
TORCH_PIN="torch==2.8.0 torchaudio==2.8.0"
whisperx_pin() {
  if [ "$(ct2_pin)" = "$CT2_WIN_CPU_PIN" ]; then echo "whisperx==3.4.5"   # ctranslate2 4.4.0: the last below 4.5
  elif [ -n "${SAC_PINS:-}" ]; then echo "whisperx==3.7.9"     # matplotlib 3.9.2 keeps pyannote at 3.x
  else echo "whisperx==3.8.6"
  fi
}
# The rest of the listener, at the versions measured working together with whisperx 3.8.6 and torch 2.8 (an
# Apple-chip Mac, 2026-10-14). Left unpinned, a fresh install took whatever was newest that day: CTranslate2 4.8.3
# the day after its release. onnxruntime 1.27 and PyAV 18 publish wheels for Python 3.11 only, and on an Apple-chip
# Mac for macOS 14+ only, so anywhere else those two keep resolving on their own. The processor-only Windows set
# and the Smart App Control set carry their own measured pins (ct2_pin, _win-sac.sh). If this set will not
# install, fallback_note's retry drops it.
TESTED_SET="ctranslate2==4.8.1 pyannote.audio==4.0.7 torchcodec==0.7.0"
TESTED_SET_311="onnxruntime==1.27.0 av==18.0.0"
tested_pins() {   # $1 = the venv's python
  [ "$(whisperx_pin)" = "whisperx==3.8.6" ] || return 0
  # A processor-only Windows PC on whisperx 3.8.6 carries its own CTranslate2 (ct2_pin): the set's 4.8.1 is the
  # release line that crashes there. The rest resolves to the same pyannote and torchcodec on torch 2.8.
  if [ "$WINDOWS_SHELL" = 1 ] && [ "${GPU_CUDA:-0}" -eq 0 ] && [ -z "${SAC_PINS:-}" ]; then return 0; fi
  # An NVIDIA PC keeps the rest of the set and takes its CTranslate2 from ct2_pin too (4.7.2, never 4.8).
  local set="" w
  for w in $TESTED_SET; do
    case "$w" in ctranslate2==*) [ "$WINDOWS_SHELL" = 1 ] && [ -z "${SAC_PINS:-}" ] && continue ;; esac
    set="${set:+$set }$w"
  done
  local wide=1
  "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)' >/dev/null 2>&1 || wide=0
  if [ "$(uname -s 2>/dev/null)" = Darwin ]; then
    [ "$(uname -m 2>/dev/null)" = arm64 ] || return 0   # an Intel Mac never installs whisperx
    local major; major="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
    [ "${major:-0}" -ge 14 ] 2>/dev/null || wide=0
  fi
  if [ "$wide" = 1 ]; then echo "$set $TESTED_SET_311"; else echo "$set"; fi
}
# The tested set could not resolve on this machine: the nearest set that keeps torch on 2.8, which is what keeps
# voice detection loading. Never the unpinned install that drifted.
fallback_note() {
  echo "[word-timings] the tested versions would not install on this computer; installing the nearest set on the" >&2
  echo "[word-timings] same torch instead" >&2
}

# The engine folder: where the python3 / PATH shims live (venv_py, venv_home, scratch_root come from them),
# along with the Mac chip check and the Windows Smart App Control helpers.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_ROOT=""
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; ENGINE_ROOT="$_d"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

# Which listener this machine gets.
#   whisperx         Apple Silicon, Windows, Linux: large-v3 for the words, then a wav2vec2 pass that pins
#                    where each word starts and ends.
#   faster-whisper   an Intel Mac. WhisperX needs torch~=2.8 and torch's last macOS x86_64 wheel is 2.2.2, so
#                    there it cannot install at all. faster-whisper runs on CTranslate2, which still ships
#                    Intel-Mac wheels, and gives its own word times (verify-cut.py already trusts them). Same
#                    words.json, same diagnostics, ~175 MB instead of ~3 GB. The cost: no wav2vec2 pass, so word
#                    edges come from Whisper's cross-attention and sit a little tighter together.
# REELS_ENGINE_FORCE_NOFW=1 takes the Intel route on any machine, for testing it.
choose_listener() {
  NOFW=0
  if [ -n "$ENGINE_ROOT" ] && [ -f "$ENGINE_ROOT/scripts/_mac-arch.sh" ]; then
    . "$ENGINE_ROOT/scripts/_mac-arch.sh"
    if [ "$(mac_arch_class)" = intel ]; then NOFW=1; fi
  fi
  if [ "${REELS_ENGINE_FORCE_NOFW:-}" = 1 ]; then NOFW=1; fi
  # Say the real cause here: without it, the run would fail later on "/scripts/transcribe-nofw.py: not found".
  if [ "$NOFW" = 1 ] && { [ -z "$ENGINE_ROOT" ] || [ ! -f "$ENGINE_ROOT/scripts/transcribe-nofw.py" ]; }; then
    echo "[word-timings] cannot find scripts/transcribe-nofw.py — the engine folder could not be located." >&2
    echo "[word-timings] Run this from inside the engine, or unset REELS_ENGINE_FORCE_NOFW." >&2
    exit 1
  fi
}

# An NVIDIA card. Decides which torch gets installed and which device the listener asks for. nvidia-smi only
# exists where NVIDIA's driver does (Windows, Linux); a Mac never has it.
detect_nvidia() {
  GPU_CUDA=0
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then GPU_CUDA=1; fi
}

# Homebrew's ffmpeg@7, when it is there, is the one the audio decoder links against.
prefer_brew_ffmpeg7() {
  local prefix
  for prefix in /opt/homebrew /usr/local; do   # Apple-chip and Intel Homebrew
    if [ -d "$prefix/opt/ffmpeg@7" ]; then
      export DYLD_LIBRARY_PATH="$prefix/opt/ffmpeg@7/lib:${DYLD_LIBRARY_PATH:-}"
      export PATH="$prefix/opt/ffmpeg@7/bin:$PATH"
      break
    fi
  done
}

# ════ The job ════════════════════════════════════════════════════════════════════════════════════════════

open_job() {
  # Absolute from here on, so nothing below depends on where the caller stood.
  JOB_DIR="$(cd "${1:?usage: word-timings.sh <job_dir> [--force]}" && pwd)"
  JOB_NAME="${JOB_DIR##*/}"
  # Intake copies footage into raw/; a job from before that keeps its clips at the top of the folder.
  if [ -d "$JOB_DIR/raw" ]; then MEDIA_DIR="$JOB_DIR/raw"; else MEDIA_DIR="$JOB_DIR"; fi
  WORK="$(scratch_root)/$JOB_NAME"
  SCRATCH_WORDS="$WORK/words.json"            # the listener writes here first; kept as the scratch copy
  TRANSCRIPT_DIR="$JOB_DIR/transcript"
  CANON="$TRANSCRIPT_DIR/words.json"          # the job's own copy, kept with the job
  mkdir -p "$WORK" "$TRANSCRIPT_DIR"
  shift
  FORCE=0
  local flag
  for flag in "$@"; do
    case "$flag" in
      --force) FORCE=1 ;;
      *) echo "unknown flag: $flag" >&2; exit 1 ;;
    esac
  done
}

# A clip whose sound starts after its picture (an iPhone clip copied out of Photos: 0.703 s) would be heard on the
# sound's own clock and cut on the file's, so every cut landed that much early. Intake lines it up (product/av_sync.py);
# this covers a job that reached the listener without it. Only before a fresh listen, so the new words are written on
# the lined-up clock. Best-effort: a clip it cannot line up is said, logged, and heard as it is.
line_up_sound() {
  [ -f "$ENGINE_ROOT/product/av_sync.py" ] || return 0
  python3 "$ENGINE_ROOT/product/av_sync.py" "$JOB_DIR" --apply --relisten >&2 || true
}

# The same clip in a job heard BEFORE intake lined such clips up (engine 2.3.6 and earlier): handing its transcript
# back as it is kept her reel choppy after the update, every cut early by the lead (a buyer, 2026-10-22). Listening
# again would lose her hand fixes and the cut she made on her words, so av_sync.py lines the clip up and moves that
# clip's stored word and cut times by its lead instead, once (the old copies go to history/ first). Last of the
# repairs, so the transcript id it records for her visual editor page is the one handed back. Best-effort.
catch_up_sound() {
  [ -f "$ENGINE_ROOT/product/av_sync.py" ] || return 0
  python3 "$ENGINE_ROOT/product/av_sync.py" "$JOB_DIR" --apply --quiet >&2 || true
}

# Whisper hears the same audio the same way every time, and large-v3 is slow, so a job that has been heard
# gets its transcript back instead. That is also what keeps the cut and the captions on ONE transcript.
hand_back_if_heard() {
  if [ "$FORCE" = 0 ] && [ -f "$CANON" ]; then
    repair_older_intel_transcript
    hear_quiet_first_line "$CANON" keep
    place_stranded_words "$CANON" keep
    catch_up_sound
    echo "[word-timings] this footage was heard before: handing back $CANON (--force hears it again)" >&2
    cp "$CANON" "$SCRATCH_WORDS"
    echo "$CANON"
    exit 0
  fi
}

# Every route, once per clip: a short word the listener barely heard ("and", "a") can come back squeezed onto the end
# of the word before it while she really says it after the pause, so its line, its caption and the next piece's
# start all come out wrong. scripts/restamp_words.py strays moves each one onto its real voice, only when the
# sound agrees. $1 = the transcript to fix in place; "keep" = it is the durable copy, so the old one goes to
# history/ first. Best-effort: never stops a run.
place_stranded_words() {
  local src="$1" out="$WORK/words.strays.json" rc=0
  [ -f "$src" ] && [ -f "$ENGINE_ROOT/scripts/restamp_words.py" ] || return 0
  python3 "$ENGINE_ROOT/scripts/restamp_words.py" strays "$src" "$MEDIA_DIR" "$out" || rc=$?
  if [ "$rc" = 0 ] && [ -s "$out" ]; then
    [ "${2:-}" = keep ] && keep_previous_transcript
    mv "$out" "$src" 2>/dev/null || true
  fi
  rm -f "$out" 2>/dev/null
  return 0
}

# Every route, once per clip: the listener's voice detector can skip a short, quiet first line that a long silence
# follows, so the transcript starts at her second line and the cut never sees the first (ISS-99). When a clip's
# first word starts over a second in and the lead-in holds voice, scripts/quiet_first_line.py hears just that
# stretch again with the detector off (faster-whisper, in both venvs) and keeps only words over the voice it
# measured. Nothing heard, nothing changes. Runs in the speech tools' own Python; on a heard job that has not been
# set up yet (no venv here) it simply does not run. $1 = the transcript to fix in place; "keep" = it is the durable
# copy, so the old one goes to history/ first. Best-effort: never stops a run.
hear_quiet_first_line() {
  local src="$1" out="$WORK/words.firstline.json" rc=0 py="${PYBIN:-}"
  [ -f "$src" ] && [ -n "$ENGINE_ROOT" ] && [ -f "$ENGINE_ROOT/scripts/quiet_first_line.py" ] || return 0
  if [ -z "$py" ]; then pick_venv; py="$(venv_py "$VENV")"; fi
  [ -x "$py" ] || return 0
  "$py" "$ENGINE_ROOT/scripts/quiet_first_line.py" "$src" "$MEDIA_DIR" "$out" \
    2> >(grep --line-buffered -vE 'Intel MKL WARNING|Intel\(R\) Streaming SIMD|oneAPI Math Kernel' >&2) || rc=$?
  if [ "$rc" = 0 ] && [ -s "$out" ]; then
    [ "${2:-}" = keep ] && keep_previous_transcript
    mv "$out" "$src" 2>/dev/null || true
  fi
  rm -f "$out" 2>/dev/null
  return 0
}

# An Intel-route transcript from before scripts/restamp_words.py has every pause folded into the word after it, and
# handing it back as it is would keep its cuts opening on dead air for good. Re-stamped from the footage once (a
# few seconds, no listening again), with the old copy kept in history/ first. Anything else is handed back untouched:
# a transcript already re-stamped, an aligned one, or one whose footage has moved. Best-effort: never stops a run.
repair_older_intel_transcript() {
  [ "$NOFW" = 1 ] || return 0
  local out="$WORK/words.restamped.json" rc=0
  python3 "$ENGINE_ROOT/scripts/restamp_words.py" repair "$CANON" "$MEDIA_DIR" "$out" || rc=$?
  if [ "$rc" = 0 ] && [ -s "$out" ]; then
    keep_previous_transcript
    mv "$out" "$CANON" 2>/dev/null || true
  fi
  rm -f "$out" 2>/dev/null
  return 0
}

# Every .mov, .mp4, .mkv and .m4v at the top of the clip folder, in any case (phones write IMG_0001.MOV), in
# that order. nullglob keeps an extension with no files from adding its own pattern.
gather_footage() {
  shopt -s nullglob
  CLIPS=("$MEDIA_DIR"/*.[Mm][Oo][Vv] "$MEDIA_DIR"/*.[Mm][Pp]4 "$MEDIA_DIR"/*.[Mm][Kk][Vv] "$MEDIA_DIR"/*.[Mm]4[Vv])
  [ "${#CLIPS[@]}" -gt 0 ] || { echo "no footage in $MEDIA_DIR" >&2; exit 1; }
}

# ════ The speech tools ═══════════════════════════════════════════════════════════════════════════════════
#
# A venv of their own, built on the first transcription and used by every one after it. WhisperX brings
# several GB of torch; nothing else goes in there. The faster-whisper venv is a separate folder on purpose: a
# machine that switches routes (a test on an Apple-chip Mac, a buyer who changes computers) must never end up
# with one venv half-filled with the other's packages. venv_home finds a venv an older install built under an
# earlier cache folder, so a 3-5 GB build is never downloaded twice.
#
# A finished build carries .speech-tools-ready, written as the very last step, holding what it was VERIFIED
# for: "cuda" or "cpu". Verified, not attempted: a GPU torch install can exit 0 and leave CPU torch in place
# (uv's cache already held a matching CPU wheel), and everything downstream would believe in a GPU it lacks.
# A build cut off partway has no record, so the next run starts it again from an empty folder.
#
# .deps-ok is the older name, still accepted: a venv carrying only that one is a finished build and is kept
# as it is. It is still written beside the new record: an engine rolled back to an older version knows only
# that name, and without it would rebuild the whole 3-5 GB install.
READY_NAME=".speech-tools-ready"
OLD_READY_NAME=".deps-ok"

pick_venv() {
  VENV="${REELS_ENGINE_WHISPERX_VENV:-$(venv_home whisperx-venv)}"
  # A computer where WhisperX would not install or run moved to faster-whisper for good (pivot_to_faster_whisper).
  if [ "$NOFW" != 1 ] && [ -e "$VENV$PIVOT_SUFFIX" ] && [ -n "$ENGINE_ROOT" ] \
     && [ -f "$ENGINE_ROOT/scripts/transcribe-nofw.py" ]; then
    NOFW=1
    export REELS_ENGINE_NOFW_REASON="${REELS_ENGINE_NOFW_REASON:-WhisperX did not work on this computer before}"
  fi
  if [ "$NOFW" = 1 ]; then VENV="${REELS_ENGINE_NOFW_VENV:-$(venv_home fasterwhisper-venv)}"; fi
}

# The record this venv carries, the engine's own name first. Prints nothing when it has neither.
ready_record() {
  if [ -e "$VENV/$READY_NAME" ]; then echo "$VENV/$READY_NAME"
  elif [ -e "$VENV/$OLD_READY_NAME" ]; then echo "$VENV/$OLD_READY_NAME"
  fi
}
# True when the record is there AND says something: a blank record means "unknown", never "finished".
has_verified_record() { local r; r="$(ready_record)"; [ -n "$r" ] && [ -s "$r" ]; }
mark_ready() {   # $1 = cuda | cpu
  echo "$1" > "$VENV/$READY_NAME"
  echo "$1" > "$VENV/$OLD_READY_NAME"
}

# A venv with no record can still be a perfectly good install: setup built it, or a version that wrote no
# record. Ask the venv before anything is deleted. A PC tester once lost 17 minutes to deleting one, and then
# the rebuild itself failed on that machine, leaving her with nothing.
keep_working_venv() {
  if has_verified_record || [ ! -d "$VENV" ]; then return 0; fi
  local py mod mode
  py="$(venv_py "$VENV")"
  mod=whisperx; if [ "$NOFW" = 1 ]; then mod=faster_whisper; fi   # either listener counts as working
  if [ -n "$py" ] && "$py" -c "import $mod" >/dev/null 2>&1; then
    mode=cpu
    if "$py" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >/dev/null 2>&1; then mode=cuda; fi
    mark_ready "$mode"
    echo "[word-timings] the speech tools were already installed here ($mode) — keeping them, no rebuild" >&2
  fi
}

# An NVIDIA card next to a venv verified for the processor only (an older version built it that way) would
# stay on the CPU for good. Rebuild it once. The sibling marker outlives the rebuild, so a card whose driver
# is too old (CUDA verifies false again) can never set off a rebuild on every run.
rebuild_once_for_gpu() {
  local r
  r="$(ready_record)"
  if [ "$NOFW" != 1 ] && [ "$GPU_CUDA" -eq 1 ] && [ -n "$r" ] && [ "$(cat "$r" 2>/dev/null)" != "cuda" ] \
     && [ ! -e "$VENV.cuda-rebuild-tried" ]; then
    echo "[word-timings] an NVIDIA GPU is here, but the speech tools on this machine were set up for the processor" >&2
    echo "[word-timings] only (an earlier version did that). Rebuilding them once for the GPU: ~3 GB, a few minutes," >&2
    echo "[word-timings] and every rough cut after this is much faster." >&2
    : > "$VENV.cuda-rebuild-tried"
    rm -rf "$VENV"
  fi
}

# The biggest download the engine ever makes (~3 GB now, ~3 GB of model files on the first reel). Say so
# before it starts, so a nearly full disk hears it here and not as "no space left" halfway through.
# The faster-whisper route (an Intel Mac, or a computer moved to it) is a fraction of that and brings no torch:
# about 300 MB on disk (measured on an Intel Mac, 2026-10-12: a 289 MB venv) and the small model (~0.5 GB).
# It used to be quoted the WhisperX numbers, ~6 GB it never downloads (a buyer's report, 2026-10-13).
announce_download() {
  local free_gb now models need
  if [ "$NOFW" = 1 ]; then now="~300 MB"; models="~0.5 GB of speech model"; need=2
  else now="~3 GB"; models="~3 GB of model files"; need=8; fi
  free_gb="$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2{printf "%d", $4/1048576}' || true)"
  if [ -n "$free_gb" ]; then
    echo "[word-timings]    one-time download: $now now (+ $models on the first reel). Free space: ${free_gb} GB" >&2
    if [ "$free_gb" -lt "$need" ]; then
      echo "[word-timings]    ⚠ under $need GB free — clear some space first, or this install can fail partway" >&2
    fi
  fi
}

# Windows with Smart App Control on blocks uv's unsigned Python download and some of the newest native wheels.
# There the venv is built from the signed python.org 3.11, uv is told never to fetch its own, and the versions
# measured to load are pinned (scripts/_win-sac.sh). Decided before the venv exists, so it never reaches the
# repair below, which cannot undo a block and only reproduced it on a tester's PC.
use_signed_python_if_blocked() {
  SAC_PY=""; SAC_PINS=""
  if [ "$WINDOWS_SHELL" = 1 ] && [ -n "$ENGINE_ROOT" ] && [ -f "$ENGINE_ROOT/scripts/_win-sac.sh" ]; then
    . "$ENGINE_ROOT/scripts/_win-sac.sh"
    if [ "$(win_sac_state)" = on ]; then
      echo "[word-timings] Smart App Control is on here, which blocks some downloaded files. Using the signed" >&2
      echo "[word-timings] Python from python.org and versions it allows (installing that Python once if needed)." >&2
      SAC_PY="$(win_get_signed_python311 || true)"
      if [ -n "$SAC_PY" ]; then
        SAC_PINS="$WIN_SAC_PINS"
        export UV_PYTHON_PREFERENCE=only-system UV_PYTHON_DOWNLOADS=never
      else
        echo "[word-timings] ⚠ could not install the signed Python 3.11 automatically. Run this once in Git Bash," >&2
        echo "[word-timings]   then try again:  winget install --id Python.Python.3.11 -e --scope user" >&2
        exit 1
      fi
    fi
  fi
}

# ── When this computer has no uv ──
#
# uv builds the venv and installs into it. Setup puts it on every machine, but not every machine kept it (a
# buyer who skipped a step, a PATH that lost it, a new computer), and with no uv the build died on "uv: command
# not found", the faster-whisper pivot with it, since that rebuilds with the same uv. So uv is fetched first,
# into ~/.local/bin the way scripts/ensure-python.sh does it (no password, no admin). When it cannot be had, or
# `uv venv` itself will not build here, the venv is made with Python's own `-m venv` and filled with its own
# pip: slower, same packages, same pins. A mark beside the WhisperX venv sends every later build straight to
# that route instead of failing first. Deleting the mark puts uv back in charge.
NO_UV=0
UV_CHECKED=0
REMEMBER_NO_UV=""   # why this run left uv, kept beside the venv once the plain venv exists

no_uv_mark() { printf '%s.no-uv' "${REELS_ENGINE_WHISPERX_VENV:-$(venv_home whisperx-venv)}"; }
# A real uv on PATH. `type -P` looks only at files, never at the stand-in function use_pip_route defines.
uv_on_path() { type -P uv >/dev/null 2>&1 || type -P uv.exe >/dev/null 2>&1; }

# On the plain route every `uv pip install --python <venv python> ...` below goes to that venv's own pip with
# the same arguments: the pins, --extra-index-url and --only-binary all mean the same thing to pip. Nothing
# else of uv's is called on this route (make_venv takes the plain branch before its `uv venv` / `uv python`).
use_pip_route() {
  NO_UV=1
  uv() { uv_by_pip "$@"; }
}
uv_by_pip() {
  [ "${1:-}" = pip ] && [ "${2:-}" = install ] || return 0   # `uv python ...`: no private Python on this route
  shift 2
  local py="" rest=()
  while [ $# -gt 0 ]; do
    if [ "$1" = --python ]; then py="${2:-}"; shift 2 || shift; else rest+=("$1"); shift; fi
  done
  [ -n "$py" ] || return 1
  # A venv uv made has no pip of its own; Python's own ensurepip adds it.
  "$py" -m pip --version >/dev/null 2>&1 || "$py" -m ensurepip --upgrade >&2 || return 1
  "$py" -m pip install --disable-pip-version-check ${rest[@]+"${rest[@]}"}
}

# Asked only when something is about to be built or installed: a run whose speech tools are ready never
# reaches for uv, so it never downloads it either.
ensure_uv() {
  [ "$UV_CHECKED" = 1 ] && return 0
  UV_CHECKED=1
  if [ -e "$(no_uv_mark)" ]; then use_pip_route; return 0; fi
  uv_on_path && return 0
  local bin="${UV_INSTALL_DIR:-$HOME/.local/bin}"
  if [ -x "$bin/uv" ] || [ -x "$bin/uv.exe" ]; then PATH="$bin:$PATH"; export PATH; return 0; fi
  echo "[word-timings] the helper the speech tools are built with (uv) is not on this computer. Fetching it into" >&2
  echo "[word-timings] your home folder first: no password, about a minute." >&2
  if [ "$WINDOWS_SHELL" = 1 ]; then
    powershell -NoProfile -ExecutionPolicy ByPass -Command \
      "irm https://astral.sh/uv/install.ps1 -TimeoutSec 600 | iex" >&2 || true
  else
    curl -LsSf -m 600 https://astral.sh/uv/install.sh | sh >&2 || true
  fi
  if [ -x "$bin/uv" ] || [ -x "$bin/uv.exe" ]; then PATH="$bin:$PATH"; export PATH; fi
  if uv_on_path; then
    note_fallback "uv was not on this computer; installed it to ~/.local/bin and built the speech tools with it"
    return 0
  fi
  note_fallback "uv was not on this computer and would not install; built the speech tools with Python's own venv and pip"
  echo "[word-timings] uv would not install here, so the speech tools are built with Python's own tools instead." >&2
  echo "[word-timings] A little slower, same versions, and every build after this goes straight there." >&2
  use_pip_route
  REMEMBER_NO_UV="uv would not install"
}

# The Python a plain venv is made from: the signed one under Smart App Control (the only kind it lets run),
# otherwise the newest the speech tools' pins install on, by name, then the python3 the shims found.
plain_venv_python() {
  if [ -n "$SAC_PY" ]; then echo "$SAC_PY"; return 0; fi
  local c
  for c in python3.11 python3.12 python3.10 python3; do
    # Never Apple's placeholder: running it opens the "install the developer tools?" dialog (_python3-shim.sh).
    if [ "$c" = python3 ] && [ "${_P3_OK:-1}" != 1 ]; then continue; fi
    type "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys, venv, ensurepip; sys.exit(0 if (3, 9) <= sys.version_info[:2] <= (3, 13) else 1)' \
         >/dev/null 2>&1; then
      echo "$c"; return 0
    fi
  done
  return 1
}

plain_venv() {   # $1 = why uv's own venv was not used (empty when it was never tried)
  local base
  base="$(plain_venv_python)" || base=""
  if [ -z "$base" ]; then
    echo "[word-timings] no Python on this computer can build the speech tools' venv (3.9 to 3.13 is needed)." >&2
    return 1
  fi
  rm -rf "$VENV"
  echo "[word-timings] building the speech tools with Python's own venv and pip ($base)" >&2
  if ! "$base" -m venv "$VENV" >&2 || [ ! -x "$(venv_py "$VENV")" ]; then rm -rf "$VENV"; return 1; fi
  use_pip_route
  # The pip a new venv starts with can be years old and resolve torch's pins badly; a current one is cheap.
  "$(venv_py "$VENV")" -m pip install --disable-pip-version-check --upgrade pip >&2 || true
  if [ -n "${1:-}" ]; then
    note_fallback "$1; built the speech tools with Python's own venv and pip"
    REMEMBER_NO_UV="$1"
  fi
  printf '%s\n' "${REMEMBER_NO_UV:-uv did not work on this computer}" > "$(no_uv_mark)" 2>/dev/null || true
}

make_venv() {
  # Always into an empty folder: whatever a cut-off build left there is never built on top of.
  rm -rf "$VENV"
  ensure_uv
  if [ "$NO_UV" = 1 ]; then plain_venv ""; return; fi
  # Windows, ordinary case: fetch uv's Python 3.11 as its own step first. Folded into `uv venv`, the download
  # can still be finishing while the venv is made, and the venv comes out broken (seen on real PCs). The step
  # costs nothing when the Python is already there, and what it prints is filed away in the scratch folder:
  # even a healthy run can print a line that looks alarming and means nothing.
  if [ "$WINDOWS_SHELL" = 1 ] && [ -z "$SAC_PY" ]; then
    uv python install "$UV_PY" >"$WORK/uv-python-install.log" 2>&1 || true
  fi
  if [ -n "$SAC_PY" ]; then
    # The signed interpreter. When uv cannot make a venv from it, the interpreter makes its own: still the
    # signed Python, so Smart App Control is just as content.
    if ! uv venv "$VENV" --python "$SAC_PY" >&2; then
      echo "[word-timings] uv could not build from the signed Python; building with that Python's own venv" >&2
      plain_venv "uv venv would not build from the signed Python" || return 1
    fi
  elif ! uv venv "$VENV" --python "$UV_PY" 2>"$WORK/uv-venv.err"; then
    cat "$WORK/uv-venv.err" >&2
    # "Missing expected target directory for Python minor version link" means an earlier interrupted run left
    # uv's OWN Python half-downloaded, under uv's folder rather than in the venv, so every retry fails the
    # same way. A tester scrapped a whole job over it. That Python is uv's private copy and nothing else uses
    # it, so it is replaced.
    if grep -qi "Missing expected target directory for Python minor version" "$WORK/uv-venv.err" 2>/dev/null; then
      echo "[word-timings] the private Python this step downloads was left half-finished by an earlier run." >&2
      echo "[word-timings] Replacing just that piece and carrying on — your footage and the rest of the job are" >&2
      echo "[word-timings] untouched, and this takes about a minute." >&2
      uv python uninstall "$UV_PY" >"$WORK/uv-python-repair.log" 2>&1 || true
      uv python install   "$UV_PY" >>"$WORK/uv-python-repair.log" 2>&1 || true
    else
      echo "[word-timings] the venv did not build; clearing it and trying once more" >&2
    fi
    rm -rf "$VENV"
    # Second and last try with uv. If this fails too, Python's own venv builds it instead.
    if ! uv venv "$VENV" --python "$UV_PY" >&2; then
      plain_venv "uv venv failed twice" || { rm -f "$WORK/uv-venv.err"; return 1; }
    fi
  fi
  rm -f "$WORK/uv-venv.err"
}

# The highest PyTorch CUDA wheel channel the driver can run, read from nvidia-smi's "CUDA Version: 12.4"
# header. A channel newer than the driver is the classic cudnn_ops...dll load failure.
pick_cuda_channel() {
  local drv major minor
  drv="$(nvidia-smi 2>/dev/null | grep -oE 'CUDA Version: [0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -1)"
  # torch 2.8.0 (TORCH_PIN) is built for cu126, cu128 and cu129 only, so cu126 is the floor: a driver it cannot
  # read gets cu126, and if that driver is older torch says so and the existing GPU warning names the fix.
  CUDA_CHAN=cu126
  if [ -n "$drv" ]; then
    major="${drv%%.*}"; minor="${drv#*.}"
    if   [ "$major" -gt 12 ] || { [ "$major" -eq 12 ] && [ "$minor" -ge 8 ]; }; then CUDA_CHAN=cu128
    elif [ "$major" -eq 12 ] && [ "$minor" -ge 6 ]; then CUDA_CHAN=cu126
    else
      # Older than CUDA 12.6: no GPU build of the pinned torch runs on it, so this is a processor install (and
      # gets the processor pins). The one GPU rebuild counts as spent, so a later run never rebuilds for it;
      # speech_tools_ready then says once that a driver update unlocks the GPU.
      echo "[word-timings] the NVIDIA driver reports CUDA $drv, older than the 12.6 the speech tools' GPU build" >&2
      echo "[word-timings] needs, so they run on the processor. Updating the NVIDIA driver unlocks the GPU." >&2
      GPU_CUDA=0; CUDA_CHAN=""
      : > "$VENV.cuda-rebuild-tried"
      return 0
    fi
    echo "[word-timings] NVIDIA driver reports CUDA $drv — using torch $CUDA_CHAN wheels" >&2
  else
    echo "[word-timings] NVIDIA GPU detected, driver CUDA version unreadable — defaulting to $CUDA_CHAN" >&2
  fi
}

install_listener() {
  # venv_py looks at what is ON DISK, so it is asked only now that `uv venv` has made the folder. Asked
  # earlier it guesses bin/python, the Mac layout, and a fresh Windows build pointed at a file never there.
  PYBIN="$(venv_py "$VENV")"
  VERIFIED_MODE=cpu
  # PyAV always as a ready-made wheel on a Mac. From av 16 its Apple-chip wheels need macOS 14 (every
  # release 16.0.1 through 19.0.0 is macosx_14_0_arm64, PyPI 2026-09-30), so on an Apple-chip Mac on macOS 13
  # the resolver would pick a source build that needs Apple's developer tools and FFmpeg's headers. With this
  # that Mac gets av 15.1.0; newer Macs and Intel Macs (wheels from macOS 11) resolve as before.
  AV_WHEEL=""
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] && AV_WHEEL="--only-binary av"
  # The faster-whisper venv runs on the processor even beside an NVIDIA card (transcribe-nofw.py): no CUDA torch,
  # no whisperx. Asked first, so an NVIDIA PC moved to it gets the ~175 MB listener, not the 3 GB set again.
  if [ "$GPU_CUDA" -eq 1 ] && [ "$NOFW" != 1 ]; then pick_cuda_channel; fi   # a driver too old for the pinned torch turns it off
  if [ "$GPU_CUDA" -eq 1 ] && [ "$NOFW" != 1 ]; then
    # The CUDA wheel goes in FIRST: a plain `pip install whisperx` pulls CPU-only torch even next to a GPU
    # and would replace it (product/PC-CONVERSION-PLAYBOOK.md → WhisperX). The second install names the same
    # torch version, which the +cuXXX build already satisfies, so PyPI's processor build never replaces it.
    echo "[word-timings] installing CUDA torch first, then whisperx" >&2
    # whisperx 3.8 also needs torchvision 0.23, which comes from the same CUDA index to match torch.
    local tv=""
    [ "$(whisperx_pin)" = "whisperx==3.8.6" ] && tv="torchvision==0.23.0"
    # --extra-index-url keeps PyPI in the search: torch's own dependencies (sympy, networkx, jinja2...) are
    # not on PyTorch's index, and --index-url alone cannot resolve them on some machines.
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" $TORCH_PIN $tv --extra-index-url "https://download.pytorch.org/whl/$CUDA_CHAN" >&2 || true
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" $(whisperx_pin) $TORCH_PIN $(tested_pins "$PYBIN") $AV_WHEEL $SAC_PINS $(ct2_pin) >&2 || { fallback_note
      uv pip install --python "$PYBIN" whisperx $TORCH_PIN $AV_WHEEL $SAC_PINS $(ct2_pin) >&2; }
    # A clean exit from uv is no evidence of a GPU torch; torch itself is asked.
    if "$PYBIN" -c 'import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)' 2>/dev/null; then
      VERIFIED_MODE=cuda
      echo "[word-timings] ✓ torch can see the GPU" >&2
    else
      echo "[word-timings] ⚠ the GPU build of torch installed, but torch still cannot see the GPU, so these" >&2
      echo "[word-timings]   speech tools run on the processor. An outdated NVIDIA driver is the usual cause." >&2
    fi
  elif [ "$NOFW" = 1 ]; then
    # onnxruntime pinned to the newest wheel this macOS has an Intel build of; unpinned, the resolver walks the
    # version list one download at a time on the slowest machine the engine supports (scripts/_mac-arch.sh).
    local pins
    pins="$(mac_intel_onnx_pin 2>/dev/null || true) $(mac_intel_extra_pins 2>/dev/null || true)"
    pins="$(echo $pins)"   # off a Mac both are empty (_mac-arch.sh): no stray "with" in the line below
    echo "[word-timings] installing faster-whisper (no torch) ${pins:+with $pins}" >&2
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" faster-whisper $pins $AV_WHEEL $(ct2_pin) >&2
  else
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" $(whisperx_pin) $TORCH_PIN $(tested_pins "$PYBIN") $AV_WHEEL $SAC_PINS $(ct2_pin) >&2 || { fallback_note
      uv pip install --python "$PYBIN" whisperx $TORCH_PIN $AV_WHEEL $SAC_PINS $(ct2_pin) >&2; }
  fi
  # verify-cut.py imports faster_whisper itself and assumes whisperx brought it. On a real PC it had not, and
  # the listen-back skipped itself for a whole job without a word, so it is installed explicitly.
  if [ "$NOFW" != 1 ] && ! "$PYBIN" -c "import faster_whisper" >/dev/null 2>&1; then
    echo "[word-timings] adding faster-whisper (the cut listen-back needs it)" >&2
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" faster-whisper $AV_WHEEL $SAC_PINS $(ct2_pin) >&2 || \
      echo "[word-timings] ⚠ faster-whisper did not install — verify-cut will be skipped, cuts are unchecked" >&2
  fi
}

build_if_unfinished() {
  if has_verified_record; then return 0; fi
  if [ "$NOFW" = 1 ]; then
    echo "[word-timings] setting up the speech tools at $VENV, once: faster-whisper, the light listener (no torch)." >&2
    echo "[word-timings] Give it a few minutes online" >&2
  else
    echo "[word-timings] setting up the speech tools at $VENV, once. They bring torch, so give it a few minutes" >&2
  fi
  # `uv venv` / `uv python install` may download a Python and then run install_name_tool, which on a Mac
  # without Apple's developer tools is a placeholder that opens an "install the tools?" dialog. The stand-in
  # shadows only that one name (scripts/_mac-arch.sh mac_clt_shield).
  if command -v mac_clt_shield >/dev/null 2>&1; then
    local shield
    shield="$(mac_clt_shield "$WORK/clt-shield")"
    if [ -n "$shield" ]; then PATH="$shield:$PATH"; export PATH; fi
  fi
  announce_download
  use_signed_python_if_blocked
  if ! make_venv; then
    note_fallback "the speech tools' venv would not build, with uv or with Python's own venv; the rough cut stopped"
    echo "[word-timings] ⚠ the speech tools could not be set up on this computer. Run /report-a-problem: the report" >&2
    echo "[word-timings]   carries what was tried." >&2
    exit 1
  fi
  # Every step inside reports its own failure; what decides is whether the listener imports afterwards.
  install_listener || true
  local mod=whisperx
  [ "$NOFW" = 1 ] && mod=faster_whisper
  # The newer processor-only set would not install: the measured one goes into the same venv, this run.
  if ! "$PYBIN" -c "import $mod" >/dev/null 2>&1 && [ "$GPU_CUDA" -eq 0 ] \
     && back_to_measured_set "the newer speech tools (CTranslate2 4.7.2, whisperx 3.8.6) would not install on this computer"; then
    install_listener || true
  fi
  if ! "$PYBIN" -c "import $mod" >/dev/null 2>&1; then
    if [ "$NOFW" != 1 ] && pivot_to_faster_whisper "WhisperX would not install on this computer"; then return 0; fi
    note_fallback "no speech tool would install; the rough cut stopped"
    echo "[word-timings] ⚠ the speech tools would not install on this computer. Run /report-a-problem: the report" >&2
    echo "[word-timings]   carries what was tried." >&2
    exit 1
  fi
  mark_ready "$VERIFIED_MODE"
}

speech_tools_ready() {
  PYBIN="$(venv_py "$VENV")"
  local r
  r="$(ready_record)"
  VENV_MODE="$( [ -n "$r" ] && cat "$r" 2>/dev/null || true)"; VENV_MODE="${VENV_MODE:-cpu}"
  # A card that showed up (or got its driver) after this venv was verified CPU-only, and the one rebuild did
  # not take: say so once rather than staying on the processor in silence.
  if [ "$NOFW" != 1 ] && [ "$GPU_CUDA" -eq 1 ] && [ "$VENV_MODE" != "cuda" ]; then
    echo "[word-timings] note: an NVIDIA GPU is present but the speech tools verified as CPU-only even after a" >&2
    echo "[word-timings]       rebuild for it. An outdated NVIDIA driver is the usual cause: update the driver," >&2
    echo "[word-timings]       then delete $VENV and $VENV.cuda-rebuild-tried and run once more." >&2
  fi
}

# A venv built before TORCH_PIN (top of this file) can hold torch or torchaudio 2.9+, where voice detection
# cannot load at all. Its record says finished, so it is never rebuilt: the tested versions go back in, in
# place, once. A venv on 2.8 or older is left exactly as it is.
pin_whisperx_in_place() {
  if [ "$NOFW" = 1 ]; then return 0; fi
  local drift
  drift="$("$PYBIN" - <<'PY' 2>/dev/null || true
import importlib.metadata as m
def mm(p):
    try: return tuple(int(x) for x in m.version(p).split("+")[0].split(".")[:2])
    except Exception: return (0, 0)
print(next((f"{p} {m.version(p)}" for p in ("torch", "torchaudio") if mm(p) >= (2, 9)), ""))
PY
)"
  if [ -z "$drift" ]; then return 0; fi
  echo "[word-timings] the speech tools here moved to $drift, which stops voice detection from loading." >&2
  echo "[word-timings] Putting back the versions the engine is tested with (once, a few minutes)." >&2
  # Smart App Control's pins, read the same way the build reads them (only the state, nothing installed).
  if [ "$WINDOWS_SHELL" = 1 ] && [ -n "$ENGINE_ROOT" ] && [ -f "$ENGINE_ROOT/scripts/_win-sac.sh" ]; then
    . "$ENGINE_ROOT/scripts/_win-sac.sh"
    if [ "$(win_sac_state)" = on ]; then SAC_PINS="$WIN_SAC_PINS"; fi
  fi
  AV_WHEEL=""   # PyAV as a ready-made wheel on a Mac, exactly as install_listener sets it
  ensure_uv     # this venv may have been built before uv went missing
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] && AV_WHEEL="--only-binary av"
  if [ "$VENV_MODE" = cuda ] && [ "$GPU_CUDA" -eq 1 ]; then pick_cuda_channel; fi
  if [ "$VENV_MODE" = cuda ] && [ "$GPU_CUDA" -eq 1 ]; then
    local tv=""
    [ "$(whisperx_pin)" = "whisperx==3.8.6" ] && tv="torchvision==0.23.0"
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" $TORCH_PIN $tv --extra-index-url "https://download.pytorch.org/whl/$CUDA_CHAN" >&2 || true
  elif [ "$VENV_MODE" = cuda ]; then
    mark_ready cpu; VENV_MODE=cpu   # the processor build replaces it below, so the record says so
  fi
  # shellcheck disable=SC2086
  uv pip install --python "$PYBIN" $(whisperx_pin) $TORCH_PIN $(tested_pins "$PYBIN") $AV_WHEEL $SAC_PINS $(ct2_pin) >&2 || { fallback_note
    uv pip install --python "$PYBIN" whisperx $TORCH_PIN $AV_WHEEL $SAC_PINS $(ct2_pin) >&2; } || \
    echo "[word-timings] could not put the tested versions back; if WhisperX stops, faster-whisper hears the reel" >&2
}

# A processor-only Windows venv built before the CTranslate2 pin (top of this file) still holds the version that
# crashes. Swapped once, in place: about a minute, never the 3 GB rebuild. 4.5.x stays (the Smart App Control
# pin, measured to load). On the newer set only 4.8 and up is swapped, to 4.7.2 (a first load that crashes on it
# still moves this PC to the measured set, in listen); on the measured set 4.6 and up goes back to 4.4.0 with the
# whisperx it allows. An NVIDIA PC's venvs were built on 4.8 before ct2_pin covered them: its WhisperX venv goes to
# 4.7.2, and the mark that sent it to faster-whisper is cleared (that crash was 4.8's), so WhisperX gets its turn
# again with the whole fallback chain behind it; its faster-whisper venv goes to 4.4.0.
pin_ct2_in_place() {
  if [ "$WINDOWS_SHELL" != 1 ] || [ -n "${SAC_PINS:-}" ]; then return 0; fi
  local v
  v="$(venv_ct2)"
  case "$v" in ""|4.[0-5]|4.[0-5].*|[0-3].*) return 0 ;; esac
  if [ "$NOFW" = 1 ]; then
    echo "[word-timings] swapping the speech tools' CTranslate2 $v for 4.4.0, the version measured on PC processors" >&2
    echo "[word-timings] (once, about a minute)" >&2
    ensure_uv
    # shellcheck disable=SC2086
    uv pip install --python "$PYBIN" $CT2_WIN_CPU_PIN >&2 || \
      echo "[word-timings] ⚠ could not swap CTranslate2, carrying on with $v" >&2
    return 0
  fi
  if [ "$GPU_CUDA" -ne 0 ]; then
    case "$v" in 4.[67]|4.[67].*) return 0 ;; esac
    echo "[word-timings] swapping the speech tools' CTranslate2 $v for 4.7.2, the last version before the change that" >&2
    echo "[word-timings] crashes on PCs (once, about a minute)" >&2
    ensure_uv
    # shellcheck disable=SC2086
    if uv pip install --python "$PYBIN" $CT2_WIN_CPU_TRY >&2; then rm -f "$VENV/$FW_ONLY_MARK" 2>/dev/null || true
    else echo "[word-timings] ⚠ could not swap CTranslate2, carrying on with $v" >&2; fi
    return 0
  fi
  if [ "${CT2_WIN_CPU_MEASURED:-0}" = 1 ]; then
    echo "[word-timings] swapping the speech tools' CTranslate2 $v for 4.4.0, the version measured on this PC's" >&2
    echo "[word-timings] processor (once, about a minute)" >&2
    put_measured_win_cpu_set || echo "[word-timings] ⚠ could not swap CTranslate2, carrying on with $v" >&2
    return 0
  fi
  case "$v" in 4.[67]|4.[67].*) return 0 ;; esac
  echo "[word-timings] swapping the speech tools' CTranslate2 $v for 4.7.2, the last version before the change that" >&2
  echo "[word-timings] crashes on PC processors (once, about a minute)" >&2
  ensure_uv
  # shellcheck disable=SC2086
  uv pip install --python "$PYBIN" $CT2_WIN_CPU_TRY >&2 || \
    echo "[word-timings] ⚠ could not swap CTranslate2, carrying on with $v" >&2
}

# ── The processor-only Windows set: newer first, measured as the way back ──
#
# A processor-only PC tries CTranslate2 4.7.2 with whisperx 3.8.6 (top of this file), which nobody has run on the
# laptop that crashed yet. Nothing about that may leave her worse off than the measured set did: an install that
# will not take, or a first WhisperX load that crashes or errors, moves this PC to 4.4.0 + whisperx 3.4.5 in the
# same run, her reel is heard on it, and the mark below keeps every later build there. Once a reel has been heard
# on 4.7.2 here, a later error is not blamed on it: the faster-whisper route takes it, as on any machine.
# Deleting the mark lets the next rebuilt venv try the newer set again.
CT2_PROVEN_SUFFIX=".ct2-4.7-heard"

# Beside the WhisperX venv, whichever venv this run uses (the no-uv mark's pattern).
ct2_measured_mark() { printf '%s.ct2-4.4' "${REELS_ENGINE_WHISPERX_VENV:-$(venv_home whisperx-venv)}"; }

venv_ct2() {   # the CTranslate2 version in this venv, or nothing
  "$PYBIN" -c 'import importlib.metadata as m; print(m.version("ctranslate2"))' 2>/dev/null || true
}

# Which set this run installs or keeps. A finished venv already on 4.4.0 or older stays exactly as it is: no
# surprise multi-GB rebuild to try the newer one. A new venv, or one being rebuilt anyway, tries 4.7.2.
choose_win_cpu_set() {
  CT2_WIN_CPU_MEASURED=0
  [ "$WINDOWS_SHELL" = 1 ] || return 0
  if [ -e "$(ct2_measured_mark)" ]; then CT2_WIN_CPU_MEASURED=1; return 0; fi
  has_verified_record || return 0
  PYBIN="$(venv_py "$VENV")"
  case "$(venv_ct2)" in 4.[0-4]|4.[0-4].*|[0-3].*) CT2_WIN_CPU_MEASURED=1 ;; esac
}

# True while this PC is on the newer set and no reel has been heard on it yet.
trying_newer_win_cpu_set() {
  [ "$WINDOWS_SHELL" = 1 ] && [ "$NOFW" != 1 ] && [ "${VENV_MODE:-cpu}" != cuda ] \
    && [ "${CT2_WIN_CPU_MEASURED:-0}" != 1 ] && [ ! -e "$VENV$CT2_PROVEN_SUFFIX" ] || return 1
  case "$(venv_ct2)" in ""|4.[0-5]|4.[0-5].*|[0-3].*) return 1 ;; esac   # 4.5.x: Smart App Control's own
}

# The switch itself, said once and remembered. Non-zero when this PC is not trying the newer set.
back_to_measured_set() {   # $1 = what happened
  [ "$WINDOWS_SHELL" = 1 ] && [ "$NOFW" != 1 ] && [ "${CT2_WIN_CPU_MEASURED:-0}" != 1 ] && [ -z "${SAC_PINS:-}" ] \
    || return 1
  CT2_WIN_CPU_MEASURED=1
  : > "$(ct2_measured_mark)" 2>/dev/null || true
  note_fallback "$1; moved this computer to CTranslate2 4.4.0 with whisperx 3.4.5, the set measured on PC processors"
  echo "[word-timings] $1." >&2
  echo "[word-timings] Moving the speech tools to the versions measured on PC processors (CTranslate2 4.4.0," >&2
  echo "[word-timings] whisperx 3.4.5): about a minute, and every reel after this uses them. Your edit keeps going." >&2
}

# The measured set, in place. Named in full: on a PC whose NVIDIA driver is too old for the GPU build, whisperx_pin
# answers for the card, not for this processor venv.
put_measured_win_cpu_set() {
  ensure_uv
  AV_WHEEL="${AV_WHEEL:-}"   # empty off a Mac, so always empty here; carried like every other whisperx install
  # shellcheck disable=SC2086
  uv pip install --python "$PYBIN" whisperx==3.4.5 $TORCH_PIN $AV_WHEEL $CT2_WIN_CPU_PIN >&2
}

# After WhisperX failed on the newer set's first load: the switch, the measured set in place, and a yes when the
# reel should be heard again. $1 = WhisperX's exit code (the codes listen treats as this computer, not her reel).
retry_on_measured_set() {
  case "$1" in 1|132|134|136|138|139) ;; *) return 1 ;; esac
  trying_newer_win_cpu_set || return 1
  local v why
  v="$(venv_ct2)"
  why="WhisperX crashed as it loaded with CTranslate2 $v (exit $1)"
  [ "$1" = 1 ] && why="WhisperX stopped with an error on CTranslate2 $v"
  back_to_measured_set "$why" || return 1
  if ! put_measured_win_cpu_set; then
    echo "[word-timings] the measured versions would not install either; faster-whisper hears this reel" >&2
    return 1
  fi
  echo "[word-timings] hearing the same footage again on them" >&2
}

# The first reel heard on 4.7.2 here: from now on it is this PC's set, and a later error is the reel's own.
note_newer_set_heard() {
  trying_newer_win_cpu_set || return 0
  : > "$VENV$CT2_PROVEN_SUFFIX" 2>/dev/null || true
}

# ════ Listening ══════════════════════════════════════════════════════════════════════════════════════════

# WhisperX loads torch, CTranslate2 and pyannote's voice detection into one process, and on some PCs those
# native libraries crash together (a buyer's 13th-gen Intel laptop: a segmentation fault at the voice-detection
# step even with CTranslate2 pinned, both detection backends, one thread and memory freed). faster-whisper on its
# own loaded clean on that same machine, and it is already in this venv for the cut listen-back. So a crash moves
# the job to it (the Intel-Mac listener: same words.json, word edges re-stamped from the audio), and a mark beside
# the venv sends every later reel straight there instead of crashing first. A rebuilt venv clears the mark.
FW_ONLY_MARK=".whisperx-crashed"

listen_faster_whisper() {
  # CTranslate2 links Intel MKL, which warns that SSE4.2-only processors are deprecated. Every Mac on the Intel
  # route has AVX2, but a line saying "WARNING ... deprecated" is the first thing she would see, right after
  # hearing her Mac is the unusual one. Only that known line is dropped.
  "$PYBIN" "$ENGINE_ROOT/scripts/transcribe-nofw.py" "$SCRATCH_WORDS" "${CLIPS[@]}" \
    2> >(grep --line-buffered -vE 'Intel MKL WARNING|Intel\(R\) Streaming SIMD|oneAPI Math Kernel' >&2)
}

# faster-whisper from WhisperX's own venv. It shares WhisperX's native libraries, so it can go down the same way (a
# buyer's NVIDIA PC, 2026-10-22: exit 139 on both, and the rough cut stopped). Its own light venv, on the CTranslate2
# measured on PC processors, is then the last stop, and every later reel goes straight there. $1 = why WhisperX is
# not the one listening.
listen_faster_whisper_here() {
  local rc=0
  REELS_ENGINE_NOFW_REASON="$1" listen_faster_whisper || rc=$?
  case "$rc" in
    132|134|136|138|139)
      pivot_to_faster_whisper "faster-whisper crashed in the same speech tools too (exit $rc)" || return "$rc"
      listen_faster_whisper ;;
    *) return "$rc" ;;
  esac
}

# True when this venv can carry the faster-whisper listener in WhisperX's place.
can_hear_without_whisperx() {
  [ -n "$ENGINE_ROOT" ] && [ -f "$ENGINE_ROOT/scripts/transcribe-nofw.py" ] \
    && "$PYBIN" -c "import faster_whisper" >/dev/null 2>&1
}

# The backup route. Her edit never stops at the transcriber: when WhisperX will not install or will not run here,
# faster-whisper hears the footage (the Intel-Mac listener: no torch, ~175 MB, same words.json, word edges
# re-stamped from the audio) and every reel after this goes straight to it. Each switch is one line in
# _local/fallbacks.log, which /report-a-problem attaches, so the cause can still be fixed for everyone.
PIVOT_SUFFIX=".use-faster-whisper"

note_fallback() {   # $1 = what happened and what the engine did instead
  [ -n "$ENGINE_ROOT" ] || return 0
  mkdir -p "$ENGINE_ROOT/_local" 2>/dev/null || return 0
  printf '%s  transcriber: %s\n' "$(date -u '+%Y-%m-%d %H:%MZ' 2>/dev/null)" "$1" \
    >> "$ENGINE_ROOT/_local/fallbacks.log" 2>/dev/null || true
}

# Marked beside the WhisperX venv (pick_venv reads it on every later run), then the faster-whisper venv built if
# this machine has none yet. Non-zero only when that build fails too.
pivot_to_faster_whisper() {   # $1 = why
  if [ -z "$ENGINE_ROOT" ] || [ ! -f "$ENGINE_ROOT/scripts/transcribe-nofw.py" ]; then return 1; fi
  : > "$VENV$PIVOT_SUFFIX" 2>/dev/null || true
  note_fallback "$1; switched to faster-whisper for this and every later reel"
  echo "[word-timings] $1. Switching to faster-whisper, the lighter listener that runs on more computers:" >&2
  echo "[word-timings] same words, timed from your audio, and every reel after this uses it. Your edit keeps going." >&2
  export REELS_ENGINE_NOFW_REASON="$1"
  NOFW=1
  pick_venv
  if ! has_verified_record; then
    make_venv || return 1
    install_listener || true
    PYBIN="$(venv_py "$VENV")"
    "$PYBIN" -c "import faster_whisper" >/dev/null 2>&1 || return 1
    mark_ready cpu
  fi
  PYBIN="$(venv_py "$VENV")"
}

# WhisperX over every clip, in its own process. Its exit code is the caller's to read: 0, a Python error (1), a
# native crash, or her own Ctrl-C.
listen_whisperx() {
  local rc=0 wo_was="${TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD-__unset__}"
  # torch 2.6 and later load checkpoints "weights only" by default, and on a PC whose torch is newer than the pin
  # (or whose pyannote / lightning never pass weights_only themselves) WhisperX's own voice-detection checkpoint
  # is refused: "Weights only load failed", exit 1, and the reel goes to faster-whisper (buyer reports,
  # 2026-10-19). Every model here comes from a known source (WhisperX's own and the pinned aligners above), so on
  # Windows torch is told to load them the way it always did, for this one run and nothing else. A Mac is left
  # exactly as it is: its measured set loads clean.
  if [ "$WINDOWS_SHELL" = 1 ]; then export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1; fi
  # Some Macs print torchcodec's failed library probes straight to the terminal (past Python's warnings, so
  # the filter inside cannot reach them), then fall back and work. Only those known lines are dropped; real
  # errors and every [word-timings] line pass through.
  "$PYBIN" - "$SCRATCH_WORDS" "${CLIPS[@]}" 2> >(grep --line-buffered -vE 'libtorchcodec|libavutil|libavcodec|libavformat|libswresample|libswscale|torchcodec|FFmpeg is not properly|torio' >&2) <<'PY' || rc=$?
"""WhisperX over every clip: what this machine can carry, the language each clip is in, the timed words, and
a diagnostics record of how it went. Status goes to stderr; stdout belongs to the shell side."""
import json, os, sys, time, warnings, logging, platform

# torchaudio probing torchcodec prints a large "Could not load libtorchcodec ... FFmpeg is not properly
# installed" warning on some machines, then falls back and transcribes fine. Only those sources are quieted.
warnings.filterwarnings("ignore", message=r".*(?i:torchcodec|libtorchcodec|FFmpeg is not properly).*")
for _n in ("torchcodec", "torio", "torio._extension", "torio._extension.utils",
           "torchaudio", "torchaudio._extension", "torchaudio.utils"):
    logging.getLogger(_n).setLevel(logging.ERROR)
import whisperx

out_path, clip_paths = sys.argv[1], sys.argv[2:]


def say(line):
    print(line, file=sys.stderr)


def load_audio(path, sr=16000):
    """whisperx.load_audio, reading the clip's FIRST audio stream. An iPhone clip can carry a second, spatial one
    (codec "apac") flagged as the default, which ffmpeg cannot decode; whisperx's own call lets ffmpeg pick it,
    stops with an error, and the run took that for a computer WhisperX cannot run on."""
    import subprocess
    r = subprocess.run(["ffmpeg", "-nostdin", "-threads", "0", "-i", path, "-map", "0:a:0?", "-f", "s16le",
                        "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(sr), "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"Failed to load audio: {r.stderr.decode(errors='replace')}")
    import numpy as np
    return np.frombuffer(r.stdout, np.int16).flatten().astype(np.float32) / 32768.0


# A clip whose sound cannot be read is the clip's problem, never this computer's. Exit 1 tells the shell side
# WhisperX itself failed here, which marks the machine and sends every later reel to faster-whisper; this code
# tells it to hear only this reel that way. (A clip filmed with no sound at all is not a failure: it is heard as a
# clip with no talking, below.)
CLIP_UNREADABLE = 3
# A language Whisper hears but no openly licensed word aligner exists for (Haitian Creole, 2026-10: the only
# Kreyòl CTC models are MMS, CC BY-NC, which a paid product cannot ship). Also never this computer's fault: the
# shell side hears this reel alone with faster-whisper, which times each word itself, and marks nothing.
# Beside the scratch words.json goes what WhisperX heard: the language, then the model it was using on the
# processor (empty on a GPU), so the faster-whisper pass hears the reel the same way.
NO_ALIGNER = 4


def audio_stream_count(path):
    """How many audio streams the clip carries, from ffprobe; None when ffprobe could not read it."""
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                            "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    return len([ln for ln in r.stdout.splitlines() if ln.strip()]) if r.returncode == 0 else None


def clip_seconds(path):
    """The clip's length from its container, 0.0 when it cannot be told."""
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60)
        return max(0.0, float(r.stdout.strip()))
    except Exception:
        return 0.0


def read_clip(path):
    """The clip's sound (mono, 16 kHz), or None when the clip was filmed with no audio stream at all. Any other
    failure to read it stops this run with CLIP_UNREADABLE, the clip named, so it is never blamed on the computer."""
    try:
        return load_audio(path)
    except RuntimeError as exc:
        if audio_stream_count(path) == 0:
            return None
        tail = " | ".join([ln.strip() for ln in str(exc).splitlines() if ln.strip()][-2:])   # ffmpeg's own words
        say(f"[word-timings] could not read the sound in {os.path.basename(path)}: {tail}")
        raise SystemExit(CLIP_UNREADABLE)


# ── This machine ──────────────────────────────────────────────────────────────────────────────────────────

def _expose_torch_dlls(torch):
    """Windows: the GPU libraries the listener loads arrive inside CUDA torch's own lib folder, where Windows
    does not look for them. Without this the GPU never loads and every PC runs on the processor."""
    dll_dir = os.path.join(os.path.dirname(torch.__file__), "lib")
    if os.path.isdir(dll_dir):
        os.add_dll_directory(dll_dir)
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")


try:
    import torch
    cuda_ok = bool(torch.cuda.is_available())
    if cuda_ok and os.name == "nt":
        _expose_torch_dlls(torch)
except Exception:
    cuda_ok = False

forced_device = os.environ.get("REELS_ENGINE_WHISPER_DEVICE", "").strip().lower()
forced_model = os.environ.get("REELS_ENGINE_WHISPER_MODEL", "").strip()

# What makes CPU + int8 + large-v3 workable is Apple Silicon's int8 acceleration, not macOS: an Intel Mac has
# the same unaccelerated CPU as a Windows laptop and the same multi-hour run. So the line is the chip.
is_apple_silicon = (sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64"))


def _under_rosetta():
    """An Apple-chip Mac running an x86_64 Python (an install carried over from an Intel Mac). It really is a
    slow machine for this run, but the fix is a native install, so it gets said. hw.optional.arm64 reports the
    hardware whatever the process is translated to, and is absent on a true Intel Mac."""
    if sys.platform != "darwin" or is_apple_silicon:
        return False
    try:
        import subprocess
        return subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True,
                              timeout=5).stdout.strip() == "1"
    except Exception:
        return False


rosetta_translated = _under_rosetta()

# A CPU-only machine with 4 logical cores or fewer counts as weak and steps down one more model size, so a
# 5-minute clip stays inside ~30 minutes on roughly 2016-on hardware. A starting heuristic, not a measurement:
# the diagnostics below record real core counts and real wall time so it can be tuned against buyers' machines.
cpu_count = os.cpu_count() or 4
is_weak_cpu = cpu_count <= 4
cpu_model = "small" if is_weak_cpu else "medium"    # what a CPU without Apple Silicon can carry
cpu_batch = 4 if is_weak_cpu else 8

device = forced_device if forced_device in ("cuda", "cpu") else ("cuda" if cuda_ok else "cpu")
if device == "cuda":
    compute_type, default_model = "float16", "large-v3"
elif is_apple_silicon:
    compute_type, default_model = "int8", "large-v3"   # the M-series default: never changed
else:
    compute_type, default_model = "int8", cpu_model
model_name = forced_model or default_model
batch_size = cpu_batch if device == "cpu" else 8

say(f"[word-timings] loading whisperx {model_name} ({device}, {compute_type}, {cpu_count} CPU threads)")
if device == "cpu" and rosetta_translated:
    say("[word-timings]    this is an Apple Silicon Mac, but Python is running under Rosetta (Intel")
    say("[word-timings]    translation), so this run can't use the chip's fast path and gets a lighter")
    say("[word-timings]    model. One-time fix for full speed AND full quality: reinstall the tools")
    say("[word-timings]    natively (a Terminal not set to 'Open using Rosetta', then ./check-setup.sh).")
elif device == "cpu" and not is_apple_silicon:
    _why = "an older/lower-core machine" if is_weak_cpu else "no GPU / Apple Silicon acceleration"
    say(f"[word-timings]    {_why} detected — using a lighter model so this takes minutes, not hours.")
    if not forced_model:
        say("[word-timings]    Set REELS_ENGINE_WHISPER_MODEL=large-v3 to force full quality instead.")

# What to try, in order. On a GPU: full precision, then CTranslate2's mixed int8/float16 at a smaller batch
# (a 4 GB card cannot hold large-v3 at float16), then this machine's own CPU model, never large-v3 on a weak
# CPU. Apple Silicon never has CUDA, so a GPU here is always beside a non-Mac CPU.
cpu_fallback_model = forced_model or cpu_model
if device == "cuda":
    attempts = [("cuda", "float16", model_name, 8),
                ("cuda", "int8_float16", model_name, 4),
                ("cpu", "int8", cpu_fallback_model, cpu_batch)]
else:
    attempts = [(device, compute_type, model_name, batch_size)]

# ── Language ──────────────────────────────────────────────────────────────────────────────────────────────
# Detected per clip, never assumed. Told the audio was English, Whisper once translated 20 seconds of a
# tester's Spanish into fluent English, and the captions faithfully showed what she never said.
# REELS_ENGINE_LANGUAGE=<code> forces one when detection is wrong (quiet audio, a few words, a heavy accent).
_FORCED_LANG = os.environ.get("REELS_ENGINE_LANGUAGE", "").strip().lower() or None
if _FORCED_LANG:
    say(f"[word-timings] language forced to {_FORCED_LANG} by REELS_ENGINE_LANGUAGE")

def _load_asr(model, dev, ctype):
    """The model from this machine's own cache when it is there, with no network at all; online only when it
    is not. Without local_files_only, faster-whisper asks Hugging Face for the newest revision on EVERY load,
    and a Mac with a broken IPv6 route sat ten minutes at 0% CPU on that one question (stuck in SYN_SENT) with
    large-v3 already fully downloaded. A cache miss raises, and the normal download runs."""
    try:
        return whisperx.load_model(model, dev, compute_type=ctype, language=_FORCED_LANG, local_files_only=True)
    except Exception:
        return whisperx.load_model(model, dev, compute_type=ctype, language=_FORCED_LANG)


asr_model = None
failed_tiers = []   # kept in the diagnostics, not only on a scrolling terminal
for _dev, _ctype, _model, _batch in attempts:
    try:
        asr_model = _load_asr(_model, _dev, _ctype)
        if (_dev, _ctype, _model, _batch) != attempts[0]:
            say(f"[word-timings]    stepped down to {_model} ({_dev}, {_ctype}) — the tier above it "
                f"didn't load on the GPU (reason printed above)")
        device, compute_type, model_name, batch_size = _dev, _ctype, _model, _batch
        break
    except Exception as e:
        # Broad on purpose: a CUDA / cuDNN mismatch can surface from CTranslate2's native binding as OSError or
        # ImportError, not only RuntimeError, and each one should move on to the next attempt.
        failed_tiers.append(f"{_model} ({_dev}, {_ctype}): {e}")
        say(f"[word-timings]    {_model} ({_dev}, {_ctype}) failed to load ({e}) — trying the next tier")
if asr_model is None:
    raise RuntimeError("whisperx.load_model failed on every fallback tier, including CPU")

# The word aligner is one model per LANGUAGE, loaded once the clip has said which language it is in.
_align_cache = {}
# Languages Whisper hears but WhisperX ships no aligner for: a wav2vec2 model fine-tuned on that language,
# pinned to the reviewed revision (the weights are a pickle; an unpinned name loads whatever the repo holds
# that day). One is added only after a real clip in that language has gone through a full rough cut.
_EXTRA_ALIGNERS = {
    # Bulgarian. Apache-2.0. Cyrillic character vocab, which is what alignment needs.
    "bg": ("infinitejoy/wav2vec2-large-xls-r-300m-bulgarian", "fa202d261efd557145f4d957759e4e2f119add7c", "1.3 GB"),
    # Icelandic. Reykjavik University's Language and Voice Lab, CC-BY-4.0, 967 h of Samromur. Its vocab carries
    # every Icelandic letter (þ ð æ ö and the acute vowels), so no word loses its timing.
    "is": ("language-and-voice-lab/wav2vec2-large-xlsr-53-icelandic-ep30-967h",
           "f8de0cdc7a09ef45362f32c3514afb2edefca68d", "1.3 GB"),
    # Haitian Creole (ht) has no entry on purpose. Checked on Hugging Face 2026-10-23: the Kreyòl CTC models are
    # Meta's MMS family (facebook/mms-1b-all's "hat" adapter, MahmoudAshraf/mms-300m-1130-forced-aligner), all
    # CC BY-NC 4.0; LLL-CREAM's Kreyòl wav2vec2 models are pretrained only (no CTC head) and CC BY-NC-SA; the
    # rest are Whisper fine-tunes. So ht goes to NO_ALIGNER below: faster-whisper times the words itself.
}
_EXTRA_FILES = ["config.json", "preprocessor_config.json", "pytorch_model.bin", "vocab.json",
                "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json"]


def _extra_aligner_path(lang):
    """Local folder of the pinned model for `lang`, downloaded the first time it is needed."""
    from huggingface_hub import snapshot_download
    repo, rev, size = _EXTRA_ALIGNERS[lang]
    try:
        return snapshot_download(repo, revision=rev, allow_patterns=_EXTRA_FILES, local_files_only=True)
    except Exception:
        say(f"[word-timings]    first {lang} reel on this machine: downloading its alignment model once (~{size})")
        return snapshot_download(repo, revision=rev, allow_patterns=_EXTRA_FILES)


def _aligner(lang):
    """(model, metadata) for `lang`, loaded once per language; None when there is no aligner for it."""
    if lang not in _align_cache:
        say(f"[word-timings] loading the {lang} alignment model")
        try:
            if lang in _EXTRA_ALIGNERS:
                _align_cache[lang] = whisperx.load_align_model(language_code=lang, device=device,
                                                               model_name=_extra_aligner_path(lang))
            else:
                try:   # cached first, for the same reason as _load_asr
                    _align_cache[lang] = whisperx.load_align_model(language_code=lang, device=device,
                                                                   model_cache_only=True)
                except Exception:
                    _align_cache[lang] = whisperx.load_align_model(language_code=lang, device=device)
        except Exception as e:
            _align_cache[lang] = None
            say(f"[word-timings]    no {lang} alignment model available ({e})")
    return _align_cache[lang]


detected_languages = {}          # language -> clip count, for the diagnostics
_announced = set()               # each language other than English is named once, not once per clip


def _no_aligner(lang):
    """Stop with NO_ALIGNER, leaving what the shell side needs to hear the reel with faster-whisper instead."""
    say(f"[word-timings] this audio is {lang}, and there is no word-alignment model for {lang}: faster-whisper "
        f"hears this reel instead and times each word itself.")
    say(f"[word-timings]    (If {lang} is wrong, force the language: REELS_ENGINE_LANGUAGE=<code>.)")
    try:
        with open(out_path + ".no-aligner", "w", encoding="utf-8", newline="\n") as fh:   # read by bash on Windows too
            fh.write(f"{lang}\n{model_name if device == 'cpu' else ''}\n")
    except OSError:
        pass
    raise SystemExit(NO_ALIGNER)


def _process(audio):
    # A language she named and nothing can align: no point hearing the clip twice.
    if _FORCED_LANG and _aligner(_FORCED_LANG.lower()) is None:
        _no_aligner(_FORCED_LANG.lower())
    r = asr_model.transcribe(audio, batch_size=batch_size, language=_FORCED_LANG)
    # A language she named wins over detection: that is the whole point of naming it.
    lang = (_FORCED_LANG or r.get("language") or "en").lower()
    detected_languages[lang] = detected_languages.get(lang, 0) + 1
    if lang != "en" and lang not in _announced:
        _announced.add(lang)
        # Said out loud: a whole reel once came back in the wrong language and nobody knew until she watched it.
        say(f"[word-timings] heard {lang}, not English — transcribing and aligning in {lang}. "
            f"(Wrong? re-run with REELS_ENGINE_LANGUAGE=<code> to force one.)")
    am = _aligner(lang)
    if am is None:
        # Every later step needs word times, and an untimed words.json would fail far downstream. This used to
        # stop with exit 1, which the shell side reads as "WhisperX cannot run on this computer" and marked it,
        # sending every later reel (English ones too) to faster-whisper. Its own code hears this reel alone there.
        _no_aligner(lang)
    return whisperx.align(r["segments"], am[0], am[1], audio, device, return_char_alignments=False)


# ── The words ─────────────────────────────────────────────────────────────────────────────────────────────

def timed_words(aligned):
    """One clip's words.json entries, {word, start, end, score} (WhisperX's own names), times to the
    millisecond. The cut, the snap and the captions all work from a word's start and end, so an entry the
    aligner handed back without them is not written."""
    kept = []
    for piece in aligned.get("segments", []):
        for item in piece.get("words", []):
            t0, t1 = item.get("start"), item.get("end")
            if t0 is None or t1 is None:
                continue
            kept.append({"word": str(item.get("word", "")).strip(), "start": round(float(t0), 3),
                         "end": round(float(t1), 3), "score": round(float(item.get("score", 1.0)), 3)})
    return kept


def _finish_on_cpu(name, exc):
    """The GPU loaded the model and then failed on a clip (a 4 GB card has run out of memory on a five-minute
    take). From here this run uses the CPU: this machine's CPU model is loaded, the clip is heard again, and
    the failure is kept for the diagnostics. A failure on the CPU after that is not caught."""
    global asr_model, device, compute_type, model_name, batch_size
    failed_tiers.append(f"{model_name} ({device}, {compute_type}) mid-run on {name}: {exc}")
    say(f"[word-timings]    the GPU gave out partway through {name} ({type(exc).__name__}) — finishing "
        f"on the CPU tier instead")
    device, compute_type, model_name, batch_size = "cpu", "int8", cpu_fallback_model, cpu_batch
    del asr_model
    try:
        import gc; gc.collect(); torch.cuda.empty_cache()
    except Exception:
        pass
    asr_model = _load_asr(model_name, device, compute_type)
    _align_cache.clear()   # the aligners sat on the old device; _process reloads them per language


# Wall time from the first clip on (model loading excluded), per second of footage: the number the
# diagnostics carry so the weak-CPU line above can be tuned on real machines.
_t_start = time.monotonic()
total_clip_seconds = 0.0
clips_out = []                   # one entry per clip, in the order the shell handed them over
for clip_path in clip_paths:
    name = os.path.basename(clip_path)
    say(f"[word-timings] {name}")
    pcm = read_clip(clip_path)                  # mono, 16 kHz
    if pcm is None:
        # Filmed with no sound (a muted clip, a screen recording): no words, the same entry a clip with no
        # talking gets, and product/quiet_clips.py marks it silent so the cut keeps it whole.
        say(f"[word-timings]    {name} has no sound in it: kept as a clip with no talking")
        clips_out.append({"clip": name, "path": clip_path, "duration": round(clip_seconds(clip_path), 3),
                          "words": []})
        continue
    seconds = len(pcm) / 16000.0
    total_clip_seconds += seconds
    try:
        aligned = _process(pcm)
    except Exception as exc:
        if device != "cuda":
            raise
        _finish_on_cpu(name, exc)
        aligned = _process(pcm)
    clips_out.append({"clip": name, "path": clip_path, "duration": round(seconds, 3),
                      "words": timed_words(aligned)})

result = {"clips": clips_out}
with open(out_path, "w") as fh:
    json.dump(result, fh, indent=2)
say(f"[word-timings] wrote {out_path}")

# ── Diagnostics ───────────────────────────────────────────────────────────────────────────────────────────
# What this machine actually did, for the hardware-diagnostic report (product/hardware-diagnostic.py: opt-in,
# she reviews it, never sent on its own). Beside the scratch words.json; the shell side copies it next to the
# job's transcript. One per job, replaced each run. Best-effort: it never fails a transcription.
wall_seconds = round(time.monotonic() - _t_start, 1)
diag_path = os.path.join(os.path.dirname(out_path), ".transcribe-diagnostics.json")
try:
    # Confidence is no proof of accuracy (real footage has no answer key), but it can flag a run that came
    # out noticeably less sure than usual for someone to go and look at.
    all_scores = [word["score"] for clip in clips_out for word in clip["words"]]
    avg_confidence = round(sum(all_scores) / len(all_scores), 3) if all_scores else None
    diag = {
        "device": device, "model": model_name, "compute_type": compute_type,
        "cpu_logical_cores": cpu_count, "is_apple_silicon": is_apple_silicon,
        "rosetta_translated": rosetta_translated,   # Apple-chip hardware, x86_64 Python: explains a lighter model
        "is_weak_cpu": is_weak_cpu, "platform": sys.platform, "machine": platform.machine(),
        "wall_seconds": wall_seconds, "total_clip_seconds": round(total_clip_seconds, 1),
        "realtime_ratio": round(wall_seconds / total_clip_seconds, 2) if total_clip_seconds > 0 else None,
        "avg_word_confidence": avg_confidence,
        # What was heard, per clip: the record that would have caught a Spanish reel labelled English.
        "detected_languages": dict(sorted(detected_languages.items(), key=lambda kv: -kv[1])),
        "language_forced": _FORCED_LANG,
        "fallback_tiers_that_failed": failed_tiers or None,
    }
    os.makedirs(os.path.dirname(diag_path), exist_ok=True)
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(diag, f, indent=2)
except Exception:
    pass

# ── Words to listen to before cutting on them ─────────────────────────────────────────────────────────────
# Measured on real footage, a word stamped over a second long more often than not has a pause inside it: two
# takes written as one word, or one word stretched over the quiet next to it. Each one is named here, before
# anything is cut on it.
for clip in clips_out:
    for w in clip["words"]:
        if w["end"] - w["start"] > 1.0:
            say(f"[word-timings] ⚠ listen before cutting on {w['word']!r} at {w['start']:.2f}-{w['end']:.2f}s: "
                f"{w['end']-w['start']:.2f}s is long enough to hold a pause (two takes as one word, or a word "
                f"stretched over quiet)")
PY
  if [ "$WINDOWS_SHELL" = 1 ]; then   # back to what it was before this run, set or not
    if [ "$wo_was" = __unset__ ]; then unset TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD; else export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="$wo_was"; fi
  fi
  return "$rc"
}

listen() {
  # The first transcription in a session spends minutes loading the model before a word comes out. Said at
  # the moment it starts, so a new buyer's first edit does not look hung. Which model loads is decided by
  # the listener itself, from the hardware it finds, and printed there.
  local label="WhisperX" rc=0
  if [ "$NOFW" = 1 ] || [ -e "$VENV/$FW_ONLY_MARK" ]; then label="faster-whisper"; fi
  echo "[word-timings] ⏳ Transcribing with $label. The FIRST one in a session takes a few minutes while" >&2
  echo "[word-timings]    the model loads — every reel after this is fast. Nothing is stuck; hang tight." >&2
  if [ "$NOFW" = 1 ]; then
    listen_faster_whisper
  elif [ -e "$VENV/$FW_ONLY_MARK" ] && can_hear_without_whisperx; then
    echo "[word-timings]    (WhisperX did not work on this computer before, so it is skipped here; same words," >&2
    echo "[word-timings]    timed from your audio)" >&2
    listen_faster_whisper_here "WhisperX did not work on this machine before"
  else
    if [ -n "${SCRATCH_WORDS:-}" ]; then rm -f "$SCRATCH_WORDS.no-aligner" 2>/dev/null || true; fi
    listen_whisperx || rc=$?
    # The newer processor-only set's first load: one more go on the measured set before faster-whisper.
    if [ "$rc" = 0 ]; then
      note_newer_set_heard
    elif retry_on_measured_set "$rc"; then
      rc=0
      listen_whisperx || rc=$?
    fi
    # 1 is a Python error: on this machine's versions voice detection or alignment would not load (torchaudio
    # without AudioMetaData, a refused checkpoint). The rest are native crashes (132 SIGILL, 134 SIGABRT, 136 SIGFPE,
    # 138 SIGBUS, 139 SIGSEGV). Either way her reel is heard by faster-whisper, and so is every reel after it.
    # 3 is one of her clips, not this computer: its sound would not read (CLIP_UNREADABLE in the listener). That
    # reel alone goes to faster-whisper, which reads audio its own way, and nothing is marked: the next reel gets
    # WhisperX again. 4 is her language, not this computer: no word aligner exists for it (NO_ALIGNER); the same
    # way out, nothing marked. 130 / 143 are her own Ctrl-C or a stop, and stay what they are.
    case "$rc" in
      0) ;;
      3)
        if can_hear_without_whisperx; then
          note_fallback "a clip's sound would not read for WhisperX; this reel heard with faster-whisper (computer not marked)"
          echo "[word-timings] One clip's sound would not read for WhisperX (the clip, not your computer)." >&2
          echo "[word-timings] Hearing this reel with faster-whisper instead; the next reel uses WhisperX as usual." >&2
          REELS_ENGINE_NOFW_REASON="a clip's sound would not read for WhisperX" listen_faster_whisper
        else
          return "$rc"
        fi ;;
      4)
        # Her language has no word aligner (NO_ALIGNER in the listener: Haitian Creole). Her language, not this
        # computer: this reel goes to faster-whisper, which times each word itself, hearing it in the language
        # WhisperX heard and on the model WhisperX was using on this processor, and nothing is marked.
        if can_hear_without_whisperx; then
          local heard="" heard_model=""
          { IFS= read -r heard; IFS= read -r heard_model; } < "${SCRATCH_WORDS:-}.no-aligner" 2>/dev/null || true
          heard="${heard%$'\r'}"; heard_model="${heard_model%$'\r'}"
          note_fallback "no word aligner for ${heard:-this language}; this reel heard with faster-whisper (computer not marked)"
          echo "[word-timings] Hearing this reel with faster-whisper, which times each word itself; same words," >&2
          echo "[word-timings] same cut. Reels in other languages still use WhisperX as usual." >&2
          REELS_ENGINE_NOFW_REASON="no word aligner for ${heard:-this language}" \
            REELS_ENGINE_HEARD_LANGUAGE="$heard" \
            REELS_ENGINE_WHISPER_MODEL="${REELS_ENGINE_WHISPER_MODEL:-$heard_model}" listen_faster_whisper
        else
          return "$rc"
        fi ;;
      1|132|134|136|138|139)
        local why="WhisperX crashed on this computer as it loaded (exit $rc)"
        [ "$rc" = 1 ] && why="WhisperX stopped with an error on this computer"
        if can_hear_without_whisperx; then
          : > "$VENV/$FW_ONLY_MARK" 2>/dev/null || true
          note_fallback "$why; heard with faster-whisper from the same speech tools"
          echo "[word-timings] $why. Nothing is lost: hearing the same footage with faster-whisper" >&2
          echo "[word-timings] instead, which runs here. Same words, and every reel after this goes straight to it." >&2
          listen_faster_whisper_here "$why"
        elif pivot_to_faster_whisper "$why"; then
          listen_faster_whisper
        else
          return "$rc"
        fi ;;
      *) return "$rc" ;;
    esac
  fi
}

# ════ Keeping it ═════════════════════════════════════════════════════════════════════════════════════════

# The transcript already there moves to history/ first. Usually it is machine output and costs nothing to
# lose, but not always: two real jobs carry hand fixes to WhisperX mis-stamps (same words, corrected times),
# and nothing in the engine could make those again. Timestamped, so a second --force never overwrites the
# copy the first one kept. Best-effort under `set -e`: a copy that cannot be made never stops the run.
keep_previous_transcript() {
  [ -f "$CANON" ] || return 0
  local hist stamp prev
  hist="$JOB_DIR/transcript/history"
  mkdir -p "$hist" 2>/dev/null || return 0
  stamp="$(date -u '+%Y%m%dT%H%M%SZ' 2>/dev/null || echo unknown)"
  prev="$hist/words.$stamp.json"
  if [ -e "$prev" ]; then prev="$hist/words.$stamp.$$.json"; fi   # a same-second re-run keeps both
  if cp "$CANON" "$prev" 2>/dev/null; then
    # The real path: this line is the only way she learns the copy exists.
    echo "[word-timings] previous transcript kept at $prev" >&2
  fi
  return 0
}

save_transcript() {
  hear_quiet_first_line "$SCRATCH_WORDS"
  place_stranded_words "$SCRATCH_WORDS"
  # A clip with no talking (her kids in the store, a vlog moment) still comes back with phantom words from its
  # background sound. product/quiet_clips.py marks it silent and sets those aside, so they never become a cut or
  # a caption. Best-effort: a transcript is never held back by it.
  [ -f "$ENGINE_ROOT/product/quiet_clips.py" ] && python3 "$ENGINE_ROOT/product/quiet_clips.py" mark "$SCRATCH_WORDS" >&2 || true
  # Swapped in whole, so a reader never sees half a transcript.
  cp "$SCRATCH_WORDS" "$CANON.tmp.$$" && mv "$CANON.tmp.$$" "$CANON"
  echo "[word-timings] saved the durable transcript → $CANON" >&2
  # The diagnostics ride along in the same folder. Best-effort: a missing copy never blocks an edit.
  [ -f "$WORK/.transcribe-diagnostics.json" ] && cp "$WORK/.transcribe-diagnostics.json" "$JOB_DIR/transcript/.transcribe-diagnostics.json" 2>/dev/null
  echo "$CANON"
}

# ════ The run ════════════════════════════════════════════════════════════════════════════════════════════

choose_listener
open_job "$@"
hand_back_if_heard
gather_footage
line_up_sound
prefer_brew_ffmpeg7
detect_nvidia
pick_venv
keep_working_venv
rebuild_once_for_gpu
choose_win_cpu_set
build_if_unfinished
speech_tools_ready
pin_whisperx_in_place
pin_ct2_in_place
listen
keep_previous_transcript
save_transcript
