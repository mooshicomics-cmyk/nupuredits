#!/usr/bin/env python3
"""A pack font always resolves to the face whose own name table matches it, never to another face that shares
a file name or a family name.

  catalog   CapCut's in-app catalog caches every font it downloads as font.ttf / font.otf under an opaque id.
            Each name must resolve to the cached file whose REAL family matches, and the cache is read from
            ~/Movies (both Mac installs; the App Store sandbox's Movies folder is a link to it), under whatever
            HOME the build runs with. A name nothing matches stays unresolved so the pack's stand-in is used.
  copies    the CapCut lane copies each pack face into CapCut's font folder named by its family. Two cuts of
            one family (Soup Du Jour solid and hollow, Inter Bold and Inter Regular) used to share that name,
            so whichever got there first was handed back for the other: a hollow takeover drew in the solid
            face. A copy already there is reused only when it is the same face.

Only the bundled OFL fonts are used, plus the Soup Du Jour pair when this machine has it. HOME is a temp
folder for the whole run, so nothing in this machine's CapCut is read or written.

Run: python3 product/tests/test_capcut_font_match.py
"""
import os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
FONTS = os.path.join(ROOT, "assets", "fonts")

BASE = tempfile.mkdtemp(prefix="capcut-font-match-")
HOME = os.path.join(BASE, "home")
os.makedirs(HOME)
os.environ["HOME"] = HOME                      # before the resolver is imported: its folders are set at import
os.environ["USERPROFILE"] = HOME
os.environ["LOCALAPPDATA"] = os.path.join(HOME, "AppData", "Local")
sys.path.insert(0, PRODUCT)

from PIL import ImageFont                      # noqa: E402
import capcut_userfonts as cu                  # noqa: E402
import packbuild as pb                         # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def face(p):
    try:
        return ImageFont.truetype(p, 40).getname()
    except Exception:
        return None


