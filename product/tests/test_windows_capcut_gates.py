#!/usr/bin/env python3
"""test_windows_capcut_gates.py — the CapCut-is-open gates guard what they protect, and nothing more.

Two Windows buyer reports drove this:
  1. With the Microsoft Store Claude app, drafts build in projects/_capcut-staging/, a folder CapCut never reads.
     The CapCut-must-be-quit guard still refused every build while a stuck CapCut.exe was running. Now a write
     into the staging folder goes ahead (one plain line), and CapCut's own drafts folder is never relaxed.
     When the SAME CapCut processes (same id, same start time) survive what she called a restart, the refusal
     says plainly that the computer did not fully restart. The guard still refuses.
  2. "Add to CapCut.bat" refused forever behind a CapCut.exe that not even an administrator could end. Now a
     CapCut that is provably stuck (every process windowless and idle over the sample) lets the copy go ahead,
     with a plain line and a fallbacks.log entry, remembering nothing. Anything with a window, any work done,
     or anything unreadable keeps refusing. "Could not check" says what to do.

Everything runs in temp folders with stand-ins: no real CapCut, no real _local/, no PowerShell.
Run: python3 product/tests/test_windows_capcut_gates.py
"""
import contextlib, glob, io, json, os, re, shutil, subprocess, sys, tempfile

for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print every character
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)

tmp = tempfile.mkdtemp(prefix="win-capcut-gates-")
ENV_KEYS = ("CAPCUT_DRAFTS_ROOT", "CAPCUT_ALLOW_OPEN", "REELS_ENGINE_LOCAL", "LOCALAPPDATA")
env_before = {k: os.environ.get(k) for k in ENV_KEYS}
os.environ["REELS_ENGINE_LOCAL"] = os.path.join(tmp, "_local")
os.environ.pop("CAPCUT_ALLOW_OPEN", None)
os.environ["CAPCUT_DRAFTS_ROOT"] = os.path.join(tmp, "real-capcut", "com.lveditor.draft")

import capcut_store_redirect as store
import draft_safety as ds
import capcut_front
import install_to_capcut as inst
import fallbacks

fails = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        fails.append(what)


