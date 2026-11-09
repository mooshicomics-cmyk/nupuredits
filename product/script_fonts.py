#!/usr/bin/env python3
"""script_fonts.py — letters a pack font does not have: Cyrillic, Greek, Korean, accented Latin, French quote marks.

Most pack faces draw only the Latin alphabet. Handed a Bulgarian (or Russian, Ukrainian, Serbian...) word,
the headless browser that renders every graphic finds no glyph and quietly borrows the letter from a system
font, usually a serif, so a caption comes out half Poppins and half Times. Nothing errors.

The fix is the ordinary web one: a second @font-face under the SAME family name, limited by unicode-range
to Cyrillic and declared after the pack's, so the browser draws Cyrillic letters from a bundled face that
has them and every other letter from the pack face, exactly as before. The companion is picked to suit the
face it stands in for (handwritten for a script face, serif for a serif, Inter at the nearest weight for
the rest), read from the font file's own name, since pack faces leave their style metadata blank.

Greek works the same way, as a whole alphabet of its own. Playfair draws Cyrillic but not Greek and Caveat
neither, so Greek has two companions of its own: Noto Serif Display for a serif face and Mynerve for a
handwritten one (Inter already has Greek, so sans and display faces use it for both alphabets). A letter
even the companion lacks (Mynerve has no polytonic Greek) goes on to Inter at the face's weight, which has
them all, so no letter is ever left for the browser to borrow.

Korean (Hangul, with the CJK quote marks and punctuation it uses) is a whole alphabet too, and no Latin
companion has it, so it has its own three: Noto Sans KR at the face's weight (Regular, Bold, Black, cut from
its variable font so CapCut gets a real weight too) for sans and display faces, Nanum Myeongjo for a serif
and Gaegu for a handwritten one.

The same holds closer to home. Many pack faces draw é and ç but not « » (French quotes), æ ø (Danish,
Norwegian), ª º (Spanish ordinals) or the Polish, Czech, Romanian and Turkish letters. Those go to the same
companion, but only the exact letters the face lacks: Cyrillic is handed over as a whole alphabet, accented
Latin one character at a time, so a face keeps drawing every letter it does have.

It only acts when the page actually shows such a letter AND a face on it lacks it. Anything else comes back
byte for byte as it went in, so a reel in English renders exactly as it always did.

    import script_fonts
    html, notes = script_fonts.add_companions(html, comp_dir)   # before writing index.html
    python3 product/script_fonts.py <composition_dir>            # patch an index.html in place
"""
import os, re, shutil, struct, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")
MARK = "/* cyrillic-companions */"   # the name predates Greek and Korean; kept, so a page done before is never done twice
RANGE = "U+0400-052F,U+1C80-1C8F,U+2DE0-2DFF,U+A640-A69F"
GREEK = "U+0370-03FF,U+1F00-1FFF"
KOREAN = "U+1100-11FF,U+3000-303F,U+3130-318F,U+A960-A97F,U+AC00-D7FF"
_CYR = re.compile("[Ѐ-ԯᲀ-᲏ⷠ-ⷿꙀ-ꚟ]")
_GRK = re.compile("[\u0370-\u03ff\u1f00-\u1fff]")
_KOR = re.compile("[\u1100-\u11ff\u3000-\u303f\u3130-\u318f\ua960-\ua97f\uac00-\ud7ff]")
# the alphabets handed over whole: (tag, unicode-range, letters, name said to her)
SCRIPTS = (("cyr", RANGE, _CYR, "Cyrillic"), ("grk", GREEK, _GRK, "Greek"), ("kor", KOREAN, _KOR, "Korean"))
_MARKS = "«»‹›"     # guillemets: French (and Spanish, Italian, Russian...) quote marks
_GREEK_MARKS = "·"  # the Greek ano teleia: Unicode folds U+0387 into this middle dot (Korean writes it too, 3·1절).
                    # Handed over only on a page with Greek or Korean letters, since the build pages carry · in
                    # their own markup


