#!/usr/bin/env python3
"""capcut_store_redirect.py — CapCut drafts when Claude runs as a Microsoft Store (MSIX) app on Windows.

WHY THIS EXISTS. The Claude desktop app from the Microsoft Store is an MSIX package. Windows gives a packaged
app, and every program it starts (Git Bash, Python, the editing engine), a private copy of AppData: a NEW file
or folder written under %LOCALAPPDATA% silently lands in
    %LOCALAPPDATA%\\Packages\\<the app's package>\\LocalCache\\Local\\...
instead. The app itself reads its private copy merged over the real one, so from inside everything looks fine.
CapCut does not run inside that package, so it never sees the private copy: a draft the engine "wrote into
CapCut" is invisible to CapCut. A buyer on a Spanish Windows 11 found this by writing a probe file and finding
it under Packages\\Claude_...\\LocalCache. (Changing an EXISTING file is not redirected, which is why reading
CapCut's list and fonts still worked; only the new draft folders went missing.)

WHAT THE ENGINE DOES ABOUT IT.
  1. detect()        probes once: make a uniquely named folder in %LOCALAPPDATA% and see whether it appeared
                     under Packages\\*\\LocalCache\\Local. Answers the package name, or None.
  2. staging_root()  when redirected, every draft is built in projects/_capcut-staging/ inside the engine
                     folder instead (not AppData, so nothing redirects it, and an update never touches it).
  3. write_installer() drops "Add to CapCut.bat" + install_to_capcut.py beside the staged drafts. Run from
                     File Explorer it runs OUTSIDE the Store package, so its copy lands in CapCut's real
                     folder. It refuses while CapCut is open, never overwrites a draft she already has,
                     rewrites the paths inside each draft, and backs up CapCut's list first.
  4. after_build() /   the engine runs that step for her. When the build process ends (so every write it makes
     auto_add()        is done) and CapCut is closed, it leaves a one-time request in the staging folder and hands
                       the .bat to the already-running Windows shell (`explorer.exe "<the .bat>"`), which starts
                       it outside the package exactly like her double-click. The installer answers in a result
                       file in the staging folder. A clean "done": one line, "It's in CapCut". Anything else
                       (CapCut open, no answer, a refusal, an error): the double-click instructions and the
                       folder, exactly as before, so it is never a dead end. REE_AUTO_ADD=0 turns it off.
                       UNVERIFIED on a real Store-app PC as of 2026-10-19; the fallback is the safe default.

THE MAC TWIN. On some Macs the engine's own Python is refused every write in ~/Movies (also ~/Music and
~/Pictures) with "Operation not permitted", while Apple's own tools (/bin/mkdir, /bin/cp) and other signed apps
write there fine. That is the shape of a security app's protected-folders shield: it guards exactly those
folders and lets through programs it recognises, and the engine's Python is not one of them. CapCut keeps its
drafts in ~/Movies, so VectCut's save failed and the build ended on a confusing error. The engine handles it:
  1. mac_drafts_blocked()  one cheap probe per run (make + remove a hidden folder directly in ~/Movies, the
                           folder the shield guards, from Python; never anything inside CapCut's own folder).
                           Refused: remembered as "mac.drafts-blocked" (product/fallbacks.py) and noted for
                           /report-a-problem. Allowed again later: forgotten, back to the usual route.
  2. drafts_root()         answers the same staging folder as the Store-app route, so every writer agrees.
     find_draft() /        a draft she ALREADY has is still found: CapCut's folder is read (reading is allowed),
     stage_existing()      and a tool that changes it works on a copy in the staging folder, which goes into
                           CapCut as a NEW version (her draft is never changed in place). Every layer-on-top tool
                           names its draft with CAPCUT_DRAFT, so drafts_root() makes that copy by itself.
  3. write_installer()     drops "Add to CapCut.command" + add_to_capcut_mac.py beside the staged drafts. She
                           double-clicks it in Finder. Python only prepares each project inside the engine's own
                           folder; Apple's /bin/mv and /bin/cp put it into CapCut, so the shield lets it through.
                           Same rules as the .bat: refuses while CapCut is open, never replaces a project already
                           in CapCut (a taken name goes in as the next version), backs up CapCut's list first.

Standard library only: install_to_capcut.py runs on whatever Python she has, with nothing installed.
"""
import atexit
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
REL_DRAFTS = "CapCut/User Data/Projects/com.lveditor.draft"
STAGING_DIR = os.path.join(ENGINE, "projects", "_capcut-staging")
BAT_NAME = "Add to CapCut.bat"
COMMAND_NAME = "Add to CapCut.command"
MAC_KEY = "mac.drafts-blocked"   # product/fallbacks.py: "probe" (this Python is refused) or "save" (VectCut was)
WIN_KEY = "windows.store-redirect"   # product/fallbacks.py: the Store package name some Python on this PC saw

