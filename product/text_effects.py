#!/usr/bin/env python3
"""text_effects.py — the SHARED named text-animation vocabulary for every rendered
overlay (.mov) and baked reel (.mp4). One place that turns an effect NAME into the
GSAP timeline lines the HyperFrames compositions run, so the rendered builders stop
hardcoding a single fade+rise and can name any of the catalog's effects per element.

Used by build-reel-type.py (hook, takeover) and build-hf-captions.py (takeover); any
composition can adopt it. It does NOT touch the CapCut editable-text path — this is
rendered-output motion only (the one place baking costs no editability).

The 24 IDs are the animate-text vocabulary carried by the hyperframes-animation skill
(per-character / per-word / per-line / whole-element). The EXACT frame specs live in
the upstream `/animate-text` skill, which is not vendored (licensing); this module is
the shippable GSAP-from-name implementation (the sanctioned fallback). For a personal
reel you can load `/animate-text` and hand-tune timings; the engine ships these.

Per-reel control: caption-plan.json
  "effects": {"hook": "focus-blur-resolve", "takeover": "bottom-up-letters"}
Any role left out uses DEFAULTS below. Pin the old look with "rise". "snap"/"karaoke"
are no-op sentinels (the builder keeps its locked behavior for those).

API
  resolve(caption_plan, role)          -> effect id (plan override else DEFAULTS)
  intro_sel(sel, effect, at, ...)      -> GSAP lines applying `effect` to a selector
                                          (whole element; `sel` may match many, with `stagger`)
  render(elid, text, effect, at, esc)  -> (inner_html, gsap_lines); splits into
                                          char/word units when the effect needs it
  CSS                                  -> helper classes the split effects rely on
Deterministic. No randomness, no dates.
"""

# ── per-role defaults (overridable per reel via caption-plan "effects") ──────────────
DEFAULTS = {
    "hook":     "soft-blur-in",       # headline / hook fragments — subtle premium resolve
    "takeover": "spring-scale-in",    # full-screen word stack — each word pops as spoken
    "caption":  "snap",               # snap read-along stays instant (locked) unless overridden
    "karaoke":  "karaoke",            # word-build karaoke keeps its color reveal (no intro motion)
}

