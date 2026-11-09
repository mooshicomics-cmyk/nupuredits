#!/usr/bin/env bash
# collect-report.sh — gather ONE pasteable problem report, for ANY problem, not just setup.
#
# Report-only. Installs nothing, changes nothing, needs no password, touches no personal files,
# and never reaches the internet. Safe to run at any time, as many times as you like.
#
#   bash scripts/collect-report.sh            # print the report, and save a copy
#   bash scripts/collect-report.sh --quiet    # save only, print just the file path
#   bash scripts/collect-report.sh --render   # a render problem: also the renderer's own checks and a
#                                             # timed test render (a few minutes; a 1-second test
#                                             # composition in a temp folder, nothing of hers touched)
#
# TWO HALVES. This script answers "is this machine set up?": versions, paths, what is missing. That is
# one kind of problem. The other kind is "it did something wrong" (a render that ran all night, a build
# that says the engine is down), and for that a clean list of versions says nothing. So the report also
# carries what the engine was actually DOING, from product/problem_evidence.py: how far the last renders
# got and how fast, whether any froze, crawled or ran at the same time, what is still running, how much
# memory is free right now, whether the build engine is up. One file either way.
#
# WHY THIS EXISTS: a problem in this engine is almost never "the engine is broken." It is one
# machine-shaped thing — an Intel Mac where Homebrew cannot install, a Windows shell where the tools
# are present but invisible, a CapCut that keeps its drafts somewhere else, a Python that is a decoy.
# Finding out WHICH used to take six rounds of questions, and every round is a message a tired person
# has to answer before anyone can help. This asks the machine instead, once, and hands over the
# answer. The buyer pastes one block. Nobody plays twenty questions.
#
# The report is deliberately boring: versions, presence, and paths. No footage, no keys, no brand kit,
# no transcripts. The one file content it carries is the engine's own code where it was changed on this
# machine (the fixes her Claude made), so a fix found on one machine reaches every buyer. Home folder paths are shortened to ~ so a screenshot or a
# paste into a public channel does not leak a real name.
set -uo pipefail

_d="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$_d" || exit 1

# Repair PATH for THIS process before checking anything, exactly as check-setup.sh does. On Windows
# the tools are usually installed but invisible to a fresh shell, and reporting an installed tool as
# missing would send the report — and whoever reads it — chasing a problem that is not there.
[ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"
[ -f "$_d/scripts/_mac-arch.sh" ]  && . "$_d/scripts/_mac-arch.sh"

QUIET=0; RENDER=0
for _a in "$@"; do
  case "$_a" in
    --quiet)  QUIET=1 ;;
    --render) RENDER=1 ;;
  esac
done
[ "$RENDER" = "1" ] && printf 'Collecting the report, including a short timed test render. This takes a few minutes and changes nothing.\n' >&2

# REPORT_OUT exists for the test (product/tests/test_problem_report.py), so running it on a staged ship
# bundle never leaves a report inside the bundle. Buyers never set it.
OUT="${REPORT_OUT:-$_d/_local/problem-report.md}"
mkdir -p "$(dirname "$OUT")" 2>/dev/null

# tilde <path> — shorten the home folder to ~, so the report can be pasted anywhere safely. On Windows the
# same folder also arrives in Windows spelling (C:\Users\name, from LOCALAPPDATA / APPDATA / USERPROFILE) or
# with forward slashes (C:/Users/your-name); shortening only the Git Bash form (/c/Users/your-name) printed her Windows
# account name in the CapCut lines. Every spelling is replaced, as plain text (no pattern characters).
tilde() {
  local t="${1:-}" tl='~' h
  for h in "$HOME" "${USERPROFILE:-}" "${USERPROFILE//\\//}"; do
    if [ -n "$h" ] && [ "$h" != "/" ]; then t="${t//"$h"/$tl}"; fi
  done
  printf '%s' "$t"
}

# have <tool> — where it resolves, or the word "missing". Never errors, never hangs.
have() {
  _p="$(command -v "$1" 2>/dev/null)"
  if [ -z "$_p" ]; then printf 'missing'
  elif _clt_stub "$_p"; then printf "Apple placeholder only (developer tools not installed, the engine doesn't need them)"
  else tilde "$_p"; fi
}

