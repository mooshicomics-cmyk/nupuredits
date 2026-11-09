#!/usr/bin/env python3
"""catalog_caption.py — use ANY HyperFrames catalog caption style for a reel's captions, on request.

  python3 product/catalog_caption.py list                    the caption styles in the catalog (name + title)
  python3 product/catalog_caption.py resolve "Kinetic Slam"  what a spoken name maps to (caption-kinetic-slam)

The DEFAULT stays the pack's own captions. A catalog style is used only when the creator names one, and only
on the rendered routes (medium / well done / hands-off), because that is where HyperFrames draws the words.
Raw hands her editable CapCut text, and there is no HyperFrames layer for a catalog style to live on.

How it is wired: set it in the reel's plan, `caption-plan.json` → `"catalog_captions": "Kinetic Slam"`, and
build-reel-type.py calls prepare() below instead of emitting the pack's captions. The prepared style becomes
ONE sub-composition on the captions lane (track 1), so everything downstream is unchanged: LAYER=captions,
separate layers, the CapCut tracks, the well-done bake, and the enforced `hyperframes check` gate.

What prepare() does to a catalog item, which ships as a 1920x1080 demo with its own sample words:
  1. installs it with the pinned CLI (`hyperframes@<pin> add <name>`), never a hand copy
  2. swaps the demo words for this reel's transcript words (the words a takeover or breakaway owns the
     screen over are left out, so two things never fight for the same pixels), and its demo keywords for
     the plan's keywords
  3. narrows it to the 1080 frame (canvas width, and the width its text is fitted to) and sets its length
     to the reel's; its own font sizes stay, so nothing drops under the legibility floor by being scaled
  4. the caller places the 1080x1080 box so its centre sits on the pack's caption height

A style whose demo is not a timed word list (a few are laid out by hand) raises Unsupported with the reason.
Then adapt it by hand under the same gate rather than falling back to the pack captions silently.
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from npx_run import npx_argv, hf_version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME_W = 1080
TEXT_W = 960          # the width a catalog style may fit a line to: 60px clear of each edge
BOX_H = 1080          # the style keeps its own 1080 height; its words sit on that box's centre line


def line_half(src):
    """Half the height of this style's biggest line, plus a 20px gap. Catalog type runs 72 to 220px, so one
    fixed offset puts a big slam word up into her chin (measured: Kinetic Slam at 220px, the subject guard
    refused it). The line's CENTRE goes this far below the top of the open zone under her chin."""
    sizes = [int(n) for n in re.findall(r"fitFontSize\([^,]+,\s*(\d+)", src)
             + re.findall(r"FONT_SIZE\s*=\s*(\d+)", src) + re.findall(r"font-size:\s*(\d+)px", src)]
    return round(max(sizes or [96]) * 0.6) + 20


# Layout written for a widescreen frame that the reel gate refuses, keyed by the style's composition id so a
# fix can never touch another style. Each pair is an exact string in that style's shipped file; a style whose
# file changes simply stops matching and goes back to the gate. All measured on her footage, 2026-09-29.
_LAYOUT_FIXES = {
    # Its "behind" word is stretched 2.8x tall and needs ~960px of height at full size: on a reel it landed on
    # her face (13.6%, refused), then collided with the front line. Scaled down (behind 220 to 120px, front
    # 130 to 80px, over the 58px floor) and stacked in the open zone under her chin. The gate reads the
    # stretched word's ink ~100px lower than its box, so the front line sits 440px under the behind line.
    "caption-parallax-layers": [
        (".behind-safe-zone {\n        position: absolute;\n        top: 40px;\n        left: 0;\n        width: 1080px;\n        height: 500px;",
         ".behind-safe-zone {\n        position: absolute;\n        top: 520px;\n        left: 0;\n        width: 1080px;\n        height: 330px;"),
        (".front-safe-zone {\n        position: absolute;\n        top: 700px;\n        left: 0;\n        width: 1080px;\n        height: 300px;",
         ".front-safe-zone {\n        position: absolute;\n        top: 960px;\n        left: 0;\n        width: 1080px;\n        height: 110px;"),
        ("font-size: 220px;", "font-size: 120px;"),
        ("font-size: 130px;", "font-size: 80px;"),
        ("fitFontSize(behindText, 220,", "fitFontSize(behindText, 120,"),
        ("fitFontSize(frontText, 130,", "fitFontSize(frontText, 80,"),
    ],
    # Its huge italic emphasis word sits on a 0.9 line only 8px under the small line, so the italic ascenders
    # reach up into it (content_overlap, refused). More room between the two lines.
    "caption-editorial-emphasis": [
        (".caption-line + .caption-line {\n        margin-top: 8px;", ".caption-line + .caption-line {\n        margin-top: 44px;"),
    ],
}