def main():
    try:
        # ---- catalog: two cached files, both literally font.ttf, two different families ------------------
        if os.name != "nt":
            check("the catalog cache is read under the HOME the build runs with",
                  os.path.abspath(cu._CATALOG).startswith(os.path.abspath(HOME)), cu._CATALOG)
            # the App Store layout: the sandbox's Movies folder is a link to ~/Movies
            sandbox = os.path.join(HOME, "Library", "Containers", "com.lemon.lvoverseas", "Data")
            os.makedirs(sandbox)
            os.symlink(os.path.join("..", "..", "..", "..", "Movies"), os.path.join(sandbox, "Movies"))
        for rid, name in (("7101", "Poppins-Regular.ttf"), ("7102", "PlayfairDisplay-VF.ttf"),
                          ("7103", "NotoSansAdlam.ttf")):
            d = os.path.join(cu._CATALOG, rid, "h")
            os.makedirs(d)
            shutil.copy(os.path.join(FONTS, name), os.path.join(d, "font.ttf"))
        for fam in ("Poppins", "Playfair Display", "Noto Sans Adlam"):
            got = cu.resolve_font_file(fam, None)
            check(f"catalog: '{fam}' resolves to the cached font.ttf whose own family is {fam}",
                  got and (face(got) or ("",))[0] == fam, (got, face(got) if got else None))
        check("catalog: three cached font.ttf files give three different paths",
              len({cu.resolve_font_file(f, None) for f in ("Poppins", "Playfair Display", "Noto Sans Adlam")}) == 3)
        check("catalog: a name nothing in the cache carries stays unresolved (the pack's stand-in is used)",
              cu.resolve_font_file("Ugly Dave", None) is None, cu.resolve_font_file("Ugly Dave", None))
        bundled = os.path.join(FONTS, "Inter-Bold.otf")
        check("catalog: a bundled file still wins over the cache", cu.resolve_font_file("Poppins", bundled) == bundled)

        # ---- cut: a role that names its file gets that cut from CapCut's copies, not the preferred one ------
        log = os.path.join(BASE, "local")
        os.environ["REELS_ENGINE_LOCAL"] = log            # the fallbacks log goes here, never the real _local
        cu._catalog_cache = None
        for rid, name in (("7201", "Poppins-Bold.ttf"), ("7202", "Poppins-SemiBold.ttf")):
            d = os.path.join(cu._CATALOG, rid, "h"); os.makedirs(d)
            shutil.copy(os.path.join(FONTS, name), os.path.join(d, "font.ttf"))
        cu._PREFERRED_SUBFAMILY["poppins"] = "regular"     # stands in for Soup Du Jour's "prefer solid"
        missing = lambda n: os.path.join(BASE, "not-bundled", n)
        for n, sub in (("Poppins-Bold.ttf", "Bold"), ("Poppins-SemiBold.ttf", "SemiBold"),
                       ("Poppins-Regular.ttf", "Regular")):
            got = cu.resolve_font_file("Poppins", missing(n))
            check(f"cut: {n} missing here resolves to CapCut's {sub} cut", face(got) == ("Poppins", sub), (got, face(got)))
        check("cut: with no cut asked for, the preferred cut still wins",
              face(cu.resolve_font_file("Poppins", None)) == ("Poppins", "Regular"))
        check("cut: nothing was noted while every asked-for cut was there", not os.path.exists(log))
        import io, contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = cu.resolve_font_file("Poppins", missing("Poppins-Black.ttf"))
            cu.resolve_font_file("Poppins", missing("Poppins-Black.ttf"))
        check("cut: an asked-for cut that is not there falls back to the preferred one",
              face(got) == ("Poppins", "Regular"), face(got))
        said = [l for l in err.getvalue().splitlines() if l.strip()]
        check("cut: the fallback is said in one plain line, once", len(said) == 1 and "Poppins-Black" in said[0]
              and "⚠" not in said[0], said)
        logged = open(os.path.join(log, "fallbacks.log"), encoding="utf-8").read() if os.path.exists(
            os.path.join(log, "fallbacks.log")) else ""
        check("cut: the fallback is noted in the fallbacks log", "Poppins-Black" in logged, logged)
        libdir = cu._LIBFON
        os.makedirs(libdir, exist_ok=True)
        shutil.copy(os.path.join(FONTS, "Poppins-Bold.ttf"), os.path.join(libdir, "Poppins.ttf"))
        got = cu.resolve_font_file("Poppins", missing("Poppins-SemiBold.ttf"))
        check("cut: a by-name copy in CapCut's font folder in another cut is passed over for the right one",
              face(got) == ("Poppins", "SemiBold"), (got, face(got)))
        check("cut: a by-name copy in the asked-for cut is still used first",
              cu.resolve_font_file("Poppins", missing("Poppins-Bold.ttf")) == os.path.join(libdir, "Poppins.ttf"))
        os.remove(os.path.join(libdir, "Poppins.ttf"))
        check("cut: the pack's own file names say their cut",
              (cu.wanted_cut("SoupDuJourHollow.ttf"), cu.wanted_cut("SoupDuJour.ttf"),
               cu.wanted_cut("Inter-SemiBold.ttf"), cu.wanted_cut("PlayfairDisplay-VF.ttf"), cu.wanted_cut(""))
              == ("regular", "solid", "semibold", None, None))
        sj, sjh = os.path.join(FONTS, "SoupDuJour.ttf"), os.path.join(FONTS, "SoupDuJourHollow.ttf")
        if os.path.exists(sj) and os.path.exists(sjh):     # the paid pair is only on the creator's machine
            cu._catalog_cache = None
            for rid, src in (("7301", sj), ("7302", sjh)):   # the solid sorts first, as CapCut's ids might
                d = os.path.join(cu._CATALOG, rid, "h"); os.makedirs(d)
                shutil.copy(src, os.path.join(d, "font.ttf"))
            got = cu.resolve_font_file("Soup Du Jour", missing("SoupDuJourHollow.ttf"))
            check("cut: a hollow takeover on a buyer machine gets CapCut's hollow Soup Du Jour",
                  face(got) == ("Soup Du Jour", "Regular"), (got, face(got)))
            got = cu.resolve_font_file("Soup Du Jour", missing("SoupDuJour.ttf"))
            check("cut: the solid headline still gets the solid one", face(got) == ("Soup Du Jour", "Solid"), face(got))

        # ---- same_face: family AND subfamily ---------------------------------------------------------------
        reg, bold = os.path.join(FONTS, "Poppins-Regular.ttf"), os.path.join(FONTS, "Poppins-Bold.ttf")
        check("same_face: two cuts of one family are different faces", not cu.same_face(reg, bold))
        twin = os.path.join(BASE, "twin.ttf"); shutil.copy(reg, twin)
        check("same_face: a copy of a face is the same face", cu.same_face(reg, twin))
        check("same_face: a missing file is never the same face", not cu.same_face(reg, os.path.join(BASE, "nope.ttf")))

        # ---- copies into CapCut's font folder ---------------------------------------------------------------
        lib = os.path.join(BASE, "capcut-fonts"); os.makedirs(lib)
        pb.CAPCUT_FONTS = lib
        first = pb.capcut_font_path(reg)
        check("copy: the first cut lands under its family name", os.path.basename(first) == "Poppins.ttf", first)
        before = sorted(os.listdir(lib))
        dst, need = pb._capcut_font_dest(bold)
        check("copy: working out where a face goes writes nothing", sorted(os.listdir(lib)) == before)
        check("copy: a second cut of the family is not handed the first cut's file", dst != first and need, (dst, need))
        got = pb.capcut_font_path(bold)
        check("copy: the second cut's path holds the second cut", face(got) == ("Poppins", "Bold"), (got, face(got)))
        check("copy: the first cut's file is left as it was", face(first) == ("Poppins", "Regular"), face(first))
        check("copy: asking again for each cut gives the same path, nothing new copied",
              pb.capcut_font_path(bold) == got and pb.capcut_font_path(reg) == first and len(os.listdir(lib)) == 2,
              sorted(os.listdir(lib)))
        for a, b in (("Inter-Regular.otf", "Inter-Bold.otf"), ("SoupDuJour.ttf", "SoupDuJourHollow.ttf")):
            pa, pbb = os.path.join(FONTS, a), os.path.join(FONTS, b)
            if not (os.path.exists(pa) and os.path.exists(pbb)):
                continue                              # the paid pair is only on the creator's machine
            ga, gb = pb.capcut_font_path(pa), pb.capcut_font_path(pbb)
            check(f"copy: {a} and {b} each get a file of their own face",
                  ga != gb and face(ga) == face(pa) and face(gb) == face(pbb), (ga, face(ga), gb, face(gb)))
        check("copy: a font file that is not there keeps the old answer (nothing copied, no error)",
              os.path.basename(pb.capcut_font_path(os.path.join(BASE, "Missing.ttf"))) == "Missing.ttf")
    finally:
        shutil.rmtree(BASE, ignore_errors=True)

    if fails:
        print(f"test_capcut_font_match: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_capcut_font_match: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
