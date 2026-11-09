#!/usr/bin/env bash
# Double-click this to turn on your editing engine.
# Keep the window it opens open while you edit. Close it when you are done.

cd "$(dirname "$0")"

# Pull in the engine's shared shims (PATH repair + the macOS pyexpat/libexpat fix) so the double-click
# launcher starts the server the SAME way every other entry point does. Without this, setup can succeed
# and then the very first server start dies on the identical pyexpat ImportError setup just fixed.
_R="$(cd ../../.. && pwd)"
[ -f "$_R/scripts/_path-shim.sh" ]    && . "$_R/scripts/_path-shim.sh"
[ -f "$_R/scripts/_python3-shim.sh" ] && . "$_R/scripts/_python3-shim.sh"
# note_fallback: one line in _local/fallbacks.log whenever this launcher had to fix something on the way up.
export REELS_ENGINE_ROOT="${REELS_ENGINE_ROOT:-$_R}"
if [ -f "$_R/scripts/_fallbacks.sh" ]; then . "$_R/scripts/_fallbacks.sh"; else note_fallback() { :; }; fi

# Already running? Don't start a second one. But only say "you're good" when the one running is
# THIS copy: a second copy of the engine (an old download still on) can hold the same port, and
# every build would quietly go through it.
if lsof -iTCP:9001 -sTCP:LISTEN >/dev/null 2>&1; then
  HERE="$(pwd -P)"
  THERE="$(curl -s --max-time 3 http://127.0.0.1:9001/engine_home 2>/dev/null || true)"
  case "$THERE" in /*) ;; *) THERE="" ;; esac   # a 404 page from an older engine is not a path
  if [ "$THERE" = "$HERE" ]; then
    echo "Your editing engine is already on (localhost:9001). You are good to go."
    echo "You can close this window."
    exit 0
  fi
  echo "Another editing engine is already running, so this one can't start."
  if [ -n "$THERE" ]; then
    echo "The one that's on is from a different folder:"
    echo "    $THERE"
  else
    echo "It's an older engine, from before your latest update or from another copy of the engine."
  fi
  echo ""
  echo "To fix it: close the engine window that is already open (or restart your computer), then double-click this again."
  exit 1
fi

# A workspace that is missing, or there but will not load the engine's own tools (its Python was upgraded away,
# an install stopped halfway), gets its setup run once, right here, instead of a "not set up" and a stop. Setup
# keeps a working workspace exactly as it is and rebuilds a broken one.
engine_loads() {
  [ -x "venv-capcut/bin/python" ] && ./venv-capcut/bin/python -c 'import flask, requests, json5, imageio, psutil' >/dev/null 2>&1
}
if ! engine_loads; then
  if [ -z "${REE_EDITOR_SETUP_TRIED:-}" ] && [ -f setup-editor-engine.sh ]; then
    export REE_EDITOR_SETUP_TRIED=1   # once per start: a setup that cannot fix it must not run in a loop
    echo "The engine's workspace is not set up yet (or would not load). Setting it up now, one time only..."
    note_fallback capcut-draft "the editing engine's workspace was missing or would not load; start-editor ran its setup once"
    bash ./setup-editor-engine.sh || true
  fi
  if ! engine_loads; then
    echo "The engine's workspace still would not load after setting it up."
    echo "Run /report-a-problem (or tell Claude 'set me up'): the report carries what setup said."
    exit 1
  fi
fi

# config.json is the engine's port. It is not shipped (each machine writes its own), and without it the server
# used to fall back to port 9000 while every build calls 9001, so builds said "not running" to a running engine.
# Written here when missing, with the same contents setup writes; the file itself is the memory.
if [ ! -f config.json ]; then
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
  note_fallback capcut-draft "the editing engine had no config.json; wrote the standard one (port 9001)"
fi

echo "Starting your editing engine..."
echo "Keep this window open while you edit. You'll see 'Running on ... 9001' when it's ready."
echo ""
exec ./venv-capcut/bin/python capcut_server.py
