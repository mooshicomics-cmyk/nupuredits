#!/usr/bin/env python3
"""capcut_installs.py — which CapCuts are on this Windows PC, and which one shows the engine's projects.

WHY THIS EXISTS. CapCut comes two ways on Windows: the desktop app from capcut.com, and the Microsoft Store
app. They keep two separate lists of projects. The engine writes into the desktop CapCut's folder
(%LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft); the Store CapCut keeps its own list inside
its package (%LOCALAPPDATA%\\Packages\\<CapCut package>\\LocalCache\\...) and never sees them. A buyer with both
installed opened the Store one, saw none of her drafts, and lost an evening before her Claude worked out that
she had "the other CapCut". Nothing told her there were two.

  state()          -> {"desktop": bool, "store": bool, "desktop_exe": path or None}
  verdict()        -> "both" | "store-only" | "desktop" | "none" | "n/a" (not Windows)
  advice()         -> the plain lines to show her for "both" and "store-only", else []
  open_desktop()   -> launches the desktop CapCut, so she never has to guess which icon

The two-CapCut question is Windows only; everywhere else every answer is "n/a" and nothing is printed. --open
works on a Mac too: "open my CapCut" means the same thing there, and a buyer's Mac answered "could not find the
desktop CapCut" with CapCut 9.5.0 sitting in /Applications, the same install the engine reads her drafts from.
Standard library only.
"""
import glob
import os
import subprocess
import sys

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

DRAFTS_REL = os.path.join("CapCut", "User Data", "Projects", "com.lveditor.draft")


def _la():
    return os.environ.get("LOCALAPPDATA", "")


def desktop_exe():
    """The desktop CapCut's program, where its installer puts it (the launcher, then a versioned copy)."""
    la = _la()
    pats = []
    if la:
        pats += [os.path.join(la, "CapCut", "Apps", "CapCut.exe"),
                 os.path.join(la, "CapCut", "Apps", "*", "CapCut.exe"),
                 os.path.join(la, "Programs", "CapCut", "CapCut.exe")]
    for pf in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")):
        if pf:
            pats += [os.path.join(pf, "CapCut", "CapCut.exe"), os.path.join(pf, "CapCut", "*", "CapCut.exe")]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _desktop_shortcut():
    """A Start-menu or desktop shortcut the desktop installer made (the Store app does not make these)."""
    places = [os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
              os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
              os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")]
    return any(glob.glob(os.path.join(p, "**", "CapCut*.lnk"), recursive=True) for p in places if p.strip("\\/"))


def store_packages():
    """Microsoft Store CapCut packages for this user (their private data folders live under Packages)."""
    la = _la()
    if not la:
        return []
    return sorted(p for p in glob.glob(os.path.join(la, "Packages", "*CapCut*")) if os.path.isdir(p))


def state():
    if os.name != "nt":
        return {"desktop": False, "store": False, "desktop_exe": None}
    exe = desktop_exe()
    desktop = bool(exe) or os.path.isdir(os.path.join(_la(), DRAFTS_REL)) or _desktop_shortcut()
    return {"desktop": desktop, "store": bool(store_packages()), "desktop_exe": exe}


def verdict():
    if os.name != "nt":
        return "n/a"
    s = state()
    if s["desktop"] and s["store"]:
        return "both"
    if s["store"]:
        return "store-only"
    return "desktop" if s["desktop"] else "none"


def advice(v=None):
    v = v or verdict()
    if v == "both":
        return [
            "  ⚠  This computer has two CapCuts: the desktop app and the one from the Microsoft Store.",
            "     They keep separate lists of projects. Your projects show up in the DESKTOP CapCut only, so if",
            "     you open CapCut and they are not there, you are in the Store one. Ask Claude to \"open my CapCut\"",
            "     and it opens the right one. (You can uninstall the Store CapCut if you never use it.)",
        ]
    if v == "store-only":
        return [
            "  ⚠  The CapCut on this computer is the Microsoft Store version, which keeps its projects where the",
            "     engine cannot put them. Install the desktop CapCut from capcut.com (free), open it once, and",
            "     your projects will show up there. The Store version can stay or go.",
        ]
    return []


def mac_app():
    """The CapCut app on a Mac: the usual two folders first, then Spotlight by CapCut's bundle id, which finds it
    wherever she dragged it. None when there is none."""
    for p in ("/Applications/CapCut.app", os.path.expanduser("~/Applications/CapCut.app")):
        if os.path.isdir(p):
            return p
    try:
        found = subprocess.run(["mdfind", "kMDItemCFBundleIdentifier == 'com.lemon.lvoverseas'"],
                               capture_output=True, text=True, timeout=10).stdout.split("\n")
        return next((f for f in found if f.endswith(".app") and os.path.isdir(f)), None)
    except Exception:
        return None


def open_desktop():
    """Open the desktop CapCut (on a Mac, the CapCut app). True when it was launched."""
    if sys.platform == "darwin":
        app = mac_app()
        return bool(app) and subprocess.run(["open", "-a", app], capture_output=True).returncode == 0
    if os.name != "nt":
        return False
    exe = state()["desktop_exe"]
    try:
        if exe:
            os.startfile(exe)   # noqa: S606 — her own installed CapCut
            return True
        # A desktop CapCut installed somewhere the patterns above do not list still answers its own link
        # (workflows/capcut-live.py opens it this way), as long as the Store one is not the only CapCut here.
        if state()["desktop"] and not store_packages():
            subprocess.run(["cmd", "/c", "start", "", "capcut:"], check=True, capture_output=True)
            return True
    except Exception:
        return False
    return False


_said = {}


def say_once():
    """Print the advice at most once per run (called after every draft build). Never raises."""
    if _said:
        return
    _said[1] = True
    try:
        for ln in advice():
            print(ln)
    except Exception:
        pass


if __name__ == "__main__":
    if "--open" in sys.argv:
        if open_desktop():
            print("opened CapCut" if sys.platform == "darwin" else "opened the desktop CapCut")
        else:
            print("could not find CapCut to open" if sys.platform == "darwin"
                  else "could not find the desktop CapCut to open")
        sys.exit(0)
    v = verdict()
    print(f"capcut: {v}")
    for ln in advice(v):
        print(ln)
