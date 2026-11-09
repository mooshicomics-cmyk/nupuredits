#!/usr/bin/env python3
"""settings_persist.py — keep the creator's own settings alive across an engine update.

Three things a creator sets up live INSIDE files the engine ships, and an update replaces those files
whole (measured on a real v1.0.93 -> v1.0.94 update: all three came back as the shipped defaults):

  * her permission mode, any other Claude Code setting she added, and any hook of her own, in
    `.claude/settings.json` (product/PERMISSIONS-SETUP.md tells her to put her mode there, and the engine's own
    hooks live in that file too)
  * her hook defaults: Part B of brand-kit.md writes DEFAULT_HOOK_TEXT / HOOK_END_WORDS into
    `presets/clean-captions/build.py`
  * her headline font: Part B swaps it into `presets/type-and-look.md` in place of the bundled Inter

Same shape of fix as pack_persist (her style packs): a protected record, `_local/kept-settings.json`,
written from the live files just before an update and replayed into the fresh files just after. Only her
part is ever written back: the engine's own hooks, and every line of a refreshed file she never touched,
arrive exactly as shipped.

  harvest(base=None)  read her values out of a tree (the live one, or an update backup's overwritten/ copy)
  restore()           put them back where the freshly shipped files have the default
  recover()           settings an EARLIER update replaced, found in the update backups. Report-only unless
                      asked, because a permission mode she has since turned off must never switch itself
                      back on:  python3 product/settings_persist.py recover [--apply]

Stdlib only. harvest/restore never raise: an unreadable file is reported, not fatal.
"""
import ast, datetime, hashlib, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIDECAR = os.path.join(ROOT, "_local", "kept-settings.json")
BACKUPS = os.path.join(ROOT, "_update-backups")

CLAUDE_SETTINGS = ".claude/settings.json"
# What the engine itself puts in .claude/settings.json; everything else there is hers. If the engine ever
# ships another key here, list it too, or an old engine value would be carried forward as if it were hers.
# "hooks" is shared, like "permissions" below: the engine's hooks are its own, and a hook she added is hers.
ENGINE_KEYS = ("$schema",)
# The hook scripts the engine runs from .claude/settings.json. A hook whose command runs one of these is the
# engine's (in whatever form the command took in any version: `bash .claude/hooks/x.sh`, or from
# ${CLAUDE_PROJECT_DIR}); any other hook in the file is hers, and an update keeps it. Keep every script the engine
# has EVER run as a hook here, even after it stops shipping one, or an old install's copy would come back as hers.
# check-ship holds the shipped settings.json to this list.
ENGINE_HOOK_SCRIPTS = ("machine-fingerprint.sh", "onboarding-nudge.sh", "update-check.sh", "protect-capcut-drafts.sh",
                       "chime.sh", "editor-says.sh")
_ENGINE_HOOK_RE = re.compile(r"(?:^|[\s\"'/\\])(?:%s)(?=$|[\s\"';&|)])"
                             % "|".join(re.escape(s) for s in ENGINE_HOOK_SCRIPTS))
