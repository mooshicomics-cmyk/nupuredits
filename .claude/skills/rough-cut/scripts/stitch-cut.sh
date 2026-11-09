#!/usr/bin/env bash
# stitch-cut.sh — the stitch at the end of every rough cut.
#
# Takes the cut plan waiting in the scratch folder, cleans it (quick restarts out, every boundary dialed to
# where the sound really starts and stops, every boundary on the frame grid) and turns it into the base cut:
# one flat render, the EDL that describes it, and the caption transcript that lines up with it.
#
#   bash .claude/skills/rough-cut/scripts/stitch-cut.sh <job_dir>
#   FLAT_RENDER=0 bash .claude/skills/rough-cut/scripts/stitch-cut.sh <job_dir>    # EDL + transcript only, for a CapCut finish
#
# in:   <temp dir>/reels-editing-engine/<job>/cuts.json    the plan (Claude, transcript-cut.py or your-turn.py
#                                                          wrote it; when it is gone, the job's saved
#                                                          transcript/cuts.json is stitched instead)
# out:  projects/<job>/outputs/<job>.mp4                   the flat render (not with FLAT_RENDER=0)
#       projects/<job>/transcript/cuts.json                the frame-snapped EDL; the one it replaces goes to history/
#       projects/<job>/outputs/<job>.transcript.json       the cut-aligned transcript captions and graphics read
# stdout: its last line is the base cut's path (the saved EDL's with FLAT_RENDER=0); the log goes to stderr.
#
# Knobs, each explained where it is used: TRIM_RESTARTS=0 · SNAP=0 · VOICE_GAIN_DB=<dB> · WARM_MASTER=0 ·
# FLAT_RENDER=0 · VERIFY_CUT=0 (VERIFY_CUT_MODEL=<size>) · STITCH_GROUP=<pieces per encode, 0 = one graph>.

set -euo pipefail

# Every Python step below prints ✓, ⚠ and → in its status lines. A Git Bash window on Windows can hand Python
# a cp1252 console, and printing one of those then stops the step with an error. PYTHONUTF8 makes Python
# write UTF-8 everywhere; a Mac already does.
export PYTHONUTF8=1

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
export REELS_ENGINE_ROOT="$_d"   # same walk-up already found it — reused below so the
                                         # python heredoc (piped via stdin, no real __file__) can
                                         # still import product/video_encoder.py
# A native Windows Python reads env vars verbatim, so hand it a real Windows path (C:\...), not the
# Git Bash spelling (/c/...). Explicit rather than trusting MSYS's env-var path conversion.
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) REELS_ENGINE_ROOT="$(cygpath -w "$_d" 2>/dev/null || echo "$_d")" ;; esac
unset _d

# ── The job ────────────────────────────────────────────────────────────────────────────────────────────
# The one argument is the job folder, made absolute here so every path below holds up whichever directory
# the caller happened to be in.
JOB_DIR="$(cd "${1:?usage: stitch-cut.sh <job_dir>}" && pwd)"
JOB_NAME="${JOB_DIR##*/}"
HERE="$(dirname "$0")"                   # the other rough-cut scripts this one hands work to
# Intake copies footage into raw/; a job made before that keeps its clips at the top of the folder.
if [ -d "$JOB_DIR/raw" ]; then MEDIA_DIR="$JOB_DIR/raw"; else MEDIA_DIR="$JOB_DIR"; fi
WORK="$(scratch_root)/$JOB_NAME"         # scratch: the plan arrives here and the working copies are made here
CUTS="$WORK/cuts.json"                   # the plan to stitch; after the snap pass, the snapped copy of it
OUT="$JOB_DIR/outputs"
MP4="$OUT/${JOB_NAME}.mp4"
mkdir -p "$WORK" "$OUT"
# A clip whose sound starts after its picture (an iPhone clip copied out of Photos: 0.7 s) in a job heard before
# intake lined such clips up: its words and this plan are on the sound's clock while every trim below is on the
# file's, so each cut lands early by the lead, and a re-cut after the update came out just as choppy (a buyer,
# 2026-10-22). product/av_sync.py lines the clip up and moves the stored word and cut times with it, the scratch
# plan included, once; every way a re-cut reaches the stitch (the chat, her visual editor, a restitch, your-turn)
# passes here. Nothing late, nothing said. Best-effort: a clip it cannot line up is said once and cut as it is.
if [ -f "$JOB_DIR/transcript/words.json" ] && [ -f "$HERE/../../../../product/av_sync.py" ]; then
  python3 "$HERE/../../../../product/av_sync.py" "$JOB_DIR" --apply --quiet >&2 || true
fi
# The plan normally waits in the scratch folder (transcript-cut.py, trim-restarts.py and your-turn.py all
# leave it there), but the operating system clears that folder whenever it likes, and a vanished plan used
# to end the run with "missing". The copy under transcript/ is the plan this job last stitched, cut or pulled
# back from CapCut, which is exactly what a re-run means to stitch, and stitching it again is safe: a cut this
# engine saved comes back as it was (measured on real jobs; a second run changes nothing either), and one
# saved by an older version is simply cleaned by today's passes, as on any stitch, with the plan it
# replaces kept in transcript/history/. It is copied INTO the scratch folder first, so every pass below still
# edits only the scratch copy, never the saved one. Only a job with neither copy stops here.
# With both copies here, the NEWER one is the plan. A scratch plan left by an earlier stitch must never undo an edit
# made since to the saved one (by hand, tighten.py): it used to win every time, and the stitch saved it over the edit
# (a buyer report, 2026-10-22). A fresh plan (the cutter, the visual editor, your-turn, Finish's own copy) lands in
# the scratch folder after the saved one, so it still wins as before. Same content either way: nothing to choose.
if [ ! -f "$CUTS" ] && [ -f "$JOB_DIR/transcript/cuts.json" ]; then
  echo "[stitch] no cut plan waiting in the scratch folder, so stitching the one this job saved last: $JOB_DIR/transcript/cuts.json" >&2
  cp "$JOB_DIR/transcript/cuts.json" "$CUTS"
elif [ -f "$CUTS" ] && [ "$JOB_DIR/transcript/cuts.json" -nt "$CUTS" ] && ! cmp -s "$CUTS" "$JOB_DIR/transcript/cuts.json"; then
  echo "[stitch] the job's saved cut plan is newer than the one waiting in the scratch folder, so stitching the saved one: $JOB_DIR/transcript/cuts.json" >&2
  cp "$JOB_DIR/transcript/cuts.json" "$CUTS"
fi
if [ ! -f "$CUTS" ]; then
  echo "can't find the cut list: $CUTS" >&2
  exit 1
fi
# FLAT_RENDER=0 means a timeline finish: the EDL and the transcript are all it needs, so nothing is encoded
# and nothing that listens to the encoded file runs. Settled once here to 0 or 1 and exported, so the render
# program reads the same answer.
FLAT_RENDER_SHOWN="${FLAT_RENDER:-1}"
if [ "$FLAT_RENDER_SHOWN" = "0" ]; then FLAT_RENDER=0; else FLAT_RENDER=1; fi
export FLAT_RENDER

# Every switch this run honors goes into the log on one line before any work starts, set or default, so a
# switch she meant to set and did not (or one left over from an earlier run) shows at the top.
# SNAP switches the boundary snap.
echo "[stitch] toggles: TRIM_RESTARTS=${TRIM_RESTARTS:-1} SNAP=${SNAP:-1} VOICE_GAIN_DB=${VOICE_GAIN_DB:-10} WARM_MASTER=${WARM_MASTER:-1} FLAT_RENDER=$FLAT_RENDER_SHOWN VERIFY_CUT=${VERIFY_CUT:-1}" >&2

# ── Quick restarts ─────────────────────────────────────────────────────────────────────────────────────
# First pass, on by default in every rough cut. When she starts a line, stops and says it again straight
# away, WhisperX often writes only the finished take, so the false start is invisible in the transcript and
# survives the cut. trim-restarts.py hears it instead: it compares how the two stretches sound (MFCCs, on
# this machine, through torchaudio in the speech tools) and drops the first one. It needs the transcript and
# the speech tools, and says so when either is missing. TRIM_RESTARTS=0 turns it off. It goes before the
# boundary snap, so the edges are measured on the cut that will actually play.
TR="$HERE/trim-restarts.py"
WX_VENV="${REELS_ENGINE_WHISPERX_VENV:-$(venv_home whisperx-venv)}"
VENV_PY="$(venv_py "$WX_VENV")"
# Every backup route this stitch takes leaves one line in _local/fallbacks.log (/report-a-problem attaches it),
# and when the cause is this computer rather than the reel, a note in _local/pivots.json, so the next stitch
# goes straight to what works instead of failing first. A copy of the engine without the helper still
# stitches; it only keeps no record.
if [ -f "$HERE/../../../../scripts/_fallbacks.sh" ]; then
  . "$HERE/../../../../scripts/_fallbacks.sh"
else
  note_fallback() { :; }; remember_pivot() { :; }; remembered_pivot() { return 1; }
fi
# A real Intel Mac, not an Apple-chip Mac running under Rosetta. scripts/_mac-arch.sh owns that test, so it is
# asked rather than copied; in a subshell, so nothing it defines leaks into this script.
_tr_intel_mac() {
  [ -f "$HERE/../../../../scripts/_mac-arch.sh" ] || return 1
  ( . "$HERE/../../../../scripts/_mac-arch.sh" && [ "$(mac_arch_class)" = intel ] )
}
# Which build of the speech tools sits here: the ready record word-timings.sh writes when it finishes building
# them, and when it wrote it. A rebuild writes a new one, so a remembered "this pass can't run here" never
# outlives the build it was learned on (product/clean_cut.py works out the same id).
_tr_tools_id() {
  local m
  for m in .speech-tools-ready .deps-ok; do
    if [ -e "$WX_VENV/$m" ]; then
      printf '%s@%s' "$m" "$(python3 -c 'import os, sys; print(int(os.path.getmtime(sys.argv[1])))' "$WX_VENV/$m" 2>/dev/null)"
      return 0
    fi
  done
  printf 'none'
}
# A cut pulled back from her CapCut timeline (your-turn) is her own trim, and it stands as she made it:
# your-turn.py leaves this marker, and while it is there neither the restart pass nor the snap touches the
# cut. The next fresh rough cut clears it (transcript-cut.py). TRIM_RESTARTS=1 or SNAP=1 overrides.
if [ -f "$JOB_DIR/transcript/.your-turn-cut" ]; then
  : "${TRIM_RESTARTS:=0}"
  [ "${TRIM_RESTARTS}" = "0" ] && echo "[stitch] your-turn marker present — trim-restarts auto-disabled (her trim wins; TRIM_RESTARTS=1 forces)" >&2
  # Her edges too: she set them by ear in CapCut, and snap-to-sound would move nearly all of them. SNAP=1 forces.
  : "${SNAP:=0}"
  [ "${SNAP}" = "0" ] && echo "[stitch] your-turn cut — her edges kept exactly as she set them (no boundary snap; SNAP=1 forces)" >&2
  : "${CLOSE_PAUSES:=0}"   # her pauses too: she left them in CapCut on purpose. CLOSE_PAUSES=1 forces.
