# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "pillow-heif", "opencv-python-headless", "numpy",
#   "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs: older OpenCV builds need numpy 1
# ///
"""
carousel.py: Instagram carousels (1080x1350) in the creator's style pack. Everything runs locally.

The words come from plan.json, written by the `carousel` skill once the creator approves the script.
This file does layout, photo placement, fonts, export and the editor, so Claude never has to.

  uv run workflows/carousel/carousel.py photos <job> [inbox files]   copy photos into the job (HEIC is fine)
  uv run workflows/carousel/carousel.py frames <job> --from <reel>    pull her best stills from a reel into photos/
  uv run workflows/carousel/carousel.py build  <job> --pack Butter --look mix
  uv run workflows/carousel/carousel.py build  <job> --pack Butter --style native --bg photo     (a story: plan.json "format": "story")
  uv run workflows/carousel/carousel.py render <job> [--png]          slides + beat sheet + layout check
  uv run workflows/carousel/carousel.py edit   <job>                  opens the editor in the browser
  uv run workflows/carousel/carousel.py words  <job>                  a reel's transcript, to write from
  uv run workflows/carousel/carousel.py deliver <job>                 copy the slides + caption to Downloads and open it

Files: projects/<job>/carousel/{plan.json, carousel.json, photos/, slides/, beat-sheet.jpg, caption.txt}
"""
from __future__ import annotations

import argparse, functools, html, json, os, platform, re, shutil, signal, socket, subprocess, sys, tempfile, threading, time, webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # OpenCV backend notes read like errors in her terminal

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent.parent
INBOX, FONTS = ENGINE / "inbox", ENGINE / "assets" / "fonts"
YUNET = ENGINE / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
W, H, M = 1080, 1350, 90                      # Instagram portrait, 90px safe margin
TEXT_W = W - 2 * M
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
SCALE = 2                                     # draw at 2x and shrink: crisp, evenly smoothed type on export
BATCH = 2                                     # slides per Chrome screenshot: small strips encode fast and draw in parallel
SLOW_NOTE = 90                                # seconds before saying "still drawing" (never a time limit)
BROWSER_STALL = 90                            # seconds at next to no CPU before a browser draw counts as stopped dead
# Test knob: behave like a buyer's machine (licensed font files absent, nothing from CapCut).
SIMULATE_BUYER = os.environ.get("CAROUSEL_SIMULATE_BUYER") == "1"

ROLES = {   # role -> fields it needs (a tuple = any one of them)
    "hook": ["headline"], "reframe": ["headline"], "point": ["headline"],
    "proof": [("number", "screenshot")], "turn": ["line"], "closer": ["action"],
}
FACE = {"hook": (.25, .20), "reframe": (.17, .15), "point": (.15, .11),    # where the face sits (y, height as a
        "proof": (.18, .14), "turn": (.20, .17), "closer": (.25, .19)}     # share of the frame); text sits below
PHOTO_SLOT = {"hook": 0, "reframe": 1, "proof": 1, "point": 2, "turn": 0, "closer": 1}  # index into plan["photos"]

# Stories: same engine, a taller canvas. Instagram draws its own UI over the top 270px (name, close button) and the
# bottom 384px (reply bar, sticker tray), about 65px in from each side (Meta's story template). Words stay inside.
STORY_H, STORY_W = 1920, W - 160
FORMATS = {
    "carousel": {"size": {"w": W, "h": H}, "safe": {"l": 50, "t": 50, "r": 1030, "b": 1300},
                 "move": {"l": M, "t": M, "r": W - M, "b": H - M},
                 "vars": {"W": f"{W}px", "H": f"{H}px", "pad": f"{M}px", "txt-b": "100px", "mid-t": "0px", "mid-b": "0px"}},
    "story": {"size": {"w": W, "h": STORY_H}, "safe": {"l": 65, "t": 270, "r": 1015, "b": 1536},
              "move": {"l": 80, "t": 290, "r": 1000, "b": 1516},
              "vars": {"W": f"{W}px", "H": f"{STORY_H}px", "pad": "80px", "txt-b": "420px", "mid-t": "290px", "mid-b": "404px"}},
}
STORY_ROLES = {"hook": ["headline"], "text": ["line"], "proof": [("number", "screenshot")], "ask": [("action", "lead", "sticker")]}
STORY_FACE = (.20, .15)          # face center and height on a story photo (the words sit low, under the face)
STICKERS = {"poll": "Poll", "question": "Question box", "link": "Link sticker", "countdown": "Countdown",
            "slider": "Emoji slider", "quiz": "Quiz"}   # added in Instagram; the design only holds the space


def die(msg: str): raise SystemExit(msg)

