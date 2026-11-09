#!/usr/bin/env python3
"""design_md.py — her DESIGN.md becomes her own style pack, the way product/DESIGN-MD-SPEC.md says, every time.

    python3 product/design_md.py favorites/designs/<name>            # dry run: what it read, what it will make, any problem
    python3 product/design_md.py favorites/designs/<name> --write    # make the pack (through pack_write, recorded, update-safe)
    python3 product/design_md.py favorites/designs/<name> --json     # the same plan, for a skill to read
    ... --exact-colors   a brand she already has: her hexes kept exactly on every graphic; a color that can't carry
                         words gets a text-only shade, said with its hex (never a silent change)

Reads the engine's own format or the common web shape (name, colors, typography, rounded, spacing, components...):
web-only fields are dropped and named in ONE line, nothing else is silently ignored. Fonts go by name (installed on
her computer = CapCut has it); a file in the folder's fonts/ is used when she put one there. A font that can't be
found, a color pair that won't read, or a value out of range stops the write with the reason in plain words.
The `## Look:` sections are listed for the build-a-look skill; this script makes the pack, never a look.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SHIPPED = ("Butter", "Editorial", "Playful")
CASES = ("upper", "lower", "title", "sentence")   # sentence: a capital on the first word, the rest as written
ROLES = ("light", "dark", "muted", "accent", "pop2")
WEB_ONLY = ("rounded", "radius", "radii", "spacing", "space", "components", "shadows", "elevation", "breakpoints",
            "dark", "darkMode", "dark_mode", "buttons", "inputs", "nav", "grid", "layout", "motion", "icons", "version")
HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
SOFT_SHADOW = None                                           # the pack's own (the HyperFrames floor)
STRONG_SHADOW = "0 0 2px rgba(0,0,0,.85), 0 2px 4px rgba(0,0,0,.6), 0 6px 16px rgba(0,0,0,.45)"


class Problem(Exception):
    """A reason the pack can't be made yet, in her words."""


# ── reading: the YAML subset the spec uses (nested maps by indent, inline { k: v }, lists, quoted values) ──

def _scalar(v):
    v = v.strip()
    if not v:
        return ""
    if v[0] in "\"'" and v[-1:] == v[0]:
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(v) if re.fullmatch(r"-?\d+", v) else float(v) if re.fullmatch(r"-?\d*\.\d+", v) else v
    except ValueError:
        return v


def _inline(v):
    v = v.strip()
    if v.startswith("{") and v.endswith("}"):
        out = {}
        for part in re.split(r",(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$)", v[1:-1]):
            if ":" in part:
                k, _, x = part.partition(":")
                out[k.strip().strip("\"'")] = _scalar(x)
        return out
    if v.startswith("[") and v.endswith("]"):
        return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
    return _scalar(v)


def _strip_comment(line):
    out, q = [], None
    for i, ch in enumerate(line):
        if ch in "\"'" and (q is None or q == ch):
            q = None if q else ch
        if ch == "#" and q is None and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_yaml(text):
    root, stack = {}, [(-1, None)]
    stack[0] = (-1, root)
    lines = [_strip_comment(l) for l in text.splitlines()]
    for n, line in enumerate(lines):
        if not line.strip():
            continue
        ind = len(line) - len(line.lstrip(" "))
        body = line.strip()
        while stack and ind <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if body.startswith("- "):
            if isinstance(parent, list):
                parent.append(_inline(body[2:]))
            continue
        k, sep, v = body.partition(":")
        if not sep:
            continue
        k = k.strip().strip("\"'")
        if v.strip():
            parent[k] = _inline(v)
        else:                                                # a block: a map, or a list when the next line is "- "
            nxt = next((l for l in lines[n + 1:] if l.strip()), "")
            child = [] if nxt.strip().startswith("- ") else {}
            parent[k] = child
            stack.append((ind, child))
    return root


def read(folder):
    """(front matter dict, [look sections], the DESIGN.md path)."""
    p = os.path.join(folder, "DESIGN.md") if os.path.isdir(folder) else folder
    if not os.path.isfile(p):
        raise Problem(f"There's no DESIGN.md in {folder}. Put it in favorites/designs/<your pack name>/.")
    text = open(p, encoding="utf-8").read()
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        raise Problem("The DESIGN.md needs its settings between two --- lines at the very top.")
    fm = parse_yaml(m.group(1))
    looks = [{"name": h.strip(), "body": b.strip()} for h, b in re.findall(r"^##[ \t]*Look:[ \t]*([^\n]+)\n(.*?)(?=^##\s|\Z)", m.group(2), re.S | re.M)]
    _BODY[p] = m.group(2)
    return fm, looks, p


_BODY = {}                                                  # the prose under each read file's front matter


# ── the common web shape, mapped onto this spec ──

def _family(x):
    if isinstance(x, dict):
        x = x.get("fontFamily") or x.get("family") or x.get("font")
    if isinstance(x, str):
        return x.split(",")[0].strip().strip("\"'") or None
    return None


_TIERS = ("xxxl", "3xl", "xxl", "2xl", "xl", "lg", "l", "md", "m", "sm", "s", "xs")
_HEAD = re.compile(r"^(display|headline|heading|h1|title|hero)(?:[-_ ]?(.*))?$", re.I)


def _headline_key(ty):
    """The typography entry a headline comes from: an exact display/heading/headline/title, else the LARGEST
    tier of a family of them (display-xl over display-lg; h1 over everything)."""
    for k in ("display", "heading", "headline", "title"):
        if _family(ty.get(k)):
            return k
    best = None
    for k in ty:
        m = _HEAD.match(str(k))
        if not m or not _family(ty[k]):
            continue
        tier = (m.group(2) or "").lower()
        rank = -1 if m.group(1).lower() == "h1" else (_TIERS.index(tier) if tier in _TIERS else len(_TIERS))
        if best is None or rank < best[0]:
            best = (rank, k)
    return best[1] if best else None


