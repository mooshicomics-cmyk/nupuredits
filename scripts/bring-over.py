#!/usr/bin/env python3
"""bring-over.py — bring everything that is hers from an old engine folder into this one.

    python3 scripts/bring-over.py "<old engine folder>"            preview: what would come across (writes nothing)
    python3 scripts/bring-over.py "<old engine folder>" --apply    bring it all over
    python3 scripts/bring-over.py "<old engine folder>" --apply --no-projects
                                                                   the same, but her footage stays where it is
    python3 scripts/bring-over.py "<old engine folder>" --apply --projects
                                                                   bring her footage even where it is a full
                                                                   copy (a PC, or another drive): asked first
    python3 scripts/bring-over.py --find                           list the engine folders in her home folder
(Windows: python, never python3.) Run it from THIS engine's folder, the new one. The `bring-over` skill
drives it: preview first, her yes, then --apply.

WHY THIS EXISTS. A new major version arrives as a fresh download, not as an update, so nothing she made in
the old folder is in the new one: her brand kit, her creator profile, the style packs she built, what she
taught it, her favorite sounds, her words, her settings, her keys, her reels. This brings all of it across,
and none of the old engine's own files, so the new version stays exactly the new version.

WHAT COMES ACROSS. Every item is COPIED. The old folder is only ever read: CapCut drafts built there still
point at footage inside it, so it has to keep working until those reels are finished.
  brand-kit.md                  hers, the whole file (while this engine's is still the blank one)
  CLAUDE.md                     her creator profile and look note, dropped into the NEW instructions with
                                merge-claude-md.py's merge(); any other line she added is saved and handed
                                to her, never merged blind
  style packs                   every pack she built: from the old pack files, from the old protected copy
                                and from every old update backup (so a pack an EARLIER update deleted comes
                                back too), written in through pack_persist / pack_write so this engine's
                                protected copy records them. The engine's own packs never come across; one of
                                them she changed in place comes across as a pack of her own ("My Butter")
  user-style.json               her default pack and accent, once that pack exists here
  _local/                       everything she taught it, minus caches and markers
  user-effects, font-overrides  the text animations she named and the fonts she matched up by hand
  caption words                 merged by the updater's own rule: new defaults arrive, her words win
  settings in engine files      permission mode, hook defaults, headline font: settings_persist harvests
                                them from the old files and restores them into these
  keys and connections          .env, .mcp.json, config.json, .claude/settings.local.json (values never shown)
  projects/ and inbox/          copied as copy-on-write clones where the disk offers them. Where it cannot
                                (a PC, another drive), the copy is a full duplicate of her footage, so
                                --apply stops before copying anything until she picks --projects or
                                --no-projects
  files she added               in assets/, the sound folder and presets/; any other one is listed for her

WHAT NEVER HAPPENS. Nothing is written in the old folder. Nothing in this engine is overwritten except the
merges named above. Nothing is deleted anywhere. A change she made to one of the old engine's OWN files is
never copied over the new file: her copy is saved under _local/my-changes/from-v1/ and listed under "Needs a
hand" in _local/my-changes.md, where the update skill's "bring my changes forward" picks it up with her.

HOW OLD FILES ARE TOLD APART. product/templates/v1-history.json holds fingerprints of every v1 release:
hashed paths, hashed contents, and (hashed old path -> new path) for the files this version renamed. No v1
file name is in it, or in this script. An old file whose path and content both match is the engine's own;
a known path with other content is a change she made; a path v1 never shipped is hers.

Running it twice brings nothing twice. Stdlib only: it has to run before this engine is set up.
"""
import sys

sys.dont_write_bytecode = True           # a preview must leave nothing behind, compiled caches included

import argparse
import ast
import collections
import difflib
import filecmp
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT = os.path.join(ROOT, "product")
ENGINE_ID = "ai-edit-engine"
HISTORY_REL = "product/templates/v1-history.json"
FROM = "from-v1"                                 # under _local/my-changes/: her saved copies from the old engine

# Where a file she ADDED to the engine comes across automatically (her logos, her sounds, her presets).
SFX_REL = "product/creative-vault/sfx"
HERS_ADDED = ("assets/", SFX_REL + "/", "presets/")
# Hers, at fixed places in the engine; the updater protects both (apply-update.py PROTECTED).
USER_EFFECTS_REL = "product/creative-vault/user-effects.json"        # text_effects.USER_EFFECTS
FONT_OVERRIDES_REL = "product/creative-vault/font-overrides.json"    # capcut_font_doctor.OVERRIDES
# draft_safety._snap_file(): the state of every CapCut draft the engine built, taken right after the build.
# It is how the engine tells her own CapCut edits apart before it touches a draft, so it comes with her.
DRAFT_SNAPSHOTS_REL = "product/.draft-snapshots.json"
SECRETS = (".env", ".mcp.json", "config.json", ".claude/settings.local.json")

# Folders that are the engine's own working state, never hers and never listed.
SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                  ".cache", "renders", ".reel_render", "dist", "releases", ".ship-state", "ship-archive",
                  "_handoff", "worktrees"}
TOP_HANDLED = {"projects", "inbox", "_local", "_update-backups", "_updates"}
# Files the engine writes inside itself as it runs: never hers.
GENERATED = ("*.bak", "*.tmp", "*.pyc", "*.log", "*.orig", "*.rej", "*.swp", "*.bringing-over", ".DS_Store",
             "*/.DS_Store", "Thumbs.db", "*/Thumbs.db", "desktop.ini", "*/desktop.ini", "CLAUDE.md.new",
             "product/templates/update-deletes.json", ".claude/*.lock")
# The vendored build engine writes its own working files as it runs: one it never shipped is not hers.
RUNTIME_DIRS = ("product/engine/",)
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
MARGIN = 200 * 1024 * 1024                       # room kept free on top of what the copy needs
PACKS_WHERE = "this engine's style packs, and its protected copy of them"
GROUPS = (("brand", "Your brand and voice"), ("packs", "Your style packs"), ("taught", "What you taught it"),
          ("words", "Your words, settings and keys"), ("files", "Files you added"),
          ("footage", "Your reels and clips"))


# ── fingerprints (dev-tools/build-v1-history.py writes the same ones) ──────────────────────────────────
def path_key(rel):
    """A path, as v1-history.json knows it: never the name itself."""
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()[:20]


def content_key(data):
    return hashlib.sha256(data).hexdigest()[:32]


def launch_pack_key(name, block):
    """One of the engine's own style packs, as a release shipped it."""
    canon = json.dumps([name, block], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]


def word_key(kind, word, value=None):
    """One entry of the caption word list (presets/caption-corrections.json) as a release shipped it: a "flag" word,
    or an "auto" word with the spelling it is corrected to."""
    raw = f"{kind}\0{word}" + (f"\0{value}" if kind == "auto" else "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class History:
    """Fingerprints of every file a v1 release shipped (product/templates/v1-history.json)."""

    def __init__(self, data):
        self.paths = set(data.get("paths") or [])
        self.contents = set(data.get("contents") or [])
        self.renamed = {k: v for k, v in (data.get("renamed") or {}).items() if isinstance(v, str)}
        self.launch_packs = set(data.get("launch_packs") or [])
        # Every word-list entry a v1 release shipped (word_key). A word the new version dropped on purpose is not
        # hers just because her old list still has it; one she added, or respelled, never matches.
        self.words = set(data.get("caption_words") or [])

    def shipped_word(self, kind, word, value=None):
        return word_key(kind, word, value) in self.words

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("format") != 1:
            return None
        return cls(data)

    def shipped_path(self, rel):
        return path_key(rel) in self.paths

    def shipped_bytes(self, data):
        """Is this exactly a file some v1 release shipped? A copy whose line endings a Windows tool
        rewrote is still the engine's own."""
        if data is None:
            return False
        if content_key(data) in self.contents:
            return True
        return b"\r\n" in data and content_key(data.replace(b"\r\n", b"\n")) in self.contents

    def new_name(self, rel):
        """Where the file that was `rel` in v1 lives in this version (the same path unless it was renamed)."""
        return self.renamed.get(path_key(rel), rel)


# ── small, safe file helpers ────────────────────────────────────────────────────────────────────────
class Refusal(Exception):
    """Stops the command with a plain message. Nothing has been written when one is raised."""


def _py():
    return "python" if os.name == "nt" or os.environ.get("MSYSTEM") else "python3"


def _rel(path, base=ROOT):
    return os.path.relpath(path, base).replace(os.sep, "/")


def _read_bytes(path):
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _read_text(path):
    """Text of a file of hers, whatever it was saved as (UTF-8, UTF-8 with a mark, Windows-1252), with
    Windows line endings read as plain ones, so a comparison is never fooled by how a file was saved."""
    data = _read_bytes(path)
    if data is None:
        return None
    for enc in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(enc).replace("\r\n", "\n")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace").replace("\r\n", "\n")


def _read_json(path):
    text = _read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _human(n):
    for unit, div in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} bytes"


def _inside(child, parent):
    child, parent = (os.path.normcase(os.path.realpath(x)) for x in (child, parent))
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def _tree_files(path):
    """(relative path, size) of every file under `path` (or of `path` itself when it is a file)."""
    if os.path.isfile(path):
        return [("", os.path.getsize(path))]
    out = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            if os.path.islink(p):
                continue
            try:
                out.append((_rel(p, path), os.path.getsize(p)))
            except OSError:
                continue
    return out


def semver(v):
    parts = []
    for chunk in str(v).split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Engine:
    """This engine's own modules. Every real write goes through them; nothing here re-implements them."""

    def __init__(self):
        if PRODUCT not in sys.path:
            sys.path.insert(0, PRODUCT)
        try:
            import keep_changes
            import pack_persist
            import pack_write
            import settings_persist
            self.mcm = _load_module("merge_claude_md", os.path.join(ROOT, "scripts", "merge-claude-md.py"))
        except Exception as exc:  # noqa: BLE001
            raise Refusal(f"This engine is missing a part this command needs ({exc}). Download the new version "
                          f"again, then run this once more. Nothing was copied or changed.")
        self.pp, self.pw, self.sp, self.kc = pack_persist, pack_write, settings_persist, keep_changes
        try:
            self.upd = _load_module("apply_update", os.path.join(ROOT, "scripts", "apply-update.py"))
        except Exception:  # noqa: BLE001
            self.upd = None


