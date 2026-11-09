#!/usr/bin/env bash
# Sets up the editable-CapCut engine (VectCut) for the Reels Editing Engine.
# Safe + idempotent: it skips anything already done and keeps a working setup exactly as it is. The one thing it
# replaces is its own workspace when that no longer runs (step 2 explains), never anything of yours.
# Run it once. After that you only ever use start-editor.command.

set -euo pipefail
cd "$(dirname "$0")"   # always run from this folder

# Which machine is this, and borrow the engine's own shims so the tools resolve.
# _path-shim repairs PATH for THIS process (on Windows the tools are usually installed but invisible
# to a fresh shell); _python3-shim handles Windows' fake `python3` and gives us venv_py, which knows
# a venv keeps its interpreter in Scripts/ on Windows and bin/ everywhere else.
case "$(uname -s)" in
  Darwin)               OSK=mac;   THIS_MACHINE="Mac" ;;
  MINGW*|MSYS*|CYGWIN*) OSK=win;   THIS_MACHINE="PC" ;;
  *)                    OSK=other; THIS_MACHINE="computer" ;;
esac
_R="$(cd ../../.. && pwd)"
[ -f "$_R/scripts/_path-shim.sh" ]    && . "$_R/scripts/_path-shim.sh"
[ -f "$_R/scripts/_python3-shim.sh" ] && . "$_R/scripts/_python3-shim.sh"
# Never a dead end: a step whose usual route fails takes the one that works and leaves one line in
# _local/fallbacks.log (note_fallback) for the problem report. _mac-arch.sh knows Apple's placeholder tools.
export REELS_ENGINE_ROOT="${REELS_ENGINE_ROOT:-$_R}"
if [ -f "$_R/scripts/_fallbacks.sh" ]; then . "$_R/scripts/_fallbacks.sh"
else note_fallback() { :; }; remember_pivot() { :; }; fi
[ "$OSK" = mac ] && [ -f "$_R/scripts/_mac-arch.sh" ] && . "$_R/scripts/_mac-arch.sh"

echo ""
echo "Setting up your editing engine. This takes a few minutes and you only do it once."
echo ""

# 1) FFmpeg (required by the engine for anything that touches video)
have_ffmpeg() { command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; }
if ! have_ffmpeg; then
  echo "-> The video engine (FFmpeg) is needed and was not found on your $THIS_MACHINE. Installing it now..."
  if [ "$OSK" = win ]; then
    # The same winget line set-me-up uses. Windows may ask "allow this app to make changes?": say yes.
    winget install -e --accept-source-agreements --accept-package-agreements --disable-interactivity --id Gyan.FFmpeg \
      || echo "   winget did not finish the install."
  elif command -v brew >/dev/null 2>&1; then
    echo "   Installing it with Homebrew..."
    brew install ffmpeg || echo "   Homebrew did not finish the install."
  elif [ "$OSK" = mac ]; then
    # No Homebrew: the engine's own direct route (signed / checksum-pinned static builds into ~/.local/bin, no
    # password). MAC_DIRECT_ROUTE=1 lets it run on an Apple-chip Mac too (scripts/_mac-arch.sh explains).
    echo "   No Homebrew here, so it comes straight from its own builds (no password needed)..."
    MAC_DIRECT_ROUTE=1 bash "$_R/scripts/intel-mac-install.sh" ffmpeg || echo "   The direct install did not finish."
    case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH"; export PATH ;; esac
  fi
  # A fresh install is usually not on this shell's PATH yet: ask the PATH shim to look again.
  [ -f "$_R/scripts/_path-shim.sh" ] && . "$_R/scripts/_path-shim.sh"
  if have_ffmpeg; then
    note_fallback editor-setup "FFmpeg was missing; setup installed it itself and carried on"
    echo "   FFmpeg is installed."
  else
    echo ""
    echo "   FFmpeg would not install on its own. Install it, then run this again:"
    if [ "$OSK" = win ]; then
      echo "       winget install -e --id Gyan.FFmpeg"
      echo "   (Close and reopen Git Bash afterwards so it can be found.)"
    elif [ "$OSK" = mac ]; then
      echo "       MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh ffmpeg"
    else
      echo "       your system's package manager (for example: sudo apt install ffmpeg)"
    fi
    echo "   If it still will not install, run /report-a-problem."
    exit 1
  fi
else
  echo "-> FFmpeg is here. Good."
fi

