#!/usr/bin/env python3
"""A Windows buyer must get the SAME guided setup a Mac buyer gets, not an experimental fallback.

Before this, `set-me-up` checked for a Mac on the first message and routed everyone else into the
`pc-conversion` skill, which offers an honest experiment or a refund. So a PC buyer never entered the
onboarding at all, nothing matched the course videos, and a capable tester stopped partway through. That
is a product decision encoded in two files, which means it can be silently undone by an edit to either.

These tests pin the decision: one flow, both platforms, and the unsupported-platform path stays for
platforms that are genuinely unsupported."""
import os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SETUP = os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md")
PCCONV = os.path.join(ROOT, ".claude", "skills", "pc-conversion", "SKILL.md")
ENGINE = os.path.join(ROOT, "product", "engine", "VectCutAPI", "setup-editor-engine.sh")
fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


setup = open(SETUP, encoding="utf-8").read()
pcconv = open(PCCONV, encoding="utf-8").read()
engine = open(ENGINE, encoding="utf-8").read()

print("set-me-up covers both platforms in one flow")
check("says both are supported", "both are supported" in setup.lower() or
      "Mac and Windows" in setup or "both Mac and Windows" in setup)
check("has the platform-detect step (0.1)", "### 0.1" in setup)
check("has the Windows pre-flight step (0.2)", "### 0.2" in setup)
check("0.2 checks for Git Bash", "Git Bash" in setup)
check("0.2 checks long paths", "LongPathsEnabled" in setup)
check("0.2 checks UTF-8", "PYTHONUTF8" in setup)

print("\nthe install step branches instead of assuming Homebrew")
check("has a winget branch", "winget install" in setup)
check("still has the Homebrew branch for Mac", "brew install" in setup or "Homebrew" in setup)
check("names the Windows starter file", "start-editor.bat" in setup)
# make-ship's whitelabel scrub rewrites "buyer" to "creator" in the shipped copy, and this guard now runs on
# the staged bundle too (check-ship §23), so it must accept either wording.
check("does NOT tell a Windows buyer to install Homebrew",
      re.search(r"Do NOT tell a Windows (buyer|creator) to install Homebrew", setup) is not None)

print("\na Windows buyer is never routed out of setup")
# the old behaviour: 0.1 handed every non-Mac machine to pc-conversion
routed_out = re.search(r"If it does NOT print `Darwin`.{0,200}pc-conversion", setup, re.S)
check("0.1 no longer sends every non-Mac machine to pc-conversion", not routed_out)
check("pc-conversion is scoped to unsupported platforms",
      "LAST RESORT" in pcconv or "unsupported-platform" in pcconv)
check("pc-conversion warns against taking Windows buyers",
      "Windows is SUPPORTED" in pcconv)
check("pc-conversion no longer advertises plain 'I am on a PC' as its trigger",
      not re.search(r'description:[^\n]*"I\'m on a PC"', pcconv))

print("\nthe editing-engine setup runs on both machines")
check("detects the platform", "MINGW" in engine)
check("uses venv_py rather than a hardcoded bin/python", "venv_py" in engine)
check("no hardcoded ./venv-capcut/bin/python left", "./venv-capcut/bin/python" not in engine)
check("knows the Windows CapCut folder", "LOCALAPPDATA" in engine)
check("offers a Windows install line for the video engine", "Gyan.FFmpeg" in engine)

print("\nno Mac-only phrasing outside the Mac branch")
mac_branch = setup[setup.index("**ON A MAC"):] if "**ON A MAC" in setup else ""
before_mac = setup[:setup.index("**ON A MAC")] if "**ON A MAC" in setup else setup
stray = [m.group(0) for m in re.finditer(r"(your|her) Mac\b", before_mac)]
check(f"no 'your/her Mac' before the Mac branch (found: {stray or 'none'})", not stray)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "PC onboarding is wired end to end"))
sys.exit(1 if fails else 0)
