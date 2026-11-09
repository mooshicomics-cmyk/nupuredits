#!/usr/bin/env python3
"""capture-templates.py — derive the reusable caption/graphics blueprints from your CapCut drafts.

WHY THIS EXISTS: build-captions.py / build-graphics.py need two blueprint files
(text-templates.json + anim-objects.json). These are NOT reel-specific -- they are the
generic CapCut text-element + animation shapes. They used to live in a throwaway temp
folder (which got wiped, breaking the builds). This tool re-derives them from your actual
CapCut drafts and writes them to a PERMANENT home in the repo:

    product/creative-vault/caption-templates/{text-templates.json, anim-objects.json}

so they can never be permanently lost again. If they ever go missing, just run:

    python3 product/capture-templates.py "<one of your drafts that has text in it>"

- The ANIMATION LIBRARY is the UNION of every named animation across ALL your drafts, so
  it covers every entrance/exit build-captions/build-graphics can ask for (not just one reel's).
- The text/segment/animation SHELL templates come from the draft you name (any draft with text
  works; the builders overwrite content/color/font/timing). There is no default draft.

Reads:  ~/Movies/CapCut/User Data/Projects/com.lveditor.draft/*/draft_info.json
Writes: product/creative-vault/caption-templates/*.json
"""
import json, os, sys, glob
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
TEMPLATE_DRAFT = sys.argv[1] if len(sys.argv) > 1 else None
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "caption-templates")

def load(draft):
    p = _ds.draft_json(__import__("capcut_store_redirect").find_draft(draft, CAP))   # read only
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None  # skip empty/corrupt draft files

def _normalize_text_material(material):
    """Force the captured text shell to ONE clean style span + 9:16 auto-wrap. A real caption can carry
    multiple style ranges (per-word color/size); if the shell keeps them, every builder that only rewrites
    styles[0] leaves stale ranges that corrupt multi-char text (wrong size/color mid-line). Normalizing
    HERE means the shell is safe no matter which draft it's captured from."""
    import json as _j
    c = _j.loads(material["content"])
    if c.get("styles"):
        st = c["styles"][0]; st["range"] = [0, len(c.get("text", ""))]
        c["styles"] = [st]
        material["content"] = _j.dumps(c, ensure_ascii=False)
    material["fixed_width"] = -1.0; material["line_max_width"] = 0.82
    material["force_apply_line_max_width"] = False
    return material


def text_shells(d):
    """Return (material, animation-shell, segment) from a draft that has text, or None."""
    mats = d.get("materials", {})
    texts = mats.get("texts", [])
    if not texts:
        return None
    material = _normalize_text_material(texts[0])
    animation = (mats.get("material_animations") or [{"animations": [], "type": "sticker_animation"}])[0]
    text_ids = {t["id"] for t in texts}
    for tr in d.get("tracks", []):
        if tr.get("type") == "text":
            for s in tr.get("segments", []):
                if s.get("material_id") in text_ids:
                    return material, animation, s
    return None

def main():
    drafts = sorted({os.path.basename(os.path.dirname(p)) for r in __import__("capcut_store_redirect").lookup_roots(CAP)
                     for p in _ds.draft_jsons_under(r)})
    if not drafts:
        sys.exit(f"No CapCut drafts found under {CAP}. Open CapCut and a project once.")

    # 1) shells from the requested template draft, else the first draft that has text
    if TEMPLATE_DRAFT is None:   # no default draft: name one of hers, never a personal one
        sys.exit(f"⛔ Name the draft to take the text shells from (any of yours with text in it):\n"
                 f"    python3 product/capture-templates.py \"<draft name>\"\n"
                 f"Drafts here: {', '.join(drafts[:12])}{' …' if len(drafts) > 12 else ''}. Nothing captured.")
    if len(sys.argv) > 1 and TEMPLATE_DRAFT not in drafts:   # a NAMED draft that is missing must not fall through
        sys.exit(f"⛔ CapCut draft {TEMPLATE_DRAFT!r} not found under {CAP}. Have: {', '.join(drafts[:12])}"
                 f"{' …' if len(drafts) > 12 else ''}. Nothing captured.")
    shells = None
    for draft in ([TEMPLATE_DRAFT] + [d for d in drafts if d != TEMPLATE_DRAFT]):
        d = load(draft)
        if d and (shells := text_shells(d)):
            shell_src = draft
            break
    if not shells:
        sys.exit("No draft with text elements found to use as the template shell.")
    material, animation, segment = shells
    text_templates = {"material": material, "animation": animation, "segment": segment}

    # 2) UNION animation library across every draft
    anim_objects, sources = {}, {}
    for draft in drafts:
        d = load(draft)
        if not d:
            continue
        for ma in d.get("materials", {}).get("material_animations", []):
            for a in ma.get("animations", []):
                name, typ = a.get("name"), a.get("type")
                if name and typ and f"{name}|{typ}" not in anim_objects:
                    anim_objects[f"{name}|{typ}"] = a
                    sources[f"{name}|{typ}"] = draft

    # 3) AUDIO structure template (for the portable SFX injector — capcut_sfx.py). Capture from the first
    #    draft that has a real audio segment, so SFX can be built on any machine with no draft/cache scraping.
    audio_template = None
    for draft in drafts:
        d = load(draft)
        if not d:
            continue
        idx = {m["id"]: (cat, m) for cat, lst in d.get("materials", {}).items() if isinstance(lst, list)
               for m in lst if isinstance(m, dict) and "id" in m}
        aud = next((t for t in d.get("tracks", []) if t.get("type") == "audio" and t.get("segments")), None)
        if aud:
            seg = aud["segments"][0]
            audio_template = {"material": idx[seg["material_id"]][1],
                              "helpers": [{"category": idx[r][0], "material": idx[r][1]}
                                          for r in seg.get("extra_material_refs", []) if r in idx],
                              "segment": seg}
            break

    os.makedirs(OUT, exist_ok=True)
    json.dump(text_templates, open(f"{OUT}/text-templates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(anim_objects, open(f"{OUT}/anim-objects.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if audio_template:
        json.dump(audio_template, open(f"{OUT}/audio-template.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"Shells from draft: {shell_src}")
    print(f"Audio template: {'captured' if audio_template else 'NONE (no draft with audio) — keep existing'}")
    print(f"Animation library: {len(anim_objects)} named animations (union of {len(drafts)} drafts)")
    print(f"  -> {OUT}")

if __name__ == "__main__":
    main()
