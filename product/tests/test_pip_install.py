#!/usr/bin/env python3
"""scripts/pip-install.py retries with --break-system-packages ONLY after pip's externally-managed refusal.

Pins the one property that makes it safe on every pip version: an older pip that does not know the flag
must never be handed it, and a newer pip that refuses must be retried with it. Uses a fake runner, so no
package is actually installed and no network is needed.
"""
import importlib.util
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location("pip_install", os.path.join(ROOT, "scripts", "pip-install.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


def fake(results):
    calls = []

    def run(cmd, **_):
        calls.append(cmd)
        rc, out, err = results[len(calls) - 1]
        return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)
    return run, calls


REFUSED = (1, "", "error: externally-managed-environment\nThis Python installation is managed by uv")

# 1. an ordinary Python: one plain install, the flag never appears
run, calls = fake([(0, "Successfully installed pillow", "")])
check("a normal install succeeds first time", mod.install(["pillow"], run=run) == 0)
check("...and is never given --break-system-packages",
      len(calls) == 1 and "--break-system-packages" not in calls[0])

# 2. a uv-managed Python: refused, then retried WITH the flag, and that retry succeeds
run, calls = fake([REFUSED, (0, "Successfully installed pillow", "")])
check("a uv-managed Python ends up installed", mod.install(["pillow"], run=run) == 0)
check("...by retrying with --break-system-packages", len(calls) == 2 and "--break-system-packages" in calls[1])

# 3. an OLDER pip failing for some other reason: never handed a flag it would reject
run, calls = fake([(1, "", "ERROR: Could not find a version that satisfies the requirement pilow")])
check("an unrelated failure is reported as-is", mod.install(["pilow"], run=run) == 1)
check("...with no retry, so an old pip never sees an unknown flag", len(calls) == 1)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "pip-install retries only when it is safe to"))
sys.exit(1 if fails else 0)