def _first_key(ty, pattern):
    return next((k for k in ty if re.search(pattern, str(k), re.I) and _family(ty[k])), None)


def _em(x, size=None):
    """A letterSpacing as em: "0.2em" -> 0.2; "2px" on a 16px face -> 0.125; a bare number is em."""
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    m = re.fullmatch(r"\s*(-?\d*\.?\d+)\s*(em|px)?\s*", str(x or ""))
    if not m:
        return None
    v = float(m.group(1))
    if m.group(2) == "px":
        sz = _px(size)
        return round(v / sz, 3) if sz else None
    return v


def _px(x):
    """A web length in px: "20px" -> 20, "1rem" -> 16, 20 -> 20. Anything else (clamp(), %) -> None."""
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    m = re.fullmatch(r"\s*(-?\d*\.?\d+)\s*(px|rem|em)?\s*", str(x or ""))
    if not m:
        return None
    return float(m.group(1)) * (16 if m.group(2) in ("rem", "em") else 1)


def _hsv(h):
    h = h.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        hue = 0.0
    elif mx == r:
        hue = (60 * ((g - b) / d)) % 360
    elif mx == g:
        hue = 60 * ((b - r) / d) + 120
    else:
        hue = 60 * ((r - g) / d) + 240
    return hue, (d / mx if mx else 0.0), mx


def _hue_name(h):
    """red / orange / yellow / green / blue / purple / pink for a colored hex, None for a neutral."""
    hue, sat, val = _hsv(h)
    if sat < 0.2 or val < 0.15:
        return None
    for name, lo, hi in (("red", 345, 360), ("red", 0, 15), ("orange", 15, 45), ("yellow", 45, 70), ("green", 70, 170),
                         ("blue", 170, 255), ("purple", 255, 290), ("pink", 290, 345)):
        if lo <= hue < hi:
            return name
    return None


def _named_palette(c):
    """A web file names colors by what they ARE (accent-red, sage-forest, warm-cream, text-ink), not by role. Map
    them by name AND value onto the five roles; the rest go to extra. Returns (palette or None, extra, skipped,
    question or None). Pure white and pure black are never an extra (every reel has them already)."""
    hexes = {k: v for k, v in c.items() if isinstance(v, str) and HEX.match(v)}
    skipped = sorted(k for k in c if k not in hexes)                 # rgba(...) and friends: not a role candidate
    used, pal = set(), {}
    sat = lambda k: _hsv(hexes[k])[1]
    lum = lambda k: _lum(hexes[k])

    def named(pat, keep=lambda k: True):
        return [k for k in hexes if k not in used and re.search(pat, k, re.I) and keep(k)]

    def take(role, ks, key, rev=False):
        if ks:
            k = sorted(ks, key=key, reverse=rev)[0]
            pal[role] = hexes[k].upper()
            used.add(k)
            return k
        return None

    take("accent", named(r"accent|brand|primary", lambda k: sat(k) > 0.25)
         or [k for k in hexes if sat(k) > 0.35 and k not in used], sat, rev=True)
    take("dark", named(r"ink|text", lambda k: lum(k) < 0.2) or named(r"dark|black|charcoal|night", lambda k: lum(k) < 0.2)
         or [k for k in hexes if lum(k) < 0.05 and k not in used], lum)
    lights = named(r"cream|canvas|background|surface|paper|light|white|ivory|bone|linen|base", lambda k: lum(k) > 0.7)
    tinted = [k for k in lights if sat(k) > 0.01]                   # light is the card color: a tinted neutral reads warmer
    take("light", tinted or lights, lum, rev=True)
    take("muted", named(r"secondary|sage|muted|forest|olive|second|moss|slate", lambda k: sat(k) > 0.1)
         or [k for k in hexes if k not in used and sat(k) > 0.25 and 0.03 < lum(k) < 0.6], sat, rev=True)
    take("pop2", named(r"wheat|highlight|pop|tint|sand|butter|blush|tertiary", lambda k: lum(k) > 0.4)
         or [k for k in hexes if k not in used and lum(k) > 0.55 and sat(k) > 0.1], lum, rev=True)
    plain = lambda v: v.lower() in ("#fff", "#ffffff", "#000", "#000000")
    extra = {re.sub(r"^(text|color|brand)[-_]", "", k): hexes[k].upper() for k in hexes
             if k not in used and not plain(hexes[k]) and not (sat(k) < 0.02 and lum(k) > 0.9)}
    gaps = [r for r in ROLES if r not in pal]
    if not gaps:
        return pal, extra, skipped, None
    left = ", ".join(f"{k} {hexes[k]}" for k in hexes if k not in used) or "none left"
    jobs = {"light": "the light ground (cards, quiet space)", "dark": "the dark ink (words, lines)",
            "muted": "the quiet second color", "accent": "the pop (the key word)", "pop2": "a second, rarer pop"}
    return None, extra, skipped, ("which of your colors is " + " and ".join(jobs[g] for g in gaps) + f" (yours: {left})")


_APART = re.compile(r"[^.\n]*\b(?:never|don'?t|do not)\s+(?:touch|sit|meet|sits|touches|pair)[^.\n]*", re.I)


