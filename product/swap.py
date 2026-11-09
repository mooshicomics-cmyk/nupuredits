#!/usr/bin/env python3
"""swap.py — put a finished file in place of another in one step, waiting out Windows' brief locks.

os.replace is atomic, so nothing ever reads half a file. On Windows it raises PermissionError (WinError 5 "Access
is denied", or WinError 32, the file is in use) while anything still holds the target or the new file open for a
moment: an antivirus scan of a freshly written MP4, the visual editor's page reading the cut, the search indexer.
A buyer's voice leveling was skipped for exactly that (2026-10-21). replace() tries again for a few seconds with
growing waits; on a Mac, or a Windows PC where nothing holds the file, the first try succeeds and nothing changes.

    from swap import replace
    replace(tmp, path)          # raises the last PermissionError only if the file stayed locked the whole time
"""
import os
import time

WAITS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.5, 2.0, 2.0)   # about 8 s in all: a scan of a long cut fits inside it


def replace(src, dst, waits=WAITS):
    """os.replace(src, dst), retried while Windows says the file is busy. The caller cleans up src on failure."""
    for wait in tuple(waits) + (None,):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)
