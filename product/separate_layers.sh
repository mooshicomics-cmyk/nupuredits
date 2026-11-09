#!/bin/bash
# separate_layers.sh — every KIND of element on its OWN CapCut track.
#
# WHY THIS EXISTS. "Can I have the captions on their own layer", "split the hook out", "let me move the
# overlay without dragging the captions with it" is a normal request, not an upgrade she had to choose in
# advance. Before this, the honest answer was a half-answer: LAYER split the hook from everything else and
# nothing finer, so a creator who wanted real control got told to start over on a different finish. That is
# the thing CLAUDE.md forbids ("NO ROUTE IS A DEAD END"). This renders each layer she picked to its own
# transparent .mov and hands them to CapCut as separate, named, independently movable tracks.
#
#   separate_layers.sh --list <JOB> <PACK>                 # what CAN be separated in this reel (no render)
#   separate_layers.sh <JOB> <PACK> <layers>               # render only the ones she ticked
#
# <layers> is a comma list: captions,hook,vibe,label,takeover,breakaway,elements
#
# ALWAYS --list FIRST and let her tick. Do not assume a set. The available layers differ per reel: one
# reel offers captions + hook, another offers five. Offering a fixed menu of six means she ticks one that
# is not in her reel and gets nothing back.
#
# COST: one render per ticked layer, plus ONE more for everything she left unticked ("rest", below). Six ticked
# is six renders, or seven when the reel has more. That is why she picks instead of getting all of them by
# default. The captions layer captures only the stretches it is on screen (product/render_spans.py, done inside
# reel_render.py), still as one full-length file; every other layer renders whole.
#
# NOTHING IS LOST. Whatever the reel has that she did not tick still reaches CapCut, together on one extra
# track called "rest". Handing over only the ticked layers used to drop the rest of the reel on the floor
# (it only survived when an old full render happened to be lying around, and then everything showed twice).
#
# Every render goes through product/reel_render.py, the engine's gated renderer: it checks the composition
# first, renders an isolated copy (a failed render can no longer take the composition with it), and a
# failure is said out loud with its reason instead of ending the script in silence.
set -e

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

ROOT=$(cd "$(dirname "$0")/.." && pwd)

if [ "$1" = "--list" ] || [ "$1" = "-l" ]; then
  shift
  [ -z "$1" ] && { echo "usage: separate_layers.sh --list <JOB> <PACK>"; exit 2; }
  # NOT `exec`. On Windows the python3 shim sourced above is a shell FUNCTION, and bash's `exec`
  # bypasses functions to search PATH — where Windows keeps the Microsoft Store decoy. Using exec
  # here sent the buyer the "install Python from the Store" message instead of her layer list.
  python3 "$ROOT/product/layer_probe.py" "$1" "${2:-}" "${3:-}"   # no pack named: layer_probe uses her saved one
  exit $?
fi

JOB=$1; PACK=${2:-}; LAYERS=$3
[ -z "$JOB" ] && { echo "usage: separate_layers.sh <JOB> <PACK> <layers>   (or --list to see the options)"; exit 2; }
# The pack she names, else her saved default, never a guess: every build below and the output folder need the
# real name, and a guessed pack renders her reel in a look that is not hers.
if [ -z "$PACK" ]; then
  PACK="$(python3 "$ROOT/product/user_style.py" "$ROOT/product/creative-vault/user-style.json" 2>/dev/null)"
  if [ -z "$PACK" ]; then
    echo "  ⛔ which style pack is this reel in? Name it (./product/separate_layers.sh $JOB <PACK> <layers>), or save a default pack first."
    exit 2
  fi
fi
if [ -z "$LAYERS" ]; then
  echo "  ⛔ which layers? Run this first and let her tick the ones she wants:"
  echo "       ./product/separate_layers.sh --list $JOB $PACK"
  exit 2
fi

OD="$ROOT/projects/$JOB/hf-reel-type-$(echo "$PACK" | tr 'A-Z' 'a-z')"
WORK="$ROOT/projects/$JOB/layers"; mkdir -p "$WORK"
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) STARTER=start-editor.bat ;; *) STARTER=start-editor.command ;; esac

