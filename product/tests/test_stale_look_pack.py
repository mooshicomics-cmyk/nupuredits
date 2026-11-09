#!/usr/bin/env python3
"""Guards: a look drawn before her pack changed is drawn again (a buyer, 2026-10-22).

She changed her own pack's karaoke font, and a Swap brought the old font back: the line's drawing was reused because
nothing about the pack's NAME had changed, only what was in it.

  sig        stylepack.signature: the same pack reads the same; an edit to it (a font) reads different; an unknown
             pack is None
  drawn      a look lookbook.draw makes carries its pack's fingerprint in look.json, and reads current
  edited     after an edit to that pack, its drawing is stale; a drawing in another pack is not; drawn again, it is
             current
  older      a drawing from before fingerprints is judged by the pack files' times (older than them = stale)

Run: python3 product/tests/test_stale_look_pack.py
"""
import json, os, shutil, sys, tempfile, time
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import stylepack  # noqa: E402
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="stale-look-pack-")
    prev = os.environ.get("REEL_PREVIEW_PACKS")
    try:
        # her own pack, a copy of a shipped one, seen by this process and the builder it starts (stylepack._data)
        mine = json.loads(json.dumps(stylepack.load("Butter")))
        packs = os.path.join(tmp, "packs.json")
        json.dump({"packs": {"Testpack": mine}}, open(packs, "w", encoding="utf-8"))
        os.environ["REEL_PREVIEW_PACKS"] = packs
        s0 = stylepack.signature("Testpack")
        check("sig: the same pack reads the same", s0 and s0 == stylepack.signature("Testpack"), s0)
        check("sig: an unknown pack has none", stylepack.signature("No Such Pack") is None)

        import lookbook
        out = os.path.join(tmp, "add-w0", "_menu", "takeover")
        lookbook.draw("takeover", out, "this is the line", 2.0, "Testpack")
        page = os.path.join(out, "hf-reel-type-testpack")
        rec = json.load(open(os.path.join(page, "look.json"), encoding="utf-8"))
        check("drawn: the look's record carries its pack's fingerprint", rec.get("pack_sig") == s0, rec.get("pack_sig"))
        check("drawn: a fresh drawing is current", not ve._stale_look(page))
        other = os.path.join(tmp, "add-w1", "_menu", "takeover")
        lookbook.draw("takeover", other, "this is the line", 2.0, "Butter")
        other_page = os.path.join(other, "hf-reel-type-butter")
        check("drawn: a drawing in a shipped pack is current too", not ve._stale_look(other_page))

        # she edits her pack: another caption font (any change to what the pack hands a drawing)
        el = mine.setdefault("elements", {}).setdefault("caption", {})
        el["font"] = str(el.get("font") or "") + " Edited"
        json.dump({"packs": {"Testpack": mine}}, open(packs, "w", encoding="utf-8"))
        check("sig: an edit to the pack reads different", stylepack.signature("Testpack") != s0)
        check("edited: a look drawn before her pack changed is drawn again (the old font never comes back)", ve._stale_look(page))
        check("edited: a look in another pack is left as drawn", not ve._stale_look(other_page))
        el["font"] = el["font"][: -len(" Edited")]               # (put back, so the builder draws a real font again)
        json.dump({"packs": {"Testpack": mine}}, open(packs, "w", encoding="utf-8"))
        s1 = stylepack.signature("Testpack")
        mine["accent_color"] = "#123456"
        json.dump({"packs": {"Testpack": mine}}, open(packs, "w", encoding="utf-8"))
        check("edited: a color change counts too", ve._stale_look(page) and stylepack.signature("Testpack") != s1)
        lookbook.draw("takeover", out, "this is the line", 2.0, "Testpack")
        check("edited: drawn again, it is current", not ve._stale_look(page))

        # a drawing from before fingerprints: judged by the pack files' times
        old = os.path.join(tmp, "old")
        os.makedirs(old)
        open(os.path.join(old, "index.html"), "w", encoding="utf-8").write("<html></html>")
        json.dump({"look": "takeover", "pack": "Butter"}, open(os.path.join(old, "look.json"), "w", encoding="utf-8"))
        newest = max(os.path.getmtime(f) for f in (stylepack.SPEC, stylepack.LOCAL_SPEC, os.path.join(os.path.dirname(HERE), "lookbook.py"),
                                                     os.path.join(os.path.dirname(HERE), "build-reel-type.py")) if os.path.isfile(f))
        os.utime(os.path.join(old, "index.html"), (newest + 60, newest + 60))
        check("older: drawn after the pack files last changed, it stays", not ve._stale_look(old))
        os.utime(os.path.join(old, "index.html"), (os.path.getmtime(stylepack.SPEC) - 60,) * 2)
        check("older: drawn before the pack files last changed, it is drawn again", ve._stale_look(old))
    except Exception as e:
        fails.append(f"stopped: {type(e).__name__}: {e}")
    finally:
        if prev is None:
            os.environ.pop("REEL_PREVIEW_PACKS", None)
        else:
            os.environ["REEL_PREVIEW_PACKS"] = prev
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_stale_look_pack: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_stale_look_pack: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
