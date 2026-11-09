#!/usr/bin/env python3
"""/studio reset — snapshot the launch baseline, and restore to it.

  python product/studio_reset.py snapshot   # run at EVERY release, before staging: freeze the shipped config as the baseline
  python product/studio_reset.py            # restore the built-in defaults to the launch baseline

Restore preserves the buyer's OWN work: any custom style pack they built (a pack not in the baseline) is kept,
and the current config is backed up first, so nothing is ever truly lost. Their brand-kit / wordlist are never
touched — reset only returns the built-in packs + engine design settings to how they shipped.
"""
import json, os, shutil, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = f"{ROOT}/product/creative-vault/_launch-baseline"
BACKUP = f"{ROOT}/product/creative-vault/_pre-reset-backup"
# tunable design config a buyer might change and want to revert (extend as needed)
FILES = ["product/creative-vault/style-packs.json"]


def snapshot():
    os.makedirs(BASE, exist_ok=True)
    for rel in FILES:
        src = f"{ROOT}/{rel}"
        if os.path.exists(src):
            shutil.copy2(src, f"{BASE}/{os.path.basename(rel)}")
    print(f"launch baseline frozen -> {BASE}  ({len(FILES)} file(s))")


def restore():
    if not os.path.isdir(BASE):
        sys.exit("no launch baseline found — run `python product/studio_reset.py snapshot` first (at ship).")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = f"{BACKUP}/{stamp}"; os.makedirs(bdir, exist_ok=True)
    for rel in FILES:
        cur = f"{ROOT}/{rel}"; basefile = f"{BASE}/{os.path.basename(rel)}"
        if not os.path.exists(basefile):
            continue
        if os.path.exists(cur):
            shutil.copy2(cur, f"{bdir}/{os.path.basename(rel)}")   # back up current first
        if rel.endswith("style-packs.json") and os.path.exists(cur):
            base = json.load(open(basefile, encoding="utf-8")); curj = json.load(open(cur, encoding="utf-8"))
            kept = [n for n in curj.get("packs", {}) if n not in base.get("packs", {})]
            for n in kept:                                          # preserve the buyer's OWN custom packs
                base["packs"][n] = curj["packs"][n]
            json.dump(base, open(cur, "w", encoding="utf-8"), indent=2)
            print(f"reset {rel} to launch baseline"
                  + (f" (kept your custom pack(s): {', '.join(kept)})" if kept else ""))
        else:
            shutil.copy2(basefile, cur)
            print(f"reset {rel} to launch baseline")
    print(f"(previous config backed up to {bdir})")


if __name__ == "__main__":
    # no argument = restore (documented); "snapshot" = freeze the baseline; ANYTHING else used to fall through to
    # restore and rewrite style-packs.json on a typo — refuse instead.
    _cmd = sys.argv[1] if len(sys.argv) > 1 else "restore"
    if _cmd not in ("snapshot", "restore"):
        sys.exit(f"studio_reset: unknown argument {_cmd!r}. Use no argument (or 'restore') to reset built-in "
                 f"defaults to the launch baseline, or 'snapshot' (ship-time only) to freeze the current config.")
    (snapshot if _cmd == "snapshot" else restore)()