def _apart_from_prose(body, palette, names):
    """A rule that two colors never touch ("Red and green never touch"), as two palette roles, or None.
    A color is recognised by its hue word (red, green ...) or its own name in the file (accent-red, sage-forest)."""
    if not body or not palette:
        return None
    words = {}
    for role in ("accent", "muted", "pop2"):
        hn = _hue_name(palette[role])
        if hn:
            words.setdefault(hn, set()).add(role)
    for key, role in names.items():
        for tok in re.split(r"[-_ ]", key.lower()):
            if len(tok) > 2:
                words.setdefault(tok, set()).add(role)
    hues = {w for w in words if w in ("red", "orange", "yellow", "green", "blue", "purple", "pink")}
    for only in (hues, set(words)):                          # "red and green never touch" outranks a name in passing
        for sent in _APART.findall(body):
            hit = set()
            for w in only:
                if len(words[w]) == 1 and re.search(rf"\b{re.escape(w)}\b", sent, re.I):
                    hit |= words[w]
            if len(hit) == 2:
                return "/".join(r for r in ("accent", "muted", "pop2", "dark", "light") if r in hit)
    return None


def normalize(fm, body=""):
    """The spec's own shape, plus what was dropped (named once) and what is still missing (asked once).
    `body` (the prose under the front matter) is read for what a web file only says in words: a never-touch
    rule, the card shadow, the hairline and the entrance curve."""
    if "typography" not in fm and isinstance(fm.get("fonts"), dict):
        return fm, [], []
    out = {k: fm[k] for k in ("name", "mood", "base", "type", "hook_color", "shadow", "card", "description") if k in fm}
    dropped = sorted(k for k in fm if k in WEB_ONLY and k not in ("rounded", "motion", "elevation", "shadows"))
    ty = fm.get("typography") or {}
    fonts, typ = {}, dict(out.get("type") or {})
    hk = _headline_key(ty)
    head = _family(ty.get(hk)) if hk else None
    body_k = next((k for k in ("body", "text", "paragraph") if _family(ty.get(k))), None) or _first_key(ty, r"^body")
    cap = _family(ty.get(body_k)) if body_k else None
    acc_k = _first_key(ty, r"script|hand|accent|signature|decor")
    lab_k = _first_key(ty, r"eyebrow") or _first_key(ty, r"label|kicker|overline")
    det_k = _first_key(ty, r"mono|numeral|detail|code|number")
    for role, k in (("headline", hk), ("caption", body_k), ("accent", acc_k), ("label", lab_k), ("detail", det_k)):
        if k:
            fonts[role] = {"family": _family(ty[k])}
            w = ty[k].get("fontWeight") if isinstance(ty[k], dict) else None
            if role == "label" and isinstance(w, (int, float)) and w >= 600:
                fonts[role]["weight"] = int(w)               # a bold label: its bold face, not the regular
    if lab_k and isinstance(ty[lab_k], dict):
        L = ty[lab_k]
        trk = _em(L.get("letterSpacing"), L.get("fontSize"))
        if trk is not None:
            typ["label_tracking"] = round(trk, 3)
        tt = str(L.get("textTransform") or "").lower()
        fam = fonts["label"]["family"]
        said_caps = bool(re.search(rf"{re.escape(fam)}[^.\n]{{0,60}}\b(caps|uppercase)\b|\b(caps|uppercase)\b[^.\n]{{0,60}}{re.escape(fam)}", body, re.I))
        if tt in ("uppercase", "lowercase", "capitalize"):
            typ["label_case"] = {"uppercase": "upper", "lowercase": "lower", "capitalize": "title"}[tt]
        elif said_caps or (trk or 0) >= 0.1:
            typ["label_case"] = "upper"                      # a wide-tracked label is a caps label
    if typ:
        out["type"] = typ
    out["fonts"] = fonts
    mapped = {x["family"] for x in fonts.values()}
    c = fm.get("colors") or {}
    if isinstance(c, dict) and all(r in c for r in ROLES):
        out["colors"] = {r: c[r] for r in ROLES}
        for k in ("extra", "apart"):
            if k in c:
                out["colors"][k] = c[k]
    elif isinstance(c, dict):
        pal, extra, skipped, ask = _named_palette(c)
        if pal:
            out["colors"] = dict(pal)
            if extra:
                out["colors"]["extra"] = dict(list(extra.items())[:3])
                dropped += [k for k in list(extra)[3:]]
            names = {}
            for k, v in c.items():
                for role, hx in pal.items():
                    if isinstance(v, str) and v.upper() == hx:
                        names[k] = role
            ap = _apart_from_prose(body, pal, names)
            if ap:
                out["colors"]["apart"] = ap
            dropped += skipped
        else:
            prim = c.get("primary") or c.get("brand")
            sec = c.get("secondary") or c.get("accent")
            bg = c.get("background") or c.get("surface")
            if not prim and ask:                             # no seeds to design from: ask once, naming her colors
                out["_ask_colors"] = ask
            out["colors"] = {k: v for k, v in (("primary", prim), ("secondary", sec)) if v}
            if isinstance(bg, str) and HEX.match(bg):
                out["colors"]["dark_ground"] = _lum(bg) < 0.25
            dropped += sorted(k for k in c if k not in ("primary", "brand", "secondary", "accent", "background", "surface"))
    dropped += sorted(k for k in ty if k not in (hk, body_k, acc_k, lab_k, det_k) and _family(ty[k]) not in mapped)
    # shapes: web px become reel px at twice the value (a reel card fills about twice the width); a pill stays a pill
    r = fm.get("rounded") or fm.get("radius") or fm.get("radii")
    rnd = {}
    if isinstance(r, dict):
        for k, v in r.items():
            px = _px(v)
            if px is None:
                continue
            if re.search(r"pill|full|button|chip|tag|label", k, re.I):
                rnd.setdefault("label", 999 if px >= 50 else min(80, round(px * 2)))
            elif re.search(r"card|panel|box", k, re.I):
                rnd.setdefault("card", min(80, round(px * 2)))
            elif re.search(r"frame|image|photo|media", k, re.I):
                rnd.setdefault("frame", min(80, round(px * 2)))
    elif r is not None:
        dropped.append("rounded")
    if rnd:
        out["rounded"] = rnd
    comp = fm.get("components") if isinstance(fm.get("components"), dict) else {}
    cardc = next((v for k, v in comp.items() if re.fullmatch(r"card|card[-_]?default", str(k), re.I) and isinstance(v, dict)), None)
    if cardc and cardc.get("padding"):
        parts = [_px(x) for x in str(cardc["padding"]).split()]
        side = parts[1] if len(parts) > 1 else parts[0]
        if side:
            out["spacing"] = {"card_pad": max(24, min(120, round(side * 2)))}
    elev = {}
    sec = re.search(r"^##[^\n]*(?:elevation|depth|shadow)[^\n]*\n(.*?)(?=^##\s|\Z)", body, re.S | re.M | re.I)
    sect = sec.group(1) if sec else ""
    if re.search(r"\bcard lift\b|\bcards? (?:rises?|lifts?)\b", sect, re.I):
        elev["card"] = "lift"
    elif re.search(r"\bsoft shadow\b", sect, re.I):
        elev["card"] = "soft"
    elif re.search(r"\b(?:flat|no shadows?)\b", sect, re.I) and sect:
        elev["card"] = "none"
    if re.search(r"\b1px\b[^.\n]*\bhairline\b|\bhairline\b[^.\n]*\b1px\b", body, re.I):
        elev["rule"] = "hairline"
    if elev:
        out["elevation"] = elev
    mo = {}
    fmo = fm.get("motion") if isinstance(fm.get("motion"), dict) else {}
    ez = fmo.get("ease") or fmo.get("easing")
    m = re.search(r"cubic-bezier\([^)]*\)", str(ez or "") + " " + body, re.I)
    if m:
        mo["ease"] = m.group(0)
    if re.search(r"\bnumbers?\b[^.\n]*\b(?:count up|count-up|counts up|tick up)\b|\bcount(?:s)? up\b", body, re.I):
        mo["numbers"] = "count-up"
    if mo:
        out["motion"] = mo
    missing = [x for x, ok in (("mood: two or three words for how the look should feel", out.get("mood")),
                               ("an accent font (a script or handwritten face for small accent words)", fonts.get("accent")))
               if not ok]
    return out, sorted(set(str(d) for d in dropped)), missing


