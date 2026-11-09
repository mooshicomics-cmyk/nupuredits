#!/usr/bin/env python3
"""test_render_cache_waivers.py — a render that passed WITH a check switched off is never reused as clean.

reel_render.py caches a clean render: an identical re-run is a no-op ("unchanged since last clean render").
The cache key left out the settings that loosen the gate (--no-contrast, --subject-max,
REEL_ALLOW_DEAD_TARGETS=1, REEL_SKIP_ALPHA_CHECK=1), so a render that passed with one of them was later
handed back as "gated clean" to a run that asked for the full gate, with no check at all. Each is now part of
the key when it is in force. A run with none of them keeps the key it always had, so an existing cache
entry stays valid and nothing re-renders just because the engine was updated.

HyperFrames is replaced by a stand-in `npx` on PATH (its check and render are not what is tested here);
every check reel_render runs on the finished file runs for real.

Run:  python3 product/tests/test_render_cache_waivers.py
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

fails, total = [], 0

FAKE_NPX = r'''#!{py}
"""Stand-in for `npx hyperframes@<pin> check|render`, steered by FAKE_* environment variables."""
import os, shutil, sys
a = sys.argv[1:]
cmd = a[1] if len(a) > 1 else ""
if cmd == "check":
    if os.environ.get("FAKE_CONTRAST_FAIL") and "--no-contrast" not in a:
        print("Contrast")
        print("  ✗ contrast: text reads 1.3:1, fails WCAG AA")
        print("◇  Check failed")
        sys.exit(1)
    for sel in filter(None, os.environ.get("FAKE_DEAD", "").split(",")):
        print(f"  ⚠ console_warning: GSAP target {{sel}} not found. https://gsap.com")
    print("◇  Check passed")
    sys.exit(0)
if cmd == "render":
    shutil.copy(os.environ["FAKE_RENDER_SRC"], a[a.index("--output") + 1])
    print("Render complete")
    sys.exit(0)
sys.exit(2)
'''


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-300:]) if detail else ''}")


def overlay(path, box=None, opaque=False):
    """1 s of 1080x1920 ProRes 4444. Solid white inside `box` (x, y, w, h), transparent elsewhere; or, with
    opaque=True, alpha 255 on every pixel (a broken 'transparent' render)."""
    if opaque:
        fc = "[0:v]format=gray,lutyuv=y=255[m];[1:v][m]alphamerge[o]"
    else:
        x, y, w, h = box
        fc = f"[0:v]format=gray,drawbox=x={x}:y={y}:w={w}:h={h}:color=white:t=fill[m];[1:v][m]alphamerge[o]"
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=black:s=1080x1920:d=1:r=10",
                    "-f", "lavfi", "-i", "color=white:s=1080x1920:d=1:r=10",
                    "-filter_complex", fc, "-map", "[o]",
                    "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", path], check=True)
    return path


def job(root, name, zones=None):
    """A job folder with one small composition in it (and her measured subject box when given)."""
    d = os.path.join(root, "projects", name)
    comp = os.path.join(d, "hf-reel-type-test")
    os.makedirs(comp)
    with open(os.path.join(comp, "index.html"), "w", encoding="utf-8") as fh:
        fh.write('<!doctype html><html><body><div id="root" data-composition-id="reel" data-start="0" '
                 'data-duration="1" data-width="1080" data-height="1920"><div class="clip" id="c0" '
                 'data-start="0" data-duration="1" data-track-index="1">x</div></div></body></html>')
    if zones:
        with open(os.path.join(d, "subject-zones.json"), "w", encoding="utf-8") as fh:
            json.dump({"subject": dict(zip(("left", "head_top", "right", "chin_bottom"), zones))}, fh)
    return comp


def engine_copy(root):
    """The engine's product/*.py in a scratch folder, so the render records reel_render keeps
    (_local/render-log beside product/) land there and never in the real engine."""
    eng = os.path.join(root, "engine")
    os.makedirs(os.path.join(eng, "product"))
    for f in os.listdir(PRODUCT):
        if f.endswith(".py"):
            shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
    if os.path.exists(os.path.join(os.path.dirname(PRODUCT), "product.json")):
        shutil.copy(os.path.join(os.path.dirname(PRODUCT), "product.json"), eng)
    return os.path.join(eng, "product", "reel_render.py")


def render(script, comp, out, env, *flags):
    r = subprocess.run([sys.executable, script, "render", comp, "-o", out, *flags],
                       capture_output=True, text=True, env=env, timeout=600)
    return r.returncode, r.stdout + r.stderr


def main():
    if os.name == "nt":
        print("test_render_cache_waivers: skipped on Windows (the stand-in npx is a POSIX script)")
        return 0
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_render_cache_waivers: skipped (ffmpeg/ffprobe not installed)")
        return 0
    tmp = tempfile.mkdtemp(prefix="render-waivers-")
    try:
        script = engine_copy(tmp)
        fake = os.path.join(tmp, "bin")
        os.makedirs(fake)
        with open(os.path.join(fake, "npx"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_NPX.format(py=sys.executable))
        os.chmod(os.path.join(fake, "npx"), 0o755)
        base = {k: v for k, v in os.environ.items()
                if k not in ("REEL_ALLOW_DEAD_TARGETS", "REEL_SKIP_ALPHA_CHECK", "REELS_RENDER_STALL_SECONDS")}
        base.update(PATH=fake + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                    REELS_RENDER_STALL_SECONDS="0")
        clean = overlay(os.path.join(tmp, "clean.mov"), box=(120, 1300, 300, 200))   # in the safe zone
        on_face = overlay(os.path.join(tmp, "on-face.mov"), box=(480, 700, 120, 120))  # ~5% of her box
        opaque = overlay(os.path.join(tmp, "opaque.mov"), opaque=True)
        her = (300, 500, 780, 1100)

        # (waiver, how the first run relaxes the gate, what the second run must now refuse with, exit code)
        cases = [
            ("REEL_ALLOW_DEAD_TARGETS=1", {"FAKE_DEAD": "#hk0"}, {"REEL_ALLOW_DEAD_TARGETS": "1"}, [],
             clean, None, "animation target(s) match nothing", 0),   # a warning, never a wall
            ("--no-contrast", {"FAKE_CONTRAST_FAIL": "1"}, {}, ["--no-contrast"],
             clean, None, "check flagged", 0),
            ("--subject-max", {}, {}, ["--subject-max", "0.5"],
             on_face, her, "sits on her face", 0),     # a face hit is said, never refused: she always gets her reel
            ("REEL_SKIP_ALPHA_CHECK=1", {}, {"REEL_SKIP_ALPHA_CHECK": "1"}, [],
             opaque, None, "rendered FULLY OPAQUE", 1),
        ]
        for i, (name, steer, waive_env, waive_flags, src, zones, refusal, rc_want) in enumerate(cases):
            comp = job(tmp, f"waiver-{i}", zones)
            out = os.path.join(os.path.dirname(comp), "renders", "layer.mov")
            env = dict(base, FAKE_RENDER_SRC=src, **steer)
            rc1, said1 = render(script, comp, out, dict(env, **waive_env), *waive_flags)
            check(f"{name}: the waived render passes", rc1 == 0, said1)
            rc2, said2 = render(script, comp, out, env)
            check(f"{name}: a full-gate run does not reuse the waived pass", "reusing" not in said2, said2)
            check(f"{name}: the full gate runs and says it (a check finding or face hit is said and renders; an opaque layer still refuses)", rc2 == rc_want and refusal in said2, (rc2, said2))

        # No waiver in force: the key is exactly the one the engine always wrote, so a clean render cached
        # before an update is still reused after it, and nothing re-renders for nothing.
        comp = job(tmp, "no-waiver")
        out = os.path.join(os.path.dirname(comp), "renders", "layer.mov")
        env = dict(base, FAKE_RENDER_SRC=clean)
        rc1, said1 = render(script, comp, out, env)
        rc2, said2 = render(script, comp, out, env)
        check("no waiver: the second identical run is reused", rc1 == 0 and rc2 == 0 and "reusing" in said2,
              said1 + said2)
        with open(os.path.join(comp, rr.STATE_DIR, "state.json"), encoding="utf-8") as fh:
            keys = set(json.load(fh))
        old_key = rr.comp_hash(comp, extra="strict=0|format=mov|sz=report|subj=None", skip=out)
        check("no waiver: the cache key is the one written before this fix", keys == {old_key}, keys)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_render_cache_waivers: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_render_cache_waivers: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
