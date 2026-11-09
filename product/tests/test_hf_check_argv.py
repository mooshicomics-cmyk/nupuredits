#!/usr/bin/env python3
"""Guard: the `hyperframes check` argv the gate builds is one the pinned CLI actually accepts.

The regression this prevents: 1.0.65 built `... --at-transitions --frame-check --timeout=3000`. On 0.7.68
(the pin at the time) `--frame-check` takes an optional value and swallows the token after it, so every gated
render was refused with "Invalid --frame-check" before it ever looked at the composition. Newer CLIs happen
to accept that order, which is exactly why only a live run against the CURRENT pin proves anything. Reading the code cannot
catch that; only running the real CLI can. This test builds a minimal composition and runs the exact argv
through `npx hyperframes@<pin> check`. It passes when the CLI parses the flags (whatever it then thinks of
the composition) and fails on any "Invalid --..." or "Unknown flag" response. Skips when npx is absent.

Run: python3 product/tests/test_hf_check_argv.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from npx_run import _without_check_progress, hf_check_argv, hf_check_env, hf_check_timeout_ms, hf_check_max_transition_samples, check_ran_out_of_time   # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def pin():
    try:
        v = json.load(open(os.path.join(os.path.dirname(HERE), "..", "product.json"), encoding="utf-8")).get("hyperframes")
        if v:
            return str(v)
    except Exception:
        pass
    import reel_render
    return reel_render.HF_VERSION


MINI_HTML = """<!doctype html><html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:1080px;height:1920px;overflow:hidden;background:transparent}
#root{position:absolute;inset:0}.t{position:absolute;top:400px;left:120px;font:700 80px/1 sans-serif;color:#fff}</style></head>
<body><div id="root" data-composition-id="mini" data-start="0" data-duration="1.00" data-width="1080" data-height="1920">
<div class="clip" id="clip-a" data-start="0" data-duration="1.00" data-track-index="1"><div class="t" id="t0">hello</div></div>
</div></body></html>
"""
MINI_JSON = {"paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
             "media": {"autoProxy": True}}


def main():
    print("hyperframes check argv\n")
    v = pin()
    argv = hf_check_argv(v, "/tmp/x", strict=False)
    tail = argv[argv.index("check"):]
    check("--timeout comes right after the composition dir", tail[2].startswith("--timeout="), str(tail))
    check("--frame-check is the last token (nothing for it to swallow)", tail[-1] == "--frame-check", str(tail))
    s = hf_check_argv(v, "/tmp/x", strict=True)
    st = s[s.index("check"):]
    check("--strict never follows --frame-check", st.index("--strict") < st.index("--frame-check"), str(st))
    check("timeout is a positive integer", hf_check_timeout_ms() >= 500)

    # The transition-sample cap: without it a caption on every word (700+ tween boundaries) runs the check out
    # of HyperFrames' fixed 120 s ("check_runtime_failure: Check did not finish within its deadline").
    cap = hf_check_max_transition_samples()
    check("a transition-sample cap is on by default", cap > 0, str(cap))
    caps = [t for t in tail if t.startswith("--max-transition-samples=")]
    check("the cap is one --flag=value token", caps == [f"--max-transition-samples={cap}"], str(tail))
    check("the cap sits after --at-transitions and before --frame-check",
          bool(caps) and tail.index("--at-transitions") < tail.index(caps[0]) < tail.index("--frame-check"), str(tail))
    old_env = os.environ.get("REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES")
    try:
        os.environ["REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES"] = "0"
        off = hf_check_argv(v, "/tmp/x")
        check("REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES=0 turns the cap off",
              not any(t.startswith("--max-transition-samples") for t in off) and off[-1] == "--frame-check", str(off))
        os.environ["REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES"] = "250"
        on = hf_check_argv(v, "/tmp/x", strict=True)
        check("the env override sets the cap", "--max-transition-samples=250" in on and on[-1] == "--frame-check", str(on))
    finally:
        if old_env is None:
            os.environ.pop("REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES", None)
        else:
            os.environ["REELS_ENGINE_HF_CHECK_MAX_TRANSITION_SAMPLES"] = old_env
    explicit = hf_check_argv(v, "/tmp/x", max_transition_samples=7)
    check("an explicit cap wins", "--max-transition-samples=7" in explicit, str(explicit))

    # HyperFrames' deadline line is a time budget, not a finding (reel_render.py says it as that).
    deadline_out = ("Runtime\n  \u2717 check_runtime_failure: Check did not finish within its deadline.\n"
                    "    selector [data-composition-id], time 0\n\n\u2717 Check failed")
    check("a check that hit HyperFrames' deadline is recognized", check_ran_out_of_time(deadline_out))
    check("a script that hit the deadline is recognized",
          check_ran_out_of_time("index.html: its script did not finish within the check deadline."))
    check("an ordinary failed check is not called out of time", not check_ran_out_of_time("\u2717 overlap ...\nCheck failed"))

    # A check that hit the deadline is HyperFrames' verdict (status "ran", exit 1): reel_render.py warns and renders.
    # It must never read as the checking tool crashing (status "crashed" refuses the render, exit 4).
    from npx_run import run_hf_check
    fake = tempfile.mkdtemp(prefix="hf-deadline-")
    try:
        script = os.path.join(fake, "check.py")
        open(script, "w", encoding="utf-8").write(
            "import sys\nprint(deadline)\nsys.exit(1)\n".replace("deadline", repr(deadline_out)))
        res = run_hf_check([sys.executable, script], step="test", echo=False)
        check("a check out of time is a verdict, not a crash (it warns and renders)",
              res.status == "ran" and res.rc == 1, f"status={res.status} rc={res.rc}")
    finally:
        shutil.rmtree(fake, ignore_errors=True)

    noisy = ("Layout\n  \u25c7 0 issues across 52 sample(s)\n[hyperframes] check: samples 1/52\n"
             "[hyperframes] check: craft 72/72\r\n[hyperframes] check: overlap 3/8\n\u25c7  Check passed\n"
             "[hyperframes] browserGpuMode probe \u2192 hardware\n")
    quiet = _without_check_progress(noisy)
    check("the check's per-step progress lines are not echoed", "check: samples" not in quiet
          and "check: craft" not in quiet and "check: overlap" not in quiet, quiet)
    check("everything else the check says is echoed as written",
          "0 issues across 52 sample(s)" in quiet and "Check passed" in quiet and "browserGpuMode" in quiet, quiet)

    saved_ci = os.environ.pop("CI", None)
    try:
        check("the check runs with CI=1 (no warm check left behind)", hf_check_env().get("CI") == "1")
        os.environ["CI"] = "true"
        check("a CI value already set is kept", hf_check_env().get("CI") == "true")
    finally:
        os.environ.pop("CI", None)
        if saved_ci is not None:
            os.environ["CI"] = saved_ci

    if not shutil.which("npx"):
        print("  SKIP  live CLI parse (npx not on PATH)")
    else:
        d = tempfile.mkdtemp(prefix="hf-argv-")
        try:
            open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(MINI_HTML)
            json.dump(MINI_JSON, open(os.path.join(d, "hyperframes.json"), "w", encoding="utf-8"))
            for strict in (False, True):
                cmd = hf_check_argv(v, d, strict=strict)
                cmd.insert(1, "--yes") if cmd[0] == "npx" else None
                try:
                    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=hf_check_env())
                    out = re.sub(r"\x1b\[[0-9;]*m", "", (p.stdout or "") + (p.stderr or ""))
                except subprocess.TimeoutExpired:
                    out = "TIMEOUT"
                bad = re.search(r"Invalid --[a-z-]+|Unknown flag|Unknown option|unknown option", out)
                check(f"hyperframes@{v} accepts the argv (strict={strict})", bad is None and out != "TIMEOUT",
                      (bad.group(0) if bad else out[-300:]))
            if os.name != "nt" and shutil.which("pgrep"):
                # From 0.8.186 HyperFrames leaves a detached "warm check" (Node + a launched Chrome, five minutes)
                # after a check run without a terminal, unless CI is set; the engine's checks never leave one.
                warm = subprocess.run(["pgrep", "-f", f"warmCheck.js .*{d}"], capture_output=True, text=True)
                check("no warm check is left running after the engine's check", not warm.stdout.strip(), warm.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
