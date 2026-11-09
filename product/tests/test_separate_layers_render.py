#!/usr/bin/env python3
"""test_separate_layers_render.py — separate_layers.sh renders a full-screen layer, and says why a build broke.

Two faults, both from one Intel tester's report:

1. render_layer() called reel_render.py with a fixed argument list. A layer holding only full-screen takeovers
   (or the breakaway card) covers her face BY DESIGN, so the render's subject check could only refuse it, and
   there was no way to pass --no-subject (or --low-memory) through. Now such a layer gets --no-subject on its
   own, a layer with anything else in it keeps the check, and REEL_RENDER_EXTRA passes more through. With
   nothing set, every other layer renders with exactly the arguments it always had.

2. When the graphics builder CRASHED (a newer-Python-only line reaching an older Python: SyntaxError on every
   build), she was told "this reel has no graphics to separate yet", with the real reason in a one-line
   "Why:". A crash is now said as a crash, with its error and where it happened; a builder that stopped on
   purpose is still a reason about the reel.

The shell part runs the script's own functions (cut out of separate_layers.sh), with python3 stood in by a
recorder, so it tests the real code without rendering anything.

Run:  python3 product/tests/test_separate_layers_render.py
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
SCRIPT = os.path.join(PRODUCT, "separate_layers.sh")

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-400:]) if detail else ''}")


def function(src, name):
    """The text of one shell function, from its `name () {` line to the `}` that closes it."""
    one = re.search(rf"^{name} \(\) \{{[^\n]*\}}[^\n]*\n", src, re.M)      # a one-line function
    if one:
        return one.group(0)
    m = re.search(rf"^{name} \(\) \{{.*?^\}}\n", src, re.S | re.M)
    return m.group(0) if m else ""


def shell_part():
    bash = shutil.which("bash")
    if not bash:
        print("  (shell part skipped: no bash here)")
        return
    src = open(SCRIPT, encoding="utf-8").read()
    fns = "".join(function(src, n) for n in ("owns_screen_only", "render_layer", "build_log", "build_failed"))
    check("the script still defines the functions this test drives", fns.count("() {") == 4, fns[:200])
    check("no fixed-argument render call is left in the script",
          not re.search(r'reel_render\.py" render "\$OD" -o "\$2" >', src))
    tmp = tempfile.mkdtemp(prefix="sep-layers-")
    try:
        rec = os.path.join(tmp, "argv.txt")
        harness = (
            'set -e\n'
            f'ROOT="{ROOT}"; OD="{tmp}/od"; WORK="{tmp}"\n'
            # Stand-in for python3 that records the render's argv and succeeds. layer_probe.py runs for real.
            'python3 () { if [ "$2" = "render" ]; then printf "%s\\n" "$*" >> "' + rec + '"; return 0; fi; '
            f'command "{sys.executable}" "$@"; }}\n'
            + fns + '\n"$@"\n')
        hpath = os.path.join(tmp, "h.sh")
        with open(hpath, "w", encoding="utf-8") as fh:
            fh.write(harness)

        def render(*args, extra=None):
            if os.path.exists(rec):
                os.remove(rec)
            env = {k: v for k, v in os.environ.items() if k != "REEL_RENDER_EXTRA"}
            if extra is not None:
                env["REEL_RENDER_EXTRA"] = extra
            r = subprocess.run([bash, hpath, "render_layer", *args], capture_output=True, text=True, env=env)
            argv = open(rec, encoding="utf-8").read().strip() if os.path.exists(rec) else ""
            return r.returncode, argv, r.stdout + r.stderr

        base = f"{ROOT}/product/reel_render.py render {tmp}/od -o {tmp}/x.mov"
        rc, argv, said = render("captions", f"{tmp}/x.mov")
        check("an ordinary layer renders with exactly the arguments it always had", argv == base, (argv, said))
        rc, argv, said = render("takeover", f"{tmp}/x.mov")
        check("a takeover layer renders with --no-subject", argv == base + " --no-subject", (argv, said))
        check("and says why, in one plain line", "full-screen by design" in said, said)
        rc, argv, _ = render("breakaway", f"{tmp}/x.mov")
        check("a breakaway-card layer renders with --no-subject", argv.endswith(" --no-subject"), argv)
        rc, argv, _ = render("rest", f"{tmp}/x.mov", "takeover,breakaway")
        check("a 'rest' layer that is only full-screen moments renders with --no-subject",
              argv.endswith(" --no-subject"), argv)
        rc, argv, _ = render("rest", f"{tmp}/x.mov", "takeover,captions")
        check("a 'rest' layer with anything else in it keeps the subject check", "--no-subject" not in argv, argv)
        rc, argv, _ = render("captions", f"{tmp}/x.mov", extra="--low-memory")
        check("REEL_RENDER_EXTRA passes through to the render", argv == base + " --low-memory", argv)
        rc, argv, _ = render("takeover", f"{tmp}/x.mov", extra="--low-memory --strict")
        check("REEL_RENDER_EXTRA adds to the automatic flag, word by word",
              argv == base + " --no-subject --low-memory --strict", argv)
        rc, argv, _ = render("captions", f"{tmp}/x.mov", extra="")
        check("an empty REEL_RENDER_EXTRA adds nothing", argv == base, argv)

        # build_failed reads the build's own log back and says what happened.
        bad = os.path.join(tmp, "bad.py")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write('x = {"a": 1}\nprint(f"{x["a"]!r:>{len(x)}" 1)\n')
        crash = subprocess.run([sys.executable, bad], capture_output=True, text=True)
        with open(os.path.join(tmp, "takeover.build.log"), "w", encoding="utf-8") as fh:
            fh.write(crash.stdout + crash.stderr)
        r = subprocess.run([bash, hpath, "build_failed", "takeover", "1", "takeover"], capture_output=True, text=True)
        said = r.stdout + r.stderr
        check("a crashed layer build is said as a crash in the engine", "crashed" in said and "engine" in said, said)
        check("with the real error", "SyntaxError" in said, said)
        check("and where the log is", "takeover.build.log" in said, said)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_part():
    spec = importlib.util.spec_from_file_location("layer_probe", os.path.join(PRODUCT, "layer_probe.py"))
    lp = importlib.util.module_from_spec(spec); spec.loader.exec_module(lp)
    tmp = tempfile.mkdtemp(prefix="probe-crash-")
    try:
        # A builder that cannot even be compiled: what every build did on an older Python.
        prod = os.path.join(tmp, "product")
        os.makedirs(os.path.join(prod))
        os.makedirs(os.path.join(tmp, "projects", "some-job"))
        with open(os.path.join(prod, "build-reel-type.py"), "w", encoding="utf-8") as fh:
            fh.write('import os\nlabel = "x"\nprint(f"{label + "y" if True else "}"  "z" )\n')
        lp.HERE, lp.ROOT = prod, tmp
        try:
            lp.probe("some-job", "Butter")
            said = ""
        except SystemExit as e:
            said = str(e)
        check("a builder that crashes is not reported as 'no graphics to separate yet'",
              "no graphics to separate" not in said, said)
        check("it says the builder crashed and that it is the engine, not her reel",
              "crashed" in said and "not in your reel" in said, said)
        check("it names the error", "SyntaxError" in said, said)
        check("it names where (file and line)", re.search(r"Where: product/build-reel-type\.py:\d+", said), said)
        check("it points at /report-a-problem", "/report-a-problem" in said, said)

        # A builder that stops on purpose with its own message is still a reason about the reel.
        with open(os.path.join(prod, "build-reel-type.py"), "w", encoding="utf-8") as fh:
            fh.write('import sys\nsys.exit("caption-plan.json is missing for this reel")\n')
        try:
            lp.probe("some-job", "Butter")
            said = ""
        except SystemExit as e:
            said = str(e)
        check("a builder that stops on purpose still says the reel has no graphics yet",
              "no graphics to separate yet" in said and "caption-plan.json is missing" in said, said)
        check("and does not call that a crash", "crashed" not in said, said)

        lp.HERE, lp.ROOT = PRODUCT, ROOT
        # An exception deep in the builder: the innermost frame is where it broke.
        text = ('Traceback (most recent call last):\n'
                f'  File "{ROOT}/product/build-reel-type.py", line 40, in <module>\n'
                '    import stylepack\n'
                f'  File "{ROOT}/product/stylepack.py", line 12, in <module>\n'
                '    x = load()\n'
                "KeyError: 'palette'\n")
        lines = lp.explain_build_failure(text, 1)
        check("a traceback names its innermost frame", any("Where: product/stylepack.py:12" in l for l in lines), lines)
        check("and its error", any("KeyError: 'palette'" in l for l in lines), lines)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    shell_part()
    probe_part()
    if fails:
        print(f"test_separate_layers_render: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_separate_layers_render: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
