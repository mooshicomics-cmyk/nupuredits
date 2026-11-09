#!/usr/bin/env python3
"""capcut_front.py — keep engine-built drafts at the TOP of CapCut's project list, permanently.

Her list is 150+ drafts deep. A new draft that lands in the middle of it is lost, and she should never have
to hunt for the thing she just asked for.

Doing this once at build time does not work, and that is the whole problem. CapCut orders the browser by
`tm_draft_modified` in `root_meta_info.json`, and it REWRITES that file from its own records every time it
runs — so a draft put at the top while CapCut was quit gets shuffled straight back down the next time she
opens the app. It has to be re-applied AFTER each CapCut session, which is not something a build step can do.

So the builders `remember` a draft, and `--ensure` re-applies it whenever CapCut is closed. A LaunchAgent can
run `--ensure` on a timer, which makes it automatic instead of something to ask for.

The agent is OPT-IN and nothing installs it for you: it only exists if `--install` is run by hand, and it
only ever acts while CapCut is CLOSED, so it cannot interfere with a session in progress. `--uninstall`
removes it completely.

  python3 product/capcut_front.py "<name>"          # bring one to the top now
  python3 product/capcut_front.py --remember "<name>"   # and keep it there from now on
  python3 product/capcut_front.py --ensure         # re-apply if CapCut is closed (the LaunchAgent calls this)
  python3 product/capcut_front.py --install        # install the LaunchAgent
  python3 product/capcut_front.py --uninstall      # remove it
  python3 product/capcut_front.py --list           # show the top of the list

CapCut must be QUIT for any write: anything written to its index while it is running is overwritten on its
next save. The index is her record of every draft she owns, so it is backed up before it is touched and no
other entry is ever modified.
"""
import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import time

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
# Buyer-facing: Cmd+Q does not exist on Windows.
_QUIT_HINT = "right-click its taskbar icon and Close, or use Task Manager" if os.name == "nt" else "Cmd+Q"

US = 1_000_000
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
META = f"{CAP}/root_meta_info.json"
STATE_DIR = os.path.expanduser("~/Library/Application Support/reels-engine")
STATE = f"{STATE_DIR}/capcut-front.json"
LABEL = "com.reelseditingengine.draft-order"   # neutral: this file ships to buyers
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def capcut_running():
    """True if CapCut is running, False if it certainly is not, None when the check itself could not run.

    Every caller treats None as running (`is not False`), exactly like draft_safety.capcut_running. This used to
    answer False when tasklist failed, and False means "go ahead and rewrite her list of drafts"."""
    if os.name == "nt":
        try:
            # Bytes, never text: tasklist prints in the console's OEM codepage (cp850 on Spanish Windows),
            # so decoding it as UTF-8 raised and the check answered None. The process name is plain ASCII.
            r = subprocess.run(["tasklist"], capture_output=True)
        except Exception:
            return None
        return None if r.returncode != 0 else b"CapCut.exe" in (r.stdout or b"")
    try:
        r = subprocess.run(["pgrep", "-f", "CapCut.app/Contents/MacOS/CapCut"], capture_output=True)
    except Exception:
        return None
    return None if r.returncode > 1 else bool(r.stdout.strip())      # pgrep: 1 = no match, >1 = it failed


def _state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"keep_on_top": []}


def _save_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    json.dump(s, open(STATE, "w", encoding="utf-8"), indent=1)


def remember(name):
    s = _state()
    keep = [n for n in s.get("keep_on_top", []) if n != name]
    s["keep_on_top"] = [name] + keep
    _save_state(s)


def show(limit=6):
    store = (json.load(open(META, encoding="utf-8")).get("all_draft_store") or [])
    ranked = sorted(store, key=lambda e: e.get("tm_draft_modified", 0), reverse=True)
    print(f"top of CapCut's list ({len(store)} drafts):")
    for e in ranked[:limit]:
        print(f"   {str(e.get('draft_name'))[:44]}")


KEEP_BACKUPS = 5


def _rotate_backups():
    """Keep the newest KEEP_BACKUPS of this tool's own index backups (root_meta_info.json.bak-<10-digit time>)
    and remove the older ones. Any other backup sitting beside the index is never touched."""
    folder, base = os.path.dirname(META), os.path.basename(META)
    own = re.compile(re.escape(base) + r"\.bak-(\d{10})$")
    try:
        found = sorted((int(m.group(1)), n) for n in os.listdir(folder) for m in [own.match(n)] if m)
    except OSError:
        return
    for _stamp, n in found[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(folder, n))
        except OSError:
            pass


