# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""
subject-zones.py: the box a talking-head subject occupies in a take, and the open bands of frame around her.

In reel-layout-rules terms this is the measured subject band that Layer 1 places against. Layer 2 is
product/safe_zones.py, the platform's own UI strip: one fixed band, identical on every reel. The subject is
different on every shoot and every framing, so it has to be read off the footage. A spot is usable only when
it clears both, which is why every band below comes back already cut down to the Layer 2 band.

What it came out of: hooks landed on a creator's forehead while the top quarter of her frame was empty wall,
after she had asked more than once for that to stop. Remembering was never the problem. Placements were typed
by hand (transform_y 0.60, 0.62, 0.74 on different jobs), each carried over from the reel before. CapCut's
transform_y is (960 - y_px) / 960, which puts 0.60 at y384: clear of a subject framed low, on the forehead of
one framed high. With nothing reading where her head actually was, nothing could tell those two cases apart.

HOW IT READS HER. Frames are sampled across the whole window and each edge keeps its worst value, because a
spot that is clear on a typical frame and covered on her most animated one is not clear.

  head top     where her hair really starts, read against the room (head_framing.crown_rows): she moves and
               the room does not. YuNet's face box begins at the brow, and placing against it parks type in her
               hair. The middle reading wins (where her hair usually is). If the hair can't be read (a hood, a hat, low contrast), the
               face-box top stands in and head_top_source says so.
               A phone that drifts is laid back in place first, so window blinds or a door frame behind her are
               not read as her hair. Stills from another shot inside the window (a punch-in, a cut to another
               take) show a different room: they are left out of the hair search and covered by their own face
               box plus the hair allowance below, and head_top_source says so.
               A handheld selfie's room swings past her and cannot be compared (head_framing.room_unsteady checks
               the room beside her head first): the head top is then the face box's top less a measured hair
               allowance (HANDHELD_HAIR of its height), and head_top_source says that too.
  chin bottom  where her jaw usually is (the middle reading).
  left/right   where the face box usually sits, each side pushed out by EAR_SHARE of the median box width for
               the ears and the hair beside her cheeks, which the box leaves out (measured on her own takes).

WHAT IT RETURNS
  subject      her box, in source px (subject_src_px) and in 1080x1920 authoring px (subject)
  zones        four open bands in authoring px, each CLEARANCE clear of her and inside the Layer 2 band:
                 above   safe_zones.TOP           -> head_top - CLEARANCE
                 below   chin_bottom + CLEARANCE  -> safe_zones.BOTTOM
                 left    safe_zones.LEFT          -> head_left - CLEARANCE
                 right   head_right + CLEARANCE   -> safe_zones.RIGHT
               above and below also carry center_y_norm, the CapCut transform_y of their centre, so a builder
               receives the number instead of choosing one. The side bands report x0/x1, and roomier_side
               names the wider of the two.
  reading      what the numbers were read from: the source size, the stretch of footage (and the cuts.json
               it was read through, if any), how many frames showed her, and the clearance and ear allowance.

A band too small for one legible line comes back `usable: false` with the reason written out. That is a fact
about her framing rather than an error, and it is reported as one.

Usage:
  uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4
      her box and the zones around her, kept with the job in subject-zones.json
  uv run workflows/subject-zones.py <video> --range 4.3,6.1
      reads only one graphic's time on screen, the fair window when she moves around during a reel
  uv run workflows/subject-zones.py <raw> --cuts projects/<job>/transcript/cuts.json --range 12.0,15.5
      the range is in seconds of the cut; each moment is found in the raw through cuts.json
  --json prints the whole answer as JSON, --out FILE saves it there, and --annotate OUT.PNG draws her box and
  the open bands on one of the frames it read.
