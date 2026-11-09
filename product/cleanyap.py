#!/usr/bin/env python3
"""cleanyap.py — the canonical CLEAN YAP build ENGINE for Naptime Creator Studio.

The TRIMMED-BACK lane, separate from the Super Yap engine on purpose.
A Clean Yap is: the locked rough cut, full-screen, + ONE hook (the pack's hook font) + thought bubbles
(the pack's thought font) + matched/trimmed SFX. Everything stays individually editable in CapCut. NOTHING loaded.

Deliberately does NOT expose the Super Yap machinery (full-screen pack-takeover-font takeover, doodle-sticker
layers, b-roll cutaways/bursts, stat cards, punch-in zooms). If a reel needs those, it's a Super Yap →
use superyap.py. Keeping the lanes separate in CODE is the point (the creator's rule #6, fix the system).

DONENESS != FORMAT (locked). "Clean vs Super" is the LOADED-NESS axis. "raw / medium /
well-done" is a SEPARATE doneness axis that applies to Clean Yaps too — don't assume Clean Yap == raw.
This module is the RAW Clean Yap engine (editable CapCut text). A Clean Yap can also ship medium
(build-hf-captions.py -> named .mov type layers) or well-done (build-reel-type.py -> baked MP4).

Shares the same engine mechanics/gotchas as superyap.py (VectCutAPI on :9001, font patch, main-track
normalize, register). Kept as a standalone module so the Super Yap engine is never in a Clean Yap's
import path. CapCut MUST be quit before finalize().
"""
import os, json, time, glob, shutil, subprocess, math
import sys as _sys   # force UTF-8: a cp1252 Windows console can't print ✓ or →
for _stream in (_sys.stdout, _sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image


import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
import vectcut_engine                                # turns the editing engine on, follows slow saves (never a dead end)
def _capcut_fonts_dir():
    """Where CapCut keeps the fonts the creator has added, on whichever OS this is.
    Existence-checked, never guessed: tries the Windows locations first, and if none of them are
    present falls back to the macOS container path, which is exactly the old behaviour."""
    import os as _os
    if _os.name == "nt":
        _la = _os.environ.get("LOCALAPPDATA", "")
        for _c in (_os.path.join(_la, "CapCut", "User Data", "Cache", "effect"),
                   _os.path.join(_la, "Microsoft", "Windows", "Fonts"),
                   _os.path.join(_os.environ.get("WINDIR", r"C:\Windows"), "Fonts")):
            if _c and _os.path.isdir(_c):
                return _c
    return _os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts")

BASE = "http://localhost:9001"
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
FONTS_DIR = _capcut_fonts_dir()
import frame as _frame; _frame.adopt()   # a wide job builds a wide draft
import safe_zones as _sz_frame
CANVAS_W, CANVAS_H = _sz_frame.W, _sz_frame.H
US = 1_000_000

# ---- LOCKED CLEAN-YAP DEFAULTS ----
WHITE, BUTTER, BLACK = "#FFFFFF", "#FFFFC2", "#000000"
# FONTS — ALL shipped typography comes from the buyer's CHOSEN style pack, resolved per-role via
# hook_font()/thought_font() (Editorial/Playful/Butter, or a custom pack). There is NO hardcoded font
# default — a build with no resolved pack RAISES (see _pack_or_default); the engine never reaches for a font
# that is not part of a pack. The creator's own reels pass her personal fonts EXPLICITLY (fallback_font),
# never from a shipped constant. (the creator: "for the yaps we ship, dont default to playfair. the user
# gets to choose their default style".) personal fonts vs ship fonts
# FONT_THOUGHT is kept ONLY as an identity marker for the thought-bubble line-spacing on the creator's own
# personal thought font — never a default, never stamped, so it cannot leak (a buyer's pack thought font
# never equals it). A buyer's thought bubbles get the same spacing through the pack's thought font
# (is_thought_font below); this marker only keeps the creator's own reels exactly as they were.
FONT_THOUGHT = f"{FONTS_DIR}/UglyDaveAlternates.otf"  # personal thought font — spacing-comparison marker only, never a default

# ---- SHIP STYLE PACKS (buyer chooses; switchable) ----
import packbuild                                        # pack -> per-role font/size/case (creative-vault/style-packs.json)
import learned                                         # preferences the creator has TAUGHT (brand-kit.md Part C)
import capcut_fonts                                     # font_path + CapCut library resource_id resolution (buyer portability)
import script_fonts                                     # Greek / Cyrillic a pack font lacks: companion-face spans
_USER_STYLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "user-style.json")

import user_style                                       # where her default pack is kept (_local/ in the source copy)

def default_pack():
    """The buyer's saved default style pack, or None if they haven't chosen yet (first-edit chooser)."""
    return user_style.default_pack(_USER_STYLE)

