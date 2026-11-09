# _path-shim.sh — source this before calling any external tool from a shell script.
#
# WHY: on Windows almost nothing the engine depends on is on PATH in a fresh shell. node, npx, npm,
# ffmpeg, ffprobe, uv and git all install to their own folders, and whether those folders reach PATH
# depends on the installer, the shell, and whether the terminal was reopened afterwards. Measured on
# Windows: the same directories had to be prepended by hand before nearly every command, and were lost
# again on the next one, because a shell's PATH does not outlive the shell.
#
# This repairs PATH for THIS PROCESS ONLY. It writes nothing to the machine, needs no admin rights,
# and cannot leave a buyer's system changed. Reopening the terminal simply re-runs it.
#
# A directory is added only when the tool is genuinely missing, so a correctly-configured machine is
# untouched. (Unlike the python3 shim this tests PRESENCE, not execution — see the note below.)
#
# Harmless on macOS, where it also covers the real case of Homebrew not being on PATH in a
# non-login shell (a fresh-Mac snag that looks identical to the buyer: "command not found").
#
# ~/.local/bin is now listed for every tool, not just uv. On a true Intel Mac, where Homebrew cannot
# be installed at all, that directory is where EVERYTHING lands (see product/INTEL-MAC-ROUTE.md) —
# static ffmpeg/ffprobe, uv, and uv's python3 shims. It used to be listed for uv alone, so on that
# machine a correct install still reported ffmpeg and python3 as missing, which is the single most
# demoralising failure shape there is: you did everything right and the checker says you did not.

# Presence check only — deliberately NOT an execution test.
#
# The python3 shim runs the tool because Windows ships a DECOY at that exact name. No such decoy
# exists for node/ffmpeg/uv/git, so here `command -v` is enough, and it is enough by a wide margin:
# executing seven tools to ask their version cost ~440 ms on EVERY script start (splice, transcribe,
# smoke-test), paid by every creator on every run, to re-confirm a healthy machine. This is ~2 ms.
# Version-flag spellings also differ (ffmpeg wants -version, not --version), so an execution test
# here reported a perfectly good ffmpeg as missing.
_ps_have() { command -v "$1" >/dev/null 2>&1; }

# Convert a Windows-style path to the POSIX form this shell uses.
#
# THIS IS LOAD-BEARING. On Git Bash the Windows environment variables are Windows-style and carry a DRIVE
# COLON: $LOCALAPPDATA is "C:\Users\her\AppData\Local". PATH is colon-separated, so prepending one of
# those raw splits it in half and leaves a junk "C" entry plus an unusable remainder — PATH is corrupted
# from that line on, and every tool lookup in the rest of the script fails. The symptom is not an error
# message, it is the engine quietly losing the ability to find its own tools.
_ps_posix() {
  case "$1" in
    *:*) command -v cygpath >/dev/null 2>&1 && cygpath -u "$1" 2>/dev/null || printf '' ;;
    *)   printf '%s' "$1" ;;
  esac
}

_ps_add() {
  # Local: a script that sources this file may use any short name for its own (collect-report keeps the
  # engine root in _d), and a tool missing from PATH used to overwrite it.
  local _ps_dest
  _ps_dest="$(_ps_posix "$1")"
  # Hard guard: never put anything containing a colon into PATH, whatever produced it. If cygpath is
  # missing or failed, we drop the candidate rather than risk corrupting PATH for everything downstream.
  case "$_ps_dest" in
    ""|*:*) return 0 ;;
  esac
  case ":$PATH:" in
    *":$_ps_dest:"*) return 0 ;;
  esac
  [ -d "$_ps_dest" ] && PATH="$_ps_dest:$PATH" && export PATH
  # A candidate that is not on this machine is the normal case, not a failure. Without this line the
  # function returned the failed [ -d ] test, and every script that sources this file under `set -e`
  # (splice, transcribe, separate_layers...) stopped right here, silently, whenever one tool was missing.
  return 0
}