_cache = {}


def real_root():
    """CapCut's own drafts folder on this Windows machine, as CapCut sees it."""
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), REL_DRAFTS).replace("\\", "/")


def _probe_store():
    """This process's own answer: the package whose private AppData caught a new folder, or None."""
    la = os.environ["LOCALAPPDATA"]
    probe = f".ree-store-probe-{uuid.uuid4().hex[:12]}"
    made = os.path.join(la, probe)
    pkg = None
    try:
        os.makedirs(made, exist_ok=True)
        hits = glob.glob(os.path.join(la, "Packages", "*", "LocalCache", "Local", probe))
        if hits:
            pkg = os.path.basename(hits[0].split(os.sep + "LocalCache")[0].rstrip("\\/"))
    except Exception:
        pkg = None
    finally:
        try:
            os.rmdir(made)
        except Exception:
            pass
    return pkg


def detect():
    """The Store package whose private AppData is swallowing new files, or None when writes are real.

    Windows only; None everywhere else. Decided once per process. Any failure answers None (the normal path),
    because the probe is an extra safety net, never a gate.

    ONE ANSWER FOR EVERY PYTHON ON THE PC. Whether a process is inside the Store package depends on how it was
    started, not on the PC: on one buyer's PC the editing engine's own Python said "redirected" and the
    `python` on PATH (started through an app alias, outside the package) said "not redirected". Two answers
    split one build across two folders. So a redirect any process sees is remembered for this computer
    (WIN_KEY in _local/pivots.json, inside the engine folder, which no package redirects), and every later
    process on this PC builds in the staging folder too, while that Store package is still installed. The
    package gone (Claude moved to the regular installer): forgotten, back to CapCut's own folder."""
    if "pkg" in _cache:
        return _cache["pkg"]
    pkg = None
    _cache["pkg_remembered"] = False
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        la = os.environ["LOCALAPPDATA"]
        pkg = _probe_store()
        fb = _fallbacks()
        seen = None
        try:
            seen = fb.remembered(WIN_KEY) if fb else None
        except Exception:
            seen = None
        if pkg:
            if fb and seen != pkg:
                try:
                    fb.remember(WIN_KEY, pkg, why="a new folder the engine made in AppData landed in the Microsoft "
                                                  "Store Claude app's private copy")
                    fb.note("capcut-drafts", f"Claude runs as a Microsoft Store app ({pkg}): drafts build in "
                            f"projects/_capcut-staging and go into CapCut with \"{BAT_NAME}\"")
                except Exception:
                    pass
        elif isinstance(seen, str) and seen:
            if os.path.isdir(os.path.join(la, "Packages", seen)):
                pkg = seen                     # another Python on this PC runs inside the package: agree with it
                _cache["pkg_remembered"] = True
            elif fb:
                try:
                    fb.forget(WIN_KEY)
                    fb.note("capcut-drafts", f"the Microsoft Store Claude app ({seen}) is no longer installed; "
                            "drafts go straight into CapCut's own folder")
                except Exception:
                    pass
    _cache["pkg"] = pkg
    return pkg


def mac_real_root():
    """CapCut's own drafts folder on a Mac."""
    return os.path.expanduser("~/Movies/" + REL_DRAFTS)