"""
import argparse, importlib.util, json, os, statistics, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))

# head-framing.py has a hyphen, which is not a valid module name, so it is loaded by path: its stills, its face
# detector and its crown search are the ones used here, and one correction to that file lands in both tools.
_spec = importlib.util.spec_from_file_location("head_framing", os.path.join(HERE, "head-framing.py"))
head_framing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(head_framing)

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "product"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "product"))
import frame; frame.adopt()            # a wide clip is measured on the wide frame
import safe_zones                      # Layer 2, the platform UI band: one source, cut into every zone

# The air every open zone keeps from her, in authoring px: one caption line at the engine's legibility floor
# (safe_zones.MIN_PX["caption"]), the smallest type that ever goes on a reel, so the nearest letters sit at
# least a line of their own height away from her.
CLEARANCE = safe_zones.MIN_PX["caption"]
# Her ears and the hair beside her cheeks reach past the face box on each side, by this share of the box's
# width: enough for 9 in 10 of her own takes (dev-tools/screen/DERIVATION.md).
EAR_SHARE = 0.27
# Stills read across a whole take. Every edge here is the middle reading over them (where she usually is; the
# worst case made a box far bigger than her face). The count below was set when it was the worst case, so it is only as good as the stills
# it sees: on the median one of her cuts it takes 26 stills to catch, 19 times in 20, one where she comes within the
# clearance of her furthest reach on her rarest edge (dev-tools/framing/DERIVATION.md). 31 is a still every 1/32 of
# the take: past 26, and the stills the earlier 16-still reading took (the middle of each sixteenth, the odd 32nds)
# are all among them, so a saved reading can only widen when it is measured again, never narrow.
SAMPLES = 31

# A zone is only "usable" if TEXT could legibly go in it. Any positive number would technically be a gap,
# but reporting a 40px band as usable hands a caller a centre line and lets a legible line spill straight
# back onto her — the defect this tool exists to prevent, arrived at politely.
MIN_TALL = safe_zones.MIN_PX["caption"]   # one legible line (58px at 1080x1920)
MIN_WIDE = MIN_TALL * 3                   # a side zone narrower than a few characters cannot hold copy


# Within one framing she leans in or sits back by a fraction of her face, never by this much: a face box past
# SIZE_SPREAD times her typical height (or under 1/SIZE_SPREAD of it) in a still that shows the same room is not
# her. It is a false detection, and kept, one such still made a buyer's measured head run from y456 to y1748
# (her forearms; her real chin sat at about y1120), so every graphic was squeezed into 128px above her and the
# guard refused layers that were clear of her. A still from another shot (a punch-in, a cut to a wider or closer
# take) is different: there her face really is a different size, and its own box stays in the worst case.
SIZE_SPREAD = 1.6


def _say(line):
    print(f"[subject-zones] {line}")


def leave_out_false_faces(imgs, per_still):
    """per_still with the impossible boxes taken out (set to None), and a list of (index, box, why) for each one
    taken out, so the report can name them. Only a still that shows the same room as the rest can be judged;
    when the room cannot be compared at all (a handheld take), nothing is taken out."""
    heights = [b[3] for b in per_still if b is not None]
    if len(heights) < 3:
        return per_still, []
    mid = statistics.median(heights)
    odd = [i for i, b in enumerate(per_still)
           if b is not None and not (mid / SIZE_SPREAD <= b[3] <= mid * SIZE_SPREAD)]
    if not odd:
        return per_still, []
    usual = [b for i, b in enumerate(per_still) if b is not None and i not in odd]
    try:
        look = head_framing._look(imgs, head_framing.typical_face(usual))
    except Exception:
        return per_still, []
    if look["unsteady"]:
        return per_still, []
    kept, gone = list(per_still), []
    for i in odd:
        if look["apart"][i] is None:
            continue            # another shot: her face really is that size there
        b = per_still[i]
        kept[i] = None
        gone.append((i, b, f"a face box {b[3] / mid:.1f}x her usual height in the same framing: a false detection"))
    return kept, gone


# ---------------------------------------------------------------------------------------------- the cut's clock
def _kept_spans(cuts_path):
    """cuts.json's kept spans, in order, as (raw start, raw end): the cut's timeline is these laid end to end."""
    with open(cuts_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    spans = doc.get("segments") if isinstance(doc, dict) else doc
    return [(float(sp["start"]), float(sp["end"])) for sp in spans]


def timeline_length(cuts_path):
    """How long the cut runs: its kept spans added up."""
    return sum(b - a for a, b in _kept_spans(cuts_path))


def timeline_to_raw(cuts_path, moments):
    """Each moment on the cut's timeline -> the same moment in the raw footage, or None past the cut's end."""
    import bisect
    spans = _kept_spans(cuts_path)
    opens, clock = [], 0.0                # where each kept span starts on the timeline
    for a, b in spans:
        opens.append(clock)
        clock += b - a
    found = []
    for t in moments:
        i = bisect.bisect_right(opens, t) - 1
        inside = i >= 0 and t < opens[i] + (spans[i][1] - spans[i][0])
        found.append(spans[i][0] + (t - opens[i]) if inside else None)
    return found


def _frames_on_timeline(video, size, t0, t1, cuts_path, n):
    """n stills of the raw at n evenly spread moments of a stretch of the cut (the same spread head-framing's
    stills use), each found in the raw through cuts.json. A moment past the cut's end is skipped."""
    w, h, _sec = size
    moments = [t0 + (t1 - t0) * (k + 1) / (n + 1) for k in range(n)]
    got = (head_framing.still_at(video, at, w, h) for at in timeline_to_raw(cuts_path, moments) if at is not None)
    return [s for s in got if s is not None]


