#!/usr/bin/env python3
"""Every engine script a skill runs with plain python3 loads on a Python that has only what setup installs.

Buyer reports (launch week, 2026-10-19): setting a default pack ran `python3 -c "import cleanyap; ..."`, and an
unused top-level `import requests` in cleanyap.py died with "No module named 'requests'" on two machines (fixed in
the sweep; test_no_requests_needed). The cause is broader than one file: a script a skill or CLAUDE.md runs with
plain python3 (never `uv run`, which brings its own packages) may import at load time only what every buyer has:
Python's own library, Pillow (check-setup.sh installs it) and the engine's own modules, followed through their own
load-time imports. A third-party import inside a function, or under try/except, is fine.

  1. every `python3 product|workflows|scripts/<x>.py` and `python3 -c "import <x>"` in a skill or CLAUDE.md, and the
     engine modules they import at load time, import nothing else at load time
  2. the check itself catches a module that does (a stand-in with a top-level `import requests`)

Static: nothing is imported or run.

Run:  python3 product/tests/test_plain_python_imports.py
"""
import ast, glob, os, re, shutil, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
GUARANTEED = {"PIL", "__future__"}           # Pillow: check-setup.sh installs it for every buyer
STDLIB = set(getattr(sys, "stdlib_module_names", ()))
fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def load_time_imports(path):
    """(top module name, guarded) for every import that runs when the file loads: module level, also inside if /
    with / for, never inside a function or class; guarded = under a try that catches the failure."""
    out = []

    def walk(body, guarded):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(n, ast.Import):
                out.extend((a.name.split(".")[0], guarded) for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                out.append((n.module.split(".")[0], guarded))
            elif isinstance(n, ast.Try):
                walk(n.body, guarded or bool(n.handlers))
                for part in (n.orelse, n.finalbody, *[h.body for h in n.handlers]):
                    walk(part, guarded)
            elif isinstance(n, ast.If):
                walk(n.body, guarded); walk(n.orelse, guarded)
            elif isinstance(n, (ast.With, ast.For, ast.While)):
                walk(n.body, guarded)

    with open(path, encoding="utf-8") as fh:
        walk(ast.parse(fh.read(), path).body, False)
    return out


def offenders(root, entries):
    """{third-party module: [the chain that loads it]} for these entry scripts."""
    def engine_module(name):
        for d in ("product", "workflows", "scripts"):
            p = os.path.join(root, d, name + ".py")
            if os.path.exists(p):
                return p
        return None

    bad, seen = {}, set()

    def visit(path, chain):
        if path in seen:
            return
        seen.add(path)
        with open(path, encoding="utf-8") as fh:
            if "# /// script" in fh.read(600):      # a uv script: it declares its own packages
                return
        for name, guarded in load_time_imports(path):
            if name in STDLIB or name in GUARANTEED:
                continue
            p = engine_module(name)
            if p:
                visit(p, chain + [name])
            elif not guarded:
                bad.setdefault(name, []).append(" > ".join(chain))

    for e in sorted(entries):
        p = os.path.join(root, e)
        if os.path.exists(p):
            visit(p, [e])
    return bad


def entry_points(root):
    text = ""
    for f in glob.glob(os.path.join(root, ".claude", "skills", "*", "SKILL.md")) + [os.path.join(root, "CLAUDE.md")]:
        with open(f, encoding="utf-8") as fh:
            text += fh.read()
    out = set(re.findall(r"python3? ((?:product|workflows|scripts)/[\w\-/]+\.py)", text))
    out |= {f"product/{m}.py" for m in re.findall(r'python3? -c "import (\w+)', text)}
    return {e for e in out if os.path.exists(os.path.join(root, e))}


if not STDLIB:
    print("plain python imports: skipped (needs Python 3.10+ to know its own library)")
    sys.exit(0)

print("1. the engine as it stands")
entries = entry_points(ROOT)
check("the skills name scripts to check", len(entries) >= 10, len(entries))
bad = offenders(ROOT, entries)
check("none imports a package a buyer may not have at load time", not bad,
      "; ".join(f"{k} <- {sorted(set(v))[:3]}" for k, v in sorted(bad.items())))

print("2. the check catches one")
tmp = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(tmp, "product"))
    with open(os.path.join(tmp, "product", "entry.py"), "w", encoding="utf-8") as fh:
        fh.write("import json\nimport helper\n")
    with open(os.path.join(tmp, "product", "helper.py"), "w", encoding="utf-8") as fh:
        fh.write("import os\nimport requests\ntry:\n    import numpy\nexcept ImportError:\n    numpy = None\n"
                 "def later():\n    import cv2\n")
    got = offenders(tmp, {"product/entry.py"})
    check("a top-level `import requests` two modules down is caught", got == {"requests": ["product/entry.py > helper"]}, got)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "plain python imports: every skill's python3 script loads on a bare Python"))
sys.exit(1 if fails else 0)
