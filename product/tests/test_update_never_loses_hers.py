#!/usr/bin/env python3
"""No update, however it goes, removes anything the buyer made. The release gate for that promise.

"Hers" is everything a creator sets up: the style packs she built (quick and recipe), a launch pack she changed in
place (it comes back as "My Butter"), her default pack and accent, what she taught the editor (learned preferences,
a named text animation), her favorites shelf and saved sounds, hand-mapped fonts, her brand kit and its Part B
edits (profile, look note, word list, hook defaults, headline font), her permission mode, a hook of her own in
.claude/settings.json, her local settings, keys, jobs, her own sound file, a hand edit to an engine builder, and a
line she added to CLAUDE.md. Each scenario below runs the REAL scripts/apply-update.py + post-update.py over a
fully customized install and compares all of it before and after:

  A  a normal update                             everything kept; nothing of hers "needs a hand" by mistake
  B  the updater killed partway (a power cut) at several points, then run again: everything kept
  C  the window closed / the app quit partway (SIGTERM, SIGHUP): the update puts itself back, then installs
  D  a killed update undone with --rollback instead: back exactly as she was, nothing of hers read from the
     half-replaced files
  E  --rollback after she built a pack, changed a pack and a setting, and edited an engine file SINCE the update:
     the packs and settings stay as she has them now, and the edited file is saved, never lost
  F  her .claude/settings.json was already broken: the update never writes an unreadable file, and hers is saved
  G  two updates in a row: everything survives both, her hooks and her My Butter are never doubled
  H  a buyer who changed nothing is not told she has changes
  I  the guards that keep this true for FUTURE releases: every hook the engine ships runs one of its registered
     hook scripts, every permission rule it ships is registered as the engine's, and every file an engine module
     keeps her things in is one the updater may never write

Run: python3 product/tests/test_update_never_loses_hers.py   (Windows: python)
"""
import ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _helpers(path):
    """The module-level helpers of another update test (its scenarios, which run inside `with` blocks, are left out)."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    keep = [n for n in tree.body if not isinstance(n, (ast.With, ast.If)) and not (
        isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Call)
        and getattr(n.value.func, "attr", getattr(n.value.func, "id", "")) in ("exit", "print"))]
    ns = {"__file__": path, "__name__": "helpers"}
    exec(compile(ast.Module(body=keep, type_ignores=[]), path, "exec"), ns)
    return ns


K = _helpers(os.path.join(ROOT, "product", "tests", "test_update_keeps_both.py"))
H = K["H"]
H["SHIPPED"] = H["SHIPPED"] + [".claude/hooks/onboarding-nudge.sh"]
check, write, rd, rjs, sh, same = H["check"], H["write"], H["rd"], H["rjs"], H["sh"], H["same"]
kc = K["kc"]
HER_LINE, HER_RULE, HER_DARK = K["HER_LINE"], K["HER_RULE"], K["HER_DARK"]
SETTINGS = os.path.join(".claude", "settings.json")
SAFE_ZONES = os.path.join("product", "safe_zones.py")
HER_HOOK = {"type": "command", "command": "bash .claude/hooks/her-own-hook.sh"}
HER_STOP = {"type": "command", "command": "say done"}

# Runs apply-update.py with shutil.copy2 wrapped: after LIMIT copies into the engine (copies into the backup folder
# do not count), the next one stops the process the way MODE says: kill = a power cut (nothing runs after it),
# TERM / HUP = the app quitting / the window closing (the updater receives the signal).
FAULT = r"""
import os, runpy, shutil, signal, sys
limit, mode, real, seen = int(os.environ["LIMIT"]), os.environ["MODE"], shutil.copy2, [0]
def copy2(src, dst, *a, **k):
    if "_update-backups" not in str(dst).replace(os.sep, "/").split("/"):
        seen[0] += 1
        if seen[0] == limit + 1:
            if mode == "kill":
                os._exit(9)
            os.kill(os.getpid(), getattr(signal, "SIG" + mode))
    return real(src, dst, *a, **k)
