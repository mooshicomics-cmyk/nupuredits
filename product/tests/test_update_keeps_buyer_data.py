#!/usr/bin/env python3
"""An update must never destroy what the buyer set up. Runs a REAL update, end to end, in a throwaway folder.

Reproduces a tester's report: onboarding wrote her business names into presets/caption-corrections.json
(the file's own README tells buyers to add them there), then a routine "update me" replaced that file
wholesale and her names were gone. Her captions went back to mishearing her own brand.

Three promises are pinned here, each against the real scripts/apply-update.py rather than a copy of it:
  1. MERGE   caption-corrections: new shipped defaults arrive AND every word the buyer added survives,
             with the buyer's spelling winning when both define the same word.
  2. PROTECT user-style.json: the buyer's chosen style pack and accent are never touched.
  3. HONEST  the delete count names only files that are actually present, so "files to remove: 33"
             can no longer be printed while nothing is removed.

Then the whole promise, on a FULLY customized install (5-9): every style pack she built (the quick
fonts-and-accent kind that used to be skipped and deleted, and a recipe pack), her default pack and accent,
a taught preference, a named text animation, her favorites shelf, a hand-mapped font, her brand kit and its
Part B edits (creator profile, look banner, word list, hook defaults, headline font), her permission mode,
her local settings, her jobs and keys. It runs the real apply-update.py + post-update.py over it, then:
  5. the current updater: nothing lost, the engine's own changes still arrive, a second run is a no-op
  6. the undo right after an update that refreshed CLAUDE.md (it used to crash)
  7. the updater ALREADY on a buyer's machine (older, knows none of this): post-update, which ships inside
     the update, still brings every customization through, incl. a pack she changed since it was saved
  8. a pack an EARLIER update deleted comes back from _update-backups; one she deleted for good does not
  9. a setting an earlier update replaced is reported by `settings_persist.py recover`, applied only on --apply
Both updaters also meet a file the engine stops shipping: the engine's own copy goes, hers (her own pop.mp3
in the sound folder) stays.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"\n         {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2))


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


with tempfile.TemporaryDirectory() as tmp:
    buyer = os.path.join(tmp, "buyer")
    pkg = os.path.join(tmp, "pkg")

    # ---- the buyer's installed engine, after onboarding -------------------------------------------
    os.makedirs(os.path.join(buyer, "scripts"))
    shutil.copy2(os.path.join(ROOT, "scripts", "apply-update.py"), os.path.join(buyer, "scripts"))
    write(os.path.join(buyer, "product.json"), {"engine": "ai-edit-engine", "version": "1.0.56"})
    write(os.path.join(buyer, "presets", "caption-corrections.json"), {
        "_README": "old readme",
        "auto": {"youtube": "YouTube",
                 "acmebakery": "AcmeBakery",          # added at onboarding: her business (fictitious)
                 "smithson": "Smithson",              # added at onboarding: her surname (fictitious)
                 "claude": "CLAUDE"},                 # she deliberately re-spelled a default
        "flag": ["notion", "herword"],
    })
    write(os.path.join(buyer, "product", "creative-vault", "user-style.json"),
          {"default_pack": "Butter", "default_accent": "#D4A373", "history": ["Butter"]})
    write(os.path.join(buyer, "stale-engine-file.md"), "engine file this update really removes")

    # ---- an update that ships new defaults and an edited style template ---------------------------
    files = os.path.join(pkg, "files")
    write(os.path.join(files, "presets", "caption-corrections.json"), {      # today's part names
        "about": ["new notes"],
        "words": {"youtube": "YouTube", "claude": "Claude", "capcut": "CapCut"},  # capcut is a NEW default
        "phrases": {},
        "check": ["notion", "cloud"],                                             # cloud is a NEW check word
    })
    write(os.path.join(files, "product", "creative-vault", "user-style.json"),
          {"_doc": "edited template", "default_pack": None, "default_accent": None, "history": []})
    write(os.path.join(pkg, "update.json"), {
        "engine": "ai-edit-engine", "version": "1.0.99", "min_version": "1.0.0",
        "summary": "test update", "changes": [],
        "files": ["presets/caption-corrections.json", "product/creative-vault/user-style.json"],
        # one delete the buyer really has, plus 32 she never had (the package lists every removal ever)
        "deletes": ["stale-engine-file.md"] + [f"gone/never-installed-{i}.py" for i in range(32)],
    })

    run = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "apply-update.py"), pkg],
                         capture_output=True, text=True, cwd=buyer,
                         env={**os.environ, "PYTHONUTF8": "1"})
    out = run.stdout + run.stderr
    check("the update itself ran cleanly", run.returncode == 0, out[-600:])

    print("\n1. caption corrections are MERGED, not replaced")
    cc = read_json(os.path.join(buyer, "presets", "caption-corrections.json"))
    auto = cc.get("words", {})
    check("her business name survived the update", auto.get("acmebakery") == "AcmeBakery", auto)
    check("her surname survived the update", auto.get("smithson") == "Smithson", auto)
    check("a brand-new shipped default still arrived", auto.get("capcut") == "CapCut", auto)
    check("where both define a word, HER spelling wins", auto.get("claude") == "CLAUDE", auto)
    check("her own flag word survived", "herword" in cc.get("check", []), cc.get("check"))
    check("a brand-new shipped flag still arrived", "cloud" in cc.get("check", []), cc.get("check"))
    check("the new notes are taken from the update", cc.get("about") == ["new notes"])
    check("her entries moved to today's part names", not {"_README", "auto", "flag"} & set(cc), sorted(cc))

    print("\n2. the buyer's chosen style is PROTECTED")
    us = read_json(os.path.join(buyer, "product", "creative-vault", "user-style.json"))
    check("her style pack is untouched", us.get("default_pack") == "Butter", us)
    check("her accent colour is untouched", us.get("default_accent") == "#D4A373", us)

    print("\n3. the delete count is honest")
    check("the one file she really had was removed",
          not os.path.exists(os.path.join(buyer, "stale-engine-file.md")))
    check("it reports 1 file to remove, not 33", "files to remove:      1" in out,
          [l for l in out.splitlines() if "files to remove" in l])

    print("\n4. it is all still reversible")
    rb = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "apply-update.py"), "--rollback"],
                        capture_output=True, text=True, cwd=buyer, env={**os.environ, "PYTHONUTF8": "1"})
    check("rollback ran", rb.returncode == 0, (rb.stdout + rb.stderr)[-400:])
    check("rollback restored the deleted file", os.path.exists(os.path.join(buyer, "stale-engine-file.md")))
    back = read_json(os.path.join(buyer, "presets", "caption-corrections.json"))
    check("rollback restored her exact pre-update wordlist", back.get("_README") == "old readme"
          and "capcut" not in back.get("auto", {}), back)


# ======================================================================================================
# 5-9. A FULLY customized install through a real update: every buyer customization must come through.
# ======================================================================================================
import copy, hashlib, re

ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "REELS_ENGINE_SKIP_BROWSER_ENSURE": "1"}
SHIPPED = ["scripts/apply-update.py", "scripts/post-update.py", "scripts/merge-claude-md.py",
           "product/pack_persist.py", "product/pack_write.py", "product/user_style.py", "product/settings_persist.py",
           "product/pack_recipe.py", "product/stylepack.py", "product/learned.py", "product/text_effects.py",
           "product/pack_palettes.py", "product/creative-vault/style-packs.json",
           "product/creative-vault/user-style.json", "presets/caption-corrections.json",
           "presets/clean-captions/build.py", "presets/type-and-look.md", ".claude/settings.json"]
ENGINE_DOC = ("# CLAUDE.md\n\n## Brand Kit\n\n### Applied - nothing yet (fresh install)\n\nNo creator yet.\n\n"
              "**⚠️ ASK THE REGISTER AT THE GRAPHICS STEP**\n\n**🎨 LOOK IS NOT SET YET.** Starter defaults.\n\n"
              "## Rules\n- engine rule {v}\n")
ENGINE_SOUNDS = {"product/creative-vault/sfx/pop.mp3": "ID3 the engine's pop",
                 "product/creative-vault/sfx/retired.mp3": "ID3 an engine sound"}
HER_POP = "ID3 HER own pop, dropped where the library page says"
HER_PROFILE = "### Applied — Jane Rivera / Sourdough Sundays\n\nCalm and exact. Gut check: hands in the dough?\n\n"
HER_LOOK = "**🎨 LOOK IS SET: Sunday Best.** Her own pack, accent #C2410C."

# What the updaters ALREADY on buyers' machines do, reduced to what they all share: back up, overwrite the
# listed files, log, bump the version, run the post-update step that ships inside the update. REPLAY=1 also
# replays the protected pack copy the way every updater since the sidecar did, from whatever it holds.
OLD_UPDATER = r"""
import datetime, json, os, shutil, subprocess, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pkg = sys.argv[1]
man = json.load(open(os.path.join(pkg, "update.json"), encoding="utf-8"))
prod = json.load(open(os.path.join(R, "product.json"), encoding="utf-8"))
b = os.path.join(R, "_update-backups", "v%s-to-v%s-%s" % (prod["version"], man["version"],
                 datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
wrote = []
for rel in man["files"]:
    t = os.path.join(R, rel)
    if os.path.exists(t):
        os.makedirs(os.path.dirname(os.path.join(b, "overwritten", rel)), exist_ok=True)
        shutil.copy2(t, os.path.join(b, "overwritten", rel))
    os.makedirs(os.path.dirname(t), exist_ok=True)
    shutil.copy2(os.path.join(pkg, "files", rel), t)
    wrote.append(rel)
deleted = []
for rel in man.get("deletes", []):                 # whatever is there, like every older updater
    t = os.path.join(R, rel)
    if os.path.isfile(t):
        os.makedirs(os.path.dirname(os.path.join(b, "deleted", rel)), exist_ok=True)
        shutil.copy2(t, os.path.join(b, "deleted", rel))
        os.remove(t)
        deleted.append(rel)
if os.environ.get("REPLAY"):
    sys.path.insert(0, os.path.join(R, "product"))
    import pack_write
    side = json.load(open(os.path.join(R, "product", "creative-vault", "user-packs.json"), encoding="utf-8"))
    live = json.load(open(os.path.join(R, "product", "creative-vault", "style-packs.json"), encoding="utf-8"))
    for n, r in side["packs"].items():
        if n not in live["packs"] and r.get("recipe"):
            pack_write.apply(n, r["block"], r["recipe"])
os.makedirs(b, exist_ok=True)
json.dump({"from": prod["version"], "to": man["version"], "wrote": wrote, "deleted": deleted},
          open(os.path.join(b, "applied.json"), "w", encoding="utf-8"))
prod["version"] = man["version"]
open(os.path.join(R, "product.json"), "w", encoding="utf-8").write(json.dumps(prod, indent=2) + "\n")
subprocess.run([sys.executable, os.path.join(R, "scripts", "post-update.py")])
"""


def sh(cwd, *args, env=None):
    r = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=env or ENV)
    return r.returncode, r.stdout + r.stderr


def rd(p):
    try:
        return open(p, encoding="utf-8").read()
    except OSError:
        return None


def rjs(p):
    t = rd(p)
    try:
        return json.loads(t) if t is not None else None
    except ValueError:
        return None


def install(dst, version="1.0.94"):
    """A buyer's engine as it arrives: the shipped files, a blank brand kit, the engine's CLAUDE.md."""
    for rel in SHIPPED:
        if os.path.exists(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), os.path.join(dst, rel))
    write(os.path.join(dst, "product.json"), {"engine": "ai-edit-engine", "version": version})
    for rel, body in ENGINE_SOUNDS.items():          # two sounds the engine shipped, retired by the update
        write(os.path.join(dst, rel), body)
    write(os.path.join(dst, "CLAUDE.md"), ENGINE_DOC.format(v="old"))
    write(os.path.join(dst, "brand-kit.md"), "# Brand kit\n- Headline font: `<<FILL_ME>>`\n")


def customize(dst, fonts, quick_via):
    """Everything a buyer sets up, done the way her session does it."""
    sp = rjs(os.path.join(dst, "product", "creative-vault", "style-packs.json"))
    block = copy.deepcopy(sp["packs"]["Butter"])
    for role, (font, fil) in {"headline": ("Sunday Display", "SYSTEM:Sunday Display"),
                              "takeover": ("Sunday Display", "SYSTEM:Sunday Display"),
                              "caption": ("Sunday Text", os.path.join(fonts, "Sunday-Text.ttf")),
                              "thought_bubble": ("Sunday Hand", os.path.join(fonts, "Sunday-Hand.otf")),
                              "accent_caption": ("Sunday Hand", os.path.join(fonts, "Sunday-Hand.otf"))}.items():
        block["elements"][role].update(font=font, file=fil)
    block["accent_color"], block["in_launch_kit"] = "#C2410C", False
    display = os.path.join(fonts, "Sunday-Display.otf")
    if quick_via == "cli":                     # the style-pack skill today
        write(os.path.join(fonts, "block.json"), block)
        rc, out = sh(dst, "product/pack_write.py", "--name", "Sunday Best", "--block",
                     os.path.join(fonts, "block.json"), "--system-font", f"Sunday Display={display}")
        check("the quick pack saves through pack_write.py", rc == 0 and "user-packs.json" in out, out[-300:])
    else:                                      # what the skill had Claude do before: edit the file by hand
        sp["packs"]["Sunday Best"] = block
        sp.setdefault("system_fonts", {})["Sunday Display"] = display
        write(os.path.join(dst, "product", "creative-vault", "style-packs.json"), sp)
    rc, out = sh(dst, "product/pack_recipe.py", "--name", "Sunrise", "--main", "Clash Display", "--caption",
                 "Inter", "--accent", "Caveat", "--primary", "#E8502E", "--secondary", "#F5C518", "--mood",
                 "warm playful bold", "--write")
    check("the recipe pack writes", rc == 0 and "saved to user-packs.json" in out, out[-300:])
    write(os.path.join(dst, "product", "creative-vault", "user-style.json"),
          {"default_pack": "Sunday Best", "default_accent": "#C2410C", "history": [None]})
    rc, out = sh(dst, "-c", "import sys; sys.path.insert(0,'product'); import text_effects as t; "
                            "t.teach('the snap', base='spring-scale-in', dur=0.28)")
    check("a named text effect is taught", rc == 0, out[-300:])
    for field, value in (("sfx.density", "lighter"), ("effects.hook", "the snap")):
        rc, out = sh(dst, "product/learned.py", "add", field, value)
        check(f"a preference is learned ({field})", rc == 0, out[-300:])
    write(os.path.join(dst, "_local", "favorites.json"),
          {"project": "my sound palette", "sounds": [{"file": "_local/sounds/soft-click.mp3"}], "rules": ["no whooshes"]})
    write(os.path.join(dst, "_local", "sounds", "soft-click.mp3"), "ID3 her sound")
    write(os.path.join(dst, "product", "creative-vault", "font-overrides.json"), {"sunday hand": os.path.join(fonts, "Sunday-Hand.otf")})
    write(os.path.join(dst, "brand-kit.md"), "# Brand kit\n- Headline font: `Recoleta`\n- Hook: `okay so here is the thing`\n")
    cm = rd(os.path.join(dst, "CLAUDE.md"))
    cm = re.sub(r"### Applied.*?(?=\*\*⚠️ ASK THE REGISTER)", HER_PROFILE, cm, flags=re.S)
    write(os.path.join(dst, "CLAUDE.md"), cm.replace("**🎨 LOOK IS NOT SET YET.** Starter defaults.", HER_LOOK))
    cc = rjs(os.path.join(dst, "presets", "caption-corrections.json"))
    cc.setdefault("words", {})["sourdoughsundays"] = "SourdoughSundays"
    write(os.path.join(dst, "presets", "caption-corrections.json"), cc)
    bp = os.path.join(dst, "presets", "clean-captions", "build.py")
    src = re.sub(r'^DEFAULT_HOOK_TEXT = ""', 'DEFAULT_HOOK_TEXT = "okay so here is the thing"', rd(bp), flags=re.M)
    write(bp, re.sub(r"^HOOK_END_WORDS = \(\)", 'HOOK_END_WORDS = ("thing",)', src, flags=re.M))
    ss = os.path.join(dst, "presets", "type-and-look.md")
    write(ss, rd(ss).replace("Inter-{Black,Bold,Regular}", "Recoleta-{Black,Bold,Regular}").replace("Inter", "Recoleta"))
    st = rjs(os.path.join(dst, ".claude", "settings.json"))
    st["permissions"] = {"defaultMode": "bypassPermissions"}          # product/PERMISSIONS-SETUP.md, Option B
    write(os.path.join(dst, ".claude", "settings.json"), st)
    write(os.path.join(dst, ".claude", "settings.local.json"), {"permissions": {"allow": ["Bash(ffmpeg:*)"]}})
    write(os.path.join(dst, "product", "creative-vault", "sfx", "pop.mp3"), HER_POP)
    write(os.path.join(dst, "projects", "my-first-reel", "outputs", "my-first-reel.final.mp4"), "her video")
    write(os.path.join(dst, ".env"), "APIFY_TOKEN=her-key\n")
    write(os.path.join(dst, "_local", "style-packs.json"), {"packs": {"Local Only": sp["packs"]["Editorial"]}})


def _const(path, var):
    import ast
    for node in ast.parse(rd(path) or "").body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == var for t in node.targets):
            return ast.literal_eval(node.value)


def _palette(dst, name):
    import ast
    out = {}
    for node in ast.parse(rd(os.path.join(dst, "product", "pack_palettes.py")) or "").body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == name:
                    out[node.targets[0].id] = ast.literal_eval(v)
    return out


def snapshot(dst):
    """Every customization, as the engine will read it."""
    j = lambda *p: rjs(os.path.join(dst, *p)) or {}
    sp = j("product", "creative-vault", "style-packs.json")
    us = j("product", "creative-vault", "user-style.json")
    st, loc = j(".claude", "settings.json"), j(".claude", "settings.local.json")
    rc, out = sh(dst, "-c", f"import sys; sys.path.insert(0,'product'); import stylepack; stylepack.load({us.get('default_pack')!r})")
    return {
        "quick pack (Sunday Best)": (sp.get("packs") or {}).get("Sunday Best"),
        "quick pack's system font": (sp.get("system_fonts") or {}).get("Sunday Display"),
        "recipe pack (Sunrise)": (sp.get("packs") or {}).get("Sunrise"),
        "recipe pack palette": _palette(dst, "Sunrise"),
        "default pack + accent": [us.get("default_pack"), us.get("default_accent")],
        "default pack builds": rc == 0,
        "learned preferences": sorted((r["field"], r["value"]) for r in j("_local", "learned.json").get("preferences", [])),
        "named text effect": sorted(j("product", "creative-vault", "user-effects.json").get("effects", {})),
        "favorites shelf": [j("_local", "favorites.json"), os.path.exists(os.path.join(dst, "_local", "sounds", "soft-click.mp3"))],
        "hand-mapped font": j("product", "creative-vault", "font-overrides.json"),
        "brand kit": hashlib.sha256((rd(os.path.join(dst, "brand-kit.md")) or "").encode()).hexdigest(),
        "creator profile + look": [HER_PROFILE.strip() in (rd(os.path.join(dst, "CLAUDE.md")) or ""),
                                   HER_LOOK in (rd(os.path.join(dst, "CLAUDE.md")) or "")],
        "her words": (j("presets", "caption-corrections.json").get("words") or {}).get("sourdoughsundays"),
        "hook defaults": [_const(os.path.join(dst, "presets", "clean-captions", "build.py"), "DEFAULT_HOOK_TEXT"),
                          _const(os.path.join(dst, "presets", "clean-captions", "build.py"), "HOOK_END_WORDS")],
        "headline font": "Recoleta-{Black,Bold,Regular}" in (rd(os.path.join(dst, "presets", "type-and-look.md")) or ""),
        "permission mode": (loc.get("permissions") or {}).get("defaultMode") or (st.get("permissions") or {}).get("defaultMode"),
        "local settings": loc,
        "her own pop.mp3": rd(os.path.join(dst, "product", "creative-vault", "sfx", "pop.mp3")),
        "her job, keys, local pack": [os.path.exists(os.path.join(dst, "projects", "my-first-reel", "outputs", "my-first-reel.final.mp4")),
                                      rd(os.path.join(dst, ".env")), sorted(j("_local", "style-packs.json").get("packs", {}))],
    }


def package(pkg, version):
    """An update the way make-update.py builds one: every shipped file (cumulative), with real engine
    changes in the very files her settings live in, so both have to come through."""
    if os.path.exists(pkg):
        shutil.rmtree(pkg)
    files = []
    for rel in SHIPPED:
        if rel in ("product/creative-vault/user-style.json", "presets/caption-corrections.json") \
                or not os.path.exists(os.path.join(ROOT, rel)):
            continue                                  # make-update.py never packs these (they become hers)
        dst = os.path.join(pkg, "files", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), dst)
        files.append(rel)
    f = lambda rel: os.path.join(pkg, "files", rel)
    st = rjs(f(".claude/settings.json"))
    # A new engine hook runs one of the engine's own hook scripts (settings_persist.ENGINE_HOOK_SCRIPTS, which
    # check-ship holds every shipped hook to): here, a new way of running one of them.
    st["hooks"].setdefault("SessionStart", [{"matcher": "startup", "hooks": []}])[0]["hooks"].append(
        {"type": "command", "command": f"bash .claude/hooks/update-check.sh --engine-{version}"})
    write(f(".claude/settings.json"), st)
    write(f("presets/clean-captions/build.py"), rd(f("presets/clean-captions/build.py")) + f"\n# engine change {version}\n")
    write(f("presets/type-and-look.md"), rd(f("presets/type-and-look.md")) + f"\nEngine note {version}.\n")
    sp = rjs(f("product/creative-vault/style-packs.json"))
    sp["_engine_note"] = version
    write(f("product/creative-vault/style-packs.json"), sp)
    write(f("product/templates/CLAUDE.engine.md"), ENGINE_DOC.format(v=version))
    write(f("product.json"), {"engine": "ai-edit-engine", "version": version})
    shipped_as = {rel: [hashlib.sha256(body.encode()).hexdigest()] for rel, body in ENGINE_SOUNDS.items()}
    write(f("product/templates/update-deletes.json"), {"files": shipped_as})       # as make-update.py writes it
    files += ["product/templates/CLAUDE.engine.md", "product.json", "product/templates/update-deletes.json"]
    write(os.path.join(pkg, "update.json"), {"engine": "ai-edit-engine", "version": version, "min_version": "1.0.0",
                                             "summary": "test", "changes": [], "files": files,
                                             "deletes": sorted(ENGINE_SOUNDS), "delete_hashes": shipped_as})


def arrived(dst, version):
    st = rjs(os.path.join(dst, ".claude", "settings.json")) or {}
    return {
        "a new engine hook": f"--engine-{version}" in json.dumps(st.get("hooks")),
        "a change to the hook preset": f"# engine change {version}" in (rd(os.path.join(dst, "presets", "clean-captions", "build.py")) or ""),
        "a change to the type page": f"Engine note {version}." in (rd(os.path.join(dst, "presets", "type-and-look.md")) or ""),
        "a change to style-packs.json": (rjs(os.path.join(dst, "product", "creative-vault", "style-packs.json")) or {}).get("_engine_note") == version,
        "a change to CLAUDE.md's engine rules": f"engine rule {version}" in (rd(os.path.join(dst, "CLAUDE.md")) or ""),
        "the removal of a retired engine sound": not os.path.exists(os.path.join(dst, "product", "creative-vault", "sfx", "retired.mp3")),
    }


def same(label, before, after):
    lost = [k for k in before if before[k] != after.get(k)]
    check(label, not lost, "; ".join(f"{k}: {json.dumps(before[k])[:70]} -> {json.dumps(after.get(k))[:70]}" for k in lost))


def tree_hash(dst):
    h = {}
    for d, _dirs, fs in os.walk(dst):
        for fn in fs:
            p = os.path.join(d, fn)
            if "__pycache__" not in p and "_update-backups" not in p and not fn.endswith(".ok"):
                h[os.path.relpath(p, dst)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return h


with tempfile.TemporaryDirectory() as tmp:
    fonts = os.path.join(tmp, "her-fonts")
    for fn in ("Sunday-Display.otf", "Sunday-Text.ttf", "Sunday-Hand.otf"):
        write(os.path.join(fonts, fn), "font " + fn)

    print("\n5. a fully customized install, through the current updater")
    a, pkg = os.path.join(tmp, "a"), os.path.join(tmp, "pkg")
    install(a)
    customize(a, fonts, "cli")
    before = snapshot(a)
    check("every customization is in place before the update", all(before.values()), before)
    package(pkg, "1.0.99")
    rc, out = sh(a, os.path.join(a, "scripts", "apply-update.py"), pkg)
    check("the update ran cleanly", rc == 0, out[-800:])
    same("every customization survived the update", before, snapshot(a))
    got = arrived(a, "1.0.99")
    check("the engine's own changes arrived too", all(got.values()), got)
    h1 = tree_hash(a)
    rc, out = sh(a, "scripts/post-update.py")
    check("running the finishing step again changes nothing", rc == 0 and tree_hash(a) == h1,
          [k for k in tree_hash(a) if tree_hash(a).get(k) != h1.get(k)])
    rc, out = sh(a, "product/pack_persist.py", "recover")
    check("'restore my style pack' finds nothing missing", rc == 0 and "nothing was missing" in out, out[-300:])

    print("\n6. the undo, right after an update that refreshed CLAUDE.md")
    check("the CLAUDE.md refresh made its own backup folder",
          os.path.isdir(os.path.join(a, "_update-backups", "claude-md")))
    rc, out = sh(a, "scripts/apply-update.py", "--rollback")
    check("rollback runs (it used to pick claude-md/ and crash)", rc == 0 and "Rolled back" in out, out[-600:])
    check("rollback put the previous version back", rjs(os.path.join(a, "product.json"))["version"] == "1.0.94")
    same("everything she had is still there after the undo", before, snapshot(a))

    print("\n7. the updater already on her machine is OLD: the update's own finishing step brings it all through")
    b = os.path.join(tmp, "b")
    install(b)
    customize(b, fonts, "hand")                      # built the old way: never recorded anywhere
    sp_path = os.path.join(b, "product", "creative-vault", "style-packs.json")
    sp = rjs(sp_path)                                 # ...and she changed her recipe pack since it was saved
    sp["packs"]["Sunrise"]["accent_color"] = "#D1432A"
    write(sp_path, sp)
    pal = os.path.join(b, "product", "pack_palettes.py")
    write(pal, rd(pal).replace('"Sunrise": "#FEF9E8"', '"Sunrise": "#FFF4E0"', 1))
    before = snapshot(b)
    check("her change to the recipe pack is in place", before["recipe pack palette"].get("GROUNDS") == "#FFF4E0",
          before["recipe pack palette"])
    # 8's setup: a pack an EARLIER update deleted is still in that update's backup, and so is a setting
    old = os.path.join(b, "_update-backups", "v1.0.80-to-v1.0.81-20260101-000000")
    old_sp = rjs(os.path.join(ROOT, "product", "creative-vault", "style-packs.json"))
    old_sp["packs"]["Old Friend"] = dict(copy.deepcopy(old_sp["packs"]["Playful"]), in_launch_kit=False, accent_color="#123456")
    write(os.path.join(old, "overwritten", "product", "creative-vault", "style-packs.json"), old_sp)
    old_st = rjs(os.path.join(ROOT, ".claude", "settings.json"))
    old_st["env"] = {"HER_OLD_SETTING": "1"}
    write(os.path.join(old, "overwritten", ".claude", "settings.json"), old_st)
    write(os.path.join(old, "applied.json"), {"from": "1.0.80", "to": "1.0.81", "wrote": [], "deleted": []})
    write(os.path.join(b, "scripts", "apply-update.py"), OLD_UPDATER)
    rc, out = sh(b, "scripts/apply-update.py", pkg, env={**ENV, "REPLAY": "1"})
    check("the old updater ran", rc == 0, out[-800:])
    after = snapshot(b)
    same("every customization survived the OLD updater", before, after)
    check("her latest recipe pack, not the older saved copy", after["recipe pack palette"].get("GROUNDS") == "#FFF4E0"
          and (after["recipe pack (Sunrise)"] or {}).get("accent_color") == "#D1432A", after["recipe pack palette"])
    got = arrived(b, "1.0.99")
    check("the engine's own changes arrived too", all(got.values()), got)
    side = rjs(os.path.join(b, "product", "creative-vault", "user-packs.json"))["packs"]["Sunrise"]
    older = {"block": side["block"], "recipe": side["recipe"]}           # how saved copies looked before
    rc, out = sh(b, "-c", "import json, sys; sys.path.insert(0, 'product'); import pack_persist as p; "
                          f"print(p._same(json.loads({json.dumps(json.dumps(older))}), "
                          f"json.loads({json.dumps(json.dumps(side))})))")
    check("a saved copy in the older shape is still recognised as the same pack", out.strip() == "True", out)
    rc, out = sh(b, "scripts/apply-update.py", "--rollback")
    check("she can undo it", rc == 0 and "Rolled back" in out, out[-400:])
    same("the undo gives back exactly what she had", before, snapshot(b))
    rc, out = sh(b, "scripts/apply-update.py", pkg, env={**ENV, "REPLAY": "1"})   # the older updater again
    same("updating again after the undo keeps everything too", before, snapshot(b))

    print("\n8. a pack an EARLIER update deleted comes back; one she deleted for good does not")
    live = rjs(sp_path)["packs"]
    check("the pack an earlier update deleted is back", (live.get("Old Friend") or {}).get("accent_color") == "#123456",
          sorted(live))
    check("it is in the protected copy now", "Old Friend" in (rjs(os.path.join(b, "product", "creative-vault", "user-packs.json")) or {}).get("packs", {}))
    rc, out = sh(b, "product/pack_persist.py", "forget", "Old Friend")
    check("'delete my style pack' takes it out", rc == 0 and "Old Friend" not in rjs(sp_path)["packs"], out)
    rc, out = sh(b, "product/pack_persist.py", "recover")
    check("recover does not bring back a pack she deleted for good", rc == 0 and "Old Friend" not in rjs(sp_path)["packs"], out[-300:])
    rc, out = sh(b, "product/pack_persist.py", "recover")
    check("recover is safe to run twice", rc == 0 and "nothing was missing" in out, out[-300:])

    print("\n9. a setting an earlier update replaced: reported, and put back only when she says yes")
    rc, out = sh(b, "product/settings_persist.py", "recover")
    st = rjs(os.path.join(b, ".claude", "settings.json"))
    check("recover reports it", rc == 0 and "HER_OLD_SETTING" in out, out[-300:])
    check("...without applying it on its own", "HER_OLD_SETTING" not in (st.get("env") or {}))
    rc, out = sh(b, "product/settings_persist.py", "recover", "--apply")
    st = rjs(os.path.join(b, ".claude", "settings.json"))
    check("--apply puts it back", rc == 0 and (st.get("env") or {}).get("HER_OLD_SETTING") == "1", out[-300:])
    check("...next to her permission mode and the engine's hooks",
          (st.get("permissions") or {}).get("defaultMode") == "bypassPermissions" and "--engine-1.0.99" in json.dumps(st))

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "an update keeps everything the buyer set up"))
sys.exit(1 if fails else 0)
