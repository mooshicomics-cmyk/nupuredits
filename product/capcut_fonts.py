#!/usr/bin/env python3
"""capcut_fonts.py — resolve a font to the CapCut draft fields that make it render for a BUYER.

Why this exists: some pack fonts (Prosecco, Bloop, Opera Cake, Geomanist, Soup Du Jour) live inside
CapCut's OWN font library, not as files we can redistribute. For those, the draft must reference CapCut's
`font_resource_id` (+ `font_source_platform=1` + `font_name`) so CapCut pulls the font from the buyer's own
library. OFL fonts we ship keep loading by file path. This module reads `creative-vault/font-registry.json`
(keyed by font-file basename) and returns the right field set either way — backward-compatible: a font with
no registry entry (or an empty resource_id) resolves exactly like before (font_path only).

    from capcut_fonts import resolve, apply
    apply(material_dict, font_path)   # sets font_path/font_id/font_resource_id/font_name/font_source_platform
"""
import os, json

_HERE = os.path.dirname(os.path.abspath(__file__))
_REGISTRY = os.path.join(_HERE, "creative-vault", "font-registry.json")

def _load():
    try:
        return json.load(open(_REGISTRY, encoding="utf-8")).get("fonts", {})
    except Exception:
        return {}

def resolve(font_path):
    """Return the CapCut font fields for this font file. If the registry marks it a capcut_library font
    WITH a resource_id, reference the library (resource_id + platform + name), keeping font_path as a
    fallback. Otherwise return today's file-only shape (blank resource_id). Never raises."""
    fields = {"font_path": font_path, "font_id": "", "font_resource_id": "",
              "font_name": "", "font_source_platform": 0}
    if not font_path:
        return fields
    reg = _load()
    entry = reg.get(os.path.basename(font_path))
    if not (entry and entry.get("font_resource_id")):
        # The basename no longer reliably matches a registry key: a catalog font resolves to 'font.ttf' or
        # a hyphenated name (Ugly-Dave-Alternates.otf), not the expected key (Bloop.ttf / UglyDaveAlternates.otf).
        # Fall back to matching the file's REAL embedded family against each entry's font_name, so the
        # portability resource_id still attaches instead of silently shipping a machine-only file path
        # (round 11 Bug B). Family read via the shared resolver's helper (PIL-guarded).
        try:
            import capcut_userfonts
            fam = (capcut_userfonts.font_family(font_path) or "").strip().lower()
        except Exception:
            fam = ""
        if fam:
            entry = next((v for v in reg.values()
                          if str(v.get("font_name", "")).strip().lower() == fam), entry)
    if entry and entry.get("font_resource_id"):
        fields["font_resource_id"] = str(entry["font_resource_id"])
        fields["font_name"] = entry.get("font_name", "")
        fields["font_source_platform"] = int(entry.get("font_source_platform", 1))
    return fields

def apply(material, font_path):
    """Set the resolved font fields on a CapCut text material dict in place. Returns the material."""
    material.update(resolve(font_path))
    return material

def missing_library_ids():
    """List capcut_library fonts still lacking a resource_id (not yet bulletproof for buyers)."""
    return [b for b, e in _load().items()
            if e.get("source") == "capcut_library" and not e.get("font_resource_id")]

if __name__ == "__main__":
    reg = _load()
    print(f"font-registry: {len(reg)} fonts")
    for base, e in reg.items():
        rid = e.get("font_resource_id") or "—(needs capture)"
        print(f"  {base:26s} {e.get('source',''):15s} resid={rid}  name={e.get('font_name','')!r}")
    miss = missing_library_ids()
    if miss:
        print("\nStill need a CapCut library resource_id (run capture-fonts.py after adding them in CapCut):")
        for b in miss:
            print(f"  - {b}")
