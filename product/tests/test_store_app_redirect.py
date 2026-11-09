#!/usr/bin/env python3
"""test_store_app_redirect.py — drafts still reach CapCut when Claude is a Microsoft Store (MSIX) app.

A Store app's new files under %LOCALAPPDATA% land in Packages\\<app>\\LocalCache\\Local instead, where CapCut
never looks, so a draft the engine "wrote into CapCut" was invisible. Checked here, in temp folders only:
  1. the probe recognises the redirect (and stays quiet when there is none, and off Windows);
  2. while redirected, every draft writer's root is the engine's staging folder, with the installer beside it;
  3. the installer copies a staged draft into CapCut, rewrites its paths (forward-slash AND JSON-escaped
     backslash forms), registers it at the top of CapCut's list, backs the list up, and a second run is a no-op;
  4. it never replaces a project she changed in CapCut, refuses while CapCut is open, and refuses when started
     from inside the Store app;
  5. the engine runs it for her (a one-time request + Explorer): a clean result is one line and no double-click;
     a refusal, CapCut open, no answer, a copy that never finishes, or a crashed build all fall back to the
     double-click instructions and the folder. Explorer itself is a stand-in here (unverified on a real PC).
Run: python3 product/tests/test_store_app_redirect.py
"""
import importlib, io, json, os, shutil, sys, tempfile, uuid, contextlib

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import capcut_store_redirect as store
import install_to_capcut as inst

fails = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        fails.append(what)


tmp = tempfile.mkdtemp(prefix="store-redirect-")
real_name, real_uuid = os.name, uuid.uuid4
env_before = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "CAPCUT_DRAFTS_ROOT", "REELS_ENGINE_LOCAL",
                                             "REE_AUTO_ADD")}
