#!/usr/bin/env python3
"""build-pack-showcase.py PACK — SHIPPABLE "pick your style" preview.

Renders the 4 elements (hook · caption · thought bubble · full-screen takeover) animating in the CHOSEN
pack's REAL fonts / sizes / case / accent, over a neutral background. No personal reel, no footage — this
is the buyer-facing style preview, generated straight from product/creative-vault/style-packs.json.

  python3 product/build-pack-showcase.py Editorial      # emit the composition
  (cd projects/_pack-preview/Editorial && npm run render)  # render to MP4

LAYOUT + animation are FIXED (same 4 behaviors every pack); the pack only swaps font/size/case/accent.
"""
import os, sys, shutil
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stylepack
import safe_zones   # the SAME in-feed legibility floors the real builder applies

PACK = sys.argv[1] if len(sys.argv) > 1 else "Editorial"
SIZE_SCALE = float(os.environ.get("SIZE_SCALE", "6.0"))     # px per CapCut size unit (locked calibration)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/projects/_pack-preview/{PACK}"
FDIR = f"{OUT}/fonts"
os.makedirs(FDIR, exist_ok=True)

pack   = stylepack.load(PACK)
ACCENT = pack.get("accent_color") or "#ffffff"
# The colors the real builder (build-reel-type.py) draws with, so the preview tells the truth about the pack: the
# hook in the pack's hook color (it was always white here), the plain words in its text color.
_WD = pack.get("welldone", {})
HOOK_COLOR = _WD.get("hook_color") or "#fff"
TEXT_COL = _WD.get("text_color") or "#fff"
TK_WHITE = bool(_WD.get("takeover_white", False))
def px(e, role=None):
    """Pack size in px, floored at the role's in-feed minimum.

    The real builder raises any role that lands under safe_zones.MIN_PX, so a preview that skips the floor
    shows the buyer a caption smaller than the one they will actually get — the preview has to tell the
    truth about the pack or it is not a preview."""
    v = max(20, round(e["size"] * SIZE_SCALE))
    return max(v, safe_zones.MIN_PX.get(role, 0)) if role else v
def caseit(s, e, first=True):
    """The pack's case for this element, read the way every builder reads it (any spelling of "as is" / "as
    written" keeps the words as written; it used to lowercase anything it didn't recognize). Caption and takeover
    words go one at a time, so sentence case keeps them as written; a later piece of the hook (first=False) is
    mid-sentence too."""
    role = "caption" if e is C else ("takeover" if e is TK else None)
    rule = stylepack.case_rule(e.get("case", "lower"), role)
    return s if (rule == "sentence" and not first) else stylepack.apply_case(s, rule)

_faces, _css = {}, []
def face(e):
    fam = "".join(c for c in e["font"] if c.isalnum()) or "F"
    if fam not in _faces:
        ext = os.path.splitext(e["file"])[1] or ".ttf"
        dst = f"{fam}{ext}"
        try: shutil.copy(e["file"], f"{FDIR}/{dst}")
        except Exception as ex: print(f"  ⚠ font copy failed for {e['font']}: {ex}")
        _css.append(f"@font-face{{font-family:'{fam}';src:url('fonts/{dst}');}}")
        _faces[fam] = fam
    return fam

H, C, TH, TK = (stylepack.element(PACK, k) for k in ("headline", "caption", "thought_bubble", "takeover"))
fH, fC, fTH, fTK = face(H), face(C), face(TH), face(TK)

# sample copy (generic — shows the style, not a real reel)
hook   = [caseit(w, H, first=i == 0) for i, w in enumerate(["your hook", "lands", "right here"])]
capw   = [caseit(w, C) for w in ["read", "along", "one", "word", "at", "a", "time"]]
cap_kw = {caseit("word", C)}
thought= caseit("(a little aside)", TH)
takew  = [caseit(w, TK) for w in ["this", "is", "the", "takeover"]]
tk_kw  = caseit("takeover", TK)

DUR = 12.0
STEP = TK.get("step", 0.16)   # takeover line spacing (pack-specific)
# Mirror the real builder: a stacked word block needs a line-height at least as tall as the FACE's own box
# or adjacent word boxes overlap. Launch packs keep their hand-tuned spacing untouched; a custom pack, whose
# numbers were cloned onto a face they were never tuned for, gets the measured floor.
_TUNED = bool(pack.get("in_launch_kit"))
TK_LH = round(1.0 + TK.get("line_height", 0.02) + STEP, 3)
if not _TUNED:
    TK_LH = max(TK_LH, round(stylepack.font_box_ratio(TK["file"]), 3))
# The takeover fits the safe width the way the builder fits it: its longest word MEASURED in the real face at the
# pack size; wider than the box, the stack steps down until it fits (the preview used to let it run off the frame).
TK_PX = px(TK)
try:
    import hooksplit as _HS
    _tk_box = 1080 - 2 * 130
    while TK_PX > 24 and max(_HS._measure(w, TK["file"], TK_PX) for w in takew) > _tk_box:
        TK_PX -= 2
except Exception:   # nothing to measure with (no Pillow / no face file): the pack size, as before
    pass

def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ---- HOOK (headline): staggered fragment build, accent on the last fragment ----
# The accent style is built OUTSIDE the f-string: an expression part may not contain a backslash
# before Python 3.12, and this file has to parse on whatever python3 a buyer happens to have.
_accent_attr = ' style="color:%s"' % ACCENT
hook_spans = "".join(f'<span class="line" id="hk{i}" data-layout-allow-overlap{_accent_attr if i==len(hook)-1 else ""}>{esc(t)}</span>' for i,t in enumerate(hook))
hook_js = "".join(
    f'tl.set("#hk{i}",{{autoAlpha:0,y:34}},0);tl.to("#hk{i}",{{autoAlpha:1,y:0,duration:0.45,ease:"power3.out"}},{0.2+i*0.45:.2f});'
    for i in range(len(hook))
) + f'tl.to("#hookwrap",{{autoAlpha:0,duration:0.3}},2.9);'

