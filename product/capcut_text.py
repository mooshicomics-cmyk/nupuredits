#!/usr/bin/env python3
"""capcut_text.py — CROSS-FORMAT text guardrails, shared by every engine (Clean Yap, Super Yap, VO).

the creator's rule (2026-08-02): "this needs to happen on ALL videos — not just clean yap. fixes like this
should not be isolated to one type of video." So the text-injection contract is enforced in ONE place
and called from every finalize, not copy-pasted per format (that's how it drifts).

Two guarantees (see product/CLEANYAP.md "Text-injection contract — LOCKED"):
  1. No stale/overlapping style spans (the "font & color switch mid-line" bug). A text element cloned
     from the caption shell must be ONE span; a genuine keyword-highlight caption has CONTIGUOUS,
     non-overlapping spans. `sanitize_draft_text` repairs ONLY the corrupt case and leaves real
     highlights untouched.
  2. 9:16 wrap: no positive `fixed_width` (forces an oversized box → text runs off the reel frame);
     use auto-wrap at 82% of frame width.

`make_text_material` is the canonical single-span builder for new injectors. `sanitize_draft_text` is
the finalize-time NET that catches text from ANY path (including VectCutAPI-created), in every format.
"""
import json
import os

# --- Studio wrap upgrade (2026-08-07): font-aware, width-based wrapping. ------------------
# REVERT SWITCH: set env CAPCUT_TEXT_WRAP=legacy to fall straight back to the original
# char-count wrapping (the width path is skipped entirely). Default is the new width path.
_WIDTH_WRAP = os.environ.get("CAPCUT_TEXT_WRAP", "width").strip().lower() != "legacy"
_FONT_METRICS_CACHE = {}


# A pre-wrapped MULTI-LINE element (the hook / any display line that already carries hard '\n' breaks)
# needs a REAL box width, or CapCut runs the long line off the reel frame. Proven on the creator's manual
# hook edit (2026-08-08): a no-box hook (fixed_width -1) overflowed BOTH edges; her ~631px box contained
# it. This applies to EVERY pack's hook, not one — the box is a frame-pixel width sized to sit inside the
# x150-930 safe zone (720 centered spans x180-900). Single-line text keeps -1 (CapCut auto-wraps it).
HOOK_BOX_W = 630.0

def apply_wrap_safety(m):
    """9:16 wrap safety. Single-line text: no box (fixed_width -1) so CapCut auto-wraps at 82% width.
    A material that ALREADY carries a real box (a hook, set at build) keeps it — the box governs wrapping and
    must not be reset to -1, or a boxed one-line emphasis gets hard-wrapped into stacked fragments."""
    if not (isinstance(m.get("fixed_width"), (int, float)) and m["fixed_width"] > 0):
        m["fixed_width"] = -1.0
    m["line_max_width"] = 0.82
    m["force_apply_line_max_width"] = False
    return m


# Calibrated to the shipped-correct an example reel draft: at size 17, ~18 chars fit within 82% of the
# 1080-wide 9:16 frame. chars-per-line scales inversely with font size. CapCut does NOT auto-wrap a
# single long line (line_max_width alone won't break it), so long text MUST carry hard '\n' breaks —
# exactly how an example reel ships. This is the ship-safe guard so NO reel, any format, runs off frame.
_CHARS_AT_17 = 18

def chars_per_line(size):
    return max(6, int(round(_CHARS_AT_17 * 17 / max(size, 1))))

def _greedy(words, width):
    lines, line = [], ""
    for w in words:
        if not line:
            line = w
        elif len(line) + 1 + len(w) <= width:
            line += " " + w
        else:
            lines.append(line); line = w
    lines.append(line)
    return lines

