#!/usr/bin/env python3
"""clean-captions/build.py: Clean Captions, burned in as still images so the pass always finishes.

Where it runs: pull-reels calls it for a reel asked for with `--captions clean`, and for any reel whose
style-pack captions did not finish (.claude/skills/pull-reels/scripts/cut-shorts.py). A single reel is
captioned by its style pack or by CapCut's Auto Captions, never here. The look is described in
presets/clean-captions-style.md.

In: a job folder whose rough cut is done, so outputs/<job>.transcript.json (her kept words, already timed to
the cut) and, when the job has one, subject-zones.json (where her chin sits). Out: the cut with two kinds of
layer on it, each a transparent still that ffmpeg switches on and off at its times:
  - the hook block, only when there is hook copy: one of the three hook shapes in
    workflows/capcut-export/WRITING-THE-HOOK.md at the top of the frame while the hook plays (hook_exit()
    below says when it leaves; --hook-end sets that outright; --hook-emphasis first makes the first line
    the headline)
  - her captions, a short phrase at a time from her first word to her last, under her chin, each one up
    until the next begins
Nothing slides, fades or scales.

Type and color are the style pack's, by job (headline, quiet line, caption): --pack, else STYLE_PACK, else
her saved default (product/creative-vault/user-style.json). With no pack, or one this computer cannot read,
it uses the starter look (Inter on neutral white) and says so in one line.

Pillow draws every layer and ffmpeg only places the images over the cut, so no HyperFrames render is
involved and nothing is transcribed again.

    python3 presets/clean-captions/build.py projects/<job> --hook "your hook" --out projects/<job>/outputs/<job>.final.mp4
    python3 presets/clean-captions/build.py projects/<job> --preview 30 --hook "your hook"   # first 30 s only
    add --pack Butter for another pack, or --pack starter for the starter look on purpose
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

ENGINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ENGINE / "product"))
from video_encoder import pick_encoder   # the engine's one encoder choice, shared by every ffmpeg render
import safe_zones                        # where the platform draws its own UI: one source for every builder
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---- THE FRAME --------------------------------------------------------------------------------------
W, H = safe_zones.W, safe_zones.H
MID_X = W / 2
SAFE_TOP, SAFE_BOT = safe_zones.TOP, safe_zones.BOTTOM
TYPE_WIDTH = safe_zones.RIGHT - safe_zones.LEFT     # the hook and the captions wrap inside the safe box
HOOK_TOP = SAFE_TOP + 10               # the first ink of the hook block, the same line the pack route uses
QUIET_COMFORT = 40                     # px: the smallest an eyebrow or subhead is drawn when it can be bigger
HEADLINE_ROOM = 230                    # px of height the headline may take: the pack route's split-hook budget
SIZE_SCALE = 6.0                       # pack size units -> px on the 1080 frame (as build-reel-type.py reads them)
FONTS = ENGINE / "assets" / "fonts"

# ---- THE STARTER LOOK (no pack chosen) ---------------------------------------------------------------
# The engine's own neutral defaults (presets/type-and-look.md): Inter, white, a dark shadow from the engine's
# ink (pack_palettes.INK) so it reads on a bright wall or a dark room. Written in the same units as a pack's
# elements, so a pack and the starter go through one code path.
STARTER = {
    "headline": {"file": "Inter-Black.otf", "size": 17, "case": None, "one_line_min": 80},   # 102px before fitting
    "quiet":    {"file": "Inter-Bold.otf", "ratio": 0.5},                    # eyebrow / subhead, half the headline
    "caption":  {"file": "Inter-SemiBold.ttf", "size": 11, "y": -0.2, "case": None},   # 66px, y1152 unmeasured
    "hook_color": "#FFFFFF",
    "quiet_color": "#FFFFFF",
    "caption_color": "#FFFFFF",
    "shadow": "0 0 2px rgba(17,17,17,.8), 0 2px 4px rgba(17,17,17,.5), 0 6px 18px rgba(17,17,17,.35)",
}
CAPTION_HOME_Y = round(H / 2 - STARTER["caption"]["y"] * H / 2)   # starter caption centre with no measurement

# ---- HER HOOK DEFAULTS -------------------------------------------------------------------------------
# A reel's own --hook copy always wins; these only fill in when a reel brings none.
HOOK_COPY = ""          # hook copy for every reel that names none (blank: no hook unless the reel brings one)
HOOK_CUE_WORDS = ()     # words she says to close her hook out loud, e.g. ("okay",): the hook leaves as she
                        # moves on from the first one she says
# All four stay plain one-line assignments: an update carries her values across in exactly this form.
# DEFAULT_HOOK_TEXT and HOOK_END_WORDS: older names of HOOK_COPY and HOOK_CUE_WORDS, still accepted.
DEFAULT_HOOK_TEXT = ""  # older name, still accepted
HOOK_END_WORDS = ()

# How long the hook holds when nothing says otherwise: the hook block's ~8 s (hook_end) from
# workflows/capcut-export/WRITING-THE-HOOK.md, landed on the sentence break nearest to it.
HOOK_HOLD = 8.0

# ---- PHRASES ------------------------------------------------------------------------------------------
PHRASE_WORDS = 5                         # a phrase closes at this many words (the pack route's phrase default)
THOUGHT_ENDS = (".", "?", "!", "…")      # a word ending in one of these ends a thought (and a phrase)
PHRASE_BREAKS = THOUGHT_ENDS + (",", ";", ":")
QUIET_MARKS = ".,;:…"                    # dropped from the end of a phrase on screen; ? and ! stay
FINAL_HOLD = 0.6                         # seconds the last phrase stays up after her last word


# ---- WORDS -----------------------------------------------------------------------------------------
# A transcribed word = leading marks, the word, trailing marks. Only the middle is looked up, so a fix
# keeps the punctuation around it: "claude," reads "Claude,".
_WORD_PARTS = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)


def load_word_fixes(repo_root):
    """The one-word fixes ("words") of presets/caption-corrections.json (as heard -> as written), or nothing
    when the file is not there; a table kept from an earlier version may hold them under "auto". A key only
    matches as written, so keys belong in lowercase."""
    fixes = {}
    path = os.path.join(repo_root, "presets", "caption-corrections.json")
    if os.path.exists(path):
        table = json.load(open(path, encoding="utf-8"))
        for key in ("words", "auto"):
            fixes.update(table.get(key) or {})
    return fixes


def shown_as(word, fixes):
    """The word as it reads on screen: a listed mishear swapped for its fix, marks kept. Anything that is
    all marks, or not in the table, or mapped to an empty fix, comes back exactly as heard."""
    lead, core, trail = _WORD_PARTS.match(word).groups()
    fix = fixes.get(core.lower()) if core else None
    return f"{lead}{fix}{trail}" if fix else word


def in_case(text, case):
    """The pack's case for a job: "upper", "lower", "title", or None for as written."""
    return text.upper() if case == "upper" else text.lower() if case == "lower" else \
        text.title() if case == "title" else text


