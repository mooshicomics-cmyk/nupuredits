#!/usr/bin/env python3
"""A two-part hook splits on her own ' / ' divider, so a series label with a slash inside it stays whole.

Reported 2026-11-02 (Shraddha, @barelydesiparenting): a hook like "Day 3/30 / My headline" split at the
first "/" of any kind, giving eyebrow "Day 3" and headline "30 / My headline". _split must prefer " / ".
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import lookbook  # noqa: E402

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {detail}")


got = lookbook._split("Day 3/30 / My headline here")
check("series label with a slash stays whole", got == ["Day 3/30", "My headline here"], got)

got = lookbook._split("a / b")
check("a plain ' / ' divider still splits", got == ["a", "b"], got)

got = lookbook._split("a/b")
check("a bare slash with no divider is unchanged", got == ["a", "b"], got)

print(f"test_hook_slash_label: {'all ' + str(total) + ' checks passed' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
