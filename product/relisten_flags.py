#!/usr/bin/env python3
"""relisten_flags.py — surface the re-listen's flagged spots at the cut review, every time.

verify-cut.py (the stitch's independent ASR re-listen) flags the spots where the audio it heard did not
match the plan — a repeat/restart region, a clipped word, dead air a stamp hid. Those spots are the exact
places a cut goes wrong, and they are usually (not always) just a soft word the re-listen misheard. They
used to live only in the stitch's build log, which the creator never sees, so a bad cut could be reviewed
and shipped without anyone looking at the one place it was known to be shaky.

This reads the flags verify-cut saved (projects/<job>/transcript/.verify-cut-listens.json) and prints them
as a short, plain block to include in the review, on BOTH review roads. It prints NOTHING when there are
no flags, so it is safe to run on every review. It changes no cut and reads no audio.

Usage:  python3 product/relisten_flags.py <job>            # job name, or projects/<job>, or a path
        python3 product/relisten_flags.py <job> --quiet    # exit 0/1 only (1 = there are spots), no output
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _job_dir(arg):
    arg = arg.rstrip("/")
    if arg.startswith("projects/"):
        arg = arg[len("projects/"):]
    if os.path.isdir(os.path.join(arg, "transcript")):
        return os.path.abspath(arg)
    return os.path.join(ROOT, "projects", arg)


def _mmss(sec):
    sec = float(sec)
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def spots(job_dir):
    """The flagged spots as (time_label, detail) pairs, newest re-listen only; [] when none/unavailable."""
    path = os.path.join(job_dir, "transcript", ".verify-cut-listens.json")
    try:
        flags = json.load(open(path, encoding="utf-8")).get("flags") or []
    except (OSError, ValueError):
        return []
    out, cur = [], None
    for raw in flags:
        line = raw.strip()
        m = re.match(r"line\s+\d+\s+@\s+([\d.]+)s", line)
        if m:
            cur = {"t": _mmss(m.group(1)), "plan": None, "cut": None}
            out.append(cur)
        elif cur is not None and line.startswith("plan says"):
            cur["plan"] = line.split(":", 1)[1].strip()
        elif cur is not None and line.startswith("cut plays"):
            cur["cut"] = line.split(":", 1)[1].strip()
    return out


def block(job_dir):
    """The review block (a string), or "" when there are no flagged spots."""
    sp = spots(job_dir)
    if not sp:
        return ""
    lines = ["Listen-check these spots before this cut goes out. The re-listen wasn't sure about them. "
             "Usually it's just a soft word it misheard, but it's where a cut goes wrong, so give each a listen:"]
    for s in sp:
        if s["plan"] and s["cut"]:
            lines.append(f'  - {s["t"]} — expected "{s["plan"]}", heard "{s["cut"]}"')
        elif s["plan"]:
            lines.append(f'  - {s["t"]} — around "{s["plan"]}"')
        else:
            lines.append(f'  - {s["t"]}')
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in sys.argv
    if not args:
        sys.exit("usage: relisten_flags.py <job> [--quiet]")
    jd = _job_dir(args[0])
    b = block(jd)
    if quiet:
        sys.exit(1 if b else 0)
    if b:
        print(b)


if __name__ == "__main__":
    main()
