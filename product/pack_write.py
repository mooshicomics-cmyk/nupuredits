#!/usr/bin/env python3
"""pack_write.py — apply a generated style pack to the two files that define it, or refuse.

The recipe tools print two paste-ready blocks and ask the creator to copy them into
`creative-vault/style-packs.json` and `pack_palettes.py` by hand. That is six separate entries across
two files, and the failure is silent: miss one and the pack falls back to ANOTHER pack's values in the
designed lanes, which looks like a broken pack rather than a missing line. This does it in one step.

Safety, because this edits files the whole engine reads:
  * every existing pack must survive byte-identical — verified by re-reading after the write
  * a launch-kit pack is never touched, and an existing name needs an explicit overwrite
  * both files are written, or neither: each is staged, parsed, verified, and only then moved into place
  * the previous version of each file is kept next to it as .bak before anything moves

Every pack written here is also recorded in the protected `creative-vault/user-packs.json` via
pack_persist, because BOTH files below are shipped and an update overwrites them.

A QUICK pack (the `style-pack` skill: her three fonts and one accent colour on a shipped pack's locked
layout) has no palette of its own, so it lives in style-packs.json alone. It is saved through this same
writer with no recipe, which is what records it in the protected copy too. Before this route existed the
skill had Claude edit style-packs.json by hand, nothing recorded it, and the next update deleted it:

    python3 product/pack_write.py --name "My Pack" --block my-pack.json [--system-font "Font=/abs/path"]

"Keep Butter but make the blue pink" is a NEW pack of hers started from a shipped one, never an edit to the
shipped pack (every update resets those):

    python3 product/pack_write.py --name "Butter Blush" --from Butter --set palette.dark=#C2527A

(Windows: python, never python3.) It warns when text in a new colour will not read on its background.

IN THE COPY THE ENGINE SHIPS FROM (the seller's own engine: `make-ship.sh` sits at its root, and make-ship
never puts itself in a bundle, so a buyer's copy never has it) both files above are the SHIPPED ones, and a
pack of hers written there would ride into every buyer's bundle. So there it goes to `_local/` instead:
the block to `_local/style-packs.json` (stylepack merges it in) and its palette to `_local/pack-palettes.json`
(pack_palettes merges it in). Both are git-ignored and never staged. Nothing is recorded in user-packs.json
there: that copy is never updated, so nothing needs putting back. A buyer's copy is unchanged.

Used by frame_to_pack.py --write, pack_recipe.py --write and the style-pack skill; pack_persist puts a pack
back after an update through `restore_pack` / `replace_pack`, the same writer without re-recording it, and
saves a shipped pack she edited in place as her own ("My Butter") through `apply`.
"""
import ast, json, os, re, shutil, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACKS_JSON = os.path.join(HERE, "creative-vault", "style-packs.json")
PALETTES = os.path.join(HERE, "pack_palettes.py")

# name -> how that entry is rendered into pack_palettes.py
_DICTS = ("GROUNDS", "HANDS_OFF_ACCENT", "PALETTE", "TREATMENTS", "PACK_ELEMENTS", "CARD_THEME")


