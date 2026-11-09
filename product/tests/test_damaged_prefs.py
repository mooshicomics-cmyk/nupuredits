#!/usr/bin/env python3
"""A damaged preferences file is kept and named, never written over.

`_local/learned.json` (what she taught with /learn) and `creative-vault/user-effects.json` (the text
animations she named) are read as EMPTY when they will not parse: cut off mid-write, or hand-edited into
invalid JSON. That is right for a build, which should carry on with the shipped defaults. It was wrong for
the next write: /learn or /learn effect saved its one new record over the top, and everything she had
taught before it was gone, without a word. And `/learn list` answered "Nothing taught yet".

Now the damaged file is moved aside, byte for byte, with a plain warning, before a fresh one is written;
the listing says the file is damaged instead of empty; and a healthy file still merges as before.

Everything runs in a throwaway engine skeleton; this engine's own _local/ and creative-vault/ are never read.

Run: python3 product/tests/test_damaged_prefs.py
"""
import glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
TRUNCATED_PREFS = ('{"preferences": [{"id": "a1", "field": "sfx.density", "value": "lighter", "scope": {}}, '
                   '{"id": "b2", "field": "hook.size", "value": 14, "scope": {}')
TRUNCATED_EFFECTS = '{"effects": {"the snap": {"gran": "word", "frm": {"autoAlpha": 0}, "to": {"autoAlpha": 1}'
fails = []


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Engine:
    def __init__(self, root):
        self.root = root
        os.makedirs(os.path.join(root, "product", "creative-vault"))
        for fn in ("learned.py", "text_effects.py"):
            shutil.copy2(os.path.join(PRODUCT, fn), os.path.join(root, "product", fn))
        self.store = os.path.join(root, "_local", "learned.json")
        self.effects = os.path.join(root, "product", "creative-vault", "user-effects.json")

    def learned(self, *args):
        r = subprocess.run([sys.executable, os.path.join(self.root, "product", "learned.py"), *args],
                           capture_output=True, text=True, cwd=self.root, env={**os.environ, "PYTHONUTF8": "1"})
        return r.returncode, r.stdout + r.stderr

    def py(self, code):
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'product'); " + code],
                           capture_output=True, text=True, cwd=self.root, env={**os.environ, "PYTHONUTF8": "1"})
        return r.returncode, r.stdout + r.stderr

    def prefs(self):
        return [p["field"] for p in json.loads(read(self.store))["preferences"]]

    def aside(self, name):
        return sorted(glob.glob(os.path.join(self.root, "_local", name + ".damaged-*")))


def main():
    tmp = tempfile.mkdtemp()
    try:
        # ---- a healthy store still merges, and nothing is set aside ----
        e = Engine(os.path.join(tmp, "healthy"))
        rc, out = e.learned("add", "sfx.density", "lighter")
        rc2, out2 = e.learned("add", "hook.size", "14")
        check("a first preference saves", rc == 0 and rc2 == 0, out + out2)
        check("a healthy file keeps what was taught before", e.prefs() == ["sfx.density", "hook.size"], e.prefs())
        check("a healthy file is never set aside or warned about", not e.aside("learned.json") and "⚠" not in out + out2)

        # ---- a damaged store: listed as damaged, moved aside intact, then a fresh one ----
        for label, body in (("cut off mid-write", TRUNCATED_PREFS), ("the wrong shape", '{"preferences": "oops"}')):
            e = Engine(os.path.join(tmp, "damaged-" + label.replace(" ", "-")))
            write(e.store, body)
            rc, out = e.learned("list")
            check(f"{label}: /learn list says the file is damaged, not that nothing was taught",
                  rc != 0 and "damaged" in out and "Nothing taught yet" not in out, out)
            rc, out = e.learned("forget", "1")
            check(f"{label}: /learn forget says the file is damaged and changes nothing",
                  rc != 0 and "damaged" in out and read(e.store) == body, out)
            rc, out = e.learned("add", "caption.size_scale", "1.2")
            kept = e.aside("learned.json")
            check(f"{label}: the next /learn still saves", rc == 0 and e.prefs() == ["caption.size_scale"], out)
            check(f"{label}: the damaged file is kept aside, byte for byte",
                  len(kept) == 1 and read(kept[0]) == body, f"{kept}")
            check(f"{label}: she is told plainly, and where it went",
                  "⚠" in out and "damaged" in out and (os.path.basename(kept[0]) if kept else "?") in out, out)
            rc, out = e.learned("add", "hook.size", "13")
            check(f"{label}: after that, the fresh file merges normally",
                  e.prefs() == ["caption.size_scale", "hook.size"] and len(e.aside("learned.json")) == 1, out)

        # ---- the named text animations ----
        e = Engine(os.path.join(tmp, "effects-healthy"))
        rc, out = e.py("import text_effects as t; t.teach('the snap', base='spring-scale-in', dur=0.28); "
                       "t.teach('slow burn', base='rise', dur=0.9); print(t.mine())")
        check("named effects save and merge", rc == 0 and "['slow burn', 'the snap']" in out, out)
        check("a healthy effects file is never set aside", not e.aside("user-effects.json") and "⚠" not in out)

        e = Engine(os.path.join(tmp, "effects-damaged"))
        write(e.effects, TRUNCATED_EFFECTS)
        rc, out = e.py("import text_effects as t; print('mine', t.mine())")
        check("a damaged effects file is announced when the engine loads, and left untouched",
              rc == 0 and "damaged" in out and read(e.effects) == TRUNCATED_EFFECTS, out)
        rc, out = e.py("import text_effects as t; t.teach('the drop', base='rise', dur=0.4); print('mine', t.mine())")
        kept = e.aside("user-effects.json")
        check("the next named effect still saves", rc == 0 and "mine ['the drop']" in out, out)
        check("the damaged effects file is kept aside in _local, byte for byte (never next to the shipped files)",
              len(kept) == 1 and read(kept[0]) == TRUNCATED_EFFECTS
              and not glob.glob(os.path.join(os.path.dirname(e.effects), "*.damaged-*")), f"{kept}")
        rc, out = e.py("import text_effects as t; print('mine', t.mine())")
        check("once set aside, the engine loads quietly again", rc == 0 and "⚠" not in out and "the drop" in out, out)

        # ---- a Windows console that cannot show a status symbol never kills the import or the CLI ----
        e = Engine(os.path.join(tmp, "cp1252"))
        write(e.effects, TRUNCATED_EFFECTS)
        write(e.store, TRUNCATED_PREFS)
        cp = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        cp.pop("PYTHONUTF8", None)
        r = subprocess.run([sys.executable, "-X", "utf8=0", "-c",
                            "import sys; sys.path.insert(0, 'product'); import text_effects; print('loaded')"],
                           capture_output=True, cwd=e.root, env=cp)
        check("on a cp1252 console the damaged-effects warning cannot kill the import",
              r.returncode == 0 and b"loaded" in r.stdout and b"damaged" in r.stdout, repr(r.stdout + r.stderr)[-300:])
        r = subprocess.run([sys.executable, "-X", "utf8=0", os.path.join(e.root, "product", "learned.py"), "add",
                            "hook.size", "13"], capture_output=True, cwd=e.root, env=cp)
        check("on a cp1252 console /learn still saves past a damaged file",
              r.returncode == 0 and e.prefs() == ["hook.size"] and len(e.aside("learned.json")) == 1,
              repr(r.stdout + r.stderr)[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    if fails:
        print(f"damaged prefs: FAILED {len(fails)}: {'; '.join(fails)}")
        sys.exit(1)
    print("damaged prefs: a damaged preferences or effects file is kept and named, never written over")