# ── checking ──

def _lum(h):
    h = h.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


LETTERS = {"es": "áéíóúñü", "pt": "ãõçáéíóúâêô", "fr": "éèêàçùâîôûë", "de": "äöüß", "it": "àèéìòù",
           "pl": "ąęłśźżćńó", "ro": "ăâîșț", "tr": "çğışöü", "nl": "ëï", "ru": "абвгдежзийклмнопрстуфхцчшщыэюя",
           "uk": "абвгґдеєжзиіїйклмнопрстуфхцчшщюя", "el": "αβγδεζηθικλμνξοπρσςτυφχψωάέήίόύώϊϋ",
           "ko": "가나다라마바사아자차카타파하엄마는요", "ht": "èòàÈÒÀ"}


def her_languages():
    """The languages her reels are in (what transcription detected), so a font is checked for the letters she uses.
    English, or no reels yet: nothing beyond a-z to check."""
    import glob
    langs = set()
    for p in glob.glob(os.path.join(ROOT, "projects", "*", "transcript", ".transcribe-diagnostics.json")):
        try:
            d = json.load(open(p, encoding="utf-8")).get("detected_languages") or []
            langs.update(str(x.get("language") if isinstance(x, dict) else x).lower()[:2] for x in d)
        except Exception:
            pass
    return sorted(l for l in langs if l in LETTERS)


def _font(folder, fam, weight=None):
    """A family's font file: one she put in fonts/ first, else what her computer (and so CapCut) has. weight >= 600
    (a bold label) prefers that family's bold face when there is one."""
    fd = os.path.join(folder, "fonts")
    if os.path.isdir(fd):
        key = re.sub(r"[^a-z0-9]", "", fam.lower())
        hits = [f for f in sorted(os.listdir(fd)) if f.lower().endswith((".ttf", ".otf")) and key and key in re.sub(r"[^a-z0-9]", "", f.lower())]
        if hits:
            return os.path.join(fd, _by_weight(hits, weight) or hits[0]), "her fonts folder"
    if weight:
        p = _system_font(fam, weight)
        if p and re.search(r"bold", os.path.basename(p), re.I):
            return p, "on your computer"
    try:
        import capcut_userfonts
        p = capcut_userfonts.resolve_font_file(fam)
    except Exception:
        p = None
    if p:
        return p, "installed"
    p = _system_font(fam)                                    # installed on her computer, not yet added in CapCut
    return (p, "on your computer") if p else (None, None)


def _by_weight(files, weight):
    """The bold face among a family's files (Bold over Semibold over ExtraBold), for weight >= 600."""
    if not weight or weight < 600:
        return None
    for pat in (r"(?<![a-z])bold", r"semi-?bold", r"extra-?bold|black"):
        hit = [f for f in files if re.search(pat, os.path.basename(f), re.I) and not re.search(r"italic", os.path.basename(f), re.I)]
        if pat == r"(?<![a-z])bold":
            hit = [f for f in hit if not re.search(r"(semi|extra|ultra|demi)-?bold", os.path.basename(f), re.I)]
        if hit:
            return sorted(hit, key=len)[0]
    return None


