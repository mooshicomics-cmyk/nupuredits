# _python3-shim.sh — source this before any `python3` call in a shell script.
#
# WHY: Windows ships a DECOY at the name `python3`. It is a Microsoft Store "App Execution Alias":
# it sits on PATH, so `command -v python3` and `[ -x ]` both SUCCEED, but running it does nothing
# except print "Python was not found; run without arguments to install from the Microsoft Store..."
# and exit non-zero. So a stock Windows machine LOOKS like it has python3 and does not.
# On Windows the real interpreter is normally called `python` (or is reached via the `py` launcher).
#
# This defines a `python3` shell function pointing at whatever actually executes, ONLY when the real
# `python3` does not work. On macOS/Linux the first test succeeds and nothing is defined — no-op.
#
# Detection is "does it RUN", never "does it exist" — existence is exactly what the decoy fakes.

# macOS: /usr/bin/python3 exists on every Mac, but without Apple's Command Line Tools it is only a
# PLACEHOLDER. Executing it does not run Python: it opens the "would you like to install the developer
# tools?" dialog over her screen and exits 1. Measured on a tester's fresh Intel Mac (2026-09-18): the
# updater's own "does python3 run" test popped that dialog, the update never ran, and the setup route
# her chip needed stayed out of reach. So the placeholder is never EXECUTED to find out. It is recognised
# by path plus the developer folder `xcode-select -p` names, which answers whether the tools are installed
# without touching anything.
# (When the tools ARE installed, /usr/bin/python3 is a real Python and passes the run test below.)
_P3_APPLE_PY="${_P3_APPLE_PY:-/usr/bin/python3}"   # overridable so a test can stand in a fake placeholder
_P3_SYS_ROOT="${_P3_SYS_ROOT:-}"                    # tests only: prefix for the system-wide Mac candidates below
_p3_apple_stub() {
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 1
  [ "$(command -v python3 2>/dev/null)" = "$_P3_APPLE_PY" ] || return 1
  # The tools count as installed only when python3 is really in the developer folder. `xcode-select -p`
  # alone answers yes for a folder a failed Command Line Tools install left configured but empty (it
  # prints any configured path, exit 0), and running the placeholder then opens the dialog again.
  # Same rule as mac_clt_has in _mac-arch.sh, written out because this shim is sourced on its own.
  _p3_dev="$(xcode-select -p 2>/dev/null)" && [ -n "$_p3_dev" ] && [ -x "$_p3_dev/usr/bin/python3" ] && return 1
  return 0
}

