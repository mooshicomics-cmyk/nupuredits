# _mac-arch.sh — one source of truth for "which kind of Mac is this, and what installs here?"
#
# WHY: Homebrew's official installer now ABORTS unless `uname -m` is arm64:
#
#     UNAME_MACHINE="$(/usr/bin/uname -m)"
#     # On macOS, support Apple Silicon only
#     if [[ "${UNAME_MACHINE}" != "arm64" ]]
#     then
#       abort "Homebrew on macOS is only supported on Apple Silicon processors!"
#
# The whole Mac setup path in this engine was Homebrew, so on a non-arm64 Mac every install line the
# engine handed over was a line that could not work. The abort happens one step BEFORE the password
# prompt, so nothing hangs and nothing errors — the buyer just waits for a password prompt that is
# never coming. That is the reported symptom: "it never asked for my password."
#
# `uname -m` says x86_64 on two VERY different machines, and they need opposite answers:
#
#   1. An Apple Silicon Mac whose Terminal has "Open using Rosetta" ticked. The hardware is fine.
#      The fix is one checkbox, after which the NORMAL, fully supported Homebrew path works. Telling
#      this person "you have an Intel Mac" is a misreport that sends her down a slower path forever.
#   2. A genuine Intel Mac. Homebrew is gone for good here and every tool needs its own route.
#
# `hw.optional.arm64` reports the real HARDWARE regardless of translation (it is absent on a true
# Intel Mac), which is what separates the two. This is the same discrimination word-timings.sh and
# check-setup.sh were already each doing by hand; it lives here now so the three cannot drift apart.
#
# Everything below is report-only. Nothing here installs, writes, or needs sudo.

# mac_sysctl <args> — sysctl, found even when /usr/sbin is not on PATH. A shell started with a short PATH
# (/usr/bin:/bin) has no `sysctl` at all, and every reading then came back empty: an Apple-chip Mac was told
# "an Intel Mac" in the problem report's setup lines, right under "Computer: Mac (arm64)", and its chip line
# was blank (a buyer on an M1, 2026-10-22). The one on PATH comes first, so a test's stand-in still answers.
mac_sysctl() {
  if command -v sysctl >/dev/null 2>&1; then sysctl "$@"
  elif [ -x /usr/sbin/sysctl ]; then /usr/sbin/sysctl "$@"
  else return 1
  fi
}

# arm64 | rosetta | intel   (empty string when this is not a Mac at all)
mac_arch_class() {
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 0
  if [ "$(uname -m 2>/dev/null)" = "arm64" ]; then
    echo arm64
  elif [ "$(mac_sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    echo rosetta
  else
    echo intel
  fi
}

# Major macOS version as an integer: 26, 15, 13, 12 ... and 10 for Catalina and older.
# Used to pick wheels, NOT to gate anything on marketing names.
mac_os_major() {
  sw_vers -productVersion 2>/dev/null | cut -d. -f1
}

# mac_os_at_least <major> [minor] — true when this Mac runs that macOS or newer. An unreadable version
# answers true, so a sw_vers hiccup can never push a working Mac onto a slower route.
mac_os_at_least() {
  _v="$(sw_vers -productVersion 2>/dev/null)"
  _M="$(printf '%s' "$_v" | cut -d. -f1)"; _n="$(printf '%s' "$_v" | cut -d. -f2)"
  case "$_M" in ''|*[!0-9]*) return 0 ;; esac
  case "$_n" in ''|*[!0-9]*) _n=0 ;; esac
  [ "$_M" -gt "$1" ] || { [ "$_M" -eq "$1" ] && [ "$_n" -ge "${2:-0}" ]; }
}

# ── Can Homebrew serve THIS Mac? ─────────────────────────────────────────────
#
# Chip is not the whole answer any more. Homebrew only builds ready-made packages (bottles) for the macOS
# versions it supports, and its installer's MACOS_OLDEST_SUPPORTED is 15.0. MEASURED 2026-09-30 from
# formulae.brew.sh: ffmpeg, node and uv ship arm64 bottles for sequoia (15), tahoe (26) and newer only.
# On an Apple-chip Mac below 15 the installer prints a "not supported" warning, then sits on Apple's
# Command Line Tools download ("Finding available software"), and every `brew install` after it would
# compile from source for hours or fail. First reported by a launch-day buyer on macOS 13 (Ventura),
# whose setup "stays there" at exactly that line.
#
# Those Macs take the SAME no-Homebrew route an Intel Mac takes (scripts/intel-mac-install.sh), with
# Apple-chip builds instead of Intel ones. Only the install route changes: the chip is still arm64, so
# WhisperX, restart trimming and music generation all still run.
#
# Raise this when Homebrew raises its floor, and re-measure the bottles when you do.
MAC_BREW_OLDEST="${MAC_BREW_OLDEST:-15}"