def _font_dirs():
    if sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts", "/System/Library/Fonts", "/System/Library/Fonts/Supplemental"]
    if os.name == "nt":
        return [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")]
    return [os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"), "/usr/share/fonts", "/usr/local/share/fonts"]


_FAMILIES = None


def _system_font(fam, weight=None):
    """A family installed in her computer's own font folders: by file name first (fast), then by each file's own
    family name (read once per run). The regular face when there is one."""
    global _FAMILIES
    want = " ".join(fam.split()).lower()
    key = re.sub(r"[^a-z0-9]", "", want)
    files = []
    for d in _font_dirs():
        try:
            files += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith((".ttf", ".otf", ".ttc"))]
        except OSError:
            pass
    named = [f for f in files if re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(f))[0].lower()).startswith(key)]
    pick = lambda fs: (_by_weight(fs, weight) or sorted(fs, key=lambda f: (not re.search(r"regular|book|roman", f, re.I), len(os.path.basename(f))))[0]) if fs else None
    if named:
        return pick(named)
    try:
        import capcut_userfonts
        if _FAMILIES is None:
            _FAMILIES = {}
            for f in files:
                n = capcut_userfonts.font_family(f)
                if n:
                    _FAMILIES.setdefault(" ".join(n.split()).lower(), []).append(f)
        return pick(_FAMILIES.get(want, []))
    except Exception:
        return None


