#!/usr/bin/env python3
"""Guards: a look she marked "behind your head" exports from the page's Finish, never sends her to the chat.

  export    Finish no longer refuses a reel with a look behind her
  cutout    each behind look gets her cutout from her own footage over that look's stretch (graded like her footage),
            via HyperFrames' remove-background at the pinned version (through product/bg_remove.py), as a clear .mov;
            made once, reused after
  stacking  the behind look goes under everything, her cutout right over it, every other look and her captions on top
  render    the behind look renders without the over-her-face check (her cutout covers it on purpose)
  marked    a look SHE added (a GIF, a sandbox collage) and marked behind her is marked behind in looks.json, so
            Finish finds it (only the reel's own layers were)
  captions  a full-screen look behind her never makes her captions step aside (they play over her, it plays under)

Run: python3 product/tests/test_finish_behind.py
"""
import inspect, os, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import finish  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


src = inspect.getsource(finish._run_finish) + inspect.getsource(finish._finish_steps)   # the steps moved out (the bar)
check("can't export that yet" not in src, "export: Finish still refuses a look behind her")
check("lname in behind" in src and "--no-subject" in src, "render: a behind look should skip the over-her-face check")
check("_behind_cutouts(" in src and "under + _behind_cutouts(" in src, "stacking: her cutout should sit right over the behind look, under the rest")

import visual_editor as ve  # noqa: E402
ms = inspect.getsource(ve.looks_manifest)
check("bool(back.get(key))" in ms, "export: a look she added and marked behind her should be marked behind in the list Finish reads")
check('"Full screen"' not in ms,
      "captions: a full-screen look (behind her or not) should never make her captions step aside unless it shows her words")

tmp = tempfile.mkdtemp(prefix="finish-behind-")
import bg_remove  # noqa: E402
real = (finish._run, finish._save, finish._looks_doc, bg_remove.run)
try:
    jd = os.path.join(tmp, "reel"); os.makedirs(os.path.join(jd, "hf-graphics", "finish"))
    base = os.path.join(jd, "base.mp4"); open(base, "w", encoding="utf-8").write("x")
    cmds = []

    def fake_run(cmd, jd_, what, stoppable=True):
        cmds.append(cmd)
        return ""

    def fake_cutout(seg, mov, **kw):          # product/bg_remove.py, the one way remove-background runs
        cmds.append(bg_remove.argv(seg, mov))
        open(mov, "w", encoding="utf-8").write("mov")
        return mov
    finish._run, finish._save = fake_run, (lambda jd_, **kv: kv)
    bg_remove.run = fake_cutout
    finish._looks_doc = lambda jd_: {"layers": [{"name": "add-w41", "dur": 2.07, "offset": 15.03, "behind": True}]}
    got = finish._behind_cutouts(jd, base, [("add-w41", "x.mov", 15.03)], "Cinematic")
    check(got and got[0][0] == "behind-add-w41" and got[0][2] == 15.03 and got[0][1].endswith(".mov"),
          f"cutout: one clear clip at the look's start, got {got}")
    ff = next((c for c in cmds if c[0] == "ffmpeg"), [])
    check("-ss" in ff and ff[ff.index("-ss") + 1] == "15.030" and ff[ff.index("-t") + 1] == "2.070",
          f"cutout: cut from her footage over exactly the look's stretch, got {ff}")
    check("-vf" in ff, "cutout: graded the way her footage is, so she matches the reel around her")
    rb = next((c for c in cmds if "remove-background" in c), [])
    check(any(str(x).startswith("hyperframes@") for x in rb), f"cutout: HyperFrames at the pinned version, got {rb}")
    cmds.clear()
    finish._behind_cutouts(jd, base, [("add-w41", "x.mov", 15.03)], "Cinematic")
    check(not cmds, f"cutout: made once, reused on the next export, ran {cmds}")
finally:
    finish._run, finish._save, finish._looks_doc, bg_remove.run = real
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_finish_behind: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_finish_behind: all {n} checks passed")
