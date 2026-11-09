# _win-sac.sh — Windows Smart App Control, for the steps that download native Python files. Source it.
#
# WHY: Smart App Control (Windows 11) blocks native files that are neither signed nor widely known. A tester's
# PC had it ON, and the speech-tools setup failed three times in a row: uv's own downloaded Python has an
# unsigned python311.dll (Code Integrity events 3077/3033), so `uv venv` ended on "Missing expected target
# directory for Python minor version link" and the repair loop just reproduced it. Then 14 of 420 native files
# in the new venv were blocked ("An Application Control policy has blocked this file") from the newest
# releases of ctranslate2, pandas, scikit-learn, aiohttp, matplotlib and SQLAlchemy. Older, widely used
# releases load. What worked, measured on that machine: the SIGNED python.org Python 3.11 (winget, user
# scope, no admin) with uv told never to download its own, plus the pins in WIN_SAC_PINS.
#
# Smart App Control cannot be switched back on once it is off, so the engine never tells her to turn it off.
# It works with it on instead.

# Versions measured to load under Smart App Control (2026-10-06, Windows 11 26200, whisperx on CPU int8).
WIN_SAC_PINS="pandas==2.2.3 ctranslate2==4.5.0 setuptools==80.9.0 scikit-learn==1.5.2 aiohttp==3.10.10 matplotlib==3.9.2 SQLAlchemy==2.0.36"

# win_sac_state -> on | eval | off | unknown   (only meaningful on Windows; elsewhere prints off)
# The registry value is VerifiedAndReputablePolicyState: 0 off, 1 on (enforcing), 2 evaluation (watching,
# blocks nothing). reg's output is in the console's OEM codepage, so only the ASCII value is read from it,
# and MSYS2 path conversion is turned off so Git Bash does not rewrite /v into a folder path.
win_sac_state() {
  case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) ;; *) echo off; return 0 ;; esac
  local v
  v="$(MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1 reg query 'HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy' \
        /v VerifiedAndReputablePolicyState 2>/dev/null | LC_ALL=C grep -a -o '0x[0-9a-fA-F]*' | tail -1)"
  case "$v" in
    0x1) echo on ;;
    0x2) echo eval ;;
    0x0) echo off ;;
    *)   echo unknown ;;
  esac
}

# win_signed_python311 -> path to a python.org (signed) Python 3.11, or nothing. Never uv's own download,
# which is the unsigned one. Each candidate is RUN, not merely found.
win_signed_python311() {
  local IFS=$'\n' c
  for c in \
    "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/Python/Python311/python.exe" \
    "/c/Program Files/Python311/python.exe" \
    "/c/Python311/python.exe"
  do
    command -v cygpath >/dev/null 2>&1 && case "$c" in *:*) c="$(cygpath -u "$c")" ;; esac
    if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)' >/dev/null 2>&1; then
      printf '%s' "$c"; return 0
    fi
  done
  if command -v py >/dev/null 2>&1; then
    c="$(py -3.11 -c 'import sys; print(sys.executable)' 2>/dev/null | tr -d '\r')"
    case "$c" in *[Ww]indows[Aa]pps*|*uv*python*) c="" ;; esac
    [ -n "$c" ] && { command -v cygpath >/dev/null 2>&1 && c="$(cygpath -u "$c")"; printf '%s' "$c"; return 0; }
  fi
  return 1
}

# win_get_signed_python311 -> installs it with winget (user scope, no admin pop-up) when missing, then prints it.
win_get_signed_python311() {
  local p
  p="$(win_signed_python311)" && { printf '%s' "$p"; return 0; }
  command -v winget >/dev/null 2>&1 || return 1
  winget install --id Python.Python.3.11 -e --scope user --silent \
    --accept-package-agreements --accept-source-agreements >&2 || true
  win_signed_python311
}