def plan(folder, exact=False):
    """Everything --write would do, checked: {"name", "base", "fonts", "colors", "sets", "looks", "dropped",
    "missing", "problems", "notes"}. Nothing is written. exact=True (--exact-colors, a brand she already has): her
    hexes are kept exactly for every decoration, and any that can't carry words gets a text-only shade, said out
    loud with the hex, never a silent change."""
    import pack_recipe
    import pack_shape
    fm, looks, path = read(folder)
    spec, dropped, missing = normalize(fm, _BODY.get(path, ""))
    problems, notes, sets = [], [], []
    if spec.get("_ask_colors"):
        missing.append(spec.pop("_ask_colors"))
    name = str(spec.get("name") or "").strip()
    if not 2 <= len(name) <= 30:
        problems.append("The pack needs a name, 2 to 30 characters.")
    elif name in SHIPPED:
        problems.append(f"{name} is one of the engine's own packs. Give yours its own name (say, “My {name}”).")
    base = spec.get("base") or "Editorial"
    if base not in SHIPPED:
        problems.append(f"base must be Butter, Editorial or Playful, not {base!r}.")
        base = "Editorial"
    mood = str(spec.get("mood") or "").strip()
    if not mood and not any(m.startswith("mood") for m in missing):
        missing.append("mood: two or three words for how the look should feel")
    fonts, checked, langs = {}, set(), her_languages()
    for role in ("headline", "caption", "accent", "label", "detail"):
        f = (spec.get("fonts") or {}).get(role)
        fam = _family(f)
        if not fam:
            if role in ("label", "detail"):                  # optional: labels and numbers wear the caption font
                continue
            if not any(role in m for m in missing):
                missing.append(f"a {role} font")
            continue
        w = f.get("weight") if isinstance(f, dict) else None
        try:
            path, where = _font(folder, fam, weight=w) if w else _font(folder, fam)
        except TypeError:                                    # a stand-in _font (a test, the Brand Kit) takes two args
            path, where = _font(folder, fam)
        if not path and role in ("label", "detail"):         # optional: said once, and the pack is still made
            notes.append(f"{fam} isn't on your computer, so your {'labels' if role == 'label' else 'numbers'} use your "
                         f"other fonts for now. Install it (or put its file in this folder's fonts/) and run this again.")
            continue
        if not path:
            problems.append(f"I can't find the font {fam} on your computer. Install it (on Windows: right-click it, "
                            f"Install for all users), or put its file in this folder's fonts/, then run this again.")
        fonts[role] = {"family": fam, "file": path, "where": where}
        if path and path not in checked and langs:
            checked.add(path)
            try:                                         # the letters her reels use, beyond plain a-z
                import script_fonts
                info = script_fonts.face_info(path)
                if info:
                    gap = sorted({ch for l in langs for ch in LETTERS[l] if ord(ch) not in info[2]})
                    if gap:
                        notes.append(f"{fam} doesn't have {' '.join(gap)}. If your reels use those letters, they show in a "
                                     f"matching font instead (your pack stays the same).")
            except Exception:
                pass
    c = spec.get("colors") or {}
    palette = None
    if all(r in c for r in ROLES):
        bad = [r for r in ROLES if not (isinstance(c[r], str) and HEX.match(c[r]))]
        if bad:
            problems.append(f"These colors need to be #hex values: {', '.join(bad)}.")
        else:
            palette = {r: c[r] for r in ROLES}
            ink_ground = pack_recipe.contrast(palette["dark"], palette["light"])
            if ink_ground < 4.5:
                problems.append(f"dark {palette['dark']} on light {palette['light']} is {ink_ground}:1, and words need 4.5:1. "
                                + (f"Your {palette['dark']} stays exactly as is for graphics; for words, the nearest shade that reads is "
                                   f"{pack_recipe.text_safe(palette['dark'], palette['light'])}. Say which to use for words."
                                   if exact else
                                   f"The nearest dark that reads: {pack_recipe.text_safe(palette['dark'], palette['light'])}."))
            acc = pack_recipe.contrast(palette["accent"], palette["light"])
            if acc < 3.0:
                notes.append(f"accent {palette['accent']} is {acc}:1 on light: fine as a highlight over footage; on cards the "
                             f"engine uses a text-safe shade ({pack_recipe.text_safe(palette['accent'], palette['light'], 3.0)}).")
    else:
        for k in ("primary", "secondary"):
            if not (isinstance(c.get(k), str) and HEX.match(c[k])):
                problems.append(f"colors need a {k} #hex (or all five roles: light, dark, muted, accent, pop2).")
    extra, apart = {}, None
    ex = c.get("extra")
    if ex is not None:
        if not isinstance(ex, dict) or not all(isinstance(v, str) and HEX.match(v) for v in ex.values()):
            problems.append("colors.extra is a few named #hex colors (brass: \"#9C7C4D\").")
        elif len(ex) > pack_shape.EXTRA_MAX:
            problems.append(f"colors.extra holds at most {pack_shape.EXTRA_MAX} colors (rare details only), not {len(ex)}.")
        else:
            extra = {str(k): v.upper() for k, v in ex.items()}
    if c.get("apart") is not None:
        ap = str(c["apart"]).replace(" ", "")
        two = ap.split("/")
        if len(two) != 2 or two[0] == two[1] or not all(x in ROLES for x in two):
            problems.append(f"colors.apart names two of light, dark, muted, accent, pop2 (\"accent/muted\"), not {c['apart']!r}.")
        else:
            apart = two
    if exact and not problems:                               # her brand, said back to her: kept, and where words use a shade
        r = pack_recipe.build(name or "x", (palette or {}).get("accent") or c.get("primary"), (palette or {}).get("pop2") or c.get("secondary"),
                              mood, bool(c.get("dark_ground")))
        acc = (palette or {}).get("accent") or c.get("primary")
        ground = (palette or {}).get("light") or r["ground"]
        safe = pack_recipe.text_safe(acc, ground, 4.5)
        notes.append(f"Your colors stay exactly as they are on every graphic, card and accent ({acc}"
                     + (f", {(palette or {}).get('pop2') or c.get('secondary')}" if ((palette or {}).get('pop2') or c.get('secondary')) else "") + ").")
        if safe.lower() != str(acc).lower():
            notes.append(f"Words written in {acc} on your background would be hard to read, so words (only) use {safe}. "
                         f"Say if you'd rather keep words in another of your colors.")
    ty = spec.get("type") or {}
    known_type = ("hook_case", "card_case", "caption_case", "label_case", "hook_tracking", "card_tracking", "label_tracking",
                  "emphasis", "emphasis_words", "emphasis_punctuation")
    unknown_type = sorted(f"type.{k}" for k in ty if k not in known_type)
    label = {}
    if "label_case" in ty:
        if ty["label_case"] not in CASES:
            problems.append(f"type.label_case is upper, lower, title or sentence, not {ty['label_case']!r}.")
        else:
            label["case"] = ty["label_case"]
    if "label_tracking" in ty:
        v, bad = pack_shape.check("label_tracking", ty["label_tracking"])
        if bad:
            problems.append(bad)
        else:
            label["tracking"] = v
    copy = {}
    if "emphasis_words" in ty:
        ew = str(ty["emphasis_words"]).replace(" ", "")
        if not re.fullmatch(r"[1-3](?:-[1-3])?", ew) or (len(ew) == 3 and ew[0] > ew[2]):
            problems.append(f"type.emphasis_words is 1 to 3 words (\"2-3\"), not {ty['emphasis_words']!r}.")
        else:
            copy["emphasis_words"] = ew
    if "emphasis_punctuation" in ty:
        if not isinstance(ty["emphasis_punctuation"], bool):
            problems.append("type.emphasis_punctuation is true or false.")
        else:
            copy["emphasis_punctuation"] = ty["emphasis_punctuation"]
    for k, key in (("hook_case", "elements.headline.case"), ("card_case", "card.headline_case"), ("caption_case", "elements.caption.case")):
        if k in ty:
            if ty[k] not in CASES:
                problems.append(f"type.{k} is upper, lower, title or sentence, not {ty[k]!r}.")
            else:
                sets.append(f"{key}={ty[k]}")
    for k, key, fmt in (("hook_tracking", "welldone.headline_tracking", "{}"), ("card_tracking", "card.headline_tracking", "{}em")):
        if k in ty:
            v = ty[k]
            if not isinstance(v, (int, float)) or not -0.08 <= v <= 0.10:
                problems.append(f"type.{k} is a number from -0.08 to 0.10, not {v!r}.")
            else:
                sets.append(f"{key}={fmt.format(v)}")
    if ty.get("emphasis") == "italic":
        sets.append("card.emphasis_italic=true")
    elif ty.get("emphasis") not in (None, "accent"):
        problems.append(f"type.emphasis is italic or accent, not {ty['emphasis']!r}.")
    hc = spec.get("hook_color")
    if hc is not None:
        if hc == "white":
            sets.append("welldone.hook_color=#ffffff")
        elif hc == "accent":
            sets.append("welldone.hook_color=" + ((palette or {}).get("accent") or str(c.get("primary") or "")))
        elif isinstance(hc, str) and HEX.match(hc):
            sets.append(f"welldone.hook_color={hc}")
        else:
            problems.append(f"hook_color is white, accent or a #hex, not {hc!r}.")
    sh = spec.get("shadow")
    if sh == "strong":
        sets.append(f"welldone.text_shadow={STRONG_SHADOW}")
    elif sh not in (None, "soft"):
        problems.append(f"shadow is soft or strong, not {sh!r} (text over footage always keeps a shadow).")
    card = spec.get("card") or {}
    for k, ok in (("ground", ("light", "dark", "accent", "pop2")), ("ink", ("light", "dark"))):
        if k in card:
            if card[k] not in ok:
                problems.append(f"card.{k} is one of {', '.join(ok)}, not {card[k]!r}.")
            else:
                sets.append(f"card.{k}={card[k]}")
    if "rule" in card:
        sets.append(f"card.rule={'true' if card['rule'] else 'false'}")
    if apart and "ground" in card:                           # a never-touch pair can't meet on a card
        ink = card.get("ink", "dark")
        emph = "accent" if ty.get("emphasis") != "italic" else ink
        for fg in {ink, emph}:
            if {card["ground"], fg} == set(apart):
                problems.append(f"card.ground {card['ground']} puts {fg} words on it, and your colors.apart says "
                                f"{apart[0]} and {apart[1]} never touch. Pick another ground.")
    shape = {}
    for sec, fld, key in (("rounded", "card", "radius_card"), ("rounded", "label", "radius_label"), ("rounded", "frame", "radius_frame"),
                          ("spacing", "card_pad", "pad_card"), ("elevation", "card", "shadow_card"), ("elevation", "rule", "rule")):
        d = spec.get(sec)
        if isinstance(d, dict) and fld in d:
            v, bad = pack_shape.check(key, d[fld])
            if bad:
                problems.append(bad)
            else:
                shape[key] = v
    for sec, allowed in (("rounded", ("card", "label", "frame")), ("spacing", ("card_pad",)), ("elevation", ("card", "rule"))):
        d = spec.get(sec)
        if d is not None and not isinstance(d, dict):
            problems.append(f"{sec} is a few named values ({', '.join(allowed)}), not {d!r}.")
        elif isinstance(d, dict):
            unknown_type += [f"{sec}.{k}" for k in d if k not in allowed]
    motion, learn = {}, []
    mo = spec.get("motion")
    if mo is not None and not isinstance(mo, dict):
        problems.append(f"motion is a few named values (ease, hook, takeover, pace, sfx, opener_zoom, numbers), not {mo!r}.")
        mo = {}
    for k, v in (mo or {}).items():
        if k in ("ease", "numbers", "pace"):
            clean, bad = pack_shape.check(k, v)
            if bad:
                problems.append(bad)
            else:
                motion[k] = clean
        elif k in ("hook", "takeover"):
            try:
                import learned
                clean, _ = learned._coerce(f"effects.{k}", v)
                learn.append((f"effects.{k}", clean))
            except Exception as e:
                problems.append(f"motion.{k}: {e}")
        elif k == "sfx":
            m = {"none": "lighter", "lighter": "lighter", "standard": "normal", "normal": "normal", "heavy": "heavier", "heavier": "heavier"}
            if str(v) not in m:
                problems.append(f"motion.sfx is none, lighter, standard or heavy, not {v!r}.")
            else:
                learn.append(("sfx.density", m[str(v)]))
                if v == "none":
                    notes.append("motion.sfx none: reels get the lightest sound (the engine never goes fully silent on its own).")
        elif k == "opener_zoom":
            if not isinstance(v, bool):
                problems.append("motion.opener_zoom is true or false.")
            else:
                learn.append(("motion.opener_zoom", v))
        else:
            unknown_type.append(f"motion.{k}")
    desc = spec.get("description")
    desc = " ".join(str(desc).split())[:300] if desc else None
    native = "typography" not in fm
    unknown = sorted(k for k in fm if k not in ("name", "mood", "base", "fonts", "colors", "type", "hook_color", "shadow",
                                                "card", "typography", "description") + (("rounded", "spacing", "elevation", "motion") if native else ())
                     and k not in WEB_ONLY) + sorted(set(unknown_type))
    return {"name": name, "base": base, "mood": mood, "fonts": fonts, "palette": palette,
            "seeds": None if palette else {"primary": c.get("primary"), "secondary": c.get("secondary"),
                                           "dark_ground": bool(c.get("dark_ground"))},
            "sets": sets, "looks": [l["name"] for l in looks], "dropped": dropped, "missing": missing,
            "unknown": unknown, "problems": problems, "notes": notes,
            "label": label, "shape": shape, "motion": motion, "learn": learn, "extra": extra, "apart": apart,
            "copy": copy, "description": desc}


