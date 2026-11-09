#!/usr/bin/env python3
"""The engine's own permission rules are the engine's; her permission mode and her own rules are hers.

.claude/settings.json holds both. An update saves her part and lays it over the freshly shipped file
(product/settings_persist.py). The engine now ships a rule of its own there (a deny that keeps the Claude app's
own setup skill from answering "set me up"), inside the same "permissions" block as her permission mode. Judged
by key, that rule read as hers, so every update would carry it forward and no later version could ever drop it.

Run: python3 product/tests/test_settings_engine_rules.py   (Windows: python)
"""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


spec = importlib.util.spec_from_file_location("settings_persist", os.path.join(ROOT, "product", "settings_persist.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
ENGINE_RULE = "Skill(anthropic-skills:setup-claude)"
HER_RULE = "Bash(rm -rf:*)"
HOOKS = {"SessionStart": [{"hooks": [{"type": "command", "command": "bash .claude/hooks/x.sh"}]}]}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


with tempfile.TemporaryDirectory() as tmp:
    sp.ROOT, sp.SIDECAR = tmp, os.path.join(tmp, "_local", "kept-settings.json")
    settings = os.path.join(tmp, ".claude", "settings.json")

    print("1. saving her settings before an update")
    write(settings, {"permissions": {"deny": [ENGINE_RULE, HER_RULE], "defaultMode": "bypassPermissions"},
                     "hooks": HOOKS})
    sp.harvest()
    kept = (sp.load().get("claude_settings") or {})
    check("her permission mode is saved", kept.get("permissions", {}).get("defaultMode") == "bypassPermissions", kept)
    check("her own rule is saved", HER_RULE in kept.get("permissions", {}).get("deny", []), kept)
    check("the engine's own rule is NOT saved as hers", ENGINE_RULE not in json.dumps(kept), kept)

    print("\n2. a later version that no longer ships the rule")
    write(settings, {"hooks": HOOKS})
    sp.restore()
    now = read(settings)
    check("her permission mode is back", now.get("permissions", {}).get("defaultMode") == "bypassPermissions", now)
    check("her own rule is back", HER_RULE in now.get("permissions", {}).get("deny", []), now)
    check("the engine's old rule does not come back", ENGINE_RULE not in json.dumps(now), now)

    print("\n3. a version that ships it: both rules stand, nothing doubled")
    write(settings, {"permissions": {"deny": [ENGINE_RULE]}, "hooks": HOOKS})
    sp.restore()
    now = read(settings)
    deny = now.get("permissions", {}).get("deny", [])
    check("the engine's rule and hers are both there, once each", deny.count(ENGINE_RULE) == 1 and deny.count(HER_RULE) == 1, deny)

    print("\n4. a record saved before the rule was known as the engine's")
    write(sp.SIDECAR, {"claude_settings": {"permissions": {"deny": [ENGINE_RULE], "defaultMode": "plan"}}})
    write(settings, {"hooks": HOOKS})
    sp.restore()
    now = read(settings)
    check("the old record puts back her mode, not the engine's rule",
          now.get("permissions", {}).get("defaultMode") == "plan" and ENGINE_RULE not in json.dumps(now), now)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "the engine's rules stay the engine's, and hers stay hers"))
sys.exit(1 if fails else 0)
