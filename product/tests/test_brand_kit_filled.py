#!/usr/bin/env python3
"""A brand kit with every field filled in reads as filled in, everywhere the engine asks.

The 2.2.0-2.2.2 kit's how-to line shows a field as `{{this}}`. Counted as a blank field, it kept a filled-in kit
"fresh" for good: the session hook nudged setup every time, and bring-over would swap her old kit in over the
filled one. A buyer's brand-kit.md is never touched by an update, so that line stays in every kit of that age:
the readers must not count it. Checked here:

  fresh      the shipped template reads as not filled in (hook nudges, bring-over brings hers, bridge says fresh)
  filled     the same template with every field filled reads as filled in
  older      a filled kit of the 2.2.0-2.2.2 shape, how-to line and all, reads as filled in
  oldest     a kit still holding an older copy's <<...>> blank reads as not filled in

Run: python3 product/tests/test_brand_kit_filled.py
"""
import importlib.util, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:200]) if detail else ''}")


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def filled(text):
    return re.sub(r"\{\{[^}]*\}\}", "filled in", text)


def hook_nudges(folder, kit):
    with open(os.path.join(folder, "brand-kit.md"), "w", encoding="utf-8") as fh:
        fh.write(kit)
    r = subprocess.run(["bash", os.path.join(ROOT, ".claude", "hooks", "onboarding-nudge.sh")], cwd=folder,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "HOME": folder})
    return "blank fields" in (r.stdout + r.stderr)


def main():
    template = open(os.path.join(ROOT, "ship-templates", "brand-kit.md"), encoding="utf-8").read()
    older = filled(template).replace("Replace every field in double curly\nbraces with your own words,",
                                     "Replace every field shaped like\n`{{this}}` with your own words,")
    check("the older how-to line is reproduced", "`{{this}}`" in older, older[:300])
    kits = {"fresh": (template, True), "filled": (filled(template), False), "older": (older, False),
            "oldest": (filled(template) + "\n- Name: `<<YOUR_NAME>>`\n", True)}

    bring = load("bring_over_under_test", os.path.join("scripts", "bring-over.py"))
    bridge = load("bridge_under_test", os.path.join("dev-tools", "v1-bridge", "payload", "scripts",
                                                     "move-to-new-engine.py"))
    tmp = tempfile.mkdtemp(prefix="brand-kit-filled-")
    try:
        for label, (kit, blank) in kits.items():
            folder = os.path.join(tmp, label)
            os.makedirs(folder)
            check(f"{label}: bring-over reads it as {'blank' if blank else 'filled in'}",
                  bring.has_blank_fields(kit.encode("utf-8")) == blank)
            check(f"{label}: the hook {'nudges setup' if blank else 'stays quiet'}", hook_nudges(folder, kit) == blank)
            check(f"{label}: the bridge reads it as {'fresh' if blank else 'set up'}", bridge.is_set_up(folder) != blank)
            n = subprocess.run(f"grep -e '{{{{' -e '<<' brand-kit.md | grep -v -c -F '{{{{this}}}}'", shell=True,
                               cwd=folder, capture_output=True, text=True).stdout.strip()
            check(f"{label}: the CLAUDE.md count is {'above 0' if blank else '0'}", (int(n or 0) > 0) == blank, n)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_brand_kit_filled: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_brand_kit_filled: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
