#!/usr/bin/env python3
"""canva_to_pack.py — turn a creator's styled Canva Style Pack into a working reel style pack.

This is the third door into /style-pack (the other two: say your font names, or bring a
hyperframes.dev frame pack via frame_to_pack.py). The creator copies the Style Pack template in
Canva, restyles it, and says "I styled my Canva pack". Claude reads the design with the Canva
connector's read-design tool, saves what it got to a JSON file, and runs this.

HOW THE TEMPLATE MARKS WHAT IS HERS (this is the whole contract; keep it in sync with the template):
  * PURPLE dashed outline (stroke #8f4dff) = a "style me" zone. ONLY what sits inside a zone is read.
  * The purple pill on each outline ("STYLE ME" / "BUILD HERE") and the outline itself are template
    parts. They are NEVER read as her style, even though they are purple and bold.
  * The GRAY panel at the bottom of a page, the gray labels, the legend, the page titles and the gray
    stand-in person are instructions or placeholders. NEVER read.
  * A full-page colored rectangle on a page whose layout has one (takeover, end card) is that page's
    background color. The gray footage gradient is a placeholder, never a color of hers.

Fonts: Canva's API returns a font as an internal ID (fontRef), never its name. The "Step 2: your
fonts" page has her TYPE each font's name under its sample, so we learn ID -> name there and use it
to name the font on every other page. A font we cannot name is reported, never guessed.

Case: Canva stores the characters she typed, not its "uppercase" toggle. So ALL-CAPS characters read
as upper, but lowercase characters are ambiguous (they may be showing in caps). Those stay at the
base pack's case and are reported so Claude can check the page thumbnail and pass --case.

Usage:
    python3 product/canva_to_pack.py --design _local/canva-pack/design.json --name "My Pack"
    python3 product/canva_to_pack.py --design ... --name "My Pack" --case headline=lower --write
    python3 product/canva_to_pack.py --design ... --name "My Pack" --json
"""
import argparse, json, os, re, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))
import pack_recipe as pr
try:
    import capcut_userfonts as _cf
except Exception:
    _cf = None

PURPLE = "#8f4dff"            # the template's "style me" color. Never a creator color.
TEMPLATE_TAGS = {"STYLE ME", "BUILD HERE"}
BASE = "Butter"               # the template's frames are drawn at Butter's real sizes and positions
ZONE_PAD = 40                 # how far outside an outline an element may drift and still count as inside
INSTRUCTION_TOP = 1600        # the gray instruction band starts here on every styling page

# page title keyword -> which part of the pack the page styles
PAGE_KEYS = [("your fonts", "fonts"), ("your colors", "colors"), ("hook", "hook"),
             ("caption", "captions"), ("side comment", "side"), ("takeover", "takeover"),
             ("name tag", "name_tag"), ("end card", "end_card"), ("screen frame", "screen_frame")]
TEMPLATE_ONLY = ("cover", "make a copy", "install", "add or delete", "before you use", "your own page")


def resolve_font(name):
    if not name or _cf is None:
        return ""
    try:
        return _cf.resolve_font_file(name) or ""
    except Exception:
        return ""


# ── reading Canva's element JSON ──────────────────────────────────────────────
def _hex(c):
    return (c or "").strip().lower()

def _solid(fill):
    col = (fill or {}).get("color") or {}
    return _hex(col.get("color")) if col.get("type") == "solid" else ""

def is_zone(el):
    """A purple dashed "style me" outline: a shape whose stroke is the template purple, big enough to
    hold something (the 62px legend square is excluded by size)."""
    if el.get("type") not in ("shape", "rect"):
        return False
    if min(el.get("width", 0), el.get("height", 0)) < 90:
        return False
    strokes = [p.get("stroke") or {} for p in el.get("paths") or []] + [el.get("stroke") or {}]
    return any(_hex((s.get("color") or {}).get("color")) == PURPLE and (s.get("weight") or 0) >= 3
               for s in strokes)

def is_template_part(el):
    """The pill tag, a purple outline, or anything whose text is a template tag."""
    if is_zone(el):
        return True
    for p in el.get("paths") or []:
        if _solid(p.get("fill")) == PURPLE:
            return True
    if _solid(el.get("fill")) == PURPLE:
        return True
    return text_of(el).strip().upper() in TEMPLATE_TAGS

def text_of(el):
    regs = el.get("textRegions") or []
    for tc in el.get("textContents") or []:
        regs = regs + (tc.get("textRegions") or [])
    return "".join(r.get("characters", "") for r in regs)

