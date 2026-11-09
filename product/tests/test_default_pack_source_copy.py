#!/usr/bin/env python3
"""test_default_pack_source_copy.py — in the copy the engine ships from, her default pack stays in _local.

The visual editor's "Make <Pack> my default" (visual_editor.set_default_pack, POST /default-pack) and
cleanyap.set_default_pack wrote her default into product/creative-vault/user-style.json, a SHIPPED file. In the
seller's own engine that dirtied the tree and make-ship refused to build until it was set aside by hand. That
copy is told apart by make-ship.sh at its root (make-ship never ships itself, so a buyer's copy never has it):

  * source copy: both writers save to _local/default-pack.json; user-style.json stays byte-identical; every
    reader (cleanyap, superyap, the editor, layer_probe, learned, reel_recipe, trial_reels, pack_persist,
    build-reel-type, capcut-live, the carousel, pull-reels, separate_layers.sh) sees the new default
  * buyer copy: unchanged — the default goes into user-style.json (which updates protect), and no _local file
  * a caller pointed at a scratch user-style.json is never treated as the source copy

Everything runs in scratch engine trees (the real engine linked in, creative-vault copied); the real files
are never written.

Run:  python3 product/tests/test_default_pack_source_copy.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.dirname(PRODUCT)
SHIPPED = os.path.join("product", "creative-vault", "user-style.json")
LOCAL = os.path.join("_local", "default-pack.json")

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:400]) if detail else ''}")


def tree(source):
    """A scratch engine root: product/, workflows/ and pull-reels linked to the real engine, creative-vault
    copied (user-style.json as shipped: default_pack null), make-ship.sh only in the source copy."""
    root = tempfile.mkdtemp(prefix="defpack-src-" if source else "defpack-buyer-")
    os.makedirs(os.path.join(root, "product", "creative-vault"))
    for n in os.listdir(PRODUCT):
        if n not in ("creative-vault", "__pycache__", "tests"):
            os.symlink(os.path.join(PRODUCT, n), os.path.join(root, "product", n))
    cv = os.path.join(PRODUCT, "creative-vault")
    for n in os.listdir(cv):
        if n != "user-style.json":
            os.symlink(os.path.join(cv, n), os.path.join(root, "product", "creative-vault", n))
    with open(os.path.join(root, SHIPPED), "w", encoding="utf-8") as fh:
        json.dump({"_doc": "as shipped", "default_pack": None, "default_accent": None, "history": []}, fh, indent=2)
    for n in ("assets", "scripts"):
        os.symlink(os.path.join(ENGINE, n), os.path.join(root, n))
    os.makedirs(os.path.join(root, "workflows", "carousel"))
    os.symlink(os.path.join(ENGINE, "workflows", "capcut-live.py"), os.path.join(root, "workflows", "capcut-live.py"))
    for n in os.listdir(os.path.join(ENGINE, "workflows", "carousel")):
        if n != "__pycache__":
            os.symlink(os.path.join(ENGINE, "workflows", "carousel", n), os.path.join(root, "workflows", "carousel", n))
    pr = os.path.join(root, ".claude", "skills", "pull-reels", "scripts")
    os.makedirs(pr)
    os.symlink(os.path.join(ENGINE, ".claude", "skills", "pull-reels", "scripts", "cut-shorts.py"),
               os.path.join(pr, "cut-shorts.py"))
    if source:
        with open(os.path.join(root, "make-ship.sh"), "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env bash\n")
    return root


# Run inside the scratch tree: set a default through a writer, then ask every reader for it.
CHILD = r'''
import ast, io, json, os, sys, types, contextlib
root, writer, pack = sys.argv[1], sys.argv[2], sys.argv[3]
P = os.path.join(root, "product")
sys.path.insert(0, P)
try:
    import requests
except ImportError:                         # cleanyap imports it for VectCut; nothing here talks to VectCut
    sys.modules["requests"] = types.ModuleType("requests")

def func_from(path, fname, extra):
    """One function out of a script that does work at import (build-reel-type needs a JOB to load)."""
    src = open(path, encoding="utf-8").read()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == fname)
    ns = {"__file__": path, "os": os, "json": json, "sys": sys, **extra}
    exec(compile(ast.Module([node], []), path, "exec"), ns)
    return ns[fname]

import visual_editor as ve, cleanyap
if writer == "editor":
    ve.set_default_pack(pack)
else:
    cleanyap.set_default_pack(pack)

import superyap, layer_probe, learned, reel_recipe, trial_reels, pack_persist, user_style
out = {}
out["cleanyap"] = cleanyap.default_pack()
out["editor"] = ve._default_pack()
out["layer_probe"] = layer_probe._saved_pack()
out["learned"] = learned.context_for_build("yap").get("pack")
out["reel_recipe"] = reel_recipe._default_pack()
os.makedirs(os.path.join(root, "projects", "j"), exist_ok=True)
out["trial_reels"] = trial_reels._pack_of(os.path.join(root, "projects", "j"))
out["pack_persist"] = list(pack_persist.default_pack_status())
learned.set_context(pack=None); learned._CTX.pop("pack", None)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    superyap._pack_takeover_font()
out["superyap"] = pack if f"the {pack} pack" in buf.getvalue() else buf.getvalue()
out["build_reel_type"] = func_from(os.path.join(P, "build-reel-type.py"), "_saved_pack", {})()
# These three find the engine with Path.resolve(), which follows the scratch tree's links back to the real
# engine (and capcut-live loads macOS-only modules at import), so their reader runs against this root.
from pathlib import Path
R = Path(root)
out["capcut_live"] = func_from(str(R / "workflows" / "capcut-live.py"), "active_pack", {"REPO": R})()
out["carousel"] = func_from(str(R / "workflows" / "carousel" / "carousel.py"), "default_pack",
                            {"ENGINE": R, "packs": lambda: [pack]})()
out["cut_shorts"] = func_from(str(R / ".claude" / "skills" / "pull-reels" / "scripts" / "cut-shorts.py"), "saved_pack",
                              {"USER_STYLE": R / "product" / "creative-vault" / "user-style.json"})()
print("RESULT " + json.dumps(out))
'''


def run(root, writer, pack):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HOME=os.path.join(root, "home"), STYLE_PACK="")
    os.makedirs(env["HOME"], exist_ok=True)
    p = subprocess.run([sys.executable, "-c", CHILD, root, writer, pack], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=root)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")), None)
    if not line:
        return None, (p.stdout + p.stderr)[-1500:]
    return json.loads(line[len("RESULT "):]), ""


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def separate_layers_pack(root):
    """The pack separate_layers.sh resolves when none is named (it stops at 'which layers?' right after)."""
    p = subprocess.run(["bash", os.path.join(root, "product", "separate_layers.sh"), "some-job"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root)
    return p.stdout + p.stderr


def readers_agree(label, got, pack):
    for k, v in got.items():
        want = [pack, True] if k == "pack_persist" else pack
        check(f"{label}: {k} reads her default", v == want, v)


def main():
    import random
    random.seed(7)
    packs = json.load(open(os.path.join(PRODUCT, "creative-vault", "style-packs.json"), encoding="utf-8"))["packs"]
    names = [n for n in packs if n != "Butter"]
    one, two = (names + ["Butter", "Butter"])[:2]
    roots = []
    try:
        # ---- source copy: the editor's "Make it my default" ------------------------------------------------
        src = tree(True); roots.append(src)
        before = sha(os.path.join(src, SHIPPED))
        got, err = run(src, "editor", one)
        check("source copy (editor): the child ran", got is not None, err)
        check("source copy (editor): user-style.json is byte-identical", sha(os.path.join(src, SHIPPED)) == before)
        local = json.load(open(os.path.join(src, LOCAL), encoding="utf-8")) if os.path.exists(os.path.join(src, LOCAL)) else {}
        check("source copy (editor): saved to _local/default-pack.json", local.get("default_pack") == one, local)
        check("source copy (editor): the switch is kept in its history", local.get("history") == [None], local)
        if got:
            readers_agree("source copy (editor)", got, one)
        check("source copy: separate_layers.sh uses her default",
              f"separate_layers.sh --list some-job {one}" in separate_layers_pack(src), separate_layers_pack(src)[-400:])

        # ---- source copy: cleanyap.set_default_pack (homebase, the style-pack skill) ------------------------
        got, err = run(src, "cleanyap", two)
        check("source copy (cleanyap): the child ran", got is not None, err)
        check("source copy (cleanyap): user-style.json is byte-identical", sha(os.path.join(src, SHIPPED)) == before)
        local = json.load(open(os.path.join(src, LOCAL), encoding="utf-8"))
        check("source copy (cleanyap): _local holds the new default", local.get("default_pack") == two, local)
        check("source copy (cleanyap): history grows by one", local.get("history") == [None, one], local)
        if got:
            readers_agree("source copy (cleanyap)", got, two)

        # ---- a shipped file already dirtied by the old writer is read only as a fallback ------------------
        src2 = tree(True); roots.append(src2)
        with open(os.path.join(src2, SHIPPED), "w", encoding="utf-8") as fh:
            json.dump({"default_pack": two, "history": [None]}, fh)
        sys.path.insert(0, os.path.join(src2, "product"))
        try:
            import importlib
            import user_style
            importlib.reload(user_style)
            shipped2 = os.path.join(src2, SHIPPED)
            check("source copy: an old default in user-style.json still reads", user_style.default_pack(shipped2) == two)
            user_style.set_default_pack(one, shipped2)
            check("source copy: _local wins over user-style.json", user_style.default_pack(shipped2) == one)
            check("source copy: the old value seeds _local's history",
                  json.load(open(os.path.join(src2, LOCAL), encoding="utf-8")).get("history") == [two])
            # ---- a scratch user-style.json in the source copy is never the source copy --------------------
            scratch = os.path.join(src2, "tmp-test", "user-style.json")
            os.makedirs(os.path.dirname(scratch))
            user_style.set_default_pack(two, scratch)
            check("a scratch user-style.json is written in place", json.load(open(scratch, encoding="utf-8"))
                  .get("default_pack") == two)
            check("a scratch user-style.json never changes the real _local",
                  json.load(open(os.path.join(src2, LOCAL), encoding="utf-8")).get("default_pack") == one)
        finally:
            sys.path.remove(os.path.join(src2, "product"))

        # ---- buyer copy: unchanged -----------------------------------------------------------------------
        buyer = tree(False); roots.append(buyer)
        got, err = run(buyer, "editor", one)
        check("buyer copy: the child ran", got is not None, err)
        us = json.load(open(os.path.join(buyer, SHIPPED), encoding="utf-8"))
        check("buyer copy: the default goes into user-style.json", us.get("default_pack") == one, us)
        check("buyer copy: user-style.json keeps its other fields", us.get("_doc") == "as shipped" and
              "default_accent" in us, us)
        check("buyer copy: no _local/default-pack.json", not os.path.exists(os.path.join(buyer, LOCAL)))
        if got:
            readers_agree("buyer copy", got, one)
    finally:
        for r in roots:
            shutil.rmtree(r, ignore_errors=True)

    if fails:
        print(f"FAIL  {len(fails)} of {total} checks:")
        for f in fails:
            print("  ✗ " + f)
        sys.exit(1)
    print(f"PASS  {total} checks: in the source copy her default pack lives in _local and every reader sees it; "
          f"a buyer's copy is unchanged")


if __name__ == "__main__":
    main()
