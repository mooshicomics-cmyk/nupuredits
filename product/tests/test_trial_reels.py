#!/usr/bin/env python3
"""Trial reels: the same finished reel with a different hook (product/trial_reels.py, product/trial_hook.py).

These checks hold without CapCut, the build engine or a render:
  * trial_hook leaves every normal build alone (no env: same text, same size, same name, same fonts);
  * on a trial build the hook block gets the trial's lines in order, the hook's own track is re-sized to the new
    length, a line past the trial's last is left out, every other text is untouched, the script's fonts follow
    the trial's words, and the draft is named "<reel> trial B" without the reel's version;
  * report() says plainly when the build placed no hook text at all;
  * trial_reels.write gives ids b, c, d..., infers the shape, refuses a two-part shape written as one line, caps at
    five, and keeps made trials when new hooks are written;
  * status() reads which road a reel was finished on (editor / capcut build script / well-done) and its hook.

Everything runs in a throwaway engine skeleton; this engine's own projects/ are never touched.

Run: python3 product/tests/test_trial_reels.py
"""
import importlib, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
fails = []


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))
    else:
        print(f"  ok   {name}")


def fresh_trial_hook(env):
    for k in ("REE_TRIAL_HOOK", "REE_TRIAL_NAME"):
        os.environ.pop(k, None)
    os.environ.update(env)
    import trial_hook
    return importlib.reload(trial_hook)


def test_trial_hook():
    th = fresh_trial_hook({})
    check("no trial: text and size pass through", th.swap("hook", "my hook", 16, hook_size=lambda t: 9) == ("my hook", 16))
    check("no trial: name and fonts pass through", th.name("Sunday Reset 1.2") == "Sunday Reset 1.2"
          and th.remap({"a": 1}) == {"a": 1} and th.report() == [])

    th = fresh_trial_hook({"REE_TRIAL_HOOK": "moms selling one-on-one / you outgrew your calendar",
                           "REE_TRIAL_NAME": "{name} trial B"})
    t1, s1 = th.swap("hook", "old headline", 17, hook_size=lambda t: len(t), wrap=lambda t, s: t.upper())
    check("hook track gets line one, re-sized to its length, wrapped",
          t1 == "MOMS SELLING ONE-ON-ONE" and s1 == len("moms selling one-on-one"), (t1, s1))
    t2, s2 = th.swap("subhead", "old subhead", 12, wrap=lambda t, s: t)
    check("the subhead gets line two at the script's own size", t2 == "you outgrew your calendar" and s2 == 12, (t2, s2))
    check("a caption or thought is never touched", th.swap("thought", "a thought", 12) == ("a thought", 12))
    t3, _ = th.swap("kicker", "old kicker", 10)
    check("a hook-block line past the trial's last is left out", t3 is None)
    fm = th.remap({"old headline": "/f/hook.ttf", "old subhead": "/f/thought.ttf", "a thought": "/f/thought.ttf"})
    check("the script's fonts follow the trial's words",
          fm.get("MOMS SELLING ONE-ON-ONE") == "/f/hook.ttf" and fm.get("you outgrew your calendar") == "/f/thought.ttf"
          and fm.get("a thought") == "/f/thought.ttf", fm)
    check("trial draft named after the reel, without its version", th.name("Sunday Reset 1.2") == "Sunday Reset trial B",
          th.name("Sunday Reset 1.2"))
    check("report names the hook it placed", th.report() == ["[trial] hook: moms selling one-on-one / you outgrew your calendar"],
          th.report())

    th = fresh_trial_hook({"REE_TRIAL_HOOK": json.dumps(["one line only"])})
    check("a JSON list works too", th.lines() == ["one line only"])
    check("report says so when the build placed no hook text", "placed no hook text" in (th.report() or [""])[0])
    fresh_trial_hook({})