def _latin(ch):
    """An accented or extended Latin letter, or a guillemet: the letters a Latin pack face may still lack.
    Plain ASCII never counts, so an English page is never touched."""
    o = ord(ch)
    if ch in _MARKS:
        return True
    return (0xAA <= o <= 0x24F or 0x1E00 <= o <= 0x1EFF) and unicodedata.category(ch).startswith("L")

# What a face is, from its own family name (letters only, lowercased, matched as a prefix). Anything not
# listed is treated as a sans and gets Inter at its weight.
_KIND = [
    ("prosecco", "hand"), ("pinyon", "hand"), ("uglydave", "hand"), ("caveat", "hand"), ("bloop", "hand"),
    ("playfair", "serif"), ("instrumentserif", "serif"),
    ("soupdujour", "display"), ("shrikhand", "display"), ("advercase", "display"), ("zymodern", "display"),
]


def _companion(kind, weight, script="cyr"):
    """The bundled face that draws `script` ("cyr", "grk" for Greek, "kor" for Korean) in place of a face of
    this kind and weight. The Cyrillic choice also draws the accented Latin letters a face lacks."""
    if script == "kor":
        if kind == "hand":
            return "Gaegu-Regular.ttf"
        if kind == "serif":
            return "NanumMyeongjo-Bold.ttf" if weight >= 550 else "NanumMyeongjo-Regular.ttf"
        if kind == "display" or weight >= 800:
            return "NotoSansKR-Black.ttf"
        return "NotoSansKR-Bold.ttf" if weight >= 550 else "NotoSansKR-Regular.ttf"
    if script == "grk" and kind == "hand":
        return "Mynerve-Regular.ttf"
    if script == "grk" and kind == "serif":
        return "NotoSerifDisplay-VF.ttf"
    if kind == "hand":
        return "Caveat-VF.ttf"
    if kind == "serif":
        return "PlayfairDisplay-SemiBold.ttf" if weight >= 550 else "PlayfairDisplay-VF.ttf"
    if kind == "display" or weight >= 800:
        return "Inter-Black.otf"
    return "Inter-Bold.otf" if weight >= 550 else "Inter-Regular.otf"


# ── just enough of the font file format to answer three questions: name, weight, which letters ──────────
def _tables(data):
    off = struct.unpack(">I", data[12:16])[0] if data[:4] == b"ttcf" else 0   # a collection: its first font
    n = struct.unpack(">H", data[off + 4:off + 6])[0]
    t = {}
    for i in range(n):
        r = off + 12 + 16 * i
        t[data[r:r + 4].decode("latin-1")] = struct.unpack(">II", data[r + 8:r + 16])
    return t


def _codepoints(data, t):
    if "cmap" not in t:
        return set()
    base = t["cmap"][0]
    subs = {}
    for i in range(struct.unpack(">H", data[base + 2:base + 4])[0]):
        pid, eid, so = struct.unpack(">HHI", data[base + 4 + 8 * i:base + 12 + 8 * i])
        subs[(pid, eid)] = base + so
    for key in ((3, 10), (0, 6), (0, 4), (3, 1), (0, 3), (0, 2), (0, 1), (0, 0)):
        if key not in subs:
            continue
        s = subs[key]
        fmt = struct.unpack(">H", data[s:s + 2])[0]
        out = set()
        if fmt == 12:
            for g in range(struct.unpack(">I", data[s + 12:s + 16])[0]):
                a, b, gid = struct.unpack(">III", data[s + 16 + 12 * g:s + 28 + 12 * g])
                out.update(range(a + (gid == 0), b + 1))   # glyph 0 is "no glyph"
            return out
        if fmt == 4:
            seg = struct.unpack(">H", data[s + 6:s + 8])[0] // 2
            ends, starts = s + 14, s + 16 + 2 * seg
            deltas, ranges = starts + 2 * seg, starts + 4 * seg
            for k in range(seg):
                e = struct.unpack(">H", data[ends + 2 * k:ends + 2 * k + 2])[0]
                st = struct.unpack(">H", data[starts + 2 * k:starts + 2 * k + 2])[0]
                d = struct.unpack(">h", data[deltas + 2 * k:deltas + 2 * k + 2])[0]
                ro_at = ranges + 2 * k
                ro = struct.unpack(">H", data[ro_at:ro_at + 2])[0]
                for c in range(st, min(e, 0xFFFE) + 1):
                    if ro == 0:
                        gid = (c + d) & 0xFFFF
                    else:
                        at = ro_at + ro + 2 * (c - st)
                        gid = struct.unpack(">H", data[at:at + 2])[0]
                        gid = (gid + d) & 0xFFFF if gid else 0
                    if gid:
                        out.add(c)
            return out
    return set()


