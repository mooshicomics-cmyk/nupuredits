#!/usr/bin/env python3
"""pull-reels' cut-shorts.py: one bad reel never costs the others their turn, an empty or null hook means no
card, the cut runs under the bash a shell would find, and the reels are named after the job.

  batch    a reel the plan left without segments or a name, or one whose footage ffprobe cannot read, is that
           reel's failure: it is reported, the reels after it still build, and the run ends naming it.
  hook     "hook" is a list of lines (or one string); [] and null both mean no card, never the word "None".
  bash     a bare "bash" on Windows is looked up in System32 first, which is WSL's, not Git Bash.
  command  set-up / build <job> [<reel> ...]: the job by name or folder, and only the reels named.
  on disk  a job pulled by an earlier engine still rebuilds, its reels where they already are.

The steps that shell out (the cut, the frame, the type, the export copy) are stood in for, so this runs in a
second and records exactly what each reel would have run.

Run: python3 product/tests/test_cut_shorts_batch.py
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


spec = importlib.util.spec_from_file_location(
    "cut_shorts_under_test", os.path.join(ROOT, ".claude", "skills", "pull-reels", "scripts", "cut-shorts.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

SEG = [{"start": 0.0, "end": 1.5}]


def _run_cli(*argv):
    """Run cut-shorts.py with `argv`, every shelled-out step stood in for.
    -> (exit code, what it printed, every command it would have run)."""
    ran = []

    def fake_run(cmd, env=None):
        ran.append([str(c) for c in cmd])
        return 0

    def fake_vertical(job, name, framing="fill"):
        if name == "probe-fails":
            raise subprocess.CalledProcessError(1, ["ffprobe", str(job)])
    real = (mc._run, mc._vertical, mc._export_copy)
    mc._run, mc._vertical, mc._export_copy = fake_run, fake_vertical, (lambda d, n: None)
    saved = sys.argv
    sys.argv = ["cut-shorts.py", *argv]
    out = io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            mc.main()
    except SystemExit as e:
        code = e.code
    finally:
        sys.argv = saved
        mc._run, mc._vertical, mc._export_copy = real
    return code, out.getvalue(), ran


def _caption_calls(ran):
    return {c[2].rsplit(os.sep, 1)[-1]: c for c in ran if c[1].endswith(os.path.join("clean-captions", "build.py"))}


def _new_parent(where, reels):
    os.makedirs(os.path.join(where, "transcript"))
    with open(os.path.join(where, "src.mp4"), "wb") as fh:
        fh.write(b"not really a video")
    with open(os.path.join(where, "transcript", "words.json"), "w", encoding="utf-8") as fh:
        json.dump({"words": []}, fh)
    with open(os.path.join(where, "reels-plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": "src.mp4", "reels": reels}, fh)
    return where


def check_batch(tmp):
    parent = _new_parent(os.path.join(tmp, "batch"), [
        {"rank": 1, "name": "no-segments"},
        {"rank": 2, "segments": SEG},                                                  # no name at all
        {"rank": 3, "name": "probe-fails", "segments": SEG, "hook": ["a real hook"]},
        {"rank": 4, "name": "null-hook", "segments": SEG, "hook": None},
        {"rank": 5, "name": "empty-hook", "segments": SEG, "hook": []},
        {"rank": 6, "name": "two-line-hook", "segments": SEG, "hook": ["the week after", "nobody posts about"],
         "hook_end": 8.0},
        {"rank": 7, "name": "string-hook", "segments": SEG, "hook": "said out loud", "hook_end": 2.5},
    ])
    code, said, ran = _run_cli("build", parent)
    check("the run ends as a failure naming every failed reel",
          isinstance(code, str) and all(n in code for n in ("no-segments", "#2", "probe-fails"))
          and not any(n in code for n in ("null-hook", "empty-hook", "two-line-hook", "string-hook")), code)
    check("a reel without segments is reported, not a traceback", "no-segments: could not set up its folder" in said, said)
    check("a reel without a name is reported", "reel #2: the plan gives it no name" in said, said)
    check("an ffprobe error fails that reel only", "probe-fails stopped: CalledProcessError" in said, said)
    check("the reels after the failures were still built",
          all(f"✓ {n}" in said for n in ("null-hook", "empty-hook", "two-line-hook", "string-hook")), said)
    caps = _caption_calls(ran)
    for n in ("null-hook", "empty-hook"):
        c = caps.get(n)
        check(f"an empty or null hook means no card ({n})", c is not None and c[c.index("--hook-text") + 1] == "", c)
    two = caps.get("two-line-hook")
    check("a hook given as lines reaches the card as those lines",
          two is not None and two[two.index("--hook-text") + 1] == "the week after\nnobody posts about"
          and two[two.index("--hook-end") + 1] == "8.0", two)
    one = caps.get("string-hook")
    check("a hook given as one string still passes through with its end time",
          one is not None and one[one.index("--hook-text") + 1] == "said out loud"
          and one[one.index("--hook-end") + 1] == "2.5", one)
    cuts = [c for c in ran if c[1].endswith("stitch-cut.sh")]
    want = shutil.which("bash") or "bash"
    check("the cut runs under the bash a shell would find", cuts and all(c[0] == want for c in cuts),
          [c[0] for c in cuts])
    check("every reel builds into reels/<name>/",
          os.path.isdir(os.path.join(parent, "reels", "two-line-hook")) and "reels/two-line-hook: set up," in said, said)
    check("the messages say reel", "=== reel two-line-hook ===" in said, said)


def check_command(tmp):
    parent = _new_parent(os.path.join(tmp, "named"), [
        {"name": "first", "segments": SEG}, {"name": "second", "segments": SEG}, {"name": "third", "segments": SEG}])
    code, said, ran = _run_cli("set-up", parent, "second")
    check("set-up builds nothing", code is None and not ran, (code, ran))
    check("set-up with a reel named sets up only that one",
          os.path.isdir(os.path.join(parent, "reels", "second")) and not os.path.exists(os.path.join(parent, "reels", "first")))
    check("set-up says how to build next", "cut-shorts.py build named" in said, said)
    code, said, ran = _run_cli("build", parent, "first", "third")
    built = {c[2].rsplit(os.sep, 1)[-1] for c in ran if c[1].endswith("stitch-cut.sh")}
    check("build with reels named builds exactly those", code is None and built == {"first", "third"}, (code, built))
    code, said, _ = _run_cli("build", parent, "nope")
    check("a name that matches no reel stops plainly", code == "cut-shorts: no reel in the plan matched", code)

    # a job by name, looked up under the engine's projects/
    real_engine = mc.ENGINE
    mc.ENGINE = Path(tmp) / "engine"
    try:
        _new_parent(os.path.join(tmp, "engine", "projects", "by-name"), [{"name": "only", "segments": SEG}])
        code, said, _ = _run_cli("set-up", "by-name")
        check("a job given by name is found under projects/",
              code is None and os.path.isdir(os.path.join(tmp, "engine", "projects", "by-name", "reels", "only")), (code, said))
    finally:
        mc.ENGINE = real_engine

    code, said, _ = _run_cli("set-up", os.path.join(tmp, "no-plan-here"))
    check("a job with no reels plan says to run the pull-reels pass", isinstance(code, str)
          and "reels-plan.json yet: the pull-reels pass writes it" in code, code)


def check_earlier_job(tmp):
    """A job pulled by an earlier engine: clips-plan.json, its reels under "clips" with "hook_text", built in clips/."""
    parent = os.path.join(tmp, "earlier")
    os.makedirs(os.path.join(parent, "transcript"))
    with open(os.path.join(parent, "src.mp4"), "wb") as fh:
        fh.write(b"not really a video")
    with open(os.path.join(parent, "transcript", "words.json"), "w", encoding="utf-8") as fh:
        json.dump({"words": []}, fh)
    with open(os.path.join(parent, "clips-plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": "src.mp4", "clips": [
            {"id": 1, "name": "said-once", "segments": SEG, "hook_text": "the line\nunder it", "hook_end": 2.5},
            {"id": 2, "name": "no-card", "segments": SEG, "hook_text": None}]}, fh)
    code, said, ran = _run_cli("build", parent, "said-once", "no-card")
    caps = _caption_calls(ran)
    one, none = caps.get("said-once"), caps.get("no-card")
    check("an earlier job rebuilds in the folder its reels are already in",
          code is None and os.path.isdir(os.path.join(parent, "clips", "said-once"))
          and not os.path.exists(os.path.join(parent, "reels")), (code, said))
    check("an earlier job's hook_text still becomes the card",
          one is not None and one[one.index("--hook-text") + 1] == "the line\nunder it"
          and one[one.index("--hook-end") + 1] == "2.5", one)
    check("an earlier job's null hook_text still means no card",
          none is not None and none[none.index("--hook-text") + 1] == "", none)
    with open(os.path.join(parent, "reels-plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": "src.mp4", "reels": [{"name": "fresh", "segments": SEG}]}, fh)
    code, said, _ = _run_cli("set-up", parent)
    check("a job holding both plans reads reels-plan.json", "fresh" in said and "said-once" not in said, said)


def main():
    tmp = tempfile.mkdtemp(prefix="cut-shorts-batch-")
    real_tmp = tempfile.tempdir
    tempfile.tempdir = os.path.join(tmp, "scratch")
    os.makedirs(tempfile.tempdir)
    try:
        check_batch(tmp)
        check_command(tmp)
        check_earlier_job(tmp)
    finally:
        tempfile.tempdir = real_tmp
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_cut_shorts_batch: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_cut_shorts_batch: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