def set_default_pack(name):
    """Persist the buyer's default pack (validated). Keeps a switch history. First-edit chooser calls this."""
    if name not in packbuild.names():
        raise ValueError(f"unknown pack {name!r}; choose one of {packbuild.names()}")
    return user_style.set_default_pack(name, _USER_STYLE)

def _pack_or_default(pack):
    pack = pack or default_pack()
    if not pack:
        raise ValueError("no style pack chosen — pick one of " + ", ".join(packbuild.names()) +
                         " (cleanyap.set_default_pack(...)); shipped yaps never default to a font.")
    return pack

def hook_font(pack=None):
    """SHIP hook font for the chosen pack (headline role). No pack + no saved default => raises (no Playfair default)."""
    return packbuild.role(_pack_or_default(pack), "headline")["font_path"]

_THOUGHT_FONTS = set()   # every font thought_font() has handed this build


def thought_font(pack=None):
    """SHIP thought-bubble font for the chosen pack (thought role)."""
    font = packbuild.role(_pack_or_default(pack), "thought")["font_path"]
    _THOUGHT_FONTS.add(font)
    return font


def is_thought_font(font, pack=None):
    """Does text set in this font get the tight thought-bubble line spacing? The pack's thought font does: the
    one thought_font() handed this build, or the thought font of the pack this build runs in (`pack`, else the
    build's own context). So does FONT_THOUGHT, which only the creator's own reels pass. The spacing used to be
    keyed on FONT_THOUGHT alone, so no shipped pack, and no spacing a buyer taught with /learn, ever reached a
    thought bubble."""
    if font == FONT_THOUGHT or font in _THOUGHT_FONTS:
        return True
    pack = pack or learned.context().get("pack")
    if not pack:
        return False
    try:
        return font == packbuild.role(pack, "thought")["font_path"]
    except Exception:
        return False
STAND_IN = "Inter_Black"                               # engine built-in placeholder; patched in finalize
LINE_SPACING_THOUGHT = -0.15                           # thought-bubble line height — the creator's dialed-in value (2026-08-02, from her edits)
SIZE_THOUGHT = 12                                       # thought bubbles — the creator's dialed-in size (2026-08-02; 15 read oversized)
SIZE_HOOK = 17                                          # SHORT-hook default; long hooks shrink — use hook_size() below

def hook_size(text):
    """Hook size scales to hook LENGTH so it wraps to ≤3 lines and never runs off frame (the creator pays
    attention to this — she sized a 59-char POV hook to 14). Ladder calibrated to her edits.

    A size she has TAUGHT (`/learn`) wins over the ladder, because she looked at a real reel to pick it."""
    n = len(text)
    ladder = 17 if n <= 20 else 16 if n <= 40 else 14 if n <= 64 else 13
    learning_context()
    return learned.get("hook.size", ladder)


def thought_size():
    """Thought-bubble size: what she taught, else the dialed-in default."""
    learning_context()
    return learned.get("thought.size", SIZE_THOUGHT)


def thought_line_spacing():
    """Thought-bubble line spacing: what she taught, else the dialed-in default."""
    learning_context()
    return learned.get("thought.line_spacing", LINE_SPACING_THOUGHT)
# Slow zoom-in opener (the creator's default for clean yaps, ESP confessional): keyframe the first footage clip's
# scale from INTRO_ZOOM_FROM -> INTRO_ZOOM_TO over INTRO_ZOOM_SECS at the clip start, then hold TO.
INTRO_ZOOM_FROM, INTRO_ZOOM_TO, INTRO_ZOOM_SECS = 1.06, 1.22, 1.4
# Layer order (render_index; higher = on top). img_ = baked emoji / text glyphs only (NOT doodle stickers).
RI_FOOTAGE, RI_IMG, RI_TEXT = 0, 12000, 15000

# ---------------- ENGINE ----------------
def call(ep, _strict=True, **kw):
    """One VectCut call. FAIL LOUD by default: a failed add_video/add_text/add_audio used to print "ERR" and
    CONTINUE, so a missing clip or a bad text produced a PARTIAL draft that still reported success. Now it
    raises. Pass _strict=False only where a failure is benign (the idempotent re-save in finalize)."""
    # The engine's backups live in vectcut_engine.post: it turns the engine on when it is off (the #1 buyer state),
    # follows a save that runs past the wait through the engine's own progress record, and gives any other slow
    # call one longer try. What still raises (NotRunning / TooSlow, both RuntimeError) says what to do next.
    j = vectcut_engine.post(BASE, ep, kw)
    if not j.get("success"):
        msg = f"VectCut {ep} failed: {str(j.get('error'))[:200]}"
        if _strict:
            raise RuntimeError(msg + "  (the draft would be INCOMPLETE — fix the input, do not hand this off)")
        print("ERR", msg)
    return j

