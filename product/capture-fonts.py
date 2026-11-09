#!/usr/bin/env python3
"""capture-fonts.py — read your CapCut drafts and fill in each pack font's CapCut LIBRARY id.

Run this once after you've added the pack fonts in CapCut (add a Text -> Fonts -> search the name -> tap
it -> type a word -> save the draft). It scans your CapCut drafts, finds the `font_resource_id` +
`font_source_platform` CapCut wrote for each font file, and updates `creative-vault/font-registry.json`
so the engine can reference those fonts from any buyer's CapCut library (no file redistribution needed).

    python3 product/capture-fonts.py            # report + fill the registry
    python3 product/capture-fonts.py --dry      # report only, don't write

Safe: only fills EMPTY resource_ids (never overwrites a value already in the registry), and only touches
fonts already listed in the registry.
"""
import os, sys, json, glob, collections

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "creative-vault", "font-registry.json")
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
DRY = "--dry" in sys.argv

def scan():
    """basename -> list of (resource_id, platform, font_name) seen across all drafts."""
    seen = collections.defaultdict(list)
    files = _ds.draft_jsons_under(CAP) + _ds.draft_jsons_under(CAP, "*/Timelines/*")
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for m in d.get("materials", {}).get("texts", []):
            path = m.get("font_path") or ""
            if not path:
                continue
            base = os.path.basename(path)
            seen[base].append((str(m.get("font_resource_id") or ""),
                               m.get("font_source_platform"),
                               m.get("font_name") or ""))
    return seen, len(files)

def best(records):
    """Prefer a platform=1 record WITH a resource_id (a true CapCut-library reference)."""
    lib = [r for r in records if r[0] and r[1] == 1]
    if lib:
        return lib[0]
    withid = [r for r in records if r[0]]
    return withid[0] if withid else None

def main():
    if not os.path.isdir(CAP):
        print(f"No CapCut drafts folder at {CAP}. Open CapCut once, then re-run.")
        return
    seen, nfiles = scan()
    print(f"scanned {nfiles} draft files, {len(seen)} distinct font files\n")
    reg = json.load(open(REGISTRY, encoding="utf-8"))
    fonts = reg.get("fonts", {})
    filled, still = [], []
    for base, entry in fonts.items():
        if entry.get("font_resource_id"):
            continue  # already known, never overwrite
        b = best(seen.get(base, []))
        if b:
            rid, plat, name = b
            entry["font_resource_id"] = rid
            if plat is not None:
                entry["font_source_platform"] = int(plat)
            if name and not entry.get("font_name"):
                entry["font_name"] = name
            filled.append(f"{base} -> resource_id={rid} platform={plat}")
        elif entry.get("source") == "capcut_library":
            still.append(base)
    if filled:
        print("FILLED (found a library id):")
        for f in filled:
            print("  +", f)
    else:
        print("No new library resource_ids found in your drafts.")
    if still:
        print("\nStill missing (add these in CapCut from the Fonts LIBRARY, type a word, save, re-run):")
        for b in still:
            print("  -", b, f"({fonts[b].get('font_name','')})")
    if filled and not DRY:
        json.dump(reg, open(REGISTRY, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"\nwrote {REGISTRY}")
    elif filled and DRY:
        print("\n(--dry: not written)")

if __name__ == "__main__":
    main()
