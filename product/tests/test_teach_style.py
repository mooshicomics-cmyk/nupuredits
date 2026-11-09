#!/usr/bin/env python3
"""Teach my style from this reel: the end-of-reel checklist (product/teach_style.py).

At the end of every reel her notes become a pick-many checklist of rules for the next reel. These checks hold:
  * `offer` says nothing (exit 1) with no notes, once the reel was asked, and when she switched it off;
  * `collect` reads every place her notes live (editor notes, look requests, a look she switched off, a music
    level she set by hand, chat notes logged with `note`);
  * `keep` with a learnable field writes BOTH halves (the learned.json record the builders apply, and the Part C
    bullet), with scope; without a field it writes the bullet only and says it is read, not applied;
  * a value the engine can't take writes nothing at all;
  * the bullet lands inside Part C's learned list, before the For-Claude note, never at the end of the file.

Everything runs in a throwaway engine skeleton; this engine's own _local/, projects/ and brand-kit.md are never touched.

Run: python3 product/tests/test_teach_style.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
fails = []

KIT = """# Brand kit

# Part C — Reel style memory

### Learned preferences (Claude appends here)

Append-only.

- **An earlier one.** (old-reel, 2026-08-02)

> _For Claude:_ load the `learn` skill.
> More notes for Claude.
"""


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))
    else:
        print(f"  ok   {name}")


def run(root, *args):
    p = subprocess.run([sys.executable, os.path.join(root, "product", "teach_style.py"), *args],
                       capture_output=True, text=True, encoding="utf-8", cwd=root,
                       env=dict(os.environ, REE_EDITOR="1"))   # the editor on (test_early_access.py covers off)
    return p.returncode, p.stdout


def skeleton():
    root = tempfile.mkdtemp(prefix="teach-style-")
    os.makedirs(os.path.join(root, "product"))
    for f in ("teach_style.py", "learned.py", "early_access.py"):
        shutil.copy(os.path.join(PRODUCT, f), os.path.join(root, "product", f))
    with open(os.path.join(root, "brand-kit.md"), "w", encoding="utf-8") as f:
        f.write(KIT)
    os.makedirs(os.path.join(root, "projects", "quiet-one", "review"))
    jd = os.path.join(root, "projects", "noisy-one")
    os.makedirs(os.path.join(jd, "review"))
    os.makedirs(os.path.join(jd, "transcript"))
    json.dump({"notes": [{"id": "n1", "w": 3, "text": "captions a bit higher", "status": "fixed",
                          "reply": "Moved up.", "at": "2026-10-17 10:00:00"}]},
              open(os.path.join(jd, "transcript", "script-notes.json"), "w", encoding="utf-8"))
    json.dump({"requests": [{"id": "r1", "idea": "a count-up card here", "at": "2026-10-17 10:05:00"}]},
              open(os.path.join(jd, "review", "look-requests.json"), "w", encoding="utf-8"))
    json.dump({"swaps": {"h01-hook": {"look": "_off", "at": "2026-10-17 10:06:00"}}},
              open(os.path.join(jd, "review", "swaps.json"), "w", encoding="utf-8"))
    json.dump({"music": {"on": True, "level_how": "hand", "level_db": -22}},
              open(os.path.join(jd, "review", "sound.json"), "w", encoding="utf-8"))
    return root


def main():
    root = skeleton()
    try:
        code, out = run(root, "offer", "quiet-one")
        check("no notes: offer is silent and exits 1", code == 1 and out == "", out)

        code, out = run(root, "note", "noisy-one", "fewer sound effects", "--from", "beat sheet")
        check("note logs a chat note", code == 0)
        code, out = run(root, "collect", "noisy-one", "--json")
        ns = json.loads(out)
        froms = {n["from"] for n in ns}
        check("collect reads every source",
              froms == {"editor note", "look she asked for", "switched off", "sound", "beat sheet"}, sorted(froms))
        check("a switched-off hook reads in plain words", any(n["said"] == "turned the hook off" for n in ns))

        code, out = run(root, "offer", "noisy-one")
        check("notes: offer exits 0 and lists them", code == 0 and "captions a bit higher" in out, out)

        code, out = run(root, "keep", "noisy-one", "Fewer sound effects on confessional reels",
                        "--field", "sfx.density", "--value", "lighter", "--scope", "register=confessional")
        recs = json.load(open(os.path.join(root, "_local", "learned.json"), encoding="utf-8")).get("preferences", [])
        check("keep with a field writes the builder record",
              code == 0 and recs and recs[-1]["field"] == "sfx.density" and recs[-1]["value"] == "lighter"
              and recs[-1]["scope"] == {"register": "confessional"} and recs[-1]["from_job"] == "noisy-one", out)
        check("keep with a field says it is applied", "applies it from your next reel" in out, out)

        code, out = run(root, "keep", "noisy-one", "Comment collages sit behind my head")
        check("keep without a field says it is read, not applied", code == 0 and "read it before planning" in out, out)

        before = open(os.path.join(root, "brand-kit.md"), encoding="utf-8").read()
        code, out = run(root, "keep", "noisy-one", "Huge hooks", "--field", "hook.size", "--value", "huge")
        after = open(os.path.join(root, "brand-kit.md"), encoding="utf-8").read()
        n_recs = len(json.load(open(os.path.join(root, "_local", "learned.json"), encoding="utf-8")).get("preferences", []))
        check("a value the engine can't take writes nothing", code == 1 and before == after and n_recs == 1, out)

        kit = after.split("\n")
        i_claude = next(i for i, l in enumerate(kit) if l.startswith("> _For Claude:_"))
        i_sfx = next(i for i, l in enumerate(kit) if "Fewer sound effects on confessional reels" in l)
        i_col = next(i for i, l in enumerate(kit) if "Comment collages sit behind my head" in l)
        i_old = next(i for i, l in enumerate(kit) if "An earlier one" in l)
        check("bullets land in the learned list, in order, before the For-Claude note",
              i_old < i_sfx < i_col < i_claude, after)
        check("a blank line still separates the list from the For-Claude note", kit[i_claude - 1] == "")
        check("the bullet says where it is kept", "Applied by the engine on every build (register confessional only)"
              in kit[i_sfx] and "Claude reads it before planning" in kit[i_col], kit[i_sfx])

        code, out = run(root, "done", "noisy-one", "--kept", "2")
        code, out = run(root, "offer", "noisy-one")
        check("asked once per reel: offer is silent after done", code == 1 and out == "", out)

        run(root, "--off")
        os.makedirs(os.path.join(root, "projects", "next-one", "review"))
        json.dump({"notes": [{"said": "x", "from": "chat note"}]},
                  open(os.path.join(root, "projects", "next-one", "review", "notes-log.json"), "w", encoding="utf-8"))
        code, out = run(root, "offer", "next-one")
        check("switched off: offer is silent", code == 1 and out == "")
        run(root, "--on")
        code, out = run(root, "offer", "next-one")
        check("switched back on: offer speaks", code == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\nPASS" if not fails else f"\nFAIL ({len(fails)}): {', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
