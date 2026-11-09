#!/usr/bin/env python3
"""Guard: one of her designs saved under more than one pack's lookbook is drawn from the right copy (a buyer,
2026-10-26). The same design id sat in a shipped pack's lookbook and in her own pack's lookbook (where every edit
landed), and her reel was on a third pack with no entry of its own. design_home() took whichever pack folder sorted
first, so every redraw used the untouched copy and her edits never showed.

  order       not the order the folders sort in: the copy she changed last wins, whatever its pack is called
  listed      a copy its pack's lookbook really lists beats a stray folder with no entry
  own pack    the reel's own pack, when it keeps the design, is used directly
  stale       a drawing records the copy it came from, so an edit to that copy draws it again on a Swap

Run: python3 product/tests/test_design_home_pack.py   (or python3 -m pytest product/tests/test_design_home_pack.py -q)
"""
import json, os, shutil, sys, tempfile, time

os.environ.setdefault("REE_EDITOR", "1")                      # guards for an engine with the editor on
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)    # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lookbook  # noqa: E402

LOOK = "my-hook-accent-draft"


class _Root:
    """A throwaway engine root for lookbook (its _local/lookbooks/ only)."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="design-home-")
        self.old = lookbook.ROOT
        lookbook.ROOT = self.tmp
        os.makedirs(os.path.join(self.tmp, "_local", "lookbooks"))
        return self

    def __exit__(self, *a):
        lookbook.ROOT = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def design(self, pack, when, listed=True, marker=None):
        d = lookbook.design_dir(pack, LOOK)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(f"<html><!-- {marker or pack} --></html>")
        json.dump({"kind": "Hook", "slots": ["text"]}, open(os.path.join(d, "design.json"), "w", encoding="utf-8"))
        for f in ("index.html", "design.json"):
            os.utime(os.path.join(d, f), (when, when))
        if listed:
            book = lookbook._read_book(pack)
            book["looks"].append({"id": LOOK, "name": "Hook, accent (draft)", "design": True, "kind": "Hook"})
            lookbook._write_book(pack, book)


def test_edited_copy_wins_not_alphabetical_first():
    now = time.time()
    with _Root() as r:
        r.design("Editorial", now - 3600)                     # the untouched copy, sorts first
        r.design("Studio Editorial", now)                     # her own pack's copy, where the edits landed
        look = lookbook.find(LOOK, "Studio")                  # her reel is on a third pack with no entry
        assert look.get("home") == "Studio Editorial", look.get("home")
        assert lookbook.design_home(LOOK, "Studio") == "Studio Editorial"


def test_order_follows_the_edit_not_the_name():
    now = time.time()
    with _Root() as r:
        r.design("Editorial", now)                            # this time she changed the copy that sorts first
        r.design("Studio Editorial", now - 3600)
        assert lookbook.find(LOOK, "Studio").get("home") == "Editorial"


def test_listed_copy_beats_a_stray_folder():
    now = time.time()
    with _Root() as r:
        r.design("Editorial", now - 3600)
        r.design("Another", now, listed=False)                # a newer folder its lookbook never listed
        assert lookbook.design_home(LOOK, "Studio") == "Editorial"
        assert lookbook.find(LOOK, "Studio").get("home") == "Editorial"


def test_the_reels_own_pack_is_used_directly():
    now = time.time()
    with _Root() as r:
        r.design("Editorial", now)
        r.design("Studio", now - 3600)                        # older, but it is the reel's own pack
        assert lookbook.design_home(LOOK, "Studio") == "Studio"
        assert not lookbook.find(LOOK, "Studio").get("home")  # found in its own lookbook: no other home
        assert lookbook.design_home("not-hers", "Studio") is None


def test_a_swap_sees_an_edit_to_the_copy_it_was_drawn_from():
    import visual_editor as ve
    now = time.time()
    with _Root() as r:
        r.design("Editorial", now - 7200)
        r.design("Studio Editorial", now - 3600)
        home = lookbook.find(LOOK, "Studio")["home"]
        src = lookbook.design_dir(home, LOOK)
        out = os.path.join(r.tmp, "drawn")
        page = os.path.join(out, "hf-reel-type-studio")
        os.makedirs(page)
        open(os.path.join(page, "index.html"), "w", encoding="utf-8").write("<html></html>")
        rec = {"look": LOOK, "pack": "Studio", "home": home, "text": "hi", "design_sig": lookbook.design_sig(src)}
        for d in (out, page):                                  # draw_design keeps its record in both
            json.dump(rec, open(os.path.join(d, "look.json"), "w", encoding="utf-8"))
        assert not ve._design_newer(os.path.join(page, "index.html"))
        open(os.path.join(src, "index.html"), "w", encoding="utf-8").write("<html><!-- smaller, new accent --></html>")
        assert ve._design_newer(os.path.join(page, "index.html")), "an edit to her copy must draw the look again"


if __name__ == "__main__":
    fails = []
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        try:
            t()
        except Exception as e:
            fails.append(f"{t.__name__}: {type(e).__name__} {e}")
    if fails:
        print(f"FAIL {len(fails)}/{len(tests)}"); [print(" -", f) for f in fails]; sys.exit(1)
    print(f"ok {len(tests)} checks")