# _clt_stub <path> — one of Apple's /usr/bin developer-tool placeholders with no tools behind it. On a Mac
# without the Command Line Tools, `git --version` (or /usr/bin/python3) does not answer: it opens Apple's
# "install the developer tools?" dialog. This report runs when she is already stuck, so it must never do
# that, least of all to a buyer whose developer-tools download just failed (scripts/_mac-arch.sh).
_clt_stub() { command -v mac_clt_stub >/dev/null 2>&1 && mac_clt_stub "$1"; }

# ver <tool> <args...> — first line of a version string, or empty. Bounded so nothing can hang.
ver() {
  _vp="$(command -v "$1" 2>/dev/null)" || return 0
  _clt_stub "$_vp" && return 0
  "$@" 2>&1 | head -1 | tr -d '\r'
}

UNAME="$(uname -s 2>/dev/null || echo unknown)"
case "$UNAME" in MINGW*|MSYS*|CYGWIN*) IS_WIN=1 ;; *) IS_WIN=0 ;; esac

# ── the report ──────────────────────────────────────────────────────────────
{
printf '## Problem report\n\n'
printf -- '- **When:** %s\n' "$(date '+%Y-%m-%d %H:%M %Z' 2>/dev/null)"

# Engine version, read without Python (a broken Python is one of the things being reported).
EV="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' product.json 2>/dev/null | head -1)"
HF="$(sed -n 's/.*"hyperframes"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' product.json 2>/dev/null | head -1)"
printf -- '- **Engine version:** %s\n' "${EV:-could not read product.json}"
# Is a newer engine out? Most reports in the launch weeks were bugs already fixed in a later version (2026-10 sweep:
# 2.2.9, 2.2.20, 2.2.26 reporting what 2.2.24 / 2.3.1 had fixed). The report says so on its own line, so the fix
# is /update, not a support email. One quick look, curl only; no answer just means it couldn't tell.
_ver_newer() {   # 0 when $1 is a newer version than $2
  local IFS=. i=0 x y; local -a a b; a=($1); b=($2)
  while [ "$i" -lt "${#a[@]}" ] || [ "$i" -lt "${#b[@]}" ]; do
    x="${a[$i]:-0}"; y="${b[$i]:-0}"; x=$((10#${x%%[!0-9]*})); y=$((10#${y%%[!0-9]*}))
    [ "$x" -gt "$y" ] && return 0; [ "$x" -lt "$y" ] && return 1; i=$((i + 1))
  done
  return 1
}
_UURL="$(grep -oE '"update_url"[[:space:]]*:[[:space:]]*"[^"]+"' product.json 2>/dev/null | sed -E 's/.*"([^"]+)".*/\1/')"
_NEWEST=""
[ -n "$_UURL" ] && command -v curl >/dev/null 2>&1 && \
  _NEWEST="$(curl -fsSL --max-time 4 "${_UURL%/}/latest.json" 2>/dev/null | grep -oE '"version"[[:space:]]*:[[:space:]]*"[0-9][0-9.]*"' | grep -oE '[0-9][0-9.]*' | head -1)"
if [ -n "$_NEWEST" ] && [ -n "$EV" ] && _ver_newer "$_NEWEST" "$EV"; then
  printf -- '- **Newer engine out:** v%s. THIS ENGINE IS BEHIND: run /update first, then try again; most problems are already fixed there\n' "$_NEWEST"
elif [ -n "$_NEWEST" ]; then
  printf -- '- **Newest engine:** v%s (this one is up to date)\n' "$_NEWEST"
else
  printf -- '- **Newest engine:** could not check just now\n'
fi
[ -n "$HF" ] && printf -- '- **HyperFrames:** %s\n' "$HF"
printf -- '- **Folder:** %s\n' "$(tilde "$_d")"

# ── machine ─────────────────────────────────────────────────────────────────
printf '\n### Machine\n\n'
if [ "$IS_WIN" = "1" ]; then
  printf -- '- **Computer:** Windows (Git Bash: %s)\n' "$UNAME"
  printf -- '- **Windows version:** %s\n' "$(cmd //c ver 2>/dev/null | tr -d '\r' | tr -s ' ' | sed '/^$/d' | head -1)"
  # The two settings that break CapCut drafts on Windows if they are off.
  LP="$(reg query 'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem' //v LongPathsEnabled 2>/dev/null | sed -n 's/.*0x\([0-9]\).*/\1/p' | head -1)"
  case "${LP:-}" in
    1) printf -- '- **Long paths:** on\n' ;;
    0) printf -- '- **Long paths:** OFF (CapCut draft folders nest deep, this matters)\n' ;;
    *) printf -- '- **Long paths:** could not read\n' ;;
  esac
  printf -- '- **PYTHONUTF8:** %s · **PYTHONIOENCODING:** %s\n' \
    "${PYTHONUTF8:-(empty)}" "${PYTHONIOENCODING:-(empty)}"
  # The python3 decoy: on PATH, looks installed, only opens the Microsoft Store.
  D="$(python3 -c 'print(1)' 2>&1 | head -1 | tr -d '\r')"
  case "$D" in
    1) printf -- '- **python3:** real\n' ;;
    '') printf -- '- **python3:** not found\n' ;;
    *) printf -- '- **python3:** DECOY (said: %s)\n' "$D" ;;
  esac
