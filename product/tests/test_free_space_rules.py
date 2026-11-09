#!/usr/bin/env python3
"""Guard: scripts/free-space.sh clears only what the engine renders or installs again, and nothing she made.

Each case builds a throwaway engine folder (a copy of free-space.sh and a projects/ folder laid out like a real
job) and runs the script there, so the real projects/ and CapCut's drafts are never touched.

What it holds:
  - cleared: a composition's renders/ (index.html or hyperframes.json beside it, or hf-graphics/renders/),
    HyperFrames' own scratch (work-<id>-* with captured-frames/ inside, <out>.assemble-work-*), and
    node_modules/ beside a package.json
  - never touched: raw/ and raw-*/ (even a renders/ inside), outputs/, a renders/ with no composition beside it,
    a folder she named work-something, node_modules with no package.json, the composition's own files, and
    any folder a CapCut draft still plays a file from
  - each kilobyte counted once; the look and --apply list the same items; a second --apply finds nothing
  - one folder du cannot read is named and left, and the sweep still finishes with exit 0
  - job names scope the sweep; an unknown job or an unknown option is refused

Run: python3 product/tests/test_free_space_rules.py
"""
import json, os, re, shutil, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-500:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def mkf(path, kib=1, body=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body.encode() if body is not None else b"x" * (kib * 1024))


def engine(tmp):
    eng = os.path.join(tmp, "engine")
    os.makedirs(os.path.join(eng, "scripts"))
    os.makedirs(os.path.join(tmp, "home"))
    shutil.copy(os.path.join(ROOT, "scripts", "free-space.sh"), os.path.join(eng, "scripts", "free-space.sh"))
    return eng


def run(eng, *args, env_extra=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C",
           "HOME": os.path.join(os.path.dirname(eng), "home")}
    env.update(env_extra or {})
    r = subprocess.run(["bash", "scripts/free-space.sh", *args], cwd=eng, capture_output=True, text=True,
                       encoding="utf-8", env=env)
    return r.returncode, r.stdout, r.stderr


def listed(out):
    """The folders a run names as clearable: '  <size>  <job-relative path>/  · <why>' under '<job>...' headers."""
    items, job = [], None
    for ln in out.splitlines():
        m = re.match(r"^(\S[^:]*?)(?::.*)?$", ln)
        if ln and not ln.startswith(" ") and m and not ln.startswith(("Looking", "Nothing", "Removed", "To clear")):
            job = m.group(1)
        m = re.match(r"^\s+(\d[\d.]* (?:KB|MB|GB))\s+(\S.*?)/\s+· ", ln)
        if m and job:
            items.append(f"{job}/{m.group(2)}")
    return items


