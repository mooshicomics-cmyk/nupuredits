#!/usr/bin/env python3
"""Rendered captions sit just under her chin, measured per reel, not at the pack's fixed height.

The rendered builder placed captions at the pack's fixed height (about y1152) unless a per-reel caption track
was written by hand, and nothing writes one. That height is chest on a subject framed high and her chin or
collar on one framed a little lower: on a real test reel the read-along sat on her collar and the subject
guard refused the render. With a measurement on file (workflows/subject-zones.py writes subject-zones.json)
the captions now start at the top of the open zone below her, which begins 60px under her lowest chin. Her
taught caption.zone picks the zone (below is the default); without a measurement, the pack's height stands.

Run: python3 product/tests/test_captions_under_chin.py   (Windows: python)
"""
import importlib.util, json, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("reel_type_harness", os.path.join(HERE, "test_reel_type_matching.py"))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)                      # its helpers only: the tests there run under __main__

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:200]})"))
    if not cond:
        fails.append(name)


def tops(html, cls):
    """The CSS top of every caption clip of one kind (capword = snap, buildwrap = karaoke)."""
    return {int(m) for m in re.findall(r'class="%s[^"]*" style="[^"]*top:(\d+)px' % cls, html)}


WORDS = "so here is the thing nobody tells you about starting".split()
ZONES = {"subject": {"head_top": 380, "chin_bottom": 1164},
         "zones": {"below": {"top": 1224, "bottom": 1620, "usable": True}}}

tmp = tempfile.mkdtemp(prefix="captions-under-chin-")
try:
    rt.shadow(tmp)
    print("1. single-word captions")
    rt.job(tmp, WORDS, {"duration": 5.0, "caption_mode": "single"})
    r, html = rt.build(tmp)
    before = tops(html, "capword")
    check("with no measurement, the pack's height stands", r.returncode == 0 and before and min(before) < 1224,
          (r.returncode, before, r.stderr[-300:]))
    check("...and the build says why", "no subject-zones.json" in r.stdout, r.stdout[-300:])
    with open(os.path.join(tmp, "projects", "qa-job", "subject-zones.json"), "w", encoding="utf-8") as fh:
        json.dump(ZONES, fh)
    r, html = rt.build(tmp)
    after = tops(html, "capword")
    check("measured: every caption sits just under her chin (zone top y1224 + half a line)", after == {1224 + 45}, after)
    check("...and the build says where", "just under her chin" in r.stdout and "y1224" in r.stdout, r.stdout[-300:])

    print("\n2. a karaoke line")
    rt.job(tmp, WORDS, {"duration": 5.0, "caption_mode": "build"})
    r, html = rt.build(tmp)
    k = tops(html, "buildwrap")
    check("a karaoke line sits under her chin too (its taller half)", k == {1224 + 90}, k)

    print("\n3. what still wins")
    rt.job(tmp, WORDS, {"duration": 5.0, "caption_mode": "single", "caption_track": [[0, 5, 1400]]})
    r, html = rt.build(tmp)
    check("a hand-written caption track still wins", tops(html, "capword") == {1400}, tops(html, "capword"))
    z = dict(ZONES, zones={"below": {"top": 1600, "bottom": 1620, "usable": False}})
    with open(os.path.join(tmp, "projects", "qa-job", "subject-zones.json"), "w", encoding="utf-8") as fh:
        json.dump(z, fh)
    rt.job(tmp, WORDS, {"duration": 5.0, "caption_mode": "single"})
    r, html = rt.build(tmp)
    check("no open zone below her: the pack's height, and it says so",
          tops(html, "capword") == before and "no open zone below her" in r.stdout, (tops(html, "capword"), r.stdout[-200:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "rendered captions sit just under her chin, measured per reel"))
sys.exit(1 if fails else 0)