# ── The Command Line Tools fallback ──────────────────────────────────────────
#
# A supported macOS is not the whole answer either. Homebrew's installer needs Apple's Command Line
# Tools, and it fetches them from Apple's Software Update server. On 2026-10-02 a buyer on an Apple-chip
# Mac on macOS 15+ (route `brew`) got Apple's own popup at that step: "Can't install the software because
# it is not currently available from the Software Update server." Homebrew cannot continue without the
# tools (it clones itself with git, and git IS one of those tools), so the normal route was a dead end
# on that Mac. Seen as either that popup, or `xcode-select: error: invalid developer directory` in the
# Homebrew Terminal.
#
# The way out is the direct route, which needs none of Apple's developer tools at all: every tool comes
# as a ready-made build (VERIFIED 2026-10-02 on 15+: ffmpeg/ffprobe static, uv, uv-managed Python,
# Pillow wheel, Node .pkg; the transcriber resolves to 107 arm64 wheels with `--only-binary :all:`, and
# hyperframes' npm tree has no native builds and no git dependencies). She runs it with
#     MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all
# and the installer PINS this Mac to `direct` (MAC_ROUTE_PIN). Without the pin every later check would
# say `brew` again: check-setup.sh would print the Homebrew line she already watched fail, and "set me
# up" would hand it to her a second time.
#
# The pin lives with her tools (~/.local/share), not in the engine folder, so a fresh engine download on
# the same Mac keeps it. It only counts while Homebrew is NOT installed: if she (or a later macOS update)
# gets Homebrew working, the normal route takes over again by itself, and a developer's Mac that has
# Homebrew can run MAC_DIRECT_ROUTE=1 without ever being pinned.
MAC_ROUTE_PIN="${MAC_ROUTE_PIN:-$HOME/.local/share/reels-editing-engine/mac-route}"
_MA_SYS_ROOT="${_MA_SYS_ROOT:-}"   # tests only: prefix for the system-wide Homebrew locations below

# True when a working Homebrew is on this Mac, on PATH or not.
mac_has_brew() {
  command -v brew >/dev/null 2>&1 && return 0
  [ -x "$_MA_SYS_ROOT/opt/homebrew/bin/brew" ] || [ -x "$_MA_SYS_ROOT/usr/local/bin/brew" ]
}

# True when this Mac is pinned to the direct route by the fallback above, and still has no Homebrew.
mac_route_pinned() {
  [ -f "$MAC_ROUTE_PIN" ] && [ "$(sed -n 1p "$MAC_ROUTE_PIN" 2>/dev/null)" = direct ] && ! mac_has_brew
}

# mac_clt_has <tool> — true when Apple's developer tools are really installed AND carry <tool>.
#
# WHY NOT just `xcode-select -p`: it only reports the CONFIGURED path, and answers 0 for a folder that is
# not there (measured: `DEVELOPER_DIR=/nonexistent xcode-select -p` prints /nonexistent, exit 0). A failed
# or half-finished Command Line Tools install leaves exactly that state, and then running /usr/bin/git or
# /usr/bin/python3 does not run anything: it opens Apple's "install the developer tools?" dialog again,
# right on top of the buyer who just watched it fail. So the tool itself has to be in the folder.
mac_clt_has() {
  _ma_dev="$(xcode-select -p 2>/dev/null)" || return 1
  [ -n "$_ma_dev" ] && [ -x "$_ma_dev/usr/bin/$1" ]
}

