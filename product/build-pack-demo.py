#!/usr/bin/env python3
"""build-pack-demo.py PACK — minimal CapCut draft showcasing a style pack's 5 text roles over a clip.

Proves the CapCut lane renders in ANY pack: native, fully editable text with the pack's fonts / sizes /
case / positions. Run with the VectCut venv python; CapCut MUST be quit. Opens as draft "PackDemo-<Pack>".
"""
import os, sys, json
import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import superyap as S
import packbuild as P

PACK = sys.argv[1] if len(sys.argv) > 1 else "Editorial"
RAW = sys.argv[2] if len(sys.argv) > 2 else None   # optional bg clip; omit for a plain background
W, H = 1080, 1920

did = S.call("create_draft", width=W, height=H)["output"]["draft_id"]
if RAW:
    S.call("add_video", draft_id=did, video_url=RAW, start=0, end=9, target_start=0)   # bg clip 0-9s

font_map = {}; patch = {}
def T(text, r, start, end, color=None):
    sp = P.role(PACK, r)
    disp = P.caseit(text, sp["case"])
    disp = P.wrap_for_canvas(disp, sp["font_path"], sp["size"])   # fit the canvas width
    S.add_text(did, disp, start, end, sp["font_path"], sp["size"], 0.0, sp["y"], r, color=color or S.WHITE)
    font_map[disp] = sp["font_path"]
    patch[disp] = {"lh": sp["line_height"], "trk": sp["tracking"], "bold": sp["bold"]}

# sequenced like the motion preview
T("here's the truth",           "headline", 0.30, 2.00, color=P.accent_color(PACK))   # headline in pack accent color
T("no one says this",           "thought",  2.20, 5.00)
T("start with one thing",       "caption",  2.50, 5.00)
T("and that changes everything","accent",   5.20, 6.80)

# takeover: word stack in the pack takeover font, fixed stacked positions
tk = P.role(PACK, "takeover")
tk_words = [("you're", 7.00), ("not", 7.30), ("behind", 7.60)]
step = tk.get("step") or 0.12; top = (len(tk_words) - 1) / 2 * step   # the creator's cloned word-spacing
for k, (wd, st) in enumerate(tk_words):
    disp = P.caseit(wd, tk["case"])
    S.add_text(did, disp, st, 8.60, tk["font_path"], tk["size"], 0.0, top - k * step, f"tk{k}", color=S.WHITE)
    font_map[disp] = tk["font_path"]
    patch[disp] = {"lh": tk["line_height"], "trk": tk["tracking"], "bold": tk["bold"]}

S.call("save_draft", draft_id=did, draft_folder=S.CAP)
S.finalize(did, f"PackDemo-{PACK}", font_map)

# patch per-element line_spacing + letter_spacing + bold — finalize/add_text don't set these
p = _ds.draft_json(f"{S.CAP}/PackDemo-{PACK}")
d = json.load(open(p, encoding="utf-8")); patched = 0
for m in d["materials"]["texts"]:
    c = json.loads(m["content"]); txt = c.get("text", "")
    if txt in patch:
        pc = patch[txt]
        m["line_spacing"] = pc["lh"]
        m["letter_spacing"] = pc["trk"]
        if pc["bold"]:
            for stx in c.get("styles", []): stx["bold"] = True
            m["content"] = json.dumps(c, ensure_ascii=False); m["bold_width"] = 0.008
        patched += 1
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
print(f"DONE -> open CapCut draft: PackDemo-{PACK}  (patched {patched} texts: line+letter+bold)")