def guard(draft=None):
    """Run the guard; answer 'allowed' or 'refused', plus what it printed and the refusal text."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            ds.require_capcut_quit("build this reel", draft=draft) if draft else ds.require_capcut_quit("build this reel")
        return "allowed", out.getvalue(), ""
    except ds.CapCutOpen as e:
        return "refused", out.getvalue(), str(e)


real_name = os.name
real_running = ds.capcut_running
real_front_running = capcut_front.capcut_running
real_staging_dir = store.STAGING_DIR
real_cap, real_front_cap, real_front_meta = ds.CAP, capcut_front.CAP, capcut_front.META
real_procs = inst.capcut_processes
try:
    # The engine's staging folder, inside a temp "engine", and a temp stand-in for CapCut's own folder.
    store.STAGING_DIR = os.path.join(tmp, "engine", "projects", "_capcut-staging")
    STAGE = store.staging_root()
    REAL = os.path.join(tmp, "real-capcut", "com.lveditor.draft")
    os.makedirs(STAGE)
    os.makedirs(REAL)

    # ── 1. which folder CapCut never reads ──────────────────────────────────
    print("capcut_never_reads: only the staging folder, never CapCut's own")
    os.environ["CAPCUT_DRAFTS_ROOT"] = STAGE           # what a redirected Store app's drafts_root() answers
    ds.CAP = STAGE
    check(ds.capcut_never_reads() is True, "a redirected machine (both roots = staging) never reaches CapCut")
    check(ds.capcut_never_reads(os.path.join(STAGE, "Reel 1.1")) is True, "a draft folder inside staging")
    check(ds.capcut_never_reads(REAL) is False, "CapCut's own drafts folder is never relaxed")
    check(ds.capcut_never_reads(os.path.join(REAL, "Reel 1.1")) is False, "nor a draft inside it")
    check(ds.capcut_never_reads(os.path.expanduser("~/Movies/" + store.REL_DRAFTS)) is False,
          "nor the Mac CapCut folder")
    check(ds.capcut_never_reads(os.path.join(STAGE, "..", "..", "elsewhere")) is False,
          "a path that only starts out in staging and climbs out of it is not staging")
    check(ds.capcut_never_reads(STAGE + "-not-really") is False, "a sibling whose name merely starts the same")
    os.environ["CAPCUT_DRAFTS_ROOT"] = REAL            # the environment changed mid-run: answer "real folder"
    check(ds.capcut_never_reads() is False, "module root = staging but a fresh drafts_root() = CapCut's: refused")
    os.environ["CAPCUT_DRAFTS_ROOT"] = STAGE
    ds.CAP = REAL
    check(ds.capcut_never_reads() is False, "module root = CapCut's folder: refused, whatever drafts_root says")

    # ── 2. the guard ─────────────────────────────────────────────────────────
    print("\nrequire_capcut_quit lets a staging build through and nothing else")
    ds.capcut_running = lambda: True
    ds.CAP = STAGE
    ds._said_staging.clear()
    res, said, _ = guard()
    check(res == "allowed", "CapCut open + a staging build: the build goes ahead")
    check("staging folder" in said and "Add to CapCut" in said and "Close CapCut" in said,
          "with one plain line that says why and what still needs CapCut closed")
    res2, said2, _ = guard()
    check(res2 == "allowed" and said2 == "", "the line is said once per run, not on every write")
    check(guard(os.path.join(STAGE, "Reel 1.2"))[0] == "allowed", "an explicit staging draft path goes ahead")
    check(guard(os.path.join(REAL, "Reel 1.2"))[0] == "refused",
          "an explicit draft in CapCut's own folder is refused even on a staging machine")
    ds.capcut_running = lambda: None
    check(guard()[0] == "allowed", "'could not tell' is harmless for staging: CapCut cannot touch it either way")
    ds.CAP = REAL
    os.environ["CAPCUT_DRAFTS_ROOT"] = REAL
    check(guard()[0] == "refused", "'could not tell' + CapCut's own folder: still refused")
    ds.capcut_running = lambda: True
    res3, _, msg3 = guard()
    check(res3 == "refused" and "quit it fully" in msg3.lower(), "CapCut open + CapCut's own folder: refused, as before")
    ds.capcut_running = lambda: False
    check(guard()[0] == "allowed", "CapCut closed: allowed, as before")
    ds.capcut_running = lambda: True
    os.environ["CAPCUT_ALLOW_OPEN"] = "1"
    check(guard()[0] == "allowed", "the deliberate CAPCUT_ALLOW_OPEN=1 override is unchanged")
    os.environ.pop("CAPCUT_ALLOW_OPEN")

    # ── 3. every writer that calls the guard writes where the guard looks ────
    print("\nevery caller of require_capcut_quit takes its drafts root from drafts_root() / draft_safety.CAP")
    # Proof the default (no draft path) is right for every caller: the guard compares draft_safety.CAP and a
    # fresh drafts_root(), so a caller is covered exactly when IT writes under one of those. A new caller that
    # builds its own root fails here until it is checked.
    sources = re.compile(r"drafts_root\(\)|draft_safety\.CAP\b|_ds\.CAP\b|\bD\.CAP\b|_ds\.CAP\)")
    delegates = re.compile(r"(cleanyap|superyap)\.finalize\(")
    files = (glob.glob(os.path.join(ROOT, "product", "*.py")) + glob.glob(os.path.join(ROOT, "product", "*.sh"))
             + glob.glob(os.path.join(ROOT, "workflows", "*.py"))
             + glob.glob(os.path.join(ROOT, "dev-tools", "**", "*.py"), recursive=True)
             + glob.glob(os.path.join(ROOT, ".claude", "skills", "**", "*.py"), recursive=True))
    callers, bad, direct = [], [], []
    for f in files:
        if "VectCutAPI" in f or os.sep + "tests" + os.sep in f:
            continue
        txt = open(f, encoding="utf-8", errors="ignore").read()
        if "require_capcut_quit(" not in txt or f.endswith("draft_safety.py"):
            continue
        rel = os.path.relpath(f, ROOT)
        callers.append(rel)
        if rel.endswith("separate_layers.sh"):
            # a check-only call, in its own process; the layers are then built by capcut_handoff (checked here)
            ok = "capcut_handoff" in txt or "build_layer" in txt
        else:
            ok = bool(sources.search(txt) or delegates.search(txt))
        if not ok:
            bad.append(rel)
        if "real_root(" in txt:
            direct.append(rel)
    check(len(callers) >= 15, f"found the writers ({len(callers)})")
    check(not bad, f"each one's root is the guard's root (offenders: {bad or 'none'})")
    check(not direct, f"none writes straight into CapCut's real folder past the redirect (offenders: {direct or 'none'})")
    handoff = open(os.path.join(ROOT, "product", "capcut_handoff.py"), encoding="utf-8").read()
    check("cleanyap.finalize(" in handoff, "capcut_handoff writes through cleanyap.finalize (cleanyap's CAP)")
    cy = open(os.path.join(ROOT, "product", "cleanyap.py"), encoding="utf-8").read()
    check("drafts_root()" in cy and "draft_folder=CAP" in cy, "cleanyap saves the VectCut draft into its CAP")

    # ── 4. "did you really restart?" ─────────────────────────────────────────
    print("\nthe same CapCut surviving a 'restart' is named plainly, and the guard still refuses")
    procs = [{"pid": 4321, "start": "2026-10-01T08:00:00.0000000Z", "window": 0, "responding": True, "cpu_ms": 9},
             {"pid": 4400, "start": "2026-10-01T08:00:01.0000000Z", "window": 0, "responding": True, "cpu_ms": 1}]
    inst.capcut_processes = lambda timeout=20: [dict(p) for p in procs]
    ds.CAP = REAL
    ds.capcut_running = lambda: True
    os.name = "nt"
    try:
        r1, _, m1 = guard()
        r2, _, m2 = guard()
        procs[0]["start"] = "2026-10-02T09:00:00.0000000Z"       # a real restart: new start time
        r3, _, m3 = guard()
        procs[0]["start"] = None                                   # Windows would not say when it started
        r4, _, m4 = guard()
    finally:
        os.name = real_name
    check(r1 == r2 == r3 == r4 == "refused", "every one of these is still a refusal")
    check("restart" not in m1.lower(), "the first refusal makes no restart claim (nothing to compare with yet)")
    check("did not fully restart" in m2 and "Start > Power > Restart" in m2 and "power button" in m2,
          "the same processes next time: 'did not fully restart', with the two ways that work")
    check("did not fully restart" not in m3, "a new start time (a real restart) makes no such claim")
    check("did not fully restart" not in m4, "an unreadable start time makes no claim: a reused id proves nothing")
    check(fallbacks.remembered("capcut.open-processes") is not None, "the processes are remembered per machine")
    os.name = "posix"
    try:
        check("restart" not in guard()[2].lower(), "off Windows the note never appears")
    finally:
        os.name = real_name
    inst.capcut_processes = real_procs

    # ── 5. capcut_front orders the staging list with CapCut open, never CapCut's own ──
    print("\ncapcut_front: staging's list is ours to order; CapCut's own list waits for CapCut to close")
    meta = {"all_draft_store": [{"draft_name": "Old", "draft_fold_path": os.path.join(STAGE, "Old"),
                                 "tm_draft_modified": 5},
                                {"draft_name": "New", "draft_fold_path": os.path.join(STAGE, "New"),
                                 "tm_draft_modified": 1}]}
    for n in ("Old", "New"):
        os.makedirs(os.path.join(STAGE, n), exist_ok=True)
    json.dump(meta, open(os.path.join(STAGE, "root_meta_info.json"), "w", encoding="utf-8"))
    capcut_front.capcut_running = lambda: True
    capcut_front.CAP, capcut_front.META = STAGE, os.path.join(STAGE, "root_meta_info.json")
    os.environ["CAPCUT_DRAFTS_ROOT"] = STAGE
    with contextlib.redirect_stdout(io.StringIO()):
        capcut_front.to_front("New")
    top = json.load(open(capcut_front.META, encoding="utf-8"))["all_draft_store"][0]["draft_name"]
    check(top == "New", "with CapCut open, a staging draft still goes to the top of the staging list")
    json.dump(meta, open(os.path.join(REAL, "root_meta_info.json"), "w", encoding="utf-8"))
    capcut_front.CAP, capcut_front.META = REAL, os.path.join(REAL, "root_meta_info.json")
    os.environ["CAPCUT_DRAFTS_ROOT"] = REAL
    try:
        capcut_front.to_front("New")
        check(False, "CapCut's own list is refused while CapCut is open")
    except SystemExit:
        check(True, "CapCut's own list is refused while CapCut is open")

    # ── 6. the stuck-CapCut test is measured and conservative ────────────────
    print("\nstuck_capcut(): True only when every CapCut is windowless AND idle across the sample")
    slept = []

    def verdict(first, second):
        seq = [first, second]
        return inst.stuck_capcut(probe=lambda: seq.pop(0), sleep=slept.append)

    z = lambda pid=7, win=0, cpu=100, start="s": {"pid": pid, "start": start, "window": win,
                                                  "responding": True, "cpu_ms": cpu}
    check(verdict([z(), z(8)], [z(), z(8)]) is True, "two windowless, idle processes: stuck")
    check(slept and slept[0] >= 3, "it waits a few seconds between the two looks")
    check(verdict([z(), z(8, win=1234)], [z(), z(8, win=1234)]) is False, "any process with a window: not stuck")
    check(verdict([z()], [z(win=99)]) is False, "a window that appears during the sample: not stuck")
    check(verdict([z()], [z(cpu=101)]) is False, "any processor time used during the sample: not stuck")
    check(verdict([z(cpu=None)], [z(cpu=None)]) is False, "processor time unreadable: not stuck (never assume idle)")
    check(verdict([z(win=None)], [z(win=None)]) is False, "window unreadable: not stuck")
    check(verdict([z()], [z(), z(8)]) is False, "a process that appears during the sample: not stuck")
    check(verdict([z()], [z(start="other")]) is False, "a different process under the same id: not stuck")
    check(verdict(None, None) is None, "processes could not be listed: None (the caller refuses)")
    check(verdict([], []) is False, "no CapCut at all is not a stuck CapCut")

    print("\ncapcut_processes() reads PowerShell's answer and never turns 'unknown' into 0")
    real_run = subprocess.run

    def fake_ps(stdout):
        def run(*a, **k):
            return subprocess.CompletedProcess(a[0], 0, stdout, b"")
        return run

    os.name = "nt"
    try:
        subprocess.run = fake_ps(b"4321|2026-10-01T08:00:00Z|0|True|1500\r\n4400|||True|\r\nEND\r\n")
        got = inst.capcut_processes()
        subprocess.run = fake_ps(b"4321|2026-10-01T08:00:00Z|0|True|1500\r\n")
        cut_short = inst.capcut_processes()
        subprocess.run = fake_ps(b"END\r\n")
        none_running = inst.capcut_processes()

        def boom(*a, **k):
            raise FileNotFoundError("powershell")
        subprocess.run = boom
        no_ps = inst.capcut_processes()
    finally:
        subprocess.run = real_run
        os.name = real_name
    check(got and got[0] == {"pid": 4321, "start": "2026-10-01T08:00:00Z", "window": 0, "responding": True,
                             "cpu_ms": 1500}, "a full line is read field by field")
    check(got and got[1]["start"] is None and got[1]["window"] is None and got[1]["cpu_ms"] is None,
          "fields Windows would not give stay unknown (None), never 0")
    check(cut_short is None, "an answer without END (PowerShell died halfway) is 'could not check'")
    check(none_running == [], "a complete answer with no CapCut is 'none running'")
    check(no_ps is None, "no PowerShell at all is 'could not check'")
    os.name = "posix"
    try:
        check(inst.capcut_processes() is None, "off Windows it never runs")
    finally:
        os.name = real_name

    # ── 7. Add to CapCut with a stuck CapCut, and with 'could not check' ─────
    print("\n\"Add to CapCut\" copies past a stuck CapCut, refuses a live one, and says what to do")
    la = os.path.join(tmp, "AppData", "Local")
    os.makedirs(la)
    os.environ["LOCALAPPDATA"] = la
    istage = os.path.join(tmp, "istage", "com.lveditor.draft")
    inst.STAGE = istage
    d = os.path.join(istage, "My Reel 1.0")
    os.makedirs(d)
    open(os.path.join(d, "draft_content.json"), "w", encoding="utf-8").write('{"tracks": []}')
    real = os.path.join(la, inst.REL)
    os.makedirs(real)
    json.dump({"all_draft_store": [{"draft_name": "Her Old Project"}], "draft_ids": 1},
              open(os.path.join(real, "root_meta_info.json"), "w", encoding="utf-8"))
    inst.inside_store_app = lambda: False
    log = os.path.join(os.environ["REELS_ENGINE_LOCAL"], "fallbacks.log")
    pivots = os.path.join(os.environ["REELS_ENGINE_LOCAL"], "pivots.json")
    pivots_before = open(pivots, encoding="utf-8").read() if os.path.exists(pivots) else ""

    def run_installer():
        out, code = io.StringIO(), 0
        os.name = "nt"
        try:
            with contextlib.redirect_stdout(out):
                try:
                    inst.main()
                except SystemExit as e:
                    code = e.code
        finally:
            os.name = real_name
        return out.getvalue(), code

    inst.capcut_running = lambda: True
    inst.stuck_capcut = lambda: False
    out1, code1 = run_installer()
    check(code1 and "Close CapCut" in str(code1), "a CapCut that has a window or is working: refused")
    check(not os.path.exists(os.path.join(real, "My Reel 1.0")), "and nothing was copied")
    inst.stuck_capcut = lambda: None
    _, code1b = run_installer()
    check(code1b and "Close CapCut" in str(code1b), "a CapCut whose state cannot be measured: refused")

    inst.stuck_capcut = lambda: True
    out2, code2 = run_installer()
    check(not code2 and os.path.isdir(os.path.join(real, "My Reel 1.0")), "every CapCut stuck: the copy goes ahead")
    check("stuck" in out2 and "cannot save" in out2, "with a plain line saying why")
    check("⚠" not in out2 and "⛔" not in out2, "and no alarm symbols for a switch that worked")
    check(os.path.exists(log) and "add-to-capcut" in open(log, encoding="utf-8").read(),
          "one line lands in fallbacks.log for /report-a-problem")
    pivots_after = open(pivots, encoding="utf-8").read() if os.path.exists(pivots) else ""
    check(pivots_after == pivots_before, "nothing is remembered: the next run measures again")

    print("\na project CapCut's list lost goes back on the list, untouched")
    reg_path = os.path.join(real, "root_meta_info.json")
    reg = json.load(open(reg_path, encoding="utf-8"))
    reg["all_draft_store"] = [e for e in reg["all_draft_store"] if e.get("draft_name") != "My Reel 1.0"]
    json.dump(reg, open(reg_path, "w", encoding="utf-8"))
    inst.capcut_running = lambda: False
    before = open(os.path.join(real, "My Reel 1.0", "draft_content.json"), encoding="utf-8").read()
    out3, _ = run_installer()
    names = [e.get("draft_name") for e in json.load(open(reg_path, encoding="utf-8"))["all_draft_store"]]
    check(names[:1] == ["My Reel 1.0"] and "Her Old Project" in names, "it is listed again, at the top")
    check(open(os.path.join(real, "My Reel 1.0", "draft_content.json"), encoding="utf-8").read() == before,
          "the project itself was not copied over")
    out4, _ = run_installer()
    check("already in CapCut" in out4, "a second run changes nothing")

    print("\n'could not check' is asked a second way, then says what to do")
    inst.capcut_running = lambda: None
    inst.capcut_processes = lambda timeout=20: None
    _, code5 = run_installer()
    msg5 = str(code5)
    check(code5 and "could not check" in msg5 and "Start > Power > Restart" in msg5 and "/report-a-problem" in msg5,
          "neither check answered: refused, with the restart and /report-a-problem steps")
    inst.capcut_processes = lambda timeout=20: []
    _, code6 = run_installer()
    check(not code6, "tasklist failed but PowerShell's full list shows no CapCut: it goes ahead")
    inst.capcut_processes = lambda timeout=20: [{"pid": 1, "start": None, "window": 55, "responding": True,
                                                 "cpu_ms": 3}]
    inst.stuck_capcut = lambda: False
    _, code7 = run_installer()
    check(code7 and "Close CapCut" in str(code7), "tasklist failed and PowerShell sees a live CapCut: refused")

    # ── 8. the docs never send her to open CapCut while writes are left ──────
    print("\nthe skill and the playbook keep CapCut closed until the last write")
    skill = open(os.path.join(ROOT, ".claude", "skills", "capcut", "SKILL.md"), encoding="utf-8").read()
    book = open(os.path.join(PRODUCT, "PC-CONVERSION-PLAYBOOK.md"), encoding="utf-8").read()
    check("mid-job" in skill.lower() or "writes left" in skill.lower(),
          "the capcut skill says never to send her into CapCut while the build has writes left")
    flat = " ".join(book.split())
    check("and opens it with `--open`" not in flat,
          "the playbook no longer reads as if every build opens CapCut")
    check("staging" in book and "stuck" in book.lower(), "the playbook names the staging gate and the stuck CapCut")

    print("\na font download never sends her into CapCut while a build has writes left")
    doctor = open(os.path.join(PRODUCT, "capcut_font_doctor.py"), encoding="utf-8").read()
    i_finish = doctor.find("let me finish and hand it over first")
    i_open = doctor.find("Open CapCut and start a new project")
    check(0 <= i_finish < i_open, "the font doctor says to let the build finish and hand off BEFORE opening CapCut")
    check("Quit CapCut fully ({_QUIT_HINT}), then tell me to go" in doctor,
          "and to quit CapCut fully (the platform's own way) and say go before the next write")
    check("Close CapCut fully. Next build" not in doctor, "the old 'close it and the next build finds it' line is gone")
    recipe = " ".join(open(os.path.join(ROOT, ".claude", "skills", "studio", "reference", "recipe.md"),
                           encoding="utf-8").read().split())
    check("never mid-job" in recipe and "hand it over first" in recipe,
          "the studio recipe asks for the font before the build writes anything, never mid-job")
    check("quit CapCut fully" in recipe and "Close out, it saves on its own" not in recipe,
          "and has her quit CapCut fully, not just close the project")
    check("Tell me to go when CapCut is closed" in recipe, "and say go only once CapCut is closed")
finally:
    os.name = real_name
    ds.capcut_running = real_running
    capcut_front.capcut_running = real_front_running
    store.STAGING_DIR = real_staging_dir
    ds.CAP, capcut_front.CAP, capcut_front.META = real_cap, real_front_cap, real_front_meta
    inst.capcut_processes = real_procs
    for k, v in env_before.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\n✓ CapCut gates: staging builds go ahead, CapCut's own folder stays guarded, a stuck CapCut is no dead end")
