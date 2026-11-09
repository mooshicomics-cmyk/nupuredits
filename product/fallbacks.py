#!/usr/bin/env python3
"""fallbacks.py — never a dead end: the shared half of every step's backup route.

When a step's usual path will not work, the step takes the route that does, finishes her edit, and leaves one
line here so the cause can still be fixed through /report-a-problem (scripts/collect-report.sh attaches the
log under "Backup routes the engine took to finish an edit"). Only "nothing can run at all" stops, and then it
points at /report-a-problem. Her own Ctrl-C stays a stop. A safety gate (CapCut must be quit, never overwrite
an opened draft, the subject guard, reel_gate's checks) is never a dead end and is never routed around.

Two records, both in _local/ (never shipped, kept by every update):
  _local/fallbacks.log   one line per switch: "<UTC time>  <step>: <what failed>; <what it did instead>"
                         (the same line word-timings.sh's note_fallback writes)
  _local/pivots.json     what THIS computer has learned works, so later reels go straight there instead of
                         failing first every time: {"<key>": {"value": ..., "why": "...", "at": "..."}}

    from fallbacks import note, remember, remembered, forget
    note("verify-cut", "the WhisperX venv would not load faster-whisper; listened with the faster-whisper venv")
    remember("verify-cut.venv", py, why="the first venv would not import faster_whisper")
    remembered("verify-cut.venv")   # -> the value, or None

Shell scripts use scripts/_fallbacks.sh (note_fallback / remember_pivot / remembered_pivot), which writes the
same two files. Command line, for those scripts and for a quick look:
    python3 product/fallbacks.py note <step> <message>
    python3 product/fallbacks.py remember <key> <value> [why]
    python3 product/fallbacks.py get <key>          # prints the value, exit 1 when none
    python3 product/fallbacks.py forget <key>
    python3 product/fallbacks.py list
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _local_dir():
    # REELS_ENGINE_LOCAL lets a test point both records at a scratch folder; nothing else sets it.
    return os.environ.get("REELS_ENGINE_LOCAL") or os.path.join(ROOT, "_local")


def log_path():
    return os.path.join(_local_dir(), "fallbacks.log")


def pivots_path():
    return os.path.join(_local_dir(), "pivots.json")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def note(step, message):
    """One line in _local/fallbacks.log. Never raises: a log that cannot be written must not stop her edit."""
    try:
        os.makedirs(_local_dir(), exist_ok=True)
        line = " ".join(str(message).split())   # one line, always
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"{_now()}  {step}: {line}\n")
    except Exception:
        pass


def _load():
    try:
        with open(pivots_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}   # missing or damaged: nothing learned yet, and the step simply tries its usual path


def _save(data):
    try:
        os.makedirs(_local_dir(), exist_ok=True)
        tmp = pivots_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, pivots_path())
    except Exception:
        pass


def remember(key, value=True, why=""):
    """Marks this computer: `key` works by `value` here. Later runs read it with remembered()."""
    data = _load()
    data[key] = {"value": value, "why": why, "at": _now()}
    _save(data)


def remembered(key, default=None):
    entry = _load().get(key)
    return entry.get("value", default) if isinstance(entry, dict) else default


def forget(key):
    data = _load()
    if data.pop(key, None) is not None:
        _save(data)


def main(argv):
    if len(argv) >= 3 and argv[0] == "note":
        note(argv[1], " ".join(argv[2:]))
        return 0
    if len(argv) >= 3 and argv[0] == "remember":
        remember(argv[1], argv[2], " ".join(argv[3:]))
        return 0
    if len(argv) == 2 and argv[0] == "get":
        v = remembered(argv[1])
        if v is None:
            return 1
        print(v)
        return 0
    if len(argv) == 2 and argv[0] == "forget":
        forget(argv[1])
        return 0
    if argv[:1] == ["list"]:
        for k, e in sorted(_load().items()):
            print(f"{k} = {e.get('value')!r}  ({e.get('why', '')}, {e.get('at', '')})")
        return 0
    print(__doc__.split("Command line")[1] if "Command line" in __doc__ else __doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
