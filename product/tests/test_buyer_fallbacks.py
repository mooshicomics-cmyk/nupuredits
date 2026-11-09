#!/usr/bin/env python3
"""Regression guard: a BUYER must always get a finished reel, never a dead build or a wrong-looking one.

Two silent failures this locks down:
  1. FONTS — the paid faces (script/display/handwritten) live in CapCut and do NOT ship as files. The CapCut
     lanes are fine (CapCut draws the text), but the BAKED lane renders in a headless browser that needs a
     real file. With none, @font-face fell through to a browser default: the reel rendered in the WRONG
     typeface and nothing errored. Every pack must now fall back to a bundled face.
  2. SFX — the creator's sfx/ folder ships EMPTY (CapCut sounds are not redistributable). A named cue used
     to raise SystemExit and kill the whole build. Cues must now resolve to the bundled Pixabay library that
     already ships with the vendored HyperFrames toolkit, and a truly missing cue must be skipped, not fatal.

And one invariant it enforces (the opposite of a silent fallback):
  3. NO PERSONAL-FONT DEFAULT — the shipped builders resolve fonts from the chosen style pack and RAISE when
     no pack is chosen; they never quietly default to a personal font. Falling a paid PACK face back to a
     bundled OFL substitute in the baked lane (check 1) is fine; defaulting to a personal font is not.

Run: python3 product/tests/test_buyer_fallbacks.py
"""
import os, sys, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import stylepack, capcut_sfx

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def shipped_fonts_only():
    """A fonts dir holding ONLY the OFL faces that actually ship (no CapCut-only paid faces)."""
    tmp = tempfile.mkdtemp()
    os.makedirs(f"{tmp}/assets/fonts")
    src = os.path.join(ROOT, "assets", "fonts")
    excluded = {"Prosecco.ttf", "ProseccoandBaguette.ttf", "HFOperaCake.ttf", "Geomanist-Regular.otf",
                "SoupDuJour.ttf", "SoupDuJourHollow.ttf", "Bloop.ttf", "UglyDaveAlternates.otf"}
    for f in os.listdir(src):
        if f not in excluded:
            shutil.copy(os.path.join(src, f), f"{tmp}/assets/fonts/{f}")
    return tmp


def main():
    print("buyer fallbacks\n")

    # ---- fonts ----
    real_root, tmp = stylepack.ROOT, shipped_fonts_only()
    stylepack.ROOT = tmp
    try:
        unresolved, fellback = [], 0
        for pk in stylepack.names():
            for kind in stylepack.load(pk)["elements"]:
                e = stylepack.element(pk, kind)
                if e.get("fallback"):
                    fellback += 1
                if not os.path.exists(e["file"]):
                    unresolved.append(f"{pk}/{kind}")
        check("every pack element resolves to a real font file on a buyer machine",
              not unresolved, f"unresolved: {unresolved}")
        # A pack face that isn't present degrades to a bundled substitute in the baked lane — that is FINE,
        # not required. On a machine whose CapCut already carries the paid faces nothing needs to fall back
        # (fellback == 0), which is not a defect. The ship-critical invariant is the resolve check above.
        print(f"  INFO  {fellback} pack element(s) degraded to a bundled substitute "
              f"(0 is fine when CapCut already has the faces)")
    finally:
        stylepack.ROOT = real_root
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- fonts: NO personal-font default (fail loud, never guess) ----
    # The shipped builders resolve every font from the CHOSEN pack and must never fall back to a personal
    # font (Advercase / Ugly Dave / ZY-Modern). Source scan (no heavy imports): no builder may reference a
    # purely-personal font at all (Advercase / ZY-Modern); only cleanyap.py keeps ONE fenced Ugly Dave marker
    # (thought-bubble line-spacing, never a default).
    import re
    _AZ = re.compile(r"Advercase|ZY[-_ ]?Modern")
    _ALL = re.compile(r"Advercase|UglyDave|Ugly Dave|ZY[-_ ]?Modern")
    for fn in ("superyap.py", "build-hf-captions.py", "build-captions.py"):
        src = open(os.path.join(PRODUCT, fn), encoding="utf-8").read()
        check(f"{fn} has no personal-font reference", not _ALL.search(src),
              f"found: {sorted(set(_ALL.findall(src)))}")
    _cy = open(os.path.join(PRODUCT, "cleanyap.py"), encoding="utf-8").read()
    check("cleanyap.py has no Advercase / ZY-Modern reference", not _AZ.search(_cy),
          f"found: {sorted(set(_AZ.findall(_cy)))}")
    # Behavioural fail-loud check (only when the builder is importable — it pulls in optional runtime deps
    # like `requests` that a bare test env may lack; the source scan above is the ship-blocking guarantee).
    try:
        import cleanyap as _cmod
    except Exception as _e:
        print(f"  SKIP  cleanyap fail-loud check (module not importable here: {type(_e).__name__})")
        _cmod = None
    if _cmod is not None:
        _real_default = _cmod.default_pack
        _cmod.default_pack = lambda: None           # simulate a buyer who has not chosen a pack yet
        try:
            for fn in ("hook_font", "thought_font"):
                try:
                    getattr(_cmod, fn)(None)
                    check(f"cleanyap.{fn}() with no pack RAISES (no personal-font default)", False, "did not raise")
                except ValueError:
                    check(f"cleanyap.{fn}() with no pack RAISES (no personal-font default)", True)
        finally:
            _cmod.default_pack = _real_default

    # ---- sfx ----
    real_dir, empty = capcut_sfx.SFX_DIR, tempfile.mkdtemp()
    capcut_sfx.SFX_DIR = empty
    try:
        pal = capcut_sfx.palette()
        check("a buyer with an EMPTY sfx folder still has cues", len(pal) > 0, f"got {len(pal)}")
        # Cues the sound pass falls back on with no Epidemic connector. Keep this list to sounds the
        # index has ENABLED: a cue switched off (a duplicate, say) is meant not to resolve, and naming
        # one here tests the old library rather than the current one.
        for cue in ("woosh", "decision_click", "cute_pop", "pop", "keyboard_typing"):
            check(f"cue '{cue}' resolves", cue in pal and os.path.exists(pal[cue]))

        # a genuinely unknown cue must be SKIPPED, never fatal
        d = {"materials": {"audios": []}, "tracks": []}
        draft = tempfile.mkdtemp()
        try:
            n = capcut_sfx.add_sfx(d, draft, [("definitely_not_a_real_sound", 1.0, 0.3, None)])
            check("an unknown cue is skipped, build survives", n == 0)
        except SystemExit as e:
            check("an unknown cue is skipped, build survives", False, f"SystemExit: {e}")
        finally:
            shutil.rmtree(draft, ignore_errors=True)
    finally:
        capcut_sfx.SFX_DIR = real_dir
        shutil.rmtree(empty, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED: {len(fails)} — {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