def _fallbacks():
    """product/fallbacks.py, or None. Never raises: the memory is a convenience, never a gate."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import fallbacks
        return fallbacks
    except Exception:
        return None


def _engine_test_on_real_home():
    """True for one of the engine's own tests (product/tests) running against the account's real home folder.
    Those tests import the draft writers for other reasons; they must never make anything in her real Movies
    folder. A test that points HOME at a temp folder still gets the probe, there."""
    try:
        import pwd
        real_home = pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        return False
    main = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    in_tests = main.startswith(os.path.join(HERE, "tests") + os.sep) or "pytest" in sys.modules
    return in_tests and os.path.realpath(os.path.expanduser("~")) == os.path.realpath(real_home)


def mac_probe():
    """True when this Mac refuses THIS Python a write in ~/Movies ("Operation not permitted").

    Mac only; False everywhere else. Probed once per process, because draft_safety.CAP (and every writer's
    CAP) is decided when the module loads. Why it is safe: it makes ONE uniquely named hidden folder directly in
    ~/Movies and removes it at once. That is the folder the shield guards (it guards Movies, Music and Pictures
    as wholes), so it answers the real question without touching anything inside CapCut's own folder, where
    CapCut could notice it. It uses the same expanduser("~") as the rest of this module, so a test with a temp
    HOME probes in there, and the engine's own tests on the real home never probe at all. Only a refusal
    (PermissionError) counts; any other failure answers False, the usual route, because the probe is a safety
    net, never a gate."""
    if "mac_probe" in _cache:
        return _cache["mac_probe"]
    blocked = False
    if sys.platform == "darwin" and not _engine_test_on_real_home():
        d = os.path.expanduser("~/Movies")
        if os.path.isdir(d):
            made = os.path.join(d, f".ree-write-probe-{uuid.uuid4().hex[:12]}")
            try:
                os.mkdir(made)
            except PermissionError:
                blocked = True
            except Exception:
                blocked = False
            else:
                try:
                    os.rmdir(made)
                except Exception:
                    pass
    _cache["mac_probe"] = blocked
    return blocked


def mac_drafts_blocked():
    """True when drafts on this Mac must build in the staging folder. Decided once per run.

    Refused by the probe: remember it for this computer and leave one line for /report-a-problem. Remembered
    from a refused VectCut save ("save"): stay on staging even though this Python may write, because the save
    runs in VectCut's own process. Remembered from an earlier probe but allowed now (the shield was told about
    the engine, or removed): forget it and go back to CapCut's own folder."""
    if "mac_route" in _cache:
        return _cache["mac_route"]
    route = False
    if sys.platform == "darwin":
        fb = _fallbacks()
        seen = fb.remembered(MAC_KEY) if fb else None
        if mac_probe():
            route = True
            if seen is None and fb:
                fb.remember(MAC_KEY, "probe", why="this Mac refuses the engine's Python a write in ~/Movies")
                fb.note("capcut-drafts", "this Mac refused the engine's Python a write in CapCut's projects folder "
                        "(Operation not permitted; usually a security app protecting Movies); drafts build in "
                        f"projects/_capcut-staging and go into CapCut with \"{COMMAND_NAME}\"")
        elif seen == "save":
            route = True
        elif seen is not None and fb:
            fb.forget(MAC_KEY)
            fb.note("capcut-drafts", "the engine's Python may write in CapCut's projects folder again; drafts go "
                    "straight into CapCut")
    _cache["mac_route"] = route
    return route


def staging_root():
    """Where drafts are built while redirected (forward slashes, like every other CapCut path in the engine)."""
    return os.path.join(STAGING_DIR, "com.lveditor.draft").replace("\\", "/")


