#!/usr/bin/env python3
"""draft_safety.py — LOCKED fail-safe for CapCut drafts: NEVER replace a draft with a rebuild.

The creator's hand-edits (fonts, effects, layout tweaks) live ONLY inside the CapCut draft, and CapCut
keeps NO version history and NO autosave. So a rebuild that deletes-and-recreates a draft destroys those
edits irreversibly. This module makes the safe path the only path.

Two allowed ways to apply a change to a draft the creator may have opened — NEVER a replace:
  1. LAYER on top       — add the new element additively to the existing draft (don't rebuild it).
  2. DUPLICATE + rebuild — copy to the next version name, build the change into the COPY.

New versions follow the sequence  <base> 1.1, <base> 1.2, <base> 1.3 ...  (never reuse a name).

Primitives:
  • next_version(base)              -> next unused '<base> N.M' name
  • refuse_replace(name)            -> HARD raise if a build would land on an existing draft
  • record_build(name)              -> snapshot a draft right after building (enables edit detection)
  • edited_in_capcut(name)          -> True if the draft changed since record_build (creator edited it)
  • list_versions(base)             -> the reel's version lineage, oldest -> newest
  • rolling_delete_candidates(base) -> oldest versions beyond KEEP_VERSIONS (ASK before deleting any)
  • recycle(name)                   -> REVERSIBLE removal to .recycle_bin (stashes the exact registry entry)
  • restore_draft(name)             -> reverse of recycle: folder + exact registry entry back (Bug #7/#7a)
  • duplicate_draft(name[,new])     -> copy to the next version + register the copy (DUPLICATE + rebuild path)

Never auto-delete. When rolling_delete_candidates is non-empty, ASK the creator whether to prune.
"""
import os, re, json, sys, time, hashlib, shutil, glob, subprocess

# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:   # loaded by file path (tests, other skills)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CAP = __import__("capcut_store_redirect").drafts_root()
KEEP_VERSIONS = 3
# Buyer-facing: Cmd+Q does not exist on Windows.
_QUIT_HINT = "right-click its taskbar icon and Close, or use Task Manager" if os.name == "nt" else "Cmd+Q"
_VER_RE = re.compile(r"^(?P<base>.+?)\s+(?P<major>\d+)\.(?P<minor>\d+)$")


# ---- which file CapCut calls a draft's timeline JSON ----
# CapCut names this file differently by PLATFORM, not by version: macOS writes draft_info.json,
# Windows writes draft_content.json. Measured 2026-09-15 — CapCut 9.4.0 on this Mac has all 158
# drafts in its registry pointing at draft_info.json, while a Windows CapCut 9.2.0 pointed at
# draft_content.json. The NEWER build uses the OLD name, so a version check would be the wrong fix.
# Everything that touches a draft's JSON goes through here instead of hardcoding either name.
DRAFT_JSON_NAMES = ("draft_info.json", "draft_content.json")
_DEFAULT_DRAFT_JSON = "draft_content.json" if os.name == "nt" else "draft_info.json"


def _registry_draft_json_name():
    """What this machine's own CapCut registry calls it. Used for a draft that isn't on disk yet."""
    try:
        m = json.load(open(os.path.join(CAP, "root_meta_info.json"), encoding="utf-8"))
        for d in m.get("all_draft_store", []):
            b = os.path.basename(d.get("draft_json_file") or "")
            if b in DRAFT_JSON_NAMES:
                return b
    except Exception:
        pass
    return None


def draft_json_name(draft_dir=None):
    """The basename CapCut uses for this draft's timeline JSON. Checks what EXISTS before assuming.

    Candidate ORDER matters: a PC that ran an older engine can hold BOTH files — the old engine wrote
    the macOS name while CapCut itself wrote the Windows one — so picking by list order would hand back
    the stale file CapCut never reads. Ask this machine's own CapCut first (the registry), then this
    platform's name, and only then the other one."""
    if draft_dir:
        preferred = _registry_draft_json_name() or _DEFAULT_DRAFT_JSON
        order = [preferred] + [n for n in DRAFT_JSON_NAMES if n != preferred]
        for n in order:
            if os.path.exists(os.path.join(draft_dir, n)):
                return n
        return preferred
    return _registry_draft_json_name() or _DEFAULT_DRAFT_JSON


def draft_json(draft_dir):
    """Full path to this draft's timeline JSON, whatever this CapCut named it."""
    return os.path.join(draft_dir, draft_json_name(draft_dir))


