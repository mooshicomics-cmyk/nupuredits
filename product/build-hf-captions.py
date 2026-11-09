#!/usr/bin/env python3
"""build-hf-captions.py — the KINETIC-CAPTION ENGINE. Emits a HyperFrames composition (index.html) → render
to a transparent .mov → inject as flag=2 PIP overlay(s) (see build-overlay.py). Three styles:
  • single   — one-word SNAP captions, Helvetica, low, TIGHT tracking, white + butter keywords
  • build    — the pack's accent font sentence builds word-by-word IN PLACE, karaoke highlight on the spoken word
  • takeover — full-screen, EVERY word its own line (vertical stack), held; hero line = biggest CAPS
Set HF_MODE=single|build|takeover to emit ONE style (split overlays — one named PIP track per style).

╔═ UNIVERSAL RULES (locked — apply to EVERY reel; see creative-vault/STYLES.md "Kinetic Type Overlays") ═╗
 • Ask kinetic-overlay vs native captions before any text-on-video.
 • KEEP APOSTROPHES ("it's"); strip only sentence punctuation on single+takeover; build keeps all punct.
 • Lowercase EVERYTHING except "God" (case_fix).
 • NO OVERLAP: clamp each clip's end to the next clip's start; no min-duration floor that overlaps.
 • Captions run EVERYWHERE — never blank a section.
 • Safe zone = product/safe_zones.py (x 90–990 / y 270–1620; the bottom is the creator's explicit 300px call). Font-by-job. The
  keyword/highlight/payoff color is the active PACK's accent_color (never an imposed default).
 • Fix caption text in edit-timeline.json (not by ear); on-screen text is the creator's to set.
 • Trim overlay dead space > DEAD_GAP s (one segment per active span), at render time too (render_spans.py).
   NAME every layer (track + clip).
 • Verify the composition in the browser before rendering. SFX stay native (never baked into the overlay).
╚══════════════════════════════════════════════════════════════════════════════════════════════════════╝
Deterministic (no random/date).
"""
import json, os, html, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import text_effects  # SHARED named text-animation vocabulary (takeover intro motion; rendered-output only)
import safe_zones    # SHARED legibility floors (MIN_PX) per role
import script_fonts  # Cyrillic a pack face lacks: drawn (and measured) on a matching bundled face
try:
    from PIL import ImageFont   # measure real glyph widths so text fits the IG safe zone (Bug #5)
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False           # no PIL -> fit is a no-op (we only ever SHRINK, so this never enlarges text)

# ── PER-REEL CONFIG — JOB from env; ranges/keywords from projects/<JOB>/caption-plan.json (loaded below) ─
JOB = os.environ.get("JOB")                         # projects/<JOB> — REQUIRED (runs on YOUR reel, not a sample)
if not JOB:
    raise SystemExit("Set JOB=<your reel folder under projects/>   e.g.  JOB=my-reel python3 product/build-hf-captions.py")
COMP = os.environ.get("COMP", "reel")               # generic composition id (previously a personal reel slug)
# DUR / BUILD_RANGES / TAKEOVER_KEYS / HERO_KEYS / KEYWORDS / YIELD are loaded from caption-plan.json below.
# ──────────────────────────────────────────────────────────────────────────────────────────────────────

# ── STYLE PACK (SWAPPABLE — fonts + colors + sizes per LAYOUT). A resolved STYLE_PACK is REQUIRED. ─────────
# Future style packs swap ONLY these tokens (and add @font-face `faces` for new fonts). The LAYOUTS and
# behavior never change — that's the whole point (the creator: templated layouts, swap fonts/colors per pack).
# Layout roles: caption (snap) · build (line-build karaoke) · takeover (full-screen vertical stack).
# (Title layout lives in hf-intro/; thought-bubble is a native CapCut component — both share these tokens.)
# NO DEFAULT TYPOGRAPHY: every font comes from the active style pack (rebuilt below from
# creative-vault/style-packs.json). This placeholder carries only the LAYOUT tokens and NEUTRAL system fonts;
# a shipped build without STYLE_PACK fails loud (see the guard below) rather than ever guessing a font — so
# the engine can never accidentally reach for a font that is not part of a pack.
STYLE = {
    "name": "(pack required)",
    "fonts": {"caption": "'Helvetica Neue',Arial,sans-serif",   # snap read-along
              "build":   "system-ui,'Helvetica Neue',Arial,sans-serif",     # sentence build + karaoke
              "takeover":"system-ui,'Helvetica Neue',Arial,sans-serif"},     # full-screen vertical stack + hero
    "faces": [],                                                # @font-face entries come from the pack only
    "color": {"base": "#ffffff", "accent": "#ffffff", "dim": "rgba(255,255,255,.42)"},
    "size":  {"caption": 66, "build": 82, "takeover": 100, "hero": 132},
    "track": {"caption": -3, "takeover": 1},                    # letter-spacing (px); caption = TIGHT
    "y":     {"caption": -0.40, "build": -0.24, "takeover": 0.0},  # positions (LAYOUT-STANDARDS §1)
}
# ──────────────────────────────────────────────────────────────────────────────────────────────────────

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HF = f"{ROOT}/projects/{JOB}/hf-captions"
# scaffold the hf-captions dir from the SHIPPED generic template if not set up yet (never copies a personal reel)
if not os.path.exists(f"{HF}/meta.json"):
    import shutil
    _tpl = f"{ROOT}/product/templates/hf-reel"
    os.makedirs(f"{HF}/fonts", exist_ok=True)
    for _f in ("hyperframes.json", "package.json", "meta.json"):
        if os.path.exists(f"{_tpl}/{_f}"):
            shutil.copy(f"{_tpl}/{_f}", f"{HF}/{_f}")
_tl_path = f"{ROOT}/projects/{JOB}/edit-timeline.json"
if os.path.exists(_tl_path):
    TL = json.load(open(_tl_path, encoding="utf-8"))
