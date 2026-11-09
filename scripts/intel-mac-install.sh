#!/usr/bin/env bash
# intel-mac-install.sh — install the prerequisites on a Mac where Homebrew cannot serve us.
#
# Three kinds of Mac land here (scripts/_mac-arch.sh → mac_install_route = direct):
#   1. A true Intel Mac. Homebrew's installer aborts on anything that is not arm64.
#   2. An Apple-chip Mac on a macOS older than Homebrew supports (MAC_BREW_OLDEST, 15 today). Homebrew
#      has no ready-made packages there, so every `brew install` would compile for hours or fail.
#   3. An Apple-chip Mac on 15+ whose Homebrew install died at Apple's Command Line Tools download
#      ("not currently available from the Software Update server"). Run with MAC_DIRECT_ROUTE=1; this
#      route needs none of Apple's developer tools, and the run pins the Mac to it (MAC_ROUTE_PIN).
# The name is historical (the Intel route came first); skills and docs point at it, so it stays.
# Each tool here comes straight from its own official build, for this Mac's chip.
#
#   ./scripts/intel-mac-install.sh ffmpeg   # ffmpeg + ffprobe, static builds for this chip, no password
#   ./scripts/intel-mac-install.sh node     # downloads Node's own .pkg and opens it
#   ./scripts/intel-mac-install.sh uv       # uv's official installer script
#   ./scripts/intel-mac-install.sh git      # a quiet git stand-in, only where git is Apple's placeholder
#   ./scripts/intel-mac-install.sh all
#
# Everything lands in ~/.local/bin, which needs NO password. /usr/local/bin would need sudo on a
# fresh Intel Mac (root-owned until Homebrew chowns it), and a password prompt is the single thing
# this whole route exists to avoid. _path-shim.sh already looks in ~/.local/bin, so the engine finds
# these without the buyer editing a PATH.
#
# Node is the one exception: it installs system-wide through Apple's own installer UI, which asks for
# her password in a normal Mac window, not blind in a terminal. That is a friendlier moment than
# Homebrew ever was, and there is no user-local Node .pkg to use instead.
set -uo pipefail

_d="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$_d/scripts/_mac-arch.sh"

BIN="$MAC_INTEL_BIN"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/intel-mac-install.XXXXXX")"

if [ -t 1 ]; then G=$(tput setaf 2); R=$(tput setaf 1); Y=$(tput setaf 3); B=$(tput bold); N=$(tput sgr0)
else G=; R=; Y=; B=; N=; fi

say()  { printf "  %s\n" "$*"; }
good() { printf "  ${G}✓${N} %s\n" "$*"; }
bad()  { printf "  ${R}✗${N} %s\n" "$*" >&2; }

# ── Recording what actually happened ────────────────────────────────────────
#
# There is no Intel Mac on this side of the engine. Every fact about how this route behaves in the
# real world has to come home from a buyer's machine, and a buyer cannot be asked to narrate a
# terminal. So each step records itself: what was attempted, where it came from, how long it took,
# whether it worked, and what version landed. `product/make-handoff.py hardware-diagnostic` reads
# this file, and SHE decides whether to send it. Nothing here is transmitted by this script.
#
# A FAILED step is the valuable one. Failures are recorded with the same care as successes.
ROUTE_LOG="$_d/_local/install-route.json"
ROUTE_STEPS=""

_route_step() {  # _route_step <tool> <source> <seconds> <exit> <version> <landed>
  # json_str (scripts/_mac-arch.sh) — NOT python3: on the fresh Intel Mac this runs on there is no Python
  # yet, and asking /usr/bin/python3 opens Apple's developer-tools dialog instead of answering.
  _esc() { json_str "${1:-}"; }
  # The report is scoped to hardware and timings. A path is useful (it says which route ran) but the
  # account name in it is not ours to collect, so $HOME always becomes "~" before anything is written.
  _rd() { printf '%s' "${1:-}" | sed "s#^$HOME#~#"; }
  set -- "$1" "$2" "$3" "$4" "$5" "$(_rd "${6:-}")"
  ROUTE_STEPS="${ROUTE_STEPS:+$ROUTE_STEPS,}{\"tool\":$(_esc "$1"),\"source\":$(_esc "$2"),\"seconds\":${3:-0},\"exit\":${4:-0},\"version\":$(_esc "$5"),\"landed\":$(_esc "$6")}"
}

_route_write() {
  mkdir -p "$(dirname "$ROUTE_LOG")" 2>/dev/null || return 0
  {
    printf '{"when":"%s","arch_class":"%s","macos":"%s","chip":"%s",' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${CLASS:-unknown}" "$(sw_vers -productVersion 2>/dev/null)" "$(mac_cpu_brand)"
    printf '"cpu_physical_cores":%s,"cpu_logical_cores":%s,' \
      "$(sysctl -n hw.physicalcpu 2>/dev/null || echo 0)" "$(sysctl -n hw.logicalcpu 2>/dev/null || echo 0)"
    printf '"bin":"%s","steps":[%s]}\n' "$(printf '%s' "$BIN" | sed "s#^$HOME#~#")" "$ROUTE_STEPS"
  } > "$ROUTE_LOG" 2>/dev/null || true
}
trap '_route_write; rm -rf "$TMP"' EXIT