# Expand a candidate containing a * — a VERSIONED install directory.
#
# WHY this exists: measured on a real tester's PC, both of the engine's two most-wanted tools install
# into a folder whose name carries a version number, so no fixed string can ever match them:
#   ffmpeg (winget) -> AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_<hash>/ffmpeg-9.0.1-full_build/bin
#   node (zip)      -> AppData/Local/Programs/node/node-v24.19.0-win-x64
# The shim previously looked at WinGet/Links (which winget had left EMPTY on that machine) and at
# Programs/nodejs (one folder shallower than where node actually was), so it found neither.
#
# The path is converted to POSIX form BEFORE globbing: a Windows-style string with a drive colon and
# backslashes matches nothing, so globbing first would silently return zero hits on every machine.
_ps_expand() {
  local _p _e
  _p="$(_ps_posix "$1")"
  [ -n "$_p" ] || return 0
  for _e in $_p; do
    [ -d "$_e" ] && printf '%s\n' "$_e"
  done
  return 0
}

# Candidate directories per tool, most-likely first. Every one of these is a real install location
# used by an official installer, winget, Chocolatey, Scoop or the tool's own bootstrap script.
_ps_candidates() {
  case "$1" in
    node|npm|npx)
      printf '%s\n' \
        "/c/Program Files/nodejs" "${ProgramFiles:-/c/Program Files}/nodejs" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/nodejs" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/node/node-v*-win-x64" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/node/node-v*" \
        "${APPDATA:-$HOME/AppData/Roaming}/nvm/v*" \
        "${APPDATA:-$HOME/AppData/Roaming}/npm" \
        "${HOME}/scoop/shims" "/c/ProgramData/chocolatey/bin" \
        "${HOME}/.local/bin" \
        "/opt/homebrew/bin" "/usr/local/bin"
      ;;
    ffmpeg|ffprobe)
      printf '%s\n' \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Packages/*FFmpeg*/*/bin" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Packages/*FFmpeg*/bin" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Links" \
        "/c/ProgramData/chocolatey/bin" "${HOME}/scoop/shims" \
        "/c/ffmpeg/bin" "/c/Program Files/ffmpeg/bin" \
        "${HOME}/.local/bin" \
        "/opt/homebrew/bin" "/usr/local/bin"
      ;;
    uv)
      # The WinGet/Packages globs are the same lesson ffmpeg taught above, and uv had not learned it:
      # winget installs uv to Packages/astral-sh.uv_<hash>/uv-x86_64-pc-windows-msvc/, a VERSIONED and
      # arch-named folder no fixed string can match, and on a real tester's PC winget had again left
      # WinGet/Links empty. So the two entries that were here found nothing, `uv` stayed missing after a
      # successful install, and setup reported a tool the machine actually had. (PC test, 2026-09-18.)
      printf '%s\n' \
        "${HOME}/.local/bin" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/uv" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Packages/*astral-sh.uv*/*" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Packages/*astral-sh.uv*" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Packages/*uv_*/*" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Packages/*uv_*" \
        "${LOCALAPPDATA:-$HOME/AppData/Local}/Microsoft/WinGet/Links" \
        "${HOME}/.cargo/bin" \
        "/opt/homebrew/bin" "/usr/local/bin"
      ;;
    git)
      printf '%s\n' \
        "/c/Program Files/Git/cmd" "${ProgramFiles:-/c/Program Files}/Git/cmd" \
        "/opt/homebrew/bin" "/usr/local/bin"
      ;;
    *)
      printf '%s\n' "${HOME}/.local/bin" "/opt/homebrew/bin" "/usr/local/bin"
      ;;
  esac
}

# Repair only what is actually broken.
# NOTE: a `| while read` pipeline runs in a SUBSHELL, whose PATH export dies with it — so the
# candidate list is walked with IFS set to newline instead, which stays in this shell.
_ps_old_ifs=$IFS
for _ps_tool in node npx npm ffmpeg ffprobe uv git; do
  if ! _ps_have "$_ps_tool"; then
    IFS='
'
    for _ps_dir in $(_ps_candidates "$_ps_tool"); do
      [ -n "$_ps_dir" ] || continue
      case "$_ps_dir" in
        *\**) for _ps_g in $(_ps_expand "$_ps_dir"); do _ps_add "$_ps_g"; done ;;
        *)    _ps_add "$_ps_dir" ;;
      esac
    done
    IFS=$_ps_old_ifs
  fi
done
unset _ps_tool _ps_dir _ps_g _ps_old_ifs

# Report, once, what is still missing — so a failure downstream reads as a setup problem, not a bug.
_path_shim_missing() {
  local _m _t
  _m=""
  for _t in node npx ffmpeg ffprobe; do
    _ps_have "$_t" || _m="$_m $_t"
  done
  printf '%s' "${_m# }"
}