def probe_dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", p]).strip())

_JOB_DIR = None     # set by add_cut; the job folder the subject measurement lives in


_CTX_REGISTER = "confessional"   # the Clean Yap treatment's register; the reel's own plan, or learning_context(), overrides


def learning_context(register=None, pack=None):
    """State what this reel is, so a preference she taught for one kind of reel applies (and no other).
    A reel's build script calls this when it knows better than the default; add_cut also reads the job's
    caption-plan.json. Safe to call more than once."""
    global _CTX_REGISTER
    if register:
        _CTX_REGISTER = register
    learned.context_for_build("yap", register=_CTX_REGISTER, pack=pack,
                              job_dir=globals().get("_JOB_DIR"))


_CUT_END = None      # where add_cut's cut ends, for a whole-reel clip (her logo)


def add_cut(did, cuts, rawdir, punch=None):
    """Splice the locked rough cut onto the main track. punch={index: scale} for optional gentle push-ins
    (Clean Yaps usually stay still — leave punch empty)."""
    punch = punch or {}
    # Remember the JOB this draft is being built from. finalize() only has the CapCut draft folder, which
    # lives under ~/Movies/CapCut and can never be walked up to reach projects/<job>/subject-zones.json — so
    # without this the subject guard would look in the wrong tree, find nothing, and report "not measured"
    # forever while quietly passing every build. Every build calls add_cut, so the hint costs nothing and
    # works for build scripts that already exist.
    global _JOB_DIR
    _JOB_DIR = os.path.dirname(os.path.abspath(rawdir))
    learning_context()                # now the job is known, its plan's register wins
    # iPhone HDR footage would come out grey in CapCut and be refused at finalize, after the whole build. Convert
    # the job's raw/ to normal colour first (hdr.py --apply, the HDR copies kept), so the cut is laid on those.
    vectcut_engine.convert_job_hdr(rawdir)
    # her speed / zoom / split-off sound / audio clips, when the cut was pulled back from her own timeline
    global _CUT_END
    _CUT_END = cut_placement.place(call, did, cuts, rawdir, punch)

def _anim(name):
    # Animation names resolve via getattr on the server enum, so a display name with SPACES
    # ("Random Typewriter") silently fails and the anim is dropped. Normalize display -> api form.
    return name.replace(" ", "_") if name else name

_STYLE_SAID = set()
_STYLE_TEXT = {}
_STYLE_ROLE_PENDING = {}    # normalized text -> role, for text that got a taught animation (finalize swaps stand-ins)

def _taught_anim(track, kind):
    """The text animation she taught with "learn this style" (favorites.py learn-style), for text the reel's
    own plan leaves unanimated. Takeover words never get one: they reveal in place, unanimated, by rule."""
    t = (track or "").lower()
    if t.startswith(("tk", "takeover")):
        return None
    role = "hook" if t.startswith("hook") else "text"
    try:
        import favorites
        a = favorites.style_animation(role, kind)
    except Exception:
        return None
    if a:
        _STYLE_ROLE_PENDING[kind] = role
    if a and (role, kind) not in _STYLE_SAID:
        _STYLE_SAID.add((role, kind))
        print(f"  from the style you taught me: {role} text {'comes in' if kind == 'in' else 'leaves'} with {a.replace('_', ' ')}")
    return a

def _trial_wrap(text, size):
    from capcut_text import wrap_text
    return wrap_text(text, size)

def add_text(did, t, s, e, fp, sz, x, y, track, color=WHITE, intro=None, outro=None):
    """Hook or thought bubble (the pack's hook / thought font). fp = real font path (patched in at finalize)."""
    import trial_hook                                   # a trial reel: the hook block gets the trial's words
    t, sz = trial_hook.swap(track, t, sz, hook_size=globals().get("hook_size") if str(track).lower().startswith("hook") else None,
                            wrap=_trial_wrap)
    if t is None:                                        # the trial has fewer hook lines: this one is left out
        return
    if intro is None:
        intro = _taught_anim(track, "in")
    if outro is None:
        outro = _taught_anim(track, "out")
    if _STYLE_ROLE_PENDING:
        import re as _re
        _STYLE_TEXT[_re.sub(r"\s+", " ", str(t)).strip()] = next(iter(_STYLE_ROLE_PENDING.values()))
        _STYLE_ROLE_PENDING.clear()
    call("add_text", draft_id=did, text=t, start=s, end=e, font=STAND_IN, color=color, size=sz,
         transform_x=x, transform_y=y, intro_animation=_anim(intro), outro_animation=_anim(outro), track_name=track)

