#!/usr/bin/env bash
# name-final.sh: the export phase. The reel she will post becomes outputs/<job>.final.mp4, the passes it
# replaces are cleared, a copy goes where she uploads from, and everything a re-edit reopens stays put.
#
#   scripts/name-final.sh <job>            # a look: says what would happen, changes nothing
#   scripts/name-final.sh <job> --apply    # does it (--apply may also come before the job name)
#
# Only the .mp4 files sitting directly in outputs/ are ever moved, cleared or copied. Each rule is written
# beside the step below that applies it.

set -euo pipefail

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # scripts/ sits one level under the engine

# check-ship.sh runs this with no arguments and looks for a line starting with a lowercase "usage:". Keep that
# prefix: without it the ship gate fails and no release zip is built.
usage() { echo "usage: scripts/name-final.sh <job> [--apply]"; }

JOB="" APPLY=0 SEEN_JOB=0
for word in "$@"; do
  case "$word" in
    --apply) APPLY=1 ;;
    -*) echo "name-final.sh does not know the option $word."; usage; exit 1 ;;
    *)
      if (( SEEN_JOB )); then echo "name-final.sh names one reel at a time; '$word' would be a second job."; usage; exit 1; fi
      JOB="$word"; SEEN_JOB=1 ;;
  esac
done
if [[ -z "$JOB" ]]; then usage; exit 1; fi

JOBDIR="$ENGINE/projects/$JOB"
OUT="$JOBDIR/outputs"
if [[ ! -d "$OUT" ]]; then echo "There is no projects/$JOB/outputs/ folder, so there is no reel to name."; exit 1; fi

CUT="$JOB.mp4"             # the clean cut the rough cut made
REEL="$JOB.final.mp4"      # the one to post
REEL_PATH="$OUT/$REEL"
if [[ -e "$REEL_PATH" && ! -f "$REEL_PATH" ]]; then
  echo "outputs/$REEL is a folder, not a video. Move it out of outputs/ and run this again."
  exit 1
fi

size_of() { du -h "$1" 2>/dev/null | cut -f1; }

# "final" and "draft" are read from the part of a file's name after the job's own name, when it starts with
# it: a job called final-cut or first-draft-tips would otherwise make every one of its passes look final, or
# look like a draft.
starts_with_job() { [[ "${1##*/}" == "$JOB"* ]]; }
tail_of()         { local b="${1##*/}"; if starts_with_job "$1"; then printf '%s' "${b#"$JOB"}"; else printf '%s' "$b"; fi; }
says()            { [[ "$(tail_of "$1")" == *"$2"* ]]; }   # says <file> <word>
is_newer()        { [[ -z "$2" || "$1" -nt "$2" ]]; }      # is_newer <file> <best so far, may be empty>

# ── 1. what is in outputs/ ──────────────────────────────────────────────────────────────────────────────
# A clean cut is never a candidate and never cleared: <job>.mp4, and any <name>.mp4 the rough cut wrote a
# <name>.transcript.json beside (a job folder renamed after its cut keeps its cut under the old name). Every
# other .mp4 is a pass. Names are compared whole (never as patterns), so a job name with [ ] or * cannot pull
# its cut into the passes. A read loop, because macOS's bash 3.2 has no mapfile.
cuts=() passes=()
[[ -f "$OUT/$CUT" ]] && cuts+=("$OUT/$CUT")
while IFS= read -r f; do
  name="${f##*/}"
  [[ "$name" == "$CUT" || "$name" == "$REEL" ]] && continue
  if [[ -f "$OUT/${name%.mp4}.transcript.json" ]]; then cuts+=("$f"); else passes+=("$f"); fi
done < <(find "$OUT" -maxdepth 1 -type f -name '*.mp4' | sort)

# ── 2. which passes are only short previews ─────────────────────────────────────────────────────────────
# A preview never becomes the reel: a pass under half the clean cut's length, or under half the longest pass
# when there is no cut to measure. Lengths come from ffprobe. The engine's path shim finds it when this shell's PATH does not (Homebrew from a
# non-login shell, winget's folders on Windows). The shim runs in a subshell with -e off, and only the PATH it
# repairs comes back: sourced directly into this set -e script, one of its folder tests failing would end
# the run. With no ffprobe, or a file it cannot read, nothing counts as a preview.
if [[ -f "$ENGINE/scripts/_path-shim.sh" ]]; then
  _repaired="$(set +e; . "$ENGINE/scripts/_path-shim.sh" >/dev/null 2>&1; printf '%s' "$PATH")" || _repaired=""
  if [[ -n "$_repaired" ]]; then PATH="$_repaired"; fi
