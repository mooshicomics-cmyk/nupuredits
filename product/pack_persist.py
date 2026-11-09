#!/usr/bin/env python3
"""pack_persist.py — keep a creator-built style pack alive across an engine update.

A pack the creator builds ("build my own style pack" / `/studio recipe`) is written INTO two shipped
files: `creative-vault/style-packs.json` and `pack_palettes.py` (see pack_write.py). Neither file is
protected by the updater, and neither is merged, so a routine "update me" replaced both and the pack was
gone — while `user-style.json` (which IS protected) still named it, so the next build asked for a pack
that no longer existed. Their look, deleted by a maintenance step they were told was safe.

The fix keeps the shipped files exactly as they are (every reader keeps working, nothing else changes) and
adds ONE protected sidecar that records what the creator built:

    product/creative-vault/user-packs.json
        {"packs": {"<name>": {"block": ..., "recipe": ..., "palette": ..., "system_fonts": ...}},
         "forgotten": ["<name>", ...]}

`block` is the pack's style-packs.json body, `palette` every pack_palettes.py entry filed under its name,
`recipe` the same six entries in the shape pack_write.apply() takes (None for a QUICK pack, which has no
palette of its own: fonts + accent only), and `system_fonts` the "SYSTEM:<key>" font paths it points at.
All of it is read out of the files verbatim, so restoring a pack is a replay of what was there — not a
second, drifting implementation, and never an invented colour.

  record()    pack_write calls this after a successful write.
  harvest()   records every pack in a tree that is not recorded yet — the quick ones included (they used to
              be skipped as "incomplete", and the next update deleted them). Run on the live files before an
              update overwrites anything, it also brings a record up to date with a pack she has since
              changed: before an update, the live files are the truth.
  restore()   replays recorded packs that the shipped files no longer have. Runs after an update.
  rescue()    after an update: the above, plus every pack still sitting in an update backup — so a pack an
              EARLIER update deleted, before any of this existed, comes back too.
  forget()    "delete my pack X" for good: it leaves both files and is never brought back from a backup.
  adopt_edited()  a SHIPPED pack she changed in place (Butter with her own colours) comes back as her own
              pack, "My Butter", instead of being quietly reset to the shipped one. Runs after an update
              (keep_changes.py), against shipped_history() of every version the engine shipped.

    python3 product/pack_persist.py recover     "restore my style pack": look everywhere, put back what is
                                                 missing, and say plainly what was found

Stdlib only, and every entry point is written so a damaged sidecar can never take a build (or an update)
down with it: on any unreadable state it reports and returns, it does not raise.
"""
import ast, collections, datetime, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIDECAR = os.path.join(HERE, "creative-vault", "user-packs.json")
PACKS_JSON = os.path.join(HERE, "creative-vault", "style-packs.json")
PALETTES = os.path.join(HERE, "pack_palettes.py")
BACKUPS = os.path.join(ROOT, "_update-backups")
USER_STYLE = os.path.join(HERE, "creative-vault", "user-style.json")

# pack_palettes.py dict  ->  the key it occupies in a pack_write `recipe`
_RECIPE_KEYS = {
    "GROUNDS": "ground",
    "HANDS_OFF_ACCENT": "hands_off_accent",
    "PALETTE": "palette",
    "TREATMENTS": "treatment",
    "PACK_ELEMENTS": "elements",
    "CARD_THEME": "card",
}

_DOC = ("Style packs YOU built, kept here so an engine update can never delete them. The engine reads "
        "your pack from style-packs.json + pack_palettes.py as usual; this file is the protected copy it "
        "restores from after an update. Safe to read, no need to edit. To delete a pack for good, say "
        "\"delete my style pack <name>\" (python3 product/pack_persist.py forget <name>), so no update "
        "backup ever brings it back.")


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _load_raw():
    try:
        with open(SIDECAR, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load():
    """Recorded packs as {name: {"block": ..., "recipe": ..., ...}}. Empty dict if there are none."""
    data = _load_raw() or {}
    packs = data.get("packs")
    return packs if isinstance(packs, dict) else {}


def forgotten():
    """Pack names she deleted for good: never recorded again from a backup, never restored."""
    data = _load_raw() or {}
    names = data.get("forgotten")
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def _write(packs, gone=None):
    out = {"_doc": _DOC, "packs": packs}
    gone = forgotten() if gone is None else gone
    if gone:
        out["forgotten"] = gone
    os.makedirs(os.path.dirname(SIDECAR), exist_ok=True)
    tmp = SIDECAR + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, SIDECAR)


