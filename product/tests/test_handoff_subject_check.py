#!/usr/bin/env python3
"""The CapCut handoff of a well-done reel checks text against HER measurement, instead of saying she was never measured.

capcut_handoff.py called finalize() without the job, and it never lays the cut through add_cut (the call that
records the job for the per-reel builders), so the face check searched upward from the CapCut draft folder, found
no subject-zones.json, and printed "her footage was never measured" for a job that was: the check never ran.

Run: python3 product/tests/test_handoff_subject_check.py   (Windows: python)
"""
import ast, importlib.util, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:200]})"))
    if not cond:
        fails.append(name)


with open(os.path.join(ROOT, "product", "capcut_handoff.py"), encoding="utf-8") as fh:
    tree = ast.parse(fh.read())
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "finalize"]
check("the handoff calls finalize once", len(calls) == 1, len(calls))
check("...and hands it the job, so the face check reads her measurement",
      bool(calls) and any(k.arg == "job" for k in calls[0].keywords), [k.arg for k in calls[0].keywords] if calls else None)

spec = importlib.util.spec_from_file_location("subject_place", os.path.join(ROOT, "product", "subject_place.py"))
sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
tmp = tempfile.mkdtemp(prefix="handoff-subject-")
try:
    job = os.path.join(tmp, "projects", "my-reel")
    os.makedirs(job)
    with open(os.path.join(job, "subject-zones.json"), "w", encoding="utf-8") as fh:
        json.dump({"subject": {"head_top": 380, "chin_bottom": 1164, "left": 152, "right": 821},
                   "zones": {"below": {"top": 1224, "bottom": 1620, "usable": True, "center_y_norm": -0.48}}}, fh)
    draft = {"materials": {"texts": []}, "tracks": [], "canvas_config": {"width": 1080, "height": 1920}}
    _br, lines = sp.report(draft, job)
    check("given the job folder, a measured job is checked (not 'never measured')",
          not any("never measured" in l for l in lines) and any("subject" in l for l in lines), lines)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "the handoff checks text against her measurement"))
sys.exit(1 if fails else 0)
