#!/usr/bin/env python3
"""hashtag.py — the engine's community hashtag, and her "don't remind me" switch for it.

#startupmomedit is how she tags a reel she made with the engine, so the community (and the creator behind
it) can find it. People forget it, so the engine says it in two places:

  * at the end of setup, once (the `set-me-up` skill), always;
  * at the end of a workflow (the CapCut handoff, or `scripts/name-final.sh`), until she says stop.

The FIRST time it shows at the end of a workflow, Claude offers one pick-one: keep the reminder, or
"don't remind me again". On "don't remind me", `--off` is run and it never shows at a workflow end again.
She can turn it back on any time ("remind me about the hashtag again" -> `--on`).

State lives in `_local/hashtag.json` ({"shown": <times shown at a workflow end>, "off": <bool>}).
`_local/` is protected by the updater and never ships, so her choice survives updates.

CLI
  python3 product/hashtag.py            print the reminder (nothing when she turned it off), count it
  python3 product/hashtag.py --first    exit 0 when this would be the FIRST showing, else 1 (no print)
  python3 product/hashtag.py --off      don't remind her again
  python3 product/hashtag.py --on       remind her again
  python3 product/hashtag.py --status   one line: on/off and how many times it has shown
Stdlib only. A missing or unreadable state file means "on, never shown"; it never raises.
"""
import json, os, sys

HASHTAG = "#startupmomedit"
LINE = f"Posting it? Tag it {HASHTAG} so we can see it."

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
STORE = os.path.join(ROOT, "_local", "hashtag.json")


def _load():
    try:
        with open(STORE, encoding="utf-8") as f:
            d = json.load(f)
        return {"shown": int(d.get("shown", 0)), "off": bool(d.get("off", False))}
    except Exception:
        return {"shown": 0, "off": False}


def _save(d):
    try:
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        tmp = STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        os.replace(tmp, STORE)
    except Exception:
        pass


def is_off():
    return _load()["off"]


def is_first():
    d = _load()
    return not d["off"] and d["shown"] == 0


def reminder():
    """The line to say at the end of a workflow, or "" when she turned it off. Counts the showing."""
    d = _load()
    if d["off"]:
        return ""
    d["shown"] += 1
    _save(d)
    return LINE


def set_off(off):
    d = _load()
    d["off"] = bool(off)
    _save(d)


def main(argv):
    arg = argv[1] if len(argv) > 1 else ""
    if arg == "--first":
        return 0 if is_first() else 1
    if arg == "--off":
        set_off(True)
        print(f"Okay. No more {HASHTAG} reminders at the end of a reel.")
        return 0
    if arg == "--on":
        set_off(False)
        print(f"Okay. The {HASHTAG} reminder is back on.")
        return 0
    if arg == "--peek":                                        # the line, without counting a showing (the page's export)
        d = _load()
        if not d["off"]:
            print(LINE)
        return 0
    if arg == "--status":
        d = _load()
        print(f"{HASHTAG} reminder: {'off' if d['off'] else 'on'}, shown {d['shown']} time(s)")
        return 0
    if arg:
        print(__doc__.split("CLI", 1)[1].split("Stdlib", 1)[0].rstrip())
        return 2
    line = reminder()
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
