#!/usr/bin/env python3
"""lookbook.py — the looks every style pack already has, drawn on any one line, by the engine's own builder.

Nothing here designs a look. The looks are the ones product/build-reel-type.py already makes in every pack
(hook, eyebrow + headline, headline + subhead, full-screen takeover, karaoke, single word, count-up card,
graphics breakaway); the pack is their skin. To draw a look on one line, this hands the builder a tiny job:
that line's words (timed from 0) and a caption plan asking for that look, then keeps the ONE layer it draws
(LAYER=hook / takeover / captions / breakaway / elements). So a look on the page, in the lookbook and in the
render is the same graphic, made the same way.

    python3 product/lookbook.py list
    python3 product/lookbook.py draw <look> <out_dir> --text "your words" --dur 3.2 [--pack Butter] [--job <job>]

The look's page (index.html + fonts) lands in <out_dir>/hf-reel-type-<pack>/, timed to the line, so the visual
editor plays it live. Her own saved looks live in _local/lookbooks/<pack>.json and survive every update: each is
one of these looks with her settings on top ({"id","name","base","plan": {...}}).

HER OWN DESIGNS (a new look, not one of the ten). A design is a composition template she workshopped with Claude,
saved per pack in _local/lookbooks/<pack>/designs/<id>/ (design.json + index.html + any assets she gave). It
wears the pack the same way the builder's looks do: every color, font, letter case and shadow comes from the pack
at draw time through the pk- variables below, never from the template. Her words go in its slots. The starter
(product/lookbook-designs/starter/) shows the contract; check_design() enforces it before anything is saved.

  slots        __TEXT__ (all the line's words) · __LINE1__ / __LINE2__ (small line, big words) ·
               __NUMBER__ / __LABEL__ (a count-up: the number in her words, and the rest) · __NUMBER_VALUE__ (JS) ·
               __EMOJI__ (an emoji pop: picked from the moment's words, emoji_for) ·
               __NOTE__ (words she wrote for the card that she doesn't say, e.g. an aside on a note card: kept in
               design.json "note", the same on every line it lands on. A note that WAS her spoken line, saved from
               the reel she made it on, is marked "note_follows_line": on every new reel it takes that reel's line,
               like any caption style, "first part / second part" split at the line's first pause mark)
               A design with the note AND a slot for her words (a checklist: a heading over her list) is given
               "heading / her words" for this reel's own heading (has_heading); without one it keeps the saved note
               __SAID__ (JS array: when she says each word, from the look's start; a design that follows her line
               has any hard-coded SAID array swapped for this reel's timings too)
  timing       __COMP__ (composition id) · __DUR__ (seconds on screen)
  fitted size  __PX_TEXT__ / __PX_LINE1__ / ... from design.json "fit": {slot: {role, box_w, max_px, max_lines}}
  pack skin    var(--pk-light|dark|muted|accent|pop2|hook|subhead) · var(--pk-shadow) ·
               font-family: PkHeadline | PkTakeover | PkCaption | PkAccent | PkLabel | PkDetail | PkThought (label,
               detail and thought wear the caption face when the pack has none; PkThought is the pack's thought-bubble
               hand, for an aside) · var(--pk-case-headline|takeover|caption|accent|label)
               for text-transform · var(--pk-track-headline|takeover|label) for letter-spacing
  pack shape   var(--pk-radius-card|label|frame) · var(--pk-pad-card) · var(--pk-shadow-card) · var(--pk-rule) ·
               var(--pk-ease) (CSS transitions; a GSAP tween uses window.pkEase) · var(--pk-extra-<name>) (her
               extra colors, only when the pack has them: give each a fallback). Always set, product/pack_shape.py.

    python3 product/lookbook.py check-design <dir> --pack Butter
    python3 product/lookbook.py save-design <dir> --pack Butter --name "Sticky note"
"""
import html, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILDER = os.path.join(HERE, "build-reel-type.py")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import frame  # noqa: E402
import graphics_python  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


class Refuse(Exception):
    """A plain-words reason a look can't be drawn here."""


# The looks the builder already makes, the layer it draws each on, and what each is for (one short line).
LOOKS = [
    {"id": "hook", "name": "Hook", "layer": "hook", "kind": "Hook", "about": "One line, top of frame."},
    {"id": "eyebrow-headline", "name": "Eyebrow + headline", "layer": "hook", "kind": "Hook", "about": "Small line, then big words."},
    {"id": "headline-subhead", "name": "Headline + subhead", "layer": "hook", "kind": "Hook", "about": "Big words, then a small line."},
    {"id": "takeover", "name": "Takeover", "layer": "takeover", "kind": "Full screen", "about": "Words stacked big, full screen."},
    {"id": "breakaway", "name": "Breakaway card", "layer": "breakaway", "kind": "Full screen", "about": "Cuts to a designed card."},
    {"id": "counter", "name": "Count-up card", "layer": "elements", "kind": "Card", "about": "Your number counts up.", "needs": "number"},
    {"id": "karaoke", "name": "Karaoke", "layer": "captions", "kind": "Captions", "about": "Builds on as you speak."},
    {"id": "single-word", "name": "Single word", "layer": "captions", "kind": "Captions", "about": "One word at a time. Tap a word to highlight it."},
    {"id": "phrase", "name": "Phrase", "layer": "captions", "kind": "Captions", "about": "A few words at a time. Tap a word to highlight it."},
    {"id": "spotlight", "name": "Spotlight", "layer": "captions", "kind": "Captions", "about": "The phrase shows; your word lights up."},
]
CAPTION_LOOKS = ("karaoke", "single-word", "phrase", "spotlight", "takeover")   # what a line's captions can be
# What a look she saved keeps from her lookbook entry: what she set on it, and the settings the engine reads off a look
# (`keeps_captions`: her captions stay on under it, visual_editor._keeps_captions). Everything else comes from the
# look it's built on, so a saved entry can never change which layer it draws on. `tags` are hers (the words she
# labels it with): they stay on the look find() hands back, where they used to be dropped (a buyer, 2026-10-25).
SAVED_KEYS = ("id", "name", "about", "base", "plan", "size", "effect", "tags", "keeps_captions")


def looks(pack=None, job=None, hidden=False):
    """Every look she can pick in this pack. A sandbox take (not committed yet) never shows, and a look she kept for
    one reel shows only on that reel (`job`); `hidden=True` returns them all (drawing a look by its id)."""
    out = [dict(l, **{"from": "pack"}) for l in LOOKS]
    if pack:
        try:
            mine = json.load(open(os.path.join(ROOT, "_local", "lookbooks", f"{pack}.json"), encoding="utf-8"))
            ids = {l["id"] for l in out}
            for l in mine.get("looks", []):
                if not hidden and (l.get("sample") or (l.get("only_reel") and l.get("only_reel") != job)):
                    continue
                if l.get("design") and l.get("id") not in ids and os.path.isfile(os.path.join(design_dir(pack, l["id"]), "index.html")):
                    out.append({"id": l["id"], "name": l["name"], "about": l.get("about") or "Your own design.",
                                "kind": l.get("kind") or "Card", "layer": "design", "design": True, "from": "design",
                                **{k: l[k] for k in ("tags", "keeps_captions") if k in l}})
                    continue
                base = next((b for b in out if b["id"] == l.get("base")), None)
                if base and l.get("id") not in ids:
                    keep = {k: v for k, v in l.items() if k in SAVED_KEYS}
                    out.append(dict(base, **keep, **{"from": "saved"}))
        except Exception:
            pass
    return out


def find(look_id, pack=None):
    for l in looks(pack, hidden=True):
        if l["id"] == look_id:
            return l
    for home in design_homes(look_id, pack):                 # one of her designs, saved in another pack: it wears this one
        if home == pack:
            continue
        for l in looks(home, hidden=True):
            if l["id"] == look_id:
                return dict(l, home=home)
    raise Refuse(f"There's no look called {look_id!r} in this lookbook.")


