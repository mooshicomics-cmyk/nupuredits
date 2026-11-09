#!/usr/bin/env python3
"""pip-install.py <package> [...] -- install a Python package into THIS interpreter, whatever manages it.

WHY: when Python was installed by uv (how setup installs it on Windows), a plain `pip install` is refused:

    error: externally-managed-environment
    This Python installation is managed by uv and should not be modified.

A tester hit that twice in one setup, once for Pillow and once for requests, and had to be walked through
the retry by hand each time.

The obvious fix, always passing --break-system-packages, is wrong: pip only learned that flag in 23.0, so on
an older pip it fails with "no such option" and breaks an install that would otherwise have worked. But
PEP 668 enforcement, the thing that produces the refusal above, arrived in that SAME pip release. So a pip
that refuses for this reason always understands the flag. Retrying with it ONLY after seeing that refusal
is therefore safe on every pip version, old or new.

It is a Python script rather than a shell one-liner so it pastes the same way into PowerShell 5.1, cmd, and
Git Bash. PowerShell 5.1, the default on Windows 11 Home, has no `||`.
"""
import subprocess
import sys

REFUSAL = "externally-managed-environment"


def install(packages, run=subprocess.run):
    base = [sys.executable, "-m", "pip", "install", *packages]
    first = run(base, capture_output=True, text=True)
    if first.returncode == 0:
        sys.stdout.write(first.stdout)
        return 0
    if REFUSAL not in (first.stdout + first.stderr):
        # A different failure (no network, typo in the name). Show it exactly as pip reported it.
        sys.stdout.write(first.stdout)
        sys.stderr.write(first.stderr)
        return first.returncode
    print("This Python is managed by another tool, so installing with its permission instead...")
    second = run(base + ["--break-system-packages"], capture_output=True, text=True)
    sys.stdout.write(second.stdout)
    if second.returncode != 0:
        sys.stderr.write(second.stderr)
    return second.returncode


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/pip-install.py <package> [...]")
    sys.exit(install(sys.argv[1:]))
