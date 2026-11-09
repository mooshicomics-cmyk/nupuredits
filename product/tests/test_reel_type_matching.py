#!/usr/bin/env python3
"""build-reel-type.py matches the plan to the transcript in any language, builds in HER pack and accent, and
files every kind of element under a layer that says what it is.

Each case builds a real composition in a private engine root (product/ and assets/ linked file by file, her
user-style.json written per case, projects/ its own), with HOME pointed at an empty folder so nothing on this
machine's CapCut is read or written. What it pins:

  words      the matcher was a-z only: a Russian transcript normalised to empty strings and one caption
             treatment matched EVERY line; an accented key ("está bien") or a curly-quote key ("don’t stop")
             never matched; keywords were not normalised at all; an empty key spun forever.
  pack       STYLE_PACK unset silently meant Butter. Now: STYLE_PACK, else her saved default, else a refusal.
  accent     her saved default accent (user-style.json, /studio accent) was ignored.
  layers     takeover stacks shared the captions' lane and the "takeover" layer held the breakaway card.
             A layer build also left timeline lines aimed at clips it had dropped, which reel_render.py
             refuses as dead animation targets.
  fonts      a face the pack pins by file (the split-hook eyebrow) pointed at a file a buyer's bundle does not
             have; it is now found like any pack face, and two CapCut catalog files both named font.ttf no
             longer collapse into one @font-face.

Run: python3 product/tests/test_reel_type_matching.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
PAID = {"Prosecco.ttf", "ProseccoandBaguette.ttf", "HFOperaCake.ttf", "Geomanist-Regular.otf", "SoupDuJour.ttf",
        "SoupDuJourHollow.ttf", "Bloop.ttf", "UglyDaveAlternates.otf"}

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def shadow(tmp, user_style=None, drop_fonts=()):
    """A private engine root. Everything is linked to the real engine except her user-style.json (written
    here) and the fonts in drop_fonts (left out, the way a buyer's bundle leaves out the paid faces)."""
    os.makedirs(os.path.join(tmp, "product", "creative-vault"))
    for n in os.listdir(PRODUCT):
        if n not in ("creative-vault", "__pycache__"):
            os.symlink(os.path.join(PRODUCT, n), os.path.join(tmp, "product", n))
    cv = os.path.join(PRODUCT, "creative-vault")
    for n in os.listdir(cv):
        if n != "user-style.json":
            os.symlink(os.path.join(cv, n), os.path.join(tmp, "product", "creative-vault", n))
    with open(os.path.join(tmp, "product", "creative-vault", "user-style.json"), "w", encoding="utf-8") as fh:
        json.dump({"default_pack": None, "default_accent": None, "history": [], **(user_style or {})}, fh)
    os.makedirs(os.path.join(tmp, "assets", "fonts"))
    for n in os.listdir(os.path.join(ROOT, "assets")):
        if n != "fonts":
            os.symlink(os.path.join(ROOT, "assets", n), os.path.join(tmp, "assets", n))
    for n in os.listdir(os.path.join(ROOT, "assets", "fonts")):
        if n not in drop_fonts:
            os.symlink(os.path.join(ROOT, "assets", "fonts", n), os.path.join(tmp, "assets", "fonts", n))
    os.makedirs(os.path.join(tmp, "home"))


def job(tmp, words, plan, name="qa-job"):
    d = os.path.join(tmp, "projects", name, "outputs")
    os.makedirs(d, exist_ok=True)
    t, out = 0.3, []
    for w in words:
        out.append({"text": w, "start": round(t, 2), "end": round(t + 0.3, 2)})
        t += 0.4
    with open(os.path.join(d, f"{name}.transcript.json"), "w", encoding="utf-8") as fh:
        json.dump({"words": out}, fh, ensure_ascii=False)
    with open(os.path.join(tmp, "projects", name, "caption-plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False)


def build(tmp, pack="Butter", home=None, name="qa-job", **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("STYLE_PACK", "LAYER", "HOOK_SPLIT", "CAPTION_MODE",
                                                               "DUR_OVERRIDE", "PREVIEW_BG")}
    env.update({"JOB": name, "HOME": home or os.path.join(tmp, "home"), **env_extra})
    if pack:
        env["STYLE_PACK"] = pack
    r = subprocess.run([sys.executable, os.path.join(tmp, "product", "build-reel-type.py")], cwd=tmp, env=env,
                       capture_output=True, text=True, timeout=120)
    got = (pack or "").lower()
    if not pack:
        m = re.search(r"hf-reel-type-([a-z]+)/index.html", r.stdout)
        got = m.group(1) if m else ""
    p = os.path.join(tmp, "projects", name, f"hf-reel-type-{got}", "index.html")
    html = open(p, encoding="utf-8").read() if r.returncode == 0 and os.path.exists(p) else ""
    return r, html


def words_in(html, cls):
    """The words shown in clips of one kind (buildwrap = karaoke, capword = snap, tkwrap = takeover)."""
    out = []
    for m in re.finditer(r'<div class="clip"[^>]*><div class="' + cls + r'[^"]*"[^>]*>(.*?)</div></div>', html):
        out += [w.strip().casefold() for w in re.findall(r">([^<>]+)<", m.group(1)) if w.strip()]
    return out


def has(html, kind):
    """Whether a clip of this kind is on the page (the CSS names every kind whatever the page holds)."""
    return {"takeover": '<div class="tkwrap"', "caption": '<div class="capword', "card": 'id="clip-bk0"',
            "hook": '<div id="hookwrap">'}[kind] in html


def dead_lines(html):
    head, _, tail = html.partition("const tl=gsap.timeline({paused:true});")
    ids = set(re.findall(r'id="([^"]+)"', head))
    aims = lambda js: set(re.findall(r'\(\s*"#([A-Za-z0-9_-]+)', js)) | set(re.findall(r'getElementById\("([^"]+)"\)', js))
    return [l for l in tail.split('window.__timelines["')[0].split("\n") if l.strip() and not aims(l) <= ids]


def main():
    base = tempfile.mkdtemp(prefix="reel-type-matching-")
    try:
        # ---- words: any script, keys and keywords normalised like the transcript -------------------------
        tmp = os.path.join(base, "words"); shadow(tmp)
        job(tmp, "Привет всем. Это важная мысль. Спасибо большое.".split(),
            {"caption_mode": "single", "caption_treatments": [{"text": "это важная мысль", "mode": "karaoke"}]})
        r, html = build(tmp)
        check("Russian: builds", r.returncode == 0, r.stderr[-300:])
        check("Russian: only the treated line is karaoke", sorted(words_in(html, "buildwrap")) == sorted(["это", "важная", "мысль"]),
              words_in(html, "buildwrap"))
        check("Russian: the other lines stay snap captions", {"привет", "всем", "спасибо", "большое"} <= set(words_in(html, "capword")),
              words_in(html, "capword"))

        job(tmp, "Todo va a estar bien. Está bien. Seguimos adelante.".split(), {"takeover_keys": ["está bien"]})
        r, html = build(tmp)
        check("accented key: the takeover renders", "takeovers=1" in r.stdout, r.stdout[-200:])
        check("accented key: it is the right line", sorted(words_in(html, "tkwrap")) == ["bien", "está"], words_in(html, "tkwrap"))

        job(tmp, "Please don't stop now. We keep going.".split(), {"takeover_keys": ["don’t stop"], "keywords": ["Going!"]})
        r, html = build(tmp)
        check("curly-quote key: the takeover renders", "takeovers=1" in r.stdout, r.stdout[-200:])
        check("keyword with capitals and punctuation: marked", re.search(r'class="capword kw"[^>]*><span id="cw\d+">going<', html) is not None)

        job(tmp, "Nothing here matches at all.".split(), {"takeover_keys": [""], "keywords": ["—"]})
        try:
            r, html = build(tmp)
            check("an empty key does not hang the build", r.returncode == 0, r.stderr[-200:])
            check("an empty key renders no takeover", "takeovers=0" in r.stdout, r.stdout[-200:])
        except subprocess.TimeoutExpired:
            check("an empty key does not hang the build", False, "timed out")

        # ---- layers: takeovers on their own lane, breakaways on theirs, no dead timeline lines ------------
        plan = {"takeover_keys": ["the whole point"], "hook": ["a short hook"], "hook_end": 2.0,
                "breakaways": [{"at": 4.0, "out": 5.5, "lines": ["a designed", "card"]}]}
        job(tmp, "This is the whole point. Then we keep talking for a while about it. And more words here.".split(), plan)
        r, html = build(tmp)
        tk = re.findall(r'data-track-index="(\d+)"><div class="tkwrap"', html)
        check("takeover stacks sit on lane 5", tk == ["5"], tk)
        _, cap = build(tmp, LAYER="captions")
        check("captions layer holds no takeover", not has(cap, "takeover") and has(cap, "caption"))
        _, tko = build(tmp, LAYER="takeover")
        check("takeover layer holds the takeover and nothing else",
              has(tko, "takeover") and not has(tko, "caption") and not has(tko, "card"))
        _, bk = build(tmp, LAYER="breakaway")
        check("breakaway layer holds the card", has(bk, "card") and not has(bk, "takeover"))
        for layer, h in (("captions", cap), ("takeover", tko), ("breakaway", bk)):
            check(f"{layer} layer has no timeline line aimed at a dropped clip", not dead_lines(h), dead_lines(h)[:2])
        _, hook = build(tmp, LAYER="hook")
        check("hook layer (behind mode) is the hook alone, with no dead lines",
              has(hook, "hook") and not has(hook, "caption") and not dead_lines(hook), dead_lines(hook)[:2])
        _, front = build(tmp, LAYER="front")
        check("front layer (behind mode) is everything but the hook",
              not has(front, "hook") and has(front, "caption") and has(front, "takeover") and not dead_lines(front))
        full_dead = dead_lines(html)
        check("a full build keeps every timeline line", not full_dead, full_dead[:2])
        lp = subprocess.run([sys.executable, os.path.join(tmp, "product", "layer_probe.py"), "qa-job", "Butter"],
                            cwd=tmp, capture_output=True, text=True, env=dict(os.environ, HOME=os.path.join(tmp, "home")))
        check("--list names the takeover truthfully", re.search(r"takeover\s+the full-screen word takeovers", lp.stdout), lp.stdout)
        check("--list names the breakaway card truthfully", re.search(r"breakaway\s+the breakaway card", lp.stdout), lp.stdout)

        # ---- pack: STYLE_PACK, else her saved default, else a refusal ------------------------------------
        r, html = build(tmp, pack=None)
        check("no pack and none saved: the build refuses", r.returncode != 0 and "No style pack chosen" in (r.stdout + r.stderr),
              (r.stdout + r.stderr)[-200:])
        lp = subprocess.run([sys.executable, os.path.join(tmp, "product", "layer_probe.py"), "qa-job"],
                            cwd=tmp, capture_output=True, text=True, env=dict(os.environ, HOME=os.path.join(tmp, "home")))
        check("layer_probe without a pack asks instead of assuming Butter", lp.returncode != 0 and "which style pack" in lp.stderr,
              lp.stderr[-200:])
        tmp2 = os.path.join(base, "saved"); shadow(tmp2, {"default_pack": "Editorial", "default_accent": "#12AB34"})
        job(tmp2, "We keep going with money now.".split(), {"keywords": ["money"]})
        r, html = build(tmp2, pack=None)
        check("her saved default pack is used", "pack=Editorial" in r.stdout, r.stdout[-200:])
        check("her saved accent is used", ".capword.kw{color:#12AB34;}" in html)
        job(tmp2, "We keep going with money now.".split(), {"keywords": ["money"], "accent": "#ABCDEF"})
        r, html = build(tmp2, pack="Butter")
        check("this reel's own accent wins over the saved one", ".capword.kw{color:#ABCDEF;}" in html)
        job(tmp, "We keep going with money now.".split(), {"keywords": ["money"]})
        r, html = build(tmp, pack="Butter")
        sys.path.insert(0, PRODUCT)
        import stylepack
        check("with nothing saved the pack's own accent is used",
              f".capword.kw{{color:{stylepack.load('Butter').get('accent_color')};}}" in html)

        # ---- fonts: a pinned face on a buyer install, and two catalog files both named font.* ------------
        tmp3 = os.path.join(base, "buyer"); shadow(tmp3, drop_fonts=PAID)
        split = {"hook": [], "hook_long": "for the mom who feels like she does not fit", "hook_end": 3.0}
        job(tmp3, "For the mom who feels like she does not fit. We keep going.".split(), split)
        for pack in ("Butter", "Playful"):
            r, html = build(tmp3, pack=pack, HOOK_SPLIT="1")
            fam = re.search(r'class="hkquiet"[^>]*?style="font-family:([A-Za-z0-9]+)', html)
            src = fam and re.search(r"@font-face\{font-family:'" + fam.group(1) + r"';src:url\('([^']+)'\)", html)
            ok = bool(src) and os.path.exists(os.path.join(tmp3, "projects", "qa-job", f"hf-reel-type-{pack.lower()}", src.group(1)))
            check(f"{pack} buyer without the paid face: the eyebrow's font file is really there", ok, (fam, src))
        # CapCut's catalog cache lives under ~/Movies for both Mac installs (capcut_userfonts._CATALOG): the
        # capcut.com download writes there, and the App Store copy's sandbox Movies folder is a link to it.
        # This fixture used to put the cache inside the sandbox folder as a real directory, a layout no
        # install has and the resolver no longer reads, so the caption quietly fell back to its stand-in.
        chome = os.path.join(tmp3, "capcut-home")
        cache = os.path.join(chome, "Movies", "CapCut", "User Data", "Cache", "effect")
        sandbox = os.path.join(chome, "Library", "Containers", "com.lemon.lvoverseas", "Data")
        os.makedirs(sandbox)
        os.symlink(os.path.join("..", "..", "..", "..", "Movies"), os.path.join(sandbox, "Movies"))
        have = {n for n in PAID if os.path.exists(os.path.join(ROOT, "assets", "fonts", n))}
        if {"SoupDuJour.ttf", "UglyDaveAlternates.otf"} <= have:
            for rid, n, ext in (("7001", "SoupDuJour.ttf", ".ttf"), ("7002", "UglyDaveAlternates.otf", ".otf")):
                os.makedirs(os.path.join(cache, rid, "x"))
                shutil.copy(os.path.join(ROOT, "assets", "fonts", n), os.path.join(cache, rid, "x", "font" + ext))
            r, html = build(tmp3, pack="Playful", home=os.path.join(tmp3, "capcut-home"), HOOK_SPLIT="1")
            faces = re.findall(r"@font-face\{font-family:'([^']+)';src:url\('([^']+)'\)", html)
            fams = [f for f, _s in faces]
            check("catalog fonts that share a file name get separate families", len(fams) == len(set(fams)) and len(faces) >= 2, faces)
            from PIL import ImageFont
            cap = re.search(r"\.capword\{[^}]*font-family:([A-Za-z0-9]+)", html)
            capfile = dict(faces).get(cap.group(1)) if cap else None
            real = capfile and ImageFont.truetype(os.path.join(tmp3, "projects", "qa-job", "hf-reel-type-playful", capfile), 20).getname()[0]
            check("the caption renders in her CapCut copy of its own face (Ugly Dave)", real == "Ugly Dave", real)
            quiet = re.search(r'class="hkquiet"[^>]*?style="font-family:([A-Za-z0-9]+)', html)
            check("the eyebrow resolves from her CapCut copy of Ugly Dave",
                  quiet and cap and quiet.group(1) == cap.group(1), (quiet and quiet.group(1), cap and cap.group(1)))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if fails:
        print(f"test_reel_type_matching: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_reel_type_matching: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
