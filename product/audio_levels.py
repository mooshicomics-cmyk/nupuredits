#!/usr/bin/env python3
"""audio_levels.py — the ONE place that decides how loud a sound effect or a music bed is.

SHARED BASE MODULE. Every format calls this (baked well-done, CapCut Clean/Super Yap, Voiceover). A level
fix lands here once and every lane gets it in the same change; never hand-tune a number in a format.

## The rule: never express a cue's level as a bare offset or a bare multiplier

A number like `gain_db: -12` or `volume: 1.0` says nothing about how loud a cue will actually SOUND, because
it is applied to whatever level that particular file happens to have. The bundled SFX span about 20 dB of
intrinsic level:

    pop.mp3              -17.4 dBFS rms  (loudest)
    keyboard_typing.mp3  -37.6 dBFS rms  (quietest)

So one shared number makes `pop` land 20 dB hotter than `keyboard_typing`. At the old `-12` default, seven
of the nine bundled SFX landed INAUDIBLE and two were marginal. Zero landed right.

Worse, it fails SILENTLY. Nothing errors; the reel simply ships with no sound design. On the Hands-Off lane
there is no human review step at all, so nobody would ever catch it. (Found by ear on a finished reel whose
cues measured +0.04 dB against the mix and had shipped as "done". Locked.)

## What this module does instead

MEASURE the cue, MEASURE the programme, and place the cue a fixed distance under it. Then every cue lands
at the same perceived level whichever file was chosen.

  * SFX are transients -> matched by PEAK, `programme_peak + SFX_DUCK_DB`.
  * A music bed is continuous -> matched by MEAN, `programme_mean + BED_DUCK_DB`.
  * With no programme reference available, cues still normalise to a canonical target, which on its own
    removes the 20 dB spread.

An explicit level from the caller always still wins, for deliberate hand-tuning.

ALWAYS print `report(...)` from a build. A level you have not seen printed is a level nobody has checked,
and that is exactly how this shipped broken the first time.

Levels here are MEASURED, never heard. The creator is the ear on whether a cue finally sits right.
"""
import os, re, subprocess

# THE NORTH STAR: her voice is the anchor and everything is set relative to it (2026-10-16 audit).
#   voice  -16 LUFS integrated, true peak <= -1.5 dBTP: AES TD1008 (speech-led streaming -18 +-2 LU, <= -1 dBTP),
#          under the -14 LUFS that Spotify/YouTube turn louder content down to, inside her own CapCut exports
#          (-14 to -19 LUFS). The rough cut lands there with one measured static gain + a true-peak limiter
#          (product/voice_level.py), never loudness normalisation.
#   sfx    its loudest moment (EBU momentary, 400 ms) 6 LU under her voice, never peaking above -6 dBFS.
#   bed    15 LU under her voice (integrated), unless she taught her own level.
VOICE_TARGET_LUFS = -16.0
TRUE_PEAK_CEILING_DBTP = -1.5
SFX_UNDER_VOICE_LU = -6.0
SFX_PEAK_CAP_DBFS = -6.0
BED_UNDER_VOICE_LU = -15.0
CUTAWAY_UNDER_VOICE_LU = -10.0   # a b-roll cutaway's own sound (she turned it on): heard, but her voice leads
CUTAWAY_BOOST_MAX_DB = 6.0       # a quiet clip is lifted at most this much, so room hiss is never pumped up to be heard
SFX_DUCK_DB = -6.0          # (fallback, when loudness can't be read) an SFX peak sits this far under the programme peak
BED_DUCK_DB = -10.0         # a music bed's mean sits this far under the programme mean (heard, and under her voice;
                            # -15 sat so low it was felt more than heard). Her own taught level wins: bed_duck_db()
SFX_TARGET_PEAK_DBFS = -7.0 # canonical SFX peak when no programme reference is available
BED_TARGET_MEAN_DBFS = -30.0
GAIN_MIN_DB, GAIN_MAX_DB = -40.0, 12.0   # a computed gain outside this means a bad measurement, not intent


def _volumedetect(path, field, trim=None):
    if not path or not os.path.exists(path):
        return None
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-map", "0:a:0?"]
    if trim:
        cmd += ["-t", f"{float(trim):.3f}"]
    cmd += ["-af", "volumedetect", "-f", "null", os.devnull]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stderr
    except Exception:
        return None
    m = re.search(rf"{field}:\s*(-?[\d.]+) dB", out)
    return float(m.group(1)) if m else None


