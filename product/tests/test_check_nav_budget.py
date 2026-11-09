#!/usr/bin/env python3
"""test_check_nav_budget.py — the pre-render check gets page-load headroom on slow machines.

HyperFrames' `check` gives its browser page max(10 s, --timeout) to load. On a machine that is not Apple
Silicon the engine passes --timeout=10000, so the budget was exactly its floor with no headroom, and a loaded
8 GB Intel Mac refused a clean composition because the check's own page could not finish loading in time.
The gate also reported that as "check found issues ... Fix the composition", which it was not.

Now: npx_run.hf_check_env() raises the page-load budget (PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS) for the check
only, scaled to the machine, and a navigation timeout is said as the machine running out of time, exit 4,
never as a finding about the composition.

Run:  python3 product/tests/test_check_nav_budget.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import npx_run   # noqa: E402

fails, total = [], 0
_SCRATCH_LOCAL = tempfile.mkdtemp(prefix="check-nav-local-")

# Stands in for `npx hyperframes check`: says which page-load budget it was given, then either times out
# loading the page (the slow-machine case) or passes.
FAKE_NPX = r'''#!{py}
import os, sys
print("nav budget:", os.environ.get("PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS", "unset"))
if os.environ.get("FAKE_NAV_TIMEOUT"):
    print("Error: Navigation timeout of 10000 ms exceeded")
    sys.exit(1)
print("◇  Check failed")                     # HyperFrames' own verdict on a composition that failed
sys.exit(1)
'''


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-300:]) if detail else ''}")


def budget(fast, ram, env=None):
    saved = (npx_run._fast_machine, npx_run._ram_gb, dict(os.environ))
    try:
        npx_run._fast_machine = lambda: fast
        npx_run._ram_gb = lambda: ram
        for k in ("REELS_ENGINE_HF_NAV_TIMEOUT_MS", "PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS"):
            os.environ.pop(k, None)
        os.environ["REELS_ENGINE_LOCAL"] = _SCRATCH_LOCAL   # a budget this machine remembered is not the guess
        os.environ.update(env or {})
        return npx_run.hf_check_env().get("PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS")
    finally:
        npx_run._fast_machine, npx_run._ram_gb = saved[0], saved[1]
        os.environ.clear(); os.environ.update(saved[2])


def main():
    check("Apple Silicon keeps HyperFrames' own page-load default", budget(True, 16) is None)
    check("an 8 GB Intel Mac gets 60 s", budget(False, 8.0) == "60000", budget(False, 8.0))
    check("a 16 GB Intel Mac or PC gets 45 s", budget(False, 16.0) == "45000", budget(False, 16.0))
    check("unreadable memory still gets headroom", budget(False, None) == "45000")
    check("a budget she already set wins",
          budget(False, 8.0, {"PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS": "90000"}) == "90000")
    check("the engine override wins over the machine guess",
          budget(True, 16, {"REELS_ENGINE_HF_NAV_TIMEOUT_MS": "120000"}) == "120000")
    check("the budget never goes below HyperFrames' 10 s floor on a slow machine",
          int(budget(False, 4.0)) > 10000)
    check("the memory reading works on this machine", npx_run._ram_gb() is None or npx_run._ram_gb() > 0.5)

    if os.name == "nt":
        print("test_check_nav_budget: render-gate part skipped on Windows (POSIX npx stand-in)")
    else:
        tmp = tempfile.mkdtemp(prefix="check-nav-")
        try:
            eng = os.path.join(tmp, "engine", "product")
            os.makedirs(eng)
            for f in os.listdir(PRODUCT):
                if f.endswith(".py"):
                    shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, f))
            comp = os.path.join(tmp, "comp")
            os.makedirs(comp)
            with open(os.path.join(comp, "index.html"), "w", encoding="utf-8") as fh:
                fh.write('<!doctype html><html><body><div id="root" data-composition-id="reel" data-start="0" '
                         'data-duration="1" data-width="1080" data-height="1920"></div></body></html>')
            npxbin = os.path.join(tmp, "npxbin")
            os.makedirs(npxbin)
            with open(os.path.join(npxbin, "npx"), "w", encoding="utf-8") as fh:
                fh.write(FAKE_NPX.format(py=sys.executable))
            os.chmod(os.path.join(npxbin, "npx"), 0o755)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("PRODUCER_PAGE_NAVIGATION_TIMEOUT_MS", "REELS_ENGINE_HF_NAV_TIMEOUT_MS")}
            env.update(PATH=npxbin + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                       REELS_RENDER_STALL_SECONDS="0", REELS_ENGINE_HF_NAV_TIMEOUT_MS="45000")
            argv = [sys.executable, os.path.join(eng, "reel_render.py"), "render", comp, "-o",
                    os.path.join(tmp, "out.mov")]
            r = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=dict(env, FAKE_NAV_TIMEOUT="1"))
            said = r.stdout + r.stderr
            check("the check runs with the raised page-load budget", "nav budget: 45000" in said, said)
            check("a page that could not load in time: exit 4, the could-not-run code", r.returncode == 4,
                  (r.returncode, said))
            check("it says the check could not start in time", "could not start in time" in said, said)
            check("it does not blame the composition", "Fix the composition" not in said, said)
            r = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=env)
            said = r.stdout + r.stderr
            check("a check that fails for another reason is still refused as before",
                  r.returncode == 1 and "Fix the composition" in said, (r.returncode, said))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_check_nav_budget: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_check_nav_budget: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
