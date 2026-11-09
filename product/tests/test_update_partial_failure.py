#!/usr/bin/env python3
"""An update that fails partway must never leave a half-updated engine.

What used to happen: each file's checksum was checked only as it was written, and product.json (it sorts
before product/) was written near the start. A bad file, a full disk or a read-only folder midway stopped the
update with every file before it already new: the engine read as updated, "update me" answered "already up to
date", and --rollback (which only reads a finished update's applied.json) undid the update BEFORE it instead,
leaving a mix of three versions.

This runs the real scripts/apply-update.py in a throwaway engine and pins:
  1. a bad checksum on a file that sorts after product.json: caught before anything is written
  2. an error midway (a folder the update cannot write into): everything goes back on its own
  3. the process killed partway: product.json is still old, and --rollback undoes exactly this update
  4. the automatic put-back itself failing: the message says so and the rollback command it prints works
  5. a normal update: the record --rollback reads is exactly what it always was

Run: python3 product/tests/test_update_partial_failure.py   (Windows: python)
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENV = {**os.environ, "PYTHONUTF8": "1", "REELS_ENGINE_SKIP_BROWSER_ENSURE": "1"}
fails = []

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-700:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2) + "\n")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tree(root):
    """{path: content hash} of the engine, backups aside."""
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in ("_update-backups", "__pycache__")]
        for fn in files:
            p = os.path.join(d, fn)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = hashlib.sha256(fh.read()).hexdigest()
    return out


def version(root):
    with open(os.path.join(root, "product.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


def backups(root):
    return sorted(os.listdir(os.path.join(root, "_update-backups")))


EARLIER = "v0.9.0-to-v1.0.0-20260101-000000"


def install(root):
    """v1.0.0, installed by an earlier update (v0.9.0 -> v1.0.0) whose backup is still there."""
    os.makedirs(os.path.join(root, "scripts"))
    shutil.copy2(os.path.join(ROOT, "scripts", "apply-update.py"), os.path.join(root, "scripts"))
    write(os.path.join(root, "product.json"), {"engine": "ai-edit-engine", "version": "1.0.0"})
    for rel in ("a.md", "product/x.py", "zz.py", "gone.md"):
        write(os.path.join(root, rel), f"v1.0.0 {rel}\n")
    write(os.path.join(root, "CHANGELOG.md"), "# Changelog\n\n## v1.0.0\n\n- first\n")
    write(os.path.join(root, "zzz"), "an ordinary file where the update needs a folder\n")
    prev = os.path.join(root, "_update-backups", EARLIER)
    write(os.path.join(prev, "overwritten", "a.md"), "v0.9.0 a.md\n")
    write(os.path.join(prev, "applied.json"), {"from": "0.9.0", "to": "1.0.0", "wrote": ["a.md"], "deleted": []})


GOOD = {"CHANGELOG.md": "# Changelog\n\n## v1.0.1\n\n- second\n\n## v1.0.0\n\n- first\n", "a.md": "v1.0.1 a.md\n",
        "product.json": json.dumps({"engine": "ai-edit-engine", "version": "1.0.1"}) + "\n",
        "product/x.py": "v1.0.1 x.py\n", "zz.py": "v1.0.1 zz.py\n", "new/added.py": "v1.0.1 added\n"}


def package(path, files=None, bad=None):
    files = GOOD if files is None else files
    entries = []
    for rel, body in files.items():
        write(os.path.join(path, "files", rel), body)
        entries.append({"path": rel, "sha256": "0" * 64 if rel == bad else sha(body)})
    write(os.path.join(path, "update.json"), {"engine": "ai-edit-engine", "version": "1.0.1", "min_version": "1.0.0",
                                             "summary": "test", "changes": [], "files": entries,
                                             "deletes": ["gone.md"]})
    return path


# Runs the engine's own apply-update.py with shutil.copy2 wrapped: once LIMIT copies into the engine have
# happened (copies into the backup folder do not count), the next one either kills the process on the spot
# (MODE=kill, like a power cut) or fails as a full disk would (MODE=full: that one, and every copy after it,
# so the automatic put-back cannot finish either).
FAULT = r"""
import errno, os, runpy, shutil, sys
limit, mode, real, seen = int(os.environ["LIMIT"]), os.environ["MODE"], shutil.copy2, [0]
def copy2(src, dst, *a, **k):
    if "_update-backups" not in str(dst).replace(os.sep, "/").split("/"):
        seen[0] += 1
        if seen[0] > limit:
            if mode == "kill":
                os._exit(9)
            seen[0] = 10 ** 9
            raise OSError(errno.ENOSPC, "No space left on device", str(dst))
    elif seen[0] >= 10 ** 9:
        raise OSError(errno.ENOSPC, "No space left on device", str(dst))
    return real(src, dst, *a, **k)
