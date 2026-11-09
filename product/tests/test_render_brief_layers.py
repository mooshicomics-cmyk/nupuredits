#!/usr/bin/env python3
"""test_render_brief_layers.py — a layer that is on screen only briefly is never called empty.

The render gate opens the finished file and refuses it when it contains nothing. It used to look at 16 evenly
spaced frames and nowhere else. A separated takeover layer on a long reel draws for a second or two, every
one of those 16 frames can land outside it, and a correct render was refused: "the render contains NOTHING".
The file was fine; its alpha carried the takeover exactly where the composition put it.

Now the gate looks at the middle of every clip window the composition holds, which is where it says
something is drawn. A render that really is empty there is still refused.

The safe-zone measurement had the same blind spot from the other side: a full-frame takeover is a "full-bleed"
frame, which is rightly not held to the bands, but it was also counted as no ink at all, so a takeover-only
layer was reported as a fully transparent, probably broken render. A full-frame frame is real content.

Run:  python3 product/tests/test_render_brief_layers.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reel_render as rr   # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def overlay(path, windows, dur, box="x=80:y=200:w=200:h=120", size="360x640"):
    """A transparent ProRes 4444 whose alpha is solid inside `box` only during the (start, end) windows."""
    en = "+".join(f"between(t,{a},{b})" for a, b in windows) or "0"
    fc = ("[0:v]format=gray[m0];"
          f"[m0]drawbox={box}:color=white:t=fill:enable='{en}'[mask];"
          "[1:v][mask]alphamerge[o]")
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", f"color=black:s={size}:d={dur}:r=30",
                    "-f", "lavfi", "-i", f"color=white:s={size}:d={dur}:r=30",
                    "-filter_complex", fc, "-map", "[o]",
                    "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", path], check=True)
    return path


def comp(root, name, clips):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    body = "\n".join(f'<div class="clip" id="c{i}" data-start="{s:.2f}" data-duration="{du:.2f}" '
                     f'data-track-index="{lane}"><div></div></div>' for i, (s, du, lane) in enumerate(clips))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
        fh.write('<!doctype html><html><body><div id="root" data-composition-id="reel" data-start="0" '
                 f'data-duration="20" data-width="1080" data-height="1920">\n{body}\n</div></body></html>')
    return d


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_render_brief_layers: skipped (ffmpeg not installed)")
        return 0
    tmp = tempfile.mkdtemp(prefix="brief-layers-")
    try:
        dur = 20
        # A takeover on its own lane (5) for one second, 7.0-8.0 s. The 16 evenly spaced looks fall at
        # 6.875 s and 8.125 s on either side of it, so they all see nothing.
        tk = comp(tmp, "takeover", [(7.0, 1.0, 5)])
        brief = overlay(os.path.join(tmp, "brief.mov"), [(7.0, 8.0)], dur)
        check("the evenly spaced looks really do all miss this window (the test is meaningful)",
              all(not (7.0 <= dur * (i + 0.5) / 16 <= 8.0) for i in range(16)))
        ok, lines = rr._verify_render_has_content(brief, tk)
        check("a one-second takeover layer is not refused as empty", ok, lines)
        check("and nothing is said about it being empty", not any("NOTHING" in l for l in lines), lines)

        empty = overlay(os.path.join(tmp, "empty.mov"), [], dur)
        ok, lines = rr._verify_render_has_content(empty, tk)
        check("a render that is empty where the composition draws is still refused", not ok, lines)
        check("and the refusal says where it looked", any("composition draws something" in l for l in lines), lines)

        ok, lines = rr._verify_render_has_content(empty, os.path.join(tmp, "nowhere"))
        check("with no composition to read, an empty render is still refused the old way",
              not ok and any("every sampled frame" in l for l in lines), lines)

        # One whole-reel clip (a catalog caption style is built that way) whose words come and go: its middle
        # can fall between words, and that must never read as an empty render.
        whole = comp(tmp, "whole", [(0.0, 20.0, 1)])
        sparse = overlay(os.path.join(tmp, "sparse.mov"), [(2.9, 3.4), (12.9, 13.4)], dur)
        ok, lines = rr._verify_render_has_content(sparse, whole)
        check("a whole-reel clip that is blank at its middle is not refused", ok, lines)
        check("nor warned about as dropped", not any("completely empty" in l for l in lines), lines)

        # Lane 0 is the preview background some builds add; it never counts as somewhere the layer draws.
        bg = comp(tmp, "with-bg", [(0.0, 20.0, 0), (7.0, 1.0, 5)])
        check("the preview background lane is not looked at", rr._clip_sample_times(bg, dur) == [7.5],
              rr._clip_sample_times(bg, dur))

        many = comp(tmp, "many", [(i * 0.1, 0.08, 1) for i in range(150)])
        check("a reel with many clips is looked at a bounded number of times",
              len(rr._clip_sample_times(many, dur)) <= rr._MAX_CLIP_SAMPLES)

        # Safe zone: full-frame ink is content, not "nothing".
        full = overlay(os.path.join(tmp, "full.mov"), [(7.0, 8.0)], dur, box="x=0:y=0:w=iw:h=ih")
        status, br = rr._safe_zone_check(full)
        check("a full-frame takeover layer is measured as full-frame content, not as empty",
              status == "fullbleed" and br == [], (status, br))
        status, _br = rr._safe_zone_check(empty)
        check("a truly transparent layer is still reported as empty", status == "empty", status)
        status, _br = rr._safe_zone_check(brief)
        check("an ordinary overlay is still measured against the bands", status == "ok", status)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_render_brief_layers: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_render_brief_layers: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