# ---------------------------------------------------------------------------------------------- the zones
def _zone(name, top, bottom, h, need=None, axis="y"):
    """One open band, honestly reported. `need` = px required before it counts as usable."""
    need = need if need is not None else (MIN_TALL if axis == "y" else MIN_WIDE)
    room = int(round(bottom - top))
    z = {"top": int(round(top)), "bottom": int(round(bottom)), "room_px": room,
         "center_px": int(round((top + bottom) / 2))}
    z["center_y_norm"] = round((h / 2 - z["center_px"]) / (h / 2), 4)
    z["usable"] = room >= need
    if not z["usable"]:
        dim = "tall" if axis == "y" else "wide"
        z["why"] = (f"only {max(room, 0)}px {dim} — her framing leaves no usable room {name} her once the "
                    f"{CLEARANCE}px of clear air and the platform band are both honoured "
                    f"(needs {need}px for legible text)")
    return z


def open_zones(head_top, chin_bottom, left, right):
    """The four bands around her box (1080x1920 px), each CLEARANCE clear of her and inside the platform band."""
    zones = {
        "above": _zone("above", safe_zones.TOP,             head_top - CLEARANCE, safe_zones.H),
        "below": _zone("below", chin_bottom + CLEARANCE,    safe_zones.BOTTOM,    safe_zones.H),
    }
    # The side zones constrain X, so they carry x-shaped keys. Reusing `top`/`bottom` for horizontal bounds
    # reads fine in a print and lies to every consumer that reads the JSON.
    lz = _zone("left of",  safe_zones.LEFT, left - CLEARANCE, safe_zones.H, axis="x")
    rz = _zone("right of", right + CLEARANCE, safe_zones.RIGHT, safe_zones.H, axis="x")
    for z in (lz, rz):
        z["x0"], z["x1"] = z.pop("top"), z.pop("bottom")
        z["center_x_px"] = z.pop("center_px")
        z.pop("center_y_norm")
    zones["left"], zones["right"] = lz, rz
    return zones


