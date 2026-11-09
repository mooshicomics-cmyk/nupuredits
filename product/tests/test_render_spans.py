#!/usr/bin/env python3
"""test_render_spans.py — caption layers render only where they are on screen, with the full render as fallback.

A caption layer that is blank for part of the reel (captions that move to a new spot half-way through are two
layers, each blank for the other's stretch) used to render every frame of the reel. render_spans.py plans the
stretches it is on screen, reel_render.py renders one time-shifted copy per stretch and stitches them back
into the same full-length .mov, and a sidecar (<out>.spans.json) says where each stretch sits so CapCut
placement lays one clip per stretch. Anything off falls back to the full render, said in one plain line.

Covered here:
  1. the plan: merge, split only past GAP, pad, whole frames; no plan when nothing is worth trimming or the
     page cannot be read with certainty
  2. the span page: clips shifted to the stretch, the rest parked, the timeline driven from the stretch start,
     the root lasting exactly the stretch's frames
  3. plan files: write / stale / clear, and the builders' wiring
  4. the sidecar round trip, and a sidecar that does not belong to the file is ignored
  5. reassembly: stretch renders land on their own frames, transparent between, frame count exact
  6. consumers: build-overlay's spans_for() / inject() (one segment per stretch, never more clips than the
     footage, so the magnet keeps the footage as its main track), and reel_render composite putting the
     stretches at the right times over footage
  5b. the filler carries the renders' own color tags, so a bake overlaying the stitched layer under a sound mix
     never rebuilds its filtergraph mid-reel (a buyer's report, 2026-10-18: untagged filler between bt709 renders stalled
     build-reel-mp4.py's single graph for good on ffmpeg 9), and a layer stitched before that fix re-renders
  7. reel_render end to end with a stand-in HyperFrames that draws each clip in its own window: the stitched
     file matches a full render frame for frame; a failed stretch, a wrong-length stretch and
     REEL_FULL_RENDER=1 each give the ordinary full render and no sidecar; an old sidecar never survives a
     fresh render

Run:  python3 product/tests/test_render_spans.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import render_spans as R

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-400:]) if detail else ''}")


def page(dur, clips, extra_root="", tl_lines="", body_extra=""):
    """A composition shaped the way the builders write one: a root of timed clips and one registered timeline."""
    cl = "\n".join(f'<div class="clip" id="c{i}" data-start="{s:.2f}" data-duration="{d:.2f}" data-track-index="1">'
                   f'<div class="w" id="w{i}"><span>w{i}</span><img src="x.png" alt=""></div></div>'
                   for i, (s, d) in enumerate(clips))
    return ('<!doctype html><html><head><meta charset="UTF-8"/><style>.w{position:absolute}</style></head><body>\n'
            f'<div id="root" data-composition-id="reel" data-start="0" data-duration="{dur:.2f}" data-width="1080" '
            f'data-height="1920"{extra_root}>\n{cl}\n{body_extra}</div>\n<script>window.__timelines=window.__timelines||{{}};'
            f'const tl=gsap.timeline({{paused:true}});\n{tl_lines}\nwindow.__timelines["reel"]=tl;\n</script></body></html>')


# ───────────────────────────────────────────────────────────── 1. the plan
def test_plan():
    check("frames_for matches HyperFrames (ceil)", [R.frames_for(x) for x in (1.0, 1.01, 1.05, 2.1, 112.35)]
          == [30, 31, 32, 63, 3371])
    # two groups 4 s apart (> GAP) -> two stretches; words 0.5 s apart inside a group stay one stretch
    p = R.plan(page(20, [(1.0, 0.4), (1.5, 0.4), (2.0, 0.5), (12.0, 0.5), (12.6, 1.0)]))
    check("two groups past GAP -> two stretches", p and len(p["spans"]) == 2, p)
    if p:
        (a0, b0), (a1, b1) = p["spans"]
        check("stretch 1 starts PAD_PRE before its first word, on a frame", a0 == 27, p["spans"])
        check("stretch 1 ends PAD_POST after its last word, on a frame", b0 == 81, p["spans"])
        check("stretch 2 frames", (a1, b1) == (357, 414), p["spans"])
        check("plan frame count is the full render's", p["frames"] == 600)
    # a gap of exactly GAP (or less) keeps one stretch
    p = R.plan(page(30, [(1.0, 1.0), (2.0 + R.GAP, 1.0)]))
    check("a gap of GAP or less does not split", p and len(p["spans"]) == 1, p)
    # captions from the first word to the last: nothing worth a second render -> no plan, render as before
    check("first word to last -> no plan", R.plan(page(10, [(0.1, 4.9), (5.0, 4.8)])) is None)
    check("dead time under GAP in total -> no plan", R.plan(page(10, [(1.2, 7.0)])) is None)
    check("dead time over GAP at the ends -> plan", R.plan(page(10, [(4.0, 3.0)])) is not None)
    # pages that cannot be read with certainty always render whole
    check("a non-clip root child -> no plan",
          R.plan(page(20, [(1, 1), (15, 1)], body_extra='<div class="always">x</div>')) is None)
    check("a sub-composition -> no plan", R.plan(page(20, [(1, 1)]).replace(
        'data-track-index="1">', 'data-track-index="1" data-composition-src="x.html">', 1)) is None)
    check("a page at another frame rate -> no plan", R.plan(page(20, [(1, 1)], ' data-fps="60"')) is None)
    check("no #root -> no plan", R.plan("<html><body><div>x</div></body></html>") is None)
    check("garbage -> no plan", R.plan("<<<not html") is None)
    check("a whole-reel clip (catalog captions) -> no plan", R.plan(page(20, [(0, 20)])) is None)
    # a void tag (img) and a self-closed one inside clips never throw the depth count off
    h = page(20, [(1, 1), (15, 1)]).replace("<span>w0</span>", "<span>w0</span><br><svg><path d='M0 0'/></svg>")
    p = R.plan(h)
    check("void and self-closed tags inside clips parse", p and len(p["spans"]) == 2, p)


# ───────────────────────────────────────────────────────────── 2. the span page
def test_span_html():
    h = page(20, [(1.0, 1.0), (12.03, 1.0)], tl_lines='tl.set("#w0",{autoAlpha:0},0);tl.to("#w1",{x:10},12.1);')
    p = R.plan(h)
    a, b = p["spans"][1]
    s = R.span_html(h, a, b)
    starts = dict(re.findall(r'id="(c\d)" data-start="([0-9.]+)"', s))
    check("the stretch's clip is shifted to the stretch start", abs(float(starts.get("c1", -1)) - (12.03 - a / 30)) < 1e-5, starts)
    check("the clip outside the stretch is not a timed clip any more", "c0" not in starts, starts)
    check("it is parked in a hidden holder, still on the page", re.search(
        r'<div style="display:none" aria-hidden="true"><div class="hf-span-parked" id="c0">', s) is not None)
    rd = float(re.search(r'id="root"[^>]*data-duration="([0-9.]+)"', s).group(1))
    check("the root lasts exactly the stretch's frames", R.frames_for(rd) == b - a, (rd, b - a))
    check("the page's own timeline lines are untouched", 'tl.set("#w0",{autoAlpha:0},0);tl.to("#w1",{x:10},12.1);' in s)
    check("the timeline is driven from the stretch start (a hair ahead, never behind)",
          f"tl.time({a / 30 + R.CLOCK_LEAD:.6f},true)" in s and f'__hfSpan.to(tl,{{time:{b / 30 + R.CLOCK_LEAD:.6f}' in s
          and 'window.__timelines["reel"]=__hfSpan;' in s and 0 < R.CLOCK_LEAD < 0.001, s[-400:])
    # a word that starts exactly on a frame keeps starting on (or a hair before) that frame, never after it
    h4 = page(20, [(1.0, 1.0), (12.6, 0.34)])
    a4, b4 = R.plan(h4)["spans"][1]
    st4 = float(re.search(r'id="c1" data-start="([0-9.]+)"', R.span_html(h4, a4, b4)).group(1))
    check("a shifted start is never later than its frame", st4 <= 12.6 - a4 / 30 and 12.6 - a4 / 30 - st4 < 2e-6,
          (st4, 12.6 - a4 / 30))
    check("the page's own timeline is registered first, the stretch's driver takes its place as the page ends",
          'window.__timelines["reel"]=tl;window.__hfSpanArm=function(){' in s
          and s.rfind('<script id="hf-span-arm">') > s.rfind("</script>", 0, s.rfind('<script id="hf-span-arm">') - 1)
          and s.rstrip().endswith("</script></body></html>"), s[-300:])
    check("exactly one #root stays", s.count('id="root"') == 1)
    # a clip across the stretch edge cannot be shifted with certainty
    try:
        R.span_html(h, a + 5, b)
        check("a clip straddling the stretch edge raises", False)
    except ValueError:
        check("a clip straddling the stretch edge raises", True)
    try:
        R.span_html(h.replace('window.__timelines["reel"]=tl;', ""), a, b)
        check("no timeline registration raises", False)
    except ValueError:
        check("no timeline registration raises", True)
    # the reel's last caption may run past the reel's own end (a real reel did: 111.86s + 0.78s on 112.35s);
    # the last stretch keeps it instead of giving up on the whole span render
    h3 = page(20, [(1.0, 1.0), (19.6, 0.9)])
    p3 = R.plan(h3)
    try:
        s3 = R.span_html(h3, *p3["spans"][-1])
        check("a last caption running past the reel's end stays on the last stretch", 'id="c1" data-start=' in s3)
    except ValueError as e:
        check("a last caption running past the reel's end stays on the last stretch", False, e)
    # a line separator inside caption text (U+2028, a form feed) must not throw the page offsets off
    h2 = h.replace("<span>w0</span>", "<span>w\u20280\x0cx</span>")
    s2 = R.span_html(h2, a, b)
    check("odd line separators in text keep the page intact", s2.count('id="root"') == 1 and
          re.search(r'id="c1" data-start="0\.1[0-9]*"', s2) is not None and "w\u20280\x0cx" in s2, s2[:600])
    # span_comp copies fonts/assets beside the page, never the old render cache or a plan
    with tempfile.TemporaryDirectory() as t:
        src = os.path.join(t, "comp"); os.makedirs(os.path.join(src, "fonts")); os.makedirs(os.path.join(src, ".reel_render"))
        open(os.path.join(src, "index.html"), "w", encoding="utf-8").write(h)
        open(os.path.join(src, "fonts", "f.ttf"), "w", encoding="utf-8").write("x")
        open(os.path.join(src, R.PLAN_NAME), "w", encoding="utf-8").write("{}")
        dst = R.span_comp(src, os.path.join(t, "s1"), a, b)
        check("span_comp keeps the fonts", os.path.exists(os.path.join(dst, "fonts", "f.ttf")))
        check("span_comp drops the render cache and the plan",
              not os.path.exists(os.path.join(dst, ".reel_render")) and not os.path.exists(os.path.join(dst, R.PLAN_NAME)))
        check("span_comp writes the shifted page", "__hfSpan" in open(os.path.join(dst, "index.html"), encoding="utf-8").read())


# ───────────────────────────────────────────────────────────── 3. plan files + builders' wiring
def test_plan_files():
    with tempfile.TemporaryDirectory() as t:
        h = page(20, [(1, 1), (15, 1)])
        open(os.path.join(t, "index.html"), "w", encoding="utf-8").write(h)
        p = R.write_plan(t)
        check("write_plan saves a plan", p and os.path.exists(os.path.join(t, R.PLAN_NAME)))
        check("load_plan reads it back", R.load_plan(t) == p)
        open(os.path.join(t, "index.html"), "w", encoding="utf-8").write(page(20, [(1, 1), (16, 1)]))
        check("a plan made for a different page is not used", R.load_plan(t) is None)
        open(os.path.join(t, "index.html"), "w", encoding="utf-8").write(page(20, [(0.1, 19.8)]))
        check("rebuilding a page not worth trimming removes the plan",
              R.write_plan(t) is None and not os.path.exists(os.path.join(t, R.PLAN_NAME)))
        open(os.path.join(t, R.PLAN_NAME), "w", encoding="utf-8").write("{not json")
        check("an unreadable plan is ignored", R.load_plan(t) is None)
        R.clear_plan(t)
        check("clear_plan removes it", not os.path.exists(os.path.join(t, R.PLAN_NAME)))
        R.clear_plan(t)   # and is safe to repeat
    for f, need in (("build-reel-type.py", ("render_spans.write_plan(OUT, HTML)", "render_spans.clear_plan(OUT)",
                                            '_GROUP_TRACKS["captions"]')),
                    ("build-hf-captions.py", ("render_spans.write_plan(HF, HTML)",)),
                    ("reel_render.py", ("render_spans.load_plan(d)", "_render_by_spans(", "render_spans.write_sidecar(out",
                                        "render_spans.drop_sidecar(out)", 'REEL_FULL_RENDER')),
                    ("build-overlay.py", ("render_spans.segments(src)",)),
                    ("build-overlay.py", ("spans_for(SRC, SPANS_FILE, ov, footage_clips(D))",))):
        src = open(os.path.join(PRODUCT, f), encoding="utf-8").read()
        for n in need:
            check(f"{f} is wired: {n}", n in src)
    # the plan is written AFTER the page, from the same HTML, so the two can never disagree
    src = open(os.path.join(PRODUCT, "build-reel-type.py"), encoding="utf-8").read()
    check("build-reel-type writes the plan after index.html",
          src.index('open(f"{OUT}/index.html", "w"') < src.index("render_spans.write_plan(OUT, HTML)"))


# ───────────────────────────────────────────────────────────── helpers for media
def have_ffmpeg():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def prores(path, frames, ink=None, size="64x64", fps=30):
    """`frames` frames of transparent ProRes 4444; with ink=[(first, end)], solid white (alpha 255) on those."""
    w, h = size.split("x")
    en = "+".join(f"between(N,{a},{b - 1})" for a, b in (ink or [])) or "0"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=black:s={size}:r={fps}",
                    "-f", "lavfi", "-i", f"color=white:s={size}:r={fps}",
                    "-filter_complex", f"[0:v]format=gray,geq=lum='if({en},255,0)'[m];[1:v][m]alphamerge[o]",
                    "-map", "[o]", "-frames:v", str(frames), "-c:v", "prores_ks", "-profile:v", "4",
                    "-pix_fmt", "yuva444p10le", path], check=True)
    return path


def alpha_per_frame(path):
    """Mean alpha (0..255) of every frame."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "alphaextract,scale=8:8", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], capture_output=True)
    b = r.stdout
    return [sum(b[i:i + 64]) / 64 for i in range(0, len(b) - 63, 64)]