# Wall-clock seconds, integer, portable (no `date +%s%N` on macOS).
_now() { date +%s; }

# ── Reading the download index without Python ───────────────────────────────
#
# The Node lookup runs BEFORE Python is on the machine: `node` can be asked for on its own. On a fresh
# Intel Mac the only python3 is Apple's placeholder, which opens the "install the developer tools?" dialog
# and answers nothing, so reading the index through `python3 -c` made the install fail at its first line.
# The document is small and regular, so tr + sed + grep read it, and print nothing for anything they do
# not recognise.

# nodejs.org's dist/index.json -> the newest LTS release that ships a macOS .pkg (v22.21.1, say). The file is
# a list of releases, newest first, each one a flat object whose "lts" is false or the release's codename;
# splitting at every "}" puts one release on each line however the file happens to be wrapped.
_node_lts_pkg_version() {
  tr -d '\n\r' | tr '}' '\n' \
    | grep -E '"lts"[[:space:]]*:[[:space:]]*("[^"]|true)' | grep '"osx-x64-pkg"' | head -1 \
    | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

# Same index, newest release of ONE major line (22, say) that ships a macOS .pkg. Needed because the
# newest LTS is not always one this Mac can run: Node 24 needs macOS 13.5 (see mac_node_line), and
# installing it on 13.4 or older leaves a node that refuses to start. The "version" field is the only
# thing matched, so an "lts" of false (a Current release in that line) never sneaks in either: only
# even-numbered majors are LTS, and those are the only lines mac_node_line ever asks for.
_node_line_pkg_version() {  # _node_line_pkg_version <major>
  tr -d '\n\r' | tr '}' '\n' \
    | grep -E "\"version\"[[:space:]]*:[[:space:]]*\"v$1\\." | grep '"osx-x64-pkg"' | head -1 \
    | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

# Refuse to run on the wrong machine. On an Apple-chip Mac that Homebrew still supports, the normal
# Homebrew path is right and much better; on a Rosetta'd terminal the fix is a checkbox, not this script.
CLASS="$(mac_arch_class)"
case "$CLASS" in
  arm64)
    if [ "$(mac_install_route)" != direct ]; then
      bad "This is an Apple Silicon Mac on a macOS Homebrew supports. Use the normal setup (Homebrew)."
      say "If Homebrew's install already failed at Apple's Command Line Tools (\"not currently available from"
      say "the Software Update server\", or \"invalid developer directory\"), run this instead:"
      say "  MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all"
      exit 2
    fi
    # The Command Line Tools fallback (scripts/_mac-arch.sh): forced onto this route on a Mac Homebrew
    # supports but could not install on. Pin it, so check-setup.sh and "set me up" stop offering the
    # Homebrew line she already watched fail. Never on a Mac that has Homebrew (a developer's test run).
    if [ "${MAC_DIRECT_ROUTE:-0}" = 1 ] && mac_os_at_least "$MAC_BREW_OLDEST" 0 && ! mac_has_brew; then
      mkdir -p "$(dirname "$MAC_ROUTE_PIN")" 2>/dev/null \
        && printf 'direct\n# Command Line Tools fallback, %s, macOS %s. Delete this file to go back to Homebrew.\n' \
             "$(date -u +%Y-%m-%d)" "$(sw_vers -productVersion 2>/dev/null)" > "$MAC_ROUTE_PIN" 2>/dev/null \
        && say "This Mac now stays on the no-Homebrew setup (Apple's developer tools could not be installed)."
    fi ;;
  rosetta)
    bad "This is an Apple Silicon Mac, but this terminal is running under Rosetta."
    say "Fix it once instead of installing Intel tools: quit Terminal, find it in Applications > Utilities,"
    say "File > Get Info, UNTICK \"Open using Rosetta\", reopen it, and run setup again."
    exit 2 ;;
  "")
    bad "Not a Mac. This script is only for Intel Macs."
    exit 2 ;;
esac

if ! mac_intel_supported; then
  bad "macOS $(sw_vers -productVersion) is older than this route supports (macOS 11 Big Sur is the floor)."
  say "Below Big Sur the speech tools would all have to be pinned back several years at once, and that"
  say "combination has never been tested here. Say so plainly rather than shipping a second dead end."
  exit 2
fi

mkdir -p "$BIN"