# Last resort when NOTHING on PATH runs: find a real interpreter on disk.
#
# WHY: measured on a tester's PC, `python3` was the Store decoy, `python` was not on PATH at all, and
# `py` was absent — so all three checks below failed and the engine had no interpreter, even though a
# perfectly good one sat at ~/.local/pyenv/Scripts/python.exe. She had to add it to PATH by hand every
# single session. A second tester's machine added two more: uv, which is how setup installs Python on
# Windows, keeps it under AppData/Roaming/uv/python/cpython-<ver>-windows-x86_64-none/, and drops a
# versioned python3.12.exe into ~/.local/bin rather than a plain python3. Neither was on this list, so the
# engine could not find the very Python its own setup had installed. These are the real directories Windows
# Python installers actually use; each is
# EXECUTED before being accepted, because existence is exactly what the decoy fakes.
#
# The Mac entries come first and are the mirror image of the same lesson: a fresh Mac's only python3 is
# Apple's placeholder (above), while a REAL one may sit in ~/.local/bin (uv's `--default` shim, which is
# what this engine's own Intel route and scripts/ensure-python.sh install), under uv's managed tree,
# in Homebrew's bin, or where python.org's installer puts it. /usr/bin/python3 is deliberately NOT in
# this list: when it works it already passed the PATH test, and when it does not, running it is the bug.
_p3_posix() {
  case "$1" in
    *:*) command -v cygpath >/dev/null 2>&1 && cygpath -u "$1" 2>/dev/null || printf '' ;;
    *)   printf '%s' "$1" ;;
  esac
}
_p3_find_on_disk() {   # $1 = "pil": only an interpreter that also imports Pillow counts
  # Split candidates on newlines only, so a home folder with a space ("Jane Smith") stays one path.
  local IFS=$'\n' _need="${1:-}"
  for _c in \
    "${HOME}/.local/bin/python3" \
    "${HOME}/.local/share/uv/python/cpython-*/bin/python3" \
    "${_P3_SYS_ROOT}/opt/homebrew/bin/python3" \
    "${_P3_SYS_ROOT}/usr/local/bin/python3" \
    "${_P3_SYS_ROOT}/Library/Frameworks/Python.framework/Versions/3.*/bin/python3" \
    "${APPDATA:-$HOME/AppData/Roaming}/uv/python/cpython-*/python.exe" \
    "${HOME}/.local/bin/python3.1*.exe" \
    "${HOME}/.local/pyenv/Scripts/python.exe" \
    "${HOME}/.pyenv/pyenv-win/versions/*/python.exe" \
    "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/Python/Python3*/python.exe" \
    "${HOME}/.local/share/uv/python/*/python.exe" \
    "${HOME}/.local/share/uv/python/*/bin/python3" \
    "/c/Python3*/python.exe"
  do
    _c="$(_p3_posix "$_c")"
    [ -n "$_c" ] || continue
    for _hit in $_c; do
      # Must RUN, not merely exist. This is the decoy test.
      if [ -x "$_hit" ] && "$_hit" -c '' >/dev/null 2>&1; then
        if [ "$_need" = pil ] && ! "$_hit" -c 'import PIL' >/dev/null 2>&1; then continue; fi
        printf '%s' "$_hit"; return 0
      fi
    done
  done
  return 1
}

# _P3_OK is 1 when `python3` (binary or the function defined here) actually runs, 0 when this machine
# has no usable Python. Scripts that must not guess (check-setup.sh, ensure-python.sh) read it instead of
# running `python3` themselves, which on a fresh Mac is exactly the call that opens Apple's dialog.
_P3_OK=0
if _p3_apple_stub; then
  :   # never run the placeholder; the on-disk search below may still turn up a real interpreter
elif python3 -c '' >/dev/null 2>&1; then
  _P3_OK=1
