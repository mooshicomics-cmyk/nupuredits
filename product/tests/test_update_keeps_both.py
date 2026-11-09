#!/usr/bin/env python3
"""Every kind of thing a buyer keeps, through ONE real update: the protected copies (her style packs, her
settings inside shipped files, her own files) AND keep_changes (her hand edits to engine files, a shipped
pack she edited in place coming back as "My Butter", her own lines in CLAUDE.md).

The two halves were built separately and meet in post-update.py: packs and settings are put back first,
then keep_changes merges what is left. Run apart, each passed its own test while nothing checked that they
agree; this runs them together, and checks the record she reads says what actually happened (nothing left
"needing a hand" or reported removed when it is already back).

Reuses the helpers of test_update_keeps_buyer_data.py (install / customize / package / snapshot / arrived),
adds keep_changes.py and a builder to the shipped set, and packs a real originals archive
(keep_changes.build_store) into the update, the way make-update.py does.

Run: python3 product/tests/test_update_keeps_both.py   (Windows: python)
"""
import ast, hashlib, importlib.util, json, os, re, shutil, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TEST = os.path.join(ROOT, "product", "tests", "test_update_keeps_buyer_data.py")
src = open(TEST, encoding="utf-8").read()
tree = ast.parse(src)
keep = [n for n in tree.body if not isinstance(n, (ast.With, ast.If)) and not (
    isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Call)
    and getattr(n.value.func, "attr", getattr(n.value.func, "id", "")) in ("exit", "print"))]
H = {"__file__": TEST, "__name__": "helpers"}
exec(compile(ast.Module(body=keep, type_ignores=[]), TEST, "exec"), H)
H["ROOT"] = ROOT
check, write, rd, rjs, sh = H["check"], H["write"], H["rd"], H["rjs"], H["sh"]
EXTRA = ["product/keep_changes.py", "product/safe_zones.py"]
H["SHIPPED"] = H["SHIPPED"] + EXTRA

spec = importlib.util.spec_from_file_location("kc", os.path.join(ROOT, "product", "keep_changes.py"))
kc = importlib.util.module_from_spec(spec); spec.loader.exec_module(kc)

HER_LINE = "# her note: keep every caption two lines at most\n"
HER_RULE = "- her rule: every reel ends on a clap\n"
HER_DARK = "#7A1F3D"


def shipped_state(dst):
    """{rel: bytes} of what the engine shipped into this install (before she touched anything)."""
    out = {}
    for rel in H["SHIPPED"] + ["product/templates/CLAUDE.engine.md", "CLAUDE.md"] + sorted(H["ENGINE_SOUNDS"]):
        p = os.path.join(dst, rel)
        if os.path.isfile(p):
            out[rel] = open(p, "rb").read()
    return out


def edit_butter(dst):
    pp = os.path.join(dst, "product", "pack_palettes.py")
    s = rd(pp)
    m = re.search(r'^PALETTE = \{.*?^\}', s, re.S | re.M)
    block = m.group(0)
    bm = re.search(r'"Butter":\s*\{[^}]*\}', block)
    assert bm, "Butter is not in PALETTE"
    new_b = re.sub(r'("dark":\s*")#[0-9A-Fa-f]{6}(")', r"\g<1>" + HER_DARK + r"\2", bm.group(0), count=1)
    assert new_b != bm.group(0), "Butter has no dark colour to edit"
    write(pp, s.replace(bm.group(0), new_b))


def build_package(pkg, version, a_state):
    H["package"](pkg, version)
    f = lambda rel: os.path.join(pkg, "files", rel)
    for rel in EXTRA:                                  # the two extra shipped files, one with an engine change
        os.makedirs(os.path.dirname(f(rel)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), f(rel))
    write(f("product/safe_zones.py"), rd(f("product/safe_zones.py")) + f"\n# engine change {version}\n")
    man = rjs(os.path.join(pkg, "update.json"))
    man["files"] += [r for r in EXTRA if r not in man["files"]]
    b_state = {rel: open(f(rel), "rb").read() for rel in man["files"]}
    versions = {"2.0.0": {r: hashlib.sha256(d).hexdigest() for r, d in a_state.items()},
                version: {r: hashlib.sha256(d).hexdigest() for r, d in b_state.items()}}
    blobs = [(hashlib.sha256(d).hexdigest(), r, d) for st in (a_state, b_state) for r, d in st.items()]
    store = "_updates/history/engine-originals.tar.xz"
    kc.build_store(f(store), versions, blobs)
    man["files"].append(store)
    write(os.path.join(pkg, "update.json"), man)