# 2) Python workspace, and 3) the engine's tools in it
#
# "It exists" is not "it works". A workspace whose Python was upgraded or removed underneath it (a Homebrew
# python@3.12 -> 3.13 move does exactly that), or one built from stock Python 3.9, used to be kept forever
# ("Workspace already exists. Keeping it.") and then fail the same way on every run, a loop with no way out.
# So the workspace has to RUN, on 3.10+, and load the engine's own tools; one that does not is moved aside and
# built again, once.
ENGINE_MODS="flask, requests, json5, imageio, psutil"   # requirements.txt, as the server imports them
venv_runs()  { local p; p="$(venv_py "$PWD/venv-capcut")"; [ -x "$p" ] && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
venv_loads() { local p; p="$(venv_py "$PWD/venv-capcut")"; [ -x "$p" ] && "$p" -c "import $ENGINE_MODS" >/dev/null 2>&1; }

# Apple's /usr/bin/python3 placeholder (no developer tools behind it) is never EXECUTED: running it opens the
# "install the developer tools?" dialog instead of answering. mac_clt_stub (scripts/_mac-arch.sh) tells it
# apart by path and the developer folder, without running it.
is_apple_placeholder() {
  [ "$OSK" = mac ] || return 1
  local p; p="$(command -v "$1" 2>/dev/null)" || return 1
  command -v mac_clt_stub >/dev/null 2>&1 && mac_clt_stub "$p"
}
is_py310() { "$@" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; }

# The engine's code uses modern type hints (str | None) that need Python 3.10 or newer. Stock macOS ships
# Python 3.9, which would build a workspace that crashes on import. Each candidate's ACTUAL version is
# tested at runtime (not its name), so 3.13 / 3.14 / any future release all qualify, and the real Homebrew
# locations are searched even when Homebrew is installed but not yet on PATH (a common fresh-Mac state where
# ~/.zprofile never sourced `brew shellenv`, so `python3` still points at stock 3.9 while a perfectly good
# brew python sits unseen on disk).
pick_python() {
  PYBIN=""
  # Pull Homebrew onto PATH for this lookup if it is installed but not resolving (does not touch the user's
  # shell files; the venv built below is pinned to the interpreter picked anyway).
  for brewbin in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if command -v "$brewbin" >/dev/null 2>&1 || [ -x "$brewbin" ]; then
      eval "$("$brewbin" shellenv 2>/dev/null)" 2>/dev/null || true
      break
    fi
  done
  # Candidates: whatever `python3` resolves to now, plus every versioned python3.NN in the usual Homebrew /
  # local / uv locations (globbed, so newer releases are found without editing this list). An unmatched glob
  # stays literal and is safely skipped by the command -v + version check.
  for cand in python3 python py \
              "${LOCALAPPDATA:-}/Programs/Python/Python3"*/python.exe \
              "/c/Python3"*/python.exe \
              "$HOME/.local/bin/python3" "$HOME/.local/bin/python3."* \
              /opt/homebrew/bin/python3.* /opt/homebrew/opt/python@*/bin/python3.* \
              /usr/local/bin/python3.* /usr/local/opt/python@*/bin/python3.*; do
    command -v "$cand" >/dev/null 2>&1 || continue
    is_apple_placeholder "$cand" && continue
    if is_py310 "$cand"; then PYBIN="$cand"; return 0; fi
  done
  return 1
}

# No Python 3.10+ on this computer: get one rather than stop. scripts/ensure-python.sh installs a private
# Python 3.11 through uv when there is no Python at all (no Homebrew, no password, no admin). When there IS a
# Python but it is too old, ensure-python.sh is satisfied by it, so uv is asked for 3.11 directly.
get_python() {
  local py uv c
  echo "   No Python 3.10 or newer on your $THIS_MACHINE yet. Getting one (a private copy, no password needed)..."
  py="$(bash "$_R/scripts/ensure-python.sh")" || py=""   # stdout is the path only; its messages go to stderr
  if [ -n "$py" ] && is_py310 "$py"; then PYBIN="$py"; return 0; fi
  uv=""
  for c in "$HOME/.local/bin/uv" "$HOME/.local/bin/uv.exe" "$(command -v uv 2>/dev/null || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && { uv="$c"; break; }
  done
  if [ -z "$uv" ]; then
    if [ "$OSK" = win ]; then
      powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex" || true
    else
      curl -LsSf -m 600 https://astral.sh/uv/install.sh | sh || true
    fi
    for c in "$HOME/.local/bin/uv" "$HOME/.local/bin/uv.exe"; do [ -x "$c" ] && { uv="$c"; break; }; done
  fi
  [ -n "$uv" ] || return 1
  local cs=""
  command -v mac_clt_shield >/dev/null 2>&1 && cs="$(mac_clt_shield "${TMPDIR:-/tmp}/editor-setup-clt-shield.$$")"
  PATH="${cs:+$cs:}$PATH" "$uv" python install 3.11 || true
  [ -n "$cs" ] && rm -rf "$cs"
  py="$("$uv" python find 3.11 2>/dev/null || true)"
  case "$py" in *:*) command -v cygpath >/dev/null 2>&1 && py="$(cygpath -u "$py")" ;; esac
  if [ -n "$py" ] && is_py310 "$py"; then PYBIN="$py"; return 0; fi
  return 1
}