def job_layout(P):
    """One job with everything a real one holds, plus each kind the sweep may clear."""
    j = f"{P}/reel-a"
    mkf(f"{j}/raw/IMG_0001.MOV", 50)
    mkf(f"{j}/raw/renders/odd.mov", 5)                       # footage stays, whatever its folder is called
    mkf(f"{j}/raw-mastered/IMG_0001.mp4", 20)
    mkf(f"{j}/outputs/reel-a.mp4", 30)
    mkf(f"{j}/outputs/reel-a.final.mp4", 30)
    mkf(f"{j}/outputs/hf-x/index.html", 1)
    mkf(f"{j}/outputs/hf-x/renders/x.mov", 10)               # anything under outputs/ stays
    mkf(f"{j}/transcript/cuts.json", 1, "{}")
    mkf(f"{j}/graphics-plan.json", 1, "{}")
    mkf(f"{j}/subject-zones.json", 1, "{}")
    # the graphics build: its sources and layer renders stay; only its renders/ folders go
    mkf(f"{j}/hf-graphics/build.py", 1)
    mkf(f"{j}/hf-graphics/g01-hook.mov", 40)
    mkf(f"{j}/hf-graphics/g01-hook/index.html", 1)
    mkf(f"{j}/hf-graphics/g01-hook/assets/hero.mp4", 15)
    mkf(f"{j}/hf-graphics/g01-hook/renders/g01-hook_2026-10-01_10-00-00.mov", 100)
    mkf(f"{j}/hf-graphics/g01-hook/renders/nested/renders/again.mov", 20)
    mkf(f"{j}/hf-graphics/renders/layer.mov", 60)
    # the type overlay, rendered the plain HyperFrames way
    mkf(f"{j}/hf-reel-type-butter/hyperframes.json", 1, "{}")
    mkf(f"{j}/hf-reel-type-butter/fonts/Inter-Black.otf", 2)
    mkf(f"{j}/hf-reel-type-butter/renders/hf-reel-type-butter_2026-10-01_10-05-00.mov", 200)
    # a renders/ she keeps by hand, with no composition beside it
    mkf(f"{j}/renders/her-cut.mov", 70)
    # HyperFrames scratch from a render that stopped, and a folder of hers that only looks similar
    mkf(f"{j}/sandbox/work-1180d35d-aa-XyZ123/captured-frames/frame_0001.png", 8)
    mkf(f"{j}/sandbox/out.mov.assemble-work-Ab12Cd/part1.mp4", 6)
    mkf(f"{j}/work-in-progress/notes.txt", 1)
    mkf(f"{j}/sandbox/work-ideas-2/sketch.png", 1)
    # packages
    mkf(f"{j}/hf-reel-type-butter/package.json", 1, "{}")
    mkf(f"{j}/hf-reel-type-butter/node_modules/pkg/index.js", 12)
    mkf(f"{j}/node_modules/loose/index.js", 4)               # no package.json beside it: stays
    return j