# The hand-over at the end needs the editing engine up and CapCut closed. Both are checked BEFORE the first
# render, because each render takes minutes and finding out afterwards threw all of them away.
if ! python3 - <<'PY'
import sys, urllib.error, urllib.request
try:
    urllib.request.urlopen("http://localhost:9001/engine_home", timeout=5)
except urllib.error.HTTPError:
    pass                      # it answered, so it is running (an older copy has no such page and says 404)
except Exception:
    sys.exit(1)
PY
then
  echo "  ⛔ the editing engine is not running, and the layers reach CapCut through it. Start it once"
  echo "     (product/engine/VectCutAPI/$STARTER, SETUP.md §1b), then run this again. Nothing was rendered."
  exit 1
fi
if ! python3 -c "import sys; sys.path.insert(0, sys.argv[1]); import draft_safety; \
draft_safety.require_capcut_quit('hand these layers over to CapCut')" "$ROOT/product"; then
  echo "     Nothing was rendered."
  exit 1
fi

build_log () { echo "$WORK/$(echo "$1" | tr ',' '+').build.log"; }   # $1 = LAYER value
build_layer () {   # $1 = LAYER value. Returns the builder's own exit code (3 = this reel has none of it).
  # Its words go to a log, not /dev/null: when a build fails, build_failed below reads them back so she is
  # told the real reason (a crash in the engine is said as one) instead of a guess.
  JOB="$JOB" STYLE_PACK="$PACK" HOOK_SPLIT="${HOOK_SPLIT:-0}" LAYER="$1" \
    python3 "$ROOT/product/build-reel-type.py" >"$(build_log "$1")" 2>&1
}
build_failed () {  # $1 = LAYER value, $2 = its exit code, $3 = what to call it. Says why, in plain words.
  python3 "$ROOT/product/layer_probe.py" --explain "$(build_log "$1")" "$2" "$3" \
    || tail -n 8 "$(build_log "$1")" | sed 's/^/       /'
  echo "     All of it: $(build_log "$1")"
}
restore_full () {  # leave the project holding the normal full overlay, not the last single-layer HTML
  build_layer all || echo "  ⚠ could not rebuild the full overlay afterwards. Before anything else uses it, run:" \
    "JOB=$JOB STYLE_PACK=$PACK LAYER=all python3 product/build-reel-type.py"
}
owns_screen_only () {  # $1 = comma list of groups. True when every one is a full-screen moment by design.
  local g
  for g in $(echo "$1" | tr ',' ' '); do
    case "$g" in takeover|breakaway) ;; *) return 1 ;; esac
  done
  [ -n "$1" ]
}
render_layer () {  # $1 = layer name, $2 = out.mov, $3 = the groups it holds (default $1). The gated render;
  # its own words are kept in a log. A layer build removes the other layers' elements AND their animations
  # (build-reel-type.py prunes them together), so a layer render goes through every check a full overlay
  # does, the dead-target one included.
  local log="$WORK/$1.render.log" rc
  local extra=()
  # A layer holding only full-screen takeovers and breakaway cards covers her BY DESIGN, so the check that
  # refuses a layer sitting on her face can only refuse it. Skip that one check for exactly those layers.
  # Every other check still runs, and a layer with anything else in it keeps the subject check.
  if owns_screen_only "${3:-$1}"; then
    extra+=(--no-subject)
    echo "  · $1 — full-screen by design, so it is not checked against your face position."
  fi
  # Anything extra for the renderer, e.g. REEL_RENDER_EXTRA="--low-memory" on a machine short of memory.
  # Unset (the normal case) adds nothing.
  if [ -n "${REEL_RENDER_EXTRA:-}" ]; then
    local more=()
    read -ra more <<< "$REEL_RENDER_EXTRA"
    extra+=("${more[@]}")
  fi
  set +e
  python3 "$ROOT/product/reel_render.py" render "$OD" -o "$2" ${extra[@]+"${extra[@]}"} >"$log" 2>&1
  rc=$?
  set -e
  if [ $rc -ne 0 ]; then
    echo "  ⛔ $1 — the render stopped (exit $rc). The last of what it said:"
    tail -n 15 "$log" | sed 's/^/       /'
    echo "     All of it: $log"
  fi
  return $rc
}

