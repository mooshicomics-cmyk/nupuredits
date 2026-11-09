#!/usr/bin/env python3
"""test_store_redirect_media_copy.py — a Store-app PC builds every draft in one folder, and a clip that could not
be copied into the draft is a failed build with the reason, never a quiet success.

A buyer's Windows PC (Claude as a Microsoft Store app) got "save_draft: success" from the editing engine, then
finalize refused: the draft had no assets/video folder at all. The engine's copy of her clip had failed inside
VectCut's save, which only printed it to the server window and still answered success. And the Store-app check
said "redirected: yes" under one Python and "no" under another on the same PC. Checked here, in temp folders:
  1. two separate Python processes on one Store-app PC, one inside the package and one outside it, answer the
     SAME drafts folder (the redirect one of them saw is remembered for the PC); the Store app uninstalled, the
     memory goes and both go back to CapCut's own folder; the folder has one kind of slash;
  2. clip paths are made absolute in the build's own process before VectCut sees them (a relative path, a Git
     Bash /c/... path on Windows), and a clip that is not on this computer fails the call right there;
  3. VectCut's copy of a clip that is not there RAISES with the path (it used to answer False), and its save
     answers success False with "media could not be copied into the draft" and the path; a clip that is there
     still lands in assets/video and the save succeeds;
  4. the builders' finalize turns that failed save into a plain error, removes the unfinished draft-id folder,
     and both builders (Clean Yap and Super Yap) do it right after their save.
No Windows needed: os.name and the folders are stand-ins. Plain python3, no network.
Run: python3 product/tests/test_store_redirect_media_copy.py
"""
import json, os, shutil, subprocess, sys, tempfile, types

for stream in (sys.stdout, sys.stderr):   # ✓ needs UTF-8; a cp1252 Windows console cannot print it
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTCUT = os.path.join(PRODUCT, "engine", "VectCutAPI")
sys.path.insert(0, PRODUCT)

fails = []


def check(ok, what, detail=""):
    print(("  ok   " if ok else "  FAIL ") + what + ("" if ok or not detail else f"   [{str(detail)[:300]}]"))
    if not ok:
        fails.append(what)


tmp = tempfile.mkdtemp(prefix="store-media-copy-")

# ── 1. one drafts folder for every Python on a Store-app PC ─────────────────
# Each "Python" is a real, separate interpreter process. Inside the package, a new folder in AppData lands in
# Packages\<app>\LocalCache\Local (the stand-in makes the probe's folder appear there); outside, it does not.
PROCESS = r'''
import os, sys, uuid
import atexit, datetime, glob, json, shutil, subprocess, time   # loaded as on this machine, before the stand-in
os.name = "nt"                                   # a Windows PC, as far as the engine can tell
sys.path.insert(0, sys.argv[1])
inside = sys.argv[2] == "inside"
la = os.environ["LOCALAPPDATA"]
if inside:
    fixed = uuid.UUID("abcdefabcdefabcdefabcdefabcdefab")
    uuid.uuid4 = lambda: fixed
    os.makedirs(os.path.join(la, "Packages", "Claude_pzs8sxrjxfjjc", "LocalCache", "Local",
                             ".ree-store-probe-" + fixed.hex[:12]), exist_ok=True)
import capcut_store_redirect as store
store.STAGING_DIR = sys.argv[3]
print(store.drafts_root())
'''


