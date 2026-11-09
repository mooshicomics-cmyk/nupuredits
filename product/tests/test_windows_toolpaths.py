#!/usr/bin/env python3
"""Three Windows failures that a Mac can never reproduce by running the engine, pinned as tests.

All three come from one tester's PC (v1.0.56 report) and all three had the same shape: the engine
looked for a thing in a place, the thing was somewhere else, and the engine reported "not installed"
instead of "not found where I looked". A Mac passes every one of these by accident, so without a test
they silently come back on the next refactor.

  1. VERSIONED TOOL DIRECTORIES. ffmpeg installs to WinGet/Packages/<pkg>/ffmpeg-<version>-full_build/bin
     and node unzips to Programs/node/node-v<version>-win-x64. No fixed string can match either, so the
     shim has to glob. It previously checked WinGet/Links (empty on that machine) and Programs/nodejs
     (one level too shallow), and found neither tool.

  2. THE python3 DECOY WITH NO FALLBACK. Windows ships an App Execution Alias at the name `python3`
     that exists on PATH and refuses to run. On that machine `python` and `py` were also absent, so all
     three of the shim's checks failed while a working interpreter sat at ~/.local/pyenv/Scripts.

  3. open() WITHOUT AN ENCODING. Python's open() uses the locale codepage on Windows, not UTF-8, so any
     file holding a curly quote or emoji raises UnicodeDecodeError. Setting PYTHONUTF8 fixes it only for
     processes launched through a shell script that exports it, which is not how most of these run.
     The call sites are the only place the fix holds everywhere.
"""
import ast
import glob
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


def sh(script, **env):
    e = dict(os.environ)
    e.update({k: str(v) for k, v in env.items()})
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=ROOT, env=e).stdout.strip()


# ---------------------------------------------------------------- 1. versioned tool directories
print("\nthe PATH shim finds tools inside VERSIONED install directories")
with tempfile.TemporaryDirectory() as tmp:
    # The exact shapes measured on the tester's machine.
    ff = os.path.join(tmp, "Microsoft/WinGet/Packages",
                      "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin")
    nd = os.path.join(tmp, "Programs/node/node-v24.19.0-win-x64")
    os.makedirs(ff)
    os.makedirs(nd)
    os.makedirs(os.path.join(tmp, "Microsoft/WinGet/Links"))   # present but EMPTY, as it was for her

    got = sh('. scripts/_path-shim.sh; _ps_expand "$LOCALAPPDATA/Microsoft/WinGet/Packages/*FFmpeg*/*/bin"',
             LOCALAPPDATA=tmp)
    check("ffmpeg's winget Packages directory resolves", got == ff, f"got {got!r}")

    got = sh('. scripts/_path-shim.sh; _ps_expand "$LOCALAPPDATA/Programs/node/node-v*-win-x64"',
             LOCALAPPDATA=tmp)
    check("node's versioned zip directory resolves", got == nd, f"got {got!r}")

    # uv, added after the SECOND PC tester (v1.0.67). ffmpeg and node learned to glob here; uv never
    # did, so winget installed it to Packages/astral-sh.uv_<hash>/uv-x86_64-pc-windows-msvc/ and the
    # shim — still checking only Programs/uv and the empty WinGet/Links — reported it missing. Setup
    # then told her to install a tool she had just successfully installed.
    uvd = os.path.join(tmp, "Microsoft/WinGet/Packages",
                       "astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv-x86_64-pc-windows-msvc")
    os.makedirs(uvd)
    got = sh('. scripts/_path-shim.sh; _ps_candidates uv | while IFS= read -r d; do'
             ' case "$d" in *"*"*) _ps_expand "$d" ;; esac; done',
             LOCALAPPDATA=tmp)
    check("uv's winget Packages directory resolves", uvd in got.splitlines(), f"got {got!r}")

    # A pattern matching nothing must produce nothing, never the unexpanded pattern itself, which would
    # otherwise be prepended to PATH as a literal directory name containing a '*'.
    got = sh('. scripts/_path-shim.sh; _ps_expand "$LOCALAPPDATA/Programs/nothing-here-*/bin"',
             LOCALAPPDATA=tmp)
    check("a pattern that matches nothing yields nothing", got == "", f"got {got!r}")

    # stitch-cut.sh, word-timings.sh and the rest source the shim under `set -e`. A missing tool makes the shim
    # try directories that are not on this machine, and a failed [ -d ] test used to be the function's
    # return value, so the script stopped right there with no message. Only /usr/bin and /bin on PATH and
    # an empty home: several tools are missing and almost no candidate folder exists.
    r = subprocess.run(["bash", "-c", "set -euo pipefail; . scripts/_path-shim.sh; echo reached"],
                       capture_output=True, text=True, cwd=ROOT,
                       env={"HOME": tmp, "PATH": "/usr/bin:/bin"})
    check("a script under set -e keeps going when a tool is missing", r.stdout.strip() == "reached",
          f"exit {r.returncode}, stdout {r.stdout.strip()!r}")


