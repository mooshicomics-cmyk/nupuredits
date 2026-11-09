#!/usr/bin/env python3
"""The Clean Captions hook sits below the platform's top band, and that band comes from safe_zones.

The preset used to carry its own numbers: a top band of 200 and the hook's top edge at y250, which is inside
the 270px band where Instagram draws its Reels header. Its own check compared against its own 200, so it
passed. The hook now takes the band from product/safe_zones.py and sits just under it. This pins that, reads
where a real rendered hook's ink starts in the starter look and in every pack, checks the three hook shapes
and the look it resolves (her pack, or the starter), and checks the line onboarding writes the creator's
hook into kept its exact form (the updater saves and restores that line as written).

Run: python3 product/tests/test_clean_captions_band.py
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
import safe_zones

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + detail) if detail else ''}")


BUILD = os.path.join(ROOT, "presets", "clean-captions", "build.py")
spec = importlib.util.spec_from_file_location("clean_captions_build", BUILD)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

check("the top band is safe_zones.TOP", cc.SAFE_TOP == safe_zones.TOP, f"{cc.SAFE_TOP} != {safe_zones.TOP}")
check("the bottom line is safe_zones.BOTTOM", cc.SAFE_BOT == safe_zones.BOTTOM, f"{cc.SAFE_BOT} != {safe_zones.BOTTOM}")
check("the hook's first ink is below the band", cc.HOOK_TOP >= safe_zones.TOP, f"HOOK_TOP {cc.HOOK_TOP}")
check("no longer the old y250 inside the band", cc.HOOK_TOP != 250)

import stylepack
looks = [cc.resolve_look("starter")] + [cc.resolve_look(name) for name in stylepack.names()]
for look in looks:
    for copy in ("the part nobody tells you", "nobody warns you\nabout winning",
                 "this hook is deliberately far too long for one line\nso the headline has to wrap it over and over"):
        img, x, y, top, bottom, rows = cc.render_hook(copy, look)
        box = img.getbbox()
        tag = f"{look['name']}: {copy[:20]!r}"
        check(f"rendered hook clears the top band ({tag})", top >= safe_zones.TOP and y + box[1] >= 0,
              f"ink starts at y{top}")
        check(f"rendered hook ends above the bottom line ({tag})", bottom <= safe_zones.BOTTOM, f"ink ends at y{bottom}")
    check(f"{look['name']}: captions never below the legibility floor",
          look["cap_px"] >= safe_zones.MIN_PX["caption"], look["cap_px"])

# the three hook shapes (workflows/capcut-export/WRITING-THE-HOOK.md), reading order never changes
check("one line is a hook card", cc.hook_parts("the part nobody tells you") == [("the part nobody tells you", "headline")])
check("two lines are eyebrow + headline by default",
      cc.hook_parts("nobody warns you\nabout winning") == [("nobody warns you", "quiet"), ("about winning", "headline")])
check("emphasis first is headline + subhead",
      cc.hook_parts("nobody warns you\nabout winning", "first") == [("nobody warns you", "headline"), ("about winning", "quiet")])
check("blank lines are not a shape", cc.hook_parts("one\n\n  \ntwo") == [("one", "quiet"), ("two", "headline")])
check("no copy, no hook", cc.hook_parts("   \n  ") == [] and cc.render_hook("  ", cc.resolve_look("starter")) is None)

# the look: a pack she chose, else the starter; a pack that cannot be drawn never stops the captions
check("'starter' asks for the starter look", cc.resolve_look("starter")["name"] == "starter")
odd = cc.resolve_look("No Such Pack")
check("an unknown pack falls back to the starter look and says why", odd["name"] == "starter" and "No Such Pack" in odd["why"], odd["why"])
for name in stylepack.names():
    got = cc.resolve_look(name)
    check(f"{name} resolves to its own look (or says why not)", got["name"] == name or name in got["why"], got["why"])

# phrases: every word she kept is captioned, however short; each phrase holds until the next, the last lingers
_w = lambda t, s, e: {"text": t, "disp": t, "start": s, "end": e}
ph = cc.phrases([_w("Okay,", 0.0, 0.1), _w("this", 0.5, 0.7), _w("is", 0.7, 0.8), _w("it.", 0.8, 1.0),
                 _w("Next", 2.0, 2.3), _w("line", 2.3, 2.6)])
check("a one-word phrase of a tenth of a second is still captioned",
      [p["text"] for p in ph] == ["Okay", "this is it", "Next line"], str(ph))
check("it stays up until the next phrase starts", ph and ph[0]["end"] == 0.5, str(ph))
check("every word is in a phrase", sum(len(p["said"]) for p in ph) == 6, str(ph))
check("a phrase holds until the next starts", ph and ph[1]["end"] == 2.0, str(ph))
check("the last phrase holds past her last word", ph and abs(ph[-1]["end"] - (2.6 + cc.FINAL_HOLD)) < 1e-9, str(ph))

# a one-word phrase that would only flash rides with a neighbour: forward for a lead-in, back for a closing word
ph = cc.phrases([_w("for", 4.69, 4.93), _w("us.", 5.05, 5.19), _w("No,", 5.44, 5.58), _w("seriously.", 5.60, 6.00),
                 _w("this", 6.2, 6.37), _w("one", 6.47, 6.61), _w("is", 6.70, 6.80), _w("it.", 6.81, 6.95),
                 _w("Big", 7.6, 7.9), _w("deal.", 7.95, 8.3)])
check("a flash of one word joins the phrase after it", [p["text"] for p in ph][:2] == ["for us", "No, seriously"], str(ph))
check("and every word still shows", sum(len(p["said"]) for p in ph) == 10, str(ph))

# when the hook leaves: a time given for the reel; else as she moves on from a cue word; else the sentence
# break nearest the hook block's ~8 s
talk = [_w("Okay", 0.2, 0.5), _w("so", 0.6, 0.8), _w("here.", 0.9, 1.4), _w("Then", 3.0, 3.3), _w("more.", 3.4, 7.6),
        _w("And", 8.4, 8.6), _w("this", 8.7, 9.0), _w("one", 9.1, 9.6), _w("ends.", 9.7, 12.0), _w("Last", 12.5, 13.0)]
check("a time given for the reel wins", cc.hook_exit(talk, 3.4)[0] == 3.4)
check("no cue words: the sentence break nearest 8 s", cc.hook_exit(talk)[0] == 8.4, str(cc.hook_exit(talk)))
real_cues = cc.HOOK_CUE_WORDS
try:
    cc.HOOK_CUE_WORDS = ("so",)
    check("a cue word: the hook leaves as her next word begins", cc.hook_exit(talk)[0] == 0.9, str(cc.hook_exit(talk)))
    cc.HOOK_CUE_WORDS = ()
    real_old = cc.HOOK_END_WORDS
    cc.HOOK_END_WORDS = ("Then",)
    check("the older setting name still sets the cue", cc.hook_exit(talk)[0] == 3.4, str(cc.hook_exit(talk)))
    cc.HOOK_END_WORDS = real_old
finally:
    cc.HOOK_CUE_WORDS = real_cues
check("no words at all: the hook block's own hold", cc.hook_exit([])[0] == cc.HOOK_HOLD)

# The card never moves or shrinks on its own; being high in the frame, or a long hook, is only raised with her
import json, tempfile


def notes(zones, rows=1):
    with tempfile.TemporaryDirectory() as job:
        if zones is not None:
            with open(os.path.join(job, "subject-zones.json"), "w", encoding="utf-8") as fh:
                json.dump(zones, fh)
        return cc.hook_notes(job, 280, 390, rows)


check("framed low: nothing to raise", notes({"subject": {"head_top": 520}}) == [])
high = notes({"subject": {"head_top": 316}})
check("framed high: raised as her choice, never a failure", len(high) == 1 and "y316" in high[0]
      and "placed as always" in high[0], high)
check("never measured: nothing to raise (and nothing moves)", notes(None) == [])
long_ = notes(None, rows=3)
check("a long hook: raised, still full size", len(long_) == 1 and "3 lines" in long_[0] and "full size" in long_[0], long_)
check("the preset has no code path that stops the build over the hook", "hook_clears_her" not in open(BUILD, encoding="utf-8").read())

with open(BUILD, encoding="utf-8") as fh:
    lines = fh.read().splitlines()
check("the onboarding hook line kept its exact form",
      any(l.startswith('DEFAULT_HOOK_TEXT = ""  #') for l in lines))
check("HOOK_END_WORDS is still a plain assignment", "HOOK_END_WORDS = ()" in lines)
import settings_persist
check("an update keeps her hook settings under either name",
      {v for r, v in settings_persist.CONSTANTS if r.endswith("clean-captions/build.py")}
      >= {"DEFAULT_HOOK_TEXT", "HOOK_END_WORDS", "HOOK_COPY", "HOOK_CUE_WORDS"})
check("the engine's own names are plain assignments too",
      any(l.startswith('HOOK_COPY = ""') for l in lines) and any(l.startswith("HOOK_CUE_WORDS = ()") for l in lines))

if fails:
    print(f"test_clean_captions_band: FAILED {len(fails)}/{total}: " + " | ".join(fails))
    sys.exit(1)
print(f"test_clean_captions_band: all {total} checks passed")
