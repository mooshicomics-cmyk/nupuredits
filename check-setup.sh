#!/usr/bin/env bash
# check-setup.sh: how set-me-up sees what this computer is missing. It runs this, installs whatever it
# flags (naming each tool by the job it does in the engine), and runs it again until nothing is left.
#
#   ./check-setup.sh
#
# This file only reports. Every missing tool gets the exact line that installs it on THIS machine (Homebrew on
# an Apple-chip Mac, each tool's own download on an Intel Mac or an older macOS, winget under Git Bash on
# Windows), and set-me-up hands that line over word for word, so each one is a fixed string. Nothing here is
# installed, upgraded, deleted or configured.
#
# The report is grouped by the phase of a reel that needs each thing: the rough cut (reading, cutting and
# transcribing her clips), then the build (captions, text, graphics, placement, sound), then the style packs'
# fonts, then (on Windows) finishing in CapCut. Each row names the job a tool does before its own name.
# Exit 0 means nothing a reel needs is missing; 1 means something is left, which is the normal answer on a
# new machine and set-me-up says so.
#
# The transcriber itself (WhisperX large-v3 and torch) is outside this check: the rough cut sets up its own venv
# the first time it runs, and the "On first use" block says so.
set -uo pipefail

# The engine folder, from where this file sits. Looked up here, before anything below touches PATH, to find
# the engine's shell helpers, and again further down for every other path the checks use.
engine_dir() { cd "$(dirname "${BASH_SOURCE[0]}")" && pwd; }
SHIMS="$(engine_dir)/scripts"

# Repair PATH for THIS process before checking anything. On Windows the tools are usually installed
# but invisible to a fresh shell, and reporting an installed tool as missing sends a buyer off to
# reinstall something they already have. The shim writes nothing to the machine.
[ -f "$SHIMS/_path-shim.sh" ] && . "$SHIMS/_path-shim.sh"

# Which kind of Mac this is, from the one place that knows (scripts/_mac-arch.sh): arm64, an Apple
# Silicon Mac running translated under Rosetta, or a true Intel Mac. It decides every install line
# printed below, because Homebrew's installer now aborts on anything that is not arm64 — so on an
# Intel Mac every `brew install` hint would be a line that could not work.
MACCLASS=""
MACROUTE=""   # brew | direct | rosetta — the chip AND the macOS decide it (see mac_install_route)
if [ -f "$SHIMS/_mac-arch.sh" ]; then
  . "$SHIMS/_mac-arch.sh"
  MACCLASS="$(mac_arch_class)"
  MACROUTE="$(mac_install_route)"
fi

# What is running this: a Mac, Windows through Git Bash, or something the engine does not support.
platform() {   # platform <kernel name>  ->  OS (mac|win|other) and MACHINE, the name in the heading
  case "$1" in
    MINGW*|MSYS*|CYGWIN*) OS=win   MACHINE="Windows, in Git Bash" ;;
    Darwin)               OS=mac   MACHINE="a Mac" ;;
    *)                    OS=other MACHINE="$1" ;;
  esac
}
platform "$(uname -s 2>/dev/null || echo unknown)"

# ── the install lines ──────────────────────────────────────────────────────────────────────────────
# winget's first run stops at a licence prompt and waits for a keypress. When Claude runs the line there is
# no keypress coming, so the install just sits there looking hung. These flags answer the prompt up front.
WINGET_FLAGS="-e --accept-source-agreements --accept-package-agreements --disable-interactivity"
winget_line() { echo "winget install $WINGET_FLAGS --id $1"; }

# An Apple-chip Mac with a working Homebrew where `brew install <tool>` failed once: set-me-up installed that
# one tool by the direct route instead and remembered it in _local/pivots.json (product/fallbacks.py,
# "setup.direct.<tool>"). Read with grep, not Python: on a Mac whose Python is the very thing that would
# not install, asking python3 could open Apple's developer-tools dialog. Either spelling of Python counts.
direct_remembered() {   # direct_remembered <ffmpeg|uv|node|python3|pillow>
  local pv="${REELS_ENGINE_LOCAL:-$(engine_dir)/_local}/pivots.json" k
  [ -f "$pv" ] || return 1
  for k in "$1" "${1%3}"; do
    grep -qF "\"setup.direct.$k\":" "$pv" 2>/dev/null && return 0
  done
  return 1
}

install_cmd() {   # install_cmd <ffmpeg|uv|node|python3|pillow>  ->  the line that installs it HERE
  # A Mac Homebrew cannot serve (a true Intel Mac, or an Apple-chip Mac on a macOS older than Homebrew
  # supports) gets its own routes. Those live in _mac-arch.sh, beside the installer that carries them
  # out, so the advice and the installer cannot drift apart.
  if [ "$MACROUTE" = direct ]; then mac_intel_hint "$1"; return; fi
  # One tool whose Homebrew install already failed on this Mac: its direct line, never the brew line she
  # watched fail. Only that tool; Homebrew still serves everything else here, so nothing is pinned.
  if [ "$OS" = mac ] && direct_remembered "$1"; then
    case "$1" in
      ffmpeg|uv|node) echo "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh $1   (its own download; Homebrew could not install it here)" ;;
      python3|pillow) echo "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh $1   (then open a NEW terminal, so python3 is the one it installed in ~/.local/bin)" ;;
    esac
    return
  fi
  case "$OS" in
    mac)
      case "$1" in
        python3)               echo "brew install python" ;;
        # Homebrew's Pillow goes into Homebrew's Python. When `python3` here is Apple's own (/usr/bin), as on a
        # Mac with a versioned Homebrew Python but no plain python3 from it, `brew install pillow` alone left
        # the checker still saying Pillow is missing. Installing Homebrew's python too makes python3 its.
        pillow)
          if [ "$(command -v "${PYBIN:-python3}" 2>/dev/null)" = /usr/bin/python3 ]; then
            echo "brew install python pillow   (then open a NEW terminal: python3 here is Apple's, which Homebrew's Pillow does not reach)"
          else
            echo "brew install pillow"
          fi ;;
        ffmpeg|uv|node)        echo "brew install $1" ;;
        *)                     echo "install $1" ;;
      esac ;;
    win)
      # Python goes in for her account only (--scope user), the way scripts/_win-sac.sh installs its 3.11:
      # winget's machine-wide Python asks for an administrator's Yes, and the per-user one lands in
      # AppData/Local/Programs/Python, where the python shim already looks. ffmpeg and uv are portable
      # packages winget already keeps per user, so no flag is needed. Node stays machine-wide and keeps its
      # one Yes: its only per-user package is a bare zip whose winget entry names node alone, not the npx
      # HyperFrames runs on, and no PC has proved npx is reachable from it.
      case "$1" in
        ffmpeg)  winget_line Gyan.FFmpeg ;;
        uv)      winget_line astral-sh.uv ;;
        node)    winget_line OpenJS.NodeJS.LTS ;;
        python3) echo "$(winget_line Python.Python.3.12) --scope user" ;;
        pillow)  echo "python scripts/pip-install.py pillow" ;;   # retries safely if uv manages this Python
        *)       echo "install $1" ;;
      esac ;;
    *) echo "install $1" ;;
  esac
}

