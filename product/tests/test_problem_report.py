#!/usr/bin/env python3
"""test_problem_report.py — /report-a-problem has to answer "what was it DOING", not just "what is installed".

The case this exists for: a buyer's well-done render was still going the next morning, so it was cancelled,
and nothing on her machine could say what it had been doing. The render timing file is only written when a
render ENDS, the stall report only when the renderer goes silent, and the problem report only listed
versions and paths, which all came back clean. So support could only guess, and the report tool was, in
practice, a setup checker.

What this pins down:
  1. A render that is stopped mid-way still leaves a record saying how far it got and how fast.
  2. The record tells the three failure shapes apart: FROZE (renderer silent while the engine waited),
     CRAWLED (frames still counting, slowly), and STOPPED from outside (record no longer rewritten).
  3. Two renders alive at the same time are called out, because that alone turns minutes into hours.
  4. A step that prints nothing by design (the ffmpeg bake) is never mistaken for one that never started.
  5. The real render wrapper (reel_render._run_render_watched) writes that record from the renderer's
     own progress output, and marks the result.
  6. The evidence script runs, and the collector folds it into the one report, before "What happened".

Run:  python3 product/tests/test_problem_report.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "product"))
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import render_log   # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


TMP = tempfile.mkdtemp(prefix="problem-report-test-")
render_log.LOG_DIR = os.path.join(TMP, "render-log")      # never write into the real _local/
NOW = time.time()
JOB = "demo"                     # a stand-in job name, never a real reel
COMP_REL = f"projects/{JOB}/hf-graphics"


def rec(**kw):
    base = {"step": "graphics render", "target": COMP_REL, "reports_progress": True,
            "started_at": NOW - 3600, "written_at": NOW - 3600, "last_output_at": None, "first_frame_at": None,
            "frames_done": None, "frames_total": None, "phase": "", "stall_seconds": None,
            "finished_at": None, "result": "running"}
    base.update(kw)
    return base


# ── 1. a Trail's life, start to finish ──────────────────────────────────────
print("a render record, from start to finish")
t = render_log.Trail("graphics render", os.path.join(ROOT, *COMP_REL.split("/")))
t.output(10, 300, "capture")
t.output(250, 300, "capture")
t.output(120, 300, "capture")          # workers can report out of order: the count must never go backwards
t.finish("ok")
got = render_log.recent(5)
check("the record is written to disk", len(got) == 1, got)
r = got[0] if got else {}
check("it keeps the highest frame count seen", r.get("frames_done") == 250, r.get("frames_done"))
check("it keeps the total", r.get("frames_total") == 300)
check("it records how it ended", r.get("result") == "ok" and r.get("finished_at"))
check("the composition path is relative to the engine (no home folder, no account name)",
      r.get("target") == COMP_REL, r.get("target"))
check("a finished render reads as finished", render_log.verdict(r) == "finished")

# ── 2. the three ways a render goes wrong, told apart ───────────────────────
print("\nfroze vs crawled vs stopped")
crawled = rec(started_at=NOW - 9 * 3600, written_at=NOW - 3600, first_frame_at=NOW - 9 * 3600 + 60,
              last_output_at=NOW - 3600 - 5, frames_done=812, frames_total=2700)
d = render_log.describe(crawled, NOW)
check("a render stopped from outside reads as never finished", "never finished" in d, d)
check("it says how far it got", "frame 812 of 2,700" in d, d)
check("it gives the real speed", "frames/s" in d, d)
check("it says what the whole render would have taken at that speed", "at that speed the whole thing takes" in d, d)
check("a render that kept counting frames is NOT called frozen", "FROZE" not in d, d)

froze = rec(started_at=NOW - 5 * 3600, written_at=NOW - 3600, first_frame_at=NOW - 5 * 3600 + 60,
            last_output_at=NOW - 4 * 3600, frames_done=400, frames_total=2700, stall_seconds=600)
d = render_log.describe(froze, NOW)
check("a renderer that went silent while the engine waited reads as FROZE", "FROZE" in d, d)
check("it says the stall watcher fired", "stall watcher" in d, d)

live = rec(started_at=NOW - 600, written_at=NOW - 5, first_frame_at=NOW - 550, last_output_at=NOW - 5,
           frames_done=900, frames_total=2700)
check("a render being rewritten right now reads as still running", render_log.verdict(live, NOW) == "still running right now")

never_started = rec(started_at=NOW - 3600, written_at=NOW - 60 * 5)
d = render_log.describe(never_started, NOW)
check("a render that never printed progress says it never really started", "never really started" in d, d)

# ── 3. two renders at the same time ─────────────────────────────────────────
print("\nrenders that overlapped")
a = rec(started_at=NOW - 7200, written_at=NOW - 3600)
b = rec(started_at=NOW - 5400, written_at=NOW - 1800)
lines = render_log.summarize([b, a], NOW)
check("overlapping renders are called out", any("Two ran at the same time" in ln for ln in lines), lines)
seq_a = rec(started_at=NOW - 7200, finished_at=NOW - 6000, written_at=NOW - 6000, result="ok")
seq_b = rec(step="final bake", started_at=NOW - 5990, finished_at=NOW - 5800, written_at=NOW - 5800, result="ok")
lines = render_log.summarize([seq_b, seq_a], NOW)
check("a render followed by its bake is NOT overlap", not any("same time" in ln for ln in lines), lines)

# ── 4. a step that is silent by design ──────────────────────────────────────
print("\nthe bake prints nothing on purpose")
bake = rec(step="final bake", reports_progress=False, started_at=NOW - 3 * 3600, written_at=NOW - 3600)
d = render_log.describe(bake, NOW)
check("a silent bake is not called 'never really started'", "never really started" not in d, d)
check("it still says how long it ran", "ran 2h 00m" in d, d)

# ── 5. the real render wrapper writes the record from the renderer's output ──
print("\nreel_render writes the record from real progress output")
import reel_render   # noqa: E402

fake_ok = [sys.executable, "-c",
           "import sys,time\n"
           "for i in range(1,21):\n"
           "    sys.stdout.write(f'Streaming frame {i}/20\\r'); sys.stdout.flush(); time.sleep(0.01)\n"
           "print()"]
comp = os.path.join(ROOT, *COMP_REL.split("/"))
before = {x.get("started_at") for x in render_log.recent(20)}
rc = reel_render._run_render_watched(fake_ok, comp_dir=comp)
new = [x for x in render_log.recent(20) if x.get("started_at") not in before]
check("the wrapper returns the renderer's exit code", rc == 0, rc)
check("it wrote one new record", len(new) == 1, new)
n = new[0] if new else {}
check("the record carries the frame count parsed from the output", n.get("frames_done") == 20 and n.get("frames_total") == 20, n)
check("the record says it finished", n.get("result") == "ok", n.get("result"))
check("the record names the composition that ran", n.get("target") == COMP_REL, n.get("target"))

fake_fail = [sys.executable, "-c", "import sys; print('Streaming frame 3/40'); sys.exit(3)"]
before = {x.get("started_at") for x in render_log.recent(20)}
rc = reel_render._run_render_watched(fake_fail, comp_dir=comp)
new = [x for x in render_log.recent(20) if x.get("started_at") not in before]
check("a failed render keeps its exit code", rc == 3, rc)
check("a failed render is recorded as failed, with how far it got",
      bool(new) and new[0].get("result") == "failed (exit 3)" and new[0].get("frames_done") == 3, new)

fake_trace = [sys.executable, "-c",
              "print('[Render:trace] {\"phase\":\"capture\",\"framesCompleted\":7,\"totalFrames\":30}')"]
before = {x.get("started_at") for x in render_log.recent(20)}
reel_render._run_render_watched(fake_trace, comp_dir=comp)
new = [x for x in render_log.recent(20) if x.get("started_at") not in before]
check("the trace-line form of progress is read too",
      bool(new) and new[0].get("frames_done") == 7 and new[0].get("frames_total") == 30 and new[0].get("phase") == "capture", new)

# ── 6. the evidence script and the collector ────────────────────────────────
print("\nthe evidence script runs, and the report carries it")
py = sys.executable
p = subprocess.run([py, os.path.join(ROOT, "product", "problem_evidence.py")], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=120, cwd=ROOT)
check("problem_evidence.py exits cleanly", p.returncode == 0, p.stderr[-400:])
for head in ("### This computer right now", "### Renders and bakes"):
    check(f"it prints '{head}'", head in p.stdout, p.stdout[:400])
check("it never prints the home folder", os.path.expanduser("~") not in p.stdout)

out = os.path.join(TMP, "problem-report.md")
env = dict(os.environ, REPORT_OUT=out)
bash = "bash"
q = subprocess.run([bash, os.path.join(ROOT, "scripts", "collect-report.sh"), "--quiet"], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=300, cwd=ROOT, env=env)
body = open(out, encoding="utf-8").read() if os.path.exists(out) else ""
check("the collector writes the report where it was told to", bool(body), q.stderr[-400:])
check("the report still has the setup half", "### Tools" in body and "### Setup check" in body)
check("the report now has what the engine was doing", "### This computer right now" in body)
check("the report carries the changes her Claude made to the engine", "### Changes made to this engine" in body)
check("'What happened' stays last, for Claude to fill in",
      body.rfind("### What happened") > body.rfind("### Changes made to this engine")
      > body.rfind("### This computer right now") >= 0)

if fails:
    print(f"\nFAILED: {len(fails)}")
    sys.exit(1)
print("\nall problem-report checks pass")
