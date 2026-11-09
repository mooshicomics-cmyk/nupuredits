#!/usr/bin/env python3
"""learned.py — the preferences the creator has TAUGHT this engine, as values a build can apply.

`brand-kit.md` Part C promises, in writing, that what she teaches is read before the next reel is built.
For a long time only the prose half existed: a bullet in a markdown file that a future session might or
might not open. Prose is not a mechanism. A tester was told her CapCut pass had been learned and saved —
true of the file, false of every build that followed.

So a preference is now written TWICE:
  * the bullet in brand-kit.md Part C, in her words — that half is hers to read.
  * a record here, in `_local/learned.json` — that half is what the builders actually apply.

`_local/` is protected by the updater and never ships, so what she teaches is hers and survives updates.

WHAT CAN BE LEARNED (and what deliberately cannot)
FIELDS below is an allowlist. A preference is only learnable when carrying it into the NEXT reel is safe:
sizes, spacing, density, which open zone to prefer, a named effect. Three things stay out on purpose:

  * REGISTER and ROUTE — asked fresh every reel, because they are decisions about THIS video.
  * HOOK COPY — measured, and never a mirror of the spoken line. A remembered hook is a wrong hook.
  * A PLACEMENT NUMBER — where she is on screen is MEASURED per reel (`subject_place`), never picked and
    never carried forward. A number learned on one reel lands on her forehead in the next. What IS
    learnable is which measured open zone to prefer (`hook.zone` = above/below/left/right); the number
    still comes from the measurement of THAT footage.

Everything is clamped to the bounds in FIELDS, so a bad record degrades one value instead of a reel.

API
  get(field, default, **ctx)   -> the learned value, else `default`; records that it was used
  value(field, default, **ctx) -> (value, record|None) when the caller wants the provenance
  add(field, value, ...)       -> validate + append (the `/learn` skill calls this)
  forget(ident)                -> drop one by id or by its number in `records()`
  records()                    -> every record, newest last
  report()                     -> the lines a build prints, so she can SEE what was applied
Stdlib only. Every entry point degrades to the shipped default rather than raising: a preferences file
must never be able to take a build down.
"""
import json, os, sys, time, uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
STORE = os.path.join(ROOT, "_local", "learned.json")

# field -> how it is validated and bounded.
#   int/float : clamped into [lo, hi]
#   choice    : must be one of `of`
#   bool      : as-is
#   effect    : must name a real text effect (shipped catalog or one of hers)
FIELDS = {
    "hook.size":            {"kind": "int",    "lo": 8,   "hi": 24,  "what": "hook text size (CapCut route)"},
    "hook.zone":            {"kind": "choice", "of": ["above", "below", "left", "right"],
                             "what": "which measured open zone the hook prefers"},
    "thought.size":         {"kind": "int",    "lo": 6,   "hi": 20,  "what": "thought-bubble text size"},
    "thought.line_spacing": {"kind": "float",  "lo": -0.5, "hi": 0.5, "what": "thought-bubble line spacing"},
    "caption.zone":         {"kind": "choice", "of": ["above", "below", "left", "right"],
                             "what": "which measured open zone the captions prefer"},
    "caption.size_scale":   {"kind": "float",  "lo": 0.8, "hi": 1.6, "what": "caption size, relative to the pack's own"},
    "caption.never_hide":   {"kind": "bool",   "what": "her captions stay on under every look, even one that shows the same "
                                                "words (a card, a label, a hook); only a caption style she picks for a line replaces them"},
    "sound.music_under_voice_db": {"kind": "float", "lo": 4.0, "hi": 24.0,
                             "what": "how far under her voice a music bed sits, in dB (Louder / Quieter on a reel teaches it)"},
    "sfx.density":          {"kind": "choice", "of": ["lighter", "normal", "heavier"],
                             "what": "how many sound cues a reel gets"},
    "motion.opener_zoom":   {"kind": "bool",   "what": "the slow push-in on the opening shot"},
    "effects.hook":         {"kind": "effect", "what": "the hook's text animation"},
    "effects.takeover":     {"kind": "effect", "what": "the takeover's text animation"},
    "effects.caption":      {"kind": "effect", "what": "the caption's text animation"},
    "hook.when_covered":    {"kind": "choice", "of": ["below", "shorter"],
                             "what": "when a graphic is in the hook's top spot: move the hook to the open zone under "
                                     "her chin for its full length, or keep it on top and end it as the graphic comes in"},
    "hook.on_hair":         {"kind": "bool",   "what": "on a close-up with no room above your head, a hook may sit on her hair (never her face)"},
    "review.style_plan":    {"kind": "choice", "of": ["widget", "table"],
                             "what": "first rough-cut review: the visual style plan, or the lighter table"},
    "review.style_plan_mode": {"kind": "choice", "of": ["ask", "visual", "text"],
                             "what": "the style plan: ask each time, always the visual editor, or always text only"},
    "review.beat_sheet":    {"kind": "choice", "of": ["ask", "always", "skip"],
                             "what": "before the render: offer the beat sheet, always show it, or skip it"},
}
# NOT here on purpose: the style PACK. `creative-vault/user-style.json` already owns which pack is hers
# (cleanyap.set_default_pack), and a second place to say it is a second answer to the same question. "Always
# use Butter" routes to set_default_pack, not to a preference record.