def runs(el):
    return [r for r in (el.get("textRegions") or []) if r.get("characters", "").strip()]

def center(el):
    return (el.get("left", 0) + el.get("width", 0) / 2, el.get("top", 0) + el.get("height", 0) / 2)

def inside(el, zone):
    """Centered inside the outline across, and wholly inside it top to bottom. Text boxes run wider
    than their outline, so width is judged by the center; the stand-in person runs far taller than
    any outline it crosses, so height is judged by the whole box."""
    x, _ = center(el)
    top, bot = el.get("top", 0), el.get("top", 0) + el.get("height", 0)
    return (zone["left"] - ZONE_PAD <= x <= zone["left"] + zone["width"] + ZONE_PAD and
            top >= zone["top"] - ZONE_PAD and bot <= zone["top"] + zone["height"] + ZONE_PAD)

def page_kind(page):
    t = (page.get("title") or "").lower()
    if any(k in t for k in TEMPLATE_ONLY):
        return "template"
    for key, kind in PAGE_KEYS:
        if key in t:
            return kind
    texts = [text_of(e).lower() for e in page.get("elements") or []]
    if sum(1 for s in texts if s.startswith("font name:")) >= 2:
        return "fonts"
    return "custom"

def hers(page):
    """Everything on the page that is the creator's: inside a style-me zone, not a template part,
    not in the gray instruction band. Grouped by zone, zones top to bottom."""
    els = page.get("elements") or []
    zones = sorted([e for e in els if is_zone(e)], key=lambda z: z["top"])
    groups = []
    for z in zones:
        members = [e for e in els if not is_template_part(e) and e is not z and inside(e, z)
                   and e.get("top", 0) < INSTRUCTION_TOP
                   and not (e.get("width", 0) >= 1000 and e.get("height", 0) >= 1800)]
        groups.append(sorted(members, key=lambda e: e.get("top", 0)))
    return groups

def page_background(page):
    """The last full-page solid rectangle that is not white (white is the page base under every
    import) and not the gray footage gradient."""
    bg = ""
    for e in page.get("elements") or []:
        if e.get("width", 0) >= 1000 and e.get("height", 0) >= 1800:
            c = _solid(e.get("fill"))
            if c and c != "#ffffff":
                bg = c
    return bg

def shape_fill(el):
    for p in el.get("paths") or []:
        c = _solid(p.get("fill"))
        if c and c != "#000000":      # Canva writes the stroke-only path with a black placeholder fill
            return c
    return _solid(el.get("fill"))

def text_style(el, font_names):
    rs = runs(el)
    if not rs:
        return None
    f = rs[0].get("formatting") or {}
    colors = []
    for r in rs:
        c = _hex((r.get("formatting") or {}).get("color"))
        if c and c not in colors:
            colors.append(c)
    ref = f.get("fontRef", "")
    chars = "".join(r.get("characters", "") for r in rs)
    letters = [ch for ch in chars if ch.isalpha()]
    if letters and all(ch.isupper() for ch in letters):
        case = "upper"
    elif letters and all(ch.islower() for ch in letters):
        case = "unsure"               # typed lowercase: may be showing in caps via Canva's toggle
    else:
        case = "title" if chars.istitle() else "mixed"
    return {"text": chars, "font_ref": ref, "font": font_names.get(ref.split(",")[0], ""),
            "weight": f.get("fontWeight", ""), "size": f.get("fontSize"), "colors": colors,
            "color": colors[0] if colors else "", "case": case}


# ── the mapping ───────────────────────────────────────────────────────────────
def read_design(data):
    if isinstance(data, dict) and "design_content" in data:
        data = data["design_content"]
    pages = data.get("pages") if isinstance(data, dict) else data
    if not pages:
        sys.exit("canva_to_pack: no pages in that file. Save the read-design result's design_content.")
    return pages

