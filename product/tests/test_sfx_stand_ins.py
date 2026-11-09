#!/usr/bin/env python3
"""Every sound the engine names by hand still plays on an engine without the owner's CapCut sounds.

The owner's own CapCut sounds (product/creative-vault/sfx/approved/ and the older cue files at the top of sfx/)
never ship: make-ship.sh leaves them out. A few names in the engine's own code pointed at them (the first-reel
script's takeover and count-up sounds among them), so on a buyer's engine those names resolved to nothing and
the effect played silent. Each now falls back to a shipped sound that does the same job, and wherever the real
file is present, the real file still wins.

Run: python3 product/tests/test_sfx_stand_ins.py   (Windows: python)
"""
import importlib.util
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *rel.split("/")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cs = load("capcut_sfx", "product/capcut_sfx.py")
sc = load("spoken_cues", "product/spoken_cues.py")
SFX = os.path.join(ROOT, "product", "creative-vault", "sfx")
AUDIO = (".mp3", ".wav", ".m4a")

print("1. on an engine as a buyer receives it (no CapCut sounds)")
with tempfile.TemporaryDirectory() as tmp:
    buyer = os.path.join(tmp, "sfx")
    os.makedirs(buyer)
    for name in os.listdir(SFX):
        src = os.path.join(SFX, name)
        if name == "approved" or (os.path.isfile(src) and name.lower().endswith(AUDIO)):
            continue                                   # exactly what make-ship leaves out
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, os.path.join(buyer, name))
    real_dir, real_fav, real_index = cs.SFX_DIR, cs.FAVORITES_DIR, cs._INDEX
    # The owner's index switches some toolkit cues off because her CapCut sounds cover them; make-ship switches
    # them back on in the index a buyer receives. This checks what RESOLVES, so no switch-off applies here.
    cs.SFX_DIR, cs.FAVORITES_DIR, cs._INDEX = buyer, os.path.join(tmp, "no-favorites"), os.path.join(tmp, "none.json")
    try:
        pal = cs.palette()
        for effect, (name, _trim) in sorted(sc.SFX.items()):
            got = cs.resolve_cue(name, pal)
            check(f"the {effect} cue's sound ({name}) plays", bool(got and os.path.isfile(got[0])), got)
        for name in sorted(cs._STAND_INS):
            got = cs.resolve_cue(name, pal)
            check(f"{name} falls back to a shipped sound ({cs._STAND_INS[name]})",
                  bool(got and os.path.isfile(got[0]) and "approved" not in got[0]), got)
    finally:
        cs.SFX_DIR, cs.FAVORITES_DIR, cs._INDEX = real_dir, real_fav, real_index

print("\n2. where the real file is there, it wins")
approved = os.path.join(SFX, "approved")
if os.path.isdir(approved):
    pal = cs.palette()
    for name in ("pop-whoosh", "coin-earn"):
        own = [f for f in os.listdir(approved) if os.path.splitext(f)[0] == name]
        if own:
            got = cs.resolve_cue(name, pal)
            check(f"{name} is still the owner's own file", bool(got) and os.path.basename(got[0]) == own[0], got)
else:
    print("  (skipped: this copy of the engine has no CapCut sounds, as in every copy a buyer receives)")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "every sound the engine names plays, with or without the CapCut sounds"))
sys.exit(1 if fails else 0)
