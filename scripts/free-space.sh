#!/usr/bin/env bash
# free-space.sh: gives back the drive space a job's renders take up, once she no longer needs them on hand.
#
# It clears only what the engine can make again, exactly as it was, from what stays in the job folder:
#   <composition>/renders/      what a HyperFrames composition rendered. The composition (its index.html or
#                               hyperframes.json) sits right beside it, or it is the job's hf-graphics/renders/,
#                               so `product/reel_render.py render <composition>` brings any of it back
#   render scratch              the frame folders a render leaves next to its output when it stops early:
#                               work-<id>-* holding HyperFrames' captured-frames/, compiled/ or
#                               capture-calibration/, and <output>.assemble-work-*
#   node_modules/               only beside a package.json, which npm installs it from again
#   hf-graphics/_looks/<line>/<look>/
#                               a look she tried on a line in the visual editor and didn't keep: the page draws
#                               it again in seconds if she opens Swap there. A look in use (review/swaps.json)
#                               anything she refined by hand (refined-*, _refine) and a look she moved (_original) always stay
# Everything else in a job is never looked at: raw/ (and raw-*/), outputs/, the plans, transcripts, audio,
# b-roll, cutouts, every composition's own files and the layer .movs in hf-graphics/. The CapCut staging
# folder is not a job and is never entered. Anything a CapCut draft still plays from by its path stays too.
#
#   scripts/free-space.sh                     # every job: what could come back (removes nothing)
#   scripts/free-space.sh <job> [<job> ...]   # only these jobs
#   scripts/free-space.sh [<job> ...] --apply # remove it
#
# Exit 0 after a sweep (also when some item could not be read or removed: it is named and left as it is);
# 1 when there is no projects/ folder or a named job does not exist; 2 for an option it does not know.

set -euo pipefail

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"   # scripts/ sits one level under the engine
PROJECTS="$ENGINE/projects"
STAGING="_capcut-staging"   # drafts waiting for "Add to CapCut", never a job

usage() { echo "usage: scripts/free-space.sh [<job> ...] [--apply]"; }

APPLY=0
NAMED=()
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "free-space.sh does not know the option $arg."; usage; exit 2 ;;
    *) NAMED+=("$arg") ;;
  esac
done

if [[ ! -d "$PROJECTS" ]]; then
  echo "There is no projects/ folder at $PROJECTS, so there is nothing to clear."
  exit 1
fi

# The jobs to look in: the ones named, or every folder in projects/.
JOBS=()
for name in ${NAMED[@]+"${NAMED[@]}"}; do
  if [[ "$name" == "$STAGING" ]]; then
    echo "projects/$STAGING holds CapCut drafts waiting to be added, not a job, so nothing in it is cleared."
    exit 1
  fi
  if [[ -z "$name" || "$name" == */* || "$name" == "." || "$name" == ".." || ! -d "$PROJECTS/$name" ]]; then
    echo "There is no job called '$name' in projects/."
    exit 1
  fi
  JOBS+=("$name")
done
if (( ${#NAMED[@]} == 0 )); then
  while IFS= read -r d; do
    name="${d##*/}"
    [[ "$name" == "$STAGING" || "$name" == .* ]] && continue
    JOBS+=("$name")
  done < <(find "$PROJECTS" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort)
fi

# ── sizes ───────────────────────────────────────────────────────────────────────────────────────────────
human() {   # human <kilobytes>
  awk -v k="$1" 'BEGIN {
    if (k < 1024) printf "%d KB", k
    else if (k < 1048576) printf "%.1f MB", k / 1024
    else printf "%.2f GB", k / 1048576 }'
}

