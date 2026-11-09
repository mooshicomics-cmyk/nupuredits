#!/usr/bin/env python3
"""subject_place.py — hand the CapCut route a MEASURED y instead of a guessed one, and catch it when
something still lands on her. Shared by every format (Clean Yap / Super Yap / VO), never copy-pasted.

## Why this exists

On the rendered routes a composition is measured and gated. On the CapCut route there is no DOM to measure:
`add_text(..., x, y, ...)` takes a bare number and writes it straight into the draft. Those numbers were
picked by eye and copied between jobs — hooks went in at transform_y 0.60 / 0.62 / 0.74 across builds with
nothing behind the choice. CapCut's transform is in HALF-CANVAS units (pyJianYingDraft: "单位为半个画布宽"),
so 0.60 is y384 on a 1920-tall frame: comfortably clear of a subject framed low, and directly on the
forehead of one framed high. Same number, same code, opposite result, and no way for anyone to tell which
they were getting. A creator reported the second case repeatedly and was told it would be remembered.

So: `y_for()` turns a measured open zone into the number, and `check_draft()` refuses to let a build finish
with type sitting on her. Neither asks anyone to remember anything.

## Units

  transform_y = (960 - y_px) / 960   on the 1080x1920 authoring frame: +1.0 is the top edge, 0 the centre,
  -1.0 the bottom. Positive is UP, which is the opposite of the px axis and the reason this conversion has
  a home instead of being written out per build.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_zones

HALF = safe_zones.H / 2.0      # 960: the half-canvas unit CapCut's transform is expressed in


def to_norm(y_px):
    """1080x1920 px (0 = top, grows down) -> CapCut transform_y (+1 top, 0 centre, -1 bottom)."""
    return round((HALF - float(y_px)) / HALF, 4)


def to_px(y_norm):
    """CapCut transform_y -> 1080x1920 px."""
    return int(round(HALF - float(y_norm) * HALF))


def load(start):
    """Find and read this job's subject-zones.json by walking up from a path. None when never measured."""
    import subject_guard
    p = subject_guard.find_zones(start)
    if not p and start and not os.path.exists(str(start)):
        # a bare job slug (finalize(job="the-pricing-one")) names projects/<slug>, not a folder in the cwd
        job_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", str(start))
        if os.path.isdir(job_dir):
            p = subject_guard.find_zones(job_dir)
    return json.load(open(p, encoding="utf-8")) if p else None


def y_for(zones, zone=None, block_h_px=None, role="hook"):
    """The transform_y to place a text block in a measured open zone.

    zone: which measured zone to sit in. OMIT it to use the zone she has TAUGHT for this `role`
    (`/learn caption.zone below`), falling back to "above". Naming a zone explicitly always wins — this
    reel's instruction outranks a standing preference. The NUMBER is always measured from THIS footage
    either way; the preference only chooses which open space to aim at, which is why "captions a bit
    higher" is safe to remember and a y value never is.

    block_h_px: the block's rendered height if you know it — the block is then seated in the zone (top-anchored
    with the leftover split, so a tall block stays inside rather than centring itself out of the zone). Without
    it you get the zone's centre, which is right for a single line and close enough for two.

    Raises rather than guessing when the zone has no room: a caller that silently fell back to a default number
    is how this defect travelled between jobs in the first place."""
    if zone is None:
        try:
            import learned
            zone = learned.get(f"{role}.zone", "above")
        except Exception:
            zone = "above"
    z = (zones or {}).get("zones", {}).get(zone)
    if not z:
        raise ValueError(f"no measured `{zone}` zone — run workflows/subject-zones.py over her footage first")
    if not z.get("usable"):
        raise ValueError(f"the `{zone}` zone has no room on this framing: {z.get('why', 'no clearance')}. "
                         f"Pick another zone (usable: "
                         f"{[k for k, v in zones['zones'].items() if v.get('usable')] or 'none'}).")
    if zone in ("left", "right"):
        raise ValueError(f"`{zone}` is a horizontal zone — it constrains x, not y; use z['center_x_px'].")
    top, bottom = z["top"], z["bottom"]
    if block_h_px:
        if block_h_px > (bottom - top):
            raise ValueError(f"a {block_h_px}px block does not fit the {zone} zone ({bottom - top}px of room). "
                             f"Shorten the copy or drop the size — do NOT let it spill onto her.")
        centre = top + (bottom - top - block_h_px) / 2 + block_h_px / 2
    else:
        centre = (top + bottom) / 2
    return to_norm(centre)


