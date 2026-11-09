#!/usr/bin/env python3
"""editor_errors.py — what went wrong in the visual editor, kept on this computer so a problem report can carry it.

Every editor error is written down the moment it happens, whether she noticed it or not: a page write that failed
behind "That didn't go through", a cut, look or export that broke in the background, an error in the page itself,
and the engine's plain-words refusals she was shown (they are often where a bug surfaces). One JSON line each in
_local/editor-errors.log, newest last, the last 300 kept. Nothing is ever sent anywhere: the page's "Report a
problem" button (and /report-a-problem) puts them in one file she emails.

    python3 product/editor_errors.py              the last few, in plain lines
    python3 product/editor_errors.py --report     the "Visual editor" section of a problem report (collect-report.sh)
    python3 product/editor_errors.py bundle <job> ["what happened"]    the editor's report file, path printed

Kept out: footage, transcripts, scripts and captions (a message is cut to 300 characters, a trace to its last
lines), and her home folder (written as ~).
"""
import json, os, platform, sys, time, traceback

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.environ.get("REE_EDITOR_ERRORS_LOG") or os.path.join(ROOT, "_local", "editor-errors.log")   # tests point it away
HANDOFF = os.path.join(ROOT, "_handoff")
KEEP, TRIM_AT = 300, 400
SUPPORT_EMAIL = "it@thestartupmom.com"


def _home(s):
    s = str(s or "")
    h = os.path.expanduser("~")
    if h and h not in ("/", "~"):
        s = s.replace(h, "~").replace(h.replace("\\", "/"), "~")
    return s


def _version():
    try:
        return json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("version", "?")
    except Exception:
        return "?"


def record(where, msg=None, job=None, kind="error", trace=None, **extra):
    """Write one entry. Never raises: a broken log must never break her editor. Inside an `except`, the current
    exception (and its trace) is used when msg/trace are not given."""
    try:
        exc = sys.exc_info()
        if msg is None and exc[1] is not None:
            msg = f"{type(exc[1]).__name__}: {exc[1]}"
        if trace is None and exc[1] is not None and kind == "error":
            trace = "".join(traceback.format_exception(*exc)[-6:])
        e = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "v": _version(), "kind": kind, "where": str(where)[:120],
             "job": os.path.basename(os.path.normpath(job)) if job else None, "msg": _home(msg)[:300]}
        if trace:
            e["trace"] = "\n".join(_home(trace).strip().splitlines()[-12:])[:2000]
        for k, v in extra.items():
            if v not in (None, ""):
                e[k] = _home(v)[:300]
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        _trim()
    except Exception:
        pass


def _trim():
    try:
        lines = open(LOG, encoding="utf-8").read().splitlines()
        if len(lines) > TRIM_AT:
            tmp = LOG + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines[-KEEP:]) + "\n")
            os.replace(tmp, LOG)
    except Exception:
        pass


def recent(n=15, job=None):
    try:
        lines = open(LOG, encoding="utf-8").read().splitlines()
    except OSError:
        return []
    out = []
    for l in lines:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if job is None or e.get("job") in (None, job):
            out.append(e)
    return out[-n:]


def _line(e):
    who = f" [{e['job']}]" if e.get("job") else ""
    tag = "told her" if e.get("kind") == "told" else "error"
    return f"{e.get('at')} v{e.get('v')} {tag} in {e.get('where')}{who}: {e.get('msg')}"


def _entry_md(e):
    out = [f"- {_line(e)}"]
    for k in ("tab", "phase", "browser", "page"):
        if e.get(k):
            out.append(f"  - {k}: {e[k]}")
    if e.get("trace"):
        out.append("  ```\n" + "\n".join("  " + l for l in e["trace"].splitlines()) + "\n  ```")
    return "\n".join(out)


def report_section(n=10):
    es = recent(n)
    head = "### Visual editor\n\n"
    if not es:
        return head + "- no editor errors recorded on this computer\n"
    errs = sum(1 for e in es if e.get("kind") != "told")
    return head + f"- last {len(es)} recorded ({errs} errors, {len(es) - errs} plain-words messages she was shown), newest last\n" + \
        "\n".join(_entry_md(e) for e in es) + "\n"


def _read(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def bundle(job=None, note="", page=None):
    """The editor's one report file, in _handoff/. Returns its path."""
    page = page or {}
    jd = os.path.join(ROOT, "projects", os.path.basename(os.path.normpath(job))) if job else None
    name = os.path.basename(jd) if jd else None
    lines = ["# Visual editor problem report", "",
             "Made by Report a problem in the visual editor. It holds no footage, transcript or captions.",
             f"Type /report-a-problem in the chat first: Claude fixes what it can. Send this to **{SUPPORT_EMAIL}** only if Claude says it is ready to send (product/report_gate.py).", "",
             "## What happened", "", (str(note).strip()[:2000] or "(nothing typed)"), "",
             "## This engine", "",
             f"- made: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- engine version: {_version()}",
             f"- computer: {platform.system()} {platform.release()} ({platform.machine()}), Python {platform.python_version()}"]
    try:
        import visual_editor
        lines.append(f"- editor code: {visual_editor.code_version()}")
    except Exception:
        pass
    for k, label in (("browser", "browser"), ("tab", "tab open"), ("phase", "page phase"), ("page", "page version")):
        if page.get(k):
            lines.append(f"- {label}: {_home(page[k])[:300]}")
    if jd and os.path.isdir(jd):
        rv = os.path.join(jd, "review")
        ph, fin, prob = _read(os.path.join(rv, "phase.json")) or {}, _read(os.path.join(rv, "finish.json")) or {}, _read(os.path.join(rv, "last-problem.json")) or {}
        route = (_read(os.path.join(rv, "route.json")) or {}).get("route")
        lines += ["", "## This reel", "", f"- reel: {name}", f"- road: {route or 'unset'}",
                  f"- phase: {ph.get('phase') or 'cut'}"]
        if fin:
            lines.append(f"- last export: {fin.get('state')}" + (f" ({fin.get('route')})" if fin.get("route") else "")
                         + (f": {_home(fin.get('message'))[:300]}" if fin.get("message") else ""))
        if prob:
            lines.append(f"- last message on her page: {_home(prob.get('message'))[:300]} ({prob.get('at')})")
    es = recent(20, name)
    lines += ["", "## What the editor recorded (newest last)", ""]
    lines += [_entry_md(e) for e in es] if es else ["- nothing recorded"]
    os.makedirs(HANDOFF, exist_ok=True)
    path = os.path.join(HANDOFF, f"visual-editor-report-{time.strftime('%Y%m%d-%H%M%S')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def reveal(path):
    """Show the file in Finder / Explorer, selected, so she can attach it to an email."""
    import subprocess
    if sys.platform == "darwin":
        cmd = ["open", "-R", path]
    elif os.name == "nt":
        cmd = ["explorer", "/select," + os.path.normpath(path)]
    else:
        cmd = ["xdg-open", os.path.dirname(path)]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    if a and a[0] == "--report":
        print(report_section(), end=""); sys.exit(0)
    if a and a[0] == "bundle":
        print(_home(bundle(a[1] if len(a) > 1 else None, a[2] if len(a) > 2 else ""))); sys.exit(0)
    es = recent(10)
    print("\n".join(_line(e) for e in es) if es else "No visual editor errors recorded on this computer.")
