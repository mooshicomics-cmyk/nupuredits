#!/usr/bin/env python3
"""capcut_ripple.py — the ONE magnet/ripple enforcement, shared by every CapCut build.

the creator's hard rule (2026-08-02): "magnet ALL tracks AND audio to the main track. write that into
every capcut build here and on the shippable version." Overlays (img_/text), b-roll, AND audio must
all follow the main track's ripple trims — not just audio.

Single source of truth so it can never drift or be forgotten. Imported by cleanyap.py (Clean Yap +
the shipped kit), superyap.py (Super Yap), and patch-ripple-snap.py (surgical patch onto a live draft).
Kept in a neutral util module — neither the Clean Yap nor Super Yap lane depends on the other
. Call this LAST in finalize, AFTER per-track render_index is set
(z-order lives on each segment's render_index, so blanking track names never disturbs layering).

⚠️ THE ANCHOR RULE (root-caused 2026-08-12, magnet silently dead on a multi-segment cut):
The magnet needs an ANCHOR. In a native CapCut footage cut where the magnet works (verified against
real multi-segment cuts, 45+ segments), the MAIN footage track is `is_default_name=False` while every
OVERLAY track is `is_default_name=True`. `is_default_name=True` = an auto-named, identity-less "floating"
track. If the MAIN track is also `is_default_name=True`, CapCut has no anchor to adsorb to and NOTHING
ripples — even with `maintrack_adsorb=True` set. The old code set the main track to True, which silently
killed the magnet on every multi-segment cut. Main = False, overlays = True. Do not "simplify" this back.
`verify_maintrack_anchor()` below is the fail-safe that hard-stops a build if this regresses.

⚠️ THE TIMELINES RESET (root-caused 2026-08-17, "magnet not working" recurring every reel):
CapCut, on a draft's FIRST import, builds a native `Timelines/<id>/<draft json>` cache and RESETS the
main track's anchor to `is_default_name=True` there — killing the magnet — even though the top-level
the top-level draft JSON was written correctly. From then on CapCut runs off the Timelines copy, so the build-time
anchor is ignored. The fix cannot happen at build time (Timelines does not exist yet); it must be applied
AFTER the first open. `snap_draft_dir()` re-enforces the anchor into the top-level file AND every Timelines
copy; `verify_draft_dir()` is the fail-safe that checks EVERY copy (a broken Timelines copy is invisible in
the top-level file). Standard handoff: build -> open in CapCut -> quit -> snap_draft_dir -> reopen.
"""
import json, os, glob, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draft_safety  # owns WHICH filename this CapCut uses for a draft's timeline JSON
try:
    import capcut_color  # every video segment SDR (see capcut_color.py); swept here so every draft writer gets it
except ImportError:      # a partial copy of the engine still writes a draft; the builders' own sweep stays
    capcut_color = None


def enforce_maintrack_ripple(d, main=None):
    """Magnet EVERY non-main track (video overlays, text, b-roll, audio) to the main footage track so
    they all follow main-track ripple edits. Sets the global linked-render + magnet flags, then anchors
    the main track (is_default_name=False, keeps its identity) and default-names every OTHER track
    (is_default_name=True → native floating tracks that adsorb to the anchor). See capcut maintrack ripple
    and the ANCHOR RULE above. Also forces every video segment to SDR (capcut_color.enforce_sdr), so no
    draft writer can hand CapCut a clip tagged HDR. Verify live before claiming fixed.

    `main`: the footage track, when the caller knows it. Default: the video track with the most segments,
    which is right for an engine build (one segment per kept line) but not for a draft whose footage is one
    compound clip under a many-segment overlay track (capcut_recut.py passes its own main_track)."""
    if capcut_color is not None:
        # SDR sweep (ISS-13): a segment copied from the footage clip or a template can carry HDR mode 1/4, and
        # CapCut then shows bt709 footage washed out. Every draft writer calls this function, so the sweep
        # lives here instead of in each writer.
        capcut_color.enforce_sdr(d)
    d["free_render_index_mode_on"] = False              # linked render mode (tracks not free-floating)
    cfg = d.setdefault("config", {})
    cfg["maintrack_adsorb"] = True                       # the magnet
    cfg["use_float_render"] = False                      # never free-float render (match native)
    vids = [t for t in d.get("tracks", []) if t["type"] == "video"]
    if main is None:
        main = max(vids, key=lambda t: len(t.get("segments", [])), default=None)
    if main is not None:
        # ANCHOR: main track keeps a fixed identity so overlays have something to adsorb TO.
        main["flag"] = 0; main["name"] = ""; main["is_default_name"] = False
    for t in d.get("tracks", []):                        # ALL other tracks (video overlays, text, audio) adsorb too
        if t is main:
            continue
        t["name"] = ""; t["is_default_name"] = True      # native default-named floating track → adsorbs to anchor
    # SELF-VERIFY: never hand back a draft with a dead magnet. This guards EVERY caller (both engines +
    # every build-*/patch-* path) and any future edit to this function, in one place. Only checked when
    # there is a main video track to anchor (audio-only drafts have nothing to magnet).
    if main is not None:
        problems = verify_maintrack_anchor(d, main=main)
        if problems:
            raise RuntimeError("magnet enforcement produced a broken anchor: " + "; ".join(problems))
    return d


