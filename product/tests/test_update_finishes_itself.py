#!/usr/bin/env python3
"""Guard: saying "/update" alone gets a buyer the WHOLE update, whichever updater version she has.

Three failures this pins, each measured on a real v1.0.64 -> v1.0.66 update:
  1. The updater read product.json BEFORE installing and wrote that stale copy back, erasing every new
     setting the release shipped (the HyperFrames pin). The current updater re-reads it after installing.
  2. An updater from v1.0.64 or earlier cannot be fixed on her machine and never runs the finishing step.
     post-update.py restores missing settings from the shipped copy (product/templates/product.engine.json).
  3. Nobody may remember to run that step. The session-start hook ships inside the update, notices an
     unfinished one (no _local/post-update-<version>.ok), makes scripts runnable on the spot and tells Claude
     to finish it; once post-update.py has run, the hook goes quiet.

Run: python3 product/tests/test_update_finishes_itself.py
"""
import json, os, shutil, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-400:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def write(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2) + "\n" if not isinstance(data, str) else data)


def read_json(p):
    return json.load(open(p, encoding="utf-8"))


ENV = {**os.environ, "PYTHONUTF8": "1", "REELS_ENGINE_SKIP_BROWSER_ENSURE": "1"}


def main():
    print("an update finishes itself\n")
    with tempfile.TemporaryDirectory() as tmp:
        buyer, pkg = os.path.join(tmp, "engine"), os.path.join(tmp, "pkg")
        os.makedirs(os.path.join(buyer, "scripts"))
        for s in ("apply-update.py", "post-update.py", "merge-claude-md.py"):
            shutil.copy2(os.path.join(ROOT, "scripts", s), os.path.join(buyer, "scripts"))
        write(os.path.join(buyer, "product.json"),
              {"engine": "ai-edit-engine", "version": "1.0.64", "update_url": "https://example.invalid"})

        # the release: a product.json with a NEW setting, and its shipped copy
        files = os.path.join(pkg, "files")
        new_prod = {"engine": "ai-edit-engine", "version": "1.0.99", "hyperframes": "9.9.9",
                    "update_url": "https://example.invalid"}
        write(os.path.join(files, "product.json"), new_prod)
        write(os.path.join(files, "product", "templates", "product.engine.json"), new_prod)
        write(os.path.join(pkg, "update.json"), {
            "engine": "ai-edit-engine", "version": "1.0.99", "min_version": "1.0.0", "summary": "test",
            "changes": [], "files": ["product.json", "product/templates/product.engine.json"], "deletes": []})

        print("1. the current updater keeps new settings a release ships")
        r = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "apply-update.py"), pkg],
                           capture_output=True, text=True, cwd=buyer, env=ENV)
        prod = read_json(os.path.join(buyer, "product.json"))
        check("the update ran", r.returncode == 0, r.stdout + r.stderr)
        check("version moved to the release", prod.get("version") == "1.0.99", prod)
        check("the new setting survived the version bump", prod.get("hyperframes") == "9.9.9", prod)
        check("the finishing step ran and recorded itself",
              os.path.exists(os.path.join(buyer, "_local", "post-update-1.0.99.ok")))

        print("\n2. after an OLD updater erased the setting, the finishing step restores it")
        write(os.path.join(buyer, "product.json"),
              {"engine": "ai-edit-engine", "version": "1.0.99", "update_url": "https://example.invalid"})
        os.remove(os.path.join(buyer, "_local", "post-update-1.0.99.ok"))
        sys.path.insert(0, os.path.join(ROOT, "product"))
        r = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "post-update.py")],
                           capture_output=True, text=True, cwd=buyer, env=ENV)
        prod = read_json(os.path.join(buyer, "product.json"))
        check("post-update restores the missing setting from the shipped copy", prod.get("hyperframes") == "9.9.9",
              r.stdout + r.stderr)
        check("it never changes her version", prod.get("version") == "1.0.99", prod)

        print("\n3. the session-start hook finishes an update nobody finished")
        os.makedirs(os.path.join(buyer, ".claude", "hooks"))
        shutil.copy2(os.path.join(ROOT, ".claude", "hooks", "onboarding-nudge.sh"), os.path.join(buyer, ".claude", "hooks"))
        os.makedirs(os.path.join(buyer, "_update-backups", "v1.0.64-to-v1.0.99"))
        write(os.path.join(buyer, "brand-kit.md"), "# filled in\n")
        sh = os.path.join(buyer, "scripts", "name-final.sh")
        write(sh, "#!/usr/bin/env bash\necho ok\n")
        os.chmod(sh, 0o644)                                   # what an older updater left behind
        os.remove(os.path.join(buyer, "_local", "post-update-1.0.99.ok"))
        h = subprocess.run(["bash", ".claude/hooks/onboarding-nudge.sh"], capture_output=True, text=True, cwd=buyer,
                           env={**ENV, "PATH": os.environ.get("PATH", "")})
        out = h.stdout.strip()
        ok_json = True
        try:
            ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
        except Exception:
            ok_json, ctx = False, ""
        check("hook output is valid JSON", ok_json, out[:300])
        check("hook tells Claude to finish the update first", "post-update.py" in ctx and "1.0.99" in ctx, ctx[:300])
        if os.name != "nt":
            check("hook makes the dropped script runnable again, instantly", os.stat(sh).st_mode & stat.S_IXUSR)
        subprocess.run([sys.executable, os.path.join(buyer, "scripts", "post-update.py")],
                       capture_output=True, text=True, cwd=buyer, env=ENV)
        h2 = subprocess.run(["bash", ".claude/hooks/onboarding-nudge.sh"], capture_output=True, text=True, cwd=buyer,
                            env={**ENV, "PATH": os.environ.get("PATH", "")})
        check("once finished, the hook goes quiet about it", "post-update.py" not in h2.stdout, h2.stdout[:300])

        print("\n4. an engine that updated in from before the visual editor is told it's there, once she hasn't met it")
        for m in ("early_access.py", "learned.py"):
            shutil.copy2(os.path.join(ROOT, "product", m), os.path.join(buyer, "product", m))
        pu = lambda: subprocess.run([sys.executable, os.path.join(buyer, "scripts", "post-update.py")],
                                    capture_output=True, text=True, cwd=buyer, env=ENV).stdout
        out = pu()
        check("never met: the update names the visual editor and both phrases that open it",
              "the visual editor" in out and "open my visual editor" in out and "show me the visual editor" in out, out[-600:])
        check("never met: it says to start a new chat (this one started on the older instructions)", "new chat" in out, out[-600:])
        write(os.path.join(buyer, "projects", "her-reel", "review", "route.json"), {"route": "editor"})
        check("a reel opened in the editor: quiet", "open my visual editor" not in pu())
        shutil.rmtree(os.path.join(buyer, "projects"))
        write(os.path.join(buyer, "_local", "first-use.json"), {"visual-editor": "2026-10-20"})
        check("she answered the editor-or-widget question: quiet", "open my visual editor" not in pu())

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
