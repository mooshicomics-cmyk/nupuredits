#!/usr/bin/env python3
"""test_caption_skips_in_stretches.py — her captions step aside for a look in the EXPORT too, and a caption stretch
that came out blank is never kept or reused.

Two buyers, 2026-10-27/28, both on a caption layer rendered in stretches (render_spans.py):
  * a design of hers that replaces the captions ("hides_captions") played over her normal captions in the exported
    MP4, while the editor's preview showed only hers. The editor's step-asides (<script id="ve-skips">, written by
    visual_editor._apply_skips in the page's own seconds) ran after the stretch had swapped its short driver in for
    the page's timeline, so "hide here" landed on the stretch's own clock: never inside the window it was meant for.
  * the same mistake opened blank patches where captions should show (a step-aside from early in the reel landed
    seconds into a later stretch), the run said "finished", and the blank stretches were cached and reused.

Covered here:
  clock     the page's real scripts, run in node with a small stand-in for GSAP: in every stretch page (whole and
            local) the layer is hidden exactly inside her step-aside windows, as in the full page
  windows   render_spans.hidden_windows reads the step-asides; ink_frames leaves out a caption she steps aside for
  blank     blank_frames finds a fully transparent frame and passes one with a single thin letter on it
  redraw    her restyled captions drawn again at export (finish._refresh_stale) keep their step-asides and her move
  e2e       reel_render with a stand-in HyperFrames: a stretch that renders blank is not cached and the layer
            renders full length (every caption there); a blank stretch already in the cache is dropped and
            rendered again, never stitched in
  versions  stretches and stitched layers made before this fix are rendered again (STRETCH_RECIPE, ASSEMBLY)

Run:  python3 product/tests/test_caption_skips_in_stretches.py
"""
import json
import os
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
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-500:]) if detail else ''}")


def page(dur, clips, comp="cap"):
    """A caption page shaped the way build-reel-type writes one: timed phrase clips, one timeline line set each."""
    cl, tl = [], []
    for i, (s, d) in enumerate(clips):
        cl.append(f'<div class="clip" id="clip-ph{i}" data-start="{s:.2f}" data-duration="{d:.2f}" data-track-index="1">'
                  f'<div class="phrase" id="ph{i}"><span class="pw">word{i}</span></div></div>')
        tl.append(f'tl.set("#ph{i}",{{autoAlpha:0}},0);tl.set("#ph{i}",{{autoAlpha:1}},{s:.2f});'
                  f'tl.set("#ph{i}",{{autoAlpha:0}},{s + d:.2f});')
    return ('<!doctype html><html><head><meta charset="UTF-8"/></head><body>\n'
            f'<div id="root" data-composition-id="{comp}" data-start="0" data-duration="{dur:.2f}" data-width="1080" '
            f'data-height="1920">\n' + "\n".join(cl) + '\n</div>\n<script>window.__timelines=window.__timelines||{};'
            'const tl=gsap.timeline({paused:true});\n' + "\n".join(tl) +
            f'\nwindow.__timelines["{comp}"]=tl;\n</script></body></html>')


def back_to_back(dur, step=1.37, first=0.02):
    out, t = [], first
    while t + step < dur - 0.2:
        out.append((round(t, 2), step)); t = round(t + step, 2)
    return out


def with_skips(html, comp, skips):
    """The page as the editor leaves it: visual_editor._apply_skips adds her step-asides."""
    import visual_editor as ve
    jd = tempfile.mkdtemp(prefix="skips-")
    try:
        os.makedirs(os.path.join(jd, "caps"))
        p = os.path.join(jd, "caps", "index.html")
        open(p, "w", encoding="utf-8").write(html)
        ve._apply_skips(jd, "caps", comp, skips)
        return open(p, encoding="utf-8").read()
    finally:
        shutil.rmtree(jd, ignore_errors=True)