fi
# Whether to try the pass at all on this computer. It is skipped up front, with one line saying so, when:
#   intel  an Intel Mac, which has the lighter speech tools only, with no torchaudio, so the pass cannot run
#          there. That has to be said out loud: without the note she would never learn her restarts stayed in.
#   tools  this computer's speech tools can't carry it: an earlier stitch tried and they failed (remembered
#          below), word-timings.sh moved this computer to faster-whisper (the mark beside the WhisperX venv),
#          or only the faster-whisper venv was ever built. The first time is logged and remembered; after
#          that it is one plain line per stitch and nothing else.
# The WhisperX-crashed mark inside the venv (word-timings.sh's FW_ONLY_MARK) is not a reason on its own: that
# crash is torch, CTranslate2 and the voice detector loaded together, and this pass loads torch alone. When
# torch is the trouble, the first try fails, is remembered, and later stitches skip straight away.
# To make the engine try again on purpose:  python3 product/fallbacks.py forget trim-restarts.unavailable
_TR_SKIP=""
if [ "${TRIM_RESTARTS:-1}" != "0" ]; then
  _tr_id="$(_tr_tools_id)"
  _tr_nofw_py="$(venv_py "${REELS_ENGINE_NOFW_VENV:-$(venv_home fasterwhisper-venv)}")"
  if [ ! -x "$VENV_PY" ] && [ -x "$_tr_nofw_py" ] && _tr_intel_mac; then
    _TR_SKIP=intel
  elif [ "$(remembered_pivot trim-restarts.unavailable 2>/dev/null || true)" = "$_tr_id" ]; then
    _TR_SKIP=tools
  elif [ -e "$WX_VENV.use-faster-whisper" ] || { [ ! -x "$VENV_PY" ] && [ -x "$_tr_nofw_py" ]; }; then
    _TR_SKIP=tools
    if [ -e "$WX_VENV.use-faster-whisper" ]; then _tr_why="this computer was moved to faster-whisper for transcribing"
    else _tr_why="only the faster-whisper speech tools are installed here"; fi
    note_fallback trim-restarts "the quick-restart pass needs torchaudio and $_tr_why; stitched without it, and later cuts skip it"
    remember_pivot trim-restarts.unavailable "$_tr_id" "$_tr_why"
  fi
fi
# The pass edits this run's scratch copy of the plan ($CUTS), never the job's saved transcript/cuts.json,
# so two stitches of one job running at once cannot overwrite each other's plan.
if [ "$_TR_SKIP" = intel ]; then
  echo "[stitch] note: the quick-restart de-stutter pass does not run on an Intel Mac. It needs a piece" >&2
  echo "[stitch]       of software that has no Intel build. Everything else in the cut is unaffected." >&2
  echo "[stitch]       If you restart a sentence mid-take, listen back and trim that one by hand." >&2
elif [ "$_TR_SKIP" = tools ]; then
  echo "[stitch] note: this computer's speech tools can't run the quick-restart pass, so the cut goes ahead without it. If a line restarts mid-take, listen back and trim that one by hand." >&2
fi
if [ "${TRIM_RESTARTS:-1}" != "0" ] && [ -z "$_TR_SKIP" ] && [ -f "$TR" ] && [ -x "$VENV_PY" ] \
     && [ -f "$JOB_DIR/transcript/words.json" ] && [ -f "$CUTS" ]; then
  _tr_err="$(mktemp)"
  _tr_rc=0
  "$VENV_PY" "$TR" "$JOB_DIR" --cuts "$CUTS" 2>"$_tr_err" || _tr_rc=$?
  # Did it fail because of this computer rather than this reel? trim-restarts.py exits 69 when torch,
  # torchaudio or numpy will not load; 132 to 139 are a native library dying under it (illegal instruction,
  # abort, bus error, segfault); a stop with nothing at all on stderr is the same kind of death; and an import
  # error that slipped past its own check still names itself.
  _tr_env=0
  case "$_tr_rc" in 69|132|134|136|138|139) _tr_env=1 ;; esac
  if [ "$_tr_rc" -ne 0 ] && [ -z "$(tr -d '[:space:]' < "$_tr_err")" ]; then _tr_env=1; fi
  if grep -qE "ModuleNotFoundError|No module named|ImportError|libtorch|DLL load failed|Library not loaded" "$_tr_err"; then
    _tr_env=1
  fi
  if [ "$_tr_rc" -eq 0 ]; then
    echo "[stitch] ✓ quick-restart de-stutter pass ran (on the scratch cut)" >&2
    # Its ⚠ lines name a kept line whose word timing is unreliable, which is the cue to re-listen there
    # before handing the cut over. They used to be thrown away with the rest of its stderr.
    grep -F '⚠' "$_tr_err" | sed 's/^[[:space:]]*/[trim-restarts] /' >&2 || true
  elif [ "$_tr_rc" -eq 130 ] || [ "$_tr_rc" -eq 143 ]; then
    rm -f "$_tr_err"
    exit "$_tr_rc"   # she stopped it (Ctrl-C), and that stays a stop
  elif grep -q "clips, but this pass reads only the first" "$_tr_err"; then
    # Not a crash: the pass reads one-clip jobs only (trim-restarts.py says so and stops). Say what that
    # means for her instead of printing it as a failure.
    _tr_n="multi"
    [[ "$(cat "$_tr_err")" =~ this\ job\ has\ ([0-9]+)\ clips ]] && _tr_n="${BASH_REMATCH[1]}"
    echo "[stitch] note: the quick-restart pass works on one-clip jobs only, so it did not run on this ${_tr_n}-clip job." >&2
    echo "[stitch]       Everything else in the cut is unaffected. If a line restarts mid-take, listen back and trim that one by hand." >&2
  elif [ "$_tr_env" = 1 ]; then
    # The computer, not the reel: the cut goes on without the pass, and later stitches skip it straight away.
    _tr_last="$(grep -v '^[[:space:]]*$' "$_tr_err" | tail -n 1 | cut -c1-160 || true)"
    case "$_tr_rc" in
      132|134|136|138|139) _tr_why="its speech libraries crashed (exit $_tr_rc)${_tr_last:+: $_tr_last}" ;;
      *) _tr_why="${_tr_last:-it stopped with exit $_tr_rc and no message}" ;;
    esac
    echo "[stitch] note: this computer's speech tools can't run the quick-restart pass, so the cut goes ahead without it (later cuts skip it straight away). If a line restarts mid-take, listen back and trim that one by hand." >&2
    note_fallback trim-restarts "the quick-restart pass could not run on this computer ($_tr_why); stitched without it, and later cuts skip it"
    remember_pivot trim-restarts.unavailable "$_tr_id" "$_tr_why"
  else
    # a real crash (bad JSON, missing ffmpeg) is about this reel, not the computer — surface it loudly
    echo "[stitch] ⚠ quick-restart pass CRASHED — double-takes may remain in the cut. Details:" >&2
    sed 's/^/[trim-restarts] /' "$_tr_err" >&2
  fi
  rm -f "$_tr_err"
fi

# ── Boundary snap ──────────────────────────────────────────────────────────────────────────────────────
# Second pass. The plan's in and out points come from WhisperX's word stamps, which sit inside her voice:
# on her footage a start stamp runs a median 39 ms late and an end stamp 75 ms early. snap-to-sound.py finds
# where each boundary word really starts and stops in the raw audio and sets the cut 42 ms before the start
# and 60 ms after the end, never past a neighbouring word. The kept words stay exactly the same.
# SNAP=0 skips it; "keep_edges": true pins one segment. Each clip's sound is decoded once for the whole pass, and the
# pass has its own time budget (SNAP_BUDGET_S, 240 s): past it, the pieces left keep their edges as written, so a
# stuck read can never hold a lean "Send my cut" up to its 15-minute limit.
words_json() {   # the word timings: the durable transcript when the job has one, else the scratch copy
  if [ -f "$JOB_DIR/transcript/words.json" ]; then
    printf '%s\n' "$JOB_DIR/transcript/words.json"
  else
    printf '%s\n' "$WORK/words.json"
  fi
}
_words="$(words_json)"
if [ "${SNAP:-1}" = "0" ] || [ ! -f "$_words" ]; then
  :   # switched off, or nothing to measure against: the plan goes to the render exactly as authored
elif python3 "$HERE/snap-to-sound.py" "$MEDIA_DIR" "$_words" "$CUTS" "$WORK/cuts.edges.json"; then
  CUTS="$WORK/cuts.edges.json"
else
  # The edges as authored are a working cut, only less tight, so the stitch goes on with them. About this reel,
  # not the computer, so nothing is remembered: the next stitch snaps again.
  echo "[stitch] snap-to-sound did not finish, so the cut is stitched on the edges as written (reason above)." >&2
  note_fallback snap-to-sound "the boundary snap did not finish on $JOB_NAME; stitched with the edges as authored"
fi

# ── Dead air ───────────────────────────────────────────────────────────────────────────────────────────
# Third pass. Whatever made the plan (transcript-cut.py, a cut written by hand, a resumed or older cut), no kept
# piece holds a long silence: close-pauses.py listens to each piece's own audio and closes every held quiet over
# 0.7 s to a natural beat (a pause hidden inside a stretched word stamp, or before a line's first word, is
# invisible to the transcript). Pinned pieces (her editor edges, a clip with no talking) and words she brought
# back stay exactly as they are. CLOSE_PAUSES=0 skips it.
if [ "${CLOSE_PAUSES:-1}" != "0" ] && [ -f "$_words" ]; then
  if python3 "$HERE/close-pauses.py" "$MEDIA_DIR" "$_words" "$CUTS" "$WORK/cuts.tight.json"; then
    CUTS="$WORK/cuts.tight.json"
  else
    echo "[stitch] the dead-air pass did not finish, so the cut is stitched without it (reason above)." >&2
    note_fallback close-pauses "the dead-air pass did not finish on $JOB_NAME; stitched without it"
  fi
fi