# Scope keys a record may carry. Absent = applies everywhere; present = must match the build.
SCOPES = ("format", "register", "pack")

_USED = {}          # field -> record, for report()
_CTX = {}           # this build's format / register / pack, set once by the build script


def set_context(**ctx):
    """Name this build (format / register / pack) once, so every later get() is scoped without the call
    sites having to thread it through. A build script calls this; the builders just read."""
    for k, v in ctx.items():
        if k in SCOPES and v:
            _CTX[k] = str(v)
    return dict(_CTX)


def context():
    return dict(_CTX)


def context_for_build(format, register=None, pack=None, job_dir=None):
    """Every builder calls this once, before it reads a preference, so a preference taught for ONE kind of
    reel ("only my confessional reels") can match. Without it the context is empty and every scoped record
    is skipped: that shipped silently for a while, and a promise in the course depended on it.

    register: what the reel's own plan says wins (`projects/<job>/caption-plan.json` "register"), then the
              caller's value (the builder's own register when it only builds one). pack: the caller's, else
              her saved default. Anything still unknown stays unset, so a scoped record never guesses."""
    plan_register = None
    if job_dir:
        try:
            with open(os.path.join(job_dir, "caption-plan.json"), encoding="utf-8") as fh:
                plan_register = (json.load(fh) or {}).get("register")
        except (OSError, ValueError, AttributeError):
            plan_register = None
    if not pack:
        try:
            import user_style
            pack = user_style.default_pack(os.path.join(ROOT, "product", "creative-vault", "user-style.json"))
        except ImportError:
            pack = None
    return set_context(format=format, register=plan_register or register, pack=pack)


# ───────────────────────────── store ─────────────────────────────