def _family(data, t):
    if "name" not in t:
        return ""
    base = t["name"][0]
    count, strings = struct.unpack(">HH", data[base + 2:base + 6])
    found = {}
    for i in range(count):
        pid, eid, lid, nid, ln, off = struct.unpack(">HHHHHH", data[base + 6 + 12 * i:base + 18 + 12 * i])
        if nid in (1, 16) and nid not in found:
            raw = data[base + strings + off:base + strings + off + ln]
            try:
                found[nid] = raw.decode("utf-16-be") if pid in (0, 3) else raw.decode("mac_roman")
            except UnicodeDecodeError:
                pass
    return found.get(16) or found.get(1) or ""


_info = {}


def face_info(path):
    """(family name, weight, set of code points) for a font file, cached. None if it cannot be read."""
    if path not in _info:
        try:
            with open(path, "rb") as f:
                data = f.read()
            t = _tables(data)
            weight = struct.unpack(">H", data[t["OS/2"][0] + 4:t["OS/2"][0] + 6])[0] if "OS/2" in t else 400
            _info[path] = (_family(data, t), weight or 400, _codepoints(data, t))
        except Exception:
            _info[path] = None
    return _info[path]


def _kind(info):
    name = "".join(c for c in info[0].lower() if c.isalnum())
    return next((k for p, k in _KIND if name.startswith(p)), "sans")


def companion_for(path, letters):
    """The bundled file to draw `letters` in, when the face at `path` lacks any of them. None when it
    covers them all, or when it cannot be read (then nothing is changed). Greek or Korean letters pick that
    alphabet's companion; anything else the Cyrillic one."""
    info = face_info(path)
    if not info or {ord(c) for c in letters} <= info[2]:
        return None
    script = next((tag for tag, _s, rx, _n in SCRIPTS[1:] if any(rx.match(c) for c in letters)), "cyr")
    return os.path.join(FONTS, _companion(_kind(info), info[1], script))


def _has(path, ch):
    info = face_info(path)
    return bool(info) and ord(ch) in info[2]