fi
length_ms() {   # length_ms <video>: whole milliseconds, or nothing
  command -v ffprobe >/dev/null 2>&1 || return 0
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null \
    | awk 'NR == 1 && $1 + 0 > 0 { printf "%d", $1 * 1000 }' || true
}
full_ms=""
for c in ${cuts[@]+"${cuts[@]}"}; do full_ms="$(length_ms "$c")"; [[ -n "$full_ms" ]] && break; done
pass_ms=()
for f in ${passes[@]+"${passes[@]}"}; do m="$(length_ms "$f")"; pass_ms+=("${m:-0}"); done
if [[ -z "$full_ms" ]]; then
  for m in ${pass_ms[@]+"${pass_ms[@]}"}; do (( m > ${full_ms:-0} )) && full_ms="$m"; done
fi
preview=()
for m in ${pass_ms[@]+"${pass_ms[@]}"}; do
  if [[ -n "$full_ms" ]] && (( m > 0 && m * 2 < full_ms )); then preview+=(1); else preview+=(0); fi
done

# ── 3. the reel ─────────────────────────────────────────────────────────────────────────────────────────
# Of the passes that are neither a draft nor a preview: the newest named final; failing that, the newest whose
# name starts with the job's (so a later music bed or -v2 wins over an earlier -graphics, and a stray
# hook-v5.mp4 never beats the job's own passes); failing that, the newest of the rest. Ties go to the name
# that sorts first. A pass named graphics gets no head start: the graphics layer comes before captions and
# music, so a later pass always carries more of the reel than it does.
newest_final="" newest_own="" newest_any=""
i=0
for f in ${passes[@]+"${passes[@]}"}; do
  if ! says "$f" draft && [[ "${preview[$i]}" == 0 ]]; then
    if says "$f" final && is_newer "$f" "$newest_final"; then newest_final="$f"; fi
    if starts_with_job "$f" && is_newer "$f" "$newest_own"; then newest_own="$f"; fi
    if is_newer "$f" "$newest_any"; then newest_any="$f"; fi
  fi
  i=$((i + 1))
done
pick="${newest_final:-${newest_own:-$newest_any}}"

# An existing <job>.final.mp4 gives way only to a strictly newer pick, and moves to earlier-finals/ first.
promote="" set_aside=""
if [[ -n "$pick" ]] && { [[ ! -f "$REEL_PATH" ]] || [[ "$pick" -nt "$REEL_PATH" ]]; }; then promote="$pick"; fi
if [[ -n "$promote" && -f "$REEL_PATH" ]]; then
  stamp="$(date -r "$REEL_PATH" +%Y%m%d-%H%M%S 2>/dev/null || date +%Y%m%d-%H%M%S)"
  set_aside="earlier-finals/$JOB.final.$stamp.mp4"; n=2
  while [[ -e "$OUT/$set_aside" ]]; do set_aside="earlier-finals/$JOB.final.$stamp-$n.mp4"; n=$((n + 1)); done
fi

# "Newer than the reel" is measured against the file that will be the reel once --apply has run: the pick
# when there is one (a move keeps its time), else the final already here. A look and --apply agree.
reel_time=""
if [[ -n "$promote" ]]; then reel_time="$promote"; elif [[ -f "$REEL_PATH" ]]; then reel_time="$REEL_PATH"; fi

# ── 4. every other pass: clear it, or leave it for her ──────────────────────────────────────────────────
# Left for her to decide: a pass also named final, one newer than the reel, and (while there is no reel at
# all) a short preview. Everything else is cleared.
clear_files=() clear_lines=() leave_lines=()
i=0
for f in ${passes[@]+"${passes[@]}"}; do
  short="${preview[$i]}"; i=$((i + 1))
  [[ "$f" == "$promote" ]] && continue
  name="${f##*/}"
  if says "$f" final; then
    leave_lines+=("$name: its name says final too, so it is yours to keep or delete")
  elif [[ -n "$reel_time" && "$f" -nt "$reel_time" ]]; then
    leave_lines+=("$name: newer than the reel. If it is the one to post, rename it $REEL yourself")
  elif [[ -z "$reel_time" && "$short" == 1 ]] && ! says "$f" draft; then
    leave_lines+=("$name: a short preview, and no reel has replaced it yet")
  else
    if says "$f" draft; then what="a draft"; else what="an earlier pass the reel replaces"; fi
    clear_files+=("$f"); clear_lines+=("$name  ($what, $(size_of "$f"))")
  fi
done

# ── 5. where the upload copy goes ───────────────────────────────────────────────────────────────────────
# REELS_EXPORT_DIR when set, else her Downloads folder. Git Bash on Windows uses her Windows home as $HOME, so
# ~/Downloads there is the Downloads folder File Explorer shows.
DEST="${REELS_EXPORT_DIR:-$HOME/Downloads}"
have_reel=0
if [[ -n "$promote" || -f "$REEL_PATH" ]]; then have_reel=1; fi

# ── the report ──────────────────────────────────────────────────────────────────────────────────────────
# A section prints its heading with its first item, so a section with nothing in it never shows.
pending=""
section() { pending="$1"; }
item()    { if [[ -n "$pending" ]]; then printf '\n%s\n' "$pending"; pending=""; fi; printf '  %s\n' "$1"; }

if (( APPLY )); then printf '%s: export\n' "$JOB"; else printf '%s: export, as a look (nothing changes yet)\n' "$JOB"; fi

