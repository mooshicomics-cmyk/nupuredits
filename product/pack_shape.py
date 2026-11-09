#!/usr/bin/env python3
"""pack_shape.py — the brand decisions a pack carries beyond fonts and colors, each one bounded.

Corners, the padding inside a card, how a card lifts, the hairline rule, the one entrance curve, whether numbers
count up, a label font's case and spacing, a few extra colors and two colors that never touch. A pack sets them
(product/design_md.py writes them from her DESIGN.md); the builder and her own designs read them HERE, so a value
is always clamped the same way and a pack can never break placement (a pack is an injection, never layout logic).

Every slot is optional. A pack that sets none of them renders exactly as before: each reader falls back to the
value it used before these slots existed, which is what DEFAULTS records.

Where they live in a pack block (creative-vault/style-packs.json, written through pack_write):
    "shape":  {"radius_card", "radius_label", "radius_frame", "pad_card", "shadow_card", "rule"}
    "motion": {"ease", "numbers", "pace"}
    "elements": {"label": {...}, "detail": {...}}     the label and detail fonts, shaped like any element
    "extra_colors": {"brass": "#9C7C4D"}               at most 3, for her own designs only, never a default role
    "apart": ["accent", "muted"]                       two palette roles that never touch
    "description": "..."                               shown with the pack
"""
import re

# What the builder drew before these slots existed. A pack without a slot gets exactly this.
DEFAULTS = {"radius_card": 28, "radius_label": 4, "radius_frame": 0, "pad_card": 40, "shadow_card": "lift", "rule": "none"}
# Three engine-owned card shadows: a pack names one, never writes a raw CSS shadow. "lift" is the count-up card's own.
SHADOWS = {"none": "none", "soft": "0 8px 26px rgba(0,0,0,.16)", "lift": "0 14px 44px rgba(0,0,0,.26)"}
RULES = ("none", "hairline")
NUMBERS = ("count-up", "still")
PACES = ("unhurried", "steady", "quick")
PILL = 999
EXTRA_MAX = 3
_CB = re.compile(r"^cubic-bezier\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)$")
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
ROLES = ("light", "dark", "muted", "accent", "pop2")


def check(field, value):
    """(clean value, problem or None) for one slot, by the same limits every reader uses."""
    if field in ("radius_card", "radius_label", "radius_frame"):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None, f"rounded.{field[7:]} is a number of reel px (0 to 80, or 999 for a pill), not {value!r}."
        v = int(round(value))
        if v >= PILL:
            return PILL, None
        if not 0 <= v <= 80:
            return None, f"rounded.{field[7:]} is 0 to 80 reel px (or 999 for a pill), not {v}."
        return v, None
    if field == "pad_card":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 24 <= value <= 120:
            return None, f"spacing.card_pad is 24 to 120 reel px, not {value!r}."
        return int(round(value)), None
    if field == "shadow_card":
        return (value, None) if value in SHADOWS else (None, f"elevation.card is none, soft or lift, not {value!r}.")
    if field == "rule":
        return (value, None) if value in RULES else (None, f"elevation.rule is none or hairline, not {value!r}.")
    if field == "ease":
        v = " ".join(str(value).split())
        m = _CB.match(v)
        if not m:
            return None, f"motion.ease is one cubic-bezier(x1, y1, x2, y2), not {value!r}."
        x1, y1, x2, y2 = (float(g) for g in m.groups())
        if not (0 <= x1 <= 1 and 0 <= x2 <= 1 and -1 <= y1 <= 2 and -1 <= y2 <= 2):
            return None, f"motion.ease: the x values sit from 0 to 1 and the y values from -1 to 2, not {value!r}."
        return f"cubic-bezier({x1:g}, {y1:g}, {x2:g}, {y2:g})", None
    if field == "numbers":
        return (value, None) if value in NUMBERS else (None, f"motion.numbers is count-up or still, not {value!r}.")
    if field == "pace":
        return (value, None) if value in PACES else (None, f"motion.pace is unhurried, steady or quick, not {value!r}.")
    if field == "label_tracking":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 0.3:
            return None, f"type.label_tracking is 0 to 0.3 (em), not {value!r}."
        return round(float(value), 3), None
    return None, f"{field} is not a pack slot."


def _block(pack):
    if isinstance(pack, dict):
        return pack
    try:
        import stylepack
        return stylepack.load(pack) or {}
    except Exception:
        return {}


