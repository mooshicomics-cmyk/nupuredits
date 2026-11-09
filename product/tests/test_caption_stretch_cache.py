#!/usr/bin/env python3
"""test_caption_stretch_cache.py — a small caption edit re-renders and re-prepares only the stretch it touches.

A caption layer used to render whole on every change, and its CapCut copy was prepared whole too: adding a few
highlight words to a 1:53 reel re-rendered 3,383 frames and re-prepared a 366 MB layer (2026-10-23: "small
caption fixes shouldn't require a whole rebuild ... they're supposed to layer"). Now (product/render_spans.py):

  plan      a caption layer on screen the whole reel is still cut into stretches: at the first caption to start
            after every STEP s of the reel (a fixed grid), never across a caption, never a piece under MIN_PIECE
  grid      moving one line moves at most the cut next to it; every other stretch keeps its frames
  local     a stretch's own page (local=True) holds only its captions and the timeline lines that move them, so
            it is the same page whatever changed elsewhere; a line that also moves an outside caption keeps it
  keys      one word changed -> exactly one stretch key changes; the pack's CSS or a font changes them all; the
            builder's notes (look.json) change none
  e2e       reel_render with a stand-in HyperFrames: the first render renders every stretch; one word changed
            renders ONE stretch and takes the rest from the cache; the sidecar lists each stretch's own file
  capcut    each stretch is prepared for CapCut on its own and cached: after the edit one stretch needs it
  handoff   the CapCut handoff lays the caption layer as one clip per stretch, each at its own place on the reel
  bar       render_spans.pending_share: 1.0 before the first render, the edited stretch's share after an edit

Run:  python3 product/tests/test_caption_stretch_cache.py
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ needs UTF-8; a cp1252 Windows console cannot print it
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
sys.path.insert(0, HERE)
import render_spans as R

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-400:]) if detail else ''}")


def page(dur, clips, words=None, css=".w{position:absolute}", extra_lines=""):
    """A caption page shaped like the builders write one: back-to-back timed phrase clips, one timeline line set
    per clip, starts off the frame grid the way real transcripts are."""
    words = words or {}
    cl, tl = [], []
    for i, (s, d) in enumerate(clips):
        cl.append(f'<div class="clip" id="clip-ph{i}" data-start="{s:.2f}" data-duration="{d:.2f}" data-track-index="1">'
                  f'<div class="phrase" id="ph{i}"><span class="pw" id="ph{i}w0">{words.get(i, f"word{i}")}</span></div></div>')
        tl.append(f'tl.set("#ph{i}",{{autoAlpha:0}},0);tl.set("#ph{i}",{{autoAlpha:1}},{s:.2f});'
                  f'tl.set("#ph{i}",{{autoAlpha:0}},{s + d:.2f});')
    return ('<!doctype html><html><head><meta charset="UTF-8"/><style>' + css + '</style></head><body>\n'
            f'<div id="root" data-composition-id="cap" data-start="0" data-duration="{dur:.2f}" data-width="1080" '
            f'data-height="1920">\n' + "\n".join(cl) + '\n</div>\n<script>window.__timelines=window.__timelines||{};'
            'const tl=gsap.timeline({paused:true});\n' + "\n".join(tl) + extra_lines +
            '\nwindow.__timelines["cap"]=tl;\n</script></body></html>')


def back_to_back(dur, step=1.37, first=0.02):
    out, t = [], first
    while t + step < dur - 0.2:
        out.append((round(t, 2), step)); t = round(t + step, 2)
    return out


# ───────────────────────────────────────────────────────────── plan + grid
def test_plan():
    clips = back_to_back(60)
    p = R.plan(page(60, clips))
    check("a caption layer on screen the whole reel still gets a plan", p is not None, p)
    if not p:
        return
    sp = p["spans"]
    check("it is cut into stretches of about STEP s", 4 <= len(sp) <= 7 and
          all((b - a) / 30 <= R.MAX_SPAN + 1.5 for a, b in sp), [(a / 30, (b - a) / 30) for a, b in sp])
    check("the stretches are back to back (nothing on screen is skipped)",
          all(sp[i][1] == sp[i + 1][0] for i in range(len(sp) - 1)), sp)
    check("no piece shorter than MIN_PIECE", all((b - a) / 30 >= R.MIN_PIECE - 1e-6 for a, b in sp), sp)
    vis = [R._vis(s, d) for s, d in clips]
    cuts = [a for a, _b in sp[1:]]
    check("every cut sits where a caption starts", all(any(v0 == c for v0, _ in vis) for c in cuts), cuts)
    check("no caption runs across a cut", not any(v0 < c < v1 for c in cuts for v0, v1 in vis), cuts)
    h = page(60, clips)
    ok = True
    for a, b in sp:
        try:
            R.span_html(h, a, b); R.span_html(h, a, b, local=True)
        except ValueError as e:
            ok = False; check("every stretch page can be made", False, (a, b, e))
    check("every stretch page can be made (whole and local)", ok)
    # a fixed grid: moving one caption in the middle leaves every cut away from it where it was
    moved = list(clips); k = len(moved) // 2
    moved[k] = (moved[k][0] + 0.4, moved[k][1] - 0.4)
    p2 = R.plan(page(60, moved))
    near = moved[k][0] * 30
    far1 = [c for c in cuts if abs(c - near) > R.STEP * 30]
    far2 = [a for a, _b in p2["spans"][1:] if abs(a - near) > R.STEP * 30]
    check("moving one line keeps every cut away from it", far1 == far2, (far1, far2))
    check("a short layer (under MAX_SPAN) still renders whole when on screen throughout",
          R.plan(page(10, back_to_back(10))) is None)


# ───────────────────────────────────────────────────────────── local page + keys
def test_local_and_keys():
    clips = back_to_back(40)
    h = page(40, clips, extra_lines='tl.to("#ph0",{x:1},0.1);tl.to(["#ph0","#ph25"],{y:2},0.2);')
    p = R.plan(h)
    a, b = p["spans"][1]
    s = R.span_html(h, a, b, local=True)
    inside = [i for i, (st, d) in enumerate(clips) if R._vis(st, d)[0] >= a and R._vis(st, d)[1] <= b]
    check("the local page keeps this stretch's captions", all(f'id="clip-ph{i}"' in s for i in inside), inside)
    check("the local page drops captions outside it", 'id="clip-ph3"' not in s and 'id="ph3"' not in s)
    check("the local page drops the lines that only move outside captions", '"#ph3"' not in s and 'tl.to("#ph0",{x:1}' not in s)
    check("a line that also moves an inside caption is kept, its outside target parked",
          ('tl.to(["#ph0","#ph25"]' in s) == (25 in inside) and (('id="ph0"' in s) == (25 in inside)), inside)
    check("the local page still registers its timeline, driven from the stretch", "__hfSpan" in s and s.count('id="root"') == 1)
    with tempfile.TemporaryDirectory() as t:
        comp = os.path.join(t, "comp"); os.makedirs(os.path.join(comp, "fonts"))
        open(os.path.join(comp, "fonts", "f.ttf"), "w", encoding="utf-8").write("font-1")
        open(os.path.join(comp, "look.json"), "w", encoding="utf-8").write('{"text": "one"}')
        open(os.path.join(comp, "hyperframes.json"), "w", encoding="utf-8").write('{"fps": 30}')
        h = page(40, clips)
        open(os.path.join(comp, "index.html"), "w", encoding="utf-8").write(h)
        p = R.plan(h)
        k1 = R.stretch_keys(comp, p, "x")
        check("every stretch gets a key", len(k1) == len(p["spans"]) and all(k1), k1)
        hw = page(40, clips, words={12: "CHANGED"})
        k2 = R.stretch_keys(comp, p, "x", html=hw)
        changed = [i for i, (x, y) in enumerate(zip(k1, k2)) if x != y]
        owner = next(i for i, (a_, b_) in enumerate(p["spans"]) if a_ <= R._vis(*clips[12])[0] < b_)
        check("one word changed -> exactly its own stretch's key changes", changed == [owner], (changed, owner))
        k3 = R.stretch_keys(comp, p, "x", html=page(40, clips, css=".w{position:absolute;color:red}"))
        check("the page's CSS changed -> every key changes", all(x != y for x, y in zip(k1, k3)))
        check("another renderer version -> every key changes", all(x != y for x, y in zip(k1, R.stretch_keys(comp, p, "y"))))
        open(os.path.join(comp, "look.json"), "w", encoding="utf-8").write('{"text": "two"}')
        check("the builder's notes (look.json) change no key", R.stretch_keys(comp, p, "x") == k1)
        open(os.path.join(comp, "fonts", "f.ttf"), "w", encoding="utf-8").write("font-2")
        check("a font changed -> every key changes", all(x != y for x, y in zip(k1, R.stretch_keys(comp, p, "x"))))


# ───────────────────────────────────────────────────────────── end to end
def fake_npx(py):
    """The stand-in HyperFrames from test_render_spans, drawing small frames so the CapCut copies stay quick."""
    import test_render_spans as T
    return (T.FAKE_NPX.format(py=py).replace("1080x1920", "180x320")
            .replace("drawbox=x=300:y=1300:w=400:h=100", "drawbox=x=40:y=200:w=100:h=30"))


def test_e2e():
    if os.name == "nt":
        print("  ..   the stand-in npx is a POSIX script — skipping the end-to-end leg on Windows"); return
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("  ..   ffmpeg not on PATH — skipping the end-to-end leg"); return
    import test_render_spans as T
    tmp = tempfile.mkdtemp(prefix="stretch-cache-")
    try:
        script = T.engine_copy(tmp)
        fake = os.path.join(tmp, "bin"); os.makedirs(fake)
        with open(os.path.join(fake, "npx"), "w", encoding="utf-8") as fh:
            fh.write(fake_npx(sys.executable))
        os.chmod(os.path.join(fake, "npx"), 0o755)
        log = os.path.join(tmp, "renders.log")
        cache = os.path.join(tmp, "stretches")
        env = {k: v for k, v in os.environ.items() if k not in ("REEL_FULL_RENDER", "FAKE_SPAN")}
        env.update(PATH=fake + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                   REELS_RENDER_STALL_SECONDS="0", FAKE_LOG=log, REEL_STRETCH_CACHE=cache)
        comp = os.path.join(tmp, "projects", "job", "hf-reel-type-test"); os.makedirs(comp)
        clips = back_to_back(24)
        open(os.path.join(comp, "index.html"), "w", encoding="utf-8").write(page(24, clips))
        plan = R.write_plan(comp)
        n = len(plan["spans"]) if plan else 0
        check("e2e: a 24 s caption layer on screen throughout is planned in stretches", n >= 2, plan)

        def run(out):
            open(log, "w", encoding="utf-8").close()
            r = subprocess.run([sys.executable, script, "render", comp, "-o", out, "--no-subject"],
                               capture_output=True, text=True, env=env, timeout=600)
            return r.returncode, r.stdout + r.stderr, open(log, encoding="utf-8").read().split()

        out = os.path.join(tmp, "out", "captions.mov")
        os.environ["REEL_STRETCH_CACHE"] = cache
        share0 = R.pending_share(comp, _hf())
        rc, txt, kinds = run(out)
        check("e2e: the first render renders every stretch", rc == 0 and kinds == ["span"] * n, (rc, kinds, txt[-600:]))
        parts1 = R.parts(out)
        check("e2e: the sidecar lists each stretch's own file, in the cache", parts1 and len(parts1) == n and
              all(p_[0].startswith(cache) for p_ in parts1), parts1)
        check("bar: before the first render the whole layer is to do", share0 is not None and share0 > 0.9, share0)
        check("bar: after it nothing is left to do", R.pending_share(comp, _hf()) == 0.0, R.pending_share(comp, _hf()))

        # one word changed in the middle stretch
        k = next(i for i, (s, d) in enumerate(clips) if R._vis(s, d)[0] >= plan["spans"][1][0])
        open(os.path.join(comp, "index.html"), "w", encoding="utf-8").write(page(24, clips, words={k: "CHANGED"}))
        R.write_plan(comp)
        share1 = R.pending_share(comp, _hf())
        want = (plan["spans"][1][1] - plan["spans"][1][0]) / plan["frames"]
        check("bar: after an edit only the edited stretch's share is left", share1 is not None and abs(share1 - want) < 1e-6,
              (share1, want))
        rc, txt, kinds = run(out)
        check("e2e: one word changed renders ONE stretch", rc == 0 and kinds == ["span"], (rc, kinds, txt[-600:]))
        check("e2e: ...and says the rest came from the cache", f"{n - 1} unchanged came from the cache" in txt, txt[-600:])
        check("e2e: the layer is still full length", R.count_frames(out) == R.frames_for(24))
        parts2 = R.parts(out)
        same = [i for i, (x, y) in enumerate(zip(parts1, parts2)) if x[0] == y[0]]
        check("e2e: every other stretch is the very same cached file", parts2 and len(same) == n - 1 and 1 not in same,
              (same, parts2))

        # the CapCut copy: each stretch prepared on its own, cached; after the edit only one needs it
        try:
            import numpy  # noqa: F401
        except Exception:
            print("  ..   numpy not here — skipping the CapCut-copy leg"); return
        os.environ["REEL_CAPCUT_ALPHA_CACHE"] = os.path.join(tmp, "alpha")
        import capcut_alpha
        for pf, _a, _d in parts1:
            capcut_alpha.for_capcut(pf)
        check("capcut: every first-render stretch is ready", all(capcut_alpha.ready(pf) for pf, _a, _d in parts1))
        todo = [i for i, (pf, _a, _d) in enumerate(parts2) if not capcut_alpha.ready(pf)]
        check("capcut: after the edit exactly one stretch needs preparing", todo == [1], todo)

        test_handoff(tmp, out, parts2)
    finally:
        os.environ.pop("REEL_STRETCH_CACHE", None)
        os.environ.pop("REEL_CAPCUT_ALPHA_CACHE", None)
        shutil.rmtree(tmp, ignore_errors=True)


def _hf():
    import reel_render
    return reel_render.HF_VERSION


def test_handoff(tmp, layer, parts_):
    root = os.path.join(tmp, "engine2"); jd = os.path.join(root, "projects", "tiny")
    os.makedirs(os.path.join(jd, "outputs"))
    base = os.path.join(jd, "outputs", "tiny.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=30:duration=25",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=25", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", base], check=True)
    import types
    sys.modules.setdefault("requests", types.ModuleType("requests"))
    import capcut_handoff as H, draft_safety, cleanyap, capcut_tail, capcut_alpha
    calls = []

    def rec(ep, **kw):
        calls.append((ep, kw))
        return {"draft_id": "test"} if ep == "create_draft" else {}
    saved = (H.call, H.ROOT, draft_safety.require_capcut_quit, draft_safety.next_version, cleanyap.finalize,
             capcut_tail.tailed_base, capcut_alpha.for_capcut)
    H.call, H.ROOT = rec, root
    draft_safety.require_capcut_quit = lambda *a, **k: None
    draft_safety.next_version = lambda *a, **k: "tiny 1.1"
    cleanyap.finalize = lambda *a, **k: "tiny 1.1"
    capcut_tail.tailed_base = lambda jd, base, bdur, *a, **k: (base, 0.0)
    capcut_alpha.for_capcut = lambda p: p
    argv, out = sys.argv, io.StringIO()
    sys.argv = ["capcut_handoff.py", "tiny", "--no-overlay", "--pack", "Butter", "--one-clip",
                "--layer", f"captions={layer}@0.5"]
    try:
        with contextlib.redirect_stdout(out):
            H.main()
    except SystemExit as e:
        check("handoff: ran", False, (e, out.getvalue()[-500:]))
    finally:
        sys.argv = argv
        (H.call, H.ROOT, draft_safety.require_capcut_quit, draft_safety.next_version, cleanyap.finalize,
         capcut_tail.tailed_base, capcut_alpha.for_capcut) = saved
    caps = [kw for ep, kw in calls if ep == "add_video" and kw.get("track_name") == "captions"]
    check("handoff: one CapCut clip per stretch", len(caps) == len(parts_), (len(caps), len(parts_)))
    check("handoff: each clip is its stretch's own file", [c["video_url"] for c in caps] == [p_[0] for p_ in parts_])
    check("handoff: each clip sits at its stretch's place on the reel (after the layer's own start)",
          all(abs(c["target_start"] - (0.5 + p_[1])) < 1e-6 for c, p_ in zip(caps, parts_)),
          [(c["target_start"], p_[1]) for c, p_ in zip(caps, parts_)])


def main():
    for t in (test_plan, test_local_and_keys, test_e2e):
        t()
    if fails:
        print(f"test_caption_stretch_cache: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_caption_stretch_cache: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