shutil.copy2 = copy2
script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
runpy.run_path(script, run_name="__main__")
"""


def run(root, *args, fault=None):
    cmd = [sys.executable, os.path.join(root, "scripts", "apply-update.py"), *args]
    env = dict(ENV)
    if fault:
        runner = os.path.join(os.path.dirname(root), "fault.py")
        write(runner, FAULT)
        cmd = [sys.executable, runner] + cmd[1:]
        env.update(LIMIT=str(fault[0]), MODE=fault[1])
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def no_traceback(out):
    return "Traceback" not in out


def main():
    print("an update that fails partway never leaves a half-updated engine\n")
    with tempfile.TemporaryDirectory() as tmp:
        good = package(os.path.join(tmp, "good"))

        print("1. a file that fails its checksum (it sorts after product.json) is caught before anything moves")
        e = os.path.join(tmp, "e1")
        install(e)
        before = tree(e)
        rc, out = run(e, package(os.path.join(tmp, "p1"), bad="zz.py"))
        check("the update refuses", rc != 0 and "integrity check: zz.py" in out, out)
        check("it says nothing was changed and which version she is on",
              "Nothing was changed" in out and "still on v1.0.0" in out, out)
        check("not one file changed (product.json included)", tree(e) == before,
              sorted(k for k in set(tree(e)) | set(before) if tree(e).get(k) != before.get(k)))
        check("no backup folder is left behind for --rollback to mistake for an update", backups(e) == [EARLIER],
              backups(e))
        check("it never says it is done", "Done." not in out, out)
        rc, out = run(e, good)
        check("the next update is not 'already up to date': it installs", rc == 0 and version(e) == "1.0.1", out)

        print("\n2. an error midway (a folder it cannot create a file in): everything it changed goes back")
        e = os.path.join(tmp, "e2")
        install(e)
        before = tree(e)
        rc, out = run(e, package(os.path.join(tmp, "p2"), dict(GOOD, **{"zzz/new.py": "v1.0.1 new\n"})))
        check("the update reports it did not finish", rc != 0 and "did not finish" in out and "zzz/new.py" in out, out)
        check("in plain words, with no traceback", no_traceback(out) and "back the way it was" in out
              and "still on v1.0.0" in out, out)
        check("the engine is exactly as it was (the files before the failure too)", tree(e) == before,
              sorted(k for k in set(tree(e)) | set(before) if tree(e).get(k) != before.get(k)))
        check("its backup is marked rolled back, so no later undo picks it up",
              [b for b in backups(e) if b != EARLIER and not b.endswith(".rolledback")] == [], backups(e))
        check("it never says it is done", "Done." not in out, out)
        time.sleep(1.1)                                     # backup folders are named to the second
        rc, out = run(e, good)
        check("the next update installs", rc == 0 and version(e) == "1.0.1", out)
        time.sleep(1.1)
        rc, out = run(e, "--rollback")
        check("--rollback undoes THAT update", rc == 0 and version(e) == "1.0.0" and tree(e) == before, out)
        rc, out = run(e, "--rollback")
        check("a second --rollback undoes the one before it, the right folder",
              rc == 0 and "v1.0.0 -> v0.9.0" in out and version(e) == "0.9.0", out)

        if os.name != "nt" and not (hasattr(os, "geteuid") and os.geteuid() == 0):
            e = os.path.join(tmp, "e2b")
            install(e)
            os.makedirs(os.path.join(e, "locked"))
            before = tree(e)
            os.chmod(os.path.join(e, "locked"), 0o555)
            try:
                rc, out = run(e, package(os.path.join(tmp, "p2b"), dict(GOOD, **{"locked/new.py": "v1.0.1 new\n"})))
            finally:
                os.chmod(os.path.join(e, "locked"), 0o755)
            check("a read-only folder midway: reported plainly, everything back, still v1.0.0",
                  rc != 0 and no_traceback(out) and "back the way it was" in out and tree(e) == before, out)

        print("\n3. the process is killed partway (a power cut): --rollback undoes exactly this update")
        e = os.path.join(tmp, "e3")
        install(e)
        before = tree(e)
        rc, out = run(e, good, fault=(3, "kill"))
        check("the run was cut off partway", rc != 0 and tree(e) != before, out)
        check("product.json still says v1.0.0 (it goes last), so the next update is not skipped",
              version(e) == "1.0.0")
        rc, out = run(e, "--rollback")
        check("--rollback runs, without a traceback", rc == 0 and no_traceback(out), out)
        check("...and undoes THIS update, back to exactly what she had", tree(e) == before and version(e) == "1.0.0",
              sorted(k for k in set(tree(e)) | set(before) if tree(e).get(k) != before.get(k)))
        rc, out = run(e, "--rollback")
        check("a second --rollback reaches the update before it, not a wrong folder",
              rc == 0 and "v1.0.0 -> v0.9.0" in out, out)

        print("\n4. the disk fills up partway AND the automatic put-back cannot finish either")
        e = os.path.join(tmp, "e4")
        install(e)
        before = tree(e)
        rc, out = run(e, good, fault=(3, "full"))
        check("the update reports it did not finish, and that putting back did not either",
              rc != 0 and "did not finish" in out and "did not finish either" in out and no_traceback(out), out)
        check("it names where the saved files are and the exact command that puts everything back",
              "_update-backups" in out and "scripts/apply-update.py --rollback" in out, out)
        check("it never says it is done", "Done." not in out, out)
        check("product.json was never touched (it goes last)", version(e) == "1.0.0")
        rc, out = run(e, "--rollback")
        check("the printed command works: back to exactly what she had",
              rc == 0 and tree(e) == before and version(e) == "1.0.0", out + str(
                  sorted(k for k in set(tree(e)) | set(before) if tree(e).get(k) != before.get(k))))

        print("\n5. a normal update: same result and same record as always")
        e = os.path.join(tmp, "e5")
        install(e)
        rc, out = run(e, good)
        check("it installs and says so", rc == 0 and "Done. You're now on v1.0.1." in out and version(e) == "1.0.1", out)
        done = [b for b in backups(e) if b != EARLIER]
        rec = {}
        if len(done) == 1:
            with open(os.path.join(e, "_update-backups", done[0], "applied.json"), encoding="utf-8") as fh:
                rec = json.load(fh)
        check("applied.json: what it wrote (in the package's order) and removed, nothing else",
              rec == {"from": "1.0.0", "to": "1.0.1", "wrote": list(GOOD), "deleted": ["gone.md"]}, rec)
        check("no half-written record left beside it",
              len(done) == 1 and not os.path.exists(os.path.join(e, "_update-backups", done[0], "applied.json.part")))
        check("every file arrived, and the retired one is gone",
              all(open(os.path.join(e, r), encoding="utf-8").read() == b for r, b in GOOD.items() if r != "product.json")
              and not os.path.exists(os.path.join(e, "gone.md")))

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed: a failed update never leaves a half-updated engine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