def extract(pages):
    kinds = {}
    custom = []
    for p in pages:
        k = page_kind(p)
        if k == "custom":
            custom.append(p)
        elif k != "template":
            kinds.setdefault(k, p)

    report = {"fonts": {}, "colors": {}, "elements": {}, "extras": {}, "problems": [],
              "custom_pages": [], "unsure_case": []}

    # 1) fonts: each zone on the fonts page holds a sample + its typed "font name: X"
    font_names = {}                       # fontRef id -> typed family name
    roles = ["main", "caption", "accent"]
    if "fonts" in kinds:
        for role, group in zip(roles, hers(kinds["fonts"])):
            name, sample = "", None
            for e in group:
                t = text_of(e).strip()
                if t.lower().startswith("font name:"):
                    name = t.split(":", 1)[1].strip()
                elif sample is None and runs(e):
                    sample = e
            if not name:
                report["problems"].append(f"the {role} font has no name typed after 'font name:'")
            if sample is not None:
                ref = ((runs(sample)[0].get("formatting") or {}).get("fontRef") or "").split(",")[0]
                if ref and name:
                    prev = font_names.get(ref)
                    if prev and prev.lower() != name.lower():
                        report["problems"].append(
                            f"two different font names ({prev}, {name}) were typed for the same font")
                    font_names[ref] = name
            report["fonts"][role] = name
    else:
        report["problems"].append("no 'your fonts' page found")

    # 2) colors: text / accent / background squares, top to bottom
    if "colors" in kinds:
        for role, group in zip(["text", "accent", "background"], hers(kinds["colors"])):
            fills = [shape_fill(e) for e in group if e.get("type") in ("shape", "rect")]
            fills = [c for c in fills if c]
            if fills:
                report["colors"][role] = fills[0]
            else:
                report["problems"].append(f"no {role} color square found inside its purple box")
    else:
        report["problems"].append("no 'your colors' page found")

    def first_text(kind, index=0):
        if kind not in kinds:
            return None
        texts = [e for g in hers(kinds[kind]) for e in g if runs(e)]
        return text_style(texts[index], font_names) if len(texts) > index else None

    el = report["elements"]
    el["headline"] = first_text("hook")
    el["caption"] = first_text("captions")
    el["thought_bubble"] = first_text("side", 0)
    el["accent_caption"] = first_text("side", 1)
    el["takeover"] = first_text("takeover")
    if "takeover" in kinds:
        report["extras"]["takeover_background"] = page_background(kinds["takeover"])
    if "name_tag" in kinds:
        g = [e for grp in hers(kinds["name_tag"]) for e in grp]
        boxes = [shape_fill(e) for e in g if e.get("type") in ("shape", "rect") and shape_fill(e)]
        texts = [text_style(e, font_names) for e in g if runs(e)]
        report["extras"]["name_tag"] = {"box": boxes[0] if boxes else "",
                                        "name": texts[0] if texts else None,
                                        "role_line": texts[1] if len(texts) > 1 else None}
    if "end_card" in kinds:
        texts = [text_style(e, font_names) for grp in hers(kinds["end_card"]) for e in grp if runs(e)]
        report["extras"]["end_card"] = {"background": page_background(kinds["end_card"]),
                                        "lines": texts}
    for p in custom:
        texts = [text_style(e, font_names) for grp in hers(p) for e in grp if runs(e)]
        report["custom_pages"].append({"title": p.get("title") or "(no page title)",
                                       "background": page_background(p),
                                       "texts": [t for t in texts if t]})

    # fonts on the styling pages that were never named on the fonts page
    for key, st in list(el.items()):
        if st is None:
            continue
        if st["font_ref"] and not st["font"]:
            report["problems"].append(
                f"{key}: uses a font that is not on the 'your fonts' page, so its name is unknown")
        if st["case"] == "unsure":
            report["unsure_case"].append(key)
    return report