else:
    # No edit-timeline.json yet. A NORMAL rough cut never writes one (it only produces
    # transcript/cuts.json + outputs/<job>.transcript.json), and the only other producer,
    # prep-reel.py, DELETES the first clip (a hook-excision workflow) — so we must NOT run it on
    # a normal job. Auto-generate the COMMON-CASE timeline (keep EVERY clip, drop nothing) from
    # the rough cut's own outputs via make-edit-timeline.py (loaded from its hyphenated path).
    import importlib.util as _ilu
    _gen_path = f"{ROOT}/product/make-edit-timeline.py"
    try:
        _spec = _ilu.spec_from_file_location("make_edit_timeline", _gen_path)
        _gen = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_gen)
        TL = _gen.build(JOB, root=ROOT)
        print(f"edit-timeline.json was missing — auto-generated (common case, no clips dropped).")
    except SystemExit:
        raise
    except Exception as _e:
        raise SystemExit(
            f"edit-timeline.json not found for job '{JOB}', and auto-generation failed: {_e}\n"
            f"Generate it manually:  python3 product/make-edit-timeline.py {JOB}\n"
            f"(Do NOT run prep-reel.py on a normal cut — it deletes the first clip.)")
# per-reel content (optional): safe defaults = all single-mode, no forced highlights. Nothing reel-specific hardcoded.
_cp_path = f"{ROOT}/projects/{JOB}/caption-plan.json"
_cp = json.load(open(_cp_path, encoding="utf-8")) if os.path.exists(_cp_path) else {}
# NAMED takeover intro effect (rendered-overlay vocabulary). Default per text_effects.DEFAULTS;
# override per reel with caption-plan "effects":{"takeover":...}. "rise" pins the original fade+rise.
TK_FX = text_effects.resolve(_cp, "takeover")
BUILD_RANGES  = [tuple(r) for r in _cp.get("build_ranges", [])]
def _fold(s):   # curly quotes (the Mac default when typing a plan) → straight, so a phrase matches the transcript
    return str(s).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
TAKEOVER_KEYS = [_fold(k).lower() for k in _cp.get("takeover_keys", [])]
HERO_KEYS     = [_fold(k).lower() for k in _cp.get("hero_keys", [])]
KEYWORDS      = set(_fold(k).lower() for k in _cp.get("keywords", []))
# KARAOKE-FIRST (per-reel): when build_default is on, every sentence longer than single_max_words is a
# karaoke word-BUILD; only short punchy fragments stay single-snap. caption_weight/size bold the singles.
BUILD_DEFAULT    = bool(_cp.get("build_default", False))
SINGLE_MAX_WORDS = int(_cp.get("single_max_words", 4))
CAP_WEIGHT       = _cp.get("caption_weight", 600)
CAP_SIZE         = _cp.get("caption_size")            # None -> STYLE pack size
YIELD         = tuple(_cp.get("yield", (0.0, 0.0)))
# MULTI-YIELD (locked): a reel with 2+ rendered overlays (takeovers / bubbles) needs captions to hide under
# EACH overlay window, not just one range. `yields` = list of [start,end]; `yield` stays for the single case.
YIELDS        = [tuple(r) for r in _cp.get("yields", [])]
def _yielded(t):
    if YIELD[0] <= t < YIELD[1]: return True
    return any(a <= t < b for a, b in YIELDS)
_YSTARTS = sorted([a for a, b in ([YIELD] if YIELD[1] > YIELD[0] else []) + YIELDS])
def _clamp_yield(start, end):
    """Clamp a caption clip's END so it never lingers into a yield window (an overlay owns the screen there).
    A single word holds up to SINGLE_MAX_HOLD; without this it could bleed ~0.9s past an overlay's start."""
    for a in _YSTARTS:
        if start < a < end: return a
    return end
_wends = [w.get("e", w.get("end", 0)) for b in TL.get("beats", []) for w in b.get("words", [])]
DUR = float(_cp.get("duration") or ((max(_wends) + 0.5) if _wends else 0.0))
SINGLE_MAX_HOLD = 0.9   # a single word holds at most this long, but always clears when the next word starts
DEAD_GAP = 3.0          # trim overlay dead space: split the track wherever text is absent > this many seconds
HF_MODE = os.environ.get("HF_MODE", "")   # "single" | "build" | "takeover" -> emit only that style

# ── STYLE-PACK OVERRIDE ── STYLE_PACK=<name> rebuilds STYLE from creative-vault/style-packs.json ──────────
# Maps pack elements -> engine layout roles: caption(snap)<-caption · build(karaoke)<-accent_caption ·
# takeover/hero<-takeover. Per-element CASE + line-height + drop-shadow come from the pack. Pack sizes are
# CapCut units -> px via SIZE_SCALE (the one calibration knob). No pack set = unchanged Naptime Default.
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STYLE_PACK = os.environ.get("STYLE_PACK", "")
if not STYLE_PACK:
    # A resolved style pack is REQUIRED — every font/size/color is pack dressing (Layer 3). Refusing to fall
    # back to a hardcoded default is what keeps the engine from ever silently reaching for a font that is not
    # part of a pack (the creator's rule: fonts come from the packs, never accidentally from anywhere else).
    raise SystemExit(
        "[build-hf-captions] Set STYLE_PACK=<pack> before running "
        "(e.g. STYLE_PACK=Butter — one of Editorial | Butter | Playful, or a custom pack in "
        "creative-vault/style-packs.json). Shipped captions never default to a font.")
