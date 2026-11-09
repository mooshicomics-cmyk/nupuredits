#!/usr/bin/env python3
"""The problem report carries the fixes a buyer's Claude made to the engine on her machine.

    python3 product/tests/test_report_engine_changes.py

A fake buyer engine in a temp folder: one shipped builder her Claude patched, one file it added, her brand kit
and a project of hers. With the originals an update brings, the report shows the patched builder's exact change,
names the added file without its contents, and never mentions her brand kit or project. Installed from the zip
(no originals yet), it names the files edited since the install instead.
"""
import hashlib, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
import keep_changes as kc   # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name)
    if not cond:
        fails.append(name)
        if detail:
            print("      " + str(detail)[:600].replace("\n", "\n      "))


def write(root, rel, data):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(data)
    return p


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


SHIPPED = {"product.json": '{"version": "1.0.0"}\n',
           "product/builder.py": "import sys\nx = f\"{'a' if 1 else \"b\"}\"\nprint(x)\n",
           "product/other.py": "print('untouched')\n"}


JOB = "my-reel"   # a project of hers, which the report must never mention


def buyer(tmp, with_originals):
    root = os.path.join(tmp, "engine")
    for rel, data in SHIPPED.items():
        write(root, rel, data)
    shutil.copy(os.path.join(ROOT, "product", "keep_changes.py"), os.path.join(root, "product", "keep_changes.py"))
    if with_originals:
        kc.build_store(os.path.join(root, *kc.STORE_REL.split("/")),
                       {"1.0.0": {r: sha(d) for r, d in SHIPPED.items()}},
                       [(sha(d), r, d.encode("utf-8")) for r, d in SHIPPED.items()])
    old = time.time() - 3600
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            os.utime(os.path.join(dirpath, f), (old, old))
    # what her Claude did, and her own things
    write(root, "product/builder.py", "import sys\nq = 'a' if 1 else 'b'\nx = f\"{q}\"\nprint(x)\n")
    write(root, "product/helper_fix.py", "SECRET_LOOKING = 'her own helper'\n")
    write(root, "brand-kit.md", "my private brand kit\n")
    write(root, f"projects/{JOB}/notes.md", "private reel notes\n")
    return root


def run(root):
    r = subprocess.run([sys.executable, os.path.join(root, "product", "keep_changes.py"), "--report"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root)
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="report-changes-")
    try:
        print("a buyer who has taken an update (originals on her machine)")
        rc, out = run(buyer(os.path.join(tmp, "a"), True))
        check("it runs", rc == 0, out)
        check("it has the section heading", "### Changes made to this engine" in out, out)
        check("the patched builder is listed", "`product/builder.py`" in out, out)
        check("its exact change is shown", "+q = 'a' if 1 else 'b'" in out and "```diff" in out, out)
        check("the untouched file is not listed", "product/other.py" not in out, out)
        check("the added file is named", "`product/helper_fix.py`" in out, out)
        check("the added file's contents are never shown", "her own helper" not in out, out)
        check("her brand kit and projects never appear",
              "brand" not in out.lower() and JOB not in out and "private" not in out, out)

        print("\na buyer installed from the zip, never updated (no originals yet)")
        rc, out = run(buyer(os.path.join(tmp, "b"), False))
        check("it runs", rc == 0, out)
        check("it says why changes are named, not shown", "no shipped originals" in out, out)
        check("the patched builder is named", "`product/builder.py`" in out, out)
        check("the untouched file is not named", "product/other.py" not in out, out)
        check("her brand kit and projects never appear", "brand-kit" not in out and JOB not in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"\nFAILED: {len(fails)}")
        return 1
    print("\nall report-engine-changes checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
