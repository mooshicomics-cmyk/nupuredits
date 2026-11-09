#!/usr/bin/env python3
"""A look's page on her preview is never missing, a hook is never her spoken line, and a quiet line still takes a look.

  * lookbook.draw redraws a look's page off to the side and swaps it in whole: a reader polling the page all through
    three redraws never finds it missing (it was deleted first, so her page could load "not found" mid-redraw), and a
    draw that fails leaves the look she had in place
  * Add a look draws the hook tiles with a sample, never her line; picking a hook from the menu with no words of its
    own is refused; with its own words, those words are on the card
  * a quiet line (no words in her cut) offers the looks that bring their own words, never a refusal and never another
    line's words, and one placed there carries her copy

Run: python3 product/tests/test_look_pages_stay.py
"""
import json, os, shutil, subprocess, sys, tempfile, threading, time
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {detail}")


def main():
    if not shutil.which("ffmpeg"):
        print("test_look_pages_stay: skipped (ffmpeg isn't on this machine to make the test reel).")
        return 0
    import test_editor_journey as tj
    import editor_journey_fixture as fx
    import lookbook
    tmp = tempfile.mkdtemp(prefix="look-pages-")
    try:
        ve, srv, jd = tj.sandbox(tmp)
        job = fx.JOB
        ve._atomic_json(os.path.join(jd, "review", "phase.json"), {"phase": "looks"})
        ve.set_captions(job, "phrase")
        t = ve.word_cut_times(jd)

        # 1. a redraw never leaves the page missing, and a failed one keeps the old page
        out = os.path.join(jd, "hf-graphics", "_looks", "add-w0", "_menu", "takeover")
        lookbook.draw("takeover", out, "this is the hook line", 2.0, "Butter")
        page = os.path.join(out, "hf-reel-type-butter", "index.html")
        missing, stop = [0], [False]

        def watch():
            while not stop[0]:
                if not os.path.isfile(page):
                    missing[0] += 1
                time.sleep(0.0005)
        th = threading.Thread(target=watch, daemon=True)
        th.start()
        for words in ("this is the hook line", "the hook line again", "and once more"):
            lookbook.draw("takeover", out, words, 2.0, "Butter")
        stop[0] = True
        th.join()
        check("redraw: the page is there the whole time it's redrawn (three redraws)", missing[0] == 0, f"missing {missing[0]} times")
        check("redraw: the new page is in place", "once more" in json.load(open(os.path.join(out, "look.json"), encoding="utf-8"))["text"].lower())
        check("redraw: nothing left beside it", not [f for f in os.listdir(out) if f.startswith((".swap-", ".old-"))], os.listdir(out))
        real = lookbook.BUILDER
        lookbook.BUILDER = os.path.join(tmp, "no-such-builder.py")
        try:
            lookbook.draw("takeover", out, "a draw that fails", 2.0, "Butter")
            check("redraw: a failed draw says so", False, "no refusal")
        except lookbook.Refuse:
            check("redraw: a failed draw says so", True)
        finally:
            lookbook.BUILDER = real
        check("redraw: a failed draw leaves the look she had", os.path.isfile(page)
              and "once more" in json.load(open(os.path.join(out, "hf-reel-type-butter", "look.json"), encoding="utf-8"))["text"].lower())

        # 2. hooks: a sample on the tile, refused without words of their own, her words on the card with them
        m = ve.add_menu(job, "add-w16", t[16][0], t[20][1])
        hooks = [x for x in m["looks"] if x.get("copy")]
        check("hook: every hook tile asks for its own words", {x["id"] for x in hooks} == {"hook", "eyebrow-headline", "headline-subhead"}, [x["id"] for x in hooks])
        tile = json.load(open(os.path.join(jd, "hf-graphics", "_looks", "add-w16", "_menu", "hook", "look.json"), encoding="utf-8"))["text"]
        check("hook: its tile shows a sample, never her spoken line", "then we speed" not in tile.lower(), tile)
        try:
            ve.swap(job, "add-w16", "hook", from_menu=True)
            check("hook: picked with no words of its own is refused", False, "placed")
        except ve.Refuse as e:
            check("hook: picked with no words of its own is refused", "own" in str(e), str(e))
        ve.swap(job, "add-w16", "hook", from_menu=True, copy="nobody tells you this part")
        L = next(x for x in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"] if x["name"] == "add-w16")
        shown = json.load(open(os.path.join(jd, L["dir"], "look.json"), encoding="utf-8"))["text"]
        check("hook: with its own words, those words are on the card", L["look"] == "hook" and shown == "nobody tells you this part", (L["look"], shown))
        check("hook: the words are kept with the look (a redraw keeps them)", (ve._entry(jd, "add-w16")[0] or {}).get("copy") == "nobody tells you this part")

        # 3. a quiet line: the looks with their own words, nothing borrowed, one placed there with her copy
        q = ve.add_menu(job, "add-w21", t[12][1] + 0.02, t[13][0] - 0.02)
        ids = [x["id"] for x in q["looks"]]
        check("quiet line: offered, never refused, only the looks that bring their own words", q["quiet"] and ids and all(i in ("hook", "eyebrow-headline", "headline-subhead") for i in ids), ids)
        texts = [json.load(open(os.path.join(jd, "hf-graphics", "_looks", "add-w21", "_menu", i, "look.json"), encoding="utf-8"))["text"].lower() for i in ids]
        check("quiet line: no tile carries another line's words", all("your hook" in x for x in texts), texts)
        ve.swap(job, "add-w21", "headline-subhead", from_menu=True, copy="the pause / that says it all")
        Lq = next((x for x in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"] if x["name"] == "add-w21"), None)
        check("quiet line: a hook with her words sits in the quiet stretch", bool(Lq) and Lq["look"] == "headline-subhead"
              and t[12][1] - 0.2 <= Lq["offset"] <= t[13][0], Lq and (Lq["look"], Lq["offset"]))
        try:
            ve.add_menu(job, "cap-w21", t[12][1] + 0.02, t[13][0] - 0.02, "caption")
            check("quiet line: captions on no words are refused plainly", False, "drew captions")
        except ve.Refuse:
            check("quiet line: captions on no words are refused plainly", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_look_pages_stay: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  FAIL  " + f)
        return 1
    print(f"test_look_pages_stay: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
