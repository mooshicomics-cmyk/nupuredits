#!/usr/bin/env python3
"""render_spans.py — render a caption layer only where it is on screen.

WHY. A caption layer is often on screen for a fraction of the reel: a reel whose captions move to a new spot
half-way through is built as two layers, each blank for the other's stretch. HyperFrames renders a whole
composition, so each of those layers used to capture every frame of the reel, blank ones included (a 1:52
reel split into a chest layer and a side layer rendered 112 s twice, about two minutes of capture each).
The engine's rule has always been "trim overlay dead space > DEAD_GAP s (one segment per active span)"
(build-hf-captions.py), but it was only applied when the layer was PLACED in CapCut, never at render time.

WHAT THIS DOES.
  1. The builder (build-reel-type.py for a caption-only layer, build-hf-captions.py always) calls write_plan()
     on the composition it just wrote. That reads the clips the page really holds, merges them into the
     stretches where text is on screen (split only where nothing shows for more than GAP seconds) and saves
     them as render-spans.json beside index.html. A layer whose text runs from the first word to the last has
     nothing worth trimming, gets no plan, and renders exactly as before.
  2. reel_render.py render (the one gated renderer) runs the check on the FULL composition as always, then,
     when a plan is there, renders one time-shifted copy per stretch (span_comp(): local time 0 = the
     stretch's start) and assemble()s them, with transparent frames in the gaps, into the SAME full-length
     .mov at the same path. The rendered frames are stream-copied, never re-encoded, so every pixel and every
     frame time is what a full render would have produced.
  3. A sidecar, <out>.spans.json, records where each stretch sits on the reel's timeline. Every consumer
     (composite, build-reel-mp4.py, capcut_handoff.py, a job's own driver) reads the full-length file exactly
     as before and never has to know. build-overlay.py lays one CapCut segment per stretch when the footage
     track keeps more clips than that (the magnet anchors to the track with the most clips), so the empty
     parts of the caption track stay clear.

FALLBACK (locked): if the plan cannot be made, a stretch fails to render, or the reassembly does not come out
frame-exact, the layer is rendered full length the way it always was, and the run says so in one plain line.
A consumer that cannot read the sidecar, or finds it does not match the file, uses the whole file. A reel is
never left without its captions.

REEL_FULL_RENDER=1 turns the span render off for a run (the old full-length render).
"""
import json, math, os, re, shutil, subprocess
from html.parser import HTMLParser

FPS = 30
GAP = 3.0            # same DEAD_GAP build-hf-captions.py uses for placement: split only where text is absent > GAP s
STEP = 10.0          # a stretch longer than MAX_SPAN is also cut at the first caption to start after every STEP s of
MAX_SPAN = 12.0      # the reel (a fixed grid: moving one line moves at most the cut next to it), so one edit touches one
MIN_PIECE = 2.0      # stretch; a piece shorter than MIN_PIECE s joins its neighbour
PAD_PRE = 0.10       # small edge pad around each stretch (the same pad the placement spans carry)
PAD_POST = 0.20
PLAN_NAME = "render-spans.json"
CLOCK_LEAD = 0.00001 # a stretch's timeline runs 10 us ahead so a frame never lands a hair before its own moment
# Bumped whenever assemble() changes what it writes. reel_render.py folds it into the render cache key of a layer
# rendered in stretches, so a layer assembled the old way is rendered again rather than reused.
# 2 (2026-10-19): the transparent filler carries the stretch renders' own color tags (see assemble()).
# 3 (2026-10-28): a stretch keeps the editor's caption step-asides on the reel's clock (span_html), and a stretch
#   left blank where its page shows words is never kept (ink_frames / blank_frames). A layer stitched before that
#   could hold captions under a look that replaces them, or blank patches, so it is rendered again.
# 4 (2026-11-02): the 3 fix never reached the real renderer (span_html armed the driver too early there), so every
#   layer stitched under it is rendered again.
ASSEMBLY = 4
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def frames_for(seconds, fps=FPS):
    """How many frames HyperFrames renders for a composition of this duration (measured: ceil(d * fps);
    1.00 s -> 30, 1.01 s -> 31, 1.05 s -> 32). The tiny tolerance keeps 2.1 s (63.000000000000004) at 63."""
    return int(math.ceil(float(seconds) * fps - 1e-6))


def _dur_attr(frames, fps=FPS):
    """A data-duration that HyperFrames turns back into exactly `frames` frames. Written rounded DOWN to the
    microsecond, so ceil() can never tip it one frame over (41/30 written "1.366667" would render 42)."""
    return f"{math.floor(frames / fps * 1e6) / 1e6:.6f}"


