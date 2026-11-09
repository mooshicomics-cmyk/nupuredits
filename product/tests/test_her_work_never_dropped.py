#!/usr/bin/env python3
"""Guards: what she builds in the visual editor is never thrown away without a word (a buyer on Windows, 2026-10-23:
placed looks vanished from review/swaps.json with no trace, GIFs she picked with an idea never landed, and Sandbox
sketches Claude had delivered were dropped and their designs deleted).

  unreadable    a looks file that can't be read for a moment is read again; one that stays unreadable stops the
                change. An empty list never stands in for it and gets written back over her other looks.
  sandbox       a new Sandbox idea never deletes sketches already in her Sandbox, a build Claude is on, or an idea
                carrying her picture: it says why instead. The same idea sent again (Back, then Send) is the one
                she has. An idea nobody has started on is still replaced, as before.
  her slot      a look she put on the sketch's line since the sketches landed is never swapped off her reel when she
                tries a sketch, and cancelling the idea never takes it off either.
  place_media   her picture goes on under the reel's lock (two writers once picked the same slot).
  work folders  a design's .hyperframes/ check records are never copied into a drawn page or a saved design (they
                pushed a sketch's path past Windows' 260 characters: [WinError 3]).

Run: python3 product/tests/test_her_work_never_dropped.py   (or with pytest)
"""
import builtins, json, os, shutil, sys, tempfile, time
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import visual_editor as ve  # noqa: E402
import lookbook  # noqa: E402

STARTER = os.path.join(PRODUCT, "lookbook-designs", "starter")


def _job(tmp, name="reel"):
    jd = os.path.join(tmp, name)
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    ve._atomic_json(os.path.join(jd, "review", "script.json"), {"words": [{"t": "Hello"}] * 12})
    return jd


def _swaps(jd, adds):
    ve._atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": {}, "adds": adds, "behind": {}})


def test_unreadable_looks_file_never_wipes_her_looks():
    tmp = tempfile.mkdtemp(prefix="ve-keep-")
    real_open, real_sleep = builtins.open, time.sleep
    try:
        jd = _job(tmp)
        mine = {"add-w1": {"look": "breakaway", "dir": "a"}, "add-w5": {"look": "eyebrow", "dir": "b"}}
        _swaps(jd, mine)
        path = os.path.join(jd, "review", "swaps.json")
        fails = {"n": 3}

        def flaky(p, *a, **k):                               # Windows: a file being swapped in refuses for a moment
            if os.path.abspath(str(p)) == os.path.abspath(path) and "w" not in (a[0] if a else k.get("mode", "r")) \
                    and fails["n"] > 0:
                fails["n"] -= 1
                raise PermissionError(13, "The process cannot access the file because it is being used by another process")
            return real_open(p, *a, **k)
        ve.open = flaky
        time.sleep = lambda s: None
        ve._save_entry(jd, "add-w9", {"look": "gif", "dir": "c"})
        got = json.load(real_open(path, encoding="utf-8"))["adds"]
        assert set(got) == {"add-w1", "add-w5", "add-w9"}, f"a moment's read failure lost her looks: {sorted(got)}"

        fails["n"] = 10 ** 6                                 # it never comes back: nothing is written at all
        try:
            ve._save_entry(jd, "add-w11", {"look": "gif2", "dir": "d"})
            raised = False
        except ve.Refuse as e:
            raised = "couldn't be read" in str(e)
        assert raised, "an unreadable looks file must stop the change with a plain reason"
        got = json.load(real_open(path, encoding="utf-8"))["adds"]
        assert set(got) == {"add-w1", "add-w5", "add-w9"}, f"her looks were written over: {sorted(got)}"
    finally:
        ve.__dict__.pop("open", None)
        time.sleep = real_sleep
        shutil.rmtree(tmp, ignore_errors=True)


