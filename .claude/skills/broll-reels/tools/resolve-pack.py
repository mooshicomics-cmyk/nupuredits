#!/usr/bin/env python3
"""Resolve an Edit Engine STYLE PACK -> baker fonts + color, from the engine's own style-packs.json.

This is what makes B-Roll Reels a native Edit Engine feature: it reuses the SAME pack definitions the
rest of the engine uses (product/creative-vault/style-packs.json). No fonts or pack data live in this
skill. Given a pack name, it prints shell-eval-able exports for build-all.sh:

  eval "$(python3 resolve-pack.py Playful)"   # sets HEADLINE_FONT / ACCENT_FONT / TEXT_COLOR
  python3 resolve-pack.py --list              # list available packs

Font resolution mirrors the engine: a pack font file resolves under font_dir (assets/fonts); a
system font resolves via system_fonts. Restricted display fonts are excluded from ship on purpose
(the engine resolves them from the buyer's own CapCut cache) — if the file is absent, the path is
still emitted and the baker errors clearly, same model as the rest of the engine.
"""
import argparse, json, os, sys, shlex

HERE = os.path.dirname(os.path.abspath(__file__))


def repo_root():
    d = HERE
    for _ in range(8):
        if os.path.isfile(os.path.join(d, "product", "creative-vault", "style-packs.json")):
            return d
        d = os.path.dirname(d)
    sys.exit("resolve-pack: could not locate product/creative-vault/style-packs.json above this skill "
             "(is broll-reels installed inside the Edit Engine?)")


def load(root):
    with open(os.path.join(root, "product", "creative-vault", "style-packs.json")) as f:
        return json.load(f)


def _capcut_resolve(root, name, bundled):
    """Bundled file if it exists; else resolve the font by NAME from the buyer's OWN CapCut fonts, exactly
    like the rest of the engine (product/capcut_userfonts.py reads CapCut's userFontData). This is what
    lets a restricted pack font the buyer added in CapCut (Soup Du Jour, Prosecco, Bloop, ...) reach the
    Pillow baker without shipping the file. Returns a real path or None."""
    if bundled and os.path.isfile(bundled):
        return bundled
    if not name:
        return None
    try:
        import importlib.util
        cu = os.path.join(root, "product", "capcut_userfonts.py")
        if not os.path.isfile(cu):
            return None
        s = importlib.util.spec_from_file_location("capcut_userfonts", cu)
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        return m.resolve_font_file(name, bundled)
    except Exception:
        return None


def resolve_font(root, spec, file_field, name_field, elements_key, spec_name_key):
    """Return an absolute font path for a pack: an explicit *_font_file or elements.<key>.file if present,
    else the buyer's CapCut font by NAME (engine-wide model), else a system font, else the expected path
    so the baker errors clearly (buyer installs it in CapCut / drops it in assets/fonts). `spec` is the pack."""
    font_dir = os.path.join(root, spec_cfg_font_dir)
    system = spec_cfg_system_fonts
    # candidate bundled file (explicit *_font_file, then elements.<key>.file)
    fname = spec.get(file_field)
    if not fname:
        el = (spec.get("elements") or {}).get(elements_key) or {}
        fname = el.get("file")
    candidate = os.path.join(font_dir, fname) if fname else None
    nm = spec.get(name_field) or (spec.get("fonts") or {}).get(spec_name_key)
    # 1) bundled file if present, else the buyer's CapCut font by name (same resolver as the rest of the engine)
    resolved = _capcut_resolve(root, nm, candidate)
    if resolved:
        return resolved
    # 2) system font by name (e.g. "Helvetica Neue")
    if nm and nm in system:
        return system[nm]
    # 3) emit the expected path (if any) so the baker errors with a clear, actionable message
    return candidate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack", nargs="?", help="style pack name (run --list for the packs the engine defines)")
    ap.add_argument("--list", action="store_true", help="list available packs and exit")
    a = ap.parse_args()

    root = repo_root()
    cfg = load(root)
    packs = cfg.get("packs", {})

    global spec_cfg_font_dir, spec_cfg_system_fonts
    spec_cfg_font_dir = cfg.get("font_dir", "assets/fonts")
    spec_cfg_system_fonts = cfg.get("system_fonts", {})

    if a.list or not a.pack:
        # Flag packs whose fonts are restricted (they resolve from the buyer's CapCut, which requires
        # CapCut Pro) so the buyer knows before they pick — OFL packs need nothing extra.
        # Bloop is intentionally NOT here: it is FREE in CapCut (available on the free plan), so the
        # Butter pack — whose only accent font is Bloop — must never be labeled "CapCut Pro required".
        # Butter is the free pack; that is the whole point of it.
        LICENSED = ("prosecco", "soup", "uglydave", "ugly dave", "handscript", "hand script",
                    "zy-modern", "zy modern", "advercase", "displayserif", "opera cake", "operacake", "geomanist")
        def needs_pro(spec):
            blobs = []
            for el in (spec.get("elements") or {}).values():
                if isinstance(el, dict) and el.get("file"):
                    blobs.append(el["file"])
            for k in ("headline_font_file", "subhead_font_file", "karaoke_font_file",
                      "headline_font_name", "subhead_font_name", "karaoke_font_name"):
                if spec.get(k):
                    blobs.append(str(spec[k]))
            for v in (spec.get("fonts") or {}).values():
                blobs.append(str(v))
            t = " ".join(blobs).lower()
            return any(s in t for s in LICENSED)
        labeled = [(f"{k} (CapCut Pro required)" if needs_pro(v) else k) for k, v in packs.items()]
        print("available packs: " + ", ".join(labeled), file=sys.stderr)
        if not a.pack:
            sys.exit(0 if a.list else "resolve-pack: pass a pack name (or --list)")
        return

    # case-insensitive match
    key = next((k for k in packs if k.lower() == a.pack.lower()), None)
    if not key:
        sys.exit(f"resolve-pack: unknown pack '{a.pack}'. Available: {', '.join(packs.keys())}")
    spec = packs[key]

    headline = resolve_font(root, spec, "headline_font_file", "headline_font_name", "headline", "main")
    accent = resolve_font(root, spec, "subhead_font_file", "subhead_font_name", "accent_caption", "accent")
    if not headline:
        sys.exit(f"resolve-pack: no headline font resolved for pack '{key}'")
    if not accent:
        accent = headline  # single-font packs reuse the headline face for the turn

    # hook color: flat white is the locked B-Roll look; a pack may state its own hook_color
    color = (spec.get("capcut") or {}).get("hook_color") or "#ffffff"
    if color == "white":
        color = "#ffffff"

    # emit shell exports (safe-quoted)
    print(f"export HEADLINE_FONT={shlex.quote(headline)}")
    print(f"export ACCENT_FONT={shlex.quote(accent)}")
    print(f"export TEXT_COLOR={shlex.quote(color)}")
    print(f"# resolved pack: {key}", file=sys.stderr)
    # warn if a resolved font file is missing (restricted/excluded — buyer resolves via CapCut cache)
    for lbl, p in (("headline", headline), ("accent", accent)):
        if os.sep in p and not os.path.isfile(p):
            print(f"# NOTE: {lbl} font not present: {p} (restricted/excluded font — install it in CapCut "
                  f"or drop it in {spec_cfg_font_dir})", file=sys.stderr)


if __name__ == "__main__":
    main()