def drafts_root():
    """The one answer every draft writer uses. CAPCUT_DRAFTS_ROOT wins (a deliberate override); a redirected
    Store app gets the staging folder; everyone else gets CapCut's real folder."""
    forced = os.environ.get("CAPCUT_DRAFTS_ROOT")
    if forced:
        return forced.replace("\\", "/")
    if os.name != "nt":
        if mac_drafts_blocked():
            root = staging_root()
            try:
                os.makedirs(root, exist_ok=True)
                write_installer()
            except Exception:
                pass
            _stage_from_env(root)
            return root
        return mac_real_root()
    if detect():
        root = staging_root()
        try:
            os.makedirs(root, exist_ok=True)
            write_installer()
        except Exception:
            pass
        return root
    return real_root()


STAGED_FROM = ".engine-staged-from.json"   # inside a staged copy of a draft she already has


def _mac_staging(root):
    return sys.platform == "darwin" and os.name != "nt" and is_staging(root)


def lookup_roots(root=None):
    """Where a draft she already has can be: the writers' root first, then, on a Mac that keeps the engine out
    of Movies, CapCut's own folder (read only). Everywhere else just the writers' root, as before."""
    root = root or drafts_root()
    return [root, mac_real_root()] if _mac_staging(root) else [root]


def find_draft(name, root=None):
    """Folder of the draft called `name`, for READING. Staging first, then CapCut's own folder on a blocked Mac.
    A name found nowhere answers the usual path, so the caller says "no draft named ..." as before."""
    root = root or drafts_root()
    for r in lookup_roots(root):
        p = os.path.join(r, name)
        if os.path.isdir(p):
            return p
    return os.path.join(root, name)


def stage_existing(name, root=None, reference=False, quiet=False):
    """The folder a tool should CHANGE for the draft called `name`. Everywhere but a blocked Mac that is simply
    <root>/<name>, unchanged.

    On a Mac that keeps the engine out of Movies, a draft she already has in CapCut is copied (read from
    CapCut's folder, written into the staging folder) and its paths are pointed at the copy. The tool changes
    the copy; "Add to CapCut.command" brings it in as a NEW version and never touches hers (rule 7). The copy
    is reused while her draft is unchanged, so several tools can layer onto it; if she changed hers in CapCut
    since, the old copy is moved aside (never deleted) and hers is copied fresh. `reference` marks a draft that
    is only read (a template): the installer never brings that one in."""
    root = root or drafts_root()
    here = os.path.join(root, name)
    if not name or not _mac_staging(root):
        return here
    real = mac_real_root()
    src = os.path.join(real, name)
    if not os.path.isdir(src):
        return here                       # built in staging by the engine, or not a draft: the tool says so
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import install_to_capcut as shared
    if os.path.isdir(here):
        mark = shared.load(os.path.join(here, STAGED_FROM), None)
        if not isinstance(mark, dict):
            return here                   # the engine built this one in staging itself
        if mark.get("real_fp") == shared.fingerprint(src):
            return here                   # hers is unchanged since the copy: keep building on the copy
        aside = os.path.join(STAGING_DIR, "_replaced", f"{name} {time.strftime('%Y%m%d-%H%M%S')}")
        os.makedirs(os.path.dirname(aside), exist_ok=True)
        shutil.move(here, aside)
    shutil.copytree(src, here)
    shared.rewrite_folder(here, real, root)
    with open(os.path.join(here, STAGED_FROM), "w", encoding="utf-8") as fh:
        json.dump({"from": name, "real_fp": shared.fingerprint(src), "copied_fp": shared.fingerprint(here),
                   "reference": bool(reference), "at": time.strftime("%Y-%m-%d %H:%M")}, fh)
    # Her list entry comes along (cover, duration, timestamps), pointed at the copy, so the installer registers
    # the new version with everything CapCut shows for hers.
    entry = next((e for e in (shared.load(os.path.join(real, "root_meta_info.json"), {}) or {})
                  .get("all_draft_store", []) if e.get("draft_name") == name), None)
    if entry:
        rp = os.path.join(root, "root_meta_info.json")
        reg = shared.load(rp, None) or shared.new_registry(root)
        shared.put_on_top(reg, json.loads(shared.rewrite_text(json.dumps(entry, ensure_ascii=False), real, root)),
                          name)
        with open(rp, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, ensure_ascii=False)
    if not reference and not quiet:
        print(f"  This Mac does not let the engine save into your Movies folder, so this change is made on a copy "
              f"of \"{name}\" in the engine's folder. When it is done, quit CapCut and double-click "
              f"\"{COMMAND_NAME}\" in {STAGING_DIR}: it goes in as a new version, and your \"{name}\" stays "
              "exactly as it is.")
    return here


