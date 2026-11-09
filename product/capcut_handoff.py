#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pillow", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'", "numpy"]   # requests: talks to VectCut · pillow: cleanyap.finalize imports it · numpy: capcut_alpha cleans each layer's faint edges
# ///
"""capcut_handoff.py — the CapCut project that ships ALONGSIDE a well-done reel.

WHY THIS EXISTS. Well-done bakes everything into one finished MP4, so when a creator wanted to change
her zooms there was nothing left to hand over: a baked file has no separate layers. The first PC tester
hit exactly that, asked three times to move to CapCut, and it took most of a day to get her a project she
could work in. Route A's spec said "nothing editable afterward" and there was no supported way to switch.
So well-done now hands over BOTH: the finished video, and a CapCut project beside it.

WHAT'S IN THE PROJECT (and what is not):
  • footage    — the engine's clean cut at scale 1.0, one clip per kept line (split where the rough cut
                 joined them; --one-clip lays it as one). THIS is the point: hers to trim, move and zoom.
                 With --punch (separate_layers.sh passes it) the plan's punch-in windows become
                 their own pieces at the plan's scale, held on her face: plain clip zooms, still hers.
  • layers     — with --layer NAME=FILE (repeatable) each KIND of element gets its OWN track, stacked
                 in the order given, so captions / hook / screens move, retime and switch off
                 independently. Reach for this whenever she asks for elements separated; do NOT answer
                 that with "that route is baked."
  • graphics   — the rendered overlay, one transparent clip sitting over the footage on the timeline.
                 On this route the type is already rendered, so it moves and retimes as a whole; it does
                 not come apart into individual words. That is what well-done means. Someone who wants
                 every element separate wants the medium route, and should be told so rather than sold this.
  • sound      — each cue as its OWN audio clip, never one pre-mixed wav, so a single cue can be moved,
                 swapped or turned down without touching the rest; each at the level the finished video gives
                 it, the music bed (when there is one) on its own track, and her Sound edits from the visual
                 editor (review/sound.json, product/sound_plan.py) applied.

WHAT THIS DOES NOT DO: it does not export. The finished MP4 is already the deliverable and the engine's
job ends there. This project is for HER changes; if she makes one, she exports it herself from CapCut.
Nothing here drives a CapCut export.

  uv run product/capcut_handoff.py <JOB> [--overlay <file.mov>] [--base <cut.mp4>] [--name <draft name>]\n\nRUN IT WITH `uv run`, not python3. This talks to the editing engine over HTTP, so it needs the\n`requests` package, and the system Python does not necessarily have it — on this very machine it\ndoes not. The script header above declares the dependency so `uv run` fetches it once and every\nmachine behaves the same, which is the same reason head-framing.py survived a PC where hook-burst.py\ndied with a missing import.

Needs the VectCut editing engine running (product/engine/VectCutAPI/start-editor.command, SETUP.md §1b)
and CapCut QUIT — CapCut's next save silently overwrites anything written while it is open.
"""
import argparse, json, os, subprocess, sys, glob

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
BASE_URL = "http://localhost:9001"


def call(ep, **kw):
    try:
        import requests
    except ModuleNotFoundError:
        sys.exit("  \u26d4 this needs the `requests` package. Run it with `uv run product/capcut_handoff.py "
                 "<JOB>` (uv fetches it from the header at the top of this file), not with python3.")
    # vectcut_engine.post turns the engine on when it is off, follows a long save through to the end, and gives a
    # slow call one longer try; only an engine that will not come up at all ends the handover here.
    import vectcut_engine
    try:
        j = vectcut_engine.post(BASE_URL, ep, kw)
    except RuntimeError as e:
        sys.exit(f"  ⛔ {e}")
    # VectCut wraps every reply as {success, error, output}. Read the envelope, never the top level:
    # treating `output` as the result is how a caller ends up with a KeyError on a call that worked.
    if not j.get("success"):
        sys.exit(f"  ⛔ {ep} failed: {j.get('error') or j}")
    return j.get("output") or {}


def _dur(p):
    import subprocess
    try:
        return float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
            text=True).strip())
    except Exception:
        return 0.0


