#!/usr/bin/env python3
"""capcut_recut.py — re-cut a FINISHED CapCut draft into a new draft, every layer moving with her words.

A trial reel of a reel she finished by hand in CapCut has to be a genuinely different edit (Instagram reads the same
footage with a new hook card as a repost) AND has to look exactly like what she posted. Rebuilding from the job's
build script loses everything she did in CapCut afterwards (her grade, her compound, her nudges and sounds). This
works on her finished draft itself: the draft is duplicated (her original is only ever read), then the whole timeline
is re-cut as if she had cut every track at once:

  pieces    time ranges of HER timeline, in the new order. Every segment on every track (footage, grade, cutouts,
            graphics, captions, sounds) keeps the part of itself inside each range and moves with it. A range that
            starts later in her reel and is played first is a cold open; a range left out is a drop.
  hook      optional new hook lines, cloned from a hook she styled herself in another draft (same font, size,
            color, spacing, shadow, animation, top-spot position), only the words changed. Editable text. It never
            sits on one of her graphics in its spot: an opening graphic plays first and the hook comes in as it
            ends, and it ends as the next one comes in (measured from the graphics' own frames).
  music     her music bed is never cut with her clips (the song would jump at every cut): it is laid again from
            where her song starts, one continuous play under the new length, her level kept, on the bottom track.

How a piece is written follows what CapCut itself writes when she splits a clip (read from her drafts, never
invented): each piece is its own segment with its own copy of the clip's material and every per-clip extra (speed,
canvas, color, sound mapping...), and every piece of a compound clip shares the one compound (`materials.drafts`).
Keyframes inside a piece are kept and re-based, with a value pinned at each cut edge so a zoom or volume ramp holds
its level across the cut. An in-animation or fade-in stays only on the piece that holds the clip's real start, an
out-animation or fade-out only on the piece that holds its real end.

  python3 product/capcut_recut.py lines "<draft>"                      her clip edges, numbered (the main track)
  python3 product/capcut_recut.py rebed "<draft>" "<new name>" --song-from "<her finished draft>"
                                                                      a copy with its music laid fresh, nothing else changed
  python3 product/capcut_recut.py make "<draft>" "<new name>" --lines "18-20,1-12,16-17" \
        [--hook "eyebrow / headline" --hook-from "<draft with her hook>" --hook-dur 8]

Trial reels drive this through product/trial_reels.py (a reel finished as a CapCut draft).

CapCut must be quit (draft_safety refuses otherwise). Every track is magnet to her footage (capcut_ripple), like
every build. Stdlib + the engine's draft_safety and capcut_ripple.
"""
import argparse, copy, json, os, re, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capcut_ripple
import draft_safety

US = 1_000_000
MIN_PIECE = 20_000                       # a sliver under 20 ms (rounding at a cut edge) is not a piece
SHARED_KINDS = {"drafts"}                # what CapCut shares between the pieces of a split clip


class Refuse(Exception):
    """A plain-words reason the re-cut can't be made."""


SLIVER = 300_000          # µs: a cut-off piece of a layer shorter than this is a glitch, not a moment


