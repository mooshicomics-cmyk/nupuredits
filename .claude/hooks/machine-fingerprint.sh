#!/usr/bin/env bash
# machine-fingerprint.sh, run when a session starts: rewrites _local/machine.txt with what this computer is
# (engine version, OS, chip class, processor, cores, memory, and when it was recorded). When she reports a
# crash or a slow render, the answer to "what machine is this?" is already in her folder for Claude to read,
# so nobody has to ask her to run a check first. A render stall report carries a copy of it too.
#
# It writes that one file and sends nothing anywhere: _local/ is kept out of git and out of the ship bundle,
# so the report leaves her computer only if she pastes it somewhere herself.
#
# On three Mac routes that need a different setup (a true Intel Mac, an Apple chip on a macOS older than
# Homebrew supports, a terminal running under Rosetta) it also hands Claude a short note about that route.
#
# This can run before setup has installed anything, so it leans only on what a new Mac or Git Bash already
# carries (uname, sysctl, sed, printf). Whatever happens, its exit status is 0.

# Only inside the engine folder (product.json sits beside it): a session opened in any other folder must
# never get a _local/ made in it. update-check.sh tests for the same file.
[ -f product.json ] || exit 0

_mf_out="_local/machine.txt"
mkdir -p _local 2>/dev/null || exit 0

# Engine version straight out of product.json, without a JSON parser.
_mf_ver="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' product.json 2>/dev/null | head -1)"
[ -n "$_mf_ver" ] || _mf_ver="unknown"

_mf_class=""; _mf_cpu=""; _mf_os=""; _mf_cores=""; _mf_mem=""