# ───────────────────────────────────────────────────────────── 4. sidecar
def test_sidecar():
    with tempfile.TemporaryDirectory() as t:
        mov = os.path.join(t, "captions.mov")
        open(mov, "wb").write(b"x" * 1234)
        p = {"fps": 30, "frames": 600, "spans": [[27, 81], [357, 414]]}
        doc = R.write_sidecar(mov, p)
        check("sidecar sits beside the .mov as <name>.spans.json", os.path.exists(os.path.join(t, "captions.spans.json")))
        check("sidecar spans carry file, at, dur", doc["spans"][0] == {"file": "captions.mov", "at": 0.9, "dur": 1.8,
                                                                       "frames": [27, 81]}, doc["spans"][0])
        segs = R.segments(mov)
        check("segments() round-trips the stretches", segs == [(0.9, 1.8), (11.9, 1.9)], segs)
        open(mov, "ab").write(b"y")
        check("a sidecar for a file that changed is ignored (whole file used)", R.segments(mov) is None)
        R.write_sidecar(mov, p)
        other = os.path.join(t, "other.mov"); shutil.copy(mov, other)
        shutil.copy(R.sidecar_path(mov), R.sidecar_path(other))
        check("a sidecar copied beside another file is ignored", R.segments(other) is None)
        open(R.sidecar_path(mov), "w", encoding="utf-8").write("{broken")
        check("a broken sidecar is ignored", R.segments(mov) is None)
        R.drop_sidecar(mov)
        check("no sidecar -> None", R.segments(mov) is None)
        R.drop_sidecar(mov)   # safe to repeat