def draft_json_copies(draft_dir, require=True):
    """EVERY timeline JSON CapCut reads for one draft: the top-level file + each Timelines cache copy.

    Raises when it finds none. A cache verifier that silently checks ZERO files reports 'all clear'
    while it is actually blind, which is how a wrong-filename assumption turned a fail-safe into a
    rubber stamp on Windows. Loud beats quiet here."""
    out = []
    for n in DRAFT_JSON_NAMES:
        top = os.path.join(draft_dir, n)
        if os.path.exists(top):
            out.append(top)
        out += sorted(glob.glob(os.path.join(draft_dir, "Timelines", "*", n)))
    if require and not out:
        raise RuntimeError(
            f"No CapCut timeline JSON found in {draft_dir}. Looked for {' or '.join(DRAFT_JSON_NAMES)}. "
            "Refusing to report a clean check against zero files."
        )
    return out


def draft_jsons_under(root, depth="*"):
    """Every draft's timeline JSON under a drafts ROOT, across both platform filenames."""
    out = []
    for n in DRAFT_JSON_NAMES:
        out += glob.glob(os.path.join(root, depth, n))
    return sorted(out)


def media_slot(target, source):
    """Where `source` goes when it is copied to `target` inside a draft, as (path, already_there). A file
    already at that name stands in for it only when it IS the same file (same inode, or the same bytes). A
    different file there is never reused (two layers both named l09-editor.mov, a graphic and her cutout, once
    played the same picture) and never overwritten (another clip may be playing it): the copy takes the next
    free name instead, stem-2.ext, stem-3.ext, and so on."""
    import filecmp
    stem, ext = os.path.splitext(str(target))
    path, n = str(target), 2
    while os.path.exists(path):
        try:
            if os.path.samefile(path, source) or (os.path.getsize(path) == os.path.getsize(source)
                                                  and filecmp.cmp(path, source, shallow=False)):
                return path, True
        except OSError:
            pass
        path, n = f"{stem}-{n}{ext}", n + 1
    return path, False

CACHE_ROOT = os.path.join(os.path.dirname(os.path.dirname(CAP)), "Cache")
_PRERENDER_DIRS = ("prerender", "segmentPrerenderCache")


def draft_timeline_ids(draft_dir):
    """The internal timeline UUIDs CapCut assigned this draft (the Timelines/<uuid> folder names)."""
    tl = os.path.join(draft_dir, "Timelines")
    try:
        return [n for n in os.listdir(tl) if os.path.isdir(os.path.join(tl, n))]
    except OSError:
        return []


def clear_draft_caches(draft_dir, timeline_ids=None):
    """Drop CapCut's regenerable caches for ONE draft, so a replaced asset actually shows on reopen.

    Clearing Timelines/ alone is NOT enough. CapCut also keeps a per-draft PRERENDER cache keyed by the
    draft's internal timeline UUID (Cache/prerender/<uuid>, Cache/segmentPrerenderCache/<uuid>) and does
    not invalidate it when the source file on disk is overwritten — so the creator fixes a graphic, re-opens,
    and still sees the old one. Measured on Windows; the same folders exist on macOS.

    Scoped by UUID on purpose: only this draft's entries are removed, never the shared cache. Pass
    timeline_ids when Timelines/ is about to be (or has been) deleted, since the ids live in its folder names.
    Returns the list of paths removed. Caches only — nothing here is the creator's work."""
    ids = timeline_ids if timeline_ids is not None else draft_timeline_ids(draft_dir)
    removed = []
    for uid in ids:
        for sub in _PRERENDER_DIRS:
            d = os.path.join(CACHE_ROOT, sub, uid)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                removed.append(d)
    return removed


# ---- CapCut-must-be-quit guard (durability of ANY draft write) ----
# CapCut holds its OWN in-memory model of a draft while it is open, built when it opened the file. Anything
# the engine writes to that draft's JSON on disk while CapCut is open — a finalize, or a self-contained
# "layer on top" add (an SFX track, an overlay, a hook) — is NOT in CapCut's model, so CapCut OVERWRITES the
# file with its own model on its next save and the engine's change is silently GONE, with no error. This is
# the inverse of the never-replace rule: CapCut wiping an engine add, instead of a rebuild wiping her edits.
# So every draft write must happen with CapCut QUIT. The engine used to only DOCUMENT this ("CapCut must be
# quit before finalize"); this makes it ENFORCED, on finalize AND every layer-on-top writer.
def capcut_running():
    """True if CapCut is running, False if it is definitely not, and None when the check COULD NOT RUN.

    The None matters. This guard is what stops a draft write from landing while CapCut has the file open,
    which is how a creator's hand edits get silently overwritten. Both branches used to answer False when
    the process check itself failed, and False means "go ahead and write" — so on any machine where
    `pgrep` or `tasklist` was missing or blocked, the safety net quietly reported all clear and the write
    went through. Same failure shape as a verifier that passes because it checked nothing. Unknown is now
    its own answer, and require_capcut_quit() refuses on it instead of assuming the happy case."""
    if os.name == "nt":
        try:
            # Bytes, never text: tasklist prints in the console's OEM codepage (cp850 or cp1252 on a Spanish,
            # French or German Windows), and with PYTHONUTF8=1 a text decode of it raised UnicodeDecodeError,
            # so every draft write was refused as "could not tell whether CapCut is open". The name is ASCII.
            r = subprocess.run(["tasklist"], capture_output=True)
            if r.returncode != 0:
                return None
            return b"CapCut.exe" in (r.stdout or b"")
        except Exception:
            return None
    try:
        r = subprocess.run(["pgrep", "-x", "CapCut"], capture_output=True, text=True)
        # pgrep exits 1 for "no match" (a real answer) and >1 for a genuine failure.
        if r.returncode > 1:
            return None
        if r.stdout.strip():
            return True
        # catch the main app launched under its bundle path even if the short name differs
        r2 = subprocess.run(["pgrep", "-if", "CapCut.app/Contents/MacOS"], capture_output=True, text=True)
        if r2.returncode > 1:
            return None
        return bool(r2.stdout.strip())
    except Exception:
        return None