if [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then
  # sysctl lives in /usr/sbin, which a shell started with a short PATH lacks: every reading below then came
  # back empty and an Apple-chip Mac under Rosetta read as Intel (scripts/_mac-arch.sh mac_sysctl, a buyer on an
  # M1, 2026-10-22). Added last, so a sysctl already on PATH still answers first.
  case ":$PATH:" in *:/usr/sbin:*) ;; *) PATH="$PATH:/usr/sbin" ;; esac
  # Three different machines all answer x86_64 to `uname -m`, and telling them apart is the single most
  # load-bearing fact in Mac support. Rosetta does not fake sysctl, so read the hardware, not the shell.
  # Kept byte-identical to scripts/_mac-arch.sh mac_arch_class() on purpose — if these two ever disagree,
  # the engine would route one way and report the other, which is worse than having no report at all.
  if [ "$(uname -m 2>/dev/null)" = "arm64" ]; then
    _mf_class=arm64
  elif [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    _mf_class=rosetta
  else
    _mf_class=intel
  fi
  # tr: this value is interpolated into the hand-built JSON at the bottom. A quote, backslash or
  # newline would emit malformed hook output and break the session's context. update-check.sh strips
  # the same characters from the feed summary for the same reason. Never remove this.
  _mf_cpu="$(sysctl -n machdep.cpu.brand_string 2>/dev/null | tr -d '"\\' | tr '\n' ' ')"
  _mf_os="macOS $(sw_vers -productVersion 2>/dev/null)"
  # Physical vs logical matters: the transcription model ladder keys off physical cores, and a 4-core
  # Intel laptop reporting 8 logical was part of why it used to be handed the heavy model.
  _mf_cores="$(sysctl -n hw.physicalcpu 2>/dev/null) physical / $(sysctl -n hw.logicalcpu 2>/dev/null) logical"
  _mf_memb="$(sysctl -n hw.memsize 2>/dev/null)"
  [ -n "$_mf_memb" ] && _mf_mem="$((_mf_memb / 1073741824)) GB"
else
  # Windows under Git Bash, or anything else. Best effort, never fatal.
  _mf_class="$(uname -m 2>/dev/null)"
  _mf_os="$(uname -s 2>/dev/null) $(uname -r 2>/dev/null)"
  _mf_cores="${NUMBER_OF_PROCESSORS:-unknown} logical"
  # Git Bash (like Linux) serves /proc/cpuinfo and /proc/meminfo, so the processor and memory are one
  # read away with no jq, no python and no PowerShell. Without these a PC's report said "unknown" for
  # both, and a stall report (which embeds this file) could not say whether the machine was a slow one.
  # Same tr as the Mac branch: this value is interpolated into hand-built JSON further down.
  _mf_cpu="$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo 2>/dev/null | head -1 | tr -d '"\\' | tr '\n' ' ')"
  _mf_memk="$(sed -n 's/^MemTotal:[[:space:]]*\([0-9]*\).*/\1/p' /proc/meminfo 2>/dev/null | head -1)"
  [ -n "$_mf_memk" ] && _mf_mem="$(( (_mf_memk + 524288) / 1048576 )) GB"
fi

[ -n "$_mf_cpu" ] || _mf_cpu="unknown"
[ -n "$_mf_os" ]  || _mf_os="unknown"
[ -n "$_mf_mem" ] || _mf_mem="unknown"

{
  printf 'Reels Editing Engine — machine report\n'
  printf 'engine      %s\n' "$_mf_ver"
  printf 'os          %s\n' "$_mf_os"
  printf 'chip class  %s\n' "$_mf_class"
  printf 'cpu         %s\n' "$_mf_cpu"
  printf 'cores       %s\n' "$_mf_cores"
  printf 'memory      %s\n' "$_mf_mem"
  printf 'recorded    %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null)"
} > "$_mf_out" 2>/dev/null

# Tell Claude about the machine ONLY when it is one of the routes that has actually burned someone. On a
# normal Apple Silicon Mac this stays silent, because a note every session on every machine is noise and
# noise gets ignored. No quotes or backslashes in these strings: the printf below builds raw JSON.
_mf_note=""
if [ "$_mf_class" = intel ]; then
  _mf_note='This is a true Intel Mac ('"$_mf_cpu"'). Homebrew CANNOT be installed here - its installer aborts before the password prompt, which is why the symptom is that setup never asked for a password. Use the Intel route: bash scripts/intel-mac-install.sh all. Transcription switches to faster-whisper automatically. Full detail in product/INTEL-MAC-ROUTE.md. Never hand her a brew install line.'
elif [ "$_mf_class" = arm64 ] && [ -f scripts/_mac-arch.sh ] \
     && [ "$(bash -c '. scripts/_mac-arch.sh; mac_install_route' 2>/dev/null)" = direct ]; then
  # Apple chip, but a macOS older than Homebrew supports (scripts/_mac-arch.sh MAC_BREW_OLDEST). Asked
  # of _mac-arch.sh rather than re-derived here, so the floor lives in exactly one place.
  _mf_note='This Mac has an Apple chip but runs '"$_mf_os"', older than Homebrew supports. Do NOT hand her the Homebrew installer - on this macOS it warns, then sits on the Command Line Tools download (Finding available software), and every brew install after it compiles for hours. Before installing anything, offer her an OPTIONAL choice (set-me-up skill spells it out): update macOS first for the smoothest standard setup, or keep going now on the no-Homebrew route, bash scripts/intel-mac-install.sh all (it detects the Apple chip and fetches Apple-chip builds). Never push the update. Every feature works either way.'
elif [ "$_mf_class" = rosetta ]; then
  _mf_note='This Mac IS Apple Silicon, but this terminal is running translated under Rosetta, so everything reports x86_64 and Homebrew refuses. Do NOT send her down the Intel route. One checkbox fixes it: quit Terminal, Get Info (Cmd+I), untick Open using Rosetta, reopen. On the other side is the normal, faster setup.'
fi

if [ -n "$_mf_note" ]; then
  _mf_note="$_mf_note"' A full machine report is at _local/machine.txt - read it before diagnosing anything on this machine, and never ask her to run a hardware check to learn what is already in that file.'
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$_mf_note"
fi

exit 0