# Hook scripts an earlier version ran under a name this version no longer uses, kept as sha256[:20] of the script's
# file name so the old name itself never ships. A v1 folder brought over still names one of them in its settings,
# and that hook is the engine's, never hers (it would run a script this version does not have).
_RETIRED_HOOK_KEYS = frozenset({"fd2a32e06d6f327c5b5a"})
_HOOK_SCRIPT_RE = re.compile(r"[\w.-]+\.sh\b")
# The permission rules the engine itself ships, per list ("permissions" is shared: her defaultMode and any rule
# she adds are hers, these entries are the engine's). Left out of her record, so an update never carries one
# forward as hers and a later version can drop one. Keep every rule the engine has EVER shipped here, even after
# it stops shipping it, or an old install would bring it back.
# The permission rules the engine ships (v2.2.0 added the private-file deny rules and a small allow list).
# Keep every rule it has EVER shipped here, so an old copy never comes back as hers.
ENGINE_PERMISSIONS = {
    "deny": (
        "Skill(anthropic-skills:setup-claude)",
        "Read(~/.ssh/**)",
        "Edit(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Edit(~/.aws/**)",
        "Read(~/.gnupg/**)",
        "Edit(~/.gnupg/**)",
        "Read(~/.config/gcloud/**)",
        "Edit(~/.config/gcloud/**)",
        "Read(~/Library/Keychains/**)",
        "Edit(~/Library/Keychains/**)",
        "Read(~/Library/Application Support/Google/Chrome/**)",
        "Edit(~/Library/Application Support/Google/Chrome/**)",
        "Read(~/Library/Safari/**)",
        "Edit(~/Library/Safari/**)",
        "Read(~/Library/Application Support/Firefox/**)",
        "Edit(~/Library/Application Support/Firefox/**)",
        "Read(~/AppData/Local/Google/Chrome/User Data/**)",
        "Edit(~/AppData/Local/Google/Chrome/User Data/**)",
        "Read(~/AppData/Roaming/Mozilla/Firefox/**)",
        "Edit(~/AppData/Roaming/Mozilla/Firefox/**)",
        "Bash(rm -rf /)",
        "Bash(rm -rf ~)",
        "Bash(rm -rf ~/)",
        "Bash(rm -rf $HOME)",
        "Bash(rm -rf $HOME/)",
        # v2.2.15 (skill guides from HyperFrames release 0.8.158): `usage` reads her Claude sign-in, `feedback` sends a run off her computer.
        "Bash(npx hyperframes usage*)",
        "Bash(npx hyperframes@* usage*)",
        "Bash(npx --yes hyperframes usage*)",
        "Bash(npx --yes hyperframes@* usage*)",
        "Bash(npx.cmd hyperframes usage*)",
        "Bash(npx.cmd hyperframes@* usage*)",
        "Bash(npx hyperframes feedback*)",
        "Bash(npx hyperframes@* feedback*)",
        "Bash(npx --yes hyperframes feedback*)",
        "Bash(npx --yes hyperframes@* feedback*)",
        "Bash(npx.cmd hyperframes feedback*)",
        "Bash(npx.cmd hyperframes@* feedback*)",
        # v2.3.19 (HyperFrames release 0.8.230): `billing` reads her HyperFrames sign-in; these two send her photos, voice or footage to HeyGen and spend credits
        "Bash(npx hyperframes billing*)",
        "Bash(npx hyperframes@* billing*)",
        "Bash(npx --yes hyperframes billing*)",
        "Bash(npx --yes hyperframes@* billing*)",
        "Bash(npx.cmd hyperframes billing*)",
        "Bash(npx.cmd hyperframes@* billing*)",
        "Bash(npx hyperframes media-use generate*)",
        "Bash(npx hyperframes@* media-use generate*)",
        "Bash(npx --yes hyperframes media-use generate*)",
        "Bash(npx --yes hyperframes@* media-use generate*)",
        "Bash(npx.cmd hyperframes media-use generate*)",
        "Bash(npx.cmd hyperframes@* media-use generate*)",
        "Bash(npx hyperframes transcribe*--engine*heygen*)",
        "Bash(npx hyperframes@* transcribe*--engine*heygen*)",
        "Bash(npx --yes hyperframes transcribe*--engine*heygen*)",
        "Bash(npx --yes hyperframes@* transcribe*--engine*heygen*)",
        "Bash(npx.cmd hyperframes transcribe*--engine*heygen*)",
        "Bash(npx.cmd hyperframes@* transcribe*--engine*heygen*)",
        "Bash(npx hyperframes audio*--read*)",
        "Bash(npx hyperframes@* audio*--read*)",
        "Bash(npx --yes hyperframes audio*--read*)",
        "Bash(npx --yes hyperframes@* audio*--read*)",
        "Bash(npx.cmd hyperframes audio*--read*)",
        "Bash(npx.cmd hyperframes@* audio*--read*)",
        "Bash(npx hyperframes reverse*)",
        "Bash(npx hyperframes@* reverse*)",
        "Bash(npx --yes hyperframes reverse*)",
        "Bash(npx --yes hyperframes@* reverse*)",
        "Bash(npx.cmd hyperframes reverse*)",
        "Bash(npx.cmd hyperframes@* reverse*)",
    ),
    "allow": (
        "Bash(ffmpeg *)",
        "Bash(ffprobe *)",
        "Bash(./check-setup.sh*)",
        "Bash(bash scripts/*)",
        "Bash(python3 scripts/*)",
    ),
}
# Environment values the engine ships in settings.json (tracking off). Hers stay hers.
# HYPERFRAMES_SKIP_SKILLS (v2.2.16): HyperFrames' `init` (from 0.8.158) otherwise checks GitHub and installs its skills into
# the computer's global Claude folder; the engine carries its own pinned copies.
ENGINE_ENV = {"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_SKIP_SKILLS": "1"}