def main():
    print("free-space.sh: only what comes back, each byte once, never her footage or reels\n")

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        j = job_layout(P)
        mkf(f"{P}/reel-b/hf-captions/index.html", 1)
        mkf(f"{P}/reel-b/hf-captions/renders/captions.mov", 30)
        mkf(f"{P}/_capcut-staging/com.lveditor.draft/x 1.1/renders/r.mov", 5)
        mkf(f"{P}/_capcut-staging/com.lveditor.draft/x 1.1/index.html", 1)

        rc, out, err = run(eng)
        items = listed(out)
        want = {"reel-a/hf-graphics/g01-hook/renders", "reel-a/hf-graphics/renders",
                "reel-a/hf-reel-type-butter/renders", "reel-a/hf-reel-type-butter/node_modules",
                "reel-a/sandbox/work-1180d35d-aa-XyZ123", "reel-a/sandbox/out.mov.assemble-work-Ab12Cd",
                "reel-b/hf-captions/renders"}
        check("the look lists exactly the remakeable folders", rc == 0 and set(items) == want,
              f"extra={sorted(set(items) - want)} missing={sorted(want - set(items))}\n{out}{err}")
        check("each folder is listed once (nothing inside a listed folder is weighed again)",
              len(items) == len(set(items)) and not any("nested" in i for i in items), items)
        check("the CapCut staging folder is never entered", "_capcut-staging" not in out, out)
        check("the look removes nothing", os.path.exists(f"{j}/hf-reel-type-butter/renders"), out)

        rc2, out2, err2 = run(eng, "--apply")
        check("--apply lists the same items as the look", rc2 == 0 and listed(out2) == items, f"{listed(out2)}\n{err2}")
        check("--apply says how much came back", re.search(r"Removed 7 item\(s\): [0-9.]+ (KB|MB|GB) is free again", out2), out2)
        gone = [i for i in want if os.path.exists(os.path.join(P, i))]
        check("every listed folder is gone after --apply", not gone, gone)
        stays = ["raw/IMG_0001.MOV", "raw/renders/odd.mov", "raw-mastered/IMG_0001.mp4", "outputs/reel-a.mp4",
                 "outputs/reel-a.final.mp4", "outputs/hf-x/renders/x.mov", "transcript/cuts.json",
                 "graphics-plan.json", "subject-zones.json", "hf-graphics/build.py", "hf-graphics/g01-hook.mov",
                 "hf-graphics/g01-hook/index.html", "hf-graphics/g01-hook/assets/hero.mp4",
                 "hf-reel-type-butter/hyperframes.json", "hf-reel-type-butter/fonts/Inter-Black.otf",
                 "hf-reel-type-butter/package.json", "renders/her-cut.mov", "work-in-progress/notes.txt",
                 "sandbox/work-ideas-2/sketch.png", "node_modules/loose/index.js"]
        lost = [s for s in stays if not os.path.exists(os.path.join(j, s))]
        check("footage, outputs, plans, sources, layer renders and her own folders all stay", not lost, lost)
        check("the staging drafts stay", os.path.exists(f"{P}/_capcut-staging/com.lveditor.draft/x 1.1/renders/r.mov"))
        rc3, out3, _ = run(eng, "--apply")
        check("a second --apply finds nothing left to clear", rc3 == 0 and not listed(out3) and "Nothing to clear" in out3, out3)

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        mkf(f"{P}/one/hf-graphics/g1/index.html", 1)
        mkf(f"{P}/one/hf-graphics/g1/renders/a.mov", 10)
        mkf(f"{P}/two/hf-graphics/g2/index.html", 1)
        mkf(f"{P}/two/hf-graphics/g2/renders/b.mov", 10)
        # a draft that plays a file straight out of job one's renders/
        drafts = os.path.join(tmp, "home", "Movies", "CapCut", "User Data", "Projects", "com.lveditor.draft")
        linked = os.path.join(os.path.realpath(P), "one", "hf-graphics", "g1", "renders", "a.mov")
        mkf(os.path.join(drafts, "one 1.1", "draft_info.json"), 1,
            json.dumps({"materials": {"videos": [{"path": linked}]}}))
        rc, out, err = run(eng, "--apply")
        check("a folder a CapCut draft plays from stays, named as kept",
              rc == 0 and os.path.exists(linked) and "one/hf-graphics/g1/renders" not in listed(out)
              and "CapCut draft still plays" in out, out + err)
        check("...while the same kind of folder no draft uses is cleared",
              not os.path.exists(f"{P}/two/hf-graphics/g2/renders"), out)
        mkf(f"{P}/two/hf-graphics/g2/renders/b.mov", 10)
        mkf(f"{P}/three/hf-graphics/g3/index.html", 1)
        mkf(f"{P}/three/hf-graphics/g3/renders/c.mov", 10)
        rc, out, _ = run(eng, "three")
        check("a job name scopes the look to that job", rc == 0 and listed(out) == ["three/hf-graphics/g3/renders"], out)
        rc, out, _ = run(eng, "nope")
        check("an unknown job is refused with exit 1", rc == 1 and "no job called 'nope'" in out, out)
        rc, out, _ = run(eng, "../x")
        check("a path is not a job name", rc == 1, out)
        rc, out, _ = run(eng, "_capcut-staging")
        check("the staging folder is refused by name", rc == 1 and "not a job" in out, out)
        rc, out, _ = run(eng, "--aply")
        check("an unknown option is refused with exit 2 and removes nothing",
              rc == 2 and os.path.exists(f"{P}/three/hf-graphics/g3/renders"), out)
        rc, out, _ = run(eng, "three", "--apply")
        check("--apply after a job name clears only that job",
              rc == 0 and not os.path.exists(f"{P}/three/hf-graphics/g3/renders")
              and os.path.exists(f"{P}/two/hf-graphics/g2/renders"), out)

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        locked = f"{P}/j/hf-graphics/g/renders/inner"
        mkf(f"{P}/j/hf-graphics/g/index.html", 1)
        mkf(f"{locked}/f.mov", 1)
        mkf(f"{P}/k/hf-graphics/g/index.html", 1)
        mkf(f"{P}/k/hf-graphics/g/renders/f.mov", 4)
        os.chmod(locked, 0)
        try:
            if os.access(locked, os.R_OK):
                print("  SKIP  the unreadable-folder case (this account can read a mode-000 folder)")
            else:
                rc, out, err = run(eng, "--apply")
                check("a folder du cannot read is named and left, and the sweep finishes",
                      rc == 0 and re.search(r"\?\s+hf-graphics/g/renders/\s+· stays: part of it could not be read", out)
                      and "j/hf-graphics/g/renders" not in listed(out) and "free again" in out, f"rc={rc} {out} {err}")
                check("...and it is where it was, while the next one is still cleared",
                      os.path.isdir(f"{P}/j/hf-graphics/g/renders") and not os.path.exists(f"{P}/k/hf-graphics/g/renders"))
        finally:
            os.chmod(locked, stat.S_IRWXU)

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        # a job name that is also a glob pattern still has its raw/ cut off
        mkf(f"{P}/job[1]/raw/hf-x/index.html", 1)
        mkf(f"{P}/job[1]/raw/hf-x/renders/clip.mov", 5)
        mkf(f"{P}/job[1]/hf-graphics/g/index.html", 1)
        mkf(f"{P}/job[1]/hf-graphics/g/renders/a.mov", 5)
        rc, out, _ = run(eng, "--apply")
        check("a job named like a pattern (job[1]) still never has anything under raw/ touched",
              rc == 0 and os.path.exists(f"{P}/job[1]/raw/hf-x/renders/clip.mov")
              and not os.path.exists(f"{P}/job[1]/hf-graphics/g/renders"), out)

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        rc, out, _ = run(eng)
        check("no projects/ folder: exit 1 with a plain sentence", rc == 1 and "no projects/ folder" in out, out)

    with tempfile.TemporaryDirectory() as tmp:               # looks tried in the visual editor
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        L = f"{P}/reel-v/hf-graphics/_looks"
        for rel in ("add-w12/hook/hf-reel-type-butter/index.html", "add-w12/takeover/hf-reel-type-butter/index.html",
                    "k02-karaoke/word-card/index.html", "k02-karaoke/hook/hf-reel-type-butter/index.html",
                    "f01-note/_original/index.html", "f01-note/refined-2/hf-reel-type-butter/index.html",
                    "_refine/x/index.html", "_book/hook/hf-reel-type-butter/index.html"):
            mkf(f"{L}/{rel}", 2)
        mkf(f"{L}/add-w12/line.json", 1, "{}")
        mkf(f"{P}/reel-v/review/swaps.json", 1, json.dumps({
            "swaps": {"k02-karaoke": {"look": "word-card", "dir": "hf-graphics/_looks/k02-karaoke/word-card"},
                      "f01-note": {"look": "_original", "dir": "hf-graphics/_looks/f01-note/_original"}},
            "adds": {"add-w12": {"look": "hook", "dir": "hf-graphics/_looks/add-w12/hook/hf-reel-type-butter"}}}))
        rc, out, err = run(eng, "reel-v")
        items = set(listed(out))
        want = {"reel-v/hf-graphics/_looks/add-w12/takeover", "reel-v/hf-graphics/_looks/k02-karaoke/hook",
                "reel-v/hf-graphics/_looks/_book/hook"}
        check("looks: only the ones she tried and didn't keep are listed", rc == 0 and items == want,
              f"extra={sorted(items - want)} missing={sorted(want - items)}\n{out}{err}")
        rc, out, err = run(eng, "reel-v", "--apply")
        kept = [r for r in ("add-w12/hook", "k02-karaoke/word-card", "f01-note/_original", "f01-note/refined-2", "_refine/x", "add-w12/line.json")
                if not os.path.exists(f"{L}/{r}")]
        check("looks: in use, moved, refined and line notes all stay", rc == 0 and not kept, kept)
        mkf(f"{L}/add-w12/counter/index.html", 2)              # one more she didn't keep
        os.chmod(f"{P}/reel-v/review/swaps.json", 0)
        rc, out, err = run(eng, "reel-v")
        check("looks: an unreadable swaps.json clears no look at all", "_looks" not in out or os.geteuid() == 0, out)
        os.chmod(f"{P}/reel-v/review/swaps.json", 0o644)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("all good: free-space clears only what comes back, counts it once, and never touches her work")
    return 0


if __name__ == "__main__":
    sys.exit(main())
