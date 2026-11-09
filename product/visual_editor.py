#!/usr/bin/env python3
"""visual_editor.py — the style plan's VISUAL EDITOR: her script and her cut, live in her own browser.

She reads her reel as a script, cuts or brings back words, trims a clip's edges on the timeline, hears the cut instantly (the page skips over what is
cut; nothing is re-encoded while she works), then presses "Send my cut". The engine turns what she sent into the
cut and stitches ONCE, with the same clean-edge passes every rough cut gets. Text only (the in-chat style plan) is
still there for anyone who prefers it. Every control on her page, and how she reaches it: product/VISUAL-EDITOR-GUIDE.md.

    python3 product/visual_editor.py open <job>        get it ready (preview copy + script), start the page, open her browser
    python3 product/visual_editor.py prepare <job>     only the preview copy + script (safe to run beside transcription)
    python3 product/visual_editor.py preview <job> [--force]   her preview copy checked against her cut (made again
                                                     when it is short or her clips changed); --force makes it again anyway
    python3 product/visual_editor.py apply <job>       she said "sent": her edits become the cut in a LEAN round (seconds: plan + clean
                                                     edges + captions, no video encode; the page already plays it)
    python3 product/visual_editor.py finish-cut <job>  the ONE full-quality stitch with every check (autopilot, the widget road). On the
                                                     page road it isn't run before the looks: Finish makes the cut exactly as she set it.
                                                     --full makes it again even when the video already matches the cut
    python3 product/visual_editor.py check-base <job>  exit 0 when outputs/<job>.mp4 matches the cut, 1 when a lean round left it behind
    python3 product/visual_editor.py apply <job> --code -    the FALLBACK: the text she pasted from "Copy your cut", on stdin
    python3 product/visual_editor.py status <job>      is there a sent cut waiting, and its receipt
    python3 product/visual_editor.py mode              how she reviews: visual / text (her saved default, learned
                                                     review.style_plan_mode) / ask (product/review_gate.py asks it)
    python3 product/visual_editor.py sandbox-takes <job> <idea-id> <take-id>...   her sandbox: Claude's quick takes,
                                                     saved first with lookbook.py save-design --sample <idea-id>
    python3 product/visual_editor.py sandbox-keep <job> <idea-id> reuse|oneoff [sketch-id] [name]   lock in a sketch
    python3 product/visual_editor.py sandbox-drop <job> <idea-id>    cancel: takes gone, her line as it was
    python3 product/visual_editor.py notes <job>       her open notes on lines, with the words and where they sit in the footage
    python3 product/visual_editor.py resolve <job> <note-id> "<what you did, in her words>"   mark one fixed (the page shows it)
    python3 product/visual_editor.py restitch <job> [fixed-plan.json]   a lean round of a plan you fixed by hand for a note
    python3 product/visual_editor.py looks <job>       her graphics, live on her open page (run after any graphics change)
    python3 product/visual_editor.py todo <job>        "update my edit": everything waiting for Claude, in order
    python3 product/visual_editor.py looks-current <job>   the looks you redid are now current for her cut
    python3 product/visual_editor.py pack <job> <Pack> switch the whole reel's looks to another style pack
    python3 product/visual_editor.py accents <job>     her accent-word changes, for the captions build
    python3 product/visual_editor.py redraw-highlights <job>   takeovers and line captions drawn again with her highlights
    python3 product/visual_editor.py media-exit <job> <add-key> <exit> [at]   how her image leaves (slide-left|-right|-up|-down|fade|slide), and when
    python3 product/visual_editor.py cutaway <job> <add-key> [slip=S] [start=S] [end=S] [sound=on|off] [cut|fade] [best]
                                                     her b-roll cutaway (a video from the Media button): which moment of
                                                     her clip plays, where it sits on her cut, its sound (muted by default)
    python3 product/visual_editor.py look-requests <job> | place-look <job> <id> <look> | look-request <job> <id> done|dropped
    python3 product/visual_editor.py url <job>         the page's address, without opening a browser
    python3 product/visual_editor.py tell <job> "<one plain line>" [--chat] [--go <tab>]   a message her open page pops
                                                     (--chat: her answer goes in the chat). product/editor_says.py
    python3 product/visual_editor.py place <job> <look> <start> <end> [--text "eyebrow / headline"]   the page-path build: one look on a stretch of her cut (a hook needs --text: its own reframe; a checklist takes "heading / item, item, item")
    python3 product/visual_editor.py captions <job> <style>             her captions in a lookbook style, whole cut
    python3 product/visual_editor.py vo-start <job> <recording> [punchy|emotional]   a voiceover reel: her recording on a
                                                     black 9:16 picture (raw/vo.mp4), cut like any clip, edited on the page
    python3 product/visual_editor.py vo-pace <job> punchy|emotional   how tight the cut closes the pauses between her lines
    python3 product/visual_editor.py vo-folders        her inbox folders with clips in them
    python3 product/visual_editor.py vo-lines <job>    her lines in cut seconds (her page's numbers), her fill folder's clips as
                                                     media ids, and what has no clip (a voiceover) or which lines she picked
    python3 product/visual_editor.py vo-beats <job>    her words cut into shots by the fill's cut rules (pace, hook burst,
                                                     sentence ends and pauses), the units a fill plan names
    python3 product/visual_editor.py vo-sheets <job> [<media id> <start> <end>]   contact sheets of her fill folder (or
                                                     one clip, closer), fast: every frame fetched by jumping to it
    python3 product/visual_editor.py broll-fill <job> <plan.json>   lay her clips on her reel: a voiceover end to end, a
                                                     talking head on the lines she picked only

Rules it keeps, so it can be trusted without watching it:
  * The page plays HER CUT IN ITS OWN ORDER (cuts.json order), never filming order, so a moved line plays where
    it really sits. Lines the engine cut appear where she said them, struck through.
  * Her choices are absolute: "these words out", "these words in". A word she brought back is marked no_trim, so
    the double-take pass cannot quietly take it out again.
  * The edits name words by their place in the transcript. If the transcript itself changed since the page was
    made (words.json), the edits no longer point at the same words, and apply refuses rather than guessing.
  * One stitch per apply (stitch-cut.sh), the normal road: trim-restarts, snap-to-sound, frame grid, master.
  * Anything it cannot preview truthfully (a segment with no transcript words under it, a clip missing from the
    transcript) is refused with the reason, and the text-only style plan is the answer.
"""
import argparse, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame

for _s in (sys.stdout, sys.stderr):   # line by line: through Claude's pipe a block buffer hid every progress line until
    if hasattr(_s, "reconfigure"):     # the end, so a long first open looked dead (2026-10-21)
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))

LONG_STAMP = 1.3   # a word stamped longer than this is a mis-stamp (the rough cut's own MAXWORD), unless it's an amount
_AMOUNT = re.compile(r"^\W*(?:[$€£¥]\d[\d,.]*[kKmMbB]?|\d[\d,.]*\s*(?:%|[kKmMbB])|\d{1,3}(?:,\d{3})+(?:\.\d+)?)\W*$")
PAD = 0.04          # the margin a new edge gets beyond the word, the same 40 ms the rough cut uses
SLIVER = 0.05       # the least of a word a piece must play for the word to count as kept: kept-words.py SLIVER, so the
                    # page and her captions agree on every word
LINE_GAP = 0.7      # a breath longer than this starts a new line on the page
QUIET_LINE = 5      # beats (seconds) per line of a clip with no talking
# A piece of her cut with no words under it (b-roll inside a talking clip, a held look, a clip with no talking) is
# kept exactly as it is: no voice for the edge pass to snap to, and the double-take and dead-air passes never take it
# out. Ten seconds of b-roll inside a talking clip went missing on every Send before (a buyer, 2026-10-23).
_PINNED = {"keep_edges": True, "no_trim": True}
# VE_SERVER_STATE: a second page server with its own state file (a test or a session checking a copy reel), so it
# never stops, restarts or moves HER server (ensure_server stops a server that runs older code)
SERVER_STATE = os.environ.get("VE_SERVER_STATE") or os.path.join(ROOT, "_local", "visual-editor-server.json")


CODE_FILES = ("product/visual_editor.py", "product/visual_editor_server.py", "product/visual-editor/editor.html",
              "product/lookbook.py", "product/pack_shape.py", "product/sound_plan.py", "product/audio_levels.py",
              "product/finish.py", "product/review_route.py", "product/learned.py", "product/premake.py",
              "product/first_use.py", "product/stylepack.py", "product/hashtag.py", "product/editor_errors.py",
              "product/early_access.py", "product/editor_says.py", "product/plan_language.py",
              "product/av_sync.py")   # what the running server imports


def code_version():
    """A fingerprint of the editor's own files: a page server left running from before an update is restarted."""
    h = hashlib.sha1()
    for f in CODE_FILES:
        try:
            h.update(open(os.path.join(ROOT, f), "rb").read())
        except OSError:
            pass
    return h.hexdigest()[:8]


class Refuse(Exception):
    """A plain reason the visual editor cannot be used for this reel, said to her as it is."""


# ── the job ────────────────────────────────────────────────────────────────────────────────────────────────────
KEEP_KEY = "visual-editor-keep"   # in _local/first-use.json: the "keep using it?" question was asked


def _finished_in_editor():
    """She exported a real reel from the editor's Finish tab (test reels and _folders don't count)."""
    for f in glob.glob(os.path.join(ROOT, "projects", "*", "review", "finish.json")):
        job = os.path.dirname(os.path.dirname(f))
        if os.path.basename(job).startswith("_") or os.path.exists(os.path.join(job, "review", ".test-reel")):
            continue
        try:
            if json.load(open(f, encoding="utf-8")).get("state") == "done":
                return True
        except Exception:
            pass
    return False


def review_mode():
    """How the rough cut is reviewed. Her saved default wins; then, once she has finished a reel in the editor,
    one "keep using it?" question; otherwise the pick-one between the editor and the original widget. With the
    editor off in this engine (early access, product/early_access.py) it is always the widget."""
    try:
        import early_access
        if not early_access.editor_on():
            return "text"
    except Exception:
        return "text"
    try:
        import learned
        v = learned.value("review.style_plan_mode", "ask")
        v = (v[0] if isinstance(v, tuple) else v) or "ask"
    except Exception:
        v = "ask"
    if v in ("visual", "text"):
        return v
    try:
        import first_use
        asked = KEEP_KEY in first_use._load()
    except Exception:
        asked = True
    return "keep" if not asked and _finished_in_editor() else "ask"


def job_dir(job):
    """A reel's folder: an absolute path, or a name that resolves INSIDE projects/ (any language, any punctuation,
    never a path that climbs out, never an engine folder that happens to share the name)."""
    if os.path.isabs(job) and os.path.isdir(job):
        return os.path.abspath(job)
    projects = os.path.realpath(os.path.join(ROOT, "projects"))
    p = os.path.realpath(os.path.join(projects, job))
    if not job or not p.startswith(projects + os.sep) or os.path.dirname(p) != projects or not os.path.isdir(p):
        raise Refuse(f"There's no reel called {job!r} in projects/.")
    return p


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def load(job):
    """Every word she said (all clips, in clip order) and the cut as the last stitch saved it."""
    jd = job_dir(job)
    wp, cp = os.path.join(jd, "transcript", "words.json"), os.path.join(jd, "transcript", "cuts.json")
    for p, what in ((wp, "the transcript"), (cp, "the rough cut")):
        if not os.path.exists(p):
            raise Refuse(f"This reel doesn't have {what} yet ({os.path.relpath(p, ROOT)}). Make the rough cut first.")
    clips = json.load(open(wp, encoding="utf-8"))["clips"]
    segs = json.load(open(cp, encoding="utf-8"))["segments"]
    return jd, clips, segs, _sha(wp)[:10], _sha(cp)[:10]


def _word_fixer(jd):
    """Her one-word fixes (the shared table, hers, this reel's), laid exactly as her caption script lays them, as a
    function word -> word as it should read. The page shows her words fixed; their timing is still what was heard."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "kept_words_fix", os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "kept-words.py"))
        kw = importlib.util.module_from_spec(spec); spec.loader.exec_module(kw)
        swaps, _check, _phrases = kw.corrections_for(os.path.join(jd, "outputs", os.path.basename(jd) + ".transcript.json"))
    except Exception:
        return lambda t: t
    if not swaps:
        return lambda t: t

    def fix(t):
        m = re.match(r"^(\W*)(.*?)(\W*)$", str(t))
        lead, core, trail = m.groups() if m else ("", str(t), "")
        return lead + swaps[core.lower()] + trail if core.lower() in swaps else t
    return fix


def words_of(clips):
    """Flat word list. `c` = clip index, `s`/`e` = seconds inside that clip. A clip with no talking in it
    (product/quiet_clips.py) comes in as one-second beats (`q`, no text), never as what the transcriber heard in its
    background sound: she cuts its seconds like words, and the page draws beats, not words she didn't say."""
    import quiet_clips
    out = []
    for ci, c in enumerate(clips):
        if quiet_clips.is_silent(c):
            out.extend(quiet_clips.quiet_beats(c, ci))
            continue
        lead = ""                                        # punctuation waiting for this clip's first word
        for w in c.get("words", []):
            t = str(w.get("word", w.get("w", ""))).strip()   # older reels saved each word as "w" (every cut tool reads both)
            if "start" not in w or not t:
                continue
            # a token that is only punctuation (French " ?" comes in as its own 20 ms "word") is never a word of its
            # own: it rides on the word before it (else the one after), keeping that word's timing. As its own word
            # it could be cut but never cut away (it lasts less than a frame), so its cut stuck, Lock in never
            # showed and every Send reopened the cut (2026-10-21, two buyers)
            if not any(ch.isalnum() for ch in t):
                if out and out[-1]["c"] == ci and not out[-1].get("q"):
                    out[-1]["t"] += t
                else:
                    lead += t
                continue
            out.append({"t": lead + t, "c": ci, "s": float(w["start"]), "e": float(w["end"])})
            lead = ""
    # a word stamped over a pause ("internet." held 5.3 s) is read at its real length everywhere, kept or cut: by
    # its middle the stretched stamp fell outside the piece that plays it, so the page showed a word she says in
    # her cut as cut (2026-10-17), and a cut beside it could reach seconds into the quiet
    for i, w in enumerate(out):
        if not w.get("q") and w["e"] - w["s"] > LONG_STAMP:
            w["s"], w["e"] = word_span(w, last=i + 1 >= len(out) or out[i + 1]["c"] != w["c"])
    return out


def kept_quiet(words, clips, segs):
    """A piece of her cut with no words under it (a pause, a reaction, a look she held on purpose, kept with a click on
    her page) is hers: it comes in as one-second quiet beats (`q`, no text, the same beats a clip with no talking gets)
    so the page shows it, plays it and lets her trim it like any other piece. Never a refusal: what she approved is her
    cut. The beats go AFTER every word she said, so a word's number never moves (her looks, line edits and notes are
    keyed by it); they only change when the cut itself does.
    "No words under it" is decided by the SAME rule membership uses (_holders: a word belongs to the first piece
    holding its middle), and each beat names the piece it belongs to (`own`). Two pieces of one clip that touch or
    overlap (a word she brought back beside a line she said twice) once left the later piece with no word and no
    beat, and her Send was refused (2026-10-17, "Piece 10 of the cut has no words under it")."""
    import quiet_clips
    names = {c["clip"]: ci for ci, c in enumerate(clips)}
    held = set(k for k in _holders(words, names, segs) if k is not None)
    out = list(words)
    for k, s in enumerate(segs):
        ci = names.get(s.get("clip"))
        if ci is None or k in held:
            continue
        a, b = float(s["start"]), float(s["end"])
        if b <= a:
            continue
        t = a
        while True:
            e = b if b - t < quiet_clips.BEAT * 1.5 else t + quiet_clips.BEAT   # no sliver at the end
            out.append({"t": "", "c": ci, "s": round(t, 3), "e": round(e, 3), "q": True, "own": k})
            if e >= b:
                break
            t = e
    return out


def _holders(words, names, segs):
    """holders[i] = the piece (segment index) that holds word i, or None (the engine cut it). A quiet beat made for a
    piece (`own`) belongs to that piece; any other word to the first piece of its clip, in cut order, whose span holds
    its middle (20 ms either side). The one rule kept_quiet and membership share."""
    by_clip = {}
    for k, s in enumerate(segs):
        if s.get("clip") in names:
            by_clip.setdefault(names[s["clip"]], []).append((k, float(s["start"]), float(s["end"])))
    out = [None] * len(words)
    for i, w in enumerate(words):
        if w.get("own") is not None and 0 <= w["own"] < len(segs):
            out[i] = w["own"]
            continue
        mid = (w["s"] + w["e"]) / 2
        for k, a, b in by_clip.get(w["c"], ()):
            if a - 0.02 <= mid <= b + 0.02:
                out[i] = k
                break
        else:
            # A stamp stretched past where her voice stops ("moment." stamped 0.98 s, the piece's edge snapped to its
            # real sound at 0.39 s in) puts the middle outside a piece that still plays the word. Her captions keep
            # every word with SLIVER or more inside a piece (kept-words.py place_on_cut), so the page does too: a
            # word she hears is never shown struck through (2026-10-18, a tester's reel).
            for k, a, b in by_clip.get(w["c"], ()):
                if min(w["e"], b) - max(w["s"], a) >= SLIVER:
                    out[i] = k
                    break
    return out


def word_span(w, last=False):
    """A word's real stretch. WhisperX sometimes glues a pause or stray sound onto a word (one "And" stamped 6.3 s):
    tapped back, that word must bring one word of footage, never the 6 s. A stamp past LONG_STAMP (not an amount)
    keeps a word's length: a sentence's last word at its stamp's start, any other word at its end, beside the word
    after it; the last word of a clip (`last`: nothing after it to sit beside, so its tail is silence) at its start.
    Only for words the engine cut (what she can tap back): a kept word keeps the cut it's in."""
    s0, e0, t = float(w["s"]), float(w["e"]), str(w.get("t") or "")
    if e0 - s0 <= LONG_STAMP or _AMOUNT.match(t):
        return s0, e0
    ln = min(0.6, max(0.25, 0.07 * len(re.sub(r"\W", "", t)) + 0.12))
    return (s0, round(s0 + ln, 3)) if (last or re.search(r"[.!?]\W*$", t)) else (round(e0 - ln, 3), e0)


def membership(words, clips, segs):
    """seg_of[i] = which cut segment holds word i (None = the engine cut it). A word belongs to the segment whose
    span holds its middle, on the same clip."""
    names = {c["clip"]: ci for ci, c in enumerate(clips)}
    for k, s in enumerate(segs):
        if s.get("clip") not in names:
            raise Refuse(f"Piece {k + 1} of the cut comes from {s.get('clip')!r}, which isn't in the transcript "
                         "(b-roll or a second camera). The visual editor only previews her own talking clips; "
                         "use the text-only style plan for this one.")
    seg_of, held = _holders(words, names, segs), [0] * len(segs)
    for k in seg_of:
        if k is not None:
            held[k] += 1
    empty = [k + 1 for k, n in enumerate(held) if n == 0]
    if empty:
        raise Refuse(f"Piece{'s' if len(empty) > 1 else ''} {', '.join(map(str, empty))} of the cut "
                     f"{'have' if len(empty) > 1 else 'has'} no words under {'them' if len(empty) > 1 else 'it'} "
                     "(a pause or b-roll on purpose), which the visual editor can't show truthfully. "
                     "Use the text-only style plan for this one.")
    return seg_of


def display_order(words, segs, seg_of):
    """The order the page shows and plays: the CUT's order. Segments in cut order; before each one that moves
    forward in her footage, the words the engine cut since the last one (struck through, where she said them);
    a segment placed out of filming order (a cold open, a line moved to the end) shows where it PLAYS and is
    marked moved. Every word appears exactly once."""
    pos = lambda i: (words[i]["c"], words[i]["s"])
    seg_words = {}
    for i, k in enumerate(seg_of):
        if k is not None:
            seg_words.setdefault(k, []).append(i)
    loose = [i for i, k in enumerate(seg_of) if k is None]        # cut by the engine, source order
    # The backbone: the longest run of pieces that keep filming order. Everything else was moved by the cut
    # (a cold open, a line saved for the end) and shows where it plays, marked moved.
    ks = [k for k in range(len(segs)) if seg_words.get(k)]
    best, back = [1] * len(ks), [-1] * len(ks)
    for x in range(len(ks)):
        for y in range(x):
            if pos(seg_words[ks[y]][-1]) <= pos(seg_words[ks[x]][0]) and best[y] + 1 > best[x]:
                best[x], back[x] = best[y] + 1, y
    spine, x = set(), (max(range(len(ks)), key=lambda q: best[q]) if ks else -1)
    while x >= 0:
        spine.add(ks[x]); x = back[x]
    order, moved, li = [], set(), 0
    for k in ks:
        ids = seg_words[k]
        if k in spine:
            while li < len(loose) and pos(loose[li]) < pos(ids[0]):
                order.append(loose[li]); li += 1
        else:
            moved.add(k)
        order.extend(ids)
    order.extend(loose[li:])
    assert sorted(order) == list(range(len(words))), "every word must appear exactly once"
    return order, moved


# words that lead into the next words (a conjunction, an article, a preposition, a possessive): never a line's last word
_LEADS_ON = re.compile(r"^\W*(?:and|but|or|so|then|because|cause|if|when|while|than|that|a|an|the|to|of|for|with|"
                       r"in|on|at|from|into|my|your|our|their|his|her|its|this|these|those|i|we|you|it's|i'm)\W*$", re.I)


def lines_of(words, order, seg_of, moved):
    """Group the display order into lines: a sentence end, a real breath, a jump in the footage, or a cut right after
    a clause starts one."""
    lines, cur = [], []
    for n, i in enumerate(order):
        cur.append(i)
        j = order[n + 1] if n + 1 < len(order) else None
        if j is None:
            break
        jump = not (words[j]["c"] == words[i]["c"] and j == i + 1)
        gap = words[j]["s"] - words[i]["e"] if words[j]["c"] == words[i]["c"] else 99
        edge_moved = (seg_of[i] in moved) != (seg_of[j] in moved)
        # one word that starts a thought ("I", "So") never stands alone because of a pause: it leads into the next line
        lone = len(cur) == 1 and not re.search(r"[.?!,;:]$", words[i]["t"])
        # a cut right after a clause ("...takeover, | and then") is where she'd break the line herself
        clause_cut = seg_of[i] != seg_of[j] and re.search(r"[,;:]$", words[i]["t"])
        # footage with no talking (quiet_clips beats) reads as its own lines, QUIET_LINE seconds each, so a look or a
        # cutaway can sit on part of it
        quiet = bool(words[i].get("q")) != bool(words[j].get("q")) or (words[i].get("q") and len(cur) >= QUIET_LINE)
        if quiet or jump or edge_moved or clause_cut or re.search(r"[.?!]$", words[i]["t"]) or (gap > LINE_GAP and not lone):
            # a line never ends on a word that leads into what follows ("takeover, and | then a count up"): up to two
            # such words start the next line instead, unless that line is a piece she moved (they'd jump with it)
            carry = []
            while (cur and len(carry) < 2 and not edge_moved and _LEADS_ON.match(words[cur[-1]]["t"])
                   and not re.search(r"[.?!,;:]$", words[cur[-1]]["t"])):
                carry.insert(0, cur.pop())
            if cur:
                lines.append(cur)
            cur = carry
    if cur:
        lines.append(cur)
    return lines


def _line_edits(jd):
    try:
        e = json.load(open(os.path.join(jd, "review", "lines.json"), encoding="utf-8"))
        return {"split": [int(i) for i in e.get("split", [])], "join": [int(i) for i in e.get("join", [])]}
    except Exception:
        return {"split": [], "join": []}


def apply_line_edits(lines, edits):
    """Her own line breaks over the engine's: 'split' = a word that starts a new line, 'join' = a line's last word
    that runs on into the next line. Keyed by word, so they hold when her cut changes."""
    flat = [i for ids in lines for i in ids]
    starts = {ids[0] for ids in lines}
    starts |= {i for i in edits.get("split", []) if i in flat}
    for i in edits.get("join", []):
        if i in flat and flat.index(i) + 1 < len(flat):
            starts.discard(flat[flat.index(i) + 1])
    out, cur = [], []
    for i in flat:
        if i in starts and cur:
            out.append(cur); cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


# ── the page's data ────────────────────────────────────────────────────────────────────────────────────────────
def clip_offsets(jd, clips):
    """Where each clip starts inside the preview copy (the clips back to back, in transcript order)."""
    offs, acc = [], 0.0
    for c in clips:
        offs.append(round(acc, 3))
        acc += float(_duration(_clip_path(jd, c)) or c.get("duration") or 0)
    return offs


def _clip_path(jd, c):
    for p in (os.path.join(jd, "raw", c["clip"]), c.get("path") or "", os.path.join(jd, c["clip"])):
        if p and os.path.exists(p):
            return p
    raise Refuse(f"Her clip {c['clip']!r} isn't in this reel's raw/ folder anymore, so there's nothing to preview.")



# ── snaps: a frame she grabs on the page, for a cover or a carousel ────────────────────────────────────────────
# Taken from her ORIGINAL clip at full quality (never the lean preview), upright, into thumbnails/snaps/. The
# index (snaps.json) keeps each snap's place in the reel and which one she starred as the cover; the
# cover-thumbnail skill starts from that star.
def _snap_dir(jd):
    return os.path.join(jd, "thumbnails", "snaps")


def snaps(job):
    jd = job_dir(job)
    try:
        idx = json.load(open(os.path.join(_snap_dir(jd), "snaps.json"), encoding="utf-8"))
    except Exception:
        idx = {}
    have = [x for x in idx.get("snaps", []) if os.path.isfile(os.path.join(_snap_dir(jd), x.get("name", "")))]
    return {"snaps": have, "cover": idx.get("cover") if any(x["name"] == idx.get("cover") for x in have) else None}


def _snap_save(jd, idx):
    os.makedirs(_snap_dir(jd), exist_ok=True)
    _atomic_json(os.path.join(_snap_dir(jd), "snaps.json"), idx)


def snap(job, t, cut_t=None):
    """Grab the frame at preview second t from her original clip. Returns the snap's index entry."""
    jd, clips, _, _, _ = load(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    offs = [c["offset"] for c in script["clips"]]
    t = float(t)
    ci = max([k for k, o in enumerate(offs) if o <= t + 1e-6] or [0])
    ct = max(0.0, t - offs[ci])
    src = _clip_path(jd, clips[ci])
    idx = snaps(job)
    same = next((x for x in idx["snaps"] if x.get("clip") == clips[ci]["clip"] and abs(float(x.get("clip_time", -9)) - ct) < 0.04), None)
    if same:                                                 # that very frame is already saved: no duplicate file
        return dict(same, already=True)
    n = max([int(m.group(1)) for x in idx["snaps"] for m in [re.match(r"snap-(\d+)", x["name"])] if m] or [0]) + 1
    at = cut_t if cut_t is not None else t
    name = f"snap-{n:02d}-{int(at // 60)}m{int(at % 60):02d}s.jpg"
    os.makedirs(_snap_dir(jd), exist_ok=True)
    out = os.path.join(_snap_dir(jd), name)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ct:.3f}", "-i", src, "-frames:v", "1", "-q:v", "2", out],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not os.path.isfile(out):
        raise Refuse("That frame couldn't be saved. Try the snap again a moment later.")
    entry = {"name": name, "t": round(t, 3), "at": round(float(at), 2), "clip": clips[ci]["clip"], "clip_time": round(ct, 3)}
    _snap_save(jd, {"snaps": idx["snaps"] + [entry], "cover": idx["cover"]})
    return entry


def trial_request(job):
    """Make trial reels, pressed on her finished reel: kept in review/trial-request.json (its own slot, so it never
    replaces a carousel or story she just asked for) for the watcher to hand Claude the trial-reels skill."""
    jd = job_dir(job)
    try:
        done = json.load(open(os.path.join(jd, "review", "finish.json"), encoding="utf-8")).get("state") == "done"
    except Exception:
        done = False
    if not done:
        raise Refuse("Export your reel first, then make trial reels.")
    req = {"reel": os.path.basename(jd), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _atomic_json(os.path.join(jd, "review", "trial-request.json"), req)
    return req


# ── the chat panel: her messages to Claude (review/chat.json). Claude's replies come back through editor_says
#    (tell --chat), so this file is only her side. The watcher surfaces unhandled ones in todo() and claims them. ──
CHAT_KEEP = 40


def _chat_path(jd):
    return os.path.join(jd, "review", "chat.json")


def chat_messages(jd):
    """Her messages to Claude from the chat panel, for the page's own thread (newest kept)."""
    d = _read_json(_chat_path(jd)) or {}
    return [{"id": m.get("id"), "at": m.get("at"), "text": m.get("text")} for m in (d.get("messages") or []) if m.get("text")]


def chat_send(job, text):
    """A message she typed in the chat panel: appended to review/chat.json for the watcher to hand Claude."""
    jd = job_dir(job)
    text = (text or "").strip()
    if not text:
        return {"ok": False}
    d = _read_json(_chat_path(jd)) or {}
    msgs = list(d.get("messages") or [])
    msg = {"id": "c%d" % int(time.time() * 1000), "at": time.time(), "text": text[:4000], "from": "her", "handled": False}
    msgs.append(msg)
    _atomic_json(_chat_path(jd), {"messages": msgs[-CHAT_KEEP:]})
    return {"ok": True, "id": msg["id"], "at": msg["at"], "text": msg["text"]}


def _chat_unhandled(jd):
    d = _read_json(_chat_path(jd)) or {}
    return [m for m in (d.get("messages") or []) if not m.get("handled") and m.get("text")]


def chat_mark_handled(jd):
    """Claude has the chat messages now: never hand them over twice (its reply, in the chat, is the receipt)."""
    d = _read_json(_chat_path(jd)) or {}
    msgs = list(d.get("messages") or [])
    changed = False
    for m in msgs:
        if not m.get("handled"):
            m["handled"] = True
            changed = True
    if changed:
        _atomic_json(_chat_path(jd), {"messages": msgs[-CHAT_KEEP:]})


# ── trial reels on her Finish tab: three real re-edits of her reel (product/trial_reels.py), shown as tiles ────────
TRIAL_MINUTES = 12                                            # a first guess for one trial's export, until this
TRIAL_TIMES = os.path.join(ROOT, "_local", "trial-export-times.json")   # computer has exported some (then its median)


def trial_of(job):
    """{"of": her reel, "id": "b"} when this reel is one of her trials (its page says so and links back), else None."""
    try:
        d = json.load(open(os.path.join(job_dir(job), "review", "trial-of.json"), encoding="utf-8"))
        return {"of": d["of"], "id": d["id"]} if d.get("of") and d.get("id") else None
    except Exception:
        return None


def trial_minutes():
    try:
        ts = sorted(float(x) for x in json.load(open(TRIAL_TIMES, encoding="utf-8"))[-8:])
        return max(1, round(ts[len(ts) // 2] / 60)) if ts else TRIAL_MINUTES
    except Exception:
        return TRIAL_MINUTES


def _opening(jd):
    """A reel's opening, as she'll see it: its first words and a still of its first shot (made once, kept)."""
    try:
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
        kept = [i for i in sc["order"] if sc["words"][i]["k"]]
        text = " ".join(sc["words"][i]["t"] for i in kept[:12]) + (" …" if len(kept) > 12 else "")
    except Exception:
        text = ""
    return text


def trial_still(job):
    """The still of a reel's first shot, for its trial tile: the first piece of its cut, from its own footage."""
    jd = job_dir(job)
    out = os.path.join(jd, "review", "opening.jpg")
    cuts = os.path.join(jd, "transcript", "cuts.json")
    if os.path.isfile(out) and os.path.isfile(cuts) and os.path.getmtime(out) >= os.path.getmtime(cuts):
        return out
    try:
        seg = json.load(open(cuts, encoding="utf-8"))["segments"][0]
        clips = {c["clip"]: c.get("path") for c in json.load(open(os.path.join(jd, "transcript", "words.json"), encoding="utf-8"))["clips"]}
        src = next((p for p in (os.path.join(jd, "raw", seg["clip"]), clips.get(seg["clip"])) if p and os.path.isfile(p)), None)
        if not src:
            return None
        try:
            from hdr import HDR2SDR, hdr_kind
            pre = f"{HDR2SDR}," if hdr_kind(src) else ""
        except Exception:
            pre = ""
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{float(seg['start']) + 0.4:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", f"{pre}scale=270:480:force_original_aspect_ratio=increase,crop=270:480", "-q:v", "4", out + ".part.jpg"],
                       capture_output=True, timeout=60)
        if os.path.isfile(out + ".part.jpg"):
            os.replace(out + ".part.jpg", out)
    except Exception:
        return None
    return out if os.path.isfile(out) else None


def _trials_export_state(jd):
    try:
        return json.load(open(os.path.join(jd, "trials", "export.json"), encoding="utf-8"))
    except Exception:
        return {}


def trials_view(job):
    """Everything her Finish tab's Trial reels section shows: tile A (her reel) and a tile per trial, each with its
    opening, what changed, and where it is (planned / ready to watch / exporting / ready); the export running now;
    the minutes a trial takes on this computer; her winner."""
    import trial_reels
    jd = job_dir(job)
    name = os.path.basename(jd)
    fin = (lambda d: d if isinstance(d, dict) else {})(_read_json(os.path.join(jd, "review", "finish.json")))
    res = fin.get("result") or {}
    exp = _trials_export_state(jd)
    running = exp.get("state") == "running" and _alive(int(exp.get("pid") or 0))
    won = (_read_json(os.path.join(jd, "trials", "won.json")) or {}).get("id")
    tiles = [{"id": "a", "job": name, "label": "Your reel", "opening": _opening(jd), "changed": ["the reel you made"],
              "state": "made" if fin.get("state") == "done" else "prepared", "file": res.get("file"), "draft": res.get("draft"),
              "to": res.get("route"), "won": won == "a"}]
    try:
        plans = trial_reels.trials(job)
    except Exception:
        plans = []
    for t in sorted(plans, key=lambda x: x.get("id", "")):
        tj = t.get("job") if t.get("job") and os.path.isdir(os.path.join(ROOT, "projects", t["job"])) else None
        tile = {"id": t["id"], "job": tj, "label": f"Trial {t['id'].upper()}", "changed": t.get("changed") or [],
                "angle": t.get("angle"), "hook": t.get("hook"), "file": t.get("file"), "draft": t.get("draft"), "to": t.get("to"),
                "opening": _opening(os.path.join(ROOT, "projects", tj)) if tj else "", "won": won == t["id"]}
        if running and exp.get("current") == t["id"]:
            tf = (lambda d: d if isinstance(d, dict) else {})(_read_json(os.path.join(ROOT, "projects", tj or "", "review", "finish.json")))
            tile.update(state="exporting", step=tf.get("step") or "Starting")
        elif running and t["id"] in (exp.get("ids") or []) and t["id"] not in (exp.get("done") or []):
            tile["state"] = "queued"
        elif t.get("made") and (t.get("file") or t.get("draft")):
            tile["state"] = "made"
        elif tj:
            tile["state"] = "prepared"
        else:
            tile["state"] = "planned"
        tiles.append(tile)
    if exp.get("state") == "running" and not running:        # an export that died with its window: said, never hung
        exp = dict(exp, state="stopped")
    req = _read_json(os.path.join(jd, "review", "trial-request.json")) or {}
    return {"of": trial_of(job), "tiles": tiles, "export": exp, "minutes": trial_minutes(), "won": won,
            "asked": bool(req) and not plans, "exported": fin.get("state") == "done"}


def _read_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def trials_export(job, to=None, only=None, log=print):
    """Export her prepared trials, one at a time (never two renders at once), from her page: each trial's own Finish,
    the time it took kept so the next estimate is this computer's own."""
    import trial_reels
    jd = job_dir(job)
    todo = [t for t in trial_reels.trials(job) if t.get("job") and (not only or t["id"] in only)
            and not (t.get("made") and (t.get("file") or t.get("draft")) and (t.get("to") or "mp4") == (to or "mp4"))]
    if not todo:
        raise Refuse("Every trial is already exported.")
    st = os.path.join(jd, "trials", "export.json")
    state = {"state": "running", "pid": os.getpid(), "ids": [t["id"] for t in todo], "done": [], "to": to or "mp4",
             "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    _atomic_json(st, state)
    try:
        for t in todo:
            _atomic_json(st, dict(state, current=t["id"]))
            t0 = time.time()
            trial_reels.export(job, only=[t["id"]], to=to)
            try:
                times = json.load(open(TRIAL_TIMES, encoding="utf-8"))
            except Exception:
                times = []
            _atomic_json(TRIAL_TIMES, (times + [round(time.time() - t0)])[-20:])
            state["done"].append(t["id"])
        _atomic_json(st, dict(state, state="done", current=None, finished=time.strftime("%Y-%m-%d %H:%M:%S")))
    except trial_reels.Refuse as e:
        _atomic_json(st, dict(state, state="failed", current=None, message=str(e)))
        raise Refuse(str(e))
    except Exception:
        _atomic_json(st, dict(state, state="failed", current=None,
                              message="A trial didn't export. Your reel and the other trials are safe. Tell me in the chat."))
        raise


def trial_won(job, tid):
    """"This one won", after she posted them: saved, and handed to Claude to keep that trial's angle as a rule."""
    import trial_reels
    jd = job_dir(job)
    ids = {"a"} | {t["id"] for t in trial_reels.trials(job)}
    if tid not in ids:
        raise Refuse("That isn't one of this reel's trials.")
    rec = {"id": tid, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _atomic_json(os.path.join(jd, "trials", "won.json"), rec)
    return rec


def kit_request(job, kind, frames, photos=None):
    """She pressed Make a carousel / Make a story on her page: which kit, the snaps she ticked for it (none = the
    engine picks her best stills), and any photos she added from her favorites, her inbox or her computer (saved to her
    favorites first). Kept in review/kit-request.json for the chat; `carousel.py frames` uses exactly these, her snaps
    first, then her photos, then the engine's own picks for whatever room is left."""
    jd = job_dir(job)
    if kind not in ("carousel", "story"):
        raise Refuse("That's a carousel or a story.")
    have = {x["name"] for x in snaps(job)["snaps"]}
    frames = [f for f in (frames or []) if f in have]
    picked = []
    for mid in photos or []:                                  # only files in her favorites or her inbox, never a path
        try:
            path = media_path(mid)
        except Refuse:
            continue
        if path and os.path.isfile(path) and os.path.splitext(path)[1].lower() in MEDIA_EXT and mid not in [p["id"] for p in picked]:
            picked.append({"id": mid, "path": path})
    req = {"kind": kind, "reel": os.path.basename(jd), "frames": frames, "photos": picked, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _atomic_json(os.path.join(jd, "review", "kit-request.json"), req)
    return req


def snap_mark(job, name, cover=None, remove=False):
    jd = job_dir(job)
    idx = snaps(job)
    if not any(x["name"] == name for x in idx["snaps"]):
        raise Refuse("That snap isn't here anymore.")
    if remove:
        try:
            os.remove(os.path.join(_snap_dir(jd), name))
        except OSError:
            pass
        idx["snaps"] = [x for x in idx["snaps"] if x["name"] != name]
        if idx["cover"] == name:
            idx["cover"] = None
    elif cover is not None:
        idx["cover"] = name if cover else (None if idx["cover"] == name else idx["cover"])
    _snap_save(jd, idx)
    return snaps(job)

def _duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return None


def zoom_focus(jd):
    """Where a clip's zoom move holds still, as fractions of the frame: the middle of her head as subject-zones.json
    measured it, else the frame's centre. The same reading the stitch uses (stitch-cut.sh zoom_focus), so the page's
    preview zooms about exactly the point the render does."""
    try:
        z = json.load(open(os.path.join(jd, "subject-zones.json"), encoding="utf-8"))
        src, box = (z.get("reading") or {}).get("source") or {}, z.get("subject_src_px") or {}
        if src.get("w") and box:
            fx, fy = (box["left"] + box["right"]) / 2 / src["w"], (box["head_top"] + box["chin_bottom"]) / 2 / src["h"]
        else:
            box = z.get("subject") or z.get("face") or {}
            _fw, _fh = frame.size(jd)
            fx, fy = (box["left"] + box["right"]) / 2 / _fw, (box["head_top"] + box["chin_bottom"]) / 2 / _fh
        return {"x": round(min(max(fx, 0.0), 1.0), 4), "y": round(min(max(fy, 0.0), 1.0), 4)}
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return {"x": 0.5, "y": 0.5}


def build_script(job):
    jd, clips, segs, wid, cid = load(job)
    words = words_of(clips)
    if not words:
        raise Refuse("The transcript has no words in it, so there's no script to show.")
    words = kept_quiet(words, clips, segs)                   # quiet pieces she kept: beats, after every word
    seg_of = membership(words, clips, segs)
    order, moved = display_order(words, segs, seg_of)
    offs = clip_offsets(jd, clips)
    names = {c["clip"]: ci for ci, c in enumerate(clips)}
    _shown = _word_fixer(jd)                                  # her word fixes ("Clawed" -> "Claude"), as her captions read
    data = {
        "version": 1, "job": os.path.basename(jd), "id": wid, "cut_id": cid, "video": "preview.mp4",
        "clips": [{"name": c["clip"], "offset": offs[ci]} for ci, c in enumerate(clips)],
        # s/e are seconds in the PREVIEW (clip offset added); k = the engine keeps it; g = its segment
        "words": [{"t": _shown(w["t"]), "s": round(offs[w["c"]] + sp[0], 3), "e": round(offs[w["c"]] + sp[1], 3),
                   "c": w["c"], "k": seg_of[i] is not None, "g": seg_of[i], **({"q": 1} if w.get("q") else {})}
                  for i, w in enumerate(words) for sp in [(w["s"], w["e"]) if seg_of[i] is not None else word_span(w, last=i + 1 >= len(words) or words[i + 1]["c"] != w["c"])]],
        "order": order,
        # the engine's real pieces, in cut order, in preview seconds: the page plays THESE (split only where she
        # cuts), so what she hears is what the stitch will make
        # the reel's real shape (upright, rotation flag honoured): the page's player matches it exactly
        "canvas": dict(zip(("w", "h"), _canvas(_clip_path(jd, clips[0])))),
        "frame": dict(zip(("w", "h"), frame.size(jd))),
        "segs": [{"s": round(offs[names[s["clip"]]] + float(s["start"]), 3), "e": round(offs[names[s["clip"]]] + float(s["end"]), 3),
                  "w": [i for i in range(len(words)) if seg_of[i] == k],
                  # its Speed and Zoom move (her page's timeline), so the page plays and shows them as the stitch makes them
                  **({"sp": float(s["speed"])} if not isinstance(s.get("speed"), dict) and float(s.get("speed", 1.0) or 1.0) != 1.0 else {}),
                  **({"rp": {"from": float(s["ramp"]["from"]), "to": float(s["ramp"]["to"]), "ease": s["ramp"].get("ease", "inOut")},
                      "sp": float(s["speed"])} if isinstance(s.get("ramp"), dict) and not isinstance(s.get("speed"), dict) else {}),
                  **({"z": {"from": float(s["zoom"]["from"]), "to": float(s["zoom"]["to"]), "ease": s["zoom"].get("ease", "inOut"),
                                **({"frames": int(s["zoom"]["frames"])} if s["zoom"].get("frames") else {})}} if isinstance(s.get("zoom"), dict) else {})}
                 for k, s in enumerate(segs)],
        "focus": zoom_focus(jd),                                  # where a zoom move holds still: her face, else the middle
        "pad": PAD,
        "lines": apply_line_edits(lines_of(words, order, seg_of, moved), _line_edits(jd)),
        "moved": sorted(moved),
        **({"voiceover": {k: v for k, v in voiceover_of(jd).items() if k in ("pace", "folder", "source")}} if voiceover_of(jd) else {}),
    }
    review = os.path.join(jd, "review"); os.makedirs(review, exist_ok=True)
    _atomic_json(os.path.join(review, "script.json"), data)
    looks_manifest(jd)
    try:
        timeline_assets(jd, data)
    except Exception:
        pass                                     # the timeline still works without pictures or a waveform
    return data



# ── phase 2: the looks, played live on the page ────────────────────────────────────────────────────────────────
# Each graphic the build wrote is a HyperFrames page (hf-graphics/<name>/index.html) whose animation is a paused
# GSAP timeline, timed to the CUT. The page stacks them over the lean preview and steers each to the playhead,
# so she sees every look moving on her footage with no render. This writes the list the page reads.
_COMP_RX = {k: re.compile(rx) for k, rx in (("id", r'data-composition-id="([^"]+)"'), ("dur", r'data-duration="([\d.]+)"'),
                                             ("w", r'data-width="(\d+)"'), ("h", r'data-height="(\d+)"'))}


def _comp(jd, rel, offset=0.0, behind=False):
    html = os.path.join(jd, rel, "index.html")
    try:
        head = open(html, encoding="utf-8", errors="replace").read(200000)
    except OSError:
        return None
    m = {k: rx.search(head) for k, rx in _COMP_RX.items()}
    if not m["id"]:
        return None
    parts = rel.replace(os.sep, "/").rstrip("/").split("/")
    # a look drawn into its own folder (hf-graphics/h01-hook/hf-reel-type-<pack>) is named by that folder: the
    # leaf is the drawing's page, the same name every look's page has, and never the whole-reel type layer
    name = parts[-2] if len(parts) > 2 and parts[-1].startswith("hf-reel-type-") else parts[-1]
    return {"name": name, "dir": "/".join(parts), "id": m["id"].group(1),
            "offset": round(float(offset or 0), 3), "dur": float(m["dur"].group(1)) if m["dur"] else None,
            "w": int(m["w"].group(1)) if m["w"] else 1080, "h": int(m["h"].group(1)) if m["h"] else 1920, "behind": bool(behind)}


def _still_source(jd, t):
    """Where a still of her cut at cut-time t comes from: the cut video when it matches her cut, else her preview
    through the cut's own pieces. What she set on the page IS her cut; the video itself is made once, at Finish."""
    mp4 = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    if os.path.isfile(mp4) and not base_is_stale(jd):
        return mp4, float(t)
    try:
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
        prev, acc = os.path.join(jd, "review", sc.get("video") or "preview.mp4"), 0.0
        if os.path.isfile(prev):
            for g in sc.get("segs", []):
                d = float(g["e"]) - float(g["s"])
                if float(t) <= acc + d:
                    return prev, float(g["s"]) + max(0.0, float(t) - acc)
                acc += d
    except Exception:
        pass
    return (mp4, float(t)) if os.path.isfile(mp4) else (None, float(t))


def _look_frames(jd, moments, prune=True):
    """A small still of her cut at each look's moment (review/look-<t>.jpg), the thumbnail its card shows; the page
    draws the live graphic over it. Made once per moment, from the rough-cut video, and dropped when unused. `prune`
    only on the last pass over the full list: an earlier pass (beats only) dropped every added look's still, so each
    change redrew all of them (32 b-roll clips: a thousand stills for one fill)."""
    rv = os.path.join(jd, "review")
    want = set()
    adds = _adds(jd) if voiceover_of(jd) else {}             # a voiceover's picture IS her clip: its card shows the clip,
    for m in moments:                                        # never the black under it
        a = adds.get(m.get("layer") or "") or {}
        clip = os.path.join(jd, a.get("dir", ""), "assets", "media.mp4") if a.get("look") == "media" else ""
        clip = clip if clip and os.path.isfile(clip) else ""
        name = f"look-{int(round(float(m['t']) * 100)):06d}{'-b' if clip else ''}.jpg"
        m["frame"] = name
        want.add(name)
        out = os.path.join(rv, name)
        src, at = (clip, max(0.0, float(m["t"]) - float(a.get("offset", 0)))) if clip else _still_source(jd, m["t"])
        if not src:
            m["frame"] = None; continue
        newest = max(os.path.getmtime(src), os.path.getmtime(os.path.join(rv, "script.json")) if os.path.isfile(os.path.join(rv, "script.json")) else 0)
        if os.path.isfile(out) and os.path.getmtime(out) >= newest:       # a new cut moves what sits at t: redo it
            continue
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", src, "-frames:v", "1",
                            "-vf", "scale=270:-2", "-q:v", "4", out], capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not os.path.isfile(out):
            m["frame"] = None
    for f in os.listdir(rv) if prune and os.path.isdir(rv) else []:
        if f.startswith("look-") and f.endswith(".jpg") and f not in want:
            try:
                os.remove(os.path.join(rv, f))
            except OSError:
                pass


def _accent_items(jd):
    """Her highlight picks, each timed on her CURRENT cut. A pick is saved by its word ("i") and the cut time it had
    then ("t"); after her cut changes the old time points at another word, so the time is always read again from
    the word itself, and a word her cut took out has no highlight to show."""
    try:
        items = json.load(open(os.path.join(jd, "transcript", "accents.json"), encoding="utf-8")).get("items", [])
    except Exception:
        return []
    times = word_cut_times(jd)
    out = []
    for x in items:
        i = x.get("i")
        if times and isinstance(i, int):
            if i not in times:
                continue
            x = dict(x, t=round(times[i][0], 3))
        out.append(x)
    return out


def _accent_drops(jd):
    """P5 (verify, never block): accents saved to accents.json that the renderer will SILENTLY drop — their word
    index 'i' isn't in the current cut, so _accent_items skips them with no signal. Returns each dropped 'on' pick
    with the index(es) where that word actually IS in the cut, so a highlight is never called done when it won't
    show. Report-only: this reads two small files, renders nothing, loops nothing, and never stops a build."""
    try:
        items = json.load(open(os.path.join(jd, "transcript", "accents.json"), encoding="utf-8")).get("items", [])
    except Exception:
        return []
    times = word_cut_times(jd)
    if not times:                                            # can't verify cheaply (no aligned cut yet): say nothing, don't guess
        return []
    try:
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
        text_at = {i: str(sc["words"][i].get("t", "")) for i in times if 0 <= i < len(sc.get("words", []))}
    except Exception:
        text_at = {}
    norm = lambda t: re.sub(r"[^\w']", "", str(t).lower())
    drops = []
    for x in items:
        i = x.get("i")
        if x.get("on") and isinstance(i, int) and i not in times:
            tgt = norm(x.get("text"))
            drops.append({"text": x.get("text"), "i": i,
                          "suggest": sorted(j for j, t in text_at.items() if tgt and norm(t) == tgt)})
    return drops


def _accent_drop_warning(jd):
    """One honest block for accents_report when picks won't show; '' when every saved accent is good."""
    drops = _accent_drops(jd)
    if not drops:
        return ""
    lines = ["⚠ These accents WON'T show on the reel — their word index isn't in the current cut, so the build drops",
             "  them silently. Fix the index in accents.json before calling the highlight done:"]
    for d in drops:
        where = (f" → in the cut that word is index {', '.join(map(str, d['suggest']))}" if d["suggest"]
                 else " → that word isn't in the cut (it was trimmed): drop this pick or accent a kept word")
        lines.append(f"    '{d['text']}' saved at i={d['i']}{where}")
    return "\n".join(lines) + "\n\n"


def _her_accents(jd):
    return [{"w": x["text"], "t": x["t"]} for x in _accent_items(jd) if x.get("on")]


def _look_accents(jd, l, caps, start, end, origin=0.0):
    """Her highlighted words for one look: the ones on its own line (start..end, cut seconds), timed from the look's
    own start (`origin`, where its words are timed from) so the builder finds that very word. Captions and a
    takeover wear them, in her highlight style; any other look, none. Whole-reel captions: start 0, origin 0."""
    if not caps and (l or {}).get("layer") != "takeover":
        return None
    on = [dict(a, t=round(float(a["t"]) - origin, 3)) for a in _her_accents(jd) if start - 0.05 <= float(a["t"]) <= end + 0.05]
    return on or None


def _captions_only(jd, rel):
    """A whole-reel type page built as captions alone (build-reel-type LAYER=captions) IS her captions: it swaps and
    highlights like any captions. A page that also holds the hook or cards is not. Said by the page's own meta.json;
    an older page without it is told by its markup (no hook block, caption clips present)."""
    try:
        m = json.load(open(os.path.join(jd, rel, "meta.json"), encoding="utf-8"))
        if m.get("layer"):
            return m["layer"] == "captions"
    except Exception:
        pass
    try:
        h = open(os.path.join(jd, rel, "index.html"), encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return not re.search(r'<div[^>]+id="(hookwrap|hooksplit|card|breakaway|takeover)', h) and bool(re.search(r'class="(phrase|clip cap|w |sw)', h))


def _caption_words(jd, layer):
    """For a captions graphic: which element is which word, when it shows (cut seconds), whether it is accented,
    and what this pack's ONE accent looks like (the class the builder gives it, its size, font and color).
    The page uses it to switch a word's accent live; None when this builder's captions can't be read."""
    html_path = os.path.join(jd, layer["dir"], "index.html")
    try:
        html = open(html_path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    words = []
    # a per-reel build's captions (its word list beside it), or her copy of them; anything else is read only when its
    # markup is the engine's own one-clip-per-word captions. A page we can't read returns None: no Accent, never a wrong one.
    orig = layer.get("original") if layer.get("look") == "_original" else None
    base_dir = orig or layer["dir"]
    side = os.path.join(jd, os.path.dirname(base_dir), layer["name"] + ".json")
    if layer.get("look") not in (None, "_original", "_off", "phrase", "single-word"):
        return None                                          # highlights belong to Single word and Phrase (karaoke/spotlight light words already)
    if layer.get("look") in ("phrase", "single-word"):       # the builder highlights that very word; a highlight redraws it
        words = [{"sel": None, "t": round(w["t"], 3), "text": w["w"], "on": False} for w in _line_words(jd, 0, 1e9)]
        on = {(a["w"], round(a["t"], 2)) for a in _her_accents(jd)}
        for w in words:
            w["on"] = (w["text"], round(w["t"], 2)) in on
        return {"layer": layer["name"], "words": words, "mode": "redraw", "cls": None, "scale": 1.0, "font": None, "color": None} if words else None
    if base_dir.startswith("hf-graphics/") and side and os.path.isfile(side):
        try:
            lst = json.load(open(side, encoding="utf-8"))
            words = [{"sel": f"#w{i}", "t": round(float(w["start"]) + layer["offset"], 3), "text": w.get("text", ""),
                      "on": bool(w.get("serif") or w.get("accent"))} for i, w in enumerate(lst)]
        except Exception:
            words = []
        cls = "s"
    else:                                                    # the engine's own captions builder: one clip per word
        cls = "kw"
        for m in re.finditer(r'<div class="clip cap( kw)?"[^>]*?data-start="([\d.]+)"[^>]*>([^<]*)</div>', html):
            words.append({"sel": f'.cap[data-start="{m.group(2)}"]', "t": round(float(m.group(2)) + layer["offset"], 3),
                          "text": m.group(3), "on": bool(m.group(1))})
    if not words:
        return None
    # the accent's look, read from the builder's own CSS: its font file, its color, its size against a plain word
    look = {"cls": cls, "scale": 1.0, "font": None, "color": None}
    rule = re.search(r"\." + re.escape(cls) + r"\{([^}]*)\}", html)
    if rule:
        fam = re.search(r"font-family:\s*([^;]+)", rule.group(1))
        col = re.search(r"(?<![-\w])color:\s*([^;]+)", rule.group(1))
        look["color"] = col.group(1).strip() if col else None
        if fam:
            ff = re.search(r"@font-face\{font-family:\s*" + re.escape(fam.group(1).strip().strip("'\"")) + r";src:url\('([^']+)'\)", html)
            look["font"] = f"{layer['dir']}/{ff.group(1)}" if ff else None
    sizes = re.findall(r'class="t( s)?" id="w\d+" style="[^"]*font-size:(\d+)px', html)
    plain = [int(px) for s_, px in sizes if not s_]
    acc = [int(px) for s_, px in sizes if s_]
    if plain and acc:
        look["scale"] = round(acc[0] / plain[0], 3)
    return {"layer": layer["name"], "words": words, **look}


def accents_report(job):
    """What the captions build should accent, after her changes on the page: the engine's picks, plus the words she
    turned on, minus the ones she turned off. Each by its start in the cut, the way caption builds key accents."""
    jd = job_dir(job)
    looks = (json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")) if os.path.isfile(os.path.join(jd, "review", "looks.json")) else {}) or {}
    acc = looks.get("accents") or {}
    warn = _accent_drop_warning(jd)                          # P5: never let a dropped accent read as clean
    mine = _accent_items(jd)
    if not mine:
        return warn + "No accent changes from her page. The captions keep the engine's picks."
    on = {round(w["t"], 2): w["text"] for w in acc.get("words", []) if w.get("on")}
    for x in mine:
        k = min(on, key=lambda t: abs(t - x["t"])) if on else None
        near = k is not None and abs(k - x["t"]) < 0.15
        if x["on"] and not near:
            on[round(x["t"], 2)] = x["text"]
        elif not x["on"] and near:
            on.pop(k)
    added = [x for x in mine if x["on"]]; removed = [x for x in mine if not x["on"]]
    lines = [f"Her accents ({len(on)} words; she added {len(added)}, removed {len(removed)}). Rebuild the captions with "
             "exactly these accented, by start time in the cut (per-reel builds: hf-graphics/picks.json \"accents\"; "
             "the engine's caption builders: the plan's accent words), then run `looks` again:"]
    lines += [f"  {t:8.3f}  {w}" for t, w in sorted(on.items())]
    return warn + "\n".join(lines)


def _read_state(path, what):
    """One of her reel's state files, read whole. Missing = nothing yet. A read that fails is tried again for a few
    seconds (on Windows a file another process is swapping in, or a scanner is holding, refuses to open for a
    moment), and one that still fails STOPS the change: every change writes the whole file back, so an empty list
    stood in for an unreadable one took looks off her reel with no trace (2026-10-23: placed looks vanished)."""
    for attempt in range(30):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            if attempt == 29:
                raise Refuse(f"Your {what} couldn't be read just now, so nothing changed. Try again in a moment.")
            time.sleep(0.1)


def _swaps_doc(jd):
    return _read_state(os.path.join(jd, "review", "swaps.json"), "looks")


def _adds(jd):
    return _swaps_doc(jd).get("adds") or {}


import threading as _threading
_REEL_LOCKS, _RL_GUARD = {}, _threading.Lock()
_HELD = _threading.local()                                   # how deep this thread is in each reel's lock


def _pid_alive(pid):
    return _alive(pid)                                       # never os.kill(pid, 0): on Windows that sends Ctrl+C


def _file_lock(path, wait=60.0):
    """Across processes: the page server and Claude's commands from the chat write the same reel files."""
    t0 = time.time()
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd)
            return
        except FileExistsError:
            try:
                pid = open(path, encoding="utf-8").read().strip()
                if (pid and not _pid_alive(pid)) or (not pid and time.time() - os.path.getmtime(path) > 300):   # its writer is gone
                    os.remove(path); continue
            except OSError:
                continue
            if time.time() - t0 > wait:
                raise Refuse("Your reel is busy saving another change. Try again in a moment.")
            time.sleep(0.05)


def _locked(fn):
    """One writer at a time per reel for the looks state (looks.json, swaps.json, the drawn looks): the page server is
    threaded, and a lean cut round, a swap and a move can land together. Re-entrant, so a swap may rebuild the list."""
    import functools

    @functools.wraps(fn)
    def run(job, *a, **k):
        key = os.path.realpath(job_dir(job))
        with _RL_GUARD:
            lock = _REEL_LOCKS.setdefault(key, _threading.RLock())
        with lock:
            held = getattr(_HELD, "d", None) or {}; _HELD.d = held
            lf = os.path.join(key, "review", ".write.lock")
            if not held.get(key):                            # outermost call: take the reel's file lock too
                os.makedirs(os.path.dirname(lf), exist_ok=True)
                _file_lock(lf, getattr(_HELD, "wait", 60.0))
            held[key] = held.get(key, 0) + 1
            try:
                return fn(job, *a, **k)
            finally:
                held[key] -= 1
                if not held[key]:
                    held.pop(key, None)
                    try:
                        os.remove(lf)
                    except OSError:
                        pass
    return run


class patient:
    """`with patient(600):` this thread waits that long for the reel's lock instead of a minute. For the export: a
    retime someone else started a moment before (her page, Claude's watcher) is the same work the export needs, so the
    export waits it out rather than failing her with "busy" (a buyer, 2026-10-22). A writer that died never holds it."""
    def __init__(self, seconds):
        self.s = float(seconds)

    def __enter__(self):
        self.was = getattr(_HELD, "wait", None); _HELD.wait = self.s
        return self

    def __exit__(self, *a):
        if self.was is None:
            del _HELD.wait
        else:
            _HELD.wait = self.was


def _behind(jd):
    return _swaps_doc(jd).get("behind") or {}


def _changes_looks(fn):
    """A change to her looks after she locked them in unlocks them: the page's button goes back to 'Lock in my
    looks', so she locks in what she actually has. (The lookbook's own sandbox, '_book', isn't her reel.)"""
    import functools

    @functools.wraps(fn)
    def run(job, *a, **k):
        out = fn(job, *a, **k)
        if not (a and a[0] == "_book"):
            reopen_looks(job_dir(job))
        return out
    return run


def reopen_looks(jd):
    ph = os.path.join(jd, "review", "phase.json")
    try:
        cur = json.load(open(ph, encoding="utf-8"))
    except Exception:
        return
    if cur.get("phase") == "render":
        _atomic_json(ph, dict(cur, phase="looks"))


def can_behind():
    """Behind your head needs her cutout: HyperFrames' remove-background (the matte the final render stacks between a
    look and her, product/studio_behind.sh), so it is offered wherever HyperFrames can run (Node's npx, the pinned
    version in product.json). The lean preview shows the look in front; the final render puts it behind her."""
    try:
        pinned = json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("hyperframes")
    except Exception:
        pinned = None
    return bool(pinned) and os.path.isfile(os.path.join(ROOT, "product", "studio_behind.sh")) and \
        bool(shutil.which("npx.cmd" if os.name == "nt" else "npx"))


def looks_cut(jd):
    """The cut her looks are timed to. Set the first time her looks exist on a finished cut, and again whenever they
    are re-timed to a new cut; the page compares it with her current cut to say "preview out of date"."""
    p = os.path.join(jd, "review", "looks-cut.json")
    try:
        return json.load(open(p, encoding="utf-8")).get("cut_id")
    except Exception:
        pass
    try:
        cid = json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8")).get("cut_id")
    except Exception:
        return None
    if cid:
        _atomic_json(p, {"cut_id": cid})
    return cid


def word_cut_times(jd):
    """{word index: (start, end) in cut seconds} for every word her cut keeps, by aligning the script's kept words
    (in the cut's order) with the cut's own transcript. Words can split or join differently, so this aligns them
    by their text instead of trusting the two lists to be the same length."""
    import difflib
    try:
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
        tw = [w for w in json.load(open(os.path.join(jd, "outputs", os.path.basename(jd) + ".transcript.json"), encoding="utf-8"))["words"]
              if w.get("type", "word") == "word"]
    except Exception:
        return {}
    kept = [i for i in sc["order"] if sc["words"][i]["k"]]
    norm = lambda t: re.sub(r"[^\w']", "", str(t).lower())
    a, b = [norm(sc["words"][i]["t"]) for i in kept], [norm(w["text"]) for w in tw]
    out = {}
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            w = tw[blk.b + k]
            out[kept[blk.a + k]] = (float(w["start"]), float(w.get("end", w["start"])))
    # Seconds of a clip with no talking (q) have no words in the cut's transcript to align with: time them from the
    # pieces themselves (cut order, each piece's own speed), so a look can sit on a b-roll reel with nothing said.
    cum = 0.0
    for sg in sc.get("segs", []):
        s, e, sp = float(sg["s"]), float(sg["e"]), float(sg.get("sp") or 1.0) or 1.0
        for i in sg.get("w", []):
            w = sc["words"][i]
            if w.get("q") and i not in out:
                a, b = max(float(w["s"]), s), min(float(w["e"]), e)
                if b > a:
                    out[i] = (round(cum + (a - s) / sp, 3), round(cum + (b - s) / sp, 3))
        cum += (e - s) / sp
    return out


DRIFT_S = 0.15     # off its words by more than this = out of place: a cut edit moves a look a word or more; a
                   # placement can sit a frame or two off a word's stamp (measured 0.08 s) and is still on it


def _drawing_gone(jd, e):
    """True when an added look's drawing folder is no longer there: it isn't on her reel (the layers never show it),
    so it can't be out of place and is never moved. Counted, it read as off its words on every page load and the
    page retimed her looks each time it opened (a buyer, 2026-10-25)."""
    return bool(e.get("dir")) and not os.path.isdir(os.path.join(jd, e["dir"]))


def drifted_adds(jd):
    """Looks she added whose words now sit somewhere else in her cut (or were cut): each look is anchored to its own
    words, so one that isn't on them is out of place, however the reel got there. Refined looks are Claude's
    (looks_to_redo), so they're not counted here."""
    times = word_cut_times(jd)
    if not times:
        return []
    out = []
    for key, e in _adds(jd).items():
        m = re.match(r"^(add|cap)-w(\d+)(?:-\d+)?$", key)
        if not m or e.get("look") in (None, "_off") or "/refined-" in str(e.get("dir", "")) or _drawing_gone(jd, e):
            continue
        span0 = (e.get("span") or [None])[0]
        if e.get("after_word") is not None:                  # a look in a quiet stretch: on its place when it sits its
            w_ = int(e["after_word"])                        # gap after the word before it
            if span0 is None or w_ not in times or abs(times[w_][1] + float(e.get("gap") or 0) - float(span0)) > DRIFT_S:
                out.append(key)
            continue
        # its words: the one its name is anchored on, or the first its span covers (an edge word can count either way)
        cands = [int(m.group(2))] + [int(w) for w in (e.get("words") or [])[:1] if w is not None]
        lead = float((media_of(jd, key) or {}).get("lead") or 0) if e.get("look") == "media" else 0.0
        if span0 is None or not any(c in times and abs(times[c][0] + lead - float(span0)) <= DRIFT_S for c in cands):
            out.append(key)
    return out


def _move_keeping_refine(job, jd, key, e, s0, e0):
    """Move one added look to a new stretch, keeping everything she set on it: a refined look comes back refined
    (its words, size, effect) and where she moved it stays (its nudge)."""
    nudge = e.get("nudge")
    meta = None
    if "/refined-" in str(e.get("dir", "")):
        try:
            meta = json.load(open(os.path.join(jd, os.path.dirname(e["dir"]), "look.json"), encoding="utf-8"))
        except Exception:
            meta = None
    place_look(job, key, s0, e0, e["look"], copy=e.get("copy") or (meta or {}).get("text") if not _span_words(jd, s0, e0) else e.get("copy"))
    if nudge:
        _save_entry(jd, key, dict(_adds(jd)[key], nudge=nudge))
    if meta:
        refine(job, key, e["look"], text=meta.get("text"), size=float(meta.get("size") or 1.0), effect=meta.get("effect"))
        refine_apply(job, key, "line")


@_changes_looks
@_locked
def retime_adds(job):
    """Her cut changed: every look she added moves with the words it sits on (anchored by word, never by seconds),
    drawn again on those words in her new cut. Looks the engine built for the old cut can't be moved this way: they
    are counted, so the page can say a refresh is needed for them. Returns {"moved", "removed", "needs_refresh"}."""
    jd = job_dir(job)
    times = word_cut_times(jd)
    _retime_sounds(jd, times)                                # sounds she added on a word move with that word, looks or not
    if not os.path.isfile(os.path.join(jd, "review", "looks.json")):    # no looks on this reel: nothing else to move
        return {"moved": [], "removed": [], "needs_refresh": 0, "captions": False}
    sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    moved, removed, refined_left = [], [], []
    try:                                                     # where each word played when her looks were last in place
        was_t = {int(k): float(v) for k, v in (json.load(open(os.path.join(jd, "review", "looks-cut.json"), encoding="utf-8")).get("times") or {}).items()}
    except Exception:
        was_t = {}
    for key, e in list(_adds(jd).items()):
        m = re.match(r"^(add|cap)-w(\d+)(?:-\d+)?$", key)        # add-w12-2: a second look on the same line
        if not m or e.get("look") in (None, "_off") or _drawing_gone(jd, e):
            continue
        try:                                                 # a hook stays pinned to the reel's opening (line 1) across a
            import lookbook as _lb                           # cut edit, instead of following its word off to another line
            if key != "cap-all" and e.get("span") and _hooky(_lb.find(e["look"], _reel_pack(jd))):
                sp = _whole_cut_span(jd)
                if sp and abs(float(e["span"][0]) - float(sp[0])) > 0.01:
                    try:
                        place_look(job, key, float(sp[0]), float(sp[0]) + max(1.0, float(e["span"][1]) - float(e["span"][0])), e["look"], copy=e.get("copy"))
                        moved.append(key)
                    except Refuse:
                        pass
                continue
        except Exception:
            pass
        if key == "cap-all":                                 # her whole-reel captions: first word to last, whatever moved
            sp = _whole_cut_span(jd)
            if sp and abs(sp[0] - float((e.get("span") or [-9])[0])) + abs(sp[1] - float((e.get("span") or [0, -9])[1])) > 0.01:
                try:
                    place_look(job, key, sp[0], sp[1], e["look"]); moved.append(key)
                except Refuse:
                    pass
            continue
        if e.get("after_word") is not None and e.get("span"):  # a look in a quiet stretch: follows the word before it
            w_ = int(e["after_word"])
            if w_ in times:
                d0 = times[w_][1] + float(e.get("gap") or 0) - float(e["span"][0])
                if abs(d0) >= 0.01:
                    try:
                        _move_keeping_refine(job, jd, key, e, float(e["span"][0]) + d0, float(e["span"][1]) + d0); moved.append(key)
                    except Refuse:
                        pass
            continue
        sw, sp, anc = e.get("words"), e.get("span"), e.get("anchor") or [None, None]
        w1 = sw[1] if sw and len(sw) > 1 else None
        b0 = anc[0] if anc[0] is not None else (was_t.get(sw[0]) if sw else None)   # where its words were when it was placed
        if anc[0] is None and b0 is not None and sp and abs(float(sp[0]) - b0) > 1.0:
            b0 = None                                        # an older look already moved since: rebuilt on its words, never shifted twice
        b1 = anc[1] if anc[1] is not None else was_t.get(w1)
        together = None                                      # how far its words all moved, when they moved as one
        if sw and sp and b0 is not None and sw[0] in times:
            d0 = times[sw[0]][0] - b0
            if w1 is None or w1 == sw[0] or (w1 in times and b1 is not None and abs((times[w1][0] - b1) - d0) < 0.02):
                together = d0
        if "/refined-" in str(e.get("dir", "")):                # her refined look: never silently redrawn plain
            w0 = int(m.group(2))
            at = (e.get("span") or [float(e.get("offset") or 0) + 0.12])[0]
            if w0 in times and abs(times[w0][0] - float(at)) <= DRIFT_S:
                continue                                     # still on its words
            if together is not None:                         # its words moved as one: it slides with them, exactly as she
                d0 = together                                # refined it (its page is timed from its own start)
                e = dict(e, offset=round(float(e.get("offset") or 0) + d0, 3), span=[round(float(sp[0]) + d0, 3), round(float(sp[1]) + d0, 3)],
                         anchor=[round(times[sw[0]][0], 3), round(times[w1][0], 3) if w1 in times else None])
                _save_entry(jd, key, e)
                _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "line.json"),
                             {k: e[k] for k in ("offset", "dur", "span", "words", "anchor") if e.get(k) is not None})
                moved.append(key)
            else:
                refined_left.append(key)                     # its words were pulled apart: only Claude can redo it
            continue
        if together is not None:                             # its own words all moved together: it moves by exactly that
            d0 = together                                    # much, so a start she nudged, a length she trimmed and her
            if abs(d0) >= 0.01:                              # picture's later entrance stay
                try:
                    place_look(job, key, float(sp[0]) + d0, float(sp[1]) + d0, e["look"])
                    moved.append(key)
                except Refuse:
                    pass                                     # one look that can't move never stops the rest
            continue
        first = int(sw[0]) if sw else int(m.group(2))        # her cut changed inside its words: rebuilt on them
        words = sw or [first, None]
        if first not in times:                               # its first word is cut: it moves to the first word left on the
            left = [w for w in range(first, int(words[1] if words[1] is not None else first) + 1) if w in times]   # line;
            if not left:                                     # her cut took all of its words out: the look goes with them
                swap(job, key, None); removed.append(key); continue
            first = left[0]
        lead = float((media_of(jd, key) or {}).get("lead") or 0) if e.get("look") == "media" and first == int(m.group(2)) else 0.0
        s0 = times[first][0] + lead                          # a picture's lead is from its line's first word
        last = words[1] if words[1] in times and e.get("look") != "media" else None
        if last is None:                                     # an older look: keep how long it was on her words
            span = e.get("span") or [float(e["offset"]) + 0.12, float(e["offset"]) + float(e["dur"]) - 0.35]
            e0 = s0 + max(0.3, float(span[1]) - float(span[0]))
        else:
            e0 = times[last][1]
        if abs(s0 - ((e.get("span") or [None])[0] or -9)) < 0.01:
            continue                                         # already right where it belongs
        try:
            place_look(job, key, s0, e0, e["look"])
            moved.append(key)
        except Refuse:
            pass                                             # one look that can't move never stops the rest
    cap_redrawn = redraw_captions(job).get("redrawn")         # a lookbook caption style: drawn again on her new cut
    looks = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    built = [l for l in looks.get("layers", []) if not l.get("added") and not l.get("off")
             and (not l.get("captions") or (not cap_redrawn and l.get("look") in (None, "_original")))]
    try:                                                     # a look Claude built needs Claude only if ITS words moved: a cut
        was = {int(k): v for k, v in (json.load(open(os.path.join(jd, "review", "looks-cut.json"), encoding="utf-8")).get("times") or {}).items()}
    except Exception:                                        # at 0:40 leaves the hook at 0:00 exactly where it was
        was = {}
    if was:
        frame = 1 / 30                                       # a look's words: those starting within a frame of it;
        def _moved(l):                                       # a word moved when it shifted by half a frame or more
            o, d = float(l.get("offset") or 0), float(l.get("dur") or 0)
            ws = [w for w, a in was.items() if o - frame <= a <= o + d + frame]
            return not ws or any(w not in times or abs(times[w][0] - was[w]) >= frame / 2 for w in ws)
        built = [l for l in built if _moved(l)]
    built += [{"name": k} for k in refined_left]
    if not built:
        _atomic_json(os.path.join(jd, "review", "looks-cut.json"), {"cut_id": sc.get("cut_id"), "times": {str(w): round(a, 3) for w, (a, b) in times.items()}})
        _drop(os.path.join(jd, "review", "looks-retimed.json"))
    else:                                                    # what's left is Claude's: the page says so, todo() lists it
        _atomic_json(os.path.join(jd, "review", "looks-retimed.json"), {"cut_id": sc.get("cut_id"), "refresh": [l["name"] for l in built]})
    looks_manifest(jd)
    return {"moved": moved, "removed": removed, "needs_refresh": len(built), "captions": bool(cap_redrawn)}


def _retime_sounds(jd, times):
    """Sounds she added on a word follow that word to its new place in her cut (sound_plan.retime_added). One that
    can't is said, never dropped quietly."""
    if not times or not os.path.isfile(os.path.join(jd, "review", "sound.json")):
        return
    try:
        import sound_plan
        sound_plan.retime_added(jd, times)
    except Exception as e:
        print(f"[sound] the sounds she added couldn't follow her new cut ({type(e).__name__}: {e}); they stay where they were.",
              file=sys.stderr)


def _drop(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _cut_id(jd):
    try:
        return json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")).get("cut_id")
    except Exception:
        return None


def exporting(jd):
    """True while her Finish export runs for this reel, in any process (the page server's background job or "render"
    typed in the chat): review/finish.json says "running" and the process that owns it is still alive. A crashed
    export (its owner gone) never counts."""
    st = _read_json(os.path.join(jd, "review", "finish.json"))
    if not isinstance(st, dict) or st.get("state") != "running" or not st.get("owner"):
        return False
    return _pid_alive(st["owner"])


def looks_to_redo(jd):
    """After "Update my preview": the looks the engine built for her old cut, by name. Only Claude can redo those."""
    try:
        r = json.load(open(os.path.join(jd, "review", "looks-retimed.json"), encoding="utf-8"))
    except Exception:
        return []
    return list(r.get("refresh") or []) if r.get("cut_id") and r.get("cut_id") == _cut_id(jd) else []


def looks_current(job):
    """Claude redid her looks on her current cut: the preview is up to date again."""
    jd = job_dir(job)
    _atomic_json(os.path.join(jd, "review", "looks-cut.json"), {"cut_id": _cut_id(jd),
                                                                "times": {str(w): round(a, 3) for w, (a, b) in word_cut_times(jd).items()}})
    _drop(os.path.join(jd, "review", "looks-retimed.json"))
    looks_manifest(jd)


def _todo_id(t):
    return str(t.get("id") or ("redo:" + str(t.get("layer"))))


def claim(job, items):
    """Claude took exactly these: her page says "Claude is on your changes" for them (and only them)."""
    _atomic_json(os.path.join(job_dir(job), "review", "claude-working.json"), {"at": time.time(), "ids": [_todo_id(t) for t in items]})
    for kind, f in (("kit", "review/kit-request.json"), ("trials", "review/trial-request.json"), ("trial-won", "trials/won.json"),
                    ("broll-fill", "review/broll-fill.json")):
        if any(t.get("kind") == kind for t in items):        # a carousel / story / trials request is Claude's once taken (a
            p = os.path.join(job_dir(job), f)                # kit's frames stay in the file for carousel.py)
            try:
                _atomic_json(p, dict(json.load(open(p, encoding="utf-8")), taken=time.strftime("%Y-%m-%d %H:%M:%S")))
            except Exception:
                pass
    if any(t.get("kind") == "chat" for t in items):          # her chat messages are Claude's now (its reply in the chat is the receipt)
        chat_mark_handled(job_dir(job))


# A watcher that returns hands Claude her items; Claude can only start the next one when its turn frees up, minutes
# later on a long build. For that long her page still counts Claude as watching, so a change she sends meanwhile reads
# "Sent" and never "Type update my edit" (2026-10-18, "why is claude still saying this?"). A session that died shows the
# typing hint again after this.
HANDOFF_S = 15 * 60
PAGE_GONE_S = 30 * 60                                        # her page closed (or untouched) this long: the watcher stops


def _page_idle(job=None):
    """Seconds since this reel's editor page last asked its server for anything (an open page checks in every few
    seconds), or None when no editor server is running, so her page can't be open. Per reel: with two reels open at
    once, a closed one reads quiet even while the other is busy. An older server with no per-reel answer gives the
    whole page's quiet time instead."""
    try:
        import urllib.parse, urllib.request
        info = json.load(open(os.path.join(ROOT, "_local", "visual-editor-server.json"), encoding="utf-8"))
        q = f"?job={urllib.parse.quote(os.path.basename(job))}" if job else ""
        with urllib.request.urlopen(f"http://127.0.0.1:{int(info['port'])}/ping{q}", timeout=4) as r:
            d = json.load(r)
        return float(d.get("idle_job", d.get("idle")) or 0)
    except Exception:
        return None


def wait_for_her(job, timeout=3300.0, every=2.0):
    """The watcher: wait until her page has something only Claude can do that Claude hasn't taken yet (a note, a
    Sandbox idea, a look to build or redo), then claim it and return the list. Run in the background right after
    handing her the editor: when it returns, Claude does those items ("update my edit" / "sandbox") with no typing
    from her, then starts it again. [] when nothing came before the timeout (start it again). None when her page has
    been closed or quiet for PAGE_GONE_S (or its server is gone), twice in a row a minute apart: the watcher stops for
    good, and "open my editor" starts it again."""
    jd = job_dir(job)
    mark = os.path.join(jd, "review", "claude-watching.json")
    try:                                                     # one watcher per reel: a second would take the same items twice
        other = json.load(open(mark, encoding="utf-8"))
        if other.get("pid") != os.getpid() and not other.get("handoff") and watching(jd):
            raise Refuse(f"Already watching this reel (pid {other.get('pid')}). Nothing to start.")
    except (OSError, ValueError):
        pass
    _atomic_json(mark, {"pid": os.getpid(), "at": time.time()})
    end, beat = time.time() + float(timeout), time.time()
    looked, gone, handed = time.time(), 0, False
    working = os.path.join(jd, "review", "claude-working.json")
    try:
        while time.time() < end:
            if time.time() - beat > 10:                      # a heartbeat: her page knows a crashed watcher from a live one
                _atomic_json(mark, {"pid": os.getpid(), "at": time.time()}); beat = time.time()
            if time.time() - looked > 60:                    # is her page still open? two misses a minute apart = closed
                looked = time.time()
                idle = _page_idle(jd)
                gone = gone + 1 if idle is None or idle > PAGE_GONE_S else 0
                if gone >= 2:
                    return None
            try:
                wk = json.load(open(working, encoding="utf-8")) or {}
            except Exception:
                wk = {}
            have = set(wk.get("ids") or [])
            items = todo(job)
            cur = {_todo_id(t) for t in items}
            if have - cur:                                   # done items leave the claim: one that comes back (a remix, a
                have &= cur                                  # sketch to fix, a look to redo on another cut) is new again
                _atomic_json(working, dict(wk, ids=sorted(have)))
            if items and any(_todo_id(t) not in have for t in items):
                time.sleep(every)                            # she may still be typing a second note: take them together
                items = todo(job)
                claim(job, items)
                handed = True
                return items
            time.sleep(every)
        return []
    finally:
        try:
            if json.load(open(mark, encoding="utf-8")).get("pid") == os.getpid():
                if handed:                                   # Claude has her items and starts the next watcher when it can:
                    _atomic_json(mark, {"handoff": True, "at": time.time()})   # her page keeps saying "Claude has it"
                else:
                    os.remove(mark)
        except Exception:
            pass


def watching(jd):
    """True while a watcher (wait_for_her) is really running for this reel: her page can say Claude takes it on its own."""
    try:
        d = json.load(open(os.path.join(jd, "review", "claude-watching.json"), encoding="utf-8"))
        if d.get("handoff"):                                 # a watcher just handed Claude her items: Claude restarts it
            return time.time() - float(d.get("at") or 0) < HANDOFF_S   # as soon as it can; till then nothing to type
        fresh = time.time() - float(d.get("at") or 0) < 45   # its heartbeat (a reused pid after a crash never counts)
        return bool(d.get("pid")) and fresh and _alive(int(d["pid"]))
    except Exception:
        return False


def _chose_clean(jd):
    """The looks step is done for this cut even with nothing on screen: Claude did it (`looks` marks the cut, a b-roll
    reel left clean on purpose) or she took her looks off herself (her click is final). Never asked for again."""
    try:
        if json.load(open(os.path.join(jd, "review", "looks-made.json"), encoding="utf-8")).get("cut_id") == _cut_id(jd):
            return True
    except Exception:
        pass
    try:
        return bool(json.load(open(os.path.join(jd, "review", "looks-trash.json"), encoding="utf-8")).get("layers"))
    except Exception:
        return False


def _needs_looks(jd):
    """Her cut is locked in (phase looks or render) and no looks are on it yet: making them is Claude's next step."""
    try:
        ph = json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8")).get("phase")
    except Exception:
        return False
    if ph not in ("looks", "render"):
        return False
    if _chose_clean(jd):
        return False
    try:                                                     # her clips alone (a voiceover's b-roll) aren't looks yet
        return not any(not l.get("cutaway") for l in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")).get("layers") or [])
    except Exception:
        return True


def todo(job):
    """Everything on her page waiting for Claude, in the order to do it, for "update my edit": notes on her cut first
    (they can move the cut), then notes on looks, then notes on a whole section (Visuals, Sound, Finish; "every reel"
    ones become defaults through `learn`), then looks to redo on her new cut, then new-look ideas."""
    jd = job_dir(job)
    # Never while her export runs: the export makes her full-quality cut (a new cut id) and moves her looks onto it
    # itself. The watcher calls this every few seconds from its own process, so it saw the new cut first, took the
    # reel's lock for its own retime, and the export's retime gave up waiting with "Your reel is busy saving another
    # change" (a buyer, 2026-10-22). Everything else here only reads, so the list itself still comes back.
    if looks_cut(jd) and _cut_id(jd) and looks_cut(jd) != _cut_id(jd) and os.path.isfile(os.path.join(jd, "review", "looks.json")) \
            and not exporting(jd):
        retime_adds(job)                                     # her cut moved under her looks: what follows by itself, follows;
                                                             # what only Claude can redo lands on the list below
    ns = notes(job)
    look_ns = [n for n in ns if str(n.get("text", "")).startswith("[Look:")]
    reel_ns = [n for n in ns if re.match(r"^\[(Visuals|Sound|Finish|Reel)\b", str(n.get("text", "")))]   # a note on a whole section
    cut_ns = [n for n in ns if n not in look_ns and n not in reel_ns]
    out = [{"kind": "cut-note", **n} for n in cut_ns] + [{"kind": "look-note", **n} for n in look_ns] + [{"kind": "reel-note", **n} for n in reel_ns]
    chat_msgs = _chat_unhandled(jd)                           # messages she typed in the chat panel: direct requests, do them first
    if chat_msgs:
        joined = " | ".join(str(m.get("text", "")) for m in chat_msgs)
        out.insert(0, {"kind": "chat", "id": "chat:%s" % chat_msgs[-1].get("id"),
                       "text": "she typed in the chat panel: \"%s\". Do what she asked on this reel, then reply to her IN THE CHAT with: "
                               "python3 product/visual_editor.py tell %s \"<one short line>\" --chat" % (joined, os.path.basename(jd))})
    if _needs_looks(jd):                                     # her cut is locked in and nothing is on it yet: her first looks
        out.insert(len(cut_ns), {"kind": "make-looks", "id": "looks",
                                 "text": "her cut is locked in: make her looks (the looks step, as if she typed \"show me my looks\")"})
    _pend = os.path.join(jd, "outputs", "edits", "drive-pending.json")   # Export to Edits staged: drive the live import now
    if os.path.isfile(_pend):
        try:
            _pj = (json.load(open(_pend, encoding="utf-8")) or {}).get("project_name")
        except Exception:
            _pj = None
        _jn = os.path.basename(jd)
        out.insert(0, {"kind": "edits-drive", "id": "edits-drive",
                       "text": "her Export to Edits is STAGED but not yet in the app: drive the live import NOW (the edits-export skill) from "
                               "projects/%s/outputs/edits/manifest.json — newProject, importMedia the cut, addOverlay each look (captions last), "
                               "renameProject to \"%s\", saveProject, captureFrame to verify — then delete projects/%s/outputs/edits/drive-pending.json"
                               % (_jn, _pj or _jn, _jn)})
    fill = _read_json(os.path.join(jd, "review", "broll-fill.json"))
    if fill and not fill.get("taken") and not fill.get("done"):   # Fill with my b-roll: her voiceover's picture comes first
        out.insert(len(cut_ns), {"kind": "broll-fill", "id": f"fill:{fill.get('at')}", "folder": fill.get("folder"),
                                 "text": ("fill her voiceover with her b-roll from inbox/" if voiceover_of(jd) else
                                          f"cut away to her b-roll on lines {', '.join(str(x) for x in fill.get('lines') or [])} only "
                                          "(her face stays on every other line), from inbox/") + str(fill.get("folder"))
                                 + (f". She said: {fill['text']}" if fill.get("text") else "")})
    out += [{"kind": "redo-look", "layer": name} for name in looks_to_redo(jd)]
    out += [{"kind": "idea", **r} for r in look_requests(job, open_only=False)      # a sketch she kept with a detail to tidy too
            if r.get("status") == "open" or (r.get("fix") and r.get("status") != "dropped")]
    try:                                                     # Make a carousel / story from her page (used = renamed away)
        k = json.load(open(os.path.join(jd, "review", "kit-request.json"), encoding="utf-8"))
        if k.get("taken"):
            raise ValueError                                 # Claude has it: never asked for twice
        out.append({"kind": "kit", "id": f"kit:{k.get('at')}", "text": f"make a {k.get('kind')} from this reel (the {k.get('kind')} skill)"})
    except Exception:
        pass
    try:                                                     # Make trial reels from her finished reel's page
        tr = json.load(open(os.path.join(jd, "review", "trial-request.json"), encoding="utf-8"))
        if not tr.get("taken"):
            out.append({"kind": "trials", "id": f"trials:{tr.get('at')}", "text": "make trial reels from this reel (the trial-reels skill)"})
    except Exception:
        pass
    try:                                                     # "This one won" on a trial tile, after she posted them
        w = json.load(open(os.path.join(jd, "trials", "won.json"), encoding="utf-8"))
        if not w.get("taken"):
            out.append({"kind": "trial-won", "id": f"won:{w.get('id')}:{w.get('at')}", "trial": w.get("id"),
                        "text": f"her trial {str(w.get('id')).upper()} won: keep its angle as a rule for her next reels (teach_style.py keep)"})
    except Exception:
        pass
    return out


@_changes_looks
@_locked
def set_behind(job, layer_name, on):
    """She marks a look 'behind your head' for the final video. The lean preview can't cut her out, so it shows the
    look in front with a plain note; the render does it for real with her cutout."""
    jd = job_dir(job)
    if on and not can_behind():
        raise Refuse("Behind your head needs the render tools (Node and HyperFrames), and they aren't set up on this "
                     "computer yet. Say \"set me up\" in the chat and I'll add them.")
    path = os.path.join(jd, "review", "swaps.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        d = {"swaps": {}, "adds": {}}
    except Exception:                                        # unreadable: never write an empty one over her looks
        raise Refuse("Your looks couldn't be read just now, so nothing changed. Try again in a moment.")
    b = d.setdefault("behind", {})
    if on:
        b[layer_name] = True
    else:
        b.pop(layer_name, None)
    _atomic_json(path, d)
    looks_manifest(jd)
    return {"layer": layer_name, "behind": bool(on)}


def _swaps(jd):
    return _swaps_doc(jd).get("swaps") or {}


def _layer(jd, name):
    d = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    for l in d.get("layers", []):
        if l["name"] == name and (l.get("swappable") or l.get("captions")):
            return l, d
    raise Refuse("That graphic can't be swapped (it's not a single moment's look).")


CHECK_KINDS = ("edge", "band", "face", "clash", "caps", "fast")


@_locked
def check_ok(job, layer_name, kind):
    """She looked at a finding and it's on purpose: that look's finding stays quiet (until she swaps in another look),
    and a look on her face is also let through Finish (finish.allow), so the render never stops on it."""
    jd = job_dir(job)
    if kind not in CHECK_KINDS:
        raise Refuse("That isn't one of the checks.")
    L = next((l for l in (json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")).get("layers") or [])
              if l["name"] == layer_name), None)
    if not L:
        raise Refuse("That look isn't on your reel anymore. Reload the page.")
    p = os.path.join(jd, "review", "checks-ok.json")
    try:
        items = json.load(open(p, encoding="utf-8")).get("items", {})
    except Exception:
        items = {}
    items[f"{layer_name}|{kind}"] = {"look": _ok_sig(L)}     # the look itself, never its folder: a redraw (her new cut, a
                                                              # pack switch, captions stepping aside) keeps her answer
    _atomic_json(p, {"items": items})
    looks_manifest(jd)                                       # the page reads its list from looks.json: so it stays quiet on reload
    if kind == "face":
        import finish
        finish.allow(job, layer_name)
    return {"ok": True}


def _ok_sig(L):
    """Which look is on the line, whatever folder it's drawn in: its look id (her picture's own id for a picture)."""
    lk = L.get("look") or "_original"
    d = str(L.get("dir") or "")
    ref = re.search(r"/(refined-[^/]+)/", d)                 # a refine is a new look: checked again
    nd = [round(float(x or 0), 1) for x in (L.get("nudge") or [])[:4]]   # and so is a move
    base = ("media:" + d.split("/_looks/")[-1].split("/")[0] + ":" + str(L.get("look_name") or "")) if lk == "media" else lk
    return f"{base}|{ref.group(1) if ref else ''}|{nd}"


def checks_ok(jd, layers):
    """The findings she said are fine, for as long as that line keeps the same look (another look is checked again)."""
    try:
        items = json.load(open(os.path.join(jd, "review", "checks-ok.json"), encoding="utf-8")).get("items", {})
    except Exception:
        return {}
    by = {l["name"]: l for l in layers}
    out = {}
    for k, v in items.items():
        L = by.get(k.split("|")[0])
        if L and ((isinstance(v, dict) and v.get("look") == _ok_sig(L)) or (isinstance(v, str) and v == L.get("dir"))):
            out[k] = True
    return out


_TEXT_SINK = re.compile(r"\.(?:textContent|innerText|innerHTML|outerHTML|nodeValue)\s*\+?=(?!=)|"
                        r"\b(?:insertAdjacentHTML|insertAdjacentText|createTextNode|append|prepend|write)\s*\(")
_REVEAL = re.compile(r"\.hidden\s*=\s*(?:false|0)|removeAttribute\(\s*['\"]hidden|toggleAttribute\(\s*['\"]hidden|"
                     r"display['\"]?\s*[:=,]\s*['\"](?!none)\w|\.style\.display\b")


def _shown_text(h):
    """The text a look's page can put on screen: its markup minus scripts, styles and what never shows (a <template>,
    an element with the `hidden` attribute, or display:none inline or by a one-selector rule of its own stylesheet).
    A hidden element still counts when the page's script reads it AND writes what it read onto the page (a count-up
    that splits its hidden note around the number, a card row that takes its names from it) or can show it again;
    one read only for timing (a design keyed off her note's words) is not words on screen (2026-10-21: captions
    stepped aside under four looks that never showed her words). visibility:hidden never counts as hidden here: a
    look's animation reveals it (autoAlpha)."""
    from html.parser import HTMLParser
    scripts = " ".join(re.findall(r"(?is)<script\b[^>]*>(.*?)</script>", h))
    gone = {"tag": set(), "id": set(), "class": set()}       # one-selector stylesheet rules that hide (never @media ones)
    for css in re.findall(r"(?is)<style\b[^>]*>(.*?)</style>", h):
        css, depth, sel, body, skip = re.sub(r"(?s)/\*.*?\*/", " ", css), 0, "", "", False
        for ch in css:
            if ch == "{":
                depth += 1
                if depth == 1:
                    skip, body = sel.strip().startswith("@"), ""
                    continue
            elif ch == "}":
                depth = max(0, depth - 1)
                if depth == 0:
                    if not skip and re.search(r"display\s*:\s*none", body, re.I):
                        for s in sel.split(","):
                            m = re.fullmatch(r"\s*([a-zA-Z][\w-]*)?(?:([#.])([A-Za-z_][\w-]*))?\s*", s)
                            if m and m.group(3):
                                gone["id" if m.group(2) == "#" else "class"].add(m.group(3))
                            elif m and m.group(1):
                                gone["tag"].add(m.group(1).lower())
                    sel = ""
                    continue
            if depth == 0:
                sel += ch
            else:
                body += ch
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    class _Page(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.shown, self.hidden = [], [], []    # stack: [tag, the hidden element's record or None]

        def handle_starttag(self, tag, attrs):
            if tag in void:
                return
            a = {k: (v or "") for k, v in attrs}
            cls = a.get("class", "").split()
            off = (tag in ("script", "style", "template", "title", "noscript") or "hidden" in a
                   or re.search(r"display\s*:\s*none", a.get("style", ""), re.I) or tag in gone["tag"]
                   or a.get("id") in gone["id"] or any(c in gone["class"] for c in cls))
            rec = None
            if off and not any(r for _, r in self.stack):        # the outermost hidden element owns its text
                rec = {"id": a.get("id"), "class": cls, "text": []}
                self.hidden.append(rec)
            self.stack.append([tag, rec])

        def handle_endtag(self, tag):
            for k in range(len(self.stack) - 1, -1, -1):
                if self.stack[k][0] == tag:
                    del self.stack[k:]
                    return

        def handle_data(self, data):
            if any(t in ("script", "style") for t, _ in self.stack):
                return                                       # code is never words on screen
            rec = next((r for _, r in self.stack if r), None)
            (rec["text"] if rec else self.shown).append(data)

    p = _Page()
    try:
        p.feed(h)
        p.close()
    except Exception:                                        # unreadable markup: every tag stripped, as before
        return re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", h))
    out = list(p.shown)
    for rec in p.hidden:
        refs = ([fr"getElementById\(\s*['\"]{re.escape(rec['id'])}['\"]", fr"['\"`][^'\"`]*#{re.escape(rec['id'])}(?![\w-])"]
                if rec["id"] else []) \
            + [fr"getElementsByClassName\(\s*['\"]{re.escape(c)}['\"]|['\"`][^'\"`]*\.{re.escape(c)}(?![\w-])" for c in rec["class"]]
        if refs and any(re.search(x, scripts) for x in refs) and (_REVEAL.search(scripts) or _reads_into_page(scripts, refs)):
            out += rec["text"]
    return " ".join(out)


def _reads_into_page(js, refs):
    """True when text the script reads from a hidden element (`refs`: how the script names it) reaches a text write on
    the page: the names assigned from it, and the names assigned from those, statement by statement."""
    src, ident = re.compile("|".join(refs)), r"[A-Za-z_$][\w$]*"
    stmts = [s for s in re.split(r"[;\n]", js) if s.strip()]
    uses = lambda s, names: src.search(s) or any(re.search(fr"(?:(?<=\.\.\.)|(?<![.\w$])){re.escape(t)}(?![\w$])", s) for t in names)
    params = lambda p: set(re.findall(ident, re.sub(r"=[^,]*", "", p)))
    funcs = {m.group(1) or m.group(3): params(m.group(2) or m.group(4) or "") for m in   # its helpers: put(host, list)
             re.finditer(fr"(?:function\s+({ident})\s*\(([^)]*)\)|({ident})\s*=\s*(?:function\s*)?\(([^)]*)\)\s*(?:=>)?\s*\{{)", js)}

    def bound(s):
        """The names a statement gives a value: plain and destructured assignments, and its callbacks' parameters."""
        m = _TEXT_SINK.search(s)
        head = s[:m.start()] if m else s
        out = set(re.findall(fr"(?<![.\w$])({ident})\s*=(?![=>])", head))
        for d in re.findall(r"[\[{]([^\[\]{}=]*)[\]}]\s*=(?![=>])", head):
            out |= set(re.findall(ident, d))
        for p in re.findall(r"\(([^()]*)\)\s*=>", s) + re.findall(r"function\s*[\w$]*\s*\(([^)]*)\)", s):
            out |= params(p)
        out |= set(re.findall(fr"(?<![.\w$])({ident})\s*=>", s))
        for f, ps in funcs.items():
            if re.search(fr"(?<![.\w$]){re.escape(f)}\s*\(", s):
                out |= ps
        return out

    taint, grew = set(), True
    while grew:
        grew = False
        for s in stmts:
            names = bound(s)
            if names - taint and uses(s, taint):
                taint |= names
                grew = True
    return any(uses(s[m.end():], taint) for s in stmts for m in _TEXT_SINK.finditer(s))


def _says_her_words(jd, l):
    """A look that puts the words she's saying on screen (a Sandbox design, one of hers, a card of her line) takes the
    captions' place while it plays, so her words never show twice: most of the words she says in its window are in
    the words the look draws."""
    try:
        h = open(os.path.join(jd, l["dir"], "index.html"), encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    shown = {p for w in re.findall(r"[a-z0-9$%']+", _shown_text(h).lower()) for p in (w, *w.split("'")) if len(p) > 1}   # don't, don
    said = [w for w in re.findall(r"[a-z0-9$%']+", " ".join(x["w"] for x in _line_words(jd, l["offset"], l["offset"] + (l["dur"] or 0))).lower()) if len(w) > 1]
    return len(said) >= 2 and sum(w in shown for w in said) >= 0.6 * len(said)


def _design_newer(page):
    """True when the design of hers this page was drawn from (its look.json names the look and pack) was changed after
    the page was drawn, so a Swap to it must draw it again: by its fingerprint (look.json design_sig), else by file time
    for a page drawn before fingerprints. False for the engine's own looks and anything unreadable. (A move rewrites
    the page, so by time alone a page drawn from the OLD design read as current, 2026-10-18 the sloppy arrow.)"""
    try:
        import lookbook
        rec = _read_json(os.path.join(os.path.dirname(page), "look.json")) or {}
        src = lookbook.design_dir(rec.get("home") or rec["pack"], rec["look"])   # the copy it was drawn from
        meta = _read_json(os.path.join(src, "design.json")) or {}
        if lookbook.follows_line(meta) and rec.get("note") != lookbook._fill_values(rec.get("text") or "", meta)["note"]:
            return True                                      # drawn with words that aren't her line (2026-10-21 the typed stack)
        if rec.get("design_sig"):                            # drawn with a fingerprint: compare what it was drawn from
            return os.path.isdir(src) and rec["design_sig"] != lookbook.design_sig(src)
        newest = max(os.path.getmtime(os.path.join(src, f)) for f in ("index.html", "design.json") if os.path.isfile(os.path.join(src, f)))
        return newest > os.path.getmtime(page)
    except Exception:
        return False


def _hides_captions(jd, l):
    """A design of hers that asks for the captions to step aside while it plays (design.json "hides_captions": true),
    even though its words aren't the ones she says: a full-screen typed line over her reaction ("I can't believe
    this is real." over "oh my god", 2026-10-18). The default stays her rule (only her own words replace the
    captions); this is the look's own setting, so it travels with the look to every reel it lands on."""
    try:
        import lookbook
        rec = _read_json(os.path.join(jd, l["dir"], "look.json")) or {}
        pack, look = rec.get("pack"), rec.get("look") or l.get("look")
        if not pack or not look:
            return False
        return bool((_read_json(os.path.join(lookbook.design_dir(pack, look), "design.json")) or {}).get("hides_captions"))
    except Exception:
        return False


def _keeps_captions(jd, l):
    """True when her captions stay on under this look even though it shows the words she's saying (a card, a label, a
    hook): she taught it for every reel (learned "caption.never_hide"), or the look itself says so ("keeps_captions":
    true in its design.json, or on the look in her lookbook). Only the stepping aside for a look that SHOWS her words
    is switched off; a caption style she picks for a line still replaces the captions there, so words never double.
    The default is unchanged: with neither set, a look that shows her words takes the captions' place (2026-10-25: a
    buyer asked twice that her captions never be removed, and they kept stepping aside under her cards)."""
    try:
        import learned
        if learned.get("caption.never_hide", False):
            return True
    except Exception:
        pass
    try:
        import lookbook
        rec = _read_json(os.path.join(jd, l["dir"], "look.json")) or {}
        pack, look = rec.get("pack"), rec.get("look") or l.get("look")
        if not pack or not look:
            return False
        try:
            entry = lookbook.find(look, pack)
        except Exception:
            entry = {}
        if entry.get("keeps_captions"):
            return True
        return bool((_read_json(os.path.join(lookbook.design_dir(entry.get("home") or pack, look), "design.json")) or {}).get("keeps_captions"))
    except Exception:
        return False


def _line_words(jd, start, end):
    """Her words in the cut between start and end: [{w, t}] with t from `start` (the kept-words transcript)."""
    try:
        tw = json.load(open(os.path.join(jd, "outputs", os.path.basename(jd) + ".transcript.json"), encoding="utf-8"))["words"]
    except Exception:
        return []
    return [{"w": w["text"], "t": round(float(w["start"]) - start, 3), "e": round(float(w.get("end", w["start"])) - start, 3)} for w in tw
            if w.get("type", "word") == "word" and start - 0.05 <= float(w["start"]) < end]


USER_STYLE = os.path.join(ROOT, "product", "creative-vault", "user-style.json")


def _default_pack():
    """Her saved default style pack (creative-vault/user-style.json "default_pack": the homebase pick, "make X my
    default", or a pack she built), or None. The same field every build route reads (cleanyap.default_pack);
    in the copy the engine ships from it is kept in _local/default-pack.json (user_style.py)."""
    import user_style
    return user_style.default_pack(USER_STYLE)


def set_default_pack(pack):
    """Make a pack her default for every new reel (the Lookbook's "Make it my default"). The same write as
    cleanyap.set_default_pack, without loading the CapCut builder into the page server: every build route and
    the editor open new reels in it. The reel she is on keeps its own pack (switching it is "Use this pack")."""
    import stylepack
    import user_style
    if pack not in stylepack.names():
        raise Refuse(f"There's no style pack called {pack!r} in this engine.")
    user_style.set_default_pack(pack, USER_STYLE)
    return {"default": pack}


def _looks_or_fresh(jd):
    """review/looks.json, or, on a reel with no look on it yet (no list written), an empty one in the reel's pack: a
    split, a pack switch or the lookbook before her first look works the same as after it, never a crash."""
    try:
        return json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    except FileNotFoundError:
        return {"layers": [], "pack": _reel_pack(jd)}


def _swap_pack(jd, looks):
    """The reel's pack when this engine has it; else her default pack; else the first shipped pack, said in one line."""
    import stylepack
    have = list(stylepack._data().get("packs", {}))
    want = looks.get("pack")
    if want in have:
        return want, None
    mine = _default_pack()
    pick = mine if mine in have else ("Butter" if "Butter" in have else have[0])
    return pick, (f"Drawn in {pick}: this reel's pack ({want}) isn't in this engine." if want else None)


@_locked
def swap_menu(job, layer_name):
    """Every look, drawn on this line (its words, its timing, her pack, placed around her), for the Swap menu.
    Drawn into hf-graphics/_looks/<layer>/<look>/ (seconds; redrawn only when the line changes)."""
    import lookbook
    jd = job_dir(job)
    layer, looks, pack, note, start, dur, caps, words, text, zones = _line_ctx(jd, layer_name)
    out = []
    capl = lambda l: (l.get("base") or l["id"]) in lookbook.CAPTION_LOOKS
    for l in lookbook.looks(pack, job=os.path.basename(jd)):
        # the reel's captions swap only to caption looks; a look on one line swaps to any line look, captions for
        # that line included (karaoke, phrase, single word...), the same menu Add a look offers
        if caps != (l.get("layer") == "captions") and not (not caps and capl(l)):
            continue
        if _is_hook(l) and (layer_name.startswith("add-") or layer.get("added")):   # her own copy, never her spoken line
            out.append(_hook_tile(jd, l, f"hf-graphics/_looks/{layer_name}/_menu/{l['id']}", f"{layer_name}-{l['id']}", dur, pack, zones,
                                  (_entry(jd, layer_name)[0] or {}).get("copy")))
            continue
        out.append(_draw_choice(jd, l, f"hf-graphics/_looks/{layer_name}/_menu/{l['id']}", f"{layer_name}-{l['id']}", text, dur, pack, zones, words,
                                accents=_look_accents(jd, l, caps, start, start + dur, origin=start), track=_track_for(jd, l, start, dur)))
    frame = _frame_at(jd, start + min(0.6, dur / 2), layer_name)          # her own frame behind every tile, never black
    if layer_name.startswith(("add-", "cap-")) or layer.get("added"):
        # a look she added has no "original": taking it off is the small "Take this look off" button, never a tile
        # called "Your original" that quietly removes it
        return {"layer": layer_name, "offset": start, "dur": dur, "text": text, "pack": pack, "note": note, "captions": caps,
                "current": layer.get("look"), "original": None, "add": True, "looks": out, "frame": frame}
    orig = layer.get("original") or layer["dir"]
    oc = _comp(jd, orig) or {}
    if caps:
        text = "your captions, the whole reel"
    return {"layer": layer_name, "offset": start, "dur": dur, "text": text, "pack": pack, "note": note, "captions": caps,
            "current": layer.get("look"), "original": {"dir": orig, "comp": oc.get("id"), "dur": oc.get("dur")}, "looks": out,
            "frame": frame}


# Effects Library names (what her hearts are saved under) that ARE one of the page's own looks, by the look's id
# here. Every other heart is an effect the page can't draw on a line itself: My favorites lists it for Claude.
HEART_LOOKS = {"karaoke": "karaoke", "word-by-word": "single-word", "bottom-pop": "phrase",
               "full-screen-takeover": "takeover", "stat-countup": "counter"}
_CATALOG_TITLES = {}


def _catalog_titles():
    """{name: title} of the Effects Library's catalog pieces, read from the library page's own CATALOG block, so a
    heart shows by the name she saw it under there ("Kinetic Slam", not caption-kinetic-slam)."""
    p = os.path.join(ROOT, "product", "effects-library.html")
    try:
        mt = os.path.getmtime(p)
        if _CATALOG_TITLES.get("mtime") != mt:
            m = re.search(r"var CATALOG=(.*?);/\* CATALOG:END \*/", open(p, encoding="utf-8").read(), re.S)
            items = json.loads(m.group(1)).get("items", []) if m else []
            _CATALOG_TITLES.update(mtime=mt, titles={str(r[0]): str(r[1]) for r in items if len(r) > 1})
        return _CATALOG_TITLES.get("titles") or {}
    except Exception:
        return {}


def hearts():
    """The effects she hearted in the Effects Library (favorites/effects.json: hers, written by the library's own
    server, never touched by an update), for the page's My favorites filter: [{"name", "title", "look"}], where
    "look" is the page's look id when the effect is one of its looks, else None (Claude puts it on a line by name)."""
    import favorites
    titles = _catalog_titles()
    return [{"name": n, "title": titles.get(n) or n.replace("-", " ").capitalize(), "look": HEART_LOOKS.get(n)}
            for n in favorites.hearted_effects()]


def with_hearts(menu):
    """A Swap / Add a look / Lookbook menu with her hearts on it: each tile of a hearted look marked "fav", and the
    whole list under "hearts" for the My favorites filter. Read fresh every time, so a heart from a minute ago shows."""
    h = hearts()
    ids = {x["look"] for x in h if x["look"]}
    for t in menu.get("looks", []):
        if (t.get("base") or t.get("id")) in ids:
            t["fav"] = True
    menu["hearts"] = h
    return menu


def _own_words(jd, layer_name, start, dur):
    """The words a look on this line shows: its own line's words, never the next line's. A look stays on screen a
    beat past its last word (its hold), and that window can reach her next word; taken by the window, the next word
    landed on the look and its real timings were thrown out (the words were then spread evenly, slower than she
    talks). Times stay relative to the look's own start."""
    end = start + dur
    e, _ = _entry(jd, layer_name)
    span = (e or {}).get("span")
    if not span:
        try:
            span = json.load(open(os.path.join(jd, "hf-graphics", "_looks", layer_name, "line.json"), encoding="utf-8")).get("span")
        except Exception:
            span = None
    if span and start - 0.2 <= float(span[1]) <= end:
        end = float(span[1]) + 0.02
    return _line_words(jd, start, end)


def _line_ctx(jd, layer_name):
    """What a look on this line is drawn from: the line, its words and timing, the reel's pack, the open zones."""
    layer, looks = _layer(jd, layer_name)
    pack, note = _swap_pack(jd, looks)
    start, dur = layer["offset"], float(layer["dur"])
    caps = bool(layer.get("captions"))
    words = _line_words(jd, start, start + dur) if caps else _own_words(jd, layer_name, start, dur)
    text = " ".join(w["w"] for w in words).strip() or layer_name
    for b in ([] if caps else looks.get("beats", [])):       # the plan's own on-screen words win when there are some
        if b.get("on_screen") and b.get("start") is not None and abs(float(b["start"]) - start) < max(1.0, dur / 2):
            text = b["on_screen"]; break
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    return layer, looks, pack, note, start, dur, caps, words, text, _zones_at(jd, zones, start, dur)


def _zones_at(jd, zones, start, dur):
    """On a wide video a look clears her head for its own seconds, not where her head usually is."""
    if frame.is_wide(jd):
        head = frame.head_in(jd, float(start or 0), float(dur or 0))
        if head:
            zones = dict(zones or {})
            zones["subject"] = dict(zones.get("subject") or {}, **head)
        grid = frame.brightness_grid(jd, float(start or 0) + float(dur or 0) / 2)
        if grid:
            zones = dict(zones or {}, bg_grid=grid)
    return zones


def grade_of(jd):
    """The filter she picked for this reel (a product/video_grade.py look), or None. Never a default."""
    try:
        g = json.load(open(os.path.join(jd, "review", "grade.json"), encoding="utf-8")).get("look")
    except Exception:
        return None
    import video_grade
    return g if g in video_grade.LOOKS else None


TOUR_FILE = os.path.join(ROOT, "_local", "editor-tour.json")
TOUR_TABS = ("cut", "visuals", "sound", "finish")
_TOUR_LOCK = _threading.Lock()


def tour_seen():
    """{tab: version} of the page tours she finished or skipped. Kept in the engine (_local/, never touched by an
    update), not the browser: the page's address can change (another engine copy took the port, a new browser), and
    the browser forgets with it, so the tour came back on every open. A tour shows again only when its words change."""
    try:
        d = json.load(open(TOUR_FILE, encoding="utf-8")).get("seen") or {}
        return {k: str(v) for k, v in d.items() if k in TOUR_TABS}
    except Exception:
        return {}


def tour_mark(tab, version):
    if tab not in TOUR_TABS or not re.fullmatch(r"[0-9a-z]{1,16}", str(version or "")):
        raise Refuse("That isn't one of the page's tours.")
    with _TOUR_LOCK:                                      # Skip marks every tab at once: four writes, none lost
        seen = tour_seen()
        if seen.get(tab) != version:
            seen[tab] = version
            _atomic_json(TOUR_FILE, {"seen": seen})
    return {"seen": seen}


def set_grade(job, look):
    """Her filter for this reel: one of the five looks, or None to take it off. On the footage only, in the MP4
    export; the CapCut route leaves the look for her to set in CapCut."""
    import video_grade
    jd = job_dir(job)
    if look not in (None, "", "none") and look not in video_grade.LOOKS:
        raise Refuse(f"There's no filter called {look!r}.")
    _atomic_json(os.path.join(jd, "review", "grade.json"), {"look": look if look in video_grade.LOOKS else None})
    reopen_looks(jd)
    looks_manifest(jd)
    return {"grade": grade_of(jd), "looks": list(video_grade.LOOKS)}


def _reel_pack(jd):
    """The pack she switched this reel to on the page (Lookbook > a pack's tab > Use this pack), or None."""
    try:
        return json.load(open(os.path.join(jd, "review", "pack.json"), encoding="utf-8")).get("pack")
    except Exception:
        return None


def _orig_record(jd, L):
    """What one of the reel's own layers IS, when the lookbook drew it (its first build): {look, text, dur, words},
    read from the page's own look.json. A captions layer built in one of the caption styles names its style in its id.
    None for a graphic made by hand for this reel only."""
    import lookbook
    src = L.get("original") or (L.get("dir") if not L.get("look") else None)
    if src:
        try:
            rec = json.load(open(os.path.join(jd, src, "look.json"), encoding="utf-8"))
            if rec.get("look"):
                return rec
        except Exception:
            pass
    if L.get("captions"):
        style = str(L.get("id") or "").split("-", 1)[-1]
        if style in lookbook.CAPTION_LOOKS and style != "takeover":
            return {"look": style, "captions": True}
    return None


def _restyle_original(job, jd, key, rec, pack, prev):
    """One of the reel's own layers, drawn in another pack: the same look, its own words (her hook copy stays her hook
    copy) and its own timing. Marked, so switching back to the reel's pack puts the original back exactly."""
    import lookbook
    if rec.get("captions"):
        set_captions(job, rec["look"])
    else:
        _l, _looks, _pk, _n, _start, _dur, _caps, _words, _text, zones = _line_ctx(jd, key)
        rel = f"hf-graphics/_looks/{key}/{rec['look']}"
        lookbook.draw(rec["look"], os.path.join(jd, rel), rec.get("text") or _text, float(rec.get("dur") or _dur), pack, zones,
                      words=rec.get("words"), comp_id=f"{key}-{rec['look']}", size=rec.get("size"), effect=rec.get("effect"),
                      track=_track_for(jd, lookbook.find(rec["look"], pack), _start, float(rec.get("dur") or _dur)))
        swap(job, key, rec["look"])
    sw = _swaps(jd)
    if key in sw:
        was = (prev or {}).get("was", prev) if (prev or {}).get("restyled") else prev
        sw[key] = dict(sw[key], restyled=True, was=was)
        if (was or {}).get("nudge"):
            sw[key]["nudge"] = was["nudge"]
            _apply_nudge(jd, sw[key]["dir"], was["nudge"])
        _atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": sw, "adds": _adds(jd), "behind": _behind(jd)})


@_locked
@_changes_looks
def _repack_refined(job, jd, key, e):
    """A refined look on this line, drawn again in the reel's new pack with everything the refine set kept: its words,
    size and effect. Her pack switch is her call: a refined look follows it like every other look (2026-10-17: the
    hook stayed in the old pack). Her own image (no pack to wear) stays as it is. True when it was redrawn."""
    try:
        meta = json.load(open(os.path.join(jd, os.path.dirname(str(e.get("dir", ""))), "look.json"), encoding="utf-8"))
    except Exception:
        return False
    look = meta.get("look") or e.get("look")
    if not look or look == "media":
        return False
    try:
        refine(job, key, look, text=meta.get("text"), size=float(meta.get("size") or 1.0), effect=meta.get("effect"))
        refine_apply(job, key, "line")
    except Refuse:
        return False
    return True


def set_pack(job, pack):
    """Switch the whole reel to another style pack, mid-build. Everything that can wear a pack is drawn again in the
    new one, same look, same moment, same words: looks she picked from the lookbook (swapped in, added, her captions),
    her own designs (whatever pack she saved them in), and the reel's own first-build looks (its hook, its captions),
    those with their own words. Switching back to the reel's own pack puts its originals back exactly. Only a graphic
    made by hand for this one reel stays as it was, and the result names it ("kept") so the page can say so."""
    import lookbook, stylepack
    jd = job_dir(job)
    if pack not in stylepack.names():
        raise Refuse(f"There's no style pack called {pack!r} in this engine.")
    _atomic_json(os.path.join(jd, "review", "pack.json"), {"pack": pack, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    looks_manifest(jd)
    ids = {l["id"] for l in lookbook.looks(pack, job=os.path.basename(jd))}
    mine = lambda look: bool(look) and lookbook.design_home(look, pack) is not None   # one of her designs: wears any pack
    redrawn = []
    for key, e in list(_adds(jd).items()):                   # looks she added to a line
        look = e.get("look")
        if look in (None, "_off"):
            continue
        if look not in ids and not mine(look):               # a saved setting of hers that lives in the other pack: stays
            continue
        if "/refined-" in str(e.get("dir", "")):                # refined (her words, size, effect): wears the new pack too
            if _repack_refined(job, jd, key, e):
                redrawn.append(key)
            continue
        span = e.get("span") or [float(e["offset"]) + 0.12, float(e["offset"]) + float(e["dur"]) - 0.35]
        place_look(job, key, span[0], span[1], look); redrawn.append(key)
    for key, e in list(_swaps(jd).items()):                  # looks she swapped in for a line's original
        look = e.get("look")
        if look in (None, "_off", "_original") or e.get("restyled"):
            continue                                         # (a restyled original is redrawn below, with its own words)
        if look not in ids and not mine(look):               # a look of hers saved in the other pack, or an older look: stays
            continue
        if "/refined-" in str(e.get("dir", "")):                # refined (her words, size, effect): wears the new pack too
            if _repack_refined(job, jd, key, e):
                redrawn.append(key)
            continue
        layer, looks, pk, _n, start, dur, caps, words, text, zones = _line_ctx(jd, key)
        l = lookbook.find(look, pk)
        item = _draw_choice(jd, l, f"hf-graphics/_looks/{key}/{l['id']}", f"{key}-{l['id']}", text, dur, pk, zones, words,
                            accents=_look_accents(jd, l, caps, start, start + dur, origin=start), track=_track_for(jd, l, start, dur))
        if not item.get("dir"):
            continue
        swap(job, key, look); redrawn.append(key)
    # the reel's own layers: its first-build looks wear the new pack; back in the reel's own pack, the originals return
    man = _looks_or_fresh(jd)
    sw = _swaps(jd)
    for L in man.get("layers", []):
        key = L["name"]
        if key.startswith(("add-", "cap-")) or key in redrawn or L.get("off"):
            continue
        e = sw.get(key)
        if e and not e.get("restyled") and e.get("look") not in (None, "_original"):
            continue                                         # she swapped this line herself (handled above)
        if "/refined-" in str((e or {}).get("dir", "")):
            continue
        rec = _orig_record(jd, L)
        own = (rec or {}).get("pack") or man.get("built_pack")     # the pack this layer was first made in
        if pack == own:
            if e and e.get("restyled"):                      # back home: exactly what was there before the switch
                sw = _swaps(jd)
                if e.get("was"):
                    sw[key] = e["was"]
                else:
                    sw.pop(key, None)
                _atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": sw, "adds": _adds(jd), "behind": _behind(jd)})
                looks_manifest(jd); redrawn.append(key)
            continue
        if not rec:
            continue
        try:
            _restyle_original(job, jd, key, rec, pack, e)
            redrawn.append(key)
        except Refuse:
            continue
    def _wears(l):                                           # already in this pack (a design or look drawn in it)
        return f"hf-reel-type-{pack.lower()}" in str(l.get("dir", "")) or (_orig_record(jd, l) or {}).get("pack") == pack
    built = [l["name"] for l in _looks_or_fresh(jd).get("layers", [])
             if l["name"] not in redrawn and not l.get("off") and not _wears(l)]
    return {"pack": pack, "redrawn": redrawn, "kept": built}


def _caption_track(jd, start, dur):
    """Centered captions, scene by scene: CAPTION_GAP px under her chin, one locked spot per scene, measured again only
    at a real scene change (product/caption_scenes.py, cached by cut; you 2026-10-17: for everyone using centered
    captions). As the builder's caption_track: [[t0, t1, centre_y]] in this look's own seconds. None = no reading
    (no face model, no preview): the captions keep their one measured spot."""
    p = os.path.join(jd, "review", "caption-scenes.json")
    try:
        cur = hashlib.sha1(open(os.path.join(jd, "transcript", "cuts.json"), "rb").read()).hexdigest()[:10]
        sc = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
        if sc.get("cut_id") != cur:
            import shutil as _sh
            if not _sh.which("uv"):
                return None
            subprocess.run(["uv", "run", os.path.join(ROOT, "product", "caption_scenes.py"), jd], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
            sc = json.load(open(p, encoding="utf-8"))
            if sc.get("cut_id") != cur:
                return None
    except Exception:
        return None
    scenes = _with_caption_moves(jd, sc.get("scenes", []))
    half = 45                                                # the caption's centre sits half a caption under its top
    import lookbook as _lbt                                  # captions show a hair early (CAPTION_LEAD_S): so does each
    lead = _lbt.CAPTION_LEAD_S                               # scene's spot, or a line's first word, shown early, sat at the
    out = [[round(max(0.0, a - lead - start), 3), round(b - lead - start, 3), int(top) + half]   # old scene's height ("because")
           for a, b, top in scenes if b > start and a < start + dur]
    return out or None


def _track_for(jd, l, start, dur):
    """A caption-style look's locked spots (_caption_track); None for any other look. Every draw of a caption look
    passes it: a swap, a refine, a pack switch or a highlight redraw without it put her captions back at the style's
    default height, over her mouth (2026-10-23)."""
    return _caption_track(jd, start, dur) if (l or {}).get("layer") == "captions" else None


def _with_caption_moves(jd, scenes):
    """Her captions moved for one stretch only (review/caption-moves.json {"moves": [[cut_t0, cut_t1, top_px]]}, in
    the scenes' own units): each stretch replaces the scene spot under it, the rest of the reel keeps its spot. For a
    card that sits where her captions do while it plays ("captions on this need to be higher", 2026-10-18); the
    page's caption Move still moves them for the whole reel, on top of this."""
    moves = sorted((_read_json(os.path.join(jd, "review", "caption-moves.json")) or {}).get("moves") or [])
    out = [list(x) for x in scenes]
    for a, b, top in moves:
        cut = []
        for s0, s1, t in out:
            if s1 <= a or s0 >= b:
                cut.append([s0, s1, t]); continue
            if s0 < a:
                cut.append([s0, a, t])
            if s1 > b:
                cut.append([b, s1, t])
        cut.append([float(a), float(b), int(top)])
        out = sorted(cut)
    return out


def caption_move(job, start, end, top):
    """Move her captions to `top` (px, the top of the letters before her whole-reel caption Move) from start to end
    (cut seconds), then redraw them so the page and every export follow."""
    jd = job_dir(job)
    p = os.path.join(jd, "review", "caption-moves.json")
    d = _read_json(p) or {}
    keep = [m for m in d.get("moves") or [] if m[1] <= start or m[0] >= end]
    _atomic_json(p, {"moves": sorted(keep + [[round(float(start), 3), round(float(end), 3), int(top)]])})
    capL = next((l for l in (looks_manifest(jd) or {}).get("layers", []) if l.get("captions")), None)
    if capL and capL.get("look") not in (None, "_original", "_off"):
        set_captions(job, capL["look"])                     # drawn again with the moved stretch (her Move rides along)
    return {"moves": sorted(keep + [[start, end, top]])}


def _draw_choice(jd, l, rel, comp, text, dur, pack, zones, words, accents=None, track=None):
    """One look drawn on one line by the engine's builder (lookbook.py), redrawn only when the line, the pack or
    the builder changed. A look this line can't take (a count-up with no number) comes back with the reason."""
    import lookbook
    d = os.path.join(jd, rel)
    page = os.path.join(d, f"hf-reel-type-{pack.lower()}")
    try:
        old = json.load(open(os.path.join(d, "look.json"), encoding="utf-8"))
    except Exception:
        old = {}
    item = {"id": l["id"], "name": l["name"], "about": l["about"], "kind": l.get("kind"), "from": l.get("from", "pack"),
            "dir": os.path.relpath(page, jd).replace(os.sep, "/"), "comp": comp, "dur": dur}
    base = l.get("base") or l["id"]
    item["base"] = base                                      # her hearts match a saved look by the look it's built on
    # guardrails, not walls: a look that doesn't quite fit this line is still drawn and still hers to use, with a
    # plain warning (a count-up with no number counts to a placeholder she types over in Refine)
    if base == "counter" and not lookbook.number_in(text):
        text, words = "100", None
        item["warn"] = "No number in this line. It counts to 100 until you type yours in Refine."
    try:
        acc = [[a["w"], a["t"]] for a in (accents or [])]
        dsrc = lookbook.design_dir(l.get("home") or pack, l["id"]) if l.get("design") else None
        cap_sz = float(_caption_box(jd).get("size") or 1.0) if l["layer"] == "captions" else None   # her caption size,
        if old.get("text") != lookbook.shown_text(l, text) or old.get("dur") != round(dur, 3) or old.get("pack") != pack or _stale_look(page, dsrc) or (old.get("accents") or []) != acc or (old.get("track") or None) != track \
                or _timing_moved(page, l, text, dur, pack, words) or (cap_sz is not None and round(float(old.get("size") or 1.0), 3) != round(cap_sz, 3)):   # redraw when she changed it
            lookbook.draw(l["id"], d, text, dur, pack, zones, words=words, comp_id=comp, accents=accents, track=track,
                          font_overrides=_resolve_fonts(jd, old.get("fonts")))   # her per-look font override survives every redraw
            for name_, e in list(_swaps(jd).items()) + list(_adds(jd).items()):   # a page in use keeps her changes
                if e.get("dir") != item["dir"]:
                    continue
                if e.get("nudge"):
                    _apply_nudge(jd, e["dir"], e["nudge"])
                try:
                    capL = next((x for x in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]
                                 if x["name"] == name_ and x.get("captions")), None)
                except Exception:
                    capL = None
                if capL and capL.get("skips"):
                    _apply_skips(jd, item["dir"], capL["id"], capL["skips"], offset=capL.get("offset"))
    except lookbook.Refuse as e:
        item.update(unavailable=str(e), dir=None)
        return item
    small = _text_too_small(page, base)
    if not small and l.get("design"):                       # her design: the draw measured its own fitted sizes
        try:
            small = json.load(open(os.path.join(d, "look.json"), encoding="utf-8")).get("warn")
        except Exception:
            small = None
    if small and not item.get("warn"):
        item["warn"] = small
    return item


def _timing_moved(page, l, text, dur, pack, words):
    """True when the look on the page was drawn with other word timings than its line has now: the same words in the
    same pack, but her cut moved them (a sped clip, a word's stamp, a censored word timed for real at last). Read from
    the page's own record of what it was drawn with; a page with no such record is left as it is."""
    import lookbook
    try:
        rec = json.load(open(os.path.join(page, "look.json"), encoding="utf-8"))
        if l.get("design"):
            was = rec.get("said")
            now = lookbook.said_times(lookbook.design_meta(l, pack), text, dur, words)
            return was is not None and (len(was) != len(now) or any(abs(float(a) - b) > 1e-3 for a, b in zip(was, now)))
        was = rec.get("words")
        if was is None:
            return False
        now = lookbook.drawn_words(l if l.get("layer") else lookbook.find(l["id"], pack), text, dur, words)
    except Exception:
        return False
    return len(was) != len(now) or any(a["w"] != b["w"] or abs(float(a["t"]) - float(b["t"])) > 1e-3 or abs(float(a["e"]) - float(b["e"])) > 1e-3
                                       for a, b in zip(was, now))


# the element that carries each look's main words, and the role whose readable floor it must stay above
_MAIN_TEXT = {"hook": (r"\.hkline\{[^}]*?font-size:(\d+)px", "headline"),
              "eyebrow-headline": (r'class="hkhead"[^>]*?font-size:(\d+)px', "headline"),
              "headline-subhead": (r'class="hkhead"[^>]*?font-size:(\d+)px', "headline"),
              "takeover": (r'class="tkwrap"[^>]*?font-size:(\d+)px', "takeover"),
              "breakaway": (r"#bkl\d+\{[^}]*?font-size:(\d+)px", "headline")}


def _text_too_small(page_dir, base):
    """Warn only when the builder had to fit her words below what reads on a phone (safe_zones.MIN_PX for that
    role), measured on the drawing itself. A long line that still fits big gets no warning."""
    if base not in _MAIN_TEXT:
        return None
    try:
        import safe_zones
        html = open(os.path.join(page_dir, "index.html"), encoding="utf-8", errors="replace").read()
        pat, role = _MAIN_TEXT[base]
        sizes = [int(x) for x in re.findall(pat, html)]
        floor = safe_zones.MIN_PX[role]
    except Exception:
        return None
    if sizes and max(sizes) < floor:
        return "Lots of words for this look, so they come out small. Fewer words read bigger."
    return None


def _stale_look(d, design=None):
    """No drawing yet, or one made by an older lookbook (a look's design changed since), or one of her designs saved
    again since this was drawn: draw it again."""
    page = os.path.join(d, "index.html")
    if not os.path.isfile(page):
        return True
    t = os.path.getmtime(page)
    srcs = [os.path.join(ROOT, "product", f) for f in ("lookbook.py", "build-reel-type.py")]
    if design:
        srcs.append(os.path.join(design, "index.html"))
    # her pack changed since this was drawn (a font, a color, in a shipped pack or one of hers in _local/): a Swap or a
    # move reused the old drawing and brought back the old font (a buyer, 2026-10-22). Switching packs was already
    # caught (the record's pack name); this is the same pack, edited. Judged by the pack's own fingerprint, so editing
    # one pack never redraws looks in another; a drawing from before fingerprints is judged by the pack files' times.
    rec = _read_json(os.path.join(d, "look.json"))
    if isinstance(rec, dict) and rec.get("pack"):
        import stylepack
        if rec.get("pack_sig"):
            now = stylepack.signature(rec["pack"])
            if now and now != rec["pack_sig"]:
                return True
        else:
            srcs += [stylepack.SPEC, stylepack.LOCAL_SPEC]
    return any(os.path.isfile(f) and t < os.path.getmtime(f) for f in srcs)


@_locked
def lookbook_view(job, pack=None):
    """Her whole lookbook, each look drawn on one line of THIS reel (its opening words, over her footage, in her
    pack), for the Lookbook button. Read-only: putting a look on a line is Swap, on that line."""
    import lookbook
    jd = job_dir(job)
    looks = _looks_or_fresh(jd)
    import stylepack
    reel, note = _swap_pack(jd, looks)
    pack = pack if pack in stylepack.names() else reel
    if pack != reel:
        note = None
    tw = _line_words(jd, 0, 1e9)
    sample, start = [], tw[0]["t"] if tw else 0.0
    for w in tw:                                             # her first sentence, up to 9 words, ending on a natural break
        sample.append({"w": w["w"], "t": round(w["t"] - start, 3), "e": round(w["e"] - start, 3)})
        if w["w"].rstrip().endswith((".", "!", "?")):
            break
        if len(sample) >= 9:
            cut = max((k for k, x in enumerate(sample[:-1]) if x["w"].rstrip().endswith((",", ";", ":"))), default=None)
            sample = sample[:cut + 1] if cut is not None and cut >= 2 else sample
            break
    text = " ".join(w["w"] for w in sample)
    dur = max(2.6, (sample[-1]["t"] + 0.9) if sample else 3.0)
    # no reel words to borrow (a fresh install): generic filler that says what goes there, never anyone's real words
    FILLER = {"hook": "this is where your hook goes", "eyebrow-headline": "a small line / this is where your hook goes",
              "headline-subhead": "this is your hook / a small line under it", "takeover": "your big moment",
              "breakaway": "your words on a card", "counter": "$1,000", "karaoke": "this is how your captions read",
              "single-word": "one word at a time"}
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    out = []
    import lookbook as _lb
    for l in lookbook.looks(pack, job=os.path.basename(jd)):
        base = l.get("base") or l["id"]
        t_, w_ = (text, sample) if text else (FILLER.get(base, "your words here"), None)
        if base == "counter" and not _lb.number_in(t_):     # the lookbook shows a count-up even when her line has no number
            t_, w_ = FILLER["counter"], None
        sub = "_book" if pack == reel else f"_book/_{re.sub(r'[^a-z0-9]+', '-', pack.lower())}"   # each pack keeps its own drawings
        out.append(_draw_choice(jd, l, f"hf-graphics/_looks/{sub}/{l['id']}", f"book-{l['id']}", t_, dur, pack, zones, w_))
        out[-1]["from"] = l.get("from", "pack")
    frame = next((m.get("frame") for m in looks.get("moments", []) if m.get("frame")), None)
    local = set()                                            # hers: an older local pack, or one pack_write recorded (her
    try:                                                     # DESIGN.md, a Brand Kit brand, /studio recipe, "My Butter")
        local |= set(json.load(open(stylepack.LOCAL_SPEC, encoding="utf-8")).get("packs", {}))
    except Exception:
        pass
    try:
        import pack_persist
        local |= set((pack_persist._load_raw() or {}).get("packs", {}))
    except Exception:
        pass
    mine_default = _default_pack()
    packs = [{"name": n, "reel": n == reel, "mine": n in local, "default": n == mine_default} for n in stylepack.names()]
    return {"pack": pack, "reel_pack": reel, "default_pack": mine_default, "packs": packs, "note": note, "text": text or "your words go here", "frame": frame, "looks": out,
            "requests": [{k: r.get(k) for k in ("id", "words", "idea", "status", "look", "mode")} for r in look_requests(job)]}


def _frame_at(jd, t, key, width=270):
    """A small still of her cut at t (review/at-<key>.jpg) for a menu's tiles; None when there's no cut video."""
    src, at = _still_source(jd, t)
    name = f"at-{re.sub(r'[^A-Za-z0-9_-]', '', key)}.jpg"
    out = os.path.join(jd, "review", name)
    if not src:
        return None
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", "-vf", f"scale={int(width)}:-2",
                        "-q:v", "4", out], capture_output=True, text=True, timeout=60)
    return name if r.returncode == 0 and os.path.isfile(out) else None


def _spot(lookbook, look_id, pack):
    """Where a look sits on screen, coarsely: "top" (hooks), "full" (takeovers, breakaways, full-screen designs),
    "card" (count-ups, cards). Two looks with the same spot at the same moment overlap."""
    try:
        l = lookbook.find(look_id, pack)
    except Exception:
        return None
    k = l.get("kind") or ""
    return {"Hook": "top", "Full screen": "full", "Card": "card", "Captions": "captions"}.get(k)


def _spot_of(jd, L, pack):
    import lookbook
    if L.get("look") and L.get("look") not in ("_original", "_off"):
        return _spot(lookbook, L["look"], pack)
    rec = _orig_record(jd, L)                                # a first-build look: what it is, from its page record
    if rec and rec.get("look"):
        return _spot(lookbook, rec["look"], pack)
    try:                                                     # an older build's own layer: its builder layer says
        lay = (json.load(open(os.path.join(jd, L.get("original") or L["dir"], "meta.json"), encoding="utf-8")) or {}).get("layer")
    except Exception:
        lay = None
    return {"hook": "top", "takeover": "full", "breakaway": "full", "elements": "card"}.get(lay)


# A hook is copy of its own: a reframe she writes (or asks Claude for), never her spoken line on a card. Its tile is
# drawn with her copy when the line already has some, else with a sample that says what goes there.
HOOK_SAMPLE = {"eyebrow-headline": "a small line / your hook, in your words", "headline-subhead": "your hook, in your words / a small line"}
HOOK_SAMPLE_ONE = "your hook, in your words"


def _is_hook(l):
    return (l or {}).get("layer") == "hook"


def _hooky(l):
    """A hook belongs at the reel's opening (line 1): a built-in hook look (layer 'hook') OR one of her own designs
    saved as a Hook (kind 'Hook'), so her Sandbox hook lands on line 1, never the line she happened to build it on."""
    l = l or {}
    return l.get("layer") == "hook" or str(l.get("kind") or "").lower() == "hook"


def _hook_tile(jd, l, rel, comp, dur, pack, zones, copy=None):
    base = l.get("base") or l["id"]
    item = _draw_choice(jd, l, rel, comp, (copy or "").strip() or HOOK_SAMPLE.get(base, HOOK_SAMPLE_ONE), dur, pack, zones, None)
    item.update(copy=True, copy_now=(copy or "").strip(), split=base in HOOK_SAMPLE)
    return item


@_locked
def add_menu(job, key, start, end, kind=None):
    """Every look, drawn on a line that has none yet (key = 'add-<line>'), for the ✦+ button. kind="caption": the
    caption looks only (single word, karaoke, phrase, spotlight, takeover, and her own), for one line's captions."""
    jd = job_dir(job)
    lp = os.path.join(jd, "review", "looks.json")
    if not os.path.isfile(lp):                               # no graphics built yet: her first look starts the list
        looks_manifest(jd)
    looks = json.load(open(lp, encoding="utf-8")) if os.path.isfile(lp) else {}
    pack, note = _swap_pack(jd, looks)
    s0, e0 = float(start), float(end)                       # the line's own words only, never the next sentence's
    start, end = max(0.0, s0 - 0.12), e0 + 0.35
    if kind == "caption":                                    # one line's own captions: on screen only between her lines, so
        t = word_cut_times(jd)                               # the reel's captions (which step aside for this window) never
        before = [b for a, b in t.values() if b <= s0 + 0.01]          # lose the next line's first word, and its last word
        after = [a for a, b in t.values() if a >= e0 - 0.01]           # never sits on screen over the next line's first
        if before:
            start = max(start, max(before) + 0.02)
        if after:
            end = min(end, min(after) - 0.02)
        dur = max(0.3, end - start)
    else:
        dur = max(1.0, end - start)
    words = [w for w in _line_words(jd, start, e0 + 0.02)]
    there, spots = [], {}                                    # several looks on one line is fine: she just hears about it
    for l in looks.get("layers", []):
        lap = min(e0, l["offset"] + (l["dur"] or 0)) - max(s0, l["offset"])          # a real overlap, not neighbours touching
        if kind != "caption" and not l.get("captions") and not l.get("off") and l["name"] != key and lap > 0.4 * max(0.3, e0 - s0):
            rec = None if l.get("look") else _orig_record(jd, l)              # a first-build look says what it is ("Hook")
            nm = l.get("look_name") or (str((rec or {}).get("look") or "").replace("-", " ").capitalize() if rec
                                        else "Your original look" if not l.get("look") else str(l.get("look")).replace("-", " ").capitalize())
            there.append(nm)
            spots.setdefault(_spot_of(jd, l, pack), nm)       # the spot on screen it takes: a same-spot look would overlap it
    text = " ".join(w["w"] for w in words).strip()
    if not text and kind == "caption":
        raise Refuse("That line has no words left in the cut, so there are no captions to put on it.")
    # a quiet line (a pause she kept, no words): only the looks that bring their own words are offered (the hooks,
    # each with its own copy); never a refusal, and never another line's words
    quiet = not text
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    import lookbook
    capl = lambda l: (l.get("base") or l["id"]) in lookbook.CAPTION_LOOKS
    out = []
    for l in lookbook.looks(pack, job=os.path.basename(jd)):
        if not (capl(l) if kind == "caption" else l.get("layer") != "captions" or capl(l)):   # a line's own caption styles too
            continue
        if _is_hook(l):                                      # a hook is its own copy, never her spoken line: a sample here
            out.append(_hook_tile(jd, l, f"hf-graphics/_looks/{key}/_menu/{l['id']}", f"{key}-{l['id']}", dur, pack, zones,
                                  (_entry(jd, key)[0] or {}).get("copy") if key.startswith("add-") else None))
        elif not quiet:
            out.append(_draw_choice(jd, l, f"hf-graphics/_looks/{key}/_menu/{l['id']}", f"{key}-{l['id']}", text, dur, pack, zones, words,
                                    accents=_look_accents(jd, l, capl(l) or l.get("layer") == "captions", s0, e0, origin=start),
                                    track=_track_for(jd, l, start, dur)))   # her highlights, this line's
    for item in out:                                         # a look that lands where one already plays: named, so the page warns
        sp = _spot(lookbook, item["id"], pack)               # (a full-screen look covers everything else on screen with it)
        hit = spots.get(sp) or (next(iter(spots.values())) if sp == "full" and spots else None) or spots.get("full")
        if hit:
            item["clash"] = hit
    cur = _adds(jd).get(key, {})
    # the menu's own line, kept with its tiles: the look on this line keeps its own until she picks a tile (swap)
    _mw = _span_words(jd, s0, e0)
    _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "_menu", "line.json"), {"offset": round(start, 3), "dur": round(dur, 3), "span": [round(s0, 3), round(e0, 3)],
                                                                          "words": _mw, "anchor": _span_anchor(jd, _mw)})
    if kind == "caption":
        json.dump({"kind": "caption"}, open(os.path.join(jd, "hf-graphics", "_looks", key, "kind.json"), "w", encoding="utf-8"))
    if there:
        names = list(dict.fromkeys(there))
        both = f"{names[0]} is already on this line" if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]} are already on this line"
        note = (note + " " if note else "") + f"{both}. A new look plays with {'it' if len(names) == 1 else 'them'}; tap a card's Swap to replace one instead."
    if quiet:
        note = (note + " " if note else "") + "No words here, so the looks that bring their own are offered: write the hook's words, or ask Claude for them."
    return {"layer": key, "offset": start, "dur": dur, "text": text, "quiet": quiet, "pack": pack, "note": note, "add": True, "caption": kind == "caption",
            "current": cur.get("look"), "original": None, "looks": out, "frame": _frame_at(jd, s0 + min(0.6, (e0 - s0) / 2), key)}


def _entry(jd, layer_name):
    """Her swap or add for this layer (the one Move and Refine change), and which list it lives in."""
    if layer_name.startswith(("add-", "cap-")):
        return _adds(jd).get(layer_name), "adds"
    return _swaps(jd).get(layer_name), "swaps"


def _save_entry(jd, layer_name, entry):
    sw, ad = _swaps(jd), _adds(jd)
    (ad if layer_name.startswith(("add-", "cap-")) else sw)[layer_name] = entry
    _atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": sw, "adds": ad, "behind": _behind(jd)})


def _apply_nudge(jd, rel, nudge):
    """Move a look she placed: one style line in ITS page (never her build's own files), read by the render too."""
    page = os.path.join(jd, rel, "index.html")
    if not os.path.isfile(page):
        return
    html_ = open(page, encoding="utf-8").read()
    html_ = re.sub(r'<style id="ve-nudge">.*?</style>', "", html_, flags=re.S)
    n = list(nudge or (0, 0)) + [None] * 4
    dx, dy, sc, rot, ox, oy = n[:6]
    sc = float(sc) if sc not in (None, "") else 1.0
    rot = float(rot) if rot not in (None, "") else 0.0
    if dx or dy or abs(sc - 1) > 1e-3 or abs(rot) > 1e-3:
        # ONE transform, in the order the separate properties would apply (move, then turn, then size, around the look's
        # own center). Never the separate translate/rotate/scale properties: the renderer ignores them, so a look she
        # moved on her page exported where it started (2026-10-16, a count-up moved 867 px down rendered at the top)
        rule = f"transform:translate({int(dx or 0)}px,{int(dy or 0)}px)"
        if abs(sc - 1) > 1e-3 or abs(rot) > 1e-3:
            rule += f" rotate({rot:.2f}deg) scale({sc:.3f});transform-origin:{int(ox if ox is not None else frame.size(jd)[0] / 2)}px {int(oy if oy is not None else frame.size(jd)[1] / 2)}px"
        rule += ";"
        tag = f'<style id="ve-nudge">#root{{{rule}}}</style>'
        html_ = html_.replace("</head>", tag + "</head>", 1) if "</head>" in html_ else tag + html_
    tmp = page + ".tmp"; open(tmp, "w", encoding="utf-8").write(html_); os.replace(tmp, page)


@_locked
def _working_copy(jd, layer_name, L=None):
    """Anything already on her reel can be moved: the first move copies that graphic into her looks folder
    (hf-graphics/_looks/<layer>/_original/) and the move lands on the copy. Her build's own files are never touched;
    the trash puts the untouched original back. `L` = the layer as the list being built has it (a reel's first load,
    before looks.json exists)."""
    if L is None:
        looks = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
        L = next((l for l in looks.get("layers", []) if l["name"] == layer_name), None)
    if not L:
        raise Refuse("That graphic isn't on your reel anymore. Reload the page.")
    src = os.path.join(jd, L["dir"])
    rel = f"hf-graphics/_looks/{layer_name}/_original"
    dst = os.path.join(jd, rel)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("renders", "*.mov", "*.mp4.tmp"))
    _stamp_copy(src, dst)
    e = {"look": "_original", "dir": rel, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_entry(jd, layer_name, e)
    return e


def _stamp_copy(src, dst):
    """Which version of the original her moved copy was made from (its page's mtime), so a later fix to the original
    can reach her copy (_refresh_moved_copy)."""
    try:
        open(os.path.join(dst, ".from-original"), "w", encoding="utf-8").write(repr(os.path.getmtime(os.path.join(src, "index.html"))))
    except OSError:
        pass


def _refresh_moved_copy(jd, orig_rel, copy_rel, nudge):
    """Her moved copy of a section look follows every later fix to its original (your GIF library kept the old
    stop-and-start glide after the original was smoothed, because the copy was made before the fix). When the
    original's page is newer than the copy's stamp, the copy is made again from it and her move is put back on.
    Returns True when it refreshed."""
    src, dst = os.path.join(jd, orig_rel), os.path.join(jd, copy_rel)
    try:
        now = os.path.getmtime(os.path.join(src, "index.html"))
        was = float(open(os.path.join(dst, ".from-original"), encoding="utf-8").read().strip())
    except (OSError, ValueError):
        was, now = None, None
    if was is None or now is None or now <= was + 0.5 or os.path.normpath(src) == os.path.normpath(dst):
        if was is None and now is None and os.path.isdir(dst) and os.path.isfile(os.path.join(src, "index.html")):
            _stamp_copy(src, dst)                            # a copy from before stamps existed: stamp it from here on
        return False
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("renders", "*.mov", "*.mp4.tmp", ".hyperframes", ".reel_render"),
                    dirs_exist_ok=True)
    _stamp_copy(src, dst)
    _apply_nudge(jd, copy_rel, nudge)
    return True


def _apply_accents(jd, rel, toggles, cls, scale):
    """Her highlight changes on the reel's own captions, written into HER copy of the captions page (a small script
    that runs in the live preview and the render alike), so a word she highlighted is highlighted in her export too.
    toggles: [(selector, on, on_as_built)]. The original size is kept on the word, so the preview never scales twice."""
    page = os.path.join(jd, rel, "index.html")
    if not os.path.isfile(page):
        return
    h = open(page, encoding="utf-8").read()
    h = re.sub(r'<script id="ve-accents">.*?</script>', "", h, flags=re.S)
    if toggles and cls:
        data = json.dumps([[sel, bool(on), bool(was)] for sel, on, was in toggles])
        js = ("(function(){var L=" + data + ",c=" + json.dumps(cls) + ",k=" + json.dumps(float(scale or 1)) + ";"
              "L.forEach(function(x){var e=document.querySelector(x[0]);if(!e)return;"
              "var px=parseFloat(e.style.fontSize||getComputedStyle(e).fontSize)||0;if(!e.dataset.vePx)e.dataset.vePx=px;"
              "e.classList.toggle(c,x[1]);if(k!==1&&px&&x[1]!==x[2])e.style.fontSize=Math.round(x[1]?px*k:px/k)+'px';});})();")
        h = h.replace("</body>", f'<script id="ve-accents">{js}</script></body>', 1)
    tmp = page + ".tmp"; open(tmp, "w", encoding="utf-8").write(h); os.replace(tmp, page)


def _merge_spans(spans):
    """Overlapping or touching windows as one: two looks that overlap (a karaoke running into a takeover) must hide the
    captions for both, never let the first one's "show again" bring them back in the middle of the second."""
    out = []
    for a, b in sorted((round(float(a), 3), round(float(b), 3)) for a, b in spans):
        if out and a <= out[-1][1] + 0.001:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _apply_skips(jd, rel, comp_id, skips, offset=0.0):
    """Lines with their own caption look: the reel's captions hide for those windows (a few timeline sets added to
    HER copy of the captions page, read by the live preview and the render alike). `skips` are in reel seconds; the
    page runs on its own clock (0 = the layer's `offset`), so a caption layer that starts after 0:00 (captions added
    at her first word) is shifted by it. Unshifted, every step-aside landed late by the offset (2026-10-17)."""
    off = float(offset or 0)
    skips = [(a - off, b - off) for a, b in (skips or []) if b - off > 0]
    page = os.path.join(jd, rel, "index.html")
    if not os.path.isfile(page):
        return
    h = open(page, encoding="utf-8").read()
    h = re.sub(r'<script id="ve-skips">.*?</script>', "", h, flags=re.S)
    if skips:
        sets = "".join(f'tl.set("#root",{{autoAlpha:0}},{a:.3f});tl.set("#root",{{autoAlpha:1}},{b:.3f});' for a, b in _merge_spans(skips))
        h = h.replace("</body>", f'<script id="ve-skips">(function(){{var tl=(window.__timelines||{{}})["{comp_id}"];if(tl){{{sets}}}}})();</script></body>', 1)
    tmp = page + ".tmp"; open(tmp, "w", encoding="utf-8").write(h); os.replace(tmp, page)


def _keeps_lock(fn):
    """A line edit (split or combine her script lines, or its Undo) is neither a cut change nor a new look: it never
    unlocks her cut or her looks, even when a look on the line is redrawn to follow its words or let go."""
    import functools

    @functools.wraps(fn)
    def run(job, *a, **k):
        ph = os.path.join(job_dir(job), "review", "phase.json")
        was = _phase_now(job_dir(job))
        try:
            return fn(job, *a, **k)
        finally:
            if was is not None and _phase_now(job_dir(job)) != was:
                _atomic_json(ph, was)
    return run


@_keeps_lock
@_locked
def edit_lines(job, op, w, looks=None, drop=None):
    """Split a line before word w, or join the line ending at word w with the next. A look she added on that line
    follows: on a split it keeps the half with its first word; on a join it covers both (looks = the new spans the
    page measured in her cut, drop = the look she chose to let go). Her picks ride along: a look she refined keeps
    its size, its animation and any words she typed; her highlights stay on; her image, GIF or clip keeps its
    entrance, its place and where she moved it. Looks change first, so a look that can't follow leaves her lines
    exactly as they were.
    Returns an undo id: restore_lines(job, id) puts the lines and those looks back exactly."""
    import copy, lookbook
    jd = job_dir(job)
    sp = os.path.join(jd, "review", "script.json")
    script = json.load(open(sp, encoding="utf-8"))
    lines = script["lines"]
    ln = next((n for n, ids in enumerate(lines) if w in ids), None)
    if ln is None:
        raise Refuse("That word isn't in the script anymore. Reload the page.")
    ids = lines[ln]
    if (op == "split" and ids[0] == w) or (op == "join" and (ids[-1] != w or ln + 1 >= len(lines))):
        return {"lines": lines, "undo": None}                # already the way she asked: nothing to change, nothing refused
    adds = _adds(jd)
    kept_as_is = []                                          # looks that can't be redrawn on the new line: they stay as drawn
    looks, drop = looks or [], [d for d in (drop or []) if d in adds]
    looks_obj = _looks_or_fresh(jd)
    pack, _ = _swap_pack(jd, looks_obj)
    plan = []
    for x in looks:                                          # check every look can follow before changing anything
        e = adds.get(x["layer"])
        if not e:
            continue
        if e.get("look") == "media":                         # her own picture or clip: drawn from her file, never the lookbook
            if not media_of(jd, x["layer"]):                 # its file record is gone: her lines regroup, it stays as drawn
                kept_as_is.append(x["layer"]); continue
            plan.append((x["layer"], e, None, float(x["start"]), float(x["end"])))
            continue
        try:
            l = lookbook.find(e["look"], pack)
        except lookbook.Refuse:                              # her lines regroup anyway; that look stays as it was drawn
            kept_as_is.append(x["layer"]); continue
        plan.append((x["layer"], e, l, float(x["start"]), float(x["end"])))
    snap = {"cut_id": script.get("cut_id"), "edits": _line_edits(jd), "lines": copy.deepcopy(lines),
            "adds": {k: copy.deepcopy(adds.get(k)) for k in [p_[0] for p_ in plan] + drop}}
    for key in drop:
        swap(job, key, None)
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    for key, e, l, s0, e0 in plan:                           # the same padding a look gets when it's added
        if l is None:                                        # her picture: exactly its stretch, as place_look draws it
            m = media_of(jd, key)
            start, dur = s0, max(0.6, e0 - s0)
            if m.get("kind") == "Video" and m.get("clip_dur"):
                dur = min(dur, float(m["clip_dur"]))         # a clip runs no longer than itself
            mm, t_ = re.match(r"^(?:add|cap)-w(\d+)", key), word_cut_times(jd)
            if mm and int(mm.group(1)) in t_:                # where it starts within its word, kept for later cut changes
                m["lead"] = round(s0 - t_[int(mm.group(1))][0], 3)
                _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), m)
            try:
                item = _draw_media(jd, key, m.get("media"), dur)   # its entrance, exit and box come from media.json
            except Refuse:                                   # can't be drawn on these words: her lines still regroup, the
                kept_as_is.append(key); continue             # picture stays as it was
            e0 = s0 + dur
        else:
            # a look with its own words (a takeover or hook given copy) keeps them, and on a split it goes to the half
            # where she says them, never just the half with the line's first word (2026-10-21: "doesn't replace the
            # HUMAN" stayed on "AI used the right way" and hid her captions there)
            copy_ = None
            try:
                m0 = json.load(open(os.path.join(jd, os.path.dirname(e["dir"]), "look.json"), encoding="utf-8"))
                sp0 = e.get("span") or [s0, e0]
                said0 = lookbook.shown_text(l, " ".join(x["w"] for x in _line_words(jd, float(sp0[0]), float(sp0[1]) + 0.02)))
                if m0.get("text") and lookbook.shown_text(l, m0["text"]) != said0 and "/refined-" not in str(e.get("dir", "")):
                    copy_ = m0["text"]
            except Exception:
                pass
            if copy_ and op == "split" and w in ids:
                toks_ = lambda s_: re.findall(r"[a-z0-9$%']+", str(s_).lower())
                ct_, t_ = set(toks_(copy_)), word_cut_times(jd)
                halves = [h_ for h_ in (ids[:ids.index(w)], ids[ids.index(w):]) if h_ and all(i_ in t_ for i_ in (h_[0], h_[-1]))]
                rng = [(t_[h_[0]][0], t_[h_[-1]][1]) for h_ in halves]
                ov = [sum(x_ in ct_ for x_ in toks_(" ".join(y["w"] for y in _line_words(jd, a_, b_ + 0.02)))) for a_, b_ in rng]
                if ov and max(ov) > 0:
                    s0, e0 = rng[ov.index(max(ov))]
            start, end = max(0.0, s0 - 0.12), e0 + 0.35
            dur = max(1.0, end - start)
            words = _line_words(jd, start, e0 + 0.02)
            text = " ".join(x["w"] for x in words).strip()
            if not text:
                continue
            if copy_:
                text = copy_
            capish = l.get("layer") == "captions" or os.path.isfile(os.path.join(jd, "hf-graphics", "_looks", key, "kind.json"))
            acc = _look_accents(jd, l, capish, s0, e0, origin=start)   # her highlights stay on it
            tag = f"{l['id']}~{int(round(s0 * 1000))}-{int(round(e0 * 1000))}"
            if "/refined-" in str(e.get("dir", "")):         # her refine is hers: same size, same animation, her own words
                try:
                    meta = json.load(open(os.path.join(jd, os.path.dirname(e["dir"]), "look.json"), encoding="utf-8"))
                except Exception:
                    meta = {}
                sp_ = e.get("span") or [float(e.get("offset") or 0) + 0.12, float(e.get("offset") or 0) + float(e.get("dur") or 0) - 0.35]
                said = lookbook.shown_text(l, " ".join(x["w"] for x in _line_words(jd, float(e.get("offset") or 0), float(sp_[1]) + 0.02)))
                if meta.get("text") and lookbook.shown_text(l, meta["text"]) != said:
                    text = meta["text"]                      # words she typed in Refine stay her words
                rel = f"hf-graphics/_looks/{key}/refined-{tag}"   # still "refined": a pack switch or retime never redraws it plain
                try:
                    r = lookbook.draw(l["id"], os.path.join(jd, rel), text, dur, pack, zones, words=words, comp_id=f"{key}-{l['id']}",
                                      size=meta.get("size"), effect=meta.get("effect"), accents=acc, track=_track_for(jd, l, start, dur))
                except lookbook.Refuse:                      # her lines still regroup; her refined look stays as drawn
                    kept_as_is.append(key); continue
                item = {"dir": os.path.relpath(r["dir"], jd).replace(os.sep, "/")}
            else:
                # its own folder per stretch of words, so Undo finds the drawing it had, exactly as it was
                item = _draw_choice(jd, l, f"hf-graphics/_looks/{key}/{tag}", f"{key}-{l['id']}", text, dur, pack, _zones_at(jd, zones, s0, dur), words, accents=acc,
                                    track=_track_for(jd, l, start, dur))
            if not item.get("dir"):                          # can't be drawn on these words: her lines still regroup, the
                kept_as_is.append(key); continue             # look stays as it was
        if e.get("nudge"):
            _apply_nudge(jd, item["dir"], e["nudge"])
        wds = _span_words(jd, s0, e0)
        anc = _span_anchor(jd, wds)
        _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "line.json"), {"offset": round(start, 3), "dur": round(dur, 3), "span": [round(s0, 3), round(e0, 3)], "words": wds, "anchor": anc})
        e.update(offset=round(start, 3), dur=round(dur, 3), dir=item["dir"], span=[round(s0, 3), round(e0, 3)], words=wds, anchor=anc)
        _save_entry(jd, key, e)
    ed = _line_edits(jd)
    if op == "split":
        prev = ids[ids.index(w) - 1]
        if prev in ed["join"]:
            ed["join"].remove(prev)
        else:
            ed["split"].append(w)
        lines[ln:ln + 1] = [ids[:ids.index(w)], ids[ids.index(w):]]
    else:
        nxt = lines[ln + 1][0]
        if nxt in ed["split"]:
            ed["split"].remove(nxt)
        else:
            ed["join"].append(w)
        lines[ln:ln + 2] = [ids + lines[ln + 1]]
    _atomic_json(os.path.join(jd, "review", "lines.json"), ed)
    script["lines"] = lines
    _atomic_json(sp, script)
    looks_manifest(jd)
    try:
        timeline_assets(jd, script)                          # a new line gets its own still on the timeline
    except Exception:
        pass
    out = {"lines": lines, "undo": _remember_lines(jd, snap)}
    if kept_as_is:
        out["said"] = (f"{len(kept_as_is)} look{'s' if len(kept_as_is) > 1 else ''} on this line stay{'' if len(kept_as_is) > 1 else 's'} "
                       "as drawn (it couldn't be redrawn on the new words). Swap it anytime.")
    return out


def _remember_lines(jd, snap):
    """Keep a split/combine's 'before' so Undo can put it back (the last 40 of them)."""
    import secrets
    path = os.path.join(jd, "review", "lines-history.json")
    try:
        hist = json.load(open(path, encoding="utf-8"))
    except Exception:
        hist = {}
    sid = secrets.token_hex(4)
    hist[sid] = snap
    for k in list(hist)[:-40]:
        hist.pop(k)
    _atomic_json(path, hist)
    return sid


@_keeps_lock
@_locked
def restore_lines(job, sid):
    """Undo (or redo) a split or combine: her lines and the looks on them, exactly as they were. Hands back the id
    that undoes this in turn."""
    jd = job_dir(job)
    try:
        snap = json.load(open(os.path.join(jd, "review", "lines-history.json"), encoding="utf-8"))[sid]
    except Exception:
        raise Refuse("That change can't be undone anymore. Use Split or Combine instead.")
    sp = os.path.join(jd, "review", "script.json")
    script = json.load(open(sp, encoding="utf-8"))
    if snap.get("cut_id") != script.get("cut_id"):
        raise Refuse("Your cut changed since then, so that can't be undone. Use Split or Combine instead.")
    adds = _adds(jd)
    now = {"cut_id": script.get("cut_id"), "edits": _line_edits(jd), "lines": script["lines"],
           "adds": {k: adds.get(k) for k in snap["adds"]}}
    for k, v in snap["adds"].items():
        if v is None:
            adds.pop(k, None)
        else:
            adds[k] = v
            if v.get("dir") and not os.path.isfile(os.path.join(jd, v["dir"], "index.html")):
                raise Refuse("A look from before is gone from the reel's folder, so that can't be undone.")
            if v.get("look") == "media" and media_of(jd, k) and v.get("dur") is not None:
                m_, mm = media_of(jd, k), re.match(r"^(?:add|cap)-w(\d+)", k)
                t_ = word_cut_times(jd)
                if mm and int(mm.group(1)) in t_ and v.get("span"):
                    m_["lead"] = round(float(v["span"][0]) - t_[int(mm.group(1))][0], 3)
                    _atomic_json(os.path.join(jd, "hf-graphics", "_looks", k, "media.json"), m_)
                _draw_media(jd, k, m_.get("media"), float(v["dur"]))   # her picture: one page, back to its old length
            _atomic_json(os.path.join(jd, "hf-graphics", "_looks", k, "line.json"),   # its words and where they played come
                         {kk: v[kk] for kk in ("offset", "dur", "span", "words", "anchor") if v.get(kk) is not None})   # back too
    _atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": _swaps(jd), "adds": adds, "behind": _behind(jd)})
    _atomic_json(os.path.join(jd, "review", "lines.json"), snap["edits"])
    script["lines"] = snap["lines"]
    _atomic_json(sp, script)
    looks_manifest(jd)
    try:
        timeline_assets(jd, script)
    except Exception:
        pass
    return {"lines": script["lines"], "undo": _remember_lines(jd, now)}


# ── "Build a new look": her idea from the page, workshopped in the chat ──────────────────────────────────────────
def _span_anchor(jd, wds):
    """Where a look's first and last words play in her cut right now: kept with the look, so a cut change moves it
    by exactly how far its words moved (her own start and length kept), however many times it's retimed."""
    if not wds:
        return None
    t = word_cut_times(jd)
    if wds[0] not in t:
        return None
    return [round(t[wds[0]][0], 3), round(t[wds[-1]][0], 3) if wds[-1] in t else None]


def _span_words(jd, s0, e0):
    """[first, last] word index (her script's) of a stretch of her cut, so a look can follow its words."""
    t = word_cut_times(jd)
    inside = sorted((v[0], i) for i, v in t.items() if s0 - 0.05 <= v[0] <= e0 + 0.02)
    return [inside[0][1], inside[-1][1]] if inside else None


def _requests_path(jd):
    return os.path.join(jd, "review", "look-requests.json")


def _requests(jd):
    return _read_state(_requests_path(jd), "ideas").get("requests") or []


@_locked
def new_look_request(job, w, start, end, text, mode="build", at=None, media=None):
    """She said what she's picturing. Kept for the chat (`build my look` for one line; `sandbox` for three quick
    sketches she picks from on the page). A sandbox idea needs no line: she names the lines or the moment in her
    own words, and her playhead travels with it ("right here")."""
    import secrets
    jd = job_dir(job)
    text = str(text or "").strip()[:1000]
    if not text:
        raise Refuse("Tell me what you're picturing first, in a few words.")
    sandbox = mode == "sandbox"
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if w is None and not sandbox:
        raise Refuse("Pick the line it goes on first.")
    if w is not None and not 0 <= int(w) < len(script["words"]):
        raise Refuse("That line isn't in the script anymore. Reload the page.")
    rid = secrets.token_hex(3)
    ph = round(float(at), 3) if at is not None else None
    if w is not None:
        s0, e0 = float(start), float(end)
    else:                                                    # where she was looking, for the still and as a fallback
        s0 = ph or 0.0; e0 = s0 + 2.0
    words = " ".join(x["w"] for x in _line_words(jd, s0 - 0.05, e0 + 0.02)).strip()
    req = {"id": rid, "w": int(w) if w is not None else None, "start": round(s0, 3), "end": round(e0, 3), "words": words,
           "idea": text, "frame": _frame_at(jd, s0 + min(0.6, (e0 - s0) / 2), f"req-{rid}", width=540), "status": "open",
           "mode": "sandbox" if sandbox else "build", "round": 1,
           **({"media": media} if media and media_path(media) else {}),   # her own image or GIF, to build it around
           **({"playhead": ph} if ph is not None else {}),   # her playhead when she asked ("at this moment")
           "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if sandbox:                                              # one sandbox at a time
        for r in _requests(jd):
            if r.get("mode") != "sandbox" or r.get("status") not in ("open", "takes"):
                continue
            if (r.get("idea") == text and r.get("media") == req.get("media")
                    and r.get("w") == req["w"]):                 # the same idea sent again (Back, then Send): it's the one
                return r                                     # she has, sketches and all, never a fresh start
            why = _sandbox_in_play(r)
            if why:                                          # never thrown away to make room: sketches Claude made,
                raise Refuse(why)                            # a build under way, or her picture
            sandbox_drop(job, r["id"])                       # an idea nobody has started on yet: the new one replaces it
        reqs = _requests(jd) + [req]
    else:
        reqs = [r for r in _requests(jd) if r.get("status") != "open" or r.get("w") != req["w"]] + [req]   # one idea per line
    _atomic_json(_requests_path(jd), {"requests": reqs[-30:]})
    looks_manifest(jd)                                       # a reload still shows "your idea is saved"
    return req


def _sandbox_in_play(r):
    """Why her open Sandbox idea can't simply be replaced by a new one, in her words, or None when it can. Replacing
    it used to drop it with no word: sketches already in her Sandbox were deleted, a build Claude was on was thrown
    away, and a GIF she picked with an idea vanished when she picked the next one (2026-10-23)."""
    idea = re.sub(r"\s+", " ", str(r.get("idea") or "")).strip()
    idea = f"“{idea[:60]}{'…' if len(idea) > 60 else ''}”"
    if r.get("status") == "takes" and r.get("takes"):
        return (f"Your sketches for {idea} are still waiting in your Sandbox. Open Sandbox to lock one in or tap Cancel "
                "this idea, then send the new one. To change those sketches, use Remix.")
    if r.get("working"):
        return (f"Claude is building sketches for {idea} right now. Once they land, lock one in or cancel that idea, "
                "then send the new one.")
    if r.get("media"):
        return (f"Your Sandbox idea {idea} and its picture are still waiting for Claude: type sandbox in your Claude "
                "chat, or open Sandbox and tap Cancel this idea. To put a picture straight on your reel, leave the "
                "words box empty and tap Add it.")
    return None


def look_requests(job, open_only=True):
    jd = job_dir(job)
    return [r for r in _requests(jd) if not open_only or r.get("status") in ("open", "draft", "takes")]


@_locked
def place_look(job, key, start, end, look_id, copy=None):
    """Put ONE look (one of the ten, one she saved, or one of her designs) on a stretch of her cut: drawn there and
    swapped in, the same as picking it from Swap. How a workshop draft shows up on her reel, live on the page."""
    import lookbook
    jd = job_dir(job)
    if not re.match(r"^(add|cap)-[A-Za-z0-9_-]{1,40}$", key):
        raise Refuse("That isn't a line's look.")
    try:
        looks = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    except FileNotFoundError:                                # the first look on a fresh reel: no list yet, the reel's pack decides
        looks = {"pack": _reel_pack(jd)}
    pack, _ = _swap_pack(jd, looks)
    s0, e0 = float(start), float(end)
    st, en = max(0.0, s0 - 0.12), e0 + 0.35
    dur = max(1.0, en - st)
    # THE YIELD RULE: a look that shows her words (a takeover, a caption style) owns exactly its own words: it is gone
    # before the next word she says, and her reel captions step aside for exactly that window and are back on that
    # next word. Its tail never runs into the next line (2026-10-17: a takeover ran into "Let me show you").
    try:
        _lk = lookbook.find(look_id, pack)
    except Exception:
        _lk = {}
    if _lk.get("layer") in ("takeover", "captions") or (_lk.get("base") or _lk.get("id")) in lookbook.CAPTION_LOOKS:
        _t = word_cut_times(jd).values()
        nxt = [a for a, b in _t if a >= e0 - 0.01]
        if nxt and min(nxt) - 0.02 < en:
            en = max(e0, min(nxt) - 0.02)
        # and it starts on its own first word: the look before it ends at that same moment, so two word looks hand
        # off back to back and never overlap (a 0.12 s lead-in reached back into the look before)
        # ...and it starts as early as her captions show that word (they lead her voice by CAPTION_LEAD_S), so a word
        # never flashes in the caption style before the look takes it over ("own" showed twice, 2026-10-17)
        st = max(0.0, s0 - 0.02 - lookbook.CAPTION_LEAD_S)
        dur = max(0.3, en - st)
    if os.path.isfile(os.path.join(jd, "hf-graphics", "_looks", key, "kind.json")):   # a line's own captions: only between
        t = word_cut_times(jd)                               # her lines, never over the next line's first word
        before = [b for a, b in t.values() if b <= s0 + 0.01]
        after = [a for a, b in t.values() if a >= e0 - 0.01]
        if before:
            st = max(st, max(before) + 0.02)
        if after:
            en = min(en, min(after) - 0.02)
        dur = max(0.3, en - st)
    words = _line_words(jd, st, e0 + 0.02)
    text = " ".join(x["w"] for x in words).strip()
    if not (copy or "").strip():                             # a redraw (pack switch, cut change) keeps the copy it was given
        copy = _kept_copy(jd, key, look_id, _lk, pack)
    if not text and not (copy or "").strip():                # a look with its own words can sit in a quiet stretch:
        own = lookbook.own_words(_lk, pack) if look_id != "media" else None   # a design whose words are its note
        if own is None and look_id != "media":               # (a Sandbox sketch's handles), or one with no words at all
            raise Refuse("That line has no words left in the cut, so there's nothing to put a look on.")
        text = own or ""
    if copy and copy.strip():                                # a hook's own copy (a reframe), timed over her words
        text = copy.strip()
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    if look_id == "media":                                   # her own image or GIF, drawn from her favorites file
        m = media_of(jd, key)
        if not m:
            raise Refuse("That image isn't saved with this line anymore. Add it again from Image.")
        st, dur = s0, max(0.6, e0 - s0)                      # exactly its stretch: pictures one after another never overlap
        _draw_media(jd, key, m["media"], dur)
        _mw = _span_words(jd, s0, e0)
        _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "line.json"), {"offset": round(st, 3), "dur": round(dur, 3), "span": [round(s0, 3), round(e0, 3)],
                                                                              "words": _mw, "anchor": _span_anchor(jd, _mw)})
        return dict(swap(job, key, "media"), warn=None)
    l = lookbook.find(look_id, pack)
    capish = l.get("layer") == "captions" or os.path.isfile(os.path.join(jd, "hf-graphics", "_looks", key, "kind.json"))
    zones = _zones_at(jd, zones, start, dur)
    item = _draw_choice(jd, l, f"hf-graphics/_looks/{key}/{l['id']}", f"{key}-{l['id']}", text, dur, pack, zones, words,
                        accents=_look_accents(jd, l, capish, s0, e0, origin=st),   # her highlights ride along: pack switch, cut change
                        track=_caption_track(jd, st, dur) if l.get("layer") == "captions" else None)
    if not item.get("dir"):
        raise Refuse(item.get("unavailable") or "That look couldn't be drawn on this line.")
    _mw = _span_words(jd, s0, e0)
    _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "line.json"), {"offset": round(st, 3), "dur": round(dur, 3), "span": [round(s0, 3), round(e0, 3)],
                                                                          "words": _mw, "anchor": _span_anchor(jd, _mw)})
    out = swap(job, key, l["id"])
    if not _mw and key.startswith("add-"):                   # a look in a quiet stretch (no words under it): anchored to
        _t = word_cut_times(jd)                              # the word she said just before it, at the same gap, so a cut
        _prev = max(((b, w) for w, (a, b) in _t.items() if b <= s0 + 0.01), default=None)   # change carries it along
        e, _ = _entry(jd, key)
        if _prev and e is not None:
            _save_entry(jd, key, dict(e, after_word=int(_prev[1]), gap=round(s0 - _prev[0], 3)))
    if copy and copy.strip():                                # remembered with the look, so every later redraw keeps it
        e, _ = _entry(jd, key)
        if e is not None and e.get("copy") != copy.strip():
            _save_entry(jd, key, dict(e, copy=copy.strip()))
    return dict(out, warn=item.get("warn"))


def _kept_copy(jd, key, look_id, look, pack):
    """The copy a look drawn on this slot keeps when it's given none: the copy saved there with the SAME look (a pack
    switch, a cut change), or a hook's reframe going to another hook (it was written for the line). A swap to any
    other look leaves the old look's copy behind (2026-10-21: a line swapped from her checklist to a handwritten line
    still showed the checklist's "the setup")."""
    import lookbook
    was = (_entry(jd, key)[0] or {}) if key.startswith("add-") else {}
    if not was.get("copy"):
        return None
    if was.get("look") == look_id:
        return was["copy"]
    try:
        was_hook = was.get("look") not in (None, "_off", "_original", "media") and _is_hook(lookbook.find(was["look"], pack))
    except Exception:
        was_hook = False
    return was["copy"] if was_hook and _is_hook(look) else None


def _free_add_key(jd, first, look_id=None):
    """The slot for a new look on the line that starts at word `first`: add-w<first>, or add-w<first>-2, -3 ... when
    that line already carries another look, so the new one plays WITH it instead of replacing it. The same look
    placed again on its own slot keeps that slot (a redraw, not a second copy)."""
    adds = _adds(jd)
    key, k = f"add-w{first}", 2
    while key in adds and (look_id is None or adds[key].get("look") != look_id):
        key, k = f"add-w{first}-{k}", k + 1
    return key


@_changes_looks
@_locked
def place_at(job, look_id, start, end, copy=None):
    """Put a lookbook look (or one of hers) on a stretch of her cut, by cut seconds: keyed by its first word, so it
    follows her words through every later cut change, and drawn exactly as the page draws it. The page-path build.
    A HOOK look Claude places carries its own copy (`copy`): a punchy reframe written to WRITING-THE-HOOK.md, never
    her spoken sentence copied onto the card (CLAUDE.md: never mirror her opener). Without it, nothing is drawn.
    (Her own Swap on the page is her call and is never held to this.)"""
    import lookbook
    jd = job_dir(job)
    try:
        _lk = lookbook.find(look_id, _reel_pack(jd))
        layer = _lk.get("layer")
    except Exception:
        _lk, layer = {}, None
    if layer == "hook" and not (copy or "").strip():
        raise Refuse(f"{look_id} is a hook: write its own copy (a punchy reframe, workflows/capcut-export/WRITING-THE-HOOK.md, "
                     "never her spoken line) and pass it with --text \"eyebrow / headline\". Nothing was drawn.")
    if _hooky(_lk):                                           # a hook always lands at the reel's opening (line 1), never the
        sp = _whole_cut_span(jd)                             # mid-reel line it was built on (CLAUDE.md: hook = line 1)
        if sp:
            end = float(sp[0]) + max(1.0, float(end) - float(start)); start = float(sp[0])
    times = word_cut_times(jd)
    s0 = float(start)
    first = min((w for w, (a, b) in times.items() if b > s0 + 0.02), key=lambda w: times[w][0], default=None)
    if first is None:
        raise Refuse("There are no words at that time in her cut.")
    out = place_look(job, _free_add_key(jd, first, look_id), s0, float(end), look_id, copy=copy)
    if layer == "hook":
        return _hook_language(jd, copy, out)[0]
    try:                                                     # a heading design given no heading wears the one it was saved
        lk = lookbook.find(look_id, _reel_pack(jd))          # with, from another reel: said, so this reel's can be written
        meta = lookbook.design_meta(lk, lk.get("home") or _reel_pack(jd))
    except Exception:
        meta = {}
    if lookbook.has_heading(meta) and not lookbook.split_heading(copy, meta)[0]:
        note = (f"Its heading says \"{str(meta.get('note') or '').strip()}\", the one it was saved with. For this reel's own, "
                "pass --text \"heading / her words\".")
        out = dict(out or {}, warn=" ".join(x for x in ((out or {}).get("warn"), note) if x))
    return out


def _hook_language(jd, copy, out):
    """(out, note): a hook's copy in English on a reel she speaks in another language is said in `warn`, and the
    copy stays exactly as written (her click is final; a bilingual reel can mean it). plan_language owns the call."""
    try:
        import plan_language
        note = plan_language.hook_note(jd, copy)
    except Exception:
        note = None
    if not note:
        return out, None
    out = dict(out or {})
    out["warn"] = " ".join(x for x in (out.get("warn"), note) if x)
    return out, note


# ── her own images and GIFs, as overlays on a line ───────────────────────────────────────────────────────────────
# The page's Image button lists her favorites drawers (gifs / graphics / photos) as thumbnails; a tap puts that file on
# the line as an overlay on top of her footage (look id "media": a card she can swap, move or remove, that follows its
# words like any look). A GIF is made into a looping clear video, because a GIF animates on its own clock and the
# render seeks every frame; a still image pops in and out. "Tell Claude what it should do" turns it into a Sandbox idea
# with the file attached (build-a-look), whose kept sketch can go to her lookbook like any sandbox.
# A VIDEO is a b-roll cutaway: it fills the frame for its words while her voice keeps playing (muted unless she turns
# its sound on), plays the clip's best moment (broll-select's scorer), and she slips it to another moment or moves
# its start and end a word at a time (cutaway_set). Videos come from her favorites' broll drawer and her inbox only:
# a .mov in graphics is a see-through graphic, never a cutaway.
MEDIA_EXT = {".gif": "GIF", ".png": "Image", ".jpg": "Image", ".jpeg": "Image", ".webp": "Image"}
VIDEO_EXT = {".mp4": "Video", ".mov": "Video", ".m4v": "Video"}
VIDEO_DRAWERS = ("broll",)
MEDIA_DRAWERS = ("gifs", "graphics", "photos") + VIDEO_DRAWERS
MEDIA_MAX_BYTES = 40_000_000
VIDEO_MAX_BYTES = 200_000_000
CUTAWAY_MIN = 0.6                                              # a cutaway shorter than this reads as a glitch
CUTAWAY_EFFECTS = [("cut", "Cut"), ("fade", "Fade")]


def _media_kind(path, drawer):
    """Image / GIF / Video for a file in that drawer ("inbox" for her inbox), or None when the picker can't place it."""
    ext = os.path.splitext(path)[1].lower()
    if ext in MEDIA_EXT:
        return MEDIA_EXT[ext]
    if ext in VIDEO_EXT and drawer in VIDEO_DRAWERS + ("inbox",):
        return VIDEO_EXT[ext]
    return None


def is_video(media_id):
    return os.path.splitext(str(media_id or ""))[1].lower() in VIDEO_EXT
# How a picture comes in, in her words. Text entrances move words a few pixels, which reads as nothing on a picture,
# so these travel for real: the slides start fully outside the frame (measured from where the picture sits) and leave
# the way they came. None = the gentle pop it starts with.
MEDIA_EFFECTS = [("pop", "Pop"), ("slide-left", "Slide in from the left"), ("slide-right", "Slide in from the right"),
                 ("drop", "Drop in from the top"), ("rise", "Rise from the bottom"), ("spin", "Spin in"),
                 ("zoom", "Zoom in"), ("wiggle", "Pop and wiggle"), ("fade", "Fade"), ("slow-zoom", "Slow zoom")]


MEDIA_EXITS = [("slide-left", "Slide out to the left"), ("slide-right", "Slide out to the right"),
               ("slide-up", "Slide out the top"), ("slide-down", "Slide out the bottom"), ("fade", "Fade out")]


def _media_exit(exit, box, end, dx=0, fw=1080, fh=1920):
    """The GSAP line for how her image leaves when she picked its exit apart from its entrance ("slide out at the
    word revenue"). "slide" alone goes out the nearer side. Starts 0.12s before `end`, like the slide entrances."""
    if exit == "slide":
        exit = "slide-right" if box["left"] + box["w"] / 2 + dx >= fw / 2 else "slide-left"
    off = {"slide-left": f"x:{-(box['left'] + box['w'] + 80 + max(0, dx))}", "slide-right": f"x:{fw - box['left'] + 80 - min(0, dx)}",
           "slide-up": f"y:{-(box['top'] + box['h'] + 80)}", "slide-down": f"y:{fh - box['top'] + 80}"}.get(exit)
    if not off:
        return f'tl.to("#media",{{autoAlpha:0,scale:0.96,duration:0.26,ease:"power2.in",immediateRender:false}},{end:.3f});'
    return f'tl.to("#media",{{{off},duration:0.4,ease:"power3.in",immediateRender:false}},{max(0.4, end - 0.12):.3f});'


def _media_moves(effect, box, end, fw=1080, fh=1920):
    """(entrance, exit) GSAP lines for #media. `box` is where it sits on the 1080x1920 frame; `end` when it leaves."""
    # far enough to start fully outside the frame even after she moved it or made it up to 4x bigger
    off_l, off_r = -(box["left"] + box["w"] * 4 + fw), fw - box["left"] + box["w"] * 3 + fw
    off_t, off_b = -(box["top"] + box["h"] * 4 + fh), fh - box["top"] + box["h"] * 3 + fh
    # a short stretch: the entrance shrinks to fit (at most 60% of the time before it starts leaving), so it lands
    # and reads before it goes; a 0.85s drop on a one-second GIF met its own exit mid-air and never showed
    room = max(0.15, end - 0.2)
    fit = lambda d: round(min(d, max(0.15, room * 0.6)), 3)
    ft = lambda frm, to, d, ease: f'tl.fromTo("#media",{{autoAlpha:0,{frm}}},{{autoAlpha:1,{to},duration:{fit(d)},ease:"{ease}",immediateRender:false}},0.08);'
    out_fade = f'tl.to("#media",{{autoAlpha:0,scale:0.96,duration:0.26,ease:"power2.in",immediateRender:false}},{end:.3f});'
    out_to = lambda prop: f'tl.to("#media",{{{prop},duration:0.4,ease:"power3.in",immediateRender:false}},{max(0.4, end - 0.12):.3f});'
    if effect == "slide-left":
        return (f'tl.fromTo("#media",{{autoAlpha:1,x:{off_l}}},{{autoAlpha:1,x:0,duration:{fit(0.6)},ease:"back.out(1.1)",immediateRender:false}},0.08);', out_to(f"x:{off_l}"))
    if effect == "slide-right":
        return (f'tl.fromTo("#media",{{autoAlpha:1,x:{off_r}}},{{autoAlpha:1,x:0,duration:{fit(0.6)},ease:"back.out(1.1)",immediateRender:false}},0.08);', out_to(f"x:{off_r}"))
    if effect == "drop":
        return (f'tl.fromTo("#media",{{autoAlpha:1,y:{off_t}}},{{autoAlpha:1,y:0,duration:{fit(0.85)},ease:"bounce.out",immediateRender:false}},0.08);', out_to(f"y:{off_t}"))
    if effect == "rise":
        return (f'tl.fromTo("#media",{{autoAlpha:1,y:{off_b}}},{{autoAlpha:1,y:0,duration:{fit(0.65)},ease:"back.out(1.2)",immediateRender:false}},0.08);', out_to(f"y:{off_b}"))
    if effect == "spin":
        return (ft("rotation:-200,scale:0.1", "rotation:0,scale:1", 0.7, "back.out(1.5)"), out_fade)
    if effect == "zoom":
        return (ft("scale:2.4", "scale:1", 0.5, "power3.out"), out_fade)
    if effect == "wiggle":
        return (ft("scale:0.4", "scale:1", 0.45, "back.out(2.2)")
                + 'tl.to("#media",{keyframes:[{rotation:-7,duration:0.09},{rotation:6,duration:0.09},{rotation:-4,duration:0.08},'
                  f'{{rotation:3,duration:0.08}},{{rotation:0,duration:0.08}}],ease:"sine.inOut",immediateRender:false}},{0.1 + fit(0.45):.3f});', out_fade)
    if effect == "fade":
        return (ft("scale:1", "scale:1", 0.45, "power1.out"), out_fade)
    if effect == "slow-zoom":
        return (ft("scale:0.9", "scale:1", 0.4, "power2.out")
                + f'tl.to("#media",{{scale:1.14,duration:{max(0.4, end - 0.5):.3f},ease:"sine.inOut",immediateRender:false}},{0.1 + fit(0.4):.3f});', out_fade)
    return (ft("scale:0.4", "scale:1", 0.45, "back.out(2.2)"), out_fade)   # pop


def _favorites():
    return os.path.join(ROOT, "favorites")


def favorite_path(media_id):
    """Her favorites file for an id ("gifs/Name.gif"), only inside her favorites drawers and only an image or GIF."""
    rel = str(media_id or "").replace("\\", "/").strip("/")
    p = os.path.realpath(os.path.join(_favorites(), rel))
    root = os.path.realpath(_favorites())
    if not p.startswith(root + os.sep) or rel.split("/")[0] not in MEDIA_DRAWERS:
        raise Refuse("That file isn't in your favorites.")
    if not _media_kind(p, rel.split("/")[0]) or not os.path.isfile(p):
        raise Refuse("That file isn't an image, GIF or video in your favorites anymore.")
    return p


def inbox_path(media_id):
    """A one-off file in her inbox ("inbox:<path in inbox>"), only inside her inbox and only an image or GIF."""
    rel = str(media_id or "")[len("inbox:"):].replace("\\", "/").strip("/")
    root = os.path.realpath(os.path.join(ROOT, "inbox")); p = os.path.realpath(os.path.join(root, rel))
    if not str(media_id or "").startswith("inbox:") or not p.startswith(root + os.sep):
        raise Refuse("That file isn't in your inbox.")
    if not _media_kind(p, "inbox") or not os.path.isfile(p):
        raise Refuse("That file isn't an image, GIF or video in your inbox anymore.")
    return p


def media_path(media_id):
    """Her favorites file, or a one-off from her inbox."""
    return inbox_path(media_id) if str(media_id or "").startswith("inbox:") else favorite_path(media_id)


def media_poster(media_id):
    """A still of her clip for its tile in the Media picker, made once and kept in _local/ (a phone clip is often HEVC
    or HDR, which a browser can't always draw as a thumbnail). Images are their own thumbnail."""
    src = media_path(media_id)
    if not is_video(src):
        return src
    st = os.stat(src)
    d = os.path.join(ROOT, "_local", "media-posters"); os.makedirs(d, exist_ok=True)
    out = os.path.join(d, hashlib.sha1(f"{src}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:20] + ".jpg")
    if not os.path.isfile(out):
        try:
            from hdr import HDR2SDR, hdr_kind
            pre = f"{HDR2SDR}," if hdr_kind(src) else ""
        except Exception:
            pre = ""
        at = min(1.0, max(0.0, _clip_len(src) / 3))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", f"{pre}scale=240:-2", "-q:v", "4", out + ".part.jpg"], capture_output=True, timeout=60)
        if os.path.isfile(out + ".part.jpg"):
            os.replace(out + ".part.jpg", out)
    return out if os.path.isfile(out) else None


def inbox_media(job=None):
    """Images and GIFs sitting in her inbox (and one folder down), and b-roll clips loose in her inbox or in a b-roll
    folder (inbox/b-roll/, and inbox/b-roll/grabs/ where b-roll prep puts them), newest first: one-offs she doesn't
    keep. A clip in any other folder is her talking footage waiting to be edited, never offered as b-roll, except the
    folder she filled this reel from (Fill with my b-roll), which is her b-roll here (listed first)."""
    root, out = os.path.join(ROOT, "inbox"), []
    try:
        folder = _fill_folder(job_dir(job)) if job else None
    except Refuse:
        folder = None
    if folder:
        out = _folder_clips(folder)
    for d, subs, files in os.walk(root) if os.path.isdir(root) else []:
        rel_d = os.path.relpath(d, root)
        depth = 0 if rel_d == "." else rel_d.count(os.sep) + 1
        broll_dir = depth == 0 or any(re.sub(r"[\s_-]", "", p.lower()) == "broll" for p in rel_d.split(os.sep))
        if depth >= 2:
            subs[:] = []
        subs[:] = [x for x in subs if not x.startswith(".") and (depth == 0 or re.sub(r"[\s_-]", "", x.lower()) in ("broll", "grabs"))]
        for f in files:
            kind = _media_kind(f, "inbox")
            if kind == "Video" and not broll_dir or kind != "Video" and depth >= 2:
                continue
            if kind and not f.startswith("."):
                p = os.path.join(d, f); rel = os.path.relpath(p, root).replace(os.sep, "/")
                if any(x["id"] == "inbox:" + rel for x in out):
                    continue
                out.append({"id": "inbox:" + rel, "name": re.sub(r"\s+(GIF|gif)\b.*$", "", os.path.splitext(f)[0]).strip() or os.path.splitext(f)[0],
                            "kind": kind, "drawer": "inbox", "at": os.path.getmtime(p)})
    first = {x["id"] for x in _folder_clips(folder)} if folder else set()
    out.sort(key=lambda x: (x["id"] not in first, -x["at"]))
    return out


def favorite_media():
    """Her images, GIFs and b-roll clips, newest first, for the Media picker."""
    out = []
    for d in MEDIA_DRAWERS:
        folder = os.path.join(_favorites(), d)
        for f in os.listdir(folder) if os.path.isdir(folder) else []:
            kind = _media_kind(f, d)
            if kind and not f.startswith("."):
                p = os.path.join(folder, f)
                out.append({"id": f"{d}/{f}", "name": re.sub(r"\s+(GIF|gif)\b.*$", "", os.path.splitext(f)[0]).strip() or os.path.splitext(f)[0],
                            "kind": kind, "drawer": d, "at": os.path.getmtime(p)})
    out.sort(key=lambda x: -x["at"])
    return out


def _drawer_for(ext):
    return ("broll" if ext in VIDEO_EXT else "gifs" if ext == ".gif" else "photos" if ext in (".jpg", ".jpeg")
            else "graphics")


def favorite_upload(name, data):
    """A file she dropped on the picker: saved into the right favorites drawer (a copy; never sent anywhere)."""
    import base64
    name = os.path.basename(str(name or "")).strip()
    ext = os.path.splitext(name)[1].lower()
    if ext not in MEDIA_EXT and ext not in VIDEO_EXT:
        raise Refuse("That isn't an image, GIF or video. PNG, JPG, WebP, GIF, MP4 or MOV work.")
    raw = base64.b64decode(str(data or "").split(",", 1)[-1])
    cap = VIDEO_MAX_BYTES if ext in VIDEO_EXT else MEDIA_MAX_BYTES
    if not raw or len(raw) > cap:
        raise Refuse(f"That file is too big to add here ({cap // 1_000_000} MB at most).")
    drawer = _drawer_for(ext)
    folder = os.path.join(_favorites(), drawer); os.makedirs(folder, exist_ok=True)
    stem, k, dst = re.sub(r"[^\w .()&'-]+", "", os.path.splitext(name)[0]).strip() or "image", 2, None
    dst = os.path.join(folder, stem + ext)
    while os.path.exists(dst):
        dst = os.path.join(folder, f"{stem} ({k}){ext}"); k += 1
    with open(dst, "wb") as fh:
        fh.write(raw)
    return next(x for x in favorite_media() if x["id"] == f"{drawer}/{os.path.basename(dst)}")


def favorite_keep(media_id):
    """An inbox one-off she decided to keep: a copy goes into the right favorites drawer (her inbox file stays)."""
    src = inbox_path(media_id)
    ext = os.path.splitext(src)[1].lower()
    drawer = _drawer_for(ext)
    folder = os.path.join(_favorites(), drawer); os.makedirs(folder, exist_ok=True)
    stem, k = os.path.splitext(os.path.basename(src))[0], 2
    dst = os.path.join(folder, os.path.basename(src))
    while os.path.exists(dst):
        dst = os.path.join(folder, f"{stem} ({k}){ext}"); k += 1
    shutil.copy2(src, dst)
    return next(x for x in favorite_media() if x["id"] == f"{drawer}/{os.path.basename(dst)}")


def _media_size(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", path], capture_output=True, text=True, timeout=30)
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
        return w, h
    except Exception:
        return 1, 1


def _media_box(jd, w, h):
    """Where her image sits by default: under her chin and above her captions, centered, inside the safe area, never
    on her face (subject-zones.json). She moves it with Move; the page's checks say if it lands on something."""
    import safe_zones
    if frame.is_wide(jd):                                     # a wide video: centered in the frame, above her captions
        sc = min(900 / max(w, 1), 620 / max(h, 1))
        bw, bh = int(w * sc), int(h * sc)
        return {"left": 960 - bw // 2, "top": max(60, 480 - bh // 2), "w": bw, "h": bh}
    top, cap_top = 1060, 1290                                 # the band between her chin and her captions (1080 x 1920)
    try:
        z = json.load(open(os.path.join(jd, "subject-zones.json"), encoding="utf-8"))
        top = max(int(z.get("subject", {}).get("chin_bottom", top)) + 30, safe_zones.TOP)
    except Exception:
        pass
    room_h = max(220, min(520, cap_top - top))
    sc = min(620 / max(w, 1), room_h / max(h, 1))
    bw, bh = int(w * sc), int(h * sc)
    return {"left": 540 - bw // 2, "top": top, "w": bw, "h": bh}


# ── b-roll cutaways: her clip over her footage, full frame, her voice going on underneath ─────────────────────────────
def _clip_len(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=30)
        return max(0.0, float(r.stdout.strip()))
    except Exception:
        return 0.0


def _cutaway_dims(jd):
    """Her cut's own frame size, so a cutaway matches her footage pixel for pixel in the export (1080x1920 before
    there is a cut). Always even, always 9:16-shaped like the cut it sits on."""
    try:
        from probe import display_dims
        w, h = display_dims(os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4"))
        if w and h:
            return int(w) // 2 * 2, int(h) // 2 * 2
    except Exception:
        pass
    return 1080, 1920


def _hw_decode():
    """Reading her phone clip on the Mac's own video chip (several times faster than the processor for a 4K HEVC
    clip). Every caller retries without it if a clip refuses. Elsewhere nothing changes."""
    import platform
    return ["-hwaccel", "videotoolbox"] if platform.system() == "Darwin" else []


def _cutaway_source(jd, key, src, made=None, window=None):
    """Her clip, once, as a copy kept with this reel: upright (a phone clip's rotation applied), standard color (an
    iPhone HDR clip converted), filled to her cut's frame, 30 fps, its own sound kept so she can turn it on. Returns the
    copy's path, relative to the reel. `window` (start, length) in her clip's seconds keeps only that stretch (the
    moment it plays plus room to slip either side): a long phone clip is made in a fraction of the time. None keeps
    the whole clip. `made`: a copy already made for this reel (a b-roll fill makes them all at once, side by side),
    copied as it is instead of made again."""
    w, h = _cutaway_dims(jd)
    keep = os.path.join(jd, "assets", "media"); os.makedirs(keep, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "-", os.path.splitext(os.path.basename(src))[0]).strip("-") or "clip"
    dst = os.path.join(keep, f"{key}-{stem}.mp4"); tmp = dst + ".part.mp4"
    if made and os.path.isfile(os.path.join(jd, made)):
        if os.path.realpath(os.path.join(jd, made)) != os.path.realpath(dst):
            shutil.copy2(os.path.join(jd, made), tmp); os.replace(tmp, dst)
        return os.path.relpath(dst, jd).replace(os.sep, "/")
    try:
        from hdr import HDR2SDR, hdr_kind
        pre = f"{HDR2SDR}," if hdr_kind(src) else ""
    except Exception:
        pre = ""
    vf = f"{pre}scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps=30,setsar=1,format=yuv420p"
    cut = ["-ss", f"{window[0]:.3f}", "-t", f"{window[1]:.3f}"] if window else []   # seek BEFORE -i: no decoding up to it
    try:
        from video_encoder import pick_encoder, software_encoder, is_hardware
        venc = pick_encoder(vbr="20M", crf=16)               # the Mac's own video chip: several times faster
    except Exception:
        venc, is_hardware, software_encoder = ["-c:v", "libx264", "-crf", "16", "-preset", "veryfast"], (lambda v: False), None
    run = lambda enc, dec: subprocess.run(["ffmpeg", "-v", "error", "-y", *dec, *cut, "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                                           "-vf", vf, *enc, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                                           "-movflags", "+faststart", tmp], capture_output=True, text=True, timeout=1800)
    r = run(venc, _hw_decode())
    if r.returncode != 0 and _hw_decode():                   # a clip the video chip won't read: the processor reads it
        r = run(venc, [])
    if r.returncode != 0 and is_hardware(venc) and software_encoder:   # a hardware encoder that refuses: the software one
        r = run(software_encoder(16, "veryfast"), [])
    if r.returncode != 0 or not os.path.isfile(tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        raise Refuse("That clip couldn't be read. Try another one, or tell me in the chat.")
    os.replace(tmp, dst)
    return os.path.relpath(dst, jd).replace(os.sep, "/")


def _best_slip(path, dur, clip):
    """The clip's best moment for a cutaway this long: sharp, well lit, no flicker, something happening (the same
    scorer the voiceover route uses on b-roll, product/broll-select.py). A clip it can't read starts in its middle."""
    room = max(0.0, clip - dur)
    if room <= 0.05:
        return 0.0
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("broll_select", os.path.join(ROOT, "product", "broll-select.py"))
        bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(bs)
        picks = bs.pick_clip_windows(path, bs.extract_frames(path), clip, max(0.5, dur), per_clip=1, allow_flicker=True)
        if picks:
            return round(max(0.0, min(room, float(picks[0]["t"]))), 2)
    except Exception:
        pass
    return round(room / 2, 2)


def _cutaway_span(jd, s0, e0, clip):
    """How long the cutaway runs on her words: the stretch she put it on, ending on a word, never longer than the clip
    (it ends on the last word that still fits) and never shorter than CUTAWAY_MIN."""
    if e0 - s0 <= clip + 0.01:
        return s0, max(e0, s0 + CUTAWAY_MIN)
    ends = sorted(b for a, b in word_cut_times(jd).values() if s0 + CUTAWAY_MIN <= b <= s0 + clip + 0.01)
    return s0, (ends[-1] if ends else s0 + clip)


def _draw_cutaway(jd, key, dur, effect=None, page=None):
    """The cutaway's page: the window of her clip it plays (cut exactly, so the page, the MP4 and CapCut all play the
    same frames), full frame, over her footage; with its own sound only when she turned it on, set under her voice."""
    m = media_of(jd, key) or {}
    src = os.path.join(jd, m.get("file") or "")
    if not m.get("file") or not os.path.isfile(src):
        raise Refuse("That clip isn't saved with this line anymore. Add it again from Media.")
    clip = float(m.get("clip_dur") or _clip_len(src))
    dur = max(0.2, min(float(dur), clip))
    slip = round(max(0.0, min(float(m.get("slip") or 0), max(0.0, clip - dur))), 3)
    effect = effect if effect in dict(CUTAWAY_EFFECTS) else m.get("effect") if m.get("effect") in dict(CUTAWAY_EFFECTS) else "cut"
    sound = bool(m.get("sound"))
    page = page or os.path.join(jd, "hf-graphics", "_looks", key, "media", "hf-reel-type-media")
    os.makedirs(os.path.join(page, "assets"), exist_ok=True)
    for f in os.listdir(os.path.join(page, "assets")):
        os.remove(os.path.join(page, "assets", f))
    out = os.path.join(page, "assets", "media.mp4")
    win = ["ffmpeg", "-v", "error", "-y", "-ss", f"{slip:.3f}", "-i", src, "-t", f"{dur:.3f}", "-map", "0:v:0",
           "-c:v", "libx264", "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    gain = None
    if sound:                                                # her clip's own sound, under her voice (audio_levels)
        raw = out + ".raw.mp4"
        r = subprocess.run(win[:-2] + ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", raw],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not os.path.isfile(raw):
            raise Refuse("That clip couldn't be cut. Try again, or tell me in the chat.")
        has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                    "-of", "csv=p=0", raw], capture_output=True, text=True).stdout.strip()
        if not has_audio:                                    # a clip filmed without sound: nothing to turn up
            os.replace(raw, out)
        else:
            try:
                import audio_levels as al
                gain = al.cutaway_gain_for(raw, os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4"))
            except Exception:
                gain = -12.0
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                                "-af", f"volume={gain:.1f}dB", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out],
                               capture_output=True, text=True, timeout=600)
            os.remove(raw)
    else:
        r = subprocess.run(win[:-2] + ["-an", "-movflags", "+faststart", out], capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.isfile(out):
        raise Refuse("That clip couldn't be cut. Try again, or tell me in the chat.")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{min(dur / 2, 0.5):.2f}", "-i", out, "-frames:v", "1",   # its block on
                    "-vf", "scale=-2:120", "-q:v", "5", os.path.join(page, "assets", "poster.jpg")],         # the b-roll lane
                   capture_output=True, timeout=60)
    comp = f"{key}-media"
    if effect == "fade":
        intro = 'tl.fromTo("#media",{autoAlpha:0},{autoAlpha:1,duration:0.25,ease:"power1.out",immediateRender:false},0);'
        outro = f'tl.to("#media",{{autoAlpha:0,duration:0.25,ease:"power1.in",immediateRender:false}},{max(0.25, dur - 0.25):.3f});'
    else:                                                    # a cutaway is a cut: on with her word, off with her word
        intro, outro = 'tl.set("#media",{autoAlpha:1},0);', f'tl.set("#media",{{autoAlpha:0}},{dur:.3f});'
    _fw, _fh = frame.size(jd)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width={_fw}, height={_fh}"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:{_fw}px;height:{_fh}px;overflow:hidden;background:transparent;}}
#root{{position:absolute;inset:0;}}
#media{{position:absolute;left:0;top:0;width:{_fw}px;height:{_fh}px;opacity:0;visibility:hidden;background:#000;}}
</style></head>
<body>
<div id="root" data-composition-id="{comp}" data-start="0" data-duration="{dur:.3f}" data-width="{_fw}" data-height="{_fh}">
<div id="media" data-layout-allow-overlap><video id="mv" class="clip" src="assets/media.mp4" muted playsinline data-start="0" data-duration="{dur:.3f}" data-track-index="1" style="width:100%;height:100%;object-fit:cover"></video></div>
</div>
<script>
window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});
{intro}
{outro}
tl.set("#media",{{autoAlpha:0}},{dur + 0.001:.3f});
window.__timelines["{comp}"]=tl;
</script>
</body></html>"""
    open(os.path.join(page, "index.html"), "w", encoding="utf-8").write(html)
    tpl = os.path.join(ROOT, "product", "templates", "hf-reel")
    for f in ("hyperframes.json", "package.json"):
        if os.path.isfile(os.path.join(tpl, f)):
            shutil.copy(os.path.join(tpl, f), os.path.join(page, f))
    _atomic_json(os.path.join(page, "meta.json"), {"id": comp, "name": "reel-type", "layer": "elements"})
    _atomic_json(os.path.join(page, "look.json"), {"look": "media", "media": m.get("media"), "video": True, "dur": round(dur, 3),
                                                   "box": {"left": 0, "top": 0, "w": frame.size(jd)[0], "h": frame.size(jd)[1]}, "effect": effect,
                                                   "slip": slip, "sound": sound, "gain_db": gain})
    return {"dir": os.path.relpath(page, jd).replace(os.sep, "/")}


def cutaway_file(jd, layer_dir):
    """The finished window of a cutaway, for the export: its page's own clip (None for anything that isn't one)."""
    try:
        lj = json.load(open(os.path.join(jd, layer_dir, "look.json"), encoding="utf-8"))
    except Exception:
        return None
    f = os.path.join(jd, layer_dir, "assets", "media.mp4")
    return f if lj.get("video") and os.path.isfile(f) else None


def _draw_media(jd, key, media_id, dur, effect=None, page=None):
    """The overlay's page: her file over her footage, coming in the way she picked (Refine), timed to the line."""
    m = media_of(jd, key) or {}
    if m.get("kind") == "Video" or is_video(media_id):
        return _draw_cutaway(jd, key, dur, effect=effect, page=page)
    kept = m.get("file")                                         # a one-off from her inbox is kept with the reel itself
    src = os.path.join(jd, kept) if kept and os.path.isfile(os.path.join(jd, kept)) else media_path(media_id)
    effect = effect if effect is not None else m.get("effect")
    if effect and effect not in dict(MEDIA_EFFECTS):
        effect = None
    ext = os.path.splitext(src)[1].lower()
    page = page or os.path.join(jd, "hf-graphics", "_looks", key, "media", "hf-reel-type-media")
    os.makedirs(os.path.join(page, "assets"), exist_ok=True)
    for f in os.listdir(os.path.join(page, "assets")):
        os.remove(os.path.join(page, "assets", f))
    w, h = _media_size(src)
    box = m.get("box")                                         # where it was placed stays where it was placed: her size
    if not box:                                                # and turn are set against this box, so a new face reading
        try:                                                   # (or anything else) never resizes a picture already on her reel
            lj = json.load(open(os.path.join(jd, "hf-graphics", "_looks", key, "media", "hf-reel-type-media", "look.json"),
                                encoding="utf-8"))
            box = lj.get("box") if lj.get("media") == media_id else None   # that same picture's box, never an old one's
        except Exception:
            box = None
        box = box or _media_box(jd, w, h)
        if m:
            _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), dict(m, box=box))
    comp = f"{key}-media"
    if ext == ".gif":                                        # a looping clear video, seeked frame by frame like any clip
        out = os.path.join(page, "assets", "media.webm")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}", "-c:v", "libvpx-vp9",
                            "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-deadline", "realtime", "-cpu-used", "8", "-an", out],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not os.path.isfile(out):
            raise Refuse("That GIF couldn't be made into a clip. Try another one, or tell me in the chat.")
        media = (f'<video id="mv" class="clip" src="assets/media.webm" muted playsinline data-start="0" data-duration="{dur:.3f}" '
                 f'data-track-index="1" style="width:100%;height:100%;object-fit:contain"></video>')
    else:
        shutil.copy(src, os.path.join(page, "assets", "media" + ext))
        media = f'<img id="mv" src="assets/media{ext}" alt="" style="width:100%;height:100%;object-fit:contain"/>'
    end = max(0.6, dur - 0.32)
    _fw, _fh = frame.size(jd)
    intro, outro = _media_moves(effect or "pop", box, end, _fw, _fh)   # no pick yet = Pop, exactly what Refine names it
    if m.get("exit") in dict(MEDIA_EXITS) or m.get("exit") == "slide":   # she picked how it leaves, apart from how it came in
        a = _adds(jd).get(key) or {}
        outro = _media_exit(m["exit"], box, end, dx=float((a.get("nudge") or [0])[0] or 0), fw=_fw, fh=_fh)
    _fw, _fh = frame.size(jd)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width={_fw}, height={_fh}"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:{_fw}px;height:{_fh}px;overflow:hidden;background:transparent;}}
#root{{position:absolute;inset:0;}}
#media{{position:absolute;left:{box['left']}px;top:{box['top']}px;width:{box['w']}px;height:{box['h']}px;filter:drop-shadow(0 12px 30px rgba(0,0,0,.28));opacity:0;visibility:hidden;}}
#media img,#media video{{border-radius:18px;}}
</style></head>
<body>
<div id="root" data-composition-id="{comp}" data-start="0" data-duration="{dur:.3f}" data-width="{_fw}" data-height="{_fh}">
<div id="media" data-layout-allow-overlap>{media}</div>
</div>
<script>
window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});
{intro}
{outro}
tl.set("#media",{{autoAlpha:0}},{min(dur, end + 0.28):.3f});
window.__timelines["{comp}"]=tl;
</script>
</body></html>"""
    open(os.path.join(page, "index.html"), "w", encoding="utf-8").write(html)
    tpl = os.path.join(ROOT, "product", "templates", "hf-reel")
    for f in ("hyperframes.json", "package.json"):
        if os.path.isfile(os.path.join(tpl, f)):
            shutil.copy(os.path.join(tpl, f), os.path.join(page, f))
    _atomic_json(os.path.join(page, "meta.json"), {"id": comp, "name": "reel-type", "layer": "elements"})
    _atomic_json(os.path.join(page, "look.json"), {"look": "media", "media": media_id, "dur": round(dur, 3), "box": box, "effect": effect})
    return {"dir": os.path.relpath(page, jd).replace(os.sep, "/")}


def media_of(jd, key):
    try:
        return json.load(open(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), encoding="utf-8"))
    except Exception:
        return None


@_changes_looks
@_locked
def media_exit(job, key, exit, at=None):
    """How her image leaves, apart from how it came in, and optionally WHEN: `at` is a moment in her cut (a word she
    named: "slide out at the word revenue"), so the image starts leaving as she says it. Its entrance, its place and
    where she moved it stay as they are."""
    jd = job_dir(job)
    m = media_of(jd, key)
    if not m:
        raise Refuse("There's no image on that line.")
    if m.get("kind") == "Video":
        raise Refuse("A clip cuts away and back. Move where it ends from its own sheet (Refine), a word at a time.")
    if exit not in dict(MEDIA_EXITS) and exit != "slide":
        raise Refuse("That isn't a way out: " + ", ".join(dict(MEDIA_EXITS)) + ", or slide.")
    a = _adds(jd).get(key)
    if not a or a.get("offset") is None or a.get("dur") is None:   # never guess its time: a missing entry put it at 0:00
        raise Refuse("That image's place on your reel couldn't be read just now, so nothing changed. Try again in a moment.")
    m["exit"] = exit
    _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), m)
    start = float(a.get("offset", 0))                        # a picture plays exactly its stretch: it keeps its start
    end = float(a.get("offset", 0)) + float(a.get("dur", 1))
    if at is not None:                                       # its page starts the exit 0.44s before the stretch ends
        end = float(at) + 0.44                               # (dur - 0.32 - 0.12), so it starts leaving on her word
    if end <= start + 0.9:                                   # her moment, as close as it can be: it leaves right after it lands
        end = start + 0.91
    nudge = a.get("nudge")
    out = place_look(job, key, start, end, "media")
    if nudge:                                                # where she moved it stays
        e = _adds(jd).get(key)
        if e and e.get("nudge") != nudge:
            e["nudge"] = nudge
            _save_entry(jd, key, e)
            _apply_nudge(jd, e["dir"], nudge)
    return out


CUTAWAY_KEEP_S = 30.0    # a clip longer than this is kept as a window around its moment, not whole (making it is the slow part)
CUTAWAY_ROOM_S = 6.0     # room to slip kept either side of that moment


def _window_for(clip_len, at, dur):
    """The stretch of her clip to keep for a cutaway playing `dur` seconds from `at`: the moment plus room either side,
    the whole clip when it's short anyway. (start, length) in her clip's seconds, or None for the whole clip."""
    if clip_len <= CUTAWAY_KEEP_S:
        return None
    t0, t1 = max(0.0, at - CUTAWAY_ROOM_S), min(clip_len, at + dur + CUTAWAY_ROOM_S)
    return round(t0, 3), round(max(t1 - t0, 0.5), 3)


@_changes_looks
@_locked
def place_media(job, start, end, media_id, made=None, slip=None, window=None):
    """Her image or GIF on a line, as an overlay: keyed by the line's first word like every look, so it follows her
    words through cut changes. It plays WITH whatever else is on that line."""
    jd = job_dir(job)
    src = media_path(media_id)                               # refuses anything outside her favorites or her inbox
    times = word_cut_times(jd)
    s0 = float(start)
    first = min((w for w, (a, b) in times.items() if b > s0 + 0.02), key=lambda w: times[w][0], default=None)
    if first is None:
        raise Refuse("There are no words at that time in her cut.")
    key = _free_add_key(jd, first, None)
    os.makedirs(os.path.join(jd, "hf-graphics", "_looks", key), exist_ok=True)
    name = next((x["name"] for x in favorite_media() + inbox_media() if x["id"] == media_id), os.path.basename(media_id))
    rec = {"media": media_id, "name": name, "kind": _media_kind(src, "inbox" if media_id.startswith("inbox:") else media_id.split("/")[0]),
           "lead": round(s0 - times[first][0], 3)}         # where it starts within its word: "one after another" keeps its turn
    e0 = float(end)
    if rec["kind"] == "Video":                               # a cutaway: her clip, upright and in her cut's frame
        whole = _clip_len(src)
        if window is None and slip is None and whole > CUTAWAY_KEEP_S:   # a long clip from Media: its best moment first,
            slip = _best_slip(src, e0 - s0, whole)           # then only the stretch around it is made
        if window is None and slip is not None:
            window = _window_for(whole, float(slip), e0 - s0)
        rec["file"] = _cutaway_source(jd, key, src, made, window)
        rec["src_in"] = window[0] if window else 0.0         # where the kept copy starts in her clip
        rec["clip_dur"] = round(_clip_len(os.path.join(jd, rec["file"])), 3)
        if rec["clip_dur"] < 0.3:
            raise Refuse("That clip is too short to cut away to.")
        s0, e0 = _cutaway_span(jd, s0, e0, rec["clip_dur"])
        if slip is not None:                                 # the moment she (or Claude) chose, in her clip's own seconds
            rec["best"] = rec["slip"] = round(max(0.0, min(float(slip) - rec["src_in"], rec["clip_dur"] - (e0 - s0))), 3)
        else:
            rec["best"] = rec["slip"] = _best_slip(os.path.join(jd, rec["file"]), e0 - s0, rec["clip_dur"])
        rec.update(sound=False, effect="cut")                # muted under her voice until she turns it on
        _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), rec)
        return place_look(job, key, s0, e0, "media")
    # a copy lives with this reel, named for its line: clearing her inbox, renaming a favorite or two files that share
    # a name ("IMG_2199.jpg" in two inbox folders) never changes or loses a picture already on her reel
    keep = os.path.join(jd, "assets", "media"); os.makedirs(keep, exist_ok=True)
    dst = os.path.join(keep, f"{key}-{os.path.basename(src)}"); shutil.copy2(src, dst)
    rec["file"] = os.path.relpath(dst, jd).replace(os.sep, "/")
    _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), rec)
    return place_look(job, key, s0, e0, "media")


@_changes_looks
@_locked
def cutaway_set(job, key, slip=None, start=None, end=None, sound=None, effect=None, best=False):
    """Her changes to one b-roll cutaway, in one go: `slip` (which moment of her clip plays, in seconds into the clip;
    where it sits and how long it runs stay), `start`/`end` (where it sits on her cut, in cut seconds: the page steps
    them a word at a time), `sound` (her clip's own sound on or off), `effect` (cut or fade), `best` (back to the
    engine's pick of the clip's best moment, for the length it runs now). Where she moved it stays."""
    jd = job_dir(job)
    m = media_of(jd, key)
    if not m or m.get("kind") != "Video":
        raise Refuse("There's no clip on that line.")
    a = _adds(jd).get(key)
    if not a or a.get("offset") is None or a.get("dur") is None:   # never guess its time: a missing entry put it at 0:00
        raise Refuse("That clip's place on your reel couldn't be read just now, so nothing changed. Try again in a moment.")
    clip = float(m.get("clip_dur") or _clip_len(os.path.join(jd, m.get("file") or "")))
    s0 = float(start) if start is not None else float(a["offset"])
    e0 = float(end) if end is not None else float(a["offset"]) + float(a["dur"])
    said = None                                              # her length, as near as her clip allows: never a refusal
    if e0 - s0 < CUTAWAY_MIN - 0.01:
        e0 = s0 + CUTAWAY_MIN; said = f"A cutaway runs at least {CUTAWAY_MIN:g} s, so it's that long."
    if e0 - s0 > clip + 0.05:
        e0 = s0 + clip; said = f"Your clip is {clip:.1f} s long, so it runs the whole clip."
    if start is not None or end is not None:
        times = word_cut_times(jd)
        edge = 0.02                                          # a word that ends right on her edge is still inside
        if not any(s0 - edge <= w0 and w1 <= e0 + edge or w0 <= s0 < w1 for w0, w1 in times.values()):
            raise Refuse("There are no words there in your cut.")
    dur = e0 - s0
    if best:
        m["slip"] = _best_slip(os.path.join(jd, m["file"]), dur, clip)
        m["best"] = m["slip"]
    elif slip is not None:
        m["slip"] = round(max(0.0, min(float(slip), max(0.0, clip - dur))), 3)
    else:                                                    # a new length keeps her moment where it fits
        m["slip"] = round(max(0.0, min(float(m.get("slip") or 0), max(0.0, clip - dur))), 3)
    if sound is not None:
        m["sound"] = bool(sound)
    if effect is not None:
        if effect not in dict(CUTAWAY_EFFECTS):
            raise Refuse("A cutaway comes in as a cut or a fade.")
        m["effect"] = effect
    if start is not None:                                    # its start, from its line's first word (follows cut changes)
        mm = re.match(r"^(add|cap)-w(\d+)", key)
        times = word_cut_times(jd)
        if mm and int(mm.group(2)) in times:
            m["lead"] = round(s0 - times[int(mm.group(2))][0], 3)
    _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), m)
    nudge = a.get("nudge")
    out = place_look(job, key, s0, e0, "media")
    if nudge:                                                # where she moved it stays
        e = _adds(jd).get(key)
        if e and e.get("nudge") != nudge:
            e["nudge"] = nudge
            _save_entry(jd, key, e)
            _apply_nudge(jd, e["dir"], nudge)
    return dict(out, slip=m["slip"], sound=m["sound"], effect=m.get("effect", "cut"), start=round(s0, 3), end=round(e0, 3), **({"said": said} if said else {}))


# ── a voiceover on the editor: her voice is the cut, her b-roll is the picture ─────────────────────────────────────
# A voiceover recording goes through the rough cut like any clip: vo_start lays it on a black 9:16 picture (raw/vo.mp4),
# so the Cut tab trims her words exactly as it trims a Yap and her phone shows a blank screen. voiceover.json marks the
# reel. On Visuals she picks an inbox folder of her clips (and can say what she wants): broll_fill_request leaves that
# for Claude, who watches the clips (broll-prep), matches them to her lines by meaning and lays them on with broll_fill,
# one b-roll cutaway after another so the picture never goes black. Each one is an ordinary cutaway: she slips, trims
# or swaps it, and Media still puts any clip on any line by hand.
VO_AUDIO_EXT = (".m4a", ".mp3", ".wav", ".aac", ".caf")
VO_PACES = ("punchy", "emotional")
VO_GAP_MIN = 0.25                                            # a stretch with no clip shorter than this is never said


def voiceover_of(jd):
    """voiceover.json for a voiceover reel ({"audio", "pace", "folder", ...}), or None for every other reel."""
    try:
        d = json.load(open(os.path.join(jd, "voiceover.json"), encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _vo_save(jd, **kw):
    d = dict(voiceover_of(jd) or {}, **kw)
    _atomic_json(os.path.join(jd, "voiceover.json"), d)
    return d


def vo_start(job, src, pace=None):
    """Her voiceover as a new reel: the recording copied into audio/ (never moved), and raw/vo.mp4, her voice on a black
    9:16 picture, the clip the rough cut cuts. A video she recorded her voiceover on gives its sound only."""
    src = os.path.abspath(os.path.expanduser(src))
    if not os.path.isfile(src):
        raise Refuse(f"There's no file at {src}.")
    ext = os.path.splitext(src)[1].lower()
    if ext not in VO_AUDIO_EXT + tuple(VIDEO_EXT):
        raise Refuse("That isn't a recording I can read. A voiceover can be .m4a, .mp3, .wav, .aac, .caf, or a video.")
    if pace is not None and pace not in VO_PACES:
        raise Refuse("The pace is punchy or emotional.")
    projects = os.path.realpath(os.path.join(ROOT, "projects"))
    jd = os.path.realpath(os.path.join(projects, job or ""))
    if not job or os.path.dirname(jd) != projects:
        raise Refuse(f"{job!r} isn't a reel name. Use a few words joined by dashes, like the-kitchen-reset.")
    raw = os.path.join(jd, "raw")
    if os.path.isdir(raw) and any(f != "vo.mp4" and not f.startswith(".") for f in os.listdir(raw)):
        raise Refuse(f"The reel {job} already has footage in it. Pick a new name for the voiceover.")
    os.makedirs(raw, exist_ok=True); os.makedirs(os.path.join(jd, "audio"), exist_ok=True)
    keep = os.path.join(jd, "audio", "vo" + ext)
    shutil.copy2(src, keep)
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", keep],
                               capture_output=True, text=True).stdout.strip()
    if not has_audio:
        raise Refuse("That file has no sound in it, so there's no voiceover to cut.")
    out, tmp = os.path.join(raw, "vo.mp4"), os.path.join(raw, ".vo.part.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30", "-i", keep,
                        "-map", "0:v:0", "-map", "1:a:0", "-t", f"{_clip_len(keep) or 36000:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
                        "-crf", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                        "-movflags", "+faststart", tmp], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.isfile(tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        raise Refuse("Her voiceover couldn't be read: " + (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
    os.replace(tmp, out)
    d = _vo_save(jd, voiceover=True, audio=os.path.relpath(keep, jd).replace(os.sep, "/"),
                 source=os.path.basename(src), at=time.strftime("%Y-%m-%d %H:%M:%S"), **({"pace": pace} if pace else {}))
    return {"job": os.path.basename(jd), "clip": os.path.relpath(out, jd).replace(os.sep, "/"), "seconds": round(_clip_len(out), 1), **d}


def vo_pace(job, pace):
    """Punchy (the pauses between her lines trimmed tight, the default) or emotional (her pauses kept, up to about a
    second): transcript-cut.py and close-pauses.py read it, so it shapes the next cut."""
    if pace not in VO_PACES:
        raise Refuse("The pace is punchy or emotional.")
    jd = job_dir(job)
    if not voiceover_of(jd):
        raise Refuse("That reel isn't a voiceover.")
    return _vo_save(jd, pace=pace)


def _inbox_root():
    return os.path.realpath(os.path.join(ROOT, "inbox"))


def _folder_clips(folder):
    """The clips in one inbox folder (and one folder down, where b-roll prep keeps its grabs), as Media ids."""
    root, out = _inbox_root(), []
    base = os.path.realpath(os.path.join(root, folder))
    for d, subs, files in os.walk(base) if os.path.isdir(base) else []:
        if os.path.relpath(d, base) != ".":
            subs[:] = []
        subs[:] = [x for x in subs if not x.startswith(".")]
        for f in sorted(files):
            if not f.startswith(".") and os.path.splitext(f)[1].lower() in VIDEO_EXT:
                p = os.path.join(d, f)
                out.append({"id": "inbox:" + os.path.relpath(p, root).replace(os.sep, "/"), "name": os.path.splitext(f)[0],
                            "kind": "Video", "drawer": "inbox", "at": os.path.getmtime(p)})
    return out


def footage_folders():
    """Her inbox folders that hold clips, newest first: what the page offers for Fill with my b-roll."""
    root, out = _inbox_root(), []
    for name in os.listdir(root) if os.path.isdir(root) else []:
        if name.startswith(".") or not os.path.isdir(os.path.join(root, name)):
            continue
        clips = _folder_clips(name)
        if clips:
            out.append({"id": name, "name": name, "clips": len(clips), "at": max(c["at"] for c in clips)})
    out.sort(key=lambda x: -x["at"])
    return out


def _check_folder(folder):
    folder = str(folder or "").replace("\\", "/").strip("/")
    p = os.path.realpath(os.path.join(_inbox_root(), folder))
    if not folder or not p.startswith(_inbox_root() + os.sep) or not os.path.isdir(p):
        raise Refuse("That folder isn't in your inbox anymore.")
    if not _folder_clips(folder):
        raise Refuse("That folder has no clips in it.")
    return folder


def broll_fill_request(job, folder, text="", lines=None):
    """She picked a folder of her clips on Visuals (and maybe said what she wants): kept for Claude, who fills her
    reel with them ("fill my b-roll"; the watcher hands it over by itself). A voiceover gets a clip on every line. A
    talking head gets one only on the lines she picked (`lines`, her page's line numbers); her face stays on the rest."""
    jd = job_dir(job)
    folder = _check_folder(folder)
    picks = None
    if voiceover_of(jd):
        _vo_save(jd, folder=folder)
    else:
        have = {l["line"] for l in vo_lines(jd)}
        picks = sorted({n for n in (_int_or_none(x) for x in (lines or [])) if n in have})
        if not picks:
            raise Refuse("Pick the lines that get b-roll. Your face stays on every other line.")
    req = {"folder": folder, "text": re.sub(r"\s+", " ", str(text or "")).strip()[:1200], "at": time.strftime("%Y-%m-%d %H:%M:%S"),
           **({"lines": picks} if picks else {})}
    _atomic_json(os.path.join(jd, "review", "broll-fill.json"), req)
    return dict(req, clips=len(_folder_clips(folder)), watching=watching(jd))


def _int_or_none(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _fill_folder(jd):
    """The inbox folder she filled this reel from: a voiceover's, else her last Fill request's."""
    return (voiceover_of(jd) or {}).get("folder") or (_read_json(os.path.join(jd, "review", "broll-fill.json")) or {}).get("folder")


def _cut_len(jd):
    """Her cut's length now, from its pieces (a lean round leaves the video itself behind until Finish)."""
    try:
        segs = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))["segs"]
        return sum((float(g["e"]) - float(g["s"])) / (float(g.get("sp") or 1.0) or 1.0) for g in segs)
    except Exception:
        return _duration(os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")) or 0.0


def vo_lines(jd):
    """Her cut's lines as she sees them, in cut seconds: [{"line", "start", "end", "text"}], in cut order. "line" is the
    number her page shows (lines the engine cut count too, so "line 5" is the same line on her page and here)."""
    try:
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    except Exception:
        raise Refuse("Her script isn't made yet. Open her editor first (visual_editor.py prepare).")
    times, out = word_cut_times(jd), []
    for n, ws in enumerate(sc.get("lines", []), 1):
        kept = [i for i in ws if i in times]
        if kept:
            out.append({"line": n, "start": round(min(times[i][0] for i in kept), 3), "end": round(max(times[i][1] for i in kept), 3),
                        "text": " ".join(str(sc["words"][i]["t"]) for i in kept)})
    out.sort(key=lambda l: l["start"])
    return out


def _cutaway_spans(jd):
    """Where her clips play: [(start, end, layer)] in cut seconds, from her looks list."""
    try:
        layers = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")).get("layers", [])
    except Exception:
        layers = []
    return sorted((float(l["offset"]), float(l["offset"]) + float(l["dur"]), l["name"])
                  for l in layers if l.get("cutaway") and not l.get("off") and l.get("dur") is not None)


def vo_gaps(jd):
    """The stretches of her voiceover with no clip on them yet (a black screen), each [start, end] in cut seconds."""
    end, at, out = _cut_len(jd), 0.0, []
    for s, e, _ in _cutaway_spans(jd):
        if s - at >= VO_GAP_MIN:
            out.append([round(at, 3), round(s, 3)])
        at = max(at, e)
    if end - at >= VO_GAP_MIN:
        out.append([round(at, 3), round(end, 3)])
    return out


def _split_span(jd, s0, e0, n):
    """A line shared by n clips, one after another: split on the word ends nearest to equal parts."""
    if n <= 1:
        return [(s0, e0)]
    ends = sorted(b for a, b in word_cut_times(jd).values() if s0 + CUTAWAY_MIN <= b <= e0 - CUTAWAY_MIN)
    cuts, at = [], s0
    for k in range(1, n):
        want = s0 + (e0 - s0) * k / n
        pick = min((b for b in ends if b > at + CUTAWAY_MIN), key=lambda b: abs(b - want), default=None)
        if pick is None:
            break
        cuts.append(pick); at = pick
    edges = [s0] + cuts + [e0]
    return list(zip(edges, edges[1:]))


# Where one clip ends and the next begins is a beat, not a line break (a line is only where her page wraps her
# script). vo_beats cuts her words into shots by these rules, and broll_fill lays one clip per beat (or one across
# several, when a shot needs to finish what it's doing):
#   * a cut lands on the end of a word, best at a sentence end, then after a pause, then after a comma
#   * how long a shot holds follows her pace: punchy 1.4 to 2.6 s, emotional 2.6 to 4.8 s, a little longer to reach a
#     sentence end or a pause rather than cut mid-phrase
#   * a voiceover opens on a burst of quick cuts (HOOK_BURST), then settles into holds
#   * never a shot under BEAT_MIN (the burst aside), and never a sliver left at the end of a stretch
BEAT_HOLD = {"punchy": (1.4, 2.6), "emotional": (2.6, 4.8)}
BEAT_MIN = 1.0
HOOK_BURST = (3, 0.75)                                       # a voiceover's opening: this many shots, about this long each
FILL_WORKERS = 3                                             # clips made side by side during a fill


def _fill_runs(jd, picks=None):
    """The stretches of her cut a fill covers, each a list of words (index, start, end, text, line) in cut order: a
    voiceover is one stretch, all of it; a talking head one per run of lines she ticked in a row."""
    sc = _read_json(os.path.join(jd, "review", "script.json")) or {}
    times, runs, cur = word_cut_times(jd), [], []
    for l in vo_lines(jd):
        if picks is not None and l["line"] not in picks:
            if cur:
                runs.append(cur); cur = []
            continue
        ws = sorted((i for i in sc["lines"][l["line"] - 1] if i in times), key=lambda i: times[i][0])
        cur += [(i, times[i][0], times[i][1], str(sc["words"][i]["t"]), l["line"]) for i in ws]
    if cur:
        runs.append(cur)
    return runs


def _cut_strength(run, j):
    """How good a place the end of word j is to cut (between it and the next word)."""
    w, nx = run[j], run[j + 1]
    gap, t = nx[1] - w[2], w[3]
    s = 3.0 if re.search(r"[.?!][\"'”’)]*$", t) else 1.5 if re.search(r"[,;:–—-][\"'”’)]*$", t) else 0.2
    s += 1.5 if gap >= 0.3 else 0.6 if gap >= 0.12 else 0.0
    if _LEADS_ON.match(t) and s < 1.5:                       # "...CapCut so | I can": a word that leads on keeps its thought
        s -= 1.5
    return s + (0.4 if w[4] != nx[4] else 0.0)


def vo_beats(jd, picks=None):
    """Her cut as shots: [{"beat", "start", "end", "text", "lines", "run", "hook"}], in cut order (see the rules
    above). `picks`: a talking head's ticked lines (None: every line, a voiceover)."""
    vo = voiceover_of(jd) or {}
    lo, hi = BEAT_HOLD.get(vo.get("pace") or "punchy", BEAT_HOLD["punchy"])
    target, out = (lo + hi) / 2, []
    for r, run in enumerate(_fill_runs(jd, picks)):
        i, n = 0, len(run)
        burst = HOOK_BURST[0] if vo and r == 0 else 0
        while i < n:
            s0, last = run[i][1], n - 1
            if burst > 1:                                    # the hook's quick cuts: on any word end near the beat
                cands = [j for j in range(i, last) if run[j][2] - s0 >= 0.45]
                j = min(cands, key=lambda j: abs(run[j][2] - s0 - HOOK_BURST[1]) + (1.0 if _LEADS_ON.match(run[j][3]) else 0.0),
                        default=last)
                burst -= 1
                hook = True
            else:
                hook = False
                if run[last][2] - s0 <= hi * 1.25:           # what's left fits one shot
                    j = last
                else:
                    cands = [j for j in range(i, last) if lo * 0.8 <= run[j][2] - s0 <= hi * 1.3]
                    if cands and max(_cut_strength(run, j) for j in cands) < 1.0:   # only mid-phrase cuts in reach: hold
                        cands = [j for j in range(i, last) if lo * 0.8 <= run[j][2] - s0 <= hi * 1.6  # a little longer for
                                 and _cut_strength(run, j) >= 1.5] or cands                         # a sentence end or pause
                    if cands:
                        j = max(cands, key=lambda j: _cut_strength(run, j) - abs(run[j][2] - s0 - target) * 1.2)
                    else:                                    # a long stretch with few words: the first end past the floor
                        j = next((j for j in range(i, last) if run[j][2] - s0 >= lo), last)
                if j < last and run[last][2] - run[j + 1][1] < BEAT_MIN:   # never a sliver left at the end
                    j = last
            ws = run[i:j + 1]
            out.append({"start": round(ws[0][1], 3), "end": round(ws[-1][2], 3), "text": " ".join(w[3] for w in ws),
                        "lines": sorted({w[4] for w in ws}), "run": r, "hook": hook})
            i = j + 1
    return [dict(b, beat=k) for k, b in enumerate(out, 1)]


def fill_sheets(job, clip=None, start=None, end=None, per=10, rows=7):
    """Contact sheets of her fill folder's clips, for Claude to watch: one row per clip, `per` frames spread across it,
    each frame's second written under it. Each frame is fetched by jumping straight to it (never playing the clip
    through), many at once, so a folder of long phone clips takes seconds. `clip` (a media id) with `start`/`end`:
    one clip, closer, for picking the exact moment. Writes review/fill-sheets/ and returns
    [(sheet path, [(media id, clip seconds, [frame seconds])])]."""
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image, ImageDraw
    jd = job_dir(job)
    folder = _fill_folder(jd)
    if clip:
        ids = [clip]
    elif folder:
        ids = [c["id"] for c in _folder_clips(folder)]
    else:
        raise Refuse("No fill folder on this reel yet: she picks one on Fill with my b-roll.")
    out_dir = os.path.join(jd, "review", "fill-sheets")
    shutil.rmtree(out_dir, ignore_errors=True); os.makedirs(os.path.join(out_dir, "f"))
    try:
        from hdr import HDR2SDR, hdr_kind
    except Exception:
        HDR2SDR, hdr_kind = "", (lambda p: False)
    plan = []
    for m in ids:
        src = media_path(m); L = _clip_len(src)
        a, b = (max(0.0, float(start or 0)), min(L, float(end))) if clip and end is not None else (0.0, L)
        n = per * 2 if clip else per
        ts = [round(a + (b - a) * (k + 0.5) / n, 2) for k in range(n)]
        plan.append((m, src, L, ts, f"{HDR2SDR}," if hdr_kind(src) else ""))
    W, H = 120, 214

    def grab(job_):
        r, k, src, t, pre = job_
        f = os.path.join(out_dir, "f", f"{r:03d}-{k:02d}.jpg")
        for dec in ([_hw_decode(), []] if _hw_decode() else [[]]):
            subprocess.run(["ffmpeg", "-v", "error", "-y", *dec, "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                            "-vf", f"scale=360:-2,{pre}scale={W}:{H}:force_original_aspect_ratio=decrease", "-q:v", "5", f],
                           capture_output=True, timeout=120)
            if os.path.isfile(f):
                break
        return f
    jobs = [(r, k, src, t, pre) for r, (m, src, L, ts, pre) in enumerate(plan) for k, t in enumerate(ts)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(grab, jobs))
    sheets = []
    cols = max(len(p[3]) for p in plan)
    for g in range(0, len(plan), rows):
        part = plan[g:g + rows]
        img = Image.new("RGB", (cols * W + 28, len(part) * (H + 14)), "black")
        d = ImageDraw.Draw(img)
        for rr, (m, src, L, ts, pre) in enumerate(part):
            y = rr * (H + 14)
            d.text((4, y + H // 2), str(g + rr + 1), fill="yellow")
            for k, t in enumerate(ts):
                f = os.path.join(out_dir, "f", f"{g + rr:03d}-{k:02d}.jpg")
                if os.path.isfile(f):
                    im = Image.open(f); img.paste(im, (28 + k * W + (W - im.width) // 2, y + (H - im.height) // 2))
                d.text((28 + k * W + 3, y + H), f"{t:.1f}s", fill="white")
        path = os.path.join(out_dir, f"sheet-{g // rows + 1}.jpg"); img.save(path, quality=82)
        sheets.append((path, [(m, round(L, 1), ts) for m, src, L, ts, pre in part]))
    shutil.rmtree(os.path.join(out_dir, "f"), ignore_errors=True)
    return sheets


def _best_moment(src, dur, clip, frames):
    """The clip's best moment for a shot this long, read from her clip itself (frames cached per clip for a fill)."""
    room = max(0.0, clip - dur)
    if room <= 0.05:
        return 0.0
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("broll_select", os.path.join(ROOT, "product", "broll-select.py"))
        bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(bs)
        if src not in frames:
            frames[src] = bs.extract_frames(src)
        picks = bs.pick_clip_windows(src, frames[src], clip, max(0.5, dur), per_clip=1, allow_flicker=True)
        if picks:
            return round(max(0.0, min(room, float(picks[0]["t"]))), 2)
    except Exception:
        pass
    return round(room / 2, 2)


def broll_fill(job, plan, log=print):
    """Lay her clips on her reel from Claude's plan (a plan.json path, or the dict): {"fills": [{"beat": n} or
    {"beats": [a, b]} or {"line": n} or {"start": s, "end": e}, with "clips": [{"media": "inbox:<folder>/<file>",
    "slip": seconds into her clip}, ...] (or "media" and "slip" on the entry itself)]}. A beat is a shot from
    `vo_beats` (the way to plan a fill); "beats" lets one clip run across several when the shot needs to finish what it's
    doing; "line" is her page's line number. "slip" is optional (the engine's pick of the clip's best moment otherwise).
    Two or more clips on one entry play one after another, split on word ends. On a voiceover every clip runs on until
    the next one starts (the first from 0:00, the last to the end), so the breath between two shots never goes black.
    On a talking head the clips sit only on the lines she ticked (shots in one run of ticked lines play back to back);
    her face is on every other line. Clips an earlier fill laid come off first; the ones she put on herself stay, and a
    fill never lands on them. Each clip is made as only the stretch around its moment, several at once. Says what's
    still uncovered (a voiceover)."""
    jd = job_dir(job)
    vo = bool(voiceover_of(jd))
    if isinstance(plan, str):
        plan = json.load(open(plan, encoding="utf-8"))
    picked = None if vo else (_read_json(os.path.join(jd, "review", "broll-fill.json")) or {}).get("lines")
    lines = {l["line"]: l for l in vo_lines(jd)}
    run_of = {w[4]: r for r, run in enumerate(_fill_runs(jd, picked)) for w in run}
    uses_beats = any(f.get("beat") is not None or f.get("beats") for f in plan.get("fills", []))
    beats = {b["beat"]: b for b in vo_beats(jd, picked)} if uses_beats else {}
    want = []                                                # [start, end, media, slip, run] in cut order
    for f in plan.get("fills", []):
        clips = f.get("clips") or ([{"media": f["media"], "slip": f.get("slip")}] if f.get("media") else [])
        if f.get("beat") is not None or f.get("beats"):
            ns = [int(x) for x in (f.get("beats") or [f["beat"]])]
            bad = [x for x in ns if x not in beats]
            if bad:
                raise Refuse(f"Her cut has no beat {bad[0]} (it has 1 to {len(beats)}). Run vo-beats again: her cut may have changed.")
            if len({beats[x]["run"] for x in ns}) > 1:
                raise Refuse(f"Beats {ns} sit on different stretches of her ticked lines; a clip can't run across a line she didn't tick.")
            s0, e0, run = min(beats[x]["start"] for x in ns), max(beats[x]["end"] for x in ns), beats[ns[0]]["run"]
        elif f.get("line") is not None:
            n = int(f["line"])
            if n not in lines:
                raise Refuse(f"Her cut has no line {n} (her lines: {', '.join(str(x) for x in lines)}).")
            if picked and n not in picked:
                raise Refuse(f"She didn't pick line {n} for b-roll. Her picks: {', '.join(str(x) for x in picked)}.")
            s0, e0, run = lines[n]["start"], lines[n]["end"], run_of.get(n)
        else:
            s0, e0, run = float(f["start"]), float(f["end"]), None
        for (s, e), c in zip(_split_span(jd, s0, e0, len(clips)), clips):
            want.append([s, e, c["media"], c.get("slip"), run])
    for w in want:
        media_path(w[2])                                     # every clip readable before anything comes off her reel
    want.sort(key=lambda w: w[0])
    for s, e, key in _cutaway_spans(jd):                     # this fill's clips from before go; hers stay
        if (media_of(jd, key) or {}).get("auto"):
            swap(job, key, None)
    hers = [(s, e) for s, e, _ in _cutaway_spans(jd)]
    end = _cut_len(jd)
    for k, w in enumerate(want):                             # one after another: no black between two of them
        nxt = want[k + 1] if k + 1 < len(want) else None
        if vo:
            w[0] = 0.0 if k == 0 else want[k - 1][1]
            w[1] = end if not nxt else nxt[0]
        elif nxt and w[4] is not None and nxt[4] == w[4]:
            w[1] = nxt[0]                                    # one run of her ticked lines: back to back, no flash of her
    pieces = []                                              # never over a clip she put on herself: around it
    for s, e, media, slip, _ in want:
        cur = [(s, e)]
        for hs, he in hers:
            cur = [p for a, b in cur for p in ([(a, b)] if hs >= b or he <= a else [(a, hs), (he, b)]) if p[1] - p[0] > 0.01]
        pieces += [[a, b, media, slip] for a, b in cur]
    placed, skipped = [], []
    for p in [p for p in pieces if p[1] - p[0] < CUTAWAY_MIN]:   # too short for a clip of its own (the sliver beside her
        k = pieces.index(p)                                  # clip): it stays on the clip it touches, the one before first
        prev = pieces[k - 1] if k else None
        nxt = pieces[k + 1] if k + 1 < len(pieces) else None
        if prev and abs(prev[1] - p[0]) < 1e-6:
            prev[1] = p[1]
        elif nxt and abs(nxt[0] - p[1]) < 1e-6:
            nxt[0] = p[0]
        elif not vo:                                         # a short line on its own: it runs the shortest cutaway
            continue
        else:
            skipped.append(p[2])
        pieces.remove(p)
    # Make every clip first, side by side: only the stretch around its moment (_window_for), the slow part of a fill.
    t_start, frames, lens = time.time(), {}, {}
    for p in pieces:
        src = media_path(p[2])
        lens.setdefault(src, _clip_len(src))
        if p[3] is None:                                     # the engine's pick of its best moment, from her clip itself
            p[3] = _best_moment(src, p[1] - p[0], lens[src], frames)
        p.append(_window_for(lens[src], float(p[3]), p[1] - p[0]))
    todo_ = {}
    for p in pieces:
        todo_.setdefault((media_path(p[2]), p[4]), f"fill{len(todo_)}")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=FILL_WORKERS) as ex:
        made = dict(zip(todo_, ex.map(lambda kv: _cutaway_source(jd, kv[1], kv[0][0], None, kv[0][1]), todo_.items())))
    log(f"  made {len(made)} clip{'s' if len(made) != 1 else ''} in {time.time() - t_start:.0f}s")
    try:
        for s, e, media, slip, win in pieces:
            out = place_media(job, s, e, media, made=made[(media_path(media), win)], slip=slip, window=win)
            key = out["layer"]
            _atomic_json(os.path.join(jd, "hf-graphics", "_looks", key, "media.json"), dict(media_of(jd, key) or {}, auto=True))
            placed.append({"layer": key, "clip": os.path.basename(media_path(media)), "start": round(s, 2)})
            log(f"  {int(s // 60)}:{s % 60:04.1f}  {os.path.basename(media_path(media))}")
    finally:
        for rel in made.values():                            # the shared copies; each clip kept its own
            try:
                os.remove(os.path.join(jd, rel))
            except OSError:
                pass
    looks_manifest(jd)
    req = os.path.join(jd, "review", "broll-fill.json")
    if os.path.isfile(req):
        _atomic_json(req, dict(_read_json(req) or {}, done=time.strftime("%Y-%m-%d %H:%M:%S")))
    log(f"  done in {time.time() - t_start:.0f}s")
    return {"placed": placed, "skipped": skipped, "gaps": vo_gaps(jd) if vo else []}


@_changes_looks
def _whole_cut_span(jd):
    """Her whole-reel captions run from her first kept word to her last, in today's cut. They are anchored to that,
    never to a second on the clock: a change to a clip before her first word (a quiet opener sped up, cut or
    trimmed) moved every word earlier while the captions stayed put, and her first line lost its captions."""
    words = _line_words(jd, 0, 1e9)
    if not words:
        return None
    return float(words[0]["t"]), float(words[-1]["e"])


def _caption_box(jd):
    """review/caption-box.json: this reel's own caption size and line width, or {} when she hasn't set them."""
    try:
        return json.load(open(os.path.join(jd, "review", "caption-box.json"), encoding="utf-8")) or {}
    except Exception:
        return {}


def _set_caption_box(jd, **kw):
    """Write her caption size (`size`) and/or line width (`narrower` px) into review/caption-box.json. Every caption
    draw reads this file (lookbook.draw for the size, build-reel-type for the width), so a size or width she sets
    HOLDS across every cut edit and style swap instead of being lost on the next redraw. A key set to None clears it."""
    p = os.path.join(jd, "review", "caption-box.json")
    cur = _caption_box(jd)
    for k, v in kw.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = v
    if cur:
        _atomic_json(p, cur)
    elif os.path.isfile(p):
        os.remove(p)
    return cur


def set_captions(job, look_id):
    """The reel's captions in a lookbook caption style (single-word, phrase, karaoke, spotlight), over her whole cut,
    with her highlights. Swaps the reel's own captions layer when it has one; otherwise lays them on as hers."""
    import lookbook
    jd = job_dir(job)
    looks = looks_manifest(jd) or {}
    capL = next((l for l in looks.get("layers", []) if l.get("captions")), None)
    if capL and capL["name"] == "cap-all":                   # captions she added: laid again over her whole cut
        sp = _whole_cut_span(jd)
        if not sp:
            raise Refuse("Her cut has no words to caption.")
        return place_look(job, "cap-all", sp[0], sp[1], look_id)
    if capL:
        layer, lk, pk, _n, start, dur, caps, words, text, zones = _line_ctx(jd, capL["name"])
        words = _line_words(jd, 0, 1e9)
        l = lookbook.find(look_id, pk)
        dur = max(1.0, (words[-1]["e"] + 0.6) if words else dur)
        item = _draw_choice(jd, l, f"hf-graphics/_looks/{capL['name']}/{l['id']}", f"{capL['name']}-{l['id']}",
                            " ".join(w["w"] for w in words), dur, pk, zones, words, accents=_her_accents(jd))
        if not item.get("dir"):
            raise Refuse(item.get("unavailable") or "Those captions couldn't be drawn.")
        return swap(job, capL["name"], look_id)
    words = _line_words(jd, 0, 1e9)
    if not words:
        raise Refuse("Her cut has no words to caption.")
    key = "cap-all"
    os.makedirs(os.path.join(jd, "hf-graphics", "_looks", key), exist_ok=True)
    json.dump({"kind": "caption"}, open(os.path.join(jd, "hf-graphics", "_looks", key, "kind.json"), "w", encoding="utf-8"))
    return place_look(job, key, words[0]["t"], words[-1]["e"], look_id)


@_changes_looks
@_locked
def set_caption_box(job, size=None, narrower=None):
    """Set this reel's caption SIZE (0.45-1.6, relative to the pack's own) and/or line WIDTH (narrower by N px, up
    to 300), persisted in review/caption-box.json so they hold across every cut edit and style swap, then redraw her
    captions so it shows now. The page can't size captions by hand, so this is how a size or width she asks for is
    set and kept. The size has a legibility floor (0.45); the width is capped at 300 px narrower."""
    jd = job_dir(job)
    kw = {}
    if size is not None:
        kw["size"] = round(max(0.45, min(1.6, float(size))), 3)
    if narrower is not None:
        kw["narrower"] = round(max(0.0, min(300.0, float(narrower))), 1)
    if not kw:
        raise Refuse("Nothing to set: give a caption size (0.45-1.6) or a width (narrower px).")
    _set_caption_box(jd, **kw)
    redrawn = False                                          # redraw her whole-reel captions at the current style so it shows
    e = _entry(jd, "cap-all")[0] or {}
    if e.get("look"):
        sp = _whole_cut_span(jd)
        if sp:
            try:
                place_look(job, "cap-all", sp[0], sp[1], e["look"]); redrawn = True
            except Refuse:
                pass
    return {"size": kw.get("size"), "narrower": kw.get("narrower"), "redrawn": redrawn}


def look_request_status(job, rid, status, look_id=None):
    """The chat moves her idea along: 'draft' (a version is on her line), 'done' (in her lookbook), 'dropped'."""
    jd = job_dir(job)
    reqs = _requests(jd)
    r = next((x for x in reqs if x["id"] == rid), None)
    if not r:
        raise Refuse(f"There's no idea {rid!r} for this reel.")
    r["status"] = status
    if status in ("draft", "done", "dropped"):               # her page's task queue counts it done from here
        r["done_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if look_id:
        r["look"] = look_id
    _atomic_json(_requests_path(jd), {"requests": reqs})
    looks_manifest(jd)
    if status in ("draft", "done"):                           # her page pops it (a draft, then kept: one card, the newest)
        import editor_says
        editor_says.told(jd, "Your new look is on your line. Press play to see it." if status == "draft" else
                         "Your new look is in your lookbook, ready for every reel.", kind="look", go="visuals", group="look")
    return r


# ── the sandbox: she describes a look on a line, Claude makes a few quick takes, she tries them on that line, commits
#    one, and keeps it for every reel (her lookbook) or just this one. Takes are hidden lookbook designs (lookbook.py
#    save-design --sample <id>) until she commits; the one she commits gets the full render check then.

def _sandbox(jd, rid):
    reqs = _requests(jd)
    r = next((x for x in reqs if x["id"] == rid), None)
    if not r or r.get("mode") != "sandbox":
        raise Refuse("That sandbox isn't open anymore. Reload the page.")
    return reqs, r


def _reel_pack_for(jd):
    return _swap_pack(jd, {"pack": _reel_pack(jd)})[0]


def _clear_sketch(pack, rid, did):
    """Remove a sandbox sketch, and only a sketch made for THIS idea: never one of her own looks or designs. It lives
    in the pack it was saved in, which a pack switch since may have changed for her reel."""
    import lookbook
    pack = lookbook.design_home(did) or pack
    e = lookbook.book_entry(pack, did)
    if e and e.get("sample") == rid:
        lookbook.remove_design(pack, did)


_GENERIC_NAME = re.compile(r"^\s*(?:(?:sketch|take|look|design|option|version|idea|draft)\s*#?\s*\d*|starter card|my look"
                           r"|your (?:own )?design)\s*$|\(draft\)\s*$", re.I)
_NAME_STOP = {"of", "the", "a", "an", "and", "to", "in", "on", "at", "with", "for", "from", "your", "her", "my", "by",
              "then", "as", "into", "over", "under", "that", "which", "while"}


def _sketch_label(pack, look_id, l=None):
    """What a Sandbox sketch is called when she locks it in: a short description of the LOOK itself ("Card pop
    orbit"), never her idea's first words. Its design.json "name" when that's a real name (not "Sketch 2"), else
    the name it was saved under, else a few words from its "about", else its kind."""
    import lookbook
    try:
        l = l or lookbook.find(look_id, pack)
    except Exception:
        l = {}
    try:
        meta = json.load(open(os.path.join(lookbook.design_dir(l.get("home") or pack, look_id), "design.json"), encoding="utf-8"))
    except Exception:
        meta = {}
    for n in (meta.get("name"), l.get("name")):
        n = re.sub(r"\s+", " ", str(n or "")).strip()
        if n and not _GENERIC_NAME.search(n):
            return n[:40].strip()
    about = re.split(r"[.:;,!?(\u2014\u2013]| - ", str(meta.get("about") or l.get("about") or ""))[0]
    words, keep = [w for w in re.findall(r"[A-Za-z0-9$%'&+-]+", about)], []
    while words and words[0].lower() in _NAME_STOP:
        words.pop(0)
    for w in words:                                          # up to three words that say something, five in all
        if len(keep) == 5 or sum(x.lower() not in _NAME_STOP for x in keep) == 3:
            break
        keep.append(w)
    words = keep
    while words and words[-1].lower() in _NAME_STOP:
        words.pop()
    if words:
        n = " ".join(words)
        return (n[0].upper() + n[1:])[:40].strip()
    kind = str(meta.get("kind") or l.get("kind") or "").strip()
    return f"{kind} look" if kind else "My look"


def _sb_where(r):
    """Where her sandbox plays: the moment Claude read from her request (r['place']), else the line she started on.
    The line is only where the idea began; "fly in at my head right here" or "across these two lines" is honored."""
    p = r.get("place") or {}
    if not p and r.get("w") is None:
        raise Refuse("Tell me where this sandbox goes: sandbox-takes needs --start and --end (her words name the lines).")
    return p.get("key") or f"add-w{r['w']}", float(p.get("start", r["start"])), float(p.get("end", r["end"])), bool(p.get("behind"))


def _sb_ours(r, look):
    """Is this look one of this idea's own sketches (any round), never one of hers?"""
    return bool(look) and (look in (r.get("takes") or []) or look in (r.get("shown") or [])
                           or f"sandbox-{r['id']}-" in str(look))


def _sb_slot(jd, r):
    """The slot a sketch plays in on her reel, kept its own. The slot is chosen when the sketches land; a look she
    put on that line since takes that slot, and trying a sketch there used to swap HER look off her reel (Lock it in
    or a dropped idea then left it gone). Then the sketch moves to the next free slot on that line instead."""
    key, a, z, behind = _sb_where(r)
    e = _adds(jd).get(key)
    m = re.match(r"^add-w(\d+)", key)
    if e and not _sb_ours(r, e.get("look")) and m:
        r["place"] = {"key": _free_add_key(jd, int(m.group(1))), "start": round(a, 3), "end": round(z, 3), "behind": behind}
        r.pop("was", None)
    return _sb_where(r)[0]


def _sb_put(job, jd, r, look):
    key, a, z, behind = _sb_where(r)
    out = place_look(job, key, a, z, look)
    if behind:
        set_behind(job, key, True)
    return out


@_locked
def sandbox_takes(job, rid, look_ids, start=None, end=None, behind=False):
    """Claude's sketches for her idea (three, usually): recorded on the idea and drawn for her sandbox panel, where they
    play side by side. Her reel is not touched until she locks one in. start/end (cut seconds) and behind follow what
    she asked for, not where her line breaks. A remix round replaces the last round's sketches."""
    import lookbook
    jd = job_dir(job)
    reqs, r = _sandbox(jd, rid)
    ids = [str(x) for x in look_ids if str(x).strip()]
    if not 1 <= len(ids) <= 4:
        raise Refuse("A sandbox gets one to four takes.")
    pack = _reel_pack_for(jd)
    for x in ids:
        lookbook.find(x, pack)                                # every take must be drawable in her pack
        e = lookbook.book_entry(lookbook.design_home(x) or pack, x)
        if not e or e.get("sample") != rid:                   # a sketch, saved for this idea: never one of her own looks
            raise Refuse(f"{x} isn't a sketch for this sandbox: save it with lookbook.py save-design --sample {rid}.")
    if start is not None or end is not None or behind:
        a = float(start if start is not None else r["start"]); z = float(end if end is not None else r["end"])
        if z - a < 1 / 3:
            raise Refuse("A sandbox look needs at least a third of a second on screen.")
        times = word_cut_times(jd)
        first = min((w for w, (s0, e0) in times.items() if e0 > a + 0.02), key=lambda w: times[w][0], default=None)
        if first is None:
            raise Refuse("There are no words at that time in her cut.")
        if behind and not can_behind():
            raise Refuse("Behind her needs the render tools (Node and HyperFrames) on this computer: make the takes in front of her for now.")
        r["place"] = {"key": _free_add_key(jd, first), "start": round(a, 3), "end": round(z, 3), "behind": bool(behind)}
    _sb_where(r)                                              # it knows where it goes before anything is drawn
    old = [t for t in (r.get("takes") or []) if t not in ids]
    r.update(takes=ids, tried=None, status="takes", done_at=time.strftime("%Y-%m-%d %H:%M:%S")); r.pop("working", None)
    r.pop("fix", None)
    _atomic_json(_requests_path(jd), {"requests": reqs})
    for t in old:                                             # last round's sketches go once the new ones are in
        _clear_sketch(pack, rid, t)
    looks_manifest(jd)
    out = dict(r, sketches=sandbox_sketches(job, rid)["sketches"])
    import editor_says                                        # her page pops it, wherever she is on it
    editor_says.told(jd, (f"Your {len(ids)} sketches are in your Sandbox. Tap one to try it on your line." if len(ids) > 1 else
                          "Your sketch is in your Sandbox. Tap it to try it on your line."), kind="sandbox", go="sandbox", group="sandbox")
    return out


def sandbox_sketches(job, rid):
    """Her sandbox panel: each sketch drawn on its moment of her cut (her words, her pack, around her), for a live
    preview over a still of that moment. Nothing renders and nothing on her reel changes."""
    import lookbook
    jd = job_dir(job)
    _, r = _sandbox(jd, rid)
    key, a, z, behind = _sb_where(r)
    pack = _reel_pack_for(jd)
    st, dur = max(0.0, a - 0.12), max(1.0, z + 0.35 - max(0.0, a - 0.12))
    words = _line_words(jd, st, z + 0.02)
    text = " ".join(x["w"] for x in words).strip() or r.get("words") or "your words"
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    out = []
    for n, t in enumerate(r.get("takes") or [], 1):
        try:
            l = lookbook.find(t, pack)
        except lookbook.Refuse:
            continue
        item = _draw_choice(jd, l, f"hf-graphics/_looks/_sandbox/{rid}/{t}", f"sb-{rid}-{n}", text, dur, pack, zones, words)
        out.append(dict(item, n=n, name=f"Sketch {n}", about=l.get("about") or "", suggest=_sketch_label(pack, t, l)))
    frame = _frame_at(jd, a + min(0.6, (z - a) / 2), f"sb-{rid}", width=540)
    return {"id": rid, "idea": r.get("idea"), "round": r.get("round", 1), "start": a, "end": z, "behind": behind,
            "text": text, "frame": frame, "sketches": out}


@_locked
def sandbox_remix(job, rid, text, look_id=None):
    """She wants another round: what to change (and which sketch it starts from). Claude makes three new ones."""
    jd = job_dir(job)
    reqs, r = _sandbox(jd, rid)
    text = str(text or "").strip()[:1000]
    if not text:
        raise Refuse("Say what to change first, in a few words.")
    r.setdefault("remixes", []).append({"text": text, "from": look_id if look_id in (r.get("takes") or []) else None})
    r.update(status="open", round=int(r.get("round", 1)) + 1, sent_at=time.strftime("%Y-%m-%d %H:%M:%S")); r.pop("working", None); r.pop("done_at", None)
    _atomic_json(_requests_path(jd), {"requests": reqs})
    looks_manifest(jd)
    return r


@_locked
def sandbox_try(job, rid, look_id):
    """She tapped a take: it plays on her line (drawn exactly as it would export)."""
    jd = job_dir(job)
    reqs, r = _sandbox(jd, rid)
    if look_id not in (r.get("takes") or []):
        raise Refuse("That take isn't in this sandbox.")
    if r.get("status") in ("dropped", "done"):
        raise Refuse("That sandbox idea is closed. Reload the page.")
    key = _sb_slot(jd, r)
    if not r.get("on_reel"):
        r["was"] = (_adds(jd).get(key) or {}).get("look"); r["on_reel"] = True
    out = _sb_put(job, jd, r, look_id)
    r["tried"] = look_id
    r["shown"] = sorted(set(r.get("shown") or []) | {look_id})
    _atomic_json(_requests_path(jd), {"requests": reqs})
    looks_manifest(jd)
    return dict(r, warn=out.get("warn"))


@_changes_looks
@_locked
def sandbox_keep(job, rid, keep, name=None, look_id=None):
    """Lock in the sketch she picked: it gets the full render check, goes on her reel at its moment, and stays
    either in her lookbook for every reel (keep='reuse') or on this reel only ('oneoff'). The other sketches go."""
    import lookbook
    jd = job_dir(job)
    reqs, r = _sandbox(jd, rid)
    if look_id:
        if look_id not in (r.get("takes") or []):
            raise Refuse("That sketch isn't in this sandbox.")
        r["tried"] = look_id
    look = r.get("tried")
    if not look:
        raise Refuse("Pick a sketch first.")
    if r.get("status") in ("dropped", "done"):                # its sketches are gone: never a crash on a missing design
        raise Refuse("That sandbox idea is closed. Reload the page.")
    _sb_slot(jd, r)
    if keep not in ("reuse", "oneoff"):
        raise Refuse("Keep it for every reel, or just this one?")
    pack = _reel_pack_for(jd)
    # her name for it, else what the sketch IS ("Card pop orbit"), never her idea's first words; the id follows it
    label = re.sub(r"\s+", " ", str(name or "")).strip()[:40] or _sketch_label(pack, look)
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "look"
    _save = lambda **kw: lookbook.save_design(lookbook.design_dir(lookbook.design_home(look) or pack, look), pack, label,
                                              only_reel=os.path.basename(jd) if keep == "oneoff" else None,
                                              design_id=f"my-{slug}" + (f"-{rid}" if keep == "oneoff" else ""),
                                              line_text=r.get("words"), **kw)
    try:
        try:
            did = _save()
        except (Refuse, lookbook.Refuse) as e:
            # her pick is final: a sketch that only trips the RENDER check (a layout warning: text near her face,
            # an overlap) is kept anyway and the warning is said once; a broken design rule still comes back to
            # Claude (2026-10-17: she locked in a sketch and the page refused it)
            bits = [b for b in str(e).replace("Not saved yet:\n- ", "").split("\n- ") if b.strip()]
            if not bits or not all("render check" in b for b in bits):
                raise
            did = _save(render_check=False)
            r["warn"] = "Kept as you picked it. Its layout check flagged a spot to look at in the final video."
    except (Refuse, lookbook.Refuse) as e:                    # it breaks a design rule: her pick still goes on her reel, as
        r["fix"] = str(e).replace("Not saved yet:\n- ", "").replace("\n- ", " · ")[:600]   # she picked it; what it trips is kept
        did = _save(her_pick=True, render_check=False)        # for Claude to tidy on her next "sandbox" (never a refusal)
        r["warn"] = "Kept as you picked it. Claude tidies one detail in it the next time you say sandbox."
    out = _sb_put(job, jd, r, did)
    for t in r.get("takes") or []:
        if t != did:
            _clear_sketch(pack, rid, t)
    if not r.get("warn"):
        r.pop("fix", None)
    r.pop("takes", None); r.pop("tried", None)               # kept: its sketches are gone, so the page never offers
    r.update(status="done", look=did, kept=keep, pack=pack)  # "Lock it in" on them again
    _atomic_json(_requests_path(jd), {"requests": reqs})
    looks_manifest(jd)
    return dict(r, warn=out.get("warn") or r.get("warn"))


@_locked
def sandbox_working(job, rid):
    """Claude picked her Sandbox idea up: her page says so ("I'm working on your sandbox now. Keep working."), so she
    knows she can close it and carry on. The idea stays open; its sketches clear the flag when they land."""
    jd = job_dir(job)
    reqs, r = _sandbox(jd, rid)
    r["working"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _atomic_json(_requests_path(jd), {"requests": reqs})
    looks_manifest(jd)
    return r


@_locked
def sandbox_drop(job, rid):
    """She cancelled: the takes go away and her line goes back to what it had."""
    import lookbook
    jd = job_dir(job)
    reqs, r = _sandbox(jd, rid)
    if r.get("takes"):
        key, a, z, behind = _sb_where(r)
        if r.get("on_reel") and _sb_ours(r, (_adds(jd).get(key) or {}).get("look")):   # a sketch it put on her reel to
            if behind:                                        # look at: only ever that sketch comes off, never a look
                set_behind(job, key, False)                   # of hers that sits there now
            if r.get("was") and can_bring_back(jd, key):
                bring_back(job, key)                          # exactly what was there, refine and moves included
            else:
                swap(job, key, None)
        pack = _reel_pack_for(jd)
        for t in r["takes"]:
            _clear_sketch(pack, rid, t)
    r["status"] = "dropped"
    _atomic_json(_requests_path(jd), {"requests": reqs})
    looks_manifest(jd)
    return r


@_changes_looks
@_locked
def redraw_captions(job):
    """Her accents changed and the reel's captions are a builder style: draw that style again with them (seconds)."""
    import lookbook
    jd = job_dir(job)
    if not os.path.isfile(os.path.join(jd, "review", "looks.json")):
        return {"redrawn": False, "lines": []}
    looks = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    capL = next((l for l in looks.get("layers", []) if l.get("captions")), None)
    # the reel's own captions (a swap), or the ones she added with Captions: add (cap-all, an added look)
    lines = redraw_line_highlights(job)                      # takeovers and a line's own captions wear them too
    sw = ((_adds(jd) if capL["name"].startswith("cap-") else _swaps(jd)).get(capL["name"])) if capL else None
    if not capL or not sw or sw.get("look") in (None, "_original", "_off"):
        return {"redrawn": bool(lines), "lines": lines}
    if capL["name"] == "cap-all":                            # captions she added: over her whole cut, as it is today
        sp = _whole_cut_span(jd)
        if sp:
            place_look(job, "cap-all", sp[0], sp[1], sw["look"])
        return {"redrawn": True, "lines": lines}
    pack, _ = _swap_pack(jd, looks)
    # timed from where the caption layer starts: the reel's own captions sit at 0:00, but captions she added
    # (cap-all) start at her first word, and words timed from 0:00 there played every caption late by that much
    off = float(capL.get("offset") or 0)
    words = _line_words(jd, off, 1e9)
    text = " ".join(w["w"] for w in words)
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    l = lookbook.find(sw["look"], pack)
    dur = max(1.0, (words[-1]["e"] + 0.6) if words else float(capL["dur"]))   # her CURRENT cut's length, never the old drawing's
    _draw_choice(jd, l, f"hf-graphics/_looks/{capL['name']}/{l['id']}", f"{capL['name']}-{l['id']}", text, dur,
                 pack, zones, words, accents=_look_accents(jd, l, True, off, 1e9, origin=off), track=_track_for(jd, l, off, dur))
    looks_manifest(jd)
    return {"redrawn": True, "lines": lines}


@_locked
def redraw_line_highlights(job):
    """Her highlights changed: every line look that wears them (a takeover, a line's own captions) is drawn again
    on the lines whose highlights differ from what it was drawn with, keeping its refine (effect, size) and where she
    moved it. A look drawn before highlights reached it catches up the same way. Returns the layers redrawn."""
    import lookbook
    jd = job_dir(job)
    try:
        looks = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    except FileNotFoundError:
        return []
    pack, _ = _swap_pack(jd, looks)
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    done = []
    for key, e in list(_adds(jd).items()) + list(_swaps(jd).items()):
        if key == "cap-all" or not e.get("dir") or e.get("look") in (None, "_off", "_original", "media"):
            continue
        page = os.path.join(jd, e["dir"])
        try:
            rec = json.load(open(os.path.join(page, "look.json"), encoding="utf-8"))
            l = lookbook.find(rec["look"], rec.get("pack") or pack)
        except Exception:
            continue
        if (l.get("base") or l["id"]) not in lookbook.CAPTION_LOOKS:   # every caption-style look on a line wears her
            continue                                                    # highlights, one added with Add a look too
                                                                        # ("don't" stayed plain on her Phrase line)
        try:
            layer, _l, _pk, _n, start, dur, caps, words, _text, _z = _line_ctx(jd, key)
        except Exception:
            continue
        acc = _look_accents(jd, l, caps or l.get("layer") == "captions", start, start + dur, origin=start)
        if [list(x) for x in rec.get("accents") or []] == [[a["w"], a["t"]] for a in acc or []]:
            continue
        m = re.search(r'data-composition-id="([^"]+)"', open(os.path.join(page, "index.html"), encoding="utf-8").read())
        lookbook.draw(rec["look"], os.path.dirname(page), rec.get("text") or _text, float(rec.get("dur") or dur),
                      rec.get("pack") or pack, zones, words=rec.get("words") or words, comp_id=m.group(1) if m else None,
                      size=rec.get("size"), effect=rec.get("effect"), accents=acc,
                      track=_track_for(jd, l, start, float(rec.get("dur") or dur)))
        if e.get("nudge"):
            _apply_nudge(jd, e["dir"], e["nudge"])
        done.append(key)
    if done:
        looks_manifest(jd)
    return done


@_locked
def nudge(job, layer_name, dx, dy, scale=None, rotate=None, ox=None, oy=None, on_face=False):
    """She dragged something on her reel: keep it there (px on the 1080x1920 frame). A graphic she never swapped is
    moved on a copy of it, so her build stays as it was. Captions move up and down only, for the whole reel."""
    jd = job_dir(job)
    e, _ = _entry(jd, layer_name)
    if not e:
        e = _working_copy(jd, layer_name)
    dx, dy = max(-3840, min(3840, int(dx))), max(-3840, min(3840, int(dy)))   # her hand wins: anywhere, even off the frame
    if layer_name in ("captions", "hf-captions") or scale is None and rotate is None:
        e["nudge"] = [dx, dy]
    else:                                                    # her size and angle too, around the look's own center
        e["nudge"] = [dx, dy, round(max(0.25, min(4.0, float(scale if scale is not None else 1))), 3),
                      round(max(-180.0, min(180.0, float(rotate or 0))), 1),
                      int(max(0, min(frame.size(jd)[0], float(ox if ox is not None else frame.size(jd)[0] / 2)))), int(max(0, min(frame.size(jd)[1], float(oy if oy is not None else frame.size(jd)[1] / 2))))]
    _save_entry(jd, layer_name, e)
    if on_face:                                              # she dragged it onto herself on purpose: the export lets it through
        import finish
        finish.allow(job, layer_name)
    _apply_nudge(jd, e["dir"], e["nudge"])
    looks_manifest(jd)
    return {"layer": layer_name, "nudge": e["nudge"]}


def _resolve_fonts(jd, names, extra=None):
    """Her per-look font overrides {role: name} -> {role: file}, resolved to HER own fonts only (unknown names drop
    out, so the pack face stays — never a missing font). `extra` {role: name} layers a fresh pick on top.
    Pure lookup (no reel state), so it is NOT locked; its caller `refine` holds the reel lock."""
    import lookbook
    out = {}
    for role, nm in list((names or {}).items()) + list((extra or {}).items()):
        f = lookbook.font_file(nm, jd)
        if f:
            out[str(role).lower()] = f
        elif extra and role in extra:                        # she named a font that isn't hers: say so, don't silently ignore
            raise Refuse(f"I couldn't find a font called {nm!r} in your fonts. Drop the .otf/.ttf in favorites/fonts "
                         f"(or assets/fonts) and try again, or use your pack's font.")
    return out or None


@_locked
def refine(job, layer_name, look_id, text=None, size=1.0, effect=None, pack=None, font=None, font_role=None):
    """Draw her refined version of a look on this line into a sandbox (hf-graphics/_looks/<layer>/_refine/).
    From the lookbook, `pack` is the tab she's on: the look is drawn in that pack and saved to that pack's lookbook.
    font: one of HER fonts to wear over the pack default for this look (font_role picks which role, default headline)."""
    import lookbook, stylepack
    jd = job_dir(job)
    looks = _looks_or_fresh(jd)
    reel_pack, _ = _swap_pack(jd, looks)
    pack = pack if layer_name == "_book" and pack in stylepack.names() else reel_pack
    if layer_name == "_book":                                # a new look, started from the lookbook (her opening line)
        bv = lookbook_view(job, pack)
        start, dur = 0.0, float(bv["looks"][0]["dur"]) if bv["looks"] else 3.0
        tw = _line_words(jd, 0, 1e9)
        t0 = tw[0]["t"] if tw else 0.0
        words = [dict(w, t=round(w["t"] - t0, 3), e=round(w["e"] - t0, 3)) for w in tw[:len(bv["text"].split())]]
        text = text or bv["text"]
    else:
        L = next((l for l in looks.get("layers", []) if l["name"] == layer_name), None)
        if not L:
            raise Refuse("That look isn't on your reel anymore. Reload the page.")
        start, dur = float(L["offset"]), float(L["dur"])
        if L.get("look") == "media":                         # her own image or GIF: its entrance, nothing to type
            m = media_of(jd, layer_name) or {}
            d = os.path.join(jd, "hf-graphics", "_looks", layer_name, "_refine", "hf-reel-type-media")
            r = _draw_media(jd, layer_name, m.get("media"), dur, effect=effect if effect is not None else m.get("effect"), page=d)
            e, _ = _entry(jd, layer_name)
            if e and e.get("nudge"):
                _apply_nudge(jd, r["dir"], e["nudge"])
            cur = effect if effect is not None else m.get("effect")
            _atomic_json(os.path.join(os.path.dirname(d), "look.json"), {"look": "media", "effect": cur, "dur": dur, "pack": pack})   # what Apply keeps
            return {"dir": r["dir"], "comp": f"{layer_name}-media", "dur": dur, "text": "", "look": "media", "media": True,
                    "effect": cur, "effects": [{"id": k, "name": n} for k, n in MEDIA_EFFECTS], "pack": pack, "sizable": False}
        words = _own_words(jd, layer_name, start, dur)
    if not text:
        try:
            rec_ = json.load(open(os.path.join(jd, os.path.dirname(L["dir"]), "look.json"), encoding="utf-8"))
            text = lookbook.words_to_edit(lookbook.find(look_id, pack), pack, rec_["text"], rec_.get("note"))   # a heading too
        except Exception:
            text = " ".join(w["w"] for w in words)
    if effect:                                               # one the look can't show was drawn without it and reported as
        offered = lookbook.effects_for(look_id, pack)        # set (2026-10-23: three from the chat, none ever played)
        if effect not in {x["id"] for x in offered}:
            can = ", ".join(f"{x['name']} ({x['id']})" for x in offered)
            raise Refuse(f"The {lookbook.find(look_id, pack).get('name', look_id)} look can't show the {effect!r} animation. "
                         + (f"It takes: {can}." if can else "It has no animations of its own to pick from."))
    zones = None
    zp = os.path.join(jd, "subject-zones.json")
    if os.path.isfile(zp):
        zones = json.load(open(zp, encoding="utf-8"))
    d = os.path.join(jd, "hf-graphics", "_looks", layer_name, "_refine")
    cur_fonts = {}                                           # font overrides already on this look, so a new pick adds, not replaces
    try:
        cur_fonts = (json.load(open(os.path.join(jd, os.path.dirname(L["dir"]), "look.json"), encoding="utf-8")).get("fonts")) or {}
    except Exception:
        pass
    _role = {"captions": "caption", "takeover": "takeover", "thought": "thought"}.get(lookbook.find(look_id, pack).get("layer"), "headline")
    font_ov = _resolve_fonts(jd, cur_fonts, {(font_role or _role): font} if font else None)
    try:
        acc = _look_accents(jd, lookbook.find(look_id, pack), lookbook.find(look_id, pack).get("layer") == "captions", start, start + dur, origin=start)   # a caption style keeps her highlights through a refine (an effect took "don't" away) if layer_name != "_book" else None
        r = lookbook.draw(look_id, d, text, dur, pack, zones, words=words, comp_id=f"{layer_name}-refine", size=size,
                          effect=effect or None, accents=acc, font_overrides=font_ov,
                          track=_track_for(jd, lookbook.find(look_id, pack), start, dur) if layer_name != "_book" else None)
    except lookbook.Refuse as e:
        raise Refuse(str(e))
    e, _ = _entry(jd, layer_name)
    if e and e.get("nudge"):
        _apply_nudge(jd, os.path.relpath(r["dir"], jd), e["nudge"])
    return {"dir": os.path.relpath(r["dir"], jd).replace(os.sep, "/"), "comp": f"{layer_name}-refine", "dur": dur, "text": text,
            "look": look_id, "size": size, "effect": effect, "effects": lookbook.effects_for(look_id, pack), "pack": pack,
            **({"hint": "The words before the / are the heading; your list comes after it."}
               if lookbook.has_heading(lookbook.design_meta(lookbook.find(look_id, pack), pack)) else {}),
            # Size only where it visibly changes the look (a hook's headline is fitted to the room over her head)
            "sizable": lookbook.find(look_id, pack)["layer"] in ("takeover", "captions")}


@_changes_looks
@_locked
def refine_apply(job, layer_name, scope, name=None):
    """Keep her refine: on this moment only, or saved to her pack's lookbook as a new look (and used here too)."""
    import lookbook
    jd = job_dir(job)
    src = os.path.join(jd, "hf-graphics", "_looks", layer_name, "_refine")
    try:
        meta = json.load(open(os.path.join(src, "look.json"), encoding="utf-8"))
    except Exception:                                        # nothing changed yet: keeping it is keeping it as it is
        return {"layer": layer_name, "scope": "line", "unchanged": True, "name": name}
    look_id = meta["look"]
    if look_id == "media":                                   # her image's entrance: kept with it, redrawn in place
        said = ("Applied here: an image stays with this reel (your favorites are where it lives for other reels)."
                if scope == "pack" else None)                # her save, as near as it goes: kept on this reel
        mp = os.path.join(jd, "hf-graphics", "_looks", layer_name, "media.json")
        m = media_of(jd, layer_name) or {}
        m["effect"] = meta.get("effect"); _atomic_json(mp, m)
        a = _adds(jd).get(layer_name) or {}
        _draw_media(jd, layer_name, m.get("media"), float(a.get("dur") or meta.get("dur") or 2))
        looks_manifest(jd)
        return {"layer": layer_name, "look": "media", "scope": "line", "name": m.get("name"), **({"said": said} if said else {})}
    if layer_name == "_book" and scope != "pack":            # a lookbook look has no line of its own: it's saved to her pack
        scope = "pack"
    if scope == "pack":
        if not (name or "").strip():
            base = lookbook.find(look_id, meta["pack"])
            name = f"My {base['name'].lower()}"
        look_id = lookbook.save_look(meta["pack"], look_id, name.strip()[:40], size=meta.get("size"), effect=meta.get("effect"))
        if layer_name == "_book":
            return {"layer": layer_name, "look": look_id, "scope": scope, "name": name}
    k = 1
    while os.path.exists(os.path.join(jd, "hf-graphics", "_looks", layer_name, f"refined-{k}")):
        k += 1
    dst = os.path.join(jd, "hf-graphics", "_looks", layer_name, f"refined-{k}")
    shutil.copytree(src, dst)
    page = next((os.path.join(dst, x) for x in sorted(os.listdir(dst)) if x.startswith("hf-reel-type-")
                 and (x == "hf-reel-type-media") == (look_id == "media")), None)   # never an old picture's page under a text look
    rel = os.path.relpath(page, jd).replace(os.sep, "/")
    e, _ = _entry(jd, layer_name)
    if layer_name.startswith(("add-", "cap-")):
        line = json.load(open(os.path.join(jd, "hf-graphics", "_looks", layer_name, "line.json"), encoding="utf-8")) if not e else {"offset": e["offset"], "dur": e["dur"]}
        keep_ = {k_: v_ for k_, v_ in (e or {}).items() if k_ in ("span", "words", "anchor", "after_word", "gap", "copy", "caption")}
        if keep_.get("copy") and str(meta.get("text") or "").strip():   # words she typed in Refine are its copy now: a
            keep_["copy"] = str(meta["text"]).strip()                   # later redraw never brings the old words back
        e = {"look": look_id, "dir": rel, "offset": line["offset"], "dur": line["dur"], "nudge": (e or {}).get("nudge"),
             "at": time.strftime("%Y-%m-%d %H:%M:%S"), **keep_}   # what anchors it to her words (and its own copy) stays with it
    else:
        e = {"look": look_id, "dir": rel, "nudge": (e or {}).get("nudge"), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_entry(jd, layer_name, e)
    base = os.path.join(jd, "hf-graphics", "_looks", layer_name)      # older refine copies nothing points at: gone
    keep = {f"refined-{k}", f"refined-{k - 1}"}
    for old in os.listdir(base):
        if old.startswith("refined-") and old not in keep:
            shutil.rmtree(os.path.join(base, old), ignore_errors=True)
    try:                                                     # her caption size HOLDS: written where every redraw reads it
        import lookbook as _lb                               # (review/caption-box.json), never lost on the next cut edit
        if _lb.find(look_id, meta["pack"]).get("layer") == "captions" and meta.get("size") is not None:
            _set_caption_box(jd, size=round(float(meta["size"]), 3))
    except Exception:
        pass
    looks_manifest(jd)
    return {"layer": layer_name, "look": look_id, "scope": scope, "name": name}


def look_effect(job, layer_name, effect):
    """A look's animation set FOR her (her note or the chat asked for it): `look-effect <job> <look key> <effect>`
    (`default` = the pack's own). refine() alone only draws into the Refine sandbox and keeps nothing until a Keep
    (refine_apply), so three animations reported as set from the chat never reached her preview (2026-10-23). This
    draws it and keeps it on that line, as her Refine and Keep do; an animation the look can't show is refused."""
    jd = job_dir(job)
    layers = _looks_or_fresh(jd).get("layers", [])
    L = next((l for l in layers if l["name"] == layer_name), None)
    if not L:
        raise Refuse(f"There's no look {layer_name!r} on this reel. Its looks: "
                     + (", ".join(f"{l['name']} ({l.get('look')})" for l in layers) or "none yet") + ".")
    eff = None if str(effect or "").lower() in ("", "default", "none", "pack") else str(effect)
    if L.get("look") == "media" and eff and eff not in dict(MEDIA_EFFECTS):
        raise Refuse(f"A picture's entrance can be: {', '.join(f'{n} ({k})' for k, n in MEDIA_EFFECTS)}.")
    r = refine(job, layer_name, L.get("look"), effect=eff)
    kept = refine_apply(job, layer_name, "moment")
    return {"layer": layer_name, "look": kept.get("look"), "effect": r.get("effect"), "effects": r.get("effects")}


def _this_pack_first(jd):
    try:
        pk = _swap_pack(jd, json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")))[0].lower()
    except Exception:
        pk = ""
    return lambda p: os.path.basename(os.path.dirname(p)) != f"hf-reel-type-{pk}"


def _trash_path(jd):
    return os.path.join(jd, "review", "looks-trash.json")


def _stash(jd, layer_name, kind, entry):
    """Keep what was on a line, exactly as it was (look, refine, moves), before anything replaces or removes it."""
    try:
        t = json.load(open(_trash_path(jd), encoding="utf-8"))
    except FileNotFoundError:
        t = {"layers": {}}
    except Exception:
        return                                               # never let a damaged history block her change
    lst = t.setdefault("layers", {}).setdefault(layer_name, [])
    lst.append({"kind": kind, "entry": entry, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    t["layers"][layer_name] = lst[-8:]
    _atomic_json(_trash_path(jd), t)


def bring_back(job, layer_name, phase=None):
    """Put back what was on this line before her last swap, removal or sandbox lock-in, refine and moves included.
    What's there now goes into the history in its place, so Bring back twice is a toggle, never a loss. `phase`
    "render": her page's Undo of the very last look change, so her looks are exactly as she locked them: locked again."""
    return _bring_back_relock(job, layer_name) if phase == "render" else _bring_back(job, layer_name)


@_locked
def _bring_back_relock(job, layer_name):
    """Undo of her very last look change, with her looks locked again in the same locked step (no change can slip
    in between and get locked in without her)."""
    jd = job_dir(job)
    out = _bring_back(job, layer_name)
    ph = os.path.join(jd, "review", "phase.json")
    try:
        cur = json.load(open(ph, encoding="utf-8"))
        if cur.get("phase") == "looks":
            _atomic_json(ph, dict(cur, phase="render"))
    except Exception:
        pass
    return out


@_changes_looks
@_locked
def _bring_back(job, layer_name):
    jd = job_dir(job)
    try:
        t = json.load(open(_trash_path(jd), encoding="utf-8"))
    except Exception:
        t = {"layers": {}}
    lst = (t.get("layers") or {}).get(layer_name) or []
    sw, adds = _swaps(jd), _adds(jd)
    if not lst:
        if layer_name.startswith(("add-", "cap-")) and adds.get(layer_name):   # undo an add: the line had nothing
            _stash(jd, layer_name, "add", adds.pop(layer_name))
            _atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": sw, "adds": adds, "behind": _behind(jd)})
            looks_manifest(jd)
            return {"layer": layer_name, "look": None}
        raise Refuse("There's nothing earlier to bring back on this line.")
    last = lst.pop()
    book = adds if last["kind"] == "add" else sw
    now = book.get(layer_name)
    if now:
        lst.append({"kind": last["kind"], "entry": now, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    if last["entry"] is None:                                # the line was empty before: it's empty again
        book.pop(layer_name, None)
    else:
        book[layer_name] = last["entry"]
    t["layers"][layer_name] = lst
    _atomic_json(os.path.join(jd, "review", "swaps.json"), {"swaps": sw, "adds": adds, "behind": _behind(jd)})
    _atomic_json(_trash_path(jd), t)
    looks_manifest(jd)
    return {"layer": layer_name, "look": (last["entry"] or {}).get("look")}


def can_bring_back(jd, layer_name):
    try:
        return bool(json.load(open(_trash_path(jd), encoding="utf-8")).get("layers", {}).get(layer_name))
    except Exception:
        return False


def _adopt_menu(jd, layer_name, look_id):
    """She picked a tile from Swap / Add a look: that tile (drawn in the menu's own folder) becomes the look on her line,
    with the menu's line. Opening a menu never touches the look already on the line; only a pick does."""
    base = os.path.join(jd, "hf-graphics", "_looks", layer_name)
    src = os.path.join(base, "_menu", look_id)
    if not look_id or not os.path.isdir(src):
        return
    import lookbook
    lookbook.replace_dir(src, os.path.join(base, look_id))  # in one step: her preview may have the line's page open
    ml = os.path.join(base, "_menu", "line.json")
    if os.path.isfile(ml):
        shutil.copy(ml, os.path.join(base, "line.json"))


@_changes_looks
@_locked
def swap(job, layer_name, look_id, from_menu=False, copy=None):
    """Put a look on that line (look_id), or put the original back (None). Her build's own files are never touched.
    Whatever was on the line goes to review/looks-trash.json first (her refine and her moves with it): Bring back."""
    jd = job_dir(job)
    path = os.path.join(jd, "review", "swaps.json")
    sw = _swaps(jd)
    if from_menu and look_id and layer_name.startswith("add-"):   # a hook from the menu: its own words, drawn on her line
        menu = os.path.join(jd, "hf-graphics", "_looks", layer_name, "_menu")
        rec = _read_json(os.path.join(menu, look_id, "look.json")) or {}
        if rec.get("layer") == "hook":
            copy = re.sub(r"\s+", " ", str(copy or "")).strip()[:200]
            if not copy:
                raise Refuse("A hook says its own thing, never your spoken line. Write its words in the box, or ask Claude to write them.")
            line = _read_json(os.path.join(menu, "line.json")) or {}
            s0, e0 = (line.get("span") or [line.get("offset", 0.0), float(line.get("offset", 0.0)) + float(line.get("dur", 1.0))])[:2]
            out, note = _hook_language(jd, copy, place_look(job, layer_name, float(s0), float(e0), look_id, copy=copy))
            if note:                                         # she typed it on her page: her page says it, once
                import editor_says
                editor_says.told(jd, note, kind="note", go="visuals")
            return out
    if look_id and look_id not in ("_off", "_original", "media"):   # her pick from Swap / Add a look (or nothing drawn yet)
        import glob as _g
        if from_menu or not _g.glob(os.path.join(jd, "hf-graphics", "_looks", layer_name, look_id, "hf-reel-type-*", "index.html")):
            _adopt_menu(jd, layer_name, look_id)
    if layer_name.startswith(("add-", "cap-")):
        adds = _adds(jd)
        if look_id:
            import glob
            pages = glob.glob(os.path.join(jd, "hf-graphics", "_looks", layer_name, look_id, "hf-reel-type-*", "index.html"))
            pages.sort(key=_this_pack_first(jd))
            if pages and _design_newer(pages[0]):          # her design changed since it was drawn here: draw it fresh,
                shutil.rmtree(os.path.dirname(os.path.dirname(pages[0])), ignore_errors=True)   # never the old one
                pages = []                                   # (2026-10-18: a look note's fix kept showing the old drawing)
            if not pages:                                    # not drawn for this line yet: draw it now, on the line's words
                base_ = os.path.join(jd, "hf-graphics", "_looks", layer_name)
                ln_ = _read_json(os.path.join(base_, "line.json")) or _read_json(os.path.join(base_, "_menu", "line.json")) or {}
                sp_ = ln_.get("span") or (adds.get(layer_name) or {}).get("span")
                if sp_:
                    return place_look(job, layer_name, float(sp_[0]), float(sp_[1]), look_id, copy=copy)
                raise Refuse("That look's line couldn't be found. Open Swap on the line again and pick it there.")
            line = json.load(open(os.path.join(jd, "hf-graphics", "_looks", layer_name, "line.json"), encoding="utf-8"))
            keep_nudge = (adds.get(layer_name) or {}).get("nudge")   # where she moved it stays where she moved it
            new_dir = os.path.relpath(os.path.dirname(pages[0]), jd).replace(os.sep, "/")
            prev = adds.get(layer_name)
            if prev and (prev.get("look") != look_id or prev.get("dir") != new_dir):
                _stash(jd, layer_name, "add", prev)
            elif not prev and can_bring_back(jd, layer_name):   # an empty line with history (a look she took off): its
                _stash(jd, layer_name, "add", None)              # Undo leaves it empty, never brings that old look back
            adds[layer_name] = {"look": look_id, "dir": os.path.relpath(os.path.dirname(pages[0]), jd).replace(os.sep, "/"),
                                "offset": line["offset"], "dur": line["dur"], "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                **({"span": line["span"]} if line.get("span") else {}),
                                **({"words": line["words"]} if line.get("words") else {}),
                                **({"anchor": line["anchor"]} if line.get("anchor") else {}),
                                "caption": os.path.isfile(os.path.join(jd, "hf-graphics", "_looks", layer_name, "kind.json")),
                                **({"nudge": keep_nudge} if keep_nudge else {})}
        else:
            if adds.get(layer_name):
                _stash(jd, layer_name, "add", adds[layer_name])
            adds.pop(layer_name, None)
        _atomic_json(path, {"swaps": sw, "adds": adds, "behind": _behind(jd)})
        looks_manifest(jd)
        return {"swapped": look_id, "layer": layer_name}
    if sw.get(layer_name) and sw[layer_name].get("look") != look_id:
        _stash(jd, layer_name, "swap", sw[layer_name])        # her swapped-in look (refine, moves) before it changes
    if look_id == "_off":                                    # off her final video; nothing of her build is deleted
        sw[layer_name] = {"look": "_off", "dir": "", "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        _atomic_json(path, {"swaps": sw, "adds": _adds(jd), "behind": _behind(jd)})
        looks_manifest(jd)
        return {"swapped": "_off", "layer": layer_name}
    if look_id:
        import glob
        pages = glob.glob(os.path.join(jd, "hf-graphics", "_looks", layer_name, look_id, "hf-reel-type-*", "index.html"))
        pages.sort(key=_this_pack_first(jd))
        rel = os.path.relpath(os.path.dirname(pages[0]), jd).replace(os.sep, "/") if pages else ""
        if not pages:                                        # not drawn for this graphic yet: draw its menu now, then take it
            try:
                swap_menu(job, layer_name); _adopt_menu(jd, layer_name, look_id)
            except Refuse:
                pass
            pages = sorted(glob.glob(os.path.join(jd, "hf-graphics", "_looks", layer_name, look_id, "hf-reel-type-*", "index.html")), key=_this_pack_first(jd))
            rel = os.path.relpath(os.path.dirname(pages[0]), jd).replace(os.sep, "/") if pages else ""
        if not pages:
            raise Refuse("That look can't be drawn on this graphic. Pick another one from Swap.")
        keep_nudge = (sw.get(layer_name) or {}).get("nudge")
        sw[layer_name] = {"look": look_id, "dir": rel, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **({"nudge": keep_nudge} if keep_nudge else {})}
    else:
        sw.pop(layer_name, None)
    _atomic_json(path, {"swaps": sw, "adds": _adds(jd), "behind": _behind(jd)})
    looks_manifest(jd)
    return {"swapped": look_id, "layer": layer_name}


@_locked
def looks_manifest(jd):
    """review/looks.json: the reel's graphics (where each starts in the cut) and its creative-plan beats.
    Nothing to show (a raw-route reel, or no build yet) writes nothing and removes a stale list."""
    out = os.path.join(jd, "review", "looks.json")
    layers, seen, from_sheet = [], {}, set()

    def add(rel, offset=0.0, behind=False, build=False, sheet=False):
        c = _comp(jd, rel, offset, bool(behind))
        if not c:
            return
        if c["dir"] not in seen:
            seen[c["dir"]] = c; layers.append(c)
            if sheet:
                from_sheet.add(c["dir"])
        elif build and c["dir"] in from_sheet:
            # the reel's own build lists say where a graphic plays and whether it sits behind her: the beat sheet's
            # copy (made before a re-time) keeps its place in the stack but never outvotes them
            from_sheet.discard(c["dir"])
            seen[c["dir"]]["offset"] = c["offset"]
            if behind is not None:                           # a plain windows list says nothing about behind
                seen[c["dir"]]["behind"] = c["behind"]

    beats_file = os.path.join(jd, "beat-sheet", "beats.json")
    meta = {}
    try:
        meta = json.load(open(beats_file, encoding="utf-8"))
        for l in meta.get("layers", []):
            d_ = str(l.get("dir", "")).replace(os.sep, "/")
            if d_.startswith("hf-graphics/_"):              # her added looks (_looks) and proposal sketches a beat sheet
                continue                                     # shows: never the reel's own layers (they doubled on her page)
            add(l.get("dir", ""), l.get("offset", 0.0), sheet=True)
    except Exception:
        pass
    hg = os.path.join(jd, "hf-graphics")
    for name in ("plan.json", "windows.json"):          # the per-reel build's own lists of where each graphic plays
        try:
            d = json.load(open(os.path.join(hg, name), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, list):
            for x in d:
                add(os.path.join("hf-graphics", x.get("name", "")), x.get("at", 0.0), x.get("layer") == "behind", build=True)
        else:
            win = d.get("windows", d)
            for k, v in win.items():
                if isinstance(v, list) and len(v) == 2 and all(isinstance(n, (int, float)) for n in v):
                    add(os.path.join("hf-graphics", k), v[0], None, build=True)
    for name in sorted(os.listdir(jd)) if os.path.isdir(jd) else []:   # whole-reel layers (type, captions) start at 0
        if name.startswith("hf-reel-type-") or name == "hf-captions":
            add(name, 0.0)
    swaps = _swaps(jd)                                       # a look she swapped in plays in place of the original
    reel_pack = _reel_pack(jd) or meta.get("pack") or _default_pack()
    _pk = _swap_pack(jd, {"pack": reel_pack})[0] if reel_pack else None

    def _named(look_id):
        if look_id == "_original":
            return "Your original, moved", ""
        try:
            import lookbook
            lk = lookbook.find(look_id, _pk)
            return lk["name"], lk["about"]
        except Exception:
            return look_id.replace("-", " ").capitalize(), ""
    for l in layers:
        # captions-only layers swap reel-wide (karaoke / single word); a whole-reel type page (hook + cards + captions
        # in one) is not a caption swap, and no whole-reel layer is ever a line's look
        l["captions"] = l["name"] in ("captions", "hf-captions") or (l["name"].startswith("hf-reel-type") and _captions_only(jd, l["dir"]))
        whole = l["dur"] is None or (l["offset"] == 0 and l["dur"] > 30) or l["captions"] or l["name"].startswith("hf-reel-type")
        sw = swaps.get(l["name"])
        if sw and sw.get("look") == "_off":
            l.update(off=True, look="_off", look_name="Removed")
            sw = None
        if sw and sw.get("look") == "_original" and not l.get("captions"):   # her moved copy keeps up with the original
            try:
                _refresh_moved_copy(jd, l["dir"], sw["dir"], sw.get("nudge"))
            except Exception:
                pass
        if sw and os.path.isfile(os.path.join(jd, sw.get("dir", ""), "index.html")):
            c = _comp(jd, sw["dir"], l["offset"], l["behind"])
            if c:
                l.update(dir=c["dir"], id=c["id"], dur=c["dur"], look=sw["look"], original=l["dir"])
                l["look_name"], l["look_about"] = _named(sw["look"])
                l["nudge"] = sw.get("nudge") or [0, 0]       # a move lives only in HER copy, never her build's page
                _apply_nudge(jd, l["dir"], sw.get("nudge"))
        l["swappable"] = not whole and l["dur"] <= 30
        l["movable"] = True                                  # anything on screen can move (the first move makes her copy)
        if l["name"] in _behind(jd):                         # she put it behind her head (the render does it with her cutout)
            l["behind"] = _behind(jd)[l["name"]]
    back = _behind(jd)
    for key, a in (_adds(jd)).items():                       # a look she added to a line that had none
        if os.path.isfile(os.path.join(jd, a["dir"], "index.html")):
            c = _comp(jd, a["dir"], a["offset"], bool(back.get(key)))   # behind her head: her own looks too, not just the reel's
            if c:
                c.update(name=key, look=a["look"], added=True, swappable=True, captions=(key == "cap-all"), movable=True, nudge=a.get("nudge") or [0, 0],
                         span=a.get("span"))
                _apply_nudge(jd, a["dir"], a.get("nudge"))
                c["look_name"], c["look_about"] = _named(a["look"])
                if a["look"] == "media":                     # her own file: named by what it is
                    m = media_of(jd, key) or {}
                    c["look_name"], c["look_about"], c["media"] = f"{m.get('kind', 'Image')}: {m.get('name', 'yours')}", "Your own, from your favorites", m.get("media")
                    if m.get("kind") == "Video" and m.get("file"):   # a b-roll cutaway: what its sheet needs to slip it
                        c["look_name"], c["look_about"] = f"B-roll: {m.get('name', 'yours')}", "Your clip, cut away to over these words"
                        c["cutaway"] = {"src": m["file"], "clip_dur": m.get("clip_dur"), "slip": m.get("slip", 0),
                                        "best": m.get("best"), "sound": bool(m.get("sound")), "effect": m.get("effect", "cut")}
                layers.append(c)
    # NO TWO WORD LOOKS AT ONCE (the yield rule, held here whatever placed them): a takeover or a line's caption
    # style is cut off where the next one starts, so two caption styles never share a frame. A look placed earlier,
    # one she refined, or one a cut change left behind used to run its tail into its neighbour (2026-10-17).
    try:
        import lookbook as _lbw
        _wordy = lambda l: (not l.get("captions") and not l.get("off") and l.get("dur") is not None and
                            (l.get("look") in _lbw.CAPTION_LOOKS or l.get("look") == "takeover" or _says_her_words(jd, l)
                             or _hides_captions(jd, l)))
        # (any look that shows the words she is saying counts, a design of hers too: its words replace the line
        # look's, never both at once; 2026-10-17 her Phrase and her Snip burst showed the same words twice)
        _wl = sorted((l for l in layers if _wordy(l)), key=lambda l: float(l["offset"]))
        for _a, _b in zip(_wl, _wl[1:]):
            if float(_a["offset"]) + float(_a["dur"]) > float(_b["offset"]) + 1e-3:
                _a["dur"] = round(max(0.3, float(_b["offset"]) - float(_a["offset"])), 3)
        # ...and it leaves as she starts her NEXT word: a look's hold after its own words used to hide the captions of
        # the words she said right after it (2026-10-21: "Just kidding." held 0.4 s and "today" never showed)
        for _a in _wl:
            if not _a.get("span"):
                continue
            _o, _se = float(_a["offset"]), float(_a["span"][1])
            _nx = [w for w in _line_words(jd, _se + 0.02, _o + float(_a["dur"])) if w["t"] > 0]
            if _nx:
                _a["dur"] = round(max(0.3, _se + 0.02 + _nx[0]["t"] - _o), 3)
    except Exception:
        pass
    capL = next((l for l in layers if l.get("captions")), None)
    # captions that step aside for a line's own caption style; never for themselves (captions she added with
    # Captions: add ARE a caption add, and stepping aside for themselves hid them for the whole reel in her export)
    skips = [(a["offset"], a["offset"] + a["dur"]) for k, a in _adds(jd).items()
             if a.get("caption") and not (capL and k == capL["name"])]
    if capL:
        # her captions step aside wherever a karaoke, takeover or other caption-style look plays, so words never double:
        # a new caption style knows nothing of the reel's other word looks, and an older build's own captions didn't
        # always stand aside for its karaoke either (the editor's copy steps aside; her build is never touched)
        try:
            import lookbook as _lb
            capish = set(_lb.CAPTION_LOOKS)
        except Exception:
            capish = {"karaoke", "single-word", "phrase", "spotlight", "takeover"}
        for l in layers:
            if l is capL or l.get("off") or l.get("dur") is None:
                continue
            nm = l["name"].lower()
            restyled = l.get("look") in capish or "karaoke" in nm or "takeover" in nm or "caption" in nm   # a caption style
            over = _spot_of(jd, l, _pk or reel_pack) == "full"   # a full-screen look sits on top of her captions: they
            if restyled or ((_says_her_words(jd, l) or _hides_captions(jd, l) or over) and not _keeps_captions(jd, l)):
                skips.append((l["offset"], l["offset"] + l["dur"]))   # clash, so the captions step aside under it by default
    if capL:                                                 # ONLY a look that shows her words replaces them: a full-screen
        skips = _merge_spans(skips)                          # card, a collage, a picture leaves her captions on (her rule)
    if capL:
        e, _ = _entry(jd, capL["name"])
        if skips and not e:                                  # captions stepping aside need her copy, never her build
            e = _working_copy(jd, capL["name"], capL)
            c = _comp(jd, e["dir"], capL["offset"], capL["behind"])
            if c:
                capL.update(dir=c["dir"], id=c["id"], look="_original", original=capL["dir"], look_name="Your original, moved", nudge=[0, 0])
        if e:
            _apply_skips(jd, capL["dir"], capL["id"], skips, offset=capL.get("offset"))
        capL["skips"] = skips
    beats = []
    try:
        for b in json.load(open(os.path.join(jd, "graphics-plan.json"), encoding="utf-8")).get("beats", []):
            if b.get("element") and b.get("element") != "face":
                beats.append({k: b.get(k) for k in ("id", "start", "end", "line", "element", "zone", "idea", "on_screen")})
    except Exception:
        pass
    clean = not layers and not beats and _chose_clean(jd)      # a clean reel on purpose: the page moves on to Sound and Finish
    vo = bool(voiceover_of(jd))                              # a voiceover's Visuals opens with her cut: her clips go on there
    vo_open = vo and not layers and not beats and ((_phase_now(jd) or {}).get("phase") in ("looks", "render"))
    if not layers and not beats and not clean and not vo_open:
        if os.path.exists(out):
            os.remove(out)
        return None
    # the beat sheet's own words for each moment (what it is, what moves), when this reel has one; without one,
    # each windowed graphic is a moment of its own, named from its folder
    moments = [{k: b.get(k) for k in ("t", "kind", "says", "motion")} for b in meta.get("beats", []) if isinstance(b, dict) and "t" in b]
    if not moments:
        moments = [{"t": round(l["offset"] + min(0.6, (l["dur"] or 1) / 2), 2), "kind": re.sub(r"^[a-z]?\d+-", "", l["name"]).replace("-", " ").capitalize(),
                    "says": "", "motion": ""} for l in layers if l["dur"] is not None and not l.get("added") and not l.get("captions")
                   and not l["name"].startswith(("hf-", "captions"))]
    _look_frames(jd, moments, prune=False)
    for l in layers:                                         # an added look is a moment of its own
        if l.get("added"):
            moments.append({"t": round(l["offset"] + min(0.6, (l["dur"] or 1) / 2), 2), "kind": l.get("look_name", "Look"),
                            "says": "", "motion": l.get("look_about", ""), "layer": l["name"], "added": True})
    moments.sort(key=lambda m: m["t"])
    _look_frames(jd, moments, prune=False)
    taken = set()
    for m in moments:                                        # which graphic each moment shows (the one a Swap changes)
        if m.get("added"):
            taken.add(m["layer"]); continue
        # an old beat-sheet note never attaches to a look she added; captions/accent notes are reel-wide, not a line's look
        on = [l for l in layers if l.get("swappable") and not l.get("added") and l["name"] not in taken
              and l["offset"] - 0.05 <= m["t"] <= l["offset"] + (l["dur"] or 0) + 0.05]
        if on and str(m.get("kind", "")).lower() in ("captions", "accent word", "accent words"):
            on = []
        if on:
            taken.add(on[0]["name"])
        m["layer"] = on[0]["name"] if on else None
        if on and on[0].get("look_name") and on[0].get("look") not in ("_original", "_off"):   # a look she swapped in: its name
            m.update(kind=on[0]["look_name"], motion=on[0].get("look_about", ""), swapped=True)
    # every graphic on her reel has a card she can swap, move or remove, however it got there (a beat sheet that
    # missed it, a look drawn straight into the build): one with no moment yet gets one of its own
    for l in layers:
        if l.get("swappable") and not l.get("added") and not l.get("off") and l["name"] not in taken:
            kind = re.sub(r"^[a-z]?\d+-", "", l["name"]).replace("-", " ")
            moments.append({"t": round(l["offset"] + min(0.6, (l["dur"] or 1) / 2), 2), "kind": l.get("look_name") or kind[:1].upper() + kind[1:],
                            "says": "", "motion": l.get("look_about", ""), "layer": l["name"]})
            taken.add(l["name"])
    moments.sort(key=lambda m: m["t"])
    _look_frames(jd, moments)
    accents = None
    for l in layers:                                         # the reel's captions: the words she can accent
        if l["name"] in ("captions", "hf-captions", "cap-all") or l["name"].startswith("hf-reel-type"):   # cap-all: captions she added
            accents = _caption_words(jd, l)
            if accents:
                break
    if accents and accents.get("mode") != "redraw" and accents.get("cls"):
        # her highlights reach her export: the words she turned on or off, written into her copy (never her build)
        mine = _accent_items(jd)                             # by her word, on her current cut
        toggles = []
        for w in accents["words"]:
            hit = next((x for x in mine if abs(float(x.get("t", -9)) - w["t"]) < 0.15 and str(x.get("text", "")).strip(" .,!?") == str(w["text"]).strip(" .,!?")), None)
            if hit is not None and bool(hit.get("on")) != bool(w["on"]) and w.get("sel"):
                toggles.append((w["sel"], bool(hit.get("on")), bool(w["on"])))
        aL = next((l for l in layers if l["name"] == accents["layer"]), None)
        if aL:
            e_, _ = _entry(jd, aL["name"])
            if toggles and not e_:
                e_ = _working_copy(jd, aL["name"])
                c_ = _comp(jd, e_["dir"], aL["offset"], aL["behind"])
                if c_:
                    aL.update(dir=c_["dir"], id=c_["id"], look="_original", original=aL["dir"], look_name="Your original, moved", nudge=[0, 0])
            if e_:
                _apply_accents(jd, aL["dir"], toggles, accents["cls"], accents.get("scale", 1.0))
    subject = None
    try:
        z = json.load(open(os.path.join(jd, "subject-zones.json"), encoding="utf-8"))
        subject = z.get("face") or z.get("subject")          # the page's checks: where her face usually is, when measured
    except Exception:
        pass
    _sz = frame.zones(jd)
    try:
        made_for = looks_cut(jd)
    except Exception:
        made_for = None
    try:                                                     # where each look sits (top / card / full): the page's checks read it
        import lookbook as _lbs
        for L in layers:
            lk = L.get("look")
            if lk and lk not in ("_original", "_off", "media"):
                L["spot"] = _spot(_lbs, lk, reel_pack) or ("full" if os.path.isfile(os.path.join(jd, L["dir"], "owns-screen.json")) else None)
            elif not L.get("captions") and lk != "media" and os.path.isfile(os.path.join(jd, L.get("dir", ""), "owns-screen.json")):
                L["spot"] = "full"
    except Exception:
        pass
    for L in layers:                                         # a look that shows her spoken words follows her voice (the checks
        if not L.get("captions") and not L.get("off") and L.get("dur") is not None and _says_her_words(jd, L):   # skip reading speed)
            L["says"] = True
    drift = drifted_adds(jd)                                 # the failsafe: a look plays on its own words, whatever a marker says
    if drift and made_for:
        made_for = "off-its-words"                           # never her cut's id: the page moves them back onto their words
    for L in layers:                                         # made by hand for this one reel: a pack switch can't restyle it
        if L.get("off") or str(L["name"]).startswith(("add-", "cap-")):
            continue
        if (L.get("look") in (None, "_original") and not _orig_record(jd, L)) or \
                (L.get("look") not in (None, "_original", "_off") and "hf-reel-type-" not in str(L.get("dir", ""))):
            L["fixed"] = True                                # (the second: an older one-off look, no pack page to redraw)
    data = {"version": 1, "route": meta.get("route"), "pack": reel_pack, "built_pack": meta.get("pack"), "layers": layers, "beats": beats, "made_for": made_for,
            **({"clean": True} if clean else {}), **({"voiceover": True} if vo else {}),
            "can_behind": can_behind(), "redo": looks_to_redo(jd), "grade": grade_of(jd),
            "ideas": [{k: r.get(k) for k in ("id", "w", "status", "mode", "takes", "tried", "idea", "start", "end", "working", "media")}
                      for r in _requests(jd) if r.get("status") in ("open", "draft", "takes")],
            "subject": subject, "safe": {"top": _sz.TOP, "bottom": _sz.BOTTOM, "left": _sz.LEFT, "right": _sz.RIGHT, "rail": _sz.RIGHT_RAIL, "w": _sz.W, "h": _sz.H},
            "checks_ok": checks_ok(jd, layers),
            "moments": moments, "accents": accents}
    for L in layers:                                         # each look's page version: a look redrawn into the SAME folder
        try:                                                 # (new skips, a new offset) is a new address, so her page never
            L["v"] = int(os.stat(os.path.join(jd, L["dir"], "index.html")).st_mtime_ns // 1_000_000)   # plays an old copy
        except (OSError, KeyError, TypeError):
            pass
    _atomic_json(out, data)
    return data

def _still_words(data):
    """The words whose stills her timeline shows: the first word of every line and of every piece of her cut (one
    block per piece, so a line made of several pieces shows each)."""
    firsts = {ids[0] for ids in data.get("lines") or [] if ids}
    firsts |= {g["w"][0] for g in data.get("segs") or [] if g.get("w")}
    return sorted(firsts)


_STILL_LOCK = _threading.Lock()                       # page threads make stills at the same time


def _still_stamp(preview, t):
    """What a still was made from: the preview (its size and time) and the moment in it."""
    st = os.stat(preview)
    return f"{st.st_size}:{int(st.st_mtime)}:{t:.2f}"


def _still_fresh(review, i, data):
    """True when strip/w{i}.jpg exists AND was made from this preview at word i's moment. A still made once and never
    remade showed footage from an older cut after a re-cut (another moment, or a clip no longer in her reel)."""
    out = os.path.join(review, "strip", f"w{i}.jpg")
    preview = os.path.join(review, "preview.mp4")
    words = data.get("words") or []
    if not (os.path.isfile(out) and os.path.getsize(out) > 0 and os.path.isfile(preview) and 0 <= i < len(words)):
        return False
    try:
        made = json.load(open(os.path.join(review, "strip", "stamps.json"), encoding="utf-8")).get(f"w{i}")
    except Exception:
        made = None
    return made == _still_stamp(preview, max(0.0, float(words[i]["s"]) + 0.15))


def make_still(jd, data, i):
    """The timeline still for word i (from the preview, a beat into the word); True when it exists afterwards.
    Remade whenever the preview or the word's moment changed (strip/stamps.json says what each was made from)."""
    review = os.path.join(jd, "review")
    preview = os.path.join(review, "preview.mp4")
    strip = os.path.join(review, "strip"); os.makedirs(strip, exist_ok=True)
    out = os.path.join(strip, f"w{i}.jpg")
    if _still_fresh(review, i, data):
        return True
    words = data.get("words") or []
    if not (0 <= i < len(words)) or not os.path.exists(preview):
        return os.path.isfile(out) and os.path.getsize(out) > 0
    t = max(0.0, float(words[i]["s"]) + 0.15)            # word times are already the preview's
    stamp = _still_stamp(preview, t)
    tmp = out + f".{os.getpid()}.{_threading.get_ident()}.tmp.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", preview, "-frames:v", "1",
                    "-vf", "scale=-2:96", "-q:v", "6", tmp], capture_output=True)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, out)
        sp = os.path.join(strip, "stamps.json")
        with _STILL_LOCK:
            try:
                stamps = json.load(open(sp, encoding="utf-8"))
            except Exception:
                stamps = {}
            stamps[f"w{i}"] = stamp
            _atomic_json(sp, stamps)
        return True
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def timeline_assets(jd, data):
    """What makes the page's timeline look like a video editor's: a still for each line (from its first word) and
    the sound's waveform, both made from the lean preview in a couple of seconds and only when missing."""
    review = os.path.join(jd, "review")
    preview = os.path.join(review, "preview.mp4")
    if not os.path.exists(preview):
        return
    for i in _still_words(data):
        make_still(jd, data, i)
    peaks = os.path.join(review, "peaks.json")
    if not os.path.exists(peaks) or os.path.getmtime(peaks) < os.path.getmtime(preview):
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", preview, "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", "4000", "-f", "s16le", "-"],
                           capture_output=True)
        import array
        a = array.array("h"); a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
        step = 100                                        # 25 ms of sound per value
        vals = [max((abs(x) for x in a[k:k + step]), default=0) for k in range(0, len(a), step)]
        top = max(vals) or 1
        if vals:                                          # no sound read: leave it missing, so the next look tries again
            _atomic_json(peaks, {"rate": 40, "peaks": [round(100 * v / top) for v in vals]})


def editor_health(job, repair=True, preview=True, log=None):
    """What her page needs to look whole, checked from the files on disk (never from what a build meant to make): her
    preview, a still for every line, the waveform, each one present, non-empty and made from the current preview.
    A brand-new reel once opened with no waveform and no stills because they were made before the preview existed;
    this catches that, and anything like it, from the result. repair=True rebuilds what is missing from what exists
    (preview=False skips rebuilding the preview itself, which takes a while: the page server's quick self-heal).
    Returns {"missing": [...], "fixed": [...], "still_missing": [...]}."""
    jd = job_dir(job)
    review = os.path.join(jd, "review")
    pv = os.path.join(review, "preview.mp4")

    def check():
        miss = []
        try:
            data = json.load(open(os.path.join(review, "script.json"), encoding="utf-8"))
        except Exception:
            return ["script"], None
        if not (os.path.isfile(pv) and os.path.getsize(pv) > 0):
            miss.append("preview")
            return miss, data
        pk = os.path.join(review, "peaks.json")
        try:
            ok = (len(json.load(open(pk, encoding="utf-8")).get("peaks") or []) > 0
                  and os.path.getmtime(pk) >= os.path.getmtime(pv))
        except Exception:
            ok = False
        if not ok:
            miss.append("waveform")
        for i in _still_words(data):
            if not _still_fresh(review, i, data):            # missing, or made from an older cut
                miss.append(f"still w{i}")
        return miss, data

    missing, data = check()
    if not missing or not repair:
        return {"missing": missing, "fixed": [], "still_missing": missing}
    try:
        if "script" in missing:
            data = build_script(job)
        if preview and (data is None or "preview" in missing or "script" in missing):
            make_preview(job, log=log or (lambda *_: None))
        if data is not None:
            timeline_assets(jd, data)
    except Exception as e:
        if log:
            log(f"  couldn't rebuild part of her page ({e})")
    after, _ = check()
    fixed = [m for m in missing if m not in after]
    if log and fixed:
        stills = sum(1 for m in fixed if m.startswith("still"))
        named = [m for m in fixed if not m.startswith("still")] + ([f"{stills} timeline still{'s' * (stills != 1)}"] if stills else [])
        log("  made what her page was missing: " + ", ".join(named))
    return {"missing": missing, "fixed": fixed, "still_missing": after}


# ── the preview copy: her clips back to back, small and fast to make ─────────────────────────────────────────
def _canvas(path):
    """Portrait (540x960) or landscape (960x540), from how the clip DISPLAYS (rotation flag honoured)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:stream_side_data=rotation:stream_tags=rotate", "-of", "json", path],
                           capture_output=True, text=True, timeout=60)
        st = json.loads(r.stdout)["streams"][0]
        w, h = int(st["width"]), int(st["height"])
        rot = abs(int(float((st.get("tags") or {}).get("rotate", 0) or
                            next((d.get("rotation", 0) for d in st.get("side_data_list", []) if "rotation" in d), 0))))
        if rot % 180 == 90:
            w, h = h, w
        return (960, 540) if w > h else (540, 960)
    except Exception:
        return (540, 960)


PREVIEW_STALL_S = 300   # the preview copy's ffmpeg is stopped only after this long with no progress at all
PREVIEW_TICK_S = 20     # how often its progress is said while it runs


def _mmss(s):
    return f"{int(s // 60)}:{int(s % 60):02d}"


def _watched_ffmpeg(cmd, total, log, stall_s=None, tick_s=None):
    """Run an ffmpeg encode (given -nostdin -progress pipe:1), reading its progress as it goes: says how far it is every PREVIEW_TICK_S,
    and stops it once nothing has moved for PREVIEW_STALL_S (a stuck decoder, a file it can't read), so the open never
    sits silent with no end. An encode that keeps moving, however slowly, is never stopped. 2026-10-21: a first open of
    15 minutes of footage ran with no output and no time limit, and looked dead."""
    import threading, types
    stall_s, tick_s = (PREVIEW_STALL_S if stall_s is None else stall_s), (PREVIEW_TICK_S if tick_s is None else tick_s)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                         encoding="utf-8", errors="replace")
    st, err = {"done": 0.0, "moved": time.time()}, []

    def _progress():
        for line in p.stdout:
            k, _, v = line.strip().partition("=")
            if k in ("out_time_us", "out_time_ms"):              # both are microseconds in ffmpeg's progress
                try:
                    s = int(v) / 1e6
                except ValueError:
                    continue
                if s > st["done"]:
                    st["done"], st["moved"] = s, time.time()

    def _errors():
        for line in p.stderr:
            err.append(line)

    readers = [threading.Thread(target=f, daemon=True) for f in (_progress, _errors)]
    for t in readers:
        t.start()
    said, stalled = time.time(), False
    while p.poll() is None:
        time.sleep(0.25)
        now = time.time()
        if now - st["moved"] > stall_s:
            stalled = True
            p.kill()
            break
        if now - said >= tick_s:
            log(f"  preview copy: {_mmss(st['done'])} of {_mmss(total)} made")
            said = now
    p.wait()
    for t in readers:
        t.join(timeout=2)
    return types.SimpleNamespace(returncode=p.returncode if not stalled else -9, stderr="".join(err), stalled=stalled,
                                 done=st["done"])


PREVIEW_SLACK_S = 0.5   # how much shorter than her cut needs a preview copy may come out (frame and sound rounding)


def _preview_need(clips, segs, durs):
    """How long her preview copy must be (preview seconds) for every word and every piece of her cut to have footage
    under it, and the clips whose own footage ends before their words do ([(clip, footage s, words s)]). Each clip must
    reach the end of its last word and of its last piece; it is counted only as far as its footage goes (the copy is
    her clips back to back, it can't be longer), so a clip that is itself too short is named, never rebuilt for ever."""
    names = {c["clip"]: i for i, c in enumerate(clips)}
    want = [0.0] * len(clips)
    for w in words_of(clips):
        want[w["c"]] = max(want[w["c"]], float(w["e"]))
    for sg in segs:
        i = names.get(sg.get("clip"))
        if i is not None:
            try:
                want[i] = max(want[i], float(sg.get("end") or 0))
            except (TypeError, ValueError):
                pass
    need, acc, short = 0.0, 0.0, []
    for i, c in enumerate(clips):
        d = durs[i] if durs[i] is not None else float(c.get("duration") or 0)
        if want[i] > d + PREVIEW_SLACK_S:
            short.append((c["clip"], d, want[i]))
        need = max(need, acc + min(want[i], d))
        acc += d
    return round(need, 3), short


def preview_length(job):
    """{"have": the preview copy's length (None: none, or unreadable), "need": what her script and cut need, "short":
    True when the copy ends before that, "clips": her clips whose own footage ends before their words}."""
    jd, clips, segs, *_ = load(job)
    paths = [_clip_path(jd, c) for c in clips]
    need, short = _preview_need(clips, segs, [_duration(p) for p in paths])
    out = os.path.join(jd, "review", "preview.mp4")
    have = _duration(out) if os.path.isfile(out) else None
    return {"have": have, "need": need, "short": have is None or have + PREVIEW_SLACK_S < need,
            "clips": [c for c, *_ in short]}


def _say_short_clips(short, log):
    for name, d, w in short:
        log(f"Her clip {name!r} is {_mmss(d)} long, but her transcript and cut use it up to {_mmss(w)}: the copy in "
            "raw/ looks like a different, shorter file than the one she filmed. Put the original back in raw/ under "
            "the same name, then open the editor again; until then the part past "
            f"{_mmss(d)} has no footage to play.")


# How the preview copy is made, part of what .preview-of records: a copy made by an older recipe is made again on the
# next open after an update, through the same check that catches changed clips. 2: her voice at her cut's level (the
# page plays her voice from the video itself, which can't go past 100%; 2026-10-26).
PREVIEW_RECIPE = 2


def _preview_sig(paths):
    clips = [[os.path.basename(p), os.path.getsize(p), int(os.path.getmtime(p))] for p in paths]
    return json.dumps({"recipe": PREVIEW_RECIPE, "clips": clips})


def _level_preview(path, log):
    """Her preview copy's voice at her cut's level (product/voice_level.py: one static gain to the north star, a
    true-peak limiter, the picture copied untouched). The page plays her voice from the video element, which stops at
    100%, and her unmastered phone voice sits about 15 dB under her cut. Never a dead end: a copy that can't be levelled
    plays as it is (the page takes what her voice is still owed off her effects and music)."""
    try:
        import voice_level
        r = voice_level.level(path)
    except Exception as e:
        r = {"changed": False, "why": str(e)}
    if not r.get("changed") and r.get("why") and r.get("why") != "no voice to measure":
        log(f"(her preview copy plays at her clip's own level: {r['why']})")
    return r


def make_preview(job, force=False, log=print):
    """Her clips back to back, small and fast to make: the footage her page plays. Made again when her clips changed
    (.preview-of), when force=True, and when the copy on disk is shorter than her script and cut need: a short copy
    once played 0.1 s and froze, because her cut started past its end (a buyer, 2026-10-25). Each copy is made beside
    the old one and swapped in only once it is whole and long enough, so a stopped or cut-short encode never stands in
    for her footage."""
    jd, clips, segs, *_ = load(job)
    paths = [_clip_path(jd, c) for c in clips]
    out = os.path.join(jd, "review", "preview.mp4")
    stamp = os.path.join(jd, "review", ".preview-of")
    known_short = os.path.join(jd, "review", ".preview-short")
    sig = _preview_sig(paths)
    durs = [_duration(p) for p in paths]
    need, short_clips = _preview_need(clips, segs, durs)
    _say_short_clips(short_clips, log)

    def _read(p):
        try:
            return open(p, encoding="utf-8").read()
        except OSError:
            return None

    if not force and os.path.exists(out) and _read(stamp) == sig:
        have = _duration(out)
        if have is not None and have + PREVIEW_SLACK_S >= need:
            return out
        if have is not None and _read(known_short) == sig:
            return out                           # made fresh from these very clips and still short: said, not redone
        log(f"Your preview copy is {_mmss(have) if have is not None else 'unreadable'}"
            f"{' long' if have is not None else ''}, but your cut needs {_mmss(need)} of footage: making it again.")
    elif not force and os.path.exists(out) and _read(stamp) and '"recipe": %d' % PREVIEW_RECIPE not in _read(stamp):
        log("Your preview copy was made by an earlier version of the engine: making it again, once, so your voice "
            "plays at your cut's level.")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    W, H = _canvas(paths[0])
    from video_encoder import pick_encoder, graph_args, remove_graph
    enc = pick_encoder(vbr="1500k", crf=28, preset="veryfast")
    chains = [f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
              f"setsar=1,fps=30,format=yuv420p[v{i}];[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]"
              for i in range(len(paths))]
    graph = ";".join(chains) + ";" + "".join(f"[v{i}][a{i}]" for i in range(len(paths))) + \
        f"concat=n={len(paths)}:v=1:a=1[v][a]"
    tmp = out + ".part.mp4"
    gfile = out + ".graph.txt"
    total = sum(d or 0 for d in durs)
    log(f"Making the preview copy of your footage ({int(total // 60)}:{int(total % 60):02d} of video). "
        "This happens once per reel.")

    def run(hw):
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-y"]
        for p in paths:
            cmd += (["-hwaccel", "videotoolbox"] if hw else []) + ["-i", p]
        # One chain per clip: a reel of many clips goes over its graph in a file (WinError 206 past 32,767 characters).
        cmd += [*graph_args(graph, gfile), "-map", "[v]", "-map", "[a]", *enc,
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", tmp]
        try:
            return _watched_ffmpeg(cmd, total, log)
        finally:
            remove_graph(gfile)

    def made():                                  # the new copy's length, or None when there is no whole copy
        return _duration(tmp) if os.path.exists(tmp) and os.path.getsize(tmp) >= 1000 else None

    t0 = time.time()
    hw = sys.platform == "darwin"                # Apple's hardware decoder makes 4K HEVC far quicker to read
    r = run(hw)
    got = made() if r.returncode == 0 else None
    if hw and (got is None or got + PREVIEW_SLACK_S < need):
        # failed, or "finished" short (a decoder that gave up partway still exits 0): read her clips in software
        r = run(False)
        got = made() if r.returncode == 0 else None
    if r.returncode != 0 or got is None:
        if os.path.exists(tmp):
            os.remove(tmp)
        if r.stalled:
            raise Refuse(f"The preview copy of her footage stopped moving at {_mmss(r.done)} of {_mmss(total)} (nothing new "
                         f"for {PREVIEW_STALL_S // 60} minutes), so it was stopped instead of left hanging. Type \"open my "
                         "visual editor\" to try again; if it stops at the same place, /report-a-problem. The text-only "
                         "style plan still works.")
        raise Refuse("The preview copy couldn't be made (ffmpeg said: "
                     f"{(r.stderr or '').strip().splitlines()[-1:] or ['nothing']}). The text-only style plan still works.")
    _level_preview(tmp, log)                     # her voice at her cut's level, before it stands in for her footage
    _replace(tmp, out)                           # never rewrite a file in place: a hardlinked copy elsewhere would change too
    open(stamp, "w", encoding="utf-8").write(sig)
    if got + PREVIEW_SLACK_S < need:             # still short from her own clips: kept (her page says where), said once
        open(known_short, "w", encoding="utf-8").write(sig)
        log(f"Her preview copy came out {_mmss(got)} long, but her cut needs {_mmss(need)}: ffmpeg could not read all "
            "of her footage. Her page plays what it has and says where it stops; /report-a-problem sends the details.")
    elif os.path.exists(known_short):
        os.remove(known_short)
    log(f"Preview copy ready in {time.time() - t0:.0f}s.")
    return out


def _line_up_sound(jd, log=print):
    """A clip whose sound starts after its picture, in a reel heard before the engine lined such clips up: her page
    showed her words, and her cut was made, on the sound's clock while the stitch cuts on the file's, so the reel came
    out choppy and stayed that way after the update (a buyer, 2026-10-22). product/av_sync.py lines the clip up and
    moves the stored word and cut times with it, once. Call it holding the cut's lock (_making). {clip: seconds}."""
    try:
        import av_sync
        return av_sync.catch_up(jd, say=log, quiet=True)
    except Exception as e:                                   # never a dead end: her reel opens as it was
        log(f"(the sound line-up could not run this time: {e})")
        return {}


def _wide_opening(jd):
    """A wide video opens on a snap zoom-out, once. She can take it off the clip like any other zoom."""
    flag, cuts = os.path.join(jd, "review", "wide-opening.json"), os.path.join(jd, "transcript", "cuts.json")
    if not frame.is_wide(jd) or os.path.exists(flag) or not os.path.isfile(cuts):
        return
    try:
        plan = json.load(open(cuts, encoding="utf-8"))
        segs = plan.get("segments") if isinstance(plan, dict) else None
        if segs and not segs[0].get("zoom"):
            segs[0]["zoom"] = dict(WIDE_ZOOMS["out"])
            _atomic_json(cuts, plan)
        _atomic_json(flag, {"done": True})
    except (OSError, ValueError):
        pass


def prepare(job, log=print):
    jd = job_dir(job)
    _wide_opening(jd)
    try:
        with _making(jd, "lean"):
            moved = _line_up_sound(jd, log=log)
    except Busy:
        moved = {}                                           # a change is being made: its stitch lines it up itself
    if moved and os.path.isfile(os.path.join(jd, "transcript", "cuts.json")):
        try:                                                 # one lean round, so her cut is cleaned on the clock it
            restitch(job, log=log)                           # now plays on; her lock-in is kept (_keep_lock)
        except Refuse as e:
            log(f"(her cut is lined up; cleaning its edges waits for her next change: {e})")
    data = build_script(job)
    make_preview(job, log=log)
    try:                                         # the stills and the waveform are made from the preview, so a brand-new
        timeline_assets(job_dir(job), data)      # reel (no preview while its script was built) gets them now
    except Exception:
        pass
    h = editor_health(job, log=log)              # then checked from the files themselves, and anything still missing rebuilt
    if h["still_missing"]:
        log("  her page opens without: " + ", ".join(h["still_missing"][:6]) + " (it tries again when she opens it)")
    return data


# ── the local page ─────────────────────────────────────────────────────────────────────────────────────────────
ACTIVE_S = 600   # a page server her page used within this many seconds is never restarted for a code change
SERVER_WAIT_S = 20   # how long a fresh page server gets to answer before "couldn't start"
LINK_PAGE = "Open my visual editor.html"   # in her engine folder: something to double-click when the tab hides


def _server_port():
    """The running page server's port, if it is alive AND runs today's code. One from before an update is stopped."""
    try:
        st = json.load(open(SERVER_STATE, encoding="utf-8"))
    except Exception:
        return None
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{st['port']}/ping", timeout=2) as r:
            body = r.read().decode("utf-8", "replace")
        if r.status == 200 and code_version() in body:
            return st["port"]
        if '"busy": true' in body:                  # out of date but mid-job: never kill it; it's replaced once idle
            return st["port"]
        m = re.search(r'"idle": (\d+)', body)        # out of date but her page used it in the last 10 minutes: she is
        if m and int(m.group(1)) < ACTIVE_S:         # working, so it stays (a restart froze her page and moved its
            return st["port"]                        # address, 2026-10-17); it's replaced once she has stepped away
    except Exception:
        return None
    try:                                           # alive but out of date: stop it so a fresh one starts
        import signal
        os.kill(int(st["pid"]), signal.SIGTERM)
        time.sleep(0.3)
    except Exception:
        pass
    return None


def ensure_server():
    port = _server_port()
    if port:
        return port
    srv = os.path.join(ROOT, "product", "visual_editor_server.py")
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL, "cwd": ROOT,
          "close_fds": True}
    if os.name == "nt":
        # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (no console flashes), plus CREATE_BREAKAWAY_FROM_JOB: Claude's
        # command runs in a job that can end everything inside it when the command returns, and her page went with
        # it. Not DETACHED_PROCESS: the server's own ffmpeg and uv calls would each flash a console window (the
        # lesson vectcut_engine.py learned). Where the job forbids breaking away, it starts without, as before.
        flags = 0x08000000 | 0x00000200
        try:
            subprocess.Popen([sys.executable, srv], creationflags=flags | 0x01000000, **kw)
        except OSError:
            subprocess.Popen([sys.executable, srv], creationflags=flags, **kw)
    else:
        subprocess.Popen([sys.executable, srv], start_new_session=True, **kw)
    deadline = time.time() + SERVER_WAIT_S    # a first start on Windows or an Intel Mac can take well past 5s
    while time.time() < deadline:
        time.sleep(0.2)
        port = _server_port()
        if port:
            return port
    raise Refuse("The visual editor's page couldn't start on this computer. The text-only style plan still works. "
                 "To try the editor again, type \"open my visual editor\" in the chat any time.")


def latest_reel():
    """Her most recent reel with a rough cut, for "open my visual editor" when she doesn't name one: the reel whose
    cut was saved last (her page's sends move it too)."""
    best, best_t = None, -1.0
    projects = os.path.join(ROOT, "projects")
    for name in (os.listdir(projects) if os.path.isdir(projects) else []):
        cp = os.path.join(projects, name, "transcript", "cuts.json")
        if os.path.isfile(cp) and os.path.isfile(os.path.join(projects, name, "transcript", "words.json")):
            t = os.path.getmtime(cp)
            if t > best_t:
                best, best_t = name, t
    if not best:
        raise Refuse("There's no rough cut yet to open in the visual editor. Drop a clip in inbox/ and say \"edit my "
                     "newest clip\": after the cut, \"open my visual editor\" opens it.")
    return best


def open_editor(job, browser=True, autopilot=False):
    """Walk-through opens on her cut. Autopilot opens on her Sound tab (every layer is built), saying once how to go
    back to the cut; going back and changing a layer locks the ones after it until she locks that one in. The page
    server starts FIRST and each step says so as it goes, so a long first preview copy is visibly working, never a
    silent command with no port (2026-10-21); the server is asked again after, in case it stepped down meanwhile."""
    print(f"Opening the visual editor for {os.path.basename(job_dir(job))}: starting its page...")
    ensure_server()
    print("Page server is up. Getting her reel ready (the first open of a reel makes a preview copy of her footage)...")
    data = prepare(job)
    import review_route; review_route.set_route(job_dir(job), "editor")   # this reel stays on the editor from here
    if autopilot:                                # autopilot built every layer: its looks are locked in, so it opens on Sound
        ph = os.path.join(job_dir(job), "review", "phase.json")
        try:
            cur = json.load(open(ph, encoding="utf-8"))
        except Exception:
            cur = {}
        if cur.get("phase") == "looks":
            _atomic_json(ph, dict(cur, phase="render", looks_locked_at=time.strftime("%Y-%m-%d %H:%M:%S")))
    port = ensure_server()
    from urllib.parse import quote
    url = f"http://127.0.0.1:{port}/editor/?job={quote(data['job'])}" + ("&from=autopilot" if autopilot else "")
    _page_answers(url)                           # the page itself, not just /ping: what she'll click has to load
    write_link_page(url)
    if browser:
        import webbrowser
        try:
            webbrowser.open(url)                 # "True" here doesn't mean she sees it: the tab can land behind Claude,
        except Exception:                        # so the EDITOR LINK line goes in the chat every time regardless
            pass
    return url


def editor_link(url):
    """The line the chat pastes word for word after every open: a link she can click whatever the browser did."""
    return f"EDITOR LINK: [Open your visual editor]({url})"


def _page_answers(url, wait=8):
    """Fetch her page from the server that just said it's up. A server that answers /ping but not the page is
    no editor to hand her."""
    import urllib.request
    deadline, err = time.time() + wait, None
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                body = r.read(4096)
            if r.status == 200 and b"<" in body:
                return True
            err = f"status {r.status}"
        except Exception as e:
            err = str(e)
        if time.time() >= deadline:
            raise Refuse(f"The visual editor's server started but its page didn't load ({err}). The text-only style "
                         "plan still works. To try the editor again, type \"open my visual editor\" in the chat any time.")
        time.sleep(0.5)


def write_link_page(url):
    """"Open my visual editor.html" in her engine folder: double-click it and her editor opens. When the editor
    has gone quiet (it stops after two idle hours, or the computer restarted) it says how to start it again
    instead of showing a browser error."""
    import html as _h
    ping = url.split("/editor/", 1)[0] + "/ping"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Open my visual editor</title>
<noscript><meta http-equiv="refresh" content="0; url={_h.escape(url)}"></noscript>
<style>body{{font:17px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:34em;margin:4em auto;padding:0 1em;color:#222}}
a{{color:#bd1b1b}}</style></head>
<body><p id="m">Opening your visual editor&hellip; If nothing happens, <a href="{_h.escape(url)}">click here</a>.</p>
<script>
fetch({json.dumps(ping)}, {{mode: "no-cors", cache: "no-store"}})
  .then(function () {{ location.replace({json.dumps(url)}); }})
  .catch(function () {{
    document.getElementById("m").innerHTML = "Your visual editor looks asleep (it rests after two quiet hours, or " +
      "when the computer restarts). In Claude, type: <b>open my visual editor</b>. It starts again in a few seconds. " +
      "<a href=" + JSON.stringify({json.dumps(url)}) + ">Try it anyway</a>";
  }});
</script></body></html>
"""
    try:
        tmp = os.path.join(ROOT, LINK_PAGE + ".tmp")
        open(tmp, "w", encoding="utf-8").write(page)
        _replace(tmp, os.path.join(ROOT, LINK_PAGE))
    except Exception:
        pass                                     # a convenience: the EDITOR LINK in the chat is the real way in


# ── what she sent → the cut ────────────────────────────────────────────────────────────────────────────────────
FX_SPEEDS = (0.5, 4.0)    # the slowest and fastest a clip can play (her page offers 1x to 2x)
# A wide video's zoom moves land in 18 frames and hold: out snaps and settles, in eases through the middle.
WIDE_ZOOMS = {"out": {"from": 1.15, "to": 1.0, "ease": "quart", "frames": 18},
              "in": {"from": 1.0, "to": 1.15, "ease": "inOut", "frames": 18}, "none": None}
FX_ZOOM = (1.0, 2.0)      # a zoom move's scales: never under the frame, never past twice


def fx_of(payload):
    """Her clips' Speed and Zoom from a page save, checked: {word: {"speed": x, "zoom": {"from", "to"} or None}}.
    Anything that isn't a number in range is dropped, never guessed."""
    out = {}
    for k, v in ((payload or {}).get("fx") or {}).items():
        try:
            w = int(k)
        except (TypeError, ValueError):
            continue
        if not isinstance(v, dict) or w < 0:
            continue
        e = {}
        if "speed" in v:
            sv = v["speed"]
            if isinstance(sv, dict):                         # a speed ramp: one fluid clip easing from one speed to another
                try:
                    a, b = round(float(sv["from"]), 3), round(float(sv["to"]), 3)
                except (KeyError, TypeError, ValueError):
                    a = b = None
                ease = sv.get("ease") if sv.get("ease") in ("linear", "in", "out", "inOut") else "inOut"
                if a is not None and all(FX_SPEEDS[0] <= x <= FX_SPEEDS[1] for x in (a, b)):
                    e["speed"] = a if a == b else {"from": a, "to": b, "ease": ease}
            else:
                try:
                    sp = round(float(sv), 3)
                except (TypeError, ValueError):
                    sp = None
                if sp is not None and FX_SPEEDS[0] <= sp <= FX_SPEEDS[1]:
                    e["speed"] = sp
        if "zoom" in v:
            z = v["zoom"]
            if z is None:
                e["zoom"] = None
            elif isinstance(z, dict):
                try:
                    a, b = round(float(z["from"]), 3), round(float(z["to"]), 3)
                except (KeyError, TypeError, ValueError):
                    a = b = None
                if a is not None and all(FX_ZOOM[0] <= x <= FX_ZOOM[1] for x in (a, b)):
                    ez = z.get("ease")
                    e["zoom"] = None if a == b == 1.0 else {"from": a, "to": b, **({"ease": ez} if ez in ("linear", "in", "out", "inOut", "quart") else {}),
                                                            **({"frames": int(z["frames"])} if z.get("frames") else {})}
        if e:
            out[w] = e
    return out


def edits_in(payload):
    """Does this save change her cut at all? (words cut or brought back, an edge, a stretch cut by time, a Speed or Zoom)"""
    p = payload or {}
    trims = p.get("trims") or {}
    return bool(p.get("cut") or p.get("back") or trims.get("s") or trims.get("e") or p.get("holes") or fx_of(p))


def last_applied(jd):
    """The newest Send that reached her cut: {"receipt", "at"} (review/applied/<receipt>.json and its time), or None.
    Her page compares it with the receipt its Send got, so a Send that never landed is said, never a silent loop."""
    done = os.path.join(jd, "review", "applied")
    try:
        files = [os.path.join(done, f) for f in os.listdir(done) if f.endswith(".json")]
    except OSError:
        return None
    if not files:
        return None
    last = max(files, key=os.path.getmtime)
    return {"receipt": os.path.basename(last)[:-5], "at": round(os.path.getmtime(last), 3)}


def pin_wordless(jd, segs):
    """Every piece of a plan with no words under it (b-roll inside a talking clip, a held look) pinned (_PINNED), so the
    stitch keeps it exactly: a plan written in the chat (`restitch`) gets the same care as her page's Send."""
    try:
        clips = json.load(open(os.path.join(jd, "transcript", "words.json"), encoding="utf-8"))["clips"]
    except Exception:
        return segs
    names = {c["clip"]: ci for ci, c in enumerate(clips)}
    held = set(k for k in _holders(words_of(clips), names, segs) if k is not None)
    return [dict(s, **_PINNED) if k not in held and s.get("clip") in names else s for k, s in enumerate(segs)]


def receipt(payload):
    core = {k: payload[k] for k in ("job", "id", "cut", "back")}
    if payload.get("trims") and (payload["trims"].get("s") or payload["trims"].get("e")):
        core["trims"] = {side: {str(k): round(float(v), 3) for k, v in sorted(payload["trims"].get(side, {}).items(), key=lambda kv: int(kv[0]))}
                         for side in ("s", "e")}
    if payload.get("holes"):
        core["holes"] = [[int(h["c"]), round(float(h["s"]), 3), round(float(h["e"]), 3)] for h in payload["holes"]]
    if fx_of(payload):
        core["fx"] = {str(k): v for k, v in sorted(fx_of(payload).items())}
    return hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()[:6].upper()


def parse_code(text):
    """The fallback she pastes from "Copy your cut". Tolerant of spaces, case and missing lines."""
    m = re.search(r"STYLE PLAN EDITS\W+(\S+)\W+v([0-9a-f]{6,10})", text, re.I)
    if not m:
        raise Refuse("That doesn't look like the text from “Copy your cut”. It starts with STYLE PLAN EDITS.")

    def nums(label):
        mm = re.search(label + r"\s*:\s*([^\n]*)", text, re.I)
        out = []
        if not mm or mm.group(1).strip().lower() in ("", "none"):
            return out
        for part in re.split(r"[,\s]+", mm.group(1).strip()):
            if not part:
                continue
            a, _, b = part.partition("-")
            out.extend(range(int(a), int(b or a) + 1))
        return out

    trims = {"s": {}, "e": {}}
    mm = re.search(r"edges\s*:\s*([^\n]*)", text, re.I)
    if mm:
        for w, side, t in re.findall(r"(\d+)\s*([se])\s*=\s*([0-9.]+)", mm.group(1)):
            trims[side][int(w)] = float(t)
    holes = []
    mm = re.search(r"holes\s*:\s*([^\n]*)", text, re.I)
    if mm:
        holes = [{"c": int(c), "s": float(a), "e": float(b)} for c, a, b in re.findall(r"(\d+)\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)", mm.group(1))]
    out = {"job": m.group(1), "id": m.group(2).lower(), "cut": nums("cut"), "back": nums("keep"), "trims": trims}
    if holes:
        out["holes"] = holes
    mm = re.search(r"fx\s*:\s*([^\n]*)", text, re.I)          # a clip's Speed and Zoom: "12 x2 z1.15-1, 40 x1 znone"
    if mm:
        fx = {}
        for part in mm.group(1).split(","):
            w = re.match(r"\s*(\d+)", part)
            if not w:
                continue
            e, sp, z = {}, re.search(r"\bx([0-9.]+)", part), re.search(r"\bz(none|[0-9.]+-[0-9.]+)", part)
            rp = re.search(r"\br([0-9.]+)-([0-9.]+)-(linear|inOut|in|out)\b", part)   # a speed ramp: r2.5-1-out
            if sp:
                e["speed"] = float(sp.group(1))
            if rp:
                e["speed"] = {"from": float(rp.group(1)), "to": float(rp.group(2)), "ease": rp.group(3)}
            if z:
                e["zoom"] = None if z.group(1) == "none" else dict(zip(("from", "to"), map(float, z.group(1).split("-"))))
            if e:
                fx[w.group(1)] = e
        if fx:
            out["fx"] = fx
    return out


def apply_edits(job, payload, stitch=True, log=print, lean=True, keep_phase=False):
    jd, clips, segs, wid, cid = load(job)
    if payload.get("job") != os.path.basename(jd):
        raise Refuse(f"These edits are for {payload.get('job')!r}, not {os.path.basename(jd)!r}.")
    # a page made before her clip's sound was lined up (product/av_sync.py) points at the same words, on the clock
    # before: {clip: seconds} to move its times by. None = a page from some other transcript: refused, as always
    import av_sync
    moved = av_sync.moved_since(jd, payload.get("id"), wid)
    if moved is None:
        raise Refuse("The transcript changed after the page was made, so these edits no longer point at the same "
                     "words. Open the visual editor again and make them there; nothing has been cut.")
    words = kept_quiet(words_of(clips), clips, segs)         # the same list the page was made from
    n = len(words)
    cut_set, back_set = set(payload.get("cut", [])), set(payload.get("back", []))
    bad = [i for i in cut_set | back_set if not (isinstance(i, int) and 0 <= i < n)]
    if bad:
        raise Refuse("Some of these edits point past the end of the transcript, so they can't be from this reel.")
    seg_of = membership(words, clips, segs)
    words = [dict(w) for w in words]
    for i, w in enumerate(words):                              # a word the engine cut can come back: only its own length
        if seg_of[i] is None:
            w["s"], w["e"] = word_span(w, last=i + 1 >= len(words) or words[i + 1]["c"] != w["c"])
    names = {ci: c["clip"] for ci, c in enumerate(clips)}
    # quiet beats she kept are never a word's neighbour (they sit after every word in the list): same as the page
    same = lambda i, j: 0 <= j < n and words[j]["c"] == words[i]["c"] and bool(words[j].get("q")) == bool(words[i].get("q"))
    # an edge sits PAD outside the word, but never past halfway to the next word she said: words she ran
    # together (20 ms apart) must not hand a sliver of the neighbour to the cut
    # a spoken amount ("$27,000") is several words under one stamp that can end a word early ("dollars"): its
    # edge reaches to just short of the next word, so a cut beside it never takes its spoken words with it
    amt = lambda i: bool(re.match(r"^\W*(?:[$€£¥]\d[\d,.]*[kKmMbB]?|\d[\d,.]*\s*(?:%|[kKmMbB])|\d{1,3}(?:,\d{3})+(?:\.\d+)?)\W*$", words[i]["t"]))
    after = lambda i: ((min(words[i + 1]["s"] - 0.05, words[i]["e"] + 1.5) if amt(i) else min(words[i]["e"] + PAD, (words[i]["e"] + words[i + 1]["s"]) / 2))
                       if same(i, i + 1) else words[i]["e"] + PAD)
    before = lambda i: ((min(words[i]["s"], max(words[i - 1]["e"] + 0.05, words[i]["s"] - 0.5)) if amt(i) else max(words[i]["s"] - PAD, (words[i - 1]["e"] + words[i]["s"]) / 2))
                        if same(i, i - 1) else words[i]["s"] - PAD)

    # her dragged edges (clip time), by word: "s" = a piece's start edge on that word, "e" = its end edge
    trims = payload.get("trims") or {}
    ts = {int(k): float(v) for k, v in (trims.get("s") or {}).items()}
    te = {int(k): float(v) for k, v in (trims.get("e") or {}).items()}
    if moved:
        # her edges sat where her page drew her words; her words moved with the line-up, so her edges move with them
        # (a buyer whose reel was heard before the line-up, 2026-10-22). Her cuts, restores and moves are by word.
        lead = lambda i: moved.get(names.get(words[i]["c"]), 0.0) if 0 <= i < n else 0.0
        ts = {i: round(v + lead(i), 4) for i, v in ts.items()}
        te = {i: round(v + lead(i), 4) for i, v in te.items()}
        log("These edits were made before your clip's sound was lined up with its picture; every edge you set moved "
            "with your words.")
    # a SPLIT she made on the timeline = an end edge on one word and a start edge on the very next one: the piece
    # is cut in two there (each half then takes her edge in step 3), so the pause between them can be closed
    split_after = lambda i: i in te and (i + 1) in ts

    # 1) her cuts: split each segment around the words she took out (and at her splits)
    new = []                                   # (segment, original index) in cut order
    for k, s in enumerate(segs):
        ids = [i for i in range(n) if seg_of[i] == k]
        keep = [i for i in ids if i not in cut_set]
        if len(keep) == len(ids) and not any(split_after(i) for i in ids[:-1]):
            new.append((dict(s, _w=(ids[0], ids[-1]), **(_PINNED if ids and all(words[i].get("q") for i in ids) else {})), k))
            continue
        runs, cur = [], []
        for i in keep:
            if cur and (i != cur[-1] + 1 or split_after(cur[-1])):
                runs.append(cur); cur = []
            cur.append(i)
        if cur:
            runs.append(cur)
        for r in runs:
            a = float(s["start"]) if r[0] == ids[0] else max(float(s["start"]), before(r[0]))
            b = float(s["end"]) if r[-1] == ids[-1] else min(float(s["end"]), after(r[-1]))
            piece = {kk: v for kk, v in s.items() if kk not in ("_snapped_from", "keep_edges", "start", "end", "transcript")}
            piece.update(start=round(a, 4), end=round(b, 4), transcript=" ".join(words[i]["t"] for i in r if words[i]["t"]))
            if all(words[i].get("q") for i in r):              # seconds of a clip with no talking: no voice to snap to
                piece.update(_PINNED)
            if s.get("keep_edges") and r[0] == ids[0] and r[-1] == ids[-1]:
                piece["keep_edges"] = True
            piece["_w"] = (r[0], r[-1])
            new.append((piece, k))

    # 2) what she brought back: each run of restored words becomes its own piece, marked no_trim (her call wins),
    #    placed exactly where the page played it: after the kept word just before it in the CUT's order
    order, _ = display_order(words, segs, seg_of)
    rank = {i: x for x, i in enumerate(order)}
    restored = sorted((i for i in back_set if seg_of[i] is None), key=rank.get)
    runs, cur = [], []
    for i in restored:
        if cur and not (i == cur[-1] + 1 and words[i]["c"] == words[cur[-1]]["c"] and rank[i] == rank[cur[-1]] + 1):
            runs.append(cur); cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    alive = lambda j: seg_of[j] is not None and j not in cut_set
    for r in runs:
        c = words[r[0]]["c"]
        a, b = before(r[0]), after(r[-1])
        prev = next((order[x] for x in range(rank[r[0]] - 1, -1, -1) if alive(order[x])), None)
        nxt = next((order[x] for x in range(rank[r[-1]] + 1, len(order)) if alive(order[x])), None)
        holds = lambda j: next((x for x, (p, _) in enumerate(new) if p.get("clip") == names[words[j]["c"]]
                                and float(p["start"]) - 1e-3 <= words[j]["s"] <= float(p["end"]) + 1e-3), None)
        px, nx = (holds(prev) if prev is not None else None), (holds(nxt) if nxt is not None else None)
        # butt against a neighbour's REAL edge (snapped, padded) when it is right beside her in the footage,
        # so no sliver of sound plays twice
        if px is not None and new[px][0].get("clip") == names[c] and float(new[px][0]["end"]) <= words[r[0]]["e"]:
            a = max(a, float(new[px][0]["end"]))
        if nx is not None and new[nx][0].get("clip") == names[c] and float(new[nx][0]["start"]) >= words[r[-1]]["s"]:
            b = min(b, float(new[nx][0]["start"]))
        piece = {"clip": names[c], "start": round(max(0.0, a), 4), "end": round(b, 4),
                 "transcript": " ".join(words[i]["t"] for i in r if words[i]["t"]), "no_trim": True, "_w": (r[0], r[-1]),
                 **(_PINNED if all(words[i].get("q") for i in r) else {})}
        at = px + 1 if px is not None else (nx if nx is not None else len(new))
        new.insert(at, (piece, None))

    # 2b) an edge she dragged OUT over struck words (like stretching a clip in CapCut) pulls them back into that
    #     clip: the words she uncovered join the piece beside them, natural pause and all, instead of playing as a
    #     separate piece. Only when that outer edge is hers (a trim on it); a tapped-back word stays its own piece.
    x = 0
    while x + 1 < len(new):
        (a, ka), (b, kb) = new[x], new[x + 1]
        (af, al), (bf, bl) = a["_w"], b["_w"]
        if a.get("clip") == b.get("clip") and al + 1 == bf and words[al]["c"] == words[bf]["c"] and \
                ((kb is None and bl in te) or (ka is None and af in ts)):
            m = dict(a, end=b["end"], transcript=f"{a.get('transcript', '')} {b.get('transcript', '')}".strip(),
                     no_trim=True, _w=(af, bl))
            new[x] = (m, ka if ka is not None else kb); del new[x + 1]
            continue
        x += 1

    # 3) her trims: an edge she dragged becomes exactly that edge, pinned (keep_edges) so the edge-cleaning pass
    #    never moves it. A handle can't reach into the neighbouring word (or past its own word), checked here too.
    n_trims = 0
    for p, _ in new:
        f, l = p.get("_w", (None, None))
        if f in ts:
            lo = words[f - 1]["e"] if same(f, f - 1) else max(0.0, words[f]["s"] - 3.0)
            p["start"] = round(min(max(ts[f], lo), words[f]["e"] - 0.05), 4); p["keep_edges"] = True; n_trims += 1
        if l in te:
            hi = words[l + 1]["s"] if same(l, l + 1) else words[l]["e"] + 3.0
            p["end"] = round(max(min(te[l], hi), words[l]["s"] + 0.05), 4); p["keep_edges"] = True; n_trims += 1

    # 3b) a clip's Speed and Zoom move, set on her timeline: keyed by a word in that clip (the page sends the clip's
    #     first word). Set on the piece holding it, before step 4, so both halves of a clip she cuts by time keep
    #     them (the page does the same). Speed 1 / zoom None take the field off. A piece she didn't touch keeps what
    #     its segment had, so a speed or zoom survives every later Send.
    #     ONE move per piece: a page that kept two words of one clip with opposite moves ("zoom in" on one, "no zoom" on
    #     another) flipped the clip on every Send and her cut never locked (a buyer, 2026-10-22). The lowest word wins,
    #     the one her page plays (buildSpans), and the others are passed over.
    fx_done = set()
    for k, v in sorted(fx_of(payload).items()):
        hold = [p for p, _ in new if p.get("_w") and p["_w"][0] <= k <= p["_w"][1]]
        if not hold:
            continue
        p = min(hold, key=lambda q: q["_w"][1] - q["_w"][0])
        if id(p) in fx_done:
            continue
        fx_done.add(id(p))
        if "speed" in v:
            p.pop("ramp", None)
            if isinstance(v["speed"], dict):                 # a ramp: "speed" holds its average (every reader of the cut
                from cut_placement import ramp_average        # keeps working), "ramp" its shape (stitch-cut.sh SPEED RAMPS)
                p["ramp"] = dict(v["speed"]); p["speed"] = round(ramp_average(v["speed"]), 6)
            elif v["speed"] == 1.0:
                p.pop("speed", None)
            else:
                p["speed"] = v["speed"]
        if "zoom" in v:
            if v["zoom"] is None:
                p.pop("zoom", None)
            else:
                p["zoom"] = dict(v["zoom"])
        n_trims += 1
    for p, _ in new:
        p.pop("played", None)                  # the stitch measures a sped piece's played length again from its new edges

    # 4) stretches she cut by TIME on the timeline (she split a clip anywhere, mid-word or in the quiet at its ends,
    #    then deleted a side, pressed Q / W on it, or dragged a split edge): each comes out of whatever piece it
    #    falls in, exactly where she put it, edges pinned. Her call, never snapped to a word (same rule as the
    #    page's buildSpans, so what she heard is what renders).
    holes = []
    for h in payload.get("holes") or []:
        try:
            c, a, b = int(h["c"]), float(h["s"]), float(h["e"])
        except (KeyError, TypeError, ValueError):
            continue
        if moved and c in names:                              # a time cut from a page before the line-up (above)
            a, b = round(a + moved.get(names[c], 0.0), 4), round(b + moved.get(names[c], 0.0), 4)
        if c in names and b - a > 0.01:
            holes.append((names[c], a, b))
    if holes:
        def text(q):
            f, l = q.get("_w", (None, None))
            if f is None:
                return q.get("transcript", "")
            qs, qe = float(q["start"]), float(q["end"])
            return " ".join(words[i]["t"] for i in range(f, l + 1)
                            if names.get(words[i]["c"]) == q.get("clip") and min(words[i]["e"], qe) - max(words[i]["s"], qs) > 0.05)
        out_new = []
        for p, k in new:
            parts = [p]
            for name, a, b in holes:
                nxt = []
                for q in parts:
                    qs, qe = float(q["start"]), float(q["end"])
                    if q.get("clip") != name or b <= qs or a >= qe:
                        nxt.append(q); continue
                    if a - qs > 0.05:
                        nxt.append(dict(q, end=round(a, 4), keep_edges=True))
                    if qe - b > 0.05:
                        nxt.append(dict(q, start=round(b, 4), keep_edges=True))
                    n_trims += 1
                parts = nxt
            for q in parts:
                q["transcript"] = text(q)
                out_new.append((q, k))
        new = out_new
    for p, _ in new:
        p.pop("_w", None)
    out = [p for p, _ in new if float(p["end"]) - float(p["start"]) > 0.05]
    if not out:
        raise Refuse("These edits cut every word of the reel, so there'd be nothing left. Nothing has been cut.")
    secs = sum((float(p["end"]) - float(p["start"])) / float(p.get("speed", 1.0) or 1.0) for p in out)
    log(f"Your edits ({len(cut_set)} word{'s' if len(cut_set) != 1 else ''} cut, {len(back_set)} brought back"
        f"{f', {n_trims} edge' + ('s' if n_trims != 1 else '') + ' trimmed' if n_trims else ''}) "
        f"make a cut of {len(out)} piece{'s' if len(out) != 1 else ''}, about {int(secs // 60)}:{int(secs % 60):02d}.")
    if cid != payload.get("cut_id", cid):
        log("The cut changed after the page was made. Your edits are about specific words, so they're applied to "
            "today's cut as they are.")

    if not stitch:
        # a look only: never the live scratch plan, so a later stitch can't pick up edits nobody confirmed
        _atomic_json(os.path.join(jd, "review", "cut-plan-preview.json"), {"segments": out})
        return out
    scratch = os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(jd))
    os.makedirs(scratch, exist_ok=True)
    _atomic_json(os.path.join(scratch, "cuts.json"), {"segments": out})
    _stitch(jd, lean=lean, log=log, keep_phase=keep_phase)
    return out


class Stopped(Refuse):
    """She pressed Stop on her Finish tab while her full-quality cut was being made."""


def _stitch(jd, lean, log=print, env=None, keep_phase=False, stop=None):
    """One run of the normal stitch. Lean (FLAT_RENDER=0): the clean-edge passes, the saved cut and the caption
    transcript, no video encode and none of the checks that listen to it; seconds, because the page already plays
    the cut. Full: everything, the base cut video included. stop: a file whose arrival ends the run (her Stop)."""
    if lean:
        _pin_base(jd)                                         # stamped first, so this round's change (a zoom too) marks it behind
    for f in (("last-problem.json",) if keep_phase else ("phase.json", "last-problem.json")):   # the cut is changing: phase 1 is open
                                                             # again, old trouble is gone (Finish encoding her cut isn't a change)
        try:
            os.remove(os.path.join(jd, "review", f))
        except OSError:
            pass
    env = dict(os.environ, FLAT_RENDER="0" if lean else "1", **(env or {}))
    log("Updating your cut (clean edges, no video yet)…" if lean else "Making your full-quality cut, with every check…")
    rc, tail = _run_stitch(jd, env, timeout=LEAN_STITCH_TIMEOUT if lean else None, stop=stop)
    if rc == STOPPED:
        raise Stopped("You stopped making your full-quality cut, so it stopped there. Your edits are saved; nothing "
                      "was lost. Press Export whenever you're ready.")
    if rc is None:
        raise Refuse(f"Updating your cut took more than {LEAN_STITCH_TIMEOUT // 60} minutes, so I stopped it. Your edits "
                     "are saved; nothing was lost. Press “Send my cut” again; if it stops again, type /report-a-problem "
                     "in the chat.")
    if rc != 0:
        last = next((t for t in reversed(tail) if t.strip()), "")
        raise Refuse("Updating your cut stopped with an error" + (f" ({last.strip()[:160]})" if last else "")
                     + ". Your edits are saved; nothing was lost. Type /report-a-problem in the chat and I'll see why.")
    if not lean:
        _stamp_base(jd)


# A lean stitch is seconds (no video encode). One that runs this long has hung, and the page would wait on it forever
# (buyer report 2026-10-19, Windows: "Send my cut" never turned into "Lock in my cut", nothing logged).
LEAN_STITCH_TIMEOUT = 15 * 60
STOPPED = "stopped"   # _run_stitch's answer when her Stop ended it


def _run_stitch(jd, env, timeout=None, stop=None):
    """stitch-cut.sh with its output kept in review/last-stitch.log (the editor's server discards its own output, so a
    failed send used to leave no trace for /report-a-problem) and still echoed as before. -> (returncode, None when
    the time ran out, or STOPPED when the file `stop` appeared; last lines). Either way the stitch ends whole, ffmpeg
    included: her Stop during a 4K cut used to be ignored for hours (a buyer report, 2026-10-23)."""
    import collections, threading
    logf = os.path.join(jd, "review", "last-stitch.log")
    os.makedirs(os.path.dirname(logf), exist_ok=True)
    kw = {"creationflags": 0x00000200} if os.name == "nt" else {"start_new_session": True}   # its own group, to stop it whole
    tail = collections.deque(maxlen=20)
    with open(logf, "w", encoding="utf-8", errors="replace") as lf:
        lf.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')} stitch {os.path.basename(jd)} (FLAT_RENDER={env.get('FLAT_RENDER')})\n")
        p = subprocess.Popen([_bash(), os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh"), jd],
                             cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             text=True, encoding="utf-8", errors="replace", **kw)

        def pump():
            for line in p.stdout:
                lf.write(line); lf.flush(); tail.append(line.rstrip("\n"))
                try:
                    if sys.stdout:
                        sys.stdout.write(line); sys.stdout.flush()
                except (OSError, ValueError):
                    pass

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        t0 = time.time()
        while True:
            try:
                rc = p.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if stop and os.path.exists(stop):
                    _stop_tree(p)
                    rc = STOPPED
                    lf.write("\n# stopped: she pressed Stop\n")
                    break
                if timeout is not None and time.time() - t0 > timeout:
                    _stop_tree(p)
                    rc = None
                    lf.write(f"\n# stopped after {timeout}s: it had hung\n")
                    break
        t.join(10)
    return rc, list(tail)


def _stop_tree(p):
    """Stop the stitch and everything it started (ffmpeg, python), not just bash."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        p.wait(5)
    except Exception:
        try:
            p.kill()
        except OSError:
            pass


def _cut_sig(jd):
    try:
        return _sha(os.path.join(jd, "transcript", "cuts.json"))
    except OSError:
        return None


def _stamp_base(jd):
    """After a full stitch: remember which cut the rough-cut video was made from."""
    mp4 = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    if os.path.exists(mp4):
        st = os.stat(mp4)
        _atomic_json(os.path.join(jd, "review", "base-cut.json"),
                     {"cut": _cut_sig(jd), "size": st.st_size, "mtime": int(st.st_mtime)})


def _stamp_of(jd):
    """The stamp outputs/<job>.mp4 was given at its full stitch, or None: never stamped, or changed since."""
    mp4 = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    try:
        stamp = json.load(open(os.path.join(jd, "review", "base-cut.json"), encoding="utf-8"))
        st = os.stat(mp4)
    except Exception:
        return None
    return stamp if stamp.get("size") == st.st_size and stamp.get("mtime") == int(st.st_mtime) else None


def _pin_base(jd):
    """Before a lean round changes the cut (her Send, clip-fx, restitch): a rough-cut video with no stamp that still
    matches the cut is stamped with it now, so whatever the round changes marks the video behind, a zoom included."""
    if os.path.exists(os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")) and _stamp_of(jd) is None \
            and not _base_stale(jd):
        _stamp_base(jd)


def base_is_stale(job):
    """True when outputs/<job>.mp4 no longer matches the cut. When the engine stamped the video at its full stitch,
    the cut it was made from is compared exactly (a one-word edit that barely changes the length is still caught);
    a video made some other way (text only, an older engine) falls back to measuring its length, and to its age
    beside a cut carrying a zoom or a framing (_fx_stale)."""
    return _base_stale(job_dir(job))


def _base_stale(jd):
    mp4 = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    if not os.path.exists(mp4):
        return True
    stamp = _stamp_of(jd)
    if stamp is not None:
        return stamp.get("cut") != _cut_sig(jd)
    return _length_stale(jd, mp4) or _fx_stale(jd, mp4)


def _picture_fx(seg):
    """Does this piece change the picture without changing its length: a zoom move, her framing (scale, x, y), or a
    speed ramp (its shape can change while its average, and so the length, stays)."""
    sc = seg.get("scale")
    return bool(isinstance(seg.get("zoom"), dict) or seg.get("ramp") or isinstance(seg.get("speed"), dict)
                or (sc not in (None, "") and abs(float(sc) - 1.0) > 1e-4)
                or any(abs(float(seg.get(k) or 0.0)) > 1e-4 for k in ("x", "y")))


def _fx_stale(jd, mp4):
    """True when the cut carries a picture change the length can't show (_picture_fx) and was saved after the video
    was made, so a video with no stamp can't be shown to carry it (a buyer's export came out without his punch-in,
    2026-10-23: a zoom round never re-encodes). At worst one full stitch more, which stamps the video for good."""
    cp = os.path.join(jd, "transcript", "cuts.json")
    try:
        segs = json.load(open(cp, encoding="utf-8"))["segments"]
        newer = os.path.getmtime(cp) > os.path.getmtime(mp4) + 1
        return newer and any(_picture_fx(s) for s in segs)
    except Exception:
        return True


def _length_stale(jd, mp4):
    """True when outputs/<job>.mp4 no longer matches the cut (a lean round moved on without it), or is missing.
    Measured, not remembered: a full stitch lands within a few hundredths of a second of its plan, and any edit
    changes the length, so a flag can't go out of date when some other road (text only, a CapCut pull-back)
    stitches in between."""
    try:
        segs = json.load(open(os.path.join(jd, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
    except Exception:
        return True
    from cut_placement import played_length                  # a sped clip (her page's Speed) counts at the length it plays
    planned = sum(played_length(x) for x in segs)
    real = _duration(mp4)
    return real is None or abs(real - planned) > 0.08


def finish_cut(job, log=print, exact=False, force=False, stoppable=False):
    """The ONE full-quality stitch of her final cut. exact=True is Finish making the cut she set on her page: the
    plan she heard, encoded as is (no second cleaning pass, no stumble check: she reviewed it by ear), and her
    place in the layers kept. Without it (autopilot, the chat), every check runs, because nobody listened yet.
    force: made again even when the video already matches (`finish-cut <job> --full`). stoppable: her Finish tab's
    Stop (review/finish.stop) ends it."""
    jd = job_dir(job)
    # A reel heard before her clip's sound was lined up: its base video still matches the cut on paper, so Finish
    # would hand back the same choppy video (a buyer, 2026-10-22). Lined up first; its cut then differs, so it is
    # made again. Her edges went back to their planned places on the new clock, so an exact Finish (no cleaning
    # pass of its own) gets one lean round of the usual cleaning first, her lock-in kept (restitch).
    try:
        with _making(jd, "full"):
            moved = _line_up_sound(jd, log=log)
    except Busy:
        moved = {}
    if moved and exact:
        restitch(job, log=log)
    already = not force and os.path.isfile(os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")) \
        and not base_is_stale(job)
    if not already:                                          # the video already matches her cut: nothing to make again
        ph = os.path.join(jd, "review", "phase.json")
        keep = open(ph, encoding="utf-8").read() if exact and os.path.exists(ph) else None
        if exact:                                            # the stitch reads the scratch plan first: make it the very plan
            scratch = os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(jd))   # the page played
            os.makedirs(scratch, exist_ok=True)               # (the scratch copy can still hold the plan from before its
            shutil.copy(os.path.join(jd, "transcript", "cuts.json"), os.path.join(scratch, "cuts.json"))   # edges were cleaned)
        try:
            with _making(jd, "full"):
                _stitch(jd, lean=False, log=log, env={"TRIM_RESTARTS": "0", "SNAP": "0", "VERIFY_CUT": "0"} if exact else None,
                        keep_phase=exact, stop=os.path.join(jd, "review", "finish.stop") if stoppable else None)
        finally:
            if keep is not None:                             # the stitch reopens phase 1; Finish isn't a change to her cut
                os.makedirs(os.path.dirname(ph), exist_ok=True)
                open(ph, "w", encoding="utf-8").write(keep)
        build_script(job)
    if base_is_stale(job):
        raise Refuse("The full-quality cut came out a different length than the plan, which shouldn't happen. "
                     "Ask me to run /report-a-problem.")
    # the same mark the page's Lock in my cut writes, so a cut finished from the chat (or autopilot) is locked in on
    # her page too, and Finish never says her cut changed when it didn't
    ph = os.path.join(jd, "review", "phase.json")
    try:
        cur = json.load(open(ph, encoding="utf-8"))
    except Exception:
        cur = {}
    if cur.get("phase") not in ("looks", "render"):
        _atomic_json(ph, {"phase": "looks", "cut_locked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "cut_id": _cut_id(jd)})
    log("Your cut is locked in at full quality. Next: your looks.")


def _bash():
    """The bash that runs the stitch. On Windows it must be GIT BASH, never WSL's bash.exe in System32 (a Linux
    process can't hand CapCut or the engine Windows paths; CLAUDE.md: native Git Bash, not WSL)."""
    if os.name != "nt":
        return "bash"
    cands = []
    w = shutil.which("bash")
    if w and not any(x in w.lower() for x in ("system32", "windowsapps")):
        cands.append(w)
    g = shutil.which("git")
    if g:
        cands.append(os.path.join(os.path.dirname(os.path.dirname(g)), "bin", "bash.exe"))
    for base in (os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            cands.append(os.path.join(base, "Git", "bin", "bash.exe"))
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise Refuse("Git Bash wasn't found, and the stitch runs in it. Your edits are saved; open Git Bash and ask me "
                 "to apply them again.")


def _review_path(jd):
    return os.path.join(jd, "transcript", "script-review.json")


def _alive(pid):
    """Is this process still running? (Never os.kill(pid, 0) on Windows: there it TERMINATES the process.)"""
    try:
        pid = int(pid)
    except Exception:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259                                  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def making_now(jd):
    """'lean' / 'full' while a cut change is really running for this reel, else ''. A flag left by a process that
    died (a crash, a power cut, a killed server) is cleared here, so the page never says "updating" forever."""
    flag = os.path.join(jd, "review", ".applying")
    try:
        d = json.load(open(flag, encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except Exception:
        d = {}
    if d.get("pid") and _alive(d["pid"]) and time.time() - float(d.get("at", 0)) < 3 * 3600:
        return d.get("kind", "lean")
    try:
        os.remove(flag)
    except OSError:
        pass
    return ""


class Busy(Refuse):
    """Something is already changing this reel's cut."""


class _making:
    """The ONE lock for this reel's cut: every road that changes it (the page's Send, My cut's ready, apply from the
    chat, finish-cut, restitch) takes it first, created exclusively and holding the pid, so two can never overlap
    and a dead holder never blocks anyone. Its kind tells her open page which note to show."""
    def __init__(self, jd, kind):
        self.jd, self.flag, self.kind = jd, os.path.join(jd, "review", ".applying"), kind

    def __enter__(self):
        os.makedirs(os.path.dirname(self.flag), exist_ok=True)
        making_now(self.jd)                                  # clear a dead holder's flag first
        try:
            fd = os.open(self.flag, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise Busy("Hold on a moment, your last change is still being made.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"kind": self.kind, "pid": os.getpid(), "at": time.time()}, f)
        return self

    def __exit__(self, *a):
        try:
            os.remove(self.flag)
        except OSError:
            pass


def apply(job, code=None, stitch=True, log=print, lean=True):
    jd = job_dir(job)
    if code is not None:
        payload = parse_code(code)
        log(f"Using the cut you pasted (receipt {receipt(payload)}).")
    else:
        p = _review_path(jd)
        if not os.path.exists(p):
            done = os.path.join(jd, "review", "applied")
            last = max((os.path.join(done, f) for f in os.listdir(done)), key=os.path.getmtime) if os.path.isdir(done) and os.listdir(done) else None
            if last and time.time() - os.path.getmtime(last) < 6 * 3600:
                raise Refuse(f"Your cut is already in (receipt {os.path.basename(last)[:-5]}). To change more, make the "
                             "changes on the page and press “Send my cut” again.")
            raise Refuse("No cut has arrived from the visual editor yet. Press “Send my cut” on the page; if it says "
                         "your engine didn't get it, press “Copy your cut” and paste it here.")
        payload = json.load(open(p, encoding="utf-8"))
        rc = receipt(payload)
        if payload.get("receipt") and payload["receipt"] != rc:
            raise Refuse("The saved cut doesn't match its own receipt (the file was changed by hand?). "
                         "Press “Send my cut” again.")
        log(f"Applying the cut you sent (receipt {rc}).")
    moved = {}
    if stitch:
        with _making(jd, "lean" if lean else "full"):
            moved = _line_up_sound(jd, log=log)               # a page from before the line-up: apply_edits moves its edges
            # a Send that changes nothing (her page had nothing left to send) never reopens a cut she locked in
            out = apply_edits(job, payload, stitch=True, log=log, lean=lean, keep_phase=not edits_in(payload))
    else:
        out = apply_edits(job, payload, stitch=False, log=log)
    if code is None and stitch:                # stitched: set it aside so a second "sent" can't double-apply an old one
        done = os.path.join(jd, "review", "applied"); os.makedirs(done, exist_ok=True)
        os.replace(_review_path(jd), os.path.join(done, f"{receipt(payload)}.json"))
    if stitch:
        build_script(job)                        # the page now shows the new cut
    if moved:
        try:                                     # her waveform was drawn from the sound before the line-up: made again
            make_preview(job, log=log)
            timeline_assets(jd, json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")))
        except Exception:
            pass                                 # the page still plays; the next open makes them again
    return out


def _notes_path(jd):
    return os.path.join(jd, "transcript", "script-notes.json")


def notes(job):
    jd = job_dir(job)
    try:
        ns = json.load(open(_notes_path(jd), encoding="utf-8"))["notes"]
    except Exception:
        return []
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    W, line_of = script["words"], {}
    for n_, ids in enumerate(script["lines"]):
        for i in ids:
            line_of[i] = n_
    out = []
    for n in ns:
        if n.get("status") == "fixed":
            continue
        w = _heal_note_w(W, n.get("w"), n.get("wt"))         # #2: a drifted index heals back to the word she tapped
        if not isinstance(w, int) or not 0 <= w < len(W):
            continue
        ln = line_of.get(w, 0)
        words = " ".join(W[i]["t"] for i in script["lines"][ln])
        out.append({**n, "w": w, "line": ln + 1, "word": W[w]["t"], "words": words,
                    "clip_time": round(W[w]["s"] - script["clips"][W[w]["c"]]["offset"], 2),
                    "clip": script["clips"][W[w]["c"]]["name"]})
    return out


def _heal_note_w(W, w, wt):
    """#2 (note anchoring): a note stores the word index she tapped plus that word's text (`wt`). If the cut later
    re-indexes, the bare index points at a different word (a note landed on a line-start, "But"/"I"). When the text
    at `w` no longer matches `wt`, find the NEAREST word that still says it, so the note stays on the word she meant.
    No `wt` (older note) or a still-matching index: use `w` unchanged."""
    if not isinstance(w, int):
        return w
    norm = lambda t: re.sub(r"[^\w']", "", str(t or "").lower())
    target = norm(wt)
    if not target or (0 <= w < len(W) and norm(W[w].get("t")) == target):
        return w
    for d in range(1, len(W)):                               # expand outward from the stored index; nearest match wins
        for j in (w - d, w + d):
            if 0 <= j < len(W) and norm(W[j].get("t")) == target:
                return j
    return w


def resolve(job, nid, reply):
    jd = job_dir(job)
    d = json.load(open(_notes_path(jd), encoding="utf-8"))
    hit = [n for n in d["notes"] if n["id"] == nid]
    if not hit:
        raise Refuse(f"There's no note {nid!r} on this reel.")
    reply = _DONE_SAID.sub("", reply.strip())                # her page says "Fixed:" itself: never "Fixed: Fixed:"
    hit[0].update(status="fixed", reply=reply[:300], done_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    _atomic_json(_notes_path(jd), d)
    import editor_says                                        # her page pops it; a few fixed together are one card
    # P3/#6: say what changed, inline in the chat — no "See my notes" button, no vague "each one says what changed".
    editor_says.told(jd, f"Done: {reply[:200]}" if reply else "Done — your note is handled.", kind="note")


_DONE_SAID = re.compile(r"^(?:\s*(?:fixed|done)\s*[:.\-–]\s*)+", re.I)


def _when(t):
    try:
        return time.mktime(time.strptime(str(t), "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return None


QUEUE_STEPS = {"note": ["sent", "has", "done"], "idea": ["sent", "has", "working", "done"]}


def task_queue(job):
    """Her page's task queue: everything she has sent Claude (notes on her cut, notes on a look or a section, Sandbox
    ideas and their remixes, new-look ideas, looks to redo on a new cut), each with its state: sent (waiting), has
    (Claude took it: claude-working.json, written by `wait` / `todo`), working (a Sandbox idea Claude started:
    `sandbox-working`) and done (`resolve`, the sketches landing with `sandbox-takes`, `look-request ... done`). One
    batch: what is open, plus what finished since the oldest open item was sent (or in the last two minutes when
    nothing is open), so the bar reads done / total for this round. Nothing is guessed: no fake percents."""
    jd = job_dir(job)
    try:
        has = set((json.load(open(os.path.join(jd, "review", "claude-working.json"), encoding="utf-8")) or {}).get("ids") or [])
    except Exception:
        has = set()
    short = lambda t, n=46: (t if len(t) <= n else t[:n - 1].rstrip() + "…")
    items = []
    try:
        ns = json.load(open(_notes_path(jd), encoding="utf-8")).get("notes", [])
    except Exception:
        ns = []
    for n in ns:
        if n.get("status") == "deleted":
            continue
        text = str(n.get("text", "")).strip()
        m = re.match(r"^\[(Look|Visuals|Sound|Finish|Reel)[^\]]*\]\s*", text)
        kind = "look-note" if m and m.group(1) == "Look" else "reel-note" if m else "cut-note"
        done = n.get("status") == "fixed"
        items.append({"id": str(n["id"]), "kind": kind, "label": short(text[m.end():] if m else text) or "A note",
                      "state": "done" if done else "has" if str(n["id"]) in has else "sent", "steps": QUEUE_STEPS["note"],
                      "t0": _when(n.get("at")), "t1": _when(n.get("done_at")) if done else None})
    for r in _requests(jd):
        st = r.get("status")
        if st == "dropped":
            continue
        sandbox = r.get("mode") == "sandbox"
        done = st in ("takes", "done", "draft")
        rnd = int(r.get("round") or 1)
        label = ("Sandbox" + (f" remix {rnd - 1}" if rnd > 1 else "") if sandbox else "New look") + ": " + short(str(r.get("idea") or "").split(": ", 1)[-1], 34)
        state = "done" if done else "working" if r.get("working") else "has" if str(r["id"]) in has else "sent"
        items.append({"id": str(r["id"]), "kind": "sandbox" if sandbox else "look-idea", "label": label, "state": state,
                      "steps": QUEUE_STEPS["idea"], "t0": _when(r.get("sent_at") or r.get("at")), "t1": _when(r.get("done_at")) if done else None})
    fill = _read_json(os.path.join(jd, "review", "broll-fill.json"))
    if fill:
        tid, done = f"fill:{fill.get('at')}", bool(fill.get("done"))
        items.append({"id": tid, "kind": "broll-fill", "label": "Fill with my b-roll: " + short(str(fill.get("folder") or ""), 30),
                      "state": "done" if done else "has" if tid in has or fill.get("taken") else "sent", "steps": QUEUE_STEPS["note"],
                      "t0": _when(fill.get("at")), "t1": _when(fill.get("done")) if done else None})
    for name in looks_to_redo(jd):
        tid = "redo:" + name
        items.append({"id": tid, "kind": "redo", "label": f"Redo a look on your new cut", "state": "has" if tid in has else "sent",
                      "steps": QUEUE_STEPS["note"], "t0": None, "t1": None})
    now = time.time()
    open_ = [x for x in items if x["state"] != "done"]
    since = min((x["t0"] for x in open_ if x["t0"]), default=None)
    keep = [x for x in items if x["state"] != "done"
            or (x["t1"] and ((since and x["t1"] >= since - 5) or (not open_ and now - x["t1"] < 120)))]
    keep.sort(key=lambda x: (x["t0"] or now, x["id"]))
    return {"items": keep, "done": sum(x["state"] == "done" for x in keep), "total": len(keep), "watching": watching(jd)}


def _phase_now(jd):
    try:
        return json.load(open(os.path.join(jd, "review", "phase.json"), encoding="utf-8"))
    except Exception:
        return None


def _keep_lock(job, was, log=print):
    """After Claude changed her cut ON HER BEHALF (her cut note fixed, a Speed or Zoom she asked for in the chat, a
    `restitch`): if she had locked her cut in, it stays locked, stamped with the new cut, and the looks keyed to her
    words follow it by themselves (retime_adds). Only HER own Send of cut edits reopens phase 1 (the server's save)."""
    jd = job_dir(job)
    if not was or was.get("phase") not in ("looks", "render"):
        return False
    _atomic_json(os.path.join(jd, "review", "phase.json"), dict(was, cut_id=_cut_id(jd)))
    try:
        if os.path.isfile(os.path.join(jd, "review", "looks.json")):
            retime_adds(job)
    except Exception as e:                                   # never undoes the cut fix; the page offers the move itself
        log(f"(her looks didn't move with the cut this time: {e})")
    return True


def restitch(job, plan=None, log=print):
    """A lean round of a plan you fixed by hand (for her notes): `restitch <job> <fixed-plan.json>`. Under the same
    lock as her page, so a Send can't overwrite your fix halfway. Your fix is made for her, so a cut she locked in
    stays locked (_keep_lock). A relative plan path is found from where the command runs, else inside the reel's folder
    (`transcript/fixed-plan.json`); one found nowhere, or unreadable, is said plainly (2026-10-21: a raw traceback)."""
    jd = job_dir(job)
    was = _phase_now(jd)
    if plan:
        if not os.path.isfile(plan) and not os.path.isabs(plan) and os.path.isfile(os.path.join(jd, plan)):
            plan = os.path.join(jd, plan)
        if not os.path.isfile(plan):
            raise Refuse(f"There's no plan file at {plan!r} (looked from {os.getcwd()} and inside the reel's folder "
                         f"{jd}). Write the fixed plan first, then restitch with its path.")
        try:
            given = json.load(open(plan, encoding="utf-8"))["segments"]
        except (ValueError, KeyError, TypeError, OSError) as e:
            raise Refuse(f"The plan file {plan!r} isn't a cut plan restitch can read (it needs a \"segments\" list, as "
                         f"in transcript/cuts.json): {type(e).__name__}: {e}")
    with _making(jd, "lean"):
        if plan:
            segs = pin_wordless(jd, given)
            scratch = os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(jd))
            os.makedirs(scratch, exist_ok=True)
            _atomic_json(os.path.join(scratch, "cuts.json"), {"segments": segs})
        _stitch(jd, lean=True, log=log, keep_phase=bool(was))
    build_script(job)
    _keep_lock(job, was, log=log)


ZOOM_PRESETS = {"in": {"from": 1.0, "to": 1.15}, "out": {"from": 1.15, "to": 1.0}, "none": None}   # the page's Zoom menu


def clip_fx(job, clip_no, speed=None, zoom=None, log=print):
    """A clip's Speed and/or Zoom move set FOR her (her note asked for it): `clip-fx <job> <clip number> [--speed 2]
    [--zoom in|out|none]`. The clip number is the one her timeline shows (1 = the first clip of her cut). The same
    road her page's Speed and Zoom take (apply_edits 3b, one lean round), and her lock-in is kept (_keep_lock)."""
    jd, clips, segs, wid, cid = load(job)
    k = int(clip_no) - 1
    if not 0 <= k < len(segs):
        raise Refuse(f"Her cut has {len(segs)} clips; there's no clip {clip_no}.")
    words = kept_quiet(words_of(clips), clips, segs)
    seg_of = membership(words, clips, segs)
    w = next(i for i, g in enumerate(seg_of) if g == k)
    e = {}
    if speed is not None:
        e["speed"] = float(speed)
    if zoom is not None:
        if zoom not in ZOOM_PRESETS:
            raise Refuse("Zoom is in, out or none.")
        e["zoom"] = WIDE_ZOOMS.get(zoom, ZOOM_PRESETS[zoom]) if frame.is_wide(jd) else ZOOM_PRESETS[zoom]
    if not e or not fx_of({"fx": {str(w): e}}):
        raise Refuse(f"Speed is {FX_SPEEDS[0]:g} to {FX_SPEEDS[1]:g}; zoom is in, out or none.")
    was = _phase_now(jd)
    with _making(jd, "lean"):
        out = apply_edits(job, {"job": os.path.basename(jd), "id": wid, "cut_id": cid, "cut": [], "back": [], "fx": {str(w): e}},
                          stitch=True, log=log, keep_phase=bool(was))
    build_script(job)
    _keep_lock(job, was, log=log)
    return out


def status(job):
    jd = job_dir(job)
    p = _review_path(jd)
    base = " The rough-cut video is behind the cut (finish-cut makes it)." if base_is_stale(job) else ""
    if not os.path.exists(p):
        return "Nothing sent yet." + base
    d = json.load(open(p, encoding="utf-8"))
    return f"Sent at {d.get('saved_at', '?')}: receipt {receipt(d)}, {len(d.get('cut', []))} cut, {len(d.get('back', []))} brought back."


def _replace(tmp, path):
    """os.replace, retried briefly: on Windows it fails while another handle (the page reading status, the video
    streaming) has the target open for a moment."""
    for attempt in range(40):
        try:
            os.replace(tmp, path); return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.1)


def _atomic_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))   # unique per writer
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    _replace(tmp, path)


def _print_todo(job, items):
    """Each item Claude takes, with how to close it (shared by `todo` and the watcher's `wait`)."""
    class _A:
        pass
    a = _A(); a.job = job
    for i, t in enumerate(items, 1):
        if t["kind"] in ("cut-note", "look-note", "reel-note"):
            print(f"{i}. [{t['id']}] {t['kind'].replace('-', ' ')}, line {t['line']}, "
                  f"at “{t['word']}” ({t['clip']} {t['clip_time']}s): {t['text']}\n      the line: {t['words']}"
                  f"\n      when done: visual_editor.py resolve {a.job} {t['id']} \"what you did\"")
        elif t["kind"] == "kit":
            print(f"{i}. [{t['id']}] {t['text']}: her page's pick is review/kit-request.json")
        elif t["kind"] == "trial-won":
            print(f"{i}. [{t['id']}] {t['text']}: read its plan in trials/trials.json (id {t['trial']}: angle, open, drop, "
                  f"hook shape), say in one line what you'll keep, then `python3 product/teach_style.py keep {a.job} \"<rule>\"`")
        elif t["kind"] == "trials":
            print(f"{i}. [{t['id']}] {t['text']}: load the trial-reels skill for this reel (3 spare hooks, one pick-many)")
        elif t["kind"] == "broll-fill":
            print(f"{i}. [{t['id']}] {t['text']}\n      the rough-cut skill's \"fill my b-roll\" step: watch every clip (broll-prep steps 1-2), "
                  f"match them to her lines (visual_editor.py vo-lines {a.job}), then visual_editor.py broll-fill {a.job} <plan.json>")
        elif t["kind"] == "make-looks":
            print(f"{i}. [looks] her cut is locked in: make her looks now, the looks step exactly as for \"show me my looks\"")
        elif t["kind"] == "redo-look":
            print(f"{i}. redo the look {t['layer']} on her new cut (it was built for her old one)"
                  f"\n      when every look is redone: visual_editor.py looks-current {a.job}")
        elif t["kind"] == "chat":
            print(f"{i}. [{t['id']}] {t['text']}")
        elif t["kind"] == "edits-drive":
            print(f"{i}. [{t['id']}] {t['text']}")
        else:
            rx = (t.get("remixes") or [])[-1:] if t.get("mode") == "sandbox" and t.get("round", 1) > 1 else []
            print(f"{i}. [{t['id']}] " + (f"SANDBOX FIX: the sketch she locked in ({t.get('tried')}) didn't pass: {t['fix']}. "
                  "Fix that sketch, save it again with --sample, then tell her to press Lock it in again"
                  if t.get("fix") else (f"SANDBOX REMIX, round {t['round']}: three new sketches. Change: {rx[0]['text']}"
                  + (f" (starting from {rx[0]['from']})" if rx[0].get("from") else "") + ". Her first idea")
                  if rx else "SANDBOX: three quick sketches" if t.get("mode") == "sandbox" else "new-look idea")
                  + f" on “{t['words']}”: {t['idea']}  (the build-a-look skill"
                  + (", its Sandbox section)" if t.get("mode") == "sandbox" else ")"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["open", "prepare", "preview", "apply", "finish-cut", "check-base", "status", "url", "mode", "keep-asked",
                                    "notes", "resolve", "restitch", "looks", "accents", "redraw-highlights", "media-exit", "cutaway", "look-requests", "place-look",
                                    "look-request", "todo", "looks-current", "pack", "place", "captions", "caption-box",
                                    "sandbox-takes", "sandbox-keep", "sandbox-drop", "sandbox-working", "wait", "clip-fx", "look-effect", "tell", "announce",
                                    "vo-start", "vo-pace", "vo-folders", "vo-lines", "vo-beats", "vo-sheets", "broll-fill"])
    ap.add_argument("job", nargs="?")
    ap.add_argument("rest", nargs="*", help="resolve: <note-id> <what you did>")
    ap.add_argument("--code", help="apply: the pasted fallback text, or - to read it from stdin")
    ap.add_argument("--no-stitch", action="store_true", help="apply: write the cut plan only")
    ap.add_argument("--full", action="store_true", help="apply: a full-quality stitch instead of a lean round; "
                    "finish-cut: make it again even when the video already matches the cut")
    ap.add_argument("--force", action="store_true", help="preview: make her preview copy again even when it looks right")
    ap.add_argument("--no-browser", action="store_true", help="open: print the address instead of opening it")
    ap.add_argument("--autopilot", action="store_true", help="open: autopilot built it all, so the page opens on her Sound tab")
    ap.add_argument("--text", help="place: a hook look's own copy (a punchy reframe, never her spoken line); ' / ' splits eyebrow and headline. "
                    "A look with a heading of its own (a checklist): 'heading / item, item, item'")
    ap.add_argument("--start", type=float, help="sandbox-takes: when the look starts (cut seconds), from what she asked")
    ap.add_argument("--end", type=float, help="sandbox-takes: when it ends (cut seconds)")
    ap.add_argument("--behind", action="store_true", help="sandbox-takes: it plays behind her (her cutout, in the render)")
    ap.add_argument("--speed", type=float, help="clip-fx: how fast the clip plays (1 = normal, 2 = twice as fast)")
    ap.add_argument("--zoom", choices=["in", "out", "none"], help="clip-fx: a zoom move across the clip")
    ap.add_argument("--chat", action="store_true", help="tell: her answer goes in the chat (the card says so)")
    ap.add_argument("--go", choices=["sandbox", "notes", "cut", "visuals", "sound", "finish"], help="tell: where its button takes her")
    ap.add_argument("--kind", choices=["ree", "news"], help="announce: a major REE update, or a piece of news for the creator")
    ap.add_argument("--title", help="announce: the bell item's bold title line")
    a = ap.parse_intermixed_args()                            # options anywhere: sandbox-takes <job> <id> --start S --end E <sketch>…
    import early_access
    if a.cmd == "mode":
        print(review_mode() if early_access.editor_on() else "text")
        return
    early_access.refuse_if_off()
    if a.cmd == "keep-asked":
        import first_use
        d = first_use._load(); d[KEEP_KEY] = time.strftime("%Y-%m-%d"); first_use._save(d)
        return
    if a.cmd == "vo-folders":                                # her inbox folders with clips in them, for a b-roll fill
        for f in footage_folders():
            print(f"{f['id']}  ({f['clips']} clip{'s' if f['clips'] != 1 else ''})")
        return
    if not a.job and a.cmd != "open":                        # open with no reel named = her most recent one
        ap.error("which reel? (the job name)")
    try:
        if a.cmd == "open":
            a.job = a.job or latest_reel()
            url = open_editor(a.job, browser=not a.no_browser, autopilot=a.autopilot)
            print(url)
            print(editor_link(url))                          # every time: the browser may open behind Claude's window
            print(f"PASTE the EDITOR LINK line above into the chat exactly as it is (the bracketed text is the link "
                  f"she clicks). Her tab can open behind this window, so never skip it. Also tell her: if it ever "
                  f"disappears, double-click \"{LINK_PAGE}\" in her engine folder, or type \"open my visual editor\".")
        elif a.cmd == "url":
            from urllib.parse import quote
            print(f"http://127.0.0.1:{ensure_server()}/editor/?job={quote(os.path.basename(job_dir(a.job)))}")
        elif a.cmd == "prepare":
            prepare(a.job); print("ready")
        elif a.cmd == "preview":
            make_preview(a.job, force=a.force)
            h = editor_health(a.job, preview=False, log=print)   # her stills and waveform, made again from the new copy
            n = preview_length(a.job)
            print(f"preview: {_mmss(n['have']) if n['have'] is not None else 'none'} of footage, her cut needs "
                  f"{_mmss(n['need'])}" + (" (SHORT: see above)" if n["short"] else " (ok)")
                  + (f"; her page opens without: {', '.join(h['still_missing'][:6])}" if h["still_missing"] else ""))
        elif a.cmd == "apply":
            code = sys.stdin.read() if a.code == "-" else a.code
            apply(a.job, code=code, stitch=not a.no_stitch, lean=not a.full)
        elif a.cmd == "finish-cut":
            finish_cut(a.job, force=a.full)
        elif a.cmd == "notes":
            ns = notes(a.job)
            if not ns:
                print("No open notes.")
            for n in ns:
                print(f"[{n['id']}] line {n['line']}, at the word “{n['word']}” ({n['clip']} {n['clip_time']}s): {n['text']}\n"
                      f"      the line: {n['words']}")
        elif a.cmd == "resolve":
            if len(a.rest) < 2:
                ap.error("resolve <job> <note-id> \"what you did\"")
            resolve(a.job, a.rest[0], " ".join(a.rest[1:])); print("marked fixed")
        elif a.cmd == "restitch":
            restitch(a.job, plan=a.rest[0] if a.rest else None)
        elif a.cmd == "clip-fx":                            # clip-fx <job> <clip number> [--speed 2] [--zoom in|out|none]
            if not a.rest:
                ap.error("clip-fx <job> <clip number> [--speed X] [--zoom in|out|none]")
            clip_fx(a.job, a.rest[0], speed=a.speed, zoom=a.zoom); print("done")
        elif a.cmd == "look-effect":                        # look-effect <job> <look key> <effect|default>: drawn AND kept
            if len(a.rest) < 2:
                ap.error("look-effect <job> <look key, as `looks` lists it> <effect id, or default>")
            r = look_effect(a.job, a.rest[0], a.rest[1])
            print(f"{r['layer']} now plays {r['effect'] or 'its pack default'} and is kept on her reel (her open page picks it "
                  f"up by itself). It can take: {', '.join(x['id'] for x in r['effects'] or []) or 'no animations of its own'}.")
        elif a.cmd == "check-base":
            stale = base_is_stale(a.job)
            print("The rough-cut video is behind the cut: run finish-cut before the looks." if stale else "The rough-cut video matches the cut.")
            sys.exit(1 if stale else 0)
        elif a.cmd == "status":
            print(status(a.job))
        elif a.cmd == "accents":
            print(accents_report(a.job))
        elif a.cmd == "media-exit":                         # media-exit <job> <add-key> <exit> [seconds in her cut]
            r = media_exit(a.job, a.rest[0], a.rest[1], float(a.rest[2]) if len(a.rest) > 2 else None)
            print(f"{a.rest[0]} now leaves by {a.rest[1]}" + (f", starting at {a.rest[2]}s." if len(a.rest) > 2 else "."))
        elif a.cmd == "cutaway":                            # cutaway <job> <add-key> [slip=S] [start=S] [end=S] [sound=on|off] [fade|cut] [best]
            kv = dict(x.split("=", 1) for x in a.rest[1:] if "=" in x)
            num = lambda k: float(kv[k]) if k in kv else None
            r = cutaway_set(a.job, a.rest[0], slip=num("slip"), start=num("start"), end=num("end"),
                            sound={"on": True, "off": False}.get(kv.get("sound")),
                            effect=next((x for x in a.rest[1:] if x in dict(CUTAWAY_EFFECTS)), None), best="best" in a.rest[1:])
            print(f"{a.rest[0]}: {r['start']:.2f}s to {r['end']:.2f}s of her cut, playing {r['slip']:.2f}s into her clip, "
                  f"{'its sound on' if r['sound'] else 'muted'}, {r['effect']}. Her page shows it now.")
        elif a.cmd == "redraw-highlights":                  # a look drawn before her highlights reached it: catch it up
            got = redraw_line_highlights(a.job)
            print(f"Drawn again with her highlights: {', '.join(got)}." if got else "Every line look already wears her highlights.")
        elif a.cmd == "wait":                               # the watcher: returns when she leaves Claude something, claimed
            items = wait_for_her(a.job)
            if items is None:
                print("STOP: her page has been closed (or untouched) for 30 minutes, so the watcher stopped. Don't start "
                      "it again and say nothing about it; \"open my editor\" starts it again.")
            elif not items:
                print("WAIT: nothing new from her page. Start the watcher again (in the background).")
            else:
                print(f"HER PAGE: {len(items)} thing{'s' if len(items) > 1 else ''} for Claude. Start the watcher again "
                      f"(in the background) right away, then do these exactly as for \"update my edit\":")
                _print_todo(a.job, items)
        elif a.cmd == "todo":                               # "update my edit": everything waiting for Claude, in order
            items = todo(a.job)
            if items:                                        # her page: "Claude is on your changes", for exactly these ones
                claim(a.job, items)
            # "update my edit" always starts the watcher too (her ask, 2026-10-18): her next note moves without typing
            print(f"FIRST: start the watcher in the background, `python3 product/visual_editor.py wait {a.job}` (a second "
                  "one for this reel refuses itself, so it is harmless if one is running).")
            if not items:
                print("Nothing is waiting for Claude: her preview is up to date.")
            _print_todo(a.job, items)
        elif a.cmd == "pack":                               # pack <job> <Pack>: switch the whole reel's looks to that pack
            if not a.rest:
                ap.error("pack <job> <Pack name>")
            r = set_pack(a.job, " ".join(a.rest))
            print(f"The reel is in {r['pack']} now: {len(r['redrawn'])} look(s) redrawn"
                  + (f"; {len(r['kept'])} made just for this reel stay as they are." if r["kept"] else "."))
        elif a.cmd == "place":                              # place <job> <look> <start> <end>: the page-path build, one look
            if len(a.rest) < 3:
                ap.error("place <job> <look> <start-seconds> <end-seconds> [--text \"hook copy\"]")
            r = place_at(a.job, a.rest[0], a.rest[1], a.rest[2], copy=a.text)
            print(f"{a.rest[0]} placed ({r.get('layer')})" + (f" · {r['warn']}" if r.get("warn") else ""))
        elif a.cmd == "captions":                           # captions <job> <style>: the reel's captions, whole cut
            if not a.rest:
                ap.error("captions <job> <single-word|phrase|karaoke|spotlight>")
            r = set_captions(a.job, a.rest[0])
            print(f"Her captions are {a.rest[0]} now ({r.get('layer')}).")
        elif a.cmd == "caption-box":                        # caption-box <job> [size=0.8] [narrower=80]: size + width, kept
            kv = dict(x.split("=", 1) for x in a.rest if "=" in x)
            r = set_caption_box(a.job, size=float(kv["size"]) if "size" in kv else None,
                                narrower=float(kv["narrower"]) if "narrower" in kv else None)
            print("Caption box set:" + (f" size {r['size']}" if r.get("size") is not None else "")
                  + (f" narrower {r['narrower']}px" if r.get("narrower") is not None else "")
                  + (" (captions redrawn)" if r.get("redrawn") else ""))
        elif a.cmd == "looks-current":
            looks_current(a.job); print("Her looks are marked current for her cut.")
        elif a.cmd == "look-requests":                      # her "Build a new look" ideas, for the chat
            rs = look_requests(a.job)
            if not rs:
                print("No new-look ideas waiting.")
            for r in rs:
                still = f"projects/{os.path.basename(job_dir(a.job))}/review/{r['frame']}" if r.get("frame") else "(no still)"
                print(f"[{r['id']}] {r.get('mode', 'build')} · {r['status']} · "
                      + (f"line from {r['start']}s to {r['end']}s · key add-w{r['w']}\n" if r.get("w") is not None else "no line: her words say where\n")
                      + f"      her words around it: {r['words']}\n      her idea: {r['idea']}\n      still: {still}"
                      + (f"\n      her playhead when she asked: {r['playhead']}s (\"right here\" / \"at this moment\" means this)" if r.get("playhead") is not None else "")
                      + "".join(f"\n      remix {k + 2}: {x['text']}" + (f" (from {x['from']})" if x.get("from") else "") for k, x in enumerate(r.get("remixes") or []))
                      + (f"\n      on her line now: {r['look']}" if r.get("look") else ""))
        elif a.cmd == "place-look":                         # place-look <job> <request-id> <look-id>
            if len(a.rest) < 2:
                ap.error("place-look <job> <request-id> <look-id>")
            r = next((x for x in look_requests(a.job, open_only=False) if x["id"] == a.rest[0]), None)
            if not r:
                raise Refuse(f"There's no idea {a.rest[0]!r} for this reel.")
            out = place_look(a.job, f"add-w{r['w']}", r["start"], r["end"], a.rest[1])
            look_request_status(a.job, r["id"], "draft", a.rest[1])
            print(f"{a.rest[1]} is on her line now (add-w{r['w']})" + (f" · {out['warn']}" if out.get("warn") else ""))
        elif a.cmd == "sandbox-takes":                      # sandbox-takes <job> <idea-id> [--start S --end E] [--behind] <take> …
            if len(a.rest) < 2:
                ap.error("sandbox-takes <job> <idea-id> <take-look-id> [<take-look-id> ...]")
            r = sandbox_takes(a.job, a.rest[0], a.rest[1:], a.start, a.end, a.behind)
            print(f"{len(r['takes'])} sketches are in her Sandbox panel (her reel is unchanged until she locks one in)")
        elif a.cmd == "sandbox-keep":                       # sandbox-keep <job> <idea-id> reuse|oneoff [name]
            if len(a.rest) < 2:
                ap.error("sandbox-keep <job> <idea-id> reuse|oneoff [sketch-id] [name]")
            look = a.rest[2] if len(a.rest) > 2 and a.rest[2].startswith("my-sandbox-") else None
            r = sandbox_keep(a.job, a.rest[0], a.rest[1], " ".join(a.rest[3 if look else 2:]) or None, look)
            print(f"committed {r['look']} ({'in her lookbook for every reel' if r['kept'] == 'reuse' else 'this reel only'})")
        elif a.cmd == "sandbox-working":                    # the first thing "sandbox" does: her page says Claude is on it
            if not a.rest:
                ap.error("sandbox-working <job> <idea-id>")
            sandbox_working(a.job, a.rest[0]); print("her page says you're working on it")
        elif a.cmd == "sandbox-drop":
            if not a.rest:
                ap.error("sandbox-drop <job> <idea-id>")
            sandbox_drop(a.job, a.rest[0]); print("takes cleared; her line is back the way it was")
        elif a.cmd == "look-request":                       # look-request <job> <request-id> done|dropped [look-id]
            if len(a.rest) < 2 or a.rest[1] not in ("done", "dropped"):
                ap.error("look-request <job> <request-id> done|dropped [look-id]")
            look_request_status(a.job, a.rest[0], a.rest[1], a.rest[2] if len(a.rest) > 2 else None)
            print(f"marked {a.rest[1]}")
        elif a.cmd == "tell":                               # tell <job> "<one plain line>" [--chat] [--go <tab>]: her page pops it
            if not a.rest:
                ap.error('tell <job> "<one plain line>" [--chat] [--go sandbox|notes|cut|visuals|sound|finish]')
            import editor_says
            jd = job_dir(a.job)
            editor_says.tell(jd, " ".join(a.rest), chat=a.chat, kind="chat" if a.chat else "note", go=a.go)
            print("Her page shows it now." if os.path.realpath(jd) in map(os.path.realpath, editor_says.open_pages())
                  else "Her editor isn't open right now: it pops when she opens it (within 6 hours).")
        elif a.cmd == "announce":                           # announce <job> "<text>" --kind news|ree [--title "..."] [--go <tab>]: the BELL (not the chat)
            if not a.rest:
                ap.error('announce <job> "<text>" --kind news|ree [--title "..."] [--go finish|visuals|sound|cut|sandbox]')
            import editor_announce
            jd = job_dir(a.job)
            m = editor_announce.add(jd, a.kind or "news", a.title or "", " ".join(a.rest), go=a.go)
            print(f"✓ bell [{m['kind']}]: {m['title'] or m['text']}"
                  + ("" if os.path.realpath(jd) in map(os.path.realpath, __import__('editor_says').open_pages())
                     else "  (she'll see it when her editor is open)"))
        elif a.cmd == "vo-start":                           # vo-start <job> <her recording> [punchy|emotional]
            if not a.rest:
                ap.error("vo-start <job> <her recording> [punchy|emotional]")
            d = vo_start(a.job, a.rest[0], a.rest[1] if len(a.rest) > 1 else None)
            print(f"{d['job']}: her voiceover ({d['seconds']}s) is {d['clip']}, on a black 9:16 picture, ready for the rough cut"
                  + (f" ({d['pace']})" if d.get("pace") else ""))
        elif a.cmd == "vo-pace":                            # vo-pace <job> punchy|emotional
            if not a.rest:
                ap.error("vo-pace <job> punchy|emotional")
            print(f"pace: {vo_pace(a.job, a.rest[0])['pace']} (the next cut follows it)")
        elif a.cmd == "vo-lines":                           # her lines in cut seconds, and where no clip is yet
            jd = job_dir(a.job)
            for l in vo_lines(jd):
                print(f"{l['line']:3d}  {l['start']:7.2f}-{l['end']:7.2f}  ({l['end'] - l['start']:4.1f}s)  {l['text']}")
            folder = _fill_folder(jd)
            if folder:
                print(f"\nher clips (inbox/{folder}), as media ids:")
                for c in _folder_clips(folder):
                    print(f"  {c['id']}  ({_clip_len(media_path(c['id'])):.1f}s)")
            if voiceover_of(jd):
                gaps = vo_gaps(jd)
                print("\nno clip yet: " + (", ".join(f"{s:.2f}-{e:.2f}" for s, e in gaps) if gaps else "none, every second has a clip"))
            else:
                picks = (_read_json(os.path.join(jd, "review", "broll-fill.json")) or {}).get("lines") or []
                print("\na talking head: b-roll goes ONLY on the lines she picked: " + (", ".join(map(str, picks)) or "none yet"))
        elif a.cmd == "vo-beats":                           # her words cut into shots (the fill's cut rules)
            jd = job_dir(a.job)
            picks = None if voiceover_of(jd) else (_read_json(os.path.join(jd, "review", "broll-fill.json")) or {}).get("lines")
            if not voiceover_of(jd) and not picks:
                raise Refuse("A talking head gets b-roll only on the lines she ticks, and she hasn't ticked any yet.")
            pace = (voiceover_of(jd) or {}).get("pace") or "punchy"
            print(f"pace: {pace} (a shot holds {BEAT_HOLD[pace][0]}-{BEAT_HOLD[pace][1]} s)"
                  + ("" if voiceover_of(jd) else f"; only her ticked lines: {', '.join(map(str, picks))}"))
            run = None
            for b in vo_beats(jd, picks):
                if run is not None and b["run"] != run:
                    print("   ── her face (lines she didn't tick)")
                run = b["run"]
                print(f"{b['beat']:3d}  {b['start']:7.2f}-{b['end']:7.2f} ({b['end'] - b['start']:4.1f}s)"
                      f"{'  hook' if b['hook'] else '      '}  line {','.join(map(str, b['lines']))}: {b['text']}")
        elif a.cmd == "vo-sheets":                          # vo-sheets <job> [<media id> <start> <end>]
            r = a.rest
            sheets = fill_sheets(a.job, clip=r[0] if r else None, start=float(r[1]) if len(r) > 1 else None,
                                 end=float(r[2]) if len(r) > 2 else None)
            for path, rows in sheets:
                print(f"{path}  (Read it; the yellow number is the row, the white number under a frame its second)")
                n0 = sum(len(x[1]) for x in sheets[:sheets.index((path, rows))])
                for k, (m, L, ts) in enumerate(rows, n0 + 1):
                    print(f"  {k:2d}. {m}  ({L}s)")
        elif a.cmd == "broll-fill":                         # broll-fill <job> <plan.json>
            if not a.rest:
                ap.error("broll-fill <job> <plan.json>")
            out = broll_fill(a.job, a.rest[0])
            print(f"{len(out['placed'])} clip{'s' if len(out['placed']) != 1 else ''} on her {'voiceover' if voiceover_of(job_dir(a.job)) else 'reel'}. Her open page picks them up by itself."
                  + (f" Left off, for want of room beside a clip she put on herself: {', '.join(out['skipped'])}." if out["skipped"] else "")
                  + ("\nStill no clip: " + ", ".join(f"{s:.2f}-{e:.2f}" for s, e in out["gaps"]) if out["gaps"] else ""))
        elif a.cmd == "looks":
            made = os.path.join(job_dir(a.job), "review", "looks-made.json")
            try:
                first = json.load(open(made, encoding="utf-8")).get("cut_id") != _cut_id(job_dir(a.job))
            except Exception:
                first = True
            _atomic_json(made, {"cut_id": _cut_id(job_dir(a.job)), "at": time.time()})
            d = looks_manifest(job_dir(a.job))
            if first and d and d.get("layers"):              # her looks for this cut, the first time: her page pops it
                import editor_says
                editor_says.told(job_dir(a.job), "Your looks are ready. Press play to watch them on your cut.", kind="looks", go="visuals")
            if d and d.get("clean"):
                print("No looks on this reel, on purpose: her page moves on to Sound and Finish.")
            elif not d:
                print("No graphics built for this reel yet, so the page has no looks to show.")
            else:
                print(f"{len(d['layers'])} graphic{'s' if len(d['layers']) != 1 else ''} ready to play live on the page"
                      + (f", {sum(1 for l in d['layers'] if l['behind'])} of them behind her (the page says so)" if any(l['behind'] for l in d['layers']) else "")
                      + ". Her open page picks them up by itself.")
    except Refuse as e:
        _note_error(a, str(e), "told")
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except Exception:
        _note_error(a, None, "error")
        raise


def _note_error(a, msg, kind):
    try:
        import editor_errors
        editor_errors.record("chat: visual_editor.py " + a.cmd, msg, job=a.job, kind=kind)
    except Exception:
        pass


if __name__ == "__main__":
    main()