# ── The render ─────────────────────────────────────────────────────────────────────────────────────────
# One ffmpeg graph, straight from the raw clips to the base cut, so each segment's picture and sound share
# one pair of in and out points and the sound is encoded once, at the very end.
#
# A segment in the plan, as her phone names the clip:
#     {"clip": "IMG_0412.MOV", "start": 13.73, "end": 17.17, "transcript": "the line she says there"}
# Times are seconds in the raw clip. "xfade" sets one joint's length (see JOINTS below); every other key is
# carried into the EDL as it is.
# The render program writes this run's EDL (below). One left in the scratch folder by an EARLIER run must
# never stand in for it: when the program stopped before writing its own, that old file used to be saved over
# the job's cut as though it had just been made. Both names go: the one it has now, and the one an earlier
# version of this script gave it.
rm -f "$WORK/edl.json" "$WORK/cuts.snapped.json"
render_rc=0
_render_retried=0
# Run at most twice: when the render program stops on the SNAPPED plan, it is run once more on the plan as
# written before the snap (the loop's end says when). The program itself sits unindented inside the loop.
while :; do
python3 - "$MEDIA_DIR" "$CUTS" "$MP4" <<'PY' || render_rc=$?
import atexit, functools, json, math, os, re, subprocess, sys
sys.path.insert(0, os.path.join(os.environ["REELS_ENGINE_ROOT"], "product"))
from video_encoder import pick_encoder, COLOR_FLAGS, filter_complex_args   # shared across every ffmpeg render in the engine
from hdr import HDR2SDR, hdr_kind                    # an HDR phone clip is converted, never only re-tagged
from probe import display_dims                       # a clip's upright size (a phone clip is stored sideways)
try:
    from swap import replace as swap_in              # os.replace that waits out Windows holding a fresh file open
except ImportError:
    swap_in = os.replace

media_dir, plan_path, out_path = sys.argv[1:]
# dB, exactly as typed: it goes into the graph verbatim. Set but empty counts as unset, as it already does in
# the toggles line above (an empty value used to print VOICE_GAIN_DB=10 there and put "volume=dB" in the graph).
gain = os.environ.get("VOICE_GAIN_DB") or "10"
warm = os.environ.get("WARM_MASTER", "1") != "0"
edl_only = os.environ.get("FLAT_RENDER", "1") == "0"   # settled to 0 or 1 by the shell above

with open(plan_path) as fh:
    plan = json.load(fh)
segments = plan["segments"]
# A cut pulled back out of the creator's own CapCut timeline (your-turn) can carry what she set there on top of
# the in and out points: a clip's "speed", its zoom and framing ("scale", "x", "y", CapCut's own units), and
# "audio_detached" when she split its sound off onto an audio track. Those split-off and extra sound clips come
# as the plan's "audio_overlays" ({clip, start, end, target_start, volume}, seconds on the cut timeline). Every
# other plan has none of these keys, and for it nothing below changes.
overlays = plan.get("audio_overlays") or []


# SPEED RAMPS. A clip can ease from one speed to another (her page's Speed menu, or clip-fx): "ramp": {"from": 2.6,
# "to": 1.4, "ease": "out"}, with "speed" holding the ramp's AVERAGE, so its played length is (end - start) / speed
# like any sped clip and every other reader of the cut (captions, CapCut, checks) keeps working. A plan written with
# the ramp inside "speed" itself ({"from", "to", "ease"}) is read the same way. The speed runs v(u) = from + (to -
# from) * E(u) over the clip's played time u (0..1), E the ease: in = u², out = 1 - (1 - u)², inOut = smoothstep,
# linear = u. So the footage reached at u is (from*u + (to - from) * area(u)) / average, area = the integral of E.
EASES = ("linear", "in", "out", "inOut", "quart")


def ease_area(ease, u):
    if ease == "linear":
        return u * u / 2
    if ease == "in":
        return u ** 3 / 3
    if ease == "out":
        return u - (1 - (1 - u) ** 3) / 3
    return u ** 3 - u ** 4 / 2                     # inOut (smoothstep)


def ease_expr(ease, u):
    """E(u) as an ffmpeg expression of u (an expression string)."""
    return {"linear": f"({u})", "in": f"(({u})*({u}))", "out": f"(1-(1-({u}))*(1-({u})))",
            "quart": f"(1-pow(1-({u}),4))"}.get(ease, f"(({u})*({u})*(3-2*({u})))")


def area_expr(ease, u):
    return {"linear": f"(({u})*({u})/2)", "in": f"(({u})*({u})*({u})/3)",
            "out": f"(({u})-(1-(1-({u}))*(1-({u}))*(1-({u})))/3)"}.get(ease, f"(({u})*({u})*({u})-({u})*({u})*({u})*({u})/2)")


for seg in segments:
    sp = seg.get("speed")
    ramp = sp if isinstance(sp, dict) else seg.get("ramp")
    if isinstance(ramp, dict):
        try:
            r = {"from": float(ramp["from"]), "to": float(ramp["to"]), "ease": ramp.get("ease") if ramp.get("ease") in EASES else "inOut"}
        except (KeyError, TypeError, ValueError):
            sys.exit(f"a speed ramp needs a from and a to: {ramp}")
        if min(r["from"], r["to"]) <= 0:
            sys.exit(f"a speed ramp can't stop the clip: {ramp}")
        seg["ramp"] = r
        seg["speed"] = round(r["from"] + (r["to"] - r["from"]) * ease_area(r["ease"], 1.0), 6)
if not segments:
    sys.exit("the cut list (cuts.json) is empty, nothing to keep")

# Every file the plan uses becomes an ffmpeg input, the first time a segment asks for it: sources[k] is input k's
# file, and seeks[k] the whole second that input starts reading at (0, the top of the file, unless READING ORDER
# below says otherwise).
sources, seeks = [], []


def clip_path(clip):
    path = os.path.join(media_dir, clip)   # a clip given as a full path stays that path
    if not os.path.exists(path):
        sys.exit(f"clip not found: {path}")
    return path


def source_index(clip):
    """The input reading this clip from the top (her sound clips), made the first time it is asked for."""
    path = clip_path(clip)
    for k, src in enumerate(sources):
        if src == path and not seeks[k]:
            return k
    sources.append(path)
    seeks.append(0)
    return len(sources) - 1


# READING ORDER. ffmpeg decodes an input once, front to back, and hands every frame to each piece cut from it. A cut
# that plays its pieces in filming order streams straight through. A cut that jumps back in a file (a cold open from
# late in the take, a replay) does not: while the join waits for the first piece, every frame of the later pieces
# filmed before it is decoded and held in memory. On a long 4K take that is tens of gigabytes, and the computer ended
# the render (signal 9) hours in (a buyer report, 2026-10-22). So each file's pieces are dealt, in cut order, into
# runs that only move forward through it, and each run is its own input; when a file needs more than one, each
# starts reading (-ss) 2 s before its first piece, on a whole second, so nothing waits in memory and no input decodes
# the whole take to reach its start. A whole second moves every in and out point below by a whole number of ticks of
# any clock, so each still lands on exactly the same frame and sample. A cut in filming order is one run per file:
# its inputs, and its graph, are exactly what they always were.
RUN_SLACK = 0.1    # seconds a piece may start before the run's furthest end and stay in it (joined pieces meet there)
runs = {}          # file -> its runs, each [furthest end so far, first start]
run_of = []        # per segment: (file, its run)
for i, seg in enumerate(segments):
    t0, t1 = float(seg["start"]), float(seg["end"])
    if t1 <= t0:
        sys.exit(f"cut {i} ends before it starts: {seg}")
    path = clip_path(seg["clip"])
    fits = [r for r in runs.setdefault(path, []) if r[0] <= t0 + RUN_SLACK]
    run = max(fits, key=lambda r: r[0]) if fits else None   # the run that left off nearest before this piece
    if run is None:
        run = [t1, t0]
        runs[path].append(run)
    run[0] = max(run[0], t1)
    run_of.append((path, run))
run_input = {}     # id(run) -> its input


def piece_input(i):
    """Segment i's input: its run's, made the first time the run is asked for (so a cut in filming order numbers its
    inputs as it always did)."""
    path, run = run_of[i]
    if id(run) not in run_input:
        sources.append(path)
        seeks.append(max(0, math.floor(run[1]) - 2) if len(runs[path]) > 1 else 0)
        run_input[id(run)] = len(sources) - 1
    return run_input[id(run)]


def input_args():
    """-i for every input, a seeked one with its -ss in front."""
    return [a for src, ss in zip(sources, seeks) for a in ((["-ss", str(ss)] if ss else []) + ["-i", src])]


