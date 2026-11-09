#!/bin/bash

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

# Bake: read HOOK-MAP.tsv from the WORKING FOLDER, bake each clip's hook (+ optional accent turn)
# onto its finished b-roll, IG-safe placement, output post-ready reels to <workdir>/clips-final/.
# Idempotent (skips already-built). Columns: clip \t hook \t aside \t keyword \t pos
#
# USAGE:  PACK=Butter build-all.sh [WORKDIR]
#   WORKDIR = the buyer's per-run b-roll folder (holds clips/ + HOOK-MAP.tsv). Defaults to the
#   current directory, so you can also just `cd` into the working folder and run it. The skill's
#   tools stay put; they are referenced by their own path, never copied into the buyer's folder.
#
# STYLE PACK (REQUIRED): the hook text uses the buyer's chosen Edit Engine style pack. Two ways:
#   1. Pack name (turnkey):   PACK=Butter build-all.sh "$WORK"
#      -> resolve-pack.py reads product/creative-vault/style-packs.json and sets the fonts.
#   2. Explicit fonts:        HEADLINE_FONT=... ACCENT_FONT=... TEXT_COLOR=... build-all.sh "$WORK"
#      (for matching a specific style outside the packs). NO fonts ship with this skill.
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKDIR="${1:-$PWD}"
cd "$WORKDIR" || { echo "build-all: cannot cd to WORKDIR '$WORKDIR'" >&2; exit 1; }
if [ ! -f HOOK-MAP.tsv ]; then
  echo "build-all: no HOOK-MAP.tsv in '$WORKDIR' — is this the buyer's working folder?" >&2; exit 1
fi
if [ -n "$PACK" ] && [ -z "$HEADLINE_FONT" ]; then
  if ! eval "$(python3 "$SKILL_DIR/resolve-pack.py" "$PACK")"; then
    echo "build-all: could not resolve pack '$PACK'. Try: python3 $SKILL_DIR/resolve-pack.py --list" >&2
    exit 1
  fi
fi
if [ -z "$HEADLINE_FONT" ]; then
  echo "build-all: no style resolved. Set PACK=<name> (turnkey) or export HEADLINE_FONT/ACCENT_FONT/TEXT_COLOR." >&2
  echo "  Available packs: $(python3 "$SKILL_DIR/resolve-pack.py" --list 2>&1)" >&2
  exit 1
fi
ACCENT_FONT="${ACCENT_FONT:-$HEADLINE_FONT}"
TEXT_COLOR="${TEXT_COLOR:-#ffffff}"
# --pos auto finds the face with OpenCV. Setup puts none in python3, so the baker borrows uv's for the face
# check (the text itself is still drawn by this python3). With neither there, every hook goes to the top:
# say so once, plainly, rather than on every clip.
if ! python3 -c "import cv2" >/dev/null 2>&1 && ! command -v uv >/dev/null 2>&1; then
  echo "build-all: uv is not installed, so hooks go at the top without the face check. Run ./check-setup.sh to add uv, then bake again to place them around faces." >&2
fi
mkdir -p clips-final
n=0; built=0; skip=0; miss=0; fail=0
# `|| [ -n "$clip" ]`: a HOOK-MAP whose last row has no trailing newline still bakes that row
while IFS=$'\t' read -r clip hook aside keyword pos || [ -n "$clip" ]; do
  [ "$clip" = "clip" ] && continue
  [ -z "$clip" ] && continue
  # Find the source under ANY common video extension, not just .mp4 — real phone footage is often .mov.
  # If it isn't already .mp4, remux to .mp4 losslessly (container change only, -c copy), so the rest of the
  # pipeline (bake, captions, posting) keeps its .mp4 assumption. (round 14 bug)
  src="clips/${clip}.mp4"
  if [ ! -f "$src" ]; then
    for ext in mov MOV MP4 m4v M4V mp4; do
      if [ -f "clips/${clip}.${ext}" ]; then
        if [ "$ext" = "mp4" ]; then src="clips/${clip}.mp4"
        else ffmpeg -nostdin -y -loglevel error -i "clips/${clip}.${ext}" -c copy -map 0 "$src" \
               || ffmpeg -nostdin -y -loglevel error -i "clips/${clip}.${ext}" -c:v libx264 -crf 18 -an "$src"; fi
        break
      fi
    done
  fi
  out="clips-final/${clip}-FINAL.mp4"
  n=$((n+1))
  [ -z "$pos" ] && pos="auto"
  if [ ! -f "$src" ]; then echo "MISSING SRC: clips/${clip}.{mp4,mov,...} (no source clip found)"; miss=$((miss+1)); continue; fi
  if [ -f "$out" ]; then skip=$((skip+1)); continue; fi
  if [ "$aside" = "-" ] || [ -z "$aside" ]; then
    python3 "$SKILL_DIR/bake-hook.py" "$src" "$out" "$hook" --pos "$pos" \
      --headline-font "$HEADLINE_FONT" --accent-font "$ACCENT_FONT" --color "$TEXT_COLOR" \
      && built=$((built+1)) || { fail=$((fail+1)); echo "BAKE FAILED: $clip"; }
  else
    python3 "$SKILL_DIR/bake-hook.py" "$src" "$out" "$hook" --aside "$aside" --pos "$pos" \
      --headline-font "$HEADLINE_FONT" --accent-font "$ACCENT_FONT" --color "$TEXT_COLOR" \
      && built=$((built+1)) || { fail=$((fail+1)); echo "BAKE FAILED: $clip"; }
  fi
done < HOOK-MAP.tsv
echo "---- built $built new, skipped $skip existing, $miss missing, $fail FAILED, of $n rows ----"
echo "clips-final now holds: $(ls -1 clips-final 2>/dev/null | wc -l)"
# fail loudly: a green exit must mean reels actually baked (a missing pack font errors every clip)
if [ "$fail" -gt 0 ]; then
  echo "build-all: $fail clip(s) failed to bake. Most common cause: the pack's font file isn't present." >&2
  echo "  The baker needs the actual font FILE. If it's a restricted/CapCut font, add it in CapCut once" >&2
  echo "  (it then resolves from your CapCut fonts), or drop the .ttf/.otf in assets/fonts/." >&2
  exit 2
fi
[ "$built" -eq 0 ] && [ "$skip" -eq 0 ] && { echo "build-all: nothing baked (0 of $n)." >&2; exit 2; }
exit 0
