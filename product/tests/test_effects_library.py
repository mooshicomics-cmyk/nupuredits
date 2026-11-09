#!/usr/bin/env python3
"""Guards: the Effects Library is one page with every effect, current with the pinned HyperFrames, and her hearts
are never lost.

  one page     one Effects tab holds everything (no second "More effects" tab to miss)
  pinned       the HyperFrames catalog on the page is from the version product.json pins (a HyperFrames update
               refreshes it: dev-tools/build-catalog.py)
  placed       every catalog piece sits in one of the page's categories (no junk drawer)
  stills       every still the page points at is in product/library-stills/, and none are left over
  grades       the color-grade tiles use the export's exact color math (product/video_grade.py PREVIEW_MATRIX)
  hearts       a heart saves to favorites/effects.json and reads back; an unreadable file is never overwritten
  updates      no update touches favorites/effects.json

Run: python3 product/tests/test_effects_library.py
"""
import importlib.util, json, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import video_grade as vg  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok    " if cond else "  FAIL  ") + name + ("" if cond else f"  ({detail})"))
    if not cond:
        fails.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


page = open(os.path.join(PRODUCT, "effects-library.html"), encoding="utf-8").read()
pin = json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8"))["hyperframes"]

check("one page: there is no separate More effects tab", 'data-tab="catalog"' not in page)
check("one page: the Effects tab carries the category rail", 'id="cx-rail"' in page and 'id="panel-effects"' in page)

m = re.search(r"/\* CATALOG:BEGIN[^*]*\*/var CATALOG=(.*?);/\* CATALOG:END \*/", page, re.S)
check("pinned: the page carries the catalog", bool(m))
data = json.loads(m.group(1)) if m else {"pin": "", "items": []}
check("pinned: the catalog is from the HyperFrames version product.json pins", data["pin"] == pin,
      f"page {data['pin']}, product.json {pin}; run dev-tools/build-catalog.py")

fam = re.search(r"var CX_FAMILIES=\[(.*?)\n  \];", page, re.S)
cats = set(re.findall(r'\["([a-z0-9-]+)","[^"]+","', fam.group(1))) if fam else set()
unplaced = sorted(r[0] for r in data["items"] if r[9] not in cats)
check("placed: every catalog piece sits in one of the page's categories", bool(cats) and not unplaced, ", ".join(unplaced[:8]))

stills_dir = os.path.join(PRODUCT, "library-stills")
missing = sorted(r[7] for r in data["items"] if r[7].startswith("library-stills/")
                 and not os.path.exists(os.path.join(PRODUCT, r[7])))
check("stills: every still the page points at ships", not missing, ", ".join(missing[:6]))
names = {r[0] for r in data["items"]}
extra = sorted(f for f in os.listdir(stills_dir) if f.endswith(".jpg") and f[:-4] not in names) if os.path.isdir(stills_dir) else []
check("stills: none left over from pieces no longer in the catalog", not extra, ", ".join(extra[:6]))

gm = re.search(r"var GRADE_MATRIX=(\{.*?\}), GRADE=\{\};", page)
check("grades: the library carries the grade matrices", bool(gm))
if gm:
    check("grades: they are exactly the export's color math", json.loads(gm.group(1)) == vg.PREVIEW_MATRIX)

srv = load(os.path.join(ROOT, "scripts", "library-server.py"), "library_server")
with tempfile.TemporaryDirectory() as tmp:
    srv.FAVS = os.path.join(tmp, "favorites", "effects.json")
    check("hearts: none saved yet reads as no file", srv.read_favorites() == ([], False))
    srv.write_favorites(["typed-prompt", "karaoke", "typed-prompt", ""])
    check("hearts: saved hearts read back, once each", srv.read_favorites() == (["karaoke", "typed-prompt"], True))
    open(srv.FAVS, "w", encoding="utf-8").write("{not json")
    check("hearts: an unreadable file is reported as existing, so the page never overwrites it with nothing",
          srv.read_favorites() == ([], True))

au = load(os.path.join(ROOT, "scripts", "apply-update.py"), "apply_update")
check("updates: no update touches favorites/effects.json", au.is_protected("favorites/effects.json"))

print(f"\n{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
