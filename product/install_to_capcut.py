#!/usr/bin/env python3
"""install_to_capcut.py — copy drafts the engine built in projects/_capcut-staging/ into CapCut.

Used on Windows when Claude runs as a Microsoft Store app: Windows keeps new files that app writes into
CapCut's folder private to the app, so the engine builds drafts here instead (product/capcut_store_redirect.py)
and the creator double-clicks "Add to CapCut.bat", which runs this from File Explorer, outside the Store app.
The Mac twin (add_to_capcut_mac.py, run by "Add to CapCut.command") shares the registration helpers below
(new_registry, registry_entry, put_on_top), so a project lands in CapCut's list the same way on both.

Rules, in order of importance:
  • CapCut must be closed. CapCut rewrites its list of projects on exit and would drop what we add.
  • Never replace a project she has changed in CapCut. A project already in CapCut is updated ONLY when this
    script put it there and CapCut has not changed it since (a fingerprint is kept inside the project).
  • Back up CapCut's list of projects (root_meta_info.json) before changing it.
  • Rewrite the paths inside each project from the staging folder to CapCut's folder.

THE AUTOMATIC RUN. After a build lands in staging the engine asks for this itself: it leaves a request file
(AUTO_REQUEST: a one-time token and the time) beside this script and hands "Add to CapCut.bat" to the Windows
shell with `explorer.exe`, which runs it OUTSIDE the Store package, exactly like her double-click. Explorer
cannot pass arguments, so the fresh request file is what says "automatic": no "press a key" pause, and a result
file (AUTO_RESULT, also in this folder, never AppData, so nothing redirects it) that says what went in or why
it refused. The engine waits for that file; anything but a clean "done" falls back to the double-click.
A request older than AUTO_FRESH seconds is ignored, so a later double-click of hers always pauses as before.

Standard library only, so it runs on any Python she has. Safe to run twice: the second run changes nothing.
"""
import hashlib, json, os, re, shutil, subprocess, sys, time, uuid, glob

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(HERE, "com.lveditor.draft")
REL = os.path.join("CapCut", "User Data", "Projects", "com.lveditor.draft")
MARK = ".engine-installed.json"
JSONS = ("draft_content.json", "draft_info.json")
AUTO_REQUEST = ".auto-request.json"   # written by the engine right before it hands the .bat to Explorer
AUTO_RESULT = ".auto-result.json"     # written here: "running", then "done" / "refused" / "error"
AUTO_FRESH = 120                      # seconds a request counts; older ones are leftovers, never honored
AUTO_EXIT = 75                        # the .bat's cue to close without "press a key" (an automatic run)
LOCK = ".add-to-capcut.lock"          # one copy at a time, whoever started it
LOCK_STALE = 30 * 60                  # a lock this old belongs to a run that died; take it over


