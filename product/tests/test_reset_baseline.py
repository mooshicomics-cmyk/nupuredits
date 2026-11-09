#!/usr/bin/env python3
"""/studio reset brings the built-in packs back to how THIS version shipped them, and keeps hers.

The reset restores from a baseline frozen by `studio_reset.py snapshot`. It was frozen once, at the first
release, and never again, so every later fix to the shipped packs was undone by a reset: the bundled
stand-in fonts vanished from every pack, Editorial's caption went back to an older weight and lost its tuned
shadow, and a retired setting came back. A buyer who reset to "how it shipped" got a version that never had.

  1. the baseline IS the shipped style-packs.json (when it is not, re-freeze it: see the failure message)
  2. a reset of an untouched install changes nothing a build reads
  3. a reset after she changed a built-in pack restores it, keeps a pack she built, and backs up first

Runs the reset in a throwaway copy; the engine's own files are only read.

Run: python3 product/tests/test_reset_baseline.py
"""
import glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
LIVE = os.path.join(PRODUCT, "creative-vault", "style-packs.json")
BASELINE = os.path.join(PRODUCT, "creative-vault", "_launch-baseline", "style-packs.json")
fails = []


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    shipped, base = load(LIVE), load(BASELINE)
    drift = sorted(k for k in set(shipped) | set(base) if shipped.get(k) != base.get(k))
    drift += sorted(f"packs/{p}" for p in set(shipped["packs"]) | set(base.get("packs", {}))
                    if shipped["packs"].get(p) != base.get("packs", {}).get(p))
    check("the /studio reset baseline is the shipped style-packs.json", not drift,
          f"differs at: {', '.join(drift)}. Re-freeze it: python3 product/studio_reset.py snapshot "
          f"(then commit product/creative-vault/_launch-baseline/style-packs.json)")

    tmp = tempfile.mkdtemp()
    try:
        vault = os.path.join(tmp, "product", "creative-vault")
        os.makedirs(os.path.join(vault, "_launch-baseline"))
        shutil.copy2(os.path.join(PRODUCT, "studio_reset.py"), os.path.join(tmp, "product"))
        shutil.copy2(BASELINE, os.path.join(vault, "_launch-baseline", "style-packs.json"))
        live = os.path.join(vault, "style-packs.json")
        run = lambda: subprocess.run([sys.executable, os.path.join(tmp, "product", "studio_reset.py")],
                                     capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})

        shutil.copy2(LIVE, live)
        r = run()
        check("a reset runs", r.returncode == 0, (r.stdout + r.stderr)[-400:])
        check("a reset of an untouched install changes nothing a build reads", load(live) == shipped)

        mine = json.loads(json.dumps(shipped))
        first = next(iter(mine["packs"]))
        mine["packs"][first]["accent_color"] = "#123456"             # she tweaked a built-in pack
        mine["packs"]["Sunday Best"] = dict(mine["packs"][first], in_launch_kit=False)   # and built one
        with open(live, "w", encoding="utf-8") as fh:
            json.dump(mine, fh, indent=1)
        r = run()
        after = load(live)
        check("a reset restores a built-in pack she changed", after["packs"][first] == shipped["packs"][first])
        check("a reset keeps the pack she built", after["packs"].get("Sunday Best") == mine["packs"]["Sunday Best"])
        check("every other built-in pack is exactly as shipped",
              all(after["packs"][p] == shipped["packs"][p] for p in shipped["packs"]))
        backups = glob.glob(os.path.join(vault, "_pre-reset-backup", "*", "style-packs.json"))
        check("the config before the reset is backed up",
              any(load(b) == mine for b in backups), f"{len(backups)} backup(s)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    if fails:
        print(f"reset baseline: FAILED {len(fails)}: {'; '.join(fails)}")
        sys.exit(1)
    print("reset baseline: /studio reset returns the built-in packs to exactly how this version ships them")
