#!/usr/bin/env python3
"""hooksplit.py — long hook -> headline + subhead (the split-hook pattern).

When a hook is long enough that a single headline would wrap to 3+ lines / climb out of the top safe zone,
splitting it into two BALANCED halves reads with more hierarchy than shrinking everything. Encoded from the
creator's two CapCut variations (2026-08-08):

  • The hook splits into two roughly length-balanced halves at a natural break (a conjunction: and/but/so...).
  • The EMPHASIS half renders in the pack HEADLINE font + size (the loud line).
  • The other half is a SUBHEAD in the pack CAPTION (or accent) font at ~caption size, but in the HOOK's
    CASE + color treatment (it is still the hook, not a read-along caption).
  • READING ORDER IS FIXED: the first half is always physically on top, the second below — the halves are
    NEVER reordered (the hook still has to read left-to-right, top-to-bottom). So the quiet line's position
    is NOT a free choice; it follows from which half carries the emphasis:
      - emphasis on the FIRST half  -> first half is the headline (top), second half is a SUBHEAD below it.
      - emphasis on the SECOND half -> first half is an EYEBROW (small line on top), second half is the
        headline below it.
    "Eyebrow" and "subhead" are the same quiet treatment (pack caption/accent font, hook case), named only by
    position. WHICH half is emphasized is the creator's call, made in the STYLE PLAN. This module does the
    mechanical split + reading-order-correct placement.
  • Placement groups the two as one unit in the upper safe zone (offsets below are from the pack headline y,
    calibrated to the creator's variations: gap ~0.16, headline near the pack y).

Per pack, the subhead font source defaults to the caption role; SUBHEAD_SRC overrides where the accent font
reads better as the quiet line.
"""
import re
import itertools as _it
import packbuild as P


def pinned_font(pack, file_key, name_key, default_name=""):
    """(font file, font name) for a face a PACK pins by file instead of by element (subhead_font_file,
    karaoke_font_file), found the way stylepack.element() finds an element's face: the bundled file, then the
    same font by name wherever this machine has it (capcut_userfonts: her hand-map, CapCut's library, CapCut's
    catalog cache), then the stand-in the pack names for that font on the element that uses it.

    Both engines read these pins through here. Pointing straight at assets/fonts/<file> broke on a buyer
    install: the paid faces are not shipped as files, so the split-hook eyebrow (Butter's Bloop, Playful's
    Ugly Dave) rendered in a default typeface, even for a buyer who had added the font in CapCut. Where the
    bundled file exists (the creator's own machine) this returns exactly that file, as before."""
    import os
    import stylepack as _sp
    pd = _sp.load(pack)
    name = pd.get(name_key) or default_name
    want = _sp._abs(pd[file_key])
    try:
        import capcut_userfonts
        found = capcut_userfonts.resolve_font_file(name, want)
    except Exception:
        found = want if os.path.exists(want) else None
    if found and os.path.exists(found):
        return found, name
    for kind, raw in pd.get("elements", {}).items():   # the stand-in the pack gives this same font
        if raw.get("font") == name:
            e = _sp.element(pack, kind)                  # says out loud that a stand-in is in use
            return e["file"], e["font"]
    return want, name

# ---- SHARED gold-standard type logic (used by BOTH the baked engine and the CapCut engine, so they can't
# drift): MEASURE the real font (never estimate width) and BALANCE into <= max_lines with no orphan word. ----
_MC = {}
def _measure(text, font_path, size_px):
    try:   # Cyrillic the face lacks is drawn from a companion face (script_fonts), so measure it there
        import script_fonts
        parts = script_fonts.split(font_path, text)
        if len(parts) > 1 or parts[0][0] != font_path:
            return sum(_measure(s, p, size_px) for p, s in parts)
    except ImportError:
        pass
    key = (font_path, int(size_px))
    f = _MC.get(key)
    if f is None:
        try:
            from PIL import ImageFont
            f = ImageFont.truetype(font_path, max(8, int(size_px))); _MC[key] = f
        except Exception:
            return len(text) * size_px * 0.6
    return f.getlength(text)