def _engine_root():
    """The engine folder that owns PACKS_JSON (product/creative-vault/style-packs.json -> its root). Taken from
    PACKS_JSON, not from this file, so a caller that points the writer at scratch copies decides it too."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(PACKS_JSON))))


def source_copy():
    """True in the copy the engine ships from: make-ship.sh is there, and it never ships."""
    return os.path.isfile(os.path.join(_engine_root(), "make-ship.sh"))


def _local_packs_path():
    return os.path.join(_engine_root(), "_local", "style-packs.json")


def _local_palettes_path():
    return os.path.join(_engine_root(), "_local", "pack-palettes.json")


def _read_json(path):
    """A _local JSON file as an OrderedDict ({} when it is not there yet). Unreadable refuses: never overwrite it."""
    if not os.path.exists(path):
        return collections.OrderedDict()
    try:
        data = json.loads(open(path, encoding="utf-8").read(), object_pairs_hook=collections.OrderedDict)
    except ValueError as e:
        raise PackWriteError(f"{path} could not be read ({e}), so it was left as it is. Nothing written.")
    if not isinstance(data, dict):
        raise PackWriteError(f"{path} is not a JSON object, so it was left as it is. Nothing written.")
    return data


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


class PackWriteError(Exception):
    """Raised before anything is written. The message is what the creator sees."""


def _read_packs():
    return json.loads(open(PACKS_JSON, encoding="utf-8").read(),
                      object_pairs_hook=collections.OrderedDict)


def _insert_into_dict(src, dict_name, line):
    """Insert `line` just before the closing brace of a top-level `NAME = {` dict literal."""
    m = re.search(rf"^{dict_name}\s*=\s*\{{", src, flags=re.M)
    if not m:
        raise PackWriteError(f"{PALETTES}: could not find the '{dict_name}' dict — file shape changed, "
                             f"not writing anything. Paste the printed blocks by hand.")
    close = re.compile(r"^\}$", flags=re.M).search(src, m.end())
    if not close:
        raise PackWriteError(f"{PALETTES}: '{dict_name}' has no closing brace at column 0 — not writing.")
    return src[:close.start()] + line + src[close.start():]


def _dict_entries(src):
    """{DICT_NAME: {key: (line, col, end_line, end_col)}} for every top-level `NAME = {...}` dict, by AST.

    Lines are 1-based; columns are UTF-8 byte offsets, as the ast module gives them."""
    out = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = {k.value: (k.lineno, k.col_offset, v.end_lineno, v.end_col_offset)
                                  for k, v in zip(node.value.keys, node.value.values)
                                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return out


def _render_recipe(recipe):
    """The six pack_palettes.py entries of a recipe, rendered exactly as the recipe tools always have."""
    return {
        "GROUNDS": f'"{recipe["ground"]}"',
        "HANDS_OFF_ACCENT": f'"{recipe["hands_off_accent"]}"',
        "PALETTE": repr(recipe["palette"]),
        "TREATMENTS": repr(recipe["treatment"]),
        "PACK_ELEMENTS": repr(recipe["elements"]),
        "CARD_THEME": repr(recipe["card"]),
    }


def _render_value(value):
    """One saved pack_palettes.py value back as Python source (a string as a JSON string: same text, safe)."""
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else repr(value)


def system_font_refs(block):
    """The `system_fonts` keys a pack points at ("SYSTEM:<key>" anywhere in its block)."""
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


def _write(name, block, entries, system_fonts, force):
    """The one writer both routes share. `entries` maps a pack_palettes.py dict to the Python source of this
    pack's value in it — empty for a quick pack, which lives in style-packs.json alone and never touches
    pack_palettes.py. Returns (dicts whose entry did not land, notes for the report)."""
    if source_copy():
        return _write_local(name, block, entries, system_fonts, force)
    cfg = _read_packs()
    existing = cfg.get("packs", {})
    if name in existing:
        if isinstance(existing[name], dict) and existing[name].get("in_launch_kit"):
            raise PackWriteError(f"'{name}' is a LAUNCH pack. Those are hand-tuned and shipped; this will "
                                 f"not overwrite one. Pick another name.")
        if not force:
            raise PackWriteError(f"'{name}' already exists. Re-run with --force to replace it, or pick "
                                 f"another name. (Its current values are not backed up anywhere else.)")

    before_packs = {k: json.dumps(v, sort_keys=True) for k, v in existing.items() if k != name}
    notes = []

    # ---- stage style-packs.json -------------------------------------------------------------
    cfg.setdefault("packs", collections.OrderedDict())[name] = json.loads(
        json.dumps(block), object_pairs_hook=collections.OrderedDict)
    for key, path in (system_fonts or {}).items():
        have = cfg.setdefault("system_fonts", collections.OrderedDict())
        if key not in have:
            have[key] = path
        elif have[key] != path:
            notes.append(f"    system font '{key}' already points at {have[key]}; kept that one")
    staged_json = json.dumps(cfg, indent=1, ensure_ascii=False) + "\n"
    reparsed = json.loads(staged_json)
    if name not in reparsed.get("packs", {}):
        raise PackWriteError("internal: staged style-packs.json did not round-trip — nothing written.")
    for k, v in before_packs.items():
        if json.dumps(reparsed["packs"].get(k), sort_keys=True) != v:
            raise PackWriteError(f"internal: writing '{name}' would have altered the existing pack "
                                 f"'{k}' — nothing written.")

    # ---- stage pack_palettes.py (a pack with a palette of its own) ---------------------------
    staged_py = None
    if entries:
        src = open(PALETTES, encoding="utf-8").read()
        for d in _DICTS:
            if re.search(rf'^\s*"{re.escape(name)}"\s*:', src, flags=re.M) and not force:
                raise PackWriteError(f"'{name}' already appears in {os.path.basename(PALETTES)} — "
                                     f"remove it or use --force.")
        # Replacing her pack (--force) takes its old entries out first. Inserting alone left every old line
        # in place beside the new one: Python keeps the last duplicate key, so the new look still won, but
        # each --force doubled her entries and the old values stayed in the file.
        staged_py = _remove_entries(src, name) if force else src
        for d, literal in entries.items():
            staged_py = _insert_into_dict(staged_py, d, f'    {json.dumps(name, ensure_ascii=False)}: {literal},\n')
        compile(staged_py, PALETTES, "exec")          # syntax-check before it can reach disk

    # ---- commit: back up, then move both ----------------------------------------------------
    writes = [(PACKS_JSON, staged_json)] + ([(PALETTES, staged_py)] if staged_py is not None else [])
    for path, _text in writes:
        shutil.copy2(path, path + ".bak")
    for path, text in writes:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)

    # ---- verify what actually landed ---------------------------------------------------------
    missing = []
    if staged_py is not None:
        landed = _dict_entries(open(PALETTES, encoding="utf-8").read())
        missing = [d for d in entries if name not in landed.get(d, {})]
    after = _read_packs().get("packs", {})
    if name not in after:
        raise PackWriteError(f"wrote the files but '{name}' is not in style-packs.json — restore from .bak")
    for k, v in before_packs.items():
        if json.dumps(after.get(k), sort_keys=True) != v:
            raise PackWriteError(f"wrote the files but existing pack '{k}' changed — restore from .bak")
    return missing, notes


def _write_local(name, block, entries, system_fonts, force):
    """_write for the copy the engine ships from: her pack lands in _local/, and both shipped files are left
    byte-identical (checked after the write). Same rules: a launch name is refused, an existing name needs
    force, every other pack of hers survives unchanged."""
    shipped_bytes = {p: open(p, "rb").read() for p in (PACKS_JSON, PALETTES)}
    shipped = _read_packs()
    shipped_packs = shipped.get("packs", {})
    if isinstance(shipped_packs.get(name), dict) and shipped_packs[name].get("in_launch_kit"):
        raise PackWriteError(f"'{name}' is a LAUNCH pack. Those are hand-tuned and shipped; this will "
                             f"not overwrite one. Pick another name.")
    local_path, pal_path = _local_packs_path(), _local_palettes_path()
    cfg = _read_json(local_path)
    packs = cfg.setdefault("packs", collections.OrderedDict())
    if (name in packs or name in shipped_packs) and not force:
        raise PackWriteError(f"'{name}' already exists. Re-run with --force to replace it, or pick "
                             f"another name. (Its current values are not backed up anywhere else.)")
    before_packs = {k: json.dumps(v, sort_keys=True) for k, v in packs.items() if k != name}
    notes = []

    packs[name] = json.loads(json.dumps(block), object_pairs_hook=collections.OrderedDict)
    shipped_fonts = shipped.get("system_fonts", {})
    for key, path in (system_fonts or {}).items():
        have = cfg.setdefault("system_fonts", collections.OrderedDict())
        known = shipped_fonts.get(key, have.get(key))
        if known is None:
            have[key] = path
        elif known != path:
            notes.append(f"    system font '{key}' already points at {known}; kept that one")

    pal = None
    if entries:
        pal = _read_json(pal_path)
        if force:                                  # replacing her pack: its old entries go first
            for table in pal.values():
                if isinstance(table, dict):
                    table.pop(name, None)
        for d, literal in entries.items():
            pal.setdefault(d, collections.OrderedDict())[name] = ast.literal_eval(literal)

    _write_json(local_path, cfg)
    if pal is not None:
        _write_json(pal_path, pal)

    for p, raw in shipped_bytes.items():
        if open(p, "rb").read() != raw:
            raise PackWriteError(f"internal: {os.path.basename(p)} changed while saving '{name}' to _local — "
                                 f"restore it from git")
    after = _read_json(local_path).get("packs", {})
    if name not in after:
        raise PackWriteError(f"wrote _local/style-packs.json but '{name}' is not in it — restore from .bak")
    for k, v in before_packs.items():
        if json.dumps(after.get(k), sort_keys=True) != v:
            raise PackWriteError(f"wrote _local/style-packs.json but your pack '{k}' changed — restore from .bak")
    landed = _read_json(pal_path) if entries else {}
    missing = [d for d in entries if name not in (landed.get(d) or {})]
    return missing, notes


def _local_palettes():
    """{DICT: {pack: value}} kept in _local/pack-palettes.json ({} outside the copy the engine ships from)."""
    if not source_copy():
        return {}
    try:                                           # plain dicts: a value here is rendered back as source
        return json.loads(json.dumps(_read_json(_local_palettes_path())))
    except PackWriteError:
        return {}


def _persist():
    try:
        import pack_persist
    except ImportError:
        import importlib.util
        _spec = importlib.util.spec_from_file_location("pack_persist", os.path.join(HERE, "pack_persist.py"))
        pack_persist = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(pack_persist)
    return pack_persist


def apply(name, block, recipe=None, force=False, system_fonts=None):
    """Write pack `name` into both files. `block` is the style-packs.json body, `recipe` the
    pack_recipe/frame_to_pack result carrying ground/ink/palette/treatment/elements/card.

    recipe=None writes a QUICK pack (fonts + accent, no palette of its own) into style-packs.json only.
    `system_fonts` ({key: absolute path}) adds the "SYSTEM:<key>" fonts the pack points at.

    Returns a short report string. Raises PackWriteError before touching anything if it is not safe."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,31}", name or ""):
        raise PackWriteError(f"pack name {name!r} is not a plain name — refusing to write it into code.")

    entries = _render_recipe(recipe) if recipe is not None else {}
    missing, notes = _write(name, block, entries, system_fonts, force)

    if source_copy():
        # The copy the engine ships from: hers stays in _local, out of every bundle. That copy is never
        # updated, so there is nothing to record for an update to put back.
        where = ("into _local/style-packs.json"
                 + (f" and all {len(_DICTS)} palette entries into _local/pack-palettes.json"
                    if recipe is not None else " (a quick pack has no palette entries of its own)"))
        return (f"  ✓ wrote '{name}' {where}\n"
                f"    this is the copy the engine ships from, so your pack stays out of the shipped files\n"
                f"    every existing pack verified unchanged · previous versions kept as .bak"
                + (f"\n    ⚠ check these entries by hand: {missing}" if missing else "")
                + ("\n" + "\n".join(notes) if notes else ""))

    # ---- record it where an update cannot reach -------------------------------------------
    # Both files above are SHIPPED, so the next engine update overwrites them. The sidecar is protected,
    # and the updater replays it afterwards, which is the only reason a pack built today still exists
    # after "update me". The record is read back from what just landed, system fonts included.
    persist = _persist()
    kept = persist.record_live(name) if hasattr(persist, "record_live") else persist.record(name, block, recipe)

    where = (f"into {os.path.relpath(PACKS_JSON, os.path.dirname(HERE))} "
             f"and all {len(_DICTS)} entries in {os.path.relpath(PALETTES, os.path.dirname(HERE))}"
             if recipe is not None else
             f"into {os.path.relpath(PACKS_JSON, os.path.dirname(HERE))} (your fonts and accent on the "
             f"shipped layout; a quick pack has no palette entries of its own)")
    return (f"  ✓ wrote '{name}' {where}\n"
            f"    every existing pack verified unchanged · previous versions kept as .bak\n"
            + ("    saved to user-packs.json, so an engine update keeps it"
               if kept else
               "    ⚠ could NOT save it to user-packs.json — an engine update would lose this pack")
            + (f"\n    ⚠ check these dicts by hand: {missing}" if missing else "")
            + ("\n" + "\n".join(notes) if notes else ""))


