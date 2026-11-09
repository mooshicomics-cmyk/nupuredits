import sys
#!/usr/bin/env python3
"""capcut_font_doctor.py — check that every style-pack font resolves, and hand-map any that don't.

The engine resolves each pack's fonts BY NAME from the buyer's own CapCut (CapCut Pro carries the licensed
display faces). Normally that "just works." This is the safety net for when it doesn't — a wrong CapCut
name, a font not added yet, a nonstandard install. It tells the buyer EXACTLY which font is missing and
gives two ways to fix it, then re-checks.

  python3 product/capcut_font_doctor.py                 # check every pack
  python3 product/capcut_font_doctor.py Playful         # check one pack
  python3 product/capcut_font_doctor.py --map "Ugly Dave=/path/to/UglyDave.otf"   # hand-map a font
  python3 product/capcut_font_doctor.py --unmap "Ugly Dave"                        # remove a hand-map

Resolution order for each pack font (first hit wins):
  1) a bundled OFL file we ship (assets/fonts/<file>) — machine-independent, always works
  2) a hand-map the buyer added here (font-overrides.json) — the manual escape hatch this tool writes
  3) the buyer's CapCut, by name (userFontData) — the normal path (CapCut Pro)
  4) CapCut's Library/Fonts by basename guess
  5) CapCut's in-app catalog cache — a font added via CapCut's text-panel search is cached by an opaque
     id, not by name, so its real family name is read out of the cached file (see capcut_userfonts)
A font that resolves anywhere = ✓. A font that resolves NOWHERE = ✗ and is reported with a fix.

The hand-map is written to product/creative-vault/font-overrides.json and is read by the engine's shared
resolver (capcut_userfonts.resolve_font_file) on every build, so a fix here fixes every format at once.
"""
import argparse, json, os, sys, importlib.util

# Windows' console defaults to a legacy codepage that cannot print the checkmark/circle symbols below,
# which crashes with UnicodeEncodeError before the buyer ever sees the actual font report. Harmless
# no-op on macOS/Linux, which are already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Buyer-facing: Cmd+Q does not exist on Windows (the same words draft_safety uses).
_QUIT_HINT = "right-click its taskbar icon and Close, or use Task Manager" if os.name == "nt" else "Cmd+Q"
PACKS_JSON = os.path.join(ROOT, "product", "creative-vault", "style-packs.json")
OVERRIDES = os.path.join(ROOT, "product", "creative-vault", "font-overrides.json")
FONT_DIR = os.path.join(ROOT, "assets", "fonts")

# A few CapCut fonts are listed under a different SEARCH NAME than their family name. When we tell the buyer
# to find a font in CapCut's font panel, we must give the name CapCut actually shows, or they won't find it.
# (Soup Du Jour ships a "Solid" cut and CapCut lists it as "Solid".)
_CAPCUT_SEARCH_NAME = {"soup du jour": "solid"}


def capcut_search_hint(name):
    """Return ' (in CapCut, search: X)' when the font is listed under a different name, else ''."""
    alt = _CAPCUT_SEARCH_NAME.get((name or "").strip().lower())
    return f'  (in CapCut, search: "{alt}")' if alt else ""


def _load_resolver():
    cu = os.path.join(HERE, "capcut_userfonts.py")
    spec = importlib.util.spec_from_file_location("capcut_userfonts", cu)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_overrides():
    try:
        with open(OVERRIDES, encoding="utf-8") as f:
            return {k.strip().lower(): v for k, v in json.load(f).items()}
    except (FileNotFoundError, ValueError):
        return {}


def save_overrides(d):
    os.makedirs(os.path.dirname(OVERRIDES), exist_ok=True)
    with open(OVERRIDES, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, sort_keys=True)


def required_fonts(pack_spec):
    """[(role, font_name, bundled_file_or_None)] for a pack — same shape resolve-pack reads."""
    out, seen = [], set()
    el = pack_spec.get("elements", {}) or {}
    role_map = [("headline", "headline", "main"),
                ("caption", "caption", "caption"),
                ("accent", "accent_caption", "accent")]
    fonts = pack_spec.get("fonts", {}) or {}
    for role, elkey, fontkey in role_map:
        e = el.get(elkey) or (el.get("caption") if elkey == "accent_caption" else {}) or {}
        name = e.get("font") or pack_spec.get(f"{role}_font_name") or fonts.get(fontkey)
        fil = e.get("file") or pack_spec.get(f"{role}_font_file")
        if not name and not fil:
            continue
        key = (name or "", fil or "")
        if key in seen:
            continue
        seen.add(key)
        out.append((role, name, fil))
    return out


def resolve(cu, overrides, name, bundled_file):
    """Return (path, source) or (None, None). source in bundled|hand-map|capcut|capcut-lib|on your computer."""
    if bundled_file and str(bundled_file).startswith("SYSTEM:"):
        # a font installed on her computer, pointed at by path (a pack the DESIGN.md import or a recipe wrote):
        # CapCut desktop shows every installed font, so it is ready as long as that file is still there
        try:
            import stylepack
            sp = stylepack._abs(bundled_file)
        except Exception:
            sp = ""
        if sp and os.path.isfile(sp):
            return sp, "on your computer"
    if bundled_file:
        # os.path.join keeps an ABSOLUTE bundled_file as-is, so a pack whose element carries a full path
        # (every pack built by frame_to_pack / pack_recipe does) used to land here and get reported as
        # "bundled (ships)" while actually pointing at a machine-local font. Only a file that really sits
        # inside the bundled font dir ships; anything else falls through to the hand-map / CapCut sources
        # below, which is what it actually is.
        bp = os.path.join(FONT_DIR, bundled_file)
        if os.path.isfile(bp) and os.path.commonpath([os.path.realpath(bp),
                                                      os.path.realpath(FONT_DIR)]) == os.path.realpath(FONT_DIR):
            return bp, "bundled (ships)"
    ov = overrides.get((name or "").strip().lower())
    if ov and os.path.isfile(ov):
        return ov, "hand-map"
    p = cu.resolve_font_file(name, None)
    if p and os.path.isfile(p):
        # distinguish an in-app-catalog font (cached under Cache/effect) from a manually-installed one
        # just for the message; both are "from your CapCut".
        src = "your CapCut (in-app catalog)" if "/Cache/effect/" in p else "your CapCut"
        return p, src
    return None, None