@functools.lru_cache(maxsize=None)
def picture(path):
    """(rate numerator, rate denominator, width, height) of the file's first video stream, asked once per file."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate,width,height", "-of", "json", path], capture_output=True, text=True)
    stream = json.loads(out.stdout)["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return int(num), int(den), int(stream["width"]), int(stream["height"])


def frame_rate(path):
    return picture(path)[:2]


@functools.lru_cache(maxsize=None)
def colour_in(path):
    """The conversion an HDR clip needs before anything else in its chain ("" for a standard-colour clip). Intake
    converts HDR clips once (product/hdr.py); this covers a clip that reached the stitch without it, so the cut is
    never HDR re-tagged as SDR (bright, flat, grey)."""
    return f"{HDR2SDR}," if hdr_kind(path) else ""


# FRAME GRID. trim keeps whole frames of picture; atrim keeps sound to the sample. Each in and out point
# goes to the nearest frame of its own clip, so a segment's sound and picture last exactly as long as each
# other and the EDL's times are the finished timeline's times.
def on_frame_grid(t, num, den):
    return round(t * num / den) * den / num


# JOINTS. At a joint the outgoing segment's sound runs XF seconds past its picture, into whatever came next
# in the raw, and acrossfade blends it into the incoming segment over exactly that stretch (a quarter-sine
# curve on both sides). The blend uses up the run-on and nothing else, so the sound still ends with the picture.
# XF spans one full cycle of the voice at its low regular pitch (172 Hz, 5.8 ms, rounded up to whole ms), so
# no cycle is cut off part-way at a joint. Longer only spends room the joint does not have: over 295 joints
# of real snapped cuts, the fade reached into the speaker's own sound (the incoming onset, or whatever follows an
# out-point in the raw) at 17% of joints at 6 ms, 21% at 15 ms and 27% at 25 ms.
XF = 0.006     # seconds
EDGE = 0.006   # the only fades to silence, in at the very start of the file and out at the very end: the same cycle


def joint_xfade(j):
    """Crossfade length into segment j (only a segment with one in front of it has a joint). A segment's
    own "xfade" overrides the default for its joint, e.g. 0.030 (as long as a long breathy attack runs, the
    95th percentile measured) to rebuild an attack that a cut-in caught already under way, without moving
    the timeline. Never under 3 ms: at d=0 acrossfade drops the shorter input's samples on sub-second clips
    (a b-roll montage lost 0.8 s of sound and slipped out of sync), while a 3 ms ramp is inaudible and leaves
    the arithmetic above intact."""
    if 0 < j < len(segments):
        return max(0.003, float(segments[j].get("xfade", XF)))
    return 0.0


# Snap the plan, segment by segment and in order: validate, probe its file, move both ends onto that file's
# frame grid, and note how long its sound must run on into the next joint.
worst_shift = 0.0
placed = []   # per segment: (input index, snapped in, snapped out, sound run-on)
# The cut's own frame rate (its first clip's). A sped clip is re-timed onto THIS rate, never its own clip's: an
# iPhone shoots 59.94 one day and 60 the next, and sped segments re-timed each onto its own rate put two frames
# on one tick after enough joints ("non monotonically increasing dts"), so the render failed its integrity
# check on both encoders. Unsped segments are only trimmed, never re-timed, and concat already takes them.
out_rate = None
for i, seg in enumerate(segments):
    t0, t1 = float(seg["start"]), float(seg["end"])
    if t1 <= t0:
        sys.exit(f"cut {i} ends before it starts: {seg}")
    k = piece_input(i)
    num, den = frame_rate(sources[k])
    if out_rate is None:
        out_rate = (num, den)
    s0, s1 = on_frame_grid(t0, num, den), on_frame_grid(t1, num, den)
    if s1 <= s0:
        s1 = s0 + den / num                      # shorter than a frame still keeps one frame
    worst_shift = max(worst_shift, abs(s0 - t0), abs(s1 - t1))
    seg["start"], seg["end"] = s0, s1            # the EDL records the times that actually ship
    placed.append((k, s0, s1, joint_xfade(i + 1)))
    if float(seg.get("speed", 1.0) or 1.0) != 1.0 or seg.get("ramp"):
        # A sped clip is held to whole frames of the cut's rate; the EDL records the length it really plays.
        onum, oden = out_rate
        seg["played"] = max(1, round((s1 - s0) / float(seg["speed"]) * onum / oden)) * oden / onum


def speed_of(seg):
    return float(seg.get("speed", 1.0) or 1.0)


def atempo(speed):
    """atempo takes 0.5 to 100 per stage; a slower-than-half clip chains stages."""
    parts = []
    while speed < 0.5:
        parts.append("atempo=0.5"); speed /= 0.5
    parts.append(f"atempo={speed:.6f}")
    return parts


def framing(seg, k):
    """The zoom and nudge she set in CapCut, as a crop of the source scaled back to full frame. CapCut
    scales the fitted clip about the centre, then moves it by x and y in half-canvas units (y up)."""
    sc = float(seg.get("scale", 1.0) or 1.0)
    tx, ty = float(seg.get("x", 0.0) or 0.0), float(seg.get("y", 0.0) or 0.0)
    if abs(sc - 1.0) < 1e-4 and abs(tx) < 1e-4 and abs(ty) < 1e-4:
        return ""
    # The UPRIGHT size, never the stored one: ffmpeg turns a phone clip upright before the crop sees it, and a
    # vertical phone clip is usually stored sideways (3840x2160 + rotation), so the stored size made a crop
    # wider than the frame and the whole stitch failed (buyer report, 2026-10-14).
    w, h = display_dims(sources[k])
    cw, ch = w / sc, h / sc
    x0 = min(max(w / 2 - tx * w / (2 * sc) - cw / 2, 0.0), w - cw)
    y0 = min(max(h / 2 + ty * h / (2 * sc) - ch / 2, 0.0), h - ch)
    return f"crop={cw:.3f}:{ch:.3f}:{x0:.3f}:{y0:.3f},scale={w}:{h},setsar=1,"


@functools.lru_cache(maxsize=None)
def zoom_focus():
    """Where a zoom move holds still, as fractions of the frame: the middle of her head as the job measured it
    (subject-zones.json, from workflows/subject-zones.py), so she stays put while the frame moves in or out
    around her; the frame's centre when the job has no measurement."""
    jd = os.path.dirname(media_dir) if os.path.basename(os.path.normpath(media_dir)) == "raw" else media_dir
    try:
        with open(os.path.join(jd, "subject-zones.json"), encoding="utf-8") as fh:
            z = json.load(fh)
        src, box = (z.get("reading") or {}).get("source") or {}, z.get("subject_src_px") or {}
        if src.get("w") and box:
            fx, fy = (box["left"] + box["right"]) / 2 / src["w"], (box["head_top"] + box["chin_bottom"]) / 2 / src["h"]
        else:
            box = z.get("subject") or z.get("face") or {}
            import frame
            fw, fh = frame.size(jd)
            fx, fy = (box["left"] + box["right"]) / 2 / fw, (box["head_top"] + box["chin_bottom"]) / 2 / fh
        return min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0)
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return 0.5, 0.5


ZOOM_MAX = 3.0


def zoom_move(seg, frames):
    """A zoom MOVE across one clip (her page's Zoom in / Zoom out: "zoom": {"from": 1.15, "to": 1.0}): the picture
    goes from one scale to the other over the clip's played frames, eased in and out (smoothstep), about her face
    (zoom_focus) or the clip's own "cx" / "cy" fractions. perspective with per-frame expressions resamples every
    frame at sub-pixel positions (bicubic), so the move is smooth; zoompan rounds its window to whole pixels and
    judders. The window always stays inside the frame (a scale under 1 is held at 1). "" when there is no move."""
    z = seg.get("zoom")
    if not isinstance(z, dict):
        return ""
    ease = z.get("ease") if z.get("ease") in EASES else "inOut"   # smoothstep unless the move asks for another ease
    try:
        z0, z1 = float(z.get("from", 1.0)), float(z.get("to", 1.0))
        fx, fy = zoom_focus()
        fx, fy = float(z.get("cx", fx)), float(z.get("cy", fy))
    except (TypeError, ValueError):
        return ""
    z0, z1 = min(max(z0, 1.0), ZOOM_MAX), min(max(z1, 1.0), ZOOM_MAX)
    fx, fy = min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0)
    if abs(z0 - 1.0) < 1e-4 and abs(z1 - 1.0) < 1e-4:
        return ""
    last = max(1, int(frames) - 1)                       # frame 0 shows "from", the clip's last frame shows "to"
    if z.get("frames"):                                  # a move with its own length lands in that many frames and holds
        last = max(1, min(last, int(z["frames"]) - 1))
    p = f"min(1,in/{last})"
    Z = f"({z0:.5f}+({z1 - z0:.5f})*{ease_expr(ease, p)})"
    lo_x, hi_x = f"{fx:.5f}*W*(1-1/{Z})", f"({fx:.5f}*W+(W-{fx:.5f}*W)/{Z})"
    lo_y, hi_y = f"{fy:.5f}*H*(1-1/{Z})", f"({fy:.5f}*H+(H-{fy:.5f}*H)/{Z})"
    corners = dict(x0=lo_x, y0=lo_y, x1=hi_x, y1=lo_y, x2=lo_x, y2=hi_y, x3=hi_x, y3=hi_y)
    return "perspective=" + ":".join(f"{k}='{v}'" for k, v in corners.items()) + ":interpolation=cubic:eval=frame,"


# See product/video_encoder.py — shared across every ffmpeg render in the engine. 16 Mbps / CRF 17, the
# same as the well-done bake (build-reel-mp4.py): this cut is the BASE that bake re-encodes, so a thin
# first generation (it was 8 Mbps) showed up as soft footage in every finished reel built on it.
venc = pick_encoder(vbr="16M", crf=17, preset="veryfast")

# This run's EDL is the plan after the frame grid. The saved transcript/cuts.json and the caption transcript
# are both made from it, so both match the times in the rendered file to the frame.
edl_path = os.path.join(os.path.dirname(plan_path), "edl.json")
with open(edl_path + ".tmp", "w") as fh:
    json.dump(dict(plan, segments=segments), fh, indent=1)   # her audio clips etc. ride through with it
swap_in(edl_path + ".tmp", edl_path)   # swapped in whole: nobody ever reads half a file
sys.stderr.write(f"[stitch] every cut point now on a whole frame of its clip (the furthest moved "
                 f"{worst_shift * 1000:.1f} ms); EDL → {edl_path}\n")

if edl_only:
    sys.stderr.write("[stitch] FLAT_RENDER=0: the EDL is this run's whole output, nothing is encoded\n")
    sys.exit(0)

# Phone footage frequently tags itself FULL range (pc). Left alone, segments disagree with each
# other going into concat and with the bt709/limited tags the encoder stamps on the way out, and a
# browser then decodes every frame PURE BLACK while the audio plays fine — no error anywhere. So
# convert each segment's pixels to limited range and tag them to match, before they are concatenated:
# after this, the data and the output tags say the same thing. (PC test, 2026-09-18.)
VNORM = ("format=yuv420p,scale=in_range=auto:out_range=tv,"
         "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")

# ONE PICTURE FOR THE WHOLE CUT. concat joins only pictures of one size, and every builder after the stitch works in
# the 9:16 authoring frame (subject-zones refuses any other shape). Clips of different sizes in one cut (one phone
# exporting at a few sizes, or two cameras) used to stop the stitch outright ("Input link in0:v0 parameters (size
# 1504x2000 ...) do not match"), and a cut of 3:4 phone clips shipped at 3:4, so nothing could be placed around her
# (buyer report, 2026-10-26). So the cut gets one frame:
#   a vertical cut  the biggest 9:16 frame its clips fill; a vertical clip of another shape is scaled to cover it and
#                   centred (the sides of a 3:4 clip go, never the top of her head), a landscape clip in it is fitted
#                   inside with bars, so nothing of it is lost
#   any other cut   the biggest clip's frame, every other clip fitted inside with bars; the reframe to 9:16 comes later
# A cut whose clips already share one 9:16 size (or one size, for a landscape cut) gets no filter at all.
def _even(v):
    return int(v) - int(v) % 2


_sizes = [display_dims(sources[k]) for k, *_ in placed]
_upright = sum(1 for w, h in _sizes if h > w) * 2 > len(_sizes)      # most of the cut's pieces are vertical
if _upright:
    # 9 and 16 times one even unit: both sides even and exactly 9:16, the shape subject-zones.py's guard asks for
    _unit = max(_even(min(w / 9, h / 16)) for w, h in _sizes if h > w)
    canvas = (9 * _unit, 16 * _unit)
else:
    canvas = max(set(_sizes), key=lambda wh: wh[0] * wh[1])
    canvas = (_even(canvas[0]), _even(canvas[1]))
if all(wh == canvas for wh in _sizes):
    canvas = None                                    # already one size (and 9:16 when vertical): nothing to do


def one_frame(k):
    """The filter that puts input k onto the cut's one frame, "" when it is already that size."""
    if canvas is None:
        return ""
    w, h = display_dims(sources[k])
    cw, ch = canvas
    if (w, h) == canvas:
        return ""
    if _upright and h > w:                           # cover and centre: the frame filled, the sides trimmed
        s = max(cw / w, ch / h)
        sw, sh = max(cw, 2 * math.ceil(w * s / 2)), max(ch, 2 * math.ceil(h * s / 2))
        return f"scale={sw}:{sh},crop={cw}:{ch},setsar=1,"
    s = min(cw / w, ch / h)                          # fit inside, bars where the shapes differ
    sw, sh = min(cw, max(2, _even(w * s))), min(ch, max(2, _even(h * s)))
    return f"scale={sw}:{sh},pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2,setsar=1,"


if canvas is not None:
    _shown = sorted(set(_sizes))
    sys.stderr.write(f"[stitch] the clips come as {', '.join(f'{w}x{h}' for w, h in _shown)}; every piece goes onto "
                     f"one {canvas[0]}x{canvas[1]} frame"
                     + (" (9:16), so the cut joins and everything after it can place around her\n" if _upright
                        else ", so the cut joins\n"))

