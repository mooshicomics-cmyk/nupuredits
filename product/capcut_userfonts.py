#!/usr/bin/env python3
"""capcut_userfonts.py — resolve a font NAME to a real file on this machine, using CapCut's own font map.

Why: the animated engine (HyperFrames @font-face) needs the font FILE to render type outside CapCut.
CapCut already downloads every font the user adds — cloud-library fonts to
`…/User Data/Cache/effect/<id>/<hash>/font.ttf`, imported ones to the container `Library/Fonts/` — and
records them ALL in `…/User Data/Config/userFontData` as `<Font Name>=<absolute path>` (names URL-encoded).
So the engine can animate ANY font the buyer has in CapCut (premium / proprietary / free) WITHOUT us
shipping the file: the buyer adds it in CapCut once, and we read userFontData to find it.

Resolution order for a font (most reliable first):
  1) a bundled OFL file we ship (redistributable, machine-independent) — caller passes it
  2) CapCut's userFontData map (the buyer added the font in CapCut)
  3) CapCut's Library/Fonts by basename guess
  4) CapCut's in-app catalog cache (a font added via CapCut's text-panel search downloads to
     …/User Data/Cache/effect/<resource id>/<hash>/font.ttf, keyed by an opaque numeric id, not the
     name — so we open each cached file and read its REAL family name to match)
Returns None if the font isn't obtainable, so the caller can fall back to a pack default.
"""
import os, glob
from urllib.parse import unquote

try:  # PIL is a hard dependency of the engine; guard the import so the resolver still works if it's absent
    from PIL import ImageFont
except Exception:                       # pragma: no cover
    ImageFont = None

if os.name == "nt":
    # com.lemon.lvoverseas is a macOS app-sandbox container path and has no Windows equivalent;
    # the Windows CapCut data root is simply %LocalAppData%\CapCut.
    _DATA    = os.environ["LOCALAPPDATA"]
    _USERFD  = os.path.join(_DATA, "CapCut/User Data/Config/userFontData")
    # No per-app Fonts container on Windows -- point at a path that never exists so that lookup stage
    # cleanly falls through to the catalog scan below.
    _LIBFON  = os.path.join(_DATA, "CapCut/_no_container_fonts")
    _CATALOG = os.path.join(_DATA, "CapCut/User Data/Cache/effect")
else:
    _DATA   = os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data")
    # CapCut's User Data lives in ~/Movies for BOTH Mac installs: the capcut.com download writes there
    # directly, and the App Store copy's sandbox Movies folder is a link to ~/Movies. Read through the
    # sandbox path alone, a capcut.com install (no sandbox folder at all) reported every font as not downloaded.
    _USERDATA = os.path.expanduser("~/Movies/CapCut/User Data")
    _USERFD = os.path.join(_USERDATA, "Config/userFontData")
    _LIBFON = os.path.join(_DATA, "Library/Fonts")
    # Fonts the buyer adds through CapCut's in-app catalog (search-and-add in the text panel) download here,
    # one folder per font keyed by an opaque numeric resource id, with the file always literally `font.ttf`.
    _CATALOG = os.path.join(_USERDATA, "Cache/effect")
# Buyer's manual escape hatch: font_name -> file path, written by product/capcut_font_doctor.py when
# CapCut auto-resolution fails for some reason. Consulted right after the bundled OFL file, before CapCut.
_OVERRIDES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "font-overrides.json")


def load_overrides():
    """Parse the hand-map file -> {lowercased font name: path}. Empty if absent/malformed."""
    import json
    try:
        with open(_OVERRIDES, encoding="utf-8") as fh:
            return {str(k).strip().lower(): v for k, v in json.load(fh).items()}
    except (FileNotFoundError, ValueError):
        return {}


