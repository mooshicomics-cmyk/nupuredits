#!/usr/bin/env python3
"""Guards: the Finish tab's bar shows the real work, and 100% only when the export is done (2026-10-23: "basically
goes from 0 to 100 and thats not a true representation of progress", "100% should only happen when truly done").

  weighted   every step this export runs is on the bar, weighted by its rough cost: the full-quality cut and the CapCut
             draft are not free, so the bar is well past 0 before the looks render and well short of 100 after
  inside     a long step moves: an encode's own out_time (ffmpeg -progress), a render's frames, a builder's stretches
             (export_progress.stage / inner, nested with window), else a slow creep by its expected time
  monotonic  the bar never goes back (an encode retried on the software encoder starts its own count again)
  capped     never 100% before done, even with every step at its end; exactly 100% at done
  page       the page reads `progress` and never shows 100 for a running export
  one        a second export while one is running says so and leaves the running one's finish.json (state, message,
             bar) and its stop file untouched: it used to mark the live export failed and tell her page it stopped

Run: python3 product/tests/test_finish_progress.py
"""
import os, shutil, sys, tempfile, time
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import finish, export_progress  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


def prog(jd):
    return float(finish.status(jd).get("progress") or 0)


def ffmpeg_at(path, secs):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"frame=1\nout_time_us={int(secs * 1e6)}\nprogress=continue\n")