def _balanced(words, font_path, size_px, n):
    """Best contiguous split of words into n lines minimizing the WIDEST line (measured). Balanced by
    construction -> never leaves an orphan word. Returns (widest_px, [lines]) or None if n > word count."""
    if n > len(words):
        return None
    best = None
    for cuts in _it.combinations(range(1, len(words)), n - 1):
        idx = [0] + list(cuts) + [len(words)]
        groups = [" ".join(words[idx[i]:idx[i + 1]]) for i in range(n)]
        widest = max(_measure(g, font_path, size_px) for g in groups)
        if best is None or widest < best[0]:
            best = (widest, groups)
    return best
def fit_balanced(text, font_path, maxw_px, start_px, floor_px=30, max_lines=2, lh=0.92, maxh_px=None):
    """Largest size (px) where `text` balances into <= max_lines within maxw_px (MEASURED) and, if maxh_px is
    given, the block fits maxh_px. Balanced = no orphan words. Returns (size_px, [lines]). Unit-agnostic: the
    baked engine passes CSS px; the CapCut engine passes size*px_per_unit and converts the result back."""
    words = text.split()
    for s in range(int(start_px), int(floor_px) - 1, -2):
        for n in range(1, max_lines + 1):
            b = _balanced(words, font_path, s, n)
            if b and b[0] <= maxw_px and (maxh_px is None or n * s * lh <= maxh_px):
                return s, b[1]
    b = _balanced(words, font_path, int(floor_px), max_lines) or (0, [text])
    return int(floor_px), b[1]

# conjunctions / hinge words we prefer to split a long hook on (kept in the SECOND half)
CONJ = {"and", "but", "so", "because", "yet", "or", "until", "while", "when",
        "before", "after", "though", "although", "if", "then", "even"}
# light connectives worth trimming from the split point to even the two halves ("and STILL miss" -> "and miss")
TRIM = {"still", "just", "really", "actually", "even", "only"}

# per-pack subhead font source: "caption" (default) or "accent"
SUBHEAD_SRC = {"Editorial": "caption", "Butter": "caption", "Playful": "caption"}

# placement offsets from the pack headline y (calibrated to the creator's two variations, Butter pack)
_HEAD_DY_ABOVE, _SUB_DY_ABOVE = -0.04, 0.116   # subhead ABOVE headline
_HEAD_DY_BELOW, _SUB_DY_BELOW = 0.05, -0.113    # subhead BELOW headline


def split_hook(hook):
    """Split a long hook into two roughly length-balanced halves at the most balanced natural break.
    Preserves reading order. Trims one light connective at the hinge if it evens the halves. Falls back to
    the word boundary nearest the char midpoint when there is no conjunction. Returns (first, second)."""
    words = hook.split()
    if len(words) < 4:
        return hook, ""                      # too short to split
    best = None                              # (imbalance, first, second)
    for i in range(1, len(words)):
        if words[i].lower().strip(",.!?") in CONJ:
            a, b = " ".join(words[:i]), " ".join(words[i:])
            imb = abs(len(a) - len(b))
            if best is None or imb < best[0]:
                best = (imb, a, b)
    if best is None:                         # no conjunction -> nearest-midpoint word split
        acc, mid = 0, len(hook) / 2
        for i, w in enumerate(words):
            acc += len(w) + 1
            if acc >= mid:
                return " ".join(words[:i + 1]), " ".join(words[i + 1:])
        return hook, ""
    _, a, b = best
    # trim a light connective right after the hinge word if it improves balance ("and still miss"->"and miss")
    bw = b.split()
    if len(bw) > 2 and bw[1].lower().strip(",.!?") in TRIM:
        cand = " ".join([bw[0]] + bw[2:])
        if abs(len(a) - len(cand)) <= abs(len(a) - len(b)):
            b = cand
    return a, b