# ---------------------------------------------------------------- 2. the python3 decoy
print("\nthe python3 shim beats the Microsoft Store decoy by finding a real interpreter on disk")
with tempfile.TemporaryDirectory() as home:
    real = sys.executable
    # A decoy that EXISTS on PATH and refuses to run, exactly like the Store alias.
    os.makedirs(os.path.join(home, "bin"))
    decoy = os.path.join(home, "bin", "python3")
    with open(decoy, "w", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\necho "Python was not found; run without arguments to install from the '
                 'Microsoft Store..." >&2\nexit 9009\n')
    os.chmod(decoy, 0o755)
    # A working interpreter at the path where hers actually lived.
    os.makedirs(os.path.join(home, ".local/pyenv/Scripts"))
    hidden = os.path.join(home, ".local/pyenv/Scripts/python.exe")
    with open(hidden, "w", encoding="utf-8") as fh:
        fh.write(f'#!/bin/sh\nexec {real} "$@"\n')
    os.chmod(hidden, 0o755)

    out = subprocess.run(
        ["bash", "-c", '. scripts/_python3-shim.sh; python3 -c "print(\'RAN\')" 2>&1 | tail -1'],
        capture_output=True, text=True, cwd=ROOT,
        env={"HOME": home, "PATH": os.path.join(home, "bin") + ":/usr/bin:/bin"},
    ).stdout.strip()
    check("a decoy python3 is replaced by the real interpreter found on disk", out == "RAN", f"got {out!r}")

# Where uv, the tool setup itself uses to install Python on Windows, really puts it. Measured on a second
# tester's machine. Before this, the engine could not find the Python its own setup had just installed.
for label, rel in (("uv's managed Python under AppData/Roaming/uv/python",
                    "AppData/Roaming/uv/python/cpython-3.12-windows-x86_64-none/python.exe"),
                   ("uv's versioned python3.12.exe in ~/.local/bin", ".local/bin/python3.12.exe")):
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, "bin"))
        decoy = os.path.join(home, "bin", "python3")
        with open(decoy, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\necho "Python was not found; run without arguments to install from the '
                     'Microsoft Store..." >&2\nexit 9009\n')
        os.chmod(decoy, 0o755)
        target = os.path.join(home, rel)
        os.makedirs(os.path.dirname(target))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
        os.chmod(target, 0o755)
        out = subprocess.run(
            ["bash", "-c", '. scripts/_python3-shim.sh; python3 -c "print(\'RAN\')" 2>&1 | tail -1'],
            capture_output=True, text=True, cwd=ROOT,
            env={"HOME": home, "PATH": os.path.join(home, "bin") + ":/usr/bin:/bin"},
        ).stdout.strip()
        check(f"the decoy is beaten when Python lives at {label}", out == "RAN", f"got {out!r}")