def add_png(did, path, st, en, x, y, track, scale=None, target_w=None):
    """Minimal image overlay — for a BAKED EMOJI / text glyph only (custom fonts can't render emoji).
    NOT for doodle stickers; those are a Super Yap feature."""
    # A sticker / glyph is an optional item: one that is not there (or will not open) is skipped with a line, and
    # the reel is built without it rather than the whole build dying over it.
    try:
        im = Image.open(path); cw, ch = im.size
    except (OSError, ValueError) as e:
        vectcut_engine.skip_note("sticker", path, "no file there" if not os.path.exists(path) else f"would not open: {e}")
        return None
    sc = scale if scale is not None else (target_w/cw if target_w else 0.2)
    call("add_image", draft_id=did, image_url=path, start=st, end=en, width=cw, height=ch,
         scale_x=sc, scale_y=sc, transform_x=x, transform_y=y, track_name=track)

def add_sfx(did, path, at, dur, volume=None, track="sfx", programme=None):
    """Matched/trimmed SFX — trim to EXACT length (dur), placed at timeline `at`. sfx must match motion duration

    LEVEL: volume=None (the default) AUTO-LEVELS via the shared `audio_levels` module. Do not hand-pick a
    multiplier: the bundled SFX span ~20 dB of intrinsic level, so the same number makes one cue slap and
    another inaudible, and it fails SILENTLY. `programme` = the cut, to place cues under the real voice.
    An explicit numeric volume is still honoured. sfx music must auto level"""
    import audio_levels
    if not path or not os.path.isfile(path):   # an optional cue with no sound file: skip it, finish the reel
        vectcut_engine.skip_note("sound cue", path)
        return None
    if volume is None:
        volume = audio_levels.sfx_volume_for(path, programme, dur)   # the north star: under her voice, by loudness
        audio_levels.report([{"file": path, "gain_db": 20 * math.log10(max(volume, 1e-6)), "how": "auto"}],
                            prefix="[sfx]")
    call("add_audio", draft_id=did, audio_url=path, start=0, end=dur, target_start=at, volume=volume, track_name=track)


def add_sound_plan(did, job, programme=None):
    """Place the reel's planned sound WITH her Sound edits from the visual editor (product/sound_plan.py: a cue she
    switched off is left out, a swapped one plays her pick, the music bed follows her on/off, song and level).
    Reads the plan the engine writes (caption-plan.json "sfx" / "music"; an older reel's sfx-plan.json), so write the
    cues there first (after capcut_sfx.plan_sfx) and call this instead of add_sfx in a loop. Each cue is trimmed to
    its motion and auto-leveled like add_sfx; overlapping cues get their own lane (CapCut refuses an overlap on one
    track). programme = the cut (default outputs/<job>.mp4). Returns (cues placed, music file or None)."""
    import audio_levels, sound_plan
    jd = sound_plan.job_dir(job)
    if programme is None:
        programme = sound_plan._programme(jd)
    cues, music = sound_plan.cues_for_build(jd)
    lanes, placed = [], 0
    for c in sorted(cues, key=lambda c: c["t"]):
        dur = float(c["trim"]) if c.get("trim") else probe_dur(c["file"])
        lane = next((i for i, free in enumerate(lanes) if c["t"] >= free), len(lanes))
        if lane == len(lanes):
            lanes.append(0.0)
        lanes[lane] = c["t"] + dur + 0.02
        add_sfx(did, c["file"], c["t"], dur, volume=c["volume"], track="sfx" if lane == 0 else f"sfx{lane + 1}",
                programme=programme)
        placed += 1
    bed = None
    if music and music.get("file") and os.path.isfile(music["file"]):
        at = float(music.get("at", 0) or 0)
        length = probe_dur(music["file"])
        if programme and os.path.isfile(programme):
            length = max(0.1, min(length, probe_dur(programme) - at))
        gain = (float(music["gain_db"]) if "gain_db" in music
                else audio_levels.bed_gain_for(music["file"], programme, music.get("duck_db")))   # her taught level counts
        call("add_audio", draft_id=did, audio_url=music["file"], start=0, end=length, target_start=at,
             volume=audio_levels.to_linear(gain), track_name="music")
        bed = music["file"]
        print(f"[sound] music bed {os.path.basename(bed)} in at {at:.2f}s  gain {gain:+.1f} dB")
    print(f"[sound] {placed} cue(s) placed from the sound plan")
    return placed, bed

# SHARED base guardrails — called in EVERY format's finalize (Clean Yap / Super Yap / VO), never
# copy-pasted per format (the creator's rule 2026-08-02: base edits happen across every format, always consistent).
from capcut_ripple import enforce_maintrack_ripple, verify_maintrack_anchor   # magnet ALL tracks + audio to main track + fail-safe
from capcut_text import sanitize_draft_text           # repair corrupt text spans + 9:16 wrap safety
import capcut_color                                  # base guardrail: every video segment SDR (single source for hdr_settings)
import capcut_media                                   # FAIL-SAFE: every clip project-local + registered (media panel) + importable
import capcut_motion                                  # DEFAULT camera motion: opener zoom-in + jump-cut punches (strong default)
import cut_placement                                  # lays the cut as she set it (speed, zoom, split sound)


