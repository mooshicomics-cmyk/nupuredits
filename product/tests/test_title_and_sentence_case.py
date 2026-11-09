#!/usr/bin/env python3
"""Guard: Title Case keeps a word with an apostrophe whole, and sentence case is a case a pack can have.

A buyer's Title Case hook came out "The Five Non-Toxic Swaps I'D Make First" and "A Family'S Routine" (2026-10-28):
the engine used Python's str.title(), which starts a new word after an apostrophe. Every route cases the hook
through stylepack.apply_case, so CapCut drafts had it too. She also asked for sentence case (a capital on the first
word, the rest as she says it), her brand guide's real style; "sentence" used to be read as "as written".

  title      apostrophes (straight and curly) stay inside the word, a word starting with a digit stays as it is,
             a brand spelled with a capital inside keeps it, hyphenated words still capitalize each part
  sentence   a capital on the first letter only, the rest exactly as written; a number first, an already capital
             first letter and leading punctuation are handled
  roles      sentence case on a caption or takeover (one word at a time) keeps her words as said; on a hook, card
             or label it is sentence case; the language rule and her plan's own choice still hold
  imports    a DESIGN.md may say sentence for hook / card / caption / label case; the recipe and the Canva import
             take it; the build summary says it in words
  builders   no builder cases text with str.title() any more; the card lines and the persistent label go through
             the shared rule

Run: python3 product/tests/test_title_and_sentence_case.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import stylepack as sp

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {detail}")


def eq(name, got, want):
    check(name, got == want, f"{got!r} != {want!r}")


# ── title
eq("title: her hook", sp.apply_case("the five non-toxic swaps i'd make first", "title"),
   "The Five Non-Toxic Swaps I'd Make First")
eq("title: a possessive", sp.apply_case("a family's routine", "title"), "A Family's Routine")
eq("title: a curly apostrophe", sp.apply_case("don’t skip this", "title"), "Don’t Skip This")
eq("title: a word starting with a digit", sp.apply_case("my 5th launch", "title"), "My 5th Launch")
eq("title: shouting comes down", sp.apply_case("STOP DOING THIS", "Title Case"), "Stop Doing This")
eq("title: a brand keeps its own capitals", sp.apply_case("my tiktok routine", "title", brands={"tiktok": "TikTok"}),
   "My TikTok Routine")
eq("title: an apostrophe at a word's edge is not a letter", sp.apply_case("'quoted' moms' night", "title"),
   "'Quoted' Moms' Night")

# ── sentence
eq("sentence: a capital on the first word, the rest as written", sp.apply_case("the five swaps I'd make first", "sentence"),
   "The five swaps I'd make first")
eq("sentence: her own capitals stay", sp.apply_case("why I quit Instagram", "Sentence case"), "Why I quit Instagram")
eq("sentence: nothing is lowered", sp.apply_case("STOP. read this", "sentence"), "STOP. read this")
eq("sentence: a number first is left as it is", sp.apply_case("5 swaps i make", "sentence"), "5 swaps i make")
eq("sentence: leading punctuation", sp.apply_case("¿qué pasa?", "sentence"), "¿Qué pasa?")
eq("sentence: empty text", sp.apply_case("", "sentence"), "")
eq("sentence: every spelling of it", [sp.normalize_case(r) for r in ("sentence", "Sentence case", "sentence_case")],
   ["sentence"] * 3)

# ── roles
eq("roles: a hook in sentence case", sp.case_rule("sentence", "headline"), "sentence")
eq("roles: a caption word keeps her words as said", sp.case_rule("sentence", "caption"), "as-written")
eq("roles: a takeover word keeps her words as said", sp.case_rule("sentence", "takeover"), "as-written")
eq("roles: no role (a hook through packbuild) is sentence case", sp.case_rule("sentence"), "sentence")
eq("roles: sentence case holds on a reel in another language", sp.case_rule("sentence", "headline", lang="de"), "sentence")
eq("roles: title on a German reel is still made safe", sp.case_rule("title", "headline", lang="de"), "as-written")
eq("roles: her plan's choice wins", sp.case_rule("upper", "headline", {"headline_case": "sentence"}), "sentence")

# ── imports
import design_md, pack_recipe
check("imports: a DESIGN.md may say sentence", "sentence" in design_md.CASES, design_md.CASES)
check("imports: the recipe offers it", "sentence" in pack_recipe.CASE_CHOICES and pack_recipe.norm_case("Sentence") == "sentence")
eq("imports: the build summary says it in words",
   pack_recipe.case_line({"elements": {"headline": {"case": "sentence"}, "takeover": {"case": "upper"}, "caption": {"case": "as-written"}}}),
   "headline Sentence case · takeover ALL CAPS · caption as she types it")
src = open(os.path.join(PRODUCT, "canva_to_pack.py"), encoding="utf-8").read()
check("imports: the Canva import takes --case sentence", '("upper", "lower", "title", "sentence")' in src)

# ── builders
for f in ("build-reel-type.py", "build-hf-captions.py", "packbuild.py", "hooksplit.py", "build-pack-showcase.py"):
    s = open(os.path.join(PRODUCT, f), encoding="utf-8").read()
    check(f"builders: {f} never cases text with str.title()", not re.search(r"\.title\(\)", s))
brt = open(os.path.join(PRODUCT, "build-reel-type.py"), encoding="utf-8").read()
check("builders: the card lines take her card case (title, lower, sentence)",
      re.search(r'_bcase = stylepack\.case_rule\(_th\.get\("headline_case"\)', brt) is not None)
check("builders: the persistent label goes through the shared rule",
      "_pltxt = stylepack.apply_case(_PLBL, stylepack.normalize_case(_plcase)" in brt)

print(f"test_title_and_sentence_case: {total - len(fails)}/{total} passed")
for f in fails:
    print("  FAIL", f)
sys.exit(1 if fails else 0)