# ------------------------------------------- 2b. the CHECKER agrees with the ENGINE about Python
print("\ncheck-setup.sh resolves Python the same way the engine does")
# check-setup.sh only ever tried the names `python3` and `python`. The engine itself uses
# scripts/_python3-shim.sh, which additionally knows `py -3` and finds interpreters on disk. On the
# second tester's PC the two disagreed: every engine script ran Python fine while the setup checker
# printed "python3  ✗  winget install Python.Python.3.12", sending her to reinstall what she had.
# A checker that contradicts the engine is worse than no checker, so it now resolves Python identically.
with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as stub:
    # Give the PATH shim every tool it repairs, so it prepends NO directories of its own. Without this
    # a dev Mac leaks /opt/homebrew/bin (which holds a real python3) onto PATH and the case vanishes.
    for _t in ("ffmpeg", "ffprobe", "node", "npx", "npm", "uv", "git"):
        _q = os.path.join(stub, _t)
        with open(_q, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho stub\n")
        os.chmod(_q, 0o755)
    # The ordinary shell utilities the script needs — but deliberately NO python/python3, and not
    # /usr/bin wholesale, because macOS ships a /usr/bin/python3 that would satisfy the first check.
    for _t in ("uname", "dirname", "basename", "grep", "sed", "awk", "cut", "tr", "sort", "head",
               "tail", "cat", "ls", "mkdir", "rm", "chmod", "find", "sw_vers", "sysctl", "arch",
               "expr", "wc", "date", "mktemp", "touch", "cp", "mv", "printf", "test", "env"):
        _w = subprocess.run(["/bin/bash", "-c", f"command -v {_t} || true"],
                            capture_output=True, text=True).stdout.strip()
        if _w:
            try: os.symlink(_w, os.path.join(stub, _t))
            except OSError: pass
    # A working interpreter ONLY where the shim knows to look, under a name neither `python3` nor
    # `python` resolves to — the exact shape of the uv-installed Python on her machine.
    os.makedirs(os.path.join(home, ".local/bin"))
    planted = os.path.join(home, ".local/bin/python3.12.exe")
    with open(planted, "w", encoding="utf-8") as fh:
        fh.write(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    os.chmod(planted, 0o755)

    _out = subprocess.run(["/bin/bash", os.path.join(ROOT, "check-setup.sh")],
                          capture_output=True, text=True, cwd=ROOT,
                          env={"HOME": home, "PATH": stub, "TERM": "dumb"}).stdout
    _lines = [l for l in _out.splitlines() if "python3" in l and ("\u2713" in l or "\u2717" in l or "!" in l)]
    check("check-setup.sh does not call python3 missing when only the shim can find it",
          bool(_lines) and "\u2717" not in _lines[0], f"got {_lines[:1]}")

# ---------------------------------------------------------------- 3. open() always names its encoding
print("\nevery engine-authored text open() names its encoding (Windows defaults to cp1252, not UTF-8)")
# Engine-authored only. product/engine/VectCutAPI is vendored: not ours to rewrite, and a local edit
# would be reverted by its next upgrade.
FILES = sorted(set(glob.glob(os.path.join(ROOT, "product", "*.py"))
                   + glob.glob(os.path.join(ROOT, "product", "tests", "*.py"))
                   + glob.glob(os.path.join(ROOT, "workflows", "*.py"))
                   + glob.glob(os.path.join(ROOT, ".claude/skills/rough-cut/scripts", "*.py"))
                   # pull-reels and the caption preset are launched on a buyer's PC too; they were outside
                   # this check and carried four bare read_text/write_text calls.
                   + glob.glob(os.path.join(ROOT, ".claude/skills/pull-reels/scripts", "*.py"))
                   + glob.glob(os.path.join(ROOT, "presets", "*", "*.py"))
                   # scripts/ holds apply-update.py, the one file that runs on EVERY buyer's machine and is
                   # launched directly, never through a shell that sets PYTHONUTF8. It was left out of the
                   # first version of this check, and nine of its reads and writes had no encoding.
                   + glob.glob(os.path.join(ROOT, "scripts", "*.py"))
                   # seller-side; absent from the buyer bundle, where this guard also runs (check-ship §23)
                   + [p for p in [os.path.join(ROOT, "make-update.py")] if os.path.exists(p)]))
bare = []
for f in FILES:
    try:
        tree = ast.parse(open(f, encoding="utf-8").read())
    except SyntaxError:
        continue
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        if any(k.arg == "encoding" or k.arg is None for k in n.keywords):
            continue
        # pathlib's read_text()/write_text() fall back to the locale codepage exactly like open() does.
        # The first version of this check only looked for open(), so 26 of these slipped straight past it.
        if isinstance(n.func, ast.Attribute) and n.func.attr in ("read_text", "write_text"):
            bare.append(f"{os.path.relpath(f, ROOT)}:{n.lineno} .{n.func.attr}()")
            continue
        if not (isinstance(n.func, ast.Name) and n.func.id == "open"):
            continue
        mode = None
        if len(n.args) >= 2:
            mode = n.args[1].value if isinstance(n.args[1], ast.Constant) else "?"
        for k in n.keywords:
            if k.arg == "mode":
                mode = k.value.value if isinstance(k.value, ast.Constant) else "?"
        if mode == "?" or (mode and "b" in mode):
            continue                      # binary, or a mode we cannot prove is text
        bare.append(f"{os.path.relpath(f, ROOT)}:{n.lineno}")

check(f"no text-mode open(), read_text() or write_text() is missing encoding= ({len(FILES)} files scanned)", not bare)
for b in bare[:15]:
    print(f"         {b}")
if len(bare) > 15:
    print(f"         ... and {len(bare) - 15} more")


# ---------------------------------------------------------------- 4. status symbols need the console guard
print("\nevery directly-run script that prints a status symbol reconfigures stdout to UTF-8 (cp1252 consoles)")
# PYTHONUTF8 is exported by the bash wrappers and persisted by setup, but a script Claude runs DIRECTLY on a
# PC before the terminal was reopened has neither, and the first ✓/⚠/✗ it prints raises UnicodeEncodeError.
GLYPHS = re.compile("[✓✗⚠⛔✅→⏳•✔✘]")
RUNNABLE = sorted(set(FILES
                      + glob.glob(os.path.join(ROOT, ".claude/skills/broll-reels/tools", "*.py"))
                      + glob.glob(os.path.join(ROOT, ".claude/skills/capcut/scripts", "*.py"))))
unguarded = []
for f in RUNNABLE:
    if "/tests/" in f or os.path.basename(f).startswith("test_"):
        continue
    try:
        src = open(f, encoding="utf-8").read()
    except OSError:
        continue
    if not GLYPHS.search(src):
        continue
    if "__main__" not in src and "sys.argv" not in src and "argparse" not in src:
        continue                      # a library module: whoever runs it owns the console
    if 'reconfigure(encoding="utf-8"' not in src:
        unguarded.append(os.path.relpath(f, ROOT))
check(f"every glyph-printing script carries the UTF-8 console guard ({len(RUNNABLE)} files scanned)", not unguarded)
for u in unguarded[:15]:
    print(f"         {u}")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "windows tool paths hold"))
sys.exit(1 if fails else 0)