def make(folder, exact=False):
    """Everything --write would save, built but NOT saved: (plan, block, recipe, system_fonts). For a preview pack
    (the Brand Kit's directions) and for write(). Refuses with the plan's problems first."""
    import pack_recipe, pack_write
    p = plan(folder, exact=exact)
    if p["problems"] or p["missing"] or p["unknown"]:
        raise Problem("Not made yet:\n- " + "\n- ".join(p["problems"] + [f"Tell me {m}." for m in p["missing"]]
                                                       + [f"I don't know the field {u!r}." for u in p["unknown"]]))
    pal = p["palette"]
    if pal:
        r = pack_recipe.build(p["name"], pal["accent"], pal["pop2"], p["mood"], False)
        r["palette"] = dict(pal)
        r["ground"] = pal["light"]
        r["ink"] = pal["dark"]
        r["hands_off_accent"] = pack_recipe.text_safe(pal["accent"], pal["light"], 4.5)
    else:
        s = p["seeds"]
        r = pack_recipe.build(p["name"], s["primary"], s["secondary"], p["mood"], s["dark_ground"])
    f = p["fonts"]
    block = pack_recipe.clone_element_block(p["base"], f["headline"]["family"], f["caption"]["family"], f["accent"]["family"],
                                            r["palette"]["accent"])
    pack_write._set_values(block, r, p["sets"])
    # a font the build can't find by name on its own (her fonts folder, or her computer but not CapCut yet) goes in by path
    system = {x["family"]: x["file"] for x in f.values() if x.get("where") in ("her fonts folder", "on your computer") and x.get("file")}
    # every element that role drives points at that font by path ("SYSTEM:<family>"), or the build would look it up
    # by name, not find it (it isn't in CapCut yet) and quietly draw a stand-in face
    roles = {"headline": ["headline", "takeover"], "caption": ["caption"], "accent": ["thought_bubble", "accent_caption"]}
    sub_role = "accent"                                      # the subhead/eyebrow line always wears the accent font (the
                                                             # spec's fonts.accent; a pack's subhead_source names its SIZE source)
    for role, els in roles.items():
        fam = (f.get(role) or {}).get("family")
        if fam not in system:
            continue
        for el in els:
            e = (block.get("elements") or {}).get(el)
            if isinstance(e, dict):
                e["file"], e["font"] = f"SYSTEM:{fam}", fam
                e.pop("fallback_file", None)
        if role == "caption":
            block["karaoke_font_file"], block["karaoke_font_name"] = f"SYSTEM:{fam}", fam
        if role == sub_role:
            block["subhead_font_file"], block["subhead_font_name"] = f"SYSTEM:{fam}", fam
    # the label and detail fonts are elements like any other (sized like the caption); only when she has them
    els = block.setdefault("elements", {})
    for role in ("label", "detail"):
        fam = (f.get(role) or {}).get("family")
        if not fam:
            continue
        e = dict(els.get("caption") or {})
        e["font"], e["file"] = fam, (f"SYSTEM:{fam}" if fam in system else "")
        if role == "label":
            e["case"] = p["label"].get("case", e.get("case", "lower"))
            e["tracking"] = p["label"].get("tracking", 0.0)
        els[role] = e
    for key, val in (("shape", p["shape"]), ("motion", p["motion"]), ("extra_colors", p["extra"]), ("copy", p["copy"])):
        if val:
            block[key] = dict(val)
    if p["apart"]:
        block["apart"] = list(p["apart"])
    if p["description"]:
        block["description"] = p["description"]
    return p, block, r, system


