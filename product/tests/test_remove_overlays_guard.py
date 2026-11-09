#!/usr/bin/env python3
"""test_remove_overlays_guard.py — remove-overlays does its job on a PC, and refuses while CapCut is open.

Its CapCut check used to be a Windows branch that returned straight after asking tasklist, so on a PC the tool
removed nothing and still exited 0 (open CapCut or not), and on a Mac it had its own pgrep check. It now uses
the shared guard, draft_safety.require_capcut_quit, on both. Simulated here in a temp folder; no real CapCut.
Run: python3 product/tests/test_remove_overlays_guard.py
"""
import contextlib, importlib.util, io, json, os, subprocess, sys, tempfile

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
spec = importlib.util.spec_from_file_location("remove_overlays", os.path.join(PRODUCT, "remove-overlays.py"))
ro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ro)
import draft_safety

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


def attempt(platform, running):
    """main() on a fresh one-overlay draft. Returns (outcome, tracks left)."""
    tmp = tempfile.mkdtemp(prefix="remove-overlays-")
    ro.CAP = tmp
    draft_safety.CAP = tmp
    folder = os.path.join(tmp, "Reel 1.1")
    os.makedirs(folder)
    name = "draft_content.json" if platform == "win" else "draft_info.json"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        json.dump({"materials": {"videos": [{"id": "F", "material_name": "video_0"},
                                            {"id": "C", "material_name": "cap-single"}]},
                   "tracks": [{"type": "video", "flag": 0, "name": "", "is_default_name": False,
                               "segments": [{"material_id": "F"}]},
                              {"type": "video", "flag": 2, "name": "", "is_default_name": True,
                               "segments": [{"material_id": "C"}]}], "config": {}}, fh)

    def fake_run(args, *a, **k):
        if args[0] == "tasklist":
            return subprocess.CompletedProcess(args, 0, b"CapCut.exe 4321 Console\n" if running else b"INFO: none\n", b"")
        if args[0] == "pgrep":
            return subprocess.CompletedProcess(args, 0 if running else 1, "4321\n" if running else "", "")
        raise AssertionError(f"unexpected command {args}")

    real_run, real_name = subprocess.run, os.name
    subprocess.run = fake_run
    os.environ["CAPCUT_DRAFT"] = "Reel 1.1"
    os.environ.pop("CAPCUT_ALLOW_OPEN", None)
    if platform == "win":
        os.name = "nt"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ro.main([])
        outcome = "ran"
    except draft_safety.CapCutOpen:
        outcome = "refused"
    except SystemExit as e:
        outcome = f"exit {e.code!r}"
    finally:
        os.name = real_name
        subprocess.run = real_run
    left = json.load(open(os.path.join(folder, name), encoding="utf-8")).get("tracks")
    return outcome, len(left)


for platform in ("win", "mac"):
    got = attempt(platform, running=False)
    check(got == ("ran", 1), f"{platform}, CapCut closed: the overlay must be removed, got {got}")
    got = attempt(platform, running=True)
    check(got == ("refused", 2), f"{platform}, CapCut open: must refuse and touch nothing, got {got}")

if failures:
    print("✗ remove-overlays guard: " + "; ".join(failures))
    sys.exit(1)
print("✓ remove-overlays guard: on a PC and a Mac it removes the overlay with CapCut closed, and refuses "
      "(touching nothing) with CapCut open")