def test_trial_reels():
    import trial_reels as tr
    root = tempfile.mkdtemp(prefix="trial-reels-")
    old_root = tr.ROOT
    tr.ROOT = root
    try:
        jd = os.path.join(root, "projects", "the-reel")
        os.makedirs(jd)
        with open(os.path.join(jd, "build-cleanyap.py"), "w", encoding="utf-8") as f:
            f.write('import cleanyap as C\nHEADLINE = "you probably know a mom like this"\n'
                    'SUBHEAD = "and she needs you"\nC.finalize(did, NAME, fm)\n')
        st = tr.status(jd)
        check("a reel built by its own CapCut script reads as capcut",
              st["how"] == "capcut" and st["hook"] == "you probably know a mom like this / and she needs you"
              and st["lines"] == 2, st)

        saved = tr.write(jd, [{"hook": "line one / line two", "angle": "who"}, {"hook": "just one line"}])
        check("ids b and c, shapes inferred", [(t["id"], t["shape"]) for t in saved] == [("b", "eyebrow-headline"), ("c", "hook")],
              saved)
        try:
            tr.write(jd, [{"hook": "no break here", "shape": "headline-subhead"}])
            check("a two-part shape written as one line is refused", False)
        except tr.Refuse:
            check("a two-part shape written as one line is refused", True)
        tr._mark(jd, "b", made="2026-10-17", file="x.mp4")
        again = tr.write(jd, [{"hook": f"hook {i}"} for i in range(9)])
        check("made trials are kept and the list caps at five",
              again[0]["id"] == "b" and again[0].get("made") and len(again) == tr.MAX_TRIALS
              and [t["id"] for t in again] == ["b", "c", "d", "e", "f"], [t["id"] for t in again])

        wd = os.path.join(root, "projects", "baked")
        os.makedirs(os.path.join(wd, "outputs"))
        json.dump({"hook": ["the hidden costs", "you can't see"], "hook_emphasis": "first", "hook_end": 7.5,
                   "pack": "Butter"}, open(os.path.join(wd, "caption-plan.json"), "w", encoding="utf-8"))
        for f in ("baked.mp4", "baked.final.mp4"):
            open(os.path.join(wd, "outputs", f), "w", encoding="utf-8").close()
        st = tr.status(wd)
        check("a baked reel reads as well-done with its hook and shape",
              st["how"] == "well-done" and st["shape"] == "headline-subhead" and st["dur"] == 7.5 and st["pack"] == "Butter", st)

        nd = os.path.join(root, "projects", "unfinished")
        os.makedirs(nd)
        check("an unfinished reel says so", tr.status(nd)["how"] is None)
    finally:
        tr.ROOT = old_root
        shutil.rmtree(root, ignore_errors=True)