# ── the plan: what comes across, what is already here, what needs a hand ─────────────────────────────
class Item:
    def __init__(self, group, label, status, where="", size=0, run=None, agg=None):
        self.group, self.label, self.status, self.where = group, label, status, where
        self.size, self.run, self.agg = size, run, agg
        self.failed = None


class Plan:
    def __init__(self):
        self.items = []        # in the order --apply runs them
        self.hands = []        # her copy of something that could not simply come across (saved, then listed)
        self.removed = []      # engine files she changed that this version no longer has
        self.hand_notes = []   # needs a hand, with nothing to save
        self.left = []         # (path, size): files she added outside the places that come across
        self.notes = []        # plain lines for her, nothing to act on
        self.added = []        # files she added that come (or came) across
        self.adopted = []      # the launch packs she changed in place, as keep_changes records them

    def add(self, group, label, status, where="", size=0, run=None, agg=None):
        item = Item(group, label, status, where, size, run, agg)
        self.items.append(item)
        return item

    def step(self, run):
        """Work that goes with the items above it and has no line of its own in the report."""
        item = Item(None, None, "bring", run=run)
        self.items.append(item)
        return item

    def hand(self, path, why, save_as=None, src=None, data=None, base=None, removed=False):
        for h in self.hands + self.removed:
            if h["path"] == path:                 # one saved copy per file, with every reason it needs a hand
                if why not in h["why"]:
                    h["why"] += "; also, " + why
                if h.get("base") is None:
                    h["base"] = base
                return
        rec = {"path": path, "why": why, "save_as": save_as or path, "src": src, "data": data, "base": base}
        (self.removed if removed else self.hands).append(rec)