else
  CLASS="$(mac_arch_class 2>/dev/null)"
  printf -- '- **Computer:** Mac (%s)\n' "${CLASS:-unknown}"
  printf -- '- **macOS:** %s\n' "$(sw_vers -productVersion 2>/dev/null)"
  printf -- '- **Chip:** %s\n' "$(mac_cpu_brand 2>/dev/null)"
  case "${CLASS:-}" in
    intel)   printf -- '- **Note:** true Intel Mac. Homebrew cannot install here; this engine uses its own route.\n' ;;
    rosetta) printf -- '- **Note:** Apple Silicon running under Rosetta. Untick "Open using Rosetta" and the normal path works.\n' ;;
  esac
  printf -- '- **Install route:** %s%s\n' "$(mac_install_route 2>/dev/null)" \
    "$(mac_route_pinned 2>/dev/null && printf ' (pinned: Apple developer tools download failed, Homebrew skipped)')"
fi
printf -- '- **Free disk:** %s\n' "$(df -h "$_d" 2>/dev/null | awk 'NR==2{print $4" free of "$2" ("$5" used)"}')"

# ── tools ───────────────────────────────────────────────────────────────────
printf '\n### Tools\n\n'
printf '| Tool | Where | Version |\n|---|---|---|\n'
for t in node npx ffmpeg ffprobe uv git; do
  case "$t" in
    node)           V="$(ver node -v)" ;;
    npx)            V="$(ver npx -v)" ;;
    ffmpeg|ffprobe) V="$(ver "$t" -version | sed 's/ Copyright.*//')" ;;
    uv)             V="$(ver uv --version)" ;;
    git)            V="$(ver git --version)" ;;
  esac
  printf '| %s | %s | %s |\n' "$t" "$(have "$t")" "${V:-—}"
done

# Python through the engine's own resolver, which knows both the Windows decoy and Apple's
# placeholder. `--check` is REPORT-ONLY: it exits 3 and installs nothing when there is no Python.
# That flag is not optional here — a report that installs a Python behind someone's back while she
# is trying to tell us something is broken would be its own bug.
PY=""
if [ -f "$_d/scripts/ensure-python.sh" ]; then
  PY="$(bash "$_d/scripts/ensure-python.sh" --check 2>/dev/null | tail -1)"
  case "$PY" in *' '*|*'No working Python'*) PY="" ;; esac
fi
[ -z "$PY" ] && PY="$(command -v python 2>/dev/null || command -v python3 2>/dev/null)"
_clt_stub "$PY" && PY=""
if [ -n "$PY" ] && "$PY" -c 'print(1)' >/dev/null 2>&1; then
  printf '| python | %s | %s |\n' "$(tilde "$PY")" "$("$PY" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null)"
else
  printf '| python | not usable yet | — |\n'
fi
printf '| bash | %s | %s |\n' "$(have bash)" "${BASH_VERSION:-—}"

# ── CapCut ──────────────────────────────────────────────────────────────────
printf '\n### CapCut\n\n'
if [ "$IS_WIN" = "1" ]; then
  CC_ROOTS="$LOCALAPPDATA/CapCut/User Data/Projects/com.lveditor.draft
$APPDATA/CapCut/User Data/Projects/com.lveditor.draft
$_d/projects/_capcut-staging/com.lveditor.draft"
else
  CC_ROOTS="$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft
