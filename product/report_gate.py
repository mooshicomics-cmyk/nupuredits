#!/usr/bin/env python3
"""report_gate.py — the one door every problem report goes through before she is told to send it.

Two things decide whether a report reaches the engine team's inbox, and this file holds both in code instead of
leaving them to judgment in the moment:

  1. THIS ENGINE IS THE NEWEST ONE. Most reports in the launch weeks described bugs a later version had already
     fixed. So the gate asks the same signed update feed /update reads (the early-access feed too, when she has a
     codeword saved) and refuses while a newer version is out. "Couldn't check" also refuses: a report that may be
     about a fixed bug waits for one more try, it does not go in on a guess.
  2. EVERY ENGINE NEEDS THIS FIX. The inbox is for fixes that go out to all buyers. Anything that lives on her one
     machine (her security software, her one clip, her disk, her internet, a CapCut she changed, a computer the
     engine doesn't support) is patched right here and never sent. To pass, Claude names, in one sentence, why
     the same thing would happen in anyone's engine on a normal setup. That sentence goes in the report.

Only when both pass does it stamp `_local/problem-report.md` with a "Ready to send" block and print SEND-READY.
A report without that block is not ready, whatever else it says.

CLI (run from the engine folder):
  python3 product/report_gate.py                          is this engine the newest? (exit 0 newest, 2 behind, 3 can't tell)
  python3 product/report_gate.py --send "<why every engine hits this>" [--report <file>]
                                                          both checks; stamps the report and prints SEND-READY (exit 0)
Windows: `python`, never `python3`.
"""
import argparse
import datetime
import importlib.util
import os
import re
import sys

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPORT = os.path.join(ROOT, "_local", "problem-report.md")
STAMP_HEAD = "### Ready to send"

NEWEST, BEHIND, UNKNOWN = 0, 2, 3


def _updater():
    """scripts/apply-update.py as a module: the same feed, channel and signature rules /update uses."""
    spec = importlib.util.spec_from_file_location("apply_update", os.path.join(ROOT, "scripts", "apply-update.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def newest_check(updater=None):
    """(status, this version, newest version or "", reason). Never raises."""
    try:
        au = updater or _updater()
        cur = str(au.load_product().get("version", "0.0.0"))
    except BaseException as e:   # die() raises SystemExit
        return UNKNOWN, "", "", f"couldn't read this engine's version ({e})"
    try:
        base = au._update_url()
        if not base:
            return UNKNOWN, cur, "", "this engine has no update feed set"
        feeds = [base + "/latest.json"]
        channel = au._saved_channel()
        if channel:
            feeds.append(f"{base}/{channel}/latest.json")
        us = au._signature_module()
        newest, err = "", ""
        for url in feeds:
            feed, e = au._read_feed(url)
            if e is not None or not isinstance(feed, dict):
                if url == feeds[0]:
                    err = str(e or "an unreadable answer")
                continue
            why = us.check_feed(feed) if us else "the signature checker is missing"
            if why:
                if url == feeds[0]:
                    err = f"the feed's signature didn't check out ({why})"
                continue
            v = str(feed.get("version", ""))
            if v and (not newest or au.semver(v) > au.semver(newest)):
                newest = v
        if not newest:
            return UNKNOWN, cur, "", f"the update server didn't answer ({err or 'no reply'})"
        if au.semver(newest) > au.semver(cur):
            return BEHIND, cur, newest, f"v{newest} is out and this engine is v{cur}"
        return NEWEST, cur, newest, f"v{cur} is the newest"
    except BaseException as e:
        return UNKNOWN, cur, "", f"the check itself failed ({e})"


def _say_newest(status, cur, newest, reason):
    if status == NEWEST:
        print(f"NEWEST: {reason}. A report from this engine is about a problem the newest version still has.")
    elif status == BEHIND:
        print(f"BEHIND: {reason}. Run /update first and try what failed again; the fix is very likely already in "
              f"it. No report goes in from an engine that is behind.")
    else:
        print(f"CAN'T TELL: {reason}. No report goes in until this answers: try again in a few minutes. "
              f"Nothing is wrong with her engine for this.")


def stamp(report, cur, why):
    """Put (or replace) the Ready to send block at the end of the report."""
    with open(report, encoding="utf-8") as f:
        text = f.read()
    text = re.split(r"\n" + re.escape(STAMP_HEAD) + r"\n", text)[0].rstrip("\n")
    when = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    text += (f"\n\n{STAMP_HEAD}\n\n"
             f"- **Newest engine:** yes, v{cur} (checked against the update feed {when})\n"
             f"- **Every engine needs this fix:** {why.strip()}\n")
    with open(report, "w", encoding="utf-8") as f:
        f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The gate a problem report passes before she is told to send it.")
    ap.add_argument("--send", metavar="WHY", help="why every buyer's engine would hit this, in one sentence")
    ap.add_argument("--report", default=REPORT, help="the report file (default _local/problem-report.md)")
    a = ap.parse_args(argv)

    status, cur, newest, reason = newest_check()
    _say_newest(status, cur, newest, reason)
    if a.send is None:
        return status
    if status != NEWEST:
        print("NOT READY: the report stays on her computer, unsent.")
        return status
    why = (a.send or "").strip()
    if len(why.split()) < 6:
        print("NOT READY: say in one real sentence why anyone's engine on a normal setup would hit this. If it "
              "only happens on her machine, her file or her setup, it is not a report: patch it here and tell her "
              "it's fixed.")
        return 4
    if not os.path.isfile(a.report):
        print(f"NOT READY: no report file at {a.report}. Run bash scripts/collect-report.sh first.")
        return 5
    stamp(a.report, cur, why)
    print(f"SEND-READY: {os.path.relpath(a.report, ROOT)} is stamped. Now, and only now, ask her to send it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
