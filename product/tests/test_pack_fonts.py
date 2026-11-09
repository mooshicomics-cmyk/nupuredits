#!/usr/bin/env python3
"""A pack font resolves to a real FONT FILE, or the engine says plainly that it could not.

Two ways this went quietly wrong:
  1. A pack built by /studio recipe leaves each element's `file` blank, so the font resolves by name at build
     time. Joined onto assets/fonts, the blank came back as the fonts FOLDER, which exists, so neither the name
     lookup nor the fallback ever ran: the CapCut lane was handed a directory as its font, the baked lane an
     @font-face for a file that was never copied, and the reel rendered in a default typeface with no word said.
  2. A shipped pack font that is not on a buyer's machine falls back to a bundled stand-in. It has to: failing
     would stop every Editorial, Butter and Playful build for a buyer who has not added those faces in CapCut
     yet. But the message said "(nothing is broken)", and the stand-in is not part of the pack.

Runs in a throwaway engine skeleton holding only the fonts that ship, with its own HOME, so neither this
engine's licensed fonts nor any real CapCut on this machine is read.

Run: python3 product/tests/test_pack_fonts.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
# the licensed faces make-ship.sh leaves out of every bundle
NOT_SHIPPED = {"Prosecco.ttf", "ProseccoandBaguette.ttf", "HFOperaCake.ttf", "Geomanist-Regular.otf",
               "SoupDuJour.ttf", "SoupDuJourHollow.ttf", "Bloop.ttf", "UglyDaveAlternates.otf",
               "Advercase-Bold.otf", "Advercase-Regular.otf", "Helvetica Medium.ttf"}

CHILD = r"""
import contextlib, io, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "product"))
import stylepack
def safe_abs(v):
    try:
        return stylepack._abs(v)
    except Exception as exc:
        return f"raised {type(exc).__name__}"
out = {"abs_blank": safe_abs(""), "abs_none": safe_abs(None), "elements": {}}
for pk in stylepack.names():
    for kind in stylepack.load(pk)["elements"]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            e = stylepack.element(pk, kind)
        out["elements"][f"{pk}/{kind}"] = {"file": e["file"], "isfile": os.path.isfile(e["file"]),
                                           "isdir": os.path.isdir(e["file"]), "fallback": bool(e.get("fallback")),
                                           "requested": e.get("requested_font"), "printed": buf.getvalue()}
with contextlib.redirect_stdout(io.StringIO()):
    out["notes"] = {pk: stylepack.delivery_font_note(pk) for pk in stylepack.names()}