fi
# Windows: when more than one real Python is installed, prefer the one that has Pillow (the engine's
# graphics scripts import it). Measured on a tester's PC: adding the signed python.org 3.11 (to get past
# Smart App Control) put it first on PATH as `python`, it had no Pillow, and build-reel-type.py died with
# "No module named 'PIL'" while the 3.14 that had it sat unused. One extra launch only when the first
# candidate lacks Pillow; a machine with one Python behaves exactly as before.
_p3_has_pil() { "$@" -c 'import PIL' >/dev/null 2>&1; }
_p3_runs()    { command -v "$1" >/dev/null 2>&1 && "$@" -c '' >/dev/null 2>&1; }
if [ "$_P3_OK" -eq 0 ]; then
  _p3_pick=""
  if command -v python >/dev/null 2>&1 && _p3_has_pil python; then _p3_pick=python
  elif command -v py >/dev/null 2>&1 && _p3_has_pil py -3; then _p3_pick=py
  elif _p3_runs python; then _p3_pick=python
  elif _p3_runs py -3; then _p3_pick=py
  fi
  if [ "$_p3_pick" = python ]; then
    python3() { python "$@"; }
    export -f python3 2>/dev/null || true
    _P3_OK=1
  elif [ "$_p3_pick" = py ]; then
    python3() { py -3 "$@"; }
    export -f python3 2>/dev/null || true
    _P3_OK=1
  else
    _P3_REAL="$(_p3_find_on_disk)"
    if [ -n "$_P3_REAL" ]; then
      export _P3_REAL
      python3() { "$_P3_REAL" "$@"; }
      export -f python3 2>/dev/null || true
      _P3_OK=1
      # Put its folder on PATH too, so `python`, pip and console scripts resolve for the rest of this
      # shell instead of only the python3 name.
      case "$_P3_REAL" in
        */*) _p3_dir="${_P3_REAL%/*}"
             case ":$PATH:" in *":$_p3_dir:"*) : ;; *) PATH="$_p3_dir:$PATH"; export PATH ;; esac ;;
      esac
    fi
  fi
fi
# Mac: with Apple's Command Line Tools installed, /usr/bin/python3 is a real Python 3.9 and passes the run test
# above, so it won over the Python setup put in ~/.local/bin whenever /usr/bin came first on PATH. It has no
# Pillow, and every look the visual editor drew failed on "No module named 'PIL'" (a buyer, 2026-10-24). Same rule
# as the Windows branch: when that python3 lacks Pillow and a real one on disk has it, that one is python3 here.
# One extra launch, only on a Mac whose python3 is Apple's.
if [ "$_P3_OK" -eq 1 ] && [ "$(uname -s 2>/dev/null)" = "Darwin" ] \
   && [ "$(command -v python3 2>/dev/null)" = "$_P3_APPLE_PY" ] && ! _p3_has_pil python3; then
  _P3_REAL="$(_p3_find_on_disk pil)"
  if [ -n "$_P3_REAL" ]; then
    export _P3_REAL
    python3() { "$_P3_REAL" "$@"; }
    export -f python3 2>/dev/null || true
  fi
fi
export _P3_OK

# macOS: on a very new macOS release, a Homebrew python's pyexpat module can link against the SYSTEM
# libexpat and expect symbols that copy does not have. Reported by a tester on macOS 26.2 + Homebrew
# python 3.14.7: `Symbol not found: _XML_SetAllocTrackerActivationThreshold`. That breaks `import
# plistlib`, and plistlib is underneath venv creation, ensurepip and pip, so setup dies with a confusing
# `ensurepip returned non-zero exit status 1` that names neither expat nor plistlib. Worse, it fails
# QUIETLY first: platform.mac_ver() returns ('', ('','',''), '') instead of raising, so pip's vendored
# truststore blows up on `int('')` and sends you chasing the wrong thing entirely.
#
# Fix: if Homebrew's own expat keg is installed, prefer it. The keg is keg-only, so it is never on the
# default search path and has to be named explicitly. Guarded to Darwin AND to the keg actually being
# present, so this is a no-op on every machine where the stock setup already works.
if [ "$(uname -s)" = "Darwin" ]; then
  for _ep in /opt/homebrew/opt/expat/lib /usr/local/opt/expat/lib; do
    if [ -d "$_ep" ]; then
      case ":${DYLD_LIBRARY_PATH:-}:" in
        *":$_ep:"*) : ;;
        # No trailing separator when the var was empty: an empty entry in a dyld search list
        # means "the current directory", which is not something to hand a library loader.
        *) DYLD_LIBRARY_PATH="$_ep${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"; export DYLD_LIBRARY_PATH ;;
      esac
    fi
  done
fi

# Force UTF-8 for every Python process launched from here.
# Two distinct Windows bugs, one switch:
#  1. WRITING - the legacy console codepage (cp1252) cannot encode the checkmark/arrow status symbols
#     these scripts print, and raises UnicodeEncodeError partway through a step.
#  2. READING - open() with no explicit encoding= uses the locale codepage on Windows, NOT UTF-8. Any
#     draft JSON, transcript or brand-kit line containing a curly quote, an em dash or an emoji then
#     raises UnicodeDecodeError. There are ~59 such open() calls in the engine; this covers all of them
#     without touching a single call site.
# Harmless no-op on macOS/Linux, which are already UTF-8.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# venv_py <venv-dir> — print the interpreter inside a venv, whatever this OS named it.
#
# WHY: `uv venv` and `python -m venv` create bin/ on macOS/Linux and Scripts/ on Windows. The engine
# hardcoded bin/python, so every venv call failed on a PC. This does not GUESS by OS — it checks which
# file actually exists and takes the first hit, so it is correct even on a layout neither of us expects.
# Falls back to the historic bin/python path, which keeps the old behaviour (and the old error message)
# when nothing is found.
venv_py() {
  for _c in "Scripts/python.exe" "bin/python" "bin/python3" "Scripts/python3.exe"; do
    if [ -x "$1/$_c" ]; then printf '%s\n' "$1/$_c"; return 0; fi
  done
  printf '%s\n' "$1/bin/python"
}

# venv_home — where the transcription venv lives, including one built under an earlier cache layout.
#
# The transcription venv is a 3-5 GB build. An install made before this engine cached under its own
# name still has a finished one sitting on disk, and moving the path without looking would quietly
# make every one of them download the whole thing again on the next rough cut, with no explanation.
#
# So a prior build is found by the engine's OWN completion marker rather than by a folder name. The
# leaf ("whisperx-venv" / "fasterwhisper-venv") is this engine's, so anything carrying it under
# ~/.cache is ours. That means no past layout has to be written down here, and a layout nobody has
# thought of yet is handled for free. A fresh install matches nothing and gets the current path.
venv_home() {   # $1 = the venv leaf, e.g. whisperx-venv
  _vh_new="$HOME/.cache/reels-editing-engine/$1"
  [ -d "$_vh_new" ] && { printf '%s\n' "$_vh_new"; return 0; }
  # a FINISHED build first (it carries .speech-tools-ready, or .deps-ok on an older build) ...
  for _vh_c in "$HOME"/.cache/*/"$1"; do
    [ -d "$_vh_c" ] && { [ -e "$_vh_c/.speech-tools-ready" ] || [ -e "$_vh_c/.deps-ok" ]; } && { printf '%s\n' "$_vh_c"; return 0; }
  done
  # ... then a half-built one, which word-timings.sh already knows how to repair in place.
  for _vh_c in "$HOME"/.cache/*/"$1"; do
    [ -d "$_vh_c" ] && { printf '%s\n' "$_vh_c"; return 0; }
  done
  printf '%s\n' "$_vh_new"
}

# scratch_root — the ONE scratch directory both halves of the engine agree on.
#
# WHY: the cut pipeline hands work between the two halves through a scratch folder. The Python half
# calls tempfile.gettempdir(); the shell half used to write "${TMPDIR:-/tmp}". On macOS TMPDIR is set
# and those are the same folder, so the split was invisible. On Windows Git Bash they are two
# different real directories: Python answers C:\Users\<her>\AppData\Local\Temp while the shell falls
# back to /tmp, which Git Bash maps inside its own install. One half then writes files the other half
# cannot find, and it fails far downstream as a missing cuts.json rather than at the cause.
#
# So there is now one source of truth: ask Python, the same call the Python half makes, and convert
# the answer to the POSIX form this shell needs. The old expression remains only as a last resort for
# a machine where Python cannot be reached at all.
scratch_root() {
  _sr="$(python3 -c 'import tempfile; print(tempfile.gettempdir())' 2>/dev/null)"
  case "$_sr" in
    "")  _sr="${TMPDIR:-/tmp}" ;;
    *:*) # Windows-style answer with a drive colon: convert, or fall back rather than emit a bad path.
         if command -v cygpath >/dev/null 2>&1; then
           _sr="$(cygpath -u "$_sr" 2>/dev/null)"
           [ -n "$_sr" ] || _sr="${TMPDIR:-/tmp}"
         else
           _sr="${TMPDIR:-/tmp}"
         fi ;;
  esac
  printf '%s/reels-editing-engine' "$_sr"
}
