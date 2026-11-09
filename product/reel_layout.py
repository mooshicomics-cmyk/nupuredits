#!/usr/bin/env python3
"""reel_layout.py — THE Layer-1 layout brain. Resolve the invariant rules (scale, size, placement, fill,
centering) for the ACTUAL draft canvas, from the single sources of truth, so no agent ever re-derives a
type scale or a safe box by eye again.

WHY THIS EXISTS (the repair, 2026-09-09)
----------------------------------------
Defects in live testing all reduced to one thing: numbers were guessed by eye against an anchor that was
itself wrong, and re-guessed every build. At thousands of buyers x every format x every pack, that guessing
drifts into thousands of *differently* wrong reels. The fix is to READ the rules from a fixed source every
build and resolve them for this exact canvas — never reconstruct them from memory.

THE ARCHITECTURE (creator's directive — governs the product)
------------------------------------------------------------
  Layer 1  THE RULES     scale / size / placement / layout / flow / hierarchy / motion.
                         Source of truth = HyperFrames docs (typography.md, frame-worker-core.md).
                         Invariant across every format, register, pack, buyer. This module resolves them.
  Layer 2  PLATFORM      Instagram Reels UI safe zones (safe_zones.py). The ONE thing allowed to clip L1.
  Layer 3  DRESSING      fonts / colors / radius / shadow (per pack: pack_palettes.py, style-packs.json).
                         Changes how it LOOKS, never WHERE or HOW BIG.

Everything below is a FUNCTION of (canvas, pack, format, register) — nothing absolute. A build at 1080 and
a build at 1440, in a different pack, with different copy, must come out visually EQUIVALENT. That is the
test of whether this was done right.

SCOPE (honest boundary)
-----------------------
This governs the routes the engine actually RENDERS (medium / well-done / Animation / any baked .mov
overlay). On the RAW route the engine hands editable native text to CapCut and the creator sizes/places it
herself — there is no engine-drawn DOM to resolve or gate. `governs_geometry(route)` says so explicitly.

Consumed by: the `reel-layout-rules` skill (prints `describe()` for the active build) and the pre-render
geometry gate (asserts the composition against `LayoutContext`). Pure Python, no browser, unit-testable.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_zones          # Layer 2 + engine legibility floors (single source)
try:
    import pack_palettes   # Layer 3 palettes (single source)
except Exception:          # pack_palettes pulls no heavy deps, but stay resilient in odd shells
    pack_palettes = None

# The base the shared sources are expressed in. Everything scales as a fraction of this.
BASE_W, BASE_H = safe_zones.W, safe_zones.H     # 1080 x 1920

# ── Layer 1: HyperFrames IN-FEED type floors (typography.md:63) ────────────────────────────────────
# This engine ships to Instagram Reels = IN-FEED viewing (the video plays small in a scrolling feed), so
# the in-feed numbers are the operative ones, ALWAYS. These are FLOORS to clear, never targets to hit
# (typography.md: "first-pass values; calibrate against real renders"). Given in px at the 1080 base;
# stored as width-fractions so they scale to any canvas.
HF_INFEED_FLOOR_PX = {"headline": 90, "body": 32, "data_label": 24}   # typography.md:63 (in-feed column)

# Engine role -> HyperFrames category. A role's floor is the STRICTER of the HF in-feed floor and the
# engine's own legibility floor (safe_zones.MIN_PX), so neither is ever violated.
ROLE_TO_HF = {
    "headline": "headline", "hook": "headline", "takeover": "headline",
    "subhead": "body", "caption": "body", "karaoke": "body", "body": "body", "checklist": "body",
    "label": "data_label", "chip": "data_label", "stat_unit": "data_label", "eyebrow": "data_label",
}

# ── Layer 1: FILL targets (frame-worker-core.md:50 "fill the content area; don't float one small cluster")
# Confirmed with the creator 2026-09-09 as starting values; calibrate against real renders. A text card
# materially below its target is a DEFECT, not a style choice — but compact badges opt out explicitly.
FILL_TARGET = {"hook": 0.95, "hero": 0.95, "card": 0.70, "badge": 0.0}   # fraction of SAFE width

# Absolute legibility floor as a fraction of canvas width (nothing below ~26px at 1080 ≈ 0.024w). Catches a
# collapsed computed size that still clears a role floor.
MIN_LEGIBLE_FRAC = 26.0 / BASE_W

# ── Layer 1: the ONE centering primitive + the content-sized card primitive ────────────────────────
# NEVER center with `transform: translateX(-50%)` — GSAP overwrites the whole transform and discards it
# (frame-worker-core.md:74 gsap_css_transform_conflict). Center with inset+margin instead; it survives any
# GSAP transform tween. Text cards are CONTENT-sized (fit-content), never author-sized, and stack their
# children explicitly so a fit-content box never sizes two inline siblings side-by-side.
CENTER_PRIMITIVE_CSS = (
    ".rl-center{position:absolute;left:0;right:0;margin-inline:auto;width:fit-content;}"
)
CARD_PRIMITIVE_CSS = (
    ".rl-card{width:fit-content;max-width:var(--rl-safe-w);"
    "display:flex;flex-direction:column;align-items:center;text-align:center;box-sizing:border-box;}"
)


def _read_canvas(draft_info_path):
    """Return (w, h, source) from a CapCut draft's canvas_config. NEVER assume 1080x1920 — read it."""
    try:
        d = json.load(open(draft_info_path, encoding="utf-8"))
        cc = d.get("canvas_config") or {}
        w, h = int(cc.get("width") or 0), int(cc.get("height") or 0)
        if w > 0 and h > 0:
            return w, h, os.path.basename(draft_info_path)
    except Exception as e:
        return BASE_W, BASE_H, f"FALLBACK 1080x1920 (could not read canvas: {e})"
    return BASE_W, BASE_H, "FALLBACK 1080x1920 (canvas_config missing width/height)"


