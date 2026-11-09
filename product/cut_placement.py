"""cut_placement.py — lays a cut onto a CapCut draft's main track the way the creator set it.

A cut is normally just in and out points on the raw clips. A cut pulled back out of her own CapCut timeline
(the your-turn round trip) can also carry what she set on each clip there, and the rebuild must reproduce it
exactly, not approximately:

  "speed"           the clip's playback speed (it plays (end - start) / speed long)
  "scale", "x", "y" her zoom and framing, in CapCut's own units (x/y are half-canvas, y up)
  "audio_detached"  she split the clip's sound onto its own audio clip, so the clip itself is silent

and the plan carries "audio_overlays": [{clip, start, end, target_start, volume}], the audio clips she laid
on the audio track (a split-off sound, a lead-in under the clip before). Every other cut has none of these
keys, and for it nothing changes. Shared by every Yap builder so the formats cannot drift apart.
"""
import os

US = 1_000_000


def segments_and_overlays(cuts):
    """Accept either a bare segment list or the whole plan ({"segments": [...], "audio_overlays": [...]})."""
    if isinstance(cuts, dict):
        return cuts.get("segments", []), cuts.get("audio_overlays") or []
    return list(cuts), []


EASES = ("linear", "in", "out", "inOut")


def ease_area(ease, u):
    """The integral from 0 to u of an ease (in = u², out = 1 - (1 - u)², inOut = smoothstep, linear = u): the same
    curves the stitch uses for a speed ramp and a zoom move (stitch-cut.sh SPEED RAMPS)."""
    if ease == "linear":
        return u * u / 2
    if ease == "in":
        return u ** 3 / 3
    if ease == "out":
        return u - (1 - (1 - u) ** 3) / 3
    return u ** 3 - u ** 4 / 2


def ramp_average(r):
    """A speed ramp's average speed: its footage length over its played length."""
    return float(r["from"]) + (float(r["to"]) - float(r["from"])) * ease_area(r.get("ease"), 1.0)


def played_length(c):
    """Seconds the segment occupies on the timeline. A sped segment the stitch saved carries "played": its length
    held to whole frames, exactly what the rendered cut plays; anything else plays (end - start) / speed."""
    sp = c.get("speed", 1.0) or 1.0
    sp = ramp_average(sp) if isinstance(sp, dict) else float(sp)   # a plan can carry a ramp inside "speed" itself
    if (sp != 1.0 or c.get("ramp")) and c.get("played"):
        return float(c["played"])
    return (float(c["end"]) - float(c["start"])) / sp


def clip_kwargs(c, punch_scale=1.0):
    """add_video keyword args for one segment. Her own zoom wins over a build punch."""
    sc = float(c.get("scale", punch_scale) or punch_scale)
    kw = {"scale_x": sc, "scale_y": sc}
    if c.get("x"): kw["transform_x"] = float(c["x"])
    if c.get("y"): kw["transform_y"] = float(c["y"])
    if float(c.get("speed", 1.0) or 1.0) != 1.0: kw["speed"] = float(c["speed"])
    if c.get("audio_detached"): kw["volume"] = 0.0
    return kw


def is_your_turn(job_dir):
    """True when the job's cut is the creator's own pulled-back CapCut timeline. Her framing and motion
    choices are already in it, so the build adds no default motion on top."""
    return bool(job_dir) and os.path.exists(os.path.join(job_dir, "transcript", ".your-turn-cut"))


def place(call, did, cuts, rawdir, punch=None):
    """Lay the cut on the main track, then her audio clips on their own track. `call` is the builder's
    VectCut caller (fail-loud)."""
    punch = punch or {}
    segs, overlays = segments_and_overlays(cuts)
    t_us = 0
    for i, c in enumerate(segs):
        call("add_video", draft_id=did, video_url=f"{rawdir}/{c['clip']}", start=c["start"], end=c["end"],
             target_start=t_us / US, **clip_kwargs(c, punch.get(i, 1.0)))
        t_us += round(played_length(c) * US)
    for o in overlays:
        call("add_audio", draft_id=did, audio_url=f"{rawdir}/{o['clip']}", start=o["start"], end=o["end"],
             target_start=o.get("target_start", 0.0), volume=o.get("volume", 1.0), track_name="her audio")
    return t_us / US                                   # where the cut ends: a whole-reel clip (her logo) runs to here
