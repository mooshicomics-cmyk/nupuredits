#!/usr/bin/env python3
"""On Windows, WhisperX's own checkpoint loads under a torch newer than the pin; a Mac runs exactly as before.

Buyer reports (launch week, 2026-10-19): torch 2.6 and later load checkpoints "weights only" by default, and a PC
whose torch had moved past the 2.8 pin refused WhisperX's voice-detection checkpoint ("Weights only load failed").
WhisperX exited 1 and every reel went to faster-whisper. Each buyer's Claude set TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD
by hand. Now word-timings.sh sets it for the WhisperX run only, on Windows only (the models come from known
sources), and vo-cutgrid.py (the voiceover's WhisperX pass) does the same.

  1. Windows (Git Bash): the WhisperX process sees TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
  2. after the run the shell is back as it was: unset when it was unset, her own value when she had set one
  3. WhisperX's exit code still reaches the caller (the faster-whisper fallback reads it)
  4. a Mac: the WhisperX process never sees the variable (the Mac path is unchanged)
  5. vo-cutgrid.py passes it on Windows only

The function is lifted out of word-timings.sh and run under the system bash (3.2 on a Mac) with a stand-in for
the venv's Python, so nothing is installed or transcribed.

Run:  python3 product/tests/test_whisperx_weights_only.py
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
VO = os.path.join(ROOT, "product", "vo-cutgrid.py")
fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


with open(WT, encoding="utf-8") as fh:
    src = fh.read()
m = re.search(r"^listen_whisperx\(\) \{\n.*?\nPY\n.*?^\}\n", src, re.S | re.M)
check("listen_whisperx is found in word-timings.sh", m is not None)
BASH = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")

if m and BASH:
    tmp = tempfile.mkdtemp()
    try:
        seen = os.path.join(tmp, "seen")
        fake = os.path.join(tmp, "python")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\ncat >/dev/null\n"
                     f"printf '%s' \"${{TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD-unset}}\" > '{seen}'\n"
                     "exit \"${FAKE_RC:-0}\"\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        fn = os.path.join(tmp, "fn.sh")
        with open(fn, "w", encoding="utf-8") as fh:
            fh.write(m.group(0))

        def run(windows, before=None, rc=0):
            pre = "" if before is None else f"export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='{before}'\n"
            script = (f"set -euo pipefail\nWINDOWS_SHELL={1 if windows else 0}\nPYBIN='{fake}'\n"
                      f"SCRATCH_WORDS='{tmp}/words.json'\nCLIPS=('{tmp}/a.mov')\n{pre}. '{fn}'\n"
                      "r=0; listen_whisperx || r=$?\n"
                      "printf 'rc=%s after=%s' \"$r\" \"${TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD-unset}\"\n")
            env = {k: v for k, v in os.environ.items() if k != "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"}
            env["FAKE_RC"] = str(rc)
            if os.path.exists(seen):
                os.remove(seen)
            out = subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=env)
            got = open(seen, encoding="utf-8").read() if os.path.exists(seen) else "<not run>"
            return got, out.stdout.strip(), out.stderr

        print("1-3. Windows")
        got, tail, err = run(True)
        check("the WhisperX process sees TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1", got == "1", f"{got!r} {err[-300:]}")
        check("after the run the variable is unset again", tail == "rc=0 after=unset", tail)
        got, tail, err = run(True, before="0")
        check("her own value comes back after the run", got == "1" and tail == "rc=0 after=0", f"{got!r} {tail}")
        got, tail, err = run(True, rc=1)
        check("WhisperX's exit code reaches the caller", tail == "rc=1 after=unset", tail)

        print("4. a Mac")
        got, tail, err = run(False)
        check("the WhisperX process never sees the variable", got == "unset", f"{got!r} {err[-300:]}")
        check("and the shell is untouched", tail == "rc=0 after=unset", tail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
elif not BASH:
    print("  (no bash here: the shell half is skipped)")

print("5. vo-cutgrid.py")
with open(VO, encoding="utf-8") as fh:
    vo = fh.read()
check("vo-cutgrid sets it for its WhisperX run on Windows only",
      re.search(r'env = dict\(os\.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1"\) if os\.name == "nt" else None', vo)
      is not None and vo.count("env=env") >= 2)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "whisperx weights-only: Windows loads WhisperX's checkpoint, a Mac is unchanged"))
sys.exit(1 if fails else 0)
