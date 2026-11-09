#!/usr/bin/env python3
"""watermark.py — her logo in a corner of every reel, ONLY when she has asked for it.

    python3 product/watermark.py set "<pack>" <logo.png> [--corner top-left|top-right|bottom-left] [--width 150] [--opacity 0.9]
    python3 product/watermark.py show ["<pack>"]
    python3 product/watermark.py off "<pack>"

A watermark is a persistent element, and the engine never adds one of its own: it exists only after she turns it
on (here, or through the Brand Kit), per pack ("*" = every pack). Saved in `_local/watermark.json` (hers, kept by
every update, never shipped); the logo itself is copied into `assets/logos/`.

Where it lands, measured, never typed:
  * inside the safe area (safe_zones: below the top 270 px, above the bottom 300 px, 90 px in from the sides)
  * never in the right-hand rail where Reels and TikTok put their buttons (bottom-right is not offered)
  * the same box on every route: its own clip in the CapCut draft (she can move it, resize it, or delete it),
    burned in on a baked MP4 (build-reel-mp4.py, burn_layers.py --watermark)
"""
import json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

STORE = os.path.join(ROOT, "_local", "watermark.json")
LOGOS = os.path.join(ROOT, "assets", "logos")
W, H = 1080, 1920
CORNERS = ("top-left", "top-right", "bottom-left")
INSET = 24                                   # breathing room inside the safe area's edge


def _read():
    try:
        d = json.load(open(STORE, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def get(pack=None):
    """Her watermark for this pack (or her every-pack one), or None. Never raises: a bad file means no watermark."""
    d = _read()
    spec = d.get(pack) if pack and pack in d else d.get("*")
    if not isinstance(spec, dict):
        return None
    f = spec.get("file") or ""
    f = f if os.path.isabs(f) else os.path.join(ROOT, f)
    if not os.path.isfile(f):
        return None
    return dict(spec, file=f, corner=spec.get("corner") if spec.get("corner") in CORNERS else "bottom-left",
                width=max(60, min(320, int(spec.get("width", 150)))),
                opacity=max(0.3, min(1.0, float(spec.get("opacity", 0.9)))))


def set_watermark(pack, logo, corner="bottom-left", width=150, opacity=0.9):
    """Turn it on for `pack` ("*" = every pack): the logo copied into assets/logos/, the spec saved."""
    from PIL import Image
    if corner not in CORNERS:
        raise ValueError(f"corner is one of {', '.join(CORNERS)} (bottom-right is where the app's buttons are)")
    im = Image.open(logo)
    os.makedirs(LOGOS, exist_ok=True)
    name = os.path.basename(logo)
    dst = os.path.join(LOGOS, name)
    if os.path.abspath(logo) != os.path.abspath(dst):
        shutil.copy(logo, dst)
    note = None
    if im.mode not in ("RGBA", "LA") or im.convert("RGBA").getextrema()[3][0] == 255:
        note = ("This logo has a solid background, so it will show as a box. A PNG with a see-through background "
                "looks much cleaner.")
    d = _read()
    d[pack or "*"] = {"file": os.path.relpath(dst, ROOT).replace(os.sep, "/"), "corner": corner,
                      "width": int(width), "opacity": float(opacity)}
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, STORE)
    return note


def off(pack):
    d = _read()
    d.pop(pack or "*", None)
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    json.dump(d, open(STORE, "w", encoding="utf-8"), indent=1)


def box(spec):
    """(left, top, width, height) in 1080x1920 for the logo, inside the safe area, never in the button rail."""
    import safe_zones
    from PIL import Image
    iw, ih = Image.open(spec["file"]).size
    w = spec["width"]
    h = max(1, round(w * ih / iw))
    left_x = safe_zones.LEFT + INSET
    right_x = min(safe_zones.RIGHT, getattr(safe_zones, "RIGHT_RAIL", 900)) - INSET - w
    top_y = safe_zones.TOP + INSET
    bottom_y = safe_zones.BOTTOM - INSET - h
    x = right_x if spec["corner"] == "top-right" else left_x
    y = bottom_y if spec["corner"] == "bottom-left" else top_y
    return int(x), int(y), int(w), int(h)


def frame_png(spec, out_path, size=(W, H)):
    """A full-frame transparent PNG with the logo placed: what a baked video lays over its footage."""
    from PIL import Image
    x, y, w, h = box(spec)
    sx, sy = size[0] / W, size[1] / H
    logo = Image.open(spec["file"]).convert("RGBA").resize((max(1, round(w * sx)), max(1, round(h * sy))), Image.LANCZOS)
    if spec["opacity"] < 1.0:
        a = logo.getchannel("A").point(lambda v: round(v * spec["opacity"]))
        logo.putalpha(a)
    frame = Image.new("RGBA", size, (0, 0, 0, 0))
    frame.alpha_composite(logo, (round(x * sx), round(y * sy)))
    frame.save(out_path)
    return out_path


def add_to_capcut(call, did, pack, end_s):
    """Her logo as its own image clip across the whole reel in the CapCut draft (movable, deletable). No-op when
    she has none. `call` is the builder's VectCut caller."""
    spec = get(pack)
    if not spec or not end_s or end_s <= 0:
        return False
    from PIL import Image
    x, y, w, h = box(spec)
    cw, ch = Image.open(spec["file"]).size
    cx, cy = x + w / 2, y + h / 2
    call("add_image", draft_id=did, image_url=spec["file"], start=0, end=float(end_s), width=cw, height=ch,
         scale_x=w / cw, scale_y=w / cw, transform_x=(cx - W / 2) / (W / 2), transform_y=(H / 2 - cy) / (H / 2),
         track_name="watermark")
    print(f"  ✓ your logo is on its own clip ({spec['corner']}), the whole reel: move or delete it in CapCut anytime")
    return True


def main(argv):
    if not argv or argv[0] not in ("set", "show", "off"):
        print(__doc__.strip().split("\n\n")[1]); return 2
    cmd, rest = argv[0], argv[1:]
    opt = lambda k, d: rest[rest.index(k) + 1] if k in rest and rest.index(k) + 1 < len(rest) else d
    pos = [a for i, a in enumerate(rest) if not a.startswith("--") and (i == 0 or not rest[i - 1].startswith("--"))]
    if cmd == "set":
        if len(pos) < 2:
            print('set "<pack>" <logo.png>  ("*" for every pack)'); return 2
        try:
            note = set_watermark(pos[0], pos[1], opt("--corner", "bottom-left"), int(opt("--width", 150)), float(opt("--opacity", 0.9)))
        except (OSError, ValueError) as e:
            print(f"Not set: {e}"); return 2
        print(f"Your logo goes on every {pos[0] if pos[0] != '*' else ''} reel, {opt('--corner', 'bottom-left')}.".replace("every  reel", "every reel"))
        if note:
            print(note)
        return 0
    if cmd == "show":
        print(json.dumps(get(pos[0] if pos else None), indent=1)); return 0
    off(pos[0] if pos else "*"); print("Watermark off."); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
