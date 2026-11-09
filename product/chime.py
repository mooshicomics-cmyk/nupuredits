#!/usr/bin/env python3
"""chime.py — the soft sound Claude makes when it is waiting on her, and her switch for it.

Buyers lost minutes not noticing Claude was waiting: a pick-one question, a "may I?" permission prompt, or a
finished reply she had not seen. So `.claude/hooks/chime.sh` (wired in `.claude/settings.json` to the
question box and to Claude Code's "waiting for you" notifications) plays one short system sound then.
It never chimes after every reply, and two in a row within a few seconds are one chime.

She can turn it off ("turn the chime off", "stop the ding") and back on. The choice lives in
`_local/chime.json` ({"off": <bool>}). `_local/` is protected by the updater and never ships, so her
choice survives updates.

CLI
  python3 product/chime.py --status   one line: on or off
  python3 product/chime.py --off      no more chimes
  python3 product/chime.py --on       chimes back on
  python3 product/chime.py --test     play it once now (even when it is off), so she hears what it sounds like
Stdlib only. A missing or unreadable state file means "on"; it never raises.
"""
import json, os, shutil, subprocess, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
STORE = os.path.join(ROOT, "_local", "chime.json")
HOOK = os.path.join(ROOT, ".claude", "hooks", "chime.sh")


def _load():
    try:
        with open(STORE, encoding="utf-8") as f:
            d = json.load(f)
        return {"off": bool(d.get("off", False))}
    except Exception:
        return {"off": False}


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


def set_off(off):
    d = _load()
    d["off"] = bool(off)
    _save(d)


def test():
    """Play the chime once through the same hook script, so the test is the real thing. True when it ran."""
    bash = shutil.which("bash")
    if not bash or not os.path.isfile(HOOK):
        return False
    try:
        subprocess.run([bash, HOOK, "--force"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
        return True
    except Exception:
        return False


def main(argv):
    arg = argv[1] if len(argv) > 1 else "--status"
    if arg == "--off":
        set_off(True)
        print("Okay. No more chime when I'm waiting on you.")
        return 0
    if arg == "--on":
        set_off(False)
        print("Okay. I'll chime when I'm waiting on you.")
        return 0
    if arg == "--status":
        print(f"Waiting chime: {'off' if is_off() else 'on'}")
        return 0
    if arg == "--test":
        ok = test()
        note = " (it's switched off, so you'll only hear it when you test it)" if is_off() else ""
        print(f"That's the chime{note}." if ok else "The chime could not play on this computer.")
        return 0
    print(__doc__.split("CLI", 1)[1].split("Stdlib", 1)[0].rstrip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
