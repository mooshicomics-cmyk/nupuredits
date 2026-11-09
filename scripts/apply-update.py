#!/usr/bin/env python3
"""
apply-update.py — safely apply an update package to this engine.

This ships INSIDE the buyer's product. When the creator releases a fix, the
buyer drops the small update file into their project folder and says
"update me" in Claude Code. The update skill runs this script.

What it guarantees:
  * It installs only updates signed by the engine's publisher (scripts/update_signature.py): the online feed
    is verified before anything is downloaded, and a file found in her folder must carry a valid signature.
  * It only ever writes files the update package explicitly lists.
  * It NEVER touches personalized / identity / secret files (hard denylist),
    even if an update package tries to. Their voice, brand kit, keys, config,
    research, and work are untouchable.
  * What is theirs INSIDE files it does replace (style packs they built, their
    permission mode, the hook defaults and headline font their brand kit set) is
    saved first and put back after (product/pack_persist.py, settings_persist.py),
    and a file of theirs at a path the engine stops shipping is left where it is.
  * Every file it overwrites or deletes is backed up first, so any update is
    reversible with `--rollback`.
  * It checks every file in the package before it changes anything, and writes
    product.json (the installed version) last. An update that stops partway puts
    back what it changed, or, if even that cannot finish, leaves `--rollback`
    able to: an engine is never left half-updated and reported as done.
  * An update that was stopped from outside (the window closed, the app quit, the
    power went) is put back the moment the next update or `--rollback` starts,
    before either reads a single file of hers: saving her settings from files an
    update had half replaced is how a stopped update used to lose them.
  * `--rollback` keeps what she made AFTER the update: her packs and settings as
    they are now are replayed into the older files, and any engine file she
    changed since the update is saved under _local/my-changes/ before the older
    copy goes back. CLAUDE.md gets the earlier version's engine instructions
    back too, her profile untouched and any line she added since carried over.
  * It refuses to write anywhere outside this project folder.

Usage (normally invoked by the `update` skill, but safe to run by hand):
  python3 scripts/apply-update.py               apply an update: check online first, else a local file
  python3 scripts/apply-update.py --fetch        check the creator's update server and apply if newer
  python3 scripts/apply-update.py [PACKAGE]      apply a specific local update folder/.zip
  python3 scripts/apply-update.py --check [PKG]  dry run: show what WOULD change, write nothing
  python3 scripts/apply-update.py --rollback     undo the most recent update
  python3 scripts/apply-update.py --version      print the installed version
  python3 scripts/apply-update.py --code WORD    an early-access codeword: also check its hidden feed (remembered)
  python3 scripts/apply-update.py --code off     forget the codeword; back to the regular updates only

PACKAGE may be a folder or a .zip. If omitted, the script first checks online
(when the product has an `update_url`), then looks for a package in the project
root and in an `_updates/` drop folder.

No third-party dependencies (online check uses only the Python standard library).
Python 3.8+.
"""
import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# --- locate the project root (the folder that holds product.json) ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # scripts/ lives at the project root
PRODUCT_FILE = PROJECT_ROOT / "product.json"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
BACKUP_ROOT = PROJECT_ROOT / "_update-backups"
# In each update's backup folder, beside applied.json: the fingerprint of every file the update wrote, as it
# stood once the update (and its finishing step) was done. --rollback compares against it to tell a file she
# changed AFTER the update (saved before the older copy goes back) from one she never touched.
INCOMING = "incoming.json"
# Where --rollback saves a file of hers it would otherwise write over (see rollback()).
LATER_REL = "_local/my-changes"

# Files/folders an update may NEVER create, overwrite, or delete. These are the
# buyer's own. Matched (fnmatch) against the path relative to the project root,
# using forward slashes. Defense-in-depth: make-update.py also excludes these.
PROTECTED = [
    ".env", ".env.*", ".mcp.json", "product.json.bak",
    "config.json",                       # edit engine local server config
    "voice-dna.md", "brand-kit.md", "competitor-list.md",
    "backbone", "backbone/*",
    "research", "research/*", "research-lab", "research-lab/*",
    "transcripts", "transcripts/*",
    "projects", "projects/*", "_local", "_local/*",
    "CLAUDE.md",                          # holds their personalized creator profile
    ".claude/settings.local.json",
    "_update-backups", "_update-backups/*",
    # The buyer's chosen style pack and accent colour. It ships as a blank template, so it has only
    # ever been skipped by luck (unchanged since release). The first edit to that shipped template
    # would otherwise overwrite every buyer's saved look on their next update.
    "product/creative-vault/user-style.json",
    # Style packs the buyer BUILT ("build my own style pack" / "/studio recipe"). The pack itself is
    # written into two SHIPPED files (style-packs.json + pack_palettes.py), which an update replaces, so
    # this protected sidecar is the copy that survives — replayed back into those files below.
    "product/creative-vault/user-packs.json",
    "product/creative-vault/user-effects.json",   # text animations she NAMED (text_effects.teach)
    "product/creative-vault/font-overrides.json", # fonts she hand-mapped (capcut_font_doctor.py --map)
    # Her brands and the Brand Kit (a separate download she installed): never the engine's to write or remove.
    "favorites/designs/*", "inbox/brand", "inbox/brand/*",
    ".claude/skills/brand-kit", ".claude/skills/brand-kit/*",
]

# Files that mix SHIPPED DEFAULTS with the BUYER'S OWN ADDITIONS. Overwriting destroys what the buyer
# added; protecting means they never receive new defaults. So these are MERGED: new defaults arrive,
# and anything the buyer added (or changed) wins.
#
# presets/caption-corrections.json tells the buyer, in its own notes, to add their business and
# product names to it, and onboarding does exactly that. A tester lost hers mid-session: a routine
# update replaced the file wholesale and the names she had set up were gone.
_CC_WORDS = ("words", "auto")      # the one-word table, and the name it had before
_CC_CHECK = ("check", "flag")      # the real words listed to check, and the name that list had before
_CC_RETIRED = {"_README", "auto", "flag"}


def _merge_caption_corrections(local, incoming):
    out = dict(incoming)                                  # the new "about" and any new top-level keys
    words = {}
    for side in (incoming, local):                        # the buyer's entry wins on the same word
        for key in _CC_WORDS:
            words.update(side.get(key) or {})
    out["words"] = words
    phrases = dict(incoming.get("phrases") or {})
    phrases.update(local.get("phrases") or {})
    out["phrases"] = phrases
    check = []
    for side in (incoming, local):
        for key in _CC_CHECK:
            check += [w for w in side.get(key) or [] if w not in check]
    out["check"] = check
    for key in _CC_RETIRED:                               # their entries now sit under the current names
        out.pop(key, None)
    for k, v in local.items():                            # keep anything else the buyer added
        if k not in out and k not in _CC_RETIRED:
            out[k] = v
    return out


MERGE_JSON = {"presets/caption-corrections.json": _merge_caption_corrections}


def _product_module(name):
    """product/<name>.py, loaded by path (this script is not run from inside product/).

    Returns None if it is not there — an engine older than it, where there is nothing to do."""
    path = PROJECT_ROOT / "product" / f"{name}.py"
    if not path.exists():
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _pack_persist():
    """product/pack_persist.py: her style packs (see _product_module)."""
    return _product_module("pack_persist")


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_product():
    if not PRODUCT_FILE.exists():
        die(f"no product.json found at {PRODUCT_FILE} — is this the right folder?")
    return json.loads(PRODUCT_FILE.read_text(encoding="utf-8"))