shutil.copy2 = copy2
script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
runpy.run_path(script, run_name="__main__")
"""


def update(dst, pkg, fault=None):
    cmd = [os.path.join(dst, "scripts", "apply-update.py"), pkg]
    if not fault:
        return sh(dst, *cmd)
    runner = os.path.join(os.path.dirname(dst), "fault.py")
    write(runner, FAULT)
    return sh(dst, runner, *cmd, env={**H["ENV"], "LIMIT": str(fault[0]), "MODE": fault[1]})


def version(dst):
    return (rjs(os.path.join(dst, "product.json")) or {}).get("version")


def settings(dst):
    return rjs(os.path.join(dst, SETTINGS)) or {}


def add_hers(dst):
    """Everything test_update_keeps_both customizes, plus a hook of her own (one inside the engine's own group, one
    of its own) and the script it runs."""
    K["edit_butter"](dst)
    sz = os.path.join(dst, SAFE_ZONES)
    lines = rd(sz).splitlines(keepends=True)
    lines.insert(1, HER_LINE)
    write(sz, "".join(lines))
    write(os.path.join(dst, "CLAUDE.md"), rd(os.path.join(dst, "CLAUDE.md")).replace("## Rules\n", "## Rules\n" + HER_RULE))
    st = settings(dst)
    st["hooks"]["SessionStart"][0]["hooks"].append(dict(HER_HOOK))
    st["hooks"]["Stop"] = [{"hooks": [dict(HER_STOP)]}]
    write(os.path.join(dst, SETTINGS), st)
    write(os.path.join(dst, ".claude", "hooks", "her-own-hook.sh"), "#!/bin/sh\necho hers\n")


def butter_dark(dst, name):
    return (H["_palette"](dst, name).get("PALETTE") or {}).get("dark")


def hers(dst):
    """Every customization, as the engine reads it (H's snapshot plus what this test adds)."""
    s = H["snapshot"](dst)
    hooks = json.dumps(settings(dst).get("hooks"))
    s["her hook, once"] = hooks.count("her-own-hook.sh") == 1
    s["her own Stop hook, once"] = hooks.count("say done") == 1
    s["her hook's script"] = os.path.exists(os.path.join(dst, ".claude", "hooks", "her-own-hook.sh"))
    s["her builder edit"] = HER_LINE in (rd(os.path.join(dst, SAFE_ZONES)) or "")
    s["her CLAUDE.md line"] = HER_RULE in (rd(os.path.join(dst, "CLAUDE.md")) or "")
    s["her edited Butter (in place before, My Butter after)"] = HER_DARK in (butter_dark(dst, "Butter"), butter_dark(dst, "My Butter"))
    return s


def pack(pkg, version_, states):
    """An update to `version_` the way make-update.py builds one: H's package (real engine changes in the files her
    settings live in, a new engine hook), the two extra shipped files, and an originals archive holding every
    earlier version in `states` ({version: {path: bytes}}) plus this one."""
    H["package"](pkg, version_)
    f = lambda rel: os.path.join(pkg, "files", rel)   # noqa: E731
    for rel in K["EXTRA"] + [".claude/hooks/onboarding-nudge.sh"]:
        os.makedirs(os.path.dirname(f(rel)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), f(rel))
    write(f("product/safe_zones.py"), rd(f("product/safe_zones.py")) + f"\n# engine change {version_}\n")
    man = rjs(os.path.join(pkg, "update.json"))
    man["files"] += [r for r in K["EXTRA"] + [".claude/hooks/onboarding-nudge.sh"] if r not in man["files"]]
    this = {rel: open(f(rel), "rb").read() for rel in man["files"]}
    allv = dict(states, **{version_: this})
    versions = {v: {r: hashlib.sha256(d).hexdigest() for r, d in st.items()} for v, st in allv.items()}
    blobs = [(hashlib.sha256(d).hexdigest(), r, d) for st in allv.values() for r, d in st.items()]
    store = "_updates/history/engine-originals.tar.xz"
    kc.build_store(f(store), versions, blobs)
    man["files"].append(store)
    write(os.path.join(pkg, "update.json"), man)
    return this


def fresh(tmp, name, fonts, customize=True):
    """A v2.0.0 install, customized like a buyer's (or not), and the originals of what 2.0.0 shipped."""
    d = os.path.join(tmp, name)
    H["install"](d, "2.0.0")
    write(os.path.join(d, "product", "templates", "CLAUDE.engine.md"), H["ENGINE_DOC"].format(v="old"))
    shipped = K["shipped_state"](d)
    shipped[".claude/hooks/onboarding-nudge.sh"] = open(os.path.join(d, ".claude", "hooks", "onboarding-nudge.sh"), "rb").read()
    if customize:
        H["customize"](d, fonts, "cli")
        add_hers(d)
    return d, shipped


def needs_hand(dst):
    doc = rd(os.path.join(dst, "_local", "my-changes.md")) or ""
    return doc.split("**Needs a hand", 1)[1].split("\n**", 1)[0] if "**Needs a hand" in doc else ""


def tree(dst):
    """Every file's content hash, the backups aside, and the protected record of her settings aside: an update
    writes that record FIRST, before anything in the engine changes, so it is there even when nothing else is."""
    out = {}
    for d, dirs, files in os.walk(dst):
        dirs[:] = [x for x in dirs if x not in ("_update-backups", "__pycache__")]
        for fn in files:
            p = os.path.join(d, fn)
            rel = os.path.relpath(p, dst).replace(os.sep, "/")
            if rel == "_local/kept-settings.json":
                continue
            with open(p, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


def diff(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


with tempfile.TemporaryDirectory() as tmp:
    fonts = os.path.join(tmp, "her-fonts")
    for fn in ("Sunday-Display.otf", "Sunday-Text.ttf", "Sunday-Hand.otf"):
        write(os.path.join(fonts, fn), "font " + fn)
    ENV_HOOK = {**H["ENV"], "HOME": os.path.join(tmp, "home")}   # the hook links /studio under HOME: never the real one

    print("\nA. a normal update")
    a, st0 = fresh(tmp, "a", fonts)
    before = hers(a)
    check("every customization is in place before the update", all(before.values()), before)
    pkg1 = os.path.join(tmp, "pkg-2.0.1")
    st1 = pack(pkg1, "2.0.1", {"2.0.0": st0})
    rc, out = update(a, pkg1)
    check("the update ran cleanly", rc == 0 and "Done. You're now on v2.0.1." in out, out[-1500:])
    same("everything of hers survived", before, hers(a))
    check("the engine's own changes arrived too", all(H["arrived"](a, "2.0.1").values()), H["arrived"](a, "2.0.1"))
    check("her hook sits beside the engine's own, which arrived in the new version's form",
          "--engine-2.0.1" in json.dumps(settings(a).get("hooks")))
    check("nothing is left 'needing a hand' when it is already back (her settings, hooks, packs)",
          not needs_hand(a).strip(), needs_hand(a))
    check("the record keeps what it did with her settings and hooks",
          "your own settings and hooks are back" in (rd(os.path.join(a, "_local", "my-changes.md")) or ""))
    inc = rjs(os.path.join(a, "_update-backups", [n for n in os.listdir(os.path.join(a, "_update-backups"))
                                                 if n.startswith("v2.0.0-to-v2.0.1")][0], "incoming.json")) or {}
    check("the update wrote down what each file it wrote looks like, merges included, for a later undo",
          inc.get("to") == "2.0.1" and inc.get("files", {}).get("product/safe_zones.py")
          == hashlib.sha256(open(os.path.join(a, SAFE_ZONES), "rb").read()).hexdigest(), inc.get("files", {}).get("product/safe_zones.py"))

    # The package lists every shipped file; the first several are scripts this update does not change, then come the
    # files her settings and packs live in. Cut points run from before the first file to after the ones that change.
    print("\nB. the updater killed partway (a power cut), then run again")
    for limit in (0, 6, 12, 14, 16):
        b, _ = fresh(tmp, f"b{limit}", fonts)
        before, t0 = hers(b), tree(b)
        rc, out = update(b, pkg1, fault=(limit, "kill"))
        if rc == 0:
            print(f"  (cut after {limit} files: the update finished before that point; nothing to test)")
            continue
        check(f"[cut after {limit}] it was cut off, and product.json still says v2.0.0", version(b) == "2.0.0", out[-400:])
        rc, hook = sh(b, "-c", "import subprocess, sys; sys.stdout.write(subprocess.run(['bash', '.claude/hooks/onboarding-nudge.sh'], "
                               "capture_output=True, text=True).stdout)", env=ENV_HOOK)
        check(f"[cut after {limit}] the next session is told plainly, before anything is built",
              "was stopped before it finished" in hook and "normal recovery, not a fault" in hook, hook[-600:])
        rc, out = update(b, pkg1)
        check(f"[cut after {limit}] running the update again puts the stopped one back first, then installs",
              rc == 0 and "was stopped before it finished" in out and "Done. You're now on v2.0.1." in out, out[-1500:])
        same(f"[cut after {limit}] everything of hers survived", before, hers(b))
        check(f"[cut after {limit}] the engine's own changes arrived", all(H["arrived"](b, "2.0.1").values()),
              H["arrived"](b, "2.0.1"))
        check(f"[cut after {limit}] nothing wrongly left needing a hand", not needs_hand(b).strip(), needs_hand(b))

    print("\nC. the window closed / the app quit partway: the update puts itself back")
    for mode in ("TERM", "HUP"):
        c, _ = fresh(tmp, f"c{mode}", fonts)
        before, t0 = hers(c), tree(c)
        rc, out = update(c, pkg1, fault=(13, mode))
        check(f"[SIG{mode}] it stops, says so plainly, and never says it is done",
              rc != 0 and "did not finish: it was stopped" in out and "Done." not in out and "Traceback" not in out, out[-800:])
        check(f"[SIG{mode}] the engine is exactly as it was", tree(c) == t0, diff(tree(c), t0))
        rc, out = update(c, pkg1)
        check(f"[SIG{mode}] the next update installs", rc == 0 and version(c) == "2.0.1", out[-800:])
        same(f"[SIG{mode}] everything of hers survived", before, hers(c))

    print("\nD. a killed update undone with --rollback instead of run again")
    d, _ = fresh(tmp, "d", fonts)
    before, t0 = hers(d), tree(d)
    rc, out = update(d, pkg1, fault=(13, "kill"))
    check("it was cut off partway, with some of her files already replaced", rc != 0 and version(d) == "2.0.0"
          and tree(d) != t0, [rc, version(d), diff(tree(d), t0)[:5]])
    rc, out = sh(d, "scripts/apply-update.py", "--rollback")
    check("--rollback puts it back, and says it had been stopped", rc == 0 and "had been stopped" in out, out[-800:])
    check("the engine is exactly as it was before the update started", tree(d) == t0, diff(tree(d), t0))
    same("everything of hers is as it was", before, hers(d))

    print("\nE. --rollback after she made more things SINCE the update")
    e, _ = fresh(tmp, "e", fonts)
    rc, out = update(e, pkg1)
    check("the update ran", rc == 0, out[-800:])
    rc, out = sh(e, "product/pack_recipe.py", "--name", "After Pack", "--main", "Clash Display", "--caption", "Inter",
                 "--accent", "Caveat", "--primary", "#2E6BE8", "--secondary", "#F5C518", "--mood", "calm", "--write")
    check("she built a pack after the update", rc == 0, out[-400:])
    spj = os.path.join(e, "product", "creative-vault", "style-packs.json")
    sp = rjs(spj)
    sp["packs"]["Sunrise"]["accent_color"] = "#ABCDEF"                    # ...and changed one she already had
    write(spj, sp)
    st = settings(e)
    st.setdefault("permissions", {})["defaultMode"] = "acceptEdits"      # ...and changed her permission mode
    write(os.path.join(e, SETTINGS), st)
    write(os.path.join(e, SAFE_ZONES), rd(os.path.join(e, SAFE_ZONES)) + "# her later note\n")   # ...and an engine file
    check("the update refreshed the instructions in CLAUDE.md", "engine rule 2.0.1" in rd(os.path.join(e, "CLAUDE.md")))
    write(os.path.join(e, "CLAUDE.md"), rd(os.path.join(e, "CLAUDE.md")) + "- her later rule: always a clap\n")   # ...and a rule
    rc, out = sh(e, "scripts/apply-update.py", "--rollback")
    check("the undo runs", rc == 0 and "Rolled back v2.0.1 -> v2.0.0" in out and version(e) == "2.0.0", out[-1200:])
    live = (rjs(spj) or {}).get("packs", {})
    check("the pack she built after the update is still here", "After Pack" in live, sorted(live))
    rc2, out2 = sh(e, "-c", "import sys; sys.path.insert(0,'product'); import stylepack; stylepack.load('After Pack')")
    check("...and it builds", rc2 == 0, out2[-300:])
    check("the pack she changed after the update keeps her latest change", (live.get("Sunrise") or {}).get("accent_color") == "#ABCDEF",
          (live.get("Sunrise") or {}).get("accent_color"))
    check("her permission mode is the one she set after the update",
          (settings(e).get("permissions") or {}).get("defaultMode") == "acceptEdits", settings(e).get("permissions"))
    check("her own hooks are still there, once each", json.dumps(settings(e).get("hooks")).count("her-own-hook.sh") == 1
          and json.dumps(settings(e).get("hooks")).count("say done") == 1)
    saved = [os.path.join(dp, fn) for dp, _d, fs in os.walk(os.path.join(e, "_local", "my-changes"))
             for fn in fs if fn == "safe_zones.py" and "rolled-back" in dp]
    check("the engine file she edited after the update is saved before the older copy went back",
          len(saved) == 1 and "# her later note" in (rd(saved[0]) or ""), saved)
    check("...and the undo says where", "saved in _local/my-changes/after-v2.0.1-rolled-back-" in out and "product/safe_zones.py" in out, out[-900:])
    check("her builder edit from before the update is in place again", HER_LINE in (rd(os.path.join(e, SAFE_ZONES)) or ""))
    cm = rd(os.path.join(e, "CLAUDE.md")) or ""
    check("CLAUDE.md has the earlier version's engine instructions again",
          "engine rule old" in cm and "engine rule 2.0.1" not in cm, cm[-400:])
    check("...with her profile, look note and her own line from before the update",
          K["H"]["HER_PROFILE"].strip() in cm and K["H"]["HER_LOOK"] in cm and HER_RULE in cm, cm[-600:])
    check("...and the rule she added after the update", "- her later rule: always a clap" in cm, cm[-400:])
    check("...and the undo says so", "engine instructions in CLAUDE.md are the earlier version's" in out, out[-900:])

    print("\nE2. --rollback right after an update, CLAUDE.md untouched since")
    e2, _ = fresh(tmp, "e2", fonts)
    cm_before = rd(os.path.join(e2, "CLAUDE.md"))
    rc, out = update(e2, pkg1)
    rc, out = sh(e2, "scripts/apply-update.py", "--rollback")
    check("CLAUDE.md is exactly what she had before the update", rc == 0 and rd(os.path.join(e2, "CLAUDE.md")) == cm_before,
          out[-600:])

    print("\nF. her .claude/settings.json was already broken")
    f_, _ = fresh(tmp, "f", fonts)
    broken = rd(os.path.join(f_, SETTINGS)).rstrip().rstrip("}") + ',\n  "oops": \n}\n'
    write(os.path.join(f_, SETTINGS), broken)
    rc, out = update(f_, pkg1)
    check("the update still installs", rc == 0 and version(f_) == "2.0.1", out[-800:])
    try:
        json.loads(rd(os.path.join(f_, SETTINGS)))
        readable = True
    except ValueError:
        readable = False
    check("the settings file it leaves is readable (never a merge of a broken one)", readable, rd(os.path.join(f_, SETTINGS))[-300:])
    check("her broken copy is saved exactly as it was, and listed for her",
          any(rd(os.path.join(dp, fn)) == broken for dp, _d, fs in os.walk(os.path.join(f_, "_local", "my-changes"))
              for fn in fs if fn == "settings.json") and "could not be read" in needs_hand(f_), needs_hand(f_))

    print("\nG. two updates in a row")
    g, st0g = fresh(tmp, "g", fonts)
    before = hers(g)
    pkg_g1 = os.path.join(tmp, "pkg-g-2.0.1")
    st1g = pack(pkg_g1, "2.0.1", {"2.0.0": st0g})
    rc, out = update(g, pkg_g1)
    check("the first update ran", rc == 0, out[-800:])
    time.sleep(1.1)                                   # backup folders are named to the second
    pkg_g2 = os.path.join(tmp, "pkg-g-2.0.2")
    pack(pkg_g2, "2.0.2", {"2.0.0": st0g, "2.0.1": st1g})
    rc, out = update(g, pkg_g2)
    check("the second update ran", rc == 0 and version(g) == "2.0.2", out[-1200:])
    same("everything of hers survived both", before, hers(g))
    live = (rjs(os.path.join(g, "product", "creative-vault", "style-packs.json")) or {}).get("packs", {})
    check("her My Butter is there once, not doubled", "My Butter" in live and "My Butter 2" not in live, sorted(live))
    check("the engine's own changes of the second update arrived", all(H["arrived"](g, "2.0.2").values()), H["arrived"](g, "2.0.2"))

    print("\nH. a buyer who changed nothing")
    h_, st0h = fresh(tmp, "h", fonts, customize=False)
    pkg_h = os.path.join(tmp, "pkg-h")
    pack(pkg_h, "2.0.1", {"2.0.0": st0h})
    rc, out = update(h_, pkg_h)
    check("the update ran", rc == 0, out[-800:])
    check("she is not told she has changes", "your changes:" not in out
          and not os.path.exists(os.path.join(h_, "_local", "my-changes.md")), out[-800:])

    print("\nJ. an update that replaces only ONE of the two pack files")
    for only, other in (("product/pack_palettes.py", "product/creative-vault/style-packs.json"),
                        ("product/creative-vault/style-packs.json", "product/pack_palettes.py")):
        j, st0j = fresh(tmp, "j-" + os.path.basename(only), fonts)
        before = hers(j)
        pkg_j = os.path.join(tmp, "pkg-j-" + os.path.basename(only))
        pack(pkg_j, "2.0.1", {"2.0.0": st0j})
        man = rjs(os.path.join(pkg_j, "update.json"))
        man["files"] = [r for r in man["files"] if r != other]          # this release did not touch that file
        os.remove(os.path.join(pkg_j, "files", *other.split("/")))
        if only.endswith("pack_palettes.py"):                          # a colour tweak to a launch pack, alone
            pp = os.path.join(pkg_j, "files", *only.split("/"))
            src = rd(pp)
            m = re.search(r'"Butter":\s*\{[^}]*\}', re.search(r'^PALETTE = \{.*?^\}', src, re.S | re.M).group(0))
            write(pp, src.replace(m.group(0), re.sub(r'("muted":\s*")#[0-9A-Fa-f]{6}', r"\g<1>#5A5A5A", m.group(0), count=1)))
        write(os.path.join(pkg_j, "update.json"), man)
        rc, out = update(j, pkg_j)
        tag = f"[{os.path.basename(only)} alone]"
        check(f"{tag} the update ran", rc == 0 and version(j) == "2.0.1", out[-800:])
        after = hers(j)
        same(f"{tag} everything of hers survived (her packs' colours included)", before, after)
        check(f"{tag} her recipe pack has all six colour entries, exactly as before",
              H["_palette"](j, "Sunrise") == before["recipe pack palette"], H["_palette"](j, "Sunrise"))
        doc = rd(os.path.join(j, "_local", "my-changes.md")) or ""
        check(f"{tag} the record never calls a pack 'in place' that is missing colours", "not in place yet" not in doc, doc[-600:])

print("\nI. the guards that keep this true for future releases")
sys.path.insert(0, os.path.join(ROOT, "product"))
import settings_persist as sp_mod                                   # noqa: E402
shipped = json.load(open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8"))
check("every hook the engine ships runs one of its registered hook scripts, and every permission rule it ships is "
      "registered as the engine's (settings_persist.ENGINE_HOOK_SCRIPTS / ENGINE_PERMISSIONS), so an update never "
      "mistakes one for hers", sp_mod._theirs(shipped) == {}, sp_mod._theirs(shipped))
running = {os.path.basename(m) for m in re.findall(r"\.claude/hooks/([\w.-]+\.sh)", json.dumps(shipped))}
check("every hook script the shipped settings run is registered", running <= set(sp_mod.ENGINE_HOOK_SCRIPTS),
      sorted(running - set(sp_mod.ENGINE_HOOK_SCRIPTS)))
spec = importlib.util.spec_from_file_location("apply_update", os.path.join(ROOT, "scripts", "apply-update.py"))
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)
stores = {}
for mod, attrs in (("pack_persist", ("SIDECAR", "USER_STYLE")), ("learned", ("STORE",)), ("settings_persist", ("SIDECAR",)),
                   ("favorites", ("STATE",)), ("capcut_font_doctor", ("OVERRIDES",))):
    try:
        m = importlib.import_module(mod)
    except Exception as exc:   # noqa: BLE001
        check(f"{mod} can be read for its stores", False, exc)
        continue
    for attr in attrs:
        stores[f"{mod}.{attr}"] = os.path.relpath(getattr(m, attr), ROOT).replace(os.sep, "/")
stores["text_effects (named animations)"] = "product/creative-vault/user-effects.json"
unprotected = {k: v for k, v in stores.items() if not au.is_protected(v)}
check("every file an engine module keeps her things in is one the updater may never write", not unprotected, unprotected)
for rel in ("brand-kit.md", "CLAUDE.md", ".env", ".mcp.json", "config.json", ".claude/settings.local.json",
            "/".join(("projects", "her-reel", "raw", "take.mov")), "_local/sounds/soft-click.mp3"):
    check(f"...and so is {rel}", au.is_protected(rel))

fails = H["fails"]
print("\n" + ("FAILED: " + "; ".join(fails) if fails else "no update, however it goes, removes anything she made"))
sys.exit(1 if fails else 0)