# ── how a row looks ────────────────────────────────────────────────────────────────────────────────
# Colour only when a person is reading a terminal. Piped into a file (collect-report.sh does that), plain.
# Named for what each one says: here, stopped, not yet, by the way, the words to act on, and back to plain.
TONE_OK= TONE_STOP= TONE_NOTE= TONE_QUIET= TONE_STRONG= TONE_END=
if [ -t 1 ]; then
  TONE_OK="$(tput setaf 2)"; TONE_STOP="$(tput setaf 1)"; TONE_NOTE="$(tput setaf 3)"
  TONE_QUIET="$(tput dim)";  TONE_STRONG="$(tput bold)"; TONE_END="$(tput sgr0)"
fi

REPO="$(engine_dir)"
missing=0          # things a reel needs that are not here yet. The closing line and the exit status come from it.
tally() { missing=$((missing + 1)); }

# A row is a mark, what the thing does for her reels (the tool's own name in brackets), then any detail.
# No fixed column: the job comes first, and a name is only there for whoever has to type it.
line()    { if [ -n "${3:-}" ]; then printf "  %s %s${TONE_QUIET}: %s${TONE_END}\n" "$1" "$2" "$3"; else printf "  %s %s\n" "$1" "$2"; fi; }
ok()      { line "${TONE_OK}✓${TONE_END}" "$1" "${2:-}"; }
note()    { line "${TONE_NOTE}!${TONE_END}" "$1" "${2:-}"; }
todo()    { note "$1" "$2"; tally; }                         # a note that counts toward what is left
section() { printf "\n${TONE_STRONG}%s${TONE_END}${TONE_QUIET}%s${TONE_END}\n" "$1" "${2:+  ($2)}"; }

# Something that is not on this machine yet: one row saying so, then the line that installs it, alone on its
# own line so it can be copied whole. An ordinary gap gets a yellow dot, not a red cross: on a new machine a
# missing tool is a step not taken yet, never a defect (CLAUDE.md, "never dress a normal state as a fault").
get() {   # get <mark> <label> <install key>
  printf "  %s %s ${TONE_NOTE}is not on this machine yet${TONE_END}\n      %s\n" "$1" "$2" "$(install_cmd "$3")"
  tally
}
need() {   # need <command> <label> <install key> [detail when present]
  if command -v "$1" >/dev/null 2>&1; then ok "$2" "${4:-}"; else get "${TONE_NOTE}•${TONE_END}" "$2" "$3"; fi
}

# bounded <seconds> <command...>: the command's output (stderr dropped), or nothing at all when it is still
# running after <seconds>. GNU timeout when it is really GNU's: Git Bash usually has it, but Windows' own
# C:\Windows\System32\timeout.exe is a different program (a pause) and may be the one PATH answers, so the
# name alone proves nothing. Otherwise the command runs in the background and is stopped at the limit.
bounded() {
  local secs="$1" out pid ticks=0; shift
  if timeout --version 2>/dev/null | grep -qiE 'GNU|coreutils'; then
    timeout "$secs" "$@" 2>/dev/null
    return 0
  fi
  out="$(mktemp "${TMPDIR:-/tmp}/check-setup.XXXXXX" 2>/dev/null)" || out="${TMPDIR:-/tmp}/check-setup.$$"
  "$@" > "$out" 2>/dev/null &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$ticks" -ge $((secs * 5)) ]; then
      kill "$pid" 2>/dev/null; sleep 0.2; kill -9 "$pid" 2>/dev/null
      : > "$out"   # half an answer is no answer
      break
    fi
    sleep 0.2; ticks=$((ticks + 1))
  done
  wait "$pid" 2>/dev/null
  cat "$out" 2>/dev/null; rm -f "$out"
  return 0
}

printf "\n${TONE_STRONG}Reels Editing Engine: what this computer has${TONE_END}  ${TONE_QUIET}(%s)${TONE_END}\n" "$MACHINE"
printf "${TONE_QUIET}  A checklist, not an error report. It installs nothing and changes nothing. A dot is something\n"
printf "  this machine does not have yet, with the line that gets it.${TONE_END}\n\n"

if [ "$OS" = win ]; then
  printf "  ${TONE_QUIET}Windows: the engine runs from Git Bash, never from PowerShell.${TONE_END}\n\n"
elif grep -qi microsoft /proc/version 2>/dev/null; then
  # WSL looks like Linux to uname. It is a Windows machine, and the engine runs on Windows itself.
  printf "  ${TONE_NOTE}This is WSL (Linux inside Windows).${TONE_END} The engine runs in ${TONE_STRONG}Git Bash on Windows itself${TONE_END}, not inside WSL:\n"
  printf "    open ${TONE_STRONG}Git Bash${TONE_END} from the Start menu (install it with: winget install -e --id Git.Git --scope user), go to this folder there, and run this again.\n\n"