# ---- CAPTION (snap): one word at a time, low, accent keyword ----
cap_html = "".join(f'<div class="capword{" kw" if w in cap_kw else ""}" id="cw{i}">{esc(w)}</div>' for i,w in enumerate(capw))
t0 = 3.2; cap_js = ""
for i,w in enumerate(capw):
    st = t0 + i*0.28
    cap_js += f'tl.set("#cw{i}",{{autoAlpha:0,y:20}},0);tl.to("#cw{i}",{{autoAlpha:1,y:0,duration:0.16}},{st:.2f});tl.to("#cw{i}",{{autoAlpha:0,duration:0.12}},{st+0.26:.2f});'

# ---- THOUGHT bubble: pop in above the head, silent, fade out ----
th_js = (f'tl.set("#thought",{{autoAlpha:0,scale:0.8,y:16}},0);'
         f'tl.to("#thought",{{autoAlpha:1,scale:1,y:0,duration:0.4,ease:"back.out(2)"}},6.1);'
         f'tl.to("#thought",{{autoAlpha:0,duration:0.35}},8.3);')

# ---- TAKEOVER: every word its own line, lift in, held, accent key word ----
tk_html = "".join(f'<span class="tkline{" kw" if w==tk_kw else ""}" id="tk{i}">{esc(w)}</span>' for i,w in enumerate(takew))
tk_js = ""
for i in range(len(takew)):
    tk_js += f'tl.set("#tk{i}",{{autoAlpha:0,y:26}},0);tl.to("#tk{i}",{{autoAlpha:1,y:0,duration:0.3,ease:"power2.out"}},{8.9+i*0.18:.2f});'

HTML = f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
{os.linesep.join(_css)}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#141414;}}
#root{{position:absolute;inset:0;}}
#bg{{position:absolute;inset:0;background:radial-gradient(120% 80% at 50% 30%, #2a2a30 0%, #141414 70%);}}
#tag{{position:absolute;top:90px;left:0;right:0;text-align:center;font-family:{fC};font-size:34px;color:rgba(255,255,255,.5);letter-spacing:2px;}}
/* HOOK (headline) — top, fragment stack */
#hookwrap{{position:absolute;left:150px;right:150px;top:22%;text-align:center;font-family:{fH};color:{HOOK_COLOR};text-shadow:0 5px 18px rgba(0,0,0,.6);}}
#hookwrap .line{{display:block;font-size:{px(H)}px;line-height:1.04;}}
/* CAPTION (snap) — low ~70% */
.capword{{position:absolute;left:0;right:0;top:70%;text-align:center;font-family:{fC};font-weight:600;font-size:{px(C,"caption")}px;color:{TEXT_COL};text-shadow:0 3px 10px rgba(0,0,0,.55);}}
.capword.kw{{color:{ACCENT};}}
/* THOUGHT bubble — above head */
#thought{{position:absolute;left:150px;right:150px;top:60%;text-align:center;font-family:{fTH};font-size:{px(TH)}px;color:{TEXT_COL};text-shadow:0 3px 10px rgba(0,0,0,.55);}}
/* TAKEOVER — vertical word stack, centered */
#tkwrap{{position:absolute;left:130px;right:130px;top:50%;transform:translateY(-50%);text-align:center;font-family:{fTK};color:{TEXT_COL};text-shadow:0 4px 14px rgba(0,0,0,.6);}}
#tkwrap .tkline{{display:block;font-size:{TK_PX}px;line-height:{TK_LH};}}
#tkwrap .tkline.kw{{color:{TEXT_COL if TK_WHITE else ACCENT};}}
</style></head>
<body>
<div id="root" data-composition-id="packpreview" data-start="0" data-duration="{DUR}" data-width="1080" data-height="1920">
  <div class="clip" data-start="0" data-duration="{DUR}" data-track-index="0"><div id="bg"></div><div id="tag">{esc(PACK.upper())} STYLE</div></div>
  <div class="clip" data-start="0" data-duration="3.2" data-track-index="1"><div id="hookwrap">{hook_spans}</div></div>
  <div class="clip" data-start="3.0" data-duration="3.1" data-track-index="1">{cap_html}</div>
  <div class="clip" data-start="6.0" data-duration="2.6" data-track-index="1"><div id="thought">{esc(thought)}</div></div>
  <div class="clip" data-start="8.7" data-duration="3.3" data-track-index="1"><div id="tkwrap">{tk_html}</div></div>
</div>
<script>
window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});
{hook_js}
{cap_js}
{th_js}
{tk_js}
window.__timelines["packpreview"]=tl;
</script>
</body></html>'''

# scaffold config from the generic template so this is portable (no personal reel)
_tpl = f"{ROOT}/product/templates/hf-reel"
for _f in ("hyperframes.json", "package.json"):
    if os.path.exists(f"{_tpl}/{_f}") and not os.path.exists(f"{OUT}/{_f}"):
        shutil.copy(f"{_tpl}/{_f}", f"{OUT}/{_f}")
open(f"{OUT}/meta.json", "w", encoding="utf-8").write('{"id":"packpreview","name":"pack-preview"}')
open(f"{OUT}/index.html", "w", encoding="utf-8").write(HTML)
print(f"wrote {OUT}/index.html  (pack={PACK}, accent={ACCENT}, sizes: hook {px(H)} cap {px(C,'caption')} thought {px(TH)} takeover {TK_PX})")