# ── files a CapCut draft still plays from ───────────────────────────────────────────────────────────────
# A draft the engine builds carries its own copy of every clip, but a draft can also point straight at a file
# in a job folder (an older build, or one she pieced together by hand). Whatever such a path sits in stays, so
# clearing space never leaves a draft with missing media. Paths are read from each draft's timeline JSON in
# every place CapCut keeps drafts on this machine, Windows' C:/... spelled the way Git Bash spells it.
unix_path() {   # unix_path <path>: C:\x or C:/x  ->  /c/x (Git Bash); anything else unchanged
  awk '{ gsub(/\\\\|\\/, "/"); if (match($0, /^[A-Za-z]:\//)) $0 = "/" tolower(substr($0, 1, 1)) substr($0, 3); print }' <<<"$1"
}
draft_roots() {
  if [[ -n "${CAPCUT_DRAFTS_ROOT:-}" ]]; then unix_path "$CAPCUT_DRAFTS_ROOT"; fi
  printf '%s\n' "$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft"
  if [[ -n "${LOCALAPPDATA:-}" ]]; then printf '%s\n' "$(unix_path "$LOCALAPPDATA")/CapCut/User Data/Projects/com.lveditor.draft"; fi
  printf '%s\n' "$PROJECTS/$STAGING/com.lveditor.draft"
}
LINKED=""
while IFS= read -r root; do
  [[ -d "$root" ]] || continue
  while IFS= read -r p; do
    p="$(unix_path "$p")"
    case "$p" in "$PROJECTS"/*) LINKED="$LINKED$p"$'\n' ;; esac
  done < <(find "$root" -mindepth 2 -maxdepth 2 -type f \( -name 'draft_info.json' -o -name 'draft_content.json' \) \
             -exec grep -ho '"path" *: *"[^"]*"' {} + 2>/dev/null | sed 's/^"path" *: *"//; s/"$//' | grep -F '/projects/' || true)
done < <(draft_roots)
draft_plays_from() {   # draft_plays_from <dir>: does any draft use a file inside it?
  [[ -n "$LINKED" ]] && grep -qF -- "$1/" <<<"$LINKED"
}

# ── what can be made again ──────────────────────────────────────────────────────────────────────────────
# Prints why <dir> can go, or fails when it cannot be proved to come back. <rel> is the path inside its job.
remakeable() {   # remakeable <dir> <rel>
  local dir="$1" rel="$2" parent name
  parent="$(dirname "$dir")"; name="${dir##*/}"
  case "$name" in
    renders)
      if [[ -f "$parent/index.html" || -f "$parent/hyperframes.json" || "${parent##*/}" == hf-graphics ]]; then
        echo "render output beside its composition, which renders it again"; return 0
      fi ;;
    node_modules)
      if [[ -f "$parent/package.json" ]]; then echo "npm installs it again from the package.json beside it"; return 0; fi ;;
    *.assemble-work-*)
      echo "pieces of a render that stopped while it was being joined"; return 0 ;;
    work-*-*)
      if [[ -d "$dir/captured-frames" || -d "$dir/compiled" || -d "$dir/capture-calibration" ]]; then
        echo "frames from a render that stopped early"; return 0
      fi ;;
  esac
  return 1
}

# ── the sweep, one job at a time ────────────────────────────────────────────────────────────────────────
# find lists a folder before what is inside it, so once a folder is on the list (or set aside), nothing
# under it is weighed again: every kilobyte is counted once.
under_taken() {   # under_taken <dir>   (reads $taken: one listed folder per line, each ending in /)
  local t
  while IFS= read -r t; do
    [[ -n "$t" ]] || continue
    case "$1/" in "$t"*) return 0 ;; esac
  done <<<"$taken"
  return 1
}
total_kb=0
items=0
problems=0