# ───────────────────────────────────────────────────────────── 5. reassembly
def test_assemble():
    if not have_ffmpeg():
        print("  ..   ffmpeg not on PATH — skipping reassembly"); return
    with tempfile.TemporaryDirectory() as t:
        p = {"fps": 30, "frames": 200, "spans": [[10, 40], [150, 185]]}
        s1 = prores(os.path.join(t, "s1.mov"), 30, ink=[(0, 30)])
        s2 = prores(os.path.join(t, "s2.mov"), 35, ink=[(5, 35)])
        out = os.path.join(t, "out", "captions.mov")
        R.assemble([s1, s2], p, out, os.path.join(t, "work"))
        check("the stitched layer has the full render's frame count", R.count_frames(out) == 200, R.count_frames(out))
        a = alpha_per_frame(out)
        want = [255 if (10 <= i < 40 or 155 <= i < 185) else 0 for i in range(200)]
        check("each stretch lands on its own frames, transparent between",
              len(a) == 200 and all(abs(x - y) < 2 for x, y in zip(a, want)),
              [i for i, (x, y) in enumerate(zip(a, want)) if abs(x - y) >= 2][:12])
        st = R._probe_stream(out)
        check("it is still transparent ProRes", st.get("codec_name") == "prores" and "yuva" in st.get("pix_fmt", ""), st)
        # a stretch of the wrong length is refused (the caller then renders full length)
        bad = prores(os.path.join(t, "bad.mov"), 29, ink=[(0, 29)])
        try:
            R.assemble([bad, s2], p, os.path.join(t, "x.mov"), os.path.join(t, "w2"))
            check("a wrong-length stretch is refused", False)
        except RuntimeError:
            check("a wrong-length stretch is refused", not os.path.exists(os.path.join(t, "x.mov")))
        try:
            R.assemble([s1], p, os.path.join(t, "y.mov"), os.path.join(t, "w3"))
            check("a missing stretch is refused", False)
        except RuntimeError:
            check("a missing stretch is refused", True)
        # a path with a space and an apostrophe (Windows profiles, a two-word pack's folder)
        odd = os.path.join(t, "my creator's reel", "hf-reel-type-two word")
        os.makedirs(odd)
        s1b = shutil.copy(s1, os.path.join(odd, "s 1.mov")); s2b = shutil.copy(s2, os.path.join(odd, "s 2.mov"))
        out2 = os.path.join(odd, "captions.mov")
        R.assemble([s1b, s2b], p, out2, os.path.join(odd, "work dir"))
        check("paths with spaces and apostrophes stitch", R.count_frames(out2) == 200)