def cdir(job: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", job): die(f"job names are letters, numbers and dashes: {job!r}")
    return ENGINE / "projects" / job / "carousel"

def read_json(p: Path): return json.loads(p.read_text(encoding="utf-8"))

def write_json(p: Path, obj) -> None:
    """Atomic: the editor autosaves while exports read, so never leave a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1)
    for attempt in range(20):        # Windows refuses to replace a file another process has open for a moment
        try: os.replace(tmp, p); return
        except PermissionError:
            if attempt == 19: raise
            time.sleep(0.05)

# ---------------------------------------------------------------- the style pack (fonts + colors)
# Nothing here is hand-picked per pack. Every font and color is read from the creator's style pack
# (product/creative-vault/style-packs.json, her own packs in _local/, colors from product/pack_palettes.py),
# so a pack she builds herself turns into carousels with no extra setup.
#   display = the pack's headline · body = its caption · eyebrow = its subhead (else accent caption)
#   turn    = its thought bubble (the aside voice, so the shift to THEIR life reads as a change of voice)
sys.path.insert(0, str(ENGINE / "product"))
ROLE_ELEMENT = {"CDisp": "headline", "CBody": "caption", "CEye": "accent_caption", "CTurn": "thought_bubble"}
REF_XH = 0.545   # x-height of the engine's caption face (Inter Medium): body/eyebrow sizes are tuned to it

@functools.lru_cache(None)
def _sp():
    import stylepack; return stylepack

def packs() -> list[str]: return _sp().names()

def default_pack() -> str:
    """Her default pack (product/creative-vault/user-style.json, the one her reels use), so a carousel or story
    matches her reels; Butter when she has none yet or it no longer exists."""
    import user_style
    name = user_style.default_pack(str(ENGINE / "product" / "creative-vault" / "user-style.json"))
    return name if name and name in packs() else "Butter"

@functools.lru_cache(None)
def _licensed() -> tuple[str, ...]:
    """Font files make-ship.sh keeps out of the download (licensed). Used to preview a buyer's machine."""
    ship = ENGINE / "make-ship.sh"
    return tuple(re.findall(r"--exclude='assets/fonts/([^']+)'", ship.read_text(encoding="utf-8"))) if ship.exists() else ()

def ships(file: str) -> bool: return not any(Path(file).match(pat) for pat in _licensed())

def _resolve(name: str | None, file: str | None, fallback: str) -> tuple[str, bool]:
    """(path, is_standin). Same order as reels: the pack's file, then the font she added in CapCut (by name),
    then the pack's own stand-in for that element."""
    path = _sp()._abs(file) if file else ""
    if path and os.path.exists(path) and (not SIMULATE_BUYER or ships(Path(path).name)): return path, False
    if not SIMULATE_BUYER and name:
        try:
            import capcut_userfonts
            hit = capcut_userfonts.resolve_font_file(name, None)
            if hit and os.path.exists(hit) and not hit.lower().endswith(".ttc"): return hit, False   # browsers can't load .ttc
        except Exception: pass
    sub = _sp()._abs(fallback)
    if not os.path.exists(sub): die(f"the font {name} is not on this computer and its stand-in {fallback} is missing")
    return sub, True

def _xh(path: str) -> float:
    """x-height as a share of the font size, measured from the real file."""
    try:
        bb = _font(path, 200).getbbox("x"); return max(.3, min(.75, (bb[3] - bb[1]) / 200))
    except Exception: return REF_XH

def _hex(c): c = c.lstrip("#"); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
def _chroma(c): r = _hex(c); return (max(r) - min(r)) / 255

@functools.lru_cache(None)
def theme(pack: str) -> dict:
    if pack not in packs(): die(f"--pack must be one of: {', '.join(packs())}")
    import pack_palettes as pp
    sp, P = _sp(), _sp().load(pack)
    els, wd = P["elements"], P.get("welldone") or {}

    fonts = {}
    for fam, kind in ROLE_ELEMENT.items():
        e = els.get(kind) or els["caption"]
        name, file = e.get("font"), e.get("file")
        if fam == "CEye" and P.get("subhead_font_name"): name, file = P["subhead_font_name"], P.get("subhead_font_file")
        fb = e.get("fallback_file") or sp._ROLE_FALLBACK.get(kind, "Poppins-SemiBold.ttf")
        path, standin = _resolve(name, file, fb)
        fonts[fam] = {"path": path, "name": name or Path(path).stem, "standin": standin}

    pal = {**pp.PALETTE.get(pack, pp.PALETTE["Editorial"])}
    if P.get("accent_color"): pal["accent"] = P["accent_color"]
    card = getattr(pp, "CARD_THEME", {}).get(pack, {})
    col = lambda role, d: pp.resolve_color(pack, card.get(role) or d)   # a palette role name, or a #hex
    light, dark, accent = pal["light"], pal["dark"], pal["accent"]
    def readable(fg, bg, floor=2.2):   # eyebrows are big decorative words: keep the pack color unless it vanishes
        if pp.contrast_ratio(fg, bg) >= floor: return fg
        return dark if pp.contrast_ratio(dark, bg) >= pp.contrast_ratio(light, bg) else light
    structure = card.get("structure", "")
    head, upper = els["headline"], (els["headline"].get("case") == "upper" or card.get("headline_case") == "upper")
    track = wd.get("headline_tracking", head.get("tracking", 0)) or 0
    photo_text = light if _chroma(light) < .08 else "#ffffff"
    card_bg = col("ground", dark); card_ink = col("ink", light)
    scrim = ",".join(str(round(v * .45)) for v in _hex(dark))       # her dark color, pulled toward black
    chip = ({"chip-r": "14px", "chip-border": f"5px solid {dark}", "chip-shadow": f"10px 10px 0 {dark}"} if structure == "block"
            else {"chip-r": "999px", "chip-border": "0", "chip-shadow": "none"} if structure == "editorial"
            else {"chip-r": "16px", "chip-border": "0", "chip-shadow": "none"})
    vars_ = {
        "photo-text": photo_text,
        "photo-disp": wd.get("hook_color") or (accent if structure == "block" else photo_text),
        # on a photo the eyebrow sits over her dark scrim: the pack color unless it vanishes there (a deep accent)
        "photo-eye": wd.get("subhead_color") or ("#ffffff" if structure == "block"
                                                 else readable(accent, "#%02x%02x%02x" % tuple(round(v * .45) for v in _hex(dark)), 3.0)),
        "ground": light, "ground-ink": dark, "ground-disp": dark,
        "ground-eye": readable(getattr(pp, "HANDS_OFF_ACCENT", {}).get(pack, pal.get("pop2", accent)), light),
        "card": card_bg, "card-ink": card_ink, "card-disp": card_ink,
        "card-eye": readable(col("kicker_color", accent), card_bg),
        "accent": accent, "accent-ink": readable(dark, accent),
        "scrim": scrim, "disp-case": "uppercase" if upper else "none", "disp-track": f"{track}em",
        "disp-lh": "0.93" if upper else "1.0", "disp-weight": "normal", "eye-weight": "normal",
        "eye-track": f"{wd.get('subhead_tracking', 0)}em", "body-weight": "normal", **chip,
    }
    scale = lambda fam, lo, hi: max(lo, min(hi, REF_XH / _xh(fonts[fam]["path"])))
    return {"fonts": fonts, "vars": vars_, "disp_case": "upper" if upper else "none", "disp_track": float(track),
            "body_scale": scale("CBody", .85, 1.15), "eye_scale": scale("CEye", .85, 1.35), "turn_scale": scale("CTurn", .8, 1.3)}

def pack_cfg(pack: str) -> dict: return theme(pack)
def resolve_fonts(pack: str) -> dict: return theme(pack)["fonts"]

@functools.lru_cache(None)
def _font(path: str, size: int):
    from PIL import ImageFont
    return ImageFont.truetype(path, size)

# ---------------------------------------------------------------- type fitting, measured with the real font
def wrap(text: str, pack: str, size: int, width: float):
    """Greedy wrap in the pack's display face and case. Returns (lines, widest line px). '\\n' forces a break."""
    p = pack_cfg(pack); f = _font(resolve_fonts(pack)["CDisp"]["path"], size)
    case = str.upper if p["disp_case"] == "upper" else (lambda s: s)
    def wid(s): return f.getlength(case(s)) + p["disp_track"] * size * max(len(s) - 1, 0)
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            test = f"{cur} {w}".strip()
            if cur and wid(test) > width: lines.append(cur); cur = w
            else: cur = test
        lines.append(cur)
    return lines, max(wid(l) for l in lines)

def balance(text: str, pack: str, size: int, width: float) -> list[str]:
    """Same number of lines, as even as they can be: the narrowest width that still fits in that many lines.
    No lonely last word ("now i'm doing / it.")."""
    lines = wrap(text, pack, size, width)[0]
    if len(lines) < 2: return lines
    lo, hi = width / len(lines), width
    for _ in range(14):
        mid = (lo + hi) / 2
        if len(wrap(text, pack, size, mid)[0]) <= len(lines): hi = mid
        else: lo = mid
    return wrap(text, pack, size, hi)[0]

def fit(text: str, pack: str, start: int, max_lines: int, width: float = TEXT_W):
    """Largest size <= start that fits the width in max_lines (3% slack for browser vs PIL rounding), balanced."""
    width *= 0.97
    for size in range(start, 40, -4):
        lines, widest = wrap(text, pack, size, width)
        if len(lines) <= max_lines and widest <= width: return size, balance(text, pack, size, width)
    return 40, balance(text, pack, 40, width)

# ---------------------------------------------------------------- slide layouts (HTML fragments)
def esc(s: str | None) -> str: return html.escape(s or "", quote=False).replace("\n", "<br>")

def div(cls: str, inner: str, style: str = "") -> str:
    return f"<div class='{cls}'" + (f" style='{style}'" if style else "") + f">{inner}</div>"

def headline(text, pack, start, max_lines, style="", cls="d", width=TEXT_W, size=None):
    size, lines = (size, balance(text, pack, size, width * .97)) if size else fit(text, pack, start, max_lines, width)
    return div(cls, "<br>".join(html.escape(l, quote=False) for l in lines), f"font-size:{size}px{style}")

# Her text size and spacing for this carousel (plan.json; nothing set = exactly as before). Two buyers had their
# Claude hand-add these (2026-10-19): the small text read too small, and the eyebrow sat too far from the headline.
#   body_boost / eye_boost          the body and eyebrow text, 1.0 = as built (0.6 to 2.0)
#   hook_support_size               px for the line under the cover's headline
#   headline_line_height            the headline's line height (0.7 to 1.6)
#   eyebrow_line_height, eyebrow_gap  the eyebrow's line height, and its gap to the headline in px
TEXT = {"body_boost": 1.0, "eye_boost": 1.0, "hook_support_size": None}


def text_settings(plan: dict) -> dict:
    """The plan's text size and spacing, held to sane ranges, plus the CSS variables they set."""
    num = lambda k, lo, hi: (min(hi, max(lo, float(plan[k]))) if isinstance(plan.get(k), (int, float)) else None)
    out = {"body_boost": num("body_boost", .6, 2.0) or 1.0, "eye_boost": num("eye_boost", .6, 2.0) or 1.0,
           "hook_support_size": num("hook_support_size", 24, 140)}
    css = {}
    if num("headline_line_height", .7, 1.6) is not None: css["disp-lh"] = str(num("headline_line_height", .7, 1.6))
    if num("eyebrow_line_height", .7, 1.6) is not None: css["eye-lh"] = str(num("eyebrow_line_height", .7, 1.6))
    if num("eyebrow_gap", 0, 120) is not None: css["eye-gap"] = f"{round(num('eyebrow_gap', 0, 120))}px"
    return {**out, "css": css}


def body(text, pack, size=46, style="", cls="b"):
    return div(cls, esc(text), f"font-size:{round(size * pack_cfg(pack)['body_scale'] * TEXT['body_boost'])}px{style}") if text else ""

def eyebrow(text, pack, size=76, style=""):
    return div("eye", esc(text), f"font-size:{round(size * pack_cfg(pack)['eye_scale'] * TEXT['eye_boost'])}px{style}") if text else ""

def box(kind, inner, center=False, left=False):
    if kind == "photo": return div("txt c" if center else "txt", inner)
    return div("mid l" if left else "mid", inner)

def layout(sl: dict, kind: str, pack: str, point_size: int | None = None) -> str:
    r, big = sl["role"], kind != "photo"
    if r == "hook":   # with no photo behind it, the headline IS the cover, so it goes much bigger
        return box(kind, eyebrow(sl.get("eyebrow"), pack, 96 if big else 76)
                   + headline(sl["headline"], pack, 230 if big else 150, 3)
                   + body(sl.get("support"), pack, TEXT["hook_support_size"] or (54 if big else 46), ";margin-top:36px"), center=True)
    if r in ("reframe", "point"):
        return box(kind, eyebrow(sl.get("eyebrow"), pack, 72) + body(sl.get("lead"), pack, 46, ";margin-bottom:30px")
                   + headline(sl["headline"], pack, 150, 3, size=point_size)
                   + body(sl.get("support"), pack, 44, ";margin-top:30px"), left=True)
    if r == "proof":  # the one visual moment: a screenshot, or the number at full width
        shot = (f"<img class=shot src='/photos/{html.escape(sl['screenshot'], quote=True)}' style='width:{sl['_shot_w']}px'>"
                if sl.get("screenshot") else "")
        number = "" if shot else headline(sl["number"], pack, 320, 1, ";margin:8px 0 10px")
        label = body(sl.get("label"), pack, 64, ";margin-top:30px", cls="b hl")
        return box(kind, eyebrow(sl.get("eyebrow"), pack, 100) + shot + number + label
                   + body(sl.get("support"), pack, 50, ";margin-top:90px"), center=True)
    if r == "turn":
        return box(kind, eyebrow(sl.get("eyebrow"), pack, 82, ";margin-bottom:40px")
                   + div("it", esc(sl["line"]), f"font-size:{round((100 if kind == 'photo' else 104) * pack_cfg(pack)['turn_scale'])}px"), center=True)
    if r == "closer":
        act = (headline(sl["action"], pack, 170, 1, ";margin:6px 0 24px") if sl.get("action_style") == "big"
               else headline(sl["action"], pack, 130, 1, ";margin:16px 0 26px", cls="d btn", width=TEXT_W - 120))
        return box(kind, eyebrow(sl.get("intro"), pack, 88) + body(sl.get("lead"), pack, 50) + act
                   + body(sl.get("support"), pack, 42), center=True)
    die(f"unknown slide role: {r}")

def sticker(st: dict) -> str:
    """The space for a sticker she adds in Instagram. Shows in the editor, never in the export (render.html hides it)."""
    t = st.get("type", "poll"); detail = " · ".join(x for x in (st.get("prompt"), " / ".join(st.get("options") or [])) if x)
    return (f"<div class='stk {html.escape(t, quote=True)}'><b>{esc(STICKERS.get(t, t.title()))} goes here</b>"
            + (f"<small>{esc(detail)}</small>" if detail else "") + "<small>(not in the export)</small></div>")

def story_native(sl: dict) -> str:
    """Instagram's own Classic text, as if typed on the phone."""
    r, out = sl["role"], ""
    if r == "hook":
        big = "" if len(sl["headline"].split()) > 8 else " style='font-size:84px'"
        out = f"<div class=nw><span class='n nh'{big}>{esc(sl['headline'])}</span></div>"
    elif r == "text": out = div("n", esc(sl["line"]), "" if len(sl["line"].split()) > 12 else "font-size:84px")
    elif r == "proof": out = (shot_img(sl) or div("n nbig", esc(sl["number"]))) + (div("n", esc(sl["label"])) if sl.get("label") else "")
    elif r == "ask":
        out = (div("n", esc(sl["lead"])) if sl.get("lead") else "")
        if sl.get("action"): out += div("n", esc(sl.get("cta", "reply"))) + div("n nbtn", esc(sl["action"]))
        out += div("n", esc(sl["support"])) if sl.get("support") else ""
    return out

def story_pack(sl: dict, kind: str, pack: str) -> str:
    """The creator's style pack fonts and colors, sized for a story."""
    r, big = sl["role"], kind != "photo"
    if r == "hook":
        return (eyebrow(sl.get("eyebrow"), pack, 84) + headline(sl["headline"], pack, 150 if big else 116, 4, width=STORY_W)
                + body(sl.get("support"), pack, 62))
    if r == "text":
        short = len(sl["line"].split()) <= 12
        return eyebrow(sl.get("eyebrow"), pack, 80) + (headline(sl["line"], pack, 108, 5, width=STORY_W) if short
                                                       else body(sl["line"], pack, 68))
    if r == "proof":
        return (eyebrow(sl.get("eyebrow"), pack, 90) + (shot_img(sl) or headline(sl["number"], pack, 300, 1, width=STORY_W))
                + body(sl.get("label"), pack, 68))
    if r == "ask":
        act = headline(sl["action"], pack, 150, 1, cls="d btn", width=STORY_W - 120) if sl.get("action") else ""
        return (body(sl.get("lead"), pack, 64) + (body(sl.get("cta", "reply"), pack, 64) if act else "") + act
                + body(sl.get("support"), pack, 60))
    die(f"unknown story frame: {r}")

def story_layout(sl: dict, kind: str, pack: str, style: str) -> str:
    inner = story_native(sl) if style == "native" else story_pack(sl, kind, pack)
    if sl.get("sticker"): inner += sticker(sl["sticker"])
    return box(kind, inner, center=True)

def shot_img(sl: dict) -> str:
    return (f"<img class=shot src='/photos/{html.escape(sl['screenshot'], quote=True)}' style='width:{sl['_shot_w']}px'>"
            if sl.get("screenshot") else "")

def kind_for(role: str, look: str, has_photo: bool) -> str:
    """photo / ground (the pack's plain slide) / card (the pack's breakaway card: proof and turn)."""
    if look == "graphic" or not has_photo: return "card" if role in ("proof", "turn") else "ground"
    if look == "photo": return "photo"
    return "card" if role in ("proof", "turn") else "photo"          # mix

def validate(plan: dict) -> None:
    problems, roles = [], STORY_ROLES if plan.get("format") == "story" else ROLES
    if plan.get("format", "carousel") not in FORMATS: problems.append(f"format must be one of {', '.join(FORMATS)}")
    for i, sl in enumerate(plan.get("slides", []), 1):
        need = roles.get(sl.get("role"))
        if need is None: problems.append(f"slide {i}: role must be one of {', '.join(roles)}"); continue
        if sl.get("sticker") and sl["sticker"].get("type", "poll") not in STICKERS:
            problems.append(f"slide {i}: sticker type must be one of {', '.join(STICKERS)}")
        for f in need:
            opts = f if isinstance(f, tuple) else (f,)
            if not any(sl.get(o) for o in opts): problems.append(f"slide {i} ({sl['role']}) needs {' or '.join(opts)}")
    if not plan.get("slides"): problems.append("plan.json has no slides")
    if problems: die("plan.json problems:\n  " + "\n  ".join(problems))

def lint_story(plan: dict) -> list[str]:
    """Story Kit checks. Flags, never blocks."""
    flags, frames = [], plan["slides"]
    texts = [v for s in frames for k, v in s.items() if isinstance(v, str) and k not in ("role", "bg", "photo", "screenshot", "_shot_w")]
    if any("—" in t for t in texts): flags.append("an em dash is in the copy")
    if len(frames) > 7: flags.append(f"{len(frames)} frames: stories past 7 lose people, so cut to the strongest")
    asks = sum(s["role"] == "ask" for s in frames)
    if asks != 1: flags.append(f"a story that sells has one ask; this has {asks}")
    for i, s in enumerate(frames, 1):
        words = sum(len(v.split()) for k, v in s.items() if isinstance(v, str) and k in ("headline", "line", "label", "lead", "support", "eyebrow"))
        if words > 25: flags.append(f"frame {i} has {words} words (people read a story in about 3 seconds)")
    kw = plan.get("keyword")
    if kw and not any(kw.lower() in (s.get("action") or "").lower() for s in frames): flags.append(f"the keyword {kw} is not on the ask frame")
    return flags

def lint(plan: dict) -> list[str]:
    """Copy checks from the carousel spec. Flags, never blocks."""
    if plan.get("format") == "story": return lint_story(plan)
    skip = {"role", "look", "photo", "screenshot", "action_style", "_shot_w"}
    texts = [v for s in plan["slides"] for k, v in s.items() if isinstance(v, str) and k not in skip]
    cap, flags = plan.get("caption", ""), []
    if any("—" in t for t in texts + [cap]): flags.append("an em dash is in the copy")
    trails = sum(t.rstrip().endswith("...") for t in texts)
    if trails > 3: flags.append(f"{trails} lines end in '...' (only where the next slide pays it off)")
    if sum(s["role"] == "closer" for s in plan["slides"]) != 1: flags.append("there should be exactly one closer slide")
    if len(plan["slides"]) > 20: flags.append(f"{len(plan['slides'])} slides: Instagram allows 20 per carousel")
    kw = plan.get("keyword")
    if kw and kw.lower() not in cap.lower(): flags.append(f"the keyword {kw} is not in the caption")
    return flags

# ---------------------------------------------------------------- photos
def cmd_photos(job: str, names: list[str]) -> None:
    from PIL import Image, ImageOps
    import pillow_heif; pillow_heif.register_heif_opener()
    out = cdir(job) / "photos"; out.mkdir(parents=True, exist_ok=True)
    srcs = [INBOX / n for n in names] if names else sorted(p for p in INBOX.iterdir() if p.suffix.lower() in IMG_EXT)
    missing = [p.name for p in srcs if not p.exists()]
    if missing: die(f"not in inbox/: {', '.join(missing)}")
    if not srcs: die("no photos in inbox/ (jpg, png, heic)")
    for p in srcs:
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB"); im.thumbnail((2400, 2400))
        name = safe_name(p.stem) + ".jpg"            # macOS screenshot names carry odd spaces; plan.json needs plain ones
        im.save(out / name, quality=92, subsampling=0)   # full color detail, so screenshot text stays crisp
        print(f"photo {p.name} -> photos/{name} ({im.width}x{im.height})")

def safe_name(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "photo"

def face_of(path: Path):
    """Biggest face as (cx, cy, h) in photo pixels, or None. Cached per photo (name + mtime)."""
    cache_p = path.parent / ".faces.json"
    cache = read_json(cache_p) if cache_p.exists() else {}
    key = f"{path.name}:{path.stat().st_mtime_ns}"
    if key in cache: return cache[key]
    import cv2, numpy as np
    try: cv2.setLogLevel(0)   # silence OpenCV's backend notes; they read like errors in her terminal
    except Exception: pass
    from PIL import Image
    im = Image.open(path); small = im.copy(); small.thumbnail((1200, 1200)); k = im.width / small.width
    det = cv2.FaceDetectorYN_create(str(YUNET), "", small.size, score_threshold=0.6)
    found = det.detect(cv2.cvtColor(np.array(small.convert("RGB")), cv2.COLOR_RGB2BGR))[1]
    face = None
    if found is not None:
        x, y, w, h = max(found, key=lambda f: f[2] * f[3])[:4]
        face = [float((x + w / 2) * k), float((y + h / 2) * k), float(h * k)]
    cache[key] = face; write_json(cache_p, cache)
    return face

def place_face(c: dict, fy: float, h: int = H) -> None:
    """Put the face center at screen y=fy, zooming in only as far as that needs (max 1.5x cover)."""
    cx, cy, fh = c["fc"]; cover = max(W / c["w"], h / c["h"])
    s = min(max(c["scale"], (h - fy) / (c["h"] - cy)), cover * 1.5)
    c["scale"] = s
    c["x"] = min(max(cx * s - W / 2, 0), c["w"] * s - W)
    c["y"] = min(max(cy * s - fy, 0), c["h"] * s - h)
    fs = fh * s
    c["face"] = [round(cx * s - c["x"] - fs * .45), round(cy * s - c["y"] - fs * .6), round(fs * .9), round(fs * 1.2)]

def crop_for(path: Path, face_y: float, face_h: float, h: int = H) -> dict:
    from PIL import Image
    iw, ih = Image.open(path).size
    cover = max(W / iw, h / ih)
    c = {"w": iw, "h": ih, "scale": cover, "x": (iw * cover - W) / 2, "y": 0.0}
    f = face_of(path)
    if f:
        c["fc"] = f; c["scale"] = max(cover, face_h * h / f[2]); place_face(c, face_y * h, h)
    return c

# ---------------------------------------------------------------- build
def cmd_build(job: str, pack: str, look: str, style: str = "pack", bg: str = "photo") -> None:
    d = cdir(job); cfg = pack_cfg(pack)
    if not (d / "plan.json").exists(): die(f"write projects/{job}/carousel/plan.json first")
    plan = read_json(d / "plan.json"); validate(plan)
    ts = text_settings(plan); TEXT.update({k: v for k, v in ts.items() if k != "css"})
    fmt = plan.get("format", "carousel"); story = fmt == "story"; F = FORMATS[fmt]; h = F["size"]["h"]
    photos_dir = d / "photos"
    order = [safe_name(Path(p).stem) + ".jpg" for p in (plan.get("photos") or sorted(p.name for p in photos_dir.glob("*.jpg")))]
    missing = [p for p in order if not (photos_dir / p).exists()]
    if missing: die(f"not in photos/ (run the photos step): {', '.join(missing)}")
    fonts = resolve_fonts(pack)

    # every point shares one headline size, so the body slides match
    points = [s for s in plan["slides"] if s["role"] == "point"]
    point_size = min((fit(s["headline"], pack, 150, 3)[0] for s in points), default=None)

    for sl in plan["slides"]:   # screenshots: as big as the slide allows, never past 2x their real pixels
        if sl.get("screenshot"):
            from PIL import Image
            sl["screenshot"] = safe_name(Path(sl["screenshot"]).stem) + ".jpg"
            if not (photos_dir / sl["screenshot"]).exists(): die(f"screenshot not in photos/: {sl['screenshot']}")
            with Image.open(photos_dir / sl["screenshot"]) as im: nw, nh = im.size
            room = STORY_W if story else TEXT_W
            w = min(room, nw * 2); w = min(w, (900 if story else 640) * nw / nh)
            sl["_shot_w"] = round(w)
            if nw * 2 < room * .6: print(f"check: the screenshot on the proof slide is small ({nw}px wide), so it may look soft")

    slides, photo_n = [], 0
    for sl in plan["slides"]:
        has_photo = bool(order) or bool(sl.get("photo"))
        if story:   # one choice for the whole story (photo or the pack's solid color), changeable per frame
            # the proof gets the pack's card, like a carousel's: a number or screenshot never sits on her face
            want = sl.get("bg") or ("color" if sl["role"] == "proof" else bg)
            kind = "photo" if want == "photo" and has_photo else ("card" if sl["role"] == "proof" else "ground")
            content = story_layout(sl, kind, pack, style)
        else:
            kind = "photo" if sl.get("look") == "photo" and has_photo else kind_for(sl["role"], sl.get("look", look), has_photo)
            content = layout(sl, kind, pack, point_size if sl["role"] == "point" else None)
        item = {"role": sl["role"], "kind": kind, "content": content}
        if kind == "photo":
            pick = order[photo_n % len(order)] if story and order else (order[PHOTO_SLOT[sl["role"]] % len(order)] if order else None)
            name = safe_name(Path(sl.get("photo") or pick).stem) + ".jpg"; photo_n += 1
            if not (photos_dir / name).exists(): die(f"slide photo not in photos/: {name}")
            item["photo"] = name; item["crop"] = crop_for(photos_dir / name, *(STORY_FACE if story else FACE[sl["role"]]), h)
            if sl["role"] == "turn": item["overlay"] = 1.25   # darker, so the turn line still reads as the shift
        slides.append(item)

    if (d / "carousel.json").exists(): shutil.copy(d / "carousel.json", d / "carousel.prev.json")
    write_json(d / "carousel.json", {"format": fmt, "size": F["size"], "safe": F["safe"], "move": F["move"],
                                     "pack": pack, "look": look, "style": style if story else None, "bg": bg if story else None,
                                     "keyword": plan.get("keyword"), "manychat": plan.get("manychat"), "dm": plan.get("dm"),
                                     "overlay": 1.0, "shadow": 0.28,
                                     "theme": {"fonts": {k: v["path"] for k, v in fonts.items()}, "vars": {**cfg["vars"], **F["vars"], **ts["css"]}},
                                     "slides": slides})
    cap = d / "caption.txt"
    if plan.get("caption"): cap.write_text(plan["caption"].strip() + "\n", encoding="utf-8")
    elif cap.exists(): cap.unlink()
    what = f"{len(slides)} story frames · {pack} · {'native Instagram' if style == 'native' else 'style pack'} · {bg}" if story \
        else f"{len(slides)} slides · {pack} · {look}"
    print("built", what)
    standins = sorted({f"{v['name']} (using {Path(v['path']).stem} for now; add {v['name']} in CapCut to use it)"
                       for v in fonts.values() if v["standin"] and not (story and style == "native")})
    for s in standins: print("font:", s)
    for f in lint(plan): print("check:", f)

# ---------------------------------------------------------------- local server (editor, render, check)
def make_handler(job: str):
    d = cdir(job)
    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            p = unquote(path.split("?")[0])
            if p.startswith("/photos/"): return str(d / "photos" / os.path.basename(p))
            if p.startswith("/slides/"): return str(d / "slides" / os.path.basename(p))
            if p.startswith("/fonts/"):   # by family; the path was resolved at build time (may be CapCut's copy)
                fam = os.path.basename(p)
                return read_json(d / "carousel.json")["theme"]["fonts"].get(fam, str(HERE / "editor" / "__none__"))
            if p.startswith("/editor/"): return str(HERE / "editor" / os.path.basename(p))
            if p in ("/", "/index.html"): return str(HERE / "editor" / "editor.html")
            return str(HERE / "editor" / "__none__")
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")     # every render reads the latest state
            super().end_headers()
        def reply(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.path.startswith("/state"): return self.reply(read_json(d / "carousel.json"))
            if self.path.startswith("/progress"): return self.reply(PROGRESS.get(job, {}))
            if self.path.startswith("/ping"): return self.reply({"ok": True, "job": job})
            if self.path == "/photos": return self.reply(sorted(p.name for p in (d / "photos").glob("*.jpg")))
            if self.path.startswith("/slides.zip"):     # every slide + the caption, one download
                import io, zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    for f in sorted((d / "slides").glob("slide-*.*"), key=lambda f: int(re.sub(r"\D", "", f.stem) or 0)):
                        z.write(f, f.name)
                    if (d / "caption.txt").exists(): z.write(d / "caption.txt", "caption.txt")
                data = buf.getvalue(); self.send_response(200)
                self.send_header("Content-Type", "application/zip"); self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{job}-carousel.zip"'); self.end_headers()
                return self.wfile.write(data)
            return super().do_GET()
        def do_POST(self):
            body_ = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                if self.path in ("/save", "/export"): write_json(d / "carousel.json", json.loads(body_))
                if self.path == "/save": return self.reply({"ok": True})
                if self.path == "/export":
                    n = export(job, self.server.server_address[1]); progress(job, stage="saving"); dest = deliver(job, open_it=False)
                    cap = (d / "caption.txt").read_text(encoding="utf-8").strip() if (d / "caption.txt").exists() else ""
                    st = read_json(d / "carousel.json")
                    return self.reply({"ok": True, "count": n, "folder": pretty_path(dest), "files": [f.name for f in slide_files(d / "slides")],
                                       "caption": cap, "app": FILE_APP, "notes": posting_notes(st, bool(cap)), "dm": st.get("dm") or "",
                                       "icloud": bool(icloud_dir()), "story": st.get("format") == "story"})
                if self.path == "/reveal": reveal(delivery_dir(job)); return self.reply({"ok": True})
                if self.path == "/icloud": return self.reply({"ok": True, "folder": pretty_path(to_icloud(job))})
                if self.path == "/reset":
                    st = read_json(d / "carousel.json"); cmd_build(job, st["pack"], st["look"]); return self.reply({"ok": True})
            except (Exception, SystemExit) as ex:
                return self.reply({"ok": False, "error": str(ex)}, 500)
            self.send_error(404)
        def log_message(self, *a): pass
    return Handler

FILE_APP = "Finder" if sys.platform == "darwin" else "File Explorer" if os.name == "nt" else "your files"

def slide_files(folder: Path) -> list[Path]:
    return sorted(folder.glob("slide-*.*"), key=lambda f: int(re.sub(r"\D", "", f.stem) or 0))

def delivery_dir(job: str) -> Path:
    """Where finished slides go: a folder named after the carousel in Downloads (where people look first)."""
    chosen = os.environ.get("REELS_EXPORT_DIR")              # same setting as reel exports; created if she set it
    dl = Path(chosen).expanduser() if chosen else Path.home() / "Downloads"
    kind = "story" if read_json(cdir(job) / "carousel.json").get("format") == "story" else "carousel"
    return (dl if chosen or dl.is_dir() else cdir(job)) / (job if job.endswith(kind) else f"{job}-{kind}")

def deliver(job: str, open_it: bool = True) -> Path:
    """Copy the exported slides + caption to Downloads, replacing an earlier export, and show them."""
    d = need_state(job); src = slide_files(d / "slides")
    if not src: die(f"No slides yet for {job}. Run render first.")
    dest = delivery_dir(job); dest.mkdir(parents=True, exist_ok=True)
    for old in slide_files(dest): old.unlink()
    for f in src: shutil.copy2(f, dest / f.name)
    if (d / "caption.txt").exists(): shutil.copy2(d / "caption.txt", dest / "caption.txt")
    notes = posting_notes(read_json(d / "carousel.json"), (d / "caption.txt").exists())
    (dest / "before-you-post.txt").write_text("Before you post\n\n" + "\n".join(f"- {x}" for x in notes) + "\n", encoding="utf-8")
    if open_it: reveal(dest)
    return dest

def posting_notes(st: dict, has_caption: bool = False) -> list[str]:
    """What she still does in Instagram: stickers (read from the sticker spaces actually on the frames, so editor
    changes count), the order, and the keyword's DM. Plain sentences: this is shown to her, and saved as a file."""
    story, notes = st.get("format") == "story", []
    unit = "frame" if story else "slide"
    notes.append(f"Post them in order, {unit} 1 first." + (" Paste the caption from caption.txt." if has_caption else ""))
    for i, sl in enumerate(st["slides"], 1):
        for t, detail in re.findall(r"""<div class=["']stk ([a-z]+)[^"']*["'][^>]*><b>[^<]*</b>(?:<small>((?:(?!</small>).)*)</small>)?""", sl.get("content", "")):
            what = STICKERS.get(t, t.title()).lower()
            detail = html.unescape(detail or "").replace("(not in the export)", "").strip(" ·")
            notes.append(f"{unit.title()} {i}: add a {what} sticker in the space left for it" + (f" ({detail})." if detail else "."))
    kw, dm = st.get("keyword"), st.get("dm")
    if kw:
        where = "story replies" if story else "comments on this post"
        if st.get("manychat"):
            notes.append(f"In ManyChat, set a keyword trigger for {kw} on {where}" + (", and paste in the DM message." if dm else "."))
        else:
            notes.append(f"People will send you {kw}" + (" in a DM" if story else " in the comments") + ". Answer each one"
                         + (" with the DM message." if dm else " with the link you promised."))
    return notes

def icloud_dir() -> Path | None:
    """iCloud Drive on a Mac that has it turned on, so the slides show up in the Files app on her phone."""
    p = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    return p if sys.platform == "darwin" and p.is_dir() else None

def to_icloud(job: str) -> Path:
    src, root = delivery_dir(job), icloud_dir()
    if not root: die("iCloud Drive is not turned on on this computer.")
    if not src.exists(): deliver(job, open_it=False)
    dest = root / src.name
    if dest.exists(): shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest

def pretty_path(p: Path) -> str:
    """Downloads › launch-carousel, not /Users/your-name/Downloads/launch-carousel."""
    cloud = icloud_dir()
    if cloud and p.is_relative_to(cloud): return " › ".join(("iCloud Drive",) + p.relative_to(cloud).parts)
    try: return " › ".join(p.relative_to(Path.home()).parts)
    except ValueError: return str(p)

def reveal(folder: Path) -> None:
    """Open the slides folder in Finder / File Explorer with slide 1 selected."""
    first = folder / "slide-1.jpg" if (folder / "slide-1.jpg").exists() else folder / "slide-1.png"
    if sys.platform == "darwin": subprocess.Popen(["open", "-R", str(first)] if first.exists() else ["open", str(folder)])
    elif os.name == "nt": subprocess.Popen(["explorer", f"/select,{first}"] if first.exists() else ["explorer", str(folder)])
    else: subprocess.Popen(["xdg-open", str(folder)])

def free_port() -> int:
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def serve(job: str, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(job))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

@functools.lru_cache(None)
def chrome() -> tuple[str, bool]:
    """(browser, is_headless_shell). The person's own Chrome or Edge first; then the HyperFrames browser."""
    cands = [os.environ.get("CHROME"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
             "/Applications/Chromium.app/Contents/MacOS/Chromium",
             "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    for root in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if root: cands += [os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
                           os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe")]
    cands += [shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "chrome", "msedge")]
    for c in cands:
        if c and os.path.exists(c): return c, False
    hf = _hf_browser()
    if hf: return hf, True
    die("No Chrome or Edge found. Install Google Chrome (free), or set CHROME to the browser's path.")

def _hf_browser() -> str | None:
    """The HyperFrames browser on this computer, when there is one this computer can run."""
    for c in sorted((Path.home() / ".cache" / "hyperframes" / "chrome").glob("**/chrome-headless-shell*"), reverse=True):
        if c.is_file() and os.access(c, os.X_OK) and c.suffix in ("", ".exe") and _runs_here(c): return str(c)
    return None

def intel_mac() -> bool:
    """Real Intel hardware (not an Apple-chip Mac running a Terminal under Rosetta)."""
    if sys.platform != "darwin": return False
    try: return subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True).stdout.strip() != "1"
    except Exception: return platform.machine() == "x86_64"

def _runs_here(exe: Path) -> bool:
    """An Apple-chip-only browser cannot run on an Intel Mac at all (it stalls instead of failing)."""
    if not intel_mac(): return True
    try: return "x86_64" in subprocess.run(["file", str(exe)], capture_output=True, text=True).stdout
    except Exception: return False

def physical_cores() -> int:
    """Real cores, not hyperthreads: a 2-core Intel i5 reports 4, and four browsers at once would crawl."""
    if sys.platform == "darwin":
        try: return max(1, int(subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True).stdout))
        except Exception: pass
    return max(1, (os.cpu_count() or 2) // 2)

_told_slow = threading.Event()

def own_profile() -> bool:
    """Each draw gets its own throwaway browser profile on Windows. There, headless Chromes all sharing her own
    Chrome/Edge profile drew some strips before their fonts and photos arrived (a stand-in serif, a missing photo).
    Not on a Mac: a fresh profile hangs headless there, so the Mac keeps drawing on her own profile."""
    return sys.platform == "win32"

def draw_workers() -> int:
    """How many strips draw at once. One on an Intel Mac (its graphics are software) and on Windows (side by side
    there, a strip could be drawn before its fonts and photo loaded); otherwise up to 4."""
    return 1 if intel_mac() or sys.platform == "win32" else max(1, min(4, physical_cores() - 1))

def _cpu_seconds(group: int) -> float | None:
    """CPU seconds a process group has used so far, or None when that can't be read (a stalled draw is only ever
    called on a reading that worked)."""
    try: rows = subprocess.run(["ps", "-A", "-o", "pgid=,time="], capture_output=True, text=True, timeout=20).stdout
    except Exception: return None
    total, seen = 0.0, False
    for row in rows.splitlines():
        got = row.split()
        if len(got) != 2 or got[0] != str(group): continue
        seen = True
        days, _, clock = got[1].rpartition("-")
        try:
            t = 0.0
            for part in clock.split(":"): t = t * 60 + float(part)
            total += t + (float(days) * 86400 if days else 0.0)
        except ValueError:
            return None
    return total if seen else None

def _draw(cmd: list[str]) -> subprocess.CompletedProcess | None:
    """One browser run, however long it takes while it is working. None when it has sat for BROWSER_STALL seconds
    using next to no CPU: on a Mac the browser can stop dead on a draw it does in 10 s when asked again (a Brand Kit
    preview, 10 minutes at 1 s of CPU, twice, 2026-10-29). Slow is never stopped: slow uses CPU."""
    if sys.platform == "win32":                       # no reading here: the browser runs to the end, as ever
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", start_new_session=True)
    last_cpu, since = None, time.monotonic()
    while True:
        try:
            out, err = p.communicate(timeout=min(10, BROWSER_STALL))
            break
        except subprocess.TimeoutExpired:
            pass
        cpu = _cpu_seconds(p.pid)
        if cpu is None or last_cpu is None or cpu - last_cpu > 0.2:
            last_cpu, since = cpu, time.monotonic()
        elif time.monotonic() - since >= BROWSER_STALL:
            try: os.killpg(p.pid, signal.SIGKILL)
            except OSError: pass
            p.communicate()
            return None
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, out, err)
    return subprocess.CompletedProcess(cmd, 0, out, err)

def run_chrome(args: list[str], url: str, scale: int = 1) -> subprocess.CompletedProcess:
    """No time limit, on purpose: an older Mac can take minutes and a killed render looks like a hang. A note after
    SLOW_NOTE seconds says it's still working instead. A throwaway --user-data-dir only where own_profile() says. A
    browser that has stopped dead (see _draw) gets one more go, on the HyperFrames browser when there is one."""
    exe, shell = chrome()
    prof = tempfile.mkdtemp(prefix="carousel-browser-") if own_profile() else None
    def line(x: str, sh: bool) -> list[str]:
        return [x, "--headless" if sh else "--headless=new", "--disable-gpu", "--hide-scrollbars",
                f"--force-device-scale-factor={scale}", "--font-render-hinting=none",
                *([f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check"] if prof else []), *args, url]
    def note():
        if not _told_slow.is_set():
            _told_slow.set(); print("still drawing: this computer is taking a while, which is fine. Leave it running.", flush=True)
    timer = threading.Timer(SLOW_NOTE, note); timer.daemon = True; timer.start()
    try:
        done = _draw(line(exe, shell))
        if done is None:
            print("The browser stopped responding on this draw, so I'm drawing it once more.", flush=True)
            spare = _hf_browser() or exe
            done = _draw(line(spare, spare != exe or shell))
        if done is None:
            die("The browser stopped responding twice while drawing. Your work is fine: quit Chrome and try again.")
        return done
    except subprocess.CalledProcessError as e: die(f"Chrome could not draw the slides:\n{(e.stderr or '')[-600:]}")
    finally:
        timer.cancel()
        if prof: shutil.rmtree(prof, ignore_errors=True)

def check(job: str, port: int) -> dict | None:
    out = run_chrome(["--virtual-time-budget=8000", "--dump-dom"], f"http://127.0.0.1:{port}/editor/check.html").stdout
    m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    try: return json.loads(html.unescape(m.group(1))) if m else None
    except ValueError: return None

def lift_faces(state: dict, report: dict) -> list[int]:
    """Text sitting on a face: slide the photo up (zooming a little if it must) until the text clears."""
    moved = []
    for s in report["slides"]:
        sl = state["slides"][s["n"] - 1]; c = sl.get("crop", {})
        if s.get("overlap", 0) > 0 and sl["kind"] == "photo" and "fc" in c:
            before = c["face"][1]
            place_face(c, c["fc"][1] * c["scale"] - c["y"] - s["overlap"] - 30, state.get("size", {}).get("h", H))
            if c["face"][1] < before: moved.append(s["n"])
    return moved

PROGRESS: dict = {}            # job -> {"stage", "done", "total"}: the editor polls it to show a real progress bar
_plock = threading.Lock()

def progress(job: str, **kw) -> None:
    with _plock: PROGRESS[job] = {**PROGRESS.get(job, {}), **kw}

def export(job: str, port: int, fmt: str = "jpg") -> int:
    """Slides drawn at 2x in small strips across parallel Chromes, each cut and shrunk to 1080 wide."""
    from PIL import Image
    d = cdir(job); out = d / "slides"; out.mkdir(exist_ok=True)
    for old in out.glob("slide-*.*"): old.unlink()
    st = read_json(d / "carousel.json"); n = len(st["slides"]); H = st.get("size", {}).get("h", 1350)
    progress(job, stage="drawing", done=0, total=n)
    def draw(a: int, tmp: str) -> None:
        b = min(a + BATCH, n); strip = Path(tmp) / f"strip-{a}.png"
        run_chrome([f"--window-size={W},{H * (b - a)}", f"--virtual-time-budget={4000 + 600 * (b - a)}",
                    f"--screenshot={strip}"], f"http://127.0.0.1:{port}/editor/render.html?from={a + 1}&to={b}", SCALE)
        im = Image.open(strip).convert("RGB")
        if im.size != (W * SCALE, H * SCALE * (b - a)): die(f"Chrome drew {im.size}, expected {(W * SCALE, H * SCALE * (b - a))}")
        for i in range(a, b):
            tile = im.crop((0, (i - a) * H * SCALE, W * SCALE, (i - a + 1) * H * SCALE)).resize((W, H), Image.LANCZOS)
            tile.save(out / f"slide-{i + 1}.{fmt}", **({"quality": 95, "subsampling": 0} if fmt == "jpg" else {}))
            with _plock: PROGRESS[job]["done"] += 1
    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(draw_workers()) as pool:   # strips draw side by side
        for f in [pool.submit(draw, a, tmp) for a in range(0, n, BATCH)]: f.result()
    progress(job, stage="finishing")
    beat_sheet(job, fmt)
    return n

def beat_sheet(job: str, fmt: str = "jpg") -> None:
    from PIL import Image, ImageDraw, ImageFont
    d = cdir(job); st = read_json(d / "carousel.json"); n = len(st["slides"])
    story = st.get("format") == "story"
    tw, th, g, lab, cols = (216, 384, 14, 40, 5) if story else (270, 338, 14, 40, 4)
    sheet = Image.new("RGB", (cols * (tw + g) + g, -(-n // cols) * (th + lab + g) + g), (244, 241, 234))
    draw, font = ImageDraw.Draw(sheet), ImageFont.truetype(str(FONTS / "Inter-Medium.ttf"), 22)
    for i, sl in enumerate(st["slides"]):
        x, y = g + (i % cols) * (tw + g), g + (i // cols) * (th + lab + g)
        sheet.paste(Image.open(d / "slides" / f"slide-{i + 1}.{fmt}").convert("RGB").resize((tw, th), Image.LANCZOS), (x, y))
        draw.text((x, y + th + 8), f"{i + 1} · {sl.get('role', '')}", font=font, fill=(40, 40, 40))
    sheet.save(d / "beat-sheet.jpg", quality=88)

def need_state(job: str) -> Path:
    d = cdir(job)
    if not (d / "carousel.json").exists(): die(f"No carousel in projects/{job}/carousel/ yet. Run build first.")
    return d

def cmd_render(job: str, fmt: str) -> None:
    d = need_state(job); port = free_port(); srv = serve(job, port); t = time.time()
    unit = "frame" if read_json(d / "carousel.json").get("format") == "story" else "slide"
    try:
        report = check(job, port)
        if report:
            st = read_json(d / "carousel.json"); moved = lift_faces(st, report)
            if moved:
                write_json(d / "carousel.json", st); report = check(job, port)
                print(f"moved the photo up so the text clears the face on {unit} " + ", ".join(map(str, moved)))
        n = export(job, port, fmt)
    finally:
        srv.shutdown()
    if report is None: print("check: the layout check could not run (slides exported anyway)")
    else:
        if report["missing_fonts"]: print("check: fonts did not load:", ", ".join(report["missing_fonts"]))
        for s in report["slides"]:
            for f in s["flags"]: print(f"check: {unit} {s['n']}: {f}")
    print(f"exported {n} {unit}s to projects/{job}/carousel/slides/ in {time.time() - t:.0f}s · "
          f"beat sheet: projects/{job}/carousel/beat-sheet.jpg")

def cmd_edit(job: str, port: int) -> None:
    need_state(job)
    try: serve(job, port := port or free_port())
    except OSError: serve(job, port := free_port())     # that port is busy (an editor left open): use another
    url = f"http://127.0.0.1:{port}/"; print("carousel editor:", url, "(Ctrl+C to stop)"); webbrowser.open(url)
    try:
        while True: time.sleep(3600)
    except KeyboardInterrupt: pass

VIDEO = ("*.mp4", "*.mov", "*.MOV", "*.MP4", "*.m4v")

def reel_video(reel: str) -> Path:
    """Her raw footage first (no burned-in captions or graphics), its biggest clip; else the finished reel;
    else a video file path she named."""
    if Path(reel).expanduser().is_file(): return Path(reel).expanduser()
    base = ENGINE / "projects" / reel
    raw = sorted({f for g in VIDEO for f in (base / "raw").glob(g)}, key=lambda f: f.stat().st_size, reverse=True)
    vids = raw or sorted({f for g in VIDEO for f in (base / "outputs").glob(g)})
    if not vids: die(f"No video found for {reel} (looked in projects/{reel}/raw and outputs).")
    if not raw: print("check: no raw footage for this reel, so the stills come from the finished reel and may show its captions")
    return vids[0]

def _word_times(vid: Path) -> list[tuple[float, float]]:
    """Word start/end times for this video: the finished reel's own transcript, or the raw clip's in transcript/words.json."""
    tj = vid.with_name(vid.stem + ".transcript.json")
    if tj.exists():
        return [(w["start"], w["end"]) for w in read_json(tj).get("words", []) if w.get("type", "word") == "word" and "start" in w]
    wj = vid.parent.parent / "transcript" / "words.json"
    if wj.exists():
        for c in read_json(wj).get("clips", []):
            if Path(c.get("path", "")).name == vid.name or c.get("clip") == vid.stem:
                return [(w["start"], w["end"]) for w in c.get("words", []) if "start" in w and "end" in w]
    return []

FFMPEG = ["ffmpeg"]     # the engine's own decoder for her clips (a list, so a test can stand in for it)
FRAME_STALL = 120       # seconds of no progress AT ALL before reading a clip counts as stuck. Never a time limit.

def _probe_video(vid: Path) -> tuple[float, int, float]:
    """(fps, frame count, seconds) of the clip's picture, from ffprobe; (0, 0, 0) when it can't be read."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=avg_frame_rate,r_frame_rate,nb_frames,duration:format=duration", "-of", "json", str(vid)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        j = json.loads(r.stdout or "{}"); st = (j.get("streams") or [{}])[0]
    except Exception:
        return 0.0, 0, 0.0
    def rate(x):
        try: a, b = str(x).split("/"); return float(a) / float(b) if float(b) else 0.0
        except Exception: return 0.0
    fps = rate(st.get("avg_frame_rate")) or rate(st.get("r_frame_rate")) or 30.0
    try: secs = float(st.get("duration") or (j.get("format") or {}).get("duration") or 0)
    except ValueError: secs = 0.0
    try: total = int(st.get("nb_frames") or 0)
    except ValueError: total = 0
    return fps, total or int(secs * fps), secs

def _ffmpeg_watched(args: list[str], seconds: float = 0.0, say: str = "") -> bool:
    """Run ffmpeg with no time limit, only a stall check: if it makes no progress at all for FRAME_STALL seconds it
    is stopped and False comes back (a decode that hangs, as an HEVC clip once did inside OpenCV, can't sit there
    forever). On a long read, `say` is printed with how far along it is."""
    cmd = [*FFMPEG, "-v", "error", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return False
    seen, moved, err = {}, [time.monotonic()], []
    def watch_out():
        for line in p.stdout:
            k, _, v = line.strip().partition("=")
            if k in ("frame", "out_time_us") and seen.get(k) != v: seen[k] = v; moved[0] = time.monotonic()
    def watch_err():
        for line in p.stderr: err.append(line)
    for fn in (watch_out, watch_err): threading.Thread(target=fn, daemon=True).start()
    told = time.monotonic()
    while p.poll() is None:
        time.sleep(0.25)
        if time.monotonic() - moved[0] > FRAME_STALL:
            p.kill(); p.wait(); return False
        if say and seconds and time.monotonic() - told > 20:
            try: done = min(99, int(int(seen.get("out_time_us", "0")) / 1e6 / seconds * 100))
            except ValueError: done = 0
            print(f"{say}: {done}%", flush=True); told = time.monotonic()
    return p.returncode == 0

def _sdr(vid: Path) -> str:
    """The HDR-to-standard-color filter for an HDR phone clip (stills come out grey otherwise), else nothing."""
    try:
        import hdr
        return f"{hdr.HDR2SDR}," if hdr.hdr_kind(str(vid)) else ""
    except Exception:
        return ""

def _frame_at(vid: Path, t: float, dst: Path, sdr: str = "") -> bool:
    """One full-quality still at `t` seconds, through ffmpeg."""
    return _ffmpeg_watched(["-ss", f"{max(0.0, t):.3f}", "-i", str(vid), "-an", "-sn", "-dn", "-frames:v", "1",
                            *(["-vf", sdr.rstrip(",")] if sdr else []), "-q:v", "2", str(dst)]) and dst.is_file()

def cmd_frames(job: str, reel: str, n: int = 8) -> None:
    """Pull her best stills from the reel: sharp, face in frame, spread across the video. Saved into photos/.
    ffmpeg reads the clip (one pass, small frames, HDR brought to standard color); OpenCV only scores the pictures.
    OpenCV used to decode the clip itself, and an iPhone HEVC clip could sit inside it at 0% CPU forever."""
    import cv2
    try: cv2.setLogLevel(0)
    except Exception: pass
    vid = reel_video(reel)
    fps, total, secs = _probe_video(vid)
    if total <= 0: die(f"Could not read {vid.name}.")
    det = cv2.FaceDetectorYN_create(str(YUNET), "", (320, 320), score_threshold=0.6) if YUNET.exists() else None
    # Moments between words: her mouth is closed there.
    ws = _word_times(vid)
    pauses = [(a[1] + b[0]) / 2 for a, b in zip(ws, ws[1:]) if b[0] - a[1] >= .18]
    step, lo = max(int(fps / 2), 1), int(fps * .5)
    hi = max(total - lo, 1)
    in_pause = set(int(t * fps) for t in pauses)
    extra = sorted(x for x in in_pause if 0 <= x < total and not (x % step == 0 and lo <= x < hi))[:1000]
    want = sorted({x for x in range(lo, hi) if x % step == 0} | set(extra))   # every half second + the pauses between words
    sdr = _sdr(vid)
    # One pass straight through (far faster than ~300 seeks): ffmpeg keeps exactly `want`, in order, 320 wide.
    sel = f"gt(not(mod(n\\,{step}))*gte(n\\,{lo})*lt(n\\,{hi})" + "".join(f"+eq(n\\,{x})" for x in extra) + "\\,0)"
    cands = []
    with tempfile.TemporaryDirectory(prefix="carousel-frames-") as tmp:
        ok = _ffmpeg_watched(["-i", str(vid), "-an", "-sn", "-dn", "-vf", f"select={sel},{sdr}scale=320:-2",
                              "-fps_mode", "passthrough", str(Path(tmp) / "c-%05d.png")], secs, f"reading {vid.name}")
        got = sorted(Path(tmp).glob("c-*.png"))
        if not ok and not got:
            die(f"Could not read {vid.name}: it stopped making progress for {FRAME_STALL // 60} minutes, so I stopped it. "
                "Your clip is fine. Try again with nothing else rendering, or pick the stills yourself in your visual editor (Snap).")
        if not ok: print(f"check: {vid.name} stopped partway through, so the stills come from the first {len(got)} spots")
        for f, png in zip(want, got):
            small = cv2.imread(str(png))
            if small is None: continue
            sharp = cv2.Laplacian(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
            face = 0.0
            if det is not None:
                det.setInputSize((small.shape[1], small.shape[0])); found = det.detect(small)[1]
                if found is not None: face = float(max(found[:, -1]))
            cands.append((sharp * (1.6 if face else 1.0) * (2.0 if f in in_pause else 1.0), f / fps, f))
    out = cdir(job) / "photos"; out.mkdir(parents=True, exist_ok=True)
    # Her snaps come first: the frames she grabbed in the visual editor (full quality, from her original clip),
    # her starred cover leading, then the rest in reel order. The engine's own picks only fill what's left.
    names, mine = [], _snaps(reel)
    for k, (src, at, _, _) in enumerate(mine[:n], 1):
        name = f"snap-{k:02d}.jpg"; shutil.copy2(src, out / name); names.append(f"{name} (your snap, {at:.0f}s)")
    taken = [ct for _, _, clip, ct in mine[:n] if clip == vid.name]      # her snaps' spots in THIS clip: no near-repeats
    # then the photos she added on her page (from her favorites, her inbox or her computer): hers, so all of them
    theirs = _kit_photos(reel)
    for k, src in enumerate(theirs, 1):
        name = f"photo-{k:02d}{src.suffix.lower()}"; shutil.copy2(src, out / name); names.append(f"{name} (your photo, {src.name})")
    room = max(0, n - len(mine[:n]) - len(theirs))
    cands.sort(reverse=True); picked = []
    for score, t, f in cands:                       # best first, at least 2 seconds apart, so they don't all look alike
        if len(picked) >= room or len(picked) + len(taken) >= n: break
        if all(abs(t - u) >= 2 for _, u, _ in picked) and all(abs(t - u) >= 2 for u in taken): picked.append((score, t, f))
    for k, (_, t, f) in enumerate(sorted(picked, key=lambda x: x[1]), 1):
        name = f"frame-{k:02d}.jpg"
        if _frame_at(vid, t, out / name, sdr): names.append(f"{name} ({t:.0f}s)")
    if not names: die(f"No usable frames in {vid.name}.")
    print(f"pulled {len(names)} stills from {vid.name}" + (f" (her {len(mine[:n])} snap{'s' if len(mine[:n]) != 1 else ''} first)" if mine else "")
          + (f" (and her {len(theirs)} photo{'s' if len(theirs) != 1 else ''})" if theirs else "") + ":", ", ".join(names))
    req = ENGINE / "projects" / reel / "review" / "kit-request.json"   # her page's pick is used: it won't steer the next one
    if req.exists():
        try: req.replace(req.with_name("kit-request.used.json"))
        except OSError: pass
    first = out / ("frame-01.jpg" if (out / "frame-01.jpg").exists() else "snap-01.jpg")
    if first.exists() and cv2.imread(str(first)).shape[1] < 1000: print("check: this video is under 1080 wide, so stills from it may look soft")


def _kit_photos(reel: str) -> list:
    """The photos she added for this carousel or story on her page (review/kit-request.json "photos"), in her order:
    files in her favorites or her inbox, checked there by the page. Missing ones are skipped."""
    try:
        req = read_json(ENGINE / "projects" / reel / "review" / "kit-request.json")
    except Exception:
        return []
    out = []
    for x in req.get("photos") or []:
        p = Path(str((x or {}).get("path", "")))
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"): out.append(p)
    return out


def _snaps(reel: str) -> list:
    """Her snaps from the visual editor for this reel: [(file, seconds into the reel, clip, seconds into that clip)],
    starred cover first, then reel order."""
    d = ENGINE / "projects" / reel / "thumbnails" / "snaps"
    try: idx = read_json(d / "snaps.json")
    except Exception: return []
    have = [(d / x["name"], float(x.get("at", x.get("t", 0))), x.get("clip"), float(x.get("clip_time", -99)))
            for x in idx.get("snaps", []) if (d / x.get("name", "")).is_file()]
    try:                                         # she ticked frames for this on her page (Make a carousel / a story)
        pick = read_json(ENGINE / "projects" / reel / "review" / "kit-request.json").get("frames")
        if isinstance(pick, list):                       # none ticked = she wants the engine's own picks only
            have = [h for h in have if h[0].name in set(pick)]
    except Exception:
        pass
    cover = idx.get("cover")
    return sorted(have, key=lambda x: (x[0].name != cover, x[1]))

def cmd_words(job: str) -> None:
    t = ENGINE / "projects" / job / "transcript"
    for name in ("cut-words.json", "words.json"):          # the kept words first: that's the finished script
        if (t / name).exists():
            data = read_json(t / name)
            words = data if isinstance(data, list) else [w for c in data.get("clips", []) for w in c.get("words", [])]
            print(" ".join((w.get("word") or w.get("w") or "").strip() for w in words).strip()); return
    die(f"no transcript in projects/{job}/transcript/. Transcribe the reel first (rough-cut's word-timings.sh).")

def main(argv=None) -> None:
    for stream in (sys.stdout, sys.stderr):    # a Windows console is often cp1252; never crash on a "·"
        try: stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError): pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("photos"); p.add_argument("job"); p.add_argument("files", nargs="*")
    p = sub.add_parser("build"); p.add_argument("job"); p.add_argument("--pack", default=None, help="default: her default pack, else Butter")
    p.add_argument("--look", default="mix", choices=["photo", "graphic", "mix"], help="carousel: photo, graphic or mix")
    p.add_argument("--style", default="pack", choices=["native", "pack"], help="story: native Instagram text or the style pack")
    p.add_argument("--bg", default="photo", choices=["photo", "color"], help="story: photos behind the words, or the pack's solid color")
    p = sub.add_parser("render"); p.add_argument("job"); p.add_argument("--png", action="store_true")
    p = sub.add_parser("edit"); p.add_argument("job"); p.add_argument("--port", type=int, default=0)
    p = sub.add_parser("words"); p.add_argument("job")
    p = sub.add_parser("deliver"); p.add_argument("job")
    p = sub.add_parser("frames"); p.add_argument("job"); p.add_argument("--from", dest="reel", required=True); p.add_argument("--n", type=int, default=8)
    a = ap.parse_args(argv)
    if a.cmd == "photos": cmd_photos(a.job, a.files)
    elif a.cmd == "build": cmd_build(a.job, a.pack or default_pack(), a.look, a.style, a.bg)
    elif a.cmd == "render": cmd_render(a.job, "png" if a.png else "jpg")
    elif a.cmd == "edit": cmd_edit(a.job, a.port)
    elif a.cmd == "words": cmd_words(a.job)
    elif a.cmd == "deliver": print("slides + caption saved to:", deliver(a.job))
    elif a.cmd == "frames": cmd_frames(a.job, a.reel, a.n)

if __name__ == "__main__":
    main()