SIZE_SCALE = float(os.environ.get("SIZE_SCALE", "6.0"))   # px per CapCut size unit (calibrate once, then lock)
CASE   = {"caption": "lower", "build": "lower", "takeover": "lower", "hero": "lower"}   # default behavior
LH     = {"build": 1.22, "take": 1.10, "hero": 1.06}
SHADOW = {"cap": "0 6px 32px rgba(0,0,0,.55)", "build": "0 6px 32px rgba(0,0,0,.55)", "take": "0 6px 32px rgba(0,0,0,.55)"}  # placeholder floor; the required pack overrides via stylepack.text_shadow()
if STYLE_PACK:
    import stylepack, shutil, capcut_userfonts, packbuild
    _fdir = f"{HF}/fonts"; os.makedirs(_fdir, exist_ok=True)
    def _face(el):
        # Resolve the real font file: bundled OFL first, else whatever CapCut has on this machine
        # (userFontData map — cloud-cache or Library/Fonts). Lets the engine animate ANY font the buyer
        # added in CapCut without us shipping it. Copy in under a unique name (cache files are all "font.ttf").
        src = capcut_userfonts.resolve_font_file(el.get("font"), el.get("file"))
        ext = os.path.splitext(src)[1] if src else ".ttf"
        base = ("".join(c for c in (el.get("font") or "font") if c.isalnum()) or "font") + ext
        if src:
            try: shutil.copy(src, f"{_fdir}/{base}")
            except Exception: pass
        else:
            print(f"  ⚠ font '{el.get('font')}' not found (not bundled, not in CapCut) — add it in CapCut once.")
        return base
    _cap = stylepack.element(STYLE_PACK, "caption")
    _bld = stylepack.element(STYLE_PACK, "accent_caption")
    _tko = stylepack.element(STYLE_PACK, "takeover")
    def _px(el): return max(20, round(el["size"] * SIZE_SCALE))
    STYLE = {
        "name": STYLE_PACK,
        "fonts": {"caption": "'PkCap'", "build": "'PkBld'", "takeover": "'PkTko'"},
        "faces": [("PkCap", f"fonts/{_face(_cap)}"), ("PkBld", f"fonts/{_face(_bld)}"), ("PkTko", f"fonts/{_face(_tko)}")],
        # The accent: this reel's own (the plan's accent_by_pack / accent), else her saved default
        # (user-style.json default_accent, set with /studio accent, read by packbuild's one reader), else the
        # pack's own accent. The same order build-reel-type.py uses, so a reel keeps its accent whichever
        # route builds it. Never the creator's personal butter.
        "color": {"base": "#ffffff",
                  "accent": ((_cp.get("accent_by_pack") or {}).get(STYLE_PACK) or _cp.get("accent")
                             or packbuild.saved_accent()
                             or stylepack._data()["packs"].get(STYLE_PACK, {}).get("accent_color") or "#ffffff"),
                  "dim": "rgba(255,255,255,.42)"},
        "size":  {"caption": _px(_cap), "build": _px(_bld), "takeover": _px(_tko), "hero": round(_px(_tko) * 1.32)},
        "track": {"caption": round(_cap["tracking"] * _px(_cap)), "takeover": round(_tko["tracking"] * _px(_tko))},
        "y":     {"caption": _cap["y"], "build": _bld["y"], "takeover": _tko["y"]},   # positions from pack y (LAYOUT-STANDARDS §1)
    }
    CASE = {"caption": _cap["case"], "build": _bld["case"], "takeover": _tko["case"], "hero": _tko["case"]}
    _lh = lambda el, floor=0.82: round(max(floor, 1.0 + el["line_height"]), 3)
    LH  = {"build": _lh(_bld), "take": _lh(_tko), "hero": _lh(_tko)}
    # DROP SHADOW = a LEGIBILITY FLOOR (locked 2026-09-09): rendered captions sit bare over footage, so they
    # ALWAYS carry a soft drop shadow — never removable, on EVERY pack (Butter/Editorial/Playful + future).
    # The VALUE comes from the pack (stylepack.text_shadow: the pack's own welldone.text_shadow, else the
    # HyperFrames default) — a pack TUNES the shadow, it can never turn it off. No on/off toggle.
    _sh = stylepack.text_shadow(STYLE_PACK)
    SHADOW = {"cap": _sh, "build": _sh, "take": _sh}
    print(f"STYLE PACK: {STYLE_PACK}  sizes={STYLE['size']}  case={CASE}  shadow={_sh}")

# ── PER-REEL FONT OVERRIDE ── caption-plan.json "fonts"/"faces" let a single reel pick its animated
# font per role (e.g. Prosecco on the 'not' build + phrase takeover) WITHOUT editing the shipped
# default STYLE or requiring a full style pack. Backward-compatible: no "fonts" key = unchanged.
# fonts: {"build":"Prosecco","takeover":"Prosecco"}  faces: [["Prosecco","fonts/Prosecco.ttf"]]
_fonts_ov = _cp.get("fonts") or {}
for _role, _fam in _fonts_ov.items():
    if _role in STYLE["fonts"]:
        STYLE["fonts"][_role] = f"'{_fam}'"
import shutil as _shutil
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
_FDIR = f"{HF}/fonts"; os.makedirs(_FDIR, exist_ok=True)
for _face in _cp.get("faces", []):
    _fam, _src = tuple(_face)
    # An ABSOLUTE font path silently fails: hyperframes renders by serving the composition dir over a LOCAL
    # HTTP SERVER, so the browser can only load a font referenced RELATIVE to that root (fonts/X.ttf). An
    # absolute src:url(/Users/...) never loads, the browser falls back to a generic serif, and the .mov comes
    # out with the WRONG typeface and NO error anywhere. So copy an absolute path into the composition's
    # fonts/ dir and rewrite it relative — the same thing the STYLE_PACK _face() helper does. (round 6 bug)
    if os.path.isabs(_src):
        if os.path.exists(_src):
            _base = ("".join(c for c in (_fam or "font") if c.isalnum()) or "font") + (os.path.splitext(_src)[1] or ".ttf")
            try:
                _shutil.copy(_src, f"{_FDIR}/{_base}")
                _src = f"fonts/{_base}"
            except Exception as _e:
                print(f"  ⚠ face '{_fam}': could not stage {_src} into fonts/ ({_e}); the render may show the wrong font.")
        else:
            print(f"  ⚠ face '{_fam}': {_src} does not exist — the render will silently fall back to a default font.")
    _pair = (_fam, _src)
    if _pair not in STYLE["faces"]:
        STYLE["faces"].append(_pair)
if _fonts_ov:
    print(f"FONT OVERRIDE (caption-plan): {_fonts_ov}")

# The pack's case, made safe for the reel's language, with her plan's per-reel override (stylepack.case_rule).
_LANG = stylepack.job_language(f"{ROOT}/projects/{JOB}")
CASE = {r: stylepack.case_rule(m, {"build": "caption", "hero": "takeover"}.get(r, r), _cp, _LANG)
        for r, m in CASE.items()}

_BRANDS = stylepack.brand_spellings(f"{ROOT}/projects/{JOB}")   # PeachPod keeps its capitals (a buyer, 2026-10-22)