def phrases(words, case=None, fits=None):
    """Group the words into on-screen phrases -> [{"text", "start", "end", "said"}], in order ("said" holds
    the start of every spoken word the phrase carries).

    A phrase closes at a mark that ends a clause or a thought, at PHRASE_WORDS words (one more when that
    word ends the thought), or before a word that would push it onto a second line (`fits`, measured in the
    look's own caption face). It then stays up until the next phrase starts, so the captions never blink off
    between phrases, and the last one holds FINAL_HOLD seconds past her last word.

    Every word the kept-words transcript holds is one she meant to keep (the rough cut already decided what
    was a false start), so every word is captioned. A one-word phrase that would be up for less time than
    she takes to say a typical word of this reel would only flash, so it rides along with a neighbour on the
    same line instead: the phrase before it when it ends a thought ("is."), the one after it otherwise
    ("No, / seriously" reads "No, seriously"). When neither fits on one line it stays up on its own."""
    groups, group = [], []

    def fits_line(members):
        return not fits or fits(in_case(" ".join(m["disp"] for m in members), case))

    def close():
        if group:
            groups.append(list(group))
            group.clear()

    for i, word in enumerate(words):
        if group and not fits_line(group + [word]):
            close()
        group.append(word)
        if word["disp"].rstrip().endswith(PHRASE_BREAKS):
            close()
        elif len(group) >= PHRASE_WORDS:
            # a full phrase still takes the next word when that word ends the thought and fits the line,
            # so a thought never leaves one word stranded on screen by itself ("mind / game")
            nxt = words[i + 1] if i + 1 < len(words) else None
            if not (nxt and nxt["disp"].rstrip().endswith(PHRASE_BREAKS) and fits_line(group + [nxt])):
                close()
    close()

    lengths = sorted(float(w["end"]) - float(w["start"]) for w in words if _bare(w["text"]))
    typical = lengths[len(lengths) // 2] if lengths else 0.0
    i = 0
    while i < len(groups) - 1:
        here = groups[i]
        up_for = float(groups[i + 1][0]["start"]) - float(here[0]["start"])
        if sum(1 for m in here if _bare(m["text"])) != 1 or up_for >= typical:
            i += 1
            continue
        ends_thought = here[-1]["disp"].rstrip().endswith(THOUGHT_ENDS)
        if ends_thought and i > 0 and fits_line(groups[i - 1] + here):
            groups[i - 1] += groups.pop(i)
        elif fits_line(here + groups[i + 1]):
            groups[i + 1] = here + groups[i + 1]
            groups.pop(i)
        else:
            i += 1

    out = []
    for members in groups:
        text = " ".join(m["disp"] for m in members).rstrip(QUIET_MARKS).strip()
        if text:
            out.append({"text": in_case(text, case), "start": members[0]["start"], "end": members[-1]["end"],
                        "said": [float(m["start"]) for m in members if _bare(m["text"])]})
    for phrase, following in zip(out, out[1:]):
        phrase["end"] = following["start"]
    if out:
        out[-1]["end"] += FINAL_HOLD
    return out


def _bare(text):
    """A word as heard, without case or the marks around it: "Okay," -> "okay"."""
    return _WORD_PARTS.match(str(text)).group(2).lower()


def hook_exit(words, pinned=None, hold=HOOK_HOLD):
    """When the hook leaves the frame, and why -> (seconds, reason).

    A time given for this reel (--hook-end, a plan's hook_end) is used as given. Else, when she has cue words
    and says one, the hook leaves as her next word begins. Else it holds the hook block's usual ~`hold`
    seconds, ending where she starts the sentence after the break nearest that mark (on the words as heard,
    before any fix), so it never leaves mid-sentence. No sentence break at all: the gap between two words
    nearest the mark; no words at all: the mark itself."""
    if pinned is not None:
        return float(pinned), "the time given for this reel"

    def leaves_after(i):
        return float(words[i + 1]["start"]) if i + 1 < len(words) else float(words[i]["end"])

    cues = {_bare(c) for c in (tuple(HOOK_CUE_WORDS) or tuple(HOOK_END_WORDS)) if _bare(c)}
    said = next((i for i, w in enumerate(words) if cues and _bare(w["text"]) in cues), None)
    if said is not None:
        return leaves_after(said), f"as she moves on from \"{words[said]['text'].strip()}\""
    for pick, what in ((lambda w: str(w["text"]).rstrip().endswith(THOUGHT_ENDS), "the sentence break"),
                       (lambda w: True, "the pause between words")):
        breaks = [leaves_after(i) for i, w in enumerate(words) if pick(w)]
        if breaks:
            at = min(breaks, key=lambda t: (abs(t - hold), -t))
            return at, f"{what} nearest {hold:g} s"
    return hold, "the hook block's usual hold; there are no words to land it on"


# ---- THE LOOK: her pack, or the starter -------------------------------------------------------------
def saved_pack():
    """Her saved default style pack (product/creative-vault/user-style.json "default_pack"), or None."""
    try:
        with open(ENGINE / "product" / "creative-vault" / "user-style.json", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("default_pack") or None
    except Exception:
        return None


def _learned(field, default):
    """A preference she taught (product/learned.py), else the default. Never takes the build down."""
    try:
        import learned
        return learned.get(field, default)
    except Exception:
        return default


def _shadows(css):
    """A CSS text-shadow list -> [(dx, dy, blur, (r, g, b, a))]. Anything unreadable is left out."""
    out = []
    for m in re.finditer(r"(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+([\d.]+)(?:px)?\s+"
                         r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", css or ""):
        dx, dy, blur, r, g, b, a = m.groups()
        out.append((float(dx), float(dy), float(blur), (int(r), int(g), int(b), float(a or 1))))
    return out


def starter_look(why):
    s = STARTER
    cap_px = round(s["caption"]["size"] * SIZE_SCALE * _learned("caption.size_scale", 1.0))
    return {
        "name": "starter", "why": f"the starter look (Inter, white): {why}",
        "head_file": str(FONTS / s["headline"]["file"]), "head_px": round(s["headline"]["size"] * SIZE_SCALE),
        "case": s["headline"]["case"], "one_line_min": s["headline"]["one_line_min"],
        "quiet_file": str(FONTS / s["quiet"]["file"]), "quiet_ratio": s["quiet"]["ratio"],
        "cap_file": str(FONTS / s["caption"]["file"]), "cap_case": s["caption"]["case"],
        "cap_px": max(safe_zones.MIN_PX["caption"], cap_px), "cap_y": CAPTION_HOME_Y,
        "hook_color": s["hook_color"], "quiet_color": s["quiet_color"], "cap_color": s["caption_color"],
        "shadow": _shadows(s["shadow"]),
    }


def pack_look(name):
    """The burn-in edition of a style pack: its headline face and case for the hook, its subhead face for the
    quiet line, its caption face, size and height for the captions, its hook colors and its shadow. Raises
    when the pack cannot be read; a missing face drops to the stand-in stylepack names, out loud."""
    import stylepack
    pack = stylepack.load(name)
    head = stylepack.element(name, "headline")
    cap = stylepack.element(name, "caption")
    quiet = dict(stylepack.element(name, pack.get("subhead_source", "caption")))
    if pack.get("subhead_font_file"):            # a pack can pin its quiet line to any face
        import hooksplit
        quiet["file"], quiet["font"] = hooksplit.pinned_font(name, "subhead_font_file", "subhead_font_name", "Subhead")
    for e in (head, cap, quiet):
        if not os.path.exists(e["file"]):
            raise FileNotFoundError(f"no font file for {e.get('requested_font') or e.get('font')}")
    wd = pack.get("welldone", {})
    designed = cap["size"] * SIZE_SCALE * float(wd.get("single_scale", wd.get("caption_scale", 1.0)))
    hook_color = wd.get("hook_color") or "#FFFFFF"
    return {
        "name": name, "why": f"the {name} style pack",
        "head_file": head["file"], "head_px": round(head["size"] * SIZE_SCALE), "case": head.get("case"),
        "one_line_min": float(wd.get("head_one_min", 100)),
        "quiet_file": quiet["file"],
        "quiet_ratio": cap["size"] * 0.92 / max(head["size"], 1) * float(wd.get("eyebrow_scale", 1.0)),
        "cap_file": cap["file"], "cap_case": cap.get("case"),
        # never below the pack's own designed size, and never below the legibility floor
        "cap_px": max(safe_zones.MIN_PX["caption"], round(designed * _learned("caption.size_scale", 1.0))),
        "cap_y": round(H / 2 - float(cap.get("y", 0.0)) * H / 2),
        "hook_color": hook_color, "quiet_color": wd.get("subhead_color") or hook_color, "cap_color": "#FFFFFF",
        "shadow": _shadows(wd.get("text_shadow")) or _shadows(STARTER["shadow"]),
    }


def resolve_look(asked):
    """The look for this run: the pack asked for, else STYLE_PACK, else her saved default; the starter when
    none is chosen ("starter" asks for it on purpose) or when the pack cannot be drawn on this computer."""
    name = asked or os.environ.get("STYLE_PACK") or saved_pack()
    if not name or str(name).strip().lower() in ("starter", "none"):
        return starter_look("no style pack is chosen yet" if not name else "asked for by name")
    try:
        return pack_look(str(name).strip())
    except Exception as e:
        return starter_look(f"the {name} pack could not be drawn here ({type(e).__name__}: {e})")


# ---- DRAWING ---------------------------------------------------------------------------------------
_FACES = {}


def face(path, size):
    key = (path, int(size))
    if key not in _FACES:
        try:
            _FACES[key] = ImageFont.truetype(path, int(size))
        except OSError:
            _FACES[key] = ImageFont.truetype(str(FONTS / STARTER["caption"]["file"]), int(size))
    return _FACES[key]


def blank():
    """A fully transparent full-frame layer."""
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def measure(text, path, size):
    return face(path, size).getlength(text)


def balanced(text, path, size, rows):
    """`text` split into `rows` lines with the narrowest widest line (no orphan word) -> (widest, lines)."""
    words = text.split()
    if rows < 2 or len(words) < 2:
        return measure(text, path, size), [text]
    best = None
    for cut in range(1, len(words)):           # two lines at most: the hook and a caption never stack higher
        lines = [" ".join(words[:cut]), " ".join(words[cut:])]
        widest = max(measure(ln, path, size) for ln in lines)
        if best is None or widest < best[0]:
            best = (widest, lines)
    return best


def fit(text, path, start, floor, max_rows=2, room=None, leading=1.0):
    """The largest size from `start` down to `floor` at which `text` sits in <= max_rows balanced lines
    inside TYPE_WIDTH (and inside `room` px tall when given) -> (size, lines). Measured, never guessed.
    Nothing fits: the floor size, balanced, and the caller's own trim keeps it on the frame."""
    for size in range(int(start), int(floor) - 1, -2):
        for rows in range(1, max_rows + 1):
            widest, lines = balanced(text, path, size, rows)
            if widest <= TYPE_WIDTH and (room is None or rows * size * leading <= room):
                return size, lines
    return int(floor), balanced(text, path, int(floor), max_rows)[1]


def set_type(runs, shadow):
    """Stack text runs top to bottom, centred, with the look's shadow under them -> a tight RGBA image.
    runs = [(lines, path, size, color, gap_after_px)]. The image is cropped to the ink, so its top edge IS
    the first ink, which is how the hook block lines up on HOOK_TOP and a caption on her chin line."""
    pad = 60
    height = sum(len(lines) * round(size * 1.12) + gap for lines, _p, size, _c, gap in runs) + 2 * pad
    ink = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    pen = ImageDraw.Draw(ink)
    y = pad
    for lines, path, size, color, gap in runs:
        font = face(path, size)
        for line in lines:
            pen.text((MID_X, y), line, font=font, fill=color, anchor="ma")
            y += round(size * 1.12)
        y += gap
    mask = ink.getchannel("A")
    out = Image.new("RGBA", ink.size, (0, 0, 0, 0))
    for dx, dy, blur, (r, g, b, a) in reversed(shadow):     # CSS paints the first shadow on top
        soft = mask.filter(ImageFilter.GaussianBlur(blur / 2)) if blur else mask
        soft = soft.point(lambda v, a=a: round(v * a))
        layer = Image.new("RGBA", ink.size, (r, g, b, 0))
        layer.putalpha(ImageChops.offset(soft, round(dx), round(dy)))
        out.alpha_composite(layer)
    out.alpha_composite(ink)
    drawn = mask.getbbox()
    if not drawn:
        return None
    shown = out.getbbox()
    return out.crop(shown), drawn[1] - shown[1], drawn[3] - shown[1]   # image, ink top and bottom inside it


def place(art, x_centre, ink_top):
    """Put a set_type image on the frame with its first ink at ink_top -> (image, x, y), kept on the frame."""
    img, top_in, _bottom_in = art
    x = round(x_centre - img.width / 2)
    y = round(ink_top - top_in)
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(img.width, W - x), min(img.height, H - y)
    return img.crop((left, top, right, bottom)), max(0, x), max(0, y)


def hook_parts(copy, emphasis="second"):
    """The hook copy as a WRITING-THE-HOOK shape -> [(text, "headline"|"quiet")] top to bottom.
    One line: a hook card. Two or more: the first line and the rest, as an eyebrow over the headline
    (emphasis "second", the default) or a headline over its subhead (emphasis "first"). Reading order
    never changes; only which half is big."""
    lines = [ln.strip() for ln in (copy or "").split("\n") if ln.strip()]
    if not lines:
        return []
    if len(lines) == 1:
        return [(lines[0], "headline")]
    first, rest = lines[0], " ".join(lines[1:])
    if emphasis == "first":
        return [(first, "headline"), (rest, "quiet")]
    return [(first, "quiet"), (rest, "headline")]


def render_hook(copy, look, emphasis="second"):
    """The hook block as a layer -> (image, x, y, ink_top, ink_bottom, rows) with its first ink on HOOK_TOP,
    or None when the copy has no ink. `rows` counts the headline's rows plus any the quiet line wraps onto
    (its one designed row is part of the shape), which is how hook_notes knows the hook runs long. The headline is fitted to the width and HEADLINE_ROOM; the quiet line steps down from it by
    the look's ratio, on one line when it fits."""
    parts = hook_parts(copy, emphasis)
    if not parts:
        return None
    head_text = in_case(next(text for text, role in parts if role == "headline"), look["case"])
    # One line when it can stay big (the pack's head_one_min), else two balanced lines, as the pack route does.
    head_px, head_lines = fit(head_text, look["head_file"], look["head_px"], safe_zones.MIN_PX["headline"],
                              max_rows=1, room=HEADLINE_ROOM)
    if head_px < look["one_line_min"]:
        head_px, head_lines = fit(head_text, look["head_file"], look["head_px"], safe_zones.MIN_PX["headline"],
                                  room=HEADLINE_ROOM)
    runs = []
    for text, role in parts:
        if role == "headline":
            runs.append([head_lines, look["head_file"], head_px, look["hook_color"], 0])
        else:
            # the look's ratio, but never so small it reads as a footnote (the pack route's 40px comfort line)
            # and never as loud as the headline
            want = max(QUIET_COMFORT, safe_zones.MIN_PX["subhead"], round(head_px * look["quiet_ratio"]))
            want = min(want, round(head_px * 0.7)) if head_px * 0.7 >= safe_zones.MIN_PX["subhead"] else want
            size, lines = fit(in_case(text, look["case"]), look["quiet_file"], want, safe_zones.MIN_PX["subhead"])
            runs.append([lines, look["quiet_file"], size, look["quiet_color"], 0])
    for run in runs[:-1]:
        run[4] = round(run[2] * 0.3)       # air between the two lines of the block
    art = set_type([tuple(r) for r in runs], look["shadow"])
    if art is None:
        return None
    img, x, y = place(art, MID_X, HOOK_TOP)
    assert HOOK_TOP >= SAFE_TOP, "the hook runs into the top safe band"
    rows = sum(len(r[0]) for r in runs) - (len(runs) - 1)     # the quiet line's own row is part of the shape
    return img, x, y, HOOK_TOP, HOOK_TOP + art[2] - art[1], rows


def caption_line(zones_path):
    """Where the captions start -> (ink top or None, plain words). Just under her chin when this job's
    subject-zones.json measured an open zone below her (her taught caption.zone can prefer another; then
    the look's own height); None means centre on the look's own height."""
    try:
        zones = json.load(open(zones_path, encoding="utf-8"))
    except (OSError, ValueError):
        return None, "at the look's own height (no subject-zones.json for this job)"
    want = _learned("caption.zone", "below")
    below = (zones.get("zones") or {}).get("below") or {}
    if want != "below":
        return None, f"at the look's own height (caption zone '{want}' is set)"
    if not below.get("usable"):
        return None, "at the look's own height (no open room below her in this framing)"
    return int(below["top"]), f"just under her chin (the open zone below her starts at y{int(below['top'])})"


def render_caption(text, look, chin_top):
    """One phrase as a layer -> (image, x, y): the look's caption face at its size, wrapped to two balanced
    lines only when one is too wide, with its shadow. Under her chin when measured, else centred on the
    look's own height, and always inside the safe bands."""
    width, lines = balanced(text, look["cap_file"], look["cap_px"], 1)
    if width > TYPE_WIDTH:
        lines = balanced(text, look["cap_file"], look["cap_px"], 2)[1]
    art = set_type([(lines, look["cap_file"], look["cap_px"], look["cap_color"], 0)], look["shadow"])
    if art is None:
        return None
    ink_h = art[2] - art[1]
    top = chin_top if chin_top is not None else look["cap_y"] - ink_h / 2
    top = min(max(top, SAFE_TOP), SAFE_BOT - ink_h)
    return place(art, MID_X, top)


def hook_notes(job_dir, top, bottom, rows):
    """Things worth raising with her about the hook -> a list of plain lines (printed, never a failure).
    The hook NEVER moves or shrinks on its own: same size, same place, every reel, unless she asks for
    something different (locked, owner decision). So nothing here changes the render. Two things get raised:
      * she is framed high: the hook overlaps her head, per THIS job's own subject-zones.json (never a parent
        folder's, which is framed differently). Hers to decide: keep it, or place it somewhere else.
      * the hook runs long: more than two lines. Hers to decide: rewrite it shorter, or a smaller size."""
    notes = []
    path = os.path.join(job_dir, "subject-zones.json")
    if os.path.exists(path):
        try:
            zones = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            zones = {}
        head = (zones.get("subject") or {}).get("head_top")
        if isinstance(head, (int, float)) and bottom > head:
            notes.append(f"you sit high in the frame here: the hook (y{top} to y{bottom}) overlaps your head, "
                         f"which starts at y{int(head)}. It is placed as always. Want to consider a different "
                         f"spot for the hook on this one?")
    if rows > 2:
        notes.append(f"this hook runs {rows} lines. It is placed as always, at full size. Want to rewrite it "
                     f"shorter, or use a smaller size?")
    return notes


# ---- LAYERS ----------------------------------------------------------------------------------------
# The reel is built the way reel_render.py composite stacks a rendered reel: the cut at the bottom, then one
# transparent layer per job (the hook block, the captions) on top, each the full 1080x1920 canvas. Here a
# layer is a run of still frames instead of a rendered video: one full-frame still for each stretch it shows
# something, and an empty one for each stretch it does not, played by ffmpeg's concat demuxer as one input
# with every still held for exactly its stretch. Two inputs over the cut, however many phrases the reel has.
class Layer:
    """One job's type over the reel: [(start, end, full-frame RGBA still)] in time order, not overlapping."""

    def __init__(self, name):
        self.name, self.spans = name, []

    def show(self, start, end, still):
        if end > start:
            self.spans.append((float(start), float(end), still))

    def write(self, folder):
        """The stills as numbered PNGs plus the concat list that plays them -> the list's path, or None when
        the layer shows nothing. The list names files relative to itself, so no path is ever quoted into it."""
        if not self.spans:
            return None
        os.makedirs(folder, exist_ok=True)
        empty = os.path.join(folder, "empty.png")
        blank().save(empty, compress_level=1)
        lines, clock = ["ffconcat version 1.0"], 0.0
        for n, (start, end, still) in enumerate(self.spans, start=1):
            if start > clock:                       # nothing of this layer on screen until its next stretch
                lines += ["file empty.png", f"duration {start - clock:.6f}"]
            name = f"{n:04d}.png"
            still.save(os.path.join(folder, name), compress_level=1)
            lines += [f"file {name}", f"duration {end - start:.6f}"]
            clock = end
        # It closes on an empty frame, so the last stretch ends at its own time and not when the list runs out.
        lines += ["file empty.png", "duration 0.033333"]
        listing = os.path.join(folder, "layer.ffconcat")
        with open(listing, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return listing


def on_canvas(img, x, y):
    """A placed image (set_type + place) as a full-frame still: the layer's frames all share the canvas size."""
    frame = blank()
    frame.alpha_composite(img, (int(x), int(y)))
    return frame


def layer_folder(job):
    """This job's layers (and the default preview) live in the engine's scratch folder under the system temp
    folder, rebuilt on every run. Never a literal /tmp: on native Windows Git Bash cannot see it."""
    return os.path.join(tempfile.gettempdir(), "reels-editing-engine", job, "clean-captions")


def cut_facts(path):
    """(seconds, codec of its first sound stream or None) of the cut, in one ffprobe call."""
    got = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name",
                          "-of", "json", path], capture_output=True, text=True, check=True)
    info = json.loads(got.stdout or "{}")
    sound = next((st.get("codec_name") for st in info.get("streams", []) if st.get("codec_type") == "audio"), None)
    return float((info.get("format") or {}).get("duration") or 0), sound


def stack(cut, layers, out_path, seconds=None, sound=None):
    """The ffmpeg command that lays each layer over the cut, in order. The layers are drawn on the 1080x1920
    canvas, so a cut of any other size is brought to it first (cover, then centre crop, as composite does);
    a 4K phone cut would otherwise take every still at its 1080-frame position, small and off to the left.
    The cut's sound is kept as it is when it is already AAC (the rough cut's level chain made it, and nothing
    here touches it); anything else becomes AAC, the one sound codec an .mp4 for Instagram carries."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", cut]
    for listing in layers:
        cmd += ["-f", "concat", "-i", listing]
    graph = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[l0]"]
    for n in range(1, len(layers) + 1):
        graph.append(f"[l{n - 1}][{n}:v]overlay=0:0:format=auto:eof_action=pass[l{n}]")
    cmd += ["-filter_complex", ";".join(graph), "-map", f"[l{len(layers)}]", "-map", "0:a:0?"]
    if seconds is not None:
        cmd += ["-t", f"{seconds:.3f}"]
    cmd += pick_encoder()
    cmd += ["-c:a", "copy"] if sound == "aac" else ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]
    return cmd + ["-movflags", "+faststart", out_path]


def build(job_dir, out_path, hook_copy="", hook_end=None, preview=None, pack=None, emphasis="second"):
    """Clean Captions on one job's cut -> the finished reel at out_path. `preview` keeps only the first that
    many seconds."""
    job_dir = os.path.abspath(job_dir)
    job = os.path.basename(job_dir)
    cut = os.path.join(job_dir, "outputs", f"{job}.mp4")
    transcript = os.path.join(job_dir, "outputs", f"{job}.transcript.json")
    for need, what in ((cut, "the rough cut"), (transcript, "the rough cut's transcript")):
        if not os.path.exists(need):
            sys.exit(f"[clean-captions] {what} is not there yet ({need}). Run the rough cut on this job first.")
    seconds, sound = cut_facts(cut)

    fixes = load_word_fixes(str(ENGINE))
    words = json.load(open(transcript, encoding="utf-8"))["words"]
    for word in words:
        word["disp"] = shown_as(word["text"], fixes)

    look = resolve_look(pack)
    print(f"[clean-captions] look: {look['why']}")
    chin_top, where = caption_line(os.path.join(job_dir, "subject-zones.json"))
    print(f"[clean-captions] captions: {where}")

    work = layer_folder(job)
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)   # only this run's layers, ever
    os.makedirs(work, exist_ok=True)
    stop = min(preview, seconds) if preview else None

    hook_layer = Layer("hook")
    if hook_copy and hook_copy.strip():           # no copy, no hook: the captions carry on by themselves
        drawn = render_hook(hook_copy, look, emphasis)
        if drawn:
            img, x, y, top, bottom, rows = drawn
            leaves, why = hook_exit(words, hook_end)
            for note in hook_notes(job_dir, top, bottom, rows):
                print(f"[clean-captions] for you to decide: {note}")
            hook_layer.show(0.0, leaves if stop is None else min(leaves, stop), on_canvas(img, x, y))
            print(f"[clean-captions] hook: on screen until {leaves:.2f} s ({why})")

    caption_layer = Layer("captions")
    lines = phrases(words, look["cap_case"],
                    fits=lambda text: measure(text, look["cap_file"], look["cap_px"]) <= TYPE_WIDTH)
    sheet = []
    for line in lines:
        if stop is not None and line["start"] >= stop:
            break
        drawn = render_caption(line["text"], look, chin_top)
        if drawn:
            end = line["end"] if stop is None else min(line["end"], stop)
            caption_layer.show(line["start"], end, on_canvas(*drawn))
            sheet.append({"start": round(line["start"], 3), "end": round(end, 3), "text": line["text"],
                          "words": sum(1 for t in line["said"] if stop is None or t < stop)})
    spoken = sum(1 for w in words if _bare(w["text"]) and (stop is None or float(w["start"]) < stop))
    shown = sum(line["words"] for line in sheet)
    print(f"[clean-captions] captions: {len(sheet)} phrases carrying {shown} of her {spoken} words"
          + ("" if stop is None else f" in the first {stop:g} s"))
    with open(os.path.join(work, "captions.json"), "w", encoding="utf-8") as fh:
        json.dump({"cut": cut, "phrases": sheet}, fh, indent=1, ensure_ascii=False)

    layers = [p for p in (hook_layer.write(os.path.join(work, "hook")),
                          caption_layer.write(os.path.join(work, "captions"))) if p]
    if not layers:
        print("[clean-captions] nothing to lay over this cut: it is copied as it is")
    subprocess.run(stack(cut, layers, out_path, stop, sound), check=True)
    print(f"[clean-captions] wrote {out_path} (each phrase and its time: {os.path.join(work, 'captions.json')})")


def main():
    ap = argparse.ArgumentParser(description="Burn Clean Captions (and a hook block) into a job's rough cut.")
    ap.add_argument("job_dir", help="the job folder, holding outputs/<job>.mp4 and its transcript")
    ap.add_argument("--hook", "--hook-text", dest="hook", default=HOOK_COPY or DEFAULT_HOOK_TEXT,
                    help="the hook copy; one line = a hook card, two lines = eyebrow + headline")
    ap.add_argument("--hook-emphasis", choices=("second", "first"), default="second",
                    help="which line of a two-line hook is the big one (second = eyebrow + headline, "
                         "first = headline + subhead)")
    ap.add_argument("--hook-end", type=float, help="seconds into the reel the hook leaves (default: about 8)")
    ap.add_argument("--pack", help="the style pack to draw in (default: STYLE_PACK, else her saved default); "
                                   "'starter' for the starter look")
    ap.add_argument("-o", "--out", help="where the reel goes (default: preview.mp4 in the layer folder)")
    ap.add_argument("--preview", "--until", dest="preview", type=float, metavar="SECONDS",
                    help="build only the first SECONDS of the reel, to check the hook and captions quickly")
    args = ap.parse_args()
    job = os.path.basename(os.path.abspath(args.job_dir))
    out = args.out or os.path.join(layer_folder(job), "preview.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    build(args.job_dir, out, args.hook, args.hook_end, args.preview, args.pack, args.hook_emphasis)


if __name__ == "__main__":
    main()