def read_her(imgs, per_still):
    """Where her head USUALLY is across these stills (the middle reading on every edge, never the furthest she
    ever leaned), in the stills' px -> {head_top, chin_bottom, left, right, face_top, ear, source}. `per_still` is
    head_framing.box_per_still(imgs). The furthest-reach box was far bigger than her face (every lean and nod
    added up, plus margins) and flagged looks that were nowhere near her; she sees her footage, so the engine
    guesses where she is and she has the last word."""
    boxes = [b for b in per_still if b is not None]
    med = statistics.median
    face_top = med(y for x, y, bw, bh in boxes)                    # where her forehead usually is
    chin_bottom = med(y + bh for x, y, bw, bh in boxes)            # where her jaw usually is
    ear = round(EAR_SHARE * med(bw for x, y, bw, bh in boxes))
    head_left = med(x for x, y, bw, bh in boxes) - ear
    head_right = med(x + bw for x, y, bw, bh in boxes) + ear
    # The crown window hangs off where her forehead usually is, sized by her typical face.
    face = head_framing.typical_face(boxes)._replace(top=face_top)

    # The TRUE hair top, not the forehead. YuNet's box starts at the brow, so placing to it puts type in
    # her hair and reads exactly like the defect this tool exists to stop.
    hair_src = "hair (read against the room)"
    handheld, unread = False, []
    try:
        tops = head_framing.crown_rows(imgs, face)
        # The middle crown read, lifted by a small margin: the stretch that marks a row as her head starts a
        # little below the very top of her hair.
        head_top = statistics.median(tops) - head_framing.CROWN_MARGIN * face.h if tops else None
        handheld = not tops and head_framing.room_unsteady(imgs, face)
        unread = head_framing.unread_stills(imgs, face) if tops else []
    except Exception:
        head_top = None
    if head_top is not None and unread:
        hair_src += f"; {len(unread)} frame{'s' if len(unread) > 1 else ''} it could not read left out"
    if head_top is None and handheld:
        # The room moves with the phone, so it cannot be compared: her hair starts a measured share of the
        # face box above its top, the middle reading over the take like every other edge here.
        head_top = statistics.median(y - head_framing.HANDHELD_HAIR * bh for x, y, bw, bh in boxes)
        hair_src = "face box + hair allowance (handheld: the room moves with the phone)"
    elif head_top is None:
        head_top, hair_src = face_top, "face box (hair unmeasurable: hood, hat, or low contrast)"
    return {"head_top": head_top, "chin_bottom": chin_bottom, "left": head_left, "right": head_right,
            "face_top": face_top, "ear": ear, "source": hair_src}