def shape(pack):
    """The pack's shape slots, each clamped, every one filled (a slot the pack leaves out is DEFAULTS')."""
    raw = _block(pack).get("shape") or {}
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in raw:
            v, bad = check(k, raw[k])
            if not bad:
                out[k] = v
    return out


def is_set(pack, field):
    """True when the pack itself sets this shape slot (a reader keeps its old literal when it doesn't)."""
    raw = _block(pack).get("shape") or {}
    return field in raw and check(field, raw[field])[1] is None


def ease(pack):
    """The pack's one entrance curve as cubic-bezier(...), or None (each entrance keeps its own ease)."""
    v = (_block(pack).get("motion") or {}).get("ease")
    if not v:
        return None
    clean, bad = check("ease", v)
    return None if bad else clean


def ease_js(curve, name="pkEase"):
    """A GSAP ease for a cubic-bezier, as a plain JS function (GSAP takes a function as `ease`; no plugin, works
    offline). Newton steps with a bisection fallback, the way browsers solve the same curve."""
    x1, y1, x2, y2 = (float(g) for g in _CB.match(curve).groups())
    lead = "" if "." in name else "var "
    return (f"{lead}{name}=(function(){{var x1={x1:g},y1={y1:g},x2={x2:g},y2={y2:g};"
            "function b(t,a,c){return 3*a*t*(1-t)*(1-t)+3*c*t*t*(1-t)+t*t*t;}"
            "function d(t,a,c){return 3*a*(1-t)*(1-t)+6*(c-a)*t*(1-t)+3*(1-c)*t*t;}"
            "return function(p){if(p<=0)return 0;if(p>=1)return 1;var t=p,i;"
            "for(i=0;i<8;i++){var e=b(t,x1,x2)-p,s=d(t,x1,x2);if(Math.abs(e)<1e-5)return b(t,y1,y2);if(Math.abs(s)<1e-6)break;t-=e/s;}"
            "var lo=0,hi=1;t=p;for(i=0;i<30;i++){var v=b(t,x1,x2);if(Math.abs(v-p)<1e-5)break;if(v<p)lo=t;else hi=t;t=(lo+hi)/2;}"
            "return b(t,y1,y2);};})();")


def numbers(pack):
    v = (_block(pack).get("motion") or {}).get("numbers")
    return v if v in NUMBERS else "count-up"


def extra_colors(pack):
    """Her extra colors ({name: hex}), at most 3, for her own designs only."""
    ex = _block(pack).get("extra_colors") or {}
    out = {}
    for k, v in ex.items():
        name = re.sub(r"[^a-z0-9]+", "-", str(k).lower()).strip("-")
        if name and isinstance(v, str) and _HEX.match(v) and len(out) < EXTRA_MAX:
            out[name] = v
    return out


def apart(pack):
    """The two palette roles that never touch, as a tuple, or None."""
    a = _block(pack).get("apart")
    if isinstance(a, str):
        a = [x.strip() for x in a.split("/")]
    if isinstance(a, (list, tuple)) and len(a) == 2 and all(x in ROLES for x in a) and a[0] != a[1]:
        return tuple(a)
    return None


def _norm(h):
    h = str(h or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", h):
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def touches(palette, apart_pair, fg, bg):
    """True when fg on bg puts the two apart colors together (a red word on a green card)."""
    if not apart_pair or not palette:
        return False
    a, b = (_norm(palette.get(r)) for r in apart_pair)
    pair = {_norm(fg), _norm(bg)}
    return bool(a and b) and pair == {a, b}


def css_vars(pack):
    """The pk- variables her own designs read: corners, card padding, card shadow, the rule, the ease, extras.
    Always every one, filled with the pack's value or the default, so a design can use them unconditionally."""
    s = shape(pack)
    v = [f"--pk-radius-card:{s['radius_card']}px;", f"--pk-radius-label:{s['radius_label']}px;",
         f"--pk-radius-frame:{s['radius_frame']}px;", f"--pk-pad-card:{s['pad_card']}px;",
         f"--pk-shadow-card:{SHADOWS[s['shadow_card']]};",
         f"--pk-rule:{'2px solid var(--pk-dark)' if s['rule'] == 'hairline' else 'none'};"]
    e = ease(pack)
    v.append(f"--pk-ease:{e or 'cubic-bezier(0.16, 1, 0.3, 1)'};")
    v += [f"--pk-extra-{k}:{h};" for k, h in extra_colors(pack).items()]
    return v