# Which routes the engine RENDERS (and therefore governs geometry for). Raw = native CapCut text = hers.
_RENDERED_ROUTES = {"medium", "well-done", "welldone", "animation", "hands-off", "handsoff", "baked"}
def governs_geometry(route):
    return str(route or "").strip().lower() in _RENDERED_ROUTES


class LayoutContext:
    """The resolved Layer-1 numbers for ONE build. Everything here is derived, per canvas/pack/format —
    nothing is a hardcoded pixel constant an agent typed."""

    def __init__(self, canvas_w, canvas_h, pack=None, fmt="yap", register="teaching",
                 route="well-done", canvas_source="explicit"):
        self.w, self.h = int(canvas_w), int(canvas_h)
        self.pack, self.format, self.register, self.route = pack, fmt, register, route
        self.canvas_source = canvas_source
        self.sx, self.sy = self.w / BASE_W, self.h / BASE_H          # scale from the 1080x1920 base
        self.governs = governs_geometry(route)

        # Layer 2 safe box, scaled from the shared fractions to THIS canvas.
        self.safe_left   = safe_zones.LEFT  / BASE_W * self.w
        self.safe_right  = safe_zones.RIGHT / BASE_W * self.w
        self.safe_top    = safe_zones.TOP   / BASE_H * self.h
        self.safe_bottom = safe_zones.BOTTOM/ BASE_H * self.h
        self.safe_w = self.safe_right - self.safe_left
        self.safe_h = self.safe_bottom - self.safe_top
        self.cx, self.cy = self.w / 2.0, self.h / 2.0                # canvas center

    # ---- type floors -------------------------------------------------------------------------------
    def floor_px(self, role):
        """The minimum legible px for a role (or an HF category) on THIS canvas: the stricter of the
        HyperFrames in-feed floor and the engine's own legibility floor, scaled by canvas width, and never
        below MIN_LEGIBLE. Accepts a role ('hook','caption','label'...) or a category ('headline','body',
        'data_label') directly."""
        cat = role if role in HF_INFEED_FLOOR_PX else ROLE_TO_HF.get(role, "body")
        hf = HF_INFEED_FLOOR_PX[cat]
        eng = safe_zones.MIN_PX.get(role, 0)          # engine floor only applies to a named role
        base = max(hf, eng)
        return max(base * self.sx, MIN_LEGIBLE_FRAC * self.w)

    # ---- fill target -------------------------------------------------------------------------------
    def fill_target_px(self, kind="card"):
        """Minimum width a filled element should reach = target fraction x SAFE width. 'badge' => 0 (opt out)."""
        return FILL_TARGET.get(kind, FILL_TARGET["card"]) * self.safe_w

    # ---- palette (Layer 3, for the color-trace check) ---------------------------------------------
    def palette(self):
        """The active pack's declared palette (light/dark/muted/accent/pop2) — the ONLY colors a build may
        use. Empty dict if the pack is unknown; the gate then warns rather than blocks."""
        if pack_palettes and self.pack in getattr(pack_palettes, "PALETTE", {}):
            return dict(pack_palettes.PALETTE[self.pack])
        return {}

    def allowed_hexes(self):
        """Lowercased set of every hex the active pack sanctions (+ black/white, always legal for text)."""
        s = {v.lower() for v in self.palette().values()}
        s |= {"#000000", "#000", "#ffffff", "#fff"}
        return s

    # ---- the human-readable resolution the skill prints -------------------------------------------
    def describe(self):
        L = []
        L.append(f"REEL LAYOUT — resolved for this build")
        L.append(f"  canvas        {self.w} x {self.h}   (source: {self.canvas_source})")
        L.append(f"  format/route  {self.format} / {self.route}   register: {self.register}   pack: {self.pack}")
        if not self.governs:
            L.append(f"  · RAW route: you set size and placement yourself in CapCut, so the engine does not draw or check it here.")
            return "\n".join(L)
        L.append(f"  safe box      x {self.safe_left:.0f} -> {self.safe_right:.0f}  ·  "
                 f"y {self.safe_top:.0f} -> {self.safe_bottom:.0f}   (safe {self.safe_w:.0f} x {self.safe_h:.0f})")
        L.append(f"  canvas center x {self.cx:.0f}  y {self.cy:.0f}   (centered => within 1px)")
        L.append(f"  type FLOORS   " + " · ".join(
            f"{r} ≥ {self.floor_px(r):.0f}px" for r in ("headline", "body", "data_label")))
        L.append(f"  fill TARGETS  hook ≥ {self.fill_target_px('hook'):.0f}px ({FILL_TARGET['hook']:.0%} safe) · "
                 f"card ≥ {self.fill_target_px('card'):.0f}px ({FILL_TARGET['card']:.0%} safe) · badge opt-out")
        pal = self.palette()
        L.append(f"  pack palette  " + (", ".join(f"{k} {v}" for k, v in pal.items()) if pal
                                        else "UNKNOWN pack — color-trace check will WARN, not block"))
        L.append(f"  centering     use .rl-center (inset+margin) — NEVER transform:translateX(-50%)")
        return "\n".join(L)


def resolve(draft_info_path=None, canvas=None, pack=None, fmt="yap",
            register="teaching", route="well-done"):
    """Build a LayoutContext. Prefer a real draft (reads canvas_config); else an explicit (w,h) tuple;
    else the 1080x1920 base with a loud note. NEVER silently assume the canvas."""
    if draft_info_path:
        w, h, src = _read_canvas(draft_info_path)
    elif canvas:
        w, h, src = int(canvas[0]), int(canvas[1]), "explicit (w,h)"
    else:
        w, h, src = BASE_W, BASE_H, "DEFAULT 1080x1920 (no draft or canvas given — state this in the build log)"
    return LayoutContext(w, h, pack=pack, fmt=fmt, register=register, route=route, canvas_source=src)


if __name__ == "__main__":
    # quick manual check: resolve at the base and at a larger canvas, confirm everything scales.
    for cv in ((1080, 1920), (1440, 2560)):
        print(resolve(canvas=cv, pack="Butter", fmt="yap", register="teaching", route="well-done").describe())
        print()
    print(resolve(canvas=(1080, 1920), pack="Butter", route="raw").describe())
