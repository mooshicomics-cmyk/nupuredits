#!/usr/bin/env python3
"""add_to_capcut_mac.py — the preparing half of "Add to CapCut.command" on a Mac.

Used only on a Mac that refuses the engine's own Python any write in ~/Movies, where CapCut keeps its projects
(usually a security app's protected-folders shield; product/capcut_store_redirect.py finds it and builds the
drafts in projects/_capcut-staging/ instead). Apple's own /bin/mv and /bin/cp are let through, so the work is
split in two:
  • this script, run by the .command, reads CapCut's folder (reading is allowed) and PREPARES everything inside
    the engine's own folder, in _ready/: each finished project with its paths rewritten, CapCut's updated list
    of projects, and plan.txt (line 1: CapCut's folder; then one project name per line to move in);
  • the .command then moves each prepared project into CapCut with /bin/mv, backs up CapCut's list with
    /bin/cp and moves the new list in last. This script never writes into CapCut's folder.

Rules, the same as Windows' install_to_capcut.py (whose registration helpers this shares):
  • CapCut must be quit. CapCut rewrites its list of projects on exit and would drop what we add.
  • Never replace a project in CapCut. A name CapCut already has goes in as the next version ("Reel 1.2" ->
    "Reel 1.3"); the project that holds the name is never touched. That is also how a change to a draft she
    already has arrives: the engine changed a copy of it (capcut_store_redirect.stage_existing), and the copy
    goes in as the next version. A copy that was only read, or never changed, is not brought in at all.
  • Safe to run twice: a project already added (same fingerprint) is not added again.

Standard library only, so it runs on any Python she has.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8 whatever the Terminal's locale says
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import install_to_capcut as shared   # noqa: E402  (copied beside this file by write_installer)

STAGE = os.path.join(HERE, "com.lveditor.draft")
READY = os.path.join(HERE, "_ready")
REL = ("Movies", "CapCut", "User Data", "Projects", "com.lveditor.draft")
MARK = shared.MARK
STAGED_FROM = ".engine-staged-from.json"   # capcut_store_redirect.stage_existing: a copy of a draft she has
_VER_RE = re.compile(r"^(?P<base>.+?)\s+(?P<major>\d+)\.(?P<minor>\d+)$")   # draft_safety's version shape


def say(msg=""):
    print(msg, flush=True)


def real_root():
    """CapCut's own drafts folder on this Mac."""
    return os.path.join(os.path.expanduser("~"), *REL)


def capcut_running():
    """True / False, or None when the check could not run (then it refuses, like draft_safety)."""
    try:
        r = subprocess.run(["pgrep", "-x", "CapCut"], capture_output=True, text=True)
        if r.returncode > 1:
            return None
        if r.stdout.strip():
            return True
        r2 = subprocess.run(["pgrep", "-if", "CapCut.app/Contents/MacOS"], capture_output=True, text=True)
        if r2.returncode > 1:
            return None
        return bool(r2.stdout.strip())
    except Exception:
        return None


def next_free(name, taken):
    """The next '<base> N.M' above every version of this reel that is taken (draft_safety.next_version's rule,
    standard library only). An un-versioned name starts at 1.1."""
    m = _VER_RE.match(name)
    base = m.group("base") if m else name
    hi = (0, 0)
    for n in set(taken) | {name}:
        mm = _VER_RE.match(n)
        if mm and mm.group("base") == base:
            hi = max(hi, (int(mm.group("major")), int(mm.group("minor"))))
    major, minor = (hi[0], hi[1] + 1) if hi != (0, 0) else (1, 1)
    while True:
        if minor > 99:
            major, minor = major + 1, 1
        cand = f"{base} {major}.{minor}"
        if cand not in taken:
            return cand
        minor += 1


def _rename_text(text, src_folder, dst_folder):
    """Point paths inside one project at its new folder. Only a whole folder name is matched ("Reel 1.1" never
    eats the start of "Reel 1.10"): it must be followed by a slash, a quote or the end."""
    return re.sub(re.escape(src_folder) + r'(?=[/"\\]|$)', lambda _m: dst_folder, text)


def _stage_roots(staged_reg):
    """Every spelling of the staging folder the engine may have written into the project files: this folder as
    seen now, its resolved form (/tmp vs /private/tmp, a symlinked engine folder), and whatever the engine
    recorded in the staging list when it built."""
    roots = {os.path.abspath(STAGE), os.path.realpath(STAGE)}
    for e in staged_reg.get("all_draft_store", []):
        r = e.get("draft_root_path")
        if r:
            roots.add(r.rstrip("/"))
    if staged_reg.get("root_path"):
        roots.add(staged_reg["root_path"].rstrip("/"))
    return sorted(roots, key=len, reverse=True)   # longest first, so a shorter spelling never eats a longer one


def _marks(real):
    """{folder name: its install mark} for every project in CapCut's folder that this put there."""
    out = {}
    try:
        names = os.listdir(real)
    except OSError:
        return out
    for n in names:
        m = shared.load(os.path.join(real, n, MARK), None)
        if isinstance(m, dict):
            out[n] = m
    return out


