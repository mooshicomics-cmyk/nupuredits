#!/usr/bin/env python3
"""Guards: a brand spelled with a capital inside it keeps it in a lowercase pack (a buyer, 2026-10-22).

Her word fixes spelled "PeachPod" and "LaLa LoLo", and her lowercase caption pack wrote "peachpod". The pack's
lowercase is a style; the brand's spelling isn't. One shared rule (stylepack.apply_case with brand_spellings), so
every caption route agrees.

  tables     brand_spellings reads the shared table, hers in _local/ and the reel's own word-fixes.json (words and
             phrases); an unreadable table is passed over
  rule       lowercase and title case keep the brand's spelling (possessives too, never inside a longer word);
             UPPERCASE still shouts it; a capital only at the start (Instagram) or an acronym (AI, DMs) follows the pack
  routes     the editor's looks and rendered captions (build-reel-type, drawn through lookbook.draw for a reel),
             the HyperFrames captions (build-hf-captions) and the CapCut text (packbuild.caseit) all use it

Run: python3 product/tests/test_brand_spellings.py
"""
import json, os, re, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import stylepack as sp  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="brand-spellings-")
    try:
        jd = os.path.join(tmp, "reel")
        os.makedirs(jd)
        json.dump({"words": {"peachpod": "PeachPod", "insta": "Insta"}, "phrases": {"la la lo lo": "LaLa LoLo"}},
                  open(os.path.join(jd, "word-fixes.json"), "w", encoding="utf-8"))
        b = sp.brand_spellings(jd)
        check("tables: the reel's own word fix is kept", b.get("peachpod") == "PeachPod", b)
        check("tables: each word of a phrase fix is kept", b.get("lala") == "LaLa" and b.get("lolo") == "LoLo", b)
        check("tables: the shared table's brands are kept (TikTok)", b.get("tiktok") == "TikTok", b)
        check("tables: a capital only at the start is an ordinary word", "insta" not in b and "instagram" not in b, b)
        check("tables: an acronym is not a brand spelling (AI, DMs)", "ai" not in b and "dms" not in b, b)
        check("tables: without the reel, only the shared and her own tables", "peachpod" not in sp.brand_spellings(None))
        open(os.path.join(jd, "word-fixes.json"), "w", encoding="utf-8").write("{ broken")
        check("tables: an unreadable table is passed over, never a crash", "peachpod" not in sp.brand_spellings(jd)
              and sp.brand_spellings(jd).get("tiktok") == "TikTok")
        json.dump({"words": {"peachpod": "PeachPod"}, "phrases": {"la la lo lo": "LaLa LoLo"}},
                  open(os.path.join(jd, "word-fixes.json"), "w", encoding="utf-8"))
        b = sp.brand_spellings(jd)

        s = "My PeachPod's box from LaLa LoLo on TikTok, AI and DMs on Instagram. peachpodx"
        check("rule: lowercase keeps the brand's spelling, possessive too, never inside a longer word",
              sp.apply_case(s, "lower", brands=b) == "my PeachPod's box from LaLa LoLo on TikTok, ai and dms on instagram. peachpodx",
              sp.apply_case(s, "lower", brands=b))
        check("rule: with no brands it is plain lowercase, as before", sp.apply_case(s, "lower") == s.lower())
        check("rule: title case keeps it too", sp.apply_case("my peachpod box", "title", brands=b) == "My PeachPod Box",
              sp.apply_case("my peachpod box", "title", brands=b))
        check("rule: UPPERCASE still shouts it", sp.apply_case("my PeachPod", "upper", brands=b) == "MY PEACHPOD")
        check("rule: a builder's own lowercase (God stays God) still runs first",
              sp.apply_case("God and PeachPod", "lower", lower=lambda t: "God and peachpod", brands=b) == "God and PeachPod")

        import packbuild
        check("routes: CapCut text (packbuild.caseit) with the reel", packbuild.caseit("PeachPod rocks", "lower", job_dir=jd) == "PeachPod rocks",
              packbuild.caseit("PeachPod rocks", "lower", job_dir=jd))
        hf = open(os.path.join(PRODUCT, "build-hf-captions.py"), encoding="utf-8").read()
        check("routes: the HyperFrames captions case through the shared rule with her brands",
              re.search(r"def apply_case\(role, w\):.*?stylepack\.apply_case\(w, m, lower=case_fix, brands=_BRANDS\)", hf, re.S) is not None)
        rt = open(os.path.join(PRODUCT, "build-reel-type.py"), encoding="utf-8").read()
        check("routes: the editor's looks and rendered captions case with her brands",
              re.search(r"def caseit\(s, e\):.*?brands=BRANDS\)", rt, re.S) is not None)

        import lookbook                                       # a real draw for a reel, in a lowercase pack
        out = os.path.join(jd, "hf-graphics", "_looks", "add-w0", "_menu", "takeover")
        lookbook.draw("takeover", out, "my peachpod box", 2.0, "Editorial")
        html = open(os.path.join(out, "hf-reel-type-editorial", "index.html"), encoding="utf-8").read()
        shown = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
        check("routes: a takeover drawn for her reel in a lowercase pack reads PeachPod (her reel's own fix)",
              "PeachPod" in shown and "peachpod" not in shown, re.findall(r"(?i)peachpod", shown))
    except Exception as e:
        fails.append(f"stopped: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_brand_spellings: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_brand_spellings: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