sweep_job() {   # sweep_job <job>
  local job="$1" root="$PROJECTS/$1" dir rel why kb taken="" lines="" job_kb=0 left
  local -a found=() reasons=() sizes=()
  # raw*/ and outputs/ are cut off before find ever enters them: footage and finished reels are not candidates.
  # find runs inside the job folder, so a job name holding [ ] or * is never read as a pattern.
  while IFS= read -r rel; do
    rel="${rel#./}"; dir="$root/$rel"
    if under_taken "$dir"; then continue; fi                      # inside something already on the list
    why="$(remakeable "$dir" "$rel")" || continue
    if draft_plays_from "$dir"; then
      lines="$lines$(printf '  %10s  %s/  · stays: a CapCut draft still plays a file from here' "kept" "$rel")"$'\n'
      taken="$taken"$'\n'"$dir/"
      continue
    fi
    if ! kb="$(du -sk "$dir" 2>/dev/null | cut -f1)" || [[ -z "$kb" ]]; then
      lines="$lines$(printf '  %10s  %s/  · stays: part of it could not be read' "?" "$rel")"$'\n'
      taken="$taken"$'\n'"$dir/"
      problems=$((problems + 1))
      continue
    fi
    found+=("$dir"); reasons+=("$why"); sizes+=("$kb")
    taken="$taken"$'\n'"$dir/"
    job_kb=$((job_kb + kb))
  done < <(cd "$root" && find . \( -path ./raw -o -path './raw-*' -o -path ./outputs \) -prune -o \
             -type d \( -name renders -o -name node_modules -o -name 'work-*' -o -name '*.assemble-work-*' \) -print \
             2>/dev/null | LC_ALL=C sort)
  # looks she tried in the visual editor and didn't keep (the ones in use are named in review/swaps.json)
  if [[ -d "$root/hf-graphics/_looks" ]] && { [[ ! -e "$root/review/swaps.json" ]] || [[ -r "$root/review/swaps.json" ]]; }; then
    local inuse=""
    [[ -e "$root/review/swaps.json" ]] && inuse="$(cat "$root/review/swaps.json")"
    while IFS= read -r rel; do
      rel="${rel#./}"; dir="$root/$rel"
      case "/$rel/" in */_refine/*|*/refined-*|*/_original/*) continue ;; esac
      grep -qF -e "\"$rel/" -e "\"$rel\"" <<<"$inuse" && continue
      draft_plays_from "$dir" && continue
      kb="$(du -sk "$dir" 2>/dev/null | cut -f1)" || continue
      [[ -n "$kb" ]] || continue
      found+=("$dir"); reasons+=("a look tried in the visual editor and not kept; Swap draws it again"); sizes+=("$kb")
      job_kb=$((job_kb + kb))
    done < <(cd "$root" && find ./hf-graphics/_looks -mindepth 2 -maxdepth 2 -type d 2>/dev/null | LC_ALL=C sort)
  fi
  [[ ${#found[@]} -eq 0 && -z "$lines" ]] && return 0

  echo
  if (( APPLY )); then echo "$job"; else echo "$job: $(human "$job_kb") can come back"; fi
  printf '%s' "$lines"
  local i=0
  for dir in ${found[@]+"${found[@]}"}; do
    printf '  %10s  %s/  · %s\n' "$(human "${sizes[$i]}")" "${dir#"$root"/}" "${reasons[$i]}"
    kb="${sizes[$i]}"
    if (( APPLY )); then
      rm -rf "$dir" 2>/dev/null || true
      if [[ -e "$dir" ]]; then
        left="$(du -sk "$dir" 2>/dev/null | cut -f1)"; left="${left:-$kb}"
        echo "              could not remove all of it; what is left stays where it is"
        kb=$((kb - left)); (( kb < 0 )) && kb=0
        problems=$((problems + 1))
      fi
    fi
    total_kb=$((total_kb + kb)); items=$((items + 1)); i=$((i + 1))
  done
}

if (( ${#NAMED[@]} )); then echo "Looking in: ${NAMED[*]}"; else echo "Looking in every job in projects/"; fi
for job in ${JOBS[@]+"${JOBS[@]}"}; do sweep_job "$job"; done

echo
if (( problems )); then echo "$problems item(s) could not be read or removed in full; they were left as they are."; fi
if (( items == 0 )); then
  echo "Nothing to clear. What is here is footage, finished reels, or what a rebuild needs."
elif (( APPLY )); then
  echo "Removed $items item(s): $(human "$total_kb") is free again."
else
  echo "Nothing was removed: this was a look. $(human "$total_kb") in $items item(s) can come back."
  echo "To clear it, run the same command with --apply."
fi
exit 0
