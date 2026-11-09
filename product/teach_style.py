#!/usr/bin/env python3
"""teach_style.py — "Teach my style from this reel": at the end of every reel, the notes she gave become a
checklist of rules for the NEXT reel, and she ticks the ones to keep.

A note she gives on a reel ("captions a bit higher", "fewer sound effects", "no music on these") fixes THAT reel.
Whether it should also be how every reel comes out is a different question, and only she can answer it. Waiting
for her to say "remember that" meant most of them were never asked: she fixed the same thing reel after reel.

So at the end of every workflow (the CapCut handoff or the final, right before the hashtag line), Claude:

  1. runs `teach_style.py offer <job>`: exit 0 and her notes from this reel when there is something to teach;
     exit 1 and NOTHING printed when there isn't (no notes, already asked on this reel, or she switched it off).
  2. turns the notes into short rules in her words: the ones that would hold on her next reel.
     A one-off ("move THIS line 40 px lower", "this card is wrong") is left out; the evidence says what it was.
  3. shows them in ONE question box of up to four pick-many sets she cycles through (her rules, more than one set
     when there are more than four; her looks kept for this reel only, `lookbook.py one-offs`, to keep for every
     reel), each line saying where it would be kept.
  4. saves each ticked rule with `keep`, then runs `done` (always, even when she ticked none), so she is asked
     once per reel.

Where a ticked rule is kept (`keep`) — said honestly on each checklist line:
  * a learnable value (`--field`, see `python3 product/learned.py fields`) -> `_local/learned.json`, which the
    builders apply on every build, AND a bullet in brand-kit.md Part C. Both halves, the `learn` skill's rule.
  * a sound rule ("never a whoosh") -> `favorites.py rule` is its owner: run that, not this.
  * anything else creative ("fewer cards on confessional reels") -> the Part C bullet only, which Claude reads
    before planning every reel. Never call that one "applied automatically": it is read, not applied.

Where her notes come from (`collect`): her editor's notes (transcript/script-notes.json), the looks she asked
for (review/look-requests.json), looks she switched off (review/swaps.json), a music level she set by hand
(review/sound.json), and notes she gave in the chat that a skill logged with `note` (review/notes-log.json:
the beat sheet's notes by beat number, a re-cut note, a CapCut fix). Claude also has the conversation itself.

State: projects/<job>/review/taught.json (asked + what she kept), _local/teach-style.json ({"off": bool}).
`_local/` is protected by the updater and never ships.

CLI
  python3 product/teach_style.py offer <job>            exit 0 + her notes when there's something to teach, else 1
  python3 product/teach_style.py collect <job> [--json] her notes from this reel (everything, even when asked)
  python3 product/teach_style.py note <job> "<words>" [--from "beat sheet"]   log a chat note for the checklist
  python3 product/teach_style.py keep <job> "<rule in her words>" [--field F --value V] [--scope register=confessional]
  python3 product/teach_style.py done <job> [--kept N]  mark the checklist asked on this reel
  python3 product/teach_style.py --off | --on | --status
Stdlib only. A missing or unreadable file reads as empty; nothing here raises into a delivery.
"""
import json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STORE = os.path.join(ROOT, "_local", "teach-style.json")
BRAND_KIT = os.path.join(ROOT, "brand-kit.md")
SECTION = "### Learned preferences"
FOR_CLAUDE = "> _For Claude:_"
MAX_RULES = 4                      # one question box holds four options

# the plain name of a layer key in swaps.json ("h01-hook" -> "hook")
_LAYER_WORDS = (("hook", "hook"), ("thought", "thought bubble"), ("takeover", "takeover"), ("cap", "captions"),
                ("count", "count-up"), ("list", "list"), ("card", "card"), ("add-", "added look"))


def _job_dir(job):
    return job if os.path.isabs(job) else os.path.join(ROOT, "projects", job)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


# ─────────────────────────── her switch ───────────────────────────

def is_off():
    return bool(_read(STORE, {}).get("off", False))


def set_off(off):
    d = _read(STORE, {})
    d = d if isinstance(d, dict) else {}
    d["off"] = bool(off)
    _write(STORE, d)


