#!/usr/bin/env python3
"""edits_mode.py — the **Instagram Edits Kit** switch.

When ON, Instagram's Edits app is the user's DEFAULT output everywhere:
  * every Finish/export defaults to the Edits app (medium), from the widget, the visual editor, or the
    YouTube/horizontal editor;
  * the rough cut transcribes IN Edits (the fast "lean mode") when the app is connected, and silently falls
    back to WhisperX when it is not (or the audio is hard);
  * the engine opens Edits for her when a step needs it (product/edits_open.py).

Her choice, not the engine's out-of-the-box default: fresh installs stay on WhisperX + CapCut. Reversible at
any time. Stored in _local/edits-mode.json, which the updater protects, so it never ships and survives updates.

Trigger phrases (the edits-kit skill): "Turn on my Instagram Edits Kit" / "turn off my Instagram Edits Kit".

    python3 product/edits_mode.py on | off | status
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "_local", "edits-mode.json")


def _read():
    try:
        return json.load(open(STORE, encoding="utf-8"))
    except Exception:
        return {}


def _write(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    json.dump(d, open(STORE, "w", encoding="utf-8"), indent=1)


def is_on():
    return bool(_read().get("on"))


def on():
    d = _read()                                               # merge, so a past "don't offer" choice is kept
    d["on"] = True
    d["since"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(d)
    return True


def off():
    d = _read()
    d["on"] = False
    d["since"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(d)
    return True


def should_offer_default():
    """After a one-off export to Edits, offer to make the kit her default — UNLESS it's already on, or she has
    said no before. 'Ask me next time' changes nothing here, so the offer simply comes back on her next export."""
    d = _read()
    return not bool(d.get("on")) and d.get("offer") != "never"


def decline_offer():
    """She said no to making Edits her default: don't ask again (she can still turn the kit on by name later)."""
    d = _read()
    d["offer"] = "never"
    d["offer_since"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(d)
    return True


def status():
    d = _read()
    return {"on": bool(d.get("on")), "since": d.get("since")}


def default_route(fallback="mp4"):
    """The Finish/export default route for the current mode: 'edits' when the kit is on, else `fallback`.
    Callers pass their own normal default (the editor remembers 'capcut'/'mp4'; the widget 'capcut')."""
    return "edits" if is_on() else fallback


def transcribe_engine(fallback="whisperx"):
    """Which transcriber the rough cut should try first: 'edits' (lean mode) when the kit is on, else
    `fallback`. The caller still falls back to WhisperX when Edits isn't connected or the audio is hard."""
    return "edits" if is_on() else fallback


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = (argv[0] if argv else "status").lower()
    if cmd == "on":
        on()
        print("Instagram Edits Kit: ON — Edits is now your default output (exports go to Edits as medium; "
              "the cut transcribes in Edits when it's connected, with WhisperX as the backup).")
    elif cmd == "off":
        off()
        print("Instagram Edits Kit: OFF — back to your normal defaults (WhisperX + CapCut).")
    elif cmd in ("decline", "no-default"):
        decline_offer()
        print("Okay — I won't ask about making Edits your default again. Say \"turn on my Instagram Edits Kit\" "
              "any time you change your mind.")
    elif cmd == "should-offer":
        print("yes" if should_offer_default() else "no")
    else:
        print(json.dumps(status()))


if __name__ == "__main__":
    main()