elif [ "$OS" != mac ]; then
  printf "  ${TONE_NOTE}This engine supports macOS and Windows. Run it on one of those.${TONE_END}\n"
  printf "  ${TONE_NOTE}On a Windows PC, run this from Git Bash (part of Git for Windows); PowerShell and cmd cannot run it.${TONE_END}\n\n"
fi

# ── Windows-only: two settings that fail silently and look like unrelated bugs later ──
if [ "$OS" = win ]; then
  # winget is how every install below happens. Windows 10 PCs from 2016-2019 can be missing it (it ships
  # with "App Installer" from the Store), and then every install line dies "command not found".
  if command -v winget >/dev/null 2>&1; then
    ok "Windows' installer (winget)" "the tools below install with it, no admin account needed"
    printf "    ${TONE_QUIET}After each install, open a NEW Git Bash window (and restart Claude Code once) so the new tool is found.${TONE_END}\n"
  else
    line "${TONE_STOP}✗${TONE_END}" "Windows' installer (winget)" "not here. Open the Microsoft Store, search \"App Installer\", install it, then close and reopen Git Bash."
    printf "    ${TONE_QUIET}(direct link: ms-windows-store://pdp/?productid=9NBLGGH4NNS1). Nothing else below can install until this is in.${TONE_END}\n"
    tally
  fi
  if [ "${PYTHONUTF8:-}" = "1" ]; then
    ok "reading accents and emoji (UTF-8 mode)" "Python reads and writes UTF-8, so accents, curly quotes and emoji are safe"
  else
    note "reading accents and emoji (UTF-8 mode)" "NOT set. Run: setx PYTHONUTF8 1  and  setx PYTHONIOENCODING utf-8  then reopen this terminal."
    printf "    ${TONE_QUIET}Without it, any caption, hook or brand-kit line with a curly quote, accent or emoji\n"
    printf "    crashes the step that reads it, and status symbols crash the step that prints them.${TONE_END}\n"
  fi
  # MSYS_NO_PATHCONV: Git Bash rewrites arguments that look like POSIX paths ("/v") into Windows paths
  # before a native .exe sees them, which turns the switch into garbage and makes this read as OFF on every PC.
  # reg prints a blank line and the key's name before the value line ("LongPathsEnabled REG_DWORD 0x1"), so
  # only the line carrying the value is kept; reading every line made this row fail on a PC that was set.
  LP="$(MSYS_NO_PATHCONV=1 reg query 'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem' /v LongPathsEnabled 2>/dev/null | tr -d ' \r' | sed -n 's/.*0x//p')"
  if [ "$LP" = "1" ]; then
    ok "deep CapCut folders (long paths)" "Windows' 260-character path limit is lifted"
  else
    note "deep CapCut folders (long paths)" "Windows still caps paths at 260 characters. CapCut draft folders nest deep; a long user name or a deep project folder can fail mid-build with a confusing error."
  fi
  # The folder guard: Windows' ransomware protection (Controlled Folder Access) lets only the programs on its
  # allow-list write inside her Documents, Desktop, Pictures, Videos, Music and OneDrive, and a refused write
  # comes back as "No such file or directory", which reads like a missing file. Four programs write in this
  # folder for the engine, and Windows allows each one on its own: Git Bash, Python, node (every graphics
  # render) and ffmpeg (every cut and pass). The row rests on three readings: a real write from this shell
  # (made, then removed), the guard's own setting as Defender reports it (no admin needed; nothing comes back
  # when Defender or PowerShell will not answer, which is no problem in itself), and whether this folder sits
  # in one of the places the guard covers.
  guard_row="writing in this folder (folder guard)"
  guard_fix="Move the engine folder to C:\\Users\\<you>\\Projects, or let bash.exe, python.exe, node.exe and ffmpeg.exe through: Windows Security > Virus & threat protection > Ransomware protection > Allow an app through Controlled folder access."
  # Bounded: on some PCs Defender's PowerShell module never answers (a third-party antivirus in its place, a
  # policy that holds it), and an unbounded call left this whole checklist sitting there looking hung. No
  # answer in time reads the same as no answer at all, which the last branch below already words calmly.
  guard="$(bounded "${REELS_ENGINE_PS_TIMEOUT:-20}" powershell.exe -NoProfile -NonInteractive -Command '(Get-MpPreference).EnableControlledFolderAccess' | tr -d '[:space:]')"
  case "$REPO" in
    */Documents/*|*/Desktop/*|*/Pictures/*|*/Videos/*|*/Music/*|*/OneDrive/*|*/OneDrive\ -\ */*) guarded_place=1 ;;
    *) guarded_place=0 ;;
  esac
  write_test="$REPO/.engine-write-test.$$"
  if { : > "$write_test"; } 2>/dev/null; then rm -f "$write_test"; shell_writes=1; else shell_writes=0; fi
  if [ "$shell_writes" -eq 0 ]; then
    line "${TONE_STOP}✗${TONE_END}" "$guard_row" "this shell just tried to write here and could not."
    printf "    ${TONE_QUIET}The usual cause is Controlled Folder Access, whatever its setting reads as. %s${TONE_END}\n" "$guard_fix"
    tally
  elif [ "$guard" = "1" ] && [ "$guarded_place" -eq 1 ]; then
    note "$guard_row" "Controlled Folder Access is on and this folder is one it guards. Git Bash can write here, but Python, node and ffmpeg are allowed one by one, so a cut, a render or an edit can still stop with \"No such file or directory\". $guard_fix"
  elif [ "$guard" = "1" ]; then
    ok "$guard_row" "Controlled Folder Access is on, and this folder is outside what it guards"
  elif [ "$guard" = "0" ]; then
    ok "$guard_row" "Controlled Folder Access is off, so nothing stops the engine writing here"
  elif [ "$guard" = "2" ]; then
    ok "$guard_row" "Controlled Folder Access only audits (it logs, it does not block)"
  else
    note "$guard_row" "this shell can write here, and Windows did not say whether Controlled Folder Access is on (no Defender, or PowerShell blocked: no problem in itself). If Python, node or ffmpeg ever stop with \"No such file or directory\" for a file that is plainly there, that is the likely cause. Keeping the engine folder in C:\\Users\\<you>\\Projects, away from the folders the guard covers, avoids it."
  fi
fi

# ── Where the engine folder lives. A synced folder quietly evicts big video files. ──
# This used to be checked ONLY inside "set me up". Anyone who set up before that check existed was never
# told, and nothing ever looked again: a tester built her whole first reel from OneDrive\Desktop and her
# setup reported the location as fine, because she set up one version before the check was added. It runs
# here too now, so every run of this script re-checks, including for people who installed long ago.
# Same rules as set-me-up, kept in step with it.
ENGINE_HERE="$(cd "$(dirname "$0")" && pwd -P)"
SYNC=""
if [ "$OS" = win ]; then
  case "$ENGINE_HERE" in
    */OneDrive/*|*/OneDrive\ -\ */*) SYNC=onedrive ;;
    *) for _od in "${OneDrive:-}" "${OneDriveCommercial:-}"; do
         [ -n "$_od" ] || continue
         _odp="$(cygpath -u "$_od" 2>/dev/null)"
         case "$ENGINE_HERE" in "$_odp"/*) SYNC=onedrive ;; esac
       done ;;
  esac
elif [ "$OS" = mac ]; then
  case "$ENGINE_HERE" in
    "$HOME"/Documents/*|"$HOME"/Desktop/*)
      [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Documents" ] && SYNC=icloud ;;
  esac
fi
if [ "$SYNC" = onedrive ]; then
  note "where the engine lives" "This engine is inside OneDrive, which syncs it. When your drive fills up, OneDrive moves big video files off your computer and leaves a placeholder that looks real, and an edit stops partway through. Say \"move my engine\" and it moves the whole folder to C:\\Users\\<you>\\Projects. Your settings and brand kit go with it."
elif [ "$SYNC" = icloud ]; then
  note "where the engine lives" "This engine is in Desktop or Documents, which iCloud syncs. When your drive fills up, iCloud moves big video files off your Mac and leaves a placeholder, and an edit stops partway through. Say \"move my engine\" and it moves the whole folder to your home folder. Your settings and brand kit go with it."
elif [ "$OS" = win ] || [ "$OS" = mac ]; then
  ok "where the engine lives" "not in a synced folder, so your video files stay put"
fi

# ── Before any install line: can Homebrew even run on this Mac? ────────────────────────────────────
# The chip is settled first and admin rights second. Where Homebrew cannot run at all, asking whether the
# account is an administrator is the wrong question, and it sends her into System Settings to fix
# something that was never the problem.
rosetta_terminal() {
  printf "  ${TONE_NOTE}This Mac has an Apple Silicon chip, but this terminal runs under Rosetta${TONE_END} (Intel translation).\n"
  printf "    Everything below would install the slow Intel versions. One checkbox fixes it for good:\n"
  printf "    ${TONE_STRONG}quit Terminal${TONE_END}, open ${TONE_STRONG}Applications > Utilities${TONE_END}, click ${TONE_STRONG}Terminal${TONE_END} once, ${TONE_STRONG}File > Get Info${TONE_END},\n"
  printf "    UNTICK ${TONE_STRONG}\"Open using Rosetta\"${TONE_END}, then reopen Terminal and run this again.\n"
  printf "    ${TONE_QUIET}Worth doing now: on the right side of that checkbox is the full-speed, fully supported setup.${TONE_END}\n\n"
}
# No Homebrew line on this machine, ever. Homebrew's installer aborts before it even asks for a password
# ("Homebrew on macOS is only supported on Apple Silicon processors!"), so what people report is a password
# prompt that never came, not an error message.
intel_route() {
  if [ "$MACCLASS" = arm64 ] && mac_os_at_least "$MAC_BREW_OLDEST" 0; then
    # An Apple-chip Mac Homebrew supports, pinned to this route because Homebrew's install died at Apple's
    # Command Line Tools download (the fallback in scripts/_mac-arch.sh). Its macOS is NOT the reason, so
    # do not tell her it is old, and do not suggest an update that would change nothing.
    printf "  ${TONE_STRONG}This Mac uses the no-Homebrew setup${TONE_END}, because Apple's developer tools could not be downloaded\n"
    printf "    for Homebrew here. That is Apple's server, not your Mac, and nothing about the engine is reduced.\n"
    printf "    Every tool comes from its own download:\n"
    printf "    ${TONE_STRONG}bash scripts/intel-mac-install.sh all${TONE_END}\n"
    printf "    ${TONE_QUIET}No password except the Node installer, which asks in a normal Mac window.${TONE_END}\n\n"
  elif [ "$MACCLASS" = arm64 ]; then
    # An Apple-chip Mac below MAC_BREW_OLDEST. Homebrew's installer would warn, then sit on Apple's
    # Command Line Tools download, and every tool after it would compile for hours. Same no-Homebrew
    # route as an Intel Mac, with Apple-chip builds. Nothing about the engine itself is reduced.
    printf "  ${TONE_STRONG}This Mac has an Apple chip and runs macOS %s${TONE_END}, so the setup skips Homebrew.\n" "$(sw_vers -productVersion 2>/dev/null)"
    printf "    Homebrew only supports macOS %s and newer now, so on this Mac its installer stalls. That is not a\n" "$MAC_BREW_OLDEST"
    printf "    broken install and it is not your machine. Everything installs from each tool's own download:\n"
    printf "    ${TONE_STRONG}bash scripts/intel-mac-install.sh all${TONE_END}\n"
    printf "    ${TONE_QUIET}No password except the Node installer, which asks in a normal Mac window. Every feature works.${TONE_END}\n"
    printf "    ${TONE_QUIET}Optional, and the smoothest route: update macOS first (System Settings > General > Software Update,${TONE_END}\n"
    printf "    ${TONE_QUIET}free on every Apple-chip Mac), then run setup again for the standard path.${TONE_END}\n\n"
  elif ! mac_intel_supported; then
    printf "  ${TONE_STOP}This Mac is an Intel Mac running macOS %s${TONE_END}, which is older than the engine can set up.\n" "$(sw_vers -productVersion 2>/dev/null)"
    printf "    ${TONE_NOTE}macOS 11 (Big Sur) is the floor.${TONE_END} Below it the speech tools would all need pinning back several\n"
    printf "    years at once, and that combination has never been tested. Updating macOS, if this Mac can take\n"
    printf "    a newer one, is the honest fix. Nothing below will work until then.\n\n"
  else
    printf "  ${TONE_STRONG}This is an Intel Mac${TONE_END} (%s), so the setup takes a different route.\n" "$(mac_cpu_brand)"
    printf "    Homebrew stopped supporting Intel Macs, and its installer now quits ${TONE_STRONG}before${TONE_END} it asks for your\n"
    printf "    password. That is not a broken install and it is not your machine. Everything still installs,\n"
    printf "    just from each tool's own download instead:\n"
    printf "    ${TONE_STRONG}bash scripts/intel-mac-install.sh all${TONE_END}\n"
    printf "    ${TONE_QUIET}No password except the Node installer, which asks in a normal Mac window. Full route:${TONE_END}\n"
    printf "    ${TONE_QUIET}product/INTEL-MAC-ROUTE.md${TONE_END}\n\n"
  fi
}
# Homebrew's own installer, pasted once by her: it asks for the Mac password, so it cannot be run for her.
BREW_INSTALLER='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
homebrew_first() {
  # Homebrew's installer needs sudo, which a Standard (non-admin) macOS account cannot run.
  # Catch that here so the buyer sees a clear fix instead of a raw "user may not run sudo" wall.
  if ! id -Gn 2>/dev/null | tr ' ' '\n' | grep -qx admin; then
    printf "  ${TONE_NOTE}This Mac account is NOT an administrator${TONE_END} — Homebrew (and the tools below) need admin rights to install, so setup cannot run on a Standard account. This is not broken and not your fault.\n"
    printf "    ${TONE_STRONG}Fix (about a minute):${TONE_END} on this Mac open ${TONE_STRONG}System Settings > Users & Groups${TONE_END}, and for this account turn ON \"Allow this user to administer this computer\" (whoever first set up this Mac can do it). Then fully quit and reopen Claude Code and run setup again.\n"
    printf "    ${TONE_STRONG}Or:${TONE_END} log in to the Mac's administrator account and run setup there instead.\n\n"
  elif [ -x /opt/homebrew/bin/brew ] || [ -x /usr/local/bin/brew ]; then
    # Installed but not on PATH in this terminal: the classic "brew: command not found" right after a fresh
    # install, on both Apple Silicon (/opt/homebrew) and Intel (/usr/local). Not a broken install.
    _brewbin=/opt/homebrew/bin/brew; [ -x "$_brewbin" ] || _brewbin=/usr/local/bin/brew
    printf "  ${TONE_NOTE}Homebrew is installed but this terminal can't see it yet${TONE_END} (normal right after installing it). Paste this once, then reopen the terminal:\n"
    printf "    ${TONE_STRONG}echo 'eval \"\$(%s shellenv)\"' >> ~/.zprofile && eval \"\$(%s shellenv)\"${TONE_END}\n\n" "$_brewbin" "$_brewbin"
  else
    printf "  ${TONE_NOTE}Homebrew not found${TONE_END} — it's the delivery truck the installs below ride on, and Claude walks you through it during \"set me up.\" The one line it'll have you paste:\n"
    printf "    ${TONE_STRONG}%s${TONE_END}\n" "$BREW_INSTALLER"
    printf "    ${TONE_QUIET}If it stops at Apple's Command Line Tools (\"not currently available from the Software Update server\"),${TONE_END}\n"
    printf "    ${TONE_QUIET}close that Terminal and use the no-Homebrew setup instead: MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all${TONE_END}\n\n"
  fi
}
case "$OS" in
  mac) if [ "$MACROUTE" = direct ]; then intel_route
       elif ! command -v brew >/dev/null 2>&1; then
         case "$MACCLASS" in rosetta) rosetta_terminal ;; *) homebrew_first ;; esac
       fi ;;
esac

# ── Rough cut: reading, cutting and transcribing her clips ────────────────────────────────────────────
section "Rough cut" "reading, cutting and transcribing your clips"
need ffprobe "the clip reader (ffprobe, comes with ffmpeg)" ffmpeg "reads each clip's length and format"
need ffmpeg  "the video engine (ffmpeg)"                    ffmpeg "cuts, levels and joins every clip, and every later audio and video pass"
# uv still counts when it is missing, even though the rough cut can fetch it for itself (word-timings.sh,
# ensure_uv): that only happens while the speech tools are being BUILT, and it can settle on Python's own pip
# instead. Every build after the cut runs the engine's measuring tools through `uv run` (where she sits in
# frame, workflows/subject-zones.py, which every route needs; the CapCut handoff; head framing), and nothing
# fetches uv for those. Its uvx is only an optional shortcut for the HyperFrames caption toolkit, which falls
# back without it, so it is not mentioned.
need uv      "the transcriber helper (uv)"                  uv     "runs the engine's measuring tools (where you sit in frame, the CapCut handoff) and builds the speech tools the first time the rough cut runs"

# How fast transcription will be. Information only: the transcriber picks its own model for the machine and
# nothing here counts toward what is left.
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
  ok "transcription speed" "NVIDIA ${GPU_NAME:-graphics card} found, and the transcriber uses it on its own: much faster than the processor alone"
elif [ "$OS" != mac ]; then
  note "transcription speed" "no NVIDIA graphics card, so transcription runs on the processor. That is normal and it works; on a Windows machine without one the engine picks a lighter, faster model on its own, so it takes minutes, not hours."
# The chip comes from MACCLASS (scripts/_mac-arch.sh), the same answer every other line of this check and the
# problem report give. This line used to read sysctl on its own, before uname: with /usr/sbin off PATH that came
# back empty and an M1 was called "an Intel Mac" right under "Computer: Mac (arm64)" (a buyer, 2026-10-22).
elif [ "$MACCLASS" = intel ]; then
  # A true Intel Mac: no Apple Silicon acceleration, and word-timings.sh already drops to a lighter model here.
  # Calling this the fast Mac path would promise a speed her first transcription is not going to have.
  note "transcription speed" "an Intel Mac, so there is no Apple Silicon speed-up. That is normal and it works; the engine picks a lighter, faster model on its own, so it takes minutes, not hours."
elif [ "$MACCLASS" = arm64 ]; then
  ok "transcription speed" "Apple Silicon, the normal fast Mac path"
elif [ "$MACCLASS" = rosetta ]; then
  # Apple Silicon hardware, but this shell runs translated (uname -m says x86_64). Tools installed from here
  # are Intel builds and the transcriber would settle for a lighter model the chip does not need. A setup fix,
  # not a hardware limit, so it is never called an Intel Mac.
  note "transcription speed" "an Apple Silicon chip, but this terminal runs under Rosetta (Intel translation), usually a Terminal setting or a Homebrew carried over from an older Mac. It works, but tools installed from here run slower than this Mac can. Fix it once: Terminal's Get Info > untick 'Open using Rosetta', reinstall the tools, and transcription gets the full-speed path."
fi

# The rough cut flags suspect words against a system wordlist. macOS ships one; Windows has none. Information only.
if [ -f /usr/share/dict/words ]; then
  ok "suspect-word check (wordlist)" "here, so the rough cut flags words the transcriber may have misheard"
elif [ "$OS" = win ]; then
  ok "suspect-word check (wordlist)" "Windows has none, so the rough cut skips that advisory scan; everything else works"
fi

# Smart App Control changes how the speech tools are built on a Windows PC. Information only.
if [ "$OS" = win ] && [ -f "$SHIMS/_win-sac.sh" ]; then
  . "$SHIMS/_win-sac.sh"
  case "$(win_sac_state)" in
    on)   note "Smart App Control" "on. It blocks unsigned downloads, so the speech tools are built from the signed Python 3.11 from python.org, with versions it allows. The first edit installs that Python once if it is missing. Leave Smart App Control on." ;;
    eval) ok "Smart App Control" "in evaluation mode (it watches, it does not block)" ;;
    off)  ok "Smart App Control" "off" ;;
    *)    ok "Smart App Control" "could not read it (fine on most PCs). If a step ever says an Application Control policy blocked a file, tell Claude" ;;
  esac
fi

# ── Build: captions, text, graphics, placement and sound ──────────────────────────────────────────────
section "Build" "captions, text, graphics, where you sit in frame, and sound"
# python3 is judged by whether it RUNS. Being on PATH proves nothing on two fronts:
#   Windows puts a Microsoft Store alias called python3 on PATH. `command -v` finds it; running it only
#     prints an install-me message.
#   A Mac without Apple's Command Line Tools has /usr/bin/python3 as a placeholder, and RUNNING that one
#     opens the "install the developer tools?" dialog over her screen (measured on a tester's fresh Intel
#     Mac, 2026-09-18). So on a Mac the placeholder is recognised by path and never run; the shim below,
#     which knows the same rule, does the looking instead.
_cs_apple_stub=0
# The tools are judged by whether python3 is really IN the developer folder, not by `xcode-select -p`
# alone, which answers yes for a folder a failed install left configured but empty (mac_clt_stub).
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && [ "$(command -v python3 2>/dev/null)" = "/usr/bin/python3" ]; then
  if command -v mac_clt_stub >/dev/null 2>&1; then
    mac_clt_stub /usr/bin/python3 && _cs_apple_stub=1
  elif ! xcode-select -p >/dev/null 2>&1; then
    _cs_apple_stub=1
  fi
fi
runs()    { "$1" -c '' >/dev/null 2>&1; }             # runs <interpreter>: does it actually execute?
imports() { "$1" -c "import $2" >/dev/null 2>&1; }   # imports <interpreter> <module>
PY_LABEL="the caption + text helper (python3)"
PY_CMD=""          # the interpreter that actually ran: the one every later Python check here uses
if [ "$_cs_apple_stub" -eq 0 ] && runs python3; then
  PY_CMD=python3
  ok "$PY_LABEL" "draws the caption and text overlays and runs the engine's steps"
elif command -v python >/dev/null 2>&1 && runs python; then
  PY_CMD=python
  # The engine reaches Python through the shim, which prefers the interpreter that has Pillow when a PC has
  # more than one. Check with the same one, so this report and the engine never disagree.
  if [ -f "$SHIMS/_python3-shim.sh" ]; then
    . "$SHIMS/_python3-shim.sh" 2>/dev/null || true
    [ "${_P3_OK:-0}" -eq 1 ] && PY_CMD=python3
  fi
  note "$PY_LABEL" "here as 'python' rather than 'python3'; the engine handles that on its own (scripts/_python3-shim.sh)"
else
  # Neither name ran. Before calling Python missing, ask the same shim every other engine script uses: it
  # also knows the `py -3` launcher and real interpreters on disk under neither name, including the
  # uv-managed Python the engine's own Windows setup installs into AppData/Roaming/uv/python/. A checker
  # that disagrees with the engine sends her off to reinstall what she has (PC test, 2026-09-18).
  if [ -f "$SHIMS/_python3-shim.sh" ]; then
    . "$SHIMS/_python3-shim.sh" 2>/dev/null || true
  fi
  # The shim's own verdict, read instead of trying `python3` again: on a fresh Mac that retry is exactly
  # the call that opens Apple's dialog (see _cs_apple_stub above).
  if [ "${_P3_OK:-0}" -eq 1 ]; then
    PY_CMD=python3
    note "$PY_LABEL" "found through scripts/_python3-shim.sh; the engine reaches it on its own, nothing to install"
  else
    get "${TONE_STOP}✗${TONE_END}" "$PY_LABEL" python3
  fi
fi
# The Microsoft Store Python as `python` cannot see files other apps put in AppData, which is where uv keeps the
# speech tools' own Python. Said in one line so a report shows which Python this is; venv_spawn.py goes around it.
if [ "$OS" = win ] && [ -f "$REPO/product/venv_spawn.py" ] \
   && python "$REPO/product/venv_spawn.py" --is-store-python >/dev/null 2>&1; then
  note "Python (Microsoft Store)" "'python' here is the Microsoft Store Python. Nothing to change: the engine starts its speech tools in a way it cannot block."
fi

# Caption and text images are drawn with Pillow: the engine's ffmpeg has no drawtext and no libass. Tried
# with the interpreter that actually ran above, never `python3` by name: on Windows that name is usually the
# Store alias, which imports nothing, and every PC would be told Pillow is missing.
if [ -z "$PY_CMD" ]; then
  :   # no Python ran at all; its row above already carries the fix
elif imports "$PY_CMD" PIL; then
  ok "the caption + text drawing kit (Pillow)"
else
  get "${TONE_NOTE}•${TONE_END}" "the caption + text drawing kit (Pillow)" pillow
fi

need node "the graphics engine (node)"                  node "renders every graphic through HyperFrames"
need npx  "the graphics launcher (npx, comes with node)" node "starts the HyperFrames command line"

# HyperFrames runs on Node 22 or newer. An older Node still passes `command -v`, so it is asked its version.
node_major()   { node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0; }
node_upgrade() {
  if [ "$OS" = win ]; then echo "winget upgrade $WINGET_FLAGS --id OpenJS.NodeJS.LTS   then reopen Git Bash"
  elif [ "$MACROUTE" = direct ]; then echo "bash scripts/intel-mac-install.sh node"
  else echo "brew upgrade node"; fi
}
node_too_old() { local major; major="$(node_major)"; [ "${major:-0}" -lt 22 ]; }
if command -v node >/dev/null 2>&1 && node_too_old; then
  node_seen="$(node -v | tr -d v)"
  printf "  ${TONE_NOTE}!${TONE_END} the graphics engine (node) ${TONE_NOTE}is v%s; HyperFrames needs 22 or newer${TONE_END}\n      %s\n" "$node_seen" "$(node_upgrade)"
  tally
fi

# Shipped inside the engine folder and reached for in the middle of a build, so a missing one fails there,
# not here. Absent means an incomplete download, and it counts.
bundled() {   # bundled <path inside the engine> <label> <what it does>
  if [ -f "$REPO/$1" ]; then ok "$2" "$3"; else todo "$2" "missing from the engine folder ($1). Download the engine zip again."; fi
}
bundled assets/models/face_detection_yunet_2023mar.onnx "the face finder (YuNet model)" \
  "measures where you sit in frame, so nothing is placed on you, and picks the cover frame"
# The index is what every build reads the sound library through, and it always ships (sfx/approved/ is the
# owner's own CapCut sounds and never does, so checking for it failed every buyer's setup).
bundled product/creative-vault/sfx/sfx-index.json "the sound library (sfx-index.json)" \
  "the matched sound effects every build places"

# ── Style pack fonts ──────────────────────────────────────────────────────────────────────────────────
# Each style pack names a font for every job (captions, hook, takeover, thoughts). The engine resolves them
# itself (capcut_font_doctor.py): a font file bundled in assets/fonts/ first, then a hand-map, then her own
# CapCut by name. What this script can check without Python is the bundled faces the packs land on.
section "Style pack fonts" "bundled with the engine, nothing to install"
bundled assets/fonts/Inter-Regular.otf "Inter, the starter face" \
  "the brand kit's starting font, and the face headlines and graphics fall back to"
bundled assets/fonts/Inter-Bold.otf "Inter Bold, the Butter pack's fallback face" \
  "stands in for Bloop on the Butter pack's thoughts and accent captions"
if [ -n "$PY_CMD" ]; then
  _doctor="python3"; [ "$OS" = win ] && _doctor="python"
  printf "    ${TONE_QUIET}Every other pack font comes from your CapCut by name. To check them all: %s product/capcut_font_doctor.py${TONE_END}\n" "$_doctor"
fi

# ── Finish in CapCut (Windows): two things about THIS PC that change where a draft lands. Neither blocks. ──
if [ "$OS" = win ] && [ -n "$PY_CMD" ]; then
  section "Finish in CapCut" "information: the engine adapts to both"
  if [ -f "$REPO/product/capcut_store_redirect.py" ]; then
    case "$("$PY_CMD" "$REPO/product/capcut_store_redirect.py" 2>/dev/null)" in
      "redirected: yes"*)
        note "Claude app (Microsoft Store)" "Windows keeps new files this Claude app writes into CapCut's folder private to Claude, so CapCut cannot see them. Each CapCut project is built in projects/_capcut-staging/ instead, and the engine adds it to CapCut for you when the build ends, with CapCut closed. If CapCut was open, it opens that folder: close CapCut, then double-click 'Add to CapCut.bat' there." ;;
      *) ok "CapCut drafts" "written straight into CapCut's own folder" ;;
    esac
  fi
  if [ -f "$REPO/product/capcut_installs.py" ]; then
    case "$("$PY_CMD" "$REPO/product/capcut_installs.py" 2>/dev/null | head -1)" in
      "capcut: both")
        note "CapCut" "two are installed: the desktop app and the Microsoft Store one. They keep separate project lists, and your projects show up in the DESKTOP CapCut only. Ask Claude to 'open my CapCut' to open the right one." ;;
      "capcut: store-only")
        todo "CapCut" "this is the Microsoft Store version, which cannot show the engine's projects. Install the free desktop CapCut from capcut.com and open it once." ;;
      "capcut: desktop")
        ok "CapCut" "the desktop app (the one that shows your projects)" ;;
      "capcut: none")
        note "CapCut" "could not find it yet. If it is not installed, get the free desktop CapCut from capcut.com and open it once." ;;
    esac
  fi
fi

printf "\n"
case "$missing" in
  0) printf "${TONE_OK}${TONE_STRONG}Nothing a reel needs is missing.${TONE_END} You can start editing.\n" ;;
  *) if [ "$missing" -eq 1 ]; then _it="One thing is"; else _it="$missing things are"; fi
     printf "${TONE_STRONG}%s left to install.${TONE_END} Nothing is wrong; this is a new machine. Run the line under each one, then run this again.\n" "$_it" ;;
esac

# ── On first use: each happens once, by itself or with one command ────────────────────────────────────
once() { printf "  %s ${TONE_STRONG}%s${TONE_END}: %s\n" "$1" "$2" "$3"; }   # once <mark> <name> <text>
# Each line asks whether its step already happened here. They were printed as "not installed" unconditionally,
# so a machine that had transcribed reels and filled its brand kit was still told both were still to come
# (a buyer's report, 2026-10-13; the same stale lines in two more).
# speech_tools_done: the speech tools' venv finished building (word-timings.sh writes .speech-tools-ready, or
# .deps-ok on an older build, as its very last step, holding what it verified). Either listener counts, at the
# same places word-timings.sh looks (scripts/_python3-shim.sh venv_home), including an earlier cache folder.
speech_tools_done() {
  local v
  for v in "${REELS_ENGINE_WHISPERX_VENV:-}" "${REELS_ENGINE_NOFW_VENV:-}" \
           "$HOME"/.cache/*/whisperx-venv "$HOME"/.cache/*/fasterwhisper-venv; do
    [ -n "$v" ] && [ -d "$v" ] || continue
    { [ -s "$v/.speech-tools-ready" ] || [ -s "$v/.deps-ok" ]; } && return 0
  done
  return 1
}
# speech_model_here: a Whisper model in the Hugging Face cache, where both listeners download it.
speech_model_here() {
  local hub="${HF_HUB_CACHE:-${HF_HOME:-$HOME/.cache/huggingface}/hub}" m
  for m in "$hub"/models--*[Ww]hisper*; do [ -d "$m" ] && return 0; done
  return 1
}
# brand_kit_done: the same count CLAUDE.md and the onboarding nudge use: no blank field left.
brand_kit_done() {
  [ -f "$REPO/brand-kit.md" ] || return 1
  [ "$(grep -e '{{' -e '<<' "$REPO/brand-kit.md" | grep -v -c -F '{{this}}')" = 0 ]
}
section "On first use" "each happens once"
if speech_tools_done; then
  if speech_model_here; then
    once "${TONE_OK}✓${TONE_END}" "Speech transcription" "ready (set up by an earlier edit)."
  else
    once "${TONE_QUIET}•${TONE_END}" "Speech transcription" "set up. Your next edit downloads its speech model once; give it a few minutes online."
  fi
elif [ "$MACCLASS" = intel ]; then
  # A different transcriber and a much smaller download. Quoting the WhisperX download at an Intel Mac would
  # be wrong, and discouraging on the machine least able to afford either.
  once "${TONE_QUIET}•${TONE_END}" "Speech transcription" "your first edit fetches the transcriber's own Python (~175 MB) and its speech model, one time. Give it a few minutes online."
  printf "    ${TONE_QUIET}On an Intel Mac this uses faster-whisper instead of WhisperX, automatically: WhisperX needs a piece of software that has no Intel build.${TONE_END}\n"
else
  once "${TONE_QUIET}•${TONE_END}" "WhisperX transcription" "your first edit fetches the transcriber's own Python and its large-v3 speech model (a few GB), one time. Give it a few minutes online."
fi
# On Windows, a bare `npx` pasted into PowerShell runs npx.ps1, which PowerShell refuses by default
# ("running scripts is disabled on this system"). npx.cmd ships with every Windows Node install and is not
# subject to that policy, so it works as pasted, with no security setting changed.
NPX_CMD="npx"; [ "$OS" = win ] && NPX_CMD="npx.cmd"
# The pin comes from product.json, the one place it is set (post-update.py writes the marker for that version).
HF_PIN="$(sed -n 's/.*"hyperframes": *"\([^"]*\)".*/\1/p' "$REPO/product.json" 2>/dev/null | head -1)"
if [ -n "$HF_PIN" ] && [ -f "$REPO/_local/hf-browser-$HF_PIN.ok" ]; then
  once "${TONE_OK}✓${TONE_END}" "Render engine" "ready (hyperframes@$HF_PIN, the version the engine is pinned to)."