def _stage_from_env(root):
    """Every tool that layers onto a draft she has names it with CAPCUT_DRAFT (and borrows from CAPCUT_TEMPLATE),
    and builds its path from drafts_root() right away. So on a blocked Mac the copy is made here, once per run,
    before the tool looks. Never fatal: a copy that fails leaves the tool to say the draft is missing."""
    if _cache.get("env_staged"):
        return
    _cache["env_staged"] = True
    draft = os.environ.get("CAPCUT_DRAFT", "").strip()
    template = os.environ.get("CAPCUT_TEMPLATE", "").strip()
    for name, ref in ((draft, False), (template, True)):
        if not name or (ref and name == draft):
            continue
        try:
            stage_existing(name, root, reference=ref)
        except Exception as e:
            print(f"  Could not copy \"{name}\" out of CapCut's folder ({type(e).__name__}: {e}).", file=sys.stderr)


def is_staging(root):
    return os.path.normcase(os.path.abspath(root)) == os.path.normcase(os.path.abspath(staging_root()))


# Which Python runs the copy, in order. The engine's own editing-engine Python comes first: setup built it, so it
# is real on every machine that has made a draft. `python` comes last because on a stock PC it can be the
# Microsoft Store stand-in, which prints an install hint and copies nothing. Each candidate is run once (-c "")
# before it is trusted, the same "does it RUN" test _python3-shim.sh uses. This folder is
# projects/_capcut-staging, so the engine's Python is two folders up.
_BAT = r"""@echo off
rem Copies the drafts the engine built into CapCut. Double-click this in File Explorer, with CapCut closed.
rem The engine also starts it by itself after a build (through Explorer, so it runs outside the Claude app);
rem then install_to_capcut.py exits 75 and this window closes without waiting for a key.
cd /d "%~dp0"
set "REE_PY=%~dp0..\..\product\engine\VectCutAPI\venv-capcut\Scripts\python.exe"
if exist "%REE_PY%" (
  "%REE_PY%" -c "" >nul 2>nul
  if not errorlevel 1 (
    "%REE_PY%" install_to_capcut.py %*
    goto done
  )
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 install_to_capcut.py %*
  goto done
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if exist "%%~D\python.exe" (
    "%%~D\python.exe" install_to_capcut.py %*
    goto done
  )
)
python install_to_capcut.py %*
:done
if "%ERRORLEVEL%"=="75" exit /b 0
echo.
pause
"""


