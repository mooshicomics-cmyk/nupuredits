#!/usr/bin/env python3
"""The PATH shim never overwrites a variable of the script that sources it.

scripts/_path-shim.sh is sourced by collect-report.sh, stitch-cut.sh, word-timings.sh and others. Its helpers
used to keep their scratch values in short global names (_d, _p, _e, _m, _t), and collect-report.sh keeps the
engine root in _d: on a machine where one tool was missing from PATH, the problem report was saved inside
/usr/local/bin instead of the engine folder. Every helper's scratch name is now local to it.

Run:  python3 product/tests/test_path_shim_scope.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SHIM = os.path.join(ROOT, "scripts", "_path-shim.sh")
BASH = shutil.which("bash")
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


if not BASH:
    print("no bash on this machine; nothing to check")
    sys.exit(0)

NAMES = ["_d", "_p", "_e", "_m", "_t"]
script = "\n".join([
    *[f'{n}="mine{n}"' for n in NAMES],
    "PATH=/usr/bin:/bin",                         # tools missing, as on a fresh install before a terminal reopen
    f'. "{SHIM}"',
    '_ps_add "$HOME"; _path_shim_missing >/dev/null; _ps_expand "$HOME" >/dev/null',
    "echo " + " ".join(f'"${{{n}}}"' for n in NAMES),
])
r = subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8")
got = r.stdout.strip().split(" ")
print("\nsourcing the shim and calling every helper leaves the caller's variables alone")
for n, v in zip(NAMES, got + [""] * len(NAMES)):
    check(f"{n} is still the caller's", v == f"mine{n}", repr(v))

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "path shim: the scripts that source it keep their own variables"))
sys.exit(1 if fails else 0)
