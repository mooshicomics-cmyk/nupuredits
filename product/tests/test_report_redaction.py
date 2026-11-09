#!/usr/bin/env python3
"""The two report tools never print the person's account name, on a Mac or a PC.

scripts/collect-report.sh ("/report-a-problem") and product/make-handoff.py (the hardware diagnostic) promise
that home-folder paths come out as "~". On Windows the same home folder arrives in three spellings:
C:\\Users\\your-name (LOCALAPPDATA, APPDATA, USERPROFILE, and what Python reports), C:/Users/your-name, and Git Bash's
/c/Users/your-name. Both tools used to shorten only one of them, so the CapCut lines of a PC report, and the log
tail of every diagnostic, carried the Windows account name.

Run: python3 product/tests/test_report_redaction.py   (Windows: python)
"""
import importlib.util
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


NAME = "Jane Doe"
WIN = {"HOME": "/c/Users/" + NAME, "USERPROFILE": "C:\\Users\\" + NAME}
PATHS = ["C:\\Users\\" + NAME + "\\AppData\\Local/CapCut/User Data/Projects/com.lveditor.draft",
         "C:/Users/" + NAME + "/AppData/Roaming/uv/python",
         "/c/Users/" + NAME + "/.local/bin/python3"]

# 1. collect-report.sh's tilde(), exactly as the script defines it
with open(os.path.join(ROOT, "scripts", "collect-report.sh"), encoding="utf-8") as fh:
    src = fh.read()
m = re.search(r"^tilde\(\) \{.*?^\}\n|^tilde\(\) \{[^\n]*\}\n", src, re.S | re.M)
check("collect-report.sh defines tilde()", bool(m))
if m:
    script = m.group(0) + 'for p in "$@"; do printf "%s\\n" "$(tilde "$p")"; done\n'
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **WIN}
    out = subprocess.run(["bash", "-c", script, "tilde-test", *PATHS], capture_output=True, text=True,
                         encoding="utf-8", env=env).stdout
    check("a PC report prints no account name, in any spelling", NAME not in out, out.strip())
    check("... and every one of those paths starts at ~", all(l.startswith("~") for l in out.splitlines()), out)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/Users/your-name"}
    out = subprocess.run(["bash", "-c", script, "tilde-test", "/Users/your-name/Movies/CapCut", "/opt/homebrew/bin"],
                         capture_output=True, text=True, encoding="utf-8", env=env).stdout.splitlines()
    check("a Mac report is shortened exactly as before", out == ["~/Movies/CapCut", "/opt/homebrew/bin"], out)

# 2. make-handoff.py's _redact (also used on the log tail now)
spec = importlib.util.spec_from_file_location("make_handoff", os.path.join(ROOT, "product", "make-handoff.py"))
mh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mh)
saved = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
try:
    os.environ.update(WIN)
    got = [mh._redact(p) for p in PATHS]
    check("the hardware diagnostic prints no account name, in any spelling", not any(NAME in g for g in got), got)
    os.environ["HOME"] = "/Users/your-name"
    os.environ.pop("USERPROFILE", None)
    check("a Mac path is redacted exactly as before", mh._redact("/Users/your-name/.local/bin/ffmpeg") == "~/.local/bin/ffmpeg")
    with open(os.path.join(ROOT, "product", "make-handoff.py"), encoding="utf-8") as fh:
        check("the log tail goes through the same redaction", "_redact(log_text" in fh.read())
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "report tools keep the account name out, on a Mac and a PC"))
sys.exit(1 if fails else 0)
