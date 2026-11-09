#!/usr/bin/env python3
"""Guard: the update nudge fires only when the feed is NEWER than this copy, never when it is merely different.

The SessionStart hook `.claude/hooks/update-check.sh` compares the installed product.json version with the
update feed's. It used to treat ANY difference as "newer", so a copy that was ahead of the feed (a build
carrying a fix the feed had not published yet) was told to /update to an older version. Versions are now
compared number by number: 1.0.100 is newer than 1.0.99, a missing part counts as 0, and 08 is eight.

Each case runs the real hook in a throwaway engine folder with a stand-in curl, so nothing touches the
network or the real ~/.cache.

Run: python3 product/tests/test_update_check_version.py
"""
import json, os, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HOOK = os.path.join(ROOT, ".claude", "hooks", "update-check.sh")
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-300:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def nudge(installed, feed):
    """(the hook's stdout, exit code) for a copy at `installed` whose feed says `feed`."""
    with tempfile.TemporaryDirectory() as tmp:
        eng, stub, cache = (os.path.join(tmp, d) for d in ("engine", "stub", "cache"))
        for d in (os.path.join(eng, ".claude", "hooks"), stub, cache):
            os.makedirs(d)
        with open(os.path.join(eng, "product.json"), "w", encoding="utf-8") as f:
            json.dump({"engine": "ai-edit-engine", "version": installed, "update_url": "https://feed.invalid"}, f)
        with open(HOOK, encoding="utf-8") as src, \
             open(os.path.join(eng, ".claude", "hooks", "update-check.sh"), "w", encoding="utf-8") as dst:
            dst.write(src.read())
        curl = os.path.join(stub, "curl")
        with open(curl, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho '{\"version\": \"%s\", \"summary\": \"a fix\"}'\n" % feed)
        os.chmod(curl, os.stat(curl).st_mode | stat.S_IXUSR)
        env = {"PATH": stub + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
               "HOME": tmp, "XDG_CACHE_HOME": cache, "LANG": "C"}
        r = subprocess.run(["bash", ".claude/hooks/update-check.sh"], cwd=eng, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        return r.stdout, r.returncode


def main():
    print("update nudge: only when the feed is newer\n")
    cases = [
        ("1.0.94", "1.0.95", True, "the feed is one release ahead"),
        ("1.0.95", "1.0.94", False, "this copy is AHEAD of the feed (was nudged backwards)"),
        ("1.0.94", "1.0.94", False, "level with the feed"),
        ("1.0.99", "1.0.100", True, "1.0.100 is newer than 1.0.99 (a text compare says otherwise)"),
        ("1.0.100", "1.0.99", False, "1.0.99 is older than 1.0.100"),
        ("1.0", "1.0.1", True, "a missing part counts as 0"),
        ("1.1", "1.0.99", False, "1.1 is newer than 1.0.99"),
        ("1.0.08", "1.0.9", True, "08 is read as eight, not as a broken octal"),
    ]
    for installed, feed, want, why in cases:
        out, rc = nudge(installed, feed)
        said = "newer version" in out
        check(f"installed {installed}, feed {feed}: {'nudge' if want else 'silent'} ({why})",
              said == want and rc == 0, f"rc={rc} out={out!r}")
        if said:
            try:
                ok = json.loads(out)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
            except (ValueError, KeyError, TypeError):
                ok = False
            check(f"...and the nudge is valid hook JSON ({installed} -> {feed})", ok, out)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("all good: a copy is only ever nudged forward")
    return 0


if __name__ == "__main__":
    sys.exit(main())
