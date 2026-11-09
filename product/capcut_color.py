#!/usr/bin/env python3
"""capcut_color.py — one place that decides a draft's colour handling.

WHY THIS EXISTS. Every video segment is BORN as HDR. `pyJianYingDraft/video_segment.py` stamps
`hdr_settings {"mode": 1, "nits": 1000}` on export, unconditionally, and `workflows/capcut-live.py`
did the same. Our footage reaching CapCut is bt709 SDR by then (stitch-cut.sh tags it, hook-burst.py does
the bt2020 matrix convert), so CapCut applies HDR treatment to footage that is already SDR and the
clip renders TINTED or WASHED OUT.

The correction used to live as an identical copy-pasted block in exactly two files, superyap.py and
cleanyap.py, out of roughly twenty modules that touch a draft. Its own comment said it had "recurred
on the hook burst + b-roll overlays". It recurred because the correction sat downstream of the
default instead of replacing it: every new path was born wrong and had to remember to undo it, and a
path that forgot shipped a washed-out reel with no error anywhere.

So there are now two lines of defence and this module is the second one:
  1. The DEFAULT is SDR at both write sites, so a segment is born right.
  2. `enforce_sdr(draft)` sweeps the finished draft, so a segment that arrived any other way
     (a template, a CapCut round-trip, a path we have not written yet) is corrected before ship.
     It runs inside capcut_ripple.enforce_maintrack_ripple(), which every draft writer already calls
     (ship gate 12), so an overlay, GIF, slip or compound write is swept too (ISS-13).

Neither is enough alone. (1) misses anything the engine did not create. (2) misses any path that
forgets to call it, which is the failure this module exists to end.

MODE REFERENCE, from real CapCut drafts: mode 0 = SDR, modes 1 and 4 = HDR. nits 203 is the SDR
reference white CapCut writes on an SDR clip; 1000 is an HDR mastering level.

IF THE ENGINE EVER SHIPS GENUINE HDR END TO END, this is the file to change, and the conversion in
hook-burst.py and stitch-cut.sh has to change with it. Do not special-case it at a call site.
"""

SDR = {"mode": 0, "intensity": 1.0, "nits": 203}

# Written by CapCut and by the draft library on an HDR clip. Anything not 0 gets corrected.
_HDR_MODES = (1, 4)


def sdr_settings():
    """A fresh copy, so a caller mutating its segment cannot poison every other segment."""
    return dict(SDR)


def needs_correction(seg):
    hs = seg.get("hdr_settings")
    return not isinstance(hs, dict) or hs.get("mode", 0) != 0


def enforce_sdr(draft):
    """Force every video segment in a finished draft to SDR. Returns how many were corrected.

    Idempotent, and safe to call more than once on the same draft. Walks tracks rather than trusting
    any one builder's shape, because the point is to catch segments this engine did not write.
    Every draft writer reaches it through capcut_ripple.enforce_maintrack_ripple(), so it never raises
    on an odd shape: anything that is not a video segment dict is left exactly as it was.
    """
    fixed = 0
    if not isinstance(draft, dict):
        return fixed
    for track in draft.get("tracks", []) or []:
        if not isinstance(track, dict) or track.get("type") != "video":
            continue
        for seg in track.get("segments", []) or []:
            if isinstance(seg, dict) and needs_correction(seg):
                seg["hdr_settings"] = sdr_settings()
                fixed += 1
    return fixed


# The other half of the same promise. Marking a segment SDR is only true when the file it plays IS SDR: an iPhone
# HDR clip (HLG, or PQ from a Dolby Vision export) played as SDR is the bright, flat, grey look a buyer reported.
# Intake converts HDR clips (product/hdr.py); this stops any draft that would still point at one.
CONVERT_FIRST = ("{name} is HDR video (an iPhone HDR clip), and CapCut would show it grey and washed out. "
                 "Convert the job's clips to normal colour first: python3 product/hdr.py <job> says how long it "
                 "takes, then python3 product/hdr.py <job> --apply. Then build the draft again.")


def hdr_media(draft):
    """Paths of the draft's video files that are still HDR (HLG or PQ). Photos and missing files are skipped."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from hdr import hdr_kind
    found = []
    for v in (draft.get("materials") or {}).get("videos") or []:
        path = v.get("path") or ""
        if v.get("type", "video") == "video" and path and os.path.isfile(path) and hdr_kind(path) in ("hlg", "pq"):
            found.append(path)
    return found