def _punch_anchors(wins, punch, base, jd):
    """One (x, y, confidence) face anchor per punch window, 0..1 of the frame: the same order the well-done
    bake uses (build-reel-mp4.resolve_punch_anchors): the plan's own "anchors", then a face-anchors.json
    measured for exactly these windows, then a live workflows/head-framing.py measure. Unmeasurable stays
    centred and says so: a silent centre zoom slides an off-centre creator toward the edge."""
    n = len(wins)
    plan = punch.get("anchors")
    if plan and len(plan) == n:
        return [(float(r[0]), float(r[1]), float(r[2]) if len(r) > 2 else 1.0) for r in plan]
    path = os.path.join(jd, "face-anchors.json")

    def cached():
        try:
            rows = json.load(open(path, encoding="utf-8")).get("windows", [])
        except (ValueError, OSError):
            return None
        if len(rows) != n:
            return None
        return [(float(r["anchor"][0]), float(r["anchor"][1]), float(r.get("confidence", 1.0))) for r in rows]

    got = cached()
    ff = os.path.join(ROOT, "workflows", "head-framing.py")
    if not got and os.path.exists(ff):
        import shutil, subprocess
        if shutil.which("uv"):
            print(f"  measuring where you sit in each punch-in ({n}) ...")
            try:
                subprocess.run(["uv", "run", ff, base, "--windows", json.dumps([list(w) for w in wins]),
                                "--out", path], check=True, timeout=600)
                got = cached()
            except (subprocess.SubprocessError, OSError) as e:
                print(f"  · could not measure the punch-ins ({e})")
    if got:
        return got
    print(f"  ⚠ no face anchors: the {n} punch-in(s) zoom on the frame centre. "
          f"Fix: uv run workflows/head-framing.py <cut> --windows @caption-plan.json --out {path}")
    return [(0.5, 0.5, 0.0)] * n


def footage_pieces(jd, base, bdur):
    """The cut as main-track pieces: (start, end, scale, x, y). Without a "punch" in caption-plan.json that is
    one clip at 1.0. With one, each punch window becomes its own piece at the plan's scale, anchored on her
    face, so the punch-ins the plan asked for are in the draft as plain clip zooms she can change or reset.
    Same file, same times: every piece plays the moment it sits at, so the graphics above stay in sync."""
    try:
        punch = json.load(open(os.path.join(jd, "caption-plan.json"), encoding="utf-8")).get("punch") or {}
    except (ValueError, OSError):
        punch = {}
    z = float(punch.get("scale", 1.10))
    wins, t = [], 0.0
    for a, b in sorted((float(a), float(b)) for a, b in punch.get("windows", []) or []):
        a, b = max(a, t), min(b, bdur)
        if b - a > 0.05:
            wins.append((a, b)); t = b
    if not wins or z <= 1.0:
        return [(0.0, bdur, 1.0, 0.0, 0.0)]
    import capcut_motion
    pieces, t = [], 0.0
    for (a, b), (fx, fy, c) in zip(wins, _punch_anchors(wins, punch, base, jd)):
        if a - t > 1e-3:
            pieces.append((t, a, 1.0, 0.0, 0.0))
        x, y = capcut_motion.anchor_transform(fx, fy, z, c)
        pieces.append((a, b, z, x, y)); t = b
    if bdur - t > 1e-3:
        pieces.append((t, bdur, 1.0, 0.0, 0.0))
    print(f"  punch-ins: {len(wins)} at {z:.2f}x from the plan, each held on your face")
    return pieces


def slice_points(jd, bdur):
    """Where the rough cut joined one kept line to the next, in seconds on the cut: the main track is split there
    so each line is its own clip (the promise every route makes: each kept line its own clip, hers to trim or
    move). Read from transcript/cuts.json (the frame-snapped plan the stitch saved). Only when that plan's
    lengths add up to this footage; a different base (a baked or re-timed file) stays one clip."""
    try:
        segs = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    except (ValueError, OSError, KeyError, TypeError):
        return []
    from cut_placement import played_length                  # a sped clip counts at the length it PLAYS (her page's Speed)
    lens = [played_length(x) for x in segs if "start" in x and "end" in x]
    if len(lens) < 2 or abs(sum(lens) - bdur) > 0.1:
        return []
    pts, t = [], 0.0
    for d in lens[:-1]:
        t += d
        pts.append(round(t, 4))
    return pts