class _RootClips(HTMLParser):
    """The direct children of #root, with their tag, attrs and source offsets (start of the opening tag and
    end of the matching closing tag), so a span copy can drop or shift them without re-serialising the page."""

    def __init__(self, src):
        super().__init__(convert_charrefs=False)
        self.src = src
        # line starts counted on "\n" only, the way HTMLParser counts them (splitlines() also breaks on
        # characters like U+2028 that can sit in caption text, and every offset after one would drift)
        self._lines = [0] + [i + 1 for i, ch in enumerate(src) if ch == "\n"]
        self.root = None          # (start offset of the root's opening tag, attrs)
        self.root_end = None
        self.children = []        # [{"tag","attrs","start","end"}]
        self._depth = 0           # depth INSIDE root (0 = not inside)
        self._open = None

    def _off(self):
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.root is None:
            if a.get("id") == "root":
                self.root = (self._off(), a)
                self._depth = 1
            return
        if self._depth == 0 or self.root_end is not None:
            return
        if self._depth == 1:
            self._open = {"tag": tag, "attrs": a, "start": self._off(), "end": None}
            self.children.append(self._open)
        if tag not in _VOID:
            self._depth += 1
        elif self._depth == 1:
            self._open["end"] = self._off() + len(self.get_starttag_text() or "")

    def handle_startendtag(self, tag, attrs):
        if self.root is not None and self.root_end is None and self._depth == 1:
            self.children.append({"tag": tag, "attrs": dict(attrs), "start": self._off(),
                                  "end": self._off() + len(self.get_starttag_text() or "")})

    def handle_endtag(self, tag):
        if self.root is None or self.root_end is not None or self._depth == 0:
            return
        if tag in _VOID:
            return
        self._depth -= 1
        if self._depth == 1 and self._open is not None:
            close = self.src.find(">", self._off())
            self._open["end"] = close + 1
            self._open = None
        elif self._depth == 0:
            self.root_end = self._off()


def read_clips(html):
    """(root_duration, [(start, duration), ...]) for the clips the page holds, or None when the page cannot be
    read with certainty: no #root, a root child that is not a timed clip (it would be on screen the whole
    time), or a sub-composition. None always means "render it full length", never a guess."""
    p = _RootClips(html)
    try:
        p.feed(html)
        p.close()
    except Exception:
        return None
    if p.root is None or p.root_end is None:
        return None
    try:
        dur = float(p.root[1].get("data-duration"))
    except (TypeError, ValueError):
        return None
    if p.root[1].get("data-fps") not in (None, "", str(FPS)):
        return None          # stretches are cut in 30 fps frames; a page at another rate renders whole
    out = []
    for c in p.children:
        a = c["attrs"]
        if c["end"] is None or "clip" not in (a.get("class") or "").split() or "data-composition-src" in a:
            return None
        try:
            out.append((float(a["data-start"]), float(a["data-duration"])))
        except (KeyError, TypeError, ValueError):
            return None
    return dur, out


def plan(html, gap=GAP, fps=FPS):
    """The stretches worth rendering, or None when trimming would not save anything worth a second render
    (the text runs from first word to last, or the page cannot be read). Stretches are whole frames:
    {"duration", "fps", "frames", "spans": [[first_frame, end_frame), ...]}."""
    got = read_clips(html)
    if not got:
        return None
    dur, clips = got
    total = frames_for(dur, fps)
    iv = sorted((s, s + d) for s, d in clips if d > 0)
    if total <= 0 or not iv:
        return None
    merged = []
    for s, e in iv:
        if merged and s - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    spans = []
    for s, e in merged:
        a = max(0, int(math.floor((s - PAD_PRE) * fps + 1e-6)))
        b = min(total, int(math.ceil((e + PAD_POST) * fps - 1e-6)))
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        elif b > a:
            spans.append([a, b])
    if not spans:
        return None
    spans = _grid_split(spans, [_vis(s, d, fps) for s, d in clips], fps)
    dead = (total - sum(b - a for a, b in spans)) / fps
    if dead < gap and len(spans) < 2:
        return None          # on screen (almost) the whole time and short: one full render, exactly as before
    return {"duration": dur, "fps": fps, "frames": total, "spans": spans}