os.environ["REELS_ENGINE_LOCAL"] = os.path.join(tmp, "_local")
real_open_folder = store.open_folder
try:
    la = os.path.join(tmp, "AppData", "Local")
    os.makedirs(la)
    os.environ["LOCALAPPDATA"] = la
    os.environ.pop("CAPCUT_DRAFTS_ROOT", None)
    fixed = uuid.UUID("12345678123456781234567812345678")
    uuid.uuid4 = lambda: fixed
    probe = f".ree-store-probe-{fixed.hex[:12]}"

    # ── 1. detection ─────────────────────────────────────────────────────────
    print("the probe tells a redirected Store app from a normal one")
    os.name = "posix"
    store._cache.clear()
    check(store.detect() is None, "off Windows there is never a redirect")
    os.name = "nt"
    store._cache.clear()
    check(store.detect() is None, "a normal Windows install is not redirected")
    os.makedirs(os.path.join(la, "Packages", "Claude_pzs8sxrjxfjjc", "LocalCache", "Local", probe))
    store._cache.clear()
    check(store.detect() == "Claude_pzs8sxrjxfjjc", "a write that lands in Packages\\<app>\\LocalCache is caught")
    check(not os.path.exists(os.path.join(la, probe)), "the probe cleans up after itself")

    # ── 2. the root every writer uses ────────────────────────────────────────
    print("\nwhile redirected, drafts build in the staging folder")
    store.STAGING_DIR = os.path.join(tmp, "engine", "projects", "_capcut-staging")
    root = store.drafts_root()
    check(root == store.staging_root() and store.is_staging(root), "drafts_root() is the staging folder")
    check(os.path.isfile(os.path.join(store.STAGING_DIR, store.BAT_NAME)), "the double-click installer is there")
    check(os.path.isfile(os.path.join(store.STAGING_DIR, "install_to_capcut.py")), "its script is beside it")
    bat = open(os.path.join(store.STAGING_DIR, store.BAT_NAME), "rb").read()
    check(b"\r\n" in bat and b"install_to_capcut.py" in bat, "the .bat has Windows line endings and runs the script")
    os.environ["CAPCUT_DRAFTS_ROOT"] = os.path.join(tmp, "forced")
    check(store.drafts_root() == os.path.join(tmp, "forced"), "CAPCUT_DRAFTS_ROOT still wins")
    os.environ.pop("CAPCUT_DRAFTS_ROOT")
    check("com.lveditor.draft" in store.handoff_lines("My Reel")[3] or
          store.BAT_NAME in "".join(store.handoff_lines("My Reel")), "the handoff names the one thing to do")

    # ── 3. the installer ─────────────────────────────────────────────────────
    print("\nthe installer brings a staged draft into CapCut")
    stage = os.path.join(store.STAGING_DIR, "com.lveditor.draft")
    inst.STAGE = stage
    d = os.path.join(stage, "My Reel 1.0")
    os.makedirs(os.path.join(d, "assets"))
    fwd = os.path.abspath(stage).replace("\\", "/")
    esc = os.path.abspath(stage).replace("/", "\\").replace("\\", "\\\\")
    content = {"materials": {"videos": [{"path": f"{fwd}/My Reel 1.0/assets/cut.mp4"},
                                         {"path": f"{esc}\\\\My Reel 1.0\\\\assets\\\\cover.png"}]}}
    raw = json.dumps(content).replace("\\\\\\\\", "\\\\")    # keep the escaped form exactly as CapCut writes it
    open(os.path.join(d, "draft_content.json"), "w", encoding="utf-8").write(raw)
    json.dump({"draft_fold_path": f"{fwd}/My Reel 1.0", "draft_root_path": fwd},
              open(os.path.join(d, "draft_meta_info.json"), "w", encoding="utf-8"))
    json.dump({"all_draft_store": [{"draft_name": "My Reel 1.0", "draft_fold_path": f"{fwd}/My Reel 1.0",
                                    "draft_root_path": fwd, "draft_json_file": f"{fwd}/My Reel 1.0/draft_content.json",
                                    "draft_cover": f"{fwd}/My Reel 1.0/draft_cover.jpg", "tm_draft_create": 1}]},
              open(os.path.join(stage, "root_meta_info.json"), "w", encoding="utf-8"))
    real = os.path.join(la, inst.REL)
    os.makedirs(real)
    json.dump({"all_draft_store": [{"draft_name": "Her Old Project"}], "draft_ids": 1, "root_path": real},
              open(os.path.join(real, "root_meta_info.json"), "w", encoding="utf-8"))

    inst.capcut_running = lambda: False
    inst.inside_store_app = lambda: False

    def run():
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out):
            try:
                inst.main()
            except SystemExit as e:
                code = e.code
        return out.getvalue(), code

    out, code = run()
    dst = os.path.join(real, "My Reel 1.0")
    check(os.path.isdir(dst) and "added" in out, "the draft is copied into CapCut's own folder")
    txt = open(os.path.join(dst, "draft_content.json"), encoding="utf-8").read()
    rfwd = os.path.abspath(real).replace("\\", "/")
    check("_capcut-staging" not in txt, "no path inside the draft still points at the staging folder")
    check(rfwd in txt, "forward-slash paths now point into CapCut's folder")
    check(os.path.abspath(real).replace("/", "\\").replace("\\", "\\\\") in txt,
          "JSON-escaped backslash paths now point into CapCut's folder")
    meta = json.load(open(os.path.join(dst, "draft_meta_info.json"), encoding="utf-8"))
    check(meta["draft_fold_path"] == f"{rfwd}/My Reel 1.0", "draft_meta_info's own folder path is rewritten")
    reg = json.load(open(os.path.join(real, "root_meta_info.json"), encoding="utf-8"))
    names = [e["draft_name"] for e in reg["all_draft_store"]]
    check(names == ["My Reel 1.0", "Her Old Project"], "registered at the top, her other projects kept")
    check(reg["all_draft_store"][0]["draft_fold_path"] == f"{rfwd}/My Reel 1.0", "the list entry points at CapCut")
    check(any(f.startswith("root_meta_info.json.before-engine-") for f in os.listdir(real)),
          "CapCut's list was backed up before it changed")

    out2, _ = run()
    check("already in CapCut" in out2, "running it again changes nothing")

    print("\nher work in CapCut always wins")
    with open(os.path.join(dst, "draft_content.json"), "a", encoding="utf-8") as fh:
        fh.write(" ")                                       # she edited it in CapCut
    with open(os.path.join(d, "draft_content.json"), "a", encoding="utf-8") as fh:
        fh.write("  ")                                      # and the engine rebuilt the staged copy
    out3, _ = run()
    check("kept" in out3 and open(os.path.join(dst, "draft_content.json"), encoding="utf-8").read().endswith(" "),
          "a project she changed in CapCut is kept, not replaced")
    os.makedirs(os.path.join(stage, "Same Name"))
    open(os.path.join(stage, "Same Name", "draft_content.json"), "w", encoding="utf-8").write("{}")
    os.makedirs(os.path.join(real, "Same Name"))
    open(os.path.join(real, "Same Name", "draft_content.json"), "w", encoding="utf-8").write('{"hers": 1}')
    run()
    check(json.load(open(os.path.join(real, "Same Name", "draft_content.json"), encoding="utf-8")) == {"hers": 1},
          "a project of hers with the same name is never touched")

    inst.capcut_running = lambda: True
    out4, code4 = run()
    check(code4 and "Close CapCut" in str(code4), "it refuses while CapCut is open")
    inst.capcut_running = lambda: None
    _, code5 = run()
    check(bool(code5), "it refuses when it cannot tell whether CapCut is open")
    inst.capcut_running = lambda: False
    inst.inside_store_app = lambda: True
    _, code6 = run()
    check(code6 and "File Explorer" in str(code6), "it refuses when started from inside the Store app")
    inst.inside_store_app = lambda: False

    # ── 5. the engine runs "Add to CapCut" itself ────────────────────────────
    print("\nafter a build, the engine adds it to CapCut itself, and falls back to the double-click")
    uuid.uuid4 = real_uuid                                  # every request gets its own token again
    bat = open(os.path.join(store.STAGING_DIR, store.BAT_NAME), encoding="ascii").read()
    check("install_to_capcut.py %*" in bat, "the .bat passes its arguments through to the script")
    check(bat.index('"%ERRORLEVEL%"=="75"') < bat.index("pause"),
          "an automatic run (exit 75) closes the window before the 'press a key' pause")
    req_path = os.path.join(store.STAGING_DIR, inst.AUTO_REQUEST)
    res_path = os.path.join(store.STAGING_DIR, inst.AUTO_RESULT)

    def stage_draft(name):
        dd = os.path.join(stage, name)
        os.makedirs(dd)
        open(os.path.join(dd, "draft_content.json"), "w", encoding="utf-8").write('{"tracks": []}')

    launched = []

    def explorer(p):                         # stands in for explorer.exe: the shell runs the .bat, no arguments
        launched.append(p)
        with contextlib.redirect_stdout(io.StringIO()):
            launched.append(inst.run([]))

    ticks = [0.0]

    def clock():
        ticks[0] += 1.0
        return ticks[0]

    quick = dict(sleep=lambda s: None, clock=clock)
    opened = []
    store.open_folder = lambda force=False: opened.append(1)

    def handoff(name, **kw):
        store._pending[:] = [name]
        store._cache.pop("crashed", None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            store.finish_handoff(**dict(quick, **kw))
        return out.getvalue()

    stage_draft("Auto Reel 1.0")
    del opened[:]
    said = handoff("Auto Reel 1.0", launch=explorer, running=lambda: False)
    check(launched and launched[0].endswith(store.BAT_NAME), "the .bat is handed to Explorer")
    check(launched[-1] == inst.AUTO_EXIT, "the automatic run exits 75 (no pause)")
    check(os.path.isdir(os.path.join(real, "Auto Reel 1.0")), "the draft is in CapCut's own folder")
    check(store.AUTO_DONE_LINE in said and "double-click" not in said and not opened,
          "she reads one line, 'It's in CapCut', with no double-click and no folder")
    check(json.load(open(os.path.join(real, "root_meta_info.json"), encoding="utf-8"))["all_draft_store"][0]
          ["draft_name"] == "Auto Reel 1.0", "it is at the top of CapCut's list")
    check(any(f.startswith("root_meta_info.json.before-engine-") for f in os.listdir(real)),
          "CapCut's list was still backed up first")
    check(not os.path.exists(req_path), "the one-time request is used up")
    check(json.load(open(res_path, encoding="utf-8"))["status"] == "done", "the result file says done")

    print("\n  ...and every way it can not finish ends on the double-click, never a dead end")
    stage_draft("Auto Reel 1.1")

    def falls_back(said, what):
        check(store.AUTO_DONE_LINE not in said and store.BAT_NAME in said and opened,
              f"{what}: the double-click instructions and the folder, as before")

    inst.inside_store_app = lambda: True
    del launched[:], opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=explorer, running=lambda: False),
               "the script finds itself inside the Store package")
    check(json.load(open(res_path, encoding="utf-8")).get("reason") == "inside-package",
          "the result file names why it refused")
    inst.inside_store_app = lambda: False

    del launched[:], opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=explorer, running=lambda: True), "CapCut is open")
    check(not launched, "with CapCut open nothing is started at all")
    del launched[:], opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=explorer, running=lambda: None), "CapCut's state is unknown")
    check(not launched, "and with CapCut's state unknown nothing is started either")

    inst.capcut_running = lambda: True                     # closed when the engine looked, open by the copy
    inst.stuck_capcut = lambda: False
    del launched[:], opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=explorer, running=lambda: False), "CapCut opened in between")
    check(not os.path.exists(os.path.join(real, "Auto Reel 1.1")), "and nothing was copied")
    inst.capcut_running = lambda: False

    del opened[:]
    ticks[0] = 0.0
    falls_back(handoff("Auto Reel 1.1", launch=lambda p: None, running=lambda: False),
               "Explorer never started it (timeout)")
    check(not os.path.exists(req_path), "the unanswered request is removed, so a later double-click pauses")

    def starts_never_ends(p):
        inst._write_json(res_path, {"token": inst.load(req_path, {})["token"], "status": "running"})

    del opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=starts_never_ends, running=lambda: False),
               "a copy that never finishes")

    def no_explorer(p):
        raise FileNotFoundError("explorer.exe")

    del opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=no_explorer, running=lambda: False), "Explorer cannot be started")

    del launched[:], opened[:]
    store._pending[:] = ["Auto Reel 1.1"]
    store._cache["crashed"] = True
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        store.finish_handoff(launch=explorer, running=lambda: False, **quick)
    falls_back(out.getvalue(), "a build that crashed")
    check(not launched, "a crashed build starts nothing automatically")
    store._cache.pop("crashed", None)

    os.environ["REE_AUTO_ADD"] = "0"
    del launched[:], opened[:]
    falls_back(handoff("Auto Reel 1.1", launch=explorer, running=lambda: False), "REE_AUTO_ADD=0")
    check(not launched, "REE_AUTO_ADD=0 turns the automatic step off")
    os.environ.pop("REE_AUTO_ADD")

    del opened[:]
    said = handoff("Auto Reel 1.1", launch=explorer, running=lambda: False)
    check(store.AUTO_DONE_LINE in said and os.path.isdir(os.path.join(real, "Auto Reel 1.1")),
          "once nothing is in the way, the next build goes straight in")

    print("\n  ...and her own double-click is unchanged")
    inst._write_json(req_path, {"token": "old", "at": 0})
    with contextlib.redirect_stdout(io.StringIO()):
        code_manual = inst.run([])
    check(code_manual == 0, "a leftover request (minutes old) is ignored: her double-click pauses as always")
    check(not os.path.exists(req_path), "and the leftover is cleared")
    open(os.path.join(store.STAGING_DIR, inst.LOCK), "w", encoding="utf-8").write("4242")
    inst._pid_alive = lambda pid: True
    _, code_busy = run()
    check(code_busy and "already running" in str(code_busy), "two copies at once: the second waits its turn")
    inst._pid_alive = lambda pid: False
    _, code_left = run()
    check(not code_left, "a lock left by a closed window is taken over at once")
    check(not os.path.exists(os.path.join(store.STAGING_DIR, inst.LOCK)), "and the lock is released after")

    print("\n  ...and the handoff waits for the build to end, so every write is done before the copy")
    hook_before = sys.excepthook
    store._cache.pop("atexit", None)
    del store._pending[:], opened[:]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        store.after_build("Later Reel 1.0")
    check(out.getvalue() == "" and store._pending == ["Later Reel 1.0"] and store._cache.get("atexit"),
          "on Windows register_draft only queues it; the handoff runs when the build process ends")
    del store._pending[:]
    sys.excepthook = hook_before
    os.name = "posix"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        store.after_build("Mac Reel 1.0")
    os.name = "nt"
    check(store.COMMAND_NAME in out.getvalue() and not store._pending, "on a Mac the double-click shows right away")
    cm = open(os.path.join(PRODUCT, "capcut_media.py"), encoding="utf-8").read()
    check("_store.after_build(name)" in cm, "register_draft, the one chokepoint, hands every staged draft over")

    fin = open(os.path.join(PRODUCT, "finish.py"), encoding="utf-8").read()
    check("AUTO_DONE_LINE not in out" in fin, "the editor's Finish tab shows 'In CapCut' when the engine added it")
finally:
    store.open_folder = real_open_folder
    os.name = real_name
    uuid.uuid4 = real_uuid
    for k, v in env_before.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\n✓ store-app redirect: detected, drafts staged, installed into CapCut with her work protected")
