#!/usr/bin/env python3
"""premake.py — her full-quality cut, made quietly while she reviews, so "Lock in my cut" is instant.

The full-quality stitch (the base cut video, every check) is the slow part of a cut: minutes on a long clip. It
only has to happen once her cut is final, and most of the time the cut she reviews IS final. So while she watches
the page, this makes that same video on a SHADOW copy of her job, never in her job:

    _local/premake/<job>/<job>~pre/      raw/ -> her raw clips (a link, nothing copied or changed)
                                          transcript/cuts.json + words.json (copies of her saved ones)
                                          outputs/<job>~pre.mp4  (the full-quality cut, made here)

It runs the SAME stitch-cut.sh, full quality, every check, on the cut she last saved. A cut the engine saved comes
back unchanged when stitched again (stitch-cut.sh, measured), so the result is the video "Lock in my cut" would
make. When she locks in, adopt() uses it ONLY if all of this holds, else the normal full stitch runs as before:
  * the cut she's locking is byte-for-byte the cut the shadow was made from, and
  * the shadow's stitch saved that same cut back (nothing moved), and
  * its video exists and the stitch finished cleanly.
Nothing about quality changes: same tools, same settings, same checks. Her job's files are written only by
adopt(), the way finish_cut writes them (the video moved in with os.replace, never written over in place).

A newer edit makes a running premake out of date: it is stopped (it's the engine's own background work, never a
job she asked for) and a fresh one starts after she pauses. It never runs while her own cut job runs.

    python3 product/premake.py status <job>
"""
import json, os, shutil, signal, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QUIET_S = 20                      # start after she has paused this long (an edit in between restarts the wait)
_lock = threading.Lock()
_procs, _timers = {}, {}          # job -> running Popen / pending Timer


def _ve():
    sys.path.insert(0, HERE)
    import visual_editor
    return visual_editor


def _sha(p):
    """The CUT in a cuts.json: every segment's own fields, leaving out the stitch's bookkeeping (keys starting with
    "_", like `_snapped_from`, which records what the previous pass changed and so differs on a re-stitch even when
    every cut point is the same)."""
    import hashlib
    try:
        d = json.load(open(p, encoding="utf-8"))
        segs = d.get("segments", d) if isinstance(d, dict) else d
        core = [{k: v for k, v in sg.items() if not str(k).startswith("_")} if isinstance(sg, dict) else sg for sg in segs]
        return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    except Exception:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()


def shadow(jd):
    name = os.path.basename(os.path.abspath(jd))
    return os.path.join(ROOT, "_local", "premake", name, name + "~pre")


def _state_path(jd):
    return os.path.join(os.path.dirname(shadow(jd)), "state.json")


def state(jd):
    try:
        return json.load(open(_state_path(jd), encoding="utf-8"))
    except Exception:
        return {}


def _save_state(jd, **kv):
    p = _state_path(jd)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    d = dict(state(jd), **kv, at=time.strftime("%Y-%m-%d %H:%M:%S"))
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, p)


def schedule(job, delay=QUIET_S):
    """Her cut just changed (or the page opened on a cut with no full-quality video): (re)start the wait."""
    ve = _ve()
    jd = ve.job_dir(job)
    with _lock:
        t = _timers.pop(jd, None)
        if t:
            t.cancel()
        _stop(jd)                                     # whatever was running is about an older cut now
        t = threading.Timer(delay, lambda: start(job))
        t.daemon = True
        _timers[jd] = t
        t.start()


def _stop(jd):
    p = _procs.pop(jd, None)
    if p and p.poll() is None:
        try:
            if os.name == "nt":
                p.terminate()
            else:
                os.killpg(p.pid, signal.SIGTERM)
        except Exception:
            pass
        _save_state(jd, status="stopped")


def cancel(job):
    """Her own full-quality cut is about to run (or the cut is locked): no background one alongside it."""
    jd = _ve().job_dir(job)
    with _lock:
        t = _timers.pop(jd, None)
        if t:
            t.cancel()
        _stop(jd)