# ── ffmpeg / ffprobe ────────────────────────────────────────────────────────
# Intel: evermeet.cx publishes the long-standing static Intel macOS builds of ffmpeg and ffprobe, as
# single self-contained binaries in a zip.
# Apple chip: evermeet is Intel-only (it would run, slowly, through Rosetta). ffmpeg.martin-riedl.de
# publishes static arm64 builds with a stable "latest release" redirect, one binary per zip. VETTED
# 2026-09-30 on 9.0.2: native arm64, LC_BUILD_VERSION minos 12.0, links only /System and /usr/lib,
# Developer ID signed (Team KU3N25YGLU), and carries every encoder and filter the engine calls
# (libx264, libx265, h264_videotoolbox, aac, libmp3lame, flac, prores_ks, qtrle, png, libvpx; plus
# drawtext and subtitles, which the Homebrew build lacks).
#
# Nothing downloaded here reaches her PATH unchecked. Each source is verified the strongest way it allows:
#   Apple chip (martin-riedl): stays on "latest", because every build is Developer ID signed. The binary
#     must carry an intact signature that chains to Apple AND belongs to Martin Riedl's team, checked with
#     codesign (part of macOS itself, not Apple's developer tools). A self-signed copy claiming the same
#     Team ID fails the Apple-anchor half, a tampered one fails the signature itself.
#   Intel (evermeet): its binaries are NOT code signed (checked 2026-10-05 on 9.0.2: "code object is not
#     signed at all"), and its downloads redirect to a mirror. So it is pinned: one exact version, one exact
#     sha256 per zip, measured from evermeet on 2026-10-05 (two downloads, same hash). minos 10.13, so it
#     runs on the Big Sur floor. To move the pin: download both zips, run `openssl dgst -sha256` on each,
#     confirm `ffmpeg -version` names the new release, then change all three lines together.
# Anything that fails its check is deleted before it is unzipped or run, and the step fails closed.
#
# Intel has a SECOND source, because one is not enough: a buyer got HTTP 429 "Too Many Connections" from
# evermeet for over 75 minutes (2026-10-21) and setup sat blocked on ffprobe. evermeet is asked twice (a short
# wait between), then osxexperts.net, which publishes static Intel macOS builds too. VETTED 2026-10-21 on 8.0:
# x86_64, LC_BUILD_VERSION minos 11.0 (the Big Sur floor), links only /System and /usr/lib, NOT code signed, and
# carries every encoder and filter the engine calls (libx264, libx265, h264_videotoolbox, aac, libmp3lame, flac,
# prores_ks, qtrle, png, libvpx; drawtext, subtitles, ebur128, alimiter, colorspace, unpremultiply). Its file names
# carry no full version, so it is pinned the same way, by sha256 (two downloads, same hash, zips dated 2025-08-22);
# if the site ever swaps the file, the check fails closed and evermeet stays the way in. Once one tool came from
# the second source, the other does too, so ffmpeg and ffprobe stay one release.
#
# Apple chip has a SECOND source too: ffmpeg.martin-riedl.de answered HTTP 521 (its server down) all through
# 2026-10-21 and every Apple-chip buyer on this route stopped at the ffmpeg step. martin-riedl is asked twice (the
# same short wait), and its download must still carry Martin Riedl's signature before it is trusted; then
# osxexperts.net, which publishes static Apple-chip builds as well. VETTED 2026-10-21 on 9.0: native arm64,
# LC_BUILD_VERSION minos 12.0 (runs on 13.x, the buyers this route serves), links only /System and /usr/lib, only
# AD-HOC signed (no Team ID, so codesign proves nothing about who built it), and carries every encoder and filter the
# engine calls (libx264, libx265, h264_videotoolbox, aac, libmp3lame, flac, prores_ks, qtrle, png, libvpx; drawtext,
# subtitles, ebur128, alimiter, colorspace, unpremultiply). So it is pinned by sha256 like the Intel builds (two
# downloads, same hash; served with Last-Modified 2026-08-09). Its file name says only "9", so when the site moves it
# to a later 9.x the check fails closed and martin-riedl stays the way in until the pin is moved. Once one tool came
# from osxexperts the other does too.
FFMPEG_ARM_TEAM="KU3N25YGLU"            # Developer ID Application: Martin Riedl
EVERMEET_FFMPEG_VERSION="9.0.2"
_evermeet_sha256() {  # _evermeet_sha256 <ffmpeg|ffprobe> -> the pinned sha256 of that tool's zip
  case "$1" in
    ffmpeg)  echo "4acc0be580f9b2788029eb7bd4d645ff87968911b0a62aeeb3940d42d54558d5" ;;
    ffprobe) echo "24a9c968cd4da72d99c7245e914b921815835eb6dff01d99868031aebaf1d439" ;;
  esac
}
OSXEXPERTS_FFMPEG_VERSION="8.0"
_osxexperts_url() { echo "https://www.osxexperts.net/${1}80intel.zip"; }
_osxexperts_sha256() {  # _osxexperts_sha256 <ffmpeg|ffprobe> -> the pinned sha256 of that tool's zip
  case "$1" in
    ffmpeg)  echo "2d24d22db78c87f394a5822867acd5c5dc5e762cd261a44bd26923f3a5af3e07" ;;
    ffprobe) echo "0b6576104a95c1b39d4939e2df86f8f7cf1d55287ff57da48777d94605d12feb" ;;
  esac
}
OSXEXPERTS_ARM_FFMPEG_VERSION="9.0"
_osxexperts_arm_url() { echo "https://www.osxexperts.net/${1}9arm.zip"; }
_osxexperts_arm_sha256() {  # _osxexperts_arm_sha256 <ffmpeg|ffprobe> -> the pinned sha256 of that tool's zip
  case "$1" in
    ffmpeg)  echo "d0c06c5c68ce48af3143b262f7a9118a7c9f67de1e237fcc24ffb14df9c67af9" ;;
    ffprobe) echo "0c94fbdd8917022f28115eca512196cf4648732bc9e5db9ec8896c7e519d02aa" ;;
  esac
}
# Seconds to wait before asking the first source (evermeet on Intel, martin-riedl on Apple chip) a second time.
# Short on purpose: a 429 at evermeet has lasted over an hour, a 521 at martin-riedl a whole afternoon.
INTEL_FETCH_WAIT="${INTEL_FETCH_WAIT:-10}"

