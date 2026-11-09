#!/usr/bin/env python3
"""build-reel-mp4.py — the FINISH step of the well-done (Route A) lane: bake the base cut + the
transparent type overlay + zoom punch-ins + matched SFX into ONE deliverable MP4.

  JOB=my-reel STYLE_PACK=Editorial OVERLAY=renders/xxx.mov python3 product/build-reel-mp4.py

Optional, only when the creator asks for a look by name (never a default):
  GRADE=cinematic|warm|cool|film|mono   grades the FOOTAGE only; the type overlay stays untouched

Everything is declared in projects/<JOB>/caption-plan.json so the build is reproducible from the
written spec (nothing lives only in a shell command):

  "punch":  {"scale": 1.10, "windows": [[4.33, 6.10], ...]}   zoom punch-INs (scale UP only, hard cuts)
            optional "anchors": [[0.62, 0.41], ...]           one face anchor per window, 0..1 of the
            frame. Left out, the anchors are measured from the footage (face-anchors.json); a punch
            that cannot be measured stays centred and says so. NEVER silently centre-anchor a zoom:
            an off-centre creator drifts toward the edge on every push-in.
  "sfx":    [{"file": "woosh.mp3", "at": 50.78, "gain_db": -12, "trim": 0.39}, ...]

Punch-ins are done as an overlay of a pre-scaled copy gated by `enable`, NOT zoompan: hard cuts are
what a punch-in IS, and this keeps one clean scale per window instead of resampling every frame.

SFX are summed at unity (normalize=0) and the whole mix goes through ONE limiter, so a cue can never
push the already-mastered voice track over 0 dBFS. Everything is trimmed to its motion length by the
caller (sound voices the movement: it starts and stops with the animation).
"""
import shlex
import os, platform, sys, json, shutil, subprocess
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_encoder import pick_encoder, software_encoder, is_hardware, graph_args, remove_graph   # sibling module in product/ — shared across every ffmpeg render
from video_grade import grade_filter     # optional footage grade (GRADE=<look>); never applied unasked
# SHARED base module — the ONE place a cue's or a bed's level is decided, for every format.
from audio_levels import (peak_dbfs, mean_dbfs, sfx_gain_db, sfx_landing, bed_gain_db, report,
                          SFX_DUCK_DB, BED_DUCK_DB, bed_duck_db)
import capcut_sfx   # SHARED cue palette: buyer's own sfx/ -> bundled Pixabay library fallback


def resolve_sfx(ref, sfx_dir):
    """A cue name or path -> a real file. Falls back to the bundled library so a cue never comes up empty."""
    if os.path.isabs(ref):
        return ref if os.path.exists(ref) else None
    direct = os.path.join(sfx_dir, ref)
    if os.path.exists(direct):
        return direct
    return capcut_sfx.palette().get(os.path.splitext(os.path.basename(ref))[0])

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# JOB_DIR: the job folder itself, for a job that does not sit directly under projects/ (a pull-reels clip at
# projects/<parent>/clips/<name>/); its files are still named after the folder. Unset: projects/<JOB>/ as before.
_JD = os.environ.get("JOB_DIR")
JOB = os.environ.get("JOB") or (os.path.basename(os.path.normpath(_JD)) if _JD else None) or sys.exit("set JOB=<reel folder under projects/>")
JOB_DIR = _JD or f"{ROOT}/projects/{JOB}"
_NAME = os.path.basename(os.path.normpath(_JD)) if _JD else JOB
OVERLAY = os.environ.get("OVERLAY") or sys.exit("set OVERLAY=<transparent .mov from hyperframes render>")
BASE = os.environ.get("BASE", f"{JOB_DIR}/outputs/{_NAME}.mp4")
OUT = os.environ.get("OUT", f"{JOB_DIR}/outputs/{_NAME}.final.mp4")
SFX_DIR = os.environ.get("SFX_DIR", f"{ROOT}/product/creative-vault/sfx")
CP = json.load(open(f"{JOB_DIR}/caption-plan.json", encoding="utf-8"))