def save_product(prod):
    # Whole or not at all: a product.json cut off mid-write (a power cut) is unreadable, and every later update
    # and undo starts by reading it.
    part = PRODUCT_FILE.with_name(PRODUCT_FILE.name + ".part")
    part.write_text(json.dumps(prod, indent=2) + "\n", encoding="utf-8")
    os.replace(part, PRODUCT_FILE)


def semver(v):
    """'1.2.3' -> (1, 2, 3); tolerant of extra/missing parts."""
    parts = []
    for chunk in str(v).split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_protected(rel_path):
    rel = rel_path.replace("\\", "/").strip("/")
    # Her favorites folder (product/favorites_folder.py): everything she drops in is hers. Only the four READMEs
    # that explain the folder are the engine's, so an update may refresh them and nothing else in there.
    if rel == "favorites" or rel.startswith("favorites/"):
        parts = rel.split("/")
        return not (parts[-1] == "README.md" and len(parts) in (2, 3))
    for pat in PROTECTED:
        if fnmatch.fnmatch(rel, pat):
            return True
    # also block anything nested under a protected top-level folder
    top = rel.split("/", 1)[0]
    if top in {p.rstrip("/*") for p in PROTECTED if "/" not in p.rstrip("/*")}:
        if top in {"backbone", "research", "research-lab", "transcripts",
                   "projects", "_local", "_update-backups"}:
            return True
    return False


