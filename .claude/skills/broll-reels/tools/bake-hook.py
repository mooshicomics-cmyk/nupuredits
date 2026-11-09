#!/usr/bin/env python3
"""Bake a hook headline (+ optional accent turn) onto a b-roll clip, in the buyer's STYLE PACK.
Renders text to a transparent PNG with Pillow, overlays with ffmpeg, keeps a flat/grainy iPhone finish.

Fonts + color are REQUIRED and come from the chosen style pack (ask resolve-pack.py --list for the
packs the engine defines). Nothing is hardcoded and NO fonts ship with this skill: the SKILL resolves the pack ->
font files + color and passes them in. (This engine deliberately does not bundle any font — some brand
fonts are licensed and cannot be distributed. Pass properly-licensed pack fonts.)

  python3 bake-hook.py IN.mp4 OUT.mp4 "hook" --headline-font PATH --accent-font PATH
      [--aside "turn"] [--pos top|center|auto] [--color "#ffffff"] [--size N]

Look rules: flat solid color by default (native in-app look); AUTO-FIT so the widest line fills ~80% of
frame width; BALANCED line-wrap (equal-width lines) for headline AND turn; IG-safe (clear of top ~14% /
bottom ~20%). Two things are now ADAPTIVE (read the footage, then decide — not a fixed rule that can be
wrong for a given clip):
  • READABILITY: a soft shadow is added ONLY where the background behind the text is bright or busy (a
    sunlit window, a light/cluttered scene). On a mid-tone or dark background it stays flat — the shadow
    would be over-produced there. (round 15 buyer feedback)
  • PLACEMENT: `--pos auto` samples faces across the clip (vendored YuNet) and picks top vs center so the
    text clears the subject's head for the WHOLE clip, not one guessed frame. If nothing clears, it warns
    on stderr so a clean build never silently ships text over a face. (round 14/15) The face check needs
    OpenCV, which setup does not put in python3; when this python3 has none, the check borrows it through
    uv (which setup does install). Only the check moves: the text is still drawn by this python3's Pillow,
    because a different Pillow build can lay the same hook out differently (letter spacing).
  • COLOR: HDR phone footage (HLG / PQ, BT.2020) is converted to SDR first (product/hdr.py, the same
    conversion the voiceover builder uses). Left tagged HDR, the white hook text landed at the HDR peak or
    washed out grey depending on the player.

AUDIO: the source audio is dropped (-an) on purpose. Text-over-b-roll REACH reels get a trending sound
added in-app at post time, so the clip ships silent. If a clip's own ambient sound matters, keep it out
of this batch (or add a --keep-audio path later).
"""
import argparse, json, platform, shutil, subprocess, os, sys, tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "product"))
from video_encoder import pick_encoder   # NVENC on a Windows GPU box; the tuned libx264 look kept on Mac
from hdr import HDR2SDR, hdr_kind        # HDR phone footage back to SDR before anything is drawn on it

W, H = 720, 1280
TOP_SAFE = 190      # ~15% — clear of IG top UI (profile pill, sound, menu)
BOTTOM_SAFE = 1024  # ~80% — clear of IG caption + right-rail actions
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
FACE_MODEL = os.path.join(_REPO, "assets", "models", "face_detection_yunet_2023mar.onnx")


def hex_to_rgba(s):
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)


def _duration(inp):
    try:
        return float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", inp],
            stderr=subprocess.DEVNULL))
    except Exception:
        return 0.0


_SDR = {}


def _sdr(inp):
    """The HDR->SDR prefix for this clip's filter chain ("" for SDR footage), probed once per clip."""
    if inp not in _SDR:
        _SDR[inp] = f"{HDR2SDR}," if hdr_kind(inp) else ""
    return _SDR[inp]


def _frame_png(inp, t):
    """Grab one frame at time t, scaled+cropped to the W×H text canvas (same transform the bake uses), as a
    temp PNG path — or None. So a sampled pixel maps 1:1 to where the text will actually sit."""
    tf = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    vf = f"{_sdr(inp)}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", f"{max(0,t):.2f}",
                        "-i", inp, "-frames:v", "1", "-vf", vf, tf], capture_output=True)
    return tf if (r.returncode == 0 and os.path.getsize(tf) > 0) else None