$_d/projects/_capcut-staging/com.lveditor.draft"
fi
CC_FOUND=0
while IFS= read -r r; do
  [ -z "$r" ] && continue
  if [ -d "$r" ]; then
    CC_FOUND=1
    printf -- '- **Draft folder:** %s\n' "$(tilde "$r")"
    printf -- '- **Drafts in it:** %s\n' "$(find "$r" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
    NEW="$(ls -t "$r" 2>/dev/null | head -1)"
    [ -n "$NEW" ] && printf -- '- **Most recent draft:** %s\n' "$NEW"
  fi
done <<EOF
$CC_ROOTS
EOF
[ "$CC_FOUND" = "0" ] && printf -- '- **Draft folder:** not found yet (normal if CapCut has never been opened)\n'
# A Microsoft Store Claude app hides new files it writes into CapCut's folder from CapCut (MSIX redirect); the
# engine then builds drafts in projects/_capcut-staging/ and runs "Add to CapCut.bat" for her (or she does).
# On a Mac a security app's protected-folders shield can refuse the engine's own Python any write in ~/Movies;
# the same staging route then applies, with "Add to CapCut.command". The script answers either question in one
# line. On a Mac it asks by making one hidden folder directly in ~/Movies and removing it at once (never
# inside CapCut's folder), and remembers a refusal the way a draft build would. Its line carries the engine's
# folder, so it is shortened to ~ like every other path here.
if [ -n "$PY" ] && [ -f "$_d/product/capcut_store_redirect.py" ]; then
  if [ "$IS_WIN" = "1" ]; then _rl='Store-app redirect'; else _rl='Movies-folder redirect'; fi
  printf -- '- **%s:** %s\n' "$_rl" "$(tilde "$("$PY" "$_d/product/capcut_store_redirect.py" 2>/dev/null | head -1)")"
  # The engine's last automatic "Add to CapCut" (status and reason only, never project names). Windows only.
  _ar="$_d/projects/_capcut-staging/.auto-result.json"
  if [ "$IS_WIN" = "1" ] && [ -f "$_ar" ]; then
    printf -- '- **Last automatic Add to CapCut:** %s\n' "$("$PY" -c 'import json,sys,time; r=json.load(open(sys.argv[1],encoding="utf-8")); print(r.get("status"), r.get("reason") or "", time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("at") or 0)))' "$_ar" 2>/dev/null)"
  fi
fi
if [ "$IS_WIN" = "0" ]; then
  APP="/Applications/CapCut.app/Contents/Info.plist"
  if [ -f "$APP" ]; then
    printf -- '- **App version:** %s\n' "$(defaults read /Applications/CapCut.app/Contents/Info CFBundleShortVersionString 2>/dev/null)"
  else
    printf -- '- **App:** not in /Applications\n'
  fi
fi

# ── setup check ─────────────────────────────────────────────────────────────
# check-setup.sh is the engine's own report-only prerequisite check. Its summary lines are the
# fastest read of whether this is a setup problem or a real bug, so they ride along.
if [ -x "$_d/check-setup.sh" ] || [ -f "$_d/check-setup.sh" ]; then
  printf '\n### Setup check\n\n```\n'
  _cs="$(bash "$_d/check-setup.sh" 2>&1 | tail -25; printf x)"   # the x keeps its trailing blank lines
  tilde "${_cs%x}"
  printf '```\n'
fi

# ── engine state ────────────────────────────────────────────────────────────
printf '\n### Engine state\n\n'
printf -- '- **Footage waiting in inbox:** %s file(s)\n' \
  "$(find "$_d/inbox" -maxdepth 2 -type f ! -name '.*' ! -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
LASTP="$(ls -t "$_d/projects" 2>/dev/null | head -1)"
printf -- '- **Most recent project:** %s\n' "${LASTP:-none yet}"
if [ -n "$LASTP" ]; then
  printf -- '- **Last touched:** %s\n' "$(date -r "$_d/projects/$LASTP" '+%Y-%m-%d %H:%M' 2>/dev/null)"
fi
printf -- '- **Homebase:** %s\n' \
  "$(if [ ! -f "$_d/brand-kit.md" ]; then echo 'not created yet'; \
     elif [ "$(grep -e '{{' -e '<<' "$_d/brand-kit.md" 2>/dev/null | grep -v -c -F '{{this}}')" -gt 0 ]; then echo 'NOT personalized (setup never finished)'; \
     else echo 'personalized'; fi)"
