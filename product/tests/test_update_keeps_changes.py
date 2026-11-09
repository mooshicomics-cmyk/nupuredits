#!/usr/bin/env python3
"""test_update_keeps_changes.py — an update keeps the changes she (or her Claude) made to the engine.

What used to happen: an update wrote the new version of every file it carries straight over hers, kept a
backup nobody would ever open, and her change was gone. A style pack built with "build my own style pack"
was written only into style-packs.json, never saved, and deleted. A shipped pack edited in place ("keep
Butter but make the blue pink") was silently reset. This builds a real OLD install with her edits in it,
applies a real update package through the real updater (one too old to know any of this, with no pack
protection at all), and checks each change came through, or was handed to her, and written down.

Run: python3 product/tests/test_update_keeps_changes.py
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
import keep_changes as kc   # noqa: E402

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-500:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


ENV = {**os.environ, "PYTHONUTF8": "1", "REELS_ENGINE_SKIP_BROWSER_ENSURE": "1"}
LINES = [f"value_{i} = {i}\n" for i in range(12)]


def text(lines):
    return "".join(lines)


def edit(lines, i, new):
    out = list(lines)
    out[i] = new
    return out


TPL_OLD = ("# CLAUDE.md\n\nEngine intro.\n\n## Brand Kit\n\n### Applied — <<NAME>>\n\n<<profile>>\n\n"
           "**⚠️ ASK THE REGISTER** at the graphics step.\n\n## Rules\n\n- Rule one.\n- Rule two.\n"
           "- Rule three.\n\n## Pipeline\n\n- Step one.\n- Step two.\n")
TPL_NEW = TPL_OLD.replace("- Step two.\n", "- Step two, now faster.\n")
HER_PROFILE = "### Applied — The Creator\n\nMoms in the middle. Big sister voice.\n\n"
HER_CLAUDE = (TPL_OLD.replace("### Applied — <<NAME>>\n\n<<profile>>\n\n", HER_PROFILE)
              .replace("- Rule two.\n", "- Rule two.\n- Always pink hooks (her rule).\n"))

BUTTER_BLOCK = {"vibe": "modern", "in_launch_kit": True, "accent_color": "#fdc341",
                "fonts": {"main": "Inter"}, "elements": {"headline": {"font": "Inter", "size": 25}}}
PALETTES = '''"""pack palettes (test copy)"""
GROUNDS = {
    "Butter": "#fffdd7",
}
HANDS_OFF_ACCENT = {
    "Butter": "#fdc341",
}
PALETTE = {
    "Butter": {"light": "#fffdd7", "dark": "#317ae1", "muted": "#5c91e6", "accent": "#fdc341", "pop2": "#fdc341"},
}
TREATMENTS = {
    "Butter": "pale lemon, cobalt ink",
}
PACK_ELEMENTS = {
    "Butter": {"card": "block"},
}
CARD_THEME = {
    "Butter": {"structure": "minimal"},
}
'''


def packs_json(extra=None, butter=None, treatment_note=None):
    b = dict(butter or BUTTER_BLOCK)
    if treatment_note:
        b["vibe"] = treatment_note
    d = {"_doc": "packs", "packs": {"Butter": b}}
    d["packs"].update(extra or {})
    return json.dumps(d, indent=1) + "\n"


def write(root, rel, data):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


SHIPPED_CODE = ["scripts/post-update.py", "scripts/merge-claude-md.py", "product/keep_changes.py",
                "product/pack_persist.py", "product/pack_write.py", "product/user_style.py"]


def main():
    print("an update keeps her changes\n")
    with tempfile.TemporaryDirectory() as tmp:
        buyer, pkg = os.path.join(tmp, "engine"), os.path.join(tmp, "pkg")
        # ---- v1.0.0 as shipped, and v1.0.1 as shipped ------------------------------------------------
        old = {
            "product/tool.py": text(LINES), "product/clash.py": text(LINES), "product/same.py": text(LINES),
            "product/removed.py": text(LINES), "product/untouched.py": text(LINES),
            "product/settings.json": json.dumps({"a": 1, "b": 1, "nested": {"x": 1}}, indent=2) + "\n",
            "product/templates/CLAUDE.engine.md": TPL_OLD, "CLAUDE.md": TPL_OLD,
            "product/creative-vault/style-packs.json": packs_json(),
            "product/pack_palettes.py": PALETTES,
            "assets/sound.bin": b"\x00\x01RIFF-shipped-sound\x00",
            "scripts/apply-update.py": open(os.path.join(ROOT, "scripts", "apply-update.py"), encoding="utf-8").read(),
            "scripts/merge-claude-md.py": open(os.path.join(ROOT, "scripts", "merge-claude-md.py"), encoding="utf-8").read(),
        }
        new = dict(old)
        del new["product/removed.py"]
        new["product/tool.py"] = text(edit(LINES, 8, "value_8 = 'eight, from the update'\n"))
        new["product/clash.py"] = text(edit(LINES, 3, "value_3 = 'the update's three'\n"))
        new["product/settings.json"] = json.dumps({"a": 1, "b": 3, "c": "new", "nested": {"x": 1}}, indent=2) + "\n"
        new["product/templates/CLAUDE.engine.md"] = TPL_NEW
        new["product/creative-vault/style-packs.json"] = packs_json(treatment_note="modern, refined")
        new["product/pack_palettes.py"] = PALETTES.replace('"pale lemon, cobalt ink"', '"pale lemon, cobalt ink, refined"')
        for rel in SHIPPED_CODE:
            new[rel] = open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()

        # ---- her install: v1.0.0 plus what she and her Claude changed ------------------------------
        for rel, data in old.items():
            write(buyer, rel, data)
        write(buyer, "product.json", json.dumps({"engine": "ai-edit-engine", "version": "1.0.0"}) + "\n")
        write(buyer, "product/tool.py", text(edit(LINES, 2, "value_2 = 'her two'\n")))
        write(buyer, "product/clash.py", text(edit(LINES, 3, "value_3 = 'her three'\n")))
        write(buyer, "product/same.py", text(edit(LINES, 5, "value_5 = 'her five'\n")))
        write(buyer, "product/removed.py", text(edit(LINES, 1, "value_1 = 'her one'\n")))
        write(buyer, "product/untouched.py", text(edit(LINES, 0, "value_0 = 'her zero'\n")))
        write(buyer, "product/settings.json", json.dumps({"a": 2, "b": 1, "mine": True, "nested": {"x": 1}}, indent=2) + "\n")
        write(buyer, "product/my_helper.py", "print('her own helper')\n")
        write(buyer, "assets/sound.bin", b"\x00\x02RIFF-her-own-sound\x00")
        write(buyer, "CLAUDE.md", HER_CLAUDE)
        her_pack = {"vibe": "her", "in_launch_kit": False, "accent_color": "#F4C2C2", "fonts": {"main": "Her Font"},
                    "elements": {"headline": {"font": "Her Font", "size": 25}}}
        her_butter = dict(BUTTER_BLOCK, accent_color="#C2527A")
        write(buyer, "product/creative-vault/style-packs.json", packs_json({"Ashlynne Pack": her_pack}, butter=her_butter))
        write(buyer, "product/pack_palettes.py", PALETTES.replace('"dark": "#317ae1"', '"dark": "#C2527A"'))
        write(buyer, "product/creative-vault/user-style.json", json.dumps({"default_pack": "Butter"}) + "\n")

        # ---- the update package: every file changed since the first release, plus the originals ----
        changed = [rel for rel in new if new[rel] != old.get(rel)] + ["product/same.py", "assets/sound.bin"]
        entries = []
        for rel in changed:
            data = new[rel]
            write(os.path.join(pkg, "files"), rel, data)
            entries.append({"path": rel, "sha256": sha(data)})
        blobs = [(sha(d), r, d.encode("utf-8")) for ver in (old, new) for r, d in ver.items() if isinstance(d, str)]
        store = os.path.join(pkg, "files", "_updates", "history", "engine-originals.tar.xz")
        stats = kc.build_store(store, {"1.0.0": {r: sha(d) for r, d in old.items()},
                                       "1.0.1": {r: sha(d) for r, d in new.items()}}, blobs)
        entries.append({"path": "_updates/history/engine-originals.tar.xz", "sha256": sha(open(store, "rb").read())})
        write(pkg, "update.json", json.dumps({"engine": "ai-edit-engine", "version": "1.0.1", "min_version": "1.0.0",
                                             "summary": "test", "changes": [], "files": entries,
                                             "deletes": ["product/removed.py"]}))
        check("the originals archive packs both versions", stats["versions"] == 2 and stats["originals"] > 5, stats)

        # ---- apply it with the updater already on her machine ---------------------------------------
        r = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "apply-update.py"), pkg],
                           capture_output=True, text=True, cwd=buyer, env=ENV, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        check("the update ran", r.returncode == 0 and "v1.0.1" in out, out)

        def read(rel):
            with open(os.path.join(buyer, rel), "rb") as fh:
                return fh.read()

        print("\n1. her edits come back on top of the new version")
        tool = read("product/tool.py").decode()
        check("her line and the update's line are both there", "'her two'" in tool and "'eight, from the update'" in tool, tool)
        check("a file the update did not change since her version: hers, exactly",
              read("product/same.py").decode() == text(edit(LINES, 5, "value_5 = 'her five'\n")))
        s = json.loads(read("product/settings.json"))
        check("JSON merges by key: her keys and the update's keys", s == {"a": 2, "b": 3, "c": "new", "mine": True, "nested": {"x": 1}}, s)
        check("a binary she replaced, which the update did not change: hers is back",
              read("assets/sound.bin") == b"\x00\x02RIFF-her-own-sound\x00")
        claude = read("CLAUDE.md").decode()
        check("CLAUDE.md: the new instructions arrived", "Step two, now faster" in claude, claude)
        check("CLAUDE.md: her profile is kept", "Moms in the middle" in claude)
        check("CLAUDE.md: her own rule is back", "Always pink hooks (her rule)" in claude, claude)

        print("\n2. where both changed the same lines, the new version stays and hers is saved")
        clash = read("product/clash.py").decode()
        check("the update's version is in place", "the update's three" in clash and "her three" not in clash)
        saved = os.path.join(buyer, "_local", "my-changes")
        runs = [d for d in os.listdir(saved) if os.path.isdir(os.path.join(saved, d))] if os.path.isdir(saved) else []
        check("one record for this update", len(runs) == 1, runs)
        run = os.path.join(saved, runs[0]) if runs else saved
        check("her version is saved", os.path.exists(os.path.join(run, "product", "clash.py")))
        diff = open(os.path.join(run, "product", "clash.py.diff"), encoding="utf-8").read() if os.path.exists(
            os.path.join(run, "product", "clash.py.diff")) else ""
        check("with exactly what she changed beside it", "+value_3 = 'her three'" in diff and "-value_3 = 3" in diff, diff)
        check("a file the update removed: hers is saved", os.path.exists(os.path.join(run, "product", "removed.py")))
        check("files she added are untouched", read("product/my_helper.py") == b"print('her own helper')\n")

        print("\n3. style packs")
        packs = json.loads(read("product/creative-vault/style-packs.json"))["packs"]
        check("her 'build my own style pack' pack is back (an old updater had deleted it)", "Ashlynne Pack" in packs, list(packs))
        check("the shipped Butter is the new one", packs.get("Butter", {}).get("vibe") == "modern, refined", packs.get("Butter"))
        check("her edited Butter is kept as her own pack, My Butter",
              packs.get("My Butter", {}).get("accent_color") == "#C2527A"
              and packs.get("My Butter", {}).get("in_launch_kit") is False, packs.get("My Butter"))
        pal = read("product/pack_palettes.py").decode()
        check("My Butter keeps her palette too", '"My Butter"' in pal and "#C2527A" in pal)
        style = json.loads(read("product/creative-vault/user-style.json"))
        check("and it is her default, as Butter was", style.get("default_pack") == "My Butter", style)
        sidecar = json.loads(read("product/creative-vault/user-packs.json"))["packs"]
        check("both are saved where the next update keeps them", {"Ashlynne Pack", "My Butter"} <= set(sidecar), list(sidecar))

        print("\n4. it is written down, and said out loud")
        doc = read("_local/my-changes.md").decode()
        for needle, what in (("product/tool.py", "a merged change"), ("Needs a hand (1)", "the collision"),
                             ("product/clash.py", "which file"), ("My Butter", "the pack it saved"),
                             ("Ashlynne Pack", "her pack"), ("product/untouched.py", "her other changes"),
                             ("product/my_helper.py", "files she added"), ("product/removed.py", "the removed file"),
                             ("bring my changes forward", "how to finish it")):
            check(f"the record names {what}", needle in doc, doc[:1200])
        check("the update output says so in one line", "your changes:" in out and "need" in out, out[-800:])

        print("\n5. running the finishing step again changes nothing")
        before = {rel: read(rel) for rel in ("product/tool.py", "CLAUDE.md", "product/creative-vault/style-packs.json",
                                             "_local/my-changes.md")}
        r2 = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "post-update.py")], capture_output=True,
                            text=True, cwd=buyer, env=ENV, encoding="utf-8", errors="replace")
        check("second run is clean", r2.returncode == 0, r2.stdout + r2.stderr)
        check("no file changed and the record was not doubled",
              all(read(rel) == data for rel, data in before.items()), r2.stdout)

        print("\n6. rollback still puts her exactly where she was")
        r3 = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "apply-update.py"), "--rollback"],
                            capture_output=True, text=True, cwd=buyer, env=ENV, encoding="utf-8", errors="replace")
        check("rollback ran", r3.returncode == 0, r3.stdout + r3.stderr)
        check("her own tool.py is back as she had it", read("product/tool.py").decode() == text(edit(LINES, 2, "value_2 = 'her two'\n")))
        check("the removed file is back", os.path.exists(os.path.join(buyer, "product", "removed.py")))

        print("\n8. an archive without her version merges nothing (a 1.x install handed a 2.x package)")
        # Without the exact original, the nearest shipped text is the NEW file itself, and merging against it
        # wrote her old copy back over the update; every untouched file also read as hers, and an untouched
        # Butter differs from every shipped Butter the archive holds, so it came back as a "My Butter".
        buyer2, pkg2 = os.path.join(tmp, "engine2"), os.path.join(tmp, "pkg2")
        for rel, data in old.items():
            write(buyer2, rel, data)
        write(buyer2, "product.json", json.dumps({"engine": "ai-edit-engine", "version": "1.0.0"}) + "\n")
        write(buyer2, "product/tool.py", text(edit(LINES, 2, "value_2 = 'her two'\n")))
        write(buyer2, "CLAUDE.md", HER_CLAUDE)
        entries2 = []
        for rel in changed:
            write(os.path.join(pkg2, "files"), rel, new[rel])
            entries2.append({"path": rel, "sha256": sha(new[rel])})
        store2 = os.path.join(pkg2, "files", "_updates", "history", "engine-originals.tar.xz")
        kc.build_store(store2, {"1.0.1": {r: sha(d) for r, d in new.items()}},
                       [(sha(d), r, d.encode("utf-8")) for r, d in new.items() if isinstance(d, str)])
        entries2.append({"path": "_updates/history/engine-originals.tar.xz", "sha256": sha(open(store2, "rb").read())})
        write(pkg2, "update.json", json.dumps({"engine": "ai-edit-engine", "version": "1.0.1", "min_version": "1.0.0",
                                              "summary": "test", "changes": [], "files": entries2, "deletes": []}))
        r4 = subprocess.run([sys.executable, os.path.join(buyer2, "scripts", "apply-update.py"), pkg2],
                            capture_output=True, text=True, cwd=buyer2, env=ENV, encoding="utf-8", errors="replace")
        out4 = r4.stdout + r4.stderr
        check("the update ran", r4.returncode == 0 and "v1.0.1" in out4, out4)

        def read2(rel):
            with open(os.path.join(buyer2, rel), "rb") as fh:
                return fh.read()

        check("the new version stays: her old copy is NOT written back over it",
              read2("product/tool.py").decode() == new["product/tool.py"], read2("product/tool.py").decode())
        packs2 = json.loads(read2("product/creative-vault/style-packs.json"))["packs"]
        check("no pack is adopted from a Butter she never touched", "My Butter" not in packs2, list(packs2))
        check("her own CLAUDE.md line still comes back (that merge uses the old template, not the archive)",
              "Always pink hooks (her rule)" in read2("CLAUDE.md").decode())
        doc2 = read2("_local/my-changes.md").decode() if os.path.exists(os.path.join(buyer2, "_local", "my-changes.md")) else ""
        check("the record says why nothing was merged", "do not include v1.0.0" in doc2, doc2[:600])
        check("... and lists none of her untouched files as changes", "Needs a hand" not in doc2
              and "product/untouched.py" not in doc2 and "Your other changes" not in doc2, doc2[:900])
        check("the update output says so in one line", "originals do not include your version" in out4, out4[-600:])

    print("\n7. the merges, on their own")
    b = ["a\n", "b\n", "c\n", "d\n", "e\n"]
    m, c = kc.merge3_lines(b, ["a\n", "B\n", "c\n", "d\n", "e\n"], ["a\n", "b\n", "c\n", "D\n", "e\n"])
    check("separate lines: both kept", m == ["a\n", "B\n", "c\n", "D\n", "e\n"] and not c, m)
    m, c = kc.merge3_lines(b, ["a\n", "B\n", "c\n", "d\n", "e\n"], ["a\n", "b\n", "C\n", "d\n", "e\n"])
    check("edits that touch are a conflict, never guessed", bool(c), m)
    m, c = kc.merge3_lines(b, ["a\n", "X\n", "c\n", "d\n", "e\n"], ["a\n", "X\n", "c\n", "d\n", "e\n"])
    check("the same edit on both sides is not a conflict", m == ["a\n", "X\n", "c\n", "d\n", "e\n"] and not c)
    m, c = kc.merge3_lines(b, ["a\n", "b\n", "new\n", "c\n", "d\n", "e\n"], ["a\n", "b\n", "c\n", "d\n", "e\n", "tail\n"])
    check("her insertion and an insertion at the end: both kept", m == ["a\n", "b\n", "new\n", "c\n", "d\n", "e\n", "tail\n"] and not c, m)
    rules = ["## Rules\n", "\n", "- one\n", "- two\n"]
    t, c = kc.merge_file("CLAUDE.md", "".join(rules), "".join(rules[:2] + ["- hers\n"] + rules[2:]),
                         "".join(rules[:2] + ["- the engine's new rule\n"] + rules[2:]))
    check("instructions: her rule and a new engine rule under one heading are both kept, ours first",
          t == "## Rules\n\n- the engine's new rule\n- hers\n- one\n- two\n" and not c, repr(t))
    t, c = kc.merge_file("x.py", "".join(rules), "".join(rules[:2] + ["- hers\n"] + rules[2:]),
                         "".join(rules[:2] + ["- the engine's new rule\n"] + rules[2:]))
    check("code: two additions at one spot go to her, never combined by rule", t is None and c)
    m, c = kc.merge3_json({"k": 1}, {"k": 2}, {"k": 3})
    check("the same JSON key changed both ways is a conflict", bool(c) and m == {"k": 3}, m)
    # Two sets of edits that each work and together won't run: her old lines and the update's own, same name twice in
    # one script (a buyer's editor page would not open, and the merge called it clean; 2026-10-29)
    base = "<html><script>\nlet a = 1;\nlet b = 2;\nlet c = 3;\nlet d = 4;\nlet e = 5;\n</script></html>\n"
    mine = base.replace("let a = 1;\n", "let a = 1;\nlet soundAt = 0;\n")
    theirs = base.replace("let e = 5;\n", "let e = 5;\nlet soundAt = {};\n")
    t, c = kc.merge_file("product/editor.html", base, mine, theirs)
    import shutil as _sh
    if _sh.which("node"):
        check("a merge that would stop a page's script running is refused, not called clean",
           t is None and any(x.get("breaks") for x in c), (t, c))
    t, c = kc.merge_file("product/editor.html", base, mine, base)
    check("the same change alone still comes through", t == mine and not c, (t, c))
    pybase = "a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n"
    t, c = kc.merge_file("x.py", pybase, pybase.replace("a = 1\n", "if a:\n"), pybase.replace("e = 5\n", "e = 6\n"))
    check("a Python merge that won't compile is refused when the update's own copy does",
       t is None and any(x.get("breaks") for x in c), (t, c))
    t, c = kc.merge_file("x.py", "a\r\nb\r\nc\r\n", "a\r\nb\r\nC\r\n", "A\r\nb\r\nc\r\n")
    check("Windows line endings survive a merge", t == "A\r\nb\r\nC\r\n" and not c, repr(t))

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