def _saved_entries(saved):
    """The pack_palettes.py entries a saved pack carries, as {DICT: source}."""
    palette = saved.get("palette")
    if isinstance(palette, dict) and palette:
        return {d: _render_value(v) for d, v in palette.items()}
    if isinstance(saved.get("recipe"), dict):
        return _render_recipe(saved["recipe"])
    return {}


def restore_pack(name, saved):
    """Put a SAVED pack back after an update (pack_persist.restore). Same writer, no re-recording, and no
    new-name rule: the pack already exists under this name on her machine, so it comes back under it.

    Entries still present in pack_palettes.py (an update that left that file alone) are not written twice.
    A dict the engine no longer has is reported, never guessed at. Returns a list of problems (empty = all
    of it is back)."""
    block = saved.get("block")
    if not isinstance(block, dict):
        raise PackWriteError("its saved copy has no pack block")
    wanted = _saved_entries(saved)
    problems = []
    if wanted:
        have = ({d: _local_palettes().get(d) or {} for d in _DICTS} if source_copy()
                else _dict_entries(open(PALETTES, encoding="utf-8").read()))
        for d in list(wanted):
            if d not in have:
                problems.append(f"the engine no longer has a {d} table, so that part of it was not put back "
                                f"(it is still saved in user-packs.json)")
                wanted.pop(d)
            elif name in have[d]:
                wanted.pop(d)                       # already there: never a second copy
    missing, notes = _write(name, block, wanted, saved.get("system_fonts"), force=True)
    problems += [f"the {d} entry did not land; it is still saved in user-packs.json" for d in missing]
    return problems


