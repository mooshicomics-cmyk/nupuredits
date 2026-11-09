#!/usr/bin/env python3
"""venv_spawn.py — the one way the engine starts the speech tools' Python (the WhisperX / faster-whisper venv)
from another Python.

Why it exists. On Windows, `python` is often the Microsoft Store Python. That Python is a packaged app, and
Windows runs it, and every program it starts, inside the package's own view of the AppData folders: writes go
to a private copy under AppData\\Local\\Packages\\<package>\\LocalCache\\, and a read sees that private copy
or the real folder (Python's own docs, "Using Python on Windows", Microsoft Store package, known issues).
Files another packaged app wrote into AppData (the Claude app from the Microsoft Store runs uv, so uv's
Python 3.11 can land in Claude's private copy) are in neither place as far as the Store Python is concerned.

A venv's Scripts\\python.exe is only a small launcher: it reads `home` from the venv's pyvenv.cfg and starts
the real python.exe there. Started from the Store Python, the launcher inherits the Store Python's view, cannot
see `home`, and stops with: No Python at "...AppData\\Roaming\\uv\\python\\cpython-3.11...\\python.exe"
(exit code 103). The same venv works from Git Bash. Starting it through bash would not help: bash started by
the Store Python is inside the same view.

What works, and what this does:
  * Whatever the parent can see is what its child sees, so the parent checks first whether pyvenv.cfg's `home`
    is visible to it. When it is not, the base python.exe is looked for where it really is (the private copy of
    another packaged app, or uv's own install folder), and that interpreter is started directly with the venv's
    site-packages added through `site.addsitedir` (which also reads the .pth files a venv relies on). That is
    the same interpreter with the same packages, without the launcher.
  * Any spawn that still ends in exit code 103 or "No Python at" is tried once more by the other route, logged
    in one line (fallbacks.note) and remembered for this computer ("windows.store-python-spawn"), so later reels
    go straight to the route that works.

    import venv_spawn
    r = venv_spawn.run(venv_python, ["script.py", "arg"], capture_output=True, text=True)
    r = venv_spawn.run(venv_python, ["-c", code, "arg"], runner=subprocess.run, timeout=900)

`runner` is the function that actually starts the process (subprocess.run by default), so a caller's tests can
stand one in. Everything else passes straight through to it.

Command line (check-setup.sh uses this, with the `python` it is asking about):
    python product/venv_spawn.py --is-store-python    # exit 0 when this interpreter is the Store Python
"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from fallbacks import note, remember, remembered, forget
except Exception:   # a copy of the engine without the shared record still starts the tools; it keeps no record
    def note(step, message): pass
    def remember(key, value=True, why=""): pass
    def remembered(key, default=None): return default
    def forget(key): pass

PIVOT = "windows.store-python-spawn"   # value "base": start the base interpreter directly on this computer
NO_PYTHON_RC = 103                     # the venv launcher's own exit code when `home` cannot be found
NO_PYTHON_TEXT = "No Python at"        # and the line it prints

# Run by the base interpreter in place of the venv launcher: put the venv's packages first, then run what the
# caller asked for exactly as `python <script>`, `python -c <code>` or `python -m <module>` would.
_BOOT = r"""
import os, runpy, site, sys
_sp = sys.argv[1]
_before = list(sys.path)
site.addsitedir(_sp)
sys.path[:] = [p for p in sys.path if p not in _before] + _before
_mode = sys.argv[2]
if _mode == "-c":
    _code = sys.argv[3]
    sys.argv = ["-c"] + sys.argv[4:]
    exec(compile(_code, "<string>", "exec"), {"__name__": "__main__", "__builtins__": __builtins__})
elif _mode == "-m":
    sys.argv = [sys.argv[3]] + sys.argv[4:]
    runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)
else:
    sys.argv = sys.argv[2:]
    sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0])))
    runpy.run_path(sys.argv[0], run_name="__main__")
"""


def is_store_python(executable=None, prefix=None):
    """Is this interpreter (or the one described) the Microsoft Store Python? Its executable sits under
    ...\\WindowsApps\\, and its install folder is named after the PythonSoftwareFoundation package."""
    exe = (sys.executable if executable is None else executable) or ""
    prefixes = [prefix] if prefix is not None else [sys.prefix, getattr(sys, "base_prefix", sys.prefix)]
    exe_l = exe.replace("/", "\\").lower()
    return "\\windowsapps\\" in exe_l or any("pythonsoftwarefoundation" in (p or "").lower() for p in prefixes)


def venv_dir(py):
    """The venv folder an interpreter path belongs to (…/Scripts/python.exe or …/bin/python)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(py)))


def pyvenv_home(venv):
    """The `home` line of the venv's pyvenv.cfg: the folder its launcher looks in for the real python."""
    try:
        with open(os.path.join(venv, "pyvenv.cfg"), encoding="utf-8") as fh:
            for line in fh:
                key, eq, value = line.partition("=")
                if eq and key.strip().lower() == "home":
                    return value.strip()
    except OSError:
        pass
    return None