def _handover(path, letters):
    """The companion rules for the face at `path` and the letters a page or a line shows, in the order they
    are written into the page: [{"comp": file, "alpha": ["cyr", "grk"], "chars": {letters}}]. An alphabet
    the face lacks any letter of goes over whole; an accented Latin letter goes over alone; a letter the
    chosen companion lacks too goes on to Inter at the face's weight (a Korean one to Noto Sans KR), in a rule
    written last so it wins.
    Mirrors what add_companions writes, so a width is measured on the face the browser will really use.
    [] when the face draws everything itself, or cannot be read."""
    info = face_info(path) if path else None
    if not info:
        return []
    kind, weight, own = _kind(info), info[1], info[2]
    rules, rest = [], set()

    def rule(comp):
        for r in rules:
            if r["comp"] == comp:
                return r
        rules.append({"comp": comp, "alpha": [], "chars": set()})
        return rules[-1]

    for tag, _span, rx, _name in SCRIPTS:
        need = {c for c in letters if rx.match(c)}
        if not need or {ord(c) for c in need} <= own:
            continue
        comp = os.path.join(FONTS, _companion(kind, weight, tag))
        if not face_info(comp):
            continue
        rule(comp)["alpha"].append(tag)
        rest |= {c for c in need if not _has(comp, c)}
    latin = os.path.join(FONTS, _companion(kind, weight))
    greek = os.path.join(FONTS, _companion(kind, weight, "grk")) if any(_GRK.match(c) for c in letters) else None
    korean = os.path.join(FONTS, _companion(kind, weight, "kor")) if any(_KOR.match(c) for c in letters) else None
    for c in letters:
        if ord(c) in own:
            continue
        if (greek or korean) and c in _GREEK_MARKS:  # with the Greek (or Korean) letters it punctuates
            mark = greek or korean
            (rule(mark)["chars"].add(c) if _has(mark, c) else rest.add(c))
        elif _latin(c):
            (rule(latin)["chars"].add(c) if _has(latin, c) else rest.add(c))
    inter = os.path.join(FONTS, _companion("sans", weight))
    hangul = os.path.join(FONTS, _companion("sans", weight, "kor"))   # Inter has no Hangul; Gaegu stops at the 2,350 common syllables
    for c in rest:
        fb = hangul if _KOR.match(c) else inter
        if _has(fb, c):
            rule(fb)["chars"].add(c)
    return [r for r in rules if r["alpha"] or r["chars"]]


def _drawn_by(rules, ch):
    """Which rule's companion draws `ch`: the last one written that covers it (the browser checks the
    later @font-face first). None when the face draws it itself."""
    for r in reversed(rules):
        if ch in r["chars"] or any(rx.match(ch) for tag, _s, rx, _n in SCRIPTS if tag in r["alpha"]):
            return r["comp"]
    return None


def split(path, text):
    """[(font file, run of text)]: how the browser will draw `text` set in the face at `path`, so a width
    can be measured on the letters actually drawn. Letters the face lacks (its Cyrillic or Greek, or a « »
    or ø it has no glyph for) go to its companion; every other case is the one run [(path, text)], as before."""
    rules = _handover(path, set(text or ""))
    if not rules:
        return [(path, text)]
    runs = []
    for ch in text:
        p = _drawn_by(rules, ch) or path
        if runs and runs[-1][0] == p:
            runs[-1] = (p, runs[-1][1] + ch)
        else:
            runs.append((p, ch))
    return runs


def pil_width(font, text):
    """Width of `text` on a loaded PIL font once any letters it lacks come from its companion, or None
    when nothing needs a companion (then measure as usual)."""
    path = getattr(font, "path", None)
    parts = split(path, text)
    if all(p == path for p, _ in parts):   # every letter in the face itself (a word all in Greek is one run, in the companion)
        return None
    from PIL import ImageFont
    return sum(ImageFont.truetype(p, font.size).getlength(s) for p, s in parts)


# ── the editable CapCut route ──────────────────────────────────────────────────────────────────────────
# CapCut draws a draft's text itself, so no @font-face reaches it. What does reach it is a text's style
# spans: each span names its own font file (CapCut writes them so when she sets one word in another font),
# so a letter the pack font lacks gets a span of its own in the same companion the rendered routes use.
# CapCut counts a span's range in UTF-16 units, not letters: a text CapCut saved as "😂😂😂" reads [0, 6].

def _u16(s):
    return len(s.encode("utf-16-le")) // 2


def _companion_letter(c):
    return bool(_CYR.match(c) or _GRK.match(c) or _KOR.match(c) or _latin(c) or c in _GREEK_MARKS)