# ───────────────────────────────────────────────────────────── 5b. the filler's color tags
def frame_colors(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "frame=color_range,color_space,color_primaries,color_transfer", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l.strip()]


def test_filler_color_tags():
    if not have_ffmpeg():
        print("  ..   ffmpeg not on PATH — skipping the filler's color tags"); return
    with tempfile.TemporaryDirectory() as t:
        p = {"fps": 30, "frames": 120, "spans": [[0, 30], [75, 105]]}
        spans = []
        for i, n in ((1, 30), (2, 30)):   # stretch renders tagged bt709, the way HyperFrames writes them
            src = prores(os.path.join(t, f"raw{i}.mov"), n, ink=[(0, n)])
            f = os.path.join(t, f"s{i}.mov")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c:v", "prores_ks", "-profile:v", "4",
                            "-pix_fmt", "yuva444p10le", "-color_range", "tv", "-colorspace", "bt709",
                            "-color_primaries", "bt709", "-color_trc", "bt709", f], check=True)
            spans.append(f)
        out = os.path.join(t, "captions.mov")
        R.assemble(spans, p, out, os.path.join(t, "work"))
        tags = frame_colors(out)
        check("every frame of the stitched layer carries one set of color tags", len(tags) == 120 and len(set(tags)) == 1,
              sorted(set(tags)))
        check("the tags are the renders' own (bt709)", tags and "bt709" in tags[0], tags[:1])
        # the bake's shape: footage, the layer overlaid, sound effects delayed and mixed in ONE graph
        base = os.path.join(t, "base.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=30:d=4",
                        "-f", "lavfi", "-i", "sine=f=220:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-colorspace", "bt709", "-c:a", "aac", "-shortest", base], check=True)
        sfx = os.path.join(t, "sfx.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=880:d=0.3", sfx], check=True)
        args = ["ffmpeg", "-y", "-v", "verbose", "-i", base, "-i", out]
        fc = ["[0:v][1:v]overlay=0:0:format=auto:eof_action=pass[vout]"]
        al = "[0:a]"
        for i in range(2, 6):
            args += ["-i", sfx]; fc.append(f"[{i}:a]adelay={i * 500}|{i * 500}[s{i}]"); al += f"[s{i}]"
        fc.append(f"{al}amix=inputs=5:duration=first:normalize=0[aout]")
        r = subprocess.run(args + ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
                                   "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                                   os.path.join(t, "bake.mp4")], capture_output=True, text=True, timeout=120)
        check("the bake finishes", r.returncode == 0, r.stderr[-300:])
        check("the bake never rebuilds its filtergraph at a stretch edge", "Reconfiguring filter graph" not in r.stderr,
              [l for l in r.stderr.splitlines() if "Reconfiguring" in l][:3])
    src = open(os.path.join(PRODUCT, "reel_render.py"), encoding="utf-8").read()
    check("a layer stitched before this fix is rendered again (render_spans.ASSEMBLY is in the cache key)",
          "spans_assembly={render_spans.ASSEMBLY}" in src and R.ASSEMBLY >= 2)


# ───────────────────────────────────────────────────────────── 6. consumers
def test_consumers():
    if not have_ffmpeg():
        print("  ..   ffmpeg not on PATH — skipping consumers"); return
    with tempfile.TemporaryDirectory() as t:
        p = {"fps": 30, "frames": 200, "spans": [[10, 40], [150, 185]]}
        mov = os.path.join(t, "captions.mov")
        R.assemble([prores(os.path.join(t, "s1.mov"), 30, ink=[(0, 30)]),
                    prores(os.path.join(t, "s2.mov"), 35, ink=[(0, 35)])], p, mov, os.path.join(t, "w"))
        R.write_sidecar(mov, p)
        # build-overlay.py's span choice (the CapCut set-overlay injector)
        os.environ.setdefault("JOB", "unit-test"); os.environ.setdefault("CAPCUT_DRAFT", "unit-test-draft")
        sys.argv = ["build-overlay.py", mov, "captions_overlay"]
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_overlay_t", os.path.join(PRODUCT, "build-overlay.py"))
        bo = importlib.util.module_from_spec(spec); spec.loader.exec_module(bo)
        sp = bo.spans_for(mov, "", int(200 / 30 * 1e6))
        check("build-overlay: the sidecar's stretches become its spans", [tuple(round(x, 4) for x in s) for s in sp]
              == [(0.3333, 1.3333), (5.0, 6.1667)], sp)
        given = os.path.join(t, "all-spans.json"); json.dump([[1.0, 2.0]], open(given, "w", encoding="utf-8"))
        check("build-overlay: an explicit spans file still wins", bo.spans_for(mov, given, 1) == [[1.0, 2.0]])
        R.drop_sidecar(mov)
        check("build-overlay: no sidecar -> one full-length segment", bo.spans_for(mov, "", 6_666_667) == [(0.0, 6.666667)])
        # and through inject(): a fresh track gets one segment per stretch at the right source/target times
        R.write_sidecar(mov, p)
        def draft_with(nclips):
            segs = [{"id": f"S{i}", "material_id": "v1", "extra_material_refs": ["sp1"],
                     "clip": {"scale": {"x": 1, "y": 1}, "transform": {"x": 0, "y": 0}},
                     "target_timerange": {"start": i * 1_333_333, "duration": 1_333_333},
                     "source_timerange": {"start": i * 1_333_333, "duration": 1_333_333}} for i in range(nclips)]
            return {"materials": {"videos": [{"id": "v1", "path": "/x/foot.mp4"}], "speeds": [{"id": "sp1"}]},
                    "tracks": [{"type": "video", "flag": 0, "segments": segs}]}
        ov_us = int(200 / 30 * 1e6)
        # a cut footage track (5 clips): one CapCut segment per stretch, and the footage stays the magnet's anchor
        dj = os.path.join(t, "draft_info.json"); json.dump(draft_with(5), open(dj, "w", encoding="utf-8"))
        n, mode = bo.inject(dj, ov_us, bo.spans_for(mov, "", ov_us, 5))
        d2 = json.load(open(dj, encoding="utf-8"))
        main = [tr for tr in d2["tracks"] if tr["type"] == "video" and tr.get("is_default_name") is False]
        over = [tr for tr in d2["tracks"] if tr["type"] == "video" and tr.get("is_default_name") is True]
        segs = [s for tr in over for s in tr["segments"]]
        check("inject(): one CapCut segment per stretch over a cut", n == 2 and len(segs) == 2, (n, mode, len(segs)))
        check("inject(): the footage stays the magnet's main track", len(main) == 1 and len(main[0]["segments"]) == 5,
              [(len(tr["segments"]), tr.get("is_default_name")) for tr in d2["tracks"]])
        # and every later writer re-applies the magnet (finalize, sfx, music...): it must keep the footage as the
        # anchor too, never pick the caption track
        import copy
        from capcut_ripple import enforce_maintrack_ripple, verify_maintrack_anchor
        d2b = enforce_maintrack_ripple(copy.deepcopy(d2))
        again = [tr for tr in d2b["tracks"] if tr["type"] == "video" and tr.get("is_default_name") is False]
        check("a re-applied magnet still anchors the footage, never the caption stretches",
              len(again) == 1 and len(again[0]["segments"]) == 5 and not verify_maintrack_anchor(d2b))
        if len(segs) == 2:
            check("inject(): each segment's source and target are the stretch's reel time",
                  all(s["source_timerange"] == s["target_timerange"] for s in segs)
                  and segs[0]["target_timerange"]["start"] == 333333 and segs[1]["target_timerange"]["start"] == 5_000_000,
                  [s["target_timerange"] for s in segs])
        # footage as ONE clip (a finished cut handed over whole): the layer goes in whole, so it can never
        # out-number the footage and steal the magnet's anchor
        check("build-overlay: one footage clip -> the whole layer as one segment",
              bo.spans_for(mov, "", ov_us, 1) == [(0.0, ov_us / 1e6)], bo.spans_for(mov, "", ov_us, 1))
        check("build-overlay: two stretches over two footage clips -> still whole (never a tie)",
              len(bo.spans_for(mov, "", ov_us, 2)) == 1)
        dj1 = os.path.join(t, "draft_one.json"); json.dump(draft_with(1), open(dj1, "w", encoding="utf-8"))
        bo.inject(dj1, ov_us, bo.spans_for(mov, "", ov_us, 1))
        d3 = json.load(open(dj1, encoding="utf-8"))
        anchor = [tr for tr in d3["tracks"] if tr["type"] == "video" and tr.get("is_default_name") is False]
        check("build-overlay: over one footage clip the footage is still the anchor",
              len(anchor) == 1 and anchor[0]["segments"][0]["material_id"] == "v1", d3["tracks"])
        fd = os.path.join(t, "Draft X"); os.makedirs(fd)
        json.dump(draft_with(7), open(os.path.join(fd, "draft_content.json"), "w", encoding="utf-8"))
        json.dump(draft_with(7), open(os.path.join(fd, "draft_info.json"), "w", encoding="utf-8"))
        check("build-overlay: footage_clips() reads the draft's footage clip count", bo.footage_clips(fd) == 7,
              bo.footage_clips(fd))

        # reel_render composite: the stretches show over the footage at their own times, nothing elsewhere
        base = os.path.join(t, "base.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=64x64:r=30:d=6.6667",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", base], check=True)
        out = os.path.join(t, "final.mp4")
        r = subprocess.run([sys.executable, os.path.join(PRODUCT, "reel_render.py"), "composite", "--base", base,
                            "--layers", mov, "-o", out], capture_output=True, text=True)
        check("composite runs on a stitched layer", r.returncode == 0 and os.path.exists(out), r.stdout + r.stderr)
        if r.returncode == 0:
            g = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt",
                                "gray", "-"], capture_output=True).stdout
            lit = [i for i, v in enumerate(g) if v > 128]
            want = list(range(10, 40)) + list(range(150, 185))
            check("composite: white exactly on the stretches' frames", lit == want,
                  f"lit {lit[:5]}..{lit[-5:] if lit else ''} ({len(lit)}) want 10..39,150..184")