class CapCutOpen(RuntimeError):
    """The CapCut-must-be-quit refusal. A subclass of RuntimeError so every existing `except RuntimeError`
    still catches it, and so it can be told apart from a real bug.

    Why it has its own class: this refusal is the guard WORKING, but a script that ends on an uncaught
    exception prints "Exit code 1" and a full stack trace, which reads exactly like a crash — a creator
    who sees it has no way to know the engine did the right thing and is waiting for her. The hook below
    prints the sentence and nothing else. Anything that is NOT this class still gets its whole traceback,
    because a real fault should be loud."""


def _install_refusal_hook():
    """Show an expected refusal as the sentence it is, not as a stack trace. A real bug keeps its traceback."""
    prev = sys.excepthook

    def hook(exc_type, exc, tb):
        if isinstance(exc, CapCutOpen):
            print(f"\n{exc}\n", file=sys.stderr)
            return
        prev(exc_type, exc, tb)

    sys.excepthook = hook


_install_refusal_hook()


def _under(path, root):
    """True when `path` is `root` or inside it. Case-insensitive where the file system is (Windows)."""
    try:
        p, r = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
        return os.path.commonpath([p, r]) == r
    except (ValueError, TypeError):      # different drives on Windows, or no path at all
        return False


def capcut_never_reads(path=None):
    """True only when a write to `path` (a draft folder or a drafts root; default: this process's drafts root,
    CAP) lands in the engine's staging folder, projects/_capcut-staging/, which CapCut never opens.

    Why that matters: the CapCut-must-be-quit guard protects ONE thing, a draft CapCut has loaded and will save
    its own copy over. A Microsoft Store Claude app builds every draft in the staging folder instead
    (capcut_store_redirect.py), and the only way one reaches CapCut is "Add to CapCut", which keeps
    refusing while CapCut runs. So an open CapCut cannot touch a staging build, and refusing it only blocked
    her for nothing (a stuck CapCut.exe that no restart cleared blocked every build).

    Strict on purpose. With no path given, BOTH this module's root and a fresh drafts_root() must be the
    staging folder: every writer takes its root from the same drafts_root() (or from draft_safety.CAP), so
    the two only differ if something changed the environment mid-run, and then the answer is "real folder".
    Anything inside one of CapCut's own drafts folders is never "never reads", whatever else is true."""
    try:
        import capcut_store_redirect as _r
        stage = _r.staging_root()
        reals = [_r.real_root(), os.path.expanduser("~/Movies/" + _r.REL_DRAFTS)]
        targets = [path] if path else [CAP, _r.drafts_root()]
    except Exception:
        return False
    for t in targets:
        if not t or not _under(t, stage):
            return False
        if any(_under(t, real) for real in reals if os.path.isabs(real)):
            return False
    return True


_said_staging = []


def _restart_note():
    """When the SAME CapCut processes (same id AND same start time) are still running as at the last refusal,
    the computer has not restarted since then, whatever it looked like. Say so plainly inside the refusal (the
    refusal itself never changes): a CapCut that a "restart" did not clear usually means Windows only shut down halfway (Fast
    Startup) or never restarted. Windows only; the guard refuses either way. Remembered per machine in
    _local/pivots.json (fallbacks.remember). Never raises; '' when there is nothing to say."""
    if os.name != "nt":
        return ""
    try:
        import install_to_capcut
        procs = install_to_capcut.capcut_processes()
        if not procs or any(not p.get("start") for p in procs):
            return ""          # no start time, no claim: a reused process id alone proves nothing
        now = sorted(f"{p['pid']}@{p['start']}" for p in procs)
        import fallbacks
        before = fallbacks.remembered("capcut.open-processes")
        fallbacks.remember("capcut.open-processes", now, why="CapCut was running when a draft write was refused")
        if before and sorted(before) == now:
            return (" This is the same CapCut that was running the last time I checked (same process, same start "
                    "time), so this computer has not restarted since then. If you restarted it, Windows did not "
                    "fully restart: use Start > Power > Restart (Shut down keeps part of Windows running when Fast "
                    "Startup is on), or hold the power button until the computer turns off, then turn it back on.")
    except Exception:
        pass
    return ""


