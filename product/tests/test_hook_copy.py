#!/usr/bin/env python3
"""A hook is never her spoken sentence copied onto the card, and a word on screen never splits in half.

  * place_at on a hook look (hook, eyebrow + headline, headline + subhead) draws nothing without its own copy, and
    with it the copy reaches the draw (2026-10-17: the hook showed her whole first sentence word for word).
  * text_effects._split_html keeps each word's letters in one unbreakable box ("THI / S HAPPENED" on a long hook).
"""
import os, re, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import text_effects  # noqa: E402
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {detail}")


def test_words_never_split():
    esc = lambda t: t
    for mask in (False, True):
        html = text_effects._split_html("and then this happened.", "char", mask, esc)
        boxes = re.findall(r'<span class="tfxw" style="display:inline-block;white-space:nowrap">(.*?)</span>', html)
        letters = ["".join(re.findall(r'<i class="tfx">(.)</i>', b)) for b in boxes]
        check(f"split{' (mask)' if mask else ''}: one unbreakable box per word", letters == ["and", "then", "this", "happened."], letters)
        outside = re.sub(r'<span class="tfxw"[^>]*>.*?</span>', "", html)
        check(f"split{' (mask)' if mask else ''}: breaks only between words", outside == "   ", repr(outside))
    check("split: word mode unchanged", text_effects._split_html("a b", "word", False, esc) == '<i class="tfx">a</i> <i class="tfx">b</i>')


def test_hook_needs_its_own_copy():
    real = (ve.job_dir, ve.word_cut_times, ve._reel_pack, ve.place_look, ve._free_add_key)
    placed = []
    jd = tempfile.mkdtemp(prefix="hook-copy-")
    ve.job_dir = lambda job: jd
    ve.word_cut_times = lambda jd: {0: (1.7, 1.85), 1: (1.89, 2.09)}
    ve._reel_pack = lambda jd: "Butter"
    ve._free_add_key = lambda jd, first, look_id=None: f"add-w{first}"
    ve.place_look = lambda job, key, s, e, look, copy=None: placed.append((key, look, copy)) or {}
    try:
        for look in ("hook", "eyebrow-headline", "headline-subhead"):
            try:
                ve.place_at("j", look, 1.7, 2.1)
                check(f"hook: {look} with no copy is refused", False, "drew it")
            except ve.Refuse as e:
                check(f"hook: {look} with no copy is refused", "--text" in str(e), str(e))
        check("hook: nothing drawn without copy", placed == [], placed)
        ve.place_at("j", "eyebrow-headline", 1.7, 2.1, copy="everyone's editing with Claude now / mine isn't the same")
        check("hook: its copy reaches the draw", placed == [("add-w0", "eyebrow-headline", "everyone's editing with Claude now / mine isn't the same")], placed)
        ve.place_at("j", "takeover", 1.7, 2.1)
        check("not a hook: her words, no copy needed", placed[-1] == ("add-w0", "takeover", None), placed)
    finally:
        ve.job_dir, ve.word_cut_times, ve._reel_pack, ve.place_look, ve._free_add_key = real


if __name__ == "__main__":
    test_words_never_split()
    test_hook_needs_its_own_copy()
    if fails:
        print(f"test_hook_copy: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  - " + f)
        sys.exit(1)
    print(f"test_hook_copy: all {total} checks passed")
