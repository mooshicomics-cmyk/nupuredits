#!/usr/bin/env python3
"""vectcut_engine.py — keeps the editing engine (VectCut) answering while a CapCut draft is built, and holds the
draft builders' other backup routes, so a finished build is never thrown away over something the engine can fix.

Never a dead end (product/fallbacks.py has the rule). What lives here:

  * ensure_running(base)   The editing engine was off: the #1 buyer state, and it used to end every build with
                           "start the editor engine". It is turned on here, quietly and detached (no Terminal
                           window she has to keep open), and the build carries on. Only an engine that will not
                           come up at all stops, and then the message points at /report-a-problem.
  * post(base, ep, data)   One VectCut call with those backups built in: the engine is looked for once per run
                           and turned on when it is off; a refused connection turns it on and tries that call
                           once more; a save that runs past the 180 s wait is followed through the engine's own
                           progress record (/query_draft_status) instead of being called a failure, because a
                           big save usually finishes on the engine's side; any other slow call gets one more
                           try with a longer wait.
  * convert_job_hdr(...)   iPhone HDR footage in a CapCut build: converted to normal colour (product/hdr.py, the
    convert_draft_hdr(...) same converter as `hdr.py <job> --apply`) and the build goes on, instead of refusing.

Nothing here is remembered between runs: whether the engine is on is a fact about this moment, not this computer.
Every switch leaves one line in _local/fallbacks.log (step "capcut-draft") for the problem report.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from fallbacks import note  # noqa: E402

VECTCUT_DIR = os.path.join(HERE, "engine", "VectCutAPI")
STEP = "capcut-draft"

TIMEOUT = 180            # the wait every call has always had
RETRY_TIMEOUT = 600      # the one more try a slow call gets
LAUNCH_WAIT = 60         # how long a freshly started engine gets to answer
SETUP_WAIT = 15 * 60     # ... or, when its launcher had to (re)build its workspace first, this long
SAVE_POLL_CAP = 30 * 60  # how long a save that ran past the wait is followed before it counts as stuck
POLL = 2.0

# Per run (one build is one process). `checked`: the engine has been looked for once already. `launched`: this run
# already tried turning it on, so a second refusal is not met with a second launch. `reached`: some call has gone
# through, which means a draft may now exist only in the engine's memory.
_STATE = {"checked": False, "launched": False, "reached": False}


class NotRunning(RuntimeError):
    """The editing engine is off and could not be turned on (or stopped partway through a draft)."""


class TooSlow(RuntimeError):
    """A call that still had not finished after its retry or after following the save to the cap."""


def _say(line):
    print(f"[editing engine] {line}", file=sys.stderr, flush=True)


def _local_dir():
    return os.environ.get("REELS_ENGINE_LOCAL") or os.path.join(ROOT, "_local")


def log_path():
    """Where a launch from here writes the engine's own output (her Terminal used to be the only place it went)."""
    return os.path.join(_local_dir(), "vectcut-server.log")


def start_file():
    return os.path.join(VECTCUT_DIR, "start-editor.bat" if os.name == "nt" else "start-editor.command")


def not_running_message(base):
    starter = os.path.relpath(start_file(), ROOT).replace("\\", "/")
    return (f"The editor engine (VectCut) is not running at {base}, and it would not start on its own. Start it "
            f"with {starter} (SETUP.md §1b), then re-run. If it will not start, run /report-a-problem: the report "
            f"carries what the engine said.")