class Refused(SystemExit):
    """A refusal with a reason the automatic run can report (inside-package, capcut-open, ...). Still a
    SystemExit carrying the same sentence, so a double-click prints exactly what it always did."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def refuse(reason, message):
    raise Refused(reason, message)


def say(msg=""):
    print(msg, flush=True)


def capcut_running():
    try:
        r = subprocess.run(["tasklist"], capture_output=True)   # bytes: tasklist is not UTF-8 off English Windows
    except Exception:
        return None
    return None if r.returncode != 0 else b"CapCut.exe" in (r.stdout or b"")


# One line per CapCut process: id | start time (UTC, ISO) | main window handle | responding | CPU ms.
# Every field that Windows refuses to read comes back EMPTY, never as 0: an unreadable CPU time read as 0 would
# make a busy CapCut look idle, and that is the one mistake this check must never make. "END" proves the
# script ran to the end, so a PowerShell that died halfway is "could not check", not "no CapCut".
_PS_PROCS = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-Process | Where-Object { $_.ProcessName -eq 'CapCut' } | ForEach-Object {"
    " $s=''; try { if ($_.StartTime -ne $null) { $s=$_.StartTime.ToUniversalTime().ToString('o') } } catch {};"
    " $w=''; try { $w=[string][int64]$_.MainWindowHandle } catch {};"
    " $r=''; try { $r=[string]$_.Responding } catch {};"
    " $c=''; try { $t=$_.TotalProcessorTime; if ($t -ne $null) { $c=[string][int64]$t.TotalMilliseconds } } catch {};"
    " Write-Output ('{0}|{1}|{2}|{3}|{4}' -f $_.Id,$s,$w,$r,$c) };"
    "Write-Output 'END'"
)


def capcut_processes(timeout=20):
    """Every running CapCut.exe as a dict (pid, start, window, responding, cpu_ms), [] when there is none, or
    None when the question could not be answered. Windows only (None elsewhere). Standard library only, so the
    double-click installer and the engine can share it (draft_safety imports it from here).

    Unknown fields stay None: window None means "could not read", not "no window"."""
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", _PS_PROCS], capture_output=True, timeout=timeout)
    except Exception:
        return None
    lines = (r.stdout or b"").decode("ascii", errors="replace").splitlines()
    if "END" not in [ln.strip() for ln in lines]:
        return None
    out = []
    for ln in lines:
        parts = ln.strip().split("|")
        if len(parts) != 5 or not parts[0].isdigit():
            continue
        pid, start, win, resp, cpu = parts
        out.append({
            "pid": int(pid),
            "start": start or None,
            "window": int(win) if win.lstrip("-").isdigit() else None,
            "responding": {"True": True, "False": False}.get(resp),
            "cpu_ms": int(cpu) if cpu.isdigit() else None,
        })
    return out


def stuck_capcut(sample_seconds=5, probe=None, sleep=time.sleep):
    """True only when EVERY running CapCut.exe is provably stuck, so it can never save over CapCut's list.

    Measured, and conservative on purpose: the same processes are seen twice, `sample_seconds` apart, and each
    one has no window both times (Windows' own main-window handle is 0) AND used no processor time at all in
    between. A live CapCut, even minimized, has a window; a CapCut busy closing or saving uses the processor.
    "Not Responding" is not used: Windows reports a windowless process as responding no matter what, so it says
    nothing about the processes this is about. Anything unreadable, a process that came or went, or any process
    with a window or any work done answers False. None when the processes could not be listed at all.
    `probe` and `sleep` are for the tests."""
    probe = probe or capcut_processes
    first = probe()
    if not first:
        return None if first is None else False
    sleep(sample_seconds)
    second = probe()
    if not second:
        return None if second is None else False
    before = {p["pid"]: p for p in first}
    after = {p["pid"]: p for p in second}
    if set(before) != set(after):
        return False
    for pid, a in after.items():
        b = before[pid]
        if a["window"] != 0 or b["window"] != 0:
            return False
        if a["cpu_ms"] is None or b["cpu_ms"] is None or a["cpu_ms"] != b["cpu_ms"]:
            return False
        if a["start"] != b["start"]:
            return False
    return True


def note_fallback(message):
    """One line in the engine's _local/fallbacks.log, for /report-a-problem. This script runs from
    projects/_capcut-staging (the engine's product/ is two folders up) or from product/ itself. Never raises."""
    for d in (HERE, os.path.join(HERE, "..", "..", "product")):
        if os.path.isfile(os.path.join(d, "fallbacks.py")):
            try:
                sys.path.insert(0, os.path.abspath(d))
                import fallbacks
                fallbacks.note("add-to-capcut", message)
            except Exception:
                pass
            return


def inside_store_app():
    """True when this was started from inside the Store app (then it would be redirected too)."""
    la = os.environ.get("LOCALAPPDATA", "")
    probe = f".ree-store-probe-{uuid.uuid4().hex[:12]}"
    made = os.path.join(la, probe)
    try:
        os.makedirs(made, exist_ok=True)
        return bool(glob.glob(os.path.join(la, "Packages", "*", "LocalCache", "Local", probe)))
    except Exception:
        return False
    finally:
        try:
            os.rmdir(made)
        except Exception:
            pass


def _variants(path):
    """The spellings a Windows path takes inside CapCut's JSON: forward slashes, raw backslashes, and the
    JSON-escaped double backslash. Longest first so a shorter form never eats part of a longer one."""
    p = os.path.abspath(path)
    fwd, bk = p.replace("\\", "/"), p.replace("/", "\\")
    return [bk.replace("\\", "\\\\"), bk, fwd]


def rewrite_text(text, src, dst):
    for s, d in zip(_variants(src), _variants(dst)):
        text = re.sub(re.escape(s), lambda _m, d=d: d, text, flags=re.IGNORECASE)
    return text


def draft_json(folder):
    for n in JSONS:
        if os.path.isfile(os.path.join(folder, n)):
            return os.path.join(folder, n)
    return None


def fingerprint(folder):
    p = draft_json(folder)
    if not p:
        return None
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rewrite_folder(folder, src, dst):
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            if not f.endswith(".json") or f == MARK:
                continue
            fp = os.path.join(dirpath, f)
            try:
                with open(fp, encoding="utf-8") as fh:
                    t = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            n = rewrite_text(t, src, dst)
            if n != t:
                with open(fp, "w", encoding="utf-8") as fh:
                    fh.write(n)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def new_registry(real):
    """CapCut's list of projects as it looks before CapCut has ever saved one."""
    return {"all_draft_store": [], "draft_ids": 0, "root_path": real.replace("\\", "/")}


def registry_entry(staged_entry, name, dst, real, rewrite=None):
    """The list entry for a project now at `dst` in CapCut's folder `real`. The staged entry (what the engine
    registered while building) is reused with its paths rewritten by `rewrite`; with none, a minimal one is
    made. Shared by the Windows and Mac installers so both register a project exactly the same way."""
    if staged_entry:
        e = json.loads(rewrite(json.dumps(staged_entry, ensure_ascii=False)))
    else:
        fwd = dst.replace("\\", "/")
        e = {"draft_name": name, "draft_fold_path": fwd, "draft_root_path": real.replace("\\", "/"),
             "draft_json_file": draft_json(dst).replace("\\", "/"), "draft_cover": fwd + "/draft_cover.jpg"}
    now = int(time.time() * 1_000_000)
    e["tm_draft_modified"] = now
    e.setdefault("tm_draft_create", now)
    return e


def put_on_top(reg, e, name):
    """Replace any entry with this name and put the new one first, where CapCut shows it at the top."""
    reg["all_draft_store"] = [x for x in reg.get("all_draft_store", []) if x.get("draft_name") != name]
    reg["all_draft_store"].insert(0, e)


def _here():
    """The staging folder: where the projects wait, and where the request, result and lock files live."""
    return os.path.dirname(STAGE)


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def take_auto_request(now=None):
    """The token of a fresh automatic request (and the request is used up), or None for a double-click."""
    p = os.path.join(_here(), AUTO_REQUEST)
    req = load(p, None)
    if req is None:
        return None
    try:
        os.remove(p)
    except OSError:
        pass
    now = time.time() if now is None else now
    try:
        fresh = 0 <= now - float(req.get("at", 0)) <= AUTO_FRESH
    except (TypeError, ValueError, AttributeError):
        fresh = False
    return (str(req.get("token") or "") or None) if fresh else None


def _pid_alive(pid):
    """True / False for a process id on Windows, None when Windows would not say. Read only: tasklist."""
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH", "/FO", "CSV"], capture_output=True,
                           timeout=15)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return f'"{int(pid)}"'.encode() in (r.stdout or b"")


def _lock():
    """Take the one-at-a-time lock. False when another copy is running right now (her double-click and the
    automatic run together would race on the same folders). A lock left by a window she closed mid-copy is
    taken over as soon as its process is gone (or, when Windows will not say, once it is LOCK_STALE old), so a
    leftover lock is never a dead end."""
    p = os.path.join(_here(), LOCK)
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                with open(p, encoding="ascii", errors="replace") as fh:
                    owner = fh.read().strip()
                alive = _pid_alive(owner) if owner.isdigit() else False
                if alive or (alive is None and time.time() - os.path.getmtime(p) < LOCK_STALE):
                    return False
                os.remove(p)
            except OSError:
                return False
        except OSError:
            return True        # the folder will not take a lock file: go on as before, never a dead end
    return False


def _unlock():
    try:
        os.remove(os.path.join(_here(), LOCK))
    except OSError:
        pass


def main():
    """Copy what is waiting into CapCut. Answers what happened ({"added": [...], ...}); a refusal raises
    Refused (a SystemExit with the sentence she reads)."""
    say("Add to CapCut")
    say("-------------")
    if os.name != "nt":
        refuse("not-windows", "This only runs on Windows.")
    if not os.path.isdir(STAGE):
        refuse("nothing-staged", "Nothing to add: there are no projects waiting in this folder.")
    if inside_store_app():
        refuse("inside-package", "Please run this by double-clicking \"Add to CapCut.bat\" in File Explorer. Started "
               "from inside the Claude app, Windows would hide the copy from CapCut again.")
    if not _lock():
        refuse("already-running", "Add to CapCut is already running in another window. Let it finish, then open "
               "CapCut.")
    try:
        return _install()
    finally:
        _unlock()


def _install():
    running = capcut_running()
    if running is None:
        # tasklist did not answer. Ask Windows a second way before giving up: a clean, complete PowerShell list
        # with no CapCut in it is a real "closed".
        procs = capcut_processes()
        if procs == []:
            note_fallback("tasklist did not answer; PowerShell's process list showed no CapCut, so the copy went ahead")
            running = False
        elif procs:
            running = True
    if running is None:
        refuse("could-not-check", "I could not check whether CapCut is open: Windows did not answer when I asked for the list of "
                 "running programs. Close CapCut if it is open, then double-click this again. If this message "
                 "comes back, restart the computer (Start > Power > Restart) and try once more. If it still comes "
                 "back, type /report-a-problem in Claude.")
    if running:
        # A CapCut.exe that is stuck (no window, no work at all) cannot save anything, so it cannot write over
        # CapCut's list. One that a forced close cannot end (Access denied, even as administrator) would
        # otherwise block this forever. Decided fresh on every run and never remembered: next time it is
        # measured again.
        say("CapCut is listed as running. Checking whether it is really open (5 seconds)...")
        if stuck_capcut() is not True:
            refuse("capcut-open", "CapCut is open. Close CapCut completely, then double-click this again.")
        say("CapCut is listed as running, but it has no window and did no work at all for 5 seconds: it is stuck")
        say("and cannot save anything, so it cannot undo this. Adding your project now.")
        say("(A restart clears the stuck CapCut: Start > Power > Restart.)")
        note_fallback("every CapCut.exe was stuck (no window, no processor time over 5s); copied into CapCut anyway")

    real = os.path.join(os.environ["LOCALAPPDATA"], REL)
    os.makedirs(real, exist_ok=True)
    reg_path = os.path.join(real, "root_meta_info.json")
    reg = load(reg_path, None)
    started = reg is None
    if started:
        reg = new_registry(real)
    staged_reg = load(os.path.join(STAGE, "root_meta_info.json"), {}).get("all_draft_store", [])
    by_name = {e.get("draft_name"): e for e in staged_reg}

    added, updated, kept, relisted, already = [], [], [], [], []
    listed = lambda n: any(x.get("draft_name") == n for x in reg.get("all_draft_store", []))
    for name in sorted(os.listdir(STAGE)):
        src = os.path.join(STAGE, name)
        if not os.path.isdir(src) or name.startswith((".", "_")) or not draft_json(src):
            continue
        dst = os.path.join(real, name)
        staged_fp = fingerprint(src)
        if os.path.exists(dst):
            mark = load(os.path.join(dst, MARK), None)
            if not mark:
                kept.append(f"{name} (you already have a project with this name; it was left exactly as it is)")
                continue
            if mark.get("staged") == staged_fp:
                if listed(name):
                    already.append(name)
                    continue                               # already in CapCut, nothing new
                # The project is in CapCut's folder but its list lost it, which is what a CapCut still running
                # at copy time does when it finally saves its own list. Put it back on the list; copy nothing.
                relisted.append(name)
            elif mark.get("installed") != fingerprint(dst):
                kept.append(f"{name} (you changed it in CapCut, so your version was kept)")
                continue
            else:
                bak = os.path.join(HERE, "_replaced", f"{name} {time.strftime('%Y%m%d-%H%M%S')}")
                os.makedirs(os.path.dirname(bak), exist_ok=True)
                shutil.move(dst, bak)
                updated.append(name)
        else:
            added.append(name)
        if name not in relisted:
            tmp = dst + ".adding"
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(src, tmp)
            rewrite_folder(tmp, STAGE, real)
            os.replace(tmp, dst)
            with open(os.path.join(dst, MARK), "w", encoding="utf-8") as fh:
                json.dump({"staged": staged_fp, "installed": fingerprint(dst),
                           "at": time.strftime("%Y-%m-%d %H:%M")}, fh)

        e = registry_entry(by_name.get(name), name, dst, real, lambda t: rewrite_text(t, STAGE, real))
        put_on_top(reg, e, name)

    if added or updated or relisted:
        if not started and os.path.exists(reg_path):
            shutil.copyfile(reg_path, reg_path + f".before-engine-{time.strftime('%Y%m%d-%H%M%S')}.bak")
        if started:
            reg["draft_ids"] = len(reg["all_draft_store"])
        with open(reg_path, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, ensure_ascii=False)

    for n in added:
        say(f"  + added   {n}")
    for n in updated:
        say(f"  ~ updated {n}")
    for n in relisted:
        say(f"  + listed  {n} (it was already in CapCut's folder; it is back on CapCut's list)")
    for n in kept:
        say(f"  = kept    {n}")
    if added or updated or relisted:
        say("\nDone. Open CapCut: your new project is at the top of the list.")
    elif not kept:
        say("Everything here is already in CapCut. Nothing to do.")
    return {"added": added, "updated": updated, "relisted": relisted, "already": already,
            "kept": [k.split(" (", 1)[0] for k in kept]}


def run(argv=None):
    """The script's entry point. A double-click runs main() exactly as always. An automatic run (a fresh request
    from the engine, or --auto <token>) also writes AUTO_RESULT and exits AUTO_EXIT so the .bat does not pause.
    Answers the exit code; never raises in an automatic run (an unexpected error is reported, not hidden)."""
    argv = sys.argv[1:] if argv is None else argv
    token = argv[argv.index("--auto") + 1] if "--auto" in argv[:-1] else None
    token = token or take_auto_request()
    if not token:
        main()
        return 0
    res = os.path.join(_here(), AUTO_RESULT)
    base = {"token": token, "pid": os.getpid()}
    try:
        _write_json(res, dict(base, status="running", at=time.time()))
    except OSError:
        pass
    try:
        got = main() or {}
        out = dict(base, status="done", **got,
                   installed=sorted(set(got.get("added", []) + got.get("updated", []) + got.get("relisted", [])
                                        + got.get("already", []))))
    except Refused as e:
        out = dict(base, status="refused", reason=e.reason, message=str(e.code))
        say(str(e.code))
    except SystemExit as e:
        out = dict(base, status="refused", reason="stopped", message=str(e.code))
        say(str(e.code))
    except Exception as e:
        out = dict(base, status="error", reason=type(e).__name__, message=str(e)[:500])
        say(f"Something went wrong ({type(e).__name__}: {e}). Double-click \"Add to CapCut.bat\" to try again.")
        note_fallback(f"automatic Add to CapCut failed: {type(e).__name__}: {e}")
    out["at"] = time.time()
    try:
        _write_json(res, out)
    except OSError:
        pass
    return AUTO_EXIT


if __name__ == "__main__":
    sys.exit(run())