for p in (BASE, OVERLAY):
    if not os.path.exists(p):
        sys.exit(f"missing input: {p}")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame as _frame; _frame.adopt()   # a wide job bakes on the wide frame
import safe_zones as _sz_frame
W, H = _sz_frame.W, _sz_frame.H

# The base is normalized to W×H with a PURE scale below (see the [base0] step). That is right only
# when the base is already ~9:16. Best-effort probe: if it is some other aspect (e.g. 16:9), the
# scale silently DISTORTS — announce it rather than ship a stretched frame. (A real 9:16 reframe
# belongs in Graphics, not here.)
try:
    import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from probe import display_dims as _display_dims      # rotation-aware: a vertical phone clip reads 1080x1920 here
    _bw, _bh = _display_dims(BASE)
    if _bh and abs((_bw / _bh) - (W / H)) > 0.02:
        print(f"[mp4] WARNING: base is {_bw}x{_bh} (not ~9:16) — scaling to {W}x{H} will DISTORT it; "
              f"a real 9:16 reframe belongs in Graphics, not this step.", file=sys.stderr)
except (ValueError, ZeroDivisionError):
    pass

def resolve_punch_anchors(wins, punch, base, root, job):
    """One (x, y) face anchor per punch window, normalised 0..1 of the frame. Tried in order:
    the plan's own "anchors", a face-anchors.json already measured for this job, then a live
    measure with workflows/head-framing.py. Anything unmeasurable falls back to frame centre and
    SAYS SO — a silent centre anchor is the bug this exists to end."""
    n = len(wins)
    plan = punch.get("anchors")
    if plan and len(plan) == n:
        print(f"[mp4] punch anchors: {n} from the plan")
        return [(float(r[0]), float(r[1]), float(r[2]) if len(r) > 2 else 1.0) for r in plan]

    path = os.path.join(JOB_DIR, "face-anchors.json") if os.environ.get("JOB_DIR") else os.path.join(root, "projects", job, "face-anchors.json")

    def read_cached():
        """The saved anchors, but ONLY if they describe THIS set of windows. A plan's punch windows
        change on almost every iteration, so a file left over from the previous build is the normal
        case, not the rare one — and it must never be mistaken for an answer."""
        if not os.path.exists(path):
            return None
        try:
            rows = json.load(open(path, encoding="utf-8")).get("windows", [])
        except (ValueError, OSError):
            return None
        if len(rows) != n:
            print(f"[mp4] {os.path.basename(path)} describes {len(rows)} window(s), this reel has {n} "
                  f"- it is stale, re-measuring")
            return None
        srcs = {}
        for r in rows:
            srcs[r.get("source", "?")] = srcs.get(r.get("source", "?"), 0) + 1
        print(f"[mp4] punch anchors: {n} from {os.path.basename(path)} "
              f"({', '.join(f'{v} {k}' for k, v in srcs.items())})")
        return [(float(r["anchor"][0]), float(r["anchor"][1]),
                 float(r.get("confidence", 1.0))) for r in rows]

    got = read_cached()
    if got:
        return got

    # Nothing usable on disk: measure. An earlier version BROKE out here whenever the file merely
    # EXISTED, so a stale file from a build with different windows permanently pinned every punch back
    # to frame centre — silently, and for good, until someone deleted it by hand.
    ff = os.path.join(root, "workflows", "head-framing.py")
    if shutil.which("uv") and os.path.exists(ff):
        print(f"[mp4] measuring a face anchor per punch window ({n}) ...")
        try:
            subprocess.run(["uv", "run", ff, base, "--windows",
                            json.dumps([[a, b] for a, b in wins]), "--out", path],
                           check=True, timeout=600)
            got = read_cached()
            if got:
                return got
        except (subprocess.SubprocessError, OSError) as e:
            print(f"[mp4] face measure unavailable ({e}) - punches stay centred")

    print(f"[mp4] WARNING: no face anchors - all {n} punches stay CENTRED on the frame. "
          f"If the creator does not sit centre, they will drift toward the edge. "
          f"Fix: uv run workflows/head-framing.py <base> --windows @caption-plan.json --out {path}")
    return [(0.5, 0.5, 0.0)] * n