class _Sandbox:
    """A reel with a Sandbox: drawing, framing and placing stand in, her lookbook lives in a throwaway root."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="ve-sb-")
        self.real = (lookbook.ROOT, lookbook.check_design, ve.place_look, ve.swap, ve._reel_pack_for, ve._draw_choice,
                     ve.set_behind, ve.word_cut_times, ve._line_words, ve._frame_at, ve.media_path)
        lookbook.ROOT = os.path.join(self.tmp, "lb")
        lookbook.check_design = lambda src, pack, render_check=True: []
        self.jd = jd = _job(self.tmp)
        self.placed, self.removed = [], []

        def place(job, key, a, b, look):
            self.placed.append((key, look))
            ve._save_entry(jd, key, {"look": look, "dir": f"hf-graphics/_looks/{key}/{look}"})
            return {"warn": None}

        def swap(job, key, look):
            self.removed.append(key)
            ad = ve._adds(jd); ad.pop(key, None)
            ve._atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": {}, "adds": ad, "behind": {}})
        ve.place_look, ve.swap = place, swap
        ve._reel_pack_for = lambda jd_: "Butter"
        ve._draw_choice = lambda jd_, l, rel, comp, text, dur, pack, zones, words, accents=None, track=None: {"id": l["id"], "dir": rel}
        ve.set_behind = lambda job, key, on: None
        ve.word_cut_times = lambda jd_: {0: (0.1, 0.4), 1: (0.5, 0.9), 5: (2.0, 2.4), 6: (2.5, 2.9)}
        ve._line_words = lambda jd_, a, b: [{"w": "Hello", "s": a, "e": b}]
        ve._frame_at = lambda *a, **k: "frame.jpg"
        ve.media_path = lambda m: "/her/favorites/gifs/wow.gif"
        return self

    def sketches(self, rid, n=3):
        ids = [f"my-sandbox-{rid}-r1-{k}" for k in range(1, n + 1)]
        for d in ids:
            lookbook.save_design(STARTER, "Butter", d, sample=rid, design_id=d)
        return ids

    def __exit__(self, *a):
        (lookbook.ROOT, lookbook.check_design, ve.place_look, ve.swap, ve._reel_pack_for, ve._draw_choice,
         ve.set_behind, ve.word_cut_times, ve._line_words, ve._frame_at, ve.media_path) = self.real
        shutil.rmtree(self.tmp, ignore_errors=True)


def test_new_idea_never_deletes_delivered_sketches():
    with _Sandbox() as sb:
        r = ve.new_look_request(sb.jd, None, None, None, "a breakaway card on my hook", mode="sandbox", at=2.1)
        ids = sb.sketches(r["id"])
        ve.sandbox_takes(sb.jd, r["id"], ids, start=2.0, end=2.9)
        again = ve.new_look_request(sb.jd, None, None, None, "a breakaway card on my hook", mode="sandbox", at=2.1)
        assert again["id"] == r["id"] and again["status"] == "takes", "the same idea sent again must be the one she has"
        try:
            ve.new_look_request(sb.jd, None, None, None, "a ticker across the bottom", mode="sandbox", at=0.2)
            said = ""
        except ve.Refuse as e:
            said = str(e)
        assert "still waiting in your Sandbox" in said, f"a new idea must say why, not drop her sketches: {said!r}"
        now = [x for x in ve._requests(sb.jd) if x["id"] == r["id"]][0]
        assert now["status"] == "takes", now["status"]
        left = [l["id"] for l in lookbook.looks("Butter", hidden=True)]
        assert all(i in left for i in ids), f"her delivered sketches were deleted: {left}"
        assert all(os.path.isdir(lookbook.design_dir("Butter", i)) for i in ids)
        ve.sandbox_drop(sb.jd, r["id"])                       # she cancels it herself: then it goes, and the new one is in
        n = ve.new_look_request(sb.jd, None, None, None, "a ticker across the bottom", mode="sandbox", at=0.2)
        assert n["status"] == "open"


def test_gif_ideas_never_replace_each_other():
    with _Sandbox() as sb:
        a = ve.new_look_request(sb.jd, 1, 0.5, 0.9, "make it pop in", mode="sandbox", media="gifs/wow.gif", at=0.5)
        try:
            ve.new_look_request(sb.jd, 5, 2.0, 2.4, "bounce this one", mode="sandbox", media="gifs/stressed.gif", at=2.0)
            said = ""
        except ve.Refuse as e:
            said = str(e)
        assert "leave the words box empty and tap Add it" in said, said
        keep = [x for x in ve._requests(sb.jd) if x["id"] == a["id"]][0]
        assert keep["status"] == "open" and keep.get("media") == "gifs/wow.gif", keep


def test_an_idea_nobody_started_is_still_replaced():
    with _Sandbox() as sb:
        a = ve.new_look_request(sb.jd, None, None, None, "x", mode="sandbox", at=0.2)
        ve.new_look_request(sb.jd, None, None, None, "something else", mode="sandbox", at=0.3)
        assert [x for x in ve._requests(sb.jd) if x["id"] == a["id"]][0]["status"] == "dropped"
        b = [x for x in ve._requests(sb.jd) if x["status"] == "open"][0]
        ve.sandbox_working(sb.jd, b["id"])                    # Claude said "I'm on it": no longer replaced quietly
        try:
            ve.new_look_request(sb.jd, None, None, None, "a third idea", mode="sandbox", at=0.3)
            said = ""
        except ve.Refuse as e:
            said = str(e)
        assert "building sketches" in said, said


def test_trying_a_sketch_never_takes_her_look_off():
    with _Sandbox() as sb:
        r = ve.new_look_request(sb.jd, None, None, None, "an eyebrow headline", mode="sandbox", at=2.1)
        ids = sb.sketches(r["id"])
        out = ve.sandbox_takes(sb.jd, r["id"], ids, start=2.0, end=2.9)
        slot = out["place"]["key"]
        her = {"look": "breakaway-card", "dir": f"hf-graphics/_looks/{slot}/breakaway-card"}
        ve._save_entry(sb.jd, slot, her)                      # she put her own look on that line since
        ve.sandbox_try(sb.jd, r["id"], ids[1])
        assert ve._adds(sb.jd).get(slot) == her, f"trying a sketch swapped her look off: {ve._adds(sb.jd).get(slot)}"
        tried_at = [k for k, l in sb.placed if l == ids[1]]
        assert tried_at and tried_at[-1] != slot, sb.placed
        ve.sandbox_drop(sb.jd, r["id"])                       # cancelling takes the sketch off, never her look
        assert ve._adds(sb.jd).get(slot) == her
        assert slot not in sb.removed and tried_at[-1] in sb.removed, sb.removed


def test_place_media_waits_for_the_reel_lock():
    tmp = tempfile.mkdtemp(prefix="ve-lock-")
    try:
        jd = _job(tmp)
        lf = os.path.join(os.path.realpath(jd), "review", ".write.lock")
        open(lf, "w", encoding="utf-8").write(str(os.getpid()))   # another live writer holds her reel
        with ve.patient(0.3):
            try:
                ve.place_media(jd, 0.5, 1.0, "gifs/none.gif")
                said = ""
            except ve.Refuse as e:
                said = str(e)
        assert "busy saving another change" in said, f"place_media must take the reel's lock first: {said!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_work_folders_never_copied():
    tmp = tempfile.mkdtemp(prefix="lb-work-")
    real = lookbook.ROOT, lookbook.check_design
    try:
        lookbook.ROOT = os.path.join(tmp, "lb")
        lookbook.check_design = lambda src, pack, render_check=True: []
        src = os.path.join(tmp, "sketch")
        shutil.copytree(STARTER, src)
        chk = os.path.join(src, ".hyperframes", "artifacts", "checks")
        os.makedirs(chk); open(os.path.join(chk, "624755e4.json"), "w", encoding="utf-8").write("{}")
        did = lookbook.save_design(src, "Butter", "Sketch", sample="42c6a6", design_id="my-sandbox-42c6a6-r1-1")
        saved = lookbook.design_dir("Butter", did)
        assert not os.path.exists(os.path.join(saved, ".hyperframes")), "a check record was saved into her design"
        os.makedirs(os.path.join(saved, ".hyperframes", "artifacts", "checks"), exist_ok=True)   # a check run on it later
        out = os.path.join(tmp, "drawn")
        lookbook.draw_design(saved, out, "Hello there", 2.0, "Butter", "sb-1", look_id=did)
        page = os.path.join(out, "hf-reel-type-butter")
        assert os.path.isfile(os.path.join(page, "index.html"))
        assert not os.path.exists(os.path.join(page, ".hyperframes")), "a check record was copied into the drawn page"
    finally:
        lookbook.ROOT, lookbook.check_design = real
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    bad = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as e:
                bad += 1
                print(f"  ✗ {name}: {e}")
    print(f"test_her_work_never_dropped: {'all passed' if not bad else f'{bad} FAILED'}")
    sys.exit(1 if bad else 0)