# ───────────────────────────────────────────────────────────── 7. reel_render end to end
FAKE_NPX = r'''#!{py}
"""Stand-in for `npx hyperframes@<pin> check|render`. Its render draws every TIMED clip of the page as solid
white during that clip's own window, the way the real renderer shows it, at the page's own length, so a
stretch page and the full page come out the way the real ones would. FAKE_SPAN=fail fails a stretch render,
FAKE_SPAN=short renders a stretch one frame short, FAKE_SPAN=blank renders a stretch with nothing on it."""
import math, os, re, subprocess, sys
a = sys.argv[1:]
cmd = a[1] if len(a) > 1 else ""
if cmd == "check":
    print("◇  Check passed"); sys.exit(0)
if cmd != "render":
    sys.exit(2)
comp, out = a[2], a[a.index("--output") + 1]
html = open(os.path.join(comp, "index.html"), encoding="utf-8").read()
is_span = "__hfSpan" in html
if is_span and os.environ.get("FAKE_SPAN") == "fail":
    print("renderer crashed"); sys.exit(1)
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as fh:
    fh.write(("span" if is_span else "full") + "\n")
dur = float(re.search(r'id="root"[^>]*data-duration="([0-9.]+)"', html).group(1))
n = int(math.ceil(dur * 30 - 1e-6))
if is_span and os.environ.get("FAKE_SPAN") == "short":
    n -= 1
spans = [(float(s), float(d)) for s, d in re.findall(r'class="clip"[^>]*data-start="([0-9.]+)" data-duration="([0-9.]+)"', html)]
en = "+".join(f"between(n,{{math.ceil(s*30-1e-6)}},{{math.ceil((s+d)*30-1e-6)-1}})" for s, d in spans) or "0"
if is_span and os.environ.get("FAKE_SPAN") == "blank":
    en = "0"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=1080x1920:r=30",
                "-f", "lavfi", "-i", "color=white:s=1080x1920:r=30", "-filter_complex",
                f"[0:v]format=gray,drawbox=x=300:y=1300:w=400:h=100:color=white:t=fill:enable='{{en}}'[m];[1:v][m]alphamerge[o]",
                "-map", "[o]", "-frames:v", str(n), "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", out],
               check=True)
print("Render complete"); sys.exit(0)
'''