class Ctx:
    """The two engines, checked, with the old one's files indexed and a scratch folder for read-only views."""

    def __init__(self, old_arg, apply=False, no_projects=False, history=None):
        self.apply, self.no_projects = apply, no_projects
        new_prod = _read_json(os.path.join(ROOT, "product.json"))
        if not isinstance(new_prod, dict) or new_prod.get("engine") != ENGINE_ID:
            raise Refusal("This has to run from inside the NEW engine's folder, and this folder does not look "
                          "like one (its product.json is missing or names another product).")
        self.new_v = str(new_prod.get("version") or "0.0.0")
        old = _normalize_arg(old_arg)
        if not old:
            raise Refusal(f"Tell me where your old engine folder is:  {_py()} scripts/bring-over.py \"<folder>\"  "
                          f"(or {_py()} scripts/bring-over.py --find to look for it).")
        if not os.path.isdir(old):
            raise Refusal(f"I can't find a folder at {old}. Check the spelling, or run {_py()} "
                          f"scripts/bring-over.py --find and I will look for it.")
        if os.path.samefile(old, ROOT):
            raise Refusal("That is this engine's own folder. Point me at your OLD engine's folder instead.")
        old_prod = _read_json(os.path.join(old, "product.json"))
        if not isinstance(old_prod, dict) or old_prod.get("engine") != ENGINE_ID:
            below = _engines_below(old)
            hint = (" It has one inside it, though: " + "; ".join(below) + ". Point me at that one.") if below else ""
            raise Refusal(f"{old} does not look like a Reels Editing Engine folder (there is no product.json in it "
                          f"that says so).{hint}")
        self.old_v = str(old_prod.get("version") or "0.0.0")
        if semver(self.old_v)[0] >= semver(self.new_v)[0]:
            raise Refusal(f"That engine is already v{self.old_v}, and this one is v{self.new_v}. This moves an "
                          f"older version's work into a newer one, so there is nothing to bring over from it.")
        self.old = os.path.abspath(old)
        # The engine's own modules (packs, settings, her record of changes) write into these folders directly, past
        # _guard. One that is a link into the old folder would carry those writes into the old engine, which this
        # command promises to leave exactly as it is.
        if not _inside(ROOT, self.old):
            for rel in ("_local", "product", "presets", ".claude", "projects", "inbox", "assets"):
                p = os.path.join(ROOT, rel)
                if os.path.exists(p) and _inside(p, self.old):
                    raise Refusal(f"This engine's {rel} folder is a link into your old engine's folder, so bringing "
                                  f"your work over would write into the old one, which this never does. Make {rel} "
                                  f"a real folder in this engine (move the link aside), then run this again. "
                                  f"Nothing was changed.")
        self.E = Engine()
        self.history = History.load(history or os.path.join(ROOT, *HISTORY_REL.split("/")))
        self.tmp = tempfile.mkdtemp(prefix="bring-over-")
        self._arch = False
        self.files = self._index(self.old)
        self.renamed_here = {}                   # this version's path -> the old engine's path, for renamed files
        if self.history:
            for rel in self.files:
                new_rel = self.history.renamed.get(path_key(rel))
                if new_rel:
                    self.renamed_here[new_rel] = rel

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)   # the scratch views this run made, outside both engines

    # -- the old engine, read through this version's names ----------------------------------------
    def _index(self, base):
        """Every file of the engine itself in a tree (her projects, inbox, _local and the engine's own
        working folders are handled on their own). A new engine unzipped INSIDE the old one is not part of it."""
        out, apart = {}, not _inside(base, ROOT)
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = _rel(dirpath, base)
            rel_dir = "" if rel_dir == "." else rel_dir
            keep = []
            for d in sorted(dirnames):
                full = os.path.join(dirpath, d)
                if os.path.islink(full) or d in SKIP_DIR_NAMES or "venv" in d.lower():
                    continue
                if not rel_dir and d in TOP_HANDLED:
                    continue
                if apart and _inside(full, ROOT):
                    continue
                keep.append(d)
            dirnames[:] = keep
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                if not os.path.islink(full):
                    out[(rel_dir + "/" + fn) if rel_dir else fn] = full
        return out

    def old_file(self, new_rel, base=None):
        """The old engine's copy of the file that is `new_rel` in this version (or None). With `base`, the
        same inside another tree the old engine kept, such as an update backup."""
        if base is None:
            rel = self.renamed_here.get(new_rel, new_rel)
            p = os.path.join(self.old, *rel.split("/"))
            return p if os.path.isfile(p) else None
        p = os.path.join(base, *new_rel.split("/"))
        if os.path.isfile(p):
            return p
        if self.history:
            for rel, full in self._index(base).items():
                if self.history.renamed.get(path_key(rel)) == new_rel:
                    return full
        return None

    def new_path(self, rel):
        return os.path.join(ROOT, *rel.split("/"))

    def view(self, name, files):
        """A scratch tree holding old files at THIS version's paths, so the engine's own readers (which know
        only this version's paths) can read them. A file given as None is written empty: a reader that
        does not find one falls back to this engine's live copy, which would be the wrong one."""
        d = os.path.join(self.tmp, name)
        for rel, src in files.items():
            dst = os.path.join(d, *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if src:
                shutil.copy2(src, dst)
            else:
                open(dst, "w", encoding="utf-8").close()
        return d

    def old_originals(self):
        """The originals archive an old engine keeps when it took the update that carries it, or None."""
        if self._arch is False:
            self._arch = None
            path = os.path.join(self.old, *self.E.kc.STORE_REL.split("/"))
            if os.path.isfile(path):
                arch = self.E.kc.Originals(path)
                self._arch = arch if arch.ok else None
        return self._arch

    def original_text(self, old_rel, mine):
        """The shipped text her change started from, when the old engine can say (its originals archive)."""
        arch = self.old_originals()
        if not arch:
            return None
        try:
            _sha, text = arch.base_for(old_rel, self.old_v, mine)
        except Exception:  # noqa: BLE001
            return None
        return text


def _normalize_arg(parts):
    """A folder as she typed or pasted it: quotes, a trailing slash, ~, and Git Bash's /c/... form."""
    if not parts:
        return ""
    raw = " ".join(parts) if isinstance(parts, (list, tuple)) else str(parts)
    raw = raw.strip().strip('"').strip("'").strip()
    if not raw:
        return ""
    if os.name == "nt":
        m = re.match(r"^/([a-zA-Z])(/.*)?$", raw)
        if m:
            raw = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    raw = os.path.expanduser(raw)
    return os.path.abspath(raw.rstrip("/\\") or raw)


def _engine_at(path):
    prod = _read_json(os.path.join(path, "product.json"))
    return str(prod.get("version") or "?") if isinstance(prod, dict) and prod.get("engine") == ENGINE_ID else None


def _engines_below(path):
    out = []
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return out
    for n in names:
        p = os.path.join(path, n)
        if os.path.isdir(p) and not n.startswith("."):
            v = _engine_at(p)
            if v:
                out.append(f"{p} (v{v})")
    return out[:3]


# ── writes: every one lands inside this engine, never in the old folder ─────────────────────────────
def _guard(ctx, path):
    """Every write lands inside this engine, and never in the old one. (When this engine was unzipped inside
    the old folder, its own subtree is not part of the old engine: writes there are this engine's.)"""
    if not _inside(path, ROOT) or (_inside(path, ctx.old) and not _inside(ROOT, ctx.old)):
        raise RuntimeError(f"refusing to write outside this engine: {path}")


def _write_bytes(ctx, path, data):
    _guard(ctx, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".bringing-over"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _write_text(ctx, path, text):
    _guard(ctx, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".bringing-over"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _write_json(ctx, path, data, indent=2):
    _write_text(ctx, path, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")


def _cp_clone(src, dst):
    """macOS: copy through `cp -c`, which clones (no extra room) where the disk can and copies otherwise."""
    r = subprocess.run(["cp", "-c", "-R", "-p", src, dst], capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout or "cp failed").strip().splitlines()[-1])


def _copy_file(ctx, src, dst, clone=False):
    _guard(ctx, dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".bringing-over"
    if clone and sys.platform == "darwin" and shutil.which("cp"):
        _cp_clone(src, tmp)
    else:
        shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _copy_tree(ctx, src, dst):
    """A whole folder (one of her projects). It lands under a temporary name and takes its real name only
    once complete, so a copy that is interrupted is never mistaken for a finished one; the next run picks up
    where it stopped."""
    _guard(ctx, dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = os.path.join(os.path.dirname(dst), "." + os.path.basename(dst) + ".bringing-over")
    if sys.platform == "darwin" and shutil.which("cp"):
        _cp_clone(src.rstrip("/") + "/." if os.path.isdir(tmp) else src, tmp)
    else:
        shutil.copytree(src, tmp, symlinks=True, dirs_exist_ok=True)
    os.rename(tmp, dst)


def _same_file(a, b):
    try:
        return filecmp.cmp(a, b, shallow=False)       # compared in small chunks: footage never fills memory
    except OSError:
        return False


def _clone_ok(src_file):
    """Can this disk clone her footage (copy-on-write, so the copy takes no extra room)? Asked of the disk
    itself, with the real system call `cp -c` uses, on one scratch file that is removed straight away."""
    if sys.platform != "darwin" or not src_file or os.environ.get("BRING_OVER_NO_CLONES"):   # (tests: a PC)
        return False
    try:
        import ctypes
        import ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib", use_errno=True)
        clonefile = libc.clonefile
        clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    except Exception:  # noqa: BLE001
        return False
    probe = None
    try:
        probe = tempfile.mkdtemp(prefix=".bring-over-probe-", dir=ROOT)
        return clonefile(os.fsencode(src_file), os.fsencode(os.path.join(probe, "probe")), 0) == 0
    except Exception:  # noqa: BLE001
        return False
    finally:
        if probe:
            shutil.rmtree(probe, ignore_errors=True)


def _one_file(ctx, plan, group, label, src, new_rel, merge=None, clone=False, agg=None):
    """One file of hers: copied when this engine has none, left alone when it already has the same one,
    merged when it is a merge-able settings file, otherwise saved for her and listed."""
    dst = ctx.new_path(new_rel)
    size = os.path.getsize(src)
    if not os.path.exists(dst):
        return plan.add(group, label, "bring", new_rel, size, lambda: _copy_file(ctx, src, dst, clone), agg)
    if _same_file(src, dst):
        return plan.add(group, label, "already", new_rel, agg=agg)
    if merge:
        old, new = _read_json(src), _read_json(dst)
        if isinstance(old, dict) and isinstance(new, dict):
            merged = merge(old, new)
            if merged == new:
                return plan.add(group, label, "already", new_rel, agg=agg)
            return plan.add(group, label, "bring", new_rel + " (added to the one here)", size,
                            lambda: _write_json(ctx, dst, merged), agg)
    plan.hand(new_rel, "this engine already has its own copy of this file, so yours was not written over it",
              src=src)
    return None


def has_blank_fields(data):
    """True while a brand kit still has a field to fill: a line with {{...}} (or an older copy's <<...>>).
    The example `{{this}}` in a 2.2.0-2.2.2 kit's how-to line is not a field, so a filled-in kit of that age
    reads as filled in."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    return any(("{{" in ln or "<<" in ln) and "{{this}}" not in ln for ln in text.splitlines())


# ── 1. brand kit ────────────────────────────────────────────────────────────────────────────────────
def plan_brand_kit(ctx, plan):
    src, dst = ctx.old_file("brand-kit.md"), ctx.new_path("brand-kit.md")
    data = _read_bytes(src)
    if data is None or (ctx.history and ctx.history.shipped_bytes(data)):
        return                                           # the blank one a release shipped: nothing of hers
    have = _read_bytes(dst)
    if have == data:
        plan.add("brand", "your brand kit", "already")
    elif have is None or has_blank_fields(have):
        # This engine's is still the blank one: it still has the blank fields the fresh-install count sees
        # ({{...}}, or <<...>> in a copy from before them).
        # If it is not exactly a blank one a release shipped, it is kept for her before hers goes in.
        def run():
            if have is not None and not (ctx.history and ctx.history.shipped_bytes(have)):
                _write_bytes(ctx, ctx.new_path(f"{ctx.E.kc.SAVED_REL}/{FROM}/brand-kit.new-engine.md"), have)
            _write_bytes(ctx, dst, data)
        plan.add("brand", "your brand kit", "bring", "brand-kit.md (yours replaces the blank one)", len(data), run)
    else:
        plan.hand("brand-kit.md", "this engine's brand kit is already filled in, so yours was not written over it",
                  data=data)


# ── 2. CLAUDE.md: her profile and look note into the NEW instructions ────────────────────────────────
def plan_claude_md(ctx, plan):
    src, dst = ctx.old_file("CLAUDE.md"), ctx.new_path("CLAUDE.md")
    old_text, new_text = _read_text(src), _read_text(dst)
    if old_text is None or new_text is None:
        return
    mcm = ctx.E.mcm
    tpl_rel = _rel(mcm.TEMPLATE)
    new_tpl = _read_text(ctx.new_path(tpl_rel))
    old_tpl = _read_text(ctx.old_file(tpl_rel))
    old_lines, new_lines = old_text.split("\n"), new_text.split("\n")

    def region(lines, block):
        r = mcm._region(lines, block)
        return None if r is None else lines[r[0]:r[1]]

    blanks = [t.split("\n") for t in (old_tpl, new_tpl) if t]
    # A region she never filled in is still the engine's own blank one: this version's own text stays.
    adj, spans, carried = list(old_lines), [], []
    for b in mcm.BLOCKS:
        r_old, r_new = mcm._region(old_lines, b), mcm._region(new_lines, b)
        if r_old is None:
            continue
        mine = old_lines[r_old[0]:r_old[1]]
        if any(region(bl, b) == mine for bl in blanks):
            if r_new is not None:
                spans.append((r_old, new_lines[r_new[0]:r_new[1]]))
        else:
            carried.append(b)
    for (start, end), repl in sorted(spans, key=lambda s: s[0][0], reverse=True):
        adj[start:end] = repl
    what = " and ".join(b["what"] for b in carried) or "your creator profile"
    old_bytes = _read_bytes(src)

    if carried:
        merged, _note = mcm.merge("\n".join(adj), new_text)
        tpl_lines = new_tpl.split("\n") if new_tpl else None
        own_here = [b for b in carried if tpl_lines is not None and region(new_lines, b) is not None
                    and region(tpl_lines, b) is not None and region(new_lines, b) != region(tpl_lines, b)
                    and region(new_lines, b) != region(old_lines, b)]
        if merged is None:
            plan.hand("CLAUDE.md", "your old CLAUDE.md is missing the lines that mark where your creator profile "
                                   "starts and ends, so it could not be dropped into the new instructions; it is "
                                   "saved whole", data=old_bytes)
        elif merged == new_text:
            plan.add("brand", what + " (CLAUDE.md)", "already")
        elif own_here:
            plan.hand("CLAUDE.md", "this engine's CLAUDE.md already has a creator profile of its own, so yours was "
                                   "not written over it", data=old_bytes)
        else:
            plan.add("brand", what, "bring", "CLAUDE.md, inside the new instructions", len(merged.encode("utf-8")),
                     lambda: _write_text(ctx, dst, merged))

    # Any other line she (or her Claude) added. The old instructions with her profile in place are exactly
    # what her file would be without them: the same comparison the update's finishing step makes.
    if old_tpl is None:
        if old_text.strip():
            plan.hand("CLAUDE.md", "your old engine has no copy of its own instructions to compare with, so a line "
                                   "you may have added to CLAUDE.md could not be picked out; your whole old file is "
                                   "saved for Claude to look through with you", data=old_bytes)
        return
    base, _note = mcm.merge(old_text, old_tpl)
    if base is None or base == old_text:
        return
    sm = difflib.SequenceMatcher(None, base.split("\n"), old_lines, autojunk=False)
    added = sum(j2 - j1 for tag, _i1, _i2, j1, j2 in sm.get_opcodes() if tag in ("insert", "replace"))
    plan.hand("CLAUDE.md", f"you added {added} line{'s' if added != 1 else ''} of your own to the instructions in your "
                           f"old engine, and the new instructions do not have them yet", data=old_bytes, base=base)


# ── 3. style packs ─────────────────────────────────────────────────────────────────────────────────
def _old_backups(ctx):
    """The old engine's update backups, newest first, as pack_persist.backups() orders its own."""
    root = os.path.join(ctx.old, "_update-backups")
    try:
        names = os.listdir(root)
    except OSError:
        return []
    found = []
    for n in names:
        ow = os.path.join(root, n, "overwritten")
        if os.path.isdir(ow):
            found.append((ctx.E.pp._stamp(n), os.path.getmtime(os.path.join(root, n)), n, ow))
    found.sort(reverse=True)
    return [(n, ow) for _s, _m, n, ow in found]


def _palettes_as_shipped(ctx, text, launch):
    """True when the old pack_palettes.py is exactly one a release shipped once her own packs' lines are
    taken out: then none of the engine's own packs had its colours changed."""
    pw = ctx.E.pw
    try:
        t = text.replace("\r\n", "\n")
        mine = {k for keys in pw._dict_entries(t).values() for k in keys} - set(launch)
        for n in sorted(mine):
            t = pw._remove_entries(t, n)
    except Exception:  # noqa: BLE001
        return False
    return ctx.history.shipped_bytes(t.encode("utf-8"))


def _launch_history(ctx, old_launch, old_packs, old_pal):
    """What each of the engine's own packs looked like as SHIPPED, in the shape pack_persist.adopt_edited()
    compares against: this engine's own copy, every v1 block the fingerprints recognise, the old palette
    lines when the old file is a shipped one, and the old engine's originals archive when it has one."""
    pp = ctx.E.pp
    blocks = collections.defaultdict(set)
    entries = collections.defaultdict(lambda: collections.defaultdict(set))
    shipped_now, live_now = pp._shipped_packs()
    pal_now = _read_text(pp.PALETTES) or ""
    for n in (shipped_now or ()):
        blocks[n].add(pp._canon(live_now[n]))
        for k, v in (pp.palette_entries_in(pal_now, n) or {}).items():
            entries[n][k].add(pp._canon(v))
    if ctx.history:
        for n in old_launch:
            if launch_pack_key(n, old_packs[n]) in ctx.history.launch_packs:
                blocks[n].add(pp._canon(old_packs[n]))
        if old_pal and _palettes_as_shipped(ctx, old_pal, old_launch):
            for n in old_launch:
                for k, v in (pp.palette_entries_in(old_pal, n) or {}).items():
                    entries[n][k].add(pp._canon(v))
    arch = ctx.old_originals()
    if arch:
        rp = ctx.renamed_here.get(_rel(pp.PACKS_JSON), _rel(pp.PACKS_JSON))
        rq = ctx.renamed_here.get(_rel(pp.PALETTES), _rel(pp.PALETTES))
        texts, seen = [], set()
        for files in arch.versions.values():
            pair = (files.get(rp), files.get(rq))
            if pair not in seen:
                seen.add(pair)
                texts.append(tuple(arch.text_of(h) if h else None for h in pair))
        hist = pp.shipped_history(texts)
        for n, canon in hist.get("blocks", {}).items():
            blocks[n] |= canon
        for n, per in hist.get("entries", {}).items():
            for k, canon in per.items():
                entries[n][k] |= canon
    return {"blocks": dict(blocks), "entries": {n: dict(e) for n, e in entries.items()}}


def plan_packs(ctx, plan):
    """Every pack she built, wherever the old engine still has it, newest truth first: its pack files, then
    its protected copy, then each update backup (the only place a pack an earlier update deleted survives).
    A pack she deleted for good stays deleted. Returns what the default-pack and adopt steps need."""
    pp, pw = ctx.E.pp, ctx.E.pw
    info = {"names": set(), "renamed": {}, "adopted": {}, "adopt_run": None}
    rel_packs, rel_pal, rel_side = _rel(pp.PACKS_JSON), _rel(pp.PALETTES), _rel(pp.SIDECAR)
    old_packs_file, old_pal_file = ctx.old_file(rel_packs), ctx.old_file(rel_pal)
    live = ctx.view("packs-live", {rel_packs: old_packs_file, rel_pal: old_pal_file})
    old_launch, old_packs = pp._shipped_packs(live)
    old_launch, old_pal = old_launch or set(), _read_text(old_pal_file)
    side = _read_json(ctx.old_file(rel_side))
    side = side if isinstance(side, dict) else {}
    gone = {n for n in (side.get("forgotten") or []) if isinstance(n, str)} | set(pp.forgotten())

    cands, seen = [], set()

    def offer(name, rec, where):
        if name not in seen and name not in gone:
            seen.add(name)
            cands.append((name, rec, where))

    if old_packs is None:
        if old_packs_file:
            plan.notes.append("Your old style-packs.json could not be read, so your packs were looked for in its "
                              "saved copy and in its update backups instead.")
    else:
        for name, block in old_packs.items():
            if name not in old_launch:
                # a damaged entry cannot be rebuilt, but it is kept exactly as it is, like pack_persist does
                offer(name, pp.capture(name, live) or {"block": block, "recipe": None, "palette": {},
                                                          "system_fonts": {}}, "")
    for name, rec in (side.get("packs") if isinstance(side.get("packs"), dict) else {}).items():
        if isinstance(rec, dict):
            offer(name, rec, "your old engine's saved copy")
    for i, (folder, ow) in enumerate(_old_backups(ctx)):
        packs_file = ctx.old_file(rel_packs, ow)
        if not packs_file:
            continue
        v = ctx.view(f"packs-backup-{i}", {rel_packs: packs_file, rel_pal: ctx.old_file(rel_pal, ow) or old_pal_file})
        b_launch, b_packs = pp._shipped_packs(v)
        for name in (b_packs or {}):
            if name not in (b_launch or set()):
                rec = pp.capture(name, v)
                if rec is not None:
                    offer(name, rec, f"an old update backup ({folder})")

    known = pp.load()
    shipped_now, live_now = pp._shipped_packs()
    shipped_now, live_now = shipped_now or set(), live_now or {}
    taken = set(live_now) | set(known)
    record, clash = [], []
    # A pack whose saved copy is already in this engine but whose pack files are not: a run that stopped between
    # the two writes. It is hers, it is saved, and it still has to be written where builds read it.
    missing = []

    def already(name_here, label_done, label_bring):
        if name_here in live_now:
            plan.add("packs", label_done, "already")
        else:
            missing.append(name_here)
            plan.add("packs", label_bring, "bring", PACKS_WHERE)

    for name, rec, where in cands:
        kind = ("your own colors, fonts and accent" if (rec.get("recipe") or rec.get("palette"))
                else "your fonts and accent")
        label = f'"{name}": {kind}' + (f", found in {where}" if where else "")
        if name in shipped_now:
            same = next((n for n, s in known.items() if n != name and pp._same(s, rec)), None)
            if same:
                info["renamed"][name] = same
                already(same, f'"{name}", here as "{same}"', label + f'. It comes across as "{same}"')
                continue
            new = pp._free_name(name, taken)
            if not new:
                plan.hand(f'style pack "{name}"', "this engine ships a pack with the same name and no free name was "
                          "left for yours; it is saved", save_as=f"style-packs/{name}.json",
                          data=json.dumps(rec, indent=2, ensure_ascii=False).encode("utf-8"))
                continue
            taken.add(new)
            info["renamed"][name] = new
            info["names"].add(new)
            clash.append((name, new, rec))
            plan.add("packs", label + f'. This engine ships its own "{name}", so yours comes across as "{new}"',
                     "bring", PACKS_WHERE)
        elif name in known or name in live_now:
            saved, cur = known.get(name), (pp.capture(name) if name in live_now else None)
            if (saved is not None and pp._same(saved, rec)) or (cur is not None and pp._same(cur, rec)):
                info["names"].add(name)
                already(name, f'"{name}"', label)
            else:
                plan.hand(f'style pack "{name}"', "this engine already has a different pack with this name, so yours "
                          "was not written over it; it is saved", save_as=f"style-packs/{name}.json",
                          data=json.dumps(rec, indent=2, ensure_ascii=False).encode("utf-8"))
        else:
            taken.add(name)
            info["names"].add(name)
            record.append((name, rec, where))
            plan.add("packs", label, "bring", PACKS_WHERE)

    registered = bool(record or clash or missing)
    if registered:
        def run():
            for name, rec, where in record:
                pp.record(name, rec.get("block"), rec.get("recipe"), rec.get("palette"), rec.get("system_fonts"),
                          f"your old engine (v{ctx.old_v})" + (f", {where}" if where else ""), rec.get("unreadable"))
            restored, problems = pp.restore()          # also writes every saved pack the pack files are missing
            for name, why in problems:
                if name in {r[0] for r in record} | set(missing):
                    plan.hand_notes.append(f'style pack "{name}": {why}')
            for name, new, rec in clash:
                problems = pw.restore_pack(new, rec)
                pp.record_live(new, f'your old engine (v{ctx.old_v}), where it was called "{name}"')
                plan.hand_notes += [f'style pack "{new}": {why}' for why in problems]
        plan.step(run)

    # One of the engine's OWN packs she changed in place ("keep Butter but make the blue pink") comes across
    # as a pack of her own, "My Butter", exactly as an update treats it (pack_persist.adopt_edited).
    if old_packs is not None and old_launch:
        hist = _launch_history(ctx, old_launch, old_packs, old_pal)
        pending = []
        for n, block in old_packs.items():
            if n not in old_launch or not hist["blocks"].get(n):
                continue
            her = (pp.palette_entries_in(old_pal, n) or {}) if old_pal else {}
            known_entries = hist["entries"].get(n, {})
            if (pp._canon(block) in hist["blocks"][n] and
                    not any(k in known_entries and pp._canon(v) not in known_entries[k] for k, v in her.items())):
                continue                                  # exactly as the engine shipped it
            own = dict(block)
            own["in_launch_kit"] = False
            recipe = her if all(k in her for k in pp._RECIPE_KEYS.values()) else None
            same = next((m for m, s in known.items() if pp._canon(s.get("block")) == pp._canon(own)
                         and pp._canon(s.get("recipe")) == pp._canon(recipe)), None)
            if same:
                info["adopted"][n] = same
                info["names"].add(same)
                already(same, f'your changed "{n}", here as "{same}"', f'your changed "{n}", here as "{same}"')
                continue
            new = pp._free_name(n, taken)
            if not new:
                plan.hand_notes.append(f'your changed "{n}" could not be given a free name, so it did not come across')
                continue
            taken.add(new)
            info["adopted"][n] = new
            info["names"].add(new)
            pending.append(n)
            plan.add("packs", f'your changed "{n}", saved as a pack of your own: "{new}"', "bring", PACKS_WHERE)
        if pending:
            def adopt():
                done, problems = pp.adopt_edited(live, hist)
                plan.adopted += done
                plan.hand_notes += [f'style pack "{n}": {why}' for n, why in problems]
            info["adopt_run"] = adopt
    if missing and not registered:                  # only her changed launch pack's saved copy was left unwritten
        def rewrite():
            _restored, problems = pp.restore()
            plan.hand_notes += [f'style pack "{n}": {why}' for n, why in problems if n in missing]
        plan.step(rewrite)
    return info


def plan_default_pack(ctx, plan, packs):
    """Her default pack and accent (user-style.json), pointed at the pack as it is called here."""
    pp = ctx.E.pp
    rel = _rel(pp.USER_STYLE)
    old, new = _read_json(ctx.old_file(rel)), _read_json(ctx.new_path(rel))
    if not isinstance(old, dict):
        return
    mine = {k: v for k, v in old.items() if k != "_doc"}
    if not (mine.get("default_pack") or mine.get("default_accent")):
        return
    new = new if isinstance(new, dict) else {}
    want = dict(new)
    want.update(mine)
    name = mine.get("default_pack")
    if name in packs["renamed"]:
        want["default_pack"] = packs["renamed"][name]
    elif name in packs["adopted"] and packs["adopted"][name] in pp.load():
        want["default_pack"] = packs["adopted"][name]    # brought over before: it is her own copy now
    if want.get("default_pack"):
        _shipped, live = pp._shipped_packs()
        here = set(live or {}) | packs["names"] | set(_local_pack_names(ctx))
        if want["default_pack"] not in here:
            plan.hand_notes.append(f'your default pack was "{name}", and it is not in your old engine or anywhere in '
                                   f'it, so no default is set here yet. Pick one ("use Butter"), or rebuild it '
                                   f'("build my own style pack")')
            want["default_pack"] = new.get("default_pack")
    bits = [f'"{want["default_pack"]}"' if want.get("default_pack") else None,
            f'accent {want["default_accent"]}' if want.get("default_accent") else None]
    label = "your default look: " + ", ".join(b for b in bits if b)
    if want == new:
        plan.add("packs", label, "already")
    else:
        plan.add("packs", label, "bring", rel, run=lambda: _write_json(ctx, ctx.new_path(rel), want))


def _local_pack_names(ctx):
    names = set()
    for base in (ROOT, ctx.old):
        d = _read_json(os.path.join(base, "_local", "style-packs.json"))
        if isinstance(d, dict) and isinstance(d.get("packs"), dict):
            names |= set(d["packs"])
    return names


# ── 4. _local and her files in the vault ───────────────────────────────────────────────────────────
def _local_skipped(rel):
    parts = rel.split("/")
    name = parts[-1]
    if parts[0] == "render-log" or "__pycache__" in parts:
        return True                        # the live record of the OLD engine's renders: its own, not hers
    if rel == "kept-settings.json":
        return True                        # the settings step reads and writes it
    if rel.startswith(f"my-changes/{FROM}/"):
        return True
    if name.endswith(".ok") or name == "machine.txt":
        return True                        # markers, and the machine report every session rewrites
    return name in JUNK_NAMES or name.endswith((".tmp", ".bringing-over"))


def plan_local(ctx, plan):
    base = os.path.join(ctx.old, "_local")
    if not os.path.isdir(base):
        return
    kc = ctx.E.kc
    doc_rel = kc.DOC_REL.split("/", 1)[1]            # my-changes.md
    files = [(r, os.path.join(base, *r.split("/"))) for r, _n in _tree_files(base) if not _local_skipped(r)]
    if not files:
        return
    counts = collections.Counter()
    todo, same, total = [], 0, 0
    for rel, src in files:
        dst = ctx.new_path("_local/" + rel)
        if rel == doc_rel:                           # her record of changes: kept, with this engine's own on top
            old_doc, new_doc = _read_text(src) or "", _read_text(dst)
            body = old_doc[len(kc._HEAD):] if old_doc.startswith(kc._HEAD) else old_doc
            if new_doc is None:
                todo.append((rel, lambda s=src, d=dst: _copy_file(ctx, s, d)))
            elif body.strip() and body.strip() not in new_doc:
                todo.append((rel, lambda d=dst, n=new_doc, b=body: _write_text(ctx, d, n.rstrip("\n") + "\n\n" + b.lstrip("\n"))))
            else:
                same += 1
            counts["record"] += 1
            continue
        if not os.path.exists(dst):
            todo.append((rel, lambda s=src, d=dst: _copy_file(ctx, s, d)))
            total += os.path.getsize(src)
        elif _same_file(src, dst):
            same += 1
        else:
            plan.hand("_local/" + rel, "this engine already has its own copy of this file, so yours was not written "
                                       "over it", save_as="_local/" + rel, src=src)
            continue
        counts[_local_kind(rel)] += 1

    learned = _read_json(os.path.join(base, "learned.json"))
    n_prefs = len(learned.get("preferences") or []) if isinstance(learned, dict) else 0
    n_sounds = sum(1 for r, _src in files if r.startswith("sounds/"))
    bits = []
    for kind in ("learned", "sounds", "words", "packs", "record", "machine", "other"):
        if counts[kind]:
            bits.append({"learned": f"{n_prefs} learned preference{'s' if n_prefs != 1 else ''}",
                         "sounds": f"your favorite sounds ({n_sounds} saved)" if n_sounds else "your favorite sounds",
                         "words": "your own word list", "packs": "your local style packs",
                         "record": "your record of changes to the old engine",
                         "machine": "notes about this computer",
                         "other": f"{counts['other']} other saved file{'s' if counts['other'] != 1 else ''}"}[kind])
    label = "in _local/: " + ", ".join(bits)
    if todo:
        def run():
            for _rel_, fn in todo:
                fn()
        plan.add("taught", label, "bring", "_local/", total, run)
    elif same:
        plan.add("taught", label, "already")


def _local_kind(rel):
    if rel.startswith("learned.json"):
        return "learned"
    if rel == "favorites.json" or rel.startswith("sounds/"):
        return "sounds"
    if rel == "caption-corrections.json":
        return "words"
    if rel == "style-packs.json":
        return "packs"
    if rel.startswith("my-changes"):
        return "record"
    if rel in ("install-route.json", "machine-notes.md"):
        return "machine"
    return "other"


def plan_vault(ctx, plan):
    sp = ctx.E.sp
    for rel, label in ((USER_EFFECTS_REL, "the text animations you named"),
                       (FONT_OVERRIDES_REL, "the fonts you matched up by hand")):
        src = ctx.old_file(rel)
        if src:
            _one_file(ctx, plan, "taught", label, src, rel)
    src = ctx.old_file(DRAFT_SNAPSHOTS_REL)
    if src:
        # entries this engine already has win; the old engine's fill in the drafts it does not know yet
        _one_file(ctx, plan, "taught", "what the engine knows about your CapCut drafts (so it can tell your own "
                  "edits apart)", src, DRAFT_SNAPSHOTS_REL, merge=lambda old, new: sp._merge_into(old, new))


# ── 5. her words ───────────────────────────────────────────────────────────────────────────────────
def plan_words(ctx, plan):
    upd = ctx.E.upd
    merge_json = getattr(upd, "MERGE_JSON", None) or {}
    for rel, merger in merge_json.items():
        src, dst = ctx.old_file(rel), ctx.new_path(rel)
        data = _read_bytes(src)
        if data is None or (ctx.history and ctx.history.shipped_bytes(data)):
            continue                                     # exactly as a release shipped it: nothing of hers
        old, new = _read_json(src), _read_json(dst)
        if not isinstance(old, dict):
            plan.hand(rel, "your old word list could not be read, so its words did not come across", data=data)
            continue
        new = new if isinstance(new, dict) else {}
        if ctx.history and ctx.history.words:
            # Entries an old release shipped, which this version dropped on purpose: the engine's, not hers.
            # (A release kept its one-word table under "auto" and its check list under "flag", or under the
            # current "words" and "check"; the history fingerprints both as "auto" and "flag".)
            old = dict(old)
            for key in ("flag", "check"):
                if key in old:
                    old[key] = [f for f in (old.get(key) or []) if not ctx.history.shipped_word("flag", f)]
            for key in ("auto", "words"):
                if key in old:
                    old[key] = {k: v for k, v in (old.get(key) or {}).items()
                                if not ctx.history.shipped_word("auto", k, v)}
        merged = merger(old, new)                        # the updater's own rule: her entry wins on the same word
        one_word = lambda t: {**(t.get("words") or {}), **(t.get("auto") or {})}
        to_check = lambda t: list(t.get("check") or []) + list(t.get("flag") or [])
        words = sorted(k for k, v in one_word(old).items() if one_word(new).get(k) != v)
        flags = [f for f in to_check(old) if f not in to_check(new)]
        shown = words + [f for f in flags if f not in words]
        label = ("your words in the caption word list" + (f": {', '.join(shown[:8])}" if shown else "")
                 + (f" and {len(shown) - 8} more" if len(shown) > 8 else ""))
        if merged == new:
            plan.add("words", "your words in the caption word list", "already")
        else:
            plan.add("words", label, "bring", rel + " (merged: new defaults arrive, your words win)",
                     run=lambda d=dst, m=merged: _write_json(ctx, d, m))
    if not merge_json and ctx.old_file("presets/caption-corrections.json"):
        plan.hand_notes.append("the words you added to the caption word list could not be merged in (this engine's "
                               "updater could not be read); your old word list is still in your old folder")


# ── 6. her settings inside engine files ─────────────────────────────────────────────────────────────
def _harvest_into(ctx, base, seed=None):
    """settings_persist.harvest() of one tree into a scratch record instead of this engine's own, so a preview
    reads her settings exactly the way the real run will, and writes nothing here."""
    sp = ctx.E.sp
    side = os.path.join(tempfile.mkdtemp(dir=ctx.tmp), "kept-settings.json")
    real = sp.SIDECAR
    sp.SIDECAR = side
    try:
        if seed:
            sp._save(seed)
        kept, problems = sp.harvest(base)
        return kept, problems, sp.load()
    finally:
        sp.SIDECAR = real


def _const_value(rec):
    rec = rec or {}
    if "value" in rec:
        return rec["value"]
    try:
        value = ast.literal_eval(rec.get("source") or "")
    except (ValueError, SyntaxError):
        return None
    return list(value) if isinstance(value, tuple) else value


def _settings_held(ctx, have, want):
    """True when `have` (this engine's files) already hold every setting of hers in `want` that this version
    has a place for. One it has no place for is reported once by settings_persist.restore(), and kept."""
    sp = ctx.E.sp
    mine = want.get("claude_settings") or {}
    cur = have.get("claude_settings") or {}
    merge = getattr(sp, "merge_settings", sp._merge_into)
    if mine and merge(cur, mine) != cur:
        return False
    for key, rec in (want.get("constants") or {}).items():
        rel, _sep, var = key.partition("::")
        text = _read_text(ctx.new_path(rel))
        if text is None or sp._constant(text, var) is None:
            continue
        if _const_value((have.get("constants") or {}).get(key)) != _const_value(rec):
            return False
    stem = (want.get("headline_font") or {}).get("stem")
    if not stem or sp._font(_read_text(ctx.new_path(sp.FONT_DOC)) or "") is None:
        return True
    return stem == (have.get("headline_font") or {}).get("stem")


def plan_settings(ctx, plan):
    sp = ctx.E.sp
    rels = [sp.CLAUDE_SETTINGS] + sorted({rel for rel, _v in sp.CONSTANTS}) + [sp.FONT_DOC]
    files = {rel: ctx.old_file(rel) for rel in rels}
    if not any(files.values()):
        return
    view = ctx.view("settings", {rel: src for rel, src in files.items() if src})
    # Her last saved record fills in what the old files alone no longer say (a value an earlier update could
    # not put back). Its entries are keyed by path, so they are keyed by THIS version's paths first.
    seed = _read_json(os.path.join(ctx.old, *_rel(sp.SIDECAR).split("/")))
    if isinstance(seed, dict):
        seed = {k: v for k, v in seed.items() if k not in ("_doc", "saved_at")}
        consts = {}
        for key, rec in (seed.get("constants") or {}).items():
            rel, sep, var = key.partition("::")
            consts[(ctx.history.new_name(rel) if ctx.history else rel) + sep + var] = rec
        if consts:
            seed["constants"] = consts
    else:
        seed = None
    kept, problems, theirs = _harvest_into(ctx, view, seed)
    _k2, _p2, here = _harvest_into(ctx, None)
    fields = ("claude_settings", "constants", "headline_font")
    if not any(theirs.get(f) for f in fields):
        return
    label = "your settings inside engine files: " + ", ".join(kept or ["the ones you set"])
    if _settings_held(ctx, here, theirs):
        plan.add("words", label, "already")
        return
    if any(here.get(f) for f in fields):
        rec = {k: v for k, v in theirs.items() if k not in ("_doc", "saved_at")}
        plan.hand("_local/kept-settings.json", "this engine already has settings of its own (permission mode, hook "
                  "defaults or headline font), so yours were not written over them; they are saved",
                  save_as="kept-settings.json", data=(json.dumps(rec, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        return

    def run():
        if seed and not os.path.exists(sp.SIDECAR):
            sp._save(seed)
        _kept, probs = sp.harvest(view)
        _restored, probs2 = sp.restore()
        plan.hand_notes.extend(f"{what}: {why}" for what, why in list(probs) + list(probs2))
    plan.add("words", label, "bring", "the engine files they live in", run=run)
    plan.hand_notes.extend(f"{what}: {why}" for what, why in problems)


# ── 7. keys, connections, and anything else the updater protects as hers ─────────────────────────────
_ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _env_keys(text):
    return {m.group(1): line for line in (text or "").splitlines() for m in [_ENV_KEY.match(line)] if m}


def plan_secrets(ctx, plan):
    sp = ctx.E.sp
    for rel in SECRETS:
        src = ctx.old_file(rel)
        if not src:
            continue
        dst = ctx.new_path(rel)
        label = {".env": "your keys (.env)", ".mcp.json": "your connected tools (.mcp.json)",
                 "config.json": "your local server settings (config.json)",
                 ".claude/settings.local.json": "your own Claude Code settings (.claude/settings.local.json)"}[rel]
        if rel in (".mcp.json", ".claude/settings.local.json"):
            # both hers: everything in either stays, and this engine's own values win where both set one
            _one_file(ctx, plan, "words", label, src, rel, merge=lambda old, new: sp._merge_into(old, new))
        elif rel == ".env" and os.path.exists(dst) and not _same_file(src, dst):
            old_keys, new_text = _env_keys(_read_text(src)), _read_text(dst) or ""
            new_keys = _env_keys(new_text)
            missing = [k for k in old_keys if k not in new_keys]
            differ = [k for k in old_keys if k in new_keys and old_keys[k].strip() != new_keys[k].strip()]
            if differ:
                plan.hand_notes.append(f"your old .env and the one here set {', '.join(differ)} differently; the one "
                                       f"here was kept (no values are shown). Yours is still in your old folder")
            if missing:
                add = "".join(old_keys[k] + "\n" for k in missing)
                text = new_text + ("" if new_text.endswith("\n") or not new_text else "\n") + add
                plan.add("words", f"your keys (.env: {len(missing)} added to the one here)", "bring", rel,
                         run=lambda d=dst, t=text: _write_text(ctx, d, t))
            else:
                plan.add("words", label, "already")
        else:
            _one_file(ctx, plan, "words", label, src, rel)


def _protected(ctx, rel):
    upd = ctx.E.upd
    if rel.endswith(".bak"):
        return False
    if upd and hasattr(upd, "is_protected"):
        return upd.is_protected(rel)
    return rel.split("/", 1)[0] in {"backbone", "research", "research-lab", "transcripts"} or \
        rel in ("voice-dna.md", "competitor-list.md") or fnmatch.fnmatch(rel, ".env.*")


# ── 8. the old engine's own files: her changes to them, and files she added ────────────────────────────
def _handled(ctx):
    """Paths (as this version names them) a step above already looks after."""
    pp, sp, mcm = ctx.E.pp, ctx.E.sp, ctx.E.mcm
    out = {"brand-kit.md", "CLAUDE.md", "product.json", "CHANGELOG.md", _rel(mcm.TEMPLATE),
           "product/templates/product.engine.json", _rel(pp.PACKS_JSON), _rel(pp.PALETTES), _rel(pp.SIDECAR),
           _rel(pp.USER_STYLE), sp.CLAUDE_SETTINGS, sp.FONT_DOC, USER_EFFECTS_REL, FONT_OVERRIDES_REL,
           DRAFT_SNAPSHOTS_REL}
    out |= {rel for rel, _v in sp.CONSTANTS}
    out |= set(SECRETS)
    out |= set(getattr(ctx.E.upd, "MERGE_JSON", None) or {"presets/caption-corrections.json": None})
    return out


def _generated(rel):
    return any(fnmatch.fnmatch(rel, g) for g in GENERATED)


def _settings_file_changed(ctx, new_rel, src):
    """True when an engine file that holds one of her settings was ALSO changed some other way. Her settings
    are put back to the blank values the engine ships; if the file is then a shipped one, it was not."""
    sp, H = ctx.E.sp, ctx.history
    data = _read_bytes(src)
    if data is None or H.shipped_bytes(data):
        return False
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    variants = [text]
    for var in [v for rel, v in sp.CONSTANTS if rel == new_rel]:
        nxt = []
        for t in variants:
            got = sp._constant(t, var)
            if not got or sp._blank(got[0]) or got[2][0] != got[2][2]:
                nxt.append(t)
                continue
            value, _src, (l1, c1, _l2, c2) = got
            blanks = ('""', "''") if isinstance(value, str) else ("()", "[]") if isinstance(value, (tuple, list)) \
                else ("None",)
            lines = t.split("\n")
            raw = lines[l1 - 1].encode("utf-8")
            for b in blanks:
                line = (raw[:c1] + b.encode("utf-8") + raw[c2:]).decode("utf-8", "replace")
                nxt.append("\n".join(lines[:l1 - 1] + [line] + lines[l1:]))
        variants = nxt
    if new_rel == sp.FONT_DOC:
        font = sp._font(text)
        if font and font["stem"] != sp.SHIPPED_FONT:
            t = text.replace(f"{font['stem']}-{{Black,Bold,Regular}}", f"{sp.SHIPPED_FONT}-{{Black,Bold,Regular}}")
            variants.append(re.sub(rf"\b{re.escape(font['name'])}\b", sp.SHIPPED_FONT, t))
            variants.append(re.sub(rf"\b{re.escape(font['stem'])}\b", sp.SHIPPED_FONT, t))
    return not any(H.shipped_bytes(v.encode("utf-8")) for v in variants)


def plan_engine_files(ctx, plan):
    H = ctx.history
    if not H:
        plan.notes.append("This engine is missing its record of the old versions (" + HISTORY_REL + "), so changes "
                          "you made to the old engine's own files, and files you added to it, could not be picked "
                          "out. Everything else came across.")
        return
    handled, added = _handled(ctx), []
    for rel in sorted(ctx.files):
        src = ctx.files[rel]
        new_rel = H.new_name(rel)
        if new_rel in handled or rel in handled:
            continue
        if _protected(ctx, rel):
            if not (H.shipped_path(rel) and H.shipped_bytes(_read_bytes(src))):
                _one_file(ctx, plan, "words", f"your {rel}", src, rel)
            continue
        if _generated(rel):
            continue
        if H.shipped_path(rel):
            data = _read_bytes(src)
            if H.shipped_bytes(data):
                continue                                 # exactly as a release shipped it: the engine's own
            renamed = f", where it was called `{rel}`" if new_rel != rel else ""
            mine = data.decode("utf-8", "replace") if b"\x00" not in data[:8192] else None
            base = ctx.original_text(rel, mine) if mine is not None else None
            if os.path.isfile(ctx.new_path(new_rel)):
                plan.hand(new_rel, f"you changed this engine file in your old engine{renamed}; your version is saved, "
                                   f"and Claude can bring the change into this version with you", src=src, base=base)
            else:
                plan.hand(new_rel, "this version no longer has this file, and you had changed it", src=src, base=base,
                          removed=True)
        elif rel.startswith(HERS_ADDED):
            added.append(rel)
        elif rel.startswith(RUNTIME_DIRS):
            continue
        else:
            try:
                plan.left.append((rel, os.path.getsize(src)))
            except OSError:
                continue
    sp = ctx.E.sp
    for new_rel in sorted({rel for rel, _v in sp.CONSTANTS} | {sp.FONT_DOC}):
        src = ctx.old_file(new_rel)
        if src and os.path.isfile(ctx.new_path(new_rel)) and _settings_file_changed(ctx, new_rel, src):
            old_rel = ctx.renamed_here.get(new_rel, new_rel)
            renamed = f" (in your old engine it was called `{old_rel}`)" if old_rel != new_rel else ""
            data = _read_bytes(src)
            plan.hand(new_rel, f"besides your settings, this file had other changes in your old engine{renamed}; your "
                               f"settings came across, and the rest of your version is saved",
                      src=src, base=ctx.original_text(old_rel, data.decode("utf-8", "replace")))
    src = ctx.old_file(sp.CLAUDE_SETTINGS)
    data = _read_bytes(src)
    if data is not None and not H.shipped_bytes(data) and os.path.isfile(ctx.new_path(sp.CLAUDE_SETTINGS)):
        try:
            parsed = json.loads(_read_text(src))
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            # Her own settings, permission rules and hooks come across with settings_persist (above); what is left
            # to compare is the engine's own part. An older settings_persist without engine_part() counted every
            # hook as the engine's.
            engine_part = (sp.engine_part(parsed) if hasattr(sp, "engine_part")
                           else {k: v for k, v in parsed.items() if k in ("hooks", "$schema")})
            # The engine's own permission rules are not hers to keep or drop (a permissions block rewritten whole
            # loses them, and the new version brings them back): her hooks-and-rules part matches a release also
            # when it matches with the engine's rules put back where the release had them.
            cands = [engine_part]
            rules = {k: list(v) for k, v in (getattr(sp, "ENGINE_PERMISSIONS", None) or {}).items()}
            if rules:
                bare = {k: v for k, v in engine_part.items() if k != "permissions"}
                cands += [bare, dict({"permissions": rules}, **bare)]
            forms = [json.dumps(c, indent=2, ensure_ascii=a) + "\n" for c in cands for a in (True, False)]
            if not any(H.shipped_bytes(f.encode("utf-8")) for f in forms):
                plan.hand(sp.CLAUDE_SETTINGS, "besides your own settings and hooks (they came across), the engine's own "
                                             "part of this file was changed in your old engine; your whole old file is "
                                             "saved", src=src)
    kinds = {"assets/": "in assets/ (your logos and brand files)", SFX_REL + "/": "in the sound folder (your own sounds)",
             "presets/": "in presets/ (your own presets)"}
    for rel in added:
        where = next(v for k, v in kinds.items() if rel.startswith(k))
        item = _one_file(ctx, plan, "files", rel, ctx.files[rel], rel, clone=True, agg=where)
        if item is not None:
            plan.added.append(rel)


# ── 9. her reels and clips ─────────────────────────────────────────────────────────────────────────
def plan_footage(ctx, plan):
    for top, what in (("projects", "project"), ("inbox", "clip in your inbox")):
        base = os.path.join(ctx.old, top)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            src = os.path.join(base, name)
            if name in JUNK_NAMES or name.endswith(".bringing-over") or os.path.islink(src):
                continue
            if top == "inbox" and name in ("README.md", ".gitkeep"):
                continue                                  # the folder's own note, the engine's
            files = _tree_files(src)
            size = sum(s for _r, s in files)
            agg = "projects" if top == "projects" else "inbox"
            if ctx.no_projects:
                plan.left.append((f"{top}/{name}", size))
                continue
            dst = ctx.new_path(f"{top}/{name}")
            if os.path.exists(dst):
                if sorted(files) == sorted(_tree_files(dst)):
                    plan.add("footage", name, "already", agg=agg)
                else:
                    plan.hand_notes.append(f"a {what} called {name} is already in this engine and it is not the same "
                                           f"one, so yours stayed in your old folder ({top}/{name})")
                continue
            if os.path.isdir(src):
                run = (lambda s=src, d=dst: _copy_tree(ctx, s, d))
            else:
                run = (lambda s=src, d=dst: _copy_file(ctx, s, d, clone=True))
            plan.add("footage", name, "bring", f"{top}/{name}", size, run, agg=agg)


# ── the whole plan ─────────────────────────────────────────────────────────────────────────────────
def build_plan(ctx):
    plan = Plan()
    plan_brand_kit(ctx, plan)
    plan_claude_md(ctx, plan)
    packs = plan_packs(ctx, plan)
    plan_local(ctx, plan)
    plan_vault(ctx, plan)
    plan_default_pack(ctx, plan, packs)
    if packs["adopt_run"]:
        plan.step(packs["adopt_run"])                    # after her default is set: it may point at the change
    plan_words(ctx, plan)
    plan_settings(ctx, plan)
    plan_secrets(ctx, plan)
    plan_engine_files(ctx, plan)
    plan_footage(ctx, plan)
    return plan


# ── report ─────────────────────────────────────────────────────────────────────────────────────────
def _lines_for(items, done):
    """Report lines for one group: footage and added files are summed up per kind, everything else by name."""
    out, aggs = [], collections.OrderedDict()
    for it in items:
        if it.agg:
            aggs.setdefault(it.agg, []).append(it)
        else:
            out.append(f"    {'✓' if done else '+'} {it.label}" + (f"  ({_human(it.size)})" if it.size >= 1 << 20 else "")
                       + (f"  → {it.where}" if it.where else ""))
    for agg, its in aggs.items():
        size = sum(i.size for i in its)
        names = [i.label for i in its]
        head = {"projects": f"{len(its)} project{'s' if len(its) != 1 else ''}",
                "inbox": f"{len(its)} clip{'s' if len(its) != 1 else ''} in your inbox"}.get(
            agg, f"{len(its)} file{'s' if len(its) != 1 else ''} {agg}")
        shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
        dest = {"projects": "  → projects/", "inbox": "  → inbox/"}.get(agg, "  → the same place here")
        out.append(f"    {'✓' if done else '+'} {head}, {_human(size)}: {shown}{dest}")
    return out


def _needs_hand_lines(plan, applied):
    out = []
    for h in plan.hands:
        saved = h.get("saved") or f"_local/my-changes/{FROM}/{h['save_as']}"
        out.append(f"  - {h['path']}: {h['why']}. Yours: {saved}")
    for h in plan.removed:
        saved = h.get("saved") or f"_local/my-changes/{FROM}/{h['save_as']}"
        out.append(f"  - {h['path']}: {h['why']}. Yours: {saved}")
    out += [f"  - {n}" for n in plan.hand_notes]
    return out


def print_report(ctx, plan, applied, room=None):
    print("Bringing over your old engine")
    print(f"  from  {ctx.old}  (v{ctx.old_v})")
    print(f"  into  {ROOT}  (v{ctx.new_v})")
    if not applied:
        print("Preview only: nothing has been copied or changed yet. Your old folder is only ever read.")
    shown = [i for i in plan.items if i.label]
    bring = [i for i in shown if i.status == "bring" and not i.failed]
    already = [i for i in shown if i.status == "already"]
    failed = [i for i in shown if i.failed]
    if bring:
        print("\n" + ("Here is what came across:" if applied else "What comes across:"))
        for key, title in GROUPS:
            its = [i for i in bring if i.group == key]
            if its:
                print(f"\n  {title}")
                for line in _lines_for(its, applied):
                    print(line)
                if key == "footage" and room:
                    print(f"      {room}")
    if already:
        names = [i.label for i in already if not i.agg]
        agg = collections.Counter(i.agg for i in already if i.agg)
        names += [f"{n} {'project' if a == 'projects' else 'clip' if a == 'inbox' else 'file'}{'s' if n != 1 else ''}"
                  + ("" if a in ("projects", "inbox") else f" {a}") for a, n in agg.items()]
        print("\nAlready in this engine, so nothing is brought twice:")
        for n in names:
            print(f"    = {n}")
    if failed:
        print("\nDid not come across this time (run the same command again and it picks up from here):")
        for i in failed:
            print(f"    - {i.label}: {i.failed}")
    hands = _needs_hand_lines(plan, applied)
    if hands:
        where = ("written down in _local/my-changes.md. Say \"bring my changes forward\" and Claude goes through "
                 "each one with you" if applied else "your copy is saved during the move, and Claude goes through each "
                 "one with you afterwards")
        print(f"\nNeeds a hand ({where}):")
        for line in hands:
            print(line)
    if plan.left:
        print(f"\nLeft in your old folder for you to decide ({len(plan.left)} item{'s' if len(plan.left) != 1 else ''} "
              f"outside the places that come across on their own):")
        for rel, size in plan.left[:25]:
            print(f"    - {rel}  ({_human(size)})")
        if len(plan.left) > 25:
            print(f"    - ...and {len(plan.left) - 25} more")
    for n in plan.notes:
        print(f"\n{n}")
    if not bring and not failed:
        print("\nEverything of yours from the old engine is already here. Nothing was brought twice."
              if already else "\nThere was nothing of yours in the old engine to bring over.")
    print("\nKeep your old folder until every reel you started in it is finished: CapCut drafts built there still "
          "point at footage inside it." + (" Nothing in it was changed." if applied else ""))
    if not applied and (bring or plan.hands or plan.removed):
        if getattr(ctx, "full_copy", 0) and not ctx.projects:
            print(f"\nYour projects and inbox clips ({_human(ctx.full_copy)}) would be a second full copy on this disk, "
                  f"so pick one:")
            print(f"  To bring them too:          {_py()} scripts/bring-over.py \"{ctx.old}\" --apply --projects")
            print(f"  To leave them where they are: {_py()} scripts/bring-over.py \"{ctx.old}\" --apply --no-projects")
        else:
            extra = " --no-projects" if ctx.no_projects else " --projects" if ctx.projects else ""
            print(f"\nTo bring it all over:  {_py()} scripts/bring-over.py \"{ctx.old}\" --apply{extra}")


# ── apply ──────────────────────────────────────────────────────────────────────────────────────────
def _room(ctx, plan, probe):
    """(fits, one plain line about room). Footage copies as clones where the disk can, which takes almost no
    room; otherwise it needs its full size."""
    copies = [i for i in plan.items if i.status == "bring" and i.size]
    need = sum(i.size for i in copies)
    free = shutil.disk_usage(ROOT).free
    footage = [i for i in copies if i.group in ("footage", "files")]
    if not need:
        return True, None
    src = None
    if footage:
        for i in footage:
            p = os.path.join(ctx.old, *i.where.split("/")) if i.group == "footage" else ctx.files.get(i.where)
            if p and os.path.isfile(p):
                src = p
                break
            if p and os.path.isdir(p):
                src = next((os.path.join(dp, fn) for dp, _d, fns in os.walk(p) for fn in fns), None)
                if src:
                    break
    if probe:
        clones = _clone_ok(src)
    else:
        try:
            clones = (sys.platform == "darwin" and not os.environ.get("BRING_OVER_NO_CLONES")
                      and os.stat(ctx.old).st_dev == os.stat(ROOT).st_dev)
        except OSError:
            clones = False
    fsize = sum(i.size for i in footage)
    # Her projects and inbox clips as a full duplicate (no clones here): she is asked before that happens.
    ctx.full_copy = 0 if clones else sum(i.size for i in footage if i.group == "footage")
    needed = (need - fsize) + (0 if clones else fsize)
    if clones and fsize:
        line = (f"Room: your footage and files ({_human(fsize)}) copy as clones on this Mac, which take almost no "
                f"extra room. You have {_human(free)} free.")
    else:
        line = f"Room: this needs about {_human(need)}, and you have {_human(free)} free."
    return free >= needed + MARGIN, line


def apply_plan(ctx, plan):
    fits, room = _room(ctx, plan, probe=True)
    if ctx.full_copy and not ctx.projects:
        raise Refusal(f"One choice before anything is copied: your projects and inbox clips are {_human(ctx.full_copy)}, "
                      f"and this disk cannot share them with the old folder the way a Mac does, so bringing them over "
                      f"makes a second full copy.\n  To bring them too:          {_py()} scripts/bring-over.py "
                      f"\"{ctx.old}\" --apply --projects\n  To leave them where they are: {_py()} scripts/bring-over.py "
                      f"\"{ctx.old}\" --apply --no-projects   (they keep working from the old folder)\n"
                      f"Nothing was copied or changed.")
    if not fits:
        raise Refusal(f"There is not enough room on this disk to bring it all over. {room} Free up some space, or run "
                      f"it with --no-projects to leave your footage in the old folder (it keeps working from there). "
                      f"Nothing was copied or changed.")
    for item in plan.items:
        if item.status != "bring" or not item.run:
            continue
        if item.label and (item.group == "footage" or item.size >= 1 << 24):
            print(f"  copying {item.label} ({_human(item.size)})...", flush=True)
        try:
            item.run()
        except Exception as exc:  # noqa: BLE001 — one item never takes the rest down with it
            item.failed = f"{type(exc).__name__}: {exc}"
            if not item.label:
                plan.hand_notes.append(f"one step did not finish ({item.failed}); run the same command again")
    _save_hands(ctx, plan)
    _write_record(ctx, plan)
    print()
    print_report(ctx, plan, applied=True, room=room)
    return 1 if any(i.failed for i in plan.items) else 0


def _save_hands(ctx, plan):
    kc = ctx.E.kc
    for h in plan.hands + plan.removed:
        data = h["data"] if h.get("data") is not None else _read_bytes(h["src"])
        if data is None:
            continue
        rel = f"{kc.SAVED_REL}/{FROM}/{h['save_as']}"
        if _read_bytes(ctx.new_path(rel)) != data:
            _write_bytes(ctx, ctx.new_path(rel), data)
        h["saved"] = rel
        if h.get("base") is not None:
            mine = data.decode("utf-8", "replace").replace("\r\n", "\n")
            diff = kc._diff(h["path"], h["base"], mine)
            if diff:
                if _read_text(ctx.new_path(rel + ".diff")) != diff:
                    _write_text(ctx, ctx.new_path(rel + ".diff"), diff)
                h["change"] = rel + ".diff"


def _write_record(ctx, plan):
    """The same record an update keeps (keep_changes.write_doc): _local/my-changes.md, newest first, where the
    update skill's "bring my changes forward" finds what needs a hand. Written only when there is something new."""
    kc, pp = ctx.E.kc, ctx.E.pp
    needs = [{"path": h["path"], "saved": h["saved"], "change": h.get("change"), "why": h["why"]}
             for h in plan.hands if h.get("saved")]
    removed = [{"path": h["path"], "saved": h["saved"], "change": h.get("change")} for h in plan.removed if h.get("saved")]
    added = sorted(plan.added)
    if not (needs or removed or plan.adopted or plan.hand_notes or added):
        return
    rec_path = ctx.new_path(f"{kc.SAVED_REL}/{FROM}/changes.json")
    stored = _read_json(rec_path)
    if isinstance(stored, dict):
        def have(key, field):
            return {(x or {}).get(field) if isinstance(x, dict) else x for x in stored.get(key) or []}
        if ({n["path"] for n in needs} <= have("needs_hand", "path") and {r["path"] for r in removed} <= have("removed", "path")
                and {p.get("saved_as") for p in plan.adopted} <= have("packs", "saved_as")
                and set(added) <= set(stored.get("added_now") or []) and set(plan.hand_notes) <= set(stored.get("notes") or [])):
            return                                        # all of it is written down already
    _shipped, live = pp._shipped_packs()
    report = {"update": FROM, "from": ctx.old_v, "to": ctx.new_v, "date": kc._now(), "kept": [],
              "needs_hand": needs, "removed": removed, "packs": plan.adopted,
              "notes": [f"All of this came from your old engine (v{ctx.old_v}) when you brought it over. Nothing in "
                        f"that folder was changed."] + plan.hand_notes,
              "packs_back": sorted(n for n in pp.load() if live and n in live)}
    kc.write_doc(report, [], added)


# ── --find ─────────────────────────────────────────────────────────────────────────────────────────
_HEAVY = {"Library", "AppData", "Applications", "node_modules", "Music", "Movies", "Pictures", "Photos",
          "OneDrive", "iCloud Drive", "Dropbox", "Google Drive", "projects", "System Volume Information"}


def find_engines(max_depth=4, budget_s=20.0, max_dirs=60000):
    home = os.path.expanduser("~")
    starts = [home] + ([os.path.dirname(ROOT)] if not _inside(ROOT, home) else [])
    found, seen, dirs = [], set(), 0
    deadline = time.time() + budget_s
    queue = collections.deque((s, 0) for s in starts)
    while queue and time.time() < deadline and dirs < max_dirs:
        d, depth = queue.popleft()
        real = os.path.realpath(d)
        if real in seen:
            continue
        seen.add(real)
        dirs += 1
        v = _engine_at(d)
        if v:
            if not os.path.samefile(d, ROOT):
                try:
                    when = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(os.path.join(d, "product.json"))))
                except OSError:
                    when = "?"
                found.append((semver(v), d, v, when))
            continue
        if depth >= max_depth:
            continue
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            p = os.path.join(d, n)
            if n.startswith(".") or n in _HEAVY or "venv" in n.lower() or os.path.splitext(n)[1] in (
                    ".app", ".photoslibrary", ".bundle", ".framework", ".musiclibrary", ".tvlibrary"):
                continue
            if os.path.isdir(p) and not os.path.islink(p):
                queue.append((p, depth + 1))
    here = semver(_engine_at(ROOT) or "0")
    older = [f for f in found if f[0][0] < here[0]]           # only an older version can be brought over
    newer = [f for f in found if f[0][0] >= here[0]]
    if not older:
        print("I did not find an older engine folder in your home folder. Where did you unzip the old one? "
              "(Downloads, Documents and the Desktop are the usual places.)")
        for _sv, d, v, _when in newer:
            print(f"  (also here, and already on this version or newer: {d}, v{v})")
        return 0
    print("Old engine folders I found (newest version first):")
    for i, (_sv, d, v, when) in enumerate(sorted(older, key=lambda f: (f[0], f[3]), reverse=True), 1):
        print(f"  {i}. {d}   v{v}, last changed {when}")
    print(f"\nThis engine is v{_engine_at(ROOT) or '?'}; bring over from one of the folders above.")
    return 0


# ── main ───────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Bring what is yours from an old engine folder into this one. "
                                             "A preview unless --apply is given.")
    ap.add_argument("old", nargs="*", help="the old engine's folder")
    ap.add_argument("--apply", action="store_true", help="bring it all over (without it, nothing is written)")
    ap.add_argument("--no-projects", action="store_true", help="leave your projects and inbox footage in the old folder")
    ap.add_argument("--projects", action="store_true",
                    help="bring your projects and inbox footage even where that makes a full copy (a PC, another drive)")
    ap.add_argument("--find", action="store_true", help="list the engine folders in your home folder")
    ap.add_argument("--history", help=argparse.SUPPRESS)          # tests: a v1 fingerprint file of their own
    a = ap.parse_args(argv)
    if a.find:
        return find_engines()
    ctx = None
    try:
        if a.projects and a.no_projects:
            raise Refusal("Pick one: --projects brings your footage, --no-projects leaves it in the old folder.")
        ctx = Ctx(a.old, apply=a.apply, no_projects=a.no_projects, history=a.history)
        ctx.projects, ctx.full_copy = a.projects, 0
        plan = build_plan(ctx)
        if not a.apply:
            _fits, room = _room(ctx, plan, probe=False)
            print_report(ctx, plan, applied=False, room=room)
            return 0
        return apply_plan(ctx, plan)
    except Refusal as r:
        print(str(r))
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Whatever already came across stays; run the same command again to finish. Your old "
              "folder was not changed.")
        return 1
    except Exception as exc:  # noqa: BLE001 — a creator never sees a traceback
        print("Something unexpected stopped this before it finished. Your old folder was not changed, and running the "
              "same command again picks up where it stopped.")
        print(f"(for Claude: {type(exc).__name__}: {exc})")
        if os.environ.get("BRING_OVER_DEBUG"):
            raise
        return 1
    finally:
        if ctx is not None:
            ctx.close()


if __name__ == "__main__":
    sys.exit(main())