punch = CP.get("punch") or {}
wins = [(float(a), float(b)) for a, b in punch.get("windows", [])]
z = float(punch.get("scale", 1.10))
# Her Sound edits from the visual editor (review/sound.json: a cue switched off, a sound swapped, the music bed's
# song / on-off / level) applied over the plan. No sound.json: the plan's sfx and music come back unchanged.
import sound_plan
sfx, CP["music"] = sound_plan.for_build(JOB_DIR, CP.get("sfx", []), CP.get("music"))

inputs = ["-i", BASE, "-i", OVERLAY]
kept_sfx = []
for s in sfx:
    f = resolve_sfx(s["file"], SFX_DIR)
    if not f:
        print(f"[mp4] skipping cue with no sound file: {s['file']}")
        continue
    if os.path.basename(f) != os.path.basename(str(s["file"])):
        print(f"[mp4] {s['file']} not present — using bundled {os.path.basename(f)}")
    s["file"] = f
    kept_sfx.append(s); inputs += ["-i", f]

sfx = kept_sfx          # only cues whose file actually exists reach the mix
fc = []
# Normalize the base cut to exactly W×H ONCE, before anything downstream reads it. stitch-cut.sh
# PRESERVES the raw footage resolution (e.g. 1440x2560), a different pixel count than the
# 1080x1920 the punch-in crop/scale math and the final overlay=0:0 both assume — the mismatch
# ghosts a half-canvas copy into every punch window. This is a PURE scale: correct when the base
# is already 9:16 (vertical phone footage is), NOT a reframe. A genuinely different aspect ratio
# (e.g. 16:9) needs the real 9:16-reframe step in Graphics, which this does not attempt.
# OPTIONAL grade (GRADE=cinematic|warm|cool|film|mono in the env): footage only, applied here on the base
# before punch-ins and before the graphics overlay, so the pack's colors on the graphics never shift.
# Nothing happens unless it was asked for (locked: optional and available, not built in).
GRADE = os.environ.get("GRADE", "")
try:
    _grade = grade_filter(GRADE)
except ValueError as e:
    sys.exit(f"  ✗ {e}")
