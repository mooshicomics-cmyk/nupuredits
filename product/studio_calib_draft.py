#!/usr/bin/env python3
"""studio_calib_draft.py [PACK] [CLIP] — a REAL CapCut calibration draft.

A realistic long hook + caption + takeover over a clip, built through the TRUE production path
(packbuild.wrap_for_canvas + pack line_spacing), so we can open CapCut and lock the wrap budget + leading
against what CapCut actually renders (no proxy). Mirrors build-pack-demo.py. CapCut MUST be quit.
Run with the VectCut venv:  product/engine/VectCutAPI/venv-capcut/bin/python3 product/studio_calib_draft.py Editorial "<clip>"
"""
import os, sys, json
import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import superyap as S
import packbuild as P

PACK = sys.argv[1] if len(sys.argv) > 1 else "Editorial"
RAW = sys.argv[2] if len(sys.argv) > 2 else None
CMD = sys.argv[3] if len(sys.argv) > 3 else "base"       # base | hush | punch | split | splitfirst
HOOK_MULT = {"base": 1.0, "hush": 0.72, "punch": 1.28}.get(CMD, 1.0)
SPLIT = CMD in ("split", "splitfirst")                   # long-hook -> two halves (split=2nd-half emphasis=eyebrow top)
NAME = (f"StudioCalib-{PACK}" if CMD == "base" else f"StudioCalib-{PACK}-{CMD}") + os.environ.get("MX_SUFFIX","")
W, H = 1080, 1920
import stylepack as _SPk
_hc = _SPk.load(PACK).get("capcut", {}).get("hook_color")   # per-pack CapCut hook color; "white" default is easier over footage, buyer restyles freely
_HOOKCOL = (S.WHITE if str(_hc).lower() == "white" else _hc) if _hc else P.accent_color(PACK)

did = S.call("create_draft", width=W, height=H)["output"]["draft_id"]
if RAW:
    S.call("add_video", draft_id=did, video_url=RAW, start=0, end=9, target_start=0)

font_map = {}
patch = {}
box_texts = set()               # hook lines (single or split halves) that get a real box, not a hard-wrap
def T(text, r, start, end, color=None, y=None, size_mult=1.0):
    sp = P.role(PACK, r)
    trk = sp.get("tracking", 0.0); lh = sp["line_height"]
    if r == "headline":
        # single headline pulls the SAME capcut tuning as the split, so the two paths can't drift
        import stylepack as _SPt
        _cc = _SPt.load(PACK).get("capcut", {})
        trk = _cc.get("headline_tracking", trk)
        lh = _cc.get("headline_line_spacing", lh)
    disp = P.caseit(text, sp["case"])
    sz = max(6, int(round(sp["size"] * size_mult)))
    disp = P.wrap_for_canvas(disp, sp["font_path"], sz, tracking=trk)   # tracking-aware wrap
    yy = sp["y"] if y is None else y
    S.add_text(did, disp, start, end, sp["font_path"], sz, 0.0, yy, r, color=color or S.WHITE)
    font_map[disp] = sp["font_path"]
    patch[disp] = {"lh": lh, "trk": trk, "bold": sp["bold"], "role": r}
    if r == "headline":
        box_texts.add(disp)
    return disp.count("\n") + 1

HOOK_LONG = os.environ.get("MX_LONG", "you can love being home and still miss who you used to be")   # long -> needs the split
HOOK_SINGLE = os.environ.get("MX_SINGLE", "here's what nobody tells you")   # short -> showcases the single headline
HOOK = HOOK_LONG if SPLIT else HOOK_SINGLE
if SPLIT:
    import hooksplit as HS
    a, b = HS.split_hook(HOOK)                            # a=first half, b=second half (reading order)
    emphasis = "first" if CMD == "splitfirst" else "second"   # default: 2nd half carries the payoff -> eyebrow on top
    layers = HS.hook_spec(a, b, PACK, emphasis=emphasis)
    for L in layers:
        disp = P.caseit(L["text"], L["case"])
        col = _HOOKCOL if L["role"] == "headline" else S.WHITE
        S.add_text(did, disp, 0.30, 4.00, L["font_path"], L["size"], 0.0, L["y"], L["role"], color=col)
        font_map[disp] = L["font_path"]
        patch[disp] = {"lh": L["line_height"], "trk": L["tracking"], "bold": L["bold"], "role": L["role"]}
        box_texts.add(disp)                              # both halves ride in a box; CapCut wraps inside it
    nh = len(layers)
else:
    # Single (headline-only) hook: the CapCut size comes from capcut.single_headline_size if the pack dials one
    # (kept SEPARATE from the shared native size, which well-done reads for the eyebrow ratio), else native.
    import stylepack as _SPh
    _sing = _SPh.load(PACK).get("capcut", {}).get("single_headline_size")
    _hmult = (_sing / P.role(PACK, "headline")["size"]) if _sing else 1.0
    nh = T(HOOK, "headline", 0.30, 4.00, color=_HOOKCOL, size_mult=HOOK_MULT * _hmult)
import stylepack as _SPc
_ccap = _SPc.load(PACK).get("capcut", {}).get("caption_size")            # per-pack CapCut caption size override
_capmult = (_ccap / P.role(PACK, "caption")["size"]) if _ccap else 1.0
nc = T("and holding both is the hardest part", "caption", 0.50, 4.00, y=-0.33, size_mult=_capmult)  # dropped below the chin

tk = P.role(PACK, "takeover")
tk_words = [("career", 7.0), ("crash", 7.3), ("out", 7.6)]
step = tk.get("step") or 0.12
top = (len(tk_words) - 1) / 2 * step
for k, (wd, st) in enumerate(tk_words):
    disp = P.caseit(wd, tk["case"])
    S.add_text(did, disp, st, 8.6, tk["font_path"], tk["size"], 0.0, top - k * step, f"tk{k}", color=S.WHITE)
    font_map[disp] = tk["font_path"]
    patch[disp] = {"lh": tk["line_height"], "trk": tk["tracking"], "bold": tk["bold"]}

S.call("save_draft", draft_id=did, draft_folder=S.CAP)

# Give every hook line a real box BEFORE finalize, so sanitize leaves it one line and CapCut wraps it inside
# the box (a -1/no-box hook runs off frame; a hard-wrapped one shatters a one-line emphasis into fragments).
if box_texts:
    bp = _ds.draft_json(f"{S.CAP}/{did}"); bd = json.load(open(bp, encoding="utf-8"))
    from capcut_text import HOOK_BOX_W
    for m in bd["materials"]["texts"]:
        if json.loads(m["content"]).get("text", "") in box_texts:
            m["fixed_width"] = HOOK_BOX_W
    json.dump(bd, open(bp, "w", encoding="utf-8"), ensure_ascii=False)

S.finalize(did, NAME, font_map)

# per-element line_spacing + letter_spacing + bold (finalize/add_text don't set these)
p = _ds.draft_json(f"{S.CAP}/{NAME}")
d = json.load(open(p, encoding="utf-8"))
for m in d["materials"]["texts"]:
    c = json.loads(m["content"]); txt = c.get("text", "")
    if txt in patch:
        pc = patch[txt]
        m["line_spacing"] = pc["lh"]
        m["letter_spacing"] = pc["trk"]
        if pc["bold"]:
            for stx in c.get("styles", []):
                stx["bold"] = True
            m["content"] = json.dumps(c, ensure_ascii=False); m["bold_width"] = 0.008
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
print(f"hook={nh} lines  caption={nc} lines")
print(f"DONE -> open CapCut draft: {NAME}")
