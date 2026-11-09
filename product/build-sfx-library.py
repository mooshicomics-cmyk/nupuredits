#!/usr/bin/env python3
"""build-sfx-library.py — regenerate the effects library's sound pool from creative-vault/sfx/sfx-index.json.

Why this exists: the wall's sound list is GENERATED from the index, and for a while nothing regenerated it.
The library underneath was replaced, the page went on advertising 230 sounds that no longer existed, and
every play button pointed at a deleted file while the click handler swallowed the error -- so a buyer
pressed play and simply nothing happened. The page is only ever as true as its last regeneration, so this
makes regenerating it one command, and --check makes "is it stale?" answerable without guessing.

The index is the source of truth. A cue is shown when it is ENABLED (`"enabled": false` hides one) and is
not an alias. Cues are grouped by MOOD, in the emotional order the wall reads in, not alphabetically.

    python3 product/build-sfx-library.py            rewrite the block in product/effects-library.html
    python3 product/build-sfx-library.py --check    say whether the page is stale; write nothing
"""
import json, os, re, subprocess, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX = os.path.join(ROOT, "product", "creative-vault", "sfx")
PAGE = os.path.join(ROOT, "product", "effects-library.html")
# The order the pool reads in: heaviest to lightest, then the everyday ones. Not alphabetical, on purpose.
MOOD_ORDER = ["somber", "tender", "tense", "triumphant", "playful", "neutral"]
HEAD = ("  // every ENABLED sound cue, grouped by MOOD: [stem, seconds, path, job, description]. "
        "Generated from creative-vault/sfx/sfx-index.json.")
DECL = re.compile(r"^  // every ENABLED sound cue.*?\n  var SFX_POOL=\{.*?\};$", re.S | re.M)


def duration(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            text=True, stderr=subprocess.DEVNULL).strip()
        return round(float(out), 2)
    except Exception:
        return 0.0


def build():
    """({mood: [[stem, seconds, path_from_product], ...]}, skipped) — mood order fixed, cues sorted."""
    idx = json.load(open(os.path.join(SFX, "sfx-index.json"), encoding="utf-8"))
    pool, skipped = {}, []
    for name, v in sorted(idx["sounds"].items()):
        if v.get("source") == "alias" or v.get("enabled") is False:
            continue
        full = os.path.normpath(os.path.join(SFX, v["file"]))
        if not os.path.isfile(full):
            skipped.append((name, v["file"]))      # never advertise a sound the page cannot play
            continue
        rel = os.path.relpath(full, os.path.join(ROOT, "product")).replace(os.sep, "/")
        # job + description feed the Sounds tab's "what it's for" filter and the readable name
        pool.setdefault(v.get("mood") or "neutral", []).append(
            [name, duration(full), rel, v.get("job") or "other", v.get("description") or ""])
    ordered = {m: pool[m] for m in MOOD_ORDER if m in pool}
    for m in sorted(pool):                          # a mood nobody listed in MOOD_ORDER still ships
        ordered.setdefault(m, pool[m])
    return ordered, skipped


def main(argv):
    check = "--check" in argv
    pool, skipped = build()
    n = sum(len(v) for v in pool.values())
    new = HEAD + "\n  var SFX_POOL=" + json.dumps(pool, ensure_ascii=False) + ";"
    page = open(PAGE, encoding="utf-8").read()
    m = DECL.search(page)
    if not m:
        print("could not find the generated SFX_POOL block in effects-library.html — nothing written.")
        return 2
    for name, f in skipped:
        print(f"  skipped {name}: no file at {f}")
    if m.group(0) == new:
        print(f"effects library: sound pool already current ({n} cues across {len(pool)} moods).")
        return 0
    if check:
        print(f"effects library: the sound pool is STALE — would rewrite it to {n} cues. Nothing written.")
        return 1
    open(PAGE, "w", encoding="utf-8").write(page[:m.start()] + new + page[m.end():])
    print(f"effects library: sound pool rewritten — {n} cues across {len(pool)} moods ({', '.join(pool)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