def _font_metrics(font_path):
    """(avg_char_advance, measure_fn) for a font at a fixed ref size, or None if it cannot load.
    Advances are relative so the ref size cancels out. Cached per path. Honors the revert switch:
    when _WIDTH_WRAP is off, always returns None so wrap_text takes the legacy char path."""
    if not _WIDTH_WRAP or not font_path:
        return None
    if font_path in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[font_path]
    metrics = None
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(font_path, 100)
        import script_fonts
        def adv(s):
            try:
                w = script_fonts.pil_width(f, s)   # Greek/Cyrillic the face lacks: measured in its companion
                return f.getlength(s) if w is None else w
            except Exception:
                return float(f.getbbox(s)[2]) if s else 0.0
        sample = "abcdefghijklmnopqrstuvwxyz etaoinshrdlu"   # lowercase-weighted, like real captions
        avg = adv(sample) / len(sample)
        if avg > 0:
            metrics = (avg, adv)
    except Exception:
        metrics = None
    _FONT_METRICS_CACHE[font_path] = metrics
    return metrics


def _wrap_width(text, size, metrics):
    """Greedy word-wrap by MEASURED width, font-aware. The budget is the SAME size-17=18-avg-char
    calibration, expressed as a pixel width for THIS font, so a narrower font (or a line full of narrow
    letters) fits more per line. Result: fewer, wider lines. Length-preserving (space<->newline); never
    splits a word; keeps existing hard breaks; keyword-highlight spans stay valid."""
    avg, adv = metrics
    budget = chars_per_line(size) * avg
    out = []
    for para in text.split("\n"):
        words = para.split(" ")
        if len(words) == 1 or adv(para) <= budget:
            out.append(para); continue
        lines, line = [], ""
        for w in words:
            cand = w if not line else line + " " + w
            if not line or adv(cand) <= budget:                 # keep at least one word per line
                line = cand
            else:
                lines.append(line); line = w
        if line:
            lines.append(line)
        out.extend(lines)
    return "\n".join(out)