# The Mac double-click. Python (any that runs, the engine's own first) only PREPARES, inside the engine's own
# folder: it checks CapCut is quit, picks each project's name (a name already in CapCut goes in as the next
# version), and assembles each finished project, paths rewritten, in _ready/. Every write into CapCut's folder
# is then Apple's own /bin/mv (and /bin/cp for the backup), which the protected-folders shield lets through.
# A move is one step, so a half-copied project never sits in CapCut's folder, and nothing there is ever
# deleted. CapCut's list is changed last, only when every project landed, after a backup. A name that turns up
# in CapCut between the two steps is left alone.
_COMMAND = r"""#!/bin/bash
# Adds the projects the engine built to CapCut. Double-click this in Finder, with CapCut quit.
cd "$(dirname "$0")" || exit 1
done_() { echo; if [ -t 0 ]; then read -r -p "Press Return to close this window. " _; fi; exit "$1"; }
echo "Add to CapCut"
echo "-------------"
PY=""
for c in "../../product/engine/VectCutAPI/venv-capcut/bin/python" "$HOME/.local/bin/python3" \
         "/opt/homebrew/bin/python3" "/usr/local/bin/python3"; do
  if [ -x "$c" ] && "$c" -c "" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ] && /usr/bin/xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c "" >/dev/null 2>&1; then
  PY=/usr/bin/python3
fi
if [ -z "$PY" ]; then
  echo "I could not find Python on this Mac to prepare the projects. Type /report-a-problem in Claude."
  done_ 1
fi
"$PY" add_to_capcut_mac.py prepare || done_ 1
PLAN="_ready/plan.txt"
[ -f "$PLAN" ] || done_ 1
REAL="$(/usr/bin/head -n 1 "$PLAN")"
if pgrep -x CapCut >/dev/null 2>&1; then
  echo "CapCut is open. Quit CapCut (Cmd+Q), then double-click this again."
  done_ 1
fi
/bin/mkdir -p "$REAL" || { echo "I could not reach CapCut's projects folder. Type /report-a-problem in Claude."; done_ 1; }
failed=0
while IFS= read -r target; do
  [ -n "$target" ] || continue
  if [ -e "$REAL/$target" ]; then
    echo "  = kept    $target (a project with this name just appeared in CapCut; it was left exactly as it is)"
    failed=1
    continue
  fi
  if /bin/mv "_ready/drafts/$target" "$REAL/$target"; then
    echo "  + added   $target"
  else
    echo "  ! could not add $target"
    failed=1
  fi
done < <(/usr/bin/tail -n +2 "$PLAN")
if [ "$failed" = 0 ] && [ -f "_ready/root_meta_info.json" ]; then
  if [ -f "$REAL/root_meta_info.json" ]; then
    /bin/cp "$REAL/root_meta_info.json" "$REAL/root_meta_info.json.before-engine-$(/bin/date +%Y%m%d-%H%M%S).bak" || failed=1
  fi
  if [ "$failed" = 0 ]; then
    /bin/mv -f "_ready/root_meta_info.json" "$REAL/root_meta_info.json" || failed=1
    [ "$failed" = 0 ] && echo && echo "Done. Open CapCut: your new project is at the top of the list."
  fi
fi
if [ "$failed" != 0 ]; then
  echo
  echo "Not everything went in. Double-click this again; if it says this twice, type /report-a-problem in Claude."
  done_ 1
fi
done_ 0
"""


def write_installer():
    """Put the double-click installer beside the staged drafts. Rewritten every time so it is never stale.
    Windows gets "Add to CapCut.bat"; a Mac gets "Add to CapCut.command" (runnable, Unix line endings)."""
    os.makedirs(STAGING_DIR, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "install_to_capcut.py"), os.path.join(STAGING_DIR, "install_to_capcut.py"))
    if os.name != "nt":
        shutil.copyfile(os.path.join(HERE, "add_to_capcut_mac.py"), os.path.join(STAGING_DIR, "add_to_capcut_mac.py"))
        cmd = os.path.join(STAGING_DIR, COMMAND_NAME)
        with open(cmd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_COMMAND)
        os.chmod(cmd, 0o755)
        return
    with open(os.path.join(STAGING_DIR, BAT_NAME), "w", encoding="ascii", newline="\r\n") as fh:
        fh.write(_BAT)


def handoff_lines(name):
    """What she reads after a build that landed in staging. Plain words, the one action, where to click."""
    if os.name != "nt":
        return [
            f"  One more step to see \"{name}\" in CapCut: this Mac does not let the engine save into your Movies "
            "folder (usually a security app protecting it), so the project is ready in this folder:",
            f"       {STAGING_DIR}",
            f"     Quit CapCut, then double-click \"{COMMAND_NAME}\" in that folder. It adds the project to "
            "CapCut and never replaces one you already have. Then open CapCut.",
        ]
    folder = STAGING_DIR.replace("/", "\\")
    return [
        f"  ⚠  One more step to see \"{name}\" in CapCut.",
        "     The Claude app you are using comes from the Microsoft Store, and Windows keeps anything it writes",
        "     inside CapCut's folder private to Claude, so CapCut cannot see it. The project is ready in this folder:",
        f"       {folder}",
        f"     Close CapCut, then double-click \"{BAT_NAME}\" in that folder. It copies the project into",
        "     CapCut and never replaces one you already have. Then open CapCut.",
    ]


