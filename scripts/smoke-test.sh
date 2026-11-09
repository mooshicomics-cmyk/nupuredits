#!/usr/bin/env bash
# smoke-test.sh — a fresh-Mac shakedown of the engine's risk points. Run it after setup, or any time you
# want proof the build is healthy on this machine. It checks the things most likely to bite a real buyer:
#   1. the tools it needs are installed
#   2. your style-pack fonts actually resolve (nothing renders in tofu)
#   3. no draft/template points at a path that does not exist on THIS machine (the /Users/creator trap)
#   4. THE BIG ONE — a real render comes out whole, not the short/corrupt file the hardware encoder can
#      occasionally produce (pass a clip to run this; --loops N stresses the encoder to catch the flaky case)
# On ANY major failure it writes a handoff report (with shell alone, so a broken Python still gets one)
# and names the address to email it to.
#
# usage:  scripts/smoke-test.sh [path/to/clip.mov]  [--loops N]
set -uo pipefail

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # lives in scripts/; the engine root is one level up
cd "$ROOT"

CLIP=""; LOOPS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --loops) LOOPS="$2"; shift 2 ;;
    *) CLIP="$1"; shift ;;
  esac
done

FAILURES=(); LOG="$(mktemp)"; PASS=0; TOTAL=0
say(){ echo "$@"; }
ok(){   TOTAL=$((TOTAL+1)); PASS=$((PASS+1)); say "  ✓ $1"; }
bad(){  TOTAL=$((TOTAL+1)); say "  ✗ $1"; FAILURES+=("$1"); }
log(){  echo "$@" >>"$LOG"; }

say "── Reels Editing Engine · smoke test ──"

# ── 1. tools ───────────────────────────────────────────────────────────────
say ""; say "1. Tools"
for tool in ffmpeg ffprobe python3 node; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool present"; else bad "$tool is not installed"; fi
done
if [ -x "$(venv_py "$(venv_home whisperx-venv)")" ]; then ok "WhisperX transcription ready"
elif [ -x "$(venv_py "${REELS_ENGINE_NOFW_VENV:-$(venv_home fasterwhisper-venv)}")" ]; then
  # An Intel Mac builds faster-whisper instead. Reporting that as "not ready" is a false alarm in
  # the one place a buyer goes to find out whether her machine is fine.
  ok "speech transcription ready (faster-whisper — the Intel-Mac engine)"
else say "  · speech transcription will build itself on your first rough cut — nothing to do now"; fi
# config.json is per-machine and not shipped: the editing engine's launcher writes it on first start, and the
# engine's own default is the same port (9001), so a missing one is a normal fresh state, never a failure.
if [ -f product/engine/VectCutAPI/config.json ]; then ok "VectCut config present"
else say "  · VectCut config.json is written the first time the editing engine starts — nothing to do now"; fi

# ── 2. fonts resolve ───────────────────────────────────────────────────────
say ""; say "2. Style-pack fonts"
if [ -f product/capcut_font_doctor.py ]; then
  fd="$(python3 product/capcut_font_doctor.py 2>&1)"; log "$fd"
  if echo "$fd" | grep -qiE "✗|○|missing|not found|not downloaded"; then
    say "  · some pack fonts come from CapCut and download the first time you use them (normal, not an error). Add your pack's font in CapCut once, or it resolves on your first reel. Diagnose anytime: python3 product/capcut_font_doctor.py <YourPack>"
  else ok "all pack fonts resolve"; fi
else bad "capcut_font_doctor.py missing"; fi

# ── 3. no dangling absolute paths in the shipped templates (the /Users/creator trap) ──
say ""; say "3. Template + font-registry paths"
dangle=0
while IFS= read -r p; do
  # any absolute /Users/... MEDIA path a template hardcodes must exist on THIS machine.
  # Font paths (.ttf/.otf) are intentionally skipped: the engine always resolves the real
  # font at build time (build-captions.py / build-graphics.py overwrite it), so a placeholder
  # font path that does not exist is expected, not a broken reference.
  for path in $(grep -oE '/Users/[^"[:space:]]+\.(mov|mp4|png|json)' "$p" 2>/dev/null | sort -u); do
    if [ ! -e "$path" ]; then log "dangling in $p -> $path"; dangle=$((dangle+1)); fi
  done
done < <(find product/creative-vault product/engine/VectCutAPI/template* -name '*.json' 2>/dev/null)
if [ "$dangle" -eq 0 ]; then ok "no template points at a missing path"
else bad "$dangle template path(s) point at files that do not exist on this machine (see report; the /Users/creator trap)"; fi

# ── 4. render integrity — THE BLOCKER (needs a clip) ───────────────────────
say ""; say "4. Render integrity"
if [ -z "$CLIP" ]; then
  say "  (skipped — pass a clip to run it, e.g. scripts/smoke-test.sh inbox/my-clip.mov)"
elif [ ! -f "$CLIP" ]; then
  bad "clip not found: $CLIP"
