#!/usr/bin/env python3
"""graphics_python.py — the Python the engine draws with: one that has Pillow.

Every look, caption page and card is drawn by a script that imports Pillow, and each one is started with the
interpreter that started its parent. So whichever `python3` came first on her PATH decided whether anything could
be drawn at all. On a Mac with Apple's Command Line Tools that can be /usr/bin/python3 (3.9, no Pillow), ahead of
the Python setup installed into ~/.local/bin: the visual editor's server came up on it and every look in the
Lookbook failed with "No module named 'PIL'" (a buyer, 2026-10-24). Setup had done its job; the engine just never
asked which Python it was on.

    import graphics_python
    py = graphics_python.python()          # sys.executable when it has Pillow, else the first one on disk that does
    graphics_python.reexec_if_needed()     # a long-lived process (the editor's server) moves onto that Python

Report-only, apart from the re-exec. Never runs Apple's placeholder /usr/bin/python3 (it opens an install
dialog on a Mac without the developer tools): /usr/bin is not searched, and the current interpreter is asked
in-process.

Run: python3 product/graphics_python.py      prints the Python it would draw with, or says none has Pillow
"""
import functools
import glob
import importlib.util
import os
import subprocess
import sys

# Said in place of a raw ModuleNotFoundError, wherever no Python on this computer has Pillow.
NO_PIL_MESSAGE = ("The engine's picture tools (Pillow) are not on this computer's Python, so looks can't be drawn "
                  "yet. Type \"set me up\" in the chat and Claude adds them; your reel is untouched.")

_REEXEC_FLAG = "REELS_ENGINE_GRAPHICS_REEXEC"   # set on the re-exec, so it can never loop


def here_has_pil():
    try:
        return importlib.util.find_spec("PIL") is not None
    except Exception:
        return False


def _candidates():
    """Where a real Python with the engine's packages lives, in the order setup puts them there (the same places
    scripts/_python3-shim.sh searches). /usr/bin/python3 is deliberately absent."""
    home = os.path.expanduser("~")
    root = os.environ.get("_P3_SYS_ROOT", "")            # tests only: a stand-in for the system-wide folders
    pats = [os.path.join(home, ".local", "bin", "python3"),
            os.path.join(home, ".local", "share", "uv", "python", "cpython-3.1*", "bin", "python3"),
            root + "/opt/homebrew/bin/python3",
            root + "/usr/local/bin/python3",
            root + "/Library/Frameworks/Python.framework/Versions/3.*/bin/python3"]
    if os.name == "nt":
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        pats += [os.path.join(appdata, "uv", "python", "cpython-*", "python.exe"),
                 os.path.join(home, ".local", "bin", "python3.1*.exe"),
                 os.path.join(local, "Programs", "Python", "Python3*", "python.exe")]
    seen = set()
    for pat in pats:
        for hit in sorted(glob.glob(pat), reverse=True):   # newest version first
            real = os.path.realpath(hit)
            if real in seen or not os.access(hit, os.X_OK):
                continue
            seen.add(real)
            yield hit


def has_pil(py):
    try:
        return subprocess.run([py, "-c", "import PIL"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, timeout=20).returncode == 0
    except Exception:
        return False


@functools.lru_cache(maxsize=1)
def find_other():
    """Another Python on this computer that has Pillow, or None."""
    me = os.path.realpath(sys.executable or "")
    for py in _candidates():
        if os.path.realpath(py) != me and has_pil(py):
            return py
    return None


def python():
    """The interpreter to start a drawing script with: this one when it has Pillow, else one that does, else this
    one (the script then fails, and the caller says NO_PIL_MESSAGE)."""
    if here_has_pil():
        return sys.executable
    return find_other() or sys.executable


def reexec_if_needed(argv=None):
    """Move this process onto a Python that has Pillow, when this one has none and another does. Returns only when
    nothing changed (this Python has Pillow, none does, or this is already the re-exec)."""
    if here_has_pil() or os.environ.get(_REEXEC_FLAG):
        return
    py = find_other()
    if not py:
        return
    argv = list(sys.argv if argv is None else argv)
    os.environ[_REEXEC_FLAG] = "1"
    if os.name == "nt":                                   # Windows' execv does not quote paths with spaces
        sys.exit(subprocess.call([py] + argv))
    os.execv(py, [py] + argv)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    if here_has_pil():
        print(f"✓ drawing with {sys.executable} (has Pillow)")
    else:
        other = find_other()
        print(f"→ {sys.executable} has no Pillow; the engine draws with {other}" if other else NO_PIL_MESSAGE)