def engine_copy(root):
    eng = os.path.join(root, "engine")
    os.makedirs(os.path.join(eng, "product"))
    for f in os.listdir(PRODUCT):
        if f.endswith(".py"):
            shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
    if os.path.exists(os.path.join(os.path.dirname(PRODUCT), "product.json")):
        shutil.copy(os.path.join(os.path.dirname(PRODUCT), "product.json"), eng)
    return os.path.join(eng, "product", "reel_render.py")


def test_reel_render():
    if os.name == "nt":
        print("  ..   the stand-in npx is a POSIX script — skipping the end-to-end leg on Windows"); return
    if not have_ffmpeg():
        print("  ..   ffmpeg not on PATH — skipping the end-to-end leg"); return
    tmp = tempfile.mkdtemp(prefix="render-spans-")
    try:
        script = engine_copy(tmp)
        fake = os.path.join(tmp, "bin"); os.makedirs(fake)
        with open(os.path.join(fake, "npx"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_NPX.format(py=sys.executable))
        os.chmod(os.path.join(fake, "npx"), 0o755)
        log = os.path.join(tmp, "renders.log")
        env = {k: v for k, v in os.environ.items() if k not in ("REEL_FULL_RENDER", "FAKE_SPAN")}
        env.update(PATH=fake + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                   REELS_RENDER_STALL_SECONDS="0", FAKE_LOG=log, REEL_STRETCH_CACHE=os.path.join(tmp, "stretches"))
        comp = os.path.join(tmp, "projects", "job", "hf-reel-type-test"); os.makedirs(comp)
        h = page(8, [(0.5, 0.5), (1.1, 0.6), (6.0, 1.0)])
        open(os.path.join(comp, "index.html"), "w", encoding="utf-8").write(h)
        plan = R.write_plan(comp)
        check("e2e: the page gets a two-stretch plan", plan and len(plan["spans"]) == 2, plan)

        def run(out, *flags, **extra):
            open(log, "w", encoding="utf-8").close()
            e = dict(env, **extra)
            r = subprocess.run([sys.executable, script, "render", comp, "-o", out, "--no-subject", *flags],
                               capture_output=True, text=True, env=e, timeout=600)
            return r.returncode, r.stdout + r.stderr, open(log, encoding="utf-8").read().split()

        full = os.path.join(tmp, "out", "full.mov")
        rc, txt, kinds = run(full, REEL_FULL_RENDER="1")
        check("e2e: REEL_FULL_RENDER=1 renders once, full length", rc == 0 and kinds == ["full"], (rc, kinds, txt))
        check("e2e: ...and writes no sidecar", not os.path.exists(R.sidecar_path(full)))

        spans = os.path.join(tmp, "out", "spans.mov")
        rc, txt, kinds = run(spans)
        check("e2e: a planned layer renders one stretch at a time", rc == 0 and kinds == ["span", "span"], (rc, kinds, txt))
        check("e2e: it says what it did in plain words", "stitched into one full-length layer" in txt, txt)
        check("e2e: the stitched file is full length", R.count_frames(spans) == R.frames_for(8), R.count_frames(spans))
        fa, sa = alpha_per_frame(full), alpha_per_frame(spans)
        check("e2e: stitched == full render, frame for frame", len(fa) == len(sa) and
              all(abs(x - y) < 1 for x, y in zip(fa, sa)),
              [i for i, (x, y) in enumerate(zip(fa, sa)) if abs(x - y) >= 1][:12])
        check("e2e: the sidecar is written beside it", R.segments(spans) == [(a / 30, (b - a) / 30) for a, b in plan["spans"]],
              R.segments(spans))

        # the cache: an identical re-run is a no-op and keeps the sidecar
        rc, txt, kinds = run(spans)
        check("e2e: an identical re-run reuses the render", rc == 0 and kinds == [] and "unchanged" in txt, (kinds, txt))
        check("e2e: ...and keeps its sidecar", R.segments(spans) is not None)
        # a fresh full render to the same path drops the old sidecar (it would mislead placement otherwise)
        rc, txt, kinds = run(spans, "--force", REEL_FULL_RENDER="1")
        check("e2e: a fresh full render drops the old sidecar", rc == 0 and kinds == ["full"] and R.segments(spans) is None
              and not os.path.exists(R.sidecar_path(spans)), (kinds, txt))

        # FALLBACK 1: a stretch fails to render -> the ordinary full render, said in one plain line, no sidecar
        fb = os.path.join(tmp, "out", "fallback.mov")
        # (each fallback run starts from an empty stretch cache, or the stretches above would just be reused)
        rc, txt, kinds = run(fb, FAKE_SPAN="fail", REEL_STRETCH_CACHE=os.path.join(tmp, "stretches-fb1"))
        check("e2e fallback: a failed stretch falls back to the full render", rc == 0 and kinds == ["full"], (rc, kinds, txt))
        check("e2e fallback: said in one plain line", "did not work here" in txt and "full length, the way it always has" in txt, txt)
        check("e2e fallback: never an alarm for it", not re.search(r"⛔[^\n]*stretch", txt), txt)
        check("e2e fallback: the layer still has its captions", all(abs(x - y) < 1 for x, y in zip(fa, alpha_per_frame(fb))))
        check("e2e fallback: no sidecar", not os.path.exists(R.sidecar_path(fb)))
        # FALLBACK 2: a stretch comes back the wrong length -> refused at reassembly -> full render
        fb2 = os.path.join(tmp, "out", "fallback2.mov")
        rc, txt, kinds = run(fb2, FAKE_SPAN="short", REEL_STRETCH_CACHE=os.path.join(tmp, "stretches-fb2"))
        check("e2e fallback: a wrong-length stretch falls back to the full render",
              rc == 0 and kinds[-1:] == ["full"] and "span" in kinds and "did not work here" in txt, (rc, kinds, txt))
        check("e2e fallback: full length", R.count_frames(fb2) == R.frames_for(8))
        # FALLBACK 3: the page changed after the plan -> the stale plan is not used
        open(os.path.join(comp, "index.html"), "w", encoding="utf-8").write(page(8, [(0.5, 0.5), (5.0, 1.0)]))
        fb3 = os.path.join(tmp, "out", "fallback3.mov")
        rc, txt, kinds = run(fb3)
        check("e2e: a stale plan renders the page whole", rc == 0 and kinds == ["full"], (rc, kinds, txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for t in (test_plan, test_span_html, test_plan_files, test_sidecar, test_assemble, test_filler_color_tags, test_consumers, test_reel_render):
        t()
    if fails:
        print(f"test_render_spans: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_render_spans: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