if (( have_reel )); then
  section "The reel to post"
  if [[ -n "$promote" ]]; then
    item "${promote##*/} becomes $REEL  ($(size_of "$promote"))"
    if [[ -n "$set_aside" ]]; then item "the older $REEL moves to $set_aside, kept in case  ($(size_of "$REEL_PATH"))"; fi
  else
    item "$REEL is already the reel  ($(size_of "$REEL_PATH"))"
  fi
fi
if (( ${#clear_lines[@]} )); then
  section "Cleared"
  for l in "${clear_lines[@]}"; do item "$l"; done
fi
if (( ${#leave_lines[@]} )); then
  section "Left for you to decide"
  for l in "${leave_lines[@]}"; do item "$l"; done
fi

# What a re-edit reopens: the clean cut and its transcript here, and (never touched) the job's plans,
# measured placement, cut, word timings, word fixes and graphics sources, each named only when this job has it.
section "Staying, so the reel can be reopened"
for c in ${cuts[@]+"${cuts[@]}"}; do
  item "${c##*/}  (the clean cut, $(size_of "$c"))"
  t="${c##*/}"; t="${t%.mp4}.transcript.json"
  [[ -f "$OUT/$t" ]] && item "$t"
done
if [[ ! -f "$OUT/$CUT" && -f "$OUT/$JOB.transcript.json" ]]; then item "$JOB.transcript.json"; fi
stays() { if [[ -e "$JOBDIR/$1" ]]; then item "$1  ($2)"; fi; }   # stays <path in the job> <what it is>
stays caption-plan.json      "what goes on screen, line by line"
stays graphics-plan.json     "the graphics plan the build reads"
stays graphics-plan.md       "the same plan, for a second pass"
stays shot-plan.json         "which shot plays on which beat"
stays subject-zones.json     "where you sit in frame, measured"
stays transcript/cuts.json   "the cut"
stays transcript/words.json  "every word and its timing"
stays word-fixes.json        "this reel's word fixes"
stays corrections.local.json "this reel's caption fixes"
stays hf-graphics/           "the graphics sources, so any one layer can be re-rendered"

if (( have_reel )); then
  section "Upload copy"
  if (( ! APPLY )) || [[ -d "$DEST" ]]; then item "$DEST/$REEL"; fi
fi

if [[ -z "$pick" && ! -f "$REEL_PATH" ]]; then
  shown_cut="$CUT"
  if [[ ! -f "$OUT/$CUT" ]] && (( ${#cuts[@]} > 0 )); then shown_cut="${cuts[0]##*/}"; fi
  section "No finished pass in outputs/ yet"
  item "Finished it in CapCut? CapCut saved the export wherever you chose. Put that file in projects/$JOB/outputs/"
  item "and run this again."
  item "Posting the clean cut just as it is? Make it the reel with:"
  item "  cp \"$OUT/$shown_cut\" \"$REEL_PATH\""
fi

# ── doing it ────────────────────────────────────────────────────────────────────────────────────────────
echo
if (( ! APPLY )); then
  echo "That was a look; nothing changed. Run it again with --apply to do it."
  exit 0
fi

failed=0
if [[ -n "$promote" ]]; then
  if [[ -n "$set_aside" ]]; then
    mkdir -p "$OUT/earlier-finals" && mv "$REEL_PATH" "$OUT/$set_aside" \
      || { echo "Stopped: the older $REEL could not be set aside, so nothing else was changed."; exit 1; }
  fi
  mv -f "$promote" "$REEL_PATH" \
    || { echo "Stopped: ${promote##*/} could not become $REEL, so nothing else was changed."; exit 1; }
fi
for f in ${clear_files[@]+"${clear_files[@]}"}; do
  rm -f "$f" 2>/dev/null || true
  if [[ -e "$f" ]]; then echo "Could not clear ${f##*/}; it is still in outputs/."; failed=1; fi
done
copied=0
if (( have_reel )); then
  if [[ ! -d "$DEST" ]]; then
    echo "There is no $DEST folder on this machine, so no upload copy was made. The reel is in outputs/."
  elif cp -f "$REEL_PATH" "$DEST/$REEL"; then
    copied=1
  else
    echo "The upload copy could not be written to $DEST. The reel is in outputs/."
  fi
fi

if [[ -f "$REEL_PATH" ]]; then
  echo "Done. The reel to post: projects/$JOB/outputs/$REEL"
  if (( copied )); then echo "Ready to upload: $DEST/$REEL"; fi
  echo
  echo "Before you post, so it stays crisp:"
  echo "  · In the Instagram app, turn on Settings > Data usage and media quality > Upload at highest quality."
  echo "    Many accounts have it off, and then Instagram compresses the video hard; text shows it first."
  echo "  · Watch it on your phone in Instagram and check that no text sits under the buttons or the caption."
  echo
  echo "This job's render caches can go now if you need the space: scripts/free-space.sh $JOB"
else
  echo "No reel was named: outputs/ has no finished pass yet."
fi
exit "$failed"