def test_trial_edits():
    import trial_edits as te
    check("a run of lines reads as its numbers", te.span("4-7") == [4, 5, 6, 7] and te.span(7) == [7] and te.span([2, 3]) == [2, 3])
    segs = [{"n": i + 1, "text": f"line {i + 1}", "dur": 1.0, "seg": {"clip": "a.mov", "start": float(i), "end": i + 0.9,
             "transcript": f"line {i + 1}"}} for i in range(8)]
    plan = te.plan_segments(segs, "6-7", ["2-3"])
    check("the opening run moves to the front, dropped lines go, the rest keep her order",
          [p["transcript"] for p in plan] == ["line 6", "line 7", "line 1", "line 4", "line 5", "line 8"],
          [p["transcript"] for p in plan])
    for bad, why in ((("9", []), "a line the reel doesn't have"), (("3", ["3"]), "a line that opens and is dropped"),
                     ((None, ["1-7"]), "fewer than two lines left")):
        try:
            te.plan_segments(segs, *bad)
            check(f"refuses {why}", False)
        except te.Refuse:
            check(f"refuses {why}", True)

    root = tempfile.mkdtemp(prefix="trial-edits-")
    try:
        src = os.path.join(root, "projects", "her-reel")
        for d in ("raw", "review", "transcript", "outputs", "hf-graphics/finish", "hf-graphics/_looks/add-w3"):
            os.makedirs(os.path.join(src, d))
        open(os.path.join(src, "raw", "take.mov"), "wb").write(b"footage")
        for f, data in (("review/finish.json", {"state": "done"}), ("review/route.json", {"route": "editor"}),
                        ("review/look-requests.json", {"requests": [{"id": "x", "idea": "old idea"}]}),
                        ("transcript/accents.json", {"job": "her-reel", "accents": []}),
                        ("hf-graphics/_looks/add-w3/line.json", {"offset": 1.0})):
            json.dump(data, open(os.path.join(src, f), "w", encoding="utf-8"))
        open(os.path.join(src, "outputs", "her-reel.final.mp4"), "wb").write(b"x")
        open(os.path.join(src, "hf-graphics", "finish", "add-w3.mov"), "wb").write(b"x")
        dst = os.path.join(root, "projects", "her-reel-trial-b")
        te.copy_reel(src, dst, "b")
        check("her footage is linked, not copied", os.path.samefile(os.path.join(src, "raw", "take.mov"), os.path.join(dst, "raw", "take.mov")))
        check("her export, renders and outputs don't carry over",
              not os.path.exists(os.path.join(dst, "review", "finish.json"))
              and not os.path.exists(os.path.join(dst, "hf-graphics", "finish"))
              and os.listdir(os.path.join(dst, "outputs")) == [])
        check("her looks and route do carry over", os.path.exists(os.path.join(dst, "hf-graphics", "_looks", "add-w3", "line.json"))
              and json.load(open(os.path.join(dst, "review", "route.json"), encoding="utf-8"))["route"] == "editor")
        check("handled ideas are cleared, the copy's own name is in its files, and it is marked a trial",
              json.load(open(os.path.join(dst, "review", "look-requests.json"), encoding="utf-8")) == {"requests": []}
              and json.load(open(os.path.join(dst, "transcript", "accents.json"), encoding="utf-8"))["job"] == "her-reel-trial-b"
              and json.load(open(os.path.join(dst, "review", "trial-of.json"), encoding="utf-8"))["of"] == "her-reel")
        check("her reel is untouched", json.load(open(os.path.join(src, "review", "finish.json"), encoding="utf-8")) == {"state": "done"}
              and json.load(open(os.path.join(src, "transcript", "accents.json"), encoding="utf-8"))["job"] == "her-reel")
        te.copy_reel(src, dst, "b")
        check("a trial's own folder is remade", os.path.exists(os.path.join(dst, "review", "trial-of.json")))
        other = os.path.join(root, "projects", "her-reel-trial-c")
        os.makedirs(other)
        open(os.path.join(other, "keep.txt"), "w", encoding="utf-8").write("hers")
        try:
            te.copy_reel(src, other, "c")
            check("a folder that isn't this reel's trial is never replaced", False)
        except te.Refuse:
            check("a folder that isn't this reel's trial is never replaced", open(os.path.join(other, "keep.txt"), encoding="utf-8").read() == "hers")

        import trial_reels as tr
        old_root = tr.ROOT
        tr.ROOT = root
        try:
            json.dump({"layers": []}, open(os.path.join(src, "review", "looks.json"), "w", encoding="utf-8"))
            json.dump({"segments": [s["seg"] for s in segs]}, open(os.path.join(src, "transcript", "cuts.json"), "w", encoding="utf-8"))
            check("an editor reel reads as editor", tr.status(src)["how"] == "editor")
            try:
                tr.write(src, [{"hook": "just a new card"}])
                check("an editor-reel trial with only a new hook is refused (it would read as a repost)", False)
            except tr.Refuse:
                check("an editor-reel trial with only a new hook is refused (it would read as a repost)", True)
            import trial_edits as te2
            real = te2.her_packs
            te2.her_packs = lambda jd: {"Butter"}                 # her brand, for this test: one pack
            try:
                try:
                    tr.write(src, [{"open": "6-7", "pack": "Editorial", "hook": "a / b"}])
                    check("a pack outside her brand is refused", False)
                except tr.Refuse as e:
                    check("a pack outside her brand is refused", "isn't one of your looks" in str(e), str(e))
                saved = tr.write(src, [{"open": "6-7", "drop": ["2-3"], "pack": "Butter", "hook": "a / b"}])
                check("a re-edit trial in her own pack saves its cut, pack and hook",
                      saved[0]["open"] == "6-7" and saved[0]["drop"] == ["2-3"] and saved[0]["pack"] == "Butter"
                      and saved[0]["shape"] == "eyebrow-headline", saved)
            finally:
                te2.her_packs = real
        finally:
            tr.ROOT = old_root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_reuse_and_windows():
    import trial_edits as te
    root = tempfile.mkdtemp(prefix="trial-reuse-")
    try:
        a, b = os.path.join(root, "a"), os.path.join(root, "b")
        for d, nudge in ((a, "#root{translate:-12px -116px;}"), (b, "#root{transform:translate(-12px,-116px);}")):
            os.makedirs(os.path.join(d, "fonts"))
            open(os.path.join(d, "fonts", "f.ttf"), "wb").write(b"font")
            open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(f'<div>hi</div><style id="ve-nudge">{nudge}</style>')
        check("the same nudge written either way is the same picture", te._same_picture(a, b))
        open(os.path.join(b, "index.html"), "w", encoding="utf-8").write('<div>hi</div><style id="ve-nudge">#root{transform:translate(-12px,-90px);}</style>')
        check("a different nudge is a different picture", not te._same_picture(a, b))
        open(os.path.join(b, "index.html"), "w", encoding="utf-8").write('<div>hi</div><style id="ve-nudge">#root{translate:-12px -116px;}</style>')
        open(os.path.join(b, "fonts", "f.ttf"), "wb").write(b"other font")
        check("any other file differing is a different picture", not te._same_picture(a, b))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    w = {"h01-hook/hf-reel-type-kitchen clean calm": [0.0, 6.9], "g02-card": [10.0, 12.0], "bad": "x"}
    check("a windows entry is found by its layer's folder or name",
          te._win_key(w, "h01-hook") == "h01-hook/hf-reel-type-kitchen clean calm" and te._win_key(w, "g02-card") == "g02-card"
          and te._win_key(w, "bad") is None and te._win_key(None, "h01-hook") is None)