[ -f "$_d/_local/install-route.json" ] && printf -- '- **Install route recorded:** yes\n'
# Every time a step took its backup route to finish her edit (word-timings.sh note_fallback), newest last.
if [ -s "$_d/_local/fallbacks.log" ]; then
  printf -- '- **Backup routes the engine took to finish an edit:**\n'
  tilde "$(tail -n 10 "$_d/_local/fallbacks.log" | sed 's/^/  - /')"
  printf '\n'
fi
# What this computer learned works, so later reels go straight there (product/fallbacks.py remember). Paths in
# it are shortened like the rest.
# The Brand Kit add-on (a separate download) keeps its last error: the error and where it happened only, never what she typed.
if [ -s "$_d/_local/brand-kit/last-error.txt" ]; then
  printf -- '- **Brand Kit, last error:**\n'
  tilde "$(tail -n 3 "$_d/_local/brand-kit/last-error.txt" | sed 's/^/  - /')"
fi
if [ -s "$_d/_local/pivots.json" ] && [ -n "$PY" ] && "$PY" -c 'print(1)' >/dev/null 2>&1; then
  printf -- '- **Routes this computer now takes first:**\n'
  tilde "$("$PY" "$_d/product/fallbacks.py" list 2>/dev/null | sed 's/^/  - /')"
  printf '\n'
fi

# ── what the engine was doing ───────────────────────────────────────────────
# The evidence half (see the header). Uses the Python resolved above, never a bare python3, which on
# Windows can be the Microsoft Store decoy. Without a working Python, say so and keep the rest.
printf '\n'
if [ -n "$PY" ] && "$PY" -c 'print(1)' >/dev/null 2>&1 && [ -f "$_d/product/problem_evidence.py" ]; then
  if [ "$RENDER" = "1" ]; then
    "$PY" "$_d/product/problem_evidence.py" --render 2>/dev/null
  else
    "$PY" "$_d/product/problem_evidence.py" 2>/dev/null
  fi
else
  printf '### What the engine was doing\n\n- could not look: no working Python yet (see Tools above)\n'
fi

# ── changes her Claude made to the engine ───────────────────────────────────
# A fix her Claude made on this machine used to stay on this machine. This carries each changed engine file and
# the exact change (engine files only; see keep_changes.report_section), home folder shortened like the rest.
printf '\n'
if [ -n "$PY" ] && "$PY" -c 'print(1)' >/dev/null 2>&1 && [ -f "$_d/product/keep_changes.py" ]; then
  _kc="$("$PY" "$_d/product/keep_changes.py" --report 2>/dev/null; printf x)"
  tilde "${_kc%x}"
else
  printf '### Changes made to this engine\n\n- could not look: no working Python yet (see Tools above)\n'
fi

# ── the visual editor (early access) ────────────────────────────────────────
# Only where the editor is switched on (product/early_access.py). Its errors are written down as they happen, even
# the ones she never saw (product/editor_errors.py), so a tester's report carries what actually broke.
if [ -n "$PY" ] && "$PY" -c 'print(1)' >/dev/null 2>&1 && [ -f "$_d/product/editor_errors.py" ] \
   && "$PY" "$_d/product/early_access.py" >/dev/null 2>&1; then
  printf '\n'
  _ve="$("$PY" "$_d/product/editor_errors.py" --report 2>/dev/null; printf x)"
  tilde "${_ve%x}"
fi
# The last cut update the editor ran on the newest reel ("Send my cut" runs it in the background, where its output
# used to go nowhere): the end of its log shows a hang or the real error.
if [ -n "$LASTP" ] && [ -f "$_d/projects/$LASTP/review/last-stitch.log" ]; then
  printf '\n**Last cut update (%s, end of review/last-stitch.log):**\n\n```\n' "$LASTP"
  tilde "$(tail -n 25 "$_d/projects/$LASTP/review/last-stitch.log" 2>/dev/null)"
  printf '\n```\n'
fi

printf '\n### What happened\n\n'
printf -- '_Claude fills this in: what she was doing, which step, and the error in her own words._\n'
} > "$OUT" 2>/dev/null

if [ "$QUIET" = "1" ]; then
  printf '%s\n' "$OUT"
else
  cat "$OUT"
  printf '\n---\nSaved a copy to: %s\n' "$(tilde "$OUT")"
fi