# The switch to the second source goes in _local/fallbacks.log (pure shell: no Python on this Mac yet), so
# /report-a-problem shows it. A copy of the installer without scripts/_fallbacks.sh beside it just skips the note.
REELS_ENGINE_ROOT="${REELS_ENGINE_ROOT:-$_d}"
if [ -f "$_d/scripts/_fallbacks.sh" ]; then . "$_d/scripts/_fallbacks.sh"; else note_fallback() { :; }; fi

# _fetch <url> <out> -> 0 when <out> holds the download. Leaves the HTTP status in $_http (429 = rate limited).
_fetch() {
  _http="$(curl -fsSL -m 600 -w '%{http_code}' -o "$2" "$1" 2>/dev/null)" && [ -s "$2" ] && return 0
  rm -f "$2"; return 1
}

# _intel_zip <tool> <out> -> 0 when <out> is the pinned zip of that tool from one of the two sources. Sets $_src,
# $_tried (what failed, for the step log) and $_pinfail (1 when a download came but was not the pinned copy).
_INTEL_SRC=""
_intel_zip() {
  _tried=""; _pinfail=0
  if [ "$_INTEL_SRC" != osxexperts ]; then
    for _try in 1 2; do
      _src="evermeet.cx"; url="https://evermeet.cx/ffmpeg/$1-$EVERMEET_FFMPEG_VERSION.zip"
      if _fetch "$url" "$2"; then
        _got="$(_sha256 "$2")"
        [ -n "$_got" ] && [ "$_got" = "$(_evermeet_sha256 "$1")" ] && { _INTEL_SRC=evermeet; return 0; }
        rm -f "$2"; _pinfail=1; _tried="${_tried:+$_tried; }evermeet: not the pinned copy (got ${_got:-none})"
      else
        _tried="${_tried:+$_tried; }evermeet: HTTP ${_http:-no answer}"
      fi
      [ "$_try" = 1 ] || break
      if [ "$_pinfail" = 1 ]; then say "the download from evermeet.cx came back damaged; trying again in ${INTEL_FETCH_WAIT}s…"
      elif [ "${_http:-}" = 429 ]; then say "evermeet.cx is busy (too many downloads at once); trying again in ${INTEL_FETCH_WAIT}s…"
      else say "evermeet.cx did not answer; trying again in ${INTEL_FETCH_WAIT}s…"; fi
      [ "$INTEL_FETCH_WAIT" -gt 0 ] 2>/dev/null && command -v sleep >/dev/null 2>&1 && sleep "$INTEL_FETCH_WAIT"
    done
    say "fetching $1 from the second Intel source (osxexperts.net) instead…"
  fi
  for _try in 1 2; do
    _src="osxexperts.net"; url="$(_osxexperts_url "$1")"
    if _fetch "$url" "$2"; then
      _got="$(_sha256 "$2")"
      if [ -n "$_got" ] && [ "$_got" = "$(_osxexperts_sha256 "$1")" ]; then
        [ "$_INTEL_SRC" = osxexperts ] || note_fallback intel-mac-install \
          "$1 could not come from evermeet.cx ($_tried); installed the pinned osxexperts.net $OSXEXPERTS_FFMPEG_VERSION build instead"
        _INTEL_SRC=osxexperts; return 0
      fi
      rm -f "$2"; _pinfail=1; _tried="$_tried; osxexperts: not the pinned copy (got ${_got:-none})"
      break                                   # a wrong file will not turn right by asking again
    fi
    _tried="$_tried; osxexperts: HTTP ${_http:-no answer}"
    [ "$_try" = 1 ] && [ "$INTEL_FETCH_WAIT" -gt 0 ] 2>/dev/null && command -v sleep >/dev/null 2>&1 && sleep "$INTEL_FETCH_WAIT"
  done
  note_fallback intel-mac-install "$1 could not be downloaded from either Intel source ($_tried)"
  return 1
}