def measure(video, t0=0.0, t1=None, cuts=None, samples=SAMPLES, annotate=None, out=None):
    # Only a measurement of the WHOLE cut may stand as the job's subject-zones.json, which subject_guard and
    # every placement read as "where she is across the reel". One graphic's window (--range) or a raw read
    # through --cuts answers a narrower question and must never overwrite it.
    whole_reel = not cuts and float(t0) == 0.0 and t1 is None
    size = head_framing.shown_size(video)
    w, h, dur = size
    # ASPECT GUARD, FIRST — before any sampling or detection. ONE scale factor maps source px onto the
    # 1080x1920 authoring frame only when the source shares that aspect. A 16:9 raw does not: it gets
    # reframed/cropped to 9:16 later, so no fixed scale maps a y in the raw onto a y in the finished reel,
    # and a number derived by scaling width would be confidently wrong. It runs here rather than after the
    # measurement so the answer is the real reason, delivered in a second instead of after a 30s sweep that
    # would then fail on "no face" and send someone hunting the wrong problem.
    if abs(safe_zones.W / w - safe_zones.H / h) > (0.02 * safe_zones.W / w if safe_zones.LOW_BAND else 1e-3):   # a wide clip may be a hair off 16:9
        sys.exit(f"✗ {w}x{h} is not the 9:16 authoring aspect, so its pixels cannot be mapped onto the "
                 f"1080x1920 frame the graphics are built in (a reframe/crop happens between the two).\n"
                 f"  Measure the finished cut instead: projects/<job>/outputs/<job>.mp4")
    if t1 is None:
        # Read through cuts.json the stretch is in the cut's seconds, and the cut is shorter than the raw it
        # came from, so the raw's length is the wrong end: past the cut's end the moments map to nothing.
        t1 = timeline_length(cuts) if cuts else dur
    else:
        t1 = float(t1) if cuts else min(float(t1), dur)

    imgs = (_frames_on_timeline(video, size, float(t0), t1, cuts, samples) if cuts
            else head_framing.stills(video, size, count=samples, start=t0, end=t1))
    if not imgs:
        sys.exit("could not decode any still in that window — check the path and the times")
    per_still, gone = leave_out_false_faces(imgs, head_framing.box_per_still(imgs))
    boxes = [b for b in per_still if b is not None]
    if len(boxes) < max(2, len(imgs) / 2):
        sys.exit(f"✗ face found in only {len(boxes)}/{len(imgs)} sampled frames — not writing zones from "
                 f"that. Place this one by eye, or re-run over a window where she is actually on camera.")
    her = read_her(imgs, per_still)
    head_top, chin_bottom, head_left, head_right = her["head_top"], her["chin_bottom"], her["left"], her["right"]
    face_top, ear, hair_src = her["face_top"], her["ear"], her["source"]

    k = safe_zones.W / w
    def A(v): return int(round(v * k))

    zones = open_zones(A(head_top), A(chin_bottom), A(head_left), A(head_right))
    roomier = "left" if zones["left"]["room_px"] >= zones["right"]["room_px"] else "right"

    result = {
        "cut": os.path.abspath(video),
        "reading": {"source": {"w": w, "h": h}, "seconds": [round(float(t0), 3), round(float(t1), 3)],
                    "cuts": os.path.abspath(cuts) if cuts else None,
                    "frames": {"with_her": len(boxes), "read": len(imgs)},
                    "clearance_px": CLEARANCE, "ear_allowance_px": ear},
        "head_top_source": hair_src,
        "subject_src_px": {"head_top": int(round(head_top)), "chin_bottom": int(round(chin_bottom)),
                           "left": int(round(head_left)), "right": int(round(head_right)),
                           "face_top": int(round(face_top))},
        "subject": {"head_top": A(head_top), "chin_bottom": A(chin_bottom),
                    "left": A(head_left), "right": A(head_right)},
        # what the "is it on her" checks read (a reel measured before 2026-10-16 keeps its older, wider "subject" for
        # placement, so nothing already placed moves, and gets this tighter box for the checks only)
        "face": {"head_top": A(head_top), "chin_bottom": A(chin_bottom), "left": A(head_left), "right": A(head_right)},
        "zones": zones, "roomier_side": roomier,
        # Stills whose face box could not be her (leave_out_false_faces), each with its box in 1080x1920 px.
        "left_out": [{"still": i + 1, "of": len(imgs),
                      "box": [A(b[0]), A(b[1]), A(b[0] + b[2]), A(b[1] + b[3])], "why": why}
                     for i, b, why in gone],
    }

    _report(result)
    if annotate:
        bands = []
        for name in ("above", "below"):
            b = zones[name]
            if b["usable"]:
                bands.append((name, safe_zones.LEFT / k, b["top"] / k, safe_zones.RIGHT / k, b["bottom"] / k))
        for name in ("left", "right"):
            b = zones[name]
            if b["usable"]:
                bands.append((name, b["x0"] / k, safe_zones.TOP / k, b["x1"] / k, safe_zones.BOTTOM / k))
        s = result["subject_src_px"]
        head_framing.mark_up(imgs[len(imgs) // 2], annotate, her=(s["left"], s["head_top"], s["right"],
                                                                  s["chin_bottom"]),
                             open_bands=bands, tag="subject-zones")

    job = head_framing._job_folder(video)
    if out is None and job is not None and whole_reel:
        out = job / "subject-zones.json"
    if out:
        try:                                                  # measured before the usual-position box (no "face"): what's
            old = json.load(open(out, encoding="utf-8"))      # already placed stays placed; only the checks get the new box
        except Exception:
            old = None
        if isinstance(old, dict) and old.get("subject") and "face" not in old:
            result = dict(result, **{k: old[k] for k in ("subject", "subject_src_px", "zones", "roomier_side") if k in old},
                          face=result["subject"])
            _say("kept this reel's earlier box for placement (nothing already placed moves); the face checks use the new one")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(result, indent=2))
        _say(f"saved {out}")
    return result


