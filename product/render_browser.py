#!/usr/bin/env python3
"""render_browser.py — the browser HyperFrames renders with, and the localhost wrapper around it.

WHY THE WRAPPER (ISS-77, diagnosed by product/render-check.py). HyperFrames' render page server listens on
127.0.0.1 but hands Chrome the name `localhost`. A VPN, proxy, content filter or security tool can break the
name while the number still works, and then every render stops at page load with "Navigation timeout ...
exceeded" although the check (which loads its page by number) passed. A tiny shell script that starts the
same chrome-headless-shell with --host-resolver-rules="MAP localhost 127.0.0.1" --no-proxy-server, handed to
HyperFrames as HYPERFRAMES_BROWSER_PATH, takes the name out of it. HyperFrames 0.9.6 reads that variable in
its BrowserManager (resolveHeadlessShellPath) after PRODUCER_HEADLESS_SHELL_PATH, and refuses a path that does
not exist, so the script is always written before it is named.

Used by product/render-check.py (variants 3 and 4 of its experiment) and by product/reel_render.py (the third
retry after a render whose page did not load, remembered as "render.localhost-wrapper").

MAC AND LINUX ONLY. On Windows write_localhost_wrapper() returns None and both callers skip the route: the
wrapper is a /bin/sh script, which Windows cannot run as a program, and the .cmd equivalent cannot stand in for
it, because Node (which launches the browser for HyperFrames) refuses to start a .cmd or .bat file as a
program without a shell. Nothing on Windows changes.
"""
import glob, os, shlex, sys

WRAPPER_NAME = "chrome-localhost-wrapper.sh"
WRAPPER_FLAGS = '--host-resolver-rules="MAP localhost 127.0.0.1" --no-proxy-server'


def supported():
    """The wrapper route runs on a Mac or Linux only (see the note at the top)."""
    return os.name != "nt"


def find_browser():
    """The newest chrome-headless-shell HyperFrames downloaded, looked for where HyperFrames itself looks:
    its own cache first, then puppeteer's. None when neither has one (it downloads on the first render)."""
    home = os.path.expanduser("~")
    name = "chrome-headless-shell.exe" if os.name == "nt" else "chrome-headless-shell"
    for cache in (os.path.join(home, ".cache", "hyperframes", "chrome"),
                  os.path.join(home, ".cache", "puppeteer", "chrome-headless-shell")):
        bins = sorted(glob.glob(os.path.join(cache, "**", name), recursive=True))
        bins = [b for b in bins if os.path.isfile(b) and os.access(b, os.X_OK)]
        if bins:
            return bins[-1]
    return None


def default_folder():
    """Where reel_render keeps the wrapper: the engine's own _local/ (never shipped, kept by every update),
    the same folder product/fallbacks.py keeps its records in."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import fallbacks
        return os.path.join(fallbacks._local_dir(), "render-browser")
    except Exception:   # noqa: BLE001 — a copy without fallbacks.py still gets a working folder
        import tempfile
        return os.path.join(tempfile.gettempdir(), "reels-engine-render-browser")


def write_localhost_wrapper(folder=None, browser=None):
    """Write the wrapper into `folder` and return its path, or None when the route cannot run here: Windows,
    or no render browser downloaded yet. Rewritten every time, so it always points at the browser that is
    there now (a `browser ensure` can replace it)."""
    if not supported():
        return None
    browser = browser or find_browser()
    if not browser:
        return None
    folder = folder or default_folder()
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, WRAPPER_NAME)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/sh\nexec {shlex.quote(browser)} {WRAPPER_FLAGS} "$@"\n')
        os.chmod(path, 0o755)
        return path
    except OSError:
        return None


# A first start of a freshly downloaded browser can be slow (macOS checks a new unsigned program on its first
# run): measured on an Intel Mac, `hyperframes doctor` gave up on it (ETIMEDOUT) while a direct start a minute
# later answered in under 8 s. So the start is given a generous budget, and a second one if the first ran out.
LAUNCH_TIMEOUTS = (60, 120)


def launch_check(browser=None, timeouts=None):
    """Start the render browser once (`--version`, nothing rendered) and say how it went:
      "ok"                 it started and answered
      "missing"            no render browser found where HyperFrames keeps it, so nothing could be started
      "failed: <why>"      it is there but did not start: the exit code and its last line, or "did not answer"
    Callers mark the browser ready only on "ok". A start that does not answer is stopped with everything it
    started (its own process group), so nothing is left running."""
    import signal, subprocess
    browser = browser or find_browser()
    if not browser:
        return "missing"
    why = "did not answer"
    for t in (timeouts or LAUNCH_TIMEOUTS):
        kw = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt" \
            else {"start_new_session": True}
        try:
            p = subprocess.Popen([browser, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 stdin=subprocess.DEVNULL, text=True, **kw)
        except OSError as e:
            return f"failed: could not start it ({e})"
        try:
            out, err = p.communicate(timeout=t)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=30)
                else:
                    os.killpg(p.pid, signal.SIGKILL)
            except Exception:   # noqa: BLE001
                p.kill()
            try:
                p.communicate(timeout=10)
            except Exception:   # noqa: BLE001
                pass
            why = f"did not answer within {t} s"
            continue
        if p.returncode == 0:
            return "ok"
        tail = [l for l in ((err or "") + (out or "")).splitlines() if l.strip()]
        return f"failed: exit {p.returncode}" + (f", {tail[-1].strip()}" if tail else "")
    return f"failed: {why}"


def mark_ready(ver, local_dir=None):
    """Write _local/hf-browser-<ver>.ok (what check-setup.sh reads as "Render engine: ready") only when the browser
    starts. Returns launch_check's answer. A browser that cannot be found is left unmarked too: the marker is
    a claim that it runs."""
    state = launch_check()
    if state == "ok":
        local_dir = local_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_local")
        os.makedirs(local_dir, exist_ok=True)
        with open(os.path.join(local_dir, f"hf-browser-{ver}.ok"), "w", encoding="utf-8") as f:
            f.write("ok\n")
    return state


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--mark-ready":   # set-me-up, after `browser ensure`
        st = mark_ready(sys.argv[2])
        print("render engine: ready (its browser started)." if st == "ok" else
              "render engine: no render browser found yet; it downloads on the first render." if st == "missing" else
              f"render engine: the browser is there but would not start yet ({st[len('failed: '):]}). The first "
              f"render tries it again.")
        sys.exit(0 if st == "ok" else 1)
    b = find_browser()
    print(f"render browser: {b or 'not downloaded yet (it downloads on the first render)'}")
    print("localhost wrapper: " + ("available here" if supported() else "not used on Windows"))