def design_homes(look_id, pack=None):
    """Every pack whose lookbook keeps a copy of this design of hers, the one to draw from first (designs wear any
    pack; they're saved in the one she made them in). The same id can sit in more than one pack's lookbook (a
    buyer, 2026-10-26: one saved under a shipped pack and under her own copy of it, while her reel was on a third
    pack): the reel's own pack comes first, then a copy its lookbook really lists, then the copy she changed
    last, the one her edits land in. Never the order the folders happen to sort in. [] when it isn't hers."""
    base = os.path.join(ROOT, "_local", "lookbooks")
    try:
        packs = [d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, "designs", look_id, "index.html"))]
    except OSError:
        return []

    def listed(pk):
        try:
            return any(l.get("id") == look_id and l.get("design") for l in _read_book(pk).get("looks", []))
        except Exception:
            return False

    def changed(pk):
        src = design_dir(pk, look_id)
        return max((os.path.getmtime(os.path.join(src, f)) for f in ("index.html", "design.json")
                    if os.path.isfile(os.path.join(src, f))), default=0.0)

    return sorted(packs, key=lambda pk: (pk != pack, not listed(pk), -changed(pk), pk))


def design_home(look_id, pack=None):
    """The pack whose lookbook keeps this design of hers, for a reel on `pack` (design_homes). None when it isn't
    one of her designs."""
    homes = design_homes(look_id, pack)
    return homes[0] if homes else None


# A number in her words: a currency sign in front ("$1,250"), or the euro after it the way French writes it ("300 €",
# "300€", "300 euros"; a buyer, 2026-10-25: her count-up lost its euro), then %, k or x.
_NUM = re.compile(r"([$£€])?\s?(\d[\d,]*(?:\.\d+)?)\s?(%|k|K|x|€|[Ee]uros?\b)?")
EURO_AFTER = "\u00a0€"          # how the euro is set after a number: a non-breaking space, then €, so it never wraps alone


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                     "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALE = {"hundred": 100, "thousand": 1_000, "grand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_SPOKEN = re.compile(r"\b(half an? |a half |an? |(?:\d+(?:\.\d+)?|(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
                     r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|zero|one|two|three|four|five|six|seven|eight|"
                     r"nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen))(?: and a half)? )"
                     r"(hundred|thousand|grand|million|billion)(?: (?:dollars|bucks))?\b", re.I)


def spoken_number(text):
    """A number she SAID in words, for a count-up: 'half a million dollars' → ('$', 500000, '', span). None when
    there isn't one. Only a number with a scale word (hundred, thousand, million ...), so 'one thing' never counts."""
    m = _SPOKEN.search(text)
    if not m:
        return None
    lead, scale = m.group(1).strip().lower(), _SCALE[m.group(2).lower()]
    half = lead.endswith("and a half")
    lead = lead.replace(" and a half", "").strip()
    if lead in ("half a", "half an", "a half"):
        n = 0.5
    elif lead in ("a", "an"):
        n = 1
    elif re.fullmatch(r"\d+(?:\.\d+)?", lead):
        n = float(lead)
    else:
        parts = re.split(r"[- ]", lead)
        n = sum(_TENS.get(x, 0) + _ONES.get(x, 0) for x in parts)
    val = (n + (0.5 if half else 0)) * scale
    money = bool(re.search(r"dollars|bucks|grand", m.group(0), re.I))
    val = int(val) if float(val).is_integer() else val
    return ("$" if money else "", val, "", m.span())


def number_in(text):
    """The number a count-up card would count to, from her words: '$1,250' → ('$', 1250, ''); said in words,
    'half a million dollars' → ('$', 500000, '')."""
    sp = spoken_number(text)
    m = _NUM.search(text.replace("*", ""))
    if sp and (not m or sp[3][0] <= m.start()):
        return sp[:3]
    if not m:
        return None
    val = float(m.group(2).replace(",", ""))
    suf = (m.group(3) or "").lower()
    if suf in ("€", "euro", "euros"):
        suf = "" if m.group(1) else EURO_AFTER             # "€300 €" says it once
    return (m.group(1) or "", int(val) if val.is_integer() else val, suf)


def _split(text, first_max=None):
    """Two parts for the two-part hooks: her own ' / ' when she wrote one, else at a comma, else about 40% in.
    first_max caps the first part (an eyebrow is a short lead-in: a long one wraps to two lines by the builder's rule)."""
    if "/" in text:
        a, b = [x.strip() for x in text.split(" / " if " / " in text else "/", 1)]   # her " / " first: "Day 5/30 / ..." keeps its slash
        if a and b:
            return [a, b]
    words = text.split()
    cap = first_max or len(words)
    for k, w in enumerate(words[:-1]):
        if 1 <= k < cap and w.endswith((",", ";", ":")):
            return [" ".join(words[:k + 1]).rstrip(",;:"), " ".join(words[k + 1:])]
    k = max(1, min(len(words) - 1, cap, round(len(words) * 0.4)))
    small = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "but", "with", "my", "your", "at", "by", "from", "as"}
    while k > 1 and words[k - 1].lower().strip(",.") in small:   # never end the first part on a little word ("unlock a")
        k -= 1
    return [" ".join(words[:k]), " ".join(words[k:])]


def plan_for(look, text, dur, words):
    """The caption plan that asks the builder for exactly this look on this line (her saved settings on top)."""
    lid = look.get("base") or look["id"]
    clean = re.sub(r"\s+", " ", text.replace("/", " ").replace("*", "")).strip()
    p = {"duration": round(dur, 3), "hook_end": round(dur, 3), "caption_mode": "single"}
    if lid == "hook":
        p["hook"] = [clean]
    elif lid in ("eyebrow-headline", "headline-subhead"):    # the builder's split hook (HOOK_SPLIT): two halves
        p["hook"] = [clean]; p["hook_long"] = clean
        p["hook_halves"] = _split(text.replace("*", ""), 4 if lid == "eyebrow-headline" else 5)
        p["hook_emphasis"] = "second" if lid == "eyebrow-headline" else "first"
    elif lid == "takeover":
        last = max((w["e"] for w in words), default=dur - 0.6)
        p.update(takeover_keys=[clean], takeover_exact=True, takeover_hold=round(max(0.3, dur - last - 0.1), 3))
    elif lid == "breakaway":
        a, b = _split(clean) if len(clean.split()) > 3 else ("", clean)
        p["breakaways"] = [{"at": 0.05, "out": round(dur, 3), "lines": [x for x in (a, b) if x]}]
    elif lid == "counter":
        n = number_in(text)
        if not n:
            raise Refuse("This line has no number to count up to.")
        pre, val, suf = n
        p["elements"] = [{"kind": "counter", "at": 0.1, "duration": round(dur - 0.2, 3), "x": 0.5, "y": 0.25, "w": 0.7,
                          "from": 0, "to": val, "prefix": pre, "suffix": suf, "count_duration": round(min(1.4, dur * 0.5), 2)}]
    elif lid == "karaoke":
        p["caption_mode"] = "build"
    elif lid in ("phrase", "spotlight"):
        p["caption_mode"] = lid
    p.update(look.get("plan") or {})
    return p


def _words(text, dur, words):
    """[{w, t, e}] for the line, from 0: her real timings when the look shows the words she says, else the look's own
    words spread across the line (on-screen copy that isn't her spoken line, a refined edit, a placeholder)."""
    norm = lambda x: re.sub(r"[^a-z0-9']+", " ", x.lower()).split()
    # "*" goes from BOTH sides: the look's text drops it, so a word the transcriber censored ("f***") must drop it
    # too, or "f***" reads as two words, nothing matches and every word on the line falls to even spacing
    if words and norm(" ".join(w["w"].replace("*", "") for w in words)) != norm(text.replace("/", " ").replace("*", "")):
        t0 = float(words[0]["t"]); t1 = float(words[-1].get("e") or words[-1]["t"] + 0.35)
        toks = re.sub(r"\s+", " ", text.replace("/", " ").replace("*", "")).split()
        step = max(0.12, (t1 - t0) / max(1, len(toks)))
        return [{"w": w, "t": round(t0 + k * step, 3), "e": round(t0 + (k + 0.85) * step, 3)} for k, w in enumerate(toks)]
    if words:
        out = []
        for k, w in enumerate(words):
            e = w.get("e") or (words[k + 1]["t"] - 0.03 if k + 1 < len(words) else w["t"] + 0.35)
            out.append({"w": w["w"], "t": max(0.0, float(w["t"])), "e": max(float(w["t"]) + 0.05, float(e))})
        return out
    toks = re.sub(r"\s+", " ", text.replace("/", " ").replace("*", "")).split()
    step = max(0.18, min(0.4, (dur - 0.6) / max(1, len(toks))))
    return [{"w": w, "t": round(0.1 + k * step, 3), "e": round(0.1 + k * step + step * 0.85, 3)} for k, w in enumerate(toks)]