def _wrap_chars(text, size):
    """LEGACY char-count wrap (the original system). Used whenever width metrics are unavailable or the
    revert switch is set. BALANCED: fewest lines that respect the width, then evened so there's no lonely
    one-word last line, with a full-width fallback when the balance over-splits."""
    cpl = chars_per_line(size)
    out = []
    for para in text.split("\n"):
        words = para.split(" ")
        if len(para) <= cpl or len(words) == 1:
            out.append(para); continue
        n_lines = -(-len(para) // cpl)                       # ceil: fewest lines that respect cpl
        target = max(-(-len(para) // n_lines), max(len(w) for w in words))   # even width, ≥ longest word
        lines = _greedy(words, target)
        # The "even width" target can OVER-SPLIT (greedy packs into more lines than n_lines). Fall back to
        # full-width greedy whenever it over-splits (or overflows), so hooks go wide, not tall.
        if len(lines) > n_lines or any(len(l) > cpl for l in lines):
            lines = _greedy(words, cpl)
        out.extend(lines)
    return "\n".join(out)


def wrap_text(text, size, font_path=None):
    """9:16-safe hard-wrap. Uses the font-aware WIDTH path when the font can be measured (and the revert
    switch is not set), otherwise the LEGACY char-count path. Both are length-preserving so
    keyword-highlight spans stay valid. Callers that pass no font_path get the legacy path (safe default)."""
    m = _font_metrics(font_path)
    if m:
        return _wrap_width(text, size, m)
    return _wrap_chars(text, size)


def _ranges_corrupt(styles, L):
    """True if the style spans are stale/overlapping (the clone bug) — NOT a valid highlight layout.
    Valid highlight = contiguous, non-overlapping, in-bounds spans. Corrupt = out-of-bounds or overlap
    (e.g. a full [0,L] span left on top of leftover [13,26],[26,39] spans from the captured template)."""
    if len(styles) <= 1:
        return False
    rngs = []
    for s in styles:
        r = s.get("range")
        if not (isinstance(r, list) and len(r) == 2):
            return True
        a, b = r
        if a < 0 or b > L or a > b:            # out of bounds vs the actual text
            return True
        rngs.append((a, b))
    rngs.sort()
    for i in range(1, len(rngs)):
        if rngs[i][0] < rngs[i - 1][1]:        # overlap → corrupt
            return True
    return False


WHITE = [1.0, 1.0, 1.0]                          # safe fallback base color (client accents are the exception)


def sanitize_draft_text(d):
    """Finalize-time net for EVERY format (Clean Yap / Super Yap / VO) and every inject path — including
    VectCutAPI-created text. Three guarantees on every text material:
      • collapse corrupt/overlapping spans to ONE span and, since a broken highlight can't carry the right
        accent, default it to WHITE (the creator: "if highlights don't function properly, just default to white");
      • hard-wrap long lines to the 9:16-safe width so nothing runs off frame (CapCut won't auto-wrap a
        single line). Wrap is LENGTH-PRESERVING (space→newline), so keyword-highlight span ranges stay
        valid and are never disturbed; existing manual breaks are kept;
      • 9:16 box safety (no positive fixed_width).
    Valid keyword-highlight captions keep all their spans (only corrupt overlaps are collapsed). Returns
    count of materials touched."""
    touched = 0
    for m in d.get("materials", {}).get("texts", []):
        apply_wrap_safety(m)
        try:
            c = json.loads(m["content"])
        except Exception:
            continue
        text = c.get("text", "")
        styles = c.get("styles") or []
        size = None
        if styles and isinstance(styles[0].get("size"), (int, float)):
            size = styles[0]["size"]
        if size is None:
            size = m.get("font_size") or 12
        fpath = None
        if styles:
            try:
                fpath = (styles[0].get("font") or {}).get("path") or None
            except Exception:
                fpath = None
        changed = False
        # CapCut counts ranges in UTF-16 units (an emoji is 2), so that is the text's real end
        if _ranges_corrupt(styles, len(text.encode("utf-16-le")) // 2):   # corruption → one WHITE span
            st = styles[0]; st["range"] = [0, len(text)]
            try:
                st["fill"]["content"]["solid"]["color"] = WHITE
            except Exception:
                pass
            c["styles"] = [st]; m["text_color"] = "#ffffff"; changed = True
        # Respect an upstream wrap: if the text already carries hard breaks (e.g. packbuild.wrap_for_canvas
        # pre-wrapped it, calibrated to CapCut), do NOT re-break it. sanitize's wrap is only the safety net
        # for single-line text (VectCut-created) that would otherwise run off frame.
        # A material with a real box (a hook, single-line or split) wraps INSIDE the box — CapCut handles it
        # (proven on the creator's manual edits). Never hard-break boxed text; that fights the box and shatters
        # a one-line emphasis into stacked fragments. Only -1/no-box single lines get hard-wrapped (or they run
        # off frame). Length-preserving wrap keeps keyword-highlight spans valid.
        has_box = isinstance(m.get("fixed_width"), (int, float)) and m["fixed_width"] > 0
        wrapped = text if ("\n" in text or has_box) else wrap_text(text, size, fpath)
        if "\n" in wrapped and not has_box:                       # pre-wrapped hook w/o a box -> give it one
            m["fixed_width"] = HOOK_BOX_W
        if wrapped != text:
            c["text"] = wrapped
            if len(c.get("styles", [])) == 1:                     # keep the single span's range in sync
                c["styles"][0]["range"] = [0, len(wrapped)]
            changed = True
        if changed:
            m["content"] = json.dumps(c, ensure_ascii=False)
            touched += 1
    return touched


def make_text_material(shell_material, text, font, size, rgb):
    """Canonical single-span text material from the caption shell. Use in new injectors so text is
    born correct (one span + wrap safety). shell_material = deep-copied TPL['material']."""
    m = shell_material
    text = wrap_text(text, size, font)           # 9:16 hard-wrap so it never runs off frame (font-aware)
    c = json.loads(m["content"])
    st = c["styles"][0]
    st["range"] = [0, len(text)]
    st["size"] = size
    st["fill"]["content"]["solid"]["color"] = list(rgb)
    st.setdefault("font", {})["path"] = font
    st["font"]["id"] = ""
    c["text"] = text
    c["styles"] = [st]                          # collapse — never leave stale spans
    m["content"] = json.dumps(c, ensure_ascii=False)
    hexc = "#%02x%02x%02x" % tuple(int(v * 255) for v in rgb)
    m.update(text_color=hexc, font_size=float(size), alignment=1)
    import capcut_fonts                               # resolve font_path + CapCut library resource_id (buyer portability)
    capcut_fonts.apply(m, font)
    apply_wrap_safety(m)
    return m