# The graph: every segment's picture and sound chains, the picture concat, the sound joins, the master.
n = len(segments)


def piece_chains(i, kin, ss):
    """Segment i's picture chain (into [v<i>]) and sound chain (into [a<i>]), read from ffmpeg input number kin, an
    input of its file that starts reading ss seconds in (READING ORDER, GROUPS). -> (the two chains, its length on the
    finished timeline)."""
    k, s0, s1, run_on = placed[i]
    seg = segments[i]
    sp = speed_of(seg)
    i0, i1 = s0 - ss, s1 - ss                  # in and out on this input's clock
    if sp == 1.0 and not seg.get("ramp"):
        d = s1 - s0
        num, den = frame_rate(sources[k])
        frames = round(d * num / den)
        vchain = f"trim={i0}:{i1},setpts=PTS-STARTPTS"
        # Held to its exact length, like a sped clip's: a phone clip's sound often stops a frame or a few before its
        # picture, so a piece cut to the clip's end came out that much short, every joint after it drew her words
        # ahead of her mouth, and the sound-only rebuild below made the same short track again ("100 ms short of
        # the picture", then "could not be rebuilt", buyer report 2026-10-26). apad fills only past the sound's end.
        sound = [f"atrim={i0}:{s1 + run_on - ss}", "asetpts=PTS-STARTPTS", "aresample=48000:ochl=stereo",
                 "apad", f"atrim=0:{d + run_on}"]
    else:
        # A sped clip plays (s1 - s0) / speed long. Held to a whole number of frames, on the cut's own rate
        # (out_rate, above), so its picture and sound agree exactly and concat has nothing to pad (see FRAME GRID).
        num, den = out_rate
        d = seg["played"]
        frames = round(d * num / den)
        vchain = (f"trim={i0}:{i1},setpts=(PTS-STARTPTS)/{sp},fps={num}/{den},"
                   f"trim=end_frame={frames},setpts=PTS-STARTPTS")
        if seg.get("ramp"):
            # The ramp, one fluid clip: each footage frame (at T seconds into the clip) goes to the played time u*d
            # where the eased speed curve reaches it, found by bisection in the expression itself (exact to well
            # under a microsecond); fps then samples it onto whole frames of the cut. Same played length as above.
            r = seg["ramp"]
            u, avg = "ld(2)", sp
            reach = f"(({r['from']:.6f})*{u}+({r['to'] - r['from']:.6f})*{area_expr(r['ease'], u)})/{avg:.6f}"
            expr = (f"st(0,0);st(1,1);st(3,0);st(4,min(1,T/{s1 - s0:.6f}));"
                    f"while(lt(ld(3),32),st(2,(ld(0)+ld(1))/2);if(lt({reach},ld(4)),st(0,ld(2)),st(1,ld(2)));st(3,ld(3)+1));"
                    f"(ld(0)+ld(1))/2*{d:.6f}/TB")
            vchain = (f"trim={i0}:{i1},setpts=PTS-STARTPTS,settb=AVTB,setpts='{expr}',fps={num}/{den},"   # a fine clock: no two frames on one tick
                      f"trim=end_frame={frames},setpts=PTS-STARTPTS")
        # The sound reads enough source to fill the whole-frame length plus the run-on, with 50 ms to spare.
        # "played" can round up past the clip's true sped length, and atempo hands back a millisecond or two
        # short; whatever apad then filled was digital silence sitting on the joint, which the crossfade turned
        # into a click (4 of 33 joints on a reel sped to 1.08, buyer report 2026-10-17). apad now only matters
        # for a clip at the very end of its file.
        src_end = s0 + (d + run_on) * sp + 0.05
        sound = ([f"atrim={i0}:{src_end - ss}", "asetpts=PTS-STARTPTS"] + atempo(sp)
                 + ["aresample=48000:ochl=stereo", "apad", f"atrim=0:{d + run_on}"])
    picture = (f"[{kin}:v]{colour_in(sources[k])}{vchain},{framing(seg, k)}{zoom_move(seg, frames)}{one_frame(k)}"
               f"{VNORM}[v{i}]")
    if seg.get("audio_detached"):
        # Her sound for this clip lives on its own audio clip (one of the overlays), so the clip is silent here.
        sound = ["anullsrc=r=48000:cl=stereo", f"atrim=0:{d + run_on}", "asetpts=PTS-STARTPTS"]
        src = ""
    else:
        src = f"[{kin}:a]"
    if i == 0:
        sound.append(f"afade=t=in:st=0:d={EDGE}")
    if i == n - 1:
        sound.append(f"afade=t=out:st={max(0.0, d - EDGE):.6f}:d={EDGE}")
    return [picture, src + ",".join(sound) + f"[a{i}]"], d


# A cut that mixes frame rates (59.94 and 60 from the same phone) goes onto the cut's one rate after the join,
# sped or not: concat keeps each clip's own frame times, and a 60 fps stretch in a 59.94 cut lands two frames on
# one tick of the output, which fails the integrity check on both encoders. fps works from each frame's real
# time, so nothing drifts; it drops one frame in about a thousand. A cut on one rate gets no filter at all.
one_rate = len({frame_rate(sources[k]) for k, *_ in placed}) == 1


def joins(idx, vout, aout):
    """The picture concat of segments idx (in cut order, each chain made by piece_chains) into [vout], and their sound
    joined at every joint into [aout]."""
    idx = list(idx)
    g = ["".join(f"[v{i}]" for i in idx) + f"concat=n={len(idx)}:v=1:a=0"
         + ("" if one_rate else f",fps={out_rate[0]}/{out_rate[1]}") + f"[{vout}]"]
    if len(idx) == 1:
        g.append(f"[a{idx[0]}]anull[{aout}]")   # one segment, no joints: straight on
    else:
        mix = [f"a{idx[0]}"] + [f"ax{j}" for j in idx[1:-1]] + [aout]    # the running mix after each joint
        for m, j in enumerate(idx[1:], 1):
            g.append(f"[{mix[m - 1]}][a{j}]acrossfade=d={joint_xfade(j)}:c1=qsin:c2=qsin[{mix[m]}]")
    return g


graph = []
lengths = []   # each segment's length on the finished timeline
for i, (k, *_r) in enumerate(placed):
    chains, d = piece_chains(i, k, seeks[k])
    graph += chains
    lengths.append(d)
graph += joins(range(n), "vc", "ac")


# The master: one fixed gain for the whole reel, then a fixed chain. Nothing in it follows the level over
# time, so her quiet lines stay quieter than her loud ones. VOICE_GAIN_DB defaults to 10 because that is
# where her own recordings sit with the limiter working within its range; sound-check.py reports when a
# reel's limiter works harder than that and names the setting to lower. Only the limiter looks ahead, and
# its delay is taken back out, so the sound stays on the picture.
def limiter(ceiling):
    # Only three settings differ from alimiter's own: the ceiling; level=false, because left on the filter
    # raises the limited track back toward the ceiling on its own; latency=true, so its lookahead does not
    # leave the sound late against the picture.
    return f"alimiter=limit={ceiling}:level=false:latency=true"


if warm:
    # The voice master (the default): body in the low mids, less box and less tinny edge, the room tail
    # between words held down, a light compressor, then a −1 dBFS ceiling.
    master = [f"volume={gain}dB",
              "highpass=f=75",                                                 # rumble out
              "equalizer=f=200:width_type=q:w=1.0:g=3",                        # low-mid body
              "equalizer=f=440:width_type=q:w=1.5:g=-2",                       # boxiness
              "equalizer=f=3400:width_type=q:w=2.5:g=-2.5",                    # presence peak
              "equalizer=f=7000:width_type=q:w=3.0:g=-3.5",                    # the tinny edge
              "lowpass=f=12500",                                               # brittle top
              "agate=threshold=0.012:ratio=1.5:attack=20:release=260",         # room tail between words
              "acompressor=threshold=-20dB:ratio=2.5:attack=12:release=160:makeup=3",   # glue
              limiter("0.89")]
else:
    # WARM_MASTER=0: the flat path, the gain straight into a −6 dBFS ceiling.
    master = [f"volume={gain}dB", limiter("0.501")]


def sound_tail(overlay_input):
    """[ac] to [ao]: her own audio clips, laid in where she put them (overlay_input(clip) is the ffmpeg input that
    reads the clip from the top), before the master so they get the same voice treatment; then the master."""
    g = []
    if overlays:
        for j, o in enumerate(overlays):
            k = overlay_input(o["clip"])
            o0, o1 = float(o["start"]), float(o["end"])
            delay = max(0, round(float(o.get("target_start", 0.0)) * 1000))
            g.append(f"[{k}:a]atrim={o0}:{o1},asetpts=PTS-STARTPTS,aresample=48000:ochl=stereo,"
                     f"volume={float(o.get('volume', 1.0))},afade=t=in:st=0:d={EDGE},"
                     f"afade=t=out:st={max(0.0, (o1 - o0) - EDGE):.6f}:d={EDGE},adelay={delay}:all=1[o{j}]")
        g.append("[ac]" + "".join(f"[o{j}]" for j in range(len(overlays)))
                 + f"amix=inputs={len(overlays) + 1}:duration=first:normalize=0[acm]")
        g.append("[acm]" + ",".join(master) + "[ao]")
    else:
        g.append("[ac]" + ",".join(master) + "[ao]")
    return g


graph += sound_tail(source_index)

AUDIO_OUT = ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]
CONTAINER = ["-video_track_timescale", "90000", "-movflags", "+faststart"]
FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
scratch = os.path.dirname(plan_path)
try:                                         # the Finish tab's bar follows this encode (a no-op outside an export)
    from export_progress import ffmpeg_args as _progress, stage as _stage
except ImportError:
    _progress = lambda _s: []
    _stage = lambda *_a, **_k: None
expected = sum(lengths)   # the timeline length the EDL asks for (a sped clip counts at its played length)

# GROUPS. One ffmpeg graph does the whole cut, and its cost grows with the square of the pieces: every frame decoded
# from a file goes to every piece cut from it, and ffmpeg looks over every filter in the graph for each of those
# steps. An 8-minute take cut into 191 pieces ran on one core at about 2 s of finished cut a minute, hours for the
# whole reel, at 4K or at 1080 alike (a buyer report, 2026-10-28; 100 pieces of a 5-minute 1080 clip took 200 s here,
# 190 pieces 21 minutes). So a cut of more than STITCH_GROUP pieces (16 unless set; 0 = always one graph) is
# made a group of pieces at a time, one after another, each its own small ffmpeg run: the same chains (piece_chains)
# and joints (joins), each forward run of a group's pieces read from its own input seeked to 2 s before it on a whole
# second (READING ORDER), so only one group's decoding is ever in memory. Each group writes its picture, encoded,
# and its joined sound, every sample as it was (32-bit float). Then one last run puts the pictures end to end as
# they are (no second encode) and joins the groups' sound at their own joints, with exactly the crossfade each joint
# always had, before her audio clips and the master run over the whole reel as before. The same 190 pieces take
# 22 s, checks included. A cut that mixes frame rates stays one graph: its rate filter runs on the whole join.
try:
    GROUP = max(0, int(os.environ.get("STITCH_GROUP") or 16))
