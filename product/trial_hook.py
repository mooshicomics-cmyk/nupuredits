#!/usr/bin/env python3
"""trial_hook.py — build a reel's CapCut draft again with ONLY the hook's words changed (a trial reel).

A trial reel is the same finished reel with a different opening, made for Instagram's trial reels. On the CapCut
routes every reel has its own short build script (projects/<job>/build-*.py) that types the hook in by hand, so
nothing outside the script knows the hook's words. Two environment variables let `product/trial_reels.py` run
that same script unchanged and get the trial instead:

  REE_TRIAL_HOOK  the trial hook, its lines in reading order: "first line / second line" (or a JSON list)
  REE_TRIAL_NAME  the trial draft's name ("Sunday Reset trial B"); finalize still never reuses a name

The builders (`cleanyap.add_text`, `superyap.add_text`) ask `swap()` before placing any text: the hook block (a track
named hook*, or the eyebrow / headline / subhead / kicker that sits with it) gets the trial's lines in the order the
script places them, re-sized to the new length on the hook's own track and wrapped 9:16-safe like the original.
Everything else in the reel (her cut, captions, thoughts, sounds, zooms) is built exactly as before. `remap()` keeps
the font the script chose for each line, `name()` names the draft, and `report()` says plainly when the script
placed no hook text at all, so a trial is never called made when it isn't.

Unset (every normal build), every function hands back what it was given. Stdlib only; never raises.
"""
import json, os, re

HOOK_BLOCK = ("hook", "eyebrow", "headline", "subhead", "kicker")
_SWAPPED = {}            # the script's text -> the trial text placed instead
_USED = []               # trial lines already placed


def lines():
    raw = (os.environ.get("REE_TRIAL_HOOK") or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            got = [str(x).strip() for x in json.loads(raw)]
            return [x for x in got if x]
        except ValueError:
            pass
    return [p.strip() for p in raw.split(" / ") if p.strip()]


def active():
    return bool(lines())


def in_hook_block(track):
    t = (track or "").lower()
    return any(t.startswith(k) for k in HOOK_BLOCK)


def swap(track, text, size, hook_size=None, wrap=None):
    """(text to place, size) for one add_text call. A hook-block call past the trial's last line returns
    (None, size): the trial has fewer lines than the original, so that line is left out."""
    want = lines()
    if not want or not in_hook_block(track):
        return text, size
    i = len(_USED)
    if i >= len(want):
        _SWAPPED[text] = None
        return None, size
    new = want[i]
    if (track or "").lower().startswith("hook") and hook_size:
        try:
            size = hook_size(new)
        except Exception:
            pass
    placed = new
    if wrap:
        try:
            placed = wrap(new, size)
        except Exception:
            placed = new
    _USED.append(new)
    _SWAPPED[text] = placed
    return placed, size


def remap(font_map):
    """The script's font for each of its hook lines, keyed by the trial text that replaced it."""
    if not _SWAPPED:
        return font_map
    out = dict(font_map or {})
    for old, new in _SWAPPED.items():
        if old in out and new:
            out[new] = out[old]
    return out


def name(default):
    """The trial draft's name. "{name}" in REE_TRIAL_NAME is the script's own reel name without its version
    ("Sunday Reset 1.2" -> "Sunday Reset"), so "{name} trial B" reads as the reel it came from."""
    n = (os.environ.get("REE_TRIAL_NAME") or "").strip()
    if not n:
        return default
    base = re.sub(r"\s+\d+\.\d+$", "", default or "").strip() or "Reel"
    return re.sub(r"[/:]", "-", n.replace("{name}", base))


def unplaced():
    """True on a trial build that placed no hook text: the trial has nowhere to go, so the build must stop."""
    return active() and not _USED


def stop_unplaced(cap, did):
    """Stop a trial build that placed no hook text, BEFORE any draft is named or registered, and take away the
    unregistered folder VectCut may already have saved, so no hookless "trial" is ever left in CapCut."""
    if not unplaced():
        return
    try:
        import draft_safety
        draft_safety.discard_unfinished(os.path.join(cap, did))
    except Exception:
        pass
    raise SystemExit(report()[0] + " Nothing was added to CapCut.")


def report():
    """The lines finalize prints on a trial build (nothing on a normal one)."""
    want = lines()
    if not want:
        return []
    if not _USED:
        return ["[trial] this build placed no hook text, so the trial hook had nowhere to go."]
    out = [f"[trial] hook: {' / '.join(_USED)}"]
    left = want[len(_USED):]
    if left:
        out.append(f"[trial] the build has fewer hook lines than the trial; not placed: {' / '.join(left)}")
    return out
