#!/usr/bin/env bash
# ensure-python.sh — print the path of a Python that actually runs. If this computer has none, get one.
#
#   PY="$(bash scripts/ensure-python.sh)" && "$PY" scripts/apply-update.py --check
#   bash scripts/ensure-python.sh --check      # report only: exit 0 + path, or exit 3 and install nothing
#
# WHY THIS EXISTS. The updater (scripts/apply-update.py) is written in Python, and a brand-new Mac has no
# Python: /usr/bin/python3 is Apple's placeholder, which opens the "install the developer tools?" dialog
# instead of running. So on a fresh machine "update me" could never run, and the ONE fix a stuck machine
# needed (a setup route for its chip) was sitting on the update feed with no way to reach it. Measured on a
# tester's fresh Intel Mac, 2026-09-18: two rounds of instructions, a dialog nobody asked for, no update.
#
# WHAT IT DOES. Finds a working Python the way every engine script does (scripts/_python3-shim.sh), and when
# there is none, installs a private one through uv: uv's own installer lands in ~/.local/bin, then
# `uv python install 3.11 --default` puts a real python3 beside it. No Homebrew, no Apple developer
# tools, no password, no admin account, about two minutes, and it is the same interpreter the Intel-Mac
# setup route installs anyway (product/INTEL-MAC-ROUTE.md), so nothing is installed twice later.
#
# stdout carries ONLY the interpreter path (so it can be captured); every message goes to stderr.
# Exit codes: 0 found or installed · 3 none and --check/ENGINE_NO_BOOTSTRAP=1 · 4 uv could not be
# installed · 5 Python could not be installed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
say() { printf '%s\n' "$*" >&2; }

# The two shims every engine script already uses. The python3 shim goes FIRST: it knows Apple's
# placeholder by path and never executes it, and it searches the real on-disk homes itself, so it does
# not need PATH repaired to find a Python. The PATH shim then only serves the uv lookup below.
[ -f "$ROOT/scripts/_python3-shim.sh" ] && . "$ROOT/scripts/_python3-shim.sh" 2>/dev/null
[ -f "$ROOT/scripts/_path-shim.sh" ]    && . "$ROOT/scripts/_path-shim.sh"    2>/dev/null

# Windows answers with a drive-letter path; the shell wants the POSIX form (see _path-shim.sh).
_ep_posix() {
  case "$1" in
    *:*) command -v cygpath >/dev/null 2>&1 && cygpath -u "$1" 2>/dev/null || printf '%s' "$1" ;;
    *)   printf '%s' "$1" ;;
  esac
}

if [ "${_P3_OK:-0}" -eq 1 ]; then
  _p="$(python3 -c 'import sys; print(sys.executable)' 2>/dev/null || true)"
  if [ -n "$_p" ]; then
    printf '%s\n' "$(_ep_posix "$_p")"
    exit 0
  fi
fi

case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
  Darwin)               OS=mac ;;
  *)                    OS=other ;;
esac

if [ "$CHECK" -eq 1 ] || [ "${ENGINE_NO_BOOTSTRAP:-0}" = "1" ]; then
  say "No working Python on this computer yet. (Report-only run: nothing was installed.)"
  exit 3
fi

# ── 1. uv ────────────────────────────────────────────────────────────────────
# The user-local uv (the one this engine's own setup installs, in ~/.local/bin) is preferred over
# whatever PATH answers: the PATH shim above may have just put a system-wide bin directory in front,
# and the interpreter this script hands back should be the one the rest of the engine will find again.
BIN="$(_ep_posix "${UV_INSTALL_DIR:-$HOME/.local/bin}")"
UV=""
for _c in "$BIN/uv" "$BIN/uv.exe" "$HOME/.local/bin/uv" "$HOME/.local/bin/uv.exe"; do
  [ -x "$_c" ] && { UV="$_c"; break; }
done
[ -n "$UV" ] || UV="$(command -v uv 2>/dev/null || true)"

if [ -z "$UV" ]; then
  say "One small helper first (uv). It goes in your home folder, needs no password, and takes about a minute…"
  if [ "$OS" = windows ]; then
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" >&2 \
      || { say "Could not download the helper. Check the internet connection and try again."; exit 4; }
  else
    curl -LsSf -m 600 https://astral.sh/uv/install.sh | sh >&2 \
      || { say "Could not download the helper. Check the internet connection and try again."; exit 4; }
  fi
  for _c in "$(command -v uv 2>/dev/null || true)" "$BIN/uv" "$BIN/uv.exe" "$HOME/.local/bin/uv" "$HOME/.local/bin/uv.exe"; do
    [ -n "$_c" ] && [ -x "$_c" ] && { UV="$_c"; break; }
  done
  [ -n "$UV" ] || { say "The helper installed but could not be found afterwards. Close and reopen the terminal, then try again."; exit 4; }
fi

# ── 2. Python 3.11, managed by uv ───────────────────────────────────────────
# --default also writes plain `python3` / `python` next to uv, which is the name every engine script and
# check-setup.sh look for. Without it only `python3.11` exists and the machine still "has no python3".
say "Installing a private Python 3.11 through it (no Homebrew, no password, about a minute)…"
# On a Mac without Apple's developer tools, keep uv away from Apple's install_name_tool placeholder, which
# would open the "install the developer tools?" dialog (scripts/_mac-arch.sh mac_clt_shield).
_cs=""
if [ -f "$ROOT/scripts/_mac-arch.sh" ]; then
  . "$ROOT/scripts/_mac-arch.sh" 2>/dev/null
  command -v mac_clt_shield >/dev/null 2>&1 && _cs="$(mac_clt_shield "${TMPDIR:-/tmp}/ensure-python-clt-shield.$$")"
fi
PATH="${_cs:+$_cs:}$PATH" "$UV" python install 3.11 --default >&2 \
  || { say "Python did not install. Check the internet connection and try again."; exit 5; }
[ -n "$_cs" ] && rm -rf "$_cs"
PY="$("$UV" python find 3.11 2>/dev/null || true)"
PY="$(_ep_posix "$PY")"
if [ -z "$PY" ] || ! "$PY" -c '' >/dev/null 2>&1; then
  say "Python installed but will not run yet. Close and reopen the terminal, then try again."
  exit 5
fi
say "Python is ready."
printf '%s\n' "$PY"
