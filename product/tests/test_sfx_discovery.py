#!/usr/bin/env python3
"""Guard: the bundled sound library answers the same from ANY working directory.

The bug this prevents: the sound pass found its library by globbing "product/creative-vault/sfx/" as a
repo-relative path. On a real build a long run of directory changes had left the working directory three
folders deep inside a job, every glob came back empty, and a finished reel was handed to the creator
SILENT with "no sound effects available" — while 239 real files sat exactly where they belong. Nothing
was missing; the question was asked from the wrong place. capcut_sfx.palette() resolves from the module's
own location, so it cannot be asked from the wrong place, and "capcut_sfx.py --list" makes that answer
reachable from a shell in any folder.

Run: python3 product/tests/test_sfx_discovery.py
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SFX = os.path.join(ROOT, "product", "capcut_sfx.py")

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def cues(cwd):
    r = subprocess.run([sys.executable, SFX, "--list"], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, "PYTHONUTF8": "1"})
    return r.returncode, [l for l in r.stdout.splitlines() if l.strip()], r.stderr


def main():
    print("bundled SFX discovery\n")
    rc, from_root, err = cues(ROOT)
    check("the engine answers from the repo root", rc == 0 and len(from_root) > 0, err)

    # The library is INDEX-DRIVEN now (creative-vault/sfx/sfx-index.json tags every cue by tone/job/
    # material, and the skill treats it as the source of truth). So the contract is no longer "a big pile of
    # files": it is that the index and the disk agree, and that the ship gate asks for what actually exists.
    VAULT = os.path.join(ROOT, "product", "creative-vault", "sfx")
    HFSFX = os.path.join(ROOT, ".claude", "skills", "media-use", "audio", "assets", "sfx")
    idx = json.load(open(os.path.join(VAULT, "sfx-index.json"), encoding="utf-8"))
    sounds = idx["sounds"]

    def resolves(entry):
        f = entry["file"]
        if entry.get("source") == "alias":       # documented pointer at another cue, not a path
            return True
        return os.path.isfile(os.path.join(VAULT, f)) or os.path.isfile(os.path.join(HFSFX, os.path.basename(f)))

    broken = sorted(k for k, v in sounds.items() if not resolves(v))
    check("every cue in the index resolves to a real file", not broken, f"unresolvable: {broken}")

    on_disk = []
    for root, _d, fs in os.walk(VAULT):
        for f in fs:
            if f.lower().endswith((".mp3", ".wav", ".m4a")):
                on_disk.append(os.path.relpath(os.path.join(root, f), VAULT))
    named = {v["file"] for v in sounds.values()}
    unindexed = sorted(f for f in on_disk if f not in named)
    check("every sound on disk is in the index (an unindexed file is one nothing will ever pick)",
          not unindexed, f"not in the index: {unindexed[:6]}")

    # The wall groups by mood and the skill budgets cues per mood, so the two vocabularies have to agree:
    # a mood with no budget gets no guidance, a budget for a mood nothing carries is dead advice.
    moods = {v.get("mood") for v in sounds.values() if v.get("mood")}
    check("every mood has a density budget, and every budget has a mood",
          moods == set(idx["density"]), f"moods={sorted(moods)} density={sorted(idx['density'])}")

    # The ship gate names its required sounds by FILENAME, so it and the library have to agree. They drift
    # apart the moment the library is reorganised, and the failure only shows up at ship time.
    gate = open(os.path.join(ROOT, "check-ship.sh"), encoding="utf-8").read()
    m = re.search(r"REQ_SFX=\(([^)]*)\)", gate)
    req = m.group(1).split() if m else []
    absent = [r for r in req if not os.path.isfile(os.path.join(VAULT, r + ".mp3"))]
    check("check-ship.sh §14 asks only for sounds that exist at the path it checks", not absent,
          f"REQ_SFX names {', '.join(n + '.mp3' for n in absent)}, not present in creative-vault/sfx/ — "
          f"make-ship would stage a bundle its own gate rejects")

    # the exact drift that caused the miss: deep inside a job's graphics folder
    deep = os.path.join(ROOT, "projects", "_sfx_discovery_test", "hf-graphics")
    os.makedirs(deep, exist_ok=True)
    try:
        rc2, from_deep, err2 = cues(deep)
        check("it answers the same from inside a job's hf-graphics folder", rc2 == 0 and from_deep == from_root,
              f"{len(from_deep)} vs {len(from_root)} cues; {err2}")
        # and from a folder outside the engine entirely
        with tempfile.TemporaryDirectory() as d:
            rc3, from_away, err3 = cues(d)
            check("it answers the same from outside the engine folder", rc3 == 0 and from_away == from_root,
                  f"{len(from_away)} vs {len(from_root)} cues; {err3}")
    finally:
        for p in (deep, os.path.dirname(deep)):
            try: os.rmdir(p)
            except OSError: pass

    # every cue resolves to a file that is really there
    r = subprocess.run([sys.executable, SFX, "--list", "--paths"], cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONUTF8": "1"})
    rows = [l.split("\t") for l in r.stdout.splitlines() if "\t" in l]
    check("--paths gives one real file per cue", rows and all(len(x) == 2 and os.path.isfile(x[1]) for x in rows),
          f"{sum(1 for x in rows if len(x) != 2 or not os.path.isfile(x[1]))} bad row(s)")
    check("--paths are absolute, so they survive a change of directory",
          rows and all(os.path.isabs(x[1]) for x in rows))

    # the cue names the sound pass is told to use must actually resolve
    # A cue the index OFFERS (enabled, not an alias) must be one the engine can actually play. A disabled
    # cue is meant not to resolve, so it is excluded here rather than treated as a fault.
    offered = [k for k, v in sounds.items()
               if v.get("enabled") is not False and v.get("source") != "alias"]
    missing = [c for c in offered if c not in from_root]
    check("every cue the index offers is actually playable by the engine", not missing,
          f"offered by the index but not resolvable by palette(): {missing[:8]}")
    check("the index offers a usable number of sounds", len(offered) >= 40, f"only {len(offered)} enabled")

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
