#!/usr/bin/env python3
"""The CapCut-must-be-quit guard must never pass because it FAILED to look.

Writing to a draft while CapCut has it open is silently discarded on CapCut's next save, which is how a
creator's hand edits disappear. capcut_running() used to answer False whenever the underlying process
check errored, and False means "go ahead and write" — so on any machine where pgrep or tasklist was
missing or blocked, the safety net quietly reported all clear.

Same failure shape as a verifier that passes having checked nothing. "I could not tell" is now its own
answer (None) and every caller treats it as unsafe."""
import os, sys, subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import draft_safety as ds

fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def with_broken_process_check(fn):
    """Run fn() with the process lookup raising, i.e. the machine cannot answer the question."""
    real = subprocess.run

    def broken(*a, **k):
        raise FileNotFoundError("pgrep/tasklist: command not found")

    subprocess.run = broken
    try:
        return fn()
    finally:
        subprocess.run = real


print("capcut_running() reports three distinct states, not two")
check("returns None when the process check cannot run",
      with_broken_process_check(ds.capcut_running) is None)
check("returns a real bool on a working machine",
      ds.capcut_running() in (True, False))

print("\na non-English Windows still gets a real answer (tasklist is not UTF-8 there)")


def _on_windows(stdout_bytes):
    """Run capcut_running() as if on Windows, with tasklist printing these exact bytes. A text decode
    (text=True / encoding=) of cp850 output raises, which is what blocked a Spanish Windows handoff."""
    real_run, real_name = subprocess.run, os.name

    def fake(*a, **k):
        if k.get("text") or k.get("encoding") or k.get("universal_newlines"):
            stdout_bytes.decode("utf-8")
        return subprocess.CompletedProcess(a[0], 0, stdout_bytes, b"")

    subprocess.run, os.name = fake, "nt"
    try:
        return ds.capcut_running()
    finally:
        subprocess.run, os.name = real_run, real_name


_hdr = "Nombre de imagen    PID Nombre de sesión  Núm. de ses\n"
check("Spanish Windows, CapCut open -> True",
      _on_windows((_hdr + "CapCut.exe   4321 Console   1\n").encode("cp850")) is True)
check("Spanish Windows, CapCut closed -> False",
      _on_windows((_hdr + "explorer.exe   11 Console   1\n").encode("cp850")) is False)
check("French Windows (cp1252), CapCut open -> True",
      _on_windows("Nom de l’image   PID Nom de la session\nCapCut.exe 9 Console\n".encode("cp1252")) is True)

print("\nno tasklist call anywhere decodes its output as text")
import glob as _g, re as _re
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_txt = []
for _f in (_g.glob(os.path.join(_root, "product", "*.py"))
           + _g.glob(os.path.join(_root, ".claude", "skills", "**", "*.py"), recursive=True)):
    for _ln in open(_f, encoding="utf-8", errors="ignore"):
        if '"tasklist"' in _ln and "subprocess" in _ln and "text=True" in _ln and "errors=" not in _ln:
            _txt.append(os.path.relpath(_f, _root))
check(f"tasklist output is read as bytes, or decoded with errors= (offenders: {sorted(set(_txt)) or 'none'})",
      not _txt)

print("\nrequire_capcut_quit REFUSES on 'could not tell' instead of allowing the write")


def _guard():
    try:
        ds.require_capcut_quit("write this draft")
        return "allowed"
    except RuntimeError:
        return "refused"


os.environ.pop("CAPCUT_ALLOW_OPEN", None)
check("unknown state refuses the write", with_broken_process_check(_guard) == "refused")

print("\nthe deliberate override still works (so a creator is never stuck)")
os.environ["CAPCUT_ALLOW_OPEN"] = "1"
check("CAPCUT_ALLOW_OPEN=1 allows it", with_broken_process_check(_guard) == "allowed")
os.environ.pop("CAPCUT_ALLOW_OPEN", None)

print("\nno caller may treat a falsy result as 'safe to write'")
import glob, re, subprocess
bad = []
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
for f in (glob.glob(os.path.join(root, "product", "*.py"))
          + glob.glob(os.path.join(root, ".claude", "skills", "**", "*.py"), recursive=True)):
    for line in open(f, encoding="utf-8", errors="ignore"):
        # `if capcut_running():` is the bug — None is falsy, so unknown reads as "not running"
        if re.search(r"if\s+capcut_running\(\)\s*(?:or|\)|:)", line) and "is not False" not in line:
            bad.append(os.path.relpath(f, root))
check(f"every caller compares against False explicitly (offenders: {sorted(set(bad)) or 'none'})", not bad)

print("\nthe refusal reads as a refusal, not as a crash")
# A creator who sees "Exit code 1" and a stack trace has no way to know the guard did the right thing and
# is waiting for her. A real PC test caught this: the message inside was perfectly clear, and the traceback
# wrapped around it made the engine look broken at the exact moment it was protecting her work.
check("the refusal has its own exception class", hasattr(ds, "CapCutOpen"))
check("it still subclasses RuntimeError, so every existing 'except RuntimeError' catches it",
      issubclass(ds.CapCutOpen, RuntimeError))

_real = ds.capcut_running
ds.capcut_running = lambda: True
try:
    ds.require_capcut_quit("build this reel")
    check("an open CapCut refuses the write", False)
except ds.CapCutOpen as e:
    check("an open CapCut refuses the write", True)
    check("the refusal says what to do", "quit it fully" in str(e).lower())
finally:
    ds.capcut_running = _real

_sub = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, %r); import draft_safety as d; "
     "d.capcut_running = lambda: True; d.require_capcut_quit('build this reel')"
     % os.path.join(root, "product")],
    capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1", "CAPCUT_ALLOW_OPEN": ""})
check("run as a script, it prints the sentence and NO traceback",
      "Traceback" not in _sub.stderr and "CapCut is open" in _sub.stderr)
check("it still exits non-zero, so nothing downstream treats it as success", _sub.returncode != 0)

_bug = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, %r); import draft_safety; 1/0" % os.path.join(root, "product")],
    capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})
check("a REAL fault still gets its whole traceback",
      "Traceback" in _bug.stderr and "ZeroDivisionError" in _bug.stderr)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "quit-guard tests passed"))
sys.exit(1 if fails else 0)