def _palette_of(rec):
    """A saved pack's palette entries; a record from before they were kept carries only its recipe."""
    rec = rec or {}
    if rec.get("palette"):
        return rec["palette"]
    recipe = rec.get("recipe")
    return {d: recipe[k] for d, k in _RECIPE_KEYS.items() if k in recipe} if isinstance(recipe, dict) else {}


def _same(a, b):
    """Two saved packs are the same pack when everything that makes it up matches (dates ignored)."""
    pick = lambda r: json.dumps({"block": (r or {}).get("block"), "palette": _palette_of(r) or None,
                                 "system_fonts": (r or {}).get("system_fonts") or None}, sort_keys=True)
    return pick(a) == pick(b)


def record(name, block, recipe=None, palette=None, system_fonts=None, source="built", raw=None):
    """Remember pack `name` so an update can put it back. Best effort: returns True/False, never raises.

    `recipe` None = a quick pack. `palette` defaults to the recipe's six entries."""
    try:
        if palette is None and isinstance(recipe, dict):
            palette = {d: recipe[k] for d, k in _RECIPE_KEYS.items() if k in recipe}
        rec = {"block": block, "recipe": recipe, "palette": palette or {},
               "system_fonts": system_fonts or {}, "saved_at": _now(), "from": source}
        if raw:
            rec["unreadable"] = raw
        packs = load()
        packs[name] = rec
        _write(packs, [n for n in forgotten() if n != name])      # building it again un-forgets it
        return True
    except (OSError, TypeError, ValueError):
        return False


def _packs_path(base=None):
    return PACKS_JSON if base is None else os.path.join(base, "product", "creative-vault", "style-packs.json")


def _palettes_path(base=None):
    return PALETTES if base is None else os.path.join(base, "product", "pack_palettes.py")


def _read_cfg(base=None):
    try:
        with open(_packs_path(base), encoding="utf-8") as fh:
            cfg = json.load(fh, object_pairs_hook=collections.OrderedDict)
    except (OSError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) and isinstance(cfg.get("packs"), dict) else None


def _shipped_packs(base=None):
    """Pack names the ENGINE ships (flagged in_launch_kit). Everything else in the file is the creator's."""
    cfg = _read_cfg(base)
    if cfg is None:
        return None, None
    packs = cfg["packs"]
    return {n for n, v in packs.items() if isinstance(v, dict) and v.get("in_launch_kit")}, packs


def _palette_tree(base=None):
    """(source, parsed module or None) of the pack_palettes.py a tree holds. A backup that does not hold
    one means that update left the file alone, so the live copy is the one that goes with it."""
    path = _palettes_path(base)
    if base is not None and not os.path.isfile(path):
        path = _palettes_path()
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return "", None
    try:
        return src, ast.parse(src, path)
    except (SyntaxError, ValueError):
        return src, None


def _dict_names(base=None):
    """The names of the top-level dicts a tree's pack_palettes.py defines (None if it will not parse)."""
    _src, tree = _palette_tree(base)
    if tree is None:
        return None
    return {t.id for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
            for t in node.targets if isinstance(t, ast.Name)}


def _palette_values(name, base=None):
    """Every pack_palettes.py value filed under `name`, as {DICT: value}, read by AST (never by importing
    or exec'ing the file). When the file will not parse, the raw lines naming the pack come back as the
    second value, so they are kept as text rather than dropped."""
    src, tree = _palette_tree(base)
    if tree is None:
        needle = json.dumps(name, ensure_ascii=False)
        return {}, ([l for l in src.splitlines() if needle in l or f"'{name}'" in l] or None)
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == name:
                    try:
                        found[target.id] = ast.literal_eval(v)
                    except (ValueError, TypeError, SyntaxError):
                        pass
    return found, None


