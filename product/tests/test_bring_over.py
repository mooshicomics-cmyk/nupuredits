#!/usr/bin/env python3
"""test_bring_over.py — "bring over my old engine" brings everything that is hers into the new version, once.

The final version ships as a fresh download, so a beta tester's work (brand kit, profile, the packs she built,
what she taught it, her words, settings, keys and reels) stays in her OLD folder until scripts/bring-over.py
copies it across. This builds that situation for real, in temp folders only: a FULLY customized v1 engine
(customized the way test_update_keeps_buyer_data.py customizes one, through the engine's own tools), with a
quick pack that survives ONLY in an old update backup, a pack she deleted for good, one of the engine's own
packs changed in place, a hand edit to a shipped engine file and one to a file the new version renamed; and a
fresh v2 engine whose own files moved on (a new hook, a new default word, new instructions). Then:

The old engine also took the update that carries the originals archive (as a v1.0.95 install has), saved its
CLAUDE.md with Windows line endings, and already keeps a record of an earlier update's changes.

  1. the preview writes NOTHING (both trees hashed before and after) and names every item
  2. --apply: every item lands where it belongs; the engine's own files are unchanged except the documented
     merges; the backup-only pack is back and recorded, the deleted-for-good one is not; the two hand edits are
     saved and listed under "Needs a hand", the renamed one under its NEW path
  3. --apply again changes nothing, and says so
  4. it refuses, in plain words, a folder that is not an engine, this same folder, and a folder already on v2
  5. seller side, where the rename table lives: no v1 name of a renamed file appears in the files that carry
     this feature, and every file of the newest real v1 release reads as the engine's own

The renamed files here use this test's own made-up v1 names, so the test itself carries no old name either.

Run: python3 product/tests/test_bring_over.py        (Windows: python)
"""
import ast
import copy
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(ROOT, "product"))
import keep_changes as KC          # noqa: E402  (their path constants: a later rename moves the test with it)
import pack_persist as PP          # noqa: E402
import settings_persist as SP      # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BO = _load("bring_over", os.path.join(ROOT, "scripts", "bring-over.py"))     # its own fingerprint functions
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"\n         {str(detail)[:900]}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "REELS_ENGINE_SKIP_BROWSER_ENSURE": "1"}


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


PACKS, PALETTES, SIDECAR, USER_STYLE = rel(PP.PACKS_JSON), rel(PP.PALETTES), rel(PP.SIDECAR), rel(PP.USER_STYLE)
HOOK_FILE, FONT_DOC, SETTINGS = SP.CONSTANTS[0][0], SP.FONT_DOC, SP.CLAUDE_SETTINGS
WORDS = "presets/caption-corrections.json"
EFFECTS, FONT_MAP, SFX = BO.USER_EFFECTS_REL, BO.FONT_OVERRIDES_REL, BO.SFX_REL

# This test's own made-up v1 names for three files the new version keeps at another path.
OLD_HOOK_FILE, OLD_FONT_DOC = "presets/v1-captions/build.py", "presets/v1-type-notes.md"
OLD_TOOL, NEW_TOOL = "workflows/v1-framing-tool.py", "workflows/v2-framing-tool.py"

ENGINE = ["scripts/bring-over.py", "scripts/merge-claude-md.py", "scripts/apply-update.py",
          "product/pack_persist.py", "product/pack_write.py", "product/settings_persist.py",
          "product/keep_changes.py", "product/pack_recipe.py", "product/stylepack.py", "product/learned.py",
          "product/text_effects.py", PACKS, PALETTES, USER_STYLE, WORDS, HOOK_FILE, FONT_DOC, SETTINGS,
          "assets/logos/README.md", "inbox/README.md", ".env.example"]
ENGINE_DOC = ("# CLAUDE.md\n\n## Brand Kit\n\n### Applied - nothing yet (fresh install)\n\nNo creator yet.\n\n"
              "**⚠️ ASK THE REGISTER AT THE GRAPHICS STEP**\n\n**🎨 LOOK IS NOT SET YET.** Starter defaults.\n\n"
              "## Rules\n- engine rule {v}\n")