fc.append(f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1{(',' + _grade) if _grade else ''}[base0]")
BASE_LABEL = "[base0]"
if wins:
    # ANCHOR EACH PUNCH ON THE FACE IN THAT SHOT (never the middle of the room). A punch that crops
    # the centre enlarges whatever is at frame centre, so a creator who does not sit centre gets
    # pushed further toward the edge on every push-in — reported from the first PC test reel as "the
    # zooms go off to the side". Crop a 1/z-sized window positioned so her face keeps its place, then
    # scale that window back up: the face at fx lands at fx*cw inside a cw-wide crop, i.e. fx of the
    # output, unmoved. fx=fy=0.5 reproduces the old centre punch exactly.
    #
    # CROP FIRST, THEN SCALE (and one STATIC crop per distinct anchor). A single time-varying crop
    # would be one pass, but crop's `eval` option does not exist on every ffmpeg a buyer has (removed
    # in 8.x; on older builds it defaults to evaluating x/y ONCE), and there it would silently fall
    # back to a centre punch — the exact silent failure this fix exists to end. Static crops behave
    # identically on every build. Windows are grouped by anchor, so a reel whose face barely moves
    # still costs one pass, and cropping before scaling makes each pass cheaper than the old upscale.
    anchors = resolve_punch_anchors(wins, punch, BASE, ROOT, JOB)
    # Derive ch FROM cw, never round the two independently: rounding each to an even number on its own
    # leaves the crop a slightly different shape than the output and the punch stretches the picture
    # (measured up to 0.15% — small, and a distortion the old scale-then-crop path did not have).
    cw = int(round(W / z)) // 2 * 2
    ch = int(round(cw * H / W)) // 2 * 2
    MAX_GROUPS = 4
    # Damp each anchor by how much the measurement is worth trusting (how still she is inside that
    # window). A stale anchor on a moving subject frames her worse than no correction, so an
    # unmeasurable or restless window fades back to the plain centre punch instead of guessing.
    eff = [(0.5 + c * (fx - 0.5), 0.5 + c * (fy - 0.5)) for fx, fy, c in anchors]
    for q in (2, 1, 0):                     # coarsen until the pass count is sane
        groups = {}
        for (a, b), (fx, fy) in zip(wins, eff):
            key = (round(fx, q), round(fy, q)) if q else (0.5, 0.5)
            groups.setdefault(key, []).append((a, b))
        if len(groups) <= MAX_GROUPS:
            break
    labels = [f"[zsrc{i}]" for i in range(len(groups))]
    fc.append(f"{BASE_LABEL}split={len(groups) + 1}[base]{''.join(labels)}")
    prev = "[base]"
    for i, ((fx, fy), gw) in enumerate(groups.items()):
        cx = max(0, min(W - cw, int(round(fx * (W - cw)))))
        cy = max(0, min(H - ch, int(round(fy * (H - ch)))))
        gate = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in gw)
        fc.append(f"[zsrc{i}]crop={cw}:{ch}:{cx}:{cy},scale={W}:{H}:flags=lanczos,setsar=1[punched{i}]")
        fc.append(f"{prev}[punched{i}]overlay=0:0:eof_action=pass:enable='{gate}'[pv{i}]")
        prev = f"[pv{i}]"
    vlast = prev
    print(f"[mp4] punch anchors: {len(groups)} distinct "
          f"({', '.join(f'({x:.2f},{y:.2f})x{len(v)}' for (x, y), v in groups.items())})")
else:
    vlast = BASE_LABEL
fc.append(f"{vlast}[1:v]overlay=0:0:format=auto:eof_action=pass[vtype]")   # [vout] comes after her logo, below

music = CP.get("music") or {}
if music.get("file"):
    mf = music["file"] if os.path.isabs(music["file"]) else f"{JOB_DIR}/audio/{music['file']}"
    if not os.path.exists(mf):
        print(f"[mp4] no music bed at {mf} — finishing without one")
        music = {}
    else:
        inputs += (["-stream_loop", "-1"] if music.get("loop", True) else []) + ["-i", mf]

# SFX AUTO-LEVEL (the fix for silently-inaudible cues). A fixed gain_db is meaningless on its own: the
# bundled SFX span ~20 dB of intrinsic level, so one offset makes `pop` audible and `keyboard_typing`
# 20 dB quieter than it. Instead, MEASURE each cue and place its peak a fixed distance under the
# programme's peak, so every cue lands at the same perceived level whichever file is chosen.
# An explicit "gain_db" on a cue still wins, for deliberate hand-tuning.
SFX_DUCK = float(CP.get("sfx_duck_db", SFX_DUCK_DB))
_prog_peak = peak_dbfs(BASE)
_rows = []
for s_ in sfx:
    f_ = s_["file"]
    if "gain_db" in s_:
        s_["_gain"], how = float(s_["gain_db"]), "manual"
        _lands, _cl = (peak_dbfs(f_, s_.get("trim")) or 0) + s_["_gain"], False
    else:
        import audio_levels as _al                              # the north star: under her voice, by loudness
        s_["_gain"] = _al.sfx_gain_for(f_, BASE, s_.get("trim"), SFX_DUCK); how = "auto"
        _lands, _cl = (peak_dbfs(f_, s_.get("trim")) or 0) + s_["_gain"], False
    _rows.append({"file": f_, "gain_db": s_["_gain"], "how": how, "lands_dbfs": _lands, "clamped": _cl})