def _vis(start, dur, fps=FPS):
    """The frames [first, end) a clip is on screen in a render: frame k shows at k / fps, a clip shows while
    start <= k / fps < start + duration."""
    return int(math.ceil(start * fps - 1e-6)), int(math.ceil((start + dur) * fps - 1e-6))


def _grid_split(spans, vis, fps=FPS):
    """Cut every stretch longer than MAX_SPAN at the first caption that starts on or after each STEP s mark of the
    reel, so a small caption edit re-renders one ~10 s piece and every other piece comes from the cache. A cut is
    only made where no caption is on screen across it (a clip straddling it could not be shifted)."""
    starts = sorted({a for a, b in vis if b > a})
    step, cap, low = int(round(STEP * fps)), int(round(MAX_SPAN * fps)), int(round(MIN_PIECE * fps))
    out = []
    for a, b in spans:
        if b - a <= cap:
            out.append([a, b]); continue
        cuts, g = [], (a // step + 1) * step
        while g < b:
            f = next((x for x in starts if g <= x < b and not any(p < x < q for p, q in vis)), None)
            if f is None:
                break
            if f - (cuts[-1] if cuts else a) >= low and b - f >= low:
                cuts.append(f)
            g = max(g + step, (f // step + 1) * step)
        edges = [a] + cuts + [b]
        out += [[edges[i], edges[i + 1]] for i in range(len(edges) - 1)]
    return out


def describe(p):
    """One plain line about a plan, for the builder's output."""
    on = sum(b - a for a, b in p["spans"]) / p["fps"]
    n = len(p["spans"])
    return (f"on screen {on:.1f}s of {p['frames'] / p['fps']:.1f}s in {n} stretch{'es' if n != 1 else ''}: "
            f"the render captures only those frames")


def write_plan(comp_dir, html=None):
    """Called by a builder for a caption layer: save render-spans.json beside index.html, or remove a stale
    one when this page is not worth trimming. Returns the plan (or None). Never raises: a plan that cannot be
    made just means the ordinary full-length render."""
    path = os.path.join(comp_dir, PLAN_NAME)
    try:
        if html is None:
            html = open(os.path.join(comp_dir, "index.html"), encoding="utf-8").read()
        p = plan(html)
    except Exception:
        p = None
    try:
        if p:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"_doc": "stretches where this caption layer is on screen, in frames [first, end); "
                                   "reel_render.py renders only these (product/render_spans.py)", **p}, fh, indent=1)
        elif os.path.exists(path):
            os.remove(path)
    except OSError:
        return None
    return p


def clear_plan(comp_dir):
    """A build that is NOT a caption-only layer: drop any plan an earlier caption build left in the folder."""
    try:
        os.remove(os.path.join(comp_dir, PLAN_NAME))
    except OSError:
        pass


def load_plan(comp_dir):
    """The saved plan, checked against the page it was made for; None when absent or no longer true."""
    path = os.path.join(comp_dir, PLAN_NAME)
    if not os.path.exists(path):
        return None
    try:
        saved = json.load(open(path, encoding="utf-8"))
        html = open(os.path.join(comp_dir, "index.html"), encoding="utf-8").read()
    except Exception:
        return None
    fresh = plan(html, fps=int(saved.get("fps", FPS)))
    if not fresh or fresh["spans"] != saved.get("spans") or fresh["frames"] != saved.get("frames"):
        return None          # the page changed after the plan was written: render it whole
    return fresh


_TL_REG = re.compile(r'window\.__timelines\[(["\'])([^"\']+)\1\]\s*=\s*([A-Za-z_$][\w$]*)\s*;')


def span_html(html, first, end, fps=FPS, local=False):
    """The page, time-shifted so local 0 is frame `first` and it lasts end - first frames.

    Clips inside the stretch keep their timing relative to its start. Clips outside it are parked: still in
    the page (so every timeline line that animates them still finds its target) but hidden and untimed.
    The page's own GSAP timeline is left exactly as written and driven from a wrapper timeline that plays it
    from the stretch's start, so every set/tween lands where it did in the full reel. Raises ValueError when
    the page cannot be shifted with certainty (a clip straddling the stretch, no timeline registration).

    local=True (the cached stretch renders): the page holds only this stretch. Clips outside it and the timeline
    lines that only animate them are left out, so the page, and the cache key made from it, is the same whenever
    this stretch's own captions are, whatever changed elsewhere in the reel."""
    p = _RootClips(html)
    p.feed(html)
    p.close()
    if p.root is None or p.root_end is None:
        raise ValueError("no #root")
    t0, t1 = first / fps, end / fps
    # The last stretch ends where the reel does, and the reel's last caption may run past that (the render
    # stops at the reel's end either way), so on that stretch a clip may end beyond it.
    root_dur = float(p.root[1].get("data-duration") or 0)
    tail = end >= frames_for(root_dur, fps)
    edits, parked, outside = [], [], {}
    for n_, c in enumerate(p.children):
        a = c["attrs"]
        s, d = float(a["data-start"]), float(a["data-duration"])
        e = s + d
        v0, v1 = _vis(s, d, fps)
        chunk = html[c["start"]:c["end"]]
        if v1 > v0 and v0 >= first and (v1 <= end or (tail and v0 < end)):
            # rounded DOWN to the microsecond: a word that starts exactly on a frame must still be showing on
            # that frame here, as it is in the full render (round-to-nearest could push it a hair later). A clip
            # whose start falls a hair before the stretch but shows no frame there starts at 0, its end unmoved.
            new = re.sub(r'data-start="[^"]*"', f'data-start="{max(0.0, math.floor((s - t0) * 1e6) / 1e6):.6f}"',
                         chunk, count=1)
            if s < t0:
                new = re.sub(r'data-duration="[^"]*"', f'data-duration="{math.floor((e - t0) * 1e6) / 1e6:.6f}"',
                             new, count=1)
            edits.append((c["start"], c["end"], new))
        elif v1 <= first or v0 >= end or v1 <= v0:
            hidden = re.sub(r'\sdata-(?:start|duration|track-index)="[^"]*"', "", chunk, count=3)
            hidden = re.sub(r'class="([^"]*)"', lambda m: 'class="' + " ".join(
                "hf-span-parked" if k == "clip" else k for k in m.group(1).split()) + '"', hidden, count=1)
            parked.append(hidden)
            outside[n_] = hidden
            edits.append((c["start"], c["end"], ""))
        else:
            raise ValueError(f"a clip ({s:.2f}s-{e:.2f}s) runs across the stretch edge")
    owner = None
    if local:                                                # only this stretch's own clips, and the lines that move them
        owner = {i_: n_ for n_, c in enumerate(p.children) for i_ in re.findall(r'\bid="([^"]+)"', html[c["start"]:c["end"]])}
        parked = [outside[n_] for n_ in sorted(_touched(html, owner, outside))]
    out = html
    for st, en, new in sorted(edits, reverse=True):
        out = out[:st] + new + out[en:]
    # the parked clips go in one hidden holder just inside the root's closing tag
    root_close = p.root_end - sum(en - st - len(new) for st, en, new in edits if st < p.root_end)
    if parked:
        holder = '<div style="display:none" aria-hidden="true">' + "".join(parked) + "</div>\n"
        out = out[:root_close] + holder + out[root_close:]
    # the root's own length becomes the stretch's length
    rs = p.root[0]
    rtag_end = out.find(">", rs) + 1
    rtag = re.sub(r'data-duration="[^"]*"', f'data-duration="{_dur_attr(end - first, fps)}"', out[rs:rtag_end], count=1)
    out = out[:rs] + rtag + out[rtag_end:]
    if local:
        out = _local_script(out, owner, outside)
    m = list(_TL_REG.finditer(out))
    if len(m) != 1:
        raise ValueError("the page does not register exactly one timeline")
    m = m[0]
    key, var = m.group(2), m.group(3)
    pin = ""
    if local:                # the timeline keeps its length past the stretch, so seeking to its end is never clamped
        pin = f'{var}.set({{}},{{}},{t1 + CLOCK_LEAD:.6f});'
    # The stretch's clock runs CLOCK_LEAD ahead of the reel's: driven through a tween, 12.6 can come out as
    # 12.59999999, and a caption that switches exactly on that frame (it did, on a real reel) showed blank. The
    # lead is far below one frame (33,333 us) and below the 1/100 s steps every builder times its words in, so
    # every frame lands on or just past its own moment, the way the full render seeks it.
    a0, a1 = t0 + CLOCK_LEAD, t1 + CLOCK_LEAD
    # The page's own timeline stays registered under its key until the page has finished loading, and the stretch's
    # driver takes its place only then (the last script on the page). A script further down that adds to the
    # timeline by its key (the editor's caption step-asides, <script id="ve-skips">, in reel seconds) used to find
    # the driver instead: its "hide the captions here" landed on the stretch's own short clock, so captions showed
    # under a look that replaces them, and blank patches opened where they should show (two buyers, 2026-10-28).
    # Never armed at the timeline line itself, however far the document has loaded: HyperFrames runs a page's scripts
    # after the document has finished loading, so a readyState test armed it right there, the step-asides went to
    # the driver after all, and a look over her first seconds blanked the start of every stretch (2026-10-31).
    swap = (f'{pin}{var}.pause();{var}.time({a0:.6f},true);'
            f'var __hfSpan=gsap.timeline({{paused:true}});'
            f'__hfSpan.to({var},{{time:{a1:.6f},duration:{t1 - t0:.6f},ease:"none",lazy:false}},0);'
            f'window.__timelines["{key}"]=__hfSpan;')
    wrap = (f'window.__timelines["{key}"]={var};window.__hfSpanArm=function(){{{swap}}};'
            f'if(window.__hfSpanArmDue){{window.__hfSpanArm();window.__hfSpanArm=null;}}')
    out = out[:m.start()] + wrap + out[m.end():]
    arm = ('<script id="hf-span-arm">if(window.__hfSpanArm){window.__hfSpanArm();window.__hfSpanArm=null;}'
           'else{window.__hfSpanArmDue=1;}</script>')
    at = out.lower().rfind("</body>")
    return out[:at] + arm + out[at:] if at >= 0 else out + arm


def _statements(js):
    """The script split at its top-level semicolons, each piece exactly as written (quotes, brackets and comments
    respected). Raises ValueError when it does not balance."""
    out, depth, i, st, q = [], 0, 0, 0, None
    while i < len(js):
        ch = js[i]
        if q:
            if ch == "\\":
                i += 2; continue
            if ch == q:
                q = None
        elif ch in "\"'`":
            q = ch
        elif js.startswith("//", i):
            j = js.find("\n", i); i = len(js) if j < 0 else j; continue
        elif js.startswith("/*", i):
            j = js.find("*/", i + 2)
            if j < 0:
                raise ValueError("an unclosed comment")
            i = j + 2; continue
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                raise ValueError("the script does not balance")
        elif ch == ";" and depth == 0:
            out.append(js[st:i + 1]); st = i + 1
        i += 1
    if q or depth:
        raise ValueError("the script does not balance")
    out.append(js[st:])
    return out


def _tl_script(html):
    """The <script> that registers the timeline: (start, end) of its text, or None."""
    for sm in re.finditer(r"(<script[^>]*>)(.*?)(</script>)", html, re.S):
        if _TL_REG.search(sm.group(2)):
            return sm.start(2), sm.end(2)
    return None


def _refs(line, owner):
    return {owner[x] for x in re.findall(r"#([A-Za-z_][\w-]*)", line) if x in owner}


def _touched(html, owner, outside):
    """The outside clips a kept timeline line still animates (it also moves a clip in the stretch): parked, so that
    line finds its target."""
    at = _tl_script(html)
    if not at:
        raise ValueError("the page does not register exactly one timeline")
    out = set()
    for line in _statements(html[at[0]:at[1]]):
        r = _refs(line, owner)
        if r and not r <= set(outside):
            out |= r & set(outside)
    return out


def _local_script(html, owner, outside):
    """The page without the timeline lines that only animate clips outside the stretch."""
    at = _tl_script(html)
    if not at:
        raise ValueError("the page does not register exactly one timeline")
    js = "".join(x for x in _statements(html[at[0]:at[1]])
                 if not ((r := _refs(x, owner)) and r <= set(outside)))
    return html[:at[0]] + js + html[at[1]:]


def span_comp(src_dir, dst_dir, first, end, fps=FPS, local=False):
    """A renderable copy of the composition for one stretch (fonts and assets alongside, as the page expects)."""
    shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns(".reel_render", "renders", ".DS_Store", PLAN_NAME))
    idx = os.path.join(dst_dir, "index.html")
    html = open(idx, encoding="utf-8").read()
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write(span_html(html, first, end, fps, local=local))
    return dst_dir