# ─────────────────────────── her notes ───────────────────────────

def _layer_name(key):
    k = (key or "").lower()
    for frag, word in _LAYER_WORDS:
        if frag in k:
            return word
    return "look"


def collect(job):
    """Every note she gave on this reel, oldest first: [{"from", "said", "reply"?, "at"}]. Never raises."""
    jd = _job_dir(job)
    out = []

    notes = _read(os.path.join(jd, "transcript", "script-notes.json"), {})
    for n in (notes.get("notes") if isinstance(notes, dict) else None) or []:
        if isinstance(n, dict) and (n.get("text") or "").strip():
            out.append({"from": "editor note", "said": n["text"].strip(), "reply": (n.get("reply") or "").strip(),
                        "at": n.get("at", "")})

    reqs = _read(os.path.join(jd, "review", "look-requests.json"), {})
    for r in (reqs.get("requests") if isinstance(reqs, dict) else None) or []:
        if isinstance(r, dict) and (r.get("idea") or "").strip():
            out.append({"from": "look she asked for", "said": r["idea"].strip(), "at": r.get("at", "")})

    swaps = _read(os.path.join(jd, "review", "swaps.json"), {})
    for key, s in ((swaps.get("swaps") if isinstance(swaps, dict) else None) or {}).items():
        if isinstance(s, dict) and s.get("look") == "_off":
            out.append({"from": "switched off", "said": f"turned the {_layer_name(key)} off", "at": s.get("at", "")})

    sound = _read(os.path.join(jd, "review", "sound.json"), {})
    music = sound.get("music") if isinstance(sound, dict) else None
    if isinstance(music, dict) and music.get("on") and music.get("level_how") not in (None, "auto"):
        lvl = music.get("level_db")
        said = "set the music level by hand" + (f" ({lvl} dB)" if lvl is not None else "")
        out.append({"from": "sound", "said": said, "at": ""})

    log = _read(os.path.join(jd, "review", "notes-log.json"), {})
    for n in (log.get("notes") if isinstance(log, dict) else None) or []:
        if isinstance(n, dict) and (n.get("said") or "").strip():
            out.append({"from": n.get("from") or "chat note", "said": n["said"].strip(), "at": n.get("at", "")})

    out.sort(key=lambda n: n.get("at") or "")
    return out


