#!/usr/bin/env python3
"""Guards: a takeover keeps up with her voice, and a held word can push in for as long as it stays.

  pace      each takeover word's entrance ends by the time she says the next word (a 0.5s fade on a line said at
            0.25s a word kept every word still arriving after she had moved on); the last word is capped by how
            long she takes to say it, so it is fully on screen before the takeover leaves
  hold      slow-zoom lands, then its follow-up push runs to the moment the word leaves (the "hold" duration)
  offered   slow-zoom is in the catalog and in a takeover's Refine menu ("Slow zoom")
  taught    a taught effect derived from slow-zoom keeps "hold" instead of failing validation
  own words a look's words come from its own line, never the next line's word inside its hold window (that word
            made the timings get thrown out and spread evenly, slower than she talks)
  skin      a pack she built (no palette entry) still defines every color a design names, light = her caption
            white, so a design's text never falls back to the browser's black; check-design refuses an undefined one;
            every pack names PkThought (its thought-bubble hand, else its caption face) for an aside
  accent    a word she highlighted on a takeover's line wears her highlight style there (the captions' .capword.hl:
            the pack's keyword face, in the pack accent);
            a takeover with no highlight on its line stays plain
  catch-up  turning a highlight on or off redraws the takeovers and line captions on that line (refine and move
            kept), and a takeover drawn before highlights reached takeovers catches up (redraw-highlights)

Run: python3 product/tests/test_takeover_word_timing.py
"""
import json, os, re, shutil, subprocess, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import text_effects as tx  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


# hold: the push runs for the rest of the time on screen
js = tx.render("x", "$27,000", "slow-zoom", 8.2, hold=2.7)[1]
m = re.search(r'tl\.to\("#x",\{scale:1\.16,duration:([0-9.]+)', js)
check(m and abs(float(m.group(1)) - 2.4) < 0.01, f"hold: slow-zoom's push should run 2.7-0.3s, got {js!r}")
check("slow-zoom" in tx.CATALOG, "offered: slow-zoom missing from the catalog")
check(tx.render("y", "w", "slow-zoom", 0.0)[1].count("duration:1.5") == 1, "hold: without a hold the push falls back to 1.5s")

# taught: a derived effect keeps the "hold" duration
try:
    spec = tx._validate("my-zoom", dict(tx.E["slow-zoom"])) if hasattr(tx, "_validate") else None
except Exception as e:
    spec = e
check(not isinstance(spec, Exception), f"taught: validating a slow-zoom copy failed: {spec}")
if isinstance(spec, dict):
    check(spec["then"][0]["dur"] == "hold", "taught: the follow-up lost its hold duration")

# offered: Refine lists it on a takeover
import lookbook  # noqa: E402
check(any(e["id"] == "slow-zoom" for e in lookbook.effects_for("takeover")), "offered: Slow zoom not in a takeover's Refine menu")

# pace: draw a real takeover on a fast five-word line and read each word's entrance
tmp = tempfile.mkdtemp(prefix="tk-pace-")
try:
    words = [{"w": w, "t": round(0.12 + i * 0.25, 3), "e": round(0.12 + i * 0.25 + 0.21, 3)}
             for i, w in enumerate("Let me break it down.".split())]
    pack = next((p for p in ("Butter", "Editorial", "Playful") if p in __import__("stylepack").names()), None)
    r = lookbook.draw("takeover", tmp, "Let me break it down.", 1.29, pack, words=words, effect="per-word-crossfade")
    html = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    starts = {int(a): (float(d), float(t)) for a, d, t in
              re.findall(r'tl\.fromTo\("#tk0w(\d) \.tfx",\{[^}]*\},\{[^}]*duration:([0-9.]+)[^}]*\},([0-9.]+)\)', html)}
    check(len(starts) == 5, f"pace: expected 5 word entrances, found {len(starts)}")
    for i in range(4):
        if i in starts and i + 1 in starts:
            d, t = starts[i]
            check(t + d <= starts[i + 1][1] + 0.002, f"pace: word {i} still arriving when word {i + 1} starts ({t}+{d})")
    if 4 in starts:
        d, t = starts[4]
        check(d <= 0.21 + 0.002, f"pace: the last word's entrance ({d}s) outlasts saying it (0.21s)")