def split_at(pieces, pts):
    """Each (start, end, scale, x, y) piece cut at every slice point inside it; a piece keeps its zoom."""
    out = []
    for s, e, sc, x, y in pieces:
        cur = s
        for p in pts:
            if cur + 0.02 < p < e - 0.02:
                out.append((cur, p, sc, x, y)); cur = p
        out.append((cur, e, sc, x, y))
    return out


US = 1_000_000      # CapCut keeps time in whole microseconds


def stretch_spots(at, parts, fits=lambda start, length: length):
    """[(path, start, length), ...] seconds for a layer laid as stretches (render_spans parts), on one microsecond
    grid. Each stretch's start and length used to be rounded on their own, so one could end 1 microsecond after
    the next began and CapCut refused the overlap ("New segment overlaps with existing segment"). Here every edge
    is a whole microsecond and a stretch never runs past the next one's start. `fits` trims a length to her
    footage."""
    order = sorted(parts, key=lambda p: p[1])
    starts = [round((at + pa) * US) for _pf, pa, _d in order]
    out = []
    for k, (pf, pa, d) in enumerate(order):
        s = starts[k]
        e = s + round(fits(at + pa, d) * US)
        if k + 1 < len(order):
            e = min(e, max(s, starts[k + 1]))
        out.append((pf, s / US, (e - s) / US))
    return out


# A layer this much shorter than her cut is a short graphic (a hook, a card, one look), not a full-length
# transparent layer: it needs its own start. Full-length layers start at 0 and are left exactly as they are.
SHORT_BY = 1.0


def page_starts(jd):
    """{look name: start seconds} from her page (review/looks.json "offset", the same start finish.py hands over)."""
    try:
        doc = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for L in doc.get("layers", []) or []:
        if isinstance(L, dict) and L.get("name"):
            try:
                out[str(L["name"])] = round(float(L.get("offset") or 0), 3)
            except (TypeError, ValueError):
                pass
    return out


def place_starts(jd, layers, bdur, dur=None):
    """Give every --layer its start. (name, file, None) means no @START was given: a full-length layer starts at 0;
    a short graphic takes its start from her page (looks.json, by the layer's name or its file's name) when it is
    there. A short one with no start anywhere still goes in at 0, and is named in one plain line, because a stack
    of short graphics all at 0 shows every one of them at once (ISS-12). Returns (layers, note or None)."""
    dur = dur or _dur
    starts, unknown, found = None, [], []
    out = []
    for nm, fp, at in layers:
        if at is None:
            at = 0.0
            ldur = dur(fp)
            if 0 < ldur < bdur - SHORT_BY:
                if starts is None:
                    starts = page_starts(jd)
                stem = os.path.splitext(os.path.basename(fp))[0]
                hit = starts.get(nm, starts.get(stem))
                if hit is not None:
                    at = hit
                    found.append(f"{nm} at {at:.2f}s")
                else:
                    unknown.append(nm)
        out.append((nm, fp, at))
    if found:
        print(f"  · start taken from your page: {', '.join(found)}")
    note = None
    if unknown:
        who = unknown[0] if len(unknown) == 1 else ", ".join(unknown[:-1]) + " and " + unknown[-1]
        note = (f"  · {who} {'is a short graphic' if len(unknown) == 1 else 'are short graphics'} with no start time, "
                f"so {'it starts' if len(unknown) == 1 else 'they all start'} at the top of your reel. Drag "
                f"{'it' if len(unknown) == 1 else 'each one'} to its moment in CapCut, or hand "
                f"{'it' if len(unknown) == 1 else 'them'} over again as --layer NAME=FILE@SECONDS.")
        print(note)
    return out, note


