#!/usr/bin/env python3
"""The chime, teach my style and trial reels are on for every buyer since launch, with or without an old codeword.

They were an early-access test until launch. Each must work in an engine that never took a codeword AND
in one that still has the closed test's codeword saved:
  * chime.sh plays (it stamps _local/.chime-last only when it would play);
  * teach_style.py offer brings her notes back;
  * trial_reels.py answers instead of saying it's early access.

Each case runs in a throwaway engine skeleton; this engine's own _local/ is never read.

Run: python3 product/tests/test_launch_features.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond or not detail else f"\n       {detail}"))
    if not cond:
        fails.append(name)


def skeleton(codeword):
    root = tempfile.mkdtemp(prefix="early-")
    os.makedirs(os.path.join(root, ".claude", "hooks"))
    os.makedirs(os.path.join(root, "product"))
    os.makedirs(os.path.join(root, "_local"))
    shutil.copy(os.path.join(ROOT, ".claude", "hooks", "chime.sh"), os.path.join(root, ".claude", "hooks", "chime.sh"))
    for f in ("early_access.py", "teach_style.py", "learned.py", "trial_reels.py", "review_route.py"):
        shutil.copy(os.path.join(PRODUCT, f), os.path.join(root, "product", f))
    if codeword:                                            # the closed test's saved feed folder
        json.dump({"channel": "early/297e98b57d9625ff073c4e7bd33aa808"}, open(os.path.join(root, "_local", "update-code.json"), "w", encoding="utf-8"))
    os.makedirs(os.path.join(root, "projects", "a-reel", "review"))
    json.dump({"notes": [{"said": "captions higher", "from": "chat note"}]},
              open(os.path.join(root, "projects", "a-reel", "review", "notes-log.json"), "w", encoding="utf-8"))
    return root


def chime_stamped(root):
    env = {k: v for k, v in os.environ.items() if k != "REE_EDITOR"}
    subprocess.run(["bash", os.path.join(root, ".claude", "hooks", "chime.sh")], env=env, capture_output=True)
    return os.path.exists(os.path.join(root, "_local", ".chime-last"))   # it stamps only when it would play


def run(root, *args):
    env = {k: v for k, v in os.environ.items() if k != "REE_EDITOR"}
    p = subprocess.run([sys.executable, *args], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout


def main():
    for codeword in (False, True):
        root = skeleton(codeword)
        try:
            label = "with the old codeword" if codeword else "without a codeword"
            check(f"the chime plays {label}", chime_stamped(root))
            code, out = run(root, "product/teach_style.py", "offer", "a-reel")
            check(f"teach my style offers {label}", code == 0 and "captions higher" in out, out)
            code, out = run(root, "product/trial_reels.py", "status", "a-reel")
            check(f"trial reels never say early access {label}", "early access" not in out.lower(), out)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print("\nPASS" if not fails else f"\nFAIL ({len(fails)}): {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