with tempfile.TemporaryDirectory() as tmp:
    fonts = os.path.join(tmp, "her-fonts")
    for fn in ("Sunday-Display.otf", "Sunday-Text.ttf", "Sunday-Hand.otf"):
        write(os.path.join(fonts, fn), "font " + fn)

    print("\nA. fully customized install + hand edits + an edited Butter, through the current updater")
    a, pkg = os.path.join(tmp, "a"), os.path.join(tmp, "pkg")
    H["install"](a, "2.0.0")
    write(os.path.join(a, "product", "templates", "CLAUDE.engine.md"), H["ENGINE_DOC"].format(v="old"))
    a_state = shipped_state(a)
    H["customize"](a, fonts, "cli")
    edit_butter(a)
    sz = os.path.join(a, "product", "safe_zones.py")
    lines = rd(sz).splitlines(keepends=True)
    lines.insert(1, HER_LINE)
    write(sz, "".join(lines))
    write(os.path.join(a, "CLAUDE.md"), rd(os.path.join(a, "CLAUDE.md")).replace("## Rules\n", "## Rules\n" + HER_RULE))
    before = H["snapshot"](a)
    check("every customization is in place before the update", all(before.values()), before)
    build_package(pkg, "2.0.1", a_state)
    rc, out = sh(a, os.path.join(a, "scripts", "apply-update.py"), pkg)
    check("the update ran cleanly", rc == 0, out[-1500:])
    H["same"]("every customization survived (packs, settings, prefs, files)", before, H["snapshot"](a))
    got = H["arrived"](a, "2.0.1")
    check("the engine's own changes arrived", all(got.values()), got)
    szt = rd(sz)
    check("her hand edit to a builder came through", HER_LINE in szt)
    check("... on top of the update's own change to that file", "# engine change 2.0.1" in szt)
    sp = rjs(os.path.join(a, "product", "creative-vault", "style-packs.json"))
    pal = H["_palette"](a, "My Butter")
    check("her edited Butter is saved as her own pack, My Butter", "My Butter" in sp["packs"]
          and (pal.get("PALETTE") or {}).get("dark") == HER_DARK, [sorted(sp["packs"]), pal.get("PALETTE")])
    check("Butter itself is the shipped one again", (H["_palette"](a, "Butter").get("PALETTE") or {}).get("dark") != HER_DARK)
    up = rjs(os.path.join(a, "product", "creative-vault", "user-packs.json")) or {}
    check("My Butter is in the protected copy, so the next update keeps it", "My Butter" in (up.get("packs") or {}))
    cm = rd(os.path.join(a, "CLAUDE.md"))
    check("her own CLAUDE.md line came through the refresh", HER_RULE in cm)
    check("the refresh brought the new engine rules", "engine rule 2.0.1" in cm)
    doc = rd(os.path.join(a, "_local", "my-changes.md")) or ""
    check("_local/my-changes.md was written", bool(doc), out[-800:])
    check("it names My Butter", "My Butter" in doc)
    check("it lists the builder edit as come through", "product/safe_zones.py" in doc.split("**Needs a hand")[0])
    needs = doc.split("**Needs a hand", 1)[1].split("\n**", 1)[0] if "**Needs a hand" in doc else ""
    check("nothing is wrongly left 'needing a hand' (settings/packs are already back)", not needs.strip(), needs)
    check("nothing is wrongly reported as removed", "No longer part of the engine" not in doc, doc[-1200:])
    h1 = H["tree_hash"](a)
    rc, out2 = sh(a, "scripts/post-update.py")
    h2 = H["tree_hash"](a)
    check("running the finishing step again changes nothing", rc == 0 and h1 == h2,
          [k for k in set(h1) | set(h2) if h1.get(k) != h2.get(k)])

    print("\nB. her default WAS the Butter she edited: it moves to My Butter")
    b, pkg2 = os.path.join(tmp, "b"), os.path.join(tmp, "pkg2")
    H["install"](b, "2.0.0")
    write(os.path.join(b, "product", "templates", "CLAUDE.engine.md"), H["ENGINE_DOC"].format(v="old"))
    b_state = shipped_state(b)
    edit_butter(b)
    write(os.path.join(b, "product", "creative-vault", "user-style.json"), {"default_pack": "Butter", "history": [None]})
    build_package(pkg2, "2.0.1", b_state)
    rc, out = sh(b, os.path.join(b, "scripts", "apply-update.py"), pkg2)
    check("the update ran cleanly", rc == 0, out[-1200:])
    us = rjs(os.path.join(b, "product", "creative-vault", "user-style.json")) or {}
    check("her default is now My Butter", us.get("default_pack") == "My Butter", us)
    rc, out = sh(b, "-c", "import sys; sys.path.insert(0,'product'); import stylepack; stylepack.load('My Butter')")
    check("My Butter builds", rc == 0, out[-400:])

fails = H["fails"]
print("\n" + ("FAILED: " + "; ".join(fails) if fails else "both protections hold together in one update"))
sys.exit(1 if fails else 0)
