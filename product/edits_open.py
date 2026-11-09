#!/usr/bin/env python3
"""edits_open.py — make sure Instagram's **Edits** app is running, launching it if it isn't (macOS).

The engine opens Edits for her; she never has to remember. The MCP that drives Edits (transcription in
Edits-first mode, and the medium export) only works while the app is open, so the edits-export flow calls
this FIRST instead of reminding her. Mirrors product/capcut_installs.py --open for CapCut.

Launch only. A plain process cannot talk to the app's MCP (public MCP mode), so the caller (the edits-export
skill) still polls the app's `appState` tool until it answers before driving — this just gets the app up.

    python3 product/edits_open.py        # launch Edits if needed; prints what it did
"""
import subprocess
import sys

BUNDLE = "com.burbn.basel.mac"
APP = "Edits"


def is_running():
    """Best-effort: is Edits already up? (Only an optimisation — `open` on a running app just focuses it.)"""
    try:
        if subprocess.run(["pgrep", "-i", "-x", APP], capture_output=True, text=True).stdout.strip():
            return True
    except Exception:
        pass
    try:  # bundle-id check (macOS)
        out = subprocess.run(["lsappinfo", "info", "-only", "bundleid", BUNDLE],
                             capture_output=True, text=True, timeout=5).stdout
        return BUNDLE in out
    except Exception:
        return False


def open_app():
    if sys.platform != "darwin":
        print("  Edits is a Mac app here; open it yourself on this platform, then continue.")
        return 2
    if is_running():
        print("  Edits is already open.")
        return 0
    for cmd in (["open", "-b", BUNDLE], ["open", "-a", APP]):
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
            print("  Opening Edits…")
            return 0
        except Exception:
            continue
    print("  ⛔ Couldn't open Edits automatically. Open it yourself (it may need installing), then continue.")
    return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):   # ⛔ and … need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(open_app())