def to_front(name, quiet=False):
    # `is not False` on purpose: capcut_running() returns None when the process check itself could not
    # run, and treating "I could not tell" as "not running" is what turns a safety net into a rubber stamp.
    # The one list an open CapCut cannot overwrite is the staging folder's (draft_safety.capcut_never_reads):
    # CapCut never reads it, so ordering it never waits on CapCut.
    if capcut_running() is not False and not _ds.capcut_never_reads(CAP):
        if quiet:
            return None
        raise SystemExit("CapCut is open, or I could not tell whether it is. Quit it fully (" + _QUIT_HINT +
                         ") first — anything written to its index while it is running is overwritten on its "
                         "next save.")
    index = json.load(open(META, encoding="utf-8"))
    store = index.get("all_draft_store") or []
    hit = [e for e in store if e.get("draft_name") == name]
    if not hit:
        if quiet:
            return None
        raise SystemExit(f"{name!r} is not in CapCut's index. Was it built and registered?")
    entry = hit[0]
    ranked = sorted(store, key=lambda e: e.get("tm_draft_modified", 0), reverse=True)
    if ranked and ranked[0] is entry:
        return 1                                    # already first, nothing to write
    folder = entry.get("draft_fold_path") or f"{CAP}/{name}"
    if not os.path.isdir(folder):
        if quiet:
            return None
        raise SystemExit(f"the index points at {folder}, which does not exist")

    shutil.copy2(META, f"{META}.bak-{int(time.time())}")
    _rotate_backups()
    now = int(time.time() * US)
    entry["tm_draft_modified"] = now
    entry["tm_draft_create"] = now
    index["all_draft_store"] = [entry] + [e for e in store if e is not entry]
    json.dump(index, open(META, "w", encoding="utf-8"))
    for p in (folder, _ds.draft_json(folder)):
        if os.path.exists(p):
            os.utime(p, None)
    if not quiet:
        print(f"✅ {name!r} is now #1 of {len(store)} in CapCut's list "
              f"({len(store) - 1} other drafts untouched)")
    return 1


def _leads_already(keep):
    """True when the remembered drafts that can be placed already lead the list, in the remembered order, so a
    pass would only rewrite her index to say the same thing. The LaunchAgent runs every 30 seconds, and doing
    exactly that (and leaving a backup of the index behind every time) filled one drafts folder with thousands
    of backups."""
    try:
        store = json.load(open(META, encoding="utf-8")).get("all_draft_store") or []
    except (OSError, ValueError):
        return False
    placeable = []
    for name in keep:
        hit = next((e for e in store if e.get("draft_name") == name), None)
        if hit and os.path.isdir(hit.get("draft_fold_path") or f"{CAP}/{name}"):
            placeable.append(name)
    ranked = sorted(store, key=lambda e: e.get("tm_draft_modified", 0), reverse=True)
    return [e.get("draft_name") for e in ranked[:len(placeable)]] == placeable


def ensure():
    """Re-apply the remembered order, but only while CapCut is closed. Safe to run on a timer: when the order is
    already right it writes nothing at all."""
    if not os.path.exists(META):
        return
    if capcut_running() is not False and not _ds.capcut_never_reads(CAP):   # unknown counts as running
        return
    keep = _state().get("keep_on_top", [])[:5]
    if _leads_already(keep):
        return
    for name in reversed(keep):
        try:
            to_front(name, quiet=True)
        except Exception:
            pass


def install_agent():
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    plistlib.dump({
        "Label": LABEL,
        "ProgramArguments": [sys.executable, os.path.abspath(__file__), "--ensure"],
        "StartInterval": 30,
        "RunAtLoad": True,
        "StandardErrorPath": "/dev/null",
        "StandardOutPath": "/dev/null",
    }, open(PLIST, "wb"))
    subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
    r = subprocess.run(["launchctl", "load", PLIST], capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"{'✅ installed' if ok else '⚠ wrote the plist but launchctl load failed'}: {PLIST}")
    print("   It checks every 30s and only ever acts while CapCut is CLOSED.")
    print(f"   Remove it any time with: python3 {os.path.abspath(__file__)} --uninstall")
    if not ok and r.stderr.strip():
        print("   launchctl said:", r.stderr.strip()[:200])


def uninstall_agent():
    subprocess.run(["launchctl", "unload", PLIST], capture_output=True)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print(f"removed {PLIST}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("--remember", metavar="NAME", help="bring to the top AND keep it there")
    ap.add_argument("--ensure", action="store_true", help="re-apply if CapCut is closed (used by the agent)")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.install:
        install_agent()
    elif a.uninstall:
        uninstall_agent()
    elif a.ensure:
        ensure()
    elif a.remember:
        remember(a.remember)
        to_front(a.remember)
    elif a.list or not a.name:
        show()
    else:
        to_front(a.name)
