"""npx_run.py — build a subprocess argv that actually runs `npx` cross-platform.

On Windows, `npx` (like `npm`/`yarn`) is a batch script (`npx.cmd`), not a real .exe. Windows'
CreateProcess (what Python's subprocess uses without shell=True) can only launch real executables
directly — it cannot execute a .cmd/.bat file even when given its exact path with extension, so
`subprocess.run(["npx", ...])` fails with `FileNotFoundError: [WinError 2]` on every Windows machine,
while working fine on macOS/Linux (where `npx` is a real executable or a shebang script the OS can
exec directly). Routing through `cmd /c` lets Windows' own shell resolve and run the batch file
correctly; on Mac/Linux this wrapping is unnecessary, so leave the argv untouched there.
"""
import os
import platform
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _fb():
    """product/fallbacks.py (note / remember / remembered): the shared record of every backup route taken
    and of what this computer has learned works. A copy of the engine without it gets stand-ins that do
    nothing, so a missing record can never stop a check or a render."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import fallbacks
        return fallbacks
    except Exception:   # noqa: BLE001
        class _NoRecord:
            note = staticmethod(lambda *a, **k: None)
            remember = staticmethod(lambda *a, **k: None)
            remembered = staticmethod(lambda *a, **k: None)
        return _NoRecord


def _say(line):
    """One calm line about a switch the engine made on its own. stderr, so it never mixes into output a
    caller parses."""
    print(line, file=sys.stderr, flush=True)


def hf_version():
    """The ONE HyperFrames pin, from product.json ("hyperframes"). Every render/check/bootstrap call reads
    it here, and check-ship refuses a bundle whose docs or scripts mention any other version, so a bump
    is one edit plus a doc sweep the gate verifies, never a hunt for stale copies.

    Fallbacks, in order: the shipped copy of product.json at product/templates/product.engine.json (an
    updater from v1.0.64 or earlier writes back a stale product.json and drops new settings; the template
    rides in every patch on an unprotected path), then the literal below, which check-ship §25 holds equal
    to the pin."""
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("product.json", os.path.join("product", "templates", "product.engine.json")):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                v = str(json.load(f).get("hyperframes", "")).strip()
            if v:
                return v
        except Exception:
            pass
    return "0.9.6"


def hf_check_timeout_ms():
    """Settle budget for `hyperframes check`. Its 3000 ms default was measured on Apple Silicon; an Intel
    Mac or a budget PC can miss it and fail a composition that is fine, and the render gate REFUSES to
    render on a failed check. One number, used by every caller, overridable for a tester whose machine
    needs more (REELS_ENGINE_HF_CHECK_TIMEOUT_MS)."""
    v = os.environ.get("REELS_ENGINE_HF_CHECK_TIMEOUT_MS", "").strip()
    if v.isdigit():
        return int(v)
    return 3000 if _fast_machine() else 10000


def _fast_machine():
    """Apple Silicon: the hardware every check budget here was measured on."""
    return sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64")


def _ram_gb():
    """Installed memory in GB, or None when it cannot be read."""
    try:
        if os.name == "nt":
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS(); ms.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return ms.ullTotalPhys / 1e9
            return None
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except Exception:
        return None


def hf_check_nav_timeout_ms():
    """Page-load budget for `hyperframes check`, or None to leave HyperFrames' own default alone.

    HyperFrames' check (0.8.43 through 0.8.158) gives the page max(10 s, --timeout) to load. On a slow machine --timeout is 10 s, so the
    budget was exactly its floor with no headroom, and a loaded 8 GB Intel Mac refused a clean composition
    because the check's own browser page could not finish loading in time. That says nothing about the
    composition, so the budget grows with how slow the machine is: Apple Silicon keeps the default, any
    other machine gets 45 s, and one with 8 GB or less gets 60 s. It is a ceiling, not a wait: a page that
    loads in 2 s still takes 2 s. REELS_ENGINE_HF_NAV_TIMEOUT_MS overrides it for a tester who needs more."""
    v = os.environ.get("REELS_ENGINE_HF_NAV_TIMEOUT_MS", "").strip()
    if v.isdigit():
        return int(v)
    # A check on this computer that only loaded its page with the longer budget (run_hf_check) starts there.
    v = str(_fb().remembered("render.nav-timeout-ms") or "").strip()
    if v.isdigit():
        return int(v)
    if _fast_machine():
        return None
    ram = _ram_gb()
    return 60000 if (ram is not None and ram <= 8.5) else 45000


def hf_check_env(base=None):
    """The environment to run `hyperframes check` in: `base` (default os.environ) plus the page-load budget
    above when this machine needs one. Never used for `render`: its own page-load default is 60 s, and this
    variable would set that budget too, so passing it to a render could only shorten it. A budget the person
    already set in their environment always wins.

    It also sets CI=1, the one switch HyperFrames gives for its "warm check" (0.8.186 on): after any check run
    without a terminal, which is every check the engine runs, it leaves a detached Node process holding a launched
    Chrome for five minutes, waiting to serve the next check. That is a second browser alive through the render
    that follows (memory an 8 GB Mac needs), a process the engine's hang handling cannot see or stop, and on Windows
    a folder held open. In this CLI, CI otherwise only turns off telemetry, the feedback prompt, the update and
    skills notices and interactive prompts, all already off or unused here. A CI value already set is kept."""
    env = dict(os.environ if base is None else base)
    nav = hf_check_nav_timeout_ms()
    if nav and not str(env.get("PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS", "")).strip():
        env["PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS"] = str(nav)
    if not str(env.get("CI", "")).strip():
        env["CI"] = "1"
    return env


def hf_check_max_transition_samples():
    """Cap on the moments `check --at-transitions` adds at tween boundaries, or 0 for no cap.

    Uncapped, the check samples every tween start and end plus the midpoint between each pair. A caption
    layer with a caption on every word has hundreds of one-word clips and 700+ boundaries, and HyperFrames'
    check gives the whole browser check a fixed 120 s (CHECK_DEADLINE_MS, not a flag), counted from the
    moment its browser is up, so page load and settle come out of the same budget. Six buyers' checks on
    dense caption layers ran out of it ("check_runtime_failure: Check did not finish within its deadline"),
    on Apple Silicon, Intel Macs and Windows alike. Capped, HyperFrames keeps an even stride across the
    whole timeline and says how many it left out; one buyer's same check went from out-of-time to passed in
    about 30 s at 100. A slower machine gets a smaller cap so the same check fits the same 120 s.
    REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES overrides it; 0 turns the cap off."""
    v = os.environ.get("REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES", "").strip()
    if v.isdigit():
        return int(v)
    if _fast_machine():
        return 100
    ram = _ram_gb()
    return 40 if (ram is not None and ram <= 8.5) else 60


def check_ran_out_of_time(text):
    """True when HyperFrames ended the check at its own deadline (check_runtime_failure, "did not finish
    within its deadline"). That is a verdict ("Check failed"), so run_hf_check returns status "ran" and the
    render goes ahead with a warning, but it is about the time the check had on this computer, never a
    finding about the composition, so callers say it as that."""
    return bool(re.search(r"did not finish within (?:its|the check) deadline", text or ""))


def hf_check_argv(version, comp_dir, strict=False, timeout_ms=None, contrast=True, max_transition_samples=None):
    """The ONE argv for `hyperframes check`. Flag ORDER is load-bearing: on 0.7.68 (the earlier pin)
    `--frame-check` takes an optional value and its parser swallows whatever token follows it, so
    `--frame-check --timeout=3000` fails with "Invalid --frame-check" (a real regression: 1.0.65 shipped that
    order and every gated render would have refused; newer CLIs happen to accept it, which is how it hid).
    Keep `--timeout=` right after the directory and `--frame-check` LAST, on every version.
    contrast=False adds --no-contrast, for a composition whose visual content is NOT authored here
    (a background plate that reproduces the creator's own website verbatim). Her site's styling is
    hers to set; WCAG on it is not this gate's call, and restyling it to pass would defeat the point
    of using the real page. Every composition whose text IS authored here keeps the pass ON.
    max_transition_samples caps the --at-transitions moments (hf_check_max_transition_samples; 0 = no cap).
    It goes between --at-transitions and --frame-check, as one `--flag=value` token so nothing can swallow it.

    product/tests/test_hf_check_argv.py runs this argv through the real CLI."""
    if timeout_ms is None:
        timeout_ms = hf_check_timeout_ms()
    if max_transition_samples is None:
        max_transition_samples = hf_check_max_transition_samples()
    args = ["check", comp_dir, f"--timeout={int(timeout_ms)}"]
    if strict:
        args.append("--strict")
    if not contrast:
        args.append("--no-contrast")
    args.append("--at-transitions")
    if int(max_transition_samples) > 0:
        args.append(f"--max-transition-samples={int(max_transition_samples)}")
    args.append("--frame-check")   # --frame-check LAST, always (see above)
    return npx_argv(f"hyperframes@{version}", *args)


def npx_argv(*args):
    """Return the argv list that actually invokes `npx <args>` on this OS."""
    if os.name == "nt":
        return ["cmd", "/c", "npx", *args]
    return ["npx", *args]


# Said by every caller that finds Node missing, so the wording is the same wherever it surfaces.
NO_NODE = ("Node is not installed on this computer, or this terminal was opened before it was installed "
           "(a new install stays invisible until the terminal is closed and opened again). HyperFrames runs "
           "on Node's `npx` command. Close the terminal and open a new one, then run this again; if it is "
           "still missing, run ./check-setup.sh, which prints the install command for this machine.")


def npx_path():
    """Where `npx` is on this machine, or None when Node is missing.

    Ask BEFORE running anything through npx_argv. On Windows that argv starts with `cmd`, which always
    exists, so a missing npx never raises: cmd prints "'npx' is not recognized" and exits 1, and a caller
    reading that exit code blames the composition. On a Mac a missing npx raises FileNotFoundError instead.
    `cmd /c npx` runs npx.cmd, so that is the name looked for on Windows.

    Not on PATH is not the same as not installed. The usual case is Node installed and this terminal
    opened before it was (or the Claude app's own shell starting with a short PATH). So when PATH has no
    npx, the folders Node's installers use are searched too (the list scripts/_path-shim.sh keeps), and
    the one found is put on PATH for everything this run starts and remembered ("node.dir"), so a later
    run looks there first."""
    import shutil
    name = "npx.cmd" if os.name == "nt" else "npx"
    hit = shutil.which(name)
    if hit:
        return hit
    return _npx_off_path(name)


def _newest(pattern):
    """Folders matching `pattern`, newest Node version first (nvm keeps one folder per version, and the
    newest is the one she most likely meant)."""
    import glob

    def ver(p):
        m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return sorted(glob.glob(pattern), key=ver, reverse=True)


def _node_dirs():
    """Where the standard Node installers put node and npx, most likely first: the same places
    scripts/_path-shim.sh searches, plus the version managers (nvm, Volta, fnm, asdf).
    REELS_ENGINE_NODE_DIRS replaces the whole search (os.pathsep-separated; empty searches nowhere), so a
    test can stand in for a computer without Node."""
    override = os.environ.get("REELS_ENGINE_NODE_DIRS")
    if override is not None:
        return [p for p in override.split(os.pathsep) if p]
    home = os.path.expanduser("~")
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        roaming = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        dirs = [os.path.join(pf, "nodejs"), r"C:\Program Files\nodejs",
                os.path.join(local, "Programs", "nodejs"),
                *_newest(os.path.join(local, "Programs", "node", "node-v*")),
                os.environ.get("NVM_SYMLINK", ""), *_newest(os.path.join(roaming, "nvm", "v*")),
                os.path.join(local, "Volta", "bin"), os.path.join(pf, "Volta"),
                os.path.join(roaming, "fnm", "aliases", "default"),
                os.path.join(home, "scoop", "apps", "nodejs", "current"), os.path.join(home, "scoop", "shims"),
                r"C:\ProgramData\chocolatey\bin", os.path.join(roaming, "npm")]
    else:
        dirs = ["/opt/homebrew/bin", "/usr/local/bin",
                *_newest(os.path.join(home, ".nvm", "versions", "node", "v*", "bin")),
                os.path.join(home, ".volta", "bin"),
                os.path.join(home, ".local", "share", "fnm", "aliases", "default", "bin"),
                os.path.join(home, "Library", "Application Support", "fnm", "aliases", "default", "bin"),
                os.path.join(home, ".fnm", "aliases", "default", "bin"),
                os.path.join(home, ".asdf", "shims"), os.path.join(home, ".local", "bin"),
                "/opt/local/bin", "/usr/bin"]
    return [d for d in dirs if d]


def _npx_off_path(name):
    """npx found outside PATH, put on PATH for this run, or None. See npx_path."""
    import shutil
    node = "node.exe" if os.name == "nt" else "node"
    fb = _fb()
    known = fb.remembered("node.dir")
    dirs = _node_dirs()
    if isinstance(known, str) and known and os.environ.get("REELS_ENGINE_NODE_DIRS") is None:
        dirs = [known] + [d for d in dirs if d != known]
    for d in dirs:
        npx = os.path.join(d, name)
        if not os.path.isfile(npx):
            continue
        # npx is a script that runs on node, so a folder with npx and no node anywhere (npm's own global
        # folder on Windows, say) cannot run it.
        if not os.path.isfile(os.path.join(d, node)) and not shutil.which(node):
            continue
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        if known != d:
            fb.remember("node.dir", d, why="Node was installed but not on this terminal's PATH")
            fb.note("node", f"npx was not on PATH; found Node in {d} and ran it from there")
            _say(f"  Node was not on this terminal's PATH; found it in {d} and used it from there.")
        return npx
    return None


# ---- running `hyperframes check` -------------------------------------------------------------------------
# reel_render.py and reel_gate.py both gate on the same check, so the backup routes live here once: npm's
# cache when the registry cannot be reached, a longer page-load budget when the check's page could not load
# in time, and one more try when the checking tool itself crashed or hung. None of them ever skips the gate:
# whatever route runs, the composition is only called clean on HyperFrames' own verdict.

NAV_RETRY_MS = 120000   # the page-load budget the check gets after its page could not load in time
STOP_CODES = {130, 143, -2, -15, 3221225786}   # her Ctrl-C / a stop (POSIX exit, signal, Windows 0xC000013A)


def check_hang_seconds():
    """How long a check may go without finishing before it counts as hung. Generous on purpose: a whole
    check runs about 40 s on Apple Silicon, a few minutes on a slow PC. REELS_ENGINE_HF_CHECK_HANG_SECONDS
    overrides it."""
    v = os.environ.get("REELS_ENGINE_HF_CHECK_HANG_SECONDS", "").strip()
    return int(v) if v.isdigit() and int(v) > 0 else 600


def hang_words():
    """check_hang_seconds() the way it is said: '10 minutes', or '45 seconds' for a short one set by hand."""
    s = check_hang_seconds()
    return f"{s} seconds" if s < 90 else f"{s // 60} minutes"


def npm_fetch_failed(text):
    """npm's error code when npx itself could not get the package (HyperFrames never started), else None."""
    m = re.search(r"^npm (?:error|ERR!) code (\S+)", text or "", flags=re.M)
    return m.group(1) if m else None


def offline_env(base=None):
    """`base` (default os.environ) set to run npx from npm's own cache, never the registry. HyperFrames at the
    pinned version is in that cache once it has run on this computer, so no connection is needed for it."""
    env = dict(os.environ if base is None else base)
    env["npm_config_prefer_offline"] = "true"
    env["npm_config_offline"] = "true"
    return env


def _kill_tree(p):
    """Stop a hung check and the browser it started. Only ever used on a CHECK: a render is never stopped
    (reel_render._run_render_watched)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=30)
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:   # noqa: BLE001
        pass
    try:
        p.kill()
    except Exception:   # noqa: BLE001
        pass


def _run_once(argv, env, timeout):
    """(exit code, output, how) for one check. how is "" (it finished), "hung" (stopped after `timeout`
    seconds) or "would-not-start" (npx is there but would not launch). The check runs in its own process
    group so a hang can be stopped along with the browser under it; that also keeps her Ctrl-C from
    reaching it, so a Ctrl-C here stops it by hand and then stops this run as always."""
    kw = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt" \
        else {"start_new_session": True}
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             encoding="utf-8", errors="replace", env=env, **kw)
    except OSError:
        return None, "", "would-not-start"
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, (out or "") + (err or ""), ""
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            out, err = p.communicate(timeout=30)
        except Exception:   # noqa: BLE001
            out, err = "", ""
        return p.returncode, (out or "") + (err or ""), "hung"
    except KeyboardInterrupt:
        _kill_tree(p)
        raise


class CheckRun:
    """What run_hf_check found. status:
      "ran"          HyperFrames gave its verdict (rc 0 = clean); the caller reads rc and text as always
      "npm"          npx could not get HyperFrames, not even from npm's cache (npm_code says why)
      "nav"          the check's page did not load in time, even with the longer budget
      "crashed"      the checking tool crashed or hung, twice (how says which)
      "would-not-start"  npx would not launch at all
      "stopped"      her Ctrl-C (rc 130/143): a stop, never retried
    offline is True when the verdict came from npm's cache, so the render that follows runs from it too."""
    def __init__(self):
        self.rc, self.text, self.status, self.how = None, "", "ran", ""
        self.offline, self.npm_code, self.nav_ms = False, None, None
        self.env = None   # the environment the verdict came from (a route that loaded the page is in it)
        self.tried = set()   # the backup routes run_hf_check took: offline, nav, gpu-software, localhost-wrapper, crash


def _localhost_wrapper():
    """product/render_browser.py's localhost wrapper (written fresh), or None: Windows, no render browser yet, a
    copy without render_browser.py, or a browser already chosen by hand (HYPERFRAMES_BROWSER_PATH /
    PRODUCER_HEADLESS_SHELL_PATH, which HyperFrames reads first)."""
    if os.environ.get("HYPERFRAMES_BROWSER_PATH") or os.environ.get("PRODUCER_HEADLESS_SHELL_PATH"):
        return None
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import render_browser
        return render_browser.write_localhost_wrapper() if render_browser.supported() else None
    except Exception:   # noqa: BLE001
        return None


def _learned_check_env(env, fb):
    """The routes this computer's check has needed before (below), applied up front: the check then goes straight
    to what loads here instead of running out of time first on every reel."""
    if fb.remembered("check.gpu-software") and not env.get("PRODUCER_BROWSER_GPU_MODE"):
        env = dict(env, PRODUCER_BROWSER_GPU_MODE="software")
        _say("  checking with software drawing, the way this computer's check loads its page.")
    if fb.remembered("check.localhost-wrapper"):
        wrap = _localhost_wrapper()
        if wrap:
            env = dict(env, HYPERFRAMES_BROWSER_PATH=wrap)
            _say("  checking through the localhost wrapper, the way this computer's check loads its page.")
    return env


_CHECK_PROGRESS = re.compile(r"^\[hyperframes\] check: [a-z][a-z ]* \d+/\d+[ \t]*\r?\n?", re.M)


def _without_check_progress(text):
    """The check's output without its per-step progress lines. From 0.8.191 HyperFrames writes one line per sample,
    overlap batch and craft frame ("[hyperframes] check: samples 12/52"), a few hundred on a caption layer, all of
    them arriving at once here (the output is read when the check ends). They are dropped from what is echoed only;
    the verdict, the findings and CheckRun.text are untouched."""
    return _CHECK_PROGRESS.sub("", text or "")


def run_hf_check(argv, step="render-check", echo=True):
    """Run `hyperframes check` (argv from hf_check_argv) with the backup routes above. Prints each attempt's
    output as it comes back when echo is set. Never decides clean or not: that is HyperFrames' verdict.

    A page that still does not load with the longer budget gets the render's own two routes, one at a time
    (ISS-77, an Intel Mac whose check ran out of time at 30 s and again at 120 s): software drawing
    (PRODUCER_BROWSER_GPU_MODE=software), then, on a Mac or Linux, the localhost wrapper (render_browser.py).
    They used to follow only a failed RENDER, and the render never came, because a check that could not load
    stopped the reel first. Whichever loads is remembered for the check and for the render after it."""
    fb = _fb()
    env = _learned_check_env(hf_check_env(), fb)
    r = CheckRun()
    tried = r.tried = set()
    before_software = None   # the environment the wrapper is tried in: drawing as it was before software
    while True:
        r.nav_ms = env.get("PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS")
        rc, text, how = _run_once(argv, env, check_hang_seconds())
        if echo and text:
            sys.stdout.write(_without_check_progress(text))
            sys.stdout.flush()
        r.rc, r.text, r.how = rc, text, how
        if how == "would-not-start":
            r.status = how
            return r
        if rc in STOP_CODES:
            r.status = "stopped"
            return r
        verdict = re.search(r"Check (?:failed|passed)", text)
        npm_code = npm_fetch_failed(text)
        if not how and rc != 0 and npm_code and not verdict:
            # Offline (or the registry unreachable) while HyperFrames is already in npm's cache from an
            # earlier run: run it from there. Not remembered: the connection comes back.
            if "offline" not in tried and str(env.get("npm_config_offline", "")).lower() != "true":
                tried.add("offline")
                env = offline_env(env)
                fb.note(step, f"npx could not reach npm (npm said {npm_code}); ran HyperFrames from npm's cache")
                _say("  Could not reach npm just now, so HyperFrames runs from the copy already on this computer.")
                continue
            r.status, r.npm_code = "npm", npm_code
            return r
        if not how and rc != 0 and re.search(r"navigation timed out|navigation timeout", text, flags=re.I):
            budget = int(r.nav_ms) if str(r.nav_ms or "").isdigit() else 10000
            if "nav" not in tried and budget < NAV_RETRY_MS:
                tried.add("nav")
                env = dict(env, PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS=str(NAV_RETRY_MS))
                fb.note(step, f"the check's page did not load within {budget // 1000} s; checked again with "
                              f"{NAV_RETRY_MS // 1000} s")
                _say(f"  The check's page did not load within {budget // 1000} s on this computer; checking "
                     f"again with {NAV_RETRY_MS // 1000} s.")
                continue
            if "gpu-software" not in tried and env.get("PRODUCER_BROWSER_GPU_MODE") != "software":
                tried.add("gpu-software")
                before_software = env
                env = dict(env, PRODUCER_BROWSER_GPU_MODE="software")
                fb.note(step, f"the check's page did not load within {budget // 1000} s; checked again with "
                              f"software drawing (PRODUCER_BROWSER_GPU_MODE=software)")
                _say("  The check's page still did not load; checking once more with software drawing (slower, "
                     "but it loads where the graphics path stalls).")
                continue
            if "localhost-wrapper" not in tried and not env.get("HYPERFRAMES_BROWSER_PATH"):
                tried.add("localhost-wrapper")
                wrap = _localhost_wrapper()
                if wrap:
                    env = dict(before_software or env, HYPERFRAMES_BROWSER_PATH=wrap)
                    fb.note(step, "the check's page did not load, with software drawing either; checked again "
                                  "through the localhost wrapper (HYPERFRAMES_BROWSER_PATH, MAP localhost 127.0.0.1)")
                    _say("  The check's page still did not load; checking once more, opening it by number "
                         "(127.0.0.1) instead of by the name localhost, which something on this computer can block.")
                    continue
            r.status = "nav"
            return r
        if how == "hung" or (rc != 0 and not verdict):
            # The checking tool crashed (it ended without HyperFrames' own verdict) or hung. That says
            # nothing about the composition, so it gets one more try; a second failure is said plainly.
            if "crash" not in tried:
                tried.add("crash")
                what = (f"gave no answer for {hang_words()}" if how == "hung"
                        else f"stopped without a verdict (exit {rc})")
                fb.note(step, f"hyperframes check {what}; ran the check once more")
                _say(f"  The checking tool {what}; running the check once more.")
                continue
            r.status = "crashed"
            return r
        # HyperFrames gave its verdict. A route that got it there is said once and, where the cause is
        # this computer, remembered.
        if "nav" in tried:
            fb.remember("render.nav-timeout-ms", NAV_RETRY_MS,
                        why=f"the check's page only loaded here with {NAV_RETRY_MS // 1000} s")
        # The route that loaded the page, for every later check and for the render that follows (reel_render.py
        # applies render.* up front), since it draws the same page in the same browser.
        if env.get("HYPERFRAMES_BROWSER_PATH") and "localhost-wrapper" in tried:
            fb.remember("check.localhost-wrapper", True, why="the check's page only loaded here through the "
                                                             "localhost wrapper")
            fb.remember("render.localhost-wrapper", True, why="the check's page only loaded here by number "
                                                              "(localhost wrapper, HYPERFRAMES_BROWSER_PATH)")
        elif env.get("PRODUCER_BROWSER_GPU_MODE") == "software" and "gpu-software" in tried:
            fb.remember("check.gpu-software", True, why="the check's page only loaded here with software drawing")
            fb.remember("render.gpu-software", True, why="the check's page only loaded here with software drawing "
                                                         "(PRODUCER_BROWSER_GPU_MODE=software)")
        r.env = env
        r.offline = "offline" in tried
        return r
