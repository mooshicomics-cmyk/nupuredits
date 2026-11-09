#!/usr/bin/env python3
"""Guards: locking in her cut hands Claude her first looks through the watcher, no typing.

  cut      while she's still cutting, nothing is waiting for Claude
  locked   once her cut is locked in with no looks on it, "make her looks" is on Claude's list
  made     once her looks are on, it's gone from the list

Run: python3 product/tests/test_watcher_looks.py
"""
import json, os, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    jd = tempfile.mkdtemp(prefix="watcher-looks-")
    rv = os.path.join(jd, "review")
    os.makedirs(rv)
    try:
        check("cut: still cutting, no looks step", not ve._needs_looks(jd))
        json.dump({"phase": "looks"}, open(os.path.join(rv, "phase.json"), "w", encoding="utf-8"))
        check("locked: her cut is locked in with no looks on it, so making them is Claude's", ve._needs_looks(jd))
        json.dump({"layers": [{"name": "h01-hook"}]}, open(os.path.join(rv, "looks.json"), "w", encoding="utf-8"))
        check("made: her looks are on, nothing more to make", not ve._needs_looks(jd))
        real = (ve.job_dir, ve.notes, ve.looks_to_redo, ve.look_requests, ve.looks_cut)
        ve.job_dir = lambda job: jd
        ve.notes = lambda job: []
        ve.looks_to_redo = lambda _jd: []
        ve.look_requests = lambda job, **k: []
        ve.looks_cut = lambda _jd: None
        try:
            os.remove(os.path.join(rv, "looks.json"))
            items = ve.todo("x")
            check("locked: the watcher gets it as one item, id 'looks' (so her page can say Claude is making them)",
                  [(t["kind"], ve._todo_id(t)) for t in items] == [("make-looks", "looks")], items)
            json.dump({"kind": "carousel", "frames": [], "at": "2026-10-15 09:00:00"}, open(os.path.join(rv, "kit-request.json"), "w", encoding="utf-8"))
            check("kit: Make a carousel on her page is on Claude's list too", any(t["kind"] == "kit" and "carousel" in t["text"] for t in ve.todo("x")))
        finally:
            ve.job_dir, ve.notes, ve.looks_to_redo, ve.look_requests, ve.looks_cut = real
    finally:
        shutil.rmtree(jd, ignore_errors=True)
    if fails:
        print(f"test_watcher_looks: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_watcher_looks: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
