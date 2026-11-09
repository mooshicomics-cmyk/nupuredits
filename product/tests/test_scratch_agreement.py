#!/usr/bin/env python3
"""The cut pipeline hands work between Python and shell through ONE scratch folder:
word-timings.sh writes it, transcript-cut.py drops cuts.json into it, stitch-cut.sh reads it back.

If the two sides compute that folder differently the handoff dies with "missing .../cuts.json",
and it dies SILENTLY on the happy path because each half looks correct on its own. That is exactly
what happened when the Windows pass moved the Python half to tempfile.gettempdir() and left the
shell half on a hardcoded /tmp: on macOS gettempdir() is /var/folders/.../T, not /tmp, so the two
halves stopped pointing at the same place on the SUPPORTED platform.

This test pins them together."""
import os, re, sys, subprocess, tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SH = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


py_root = os.path.join(tempfile.gettempdir(), "reels-editing-engine")
# Ask the REAL function the scripts call, not a copy of the formula. A test that re-implements the
# thing it is testing passes forever while the shipped code drifts underneath it, which is exactly how
# this bug survived the Windows pass.
_shim = os.path.join(ROOT, "scripts", "_python3-shim.sh")
sh_root = subprocess.run(["bash", "-c", f'. "{_shim}"; scratch_root'],
                         capture_output=True, text=True).stdout.strip()
print(f"python computes : {py_root}")
print(f"shell  computes : {sh_root}\n")
check("python and shell resolve the SAME scratch root",
      os.path.normpath(py_root) == os.path.normpath(sh_root))

print("\nno shell script may hardcode /tmp for the scratch root")
for name in ("stitch-cut.sh", "word-timings.sh", "respell.sh"):
    p = os.path.join(SH, name)
    if not os.path.exists(p):
        continue
    body = open(p, encoding="utf-8").read()
    hard = re.findall(r'(?<!\{TMPDIR:-)/tmp/reels-editing-engine', body)
    # comments that merely describe the path are fine; assignments are not
    assigns = re.findall(r'^\s*\w+="(?:/tmp|\$\{TMPDIR:-/tmp\})/reels-editing-engine', body, re.M)
    check(f"{name} has no hardcoded scratch assignment", not assigns)

print("\npython halves use gettempdir, never a literal /tmp")
for rel in ("transcript-cut.py", "trim-restarts.py"):
    p = os.path.join(SH, rel)
    if not os.path.exists(p):
        continue
    body = open(p, encoding="utf-8").read()
    uses_literal = re.search(r'["\']\/tmp\/reels-editing-engine', body)
    check(f"{rel} has no literal /tmp scratch path", not uses_literal)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "scratch agreement holds"))
sys.exit(1 if fails else 0)
