#!/usr/bin/env python3
"""Guards: "Send my cut" never leaves her waiting on a cut update that hung or died with no word.

Buyer report 2026-10-19 (Windows, v2.3.0): the send landed, the background cut update never finished, and the page
kept "Send my cut" forever. The update had no time limit and its output went nowhere. Now (visual_editor._stitch):

  hang      a lean update that runs past its limit is stopped, with everything it started, and becomes a plain
            Refuse (the page shows it from last-problem.json)
  error     a failing update says its last line in the Refuse, never "(above)" that the page can't show
  log       either way review/last-stitch.log keeps what it printed, for /report-a-problem
  ok        a clean update returns quietly and still logs

Run: python3 product/tests/test_send_cut_never_hangs.py
"""
import os, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}: {detail}")


tmp = tempfile.mkdtemp()
real_root = ve.ROOT
try:
    ve.ROOT = tmp
    scripts = os.path.join(tmp, ".claude", "skills", "rough-cut", "scripts")
    os.makedirs(scripts)
    stitch = os.path.join(scripts, "stitch-cut.sh")
    jd = os.path.join(tmp, "projects", "reel")
    os.makedirs(os.path.join(jd, "review"))
    pidf = os.path.join(tmp, "child.pid")

    def fake(body):
        with open(stitch, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n" + body + "\n")

    # hang: prints, starts a child that would outlive bash, then waits forever
    fake(f'echo "cleaning edges"\nsleep 300 &\necho $! > "{pidf}"\nwait')
    ve.LEAN_STITCH_TIMEOUT = 2
    t0 = time.time()
    try:
        ve._stitch(jd, lean=True, log=lambda *a: None)
        check("hang refuses", False, "no Refuse")
    except ve.Refuse as e:
        check("hang refuses", "took more than" in str(e) and "Send my cut" in str(e), str(e))
    check("hang stops on time", time.time() - t0 < 20, f"{time.time() - t0:.1f}s")
    log = open(os.path.join(jd, "review", "last-stitch.log"), encoding="utf-8").read()
    check("hang is logged", "cleaning edges" in log and "hung" in log, log)
    if os.name != "nt" and os.path.exists(pidf):
        child = int(open(pidf, encoding="utf-8").read().strip())
        time.sleep(0.3)
        try:
            os.kill(child, 0)
            alive = True
        except OSError:
            alive = False
        check("hang stops its children too", not alive, f"pid {child} still running")

    # error: the last line it printed is in the message
    ve.LEAN_STITCH_TIMEOUT = 60
    fake('echo "step 1"\necho "ffmpeg: Invalid data found when processing input" >&2\nexit 3')
    try:
        ve._stitch(jd, lean=True, log=lambda *a: None)
        check("error refuses", False, "no Refuse")
    except ve.Refuse as e:
        check("error names its last line", "Invalid data found" in str(e) and "(above)" not in str(e), str(e))
    log = open(os.path.join(jd, "review", "last-stitch.log"), encoding="utf-8").read()
    check("error is logged", "step 1" in log and "Invalid data" in log, log)

    # ok
    fake('echo "all good"')
    try:
        ve._stitch(jd, lean=True, log=lambda *a: None)
        check("ok passes", True)
    except ve.Refuse as e:
        check("ok passes", False, str(e))
    check("ok is logged", "all good" in open(os.path.join(jd, "review", "last-stitch.log"), encoding="utf-8").read())
finally:
    ve.ROOT = real_root
    shutil.rmtree(tmp, ignore_errors=True)

print(f"{total - len(fails)}/{total} passed")
for f in fails:
    print("  FAIL", f)
sys.exit(1 if fails else 0)