def check(packs_filter=None):
    cu = _load_resolver()
    overrides = load_overrides()
    cfg = json.load(open(PACKS_JSON, encoding="utf-8"))
    packs = cfg.get("packs", {})
    want = [k for k in packs if not packs_filter or k.lower() in [p.lower() for p in packs_filter]]
    if packs_filter and not want:
        sys.exit(f"font-doctor: no such pack. Available: {', '.join(packs.keys())}")
    any_missing = []
    for pk in want:
        print(f"\n== {pk} ==")
        for role, name, fil in required_fonts(packs[pk]):
            path, src = resolve(cu, overrides, name, fil)
            label = name or fil or "?"
            if path:
                print(f"  ✓ {role:<9} {label:<26} → {src}")
            else:
                print(f"  ○ {role:<9} {label:<26} → not downloaded to CapCut yet")
                any_missing.append((pk, role, name, fil))
    if any_missing:
        print("\n" + "─" * 64)
        print("A few of your pack fonts are not downloaded to CapCut yet. This is NORMAL on a fresh CapCut")
        print("and is NOT an error: these fonts COME WITH CapCut. They live in CapCut's cloud and only save")
        print("to your computer the first time you actually use one. Until then your reels use a clean")
        print("stand-in font, so nothing is blocked. Getting the real font ready is a one-time, one-minute")
        print("thing you do once and never again:")
        # Only between builds. The engine has no reliable signal that a build still has writes left, and
        # anything written while CapCut is open is lost on CapCut's next save (a reopened CapCut on Windows
        # has also hung and stayed stuck until a full restart). So the order is always: the build finishes
        # and is handed over, THEN CapCut opens for the font, THEN CapCut is quit and she says go.
        print("  0. If I am in the middle of building a reel for you, let me finish and hand it over first.")
        print("     CapCut has to stay closed while I write, so open it for a font only between builds.")
        print("  1. Open CapCut and start a new project (any blank one).")
        print("  2. Add a text box and type a few words.")
        print("  3. In the font list, pick the font(s) below so it's applied to your text — that is what")
        print("     pulls it down from the cloud onto your computer:")
        for pk, role, name, fil in any_missing:
            nm = name or fil
            print(f"        • {nm}{capcut_search_hint(name)}")
        print(f"  4. Quit CapCut fully ({_QUIT_HINT}), then tell me to go. The next build finds the font")
        print("     automatically. (Re-run this anytime to confirm: python3 product/capcut_font_doctor.py)")
        print("")
        print("  Already have the font file on your computer? Point me at it instead and skip the above:")
        for pk, role, name, fil in any_missing:
            nm = name or fil
            print(f"     python3 product/capcut_font_doctor.py --map \"{nm}=/full/path/to/the/font.otf\"")
        return 0   # a one-time setup step, not a failure — never let this read as an error to a new user
    print("\n✓ every pack font resolves — you're good to build.")
    return 0


def do_map(pairs):
    overrides = load_overrides()
    for pair in pairs:
        if "=" not in pair:
            sys.exit(f"font-doctor: --map needs \"Name=/path/to/font\", got: {pair}")
        name, path = pair.split("=", 1)
        name, path = name.strip(), os.path.expanduser(path.strip())
        if not os.path.isfile(path):
            sys.exit(f"font-doctor: no file at {path} (check the path).")
        if os.path.splitext(path)[1].lower() not in (".ttf", ".otf", ".ttc"):
            print(f"  ! warning: {path} is not a .ttf/.otf/.ttc — mapping it anyway")
        overrides[name.strip().lower()] = path
        print(f"  ✓ mapped \"{name}\" → {path}")
    save_overrides(overrides)
    print(f"saved to {OVERRIDES} — the engine will use this on every build.")


def do_unmap(names):
    overrides = load_overrides()
    for name in names:
        if overrides.pop(name.strip().lower(), None) is not None:
            print(f"  ✓ removed hand-map for \"{name}\"")
        else:
            print(f"  (no hand-map for \"{name}\")")
    save_overrides(overrides)


def main():
    ap = argparse.ArgumentParser(description="Check + hand-map style-pack fonts against your CapCut.")
    ap.add_argument("pack", nargs="*", help="pack name(s) to check (default: all)")
    ap.add_argument("--map", action="append", default=[], metavar='"Name=/path"',
                    help="hand-map a font name to a file on disk (repeatable)")
    ap.add_argument("--unmap", action="append", default=[], metavar='"Name"',
                    help="remove a hand-map (repeatable)")
    a = ap.parse_args()
    if a.map:
        do_map(a.map)
    if a.unmap:
        do_unmap(a.unmap)
    if a.map or a.unmap:
        print()
    sys.exit(check(a.pack or None))


if __name__ == "__main__":
    main()