# A stand-in for GSAP just big enough for these pages: timeline().set/.to/.pause/.time, seeking from scratch the way
# GSAP renders a seek (every set at or before the time applied in order; a tween on another timeline's `time`
# drives it linearly). It runs the page's own <script>s in order, as a browser does, then seeks the timeline the
# renderer finds under the page's key and says, for each local time asked, whether #root is hidden.
SIM_JS = r"""
const vm = require("vm");
const inp = JSON.parse(require("fs").readFileSync(0, "utf8"));
function TL() { this.items = []; this._t = 0; }
TL.prototype.set = function (target, vars, pos) { this.items.push({k: "set", target, vars, pos: +pos || 0}); return this; };
TL.prototype.to = function (target, vars, pos) {
  this.items.push({k: "to", target, vars, pos: +pos || 0, from: (target instanceof TL) ? target._t : 0}); return this; };
TL.prototype.pause = function () { return this; };
TL.prototype.time = function (t) { this._t = t; this._render(t); return this; };
TL.prototype._render = function (t) {
  const st = {};
  const items = this.items.map((x, i) => [x, i]).sort((a, b) => a[0].pos - b[0].pos || a[1] - b[1]).map(x => x[0]);
  for (const it of items) {
    if (it.k === "set" && it.pos <= t + 1e-12 && typeof it.target === "string") Object.assign(st[it.target] = st[it.target] || {}, it.vars);
    if (it.k === "to" && it.target instanceof TL && it.vars.time !== undefined) {
      const d = it.vars.duration || 0, f = d > 0 ? Math.min(1, Math.max(0, (t - it.pos) / d)) : 1;
      it.target._render(it.from + (it.vars.time - it.from) * f);
      Object.assign(st, it.target._state);
    }
  }
  this._state = st;
};
const out = [];
for (const pg of inp.pages) {
  const win = {};
  const ctx = vm.createContext({window: win, document: {readyState: inp.readyState}, gsap: {timeline: () => new TL()}});
  win.__timelines = undefined;
  for (const js of pg.scripts) vm.runInContext(js, ctx);
  const tl = win.__timelines[inp.key];
  out.push(pg.times.map(t => { tl.time(t); const r = (tl._state || {})["#root"]; return !!(r && r.autoAlpha === 0); }));
}
process.stdout.write(JSON.stringify(out));
"""


def scripts(html):
    import re
    return re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)


def simulate(key, pages, ready="complete"):
    """[[hidden?, ...], ...] for each (html, local times) in `pages`, or None when node is not on this computer.
    `ready` is what document.readyState says while the page's scripts run: HyperFrames runs them after the document
    has finished loading ("complete"), a plain browser while it loads ("loading"). It must never matter."""
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as t:
        js = os.path.join(t, "sim.js")
        open(js, "w", encoding="utf-8").write(SIM_JS)
        r = subprocess.run([node, js], input=json.dumps({"key": key, "readyState": ready,
                                                       "pages": [{"scripts": scripts(h), "times": ts} for h, ts in pages]}),
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    return json.loads(r.stdout)


# ───────────────────────────────────────────────────────────── clock
def test_clock():
    clips = back_to_back(48)
    skips = [(3.4, 7.6), (25.3, 28.1), (41.0, 44.2)]          # one per region of the reel: early, middle, late
    h = with_skips(page(48, clips), "cap", skips)
    p = R.plan(h)
    check("clock: the layer is planned in several stretches", p and len(p["spans"]) >= 3, p)
    inside = lambda t: any(a <= t < b for a, b in skips)
    near = lambda t: any(abs(t - x) < 0.05 for ab in skips for x in ab)
    frames = [k for k in range(R.frames_for(48)) if not near(k / 30)]
    pages = [(h, [k / 30 for k in frames])]
    for local in (False, True):
        for a, b in p["spans"]:
            pages.append((R.span_html(h, a, b, local=local), [(k - a) / 30 for k in frames if a <= k < b]))
    for ready in ("complete", "loading"):
        got = simulate("cap", pages, ready)
        if got is None:
            print("  ..   node not on PATH: skipping the clock leg"); return
        full = got[0]
        want = [inside(k / 30) for k in frames]
        check(f"clock ({ready}): the full page hides the layer exactly in her windows (the stand-in GSAP reads it right)",
              full == want, [frames[i] for i, (x, y) in enumerate(zip(full, want)) if x != y][:10])
        i = 1
        for local in (False, True):
            bad = []
            for a, b in p["spans"]:
                ks = [k for k in frames if a <= k < b]
                bad += [k for k, hid in zip(ks, got[i]) if hid != inside(k / 30)]
                i += 1
            check(f"clock ({ready}): every {'local ' if local else ''}stretch page hides the layer exactly in her "
                  f"windows, on the reel's clock", not bad, [(k, round(k / 30, 2)) for k in bad[:10]])


# ───────────────────────────────────────────────────────────── windows + ink frames
def test_windows():
    clips = [(1.0, 1.0), (3.0, 1.0), (5.0, 1.0), (7.0, 1.0)]
    h = with_skips(page(10, clips), "cap", [(2.9, 4.2), (6.5, 7.5)])
    check("windows: the step-asides are read back from the page", R.hidden_windows(h) == [(2.9, 4.2), (6.5, 7.5)],
          R.hidden_windows(h))
    check("windows: a page without step-asides has none", R.hidden_windows(page(10, clips)) == [])
    got = R.ink_frames(h, 0, 300)
    check("windows: ink is expected mid-caption, never under a step-aside",
          got == [R._vis(1.0, 1.0)[0] + 14, R._vis(5.0, 1.0)[0] + 14], got)
    got = R.ink_frames(page(10, clips), 120, 300)
    check("windows: frames counted from the stretch's own start", got == [5.0 * 30 + 14 - 120, 7.0 * 30 + 14 - 120], got)


# ───────────────────────────────────────────────────────────── blank frames
def test_blank():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("  ..   ffmpeg not on PATH: skipping the blank-frame leg"); return
    with tempfile.TemporaryDirectory() as t:
        f = os.path.join(t, "s.mov")
        # one thin 1 px opaque line on frames 10..19 of an otherwise clear 30-frame layer
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=1080x1920:r=30",
                        "-f", "lavfi", "-i", "color=white:s=1080x1920:r=30", "-filter_complex",
                        "[0:v]format=gray,drawbox=x=500:y=900:w=1:h=40:color=white:t=fill:enable='between(n,10,19)'[m];"
                        "[1:v][m]alphamerge[o]", "-map", "[o]", "-frames:v", "30", "-c:v", "prores_ks",
                        "-profile:v", "4", "-pix_fmt", "yuva444p10le", f], check=True)
        check("blank: a frame with one thin letter on it is not blank, a clear one is",
              R.blank_frames(f, [5, 12, 18, 25]) == [5, 25], R.blank_frames(f, [5, 12, 18, 25]))
        check("blank: an unreadable file is never called blank", R.blank_frames(os.path.join(t, "none.mov"), [1]) is None)
        check("blank: nothing to look at, nothing blank", R.blank_frames(f, []) == [])
    # a build of ffmpeg that writes gray in video range: "nothing here" comes back as 16, not 0
    n, real = 135 * 240, subprocess.run
    frames = bytes([16]) * n + bytes([16]) * (n - 1) + bytes([40]) + bytes([200]) * n
    subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=frames)
    try:
        check("blank: an all-16 frame is blank too, a letter on one is not, and a solid frame is not",
              R.blank_frames("x.mov", [0, 1, 2]) == [0], R.blank_frames("x.mov", [0, 1, 2]))
    finally:
        subprocess.run = real