def safe_target(rel_path):
    """Resolve a manifest path to an absolute path INSIDE the project. Reject escapes."""
    rel = rel_path.replace("\\", "/").strip("/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        die(f"unsafe path in update package: {rel_path!r}")
    target = (PROJECT_ROOT / rel).resolve()
    root = PROJECT_ROOT.resolve()
    if root not in target.parents and target != root:
        die(f"update path escapes the project folder: {rel_path!r}")
    return target


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def find_package():
    """Auto-discover an update folder or zip in the project root or _updates/."""
    candidates = []
    search_dirs = [PROJECT_ROOT, PROJECT_ROOT / "_updates"]
    for d in search_dirs:
        if not d.exists():
            continue
        for entry in d.iterdir():
            if entry.is_dir() and (entry / "update.json").exists():
                candidates.append(entry)
            elif entry.is_file() and entry.suffix == ".zip" and "update-v" in entry.name:
                candidates.append(entry)
    if not candidates:
        return None
    # Prefer the highest version encoded in the name; fall back to newest mtime.
    def keyer(p):
        name = p.name
        ver = (0, 0, 0)
        if "update-v" in name:
            ver = semver(name.split("update-v", 1)[1].split(".zip")[0])
        return (ver, p.stat().st_mtime)
    candidates.sort(key=keyer)
    return candidates[-1]


# ── authenticity: every update must be signed by the engine's publisher ─────────────────────────────────
# The online feed (latest.json), the update.json inside every package and the update .zip itself carry an
# Ed25519 signature, checked against the public key pinned in scripts/update_signature.py. The sha256 of the
# download alone only proved it arrived intact; it sat in the same feed, so whoever could change the feed
# could change both. Now nothing is downloaded until the feed's signature checks out, and a package found in
# her folder is installed only when it proves it came from the publisher.
def _signature_module():
    """scripts/update_signature.py, loaded by path; None when it is not there."""
    path = SCRIPT_DIR / "update_signature.py"
    if not path.exists():
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("update_signature", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:   # noqa: BLE001
        return None


def _zip_signature(pkg):
    """('ok'|'bad'|'none', reason) for the detached <zip>.sig beside a zip."""
    if not (pkg.is_file() and pkg.suffix == ".zip"):
        return "none", ""
    sig = pkg.with_name(pkg.name + ".sig")
    if not sig.is_file():
        return "none", ""
    us = _signature_module()
    if us is None:
        return "bad", "the signature checker (scripts/update_signature.py) is missing from this engine"
    try:
        text = sig.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return "bad", f"its signature file could not be read ({e})"
    why = us.check_zip(pkg, text)
    return ("bad", why) if why else ("ok", "")


def _package_signature(root, manifest):
    """('ok'|'bad'|'none', reason) for update.json.sig inside an unpacked package. A valid one covers every
    file too: update.json lists each file's sha256, and apply() checks every one before writing anything."""
    sig = root / "update.json.sig"
    if not sig.is_file():
        return "none", ""
    us = _signature_module()
    if us is None:
        return "bad", "the signature checker (scripts/update_signature.py) is missing from this engine"
    try:
        why = us.check_manifest((root / "update.json").read_bytes(), sig.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        why = f"its signature could not be read ({e})"
    if why:
        return "bad", why
    for entry in manifest.get("files", []):
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if not (isinstance(digest, str) and len(digest) == 64):
            return "bad", "it lists a file without a checksum"
        # Checked here too, not only just before writing, so a dry run never presents a package whose
        # files are not the ones its signature names.
        rel = str(entry.get("path", "")).replace("\\", "/").strip("/")
        src = root / "files" / rel
        if rel and ".." not in rel.split("/") and src.is_file() and sha256(src) != digest.lower():
            return "bad", f"{rel} in it is not the file its signature names"
    return "ok", ""


def _refuse_unsigned(pkg, why):
    die(f"the update file {pkg.name} is not signed by this engine's publisher ({why}), so I did not install it. "
        f"Nothing was changed. Run the update again with no file named: it fetches the official, signed update "
        f"on its own. If you were sent this file directly, ask for a fresh copy.")


def load_package(package_path):
    """Return (manifest_dict, files_root_path, tempdir_or_None)."""
    p = Path(package_path).expanduser().resolve()
    if not p.exists():
        die(f"update package not found: {package_path}")
    tmp = None
    if p.is_file() and p.suffix == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="engine-update-"))
        with zipfile.ZipFile(p) as zf:
            # extractall() drops Unix file modes, which stripped the executable bit from every shipped
            # shell script on the way in ("./check-setup.sh: permission denied" after an update, measured).
            # The package stores the modes; restore them file by file.
            for info in zf.infolist():
                zf.extract(info, tmp)
                mode = (info.external_attr >> 16) & 0o7777
                if mode and not info.is_dir():
                    try:
                        os.chmod(tmp / info.filename, mode)
                    except OSError:
                        pass
        # the zip usually contains a single top folder
        inner = [c for c in tmp.iterdir() if c.is_dir()]
        root = inner[0] if len(inner) == 1 and (inner[0] / "update.json").exists() else tmp
    else:
        root = p
    manifest_file = root / "update.json"
    if not manifest_file.exists():
        die("this does not look like an update package (no update.json inside).")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    return manifest, root, tmp


def backup_dir_for(from_v, to_v):
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = BACKUP_ROOT / f"v{from_v}-to-v{to_v}-{stamp}"
    return d


def _write_record(bdir, log):
    """applied.json, the record --rollback reads, written whole or not at all (a half-written one would stop
    the undo it exists for): a copy beside it first, then a rename over it."""
    part = bdir / "applied.json.part"
    part.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    os.replace(part, bdir / "applied.json")


def _unchanged(saved, target):
    """True while `target` is still exactly the copy saved before the update (bytes and permission bits)."""
    try:
        a, b = os.stat(saved), os.stat(target)
        return (target.is_file() and a.st_size == b.st_size and (a.st_mode & 0o7777) == (b.st_mode & 0o7777)
                and sha256(saved) == sha256(target))
    except OSError:
        return False


def _write_incoming(bdir, to_v, wrote):
    """INCOMING for this update: every file it wrote, as it stands right now (the finishing step refreshes it
    once its own merges are done). Written whole or not at all, like applied.json."""
    files = {}
    for rel in wrote:
        t = PROJECT_ROOT / rel
        if t.is_file():
            files[rel] = sha256(t)
    part = bdir / (INCOMING + ".part")
    part.write_text(json.dumps({"to": to_v, "files": files}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(part, bdir / INCOMING)


def _incoming(bdir):
    """{path: sha256} from an update's INCOMING, or {} for an update from before it was kept."""
    try:
        data = json.loads((bdir / INCOMING).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    files = data.get("files") if isinstance(data, dict) else None
    return files if isinstance(files, dict) else {}


def _record_of(bdir):
    try:
        log = json.loads((bdir / "applied.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return log if isinstance(log, dict) else None


def _unfinished(cur_v):
    """Backup folders of updates that were stopped from outside after they began (the window closed, the app
    quit, the power went): each still names the version she is on as where it started, because product.json
    takes the new version last. Newest first. Their files are part old, part new, so nothing may read her
    settings or packs from the engine until they are put back."""
    if not BACKUP_ROOT.exists():
        return []
    found = []
    for d in BACKUP_ROOT.iterdir():
        if not d.is_dir() or d.name.endswith(".rolledback"):
            continue
        log = _record_of(d)
        if log and str(log.get("from", "")) == str(cur_v) and str(log.get("to", "")) != str(cur_v):
            found.append(d)
    return sorted(found, key=_backup_stamp, reverse=True)


class _Stopped(KeyboardInterrupt):
    """The window closed or the app quit while the update was working: handled exactly like Ctrl-C, so what it
    had changed goes back (a stop it never gets to see, like a power cut, is put back by the next run)."""


def _on_stop(signum, frame):   # noqa: ARG001
    raise _Stopped()


# The signals a process receives when its terminal or window closes, or the app running it quits. SIGKILL cannot be
# caught at all; _unfinished() covers that one on the next run.
_STOP_SIGNALS = [s for s in (getattr(signal, n, None) for n in ("SIGTERM", "SIGHUP", "SIGBREAK")) if s is not None]


def _on_stop_signals(handler):
    """Point the stop signals at `handler`; returns what they pointed at before (for _restore_signals)."""
    prev = {}
    for sig in _STOP_SIGNALS:
        try:
            prev[sig] = signal.signal(sig, handler)
        except (ValueError, OSError, RuntimeError):   # not the main thread, or not settable on this system
            pass
    return prev


def _restore_signals(prev):
    for sig, handler in prev.items():
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, RuntimeError, TypeError):
            pass


def _put_back(bdir, cur_v):
    """Undo an update that stopped partway, from the copies it saved before changing anything.

    Returns None once everything is back (the backup folder is then marked .rolledback, exactly as --rollback
    leaves it), else what stopped it: the copies and the record then stay in place for --rollback. A file the
    update never got to is left alone rather than rewritten, so the file that stopped it (read-only, or open
    in another program) cannot stop the undo too."""
    try:
        log = json.loads((bdir / "applied.json").read_text(encoding="utf-8"))
        ow, dl = bdir / "overwritten", bdir / "deleted"
        saved = {p.relative_to(ow).as_posix(): p for p in ow.rglob("*") if p.is_file()} if ow.exists() else {}
        for rel in log.get("wrote", []):                 # a file it added: gone again (first: frees room on a full disk)
            if rel not in saved:
                t = safe_target(rel)
                if t.exists():
                    t.unlink()
        restore = list(saved.items())
        if dl.exists():
            restore += [(p.relative_to(dl).as_posix(), p) for p in dl.rglob("*") if p.is_file()]
        for rel, copy in restore:                        # a file it replaced or removed: the saved copy goes back
            t = safe_target(rel)
            if not _unchanged(copy, t):
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(copy, t)
        prod = load_product()
        if prod.get("version") != cur_v:
            prod["version"] = cur_v
            save_product(prod)
    except BaseException as e:   # noqa: BLE001  (reported to her, never raised: the update already failed once)
        return e
    try:
        shutil.move(str(bdir), str(bdir) + ".rolledback")   # no longer an update --rollback could undo
    except OSError:
        try:
            (bdir / "applied.json").unlink()
        except OSError:
            pass
    return None


def _stopped_partway(bdir, cur_v, new_v, doing, exc):
    """An update failed after it began changing files. Put everything back, say plainly what happened and what
    to do, and exit non-zero. Never reports success."""
    what = "it was stopped" if isinstance(exc, KeyboardInterrupt) else f"{doing} ({exc or type(exc).__name__})"
    # Putting back must not itself be cut short by a second Ctrl-C or the window finishing closing.
    _on_stop_signals(signal.SIG_IGN)
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError, RuntimeError):
        pass
    problem = _put_back(bdir, cur_v)
    if problem is not None:
        problem = "it was stopped" if isinstance(problem, KeyboardInterrupt) else (str(problem) or type(problem).__name__)
    try:
        sys.stdout.flush()
        if problem is None:
            print(f"ERROR: the update to v{new_v} did not finish: {what}.\n"
                  f"Everything it had changed is back the way it was: you are still on v{cur_v}, and nothing of "
                  f"yours was touched.\nOnce that is sorted (a full disk, or a file another program has open, are "
                  f"the usual causes), run the update again.", file=sys.stderr)
        else:
            print(f"ERROR: the update to v{new_v} did not finish: {what}.\n"
                  f"Putting the earlier files back did not finish either ({problem}), so the engine is part-way "
                  f"between v{cur_v} and v{new_v}. Every file it changed is saved in {bdir.relative_to(PROJECT_ROOT)}/."
                  f"\nTo put everything back, run: python3 scripts/apply-update.py --rollback (or simply run the "
                  f"update again: it puts this one back first)", file=sys.stderr)
    except (OSError, ValueError):
        pass                       # the window it would print to is gone; what matters, the put-back, is done
    sys.exit(1)


def apply(package_path, dry_run=False, verified=False):
    """`verified`: the caller already proved the package genuine (fetch(): a signed feed, then the download's
    sha256 against it). Otherwise it must prove itself here: a package found in her folder, or any .zip, is
    installed only with a valid publisher signature. An unpacked folder named on the command line (a
    developer's test package) is the one exception, and the output says it was not checked."""
    prod = load_product()
    cur_v = prod.get("version", "0.0.0")
    engine = prod.get("engine", "")

    found = not package_path
    pkg = package_path or find_package()
    if not pkg:
        die("no update file found. Put the update the creator sent you into this "
            "folder (or an `_updates/` folder inside it) and try again.")

    pkg_path = Path(pkg).expanduser().resolve()
    zip_sig = ("none", "") if verified else _zip_signature(pkg_path)
    if zip_sig[0] == "bad":
        _refuse_unsigned(pkg_path, zip_sig[1])
    manifest, files_root, tmp = load_package(pkg)
    try:
        if not verified and zip_sig[0] != "ok":
            status, why = _package_signature(files_root, manifest)
            if status == "bad":
                _refuse_unsigned(pkg_path, why)
            if status == "none":
                if found or pkg_path.suffix == ".zip" or not pkg_path.is_dir():
                    _refuse_unsigned(pkg_path, "it carries no signature")
                print("  (an unpacked update folder named by hand: its publisher signature was not checked)")
        new_v = manifest.get("version", "0.0.0")
        min_v = manifest.get("min_version", "0.0.0")
        pkg_engine = manifest.get("engine", "")

        if pkg_engine and engine and pkg_engine != engine:
            die(f"this update is for '{pkg_engine}', but this folder is '{engine}'. "
                "You've got the wrong update file for this product.")

        if semver(cur_v) >= semver(new_v):
            print(f"You're already up to date (installed v{cur_v}, update is v{new_v}). "
                  "Nothing to do.")
            return
        if semver(cur_v) < semver(min_v):
            die(f"this update needs at least v{min_v}, but you're on v{cur_v}. "
                "Apply the earlier update(s) first, in order.")

        # An earlier update that was stopped partway (the window closed, the app quit, the power went) left the
        # engine part old, part new. Put it back BEFORE anything below reads the engine: her settings and packs
        # are saved from the live files next, and saving them from half-replaced files is how a stopped update
        # used to lose her permission mode, her hooks and her edited packs on the next run.
        stopped = _unfinished(cur_v)
        if stopped:
            was = ", ".join(f"v{(_record_of(d) or {}).get('to', '?')}" for d in stopped)
            if dry_run:
                print(f"  An earlier update ({was}) was stopped before it finished. Installing puts it back first, "
                      f"then applies v{new_v}.")
            else:
                for d in stopped:
                    problem = _put_back(d, cur_v)
                    if problem is not None:
                        die(f"an earlier update ({was}) was stopped before it finished, and putting its files back did "
                            f"not finish either ({problem or type(problem).__name__}). Nothing new was installed and "
                            f"nothing of yours was touched. Every file it changed is saved in "
                            f"{d.relative_to(PROJECT_ROOT)}/. Run: python3 scripts/apply-update.py --rollback")
                print(f"  An earlier update ({was}) was stopped before it finished. Everything it had changed is back "
                      f"the way it was, and nothing of yours was lost; installing v{new_v} now.")

        changes = manifest.get("files", [])
        deletes = manifest.get("deletes", [])
        # Every version the engine ever shipped of each file it now removes (make-update.py). A file at one
        # of those paths that matches none of them is not the engine's copy: it is hers, and it stays.
        delete_hashes = manifest.get("delete_hashes") or {}

        planned_writes, planned_deletes, skipped, kept_hers = [], [], [], []

        for entry in changes:
            rel = entry["path"] if isinstance(entry, dict) else entry
            if is_protected(rel):
                skipped.append(rel)
                continue
            src = files_root / "files" / rel
            if not src.exists():
                die(f"update package is missing a file it lists: {rel}")
            planned_writes.append((rel, src, entry.get("sha256") if isinstance(entry, dict) else None))

        for rel in deletes:
            if is_protected(rel):
                skipped.append(rel)
                continue
            # Only count a delete if the file is really here. The package lists every file removed since
            # the first release, most of which a given buyer never had, so the old count announced "33
            # files to remove" while removing none, and the saved record (correctly) said zero.
            target = safe_target(rel)
            if target.exists():
                if rel in delete_hashes and target.is_file() and sha256(target) not in delete_hashes[rel]:
                    kept_hers.append(rel)
                    continue
                planned_deletes.append(rel)

        # --- report ---
        print(f"Update: v{cur_v}  ->  v{new_v}")
        if manifest.get("summary"):
            print(f"  {manifest['summary']}")
        print(f"  files to add/replace: {len(planned_writes)}")
        print(f"  files to remove:      {len(planned_deletes)}")
        if skipped:
            print(f"  protected (left untouched): {len(skipped)} -> {', '.join(skipped)}")
        if kept_hers:
            print(f"  kept as yours (the engine no longer ships these, and yours are your own): "
                  f"{', '.join(kept_hers)}")
        if dry_run:
            print("\n(dry run — nothing was written.)")
            for rel, _src, _sha in planned_writes:
                print(f"    would write   {rel}")
            for rel in planned_deletes:
                print(f"    would delete  {rel}")
            return

        # --- check the WHOLE package before a single byte moves ---
        # Each file used to be checked only as it was written. A bad one stopped the update halfway, with every
        # file before it already new: product.json among them (it sorts before product/), so the engine read as
        # updated, "update me" said there was nothing to do, and --rollback undid the update before it instead.
        targets = {}
        for rel, src, expected_sha in planned_writes:
            targets[rel] = safe_target(rel)
            try:
                intact = not expected_sha or sha256(src) == expected_sha
            except OSError as e:
                die(f"could not read {rel} in the update package ({e}). Nothing was changed: you are still on "
                    f"v{cur_v}.")
            if not intact:
                die(f"update file failed its integrity check: {rel}. Package may be corrupt. Nothing was changed: "
                    f"you are still on v{cur_v}. Download the update again (or ask for a fresh copy) and re-run it.")

        # --- apply: back up everything it touches first, then write ---
        bdir = backup_dir_for(cur_v, new_v)
        made_bdir = not bdir.exists()
        try:
            bdir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            die(f"the update could not make its backup folder ({e}), so it changed nothing: you are still on "
                f"v{cur_v}. If your disk is full, free up some space, then run the update again.")

        # A pack the buyer built lives in two shipped files this update is about to replace. Save every one
        # as it stands right now (a quick fonts-and-accent pack included, and any pack she has changed since
        # it was saved), BEFORE a single byte moves.
        persist = _pack_persist()
        if persist:
            try:
                recorded, problems = persist.harvest()
                if recorded:
                    print(f"  saved your style pack(s) first: {', '.join(recorded)}")
                for item in problems:
                    n, why = item if isinstance(item, tuple) else (item, "could not be read in full")
                    print(f"  ! style pack '{n}': {why}. Your previous files are backed up in {bdir.name}/.")
            except Exception as exc:
                print(f"  ! could not check your style packs before updating ({exc}). Your previous files "
                      f"are backed up in {bdir.name}/.")
        # Her own settings inside shipped files (permission mode, hook defaults, headline font): same idea.
        keep = _product_module("settings_persist")
        if keep:
            try:
                kept, problems = keep.harvest()
                if kept:
                    print(f"  saved your own settings first: {', '.join(kept)}")
                for what, why in problems:
                    print(f"  ! {what}: {why}")
            except Exception as exc:
                print(f"  ! could not save your own settings before updating ({exc}). Your previous files "
                      f"are backed up in {bdir.name}/.")
        manifest_log = {"from": cur_v, "to": new_v, "wrote": [], "deleted": []}
        # From the first backup copy to the new version number, the window closing or the app quitting stops the
        # update the way Ctrl-C does, so what it changed goes back instead of being left half done.
        prev_signals = _on_stop_signals(_on_stop)

        # Copy every file this update will replace or remove, ALL of them, before the first one changes; then
        # write the record --rollback reads (applied.json), naming everything it is about to write or remove.
        # From then on an update that stops partway, for any reason, can be undone: every copy is whole and the
        # record covers every file it may have touched. Nothing in the engine has changed yet at this point, so
        # a failure here (a full disk, most likely) stops cleanly.
        try:
            (bdir / "_from_version.txt").write_text(cur_v + "\n", encoding="utf-8")
            for rel, _src, _sha in planned_writes:
                if targets[rel].exists():
                    bpath = bdir / "overwritten" / rel
                    bpath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(targets[rel], bpath)
            for rel in planned_deletes:
                target = safe_target(rel)
                if target.exists():
                    bpath = bdir / "deleted" / rel
                    bpath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, bpath)
            _write_record(bdir, dict(manifest_log, wrote=[w[0] for w in planned_writes],
                                     deleted=list(planned_deletes)))
        except BaseException as e:   # noqa: BLE001  (Ctrl-C included: nothing in the engine has changed yet)
            if made_bdir:
                shutil.rmtree(bdir, ignore_errors=True)
            if isinstance(e, KeyboardInterrupt):
                die(f"the update was stopped before it changed anything: you are still on v{cur_v}.")
            die(f"the update could not save its backup ({e}), so it stopped before changing anything: you are "
                f"still on v{cur_v}. If your disk is full, free up some space, then run the update again.")

        def write_one(rel, src):
            target = targets[rel]
            was_exec = target.exists() and os.access(target, os.X_OK)
            target.parent.mkdir(parents=True, exist_ok=True)
            merger = MERGE_JSON.get(rel)
            if merger and target.exists():
                try:
                    merged = merger(json.loads(target.read_text(encoding="utf-8")),
                                    json.loads(src.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    # Their copy will not parse. Leave it exactly as it is rather than overwrite what they
                    # wrote; the backup above already holds it either way.
                    print(f"  kept your {rel} as-is (could not read it to merge in new defaults)")
                    return
                target.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                shutil.copy2(src, target)
            # A script must stay runnable: keep the bit if the old copy had it, the package carries it,
            # or the file is a shell script by name (belt and braces on a machine where the zip lost it).
            if os.name != "nt" and (was_exec or os.access(src, os.X_OK) or rel.endswith((".sh", ".command"))):
                try:
                    os.chmod(target, os.stat(target).st_mode | 0o111)
                except OSError:
                    pass
            manifest_log["wrote"].append(rel)

        # Everything from the first write to the new version number is all or nothing: if any step fails, what
        # was changed goes back (_stopped_partway), and the update never reports success.
        doing = ""
        try:
            # product.json goes LAST, once every other file has landed and every removal is done: the version
            # in it is what says this update is installed, so it must never read new while the rest is old.
            for rel, src, _sha in planned_writes:
                if rel != "product.json":
                    doing = f"could not write {rel}"
                    write_one(rel, src)
            for rel in planned_deletes:
                target = safe_target(rel)
                if target.exists():
                    doing = f"could not remove {rel}"
                    target.unlink()
                    manifest_log["deleted"].append(rel)
            for rel, src, _sha in planned_writes:
                if rel == "product.json":
                    doing = f"could not write {rel}"
                    write_one(rel, src)
            doing = "stopped while putting your style packs and settings back"

            # The update has replaced style-packs.json / pack_palettes.py with the shipped versions. Put the
            # buyer's own packs back, by replaying the same write their build used.
            if persist:
                try:
                    restored, problems = persist.restore()
                    if restored:
                        print(f"  put your style pack(s) back: {', '.join(restored)}")
                    for n, why in problems:
                        print(f"  ! style pack '{n}': {why}")
                except Exception as exc:
                    print(f"  ! could not restore your style packs ({exc}). They are saved in "
                          f"product/creative-vault/user-packs.json — nothing is lost.")
            if keep:
                try:
                    restored, problems = keep.restore()
                    if restored:
                        print(f"  put back {', '.join(restored)}")
                    for what, why in problems:
                        print(f"  ! {what}: {why}")
                except Exception as exc:
                    print(f"  ! could not put your own settings back ({exc}). They are saved in "
                          f"_local/kept-settings.json and in {bdir.name}/ — nothing is lost.")

            doing = "could not save the update's record (applied.json)"
            order = {w[0]: i for i, w in enumerate(planned_writes)}
            manifest_log["wrote"].sort(key=order.get)          # in the package's own order, as it always was
            _write_record(bdir, manifest_log)

            # --- bump version + changelog ---
            # Re-read product.json first: the package may have just installed a newer one carrying new engine
            # settings (the HyperFrames pin, for one). Writing back the copy read BEFORE the install silently
            # erased them on every buyer's machine (measured on a 1.0.64 -> 1.0.66 update).
            doing = "could not write the new version into product.json"
            try:
                prod = load_product()
            except (Exception, SystemExit):
                pass
            prod["version"] = new_v
            save_product(prod)
            doing = "could not update CHANGELOG.md"
            _write_changelog(cur_v, new_v, manifest)
        except BaseException as e:   # noqa: BLE001  (whatever stopped it, never leave the engine half-updated)
            _stopped_partway(bdir, cur_v, new_v, doing, e)
        finally:
            _restore_signals(prev_signals)

        # What each file it wrote looks like now, so --rollback can tell a file she changes later from one she never
        # touched. Best-effort: without it --rollback simply puts the older copies back, as it always did.
        try:
            _write_incoming(bdir, new_v, manifest_log["wrote"])
        except OSError:
            pass

        # CLAUDE.md is protected (it holds the creator's profile), which used to mean the ENGINE's own
        # instructions in it never reached an existing install. The shipped template now rides along at
        # product/templates/CLAUDE.engine.md and this merge keeps her block, refreshes the rest, and backs
        # the old file up first. Best-effort: a merge problem never fails an update that already applied.
        # post-update.py also repairs script permissions and tidies the changelog; it is the same step the
        # update skill runs by hand for installs whose older updater does not know it yet.
        _post = SCRIPT_DIR / "post-update.py"
        if _post.exists():
            sys.stdout.flush()   # everything above prints BEFORE the finishing step's own lines, in order
            try:
                subprocess.run([sys.executable, str(_post)], check=False)
            except Exception as e:   # noqa: BLE001
                print(f"  (could not run the post-update step: {e}; run python3 scripts/post-update.py)")

        print(f"\nDone. You're now on v{new_v}.")
        print(f"A backup of everything changed is saved at: {bdir.relative_to(PROJECT_ROOT)}")
        print("Nothing personal was touched. To undo: python3 scripts/apply-update.py --rollback")
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _write_changelog(from_v, to_v, manifest):
    today = _dt.date.today().isoformat()
    lines = [f"## v{to_v} — {today}", ""]
    if manifest.get("summary"):
        lines.append(manifest["summary"])
        lines.append("")
    for c in manifest.get("changes", []):
        lines.append(f"- {c}")
    lines.append("")
    entry = "\n".join(lines)
    existing = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Changelog\n\n"
    # The package ships CHANGELOG.md itself, which already carries this version's full entry; adding a
    # second, shorter one on top left buyers with two headings for the same version. Only write when absent.
    if f"## v{to_v}" in existing:
        return
    # insert new entry right after the top-level heading
    if existing.startswith("# "):
        head, _, rest = existing.partition("\n")
        CHANGELOG.write_text(f"{head}\n\n{entry}\n{rest.lstrip()}", encoding="utf-8")
    else:
        CHANGELOG.write_text(f"# Changelog\n\n{entry}\n{existing}", encoding="utf-8")


def _backup_stamp(d):
    """(the YYYYMMDD-HHMMSS in a backup folder's name, its mtime): newest update last when sorted."""
    import re
    m = re.search(r"(\d{8}-\d{6})", d.name)
    return (m.group(1) if m else "", d.stat().st_mtime)


def _undo_claude_md(bdir, later):
    """Put back the CLAUDE.md she had before the update that `bdir` recorded (the updater never writes CLAUDE.md;
    its finishing step refreshed the engine instructions in it). Any line she changed since that refresh is carried
    onto the older file by the same three-way merge updates use; where it cannot be, her current file is saved in
    `later` first. Returns (plain line for her or None, saved path or None). Never raises."""
    target = PROJECT_ROOT / "CLAUDE.md"
    try:
        before_p, after_p = bdir / "claude-md-before.md", bdir / "claude-md-after.md"
        after = None
        if before_p.is_file():
            before = before_p.read_text(encoding="utf-8")
            after = after_p.read_text(encoding="utf-8") if after_p.is_file() else None
        else:
            # An update from before these copies were kept: the refresh's own backup, made after this update began.
            import re
            m = re.search(r"(\d{8}-\d{6})", bdir.name)
            cands = sorted(p for p in (BACKUP_ROOT / "claude-md").glob("CLAUDE.md.*.bak")
                           if m and re.search(r"(\d{8}-\d{6})", p.name) and
                           re.search(r"(\d{8}-\d{6})", p.name).group(1) >= m.group(1)) \
                if (BACKUP_ROOT / "claude-md").is_dir() else []
            if not cands:
                return None, None
            before = cands[0].read_text(encoding="utf-8")
        cur = target.read_text(encoding="utf-8") if target.is_file() else None
        if cur is None or cur == before:
            return None, None
        saved = None
        text = before
        if after is not None and cur != after:
            kc = _product_module("keep_changes")
            merged = None
            if kc:
                merged, _conflicts = kc.merge_file("CLAUDE.md", after, cur, before)
            if merged is not None:
                text = merged
            else:
                saved = later / "CLAUDE.md"
        elif after is None:
            saved = later / "CLAUDE.md"          # nothing to tell her later lines from the refresh by: keep all of it
        if saved is not None:
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(cur, encoding="utf-8")
        part = target.with_name("CLAUDE.md.part")
        part.write_text(text, encoding="utf-8")
        os.replace(part, target)
        line = "  the engine instructions in CLAUDE.md are the earlier version's again, your profile in them untouched"
        if text != before:
            line += "; the lines you added since the update are kept"
        if saved is not None:
            line += (f"; your CLAUDE.md as it was a moment ago is saved at "
                     f"{saved.relative_to(PROJECT_ROOT).as_posix()}")
        return line, saved
    except Exception as exc:   # noqa: BLE001  (the undo of the files already happened; this part never stops it)
        return (f"  ! CLAUDE.md was left as it is (its earlier version could not be put back: {exc}); the earlier "
                f"copy is in {bdir.relative_to(PROJECT_ROOT).as_posix()}/"), None


def rollback():
    if not BACKUP_ROOT.exists():
        die("no updates have been applied yet — nothing to roll back.")
    # Only a folder an UPDATE made can be undone: it holds applied.json. The CLAUDE.md refresh keeps its own
    # backups in _update-backups/claude-md/, written after the update's folder, so "newest folder" used to
    # land on it and the undo died with a traceback right after any update that refreshed CLAUDE.md.
    backups = sorted([d for d in BACKUP_ROOT.iterdir() if d.is_dir() and (d / "applied.json").exists()
                      and not d.name.endswith(".rolledback")], key=_backup_stamp)
    if not backups:
        die("no updates have been applied yet — nothing to roll back.")
    latest = backups[-1]
    log = json.loads((latest / "applied.json").read_text(encoding="utf-8"))
    from_v, to_v = log["from"], log["to"]

    cur_v = str(load_product().get("version", ""))
    if cur_v == str(from_v) and str(to_v) != cur_v:
        # It was stopped before it finished: its files are part old, part new, and nothing of hers is newer than
        # its backup. Put it back exactly (never read her settings from the half-replaced files first).
        problem = _put_back(latest, cur_v)
        if problem is not None:
            die(f"the update to v{to_v} had been stopped before it finished, and putting it back did not finish "
                f"either ({problem or type(problem).__name__}). Its saved files are in "
                f"{latest.relative_to(PROJECT_ROOT)}/; run this again once that is sorted.")
        print(f"Rolled back v{to_v} -> v{from_v}. You're back to where you were. (That update had been stopped "
              f"before it finished; everything it had changed is back.)")
        return

    incoming = _incoming(latest)
    later = PROJECT_ROOT / LATER_REL / f"after-v{to_v}-rolled-back-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    saved_later = []

    def changed_since(rel, target):
        """She changed this file AFTER the update (it is not what the update left there)."""
        return target.is_file() and incoming.get(rel) is not None and sha256(target) != incoming[rel]

    def keep_later(rel, target):
        """Save her copy before the older one (or nothing) takes its place."""
        dst = later / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, dst)
        saved_later.append(rel)

    # Her style packs and settings as they are NOW, before a single file goes back: she may have built a pack or
    # changed a setting since the update, and the older files know nothing of it. They go back in below.
    persist, keep = _pack_persist(), _product_module("settings_persist")
    for mod in (persist, keep):
        if mod:
            try:
                mod.harvest()
            except Exception:   # noqa: BLE001  (the undo itself must still run; the saved copies stay as they were)
                pass

    # restore overwritten files
    ow = latest / "overwritten"
    if ow.exists():
        for src in ow.rglob("*"):
            if src.is_file():
                rel = src.relative_to(ow).as_posix()
                t = safe_target(rel)
                if changed_since(rel, t) and sha256(t) != sha256(src):
                    keep_later(rel, t)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, t)
    # restore deleted files
    dl = latest / "deleted"
    if dl.exists():
        for src in dl.rglob("*"):
            if src.is_file():
                rel = src.relative_to(dl).as_posix()
                t = safe_target(rel)
                if t.is_file() and sha256(t) != sha256(src):
                    keep_later(rel, t)                   # a file of hers now sits where the update removed one
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, t)
    # files that were newly ADDED by the update (not in overwritten backup) should be removed
    added_backup = {p.relative_to(ow).as_posix() for p in ow.rglob("*") if p.is_file()} if ow.exists() else set()
    for rel in log.get("wrote", []):
        if rel not in added_backup:
            t = safe_target(rel)
            if t.exists():
                if changed_since(rel, t):
                    keep_later(rel, t)
                t.unlink()

    claude_line, _claude_saved = _undo_claude_md(latest, later)
    prod = load_product()
    prod["version"] = from_v
    save_product(prod)
    shutil.move(str(latest), str(latest) + ".rolledback")
    print(f"Rolled back v{to_v} -> v{from_v}. You're back to where you were.")
    if claude_line:
        print(claude_line)

    # Her packs and settings back into the older files, as she has them now.
    if persist:
        try:
            restored, problems = persist.restore()
            fixed, more = persist.reassert() if hasattr(persist, "reassert") else ([], [])
            back = restored + [n for n in fixed if n not in restored]
            if back:
                print(f"  kept your style pack(s) as you have them now: {', '.join(back)}")
            for n, why in problems + more:
                print(f"  ! style pack '{n}': {why}")
        except Exception as exc:   # noqa: BLE001
            print(f"  ! could not check your style packs after the undo ({exc}). They are saved in "
                  f"product/creative-vault/user-packs.json; say \"restore my style pack\".")
    if keep:
        try:
            restored, problems = keep.restore()
            if restored:
                print(f"  kept {', '.join(restored)} as you have them now")
            for what, why in problems:
                print(f"  ! {what}: {why}")
        except Exception as exc:   # noqa: BLE001
            print(f"  ! could not put your own settings back after the undo ({exc}). They are saved in "
                  f"_local/kept-settings.json.")
    if saved_later:
        print(f"  You changed {len(saved_later)} engine file(s) after that update; each is saved in "
              f"{later.relative_to(PROJECT_ROOT).as_posix()}/ before the older copy went back: "
              f"{', '.join(saved_later)}. Say \"bring my changes forward\" to redo a change on this version.")


def _update_url():
    """The creator's update feed base URL, from product.json (empty if not set)."""
    prod = load_product()
    return str(prod.get("update_url") or "").strip().rstrip("/")


FEED_RETRY_WAIT = 5   # seconds before asking the feed a second time; a deploy swaps the feed in about that long

# Early access by codeword. The creator can put a coming version on a hidden feed beside the regular one, at
# <update_url>/early/<32 hex>/, where the hex comes from the codeword itself: the engine never carries the word,
# and only someone who was told it can reach that feed. The feed is signed and checked exactly like the regular
# one. Once a codeword works it is remembered (_local/, which no update touches), and every later update looks
# at both feeds and installs whichever version is newer, so a tester moves back onto the regular updates the
# moment the release for everyone passes the test version. make-update.py --codeword publishes to it.
CODE_FILE_REL = "_local/update-code.json"
EARLY_SALT = "reels-editing-engine/early-access/"   # keep in step with make-update.py


def code_channel(word):
    """The feed folder a codeword opens, 'early/<32 hex>'. Case and spaces never matter ('Sun Flower' = 'sunflower')."""
    w = "".join(str(word).lower().split())
    return "early/" + hashlib.sha256((EARLY_SALT + w).encode("utf-8")).hexdigest()[:32]


# What a buyer types around a codeword: "/update v2.2.26 christmas", "christmas update", "update to the christmas
# version". The whole phrase is tried first (a codeword can have spaces in it); when that opens nothing, the phrase
# again without its version numbers and these words. A version number never picks a version: the newest wins.
_CODE_FILLER = {"update", "updates", "updated", "updating", "me", "my", "to", "the", "a", "an", "version", "versions",
                "release", "early", "access", "codeword", "code", "word", "please", "install", "get", "for", "on",
                "with", "engine", "new", "newest", "latest", "build"}
_VERSION_TOKEN = re.compile(r"^v?\d+(?:\.\d+)+$", re.I)


def code_tries(word):
    """The codeword as typed, then (only if different) the same phrase without version numbers and filler words."""
    toks = str(word).lower().replace("/update", " ").split()
    bare = [t for t in (x.strip(".,!?:;\"'") for x in toks) if t and not _VERSION_TOKEN.match(t) and t not in _CODE_FILLER]
    out = ["".join(str(word).lower().split())]
    if bare and "".join(bare) != out[0]:
        out.append("".join(bare))
    return out


def _saved_channel():
    try:
        ch = str(json.loads((PROJECT_ROOT / CODE_FILE_REL).read_text(encoding="utf-8")).get("channel", ""))
    except (OSError, ValueError, AttributeError):
        return ""
    head, _, tail = ch.partition("/")
    ok = head == "early" and len(tail) == 32 and all(c in "0123456789abcdef" for c in tail)
    return ch if ok else ""


def _save_channel(channel):
    f = PROJECT_ROOT / CODE_FILE_REL
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"channel": channel, "saved": _dt.date.today().isoformat()}) + "\n", encoding="utf-8")