def _report(r):
    s, z, rd = r["subject"], r["zones"], r["reading"]
    _say(f"{rd['source']['w']}x{rd['source']['h']}: her face in {rd['frames']['with_her']} of "
         f"{rd['frames']['read']} frames read (numbers below in 1080x1920 reel px)")
    _say(f"her head usually sits y{s['head_top']} to y{s['chin_bottom']}, x{s['left']} to x{s['right']} "
         f"(head top from the {r['head_top_source']}; {rd['ear_allowance_px']}px each side for ears and hair)")
    for g in r.get("left_out") or []:
        _say(f"left out still {g['still']} of {g['of']}: {g['why']} (box y{g['box'][1]} to y{g['box'][3]})")
    _say(f"open zones, each {rd['clearance_px']}px clear of her and inside the platform's safe band:")
    for name in ("above", "below"):
        b = z[name]
        if b["usable"]:
            print(f"  {name:<6} y{b['top']} to y{b['bottom']}, {b['room_px']}px tall; centre y{b['center_px']}, "
                  f"CapCut transform_y {b['center_y_norm']}")
        else:
            print(f"  {name:<6} {b['why']}")
    for name in ("left", "right"):
        b = z[name]
        print(f"  {name:<6} x{b['x0']} to x{b['x1']}, {b['room_px']}px wide" if b["usable"] else f"  {name:<6} {b['why']}")
    if z["left"]["usable"] and z["right"]["usable"]:
        _say(f"the {r['roomier_side']} side has more room")
    if not any(z[n]["usable"] for n in ("above", "below", "left", "right")):
        _say("nothing around her is usable on this framing. That is the framing, not a failure: a graphic "
             "here has to go over her on purpose, or the shot needs re-framing.")


def _range(spec):
    """--range A,B (or A:B) -> (A, B), seconds."""
    a, b = (float(v) for v in spec.replace(":", ",").split(",")[:2])
    return a, b


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Where she is in a 9:16 cut, and the open zones around her.")
    ap.add_argument("cut", help="a 9:16 cut, normally projects/<job>/outputs/<job>.mp4")
    ap.add_argument("--range", metavar="A,B", help="read only these seconds (default: the whole video)")
    ap.add_argument("--cuts", "--edl", dest="cuts", metavar="CUTS.JSON",
                    help="the video is the raw footage: --range is in seconds of the cut, read through this cuts.json")
    ap.add_argument("--from", dest="t0", type=float, help=argparse.SUPPRESS)   # older form of --range, still accepted
    ap.add_argument("--to", dest="t1", type=float, help=argparse.SUPPRESS)
    ap.add_argument("--samples", type=int, default=SAMPLES, help=f"frames to read (default {SAMPLES})")
    ap.add_argument("--json", action="store_true", help="print the whole answer as JSON instead of the summary")
    ap.add_argument("--out", metavar="FILE", help="save the JSON here")
    ap.add_argument("--annotate", metavar="OUT.PNG", help="draw her box and the open zones on a frame")
    a = ap.parse_args()
    t0, t1 = _range(a.range) if a.range else (a.t0 if a.t0 is not None else 0.0, a.t1)
    if a.json:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            r = measure(a.cut, t0, t1, a.cuts, a.samples, a.annotate, a.out)
        print(json.dumps(r, indent=2))
    else:
        measure(a.cut, t0, t1, a.cuts, a.samples, a.annotate, a.out)
