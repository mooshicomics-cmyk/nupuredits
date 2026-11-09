#!/usr/bin/env python3
"""test_pack_tools_fixes.py — her own style pack can be replaced, tweaked, and use a variable font.

Three faults from one creator building and reworking her own pack:

1. Replacing a pack (`pack_write.py --force`, and frame_to_pack.py --write --force, which goes through the same
   writer) APPENDED its pack_palettes.py entries instead of replacing them: every --force doubled her six
   lines, and the old values stayed in the file next to the new ones. The tools still said "verified".
2. `pack_write.py --set elements.<role>.<field>=...` (the form its own help suggests) crashed with
   "'list' object has no attribute 'setdefault'": any key starting with `elements` went to the palette's
   element LIST. A role name now goes to the pack block; `elements.<n>.<field>` still reaches the list.
3. A CapCut font whose filename holds brackets (a variable font, SourceSerif4[opsz,wght].ttf) is written to
   CapCut's userFontData wrapped in double quotes. The quotes were kept, the path never existed, and the font
   doctor said the font was not downloaded even after she had used it in CapCut.

Everything runs on scratch copies; the shipped files are never written.

Run:  python3 product/tests/test_pack_tools_fixes.py
"""
import ast
import importlib.util
import json
import os
import shutil
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(PRODUCT, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def entries_for(path, name):
    """How many times `name` is a key in each top-level dict of pack_palettes.py (by AST, not by text)."""
    counts = {}
    for node in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    counts[t.id] = sum(1 for k in node.value.keys
                                       if isinstance(k, ast.Constant) and k.value == name)
    return counts


def pack_part():
    pw = load("pack_write")
    tmp = tempfile.mkdtemp(prefix="pack-tools-")
    try:
        packs = os.path.join(tmp, "style-packs.json")
        pal = os.path.join(tmp, "pack_palettes.py")
        shutil.copy(pw.PACKS_JSON, packs)
        shutil.copy(pw.PALETTES, pal)
        pw.PACKS_JSON, pw.PALETTES = packs, pal
        pp = pw._persist()                    # its protected copy goes to the scratch folder too, never the real one
        pp.SIDECAR, pp.PACKS_JSON, pp.PALETTES = os.path.join(tmp, "user-packs.json"), packs, pal
        pp.BACKUPS = os.path.join(tmp, "_update-backups")

        cfg = json.load(open(packs, encoding="utf-8"))["packs"]
        base = next((k for k, v in cfg.items() if v.get("in_launch_kit")
                     and len(pw._persist().palette_entries_in(open(pal, encoding="utf-8").read(), k) or {})
                     == len(pw._DICTS)), None)
        check("there is a launch pack with a full palette to start from", base is not None)
        if base is None:
            return
        name = "Test Pack Fix"
        rc = pw.main(["--name", name, "--from", base])
        check("a new pack from a launch pack is written", rc == 0, rc)
        first = entries_for(pal, name)
        check("each palette dict holds the new pack once", all(first.get(d) == 1 for d in pw._DICTS), first)

        rc = pw.main(["--name", name, "--from", name, "--force", "--set", "palette.dark=#123456"])
        again = entries_for(pal, name)
        check("--force replaces her pack without error", rc == 0, rc)
        check("--force leaves each palette entry once, not doubled", all(again.get(d) == 1 for d in pw._DICTS), again)
        src = open(pal, encoding="utf-8").read()
        ent = pw._persist().palette_entries_in(src, name) or {}
        check("and the replaced entry carries the new value", "#123456" in str(ent.get("palette")), ent)
        compile(src, pal, "exec")
        for k in cfg:
            if k != name and cfg[k].get("in_launch_kit"):
                check(f"the launch pack {k} is untouched", entries_for(pal, k).get("PALETTE", 0) <= 1)

        # --set elements.<role>.<field> goes to the pack block, not the palette's element list.
        block = json.load(open(packs, encoding="utf-8"))["packs"][name]
        role = next(iter(block["elements"]))
        rc = pw.main(["--name", name, "--from", name, "--force", "--set", f"elements.{role}.case=upper"])
        check("--set elements.<role>.<field> does not crash", rc == 0, rc)
        after = json.load(open(packs, encoding="utf-8"))["packs"][name]
        check("and lands on that element in the pack block", after["elements"][role].get("case") == "upper",
              after["elements"][role])
        check("still once per palette dict after a third save", all(entries_for(pal, name).get(d) == 1 for d in pw._DICTS))

        # The palette list is still reachable by position, and a bad position is said, not crashed on.
        recipe = {"ground": "#fff", "hands_off_accent": "#000", "palette": {}, "treatment": {},
                  "elements": [{"color": "#111111"}], "card": {}}
        pw._set_values({"elements": {}}, recipe, ["elements.0.color=#222222"])
        check("elements.<n>.<field> still changes the palette's element list", recipe["elements"][0]["color"] == "#222222")
        try:
            pw._set_values({"elements": {}}, recipe, ["elements.7.color=#333333"])
            said = ""
        except pw.PackWriteError as e:
            said = str(e)
        check("a position past the end of the list is a plain refusal", "not a position" in said, said)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def font_part():
    cu = load("capcut_userfonts")
    tmp = tempfile.mkdtemp(prefix="userfonts-")
    try:
        real = os.path.join(tmp, "SourceSerif4[opsz,wght].ttf")
        open(real, "wb").close()
        plain = os.path.join(tmp, "Bloop.ttf")
        open(plain, "wb").close()
        ini = os.path.join(tmp, "userFontData")
        with open(ini, "w", encoding="utf-8") as fh:
            fh.write("[General]\n"
                     f'Source%20Serif%204="{real}"\n'
                     f"Bloop={plain}\n"
                     'Escaped="C:\\\\Fonts\\\\Odd \\"Name\\".ttf"\n')
        cu._USERFD = ini
        fonts = cu.load_user_fonts()
        check("a quoted path comes back without its quotes", fonts.get("source serif 4") == real, fonts)
        check("so the font is found", cu.resolve_font_file("Source Serif 4") == real)
        check("an unquoted path is unchanged", fonts.get("bloop") == plain, fonts)
        check("escaped backslashes and quotes inside a quoted value are undone",
              fonts.get("escaped") == 'C:\\Fonts\\Odd "Name".ttf', fonts.get("escaped"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    pack_part()
    font_part()
    if fails:
        print(f"test_pack_tools_fixes: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_pack_tools_fixes: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