report(_rows, programme_peak_db=_prog_peak, prefix="[mp4]")

alabels = ["[0:a]"]
for i, s in enumerate(sfx):
    idx = 2 + i
    chain = []
    if s.get("trim"):
        t = float(s["trim"])
        chain.append(f"atrim=0:{t:.3f}")
        chain.append(f"afade=t=out:st={max(0, t - 0.12):.3f}:d=0.12")
    chain.append("aresample=48000")
    chain.append("aformat=sample_fmts=fltp:channel_layouts=stereo")
    chain.append(f"volume={float(s['_gain']):.1f}dB")
    ms = int(round(float(s["at"]) * 1000))
    chain.append(f"adelay={ms}|{ms}")
    fc.append(f"[{idx}:a]{','.join(chain)}[s{i}]")
    alabels.append(f"[s{i}]")
if music.get("file"):
    # MUSIC BED: enters on a beat (not at 0 — a confessional opens dry), flat under the voice, no ducking.
    midx = 2 + len(sfx)
    at = float(music.get("at", 0)); fi = float(music.get("fade_in", 0.0)); fo = float(music.get("fade_out", 2.5))
    total = float(CP.get("duration", 0)) or 0
    if not total:
        # The plan has no "duration" (it is optional, and real plans leave it out). The bed was then trimmed
        # to 0.1s, which is no bed at all, and nothing said so. The reel is as long as the base cut, so
        # measure that, with the same ffprobe call the finish below makes on the output.
        _bl = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", BASE], capture_output=True, text=True).stdout.strip()
        try:
            total = float(_bl)
        except ValueError:
            total = 0
    mlen = max(0.1, total - at)
    # Same auto-level as the SFX, but against the programme MEAN: a bed is continuous, so mean is the
    # honest measure. A blind default here fails exactly like the SFX did (a -24 offset on a -19 dBFS
    # track lands at -43 dBFS, i.e. inaudible). Explicit gain_db still wins.
    if "gain_db" in music:
        _mgain, _mhow = float(music["gain_db"]), "manual"
    else:
        import audio_levels as _al
        _mgain = _al.bed_gain_for(mf, BASE, CP.get("music_duck_db"))
        _mhow = "auto"
    print(f"[mp4] music bed {os.path.basename(mf)} in at {at:.2f}s  gain {_mgain:+.1f} dB ({_mhow})")
    mch = [f"atrim=0:{mlen:.3f}", "asetpts=PTS-STARTPTS",
           "aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo",
           f"afade=t=in:st=0:d={fi:.2f}", f"afade=t=out:st={max(0, mlen - fo):.3f}:d={fo:.2f}",
           f"volume={_mgain:.1f}dB"]
    ms = int(round(at * 1000))
    if ms: mch.append(f"adelay={ms}|{ms}")
    fc.append(f"[{midx}:a]{','.join(mch)}[bed]")
    alabels.append("[bed]")

fc.append(f"{''.join(alabels)}amix=inputs={len(alabels)}:duration=first:normalize=0,"
          f"aresample=192000,alimiter=level_in=1:level_out=1:limit=0.8414:attack=5:release=50:level=disabled,"   # true peak
          f"aresample=48000[aout]")                           # <= -1.5 dBTP after the encode (the north star, audio_levels)

def _venc():
    """Video encoder args — see product/video_encoder.py (shared across every ffmpeg render in
    the engine: Mac videotoolbox, NVENC when a real NVIDIA GPU + nvenc-capable ffmpeg are both
    confirmed present, else libx264). CRF 17 here for the well-done finish: visually at or above
    the 16 Mbps hardware-encoder target this file has always used."""
    return pick_encoder(vbr="16M", crf=17, preset="veryfast")


