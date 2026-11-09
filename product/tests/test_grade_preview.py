#!/usr/bin/env python3
"""Guards: her Filter on the visual editor looks like the filter her export bakes in.

2026-10-16 the page previewed each Filter with hand-picked CSS that only resembled the export's ffmpeg grade (3 to 8.5
of 255 apart on her footage, and "Cool" pulled blue DOWN on the page while the export pushed it up). The page now
applies one color matrix per look, fitted from the export's own grade.

  same        the page's GRADE_MATRIX is exactly product/video_grade.py PREVIEW_MATRIX
  current     refitting from ffmpeg gives the same matrices (a look changed in LOOKS without a refit fails here)
  close       each matrix lands within 3 of 255 of ffmpeg's grade, on average, across the whole RGB cube
  looks       in a real browser, the page's filter on a color chart lands within 4 of 255 of the export's grade
              (skipped, and said so, without the headless browser)

Run: python3 product/tests/test_grade_preview.py
"""
import json, os, re, shutil, subprocess, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT); sys.path.insert(0, HERE)
import video_grade as vg  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}  -- {detail}")


def rgb(path, vf=None):
    vf = (vf + "," if vf else "") + "scale=320:240,format=rgb24"
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-f", "rawvideo", "-"], capture_output=True).stdout


def main():
    page = open(os.path.join(PRODUCT, "visual-editor", "editor.html"), encoding="utf-8").read()
    m = re.search(r"const GRADE_MATRIX = (\{.*?\});", page)
    check("same: the page carries GRADE_MATRIX", bool(m))
    if m:
        check("same: the page's matrices are the engine's", json.loads(m.group(1)) == vg.PREVIEW_MATRIX)
    check("same: every export look has a preview", set(vg.PREVIEW_MATRIX) == set(vg.LOOKS), (set(vg.PREVIEW_MATRIX), set(vg.LOOKS)))
    for k in vg.LOOKS:
        fit, err = vg.fit_preview(k)
        drift = max(abs(a - b) for ra, rb in zip(fit, vg.PREVIEW_MATRIX.get(k, [[9] * 4] * 3)) for a, b in zip(ra, rb))
        check(f"current: {k} matches a fresh fit from ffmpeg", drift <= 0.01, drift)
        check(f"close: {k} within 3 of 255 of the export's grade", err <= 3.0, err)

    try:
        import test_visual_editor_page as T
        tools = T.find_tools()
    except Exception:
        tools = None
    if not tools:
        print("test_grade_preview: browser part skipped (no headless browser on this computer)")
    else:
        node, pup, chrome = tools[:3]
        tmp = tempfile.mkdtemp(prefix="grade-preview-")
        try:
            src = os.path.join(tmp, "src.png")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240", "-frames:v", "1", src], check=True)
            defs = "".join(f'<filter id="g-{k}" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="'
                           + " ".join(" ".join(str(x) for x in [r[0], r[1], r[2], 0, r[3]]) for r in mx) + ' 0 0 0 1 0"/></filter>'
                           for k, mx in vg.PREVIEW_MATRIX.items())
            for k in vg.PREVIEW_MATRIX:
                open(os.path.join(tmp, f"{k}.html"), "w", encoding="utf-8").write(
                    f'<html><body style="margin:0"><svg width="0" height="0" style="position:absolute">{defs}</svg>'
                    f'<img src="src.png" style="width:320px;height:240px;display:block;filter:url(#g-{k})"></body></html>')
            js = os.path.join(tmp, "shoot.js")
            open(js, "w", encoding="utf-8").write(
                'const p=require(process.argv[2]);(async()=>{const b=await p.launch({executablePath:process.argv[3],headless:"new",'
                'args:["--allow-file-access-from-files"]});const pg=await b.newPage();await pg.setViewport({width:320,height:240});'
                'for(const k of process.argv[5].split(",")){await pg.goto(`file://${process.argv[4]}/${k}.html`,{waitUntil:"load"});'
                'await new Promise(r=>setTimeout(r,150));await pg.screenshot({path:`${process.argv[4]}/page-${k}.png`});}await b.close();})();')
            subprocess.run([node, js, pup, chrome, tmp, ",".join(vg.PREVIEW_MATRIX)], check=True, capture_output=True, timeout=120)
            for k in vg.PREVIEW_MATRIX:
                a, b = rgb(os.path.join(tmp, f"page-{k}.png")), rgb(src, vg.LOOKS[k])
                diff = sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))
                check(f"looks: {k} on the page lands within 4 of 255 of the export", len(a) == len(b) and diff <= 4.0, round(diff, 2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_grade_preview: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f[:300])
        return 1
    print(f"test_grade_preview: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