def note(job, words, source="chat note"):
    """Log a note she gave in the chat (the beat sheet, a re-cut, a CapCut fix) so the checklist sees it."""
    words = (words or "").strip()
    if not words:
        return False
    path = os.path.join(_job_dir(job), "review", "notes-log.json")
    d = _read(path, {})
    d = d if isinstance(d, dict) else {}
    d.setdefault("notes", []).append({"from": source, "said": words[:500], "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return _write(path, d)


# ─────────────────────────── asked once per reel ───────────────────────────

def _taught_path(job):
    return os.path.join(_job_dir(job), "review", "taught.json")


def asked(job):
    return bool(_read(_taught_path(job), {}).get("asked"))


def done(job, kept=None):
    d = _read(_taught_path(job), {})
    d = d if isinstance(d, dict) else {}
    d["asked"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if kept is not None:
        d["kept_count"] = int(kept)
    return _write(_taught_path(job), d)


def should_offer(job):
    """(yes, notes). Yes only when she hasn't switched it off, this reel wasn't asked, and there are notes."""
    if is_off() or not os.path.isdir(_job_dir(job)) or asked(job):
        return False, []
    ns = collect(job)
    return bool(ns), ns


# ─────────────────────────── keeping a rule ───────────────────────────

def _bullet(rule, job, where):
    day = time.strftime("%Y-%m-%d")
    return f"- **{rule.strip().rstrip('.')}.** ({job}, {day}; taught from this reel's notes. {where})"


def add_bullet(text, kit=BRAND_KIT):
    """Append one bullet to Part C's learned list: before the For-Claude note when the kit has one, else at the
    end of the section, else at the end of the file. Append-only. Returns True when written."""
    try:
        with open(kit, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        return False
    start = next((i for i, l in enumerate(lines) if l.startswith(SECTION)), None)
    at = len(lines)
    if start is not None:
        at = next((i for i in range(start + 1, len(lines))
                   if lines[i].startswith(FOR_CLAUDE) or re.match(r"^#{1,3} ", lines[i])), len(lines))
    while at > 0 and not lines[at - 1].strip():      # sit right under the last bullet, keep the blank line after
        at -= 1
    lines[at:at] = [text]
    try:
        tmp = kit + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        os.replace(tmp, kit)
        return True
    except OSError:
        return False


def keep(job, rule, field=None, value=None, scope=None):
    """Save one ticked rule. Returns the one line to say back to her. Raises learned.LearnError (her words) on a
    value the engine can't take, before anything is written."""
    sys.path.insert(0, HERE)
    if field:
        import learned
        rec, clamp = learned.add(field, value, note=rule, scope=scope or {}, from_job=os.path.basename(_job_dir(job)))
        where = "Applied by the engine on every build" + (f" ({', '.join(f'{k} {v}' for k, v in rec['scope'].items())} only)"
                                                          if rec["scope"] else "") + "."
        said = f"Saved: {rule}. The engine applies it from your next reel." + (f" {clamp}" if clamp else "")
    else:
        where = "Claude reads it before planning each reel."
        said = f"Saved: {rule}. I'll read it before planning your next reel."
    add_bullet(_bullet(rule, os.path.basename(_job_dir(job)), where))
    d = _read(_taught_path(job), {})
    d = d if isinstance(d, dict) else {}
    d.setdefault("kept", []).append({"rule": rule, "field": field, "value": value, "scope": scope or {},
                                     "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    _write(_taught_path(job), d)
    return said


# ─────────────────────────── CLI ───────────────────────────

def _print_notes(ns):
    for n in ns:
        line = f"- [{n['from']}] {n['said']}"
        if n.get("reply"):
            line += f"  (fixed: {n['reply'][:160]})"
        print(line)


def _opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.split("CLI", 1)[1].split("Stdlib", 1)[0].rstrip())
        return 0 if len(argv) >= 2 else 2
    cmd = argv[1]
    if cmd == "--off":
        set_off(True)
        print("Okay. I won't offer to teach your style at the end of a reel. Say \"teach my style from this reel\" any time.")
        return 0
    if cmd == "--on":
        set_off(False)
        print("Okay. At the end of each reel I'll offer to keep what your notes taught me.")
        return 0
    if cmd == "--status":
        print(f"teach-my-style checklist at the end of a reel: {'off' if is_off() else 'on'}")
        return 0
    if len(argv) < 3:
        print(f"usage: teach_style.py {cmd} <job> ...")
        return 2
    job = argv[2]
    if cmd == "offer":
        yes, ns = should_offer(job)
        if not yes:
            return 1
        print(f"Her notes on this reel ({len(ns)}). Turn the ones that would hold on her NEXT reel into at most "
              f"{MAX_RULES} rules; leave one-offs out:")
        _print_notes(ns)
        print("Learnable values (applied by the builders): python3 product/learned.py fields")
        return 0
    if cmd == "collect":
        ns = collect(job)
        if "--json" in argv:
            print(json.dumps(ns, indent=2, ensure_ascii=False))
        elif ns:
            _print_notes(ns)
        else:
            print("No notes on this reel.")
        return 0
    if cmd == "note":
        words = argv[3] if len(argv) > 3 else ""
        return 0 if note(job, words, _opt(argv, "--from", "chat note")) else 1
    if cmd == "done":
        kept = _opt(argv, "--kept")
        done(job, int(kept) if kept and kept.isdigit() else None)
        return 0
    if cmd == "keep":
        rule = argv[3] if len(argv) > 3 and not argv[3].startswith("--") else ""
        if not rule:
            print("keep needs the rule, in her words.")
            return 2
        scope = {}
        for s in (_opt(argv, "--scope", "") or "").split(","):
            if "=" in s:
                k, v = s.split("=", 1)
                scope[k.strip()] = v.strip()
        try:
            print(keep(job, rule, _opt(argv, "--field"), _opt(argv, "--value"), scope))
        except Exception as e:                       # learned.LearnError carries the words she should see
            print(f"Not saved: {e}")
            return 1
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