def prepare():
    say("Add to CapCut")
    say("-------------")
    if sys.platform != "darwin":
        sys.exit("This only runs on a Mac. On Windows, double-click \"Add to CapCut.bat\".")
    if not os.path.isdir(STAGE):
        sys.exit("Nothing to add: there are no projects waiting in this folder.")
    running = capcut_running()
    if running is None:
        sys.exit("I could not check whether CapCut is open. Quit CapCut if it is open, then double-click this "
                 "again. If this comes back, type /report-a-problem in Claude.")
    if running:
        sys.exit("CapCut is open. Quit CapCut (Cmd+Q), then double-click this again.")

    real = real_root()
    shutil.rmtree(READY, ignore_errors=True)            # the engine's own folder, never CapCut's
    os.makedirs(os.path.join(READY, "drafts"))

    reg = shared.load(os.path.join(real, "root_meta_info.json"), None)
    started = reg is None
    if started:
        reg = shared.new_registry(real)
    staged_reg = shared.load(os.path.join(STAGE, "root_meta_info.json"), {}) or {}
    by_name = {e.get("draft_name"): e for e in staged_reg.get("all_draft_store", [])}
    roots = _stage_roots(staged_reg)
    marks = _marks(real)
    try:
        in_capcut = set(os.listdir(real))
    except OSError:
        in_capcut = set()
    listed = {x.get("draft_name") for x in reg.get("all_draft_store", [])}
    staged_names = [n for n in sorted(os.listdir(STAGE))
                    if os.path.isdir(os.path.join(STAGE, n)) and not n.startswith((".", "_"))
                    and shared.draft_json(os.path.join(STAGE, n))]
    taken = set(in_capcut) | listed | set(staged_names)

    moves, relisted, renamed = [], [], []
    for name in staged_names:
        src = os.path.join(STAGE, name)
        staged_fp = shared.fingerprint(src)
        copied = shared.load(os.path.join(src, STAGED_FROM), None)
        if isinstance(copied, dict) and (copied.get("reference") or copied.get("copied_fp") == staged_fp):
            continue          # a copy of hers the engine only read, or never changed: nothing new to bring in
        already = [n for n, m in marks.items() if m.get("source", n) == name and m.get("staged") == staged_fp]
        if already:
            target = already[0]
            if target in listed:
                continue                                      # already in CapCut, nothing new
            dst = os.path.join(real, target)
            if not shared.draft_json(dst):
                continue
            relisted.append(target)                           # in the folder, lost from the list: list it again
            e = shared.registry_entry(None, target, dst, real)
            shared.put_on_top(reg, e, target)
            continue
        # A name CapCut already has (a folder or a list entry) is never reused: next version instead.
        target = name if name not in in_capcut and name not in listed else next_free(name, taken)
        taken.add(target)
        if target != name:
            renamed.append((name, target))
        dst = os.path.join(real, target)

        def rewrite(text, name=name, dst=dst):
            for r in roots:
                text = _rename_text(text, f"{r}/{name}", dst)
            for r in roots:
                text = shared.rewrite_text(text, r, real)
            return text

        work = os.path.join(READY, "drafts", target)
        shutil.copytree(src, work)
        if os.path.exists(os.path.join(work, STAGED_FROM)):
            os.remove(os.path.join(work, STAGED_FROM))    # the engine's own note; CapCut's copy does not need it
        for dirpath, _dirs, files in os.walk(work):
            for f in files:
                if not f.endswith(".json") or f == MARK:
                    continue
                fp = os.path.join(dirpath, f)
                try:
                    with open(fp, encoding="utf-8") as fh:
                        t = fh.read()
                except (UnicodeDecodeError, OSError):
                    continue
                n = rewrite(t)
                if target != name and f == "draft_meta_info.json":
                    try:
                        meta = json.loads(n)
                        if isinstance(meta, dict) and "draft_name" in meta:
                            meta["draft_name"] = target
                            n = json.dumps(meta, ensure_ascii=False)
                    except ValueError:
                        pass
                if n != t:
                    with open(fp, "w", encoding="utf-8") as fh:
                        fh.write(n)
        with open(os.path.join(work, MARK), "w", encoding="utf-8") as fh:
            json.dump({"staged": staged_fp, "installed": shared.fingerprint(work), "source": name,
                       "at": time.strftime("%Y-%m-%d %H:%M")}, fh)
        e = shared.registry_entry(by_name.get(name), target, dst, real, rewrite)
        e["draft_name"] = target
        shared.put_on_top(reg, e, target)
        moves.append(target)

    with open(os.path.join(READY, "plan.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(real + "\n")
        for t in moves:
            fh.write(t + "\n")
    if moves or relisted:
        if started:
            reg["draft_ids"] = len(reg["all_draft_store"])
        with open(os.path.join(READY, "root_meta_info.json"), "w", encoding="utf-8") as fh:
            json.dump(reg, fh, ensure_ascii=False)
    for old, new in renamed:
        say(f"  CapCut already has a project called \"{old}\", so this one goes in as \"{new}\". Yours is untouched.")
    for t in relisted:
        say(f"  ~ listed  {t} (it was in CapCut's folder but missing from its list)")
    if not moves and not relisted:
        say("Everything here is already in CapCut. Nothing to do.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["prepare"]:
        sys.exit(prepare())
    print("Double-click \"Add to CapCut.command\" in this folder instead.", file=sys.stderr)
    sys.exit(2)