def capcut_runs(path, text):
    """[(font file, start, end)] in code points: split(), except that spaces between two runs of the same
    face join them, so a Greek line is one span and not one per word. Exactly [(path, 0, len)] when nothing
    needs a companion (an all-Greek line is one run too, but in the companion)."""
    runs = []
    for p, t in split(path, text):
        runs.append([p, t])
    i = 1
    while i < len(runs) - 1:
        if not runs[i][1].strip() and runs[i - 1][0] == runs[i + 1][0]:
            runs[i - 1][1] += runs[i][1] + runs[i + 1][1]
            del runs[i:i + 2]
        else:
            i += 1
    out, at = [], 0
    for p, t in runs:
        out.append((p, at, at + len(t)))
        at += len(t)
    return out


def _capcut_path(comp):
    """Where CapCut can load a companion from (its own font folder; packbuild copies it there). None when
    it cannot be put there."""
    import packbuild
    dst = packbuild.capcut_font_path(comp)
    return dst if dst and os.path.exists(dst) else None


def _fallback_note(name, gone):
    return (f"{' and '.join(gone)} letters in {name} show in CapCut's own built-in font (a plain sans) in this "
            f"draft: no bundled face could be handed to CapCut for them. The medium and well-done routes draw "
            f"them in a matching face.")


def capcut_companions(material, font_path, resolve=_capcut_path):
    """Give the letters `font_path` lacks their companion face inside one CapCut text material, in place.
    Each style span that covers such letters becomes one span per run, a copy with the same size, color and
    effects, differing only in range and font.path; the text stays one editable clip. Ranges are written in
    UTF-16 units, as CapCut counts them. A text needing no companion is left byte for byte. Returns a plain
    note when some letter still has no face of its own in CapCut (CapCut then draws it from its built-in
    Noto Sans), else None. Never raises: on any trouble the material is left as it was."""
    import copy, json
    try:
        c = json.loads(material["content"])
        text, styles = c.get("text", ""), c.get("styles") or []
        runs = capcut_runs(font_path, text)
        if runs == [(font_path, 0, len(text))] or not styles:
            return None
        loadable = {}
        for p, _a, _b in runs:
            if p != font_path and p not in loadable:
                loadable[p] = resolve(p)
        u16 = [0]
        for ch in text:
            u16.append(u16[-1] + _u16(ch))
        out = []
        for st in sorted(styles, key=lambda s: (s.get("range") or [0])[0]):
            r = st.get("range")
            if not (isinstance(r, list) and len(r) == 2):
                out.append(st)
                continue
            for p, a, b in runs:
                lo, hi = max(a, r[0]), min(b, r[1])
                if lo >= hi:
                    continue
                piece = copy.deepcopy(st)
                piece["range"] = [u16[lo], u16[min(hi, len(text))]]
                if p != font_path and loadable.get(p) and isinstance(piece.get("font"), dict):
                    piece["font"]["path"] = loadable[p]
                    piece["font"]["id"] = ""
                out.append(piece)
        c["styles"] = out
        drawn = {}
        for p, a, b in runs:
            face = p if p == font_path or loadable.get(p) else font_path
            for ch in text[a:b]:
                drawn[ch] = face
        gone = []
        for _t, _s, rx, label in SCRIPTS:
            if any(rx.match(ch) and ord(ch) not in (face_info(f) or ("", 0, set()))[2] for ch, f in drawn.items()):
                gone.append(label)
        if not gone and any(_companion_letter(ch) and ord(ch) not in (face_info(f) or ("", 0, set()))[2]
                            for ch, f in drawn.items()):
            gone.append("Accented")
        material["content"] = json.dumps(c, ensure_ascii=False)
        if not gone:
            return None
        info = face_info(font_path)
        return _fallback_note((info and info[0]) or os.path.basename(font_path), gone)
    except Exception:
        return None


_capcut_said = set()


def say_capcut(line):
    """Print a capcut_companions note once per run (the CapCut builders call it per text). Never raises."""
    if line and line not in _capcut_said:
        _capcut_said.add(line)
        print(f"  {line}")