def _remove_entries(src, name):
    """pack_palettes.py source with every entry filed under `name` taken out (by AST line spans).

    Refuses (PackWriteError) rather than guess when an entry shares a line with another one."""
    table = _dict_entries(src)
    lines = src.splitlines(keepends=True)
    drop = set()
    for d, keys in table.items():
        if name not in keys:
            continue
        a, col, b, end_col = keys[name]
        if any(not (s[2] < a or s[0] > b) for k, s in keys.items() if k != name):
            raise PackWriteError(f"its {d} entry shares a line with another pack's, so it was left as it is")
        head = lines[a - 1].encode("utf-8")[:col]
        tail = lines[b - 1].encode("utf-8")[end_col:].decode("utf-8", "replace")
        if head.strip() or not re.fullmatch(r"\s*,?\s*(#.*)?\s*", tail):
            raise PackWriteError(f"its {d} entry does not sit on lines of its own, so it was left as it is")
        drop.update(range(a - 1, b))
    return "".join(l for i, l in enumerate(lines) if i not in drop)


def replace_pack(name, saved):
    """Swap the pack called `name` for a saved copy of it (pack_persist, when an older updater put back an
    older copy than the one she had). Its old palette entries are taken out first, so nothing is left
    doubled. Returns a list of problems, like restore_pack."""
    if source_copy():                    # her packs live in _local there; restore_pack's force replaces them
        local = _read_json(_local_palettes_path())
        if any(isinstance(t, dict) and name in t for t in local.values()):
            for t in local.values():
                if isinstance(t, dict):
                    t.pop(name, None)
            _write_json(_local_palettes_path(), local)
        return restore_pack(name, saved)
    src = open(PALETTES, encoding="utf-8").read()
    cleaned = _remove_entries(src, name)
    if cleaned != src:
        compile(cleaned, PALETTES, "exec")
        shutil.copy2(PALETTES, PALETTES + ".bak")
        tmp = PALETTES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
        os.replace(tmp, PALETTES)
    return restore_pack(name, saved)


