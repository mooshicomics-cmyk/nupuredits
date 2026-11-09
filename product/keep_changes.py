#!/usr/bin/env python3
"""keep_changes.py — an update keeps every change she made to the engine, and writes down what it did.

    python3 product/keep_changes.py          after an update: bring her changes forward (runs on its own)
    python3 product/keep_changes.py --scan   list every change she has made to the engine; writes nothing
    python3 product/keep_changes.py --report the same, with each change shown, for the problem report
(Windows: python, never python3.)

WHY THIS EXISTS. The creator's Claude changes the engine for her: a tweak to a builder, a rule added to
CLAUDE.md, a pack whose blue became blush pink. An update used to write the new version of every file it
carries straight over hers. It kept a backup, but nothing ever put her change back, so each update quietly
undid the work her Claude had done, and she found out when a reel came out wrong. An update carries every
file that has changed since the first release, which is nearly every file, so this happened on every update.

HOW. Every update now carries the originals: every version of every text file this engine ever shipped,
packed into one small archive (_updates/history/engine-originals.tar.xz, written by the updater like any
other file), plus the fingerprint of every file in every version. After the new files land, this step:
  1. reads the update's backup of every file it replaced or removed (her versions of them);
  2. asks of each one "is this exactly a version we shipped?" by fingerprint. If so, she never touched it;
  3. for each file she did change, finds the original she started from and re-applies her change on top of
     the new version: a three-way merge, the same idea git uses. Where her edit and ours touch different
     lines, her change comes back on its own. Where they collide, the new version stays in place, hers is
     saved, and the `update` skill has Claude bring it forward with her;
  4. a shipped style pack she edited in place comes back as her own pack ("My Butter") and becomes her
     default if it was; the packs she built are put back by post-update.py's pack step;
  5. CLAUDE.md is refreshed every update with her profile kept; any other line she or her Claude added is
     re-applied the same three-way way;
  6. writes it all down in _local/my-changes.md, newest update first, in plain words, with her saved copies
     and the exact change beside them under _local/my-changes/.

It runs from post-update.py, which ships INSIDE every update, so it works whatever updater version she has.
It never raises into the update: anything it cannot do, it reports and leaves alone. Everything it writes
over is still in the update's backup, and `apply-update.py --rollback` undoes the lot.
"""
import argparse, datetime as _dt, difflib, fnmatch, hashlib, io, json, lzma, os, re, shutil, subprocess, sys, tarfile, tempfile

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STORE_REL = "_updates/history/engine-originals.tar.xz"
DOC_REL = "_local/my-changes.md"
SAVED_REL = "_local/my-changes"

# Files something else already owns across an update. Never merged here, never listed as "her change".
OWNED = {
    "CLAUDE.md",                                   # refreshed by merge-claude-md.py; her other lines: below
    "product/templates/CLAUDE.engine.md",          # the template that refresh reads
    "product/creative-vault/style-packs.json",     # style packs: pack_persist.py
    "product/pack_palettes.py",                    # style packs: pack_persist.py
    "presets/caption-corrections.json",            # merged by the updater, never shipped in a patch
    "product.json",                                # the updater writes her version into it
    "CHANGELOG.md",                                # the updater writes it
}
# Her own data, runtime state and caches: not changes to the engine, and updates never touch them anyway.
SKIP_DIRS = {"projects", "_local", "inbox", "favorites", "_update-backups", "_updates", ".git", "node_modules",
             "__pycache__", "renders", "_handoff", "dist", "releases", ".ship-state", ".venv", "venv",
             ".reel_render", ".cache", ".pytest_cache", "worktrees"}
SKIP_FILES = {"brand-kit.md", "voice-dna.md", "competitor-list.md", "config.json", ".env", ".mcp.json",
              ".claude/settings.local.json", "product/creative-vault/user-style.json",
              "product/creative-vault/user-packs.json", "product/creative-vault/user-effects.json",
              "product/creative-vault/font-overrides.json", "CLAUDE.md.new",
              # written by the engine itself as it runs, never by her: the removal table every update carries
              # (never in a release's file list, so it read as "a file you added" after every update) and the
              # record of which drafts she has opened in CapCut (product/draft_safety.py)
              "product/templates/update-deletes.json", "product/.draft-snapshots.json"}
# Her own settings, permission rules and hooks inside this file are settings_persist.py's to carry across; only a
# change she made to the ENGINE's part of it (its hooks, the rules it ships) is merged here.
CLAUDE_SETTINGS = ".claude/settings.json"


def _skip_dir(name):
    """A folder that is never engine code: her data, caches, and every Python environment the engine builds on
    her machine (venv-capcut, venv-whisperx, ...). Those venvs are thousands of installed-package files, and
    listing them as "changes her Claude made" buried the one real fix in a problem report."""
    return name in SKIP_DIRS or name.startswith(("venv-", ".venv-"))


SKIP_GLOBS = ("*.bak", "*.tmp", "*.pyc", "*.log", "*.orig", "*.rej", "*.swp", ".DS_Store", "*/.DS_Store",
              "Thumbs.db", "*/Thumbs.db", "desktop.ini", "*/desktop.ini", ".env.*")


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _as_text(data):
    """UTF-8 text, or None for anything that is not (binaries, and the rare file in another encoding,
    which is saved rather than merged so nothing is ever re-encoded behind her back)."""
    if data is None or b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _skipped(rel):
    if rel in OWNED or rel in SKIP_FILES:
        return True
    if any(_skip_dir(part) for part in rel.split("/")[:-1]):
        return True
    return any(fnmatch.fnmatch(rel, g) for g in SKIP_GLOBS)