def require_capcut_quit(action="write this draft", draft=None):
    """Raise a clear, buyer-friendly error if CapCut is open. Call BEFORE any draft write — finalize AND any
    raw-JSON layer-on-top add — so an out-of-band change can never be silently dropped by CapCut's next save.
    Escape hatch: set CAPCUT_ALLOW_OPEN=1 to bypass (only when you KNOW the draft is not the open one).

    `draft` (optional) is the draft folder or drafts root being written; without it, this process's drafts root.
    A write into the engine's staging folder goes ahead with CapCut open (capcut_never_reads): CapCut never
    reads that folder, and the "Add to CapCut" step is what keeps requiring CapCut closed. CapCut's own drafts
    folder is never relaxed."""
    if os.environ.get("CAPCUT_ALLOW_OPEN") == "1":
        return
    state = capcut_running()
    if state is not False and capcut_never_reads(draft):
        if state and not _said_staging:
            _said_staging.append(1)
            print("  CapCut is open, which is fine for this step: the project builds in the engine's staging "
                  "folder, which CapCut never reads. Close CapCut before you double-click \"Add to CapCut\" in that "
                  "folder.")
        return
    if state is None:
        raise CapCutOpen(
            f"I could not tell whether CapCut is open on this machine, so I am not going to {action}. "
            f"Writing while CapCut is open silently throws the change away, and guessing is exactly how "
            f"that happens. Quit CapCut fully ({_QUIT_HINT}), then tell me to go again. If you are certain "
            f"CapCut is closed, set CAPCUT_ALLOW_OPEN=1 to override.")
    if state:
        raise CapCutOpen(
            f"CapCut is open — quit it fully ({_QUIT_HINT}) before I {action}. While CapCut is open it rewrites the "
            f"draft on its next save and silently drops anything I add out of band (a layered sound, overlay, "
            f"or the whole build). Quit CapCut, then tell me to go again." + _restart_note())


def _roots():
    """Every folder her drafts can be in: CAP, plus CapCut's own folder (read only) on a Mac that keeps the
    engine out of Movies (capcut_store_redirect.lookup_roots). Names are counted across all of them, so a new
    version is numbered above the one she already has in CapCut, not just above the staged copies."""
    try:
        return __import__("capcut_store_redirect").lookup_roots(CAP)
    except Exception:
        return [CAP]


def _drafts():
    names = []
    for root in _roots():
        try:
            names += [n for n in os.listdir(root)
                      if os.path.isdir(os.path.join(root, n)) and not n.startswith(".") and n not in names]
        except FileNotFoundError:
            pass
    return names


def _draft_dir(name):
    """Where the draft called `name` is, for reading (CAP first). CAP's path when it is nowhere."""
    for root in _roots():
        if os.path.isdir(os.path.join(root, name)):
            return os.path.join(root, name)
    return os.path.join(CAP, name)


def discard_unfinished(path):
    """Delete a half-built draft folder that a REFUSED finalize created, so a refused build leaves nothing
    behind. Returns True if it removed something.

    Why this exists: finalize renames the VectCut temp folder onto the final draft name BEFORE it runs its
    validation, so a guard that refuses afterwards leaves an unregistered folder sitting on that name. It is
    invisible in CapCut (never registered), but it OWNS the name — so fixing the problem and rebuilding to
    the same name then hits the never-replace refusal, and the creator is told their own unbuilt draft is
    work they must not overwrite. Two confusing errors for one real one.

    This is the one deletion the never-replace rule does not cover, and the conditions are deliberately
    narrow: the folder must sit directly under the drafts root, must NOT be registered in the drafts grid
    (registration is the last thing finalize does, so anything registered is a real, possibly hand-edited
    draft and is never touched here), and must not be the recycle bin. Anything else is refused, loudly."""
    path = os.path.abspath(path)
    parent, base = os.path.dirname(path), os.path.basename(path)
    if not os.path.isdir(path):
        return False
    if os.path.abspath(parent) != os.path.abspath(CAP) or base.startswith("."):
        raise RuntimeError(f"discard_unfinished refused {path!r}: not a draft folder directly under {CAP!r}")
    try:
        meta = json.load(open(os.path.join(CAP, "root_meta_info.json"), encoding="utf-8"))
        for row in meta.get("all_draft_store", []):
            if str(row.get("draft_name")) == base or os.path.abspath(str(row.get("draft_fold_path") or "")) == path:
                raise RuntimeError(
                    f"discard_unfinished REFUSED {base!r}: it is registered in the drafts grid, so it is a "
                    f"real draft that may carry in-app edits. Never delete one — build a new version.")
    except FileNotFoundError:
        pass
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.isdir(path)