def remove_pack(name):
    """Take a creator-built pack out of both files (pack_persist.forget). A launch pack is never removed."""
    cfg = _read_packs()
    packs = cfg.get("packs", {})
    if name in packs and isinstance(packs[name], dict) and packs[name].get("in_launch_kit"):
        raise PackWriteError(f"'{name}' is a LAUNCH pack; it is not yours to remove.")
    if source_copy():                    # hers live in _local there; the shipped files are never written
        local = _read_json(_local_packs_path())
        if name in local.get("packs", {}):
            del local["packs"][name]
            _write_json(_local_packs_path(), local)
        pal = _read_json(_local_palettes_path())
        if any(isinstance(t, dict) and name in t for t in pal.values()):
            for t in pal.values():
                if isinstance(t, dict):
                    t.pop(name, None)
            _write_json(_local_palettes_path(), pal)
        return
    src = open(PALETTES, encoding="utf-8").read()
    cleaned = _remove_entries(src, name)
    if name in packs:
        del packs[name]
        shutil.copy2(PACKS_JSON, PACKS_JSON + ".bak")
        tmp = PACKS_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n")
        os.replace(tmp, PACKS_JSON)
    if cleaned != src:
        compile(cleaned, PALETTES, "exec")
        shutil.copy2(PALETTES, PALETTES + ".bak")
        tmp = PALETTES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
        os.replace(tmp, PALETTES)