def newest(pattern):
    hits = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--base", default=None, help="the clean footage cut (default: outputs/<JOB>.mp4)")
    ap.add_argument("--overlay", default=None, help="the transparent graphics .mov (default: newest in renders/)")
    ap.add_argument("--layer", action="append", default=[], metavar="NAME=FILE[@START]",
                    help="an EXTRA named overlay track, repeatable, laid bottom-to-top in the order given "
                         "(e.g. --layer screens=build/screens.mov --layer captions=build/caps.mov). "
                         "Use this when she wants each KIND of element on its own layer instead of one "
                         "flattened graphics track, so she can move, retime or switch off captions "
                         "without touching the hook. With --layer, --overlay is optional. "
                         "Append @SECONDS for a layer that starts part-way through (e.g. "
                         "--layer crossout=build/crossout.mov@11.0) - a short element belongs at its "
                         "own time on a full-length track, not padded out with transparent video. "
                         "A short layer given no @SECONDS takes its start from her page (review/looks.json); "
                         "with none there it goes in at 0 and is named in one line.")
    ap.add_argument("--name", default=None, help="draft name (default: <JOB>)")
    ap.add_argument("--no-overlay", action="store_true",
                    help="the layers given are all of it: never reach for an old render (a reel finished from the page)")
    ap.add_argument("--pack", default=None, help="style pack (default: read off the overlay's name)")
    ap.add_argument("--one-clip", action="store_true",
                    help="lay the cut as ONE main-track clip instead of one clip per kept line (the default)")
    ap.add_argument("--grade", default=None,
                    help="her Filter, baked into the footage after her last clip too (the --base copy already has it)")
    ap.add_argument("--punch", action="store_true",
                    help="lay the caption plan's punch-in windows as zoomed pieces of the main track, held on "
                         "her face (separate_layers.sh passes it: the medium route's punch-ins live nowhere else)")
    a = ap.parse_args()

    jd = os.path.join(ROOT, "projects", a.job)
    if not os.path.isdir(jd):
        sys.exit(f"  ⛔ no job at {jd}")
    base = a.base or os.path.join(jd, "outputs", f"{a.job}.mp4")
    # VectCut stages media by the path it is handed, so a relative one silently stages nothing and the
    # build only fails later, at finalize, naming a missing asset instead of the path that was wrong.
    base = os.path.abspath(base if os.path.isabs(base) else
                           (base if os.path.exists(base) else os.path.join(jd, base)))
    # With --layer the layers ARE the graphics. Reaching for the newest render as well laid the whole flattened
    # overlay on top of them, so every separated element showed twice. --overlay still adds one on purpose.
    overlay = a.overlay or (None if (a.layer or a.no_overlay) else newest(os.path.join(jd, "renders", "*.mov")))
    if overlay:
        overlay = os.path.abspath(overlay if os.path.isabs(overlay) else
                                  (overlay if os.path.exists(overlay) else os.path.join(jd, overlay)))
    if not os.path.exists(base):
        sys.exit(f"  ⛔ no footage cut at {base} — well-done builds one before it bakes; run the build first.")
    layers = []
    for spec in a.layer:
        if "=" not in spec:
            sys.exit(f"  ⛔ --layer wants NAME=FILE, got {spec!r}")
        nm, _, rest = spec.partition("=")
        fp, at = rest, None                                  # None: no @START given (place_starts decides, below)
        if "@" in rest:
            fp, _, at_s = rest.rpartition("@")
            try:
                at = float(at_s)
            except ValueError:
                sys.exit(f"  ⛔ layer {nm!r}: {at_s!r} is not a start time in seconds")
        fp = fp if os.path.isabs(fp) else os.path.join(jd, fp)
        if not os.path.exists(fp):
            sys.exit(f"  ⛔ layer {nm!r}: no file at {fp}")
        layers.append((nm.strip(), os.path.abspath(fp), at))
    # Finish with every look off (or none yet: Filter and Cover a face work before any look exists) passes
    # --no-overlay and no layers: her cut alone is the draft. Only a bare call with nothing to lay refuses.
    if not overlay and not layers and not a.no_overlay:
        sys.exit(f"  ⛔ no rendered overlay in {jd}/renders/ — nothing to lay over the footage.")

    # CapCut must be quit BEFORE anything is written, or its next save wipes the draft.
    import draft_safety
    draft_safety.require_capcut_quit("hand this reel over to CapCut")
    name = draft_safety.next_version(draft_safety.base_of(a.name or a.job))

    bdur = _dur(base)
    odur = _dur(overlay) if overlay else 0.0
    # A zero duration means ffprobe could not read the file. Building on it produces an empty draft
    # that reports success — refuse instead, and name the file that could not be read.
    checks = [("footage", base, bdur)]
    if overlay:
        checks.append(("graphics", overlay, odur))
    checks += [(nm, fp, _dur(fp)) for nm, fp, _at in layers]
    for label, f, d in checks:
        if d <= 0:
            sys.exit(f"  \u26d4 could not read the {label} file's length: {f}\n"
                     f"     It may be corrupt or still being written. Nothing was created.")
    layers, _ = place_starts(jd, layers, bdur)           # a short graphic is never silently stacked at 0 (ISS-12)
    print(f"  footage : {os.path.relpath(base, ROOT)}  ({bdur:.1f}s)")
    if overlay:
        print(f"  graphics: {os.path.relpath(overlay, ROOT)}  ({odur:.1f}s)")
    for nm, fp, at in layers:
        when = f"  @ {at:.2f}s" if at else ""
        print(f"  {nm:<16}: {os.path.relpath(fp, ROOT)}  ({_dur(fp):.1f}s){when}")

    # The overlay and every --layer are rendered with STRAIGHT alpha, which is what CapCut reads, so they go in
    # as they are. finalize() still passes each transparent clip through capcut_media.ensure_shippable
    # (fresh=True), which converts a WebM (CapCut drops its alpha) to ProRes; the renders here stay untouched.
    import frame
    _cw, _ch = frame.size(jd)                                 # a wide video gets a wide draft
    os.environ.update(frame.env(jd))
    did = call("create_draft", name=name, width=_cw, height=_ch)["draft_id"]
    pieces = footage_pieces(jd, base, bdur) if a.punch else [(0.0, bdur, 1.0, 0.0, 0.0)]
    pts = [] if a.one_clip else slice_points(jd, bdur)
    if pts:
        pieces = split_at(pieces, pts)
        print(f"  main track: {len(pts) + 1} clips, one per kept line of your cut")
    # Her clips are cut from a copy of her cut with her own footage after the last line (capcut_tail.py), so the last
    # clip can be dragged longer like every other one. Same times: the extra footage plays only if she extends it.
    # The Finish tab's bar (a no-op from the chat): the tail, each layer's CapCut copy, then the draft, each its share
    import export_progress, render_spans, capcut_alpha
    # A caption layer rendered in stretches goes in as one clip per stretch (its sidecar's parts), each prepared for
    # CapCut on its own and cached: a caption edit re-prepares only the stretch it changed.
    _parts = {nm: render_spans.parts(fp) for nm, fp, _a in layers}
    def _alpha_of(nm, fp):
        if _parts.get(nm):
            return sum(export_progress.alpha_cost(d) for pf, _pa, d in _parts[nm] if not capcut_alpha.ready(pf))
        return export_progress.alpha_cost(_dur(fp))
    _alpha = [(nm, _alpha_of(nm, fp)) for nm, fp, _a in layers] + ([("graphics", export_progress.alpha_cost(odur))] if overlay else [])
    _c = [export_progress.tail_cost(jd, bdur, export_progress.cut_cost(jd)[2]), sum(c for _n, c in _alpha), 15.0]
    _tot = sum(_c) or 1.0
    _e = [sum(_c[:i]) / _tot for i in range(4)]
    export_progress.window(_e[0], _e[1]); export_progress.stage(0, 1, "adding your footage after the last clip")
    _at = [_e[1]]
    def _prep(nm):                                         # this layer's stretch of the bar, before its CapCut copy
        c = next((c for n, c in _alpha if n == nm), 0.0)
        hi = _at[0] + (_e[2] - _e[1]) * (c / (_c[1] or 1.0))
        export_progress.window(_at[0], hi); export_progress.stage(0, 1, "getting your captions ready for CapCut" if nm.startswith("cap") else "getting your looks ready for CapCut")
        _at[0] = hi
    import capcut_tail
    clips_from, tail = capcut_tail.tailed_base(jd, base, bdur, a.grade)
    import sound_plan
    muted = sound_plan.voice_muted(jd)                        # she muted her clip (review/sound.json): main track silent
    if muted:
        print("  main track: muted, as you asked (your clip's own sound is off)")
    for s, e, sc, x, y in pieces:
        call("add_video", draft_id=did, video_url=clips_from, start=s, end=e, target_start=s, track_name="main",
             scale_x=sc, scale_y=sc, transform_x=x, transform_y=y, volume=0.0 if muted else 1.0)
    # Nothing outlasts her footage: a layer rendered a beat longer than the cut (captions run to their own end)
    # left CapCut playing black after her last clip. Every overlay ends with the main track, at most.
    def fits(at, length):
        return max(0.0, min(length, bdur - at))
    import capcut_alpha                      # every layer's faint edges cleaned on the way in: no rainbow ring in CapCut
    if overlay and fits(0, odur) > 0.02:
        _prep("graphics")
        call("add_video", draft_id=did, video_url=capcut_alpha.for_capcut(overlay), start=0, end=fits(0, odur),
             target_start=0, track_name="graphics")
    # Extra layers stack in the order given, so the caller controls what sits over what.
    for nm, fp, at in layers:
        if fits(at, _dur(fp)) <= 0.02:
            print(f"  · {nm} starts after your footage ends, so it isn't laid in")
            continue
        _prep(nm)
        if _parts.get(nm):
            lo, hi = export_progress._WIN
            todo = [(pf, d) for pf, _pa, d in _parts[nm] if not capcut_alpha.ready(pf)]
            tot, done = sum(d for _pf, d in todo) or 1.0, 0.0
            if len(todo) < len(_parts[nm]):
                print(f"  · {nm}: {len(_parts[nm]) - len(todo)} of {len(_parts[nm])} stretches already ready for CapCut")
            for pf, t0, d in stretch_spots(at, _parts[nm], fits):   # whole microseconds, never overlapping
                if d <= 0.02:
                    continue
                if not capcut_alpha.ready(pf):              # this stretch's own share of the layer's bar
                    export_progress.window(lo + (hi - lo) * done / tot, lo + (hi - lo) * (done + d) / tot)
                    export_progress.stage(0, 1, "getting your captions ready for CapCut")
                    done += d
                call("add_video", draft_id=did, video_url=capcut_alpha.for_capcut(pf), start=0, end=d,
                     target_start=t0, track_name=nm)
            continue
        call("add_video", draft_id=did, video_url=capcut_alpha.for_capcut(fp), start=0, end=fits(at, _dur(fp)),
             target_start=at, track_name=nm)

    export_progress.window(_e[2], 1.0); export_progress.stage(0, 1, "writing your draft")
    # Sound cues as INDIVIDUAL clips. The tester's package glued every cue into one wav and she could not
    # move, swap or lower a single one — the thing she most wanted to adjust was the thing most welded shut.
    plan_p = os.path.join(jd, "caption-plan.json")
    cues = 0
    sfx_lanes = []          # per-track "free from" time, so overlapping cues get their own lane
    bed = None
    import sound_plan
    # A reel finished from the visual editor may have no caption plan at all: its Sound tab (review/sound.json) is
    # the plan. Skipping sound whenever caption-plan.json was missing dropped every one of her cues, silently.
    if os.path.exists(plan_p) or os.path.isfile(sound_plan.sound_json(jd)):
        try:
            plan = json.load(open(plan_p, encoding="utf-8")) if os.path.exists(plan_p) else {}
        except ValueError:
            plan = {}
        import capcut_sfx, audio_levels
        pal = capcut_sfx.palette()          # the buyer's own sfx/ folder, then the bundled library
        sfx_dir = os.path.join(jd, "sfx")
        # The cues the same way the MP4 export reads them (caption-plan.json, else sfx-plan.json), then her Sound
        # edits over them: a cue she switched off is left out, a swapped one plays her pick, the sounds on her looks
        # and the ones she added come along, and the music bed follows her on/off, song and level.
        _src, entries, tkey, music0 = sound_plan.base(jd)
        plan_sfx, plan_music = sound_plan.for_build(jd, [dict(e, at=e.get(tkey, e.get("at", e.get("t", 0)))) for e in entries],
                                                    music0)
        # Every cue lands at the level the finished video gives it (the shared audio_levels rule: measured, its
        # peak a fixed distance under the cut's), so her CapCut project sounds like the reel she approved.
        prog_peak = audio_levels.peak_dbfs(base)
        for s in plan_sfx:
            ref = s["file"]
            # Same resolution order the bake uses (build-reel-mp4.resolve_sfx): an absolute path, then the
            # job's own sfx/ folder, then the shared palette by cue NAME. A cue in a plan is usually a name
            # like "whoosh-short", not a file — looking only for a file finds nothing and drops every cue.
            f = (ref if os.path.isabs(ref) and os.path.exists(ref) else None)
            # a plan may name a cue WITHOUT its extension (the mixer appends one), and the job's
            # levelled copies live in sfx/norm - look for both before falling back to the palette,
            # or every one of the job's own sounds is silently skipped.
            if not f:
                for d in (os.path.join(sfx_dir, "norm"), sfx_dir):
                    for cand in (ref, ref + ".wav", ref + ".mp3"):
                        p = os.path.join(d, cand)
                        if os.path.exists(p):
                            f = p
                            break
                    if f:
                        break
            if not f:
                # resolve_cue returns (path, stem, ext) or None; only the path is wanted here.
                f = pal.get(os.path.splitext(os.path.basename(ref))[0]) or (capcut_sfx.resolve_cue(ref, pal) or (None,))[0]
            if not f or not os.path.exists(f):
                print(f"  · cue skipped (no sound file for it): {ref}")
                continue
            d = _dur(f)
            if d <= 0:
                continue
            src_f = f                                            # leveled from the ORIGINAL over its played stretch,
            tr = float(s.get("trim") or 0)                       # exactly as the MP4 and the preview measure it
            if 0 < tr < d - 0.05:
                # The page and the MP4 play a cue only as long as its motion, fading out over its last 0.12 s. CapCut
                # gets that same sound as its own short clip (one file per length, written once, never rewritten:
                # a draft may already link it), so her CapCut reel sounds like the one she approved.
                cut = os.path.join(sfx_dir, "capcut", f"{os.path.splitext(os.path.basename(f))[0][:60]}-{tr:.2f}s.wav")
                if not os.path.isfile(cut):
                    os.makedirs(os.path.dirname(cut), exist_ok=True)
                    tmp = cut + ".tmp.wav"
                    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-map", "0:a:0?", "-af",
                                        f"atrim=0:{tr:.3f},afade=t=out:st={max(0.0, tr - 0.12):.3f}:d=0.12", tmp],
                                       capture_output=True, text=True)
                    if r.returncode == 0 and os.path.isfile(tmp):
                        os.replace(tmp, cut)
                if os.path.isfile(cut):
                    f, d = cut, _dur(cut) or tr
            vol = (audio_levels.to_linear(s["gain_db"]) if "gain_db" in s
                   else audio_levels.sfx_volume_for(src_f, base, s.get("trim"),          # the north star: under her
                                                    float(plan.get("sfx_duck_db", audio_levels.SFX_DUCK_DB))))   # voice, by loudness
            # CapCut refuses two clips that overlap on ONE track, and a dense sound design has
            # cues within a few frames of each other. Lay each cue on the first sfx track that is
            # free at that moment, so nothing has to be nudged off its beat to fit.
            at = float(s.get("at", 0))
            if at >= bdur - 0.02:                       # a cue after her footage ends would play over black
                continue
            d = min(d, bdur - at)
            lane = next((i for i, free_at in enumerate(sfx_lanes) if at >= free_at), len(sfx_lanes))
            if lane == len(sfx_lanes):
                sfx_lanes.append(0.0)
            sfx_lanes[lane] = at + d + 0.02
            call("add_audio", draft_id=did, audio_url=f, start=0, end=d,
                 target_start=at, volume=vol,
                 track_name="sfx" if lane == 0 else f"sfx{lane+1}")
            cues += 1
        # The music bed, when the plan (or her Sound edits) has one: its own track, at the bake's level.
        if isinstance(plan_music, dict) and plan_music.get("file"):
            mf = plan_music["file"] if os.path.isabs(plan_music["file"]) else os.path.join(jd, "audio", plan_music["file"])
            mdur = _dur(mf) if os.path.exists(mf) else 0.0
            if mdur > 0:
                at = float(plan_music.get("at", 0) or 0)
                length = max(0.1, min(mdur, bdur - at))
                gain = (float(plan_music["gain_db"]) if "gain_db" in plan_music
                        else audio_levels.bed_gain_for(mf, base, plan.get("music_duck_db")))
                want = max(0.1, bdur - at)                       # a song shorter than the reel loops, so the bed never stops
                pos, k = at, 0
                while pos < at + want - 0.05 and k < 50:
                    piece = min(mdur, at + want - pos)
                    call("add_audio", draft_id=did, audio_url=os.path.abspath(mf), start=0, end=piece,
                         target_start=pos, volume=audio_levels.to_linear(gain), track_name="music")
                    pos += piece; k += 1
                bed = os.path.basename(mf)
                print(f"  music   : {bed}  in at {at:.2f}s  gain {gain:+.1f} dB")
            else:
                print(f"  · music bed skipped (no file at {mf})")

    # REGISTER through the engine's own finalize, never a bare save_draft. VectCut writes the draft into a
    # folder named after its internal id and bakes THAT path into every asset reference, so a draft that is
    # merely saved lands as "dfd_cat_1789687033_b9f51556" and is not the project she was told to open.
    # finalize() does the save, the rename, the raw-text asset-path rewrite (including the Windows
    # backslash form), the never-overwrite fail-safe and the build record. There is no text in this draft,
    # so the font map is empty; the fallback is required and unused.
    # No baked camera moves in a handover draft: the footage track is the whole point of giving it to her.
    os.environ["REEL_NO_DEFAULT_MOTION"] = "1"
    import cleanyap, packbuild
    # finalize() needs a pack because it will not default a font — a shipped reel never reaches for a
    # personal one. There is no text in THIS draft, so the font is genuinely unused, but the rule still
    # holds and guessing would be the wrong habit. Read the pack off the render she already has.
    pack = a.pack or os.environ.get("STYLE_PACK")
    if not pack:
        # read it off whatever rendered file this draft was built from - with --layer there may be no
        # single "overlay", so look across every layer name too rather than crashing on None.
        for cand in ([overlay] if overlay else []) + [fp for _, fp, _a in layers]:
            low = os.path.basename(cand).lower()
            pack = next((n for n in packbuild.names() if n.lower() in low), None)
            if pack:
                break
    if not pack:
        sys.exit("  ⛔ cannot tell which style pack this reel used. Pass --pack "
                 + " | ".join(packbuild.names()))
    print(f"  pack    : {pack}")
    # job=: the face check reads THIS job's measurement. Without it finalize had only the CapCut draft folder to
    # search from, found none, and reported a measured job as "never measured" (so it never checked).
    cleanyap._CUT_END = bdur                       # her logo (when she turned one on) runs the whole reel
    name = cleanyap.finalize(did, name, {}, fallback_font=cleanyap.hook_font(pack), job=jd) or name
    _label_clips(name, [(nm, fp, at) for nm, fp, at in layers if nm.startswith("cut out")])
    print(f"\n  ✅ CapCut project ready: {name}")
    if layers:
        print(f"     footage on the main track; "
              + ", ".join(nm for nm, _f, _a in layers) + f" each on its own track; "
              + f"{cues} sound cue(s) on their own clips.")
    else:
        print(f"     footage on the main track, the graphics over it, {cues} sound cue(s) on their own clips.")
    if sfx_lanes and len(sfx_lanes) > 1:
        print(f"     sound spread over {len(sfx_lanes)} tracks so overlapping cues keep their timing.")
    if bed:
        print(f"     the music bed ({bed}) on its own track.")
    print(f"     Open CapCut and it is at the top of your projects.")
    print(f"     Your finished video is already done — this is only here if you want to change something")
    print(f"     yourself (your own zooms on the footage clip). If you do change it, export it from CapCut.")