class Unsupported(Exception):
    """This catalog style cannot be adapted automatically. The message says why."""


def _npx(*args, cwd=None):
    r = subprocess.run(npx_argv("-y", f"hyperframes@{hf_version()}", *args), cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"hyperframes {' '.join(args)} failed:\n{(r.stderr or r.stdout)[-1200:]}")
    return r.stdout


def list_styles():
    """[(name, title), ...] for every catalog item tagged captions that is a component (the word styles)."""
    items = json.loads(_npx("catalog", "--tag=captions", "--json"))
    items = items if isinstance(items, list) else items.get("items", [])
    return [(i["name"], i.get("title") or i["name"]) for i in items
            if str(i.get("type", "")).endswith("component")]


def _key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("caption-", "", 1))


def resolve(style, styles=None):
    """A spoken style name ("Kinetic Slam", "kinetic slam captions", "caption-kinetic-slam") → catalog name."""
    styles = styles if styles is not None else list_styles()
    want = _key(re.sub(r"\bcaptions?\b", "", style, flags=re.I))
    for name, title in styles:
        if want in (_key(name), _key(title)):
            return name
    near = [t for n, t in styles if want and (want in _key(t) or _key(t) in want)]
    raise LookupError(f"No catalog caption style called '{style}'."
                      + (f" Closest: {', '.join(near)}." if near else "")
                      + f" All of them: {', '.join(t for _, t in styles)}.")


def _array_span(src):
    """(start, end) of the demo's timed word array literal, brackets included."""
    m = re.search(r"(?:var|const|let)\s+\w+\s*=\s*(\[)\s*\{\s*text\s*:", src)
    if not m:
        raise Unsupported("its demo words are not a word list I can swap")
    i = m.start(1); depth = 0
    for j in range(i, len(src)):
        if src[j] == "[": depth += 1
        elif src[j] == "]":
            depth -= 1
            if depth == 0:
                if not re.search(r"\bstart\s*:", src[i:j]):
                    raise Unsupported("its demo words carry no timings, so it cannot follow her voice")
                return i, j + 1
    raise Unsupported("its demo word list never closes")


def _literal_span(src, name):
    """(start, end) of `var NAME = [ ... ]`, brackets included, or None."""
    m = re.search(r"(?:var|const|let)\s+" + name + r"\s*=\s*(\[)", src)
    if not m:
        return None
    i = m.start(1); depth = 0
    for j in range(i, len(src)):
        if src[j] == "[": depth += 1
        elif src[j] == "]":
            depth -= 1
            if depth == 0:
                return i, j + 1
    return None


