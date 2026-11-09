#!/usr/bin/env python3
"""render_lock.py — one HyperFrames render at a time on this computer.

    import render_lock
    with render_lock.held("captions"):        # or: render_lock.acquire("captions") ... render_lock.release()
        run the render

WHY. Two renders at once (two Claude windows, or a render started while another is still counting frames)
each get half the memory and the browser, and on a 16 GB Mac that is how both die partway or the machine
stalls. So every HyperFrames render the engine runs (reel_render.py, hf_render.py, the beat-sheet sandbox,
the render checks, and product/hf_npx.cjs for the vendored Node scripts) holds this one lock. Snapshots and
checks do not: they are short and they never count frames.

A second render WAITS, never stops the first ("never stop a render still counting frames"): it says so in
one line, then once a minute. Ctrl-C while waiting is a stop (exit 130) that leaves the other render's lock
exactly as it was. A cache hit never reaches a render, so it never waits.

THE PROTOCOL, kept identical in hf_npx.cjs so Python and Node respect each other:
  where   ~/.cache/reels-editing-engine/render.lock (the engine's per-user cache, shared by every copy of the
          engine and every window; not this copy's _local/ and not the temp folder, which can differ by
          session). REEL_RENDER_LOCK_DIR moves it, for tests.
  taking  the file is made with O_CREAT|O_EXCL (works the same on a Mac and on Windows; no fcntl or msvcrt)
          and holds JSON: {"pid": <owner>, "started": <epoch seconds>, "what": <what is rendering>, "host": ...}
  stale   its owner's pid is not running, or that pid now belongs to a program that started more than 120 s
          after the lock was written (the owner died and the number was handed out again), or the record
          is still unreadable 30 s after it was written. A stale lock is moved aside (only one waiter's
          rename can succeed), checked, and taken over with a note.
          There is deliberately NO time ceiling: the holder does not heartbeat (a Node holder is blocked in
          spawnSync for the whole render and could not), and a real render can run all night, so a lock is
          never taken from a live process whose start time still matches. The start time is read from the
          kernel on Windows (here) and from PowerShell in hf_npx.cjs, from ps everywhere else; when it cannot
          be read, that one look cannot tell, and the pid check still runs on every look.
  same    a process asking again holds it deeper, so the retries inside one render never wait on themselves.
  can't   a lock folder that cannot be made means the render goes ahead without one, said in one line: a
          lock is a courtesy between renders, never a reason not to render.
REEL_RENDER_LOCK_POLL / REEL_RENDER_LOCK_SAY_EVERY tune the waiting (seconds), for tests.
"""
import atexit
import contextlib
import json
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_STATE = {"path": None, "depth": 0}
POLL = 2.0              # seconds between looks at the lock while waiting
SAY_EVERY = 60.0        # one "still waiting" line a minute
UNREADABLE_GRACE = 30   # an unreadable record younger than this is still being written
REUSED_SLACK = 120      # a pid this much younger than its lock is someone else's


def _fallbacks():
    """product/fallbacks.py, or a stand-in that records nothing: a missing record never stops a render."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import fallbacks
        return fallbacks
    except Exception:   # noqa: BLE001
        class _NoRecord:
            note = staticmethod(lambda *a, **k: None)
        return _NoRecord


def _setting(name, default):
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def lock_path():
    base = os.environ.get("REEL_RENDER_LOCK_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "reels-editing-engine")
    return os.path.join(base, "render.lock")


def pid_running(pid):
    """True / False when it can tell whether process `pid` is running here; None when it cannot."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) on Windows does not test a process: it TERMINATES it. Ask the kernel instead.
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False if ctypes.get_last_error() == 87 else None   # 87 = no such process
            try:
                code = ctypes.c_ulong()
                if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return None
                return code.value == 259                       # STILL_ACTIVE
            finally:
                k32.CloseHandle(h)
        except Exception:   # noqa: BLE001
            return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                                            # running, as someone else
    except OSError:
        return None


def pid_age_seconds(pid):
    """How long process `pid` has been running, or None when this computer will not say. Used only to tell a
    lock's owner from a newer, unrelated process that was handed the same pid after the owner died."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            h = k32.OpenProcess(0x1000, False, pid)
            if not h:
                return None
            try:
                t = [wintypes.FILETIME() for _ in range(4)]
                if not k32.GetProcessTimes(h, *[ctypes.byref(x) for x in t]):
                    return None
                created = (t[0].dwHighDateTime << 32 | t[0].dwLowDateTime) / 1e7 - 11644473600
                return max(0.0, time.time() - created)
            finally:
                k32.CloseHandle(h)
        etime = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True,
                               timeout=5).stdout.strip()            # [[dd-]hh:]mm:ss
        if not etime:
            return None
        days, _, clock = etime.rpartition("-")
        secs = 0
        for part in clock.split(":"):
            secs = secs * 60 + int(part)
        return secs + int(days or 0) * 86400
    except Exception:   # noqa: BLE001
        return None


def read_record(path):
    """The lock's record: a dict, {} while unreadable (being written, or left half-written), None when gone."""
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        return rec if isinstance(rec, dict) else {}
    except FileNotFoundError:
        return None
    except Exception:   # noqa: BLE001
        return {}


