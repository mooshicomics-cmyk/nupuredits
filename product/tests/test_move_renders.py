#!/usr/bin/env python3
"""Guards: a look she moved on her page exports where she put it.

2026-10-16 a count-up she moved 867 px down exported at the top: the move was written as the separate CSS translate /
rotate / scale properties, which her page honoured and the renderer ignores. A move is now ONE transform.

  written    _apply_nudge writes one transform (and never the separate properties), and a second move replaces the first
  rendered   a hook drawn, moved 600 px down and rendered for real: its ink lands 600 px lower than unmoved
             (skipped, and said so, on a computer without the render tools)

Run: python3 product/tests/test_move_renders.py
"""
import os, re, shutil, subprocess, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}  -- {detail}")


def ink_top(mov, at=1.0):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", mov, "-frames:v", "1",
                          "-vf", "alphaextract,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    W = 1080
    rows = [y for y in range(len(raw) // W) if max(raw[y * W:(y + 1) * W]) > 20]
    return rows[0] if rows else None


def main():
    tmp = tempfile.mkdtemp(prefix="move-renders-")
    try:
        page_dir = os.path.join(tmp, "p"); os.makedirs(page_dir)
        open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8").write("<html><head></head><body><div id=root></div></body></html>")
        ve._apply_nudge(tmp, "p", [0, 867])
        h = open(os.path.join(page_dir, "index.html"), encoding="utf-8").read()
        check("written: one transform", "transform:translate(0px,867px)" in h, h)
        check("written: never the separate properties the renderer ignores", not re.search(r"[{;]\s*(translate|rotate|scale)\s*:", h), h)
        ve._apply_nudge(tmp, "p", [10, 20, 1.5, 12, 500, 900])
        h = open(os.path.join(page_dir, "index.html"), encoding="utf-8").read()
        check("written: a second move replaces the first, size and angle around its center",
              h.count("ve-nudge") == 1 and "translate(10px,20px) rotate(12.00deg) scale(1.500)" in h and "transform-origin:500px 900px" in h, h)

        if not shutil.which("npx") or not shutil.which("ffmpeg"):
            print("test_move_renders: render part skipped (no render tools on this computer)")
        else:
            import lookbook
            out = {}
            for name, dy in (("still", 0), ("moved", 600)):
                d = os.path.join(tmp, name)
                r = lookbook.draw("hook", d, "a hook to move", 2.0, "Butter", comp_id=f"mv-{name}")
                rel = os.path.relpath(r["dir"], tmp)
                if dy:
                    ve._apply_nudge(tmp, rel, [0, dy])
                mov = os.path.join(tmp, f"{name}.mov")
                subprocess.run([sys.executable, os.path.join(PRODUCT, "reel_render.py"), "render", r["dir"], "-o", mov],
                               capture_output=True, text=True, timeout=600)
                out[name] = ink_top(mov) if os.path.isfile(mov) else None
            ok = None not in out.values() and abs((out["moved"] - out["still"]) - 600) <= 4
            check("rendered: a look moved 600 px down renders 600 px lower", ok, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_move_renders: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f[:500])
        return 1
    print(f"test_move_renders: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