def shown_text(look, text):
    """The words a look shows. A card is a title, not a sentence: it never ends on a comma, a semicolon or a colon
    ("I want to see a hook above my head," reads as a hook without the comma). Captions keep her punctuation."""
    if look.get("layer") == "captions":
        return text
    return re.sub(r"[,;:]+\s*$", "", str(text).strip())


# Captions shown exactly on a word's start stamp read as lagging (the eye wants the word as the sound starts, and
# the stamp sits a touch after the onset). Every caption style leads her voice by this much (2026-10-17).
CAPTION_LEAD_S = 0.08


def drawn_words(look, text, dur, words):
    """The words a look is drawn with, timed as the page plays them ([{w, t, e}]): what draw() hands the builder and
    records on the page, so a caller can tell a line whose timing moved from one that only looks the same."""
    text = shown_text(look, text)
    ws = _words(text, dur, words)
    if look["layer"] != "captions" and ws:
        ws[-1] = dict(ws[-1], w=ws[-1]["w"].rstrip(",;:"))
    if look["layer"] == "captions" and ws and CAPTION_LEAD_S:  # a caption lands a hair BEFORE her word, so it reads in
        ws = [dict(w, t=max(0.0, float(w["t"]) - CAPTION_LEAD_S), e=max(0.0, float(w["e"]) - CAPTION_LEAD_S)) for w in ws]   # time
    return ws


