#!/usr/bin/env python3
"""Guards: the one line before a render says about how long it takes on THIS computer, and that it is free
(product/render_log.py estimate / estimate_line / human_time).

  first guess  no finished render on this computer yet: a cautious default, and the line says it is a first guess
  history      a few finished renders: the time is the median seconds per frame of those, plus their start-up
  scaling      a frame with more pixels takes proportionally longer; a caption layer in stretches pays start-up
               once per stretch
  bake         the final bake reads its own records (timed whole, over the frames it started with), not renders
  ignored      failed, stopped and too-short records never feed the estimate
  rounding     "under a minute", "about 4 minutes", "about 25 minutes", "about 1 hour 10 minutes", "about 2 hours"
  cached       an unchanged render says it is already made, never a time
  free         every line says it is free and nothing leaves her computer, and never carries a dollar figure
  real log     a Trail written to disk with a size and a frame count is read back by estimate() as history

Run: python3 product/tests/test_render_estimate.py
"""
import os, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import render_log   # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(name)
        print(f"  FAIL {name} {detail}")


NOW = time.time()


def render(spf, overhead, frames=300, result="ok", width=None, height=None, step="graphics render"):
    """A finished render record: `overhead` seconds of start-up, then `frames` frames at `spf` s/frame."""
    t0 = NOW - 1000
    first = t0 + overhead
    last = first + frames * spf
    return {"step": step, "result": result, "started_at": t0, "first_frame_at": first, "last_output_at": last,
            "finished_at": last, "frames_done": frames, "frames_total": frames, "width": width, "height": height}


# first guess
e = render_log.estimate(1000, 1080, 1920, records=[])
d = render_log.DEFAULTS["graphics render"]
check("first guess: basis", e["basis"] == "first guess", e)
check("first guess: the default rate", abs(e["seconds"] - (d["overhead"] + 1000 * d["spf"])) < 1e-6, e)
line = render_log.estimate_line(1000, 1080, 1920, records=[])
check("first guess: the line says so", "first guess" in line and "more accurate after your first render" in line, line)
check("first guess: frames shown", "(1,000 frames)" in line, line)

# history: median, not mean (one freak slow render does not move it)
recs = [render(0.10, 5), render(0.12, 6), render(0.11, 4), render(2.0, 60)]
e = render_log.estimate(1000, 1080, 1920, records=recs)
check("history: basis", e["basis"] == "history" and e["samples"] == 4, e)
want = (5 + 6) / 2 + 1000 * (0.11 + 0.12) / 2          # medians of an even count: mean of the middle two
check("history: median rate + median start-up", abs(e["seconds"] - want) < 1e-6, (e["seconds"], want))
line = render_log.estimate_line(1000, 1080, 1920, records=recs)
check("history: no first-guess wording", "first guess" not in line, line)
check("history: the time", line.startswith("This render: about 2 minutes on your computer (1,000 frames)."), line)

# scaling
recs = [render(0.1, 0, frames=100)] * 3
small = render_log.estimate(1000, 540, 960, records=recs)["seconds"]
full = render_log.estimate(1000, 1080, 1920, records=recs)["seconds"]
check("scaling: a quarter of the pixels, a quarter of the time", abs(small * 4 - full) < 1e-6, (small, full))
recs = [render(0.1, 0, frames=100, width=540, height=960)] * 3      # history made at the small size
check("scaling: a small-size history scales up to the full frame",
      abs(render_log.estimate(100, 1080, 1920, records=recs)["seconds"] - 40.0) < 1e-6)
recs = [render(0.1, 10)] * 3
one = render_log.estimate(300, records=recs)["seconds"]
three = render_log.estimate(300, records=recs, renders=3)["seconds"]
check("stretches: start-up once per stretch", abs(three - one - 20) < 1e-6, (one, three))

# the bake reads bake records, timed whole
bake = {"step": "final bake", "result": "ok", "started_at": NOW - 100, "finished_at": NOW - 40, "frames_planned": 1200}
mixed = [render(1.0, 30), bake]
e = render_log.estimate(1200, step="final bake", records=mixed)
check("bake: its own history", e["basis"] == "history" and abs(e["seconds"] - 60) < 1e-6, e)
e = render_log.estimate(1200, step="final bake", records=[render(1.0, 30)])
check("bake: a render record is not a bake", e["basis"] == "first guess", e)

# ignored records
bad = [render(0.1, 5, result="failed (exit 1)"), render(0.1, 5, result="stopped"), render(0.1, 5, frames=3),
       {"step": "graphics render", "result": "ok"}]
check("ignored: failed / stopped / too short / empty", render_log.estimate(100, records=bad)["basis"] == "first guess")

# rounding
for secs, words in [(0, "under a minute"), (59, "under a minute"), (60, "about 1 minute"), (100, "about 2 minutes"),
                    (4 * 60 + 10, "about 4 minutes"), (9 * 60 + 40, "about 10 minutes"), (12 * 60, "about 10 minutes"),
                    (23 * 60, "about 25 minutes"), (56 * 60, "about 55 minutes"), (58 * 60, "about 1 hour"),
                    (70 * 60, "about 1 hour 10 minutes"), (124 * 60, "about 2 hours"),
                    (3 * 3600 + 26 * 60, "about 3 hours 30 minutes")]:
    got = render_log.human_time(secs)
    check(f"rounding: {secs}s", got == words, f"{got!r} != {words!r}")

# cached
line = render_log.estimate_line(cached=True)
check("cached: already made, no time", "already made" in line and "minute" not in line, line)

# free, never a price
for ln in (render_log.estimate_line(500, records=[]), render_log.estimate_line(500, records=[render(0.1, 2)] * 3),
           render_log.estimate_line(cached=True),
           render_log.estimate_line(500, step="final bake", what="Putting your reel together", records=[])):
    check("free: said plainly", ln.endswith("Free, nothing leaves your computer."), ln)
    check("free: no dollar figure", "$" not in ln, ln)

# a real Trail on disk feeds the next estimate
tmp = tempfile.mkdtemp(prefix="render-estimate-test-")
real_dir = render_log.LOG_DIR
try:
    render_log.LOG_DIR = os.path.join(tmp, "render-log")             # never touch the real _local/
    check("real log: empty log is a first guess", render_log.estimate(300)["basis"] == "first guess")
    t = render_log.Trail("graphics render", os.path.join(tmp, "comp"), size=(1080, 1920))
    t.rec["first_frame_at"] = t.rec["started_at"] + 2
    t.output(300, 300, "capture")
    t.rec["first_frame_at"] = t.rec["last_output_at"] - 30           # 300 frames over 30 s = 0.1 s/frame
    t.finish("ok")
    got = render_log.recent(1)[0]                                    # the only record so far
    check("real log: size recorded", got.get("width") == 1080 and got.get("height") == 1920, got)
    e = render_log.estimate(600, 1080, 1920)
    check("real log: read back as history", e["basis"] == "history" and e["samples"] == 1, e)
    check("real log: about 0.1 s/frame", 59 <= e["seconds"] <= 62, e)
    b = render_log.Trail("final bake", os.path.join(tmp, "out.mp4"), reports_progress=False, frames=900)
    b.finish("ok")
    bk = [r for r in render_log.recent(5) if r.get("step") == "final bake"]
    check("real log: a bake keeps its frame count", bk and bk[0].get("frames_planned") == 900, bk)
finally:
    render_log.LOG_DIR = real_dir
    shutil.rmtree(tmp, ignore_errors=True)

print(f"{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