# ── the catalog. gran: element | char | word (char/word split only via render()). ────
# Each effect = an initial state (frm, set at t0) tweened to a resting state (to). `then`
# adds follow-up tweens (for out-and-back effects). `mask` wraps each char in an
# overflow-hidden cell (slot-machine reveals). `stagger`/`stagger_from` drive split units.
_NOOP = {"noop": True}
E = {
    # ── per-character ──────────────────────────────────────────────────────────────
    "soft-blur-in":       {"gran": "char", "frm": {"autoAlpha": 0, "filter": "blur(8px)", "y": 6},
                           "to": {"autoAlpha": 1, "filter": "blur(0px)", "y": 0}, "dur": 0.5, "ease": "power2.out", "stagger": 0.03},
    "per-character-rise": {"gran": "char", "frm": {"autoAlpha": 0, "yPercent": 70},
                           "to": {"autoAlpha": 1, "yPercent": 0}, "dur": 0.5, "ease": "back.out(1.7)", "stagger": 0.03},
    "typewriter":         {"gran": "char", "frm": {"autoAlpha": 0}, "to": {"autoAlpha": 1},
                           "dur": 0.001, "ease": "steps(1)", "stagger": 0.046},
    "bottom-up-letters":  {"gran": "char", "mask": True, "frm": {"yPercent": 110}, "to": {"yPercent": 0},
                           "dur": 0.52, "ease": "power3.out", "stagger": 0.03},
    "top-down-letters":   {"gran": "char", "mask": True, "frm": {"yPercent": -110}, "to": {"yPercent": 0},
                           "dur": 0.52, "ease": "power3.out", "stagger": 0.03},
    "stagger-from-center":{"gran": "char", "frm": {"autoAlpha": 0, "y": 10, "scale": 0.8}, "to": {"autoAlpha": 1, "y": 0, "scale": 1},
                           "dur": 0.5, "ease": "power2.out", "stagger": 0.03, "stagger_from": "center"},
    "stagger-from-edges": {"gran": "char", "frm": {"autoAlpha": 0, "y": 10, "scale": 0.8}, "to": {"autoAlpha": 1, "y": 0, "scale": 1},
                           "dur": 0.5, "ease": "power2.out", "stagger": 0.03, "stagger_from": "edges"},
    # ── per-word ─────────────────────────────────────────────────────────────────────
    "per-word-crossfade": {"gran": "word", "frm": {"autoAlpha": 0}, "to": {"autoAlpha": 1}, "dur": 0.5, "ease": "sine.inOut", "stagger": 0.16},
    "spring-scale-in":    {"gran": "element", "frm": {"autoAlpha": 0, "scale": 0.5}, "to": {"autoAlpha": 1, "scale": 1}, "dur": 0.5, "ease": "back.out(2)"},
    "shared-axis-y":      {"gran": "element", "frm": {"autoAlpha": 0, "y": 26}, "to": {"autoAlpha": 1, "y": 0}, "dur": 0.5, "ease": "power3.out"},
    "blur-out-up":        {"gran": "element", "frm": {"autoAlpha": 1, "y": 0, "filter": "blur(0px)"},
                           "to": {"autoAlpha": 0, "y": -22, "filter": "blur(6px)"}, "dur": 0.5, "ease": "power2.in",
                           "then": [{"to": {"autoAlpha": 1, "y": 0, "filter": "blur(0px)"}, "dur": 0.45, "ease": "power2.out", "delay": 0.85}]},
    "kinetic-center-build":{"gran": "element", "frm": {"autoAlpha": 0, "scale": 0.5}, "to": {"autoAlpha": 1, "scale": 1}, "dur": 0.6, "ease": "back.out(1.4)"},
    "short-slide-right":  {"gran": "element", "frm": {"autoAlpha": 0, "x": -20}, "to": {"autoAlpha": 1, "x": 0}, "dur": 0.42, "ease": "power2.out"},
    "short-slide-down":   {"gran": "element", "frm": {"autoAlpha": 0, "y": -20}, "to": {"autoAlpha": 1, "y": 0}, "dur": 0.42, "ease": "power2.out"},
    "depth-parallax-words":{"gran": "word", "frm": {"autoAlpha": 0, "y": 26, "scale": 0.85}, "to": {"autoAlpha": 1, "y": 0, "scale": 1},
                           "dur": 0.7, "ease": "power2.out", "stagger": 0.1},
    # ── per-line (applied to a whole line element) ─────────────────────────────────────
    "mask-reveal-up":     {"gran": "element", "frm": {"autoAlpha": 0, "yPercent": 60}, "to": {"autoAlpha": 1, "yPercent": 0}, "dur": 0.6, "ease": "power4.out"},
    "line-by-line-slide": {"gran": "element", "frm": {"autoAlpha": 0, "x": -42}, "to": {"autoAlpha": 1, "x": 0}, "dur": 0.52, "ease": "power3.out"},
    # ── whole element ──────────────────────────────────────────────────────────────────
    "micro-scale-fade":   {"gran": "element", "frm": {"autoAlpha": 0, "scale": 0.98}, "to": {"autoAlpha": 1, "scale": 1}, "dur": 0.5, "ease": "power2.out"},
    "shimmer-sweep":      {"gran": "element", "frm": {"autoAlpha": 0, "filter": "brightness(1.8)"}, "to": {"autoAlpha": 1, "filter": "brightness(1)"}, "dur": 0.6, "ease": "power2.out"},
    "fade-through":       {"gran": "element", "frm": {"autoAlpha": 1}, "to": {"autoAlpha": 0}, "dur": 0.26, "ease": "power1.in",
                           "then": [{"to": {"autoAlpha": 1}, "dur": 0.44, "ease": "power1.out", "delay": 0.26}]},
    "shared-axis-z":      {"gran": "element", "frm": {"autoAlpha": 0, "scale": 0.8}, "to": {"autoAlpha": 1, "scale": 1}, "dur": 0.52, "ease": "power3.out"},
    "scale-down-fade":    {"gran": "element", "frm": {"autoAlpha": 0, "scale": 1.18}, "to": {"autoAlpha": 1, "scale": 1}, "dur": 0.56, "ease": "power2.out"},
    "focus-blur-resolve": {"gran": "element", "frm": {"autoAlpha": 0, "filter": "blur(12px)", "scale": 1.04}, "to": {"autoAlpha": 1, "filter": "blur(0px)", "scale": 1}, "dur": 0.7, "ease": "power2.out"},
    "shared-axis-x":      {"gran": "element", "frm": {"autoAlpha": 0, "x": 42}, "to": {"autoAlpha": 1, "x": 0}, "dur": 0.52, "ease": "power3.out"},
    # ── preserved: the engine's original hardcoded move, nameable so a reel can pin it ──
    "rise":               {"gran": "element", "frm": {"autoAlpha": 0, "y": 26}, "to": {"autoAlpha": 1, "y": 0}, "dur": 0.3, "ease": "power2.out"},
    # "punch in": each word slams in big and snaps to size, fast (2026-10-17: "needs to punch in faster")
    "punch-in":           {"gran": "word", "frm": {"autoAlpha": 0, "scale": 1.6}, "to": {"autoAlpha": 1, "scale": 1}, "dur": 0.16, "ease": "power4.out", "stagger": 0.05},
    # "bowling drop": each word falls in from above and lands with a heavy bounce (2026-10-17)
    "drop-in":            {"gran": "word", "frm": {"autoAlpha": 0, "y": -220}, "to": {"autoAlpha": 1, "y": 0}, "dur": 0.6, "ease": "bounce.out", "stagger": 0.09},
    # lands fast, then pushes in slowly for as long as the word is on screen ("hold") - the dramatic held number
    "slow-zoom":          {"gran": "element", "frm": {"autoAlpha": 0, "scale": 0.94}, "to": {"autoAlpha": 1, "scale": 1},
                           "dur": 0.3, "ease": "power2.out",
                           "then": [{"to": {"scale": 1.16}, "dur": "hold", "ease": "sine.inOut", "delay": 0.3}]},
    # ── no-op sentinels: the builder keeps its own locked behavior for these ────────────
    "snap": _NOOP, "karaoke": _NOOP, "none": _NOOP,
}