def peak_dbfs(path, trim=None):
    """True peak in dBFS — the honest measure for a short transient (an SFX cue)."""
    return _volumedetect(path, "max_volume", trim)


def mean_dbfs(path, trim=None):
    """Average level in dBFS — the honest measure for a continuous signal (a music bed, a voice track)."""
    return _volumedetect(path, "mean_volume", trim)


def loudness_lufs(path):
    """Integrated loudness (EBU R128, gated): how loud speech sounds, with its silences left out, so a long quiet
    stretch can't make a voice read 18 dB quieter than it plays."""
    if not path or not os.path.exists(path):
        return None
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0?", "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", os.devnull]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300).stderr
    except Exception:
        return None
    m = re.findall(r"\bI:\s*(-?[\d.]+) LUFS", out)
    return float(m[-1]) if m else None


def momentary_max_lufs(path, trim=None):
    """The loudest 400 ms of a file (EBU R128 momentary loudness), the honest loudness of a short sound."""
    if not path or not os.path.exists(path):
        return None
    cut = f"atrim=0:{float(trim):.3f}," if trim else ""     # trimmed BEFORE the pad (an output -t would cut the pad off)
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-v", "verbose", "-i", path, "-map", "0:a:0?",   # verbose: the per-moment log
           "-vn", "-af", f"{cut}apad=pad_dur=0.5,ebur128=framelog=verbose", "-f", "null", os.devnull]   # a short sound still reads
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stderr
    except Exception:
        return None
    ms = [float(m) for m in re.findall(r"\bM:\s*(-?[\d.]+)", out) if float(m) > -70]
    return max(ms) if ms else None


def bed_duck_db():
    """How far under her voice a music bed sits: the level she taught (Louder / Quieter on a reel, remembered as
    `sound.music_under_voice_db`), else the engine's BED_DUCK_DB. Every build and the preview read this one place."""
    try:
        import learned
        v, rec = learned.value("sound.music_under_voice_db", None)
        if rec is not None and v is not None:
            return -abs(float(v))
    except Exception:
        pass
    return BED_DUCK_DB


def _clamp(db):
    return max(GAIN_MIN_DB, min(GAIN_MAX_DB, db))


def sfx_gain_db(sfx_path, programme_peak_db=None, duck_db=SFX_DUCK_DB, trim=None):
    """dB of gain to apply to an SFX file so its peak lands duck_db under the programme peak.
    With no programme reference, normalises to SFX_TARGET_PEAK_DBFS, which alone kills the 20 dB spread."""
    src = peak_dbfs(sfx_path, trim)
    if src is None:
        return 0.0
    target = (programme_peak_db + duck_db) if programme_peak_db is not None else SFX_TARGET_PEAK_DBFS
    return _clamp(target - src)


def bed_gain_db(bed_path, programme_mean_db=None, duck_db=BED_DUCK_DB):
    """dB of gain for a music bed so its mean sits duck_db under the programme mean."""
    src = mean_dbfs(bed_path)
    if src is None:
        return 0.0
    target = (programme_mean_db + duck_db) if programme_mean_db is not None else BED_TARGET_MEAN_DBFS
    return _clamp(target - src)


def sfx_landing(sfx_path, programme_peak_db=None, duck_db=SFX_DUCK_DB, trim=None):
    """(gain_db, lands_dbfs, clamped) for a cue. `clamped` = the file is too quiet to reach target within
    GAIN_MAX_DB, so it lands short. That is deliberate — boosting a very quiet file to target would drag its
    noise floor up with it — but it must be REPORTED, never silently accepted."""
    src = peak_dbfs(sfx_path, trim)
    if src is None:
        return 0.0, None, False
    target = (programme_peak_db + duck_db) if programme_peak_db is not None else SFX_TARGET_PEAK_DBFS
    want = target - src
    gain = _clamp(want)
    return gain, src + gain, abs(want - gain) > 0.05


_LUFS = {}


def _voice_lufs(path):
    if not path or not os.path.exists(path):
        return None
    st = os.stat(path)
    k = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if k not in _LUFS:
        _LUFS[k] = loudness_lufs(path)
    return _LUFS[k]


