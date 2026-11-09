#!/usr/bin/env python3
"""A pack she builds borrows a shipped pack's LAYOUT, never its typefaces or its colors.

/studio recipe (pack_recipe.py) and the frame-pack flow (frame_to_pack.py) both clone a launch pack's locked
sizes and swap in her three fonts. Two things came along that are not layout:
  * the base pack's PINNED fonts. They live at the pack's top level (Playful's eyebrow is Ugly Dave, Butter's
    eyebrow is Bloop and its karaoke line is Inter), and the builders read them there, so her pack's eyebrow
    rendered in a font she never chose. frame_to_pack tried to drop them, but looked in `welldone`.
  * the base pack's hook and eyebrow COLORS (Butter's rendered hook is its butter yellow).
Everything else about the base (sizes, tracking, line height, positions, the welldone tuning) must still come
through unchanged, because that is the part a clone is for.

Case is NOT layout. Butter's headline and takeover are ALL CAPS, so a pack built from Butter came out shouting in
caps she never chose, and kept doing it once she made that pack her default (a buyer, 2026-10-20). The headline and
takeover now take her answer (--case), a frame's own caps / lowercase marking, or with neither her words as typed.

Reads the shipped style-packs.json and writes nothing (frame_to_pack runs with --json, under its own HOME).

Run: python3 product/tests/test_pack_clone.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import pack_recipe

PINS = ("subhead_font_file", "subhead_font_name", "karaoke_font_file", "karaoke_font_name")
COLORS = ("hook_color", "subhead_color")
fails = []


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


LOUD = ("headline", "takeover")


def same_layout(label, base, block):
    """Everything a clone is FOR survives: per-element layout, welldone tuning, the rest of the pack. The loud
    roles' case is hers, not layout (checked on its own below)."""
    for kind, el in base["elements"].items():
        got = block["elements"].get(kind, {})
        skip = ("font", "file", "case") if kind in LOUD else ("font", "file")
        diff = sorted(k for k in set(el) | set(got) if k not in skip and el.get(k) != got.get(k))
        check(f"{label}: {kind} keeps the base layout", not diff, f"changed: {diff}")
    wd_base = {k: v for k, v in (base.get("welldone") or {}).items() if k not in COLORS}
    check(f"{label}: the welldone tuning comes through", block.get("welldone") == wd_base,
          json.dumps({"base": wd_base, "clone": block.get("welldone")})[:400])
    for k in ("subhead_source", "capcut", "line_height_override", "subhead_weight"):
        if k in base:
            check(f"{label}: '{k}' comes through", block.get(k) == base[k], f"{base[k]!r} -> {block.get(k)!r}")