build_workspace() {
  echo "-> Building the engine's private workspace..."
  if ! pick_python; then
    if get_python; then
      note_fallback editor-setup "no Python 3.10+ was installed; setup got a private Python 3.11 through uv and carried on"
    else
      echo ""
      echo "   The engine needs Python 3.10 or newer, and it would not install on its own. Install it, then run this again:"
      if [ "$OSK" = win ]; then
        echo "       winget install -e --id Python.Python.3.12 --scope user"
        echo "   (Then close and reopen Git Bash.)"
      else
        echo "       bash scripts/ensure-python.sh"
      fi
      echo "   If it still will not install, run /report-a-problem."
      exit 1
    fi
  fi
  echo "   Using $PYBIN ($("$PYBIN" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))."
  "$PYBIN" -m venv venv-capcut
}

# 3) Install the engine's tools (requirements.txt ONLY -- never pyproject, never pyJianYingDraft).
# venv_py finds the interpreter wherever this OS put it (Scripts/ on Windows, bin/ elsewhere), and pip is
# invoked THROUGH it so there is no second path to get wrong. A pip that will not upgrade itself is not a
# reason to stop (the one the venv shipped with installs these tools fine), so that step can fail quietly.
install_tools() {
  echo "-> Installing the engine's tools..."
  VPY="$(venv_py "$PWD/venv-capcut")"
  "$VPY" -m pip install --quiet --upgrade pip || echo "   (pip could not update itself; carrying on with the one it has)"
  "$VPY" -m pip install --quiet -r requirements.txt || echo "   The tools did not all install."
}

# A broken workspace is moved aside, not deleted on sight: if the rebuild cannot finish either, it is still
# there for the problem report. Once the rebuild works it is removed, since it held nothing of hers (it is a
# regenerable copy of the tools, built from requirements.txt) and would only take up disk.
BROKEN=""
move_aside() {   # $1 = why
  BROKEN="venv-capcut.broken-$(date +%Y%m%d-%H%M%S)"
  echo "-> The engine's workspace is here but $1. Moving it aside to $BROKEN and building a fresh one..."
  mv venv-capcut "$BROKEN"
}

if [ -d "venv-capcut" ] && ! venv_runs; then
  move_aside "its Python no longer runs (or is older than 3.10)"
fi
if [ ! -d "venv-capcut" ]; then
  build_workspace
else
  echo "-> Workspace already exists and runs. Keeping it."
fi
install_tools
if ! venv_loads && [ -z "$BROKEN" ]; then
  move_aside "its tools would not load"
  build_workspace
  install_tools
fi
if ! venv_loads; then
  echo ""
  echo "   The engine's tools would not load, even in a fresh workspace. Run /report-a-problem: the report"
  echo "   carries what was tried."
  exit 1
fi
if [ -n "$BROKEN" ]; then
  rm -rf "$BROKEN"
  note_fallback editor-setup "the editing engine's workspace would not run or load its tools; moved it aside and rebuilt it"
  remember_pivot vectcut.venv-rebuilt 1 "the workspace's Python or tools stopped working; setup rebuilt it"
fi
echo "   Tools installed."

# 4) config.json pointed at your own computer (only write it if missing, never overwrite yours)
if [ ! -f "config.json" ]; then
  echo "-> Writing the local config (points the engine at your own computer)..."
  cat > config.json <<'JSON'
{
  "draft_profile": "capcut_legacy",
  "is_capcut_env": true,
  "draft_domain": "http://localhost:9001",
  "port": 9001,
  "preview_router": "/draft/downloader",
  "is_upload_draft": false
}
JSON
else
  echo "-> config.json already here. Keeping it."
fi

# 5) CapCut projects folder check (needs CapCut opened at least once)
if [ "$OSK" = win ]; then
  CAPFOLDER="$LOCALAPPDATA/CapCut/User Data/Projects/com.lveditor.draft"
else
  CAPFOLDER="$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft"
fi
if [ ! -d "$CAPFOLDER" ]; then
  echo ""
  echo "   One quick thing: open the CapCut app once so it can create its projects folder,"
  echo "   then you are all set. (You do not have to do anything in CapCut, just open it once.)"
fi

echo ""
echo "============================================"
echo " Editing engine ready."
if [ "$OSK" = win ]; then
  echo " To turn it on: double-click  start-editor.bat"
else
  echo " To turn it on: double-click  start-editor.command"
fi
echo " (or run:  \"$(venv_py "$PWD/venv-capcut")\" capcut_server.py )"
echo "============================================"
echo ""