def _did(seed, *parts):
    """A fixed new id for (seed, parts): the same re-cut written to every timeline copy gets the same ids."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "recut:" + seed + ":" + ":".join(map(str, parts)))).upper()


def _pool(d):
    """id -> (kind, material) for every material in the draft."""
    out = {}
    for k, v in d["materials"].items():
        if isinstance(v, list):
            for m in v:
                if isinstance(m, dict) and "id" in m:
                    out[m["id"]] = (k, m)
    return out


def main_track(d):
    """The footage track: the video track holding the most time (a saved draft's first video track can be empty)."""
    vids = [t for t in d["tracks"] if t["type"] == "video" and t["segments"]]
    if not vids:
        raise Refuse("This draft has no footage on it.")
    return max(vids, key=lambda t: sum(s["target_timerange"]["duration"] for s in t["segments"]))


def clip_edges(d):
    """Where each of her clips starts and ends on the timeline, in microseconds: [(start, end), ...].
    A main track that is ONE compound clip (she compounded her timeline to grade it) is read from inside."""
    mt = main_track(d)
    pool = _pool(d)
    if len(mt["segments"]) == 1:
        s = mt["segments"][0]
        for r in s.get("extra_material_refs", []):
            k, m = pool.get(r, (None, None))
            if k == "drafts":
                inner = m.get("draft") or {}
                ivid = [t for t in inner.get("tracks", []) if t["type"] == "video" and t["segments"]]
                if ivid:
                    it = max(ivid, key=lambda t: len(t["segments"]))
                    off = s["target_timerange"]["start"] - (s.get("source_timerange") or {}).get("start", 0)
                    end = s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                    out = []
                    for x in sorted(it["segments"], key=lambda x: x["target_timerange"]["start"]):
                        a = x["target_timerange"]["start"] + off
                        b = a + x["target_timerange"]["duration"]
                        a, b = max(a, s["target_timerange"]["start"]), min(b, end)
                        if b - a > MIN_PIECE:
                            out.append((a, b))
                    return _close_gaps(out, end)
    out = [(s["target_timerange"]["start"], s["target_timerange"]["start"] + s["target_timerange"]["duration"])
           for s in sorted(mt["segments"], key=lambda s: s["target_timerange"]["start"])]
    return _close_gaps(out, out[-1][1])


def _close_gaps(edges, end):
    """Each clip runs to the next one's start (the main track is magnetic), the last to the reel's end."""
    return [(a, edges[i + 1][0] if i + 1 < len(edges) else end) for i, (a, _b) in enumerate(edges)]


def pieces_from_lines(d, spec):
    """'18-20,1-12,16-17' (her clip numbers, 1-based, in the new order) -> [(start_us, end_us), ...].
    A run of neighboring clips becomes ONE piece, so nothing is cut where she didn't cut."""
    edges = clip_edges(d)
    out, seen = [], set()
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise Refuse(f"'{part}' isn't a clip number or a run like 3-7.")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if not (1 <= a <= b <= len(edges)):
            raise Refuse(f"'{part}': this reel has clips 1-{len(edges)}.")
        for n in range(a, b + 1):
            if n in seen:
                raise Refuse(f"Clip {n} is used twice: a line can be moved, never repeated.")
            seen.add(n)
        out.append((edges[a - 1][0], edges[b - 1][1]))
    if len(out) < 1:
        raise Refuse("Name at least one run of clips.")
    return out


# ─────────────────────────── the re-cut ───────────────────────────

def _lerp_kf(kfs, t):
    """The values of a keyframe list at time t (linear between neighbors, held past either end)."""
    kfs = sorted(kfs, key=lambda k: k["time_offset"])
    if t <= kfs[0]["time_offset"]:
        return list(kfs[0]["values"])
    if t >= kfs[-1]["time_offset"]:
        return list(kfs[-1]["values"])
    for a, b in zip(kfs, kfs[1:]):
        if a["time_offset"] <= t <= b["time_offset"]:
            span = (b["time_offset"] - a["time_offset"]) or 1
            f = (t - a["time_offset"]) / span
            return [va + (vb - va) * f for va, vb in zip(a["values"], b["values"])]
    return list(kfs[-1]["values"])


def _cut_keyframes(seg, lo, hi, seed, tag):
    """Keep the keyframes inside [lo, hi) of the segment (segment-relative us), re-based to the piece; a value is
    pinned at each cut edge when the ramp continues past it."""
    for group in seg.get("common_keyframes") or []:
        kfs = group.get("keyframe_list") or []
        if not kfs:
            continue
        inside = [k for k in kfs if lo <= k["time_offset"] <= hi]
        new = []
        if not any(k["time_offset"] == lo for k in inside):
            k0 = copy.deepcopy(min(kfs, key=lambda k: abs(k["time_offset"] - lo)))
            k0["values"] = _lerp_kf(kfs, lo); k0["time_offset"] = lo
            new.append(k0)
        new += [copy.deepcopy(k) for k in inside]
        if not any(k["time_offset"] == hi for k in inside) and any(k["time_offset"] > hi for k in kfs):
            k1 = copy.deepcopy(min(kfs, key=lambda k: abs(k["time_offset"] - hi)))
            k1["values"] = _lerp_kf(kfs, hi); k1["time_offset"] = hi
            new.append(k1)
        for i, k in enumerate(sorted(new, key=lambda k: k["time_offset"])):
            k["time_offset"] -= lo
            k["id"] = _did(seed, tag, group.get("id", ""), i)
        group["keyframe_list"] = sorted(new, key=lambda k: k["time_offset"])
        group["id"] = _did(seed, tag, "group", group.get("id", ""))


def _trim_ends(kind, m, has_start, has_end):
    """An in-animation / fade-in belongs to the piece holding the clip's real start; out / fade-out to its end."""
    if kind == "material_animations":
        m["animations"] = [a for a in m.get("animations") or []
                           if (a.get("type") != "in" or has_start) and (a.get("type") != "out" or has_end)]
    elif kind == "audio_fades":
        if not has_start:
            m["fade_in_duration"] = 0
        if not has_end:
            m["fade_out_duration"] = 0


BED_COVER = 0.5          # a music bed plays under at least half the reel...
BED_MAX_VOLUME = 0.6     # ...and sits under her voice (her voice is never this quiet); CapCut library music always counts


def _volumes(s):
    out = [float(s.get("volume", 1.0))]
    for g in s.get("common_keyframes") or []:
        if g.get("property_type") == "KFTypeVolume":
            out += [float(v) for k in g.get("keyframe_list") or [] for v in (k.get("values") or [])[:1]]
    return out


def bed_tracks(d):
    """The music bed's track(s): one piece of music under most of the reel, quieter than her voice. A bed is never
    cut with her clips (the song would jump every cut); the re-cut lays it again, one continuous play."""
    total = d.get("duration") or max((s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                                      for t in d["tracks"] for s in t["segments"]), default=0)
    pool = _pool(d)
    out = []
    for t in d["tracks"]:
        if t["type"] != "audio" or not t["segments"] or not total:
            continue
        songs = set()                                        # one song: a re-cut gives each piece its own copy
        for s in t["segments"]:
            _k, m = pool.get(s.get("material_id"), (None, {}))
            songs.add((m or {}).get("path") or (m or {}).get("name") or s.get("material_id"))
        if len(songs) != 1:
            continue
        if sum(s["target_timerange"]["duration"] for s in t["segments"]) < BED_COVER * total:
            continue
        _k, m = pool.get(t["segments"][0].get("material_id"), (None, {}))
        if (m or {}).get("type") == "music" or max(v for s in t["segments"] for v in _volumes(s)) <= BED_MAX_VOLUME:
            out.append(t)
    return out


def recut(d, pieces, seed="recut"):
    """Return a NEW draft dict: d re-cut to `pieces` [(start_us, end_us), ...] in play order. d is not changed.
    A music bed (bed_tracks) is not cut: it is laid again from where her song starts, one continuous play under the
    whole new length, her level and volume shape kept, on its own track at the bottom."""
    d = copy.deepcopy(d)
    pool = _pool(d)
    beds = {id(t) for t in bed_tracks(d)}
    total = sum(b - a for a, b in pieces)
    referenced = set()
    for t in d["tracks"]:
        for s in t["segments"]:
            referenced.add(s.get("material_id"))
            referenced.update(s.get("extra_material_refs") or [])
    new_mats = {}                                            # kind -> [materials to add]

    def own(mid, slot, sid, has_start, has_end):
        """The clip's own material and every per-clip extra: a copy per piece; a compound stays shared."""
        k, m = pool.get(mid, (None, None))
        if m is None or k in SHARED_KINDS:
            return mid
        nm = copy.deepcopy(m)
        nm["id"] = _did(seed, "mat", mid, sid, slot)          # per new segment: two clips sharing one never collide
        _trim_ends(k, nm, has_start, has_end)
        new_mats.setdefault(k, []).append(nm)
        return nm["id"]

    def place(s, p, pi, o0, s0, o1, s1, tag, at):
        p["target_timerange"] = {"start": at, "duration": o1 - o0}
        speed = float(s.get("speed") or 1.0)
        src = s.get("source_timerange")
        if isinstance(src, dict):
            p["source_timerange"] = {"start": int(round(src["start"] + (o0 - s0) * speed)),
                                     "duration": int(round((o1 - o0) * speed))}
        _cut_keyframes(p, o0 - s0, o1 - s0, seed, tag)
        has_start, has_end = o0 == s0, o1 == s1
        if p.get("material_id"):
            p["material_id"] = own(p["material_id"], "main", p["id"], has_start, has_end)
        p["extra_material_refs"] = [own(r, i, p["id"], has_start, has_end) for i, r in enumerate(p.get("extra_material_refs") or [])]
        return p

    bottom = []
    try:
        main_id = id(main_track(d))
    except Refuse:
        main_id = None
    for ti, t in enumerate(d["tracks"]):
        if id(t) in beds:                                    # the song, laid again whole: never jumps at a cut
            s = min(t["segments"], key=lambda x: x["target_timerange"]["start"])
            s0 = s["target_timerange"]["start"]
            at = s0 if s0 < total else 0
            _k, m = pool.get(s.get("material_id"), (None, {}))
            speed = float(s.get("speed") or 1.0)
            room = total - at
            if (m or {}).get("duration") and isinstance(s.get("source_timerange"), dict):
                room = min(room, int((m["duration"] - s["source_timerange"]["start"]) / speed))
            p = copy.deepcopy(s)
            p["id"] = _did(seed, "bed", s["id"])
            # her volume shape on the new clock (the keyframes keep their times from the song's start)
            t["segments"] = [place(s, p, "bed", s0, s0, s0 + room, s0 + room, f"{ti}.bed", at)]
            bottom.append(t)
            continue
        out = []
        cursor = 0
        for pi, (a, b) in enumerate(pieces):
            for si, s in enumerate(t["segments"]):
                s0 = s["target_timerange"]["start"]
                s1 = s0 + s["target_timerange"]["duration"]
                o0, o1 = max(a, s0), min(b, s1)
                if o1 - o0 < MIN_PIECE:
                    continue
                # a layer the cut leaves as a sliver (the last frames of a graphic or a sound running across the cut)
                # is a flash or a click, not part of the edit: left out. Her footage is never dropped, and a layer that
                # was short to begin with (a click sound) is kept whole. You: "glitched moments where cuts were not perfect"
                if id(t) != main_id and (o0 > s0 or o1 < s1) and o1 - o0 < SLIVER and s1 - s0 > o1 - o0:
                    continue
                p = copy.deepcopy(s)
                p["id"] = _did(seed, "seg", s["id"], pi)
                out.append(place(s, p, pi, o0, s0, o1, s1, f"{ti}.{si}.{pi}", cursor + (o0 - a)))
            cursor += b - a
        t["segments"] = sorted(out, key=lambda s: s["target_timerange"]["start"])
    d["tracks"] = [t for t in d["tracks"] if id(t) not in beds] + bottom      # the bed on the bottom layer
    # drop the originals the pieces replaced (each piece carries its own copy); shared compounds stay
    for k, v in d["materials"].items():
        if isinstance(v, list) and k not in SHARED_KINDS:
            d["materials"][k] = [m for m in v if not (isinstance(m, dict) and m.get("id") in referenced)]
    for k, lst in new_mats.items():
        d["materials"].setdefault(k, []).extend(lst)
    d["duration"] = total
    return d


# ─────────────────────────── her hook, cloned ───────────────────────────

def hook_segments(d):
    """The hook block in a draft: its text segments starting in the first second in the top part of the frame,
    top line first. [(track, segment), ...]"""
    found = []
    for t in d["tracks"]:
        if t["type"] != "text":
            continue
        for s in t["segments"]:
            if s["target_timerange"]["start"] < US and (s.get("clip") or {}).get("transform", {}).get("y", 0) > 0.3:
                found.append((t, s))
    found.sort(key=lambda ts: -ts[1]["clip"]["transform"]["y"])      # top line first
    return found


def hook_shell(src_draft_name):
    """The hook block she styled in another draft: its text segments at the very start, top of frame first.
    Returns (draft_dict, [(track, segment), ...] in reading order)."""
    src_dir = os.path.join(draft_safety.CAP, src_draft_name)
    if not os.path.isdir(src_dir):
        raise Refuse(f"No CapCut draft named '{src_draft_name}' to take the hook style from.")
    sd = json.load(open(draft_safety.draft_json(src_dir), encoding="utf-8"))
    found = hook_segments(sd)
    if not found:
        raise Refuse(f"'{src_draft_name}' has no hook at the top of its first second to copy.")
    return sd, found


def hook_texts(d):
    """The words of a draft's own hook block, top line first ([] when it has none)."""
    pool = _pool(d)
    return [_text_of(pool[s["material_id"]][1]) for _t, s in hook_segments(d) if s.get("material_id") in pool]


def strip_hook(d):
    """Take a draft's own hook block off its timeline (before a re-cut, so it doesn't travel into the middle with
    the clip it sat over; it goes back at the front). Materials only it used go too; a track it emptied goes."""
    gone = {s["id"] for _t, s in hook_segments(d)}
    if not gone:
        return 0
    refs = {}
    for t in d["tracks"]:
        for s in t["segments"]:
            for r in [s.get("material_id")] + list(s.get("extra_material_refs") or []):
                refs.setdefault(r, set()).add(s["id"])
    drop = {r for r, users in refs.items() if users <= gone}
    for t in d["tracks"]:
        t["segments"] = [s for s in t["segments"] if s["id"] not in gone]
    d["tracks"] = [t for t in d["tracks"] if t["segments"] or t["type"] != "text"]
    for k, v in d["materials"].items():
        if isinstance(v, list):
            d["materials"][k] = [m for m in v if not (isinstance(m, dict) and m.get("id") in drop)]
    return len(gone)


def _text_of(m):
    try:
        return json.loads(m["content"]).get("text", "")
    except Exception:
        return ""


def _set_text(m, text):
    """Swap a text material's words, keeping its one style (font, size, color) over the whole new line."""
    c = json.loads(m["content"])
    styles = c.get("styles") or []
    st = copy.deepcopy(styles[0]) if styles else {}
    st["range"] = [0, len(text)]
    c["text"], c["styles"] = text, [st]
    m["content"] = json.dumps(c, ensure_ascii=False)
    if "words" in m:
        m["words"] = {"end_time": [], "start_time": [], "text": []}
    return m


# ─────────────────────────── keeping the hook clear of her graphics ───────────────────────────

HOOK_MIN = 1_500_000     # the shortest stretch a hook reads in (the editor road's HOOK_MIN_S); under this it would flash
HOOK_PAD = 70            # px above and below a hook line's center its words take up (1080x1920 canvas)
SAMPLE = 250_000         # how often a graphic's drawn area is measured while it's on screen
_PLACEHOLDER = re.compile(r"##_draftpath_placeholder_[^#]+_##")
_alpha_cache, _band_cache = {}, {}


def _canvas_y(y_px, clip):
    """A media pixel row -> the canvas row, through the segment's own scale and position (CapCut y points up)."""
    c = clip or {}
    sc = float((c.get("scale") or {}).get("y", 1.0))
    ty = float((c.get("transform") or {}).get("y", 0.0))
    return 960 + (y_px - 960) * sc - ty * 960


def _has_alpha(path):
    if path not in _alpha_cache:
        import subprocess
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt,height",
                            "-of", "default=nw=0", path], capture_output=True, text=True)
        kv = dict(l.split("=", 1) for l in (r.stdout or "").splitlines() if "=" in l)
        fmt = kv.get("pix_fmt", "")
        _alpha_cache[path] = (fmt.startswith(("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")) or fmt == "pal8",
                              int(kv["height"]) if kv.get("height", "").isdigit() else 1920)
    return _alpha_cache[path]