def main():
    with open(os.path.join(PRODUCT, "creative-vault", "style-packs.json"), encoding="utf-8") as fh:
        packs = json.load(fh)["packs"]
    bases = [k for k, v in packs.items() if v.get("in_launch_kit")]
    check("there are launch packs to clone", bool(bases))
    check("the case this guards is real: a launch pack pins a font at its top level",
          any(k in packs[b] for b in bases for k in PINS))

    for base in bases:
        block = pack_recipe.clone_element_block(base, "Clash Display", "Inter", "Caveat", "#E8502E")
        label = f"recipe on {base}"
        check(f"{label}: none of the base pack's pinned fonts", not [k for k in PINS if k in block],
              f"{ {k: block[k] for k in PINS if k in block} }")
        check(f"{label}: none of the base pack's hook / eyebrow colors",
              not [k for k in COLORS if k in (block.get("welldone") or {})],
              f"{ {k: block['welldone'][k] for k in COLORS if k in (block.get('welldone') or {})} }")
        check(f"{label}: her fonts, by role",
              block["fonts"] == {"main": "Clash Display", "accent": "Caveat", "caption": "Inter"}
              and block["elements"]["headline"]["font"] == "Clash Display"
              and block["elements"]["caption"]["font"] == "Inter"
              and block["elements"]["accent_caption"]["font"] == "Caveat", json.dumps(block["fonts"]))
        check(f"{label}: her accent, and never a launch pack", block["accent_color"] == "#E8502E"
              and block["in_launch_kit"] is False)
        same_layout(label, packs[base], block)
        cases = {k: block["elements"][k]["case"] for k in LOUD}
        check(f"{label}: headline + takeover keep her words as typed when she named no case",
              cases == {"headline": "as-written", "takeover": "as-written"},
              f"{cases} (the base {base} has {({k: packs[base]['elements'][k]['case'] for k in LOUD})})")
        check(f"{label}: the caption keeps the layout's case",
              block["elements"]["caption"]["case"] == packs[base]["elements"]["caption"]["case"])
        up = pack_recipe.clone_element_block(base, "Clash Display", "Inter", "Caveat", "#E8502E", case="ALL CAPS")
        check(f"{label}: --case upper (any spelling) puts both loud roles in caps",
              all(up["elements"][k]["case"] == "upper" for k in LOUD))
        mix = pack_recipe.clone_element_block(base, "Clash Display", "Inter", "Caveat", "#E8502E",
                                              case={"headline": "as typed", "takeover": "upper"}, caption_case="none")
        check(f"{label}: case per role, and her caption case",
              mix["elements"]["headline"]["case"] == "as-written" and mix["elements"]["takeover"]["case"] == "upper"
              and mix["elements"]["caption"]["case"] == "as-written",
              json.dumps({k: mix["elements"][k]["case"] for k in ("headline", "takeover", "caption")}))
        keep = pack_recipe.clone_element_block(base, "Clash Display", "Inter", "Caveat", "#E8502E", case=None)
        check(f"{label}: case=None keeps the base's (a caller that sets each role itself, as canva_to_pack does)",
              all(keep["elements"][k]["case"] == packs[base]["elements"][k]["case"] for k in LOUD))

    # the CLI: the recipe route takes --case, and Butter as the base never forces caps
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "pack_recipe.py"), "--name", "Sunrise", "--main",
                        "Clash Display", "--caption", "Inter", "--accent", "Caveat", "--primary", "#E8502E",
                        "--secondary", "#F5C518", "--base", "Butter"], capture_output=True, text=True, cwd=ROOT,
                       env={**os.environ, "PYTHONUTF8": "1"})
    check("pack_recipe --base Butter, no --case: says her words stay as typed",
          r.returncode == 0 and "headline as she types it" in r.stdout and '"case": "upper"' not in r.stdout,
          (r.stdout + r.stderr)[-600:])
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "pack_recipe.py"), "--name", "Sunrise", "--main",
                        "Clash Display", "--caption", "Inter", "--accent", "Caveat", "--primary", "#E8502E",
                        "--secondary", "#F5C518", "--base", "Editorial", "--case", "upper"],
                       capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})
    check("pack_recipe --case upper on Editorial: ALL CAPS", r.returncode == 0 and "headline ALL CAPS" in r.stdout
          and "takeover ALL CAPS" in r.stdout, (r.stdout + r.stderr)[-600:])

    home = tempfile.mkdtemp()
    try:
        for base in bases:
            r = subprocess.run([sys.executable, os.path.join(PRODUCT, "frame_to_pack.py"), "--frame",
                                "editorial-forest", "--name", "Forest", "--base", base, "--json"],
                               capture_output=True, text=True, cwd=ROOT,
                               env={**os.environ, "HOME": home, "PYTHONUTF8": "1"})
            label = f"frame_to_pack on {base}"
            try:
                block = json.loads(r.stdout)["block"]
            except (ValueError, KeyError):
                check(f"{label}: runs", False, (r.stdout + r.stderr)[-600:])
                continue
            check(f"{label}: none of the base pack's pinned fonts", not [k for k in PINS if k in block],
                  f"{ {k: block[k] for k in PINS if k in block} }")
            check(f"{label}: none of the base pack's hook / eyebrow colors",
                  not [k for k in COLORS if k in (block.get("welldone") or {})])
            same_layout(label, packs[base], block)
            check(f"{label}: a frame that sets no caps keeps her words as typed (never the base's case)",
                  all(block["elements"][k]["case"] == "as-written" for k in LOUD),
                  json.dumps({k: block["elements"][k]["case"] for k in LOUD}))

        def ftp(*args):
            r = subprocess.run([sys.executable, os.path.join(PRODUCT, "frame_to_pack.py"), *args, "--json"],
                               capture_output=True, text=True, cwd=ROOT,
                               env={**os.environ, "HOME": home, "PYTHONUTF8": "1"})
            try:
                return {k: v["case"] for k, v in json.loads(r.stdout)["block"]["elements"].items() if k in LOUD}
            except (ValueError, KeyError):
                return {"error": (r.stdout + r.stderr)[-400:]}
        got = ftp("--frame", "blockframe", "--name", "Block", "--base", "Editorial")
        check("frame_to_pack: a frame whose headlines are set in caps gives caps, on a lowercase base",
              got == {"headline": "upper", "takeover": "upper"}, json.dumps(got))
        got = ftp("--frame", "broadside", "--name", "Broad", "--base", "Butter")
        check("frame_to_pack: a frame whose headlines are set lowercase gives lowercase, on Butter",
              got == {"headline": "lower", "takeover": "lower"}, json.dumps(got))
        got = ftp("--frame", "blockframe", "--name", "Block", "--case", "as-written")
        check("frame_to_pack: her --case wins over the frame", got == {"headline": "as-written",
                                                                         "takeover": "as-written"}, json.dumps(got))
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_pack_clone():
    """pytest entry: the same checks as running this file."""
    fails.clear()
    main()
    assert not fails, "; ".join(fails)


if __name__ == "__main__":
    main()
    if fails:
        print(f"pack clone: FAILED {len(fails)}: {'; '.join(fails)}")
        sys.exit(1)
    print("pack clone: a built pack takes the base pack's layout, and only its layout")