# ── effects the CREATOR has taught, merged in as first-class citizens ───────────────
# A spec above is just a dict, so an effect she names is the same kind of thing as a shipped one — it
# resolves, renders and appears in CATALOG identically. She does not author one from scratch: `teach()`
# DERIVES it from an effect that already works and overrides a few fields ("same as spring-scale-in but
# faster, and per word"), which is the difference between naming a look and hand-writing GSAP.
#
# Lives in creative-vault/user-effects.json — protected by the updater, never shipped, like her style pack.
# Every value is validated before it can reach the timeline: these strings are emitted INTO JavaScript, so
# a stray quote would produce a broken composition rather than a bad-looking one.
import os as _os, json as _json, sys as _sys


def _say(msg):
    """print() that can never kill an import: builders import this module before their own UTF-8 console
    guard runs, and a Windows cp1252 console cannot encode a status symbol. There the glyph shows as "?"."""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(_sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"))


USER_EFFECTS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             "creative-vault", "user-effects.json")
# Where a damaged copy of that file is kept. `_local/` never ships and an update never touches it; a copy
# left next to the original in creative-vault/ would ride along in the next bundle built from this folder.
DAMAGED_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "_local")


def _shown(path):
    """A path as she would look for it: relative to the engine folder when it is inside it."""
    try:
        rel = _os.path.relpath(path, _os.path.dirname(DAMAGED_DIR))
    except ValueError:              # Windows: a path on another drive has no relative form
        return path
    return path if rel.startswith("..") else rel


_GRAN = ("element", "char", "word")
_FROM = ("center", "edges", "start", "end", "random")
_TWEEN_KEYS = ("autoAlpha", "opacity", "x", "y", "xPercent", "yPercent", "scale", "scaleX", "scaleY",
               "rotation", "filter", "color", "backgroundColor", "letterSpacing", "skewX", "skewY")


class EffectError(Exception):
    """Raised by teach() only. The message is what the creator sees."""


def _safe_scalar(v, what):
    """A value that can be written into JS source without breaking it."""
    if isinstance(v, bool) or isinstance(v, (int, float)):
        return v
    v = str(v)
    if any(c in v for c in '"\\\n\r') or len(v) > 80:
        raise EffectError(f"{what}: {v!r} has characters that cannot go into an animation.")
    return v


