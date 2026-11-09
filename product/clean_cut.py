#!/usr/bin/env python3
"""clean_cut.py — the ONE required pre-stitch gate. Runs the engine's existing acoustic cut tools in
order; it does NOT reimplement them.

Root cause it exists to kill: a CUSTOM build that bypasses `stitch-cut.sh` (cold-open / rewind / VHS / any
bespoke stitch, or resuming an old hand-authored cut) silently skips the cut-cleaning that the normal
rough-cut path gets for free — so double-takes and clipped words come straight back. There was no single
gate a custom build could call, so it got skipped by omission. This is that gate.

It chains the two existing tools:
  1. trim-restarts.py  — acoustic MFCC/DTW removal of quick restarts / duplicate takes the transcript
                         can't see (needs the WhisperX venv Python for torch)
  2. snap-to-sound.py    — snap every boundary to the word's real acoustic onset/offset (stdlib)
  3. close-pauses.py     — close every held silence over 0.7 s inside a kept piece (stdlib + ffmpeg)

Both are idempotent-safe to re-run, so calling this on an already-clean cut is a near no-op.

CLI:      python product/clean_cut.py <job>
Import:   from clean_cut import clean_cut ; segs = clean_cut(job)   # writes cuts.json in place
Any custom builder MUST call this after editing cuts.json and before stitching (CLAUDE.md rule 8).
"""
import json, os, sys, subprocess
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _venv_py(venv):
    """Interpreter inside a venv, whatever this OS named it (bin/ on mac+linux, Scripts/ on Windows).
    Checks what EXISTS rather than guessing by os.name, then falls back to the historic bin/python."""
    for _c in ("Scripts/python.exe", "bin/python", "bin/python3", "Scripts/python3.exe"):
        _p = os.path.join(venv, _c)
        if os.path.exists(_p):
            return _p
    return os.path.join(venv, "bin/python")


def _venv_home(leaf):
    """Where the transcription venv lives, including one built under an earlier cache layout.

    A prior build is found by the engine's own completion marker rather than by folder name: the leaf
    is this engine's, so anything carrying it under ~/.cache is ours. That way no past layout has to be
    written down, nobody re-downloads a finished 3-5 GB build, and a fresh install matches nothing and
    gets the current path."""
    import glob
    new = os.path.expanduser(f"~/.cache/reels-editing-engine/{leaf}")
    if os.path.isdir(new):
        return new
    cands = [d for d in glob.glob(os.path.expanduser(f"~/.cache/*/{leaf}")) if os.path.isdir(d)]
    finished = [d for d in cands if any(os.path.exists(os.path.join(d, m)) for m in (".speech-tools-ready", ".deps-ok"))]
    return finished[0] if finished else (cands[0] if cands else new)


def _seconds(cuts):
    """How long the cut in this file runs, in seconds, or None when the file cannot say."""
    try:
        with open(cuts, encoding="utf-8") as fh:
            from cut_placement import played_length          # a sped clip counts at the length it plays
            return sum(played_length(s) for s in json.load(fh)["segments"])
    except Exception:
        return None