def verify_maintrack_anchor(d, main=None):
    """Fail-safe. Returns a list of human-readable problems that would leave the magnet dead; empty list
    = the ripple graph is correctly anchored. Call at the END of finalize and raise if it is non-empty,
    so a broken magnet can NEVER ship silently again (the 2026-08-12 regression shipped clean-looking:
    every flag was set, only the anchor boolean was wrong)."""
    problems = []
    if d.get("free_render_index_mode_on") is not False:
        problems.append("free_render_index_mode_on must be False (linked render)")
    cfg = d.get("config", {})
    if cfg.get("maintrack_adsorb") is not True:
        problems.append("config.maintrack_adsorb must be True (the magnet)")
    if cfg.get("use_float_render") is not False:
        problems.append("config.use_float_render must be False")
    vids = [t for t in d.get("tracks", []) if t.get("type") == "video"]
    if not vids:
        problems.append("no video track to anchor to")
        return problems
    if main is None:
        main = max(vids, key=lambda t: len(t.get("segments", [])))
    if main.get("is_default_name") is not False:
        problems.append("MAIN track is_default_name must be False (anchor identity) — this is the magnet-killer")
    if main.get("flag") not in (0, None):
        problems.append(f"MAIN track flag should be 0, got {main.get('flag')!r}")
    for t in d.get("tracks", []):
        if t is main:
            continue
        if t.get("is_default_name") is not True:
            problems.append(f"overlay/{t.get('type')} track is_default_name must be True (floats + adsorbs), got {t.get('is_default_name')!r}")
    return problems


def _draft_info_copies(draft_dir, require=True):
    """Every timeline JSON CapCut reads for one draft: the top-level file + each native Timelines copy.

    Delegates the FILENAME to draft_safety, because CapCut names this file per platform (draft_info.json
    on macOS, draft_content.json on Windows). This used to hardcode the macOS name, so on Windows it
    matched nothing and returned [] — which made verify_draft_dir() below hand back an EMPTY problems
    dict, i.e. a confident 'every copy is correctly anchored' while it had in fact checked zero files.
    A fail-safe that passes by finding nothing is worse than no fail-safe, so finding none now RAISES."""
    return draft_safety.draft_json_copies(draft_dir, require=require)


def snap_draft_dir(draft_dir):
    """Re-enforce the magnet into EVERY timeline-JSON copy (top-level + Timelines cache). Run AFTER
    CapCut has imported the draft once and been quit — this is the fix for the Timelines reset described in
    the header. Returns (patched_count, {file: [problems]}). CapCut MUST be quit (it rewrites on save)."""
    patched, problems = 0, {}
    for f in _draft_info_copies(draft_dir):
        d = json.load(open(f, encoding="utf-8"))
        if not [t for t in d.get("tracks", []) if t.get("type") == "video"]:
            continue                                          # audio-only copy: nothing to anchor
        enforce_maintrack_ripple(d)
        json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False)
        p = verify_maintrack_anchor(d)
        if p:
            problems[f] = p
        patched += 1
    return patched, problems


def verify_draft_dir(draft_dir):
    """FAIL-SAFE: check EVERY timeline-JSON copy's magnet anchor, not just the top-level file (a reset
    Timelines copy is invisible there and is exactly what kills the magnet). Returns {file: [problems]};
    empty dict = every copy is correctly anchored. Gate a CapCut handoff on this being empty."""
    out = {}
    for f in _draft_info_copies(draft_dir):
        d = json.load(open(f, encoding="utf-8"))
        if not [t for t in d.get("tracks", []) if t.get("type") == "video"]:
            continue
        p = verify_maintrack_anchor(d)
        if p:
            out[f] = p
    return out
