#!/usr/bin/env python3
"""test_mac_movies_blocked.py — a Mac that refuses the engine's Python any write in ~/Movies still gets its draft.

On one buyer's Mac a security app's protected-folders shield refused the engine's own Python every write in
~/Movies (where CapCut keeps its projects) while Apple's /bin/mkdir, /bin/cp and ffmpeg wrote there fine. VectCut's
save failed, then finalize ended on a bare FileNotFoundError: a dead end with a confusing error. Checked here, in
a temp HOME with the refusal simulated (nothing real is touched, never her CapCut folder):
  1. the probe: allowed = nothing changes (CapCut's own folder, nothing remembered, no probe left behind);
     refused = drafts build in the staging folder with "Add to CapCut.command" beside it, remembered for this
     Mac and noted for /report-a-problem; allowed again later = forgotten, back to CapCut's own folder;
  2. every draft writer agrees: draft_safety.CAP and capcut_front.CAP are the staging folder too;
  3. a refused VectCut save ends on plain words in BOTH builders' finalize, not a FileNotFoundError, and is
     remembered so the next build takes the staging route even when this Python's own probe passes;
  4. (Mac only) the .command adds a staged project to CapCut: paths rewritten, listed at the top, list backed
     up, a taken name goes in as the next version with hers untouched, a second run changes nothing, a project
     dropped from the list is listed again, and it refuses while CapCut is open;
  5. a draft she ALREADY has is still found on a blocked Mac (CapCut's folder is read), a tool that changes it
     works on a copy in staging (made by itself for CAPCUT_DRAFT tools), and the .command brings the change in
     as a NEW version with hers untouched; a copy that was only read or never changed is not brought in;
  6. the probe only ever makes one hidden folder directly in ~/Movies (never inside CapCut's folder), and the
     engine's own tests on the real home never probe at all;
  7. /report-a-problem asks the Mac question too: the script's own answer line, and scripts/collect-report.sh
     running it on a Mac (not only on Windows) with the staging folder among the Mac draft folders.
Run: python3 product/tests/test_mac_movies_blocked.py
"""
import contextlib, errno, io, json, os, shutil, subprocess, sys, tempfile, types

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="mac-movies-blocked-")
HOME = os.path.join(TMP, "home")
LOCAL = os.path.join(TMP, "local")
os.makedirs(HOME)
saved_env = {k: os.environ.get(k) for k in ("HOME", "REELS_ENGINE_LOCAL", "CAPCUT_DRAFTS_ROOT", "LOCALAPPDATA")}
os.environ["HOME"] = HOME
os.environ["REELS_ENGINE_LOCAL"] = LOCAL
os.environ.pop("CAPCUT_DRAFTS_ROOT", None)
os.environ["LOCALAPPDATA"] = os.path.join(HOME, "AppData", "Local")
sys.path.insert(0, PRODUCT)
real_platform = sys.platform
sys.platform = "darwin"                      # the route is a Mac route; the decision code runs anywhere

import capcut_store_redirect as store       # noqa: E402
import fallbacks                             # noqa: E402

fails = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        fails.append(what)


REAL = store.mac_real_root()
MOVIES = os.path.join(HOME, "Movies")
store.STAGING_DIR = os.path.join(TMP, "engine", "projects", "_capcut-staging")
real_mkdir = os.mkdir


def shield(path, *a, **k):
    """What the buyer's security app did: the engine's Python may not create anything under ~/Movies."""
    if os.path.abspath(path).startswith(MOVIES + os.sep):
        raise PermissionError(errno.EPERM, "Operation not permitted", path)
    return real_mkdir(path, *a, **k)


def fresh():
    store._cache.clear()