def test_hook_clear_of_cards():
    """A trial hook never sits on top of another look: it ends as a card comes in, or waits for a clear stretch
    (2026-10-18, her post card under "wait till you see this")."""
    import trial_edits as te
    check("hook: nothing else on screen = its full length", te.hook_window([], 0.0, 7.0, 30.0) == (0.0, 7.0))
    check("hook: ends as a card comes in", te.hook_window([(4.0, 7.0)], 0.0, 7.0, 30.0) == (0.0, 4.0))
    check("hook: a card from the start = it waits for the card to go",
          te.hook_window([(0.0, 3.0), (10.0, 12.0)], 0.0, 7.0, 30.0) == (3.0, 7.0))
    check("hook: a gap too short to read in is skipped", te.hook_window([(0.0, 3.0), (4.0, 6.0)], 0.0, 7.0, 30.0) == (6.0, 7.0))
    check("hook: no clear stretch = no room", te.hook_window([(0.0, 29.5)], 0.0, 7.0, 30.0)[1] < te.HOOK_MIN_S)
    check("hook: a look elsewhere on screen (low, or beside her) doesn't block it; an unknown one does",
          not te._meets((1150, 1700), te.HOOK_BAND) and not te._meets((455, 680), te.HOOK_BAND)
          and te._meets(None, te.HOOK_BAND) and te._meets((150, 850), te.HOOK_BAND))


def main():
    test_trial_hook()
    test_hook_clear_of_cards()
    test_trial_reels()
    test_trial_edits()
    test_reuse_and_windows()
    print("\nPASS" if not fails else f"\nFAIL ({len(fails)}): {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