def _texts_by_id(d):
    out = {}
    for m in d.get("materials", {}).get("texts", []):
        label = ""
        try:
            label = (json.loads(m.get("content") or "{}").get("text") or "").replace("\n", " ")[:40]
        except Exception:
            pass
        out[m.get("id")] = label
    return out


def check_draft(d, zones, margin=0):
    """Finalize-time net: every text segment whose CENTRE sits inside the measured subject box.

    Deliberately centre-only. The block's rendered height is not knowable from the draft (CapCut sizes text in
    its own units against a font it resolves at open time), and a guess at the height would produce false
    alarms on type that is merely near her — which trains everyone to ignore the check. A centre inside her
    head-to-chin box is unambiguous: that is type ON her, which is the reported defect.

    Returns a list of plain-language breaches. Empty when clear, and empty when never measured — the caller
    says which, because those are different states and only one of them is good news."""
    if not zones:
        return []
    s = zones.get("face") or zones.get("subject") or {}     # is it ON her: where her face usually is, when measured
    top, bot = s.get("head_top"), s.get("chin_bottom")
    left, right = s.get("left"), s.get("right")
    if top is None or bot is None:
        return []
    labels = _texts_by_id(d)
    out = []
    for t in d.get("tracks", []):
        if t.get("type") != "text":
            continue
        for seg in t.get("segments", []):
            if seg.get("material_id") not in labels:
                continue
            tr = (seg.get("clip") or {}).get("transform") or {}
            y_px = to_px(tr.get("y", 0.0))
            x_px = int(round(safe_zones.W / 2 + float(tr.get("x", 0.0)) * (safe_zones.W / 2)))
            if not (top - margin <= y_px <= bot + margin):
                continue
            if left is not None and right is not None and not (left - margin <= x_px <= right + margin):
                continue    # beside her, not on her — a side callout is a legitimate placement
            label = labels[seg["material_id"]] or "(untitled text)"
            out.append(f'"{label}" sits at y{y_px} on the "{t.get("name") or "text"}" track, inside her '
                       f'head-to-chin box (y{top}–{bot}) — that is type ON her face')
    return out