def _unquote_ini(value):
    """A userFontData value as a plain path. CapCut writes the file with Qt's ini format, which wraps a value
    holding characters such as "[" or "," in double quotes (a variable font: SourceSerif4[opsz,wght].ttf) and
    escapes backslashes and quotes inside. Kept quoted, the path never exists, so a font she added in CapCut
    was reported as not downloaded."""
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def load_user_fonts():
    """Parse CapCut's userFontData ini -> {lowercased font name: absolute file path}."""
    out = {}
    try:
        with open(_USERFD, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("[") or "=" not in line:
                    continue
                name, _, path = line.partition("=")
                name = unquote(name.strip())
                path = _unquote_ini(path.strip())
                if not path or name.lower() == "order":
                    continue
                out.setdefault(name.lower(), path)
    except FileNotFoundError:
        pass
    return out


def _norm(name):
    """Match key for a font name: lowercased with surrounding/internal whitespace collapsed."""
    return " ".join((name or "").split()).lower()


def font_family(path):
    """The font file's own embedded family name (e.g. 'Bloop'), or None. Guarded — PIL is optional and a
    file may be unreadable. The one collision-proof identity a catalog-cached font has (its folder is an
    opaque id and its filename is often the generic 'font.ttf')."""
    if ImageFont is None or not path or not os.path.exists(path):
        return None
    try:
        return ImageFont.truetype(path, 40).getname()[0] or None
    except Exception:
        return None


def font_face(path):
    """(family, subfamily) from the font file's own name table, e.g. ('Soup Du Jour', 'Solid'), or None when
    it cannot be read. The family alone does not tell two cuts of one font apart: Soup Du Jour's solid and
    hollow files, or Inter Bold and Inter Regular, all carry the same family name."""
    if ImageFont is None or not path or not os.path.exists(path):
        return None
    try:
        fam, sub = ImageFont.truetype(path, 40).getname()
    except Exception:
        return None
    return (fam or "", (sub or "").strip()) if fam else None


def same_face(a, b):
    """True when files a and b draw the same face: the same file, the same family AND subfamily in their name
    tables, or (when a name table cannot be read) the same bytes. Used before reusing a font copy that is
    already in CapCut's folder, so a different cut of the family that got there first is never handed out."""
    if not (a and b and os.path.exists(a) and os.path.exists(b)):
        return False
    try:
        if os.path.samefile(a, b):
            return True
    except OSError:
        pass
    fa, fb = font_face(a), font_face(b)
    if fa and fb:
        return (_norm(fa[0]), _norm(fa[1])) == (_norm(fb[0]), _norm(fb[1]))
    import filecmp
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def stable_basename(src):
    """A COLLISION-PROOF filename to copy `src` under into CapCut's Library/Fonts. The source basename is
    NOT safe any more: every font added through CapCut's in-app catalog caches as the generic 'font.ttf',
    so two different fonts would copy onto the SAME name and silently alias each other (round 11 Bug A).
    Derive the name from the font's own embedded family instead (spaces stripped, so it stays close to the
    pack's expected filenames like Bloop.ttf / SoupDuJour.ttf), falling back to the source basename only
    when PIL cannot read the family."""
    fam = font_family(src)
    if fam:
        safe = "".join(c for c in fam if c.isalnum() or c in "-_") or "font"
        return f"{safe}{os.path.splitext(src)[1] or '.ttf'}"
    return os.path.basename(src)


_catalog_cache = None

# Some catalog fonts cache MULTIPLE variants under the SAME embedded family name, differing only by
# subfamily (e.g. Soup Du Jour "Solid" vs its hollow/regular cut). Keyed by family name alone, whichever
# folder sorts first wins by luck — which handed the buyer the wrong variant. For a known-ambiguous family,
# prefer the named subfamily. Extend as new collisions turn up. capcut catalog font scan
# This is only the choice when the caller does not say which cut it wants, or the cut it wants is not there:
# a pack role that names its file (SoupDuJourHollow.ttf) gets that cut first (wanted_cut below).
_PREFERRED_SUBFAMILY = {"soup du jour": "solid"}

# The cut a pack file stands for, by its name table's subfamily, for files whose name does not say it.
# Soup Du Jour's hollow file calls itself "Regular", so its file name alone could never find it in the cache.
_FILE_CUT = {"soupdujour.ttf": "solid", "soupdujourhollow.ttf": "regular",
             "uglydavealternates.otf": "alternates"}
# Style words a file name can end in ("Inter-Bold.otf", "Poppins-SemiBold.ttf"). Anything else after a dash
# ("-VF", "-DL") is not a cut, so it asks for nothing and the old choice stands.
_STYLE_WORDS = {"thin", "hairline", "extralight", "ultralight", "light", "book", "regular", "normal", "medium",
                "semibold", "demibold", "bold", "extrabold", "ultrabold", "heavy", "black", "italic", "oblique",
                "solid", "hollow", "outline", "alternates"}


def _ncut(s):
    """A cut name as a match key: lowercase, no spaces, dashes or underscores ("Semi Bold" == "semibold")."""
    return "".join(c for c in (s or "").lower() if c.isalnum())


def wanted_cut(fileref):
    """The subfamily (as a match key) the pack file `fileref` stands for, or None when the name does not say.
    The file itself need not exist: on a buyer machine the paid face is not bundled, and this is how the
    lookup in CapCut's copies still knows a hollow takeover wants the hollow cut."""
    base = os.path.basename(fileref or "").lower()
    if not base:
        return None
    if base in _FILE_CUT:
        return _FILE_CUT[base]
    stem = os.path.splitext(base)[0]
    if "-" in stem:
        tail = _ncut(stem.rsplit("-", 1)[1])
        if tail in _STYLE_WORDS or (tail.endswith("italic") and tail[:-6] in _STYLE_WORDS):
            return tail
    return None


def scan_capcut_catalog_variants(container=None):
    """Every font CapCut's in-app catalog has downloaded, as {normalized family name: [(subfamily key, path)]}.

    A catalog-added font is cached at …/Cache/effect/<resource id>/<hash>/<file>. The folder is keyed by an
    opaque numeric id (not the font name) and the file is often the generic `font.ttf` but can also carry a
    descriptive name (e.g. `Ugly-Dave-Alternates.otf`), so we glob ANY .ttf/.otf there — NOT just `font.*`,
    which silently missed the descriptively-named ones — and read each file's real family and subfamily via
    PIL. Sorted by path, so the order never depends on the disk. Cached within a run; skips unopenable files."""
    global _catalog_cache
    default = container is None
    if default and _catalog_cache is not None:
        return _catalog_cache
    root = container or _CATALOG
    variants = {}
    if ImageFont is not None:
        for path in sorted(glob.glob(os.path.join(root, "*", "*", "*.ttf")) +
                           glob.glob(os.path.join(root, "*", "*", "*.otf"))):
            try:
                fam, sub = ImageFont.truetype(path, 40).getname()
            except Exception:
                continue
            if fam:
                variants.setdefault(_norm(fam), []).append((_ncut(sub), path))
    if default:
        _catalog_cache = variants
    return variants


def _preferred(nfam, vs):
    """The variant chosen when no cut is asked for (or the asked-for one is missing): the family's
    _PREFERRED_SUBFAMILY entry if it is there, else the first by path."""
    pref = _ncut(_PREFERRED_SUBFAMILY.get(nfam))
    return next((p for s, p in vs if pref and s == pref), None) or vs[0][1]


def scan_capcut_catalog_fonts(container=None):
    """Index every font CapCut's in-app catalog has downloaded, keyed by the font's REAL family name.
    When two files share a family name, a `_PREFERRED_SUBFAMILY` entry picks the right variant instead of
    alphabetical luck. Returns {normalized family name: path}."""
    return {nfam: _preferred(nfam, vs) for nfam, vs in scan_capcut_catalog_variants(container).items()}


_said_cut = set()


def _cut_of(path):
    face = font_face(path)
    return _ncut(face[1]) if face else None


def _say_other_cut(name, fileref, path):
    """One plain line (on stderr, so a caller printing a path or JSON on stdout is untouched) and one line in
    the fallbacks log, once per font per run, when the cut a pack asks for is not on this computer."""
    key = (name, os.path.basename(fileref or ""))
    if key in _said_cut:
        return
    _said_cut.add(key)
    face = font_face(path) or (name, "")
    asked = os.path.splitext(os.path.basename(fileref or ""))[0] or name
    import sys
    print(f"  {name}: the cut this pack asks for ({asked}) is not in CapCut on this computer, so "
          f"{face[0]} {face[1]} is used in its place. Adding that cut in CapCut brings the pack's exact look back.",
          file=sys.stderr)
    try:
        import fallbacks
        fallbacks.note("pack fonts", f"{name}: the pack's cut {asked} was not in CapCut; used {face[0]} {face[1]}")
    except Exception:
        pass


# A family's file can carry more than its name: Google's variable fonts ship as Caveat-VF.ttf, Name-Variable.ttf
# or Name[wght].ttf, and CapCut keeps the file name it was given. Looked for by the bare name alone, a Caveat she
# had added in CapCut (and the very Caveat the engine bundles) was reported "not installed yet" (a buyer,
# 2026-10-12), and needed a hand-map.
_NAME_TAILS = ("", "-VF", "-Variable", "-Regular", "VF")


def _named_files(folder, cand):
    """The files in `folder` named for `cand` itself or as its variable or regular file, in that order."""
    out = []
    for tail in _NAME_TAILS:
        for ext in (".ttf", ".otf", ".ttc"):
            fp = os.path.join(folder, cand + tail + ext)
            if os.path.exists(fp):
                out.append(fp)
    out += sorted(p for p in glob.glob(os.path.join(glob.escape(folder), glob.escape(cand) + "[[]*[]].*"))
                  if p.lower().endswith((".ttf", ".otf")))
    return out


_family_cache = {}


def _family_files(folder):
    """Every .ttf/.otf in `folder` by the family name its own name table gives: {normalized family: [paths]}.
    Read once per folder per run; files whose name says italic come last, so a family's upright file wins."""
    if folder in _family_cache:
        return _family_cache[folder]
    fams = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        names = []
    for f in sorted(names, key=lambda f: ("italic" in f.lower(), f.lower())):
        if f.lower().endswith((".ttf", ".otf")):
            fam = font_family(os.path.join(folder, f))
            if fam:
                fams.setdefault(_norm(fam), []).append(os.path.join(folder, f))
    _family_cache[folder] = fams
    return fams


BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")


def bundled_font_for(name):
    """The engine's own bundled file for the family `name` (e.g. 'Caveat' -> assets/fonts/Caveat-VF.ttf), or None.
    By file name first, then by each bundled file's own family name. A caller that knows only the family (a pack
    built from a frame) checks here first, so a font the engine ships is never sent to CapCut to be found."""
    if not name:
        return None
    for cand in (name, name.replace(" ", ""), name.replace(" ", "-")):
        hits = [p for p in _named_files(BUNDLED_DIR, cand) if "italic" not in os.path.basename(p).lower()]
        if hits:
            return hits[0]
    fams = _family_files(BUNDLED_DIR).get(_norm(name))
    return fams[0] if fams else None


def resolve_font_file(name, bundled_file=None, cut=None):
    """Return a real font-file path for `name`, or None. `bundled_file` (an assets/fonts path) wins if it
    exists — that's the shippable OFL case. Otherwise fall back to what CapCut has on the machine.

    Pass the pack's file reference as `bundled_file` even when it is missing: its name says which CUT of the
    family the role wants (wanted_cut; or pass `cut` directly), and every copy found by name is then checked
    against its name table, so a hollow takeover gets CapCut's hollow file, never the solid one that shares
    the family name. Only when no copy of that cut is on this computer does the old choice stand, said in
    one plain line. With no cut asked for, the lookup is exactly as before."""
    if bundled_file and os.path.exists(bundled_file):
        return bundled_file
    # buyer's hand-map wins over CapCut auto-resolution (their explicit fix when auto fails)
    ov = load_overrides().get((name or "").strip().lower())
    if ov:
        ov = os.path.expanduser(ov)
        if os.path.exists(ov):
            return ov
    want = _ncut(cut) or wanted_cut(bundled_file)
    other = None            # a copy of the family in another cut: used only if the asked-for cut is nowhere

    def fits(path):
        nonlocal other
        if not want:
            return True
        got = _cut_of(path)
        if got is None or got == want:    # unreadable name table: trust the name match, as before
            return True
        other = other or path
        return False

    p = load_user_fonts().get((name or "").strip().lower())
    if p and os.path.exists(p) and fits(p):
        return p
    if name:
        cands = [name, name.replace(" ", ""), name.replace(" ", "-"), name.replace(" ", "_")]
        if want and bundled_file:         # her CapCut folder may hold this cut under the pack's own file name
            cands.insert(0, os.path.splitext(os.path.basename(bundled_file))[0])
        for cand in cands:
            for fp in _named_files(_LIBFON, cand):
                if fits(fp):
                    return fp
        # a file in CapCut's Fonts folder named some other way: matched on its own family name
        for fp in _family_files(_LIBFON).get(_norm(name), []):
            if fits(fp):
                return fp
        # last resort: a font added via CapCut's in-app catalog is cached by an opaque id (not by name),
        # so the by-name checks above all miss it. Match on the cached file's real family name instead.
        nfam = _norm(name)
        vs = [(s, cp) for s, cp in scan_capcut_catalog_variants().get(nfam, []) if os.path.exists(cp)]
        if vs:
            hit = next((cp for s, cp in vs if want and s == want), None)
            if hit:
                return hit
            if not want:
                return _preferred(nfam, vs)
            other = other or _preferred(nfam, vs)
    if other:
        _say_other_cut(name, bundled_file, other)
        return other
    return None


def source_of(name, bundled_file=None):
    """Human-readable where-from for a resolved font: 'bundled' | 'capcut' | 'libfonts' | 'MISSING'."""
    if bundled_file and os.path.exists(bundled_file):
        return "bundled"
    p = resolve_font_file(name, None)
    if not p:
        return "MISSING"
    return "capcut" if "/Cache/effect/" in p else "libfonts"


if __name__ == "__main__":
    um = load_user_fonts()
    print(f"userFontData: {len(um)} fonts CapCut has on this machine")
    for k, v in um.items():
        where = "cloud-cache" if "/Cache/effect/" in v else "lib-fonts"
        print(f"  {k:20s} [{where}] {os.path.basename(v)}")