def sfx_gain_for(sfx_path, programme_path=None, trim=None, duck_db=SFX_DUCK_DB):
    """THE rule every route uses for a sound effect (the north star): its loudest moment SFX_UNDER_VOICE_LU under
    her voice's integrated loudness, never peaking above SFX_PEAK_CAP_DBFS. A plan's own duck (sfx_duck_db) moves it
    dB for dB. Falls back to the old peak rule only when loudness can't be read."""
    pk = peak_dbfs(sfx_path, trim)
    if pk is None:
        return 0.0
    vi, mm = _voice_lufs(programme_path), momentary_max_lufs(sfx_path, trim)
    if vi is not None and mm is not None:
        g = vi + SFX_UNDER_VOICE_LU + (float(duck_db) - SFX_DUCK_DB) - mm
        return round(_clamp(min(g, SFX_PEAK_CAP_DBFS - pk)), 1)
    return round(sfx_gain_db(sfx_path, peak_dbfs(programme_path) if programme_path else None, duck_db, trim), 1)


def sfx_volume_for(sfx_path, programme_path=None, trim=None, duck_db=SFX_DUCK_DB):
    return to_linear(sfx_gain_for(sfx_path, programme_path, trim, duck_db))


def bed_gain_for(bed_path, programme_path=None, duck_db=None):
    """THE rule every route uses for a music bed: BED_UNDER_VOICE_LU under her voice's integrated loudness, unless she
    taught her own level or the plan sets one (then the older under-the-average rule those were set on)."""
    if duck_db is None and bed_duck_db() == BED_DUCK_DB:
        vi, bl = _voice_lufs(programme_path), _voice_lufs(bed_path)
        if vi is not None and bl is not None:
            return round(_clamp(vi + BED_UNDER_VOICE_LU - bl), 1)
    return bed_gain_db(bed_path, mean_dbfs(programme_path) if programme_path else None,
                       float(duck_db) if duck_db is not None else bed_duck_db())


def cutaway_gain_for(clip_path, programme_path=None):
    """THE rule for a b-roll clip's own sound under her voice: its integrated loudness CUTAWAY_UNDER_VOICE_LU under
    her voice's, lifted at most CUTAWAY_BOOST_MAX_DB, never peaking above SFX_PEAK_CAP_DBFS. Natural sound runs the
    whole cutaway, so it's measured like a voice, not by its loudest moment like a sound effect."""
    pk = peak_dbfs(clip_path)
    if pk is None:
        return 0.0
    vi, cl = _voice_lufs(programme_path), loudness_lufs(clip_path)
    if vi is None or cl is None:
        return round(min(0.0, SFX_PEAK_CAP_DBFS - pk), 1)
    return round(_clamp(min(vi + CUTAWAY_UNDER_VOICE_LU - cl, CUTAWAY_BOOST_MAX_DB, SFX_PEAK_CAP_DBFS - pk)), 1)


def to_linear(gain_db, lo=0.02, hi=4.0):
    """dB -> the linear multiplier CapCut / VectCutAPI want in a segment's `volume` field."""
    return round(max(lo, min(hi, 10 ** (float(gain_db) / 20.0))), 4)


def sfx_volume(sfx_path, programme_peak_db=None, duck_db=SFX_DUCK_DB, trim=None):
    """Linear volume multiplier for an SFX in an editor timeline (CapCut lanes)."""
    return to_linear(sfx_gain_db(sfx_path, programme_peak_db, duck_db, trim))


def bed_volume(bed_path, programme_mean_db=None, duck_db=BED_DUCK_DB):
    """Linear volume multiplier for a music bed in an editor timeline."""
    return to_linear(bed_gain_db(bed_path, programme_mean_db, duck_db))


def report(rows, programme_peak_db=None, programme_mean_db=None, prefix="[levels]"):
    """Print what was computed. Never ship a level nobody has seen — silent failure is the whole bug."""
    if programme_peak_db is not None or programme_mean_db is not None:
        bits = []
        if programme_peak_db is not None:
            bits.append(f"peak {programme_peak_db:.1f} dBFS")
        if programme_mean_db is not None:
            bits.append(f"mean {programme_mean_db:.1f} dBFS")
        print(f"{prefix} programme {' · '.join(bits)}")
    for r in rows:
        name = os.path.basename(str(r.get("file", "?")))
        gain = r.get("gain_db", 0.0)
        lands = r.get("lands_dbfs")
        how = r.get("how", "auto")
        tail = f" -> {lands:6.1f} dBFS" if lands is not None else ""
        warn = "  ⚠ too quiet to reach target (boosting further would raise its noise floor)" if r.get("clamped") else ""
        print(f"{prefix}   {name:24} gain {gain:+6.1f} dB ({how}){tail}{warn}")
