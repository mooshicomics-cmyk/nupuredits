#!/usr/bin/env python3
"""Guards: Cover a face (product/face_cover.py + the visual editor's Visuals tab).

  covers    only the faces she covered come back, and only for the faces the engine found for THIS cut of footage
  fixes     her drags move a cover exactly the way the page draws them (page fcFixAt == face_cover._fix_at)
  time      the export finds each frame's box through her cut's own pieces (cut seconds -> preview seconds)
  bottom    the cover is the bottom layer: in the footage at Finish (before her filter and any cutout), and under her
            looks on the page; nothing moves out of its way
  page      the tool is on the Visuals tab, beside Filter, and saves through the editor server
  picture   an emoji or sticker cover is laid as the PNG the page drew (same square on both sides)

Run: python3 product/tests/test_face_cover.py
"""
import json, os, re, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import face_cover as fc  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


# ── covers: only hers, only for the faces found on this footage ──
tmp = tempfile.mkdtemp(prefix="face-cover-")
try:
    rv = os.path.join(tmp, "review")
    os.makedirs(rv)
    found = {"made_for": "abc", "fps": 30, "frames": 3, "me": 1,
             "faces": [{"id": 1, "track": [[.5, .5, .1, .1, 0]] * 3}, {"id": 2, "track": [[.3, .6, .08, .08, 2]] * 3}]}
    json.dump(found, open(os.path.join(rv, "faces.json"), "w", encoding="utf-8"))
    mine = {"made_for": "abc", "faces": {"1": {"on": False, "kind": "emoji"}, "2": {"on": True, "kind": "blur", "size": 1.7}}}
    json.dump(mine, open(os.path.join(rv, "face-cover.json"), "w", encoding="utf-8"))
    got = fc.covers_on(tmp)
    check([c["id"] for c in got] == [2] and got[0]["kind"] == "blur" and got[0]["track"] == found["faces"][1]["track"],
          f"covers: only the covered face, with its track, got {got}")
    s1 = fc.signature(tmp)
    mine["faces"]["2"]["fixes"] = {"1": [0.01, 0.0]}
    json.dump(mine, open(os.path.join(rv, "face-cover.json"), "w", encoding="utf-8"))
    check(fc.signature(tmp) != s1, "covers: a drag she made should make the covered footage again")
    mine["made_for"] = "older-footage"
    json.dump(mine, open(os.path.join(rv, "face-cover.json"), "w", encoding="utf-8"))
    check(fc.covers_on(tmp) == [], "covers: picks made for other footage must never cover these faces")
    os.remove(os.path.join(rv, "faces.json"))
    check(fc.covers_on(tmp) == [], "covers: no faces found = nothing covered")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── fixes: the export moves a cover exactly as the page drew it ──
fx = {"30": [0.1, 0.0], "60": [0.3, 0.2]}
check(fc._fix_at(fx, 30) == (0.1, 0.0) or list(fc._fix_at(fx, 30)) == [0.1, 0.0], "fixes: on her keyframe, her exact offset")
mid = fc._fix_at(fx, 45)
check(abs(mid[0] - 0.2) < 1e-9 and abs(mid[1] - 0.1) < 1e-9, f"fixes: halfway between two drags, halfway between, got {mid}")
check(fc._fix_at(fx, 60 + 30) == tuple(fx["60"]) or list(fc._fix_at(fx, 90)) == fx["60"], "fixes: held a second past her last drag")
check(fc._fix_at(fx, 60 + 30 + 15) == (0.0, 0.0), "fixes: eased away half a second after the hold")
check(fc._fix_at({}, 10) == (0.0, 0.0), "fixes: no drags, no offset")
page = open(os.path.join(PRODUCT, "visual-editor", "editor.html"), encoding="utf-8").read()
m = re.search(r"SPAN = fps \* 3, FADE = fps \* \.5, HOLD = fps", page)
check(bool(m), "fixes: the page's fcFixAt must keep the export's 3 s span, half-second fade and 1 s hold")

# ── time: cut seconds -> preview seconds through her cut's pieces ──
at = fc._cut_to_preview([{"s": 2.0, "e": 4.0}, {"s": 10.0, "e": 11.5}])
check(abs(at(0.0) - 2.0) < 1e-9 and abs(at(1.5) - 3.5) < 1e-9, "time: inside the first piece")
check(abs(at(2.25) - 10.25) < 1e-9, f"time: the second piece starts where the first ends, got {at(2.25)}")
check(abs(at(99) - 11.5) < 1e-9, "time: past the end holds the last frame")