# ── the originals every update carries ─────────────────────────────────────────
class Originals:
    """Every version of every file this engine shipped: fingerprints for all, contents for text files."""

    def __init__(self, path=None):
        self.path = path or os.path.join(ROOT, STORE_REL)
        self.ok, self.versions, self.known, self.blobs = False, {}, {}, {}
        try:
            idx = None
            with tarfile.open(self.path, "r:xz") as t:
                for m in t:
                    if not m.isfile():
                        continue
                    data = t.extractfile(m).read()
                    if m.name == "index.json":
                        idx = json.loads(data.decode("utf-8"))
                    elif m.name.startswith("blobs/"):
                        self.blobs[m.name[len("blobs/"):]] = data
            paths, shas = idx["paths"], idx["shas"]
            for ver, pairs in idx["versions"].items():
                d = {paths[p]: shas[h] for p, h in pairs}
                self.versions[ver] = d
                for rel, h in d.items():
                    self.known.setdefault(rel, set()).add(h)
            self.ok = True
        except (OSError, ValueError, KeyError, TypeError, IndexError, tarfile.TarError, lzma.LZMAError, EOFError):
            self.ok = False

    def shipped(self, rel, sha):
        return sha in self.known.get(rel, ())

    def ever_shipped(self, rel):
        return rel in self.known

    def text_of(self, sha):
        return _as_text(self.blobs.get(sha))

    def base_for(self, rel, from_v, mine_text):
        """(sha, text) of the original she most likely started from.

        Exact when her version is known: the fingerprint that version shipped. A path her version never had
        gives ("", "") (she created it). Otherwise the shipped text closest to hers."""
        if from_v in self.versions:
            sha = self.versions[from_v].get(rel)
            if sha is None:
                return "", ""
            # Exactly what her version shipped. For a binary, or an original missing from the archive, the text
            # is None: better to hand that file to her than to guess at a different starting point.
            return sha, self.text_of(sha)
        best, best_ratio = (None, None), -1.0
        for sha in list(self.known.get(rel, ()))[:40]:
            txt = self.text_of(sha)
            if txt is None or mine_text is None:
                continue
            r = difflib.SequenceMatcher(None, txt.splitlines(), mine_text.splitlines(), autojunk=False).ratio()
            if r > best_ratio:
                best, best_ratio = (sha, txt), r
        return best


def build_store(out_path, versions, blobs):
    """Seller side (make-update.py): pack every version's fingerprints and every shipped text original into
    one archive. `versions` is {version: {path: sha256}}; `blobs` yields (sha256, path, bytes) for text
    files. The versions of one file sit side by side so the compressor sees how alike they are (28 MB of
    history packs to about 3.5 MB). Deterministic: the same inputs give the same archive, byte for byte."""
    paths = sorted({p for d in versions.values() for p in d})
    shas = sorted({h for d in versions.values() for h in d.values()})
    pi, si = {p: i for i, p in enumerate(paths)}, {h: i for i, h in enumerate(shas)}
    index = {"format": 1, "paths": paths, "shas": shas,
             "versions": {v: sorted([pi[p], si[h]] for p, h in d.items()) for v, d in versions.items()}}
    seen = {}
    for sha, rel, data in blobs:
        seen.setdefault(sha, (rel, data))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    def add(t, name, data):
        ti = tarfile.TarInfo(name)
        ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(data), 0, 0o644, 0, 0, "", ""
        t.addfile(ti, io.BytesIO(data))

    with tarfile.open(out_path, "w:xz", preset=9 | lzma.PRESET_EXTREME) as t:
        add(t, "index.json", json.dumps(index, separators=(",", ":")).encode("utf-8"))
        for sha, (rel, data) in sorted(seen.items(), key=lambda kv: (kv[1][0], kv[0])):
            add(t, f"blobs/{sha}", data)
    raw = sum(len(d) for _, d in seen.values())
    return {"versions": len(versions), "paths": len(paths), "originals": len(seen), "raw_bytes": raw,
            "packed_bytes": os.path.getsize(out_path)}