def hook_spec(first, second, pack, emphasis="second", lang=None):
    """Reading-order split-hook layers for the CapCut engine, top-to-bottom. `first`/`second` are the two
    halves IN READING ORDER; `first` is always on top (never reordered). `emphasis` ('first'|'second') = which
    half is the loud headline. CapCut renders great at the PACK's native sizes, so the headline keeps its pack
    size (do NOT blow it up to match the baked engine's pixel sizes — CapCut size units are far larger, so a
    big number explodes into huge over-wrapped lines). The other half is the quiet line in the pack caption
    (/accent) font at ~caption size, in the HOOK's case — EYEBROW above (emphasis `second`) / SUBHEAD below
    (emphasis `first`). Returns [top_layer, bottom_layer]."""
    import stylepack as _sp
    pd = _sp.load(pack)
    hl = P.role(pack, "headline")
    # subhead font from the PACK (same source of truth as the well-done engine, so the two can't drift): the
    # subhead_source element, unless the pack overrides with a specific font file (e.g. Playful -> Ugly Dave).
    _ROLE = {"caption": "caption", "accent_caption": "accent", "thought_bubble": "thought"}
    sr = dict(P.role(pack, _ROLE.get(pd.get("subhead_source"), SUBHEAD_SRC.get(pack, "caption"))))
    if pd.get("subhead_font_file"):
        sr["font_path"] = P.capcut_font_path(pinned_font(pack, "subhead_font_file", "subhead_font_name", "Subhead")[0])
    py = hl["y"]
    # Per-pack CapCut tuning (pack fonts render at very different visual sizes at the same "size" unit, so each
    # pack sets its own): headline size + tracking, subhead size, and an eyebrow lift to keep it off the headline.
    cc = pd.get("capcut", {})
    _hsz = cc.get("headline_size", hl["size"])
    _htrk = cc.get("headline_tracking", hl["tracking"])
    _ssz = cc.get("subhead_size")                             # direct eyebrow size, else derived below
    _elift = cc.get("eyebrow_lift", 0)                        # push the quiet line AWAY from the headline
    _hls = cc.get("headline_line_spacing", hl["line_height"]) # CapCut headline line-spacing (creator-tuned)
    # The hook's case, made safe for the reel's language (`lang`: stylepack.job_language(job_dir), None = English):
    # both layers carry it, so a caller that cases each layer's text with it keeps her capitals on a German reel.
    _case = _sp.case_rule(hl["case"], lang=lang)

    def head(text, y):
        # Balance the headline into <=2 lines AT the CapCut size (measured), so it never orphans a word
        # (CapCut's own box-wrap is greedy and orphans on narrow fonts) and never explodes (each balanced half
        # is short enough to sit on one line inside the box).
        cased = P.caseit(text, _case)
        b = _balanced(cased.split(), hl["font_path"], _hsz * 2.2, 2) if len(cased.split()) > 3 else None
        disp = "\n".join(b[1]) if b else cased
        return {"text": disp, "font_path": hl["font_path"], "size": _hsz, "case": _case,
                "tracking": _htrk, "line_height": _hls, "bold": hl["bold"],
                "y": y, "role": "headline"}

    def quiet(text, y, pos):                                   # pos = "eyebrow" (above) | "subhead" (below)
        # eyebrow steps down from the caption size, but NEVER louder than the headline (cap at 0.7x the headline)
        sz = _ssz if _ssz else max(9, round(min(sr["size"] * 0.92, _hsz * 0.7)))
        return {"text": text, "font_path": sr["font_path"], "size": sz,
                "case": _case,                                 # hook case, NOT the caption's lower — it IS the hook
                "tracking": sr["tracking"], "line_height": sr["line_height"], "bold": sr["bold"],
                "y": y, "role": pos}

    if emphasis == "first":                                   # first half loud on top; second is a subhead below
        return [head(first, py + _HEAD_DY_BELOW), quiet(second, py + _SUB_DY_BELOW - _elift, "subhead")]
    # emphasis on second half: first half is an eyebrow on top; second half is the headline below
    return [quiet(first, py + _SUB_DY_ABOVE + _elift, "eyebrow"), head(second, py + _HEAD_DY_ABOVE)]