# _arm_zip <tool> <out> -> 0 when <out> is a trusted zip of that tool: martin-riedl's (its binary signed by Team
# $FFMPEG_ARM_TEAM, checked here so a bad copy moves on instead of stopping setup) or osxexperts' pinned one. Sets
# $_src, $_tried, $_pinfail (an osxexperts download that was not the pinned copy) and $_sigfail (a martin-riedl
# download whose binary was not signed by Martin Riedl).
_ARM_SRC=""
_arm_zip() {
  _tried=""; _pinfail=0; _sigfail=0
  if [ "$_ARM_SRC" != osxexperts ]; then
    for _try in 1 2; do
      _src="ffmpeg.martin-riedl.de"; url="https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$1.zip"
      if _fetch "$url" "$2"; then
        rm -rf "$TMP/sigcheck"; mkdir -p "$TMP/sigcheck"
        if unzip -qo "$2" -d "$TMP/sigcheck" 2>/dev/null && [ -f "$TMP/sigcheck/$1" ] \
           && _signed_by "$TMP/sigcheck/$1" "$FFMPEG_ARM_TEAM"; then
          rm -rf "$TMP/sigcheck"; _ARM_SRC=martin-riedl; return 0
        fi
        rm -rf "$TMP/sigcheck"; rm -f "$2"; _sigfail=1
        _tried="${_tried:+$_tried; }martin-riedl: not signed by Team $FFMPEG_ARM_TEAM"
      else
        _tried="${_tried:+$_tried; }martin-riedl: HTTP ${_http:-no answer}"
      fi
      [ "$_try" = 1 ] || break
      if [ "$_sigfail" = 1 ]; then say "the download from ffmpeg.martin-riedl.de came back damaged; trying again in ${INTEL_FETCH_WAIT}s…"
      else say "ffmpeg.martin-riedl.de did not answer; trying again in ${INTEL_FETCH_WAIT}s…"; fi
      [ "$INTEL_FETCH_WAIT" -gt 0 ] 2>/dev/null && command -v sleep >/dev/null 2>&1 && sleep "$INTEL_FETCH_WAIT"
    done
    say "fetching $1 from the second Apple-chip source (osxexperts.net) instead…"
  fi
  for _try in 1 2; do
    _src="osxexperts.net"; url="$(_osxexperts_arm_url "$1")"
    if _fetch "$url" "$2"; then
      _got="$(_sha256 "$2")"
      if [ -n "$_got" ] && [ "$_got" = "$(_osxexperts_arm_sha256 "$1")" ]; then
        [ "$_ARM_SRC" = osxexperts ] || note_fallback intel-mac-install \
          "$1 could not come from ffmpeg.martin-riedl.de ($_tried); installed the pinned osxexperts.net $OSXEXPERTS_ARM_FFMPEG_VERSION Apple-chip build instead"
        _ARM_SRC=osxexperts; return 0
      fi
      rm -f "$2"; _pinfail=1; _tried="${_tried:+$_tried; }osxexperts: not the pinned copy (got ${_got:-none})"
      break                                   # a wrong file will not turn right by asking again
    fi
    _tried="${_tried:+$_tried; }osxexperts: HTTP ${_http:-no answer}"
    [ "$_try" = 1 ] && [ "$INTEL_FETCH_WAIT" -gt 0 ] 2>/dev/null && command -v sleep >/dev/null 2>&1 && sleep "$INTEL_FETCH_WAIT"
  done
  note_fallback intel-mac-install "$1 could not be downloaded from either Apple-chip source ($_tried)"
  return 1
}

# _sha256 <file> -> its sha256 in lowercase hex, or nothing. /usr/bin/openssl (LibreSSL) ships with macOS
# itself, so this needs no developer tools; shasum (a perl script) is only the fallback.
_sha256() {
  _h="$(openssl dgst -sha256 "$1" 2>/dev/null | sed -n 's/.*= *\([0-9a-fA-F]\{64\}\)$/\1/p')"
  [ -n "$_h" ] || _h="$(shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1)"
  printf '%s' "$_h" | tr 'A-F' 'a-f'
}

# _signed_by <file> <TeamID> -> true only for an intact signature that chains to Apple and was issued to
# that team. Both halves matter: --verify alone also passes a self-signed or ad-hoc signature.
_signed_by() {
  codesign --verify --strict \
    --test-requirement="=anchor apple generic and certificate leaf[subject.OU] = \"$2\"" "$1" >/dev/null 2>&1 \
    || return 1
  [ "$(codesign -dv "$1" 2>&1 | sed -n 's/^TeamIdentifier=//p')" = "$2" ]
}