except ValueError:
    GROUP = 16
grouped = bool(GROUP) and n > GROUP and one_rate
for _old in os.listdir(scratch):             # a stopped run's group files never join this run's cut
    if _old.startswith("group-") or _old in ("groups.txt", "graph-join.txt"):
        try:
            os.remove(os.path.join(scratch, _old))
        except OSError:
            pass
if not grouped:
    # The graph goes to ffmpeg in a file, never inline: it grows by about 350 characters per kept line, and Windows
    # refuses a command line over 32,767 (WinError 206), so a long cut (about 90 lines, fewer for HDR clips) could
    # not be stitched on a PC at all. It sits beside this run's EDL in the scratch folder.
    graph_args = filter_complex_args(";".join(graph), os.path.join(scratch, "graph.txt"))
    sound_inputs = input_args
    sound_graph = [g for g in graph if not re.search(r"\[v(?:c|\d+)\]$", g)]   # every chain that ends in sound
else:
    G = math.ceil(n / GROUP)
    bounds = [round(g * n / G) for g in range(G + 1)]          # G groups as even as the pieces allow
    group_jobs = []
    group_sound = []   # per group: its inputs, its pieces, where each reads from, its files' stem (a joint fix below)
    for g in range(G):
        idx = list(range(bounds[g], bounds[g + 1]))
        args, at, ends = [], {}, {}
        for i in idx:
            k, s0, s1, _r = placed[i]
            path = sources[k]
            fits = [r for r in ends.setdefault(path, []) if r[0] <= s0 + RUN_SLACK]
            run = max(fits, key=lambda r: r[0]) if fits else None   # the run that left off nearest before this piece
            if run is None:
                run = [s1, len(args) // 4, max(0, math.floor(s0) - 2)]   # [furthest end, its input, where it reads from]
                ends[path].append(run)
                args += ["-ss", str(run[2]), "-i", path]
            run[0] = max(run[0], s1)
            at[i] = (run[1], run[2])
        chains = []
        for i in idx:
            chains += piece_chains(i, *at[i])[0]
        stem = os.path.join(scratch, f"group-{g:03d}")
        group_jobs.append((args, filter_complex_args(";".join(chains + joins(idx, "vc", "ac")), stem + ".txt"),
                           stem + ".mp4", stem + ".wav", sum(lengths[i] for i in idx)))
        group_sound.append((args, idx, at, stem))
    with open(os.path.join(scratch, "groups.txt"), "w", encoding="utf-8") as fh:   # names beside the list: any OS path
        fh.writelines(f"file '{os.path.basename(job[2])}'\n" for job in group_jobs)
    join_in = ["-f", "concat", "-safe", "0", "-i", os.path.join(scratch, "groups.txt")]
    sound_in = [a for job in group_jobs for a in ("-i", job[3])]  # group g's sound is input g + 1
    over_args, over_at = [], {}

    def over_input(clip):
        """The input reading one of her audio clips from the top, in the joining run (after the groups' sound)."""
        path = clip_path(clip)
        if path not in over_at:
            over_at[path] = 1 + G + len(over_at)
            over_args.extend(["-i", path])
        return over_at[path]

    def join_sound_graph():
        """The groups' sound joined at their own joints, then her audio clips and the master."""
        mix = ["1:a"] + [f"gx{g}" for g in range(1, G - 1)] + ["ac"]
        return [f"[{mix[g - 1]}][{g + 1}:a]acrossfade=d={joint_xfade(bounds[g])}:c1=qsin:c2=qsin[{mix[g]}]"
                for g in range(1, G)] + sound_tail(over_input)

    join_sound = join_sound_graph()
    join_graph = filter_complex_args(";".join(join_sound), os.path.join(scratch, "graph-join.txt"))
    sound_inputs = lambda: join_in + sound_in + over_args
    sound_graph = join_sound                 # the rebuild below reads the same groups' sound, nothing of the picture
    sys.stderr.write(f"[stitch] {n} pieces: made in {G} groups of {GROUP} or fewer, one after another, then joined\n")


def render(enc):
    """The whole cut, its picture on the video encoder `enc` -> ffmpeg's return code (a signal as a negative)."""
    if not grouped:
        return subprocess.run(FFMPEG + _progress(expected) + input_args() + graph_args + ["-map", "[vc]", "-map", "[ao]"]
                              + enc + AUDIO_OUT + CONTAINER + [out_path]).returncode
    done = 0.0
    for args, gargs, pic, snd, length in group_jobs:
        _stage(0.9 * done / expected, 0.9 * (done + length) / expected)
        rc = subprocess.run(FFMPEG + _progress(length) + args + gargs + ["-map", "[vc]"] + enc + [pic]
                            + ["-map", "[ac]", "-c:a", "pcm_f32le", snd]).returncode
        if rc != 0:
            return rc
        done += length
    _stage(0.9, 1.0)
    return subprocess.run(FFMPEG + _progress(expected) + join_in + sound_in + over_args + join_graph
                          + ["-map", "0:v", "-map", "[ao]", "-c:v", "copy"] + AUDIO_OUT + CONTAINER + [out_path]).returncode


def _clear_groups():
    if grouped:
        for job in group_jobs:
            for f in (job[2], job[3], job[2][:-4] + ".txt"):
                try:
                    os.remove(f)
                except OSError:
                    pass


atexit.register(_clear_groups)               # every way out of this program, the group files go
# --- render + self-heal ------------------------------------------------------------------
# A hardware encoder (Apple's videotoolbox, or NVENC on Windows/Linux when a GPU is present) can
# occasionally finalize a SHORT or NAL-corrupt file while still exiting 0 (session pressure / GPU
# contention). Nothing downstream re-checked it, so that broken file could ship. So: validate the
# output, and if it is bad, retry ONCE on the always-present software encoder (libx264); if it is
# STILL bad, exit non-zero so the pipeline stops instead of handing off a broken cut.
def _dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except Exception: return -1.0


# The render has to WRITE the file. When both encoders fail without writing one, the PREVIOUS run's cut is
# still sitting at out_path and passes every check below (right length, decodes clean), which used to end
# in "✓ clean render" and exit 0 over a cut this run never made. So note what was there before, and never
# accept that same file back as this render.
def _stamp(p):
    try:
        st = os.stat(p)
        return (st.st_ino, st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _whole(p):
    if not os.path.exists(p) or os.path.getsize(p) < 1024:
        return False
    if before is not None and _stamp(p) == before:   # untouched since before the render: the previous cut
        return False
    if abs(_dur(p) - expected) > max(0.75, 0.03 * expected):   # gross-corruption tolerance; ignores tiny crossfade diffs
        return False
    scan = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "null", "-"],
                          capture_output=True, text=True)
    return scan.returncode == 0 and not scan.stderr.strip()

before = _stamp(out_path)
rc = render(venc)

# A render ended from outside is not an encoder failure. Signal 9 is the system ending ffmpeg (most often because the
# computer ran out of memory), and the same graph on libx264 only ends the same way, hours later: a buyer's 4K cut
# was retried twice, for three and a half hours in all (2026-10-22). Signals 2 and 15 are a stop. Each is handed back
# as the shell sees it (137, 130, 143), so the stitch says so plainly and tries nothing else.
def _unless_ended(rc):
    if rc in (-9, -2, -15):
        if rc == -9:
            sys.stderr.write("[stitch] ✗ the computer ended the render partway (signal 9), most often because it ran "
                             "out of memory, so no other encoder is tried\n")
        sys.exit(128 - rc)


_unless_ended(rc)

# A hardware encoder can fail EITHER of two ways, and both mean the same thing: this machine's
# hardware path cannot be trusted for this render.
#   1. It exits NON-ZERO outright. On Windows the common cause is an NVENC driver/API mismatch
#      ("Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0") —
#      a stock OEM NVIDIA driver lagging the ffmpeg build the buyer just installed. No output
#      file is produced at all.
#   2. It exits ZERO having finalized a SHORT or NAL-corrupt file (session pressure / GPU
#      contention), which is what the integrity gate below was originally written for.
# Case 1 used to `sys.exit(rc)` right here, one line above a working software fallback it never
# reached — so a buyer with an out-of-date NVIDIA driver got a dead render and no way around it.
# Now either failure falls back to libx264, which every ffmpeg build ships and which needs no GPU.
# (Found on the PC test, 2026-09-18.)
_hw = any(e in " ".join(venc) for e in ("nvenc", "videotoolbox", "qsv", "amf", "vaapi"))
if rc != 0 and not _hw:
    sys.exit(rc)                                       # already the software encoder — a real ffmpeg failure

if rc != 0 or not _whole(out_path):
    _why = f"exited {rc}" if rc != 0 else "produced a short/corrupt file"
    sys.stderr.write(f"[stitch] ⚠ hardware encoder {_why} — retrying on the software encoder (libx264)\n")
    sw = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p"] + COLOR_FLAGS
    _unless_ended(render(sw))                          # every group again, so the pictures all match before the join
    if not _whole(out_path):
        if _stamp(out_path) is None:
            sys.stderr.write("[stitch] ✗ neither encoder wrote the file — no render to hand over\n")
        elif _stamp(out_path) == before:
            sys.stderr.write("[stitch] ✗ neither encoder wrote a new file; the one at the output path is the "
                             "previous cut — refusing to hand it over as this one\n")
        else:
            sys.stderr.write("[stitch] ✗ render still short/corrupt after fallback — refusing to ship a broken cut\n")
        sys.exit(3)
    sys.stderr.write("[stitch] ✓ software-encoder fallback produced a clean render\n")


# --- sound and picture the same length ----------------------------------------------------------------------
# The checks above read the FILE's length, which is its longest stream. A render can come out with the picture
# whole and the sound track ending early, no dead air at any joint: her words run ahead of her mouth toward the
# end, and stitching again the same way made the same file (buyer reports, 2026-10-19). So each stream is
# measured on its own after the master. When they disagree by more than one AAC frame and a video frame, the
# sound graph alone is rendered again (no picture in that ffmpeg run to hold its sound back) and put under
# the picture as it is, the picture copied, never re-encoded.
def _stream_dur(p, kind):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", f"{kind}:0", "-show_entries",
                        "stream=duration", "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try:
        return float(r.stdout.split()[0])
    except (IndexError, ValueError):
        return None


SYNC_SLACK = 1024 / 48000 + 1 / 24   # one AAC frame (the encoder's own tail) and one video frame


def _drift(p):
    """Sound length minus picture length in seconds (None when either can't be read)."""
    vd, ad = _stream_dur(p, "v"), _stream_dur(p, "a")
    return None if vd is None or ad is None else ad - vd