AUTO_DONE_LINE = "It's in CapCut, at the top of your list"   # finish.py reads it: no double-click to show
AUTO_WAIT_START = 25        # seconds for the shell to start the .bat and the script to say it is running
AUTO_WAIT_DONE = 15 * 60    # once it runs: a project with big media can take minutes to copy
_pending = []               # drafts this process built in staging, handed over when it ends


def auto_add(names, launch=None, running=None, sleep=time.sleep, clock=time.monotonic):
    """Bring the staged drafts `names` into CapCut without her double-click. (True, "") when every one of them
    is in CapCut; (False, why) otherwise, and then nothing has changed that the double-click cannot finish.

    Windows only. CapCut must be closed by the engine's own check (draft_safety.capcut_running) before anything
    starts; the installer checks again itself. `launch`, `running`, `sleep` and `clock` are for the tests."""
    if os.name != "nt":
        return False, "not-windows"
    if os.environ.get("REE_AUTO_ADD") == "0":
        return False, "off"
    if running is None:
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import draft_safety
            running = draft_safety.capcut_running
        except Exception:
            return False, "could-not-check"
    state = running()
    if state is not False:
        return False, "capcut-open" if state else "could-not-check"
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import install_to_capcut as inst
    req = os.path.join(STAGING_DIR, inst.AUTO_REQUEST)
    res = os.path.join(STAGING_DIR, inst.AUTO_RESULT)
    bat = os.path.normpath(os.path.join(STAGING_DIR, BAT_NAME))
    token = uuid.uuid4().hex
    try:
        write_installer()
        if os.path.exists(res):
            os.remove(res)
        inst._write_json(req, {"token": token, "at": time.time(), "names": list(names)})
    except Exception as e:
        return False, f"no-request ({type(e).__name__})"
    try:
        # Explorer hands the file to the shell that is already running, outside the Store package. Its own exit
        # code means nothing (it answers 1 on success), so only a failure to start it at all counts.
        (launch or (lambda p: subprocess.run(["explorer.exe", p], capture_output=True, timeout=30)))(bat)
    except Exception as e:
        _drop(req)
        return False, f"no-launch ({type(e).__name__})"
    deadline, got, started = clock() + AUTO_WAIT_START, None, False
    while True:
        r = inst.load(res, None)
        if isinstance(r, dict) and r.get("token") == token:
            if r.get("status") != "running":
                got = r
                break
            if not started:                   # it is running: give the copy its time
                started = True
                deadline = clock() + AUTO_WAIT_DONE
        if clock() > deadline:
            break
        sleep(0.5)
    if got is None:
        _drop(req)          # never let a late start pass for an automatic run: her double-click pauses as always
        return False, "still-copying" if started else "no-start"
    if got.get("status") != "done":
        return False, f"{got.get('status')}:{got.get('reason')}"
    missing = [n for n in names if n not in (got.get("installed") or [])]
    if missing:
        return False, "not-installed:" + ", ".join(missing)
    return True, ""


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def after_build(name):
    """register_draft calls this for every draft that landed in staging. On Windows the handoff waits for the
    build process to end, so every write the build makes is done before anything is copied into CapCut; on a
    Mac the double-click instructions show right away, as before."""
    write_installer()
    if os.name != "nt":
        print()
        for ln in handoff_lines(name):
            print(ln)
        open_folder()
        return
    if name not in _pending:
        _pending.append(name)
    if not _cache.get("atexit"):
        _cache["atexit"] = True
        atexit.register(finish_handoff)
        prev = sys.excepthook

        def hook(exc_type, exc, tb):          # a build that crashed hands over nothing automatically
            _cache["crashed"] = True
            prev(exc_type, exc, tb)
        sys.excepthook = hook