def _safe_tween(d, what):
    if not isinstance(d, dict) or not d:
        raise EffectError(f"{what} must be a set of properties, e.g. {{'autoAlpha': 0, 'y': 20}}.")
    out = {}
    for k, v in d.items():
        if k not in _TWEEN_KEYS:
            raise EffectError(f"{what}: '{k}' is not a property an effect can animate. "
                              f"Try one of: {', '.join(_TWEEN_KEYS[:8])}…")
        out[k] = _safe_scalar(v, f"{what}.{k}")
    return out


def _validate(name, spec):
    if not isinstance(name, str) or not name.strip() or len(name) > 48:
        raise EffectError("an effect needs a short name.")
    if name in E and name not in _user_names():
        raise EffectError(f"'{name}' is one of the engine's own effects. Pick another name so both stay "
                          f"available.")
    if spec.get("gran") not in _GRAN:
        raise EffectError(f"'{name}': it has to animate by {' / '.join(_GRAN)}.")
    out = {"gran": spec["gran"],
           "frm": _safe_tween(spec.get("frm"), "the starting state"),
           "to": _safe_tween(spec.get("to"), "the resting state")}
    try:
        out["dur"] = float(spec.get("dur", 0.5))
    except (TypeError, ValueError):
        raise EffectError(f"'{name}': the duration has to be a number of seconds.")
    if not 0.001 <= out["dur"] <= 4.0:
        raise EffectError(f"'{name}': {out['dur']}s is outside what reads on screen (0.001–4s).")
    ease = str(spec.get("ease", "power2.out"))
    if not all(c.isalnum() or c in "._()+-, " for c in ease) or len(ease) > 40:
        raise EffectError(f"'{name}': {ease!r} is not an easing name.")
    out["ease"] = ease
    if spec.get("mask"):
        out["mask"] = True
    if "stagger" in spec:
        try:
            st = float(spec["stagger"])
        except (TypeError, ValueError):
            raise EffectError(f"'{name}': the stagger has to be a number of seconds.")
        if not 0 <= st <= 1.0:
            raise EffectError(f"'{name}': a {st}s stagger would run past the shot (0–1s).")
        out["stagger"] = st
    if spec.get("stagger_from"):
        if spec["stagger_from"] not in _FROM:
            raise EffectError(f"'{name}': stagger_from must be one of {', '.join(_FROM)}.")
        out["stagger_from"] = spec["stagger_from"]
    steps = spec.get("then") or []
    if steps:
        if not isinstance(steps, list) or len(steps) > 4:
            raise EffectError(f"'{name}': an effect can have at most 4 follow-up moves.")
        out["then"] = []
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                raise EffectError(f"'{name}': follow-up {i + 1} is not a move.")
            out["then"].append({"to": _safe_tween(st.get("to"), f"follow-up {i + 1}"),
                                "dur": "hold" if st.get("dur") == "hold" else float(st.get("dur", 0.4)),
                                "ease": str(st.get("ease", "power2.out")),
                                "delay": float(st.get("delay", 0.0))})
    return out


def _read_user():
    try:
        with open(USER_EFFECTS, encoding="utf-8") as fh:
            data = _json.load(fh)
    except (OSError, ValueError):
        return {}
    eff = data.get("effects") if isinstance(data, dict) else None
    return eff if isinstance(eff, dict) else {}


def _user_names():
    return set(_read_user())


def _user_damaged():
    """True when her effects file EXISTS but cannot be read: cut off mid-write, hand-edited into invalid
    JSON, or the wrong shape. _read_user() returns {} for that, the same as for no file at all, and the next
    teach() used to save its one new effect over the top of every effect she had named before it."""
    if not _os.path.exists(USER_EFFECTS):
        return False
    try:
        with open(USER_EFFECTS, encoding="utf-8") as fh:
            data = _json.load(fh)
    except (OSError, ValueError):
        return True
    return not (isinstance(data, dict) and isinstance(data.get("effects", {}), dict))


