#!/usr/bin/env python3
"""Guards: a carousel or story can carry photos she picks on her page, from her favorites, her inbox or her computer.

  request   kit_request keeps her photos in her order, only files in her favorites or inbox (a path, a file outside
            them, a non-image or a repeat is dropped), next to the snaps she ticked
  frames    the carousel tool reads those photos back, in her order, skipping one that has since gone missing

Run: python3 product/tests/test_kit_photos.py
"""
import importlib.util, json, os, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}  -- {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="kit-photos-")
    keep_fav, keep_root = ve._favorites, ve.ROOT
    try:
        fav = os.path.join(tmp, "favorites"); os.makedirs(os.path.join(fav, "photos")); os.makedirs(os.path.join(tmp, "inbox"))
        for p in ("photos/beach.jpg", "photos/notes.txt"):
            open(os.path.join(fav, p), "wb").write(b"x")
        open(os.path.join(tmp, "inbox", "kids.png"), "wb").write(b"x")
        open(os.path.join(tmp, "secret.jpg"), "wb").write(b"x")
        ve._favorites = lambda: fav
        ve.ROOT = tmp
        reel = os.path.join(tmp, "projects", "the-reel"); os.makedirs(os.path.join(reel, "review"))
        req = ve.kit_request(reel, "carousel", [], ["inbox:kids.png", "photos/beach.jpg", "photos/notes.txt",
                                                     "../secret.jpg", "/etc/hosts", "photos/beach.jpg"])
        ids = [p["id"] for p in req["photos"]]
        check("request: her photos in her order, favorites and inbox only, no repeats", ids == ["inbox:kids.png", "photos/beach.jpg"], ids)
        saved = json.load(open(os.path.join(reel, "review", "kit-request.json"), encoding="utf-8"))
        check("request: saved for the chat with each file's place", [os.path.basename(p["path"]) for p in saved["photos"]] == ["kids.png", "beach.jpg"], saved)
        check("request: a photo-less request still works", ve.kit_request(reel, "story", [], None)["photos"] == [])

        ve.kit_request(reel, "carousel", [], ["photos/beach.jpg", "inbox:kids.png"])
        spec = importlib.util.spec_from_file_location("carousel", os.path.join(ROOT, "workflows", "carousel", "carousel.py"))
        car = importlib.util.module_from_spec(spec); spec.loader.exec_module(car)
        from pathlib import Path
        car.ENGINE = Path(tmp)
        got = [p.name for p in car._kit_photos("the-reel")]
        check("frames: the carousel reads her photos back in her order", got == ["beach.jpg", "kids.png"], got)
        os.remove(os.path.join(tmp, "inbox", "kids.png"))
        got = [p.name for p in car._kit_photos("the-reel")]
        check("frames: a photo that's gone since is skipped, never a crash", got == ["beach.jpg"], got)
    finally:
        ve._favorites, ve.ROOT = keep_fav, keep_root
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_kit_photos: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f[:400])
        return 1
    print(f"test_kit_photos: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