# What Part B of brand-kit.md writes into a shipped preset: (file, variable). A blank value = she has none.
CONSTANTS = (("presets/clean-captions/build.py", "DEFAULT_HOOK_TEXT"),
             ("presets/clean-captions/build.py", "HOOK_END_WORDS"),
             ("presets/clean-captions/build.py", "HOOK_COPY"),
             ("presets/clean-captions/build.py", "HOOK_CUE_WORDS"))
LABELS = {"DEFAULT_HOOK_TEXT": "your default hook", "HOOK_END_WORDS": "the word that ends your hook card",
          "HOOK_COPY": "your hook copy", "HOOK_CUE_WORDS": "the words that close your hook"}
FONT_DOC = "presets/type-and-look.md"
_FILES_RE = re.compile(r"assets/fonts/([^/`{}\n]+)-\{Black,Bold,Regular\}")
_TYPE_RE = re.compile(r"^#{2,4}\s*Type\s*[—–:-]+\s*([^,\n]+)", re.M)

_DOC = ("Your own settings that live inside files the engine ships (your permission mode, the hook "
        "defaults and headline font your brand kit set). An update refreshes those files; this protected "
        "copy is how your values go back into them. Written by the updater, no need to edit.")

SHIPPED_FONT = "Inter"      # the bundled headline font Part B swaps out; change it here if the engine's ever does


