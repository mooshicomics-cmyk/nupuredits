#!/usr/bin/env python3
"""subject_guard.py — prove a graphics layer never lands on HER. Deterministic, no eyeballing.

The subject-relative sibling of the safe-zone check in reel_render.py. That one asks "is this ink inside
the platform's UI band"; this asks "is this ink on her face", and nothing in the engine could answer it
before, because the two live in different files: the overlay renders TRANSPARENT and the footage is not in
the composition, so `hyperframes check` measures a canvas with no person in it and passes text sitting
squarely on a forehead. Every existing check is blind to this by construction. That is why the defect
shipped repeatedly and why "remember not to cover my face" could never hold: nothing was looking.

Method is caption_guard's, pointed at a measured subject box instead of a fixed caption band: alpha-extract
the layer, crop to the box `workflows/subject-zones.py` measured on the real footage, binarize, and read the
covered fraction frame by frame. Spot-checking frames cannot catch this — a hook can clear her head at the
start of its hold and sit on her hair by the end of it, so the whole hold has to be swept.

  python3 product/subject_guard.py <graphics.mov> --zones projects/<job>/subject-zones.json [--max 0.01]
  python3 product/subject_guard.py <graphics.mov> --box 220,316,769,957 [--strict]

Exit 1 on a collision (with --strict, which reel_render passes). A transparent layer that covers nothing is
reported as such and never silently called clean.
"""
import argparse, json, os, re, subprocess, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_zones

DEFAULT_MAX = 0.01     # a face is not a caption band: 1% of the head box is already type ON her


def box_from_zones(path):
    """The measured subject box, in the 1080x1920 authoring frame subject-zones.py already normalises to."""
    z = json.load(open(path, encoding="utf-8"))
    s = z.get("face") or z.get("subject") or {}             # the checks read where her face usually is ("face") when measured
    for k in ("left", "head_top", "right", "chin_bottom"):
        if k not in s:
            raise SystemExit(f"{path} has no measured `subject.{k}` — re-run workflows/subject-zones.py")
    return int(s["left"]), int(s["head_top"]), int(s["right"]), int(s["chin_bottom"])


