#!/usr/bin/env python3
"""Guard: a hiccup at the update server never reads as "you're up to date".

A buyer said "update me" while a new version was being published. The feed answered "not found" once, so the
updater fell back to an update file an earlier update had left in her folder, the same version she already had,
and reported "You're already up to date" while the server held a much newer one (buyer report, 2026-10-14).

Pinned here, against the real scripts/apply-update.py in a throwaway engine folder (no network: urlopen is a
stand-in):
  1. one failed answer is asked again, and the second answer is used;
  2. when both fail and the only file in her folder is NOT newer, nothing is applied and the message says the
     server didn't answer and that this doesn't mean she's up to date;
  3. when both fail and her folder holds a NEWER update file, that file is still used (offline updates work);
  4. the version of a file in her folder is read from its update.json, then its name.

Run: python3 product/tests/test_update_feed_hiccup.py   (Windows: python)
"""
import contextlib, importlib.util, io, json, os, shutil, sys, tempfile, urllib.error, zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-600:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def engine(tmp, version):
    """A throwaway engine folder at `version` with the real updater, loaded as a module."""
    eng = Path(tmp) / "engine"
    (eng / "scripts").mkdir(parents=True)
    for f in ("apply-update.py", "update_signature.py"):
        shutil.copy(os.path.join(ROOT, "scripts", f), eng / "scripts" / f)
    (eng / "product.json").write_text(json.dumps(
        {"engine": "ai-edit-engine", "version": version, "update_url": "https://feed.invalid/v2"}), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"apply_update_{os.path.basename(tmp)}", eng / "scripts" / "apply-update.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.FEED_RETRY_WAIT = 0
    return eng, mod


def left_behind(eng, version, named=None):
    """An update zip in her folder that installs `version` (its name can disagree, as a renamed file would)."""
    d = eng / "_updates"
    d.mkdir(exist_ok=True)
    z = d / (named or f"ai-edit-engine-update-v{version}.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("update.json", json.dumps({"engine": "ai-edit-engine", "version": version}))
    return z


class Answers:
    """Stand-in urlopen: each call takes the next answer; an exception is raised, a dict is served as JSON."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return contextlib.nullcontext(io.BytesIO(json.dumps(a).encode("utf-8")))


def not_found():
    return urllib.error.HTTPError("https://feed.invalid/v2/latest.json", 404, "Not Found", {}, None)


def run_fetch(mod, answers):
    """(exit code or None, stdout + stderr, what apply() was handed) for one fetch()."""
    handed = []
    mod.urllib.request.urlopen = answers
    mod.apply = lambda pkg, dry_run=False, verified=False: handed.append(str(pkg))
    out, code = io.StringIO(), None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            mod.fetch()
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), handed


def main():
    print("update server hiccup: never a false \"up to date\"\n")

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.2")
        feed = {"engine": "ai-edit-engine", "version": "2.2.2"}
        ans = Answers(not_found(), feed)
        mod.urllib.request.urlopen = ans
        latest, err = mod._read_feed("https://feed.invalid/v2/latest.json")
        check("one not-found is asked again, and the second answer is used",
              err is None and latest == feed and ans.calls == 2, f"calls={ans.calls} err={err}")

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.2")
        left_behind(eng, "2.2.2")
        ans = Answers(not_found(), not_found())
        code, said, handed = run_fetch(mod, ans)
        check("an old file in her folder is NOT re-applied when the server is down", not handed, handed)
        check("the update stops with an error, not a false success", code == 1, f"code={code}")
        check("it says the server didn't answer", "didn't answer" in said, said)
        check("it says plainly that this doesn't mean she's up to date",
              "doesn't mean you're up to date" in said and "already up to date" not in said, said)
        check("it offers the download-and-bring-over route for a network that can't reach the server",
              "bring over my old engine" in said, said)
        check("the server was asked twice", ans.calls == 2, f"calls={ans.calls}")

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.2")
        z = left_behind(eng, "2.2.19")
        code, said, handed = run_fetch(mod, Answers(not_found(), not_found()))
        check("a NEWER file in her folder is still used when the server is down",
              [os.path.realpath(p) for p in handed] == [os.path.realpath(z)], handed)

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.2")
        z = left_behind(eng, "2.2.2", named="ai-edit-engine-update-v9.9.9.zip")
        check("a file's version comes from its update.json, not a misleading name",
              mod._package_version(z) == "2.2.2", mod._package_version(z))
        bare = eng / "_updates" / "ai-edit-engine-update-v2.3.0.zip"
        bare.write_bytes(b"not a zip")
        check("a file that can't be opened falls back to the version in its name",
              mod._package_version(bare) == "2.3.0", mod._package_version(bare))

    print()
    if fails:
        print(f"FAILED: {len(fails)} check(s): {', '.join(fails)}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
