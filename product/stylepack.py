#!/usr/bin/env python3
"""stylepack.py — load a swappable font STYLE PACK for either build (kinetic or CapCut).

A pack = 3 fonts by role (main/accent/caption) at LOCKED per-element formats, cloned from the creator's CapCut
mockup → product/creative-vault/style-packs.json. Both engines call this so a reel builds identically in
any pack. Users can also build their OWN pack (pick 3 fonts) — see font-picking-guardrails.md.

    from stylepack import load, element
    p = load("Editorial")                 # -> pack dict
    e = element("Editorial", "headline")  # -> {font,file(abs),size,tracking,line_height,y}

Element types: headline · takeover · caption · thought_bubble · accent_caption.
"""
import json, os, unicodedata
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "product", "creative-vault", "style-packs.json")

LOCAL_SPEC = os.path.join(ROOT, "_local", "style-packs.json")

def _data():
    """The shipped packs, with any LOCAL packs merged over the top.

    A creator's own pack is personal: her licensed faces and her palette. It must never land in a
    buyer's bundle, so it lives in `_local/style-packs.json` (git-ignored, never staged by
    make-ship) and is merged here. This is also the supported route for a buyer who builds their
    own pack rather than picking one of the shipped three - same file, same shape.
    """
    data = json.load(open(SPEC, encoding="utf-8"))
    if os.path.exists(LOCAL_SPEC):
        local = json.load(open(LOCAL_SPEC, encoding="utf-8"))
        data.setdefault("packs", {}).update(local.get("packs", {}))
        for key, path in (local.get("system_fonts") or {}).items():   # a local pack's "SYSTEM:<key>" fonts
            data.setdefault("system_fonts", {}).setdefault(key, path)
    prev = os.environ.get("REEL_PREVIEW_PACKS")   # a look not saved yet (the Brand Kit's directions): only
    if prev and os.path.isfile(prev):             # a process started with this sees it; nothing is written
        extra = json.load(open(prev, encoding="utf-8"))
        data.setdefault("packs", {}).update(extra.get("packs", {}))
        data.setdefault("system_fonts", {}).update(extra.get("system_fonts", {}))
    return data

def names():
    """List available pack names (all in the launch kit)."""
    return list(_data()["packs"].keys())

def load(pack):
    d = _data()
    if pack not in d["packs"]:
        raise KeyError(f"unknown style pack {pack!r}; have {list(d['packs'])}. If it is a pack you built, an "
                       f"engine update may have removed it; bring it back with: python3 product/pack_persist.py recover")
    return d["packs"][pack]