def finish_handoff(**auto_kw):
    """Hand this process's staged drafts to CapCut: automatically when that works, else the double-click. Runs
    once, when the build process ends (atexit); safe to call by hand. Never raises."""
    names = list(_pending)
    del _pending[:]
    if not names:
        return
    try:
        ok, why = (False, "build-stopped") if _cache.get("crashed") else auto_add(names, **auto_kw)
    except Exception as e:
        ok, why = False, f"error ({type(e).__name__})"
    if ok:
        print()
        print(f"  {AUTO_DONE_LINE}: " + ", ".join(f'"{n}"' for n in names) + ".")
        return
    if why not in ("off", "not-windows"):
        fb = _fallbacks()
        if fb:
            try:
                fb.note("capcut-drafts", f"automatic Add to CapCut did not finish ({why}); she was shown the "
                        "double-click instead")
            except Exception:
                pass
    print()
    for n in names:
        for ln in handoff_lines(n):
            print(ln)
    open_folder()


def open_folder(force=False):
    """Show her the staging folder in File Explorer. Explorer runs outside the Store package, so the
    double-click she makes there escapes the redirect. On a Mac, Finder opens with the .command selected.
    `force`: her own click on the page opens it every time."""
    if _cache.get("opened") and not force:
        return
    _cache["opened"] = True
    try:
        if os.name == "nt":
            os.startfile(STAGING_DIR)   # noqa: S606 — her own engine folder
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", "-R", os.path.join(STAGING_DIR, COMMAND_NAME)], capture_output=True, timeout=10)
    except Exception:
        pass


def save_refused_message(save_result, root):
    """Plain words for a VectCut save that left no project behind, so a build never ends on a bare
    FileNotFoundError from the rename that follows. A refused write on a Mac is remembered ("save"), so the next
    build goes to the staging folder by itself."""
    err = str((save_result or {}).get("error") or "")
    refused = any(k in err for k in ("Operation not permitted", "PermissionError", "Permission denied",
                                     "Errno 1]", "Errno 13]"))
    if refused and sys.platform == "darwin":
        fb = _fallbacks()
        if fb:
            fb.remember(MAC_KEY, "save", why="VectCut's save into ~/Movies was refused (Operation not permitted)")
            fb.note("capcut-drafts", "VectCut's save into CapCut's projects folder was refused (Operation not "
                    "permitted); the next build goes to projects/_capcut-staging")
        return (f"This Mac would not let the engine save the project into CapCut's folder ({root}): Operation "
                "not permitted. That is usually a security app protecting your Movies folder. Nothing of yours "
                "was changed. Run the build again: from now on the engine builds the project in its own folder "
                f"and leaves \"{COMMAND_NAME}\" for you to double-click.")
    if refused:
        return (f"CapCut's projects folder refused the save ({root}): permission denied. Nothing of yours was "
                "changed. Type /report-a-problem in Claude.")
    return (f"VectCut did not save the project into {root} ({err[:200] or 'no reason given'}), so there is "
            "nothing to finish. Nothing of yours was changed. Type /report-a-problem in Claude.")


if __name__ == "__main__":
    if sys.platform == "darwin":
        if "--recheck" in sys.argv[1:]:          # forget what this Mac learned and probe again
            fb = _fallbacks()
            if fb:
                fb.forget(MAC_KEY)
        if mac_drafts_blocked():
            print(f"redirected: yes (this Mac refuses the engine a write in ~/Movies). Drafts build in "
                  f"{staging_root()} and go into CapCut with \"{COMMAND_NAME}\".")
        else:
            print("redirected: no. Drafts go straight into CapCut's own folder.")
        sys.exit(0)
    if "--recheck" in sys.argv[1:]:              # forget what this PC learned and probe again
        fb = _fallbacks()
        if fb:
            fb.forget(WIN_KEY)
    pkg = detect()
    if pkg:
        how = (" remembered: another Python on this PC runs inside the Store app, so every build agrees"
               if _cache.get("pkg_remembered") else "")
        print(f"redirected: yes ({pkg}{';' + how if how else ''}). Drafts build in {staging_root()} and go into "
              f"CapCut with \"{BAT_NAME}\".")
    else:
        print("redirected: no. Drafts go straight into CapCut's own folder.")
