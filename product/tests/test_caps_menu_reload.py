#!/usr/bin/env python3
"""Guard: a tap on Captions (or a look's ⋯) while her looks are reloading does nothing instead of throwing.

Every looks reload (a style switch, a restitch, a refine) sets LOOKS = null before loadLooks() comes back, and the
Captions button keeps its old onclick the whole time. A buyer on v2.3.4 tapped it in that window and the page threw
"Cannot read properties of null (reading 'moments')" at capsMenu. This runs the page's own capsMenu and lookMenu
under node with LOOKS = null and checks neither throws.

Run: python3 product/tests/test_caps_menu_reload.py
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(os.path.dirname(HERE), "visual-editor", "editor.html")


def fn_source(src, name):
    """The full text of `function name(...) { ... }` in the page, found by brace matching."""
    m = re.search(r"\nfunction " + re.escape(name) + r"\(", src)
    if not m:
        return None
    i = src.index("{", m.end())
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[m.start() + 1:j + 1]
    return None


def main():
    node = shutil.which("node")
    if not node:
        print("SKIP: node is not on PATH")
        return 0
    src = open(PAGE, encoding="utf-8").read()
    fns = {n: fn_source(src, n) for n in ("capsMenu", "lookMenu")}
    missing = [n for n, s in fns.items() if not s]
    if missing:
        print(f"FAIL: could not find {', '.join(missing)} in editor.html")
        return 1
    js = (
        "let LOOKS = null; const calls = [];\n"
        "function trashLook() { calls.push('trash'); } function openSwap() { calls.push('swap'); }\n"
        "function hidePop() {} function cutPos() { return 0; } function icon() { return ''; }\n"
        "const document = { querySelector: () => null, createElement: () => ({ setAttribute() {}, style: {} }),"
        " body: { append() {} } };\n"
        + fns["capsMenu"] + "\n" + fns["lookMenu"] + "\n"
        "const btn = { getBoundingClientRect: () => ({ top: 100, bottom: 120, left: 10, width: 40 }) };\n"
        "let bad = [];\n"
        "for (const capL of [{ name: 'cap-1', captions: true }, { name: 'cap-1', captions: true, off: true }]) {\n"
        "  try { capsMenu(btn, capL); } catch (e) { bad.push('capsMenu: ' + e.message); } }\n"
        "try { lookMenu(btn, { layer: 'cap-1' }, null); } catch (e) { bad.push('lookMenu: ' + e.message); }\n"
        "if (calls.length) bad.push('acted while reloading: ' + calls.join(','));\n"
        "console.log(JSON.stringify(bad)); process.exit(bad.length ? 1 : 0);\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if r.returncode:
        print("FAIL: a tap during a looks reload threw or acted:", (r.stdout + r.stderr).strip()[-400:])
        return 1
    print("caps menu reload guard: 3/3 ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