# ── the stretch cache: each stretch's render kept by what it shows, so an edit re-renders only its own stretch ──
STRETCH_RECIPE = "3"   # bump when what a stretch render holds changes: every cached stretch renders again
# 3 (2026-11-02): the step-asides really land on the reel's clock now, in HyperFrames as well as in the test (span_html)
# 2 (2026-10-28): the step-asides land on the reel's clock in a stretch (span_html); a stretch cached before could
#   hold captions where a look replaces them, or blank patches where they should show
CACHE_DAYS = 30


def cache_root():
    return os.environ.get("REEL_STRETCH_CACHE") or os.path.join(os.path.expanduser("~"), ".cache",
                                                                "reels-editing-engine", "caption-stretches")


def _assets_hash(comp_dir, html):
    """Every file a stretch copy carries (fonts, images, the HyperFrames config) except the page itself, the plan
    and the builder's notes about the look (look.json, meta.json: they change with every edit and the page never
    reads them). A .json the page names, hyperframes.json and package.json do count."""
    import hashlib
    h = hashlib.sha256()
    for root, dirs, files in os.walk(comp_dir):
        dirs[:] = sorted(x for x in dirs if x not in (".reel_render", "renders", ".hyperframes", "node_modules"))
        for f in sorted(files):
            if f in ("index.html", PLAN_NAME, ".DS_Store"):
                continue
            if f.endswith(".json") and f not in ("hyperframes.json", "package.json") and f not in html:
                continue
            pth = os.path.join(root, f)
            h.update(os.path.relpath(pth, comp_dir).replace(os.sep, "/").encode()); h.update(b"\0")
            with open(pth, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def stretch_keys(comp_dir, p, hf_version, html=None):
    """One cache key per stretch of plan `p`: its own page (local=True), the comp's assets, the renderer's
    version. None for a stretch whose page can't be made on its own (it renders, uncached, the old way)."""
    import hashlib
    if html is None:
        html = open(os.path.join(comp_dir, "index.html"), encoding="utf-8").read()
    assets = _assets_hash(comp_dir, html)
    keys = []
    for first, end in p["spans"]:
        try:
            page_ = span_html(html, first, end, p["fps"], local=True)
        except Exception:
            keys.append(None); continue
        h = hashlib.sha256(f"stretch={STRETCH_RECIPE}|hf={hf_version}|fps={p['fps']}|frames={end - first}|".encode())
        h.update(assets.encode()); h.update(page_.encode("utf-8"))
        keys.append(h.hexdigest()[:32])
    return keys


def cached_stretch(key, frames):
    """The cached render for this key when it is there and whole, else None."""
    if not key:
        return None
    f = os.path.join(cache_root(), key + ".mov")
    if os.path.isfile(f) and os.path.getsize(f) and count_frames(f) == frames:
        try:
            os.utime(f)                                      # a used stretch stays out of the prune
        except OSError:
            pass
        return f
    return None


def store_stretch(key, rendered):
    """Keep a fresh stretch render under its key; returns its cached path (or the render itself when it can't be
    kept). Old entries nobody used in CACHE_DAYS are pruned."""
    if not key:
        return rendered
    root = cache_root()
    try:
        os.makedirs(root, exist_ok=True)
        dst = os.path.join(root, key + ".mov")
        tmp = dst + f".{os.getpid()}.tmp"
        shutil.copyfile(rendered, tmp)
        os.replace(tmp, dst)
    except OSError:
        return rendered
    import time
    cutoff = time.time() - CACHE_DAYS * 86400
    try:
        for e in os.listdir(root):
            pth = os.path.join(root, e)
            if e.endswith(".mov") and pth != dst and os.path.getmtime(pth) < cutoff:
                os.remove(pth)
    except OSError:
        pass
    return dst


def pending_share(comp_dir, hf_version):
    """How much of this caption layer still has to render (0..1 of its frames), for the Finish bar: a stretch in
    the cache costs nothing. None when the layer has no stretch plan (it renders whole)."""
    try:
        p = load_plan(comp_dir)
        if not p:
            return None
        keys = stretch_keys(comp_dir, p, hf_version)
        todo = sum(b - a for (a, b), k in zip(p["spans"], keys)
                   if not (k and os.path.isfile(os.path.join(cache_root(), k + ".mov"))))
        return todo / max(1, p["frames"])
    except Exception:
        return None


def _probe_stream(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,profile,width,height,pix_fmt,color_range,color_space,color_primaries,"
                        "color_transfer", "-of", "json", path],
                       capture_output=True, text=True)
    return (json.loads(r.stdout or "{}").get("streams") or [{}])[0]