def palette_entries_in(text, name):
    """{recipe-key: value} for pack `name` in pack_palettes.py TEXT, read by AST (never exec'd): the six
    entries a pack_write recipe carries. Empty dict when the pack has no lines there; None when the text
    will not parse. Works on any version's text, so shipped_history() can read shipped originals with it,
    and pack_write --from starts a new pack from one."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, TypeError):
        return None
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        for target in node.targets:
            key = _RECIPE_KEYS.get(getattr(target, "id", None))
            if not key:
                continue
            for k, v in zip(node.value.keys, node.value.values):
                try:
                    if isinstance(k, ast.Constant) and k.value == name:
                        found[key] = ast.literal_eval(v)
                except (ValueError, TypeError):
                    pass
    return found


def _system_refs(block):
    refs = []
    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and v.startswith("SYSTEM:") and v[7:] not in refs:
            refs.append(v[7:])
    walk(block)
    return refs


def capture(name, base=None):
    """Pack `name` as it stands in one tree (the live one, or a backup's overwritten/ copy), or None.

    Read faithfully: its block, every palette entry under its name, and the system font paths it uses."""
    cfg = _read_cfg(base)
    if cfg is None or not isinstance(cfg["packs"].get(name), dict):
        return None
    block = cfg["packs"][name]
    palette, raw = _palette_values(name, base)
    recipe = ({k: palette[d] for d, k in _RECIPE_KEYS.items()}
              if all(d in palette for d in _RECIPE_KEYS) else None)
    have = cfg.get("system_fonts") if isinstance(cfg.get("system_fonts"), dict) else {}
    fonts = {k: have[k] for k in _system_refs(block) if k in have}
    rec = {"block": block, "recipe": recipe, "palette": palette, "system_fonts": fonts}
    if raw:
        rec["unreadable"] = raw
    return rec


def _with_palette_from(name, base):
    """Pack `name` with its block as the live files have it and its colour entries as `base` holds them (an
    update backup that saved pack_palettes.py alone), or None when the live files do not have the pack."""
    rec = capture(name)
    if rec is None:
        return None
    palette, raw = _palette_values(name, base)
    rec["palette"] = palette
    rec["recipe"] = ({k: palette[d] for d, k in _RECIPE_KEYS.items()} if all(d in palette for d in _RECIPE_KEYS)
                     else None)
    if raw:
        rec["unreadable"] = raw
    else:
        rec.pop("unreadable", None)
    return rec


def record_live(name, source="built"):
    """Record pack `name` exactly as it now stands in the live files (pack_write, after a write)."""
    rec = capture(name)
    if rec is None:
        return False
    return record(name, rec["block"], rec["recipe"], rec["palette"], rec["system_fonts"], source,
                  rec.get("unreadable"))


def harvest(base=None, refresh=None, source=None):
    """Record every creator-built pack in a tree: the live files, or an update backup (`base`).

    A quick pack (fonts + accent, no palette entries) is recorded like any other, exactly as it is. On the
    live files (base None) a record she has since moved on from is brought up to date, because before an
    update the live files are the truth; a backup is older than any record, so it only fills gaps.

    Returns (recorded, problems): the names saved or brought up to date, and (name, why) pairs for anything
    that could not be read or saved. Nothing is ever skipped silently."""
    refresh = (base is None) if refresh is None else refresh
    source = source or ("live files" if base is None else f"update backup {os.path.basename(os.path.dirname(base.rstrip(os.sep)))}")
    shipped, packs = _shipped_packs(base)
    if packs is None:
        if os.path.exists(_packs_path(base)):
            return [], [("(style-packs.json)", "could not be read, so the packs in it were not checked")]
        return [], []
    # A pack she deleted for good never comes back from a BACKUP. One in the live files is hers again
    # (she built it anew), so it is recorded, which un-forgets it.
    known, gone = load(), (set(forgotten()) if base is not None else set())
    recorded, problems = [], []
    for name in packs:
        if name in shipped or name in gone:
            continue
        rec = capture(name, base)
        if rec is None:
            # Not a pack block at all (a damaged entry). It cannot be rebuilt, but it is never dropped:
            # keep it exactly as it is, and say so.
            raw = packs[name]
            if name not in known or (refresh and (known[name] or {}).get("block") != raw):
                if record(name, raw, None, {}, {}, source):
                    recorded.append(name)
                problems.append((name, "its entry in style-packs.json is not a pack block, so it cannot be "
                                       "rebuilt; it is kept exactly as it was in user-packs.json"))
            continue
        if name in known and refresh:
            # A saved entry for a table the engine no longer has could not be put back last time, so its
            # absence from the live files is not her choice: keep it rather than refresh it away.
            tables = _dict_names(base) or set()
            for d, v in ((known[name] or {}).get("palette") or {}).items():
                if d not in rec["palette"] and d not in tables:
                    rec["palette"][d] = v
        if name in known and (not refresh or _same(known[name], rec)):
            continue
        if record(name, rec["block"], rec["recipe"], rec["palette"], rec["system_fonts"], source,
                  rec.get("unreadable")):
            recorded.append(name)
            if rec.get("unreadable"):
                problems.append((name, "pack_palettes.py could not be read, so its colour lines are kept "
                                       "as text in user-packs.json"))
        else:
            problems.append((name, "could not be saved to user-packs.json"))
    return recorded, problems


def _pack_write():
    try:
        import pack_write
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("pack_write", os.path.join(HERE, "pack_write.py"))
        pack_write = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pack_write)
    return pack_write


def missing_tables(name, saved):
    """The pack_palettes.py tables a saved pack has entries in, where the live file has NO entry for it (and the
    table itself still exists). An update that replaced pack_palettes.py but not style-packs.json leaves her pack's
    name in place with every colour of it gone: this is how restore() and the record see that."""
    have = _dict_names() or set()
    live, _raw = _palette_values(name)
    return sorted(d for d in _palette_of(saved) if d in have and d not in live)


def restore():
    """Replay recorded packs the shipped files no longer carry, whole or in part.

    Returns (restored, problems) where `problems` is a list of (name, reason) the creator should see.
    Nothing is ever forced over a pack that is already there: a pack whose block is present has only its
    MISSING colour entries written back (an update that replaced pack_palettes.py alone took them)."""
    known = load()
    if not known:
        return [], []
    shipped, packs = _shipped_packs()
    if packs is None:
        return [], [("(all)", "style-packs.json could not be read, so nothing was restored")]
    try:
        pack_write = _pack_write()
    except Exception:
        return [], [("(all)", "pack_write.py could not be loaded, so nothing was restored")]

    gone = set(forgotten())
    restored, problems = [], []
    for name, saved in known.items():
        if name in gone or not isinstance(saved, dict):
            continue
        if name in packs:
            if name in shipped:
                problems.append((name, "the engine now ships a pack with this name, so yours was not "
                                       "written over it. Yours is still saved; rename it to use it."))
                continue
            if not (missing_tables(name, saved) and isinstance(saved.get("block"), dict)
                    and hasattr(pack_write, "restore_pack")):
                continue                               # already present, whole, and hers: leave it alone
            # Its block is here but its colours are not (pack_palettes.py was replaced on its own). The same
            # writer puts back only what is missing; entries still there are never written twice.
            try:
                problems += [(name, why) for why in pack_write.restore_pack(name, saved)]
                restored.append(name)
            except Exception as exc:                    # pack_write raises before touching anything
                problems.append((name, f"its colours could not be put back ({exc}); they are saved in "
                                       f"user-packs.json"))
            continue
        if not isinstance(saved.get("block"), dict):
            problems.append((name, "its saved copy is incomplete, so it was not restored (it is kept in "
                                   "user-packs.json)"))
            continue
        try:
            if hasattr(pack_write, "restore_pack"):
                rest = pack_write.restore_pack(name, saved)
            else:                                       # an older pack_write: recipe packs only
                pack_write.apply(name, saved["block"], saved["recipe"])
                rest = []
            restored.append(name)
            problems += [(name, why) for why in rest]
            if saved.get("unreadable"):
                problems.append((name, "its colour lines were saved as text only; ask Claude to put them "
                                       "back from user-packs.json"))
        except Exception as exc:                        # pack_write raises before touching anything
            problems.append((name, str(exc)))
    return restored, problems


def reassert():
    """After an undo (apply-update --rollback) put OLDER pack files back: every pack of hers whose copy in the
    live files is not the one she last had (she changed it after the update, and harvest() recorded that just
    before the undo) is written as she last had it. restore() only adds a pack that is missing; this is the other
    half. Returns (fixed, problems)."""
    known = load()
    if not known:
        return [], []
    shipped, packs = _shipped_packs()
    if packs is None:
        return [], [("(all)", "style-packs.json could not be read, so your packs were not checked")]
    gone, fixed, problems = set(forgotten()), [], []
    for name, saved in known.items():
        if (name in gone or name not in packs or name in (shipped or set()) or not isinstance(saved, dict)
                or not isinstance(saved.get("block"), dict)):
            continue
        live = capture(name)
        if live is None or _same(live, saved):
            continue
        try:
            rest = _pack_write().replace_pack(name, dict(saved))
            fixed.append(name)
            problems += [(name, why) for why in rest]
        except Exception as exc:   # noqa: BLE001  (pack_write refuses before writing anything)
            problems.append((name, f"your latest version is saved, but could not be put back in place of the older "
                                   f"one ({exc})"))
    return fixed, problems


def _stamp(dirname):
    m = re.search(r"(\d{8}-\d{6})", dirname)
    return m.group(1) if m else ""


def backups():
    """Update backups holding a copy of style-packs.json, newest first, as (folder, its overwritten/ tree)."""
    try:
        names = os.listdir(BACKUPS)
    except OSError:
        return []
    found = []
    for n in names:
        ow = os.path.join(BACKUPS, n, "overwritten")
        if os.path.isfile(_packs_path(ow)):
            found.append((_stamp(n), os.path.getmtime(os.path.join(BACKUPS, n)), n, ow))
    found.sort(reverse=True)
    return [(n, ow) for _s, _m, n, ow in found]


def rescue(fresh=None):
    """After an update, bring back every pack of hers from wherever one can still be found.

    `fresh` is the update backup the update that just ran made (post-update passes it, once). It holds her
    packs exactly as they were a moment before the update, so it is the truth for them: a record older
    than it is brought up to date, and a pack an older updater put back from such an older record is
    swapped for the one she actually had. Every OTHER backup is older than any record, so it only fills
    gaps — that is how a pack an EARLIER update deleted, before the protected copy existed, comes back.

    Returns {"recovered": [(name, backup)], "updated": [...], "fixed": [...], "restored": [...],
             "problems": [(name, why)]}. Safe to run any number of times."""
    out = {"recovered": [], "updated": [], "fixed": [], "restored": [], "problems": []}
    gone = set(forgotten())
    if fresh and (os.path.isfile(_packs_path(fresh)) or os.path.isfile(_palettes_path(fresh))):
        # A backup holding only pack_palettes.py: that update left style-packs.json alone, so her pack blocks are
        # the live ones and her colours are the backup's.
        packs_there = os.path.isfile(_packs_path(fresh))
        replaced_both = packs_there and os.path.isfile(_palettes_path(fresh))   # that update overwrote both pack files
        shipped, packs = _shipped_packs(fresh if packs_there else None)
        shipped = shipped or set()
        before = load()
        for name in (packs or {}):
            if name in shipped or name in gone:
                continue
            truth = capture(name, fresh) if packs_there else _with_palette_from(name, fresh)
            live, old = capture(name), before.get(name)
            if truth is None:
                continue
            if old is None or not _same(old, truth):
                record(name, truth["block"], truth["recipe"], truth["palette"], truth["system_fonts"],
                       f"update backup {os.path.basename(os.path.dirname(fresh))}", truth.get("unreadable"))
                out["updated"].append(name)
            if replaced_both and live is not None and old is not None and not _same(live, truth) \
                    and _same(live, old):
                try:
                    rest = _pack_write().replace_pack(name, dict(truth))
                    out["fixed"].append(name)
                    out["problems"] += [(name, why) for why in rest]
                except Exception as exc:
                    out["problems"].append((name, f"your latest version is saved, but could not be put back "
                                                  f"in place of the older one ({exc})"))
    for folder, ow in backups():
        got, probs = harvest(ow, refresh=False, source=f"update backup {folder}")
        out["recovered"] += [(n, folder) for n in got]
        out["problems"] += probs
    got, probs = harvest(refresh=False)               # a pack only in the live files (pasted by hand)
    out["problems"] += probs
    restored, probs = restore()
    out["restored"] = restored
    out["problems"] += probs
    return out


def default_pack_status():
    """(pack name or None, True when that pack is available to build with)."""
    import sys
    if HERE not in sys.path:                               # the updater loads this file and then takes product/ off its
        sys.path.insert(0, HERE)                           # path: without this the import below failed on every update
    try:
        import user_style
        name = user_style.default_pack(USER_STYLE)
    except ImportError:                                    # an update step running before user_style.py landed
        try:
            with open(USER_STYLE, encoding="utf-8") as fh:
                name = (json.load(fh) or {}).get("default_pack")
        except (OSError, ValueError, AttributeError):
            name = None
    if not name:
        return None, True
    _shipped, packs = _shipped_packs()
    avail = set(packs or {})
    local = os.path.join(ROOT, "_local", "style-packs.json")
    try:
        with open(local, encoding="utf-8") as fh:
            avail |= set((json.load(fh) or {}).get("packs", {}))
    except (OSError, ValueError, AttributeError):
        pass
    return name, name in avail


def forget(name):
    """Delete pack `name` for good: out of both files, out of the saved copies, and remembered as gone so
    no update backup ever brings it back. A launch pack is never removed. Returns a short report."""
    shipped, _packs = _shipped_packs()
    if name in (shipped or set()):
        return f"'{name}' is one of the engine's own packs; it stays."
    packs = load()
    was = name in packs
    packs.pop(name, None)
    gone = [n for n in forgotten() if n != name] + [name]
    _write(packs, gone)
    try:
        _pack_write().remove_pack(name)
    except Exception as exc:
        return f"stopped keeping '{name}', but it could not be taken out of the pack files ({exc})"
    return (f"deleted '{name}' for good" if was else f"'{name}' was not saved; it is now also out of the "
            f"pack files and will not come back from an update backup")


def _recover_report():
    r = rescue()
    lines = []
    for name, folder in r["recovered"]:
        lines.append(f"  brought back '{name}' (it was still in the update backup {folder})")
    for name in r["restored"]:
        if name not in [n for n, _f in r["recovered"]]:
            lines.append(f"  put '{name}' back in place from your saved copy")
    for name, why in r["problems"]:
        lines.append(f"  ! '{name}': {why}")
    shipped, packs = _shipped_packs()
    mine = [n for n in (packs or {}) if n not in (shipped or set())]
    if not r["recovered"] and not r["restored"]:
        lines.append("  nothing was missing." + (f" Your packs are all here: {', '.join(mine)}." if mine
                                                   else " You have not built a pack of your own yet."))
    elif mine:
        lines.append(f"  your packs now: {', '.join(mine)}")
    name, ok = default_pack_status()
    if name and not ok:
        lines.append(f"  ! your default pack is '{name}', and it is not in this engine or any update backup. "
                     f"Rebuild it (\"build my own style pack\") or pick another (\"use Butter\").")
    elif name:
        lines.append(f"  your default pack '{name}' is ready to build with.")
    return "\n".join(lines)


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def shipped_history(texts):
    """What every SHIPPED version of each launch pack looked like, from (style-packs.json text,
    pack_palettes.py text) pairs of past releases. Either text may be None. Returns
    {"blocks": {name: {canon}}, "entries": {name: {key: {canon}}}}."""
    blocks, entries = collections.defaultdict(set), collections.defaultdict(lambda: collections.defaultdict(set))
    names = set()
    for packs_text, pal_text in texts:
        if packs_text:
            try:
                packs = json.loads(packs_text).get("packs") or {}
            except (ValueError, AttributeError):
                packs = {}
            for n, b in packs.items():
                if isinstance(b, dict) and b.get("in_launch_kit"):
                    blocks[n].add(_canon(b))
                    names.add(n)
    for packs_text, pal_text in texts:
        if pal_text:
            for n in names:
                got = palette_entries_in(pal_text, n) or {}
                for k, v in got.items():
                    entries[n][k].add(_canon(v))
    return {"blocks": dict(blocks), "entries": {n: dict(e) for n, e in entries.items()}}


def _free_name(base, taken):
    for cand in [f"My {base}"] + [f"My {base} {i}" for i in range(2, 20)]:
        if cand not in taken and re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,31}", cand):
            return cand
    return None


def adopt_edited(her_base, history):
    """A SHIPPED pack she changed in place comes back as her own pack instead of being reset.

    `her_base` is a tree holding her pre-update pack files (the update's backup of what it replaced);
    `history` is shipped_history() of every version this engine ever shipped. A launch pack whose settings
    or palette lines match NO shipped version was edited on her machine ("keep Butter but make the blue
    pink"). The update has just put the shipped pack back, so her version is written as a new pack,
    "My Butter", recorded like any pack she builds, and made her default when the edited pack was it.

    Returns a list of {"pack", "saved_as", "default_switched"} and a list of (name, reason) problems.
    Packs with no shipped history to compare against are left alone: never guess that she changed one.

    An update that replaced only ONE of the two pack files saved only that one: the other is still hers, as she
    left it, in the live engine, so that is where her copy of it is read."""
    packs_file = _packs_path(her_base) if os.path.isfile(_packs_path(her_base)) else PACKS_JSON
    pal_file = _palettes_path(her_base) if os.path.isfile(_palettes_path(her_base)) else PALETTES
    try:
        with open(packs_file, encoding="utf-8") as fh:
            her_packs = json.load(fh).get("packs") or {}
    except (OSError, ValueError, AttributeError):
        return [], []
    try:
        with open(pal_file, encoding="utf-8") as fh:
            her_pal = fh.read()
    except OSError:
        her_pal = None
    shipped_now, live = _shipped_packs()
    if live is None:
        return [], [("(all)", "style-packs.json could not be read, so edited packs were not checked")]
    done, problems = [], []
    taken = set(live) | set(load())
    for name, block in her_packs.items():
        if not (isinstance(block, dict) and block.get("in_launch_kit")):
            continue                                        # her own packs are harvest()'s job
        known_blocks = history.get("blocks", {}).get(name)
        if not known_blocks:
            continue
        her_entries = (palette_entries_in(her_pal, name) or {}) if her_pal else {}
        known_entries = history.get("entries", {}).get(name, {})
        block_edited = _canon(block) not in known_blocks
        entries_edited = any(k in known_entries and _canon(v) not in known_entries[k]
                             for k, v in her_entries.items())
        if not (block_edited or entries_edited):
            continue
        own = dict(block)
        own["in_launch_kit"] = False
        recipe = her_entries if all(k in her_entries for k in _RECIPE_KEYS.values()) else None
        same = next((n for n, saved in load().items()
                     if _canon(saved.get("block")) == _canon(own) and _canon(saved.get("recipe")) == _canon(recipe)), None)
        if same:
            # She already has a pack exactly like her edited one (or an earlier run saved it): do not make a
            # second copy, but do not leave her default on the pack the update just reset either.
            switched = _switch_default(name, same)
            if switched:
                done.append({"pack": name, "saved_as": same, "default_switched": True})
            continue
        new = _free_name(name, taken)
        if not new:
            problems.append((name, "your version could not be given a free name, so it was not saved"))
            continue
        try:
            _pack_write().apply(new, own, recipe)
        except Exception as exc:                            # pack_write refuses before writing anything
            problems.append((name, f"your version could not be saved as {new}: {exc}"))
            continue
        taken.add(new)
        switched = _switch_default(name, new)
        done.append({"pack": name, "saved_as": new, "default_switched": switched})
    return done, problems


def _switch_default(old, new):
    """If her saved default is the pack she had edited, point it at her version of it."""
    path = USER_STYLE
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(st, dict) or st.get("default_pack") != old:
        return False
    st["default_pack"] = new
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(st, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return True


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "harvest":
        got, bad = harvest(sys.argv[2] if len(sys.argv) > 2 else None)
        print(f"recorded: {got or 'nothing new'}")
        for n, why in bad:
            print(f"  ! {n}: {why}")
    elif cmd == "restore":
        got, bad = restore()
        print(f"restored: {got or 'nothing to restore'}")
        for n, why in bad:
            print(f"  ! {n}: {why}")
    elif cmd in ("recover", "rescue"):
        print("Looking for your style packs (the engine, your saved copies, every update backup)...")
        print(_recover_report())
    elif cmd == "forget" and len(sys.argv) > 2:
        print(forget(" ".join(sys.argv[2:])))
    else:
        for n in load():
            print(n)