def is_up(base, timeout=3.0):
    """True when anything answers on the engine's port. /engine_home is the engine's own "who are you" page; an
    older engine answers it with a 404, and that still means it is on. Standard library only, so the check runs
    before `requests` is even imported."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"{base}/engine_home", timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True          # it answered, just not with a 200
    except Exception:
        return False


def launch():
    """Start the engine's own launcher, detached, with its output going to log_path(). Returns the process.

    Mac (and Linux): start-editor.command is run by bash directly, never through `open`, so no Terminal window
    appears and nothing waits on one. Its own last line `exec`s the server, so the process IS the engine. A new
    session keeps it alive when the build that started it ends.
    Windows: start-editor.bat through cmd, with no window. Not DETACHED_PROCESS: a batch file run that way gives
    each console tool it starts (netstat, findstr, curl, the server itself) a console window of its own. With
    stdin at NUL its closing `pause` returns at once. CREATE_BREAKAWAY_FROM_JOB lets it outlive the build where
    the job allows that; where it does not, it is started without and still runs for the rest of this build."""
    os.makedirs(_local_dir(), exist_ok=True)
    with open(log_path(), "ab") as log:   # the engine keeps its own handle; this one closes once it has started
        log.write(f"\n--- started by a CapCut build, {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n".encode())
        log.flush()
        common = dict(cwd=VECTCUT_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        if os.name == "nt":
            flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                     | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            try:
                return subprocess.Popen(["cmd", "/c", start_file()], env=env,
                                        creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000),
                                        **common)
            except OSError:
                return subprocess.Popen(["cmd", "/c", start_file()], env=env, creationflags=flags, **common)
        return subprocess.Popen(["bash", start_file()], start_new_session=True, **common)


def _log_tail():
    try:
        with open(log_path(), encoding="utf-8", errors="replace") as fh:
            lines = [ln.strip() for ln in fh.read().splitlines()[-40:]]
    except OSError:
        return []
    out = []
    for ln in reversed(lines):
        if ln.startswith("--- started by"):
            break
        out.insert(0, ln)
    return [ln for ln in out if ln]


def _setting_up():
    return any("Setting up your editing engine" in ln for ln in _log_tail())


def ensure_running(base, say=_say, wait=None):
    """Make sure the editing engine answers at `base`. True when it does (already, or after turning it on).

    Turned on at most once per run: a second refusal in the same build means it will not stay up, and launching
    it again would only hide that."""
    if is_up(base):
        return True
    if _STATE["launched"]:
        return False
    _STATE["launched"] = True
    say("the editing engine was off, so I'm turning it on. Your build carries on as soon as it answers.")
    try:
        proc = launch()
    except Exception as e:  # noqa: BLE001 - a launcher that cannot even start is the stop case, said plainly
        note(STEP, f"the editing engine was off and its launcher would not run ({type(e).__name__}: {e}); "
                   f"the build stopped")
        return False
    deadline = time.time() + (wait if wait is not None else LAUNCH_WAIT)
    extended = False
    while time.time() < deadline:
        if is_up(base, timeout=2.0):
            note(STEP, "the editing engine was off; turned it on from its launcher and the build carried on")
            say("it's on. Carrying on.")
            return True
        if proc.poll() is not None:
            break                           # the launcher ended without a server: its log says why
        if not extended and _setting_up():
            # Its workspace was missing or broken and the launcher is rebuilding it (one time, a few minutes).
            extended = True
            deadline = max(deadline, time.time() + SETUP_WAIT)
            say("its workspace needed setting up first. That takes a few minutes, one time only.")
        time.sleep(POLL)
    tail = _log_tail()
    note(STEP, "the editing engine was off and did not come up after its launcher ran; the build stopped"
               + (f" (it said: {tail[-1]})" if tail else ""))
    return False


def _json(r):
    try:
        return r.json()
    except ValueError:   # 404 / crash page / HTML — not a JSON reply: a failed call, not a raw traceback
        return {"success": False, "error": f"non-JSON reply (HTTP {r.status_code}): {r.text[:120]!r}"}


class _StdlibHTTP:
    """The few pieces of `requests` the calls here use, on Python's own urllib. A build run with plain python3 on a
    machine without the `requests` package used to die on the import (buyer reports 2026-10-19, Mac and Windows:
    "No module named 'requests'"); the engine only ever POSTs JSON to VectCut on localhost, which urllib does fine."""

    class exceptions:
        class RequestException(Exception):
            pass

        class ConnectionError(RequestException):
            pass

        class Timeout(RequestException):
            pass

    class _Reply:
        def __init__(self, status, body):
            self.status_code, self.text = status, body.decode("utf-8", "replace")

        def json(self):
            import json
            return json.loads(self.text)

    @classmethod
    def post(cls, url, json=None, timeout=None):
        import json as _j, socket, urllib.error, urllib.request
        req = urllib.request.Request(url, data=_j.dumps(json or {}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return cls._Reply(resp.status, resp.read())
        except urllib.error.HTTPError as e:            # a 4xx/5xx still carries VectCut's reply, like requests
            return cls._Reply(e.code, e.read() or b"")
        except (socket.timeout, TimeoutError) as e:
            raise cls.exceptions.Timeout(str(e)) from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise cls.exceptions.Timeout(str(e)) from None
            raise cls.exceptions.ConnectionError(str(e)) from None
        except (ConnectionError, OSError) as e:
            raise cls.exceptions.ConnectionError(str(e)) from None


def _http():
    """`requests` when it is installed (uv run and the VectCut venv carry it), else the urllib stand-in above."""
    try:
        import requests
        return requests
    except ImportError:
        return _StdlibHTTP


def _follow_save(requests, base, payload, say):
    """A save that ran past the wait. VectCut saves synchronously and records its progress under the draft's id
    (save_draft_impl: task_id = draft_id), so ask it how far along it is until it says completed or failed."""
    did = payload.get("draft_id")
    if not did:
        return None
    say("the save is taking a while (a big clip being copied in). Following it through.")
    deadline = time.time() + SAVE_POLL_CAP
    while time.time() < deadline:
        try:
            r = requests.post(f"{base}/query_draft_status", json={"task_id": did}, timeout=30)
            j = _json(r)
        except requests.exceptions.RequestException:
            j = None                        # busy saving: the next look will get through
        out = (j or {}).get("output")
        st = out if isinstance(out, dict) else {}
        status = st.get("status")
        if status == "completed":
            note(STEP, f"save_draft ran past {TIMEOUT}s; followed it on the engine's side until it finished")
            say("the save finished.")
            return {"success": True, "output": {"success": True, "draft_url": st.get("draft_url", "")}}
        if status == "failed":
            return {"success": False, "error": st.get("message") or "the engine's save failed"}
        if j is not None and not j.get("success") and "not found" in str(j.get("error", "")).lower():
            return None                     # the engine no longer knows this draft (restarted): nothing to follow
        time.sleep(POLL)
    return None


MEDIA_KEYS = ("video_url", "audio_url", "image_url")
# The words VectCut's save uses when a clip could not be copied into the draft (save_draft_impl.py says the same).
MEDIA_COPY_FAILED = "media could not be copied into the draft"


def local_media_path(p):
    """The path the editing engine (a separate process, in its own folder) will find this clip at.

    VectCut copies every clip into the draft at save time, from ITS working folder (product/engine/VectCutAPI),
    not the build's. So a relative path ("projects/<job>/raw/clip.mp4") or a Git Bash path ("/c/Users/...", which
    Windows Python reads as C:\\c\\Users\\...) named a file the engine could not see, and the clip was left out
    of the draft while the save still said success. Made absolute here, in the build's own process, where the
    path means what the driver meant. URLs and draft placeholders pass through untouched."""
    if not isinstance(p, str) or not p.strip():
        return p
    s = p.strip()
    if "://" in s or s.startswith("##"):
        return p
    import ntpath, posixpath
    pathmod = ntpath if os.name == "nt" else posixpath    # os.path on each, named so a test can stand in for one
    if os.name == "nt":
        import re
        m = re.match(r"^/(?:cygdrive/|mnt/)?([a-zA-Z])(/.*)?$", s)
        if m:
            s = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    if not pathmod.isabs(s):
        s = pathmod.abspath(s)
    return s


def _media_payload(ep, payload):
    """(payload with every local clip path made absolute, None) or (payload, the reason one is not there)."""
    out = dict(payload)
    for k in MEDIA_KEYS:
        if k in out and out[k]:
            out[k] = local_media_path(out[k])
            v = out[k]
            if isinstance(v, str) and "://" not in v and not v.startswith("##") and not os.path.isfile(v):
                given = payload[k] if payload[k] == v else f"{payload[k]} (read as {v})"
                return out, f"{ep}: no file at {given}. The clip has to be on this computer before it can go in."
    return out, None


def refuse_failed_media(save_result, draft_dir):
    """A save that could not copy a clip into the draft is a failed build, never a quiet success with a hole in
    it. Removes the unfinished draft-id folder VectCut just wrote (nothing of hers: it is renamed and registered
    only after this) and raises with VectCut's reason for each clip. Anything else: nothing to do."""
    err = str((save_result or {}).get("error") or "")
    if (save_result or {}).get("success") or MEDIA_COPY_FAILED not in err:
        return
    import shutil
    if draft_dir and os.path.isdir(draft_dir):
        shutil.rmtree(draft_dir, ignore_errors=True)
    note(STEP, f"save_draft could not copy media into the draft: {err[:300]}")
    raise RuntimeError(f"The editing engine could not copy a clip into the CapCut project, so nothing was "
                       f"handed over. {err[:600]}\n  Nothing of yours was changed. If the clip is there and this "
                       "repeats, type /report-a-problem in Claude.")