def _path(rel, base=None):
    return os.path.join(base or ROOT, *rel.split("/"))


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def load():
    try:
        with open(SIDECAR, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(rec):
    rec = dict(rec)
    rec["_doc"] = _DOC
    os.makedirs(os.path.dirname(SIDECAR), exist_ok=True)
    _write_text(SIDECAR, json.dumps(rec, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- her Claude Code settings

def is_engine_hook(entry):
    """True when one hook entry ({"type": "command", "command": ...}) runs one of the engine's own hook scripts."""
    if not (isinstance(entry, dict) and isinstance(entry.get("command"), str)):
        return False
    cmd = entry["command"]
    return bool(_ENGINE_HOOK_RE.search(cmd)) or any(
        hashlib.sha256(name.encode("utf-8")).hexdigest()[:20] in _RETIRED_HOOK_KEYS for name in _HOOK_SCRIPT_RE.findall(cmd))


def _split_hooks(hooks):
    """(the engine's, hers, odd) of a settings.json "hooks" object. The first two keep its shape
    ({event: [group, ...]}, a group being {"matcher": ..., "hooks": [entry, ...]}); a group holding both keeps
    its matcher on each side. `odd` lists what is not in the shape Claude Code reads (an event that is not a list,
    a group without a hooks list, an entry that is not an object): never written into a new file, where one
    unreadable entry could stop Claude Code reading the whole file, engine hooks included. harvest() reports it,
    and the update backup keeps her file exactly as it was."""
    if not isinstance(hooks, dict):
        return {}, {}, ([hooks] if hooks not in (None, {}) else [])
    eng, hers, odd = {}, {}, []
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            odd.append({event: groups})
            continue
        for g in groups:
            if not isinstance(g, dict) or not isinstance(g.get("hooks"), list):
                odd.append({event: g})
                continue
            rest = {k: v for k, v in g.items() if k != "hooks"}
            ours = [h for h in g["hooks"] if is_engine_hook(h)]
            mine = [h for h in g["hooks"] if isinstance(h, dict) and not is_engine_hook(h)]
            odd += [{event: h} for h in g["hooks"] if not isinstance(h, dict)]
            if ours:
                eng.setdefault(event, []).append(dict(rest, hooks=ours))
            if mine:
                hers.setdefault(event, []).append(dict(rest, hooks=mine))
    return eng, hers, odd


def engine_part(settings):
    """The engine's own part of a parsed .claude/settings.json: its keys, its hooks, the permission rules it
    ships. In the file's own key order, so a copy the engine shipped comes back byte for byte when dumped."""
    out = {}
    for k, v in (settings or {}).items():
        if k in ENGINE_KEYS:
            out[k] = v
        elif k == "hooks":
            eng, _hers, _odd = _split_hooks(v)
            if eng:
                out[k] = eng
        elif k == "env" and isinstance(v, dict):
            eng = {ek: ev for ek, ev in v.items() if ek in ENGINE_ENV}
            if eng:
                out[k] = eng
        elif k == "permissions" and isinstance(v, dict):
            eng = {pk: [x for x in pv if x in ENGINE_PERMISSIONS[pk]] for pk, pv in v.items()
                   if isinstance(pv, list) and ENGINE_PERMISSIONS.get(pk)}
            eng = {pk: pv for pk, pv in eng.items() if pv}
            if eng:
                out[k] = eng
    return out


def _theirs(settings):
    """Her part of .claude/settings.json: everything the engine does not put there itself (its own keys, its
    hooks, and the permission rules it ships). Hooks she added are hers."""
    out = {}
    for k, v in settings.items():
        if k in ENGINE_KEYS:
            continue
        if k == "hooks":
            _eng, hers, _odd = _split_hooks(v)
            if hers:
                out[k] = hers
            continue
        out[k] = v
    env = out.get("env")
    if isinstance(env, dict):
        env = {ek: ev for ek, ev in env.items() if ek not in ENGINE_ENV}
        if env:
            out["env"] = env
        else:
            del out["env"]
    perms = out.get("permissions")
    if isinstance(perms, dict):
        mine = {}
        for k, v in perms.items():
            if isinstance(v, list) and ENGINE_PERMISSIONS.get(k):
                v = [x for x in v if x not in ENGINE_PERMISSIONS[k]]
                if not v:
                    continue
            mine[k] = v
        if mine:
            out["permissions"] = mine
        else:
            del out["permissions"]
    return out


def _merge_into(cur, mine):
    """`cur` with `mine` laid over it: her scalars win, dicts merge, lists keep every entry of both."""
    out = dict(cur)
    for k, v in mine.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_into(out[k], v)
        elif isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + [x for x in v if x not in out[k]]
        else:
            out[k] = v
    return out


def _merge_hooks(cur, mine):
    """The engine's hooks (`cur`) with each hook of hers added once: a hook already in that event, in any group,
    is not added again; the rest go in as her own group, under her matcher."""
    out = {k: list(v) if isinstance(v, list) else v for k, v in (cur or {}).items()}
    for event, groups in (mine or {}).items():
        if not isinstance(groups, list) or not isinstance(out.get(event, []), list):
            continue                                   # not a shape Claude Code reads: never written (see _split_hooks)
        have = out.setdefault(event, [])
        present = [h for g in have if isinstance(g, dict) for h in (g.get("hooks") or [])]
        for g in groups:
            if not isinstance(g, dict) or not isinstance(g.get("hooks"), list):
                continue
            new = [h for h in g["hooks"] if isinstance(h, dict) and h not in present]
            if new:
                have.append(dict({k: v for k, v in g.items() if k != "hooks"}, hooks=new))
                present += new
    return out


def merge_settings(cur, mine):
    """.claude/settings.json `cur` with her part `mine` laid over it (_merge_into), her hooks added once each."""
    hooks = mine.get("hooks") if isinstance(mine, dict) else None
    out = _merge_into(cur, {k: v for k, v in (mine or {}).items() if k != "hooks"})
    if hooks:
        out["hooks"] = _merge_hooks(out.get("hooks") if isinstance(out.get("hooks"), dict) else {}, hooks)
    return out


def _settings_label(mine):
    """What of hers a settings record holds, in her words: "your Claude settings (permission mode, your own hooks)"."""
    bits = []
    if isinstance(mine.get("permissions"), dict):
        bits.append("permission mode" if "defaultMode" in mine["permissions"] else "permission rules")
    if mine.get("hooks"):
        bits.append("your own hooks")
    if any(k not in ("permissions", "hooks") for k in mine):
        bits.append("your other settings")
    return "your Claude settings" + (f" ({', '.join(bits)})" if bits else "")


def _settings(base=None):
    """(parsed settings.json or None, whether the file exists)."""
    text = _read(_path(CLAUDE_SETTINGS, base))
    if text is None:
        return None, False
    try:
        data = json.loads(text)
    except ValueError:
        return None, True
    return (data if isinstance(data, dict) else None), True


# ---------------------------------------------------------------- a Part B constant in a preset

def _constant(src, var):
    """(value, its source text, (line, col, end_line, end_col)) of a top-level `var = <literal>`, or None."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == var for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                return None
            text = ast.get_source_segment(src, node.value)
            return value, text, (node.value.lineno, node.value.col_offset,
                                 node.value.end_lineno, node.value.end_col_offset)
    return None


def _blank(v):
    return v in ("", (), [], None)


# ---------------------------------------------------------------- her headline font

def _font(text):
    """{"stem", "name"} of the headline font a type-and-look.md names, or None when it names none."""
    m = _FILES_RE.search(text or "")
    if not m:
        return None
    t = _TYPE_RE.search(text)
    return {"stem": m.group(1), "name": (t.group(1).strip() if t else m.group(1))}


# ---------------------------------------------------------------- record / replay

def harvest(base=None):
    """Record her values from a tree: the live files (just before an update), or an update backup's
    overwritten/ copy (the files as they were just before the update that made it). A value she has set
    back to blank clears its record; a file the tree does not hold leaves the record as it is.

    Returns (kept, problems): labels of what is recorded, and (what, why) pairs she should see."""
    rec = load()
    kept, problems = [], []

    st, exists = _settings(base)
    if exists and st is None:
        problems.append(("your Claude settings", ".claude/settings.json could not be read, so your "
                                                 "permission mode was not saved (the update backup keeps "
                                                 "the file as it was)"))
    elif st is not None:
        mine = _theirs(st)
        if mine:
            rec["claude_settings"] = mine
            kept.append(_settings_label(mine))
        else:
            rec.pop("claude_settings", None)
        if "hooks" in st and _split_hooks(st.get("hooks"))[2]:
            problems.append(("a hook in your Claude settings", "is not written the way Claude Code reads hooks, so "
                                                               "it is not carried into the new file (the update "
                                                               "backup keeps your file exactly as it was)"))

    consts = dict(rec.get("constants") or {})
    for rel, var in CONSTANTS:
        src = _read(_path(rel, base))
        got = _constant(src, var) if src is not None else None
        if got is None:
            continue
        value, text, _span = got
        key = f"{rel}::{var}"
        if _blank(value):
            consts.pop(key, None)
        else:
            consts[key] = {"value": list(value) if isinstance(value, tuple) else value, "source": text}
            kept.append(LABELS.get(var, var))
    if consts:
        rec["constants"] = consts
    else:
        rec.pop("constants", None)

    doc = _read(_path(FONT_DOC, base))
    font = _font(doc) if doc is not None else None
    if font and font["stem"] == SHIPPED_FONT:
        rec.pop("headline_font", None)
    elif font:
        rec["headline_font"] = font
        kept.append(f"your headline font ({font['name']})")

    rec["saved_at"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    try:
        _save(rec)
    except OSError as exc:
        problems.append(("your settings", f"could not be saved to _local/kept-settings.json ({exc})"))
    return kept, problems


def restore():
    """Put her recorded values back into files an update has just replaced (right after it — never at any
    other time, so a setting she changes by hand is never "restored" over). Returns (restored, problems)."""
    rec = load()
    restored, problems = [], []

    mine = rec.get("claude_settings")
    mine = _theirs(mine) if isinstance(mine, dict) else mine   # a record saved before a rule was the engine's
    if isinstance(mine, dict) and mine:
        cur, exists = _settings()
        if exists and cur is None:
            problems.append(("your Claude settings", ".claude/settings.json could not be read, so your "
                                                     "permission mode was not put back; it is kept in "
                                                     "_local/kept-settings.json"))
        else:
            merged = merge_settings(cur or {}, mine)
            if merged != cur:
                try:
                    os.makedirs(os.path.dirname(_path(CLAUDE_SETTINGS)), exist_ok=True)
                    _write_text(_path(CLAUDE_SETTINGS), json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
                    restored.append(_settings_label(mine))
                except OSError as exc:
                    problems.append(("your Claude settings", f"could not be written ({exc})"))

    by_file = {}
    for key, saved in (rec.get("constants") or {}).items():
        rel, _, var = key.partition("::")
        by_file.setdefault(rel, []).append((var, saved))
    for rel, items in by_file.items():
        src = _read(_path(rel))
        if src is None:
            problems.append((rel, "is not there any more; your values are kept in _local/kept-settings.json"))
            continue
        new = src
        for var, saved in items:
            text = (saved or {}).get("source") or ""
            try:
                want = ast.literal_eval(text)
            except (ValueError, TypeError, SyntaxError):
                problems.append((LABELS.get(var, var), "its saved value could not be read back"))
                continue
            got = _constant(new, var)
            if got is None:
                problems.append((LABELS.get(var, var), f"{rel} no longer sets it; yours ({text}) is kept in "
                                      f"_local/kept-settings.json. Say \"update my homebase\" to put it back."))
                continue
            value, _text, (l1, c1, l2, c2) = got
            if value == want:
                continue
            same_kind = isinstance(value, type(want)) or (isinstance(value, (tuple, list)) and
                                                          isinstance(want, (tuple, list)))
            if not same_kind or l1 != l2 or "\n" in text:
                problems.append((LABELS.get(var, var), f"{rel} changed how it is set, so yours ({text}) was not written in; it "
                                      f"is kept in _local/kept-settings.json"))
                continue
            lines = new.splitlines(keepends=True)
            raw = lines[l1 - 1].encode("utf-8")
            lines[l1 - 1] = (raw[:c1] + text.encode("utf-8") + raw[c2:]).decode("utf-8")
            new = "".join(lines)
        if new != src:
            try:
                compile(new, rel, "exec")
                _write_text(_path(rel), new)
                restored.append("your hook defaults")
            except (SyntaxError, OSError) as exc:
                problems.append((rel, f"your values could not be written back ({exc}); they are kept in "
                                      f"_local/kept-settings.json"))

    font = rec.get("headline_font")
    if isinstance(font, dict) and font.get("stem"):
        doc = _read(_path(FONT_DOC))
        cur = _font(doc) if doc is not None else None
        if doc is None:
            pass
        elif cur is None:
            problems.append(("your headline font", f"{FONT_DOC} no longer says where it goes; yours "
                                                   f"({font['name']}) is kept in _local/kept-settings.json. "
                                                   f"Say \"update my homebase\" to put it back."))
        elif cur["stem"] != font["stem"]:
            new = doc.replace(f"{cur['stem']}-{{Black,Bold,Regular}}", f"{font['stem']}-{{Black,Bold,Regular}}")
            new = re.sub(rf"\b{re.escape(cur['name'])}\b", lambda _m: font["name"], new)
            try:
                _write_text(_path(FONT_DOC), new)
                restored.append(f"your headline font ({font['name']})")
            except OSError as exc:
                problems.append(("your headline font", f"could not be written ({exc})"))
    return restored, problems


# ---------------------------------------------------------------- earlier updates

def _backups():
    """(folder, overwritten/ tree) of every update backup, newest first."""
    try:
        names = os.listdir(BACKUPS)
    except OSError:
        return []
    found = []
    for n in names:
        ow = os.path.join(BACKUPS, n, "overwritten")
        if os.path.isdir(ow):
            m = re.search(r"(\d{8}-\d{6})", n)
            found.append(((m.group(1) if m else ""), n, ow))
    found.sort(reverse=True)
    return [(n, ow) for _s, n, ow in found]


def recover(apply=False):
    """Values an EARLIER update replaced (before this protection shipped) that the live files no longer
    carry, from the newest update backup that still holds each. Returns [(what, value, backup)].

    Nothing is written unless apply=True: a permission mode she turned off since must never switch itself
    back on, so this is a report she (or support) confirms first."""
    found, taken = [], set()
    live_st, _ = _settings()
    live_mine = _theirs(live_st or {})
    for folder, ow in _backups():
        st, _exists = _settings(ow)
        mine = _theirs(st or {})
        if mine and "claude" not in taken and merge_settings(live_mine, mine) != live_mine:
            found.append(("your Claude settings", mine, folder))
            taken.add("claude")
        for rel, var in CONSTANTS:
            if var in taken:
                continue
            src = _read(_path(rel, ow))
            got = _constant(src, var) if src is not None else None
            live = _read(_path(rel))
            now = _constant(live, var) if live is not None else None
            if got and not _blank(got[0]) and now and _blank(now[0]):
                found.append((LABELS.get(var, var), got[1], folder))
                taken.add(var)
        if "font" not in taken:
            doc = _read(_path(FONT_DOC, ow))
            f = _font(doc) if doc else None
            live_f = _font(_read(_path(FONT_DOC)) or "")
            if f and f["stem"] != SHIPPED_FONT and live_f and live_f["stem"] == SHIPPED_FONT:
                found.append(("your headline font", f["name"], folder))
                taken.add("font")
    if apply and found:
        rec = load()
        for what, value, folder in found:
            ow = os.path.join(BACKUPS, folder, "overwritten")
            if what == "your Claude settings":
                rec["claude_settings"] = merge_settings(rec.get("claude_settings") or {}, value)
            elif what == "your headline font":
                rec["headline_font"] = _font(_read(_path(FONT_DOC, ow)))
            else:
                var = next(v for v in LABELS if LABELS[v] == what) if what in LABELS.values() else what
                rel = next(r for r, v in CONSTANTS if v == var)
                rec.setdefault("constants", {})[f"{rel}::{var}"] = {"source": value}
        _save(rec)
        restore()
    return found


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "harvest":
        got, bad = harvest(sys.argv[2] if len(sys.argv) > 2 else None)
        print(f"saved: {', '.join(got) or 'nothing of yours in those files'}")
        for what, why in bad:
            print(f"  ! {what}: {why}")
    elif cmd == "restore":
        got, bad = restore()
        print(f"put back: {', '.join(got) or 'nothing needed'}")
        for what, why in bad:
            print(f"  ! {what}: {why}")
    elif cmd == "recover":
        do = "--apply" in sys.argv
        found = recover(apply=do)
        if not found:
            print("Nothing of yours is missing from the settings an update refreshes.")
        for what, value, folder in found:
            shown = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            print(f"  {'put back' if do else 'found'} {what}: {shown}   (from the update backup {folder})")
        if found and not do:
            print("Say the word and I will put these back: python3 product/settings_persist.py recover --apply")
    else:
        print(json.dumps({k: v for k, v in load().items() if k != "_doc"}, indent=2, ensure_ascii=False))