def _drawn_rows(path, t_s, height):
    """(top, bottom) rows of the drawn (non-transparent) part of one frame, in the media's own 1920-tall rows;
    () when nothing is drawn; None when it can't be read."""
    key = (path, round(t_s, 2))
    if key not in _band_cache:
        import subprocess
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t_s):.3f}", "-i", path, "-frames:v", "1",
                            "-vf", "alphaextract,scale=108:192", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True)
        b = r.stdout or b""
        if len(b) < 108 * 192:
            _band_cache[key] = None
        else:
            rows = [y for y in range(192) if max(b[y * 108:(y + 1) * 108]) > 40]
            _band_cache[key] = (rows[0] * 10, rows[-1] * 10 + 10) if rows else ()
    return _band_cache[key]


BACKGROUND = 0.92        # a layer drawn over this much of the frame's height is a background (a backdrop), not a graphic


def _is_her(track):
    """Her own cut-out (the engine labels those tracks "cut out", hers may say "cutout"): her, not a graphic."""
    n = (track.get("name") or "").lower()
    return "cutout" in n or "cut out" in n


def graphic_spans(d, band, until_us, media_root, skip=(), report=None):
    """[(start_us, end_us)] when one of her graphics is drawn inside `band` (canvas rows) before until_us: every
    video layer above her footage (measured from its own frames, so a layer counts only where it draws; inside a
    compound clip, its own layers) and every text or sticker. Her footage, her cut-out, a full-frame backdrop, her
    captions low in the frame and full-frame b-roll don't count."""
    import shutil
    from concurrent.futures import ThreadPoolExecutor
    can_measure = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    jobs, spans = [], []
    rep = report if report is not None else {}
    rep.setdefault("checked", 0); rep.setdefault("unread", 0)

    def walk(dd, t_off, lo, hi, outer, depth):
        """dd's time t plays at t + t_off on the reel, only [lo, hi) of it shows; outer maps dd's rows to the canvas."""
        mt = main_track(dd) if depth == 0 else None
        pool = _pool(dd)
        for t in dd["tracks"]:
            if t is mt or t["type"] not in ("video", "text", "sticker") or _is_her(t):
                continue
            for s in t["segments"]:
                if s["id"] in skip:
                    continue
                a = max(lo, s["target_timerange"]["start"])
                b = min(hi, s["target_timerange"]["start"] + s["target_timerange"]["duration"])
                if b <= a or a + t_off >= until_us or b + t_off <= 0:
                    continue
                clip = s.get("clip") or {}
                to = (lambda c: (lambda y: outer(_canvas_y(y, c))))(clip)
                rep["checked"] += 1
                if t["type"] != "video":
                    y = to(960)
                    pad = HOOK_PAD * float((clip.get("scale") or {}).get("y", 1.0)) * 2
                    if y + pad > band[0] and y - pad < band[1]:
                        spans.append((a + t_off, b + t_off))
                    continue
                speed = float(s.get("speed") or 1.0)
                src0 = (s.get("source_timerange") or {}).get("start", 0)
                inner = next(((pool.get(r, (None, {}))[1] or {}).get("draft") for r in s.get("extra_material_refs") or []
                              if pool.get(r, (None, None))[0] == "drafts"), None)
                if inner and depth < 2:                      # a compound over her footage: the layers inside it
                    rep["checked"] -= 1
                    off = s["target_timerange"]["start"] - src0
                    walk(inner, t_off + off, src0 + (a - s["target_timerange"]["start"]),
                         src0 + (b - s["target_timerange"]["start"]), to, depth + 1)
                    continue
                _k, m = pool.get(s.get("material_id"), (None, {}))
                raw = (m or {}).get("path") or ""
                path = _PLACEHOLDER.sub(lambda _m: media_root, raw) if media_root else raw
                if not path or not os.path.isfile(path) or not can_measure:
                    rep["checked"] -= 1; rep["unread"] += 1
                    continue                                 # nothing to measure: not counted (never a wall), but said
                alpha, height = _has_alpha(path)
                if not alpha:                                # opaque: its frame's rectangle; full-frame footage is no graphic
                    top, bot = to(0), to(height)
                    if top <= 0 and bot >= 1920:
                        continue
                    if top < band[1] and bot > band[0]:
                        spans.append((a + t_off, b + t_off))
                    continue
                ts = list(range(a + 20_000, min(b, until_us - t_off), SAMPLE)) or [a + 20_000]
                rel0 = s["target_timerange"]["start"]
                jobs.append((a + t_off, b + t_off, to, path, height,
                             [(x + t_off, (src0 + (x - rel0) * speed) / US) for x in ts]))

    walk(d, 0, 0, d.get("duration") or until_us, lambda y: y, 0)

    def measure(job):
        a, b, to, path, height, samples = job
        hits = []
        for x, src_s in samples:
            rows = _drawn_rows(path, src_s, height)
            if rows is None or not rows:
                continue
            if rows[1] - rows[0] >= BACKGROUND * height:     # a backdrop behind her: the whole frame, no spot to avoid
                continue
            if to(rows[0]) < band[1] and to(rows[1]) > band[0]:
                hits.append(x)
        if not hits:
            return None
        return (a if hits[0] - a <= SAMPLE else hits[0] - SAMPLE, min(b, hits[-1] + SAMPLE))

    with ThreadPoolExecutor(max_workers=4) as ex:
        spans += [sp for sp in ex.map(measure, jobs) if sp]
    return sorted(spans)


