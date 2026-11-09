#!/usr/bin/env python3
"""test_capcut_front.py — the keep-on-top pass must be quiet when there is nothing to do.

capcut_front.ensure() runs every 30 seconds from its LaunchAgent. It used to rewrite CapCut's index, and leave
a timestamped backup of it, on EVERY run, even when the remembered drafts already led the list: one drafts
folder collected thousands of backups that way. And its CapCut check answered "not running" when the check
itself failed, which is the one answer that lets it write.

Everything here runs in a temp folder: the real index, the real pin list and the real CapCut are never touched.
Run: python3 product/tests/test_capcut_front.py
"""
import glob, json, os, subprocess, sys, tempfile, time

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capcut_front as cf

_REAL = [cf.STATE, cf.META]
_REAL_BEFORE = {p: (os.path.getmtime(p) if os.path.exists(p) else None) for p in _REAL}
tmp = tempfile.mkdtemp(prefix="capcut-front-test-")
cf.CAP = tmp
cf.META = os.path.join(tmp, "root_meta_info.json")
cf.STATE_DIR = tmp
cf.STATE = os.path.join(tmp, "capcut-front.json")
cf.capcut_running = lambda: False            # "closed", without asking the real machine

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


def order():
    store = json.load(open(cf.META, encoding="utf-8"))["all_draft_store"]
    return [e["draft_name"] for e in sorted(store, key=lambda e: e.get("tm_draft_modified", 0), reverse=True)]


def own_backups():
    return sorted(p for p in glob.glob(cf.META + ".bak-*")
                  if os.path.basename(p)[len("root_meta_info.json.bak-"):].isdigit())


for n in ("A", "B", "C", "other"):
    os.makedirs(os.path.join(tmp, n))
store = [{"draft_name": n, "draft_fold_path": os.path.join(tmp, n), "tm_draft_modified": t, "tm_draft_create": t}
         for n, t in (("C", 300), ("B", 200), ("A", 100), ("other", 50))]
with open(cf.META, "w", encoding="utf-8") as fh:
    json.dump({"all_draft_store": store, "draft_ids": 4, "root_path": tmp}, fh)
with open(cf.META + ".bak-pre-update", "w", encoding="utf-8") as fh:
    fh.write("a backup some other tool made")
for n in ("C", "B", "A"):
    cf.remember(n)                            # keep_on_top = [A, B, C]

real_time = time.time
try:
    # 1) the first pass puts them in order and writes once
    time.time = lambda: 1_790_000_000
    cf.ensure()
    check(order()[:3] == ["A", "B", "C"], f"first pass should lead with A, B, C, got {order()}")
    first = open(cf.META, encoding="utf-8").read()

    # 2) nothing changed since: the next passes write nothing and leave no backup
    for i in range(20):
        time.time = lambda i=i: 1_790_000_100 + 30 * i
        cf.ensure()
    check(open(cf.META, encoding="utf-8").read() == first, "an ensure() with the order already right rewrote the index")
    check(len(own_backups()) == 1, f"an ensure() with the order already right left backups: {own_backups()}")

    # 3) she worked on another draft in CapCut, so it moved up: the next pass puts hers back on top
    data = json.load(open(cf.META, encoding="utf-8"))
    for e in data["all_draft_store"]:
        if e["draft_name"] == "other":
            e["tm_draft_modified"] = 1_790_000_500 * 1_000_000
    with open(cf.META, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    time.time = lambda: 1_790_001_000
    cf.ensure()
    check(order()[:3] == ["A", "B", "C"], f"a pass after the order drifted should restore it, got {order()}")

    # 4) a remembered draft that no longer exists does not make every pass rewrite the index
    cf.remember("gone")                       # not in the index at all
    time.time = lambda: 1_790_002_000
    cf.ensure()                               # the new first pin is unplaceable: the rest already lead
    before = open(cf.META, encoding="utf-8").read()
    time.time = lambda: 1_790_002_030
    cf.ensure()
    check(open(cf.META, encoding="utf-8").read() == before, "an unplaceable pin made ensure() rewrite the index")

    # 5) its own backups are rotated to the newest five; anybody else's are left alone
    for k in range(9):
        with open(cf.META + f".bak-17800000{k:02d}", "w", encoding="utf-8") as fh:
            fh.write("old")
    with open(cf.META + ".bak-1780000000.keep", "w", encoding="utf-8") as fh:
        fh.write("not one of its own")
    time.time = lambda: 1_790_003_000
    cf.to_front("C")                          # a real move: writes, backs up, rotates
    own = own_backups()
    check(len(own) == getattr(cf, "KEEP_BACKUPS", 5), f"expected 5 of its own backups after rotating, got {len(own)}")
    check(own and own[-1].endswith(".bak-1790003000"), f"the backup it just made must be kept: {own}")
    check(os.path.exists(cf.META + ".bak-pre-update"), "rotation removed a backup that was not its own")
    check(os.path.exists(cf.META + ".bak-1780000000.keep"), "rotation removed a file that only looks like its own")
finally:
    time.time = real_time

# 6) "could not tell" is its own answer, never "not running"
import importlib
cf2 = importlib.reload(cf)                   # the real capcut_running again
real_run = subprocess.run
try:
    def missing(*a, **k):
        raise FileNotFoundError(2, "No such file or directory", a[0][0])
    subprocess.run = missing
    check(cf2.capcut_running() is None, "a process check that could not run must answer None")
    subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a[0], 3, b"", b"")
    check(cf2.capcut_running() is None, "a process check that failed must answer None")
    real_name = os.name
    os.name = "nt"
    try:
        subprocess.run = missing
        check(cf2.capcut_running() is None, "on Windows a missing tasklist must answer None, not False")
        subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "")
        check(cf2.capcut_running() is None, "on Windows a failed tasklist must answer None, not False")
        subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, b"CapCut.exe  4321 Console", b"")
        check(cf2.capcut_running() is True, "on Windows a listed CapCut.exe is running")
        # Spanish Windows: tasklist prints in cp850 ("Nombre de imagen ... Sesi\xa2n"), not UTF-8. A text decode
        # of that raised UnicodeDecodeError and the CapCut check answered None, blocking every handoff.
        _es = "Nombre de imagen   PID Nombre de sesión\nCapCut.exe   4321 Console\n".encode("cp850")
        def _strict(*a, **k):
            if k.get("text") or k.get("encoding") or k.get("universal_newlines"):
                _es.decode("utf-8")          # what the old text=True call did; raises on 0xa2
            return subprocess.CompletedProcess(a[0], 0, _es, b"")
        subprocess.run = _strict
        check(cf2.capcut_running() is True, "on Spanish Windows (cp850 tasklist) CapCut.exe is still found")
        _es_closed = "Nombre de imagen   PID Nombre de sesión\nexplorer.exe   11 Console\n".encode("cp850")
        subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, _es_closed, b"")
        check(cf2.capcut_running() is False, "on Spanish Windows a closed CapCut answers False, not None")
    finally:
        os.name = real_name
finally:
    subprocess.run = real_run

for p, before in _REAL_BEFORE.items():
    after = os.path.getmtime(p) if os.path.exists(p) else None
    check(after == before, f"the test wrote to a real file it must never touch: {p}")

if failures:
    print("✗ capcut_front: " + "; ".join(failures))
    sys.exit(1)
print("✓ capcut_front: a pass with the order already right writes nothing, a drifted order is restored, its own "
      "backups keep the newest five and nobody else's, and a failed CapCut check counts as running")
