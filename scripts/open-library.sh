#!/usr/bin/env bash
# open-library.sh [tab] — open the Effects Library in her own browser, with every sound playing.
#   bash scripts/open-library.sh            the Effects tab
#   bash scripts/open-library.sh studio     straight to a tab (studio, commands, sounds, concepts)
#
# Mac: served from this computer at http://127.0.0.1 (scripts/library-server.py), never as a file. Safari
# refuses to let a file:// page play the sounds beside it, so on a Safari Mac every play button failed while
# the page told her to open it in her browser, which she already had. Served over http it plays in Safari,
# Chrome and the rest alike, in whichever browser she already uses. If the server cannot start, the page
# still opens as a file (Chrome plays it that way; Safari shows the animations). Served, her hearts in the library save
# to favorites/effects.json (scripts/library-server.py); as a file they keep in that browser only.
# Windows: served the same way when a real Python is there (after setup it is), so hearts save to her favorites
# folder like on a Mac; with no Python it opens as a file in her default browser, which still plays the sounds.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
TAB="${1:-}"; TAB="${TAB#\#}"; FRAG="${TAB:+#$TAB}"
PAGE="product/effects-library.html"

WIN=""
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; esac
show() { if [ -n "$WIN" ]; then cmd //c start "" "$1"; else open "$1"; fi; }
file_url() { if [ -n "$WIN" ]; then echo "file:///$(cygpath -m "$PWD/$PAGE")$FRAG"; else echo "file://$PWD/$PAGE$FRAG"; fi; }

STATE="_local/library-server.json"
port() { sed -n 's/.*"port": *\([0-9][0-9]*\).*/\1/p' "$STATE" 2>/dev/null; }
alive() { [ -n "$1" ] && curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:$1/$PAGE" 2>/dev/null; }

P="$(port)"
if ! alive "$P"; then
  PY=""                                       # a real Python: Windows' python3 can be a Store placeholder that runs nothing
  for c in python3 python; do
    c="$(command -v "$c" 2>/dev/null)"; [ -n "$c" ] && "$c" -c '' >/dev/null 2>&1 && { PY="$c"; break; }
  done
  if [ -n "$PY" ]; then
    rm -f "$STATE"
    nohup "$PY" scripts/library-server.py >/dev/null 2>&1 &
    _tries=0                                  # up to ~5 s for the server to say which port it took
    while [ "$_tries" -lt 20 ]; do
      P="$(port)"; alive "$P" && break; sleep 0.25; _tries=$((_tries + 1))
    done
  fi
fi
if alive "$P"; then
  show "http://127.0.0.1:$P/$PAGE$FRAG"
else
  show "$(file_url)"                          # still opens; hearts then keep in this browser only
fi