def build_block(name, rep, case_overrides):
    fonts = rep["fonts"]
    main = fonts.get("main") or "Inter"
    cap = fonts.get("caption") or main
    acc = fonts.get("accent") or cap
    cols = rep["colors"]
    text_c = cols.get("text") or "#ffffff"
    accent = cols.get("accent") or "#fdc341"
    bg = rep["extras"].get("takeover_background") or cols.get("background") or "#317ae1"

    dark = pr._lum(bg) < 0.35
    r = pr.build(name, accent, bg, "", dark)
    # her background IS the card ground; her text color is its ink when it reads on it
    r["ground"] = bg
    ink = text_c if pr.contrast(text_c, bg) >= 4.5 else ("#ffffff" if dark else "#1a1a17")
    r["ink"] = ink
    if dark:
        r["palette"]["dark"], r["palette"]["light"] = bg, ink
        r["card"].update({"ground": "dark", "ink": "light"})
    else:
        r["palette"]["light"], r["palette"]["dark"] = bg, ink
        r["card"].update({"ground": "light", "ink": "dark"})
    r["palette"]["accent"] = accent
    r["palette"]["pop2"] = bg
    r["hands_off_accent"] = accent if pr.contrast(accent, bg) >= 3.0 else pr.text_safe(accent, bg, 3.0)
    r["treatment"] = re.sub(r"Ground \S+ · ink \S+", f"Ground {bg} · ink {ink}", r["treatment"])

    # the read-along highlight is the colored word on the captions page when she set one there
    cap_st = rep["elements"].get("caption") or {}
    highlight = next((c for c in cap_st.get("colors", []) if c != cap_st.get("color")), accent)

    block = pr.clone_element_block(BASE, main, cap, acc, highlight)
    elements = block.get("elements") or {}
    missing = []
    for key, st in rep["elements"].items():
        e = elements.get(key)
        if not isinstance(e, dict):
            continue
        if st and st.get("font"):
            e["font"] = st["font"]
        if st and st["case"] in ("upper", "title"):
            e["case"] = st["case"]
        if key in case_overrides:
            e["case"] = case_overrides[key]
        e["file"] = resolve_font(e.get("font"))
        if not e["file"] and e.get("font") and e["font"] not in missing:
            missing.append(e["font"])

    wd = block.setdefault("welldone", {})
    head = rep["elements"].get("headline") or {}
    if head.get("color") and head["color"] != "#ffffff":
        wd["hook_color"] = head["color"]

    block["canva"] = {k: v for k, v in rep["extras"].items() if v}
    if rep["custom_pages"]:
        block["canva"]["custom_pages"] = rep["custom_pages"]
    block["vibe"] = "styled in Canva"
    block["_recipe"] = (f"Built by canva_to_pack from her Canva Style Pack. Layout cloned from {BASE}; "
                        f"fonts, colors and case are hers.")
    return block, r, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--design", required=True, help="JSON file: the read-design result (design_content)")
    ap.add_argument("--name", required=True, help="what to call the pack")
    ap.add_argument("--case", action="append", default=[],
                    help="role=upper|lower|title, after checking the page thumbnail (repeatable)")
    ap.add_argument("--write", action="store_true", help="save it through pack_write (protected copy)")
    ap.add_argument("--force", action="store_true", help="with --write: replace her pack of the same name")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    pages = read_design(json.load(open(a.design, encoding="utf-8")))
    rep = extract(pages)
    overrides = {}
    for c in a.case:
        k, _, v = c.partition("=")
        if v not in ("upper", "lower", "title", "sentence"):
            sys.exit(f"--case {c}: use upper, lower, title or sentence")
        overrides[k.strip()] = v
    rep["unsure_case"] = [k for k in rep["unsure_case"] if k not in overrides]
    block, r, missing = build_block(a.name, rep, overrides)

    if a.json:
        print(json.dumps({"name": a.name, "read": rep, "block": block, "palette": r["palette"],
                          "missing_fonts": missing}, indent=2))
    else:
        print(f"── CANVA → PACK: {a.name} ──")
        f = rep["fonts"]
        print(f"  fonts: main={f.get('main') or '?'} · caption={f.get('caption') or '?'} · "
              f"accent={f.get('accent') or '?'}")
        c = rep["colors"]
        print(f"  colors: text={c.get('text', '?')} · accent={c.get('accent', '?')} · "
              f"background={c.get('background', '?')}")
        for key, st in rep["elements"].items():
            if st:
                print(f"  {key}: {st['font'] or 'UNNAMED FONT'} · {st['color']} · case {st['case']}")
        for pg in rep["custom_pages"]:
            print(f"  her own page: {pg['title']}")
        if rep["unsure_case"]:
            print(f"  ? case unclear (check the thumbnail, then pass --case): {', '.join(rep['unsure_case'])}")
        for p in rep["problems"]:
            print(f"  ⚠ {p}")
        if missing:
            print(f"  ⚠ not installed yet: {', '.join(missing)} — install it, pick it once in CapCut, re-run")
        else:
            print("  ✓ every font resolved to a real file")

    if a.write:
        if rep["problems"] or missing:
            sys.exit("  ⛔ not written: fix the items above first (a pack with a missing or unnamed font "
                     "renders in a substitute, and that is never silent).")
        import pack_write
        try:
            print(pack_write.apply(a.name, block, r, force=a.force))
        except pack_write.PackWriteError as e:
            sys.exit(f"  ⛔ not written: {e}")


if __name__ == "__main__":
    main()
