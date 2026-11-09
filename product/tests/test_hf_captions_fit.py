#!/usr/bin/env python3
"""build-hf-captions.py (the medium route's caption overlays) sizes type to readable floors, fits a long word or
a long takeover on its own, carries HER accent, and records the takeovers that cover her by design.

Each case builds a real composition in a private engine root (product/ and assets/ linked file by file, her
user-style.json written per case, projects/ its own), HOME pointed at an empty folder. What it pins:

  floors     the width fit shrank ONE shared size per mode down to 40px, so one long word took every caption
             of the reel below the legibility floor, and a plan's caption_size was never floored at all
  per word   a word too wide for the safe width now gets its own size; everything else keeps the pack's size
  stacks     a takeover (one word per line) is sized as a whole to fit between the platform bands
  accent     her saved default accent was ignored and the fallback was the creator's personal butter
  owns       the full-screen takeovers are written to owns-screen.json (beside the composition and in the job
             folder) whatever HF_MODE is built, so the subject check waives them and nothing else
  note       the composition tells whoever renders it to go through reel_render.py, not around the gate

Run: python3 product/tests/test_hf_captions_fit.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import safe_zones, stylepack

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def shadow(tmp, user_style=None):
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
    os.symlink(os.path.join(ROOT, "assets"), os.path.join(tmp, "assets"))
    os.makedirs(os.path.join(tmp, "home"))


def job(tmp, sentences, plan, name="qa-job"):
    d = os.path.join(tmp, "projects", name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    t, beats = 0.3, []
    for s in sentences:
        ws = []
        for w in s.split():
            ws.append({"w": w, "t": round(t, 2), "e": round(t + 0.3, 2)})
            t += 0.4
        beats.append({"words": ws})
        t += 0.5
    with open(os.path.join(d, "edit-timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"beats": beats}, fh)
    with open(os.path.join(d, "caption-plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh)
    return beats


def build(tmp, pack="Butter", mode="", name="qa-job"):
    env = {k: v for k, v in os.environ.items() if k not in ("STYLE_PACK", "HF_MODE", "SIZE_SCALE")}
    env.update({"JOB": name, "STYLE_PACK": pack, "HF_MODE": mode, "HOME": os.path.join(tmp, "home")})
    r = subprocess.run([sys.executable, os.path.join(tmp, "product", "build-hf-captions.py")], cwd=tmp, env=env,
                       capture_output=True, text=True, timeout=120)
    p = os.path.join(tmp, "projects", name, "hf-captions", "index.html")
    return r, (open(p, encoding="utf-8").read() if r.returncode == 0 and os.path.exists(p) else "")


def css_px(html, sel):
    m = re.search(re.escape(sel) + r"\{[^}]*?font-size:(\d+)px", html)
    return int(m.group(1)) if m else None


def owns(tmp, where, name="qa-job"):
    p = os.path.join(tmp, "projects", name, *(["hf-captions"] if where == "comp" else []), "owns-screen.json")
    return json.load(open(p, encoding="utf-8"))["windows"] if os.path.exists(p) else None


def main():
    base = tempfile.mkdtemp(prefix="hf-captions-fit-")
    try:
        tmp = os.path.join(base, "e"); shadow(tmp)
        px = lambda pack, role: max(20, round(stylepack.element(pack, role)["size"] * 6.0))

        # ---- floors ------------------------------------------------------------------------------------
        job(tmp, ["this is a normal line.", "and here is another one."], {"caption_size": 30})
        r, html = build(tmp)
        check("a plan's caption_size cannot take captions below the pack's own size",
              css_px(html, ".cap") == max(px("Butter", "caption"), safe_zones.MIN_PX["caption"]), (css_px(html, ".cap"), r.stderr[-200:]))
        job(tmp, ["this is a normal line.", "and here is another one."], {})
        r, html = build(tmp, pack="Playful")
        check("every pack's snap captions are at least the legibility floor",
              (css_px(html, ".cap") or 0) >= safe_zones.MIN_PX["caption"], css_px(html, ".cap"))

        # ---- per word ----------------------------------------------------------------------------------
        job(tmp, ["this is supercalifragilisticexpialidocious and fine.", "short words only here."], {})
        r, html = build(tmp)
        shared = css_px(html, ".cap")
        own = re.findall(r'<div class="clip cap[^"]*" style="font-size:(\d+)px"[^>]*>([^<]+)</div>', html)
        check("the shared caption size stays the pack's", shared == px("Butter", "caption"), shared)
        check("only the long word is sized on its own", [w for _p, w in own] == ["supercalifragilisticexpialidocious"], own)
        check("the long word keeps at least the legibility floor", own and all(int(p) >= safe_zones.MIN_PX["caption"] for p, _w in own), own)

        # ---- stacks + owns-screen ------------------------------------------------------------------------
        long_line = "can i tell you something that i have noticed about us"
        beats = job(tmp, ["we start here.", long_line + ".", "and we end here."], {"takeover_keys": ["something that i have noticed"]})
        r, html = build(tmp)
        stack = re.search(r'<div class="clip take-wrap"[^>]*><div class="inner"( style="font-size:(\d+)px")?>(.*?)</div></div>', html)
        lh = float(re.search(r"\.take-wrap \.inner\{[^}]*?line-height:([\d.]+)", html).group(1))
        tk = css_px(html, ".take-wrap .inner")
        size = int(stack.group(2)) if stack and stack.group(2) else tk
        spans = re.findall(r'<span id="s\d+w\d+"(?: class="kwy")?(?: style="font-size:(\d+)px")?>', stack.group(3)) if stack else []
        height = sum(lh * (int(p) if p else size) for p in spans)
        cy = round(960 - stylepack.element("Butter", "takeover")["y"] * 960)
        room = 2 * min(cy - safe_zones.TOP, safe_zones.BOTTOM - cy)
        check("the takeover stack fits between the platform bands", stack and height <= room + 1, (height, room, size))
        check("no takeover word goes below its legibility floor",
              spans and all((int(p) if p else size) >= safe_zones.MIN_PX["takeover"] for p in spans), spans)
        want = [[beats[1]["words"][0]["t"], round(beats[1]["words"][-1]["e"] + 1.0, 3)]]
        check("owns-screen.json beside the composition holds the takeover", owns(tmp, "comp") == want, owns(tmp, "comp"))
        check("owns-screen.json in the job folder holds the takeover", owns(tmp, "job") == want, owns(tmp, "job"))
        r, html1 = build(tmp, mode="single")
        check("a single-style overlay writes the same takeover windows", owns(tmp, "job") == want and owns(tmp, "comp") == want,
              owns(tmp, "job"))
        check("the composition points at the gated render path",
              "reel_render.py render" in html and "`hyperframes render` directly" not in html)

        # ---- accent ------------------------------------------------------------------------------------
        job(tmp, ["this is about money today."], {"keywords": ["money"]})
        r, html = build(tmp)
        check("with nothing saved the pack's own accent is used",
              f".cap.kw{{color:{stylepack.load('Butter').get('accent_color')};}}" in html, re.findall(r"\.cap\.kw\{[^}]*\}", html))
        tmp2 = os.path.join(base, "s"); shadow(tmp2, {"default_accent": "#12AB34"})
        job(tmp2, ["this is about money today."], {"keywords": ["money"]})
        r, html = build(tmp2)
        check("her saved default accent is used", ".cap.kw{color:#12AB34;}" in html, re.findall(r"\.cap\.kw\{[^}]*\}", html))
        job(tmp2, ["this is about money today."], {"keywords": ["money"], "accent": "#ABCDEF"})
        r, html = build(tmp2)
        check("this reel's own accent wins", ".cap.kw{color:#ABCDEF;}" in html, re.findall(r"\.cap\.kw\{[^}]*\}", html))
        src = open(os.path.join(PRODUCT, "build-hf-captions.py"), encoding="utf-8").read()
        check("no personal butter fallback in the builder", "#FAE38E" not in src.upper())
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if fails:
        print(f"test_hf_captions_fit: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_hf_captions_fit: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