HER_PROFILE = "### Applied — Jane Rivera / Sourdough Sundays\n\nCalm and exact. Gut check: hands in the dough?\n\n"
HER_LOOK = "**🎨 LOOK IS SET: Sunday Best.** Her own pack, accent #C2410C."
HER_LINE = "- Always keep the starter jar in frame."
BLANK_KIT = "# Brand kit\n- Headline font: `{{a font name}}`\n"
BLANK_KIT_V1 = "# Brand kit\n- Headline font: `<<FILL_ME>>`\n"     # an older copy's blank field
HER_KIT = "# Brand kit\n- Headline font: `Recoleta`\n- Hook: `okay so here is the thing`\n"
TOOL_V1, TOOL_V2 = "def frame():\n    return 50\n", "def frame():\n    return 50  # the v2 build\n"
HER_TOOL = "def frame():\n    return 62  # she likes more headroom\n"


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(data, bytes):
        with open(path, "wb") as fh:
            fh.write(data)
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False))


def rd(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def rb(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def rjs(path):
    text = rd(path)
    try:
        return json.loads(text) if text is not None else None
    except ValueError:
        return None


def sh(cwd, *args, env=None):
    r = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=env or ENV,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def tree(dst):
    """Every file under a folder, with its content hash: any write at all shows up here."""
    out = {}
    for d, _dirs, files in os.walk(dst):
        for fn in files:
            p = os.path.join(d, fn)
            out[os.path.relpath(p, dst).replace(os.sep, "/")] = hashlib.sha256(rb(p)).hexdigest()
    return out


def const(path, var):
    for node in ast.parse(rd(path) or "").body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == var for t in node.targets):
            return ast.literal_eval(node.value)


def palette(dst, name):
    out = {}
    for node in ast.parse(rd(os.path.join(dst, PALETTES)) or "").body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == name:
                    out[node.targets[0].id] = ast.literal_eval(v)
    return out


def install(dst, version, v1):
    """An engine as it arrives: the shipped files, a blank brand kit, the engine's own instructions."""
    for r in ENGINE:
        if v1 and r == "scripts/bring-over.py":
            continue
        target = {HOOK_FILE: OLD_HOOK_FILE, FONT_DOC: OLD_FONT_DOC}.get(r, r) if v1 else r
        os.makedirs(os.path.dirname(os.path.join(dst, target)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, r), os.path.join(dst, target))
    write(os.path.join(dst, "product.json"), {"engine": "ai-edit-engine", "version": version})
    doc = ENGINE_DOC.format(v="v1" if v1 else "v2")
    write(os.path.join(dst, "CLAUDE.md"), doc)
    write(os.path.join(dst, "product", "templates", "CLAUDE.engine.md"), doc)
    write(os.path.join(dst, "brand-kit.md"), BLANK_KIT_V1 if v1 else BLANK_KIT)
    write(os.path.join(dst, OLD_TOOL if v1 else NEW_TOOL), TOOL_V1 if v1 else TOOL_V2)
    write(os.path.join(dst, "inbox", ".gitkeep"), "")


def fingerprints(eng):
    """The v1 history the real one is built like: every shipped path and content, hashed, plus the renames."""
    paths, contents = set(), set()
    for d, _dirs, files in os.walk(eng):
        for fn in files:
            p = os.path.join(d, fn)
            paths.add(BO.path_key(os.path.relpath(p, eng).replace(os.sep, "/")))
            contents.add(BO.content_key(rb(p)))
    packs = rjs(os.path.join(eng, PACKS))["packs"]
    return {"format": 1, "paths": sorted(paths), "contents": sorted(contents),
            "renamed": {BO.path_key(o): n for o, n in ((OLD_HOOK_FILE, HOOK_FILE), (OLD_FONT_DOC, FONT_DOC),
                                                        (OLD_TOOL, NEW_TOOL))},
            "launch_packs": sorted(BO.launch_pack_key(n, b) for n, b in packs.items() if b.get("in_launch_kit"))}


def originals(eng, version):
    """The archive an update leaves in an engine (keep_changes.build_store): every shipped text original."""
    files, blobs = {}, []
    for d, _dirs, names in os.walk(eng):
        for fn in names:
            p = os.path.join(d, fn)
            r, data = os.path.relpath(p, eng).replace(os.sep, "/"), rb(p)
            files[r] = hashlib.sha256(data).hexdigest()
            try:
                data.decode("utf-8")
                blobs.append((files[r], r, data))
            except UnicodeDecodeError:
                pass
    KC.build_store(os.path.join(eng, *KC.STORE_REL.split("/")), {version: files}, blobs)


def v2_moves_on(dst):
    """The new version changed its own copies of the files her settings live in: both have to survive."""
    st = rjs(os.path.join(dst, SETTINGS))
    # A new engine hook runs one of the engine's own hook scripts (settings_persist.ENGINE_HOOK_SCRIPTS, which
    # check-ship holds every shipped hook to); here it is a new way of running one of them.
    st["hooks"].setdefault("SessionStart", [{"matcher": "startup", "hooks": []}])[0]["hooks"].append(
        {"type": "command", "command": "bash .claude/hooks/update-check.sh --engine-v2"})
    write(os.path.join(dst, SETTINGS), st)
    write(os.path.join(dst, HOOK_FILE), rd(os.path.join(dst, HOOK_FILE)) + "\n# engine change v2\n")
    write(os.path.join(dst, FONT_DOC), rd(os.path.join(dst, FONT_DOC)) + "\nEngine note v2.\n")
    cc = rjs(os.path.join(dst, WORDS))
    cc["words"]["capcutpro"] = "CapCut Pro"
    cc["check"].append("newflag")
    write(os.path.join(dst, WORDS), cc)


def customize(eng, fonts):
    """Everything a creator sets up in her v1 engine, done the way her sessions do it."""
    sp = rjs(os.path.join(eng, PACKS))
    block = copy.deepcopy(sp["packs"]["Butter"])
    for role, (font, fil) in {"headline": ("Sunday Display", "SYSTEM:Sunday Display"),
                              "takeover": ("Sunday Display", "SYSTEM:Sunday Display"),
                              "caption": ("Sunday Text", os.path.join(fonts, "Sunday-Text.ttf")),
                              "thought_bubble": ("Sunday Hand", os.path.join(fonts, "Sunday-Hand.otf")),
                              "accent_caption": ("Sunday Hand", os.path.join(fonts, "Sunday-Hand.otf"))}.items():
        block["elements"][role].update(font=font, file=fil)
    block["accent_color"], block["in_launch_kit"] = "#C2410C", False
    write(os.path.join(fonts, "block.json"), block)
    rc, out = sh(eng, "product/pack_write.py", "--name", "Sunday Best", "--block", os.path.join(fonts, "block.json"),
                 "--system-font", f"Sunday Display={os.path.join(fonts, 'Sunday-Display.otf')}")
    check("v1: the quick pack saves through pack_write.py", rc == 0 and "user-packs.json" in out, out[-300:])
    rc, out = sh(eng, "product/pack_recipe.py", "--name", "Sunrise", "--main", "Clash Display", "--caption", "Inter",
                 "--accent", "Caveat", "--primary", "#E8502E", "--secondary", "#F5C518", "--mood", "warm playful bold",
                 "--write")
    check("v1: the recipe pack writes", rc == 0 and "saved to user-packs.json" in out, out[-300:])
    write(os.path.join(eng, USER_STYLE), {"_doc": "old doc", "default_pack": "Sunday Best", "default_accent": "#C2410C",
                                          "history": [None]})
    rc, out = sh(eng, "-c", "import sys; sys.path.insert(0,'product'); import text_effects as t; "
                            "t.teach('the snap', base='spring-scale-in', dur=0.28)")
    check("v1: a named text animation is taught", rc == 0, out[-300:])
    for field, value in (("sfx.density", "lighter"), ("effects.hook", "the snap")):
        rc, out = sh(eng, "product/learned.py", "add", field, value)
        check(f"v1: a preference is learned ({field})", rc == 0, out[-300:])
    write(os.path.join(eng, "_local", "favorites.json"),
          {"project": "my sound palette", "sounds": [{"file": "_local/sounds/soft-click.mp3"}], "rules": ["no whooshes"]})
    write(os.path.join(eng, "_local", "sounds", "soft-click.mp3"), b"ID3 her saved sound")
    write(os.path.join(eng, "_local", "style-packs.json"), {"packs": {"Local Only": sp["packs"]["Editorial"]}})
    write(os.path.join(eng, FONT_MAP), {"sunday hand": os.path.join(fonts, "Sunday-Hand.otf")})
    write(os.path.join(eng, "brand-kit.md"), HER_KIT)
    cm = re.sub(r"### Applied.*?(?=\*\*⚠️ ASK THE REGISTER)", HER_PROFILE, rd(os.path.join(eng, "CLAUDE.md")), flags=re.S)
    cm = cm.replace("**🎨 LOOK IS NOT SET YET.** Starter defaults.", HER_LOOK).replace("- engine rule v1\n",
                                                                                      "- engine rule v1\n" + HER_LINE + "\n")
    write(os.path.join(eng, "CLAUDE.md"), cm.replace("\n", "\r\n").encode("utf-8"))   # as Windows saves it
    write(os.path.join(eng, *KC.DOC_REL.split("/")), KC._HEAD + "\n## v1.0.93 → v1.0.94 · 2026-09-20 10:00\n\n"
          "- an earlier update's record of her changes\n")
    cc = rjs(os.path.join(eng, WORDS))
    cc = {"_README": "the v1 notes", "auto": dict(cc["words"]), "flag": list(cc["check"])}   # as v1 shipped it
    cc["auto"]["sourdoughsundays"] = "SourdoughSundays"
    cc["auto"]["tiktok"] = "TIKTOK"                                    # she re-spelled one of the defaults
    cc["flag"].append("herword")
    write(os.path.join(eng, WORDS), cc)
    hp = os.path.join(eng, OLD_HOOK_FILE)
    src = re.sub(r'^DEFAULT_HOOK_TEXT = ""', 'DEFAULT_HOOK_TEXT = "okay so here is the thing"', rd(hp), flags=re.M)
    write(hp, re.sub(r"^HOOK_END_WORDS = \(\)", 'HOOK_END_WORDS = ("thing",)', src, flags=re.M))
    fd = os.path.join(eng, OLD_FONT_DOC)                               # Part B's swap, as settings_persist makes it
    text = rd(fd).replace("Inter-{Black,Bold,Regular}", "Recoleta-{Black,Bold,Regular}")
    write(fd, re.sub(r"\bInter\b", "Recoleta", text))
    st = rjs(os.path.join(eng, SETTINGS))
    st["permissions"] = {"defaultMode": "bypassPermissions"}
    st["hooks"]["Stop"] = [{"matcher": "", "hooks": [{"type": "command", "command": "bash her-chime.sh"}]}]
    write(os.path.join(eng, SETTINGS), st)                             # ...and a hook of her own
    write(os.path.join(eng, ".claude", "settings.local.json"), {"permissions": {"allow": ["Bash(ffmpeg:*)"]}})
    write(os.path.join(eng, ".env"), "APIFY_TOKEN=her-key\n")
    write(os.path.join(eng, "projects", "my-first-reel", "outputs", "my-first-reel.final.mp4"), b"her finished reel")
    write(os.path.join(eng, "projects", "my-first-reel", "raw", "take-1.mov"), b"her raw take")
    write(os.path.join(eng, "inbox", "kitchen-take.mov"), b"her next clip")
    write(os.path.join(eng, "assets", "logos", "sunday-logo.png"), b"\x89PNG her logo")
    write(os.path.join(eng, SFX, "her-chime.mp3"), b"ID3 her own chime")
    write(os.path.join(eng, "notes", "my-ideas.txt"), "reel ideas\n")
    # the engine's own markers and caches: never brought over
    write(os.path.join(eng, "_local", "post-update-1.0.94.ok"), "ok\n")
    write(os.path.join(eng, "_local", "render-log", "render-1.json"), {"frames": 10})
    write(os.path.join(eng, "_local", "machine.txt"), "this machine\n")
    # one of the engine's OWN packs, changed in place ("keep Butter, just a pinker accent")
    sp = rjs(os.path.join(eng, PACKS))
    sp["packs"]["Butter"]["accent_color"] = "#E86A92"
    write(os.path.join(eng, PACKS), sp)
    # a quick pack an EARLIER update deleted, alive only in that update's backup; and one she deleted for good
    bk = os.path.join(eng, "_update-backups", "v1.0.80-to-v1.0.81-20260101-000000")
    old_sp = rjs(os.path.join(ROOT, PACKS))
    old_sp["packs"]["Old Friend"] = dict(copy.deepcopy(old_sp["packs"]["Playful"]), in_launch_kit=False,
                                         accent_color="#123456")
    old_sp["packs"]["Retired Look"] = dict(copy.deepcopy(old_sp["packs"]["Editorial"]), in_launch_kit=False,
                                           accent_color="#654321")
    write(os.path.join(bk, "overwritten", PACKS), old_sp)
    write(os.path.join(bk, "applied.json"), {"from": "1.0.80", "to": "1.0.81", "wrote": [], "deleted": []})
    side = rjs(os.path.join(eng, SIDECAR))
    side["forgotten"] = ["Retired Look"]
    write(os.path.join(eng, SIDECAR), side)
    # two hand edits: one to a shipped engine file, one to a file the new version renamed
    write(os.path.join(eng, "product", "learned.py"),
          rd(os.path.join(eng, "product", "learned.py")) + "\n# her tweak: lighter sound by default\n")
    write(os.path.join(eng, OLD_TOOL), HER_TOOL)


with tempfile.TemporaryDirectory() as tmp:
    old, new = os.path.join(tmp, "Old Engine v1"), os.path.join(tmp, "New Engine v2")   # spaces on purpose
    fonts = os.path.join(tmp, "her fonts")
    for fn in ("Sunday-Display.otf", "Sunday-Text.ttf", "Sunday-Hand.otf"):
        write(os.path.join(fonts, fn), "font " + fn)

    print("building a fully customized v1 engine and a fresh v2 engine")
    install(old, "1.0.94", v1=True)
    hist = os.path.join(tmp, "v1-history.json")
    write(hist, fingerprints(old))
    originals(old, "1.0.94")
    customize(old, fonts)
    install(new, "2.0.0", v1=False)
    v2_moves_on(new)
    old_packs = rjs(os.path.join(old, PACKS))["packs"]
    v2_butter = rjs(os.path.join(new, PACKS))["packs"]["Butter"]

    print("\n1. the preview writes nothing and names every item")
    before_old, before_new = tree(old), tree(new)
    dry_env = {k: v for k, v in ENV.items() if k != "PYTHONDONTWRITEBYTECODE"}   # the script keeps itself clean
    rc, out = sh(new, "scripts/bring-over.py", old, "--history", hist, env=dry_env)
    print("\n".join("      | " + line for line in out.splitlines()))
    check("the preview runs", rc == 0 and "Traceback" not in out, out[-800:])
    t_old, t_new = tree(old), tree(new)
    check("the preview wrote NOTHING in the old engine", t_old == before_old,
          sorted(k for k in set(t_old) | set(before_old) if t_old.get(k) != before_old.get(k)))
    check("the preview wrote NOTHING in the new engine (not even a compiled cache)", t_new == before_new,
          sorted(k for k in set(t_new) | set(before_new) if t_new.get(k) != before_new.get(k)))
    for what, needle in (("her brand kit", "your brand kit"), ("her creator profile", "creator profile"),
                         ("the quick pack", '"Sunday Best"'), ("the recipe pack", '"Sunrise"'),
                         ("the pack only an old backup still has", '"Old Friend"'),
                         ("the engine pack she changed, as her own", '"My Butter"'),
                         ("her default pack and accent", "#C2410C"), ("her learned preferences", "2 learned preferences"),
                         ("her favorite sounds", "favorite sounds (1 saved)"), ("her local pack", "local style packs"),
                         ("the text animation she named", "text animations you named"),
                         ("her hand-mapped fonts", "fonts you matched up by hand"),
                         ("her caption word", "sourdoughsundays"), ("her permission mode", "permission mode"),
                         ("her hook defaults", "your default hook"), ("her headline font", "Recoleta"),
                         ("her keys", "your keys (.env)"), ("her local Claude settings", "settings.local.json"),
                         ("her project", "my-first-reel"), ("her inbox clip", "kitchen-take.mov"),
                         ("her logo", "sunday-logo.png"), ("her own sound", "her-chime.mp3"),
                         ("a Needs a hand section", "Needs a hand"), ("her edit to a shipped file", "product/learned.py"),
                         ("her edit to a renamed file, by its NEW path", NEW_TOOL),
                         ("...and by the name she knew", OLD_TOOL),
                         ("her own lines in CLAUDE.md", "1 line of your own"),
                         ("the hook she added to the engine's settings", "your own hooks"),
                         ("the file left for her to decide", "notes/my-ideas.txt"),
                         ("the keep-your-old-folder warning", "Keep your old folder"),
                         ("the command that applies it", "--apply")):
        check(f"the preview names {what}", needle in out, needle)
    check("a pack she deleted for good is not offered", "Retired Look" not in out)
    check("the engine's markers and caches are not offered", "post-update" not in out and "render-log" not in out)

    print("\n1b. where her footage would be a second full copy (a PC, another drive), she picks first")
    pc_env = {**dry_env, "BRING_OVER_NO_CLONES": "1"}
    rc, out = sh(new, "scripts/bring-over.py", old, "--history", hist, env=pc_env)
    check("the preview asks her to pick, with both commands",
          rc == 0 and "pick one" in out and "--apply --projects" in out and "--apply --no-projects" in out, out[-600:])
    rc, out = sh(new, "scripts/bring-over.py", old, "--apply", "--history", hist, env=pc_env)
    check("--apply alone stops before copying anything and says why",
          rc == 1 and "One choice before anything is copied" in out and "Traceback" not in out, out[-600:])
    rc, out2 = sh(new, "scripts/bring-over.py", old, "--apply", "--projects", "--no-projects", "--history", hist,
                  env=pc_env)
    check("both choices at once is refused", rc == 1 and "Pick one" in out2, out2[-300:])
    check("...and nothing was written anywhere", tree(new) == before_new and tree(old) == before_old)
    if sys.platform == "darwin":
        rc, out = sh(new, "scripts/bring-over.py", old, "--history", hist, env=dry_env)
        check("on a Mac that clones, nothing is asked", "pick one" not in out and "--apply --projects" not in out)

    print("\n2. --apply brings every item where it belongs")
    pick = [] if sys.platform == "darwin" else ["--projects"]      # a PC is asked first (1b), and says yes here
    rc, out = sh(new, "scripts/bring-over.py", old, "--apply", *pick, "--history", hist)
    print("\n".join("      | " + line for line in out.splitlines()))
    check("--apply runs cleanly", rc == 0 and "Traceback" not in out, out[-1500:])
    after = tree(new)
    check("the old folder was only read", tree(old) == before_old)
    changed = sorted(k for k in before_new if k in after and after[k] != before_new[k])
    deleted = sorted(k for k in before_new if k not in after)
    added = sorted(k for k in after if k not in before_new)
    merges = {"brand-kit.md", "CLAUDE.md", PACKS, PALETTES, USER_STYLE, WORDS, HOOK_FILE, FONT_DOC, SETTINGS}
    check("nothing in the new engine was deleted", not deleted, deleted)
    check("the engine's own files are unchanged except the documented merges", set(changed) <= merges,
          sorted(set(changed) - merges))
    hers = ("_local/", "projects/", "inbox/", "assets/logos/", SFX + "/her-chime.mp3", SIDECAR, EFFECTS, FONT_MAP,
            PACKS + ".bak", PALETTES + ".bak", ".env", ".claude/settings.local.json")
    check("every new file is one of hers, in its place", all(a.startswith(hers) for a in added),
          [a for a in added if not a.startswith(hers)])
    check("the engine files she changed are NOT copied over the new ones",
          rd(os.path.join(new, "product", "learned.py")) == rd(os.path.join(ROOT, "product", "learned.py"))
          and rd(os.path.join(new, NEW_TOOL)) == TOOL_V2)

    j = lambda *p: rjs(os.path.join(new, *p)) or {}                                    # noqa: E731
    check("her brand kit, whole", rd(os.path.join(new, "brand-kit.md")) == HER_KIT)
    cm = rd(os.path.join(new, "CLAUDE.md")) or ""
    check("her creator profile and look note are in the NEW instructions",
          HER_PROFILE.strip() in cm and HER_LOOK in cm and "engine rule v2" in cm and "engine rule v1" not in cm, cm)
    check("...and her other line is not merged blind", HER_LINE not in cm)
    live = j(PACKS).get("packs", {})
    check("the quick pack arrived exactly", live.get("Sunday Best") == old_packs["Sunday Best"])
    check("...with the system font it points at", "Sunday Display" in (j(PACKS).get("system_fonts") or {}))
    check("the recipe pack arrived exactly, colors included", live.get("Sunrise") == old_packs["Sunrise"]
          and palette(new, "Sunrise") == palette(old, "Sunrise") and len(palette(new, "Sunrise")) == 6,
          palette(new, "Sunrise"))
    check("the pack only an old update backup still had is back", (live.get("Old Friend") or {}).get("accent_color") == "#123456")
    check("a pack she deleted for good stays deleted", "Retired Look" not in live)
    mb = live.get("My Butter") or {}
    check("the engine pack she changed came across as her own pack", mb.get("accent_color") == "#E86A92"
          and mb.get("in_launch_kit") is False and len(palette(new, "My Butter")) == 6, mb.get("accent_color"))
    check("...and the engine's own Butter is the new version's, untouched", live.get("Butter") == v2_butter)
    saved = j(SIDECAR).get("packs", {})
    check("this engine's protected copy records every pack of hers",
          all(n in saved for n in ("Sunday Best", "Sunrise", "Old Friend", "My Butter")), sorted(saved))
    us = j(USER_STYLE)
    check("her default pack and accent", us.get("default_pack") == "Sunday Best" and us.get("default_accent") == "#C2410C", us)
    rc2, out2 = sh(new, "-c", "import sys; sys.path.insert(0,'product'); import stylepack; stylepack.load('Sunday Best'); "
                              "stylepack.load('Local Only')")
    check("her default pack and her local pack both load in the new engine", rc2 == 0, out2[-300:])
    for p in ("learned.json", "favorites.json", "sounds/soft-click.mp3", "style-packs.json"):
        check(f"_local/{p} came across exactly", rb(os.path.join(new, "_local", p)) == rb(os.path.join(old, "_local", p)))
    check("the engine's markers and caches did not come across",
          not any(os.path.exists(os.path.join(new, "_local", p)) for p in ("post-update-1.0.94.ok", "render-log", "machine.txt")))
    check("her named text animation and her font map came across",
          rb(os.path.join(new, EFFECTS)) == rb(os.path.join(old, EFFECTS)) and rb(os.path.join(new, FONT_MAP)) == rb(os.path.join(old, FONT_MAP)))
    cc = j(WORDS)
    check("her caption word is in the new word list", (cc.get("words") or {}).get("sourdoughsundays") == "SourdoughSundays")
    check("...her spelling wins where both have the word", (cc.get("words") or {}).get("tiktok") == "TIKTOK")
    check("...and the new version's own new words still arrived", (cc.get("words") or {}).get("capcutpro") == "CapCut Pro"
          and "newflag" in cc.get("check", []) and "herword" in cc.get("check", []))
    check("...under today's part names only", not {"_README", "auto", "flag"} & set(cc), sorted(cc))
    hook = os.path.join(new, HOOK_FILE)
    check("her hook defaults, in the new version's file", const(hook, "DEFAULT_HOOK_TEXT") == "okay so here is the thing"
          and tuple(const(hook, "HOOK_END_WORDS") or ()) == ("thing",) and "# engine change v2" in (rd(hook) or ""))
    fd = rd(os.path.join(new, FONT_DOC)) or ""
    check("her headline font, in the new version's type page", "Recoleta-{Black,Bold,Regular}" in fd and "Engine note v2." in fd)
    st = j(SETTINGS)
    check("her permission mode, next to the new version's own hooks",
          (st.get("permissions") or {}).get("defaultMode") == "bypassPermissions" and "--engine-v2" in json.dumps(st.get("hooks")))
    check("her local Claude settings and her keys", rb(os.path.join(new, ".claude", "settings.local.json")) ==
          rb(os.path.join(old, ".claude", "settings.local.json")) and rd(os.path.join(new, ".env")) == "APIFY_TOKEN=her-key\n")
    check("her project came across whole", all(rb(os.path.join(new, "projects", "my-first-reel", *p)) ==
                                               rb(os.path.join(old, "projects", "my-first-reel", *p))
                                               for p in (("outputs", "my-first-reel.final.mp4"), ("raw", "take-1.mov"))))
    check("her inbox clip, her logo and her own sound came across",
          rb(os.path.join(new, "inbox", "kitchen-take.mov")) == b"her next clip"
          and rb(os.path.join(new, "assets", "logos", "sunday-logo.png")) == b"\x89PNG her logo"
          and rb(os.path.join(new, SFX, "her-chime.mp3")) == b"ID3 her own chime")
    check("a file outside those places is left for her to decide", not os.path.exists(os.path.join(new, "notes")))
    keep = os.path.join(new, "_local", "my-changes", "from-v1")
    check("her edit to a shipped engine file is saved", rd(os.path.join(keep, "product", "learned.py")) ==
          rd(os.path.join(old, "product", "learned.py")))
    check("her edit to a renamed file is saved under its NEW path", rd(os.path.join(keep, NEW_TOOL)) == HER_TOOL)
    check("her change to the shipped file comes with the diff the update skill reads",
          "+# her tweak: lighter sound by default" in (rd(os.path.join(keep, "product", "learned.py.diff")) or ""))
    check("...and so does her change to the renamed file, named by its NEW path",
          "+    return 62  # she likes more headroom" in (rd(os.path.join(keep, NEW_TOOL + ".diff")) or "")
          and f"yours/{NEW_TOOL}" in (rd(os.path.join(keep, NEW_TOOL + ".diff")) or ""))
    check("her CLAUDE.md is saved, with exactly her own line as the change",
          HER_LINE in (rd(os.path.join(keep, "CLAUDE.md.diff")) or "") and rd(os.path.join(keep, "CLAUDE.md")) ==
          rd(os.path.join(old, "CLAUDE.md")))
    doc = rd(os.path.join(new, "_local", "my-changes.md")) or ""
    section = doc.split("**Needs a hand", 1)[1].split("\n\n**", 1)[0] if "**Needs a hand" in doc else ""
    check("_local/my-changes.md lists them under Needs a hand, where the update skill looks",
          "`product/learned.py`" in section and f"`{NEW_TOOL}`" in section and OLD_TOOL in section
          and "`CLAUDE.md`" in section and "bring my changes forward" in doc, doc[:1500])
    check("...and records her changed Butter as My Butter", "**My Butter**" in doc)
    check("the hook she added to the engine's own settings file came across, and runs in the new version",
          json.dumps(st.get("hooks")).count("her-chime.sh") == 1)
    check("...so the settings file is not left needing a hand (only the engine's own part could be)",
          f"`{SETTINGS}`" not in section, section)
    check("...with the old engine's own record of changes kept below it",
          doc.count("# Your changes to the engine") == 1 and "an earlier update's record of her changes" in doc
          and doc.index("v1.0.94 → v2.0.0") < doc.index("v1.0.93 → v1.0.94"))

    print("\n3. --apply again changes nothing")
    rc, out = sh(new, "scripts/bring-over.py", old, "--apply", "--history", hist)
    print("\n".join("      | " + line for line in out.splitlines()[:12]))
    again = tree(new)
    check("a second --apply runs cleanly", rc == 0 and "Traceback" not in out, out[-800:])
    check("a second --apply changes nothing at all", again == after,
          sorted(k for k in set(again) | set(after) if again.get(k) != after.get(k)))
    check("...and says so", "already here" in out and "Nothing was brought twice" in out, out[-600:])
    check("the old folder is still untouched", tree(old) == before_old)

    print("\n4. it refuses, plainly, what it must not bring over")
    stray = os.path.join(tmp, "Just A Folder")
    os.makedirs(stray)
    newer = os.path.join(tmp, "Another v2")
    write(os.path.join(newer, "product.json"), {"engine": "ai-edit-engine", "version": "2.0.1"})
    for what, target, needle in (("a folder that is not an engine", stray, "does not look like"),
                                 ("this same folder", new, "this engine's own folder"),
                                 ("a folder already on the new version", newer, "already v2.0.1")):
        rc, out = sh(new, "scripts/bring-over.py", target, "--history", hist)
        check(f"refuses {what}", rc == 1 and needle in out and "Traceback" not in out, out[-300:])
    check("...and writes nothing while refusing", tree(new) == after)
    rc, out = sh(new, "scripts/bring-over.py", "--find", env={**ENV, "HOME": tmp, "USERPROFILE": tmp})
    listed = [line for line in out.splitlines() if re.match(r"\s+\d+\. ", line)]
    check("--find lists the old engine for her to pick, and only folders that can be brought over",
          rc == 0 and len(listed) == 1 and old in listed[0] and "v1.0.94" in listed[0], out[-500:])

print("\n5. seller side: the lineage rule and the real v1 history")
builder = os.path.join(ROOT, "dev-tools", "build-v1-history.py")
if not os.path.exists(builder):
    print("  (skipped: dev-tools/ is not in this copy of the engine, as in every copy a creator receives)")
else:
    BH = _load("build_v1_history", builder)
    olds = sorted({o for o, _n in BH.RENAMES} | {os.path.basename(o) for o, _n in BH.RENAMES})
    for carrier in ("scripts/bring-over.py", ".claude/skills/bring-over/SKILL.md", BO.HISTORY_REL,
                    "product/tests/test_bring_over.py"):
        text = rd(os.path.join(ROOT, carrier))
        hits = [o for o in olds if o in (text or "")]
        check(f"no v1 name of a renamed file in {carrier}", text is not None and not hits, hits or "missing")
    manifests = glob.glob(os.path.join(ROOT, ".ship-state", "manifest-v1.*.json"))
    if manifests:
        H = BO.History.load(os.path.join(ROOT, *BO.HISTORY_REL.split("/")))
        newest = max(manifests, key=lambda p: BO.semver(json.load(open(p, encoding="utf-8"))["version"]))
        with open(newest, encoding="utf-8") as fh:
            m = json.load(fh)
        bad = [r for r, sha in m["files"].items() if not (H and H.shipped_path(r) and sha[:32] in H.contents)]
        check(f"every file of the real v{m['version']} reads as the engine's own ({len(m['files'])} files)", not bad, bad[:5])
        check("every rename resolves to its new path", H is not None and all(H.new_name(o) == n for o, n in BH.RENAMES))
        rc, out = sh(ROOT, builder, "--check")
        if rc == 2:
            print("  (history freshness check skipped: no git history in this copy, e.g. a release-gate copy)")
        else:
            check("the shipped v1 history is current with every v1 manifest (else: python3 dev-tools/build-v1-history.py)",
                  rc == 0, out[-300:])

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "bring-over brings everything of hers into the new version, once"))
sys.exit(1 if fails else 0)