install_ffmpeg() {
  for tool in ffmpeg ffprobe; do
    _t="$(_now)"
    if [ "$CLASS" = arm64 ]; then
      _want=arm64
      say "fetching $tool (Apple chip build)…"
      # Apple chip: martin-riedl's signed build, or osxexperts' pinned one when martin-riedl fails (_arm_zip).
      if ! _arm_zip "$tool" "$TMP/$tool.zip"; then
        rm -f "$TMP/$tool.zip" "$TMP/$tool"
        if [ "$_pinfail" = 1 ]; then
          _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: checksum mismatch ($_tried)"
          bad "The $tool download did not match the exact copy this engine was tested with, so it was NOT installed."
          say "Nothing on your Mac was changed. This usually means the download was cut short or the file on the"
          say "server changed. Try again in a few minutes. If it keeps happening, send a problem report."
        elif [ "$_sigfail" = 1 ]; then
          _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: not signed by Team $FFMPEG_ARM_TEAM ($_tried)"
          bad "The $tool download is not signed by its publisher (Martin Riedl, Apple Team ID $FFMPEG_ARM_TEAM), so it was NOT installed."
          say "Nothing on your Mac was changed. A real copy always carries that signature, so this one was damaged"
          say "on the way or did not come from the publisher. Try again in a few minutes. If it keeps happening,"
          say "send a problem report."
        else
          _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: download failed ($_tried)"
          bad "download failed: neither Apple-chip source would hand over $tool right now ($_tried)"
          say "Nothing on your Mac was changed. Both download sites are busy or out of reach. Try again in a few"
          say "minutes. If it keeps happening, send a problem report."
        fi
        return 1
      fi
    else
      _want=x86_64
      say "fetching $tool (Intel build)…"
      # Intel: the zip must be byte-for-byte a pinned one, checked BEFORE it is even unzipped (_intel_zip).
      if ! _intel_zip "$tool" "$TMP/$tool.zip"; then
        rm -f "$TMP/$tool.zip" "$TMP/$tool"
        if [ "$_pinfail" = 1 ]; then
          _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: checksum mismatch ($_tried)"
          bad "The $tool download did not match the exact copy this engine was tested with, so it was NOT installed."
          say "Nothing on your Mac was changed. This usually means the download was cut short or the file on the"
          say "server changed. Try again in a few minutes. If it keeps happening, send a problem report."
        else
          _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: download failed ($_tried)"
          bad "download failed: neither Intel source would hand over $tool right now ($_tried)"
          say "Nothing on your Mac was changed. Both download sites are busy or out of reach. Try again in a few"
          say "minutes. If it keeps happening, send a problem report."
        fi
        return 1
      fi
    fi

    if ! unzip -qo "$TMP/$tool.zip" -d "$TMP"; then _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: could not unzip $tool"; bad "could not unzip $tool"; return 1; fi
    [ -f "$TMP/$tool" ] || { _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: not in zip"; bad "$tool not found inside the zip"; return 1; }

    # Apple chip: martin-riedl's binary must be signed by its publisher, verified before it is ever run (again,
    # on the very file that lands). osxexperts' copy has no publisher signature; its zip was sha256-pinned instead.
    if [ "$CLASS" = arm64 ] && [ "$_ARM_SRC" = martin-riedl ] && ! _signed_by "$TMP/$tool" "$FFMPEG_ARM_TEAM"; then
      rm -f "$TMP/$tool.zip" "$TMP/$tool"
      _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: not signed by Team $FFMPEG_ARM_TEAM"
      bad "The $tool download is not signed by its publisher (Martin Riedl, Apple Team ID $FFMPEG_ARM_TEAM), so it was NOT installed."
      say "Nothing on your Mac was changed. A real copy always carries that signature, so this one was damaged"
      say "on the way or did not come from the publisher. Try again in a few minutes. If it keeps happening,"
      say "send a problem report."
      return 1
    fi

    # Verify it is built for THIS chip before putting it on her PATH. A wrong-arch binary here would
    # fail later with "bad CPU type" (or run crawling under Rosetta), mid-edit, which reads as a broken engine.
    if ! file "$TMP/$tool" | grep -q "$_want"; then
      _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: wrong architecture"
      bad "$tool downloaded but is not an $_want binary: $(file -b "$TMP/$tool")"; return 1
    fi
    chmod +x "$TMP/$tool"
    # macOS quarantines anything downloaded and refuses to run it until it is cleared. Without this
    # the very first ffmpeg call dies with a Gatekeeper dialog instead of transcoding.
    xattr -d com.apple.quarantine "$TMP/$tool" 2>/dev/null || true
    mv -f "$TMP/$tool" "$BIN/$tool"
    _v="$("$BIN/$tool" -version 2>/dev/null | head -1 | cut -c1-40)"
    # It has to RUN here, not just download: a binary built for a newer macOS than this one dies on its
    # first call. Caught now, it is a clear message; caught at the first reel, it is a broken engine.
    if [ -z "$_v" ]; then
      _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: installed but does not run on macOS $(sw_vers -productVersion 2>/dev/null)"
      bad "$tool installed but will not run on this Mac"; return 1
    fi
    _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 0 "$_v" "$BIN/$tool"
    good "$tool → $BIN/$tool  ($_v)"
  done
}

# ── git (a quiet stand-in, only when git is Apple's placeholder) ────────────
# Nothing in the engine runs git, but the graphics renderer does: hyperframes checks whether its agent
# skills are current with `git ls-remote https://github.com/heygen-com/hyperframes.git` on any command,
# up to every run (FOUND 2026-10-02 running `browser ensure` with the tools hidden). On a Mac without
# Apple's developer tools /usr/bin/git is a placeholder, so that background check would open the "install
# the developer tools?" dialog during setup and again mid-render. There is no switch for it
# (HYPERFRAMES_NO_UPDATE_CHECK does not cover the skills check), but it fails soft: when git errors it
# fetches the same manifest over HTTPS. So ~/.local/bin/git answers "not installed" quietly instead, and
# the moment real developer tools exist it hands every call straight to Apple's git. A real git already
# sitting in ~/.local/bin is never touched.
GIT_GUARD_MARK="reels-editing-engine git stand-in"
install_git_guard() {
  _t="$(_now)"
  if ! mac_clt_stub /usr/bin/git; then
    _route_step git-guard none "$(( $(_now) - _t ))" 0 "" "not needed: Apple's developer tools are installed"
    return 0
  fi
  if [ -e "$BIN/git" ] && ! grep -q "$GIT_GUARD_MARK" "$BIN/git" 2>/dev/null; then
    _route_step git-guard none "$(( $(_now) - _t ))" 0 "" "left alone: a real git is already in $BIN"
    return 0
  fi
  cat > "$BIN/git" <<'GITGUARD'
#!/bin/sh
# reels-editing-engine git stand-in (placed by scripts/intel-mac-install.sh). This Mac has no Apple developer
# tools, so /usr/bin/git is only a placeholder that opens Apple's "install the developer tools?" dialog. Tools
# that call git in the background get a quiet "not installed" here instead. Once real developer tools exist,
# every call goes straight to Apple's git. Safe to delete.
_dev="$(xcode-select -p 2>/dev/null)"
if [ -n "$_dev" ] && [ -x "$_dev/usr/bin/git" ]; then exec /usr/bin/git "$@"; fi
echo "git is not installed on this Mac (Apple's developer tools are not here). The Reels Editing Engine does not need it." >&2
exit 1
GITGUARD
  chmod +x "$BIN/git"
  _route_step git-guard engine "$(( $(_now) - _t ))" 0 "" "$BIN/git (quiet stand-in)"
  good "git stand-in → $BIN/git  (keeps Apple's developer-tools dialog closed)"
}

# ── node ────────────────────────────────────────────────────────────────────
# nodejs.org's macOS .pkg is universal (arm64 + x64), so one download serves both chips.
# This downloads it and opens it; Apple's installer UI does the rest and asks for her password there.
# The LINE is picked for this macOS (mac_node_line): the newest LTS, or Node 22 below macOS 13.5.
install_node() {
  _t="$(_now)"
  _line="$(mac_node_line)"
  if [ "$_line" = lts ]; then
    say "finding the current Node LTS…"
    ver="$(curl -fsSL -m 60 https://nodejs.org/dist/index.json 2>/dev/null | _node_lts_pkg_version)"
  else
    say "finding Node $_line (the newest Node that runs on macOS $(sw_vers -productVersion 2>/dev/null))…"
    ver="$(curl -fsSL -m 60 https://nodejs.org/dist/index.json 2>/dev/null | _node_line_pkg_version "$_line")"
  fi
  url=""; [ -n "$ver" ] && url="https://nodejs.org/dist/$ver/node-$ver.pkg"
  if [ -z "${url:-}" ]; then
    _route_step node nodejs.org "$(( $(_now) - _t ))" 1 "" "FAILED: no LTS with a macOS installer"
    bad "could not find a Node LTS with a macOS installer"; return 1
  fi
  # ${ver}, braced: bash 3.2 in a UTF-8 terminal (macOS Terminal's default) reads the first byte of "…"
  # as part of the NAME, and under `set -u` "$ver…" died here with "ver?: unbound variable", one step from
  # the end of every Terminal-run install. (Found 2026-10-02 with LANG=en_US.UTF-8.)
  say "downloading Node ${ver}…"
  if ! curl -fsSL -m 900 -o "$TMP/node.pkg" "$url"; then
    _route_step node nodejs.org "$(( $(_now) - _t ))" 1 "" "FAILED: download"
    bad "download failed: $url"; return 1
  fi
  # Keep it somewhere she can find it again if she closes the installer.
  mkdir -p "$HOME/Downloads"
  mv -f "$TMP/node.pkg" "$HOME/Downloads/node-$ver.pkg"
  _route_step node nodejs.org "$(( $(_now) - _t ))" 0 "$ver" "~/Downloads/node-$ver.pkg (installer opened, not yet run)"
  good "downloaded → ~/Downloads/node-$ver.pkg"
  say "${B}Opening it now.${N} Click through the installer and enter your Mac password when it asks."
  say "That password box is a normal Mac window — this is the only password in the whole setup."
  open "$HOME/Downloads/node-$ver.pkg" 2>/dev/null || say "Open it yourself from your Downloads folder."
}

# ── uv ──────────────────────────────────────────────────────────────────────
# uv's own installer ships x86_64 and aarch64 macOS builds and installs to ~/.local/bin without sudo.
# uv then provides Python too (`uv python install 3.11`), which is what replaces `brew install python`.
install_uv() {
  _t="$(_now)"
  say "installing uv (the transcriber helper)…"
  if curl -LsSf -m 600 https://astral.sh/uv/install.sh | sh; then
    _route_step uv astral.sh "$(( $(_now) - _t ))" 0 "$("$BIN/uv" --version 2>/dev/null)" "$BIN/uv"
    good "uv installed → $BIN/uv"
    say "Reopen the terminal before using it, or run: export PATH=\"\$HOME/.local/bin:\$PATH\""
  else
    _route_step uv astral.sh "$(( $(_now) - _t ))" 1 "" "FAILED: installer script"
    bad "uv install failed"; return 1
  fi
}

# ── python 3.11 + Pillow ────────────────────────────────────────────────────
#
# `brew install python` has no Intel equivalent, and it does not need one: uv already manages
# interpreters, and python-build-standalone publishes an x86_64-apple-darwin CPython 3.11. That is
# the same interpreter the transcriber venv is built against, so the buyer ends up on one Python
# instead of two. Pillow then comes from its own Intel wheel — check-setup.sh tests `import PIL`,
# not a command, so it has to land in the Python that actually runs.
install_python() {
  _t="$(_now)"
  UV="$(command -v uv || echo "$BIN/uv")"
  if [ ! -x "$UV" ]; then
    _route_step python3 uv "$(( $(_now) - _t ))" 1 "" "FAILED: uv missing, install uv first"
    bad "uv is not installed yet — run this script with 'uv' first."; return 1
  fi
  say "installing Python 3.11 (managed by uv, no Homebrew)…"
  # --default also writes plain `python3` / `python` shims next to uv, which is what check-setup.sh
  # and every script in the engine actually look for. Without it uv installs `python3.11` only, and
  # `python3` stays missing on a Mac that has no Homebrew Python — setup would report success and
  # then fail on the first caption.
  # Without Apple's developer tools uv's post-download tidy-up would run Apple's install_name_tool
  # placeholder and open the "install the developer tools?" dialog (mac_clt_shield, _mac-arch.sh).
  _cs="$(mac_clt_shield "$TMP/clt-shield")"
  if ! PATH="${_cs:+$_cs:}$PATH" "$UV" python install 3.11 --default >&2; then
    _route_step python3 uv "$(( $(_now) - _t ))" 1 "" "FAILED: uv python install 3.11 --default"
    bad "could not install Python 3.11"; return 1
  fi
  _py="$("$UV" python find 3.11 2>/dev/null)"
  if [ -z "$_py" ] || [ ! -x "$_py" ]; then
    _route_step python3 uv "$(( $(_now) - _t ))" 1 "" "FAILED: installed but could not be located"
    bad "Python 3.11 installed but could not be found afterwards"; return 1
  fi
  _route_step python3 "uv-managed" "$(( $(_now) - _t ))" 0 "$("$_py" -V 2>&1)" "uv python 3.11 (+ python3 shim)"
  good "Python 3.11 ready ($("$_py" -V 2>&1))"

  _t="$(_now)"
  say "installing Pillow (the caption renderer)…"
  # NOT `uv pip install --python <interpreter>`: uv refuses to install into a bare managed
  # interpreter ("Consider creating a virtual environment"), and the engine needs Pillow in the
  # interpreter itself, because check-setup.sh tests `import PIL` through whichever python3 runs.
  # scripts/pip-install.py already exists for exactly this — it installs into the interpreter that
  # runs it and handles uv's externally-managed refusal. (Caught on a real run; the obvious uv
  # command looks right and fails.)
  if "$_py" "$_d/scripts/pip-install.py" pillow >&2; then
    _route_step pillow pypi "$(( $(_now) - _t ))" 0 "$("$_py" -c 'import PIL;print(PIL.__version__)' 2>/dev/null)" "uv python 3.11"
    good "Pillow ready"
  else
    _route_step pillow pypi "$(( $(_now) - _t ))" 1 "" "FAILED: pip-install.py pillow"
    bad "Pillow did not install"; return 1
  fi
}

rc=0
case "${1:-all}" in
  ffmpeg|ffprobe)   install_ffmpeg || rc=1 ;;
  node)             install_node   || rc=1 ;;
  uv)               install_uv     || rc=1 ;;
  python|python3)   install_python || rc=1 ;;
  pillow)           install_python || rc=1 ;;
  git)              install_git_guard || rc=1 ;;
  all)              install_ffmpeg || rc=1
                    install_git_guard || rc=1
                    install_uv     || rc=1
                    install_python || rc=1
                    install_node   || rc=1 ;;   # last: it hands the screen to Apple's installer UI
  *) bad "unknown tool: $1 (want: ffmpeg | node | uv | python | git | all)"; exit 2 ;;
esac

printf "\n"
if [ "$rc" -eq 0 ]; then
  say "${G}${B}Done.${N} Reopen the terminal, then run ./check-setup.sh to confirm."
else
  say "${Y}Something above did not finish.${N} Re-run this — it is safe to run twice — and if it still"
  say "fails, the full route is written down in product/INTEL-MAC-ROUTE.md."
fi
exit "$rc"
