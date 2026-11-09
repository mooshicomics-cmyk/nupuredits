#!/usr/bin/env python3
"""The rendered text wears HER pack's look: text color, keyword face, a hook accent word, the hook color, a spoken
thought bubble.

Buyer reports (launch week, 2026-10-19), each hand-patched by the buyer's Claude in product/build-reel-type.py:
  - plain caption and takeover words were hardcoded white, whatever the pack said
  - a spoken "thought bubble" rendered as the iMessage blue in Helvetica on every pack, breaking "every on-screen
    font and color comes from the pack"
  - the default two-part hook had no way to accent one word; three buyers hand-added a hook accent word, a hook
    keyword or a per-reel hook color
And in product/build-pack-showcase.py (the pack preview): the hook was drawn white whatever the pack's hook color.

  1. a pack's welldone text_color colors the plain captions, karaoke and takeover words; a pack without one stays white
  2. keyword_face_accents puts the accent word in the pack's keyword face; off by default
  3. hook_accent_word (and hook_keyword) draws that one hook word in the keyword face and accent color, on a one-line
     hook and on the two-part hook; a word the hook doesn't carry is said once
  4. a per-reel hook_color (and hook_color_by_pack) wins over the pack's
  5. a spoken thought bubble is drawn in the pack's face and colors; the iMessage look only when asked for by name
  6. the pack preview draws the hook in the pack's hook color

Builds real compositions in a private engine root (test_reel_type_matching's shadow), nothing rendered.

Run:  python3 product/tests/test_pack_look_honored.py
"""
import copy
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, PRODUCT)
import test_reel_type_matching as rt  # noqa: E402
import stylepack  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {str(detail)[:400]}"))
    if not cond:
        fails.append(label)


def css_rule(html, sel):
    m = re.search(re.escape(sel) + r"\{([^}]*)\}", html)
    return m.group(1) if m else ""


WORDS = "Here is the one thing. Nobody tells you this. Keep going.".split()
base = tempfile.mkdtemp(prefix="pack-look-")
try:
    tmp = os.path.join(base, "e")
    rt.shadow(tmp)
    butter = stylepack.load("Butter")
    qa = copy.deepcopy(butter)
    qa.setdefault("welldone", {}).update(text_color="#123456", keyword_face_accents=True)
    preview = os.path.join(base, "packs.json")
    with open(preview, "w", encoding="utf-8") as fh:
        json.dump({"packs": {"QaLook": qa}}, fh)
    env = {"REEL_PREVIEW_PACKS": preview}

    print("1-2. text_color and keyword_face_accents")
    rt.job(tmp, WORDS, {"takeover_keys": ["nobody tells you this"], "keywords": ["going"], "hook": ""})
    r, html = rt.build(tmp, pack="QaLook", **env)
    check("a pack with text_color builds", r.returncode == 0 and html, r.stderr[-400:])
    check("its captions are its text color", "color:#123456" in css_rule(html, ".capword"), css_rule(html, ".capword"))
    check("its karaoke is its text color", "color:#123456" in css_rule(html, ".buildwrap"), css_rule(html, ".buildwrap"))
    check("its takeovers are its text color", "color:#123456" in css_rule(html, ".tkwrap"), css_rule(html, ".tkwrap"))
    check("its accent word is in the keyword face", "font-family:" in css_rule(html, ".capword.kw"), css_rule(html, ".capword.kw"))
    r, html = rt.build(tmp, pack="Butter")
    check("a pack without text_color stays white", "color:#fff" in css_rule(html, ".capword")
          and "color:#fff" in css_rule(html, ".tkwrap"), css_rule(html, ".capword"))
    check("without keyword_face_accents the accent word keeps the caption face",
          "font-family" not in css_rule(html, ".capword.kw"), css_rule(html, ".capword.kw"))

    print("3-4. hook accent word and hook color")
    for key in ("hook_accent_word", "hook_keyword"):
        rt.job(tmp, WORDS, {"hook": ["the one thing nobody tells you"], key: "Nobody", "hook_color": "#abcdef"})
        r, html = rt.build(tmp, pack="Butter")
        m = re.search(r'<span style="font-family:([^;]+);color:([^;]+);font-style:normal">nobody</span>', html, re.I)
        check(f"{key}: the one-line hook's word is in the keyword face and accent color", m is not None,
              re.findall(r"<div id=\"hookwrap\">.*?</div></div>", html)[:1])
        check(f"{key}: only that word", len(re.findall(r'font-style:normal">[^<]*</span>', html)) == 1)
    check("a per-reel hook_color wins over the pack's", 'class="hkline"' in html and "color:#abcdef" in html)
    rt.job(tmp, WORDS, {"hook_long": "Nobody warned me about this part. The one thing nobody tells you about launching.",
                        "hook_accent_word": "launching"})
    r, html = rt.build(tmp, pack="Butter")
    i = html.find('id="hooksplit"')
    acc = re.search(r'<span style="font-family:[^;]+;color:[^;]+;font-style:normal">(.*?)</span></span>', html[i:i + 20000], re.S)
    letters = "".join(re.findall(r">([^<>])<", acc.group(1))) if acc else ""
    check("the two-part hook carries the accent word too (letter by letter under a split effect)",
          i >= 0 and letters.lower().strip(".,") == "launching", (letters, r.stdout[-300:]))
    rt.job(tmp, WORDS, {"hook": ["the one thing nobody tells you"], "hook_accent_word": "elephant",
                        "hook_color_by_pack": {"Butter": "#fedcba"}})
    r, html = rt.build(tmp, pack="Butter")
    check("a word the hook doesn't carry is said once", r.stdout.count('hook_accent_word "elephant"') == 1, r.stdout[-300:])
    check("hook_color_by_pack wins for that pack", "color:#fedcba" in html)

    print("5. a spoken thought bubble")
    rt.job(tmp, WORDS, {"hook": ["the one thing"], "vibe": {"kind": "bubble", "text": "me: wait what", "at": 1.0}})
    r, html = rt.build(tmp, pack="Butter")
    rule = css_rule(html, "#vibeB")
    check("it builds", r.returncode == 0 and rule, r.stderr[-300:])
    check("no iMessage blue", "#0A84FF" not in html and "#25B4FF" not in html, rule)
    check("no system face: a pack face draws it", "Helvetica" not in rule and "font-family:" in rule, rule)
    rt.job(tmp, WORDS, {"hook": ["the one thing"], "vibe": {"kind": "bubble", "text": "me: wait what", "imessage": True}})
    r, html = rt.build(tmp, pack="Butter")
    check("the iMessage look when she asks for it by name", "#0A84FF" in css_rule(html, "#vibeB"))
finally:
    shutil.rmtree(base, ignore_errors=True)

print("6. the pack preview")
src = open(os.path.join(PRODUCT, "build-pack-showcase.py"), encoding="utf-8").read()
check("the preview draws the hook in the pack's hook color", 'hook_color' in src and "HOOK_COLOR" in src)
check("the preview cases text the way the builders do", "stylepack.apply_case" in src or "stylepack.case_rule" in src)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "pack look: every rendered word wears her pack"))
sys.exit(1 if fails else 0)