def _exe_names():
    return ("python.exe",) if os.name == "nt" else ("python3", "python")


def _in_folder(folder):
    for name in _exe_names():
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return None


def _under(path, root):
    """path's location relative to root, or None when it is not inside it (case-insensitive, like Windows)."""
    if not path or not root:
        return None
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    try:
        if os.path.commonpath([a, b]) != b:
            return None
    except ValueError:   # different drives
        return None
    return os.path.relpath(a, b)


def _base_candidates(home):
    """Where the venv's base interpreter can really be, best first."""
    out = [home]
    appdata, local = os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")
    packages = os.path.join(local, "Packages") if local else None
    # A packaged app's writes to AppData land in its private copy: LocalCache\Roaming\... or LocalCache\Local\...
    for root, leaf in ((appdata, "Roaming"), (local, "Local")):
        rel = _under(home, root)
        if rel and packages:
            out += sorted(glob.glob(os.path.join(packages, "*", "LocalCache", leaf, rel)))
    # uv's own install folder, in case the venv was made from a uv Python that has since moved there
    name = os.path.basename(home.rstrip("\\/"))
    for d in (os.environ.get("UV_PYTHON_INSTALL_DIR"), appdata and os.path.join(appdata, "uv", "python")):
        if d:
            out.append(os.path.join(d, name))
    return out


def base_python(py):
    """The real, visible base interpreter of the venv `py` belongs to, or None."""
    home = pyvenv_home(venv_dir(py))
    if not home:
        return None
    for folder in _base_candidates(home):
        found = _in_folder(folder)
        if found:
            return found
    return None


def _site_packages(venv):
    for pattern in (os.path.join(venv, "Lib", "site-packages"), os.path.join(venv, "lib", "python*", "site-packages")):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def home_visible(py):
    """Can this process see the interpreter the venv's launcher will look for? Its children see the same."""
    home = pyvenv_home(venv_dir(py))
    return home is None or _in_folder(home) is not None


def base_argv(py, args):
    """[base python, -c, boot, site-packages, *args]: the venv's packages without its launcher. None when the
    base interpreter or the venv's packages cannot be found from here."""
    base, site_dir = base_python(py), _site_packages(venv_dir(py))
    if not base or not site_dir:
        return None
    return [base, "-c", _BOOT, site_dir, *args]


def _launcher_failed(r):
    if r.returncode == NO_PYTHON_RC:
        return True
    err = r.stderr if isinstance(r.stderr, str) else (r.stderr or b"").decode("utf-8", "replace")
    return NO_PYTHON_TEXT in (err or "")


def _base_env(kw):
    env = dict(kw.get("env") or os.environ)
    env.pop("PYTHONHOME", None)          # would point the base interpreter away from its own library
    env.pop("__PYVENV_LAUNCHER__", None)
    env["PYTHONNOUSERSITE"] = "1"        # a venv never reads the user's own site-packages; neither does this
    return env


def run(py, args, runner=None, step="speech tools", **kw):
    """Start the venv interpreter `py` with `args` the way that works on this computer. Returns what `runner`
    returns (a CompletedProcess). Timeouts and other errors from the runner pass straight through."""
    runner = runner or subprocess.run
    args = list(args)
    direct = [py, *args]
    learned = remembered(PIVOT) == "base"
    # Checked before the first try, not after it fails: a launcher that cannot see `home` always fails.
    store_blind = not learned and is_store_python() and not home_visible(py)
    if learned or store_blind:
        argv = base_argv(py, args)
        if argv:
            if store_blind:
                why = "the Microsoft Store Python cannot see the speech tools' own Python"
                note(step, f"{why} ({pyvenv_home(venv_dir(py))}); started its base Python directly instead")
                remember(PIVOT, "base", why)
            return runner(argv, **{**kw, "env": _base_env(kw)})
    r = runner(direct, **kw)
    if not _launcher_failed(r):
        return r
    argv = base_argv(py, args)
    if not argv:
        return r      # nothing else to try from here: the caller reports the original failure as before
    r2 = runner(argv, **{**kw, "env": _base_env(kw)})
    if not _launcher_failed(r2):
        note(step, f"the speech tools' Python would not start from here (No Python at its home, exit "
                   f"{r.returncode}); started its base Python directly instead")
        remember(PIVOT, "base", "the venv launcher could not find its home Python from this parent")
    return r2


def call(py, args, runner=None, step="speech tools", **kw):
    """run(), with the child's output going straight to the terminal; returns the exit code."""
    return run(py, args, runner=runner, step=step, **kw).returncode


if __name__ == "__main__":
    if sys.argv[1:] == ["--is-store-python"]:
        sys.exit(0 if is_store_python() else 1)
    sys.exit("usage: python product/venv_spawn.py --is-store-python")