else
  JOB="smoke-$(date +%s)"; mkdir -p "projects/$JOB/raw"; cp "$CLIP" "projects/$JOB/raw/"
  say "  transcribing + cutting a real render ($LOOPS render pass(es))…"
  bash .claude/skills/rough-cut/scripts/word-timings.sh "projects/$JOB" >>"$LOG" 2>&1
  python3 .claude/skills/rough-cut/scripts/transcript-cut.py "$JOB" >>"$LOG" 2>&1
  badrender=0
  for i in $(seq 1 "$LOOPS"); do
    bash .claude/skills/rough-cut/scripts/stitch-cut.sh "projects/$JOB" >>"$LOG" 2>&1
    out="projects/$JOB/outputs/$JOB.mp4"
    exp="$(python3 -c "import json;d=json.load(open('projects/$JOB/transcript/cuts.json'));s=d if isinstance(d,list) else d['segments'];print(sum(x['end']-x['start'] for x in s))" 2>/dev/null)"
    act="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out" 2>/dev/null)"
    errs="$(ffmpeg -v error -i "$out" -f null - 2>&1 | head -c 200)"
    dur_ok="$(python3 -c "print(1 if abs(float('${act:-0}')-float('${exp:-0}'))<=0.5 else 0)" 2>/dev/null)"
    if [ "$dur_ok" != "1" ] || [ -n "$errs" ]; then
      log "RENDER PASS $i BAD: expected=${exp}s actual=${act}s decode_errors='${errs}'"
      badrender=$((badrender+1))
    fi
  done
  rm -rf "projects/$JOB"
  if [ "$badrender" -eq 0 ]; then ok "render is whole and clean ($LOOPS/$LOOPS good)"
  else bad "render came out short or corrupt on $badrender/$LOOPS pass(es) — the hardware-encoder bug (see report)"; fi
fi

# ── verdict ────────────────────────────────────────────────────────────────
say ""; say "── $PASS/$TOTAL checks passed ──"
if [ "${#FAILURES[@]}" -eq 0 ]; then
  say "✅ Engine looks healthy on this machine."
  rm -f "$LOG"; exit 0
fi
say "⚠ ${#FAILURES[@]} issue(s) found. Writing a handoff report for the engine team."

# The report is written by the shell alone. A broken Python is one of the things this test exists to
# catch, and when the report needed python3 (product/make-handoff.py) the very machine that most needed
# a report got none. Same file name, headings and support address as make-handoff.py, so whoever reads
# it sees the same shape; the machine section is what plain shell tools can tell.

# Home folder out, "~" in: the report is about the machine, and a raw path carries her account name.
# Windows writes the same folder three ways (C:\Users\your-name, C:/Users/your-name, /c/Users/your-name), so each is replaced.
redact_home() {
  local text="$1" f forms=() up tilde="~"
  [ -n "${HOME:-}" ] && [ "$HOME" != / ] && forms+=("$HOME")
  up="${USERPROFILE:-}"
  if [ -n "$up" ]; then
    forms+=("$up" "${up//\\//}")
    case "$up" in ?:*) forms+=("/$(printf '%s' "${up:0:1}" | tr '[:upper:]' '[:lower:]')$(printf '%s' "${up:2}" | tr '\\' '/')") ;; esac
  fi
  for f in ${forms[@]+"${forms[@]}"}; do text="${text//"$f"/$tilde}"; done
  printf '%s' "$text"
}
first_line() { "$@" 2>/dev/null | head -1; }   # first_line <command...>: a tool's version line, or nothing

# The address comes from make-handoff.py, its one home (make-ship.sh keeps it whole in every zip). Read
# with sed, never Python, for the reason above.
SUPPORT_EMAIL="$(sed -n 's/^SUPPORT_EMAIL = "\([^"]*\)".*/\1/p' product/make-handoff.py 2>/dev/null | head -1)"
mkdir -p _handoff
REPORT="_handoff/HANDOFF-smoke-test-$(date +%Y%m%d-%H%M%S).md"
{
  printf '# smoke-test handoff report\n\n'
  printf 'A check failed on a real machine. Claude tries the fix first (/report-a-problem); this goes to the\n'
  printf 'engine team only when it cannot. Nothing here is private beyond your machine specs.\n\n'
  printf '## What failed\n'
  for f in "${FAILURES[@]}"; do printf -- '- %s\n' "$f"; done
  printf '\n## Machine\n'
  printf -- '- **when:** %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')"
  printf -- '- **os:** %s %s\n' "$(uname -s 2>/dev/null)" "$(uname -r 2>/dev/null)"
  printf -- '- **architecture:** %s\n' "$(uname -m 2>/dev/null)"
  if command -v sw_vers >/dev/null 2>&1; then
    printf -- '- **macos_version:** %s\n' "$(sw_vers -productVersion 2>/dev/null)"
    printf -- '- **mac_model:** %s\n' "$(sysctl -n hw.model 2>/dev/null)"
    printf -- '- **chip:** %s\n' "$(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
  fi
  # Whether a Python RAN, from the shim's own verdict: never running python3 here, which on a fresh Mac
  # is the call that opens Apple's developer-tools dialog.
  if [ "${_P3_OK:-0}" = 1 ]; then printf -- '- **python:** runs\n'; else printf -- '- **python:** did not run\n'; fi
  printf -- '- **ffmpeg:** %s\n' "$(first_line ffmpeg -version)"
  printf -- '- **ffprobe:** %s\n' "$(first_line ffprobe -version)"
  printf -- '- **node:** %s\n' "$(first_line node -v)"
  printf -- '- **uv:** %s\n' "$(first_line uv --version)"
  printf -- '- **free_disk:** %s\n' "$(df -Ph . 2>/dev/null | awk 'NR==2{print $4}')"
  printf -- '- **tool_origins:** %s\n' "$(redact_home "$(for t in ffmpeg ffprobe node npx uv python3; do printf '%s=%s ' "$t" "$(command -v "$t" 2>/dev/null)"; done)")"
  if [ -s "$LOG" ]; then
    printf '\n## Log tail\n```\n'
    redact_home "$(tail -c 4000 "$LOG")"
    printf '\n```\n'
  fi
} > "$REPORT"

say ""
say "  ────────────────────────────────────────────────────────"
say "  Something didn't check out. A report is saved here:  $REPORT"
say "  Claude fixes it first (the /report-a-problem steps). It goes to the team at"
say "  ${SUPPORT_EMAIL:-the support address in your welcome email} only if Claude says so."
say "  ────────────────────────────────────────────────────────"
rm -f "$LOG"; exit 1