def _label_clips(name, layers):
    """Name each of these layers' clips in CapCut (the name CapCut shows on a clip is its material name; VectCut
    copies every overlay in as video_<id>.mp4, so without this a cut-out reads as a number). Matched by where the
    clip starts and the file's size. You: "label all the cutout layers in CapCut as cut out"."""
    if not layers:
        return
    import capcut_alpha, draft_safety
    dd = draft_safety._draft_dir(name)
    if not dd:
        return
    want = []
    for nm, fp, at in layers:
        try:
            want.append((nm, os.path.getsize(capcut_alpha.for_capcut(fp)), float(at)))
        except OSError:
            pass
    n = 0
    for path in draft_safety.draft_json_copies(dd, require=False):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        vids = {m["id"]: m for m in d.get("materials", {}).get("videos", [])}
        n = 0
        for t in d.get("tracks", []):
            for sg in t.get("segments", []):
                m = vids.get(sg.get("material_id"))
                if not m:
                    continue
                f = m.get("path", "")
                f = f if os.path.isabs(f) else os.path.join(dd, f.split("##/", 1)[-1])
                try:
                    size = os.path.getsize(f)
                except OSError:
                    continue
                st = sg.get("target_timerange", {}).get("start", 0) / 1e6
                for nm, sz, at in want:
                    if sz == size and abs(st - at) < 0.05:
                        m["material_name"] = nm; n += 1
                        break
        json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    if n:
        print(f"  · {n} cut-out clip(s) named \"cut out\" in CapCut")


if __name__ == "__main__":
    main()