def hook_window(busy, dur, total, opening_until=500_000):
    """(start, dur) of the hook, the editor road's rule: a graphic already on screen as the reel opens plays first and
    the hook comes in as it ends; then the first stretch at least HOOK_MIN long with no graphic in its spot, ending
    as the next one comes in. dur < HOOK_MIN = no clear room."""
    t = max([b for a, b in busy if a < opening_until] + [0])
    for a0, b0 in busy:
        if b0 <= t:
            continue
        if a0 - t >= HOOK_MIN:
            break
        t = max(t, b0)
    nxt = min((a0 for a0, b0 in busy if a0 >= t), default=total)
    return t, max(0, min(dur, nxt - t, total - t))


LOW_FIRST_LINE = 90      # px from the top of the open zone under her chin to the hook's first line (where she puts it)


def add_hook(d, lines, shell_name, dur_us=None, seed="hook", media_root=None, clear=True, low_zone=None,
             when_covered="shorter"):
    """Add her styled hook lines (top line first) for dur_us (None = as long as her hook held), each on its own text
    track, scaled so a longer line keeps the width her line had (never larger than she made it). With `clear`, the
    hook never sits on one of her graphics in its spot (graphic_spans + hook_window, measured from the frames of the
    layers in media_root): it comes in as an opening graphic ends and ends as the next one comes in. When there's
    no clear stretch it goes in at the start anyway and says so ("note"). With when_covered="below" and `low_zone`
    (the measured open zone under her chin, {"top", "bottom"} canvas px, from subject-zones.json), a hook whose top
    spot has a graphic moves into that zone instead, her line spacing kept, when that gives it a better stretch (on
    from the very start first, then longer). Returns {"placed", "start", "dur", "note", "spot"}."""
    sd, shell = hook_shell(shell_name)
    spool = _pool(sd)
    if len(lines) > len(shell):
        raise Refuse(f"'{shell_name}' has {len(shell)} hook line(s); give at most that many.")
    if not dur_us:
        dur_us = max(US, max(ss["target_timerange"]["duration"] for _t, ss in shell))
    at, note, spot, low_ys = 0, "", "top", None
    if clear:
        ys = [_canvas_y(960, ss.get("clip")) for _t, ss in shell[:len(lines)]]
        band = (min(ys) - HOOK_PAD, max(ys) + HOOK_PAD)
        total = d.get("duration") or dur_us
        rep = {}
        busy = graphic_spans(d, band, min(total, 3 * dur_us), media_root, report=rep)
        start, room = hook_window(busy, dur_us, total)
        covered = start > 0 or room < dur_us
        if covered and when_covered == "below" and low_zone and low_zone.get("top") is not None:
            first = float(low_zone["top"]) + LOW_FIRST_LINE
            cand = [first + (y - ys[0]) for y in ys]             # her line spacing, top line first
            lband = (min(cand) - HOOK_PAD, max(cand) + HOOK_PAD)
            if lband[1] <= float(low_zone.get("bottom", 1620)) + HOOK_PAD:
                lbusy = graphic_spans(d, lband, min(total, 3 * dur_us), media_root, report=rep)
                lstart, lroom = hook_window(lbusy, dur_us, total)
                if lroom >= HOOK_MIN and ((lstart == 0, lroom) > (start == 0, room) or room < HOOK_MIN):
                    low_ys, busy, start, room, spot = cand, lbusy, lstart, lroom, "below"
        if room >= HOOK_MIN:
            at, dur_us = int(start), int(room)
        elif busy:
            note = ("the hook is over one of your graphics: there's a graphic in its spot nearly all the way through "
                    "the opening, so there was no clear stretch to put it in")
        if rep.get("unread") and not note:
            note = (f"{rep['unread']} layer{'s' if rep['unread'] != 1 else ''} near the hook couldn't be read, so I couldn't "
                    f"check the hook is clear of {'them' if rep['unread'] != 1 else 'it'}")
    placed = []
    for i, (text, (st, ss)) in enumerate(zip(lines, shell)):
        k, sm = spool[ss["material_id"]]
        old = _text_of(sm)
        m = _set_text(copy.deepcopy(sm), text)
        m["id"] = _did(seed, "text", i)
        d["materials"].setdefault(k, []).append(m)
        seg = copy.deepcopy(ss)
        seg["id"] = _did(seed, "seg", i)
        seg["material_id"] = m["id"]
        refs = []
        for j, r in enumerate(seg.get("extra_material_refs") or []):
            rk, rm = spool.get(r, (None, None))
            if rm is None:
                continue
            nm = copy.deepcopy(rm); nm["id"] = _did(seed, "extra", i, j)
            d["materials"].setdefault(rk, []).append(nm)
            refs.append(nm["id"])
        seg["extra_material_refs"] = refs
        seg["target_timerange"] = {"start": at, "duration": dur_us}
        if isinstance(seg.get("source_timerange"), dict):
            seg["source_timerange"] = {"start": 0, "duration": dur_us}
        if low_ys:                                                  # the open zone under her chin
            seg["clip"]["transform"]["y"] = round((960 - low_ys[i]) / 960, 4)
        if old and len(text) > len(old):                          # same width as her line, never wider
            f = max(0.55, len(old) / len(text) * 1.25)
            if f < 1:
                for ax in ("x", "y"):
                    seg["clip"]["scale"][ax] *= f
        tr = copy.deepcopy(st)
        tr["id"] = _did(seed, "track", i)
        tr["segments"] = [seg]
        tr["name"] = "hook" if i == 0 else f"hook {i + 1}"
        d["tracks"].append(tr)
        placed.append(text)
    for idx, t in enumerate(d["tracks"]):
        for s in t["segments"]:
            s["track_render_index"] = idx
    return {"placed": placed, "start": at, "dur": dur_us, "note": note, "spot": spot}


