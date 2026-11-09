#!/usr/bin/env python3
"""merge-claude-md.py — refresh the engine's own instructions in CLAUDE.md, keeping the creator's profile.

Why this exists: CLAUDE.md is protected from updates because it holds the creator's applied brand kit
(identity, niche, voice). That protection also meant every improvement to the ENGINE's instructions in
that file (pipeline steps, layout rules, what is optional, how setup works) never reached an existing
install. The code arrived; the instructions Claude reads stayed old.

How it works: the shipped, blank engine template lives at product/templates/CLAUDE.engine.md (the same
file a fresh install gets as CLAUDE.md). The creator's own content lives in the regions listed in BLOCKS
below — the profile block ("### Applied" down to "**⚠️ ASK THE REGISTER"), and the look banner ("**🎨 LOOK
IS", one paragraph) that records which style pack is live. This script takes the template and drops each
of those regions into it, so the result is "new instructions + her own content". The previous CLAUDE.md is
backed up first, always.

Why the look banner is in that list: it is set during onboarding, it sits outside the profile block, and
an update that refreshed the template used to revert it to "LOOK IS NOT SET YET" with nothing said. A
creator would not notice until a reel came out in the starter colors. Everything outside these regions is
engine instructions and is meant to be refreshed. When a new piece of creator-owned content is added to
CLAUDE.md, it belongs in BLOCKS on the same day, or the next update will quietly undo it.

Runs automatically at the end of every update (scripts/apply-update.py) and can be run by hand:
  python3 scripts/merge-claude-md.py            refresh if the template is newer
  python3 scripts/merge-claude-md.py --check    say what would happen, write nothing
Safe to run any number of times: when nothing would change, it changes nothing.
"""
import datetime as _dt
import os
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "CLAUDE.md")
TEMPLATE = os.path.join(ROOT, "product", "templates", "CLAUDE.engine.md")
BACKUPS = os.path.join(ROOT, "_update-backups", "claude-md")
# Every region of CLAUDE.md the creator owns. (start marker, end marker or None for "to the blank line
# that ends the paragraph"). REQUIRED blocks must be present in both files or the merge refuses and writes
# nothing; an optional block that is missing from either file is simply left alone.
BLOCKS = [
    {"start": "### Applied", "end": "**⚠️ ASK THE REGISTER", "required": True,
     "what": "your creator profile"},
    {"start": "**🎨 LOOK IS", "end": None, "required": False,
     "what": "your look/style-pack note"},
]
START = BLOCKS[0]["start"]   # kept for anything that imported these
END = BLOCKS[0]["end"]


def _region(lines, block=None):
    """(start, end) line indexes of one creator region — end EXCLUSIVE — or None when it is not there.

    With no end marker the region is the paragraph: from the start line to the first blank line after it."""
    block = block or BLOCKS[0]
    start = next((i for i, l in enumerate(lines) if l.startswith(block["start"])), None)
    if start is None:
        return None
    if block["end"] is None:
        end = next((i for i in range(start + 1, len(lines)) if not lines[i].strip()), len(lines))
        return start, end
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(block["end"])), None)
    if end is None:
        return None
    return start, end


def merge(current_text, template_text):
    """Return (merged_text, note). merged_text is None when a safe merge is not possible."""
    cur, tpl = current_text.split("\n"), template_text.split("\n")
    merged = list(tpl)
    # bottom-up, so splicing one region cannot shift the line numbers of the ones above it
    pairs = []
    for block in BLOCKS:
        rc, rt = _region(cur, block), _region(tpl, block)
        if rc is None or rt is None:
            if block["required"]:
                side = "your CLAUDE.md" if rc is None else "the engine template"
                return None, f"{side} does not have the markers this merge relies on for {block['what']}"
            continue        # optional block absent from one side: nothing to carry over
        pairs.append((rt, cur[rc[0]:rc[1]]))
    for (ts, te), own in sorted(pairs, reverse=True):
        merged[ts:te] = own
    return "\n".join(merged), None



def main(argv):
    check = "--check" in argv
    if not os.path.exists(TEMPLATE):
        print("CLAUDE.md: no engine template shipped, nothing to refresh.")
        return 0
    template = open(TEMPLATE, encoding="utf-8").read()
    if not os.path.exists(TARGET):
        # Nothing to preserve: a fresh copy of the template is the right file.
        if not check:
            open(TARGET, "w", encoding="utf-8").write(template)
        print("CLAUDE.md was missing; " + ("would restore" if check else "restored") + " it from the engine template.")
        return 0
    current = open(TARGET, encoding="utf-8").read()
    merged, note = merge(current, template)
    if merged is None:
        alt = TARGET + ".new"
        if not check:
            open(alt, "w", encoding="utf-8").write(template)
        print(f"CLAUDE.md left as it is ({note}). The refreshed engine instructions are saved next to it as "
              f"{os.path.basename(alt)} so nothing of yours is lost; ask Claude to bring the two together.")
        return 0
    if merged == current:
        print("CLAUDE.md: engine instructions already current; your creator profile untouched.")
        return 0
    if check:
        print("CLAUDE.md: the engine instructions would be refreshed (your creator profile kept). Nothing written.")
        return 0
    os.makedirs(BACKUPS, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bpath = os.path.join(BACKUPS, f"CLAUDE.md.{stamp}.bak")
    open(bpath, "w", encoding="utf-8").write(current)
    open(TARGET, "w", encoding="utf-8").write(merged)
    kept = ", ".join(b["what"] for b in BLOCKS if _region(current.split("\n"), b) is not None)
    print(f"CLAUDE.md: refreshed the engine's instructions; {kept} kept exactly as it was.")
    print(f"  backup of the previous file: {os.path.relpath(bpath, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
