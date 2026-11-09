#!/usr/bin/env python3
"""With Node missing, the pre-render gate says so, instead of blaming the composition or crashing.

On Windows the check runs as `cmd /c npx ...`. `cmd` always exists, so a missing npx never raised: it came back
as an ordinary exit 1 and the gate told her to "fix the composition". On a Mac the same case was a traceback.
The gate now asks for npx first (npx.cmd on Windows, which is what `cmd /c npx` runs) and says plainly that
Node is missing or the terminal needs reopening, with exit 4, the code reel_render.py uses for it.

Run: python3 product/tests/test_reel_gate_no_node.py
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import npx_run

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def main():
    tmp = tempfile.mkdtemp(prefix="reel-gate-no-node-")
    try:
        comp = os.path.join(tmp, "comp")
        os.makedirs(comp)
        with open(os.path.join(comp, "index.html"), "w", encoding="utf-8") as fh:
            fh.write("<!doctype html><html><body></body></html>")
        empty = os.path.join(tmp, "empty-path")
        os.makedirs(empty)
        env = {k: v for k, v in os.environ.items() if k != "PATH"}
        env["PATH"] = empty                                     # nothing on PATH: no npx, no node
        env["REELS_ENGINE_NODE_DIRS"] = ""                       # and none in the usual install folders either
        env["REELS_ENGINE_LOCAL"] = os.path.join(tmp, "_local")   # never the real _local/ records
        r = subprocess.run([sys.executable, os.path.join(PRODUCT, "reel_gate.py"), comp, "--canvas", "1080x1920"],
                           capture_output=True, text=True, env=env, timeout=120)
        said = r.stdout + r.stderr
        check("exit 4 (could not run the check), not a composition failure", r.returncode == 4, (r.returncode, said[-300:]))
        check("it says Node is missing", "Node is not installed" in said, said[-300:])
        check("it does not blame the composition", "Fix the composition" not in said and "fix them before rendering" not in said)
        check("no traceback", "Traceback" not in said, said[-300:])

        # Windows: `cmd /c npx` runs npx.cmd, so that is the name that has to be found.
        asked = []
        os.environ["REELS_ENGINE_NODE_DIRS"] = ""                # PATH only: the install-folder search has its own test
        os.environ["REELS_ENGINE_LOCAL"] = os.path.join(tmp, "_local")
        real_which, real_name = shutil.which, os.name
        shutil.which = lambda name, *a, **k: asked.append(name) or None
        try:
            os.name = "nt"
            got = npx_run.npx_path()
        finally:
            os.name = real_name
            shutil.which = real_which
        check("on Windows it looks for npx.cmd", asked == ["npx.cmd"] and got is None, asked)
        check("here it finds npx when Node is installed", (npx_run.npx_path() is not None) == (shutil.which("npx") is not None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_reel_gate_no_node: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_reel_gate_no_node: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