def stale_reason(rec, path):
    """Why the lock's owner is gone (a short reason), or "" while it is still rendering."""
    pid = rec.get("pid")
    if not rec:
        try:
            return "" if time.time() - os.path.getmtime(path) < UNREADABLE_GRACE else "its record was never finished"
        except OSError:
            return ""
    running = pid_running(pid)
    if running is False:
        return f"the render that held it (process {pid}) is no longer running"
    if running and isinstance(rec.get("started"), (int, float)):
        age = pid_age_seconds(pid)
        if age is not None and age + REUSED_SLACK < time.time() - rec["started"]:
            return f"the render that held it (process {pid}) is gone; that number now belongs to another program"
    return ""


def acquire(what=""):
    """Hold the computer's render lock, waiting for another render to finish first. True when held, False when
    no lock could be made at all (the render then goes ahead without one, said in one line)."""
    if _STATE["depth"]:
        _STATE["depth"] += 1
        return True
    path = lock_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as e:
        print(f"  (could not make the render lock folder, {e.strerror or e}; rendering without waiting for "
              f"any other render)", flush=True)
        return False
    poll = _setting("REEL_RENDER_LOCK_POLL", POLL)
    say_every = _setting("REEL_RENDER_LOCK_SAY_EVERY", SAY_EVERY)
    waited_from, said = None, 0.0
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            rec = read_record(path)
            if rec is None:
                continue                                   # released between the two looks: try again now
            if rec.get("pid") == os.getpid():              # a lock this process left (an earlier call that
                _STATE.update(path=path, depth=1)          # stopped partway): it is ours to use
                return True
            stale = stale_reason(rec, path)
            if stale:
                # Moved aside, not deleted, so two waiters cannot both clear it: only one rename succeeds,
                # and a record that changed under us (a fresh owner) is put back.
                aside = f"{path}.stale.{os.getpid()}"
                try:
                    os.replace(path, aside)
                except OSError:
                    continue
                if read_record(aside) != rec and not os.path.exists(path):
                    try:
                        os.replace(aside, path)
                    except OSError:
                        pass
                    continue
                try:
                    os.remove(aside)
                except OSError:
                    pass
                print(f"  A render lock was left behind ({stale}), so this render takes it over.", flush=True)
                _fallbacks().note("render-lock", f"took over a render lock left behind: {stale}")
                continue
            now = time.monotonic()
            if waited_from is None:
                waited_from, said = now, now
                owner = f" ({rec['what']})" if rec.get("what") else ""
                print(f"  Another render is running on this computer{owner}; this one starts when it finishes.",
                      flush=True)
            elif now - said >= say_every:
                said = now
                print(f"  Still waiting for the other render to finish ({int((now - waited_from) // 60)} min so far).",
                      flush=True)
            try:
                time.sleep(poll)
            except KeyboardInterrupt:
                print("\n  Stopped while waiting for the other render. Nothing was rendered; that render carries on.",
                      flush=True)
                raise SystemExit(130)
            continue
        except OSError as e:
            print(f"  (could not make the render lock, {e.strerror or e}; rendering without waiting for any "
                  f"other render)", flush=True)
            return False
        try:
            os.write(fd, json.dumps({"pid": os.getpid(), "started": time.time(), "what": what,
                                     "host": platform.node()}).encode("utf-8"))
        finally:
            os.close(fd)
        _STATE.update(path=path, depth=1)
        if waited_from is not None:
            print(f"  The other render finished; rendering now "
                  f"(waited {int(time.monotonic() - waited_from)} s).", flush=True)
        return True


def release(all_levels=False):
    """Let the next render go. Only a lock this process holds is removed, never someone else's."""
    if not _STATE["depth"]:
        return
    _STATE["depth"] = 0 if all_levels else _STATE["depth"] - 1
    if _STATE["depth"]:
        return
    path, _STATE["path"] = _STATE["path"], None
    rec = read_record(path) if path else None
    if rec and rec.get("pid") == os.getpid():
        try:
            os.remove(path)
        except OSError:
            pass


@contextlib.contextmanager
def held(what=""):
    """`with held("..."):` around a render. Released on the way out, however the render ends."""
    took = acquire(what)
    try:
        yield took
    finally:
        if took:
            release()


atexit.register(release, True)   # a render that stops on an error still lets the next one go


if __name__ == "__main__":   # python3 product/render_lock.py  -> where the lock is and who holds it
    p = lock_path()
    r = read_record(p)
    print(p, "-> free" if r is None else f"-> held: {json.dumps(r)}"
          + (f" (stale: {stale_reason(r, p)})" if r is not None and stale_reason(r, p) else ""))