print(json.dumps(out))
"""

fails = []


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def main():
    tmp = tempfile.mkdtemp()
    try:
        eng, home = os.path.join(tmp, "engine"), os.path.join(tmp, "home")
        os.makedirs(os.path.join(eng, "product", "creative-vault"))
        os.makedirs(os.path.join(eng, "assets", "fonts"))
        os.makedirs(home)
        for fn in ("stylepack.py", "capcut_userfonts.py", "capcut_font_doctor.py"):
            shutil.copy2(os.path.join(PRODUCT, fn), os.path.join(eng, "product", fn))
        src_fonts = os.path.join(ROOT, "assets", "fonts")
        for fn in os.listdir(src_fonts):
            if fn not in NOT_SHIPPED:
                shutil.copy2(os.path.join(src_fonts, fn), os.path.join(eng, "assets", "fonts", fn))
        # her own font, hand-mapped with capcut_font_doctor --map, is the one a blank file must still find by name
        mine = os.path.join(tmp, "my-fonts", "MyBrand.ttf")
        os.makedirs(os.path.dirname(mine))
        shutil.copy2(os.path.join(src_fonts, "Poppins-Regular.ttf"), mine)
        with open(os.path.join(eng, "product", "creative-vault", "font-overrides.json"), "w", encoding="utf-8") as fh:
            json.dump({"my brand font": mine}, fh)
        with open(os.path.join(PRODUCT, "creative-vault", "style-packs.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        shipped = [k for k, v in cfg["packs"].items() if v.get("in_launch_kit")]
        # two packs as /studio recipe writes them: every element's file blank, resolved by name at build time
        for name, fonts in (("Sunrise", ("Clash Display", "Inter", "Caveat")),
                            ("Mapped", ("My Brand Font", "My Brand Font", "My Brand Font"))):
            block = json.loads(json.dumps(cfg["packs"]["Editorial"]))
            role = {"headline": fonts[0], "takeover": fonts[0], "caption": fonts[1],
                    "thought_bubble": fonts[2], "accent_caption": fonts[2]}
            for kind, el in block["elements"].items():
                el["font"], el["file"] = role[kind], ""
                el.pop("fallback_file", None)
            block["in_launch_kit"] = False
            cfg["packs"][name] = block
        with open(os.path.join(eng, "product", "creative-vault", "style-packs.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)

        r = subprocess.run([sys.executable, "-c", CHILD, eng], capture_output=True, text=True, cwd=eng,
                           env={**os.environ, "HOME": home, "PYTHONUTF8": "1"})
        if r.returncode != 0:
            check("the pack layer runs on a buyer-like install", False, (r.stdout + r.stderr)[-800:])
            return
        out = json.loads(r.stdout)
        els = out["elements"]

        check("a blank font file resolves to no path, never the fonts folder", out["abs_blank"] == "",
              repr(out["abs_blank"]))
        check("a missing font file resolves to no path", out["abs_none"] == "", repr(out["abs_none"]))
        not_files = [k for k, e in els.items() if not e["isfile"] or e["isdir"]]
        check("every element of every pack resolves to a real font FILE on a buyer machine", not not_files,
              ", ".join(not_files))
        check("a blank-file pack's fonts are looked for, then stood in for (not silently skipped)",
              all(els[f"Sunrise/{k}"]["fallback"] for k in cfg["packs"]["Sunrise"]["elements"]))
        check("a blank-file font she hand-mapped is found by NAME, with no stand-in and no message",
              all(not els[f"Mapped/{k}"]["fallback"] and els[f"Mapped/{k}"]["file"] == mine
                  and not els[f"Mapped/{k}"]["printed"] for k in cfg["packs"]["Mapped"]["elements"]),
              json.dumps({k: v["file"] for k, v in els.items() if k.startswith("Mapped/")}))
        fell = {k: e for k, e in els.items() if e["fallback"]}
        check("the shipped packs lean on the stand-ins here, as on a fresh buyer machine",
              any(k.split("/")[0] in shipped for k in fell), sorted(fell))
        for k, e in fell.items():
            msg = e["printed"]
            check(f"{k}: the stand-in is announced", bool(msg.strip()), "nothing printed")
            check(f"{k}: the message names the missing pack font", (e["requested"] or "") in msg, msg)
            check(f"{k}: the message says the stand-in is not the pack's look", "not part of the pack" in msg, msg)
            check(f"{k}: the message never calls it fine", "nothing is broken" not in msg.lower(), msg)
        how = "\n".join(e["printed"] for e in els.values())
        for pk, font in (("Editorial", "Prosecco and Baguette"), ("Playful", "Soup Du Jour"), ("Butter", "Bloop")):
            n = how.count(f"add '{font}' in CapCut once")
            check(f"how to add {font} is said once for {pk}, not once per element", n == 1, f"said {n} times")
        check("a paid face is named as coming with CapCut Pro", "comes with CapCut Pro" in how)
        check("CapCut's own listing name is given where it differs (Soup Du Jour is listed as Solid)",
              "search 'solid'" in how.lower())
        note = out["notes"].get("Sunrise") or ""
        check("the delivery note names a blank-file pack's missing fonts instead of saying nothing",
              "Clash Display" in note, repr(note))
        check("the delivery note makes no free-or-Pro claim about a font it does not know",
              "Clash Display** is free" not in note and "Clash Display** comes with" not in note, note)
        check("the shipped delivery note is unchanged for a paid face",
              "comes with CapCut Pro" in (out["notes"].get("Editorial") or ""), repr(out["notes"].get("Editorial")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    if fails:
        print(f"pack fonts: FAILED {len(fails)}: {'; '.join(fails)}")
        sys.exit(1)
    print("pack fonts: a pack font always resolves to a real file, and a stand-in is always named as one")