def _set_aside():
    """Move a damaged effects file to DAMAGED_DIR (never over an earlier one) and say where. Returns the new
    path. Raises EffectError, before anything is written, if it cannot be moved."""
    import time
    _os.makedirs(DAMAGED_DIR, exist_ok=True)
    base = _os.path.join(DAMAGED_DIR, f"{_os.path.basename(USER_EFFECTS)}.damaged-{time.strftime('%Y%m%d-%H%M%S')}")
    dest, n = base, 2
    while _os.path.exists(dest):
        dest, n = f"{base}-{n}", n + 1
    try:
        _os.replace(USER_EFFECTS, dest)
    except OSError as exc:
        raise EffectError(f"your saved text animations file ({_shown(USER_EFFECTS)}) is damaged and could not be "
                          f"moved aside ({exc}), so nothing was saved and nothing in it was changed.")
    _say(f"  ⚠ your saved text animations file ({_shown(USER_EFFECTS)}) was damaged and could not be read, so the "
         f"effects you named before could not load. It is kept, unchanged, at {_shown(dest)}, and a fresh one "
         f"starts now. Your earlier effect names and settings are in that copy.")
    return dest


def _load_user():
    """Merge her effects into E. A broken one is REPORTED and skipped — never silently dropped (an effect
    that vanishes without a word looks like the engine ignoring her) and never fatal."""
    if _user_damaged():
        _say(f"  ⚠ your saved text animations file ({_shown(USER_EFFECTS)}) is damaged and cannot be read, so "
             f"the effects you named are not available right now; anything that asks for one gets a shipped "
             f"effect instead. Nothing in the file was changed. The next effect you name moves it aside, "
             f"kept as it is, and starts a fresh one.")
        return
    for name, spec in _read_user().items():
        try:
            E[name] = _validate(name, spec if isinstance(spec, dict) else {})
        except (EffectError, TypeError, ValueError) as exc:
            print(f"  ⚠ your effect {name!r} could not be loaded: {exc}")


def teach(name, base="spring-scale-in", **overrides):
    """Name a new effect, DERIVED from one that already works. Returns the stored spec.

    `teach("the snap", base="spring-scale-in", dur=0.28, gran="word", stagger=0.06)` is the whole idea:
    she points at a look the engine can already produce and says what to call it and what to change."""
    if base not in E or E[base].get("noop"):
        raise EffectError(f"there is no effect called {base!r} to build on.")
    spec = {k: (dict(v) if isinstance(v, dict) else v) for k, v in E[base].items()}
    spec.pop("noop", None)
    spec.update(overrides)
    valid = _validate(name, spec)
    if _user_damaged():     # a damaged file is moved aside, never written over
        _set_aside()
    saved = _read_user()
    saved[name] = valid
    _os.makedirs(_os.path.dirname(USER_EFFECTS), exist_ok=True)
    tmp = USER_EFFECTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"_doc": "Text animations you named. Built from the engine's own effects, so "
                                      "they work everywhere the shipped ones do. Protected: an engine "
                                      "update never touches this file.",
                              "effects": saved}, indent=2, ensure_ascii=False) + "\n")
    _os.replace(tmp, USER_EFFECTS)
    E[name] = valid
    if name not in CATALOG:
        CATALOG.append(name)
    return valid