# ── three-way merges ────────────────────────────────────────────────────────────
def _hunks(a, b):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [(i1, i2, b[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def _apply(base, start, end, hunks):
    out, p = [], start
    for i1, i2, repl in sorted(hunks, key=lambda h: (h[0], h[1])):
        out.extend(base[p:i1])
        out.extend(repl)
        p = i2
    out.extend(base[p:end])
    return out


def merge3_lines(base, mine, theirs, prose=False):
    """Three-way merge of line lists. Returns (merged, conflicts).

    Her change and ours are each a list of edits against the original. Edits that do not touch are both
    applied. In CODE, edits that overlap, or even touch, are a conflict unless they are the same edit: the
    careful choice git also makes, because two edits at one spot in code are not safe to combine by rule.
    In PROSE (instructions, notes: prose=True), edits that only touch are both applied, and two additions at
    the same spot are both kept, ours first: a new rule the engine added and a rule she added under the same
    heading both belong there. Edits to the same lines are still a conflict either way."""
    if mine == base:
        return list(theirs), []
    if theirs == base or theirs == mine:
        return list(mine), []
    events = sorted([(i1, i2, "mine", r) for i1, i2, r in _hunks(base, mine)] +
                    [(i1, i2, "theirs", r) for i1, i2, r in _hunks(base, theirs)], key=lambda e: (e[0], e[1]))
    clusters = []
    for e in events:
        last = clusters[-1] if clusters else None
        joins = last is not None and (e[0] < last["end"] or (e[0] == last["end"] and (
            not prose or (e[0] == e[1] and last["start"] == last["end"]))))
        if joins:
            clusters[-1]["end"] = max(clusters[-1]["end"], e[1])
            clusters[-1]["events"].append(e)
        else:
            clusters.append({"start": e[0], "end": e[1], "events": [e]})
    out, pos, conflicts = [], 0, []
    for c in clusters:
        out.extend(base[pos:c["start"]])
        m = [(i1, i2, r) for i1, i2, side, r in c["events"] if side == "mine"]
        t = [(i1, i2, r) for i1, i2, side, r in c["events"] if side == "theirs"]
        if not t:
            out.extend(_apply(base, c["start"], c["end"], m))
        elif not m:
            out.extend(_apply(base, c["start"], c["end"], t))
        elif prose and c["start"] == c["end"] and all(h[0] == h[1] for h in m + t):
            ins_t = [line for h in t for line in h[2]]
            ins_m = [line for h in m for line in h[2]]
            out.extend(ins_t + ([] if ins_m == ins_t else ins_m))   # both additions, ours first
        else:
            mv, tv = _apply(base, c["start"], c["end"], m), _apply(base, c["start"], c["end"], t)
            out.extend(tv)
            if mv != tv:
                conflicts.append({"line": c["start"] + 1, "yours": "".join(mv), "update": "".join(tv)})
        pos = c["end"]
    out.extend(base[pos:])
    return out, conflicts


_GONE = object()


def merge3_json(base, mine, theirs, path=""):
    """Three-way merge of parsed JSON. Keys she added stay, keys she changed keep her value, keys the update
    changed take the update's; the same key changed both ways is a conflict. Returns (merged, conflicts)."""
    if mine == base:
        return theirs, []
    if theirs == base or theirs == mine:
        return mine, []
    if not (isinstance(base, dict) and isinstance(mine, dict) and isinstance(theirs, dict)):
        return theirs, [{"key": path or "/", "yours": mine, "update": theirs}]
    out, conflicts = {}, []
    for k in list(theirs) + [k for k in mine if k not in theirs]:
        b, m, t = base.get(k, _GONE), mine.get(k, _GONE), theirs.get(k, _GONE)
        here = f"{path}/{k}"
        if m is _GONE and t is _GONE:
            continue
        if m is _GONE:                                       # she removed it, or the update added it
            if b is _GONE:
                out[k] = t
            elif t != b:
                out[k] = t
                conflicts.append({"key": here, "yours": "(removed)", "update": t})
            continue
        if t is _GONE:                                       # the update removed it, or she added it
            if b is _GONE:
                out[k] = m
            elif m != b:
                conflicts.append({"key": here, "yours": m, "update": "(removed)"})
            continue
        if b is _GONE:                                       # both added the same key
            if m == t:
                out[k] = m
            elif isinstance(m, dict) and isinstance(t, dict):
                out[k], c = merge3_json({}, m, t, here)
                conflicts += c
            else:
                out[k] = t
                conflicts.append({"key": here, "yours": m, "update": t})
            continue
        out[k], c = merge3_json(b, m, t, here)
        conflicts += c
    return out, conflicts


def _json_indent(text):
    for line in text.splitlines()[1:]:
        stripped = line.lstrip(" \t")
        if stripped and len(line) != len(stripped):
            ws = line[:len(line) - len(stripped)]
            return "\t" if "\t" in ws else len(ws)
    return 2


def _parses(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def _code_problem(rel, text):
    """Why this code would not run, or None (fine, not code, or no way to tell here). Two sets of edits can each be
    right and still not run once they sit together: a buyer's old editor lines landed on top of a new update's own
    `let soundAt`, one script declared it twice, the merge called that clean, and her editor page would not open
    (2026-10-29). Only ever read against the update's own copy, so a tool this computer lacks changes nothing."""
    with tempfile.TemporaryDirectory(prefix="keep-check-") as tmp:
        def fails(argv, name, body):
            path = os.path.join(tmp, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            try:
                r = subprocess.run([*argv, path], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=30)
            except (OSError, subprocess.SubprocessError):
                return None
            if r.returncode == 0:
                return None
            lines = [x.strip() for x in (r.stderr or "").splitlines() if x.strip()]
            return next((x for x in lines if "Error" in x or "error" in x), lines[-1] if lines else "it would not run")
        if rel.endswith(".py"):
            try:
                compile(text, rel, "exec")
            except (SyntaxError, ValueError) as e:
                return str(e)
            return None
        if rel.endswith(".sh"):
            bash = shutil.which("bash")
            return fails([bash, "-n"], "check.sh", text.replace("\r\n", "\n")) if bash else None
        node = shutil.which("node")
        if not node:
            return None
        if rel.endswith((".js", ".cjs")):
            return fails([node, "--check"], "check.js", text)
        if rel.endswith((".html", ".htm")):
            for i, m in enumerate(re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", text, re.S | re.I)):
                attrs = m.group("attrs").lower()
                if "src=" in attrs or re.search(r"type\s*=", attrs) and "javascript" not in attrs:
                    continue
                bad = fails([node, "--check"], f"script{i}.js", m.group("body"))
                if bad:
                    return bad
    return None


def merge_file(rel, base_text, mine_text, theirs_text):
    """Merge one file's text. Returns (merged_text or None, conflicts). JSON merges by key.

    A JSON file is only ever merged as JSON. When one of the three will not parse (hers most likely, broken
    before the update came), a line-by-line merge could write a file nothing can read, so there is no merge:
    the update's copy stays, hers is saved, and the conflict says why (`not_json`)."""
    crlf = "\r\n" in theirs_text
    b, m, t = (x.replace("\r\n", "\n") for x in (base_text, mine_text, theirs_text))
    if rel.endswith(".json"):
        bad = [side for side, x in (("yours", m), ("update", t)) if not _parses(x)]
        if b.strip() and not _parses(b):
            bad.append("original")
        if bad:
            return None, [{"key": "/", "not_json": bad}]
        jb, jm, jt = json.loads(b) if b.strip() else {}, json.loads(m), json.loads(t)
        merged, conflicts = merge3_json(jb, jm, jt)
        if conflicts:
            return None, conflicts
        text = json.dumps(merged, indent=_json_indent(t), ensure_ascii=False)
        if t.endswith("\n"):
            text += "\n"
        if merged == jt:
            text = t                                         # nothing of hers left to add: keep the file as shipped
        return (text.replace("\n", "\r\n") if crlf else text), []
    merged, conflicts = merge3_lines(b.splitlines(keepends=True), m.splitlines(keepends=True),
                                     t.splitlines(keepends=True), prose=rel.endswith((".md", ".txt")))
    if conflicts:
        return None, conflicts
    text = "".join(merged)
    if text != t:
        broke = _code_problem(rel, text)
        if broke and not _code_problem(rel, t):
            return None, [{"key": "/", "breaks": broke}]
    return (text.replace("\n", "\r\n") if crlf else text), []


def _diff(rel, before, after):
    return "".join(difflib.unified_diff((before or "").replace("\r\n", "\n").splitlines(keepends=True),
                                        (after or "").replace("\r\n", "\n").splitlines(keepends=True),
                                        f"original/{rel}", f"yours/{rel}", n=3))


def _write_keep_mode(path, data):
    mode = os.stat(path).st_mode if os.path.exists(path) else None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    if mode is not None:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


# ── the update this is finishing ────────────────────────────────────────────────
def _version():
    try:
        with open(os.path.join(ROOT, "product.json"), encoding="utf-8") as fh:
            return str(json.load(fh).get("version", ""))
    except (OSError, ValueError):
        return ""


def latest_backup():
    """The backup the update that just ran made (it lands us on the version now installed), or None."""
    root = os.path.join(ROOT, "_update-backups")
    if not os.path.isdir(root):
        return None
    ver, best = _version(), None
    for name in os.listdir(root):
        d = os.path.join(root, name)
        if name.endswith(".rolledback") or not os.path.isfile(os.path.join(d, "applied.json")):
            continue
        try:
            with open(os.path.join(d, "applied.json"), encoding="utf-8") as fh:
                log = json.load(fh)
        except (OSError, ValueError):
            continue
        if str(log.get("to")) == ver and (best is None or os.path.getmtime(d) > os.path.getmtime(best[0])):
            best = (d, log)
    return best


def _walk(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            yield os.path.relpath(p, base).replace(os.sep, "/"), p


def bring_forward(originals, backup, claude_before=None):
    """Re-apply her changes from one update's backup. Returns the report dict (also saved to disk)."""
    bdir, log = backup
    name = os.path.basename(bdir)
    from_v, to_v = str(log.get("from", "")), str(log.get("to", ""))
    saved_dir = os.path.join(ROOT, SAVED_REL, name)
    report = {"update": name, "from": from_v, "to": to_v, "date": _now(),
              "kept": [], "needs_hand": [], "removed": [], "packs": [], "notes": []}

    def save_hers(rel, data, base_text):
        p = os.path.join(saved_dir, rel)
        _write_keep_mode(p, data)
        diff_rel = None
        mine_text = _as_text(data)
        if mine_text is not None and base_text is not None:
            with open(p + ".diff", "w", encoding="utf-8") as fh:
                fh.write(_diff(rel, base_text, mine_text))
            diff_rel = f"{SAVED_REL}/{name}/{rel}.diff"
        return f"{SAVED_REL}/{name}/{rel}", diff_rel

    if from_v not in originals.versions:
        # Her version is not in this archive (a 1.x install given a 2.x package, or an archive that stops short
        # of her version). Without the exact original, "is this hers?" has no answer: every file she never
        # touched reads as her change, and the nearest shipped text can be the NEW file, which would write her
        # old copy back over the update. So nothing is merged and no pack is adopted; everything the update
        # replaced stays in its backup. (Her CLAUDE.md lines are still brought back: that merge starts from the
        # old template in the backup, not from this archive.)
        report["notes"].append(f"this update's originals do not include v{from_v}, the version you updated from, "
                               f"so your changes to engine files were not merged. Every file it replaced is in "
                               f"{os.path.relpath(bdir, ROOT)}.")
        _bring_forward_claude_md(bdir, claude_before, report, save_hers)
        return report

    for kind in ("overwritten", "deleted"):
        top = os.path.join(bdir, kind)
        if not os.path.isdir(top):
            continue
        for rel, path in _walk(top):
            if _skipped(rel) or rel.startswith("_updates/"):
                continue
            mine = _read(path)
            if originals.shipped(rel, sha256_bytes(mine)):
                continue                                     # exactly a version we shipped: not hers
            mine_text = _as_text(mine)
            base_sha, base_text = originals.base_for(rel, from_v, mine_text)
            target = os.path.join(ROOT, rel)
            if kind == "deleted" and os.path.exists(target) and _read(target) == mine:
                # An older updater removed her own file along with the engine's copy of that name, and
                # post-update's keep_her_files step has already put hers back where it was.
                report["kept"].append({"path": rel, "how": "your own copy is back where it was"})
                continue
            if kind == "deleted" or not os.path.exists(target):
                copy, diff_rel = save_hers(rel, mine, base_text)
                report["removed"].append({"path": rel, "saved": copy, "change": diff_rel})
                continue
            theirs = _read(target)
            theirs_text = _as_text(theirs)
            if mine_text is None or theirs_text is None or base_text is None:
                # A binary, or no original to measure her change against. Her version is kept when the update
                # did not change this file from what she started with; otherwise both are kept for her.
                if base_sha and sha256_bytes(theirs) == base_sha:
                    _write_keep_mode(target, mine)
                    report["kept"].append({"path": rel, "how": "the update had not changed this file; yours is back"})
                else:
                    copy, diff_rel = save_hers(rel, mine, base_text)
                    why = ("no original to compare yours with" if base_text is None and mine_text is not None
                           else "not a text file, so it cannot be merged line by line")
                    report["needs_hand"].append({"path": rel, "saved": copy, "change": diff_rel, "why": why})
                continue
            if rel == CLAUDE_SETTINGS:
                verdict = _settings_verdict(base_text, mine_text, theirs_text)
                if verdict == "kept":
                    report["kept"].append({"path": rel, "how": "your own settings and hooks are back in the new version"})
                    continue
                if verdict == "nothing":
                    continue
                if verdict in ("engine", "missing"):
                    copy, diff_rel = save_hers(rel, mine, base_text)
                    why = ("you changed one of the engine's own hooks in this file (took one out, or changed one); the "
                           "new version is in place with your own settings and hooks in it, and your whole file is saved"
                           if verdict == "engine" else
                           "not all of your own settings could be put back into the new file; the new version is in "
                           "place and your whole file is saved")
                    report["needs_hand"].append({"path": rel, "saved": copy, "change": diff_rel, "why": why})
                    continue
            merged, conflicts = merge_file(rel, base_text, mine_text, theirs_text)
            if merged is None:
                copy, diff_rel = save_hers(rel, mine, base_text)
                not_json = next((c["not_json"] for c in conflicts if c.get("not_json")), None)
                if any(c.get("breaks") for c in conflicts):
                    why = ("your change and the update's both fit on their own, but together this file would not run, "
                           "so the new version is in place and yours is saved")
                elif not_json and "yours" in not_json:
                    why = ("your copy of this file could not be read (it was already broken before the update), so "
                           "the new version is in place and yours is saved exactly as it was")
                elif not_json:
                    why = "this file could not be read to merge, so the new version is in place and yours is saved"
                else:
                    why = "the update changed the same lines you did"
                report["needs_hand"].append({"path": rel, "saved": copy, "change": diff_rel, "why": why,
                                             "where": [c.get("line") or c.get("key") for c in conflicts][:6]})
                continue
            data = merged.encode("utf-8")
            if data != theirs:
                _write_keep_mode(target, data)
                report["kept"].append({"path": rel, "how": "your change is back, on top of the new version"})
            elif originals.versions.get(to_v, {}).get(rel) not in (None, sha256_bytes(theirs)):
                # Not the file this update shipped: an earlier finishing step (her settings, her packs) already
                # put her change back into it.
                report["kept"].append({"path": rel, "how": "your change is already back in the new version"})
            else:
                report["kept"].append({"path": rel, "how": "the new version already does what your change did"})

    _bring_forward_claude_md(bdir, claude_before, report, save_hers)
    _adopt_edited_packs(bdir, originals, report)
    return report


def _settings_persist():
    try:
        sys.path.insert(0, HERE)
        import settings_persist
        return settings_persist if hasattr(settings_persist, "engine_part") else None
    except ImportError:
        return None
    finally:
        sys.path.pop(0)


def _settings_verdict(base_text, mine_text, theirs_text):
    """What became of her .claude/settings.json. This step never writes that file: the update wrote the engine's
    new one and settings_persist put her part (settings, permission rules, hooks) back into it. So:
      "kept"     she changed only her own part, and the new file on disk holds all of it
      "nothing"  she changed nothing of hers (formatting alone)
      "engine"   she changed one of the ENGINE's own hooks (took one out, changed one): saved for her to redo
      "missing"  some of her own part is not in the new file: saved, never dropped silently
      None       the file cannot be read as settings (the JSON merge then says why)
    The engine's own permission rules are left out of "engine": the update always puts them back, and one missing
    from her copy is almost always a permissions block rewritten whole, not a choice to turn a safeguard off."""
    sp = _settings_persist()
    if sp is None:
        return None
    try:
        base = json.loads(base_text) if (base_text or "").strip() else {}
        mine, now = json.loads(mine_text), json.loads(theirs_text)
    except ValueError:
        return None
    if not all(isinstance(x, dict) for x in (base, mine, now)):
        return None
    engine_hooks = lambda d: {k: v for k, v in sp.engine_part(d).items() if k != "permissions"}   # noqa: E731
    if engine_hooks(mine) != engine_hooks(base):
        return "engine"
    hers = sp._theirs(mine)
    if hers == sp._theirs(base):
        return "nothing"
    return "kept" if sp.merge_settings(now, hers) == now else "missing"


def _bring_forward_claude_md(bdir, before, report, save_hers):
    """Her own lines in CLAUDE.md, outside the profile block the refresh already keeps.

    The refresh rebuilds CLAUDE.md from the engine template every time it runs, which drops any line she
    added outside her profile block, so this runs on EVERY finishing step, not only the first after an
    update. The original to compare with is the template her file was built from: the one this update
    replaced (in its backup), or, when the template did not change, the one on disk now."""
    target = os.path.join(ROOT, "CLAUDE.md")
    old_tpl = os.path.join(bdir, "overwritten", "product", "templates", "CLAUDE.engine.md") if bdir else ""
    if not old_tpl or not os.path.exists(old_tpl):
        old_tpl = os.path.join(ROOT, "product", "templates", "CLAUDE.engine.md")
    if not before or not os.path.exists(old_tpl) or not os.path.exists(target):
        return
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("merge_claude_md", os.path.join(ROOT, "scripts", "merge-claude-md.py"))
        mcm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mcm)
        with open(old_tpl, encoding="utf-8") as fh:
            base, _ = mcm.merge(before, fh.read())          # the old instructions with her profile in place
    except Exception as e:   # noqa: BLE001
        report["notes"].append(f"CLAUDE.md: could not compare your version with the old one ({e})")
        return
    if base is None or base == before:
        return                                               # nothing of hers beyond the profile block
    with open(target, encoding="utf-8") as fh:
        now = fh.read()
    merged, conflicts = merge_file("CLAUDE.md", base, before, now)
    if merged is None:
        copy, diff_rel = save_hers("CLAUDE.md", before.encode("utf-8"), base)
        report["needs_hand"].append({"path": "CLAUDE.md", "saved": copy, "change": diff_rel,
                                     "why": "the update rewrote the same instructions you had changed"})
        return
    if merged != now:
        _write_keep_mode(target, merged.encode("utf-8"))
    report["kept"].append({"path": "CLAUDE.md", "how": "your own lines are back in the refreshed instructions"})


def _adopt_edited_packs(bdir, originals, report):
    her_base = os.path.join(bdir, "overwritten")
    # Either pack file replaced is enough: an update that shipped pack_palettes.py alone still reset the colours
    # of a launch pack she had changed in place.
    if not any(os.path.isfile(os.path.join(her_base, *rel.split("/")))
               for rel in ("product/creative-vault/style-packs.json", "product/pack_palettes.py")):
        return
    try:
        sys.path.insert(0, HERE)
        import pack_persist
    except ImportError:
        return
    finally:
        sys.path.pop(0)
    texts, seen = [], set()
    for ver, files in originals.versions.items():
        pj, pp = files.get("product/creative-vault/style-packs.json"), files.get("product/pack_palettes.py")
        if (pj, pp) in seen:
            continue                                         # most releases did not touch the packs
        seen.add((pj, pp))
        texts.append((originals.text_of(pj) if pj else None, originals.text_of(pp) if pp else None))
    try:
        done, problems = pack_persist.adopt_edited(her_base, pack_persist.shipped_history(texts))
    except Exception as e:   # noqa: BLE001
        report["notes"].append(f"style packs: could not check for packs you edited ({e})")
        return
    report["packs"] += done
    report["notes"] += [f"style pack {n}: {why}" for n, why in problems]


# ── what she has changed, right now ─────────────────────────────────────────────
def inventory(originals, exclude=()):
    """(changed, added): shipped files whose content is not any version we shipped, and files she added."""
    changed, added = [], []
    for rel, path in _walk(ROOT):
        if _skipped(rel) or rel in exclude:
            continue
        if originals.ever_shipped(rel):
            try:
                if not originals.shipped(rel, sha256_bytes(_read(path))):
                    changed.append(rel)
            except OSError:
                continue
        else:
            added.append(rel)
    return sorted(changed), sorted(added)


def _packs_back():
    """(in place, not whole): her own packs after the update. A pack is in place only when it is whole, its
    colours included, never by its name alone: an update can leave the name and take every colour of it."""
    try:
        sys.path.insert(0, HERE)
        import pack_persist
        mine = pack_persist.load()
        _, live = pack_persist._shipped_packs()
        here = [n for n in mine if live and n in live and n not in set(pack_persist.forgotten())]
        gaps = getattr(pack_persist, "missing_tables", lambda _n, _s: [])
        broken = sorted(n for n in here if gaps(n, mine[n]))
        return sorted(n for n in here if n not in broken), broken
    except Exception:   # noqa: BLE001
        return [], []
    finally:
        sys.path.pop(0)


# ── the record she (and Claude) can read ───────────────────────────────────────
def _section(report, changed, added):
    L = [f"## v{report['from']} → v{report['to']} · {report['date']}", ""]
    if report["kept"]:
        L += [f"**Came through the update on their own ({len(report['kept'])})**", ""]
        L += [f"- `{k['path']}`: {k['how']}" for k in report["kept"]] + [""]
    if report["needs_hand"]:
        L += [f"**Needs a hand ({len(report['needs_hand'])})** The new version is in place and yours is saved. "
              "Say \"bring my changes forward\" and Claude will redo your change on the new version with you.", ""]
        for n in report["needs_hand"]:
            line = f"- `{n['path']}`: {n['why']}. Yours: `{n['saved']}`"
            if n.get("change"):
                line += f" · what you changed: `{n['change']}`"
            L.append(line)
        L.append("")
    if report["removed"]:
        L += [f"**No longer part of the engine ({len(report['removed'])})** This update removed these files. "
              "You had changed them, so your versions are saved.", ""]
        L += [f"- `{r['path']}`: yours is at `{r['saved']}`" for r in report["removed"]] + [""]
    packs = report["packs"]
    back = report.get("packs_back") or []
    broken = report.get("packs_broken") or []
    if packs or back or broken:
        L += ["**Style packs**", ""]
        for p in packs:
            L.append(f"- \"{p['pack']}\" had your own changes. The update brought a new {p['pack']}, so yours is saved "
                     f"as its own pack, **{p['saved_as']}**" + (", and it is now your default." if p["default_switched"] else "."))
        if back:
            L.append(f"- Your own pack{'s' if len(back) > 1 else ''} {', '.join(back)}: in place.")
        if broken:
            L.append(f"- Your own pack{'s' if len(broken) > 1 else ''} {', '.join(broken)}: some of {'their' if len(broken) > 1 else 'its'} "
                     f"colours are not in place yet. They are saved; say \"restore my style pack\" and Claude puts them back.")
        L.append("")
    listed = ({k["path"] for k in report["kept"]} | {n["path"] for n in report["needs_hand"]}
              | {r["path"] for r in report["removed"]})
    others = [c for c in changed if c not in listed]
    if others:
        L += [f"**Your other changes, untouched by this update ({len(others)})**", ""]
        L += [f"- `{c}`" for c in others[:40]] + ([f"- …and {len(others) - 40} more"] if len(others) > 40 else []) + [""]
    if added:
        L += [f"**Files you added ({len(added)})** Updates never touch these.", ""]
        L += [f"- `{a}`" for a in added[:40]] + ([f"- …and {len(added) - 40} more"] if len(added) > 40 else []) + [""]
    for n in report["notes"]:
        L.append(f"- {n}")
    return "\n".join(L).rstrip() + "\n"


_HEAD = ("# Your changes to the engine\n\n"
         "The engine's own record of changes you (or Claude, for you) made to the engine's files, and what each "
         "update did with them. Your projects, footage, brand kit and settings are never touched by an update, so "
         "they are not listed here. Newest update first.\n")


def write_doc(report, changed, added):
    doc = os.path.join(ROOT, DOC_REL)
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    body = ""
    if os.path.exists(doc):
        with open(doc, encoding="utf-8") as fh:
            body = fh.read()
        body = body[len(_HEAD):] if body.startswith(_HEAD) else body
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write(_HEAD + "\n" + _section(report, changed, added) + ("\n" + body.lstrip("\n") if body.strip() else ""))
    rec = os.path.join(ROOT, SAVED_REL, report["update"], "changes.json")
    os.makedirs(os.path.dirname(rec), exist_ok=True)
    with open(rec, "w", encoding="utf-8") as fh:
        json.dump(dict(report, changed_now=changed, added_now=added), fh, indent=2, ensure_ascii=False)


def after_update(claude_before=None, again=False):
    """post-update.py's step. Returns a one-line summary for the update output (or "")."""
    backup = latest_backup()
    if not backup or (not again and os.path.exists(os.path.join(ROOT, SAVED_REL, os.path.basename(backup[0]),
                                                                  "changes.json"))):
        # No fresh update to finish, but the instructions refresh just ran again: put her own CLAUDE.md
        # lines back if it dropped them. Quietly, unless there is something she needs to know.
        quiet = {"kept": [], "needs_hand": [], "notes": []}
        _bring_forward_claude_md(None, claude_before, quiet, lambda rel, data, base: (DOC_REL, None))
        if quiet["needs_hand"]:
            return ("your changes: the refreshed instructions in CLAUDE.md collide with a line you added; "
                    "say \"bring my changes forward\"")
        return ""
    originals = Originals()
    if not originals.ok:
        return ("your changes: this update did not carry the originals to compare with, so nothing was merged. "
                f"Every file it replaced is in {os.path.relpath(backup[0], ROOT)}.")
    report = bring_forward(originals, backup, claude_before)
    report["packs_back"], report["packs_broken"] = _packs_back()
    if str(backup[1].get("from", "")) not in originals.versions:
        # The same reason bring_forward merged nothing: against an archive without her version, every file of
        # hers would be listed as "changed", so the record says only what happened.
        write_doc(report, [], [])
        return ("your changes: this update's originals do not include your version, so nothing was merged. "
                f"Every file it replaced is in {os.path.relpath(backup[0], ROOT)} (details: {DOC_REL}).")
    changed, added = inventory(originals)
    if not (report["kept"] or report["needs_hand"] or report["removed"] or report["packs"]
            or report["packs_broken"] or changed or added or report["notes"]):
        return ""                                            # she has changed nothing: nothing to say
    write_doc(report, changed, added)
    bits = []
    if report["kept"]:
        bits.append(f"{len(report['kept'])} came through on their own")
    if report["needs_hand"]:
        bits.append(f"{len(report['needs_hand'])} need{'s' if len(report['needs_hand']) == 1 else ''} a hand")
    for p in report["packs"]:
        bits.append(f"{p['pack']} saved as {p['saved_as']}")
    if report["packs_broken"]:
        bits.append(f"colours of {', '.join(report['packs_broken'])} not back yet (say \"restore my style pack\")")
    if not bits:
        bits.append("none of them overlapped with this update")
    return f"your changes: {', '.join(bits)} (details: {DOC_REL})"


# ── the problem report's section (scripts/collect-report.sh) ────────────────────
# A buyer's Claude fixes engine bugs on her machine, and until this section those fixes never travelled: they
# lived in her copy, and the seller only ever saw a screenshot saying "five engine bugs fixed today". The report
# now carries every engine file that differs from what shipped, with the exact change, so the fix can land in the
# engine for everyone. Engine files only: her projects, brand kit, packs and settings are skipped (SKIP_*), and a
# file she ADDED is named, never shown, because it can be anything of hers.
REPORT_DIFF_LINES = 300        # per file
REPORT_TOTAL_LINES = 2500      # the whole section, so one huge rewrite cannot bury the rest of the report


def _changed_by_mtime(newer_than):
    """Engine files modified after the install, for a copy with no originals to compare against (installed from
    the zip, never updated). Unzipping keeps each file's packed time, so a file her Claude edited is newer."""
    out = []
    for rel, path in _walk(ROOT):
        if _skipped(rel):
            continue
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if m > newer_than:
            out.append((rel, m))
    return sorted(out, key=lambda x: -x[1])


def report_section():
    ver = _version()
    L = ["### Changes made to this engine", "",
         "_Engine files on this machine that differ from what shipped: fixes her Claude made. Each one is a bug to "
         "fix in the engine for everyone._", ""]
    o = Originals()
    if o.ok:
        changed, added = inventory(o)
        if not changed and not added:
            return "\n".join(L + ["- none: every engine file is exactly as shipped"]) + "\n"
        L += [f"**Changed ({len(changed)})**", ""] + [f"- `{c}`" for c in changed] + [""]
        if added:
            L += [f"**Added ({len(added)}, names only)**", ""] + [f"- `{a}`" for a in added[:40]]
            L += ([f"- …and {len(added) - 40} more"] if len(added) > 40 else []) + [""]
        budget = REPORT_TOTAL_LINES
        for rel in changed:
            try:
                mine = _as_text(_read(os.path.join(ROOT, rel)))
            except OSError:
                continue
            if mine is None:
                L += [f"`{rel}`: not a text file, not shown", ""]
                continue
            _sha, base = o.base_for(rel, ver, mine)
            if base is None:
                L += [f"`{rel}`: no shipped original to compare with", ""]
                continue
            d = _diff(rel, base, mine).splitlines()
            shown = d[:min(REPORT_DIFF_LINES, max(budget, 0))]
            if not shown:
                L += [f"`{rel}`: change not shown (the report's size limit was reached)", ""]
                continue
            budget -= len(shown)
            L += ["```diff"] + shown + ["```"]
            if len(shown) < len(d):
                L.append(f"_…{len(d) - len(shown)} more lines of this change not shown_")
            L.append("")
    else:
        # A copy installed from the zip and never updated has no originals yet (they arrive with the first update).
        # Name what changed since the install so the seller can compare it against that version's release.
        try:
            installed = os.path.getmtime(os.path.join(ROOT, "product.json"))
        except OSError:
            installed = None
        L.append(f"- no shipped originals on this machine yet (installed from the zip, v{ver or '?'}, never updated), "
                 "so the changes are named, not shown. Compare them against that version's release.")
        if installed is not None:
            recent = _changed_by_mtime(installed + 120)
            if recent:
                L += ["", f"**Edited since the install ({len(recent)})**", ""]
                L += [f"- `{r}` ({_dt.datetime.fromtimestamp(m).strftime('%Y-%m-%d %H:%M')})" for r, m in recent[:60]]
                L += ([f"- …and {len(recent) - 60} more"] if len(recent) > 60 else [])
            else:
                L.append("- no engine file was edited since the install")
        L.append("")
    doc = os.path.join(ROOT, DOC_REL)
    if os.path.exists(doc):
        try:
            with open(doc, encoding="utf-8") as fh:
                body = fh.read()
            body = body[len(_HEAD):] if body.startswith(_HEAD) else body
            last = body.strip().split("\n## ")[0].strip()
            if last:
                L += ["**What the last update did with them** (from `_local/my-changes.md`)", "", last[:4000], ""]
        except OSError:
            pass
    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Keep her changes to the engine across updates.")
    ap.add_argument("--scan", action="store_true", help="list what she has changed; write nothing")
    ap.add_argument("--report", action="store_true",
                    help="the problem report's section: every changed engine file with its change; write nothing")
    ap.add_argument("--again", action="store_true", help="redo the last update's merge even if it was done")
    ap.add_argument("--store", help="the originals archive to use (default: the last update's)")
    a = ap.parse_args()
    if a.report:
        sys.stdout.write(report_section())
        return 0
    if a.scan:
        o = Originals(a.store)
        if not o.ok:
            print("No originals to compare with yet: they arrive with the next update.")
            return 0
        changed, added = inventory(o)
        print(f"Changed engine files ({len(changed)}):" + "".join(f"\n  {c}" for c in changed))
        print(f"Files you added ({len(added)}):" + "".join(f"\n  {x}" for x in added))
        return 0
    line = after_update(again=a.again)
    print(line or "Nothing of yours to bring forward.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