def apply_case(role, w):
    m = CASE.get(role, "lower")
    if m in stylepack.AS_WRITTEN: return w
    # the shared rule (stylepack.apply_case), with this builder's lowercase that keeps God/Bible/Lord capitalized
    return stylepack.apply_case(w, m, lower=case_fix, brands=_BRANDS)

# keep APOSTROPHES (the creator wants "it's", "that's"); strip only sentence punctuation on single + takeover
_PUNCT = re.compile(r"[.,!?;:\"“”…()\[\]]")
CAP_WORDS = {"god","bible","lord"}   # always capitalized; everything else lowercase (the creator's rule)
def norm(w): return _fold(w).lower().strip(".,!?;:\"'")
def esc(s): return html.escape(s)
def strip_punct(w): return _PUNCT.sub("", w).strip()   # single + takeover: no punctuation (apostrophes kept)
def case_fix(w):   # lowercase EVERYTHING except God/Bible/Lord (which keep a capital, punctuation preserved)
    return w.capitalize() if norm(w) in CAP_WORDS else w.lower()

def sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if w["w"].strip().endswith((".","!","?")): out.append(cur); cur=[]
    if cur: out.append(cur)
    return out

def mode_for(sent):
    txt=_fold(" ".join(w["w"] for w in sent)).lower(); t0=sent[0]["t"]
    if any(k in txt for k in TAKEOVER_KEYS): return "takeover"
    if any(a<=t0<b for a,b in BUILD_RANGES): return "build"
    if BUILD_DEFAULT and len(sent) > SINGLE_MAX_WORDS: return "build"   # karaoke-first: long lines build
    return "single"

def extract_heroes(words):
    """Find the exact word-runs matching a HERO_KEY (e.g. "this is the life") ANYWHERE in the stream — even
    mid-sentence — so only the phrase gets the hero treatment, not the whole run-on sentence it sits in."""
    nwords=[norm(w["w"]) for w in words]
    keys=sorted((k.split() for k in HERO_KEYS), key=len, reverse=True)   # longest first, no overlap
    consumed=set(); groups=[]
    for key in keys:
        L=len(key)
        for i in range(len(words)-L+1):
            if any(j in consumed for j in range(i,i+L)): continue
            if nwords[i:i+L]==key:
                groups.append(words[i:i+L]); consumed.update(range(i,i+L))
    groups.sort(key=lambda g:g[0]["t"])
    return groups, set(id(w) for g in groups for w in g)

def chunk_words(sent, char_limit):
    """Split a sentence's words into chunks that fit <= 2 lines (never more than 2 lines on screen)."""
    chunks, cur, ln = [], [], 0
    for w in sent:
        wl = len(w["w"]) + 1
        if cur and ln + wl > char_limit:
            chunks.append(cur); cur=[]; ln=0
        cur.append(w); ln += wl
    if cur: chunks.append(cur)
    return chunks


