#!/usr/bin/env python3
"""test_capcut_installs.py — two CapCuts on one PC are named, and she is pointed at the one that shows her work.

A buyer with both the desktop CapCut and the Microsoft Store CapCut opened the Store one and saw none of her
projects, for an evening. Checked here in temp folders, with Windows faked: each of the four setups is told
apart, the advice names the desktop app for "both" and capcut.com for "store-only", nothing is said off
Windows or on a normal PC, and the advice prints at most once per run.
Run: python3 product/tests/test_capcut_installs.py
"""
import contextlib, io, os, shutil, sys, tempfile

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capcut_installs as ci

fails = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        fails.append(what)


KEYS = ("LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)")
saved = {k: os.environ.get(k) for k in KEYS}
real_name = os.name
tmp = tempfile.mkdtemp(prefix="capcut-installs-")
try:
    print("off Windows nothing is checked or said")
    check(ci.verdict() == "n/a" and ci.advice() == [], "a Mac answers n/a with no advice")

    os.name = "nt"
    for k in KEYS:
        os.environ[k] = os.path.join(tmp, k.replace("(", "").replace(")", ""))
        os.makedirs(os.environ[k], exist_ok=True)
    la = os.environ["LOCALAPPDATA"]

    print("\neach setup is told apart")
    check(ci.verdict() == "none", "no CapCut at all -> none")
    store = os.path.join(la, "Packages", "ByteDancePte.Ltd.CapCut_abc123", "LocalCache")
    os.makedirs(store)
    check(ci.verdict() == "store-only", "only the Store package -> store-only")
    exe = os.path.join(la, "CapCut", "Apps", "CapCut.exe")
    os.makedirs(os.path.dirname(exe))
    open(exe, "wb").close()
    check(ci.verdict() == "both", "desktop program + Store package -> both")
    check(ci.state()["desktop_exe"] == exe, "the desktop program is found where its installer puts it")
    shutil.rmtree(os.path.join(la, "Packages"))
    check(ci.verdict() == "desktop", "desktop only -> desktop")

    print("\nthe desktop app is recognised even when its program is somewhere else")
    shutil.rmtree(os.path.join(la, "CapCut"))
    os.makedirs(os.path.join(la, ci.DRAFTS_REL))
    check(ci.verdict() == "desktop", "its projects folder alone counts")
    shutil.rmtree(os.path.join(la, "CapCut"))
    lnk = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "CapCut.lnk")
    os.makedirs(os.path.dirname(lnk))
    open(lnk, "wb").close()
    check(ci.verdict() == "desktop", "its Start-menu shortcut alone counts")

    print("\nthe advice says what to do")
    both, store_only = " ".join(ci.advice("both")), " ".join(ci.advice("store-only"))
    check("DESKTOP" in both and "open my CapCut" in both, "both: projects are in the desktop CapCut, and how to open it")
    check("capcut.com" in store_only, "store-only: get the desktop CapCut from capcut.com")
    check(ci.advice("desktop") == [] and ci.advice("none") == [], "a normal PC hears nothing")

    print("\nit is said once per run, never every build")
    os.makedirs(store)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        ci.say_once()
        ci.say_once()
    check(out.getvalue().count("two CapCuts") == 1, "two builds in one run print it once")
finally:
    os.name = real_name
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\n✓ capcut installs: two CapCuts are named, and she is sent to the one that shows her projects")