def base_of(name):
    """'Reel 1.3' -> 'Reel'; an un-versioned name is its own base."""
    m = _VER_RE.match(name)
    return m.group("base") if m else name


def _ver_key(name):
    """Sort key: by version number when present (un-suffixed base sorts first as 0.0), then by folder mtime
    as a tie-break. So 'oldest' means lowest version number, not merely least-recently-touched."""
    m = _VER_RE.match(name)
    major, minor = (int(m.group("major")), int(m.group("minor"))) if m else (0, 0)
    try:
        mt = os.path.getmtime(os.path.join(CAP, name))
    except OSError:
        mt = 0.0
    return (major, minor, mt)


def list_versions(base):
    """Every draft in `base`'s lineage (the un-suffixed base + its N.M versions), oldest -> newest by
    version number (then mtime)."""
    out = [n for n in _drafts() if n == base or base_of(n) == base]
    return sorted(out, key=_ver_key)


def _recycled_versions(base):
    """Names in `base`'s lineage that currently sit in .recycle_bin. A recycled version number must STILL be
    counted as used, or next_version would hand a recycled name back out and REUSE it (locked rule: never
    reuse a name). Bug: a reel whose 1.1-1.3 were recycled got the next build named 1.1 again."""
    binroot = os.path.join(CAP, ".recycle_bin")
    out = []
    if os.path.isdir(binroot):
        for d in os.listdir(binroot):
            i = d.find(_RECYCLE_TAG)                       # strip " [recycled <unix>]" -> the original name
            nm = d[:i] if i != -1 else d
            if nm == base or base_of(nm) == base:
                out.append(nm)
    return out


def next_version(base):
    """Next unused '<base> N.M' name, ALWAYS strictly ABOVE the highest version EVER used for this reel —
    counting live drafts AND anything in the recycle bin — so a recycled name is never reused (locked rule).
    Increments the minor (1.6 -> 1.7); rolls the major at .99. Never returns an existing LIVE draft name."""
    live = _drafts()
    lineage = [n for n in live if n == base or base_of(n) == base] + _recycled_versions(base)
    hi = (0, 0)
    for n in lineage:
        m = _VER_RE.match(n)
        if m:
            hi = max(hi, (int(m.group("major")), int(m.group("minor"))))
    major, minor = (hi[0], hi[1] + 1) if hi != (0, 0) else (1, 1)
    if minor > 99:
        major, minor = major + 1, 1
    existing = set(live)                                   # final guard: never collide with a live draft
    while f"{base} {major}.{minor}" in existing:
        minor += 1
        if minor > 99:
            major, minor = major + 1, 1
    return f"{base} {major}.{minor}"


def refuse_replace(name):
    """HARD GUARD: raise if `name` already exists. A build there would wipe in-app edits."""
    if any(os.path.isdir(os.path.join(root, name)) for root in _roots()):
        raise RuntimeError(
            f"REFUSING to replace existing CapCut draft {name!r}: a rebuild would wipe the creator's "
            f"in-app edits (CapCut has no version history). Build to {next_version(base_of(name))!r} "
            f"instead, or layer the change on top of the existing draft.")


# ---- in-app edit detection: snapshot the draft right after building, compare later ----
def _snap_file():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".draft-snapshots.json")


