#!/usr/bin/env python3
"""test_render_takeover_lookup.py — a takeover keeps its waiver wherever the render is written.

A full-screen takeover covers the creator BY DESIGN. The type builder records those moments in
owns-screen.json (beside the composition and in the job folder), and the subject check does not count a
frame inside one. It looked for that file by walking up from the render's OUTPUT path, so a render written
outside the job folder (`reel_render.py render <comp> -o <out.mov>`, the documented form) found nothing,
lost the waiver, and a correct render was refused with exit 6 ("sits on her face"). It is now looked up
from the composition first, then from the output as before.

HyperFrames is replaced by a stand-in `npx` on PATH; the subject check itself runs for real.

Run:  python3 product/tests/test_render_takeover_lookup.py
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

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import reel_render as rr
import subject_guard

fails, total = [], 0

FAKE_NPX = r'''#!{py}
"""Stand-in for `npx hyperframes@<pin> check|render`: the check passes, the render copies FAKE_RENDER_SRC."""
import os, shutil, sys
a = sys.argv[1:]
if len(a) > 1 and a[1] == "check":
    print("◇  Check passed")
    sys.exit(0)
if len(a) > 1 and a[1] == "render":
    shutil.copy(os.environ["FAKE_RENDER_SRC"], a[a.index("--output") + 1])
    sys.exit(0)
sys.exit(2)
'''

HER = (300, 500, 780, 1100)          # her measured head-to-chin box: left, head_top, right, chin_bottom
TAKEOVER = (0.2, 0.8)                # the declared moment that owns the screen


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-300:]) if detail else ''}")


def overlay(path, on_her):
    """1 s of 1080x1920 ProRes 4444: solid across her box while t is inside `on_her`, clear otherwise."""
    a, b = on_her
    x0, y0, x1, y1 = HER
    fc = (f"[0:v]format=gray,drawbox=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}:color=white:t=fill:"
          f"enable='between(t,{a},{b})'[m];[1:v][m]alphamerge[o]")
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=black:s=1080x1920:d=1:r=10",
                    "-f", "lavfi", "-i", "color=white:s=1080x1920:d=1:r=10",
                    "-filter_complex", fc, "-map", "[o]",
                    "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", path], check=True)
    return path


def engine_copy(root):
    """The engine's product/*.py in a scratch folder, so reel_render's own records land there."""
    eng = os.path.join(root, "engine")
    os.makedirs(os.path.join(eng, "product"))
    for f in os.listdir(PRODUCT):
        if f.endswith(".py"):
            shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
    return os.path.join(eng, "product", "reel_render.py")


def main():
    if os.name == "nt":
        print("test_render_takeover_lookup: skipped on Windows (the stand-in npx is a POSIX script)")
        return 0
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_render_takeover_lookup: skipped (ffmpeg/ffprobe not installed)")
        return 0
    tmp = tempfile.mkdtemp(prefix="render-takeover-")
    try:
        script = engine_copy(tmp)
        job = os.path.join(tmp, "projects", "job")
        comp = os.path.join(job, "hf-reel-type-test")
        os.makedirs(comp)
        with open(os.path.join(comp, "index.html"), "w", encoding="utf-8") as fh:
            fh.write('<!doctype html><html><body><div id="root" data-composition-id="reel" data-start="0" '
                     'data-duration="1" data-width="1080" data-height="1920"><div class="clip" id="tk0" '
                     'data-start="0.2" data-duration="0.6" data-track-index="1">x</div></div></body></html>')
        with open(os.path.join(job, "subject-zones.json"), "w", encoding="utf-8") as fh:
            json.dump({"subject": dict(zip(("left", "head_top", "right", "chin_bottom"), HER))}, fh)
        owns = {"windows": [list(TAKEOVER)]}
        for d in (comp, job):                  # where the type builder writes it: both places
            with open(os.path.join(d, "owns-screen.json"), "w", encoding="utf-8") as fh:
                json.dump(owns, fh)
        takeover = overlay(os.path.join(tmp, "takeover.mov"), (0.3, 0.7))   # covers her inside the window
        stray = overlay(os.path.join(tmp, "stray.mov"), (0.0, 0.15))         # covers her OUTSIDE it

        # 1) the check itself, with the render written outside the job folder
        elsewhere = os.path.join(tmp, "elsewhere")
        os.makedirs(elsewhere)
        out = os.path.join(elsewhere, "takeover.mov")
        shutil.copy(takeover, out)
        status, lines = rr._subject_check(out, comp)
        check("a takeover written outside the job is still recognised as a takeover", status == "ok", lines)
        box = subject_guard.box_from_zones(os.path.join(job, "subject-zones.json"))
        rc, lines = subject_guard.report(out, box)
        check("the stand-alone check with no composition to ask behaves as before", rc == 1, lines)

        # 2) the whole gated render, end to end
        env = {k: v for k, v in os.environ.items() if k != "REELS_RENDER_STALL_SECONDS"}
        fake = os.path.join(tmp, "bin")
        os.makedirs(fake)
        with open(os.path.join(fake, "npx"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_NPX.format(py=sys.executable))
        os.chmod(os.path.join(fake, "npx"), 0o755)
        env.update(PATH=fake + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                   REELS_RENDER_STALL_SECONDS="0")

        def render(src, out_path):
            r = subprocess.run([sys.executable, script, "render", comp, "-o", out_path],
                               capture_output=True, text=True, env=dict(env, FAKE_RENDER_SRC=src), timeout=600)
            return r.returncode, r.stdout + r.stderr

        rc, said = render(takeover, os.path.join(elsewhere, "layer.mov"))
        check("-o outside the job: a correct takeover render is not refused", rc == 0, (rc, said))
        rc, said = render(takeover, os.path.join(job, "layers", "layer.mov"))
        check("-o inside the job: still passes, as before", rc == 0, (rc, said))
        rc, said = render(stray, os.path.join(elsewhere, "stray.mov"))
        check("a graphic on her face outside the declared moment is still caught and said, and she still gets it",
              rc == 0 and "sits on her face" in said and "Rendered anyway" in said, (rc, said))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_render_takeover_lookup: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_render_takeover_lookup: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