# mac_clt_stub <path> — true when <path> is one of Apple's /usr/bin developer-tool placeholders (git,
# python3, make, clang ...) and the tools behind it are missing, so EXECUTING it would open the dialog.
mac_clt_stub() {
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 1
  case "$1" in /usr/bin/*) ;; *) return 1 ;; esac
  ! mac_clt_has "${1#/usr/bin/}"
}

# mac_clt_shield <dir> — on a Mac without Apple's developer tools, write a stand-in `install_name_tool`
# into <dir> and print <dir>; anywhere else, print nothing. Put it in front of PATH for a `uv python
# install` (or a `uv venv` that may download a Python):
#     _cs="$(mac_clt_shield "$TMP/clt-shield")"; PATH="${_cs:+$_cs:}$PATH" uv python install 3.11
# WHY: after downloading a Python, uv runs `install_name_tool` to tidy one library name. On a Mac without
# the tools that name is Apple's placeholder (it links libxcselect), so the run would open the "install
# the developer tools?" dialog: on the very Mac whose tools download just failed, the direct route would
# pop it again. MEASURED 2026-10-02 (uv 0.12.22, tools hidden): uv only warns when the call fails ("Failed
# to patch the install name ... building Python native extensions") and the Python works; the engine
# builds no native extensions, so a stand-in that quietly fails is the honest answer.
mac_clt_shield() {
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 0
  mac_clt_stub /usr/bin/install_name_tool || return 0
  mkdir -p "$1" 2>/dev/null || return 0
  printf '#!/bin/sh\n# stand-in for Apple'"'"'s install_name_tool placeholder (scripts/_mac-arch.sh mac_clt_shield)\nexit 1\n' \
    > "$1/install_name_tool" 2>/dev/null && chmod +x "$1/install_name_tool" && printf '%s' "$1"
}

# brew | direct | rosetta   (empty when this is not a Mac)
#   brew     Apple-chip Mac on a macOS Homebrew still supports. The normal route.
#   direct   no Homebrew: a true Intel Mac, an Apple-chip Mac older than MAC_BREW_OLDEST, or an
#            Apple-chip Mac pinned by the Command Line Tools fallback (mac_route_pinned).
#   rosetta  Apple-chip Mac in a Rosetta terminal. One checkbox, then it is `brew` or `direct`.
# MAC_DIRECT_ROUTE=1 forces `direct` on an Apple-chip Mac. Support hands it to a buyer whose Command Line
# Tools download failed (the fallback above), and the release test uses it to run the route for real on
# a current Mac.
mac_install_route() {
  case "$(mac_arch_class)" in
    intel)   echo direct ;;
    rosetta) echo rosetta ;;
    arm64)
      if [ "${MAC_DIRECT_ROUTE:-0}" = 1 ] || ! mac_os_at_least "$MAC_BREW_OLDEST" 0 || mac_route_pinned
      then echo direct
      else echo brew; fi ;;
  esac
}

# Which Node line this Mac can run. Node 24 (the current LTS) needs macOS 13.5 (nodejs/node BUILDING.md,
# v24.x: "macOS >= 13.5"); Node 22 runs on 11.0+ and is still a supported LTS. HyperFrames needs 22 or
# newer, so a Mac below 13.5 gets 22 and everything else gets the newest LTS.
mac_node_line() {
  if mac_os_at_least 13 5; then echo lts; else echo 22; fi
}

# The human-readable chip string, for telling her what we actually detected.
mac_cpu_brand() {
  mac_sysctl -n machdep.cpu.brand_string 2>/dev/null
}

# ── Where Intel installs go ─────────────────────────────────────────────────
#
# ~/.local/bin, NOT /usr/local/bin. On a fresh Intel Mac with no Homebrew, /usr/local is root-owned
# and writing there needs sudo — which would re-introduce the exact password moment this route exists
# to avoid. ~/.local/bin needs no password, and it is already where uv's own installer puts uv, so
# setup is creating it anyway. _path-shim.sh lists it for ffmpeg/ffprobe so the engine finds them.
MAC_INTEL_BIN="${MAC_INTEL_BIN:-$HOME/.local/bin}"

# The install route for one tool on a Mac without Homebrew (route `direct`: a true Intel Mac, or an
# Apple-chip Mac below MAC_BREW_OLDEST). Echoes a command the buyer (or Claude) can run.
mac_intel_hint() {
  case "$1" in
    ffmpeg|ffprobe)
      echo "bash scripts/intel-mac-install.sh ffmpeg   (static build for this chip → $MAC_INTEL_BIN, no password)" ;;
    node)
      echo "bash scripts/intel-mac-install.sh node     (downloads the Node installer; double-click it)" ;;
    uv)
      echo "curl -LsSf https://astral.sh/uv/install.sh | sh   (then reopen the terminal)" ;;
    python3)
      echo "uv python install 3.11 --default   (uv manages the Python; no Homebrew needed)" ;;
    pillow)
      echo "python3 scripts/pip-install.py pillow" ;;
    *)
      echo "see product/INTEL-MAC-ROUTE.md" ;;
  esac
}

# ── The transcription pin ───────────────────────────────────────────────────
#
# faster-whisper's VAD runs on onnxruntime, and onnxruntime's macOS x86_64 wheels are capped by the
# macOS version the wheel was built against. MEASURED from PyPI (cp311 wheels), not guessed:
#
#   1.15.0 – 1.16.3   macosx_10_15_x86_64     macOS 10.15+
#   1.17.0 – 1.19.2   macosx_11_0_universal2  macOS 11+
#   1.20.0 – 1.22.1   macosx_13_0_universal2  macOS 13+
#   1.23.0 – 1.23.2   macosx_13_0_x86_64      macOS 13+
#   1.24.0 and later  (no macOS x86_64 wheel at all — Intel was dropped)
#
# So the cap is real and permanent, and there are THREE bands, not two. Pinning explicitly keeps the
# resolver from walking down the version list one wheel at a time on a machine that is already slow.
# (An earlier note here said "1.16.3 below macOS 13", which would needlessly hand a Monterey machine
# an onnxruntime three years older than the one it can actually run.)
#
# A Mac's caps only. Off a Mac there is no sw_vers, the version reads empty, and the bands below used to take that
# for macOS 10 and hand a Windows PC 'onnxruntime<=1.16.3': on a Windows ARM64 (Snapdragon) laptop that version
# has no wheel at all and the speech tools could never install (a buyer, 2026-10-24). Every other machine gets
# nothing here and resolves onnxruntime, ctranslate2 and av on its own.
mac_intel_onnx_pin() {
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 0
  _m="$(mac_os_major)"
  case "${_m:-0}" in
    ''|*[!0-9]*) echo 'onnxruntime<=1.19.2' ;;   # unreadable version: pick the safe middle band
    *) if   [ "$_m" -ge 13 ]; then echo 'onnxruntime<=1.23.2'
       elif [ "$_m" -ge 11 ]; then echo 'onnxruntime<=1.19.2'
       else                        echo 'onnxruntime<=1.16.3'
       fi ;;
  esac
}

# ctranslate2 and av carry their own macOS floors (also measured from PyPI):
#   ctranslate2  4.6.1+ needs macOS 11 · 4.6.0 needs 10.13 · <=4.3.1 needs 10.9
#   av          14.0.0+ needs macOS 11 · <=13.1.0 needs 10.13
# On macOS 11+ the current versions of both are fine, so only onnxruntime needs a pin there.
# macOS 10.15 would need all three capped at once; see mac_intel_supported below.
mac_intel_extra_pins() {
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 0
  _m="$(mac_os_major)"
  case "${_m:-0}" in
    ''|*[!0-9]*) ;;
    *) [ "$_m" -lt 11 ] && echo 'ctranslate2<=4.6.0 av<=13.1.0' ;;
  esac
}

# Is this Intel Mac new enough for the route to work at all?
# macOS 11 (Big Sur) is the honest floor: below it ctranslate2, av and onnxruntime must ALL be pinned
# back years at once, and that combination is not something this engine has ever run.
mac_intel_supported() {
  _m="$(mac_os_major)"
  case "${_m:-0}" in
    ''|*[!0-9]*) return 0 ;;
    *) [ "$_m" -ge 11 ] ;;
  esac
}

# ── JSON without Python ─────────────────────────────────────────────────────
#
# json_str <text> — print <text> as a double-quoted JSON string. Pure tr + sed.
#
# WHY: the Intel install route records every step to _local/install-route.json, and it used to quote
# each value by piping it through `python3 -c 'import json...'`. On the very machine that route exists
# for — a fresh Intel Mac — there is no Python yet, and /usr/bin/python3 is Apple's placeholder that
# opens the "install the developer tools?" dialog when run. So recording step ONE of the install popped
# a dialog nobody asked for, and the value came back empty. Values here are tool names, versions and
# paths, so: backslash and quote are escaped, tabs and newlines become spaces, other control characters
# are dropped. That is a valid JSON string for everything this file ever holds.
json_str() {
  printf '"%s"' "$(printf '%s' "${1:-}" | tr '\n\r\t' '   ' | tr -d '\000-\010\013\014\016-\037\177' \
                 | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
}