def _phrases(words, is_kw, most=4):
    """Her words as phrases: at most `most` words, closed at a sentence end or a pause over 0.6s."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        gap = (words[i + 1]["t"] - w["e"]) if i + 1 < len(words) else 9
        if len(cur) >= most or w["w"].strip().endswith((".", "!", "?")) or gap > 0.6:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def _regroup(src, kept, is_kw):
    """Some styles also ship HAND-PICKED groups that point into the demo sentence by word position (which
    words share a line, which one goes huge). Kept as-is they would caption only her first ~20 words, so
    they are rebuilt here from her words. Measured: Editorial Emphasis, Parallax Layers (BLOCKS), Gradient
    Fill, Matrix Decode, Neon Glow (GROUPS). A group shape this does not know is refused, never guessed."""
    notes = []
    sp = _literal_span(src, "GROUPS")
    if sp:
        demo = src[sp[0]:sp[1]]
        if "wordStart" not in demo:
            raise Unsupported("its word groups are a shape I do not know yet")
        ph = _phrases(kept, is_kw)
        rows = []
        for n, g in enumerate(ph):
            nxt = kept[ph[n + 1][0]]["t"] if n + 1 < len(ph) else kept[g[-1]]["e"] + 0.4
            end = max(kept[g[-1]]["e"], min(kept[g[-1]]["e"] + 0.3, nxt - 0.05))
            rows.append("  { wordStart: %d, wordEnd: %d, start: %.3f, end: %.3f }"
                        % (g[0], g[-1], kept[g[0]]["t"], end))
        src = src[:sp[0]] + "[\n" + ",\n".join(rows) + "\n]" + src[sp[1]:]
        notes.append(f"regrouped into {len(rows)} phrases from her words")
    sp = _literal_span(src, "BLOCKS")
    if sp:
        demo = src[sp[0]:sp[1]]
        rows = []
        if "line1" in demo:                      # small line, then a line or ONE huge emphasis word
            cur = []
            for i, w in enumerate(kept):
                if is_kw(i) and cur:
                    rows.append("  { line1: [%s], line2: [[%d, \"e\"]] }" % (", ".join(f'[{k}, "n"]' for k in cur), i))
                    cur = []; continue
                cur.append(i)
                gap = (kept[i + 1]["t"] - w["e"]) if i + 1 < len(kept) else 9
                if len(cur) >= 5 or w["w"].strip().endswith((".", "!", "?")) or gap > 0.6:
                    l1 = ", ".join(f'[{k}, "n"]' for k in cur[:3])
                    l2 = ", ".join(f'[{k}, "n"]' for k in cur[3:])
                    rows.append("  { line1: [%s]%s }" % (l1, f", line2: [{l2}]" if l2 else ""))
                    cur = []
            if cur:
                rows.append("  { line1: [%s] }" % ", ".join(f'[{k}, "n"]' for k in cur))
        elif "front" in demo:                    # one big word behind her, the rest in front
            # the style times a block from its behind word, so a keyword always LEADS its block: the words
            # before it become their own front-only block, or they would appear late
            for g in _phrases(kept, is_kw):
                p = next((n for n, k in enumerate(g) if is_kw(k)), None)
                if p:
                    rows.append("  { behind: null, front: [%s] }" % ", ".join(f"[{k}]" for k in g[:p]))
                    g = g[p:]; p = 0
                if p == 0:
                    rest = ", ".join(f"[{k}]" for k in g[1:])
                    rows.append("  { behind: [[%d]], front: %s }" % (g[0], f"[{rest}]" if rest else "null"))
                else:
                    rows.append("  { behind: null, front: [%s] }" % ", ".join(f"[{k}]" for k in g))
        else:
            raise Unsupported("its word blocks are a shape I do not know yet")
        src = src[:sp[0]] + "[\n" + ",\n".join(rows) + "\n]" + src[sp[1]:]
        notes.append(f"regrouped into {len(rows)} blocks from her words")
    return src, notes


def _norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def prepare(style, words, out_dir, *, duration, keywords=(), windows=()):
    """Install `style` into out_dir/compositions and adapt it to this reel.

    words     [{"w","t","e"}] — the reel's transcript words (the same shape build-reel-type.py uses)
    windows   [(start, end)]  — seconds a takeover or breakaway owns the screen; words inside are left out
    Returns (composition_id, src_relative_to_out_dir, notes, line_half). Raises LookupError / Unsupported."""
    name = resolve(style)
    info = json.loads(_npx("add", name, "--dir", out_dir, "--no-clipboard", "--json", "--force"))
    path = next((p for p in info.get("written", []) + info.get("preserved", []) if p.endswith(".html")), None)
    if not path:
        raise RuntimeError(f"hyperframes add {name} wrote no composition")
    src, notes = adapt(open(path, encoding="utf-8").read(), words, duration=duration,
                       keywords=keywords, windows=windows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    cid = re.search(r'data-composition-id="([^"]+)"', src).group(1)
    return cid, os.path.relpath(path, out_dir).replace(os.sep, "/"), notes, line_half(src)


def adapt(src, words, *, duration, keywords=(), windows=()):
    """The pure half of prepare(): a catalog style's HTML in, this reel's version out, plus notes.
    No network, no files, so it is tested directly (product/tests/test_catalog_caption.py)."""
    notes = []

    kept = [w for w in words if not any(w["t"] < b and w["e"] > a for a, b in windows)]
    if len(kept) < len(words):
        notes.append(f"{len(words) - len(kept)} word(s) left out under takeovers/breakaways")
    a, b = _array_span(src)
    body = ",\n".join('  { text: %s, start: %.3f, end: %.3f }' % (json.dumps(w["w"].strip()), w["t"], w["e"])
                      for w in kept)
    src = src[:a] + "[\n" + body + "\n]" + src[b:]

    kw = {_norm(k) for k in keywords if isinstance(k, str)} - {""}
    src, gnotes = _regroup(src, kept, lambda i: _norm(kept[i]["w"]) in kw)
    notes += gnotes
    def _kwset(m):
        inner = m.group(2).strip()
        if inner and re.fullmatch(r"[\d,\s]+", inner):      # demo keyed by word index
            vals = [str(i) for i, w in enumerate(kept) if _norm(w["w"]) in kw]
        else:                                                # demo keyed by the word itself
            vals = [json.dumps(k) for k in sorted(kw)]
        return f"{m.group(1)}new Set([{', '.join(vals)}])"
    src = re.sub(r"(KEYWORDS\s*=\s*)new Set\(\[([^\]]*)\]\)", _kwset, src)

    dur = f"{duration:.2f}"
    src = re.sub(r'data-duration="[\d.]+"', f'data-duration="{dur}"', src)
    src = re.sub(r"\b(DURATION\s*=\s*)[\d.]+", rf"\g<1>{dur}", src)

    src = src.replace("width: 1920px", f"width: {FRAME_W}px").replace("width:1920px", f"width:{FRAME_W}px")
    src = src.replace('data-width="1920"', f'data-width="{FRAME_W}"').replace("width=1920", f"width={FRAME_W}")
    src = re.sub(r",\s*1[4-9]\d\d\s*\)", f", {TEXT_W})", src)                  # fitFontSize(..., maxWidth)
    src = re.sub(r"\b([A-Z_]*WIDTH\s*=\s*)1[4-9]\d\d\b", rf"\g<1>{TEXT_W}", src)      # SAFE_WIDTH, PILL_MAX_WIDTH, ...
    src = re.sub(r"(max-width:\s*)1[4-9]\d\dpx", rf"\g<1>{TEXT_W}px", src)
    cid = (re.search(r'data-composition-id="([^"]+)"', src) or [None, ""])[1]
    for old, new in _LAYOUT_FIXES.get(cid, []):
        if old not in src:
            notes.append(f"a layout fix for {cid} no longer matches its file: the gate decides")
        src = src.replace(old, new)
    left = sorted(set(re.findall(r"(?<![-\w])(1920|1[4-9][0-9]{2})\b", src)))   # a -1920 slide-in stays off-frame
    if left:
        notes.append(f"widescreen numbers still in the file ({', '.join(left)}): "
                     "the gate's frame check is what proves the words stay on screen")
    return src, notes


def clip_html(cid, rel, duration, centre_y, track=1):
    """The one clip that puts a prepared catalog style on the captions lane, its words centred on centre_y."""
    top = round(centre_y - BOX_H / 2)
    return (f'<div class="clip" id="clip-catcap" data-composition-id="{cid}" data-composition-src="{rel}" '
            f'data-start="0" data-duration="{duration:.2f}" data-track-index="{track}" '
            f'data-width="{FRAME_W}" data-height="{BOX_H}" '
            f'style="position:absolute;left:0;top:{top}px;width:{FRAME_W}px;height:{BOX_H}px"></div>')


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for n, t in list_styles():
            print(f"  {t:<22} {n}")
    elif cmd == "resolve" and len(sys.argv) > 2:
        try:
            print(resolve(" ".join(sys.argv[2:])))
        except LookupError as e:
            sys.exit(str(e))
    else:
        sys.exit(__doc__)
