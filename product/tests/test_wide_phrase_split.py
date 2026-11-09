#!/usr/bin/env python3
"""Guard: a phrase or spotlight caption still wider than the safe box at the size floor is shown as two captions
that hand off to each other, never run into the side margins (a buyer's report, 2026-10-18: a spotlight phrase of
four long words stayed 977px wide at the 58px floor, where the step-down stops, ~35px into each margin).
Phrases that fit are untouched.

  unit   _split_wide splits where the wider half is narrowest, the second half takes over the moment its first
         word is said, and it leaves a one-word phrase or a half too short to show alone.
  build  a real composition (the private engine root from test_reel_type_matching): the wide phrase becomes two
         abutting clips, every phrase box fits inside the safe width, and a short phrase stays one clip.

Run: python3 product/tests/test_wide_phrase_split.py
"""
import ast, html as _html, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "build-reel-type.py")
sys.path.insert(0, HERE)
import test_reel_type_matching as rt   # noqa: E402  (shadow / job / build helpers)

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


# ---- unit --------------------------------------------------------------------------------------------------
tree = ast.parse(open(SRC, encoding="utf-8").read())
fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "_split_wide")
ns = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), SRC, "exec"), ns)
split = ns["_split_wide"]

W = lambda txt, t: (0, {"w": txt, "t": t, "e": t + 0.3})
P = dict(gid="ph3", mode="spotlight", start=1.0, end=3.0,
         words=[W("grandmother's", 1.0), W("garden", 1.4), W("photography", 1.8), W("introduction", 2.2)], F=58)
a_b = split(P, [290, 170, 240, 330], 15, "ph9")
check(len(a_b) == 2, f"a wide 4-word phrase splits in two, got {len(a_b)}")
if len(a_b) == 2:
    a, b = a_b
    check([w["w"] for _, w in a["words"]] == ["grandmother's", "garden"], f"first half {[w['w'] for _, w in a['words']]}")
    check([w["w"] for _, w in b["words"]] == ["photography", "introduction"], f"second half {[w['w'] for _, w in b['words']]}")
    check(a["start"] == 1.0 and a["end"] == 1.8 == b["start"] and b["end"] == 3.0, "the halves hand off with no gap")
    check(a["gid"] == "ph3" and b["gid"] == "ph9", "the second half gets its own id")
    check("F" not in a and "F" not in b, "each half is measured fresh (no stale layout carried over)")
uneven = split(dict(P, words=P["words"][:3]), [600, 100, 100], 15, "ph9")
check(len(uneven) == 2 and len(uneven[0]["words"]) == 1, "an uneven phrase splits where the wider half is narrowest")
check(split(dict(P, words=P["words"][:1]), [977], 15, "ph9") == [dict(P, words=P["words"][:1])], "one word: unchanged")
check(len(split(dict(P, end=1.82), [290, 170, 240, 330], 15, "ph9")) == 1, "a half too short to show: unchanged")

# ---- build -------------------------------------------------------------------------------------------------
base = tempfile.mkdtemp(prefix="wide-phrase-")
try:
    tmp = os.path.join(base, "spot"); rt.shadow(tmp)
    rt.job(tmp, "Her grandmother's garden photography introduction. Went fine.".split(),
           {"caption_mode": "spotlight", "hook": ""})
    r, html = rt.build(tmp)
    check(r.returncode == 0 and html, f"builds: {r.stderr[-400:]}")
    clips = re.findall(r'<div class="clip" id="clip-(ph\d+)" data-start="([\d.]+)" data-duration="([\d.]+)"[^>]*>'
                       r'<div class="phrase"[^>]*gap:(\d+)px[^>]*>(.*?)</div></div>', html)
    safe = 1080 - 2 * 90
    shown = []
    for gid, st, du, gap, body in clips:
        widths = [int(x) for x in re.findall(r'class="pw" id="[^"]+" style="width:(\d+)px"', body)]
        words = re.findall(r'class="ph-h"[^>]*>([^<]+)<', body)
        total = sum(widths) + int(gap) * (len(widths) - 1)
        check(total <= safe, f"{gid} {words} is {total}px, wider than the {safe}px safe box")
        shown.append((float(st), float(st) + float(du), [_html.unescape(w).strip(".,").casefold() for w in words]))
    long_ = [s for s in shown if set(s[2]) & {"grandmother's", "garden", "photography", "introduction"}]
    # Two captions with the pack's own faces; a bundle without a paid face measures on its stand-in and can land on
    # more. What holds either way: more than one caption, each inside the safe box (above), handing off with no gap.
    check(len(long_) >= 2, f"the wide phrase is more than one caption, got {[s[2] for s in long_]}")
    if len(long_) >= 2:
        check(all(abs(long_[i][1] - long_[i + 1][0]) < 0.011 for i in range(len(long_) - 1)),
              f"they hand off with no gap: {long_}")
        check(sum((s[2] for s in long_), []) == ["her", "grandmother's", "garden", "photography", "introduction"],
              f"every word once, in order: {[s[2] for s in long_]}")
    check([s[2] for s in shown if "went" in s[2]] == [["went", "fine"]], "a phrase that fits stays one caption")
    check("each shown as two captions that hand off" in r.stdout, "the split is said in the build output")
finally:
    shutil.rmtree(base, ignore_errors=True)

if fails:
    print(f"FAIL test_wide_phrase_split: {len(fails)}/{n}"); [print("FAIL  ", f) for f in fails]; sys.exit(1)
print(f"test_wide_phrase_split: all {n} checks passed")