# ── the page ───────────────────────────────────────────────────────────────────────────────────────────
_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.I)


def _desc(body, name):
    m = re.search(name + r"\s*:\s*([^;]+)", body, re.I)
    return m.group(1).strip() if m else None


def add_companions(html, comp_dir):
    """Return (html, notes). Adds a companion after each @font-face whose file lacks letters the page shows
    (Cyrillic, Greek, Korean, accented Latin, « »). Unchanged (and notes empty) when the page has none of those
    letters, or has been through here."""
    if MARK in html:
        return html, []
    letters = {c for c in set(html) if _CYR.match(c) or _GRK.match(c) or _KOR.match(c) or _latin(c)}
    if not letters:
        return html, []
    if any(_GRK.match(c) or _KOR.match(c) for c in letters):
        letters |= {c for c in _GREEK_MARKS if c in html}
    names = {tag: label for tag, _s, _rx, label in SCRIPTS}
    spans = {tag: span for tag, span, _rx, _l in SCRIPTS}
    rules, notes, done = [], [], set()
    for m in _FACE.finditer(html):
        body = m.group(1)
        fam = (_desc(body, "font-family") or "").strip("'\" ")
        url = re.search(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", body)
        if not fam or not url or _desc(body, "unicode-range"):
            continue
        src = url.group(1)
        src = src[7:] if src.startswith("file://") else src
        path = src if os.path.isabs(src) else os.path.join(comp_dir, src)
        if not os.path.exists(path):
            continue
        extra = "".join(f"{d}:{_desc(body, d)};" for d in ("font-weight", "font-style") if _desc(body, d))
        name = face_info(path)[0] or os.path.basename(path)
        for r in _handover(path, letters):
            comp = r["comp"]
            if not os.path.exists(comp):
                continue
            pre = f"fonts/{r['alpha'][0]}-" if r["alpha"] else "fonts/comp-"
            rel = pre + os.path.basename(comp)
            os.makedirs(os.path.join(comp_dir, "fonts"), exist_ok=True)
            dst = os.path.join(comp_dir, rel)
            if not os.path.exists(dst):
                shutil.copy(comp, dst)
            span = [spans[t] for t in r["alpha"]] + [f"U+{ord(c):04X}" for c in sorted(r["chars"])]
            rules.append(f"@font-face{{font-family:'{fam}';src:url('{rel}');unicode-range:{','.join(span)};{extra}}}")
            cname = os.path.splitext(os.path.basename(comp))[0]
            for t in r["alpha"]:
                if (name, cname, t) not in done:
                    done.add((name, cname, t))
                    notes.append(f"{names[t]} letters in {name} are drawn from {cname}, since that font does not have them.")
            lat = r["chars"]
            if lat and (name, cname, "".join(sorted(lat))) not in done:
                done.add((name, cname, "".join(sorted(lat))))
                notes.append(f"{' '.join(sorted(lat))} in {name} {'is' if len(lat) == 1 else 'are'} drawn from {cname}, "
                             f"since that font does not have {'it' if len(lat) == 1 else 'them'}.")
    if not rules:
        return html, []
    block = MARK + "\n" + "\n".join(rules) + "\n"
    at = html.find("</style>")
    html = html[:at] + block + html[at:] if at >= 0 else html.replace("</head>", f"<style>{block}</style></head>", 1)
    return html, notes


def patch_dir(comp_dir):
    """Apply add_companions to <comp_dir>/index.html in place; print what it did. Returns the notes."""
    index = os.path.join(comp_dir, "index.html")
    if not os.path.exists(index):
        return []
    with open(index, encoding="utf-8") as f:
        html = f.read()
    new, notes = add_companions(html, comp_dir)
    if new != html:
        with open(index, "w", encoding="utf-8") as f:
            f.write(new)
    for n in notes:
        print(f"  {n}")
    return notes


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: script_fonts.py <composition_dir>")
    patch_dir(sys.argv[1])