ENG  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK   = f"{ENG}/.claude/skills/rough-cut/scripts"
VENV = _venv_py(_venv_home("whisperx-venv"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from swap import replace as swap_in   # os.replace that waits out Windows holding cuts.json open (the editor page reads it)
except ImportError:
    swap_in = os.replace
try:
    from fallbacks import note, remember, remembered
except Exception:   # a copy of the engine without the shared record still cleans; it only keeps no record
    def note(step, message): pass
    def remember(key, value=True, why=""): pass
    def remembered(key, default=None): return default
try:
    import venv_spawn   # starts the speech tools' Python the way that works here (the Store Python case)
except Exception:
    venv_spawn = None

# The same memory stitch-cut.sh keeps: this computer's speech tools can't run the restart pass, learned on a
# given build of them (see _tools_id), so neither path fails first on every reel.
PIVOT = "trim-restarts.unavailable"
EXIT_TOOLS_UNAVAILABLE = 69          # trim-restarts.py: torch, torchaudio or numpy will not load here
NATIVE_CRASH = {132, 134, 136, 138, 139, -4, -6, -7, -8, -10, -11}   # a native library died under it (128+n
                                                                      # through a shell, -n straight from Python)
ENV_WORDS = ("ModuleNotFoundError", "No module named", "ImportError", "libtorch", "DLL load failed",
             "Library not loaded")


def _media_dir(jd):
    """raw/ when intake made one, else the job folder itself: the rule stitch-cut.sh uses for MEDIA_DIR."""
    return f"{jd}/raw" if os.path.isdir(f"{jd}/raw") else jd


def _tools_id(venv_dir):
    """Which build of the speech tools sits here: the ready record word-timings.sh writes when it finishes a build,
    and when it wrote it. stitch-cut.sh's _tr_tools_id makes the same string, so a memory either one keeps holds
    for both, and a rebuild (a new record) clears it."""
    for m in (".speech-tools-ready", ".deps-ok"):
        p = os.path.join(venv_dir, m)
        if os.path.exists(p):
            try:
                return f"{m}@{int(os.path.getmtime(p))}"
            except OSError:
                return f"{m}@"
    return "none"


def _intel_mac():
    """A real Intel Mac, not an Apple-chip Mac running under Rosetta (scripts/_mac-arch.sh's test)."""
    import platform
    if platform.system() != "Darwin" or platform.machine() == "arm64":
        return False
    try:
        r = subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() != "1"
    except Exception:
        return True


def _environmental(rc, stderr):
    """Did trim-restarts fail because of this computer rather than this reel?"""
    return (rc == EXIT_TOOLS_UNAVAILABLE or rc in NATIVE_CRASH or not stderr.strip()
            or any(w in stderr for w in ENV_WORDS))

def clean_cut(job):
    jd    = job if os.path.isabs(job) else f"{ENG}/projects/{job}"   # isabs: C:\... on Windows too
    name  = os.path.basename(jd.rstrip("/"))
    cuts  = f"{jd}/transcript/cuts.json"
    words = f"{jd}/transcript/words.json"
    if not os.path.exists(cuts):
        sys.exit(f"clean_cut: no cut to clean — {cuts} does not exist. Run the rough-cut skill first (it writes "
                 f"transcript/cuts.json); pass the job slug under projects/ or an absolute job path.")
    # A late-sound clip in a job heard before intake lined such clips up: its words and this cut are on the sound's
    # clock, and every pass below (and the stitch after) cuts on the file's (a buyer, 2026-10-22). Lined up, and its
    # stored times moved with it, once, before anything here reads them. Best-effort, like every step of this gate.
    try:
        import av_sync                                 # beside this file, like cut_placement below
        av_sync.catch_up(jd, quiet=True)
    except Exception as e:
        print(f"clean_cut: the sound line-up could not run ({e}); cleaning the cut as it is", file=sys.stderr)
    notes = []
    failed = []   # steps that crashed (reported loud; the CLI exits non-zero so a pipeline cannot mistake it for clean)
    # "Her trim wins" (Bug #3): if this cut is the creator's authoritative your-turn pull-back, NEVER run the
    # restart-detector over it — it could silently remove a deliberate acoustic repeat ("no. no. I mean it.").
    # Only refine boundaries. This is the SAME marker stitch-cut.sh honors, so every path (splice, clean_cut, and a
    # standalone `python product/clean_cut.py <job>`) agrees. A fresh rough cut (transcript-cut) clears it.
    yourturn = os.path.exists(f"{jd}/transcript/.your-turn-cut")
    # 1) double-takes / quick restarts (acoustic) — needs the WhisperX venv (torch/torchaudio). Matches the stitch:
    #    when this computer can't run it (or the job has several clips) the cut is cleaned without it and says so;
    #    only a real crash on this reel counts as a failure.
    wx_dir = os.path.dirname(os.path.dirname(VENV))           # the venv folder VENV's interpreter lives in
    tools = _tools_id(wx_dir)
    _nofw = os.path.expanduser(os.environ.get("REELS_ENGINE_NOFW_VENV", _venv_home("fasterwhisper-venv")))
    skip_line = "trim-restarts: SKIPPED (this computer's speech tools can't run this pass — listen back for restarts)"
    if yourturn:
        notes.append("trim-restarts: SKIPPED (your-turn cut — her trim wins)")
    elif not os.path.exists(VENV) and os.path.exists(_venv_py(_nofw)) and _intel_mac():
        # On an Intel Mac this venv is never built (WhisperX needs a torch with no Intel build) and
        # trim-restarts genuinely cannot run there, so "venv missing" reads as a broken install when
        # it is actually a permanent, explainable limit. Name the real cause.
        notes.append("trim-restarts: SKIPPED (not available on an Intel Mac — "
                     "double-takes NOT removed, listen back for restarts)")
    elif remembered(PIVOT) == tools:
        notes.append(skip_line)   # learned on an earlier run; already in the log
    elif os.path.exists(wx_dir + ".use-faster-whisper") or (not os.path.exists(VENV)
                                                             and os.path.exists(_venv_py(_nofw))):
        why = ("this computer was moved to faster-whisper for transcribing"
               if os.path.exists(wx_dir + ".use-faster-whisper")
               else "only the faster-whisper speech tools are installed here")
        notes.append(skip_line)
        note("trim-restarts", f"the quick-restart pass needs torchaudio and {why}; cleaned without it, "
                              f"and later cuts skip it")
        remember(PIVOT, tools, why)
    elif os.path.exists(VENV):
        was = _seconds(cuts)
        # The full job path: a bare name sent the pass looking under projects/ for a job that lives elsewhere.
        # Through venv_spawn: started from the Microsoft Store Python, the venv's own launcher can stop with
        # "No Python at ..." (exit 103) before the pass even begins.
        tr_args = [f"{SK}/trim-restarts.py", jd]
        r = (venv_spawn.run(VENV, tr_args, runner=subprocess.run, step="trim-restarts", capture_output=True, text=True)
             if venv_spawn else subprocess.run([VENV, *tr_args], capture_output=True, text=True))
        if r.returncode in (130, -2, 143, -15):
            sys.exit(r.returncode if r.returncode > 0 else 128 - r.returncode)   # her Ctrl-C stays a stop
        if r.returncode != 0 and "clips, but this pass reads only the first" in r.stderr:
            notes.append("trim-restarts: SKIPPED (it reads one-clip jobs only — listen back for restarts)")
        elif r.returncode != 0 and _environmental(r.returncode, r.stderr):
            last = (r.stderr.strip().splitlines() or [f"exit {r.returncode}, no message"])[-1][:160]
            notes.append(skip_line)
            note("trim-restarts", f"the quick-restart pass could not run on this computer ({last}); "
                                  f"cleaned without it, and later cuts skip it")
            remember(PIVOT, tools, last)
        elif r.returncode != 0:
            # never report a crashed detector as "no restarts" (it used to): say it FAILED and why
            why = (r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or ["no output"])[-1][:200]
            notes.append(f"trim-restarts: ⚠ FAILED — double-takes NOT removed ({why})")
            failed.append("trim-restarts")
        else:
            # Its real run prints nothing on stdout, so this used to say "no restarts" every time, including
            # the times it cut some. What it did is read off the cut itself, before and after.
            now = _seconds(cuts)
            gone = None if was is None or now is None else was - now
            if gone is None:
                notes.append("trim-restarts: ran")
            elif gone > 0.0005:
                notes.append(f"trim-restarts: ran, removed {gone:.2f}s of restarted takes")
            else:
                notes.append("trim-restarts: ran, found no quick restarts to remove")
            # and its ⚠ lines (a kept line whose word timing is unreliable: re-listen there) are passed on
            notes.extend("trim-restarts: " + line.strip() for line in r.stderr.splitlines() if "⚠" in line)
    else:
        notes.append("trim-restarts: SKIPPED (WhisperX venv missing — double-takes NOT checked)")
    # 2) boundary onset/offset refinement (stdlib) — temp then atomic replace. Not on a your-turn cut: she set
    #    those edges by ear, frame by frame, in CapCut, and the snap would move nearly every one of them (on one
    #    pulled-back reel it moved 29 of 31, some by 0.2s). Her trim wins, edges included.
    if yourturn:
        notes.append("snap-to-sound: SKIPPED (your-turn cut — her edges are kept exactly as she set them)")
        for n in notes: sys.stderr.write("  " + n + "\n")
        clean_cut.failed = failed
        return json.load(open(cuts, encoding="utf-8"))["segments"]
    tmp = cuts + ".clean.tmp"
    # sys.executable, not "python3": on Windows "python3" can resolve to the Microsoft Store stub.
    r = subprocess.run([sys.executable, f"{SK}/snap-to-sound.py", _media_dir(jd), words, cuts, tmp],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(tmp):
        swap_in(tmp, cuts); notes.append("snap-to-sound: boundaries snapped to acoustic onset/offset")
    else:
        # The edges as authored are a working cut, only less tight: the stitch takes the same route when its own
        # snap does not finish. About this reel, not the computer, so nothing is remembered.
        why = (r.stderr.strip().splitlines() or ["no output"])[-1][:200]
        notes.append(f"snap-to-sound: did not finish, edges kept as authored ({why})")
        note("snap-to-sound", f"the boundary snap did not finish on {name} ({why}); kept the edges as authored")
        if os.path.exists(tmp): os.remove(tmp)
    # 3) dead air (stdlib + ffmpeg): no kept piece holds a held silence over 0.7 s, however the cut was written
    r = subprocess.run([sys.executable, f"{SK}/close-pauses.py", _media_dir(jd), words, cuts, tmp],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(tmp):
        swap_in(tmp, cuts); notes.append("close-pauses: " + ((r.stderr.strip().splitlines() or ["ran"])[-1]).split(";")[0].replace("[pauses] ", ""))
    else:
        why = (r.stderr.strip().splitlines() or ["no output"])[-1][:200]
        notes.append(f"close-pauses: did not finish, cut kept as it was ({why})")
        note("close-pauses", f"the dead-air pass did not finish on {name} ({why}); kept the cut as it was")
        if os.path.exists(tmp): os.remove(tmp)
    for n in notes: sys.stderr.write("  " + n + "\n")
    clean_cut.failed = failed
    return json.load(open(cuts, encoding="utf-8"))["segments"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python product/clean_cut.py <job>")
    segs = clean_cut(sys.argv[1])
    if clean_cut.failed:
        sys.exit(f"clean_cut: {len(segs)} segments, but {', '.join(clean_cut.failed)} FAILED (see above) — "
                 f"NOT clean; fix the step and re-run before stitching")
    print(f"clean_cut: {len(segs)} segments cleaned (trim-restarts → snap-to-sound → close-pauses) — safe to stitch")
