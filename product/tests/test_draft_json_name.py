#!/usr/bin/env python3
"""CapCut's timeline JSON is named per PLATFORM: draft_info.json on macOS, draft_content.json on
Windows. The engine used to hardcode the macOS name, so on a PC every draft read/write pointed at a
file that does not exist — and worse, capcut_ripple's whole-draft fail-safe found ZERO files and
reported an empty problem list, i.e. a confident "all clear" from a check that ran on nothing.

These tests pin both halves: the name is resolved from what is on disk, and a check that finds
nothing raises instead of passing."""
import os, sys, json, glob, tempfile, shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import draft_safety as ds
import capcut_ripple as cr

fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def mkdraft(name, timelines=0):
    d = tempfile.mkdtemp()
    json.dump({"tracks": []}, open(os.path.join(d, name), "w", encoding="utf-8"))
    for i in range(timelines):
        t = os.path.join(d, "Timelines", f"uuid-{i}")
        os.makedirs(t)
        json.dump({"tracks": []}, open(os.path.join(t, name), "w", encoding="utf-8"))
    return d


print("draft_json_name resolves from disk, not from a guess")
for name in ds.DRAFT_JSON_NAMES:
    d = mkdraft(name)
    check(f"{name} on disk -> {name}", ds.draft_json_name(d) == name)
    check(f"{name} full path ends correctly", ds.draft_json(d).endswith(name))
    shutil.rmtree(d)

print("\nan unknown / empty folder falls back to this platform's default")
empty = tempfile.mkdtemp()
expected = "draft_content.json" if os.name == "nt" else "draft_info.json"
check(f"empty dir -> platform default ({expected})", ds.draft_json_name(empty) == expected)

print("\ndraft_json_copies collects the top-level file AND every Timelines cache copy")
for name in ds.DRAFT_JSON_NAMES:
    d = mkdraft(name, timelines=2)
    got = ds.draft_json_copies(d)
    check(f"{name}: found 3 copies (1 top + 2 cache), got {len(got)}", len(got) == 3)
    shutil.rmtree(d)

print("\nthe false all-clear is gone: zero files RAISES instead of reporting clean")
try:
    ds.draft_json_copies(empty)
    check("empty dir raises", False)
except RuntimeError:
    check("empty dir raises", True)
check("soft mode still returns []", ds.draft_json_copies(empty, require=False) == [])

try:
    cr.verify_draft_dir(empty)
    check("capcut_ripple.verify_draft_dir raises on a blind check", False)
except RuntimeError:
    check("capcut_ripple.verify_draft_dir raises on a blind check", True)

print("\nboth files present: prefer the one THIS CapCut actually reads, not list order")
def _probe(files, default):
    d = tempfile.mkdtemp()
    for f in files:
        json.dump({}, open(os.path.join(d, f), "w", encoding="utf-8"))
    old_def, old_reg = ds._DEFAULT_DRAFT_JSON, ds._registry_draft_json_name
    ds._DEFAULT_DRAFT_JSON = default
    ds._registry_draft_json_name = lambda: None          # simulate a machine with no registry yet
    try:
        return ds.draft_json_name(d)
    finally:
        ds._DEFAULT_DRAFT_JSON, ds._registry_draft_json_name = old_def, old_reg
        shutil.rmtree(d, ignore_errors=True)

# the case that matters: a PC that ran an OLDER engine holds both — the stale macOS file the old
# engine wrote, plus the draft_content.json CapCut itself reads. List order would pick the stale one.
for label, files, default, expect in [
    ("win, both present (old engine left a stale file)",
     ["draft_info.json", "draft_content.json"], "draft_content.json", "draft_content.json"),
    ("mac, both present", ["draft_info.json", "draft_content.json"], "draft_info.json", "draft_info.json"),
    ("win, only the stale macOS file exists",
     ["draft_info.json"], "draft_content.json", "draft_info.json"),
    ("win, brand new draft, nothing on disk", [], "draft_content.json", "draft_content.json"),
]:
    check(f"{label} -> {expect}", _probe(files, default) == expect)

print("\nthe CapCut root carries NO backslashes, so media paths match CapCut's own style")
# Measured in a real Windows CapCut 9.2.0 draft: CapCut writes "C:/Users/.../clip.MOV" — forward
# slashes, drive letter, no backslashes anywhere. The engine builds absolute media paths by joining
# onto the drafts root, so if that root mixes separators (os.path.join does, on Windows) every media
# path in the draft carries a separator style CapCut never produces. Normalised at the root.
check("draft_safety.CAP has no backslashes", "\\" not in ds.CAP)
import glob as _g, re as _re
_bad = []
for _f in _g.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "*.py")):
    _src = open(_f, encoding="utf-8").read()
    if 'os.environ["LOCALAPPDATA"], "CapCut/User Data/Projects/com.lveditor.draft")' in _src \
       and '.replace("\\\\", "/")' not in _src:
        _bad.append(os.path.basename(_f))
check(f"every module normalises its CapCut root (offenders: {_bad or 'none'})", not _bad)

print("\nboth filenames are known to the engine")
check("draft_info.json known", "draft_info.json" in ds.DRAFT_JSON_NAMES)
check("draft_content.json known", "draft_content.json" in ds.DRAFT_JSON_NAMES)

shutil.rmtree(empty)
print("\n" + ("FAILED: " + "; ".join(fails) if fails else "all draft-json-name tests passed"))
sys.exit(1 if fails else 0)
