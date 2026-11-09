#!/usr/bin/env python3
"""test_render_partial_layers.py — a render of SOME of the reel's layers is judged on the elements it holds.

The render gate opens the finished file and refuses it when it is blank at a moment the caption-plan puts an
element on screen (test_render_proves_itself.py). It used to ask EVERY render for EVERY plan element. A
render of one layer (LAYER=captions / hook / takeover / elements for separate layers, the hook / front split
behind mode renders, a one-style caption overlay) never draws the other layers' elements, so a correct
render was refused: "the render is EMPTY where the plan says an element is on screen".

Now a plan time is asked of a render only when its composition holds a clip for that element (element i on
lane 7 + i, a breakaway card on lane 6, as build-reel-type.py lays them out). A full composition holds every
element, so it is judged exactly as before, and one that cannot be read with certainty (no index.html, a
sub-composition) still has every plan time checked.

Run:  python3 product/tests/test_render_partial_layers.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reel_render as rr

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def overlay(path, visible, dur=10):
    """A transparent ProRes 4444 whose alpha is solid only inside the given (start, end) windows."""
    en = "+".join(f"between(t,{a},{b})" for a, b in visible) or "0"
    fc = ("[0:v]format=gray[m0];"
          f"[m0]drawbox=x=80:y=200:w=200:h=120:color=white:t=fill:enable='{en}'[mask];"
          "[1:v][mask]alphamerge[o]")
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", f"color=black:s=360x640:d={dur}:r=30",
                    "-f", "lavfi", "-i", f"color=white:s=360x640:d={dur}:r=30",
                    "-filter_complex", fc, "-map", "[o]",
                    "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", path], check=True)
    return path


def comp(job, name, clips, extra=""):
    """A composition shaped like build-reel-type.py writes it: the root, then one clip per element."""
    d = os.path.join(job, name)
    os.makedirs(d, exist_ok=True)
    body = "\n".join(f'<div class="clip" id="{cid}" data-start="{s:.2f}" data-duration="{du:.2f}" '
                     f'data-track-index="{lane}"><div></div></div>' for cid, s, du, lane in clips)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
        fh.write('<!doctype html><html><body>\n<div id="root" data-composition-id="reel" data-start="0" '
                 f'data-duration="10.00" data-width="1080" data-height="1920">\n{body}\n{extra}</div>\n'
                 '<script>window.__timelines={};</script></body></html>')
    return d


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_render_partial_layers: skipped (ffmpeg/ffprobe not installed)")
        return 0
    tmp = tempfile.mkdtemp(prefix="render-layers-")
    try:
        job = os.path.join(tmp, "projects", "job")
        os.makedirs(job)
        with open(os.path.join(job, "caption-plan.json"), "w", encoding="utf-8") as fh:
            json.dump({"elements": [{"kind": "star", "at": 1.0}, {"kind": "counter", "at": 4.0}],
                       "breakaways": [{"at": 7.0, "out": 9.0}],
                       "sfx": [{"file": "pop", "at": 5.5}]}, fh)     # a sound is never asked for a picture

        hook = ("clip-hookwrap", 0, 3.0, 2)
        caps = [("clip-cw0", 0.2, 3.0, 1), ("clip-cw1", 3.2, 3.0, 1), ("clip-cw2", 9.2, 0.7, 1)]
        els = [("clip-el0", 0, 2.5, 7), ("clip-el1", 0, 6.0, 8)]
        card = ("clip-bk0", 7.0, 2.0, 6)
        full = comp(job, "full", [hook] + caps + els + [card])
        only_hook = comp(job, "layer-hook", [hook])
        only_caps = comp(job, "layer-captions", caps)
        only_els = comp(job, "layer-elements", els)
        only_card = comp(job, "layer-takeover", [card])
        front = comp(job, "layer-front", caps + els + [card])

        # 1) the verdicts on real files
        hook_only = overlay(os.path.join(tmp, "hook.mov"), [(0, 3)])      # a correct hook-layer render
        for d in (only_hook, only_caps):
            ok, lines = rr._verify_render_has_content(hook_only, d)
            check(f"a correct {os.path.basename(d)} render is not refused for other layers' elements",
                  ok, lines)
        ok, lines = rr._verify_render_has_content(hook_only, full)
        check("a FULL render that lost its elements is still refused, naming when",
              not ok and any("4.00s" in l and "7.00s" in l for l in lines), lines)
        ok, lines = rr._verify_render_has_content(hook_only, only_els)
        check("an elements layer that lost its elements is still refused, for its own times only",
              not ok and any("4.00s" in l for l in lines) and not any("7.00s" in l for l in lines), lines)
        everything = overlay(os.path.join(tmp, "all.mov"), [(0, 10)])
        ok, lines = rr._verify_render_has_content(everything, full)
        check("a healthy full render passes", ok, lines)

        # 2) what each composition is asked for
        asked = getattr(rr, "_render_expect_times", lambda d: "(the gate has no per-layer check)")
        plan = rr._plan_expect_times(full)
        check("the plan's on-screen times are unchanged (sound cues never count)", plan == [1.0, 4.0, 7.0], plan)
        want = {full: [1.0, 4.0, 7.0], front: [1.0, 4.0, 7.0], only_els: [1.0, 4.0], only_card: [7.0],
                only_hook: [], only_caps: []}
        for d, exp in want.items():
            got = asked(d)
            check(f"{os.path.basename(d)} is asked only for the elements it holds", got == exp, got)

        # 3) when the composition cannot be read with certainty, every plan time is checked, as before
        nohtml = os.path.join(job, "no-index")
        os.makedirs(nohtml)
        check("no index.html: every plan time", asked(nohtml) == [1.0, 4.0, 7.0])
        sub = comp(job, "with-subcomp", [hook], extra='<div data-composition-src="part.html" data-start="0" '
                                                      'data-duration="10" data-track-index="3"></div>')
        check("a sub-composition: every plan time", asked(sub) == [1.0, 4.0, 7.0])
        rel = comp(job, "relative-start", [hook], extra='<div class="clip" data-start="clip-hookwrap + 1" '
                                                        'data-duration="2" data-track-index="7"></div>')
        check("a clip timed by reference: every plan time", asked(rel) == [1.0, 4.0, 7.0])
        bare = comp(job, "no-clips", [])
        check("no timed clip at all: every plan time", asked(bare) == [1.0, 4.0, 7.0])

        # 4) a composition that draws elements draws them all, so one with no clip on its lane was DROPPED
        #    (a kind the builder does not draw), never left out on purpose: its moment is still asked for
        dropped = comp(job, "elements-one-dropped", caps + [els[0]])
        check("an element the builder dropped is still asked for", asked(dropped) == [1.0, 4.0], asked(dropped))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_render_partial_layers: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_render_partial_layers: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
