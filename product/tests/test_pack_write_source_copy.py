#!/usr/bin/env python3
"""test_pack_write_source_copy.py — in the copy the engine ships from, her own pack stays in _local.

`pack_write.py --name "<her pack>" --block - --force` in the seller's own engine wrote her personal pack into
the SHIPPED creative-vault/style-packs.json (and pack_palettes.py for a pack with a palette). make-ship
refuses to build on it, but the writer should never have put it there. That copy is told apart by
make-ship.sh at its root (make-ship never ships itself, so a buyer's copy never has it):

  * source copy: the pack goes to _local/style-packs.json, its palette to _local/pack-palettes.json; both
    shipped files stay byte-identical; nothing is recorded in user-packs.json; stylepack and pack_palettes
    both see the pack; --force, --from one of her _local packs, and removing it all stay in _local
  * buyer copy: unchanged — the pack goes into the shipped files and is recorded in user-packs.json, so it
    survives "update me"
  * a caller that points the writer at scratch copies (the other pack tests) is never treated as the source
    copy, so it can never write into a real _local

Everything runs in scratch engine trees; the real files are never written.

Run:  python3 product/tests/test_pack_write_source_copy.py
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
sys.path.insert(0, PRODUCT)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:400]) if detail else ''}")


FILES = ("product/pack_write.py", "product/pack_persist.py", "product/pack_palettes.py", "product/stylepack.py",
         "product/creative-vault/style-packs.json")
PACKS, PALETTES = "product/creative-vault/style-packs.json", "product/pack_palettes.py"
SIDECAR = "product/creative-vault/user-packs.json"
LOCAL_PACKS, LOCAL_PAL = "_local/style-packs.json", "_local/pack-palettes.json"


def tree(source):
    root = tempfile.mkdtemp(prefix="pack-src-" if source else "pack-buyer-")
    for rel in FILES:
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        shutil.copy2(os.path.join(ENGINE, rel), os.path.join(root, rel))
    if source:
        open(os.path.join(root, "make-ship.sh"), "w", encoding="utf-8").write("#!/usr/bin/env bash\n")
    return root


def run(root, *args, stdin=None):
    p = subprocess.run([sys.executable, os.path.join(root, "product", "pack_write.py"), *args], cwd=root,
                       input=stdin, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr


def py(root, code):
    p = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(root, "product"),
                       capture_output=True, text=True, encoding="utf-8")
    return p.stdout.strip() + p.stderr.strip()


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


def rd(root, rel):
    try:
        return json.load(open(os.path.join(root, rel), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def quick_block():
    packs = json.load(open(os.path.join(ENGINE, PACKS), encoding="utf-8"))["packs"]
    base = next(v for v in packs.values() if v.get("in_launch_kit"))
    block = json.loads(json.dumps(base))
    block["accent_color"] = "#A1B2C3"
    return json.dumps(block)


def source_part():
    root = tree(source=True)
    try:
        shipped = {rel: sha(os.path.join(root, rel)) for rel in (PACKS, PALETTES)}

        # a QUICK pack, the exact command that leaked: --block - --force
        rc, out = run(root, "--name", "Kitchen Calm Test", "--block", "-", "--force", stdin=quick_block())
        check("source: the quick pack saves", rc == 0, out)
        check("source: it says it went to _local", "_local/style-packs.json" in out, out)
        local = rd(root, LOCAL_PACKS) or {}
        check("source: the quick pack is in _local/style-packs.json",
              (local.get("packs") or {}).get("Kitchen Calm Test", {}).get("accent_color") == "#A1B2C3", local)

        # a pack WITH a palette, started from a shipped one
        rc, out = run(root, "--name", "Blush Test", "--from", "Butter", "--set", "palette.dark=#7A2E4A")
        check("source: the palette pack saves", rc == 0, out)
        pal = rd(root, LOCAL_PAL) or {}
        check("source: its palette is in _local/pack-palettes.json",
              (pal.get("PALETTE") or {}).get("Blush Test", {}).get("dark") == "#7A2E4A", pal)
        check("source: all six palette tables carry it",
              all("Blush Test" in (pal.get(d) or {}) for d in
                  ("GROUNDS", "HANDS_OFF_ACCENT", "PALETTE", "TREATMENTS", "PACK_ELEMENTS", "CARD_THEME")), pal)

        for rel, before in shipped.items():
            check(f"source: {rel} is byte-identical", sha(os.path.join(root, rel)) == before)
        check("source: nothing recorded in user-packs.json", not os.path.exists(os.path.join(root, SIDECAR)))

        # the engine's readers see both packs
        seen = py(root, "import stylepack, pack_palettes, json; print(json.dumps(["
                        "stylepack.load('Kitchen Calm Test')['accent_color'], "
                        "pack_palettes.PALETTE['Blush Test']['dark'], "
                        "pack_palettes.resolve_color('Blush Test', 'dark')]))")
        check("source: stylepack and pack_palettes read the _local packs",
              seen == json.dumps(["#A1B2C3", "#7A2E4A", "#7A2E4A"]), seen)

        # replacing it, and starting a new pack from one of hers, stay in _local too
        rc, out = run(root, "--name", "Blush Test", "--from", "Blush Test", "--set", "palette.dark=#5A1E3A",
                      "--force")
        check("source: --force from her own _local pack saves", rc == 0, out)
        pal = rd(root, LOCAL_PAL) or {}
        check("source: --force replaced the palette entry",
              (pal.get("PALETTE") or {}).get("Blush Test", {}).get("dark") == "#5A1E3A", pal)
        rc, out = run(root, "--name", "Blush Test", "--block", "-", stdin=quick_block())
        check("source: an existing name without --force is refused", rc == 1 and "already exists" in out, out)
        rc, out = run(root, "--name", "Butter", "--block", "-", "--force", stdin=quick_block())
        check("source: a launch pack name is still refused", rc == 1 and "LAUNCH" in out, out)

        out = py(root, "import pack_write; pack_write.remove_pack('Blush Test'); print('removed')")
        check("source: remove_pack runs", out.endswith("removed"), out)
        local, pal = rd(root, LOCAL_PACKS) or {}, rd(root, LOCAL_PAL) or {}
        check("source: removing takes it out of _local",
              "Blush Test" not in (local.get("packs") or {})
              and not any("Blush Test" in (t or {}) for t in pal.values()), (local, pal))
        check("source: removing left her other pack", "Kitchen Calm Test" in (local.get("packs") or {}), local)

        for rel, before in shipped.items():
            check(f"source: {rel} is still byte-identical at the end", sha(os.path.join(root, rel)) == before)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def buyer_part():
    root = tree(source=False)
    try:
        rc, out = run(root, "--name", "Sunday Test", "--block", "-", stdin=quick_block())
        check("buyer: the quick pack saves", rc == 0, out)
        packs = (rd(root, PACKS) or {}).get("packs") or {}
        check("buyer: it lands in the shipped style-packs.json, as before", "Sunday Test" in packs, list(packs))
        side = (rd(root, SIDECAR) or {}).get("packs") or {}
        check("buyer: it is recorded in user-packs.json, so an update keeps it", "Sunday Test" in side, side)
        check("buyer: the report says so", "user-packs.json" in out, out)

        rc, out = run(root, "--name", "Blush Test", "--from", "Butter", "--set", "palette.dark=#7A2E4A")
        check("buyer: the palette pack saves", rc == 0, out)
        src = open(os.path.join(root, PALETTES), encoding="utf-8").read()
        check("buyer: its palette lands in pack_palettes.py, as before", '"Blush Test"' in src)
        side = (rd(root, SIDECAR) or {}).get("packs") or {}
        check("buyer: the palette pack is recorded with its palette",
              (side.get("Blush Test", {}).get("palette") or {}).get("PALETTE", {}).get("dark") == "#7A2E4A", side)
        check("buyer: nothing goes to _local", not os.path.exists(os.path.join(root, "_local")))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def scratch_part():
    """The other pack tests point an in-process writer at scratch copies while running in the real engine:
    that must stay the buyer path, never the source copy (it would write the real _local)."""
    import pack_write as pw
    check("the real engine here is the source copy", pw.source_copy())
    tmp = tempfile.mkdtemp(prefix="pack-scratch-")
    saved = pw.PACKS_JSON
    try:
        pw.PACKS_JSON = os.path.join(tmp, "style-packs.json")
        check("a writer pointed at scratch copies is not the source copy", not pw.source_copy())
    finally:
        pw.PACKS_JSON = saved
        shutil.rmtree(tmp, ignore_errors=True)


real_local = {p: sha(os.path.join(ENGINE, p)) for p in (LOCAL_PACKS, LOCAL_PAL, PACKS, PALETTES)}
source_part()
buyer_part()
scratch_part()
for p, before in real_local.items():
    check(f"the real {p} was never touched", sha(os.path.join(ENGINE, p)) == before)

if fails:
    print(f"FAIL {len(fails)}/{total}")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print(f"PASS {total}/{total}  in the copy the engine ships from her pack stays in _local; a buyer's still survives updates")