def forget_code():
    f = PROJECT_ROOT / CODE_FILE_REL
    if f.exists():
        f.unlink()
        print("Done: the early-access codeword is forgotten. From now on you get the regular updates only.")
    else:
        print("There was no early-access codeword saved here, so nothing changed. You get the regular updates.")


def _curl_get(url, timeout, dest=None):
    """The same request through curl: bytes (or True once `dest` is written), None if curl is missing or fails.

    Python's own requests follow the Mac's system proxy settings and a security or VPN app's filter, and some
    Pythons carry no certificate list; curl does neither, which is why the session-start check (curl) saw a new
    version while "update me" (Python) got "not found" and then "couldn't reach the server" on the same Mac, five
    days apart (buyer report, 2026-10-19). Safe to fall back to: whatever arrives must still match the
    publisher's signature and the feed's checksum before anything is applied.
    """
    curl = shutil.which("curl")
    if not curl:
        return None
    cmd = [curl, "-fsSL", "-A", "engine-updater", "--connect-timeout", "20"]
    # A feed is tiny, so it gets a hard limit; a large download only stops when it stalls for `timeout` seconds.
    cmd += ["--max-time", str(timeout)] if dest is None else ["--speed-limit", "1", "--speed-time", str(timeout)]
    if dest is not None:
        cmd += ["-o", str(dest)]
    try:
        r = subprocess.run(cmd + [url], capture_output=True, timeout=(timeout + 30) if dest is None else None)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        if dest is not None:
            Path(dest).unlink(missing_ok=True)
        return None
    return True if dest is not None else r.stdout