# ───────────────────────────────────────────────────────────── end to end
def test_e2e():
    if os.name == "nt":
        print("  ..   the stand-in npx is a POSIX script: skipping the end-to-end leg on Windows"); return
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("  ..   ffmpeg not on PATH: skipping the end-to-end leg"); return
    import test_render_spans as T
    import test_caption_stretch_cache as C
    tmp = tempfile.mkdtemp(prefix="stretch-blank-")
    try:
        script = T.engine_copy(tmp)
        fake = os.path.join(tmp, "bin"); os.makedirs(fake)
        with open(os.path.join(fake, "npx"), "w", encoding="utf-8") as fh:
            fh.write(C.fake_npx(sys.executable))
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
        check("e2e: the layer is planned in stretches", n >= 2, plan)

        def run(out, **extra):
            open(log, "w", encoding="utf-8").close()
            r = subprocess.run([sys.executable, script, "render", comp, "-o", out, "--no-subject", "--force"],
                               capture_output=True, text=True, env=dict(env, **extra), timeout=600)
            return r.returncode, r.stdout + r.stderr, open(log, encoding="utf-8").read().split()

        def ink_ok(mov):
            want = sorted({(a + b - 1) // 2 for a, b in (R._vis(s, d) for s, d in clips)})
            return R.blank_frames(mov, want) == []

        out = os.path.join(tmp, "out", "captions.mov")
        rc, txt, kinds = run(out, FAKE_SPAN="blank")
        check("e2e: a stretch that renders blank falls back to the full render", rc == 0 and kinds == ["span", "full"],
              (rc, kinds, txt[-600:]))
        check("e2e: ...said in one plain line", "came out blank where its captions show" in txt, txt[-600:])
        check("e2e: ...and the layer has every caption", ink_ok(out))
        cached = [f for f in os.listdir(cache)] if os.path.isdir(cache) else []
        check("e2e: ...and nothing blank was kept in the cache", not cached, cached)

        # a blank stretch already in the cache (kept by an older engine) is dropped and rendered again
        os.environ["REEL_STRETCH_CACHE"] = cache
        import reel_render
        keys = R.stretch_keys(comp, plan, reel_render.HF_VERSION)
        os.makedirs(cache, exist_ok=True)
        a, b = plan["spans"][0]
        T.prores(os.path.join(cache, keys[0] + ".mov"), b - a, size="180x320")
        rc, txt, kinds = run(out)
        check("e2e: a blank stretch in the cache is never reused: it renders again", rc == 0 and kinds == ["span"] * n,
              (rc, kinds, txt[-600:]))
        check("e2e: ...and the stitched layer has every caption", ink_ok(out))
        check("e2e: ...and the cache now holds the good one", not R.stretch_is_blank(
            os.path.join(cache, keys[0] + ".mov"), open(os.path.join(comp, "index.html"), encoding="utf-8").read(), a, b))
    finally:
        os.environ.pop("REEL_STRETCH_CACHE", None)
        shutil.rmtree(tmp, ignore_errors=True)


# ───────────────────────────────────────────────────────────── a redraw at export keeps the step-asides
def test_redraw():
    """Her restyled captions (a swap) drawn again at export (finish._refresh_stale: the drawing is older than the
    engine's builder) used to come back without their step-asides: two caption styles at once in the export."""
    import finish, lookbook, visual_editor as ve
    jd = tempfile.mkdtemp(prefix="redraw-")
    d = "hf-graphics/_looks/captions/phrase/hf-reel-type-phrase"
    try:
        os.makedirs(os.path.join(jd, d)); os.makedirs(os.path.join(jd, "review"))
        page_ = os.path.join(jd, d, "index.html")
        open(page_, "w", encoding="utf-8").write(page(20, [(1.0, 2.0), (6.0, 2.0)], comp="captions-phrase"))
        json.dump({"look": "phrase", "text": "word0 word1", "dur": 20}, open(os.path.join(jd, d, "look.json"), "w", encoding="utf-8"))
        json.dump({"pack": "Butter", "layers": [{"name": "captions", "captions": True, "id": "captions-phrase", "dir": d,
                                                 "offset": 0.5, "dur": 20, "skips": [[6.4, 8.6]]}]},
                  open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
        ve._apply_skips(jd, d, "captions-phrase", [(6.4, 8.6)], offset=0.5)
        check("redraw: her page steps aside before the export", 'id="ve-skips"' in open(page_, encoding="utf-8").read())

        def fresh_draw(look, out_dir, *a, **k):                # the builder writes a brand-new page: no step-asides
            open(os.path.join(out_dir, "hf-reel-type-phrase", "index.html"), "w", encoding="utf-8").write(
                page(20, [(1.0, 2.0), (6.0, 2.0)], comp=k.get("comp_id")))
        saved = (ve._swap_pack, ve._adds, ve._swaps, ve._stale_look, lookbook.draw)
        ve._swap_pack = lambda jd_, looks: ("Butter", None)
        ve._adds = lambda jd_: {}
        ve._swaps = lambda jd_: {"captions": {"look": "phrase", "dir": d, "nudge": [0, -40]}}
        ve._stale_look = lambda *a, **k: True
        lookbook.draw = fresh_draw
        try:
            finish._refresh_stale("job", jd)
        finally:
            ve._swap_pack, ve._adds, ve._swaps, ve._stale_look, lookbook.draw = saved
        h = open(page_, encoding="utf-8").read()
        check("redraw: drawn again at export, her captions still step aside, on the page's own clock",
              R.hidden_windows(h) == [(5.9, 8.1)], (R.hidden_windows(h), h[-400:]))
        check("redraw: ...and stay where she moved them", 'id="ve-nudge"' in h and "translate(0px,-40px)" in h)
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_versions():
    check("versions: stretches cached before this fix render again", R.STRETCH_RECIPE != "1")
    check("versions: layers stitched before this fix render again", R.ASSEMBLY >= 3)


def main():
    for t in (test_clock, test_windows, test_blank, test_redraw, test_e2e, test_versions):
        t()
    if fails:
        print(f"test_caption_skips_in_stretches: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗ " + f)
        sys.exit(1)
    print(f"test_caption_skips_in_stretches: all {total} checks passed")


if __name__ == "__main__":
    main()