except lookbook.Refuse as e:
    check(False, f"pace: drawing the takeover refused: {e}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# accent: her highlight on the takeover's line reaches the takeover
tmp = tempfile.mkdtemp(prefix="tk-acc-")
try:
    pack = next((p for p in ("Butter", "Editorial", "Playful") if p in __import__("stylepack").names()), None)
    r = lookbook.draw("takeover", tmp, "$27,000", 2.6, pack, words=[{"w": "$27,000", "t": 0.12, "e": 2.6}],
                      accents=[{"w": "$27,000", "t": 8.2}])
    html = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    check('id="tk0w0" class="kw"' in html, "accent: the highlighted word isn't marked in the takeover")
    kwcss = re.search(r"\.tkwrap span\.kw\{([^}]*)\}", html)
    capcss = re.search(r"\.capword\.hl\{[^}]*font-family:([^;]+);", html)
    check(kwcss and "font-family:" in kwcss.group(1), "accent: the highlighted takeover word should wear her highlight face")
    check(kwcss and capcss and ("font-family:" + capcss.group(1)) in kwcss.group(1),
          "accent: the takeover's highlight face should be the captions' highlight face (.capword.hl)")
    line = [("But", 0.0, 0.2), ("don't", 0.22, 0.45), ("just", 0.47, 0.66), ("build", 0.68, 0.9), ("an", 0.92, 1.0),
            ("offer,", 1.02, 1.4), ("build", 1.606, 1.9), ("the", 1.926, 2.04), ("room.", 2.066, 2.5)]
    r = lookbook.draw("takeover", tmp, " ".join(w for w, _, _ in line), 3.0, pack, words=[{"w": w, "t": a, "e": b} for w, a, b in line],
                      accents=[{"w": "build", "t": 1.606}, {"w": "the", "t": 1.926}, {"w": "room.", "t": 2.066}])
    html = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    marked = re.findall(r'id="tk\d+w(\d+)" class="kw"', html)
    check(sorted(map(int, marked)) == [6, 7, 8], f"accent: 'build the room' highlighted should light all three and leave the first 'build' plain, got {marked}")
    r = lookbook.draw("takeover", tmp, "$27,000", 2.6, pack, words=[{"w": "$27,000", "t": 0.12, "e": 2.6}])
    html = open(os.path.join(r["dir"], "index.html"), encoding="utf-8").read()
    check('class="kw"' not in html, "accent: a takeover with no highlight came out accented")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

import visual_editor as ve  # noqa: E402
jd = tempfile.mkdtemp(prefix="tk-acc-job-")
try:
    os.makedirs(os.path.join(jd, "transcript"))
    json.dump({"items": [{"text": "$27,000", "t": 8.2, "on": True}, {"text": "room", "t": 50.0, "on": True},
                         {"text": "off", "t": 8.5, "on": False}]},
              open(os.path.join(jd, "transcript", "accents.json"), "w", encoding="utf-8"))
    tk = {"layer": "takeover"}
    got = ve._look_accents(jd, tk, False, 8.0, 10.9)
    check([a["w"] for a in got or []] == ["$27,000"], f"accent: a takeover should get only its own line's highlights, got {got}")
    check(ve._look_accents(jd, tk, False, 20.0, 22.0) is None, "accent: a line with no highlight should give the takeover none")
    check(len(ve._look_accents(jd, {"layer": "captions"}, True, 0, 100)) == 2, "accent: whole-reel captions should wear every highlight")
    line = ve._look_accents(jd, {"layer": "captions"}, True, 49.5, 51.0, origin=49.38)
    check(line and [(x["w"], x["t"]) for x in line] == [("room", 0.62)],
          f"accent: a line's own captions get that line's highlight, timed from the look's start, got {line}")
    check(ve._look_accents(jd, {"layer": "hook"}, False, 8.0, 10.9) is None, "accent: a hook gets no caption highlights")
finally:
    shutil.rmtree(jd, ignore_errors=True)

# catch-up: a highlight change redraws the takeovers and line captions it touches, refines kept, and the page asks for it
import inspect  # noqa: E402
src = inspect.getsource(ve.redraw_captions)
check("redraw_line_highlights(job)" in src, "catch-up: changing a highlight should redraw takeovers and line captions too")
rl = inspect.getsource(ve.redraw_line_highlights)
check("effect=rec.get(\"effect\")" in rl and "_apply_nudge" in rl, "catch-up: a redraw should keep her refine and where she moved it")
page = open(os.path.join(PRODUCT, "visual-editor", "editor.html"), encoding="utf-8").read()
blk = page[page.index("function saveAccents"):page.index("async function loadAccents")]
check("/captions-redraw" in blk and "rj.lines" in blk and 'if (A.mode === "redraw") {' not in blk,
      "catch-up: the page should ask for the redraw on every highlight, not only for builder captions")

# own words: the hold window reaches her next word ("So"); the look still gets only its line, at her real times
jd = tempfile.mkdtemp(prefix="tk-own-")
try:
    name = os.path.basename(jd)
    os.makedirs(os.path.join(jd, "outputs")); os.makedirs(os.path.join(jd, "hf-graphics", "_looks", "add-w46"))
    tw = [("Let", 16.908, 17.028), ("me", 17.068, 17.148), ("break", 17.188, 17.348), ("it", 17.388, 17.448),
          ("down.", 17.468, 17.728), ("So", 18.025, 18.165)]
    json.dump({"words": [{"text": w, "start": a, "end": b, "type": "word"} for w, a, b in tw]},
              open(os.path.join(jd, "outputs", name + ".transcript.json"), "w", encoding="utf-8"))
    json.dump({"offset": 16.789, "dur": 1.29, "span": [16.909, 17.729]},
              open(os.path.join(jd, "hf-graphics", "_looks", "add-w46", "line.json"), "w", encoding="utf-8"))
    got = ve._own_words(jd, "add-w46", 16.789, 1.29)
    check([w["w"] for w in got] == ["Let", "me", "break", "it", "down."], f"own words: the next line's word got in: {got}")
    check(got and abs(got[0]["t"] - 0.119) < 0.002, f"own words: times should stay relative to the look's start, got {got[:1]}")
finally:
    shutil.rmtree(jd, ignore_errors=True)

# skin: every named color is defined even for a pack with no palette; an undefined one is refused
import stylepack  # noqa: E402
tmp = tempfile.mkdtemp(prefix="tk-skin-")
try:
    import pack_palettes
    bare = next((p for p in stylepack.names() if p not in pack_palettes.PALETTE), None)
    for pk in [x for x in (bare, "Butter") if x and x in stylepack.names()]:
        skin = lookbook._skin(pk, tmp)
        have = dict(re.findall(r"--pk-([\w-]+):([^;]+);", skin))
        for k in ("light", "dark", "muted", "accent", "pop2", "hook", "subhead"):
            check(k in have, f"skin: {pk} leaves --pk-{k} undefined (it would render black)")
        if pk == bare:
            check(have.get("light", "").lower() == "#ffffff", f"skin: a palette-less pack's light should be caption white, got {have.get('light')}")
    # thought: every pack names a PkThought face (its thought-bubble hand, or its caption face when it has none)
    for pk in stylepack.names():
        skin = lookbook._skin(pk, tmp)
        check("font-family:PkThought;" in skin, f"skin: {pk} has no PkThought face for an aside")
        el = stylepack.load(pk).get("elements") or {}
        want = (el.get("thought_bubble") or el.get("caption") or {}).get("font")
        if want and "thought_bubble" not in el:
            check(lookbook._fit_px("an aside", "thought", pk, 600, 80, 2) == lookbook._fit_px("an aside", "caption", pk, 600, 80, 2),
                  f"skin: {pk} has no thought hand, so an aside should size as its caption face")
    d = os.path.join(tmp, "bad"); shutil.copytree(os.path.join(PRODUCT, "lookbook-designs", "starter"), d)
    hp = os.path.join(d, "index.html"); _h = open(hp, encoding="utf-8").read(); open(hp, "w", encoding="utf-8").write(_h.replace("var(--pk-dark)", "var(--pk-nope)", 1))
    probs = lookbook.check_design(d, "Butter", render_check=False) if "render_check" in lookbook.check_design.__code__.co_varnames else []
    check(any("--pk-nope" in x for x in probs), f"skin: an undefined pack color should be refused, got {probs}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_takeover_word_timing: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_takeover_word_timing: all {n} checks passed")