def auto_clear(d, start, margin=0):
    """Try to fix it before it ships: each piece of text whose centre sits on her moves to the nearest measured
    open zone (above or below her), in place in the draft dict. What can't move (no open zone) stays as it is;
    the draft still builds (her rule: she always gets a product). Returns how many moved."""
    zones = load(start)
    if not zones or not check_draft(d, zones, margin):
        return 0
    s = zones.get("face") or zones["subject"]
    top, bot, left, right = s.get("head_top"), s.get("chin_bottom"), s.get("left"), s.get("right")
    spots = []
    for zn in ("above", "below"):
        try:
            spots.append(y_for(zones, zone=zn))
        except Exception:
            pass
    if not spots:
        return 0
    labels, moved = _texts_by_id(d), 0
    segs = [seg for t in d.get("tracks", []) if t.get("type") == "text" for seg in t.get("segments", [])
            if seg.get("material_id") in labels]
    span = lambda seg: (int((seg.get("target_timerange") or {}).get("start", 0)),
                        int((seg.get("target_timerange") or {}).get("start", 0)) + int((seg.get("target_timerange") or {}).get("duration", 0)))
    def on_her(seg):
        tr = (seg.get("clip") or {}).get("transform") or {}
        y_px = to_px(tr.get("y", 0.0)); x_px = int(round(safe_zones.W / 2 + float(tr.get("x", 0.0)) * (safe_zones.W / 2)))
        return top - margin <= y_px <= bot + margin and (left is None or right is None or left - margin <= x_px <= right + margin)
    def taken(yn, seg):                                       # another piece of text already sits there at the same time
        a0, a1 = span(seg)
        for o in segs:
            if o is seg or on_her(o):
                continue
            b0, b1 = span(o)
            if a0 < b1 and b0 < a1 and abs(to_px(((o.get("clip") or {}).get("transform") or {}).get("y", 0.0)) - to_px(yn)) < 140:
                return True
        return False
    for seg in segs:
        if not on_her(seg):
            continue
        tr = seg.setdefault("clip", {}).setdefault("transform", {})
        y_px = to_px(tr.get("y", 0.0))
        free = [yn for yn in sorted(spots, key=lambda yn: abs(to_px(yn) - y_px)) if not taken(yn, seg)]
        if not free:
            continue                                          # nowhere clear at that moment: it stays, and is said
        tr["y"] = free[0]
        moved += 1
    return moved


def report(d, start, margin=0):
    """check_draft + the honest not-measured case, as printable lines. -> (breaches, lines)."""
    zones = load(start)
    if not zones:
        return [], ["  ⚠ SUBJECT: her footage was never measured for this job, so text placement was not "
                    "checked. Run: uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4"]
    br = check_draft(d, zones, margin)
    band = _platform_band(d)
    if not br:
        s = zones.get("face") or zones["subject"]
        return [], [f"  ✓ subject: no text sits on her (measured box y{s['head_top']}–{s['chin_bottom']})"] + band
    lines = ["  ⚠ SUBJECT: text may sit on her (built anyway; she moves it in CapCut or keeps it):"]
    lines += [f"     • {b}" for b in br]
    z = zones.get("zones", {})
    ok = [f"{k} (transform_y {v['center_y_norm']})" for k, v in z.items()
          if v.get("usable") and "center_y_norm" in v]
    lines.append(f"     Open instead: {', '.join(ok) if ok else 'nothing clear — re-frame or re-measure'}. "
                 "product/subject_place.py y_for(zones, 'above'|'below') returns the number.")
    return br, lines + band


def _platform_band(d):
    """WARN (never refuse) on text whose centre sits in the platform's own UI band. Different rule, different
    history from the subject box — safe_zones.TOP exists because a label at y201-263 shipped under Instagram's
    Reels header, invisible in the render and in QuickTime, visible only in the app after posting. The rendered
    routes get this from reel_render's safe-zone check; the CapCut route had nothing, and a shipped builder
    still carries transform_y 0.74, which is y250: clear of her face and squarely inside that band.

    A warning, not a refusal: the centre is all this can see, the creator can move it in CapCut, and this rule
    already has a report-mode home on the other route."""
    hits = []
    labels = _texts_by_id(d)
    for t in d.get("tracks", []):
        if t.get("type") != "text":
            continue
        for seg in t.get("segments", []):
            if seg.get("material_id") not in labels:
                continue
            y = to_px(((seg.get("clip") or {}).get("transform") or {}).get("y", 0.0))
            edge = "top" if y < safe_zones.TOP else ("bottom" if y > safe_zones.BOTTOM else None)
            if edge:
                hits.append(f'"{labels[seg["material_id"]] or "(untitled text)"}" is centred at y{y}, inside '
                            f'the {edge} platform UI band (safe y{safe_zones.TOP}–{safe_zones.BOTTOM})')
    if not hits:
        return []
    return ["  ⚠ PLATFORM BAND: text sits where the app draws its own UI (you only see this in the app, "
            "after posting):"] + [f"     • {h}" for h in hits]