def draw(look_id, out_dir, text, dur, pack, zones=None, words=None, comp_id=None, size=None, effect=None, accents=None, track=None, font_overrides=None):
    """Draw the look on one line with the engine's builder. out_dir becomes a tiny job folder; the look's page is
    out_dir/hf-reel-type-<pack>/. Returns {"dir": that folder, "id": its composition id, "dur": dur}.
    font_overrides {role: her font file} wears her chosen font over the pack default for this look (designs only)."""
    look = find(look_id, pack)
    dur = max(0.8, float(dur))
    cid = comp_id or re.sub(r"[^a-z0-9-]", "-", os.path.basename(out_dir.rstrip("/")).lower()) or "look"
    if look.get("design"):
        return draw_design(design_dir(look.get("home") or pack, look_id), out_dir, text, dur, pack, cid, look_id=look_id, words=words,
                           home=look.get("home"), font_overrides=font_overrides)
    text = shown_text(look, text)
    ws = drawn_words(look, text, dur, words)
    plan = plan_for(look, text, dur, ws)
    effect = effect or look.get("effect")                   # her refine: the builder's own named text animations
    if effect:
        role = {"hook": "hook", "takeover": "takeover", "captions": "caption"}.get(look["layer"])
        if role:
            plan.setdefault("effects", {})[role] = effect
    if track and look["layer"] == "captions":                # centered captions: one locked spot per scene (caption_scenes.py)
        plan["caption_track"] = [list(x) for x in track]
    if not size and look["layer"] == "captions":             # the reel's own caption size (review/caption-box.json "size"),
        _parts = os.path.abspath(out_dir).split(os.sep)      # so every redraw keeps it: a cut change redraws her captions
        if "hf-graphics" in _parts:                          # plain, and her smaller size was lost each time (2026-10-23)
            try:
                size = float(json.load(open(os.path.join(os.sep.join(_parts[:_parts.index("hf-graphics")]) or os.sep,
                                                         "review", "caption-box.json"), encoding="utf-8")).get("size") or 0) or None
            except Exception:
                size = None
    size = float(size or look.get("size") or 1.0)
    if accents and look["layer"] == "captions":             # her accent words, in this caption style's own way:
        plan["accent_words"] = [{"w": a["w"], "t": max(0.0, float(a["t"]) - CAPTION_LEAD_S)} for a in accents]   # same lead as its words          # that very word (Single word, Phrase)
    elif accents and look["layer"] == "takeover":           # a takeover wears her highlight on the word she highlighted
        plan["keywords"] = [a["w"] for a in accents]         # in her highlight style, the captions' own (.capword.hl):
        plan["takeover_highlight"] = True                    # the pack's keyword face, in the pack accent
        plan["keyword_at"] = [{"w": a["w"], "t": a["t"]} for a in accents]   # each at its moment: "build the room" lights
    name = os.path.basename(out_dir.rstrip("/"))
    os.makedirs(os.path.join(out_dir, "outputs"), exist_ok=True)
    json.dump({"text": " ".join(w["w"] for w in ws), "words": [{"text": w["w"], "start": w["t"], "end": w["e"], "type": "word"} for w in ws]},
              open(os.path.join(out_dir, "outputs", f"{name}.transcript.json"), "w", encoding="utf-8"))
    json.dump(plan, open(os.path.join(out_dir, "caption-plan.json"), "w", encoding="utf-8"), indent=1)
    zp = os.path.join(out_dir, "subject-zones.json")
    if zones:
        json.dump(zones, open(zp, "w", encoding="utf-8"))
    elif os.path.exists(zp):
        os.remove(zp)
    page_dir = os.path.join(out_dir, f"hf-reel-type-{pack.lower()}")
    # Drawn OFF to the side and swapped in whole at the end: the page on her preview is never missing while it's
    # redrawn (it was deleted first, so anything loading it mid-draw got "not found"), and a draw that fails leaves
    # the look she had in place. The builder sees a copy of this tiny job folder under the same name.
    stage = tempfile.mkdtemp(prefix="look-draw-")
    try:
        work = os.path.join(stage, name)
        shutil.copytree(out_dir, work, ignore=shutil.ignore_patterns("hf-reel-type-*", ".swap-*", ".old-*"))
        env = dict(os.environ, **frame.env(out_dir), JOB_DIR=work, STYLE_PACK=pack, LAYER=look["layer"], COMP=cid,
                   # captions may go smaller (more words per line, 2026-10-23); the builder's MIN_PX floor still holds
                   SIZE_SCALE=f"{6.0 * max(0.45 if look['layer'] == 'captions' else 0.6, min(1.6, size)):.3f}",
                   HOOK_SPLIT="1" if (look.get("base") or look["id"]) in ("eyebrow-headline", "headline-subhead") else "0")
        env.pop("DUR_OVERRIDE", None)
        # the reel this look is drawn for (<job>/hf-graphics/...), so the builder reads that reel's own word fixes
        # (a brand spelled with a capital inside keeps it in a lowercase pack); the tiny copy above has none
        parts = os.path.abspath(out_dir).split(os.sep)
        if "hf-graphics" in parts:
            env["REEL_JOB_DIR"] = os.sep.join(parts[:parts.index("hf-graphics")]) or os.sep
        else:
            env.pop("REEL_JOB_DIR", None)
        new_page = os.path.join(work, os.path.basename(page_dir))
        # the builder draws with Pillow: a Python that has it, not whichever one started this (Apple's 3.9 has none)
        r = subprocess.run([graphics_python.python(), BUILDER], env=env, capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not os.path.isfile(os.path.join(new_page, "index.html")):
            why = [l for l in (r.stderr or r.stdout or "").strip().splitlines() if l.strip()]
            if any("No module named 'PIL'" in l for l in why):
                raise Refuse(graphics_python.NO_PIL_MESSAGE)
            raise Refuse(f"The {look['name']} look couldn't be drawn in {pack}: {why[-1].strip() if why else 'the builder stopped'}")
        rec = {"look": look_id, "pack": pack, "text": text, "dur": round(dur, 3), "layer": look["layer"], "size": size, "effect": effect,
               "track": [list(x) for x in track] if track and look["layer"] == "captions" else None,
               "accents": [[a["w"], a["t"]] for a in (accents or [])], "pack_sig": _pack_sig(pack)}
        # the page carries its own record too, so wherever it's copied (a reel's first build) it can be redrawn in another
        # pack with its own words and timing
        json.dump(dict(rec, words=[{"w": w["w"], "t": w["t"], "e": w["e"]} for w in ws]),
                  open(os.path.join(new_page, "look.json"), "w", encoding="utf-8"), indent=1)
        for f in os.listdir(work):                           # what the builder wrote beside the page (owns-screen.json)
            if f != os.path.basename(page_dir) and os.path.isfile(os.path.join(work, f)):
                shutil.copy2(os.path.join(work, f), os.path.join(out_dir, f))
        replace_dir(new_page, page_dir)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    json.dump(rec, open(os.path.join(out_dir, "look.json"), "w", encoding="utf-8"), indent=1)
    return {"dir": page_dir, "id": cid, "dur": dur}


def _swap_dirs(a, b):
    """Exchange two folders in one atomic step where the system can (macOS renamex_np RENAME_SWAP, Linux renameat2
    RENAME_EXCHANGE). False where it can't (Windows, an old system): the caller falls back to two renames, which leave
    a split second with no folder (her page could load "not found" mid-redraw)."""
    try:
        import ctypes, ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
        fa, fb = os.fsencode(a), os.fsencode(b)
        if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
            return libc.renamex_np(fa, fb, 0x2) == 0          # RENAME_SWAP
        if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
            return libc.renameat2(-100, fa, -100, fb, 0x2) == 0   # AT_FDCWD, RENAME_EXCHANGE
    except Exception:
        pass
    return False


def replace_dir(src, dst):
    """dst becomes a copy of src in one step anyone reading dst can't fall into: copied in beside it under a hidden
    name, then two renames. A page her preview has open is never half-written or missing (a look redrawn or picked
    from Swap while her page loads it got "not found")."""
    parent = os.path.dirname(os.path.abspath(dst))
    os.makedirs(parent, exist_ok=True)
    tag = f"{os.getpid()}-{os.urandom(3).hex()}"
    new, old = os.path.join(parent, f".swap-{tag}"), os.path.join(parent, f".old-{tag}")
    shutil.copytree(src, new)
    if os.path.isdir(dst) and _swap_dirs(new, dst):        # one atomic step: dst is never missing, not even for a moment
        shutil.rmtree(new, ignore_errors=True)               # (new now holds the old page)
        return
    try:
        if os.path.exists(dst):
            os.rename(dst, old)
        os.rename(new, dst)
    except OSError:
        if os.path.exists(old) and not os.path.exists(dst):
            os.rename(old, dst)                              # never leave her look missing
        shutil.rmtree(new, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


# The builder animates a hook as whole blocks, so only block animations read differently there; a takeover
# animates each word, so letter and word animations show too. Each offered set is short, distinct, plainly named.
_BLOCK_FX = [("spring-scale-in", "Pop"), ("rise", "Rise"), ("short-slide-right", "Slide in"), ("focus-blur-resolve", "Blur in"),
             ("scale-down-fade", "Zoom out"), ("shimmer-sweep", "Flash"), ("mask-reveal-up", "Reveal up")]
_WORD_FX = [("typewriter", "Typewriter"), ("per-character-rise", "Letters rise"), ("stagger-from-center", "From the center"),
            ("per-word-crossfade", "Word by word"), ("depth-parallax-words", "Words fly in"),
            ("slow-zoom", "Slow zoom"), ("drop-in", "Drop in"), ("punch-in", "Punch in")]


# a line's own caption style can take an entrance too (each word/phrase arrives with it); the reel's default stays snap
_CAPTION_FX = [("drop-in", "Drop in"), ("punch-in", "Punch in"), ("spring-scale-in", "Pop"), ("rise", "Rise"), ("per-word-crossfade", "Word by word")]


def effects_for(look_id, pack=None):
    """The named animations this look can visibly take: [{"id", "name"}] (the builder's own catalog), or []."""
    look = find(look_id, pack)
    import text_effects
    have = set(text_effects.CATALOG)
    pick = (_BLOCK_FX if look["layer"] == "hook" else (_WORD_FX + _BLOCK_FX[:3]) if look["layer"] == "takeover"
            else _CAPTION_FX if look["layer"] == "captions" else [])
    return [{"id": i, "name": n} for i, n in pick if i in have]


# ── her lookbook file: read safely, written under a lock, and a save never replaces a different look ───────
import contextlib, time as _time


def _book_path(pack):
    return os.path.join(ROOT, "_local", "lookbooks", f"{pack}.json")


def _read_book(pack):
    """Her lookbook for this pack. Missing = a fresh, empty one; unreadable = stop, never write an empty one over it."""
    try:
        return json.load(open(_book_path(pack), encoding="utf-8"))
    except FileNotFoundError:
        return {"pack": pack, "looks": []}
    except Exception as e:
        raise Refuse(f"Your {pack} lookbook couldn't be read just now ({type(e).__name__}), so nothing was changed. "
                     "Try again in a moment.")


@contextlib.contextmanager
def _book_lock(pack, wait=30.0):
    """One writer at a time for her lookbook, across the page and the chat (two processes)."""
    d = os.path.join(ROOT, "_local", "lookbooks"); os.makedirs(d, exist_ok=True)
    lock = os.path.join(d, f".{pack}.lock"); t0 = _time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd)
            break
        except FileExistsError:
            try:
                if _time.time() - os.path.getmtime(lock) > 120:      # a writer that died mid-save
                    os.remove(lock); continue
            except OSError:
                continue
            if _time.time() - t0 > wait:
                raise Refuse("Your lookbook is busy saving something else. Try again in a moment.")
            _time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _write_book(pack, book):
    p = _book_path(pack); tmp = p + ".tmp"
    json.dump(book, open(tmp, "w", encoding="utf-8"), indent=1); os.replace(tmp, p)


def _free_id(pack, book, want, may_replace=lambda e: False):
    """`want`, or want-2, want-3… so a save never lands on a different look she already has."""
    taken = {l.get("id"): l for l in book.get("looks", [])}
    n, did = 1, want
    while (did in taken and not may_replace(taken[did])) or (did not in taken and os.path.isdir(design_dir(pack, did))):
        n += 1; did = f"{want}-{n}"
    return did


def book_entry(pack, look_id):
    """Her lookbook's own record of one look (sample / only_reel and all), or None."""
    return next((l for l in _read_book(pack).get("looks", []) if l.get("id") == look_id), None)


def keep_everywhere(pack, look_id):
    """A look she kept for one reel joins her lookbook for every reel (teach my style's "keep this look"). True if it
    changed; False if it was already on every reel or isn't hers."""
    with _book_lock(pack):
        book = _read_book(pack)
        hit = next((l for l in book.get("looks", []) if l.get("id") == look_id and l.get("only_reel")), None)
        if not hit:
            return False
        job = hit.pop("only_reel", None)
        _write_book(pack, book)
    if hit.get("design") and job:                           # its words were the line it was made on: on every reel, the
        try:                                                # new line (that line only, never the whole reel's words)
            reqs = json.load(open(os.path.join(ROOT, "projects", job, "review", "look-requests.json"), encoding="utf-8")).get("requests", [])
            rid = hit.get("sample") or look_id.rsplit("-", 1)[-1]
            said = next((r.get("words") for r in reqs if r.get("id") == rid), None)
            if said:
                follow_line(pack, look_id, said)
        except Exception:
            pass
    return True


def one_off_looks(pack, job):
    """Her looks kept for this one reel only (sandbox sketches she hasn't locked in are left out)."""
    return [l for l in _read_book(pack).get("looks", []) if l.get("only_reel") == job and not l.get("sample")]


def save_look(pack, base_id, name, plan=None, size=None, effect=None):
    """Add a look to her lookbook: one of the pack's looks with her settings on top. Survives every update."""
    base_id = find(base_id, pack).get("base") or base_id
    with _book_lock(pack):
        book = _read_book(pack)
        lid = _free_id(pack, book, "my-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "look"))
        entry = {"id": lid, "name": name, "base": base_id, "about": f"Your {find(base_id)['name'].lower()}.", "plan": plan or {}}
        if size and abs(float(size) - 1.0) > 0.01:
            entry["size"] = round(float(size), 3)
        if effect:
            entry["effect"] = effect
        book["looks"] = [l for l in book["looks"] if l.get("id") != lid] + [entry]
        _write_book(pack, book)
    return lid


# ── her own designs ──────────────────────────────────────────────────────────────────────────────────────────
SLOTS = ("text", "line1", "line2", "number", "label", "emoji", "note")


# An emoji pop picks its emoji from the words at its moment (the strongest match in this list wins), so one look
# placed on many lines gives each line its own. Plain, widely read emoji only; nothing matched = ✨.
EMOJI_FOR = [
    (r"trap|warn|careful|danger|watch out", "⚠️"), (r"secret|whisper|nobody knows", "🤫"), (r"launch|rocket|lift ?off", "🚀"),
    (r"million|money|dollars?|bucks|income|paid|cash|profit|revenue|\$", "💸"), (r"win|wins|won|winning|success", "🏆"),
    (r"cheer|cheerleader|celebrat|hype", "📣"), (r"team|teammates?|together|community", "🤝"), (r"dream|magic|sparkle", "✨"),
    (r"idea|advice|tip|lesson|learn", "💡"), (r"love|heart|grateful|thankful", "❤️"), (r"jealous|envy|compar", "😒"),
    (r"doubt|fear|scared|afraid|anxious|worr", "😬"), (r"truth|honest|real talk", "🫣"), (r"wave|waves|ocean", "🌊"),
    (r"fire|hot|on fire|lit", "🔥"), (r"time|clock|hours?|minutes?|late", "⏰"), (r"kids?|baby|toddler|mom|motherhood", "👶"),
    (r"coffee|morning", "☕"), (r"laugh|funny|silly|lol", "😂"), (r"cry|tears|sad", "🥲"), (r"phone|post|reel|video|film", "📱"),
    (r"pray|god|faith|bless", "🙏"), (r"goal|target|aim", "🎯"), (r"grow|growth|bloom", "🌱"), (r"stop|don'?t|never|no ", "🛑"),
    (r"start|begin|first", "🏁"), (r"brain|think|mind", "🧠"), (r"strong|strength|power", "💪"), (r"eyes|look|see|watch", "👀"),
]


def emoji_for(text):
    """The emoji a pop shows on these words (her words decide; nothing matched = ✨)."""
    typed = re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?", str(text or ""))   # an emoji she typed is the one
    if typed:
        return typed.group(0)
    low = " " + str(text or "").lower() + " "
    return next((emo for pat, emo in EMOJI_FOR if re.search(rf"(?<![a-z])(?:{pat})", low)), "✨")   # the list runs strongest first
KINDS = ("Hook", "Card", "Full screen")
_FONT_ROLES = {"PkHeadline": "headline", "PkTakeover": "takeover", "PkCaption": "caption", "PkAccent": "accent_caption",
               "PkLabel": "label", "PkDetail": "detail", "PkThought": "thought_bubble"}
_FONT_FALLBACK = {"label": "caption", "detail": "caption", "thought_bubble": "caption"}   # a pack without them: its caption face
_CASE_CSS = {"upper": "uppercase", "lower": "lowercase", "title": "capitalize"}


def design_dir(pack, design_id):
    return os.path.join(ROOT, "_local", "lookbooks", pack, "designs", design_id)


def _pack_sig(pack):
    """The pack's fingerprint when this look was drawn (stylepack.signature), kept in its look.json so a later change
    to the pack draws it again (visual_editor._stale_look)."""
    try:
        import stylepack
        return stylepack.signature(pack)
    except Exception:
        return None


def font_file(name, jd=None):
    """An override font FILE from HER OWN fonts (favorites/fonts, assets/fonts, this job's assets/fonts) by name or
    filename, else None. The pack is always the default and the guide; an override only ever points at a real font
    of hers, never an arbitrary or missing one (so "a build with no resolved font fails loud" still holds — an
    unknown name resolves to None and the caller keeps the pack face). You, 2026-11-07: pack is the guide, override allowed."""
    if not str(name or "").strip():
        return None
    if os.path.isfile(str(name)) and os.path.splitext(str(name))[1].lower() in (".ttf", ".otf", ".woff", ".woff2"):
        return str(name)
    want = re.sub(r"[^a-z0-9]", "", str(name).lower())
    if not want:
        return None
    dirs = [os.path.join(ROOT, "favorites", "fonts"), os.path.join(ROOT, "assets", "fonts")]
    if jd:
        dirs.insert(0, os.path.join(jd, "assets", "fonts"))
    for d in dirs:
        try:
            cands = sorted(f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in (".ttf", ".otf", ".woff", ".woff2"))
        except OSError:
            continue
        for f in cands:                                      # exact match wins
            if re.sub(r"[^a-z0-9]", "", os.path.splitext(f)[0].lower()) == want:
                return os.path.join(d, f)
        for f in cands:                                      # then a prefix match (a weight: "Inter" -> Inter-Bold), min 3 chars
            stem = re.sub(r"[^a-z0-9]", "", os.path.splitext(f)[0].lower())
            if len(want) >= 3 and len(stem) >= 3 and (stem.startswith(want) or want.startswith(stem)):
                return os.path.join(d, f)
    return None


def _skin(pack, page_dir, font_overrides=None):
    """The pack, as what a design may use: its fonts copied beside the page, its colors, case, tracking, shadow.
    font_overrides {role: font file} swaps the FILE behind a pack role (PkHeadline...) for this one look, so the
    template still only names pack roles (stays check-clean) while the reel wears her chosen font. The pack face is
    the default for every role she doesn't override."""
    import stylepack, pack_palettes
    os.makedirs(os.path.join(page_dir, "fonts"), exist_ok=True)
    ov = {str(k).lower().removeprefix("pk"): v for k, v in (font_overrides or {}).items() if v}
    faces = []
    have = (stylepack.load(pack).get("elements") or {})
    for fam, kind in _FONT_ROLES.items():
        role = fam[2:].lower()
        over = ov.get(role)
        if over and os.path.isfile(over):                    # her override font for this role, this look
            f = over
        else:
            try:
                f = stylepack.element(pack, kind if kind in have else _FONT_FALLBACK.get(kind, kind))["file"]
            except Exception:
                continue
        if f and os.path.isfile(f):
            name = fam + os.path.splitext(f)[1].lower()
            shutil.copyfile(f, os.path.join(page_dir, "fonts", name))
            faces.append(f'@font-face{{font-family:{fam};src:url("fonts/{name}");font-display:block;}}')
    p = stylepack.load(pack)
    wd = p.get("welldone") or {}
    pal = dict(pack_palettes.PALETTE.get(pack) or {})
    pal.setdefault("accent", p.get("accent_color") or "#ffffff")
    pal.update(hook=wd.get("hook_color") or "#ffffff", subhead=wd.get("subhead_color") or "#ffffff")
    # a pack she built has no palette entry: every color a design can name is still defined, so nothing falls
    # back to the browser's black. Text over her footage reads in her caption white unless the pack says otherwise.
    for k, v in (("light", "#ffffff"), ("dark", "#111111"), ("muted", "rgba(255,255,255,.78)"), ("pop2", pal["accent"])):
        pal.setdefault(k, v)
    var = [f"--pk-{k}:{v};" for k, v in pal.items() if isinstance(v, str)]
    var.append(f"--pk-shadow:{stylepack.text_shadow(pack)};")
    import pack_shape
    var += pack_shape.css_vars(p)
    for fam, kind in _FONT_ROLES.items():
        e = (p.get("elements") or {}).get(kind) or {}
        role = fam[2:].lower()
        var.append(f"--pk-case-{role}:{_CASE_CSS.get(e.get('case'), 'none')};")
        trk = wd.get(f"{role}_tracking", e.get("tracking", 0)) or 0
        var.append(f"--pk-track-{role}:{float(trk):g}em;")
    ease = pack_shape.ease(p)
    js = f"<script>{pack_shape.ease_js(ease, 'window.pkEase')}</script>" if ease else "<script>window.pkEase=\"power3.out\";</script>"
    return "<style id=\"pk-skin\">" + "".join(faces) + ":root{" + "".join(var) + "}</style>" + js


def _fit_px(text, role, pack, box_w, max_px, max_lines, override_file=None):
    """The biggest size her words fit at in box_w over max_lines, in the pack's own font for that role, never
    below what reads on a phone for that role (safe_zones.MIN_PX). Returns (px, fits). When this role carries a
    font override, the words are MEASURED in that override face (not the pack's), so a wider override font is sized
    to actually fit the box instead of overflowing it."""
    import stylepack, safe_zones, script_fonts
    from PIL import ImageFont
    kind = {"headline": "headline", "takeover": "takeover", "caption": "caption", "accent": "accent_caption",
            "label": "label", "detail": "detail", "thought": "thought_bubble"}.get(role, "headline")
    if kind in _FONT_FALLBACK and kind not in (stylepack.load(pack).get("elements") or {}):
        kind = _FONT_FALLBACK[kind]
    floor = safe_zones.MIN_PX.get(role if role in safe_zones.MIN_PX else "headline", 54)
    try:
        f = stylepack.element(pack, kind)["file"]
        case = (stylepack.load(pack).get("elements") or {}).get(kind, {}).get("case")
    except Exception:
        f, case = None, None
    if override_file and os.path.isfile(override_file):     # measure in her override face, so the fitted size matches what renders
        f = override_file
    t = stylepack.upper(text) if case == "upper" else text.lower() if case == "lower" else text
    words = t.split() or [" "]

    def fits(px):
        try:
            font = ImageFont.truetype(f, px) if f else ImageFont.load_default()
        except Exception:
            return True
        lines, cur = 1, ""
        for w in words:
            cand = (cur + " " + w).strip()
            w_ = script_fonts.pil_width(font, cand) if f else None   # Greek/Cyrillic the face lacks: its companion
            if (font.getlength(cand) if w_ is None else w_) <= box_w:
                cur = cand
            elif not cur:
                return False                                  # one word wider than the box
            else:
                lines, cur = lines + 1, w
        return lines <= max_lines

    lo, hi = int(floor), int(max_px)
    if fits(hi):
        return hi, True
    if not fits(lo):
        return lo, False
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    return lo, True


SPOKEN_SLOTS = ("text", "line1", "line2", "number", "label", "emoji")   # the slots filled from what she says


def _toks(x):
    return [w for w in re.findall(r"[a-z0-9$%']+", str(x or "").lower()) if len(w) > 1]


def note_is_spoken(note, said):
    """True when a design's note is the line she said (most of its words are in `said`), not an aside she typed:
    a look saved from a reel with her spoken line as its note (2026-10-20: her comment CTA kept saying "comment
    surprise" on every new reel instead of the new reel's own ask)."""
    n, s = _toks(note), set(_toks(said))
    return len(n) >= 2 and sum(w in s for w in n) >= 0.6 * len(n)


def follows_line(meta):
    """True when a design shows the line she is saying on each reel it lands on: marked so when saved from her spoken
    line, or a design that takes her captions' place (hides_captions) with a note slot. A look that hides her captions
    while it plays must carry her words (every word she says is on screen); 2026-10-21 her typed stack kept showing
    another reel's line, "I can't believe this is real.", over a different line."""
    slots = meta.get("slots") or []                      # (a design with a slot of its own for her words keeps its note:
    return bool(meta.get("note_follows_line") or (meta.get("hides_captions") and "note" in slots   # a checklist's heading)
                                                  and not any(x in slots for x in SPOKEN_SLOTS)))


def has_heading(meta):
    """True when a design shows a heading of its own (its note) over the words she says: a checklist's heading over
    her list. Given "heading / her words", it wears THAT heading on this reel; without one, the heading it was saved
    with (2026-10-21: her Butter checklist said "your exact", from the reel it was made on, over every new list)."""
    slots = meta.get("slots") or []
    return "note" in slots and any(x in slots for x in SPOKEN_SLOTS) and not follows_line(meta)


def split_heading(text, meta):
    """(heading, words) for a heading design's "heading / words", split at its first " / "; ("", text) otherwise."""
    t = str(text or "")
    if has_heading(meta) and " / " in t:
        head, rest = t.split(" / ", 1)
        if head.strip() and rest.strip():
            return head.strip(), rest.strip()
    return "", t


def design_meta(look, pack):
    """A design's design.json ({} for a builder look, or one whose files are gone)."""
    if not (look or {}).get("design"):
        return {}
    try:
        return json.load(open(os.path.join(design_dir(look.get("home") or pack, look["id"]), "design.json"), encoding="utf-8"))
    except Exception:
        return {}


def words_to_edit(look, pack, text, note=""):
    """The words Refine › Words shows for a look drawn with `text`: a heading design's heading in front of them
    ("heading / her words"), so she changes the heading right there."""
    meta = design_meta(look, pack)
    if has_heading(meta) and " / " not in str(text or "") and str(note or "").strip():
        return f"{str(note).strip()} / {text}"
    return text


def said_times(meta, text, dur, words):
    """When she says each word a design shows, from its start (__SAID__). A heading design's words are matched to
    hers one by one, so each thing she lists ticks the moment she says it, even when its words are copy written for
    the card and not her whole line; a word she never says falls back to the even spread."""
    _, text = split_heading(text, meta)
    if not str(text or "").strip():
        return []
    ws = _words(text, dur, words)
    if not (has_heading(meta) and words):
        return [round(float(w["t"]), 3) for w in ws]
    norm = lambda x: re.sub(r"[^a-z0-9']+", "", str(x).lower())
    out, k, prev = [], 0, 0.0
    for w in ws:
        j = next((j for j in range(k, len(words)) if norm(words[j]["w"].replace("*", "")) == norm(w["w"])), None)
        t = max(0.0, float(words[j]["t"])) if j is not None and norm(w["w"]) else float(w["t"])
        if j is not None and norm(w["w"]):
            k = j + 1
        prev = max(prev, t)
        out.append(round(prev, 3))
    return out


def line_note(text):
    """Her line as a two-part note ("first part / second part"), split at its first pause mark (comma, period, dash,
    colon), else where _split would break it. The pause mark itself is left out at the break."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    m = re.search(r"^(.+?\w)[,.;:!?\u2014-]+\s+(\S.*)$", t)
    if m:
        return f"{m.group(1)} / {m.group(2)}"
    a, b = _split(t)
    return f"{a} / {b}" if b else a


def follow_line(pack, design_id, said):
    """Mark one of her designs as following the line when its note is the line `said` (her words on the reel she made
    it on). True if it changed. Idempotent; a note that is an aside she typed is left exactly as it is."""
    src = design_dir(pack, design_id)
    p = os.path.join(src, "design.json")
    try:
        meta = json.load(open(p, encoding="utf-8"))
    except Exception:
        return False
    if follows_line(meta) or "note" not in (meta.get("slots") or []) or not note_is_spoken(meta.get("note"), said):
        return False
    meta["note_follows_line"] = True
    tmp = p + ".tmp"
    json.dump(meta, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, p)
    return True


def own_words(look, pack):
    """A design that carries its own words: the words it shows (its design.json "note") when it never needs hers
    (it lists the note slot with a note, or no slot filled from what she says), else None. Such a look sits in a
    quiet stretch (a b-roll reel with no talking) like anywhere else: there is nothing of hers it waits for.
    Returns "" for a design with no words at all (pictures, motion)."""
    if not (look or {}).get("design"):
        return None
    try:
        meta = json.load(open(os.path.join(design_dir(look.get("home") or pack, look["id"]), "design.json"), encoding="utf-8"))
    except Exception:
        return None
    slots, note = meta.get("slots") or [], str(meta.get("note") or "").strip()
    if follows_line(meta):
        return None
    if "note" in slots and note:
        return note
    if not any(x in slots for x in SPOKEN_SLOTS):
        return note
    return None


def _fill_values(text, meta):
    head, text = split_heading(text, meta)                  # "heading / her words": this reel's heading
    saved = head or str(meta.get("note") or "").strip()
    slots = meta.get("slots") or []
    # A note-ONLY design (an aside: its note IS the content, no list/number slot) ADAPTS to this reel's words when
    # they're passed in, so an aside placed with --text shows that reel's words, not the ones it was saved on (you:
    # looks adapt to the reel). A checklist (note + a list/number slot) keeps its own heading; a follows_line design
    # takes her spoken line. her new line, split "first part / second part" only for a design saved that way (a
    # design that types every word it is given would put the "/" on screen).
    note_only = "note" in slots and not any(x in slots for x in ("text", "line1", "line2", "number", "label"))
    if follows_line(meta) and str(text or "").strip():
        note = (re.sub(r"\s+", " ", str(text)).strip() if " / " in str(text) else line_note(text) if "/" in saved   # her own breaks win
                else re.sub(r"\s+", " ", str(text)).strip())
    elif note_only and not head and str(text or "").strip():
        note = re.sub(r"\s+", " ", str(text)).strip()       # the aside's words come from this reel, not the sample it was saved on
    else:
        note = saved
    v = {"text": text, "emoji": emoji_for(text), "note": note or text}
    if {"line1", "line2"} & set(meta.get("slots", [])):
        v["line1"], v["line2"] = _split(text, first_max=int(meta.get("first_max", 4)))
    n = number_in(text)
    if n:
        sym, val, suf = n
        num = f"{sym}{val:,.0f}{suf}" if float(val).is_integer() else f"{sym}{val:,}{suf}"
        v["number"], v["number_value"] = num, val
        sp = spoken_number(text)
        if sp and (not _NUM.search(text) or sp[3][0] <= _NUM.search(text).start()):
            a, z = sp[3]
            rest = text[:a] + text[z:]
        else:
            rest = _NUM.sub(" ", text, count=1)
        v["label"] = " ".join(rest.split()).strip(" ,.-:") or text
    else:
        v["number"], v["number_value"], v["label"] = "100", 100, text
    return v


def design_sig(src):
    """A fingerprint of a design's own files (its page and its settings): a page drawn from an older version of the
    design is told apart by content, never by file times (a move rewrites a page and makes it look new)."""
    import hashlib
    h = hashlib.sha1()
    for f in ("index.html", "design.json"):
        try:
            h.update(open(os.path.join(src, f), "rb").read())
        except OSError:
            pass
    return h.hexdigest()[:12]


# A design's working folders, never part of the design: HyperFrames (0.8.152 on) writes a fresh check record into
# .hyperframes/ of any folder it checks. Copied along, it lands two folders deeper on every draw and pushed a sandbox
# sketch's path past Windows' 260-character limit, so the sketch could not be drawn at all ([WinError 3], 2026-10-23).
WORK_DIRS = (".hyperframes", ".reel_render", "node_modules", "__pycache__")


def draw_design(src, out_dir, text, dur, pack, comp_id, look_id=None, words=None, home=None, font_overrides=None):
    """Draw one of her designs on a line: the template, her words in its slots, the pack's skin on top."""
    try:
        meta = json.load(open(os.path.join(src, "design.json"), encoding="utf-8"))
        tpl = open(os.path.join(src, "index.html"), encoding="utf-8").read()
    except Exception:
        raise Refuse("That design's files are missing. Open it again from the lookbook.")
    page_dir = os.path.join(out_dir, f"hf-reel-type-{pack.lower()}")
    shutil.rmtree(page_dir, ignore_errors=True)
    shutil.copytree(src, page_dir, ignore=shutil.ignore_patterns("design.json", "index.html", "fonts", *WORK_DIRS))
    v = _fill_values(text, meta)
    warn = None
    _ov = {str(k).lower().removeprefix("pk"): val for k, val in (font_overrides or {}).items() if val}
    for slot, spec in (meta.get("fit") or {}).items():
        _role = str(spec.get("role", "headline")).lower()
        px, ok = _fit_px(str(v.get(slot, "")), spec.get("role", "headline"), pack, int(spec.get("box_w", 900)),
                         int(spec.get("max_px", 140)), int(spec.get("max_lines", 2)), override_file=_ov.get(_role))
        tpl = tpl.replace(f"__PX_{slot.upper()}__", str(px))
        if not ok:
            warn = "Lots of words for this look, so they come out small. Fewer words read bigger."
    out = tpl.replace("__COMP__", comp_id).replace("__DUR__", f"{dur:.2f}").replace("__NUMBER_VALUE__", repr(float(v["number_value"])))
    said = json.dumps(said_times(meta, text, dur, words))
    out = out.replace("__SAID__", said)
    if follows_line(meta):                                  # timings typed in for the reel it was made on are that reel's
        out = re.sub(r"(const\s+SAID\s*=\s*)\[[^\]]*\]", lambda m: m.group(1) + said, out, count=1)
    for slot in SLOTS:
        out = out.replace(f"__{slot.upper()}__", html.escape(str(v.get(slot, "")), quote=True))
    skin = _skin(pack, page_dir, font_overrides)
    out = out.replace("</head>", skin + "</head>", 1) if "</head>" in out else skin + out
    open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8").write(out)
    rec = {"look": look_id or os.path.basename(src.rstrip("/")), "pack": pack, "text": text, "dur": round(dur, 3), "layer": "design", "warn": warn,
           "design_sig": design_sig(src), "note": v.get("note", ""), "said": json.loads(said), "pack_sig": _pack_sig(pack),
           **({"fonts": {k: os.path.basename(str(f)) for k, f in font_overrides.items() if f}} if font_overrides else {}),
           **({"home": home} if home and home != pack else {})}       # drawn from her copy in another pack's lookbook
    json.dump(rec, open(os.path.join(out_dir, "look.json"), "w", encoding="utf-8"), indent=1)
    json.dump(rec, open(os.path.join(page_dir, "look.json"), "w", encoding="utf-8"), indent=1)
    return {"dir": page_dir, "id": comp_id, "dur": dur, "warn": warn}


_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\([^)]*\)")
_OK_COLOR = re.compile(r"^(#000|#000000|#fff|#ffffff|rgba?\(\s*(0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\b.*)$", re.I)


def _parked_pieces(tpl):
    """Ids of small pieces placed at left:0;top:0 (where a script would move them from), visible by default."""
    css = dict((s.strip()[1:], b) for s, b in re.findall(r"(#[\w-]+)\s*\{([^{}]*)\}", " ".join(re.findall(r"<style[^>]*>(.*?)</style>", tpl, re.S))))
    out = []
    for tag, i, inline in re.findall(r'<(\w+)\b[^>]*?\bid="([\w-]+)"(?:[^>]*?\bstyle="([^"]*)")?', tpl):
        st = (css.get(i, "") + ";" + (inline or "")).replace(" ", "")
        if i == "root" or not re.search(r"(?:^|;)left:0(?:px)?(?:;|$)", st) or not re.search(r"(?:^|;)top:0(?:px)?(?:;|$)", st):
            continue
        if "inset:0" in st or re.search(r"width:(?:100%|1\d{3}px)", st) or re.search(r"(?:opacity:0|visibility:hidden|display:none)(?:;|$)", st):
            continue                                            # full-frame grounds, and pieces that start hidden
        out.append(i)
    return out


def check_design(src, pack, render_check=True):
    """Everything a design must be before it joins her lookbook. Returns a list of plain problems ([] = good)."""
    probs = []
    try:
        meta = json.load(open(os.path.join(src, "design.json"), encoding="utf-8"))
        tpl = open(os.path.join(src, "index.html"), encoding="utf-8").read()
    except Exception:
        return ["The design needs a design.json and an index.html."]
    if not str(meta.get("name", "")).strip():
        probs.append("design.json needs a name.")
    if meta.get("kind") not in KINDS:
        probs.append(f"design.json kind must be one of {', '.join(KINDS)}.")
    slots = meta.get("slots") or []
    if not slots or any(x not in SLOTS for x in slots):
        probs.append(f"design.json slots must list which of {', '.join(SLOTS)} it uses.")
    for need, why in (('data-composition-id="__COMP__"', "the root needs data-composition-id=\"__COMP__\""),
                      ('data-duration="__DUR__"', "the root needs data-duration=\"__DUR__\""),
                      ('__timelines["__COMP__"]', "the timeline must register as window.__timelines[\"__COMP__\"]")):
        if need not in tpl:
            probs.append(f"index.html: {why}.")
    scripts = " ".join(re.findall(r"<script[^>]*>(.*?)</script>", tpl, re.S))
    markup = re.sub(r"<script[^>]*>.*?</script>", "", tpl, flags=re.S)
    if "note" in slots and not str(meta.get("note") or "").strip() and not follows_line(meta):
        probs.append('design.json lists the note slot but has no "note": the words she wants on the card.')
    for x in slots:
        if f"__{x.upper()}__" not in markup:
            probs.append(f"index.html never shows the {x} slot (__{x.upper()}__).")
        if f"__{x.upper()}__" in scripts:
            probs.append(f"__{x.upper()}__ is her words: put it in the page, not inside a script (use __NUMBER_VALUE__ for a count).")
    styles = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", tpl, re.S)) + " ".join(re.findall(r'style="([^"]*)"', tpl))
    # a real brand keeps its real colour for its own element (another app's UI): design.json "brand_colors" names each
    # one, sampled from the brand's own mark (product/brand_logo.py), never recalled from memory
    brand = {str(v).strip().lower().replace(" ", "") for v in (meta.get("brand_colors") or {}).values()}
    bad = sorted({c for c in _COLOR.findall(styles + scripts) if not _OK_COLOR.match(c.strip())
                  and c.strip().lower().replace(" ", "") not in brand})
    if bad:
        probs.append(f"Colors come from the pack (var(--pk-…)), not the design: {', '.join(bad[:5])}.")
    import pack_shape
    ap = pack_shape.apart(pack)
    if ap:                                                  # two colors this pack keeps apart never meet in a design
        css = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", tpl, re.S))
        grounds, inks = [], []
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            sel = " ".join(sel.split())
            for m in re.finditer(r"background(?:-color)?\s*:\s*var\(--pk-(\w+)", body):
                grounds.append((sel, m.group(1)))
            for m in re.finditer(r"(?<![-\w])color\s*:\s*var\(--pk-(\w+)", body):
                inks.append((sel, m.group(1)))
        for gs, g in grounds:
            for ts, t in inks:
                if {g, t} == set(ap) and any(ts == x.strip() or ts.startswith(x.strip() + " ") for x in gs.split(",")):
                    probs.append(f"This pack keeps {ap[0]} and {ap[1]} apart, and {ts} puts {t} on {g}. Use the ink "
                                 f"(var(--pk-dark) or var(--pk-light)) there instead.")
                    break
    fams = {f.strip().strip("'\"") for f in re.findall(r"font-family\s*:\s*([^;}\"]+)", styles) for f in f.split(",")}
    odd = sorted(f for f in fams if f and f not in _FONT_ROLES and f.lower() not in ("inherit", "sans-serif", "serif"))
    if odd:
        probs.append(f"Fonts come from the pack (PkHeadline, PkTakeover, PkCaption, PkAccent, PkLabel, PkDetail, PkThought), not {', '.join(odd[:4])}.")
    if "@font-face" in tpl:
        probs.append("No @font-face in a design: the pack's fonts are put in for it.")
    ext = [u for u in re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', tpl) if "gsap" not in u]
    if ext or re.search(r"url\(\s*['\"]?https?://", tpl):
        probs.append("Everything a design shows lives in its own folder (no web links), so it works offline.")
    if "tl.set" not in scripts:
        probs.append("Every exit ends in a tl.set kill, so nothing lingers past its moment.")
    def _named(i):                                           # "#ring", or a numbered set built as "#b"+k
        stem = re.sub(r"\d+$", "", i)
        return re.search(r"""['"#]%s\b""" % re.escape(i), scripts) or (stem != i and re.search(r"""['"]#?%s['"]\s*\+""" % re.escape(stem), scripts))
    parked = [i for i in _parked_pieces(tpl) if not _named(i)]
    if parked:                                               # you: "there's a random circle in the left corner"
        probs.append(f"{', '.join('#' + i for i in parked)} sits in the top-left corner and nothing ever moves or hides "
                     "it, so it shows there the whole time. Animate it into place (starting hidden) or delete it.")
    try:                                                     # a color it names must exist in this pack, or it renders black
        with tempfile.TemporaryDirectory() as _t:
            have = set(re.findall(r"--pk-([\w-]+):", _skin(pack, _t)))
        miss = sorted({m for m in re.findall(r"var\(--pk-([\w-]+)\s*\)", tpl) if m not in have})
        if miss:
            probs.append(f"{', '.join('--pk-' + m for m in miss)} isn't defined in {pack}, so it would render in the "
                         "browser's black. Give it a fallback, var(--pk-name, #fff), or use a color the pack has.")
    except Exception:
        pass
    if probs or not render_check:
        return probs
    with tempfile.TemporaryDirectory() as tmp:                 # drawn short and long, in the pack, then the gate
        for n, sample in enumerate(("this is your hook", "this is where a longer line of your words will be when you say more")):
            d = os.path.join(tmp, f"s{n}")
            r = draw_design(src, d, sample, 3.0, pack, f"check-{n}")
            g = subprocess.run([sys.executable, os.path.join(HERE, "reel_gate.py"), r["dir"], "--pack", pack],
                               capture_output=True, text=True, timeout=300)
            if g.returncode != 0:
                tail = [l for l in (g.stdout + g.stderr).splitlines() if l.strip()][-3:]
                probs.append(f"The {'short' if n == 0 else 'long'} sample didn't pass the render check: {' / '.join(tail)}")
    return probs


def save_design(src, pack, name, about=None, sample=None, only_reel=None, design_id=None, replace=False, render_check=None,
                her_pick=False, line_text=None):
    """Put a checked design in her lookbook for this pack. Survives every update (it lives in _local/).
    sample=<sandbox idea id>: a quick sketch that never shows in her lists. Sketches are cheap on purpose: the design
    rules are checked, the render check waits for the one she locks in (sandbox_keep saves it again, fully checked).
    only_reel=<job>: a look she kept for that one reel."""
    probs = check_design(src, pack, render_check=(not sample) if render_check is None else render_check)
    if probs and not her_pick:                               # her_pick: a sketch she locked in is kept as she picked it
        raise Refuse("Not saved yet:\n- " + "\n- ".join(probs))
    meta = json.load(open(os.path.join(src, "design.json"), encoding="utf-8"))
    want = design_id or "my-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "design")
    # A save only lands on an existing look when it IS that look: the same sandbox idea's sketch being fixed, a
    # workshop draft saved again under its draft name, or replace=True. Anything else gets its own id.
    same = lambda e: replace or (sample and e.get("sample") == sample) or (
        not sample and str(e.get("name", "")).endswith("(draft)") and e.get("name") == name)
    with _book_lock(pack):
        book = _read_book(pack)
        did = _free_id(pack, book, want, same)
        dst = design_dir(pack, did)
        if os.path.abspath(dst) != os.path.abspath(src):
            tmp_dst = dst + ".saving"
            shutil.rmtree(tmp_dst, ignore_errors=True)
            shutil.copytree(src, tmp_dst, ignore=shutil.ignore_patterns("fonts", "renders", "hf-reel-type-*", *WORK_DIRS))
            shutil.rmtree(dst, ignore_errors=True); os.replace(tmp_dst, dst)
        entry = {"id": did, "name": name, "about": about or meta.get("about") or "Your own design.", "design": True,
                 "kind": meta.get("kind"), "slots": meta.get("slots"),
                 **({"sample": sample} if sample else {}), **({"only_reel": only_reel} if only_reel else {})}
        book["looks"] = [l for l in book["looks"] if l.get("id") != did] + [entry]
        _write_book(pack, book)
    if line_text:                                           # her spoken line as its words: it follows each new line
        follow_line(pack, did, line_text)
    return did


def remove_design(pack, design_id):
    """Take a design out of her lookbook (a draft she moved past). Reels already using it keep their drawing."""
    with _book_lock(pack):
        try:
            book = _read_book(pack)
        except Refuse:
            return False
        keep = [l for l in book.get("looks", []) if l.get("id") != design_id]
        if len(keep) == len(book.get("looks", [])):
            return False
        book["looks"] = keep
        _write_book(pack, book)
    shutil.rmtree(design_dir(pack, design_id), ignore_errors=True)
    return True


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "draw", "check-design", "save-design", "remove-design", "keep-everywhere", "one-offs"])
    ap.add_argument("look", nargs="?"); ap.add_argument("out", nargs="?")
    ap.add_argument("--pack", default="Butter"); ap.add_argument("--text", default=""); ap.add_argument("--dur", type=float, default=3.0)
    ap.add_argument("--job"); ap.add_argument("--name"); ap.add_argument("--about")
    ap.add_argument("--sample", help="save-design: a quick sandbox take for this idea id (hidden until she commits)")
    ap.add_argument("--id", help="save-design: the design's id (default: my-<name>); sandbox takes use my-sandbox-<idea>-take-<n>")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "check-design":
            probs = check_design(a.look, a.pack)
            print("\n".join(f"- {x}" for x in probs) if probs else f"good: this design is ready for the {a.pack} lookbook")
            return 1 if probs else 0
        if a.cmd == "save-design":
            if not a.name:
                ap.error("save-design needs --name")
            print(f"saved {save_design(a.look, a.pack, a.name, a.about, sample=a.sample, design_id=a.id)} to the {a.pack} lookbook"
                  + (" (a sandbox sketch: hidden until she locks it in)" if a.sample else ""))
            return 0
        if a.cmd == "remove-design":
            print("removed" if remove_design(a.pack, a.look) else f"no design {a.look!r} in the {a.pack} lookbook")
            return 0
        if a.cmd == "keep-everywhere":                       # a look kept for one reel, now in her lookbook for every reel
            print(f"{a.look} is in your {a.pack} lookbook for every reel now" if keep_everywhere(a.pack, a.look)
                  else f"{a.look} was already on every reel (or isn't one of your looks)")
            return 0
        if a.cmd == "one-offs":                              # looks she kept for this reel only (--job)
            for l in one_off_looks(a.pack, a.job):
                print(f"{l['id']}\t{l.get('name', '')}\t{l.get('about', '')}")
            return 0
        if a.cmd == "list":
            for l in looks(a.pack, job=a.job):
                print(f"{l['id']:18s} {l['name']:20s} {l['kind']:12s} {l['about']}")
        else:
            zones = None
            if a.job:
                zp = os.path.join(ROOT, "projects", a.job, "subject-zones.json")
                zones = json.load(open(zp, encoding="utf-8")) if os.path.isfile(zp) else None
            r = draw(a.look, a.out, a.text, a.dur, a.pack, zones)
            print(f"drew {a.look} in {a.pack} → {r['dir']}/index.html")
    except Refuse as e:
        print(str(e), file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