venc = _venc()
# HER LOGO, only when she turned it on for this pack (product/watermark.py): laid last, over everything, in the
# same measured corner the CapCut draft uses. Added after every other input so no input index above moves.
try:
    import watermark as _wm
    _wspec = _wm.get(os.environ.get("STYLE_PACK"))
except Exception:
    _wspec = None
if _wspec:
    _wpng = _wm.frame_png(_wspec, os.path.join(JOB_DIR, "outputs", ".watermark-frame.png"))
    _widx = inputs.count("-i")
    inputs += ["-loop", "1", "-i", _wpng]
    fc.append(f"[vtype][{_widx}:v]overlay=0:0:shortest=1[vout]")
    print(f"[mp4] your logo: {_wspec['corner']}, the whole reel")
else:
    fc.append("[vtype]null[vout]")
# A long graph (one chain per punch-in and per sound) goes to ffmpeg in a file: inline, a sound-heavy reel ran a
# Windows command line past its 32,767-character limit (WinError 206). Beside the reel, hidden, gone after the bake.
GRAPH_FILE = os.path.join(os.path.dirname(os.path.abspath(OUT)), "." + os.path.basename(OUT) + ".graph.txt")
cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *inputs,
       *graph_args(";".join(fc), GRAPH_FILE), "-map", "[vout]", "-map", "[aout]",
       # No chapters from any input: ffmpeg copies the first input's that has one, and a song's own chapter (an
       # Epidemic mp3 carries one) outlasting the reel made players show a longer reel with an empty stretch.
       "-map_chapters", "-1",
       *venc,
       "-pix_fmt", "yuv420p", "-r", "30",
       "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
       "-video_track_timescale", "90000", "-movflags", "+faststart", OUT]
print(f"[mp4] base={os.path.basename(BASE)} overlay={os.path.basename(OVERLAY)} "
      f"punches={len(wins)}@{z}x sfx={len(sfx)} grade={GRADE.strip().lower() or 'none'}")
# The bake prints nothing while it works (-loglevel error), so a record of it is the only way to know
# afterwards how long it ran, or that it was stopped before it finished (product/render_log.py).
# Before it starts: one line on about how long it takes on this computer, and that it is free
# (render_log.estimate_line, from this computer's own past bakes). The frame count goes into the record too,
# so this bake's real time makes the next estimate.
_bake_frames = None
try:
    _bl = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", BASE], capture_output=True, text=True).stdout.strip()
    _bake_frames = int(float(_bl) * 30 + 0.999)          # the bake writes -r 30
except (OSError, ValueError):
    pass
try:
    from render_log import Trail, estimate_line
    if _bake_frames:
        print(f"[mp4] {estimate_line(_bake_frames, step='final bake', what='Putting your reel together')}",
              flush=True)
    _trail = Trail("final bake", OUT, reports_progress=False, frames=_bake_frames)
except Exception:   # noqa: BLE001 — evidence only, never a reason to fail the bake
    _trail = None