def signature(pack):
    """A short fingerprint of everything a pack hands a drawing: its entry (shipped or hers in _local/) and its
    palette. A look drawn under another fingerprint was drawn before the pack changed, so it is drawn again (a buyer,
    2026-10-22: after she changed her pack's karaoke font, a Swap brought back the old one). None for an unknown pack."""
    import hashlib
    try:
        spec = load(pack)
    except KeyError:
        return None
    try:
        import pack_palettes
        pal = pack_palettes.PALETTE.get(pack)
    except Exception:
        pal = None
    return hashlib.sha256(json.dumps([spec, pal], sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

def _abs(fileref):
    """Resolve a font file reference to an absolute path (handles SYSTEM: + assets/fonts).

    A blank reference is not a file, and resolves to "" (a path that never exists). Packs built by
    /studio recipe leave `file` blank on purpose, and frame_to_pack does for a font not added yet, so the
    font resolves BY NAME at build time. Joined onto assets/fonts, a blank used to come back as the fonts
    FOLDER, which exists: the name lookup and the fallback in element() never ran, and the text rendered in
    the browser's default typeface with nothing said."""
    if not fileref:
        return ""
    if fileref.startswith("SYSTEM:"):
        return _data()["system_fonts"][fileref[len("SYSTEM:"):]]
    return os.path.join(ROOT, "assets", "fonts", fileref)

# A pack may name a font that is NOT on this machine. The paid faces (script/display/handwritten) do not
# ship as files: they live in CapCut, added once from its font panel, and resolve from there by name.
# The BAKED lane renders in a headless browser, which cannot see CapCut's fonts and needs a real file. With
# no file the @font-face silently resolves to a browser default, so the reel renders in the WRONG typeface
# and nothing errors. A wrong-looking reel that shipped is worse than a loud failure.
# So: fall back to a BUNDLED face chosen to suit the role, and always render something intentional. A pack
# can name its own substitute per element via "fallback_file". The fallback stays (failing instead would stop
# every Editorial, Butter and Playful build on a buyer machine that has not added those faces in CapCut
# yet), but it is never quiet and never "fine": the stand-in is not part of the pack, so the message names
# the pack font that is missing, says the text will not have the pack's look, and says how to add it.
_ROLE_FALLBACK = {
    "headline":       "PlayfairDisplay-VF.ttf",
    "takeover":       "PlayfairDisplay-VF.ttf",
    "caption":        "Poppins-SemiBold.ttf",
    "thought_bubble": "PinyonScript-Regular.ttf",
    "accent_caption": "PinyonScript-Regular.ttf",
}
_warned = set()
_told_how = set()


def _how_to_add(pack, font):
    """The one plain line on how to get a missing pack font, said once per pack + font."""
    key = (pack, font)
    if key in _told_how:
        return ""
    _told_how.add(key)
    try:
        import capcut_font_doctor   # CapCut lists a few fonts under another name (Soup Du Jour -> "Solid")
        search = capcut_font_doctor._CAPCUT_SEARCH_NAME.get((font or "").strip().lower()) or font
    except Exception:
        search = font
    lic = {"pro": "; it comes with CapCut Pro", "free": "; it is free in CapCut"}.get(
        _FONT_LICENSE.get((font or "").strip().lower()), "")
    return (f"\n    To get it: add '{font}' in CapCut once (search '{search}' in the text panel{lic}), or point "
            f"the engine at a font file you have: python3 product/capcut_font_doctor.py --map "
            f"\"{font}=/path/to/the/font\"")


def element(pack, kind):
    """Full spec for one element in a pack: font, abs file path, size, tracking, line_height, y.

    A missing face falls back to a bundled stand-in (see above) and says so. The only path returned that
    does not exist is when that bundled stand-in is missing too, and that is said loudly as well."""
    raw = dict(load(pack)["elements"][kind])
    e = dict(raw)
    e["file"] = _abs(e["file"])
    if not os.path.exists(e["file"]):
        # Before falling back, try the SAME resolver the CapCut lanes use — it finds a font the buyer added
        # in CapCut's own catalog (cached under an opaque id as font.ttf) by its real family name. This is
        # what closes the RAW-vs-BAKED gap: CapCut draws Bloop from the buyer's library in the editable lane,
        # so the baked lane must be able to find that SAME cached file instead of dropping to the stand-in.
        # capcut catalog font scan — the font-cache scan lives in capcut_userfonts.resolve_font_file.
        # The missing file's path goes along: its name says which cut the role wants (the hollow takeover).
        try:
            import capcut_userfonts
            real = capcut_userfonts.resolve_font_file(raw.get("font"), e["file"])
        except Exception:
            real = None
        if real and os.path.exists(real):
            e["file"] = real
            return e
        sub = raw.get("fallback_file") or _ROLE_FALLBACK.get(kind, "Poppins-SemiBold.ttf")
        sub_path = _abs(sub)
        e["requested_font"] = raw.get("font")
        e["fallback"] = True
        key = (pack, kind, raw.get("font"))
        if os.path.exists(sub_path):
            e["file"] = sub_path
            e["font"] = os.path.splitext(os.path.basename(sub))[0]
            if key not in _warned:
                _warned.add(key)
                print(f"  ⚠ {pack}/{kind}: the {pack} pack's font '{raw.get('font')}' was not found on this computer, so "
                      f"the stand-in '{e['font']}' is used in its place. The stand-in is not part of the pack, so "
                      f"this text will not have the {pack} look.{_how_to_add(pack, raw.get('font'))}")
        else:
            e["fallback_missing"] = True
            if key not in _warned:
                _warned.add(key)
                print(f"  ⚠ {pack}/{kind}: the {pack} pack's font '{raw.get('font')}' was not found on this computer, and "
                      f"its bundled stand-in '{sub}' is missing from assets/fonts too, so this text has no font "
                      f"file and will show in a default typeface.{_how_to_add(pack, raw.get('font'))}")
    return e

def audit(pack=None):
    """Which elements would fall back on THIS machine. Returns [(pack, kind, requested, using)]."""
    out = []
    for pk in ([pack] if pack else names()):
        for kind in load(pk)["elements"]:
            e = element(pk, kind)
            if e.get("fallback"):
                out.append((pk, kind, e.get("requested_font"), e.get("font")))
    return out

# How each non-bundled pack font is added, for the honest delivery note (source of truth = the `licensing`
# note in style-packs.json). "pro" = a paid face that comes with CapCut Pro; "free" = a no-cost face the
# buyer adds from CapCut's font panel (never call these "Pro" — Bloop/Ugly Dave are free; bloop is free).
_FONT_LICENSE = {
    "prosecco and baguette": "pro", "prosecco": "pro", "soup du jour": "pro",
    "bloop": "free", "ugly dave": "free",
}

def delivery_font_note(pack):
    """Warm, buyer-facing HANDOFF note for when a pack's premium font will NOT render on this buyer's
    machine and a replacement is used instead. Returns the message string, or None when every pack font
    resolves (a CapCut Pro buyer, or one who already added the free face) so nothing needs saying.

    Honest by design: it only fires for fonts that genuinely do not resolve for THIS buyer (checked through
    the same resolver every build uses, so a Pro user who has the font is never nagged), and it says the
    RIGHT fix per font — "comes with CapCut Pro" for a paid face, "free to add in CapCut" for a free one,
    and no claim either way for a font of a pack she built (the engine cannot know its plan).
    No em dashes (buyer-facing). Surfaced at delivery by the CapCut-export handoff. See QA-log item #14."""
    try:
        import capcut_userfonts as cu
    except Exception:
        cu = None
    data = load(pack)
    subs, seen = [], set()                       # (requested, substitute, license) per distinct requested font
    for kind, raw in data["elements"].items():
        requested = raw.get("font")
        if not requested or requested in seen:
            continue
        bundled = _abs(raw.get("file"))
        resolved = (cu.resolve_font_file(requested, bundled if os.path.exists(bundled) else None)
                    if cu else (bundled if os.path.exists(bundled) else None))
        if resolved:                             # ships bundled, or the buyer has it in CapCut — nothing to say
            continue
        seen.add(requested)
        e = element(pack, kind)                  # what substitute actually renders
        subs.append((requested, e.get("font"), _FONT_LICENSE.get(requested.strip().lower())))
    if not subs:
        return None
    lines = [f"A quick heads up on fonts for your **{pack}** pack:"]
    for requested, sub, lic in subs:
        if lic == "pro":
            lines.append(f"- **{requested}** comes with CapCut Pro, and it looks like it is not on your "
                         f"setup yet, so I used **{sub}** in its place. It still looks clean. If you would "
                         f"rather have the exact pack look, add {requested} in CapCut with Pro, or just tell "
                         f"me another font you would like and I will swap it.")
        elif lic == "free":
            lines.append(f"- **{requested}** is free in CapCut but is not added on your machine yet, so I "
                         f"used **{sub}** for now. To get the real look, add {requested} in CapCut (it is "
                         f"free, no Pro needed), or tell me another font you would prefer and I will use it.")
        else:   # a font of her own pack's choosing: whether CapCut carries it, and on which plan, is unknown
            lines.append(f"- **{requested}** is not added in CapCut on your machine yet, so I used **{sub}** "
                         f"for now. To get the real look, add {requested} in CapCut, or tell me another font "
                         f"you would prefer and I will use it.")
    return "\n".join(lines)

def roles(pack):
    """{main, accent, caption} font names for the pack."""
    return load(pack)["fonts"]

# LEGIBILITY FLOOR (Layer 1, locked 2026-09-09): rendered text over footage ALWAYS carries a soft drop
# shadow so it stays readable on any footage. It is a RULE, not a style choice — a pack may TUNE the shadow
# value (its `welldone.text_shadow`) but can never remove it. A pack that declares none gets the HyperFrames
# white-on-video default. There is deliberately NO on/off toggle: legibility is not optional (the creator:
# "regardless of style pack, there should be a soft drop shadow behind all text you render").
HF_TEXT_SHADOW = "0 6px 32px rgba(0,0,0,.55)"   # HyperFrames default (composition-patterns.md) — soft + wide

def text_shadow(pack):
    """The drop-shadow VALUE for a pack's rendered text over footage — always a REAL shadow, never 'none'.
    The pack's own `welldone.text_shadow` when declared (a pack TUNES the floor), else the HyperFrames floor."""
    p = _data().get("packs", {}).get(pack, {})
    return p.get("text_shadow") or (p.get("welldone") or {}).get("text_shadow") or HF_TEXT_SHADOW

if __name__ == "__main__":
    for p in names():
        r = roles(p)
        print(f"{p:10s} main={r['main']:20s} accent={r['accent']:20s} caption={r['caption']}")
        for k in ("headline", "takeover", "caption", "thought_bubble", "accent_caption"):
            e = element(p, k)
            ok = "✓" if os.path.exists(e["file"]) else "✗MISSING"
            print(f"   {k:15s} {e['font']:22s} sz={e['size']:<3} trk={e['tracking']:<5} lnH={e['line_height']:<6} y={e['y']:<5} {ok}")


def font_box_ratio(font_file, default=1.0):
    """(ascent + descent) / font-size for a face — the height of the box a browser gives ONE line.

    Stacked display type (the takeover word-stack) needs a line-height at least this tall or adjacent
    word boxes overlap and `hyperframes check` fails with content_overlap. The value is a property of
    the FONT, not a taste call: Soup Du Jour is 1.00, Inter 1.22, Playfair 1.34, Anton 1.51. A constant
    floor tuned against one face silently collides under a taller one.

    Falls back to `default` when PIL is unavailable or the file will not open, so a build never dies
    over a metric it can do without.
    """
    try:
        from PIL import ImageFont
        a, d = ImageFont.truetype(font_file, 200).getmetrics()
        return (a + d) / 200.0
    except Exception:
        return default


def font_ink_ratio(font_file, sample="hgxy Hd", default=0.72):
    """Height of the actual INK for `sample`, as a fraction of font-size.

    The floor for a deliberately tight line-height: type may be set tighter than its box (that is how
    stacked display type reads as one unit) but never tighter than its own ink, or ascenders and
    descenders of neighbouring lines physically cross. Soup Du Jour is 0.68, Anton 0.98 — a constant
    tuned on the first collides under the second.
    """
    try:
        from PIL import ImageFont
        bb = ImageFont.truetype(font_file, 200).getbbox(sample)
        return (bb[3] - bb[1]) / 200.0
    except Exception:
        return default


# ── Letter case ─────────────────────────────────────────────────────────────────────────────────────────────
# A pack's "case" (lower / upper / title) is a design rule written for English. Lowercase in German turns every
# noun into a misspelling ("Gott" -> "gott", "Entscheidung" -> "entscheidung"); a buyer caught it on her own
# reel. Title case does the same in reverse. So on a reel that is not in English those two become "as-written",
# her words exactly as said; upper is a real style in any cased alphabet and stays. Her plan can always set the
# case per reel ("caption_case" / "takeover_case" / "headline_case" in caption-plan.json), in any language.
AS_WRITTEN = ("none", "as-written", "as-said")
ENGLISH_ONLY_CASES = ("lower", "title")
# How a pack or plan spells a case varies ("as_is", "asis", "As Written", "UPPERCASE"), and anything unrecognized used
# to fall through to lowercase, rewriting her words (three buyers' Claudes patched this by hand, 2026-10). Spellings
# are read by their letters alone; one that names no case keeps her words exactly as said.
_CASE_SPELLINGS = {
    "lower": "lower", "lowercase": "lower", "lowercased": "lower",
    "upper": "upper", "uppercase": "upper", "caps": "upper", "allcaps": "upper",
    "title": "title", "titlecase": "title",
    "none": "as-written", "aswritten": "as-written", "assaid": "as-written", "asis": "as-written",
    "original": "as-written", "keep": "as-written", "natural": "as-written", "normal": "as-written",
    "sentence": "sentence", "sentencecase": "sentence",
}
# Sentence case: a capital on the first word of the text, every other letter exactly as she wrote or said it. It
# belongs to text read as a block (a hook, a card, a label). Captions and takeover words arrive one word at a time,
# and her transcript already starts each sentence with a capital, so on those roles it keeps her words as said.
WORD_ROLES = ("caption", "takeover")


def normalize_case(rule, default="lower"):
    """'lower' | 'upper' | 'title' | 'sentence' | 'as-written' for any spelling of a case rule; `default` when none
    is set."""
    if rule is None or not str(rule).strip():
        return default
    return _CASE_SPELLINGS.get("".join(ch for ch in str(rule).lower() if ch.isalpha()), "as-written")


def job_language(job_dir):
    """The reel's language code, or None when it is English or unknown. Read from the job's transcript, which
    records the language the listener heard (rough-cut kept-words.py), and, for a transcript written before it
    did, from the listener's own diagnostics when every clip was heard in one language."""
    def _read(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    job = os.path.basename(os.path.normpath(job_dir))
    tr = _read(os.path.join(job_dir, "outputs", f"{job}.transcript.json"))
    code = (tr.get("language_code") or "").lower()
    if not code and tr.get("language_verdict") in ("non_english", "mixed"):
        diag = _read(os.path.join(job_dir, "transcript", ".transcribe-diagnostics.json"))
        heard = [diag["language_forced"]] if diag.get("language_forced") else list(diag.get("detected_languages") or {})
        code = heard[0].lower() if len(heard) == 1 else ""
    return code if code and code != "en" else None


def case_rule(pack_case, role=None, plan=None, lang=None):
    """The case one piece of on-screen text gets. `role` is "caption" | "takeover" | "headline"; `plan` is the
    reel's caption-plan dict; `lang` is job_language(). Her plan wins, then the pack, made safe for the language."""
    chosen = (plan or {}).get(f"{role}_case") if role else None
    rule = normalize_case(chosen) if chosen else normalize_case(pack_case)
    if not chosen and lang and rule in ENGLISH_ONLY_CASES:
        return "as-written"
    if rule == "sentence" and role in WORD_ROLES:
        return "as-written"
    return rule


_GRK_ACCENTS = {"̀", "́", "͂", "̓", "̔", "ͅ"}   # tonos/oxia, varia, perispomeni, breathings, iota subscript


def upper(text):
    """`text` in capitals. Greek in capitals drops its accents (ΔΈΚΑ is wrong, ΔΕΚΑ is right) and keeps its
    dialytika; a vowel that loses its accent before ι or υ hands that ι/υ a dialytika, so άι reads ΑΪ, not the
    diphthong ΑΙ. Every other language is plain str.upper()."""
    up = text.upper()
    if not any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in up):
        return up
    out, bare = [], False          # bare: the vowel just written lost its accent
    for c in unicodedata.normalize("NFD", up):
        if c in _GRK_ACCENTS and out and ("Ͱ" <= out[-1] <= "Ͽ"):
            bare = out[-1] in "ΑΕΗΟΩ"
            continue
        out.append(c)
        if bare and c in "ΙΥ":
            out.append("̈")
        if not unicodedata.combining(c):
            bare = False
    return unicodedata.normalize("NFC", "".join(out).replace("̈̈", "̈"))


import re as _re
_WORD = _re.compile(r"[^\W_]+")
_BRANDS_CACHE = {}


def _camel(w):
    """A word spelled with a capital inside it AND lowercase letters (TikTok, iPhone, ChatGPT), not an acronym (AI, DMs)."""
    if not any(c.isupper() for c in w[1:]) or not any(c.islower() for c in w):
        return False
    return not (w.endswith("s") and w[:-1].isupper())


def brand_spellings(job_dir=None):
    """{casefolded word: her spelling} for every word in her word-fix tables spelled with a capital inside it
    (PeachPod, TikTok, LaLa LoLo): the shared presets/caption-corrections.json, hers in _local/, and the reel's own
    word-fixes.json (corrections.local.json in an older job), each laid over the one before, as the rough cut lays
    them. A lowercase pack is a style; a brand's spelling isn't, so apply_case keeps these as written (a buyer,
    2026-10-22: "PeachPod" came out "peachpod" in her captions). A capital only at the start (Instagram) is an
    ordinary word, and an all-capitals one (AI, DM, DMs) reads fine lowercased, so both still follow the pack."""
    files = [os.path.join(ROOT, "presets", "caption-corrections.json"), os.path.join(ROOT, "_local", "caption-corrections.json")]
    if job_dir:
        files += [os.path.join(job_dir, n) for n in ("corrections.local.json", "word-fixes.json")]
    key = tuple((f, os.path.getmtime(f)) for f in files if os.path.isfile(f))
    if key in _BRANDS_CACHE:
        return _BRANDS_CACHE[key]
    keep = {}
    for f, _ in key:
        try:
            t = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue                                             # an unreadable table is passed over, as the rough cut does
        vals = []
        for part in ("words", "auto", "phrases"):
            p = t.get(part) or {}
            vals += list(p.values()) if isinstance(p, dict) else [x[1] for x in p if isinstance(x, (list, tuple)) and len(x) > 1]
        for v in vals:
            for w in _WORD.findall(str(v)):
                if _camel(w):
                    keep[w.casefold()] = w
    _BRANDS_CACHE.clear(); _BRANDS_CACHE[key] = keep
    return keep


def keep_brands(text, brands):
    """`text` with every word in `brands` (brand_spellings) put back in its own spelling."""
    if not brands:
        return text
    return _WORD.sub(lambda m: brands.get(m.group(0).casefold(), m.group(0)), text)


def apply_case(text, rule, lower=None, brands=None):
    """`text` in `rule`'s case. `lower` is an optional function for the lowercase step (a builder that keeps
    God / Bible / Lord capitalised passes its own). `brands` (brand_spellings(job_dir)): words spelled with a capital
    inside keep it in a lowercase or title-case pack; an UPPERCASE pack still shouts them."""
    rule = normalize_case(rule)
    if rule in AS_WRITTEN:
        return text
    if rule == "upper":
        return upper(text)
    if rule == "title":
        return keep_brands(title(text), brands)
    if rule == "sentence":
        return sentence(text)
    return keep_brands(lower(text) if lower else text.lower(), brands)


# A word for title case keeps its apostrophe: str.title() starts a new word after one, so "i'd" came out "I'D" and
# "family's" "Family'S" on a buyer's hook (2026-10-28), and "5th" came out "5Th".
_TITLE_WORD = _re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)*")


def title(text):
    """`text` in Title Case: every word's first letter up and the rest down, a word with an apostrophe in it kept
    whole (I'd, Mom's, Don't) and a word starting with a digit left as it is (5th)."""
    return _TITLE_WORD.sub(lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), str(text))


def sentence(text):
    """`text` in sentence case: its first word starts with a capital, every other letter exactly as written (a text
    that starts with a number, "5 swaps", is left as it is)."""
    text = str(text)
    m = _re.search(r"[^\W_]", text)
    up = m.group(0).upper() if m else ""
    if not m or not m.group(0).islower() or len(up) != 1:
        return text
    return text[:m.start()] + up + text[m.end():]