else
  once "${TONE_QUIET}•${TONE_END}" "Render engine" "run this once in the engine folder:  ${TONE_STRONG}${NPX_CMD} hyperframes@${HF_PIN:-latest} browser ensure${TONE_END}  (it fetches the ~150 MB headless browser that draws the graphics, at the pinned version). ${TONE_QUIET}\`doctor\` only reports; it downloads nothing.${TONE_END}"
fi
# The renderer's browser has needed macOS 13 before (it aborted at launch on macOS 12), and no macOS 12 Mac has
# proved the older browser HyperFrames now picks there. Information only, never counted: the CapCut route needs
# no renderer, and product/reel_render.py says the same thing if a render here does fail that way.
if [ "$OS" = mac ] && command -v mac_os_at_least >/dev/null 2>&1 && ! mac_os_at_least 13 0; then
  once "${TONE_QUIET}•${TONE_END}" "Graphics renders" "this Mac runs macOS $(sw_vers -productVersion 2>/dev/null), and the graphics renderer may not run on macOS 12 or older. Every reel can still finish as an editable CapCut draft: say \"keep it raw\"."
fi
if brand_kit_done; then
  once "${TONE_OK}✓${TONE_END}" "Homebase" "${TONE_STRONG}brand-kit.md${TONE_END} is filled in, so reels sound like you."
else
  once "${TONE_QUIET}•${TONE_END}" "Homebase" "say \"build my homebase\" to fill in ${TONE_STRONG}brand-kit.md${TONE_END}, so reels sound like you (recommended, never required)."
fi
printf "\n"

# The verdict: 0 when nothing a reel needs is missing, 1 otherwise.
(( missing == 0 ))