def count_frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return int((r.stdout or "").strip().splitlines()[0])
    except (ValueError, IndexError):
        return -1


# ── a stretch that came out blank where its page shows words is never kept ─────────────────────────────────
# A buyer's caption layer rendered in stretches came back with about 15 s blank in the middle of four of them, the
# run said "finished", and the blank stretches were cached, so every later export reused them (2026-10-27). Each
# stretch is now looked at before it is kept or reused: the middle frame of every caption it holds must show
# something, unless the editor has the captions stepping aside there. A blank one is never cached, a blank cached
# one is dropped, and the layer falls back to the ordinary full render.
_SKIP_SETS = re.compile(r'tl\.set\("#root",\{autoAlpha:([01])\},([0-9.]+)\)')


def hidden_windows(html):
    """[(start, end), ...] page seconds where the editor's step-asides (<script id="ve-skips">) hide the layer."""
    m = re.search(r'<script id="ve-skips">(.*?)</script>', html, re.S)
    if not m:
        return []
    out, opened = [], None
    for on, t in _SKIP_SETS.findall(m.group(1)):
        if on == "0" and opened is None:
            opened = float(t)
        elif on == "1" and opened is not None:
            out.append((opened, float(t))); opened = None
    if opened is not None:
        out.append((opened, float("inf")))
    return out


