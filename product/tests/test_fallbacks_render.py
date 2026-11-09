#!/usr/bin/env python3
"""test_fallbacks_render.py — never a dead end at the graphics check and render (rows 14-21 of the fallbacks brief).

When the usual route fails and a working one exists, the engine takes it, finishes, logs one line to
_local/fallbacks.log, and (when the cause is the computer) remembers it in _local/pivots.json. The gate is
never skipped: only HyperFrames' own verdict lets a render through, and a real "Check failed" refuses as before.

  14  a failed render is rendered again with --low-memory-mode, then software drawing; whichever works is
      remembered (render.low-memory / render.gpu-software) and applied up front later. Her Ctrl-C (exit 130)
      and a gate refusal are never retried; renders never overlap; a renderer that will not start says so.
  14b a render whose PAGE did not load ("Navigation timeout ... exceeded", ISS-77) is rendered a third time
      through the localhost wrapper (product/render_browser.py), remembered (render.localhost-wrapper) and
      applied up front later; an unrelated failure never gets it; Windows never writes it.
  15  offline with HyperFrames in npm's cache: the check (and the render after it) run from the cache.
  16  the check's page did not load in time: checked again with 120 s, remembered (render.nav-timeout-ms).
  17  the checking tool crashed or hung: one more try, then "the checking tool could not run", exit 4, no render.
  18  Node installed but not on PATH: found in the install folders, put on PATH, remembered (node.dir).
  19  a licensed pack font missing from the composition: staged from her CapCut, then rendered; still
      missing keeps the refusal.
  20  the caption-stretch render falling back to full length is logged.
  21  build-reel-mp4.py: an empty ffprobe answer after a finished bake reports the file, no traceback.

Everything runs against a scratch copy of product/ with a stand-in `npx` on PATH. Nothing real renders.

Run:  python3 product/tests/test_fallbacks_render.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-600:]) if detail else ''}")


# Stands in for `npx hyperframes@<pin> check|render`. Every call is written to FAKE_LOG with the settings it
# ran under, and its start and end time (to prove renders never overlap).
FAKE_NPX = r'''#!{py}
import json, os, sys, time
args = sys.argv[1:]
sub = args[1] if len(args) > 1 else ""
log = os.environ["FAKE_LOG"]
calls = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
rec = {{"sub": sub, "args": args, "start": time.time(),
       "gpu": os.environ.get("PRODUCER_BROWSER_GPU_MODE"),
       "nav": os.environ.get("PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS"),
       "offline": os.environ.get("npm_config_offline"),
       "browser": os.environ.get("HYPERFRAMES_BROWSER_PATH")}}

def done(code, said=""):
    if said:
        print(said)
    rec["end"] = time.time()
    with open(log, "a") as f:
        f.write(json.dumps(rec) + "\n")
    sys.exit(code)

mode = os.environ.get("FAKE_CHECK", "pass")
if sub == "check":
    n = sum(1 for c in calls if c["sub"] == "check") + 1
    if mode == "offline" and rec["offline"] != "true":
        done(1, "npm error code ENOTFOUND\nnpm error network request to https://registry.npmjs.org failed")
    if mode == "uncached":
        done(1, "npm error code ENOTCACHED")
    if mode == "nav-always" or (mode == "nav" and rec["nav"] != "120000"):
        done(1, "✗ Check failed: Navigation timeout of 10000 ms exceeded")
    if mode == "crash" or (mode == "crash-once" and n == 1):
        done(139)
    if mode == "hang":
        time.sleep(60)
    if mode == "realfail":
        done(1, "Layout\n  ✗ overflow: text runs off the canvas\n◇  Check failed")
    done(0, "◇  Check passed")
if sub == "render":
    out = args[args.index("--output") + 1]
    how = os.environ.get("FAKE_RENDER", "ok")
    time.sleep(0.2)
    if how == "stop":
        done(130)
    if how == "loopback":   # the page loads only when the browser maps localhost to 127.0.0.1 (ISS-77)
        b = rec["browser"]
        if b and os.path.exists(b) and "MAP localhost 127.0.0.1" in open(b, encoding="utf-8").read():
            open(out, "wb").write(b"rendered")
            done(0)
        done(1, "Error: Navigation timeout of 30000 ms exceeded\n    at LifecycleWatcher._LifecycleWatcher_createTimeout")
    ok = (how == "ok" or (how == "low-memory" and "--low-memory-mode" in args)
          or (how == "software" and rec["gpu"] == "software"))
    if ok:
        open(out, "wb").write(b"rendered")
        done(0)
    done(1, "Error: the render failed")
done(0)
'''

# Runs the scratch reel_render with the post-render video checks stubbed (the stand-in render is not a video).
DRIVER = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
import reel_render as rr
rr._verify_render_has_content = lambda out, d, strict=False: (True, [])
rr._alpha_is_real = lambda out: None
if os.environ.get("FAKE_SPANS"):
    rr.render_spans.load_plan = lambda d: {"spans": [[0, 30]], "fps": 30, "frames": 30}
    rr.render_spans.describe = lambda plan: "render only where they are on screen"
    rr._render_by_spans = lambda d, out, plan, extra, env=None: (False, "a stretch did not render")
if os.environ.get("FAKE_RENDER_OSERROR"):
    def _boom(*a, **k):
        raise FileNotFoundError("npx")
    rr._run_render_watched = _boom
sys.argv = ["reel_render.py"] + sys.argv[2:]
sys.exit(rr.main())
'''

COMP_HTML = ('<!doctype html><html><head><style>{font}</style></head><body><div id="root" '
             'data-composition-id="reel" data-start="0" data-duration="1" data-width="1080" '
             'data-height="1920"></div></body></html>')


class Rig:
    def __init__(self, tmp):
        self.tmp = tmp
        self.eng = os.path.join(tmp, "engine", "product")
        os.makedirs(self.eng)
        for f in os.listdir(PRODUCT):
            if f.endswith(".py"):
                shutil.copy(os.path.join(PRODUCT, f), os.path.join(self.eng, f))
        self.npxbin = os.path.join(tmp, "npxbin")
        os.makedirs(self.npxbin)
        self._write(os.path.join(self.npxbin, "npx"), FAKE_NPX.format(py=sys.executable), exe=True)
        self._write(os.path.join(self.npxbin, "node"), "#!/bin/sh\nexit 0\n", exe=True)
        self.driver = os.path.join(tmp, "driver.py")
        self._write(self.driver, DRIVER)
        self.n = 0

    @staticmethod
    def _write(path, body, exe=False):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        if exe:
            os.chmod(path, 0o755)

    def fresh(self, font=""):
        """A new composition, a new _local/ and a new call log."""
        self.n += 1
        base = os.path.join(self.tmp, f"case{self.n}")
        self.comp = os.path.join(base, "comp")
        self._write(os.path.join(self.comp, "index.html"), COMP_HTML.format(font=font))
        self.local = os.path.join(base, "_local")
        self.log = os.path.join(base, "calls.jsonl")
        self.out = os.path.join(base, "out.mov")
        return self

    def env(self, path=None, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "REELS_ENGINE_", "PRODUCER_"))
               and k not in ("npm_config_offline", "npm_config_prefer_offline", "REEL_FULL_RENDER",
                             "HYPERFRAMES_BROWSER_PATH")}
        env.update(PATH=path or (self.npxbin + os.pathsep + os.environ.get("PATH", "")),
                   PYTHONDONTWRITEBYTECODE="1", REELS_RENDER_STALL_SECONDS="0", REEL_SKIP_ALPHA_CHECK="1",
                   REELS_ENGINE_LOCAL=self.local, REELS_ENGINE_NODE_DIRS="", FAKE_LOG=self.log)
        env.update(extra)
        return env

    def render(self, *flags, **extra):
        argv = [sys.executable, self.driver, self.eng, "render", self.comp, "-o", self.out,
                "--force", "--no-safe-zone", "--no-subject", *flags]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=self.env(**extra))
        return r.returncode, r.stdout + r.stderr

    def gate(self, path=None, **extra):
        argv = [sys.executable, os.path.join(self.eng, "reel_gate.py"), self.comp, "--canvas", "1080x1920"]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=self.env(path=path, **extra))
        return r.returncode, r.stdout + r.stderr

    def calls(self, sub=None):
        if not os.path.exists(self.log):
            return []
        cs = [json.loads(l) for l in open(self.log, encoding="utf-8")]
        return [c for c in cs if sub is None or c["sub"] == sub]

    def pivots(self):
        try:
            return json.load(open(os.path.join(self.local, "pivots.json"), encoding="utf-8"))
        except Exception:
            return {}

    def logged(self):
        try:
            return open(os.path.join(self.local, "fallbacks.log"), encoding="utf-8").read()
        except Exception:
            return ""


def test_row14_render_retries(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="low-memory")
    rs = rig.calls("render")
    check("14 low-memory: the reel finishes", rc == 0 and os.path.exists(rig.out), (rc, said))
    check("14 low-memory: rendered twice, the second with --low-memory-mode",
          len(rs) == 2 and "--low-memory-mode" not in rs[0]["args"] and "--low-memory-mode" in rs[1]["args"], rs)
    check("14 low-memory: remembered", rig.pivots().get("render.low-memory", {}).get("value") is True, rig.pivots())
    check("14 low-memory: one line in the log", rig.logged().count("render: ") == 1, rig.logged())
    check("14 low-memory: said calmly, no alarm", "Rendering once more" in said and "⛔" not in said, said)
    os.remove(rig.log)
    rc, said = rig.render(FAKE_RENDER="low-memory")
    rs = rig.calls("render")
    check("14 low-memory: a later render starts with it, one render",
          rc == 0 and len(rs) == 1 and "--low-memory-mode" in rs[0]["args"], (rc, rs, said))

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="software")
    rs = rig.calls("render")
    check("14 software: the reel finishes", rc == 0, (rc, said))
    check("14 software: plain, then low-memory, then software drawing (without low-memory)",
          len(rs) == 3 and rs[2]["gpu"] == "software" and rs[1]["gpu"] is None
          and "--low-memory-mode" not in rs[2]["args"], rs)
    pv = rig.pivots()
    check("14 software: remembered render.gpu-software, not low-memory",
          pv.get("render.gpu-software", {}).get("value") is True and "render.low-memory" not in pv, pv)
    os.remove(rig.log)
    rc, said = rig.render(FAKE_RENDER="software")
    rs = rig.calls("render")
    check("14 software: a later render starts with software drawing",
          rc == 0 and len(rs) == 1 and rs[0]["gpu"] == "software", (rc, rs))
    starts = sorted((c["start"], c["end"]) for c in rig.calls("render"))
    check("14 renders never overlap", all(a[1] <= b[0] for a, b in zip(starts, starts[1:])), starts)

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="stop")
    check("14 her Ctrl-C (exit 130) is a stop, never retried",
          rc == 130 and len(rig.calls("render")) == 1 and not rig.pivots(), (rc, rig.calls("render"), said))

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="never")
    check("14 nothing works: exit 1 after three tries, pointing at /report-a-problem",
          rc == 1 and len(rig.calls("render")) == 3 and "/report-a-problem" in said, (rc, said))
    check("14 nothing works: nothing remembered", not rig.pivots(), rig.pivots())
    check("14 the composition folder is untouched", os.path.exists(os.path.join(rig.comp, "index.html")))

    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="realfail")
    check("14 a check finding is a warning: checked once, rendered as placed, never called clean (2026-10-18)",
          rc == 0 and len(rig.calls("check")) == 1 and len(rig.calls("render")) == 1 and "rendering anyway" in said
          and "gated clean" not in said, (rc, said))

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER_OSERROR="1")
    check("14 a renderer that will not start: exit 4, said plainly, no traceback",
          rc == 4 and "renderer could not start" in said and "Traceback" not in said, (rc, said))


def test_row14b_nav_words():
    sys.path.insert(0, PRODUCT)
    from reel_render import _NAV_FAIL
    plain = ('"browserConsoleErrors":["[FrameCapture:NAV] page.goto start mode=screenshot timeoutMs=60000 '
             'url=http://localhost:1/","[FrameCapture:NAV] page.goto complete status=200"]')
    check("14b the renderer's plain page.goto log line is not a page that failed to load", not _NAV_FAIL.search(plain))
    for said in ("Error: Navigation timeout of 30000 ms exceeded", "page.goto timed out after 60000 ms",
                 "page.goto failed: timeout of 60000 ms", "net::ERR_CONNECTION_REFUSED at http://localhost:1/"):
        check(f"14b a page that failed to load is still read as one: {said}", bool(_NAV_FAIL.search(said)))


def test_row14b_localhost_wrapper(rig):
    # A home whose HyperFrames cache holds a render browser, the way `browser ensure` lays it out.
    home = os.path.join(rig.tmp, "home14b")
    shell = os.path.join(home, ".cache", "hyperframes", "chrome", "chrome-headless-shell", "mac_arm-1.0",
                         "chrome-headless-shell-mac-arm64", "chrome-headless-shell")
    rig._write(shell, "#!/bin/sh\nexit 0\n", exe=True)

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="loopback", HOME=home)
    rs = rig.calls("render")
    check("14b page did not load: the reel finishes", rc == 0 and os.path.exists(rig.out), (rc, said))
    check("14b page did not load: plain, low-memory, software, then the localhost wrapper (drawing as before)",
          len(rs) == 4 and not any(c["browser"] for c in rs[:3]) and rs[3]["browser"]
          and rs[3]["gpu"] is None and "--low-memory-mode" not in rs[3]["args"], rs)
    wrap = rs[3]["browser"] if len(rs) == 4 else ""
    body = open(wrap, encoding="utf-8").read() if wrap and os.path.exists(wrap) else ""
    check("14b the wrapper starts her render browser with localhost mapped to 127.0.0.1",
          shell in body and "MAP localhost 127.0.0.1" in body and "--no-proxy-server" in body
          and wrap.startswith(rig.local), (wrap, body))
    pv = rig.pivots()
    check("14b page did not load: remembered render.localhost-wrapper only",
          pv.get("render.localhost-wrapper", {}).get("value") is True
          and "render.gpu-software" not in pv and "render.low-memory" not in pv, pv)
    check("14b page did not load: logged", "localhost wrapper" in rig.logged(), rig.logged())
    check("14b said calmly, no alarm", "opening it by number" in said and "⛔" not in said, said)
    os.remove(rig.log)
    rc, said = rig.render(FAKE_RENDER="loopback", HOME=home)
    rs = rig.calls("render")
    check("14b a later render starts with the wrapper, one render",
          rc == 0 and len(rs) == 1 and rs[0]["browser"] and "the way this computer renders" in said, (rc, rs, said))

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="never", HOME=home)
    check("14b an unrelated failure never gets the wrapper",
          rc == 1 and len(rig.calls("render")) == 3 and not any(c["browser"] for c in rig.calls("render"))
          and "render.localhost-wrapper" not in rig.pivots(), (rc, rig.calls("render"), said))

    rig.fresh()
    rc, said = rig.render(FAKE_RENDER="loopback", HOME=os.path.join(rig.tmp, "home-no-browser"))
    check("14b no render browser downloaded yet: three tries, nothing remembered, no traceback",
          rc == 1 and len(rig.calls("render")) == 3 and not rig.pivots() and "Traceback" not in said, (rc, said))

    # Windows: the route is skipped (a /bin/sh script cannot be the browser there), in this process.
    sys.path.insert(0, rig.eng)
    import render_browser
    real = os.name
    try:
        os.name = "nt"
        got = render_browser.write_localhost_wrapper(os.path.join(rig.tmp, "win14b"), browser=shell)
        sup = render_browser.supported()
    finally:
        os.name = real
    check("14b on Windows no wrapper is written and the route is off",
          got is None and sup is False and not os.path.exists(os.path.join(rig.tmp, "win14b")), (got, sup))


def test_row15_offline(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="offline")
    cs, rs = rig.calls("check"), rig.calls("render")
    check("15 offline: checked again from npm's cache and rendered", rc == 0 and len(cs) == 2
          and cs[1]["offline"] == "true", (rc, cs, said))
    check("15 offline: the render runs from the cache too", rs and rs[0]["offline"] == "true", rs)
    check("15 offline: logged, not remembered", "render-check: npx could not reach npm" in rig.logged()
          and not rig.pivots(), (rig.logged(), rig.pivots()))
    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="uncached")
    check("15 never cached: one try only (already offline-proof), exit 4, the go-online answer",
          rc == 4 and "browser ensure" in said and "Fix the composition" not in said and not rig.calls("render"),
          (rc, said))
    rig.fresh()
    rc, said = rig.gate(FAKE_CHECK="offline")
    check("15 the gate uses the same route", rc == 0 and "gate-check: npx could not reach npm" in rig.logged(),
          (rc, said))


def test_row16_nav_timeout(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="nav")
    cs = rig.calls("check")
    check("16 nav: checked again with 120 s and rendered", rc == 0 and len(cs) == 2 and cs[1]["nav"] == "120000",
          (rc, cs, said))
    check("16 nav: remembered", str(rig.pivots().get("render.nav-timeout-ms", {}).get("value")) == "120000",
          rig.pivots())
    check("16 nav: logged", "render-check: the check's page did not load" in rig.logged(), rig.logged())
    os.remove(rig.log)
    rc, said = rig.render(FAKE_CHECK="nav")
    cs = rig.calls("check")
    check("16 nav: a later check starts with 120 s", rc == 0 and len(cs) == 1 and cs[0]["nav"] == "120000",
          (rc, cs))
    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="nav-always", PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS="120000")
    cs = rig.calls("check")
    # ISS-77: before giving up, the check takes the render's own routes, software drawing first (then the localhost
    # wrapper where a render browser is there to wrap); nothing that did not load is remembered
    check("16 nav: already at 120 s, still out of time: exit 4, not blamed on the composition",
          rc == 4 and "could not start in time" in said and "/report-a-problem" in said
          and len(cs) in (2, 3) and cs[0]["gpu"] is None and cs[1]["gpu"] == "software"
          and "Software drawing" in said and not rig.calls("render"), (rc, cs, said))
    check("16 nav: a route that did not load is not remembered",
          not any(k in rig.pivots() for k in ("render.gpu-software", "check.gpu-software",
                                              "render.localhost-wrapper", "check.localhost-wrapper")), rig.pivots())


def test_row17_tool_crash(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="crash-once")
    check("17 crashed once: checked again, then rendered on its verdict",
          rc == 0 and len(rig.calls("check")) == 2 and len(rig.calls("render")) == 1, (rc, said))
    check("17 crashed once: logged", "render-check: hyperframes check stopped without a verdict" in rig.logged(),
          rig.logged())
    rig.fresh()
    rc, said = rig.render(FAKE_CHECK="crash")
    check("17 crashed twice: exit 4, the tool could not run, never rendered",
          rc == 4 and "checking tool could not run" in said and "/report-a-problem" in said
          and not rig.calls("render") and "Fix the composition" not in said, (rc, said))
    rig.fresh()
    t0 = time.monotonic()
    rc, said = rig.render(FAKE_CHECK="hang", REELS_ENGINE_HF_CHECK_HANG_SECONDS="2")
    check("17 hung twice: stopped after the limit, exit 4, never rendered",
          rc == 4 and "gave no answer for 2 seconds" in said and not rig.calls("render")
          and time.monotonic() - t0 < 60, (rc, said))
    rig.fresh()
    rc, said = rig.gate(FAKE_CHECK="crash")
    check("17 the gate says the same and is not safe to render",
          rc == 4 and "checking tool could not run" in said and "safe to render." not in said.replace("NOT safe", ""),
          (rc, said))
    rig.fresh()
    rc, said = rig.gate(FAKE_CHECK="realfail")
    check("17 a real failed check in the gate is reported as before",
          rc == 1 and "fix them before rendering" in said and len(rig.calls("check")) == 1, (rc, said))


def test_row18_node_off_path(rig):
    rig.fresh()
    home = os.path.join(rig.tmp, "home18")
    nodedir = os.path.join(home, ".nvm", "versions", "node", "v20.11.1", "bin")
    for d in (nodedir, os.path.join(home, ".nvm", "versions", "node", "v18.2.0", "bin")):
        os.makedirs(d)
    shutil.copy(os.path.join(rig.npxbin, "npx"), os.path.join(nodedir, "npx"))
    shutil.copy(os.path.join(rig.npxbin, "node"), os.path.join(nodedir, "node"))
    bare = "/usr/bin" + os.pathsep + "/bin"
    if shutil.which("npx", path=bare):
        print("test_fallbacks_render: row 18 subprocess part skipped (npx is in /usr/bin here)")
    else:
        rc, said = rig.gate(path=bare, REELS_ENGINE_NODE_DIRS=nodedir)
        check("18 Node off PATH: found, and the check ran", rc == 0 and len(rig.calls("check")) == 1, (rc, said))
        check("18 Node off PATH: remembered", rig.pivots().get("node.dir", {}).get("value") == nodedir, rig.pivots())
        check("18 Node off PATH: logged once, said calmly",
              rig.logged().count("node: ") == 1 and "found it in" in said and "Node is not installed" not in said,
              (rig.logged(), said))
        rc, said = rig.gate(path=bare, REELS_ENGINE_NODE_DIRS=nodedir)
        check("18 the second time: no new log line", rc == 0 and rig.logged().count("node: ") == 1, rig.logged())

    # The default search, in this process: nvm's newest version first; Windows looks in Program Files.
    sys.path.insert(0, rig.eng)
    import npx_run
    saved = dict(os.environ)
    try:
        os.environ.pop("REELS_ENGINE_NODE_DIRS", None)
        os.environ["HOME"] = home
        os.environ["REELS_ENGINE_LOCAL"] = os.path.join(rig.tmp, "local18")
        dirs = npx_run._node_dirs()
        nv = [d for d in dirs if ".nvm" in d]
        check("18 the search covers Homebrew, /usr/local and nvm, newest nvm first",
              os.name == "nt" or ("/opt/homebrew/bin" in dirs and "/usr/local/bin" in dirs
                                  and len(nv) == 2 and "v20.11.1" in nv[0]), dirs)
        real = os.name
        try:
            os.name = "nt"
            wdirs = npx_run._node_dirs()
        finally:
            os.name = real
        check("18 on Windows it looks in Program Files\\nodejs and nvm-windows",
              any(d.endswith("nodejs") and "Program Files" in d for d in wdirs)
              and any(os.path.join("AppData", "Roaming", "nvm") in d or "nvm" in d for d in wdirs + ["nvm"]), wdirs)
        os.environ["REELS_ENGINE_NODE_DIRS"] = nodedir
        os.environ["PATH"] = bare
        if not shutil.which("npx", path=bare):
            got = npx_run.npx_path()
            check("18 npx_path returns the found npx and puts its folder on PATH",
                  got == os.path.join(nodedir, "npx") and os.environ["PATH"].split(os.pathsep)[0] == nodedir,
                  (got, os.environ["PATH"]))
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_row19_fonts(rig):
    face = "@font-face{font-family:Soup;src:url('soup.ttf');}"
    hands = os.path.join(rig.tmp, "engine", "product", "creative-vault", "hands-off", "playful")
    os.makedirs(hands, exist_ok=True)
    fontsrc = os.path.join(rig.tmp, "capcut-fonts", "SoupDuJour.ttf")
    rig._write(fontsrc, "a font")
    resolver = os.path.join(rig.eng, "capcut_userfonts.py")
    real_resolver = open(resolver, encoding="utf-8").read()
    try:
        rig._write(resolver, "import os\n"
                             "def resolve_font_file(name, _=None):\n"
                             f"    return {fontsrc!r} if name == 'Soup Du Jour' and os.environ.get('FAKE_HAS_FONT') "
                             "else None\n")
        rig.fresh(font=face)
        rc, said = rig.render(FAKE_HAS_FONT="1")
        check("19 missing font: staged from her CapCut, then rendered",
              rc == 0 and os.path.exists(os.path.join(rig.comp, "soup.ttf")) and len(rig.calls("render")) == 1,
              (rc, said))
        check("19 missing font: logged", "render-fonts: soup.ttf" in rig.logged(), rig.logged())
        os.remove(os.path.join(hands, "soup.ttf"))
        rig.fresh(font=face)
        rc, said = rig.render()
        check("19 not in her CapCut either: still refuses (exit 3), no substitute typeface",
              rc == 3 and "REFUSING to render" in said and not rig.calls("render"), (rc, said))
        rig.fresh(font="@font-face{font-family:X;src:url('nothere.ttf');}")
        rc, said = rig.render(FAKE_HAS_FONT="1")
        check("19 a font that is not a pack font: refuses as before", rc == 3 and "nothere.ttf" in said, (rc, said))
    finally:
        rig._write(resolver, real_resolver)


def test_row20_spans(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_SPANS="1")
    check("20 spans fell back to full length: rendered", rc == 0 and len(rig.calls("render")) == 1, (rc, said))
    check("20 spans fallback: logged",
          "render-spans: rendering only the on-screen stretches did not work (a stretch did not render)"
          in rig.logged(), rig.logged())


def test_row21_bake_duration():
    src = open(os.path.join(PRODUCT, "build-reel-mp4.py"), encoding="utf-8").read()
    start = src.index("# The bake is done here.")
    end = src.index("\n", src.index('print(f"[mp4] wrote {OUT}', start))
    snippet = src[start:end]

    class _R:
        def __init__(self, out):
            self.stdout = out

    def run(answer):
        def fake_run(*a, **k):
            if isinstance(answer, Exception):
                raise answer
            return _R(answer)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                exec(snippet, {"subprocess": type("S", (), {"run": staticmethod(fake_run)}), "OUT": "reel.mp4"})
        except Exception as e:   # noqa: BLE001
            return f"RAISED {type(e).__name__}"
        return buf.getvalue()

    check("21 empty ffprobe answer: the finished file is reported", run("") == "[mp4] wrote reel.mp4\n", run(""))
    check("21 no ffprobe: the finished file is reported", run(FileNotFoundError("ffprobe")) == "[mp4] wrote reel.mp4\n")
    check("21 a real length is still shown", run("12.5\n") == "[mp4] wrote reel.mp4  (12.50s)\n", run("12.5\n"))


def main():
    test_row21_bake_duration()
    test_row14b_nav_words()
    if os.name == "nt":
        print("test_fallbacks_render: rows 14-20 skipped on Windows (POSIX npx stand-in)")
    else:
        tmp = tempfile.mkdtemp(prefix="fallbacks-render-")
        try:
            rig = Rig(tmp)
            for t in (test_row14_render_retries, test_row14b_localhost_wrapper, test_row15_offline, test_row16_nav_timeout,
                      test_row17_tool_crash, test_row18_node_off_path, test_row19_fonts, test_row20_spans):
                t(rig)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_fallbacks_render: FAILED {len(fails)}/{total}:\n  " + "\n  ".join(fails))
        return 1
    print(f"test_fallbacks_render: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