def _draft_hash(name):
    p = draft_json(_draft_dir(name))
    return hashlib.sha1(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None


def record_build(name):
    """Snapshot a draft's state right after the engine builds it, so later edits are detectable."""
    f = _snap_file()
    s = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    s[name] = {"hash": _draft_hash(name), "t": time.time()}
    json.dump(s, open(f, "w", encoding="utf-8"))


def edited_in_capcut(name, why=False):
    """True ONLY when the draft GENUINELY changed since the last record_build (the creator edited it in
    CapCut — a real 'hash-changed'). 'no snapshot' means UNKNOWN, not edited: it must NOT report True, or a
    freshly-duplicated, never-opened draft cries wolf and trains everyone to ignore the real alarm (§2.9).

    Pass why=True to get (edited, reason) so the state is DIAGNOSABLE. Reasons: 'no-draft' (no file),
    'no-snapshot' (never record_build'd → UNKNOWN, treated as NOT edited — a fresh duplicate already gets a
    snapshot via record_build, so this only means a draft the engine never built), 'unchanged',
    'hash-changed' (real edit, or something rewrote the draft JSON after record_build; the reason includes
    how long after the snapshot the file changed, which points at who rewrote it). Callers must only advise a
    version bump on 'hash-changed', never on 'no-snapshot'. Set DRAFT_SAFETY_DEBUG=1 to print the reason."""
    import sys
    f = _snap_file()
    s = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    cur = _draft_hash(name)
    snap = s.get(name, {})
    prev = snap.get("hash")
    if cur is None:
        edited, reason = False, "no-draft"
    elif prev is None:
        edited, reason = False, "no-snapshot"      # UNKNOWN, not edited — never cry wolf on a fresh duplicate (§2.9)
    elif cur == prev:
        edited, reason = False, "unchanged"
    else:
        dt = time.time() - snap.get("t", 0)
        p = draft_json(_draft_dir(name))
        try: since = time.time() - os.path.getmtime(p)
        except OSError: since = -1
        edited, reason = True, f"hash-changed (snapshot {dt:.1f}s ago; file last written {since:.1f}s ago)"
    if os.environ.get("DRAFT_SAFETY_DEBUG") == "1":
        print(f"[draft_safety] edited_in_capcut({name!r}) -> {edited} · {reason}", file=sys.stderr)
    return (edited, reason) if why else edited


# ---- rolling delete (ASK first; never auto-delete; RECYCLE, never hard-delete) ----
def rolling_delete_candidates(base, keep=KEEP_VERSIONS):
    """Oldest versions beyond `keep` for this reel lineage — what a rolling delete WOULD prune.
    Returns [] at/under the limit. The caller MUST ask the creator before recycling any of these."""
    v = list_versions(base)
    return v[:-keep] if len(v) > keep else []


_RECYCLE_TAG = " [recycled "     # folder name suffix: "<name> [recycled <unix>]" (literal [ ] — NOT a glob)
_ENTRY_SIDECAR = ".root_meta_entry.json"   # stashed inside a recycled folder: the exact registry entry


def fresh_timeline_id(draft_dir):
    """Give a COPIED draft its own timeline id. CapCut files its preview cache under this id, so a copy that kept
    its original's showed the original's frames (a fixed graphic still drawn the old way). The id lives in the
    draft JSON, Timelines/project.json and the Timelines/<id> folder name; all are moved together. Copies only,
    never a draft she has open (callers hold the CapCut-quit rule)."""
    import uuid as _uuid
    old = None
    try:
        old = json.load(open(os.path.join(draft_dir, "Timelines", "project.json"), encoding="utf-8")).get("main_timeline_id")
    except Exception:
        pass
    if not old:
        try:
            old = json.load(open(draft_json(draft_dir), encoding="utf-8")).get("id")
        except Exception:
            return None
    if not old:
        return None
    new = str(_uuid.uuid4()).upper()
    tl = os.path.join(draft_dir, "Timelines")
    if os.path.isdir(os.path.join(tl, old)):
        try:                                       # Windows refuses a rename while anything holds the folder: then the
            os.rename(os.path.join(tl, old), os.path.join(tl, new))   # copy keeps its id (shared preview cache) rather
        except OSError:                            # than an id that no longer matches its own folder
            return None
    for root, _dirs, files in os.walk(draft_dir):
        for f in files:
            if f.endswith((".json", ".bak", ".tmp")) or f in ("draft_settings", "draft.extra"):
                p = os.path.join(root, f)
                try:
                    s = open(p, encoding="utf-8").read()
                except Exception:
                    continue
                if old in s:
                    tmp = p + ".tlid"
                    open(tmp, "w", encoding="utf-8").write(s.replace(old, new))
                    os.replace(tmp, p)
    return new


def duplicate(name, new_name=None):
    """Copy a draft to a NEW versioned name (leaves the original 100% untouched), fix its internal
    self-path references, and register it in the draft list. Returns the new name. This is the safe way to
    apply a rebuild-scale change: build into the COPY, never the original."""
    src = os.path.join(CAP, name)
    if not os.path.isdir(src):
        raise FileNotFoundError(src)
    new_name = new_name or next_version(base_of(name))
    dst = os.path.join(CAP, new_name)
    if os.path.isdir(dst):
        raise RuntimeError(f"{new_name!r} already exists")
    shutil.copytree(src, dst)
    fresh_timeline_id(dst)                     # its own preview cache, never the original's frames
    # rewrite absolute self-references (old folder path -> new) in every json (placeholder-token paths are
    # folder-independent and left alone)
    for f in glob.glob(f"{dst}/*.json") + draft_json_copies(dst, require=False):
        s = open(f, encoding="utf-8").read()
        if src in s:
            open(f, "w", encoding="utf-8").write(s.replace(src, dst))
    mp = f"{dst}/draft_meta_info.json"
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8")); m["draft_name"] = new_name
        json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
    rp = os.path.join(CAP, "root_meta_info.json")
    if os.path.exists(rp):
        r = json.load(open(rp, encoding="utf-8")); store = r.get("all_draft_store", [])
        base_e = next((e for e in store if e.get("draft_name") == name), dict(store[0]) if store else {})
        now = int(time.time()) * 1_000_000
        e = dict(base_e); e.update(draft_name=new_name, draft_fold_path=dst,
                                   draft_json_file=draft_json(dst), draft_cover=f"{dst}/draft_cover.jpg",
                                   tm_draft_create=now, tm_draft_modified=now)
        r["all_draft_store"] = [x for x in store if x.get("draft_name") != new_name]
        r["all_draft_store"].insert(0, e)
        json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
    record_build(new_name)
    return new_name


def recycle(name):
    """REVERSIBLE removal: MOVE a draft into the CapCut .recycle_bin (never hard-delete) AND stash the exact
    root_meta_info registry entry that made CapCut show it, as a sidecar inside the recycled folder. Also drop
    that entry from root_meta_info so the draft leaves the grid. Use ONLY after the creator says yes to a
    rolling delete. Returns the recycle path.

    Why the sidecar (Bug #7): CapCut's drafts grid is driven by the root_meta_info registry, NOT the
    filesystem. The old recycle() moved the folder (files survived) but DISCARDED the registry entry — so
    even moving the folder back never made the draft reappear, because the entry could not be reconstructed.
    Stashing the exact entry makes restore_draft() a true byte-for-byte round trip. Never rm/rmtree a draft."""
    require_capcut_quit("recycle this draft")
    src = os.path.join(CAP, name)
    if not os.path.isdir(src):
        raise FileNotFoundError(src)
    binroot = os.path.join(CAP, ".recycle_bin")
    os.makedirs(binroot, exist_ok=True)
    dst = os.path.join(binroot, f"{name}{_RECYCLE_TAG}{int(time.time())}]")
    os.rename(src, dst)
    rp = os.path.join(CAP, "root_meta_info.json")
    removed = None
    if os.path.exists(rp):
        try:
            r = json.load(open(rp, encoding="utf-8"))
            kept = []
            for e in r.get("all_draft_store", []):
                if e.get("draft_name") == name:
                    if removed is None:
                        removed = e          # stash the EXACT entry (first match); drop every entry by this name
                    continue
                kept.append(e)
            r["all_draft_store"] = kept
            json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    try:   # sidecar = the exact removed entry, so restore_draft can re-register the draft byte-for-byte
        json.dump({"draft_name": name, "entry": removed},
                  open(os.path.join(dst, _ENTRY_SIDECAR), "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    # Drop it from capcut_front's keep-on-top list too. A recycled draft left pinned still occupies one of
    # the five slots ensure() re-applies, so dead names silently crowd real drafts out of the top of the
    # list — which puts the creator right back to hunting for what was just built.
    try:
        import capcut_front
        st = capcut_front._state()
        keep = [n for n in st.get("keep_on_top", []) if n != name]
        if keep != st.get("keep_on_top", []):
            st["keep_on_top"] = keep
            capcut_front._save_state(st)
    except Exception:
        pass
    return dst


def _find_recycled(name):
    """Newest recycled folder for `name`, matched with plain listdir + literal startswith/endswith — NEVER
    glob. The folder name embeds literal '[' and ']' ("<name> [recycled <unix>]"), which glob would read as
    character-class wildcards and silently match zero files (Bug #7a: that shipped a 'restore' that couldn't
    find what recycle() had just written). Returns the absolute path, or None."""
    binroot = os.path.join(CAP, ".recycle_bin")
    if not os.path.isdir(binroot):
        return None
    pref, suf = f"{name}{_RECYCLE_TAG}", "]"
    hits = [d for d in os.listdir(binroot)
            if d.startswith(pref) and d.endswith(suf) and os.path.isdir(os.path.join(binroot, d))]
    if not hits:
        return None
    # newest by the trailing unix timestamp (fall back to mtime if it doesn't parse)
    def _ts(d):
        try: return int(d[len(pref):-1])
        except ValueError:
            try: return int(os.path.getmtime(os.path.join(binroot, d)))
            except OSError: return 0
    return os.path.join(binroot, max(hits, key=_ts))


def _reconstruct_entry(name, folder):
    """Best-effort registry entry for a draft recycled BEFORE the sidecar existed (no .root_meta_entry.json).
    Clones the shape of any current registry entry and rewrites the name / id / path fields from the draft's
    own draft_meta_info.json. Untested against a real pre-fix draft (QA Bug #7 note) — the sidecar path is
    the trustworthy one; this only keeps an old recycle recoverable at all."""
    rp = os.path.join(CAP, "root_meta_info.json")
    template = None
    if os.path.exists(rp):
        try:
            store = json.load(open(rp, encoding="utf-8")).get("all_draft_store", [])
            if store: template = dict(store[0])
        except Exception:
            pass
    if template is None:
        template = {"draft_name": name}
    e = dict(template)
    draft_id = ""
    try:
        draft_id = json.load(open(os.path.join(folder, "draft_meta_info.json"), encoding="utf-8")).get("draft_id", "")
    except Exception:
        pass
    restored_fold = os.path.join(CAP, name)
    e["draft_name"] = name
    if draft_id:
        e["draft_id"] = draft_id
    e["draft_root_path"] = CAP
    e["draft_fold_path"] = restored_fold
    e["draft_json_file"] = draft_json(restored_fold)
    e["draft_cover"] = os.path.join(restored_fold, "draft_cover.jpg")
    return e


def restore_draft(name):
    """Reverse recycle(): move the recycled folder back to CAP/<name> and re-register its exact root_meta_info
    entry (from the sidecar), so CapCut shows the draft again. Refuses to overwrite a LIVE draft of the same
    name. Falls back to a best-effort reconstructed entry for a draft recycled before the sidecar existed.
    Returns the restored path. (Bug #7 / #7a)"""
    require_capcut_quit("restore this draft")
    dest = os.path.join(CAP, name)
    if os.path.isdir(dest):
        raise RuntimeError(
            f"REFUSING to restore {name!r}: a live draft of that name already exists at {dest!r}. "
            f"Rename or recycle the live one first, then restore.")
    folder = _find_recycled(name)
    if not folder:
        raise FileNotFoundError(f"nothing in the recycle bin matches {name!r}")
    # read the stashed exact entry (preferred) before moving anything
    entry, sidecar = None, os.path.join(folder, _ENTRY_SIDECAR)
    if os.path.exists(sidecar):
        try:
            entry = json.load(open(sidecar, encoding="utf-8")).get("entry")
        except Exception:
            entry = None
        try: os.remove(sidecar)   # don't carry the sidecar back into the live draft folder
        except OSError: pass
    if entry is None:
        entry = _reconstruct_entry(name, folder)
    os.rename(folder, dest)
    rp = os.path.join(CAP, "root_meta_info.json")
    try:
        r = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {"all_draft_store": []}
        store = r.get("all_draft_store", [])
        if not any(e.get("draft_name") == name for e in store):   # idempotent: never double-register
            store.insert(0, entry)
        r["all_draft_store"] = store
        json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    return dest


def duplicate_draft(name, new_name=None):
    """Copy a draft to a NEW version (default: next_version) and register the copy as its own draft — so a
    change can be built into the copy while the original is left byte-for-byte untouched (the DUPLICATE +
    rebuild path from the module header). Refuses if the target name already exists. Returns the new name.

    The registry entry is cloned from the source's, then given a fresh draft_id and the copy's name + path
    fields, so CapCut shows the duplicate as a separate draft (not an alias of the original)."""
    require_capcut_quit("duplicate this draft")
    src = os.path.join(CAP, name)
    if not os.path.isdir(src):
        raise FileNotFoundError(src)
    new_name = new_name or next_version(base_of(name))
    dest = os.path.join(CAP, new_name)
    refuse_replace(new_name)
    import shutil as _sh, uuid as _uuid
    _sh.copytree(src, dest)
    fresh_timeline_id(dest)                    # its own preview cache, never the original's frames
    rp = os.path.join(CAP, "root_meta_info.json")
    try:
        r = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {"all_draft_store": []}
        store = r.get("all_draft_store", [])
        srcentry = next((e for e in store if e.get("draft_name") == name), None)
        e = dict(srcentry) if srcentry else {}
        e["draft_name"] = new_name
        e["draft_id"] = str(_uuid.uuid4()).upper()
        e["draft_root_path"] = CAP
        e["draft_fold_path"] = dest
        e["draft_json_file"] = draft_json(dest)
        e["draft_cover"] = os.path.join(dest, "draft_cover.jpg")
        # MICROSECONDS, and ALWAYS stamped: CapCut sorts + shows the grid by these. A copy that inherits the
        # source's old time (or a millisecond value) sinks to the bottom and the creator can't find it.
        now = int(time.time()) * 1_000_000
        for k in ("tm_draft_create", "tm_draft_modified"):
            e[k] = now
        store.insert(0, e)
        r["all_draft_store"] = store
        json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    # keep the copy's own draft_meta_info.json id in sync with the new registry id, best-effort
    try:
        dm = os.path.join(dest, "draft_meta_info.json")
        if os.path.exists(dm):
            m = json.load(open(dm, encoding="utf-8")); m["draft_name"] = new_name; m["draft_id"] = e.get("draft_id", m.get("draft_id"))
            m["tm_draft_create"] = m["tm_draft_modified"] = int(time.time()) * 1_000_000   # fresh, so it lands at the top
            json.dump(m, open(dm, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    return new_name