def _resound(inputs, chains, graph_name):
    """Render the sound chains alone (no picture in that ffmpeg run to hold its sound back) and put the result under
    the cut's picture as it is, the picture copied, never re-encoded. The sound runs on to the picture's length
    (apad, then -t), so it is never short of the picture. -> (the new cut, written beside the old one, None) or
    (None, why it did not take, in ffmpeg's own words)."""
    scratch = os.path.dirname(plan_path)
    sound_only = os.path.join(scratch, "sound-only.m4a")
    resound = os.path.splitext(out_path)[0] + ".resound" + os.path.splitext(out_path)[1]
    vlen = _stream_dur(out_path, "v")
    if vlen is None:
        return None, "the cut's picture length could not be read"
    r1 = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"] + inputs
                        + filter_complex_args(";".join(chains).replace("[ao]", "[aom]") + ";[aom]apad[ao]",
                                              os.path.join(scratch, graph_name))
                        + ["-map", "[ao]", "-vn", "-t", f"{vlen:.6f}"] + AUDIO_OUT + [sound_only],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    r2 = None
    if r1.returncode == 0 and os.path.exists(sound_only):
        r2 = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", out_path,
                             "-i", sound_only, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                             "-movflags", "+faststart", resound],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")

    def _last_line(run):
        return next((ln.strip() for ln in reversed((run.stderr or "").splitlines()) if ln.strip()), "")

    _drop(sound_only)
    if r2 is None:
        return None, f"rendering the sound alone failed: {_last_line(r1) or f'ffmpeg exited {r1.returncode}'}"
    if r2.returncode != 0 or not os.path.exists(resound):
        _drop(resound)
        return None, f"putting it under the picture failed: {_last_line(r2)}".rstrip(": ")
    return resound, None


def _drop(path):
    if path and os.path.exists(path):
        os.remove(path)


drift = _drift(out_path)
if drift is not None and abs(drift) > SYNC_SLACK:
    sys.stderr.write(f"[stitch] the sound track came out {abs(drift) * 1000:.0f} ms "
                     f"{'short of' if drift < 0 else 'longer than'} the picture; building the sound again on its own\n")
    # Whatever made the full render's track short, the rebuilt one is never short of the picture (_resound).
    resound, why = _resound(sound_inputs(), sound_graph, "graph-sound.txt")
    fixed = _drift(resound) if resound else None
    # Why it did not take, in ffmpeg's own words or the numbers, for the warning and for /report-a-problem.
    if resound and fixed is None:
        why = "the rebuilt cut's sound or picture length could not be read"
    elif resound:
        why = f"the rebuilt sound came out {fixed * 1000:+.0f} ms against the picture, no closer"
    if fixed is not None and abs(fixed) < abs(drift):
        swap_in(resound, out_path)   # swapped in whole (a hardlinked copy of the old cut is never rewritten)
        if abs(fixed) <= SYNC_SLACK:
            sys.stderr.write(f"[stitch] ✓ sound rebuilt and put under the picture: they now match ({fixed * 1000:+.0f} ms)\n")
        else:
            sys.stderr.write(f"[stitch] ⚠ sound rebuilt and put under the picture; it is still {fixed * 1000:+.0f} ms "
                             f"against the picture. The cut is usable; run /report-a-problem so this gets fixed.\n")
    else:
        sys.stderr.write(f"[stitch] ⚠ the sound could not be rebuilt on its own ({why[:300]}), so the cut is kept "
                         "as rendered; run /report-a-problem so this gets fixed.\n")
    _drop(resound)