IFS=',' read -ra WANT <<< "$LAYERS"
TICKED=()
for g in "${WANT[@]}"; do
  g="$(echo "$g" | tr -d '[:space:]')"; [ -n "$g" ] && TICKED+=("$g")
done

# What the reel really has, read off the full overlay (built fresh, so a run that stopped part-way before cannot
# leave a single-layer page behind to answer for it). Everything not ticked goes on the "rest" track, and that
# track sits on top when the reel draws its topmost element above every ticked layer (the usual case: the
# captions and hook are the reel's lowest layers), at the bottom otherwise.
set +e
build_layer all
rc=$?
set -e
if [ $rc -ne 0 ]; then
  build_failed all "$rc" "full"
  exit $rc
fi
trap restore_full EXIT
if ! PLAN=$(python3 - "$ROOT" "$JOB" "$PACK" "$OD/index.html" "${TICKED[@]}" <<'PY'
import os, re, sys
root, job, pack, index, ticked = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:]
sys.path.insert(0, os.path.join(root, "product"))
import layer_probe
have = [row["group"] for row in layer_probe.probe(job, pack)]
rest = [g for g in have if g not in ticked]
order = []
for track in re.findall(r'<div class="clip"[^>]*data-track-index="(\d+)"', open(index, encoding="utf-8").read()):
    group = layer_probe.group_of(int(track))
    if group and group not in order:
        order.append(group)
rank = {group: i for i, group in enumerate(order)}
top_rest = max((rank.get(g, -1) for g in rest), default=-1)
top_ticked = max((rank.get(g, -1) for g in ticked if g in rank), default=-1)
print((",".join(rest) or "-") + " " + ("top" if top_rest > top_ticked else "bottom"))
PY
); then
  echo "  ⛔ could not read which layers this reel has (see above). Nothing was rendered."
  exit 1
fi
REST="${PLAN% *}"; REST_AT="${PLAN##* }"
[ "$REST" = "-" ] && REST=""

LAYER_ARGS=(); MADE=()
for g in "${TICKED[@]}"; do
  set +e
  build_layer "$g"
  rc=$?
  set -e
  if [ $rc -eq 3 ]; then
    echo "  · $g — this reel has none, skipping. (--list shows what it does have.)"; continue
  fi
  if [ $rc -ne 0 ]; then
    build_failed "$g" "$rc" "$g"
    exit $rc
  fi
  render_layer "$g" "$WORK/$g.mov" || exit $?
  LAYER_ARGS+=(--layer "$g=$WORK/$g.mov"); MADE+=("$g")
  echo "  ✓ $g -> $WORK/$g.mov"
done

[ ${#MADE[@]} -eq 0 ] && { echo "  ⛔ nothing rendered: none of [$LAYERS] are in this reel. Run --list."; exit 1; }

if [ -n "$REST" ]; then
  set +e
  build_layer "$REST"
  rc=$?
  set -e
  if [ $rc -ne 0 ]; then
    build_failed "$REST" "$rc" "rest ($REST)"
    exit $rc
  fi
  render_layer rest "$WORK/rest.mov" "$REST" || exit $?
  if [ "$REST_AT" = "top" ]; then
    LAYER_ARGS+=(--layer "rest=$WORK/rest.mov")
  else
    LAYER_ARGS=(--layer "rest=$WORK/rest.mov" "${LAYER_ARGS[@]}")
  fi
  echo "  ✓ rest ($REST) -> $WORK/rest.mov"
fi

# Rebuild the normal full overlay so the project is not left holding the last single-layer HTML.
trap - EXIT
restore_full

if [ -n "$REST" ]; then
  echo "  → CapCut: ${#MADE[@]} layer(s), each on its own track (${MADE[*]}), and everything else together on one more ($REST)"
else
  echo "  → CapCut: ${#MADE[@]} layer(s), each on its own track (${MADE[*]})"
fi
uv run "$ROOT/product/capcut_handoff.py" "$JOB" --pack "$PACK" --punch "${LAYER_ARGS[@]}"