def write(folder, force=False, exact=False):
    """Make the pack and save it through pack_write (recorded, so updates never delete it)."""
    import pack_write
    p, block, r, system = make(folder, exact=exact)
    try:
        msg = pack_write.apply(p["name"], block, r, force=force, system_fonts=system)
    except pack_write.PackWriteError as e:
        msg = str(e)
        if re.search(r"already|exists", msg, re.I):
            raise Problem(f"You already have a pack called {p['name']}. Give this one a new name, or say you want to "
                          f"replace it (--force).")
        raise Problem(f"The pack wasn't saved: {msg}")
    taught = []
    if p["learn"]:                                           # her hook / takeover / sound / opener choices, for this pack only
        try:
            import learned
            for field, value in p["learn"]:
                learned.add(field, value, note=f"from {os.path.basename(os.path.abspath(folder))}/DESIGN.md", scope={"pack": p["name"]})
                taught.append(f"{field}={value}")
        except Exception as e:
            taught.append(f"(her motion choices weren't saved: {e})")
    return (msg + (f"\nRemembered for {p['name']} reels: {', '.join(taught)}." if taught else "")), p


def _say(p):
    out = [f"Pack: {p['name'] or '(no name)'}  ·  starts from {p['base']}  ·  mood: {p['mood'] or '(missing)'}"]
    for role, x in p["fonts"].items():
        out.append(f"  {role} font: {x['family']}" + (f" ({x['where']})" if x.get("where") else "  (not found)"))
    out.append("  colors: " + (", ".join(f"{k} {v}" for k, v in p["palette"].items()) if p["palette"]
                               else f"from {p['seeds']['primary']} and {p['seeds']['secondary']} (the engine designs the rest)"))
    if p.get("extra"):
        out.append("  extra colors (for your own looks): " + ", ".join(f"{k} {v}" for k, v in p["extra"].items()))
    if p.get("apart"):
        out.append(f"  never touch: {p['apart'][0]} and {p['apart'][1]}")
    if p.get("label"):
        out.append("  labels: " + ", ".join(f"{k} {v}" for k, v in p["label"].items()))
    if p["sets"]:
        out.append("  type and cards: " + "; ".join(p["sets"]))
    if p.get("shape"):
        out.append("  shapes: " + ", ".join(f"{k} {v}" for k, v in p["shape"].items()))
    if p.get("motion") or p.get("learn"):
        out.append("  motion: " + ", ".join([f"{k} {v}" for k, v in (p.get("motion") or {}).items()]
                                          + [f"{k} {v}" for k, v in (p.get("learn") or [])]))
    if p.get("copy"):
        out.append("  card and hook copy: " + ", ".join(f"{k} {v}" for k, v in p["copy"].items()))
    if p["looks"]:
        out.append(f"  new looks to design with you after: {', '.join(p['looks'])}")
    if p["dropped"]:
        out.append(f"  left out (web layout, no place in a reel): {', '.join(p['dropped'])}")
    for n in p["notes"]:
        out.append(f"  note: {n}")
    for m in p["missing"]:
        out.append(f"  ? still need: {m}")
    for u in p["unknown"]:
        out.append(f"  ? I don't know the field {u!r}")
    for x in p["problems"]:
        out.append(f"  ⛔ {x}")
    return "\n".join(out)


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip().split("\n\n")[1]); return 2
    folder = argv[0]
    try:
        if "--write" in argv:
            msg, p = write(folder, force="--force" in argv, exact="--exact-colors" in argv)
            print(_say(p)); print(msg); return 0
        p = plan(folder, exact="--exact-colors" in argv)
        print(json.dumps(p, indent=1) if "--json" in argv else _say(p))
        return 1 if (p["problems"] or p["missing"] or p["unknown"]) else 0
    except Problem as e:
        print(str(e)); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