def _head_rows(y, h):
    """The rows a detected face's head occupies: a little hair/forehead above the box, the chin below."""
    return max(0, int(y - h * 0.30)), min(H, int(y + h * 1.10))


# Face detection for a python3 without OpenCV: the same YuNet model, run by uv's OpenCV on the frames this
# process already cut. Prints one JSON list per frame of [x, y, w, h] boxes.
_DETECT = r"""
import json, os, sys
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
import cv2
det = cv2.FaceDetectorYN.create(sys.argv[1], "", (int(sys.argv[2]), int(sys.argv[3])), 0.6)
out = []
for p in sys.argv[4:]:
    img, faces = cv2.imread(p), None
    if img is not None:
        det.setInputSize((img.shape[1], img.shape[0]))
        try:
            _, faces = det.detect(img)
        except Exception:
            faces = None
    out.append([[float(v) for v in fc[:4]] for fc in (faces if faces is not None else [])])
print(json.dumps(out))
"""


def _boxes_via_uv(pngs):
    """Face boxes per frame from an OpenCV that uv provides, or None when uv is missing or the run fails."""
    uv = shutil.which("uv")
    if not uv:
        return None
    # Intel Macs on macOS 11/12 only get an OpenCV built for numpy 1; with numpy 2 it crashes on import
    pin = ["--with", "numpy<2"] if sys.platform == "darwin" and platform.machine() == "x86_64" else []
    r = subprocess.run([uv, "run", "--quiet", "--no-project", "--with", "opencv-python-headless", *pin, "python", "-c",
                        _DETECT, FACE_MODEL, str(W), str(H), *pngs],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return None


def face_band(inp, n=8):
    """Vertical band [top, bottom] (W×H px) the subject's head occupies across the clip; () when the check ran
    and found no face; None when it could not run. Best-effort: reuses the engine's vendored YuNet detector;
    returns None if cv2 or the model is unavailable (the caller then keeps the requested placement and warns
    that it could not be verified)."""
    # OpenCV 5 prints a "Targets are not supported" WARN line every time the detector loads; it is not a
    # problem, so keep it off the creator's screen (errors still print). Must be set before the import.
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    try:
        import cv2
    except Exception:
        cv2 = None
    if not os.path.exists(FACE_MODEL) or (cv2 is None and not shutil.which("uv")):
        return None
    dur = _duration(inp)
    times = [dur * (i + 0.5) / n for i in range(n)] if dur > 0 else [0.0]
    if cv2 is None:                                  # no OpenCV here: borrow uv's for the check only
        pngs = [p for p in (_frame_png(inp, t) for t in times) if p]
        boxes = _boxes_via_uv(pngs) if pngs else []
        for p in pngs:
            os.unlink(p)
        if boxes is None:
            return None
        rows = [_head_rows(y, h) for frame in boxes for x, y, w, h in frame]
        return (min(r[0] for r in rows), max(r[1] for r in rows)) if rows else ()
    try:
        det = cv2.FaceDetectorYN.create(FACE_MODEL, "", (W, H), 0.6)
    except Exception:
        return None
    top = bot = None
    for t in times:
        p = _frame_png(inp, t)
        if not p:
            continue
        img = cv2.imread(p); os.unlink(p)
        if img is None:
            continue
        det.setInputSize((img.shape[1], img.shape[0]))
        try:
            _, faces = det.detect(img)
        except Exception:
            faces = None
        for fc in (faces if faces is not None else []):
            x, y, w, h = fc[:4]
            y0, y1 = _head_rows(y, h)               # hair/forehead above the box, the chin below
            top = y0 if top is None else min(top, y0)
            bot = y1 if bot is None else max(bot, y1)
    return (top, bot) if top is not None else ()


def _needs_shadow(inp, y0, y1):
    """True if the background directly behind the text band is bright or busy enough that flat text would
    lose legibility (round 15). Cheap: sample one mid-clip frame, look at the band the text sits in."""
    p = _frame_png(inp, _duration(inp) / 2)
    if not p:
        return False
    try:
        im = Image.open(p).convert("L").crop((0, max(0, y0), W, min(H, y1)))
    except Exception:
        return False
    finally:
        try: os.unlink(p)
        except OSError: pass
    px = list(im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())
    if not px:
        return False
    mean = sum(px) / len(px)
    var = sum((v - mean) ** 2 for v in px) / len(px)
    # bright ground (white text washes out) OR busy/high-variance ground (text fights detail)
    return mean > 150 or var > 3200


def draw_centered(draw, text, font, y, fill, shadow=False):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    x = (W - (r - l)) // 2 - l
    draw.text((x, y), text, font=font, fill=fill)   # flat fill (the soft shadow, if any, is a blurred layer below)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("hook")
    ap.add_argument("--aside", default=None)
    ap.add_argument("--size", type=int, default=0)   # 0 = auto-fit to width
    ap.add_argument("--pos", choices=["top", "center", "auto"], default="auto")
    ap.add_argument("--headline-font", required=True,
                    help="path to the style pack's headline font (required; no font ships with this skill)")
    ap.add_argument("--accent-font", default=None,
                    help="path to the pack's accent/subhead font (defaults to the headline font if omitted)")
    ap.add_argument("--color", default="#ffffff")
    a = ap.parse_args()

    if not a.hook or not a.hook.strip():
        sys.exit("bake-hook: empty hook — every reel needs a headline (check the HOOK-MAP row for this clip).")
    HF = a.headline_font
    AF = a.accent_font or a.headline_font   # single-font packs reuse the headline face for the turn
    for label, fp in (("headline", HF), ("accent", AF)):
        if not os.path.isfile(fp):
            sys.exit(f"bake-hook: {label} font not found: {fp}\n"
                     f"  Pass the buyer's STYLE PACK font (see SKILL.md -> Style pack). "
                     f"This skill ships no fonts; licensed brand fonts are not distributed.")
    fill = hex_to_rgba(a.color)
    probe = ImageDraw.Draw(Image.new("RGBA", (W, H)))

    def word_w(word, s, fp):
        f = ImageFont.truetype(fp, s)
        l, t, r, b = probe.textbbox((0, 0), word, font=f)
        return r - l

    def balance(words, k, s, fp):
        # split words into k contiguous lines minimizing the WIDEST line (balanced across width)
        ww = [word_w(w, s, fp) for w in words]
        sp = word_w(" ", s, fp)
        def lines_needed(cap):
            n = 1; cur = 0
            for w in ww:
                add = w if cur == 0 else cur + sp + w
                if add <= cap: cur = add
                else: n += 1; cur = w
            return n
        lo, hi = max(ww), sum(ww) + sp * (len(ww) - 1)
        while lo < hi:
            mid = (lo + hi) // 2
            if lines_needed(mid) <= k: hi = mid
            else: lo = mid + 1
        cap = lo
        out, cur, cw = [], [], 0
        for w, x in zip(words, ww):
            add = x if not cur else cw + sp + x
            if add <= cap: cur.append(w); cw = add
            else: out.append(" ".join(cur)); cur = [w]; cw = x
        if cur: out.append(" ".join(cur))
        return out

    target_w = int(W * 0.80)
    if a.size and a.size > 0:
        lines = a.hook.split("|"); size = a.size
    elif "|" in a.hook:
        lines = a.hook.split("|"); size = 42
        for s in range(76, 41, -1):
            if max(word_w(ln, s, HF) for ln in lines) <= target_w: size = s; break
    else:
        words = a.hook.split()
        k = max(1, min(4, round(len(a.hook) / 20)))       # ~20 chars/line target
        size, lines = 42, [a.hook]
        for s in range(76, 41, -1):
            cand = balance(words, k, s, HF)
            if max(word_w(ln, s, HF) for ln in cand) <= target_w:
                size, lines = s, cand; break
        else:
            lines = balance(words, k, 42, HF)
    a.size = size
    hook_font = ImageFont.truetype(HF, a.size)
    lh = int(a.size * 1.16)

    # accent turn: balance-wrap AND auto-fit within the safe width too (long turns must not overflow)
    aside_lines, aside_size, aside_font = [], 0, None
    if a.aside:
        awords = a.aside.split()
        ka = max(1, min(3, round(len(a.aside) / 24)))
        aside_size = max(30, int(a.size * 0.62))
        for s in range(int(a.size * 0.66), 29, -1):
            cand = balance(awords, ka, s, AF)
            if max(word_w(ln, s, AF) for ln in cand) <= target_w:
                aside_size, aside_lines = s, cand
                break
        else:
            aside_lines = balance(awords, ka, 30, AF)
        aside_font = ImageFont.truetype(AF, aside_size)
    alh = int(aside_size * 1.18) if a.aside else 0
    aside_gap = int(a.size * 0.30) if a.aside else 0
    block_h = lh * len(lines) + aside_gap + alh * len(aside_lines)

    def band_for(pos):
        y = max(TOP_SAFE, (H - block_h) // 2) if pos == "center" else TOP_SAFE
        if y + block_h > BOTTOM_SAFE:
            y = max(TOP_SAFE, BOTTOM_SAFE - block_h)
        return y

    def face_overlap(y, fb):
        if not fb:
            return 0
        ft, fbot = fb
        return max(0, min(y + block_h, fbot) - max(y, ft))

    # PLACEMENT: resolve `auto` from where the subject's head actually is (across the whole clip), so the
    # text clears the face. Fall back to top + a visible note when detection isn't available. (round 14/15)
    if a.pos == "auto":
        fb = face_band(a.inp)
        clip = os.path.basename(a.inp)
        if fb is None:
            a.pos = "top"
            print(f"[bake-hook] {clip}: could not verify face placement (no cv2/model) — used top; "
                  f"pull a frame and check the hook is clear of the face.", file=sys.stderr)
        elif not fb:
            a.pos = "top"                   # checked across the clip: no face to keep clear of
            print(f"[bake-hook] {clip}: no face in this clip, so the hook sits at the top.", file=sys.stderr)
        else:
            a.pos = min(("top", "center"), key=lambda p: face_overlap(band_for(p), fb))
            ov = face_overlap(band_for(a.pos), fb)
            if ov > 0:
                print(f"[bake-hook] WARN {clip}: hook still overlaps the subject's head by ~{ov}px even at "
                      f"best placement ({a.pos}). Use a shorter hook or re-trim this clip.", file=sys.stderr)
    y0 = band_for(a.pos)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = y0
    for ln in lines:
        draw_centered(d, ln, hook_font, y, fill); y += lh
    if a.aside:
        y += aside_gap
        for ln in aside_lines:
            draw_centered(d, ln, aside_font, y, fill); y += alh

    # READABILITY: add a SOFT shadow (a blurred dark halo behind the exact letter shapes) ONLY when the
    # background behind the text is bright or busy. On a mid-tone/dark ground it stays flat — a shadow there
    # would read as over-produced, against the native look. (round 15 buyer feedback)
    if _needs_shadow(a.inp, y0, y0 + block_h):
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        halo.putalpha(img.split()[3].filter(ImageFilter.GaussianBlur(7)))   # black with blurred text alpha
        img = Image.alpha_composite(Image.alpha_composite(halo, halo), img)  # 2x halo, then the flat text

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        png = tf.name
    img.save(png)

    # SCALE the source to the text canvas (W×H) first — the hook PNG is authored at W×H and overlaid at
    # 0:0, so any-res b-roll (1080×1920, 4K, …) must be normalized to W×H or the text lands wrong/offset.
    # force_original_aspect_ratio=increase + crop keeps 9:16 framing and never letterboxes.
    vf = (f"[0:v]{_sdr(a.inp)}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
          "eq=contrast=0.93:saturation=0.92:brightness=0.012:gamma=1.02,"
          "noise=alls=7:allf=t+u[bg];[bg][1:v]overlay=0:0,format=yuv420p")
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", a.inp, "-i", png,
           "-filter_complex", vf, *pick_encoder(vbr="12M", crf=22, preset="medium", hw_on_mac=False),
           "-an", a.out]
    subprocess.run(cmd, check=True)
    os.unlink(png)
    print("baked", a.out)


if __name__ == "__main__":
    main()