# A bake only counts when it WROTE the file. A hardware encoder that fails on this machine (an NVIDIA driver
# older than the buyer's ffmpeg, GPU contention) can exit non-zero having written a 0-byte file, or exit 0
# over an empty one, and that empty file used to stay at the reel's path. So: check what was written, and on
# a hardware encoder retry once on libx264 before giving up. A file untouched since before the bake is a
# previous bake, never this one, and is never deleted.
def _stamp(p):
    try:
        st = os.stat(p)
        return (st.st_ino, st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _written(p):
    return _stamp(p) not in (None, before) and os.path.getsize(p) >= 1024


def _discard_partial(p):
    if _stamp(p) not in (None, before):
        try: os.remove(p)
        except OSError: pass


before = _stamp(OUT)
try:
    r = subprocess.run(cmd)
    if (r.returncode != 0 or not _written(OUT)) and is_hardware(venc):
        print(f"[mp4] the hardware encoder {'exited ' + str(r.returncode) if r.returncode else 'wrote no video'}, "
              "so the bake is running again on the software encoder (same look, slower)")
        _discard_partial(OUT)
        i = cmd.index("-c:v")
        cmd = cmd[:i] + software_encoder(crf=17, preset="veryfast") + cmd[i + len(venc):]
        r = subprocess.run(cmd)
except KeyboardInterrupt:
    if _trail:
        _trail.finish("stopped")
    raise
finally:
    remove_graph(GRAPH_FILE)
ok = r.returncode == 0 and _written(OUT)
if _trail:
    _trail.finish("ok" if ok else f"failed (exit {r.returncode})")
if not ok:
    _discard_partial(OUT)
    print("[mp4] ✗ the bake did not write the reel (any ffmpeg error is above), so nothing was left at "
          f"{os.path.relpath(OUT, ROOT) if os.path.isabs(OUT) else OUT}", file=sys.stderr)
    # Never exit 0 here, and never hand back ffmpeg's own code raw: on Windows it is a negative error number
    # read as an unsigned 32-bit value, which Python and Git Bash do not pass through intact.
    sys.exit(r.returncode if 0 < r.returncode < 256 else 3)
# The bake is done here. A length ffprobe cannot give (empty answer, or no ffprobe) only leaves the length
# off the line; it must never turn a finished reel into a traceback.
try:
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", OUT], capture_output=True, text=True).stdout.strip()
    _len = f"  ({float(dur):.2f}s)"
except (OSError, ValueError):
    _len = ""
print(f"[mp4] wrote {OUT}{_len}")

# THE WELL-DONE DEAD END, closed. This bake is the moment after which nothing inside the reel can be
# changed — the type is rendered in, so there are no layers left to hand anyone. The first PC tester
# reached exactly this point, asked three times to move to CapCut, and lost most of a day to it, because
# nobody asked her before the door shut. So the door now asks on its way closed. Printed rather than
# prompted on purpose: Claude runs this script and Claude is who asks her, in her own words, one clean
# pick-one — and it must happen NOW, while the pieces this needs are still on disk.
# REEL_NO_HANDOFF_ASK=1: a clip baked inside a pull-reels batch; the batch reports its own results.
if os.environ.get("REEL_NO_HANDOFF_ASK") != "1":
    print("\n[mp4] ── ASK HER THIS NOW, before moving on ──")
    print("[mp4] Her reel is finished and ready to post. Ask ONE clean pick-one:")
    print("[mp4]   \"Do you want this in CapCut too, or is the finished video all you need?\"")
    # The exact command, for THIS bake: the handoff talks to the editing engine over HTTP, so it runs under uv (its
    # header brings `requests`), and it is handed the overlay this bake used, which a render can have written
    # anywhere (on its own it only looks in renders/). Followed as printed, it works.
    _ov = os.path.relpath(OVERLAY, ROOT) if os.path.isabs(OVERLAY) else OVERLAY
    _pk = os.environ.get("STYLE_PACK")
    _handoff = f"uv run product/capcut_handoff.py {JOB} --overlay {shlex.quote(_ov)}" + (f" --pack {shlex.quote(_pk)}" if _pk else "")
    print(f"[mp4] If she wants it:   {_handoff}")
    print("[mp4]   She gets her cut on the timeline with the graphics over it and every sound cue on its own")
    print("[mp4]   clip — hers to split and zoom. The type is rendered, so it moves as a whole rather than")
    print("[mp4]   coming apart into words; if she wants every element separate, that is the MEDIUM route and")
    print("[mp4]   she should be told so, not sold this. The finished video above stays the deliverable.")
    print("[mp4] If she does not want it: say plainly that this is the last moment it can be handed over,")
    print("[mp4]   so she is choosing with her eyes open rather than finding out later.")