def start(job):
    """Make the full-quality cut on the shadow copy, in the background, if it's worth doing now."""
    ve = _ve()
    jd = ve.job_dir(job)
    saved = os.path.join(jd, "transcript", "cuts.json")
    if not os.path.isfile(saved) or ve.making_now(jd) or os.path.exists(os.path.join(jd, "review", "phase.json")):
        return None                                   # no cut yet, her own cut job is running, or the cut is locked
    if not ve.base_is_stale(job):
        return None                                   # her full-quality cut already matches: nothing to make
    sig = _sha(saved)
    st = state(jd)
    if st.get("cut") == sig and st.get("status") in ("running", "ready"):
        return None                                   # already made (or being made) for this exact cut
    sh = shadow(jd)
    shutil.rmtree(sh, ignore_errors=True)
    import tempfile                                   # the stitch prefers a plan left in its scratch folder: clear
    shutil.rmtree(os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(sh)), ignore_errors=True)
    os.makedirs(os.path.join(sh, "transcript"))
    raw = os.path.join(jd, "raw")
    if os.path.isdir(raw):
        try:
            os.symlink(raw, os.path.join(sh, "raw"), target_is_directory=True)
        except OSError:                               # Windows without symlink rights: link each clip instead
            os.makedirs(os.path.join(sh, "raw"))
            for f in os.listdir(raw):
                try:
                    os.link(os.path.join(raw, f), os.path.join(sh, "raw", f))
                except OSError:
                    return None                       # can't share her clips without copying gigabytes: skip it
    else:
        return None
    for f in ("cuts.json", "words.json"):
        src = os.path.join(jd, "transcript", f)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(sh, "transcript", f))
    log = os.path.join(os.path.dirname(sh), "stitch.log")
    env = dict(os.environ, FLAT_RENDER="1")
    cmd = [ve._bash(), os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh"), sh]
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    if os.name != "nt":
        cmd = ["nice", "-n", "10"] + cmd              # her editing stays smooth while it runs
    with _lock:
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT, **kw)
        _procs[jd] = p
    _save_state(jd, status="running", cut=sig, pid=p.pid)

    def wait():
        rc = p.wait()
        with _lock:
            if _procs.get(jd) is not p:
                return                                # stopped for a newer cut
            _procs.pop(jd, None)
        mp4 = os.path.join(sh, "outputs", os.path.basename(sh) + ".mp4")
        made = os.path.join(sh, "transcript", "cuts.json")
        ok = rc == 0 and os.path.isfile(mp4) and os.path.isfile(made) and _sha(made) == sig
        _save_state(jd, status="ready" if ok else "failed", cut=sig, rc=rc)
    threading.Thread(target=wait, daemon=True).start()
    return p.pid


def adopt(job):
    """At "Lock in my cut": use the premade video if it is exactly this cut's. True = adopted (instant lock)."""
    ve = _ve()
    jd = ve.job_dir(job)
    st = state(jd)
    saved = os.path.join(jd, "transcript", "cuts.json")
    if st.get("status") != "ready" or not os.path.isfile(saved) or st.get("cut") != _sha(saved):
        return False
    sh = shadow(jd)
    src = os.path.join(sh, "outputs", os.path.basename(sh) + ".mp4")
    made = os.path.join(sh, "transcript", "cuts.json")
    if not (os.path.isfile(src) and os.path.isfile(made) and _sha(made) == st["cut"]):
        return False
    out = os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".premade.tmp"
    shutil.copyfile(src, tmp)                         # copy across, then swap the name in: a draft that links the
    os.replace(tmp, out)                              # old file keeps it (never written over in place)
    ve._stamp_base(jd)
    _save_state(jd, status="adopted")
    shutil.rmtree(sh, ignore_errors=True)
    return not ve.base_is_stale(job)


def main(argv):
    if len(argv) >= 2 and argv[0] == "status":
        ve = _ve()
        print(json.dumps(state(ve.job_dir(argv[1])), indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