def run_python(where, la, local, staging):
    env = dict(os.environ, LOCALAPPDATA=la, REELS_ENGINE_LOCAL=local, PYTHONDONTWRITEBYTECODE="1")
    env.pop("CAPCUT_DRAFTS_ROOT", None)
    r = subprocess.run([sys.executable, "-c", PROCESS, PRODUCT, where, staging], env=env, capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    return (r.stdout.strip().splitlines() or [""])[-1], r.stderr


print("every Python on a Store-app PC builds in the same folder")
la = os.path.join(tmp, "pc", "AppData", "Local")
os.makedirs(os.path.join(la, "Packages", "Claude_pzs8sxrjxfjjc"))
local = os.path.join(tmp, "pc", "engine", "_local")
staging = os.path.join(tmp, "pc", "engine", "projects", "_capcut-staging")
staged = os.path.join(staging, "com.lveditor.draft").replace("\\", "/")
real = os.path.join(la, "CapCut/User Data/Projects/com.lveditor.draft").replace("\\", "/")

out_first, err = run_python("outside", la, local, staging)
check(out_first == real, "before anything has seen the redirect, a Python outside the package uses CapCut's folder",
      out_first + err)
in_root, err = run_python("inside", la, local, staging)
check(in_root == staged, "the Python inside the Store package builds in the staging folder", in_root + err)
out_root, err = run_python("outside", la, local, staging)
check(out_root == in_root == staged, "the Python outside the package now answers the SAME folder (remembered for the PC)",
      f"inside={in_root} outside={out_root} {err}")
pivots = json.load(open(os.path.join(local, "pivots.json"), encoding="utf-8"))
check(pivots.get("windows.store-redirect", {}).get("value") == "Claude_pzs8sxrjxfjjc",
      "the redirect is remembered in the engine's own _local folder, which no package redirects", pivots)
check("\\" not in in_root and "\\" not in out_root, "the drafts folder has one kind of slash", in_root)
again, err = run_python("inside", la, local, staging)
check(again == in_root, "the inside Python still agrees on a later run", again + err)

shutil.rmtree(os.path.join(la, "Packages", "Claude_pzs8sxrjxfjjc"))
gone, err = run_python("outside", la, local, staging)
check(gone == real, "Store app uninstalled: the memory is dropped and drafts go to CapCut's own folder", gone + err)
pivots = json.load(open(os.path.join(local, "pivots.json"), encoding="utf-8"))
check("windows.store-redirect" not in pivots, "and the PC forgets the redirect", pivots)

src = open(os.path.join(PRODUCT, "capcut_store_redirect.py"), encoding="utf-8").read()
check("--recheck" in src.split('if __name__ == "__main__":')[1].split("pkg = detect()")[0],
      "`capcut_store_redirect.py --recheck` forgets the PC's answer on Windows too")
server = open(os.path.join(VECTCUT, "capcut_server.py"), encoding="utf-8").read()
check("capcut_store_redirect.detect()" in server and "_note_store_redirect()\n    app.run" in server,
      "the editing engine (VectCut) runs the same check in its own process when it starts")

# ── 2. clip paths the editing engine can find ────────────────────────────────
print("\nclip paths are made absolute in the build's own process")
import vectcut_engine as VE

real_os_name, real_cwd = os.name, os.getcwd()
job = os.path.join(tmp, "engine")
clip_dir = os.path.join(job, "footage", "raw")
os.makedirs(clip_dir)
clip = os.path.join(clip_dir, "take.mp4")
open(clip, "wb").write(b"\0" * 64)
try:
    os.chdir(job)
    rel = "footage/raw/take.mp4"
    check(VE.local_media_path(rel) == os.path.abspath(rel), "a relative clip path is read from the build's folder",
          VE.local_media_path(rel))
    check(VE.local_media_path(clip) == clip, "an absolute path is left exactly as it is")
    for keep in ("https://example.com/a.mp4", "##_draftpath_placeholder_x_##/a.mp4", "", None):
        check(VE.local_media_path(keep) == keep, f"left alone: {keep!r}")
    os.name = "nt"
    check(VE.local_media_path("/c/Users/USERNAME/raw/take.mp4") == "C:/Users/USERNAME/raw/take.mp4",
          "Windows: a Git Bash /c/... path becomes C:/...", VE.local_media_path("/c/Users/USERNAME/raw/take.mp4"))
    check(VE.local_media_path("/cygdrive/d/clips/a.mp4") == "D:/clips/a.mp4", "Windows: /cygdrive/d/... becomes D:/...")
    os.name = real_os_name
    check(VE.local_media_path("/c/Users/USERNAME/x.mp4") == "/c/Users/USERNAME/x.mp4", "a Mac path that looks like /c/... is untouched")

    sent = []

    class FakeRequests:
        class exceptions:
            class RequestException(Exception):
                pass

            class ConnectionError(RequestException):
                pass

            class Timeout(RequestException):
                pass

        @staticmethod
        def post(url, json=None, timeout=None):
            sent.append((url, json))
            return types.SimpleNamespace(status_code=200, json=lambda: {"success": True, "output": {}}, text="")

    real_http, real_state = VE._http, dict(VE._STATE)
    VE._http = lambda: FakeRequests
    VE._STATE.update(checked=True, reached=False)
    try:
        j = VE.post("http://127.0.0.1:9001", "add_video", {"draft_id": "d", "video_url": rel, "start": 0})
        check(j.get("success") and sent and sent[-1][1]["video_url"] == os.path.abspath(rel),
              "the editing engine is sent the absolute path, so its copy finds the clip", sent[-1:] or j)
        n = len(sent)
        j = VE.post("http://127.0.0.1:9001", "add_video", {"draft_id": "d", "video_url": "footage/raw/gone.mp4"})
        check(not j.get("success") and "no file at" in j.get("error", "") and len(sent) == n,
              "a clip that is not on this computer fails the call right there (nothing is sent)", j)
        j = VE.post("http://127.0.0.1:9001", "add_audio", {"draft_id": "d", "audio_url": "https://example.com/a.mp3"})
        check(j.get("success") and sent[-1][1]["audio_url"] == "https://example.com/a.mp3", "a URL is sent as given")
    finally:
        VE._http = real_http
        VE._STATE.clear(); VE._STATE.update(real_state)
finally:
    os.name = real_os_name
    os.chdir(real_cwd)

# ── 3. VectCut's copy and save say when a clip did not go in ─────────────────
print("\nthe editing engine's save fails, with the reason, when a clip cannot be copied in")
for name in ("requests", "requests.exceptions", "imageio", "imageio.v2", "pyJianYingDraft", "draft_cache"):
    try:
        __import__(name)
    except Exception:                       # plain python3 has none of VectCut's packages: stand-ins, import only
        m = types.ModuleType(name)
        if name == "requests.exceptions":
            m.RequestException = type("RequestException", (Exception,), {})
            m.Timeout = type("Timeout", (m.RequestException,), {})
            sys.modules["requests"].exceptions = m
        if name == "draft_cache":
            m.DRAFT_CACHE = {}
        sys.modules[name] = m
        if name == "imageio.v2":
            sys.modules["imageio"].v2 = m
sys.path.insert(0, VECTCUT)
import logging
import downloader
import save_draft_impl as SD
downloader.print = lambda *a, **k: None                       # its progress lines are the server window's, not ours
logging.getLogger("flask_video_generator").disabled = True    # and so are its logged tracebacks

dest = os.path.join(tmp, "dl", "assets", "video", "video_x.mp4")
try:
    downloader.download_file(os.path.join(tmp, "nowhere", "take.mp4"), dest)
    raised = None
except Exception as e:
    raised = e
check(isinstance(raised, FileNotFoundError) and "nowhere" in str(raised),
      "copying a clip that is not there raises with the path (it used to answer False)", repr(raised))
check(downloader.download_file(clip, dest) is True and os.path.isfile(dest), "a clip that is there is copied in")

SD.update_media_metadata = lambda script, task_id=None: None   # ffprobe of the stand-in clips is not the point


def fake_draft(paths):
    vids = [types.SimpleNamespace(remote_url=p, material_name=f"video_{i}.mp4", material_type="video",
                                  replace_path=None) for i, p in enumerate(paths)]
    return types.SimpleNamespace(materials=types.SimpleNamespace(audios=[], videos=vids),
                                 dumps=lambda profile=None: json.dumps({"materials": {}, "tracks": []}))


drafts = os.path.join(tmp, "engine", "projects", "_capcut-staging", "com.lveditor.draft").replace("\\", "/")
os.makedirs(drafts)
missing = os.path.join(tmp, "elsewhere", "take.mp4")
SD.DRAFT_CACHE["dfd_bad"] = fake_draft([clip, missing])
res = SD.save_draft_impl("dfd_bad", drafts)
err = str(res.get("error", ""))
check(res.get("success") is False, "a save with a clip it could not copy answers success False", res)
check(VE.MEDIA_COPY_FAILED in err and SD.MEDIA_COPY_FAILED == VE.MEDIA_COPY_FAILED,
      "with the words the builders look for", err)
check(missing in err and "video_1.mp4" in err and "FileNotFoundError" in err, "and which clip, from where, and why",
      err)
check(SD.get_task_status("dfd_bad").get("status") == "failed", "its progress record says failed (a slow save "
      "followed through /query_draft_status sees it too)")

SD.DRAFT_CACHE["dfd_good"] = fake_draft([clip])
res = SD.save_draft_impl("dfd_good", drafts)
check(res.get("success") is True and os.path.isfile(os.path.join(drafts, "dfd_good", "assets", "video", "video_0.mp4")),
      "a save whose clips are all there still succeeds, with the clip in assets/video", res)
check("draft_result.get(\"success\") is False" in server and "result[\"error\"] = draft_result.get(\"error\")" in server,
      "the /save_draft route passes the failure on instead of answering success")

# ── 4. finalize turns it into a plain error ──────────────────────────────────
print("\nfinalize stops on a clip that did not go in, says why, and leaves nothing half-built")
bad_dir = os.path.join(drafts, "dfd_bad")
check(os.path.isdir(bad_dir), "(the failed save left its draft-id folder behind)")
real_note = VE.note
VE.note = lambda *a, **k: None
try:
    try:
        VE.refuse_failed_media(SD.save_draft_impl("dfd_bad", drafts), bad_dir)
        msg = None
    except RuntimeError as e:
        msg = str(e)
    check(msg is not None and missing in msg and "could not copy a clip" in msg,
          "a failed copy is a RuntimeError naming the clip", msg)
    check(not os.path.exists(bad_dir), "the unfinished draft-id folder is removed (it was never hers)")
    good_dir = os.path.join(drafts, "dfd_good")
    VE.refuse_failed_media({"success": True, "output": {}}, good_dir)
    VE.refuse_failed_media({"success": False, "error": "Draft x does not exist in cache"}, good_dir)
    check(os.path.isdir(good_dir), "a clean save, or a different failure, is left to finalize's own checks")
finally:
    VE.note = real_note

for builder in ("cleanyap.py", "superyap.py"):
    s = open(os.path.join(PRODUCT, builder), encoding="utf-8").read()
    i = s.find('_saved = call("save_draft"')
    check(i > 0 and "vectcut_engine.refuse_failed_media(_saved, os.path.join(CAP, did))" in s[i:i + 400],
          f"{builder}: finalize checks the save right after it")

shutil.rmtree(tmp, ignore_errors=True)
if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\n✓ store-app media copy: one drafts folder for every Python, absolute clip paths, a failed copy is said")