def _read():
    try:
        with open(STORE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    recs = data.get("preferences") if isinstance(data, dict) else data
    return [r for r in recs if isinstance(r, dict)] if isinstance(recs, list) else []


def _damaged():
    """True when the store EXISTS but cannot be read as preferences: cut off mid-write, hand-edited into
    invalid JSON, or the wrong shape. A missing file is not damaged; that is simply nothing taught yet.

    _read() treats both the same (no preferences), which is right for a build and wrong for a write: the
    next /learn used to save its one new record over the top, and everything taught before it was gone."""
    if not os.path.exists(STORE):
        return False
    try:
        with open(STORE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return True
    recs = data.get("preferences", []) if isinstance(data, dict) else data
    return not isinstance(recs, list)


def _shown(path):
    """A path as she would look for it: relative to the engine folder when it is inside it."""
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:              # Windows: a path on another drive has no relative form
        return path
    return path if rel.startswith("..") else rel


def _say(msg):
    """print() that can never fail on a console that cannot show a status symbol (a Windows cp1252 pipe,
    when this is imported rather than run): there the glyph shows as "?" and the words stay."""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"))


def _set_aside():
    """Move a damaged store out of the way (never over an earlier one), say so, and return where it went.
    Nothing is written unless this succeeds, so a damaged file is never overwritten."""
    dest = f"{STORE}.damaged-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 2
    while os.path.exists(dest):
        dest = f"{STORE}.damaged-{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    try:
        os.replace(STORE, dest)
    except OSError as exc:
        raise LearnError(f"your saved preferences file ({_shown(STORE)}) is damaged and could not be moved "
                         f"aside ({exc}), so nothing was saved and nothing in it was changed.")
    _say(f"  ⚠ your saved preferences file ({_shown(STORE)}) was damaged and could not be read, so none of "
         f"what you taught before could be used. It is kept, unchanged, at {_shown(dest)}, and a fresh one "
         f"starts now. The plain-language list of what you taught is still in brand-kit.md Part C.")
    return dest


def _write(recs):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    payload = {
        "_doc": "Preferences you have taught this engine. Written when you say \"learn my pattern for the "
                "next reel\" or \"remember that\", and read before every build. The plain-language version "
                "of each one is in brand-kit.md Part C. Say \"/learn list\" to see them, \"/learn forget "
                "<number>\" to drop one.",
        "preferences": recs,
    }
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, STORE)


def records():
    """Every saved preference, oldest first. Safe on a missing or damaged file (returns [])."""
    return _read()


# ─────────────────────────── validation ───────────────────────────

class LearnError(Exception):
    """Raised by add() only. The message is what the creator sees."""


def _effect_names():
    try:
        import text_effects
        return set(text_effects.E)
    except Exception:
        return set()


def _coerce(field, value):
    """Validate + clamp `value` for `field`. Returns (value, note_if_clamped). Raises LearnError if the
    field is not learnable or the value is not usable at all."""
    spec = FIELDS.get(field)
    if not spec:
        raise LearnError(
            f"'{field}' is not something the engine can carry into the next reel. Learnable: "
            + ", ".join(sorted(FIELDS)) + ".")
    kind = spec["kind"]
    if kind in ("int", "float"):
        try:
            v = int(value) if kind == "int" else float(value)
        except (TypeError, ValueError):
            raise LearnError(f"{field} needs a number, got {value!r}.")
        lo, hi = spec["lo"], spec["hi"]
        if v < lo or v > hi:
            return (lo if v < lo else hi), f"kept inside the safe range {lo}–{hi}"
        return v, None
    if kind == "choice":
        v = str(value).strip().lower()
        if v not in spec["of"]:
            raise LearnError(f"{field} must be one of: {', '.join(spec['of'])}.")
        return v, None
    if kind == "bool":
        if isinstance(value, bool):
            return value, None
        v = str(value).strip().lower()
        if v in ("true", "yes", "on", "1"):
            return True, None
        if v in ("false", "no", "off", "0"):
            return False, None
        raise LearnError(f"{field} is on or off, got {value!r}.")
    if kind == "effect":
        names = _effect_names()
        v = str(value).strip()
        if names and v not in names:
            raise LearnError(f"there is no text effect called {v!r}. Say \"library\" to see the ones you "
                             f"have, or teach a new one with /learn effect.")
        return v, None
    return str(value), None


def add(field, value, note="", scope=None, from_job=None):
    """Save one preference. Returns (record, clamp_note). Raises LearnError before writing anything."""
    val, clamped = _coerce(field, value)
    scope = {k: str(v) for k, v in (scope or {}).items() if k in SCOPES and v}
    rec = {
        "id": uuid.uuid4().hex[:8],
        "field": field,
        "value": val,
        "scope": scope,
        "note": (note or "").strip(),
        "from_job": from_job or "",
        "date": time.strftime("%Y-%m-%d"),
    }
    if _damaged():          # a damaged store is moved aside, never written over
        _set_aside()
    recs = _read()
    # A newer preference on the same field AT THE SAME SCOPE replaces the older one: teaching it twice is
    # refining, not stacking, and two live records for one field make "which is winning?" unanswerable.
    recs = [r for r in recs if not (r.get("field") == field and (r.get("scope") or {}) == scope)]
    recs.append(rec)
    _write(recs)
    return rec, clamped


def forget(ident):
    """Drop a preference by id or by its 1-based number in records(). Returns the removed record or None."""
    recs = _read()
    gone = None
    try:
        n = int(ident)
        if 1 <= n <= len(recs):
            gone = recs.pop(n - 1)
    except (TypeError, ValueError):
        for i, r in enumerate(recs):
            if r.get("id") == str(ident):
                gone = recs.pop(i)
                break
    if gone:
        _write(recs)
    return gone


# ─────────────────────────── resolution ───────────────────────────

def _matches(rec, ctx):
    """A record applies when every scope key it names matches this build. A record with no scope applies
    everywhere; a record scoped to something this build did not state does NOT apply (an unknown register
    must not inherit a confessional preference)."""
    for k, want in (rec.get("scope") or {}).items():
        if str(ctx.get(k) or "").lower() != str(want).lower():
            return False
    return True


def value(field, default=None, **ctx):
    """(value, record) for `field` in this build's context, else (default, None).

    The MOST SPECIFIC matching record wins — a preference taught for confessional yaps beats one taught
    everywhere — and the newest wins a tie, so re-teaching always takes effect."""
    if field not in FIELDS:
        return default, None
    merged = dict(_CTX)
    merged.update({k: v for k, v in ctx.items() if v})
    ctx = merged
    best, best_rank = None, -1
    for i, rec in enumerate(_read()):
        if rec.get("field") != field or not _matches(rec, ctx):
            continue
        rank = len(rec.get("scope") or {}) * 1000 + i          # specificity, then recency
        if rank > best_rank:
            best, best_rank = rec, rank
    if best is None:
        return default, None
    try:
        v, _ = _coerce(field, best.get("value"))               # re-clamp on read: an edited file cannot widen bounds
    except LearnError:
        return default, None
    _USED[field] = best
    return v, best


def get(field, default=None, **ctx):
    """The learned value for `field`, else `default`."""
    return value(field, default, **ctx)[0]


# ───────────────────────────── report ─────────────────────────────

def report(prefix="  "):
    """Lines naming what this build took from her saved preferences, for the build to PRINT.

    A preference applied silently is indistinguishable from one ignored, which is how a creator ends up
    re-teaching the same thing. Only fields actually READ this run appear."""
    if not _USED:
        return []
    out = [f"{prefix}from what you've taught me:"]
    for field, rec in _USED.items():
        spec = FIELDS.get(field, {})
        scope = rec.get("scope") or {}
        where = (" (" + ", ".join(f"{v}" for v in scope.values()) + " only)") if scope else ""
        note = f" — \"{rec['note']}\"" if rec.get("note") else ""
        val = rec["value"]
        shown = ("on" if val else "off") if isinstance(val, bool) else val
        out.append(f"{prefix}  · {spec.get('what', field)}: {shown}{where}{note}")
    out.append(f"{prefix}  say \"/learn list\" to see them, \"/learn forget <n>\" to drop one")
    return out


def reset_report():
    """Forget what was read this run (a process that builds several reels reports each one separately)."""
    _USED.clear()
    _CTX.clear()


# ────────────────────────────── CLI ───────────────────────────────

def _fmt(i, r):
    scope = ", ".join(f"{k}={v}" for k, v in (r.get("scope") or {}).items())
    bits = [f"{i}. {r['field']} = {r['value']}"]
    if scope:
        bits.append(f"[{scope}]")
    if r.get("note"):
        bits.append(f'"{r["note"]}"')
    tail = "  ".join(x for x in (r.get("from_job"), r.get("date")) if x)
    return "  ".join(bits) + (f"   ({tail})" if tail else "")


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "list"
    if cmd in ("list", "forget") and _damaged():
        # "Nothing taught yet" / "no preference 2" would be untrue: there is a file, it just cannot be read.
        print(f"Your saved preferences file ({_shown(STORE)}) is damaged and cannot be read, so builds are "
              f"using the shipped defaults for now. Nothing has been changed or deleted. The next thing you "
              f"teach moves it aside, kept as it is, and starts a fresh one. The plain-language list of what "
              f"you taught is in brand-kit.md Part C.")
        sys.exit(1)
    if cmd == "list":
        recs = records()
        if not recs:
            print("Nothing taught yet. After a reel, say \"learn my pattern for the next reel\".")
        for i, r in enumerate(recs, 1):
            print(_fmt(i, r))
    elif cmd == "fields":
        for f, s in FIELDS.items():
            rng = (f"  {s['lo']}–{s['hi']}" if "lo" in s else
                   ("  " + "/".join(s["of"]) if "of" in s else ""))
            print(f"{f:24} {s['what']}{rng}")
    elif cmd == "forget" and len(argv) > 1:
        gone = forget(argv[1])
        print(f"forgot: {gone['field']} = {gone['value']}" if gone else f"no preference {argv[1]!r}")
    elif cmd == "add" and len(argv) >= 3:
        try:
            rec, clamped = add(argv[1], argv[2], note=" ".join(argv[3:]))
            print(f"saved: {rec['field']} = {rec['value']}" + (f"  ({clamped})" if clamped else ""))
        except LearnError as e:
            print(f"not saved: {e}")
            sys.exit(1)
    else:
        print(__doc__.strip().splitlines()[0])
        print("usage: learned.py [list | fields | add <field> <value> [note] | forget <n|id>]")
