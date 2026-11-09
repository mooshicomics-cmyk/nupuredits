#!/usr/bin/env python3
"""video_grade.py — OPTIONAL color grade for the footage on the rendered routes.

Never applied by default. A grade is something the creator asks for by name (locked: "optional and
available, not built in"). It goes on the FOOTAGE only; graphics are composited on top, untouched, so
the pack's colors never shift. On the CapCut route a grade comes only from her own pick on the visual editor's
Filter: baked into a copy of the footage (product/finish.py), still split one clip per line, graphics untouched.

Five looks, built only from filters every ffmpeg has shipped for a decade (eq, colorbalance, curves,
hue) — so an older Mac's Homebrew ffmpeg or a minimal Windows build cannot lack them, and there is no
LUT file to bundle, stage, or lose:

  cinematic  richer contrast, teal shadows and amber highlights
  warm       sunlit, nostalgic warmth
  cool       calm, moody cool cast
  film       soft contrast, lifted blacks, a little less saturation
  mono       black and white with a touch more contrast

Used by: product/build-reel-mp4.py (GRADE=<look> in the env) and product/reel_render.py composite
(--grade <look>). Unknown names fail loud — a misspelled look must never silently ship the reel ungraded
when a grade was asked for.
"""

LOOKS = {
    "cinematic": "colorbalance=rs=-0.05:gs=0.02:bs=0.06:rh=0.06:gh=0.02:bh=-0.06,"
                 "eq=contrast=1.10:saturation=1.05",
    "warm":      "colorbalance=rm=0.05:gm=0.02:bm=-0.06:rh=0.04:bh=-0.05,"
                 "eq=saturation=1.06:brightness=0.01",
    "cool":      "colorbalance=rs=-0.03:bs=0.04:rm=-0.05:bm=0.06,"
                 "eq=saturation=0.95:contrast=1.04",
    "film":      "curves=all='0/0.04 0.5/0.5 1/0.96',"
                 "eq=saturation=0.90:contrast=1.06",
    "mono":      "hue=s=0,eq=contrast=1.08",
}

OFF = ("", "none", "off", "no")

# How each look PREVIEWS on her visual editor page: the export's own color math above, measured from ffmpeg and fitted
# as one color matrix per look (rows R, G, B: [r, g, b, offset], on 0..1). The page used hand-picked CSS filters that
# only resembled these, and two ran the wrong way ("Cool" warmed her preview while the export cooled it). The page
# applies exactly these numbers (product/visual-editor/editor.html GRADE_MATRIX, checked equal by
# product/tests/test_grade_preview.py, which also refits them from ffmpeg). Change a look above: run --fit, paste both.
PREVIEW_MATRIX = {
    "cinematic": [[1.0584, 0.0466, 0.0266, -0.0426], [0.0192, 1.059, 0.0109, -0.031], [-0.0074, 0.0064, 1.01, -0.0497]],
    "warm": [[1.0278, -0.0321, -0.0053, 0.022], [-0.0203, 1.0134, -0.0107, 0.0099], [-0.0171, -0.0313, 1.0252, -0.0323]],
    "cool": [[0.9839, 0.0631, 0.0226, -0.0515], [0.0253, 1.0, 0.0095, -0.0198], [0.0101, 0.0368, 0.9436, -0.0031]],
    "film": [[0.8735, 0.0861, 0.017, -0.0024], [0.0441, 0.916, 0.0166, 0.0123], [0.0436, 0.0869, 0.8461, -0.0047]],
    "mono": [[0.3226, 0.6335, 0.1228, -0.0462], [0.3226, 0.6335, 0.1228, -0.0462], [0.3226, 0.6335, 0.1228, -0.0462]],
}


def fit_preview(look):
    """The color matrix that best matches ffmpeg's grade for this look (least squares over the whole RGB cube)."""
    import subprocess
    import numpy as np
    lv = np.linspace(0, 255, 17).round().astype(np.uint8)
    cube = np.array([[r, g, b] for r in lv for g in lv for b in lv], dtype=np.uint8)
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "289x17", "-i", "-",
                          "-vf", LOOKS[look] + ",format=rgb24", "-f", "rawvideo", "-"],
                         input=cube.tobytes(), capture_output=True).stdout
    y = np.frombuffer(out, np.uint8).reshape(-1, 3).astype(float) / 255
    x = np.hstack([cube.astype(float) / 255, np.ones((len(cube), 1))])
    m = np.linalg.lstsq(x, y, rcond=None)[0]
    return [[round(float(v), 4) for v in row] for row in m.T], float(np.abs(np.clip(x @ m, 0, 1) - y).mean() * 255)



def grade_filter(name):
    """ffmpeg filter string for a named look, or None when no grade was asked for."""
    key = (name or "").strip().lower()
    if key in OFF:
        return None
    if key not in LOOKS:
        raise ValueError(f"unknown grade look {name!r}; choose one of: {', '.join(LOOKS)}")
    return LOOKS[key]


if __name__ == "__main__":
    import json, sys
    if "--fit" in sys.argv:                                  # refit the page's preview matrices from ffmpeg
        print(json.dumps({k: fit_preview(k)[0] for k in LOOKS}))
    else:
        for k, v in LOOKS.items():
            print(f"{k:10} {v}")
