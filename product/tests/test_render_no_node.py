#!/usr/bin/env python3
"""test_render_no_node.py — when the check cannot run, the render gate says so and never blames the composition.

reel_render.py runs HyperFrames' check through npx. On Windows that is `cmd /c npx ...`, and `cmd` always
exists, so with Node missing (most often: installed, but Git Bash not reopened since) nothing raised: the
check came back as an ordinary exit 1 and the gate said "check found issues ... Fix the composition". The
gate now asks for npx first (npx.cmd on Windows) and says plainly that Node is missing or the terminal needs
reopening, exit 4, in the same words product/reel_gate.py uses. The same holds when npx is there but could
not start HyperFrames at all (npm prints its own "npm error code ..." and HyperFrames never gives a
verdict). A real failed check (HyperFrames' own "Check failed") is reported exactly as before.

Run:  python3 product/tests/test_render_no_node.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fails, total = [], 0

# Runs reel_render.py the way it runs on a PC: os.name == "nt", so npx_argv builds `cmd /c npx ...` and the
# Node check looks for npx.cmd. Everything is imported first, on this OS, so only the engine's own os.name
# checks take the Windows branch.
AS_WINDOWS = ("import argparse, hashlib, json, os, platform, re, runpy, shutil, subprocess, sys, tempfile, "
              "threading, time\n"
              "sys.argv = sys.argv[1:]\n"
              "os.name = 'nt'\n"
              "runpy.run_path(sys.argv[0], run_name='__main__')\n")

# Windows' cmd.exe on a PC without Node: `cmd /c npx ...` prints this and exits 1.
FAKE_CMD = ("#!/bin/sh\n"
            "[ \"$1\" = \"/c\" ] && shift\n"
            "echo \"'$1' is not recognized as an internal or external command,\"\n"
            "echo \"operable program or batch file.\"\n"
            "exit 1\n")

FAKE_NPX = r'''#!{py}
import os, sys
if os.environ.get("FAKE_NPM_FAIL"):          # npx is there, but npm could not get the package
    print("npm warn exec The following package was not found and will be installed: hyperframes@<pin>")   # check-ship §25 refuses any other literal version
    print("npm error code ENOTCACHED")
    print("npm error request to https://registry.npmjs.org/hyperframes failed: cache mode is 'only-if-cached'")
    sys.exit(1)
print("Layout")                              # HyperFrames ran and the composition really failed its check
print("  ✗ overflow: text runs off the canvas")
print("◇  Check failed")
sys.exit(1)
'''


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-300:]) if detail else ''}")


def main():
    if os.name == "nt":
        print("test_render_no_node: skipped on Windows (it simulates a PC with POSIX stand-ins)")
        return 0
    tmp = tempfile.mkdtemp(prefix="render-no-node-")
    try:
        eng = os.path.join(tmp, "engine", "product")        # a scratch copy: its records land there
        os.makedirs(eng)
        for f in os.listdir(PRODUCT):
            if f.endswith(".py"):
                shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, f))
        script = os.path.join(eng, "reel_render.py")
        comp = os.path.join(tmp, "comp")
        os.makedirs(comp)
        with open(os.path.join(comp, "index.html"), "w", encoding="utf-8") as fh:
            fh.write('<!doctype html><html><body><div id="root" data-composition-id="reel" data-start="0" '
                     'data-duration="1" data-width="1080" data-height="1920"></div></body></html>')
        out = os.path.join(tmp, "out.mov")
        winbin, empty, npxbin = (os.path.join(tmp, n) for n in ("winbin", "empty", "npxbin"))
        for d in (winbin, empty, npxbin):
            os.makedirs(d)
        for path, body in ((os.path.join(winbin, "cmd"), FAKE_CMD),
                           (os.path.join(npxbin, "npx"), FAKE_NPX.format(py=sys.executable))):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
        env = {k: v for k, v in os.environ.items() if k not in ("FAKE_NPM_FAIL", "REELS_RENDER_STALL_SECONDS")}
        # REELS_ENGINE_NODE_DIRS="": no Node in the usual install folders either (npx_run.npx_path searches them).
        env.update(PYTHONDONTWRITEBYTECODE="1", REELS_RENDER_STALL_SECONDS="0", REELS_ENGINE_NODE_DIRS="")

        def run(argv, path, **extra):
            r = subprocess.run(argv, capture_output=True, text=True, timeout=300,
                               env=dict(env, PATH=path, **extra))
            return r.returncode, r.stdout + r.stderr

        cases = [
            ("a PC without Node (cmd /c npx is not recognized)",
             [sys.executable, "-c", AS_WINDOWS, script, "render", comp, "-o", out], winbin, {}),
            ("a Mac or Linux machine without npx on PATH",
             [sys.executable, script, "render", comp, "-o", out], empty, {}),
        ]
        for name, argv, path, extra in cases:
            rc, said = run(argv, path, **extra)
            check(f"{name}: exit 4, the could-not-run code", rc == 4, (rc, said))
            check(f"{name}: says Node is missing or the terminal needs reopening",
                  "Node is not installed" in said and "open a new one" in said, said)
            check(f"{name}: does not blame the composition", "Fix the composition" not in said, said)
            check(f"{name}: no traceback", "Traceback" not in said, said)

        path = npxbin + os.pathsep + os.environ.get("PATH", "")
        rc, said = run([sys.executable, script, "render", comp, "-o", out], path, FAKE_NPM_FAIL="1")
        check("npx could not start HyperFrames: exit 4, said plainly",
              rc == 4 and "the check could not run" in said and "ENOTCACHED" in said, (rc, said))
        check("npx could not start HyperFrames: the composition is not blamed", "Fix the composition" not in said, said)
        rc, said = run([sys.executable, script, "render", comp, "-o", out], path)
        check("a real failed check still refuses as before", rc == 1 and "Fix the composition" in said, (rc, said))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_render_no_node: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_render_no_node: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