# --- a click or a dip at one joint ----------------------------------------------------------------------------
# sound-check hears every joint once the cut is saved, and the first fix it names for a click or a dip at one of
# them is a 30 ms crossfade there ("xfade": 0.030 on the segment the joint leads into, see joint_xfade). That fix
# moves nothing on the timeline: the outgoing sound runs on 30 ms instead of 6 and the two blend over that stretch,
# so the picture never changes. A buyer was told to type it into cuts.json herself and stitch again (2026-10-28).
# So the stitch hears its own joints first, with sound-check's own hear_each (never a copy of it), gives each joint
# it flags that crossfade, renders the sound alone again and hears it once more. The longer run-on can reach into
# whatever she said next in the take (JOINTS, above), so a joint it made worse goes back to its own crossfade, and
# the sound is made once more with only the joints it helped. The new sound is kept unless a joint that was clean
# is not any more; the EDL then records each crossfade it kept (and "_xfade_worse" where it made one worse), so
# sound-check reads the sound that ships and names the next fix ("keep_edges") for a joint that still needs one. When the joints say the crossfade itself is broken
# across the reel, nothing is tried here: that is sound-check's to say.
def _sound_check():
    """sound-check.py, loaded from beside this script (None when it is not there)."""
    import importlib.util
    path = os.path.join(os.environ.get("REELS_ENGINE_ROOT", ""), ".claude", "skills", "rough-cut", "scripts",
                        "sound-check.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("sound_check", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fix_joints():
    """Hear the joints, give the ones that click or dip the longer crossfade, keep it where it helps."""
    def _hear(path):
        return sc.hear_each(sc._decode(path), sc.plan_joints(segments)[0])

    def _better(b, a):
        """The longer crossfade left this joint (heard as b before, as a after) no worse than it found it."""
        if not a[6]:
            return True
        louder = a[3] > sc.CLICK_RATIO and a[3] >= b[3]
        deeper = a[4] is not None and a[4] < -sc.DIP_DB and (b[4] is None or a[4] <= b[4])
        return not (louder or deeper)

    heard = _hear(out_path)
    tries = [e for e in heard if e[6] and e[5] < sc.DEAD_AIR and joint_xfade(e[2]) < sc.LONGER_XFADE]
    if tries and not sc.stitch_broken(heard):
        was = {e[2]: segments[e[2]].get("xfade") for e in tries}

        def _set(keep):
            """Each tried joint at the longer crossfade when it is in keep, else at what it had; the piece before
            each joint runs on for its crossfade."""
            for j, x in was.items():
                if j in keep:
                    segments[j]["xfade"] = sc.LONGER_XFADE
                elif x is None:
                    segments[j].pop("xfade", None)
                else:
                    segments[j]["xfade"] = x
                k, s0, s1, _r = placed[j - 1]
                placed[j - 1] = (k, s0, s1, joint_xfade(j))

        def _joint_sound():
            """(inputs, chains) for the sound alone with today's crossfades, or None when a group's sound would not
            make. A cut of a few pieces is one graph. A grouped cut makes again, sound only, each group a tried
            joint's run-on sits in, and joins the groups as the render did: one graph of every piece costs the
            square of the pieces in sound too (53 pieces, 14 s; 190, minutes)."""
            if not grouped:
                chains = [piece_chains(i, k, seeks[k])[0][1] for i, (k, *_r) in enumerate(placed)]
                return input_args(), chains + joins(range(n), "vc", "ac")[1:] + sound_tail(source_index)
            for args, idx, at, stem in group_sound:
                if not any(j - 1 in idx for j in was):
                    continue
                chains = [piece_chains(i, *at[i])[0][1] for i in idx] + joins(idx, "vc", "ac")[1:]
                rc = subprocess.run(FFMPEG + args + filter_complex_args(";".join(chains), stem + "-sound.txt")
                                    + ["-map", "[ac]", "-c:a", "pcm_f32le", stem + ".wav"]).returncode
                _drop(stem + "-sound.txt")
                if rc != 0:
                    return None
            return sound_inputs(), join_sound_graph()

        def _attempt(keep):
            """The sound made again with the longer crossfade at the joints in keep -> (the new cut, its joints
            heard, why it did not make)."""
            _set(keep)
            made = _joint_sound()
            if not made:
                return None, [], "a group's sound would not make"
            new, why = _resound(*made, "graph-joints.txt")
            return new, (_hear(new) if new else []), why

        def _helped(again):
            now = {e[0]: e for e in again}
            return {e[2] for e in tries if e[0] in now and _better(e, now[e[0]])}

        keep = set(was)
        resound, again, why = _attempt(keep)
        helped = _helped(again)
        if again and helped and helped != keep:
            keep = helped
            _drop(resound)
            resound, again, why = _attempt(keep)
            helped = _helped(again)
        clean = {e[0] for e in heard if not e[6]}
        worse = [e for e in again if e[0] in clean and e[6]]
        accept = again and helped and helped >= keep and not worse

        def _save_edl(made_worse):
            """The EDL with each tried joint as it ships; "_xfade_worse" marks one the longer crossfade made worse,
            so sound-check names the next fix there instead of the one just tried."""
            for j in was:
                if j in made_worse:
                    segments[j]["_xfade_worse"] = sc.LONGER_XFADE
                else:
                    segments[j].pop("_xfade_worse", None)
            with open(edl_path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(dict(plan, segments=segments), fh, indent=1)
            swap_in(edl_path + ".tmp", edl_path)

        if accept:
            swap_in(resound, out_path)
            _save_edl(set(was) - keep)
            now = {e[0]: e for e in again}
            longer = f"{sc.LONGER_XFADE * 1000:.0f} ms"
            for jn, t, j, *_m, found in tries:
                if j not in keep:
                    done = f"a {longer} crossfade made it worse, so it keeps its own (sound-check names the next step)"
                elif now.get(jn) and not now[jn][6]:
                    done = f"it now crossfades over {longer} (the sound made again, the picture untouched) and hears clean now"
                else:
                    done = (f"it now crossfades over {longer} (the sound made again, the picture untouched), better but"
                            " still worth a listen (sound-check names the next step)")
                sys.stderr.write(f"[stitch] {'✓' if j in keep else '·'} joint {jn} at {t:.2f}s, into segments[{j}]"
                                 f"{sc._words(segments[j])}, had {'; '.join(found)}: {done}\n")
        else:
            _set(set())
            if worse:
                why = f"it made joint {worse[0][0]} worse"
            elif again and not helped:
                why = "it made no joint better"
                _save_edl(set(was))
            sys.stderr.write(f"[stitch] a {sc.LONGER_XFADE * 1000:.0f} ms crossfade at {len(tries)} joint"
                             f"{'s' if len(tries) > 1 else ''} did not take ({(why or 'no sound to hear')[:300]}), so "
                             "the cut keeps its sound as rendered\n")
        _drop(resound)


# The cut is already whole here, so this is never what stops a stitch: anything it can't do leaves the cut as rendered.
try:
    sc = _sound_check() if n > 1 else None
    if sc is not None:
        _fix_joints()
except Exception as e:   # noqa: BLE001
    sys.stderr.write(f"[stitch] the joints could not be heard again ({type(e).__name__}: {str(e)[:200]}), so the cut "
                     "keeps its sound as rendered\n")
    _drop(os.path.splitext(out_path)[0] + ".resound" + os.path.splitext(out_path)[1])
sys.exit(0)
PY
  # The snap moves edges by tens of milliseconds and keeps every word, so a plan it touched that will not
  # build is the snap's doing far more often than the footage's. The plan as written (with the quick restarts
  # already out) is a working cut, so it gets one more try before the stitch stops. Not when she stopped it
  # (130/143), not when the computer ended it (137: the same graph would only be ended again), and not when the
  # snap never ran: then there is no other plan to try. Whatever the stopped
  # attempt left behind goes first, the EDL above all, so only what the retry itself writes can be saved
  # (an old output file is refused by the program's own before/after check).
  if [ "$render_rc" -ne 0 ] && [ "$render_rc" -ne 130 ] && [ "$render_rc" -ne 143 ] && [ "$render_rc" -ne 137 ] \
     && { [ "$CUTS" = "$WORK/cuts.edges.json" ] || [ "$CUTS" = "$WORK/cuts.tight.json" ]; } && [ -f "$WORK/cuts.json" ]; then
    echo "[stitch] the snapped plan would not build (reason above), so building the cut once more on the edges as written." >&2
    CUTS="$WORK/cuts.json"
    rm -f "$WORK/edl.json" "$WORK/cuts.snapped.json"
    render_rc=0
    _render_retried=1
    continue
  fi
  break
done
if [ "$_render_retried" = 1 ] && [ "$render_rc" -eq 0 ]; then
  echo "[stitch] built on the edges as written; the boundary snap is left out of this cut." >&2
  note_fallback stitch "the render stopped on the snapped plan for $JOB_NAME; built the cut on the edges as written"
fi

if [ "${render_rc:-0}" -ne 0 ]; then
  if [ "$FLAT_RENDER" = 1 ] && [ "$render_rc" -eq 3 ]; then
    # Exit 3, and only exit 3, is the render self-check: the retry and the software-encoder fallback are
    # exhausted, so the render itself is broken on this machine, and that is worth a hardware report.
    HANDOFF="$HERE/../../../../product/make-handoff.py"
    [ -f "$HANDOFF" ] && python3 "$HANDOFF" render \
      "Render came out short or corrupt on this machine, even after the software-encoder fallback (stitch-cut.sh integrity gate)." || true
    echo "[stitch] ✗ render failed the integrity check — not shipping a broken cut." >&2
  elif [ "$FLAT_RENDER" = 1 ] && [ "$render_rc" -eq 137 ]; then
    # Ended from outside, not broken here (the program said why): nothing was saved, and no hardware report.
    echo "[stitch] ✗ the cut was not finished, so nothing was saved: the job's cut plan is untouched. If it happens again, type /report-a-problem." >&2
  elif [ "$FLAT_RENDER" = 1 ]; then
    # Anything else stopped before or during the render for a reason it has just printed (a clip that is
    # not there, a segment that ends before it starts, ffmpeg refusing the job). Not hardware, no report.
    echo "[stitch] ✗ could not build the cut (reason above)." >&2
  else
    # An EDL-only run used to carry on past this and save whatever EDL sat in the scratch folder, stale or empty,
    # over the job's cut. Stop before anything is saved.
    echo "[stitch] ✗ could not build the cut (reason above), so nothing was saved: the job's last cut is untouched." >&2
  fi
  exit "$render_rc"
fi

# The cut's length goes in the log; stdout carries only the path of what this run made, the base cut here (the
# saved EDL on a FLAT_RENDER=0 run, below).
if [ "$FLAT_RENDER" = 1 ]; then
  _len="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$MP4" 2>/dev/null || true)"
  echo "[stitch] wrote $MP4${_len:+ (${_len} s)}" >&2
  echo "$MP4"
fi

# ── Keep the EDL ───────────────────────────────────────────────────────────────────────────────────────
# The scratch folder does not last (macOS clears it whenever it likes), and the EDL has to: rebuilding this
# cut as separate clips on a timeline reads it later. So it goes next to words.json, which lives on the
# same raw-footage timeline. The EDL on the frame grid is the one kept, because it matches what shipped; when
# the scratch folder holds none at all, the plan the render program was handed is kept instead.
if [ -f "$WORK/edl.json" ]; then EDL="$WORK/edl.json"; else EDL="$CUTS"; fi
KEPT="$JOB_DIR/transcript/cuts.json"
mkdir -p "$JOB_DIR/transcript"
# The saved cuts.json is about to be replaced, and it may hold choices made by hand (the rough-cut skill
# lets her edit it directly). So when this run's EDL differs from it, the old one is copied into
# transcript/history/ under the time first. Nothing reads that folder; it exists so an earlier plan can be
# put back by hand. An identical re-run copies nothing.
if [ -f "$KEPT" ] && ! cmp -s "$EDL" "$KEPT"; then
  _chist="$JOB_DIR/transcript/history"
  if mkdir -p "$_chist" 2>/dev/null; then
    _cstamp="$(date -u '+%Y%m%dT%H%M%SZ' 2>/dev/null || echo unknown)"
    _cprev="$_chist/cuts.$_cstamp.json"
    [ -e "$_cprev" ] && _cprev="$_chist/cuts.$_cstamp.$$.json"   # same-second re-run keeps both
    if cp "$KEPT" "$_cprev" 2>/dev/null; then
      # Real path, never a placeholder: this line is the only way she learns the old plan survived.
      echo "[stitch] previous cut plan kept at $_cprev" >&2
    fi
  fi
fi
if cp "$EDL" "$KEPT"; then
  echo "[stitch] saved the frame-snapped EDL → $KEPT" >&2
  [ "$FLAT_RENDER" = 1 ] || echo "$KEPT"
fi

# ── Caption transcript ─────────────────────────────────────────────────────────────────────────────────
# The words already on hand from the one large-v3 pass, re-timed onto the edited timeline. The caption
# presets and graphics-plan read this file, so nothing downstream ever transcribes the footage again.
#
# Never a dead end, and never a quiet one: captions and the creative plan have nothing to read without this
# file, so the stitch always ends with either the transcript or one plain line saying why there is none.
# kept-words.py skips a span, word or word-fix table it cannot read and says so; if it still stops, its
# --plain route (every word inside a kept span, moved onto the cut the same way, no word fixes) writes it.
# Only words.json itself being missing or unreadable leaves no transcript. When it is unreadable, a
# transcript this stitch made for an earlier cut is moved aside, because its words would sit at the wrong
# times on this one. When there is no words.json at all, a transcript already there came from somewhere
# else (a job made another way), so it is left where it is and only named.
CAPTIONS="$OUT/${JOB_NAME}.transcript.json"
_words="$(words_json)"
_no_captions_why=""
if [ ! -f "$_words" ]; then
  _no_captions_why="there are no word timings for this job yet (transcript/words.json)"
  [ -f "$CAPTIONS" ] && _no_captions_why="$_no_captions_why, and the caption transcript already in outputs/ was not made from this cut"
elif python3 "$HERE/kept-words.py" "$_words" "$EDL" "$CAPTIONS" >&2 && [ -s "$CAPTIONS" ]; then
  echo "[stitch] built the caption transcript → $CAPTIONS" >&2
elif python3 "$HERE/kept-words.py" --plain "$_words" "$EDL" "$CAPTIONS" >&2 && [ -s "$CAPTIONS" ]; then
  echo "[stitch] built the caption transcript the simple way (every word inside a kept span, no word fixes) → $CAPTIONS" >&2
  note_fallback kept-words "the full caption transcript stopped for $JOB_NAME; wrote it the simple way (words inside the kept spans, no word fixes)"
else
  _no_captions_why="the word timings or the cut could not be read (reason above)"
  note_fallback kept-words "no caption transcript for $JOB_NAME: $_no_captions_why"
  if [ -f "$CAPTIONS" ] && mv -f "$CAPTIONS" "${CAPTIONS%.json}.earlier-cut.json" 2>/dev/null; then
    echo "[stitch] the caption transcript from an earlier cut no longer lines up, so it is moved aside → ${CAPTIONS%.json}.earlier-cut.json" >&2
  fi
fi
if [ -n "$_no_captions_why" ]; then
  echo "[stitch] no caption transcript for this cut: $_no_captions_why. Captions and the creative plan need one; the rough cut makes it with its transcribe step (bash .claude/skills/rough-cut/scripts/word-timings.sh <job folder>), then stitch again." >&2
fi
unset _no_captions_why

# ── Listen back ────────────────────────────────────────────────────────────────────────────────────────
# Both checks listen to the rendered file, so a run with FLAT_RENDER=0 has nothing for them. They report
# what they hear and never hold the cut back.
if [ "$FLAT_RENDER" = 1 ]; then
  # sound-check: are the joints click-free, and how hard did the limiter have to work.
  python3 "$HERE/sound-check.py" "$JOB_DIR" >&2 || true
  # verify-cut: transcribes the rendered cut again and compares it with the words the plan kept. A stumble
  # WhisperX stamped in the wrong place shows up here as words she did not mean to keep. Read its ⚠ lines
  # before handing the cut over. VERIFY_CUT=0 skips it.
  if [ "${VERIFY_CUT:-1}" != "0" ]; then
    python3 "$HERE/verify-cut.py" "$JOB_DIR" ${VERIFY_CUT_MODEL:+--model "$VERIFY_CUT_MODEL"} >&2 || true
  fi
  # voice level: her voice at the engine's north star (-16 LUFS, true peak <= -1.5 dBTP), one measured static gain and a
  # true-peak limiter, after the checks above have listened to the master as it came out (product/voice_level.py;
  # every sound and the music bed are set against this voice). VOICE_LEVEL=0 leaves the master as it is.
  if [ "${VOICE_LEVEL:-1}" != "0" ] && [ -f "$MP4" ]; then
    python3 "$REELS_ENGINE_ROOT/product/voice_level.py" "$MP4" >&2 || true
  fi
  # Last, once nothing else rewrites the video: it is stamped with the cut it was made from (review/base-cut.json,
  # product/visual_editor.py), so Finish and check-base compare the cut itself. Without a stamp only the length could
  # be measured, and a zoom or a framing keeps the length: a buyer's export came out without his punch-in (2026-10-23).
  if [ -f "$MP4" ] && [ -f "$REELS_ENGINE_ROOT/product/visual_editor.py" ]; then
    python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import visual_editor; visual_editor._stamp_base(sys.argv[2])' \
      "$REELS_ENGINE_ROOT/product" "$JOB_DIR" >&2 || true
  fi
fi

# ── Next: the review gate (always, walk-through and autopilot alike) ───────────────────────────────────
# The step after every rough cut: "Your rough cut is done." Its script prints the clickable question to ask
# and records her pick (the visual editor or the original widget), so the order never drifts.
if [ ! -f "$JOB_DIR/review/route.json" ]; then   # only until she has picked her review (a later stitch is mid-edit)
  echo "[stitch] NEXT: the review gate → python3 product/review_gate.py $JOB_NAME (phase by phase asks it; on autopilot it says to carry on). Whenever visual_editor.py open runs, paste its EDITOR LINK: line into the chat word for word." >&2
fi