tmp = tempfile.mkdtemp(prefix="finish-progress-")
real_frames, real_env = finish._render_frames, os.environ.get(export_progress.ENV)
try:
    jd = os.path.join(tmp, "reel"); os.makedirs(os.path.join(jd, "review"))
    sub = finish._sub_path(jd)
    steps = [("cut", 300.0), ("check", 3.0), ("look:cap-all", 70.0), ("capcut", 300.0)]
    bar = finish._Bar(jd, steps)
    tot = sum(c for _k, c in steps)
    finish._save(jd, state="running", progress=0.0)

    # weighted: the cut is a real share of the bar, before any look renders
    bar.go("cut", state="running", step="Making your full-quality cut")
    os.environ[export_progress.ENV] = sub
    fp = export_progress.ffmpeg_args(100.0)
    check(fp[:1] == ["-progress"] and os.path.isfile(fp[1]), f"inside: an export's encode gets -progress, got {fp}")
    ffmpeg_at(fp[1], 25.0); bar.tick(); a = prog(jd)
    ffmpeg_at(fp[1], 75.0); bar.tick(); b = prog(jd)
    check(0 < a < b < 300 / tot, f"inside: the cut's encode moves the bar within its share, got {a} then {b}")
    check(abs(b - 0.75 * 300 / tot) < 0.01, f"weighted: 75% of the cut is 75% of its share, got {b}")

    # monotonic: a software retry starts its count again; the bar holds
    fp = export_progress.ffmpeg_args(100.0)
    ffmpeg_at(fp[1], 5.0); bar.tick()
    check(prog(jd) >= b, f"monotonic: a retried encode never pulls the bar back, {b} -> {prog(jd)}")

    bar.go("check", step="Checking your looks are current")
    check(prog(jd) >= 303 / tot - 0.003 or prog(jd) >= b, "weighted: the next step starts past the whole cut")

    # a look render: its frames
    finish._render_frames = lambda pid: 0.5
    finish._save(jd, child=999001)
    bar.go("look:cap-all", step="Rendering your captions")
    finish._save(jd, child=999002)                            # the render's own process, started after the step
    bar.tick()
    want = (303 + 35) / tot
    check(abs(prog(jd) - want) < 0.01, f"inside: half the caption frames is half the render's share, got {prog(jd)} want {want}")
    finish._render_frames = real_frames

    # the CapCut draft: nested stretches (capcut_handoff's window, capcut_tail's stage, capcut_alpha's inner)
    bar.go("capcut", step="Building your CapCut draft")
    before = prog(jd)
    check(before < 0.99 and before <= (373 + 1) / tot, f"weighted: the draft is a real share still to come, at {before}")
    export_progress.window(0.5, 0.9); export_progress.stage(0, 1, "getting your captions ready for CapCut")
    export_progress.inner(0.5)
    bar.tick()
    want = (373 + 300 * 0.7) / tot
    check(abs(prog(jd) - want) < 0.01, f"inside: a stretch inside a window lands where it should, got {prog(jd)} want {want}")
    st = finish.status(jd).get("step") or ""
    check(st.startswith("Building your CapCut draft") and "captions ready" in st,
          f"inside: the step says what the builder is doing, got {st!r}")

    # creep: a step that says nothing still moves
    export_progress.reset(sub); export_progress.window(0, 1)
    bar.t0 = time.time() - 600
    was = prog(jd); bar.tick()
    check(prog(jd) >= was, "monotonic: a creep never pulls the bar back")
    bar2 = finish._Bar(jd, [("only", 100.0)])
    finish._save(jd, state="running", progress=0.0)
    bar2.go("only", step="x"); bar2.t0 = time.time() - 60; bar2.tick()
    check(0 < prog(jd) < 0.99, f"inside: a silent step creeps by its expected time, got {prog(jd)}")

    # capped: every step at its end is still not done
    finish._save(jd, state="running", progress=0.0)
    bar3 = finish._Bar(jd, [("capcut", 10.0)])
    bar3.go("capcut", step="Building your CapCut draft")
    export_progress.window(0, 1); export_progress.stage(0, 1); export_progress.inner(1.0)
    bar3.tick()
    check(0.98 <= prog(jd) <= 0.99, f"capped: never 100% before done, got {prog(jd)}")
    bar3.close()
    finish._save(jd, state="done", step="In CapCut")
    check(prog(jd) == 1.0, f"capped: exactly 100% at done, got {prog(jd)}")
    bar3._put(0.5)
    check(prog(jd) == 1.0, "capped: the bar never writes over a finished export")

    # no export running: every call is a no-op
    os.environ.pop(export_progress.ENV, None)
    check(export_progress.ffmpeg_args(10.0) == [], "outside an export, an encode gets no -progress")

    # one: a second export never touches the running one
    import json, visual_editor as ve
    live = {"state": "running", "owner": os.getppid(), "progress": 0.26, "message": None,
            "step": "Building your CapCut draft: getting your captions ready for CapCut"}
    ve._atomic_json(finish._path(jd), live)
    open(finish._stop_path(jd), "w", encoding="utf-8").close()
    before_doc = open(finish._path(jd), encoding="utf-8").read()
    real_dir = ve.job_dir
    ve.job_dir = lambda job: jd
    try:
        finish.run("reel", "capcut")
        check(False, "one: a second export should refuse while one is running")
    except finish.Busy as e:
        check("already running" in str(e), f"one: said plainly, got {e}")
    except Exception as e:
        check(False, f"one: a second export should raise Busy, got {e!r}")
    finally:
        ve.job_dir = real_dir
    check(open(finish._path(jd), encoding="utf-8").read() == before_doc,
          f"one: the running export's finish.json is untouched, got {finish.status(jd)}")
    check(os.path.exists(finish._stop_path(jd)), "one: the running export's stop file is left alone")
    os.remove(finish._stop_path(jd))
    srv = open(os.path.join(os.path.dirname(HERE), "visual_editor_server.py"), encoding="utf-8").read()
    check("except finish.Busy" in srv, "one: the page's export never marks a running export failed")

    # the whole plan: the cut and the draft are on it, weighted
    src = open(os.path.join(os.path.dirname(HERE), "finish.py"), encoding="utf-8").read()
    check('("cut", cut_c)' in src and '("capcut",' in src and "bar.go(f\"look:{lname}\"" in src,
          "weighted: the cut, each look and the CapCut draft are steps of the bar")
    html = open(os.path.join(os.path.dirname(HERE), "visual-editor", "editor.html"), encoding="utf-8").read()
    check("F.progress != null ? Math.min(99," in html, "page: the bar reads progress and never shows 100 while running")
finally:
    finish._render_frames = real_frames
    if real_env is None:
        os.environ.pop(export_progress.ENV, None)
    else:
        os.environ[export_progress.ENV] = real_env
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("test_finish_progress: FAILED\n  " + "\n  ".join(fails))
    sys.exit(1)
print(f"test_finish_progress: all {n} checks passed")