def _http_get(url, timeout, dest=None):
    """GET `url` as the updater: Python first, then curl if Python can't get through. Returns the body, or writes
    it to `dest`. Raises Python's own error when both fail, so callers keep their messages."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "engine-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if dest is None:
                return resp.read()
            with open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        got = _curl_get(url, timeout, dest)
        if got is None:
            raise e
        return got


def _download_verified(url, dest, expected):
    """Download the update file to `dest` and check it against the feed's sha256: True once it matches, False (and
    no file left behind) when it never does. Raises Python's error when it can't be downloaded at all.

    A network filter (a security or VPN app, a school or office proxy) can hand Python a damaged zip without an error,
    so _http_get's curl fallback never runs and the update stopped at the checksum (buyer report, 2026-10-21). A
    mismatch is asked once more through curl before giving up; whatever arrives must still match the same checksum.
    """
    _http_get(url, 60, dest=dest)
    if sha256(dest) == expected:
        return True
    Path(dest).unlink(missing_ok=True)
    print("That download came through damaged. Trying once more another way...")
    if _curl_get(url, 60, dest) is not None and Path(dest).is_file() and sha256(dest) == expected:
        return True
    Path(dest).unlink(missing_ok=True)
    return False


def _read_feed(feed_url):
    """(latest.json as a dict, None), or (None, the error). Asked twice, a few seconds apart, so one hiccup
    (a not-found while a new version is being published, a dropped connection) does not end the update."""
    err = None
    for attempt in range(2):
        try:
            return json.loads(_http_get(feed_url, 20).decode("utf-8")), None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as e:
            err = e
            if attempt == 0:
                time.sleep(FEED_RETRY_WAIT)
    return None, err


def _package_version(pkg):
    """The version an update file in her folder would install ("0.0.0" when it can't be read)."""
    pkg = Path(pkg)
    try:
        if pkg.is_dir():
            return str(json.loads((pkg / "update.json").read_text(encoding="utf-8")).get("version", "0.0.0"))
        with zipfile.ZipFile(pkg) as zf:
            name = next((n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "update.json"), None)
            if name:
                return str(json.loads(zf.read(name).decode("utf-8")).get("version", "0.0.0"))
    except (OSError, ValueError, zipfile.BadZipFile):
        pass
    if "update-v" in pkg.name:
        return pkg.name.split("update-v", 1)[1].split(".zip")[0]
    return "0.0.0"


def fetch(dry_run=False, code=None):
    """Check the creator's update server; if it's newer, download + apply it.

    The feed is a small JSON file at <update_url>/latest.json describing the
    newest update package. The package itself sits next to it. Anything we
    download is still run through apply()'s hard safety net (protected files,
    path guards, per-file checksums, automatic backup), so a bad or tampered
    package can never touch personal files or land un-backed-up.
    """
    base = _update_url()
    if not base:
        # No online source configured — fall back to a locally-dropped file.
        pkg = find_package()
        if pkg:
            return apply(pkg, dry_run=dry_run)
        print("There's no online update source set for this engine yet, and I don't "
              "see an update file in your folder. If your creator sent you one, save "
              "it here and say \"update me\" again. You can also get the newest version "
              "the same place you first downloaded this engine, unzip it as a new folder, "
              "and say \"bring over my old engine\" to move your work into it.")
        return

    prod = load_product()
    cur_v = prod.get("version", "0.0.0")
    engine = prod.get("engine", "")
    feed_url = base + "/latest.json"

    latest, err = _read_feed(feed_url)
    if err is not None and not isinstance(err, json.JSONDecodeError):
        # Offline or server down. An update file in her folder is used only when it is NEWER than this copy:
        # an old one left behind by an earlier update used to be re-applied here, and it then reported "already
        # up to date" while the server had a newer version (buyer report, 2026-10-14).
        pkg = find_package()
        if pkg and semver(_package_version(pkg)) > semver(cur_v):
            print("(Couldn't reach the update server, but I found a newer update file in your "
                  "folder — using that.)")
            return apply(pkg, dry_run=dry_run)
        die(f"the update server didn't answer just now, so I couldn't check for a newer version. Nothing was "
            f"changed, and you're still on v{cur_v}. This doesn't mean you're up to date: say \"update me\" "
            f"again in a few minutes.\n\n"
            f"If it keeps timing out (some networks can't reach the update server), you don't have to wait on "
            f"it: get the newest version the same place you first downloaded this engine, unzip it as a new "
            f"folder, open that folder, and say \"bring over my old engine\". That moves your brand kit, packs, "
            f"settings and projects into the new version, and nothing in this folder is touched. Details: {err}")
    if err is not None:
        die("the update server sent something I couldn't read. Try again in a minute.")

    # Nothing in the feed is used (not its version, not its file name, not its summary) until it proves it came
    # from the publisher. A feed that cannot is treated as a tampered one: nothing is downloaded.
    us = _signature_module()
    why = us.check_feed(latest) if us else "the signature checker (scripts/update_signature.py) is missing"
    if why:
        die(f"the update server's announcement could not be verified as coming from this engine's publisher "
            f"({why}). For your safety I did not download or install anything, and nothing was changed. Try "
            f"again later; if it keeps happening, tell your creator.")

    # An early-access feed (a codeword typed now, or one saved from before). The newer of the two feeds wins.
    channel = code_channel(code) if code else _saved_channel()
    if channel:
        early, e_err = _read_feed(f"{base}/{channel}/latest.json")
        for alt in (code_tries(code)[1:] if code and e_err is not None else []):
            a_early, a_err = _read_feed(f"{base}/{code_channel(alt)}/latest.json")
            if a_err is None:                            # "v2.2.26 christmas" -> "christmas"
                channel, early, e_err = code_channel(alt), a_early, None
                break
        e_why = (us.check_feed(early) if us else "the signature checker is missing") if e_err is None else ""
        if code and e_err is not None:
            # No dead end over a word (buyer reports 2026-10-19: "/update christmas" after the test closed stopped
            # here and left her on the old version, editor locked). Every feature is in the regular release, so a
            # word that opens nothing simply gets the regular update. Nothing is saved.
            print("There's no codeword needed anymore: everything is in the regular update, so you're getting that.")
            code = None
        if e_err is None and e_why:
            die(f"the early update's announcement could not be verified as coming from this engine's publisher "
                f"({e_why}). For your safety I did not download or install anything, and nothing was changed.")
        if e_err is None:
            if code and not dry_run:
                _save_channel(channel)
            if semver(str(early.get("version", "0.0.0"))) > semver(str(latest.get("version", "0.0.0"))):
                latest, base = early, f"{base}/{channel}"
                print(f"Your early-access codeword opened v{latest.get('version')}, ahead of the regular updates.")
            elif code:
                print("Your codeword works, and the regular update is already as new as the early one, so you get "
                      "that.")
            if code and dry_run:
                # The check saves nothing, so the word is only remembered by the real run. Say so plainly: a
                # check that ends "up to date" must still be followed by the real run, or the word is lost.
                print("The codeword is not saved yet: run the update itself (without --check) to remember it, "
                      "even if there is nothing new to install.")
            elif code:
                print("Your codeword is saved: you're in the early group.")
        # A saved codeword whose feed is gone (the test is over) is no fault: the regular feed answers alone.

    new_v = str(latest.get("version", "0.0.0"))
    pkg_engine = str(latest.get("engine", ""))
    if pkg_engine and engine and pkg_engine != engine:
        die(f"the update server is serving updates for '{pkg_engine}', but this folder "
            f"is '{engine}'. Nothing applied.")

    if semver(cur_v) > semver(new_v):
        print(f"You're already up to date: you're on v{cur_v}, ahead of the newest published v{new_v} (an "
              f"early-access version). Nothing to do; the next release for everyone comes through as usual.")
        return
    if semver(cur_v) >= semver(new_v):
        print(f"You're already up to date (you're on v{cur_v}, newest is v{new_v}). Nothing to do.")
        return

    fname = str(latest.get("file", "")).strip()
    if not fname or "/" in fname or "\\" in fname or ".." in fname:
        die("the update server pointed at an update file with an unsafe name. Nothing applied.")

    expected = str(latest.get("sha256") or "").lower()
    if len(expected) != 64:
        die("the update server's announcement has no checksum for the update file. Nothing applied.")

    if dry_run:
        print(f"An update is available: v{cur_v}  ->  v{new_v}.")
        if latest.get("summary"):
            print(f"  What's in it (the publisher's notes): {us.clean_summary(latest['summary'], 600)}")
        print("Say \"update me\" to download and apply it. Nothing personal will be touched, "
              "and it's reversible.")
        return

    zip_url = base + "/" + fname
    dest_dir = PROJECT_ROOT / "_updates"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / fname
    print(f"Downloading update v{new_v}...")
    try:
        intact = _download_verified(zip_url, dest, expected)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        die(f"couldn't download the update ({zip_url}). Check your internet and try again. "
            f"Details: {e}")
    if not intact:
        die("the downloaded update failed its safety checksum, so I threw it away and "
            "changed nothing. Try again — if it keeps happening, tell your creator.")

    # Signed feed + matching sha256 = the publisher's own file. Hand it to the normal safe apply path.
    apply(str(dest), dry_run=False, verified=True)


def main():
    ap = argparse.ArgumentParser(add_help=True, description="Apply an engine update safely.")
    ap.add_argument("package", nargs="?", help="update folder or .zip (auto-found if omitted)")
    ap.add_argument("--fetch", action="store_true",
                    help="check the creator's update server online and apply if newer")
    ap.add_argument("--check", action="store_true", help="dry run; show changes, write nothing")
    ap.add_argument("--rollback", action="store_true", help="undo the most recent update")
    ap.add_argument("--version", action="store_true", help="print the installed version")
    ap.add_argument("--code", metavar="WORD",
                    help="an early-access codeword from the creator (remembered); 'off' forgets it")
    args = ap.parse_args()

    if args.version:
        print(load_product().get("version", "0.0.0"))
        return
    if args.rollback:
        rollback()
        return
    # Default (no explicit package): check online first, then fall back to a local
    # file. An explicit package path skips the network and applies that file.
    if args.code is not None and "".join(args.code.lower().split()) in ("off", "forget", "none", "stop"):
        forget_code()
        return
    if args.code is not None and not "".join(args.code.split()):
        die("the codeword was empty. Type it after /update, like: /update sunflower")
    if args.fetch or not args.package or args.code:
        fetch(dry_run=args.check, code=args.code)
        return
    apply(args.package, dry_run=args.check)


if __name__ == "__main__":
    main()
