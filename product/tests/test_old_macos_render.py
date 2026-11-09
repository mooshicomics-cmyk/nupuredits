#!/usr/bin/env python3
"""test_old_macos_render.py — a macOS too old for the graphics renderer is said plainly, never a dead end.

The headless Chrome pinned with 0.8.43 aborted at launch on macOS 12 (dyld "Symbol not found" in VideoToolbox), so no
graphics render could run below macOS 13. 0.8.158 picks Chrome 150 there by itself, but no macOS 12 Mac has proved
it, so product/reel_render.py keeps a net:

  a  macOS 12 + a render that dies with the loader's line: ONE render (no low-memory / software retries, which
     cannot change a missing symbol), one plain line naming the macOS and the CapCut route ("keep it raw"),
     exit 4, one line in _local/fallbacks.log, render.os-unsupported remembered with the macOS version and pin.
  b  the next render on that Mac says it at once: no check, no render.
  c  a macOS update (or a new pin) forgets it, and the renderer is simply tried again.
  d  macOS 12 + a bare abort (exit 134, nothing said): the usual retries first, then the same line.
  e  macOS 12 + the CHECK's browser dying that way (with or without "Check failed"): the same line, no render,
     and the composition is not marked as failed.
  f  macOS 12 + an ordinary render failure, and macOS 14 / not a Mac + the dyld crash: the usual path, nothing
     remembered.
  g  _macos_version reads sw_vers, falls back to platform.mac_ver, and is None off a Mac.
  h  check-setup.sh: one information line on macOS 12 (never counted), none on macOS 13+.
  i  with the stall watcher switched off (REELS_RENDER_STALL_SECONDS=0) the render's words still pass through
     and are still read: the same one render, the same line, remembered.

Everything runs against a scratch copy of product/ with a stand-in `npx` on PATH. Nothing real renders.

Run:  python3 product/tests/test_old_macos_render.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(PRODUCT)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-700:]) if detail else ''}")


# What the loader printed on the buyer's macOS 12 Mac, in the shape HyperFrames passes it on (no machine paths).
DYLD = ("Error: Failed to launch the browser process!\\n"
        "dyld[4242]: Symbol not found: _kVTCompressionPropertyKey_ReferenceBufferCount\\n"
        "  Referenced from: <cache>/chrome-headless-shell\\n"
        "  Expected in: /System/Library/Frameworks/VideoToolbox.framework/Versions/A/VideoToolbox")

FAKE_NPX = r'''#!{py}
import json, os, sys, time
args = sys.argv[1:]
sub = args[1] if len(args) > 1 else ""
log = os.environ["FAKE_LOG"]
rec = {{"sub": sub, "args": args, "gpu": os.environ.get("PRODUCER_BROWSER_GPU_MODE")}}
with open(log, "a") as f:
    f.write(json.dumps(rec) + "\n")

def say(text):
    sys.stdout.write(text + "\n"); sys.stdout.flush()

if sub == "check":
    how = os.environ.get("FAKE_CHECK", "pass")
    if how == "dyld":          # the browser never started: no verdict at all
        say("{dyld}"); sys.exit(1)
    if how == "dyld-verdict":  # the same, but the CLI still printed its "Check failed" line
        say("{dyld}"); say("◇  Check failed"); sys.exit(1)
    say("◇  Check passed"); sys.exit(0)
if sub == "render":
    out = args[args.index("--output") + 1]
    how = os.environ.get("FAKE_RENDER", "ok")
    if how == "ok":
        open(out, "wb").write(b"rendered"); sys.exit(0)
    if how == "dyld":
        say("[render] launching browser"); say("{dyld}"); sys.exit(134)
    if how == "abort":
        sys.exit(134)
    say("Error: the render failed"); sys.exit(1)
sys.exit(0)
'''

# Runs the scratch reel_render with this Mac's macOS stood in (FAKE_MACOS; empty = not a Mac) and the post-render
# video checks stubbed (the stand-in render is not a video).
DRIVER = r'''
import os, sys
sys.path.insert(0, sys.argv[1])
import reel_render as rr
rr._verify_render_has_content = lambda out, d, strict=False: (True, [])
rr._alpha_is_real = lambda out: None
if "FAKE_MACOS" in os.environ:
    rr._macos_version = lambda: os.environ["FAKE_MACOS"] or None
if os.environ.get("FAKE_PIN"):
    rr.HF_VERSION = os.environ["FAKE_PIN"]
sys.argv = ["reel_render.py"] + sys.argv[2:]
sys.exit(rr.main())
'''

COMP_HTML = ('<!doctype html><html><head></head><body><div id="root" data-composition-id="reel" data-start="0" '
             'data-duration="1" data-width="1080" data-height="1920"></div></body></html>')


def write(path, body, exe=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    if exe:
        os.chmod(path, 0o755)


class Rig:
    def __init__(self, tmp):
        self.tmp = tmp
        self.eng = os.path.join(tmp, "engine", "product")
        os.makedirs(self.eng)
        for f in os.listdir(PRODUCT):
            if f.endswith(".py"):
                shutil.copy(os.path.join(PRODUCT, f), os.path.join(self.eng, f))
        if os.path.exists(os.path.join(ROOT, "product.json")):
            shutil.copy(os.path.join(ROOT, "product.json"), os.path.join(tmp, "engine", "product.json"))
        self.npxbin = os.path.join(tmp, "npxbin")
        write(os.path.join(self.npxbin, "npx"), FAKE_NPX.format(py=sys.executable, dyld=DYLD), exe=True)
        write(os.path.join(self.npxbin, "node"), "#!/bin/sh\nexit 0\n", exe=True)
        self.driver = os.path.join(tmp, "driver.py")
        write(self.driver, DRIVER)
        self.n = 0

    def fresh(self):
        """A new composition, a new _local/ and a new call log."""
        self.n += 1
        base = os.path.join(self.tmp, f"case{self.n}")
        self.comp = os.path.join(base, "comp")
        write(os.path.join(self.comp, "index.html"), COMP_HTML)
        self.local = os.path.join(base, "_local")
        self.log = os.path.join(base, "calls.jsonl")
        self.out = os.path.join(base, "out.mov")
        return self

    def render(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "REELS_ENGINE_", "PRODUCER_"))
               and k not in ("npm_config_offline", "npm_config_prefer_offline", "REEL_FULL_RENDER")}
        # The watcher stays ON (a positive stall threshold): it is what reads the renderer's words.
        env.update(PATH=self.npxbin + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                   REELS_RENDER_STALL_SECONDS="600", REEL_SKIP_ALPHA_CHECK="1", REELS_ENGINE_LOCAL=self.local,
                   REELS_ENGINE_NODE_DIRS="", FAKE_LOG=self.log)
        env.update(extra)
        argv = [sys.executable, self.driver, self.eng, "render", self.comp, "-o", self.out,
                "--force", "--no-safe-zone", "--no-subject"]
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=300, env=env)
        return r.returncode, r.stdout + r.stderr

    def calls(self, sub=None):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            cs = [json.loads(l) for l in fh]
        return [c for c in cs if sub is None or c["sub"] == sub]

    def pivots(self):
        try:
            with open(os.path.join(self.local, "pivots.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def logged(self):
        try:
            with open(os.path.join(self.local, "fallbacks.log"), encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return ""

    def state(self):
        try:
            with open(os.path.join(self.comp, ".reel_render", "state.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}


SAID = "macOS (12.7.6) can't run the graphics renderer"
ROUTE = 'say "keep it raw"'


def test_dyld_render_then_remembered(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="dyld")
    rs = rig.calls("render")
    check("a: exit 4 (nothing could run here)", rc == 4, (rc, said))
    check("a: one render, no low-memory / software retries", len(rs) == 1, rs)
    check("a: says the macOS and the route in plain words", SAID in said and ROUTE in said, said)
    check("a: not the disk-space / reinstall advice", "render failed" not in said and "browser ensure" not in said, said)
    check("a: one line in the log", rig.logged().count("render: ") == 1 and "12.7.6" in rig.logged(), rig.logged())
    pv = rig.pivots().get("render.os-unsupported", {}).get("value")
    check("a: remembered with the macOS version and the pin",
          isinstance(pv, dict) and pv.get("macos") == "12.7.6" and pv.get("hyperframes"), rig.pivots())

    os.remove(rig.log)
    rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="dyld")
    check("b: the next render says it at once", rc == 4 and SAID in said and ROUTE in said, (rc, said))
    check("b: no check and no render were run", rig.calls() == [], rig.calls())
    check("b: says it was learned earlier", "earlier render" in said, said)
    check("b: still remembered", "render.os-unsupported" in rig.pivots(), rig.pivots())

    # c: a macOS update forgets it and the renderer is simply tried again (and works).
    rc, said = rig.render(FAKE_MACOS="13.6.1", FAKE_RENDER="ok")
    check("c: after a macOS update the render runs and finishes", rc == 0 and len(rig.calls("render")) == 1,
          (rc, said, rig.calls()))
    check("c: forgotten", "render.os-unsupported" not in rig.pivots(), rig.pivots())

    # c: a new HyperFrames pin forgets it too, even on the same macOS.
    rig.fresh()
    rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="dyld")
    check("c: remembered again", "render.os-unsupported" in rig.pivots(), rig.pivots())
    rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="ok", FAKE_PIN="9.9.9")
    check("c: a new pin tries the renderer again", rc == 0 and "render.os-unsupported" not in rig.pivots(),
          (rc, said, rig.pivots()))


def test_bare_abort_gets_retries(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="abort")
    rs = rig.calls("render")
    check("d: an abort alone still gets low-memory then software drawing", len(rs) == 3
          and "--low-memory-mode" in rs[1]["args"] and rs[2]["gpu"] == "software", rs)
    check("d: then the same plain line", rc == 4 and SAID in said and ROUTE in said, (rc, said))
    check("d: remembered", "render.os-unsupported" in rig.pivots(), rig.pivots())


def test_check_dies(rig):
    for mode in ("dyld", "dyld-verdict"):
        rig.fresh()
        rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_CHECK=mode)
        check(f"e ({mode}): the plain line, exit 4", rc == 4 and SAID in said and ROUTE in said, (rc, said))
        check(f"e ({mode}): nothing rendered", rig.calls("render") == [], rig.calls())
        check(f"e ({mode}): not called a composition fault",
              "REFUSING" not in said and "could not run on this computer" not in said, said)
        check(f"e ({mode}): the composition is not marked as failed",
              not any(v.get("ok") is False for v in rig.state().values() if isinstance(v, dict)), rig.state())
        check(f"e ({mode}): remembered", "render.os-unsupported" in rig.pivots(), rig.pivots())


def test_usual_path_untouched(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="fail")
    check("f: an ordinary failure on macOS 12 keeps the usual retries and advice",
          rc != 0 and len(rig.calls("render")) == 3 and "render failed" in said and SAID not in said, (rc, said))
    check("f: nothing remembered for it", "render.os-unsupported" not in rig.pivots(), rig.pivots())
    for mac in ("14.5", ""):
        rig.fresh()
        rc, said = rig.render(FAKE_MACOS=mac, FAKE_RENDER="dyld")
        check(f"f ({mac or 'not a Mac'}): the usual path", rc != 0 and len(rig.calls("render")) == 3
              and SAID not in said and "render.os-unsupported" not in rig.pivots(), (rc, said))
    rig.fresh()
    rc, said = rig.render(FAKE_MACOS="14.5", FAKE_CHECK="dyld")
    check("f (14.5): a crashed check is still the checking tool's own message",
          rc == 4 and "could not run on this computer" in said and SAID not in said, (rc, said))


def test_watcher_off(rig):
    rig.fresh()
    rc, said = rig.render(FAKE_MACOS="12.7.6", FAKE_RENDER="dyld", REELS_RENDER_STALL_SECONDS="0")
    check("i: watcher off: the renderer's own words still pass through",
          "[render] launching browser" in said and "Symbol not found" in said, said)
    check("i: watcher off: one render, the same plain line, exit 4",
          rc == 4 and len(rig.calls("render")) == 1 and SAID in said and ROUTE in said, (rc, said, rig.calls()))
    check("i: watcher off: remembered", "render.os-unsupported" in rig.pivots(), rig.pivots())
    rig.fresh()
    rc, said = rig.render(FAKE_MACOS="", FAKE_RENDER="ok", REELS_RENDER_STALL_SECONDS="0")
    check("i: watcher off: a good render still finishes", rc == 0 and os.path.exists(rig.out), (rc, said))


def test_macos_version():
    sys.path.insert(0, PRODUCT)
    import reel_render as rr
    real_platform, real_path, real_mac_ver = sys.platform, os.environ.get("PATH", ""), rr.platform.mac_ver
    with tempfile.TemporaryDirectory() as tmp:
        write(os.path.join(tmp, "sw_vers"), "#!/bin/sh\necho 12.7.6\n", exe=True)
        try:
            sys.platform = "darwin"
            if os.name != "nt":
                os.environ["PATH"] = tmp + os.pathsep + real_path
                check("g: reads sw_vers", rr._macos_version() == "12.7.6", rr._macos_version())
                check("g: 12.7.6 is older than the renderer needs", rr._old_macos() == "12.7.6")
            os.environ["PATH"] = os.path.join(tmp, "nothing-here")   # no sw_vers at all
            rr.platform.mac_ver = lambda: ("11.7.10", ("", "", ""), "")
            check("g: falls back to platform.mac_ver", rr._macos_version() == "11.7.10", rr._macos_version())
            rr.platform.mac_ver = lambda: ("26.1", ("", "", ""), "")
            check("g: a current macOS is not old", rr._old_macos() is None)
            sys.platform = "win32"
            check("g: None off a Mac", rr._macos_version() is None and rr._old_macos() is None)
        finally:
            sys.platform = real_platform
            os.environ["PATH"] = real_path
            rr.platform.mac_ver = real_mac_ver
    check("g: the loader line is certain, a bare abort is not",
          rr._os_crash(1, "dyld[1]: Symbol not found: _x", definite_only=True)
          and not rr._os_crash(134, "", definite_only=True) and rr._os_crash(134, "")
          and rr._os_crash(1, "Error: Failed to launch the browser process!") and not rr._os_crash(1, "Error: oom"))


def test_check_setup():
    cs_path = os.path.join(ROOT, "check-setup.sh")
    with open(cs_path, encoding="utf-8") as fh:
        cs = fh.read()
    check("h: one Graphics renders line in check-setup.sh", cs.count('"Graphics renders"') == 1)
    if sys.platform != "darwin":
        return   # the line itself is Mac-only; the run below needs the Mac's own tools
    for macos, want in (("12.7.6", 1), ("13.0", 0), ("15.5", 0)):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "bin")
            write(os.path.join(fake, "sw_vers"), f"#!/bin/sh\necho {macos}\n", exe=True)
            write(os.path.join(fake, "uname"), "#!/bin/sh\ncase \"$1\" in -m) /usr/bin/uname -m;; "
                  "*) echo Darwin;; esac\n", exe=True)
            os.makedirs(os.path.join(tmp, "home"))
            env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""),
                       HOME=os.path.join(tmp, "home"), REELS_ENGINE_LOCAL=os.path.join(tmp, "local"))
            r = subprocess.run(["bash", cs_path], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=env, cwd=ROOT, timeout=300)
            said = r.stdout + r.stderr
            n = said.count("Graphics renders")
            check(f"h: macOS {macos}: {want} line(s)", n == want, said[-1500:])
            if want:
                check("h: names the macOS and the route", f"macOS {macos}" in said and ROUTE in said, said[-1500:])


def main():
    if os.name == "nt":
        print("test_old_macos_render: the stand-in npx is a POSIX script; the macOS route is Mac-only. "
              "Running the platform-free part only.")
        test_macos_version()
        test_check_setup()
    else:
        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp)
            test_dyld_render_then_remembered(rig)
            test_bare_abort_gets_retries(rig)
            test_check_dies(rig)
            test_usual_path_untouched(rig)
            test_watcher_off(rig)
        test_macos_version()
        test_check_setup()
    if fails:
        print(f"FAIL {len(fails)}/{total}")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"OK {total}/{total}: an old macOS is said plainly with the CapCut route, remembered, and forgotten "
          f"after an update")
    return 0


if __name__ == "__main__":
    sys.exit(main())