def post(base, ep, payload, timeout=TIMEOUT, say=_say):
    """One VectCut call -> its parsed JSON reply ({success, output, error}). Raises NotRunning / TooSlow (both
    RuntimeError) only when every backup above has been tried. A local clip path is made absolute first, and one
    that is not on this computer is a failed call right here (local_media_path)."""
    payload, missing = _media_payload(ep, payload or {})
    if missing:
        return {"success": False, "error": missing}
    requests = _http()
    if not _STATE["checked"]:
        _STATE["checked"] = True
        if not ensure_running(base, say=say):
            raise NotRunning(not_running_message(base))
    try:
        r = requests.post(f"{base}/{ep}", json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        if _STATE["reached"] and payload.get("draft_id"):
            # It answered earlier in this build and then went away. The draft it was holding lived only in its
            # memory, and a restarted engine would quietly start a NEW empty one under the same id, so a retry
            # here would build a partial draft that still reports success. Turn it back on for the next run,
            # then stop this one.
            ensure_running(base, say=say)
            note(STEP, f"the editing engine stopped partway through a draft (on {ep}); the build stopped")
            raise NotRunning("The editor engine (VectCut) stopped partway through this draft, and the draft it was "
                             "holding went with it. Run the build again"
                             + (" (it is back on now)." if is_up(base) else
                                f"; if the engine will not start, run /report-a-problem.")) from None
        if not ensure_running(base, say=say):
            raise NotRunning(not_running_message(base)) from None
        try:
            r = requests.post(f"{base}/{ep}", json=payload, timeout=timeout)
        except requests.exceptions.ConnectionError:
            raise NotRunning(not_running_message(base)) from None
        except requests.exceptions.Timeout:
            return _after_timeout(requests, base, ep, payload, say)
    except requests.exceptions.Timeout:
        return _after_timeout(requests, base, ep, payload, say)
    _STATE["reached"] = True
    return _json(r)


def _after_timeout(requests, base, ep, payload, say):
    if ep == "save_draft":
        j = _follow_save(requests, base, payload, say)
        if j is not None:
            _STATE["reached"] = True
            return j
        raise TooSlow(f"VectCut was still saving after {SAVE_POLL_CAP // 60} minutes. Let the editor engine finish "
                      "and re-run; if it repeats, run /report-a-problem.")
    # Anything else: one more try with a longer wait. The first try may still finish on the engine's side while
    # this one runs, so a retry that is turned away because its clip now OVERLAPS one already on that track means
    # the first try landed: that is the call done, not a failure.
    say(f"{ep} ran past {TIMEOUT}s (usually a very large clip being transcoded). Giving it one more go, longer.")
    try:
        r = requests.post(f"{base}/{ep}", json=payload, timeout=RETRY_TIMEOUT)
    except requests.exceptions.RequestException:
        note(STEP, f"{ep} ran past {TIMEOUT}s twice; the build stopped")
        raise TooSlow(f"VectCut took longer than {RETRY_TIMEOUT}s on {ep}, even on a second try. Usually a very "
                      "large clip being transcoded: trim that clip first and re-run; if it repeats, run "
                      "/report-a-problem.") from None
    _STATE["reached"] = True
    j = _json(r)
    if not j.get("success") and "overlap" in str(j.get("error", "")).lower():
        j = {"success": True, "output": {}}
        note(STEP, f"{ep} ran past {TIMEOUT}s; the first try had landed after all, so the retry stood down")
    elif j.get("success"):
        note(STEP, f"{ep} ran past {TIMEOUT}s; a second try with a longer wait went through")
    return j


# ---- HDR footage in a CapCut build ----------------------------------------------------------------------------
# A CapCut draft that plays an iPhone HDR clip shows it grey and washed out, so the builders used to refuse the
# whole finished build at finalize and send her off to run hdr.py by hand. The conversion is the engine's own
# (product/hdr.py, the same one `hdr.py <job> --apply` runs), so the build runs it and goes on. If the conversion
# itself fails, the refusal stands: a washed-out draft is never shipped.

def convert_job_hdr(rawdir, say=print):
    """Before a build lays the cut: every HDR clip in the job's raw/ becomes a normal-colour copy under the same
    name (HDR copy kept in hdr-originals/), exactly `hdr.py <job> --apply`. -> names converted. Never raises: a
    failure here leaves finalize's check to catch it."""
    if os.path.basename(os.path.normpath(rawdir)) != "raw":
        return []
    try:
        import hdr
        clips = hdr.hdr_clips(rawdir)
        if not clips:
            return []
        m = hdr.minutes_needed(clips)
        say(f"[hdr] {len(clips)} clip(s) were filmed in iPhone HDR, which CapCut shows grey and washed out. "
            f"Converting to normal colour first (about {m} minute{'s' if m != 1 else ''}); your originals are kept "
            f"in {hdr.KEPT}/.")
        done = hdr.convert_job(os.path.dirname(os.path.abspath(rawdir)), say=say)
    except Exception as e:  # noqa: BLE001
        say(f"[hdr] could not convert to normal colour first ({str(e)[:160]}); the build checks again at the end")
        return []
    if done:
        note(STEP, f"{len(done)} HDR clip(s) reached a CapCut build; converted them to normal colour "
                   f"(hdr.py --apply) and built on those")
    return done


def convert_draft_hdr(d, paths, draft_dir, say=print):
    """At finalize: the draft still plays HDR files (a clip from outside raw/, or one the first pass could not
    convert). Each gets a normal-colour copy and the draft plays that instead. A file inside this new draft (VectCut's
    own copy) is replaced in place, written beside it first and swapped in with os.replace, so a file hardlinked
    from somewhere else keeps its own copy. A file anywhere else is HERS and is never changed: the copy goes into
    this draft's assets and the draft is pointed at it. The material's size follows the new file. -> paths that
    are still HDR (empty when every one converted)."""
    import hdr
    left = []
    inside = os.path.normcase(os.path.abspath(draft_dir)) + os.sep
    for p in paths:
        stem, ext = os.path.splitext(os.path.basename(p))
        ours = os.path.normcase(os.path.abspath(p)).startswith(inside)
        if ours:
            dst = None
            tmp = os.path.join(os.path.dirname(p), f".{stem}.sdr{ext or '.mp4'}")
        else:
            os.makedirs(os.path.join(draft_dir, "assets", "video"), exist_ok=True)
            dst = os.path.join(draft_dir, "assets", "video", f"{stem}-sdr{ext or '.mp4'}")
            tmp = os.path.join(draft_dir, "assets", "video", f".{stem}-sdr{ext or '.mp4'}")
        try:
            secs = hdr._clip_facts(p)[0]
            say(f"[hdr] {os.path.basename(p)} is iPhone HDR; converting it to normal colour for CapCut")
            hdr.to_sdr(p, tmp)
            secs2, w, h = hdr._clip_facts(tmp)
            if abs(secs2 - secs) > 0.05 or hdr.hdr_kind(tmp):
                raise RuntimeError(f"the copy came out {secs2:.2f}s against {secs:.2f}s")
            os.replace(tmp, p if ours else dst)
        except Exception as e:  # noqa: BLE001
            try:
                os.remove(tmp)
            except OSError:
                pass
            say(f"[hdr] could not convert {os.path.basename(p)} ({str(e)[:160]})")
            left.append(p)
            continue
        for v in (d.get("materials") or {}).get("videos") or []:
            if v.get("path") == p:
                if not ours:
                    v["path"] = dst
                if w and h:
                    v["width"], v["height"] = w, h
        note(STEP, f"{os.path.basename(p)} in the draft was HDR; converted it to normal colour and built on")
    return left


def skip_note(kind, path, why="no file there"):
    """An optional sound cue or sticker that is not there: skip that one item, say so in one line, finish the
    reel. (capcut_sfx.add_sfx already did this for the bundled sounds.)"""
    print(f"  · {kind} skipped ({why}): {os.path.basename(str(path))}. The rest of the reel is built as planned.")
    note(STEP, f"{kind} {os.path.basename(str(path))!r} was missing ({why}); skipped it and built the rest")