try:
    os.makedirs(REAL)

    # ── 1. the probe ─────────────────────────────────────────────────────────────────────────────────────────
    print("allowed: nothing changes")
    made = []

    def recorder(path, *a, **k):
        made.append(os.path.abspath(path))
        return real_mkdir(path, *a, **k)

    os.mkdir = recorder
    fresh()
    check(store.drafts_root() == REAL, "drafts go straight into CapCut's own folder")
    os.mkdir = real_mkdir
    check(len(made) == 1 and os.path.dirname(made[0]) == MOVIES and os.path.basename(made[0]).startswith("."),
          "the probe makes one hidden folder directly in ~/Movies, nothing inside CapCut's folder")
    check(not [n for n in os.listdir(MOVIES) if n.startswith(".ree-")], "and removes it")
    import pwd
    os.environ["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
    made.clear()
    os.mkdir = recorder
    fresh()
    probed = store.mac_probe()
    os.mkdir = real_mkdir
    os.environ["HOME"] = HOME
    check(probed is False and not made, "an engine test on the real home never probes it")
    check(fallbacks.remembered(store.MAC_KEY) is None, "nothing is remembered")
    check(not [n for n in os.listdir(REAL) if n.startswith(".ree-")], "the probe leaves nothing behind")
    check(not os.path.exists(store.STAGING_DIR), "no staging folder is made")

    print("\nrefused: the staging route, remembered and noted")
    os.mkdir = shield
    fresh()
    root = store.drafts_root()
    os.mkdir = real_mkdir
    check(root == store.staging_root() and store.is_staging(root), "drafts build in the staging folder")
    cmd = os.path.join(store.STAGING_DIR, store.COMMAND_NAME)
    check(os.path.isfile(cmd) and os.access(cmd, os.X_OK), "\"Add to CapCut.command\" is there and runnable")
    for f in ("add_to_capcut_mac.py", "install_to_capcut.py"):
        check(os.path.isfile(os.path.join(store.STAGING_DIR, f)), f"{f} is beside it")
    body = open(cmd, "rb").read()
    check(b"\r\n" not in body and body.startswith(b"#!/bin/bash"), "the .command is a Unix shell script")
    check(b"/bin/mv " in body and b"/bin/cp " in body, "Apple's own /bin/mv and /bin/cp do the writing")
    check(b"rm " not in body, "it never deletes anything")
    check(not os.path.exists(os.path.join(store.STAGING_DIR, store.BAT_NAME)), "no Windows .bat on a Mac")
    check(fallbacks.remembered(store.MAC_KEY) == "probe", "remembered for this Mac")
    log = open(fallbacks.log_path(), encoding="utf-8").read()
    check("capcut-drafts:" in log and "Operation not permitted" in log, "one line for /report-a-problem")
    lines = store.handoff_lines("My Reel 1.1")
    check(any(store.COMMAND_NAME in ln for ln in lines) and any("Quit CapCut" in ln for ln in lines),
          "the handoff names the one double-click")
    check(not any("⚠" in ln for ln in lines), "no alarm symbol for a route that worked")
    os.mkdir = shield
    fresh()
    store.drafts_root()
    os.mkdir = real_mkdir
    check(open(fallbacks.log_path(), encoding="utf-8").read().count("refused the engine's Python") == 1,
          "a second run does not log it again")

    print("\nallowed again: back to CapCut's own folder")
    fresh()
    check(store.drafts_root() == REAL, "drafts go straight into CapCut's folder again")
    check(fallbacks.remembered(store.MAC_KEY) is None, "the memory is forgotten")

    # ── 2. every draft writer agrees ─────────────────────────────────────────────────────────────────────────
    print("\nevery draft writer takes the same answer")
    probe_code = (
        "import errno, os, sys\n"
        f"sys.path.insert(0, {PRODUCT!r})\n"
        "sys.platform = 'darwin'\n"
        "m = os.path.join(os.environ['HOME'], 'Movies') + os.sep\n"
        "real = os.mkdir\n"
        "def shield(p, *a, **k):\n"
        "    if os.path.abspath(p).startswith(m):\n"
        "        raise PermissionError(errno.EPERM, 'Operation not permitted', p)\n"
        "    return real(p, *a, **k)\n"
        "os.mkdir = shield\n"
        "import capcut_store_redirect as s\n"
        f"s.STAGING_DIR = {store.STAGING_DIR!r}\n"
        "import draft_safety, capcut_front\n"
        "print(draft_safety.CAP == s.staging_root() and capcut_front.CAP == s.staging_root())\n")
    r = subprocess.run([sys.executable, "-c", probe_code], capture_output=True, text=True, env=dict(os.environ))
    check(r.stdout.strip().endswith("True"), "draft_safety.CAP and capcut_front.CAP are the staging folder "
          + (r.stderr.strip().splitlines()[-1] if r.returncode and r.stderr.strip() else ""))
    fallbacks.forget(store.MAC_KEY)

    # ── 3. a refused VectCut save ends on plain words ────────────────────────────────────────────────────────
    print("\na refused save says why, in both builders")
    for name in ("requests",):
        sys.modules.setdefault(name, types.ModuleType(name))
    if "PIL" not in sys.modules:
        try:
            import PIL.Image  # noqa: F401
        except Exception:
            pil = types.ModuleType("PIL"); pil.Image = types.ModuleType("PIL.Image")
            sys.modules["PIL"], sys.modules["PIL.Image"] = pil, pil.Image
    fresh()
    import draft_safety
    draft_safety.capcut_running = lambda: False
    draft_safety._snap_file = lambda: os.path.join(HOME, ".draft-snapshots.json")
    import cleanyap, superyap
    refused = {"success": False, "error": "[Errno 1] Operation not permitted: '" + REAL + "/dfd_x'"}
    for mod in (cleanyap, superyap):
        fallbacks.forget(store.MAC_KEY)
        mod.call = lambda ep, _strict=True, **k: refused
        err = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                mod.finalize("dfd_never_saved", "My Reel 1.1", {})
        except BaseException as e:  # noqa: BLE001
            err = e
        tag = mod.__name__
        check(isinstance(err, RuntimeError) and not isinstance(err, FileNotFoundError),
              f"{tag}: a RuntimeError, not a FileNotFoundError ({type(err).__name__})")
        msg = str(err)
        check("Operation not permitted" in msg and "Movies" in msg and store.COMMAND_NAME in msg,
              f"{tag}: says what refused it and what happens next")
        check(fallbacks.remembered(store.MAC_KEY) == "save", f"{tag}: remembered, so the next build is staged")
    fresh()
    check(store.drafts_root() == store.staging_root(), "after a refused save the next build is staged, "
          "even though this Python's own probe passes")
    other = store.save_refused_message({"success": False, "error": "timed out"}, REAL)
    check("/report-a-problem" in other and "timed out" in other, "any other failed save points at /report-a-problem")
    fallbacks.forget(store.MAC_KEY)
    fresh()

    # ── 4. the .command, end to end (needs a real Mac shell) ─────────────────────────────────────────────────
    if real_platform != "darwin":
        print("\n· Add to CapCut.command: skipped (needs a Mac)")
    else:
        print("\nAdd to CapCut.command brings a staged project into CapCut")
        stage = os.path.join(store.STAGING_DIR, "com.lveditor.draft")
        sroot = store.staging_root()

        def stage_draft(name, extra=""):
            d = os.path.join(stage, name)
            os.makedirs(os.path.join(d, "assets"), exist_ok=True)
            open(os.path.join(d, "assets", "cut.mp4"), "wb").write(b"\0" * 64)
            json.dump({"materials": {"videos": [{"path": f"{sroot}/{name}/assets/cut.mp4"}]}, "x": extra},
                      open(os.path.join(d, "draft_info.json"), "w", encoding="utf-8"))
            json.dump({"draft_name": name, "draft_fold_path": f"{sroot}/{name}", "draft_root_path": sroot},
                      open(os.path.join(d, "draft_meta_info.json"), "w", encoding="utf-8"))
            reg_p = os.path.join(stage, "root_meta_info.json")
            reg = json.load(open(reg_p, encoding="utf-8")) if os.path.exists(reg_p) else \
                {"all_draft_store": [], "draft_ids": 0, "root_path": sroot}
            reg["all_draft_store"] = [e for e in reg["all_draft_store"] if e["draft_name"] != name]
            reg["all_draft_store"].insert(0, {
                "draft_name": name, "draft_fold_path": f"{sroot}/{name}", "draft_root_path": sroot,
                "draft_json_file": f"{sroot}/{name}/draft_info.json",
                "draft_cover": f"{sroot}/{name}/draft_cover.jpg", "tm_draft_create": 1})
            json.dump(reg, open(reg_p, "w", encoding="utf-8"))

        stage_draft("My Reel 1.1")
        stage_draft("Taken 1.1")
        os.makedirs(os.path.join(REAL, "Taken 1.1"))
        open(os.path.join(REAL, "Taken 1.1", "draft_info.json"), "w", encoding="utf-8").write('{"hers": 1}')
        json.dump({"all_draft_store": [{"draft_name": "Her Old Project"}, {"draft_name": "Taken 1.1"}],
                   "draft_ids": 2, "root_path": REAL},
                  open(os.path.join(REAL, "root_meta_info.json"), "w", encoding="utf-8"))

        fakebin = os.path.join(TMP, "bin")
        os.makedirs(fakebin)
        os.makedirs(os.path.join(HOME, ".local", "bin"))
        os.symlink(sys.executable, os.path.join(HOME, ".local", "bin", "python3"))
        pgrep = os.path.join(fakebin, "pgrep")

        def capcut(open_):
            with open(pgrep, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("#!/bin/sh\necho 4242\nexit 0\n" if open_ else "#!/bin/sh\nexit 1\n")
            os.chmod(pgrep, 0o755)

        def run():
            env = dict(os.environ, HOME=HOME, PATH=fakebin + ":/usr/bin:/bin")
            r = subprocess.run(["bash", cmd], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
            return r.stdout + r.stderr, r.returncode

        capcut(True)
        before = sorted(os.listdir(REAL))
        out, code = run()
        check(code != 0 and "CapCut is open" in out and sorted(os.listdir(REAL)) == before,
              "it refuses while CapCut is open, and changes nothing")

        capcut(False)
        out, code = run()
        dst = os.path.join(REAL, "My Reel 1.1")
        check(code == 0 and "added   My Reel 1.1" in out and os.path.isdir(dst), "the project is added to CapCut")
        txt = open(os.path.join(dst, "draft_info.json"), encoding="utf-8").read()
        check("_capcut-staging" not in txt and f"{REAL}/My Reel 1.1/assets/cut.mp4" in txt,
              "its paths now point into CapCut's folder")
        check(os.path.isfile(os.path.join(dst, "assets", "cut.mp4")), "its media came with it")
        check(json.load(open(os.path.join(REAL, "Taken 1.1", "draft_info.json"), encoding="utf-8")) == {"hers": 1},
              "her project with the same name is untouched")
        t2 = os.path.join(REAL, "Taken 1.2")
        check(os.path.isdir(t2) and "goes in as \"Taken 1.2\"" in out, "the staged one goes in as the next version")
        meta = json.load(open(os.path.join(t2, "draft_meta_info.json"), encoding="utf-8"))
        check(meta["draft_name"] == "Taken 1.2" and meta["draft_fold_path"] == f"{REAL}/Taken 1.2",
              "the renamed project knows its own name and folder")
        reg = json.load(open(os.path.join(REAL, "root_meta_info.json"), encoding="utf-8"))
        names = [e["draft_name"] for e in reg["all_draft_store"]]
        check(set(names[:2]) == {"My Reel 1.1", "Taken 1.2"} and names[2:] == ["Her Old Project", "Taken 1.1"],
              "listed at the top, her projects kept")
        top = {e["draft_name"]: e for e in reg["all_draft_store"]}
        check(top["Taken 1.2"]["draft_fold_path"] == f"{REAL}/Taken 1.2"
              and top["My Reel 1.1"]["draft_json_file"] == f"{REAL}/My Reel 1.1/draft_info.json",
              "the list entries point into CapCut's folder")
        check(any(f.startswith("root_meta_info.json.before-engine-") for f in os.listdir(REAL)),
              "CapCut's list was backed up first")
        check(not [n for n in os.listdir(REAL) if n.endswith(".adding")], "nothing half-copied is left behind")

        snapshot = sorted(os.listdir(REAL))
        out, code = run()
        check(code == 0 and "already in CapCut" in out and sorted(os.listdir(REAL)) == snapshot,
              "running it again changes nothing")

        reg["all_draft_store"] = [e for e in reg["all_draft_store"] if e["draft_name"] != "My Reel 1.1"]
        json.dump(reg, open(os.path.join(REAL, "root_meta_info.json"), "w", encoding="utf-8"))
        out, code = run()
        names = [e["draft_name"] for e in
                 json.load(open(os.path.join(REAL, "root_meta_info.json"), encoding="utf-8"))["all_draft_store"]]
        check(code == 0 and "listed  My Reel 1.1" in out and names[0] == "My Reel 1.1"
              and not os.path.isdir(os.path.join(REAL, "My Reel 1.2")),
              "a project dropped from CapCut's list is listed again, not copied twice")

    # ── 5. a draft she already has ───────────────────────────────────────────────────────────────────────────
    print("\na draft she already has, on a blocked Mac")
    fresh()
    sroot = store.staging_root()
    hers = os.path.join(REAL, "Her Reel 1.2")
    os.makedirs(os.path.join(hers, "assets"), exist_ok=True)
    open(os.path.join(hers, "assets", "a.mp4"), "wb").write(b"\1" * 32)
    open(os.path.join(hers, "draft_info.json"), "w", encoding="utf-8").write(
        json.dumps({"materials": {"videos": [{"path": f"{hers}/assets/a.mp4"}]}, "tracks": []}))
    json.dump({"draft_name": "Her Reel 1.2", "draft_fold_path": hers, "draft_root_path": REAL},
              open(os.path.join(hers, "draft_meta_info.json"), "w", encoding="utf-8"))
    tpl = os.path.join(REAL, "Sound Template")
    os.makedirs(tpl, exist_ok=True)
    open(os.path.join(tpl, "draft_info.json"), "w", encoding="utf-8").write('{"tracks": []}')
    rp = os.path.join(REAL, "root_meta_info.json")
    reg0 = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {"all_draft_store": [], "root_path": REAL}
    reg0["all_draft_store"].append({"draft_name": "Her Reel 1.2", "draft_fold_path": hers, "draft_root_path": REAL,
                                    "draft_json_file": f"{hers}/draft_info.json", "tm_duration": 9000000})
    json.dump(reg0, open(rp, "w", encoding="utf-8"))
    hers_before = open(os.path.join(hers, "draft_info.json"), "rb").read()

    check(store.find_draft("Her Reel 1.2", sroot) == hers, "found in CapCut's own folder (read only)")
    check(store.lookup_roots(sroot) == [sroot, REAL], "both places are searched")
    check(store.find_draft("Her Reel 1.2", REAL) == hers and store.lookup_roots(REAL) == [REAL],
          "off the staging route nothing changes")
    check(store.stage_existing("Her Reel 1.2", REAL) == hers and not os.path.exists(os.path.join(sroot, "Her Reel 1.2")),
          "off the staging route a tool changes the draft where it is, as before")

    env = dict(os.environ, CAPCUT_DRAFT="Her Reel 1.2", CAPCUT_TEMPLATE="Sound Template")
    r = subprocess.run([sys.executable, "-c", probe_code], capture_output=True, text=True, env=env)
    copy = os.path.join(sroot, "Her Reel 1.2")
    check(r.stdout.strip().endswith("True") and os.path.isdir(copy),
          "a CAPCUT_DRAFT tool gets a copy of hers in the staging folder by itself")
    check(store.COMMAND_NAME in r.stdout and "new version" in r.stdout, "and is told the one double-click")
    ctext = open(os.path.join(copy, "draft_info.json"), encoding="utf-8").read()
    check(f"{sroot}/Her Reel 1.2/assets/a.mp4" in ctext and REAL not in ctext, "the copy's paths point at the copy")
    sreg = json.load(open(os.path.join(sroot, "root_meta_info.json"), encoding="utf-8"))
    ent = [e for e in sreg["all_draft_store"] if e["draft_name"] == "Her Reel 1.2"]
    check(ent and ent[0].get("tm_duration") == 9000000 and ent[0]["draft_fold_path"] == copy,
          "her list entry came along, pointed at the copy")
    check(os.path.isdir(os.path.join(sroot, "Sound Template")), "the template it borrows from is copied too")
    check(open(os.path.join(hers, "draft_info.json"), "rb").read() == hers_before, "hers is untouched")
    fallbacks.forget(store.MAC_KEY)

    d = json.load(open(os.path.join(copy, "draft_info.json"), encoding="utf-8"))
    d["tracks"].append({"type": "audio", "segments": []})     # what a layer-on-top tool does to the copy
    json.dump(d, open(os.path.join(copy, "draft_info.json"), "w", encoding="utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        again = store.stage_existing("Her Reel 1.2", sroot)
    check(again == copy and json.load(open(os.path.join(copy, "draft_info.json"), encoding="utf-8"))["tracks"],
          "a second tool keeps building on the same copy while hers is unchanged")
    with contextlib.redirect_stdout(io.StringIO()):
        store.stage_existing("Sound Template", sroot, reference=True)   # already copied: reused, still a reference

    if real_platform == "darwin":
        capcut(False)
        out, code = run()
        v13 = os.path.join(REAL, "Her Reel 1.3")
        check(code == 0 and os.path.isdir(v13) and "goes in as \"Her Reel 1.3\"" in out,
              "the change goes into CapCut as a NEW version")
        check(open(os.path.join(hers, "draft_info.json"), "rb").read() == hers_before, "hers is still untouched")
        t13 = open(os.path.join(v13, "draft_info.json"), encoding="utf-8").read()
        check(f"{v13}/assets/a.mp4" in t13 and "_capcut-staging" not in t13 and
              json.loads(t13)["tracks"], "the new version carries the change and points at its own folder")
        check(not os.path.exists(os.path.join(v13, store.STAGED_FROM)), "the engine's own note stays behind")
        check(not os.path.isdir(os.path.join(REAL, "Sound Template 1.1")), "a template that was only read stays out")
        names = [e["draft_name"] for e in json.load(open(rp, encoding="utf-8"))["all_draft_store"]]
        check(names[0] == "Her Reel 1.3" and "Her Reel 1.2" in names, "listed at the top, hers still listed")
        snap = sorted(os.listdir(REAL))
        out, code = run()
        check(code == 0 and sorted(os.listdir(REAL)) == snap, "running it again changes nothing")

        # she edits hers in CapCut: the next change starts from her edit, and the old copy is kept aside
        open(os.path.join(hers, "draft_info.json"), "w", encoding="utf-8").write(
            json.dumps({"materials": {"videos": [{"path": f"{hers}/assets/a.mp4"}]}, "tracks": [], "hers": 2}))
        with contextlib.redirect_stdout(io.StringIO()):
            store.stage_existing("Her Reel 1.2", sroot)
        check(json.load(open(os.path.join(copy, "draft_info.json"), encoding="utf-8")).get("hers") == 2
              and os.path.isdir(os.path.join(store.STAGING_DIR, "_replaced")),
              "after she edits hers, the copy is fresh and the old copy is moved aside, not deleted")
        out, code = run()
        check(code == 0 and not os.path.isdir(os.path.join(REAL, "Her Reel 1.4")),
              "a fresh copy no tool has changed yet is not brought in")

    print("\nthe tools that look a draft up by name use the shared lookup")
    root = os.path.dirname(PRODUCT)
    for rel, needle in ((".claude/skills/rough-cut/scripts/your-turn.py", "find_draft(draft_arg"),
                        (".claude/skills/rough-cut/scripts/your-turn.py", "lookup_roots(CAPCUT_ROOT)"),
                        ("workflows/capcut-live.py", "stage_existing(name, str(DRAFTS))"),
                        ("product/gif_dropins.py", "stage_existing(draft_name, CAP)"),
                        ("product/capture-templates.py", "find_draft(draft, CAP)")):
        check(needle in open(os.path.join(root, rel), encoding="utf-8").read(), f"{rel}: {needle}")

    # ── 7. the problem report asks the Mac question too ───────────────────────────────────────────────────────
    print("\nthe problem report says whether the engine's Python may write CapCut's folder on a Mac")
    import runpy
    report_local = os.path.join(TMP, "local-report")
    os.environ["REELS_ENGINE_LOCAL"] = report_local

    def main_says(mkdir):
        """capcut_store_redirect.py run as a script (what collect-report.sh runs), in the temp HOME."""
        buf = io.StringIO()
        os.mkdir = mkdir
        try:
            with contextlib.redirect_stdout(buf):
                runpy.run_path(os.path.join(PRODUCT, "capcut_store_redirect.py"), run_name="__main__")
        except SystemExit:
            pass
        finally:
            os.mkdir = real_mkdir
        return buf.getvalue()

    said = main_says(shield)
    check(said.startswith("redirected: yes (this Mac refuses the engine a write in ~/Movies)"),
          "refused: the script answers with the Mac line")
    said = main_says(real_mkdir)
    check(said.startswith("redirected: no."), "allowed: the script answers no")

    collector = os.path.join(root, "scripts", "collect-report.sh")
    src = open(collector, encoding="utf-8").read()
    at = src.index("capcut_store_redirect.py\" ]; then")
    gate = src[src.rindex("\nif ", 0, at) + 1:src.index("\n", at)]
    check("IS_WIN" not in gate, "collect-report.sh runs the redirect check on a Mac too, not only on Windows")
    mac_roots = src[src.index('CC_ROOTS="$HOME/Movies'):src.index("\nfi", src.index('CC_ROOTS="$HOME/Movies'))]
    check("$_d/projects/_capcut-staging/com.lveditor.draft" in mac_roots,
          "the Mac draft folders include the staging folder")

    if real_platform == "darwin" and os.getuid() != 0:
        # The collector's own CapCut section, run by bash on a temp home whose Movies folder refuses writes
        # (a read-only folder: the same PermissionError a protected-folders shield gives the engine's Python).
        h2 = os.path.join(TMP, "home-report")
        eng = os.path.join(h2, "engine")
        os.makedirs(os.path.join(eng, "product"))
        for f in os.listdir(PRODUCT):
            if f.endswith(".py"):
                shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
        os.makedirs(os.path.join(eng, "projects", "_capcut-staging", "com.lveditor.draft", "My Reel 1.1"))
        mv = os.path.join(h2, "Movies")
        os.makedirs(mv)
        os.chmod(mv, 0o555)
        try:
            tf = src.index("tilde() {")
            body = ("set -uo pipefail\n" + src[tf:src.index("\n}\n", tf) + 3]
                    + src[src.index("# ── CapCut"):src.index("# ── setup check")])
            env = dict(os.environ, HOME=h2, IS_WIN="0", PY=sys.executable, _d=eng,
                       REELS_ENGINE_LOCAL=os.path.join(TMP, "local-report2"), PYTHONDONTWRITEBYTECODE="1")
            r = subprocess.run(["bash", "-c", body], capture_output=True, text=True, encoding="utf-8",
                               timeout=120, env=env)
            out = r.stdout
        finally:
            os.chmod(mv, 0o755)
        check("- **Movies-folder redirect:** redirected: yes (this Mac refuses the engine a write in ~/Movies)" in out,
              "the report carries the Mac answer line")
        check("~/engine/projects/_capcut-staging/com.lveditor.draft" in out and h2 not in out,
              "the staging path is in the report, home shortened to ~")
        check("**Draft folder:** ~/engine/projects/_capcut-staging/com.lveditor.draft" in out
              and "**Most recent draft:** My Reel 1.1" in out, "the staged drafts are listed on a Mac")
        check(not [n for n in os.listdir(mv) if n.startswith(".ree-")], "the probe leaves nothing in Movies")
finally:
    os.mkdir = real_mkdir
    sys.platform = real_platform
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(TMP, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\n✓ a Mac that blocks ~/Movies: drafts staged, one double-click into CapCut, plain words on a refused save")
