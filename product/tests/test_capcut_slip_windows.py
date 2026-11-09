#!/usr/bin/env python3
"""test_capcut_slip_windows.py — the slip-reel hand-over on a PC, and on a CapCut with no drafts yet.

Two ways the compound (slip) draft used to come out broken, both silently:
  1. On Windows the editing engine writes media paths with backslashes. The path tokeniser only looked for
     "/assets/", so it rewrote none of them; the draft folder was then renamed, and every clip kept pointing
     into the folder that no longer existed (red "media not found" clips).
  2. Its own registry writer quietly did nothing when CapCut's list was empty, so the draft was invisible and
     the next step stopped on "not in CapCut's index". It now registers through capcut_media.register_draft,
     the writer every builder uses.
Temp folders only; the real CapCut list and pin file are never touched.
Run: python3 product/tests/test_capcut_slip_windows.py
"""
import copy, importlib.util, json, os, sys, tempfile, types

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import capcut_compound as cc

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


# 1) a draft exactly as the editing engine saves it on Windows
WIN = r"C:\Users\your-name\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\dfd_cat_1790000000_x"
MAC = "/Users/your-name/Movies/CapCut/User Data/Projects/com.lveditor.draft/dfd_cat_1790000000_x"
draft = {"materials": {
    "videos": [{"id": "V1", "path": WIN + r"\assets\video\beat1.mp4", "media_path": WIN + r"\assets\video\beat1.mp4"},
               {"id": "V2", "path": MAC + "/assets/video/beat2.mp4", "media_path": ""}],
    "audios": [{"id": "A1", "path": WIN + r"\assets\audio\vo.wav"}],
    "drafts": [{"draft": {"materials": {"videos": [{"path": WIN + r"\assets\video\beat1.mp4"}]}}}]}}
before = copy.deepcopy(draft)
n = cc.tokenise_paths(draft)
paths = [draft["materials"]["videos"][0]["path"], draft["materials"]["videos"][0]["media_path"],
         draft["materials"]["videos"][1]["path"], draft["materials"]["audios"][0]["path"],
         draft["materials"]["drafts"][0]["draft"]["materials"]["videos"][0]["path"]]
check(n == 5, f"expected 5 paths tokenised (Windows and Mac alike), got {n}")
check(all(p.startswith(cc.PATH_TOKEN + "/assets/") for p in paths), f"paths not all tokenised: {paths}")
check(not any("dfd_" in p or "\\" in p for p in paths), f"a path still names the old folder or a backslash: {paths}")
check(paths[0] == cc.PATH_TOKEN + "/assets/video/beat1.mp4", f"Windows path tokenised wrong: {paths[0]}")
check(draft["materials"]["videos"][1]["media_path"] == "", "an empty path must stay empty")

# 2) registering into a CapCut whose list is empty
tmp = tempfile.mkdtemp(prefix="slip-register-")
import capcut_front, capcut_media
capcut_front.CAP = tmp
capcut_front.META = os.path.join(tmp, "root_meta_info.json")
capcut_front.STATE_DIR = tmp
capcut_front.STATE = os.path.join(tmp, "capcut-front.json")
capcut_front.capcut_running = lambda: False
sys.modules.setdefault("requests", types.ModuleType("requests"))   # only VectCut calls use it; none here
spec = importlib.util.spec_from_file_location("slip_reel", os.path.join(PRODUCT, "capcut-slip-reel.py"))
slip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slip)
slip.CAP = tmp
with open(capcut_front.META, "w", encoding="utf-8") as fh:
    json.dump({"all_draft_store": [], "draft_ids": 0, "root_path": tmp}, fh)
dst = os.path.join(tmp, "Slip Reel 1.1")
os.makedirs(dst)
with open(os.path.join(dst, "draft_meta_info.json"), "w", encoding="utf-8") as fh:
    json.dump({"draft_id": "META-ID"}, fh)
try:
    slip.register(dst, "Slip Reel 1.1", {"duration": 4_000_000})
    store = json.load(open(capcut_front.META, encoding="utf-8"))["all_draft_store"]
    row = next((e for e in store if e.get("draft_name") == "Slip Reel 1.1"), None)
    check(row is not None, "a draft registered into an empty list did not land in it")
    meta_now = json.load(open(os.path.join(dst, "draft_meta_info.json"), encoding="utf-8"))
    # a FRESH id per draft (the template's fixed one made a newer version vanish from CapCut's grid), the same in
    # the draft's own meta and in the list
    check(row and row.get("draft_id") not in (None, "", "META-ID") and row.get("draft_id") == meta_now.get("draft_id")
          and row.get("tm_duration") == 4_000_000, f"registry row carries the wrong id or length: {row}")
    capcut_front.to_front("Slip Reel 1.1", quiet=False)   # what the slip reel does next; used to stop here
except SystemExit as e:
    check(False, f"the hand-over stopped: {e}")
except TypeError as e:
    check(False, f"register() has the old signature: {e}")

if failures:
    print("✗ slip reel on Windows: " + "; ".join(failures))
    sys.exit(1)
print("✓ slip reel on Windows: backslash media paths are written as CapCut's own token, and a draft built into "
      "an empty CapCut list is registered and found")
