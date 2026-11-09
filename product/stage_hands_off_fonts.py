#!/usr/bin/env python3
"""Stage the Hands-Off templates' restricted display fonts from the buyer's OWN CapCut, at render time.

WHY THIS EXISTS
The Hands-Off lane renders a finished MP4 in HyperFrames (a headless browser), so its frame templates
(product/creative-vault/hands-off/<pack>/index.html) load fonts via relative @font-face, e.g.
    @font-face{font-family:Soup;src:url('soup.ttf');}
Those display fonts (Soup Du Jour, Ugly Dave, Prosecco) are LICENSED and are NOT shipped — exactly like
the rest of the engine, which never distributes a licensed font and instead resolves it from the buyer's
CapCut (CapCut Pro carries them). This helper closes that loop for the Hands-Off render: it resolves each
restricted font BY NAME from CapCut's userFontData (via capcut_userfonts.py) and copies the file into the
pack's Hands-Off dir under the exact filename the template's @font-face expects. The template is untouched;
only the file appears, sourced from the buyer's machine.

Free/OFL fonts the templates also use (Noto, Playfair, Poppins, Inter) DO ship and need no staging.

USAGE
    python3 product/stage_hands_off_fonts.py                 # stage every pack that has restricted fonts
    python3 product/stage_hands_off_fonts.py playful         # just one pack
Run it once before a Hands-Off render. Idempotent: a font already present is left alone. If a restricted
font isn't in the buyer's CapCut, it's reported (they add it in CapCut Pro once, then re-run) — the render
would otherwise fall back to a system serif for that face.

Returns exit 0 when every restricted font for the requested pack(s) is present, 2 if any is still missing.
"""
import os, sys, shutil, importlib.util
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HANDS_OFF = os.path.join(ROOT, "product", "creative-vault", "hands-off")

# The template @font-face family names ("Soup", "Ugly") are short handles, NOT the CapCut font names.
# This maps each pack's expected co-located FILE -> the CapCut font NAME(s) to resolve it by (first that
# the buyer's CapCut has, wins — CapCut records vary, e.g. "Prosecco" vs "Prosecco and Baguette").
# (Only restricted/licensed faces are listed; OFL faces like noto.ttf ship and are not staged.)
RESTRICTED = {
    "editorial": {"prosecco.ttf": ["Prosecco and Baguette", "Prosecco"]},
    "playful":   {"soup.ttf": ["Soup Du Jour", "Soup"], "uglydave.otf": ["Ugly Dave", "UglyDave"]},
    # butter uses only OFL faces (Inter) — nothing to stage.
}


def _load_resolver():
    cu = os.path.join(HERE, "capcut_userfonts.py")
    if not os.path.isfile(cu):
        sys.exit(f"stage-hands-off-fonts: missing {cu} (the CapCut font resolver).")
    spec = importlib.util.spec_from_file_location("capcut_userfonts", cu)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.resolve_font_file


def stage(packs=None):
    resolve = _load_resolver()
    want = packs or list(RESTRICTED.keys())
    missing = []
    staged = 0
    present = 0
    unknown = [p for p in want if not RESTRICTED.get(p.lower())]
    if unknown:
        print(f"  ⛔ unknown pack(s) {unknown} — nothing staged. Known packs: {sorted(RESTRICTED)}")
        return 2
    for pack in want:
        files = RESTRICTED.get(pack.lower())
        if not files:
            continue
        pdir = os.path.join(HANDS_OFF, pack.lower())
        if not os.path.isdir(pdir):
            print(f"  ! no Hands-Off dir for pack '{pack}' ({pdir}) — skipping")
            continue
        for fname, capcut_names in files.items():
            dest = os.path.join(pdir, fname)
            if os.path.isfile(dest):
                present += 1
                continue
            names = capcut_names if isinstance(capcut_names, (list, tuple)) else [capcut_names]
            src, hit_name = None, names[0]
            for nm in names:                       # first name the buyer's CapCut actually has, wins
                p = resolve(nm, None)
                if p and os.path.isfile(p):
                    src, hit_name = p, nm
                    break
            if src:
                shutil.copyfile(src, dest)
                staged += 1
                print(f"  ✓ staged {pack}/{fname}  <-  \"{hit_name}\" (from your CapCut)")
            else:
                missing.append((pack, fname, names[0]))
    if missing:
        print("\n  ⚠ these restricted fonts are not in your CapCut yet:")
        for pack, fname, capcut_name in missing:
            print(f"      {pack}: \"{capcut_name}\"  (needed as {fname})")
        print("  Add each one in CapCut once (CapCut Pro carries them), then re-run. Until then the")
        print("  Hands-Off render for that pack falls back to a system serif for that face.")
    print(f"\nhands-off fonts: {staged} staged, {present} already present, {len(missing)} missing")
    return 2 if missing else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(stage(args or None))