def _luminance(hexcolor):
    h = str(hexcolor).lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _readability(recipe):
    """A plain warning when the pack's ink will not read on its own ground (WCAG contrast, 3:1 floor for
    large type). The render check would refuse it later anyway; saying so now saves a build."""
    if not recipe:
        return ""
    pal = recipe.get("palette") or {}
    grounds = [pal.get("light"), recipe.get("ground")]
    for role in ("dark", "muted"):                     # the two text colours; both must clear 3:1
        ink = pal.get(role)
        li = _luminance(ink)
        for g in grounds:
            lg = _luminance(g)
            if li is None or lg is None:
                continue
            ratio = (max(li, lg) + 0.05) / (min(li, lg) + 0.05)
            if ratio < 3.0:
                return (f"  ⚠ {role} {ink} on {g} reads at {ratio:.1f}:1, under the 3:1 floor for large type. Text "
                        f"in this colour will be hard to read on that background; pick a deeper shade.")
    return ""


def _set_values(block, recipe, pairs):
    """--set KEY=VALUE, one value at a time: palette/ground/... keys change the designed palette, anything
    else (accent_color, elements.caption.size ...) the pack block. A value that parses as JSON is used as
    JSON (numbers, true/false), anything else as text.

    "elements" names two things: the palette's element list (elements, elements.0.color) and the pack
    block's elements by role (elements.caption.size). A key that names a role goes to the block; routing
    it to the palette list crashed ('list' object has no attribute 'setdefault')."""
    for kv in pairs:
        key, sep, val = kv.partition("=")
        if not sep or not key:
            raise PackWriteError(f"--set wants KEY=VALUE, got {kv!r}")
        parts = key.split(".")
        to_palette = parts[0] in ("ground", "hands_off_accent", "palette", "treatment", "elements", "card")
        if parts[0] == "elements" and len(parts) > 1 and not parts[1].isdigit():
            to_palette = False                    # elements.<role>.<field>: the pack block's own element
        if to_palette:
            if recipe is None:
                raise PackWriteError(f"{key}: this pack has no designed palette to change")
            target = recipe
        else:
            target = block
            parts = parts[1:] if parts[0] == "block" else parts
        for p in parts[:-1]:
            if isinstance(target, list):
                if not p.isdigit() or int(p) >= len(target):
                    raise PackWriteError(f"{key}: {p!r} is not a position in that list (0 to {len(target) - 1})")
                target = target[int(p)]
            else:
                target = target.setdefault(p, {})
        if isinstance(target, list):
            last = parts[-1]
            if not last.isdigit() or int(last) >= len(target):
                raise PackWriteError(f"{key}: {last!r} is not a position in that list (0 to {len(target) - 1})")
            parts[-1] = int(last)
        try:
            target[parts[-1]] = json.loads(val)
        except ValueError:
            target[parts[-1]] = val