def coverage(layer, box):
    """-> [(t_seconds, covered_fraction_of_the_box)] for every frame of the layer."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        raise SystemExit(f"degenerate subject box {box} — re-measure with workflows/subject-zones.py")
    # format=gray FIRST: these layers render as 12-bit yuva444p12le, so a raw threshold compares against a
    # 0..4095 range and reads every stray alpha value as solid. Normalise to 8-bit before thresholding.
    # SOLID ink only (alpha >= 128), matching reel_render's safe-zone check: type on this engine's routes
    # carries a drop shadow, and a shadow falling across her is not type on her face. caption_guard uses a
    # far lower threshold on purpose — a shadow bleeding into the caption band IS a defect there. Here it
    # would fire on every shadowed hook and train everyone to ignore the check.
    vf = (f"alphaextract,format=gray,crop={w}:{h}:{x0}:{y0},"
          f"lutyuv=y='if(gte(val,128),255,0)',signalstats,metadata=print:key=lavfi.signalstats.YAVG")
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", layer, "-vf", vf, "-f", "null", "-"],
                       capture_output=True, text=True)
    out, t = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1)); continue
        m = re.search(r"YAVG=([\d.]+)", line)
        if m and t is not None:
            out.append((t, float(m.group(1)) / 255.0))
    if not out:
        raise SystemExit(f"could not read alpha from {layer} — is it a transparent .mov (qtrle/prores4444)?")
    return out


FULL_BLEED = 0.90      # a frame covering this much of the CANVAS is a designed takeover, not a stray overlay


def report(layer, box, max_cov=DEFAULT_MAX, label="her face", owns_from=None):
    """-> (rc, lines). rc 1 = the layer lands on her. Never returns 0 on an unmeasurable layer.
    owns_from: the composition the layer was rendered from (reel_render passes it), where the takeover
    windows are looked up first; see owned_windows."""
    cov = coverage(layer, box)
    bad = [(t, c) for t, c in cov if c > max_cov]
    waived = 0
    if bad:
        # A full-screen takeover covers her BY DESIGN — that is the feature, not the defect. The safe-zone
        # check draws the same line at 90% of the canvas. Only measured once a breach exists, so the clean
        # path stays a single ffmpeg pass.
        owned = owned_windows(layer, owns_from)
        kept = [(t, c) for t, c in bad if not any(a <= t <= b for a, b in owned)]
        # Backstop for a SOLID-FILL full-screen graphic, which carries no declared window: a frame that
        # really does fill the canvas is a designed moment whatever wrote it.
        if kept:
            full = dict(coverage(layer, (0, 0, safe_zones.W, safe_zones.H)))
            kept = [(t, c) for t, c in kept if full.get(t, 0.0) < FULL_BLEED]
        waived, bad = len(bad) - len(kept), kept
    name = os.path.basename(layer)
    x0, y0, x1, y1 = box
    where = f"x{x0}–{x1} y{y0}–{y1}"
    note = ([f"   ({waived} frame(s) fall inside a declared takeover / full-screen card, which covers "
             f"her on purpose; not counted)"] if waived else [])
    if not bad:
        # Say which clean this is. "Clear of her" on a layer that covers her completely for half its life
        # is the kind of true-but-misleading line that teaches people to stop reading the output.
        unwaived = [c for t, c in cov if not (waived and c > max_cov)]
        peak = max(unwaived) if unwaived else 0.0
        head = (f"✅ no stray graphic on {label}: {name} peaks at {peak*100:.2f}% of the subject box "
                f"({where}) outside its takeover frames, limit {max_cov*100:.0f}%") if waived else \
               (f"✅ clear of {label}: {name} peaks at {max(cov, key=lambda x: x[1])[1]*100:.2f}% of the "
                f"subject box ({where}) at {max(cov, key=lambda x: x[1])[0]:.2f}s, limit {max_cov*100:.0f}%")
        return 0, [head] + note
    # collapse consecutive frames into ranges so the report reads like an edit note, not a log
    runs, start, prev = [], bad[0][0], bad[0][0]
    for t, _ in bad[1:]:
        if t - prev > 0.2:
            runs.append((start, prev)); start = t
        prev = t
    runs.append((start, prev))
    peak = max(bad, key=lambda x: x[1])
    lines = note + [f"⛔ {name} sits on {label} (subject box {where}) in {len(runs)} place(s), "
                    f"peak {peak[1]*100:.1f}% at t={peak[0]:.2f}s:"]
    for a, b in runs:
        worst = max((c for t, c in bad if a <= t <= b), default=0)
        lines.append(f"     {a:6.2f}s → {b:6.2f}s   up to {worst*100:.1f}% of her covered")
    return 1, lines


def _walk_up(start, name):
    """Walk up from a composition/render path looking for `name`. None when it is not there."""
    d = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))
    for _ in range(6):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def find_zones(start):
    """The job folder's subject-zones.json. None if the footage was never measured — which is reported as
    NOT MEASURED, never as clean."""
    return _walk_up(start, "subject-zones.json")


def owned_windows(start, owns_from=None):
    """The moments that cover her BY DESIGN — takeovers and full-screen breakaway cards — as [(a, b), ...]
    in seconds. build-reel-type.py writes owns-screen.json beside the composition.

    This replaces guessing from pixel coverage. The old test asked whether a frame filled >=90% of the
    CANVAS and called that a designed takeover. A word stack is mostly transparent between the letters
    and can never get near that: measured on a real takeover, it covered 39.7% of her face and 7.0% of
    the canvas, and the busiest frame in the entire layer reached 19.8%. So the waiver never fired for
    type, and every takeover — the mechanic working exactly as intended — was reported as a defect.

    Looked up from `owns_from` first when it is given (the composition dir, which holds its own copy),
    then by walking up from `start` as before. A render can be written anywhere, and a walk up from an
    output outside the job folder finds nothing: the takeover lost its waiver and a correct render was
    refused."""
    p = (_walk_up(owns_from, "owns-screen.json") if owns_from else None) or _walk_up(start, "owns-screen.json")
    if not p:
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return [(float(a), float(b)) for a, b in json.load(f).get("windows", [])]
    except (OSError, ValueError, TypeError):
        return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("layer")
    ap.add_argument("--zones", help="projects/<job>/subject-zones.json (default: found by walking up)")
    ap.add_argument("--box", help="x0,y0,x1,y1 in 1080x1920 authoring px, instead of --zones")
    ap.add_argument("--max", dest="max_cov", type=float, default=DEFAULT_MAX)
    ap.add_argument("--strict", action="store_true", help="exit non-zero on a collision")
    a = ap.parse_args()
    if a.box:
        box = tuple(int(v) for v in a.box.split(","))
    else:
        zp = a.zones or find_zones(a.layer)
        if not zp:
            print("⚠ SUBJECT: not measured — no subject-zones.json for this job, so nothing was checked. "
                  "Run: uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4\n"
                  "   This is NOT evidence that the layer is clear of her.")
            sys.exit(0)
        box = box_from_zones(zp)
    rc, lines = report(a.layer, box, a.max_cov)
    for ln in lines:
        print(ln)
    if rc:
        print("   Fix = move it into an open zone (subject-zones.json → zones.above / below / left / right) "
              "and re-render that layer.")
    sys.exit(rc if a.strict else 0)