def ink_frames(html, first, end, fps=FPS):
    """Frames of stretch [first, end), counted from its own start, where the page must show something: the middle
    frame of every caption on screen there, leaving out any caption the editor hides (hidden_windows)."""
    got = read_clips(html)
    if not got:
        return []
    hide = hidden_windows(html)
    out = set()
    for s, d in got[1]:
        v0, v1 = _vis(s, d, fps)
        v0, v1 = max(v0, first), min(v1, end)
        if v1 <= v0:
            continue
        lo, hi = v0 / fps, v1 / fps
        if any(a < hi + 1.0 / fps and b > lo - 1.0 / fps for a, b in hide):
            continue                                          # stepping aside (or about to): it may rightly be blank
        out.add((v0 + v1 - 1) // 2 - first)
    return sorted(out)


def blank_frames(mov, frames, fps=FPS):
    """The frames in `frames` (0-based in `mov`) where every pixel is fully transparent. [] when none is, None when
    the file can't be read (never a reason to refuse it). Decoded small with area averaging, so a single opaque
    pixel of a thin letter still counts as something shown."""
    if not frames:
        return []
    w, h = 135, 240
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", mov, "-vf", f"alphaextract,scale={w}:{h}:flags=area",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=600)
    except Exception:
        return None
    b, n = r.stdout, w * h
    if r.returncode != 0 or not b or len(b) % n:
        return None
    count = len(b) // n
    # One value across the whole frame, not only 0: a build of ffmpeg that writes gray in video range makes "nothing
    # here" a 16, and a frame of all 16s is as empty as a frame of all 0s. Any letter anywhere breaks the run.
    return [f for f in frames if f < count and b[f * n] <= 32 and b.count(b[f * n], f * n, (f + 1) * n) == n]


def stretch_is_blank(mov, html, first, end, fps=FPS):
    """True when a stretch render shows nothing where its page shows a caption (ink_frames). False when it looks
    right or can't be read."""
    try:
        bad = blank_frames(mov, ink_frames(html, first, end, fps), fps)
    except Exception:
        return False
    return bool(bad)


def assemble(span_files, p, out, work):
    """Stitch the stretch renders into ONE full-length transparent .mov at `out`: each stretch at its own
    frames, transparent frames between them. Stream copy only (the renders are never re-encoded), then the
    frame count is checked against what a full render makes. Raises RuntimeError on anything off."""
    fps, total, spans = p["fps"], p["frames"], p["spans"]
    if len(span_files) != len(spans):
        raise RuntimeError("one render per stretch is missing")
    for f, (a, b) in zip(span_files, spans):
        n = count_frames(f)
        if n != b - a:
            raise RuntimeError(f"a stretch rendered {n} frames, expected {b - a}")
    st = _probe_stream(span_files[0])
    if st.get("codec_name") != "prores":
        raise RuntimeError(f"stretch renders are {st.get('codec_name')}, not ProRes")
    w, h = st.get("width"), st.get("height")
    os.makedirs(work, exist_ok=True)
    # Transparent filler in the renders' own format: one 30-frame second and one single frame, repeated.
    # Its COLOR TAGS are the renders' own too. Untagged filler between bt709 renders made every switch a change
    # of frame parameters, so ffmpeg rebuilt the whole filtergraph at each one, and the finish's single graph
    # (the overlay plus the sound effects' adelay/amix) stalled there for good on ffmpeg 9: 0% CPU, the same
    # frame every run (a buyer's problem report, 2026-10-18). Same tags throughout = no rebuild.
    tags = []
    for key, flag in (("color_range", "-color_range"), ("color_space", "-colorspace"),
                      ("color_primaries", "-color_primaries"), ("color_transfer", "-color_trc")):
        v = st.get(key)
        if v and v not in ("unknown", "unspecified", "reserved"):
            tags += [flag, v]
    fill = {}
    for n in (fps, 1):
        f = os.path.join(work, f"clear{n}.mov")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            f"color=c=black@0.0:s={w}x{h}:r={fps},format=yuva444p10le", "-frames:v", str(n),
                            "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                            "-vendor", "apl0", *tags, f], capture_output=True, text=True)
        if r.returncode != 0 or count_frames(f) != n:
            raise RuntimeError("could not make the transparent filler: " + (r.stderr or "").strip()[-200:])
        fill[n] = f

    def _q(path):   # concat-list quoting; forward slashes work on Windows too
        return "file '" + os.path.abspath(path).replace("\\", "/").replace("'", "'\\''") + "'\n"

    lines, at = [], 0
    def _gap(n):
        out_ = [_q(fill[fps])] * (n // fps) + [_q(fill[1])] * (n % fps)
        return out_
    for f, (a, b) in zip(span_files, spans):
        lines += _gap(a - at)
        lines.append(_q(f))
        at = b
    lines += _gap(total - at)
    lst = os.path.join(work, "assemble.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    tmp = os.path.join(work, "assembled.mov")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                        "-movflags", "+faststart", tmp], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError("reassembly failed: " + (r.stderr or "").strip()[-200:])
    n = count_frames(tmp)
    if n != total:
        raise RuntimeError(f"the reassembled layer has {n} frames, a full render has {total}")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    shutil.move(tmp, out)
    return out


# ── the sidecar: where each stretch sits on the reel's timeline ─────────────────────────────────────────────
def sidecar_path(mov):
    return os.path.splitext(os.path.abspath(mov))[0] + ".spans.json"


def drop_sidecar(mov):
    try:
        os.remove(sidecar_path(mov))
    except OSError:
        pass


def write_sidecar(mov, p, parts=None):
    """parts: each stretch's own render (the cache), in plan order. CapCut gets those as separate clips, so a
    caption edit re-prepares only the stretch it changed."""
    fps = p["fps"]
    # A stretch's length is its rounded end minus its rounded start, so at + dur lands exactly on the next stretch's
    # at. Rounding the length on its own let one stretch end 1 microsecond inside the next one at 30 fps.
    at = lambda f: round(f / fps, 6)
    dur = lambda a, b: round(at(b) - at(a), 6)
    doc = {"_doc": "where this layer is on screen; the .mov is full length, so a stretch's place in the file IS "
                   "its place on the reel. Written by reel_render.py (product/render_spans.py).",
           "file": os.path.basename(mov), "size": os.path.getsize(mov), "fps": fps, "frames": p["frames"],
           "spans": [{"file": os.path.basename(mov), "at": at(a), "dur": dur(a, b),
                      "frames": [a, b]} for a, b in p["spans"]]}
    if parts and len(parts) == len(p["spans"]):
        doc["parts"] = [{"path": os.path.abspath(f), "size": os.path.getsize(f), "at": at(a),
                         "dur": dur(a, b)} for f, (a, b) in zip(parts, p["spans"])]
    with open(sidecar_path(mov), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return doc


def segments(mov):
    """[(at, dur), ...] seconds where `mov` is on screen, read from its sidecar; None when there is no sidecar
    or it does not belong to this exact file (re-rendered, replaced, copied from elsewhere). None means: use
    the whole file, as before."""
    try:
        doc = json.load(open(sidecar_path(mov), encoding="utf-8"))
        if doc.get("file") != os.path.basename(mov) or int(doc.get("size", -1)) != os.path.getsize(mov):
            return None
        segs = [(float(s["at"]), float(s["dur"])) for s in doc["spans"]]
    except Exception:
        return None
    if not segs or any(d <= 0 or a < 0 for a, d in segs):
        return None
    return segs


def parts(mov):
    """[(path, at, dur), ...]: each stretch's own render, where it sits on the reel; None when the sidecar has no
    parts or any part is gone or changed (then the whole file is laid, as before)."""
    if segments(mov) is None:
        return None
    try:
        doc = json.load(open(sidecar_path(mov), encoding="utf-8"))
        out = []
        for x in doc.get("parts") or []:
            if not os.path.isfile(x["path"]) or os.path.getsize(x["path"]) != int(x["size"]):
                return None
            out.append((x["path"], float(x["at"]), float(x["dur"])))
    except Exception:
        return None
    return out or None