def finalize(did, name, font_map, anim_durations=None, fallback_font=None, job=None, pack=None):
    """Register + normalize: patch custom fonts, put img_ overlays above footage, normalize the main
    track to CapCut's flag=0 shape. font_map = {exact_text: font_path}. CapCut MUST be quit first.
    anim_durations = {animation_name: seconds} overrides an intro ('in') animation's length,
    e.g. {"Random Typewriter": 1.25} to slow the hook type-on. pack = the style pack the reel is built in,
    so its thought font gets the thought-bubble line spacing (optional: see is_thought_font)."""
    import review_route; review_route.refuse_if_editor(job, "the Clean Yap build")   # its export is the Finish tab
    import draft_safety; draft_safety.require_capcut_quit("build this reel")   # else CapCut's next save wipes it
    import trial_hook                                    # a trial reel: its own name, the script's fonts on the trial's words
    trial_hook.stop_unplaced(CAP, did)                   # no hook text placed: stop before any draft is written
    name, font_map = trial_hook.name(name), trial_hook.remap(font_map)
    for _line in trial_hook.report():
        print(_line)
    import plan_language                                 # her hook and thoughts in her language: a warning, never a stop
    plan_language.warn(globals().get("_JOB_DIR") or plan_language.job_dir(job), texts=list(font_map or {}))
    # VectCut holds the draft only in memory (keyed by draft_id) until /save_draft flushes it to
    # the CapCut projects folder. Do it here so the documented add_cut->add_text->add_sfx->finalize
    # flow works on its own; without it the os.rename below hits a path that was never written.
    # Idempotent: safe if the draft was already saved (non-strict: a re-save "failure" is benign here).
    # her logo, only when she turned it on for this pack (watermark.py): its own clip, the whole reel
    try:
        import watermark
        watermark.add_to_capcut(call, did, pack, _CUT_END)
    except Exception as e:                              # optional: a logo problem never stops the reel
        print(f"  (your logo was left off this draft: {e})")
    _saved = call("save_draft", _strict=False, draft_id=did, draft_folder=CAP)
    vectcut_engine.refuse_failed_media(_saved, os.path.join(CAP, did))   # a clip left out is a failed save, said why
    name = name.replace("/", "-").replace(":", "-")   # a path separator in a draft name would break the rename below
    # Built with os.path.join, matching EXACTLY how util.build_draft_asset_path() constructed the asset
    # paths baked into the draft's JSON (it appends draft_id/asset segments onto CAP as-is, without
    # normalizing CAP's own separators) -- an f-string "/" join produces a DIFFERENT literal string on
    # Windows (CAP already mixes slash styles), so the string-replace fixup below would silently never
    # match and every asset path would still point at the pre-rename draft_id folder.
    old = os.path.join(CAP, did); D = os.path.join(CAP, name)
    if not os.path.isdir(old):
        # VectCut's save left nothing to finish (on one Mac a security app refused it any write in ~/Movies).
        # Say why in plain words instead of letting the rename below end on a bare FileNotFoundError.
        raise RuntimeError(__import__("capcut_store_redirect").save_refused_message(_saved, CAP))
    if os.path.isdir(D) and D != old:
        # FAIL-SAFE (locked): NEVER destroy an existing draft. A rebuild goes to a NEW name so her by-hand edits
        # can never be wiped. The finished build is not thrown away over a name, though: it lands on the next
        # free version (draft_safety.next_version, the same move capcut_handoff makes), and the draft that holds
        # the name is never touched.
        taken = name
        try:
            nxt = _ds.next_version(_ds.base_of(name))
        except Exception:
            nxt = None
        if not nxt or os.path.isdir(os.path.join(CAP, nxt)):
            shutil.rmtree(old, ignore_errors=True)
            raise RuntimeError(
                f"REFUSING to overwrite existing draft {name!r}: a rebuild would wipe the creator's in-app "
                f"edits (CapCut has NO version history), and no free version name could be found next to it. "
                f"Build to a new name, or LAYER the change on top of the existing draft. See product/draft_safety.py.")
        name, D = nxt, os.path.join(CAP, nxt)
        print(f"  \"{taken}\" is already a project in CapCut, so this build is \"{name}\". Yours is untouched.")
        vectcut_engine.note(vectcut_engine.STEP, f"draft name {taken!r} was already taken; built to {name!r} instead")
    # SUBJECT GUARDRAIL (base, every format): no text ends up ON her. The placement numbers on this route
    # are hand-written, so this is the only thing standing between a copied-forward transform_y and a hook
    # across her forehead.
    # It runs HERE, before the rename below, because that rename is the point of no return: after it the
    # folder owns the final draft name, so refusing later would leave an invisible folder squatting that
    # name — and the next build, with the placement fixed, would be told it must not overwrite the
    # creator's work. Two confusing errors for one real one. Refusing before the rename leaves nothing.
    # Warns (never refuses) when her footage was not measured — an unmeasured job is not a defect, but it
    # is not a clean bill of health either, and it says so. The CHECK degrades to a warning if it cannot
    # run; only a real breach refuses. A guardrail that can itself break a working build is a worse bug
    # than the one it catches.
    _sbr = []
    try:
        import subject_place
        _dj = json.load(open(_ds.draft_json(old), encoding="utf-8"))
        _mv = 0
        if os.environ.get("SUBJECT_ALLOW_OVERLAP") != "1":   # tried to fix it first: text on her moves to the nearest
            for _cp in [_ds.draft_json(old)] + [p for p in _ds.draft_json_copies(old, require=False) if p != _ds.draft_json(old)]:
                _cd = json.load(open(_cp, encoding="utf-8"))   # open zone, in every copy CapCut reads
                _n = subject_place.auto_clear(_cd, job or _JOB_DIR or old)
                if _n:                                   # written whole or not at all: never a half-written draft
                    json.dump(_cd, open(_cp + ".clear", "w", encoding="utf-8"), ensure_ascii=False)
                    os.replace(_cp + ".clear", _cp)
                    _mv = max(_mv, _n)
            if _mv:
                _dj = json.load(open(_ds.draft_json(old), encoding="utf-8"))
                print(f"  \u2713 SUBJECT: moved {_mv} piece(s) of text off her face to the nearest open spot")
        _sbr, _slines = subject_place.report(_dj, job or _JOB_DIR or old)
        for _l in _slines:
            print(_l)
    except Exception as _e:
        print(f"  \u26a0 SUBJECT: placement not checked ({type(_e).__name__}: {str(_e)[:120]}). "
              "NOT evidence that text is clear of her.")
    if _sbr and os.environ.get("SUBJECT_ALLOW_OVERLAP") != "1":   # still on her after the fix: she gets her draft anyway
        print("  \u26a0 SUBJECT: built anyway (she always gets her draft). Tell her which text sits on her face; "
              "she moves it in CapCut, or it stays on purpose.")

    os.rename(old, D)
    try:
        # On Windows, `old`/`D` contain backslashes, but we are doing a RAW-TEXT replace on the file's bytes
        # BEFORE it is JSON-parsed -- and JSON escapes a literal backslash as two characters ("\\"). So the file's
        # raw text has every backslash doubled, and a plain-string search for the unescaped path silently never
        # matches, leaving every asset path pointed at the pre-rename draft_id folder forever. Mac paths use "/",
        # which JSON does not escape, which is exactly why this never surfaced there. Replace both the raw form
        # (a no-op check on Mac/Windows alike when no backslash is present) and the JSON-escaped form.
        def _json_escaped(p): return p.replace("\\", "\\\\")
        old_json, D_json = _json_escaped(old), _json_escaped(D)
        for f in glob.glob(f"{D}/*.json") + _ds.draft_json_copies(D, require=False):
            s = open(f, encoding="utf-8").read()
            changed = False
            if old in s: s = s.replace(old, D); changed = True
            if old_json in s: s = s.replace(old_json, D_json); changed = True
            if changed: open(f, "w", encoding="utf-8").write(s)
        p = _ds.draft_json(D); d = json.load(open(p, encoding="utf-8"))
        fm = {k.upper(): v for k, v in font_map.items()}   # case-insensitive (VectCut may uppercase single words)
        # Unmatched text falls back to a PACK font, NEVER a personal font (the creator: "fallback should be the
        # pack font"). Explicit fallback_font wins; else the most-common font the caller PROVIDED (pack fonts for
        # ship, personal on her reels). If the map is EMPTY and no fallback_font was passed there is no font to
        # use: FAIL LOUD rather than reach for a non-pack default.
        if fallback_font:
            default_font = fallback_font
        elif fm:
            default_font = max(fm.values(), key=list(fm.values()).count)
        else:
            # Refused after the rename: hand back the name so a corrected rebuild is not told it must
            # not overwrite "existing work" that is really this failed attempt (draft_safety refuses to
            # touch anything registered, and registration is the last step of a SUCCESSFUL build).
            _ds.discard_unfinished(D)
            raise RuntimeError(
                "finalize(): no fonts resolved for this draft and no fallback_font given — pass a pack font "
                "(cleanyap.hook_font(pack)/thought_font(pack)) or fallback_font=<pack font path>. "
                "The engine never defaults to a personal font.")
        _script_texts = []
        for m in d["materials"].get("texts", []):
            txt = json.loads(m["content"]).get("text", "")
            font = fm.get(txt.upper(), default_font)
            _script_texts.append((m, font))    # Greek / Cyrillic it lacks: companion spans, after the wrap below
            capcut_fonts.apply(m, font)   # sets font_path + (for CapCut-library fonts) resource_id/platform so a buyer's CapCut resolves it
            m["alignment"] = 1; m["preset_has_set_alignment"] = True
            if is_thought_font(font, pack):
                m["line_spacing"] = thought_line_spacing()   # thought-bubble multi-line = tight, not loose
            c = json.loads(m["content"])
            for st in c.get("styles", []):
                if isinstance(st.get("font"), dict): st["font"]["path"] = font; st["font"]["id"] = ""
            m["content"] = json.dumps(c, ensure_ascii=False)
        if anim_durations:
            for ma in d["materials"].get("material_animations", []):
                for a in ma.get("animations", []):
                    if a.get("type") == "in" and a.get("name") in anim_durations:
                        a["duration"] = int(round(anim_durations[a["name"]] * US))
        for t in d["tracks"]:
            if t.get("name", "").startswith("img_"):
                for seg in t["segments"]:
                    seg["render_index"] = RI_IMG
        d["tracks"] = [t for t in d["tracks"] if not (t["type"] == "video" and len(t["segments"]) == 0)]
        vids = [t for t in d["tracks"] if t["type"] == "video"]
        if vids:
            footage = max(vids, key=lambda t: len(t["segments"]))
            footage["flag"] = 0; footage["name"] = ""; footage["is_default_name"] = False  # anchor identity (magnet)
        # DEFAULT MOTION (locked strong-default): a slow zoom-in on the opener + gentle jump-cut punches, so the
        # frame never sits dead still. EVERY move reframes on her face in THAT shot (measured off the
        # footage the draft points at): a scale keyframe alone zooms about the frame centre, which slides
        # an off-centre creator toward the edge on every push-in. Only touches clips still at scale 1.0
        # AND transform 0/0 — any punch the build passed to add_cut, and any zoom or nudge the creator
        # set herself, is preserved. Must run BEFORE the guardrail below (it flips
        # uniform_scale off for exactly these scale changes so they render). See capcut_motion.py.
        # Motion is a STRONG DEFAULT, never a gate she has to ask for — but "no push-in on my openers" is a
        # preference she can teach once instead of saying every reel.
        learning_context()
        if cut_placement.is_your_turn(globals().get("_JOB_DIR")):
            # her own CapCut timeline: every zoom and every still shot in it is her call, kept exactly
            print("[motion] your-turn cut — your own zooms and framing kept exactly, no default motion added")
        elif learned.get("motion.opener_zoom", True):
            _z, _p = capcut_motion.apply_default_motion(d)
            if _z or _p: print(f"[motion] intro zoom: {_z} · jump-cut punches: {_p}")
        else:
            print("[motion] opener push-in off (you taught me that) — say \"/learn forget\" to bring it back")
        # SCALE GUARDRAIL (locked): VectCut writes clip.scale but leaves uniform_scale.on=True (value hardcoded
        # 1.0), and uniform_scale OVERRIDES clip.scale — so every jump-cut zoom / b-roll inset silently renders at
        # 1.0 in CapCut. Turn uniform_scale OFF wherever a non-1.0 clip.scale or a scale keyframe is set.
        for t in vids:
            for seg in t["segments"]:
                sc = seg.get("clip", {}).get("scale", {})
                scaled = abs(sc.get("x", 1.0) - 1.0) > 1e-3 or abs(sc.get("y", 1.0) - 1.0) > 1e-3
                kf = any(k.get("property_type") in ("KFTypeScaleX", "KFTypeScaleY")
                         for k in seg.get("common_keyframes", []))
                if (scaled or kf) and isinstance(seg.get("uniform_scale"), dict):
                    seg["uniform_scale"]["on"] = False
                # SDR COLOR FIX (locked): see product/capcut_color.py for why. The sweep below
                # (enforce_sdr) is the draft-wide guarantee; this keeps the per-segment pass in step.
                if capcut_color.needs_correction(seg):
                    seg["hdr_settings"] = capcut_color.sdr_settings()
        sanitize_draft_text(d)                      # base guardrail: no corrupt text spans, 9:16 wrap-safe
        for _m, _font in _script_texts:             # letters the pack font lacks: a span in the same companion
            script_fonts.say_capcut(script_fonts.capcut_companions(_m, _font))   # face the rendered routes use
        capcut_color.enforce_sdr(d)                 # base guardrail: no segment reaches CapCut tagged HDR
        _hdr = capcut_color.hdr_media(d)            # ...and no file it plays is HDR either (washed out if it is)
        if _hdr:                                    # convert what is left and go on; refuse only if that fails
            _hdr = vectcut_engine.convert_draft_hdr(d, _hdr, D)
        if _hdr:
            _ds.discard_unfinished(D)      # same reason: a refused build must not squat the name
            raise RuntimeError(capcut_color.CONVERT_FIRST.format(name=os.path.basename(_hdr[0]))
                               .replace("<job>", job or "<job>"))
        enforce_maintrack_ripple(d)                 # base guardrail: magnet ALL tracks + audio to main track
        _mp = verify_maintrack_anchor(d)            # FAIL-SAFE: never ship a dead magnet again (2026-08-12 regression)
        if _mp:
            _ds.discard_unfinished(D)      # same reason: a refused build must not squat the name
            raise RuntimeError("magnet anchor broken — build refused:\n  - " + "\n  - ".join(_mp))
        _media = capcut_media.ensure_shippable(d, D, fresh=True)  # FAIL-SAFE: every clip project-local + registered (links in the
        if _media:                                    # media panel) + importable — never ship "not linked" / ProRes again
            _ds.discard_unfinished(D)      # same reason: a refused build must not squat the name
            raise RuntimeError("media won't link/import in CapCut — build refused:\n  - " + "\n  - ".join(_media))
        try:                                           # the style she taught: her real CapCut animation in for the stand-in
            import favorites
            _sw = favorites.apply_style_swaps(d, _STYLE_TEXT)
            if _sw:
                print(f"  swapped in {_sw} of your own CapCut animation{'s' if _sw != 1 else ''} from the style you taught me")
        except Exception as _e:
            print(f"  (could not apply your taught animations: {_e}; the stand-in stays)")
        # The face measurement above can run for many minutes per clip, and CapCut may have been opened in
        # the meantime. Check again right before the draft is written: written under an open CapCut, the
        # whole build is silently dropped by its next save.
        _ds.require_capcut_quit("build this reel")
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        capcut_media.write_cover(d, D)              # FAIL-SAFE: the drafts grid needs a real draft_cover.jpg or the
                                                   # new draft can be INVISIBLE with no error (draft-not-visible bug)
        now = int(time.time())
        dm = json.load(open(f"{D}/draft_meta_info.json", encoding="utf-8")); dm["draft_name"] = name
        # A FRESH draft_id for every draft. The template carries one fixed id, so every draft the engine built
        # shared it, and CapCut, which keeps one project per id when it rebuilds its list, dropped the newer
        # version from the grid (a buyer's 1.2 vanished beside her 1.1, report 2026-10-17).
        import uuid as _uuid
        dm["draft_id"] = str(_uuid.uuid4()).upper()
        # FRESH TIMESTAMPS (locked): CapCut sorts + shows the drafts grid by draft_meta_info's own tm fields, not
        # root_meta. A DUPLICATE+rebuild (new version) inherits the source's stale times here, so the new draft
        # sorted to the end / went unseen. Stamp real current time so a new version always lands at the top.
        dm["tm_draft_create"] = dm["tm_draft_modified"] = now * US
        dm["tm_duration"] = d.get("duration", dm.get("tm_duration", 0))
        json.dump(dm, open(f"{D}/draft_meta_info.json", "w", encoding="utf-8"), ensure_ascii=False)
        # Register in root_meta_info.json (the drafts grid). Shared guard handles a brand-new CapCut whose
        # all_draft_store is [] (first-ever buyer build) instead of crashing on [0]. now/US threaded in so
        # the timestamp matches the draft_meta_info write above (CapCut sorts the grid off both).
        capcut_media.register_draft(CAP, name, D, p, dm.get("draft_id", did), d.get("duration", 0), now, US)
    except BaseException:
        # Anything that stops the build between the rename and the registration would leave a folder CapCut
        # cannot show that still owns the name, and the next build to that name would be refused as the
        # creator's existing work. Hand the name back first. discard_unfinished never touches a draft that
        # got registered, and the original error is the one worth showing.
        try:
            _ds.discard_unfinished(D)
        except Exception:
            pass
        raise
    try:                                     # snapshot so later in-app edits are detectable (never-replace fail-safe)
        import draft_safety; draft_safety.record_build(name)
    except Exception:
        pass
    for _ln in learned.report():                 # what came from her saved preferences (never applied silently)
        print(_ln)
    print("CLEAN YAP built + registered:", name, "| tracks v/img/text:",
          sum(t["type"] == "video" for t in d["tracks"]), "/",
          sum(t.get("name", "").startswith("img_") for t in d["tracks"]), "/",
          sum(t["type"] == "text" for t in d["tracks"]))
    return name                                # the name it landed on (the next version when hers was taken)