# ─────────────────────────── the new draft ───────────────────────────

def _write_copy(src_name, new_name, base, d):
    """Duplicate src_name to new_name (never replacing a draft) and write d as the copy's timeline, magnet on."""
    capcut_ripple.enforce_maintrack_ripple(d, main=main_track(d))   # every layer magnet to her footage, as every build
    src_dir = os.path.join(draft_safety.CAP, src_name)
    name = draft_safety.duplicate_draft(src_name, new_name)
    dst = os.path.join(draft_safety.CAP, name)
    new_id = json.load(open(draft_safety.draft_json(dst), encoding="utf-8")).get("id")
    text = json.dumps(d, ensure_ascii=False)
    if new_id and base.get("id") and new_id != base["id"]:
        text = text.replace(base["id"], new_id)                # the copy's own timeline id (its own preview cache)
    text = text.replace(json.dumps(src_dir)[1:-1], json.dumps(dst)[1:-1])   # any absolute self-path -> the copy
    for p in draft_safety.draft_json_copies(dst):
        tmp = p + ".recut"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    mp = os.path.join(dst, "draft_meta_info.json")
    if os.path.isfile(mp):
        meta = json.load(open(mp, encoding="utf-8"))
        meta["tm_duration"] = d["duration"]
        json.dump(meta, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
    draft_safety.clear_draft_caches(dst)
    draft_safety.record_build(name)
    return name


def fresh_bed(d, song_from):
    """Lay the music bed in d again as one continuous play: d's bed track(s) (bed_tracks) come off, and her song as
    she laid it in `song_from` (her finished draft: where it starts, her level and volume shape, her fades) goes in
    on the bottom track under d's whole length. Everything else in d is untouched. Returns the song's name or None."""
    src_beds = bed_tracks(song_from)
    if not src_beds:
        return None
    total = d.get("duration") or 0
    mini = {"tracks": [copy.deepcopy(src_beds[0])], "materials": copy.deepcopy(song_from["materials"]),
            "duration": song_from.get("duration")}
    fresh = recut(mini, [(0, total)], seed="bed:" + str(d.get("id", "")))
    track = fresh["tracks"][0]
    fpool = _pool(fresh)
    seg = track["segments"][0]
    gone = {s["id"] for t in bed_tracks(d) for s in t["segments"]}
    refs = {}
    for t in d["tracks"]:
        for s in t["segments"]:
            for r in [s.get("material_id")] + list(s.get("extra_material_refs") or []):
                refs.setdefault(r, set()).add(s["id"])
    drop = {r for r, users in refs.items() if users <= gone}
    d["tracks"] = [t for t in d["tracks"] if not ({s["id"] for s in t["segments"]} & gone)]
    for k, v in d["materials"].items():
        if isinstance(v, list):
            d["materials"][k] = [m for m in v if not (isinstance(m, dict) and m.get("id") in drop)]
    for r in [seg.get("material_id")] + list(seg.get("extra_material_refs") or []):
        k, m = fpool.get(r, (None, None))
        if m is not None:
            d["materials"].setdefault(k, []).append(m)
    track["id"] = _did("bed-track", str(d.get("id", "")))
    d["tracks"].append(track)                                 # the bottom layer
    for idx, t in enumerate(d["tracks"]):
        for s in t["segments"]:
            s["track_render_index"] = idx
    _k, m = fpool.get(seg.get("material_id"), (None, {}))
    return (m or {}).get("name") or "her music"


def rebed(draft_name, new_name, song_from_name):
    """A copy of draft_name with its music bed laid fresh from song_from_name (fresh_bed); nothing else changes, so
    whatever she did in that draft (a hook she moved, a trim) stays. Her drafts are only read."""
    draft_safety.require_capcut_quit("lay the music fresh in a copy of this draft")
    for n in (draft_name, song_from_name):
        if not os.path.isdir(os.path.join(draft_safety.CAP, n)):
            raise Refuse(f"No CapCut draft named '{n}'.")
    base = json.load(open(draft_safety.draft_json(os.path.join(draft_safety.CAP, draft_name)), encoding="utf-8"))
    song = json.load(open(draft_safety.draft_json(os.path.join(draft_safety.CAP, song_from_name)), encoding="utf-8"))
    d = copy.deepcopy(base)
    bed = fresh_bed(d, song)
    if not bed:
        raise Refuse(f"'{song_from_name}' has no music bed to lay.")
    name = _write_copy(draft_name, new_name, base, d)
    return {"draft": name, "bed": bed, "seconds": round(d["duration"] / US, 2)}


def make(src_name, new_name, pieces, hook=None, hook_from=None, hook_dur=None, low_zone=None, when_covered="shorter"):
    """Duplicate her draft to new_name and re-cut it (+ her styled hook). Her draft is only read.

    A hook block of her own at the top of her draft's first second stays at the front of the re-cut (it is
    lifted off before the cut, so it never rides into the middle with the clip it sat over): with `hook` given,
    the new words go into it (her draft is the style source unless `hook_from` names another); without, her
    own words go back. hook_dur in seconds (None = as long as the style source's hook held)."""
    draft_safety.require_capcut_quit("make a re-cut copy of this draft")
    src_dir = os.path.join(draft_safety.CAP, src_name)
    if not os.path.isdir(src_dir):
        raise Refuse(f"No CapCut draft named '{src_name}'.")
    base = json.load(open(draft_safety.draft_json(src_dir), encoding="utf-8"))
    own = hook_texts(base)
    work = copy.deepcopy(base)
    if own:
        strip_hook(work)
        if not hook:
            hook, hook_from = own, src_name
        hook_from = hook_from or src_name
    wpool = _pool(work)
    beds = [(wpool.get(t["segments"][0].get("material_id"), (None, {}))[1] or {}).get("name") or "her music"
            for t in bed_tracks(work)]
    d = recut(work, pieces, seed=new_name)
    dur = int(hook_dur * US) if hook_dur else None
    hk = add_hook(d, hook, hook_from, dur, seed=new_name + ":hook", media_root=src_dir, low_zone=low_zone,
                  when_covered=when_covered) if hook else {}
    placed = hk.get("placed") or []
    name = _write_copy(src_name, new_name, base, d)
    return {"draft": name, "seconds": round(d["duration"] / US, 2), "hook": placed, "bed": beds,
            "hook_at": round(hk.get("start", 0) / US, 2) if hk else None,
            "hook_dur": round(hk.get("dur", 0) / US, 2) if hk else None, "note": hk.get("note", ""),
            "hook_spot": hk.get("spot")}


def _cli():
    ap = argparse.ArgumentParser(description="Re-cut a finished CapCut draft into a new draft, every layer following.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("lines"); a.add_argument("draft")
    b = sub.add_parser("make"); b.add_argument("draft"); b.add_argument("new_name")
    b.add_argument("--lines", required=True, help="her clip numbers in the new order: '18-20,1-12'")
    b.add_argument("--hook", help="'top line / next line'")
    b.add_argument("--hook-from", help="a draft with a hook she styled (its look is copied)")
    b.add_argument("--hook-dur", type=float, default=None, help="seconds (default: as long as that hook held)")
    b.add_argument("--when-covered", choices=("shorter", "below"), default="shorter",
                   help="a graphic in the hook's top spot: end the hook as it comes in, or move the hook under her chin")
    b.add_argument("--zones", help="the reel's subject-zones.json (where the open zone under her chin is)")
    c = sub.add_parser("rebed", help="a copy of a draft with its music laid fresh, one continuous play")
    c.add_argument("draft"); c.add_argument("new_name")
    c.add_argument("--song-from", required=True, help="the draft whose music bed is laid right (her finished draft)")
    args = ap.parse_args()
    try:
        if args.cmd == "lines":
            d = json.load(open(draft_safety.draft_json(os.path.join(draft_safety.CAP, args.draft)), encoding="utf-8"))
            for i, (s, e) in enumerate(clip_edges(d), 1):
                print(f"{i:3}  {s / US:7.3f} - {e / US:7.3f}")
            return 0
        if args.cmd == "rebed":
            print(json.dumps(rebed(args.draft, args.new_name, args.song_from), ensure_ascii=False))
            return 0
        d = json.load(open(draft_safety.draft_json(os.path.join(draft_safety.CAP, args.draft)), encoding="utf-8"))
        pieces = pieces_from_lines(d, args.lines)
        hook = [h.strip() for h in args.hook.split(" / ")] if args.hook else None
        if hook and not args.hook_from and not hook_texts(d):
            raise Refuse("Name the draft whose hook style to copy with --hook-from.")
        low = (json.load(open(args.zones, encoding="utf-8")).get("zones") or {}).get("below") if args.zones else None
        print(json.dumps(make(args.draft, args.new_name, pieces, hook, args.hook_from, args.hook_dur,
                              low_zone=low if (low or {}).get("usable") else None, when_covered=args.when_covered),
                         ensure_ascii=False))
        return 0
    except Refuse as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