def forget(name):
    """Drop one of her effects. Returns True if it was there. Shipped effects are never removable."""
    saved = _read_user()
    if name not in saved:
        return False
    del saved[name]
    with open(USER_EFFECTS, "w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"effects": saved}, indent=2, ensure_ascii=False) + "\n")
    E.pop(name, None)
    if name in CATALOG:
        CATALOG.remove(name)
    return True


def mine():
    """The names SHE taught, for the library wall and `/learn list`."""
    return sorted(_read_user())


_load_user()

# ordered ids for tooling / the Animation format menu (excludes the no-op sentinels)
CATALOG = [k for k in E if not E[k].get("noop")]

CSS = (".tfx{display:inline-block;font-style:normal;will-change:transform,opacity,filter;}"
       ".tfxm{display:inline-block;overflow:hidden;vertical-align:top;font-style:normal;}"
       ".tfxm>.tfx{display:block;}")


def _spec(effect):
    return E.get(effect) or E["rise"]


def _jsval(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, dict):
        return _obj(v)
    if isinstance(v, (int, float)):
        return repr(v)
    return '"%s"' % v


def _obj(d):
    return "{" + ",".join("%s:%s" % (k, _jsval(v)) for k, v in d.items()) + "}"


def resolve(caption_plan, role):
    """Effect id for a role, in the order the creator's control runs:

        THIS reel's plan  ->  what she has TAUGHT  ->  the shipped default

    A per-reel instruction always wins, because it is what she is asking for right now; a taught
    preference sits under it and above the default, so "I always want the hook to do that" only has to be
    said once."""
    eff = (caption_plan.get("effects") or {}).get(role) if caption_plan else None
    if eff:
        return eff
    try:
        import learned                    # imported here: `learned` reads this module for its own validation
        taught = learned.get("effects." + role)
        if taught and taught in E:
            return taught
    except Exception:
        pass
    return DEFAULTS.get(role, "rise")


def intro_sel(sel, effect, at, dur=None, stagger=None, hold=None):
    """GSAP lines applying `effect` to CSS selector `sel` (a whole element, or many
    with `stagger`), starting at absolute time `at`. Returns "" for no-op effects.
    `hold` = seconds the element stays on screen: a follow-up step whose dur is "hold"
    (slow-zoom) runs for the rest of that time, so it moves until the moment it leaves."""
    e = _spec(effect)
    if e.get("noop"):
        return ""
    frm = dict(e["frm"])
    to = dict(e["to"])
    to["duration"] = e["dur"] if dur is None else dur
    to["ease"] = e["ease"]
    if stagger is not None:
        to["stagger"] = stagger
    elif e.get("stagger_from"):
        to["stagger"] = {"each": e.get("stagger", 0.03), "from": e["stagger_from"]}
    # fromTo, not set-at-0 + to: a zero-duration tl.set at position 0 does NOT render while the playhead
    # sits exactly at 0, so frame 0 showed the un-hidden state (hyperframes check: gsap_timeline_set_initial_hide,
    # and the one-frame flash on the most-watched frame of a short reel). fromTo defines BOTH ends, is
    # seek-safe, and renders the hidden 'from' state at frame 0. (HyperFrames-preferred over set+to / from.)
    js = 'tl.fromTo("%s",%s,%s,%.2f);' % (sel, _obj(frm), _obj(to), at)
    for step in e.get("then", []):
        sv = dict(step["to"])
        sv["duration"] = (max(0.3, hold - step["delay"]) if hold else 1.5) if step["dur"] == "hold" else step["dur"]
        sv["ease"] = step["ease"]
        js += 'tl.to("%s",%s,%.2f);' % (sel, _obj(sv), at + step["delay"])
    return js


def _split_html(text, gran, mask, esc):
    if gran == "word":
        return " ".join('<i class="tfx">%s</i>' % esc(p) for p in text.split(" "))
    # each letter is its own box, so each WORD's letters ride in one unbreakable box: a long line wraps between
    # words, never inside one ("THI / S HAPPENED")
    out = []
    for word in text.split(" "):
        letters = "".join(('<i class="tfxm"><i class="tfx">%s</i></i>' if mask else '<i class="tfx">%s</i>') % esc(ch)
                          for ch in word)
        out.append('<span class="tfxw" style="display:inline-block;white-space:nowrap">%s</span>' % letters if word else "")
    return " ".join(out)


def render(elid, text, effect, at, esc=None, dur=None, hold=None):
    """(inner_html, gsap_lines) for element id `elid` playing `effect` on `text`.
    Whole-element effects return the plain (escaped) text; char/word effects split
    the text into <i class="tfx"> units and stagger over them. Requires CSS in the
    composition's <style>. `esc` = the caller's HTML-escaper (default: identity)."""
    if esc is None:
        esc = lambda s: s
    e = _spec(effect)
    if e.get("noop"):
        return esc(text), ""
    if e["gran"] == "element":
        return esc(text), intro_sel("#%s" % elid, effect, at, dur=dur, hold=hold)
    inner = _split_html(text, e["gran"], e.get("mask", False), esc)
    if e.get("stagger_from"):
        stag = {"each": e.get("stagger", 0.03), "from": e["stagger_from"]}
    else:
        stag = e.get("stagger", 0.03)
    return inner, intro_sel("#%s .tfx" % elid, effect, at, dur=dur, stagger=stag, hold=hold)