def main(argv=None):
    """Save a pack through the recorded path: a QUICK pack (the style-pack skill, --block), or a new pack of
    hers started from an existing one (--from Butter --set palette.dark=#C2527A)."""
    import argparse
    for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Save a style pack you built into the engine, and keep a "
                                             "protected copy so an update can never delete it.")
    ap.add_argument("--name", required=True, help='the pack name she chose, e.g. "My Pack"')
    ap.add_argument("--block",
                    help="the pack's style-packs.json block as a JSON file (or - to read it from stdin)")
    ap.add_argument("--from", dest="from_pack",
                    help="start from an existing pack (e.g. Butter): its fonts, settings and palette")
    ap.add_argument("--recipe", help="optional JSON file with the designed palette (pack_recipe output)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="change one value on the way, e.g. palette.dark=#E8A0B4 or accent_color=#F4C2C2")
    ap.add_argument("--system-font", action="append", default=[], metavar='"Font Name=/absolute/path"',
                    help='a system font a role uses as "SYSTEM:<Font Name>" (repeatable)')
    ap.add_argument("--force", action="store_true", help="replace her pack of the same name")
    a = ap.parse_args(argv)
    block, recipe = None, None
    if a.from_pack:
        # "Keep Butter but make the blue pink" is a NEW pack of hers, never an edit to Butter itself: a
        # shipped pack is reset by every update, and hers is kept.
        src = _read_packs().get("packs", {}).get(a.from_pack)
        if source_copy():                        # a pack of hers in _local can be the starting point too
            src = _read_json(_local_packs_path()).get("packs", {}).get(a.from_pack, src)
        if not isinstance(src, dict):
            print(f"  ⛔ not written: there is no pack called {a.from_pack!r} to start from")
            return 1
        block = json.loads(json.dumps(src), object_pairs_hook=collections.OrderedDict)
        with open(PALETTES, encoding="utf-8") as fh:
            ent = _persist().palette_entries_in(fh.read(), a.from_pack) or {}
        local_pal = _local_palettes()
        if any(isinstance(local_pal.get(d), dict) and a.from_pack in local_pal[d] for d in _DICTS):
            keys = _persist()._RECIPE_KEYS          # table name -> its key in a recipe
            ent = {keys[d]: local_pal[d][a.from_pack] for d in _DICTS
                   if isinstance(local_pal.get(d), dict) and a.from_pack in local_pal[d]}
        recipe = ent if len(ent) == len(_DICTS) else None
    try:
        if a.block:
            block = json.load(sys.stdin if a.block == "-" else open(a.block, encoding="utf-8"),
                              object_pairs_hook=collections.OrderedDict)
        if a.recipe:
            with open(a.recipe, encoding="utf-8") as fh:
                recipe = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"  ⛔ not written: could not read the pack block ({e})")
        return 1
    if block is None:
        print("  ⛔ not written: give --block (a pack body) or --from (a pack to start from)")
        return 1
    if not isinstance(block, dict) or not isinstance(block.get("elements"), dict):
        print("  ⛔ not written: that is not a pack block (it needs its \"elements\").")
        return 1
    block["in_launch_kit"] = False                 # hers, never a launch pack, whatever it was cloned from
    fonts = {}
    for pair in a.system_font:
        if "=" not in pair:
            print(f'  ⛔ not written: --system-font needs "Font Name=/absolute/path", got {pair!r}')
            return 1
        k, v = pair.split("=", 1)
        fonts[k.strip()] = os.path.expanduser(v.strip())
    try:
        _set_values(block, recipe, a.set)
        print(apply(a.name, block, recipe, force=a.force, system_fonts=fonts))
    except PackWriteError as e:
        print(f"  ⛔ not written: {e}")
        return 1
    warn = _readability(recipe)
    if warn:
        print(warn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
