#!/usr/bin/env python3
"""A voiceover reel gets its fonts the way every other build does, on a buyer's machine too.

THE BUG THIS EXISTS FOR. vo-build.py looked for a pack's fonts in the shipped style-packs.json and in
assets/fonts/ and nowhere else. The licensed faces are not bundled with the engine, so on a buyer's
machine the Playful pack found no caption font at all and stopped with "no usable font for pack Playful"
AFTER the whole picture had been rendered, a pack the buyer built herself (_local/style-packs.json) died on
a KeyError traceback, and Editorial's script takeover quietly turned into its caption font. Now it asks
product/stylepack.py, the resolver every other build uses (her own packs, the fonts she added in CapCut, and
the pack's own stand-in when a face is not on the machine), and it asks before the picture is built.

How it is checked: a throwaway engine with the real style packs and the bundled fonts, once with every font
present (the creator's machine: each pack must resolve to exactly its own files, as before) and once
without the faces that do not ship (a buyer's machine). HOME points at an empty folder, so no real CapCut
font library is ever read. No render: pack_fonts is called directly, plus one vo-build run that must stop
before its first step.

Run: python3 product/tests/test_vo_fonts.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MODULES = ("vo-build.py", "stylepack.py", "capcut_userfonts.py", "capcut_font_doctor.py", "safe_zones.py",
           "learned.py", "video_encoder.py", "hdr.py", "text_effects.py")
# the faces the buyer bundle leaves out (licensed or personal), as make-ship excludes them
NOT_SHIPPED = ("Prosecco.ttf", "ProseccoandBaguette.ttf", "HFOperaCake.ttf", "Geomanist-Regular.otf",
               "SoupDuJour.ttf", "SoupDuJourHollow.ttf", "Bloop.ttf", "UglyDaveAlternates.otf", "ZY-Modern.ttf")
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def engine(buyer):
    t = tempfile.mkdtemp()
    os.makedirs(os.path.join(t, "product", "creative-vault"))
    for m in MODULES:
        if os.path.exists(os.path.join(ROOT, "product", m)):
            shutil.copy(os.path.join(ROOT, "product", m), os.path.join(t, "product", m))
    shutil.copy(os.path.join(ROOT, "product", "creative-vault", "style-packs.json"),
                os.path.join(t, "product", "creative-vault", "style-packs.json"))
    fonts = os.path.join(t, "assets", "fonts")
    os.makedirs(fonts)
    for f in os.listdir(os.path.join(ROOT, "assets", "fonts")):
        if buyer and (f in NOT_SHIPPED or f.startswith(("Advercase-", "Helvetica"))):
            continue
        shutil.copy(os.path.join(ROOT, "assets", "fonts", f), os.path.join(fonts, f))
    # a pack of her own, built from bundled faces, the way the style-pack skill writes one
    os.makedirs(os.path.join(t, "_local"))
    own = {"packs": {"Mine": {"fonts": {"main": "Inter", "accent": "Inter", "caption": "Poppins"}, "elements": {
        "headline": {"font": "Inter", "file": "Inter-Black.otf", "case": "lower"},
        "takeover": {"font": "Inter", "file": "Inter-Black.otf", "case": "upper"},
        "caption": {"font": "Poppins", "file": "Poppins-SemiBold.ttf", "case": "lower"},
        "thought_bubble": {"font": "Poppins", "file": "Poppins-SemiBold.ttf", "case": "lower"},
        "accent_caption": {"font": "Poppins", "file": "Poppins-SemiBold.ttf", "case": "lower"}}}}}
    with open(os.path.join(t, "_local", "style-packs.json"), "w", encoding="utf-8") as fh:
        json.dump(own, fh)
    return t


PROBE = r'''
import importlib.util, json, os, sys
root = sys.argv[1]
spec = importlib.util.spec_from_file_location("vo_build", os.path.join(root, "product", "vo-build.py"))
vb = importlib.util.module_from_spec(spec); spec.loader.exec_module(vb)
out = {}
for pack in sys.argv[2:]:
    try:
        b, d, u = vb.pack_fonts(pack)
        out[pack] = [os.path.basename(b) if b else None, os.path.basename(d) if d else None, u,
                     bool(b and os.path.exists(b)), bool(d and os.path.exists(d))]
    except SystemExit as e:
        out[pack] = ["exit", str(e.code)]
print("RESULT " + json.dumps(out))
'''


def resolve(t, packs):
    r = subprocess.run([sys.executable, "-c", PROBE, t, *packs], capture_output=True, text=True,
                       env=dict(os.environ, HOME=t), cwd=t)
    line = next((l for l in r.stdout.splitlines() if l.startswith("RESULT ")), None)
    return (json.loads(line[7:]) if line else {}), r.stdout + r.stderr


def main():
    with open(os.path.join(ROOT, "product", "creative-vault", "style-packs.json"), encoding="utf-8") as fh:
        shipped = json.load(fh)["packs"]
    packs = list(shipped)

    t = engine(buyer=False)
    try:
        got, out = resolve(t, packs)
        for p in packs:
            el = shipped[p]["elements"]
            want = [el["caption"]["file"], el["takeover"]["file"], el["takeover"].get("case") == "upper"]
            check(f"every font present: {p} resolves to exactly its own caption + takeover files",
                  got.get(p, [None])[:3] == want, f"got {got.get(p)} want {want}")
    finally:
        shutil.rmtree(t, ignore_errors=True)

    t = engine(buyer=True)
    try:
        got, out = resolve(t, packs + ["Mine", "NoSuchPack"])
        for p in packs:
            g = got.get(p) or [None] * 5
            check(f"buyer machine: {p} resolves to fonts that exist", g[0] != "exit" and g[3] and g[4], str(g))
            el = shipped[p]["elements"]
            for i, kind in ((0, "caption"), (1, "takeover")):
                if el[kind]["file"] in NOT_SHIPPED and el[kind].get("fallback_file"):
                    check(f"buyer machine: {p} {kind} uses the pack's own stand-in ({el[kind]['fallback_file']})",
                          g[i] == el[kind]["fallback_file"], str(g))
        check("buyer machine: a pack she built herself (_local) resolves", (got.get("Mine") or [None])[:2]
              == ["Poppins-SemiBold.ttf", "Inter-Black.otf"], str(got.get("Mine")))
        nsp = got.get("NoSuchPack") or []
        check("an unknown pack stops with a plain message, not a traceback",
              nsp[:1] == ["exit"] and "unknown style pack" in (nsp[1] if len(nsp) > 1 else ""), str(nsp))

        # vo-build stops on it BEFORE step 1 (it used to render the whole picture first)
        jd = os.path.join(t, "projects", "j")
        os.makedirs(os.path.join(jd, "audio"))
        open(os.path.join(jd, "audio", "vo.wav"), "wb").close()
        with open(os.path.join(jd, "vo-grid.json"), "w", encoding="utf-8") as fh:
            json.dump({"duration": 1.0, "phrases": [{"text": "hi", "a": 0.1, "b": 0.5,
                                                     "words": [{"w": "hi", "a": 0.1, "b": 0.5}]}]}, fh)
        with open(os.path.join(jd, "shot-plan.json"), "w", encoding="utf-8") as fh:
            json.dump({"burst": [], "holds": [{"path": "/nowhere.mp4", "in": 0, "out": 1}]}, fh)
        r = subprocess.run([sys.executable, os.path.join(t, "product", "vo-build.py"), "--job", "j", "--pack",
                            "NoSuchPack"], capture_output=True, text=True, env=dict(os.environ, HOME=t), cwd=t)
        check("vo-build stops on a pack problem before it renders anything",
              r.returncode != 0 and "[1/3]" not in r.stdout and "unknown style pack" in r.stderr
              and "Traceback" not in r.stderr, (r.stdout + r.stderr)[-500:])

        # her own pack file cut off mid-write: the shipped packs still build (as they did before this read
        # her packs at all), and it says why hers are missing
        with open(os.path.join(t, "_local", "style-packs.json"), "w", encoding="utf-8") as fh:
            fh.write('{"packs": {"Mine": {"elements": {"caption": {"file": "Poppins')
        got, out = resolve(t, ["Butter"])
        check("a damaged pack file of her own does not stop a shipped pack", (got.get("Butter") or [None])[:2]
              == ["Inter-SemiBold.ttf", "Inter-Black.otf"] and "will not read" in out and "Traceback" not in out,
              out[-400:])
    finally:
        shutil.rmtree(t, ignore_errors=True)

    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