# ── bottom: in the footage before everything else, under her looks on the page ──
fsrc = open(os.path.join(PRODUCT, "finish.py"), encoding="utf-8").read()
i_cov, i_beh = fsrc.find("base = _covered_base(jd, base)"), fsrc.find("_behind_cutouts(jd, base, under")
check(i_cov > 0 and i_beh > i_cov, "bottom: her covered footage must be made before the cutout of her for a look behind her")
check(i_cov < fsrc.find("graded = _graded_base(jd, base"), "bottom: covers go in before her filter (the filter grades the covered footage)")
check('cmd += ["--base", base]' in fsrc, "bottom: the CapCut route must split her covered footage, not the uncovered cut")
hsrc = open(os.path.join(PRODUCT, "capcut_handoff.py"), encoding="utf-8").read()
check("if not overlay and not layers and not a.no_overlay:" in hsrc,
      "bottom: a CapCut export with no looks yet (covers or a filter only) must build her cut as the draft, not refuse")
check('"review/face-cover.json"' in fsrc, "bottom: a cover change must make an older export out of date")
check(page.find('id="faceLayer"') < page.find('id="lookStack"'), "bottom: on the page the cover layer sits under her looks")
check(".facelayer{position:absolute; pointer-events:none; z-index:1" in page, "bottom: the cover layer shares the looks' z-index, so DOM order puts it under")

# ── opt-in: nothing covered until she taps a face; every video's faces in one list; one default cover ──
check(': { on: false, kind: "emoji", emoji, size: 1.65' in page, "opt-in: a face she hasn't tapped must never start covered")
check("FC.found.me" not in page and '"me"' not in open(os.path.join(PRODUCT, "face_cover.py"), encoding="utf-8").read(),
      "opt-in: the engine must not guess which face is hers (nothing is decided for her)")
check('"clips": [c["name"] for c in clips]' in open(os.path.join(PRODUCT, "face_cover.py"), encoding="utf-8").read()
      and "Video ${ci + 1}" in page, "opt-in: faces from every video are listed together, grouped by video")
check("const emoji = FC_EMOJI[0];" in page, "opt-in: every face starts with the same cover, so one child looks the same in every video")

# ── page: on Visuals, beside Filter, saved through the server ──
check(re.search(r'id="filterBtn"[^>]*>.*?</button><button class="tool" id="faceBtn" data-for="visuals"', page) is not None,
      "page: Cover a face sits on the Visuals toolbar, right after Filter")
check('$("heroTools").hidden = !on && phase === "cut"' in page, "page: Filter and Cover a face show once her cut is locked, looks or not")
srv = open(os.path.join(PRODUCT, "visual_editor_server.py"), encoding="utf-8").read()
check('"/face-find", "/face-cover"' in srv, "page: the server must accept the face search and her cover picks")
check('f"face-cover-{fid}.png' in srv and 'f"face-cover-{c[\'id\']}.png"' in open(os.path.join(PRODUCT, "face_cover.py"), encoding="utf-8").read(),
      "picture: the page's cover PNG and the export's must be the same file")

# ── picture: same square on both sides ──
m = re.search(r"const FC_SPAN = ([\d.]+);", page)
check(m and float(m.group(1)) == fc.STICKER_SPAN, "picture: the page and the export must draw a sticker over the same square")

if fc.np is not None:                                   # the draw itself, where numpy is here (uv run brings it)
    import numpy as np
    img = np.full((100, 100, 3), 50, np.uint8)
    st = np.zeros((40, 40, 4), np.uint8); st[..., 2] = 255; st[..., 3] = 255
    fc._draw(img, "img", st, 50, 50, 10)
    check(tuple(img[50, 50]) == (0, 0, 255) and tuple(img[2, 2]) == (50, 50, 50), "picture: a sticker lands on the face and nowhere else")
    img = np.zeros((100, 100, 3), np.uint8); img[:, 50:] = 255
    fc._draw(img, "blur", None, 50, 50, 20)
    check(0 < int(img[50, 50, 0]) < 255 and int(img[2, 2, 0]) == 0, "picture: a blur softens the face and leaves the rest alone")

if fails:
    print("test_face_cover: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_face_cover: all {n} checks passed")
