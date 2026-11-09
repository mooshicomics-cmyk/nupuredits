#!/usr/bin/env python3
"""safe_zones.py — where the PLATFORM draws its own UI, so we never put anything there.

SHARED BASE MODULE. Every engine that places an element on a 1080x1920 reel imports these numbers rather
than hardcoding its own. One correction lands everywhere.

## Why this exists

The engine once documented "top 200px / bottom 300px". The TOP was too generous: Meta's own Reels
guidance reserves the **top 14%** of the frame, and a persistent label placed at y201-263 shipped sitting
directly under Instagram's Reels header. It looked fine in the render and fine in QuickTime. You only see
it in the app, on the phone, after posting.

That is the trap: a UI collision is invisible everywhere except the one place that matters.

The BOTTOM has a different history: it went to 480 (TikTok's band) for a while, then back to 300 by the
creator's explicit decision (locked) — see BOTTOM below. That is a deliberate trade of platform caution
for usable frame, backed by the pipeline's Export step (open the posted reel in the app and look).

## The numbers (1080 x 1920)

                     top reserved   bottom reserved   notes
  Instagram Reels    269 (14%)      384 (20%)         Meta's published guidance
  TikTok             ~260           ~480              heavier bottom + a right-hand action rail
  YouTube Shorts     ~180           ~380              lighter top

`TOP` is the STRICTEST across the three (the incident band). `BOTTOM` is the creator's explicit call:
300px clear, LOOSER than every platform's published band. The per-platform table stays factual, so
`violations(elements, platform="reels")` still reports against Instagram's real band when that matters.
"""
import os, types

W, H = 1080, 1920

# ---- LEGIBILITY FLOORS ----------------------------------------------------------------------------
# Minimum rendered size per role, in px on the 1080x1920 canvas. A reel is watched on a phone: 1080px maps
# to roughly 390pt, so 1px is about 0.36pt. A 44px caption reads as ~16pt, which is fine. 30px reads as
# ~11pt, which is not.
#
# Why these exist: sizes are COMPUTED (fitted to a band, scaled off an anchor, shrunk to fit a width), and
# a computed size can collapse without anything erroring. Measured case: captions rendered at 43px instead
# of the pack's own 61px because they were anchored to a hook that had shrunk. It looked deliberate. The
# engine's own floors were `max(20, ...)`, which is far below anything readable, so nothing caught it.
MIN_PX = {
    "caption":  58,   # snap read-along — anchored to the HyperFrames in-feed baseline so it never drifts small
    "karaoke":  58,   # word-by-word build (same baseline; the width-fit still shrinks a too-wide line to fit)
    "headline": 54,   # hook headline
    "subhead":  28,   # eyebrow above/below the headline
    "takeover": 60,   # full-screen word stack
    "label":    30,   # small persistent chrome
}


def check_text(items):
    """items = [(role, size_px, [width_px])] -> list of human-readable problems. Empty means it will read."""
    out = []
    for it in items:
        role, size = it[0], it[1]
        floor = MIN_PX.get(role)
        if floor and size < floor:
            out.append(f"{role} is {size:.0f}px, below the {floor}px legibility floor")
        if len(it) > 2 and it[2] is not None and it[2] > (RIGHT - LEFT):
            out.append(f"{role} is {it[2]:.0f}px wide, past the {RIGHT - LEFT}px safe width")
    return out

TOP = 270           # nothing meaning-bearing above this line (Meta's 14%; the band the incident was in)
BOTTOM = 1620       # nor below it. H - 300: CREATOR DECISION, locked with an explicit yes. Deliberately
                    # looser than every platform's band (Reels 384 / TikTok ~480 / Shorts ~380) — the
                    # per-platform table below stays factual for a single-platform check, and the Export
                    # step's phone check is what backs this choice. Never widen it further without asking.
LEFT, RIGHT = 90, 990
RIGHT_RAIL = 900    # TikTok/Reels action buttons live right of this; avoid wide elements crossing it

PLATFORMS = {
    "reels":  {"top": 269, "bottom": H - 384},
    "tiktok": {"top": 260, "bottom": H - 480},
    "shorts": {"top": 180, "bottom": H - 380},
}
TEXT_SCALE = 1.0    # pack text sizes are designed for a phone; a wide frame draws them smaller (see below)
LOW_BAND = None     # a wide frame's text sits in this band under the face (see below)

# Horizontal video for YouTube (product/frame.py sets REEL_FRAME for a builder). No platform buttons sit on a YouTube
# video, so the box is plain breathing room off the frame's edges (100 px each side, 110 top, 70 bottom).
# A wide talking head fills the middle of the frame, so anything sharing it with her face sits in the band below her chin.
_WIDE = dict(W=1920, H=1080, TOP=110, BOTTOM=1010, LEFT=100, RIGHT=1820, RIGHT_RAIL=1820, TEXT_SCALE=0.8, LOW_BAND=(785, 1010))
_TALL = dict(W=W, H=H, TOP=TOP, BOTTOM=BOTTOM, LEFT=LEFT, RIGHT=RIGHT, RIGHT_RAIL=RIGHT_RAIL, TEXT_SCALE=TEXT_SCALE, LOW_BAND=LOW_BAND)
if os.environ.get("REEL_FRAME") == "%dx%d" % (_WIDE["W"], _WIDE["H"]):
    globals().update(_WIDE)
    PLATFORMS = {"youtube": {"top": TOP, "bottom": BOTTOM}}


def numbers(wide=False):
    """This module's numbers for one job, for a process that serves more than one (see product/frame.py)."""
    return types.SimpleNamespace(MIN_PX=MIN_PX, **(_WIDE if wide else _TALL))


def violations(elements, platform=None):
    """elements = [(name, top_px, bottom_px)] -> [(name, which_edge, by_px, platform)].

    Pass a platform name to check one, or None for the strictest-across-all default."""
    top = PLATFORMS[platform]["top"] if platform else TOP
    bot = PLATFORMS[platform]["bottom"] if platform else BOTTOM
    out = []
    for name, t, b in elements:
        if t < top:
            out.append((name, "top", round(top - t), platform or "all"))
        if b > bot:
            out.append((name, "bottom", round(b - bot), platform or "all"))
    return out


def describe():
    lines = [f"safe box (engine default; bottom is the creator's 300px call): y {TOP} -> {BOTTOM}, x {LEFT} -> {RIGHT}"]
    for p, v in PLATFORMS.items():
        lines.append(f"  {p:8} y {v['top']} -> {v['bottom']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
