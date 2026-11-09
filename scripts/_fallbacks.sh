# _fallbacks.sh — the shell half of product/fallbacks.py. Source it; it defines three functions and runs nothing.
#
#   note_fallback <step> <what failed; what it did instead>   one line in _local/fallbacks.log
#   remember_pivot <key> [value] [why]                         this computer works by <value> for <key>
#   remembered_pivot <key>                                     prints the value; non-zero when none
#
# Pure shell for the log (no Python needed, so it works even when Python is the thing that broke). The pivot
# record is JSON, so it goes through product/fallbacks.py with whichever Python the caller has.
# Needs REELS_ENGINE_ROOT or ENGINE_ROOT (the engine folder); without one it does nothing and never fails.

_fb_root() { printf '%s' "${REELS_ENGINE_ROOT:-${ENGINE_ROOT:-}}"; }
_fb_local() {
  if [ -n "${REELS_ENGINE_LOCAL:-}" ]; then printf '%s' "$REELS_ENGINE_LOCAL"
  elif [ -n "$(_fb_root)" ]; then printf '%s/_local' "$(_fb_root)"; fi
}
_fb_py() {
  local p
  for p in "${PYTHON:-}" python3 python; do
    [ -n "$p" ] && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1 \
      && { printf '%s' "$p"; return 0; }
  done
  return 1
}

note_fallback() {   # $1 = step, rest = message
  local dir step="$1"; shift
  dir="$(_fb_local)"; [ -n "$dir" ] || return 0
  mkdir -p "$dir" 2>/dev/null || return 0
  printf '%s  %s: %s\n' "$(date -u '+%Y-%m-%d %H:%MZ' 2>/dev/null)" "$step" "$*" >> "$dir/fallbacks.log" 2>/dev/null || true
}

remember_pivot() {   # $1 = key, $2 = value (default 1), $3 = why
  local py root; root="$(_fb_root)"; [ -n "$root" ] || return 0
  py="$(_fb_py)" || return 0
  "$py" "$root/product/fallbacks.py" remember "$1" "${2:-1}" "${3:-}" >/dev/null 2>&1 || true
}

remembered_pivot() {   # $1 = key
  local py root; root="$(_fb_root)"; [ -n "$root" ] || return 1
  py="$(_fb_py)" || return 1
  "$py" "$root/product/fallbacks.py" get "$1" 2>/dev/null
}