# ── FONT FILE GUARD (locked): every @font-face the composition references MUST exist in HF/fonts before
# render. A RELATIVE face (the pack's resolved face entries, or a per-reel "fonts/X.otf") was trusted
# to be there and never copied, so the headless browser silently fell back to a generic face and the .mov
# shipped in the WRONG font with no error (2026-09-09, a real reel). Resolve each missing face the same way
# the style-pack path does (bundled OFL → CapCut's user fonts → ~/Library/Fonts) and copy it in; refuse to
# emit a composition whose fonts can't be found rather than render a fallback.
def _ensure_faces(faces):
    import capcut_userfonts as _cuf
    missing = []
    for _fam, _rel in faces:
        _dst = os.path.join(HF, _rel) if not os.path.isabs(_rel) else _rel
        if os.path.exists(_dst) and os.path.getsize(_dst) > 0:
            continue
        _base = os.path.basename(_rel)
        _src = None
        try: _src = _cuf.resolve_font_file(_fam, _base)
        except Exception: _src = None
        if not _src:
            for _d in (os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts"),
                       os.path.expanduser("~/Library/Fonts"), f"{ROOT}/assets/fonts", f"{ROOT}/product/creative-vault/fonts",
                       # Windows: per-user installed fonts, then the system font folder
                       os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
                       os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")):
                _cand = os.path.join(_d, _base)
                if os.path.exists(_cand): _src = _cand; break
        if _src:
            os.makedirs(os.path.dirname(_dst), exist_ok=True); _shutil.copy(_src, _dst)
            print(f"  font '{_fam}' -> {os.path.relpath(_dst, HF)} (copied from {_src})")
        else:
            missing.append((_fam, _rel))
    if missing:
        raise SystemExit("font file(s) not found for the composition — refusing to render a fallback face: "
                         + ", ".join(f"{f} ({r})" for f, r in missing) + ". Add the font in CapCut once, or drop the file in assets/fonts/.")
_ensure_faces(STYLE["faces"])

# ── SAFE-ZONE TEXT FIT (Bug #5) ── the IG safe zone is x150..930, centered on 540, so any centered line can
# be at most 780px wide before it crops at the frame edge (and reads as "off-center" from the asymmetric
# clip). The three text sizes (caption/build/takeover+hero) were FIXED px with no width check, so a long word
# ("motherhood" at the 206px Editorial hero size) overflowed. This measures each mode's words against the
# REAL font (PIL). A mode's SHARED size never drops below its own floor: the legibility floor for the role
# (safe_zones.MIN_PX) or the pack's designed size, whichever is larger. It used to shrink in 4px steps all
# the way to 40px, so one long word took every caption of the reel below readable. Now a word still too wide
# at that size gets its OWN smaller size (per-word fit, below), down to the legibility floor and no further.
# It only ever shrinks from the floored size — no PIL / no font file -> the size is left as it is.
SAFE_W = 780
def _role_font_file(role):
    """Absolute path to the real font file backing a STYLE role, or None if it's an unbundled system font we
    can't measure (Helvetica etc.) — then the fit is skipped for that role, which is safe (we never upsize)."""
    fam = STYLE["fonts"].get(role, "")
    first = fam.split(",")[0].strip().strip("'\"")     # first concrete family in the CSS stack, unquoted
    for f_fam, f_src in STYLE["faces"]:
        if f_fam != first:
            continue
        for p in ([f_src] if os.path.isabs(f_src) else
                  [f"{HF}/{f_src}", f"{ROOT}/product/templates/hf-reel/{f_src}", f"{ROOT}/{f_src}"]):
            if p and os.path.exists(p):
                return p
    return None

def _fit_text_px(items, font_src, base_px, safe_w=SAFE_W, tracking=0, step=4, floor=40):
    """Shrink base_px in `step`px steps until the WIDEST of `items` fits within safe_w on the real font
    (letter-spacing included). `items` are strings that must each fit ALONE (per-word for the stacked/snap
    layouts).

    FAILS LOUD (§15) when text needs fitting but it cannot be measured — no Pillow, no resolved font file,
    or a measurement error. It must NEVER silently return the unfitted size: that is exactly the defect that
    shipped a 204px takeover off the right edge while printing '204->204' and exiting 0. A buyer gets Pillow
    from set-me-up, so this only fires on a broken environment — where stopping is correct, not shipping
    text off the screen. The pre-render geometry gate is the second net, but the builder must not lie."""
    items = [t for t in items if t and t.strip()]
    if not items:
        return int(base_px)                                  # nothing to fit — legitimately a no-op
    if not _HAVE_PIL:
        raise SystemExit(
            "[build-hf-captions] Pillow (PIL) is required to size on-screen text to the safe zone but is not "
            "installed on this Python. Run 'set me up' (it installs pillow), then rebuild. Refusing to skip "
            "the fit and risk text rendering off the screen.")
    if not font_src:
        raise SystemExit(
            "[build-hf-captions] cannot size text: no font file resolved for this role (is STYLE_PACK set and "
            "the pack font present?). Refusing to skip the safe-zone fit.")
    px = int(base_px)
    try:
        while px > floor:
            font = ImageFont.truetype(font_src, px)
            if max(_text_w(font, t, tracking) for t in items) <= safe_w:
                break
            px -= step
    except Exception as _e:
        raise SystemExit(f"[build-hf-captions] safe-zone fit could not measure text ({_e}); refusing to "
                         f"render at an unverified size.")
    return px

def _text_w(font, t, tracking=0):
    """Rendered width of one string on a loaded PIL font, letter-spacing included (measured the same way
    _fit_text_px measures). Cyrillic the face lacks is measured on the companion that draws it."""
    wpx = script_fonts.pil_width(font, t)
    if wpx is None:
        try: bb = font.getbbox(t); wpx = bb[2] - bb[0]
        except Exception: wpx = font.getlength(t)
    return wpx + tracking * max(0, len(t) - 1)   # CSS letter-spacing sits BETWEEN glyphs

def _fit_word_px(word, font_src, start, floor, tracking=0, step=4, safe_w=SAFE_W):
    """(px, fits): the largest size from `start` down, in `step`px steps and never below `floor`, at which ONE
    word clears the safe width. fits=False means it is still too wide at the floor, and it stays at the floor:
    a word too small to read is not traded for one that fits."""
    px = int(start)
    while True:
        if _text_w(ImageFont.truetype(font_src, px), word, tracking) <= safe_w:
            return px, True
        if px <= floor:
            return px, False
        px = max(int(floor), px - step)

# per-mode display strings, collected during emission, then measured for the shared-size fit above
_fit_pool = {"single": [], "build": [], "takeover": [], "hero": []}
# Every measured word also leaves a marker where its element opens, and every takeover stack one on its word
# block. After the fit, a word too wide for its mode's shared size, or a stack too tall for the safe band, gets
# its own font-size there; every other marker becomes nothing at all.
_fit_marks = {}     # word marker -> (pool, display text, its stack's marker or None)
_stack_marks = {}   # stack marker -> pool
def _fit_mark(pool, disp, stack=None):
    m = f"\x00{len(_fit_marks)}\x00"
    _fit_marks[m] = (pool, disp, stack)
    return m
def _fit_stack(pool):
    m = f"\x00s{len(_stack_marks)}\x00"
    _stack_marks[m] = pool
    return m

words = sorted([w for b in TL["beats"] for w in b["words"]], key=lambda w: w["t"])
hero_groups, hero_ids = extract_heroes(words)   # emitted as takeover-hero AFTER the loop; excluded from normal
records, tl_js, ti = [], [], 0   # records: {mode,start,end,tmpl}  tmpl has a {D} duration placeholder

def emit_takeover(ch, hero):
    """Emit one takeover chunk (vertical word stack, held). hero=True → CAPS + biggest style."""
    global ti
    gid=f"s{ti}"; ti+=1
    c_start=ch[0]["t"]; c_end=ch[-1]["e"] + 1.0
    sp=[]
    hl = KEYWORDS   # accent word(s) = the reel's plan keywords (same rule as single mode); never a reel-specific literal
    _stk = _fit_stack("hero" if hero else "takeover")
    for j,w in enumerate(ch):
        wid=f"{gid}w{j}"
        disp=apply_case("takeover", strip_punct(w["w"])) or w["w"]   # per-pack case (takeover element)
        _fit_pool["hero" if hero else "takeover"].append(disp)       # measured for the safe-zone fit (Bug #5)
        kwy=' class="kwy"' if norm(w["w"]) in hl else ''
        _inner, _js = text_effects.render(wid, disp, TK_FX, w["t"], esc=esc)
        sp.append(f'<span id="{wid}"{kwy}{_fit_mark("hero" if hero else "takeover", disp, _stk)}>{_inner}</span>')
        tl_js.append(_js)
    wrap="take-wrap hero" if hero else "take-wrap"
    records.append({"mode":"takeover","start":c_start,"end":c_end,
        "tmpl":f'<div class="clip {wrap}" data-start="{c_start:.2f}" data-duration="{{D}}" data-track-index="1"><div class="inner"{_stk}>{" ".join(sp)}</div></div>'})

# The moments a full-screen takeover covers her BY DESIGN, for owns-screen.json (written at the end). Taken
# from the plan and the transcript whichever HF_MODE this run emits, so every split overlay of one reel
# carries the same windows: each takeover's designed hold, first word to one second past its last.
_owns = [(g[0]["t"], g[-1]["e"] + 1.0) for g in hero_groups]
for sent in sentences(words):
    sent=[w for w in sent if id(w) not in hero_ids and not _yielded(w["t"])]
    if not sent: continue
    mode=mode_for(sent); s_end=sent[-1]["e"]
    if mode == "takeover":
        _owns.append((sent[0]["t"], sent[-1]["e"] + 1.0))
    if HF_MODE and mode != HF_MODE: continue
    if mode=="single":
        for w in sent:
            disp=apply_case("caption", strip_punct(w["w"]))
            if not disp: continue
            _fit_pool["single"].append(disp)             # measured for the safe-zone fit (Bug #5)
            start=w["t"]
            cls="cap kw" if norm(w["w"]) in KEYWORDS else "cap"
            records.append({"mode":"single","start":start,"end":start+SINGLE_MAX_HOLD,
                "tmpl":f'<div class="clip {cls}"{_fit_mark("single", disp)} data-start="{start:.2f}" data-duration="{{D}}" data-track-index="1">{esc(disp)}</div>'})
    elif mode=="takeover":
        emit_takeover(sent, hero=False)   # non-hero takeover (nothing / worth choosing)
    else:  # build — the pack's accent font sentence build word-by-word, chunked to <=2 lines, karaoke highlight
        chunks = chunk_words(sent, 34)
        for ci, ch in enumerate(chunks):
            gid=f"s{ti}"; ti+=1
            c_start=ch[0]["t"]
            c_end = chunks[ci+1][0]["t"] if ci+1 < len(chunks) else s_end + 0.6
            spans=[]
            for j,w in enumerate(ch):
                wid=f"{gid}w{j}"
                disp = apply_case("build", w["w"])   # per-pack case (accent_caption element)
                _fit_pool["build"].append(disp)      # measured for the safe-zone fit (Bug #5)
                spans.append(f'<span id="{wid}"{_fit_mark("build", disp)}>{esc(disp)}</span>')
                # reveal in place + KARAOKE-highlight the current word butter-yellow, back to white on the next
                nt = ch[j+1]["t"] if j+1 < len(ch) else None
                js = (f'tl.set("#{wid}",{{autoAlpha:0,color:"#ffffff"}},0);'
                      f'tl.to("#{wid}",{{autoAlpha:1,duration:0.1}},{w["t"]:.2f});'
                      f'tl.set("#{wid}",{{color:"{STYLE["color"]["accent"]}"}},{w["t"]:.2f});')   # the PACK's accent, never an imposed yellow
                if nt is not None:
                    js += f'tl.set("#{wid}",{{color:"#ffffff"}},{nt:.2f});'
                tl_js.append(js)
            records.append({"mode":"build","start":c_start,"end":c_end,
                "tmpl":f'<div class="clip build-wrap" data-start="{c_start:.2f}" data-duration="{{D}}" data-track-index="1"><div class="inner">{" ".join(spans)}</div></div>'})

# hero phrases (the single most prominent line) — emitted as the biggest CAPS takeover
if (not HF_MODE) or HF_MODE=="takeover":
    for g in hero_groups:
        emit_takeover(g, hero=True)

# FAIL LOUD on a stale plan (same trap the well-done builder guards): a takeover_key / hero_key that matches no
# transcript text used to vanish silently — the reel rendered with its payoff missing and nothing said so.
if (not HF_MODE) or HF_MODE=="takeover":
    _n_tk = sum(1 for r in records if r["mode"]=="takeover")
    if (TAKEOVER_KEYS or HERO_KEYS) and _n_tk == 0:
        print(f"  ⚠ NO takeover will render: takeover_keys {TAKEOVER_KEYS} / hero_keys {HERO_KEYS} matched nothing in "
              f"the transcript. caption-plan.json is stale vs the current cut — fix the text or the takeover is gone.")
    else:
        for k in HERO_KEYS:   # mirrors extract_heroes' exact match
            if not any([norm(w["w"]) for w in g] == k.split() for g in hero_groups):
                print(f"  ⚠ hero_key {k!r} matched nothing in the transcript (no hero takeover for it).")
# Same trap for the hand-authored TIME ranges: a build_range that no line starts inside is stale vs the current
# cut (a re-cut shifted the words) and would silently change nothing — say so.
for _rng in BUILD_RANGES:
    try:
        _a, _b = float(_rng[0]), float(_rng[1])
    except Exception:
        print(f"  ⚠ build_ranges entry {_rng!r} is not [start, end] seconds — ignored."); continue
    if not any(_a <= s[0]["t"] < _b for s in sentences(words)):
        print(f"  ⚠ build_ranges [{_a:g}, {_b:g}) contains no line start in the current cut — stale vs the transcript; "
              f"no line will BUILD there (re-time it, or use a phrase key instead).")

# NO-OVERLAP pass (GLOBAL): captions are strictly one-at-a-time, so clamp EVERY clip against the next clip's
# start across ALL modes (not just its own layer) — a karaoke sentence's hold never lingers into the next
# line, and a build->single (or single->build) handoff never shows two caption elements at once.
clips_html=[]
intervals=[]   # (start,end) of every visible clip -> merged into active spans for dead-space trimming
allr=sorted(records, key=lambda r: (r["start"], r["end"]))
for i, r in enumerate(allr):
    nxt = allr[i+1]["start"] if i+1 < len(allr) else None
    end = r["end"]
    if nxt is not None: end = min(end, nxt)       # never overlap the next clip in ANY layer
    end = _clamp_yield(r["start"], end)           # and never linger into an overlay (takeover) window
    # round BOTH ends before taking the duration so adjacent clips abut exactly: rounding start and duration
    # separately left a 0.01s hole that caught a frame about a third of the time (a blink between words)
    dur = round(end, 2) - round(r["start"], 2)
    if dur <= 0: dur = 0.04                        # degenerate timestamps: tiny flash, still no real overlap
    clips_html.append(r["tmpl"].replace("{D}", f"{dur:.2f}"))
    intervals.append((r["start"], r["start"]+dur))

# ACTIVE SPANS: merge visible intervals, splitting only where text is absent > DEAD_GAP seconds. The injector
# lays one overlay segment per span so long empty stretches leave the track clear (the creator can grab layers below).
intervals.sort()
spans=[]
for s,e in intervals:
    if spans and s - spans[-1][1] <= DEAD_GAP:
        spans[-1][1]=max(spans[-1][1], e)
    else:
        spans.append([s,e])
spans=[[max(0.0, round(a-0.10,2)), min(DUR, round(b+0.20,2))] for a,b in spans]   # small edge pad
spans_name = (HF_MODE or "all")+"-spans.json"
json.dump(spans, open(f"{HF}/{spans_name}","w", encoding="utf-8"))

F=STYLE["fonts"]; SZ=dict(STYLE["size"]); C=STYLE["color"]; TR=STYLE["track"]
SY=STYLE.get("y",{"caption":-0.40,"build":-0.24,"takeover":0.0}); _ypx=lambda v: round(960 - v*960)   # LAYOUT-STANDARDS §1
# SAFE-ZONE FIT (Bug #5): each mode's SHARED size, then any word still too wide sized on its own.
# hero + takeover share the takeover font; build + caption each measure their own. A shared size starts from
# what was asked for (the plan's caption_size for captions, else the pack's own size) lifted to its floor, and
# only shrinks while its widest word does not fit, never below that floor. The floor is the legibility floor
# for the role or the pack's designed size, whichever is larger: a plan's caption_size can make captions
# bigger than the pack, never smaller than the pack or unreadable.
_hero_font=_role_font_file("takeover"); _cap_font=_role_font_file("caption"); _bld_font=_role_font_file("build")
_FIT = {   # pool -> (font file, letter-spacing px, legibility floor, the pack's designed size)
    "single":   (_cap_font,  TR.get("caption", 0),  safe_zones.MIN_PX["caption"],  STYLE["size"]["caption"]),
    "build":    (_bld_font,  0,                     safe_zones.MIN_PX["karaoke"],  STYLE["size"]["build"]),
    "takeover": (_hero_font, TR.get("takeover", 0), safe_zones.MIN_PX["takeover"], STYLE["size"]["takeover"]),
    "hero":     (_hero_font, TR.get("takeover", 0), safe_zones.MIN_PX["takeover"], STYLE["size"]["hero"]),
}
def _shared_px(pool, want):
    font, trk, legible, designed = _FIT[pool]
    floor = max(legible, designed)
    return max(floor, _fit_text_px(_fit_pool[pool], font, max(int(want), floor), SAFE_W, trk, floor=floor))
SZ["hero"]     = _shared_px("hero", STYLE["size"]["hero"])
SZ["takeover"] = _shared_px("takeover", SZ["takeover"])
SZ["build"]    = _shared_px("build", SZ["build"])
_cap_fit       = _shared_px("single", CAP_SIZE or SZ["caption"])
if any(_fit_pool.values()):
    print(f"safe-zone fit: caption {CAP_SIZE or STYLE['size']['caption']}->{_cap_fit}  build {STYLE['size']['build']}->{SZ['build']}"
          f"  takeover {STYLE['size']['takeover']}->{SZ['takeover']}  hero {STYLE['size']['hero']}->{SZ['hero']}")
# PER-WORD FIT: only the words that do not clear the safe width at their mode's shared size get a size of
# their own, the largest that fits, never below the legibility floor. Everything else keeps the shared size.
_SHARED = {"single": _cap_fit, "build": SZ["build"], "takeover": SZ["takeover"], "hero": SZ["hero"]}
_own_px, _too_wide = {}, []    # (pool, word) -> px · words still too wide at the floor
for _pool in _SHARED:
    _words = sorted({d for p, d, _st in _fit_marks.values() if p == _pool and d and d.strip()})
    if not _words:
        continue
    _font, _trk, _legible, _designed = _FIT[_pool]
    try:
        _at = ImageFont.truetype(_font, int(_SHARED[_pool]))
        for _wd in _words:
            if _text_w(_at, _wd, _trk) <= SAFE_W:
                continue
            _px, _fits = _fit_word_px(_wd, _font, _SHARED[_pool], _legible, _trk)
            _own_px[(_pool, _wd)] = _px
            if not _fits:
                _too_wide.append((_wd, _px))
    except Exception as _e:
        raise SystemExit(f"[build-hf-captions] per-word fit could not measure text ({_e}); refusing to "
                         f"render at an unverified size.")
# A takeover stacks one word per line, so a stack also has to fit the safe band's HEIGHT. The shared size no
# longer shrinks for a long word (only that word does), so a long stack is sized as a whole here: the largest
# size, never below the legibility floor, at which its lines fit between the platform bands.
_TK_CY = _ypx(SY['takeover'])
_STACK_H = 2 * min(_TK_CY - safe_zones.TOP, safe_zones.BOTTOM - _TK_CY)
_px_of = {}     # marker -> px, for a word or stack whose size differs from what it would inherit
for _m, (_pool, _wd, _st) in _fit_marks.items():
    if _st is None and (_pool, _wd) in _own_px:
        _px_of[_m] = _own_px[(_pool, _wd)]
_stack_fits = []
for _sm, _pool in _stack_marks.items():
    _members = [(_m, _wd) for _m, (_p, _wd, _st) in _fit_marks.items() if _st == _sm]
    _shared, _legible = _SHARED[_pool], _FIT[_pool][2]
    _lh = LH["hero" if _pool == "hero" else "take"]
    _fitw = [_own_px.get((_pool, _wd), _shared) for _m, _wd in _members]
    _s = _shared
    while _s > _legible and _lh * sum(min(_s, _f) for _f in _fitw) > _STACK_H:
        _s = max(_legible, _s - 4)
    if _s < _shared:
        _px_of[_sm] = _s
        _stack_fits.append((" ".join(_wd for _m, _wd in _members[:4]), _shared, _s, len(_members),
                            _lh * sum(min(_s, _f) for _f in _fitw) <= _STACK_H))
    for (_m, _wd), _f in zip(_members, _fitw):
        if _f < _s:
            _px_of[_m] = _f
# Say what was sized on its own, at the size it actually renders (a stack that came down for height can take
# a long word's own size with it), and say loudly when a word is too long to fit at a readable size.
_own_final = sorted({(_fit_marks[_m][0], _fit_marks[_m][1], _px) for _m, _px in _px_of.items() if _m in _fit_marks})
if _own_final:
    print("per-word fit: " + "  ".join(f"{w!r} {_SHARED[p]}->{px}" for p, w, px in _own_final))
for _txt, _a, _b, _n, _fits in _stack_fits:
    _tag = f"{_txt!r}{'…' if _n > 4 else ''}"
    if _fits:
        print(f"stack fit: {_tag} {_a}->{_b} so the stack stays inside the safe band")
    else:
        print(f"  ⚠ the takeover {_tag} is {_n} lines, too many to fit between the platform bands even at the "
              f"{_b}px legibility floor, so its top and bottom lines sit in them. A shorter takeover phrase fixes it.")
for _wd, _px in _too_wide:
    print(f"  ⚠ {_wd!r} is wider than the safe width even at the {_px}px legibility floor, so it may run past "
          f"the safe zone. Shorten or correct that word in edit-timeline.json if it should not be this long.")
_MARK = re.compile("\x00s?\\d+\x00")
clips_html = [_MARK.sub(lambda m: (f' style="font-size:{_px_of[m.group(0)]}px"' if m.group(0) in _px_of else ""), c)
              for c in clips_html]
FACES="\n".join(f"@font-face{{font-family:'{fam}';src:url('{src}');}}" for fam,src in STYLE["faces"])
HTML = f'''<!doctype html>
<html lang="{_LANG or 'en'}"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
{FACES}
{text_effects.CSS}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:transparent;}}
#root{{position:absolute;inset:0;}}
/* Layouts are FIXED; fonts/colors/sizes come from the STYLE PACK tokens above (swappable per pack).
   IG REELS SAFE ZONE: all text inside x 150..930 (clear of the right rail ~960+) and y 270..1620. */
.cap{{position:absolute;left:110px;right:110px;top:{_ypx(SY['caption'])}px;transform:translateY(-50%);text-align:center;font-family:{F['caption']};
  font-weight:{CAP_WEIGHT};font-size:{_cap_fit}px;color:{C['base']};text-shadow:{SHADOW['cap']};letter-spacing:{TR['caption']}px;}}
.cap.kw{{color:{C['accent']};}}
.build-wrap{{position:absolute;left:160px;right:160px;top:{_ypx(SY['build'])}px;transform:translateY(-50%);text-align:center;}}
.build-wrap .inner{{font-family:{F['build']};font-size:{SZ['build']}px;color:{C['base']};line-height:{LH['build']};text-shadow:{SHADOW['build']};}}
.build-wrap .inner span{{display:inline;}}
/* takeover: every word on its OWN line, whole phrase stacked + held, vertically centered */
.take-wrap{{position:absolute;left:130px;right:130px;top:{_ypx(SY['takeover'])}px;transform:translateY(-50%);text-align:center;}}
.take-wrap .inner{{font-family:{F['takeover']};font-size:{SZ['takeover']}px;color:{C['base']};line-height:{LH['take']};text-shadow:{SHADOW['take']};letter-spacing:{TR['takeover']}px;}}
.take-wrap .inner span{{display:block;}}
.take-wrap .inner .kwy{{color:{C['accent']};}}
/* hero = the single most prominent line ("this is the life. this is it."): biggest (lowercase), "life" butter */
.take-wrap.hero .inner{{font-size:{SZ['hero']}px;line-height:{LH['hero']};}}
</style></head>
<body>
<div id="root" data-composition-id="{COMP}" data-start="0" data-duration="{DUR}" data-width="1080" data-height="1920">
{os.linesep.join(clips_html)}
</div>
<script>
/* Captions are timed NATIVELY: every word is a `.clip` with data-start/data-duration and the
   renderer shows it for its own window. GSAP carries only the karaoke reveals and the takeover
   intros, so on an all-snap reel the timeline is empty. The registry is still required by the
   composition contract, so it is declared even when empty.

   Render it like every other composition, through the gate, never around it:
     python3 product/reel_render.py render projects/<job>/hf-captions -o projects/<job>/hf-captions/renders/<layer>.mov
   `hyperframes check` sees native clip timing (its seek shows each clip in its own window), so
   no extra flag is needed. The full-screen takeovers cover her on purpose; their windows are in
   owns-screen.json beside this file and in the job folder, where the subject check reads them. */
window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});
{os.linesep.join(tl_js)}
window.__timelines["{COMP}"]=tl;
</script>
</body></html>'''

HTML, _script_notes = script_fonts.add_companions(HTML, HF)
for _n in _script_notes:
    print(f"  {_n}")
open(f"{HF}/index.html","w", encoding="utf-8").write(HTML)
# The same dead-space rule at RENDER time (product/render_spans.py): reel_render.py captures only the stretches
# this layer is on screen and stitches them back into one full-length .mov, so the ACTIVE SPANS above and the
# render agree. A layer on screen from first word to last gets no plan and renders exactly as before.
import render_spans
_sp = render_spans.write_plan(HF, HTML)
if _sp:
    print(f"captions {render_spans.describe(_sp)}")
# The takeovers cover her BY DESIGN, and subject_guard.py (run by reel_render.py) waives exactly the windows
# listed here and nothing else. Without this file every full-screen takeover read as a graphic on her face and
# the render was refused. Written the way build-reel-type.py writes it: beside the composition, and in the job
# folder, which is where the guard walks up to from a render placed anywhere in the job.
_owns_doc = {"_doc": "moments that cover the subject BY DESIGN (full-screen takeovers), written by "
                     "build-hf-captions.py for subject_guard.py. Seconds, [start, end].",
             "windows": [[round(float(a), 3), round(float(b), 3)] for (a, b) in sorted(_owns)]}
for _p in (f"{HF}/owns-screen.json", f"{ROOT}/projects/{JOB}/owns-screen.json"):
    json.dump(_owns_doc, open(_p, "w", encoding="utf-8"), indent=1)
try:
    mj=json.load(open(f"{HF}/meta.json", encoding="utf-8")); mj["id"]=COMP; json.dump(mj,open(f"{HF}/meta.json","w", encoding="utf-8"))
except Exception: pass
print(f"wrote {HF}/index.html  (mode={HF_MODE or 'ALL'}, {len(clips_html)} clips, {ti} build/takeover chunks)")
