#!/usr/bin/env python3
"""relisten_flags.py: the re-listen's flagged spots surface at the cut review, every time.

verify-cut.py saves the spots it wasn't sure about to transcript/.verify-cut-listens.json. Those used to
live only in the build log, so a cut could be reviewed and shipped without anyone looking at the one place
it was known to be shaky (2026-11-02: a doubled take and dead air shipped past dismissed warnings). This
checks the tool that pulls them into the review: it shows real spots with their time, and prints NOTHING on
a clean cut so it is safe to run on every review.
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # product/
import relisten_flags as rf

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {detail}"))
    if not ok:
        FAILS.append(name)


def _job(d, flags):
    os.makedirs(os.path.join(d, "transcript"), exist_ok=True)
    state = {"plan": "x", "listens": 1, "flags": flags}
    json.dump(state, open(os.path.join(d, "transcript", ".verify-cut-listens.json"), "w", encoding="utf-8"))


def main():
    with tempfile.TemporaryDirectory() as d:
        # a reel with a flagged spot (the stored shape verify-cut writes)
        job = os.path.join(d, "a-reel")
        _job(job, [
            "  line 29 @ 89.9s [mismatch (audio != plan)]",
            "      plan says : a month crazy",
            "      cut plays : (missing/dropped)",
        ])
        out = rf.block(job)
        check("a flagged spot is surfaced", out != "", out)
        check("its time is shown as m:ss", "1:30" in out, out)
        check("it names what was expected and heard", 'a month crazy' in out and 'missing/dropped' in out, out)
        check("it tells her to listen, not that it is broken", "listen" in out.lower() and "error" not in out.lower(), out)
        check("--quiet signals there are spots (exit 1)", rf.spots(job), "no spots parsed")

        # a clean reel: a state file with no flags prints NOTHING (safe to run every time)
        clean = os.path.join(d, "clean-reel")
        _job(clean, [])
        check("a clean cut surfaces nothing", rf.block(clean) == "", rf.block(clean))

        # a reel verify-cut never ran on (no state file): also nothing, no crash
        none = os.path.join(d, "no-state")
        os.makedirs(os.path.join(none, "transcript"), exist_ok=True)
        check("a reel with no re-listen state surfaces nothing", rf.block(none) == "", "should be empty")

        # a flag with only a time (no plan/cut lines) still surfaces with its time
        tonly = os.path.join(d, "time-only")
        _job(tonly, ["  line 4 @ 12.0s [mismatch (audio != plan)]"])
        bt = rf.block(tonly)
        check("a bare time-only flag still shows its time", "0:12" in bt, bt)

    print("test_relisten_flags: " + ("all checks passed" if not FAILS else f"{len(FAILS)} FAILED"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
