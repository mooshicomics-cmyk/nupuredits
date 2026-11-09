#!/usr/bin/env python3
"""sound_plan.py — every sound on a reel as rows she can hear, switch off and swap, and the build honoring them.

The visual editor's Sound section reads this: each sound effect on the reel (when it plays in the cut, what it sits
on, on/off, a Swap menu with HER favorites first and the engine's library after) and the music bed (on/off, swap,
level). What she picks is saved to ONE file per reel, `projects/<job>/review/sound.json`, and the builds read it.

## Where a reel's sounds come from (one source of truth, plus her edits on top)

The sound pass still decides the cues; nothing here re-plans them. They live where the pipeline already writes them:
  * `caption-plan.json` "sfx" / "music": the engine's plan (spoken_cues.py and the creative plan write it). The
    well-done bake (build-reel-mp4.py) and the CapCut handoff (capcut_handoff.py, also the medium route's
    separate-layers handover) read it. Cue shape: {"file": name-or-path, "at": cut seconds, "trim", "gain_db"?}.
  * `sfx-plan.json` "cues" / "music": an older per-reel shape some hand-built reels use ({"file", "t", "volume",
    "beat"}). Read for the page when caption-plan.json has no sfx; only that reel's own driver plays it.

`review/sound.json` is an OVERRIDE LAYER over that plan, not a second plan. That is the cleaner fit: the builders
already read the caption plan, and a layer keyed by cue means a re-planned reel never plays a stale copy. Each cue
has a stable id (`<sound>@<cut seconds>`); her edit to a cue (on/off, a swap) is kept by that id. A cue that is no
longer in the plan (the plan changed since she edited) is reported as an orphan and left out, never guessed onto
another cue. The file holds the full rows the page shows, so the page reads one file; only a cue's `on` and a swap
(`swapped`, `choice`, `file`, `name`, `source`), and the music's `edits`, are hers. Times, what a cue sits on and the
plan's own levels always come fresh from the plan.

    {"version": 1, "from": "caption-plan.json",
     "cues": [{"id", "t" (cut seconds), "name", "file" (engine-relative path, or absolute outside the engine),
               "source": "favorite"|"library"|"hers", "on": true, "gain_db", "gain_how": "auto"|"set",
               "on_look": layer name or null, "beat", "trim", "choice", "swapped", "original": {"name", "file"}}],
     "music": {"on", "name", "file", "level_db", "level_how", "choice", "at", "swapped",
               "edits": {"on"?, "file"/"name"/"source"/"choice" (a swapped song)?, "level_db": dB or "auto"?}}}

## Moments: every look that moves gets a sound row, timed to its motion

moments(job) reads review/looks.json "layers" (the captions layer and switched-off looks are skipped) and, for each
look, its composition's own timeline script (<dir>/index.html: `window.__timelines[id] = tl` with GSAP calls such
as `tl.fromTo("#hk0",{autoAlpha:0,...},{autoAlpha:1,duration:0.5,...},0.20)`). The ENTRANCE is the earliest tween
that makes something visible (fromTo/from from autoAlpha/opacity 0, a to/set that raises it), else the earliest
tween that moves something in; its position + the look's `offset` is the moment's cut time `t`, its duration the
motion length `motion_s` (a count-up runs to the end of its counting; a type-on to its last letter). No tween
found: `t` = the look's offset and `"timing": "start"` (else "motion"). EVERY MOTION GETS ITS OWN SOUND: a look that
brings in several things at separate moments (four cards popping in one after another, a list's lines) is one
moment per thing (entrances(): PART_GAP_S apart or more; a closer burst is one), keyed "<layer>#2", "#3" ... after
the first, each with its own sound row ("Part of your <look>" on the Sound tab). Positions timed by a loop
(`[0,1,2,3].forEach(i => tl.fromTo(..., T0 + i*0.45))`, `for (let i...)`) and a numeric stagger over a class are
read pass by pass. A look that shows her words as she says them (hook, takeover, captions, type-on) and a count-up
stay one moment. Two looks bringing something in on the same frame (a sketch's in-front and behind halves) are one
motion to the viewer: one sound (the later folds into the first, "with"). `kind` (pop / slide / rise / blur / reveal /
card / count / type / other) comes from the look's type (a counter, a type-on, a card) and else from how the
entrance moves (a blur, a scale-up, a slide, a small rise, a wipe).

A moment's sound is stored ANCHORED to its look, never to a time: {"anchor": {"layer", "at": "entrance"}}, so a
look that moves (or a cut that changes its offset) takes its sound with it on the next read. A planned cue already
sitting on a look's entrance (within MATCH_S) IS that look's sound, so a default is never stacked on top of it.

## Defaults that follow the motion (defaults_for / apply_defaults)

Per moment, by its kind, from HER sources first, in this order: (a) her favorites folder (favorites/sounds), (b) her
CapCut favorites shelf (product/favorites.py -> _local/sounds), (c) Epidemic Sound files she already downloaded
(LOCAL only, never a network call: the Epidemic Sound app's folder ~/Documents/Epidemic Sound and any reel's
sfx/epidemic*/ or audio/epidemic*/ folder), (d) the engine's shipped library (product/creative-vault/sfx/cc0 first,
then the bundled Pixabay set; the index's switched-off sounds never). The first source with a sound that fits the
kind wins (matched on the sound's own name / the index's description and job tag); inside it, the least-used fit
that isn't the cue just before, so nothing repeats back to back. Each is trimmed to its motion (a hit: the motion,
at least MIN_HIT_S; a type-on or count-up: exactly the motion) and auto-leveled like every cue.
REGISTER: a confessional reel (or a somber one) gets NO default sounds; its moments show "no sound" until she adds
one. The register is the one recorded for the reel (product/choices.py), or the one passed in.

## sound.json, besides the plan-cue edits

    "added": [{"id": "look:<layer>" | "add-<n>", "anchor": {"layer", "at": "entrance"} | null, "t" (free cues),
               "word"?, "choice", "file", "name", "source", "on", "none", "nudge" (s, +-NUDGE_MAX), "how":
               "default"|"hers"}],
    "sfx_enabled": true            the reel-wide Sound effects switch (off: no sound effects in any build; music stays)
    "voice_enabled": true          her clip's own sound (off = a muted clip: no voice on the CapCut main track, none in
                                   the MP4 export, none in the page's preview; the sound effects and music still play)
A plan cue's edit may also carry "nudge" and "none".

## Levels (the engine's rule, never a number she has to pick)

A swapped sound is leveled exactly the way the engine levels every cue (product/audio_levels.py): its peak measured
and placed SFX_DUCK_DB under the cut's peak, so any sound she picks lands at the same loudness. A cue the plan set by
hand keeps its level until she swaps it; the swap makes it auto. The music bed's level is auto (its mean
BED_DUCK_DB under her voice) until she sets `level_db`; "auto" puts it back. The gains shown are measured with the
same functions the builds use, cached in `_local/sound-levels.json` by file size + time.

## Which builds honor it

  * well-done (build-reel-mp4.py): yes, cues and bed, through for_build().
  * the CapCut project beside a well-done reel, and the medium route's separate-layers handover
    (capcut_handoff.py): yes, cues and bed, through for_build(); every cue now gets the same level the bake gives it.
  * raw / Super Yap CapCut drivers: when the driver places sound with `cleanyap.add_sound_plan(did, job)` (the step
    CLEANYAP.md and SUPERYAP.md now name), which reads the plan through for_build(). A driver that still hand-places
    cues with add_sfx in a loop does not see her edits; the page's rows come from the plan, so write the cues into
    caption-plan.json "sfx" first.
  * reels that only have an sfx-plan.json (older hand-built drivers) and the Voiceover route (vo-build.py's own
    music/ambience): not yet. Their drivers read their own files; cues_for_build(job) gives them the edited list.
  * a draft already in CapCut is never rewritten: her edits reach CapCut on the next build, as a new version.
  * every route above that reads for_build() also gets, with no change of its own: the sounds on her looks (each
    resolved to its look's entrance in looks.json at build time, trimmed to the motion, auto-leveled), the sounds
    she added at a time, nudges, "No sound here", and the reel-wide Sound effects switch (off = no cues at all;
    the music bed follows its own switch). finish.py's export mix reads it the same way.

## The page's calls

    read(job)                                   the plan with her edits applied (no write). Rows: planned cues
                                                (origin "plan"), one per moving look (origin "look"; "empty" until
                                                it has a sound), sounds she added (origin "free"). Each row: id, t,
                                                name, file, source, on, none, empty, gain_db, gain_how, on_look, beat,
                                                trim, choice, swapped, missing, original, moment, anchor, motion_s,
                                                kind, look_name, timing, nudge, origin, word. Top level: sfx_enabled,
                                                moments, moments_without_sound, register, quiet, orphans, music.
    moments(job)                                the looks that move: [{"layer", "t", "motion_s", "kind", "look_name",
                                                "timing", "offset", "entrance"}]
    defaults_for(job, register=None)            {"register", "quiet", "reason", "moments": [moment + "default":
                                                {"choice", "name", "file", "source", "trim"} | None]}
    choices(kind="sfx"|"music", job=None)       a Swap menu: her favorites folder ("favorite"), her CapCut shelf
                                                ("capcut"), her Epidemic downloads ("epidemic"), this reel's own sounds
                                                ("hers", when job is given), then the engine library ("library",
                                                capcut_sfx.selectable(), never a glob). Each row:
                                                {"id", "name", "file", "source", "duration"}.
    swap(job, cue_id, choice_id)                "original" puts the planned (or motion-matched) sound back; "none"
                                                makes that moment silent
    toggle(job, cue_id, on)
    apply_defaults(job, register=None)          fill every moment that has no sound (never one she chose or silenced)
    add_cue(job, choice_id, t=None, layer=None, word=None)    a sound at the playhead (t) or on a look's entrance
    remove_cue(job, cue_id)                     a sound she added goes; a planned cue is switched off
    nudge(job, cue_id, delta_s)                 +-, the total held to +-NUDGE_MAX
    set_sfx_enabled(job, on)                    the reel-wide Sound effects switch
    set_voice_enabled(job, on)                  her clip's own sound (off = muted clip, every export and the preview)
    set_music(job, on=None, choice_id=None, level_db=None)    level_db: dB of gain, or "auto"
    preview_path(choice_id, job=None)           a local file a browser can play (converted once into _local/ if needed)
Each edit validates, writes sound.json atomically (tmp + os.replace) and returns the updated plan. Bad input raises
Refuse with a plain reason the page can show her.

    python3 product/sound_plan.py show <job>                  the rows, as the page sees them
    python3 product/sound_plan.py moments <job>
    python3 product/sound_plan.py defaults <job> [teaching|confessional]
    python3 product/sound_plan.py apply-defaults <job> [teaching|confessional]
    python3 product/sound_plan.py choices sfx|music [<job>]
    python3 product/sound_plan.py swap <job> <cue_id> <choice_id|none|original>
    python3 product/sound_plan.py toggle <job> <cue_id> on|off
    python3 product/sound_plan.py add <job> <choice_id> (--at SECONDS | --look LAYER) [--word N]
    python3 product/sound_plan.py remove <job> <cue_id>
    python3 product/sound_plan.py nudge <job> <cue_id> <+-seconds>
    python3 product/sound_plan.py sfx <job> on|off
    python3 product/sound_plan.py voice <job> on|off          off = a muted clip (her own sound out of every export)
    python3 product/sound_plan.py music <job> [--on|--off] [--choice ID] [--level DB|auto]

Stdlib + ffmpeg/ffprobe. Her files never leave her computer.
"""
import hashlib, json, math, os, re, subprocess, sys, tempfile, threading, time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import audio_levels      # the ONE place a level is decided
import capcut_sfx        # the engine's sound library (palette / selectable / disabled), never a glob
import favorites_folder  # her drop folder: favorites/sounds

LOCAL = os.path.join(ROOT, "_local")
LEVELS = os.path.join(LOCAL, "sound-levels.json")
PREVIEW_DIR = os.path.join(LOCAL, "sound-preview")
PLAYABLE = (".mp3", ".m4a", ".aac", ".wav")          # every browser the page runs in plays these
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".aif", ".aiff", ".flac", ".ogg", ".caf")
SFX_MAX_S = favorites_folder.LONGEST_SFX_S          # longer is a song: it goes in the bed, not on a cue
_LOCK = threading.RLock()                           # one writer at a time inside the page server
# Epidemic Sound files she already downloaded under her own account. Only LOCAL files: the Epidemic Sound app's
# own download folder, and the per-reel folders the epidemic-sound-design skill pulls into (sfx/epidemic*/,
# audio/epidemic*/). Nothing here ever reaches the network.
EPIDEMIC_HOME = os.path.join(os.path.expanduser("~"), "Documents", "Epidemic Sound")
PROJECTS_DIR = os.path.join(ROOT, "projects")
OWN_SAYS = "This sound is part of the look itself. Switch it off here, or swap the look."
MATCH_S = 0.30          # a planned cue this close to a look's entrance IS that look's sound
NUDGE_MAX = 600.0       # a sanity bound only: a nudge (or a drag on the timeline) keeps a sound inside her cut
MIN_HIT_S = 0.25        # a one-off hit (pop, whoosh, thud) is never trimmed shorter than this
DEFAULT_MOTION_S = 0.40 # a look whose motion can't be read: the length its sound plays
PART_GAP_S = 0.30       # a look's things coming in this far apart are separate motions, each with its own sound
MAX_PARTS = 16          # (a burst closer than that is one motion: one sound)
SAME_FRAME_S = 0.04     # two looks bringing something in this close together: one motion, one sound
CONTINUOUS = ("type", "count")    # the sound voices the whole motion: trimmed to EXACTLY its length
QUIET_HEAD_DB = 18.0    # a sound whose first stretch peaks this far under its own peak has not started yet: it plays
LATE_PEAK_TAIL_S = 0.35 # ... through its loudest moment and this much after (whole, when that reaches its end)


class Refuse(Exception):
    """A plain reason an edit can't be made, said to her as it is."""


# ── the reel ──────────────────────────────────────────────────────────────────────────────────────────────
def job_dir(job):
    """A reel's folder: an absolute path to one, or a name inside projects/ (never a path that climbs out)."""
    if os.path.isabs(str(job)) and os.path.isdir(job):
        return os.path.abspath(job)
    projects = os.path.realpath(os.path.join(ROOT, "projects"))
    p = os.path.realpath(os.path.join(projects, str(job)))
    if not job or not p.startswith(projects + os.sep) or not os.path.isdir(p):
        raise Refuse(f"There's no reel called {job!r} in projects/.")
    return p


def _json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _atomic_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    for i in range(6):            # Windows: a reader holding the file open makes replace fail for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, path)


def sound_json(jd):
    return os.path.join(jd, "review", "sound.json")


def _programme(jd):
    """Her cut, the reference every level is measured against (outputs/<job>.mp4), or None before there is one."""
    p = os.path.join(jd, "outputs", f"{os.path.basename(os.path.normpath(jd))}.mp4")
    return p if os.path.isfile(p) else None


# ── names and files ───────────────────────────────────────────────────────────────────────────────────────
def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:40] or "sound"


def cue_id(t, ref):
    """Stable id for a planned cue: the sound's name and where it plays, e.g. 'whoosh@12.260'."""
    stem = os.path.splitext(os.path.basename(str(ref or "")))[0]
    return f"{_slug(stem)}@{float(t):.3f}"


def _ids(entries, tkey):
    """Ids for a list of plan entries, with '#2', '#3' on the rare exact repeat (same sound, same moment)."""
    seen, out = {}, []
    for e in entries:
        base = cue_id(e.get(tkey, e.get("t", e.get("at", 0))) or 0, e.get("file"))
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}#{n}")
    return out


def _rel(path):
    """Engine-relative when inside the engine (so the folder can move), absolute otherwise."""
    if not path:
        return None
    ap = os.path.abspath(path)
    return os.path.relpath(ap, ROOT).replace(os.sep, "/") if ap.startswith(ROOT + os.sep) else ap


def _abs(path):
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def resolve_ref(jd, ref):
    """A cue's file as the builds resolve it: an absolute path, the reel's own folder (and its sfx/norm, sfx, audio
    folders, with or without an extension), the engine's sfx folder, then the library by name. None when missing."""
    if not ref:
        return None
    ref = str(ref)
    if os.path.isabs(ref):
        return ref if os.path.isfile(ref) else None
    cands = [os.path.join(jd, ref)]
    for d in (os.path.join(jd, "sfx", "norm"), os.path.join(jd, "sfx"), os.path.join(jd, "audio")):
        cands += [os.path.join(d, ref), os.path.join(d, ref + ".wav"), os.path.join(d, ref + ".mp3")]
    cands.append(os.path.join(capcut_sfx.SFX_DIR, ref))
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    pal = capcut_sfx.palette()
    f = pal.get(os.path.splitext(os.path.basename(ref))[0])
    if f and os.path.isfile(f):
        return f
    r = capcut_sfx.resolve_cue(ref, pal)
    return r[0] if r and os.path.isfile(r[0]) else None


def _index():
    return capcut_sfx._index()


def _shelf():
    """Her CapCut favorites shelf (product/favorites.py), as [{"name", "title", "file", "seconds"}], with "file"
    made absolute (favorites.py records it relative to the engine root, the folder that holds _local/)."""
    st = _json(os.path.join(LOCAL, "favorites.json"), {}) or {}
    home = os.path.dirname(LOCAL)
    return [dict(s, file=s["file"] if os.path.isabs(s["file"]) else os.path.join(home, s["file"]))
            for s in st.get("sounds", []) or [] if s.get("file")]


def _under(path, folder):
    try:
        return os.path.realpath(path).startswith(os.path.realpath(folder) + os.sep)
    except Exception:
        return False


def describe(jd, path):
    """(choice id, source, display name) for a sound file wherever it lives."""
    if not path:
        return None, "library", None
    if _under(path, favorites_folder.FOLDER):
        rel = os.path.relpath(os.path.realpath(path), os.path.realpath(favorites_folder.FOLDER)).replace(os.sep, "/")
        return f"folder:{rel}", "favorite", favorites_folder._pretty(os.path.splitext(os.path.basename(path))[0])
    if _under(path, capcut_sfx.FAVORITES_DIR):
        stem = os.path.splitext(os.path.basename(path))[0]
        title = next((s.get("title") for s in _shelf() if os.path.splitext(os.path.basename(s["file"]))[0] == stem), None)
        return f"fav:{stem}", "capcut", _clean_title(title) if title else favorites_folder._pretty(stem)
    eid = _epi_id(path)
    if eid:
        return eid, "epidemic", _epi_name(os.path.basename(path))
    if jd and _under(path, jd):
        rel = os.path.relpath(os.path.realpath(path), os.path.realpath(jd)).replace(os.sep, "/")
        return f"job:{rel}", "hers", favorites_folder._pretty(os.path.splitext(os.path.basename(path))[0])
    pal = capcut_sfx.palette()
    real = os.path.realpath(path)
    keys = [k for k, v in pal.items() if os.path.realpath(v) == real]
    if keys:
        stem = os.path.splitext(os.path.basename(path))[0]
        k = stem if stem in keys else sorted(keys)[0]
        return f"lib:{k}", "library", _lib_name(k)
    if _under(path, os.path.join(ROOT, "projects")):          # another reel's sound (a reused pull)
        return f"file:{_rel(path)}", "hers", favorites_folder._pretty(os.path.splitext(os.path.basename(path))[0])
    if _under(path, ROOT):
        return f"file:{_rel(path)}", "library", favorites_folder._pretty(os.path.splitext(os.path.basename(path))[0])
    return None, "hers", favorites_folder._pretty(os.path.splitext(os.path.basename(path))[0])


def _clean_title(t):
    t = re.sub(r"\(\d+\)", "", str(t or "")).strip()
    return os.path.splitext(t)[0] if t.lower().endswith(AUDIO_EXT) else t


def _lib_name(key):
    """A short name for a library sound: its index description up to the first pause ("A bell ring: a message or a
    small win." -> "A bell ring"), else its file name."""
    d = (_index().get(key) or {}).get("description")
    if not d:
        return favorites_folder._pretty(key)
    short = re.split(r":\s| — | – | - |\.\s|\.$|;\s|, only| \(", _clean_title(d).strip())[0].strip()
    return (short or _clean_title(d))[:48]


def _lib_about(key):
    return _clean_title((_index().get(key) or {}).get("description") or "") or None


# ── Epidemic Sound files already on her computer (never a network call) ──────────────────────────────────
_EPI_PROJECT = re.compile(r"^[^/]+/(?:sfx|audio)/epidemic[^/]*/", re.I)


def _epi_id(path):
    """'epi:home/<rel>' for a file in the Epidemic Sound app's folder, 'epi:projects/<rel>' for one in a reel's
    epidemic download folder, else None."""
    if not path:
        return None
    real = os.path.realpath(path)
    for prefix, root in (("home", EPIDEMIC_HOME), ("projects", PROJECTS_DIR)):
        r = os.path.realpath(root)
        if real.startswith(r + os.sep):
            rel = os.path.relpath(real, r).replace(os.sep, "/")
            if prefix == "home" or _EPI_PROJECT.match(rel):
                return f"epi:{prefix}/{rel}"
    return None


def _epi_name(fn):
    """'ES_204275_Swooshes, Whoosh, Mids_segment_0.07_0.64.mp3' -> 'Swooshes, Whoosh, Mids (trimmed)'."""
    s = os.path.splitext(fn)[0]
    s = re.sub(r"^ES_\d+_", "", s)
    s, cut = re.subn(r"_segment_[\d.]+_[\d.]+$", "", s)
    s = favorites_folder._pretty(s) if "_" in s or "-" in s and " " not in s else s
    return s + (" (trimmed)" if cut else "")


def _dataless(path):
    """macOS: a file iCloud has offloaded (its bytes are not on this computer; opening it would fetch them)."""
    try:
        return bool(getattr(os.stat(path), "st_flags", 0) & 0x40000000)     # SF_DATALESS
    except OSError:
        return True


def epidemic_dirs():
    """Every folder her Epidemic downloads live in: the app's folder, then each reel's epidemic folder(s)."""
    out = [EPIDEMIC_HOME] if os.path.isdir(EPIDEMIC_HOME) else []
    try:
        reels = sorted(os.listdir(PROJECTS_DIR))
    except OSError:
        reels = []
    for n in reels:
        if n.startswith("."):
            continue
        for sub in ("sfx", "audio"):
            d = os.path.join(PROJECTS_DIR, n, sub)
            try:
                kids = sorted(os.listdir(d))
            except OSError:
                continue
            out += [os.path.join(d, k) for k in kids
                    if k.lower().startswith("epidemic") and os.path.isdir(os.path.join(d, k))]
    return out


def _epidemic_files():
    """[(id, absolute path, name)] for every Epidemic file on disk (the app's Voiceover folder is not a sound)."""
    rows, seen = [], set()
    for d in epidemic_dirs():
        for dp, dirs, files in os.walk(d):
            dirs[:] = sorted(x for x in dirs if not x.startswith(".") and x.lower() not in ("voiceover", "voiceovers"))
            for fn in sorted(files):
                if fn.startswith(".") or not fn.lower().endswith(AUDIO_EXT):
                    continue
                p = os.path.join(dp, fn)
                if _dataless(p):
                    continue                   # an iCloud placeholder: reading it would download it. Local only.
                cid = _epi_id(p)
                if cid and cid not in seen:
                    seen.add(cid)
                    rows.append((cid, p, _epi_name(fn)))
    return rows


# ── moments: every look that moves, timed to its motion ──────────────────────────────────────────────────
_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S | re.I)
_TL_NAME = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*(?:window\s*\.\s*)?gsap\s*\.\s*timeline\s*\(")
_ALPHA = ("autoAlpha", "opacity")
_MOVE = ("scale", "scaleX", "scaleY", "x", "y", "xPercent", "yPercent", "rotation", "clipPath", "webkitClipPath",
         "filter", "strokeDashoffset", "width", "height", "top", "left")


def _split(s):
    """Top-level comma split of a JS argument / object body, respecting quotes and brackets."""
    out, depth, start, q, i = [], 0, 0, None, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'`":
            q = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            out.append(s[start:i].strip())
            start = i + 1
        i += 1
    tail = s[start:].strip()
    if tail:
        out.append(tail)
    return out


def _close(s, i):
    """s[i] is an opening bracket: the index of its match (quotes respected), or -1."""
    depth, q, j = 0, None, i
    while j < len(s):
        c = s[j]
        if q:
            if c == "\\":
                j += 2
                continue
            if c == q:
                q = None
        elif c in "\"'`":
            q = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _obj(raw):
    """A JS object literal -> {key: raw value text} (one level), or None when it isn't one."""
    raw = (raw or "").strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        return None
    out = {}
    for part in _split(raw[1:-1]):
        m = re.match(r"""\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z_$][\w$]*))\s*:(.*)$""", part, re.S)
        if m:
            out[m.group(1) or m.group(2) or m.group(3)] = m.group(4).strip()
    return out


def _num(v):
    if v is None:
        return None
    s = str(v).strip().strip("\"'`")
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _unq(raw):
    raw = (raw or "").strip()
    return raw[1:-1] if len(raw) >= 2 and raw[0] in "\"'`" and raw[-1] == raw[0] else None


_DECL = re.compile(r"\b(?:const|let|var)\s+([^;\n]+)")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?")


def _constants(scripts):
    """Numbers a page names once and times its tweens by: `const D=3.2`, `const T={put:0.09,end:7.5}`."""
    out = {}
    for m in _DECL.finditer(scripts):
        for part in _split(m.group(1)):
            mm = re.match(r"([A-Za-z_$][\w$]*)\s*=\s*(.+)$", part.strip(), re.S)
            if not mm:
                continue
            name, val = mm.group(1), mm.group(2).strip()
            v = _num(val)
            if v is not None:
                out[name] = v
                continue
            o = _obj(val)
            if o:
                for k, raw in o.items():
                    x = _num(raw)
                    if x is not None:
                        out[f"{name}.{k}"] = x
    return out


def _arith(expr, consts):
    """A plain arithmetic expression over numbers and named constants (`T.put+.2`, `D-0.35`) -> seconds, or None.
    Evaluated through Python's own parser restricted to + - * / and brackets: nothing else can run."""
    import ast
    if not expr or len(expr) > 120:
        return None
    miss = []

    def sub(m):
        if m.group(0) in consts:
            return repr(consts[m.group(0)])
        miss.append(m.group(0))
        return "0"
    e = _IDENT.sub(sub, expr)
    if miss or not re.fullmatch(r"[\d.\s+\-*/()eE]+", e):
        return None
    try:
        tree = ast.parse(e.strip(), mode="eval")
    except SyntaxError:
        return None
    ok = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)
    if not all(isinstance(n, ok) for n in ast.walk(tree)):
        return None
    try:
        v = float(eval(compile(tree, "<pos>", "eval"), {"__builtins__": {}}, {}))
    except Exception:
        return None
    return v if math.isfinite(v) else None


def _position(raw, end, prev, consts=None):
    """A GSAP position parameter -> seconds on the timeline, or None for one that can't be read (a label, an
    expression). Omitted = the timeline's end, '+=x'/'-=x' from the end, '<' / '>' the previous tween's start /
    end, '<0.2' and '<+=0.2' from there."""
    if raw is None or raw == "":
        return end
    v = _num(raw)
    if v is None and consts is not None and _unq(raw) is None:
        v = _arith(raw, consts)
    if v is not None:
        return v
    s = _unq(raw)
    if s is None:
        return None
    m = re.fullmatch(r"\s*([<>])?\s*(?:([+-])=)?\s*(-?\d*\.?\d+)?\s*", s)
    if not m or (not m.group(1) and not m.group(2)):
        return None
    base = (prev[0] if m.group(1) == "<" else prev[1]) if m.group(1) else end
    amt = float(m.group(3)) if m.group(3) else 0.0
    return base - amt if m.group(2) == "-" else base + amt


def _alpha(d):
    if not d:
        return None
    for k in _ALPHA:
        if k in d:
            return _num(d[k])
    return None


def _open_back(s, j):
    """s[j] is a closing bracket: the index of its opening match, scanning backwards (strings are rare here)."""
    depth = 0
    while j >= 0:
        c = s[j]
        if c in ")]}":
            depth += 1
        elif c in "([{":
            depth -= 1
            if depth == 0:
                return j
        j -= 1
    return -1


_FOR = re.compile(r"\bfor\s*\(\s*(?:let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(-?\d+)\s*;\s*\1\s*(<=?)\s*(\d+)\s*;\s*"
                  r"(?:\1\s*\+\+|\+\+\s*\1|\1\s*\+=\s*1)\s*\)")


def _loop_binds(scripts, at):
    """A tween inside a loop: the names the loop sets on each pass, so every pass is read as its own tween, timed
    by its own values. Reads `[[sel, t], ...].forEach(([s, t]) => ...)`, `[0.2, 0.5].forEach(t => ...)`,
    `[0,1,2,3].forEach(i => tl.fromTo(..., T0 + i*0.45))`, `sels.forEach((s, i) => ...)` with a literal array, and
    `for (let i = 0; i < 4; i++) { ... }`. [{name: number}] per pass, [] when it isn't one of those shapes."""
    fe = scripts.rfind(".forEach(", 0, at)
    if fe >= 0 and _close(scripts, fe + len(".forEach")) > at:
        head = scripts[fe + len(".forEach("):at]
        m = re.match(r"\s*(?:function\s*)?\(?\s*(?:\[([^\]]*)\]|([A-Za-z_$][\w$]*))\s*(?:,\s*([A-Za-z_$][\w$]*)\s*)?\)?\s*(?:=>|\{)", head)
        k = fe - 1
        while k >= 0 and scripts[k].isspace():
            k -= 1
        o = _open_back(scripts, k) if m and k >= 0 and scripts[k] == "]" else -1
        if o >= 0:
            names = [n.strip() for n in m.group(1).split(",")] if m.group(1) is not None else [m.group(2)]
            out = []
            for n, el in enumerate(_split(scripts[o + 1:k])):
                el = el.strip()
                vals = (_split(el[1:-1]) if el.startswith("[") and el.endswith("]") else []) if m.group(1) is not None else [el]
                b = {nm: v for nm, v in ((nm, _num(vals[j]) if j < len(vals) else None) for j, nm in enumerate(names))
                     if nm and v is not None}
                if m.group(3):
                    b[m.group(3)] = float(n)                 # the index: (s, i) => ...
                out.append(b)
            return out
    for m in _FOR.finditer(scripts, 0, at):                 # the nearest for-loop whose body holds the tween
        br = scripts.find("{", m.end(), at)
        if br < 0 or scripts[m.end():br].strip() or _close(scripts, br) < at:
            continue
        a, z = int(m.group(2)), int(m.group(4)) + (1 if m.group(3) == "<=" else 0)
        if 0 <= z - a <= 64:
            return [{m.group(1): float(v)} for v in range(a, z)]
    return []



_TEXT_WRITE = re.compile(r"\.(?:textContent|innerText|innerHTML)\s*=")


def _written_out(scripts, obj):
    """Does the page write this plain object's value out as text (a count-up's number)?"""
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", obj.strip()):
        return False
    ref = re.compile(r"\b" + re.escape(obj.strip()) + r"\s*\.\s*[A-Za-z_$]")
    for st in re.split(r"[;\n]", scripts):
        if ref.search(st) and _TEXT_WRITE.search(st):
            return True
    return False


def _writes_text(scripts, cb):
    """Does this callback (inline, or a function the page names) write text?"""
    cb = (cb or "").strip()
    if re.fullmatch(r"[A-Za-z_$][\w$]*", cb):
        m = re.search(r"(?:function\s+" + re.escape(cb) + r"\s*\([^)]*\)\s*|\b" + re.escape(cb)
                      + r"\s*=\s*(?:function\s*)?\([^)]*\)\s*(?:=>\s*)?)\{", scripts)
        cb = scripts[m.end() - 1:_close(scripts, m.end() - 1) + 1] if m else ""
    return _TEXT_WRITE.search(cb) is not None


def timeline_tweens(html):
    """The tweens a composition's own timeline script adds, in order: [{"method", "sel", "from", "vars", "pos",
    "dur", "count"}] (pos None = a position that can't be read). Reads every inline <script>."""
    scripts = "\n".join(_SCRIPT.findall(html or ""))
    consts = _constants(scripts)
    names = set(_TL_NAME.findall(scripts)) | {"tl"}
    call = re.compile(r"(?:\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")|\))\s*\.\s*(fromTo|from|to|set)\s*\(")
    out, end, prev, i = [], 0.0, (0.0, 0.0), 0
    while True:
        m = call.search(scripts, i)
        if not m:
            break
        op = m.end() - 1
        cl = _close(scripts, op)
        if cl < 0:
            break
        i = op + 1                     # keep scanning INSIDE too: a chained or nested call is its own tween
        args = _split(scripts[op + 1:cl])
        meth = m.group(1)
        if meth == "fromTo":
            if len(args) < 3:
                continue
            frm, vars_, praw = _obj(args[1]), _obj(args[2]), (args[3] if len(args) > 3 else None)
        else:
            if len(args) < 2:
                continue
            frm, vars_, praw = None, _obj(args[1]), (args[2] if len(args) > 2 else None)
        if vars_ is None:
            continue
        if meth == "set" and not vars_:
            continue                   # tl.set({},{},D): the kill that pins the length, not a tween
        dur = 0.0 if meth == "set" else _num(vars_.get("duration"))
        if dur is None and meth != "set" and vars_.get("duration"):
            dur = _arith(vars_["duration"], consts)
        if dur is None or dur < 0:
            dur = 0.5                  # GSAP's own default
        sel = args[0]
        # a count-up tweens a plain number (an object, not an element) and writes it out as text: in its own
        # onUpdate, or wherever the page writes that object's value. (An orbit's angle or a ring's spin is a plain
        # object too, but nothing writes it out as text: that is motion, not counting.)
        count = meth in ("to", "fromTo") and (_writes_text(scripts, vars_.get("onUpdate", "")) or (
            _unq(sel) is None and not any(k in vars_ for k in _ALPHA + _MOVE) and _written_out(scripts, sel)))
        binds = _loop_binds(scripts, m.start()) if praw else []
        if any(re.search(r"(?<![\w$.])" + re.escape(n) + r"(?![\w$])", praw) for b in binds for n in b):
            # timed by its loop (`T0 + i*0.45`): every pass is its own tween, at its own time
            passes = [_position(praw, end, prev, dict(consts, **b)) for b in binds]
        else:
            passes = [_position(praw, end, prev, consts)]
        for p in passes:
            out.append({"method": meth, "sel": _unq(sel) or sel, "from": frm, "vars": vars_, "pos": p, "dur": dur,
                        "stagger": _num(vars_.get("stagger")), "count": bool(count)})
            if p is not None:
                prev = (p, p + dur)
                end = max(end, p + dur)
    return out


def _raises(tw):
    """Does this tween make something visible?"""
    if tw["method"] == "fromTo":
        a0, a1 = _alpha(tw["from"]), _alpha(tw["vars"])
        return a1 is not None and a1 > 0.05 and a0 is not None and a0 <= 0.05
    if tw["method"] == "from":
        a = _alpha(tw["vars"])
        return a is not None and a <= 0.05
    a = _alpha(tw["vars"])                                   # to / set
    return a is not None and a > 0.05


def _moves_in(tw):
    """Does this tween move something into place (a from / fromTo with a starting transform)?"""
    src = tw["from"] if tw["method"] == "fromTo" else tw["vars"] if tw["method"] == "from" else None
    return bool(src) and any(k in src for k in _MOVE)


def _from_state(tweens, tw):
    """How the entering thing starts: its own from-vars, the sets on the same target before it, and a fromTo on the
    same target starting at the same moment (a card that fades in while it settles from a bigger scale)."""
    st = {}
    for o in tweens:
        if o is tw:
            break
        if o["method"] == "set" and o["sel"] == tw["sel"]:
            st.update(o["vars"])
    for o in tweens:
        if o is not tw and o["sel"] == tw["sel"] and o["method"] == "fromTo" and o["pos"] == tw["pos"]:
            st.update(o["from"] or {})
    if tw["method"] == "fromTo":
        st.update(tw["from"] or {})
    elif tw["method"] == "from":
        st.update(tw["vars"])
    return st


def _effect(st):
    """The kind of entrance from how it starts."""
    flt = str(st.get("filter", "")).lower()
    if "blur" in flt:
        return "blur"
    sc = _num(st.get("scale"))
    if sc is not None and (sc <= 0.85 or sc >= 1.25):
        return "pop"
    for k, big in (("x", 30), ("xPercent", 10)):
        v = _num(st.get(k))
        if v is not None and abs(v) >= big:
            return "slide"
    for k, big, small in (("y", 60, 3), ("yPercent", 20, 2)):
        v = _num(st.get(k))
        if v is not None and abs(v) >= big:
            return "slide"
        if v is not None and abs(v) >= small:
            return "rise"
    if any(k in st for k in ("clipPath", "webkitClipPath", "strokeDashoffset", "scaleX", "scaleY", "width", "height")):
        return "reveal"
    if sc is not None and abs(sc - 1) > 0.01:
        return "pop"
    if _alpha(st) is not None:
        return "reveal"
    return "other"


def _look_key(layer):
    return " ".join(str(layer.get(k) or "") for k in ("look", "look_name", "name", "id")).lower()


def _comp_html(jd, layer):
    """The look's composition page, or None."""
    for rel in (layer.get("dir"), f"hf-graphics/{layer.get('name')}" if layer.get("name") else None):
        if not rel:
            continue
        p = rel if os.path.isabs(rel) else os.path.join(jd, rel)
        if os.path.isdir(p):
            p = os.path.join(p, "index.html")
        if os.path.isfile(p) and p.lower().endswith((".html", ".htm")):
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            except OSError:
                return None
    return None


_AUDIO_TAG = re.compile(r"<audio\b[^>]*>", re.I)


def _attr(tag, name):
    m = re.search(r'\b' + re.escape(name) + r'\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', tag)
    return (m.group(1) if m.group(1) is not None else m.group(2)) if m else None


def _comp_dir(jd, layer):
    for rel in (layer.get("dir"), f"hf-graphics/{layer.get('name')}" if layer.get("name") else None):
        if rel:
            p = rel if os.path.isabs(rel) else os.path.join(jd, rel)
            if os.path.isfile(os.path.join(p, "index.html")):
                return p
    return None


def look_sounds(jd, layers=None):
    """A look's OWN sound: every <audio> its page carries (a design or a Sandbox sketch can make its sound part of the
    effect: an echo, a stinger, a jingle). [{"id": "own:<layer>:<n>", "layer", "look_name", "file" (absolute), "at"
    (cut seconds: the look's offset + the audio's data-start), "trim" (its data-duration, held inside the look),
    "volume" (data-volume, 1 = as made)}]. HyperFrames renders a look without its sound, so the builds lay these in
    (for_build); her page plays them with the look; her Sound tab lists them so she can switch one off."""
    out = []
    for L in (layers if layers is not None else _looks(jd)):
        d = _comp_dir(jd, L)
        if not d:
            continue
        try:
            html = open(os.path.join(d, "index.html"), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        off, ldur = float(L.get("offset") or 0), _num(L.get("dur"))
        for k, tag in enumerate(_AUDIO_TAG.findall(html)):
            src = _attr(tag, "src")
            if not src or re.match(r"^[a-z]+:", src, re.I):
                continue                                     # never a web address: the engine works offline
            f = os.path.normpath(os.path.join(d, src))
            if not os.path.isfile(f) or not f.lower().endswith(AUDIO_EXT + (".mp4", ".mov", ".m4v")):
                continue
            st = max(0.0, _num(_attr(tag, "data-start")) or 0.0)
            du = _num(_attr(tag, "data-duration"))
            if ldur is not None:
                du = min(du, max(0.0, ldur - st)) if du is not None else max(0.0, ldur - st)
            vol = _num(_attr(tag, "data-volume"))
            out.append({"id": f"own:{L.get('name')}:{k}", "layer": L.get("name"), "look_name": L.get("look_name") or L.get("look") or L.get("name"),
                        "file": f, "at": round(off + st, 3), "trim": round(du, 3) if du else None,
                        "volume": 1.0 if vol is None else max(0.0, min(vol, 4.0))})
    return out


def _own_gain(f, prog, trim, sd, volume):
    """A look's own sound at the level the engine gives every sound against her voice (audio_levels, the north star),
    then its own data-volume on top."""
    g = auto_sfx_gain(f, prog, trim, sd) if prog else 0.0
    return round((g or 0.0) + (20 * math.log10(volume) if volume and volume > 0 else -60.0), 1)


def entrance(html, layer=None):
    """(entrance seconds inside the composition, motion seconds, kind, money) from its timeline, or
    (None, None, kind, False) when no entrance tween can be read."""
    layer = layer or {}
    tw = timeline_tweens(html) if html else []
    vis = [t for t in tw if t["pos"] is not None and _raises(t)]
    mov = [t for t in tw if t["pos"] is not None and _moves_in(t)]
    pick = None
    if vis:
        first = min(t["pos"] for t in vis)
        tied = [t for t in vis if abs(t["pos"] - first) < 1e-6]
        pick = max(tied, key=lambda t: (t["method"] != "set", -t["dur"]))     # a real tween over an instant set
    elif mov:
        first = min(t["pos"] for t in mov)
        pick = next(t for t in mov if abs(t["pos"] - first) < 1e-6)
    key = _look_key(layer)
    writes_text = bool(re.search(r"\.(?:textContent|innerText|innerHTML)\s*=", html or ""))
    counts = [t for t in tw if t["count"] and t["pos"] is not None] if writes_text else []   # a number written out
    money = bool(re.search(r"""["'`]\$["'`]|\$\s*["'`]\s*\+""", html or "")) or "money" in key
    if re.search(r"count|counter|tally", key) or counts:
        kind = "count"
    elif re.search(r"typewriter|type-?on|typing|typer|write-?on|scribble", key):
        kind = "type"
    elif "hook" not in key and re.search(r"breakaway|takeover|card|\bstat\b", key):
        kind = "card"
    elif pick is not None:
        kind = _effect(_from_state(tw, pick))
        if kind == "other":
            kind = next((k for k in ("slide", "pop", "blur", "reveal", "rise") if k in key), "other")
    else:
        kind = next((k for k in ("slide", "pop", "blur", "reveal", "rise") if k in key), "other")
    if pick is None:
        return None, None, kind, money
    start, motion = pick["pos"], pick["dur"]
    if kind == "count" and counts:                 # the tick voices the counting: to the end of it
        motion = max(motion, max(t["pos"] + t["dur"] for t in counts) - start)
    elif kind == "type":                           # the type-on runs to its last letter
        last = max((t["pos"] + t["dur"] for t in vis), default=start + motion)
        motion = max(motion, last - start)
    return round(max(0.0, start), 3), round(max(0.0, motion), 3), kind, money


# looks that show HER WORDS as she says them: their lines and letters are one motion (the voice is the sound)
_WORD_LOOK = re.compile(r"hook|eyebrow|headline|takeover|caption|karaoke|single-word|phrase|spotlight|typewriter|type-?on")


def _targets(html, sel):
    """How many elements a plain `.class` selector names in the page (a stagger runs once per element); 1 otherwise."""
    m = re.fullmatch(r"\.([A-Za-z_][\w-]*)", str(sel or "").strip())
    if not m:
        return 1
    n = sum(1 for c in re.findall(r"""\bclass\s*=\s*["']([^"']*)["']""", html or "") if m.group(1) in c.split())
    return max(1, min(n, MAX_PARTS))


def entrances(html, layer=None):
    """Every separate thing a look brings in, each its own motion: [(seconds inside the composition, motion seconds,
    kind, money)]. Four cards popping in at four moments are four entrances (each gets its own sound); things
    coming in closer than PART_GAP_S apart are one burst, one entrance. A look that shows her words as she says
    them (a hook, a takeover, captions, a type-on) and a count-up stay ONE entrance. The first is always
    entrance(): [(None, None, kind, False)] when nothing can be read."""
    first = entrance(html, layer)
    start, motion, kind, money = first
    if start is None or kind in ("type", "count") or _WORD_LOOK.search(_look_key(layer or {})):
        return [first]
    tw = timeline_tweens(html)
    ins = []
    for t in tw:
        if t["pos"] is None or not _raises(t):
            continue
        n = _targets(html, t["sel"]) if (t.get("stagger") or 0) > 0 else 1
        ins += [(t["pos"] + k * t["stagger"], t) for k in range(n)] if n > 1 else [(t["pos"], t)]
    ins.sort(key=lambda x: (x[0], x[1]["method"] == "set", -x[1]["dur"]))
    parts, last = [], None
    for p, t in ins:
        if last is None or p - last >= PART_GAP_S - 1e-6:
            parts.append((p, t))
        last = p
    if len(parts) < 2:
        return [first]
    out = []
    for i, (p, t) in enumerate(parts[:MAX_PARTS]):
        k = _effect(_from_state(tw, t))
        mot = motion if i == 0 else (t["dur"] or DEFAULT_MOTION_S)
        out.append((round(max(0.0, p), 3), round(max(0.0, mot), 3), kind if k == "other" else k, money))
    return out


def _all_looks(jd):
    """The looks that can carry a sound: every layer but the reel-wide captions and the ones she switched off."""
    d = _json(os.path.join(jd, "review", "looks.json"), {}) or {}
    return [l for l in d.get("layers", []) or [] if isinstance(l, dict) and l.get("name") and not l.get("captions")
            and not l.get("off") and not str(l.get("name", "")).startswith(("hf-reel-type", "captions", "hf-captions"))]


def moments(job):
    """Every look on the reel that moves, timed to its motion, in cut order:
    [{"layer", "t" (cut seconds of the entrance), "motion_s", "kind", "look_name", "timing": "motion"|"start",
      "offset", "entrance" (seconds inside the look), "money", "look_layer", "part", "parts", "with"?}].
    A look that brings in several things at separate moments (entrances()) is one moment per thing: the first keyed
    by its layer as always, the rest "<layer>#2", "<layer>#3" ... ("look_layer" is the look itself). Two looks
    bringing something in on the same frame (SAME_FRAME_S) are one motion: the later folds into the first ("with")."""
    jd = job_dir(job)
    out = []
    vo = os.path.isfile(os.path.join(jd, "voiceover.json"))   # a voiceover's clips ARE its picture: a cut from one to the
    for l in _all_looks(jd):                                  # next is an edit, not a motion, so no sound of its own
        if vo and l.get("cutaway"):
            continue
        off = _num(l.get("offset")) or 0.0
        dur = _num(l.get("dur"))
        parts = entrances(_comp_html(jd, l), l)
        if len(parts) > 1 and dur is not None:      # an entrance past the look's own end isn't one we can trust
            parts = [x for x in parts if x[0] <= dur] or parts[:1]
        for n, (ent, mot, kind, money) in enumerate(parts, 1):
            if ent is not None and dur is not None and ent > dur:
                ent = None
            row = {"layer": l["name"] if n == 1 else f"{l['name']}#{n}", "look_layer": l["name"],
                   "part": n, "parts": len(parts), "kind": kind,
                   "look_name": l.get("look_name") or favorites_folder._pretty(l["name"]), "offset": round(off, 3), "money": money}
            if ent is None:
                row.update(t=round(off, 3), motion_s=DEFAULT_MOTION_S, timing="start", entrance=None)
            else:
                row.update(t=round(off + ent, 3), motion_s=mot, timing="motion", entrance=ent)
            out.append(row)
    out.sort(key=lambda r: (r["t"], r["layer"]))
    kept = []                                        # two looks bringing something in on the same frame (a sketch's
    for r in out:                                    # in-front and behind halves) are ONE motion to the viewer: one sound
        same = next((k for k in kept if k["look_layer"] != r["look_layer"] and r["timing"] == "motion" == k["timing"]
                     and abs(k["t"] - r["t"]) <= SAME_FRAME_S), None)
        if same:
            same.setdefault("with", []).append(r["layer"])
        else:
            kept.append(r)
    return kept


def _trim_for(kind, motion_s, dur=None, path=None):
    """How long a moment's sound plays: the motion's length (a one-off hit never under MIN_HIT_S; a type-on or a
    count-up exactly the motion), never past the sound itself. With the file (`path`), a sound that has barely
    started by then (a riser, a slow swell, a whoosh with a soft lead-in: its first stretch far under its own peak)
    plays through its loudest moment instead, since cut to the motion it would be silence."""
    m = DEFAULT_MOTION_S if motion_s is None else float(motion_s)
    t = max(m, 0.1 if kind in CONTINUOUS else MIN_HIT_S)
    if dur:
        t = min(t, float(dur))
    t = round(t, 3)
    if path and (not dur or t < float(dur)):
        head, whole = _measure(path, "peak", t), _measure(path, "peak")
        if head is not None and whole is not None and head < whole - QUIET_HEAD_DB:
            at = _measure(path, "peak_at")
            if at is None:
                return None
            t = round(at + LATE_PEAK_TAIL_S, 3)
            return None if dur and t >= float(dur) else t
    return t


# ── defaults that follow the motion ───────────────────────────────────────────────────────────────────────
# Per kind: the words that name a fitting sound (matched on her files' names, the shelf's titles and the library
# index's descriptions), the library's preferred shipped sounds in order, and the index jobs that also fit.
KIND_SOUNDS = {
    "pop":    {"words": ["pop", "plop", "plink", "bubble", "bloop", "boop", "pyui", "blip"],
               "lib": ["comedic-pop", "pop-1", "plop-2", "plink", "studio-open"], "jobs": ["reveal"]},
    "slide":  {"words": ["whoosh", "woosh", "swoosh", "swish", "swipe", "flyby", "fly by", "wind noise", "airy"],
               "lib": ["quick-wind"], "jobs": ["transition"]},
    "rise":   {"words": ["swish", "airy", "soft whoosh", "swoosh", "open", "rise up"],
               "lib": ["studio-open", "quick-wind", "soulful-click"], "jobs": ["reveal"]},
    "blur":   {"words": ["swish", "swoosh", "whoosh", "woosh", "airy", "shimmer"],
               "lib": ["quick-wind", "studio-open"], "jobs": ["transition", "reveal"]},
    "reveal": {"words": ["swish", "reveal", "telop", "appear", "open", "swoosh", "plink"],
               "lib": ["studio-open", "plink", "comedic-pop"], "jobs": ["reveal"]},
    "card":   {"words": ["thud", "thump", "slap", "hit", "impact", "punch", "slam", "stomp", "snap"],
               "lib": ["thud", "hit-1", "studio-snap", "hit-tap-2", "hit-2", "snap"], "jobs": ["emphasis"]},
    "count":  {"words": ["tick", "ticking", "ratchet", "counter", "clock", "click"],
               "lib": ["studio-tap", "click-1", "tap-1", "click-decision"], "jobs": ["click"]},
    "type":   {"words": ["typing", "typewriter", "keyboard", "writing", "pencil", "marker", "key press"],
               "lib": ["key-press", "studio-tap"], "jobs": ["typing"]},
    "other":  {"words": ["pop", "click", "tap", "swish"],
               "lib": ["studio-open", "click-1"], "jobs": ["reveal", "click"]},
}
MONEY_WORDS = ["coin", "coins", "cash", "ka-ching", "ka ching", "cha-ching", "cha ching", "register", "money"]
MONEY_LIB = ["coin-drops", "coin-in-cup"]
_MUDDY = re.compile(r"\b(low|bass|dark|deep|boom|sub|distorted)\b")


def _words_re(words):
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")(?:e?s)?\b")


def _text(*parts):
    return re.sub(r"[_\-]+", " ", " ".join(str(p or "") for p in parts)).lower()


def _shipped(path):
    """A library file that ships with the engine (never the sounds collected from CapCut's own library)."""
    return _under(path, os.path.join(capcut_sfx.SFX_DIR, "cc0")) or _under(path, capcut_sfx._HF_SFX)


def _pools():
    """The four sources a default draws from, in order, each [(id, file, name, text, meta)]."""
    fav = [(e["id"], e["file"], e["name"], _text(e["name"], os.path.basename(e["file"])), {"duration": e.get("duration")})
           for e in favorites_folder.sounds(use="sfx")]
    cap = [(f"fav:{os.path.splitext(os.path.basename(s['file']))[0]}", s["file"],
            _clean_title(s.get("title")) or s.get("name"), _text(_clean_title(s.get("title")), s.get("name")),
            {"duration": s.get("seconds")}) for s in _shelf() if os.path.isfile(s["file"])]
    epi = [(cid, p, name, _text(name), {}) for cid, p, name in _epidemic_files()]
    pal_all, pal, ix = capcut_sfx.palette(), capcut_sfx.selectable(), _index()
    lib, seen = [], set()
    for k in sorted(pal):
        p = pal[k]
        real = os.path.realpath(p)
        stem = os.path.splitext(os.path.basename(p))[0]
        if real in seen or not _shipped(p) or (stem != k and stem in pal_all):
            continue                                    # an alias: the canonical name (or its switch) decides
        meta = ix.get(k) or {}
        if meta.get("enabled") is False or meta.get("keep_off"):
            continue
        seen.add(real)
        lib.append((f"lib:{k}", p, _lib_name(k), _text(k, meta.get("description")), dict(meta, key=k)))
    lib.sort(key=lambda r: (0 if _under(r[1], os.path.join(capcut_sfx.SFX_DIR, "cc0")) else 1, r[0]))
    return [("favorite", fav), ("capcut", cap), ("epidemic", epi), ("library", lib)]


def _fits(pools, kind, money=False):
    """[(source, ranked [(id, file, name, duration)])] for a moment's kind, every source that has a fit, in the
    sources' order."""
    spec = KIND_SOUNDS.get(kind) or KIND_SOUNDS["other"]
    words = spec["words"] + (MONEY_WORDS if money and kind == "count" else [])
    rx = _words_re(words)
    money_rx = _words_re(MONEY_WORDS)
    found = []
    for source, pool in pools:
        ranked = []
        if source == "library":
            pref = (MONEY_LIB if money and kind == "count" else []) + spec["lib"]
            by_key = {r[4].get("key"): r for r in pool}
            ranked = [by_key[k] for k in pref if k in by_key]
            for r in pool:
                m = r[4]
                if r in ranked or m.get("mood") == "somber" or (m.get("tactile") and kind != "type"):
                    continue
                if m.get("job") in spec["jobs"] and (rx.search(r[3]) or m.get("job") in spec["jobs"][:1]):
                    ranked.append(r)
        else:
            ranked = [r for r in pool if rx.search(r[3])]
            ranked.sort(key=lambda r: (0 if (money and money_rx.search(r[3])) else 1, 1 if _MUDDY.search(r[3]) else 0))
        out = []
        for cid, f, name, _t, meta in ranked:
            d = meta.get("duration")
            if d is None:
                d = _measure(f, "duration")
            if d is not None and 0 < d <= SFX_MAX_S:
                out.append((cid, f, name, d))
        if out:
            found.append((source, out))
    return found


def _same_sound(p):
    """One key per sound: a file and the trimmed segments made from it ("<name>_segment_0.08...") count as the same."""
    return re.sub(r"_segment_[\d.]+$", "", os.path.splitext(os.path.basename(os.path.realpath(p)))[0]).lower()


def _pick(pools, m, used, prev_real, cache):
    """The default for one moment: the least-used fit in the first source that has one, never the sound just
    before it. Returns {"choice", "name", "file" (absolute), "source", "trim", "duration"} or None."""
    key = (m["kind"], bool(m.get("money")))
    if key not in cache:
        cache[key] = _fits(pools, m["kind"], m.get("money"))
    found = cache[key]
    if not found:
        return None
    # the first source with a fit that isn't the sound just before; only when every fit everywhere IS that sound
    # does it repeat (rule: never the same sound twice in a row)
    pk = _same_sound(prev_real) if prev_real else None      # a trimmed segment of a sound IS that sound
    source, fits = next(((s, [f for f in fs if _same_sound(f[1]) != pk]) for s, fs in found
                         if any(_same_sound(f[1]) != pk for f in fs)), found[0])
    order = {f[0]: i for i, f in enumerate(fits)}
    uses = lambda f: sum(n for k, n in used.items() if _same_sound(k) == _same_sound(f[1]))
    choice = sorted(fits, key=lambda f: (uses(f), order[f[0]]))[0]
    cid, f, name, d = choice
    return {"choice": cid, "name": name, "file": f, "source": source, "duration": d,
            "trim": _trim_for(m["kind"], m["motion_s"], d, f)}


def _register(jd, register=None):
    """(register, mood) for this reel: the one passed in, else the one recorded for it (product/choices.py), and
    the mood its plans name. Never guessed here."""
    if register is not None and register not in ("teaching", "confessional"):
        raise Refuse(f"{register!r} isn't a register. It's 'teaching' or 'confessional'.")
    if register is None:
        try:
            import choices as _choices
            register = _choices.read(jd).get("register")
        except Exception:
            register = None
    mood = None
    for rel in ("caption-plan.json", "graphics-plan.json", os.path.join("review", "choices.json")):
        d = _json(os.path.join(jd, rel), {}) or {}
        if isinstance(d, dict) and isinstance(d.get("mood"), str):
            mood = d["mood"].strip().lower()
    return register, mood


def _quiet(register, mood):
    if register == "confessional":
        return "This reel is confessional, so it stays near-silent: no sound is added for you. Add one where you want it."
    if mood == "somber":
        return "This reel is somber, so it gets no sound unless you add one."
    return None


def defaults_for(job, register=None):
    """The sound each moment would get by default, following its motion, from her sources first (each look on its
    own: the sounds already on the reel are not counted here; apply_defaults counts them).
    {"register", "quiet": bool, "reason": plain words or None, "moments": [moment + "default": {"choice", "name",
    "file" (engine-relative or absolute), "source", "trim"} | None]}. Confessional / somber: every default is None."""
    jd = job_dir(job)
    reg, mood = _register(jd, register)
    why = _quiet(reg, mood)
    ms = moments(jd)
    out = {"register": reg, "quiet": bool(why), "reason": why, "moments": []}
    pools = None if why else _pools()
    used, prev, cache = {}, None, {}
    for m in ms:
        d = None
        if not why:
            p = _pick(pools, m, used, prev, cache)
            if p:
                real = os.path.realpath(p["file"])
                used[real] = used.get(real, 0) + 1
                prev = real
                d = {k: p[k] for k in ("choice", "name", "source", "trim")}
                d["file"] = _rel(p["file"])
        out["moments"].append(dict(m, default=d))
    _flush()
    return out


# ── measuring (cached; the same functions the builds use) ────────────────────────────────────────────────
_levels_mem = None
_levels_dirty = False


def _flush():
    """Save measurements taken since the last save (one write per call from the page, not one per file)."""
    global _levels_dirty
    if _levels_dirty and _levels_mem is not None:
        try:
            _atomic_json(LEVELS, _levels_mem)
            _levels_dirty = False
        except OSError:
            pass


def _levels():
    global _levels_mem
    if _levels_mem is None:
        _levels_mem = _json(LEVELS, {}) or {}
    return _levels_mem


def _measure(path, what, trim=None):
    """peak / mean dBFS or duration of a file, cached by size + time so the page never waits twice."""
    if not path or not os.path.isfile(path):
        return None
    st = os.stat(path)
    key = f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}|{what}|{trim or ''}"
    c = _levels()
    if key in c:
        return c[key]
    if what == "peak":
        v = audio_levels.peak_dbfs(path, trim)
    elif what == "mean":
        v = audio_levels.mean_dbfs(path, trim)
    elif what == "lufs":
        v = audio_levels.loudness_lufs(path)
    elif what == "mmax":
        v = audio_levels.momentary_max_lufs(path, trim)
    elif what == "peak_at":
        v = _peak_at(path)
    else:
        v = _duration(path)
    global _levels_dirty
    c[key] = v
    _levels_dirty = True
    return v


def _peak_at(path):
    """When a sound has become loud (first within 3 dB of its peak), in seconds from its start, or None if unreadable."""
    import array
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0?", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True, timeout=60).stdout
    except Exception:
        return None
    a = array.array("h", raw[: len(raw) // 2 * 2])
    if not a:
        return None
    step = 80
    env = [max(abs(x) for x in a[i:i + step]) for i in range(0, len(a), step)]
    best = max(env)
    at = next(i for i, v in enumerate(env) if v >= best * 0.7)   # the first moment within 3 dB of its loudest
    return round(at * step / 8000, 2)


def _duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return round(float(out), 3)
    except Exception:
        return None


def _ducks(jd):
    """The plan's own duck settings (caption-plan.json sfx_duck_db / music_duck_db), as the bake reads them."""
    cp = _json(os.path.join(jd, "caption-plan.json"), {}) or {}
    try:
        return (float(cp.get("sfx_duck_db", audio_levels.SFX_DUCK_DB)),
                float(cp.get("music_duck_db", audio_levels.bed_duck_db())))
    except (TypeError, ValueError):
        return audio_levels.SFX_DUCK_DB, audio_levels.bed_duck_db()


def auto_sfx_gain(path, programme, trim=None, duck_db=audio_levels.SFX_DUCK_DB):
    """The gain the build gives this cue: audio_levels.sfx_gain_db's rule (peak duck_db under the cut's peak,
    or SFX_TARGET_PEAK_DBFS with no cut yet), from cached measurements."""
    src = _measure(path, "peak", trim)
    if src is None:
        return 0.0
    vi = _measure(programme, "lufs") if programme else None   # the north star: under HER VOICE's loudness, by loudness
    mm = _measure(path, "mmax", trim)
    if vi is not None and mm is not None:
        shift = float(duck_db) - audio_levels.SFX_DUCK_DB      # a plan's own duck (sfx_duck_db) still moves it, dB for dB
        gain = vi + audio_levels.SFX_UNDER_VOICE_LU + shift - mm
        gain = min(gain, audio_levels.SFX_PEAK_CAP_DBFS - src)  # and never a peak above the cap (a sharp click)
        return round(audio_levels._clamp(gain), 1)
    pp = _measure(programme, "peak") if programme else None
    target = (pp + duck_db) if pp is not None else audio_levels.SFX_TARGET_PEAK_DBFS
    return round(audio_levels._clamp(target - src), 1)


def auto_bed_gain(path, programme, duck_db=None):
    """The gain the build gives a music bed: audio_levels.bed_gain_db's rule (mean duck_db under her voice; her
    taught level when she has one)."""
    taught = audio_levels.bed_duck_db() != audio_levels.BED_DUCK_DB
    if duck_db is None and not taught:                        # the north star: 15 LU under her voice, by loudness
        vi = _measure(programme, "lufs") if programme else None
        bl = _measure(path, "lufs")
        if vi is not None and bl is not None:
            return round(audio_levels._clamp(vi + audio_levels.BED_UNDER_VOICE_LU - bl), 1)
    duck_db = audio_levels.bed_duck_db() if duck_db is None else duck_db
    src = _measure(path, "mean")
    if src is None:
        return 0.0
    pm = _measure(programme, "mean") if programme else None
    target = (pm + duck_db) if pm is not None else audio_levels.BED_TARGET_MEAN_DBFS
    return round(audio_levels._clamp(target - src), 1)


# ── the plan the pipeline wrote ───────────────────────────────────────────────────────────────────────────
def base(jd):
    """(source file name, cue entries as the plan has them, the time key, music entry) from caption-plan.json, else
    sfx-plan.json. Entries are the plan's own dicts, untouched."""
    cp = _json(os.path.join(jd, "caption-plan.json"), {}) or {}
    sp = _json(os.path.join(jd, "sfx-plan.json"), {}) or {}
    music = cp.get("music") if isinstance(cp.get("music"), dict) else None
    if not music and isinstance(sp.get("music"), dict):
        music = sp.get("music")
    if isinstance(cp.get("sfx"), list) and cp.get("sfx"):
        return "caption-plan.json", [e for e in cp["sfx"] if isinstance(e, dict) and e.get("file")], "at", music
    if isinstance(sp.get("cues"), list) and sp.get("cues"):
        return "sfx-plan.json", [e for e in sp["cues"] if isinstance(e, dict) and e.get("file")], "t", music
    return ("caption-plan.json" if cp else None), [], "at", music


def _looks(jd):
    d = _json(os.path.join(jd, "review", "looks.json"), {}) or {}
    return [l for l in d.get("layers", []) or [] if isinstance(l, dict) and not l.get("captions") and not l.get("off")
            and not str(l.get("name", "")).startswith(("hf-reel-type", "captions", "hf-captions"))]


def _on_look(layers, t):
    """The graphic on screen when the cue plays: of the layers covering t, the one that started most recently."""
    on = [l for l in layers if (l.get("offset") or 0) - 0.05 <= t <= (l.get("offset") or 0) + (l.get("dur") or 0) + 0.05]
    if not on:
        return None
    return max(on, key=lambda l: (l.get("offset") or 0, -(l.get("dur") or 0))).get("name")


def _overrides(jd):
    """Her edits by cue id, and the music edit, from sound.json. Unreadable -> (None, None, reason)."""
    p = sound_json(jd)
    if not os.path.isfile(p):
        return {}, {}, None
    d = _json(p)
    if not isinstance(d, dict):
        return None, None, f"{os.path.relpath(p, ROOT)} can't be read"
    cues = {c["id"]: c for c in d.get("cues", []) or [] if isinstance(c, dict) and c.get("id")}
    m = d.get("music") if isinstance(d.get("music"), dict) else {}
    return cues, (m.get("edits") if isinstance(m.get("edits"), dict) else {}), None


def _store(jd):
    """The sounds she (or apply_defaults) added, and the reel-wide switch, from sound.json:
    {"added": [...], "sfx_enabled": bool, "bad": bool}. Unreadable -> nothing added, switch on, bad."""
    p = sound_json(jd)
    d = _json(p) if os.path.isfile(p) else {}
    if not isinstance(d, dict):
        return {"added": [], "sfx_enabled": True, "voice_enabled": True, "bad": True}
    added = [dict(a) for a in d.get("added", []) or [] if isinstance(a, dict) and a.get("id")]
    en, ve = d.get("sfx_enabled", True), d.get("voice_enabled", True)
    return {"added": added, "sfx_enabled": en if isinstance(en, bool) else True,
            "voice_enabled": ve if isinstance(ve, bool) else True, "bad": False}


def voice_muted(job):
    """True when she muted her clip's own sound for this reel (sound.json "voice_enabled": false)."""
    try:
        return not _store(job_dir(job))["voice_enabled"]
    except Exception:
        return False


def _nudge_of(o):
    v = _num((o or {}).get("nudge"))
    return max(-NUDGE_MAX, min(NUDGE_MAX, v)) if v is not None else 0.0


def _link(ms, plan_rows):
    """{layer: plan row} for planned cues that already sit on a look's entrance (nearest first, one each)."""
    pairs = sorted(((abs(r["t_plan"] - m["t"]), m["layer"], i) for m in ms for i, r in enumerate(plan_rows)
                    if abs(r["t_plan"] - m["t"]) <= MATCH_S), key=lambda x: x[0])
    out, taken = {}, set()
    for _d, layer, i in pairs:
        if layer in out or i in taken:
            continue
        out[layer] = plan_rows[i]
        taken.add(i)
    return out


def _empty_row(m):
    return {"id": f"look:{m['layer']}", "origin": "look", "t": m["t"], "name": "No sound", "file": None,
            "source": None, "on": False, "none": False, "empty": True, "gain_db": None, "gain_how": None,
            "on_look": m.get("look_layer", m["layer"]), "beat": None, "trim": None, "choice": None, "swapped": False,
            "missing": False, "original": None, "nudge": 0.0}


def _her_gain(a):
    """The level she set on a sound she added (its "gain_db", dB), or None when the engine levels it. A level she
    asked for in the chat (a song under a stretch with no voice, a typing burst brought up) is hers: the Sound tab,
    the preview and every build play it as set, never re-leveled (two buyers, 2026-10-22). A swap clears it."""
    return _num((a or {}).get("gain_db"))


def _added_row(jd, a, t, m, prog, sd, layers):
    """A sound from the "added" list as a row: on a look's entrance (m) or at a cut time she picked."""
    nud = _nudge_of(a)
    hers = _her_gain(a)
    f = _abs(a.get("file")) if a.get("file") and not a.get("none") else None
    missing = bool(f) and not os.path.isfile(f)
    dur = _measure(f, "duration") if f and not missing else None
    trim = _trim_for(m["kind"], m["motion_s"], dur, f) if m and f and not missing else (
        _trim_for(m["kind"], m["motion_s"], dur) if m else (_num(a.get("trim")) or None))
    when = round(max(0.0, t + nud), 3)
    row = {"id": a["id"], "origin": "look" if m else "free", "t": when, "name": a.get("name") or "No sound here",
           "file": _rel(f) if f else None, "source": a.get("source"), "on": bool(a.get("on", True)) and bool(f)
           and not missing and not a.get("word_cut"), "none": bool(a.get("none")), "empty": False,
           "word_cut": bool(a.get("word_cut")),
           "gain_db": (hers if hers is not None else auto_sfx_gain(f, prog, trim, sd)) if f and not missing else None,
           "gain_how": ("set" if hers is not None else "auto") if f else None,
           "on_look": m.get("look_layer", m["layer"]) if m else _on_look(layers, when),
           "beat": None, "trim": trim, "choice": a.get("choice"), "swapped": a.get("how") == "hers",
           "missing": missing, "nudge": nud, "how": a.get("how") or "hers",
           "original": None}
    if a.get("none"):
        row.update(name="No sound here", on=False)
    if not m:
        row["word"] = a.get("word")
    return row


# ── read ──────────────────────────────────────────────────────────────────────────────────────────────────
def read(job):
    """The reel's sounds with her edits applied, as the page shows them. Never writes sound.json."""
    jd = job_dir(job)
    src, entries, tkey, music = base(jd)
    prog = _programme(jd)
    sd, bd = _ducks(jd)
    layers = _looks(jd)
    ov, ovm, bad = _overrides(jd)
    ov, ovm = ov or {}, ovm or {}
    store = _store(jd)
    cues = []
    for e, cid in zip(entries, _ids(entries, tkey)):
        t = float(e.get(tkey, e.get("t", e.get("at", 0))) or 0)
        f = resolve_ref(jd, e.get("file"))
        choice, source, name = describe(jd, f)
        trim = e.get("trim")
        if "gain_db" in e:
            gain, how = float(e["gain_db"]), "set"
        elif e.get("volume") is not None:
            gain, how = round(20 * math.log10(max(float(e["volume"]), 1e-6)), 1), "set"
        else:
            gain, how = (auto_sfx_gain(f, prog, trim, sd) if f else None), "auto"
        row = {"id": cid, "origin": "plan", "t": round(t, 3), "t_plan": round(t, 3),
               "name": name or os.path.basename(str(e.get("file"))),
               "file": _rel(f), "source": source, "on": True, "none": False, "empty": False, "gain_db": gain,
               "gain_how": how, "on_look": _on_look(layers, t), "beat": e.get("beat") or e.get("_why"), "trim": trim,
               "choice": choice, "swapped": False, "missing": f is None, "nudge": 0.0,
               "original": {"name": name, "file": _rel(f), "choice": choice}}
        o = ov.get(cid)
        if o:
            if o.get("on") is False:
                row["on"] = False
            if o.get("none"):
                row.update(on=False, none=True)
            nud = _nudge_of(o)
            if nud:
                row.update(nudge=nud, t=round(max(0.0, t + nud), 3))
            if o.get("swapped") and o.get("file"):
                nf = _abs(o["file"])
                if os.path.isfile(nf):
                    row.update(swapped=True, file=_rel(nf), name=o.get("name") or row["name"],
                               source=o.get("source") or "library", choice=o.get("choice"),
                               gain_db=auto_sfx_gain(nf, prog, trim, sd), gain_how="auto", missing=False)
                else:
                    row["swap_missing"] = o.get("file")
        cues.append(row)
    ms = moments(jd)
    by_layer = {m["layer"]: m for m in ms}
    added = [] if store["bad"] else store["added"]
    anchored = {a["anchor"]["layer"]: a for a in added if isinstance(a.get("anchor"), dict) and a["anchor"].get("layer")}
    # a look whose sound she set keeps HER sound: a planned cue that lands near it later (her cut moved the look) stays
    # a cue of its own at its own time, never takes her look's place
    linked = _link([m for m in ms if m["layer"] not in anchored or anchored[m["layer"]].get("how") == "default"], cues)
    for r in cues:
        r.update(moment=False, anchor=None, motion_s=None, kind=None, look_name=None, timing=None)
    for layer, r in linked.items():
        m = by_layer[layer]
        r.update(moment=True, anchor={"layer": layer, "at": "entrance"}, motion_s=m["motion_s"], kind=m["kind"],
                 look_name=m["look_name"], timing=m["timing"], on_look=m.get("look_layer", layer),
                 part=m.get("part", 1), parts=m.get("parts", 1))
    orphans = []
    for m in ms:
        if m["layer"] in linked:
            continue
        a = anchored.get(m["layer"])
        r = _added_row(jd, a, m["t"], m, prog, sd, layers) if a else _empty_row(m)
        r.update(moment=True, anchor={"layer": m["layer"], "at": "entrance"}, motion_s=m["motion_s"], kind=m["kind"],
                 look_name=m["look_name"], timing=m["timing"], part=m.get("part", 1), parts=m.get("parts", 1))
        cues.append(r)
    for a in added:
        if isinstance(a.get("anchor"), dict):
            if a["anchor"].get("layer") not in by_layer or a["anchor"].get("layer") in linked:
                orphans.append(a["id"])            # its look is gone (or a planned cue now sits on it)
            continue
        t = _num(a.get("t"))
        if t is None:
            orphans.append(a["id"])
            continue
        r = _added_row(jd, a, t, None, prog, sd, layers)
        r.update(moment=False, anchor=None, motion_s=None, kind=None, look_name=None, timing=None)
        cues.append(r)
    for o in look_sounds(jd, layers):                       # a look's own sound: a row of its own, hers to switch off
        cues.append({"id": o["id"], "origin": "own", "t": o["at"], "name": f"{o['look_name']}'s own sound",
                     "file": _rel(o["file"]), "source": "look", "on": (ov.get(o["id"]) or {}).get("on") is not False,
                     "none": False, "empty": False, "gain_db": _own_gain(o["file"], prog, o["trim"], sd, o["volume"]),
                     "gain_how": "set", "on_look": o["layer"], "beat": None, "trim": o["trim"], "choice": None,
                     "swapped": False, "missing": False, "nudge": 0.0, "original": None, "moment": False, "anchor": None,
                     "motion_s": None, "kind": None, "look_name": o["look_name"], "timing": None, "own": True})
    for r in cues:
        r.pop("t_plan", None)
    cues.sort(key=lambda r: (r["t"], r["id"]))
    known = {r["id"] for r in cues if r["origin"] == "plan"}
    reg, mood = _register(jd)
    why = _quiet(reg, mood)
    plan = {"version": 1, "job": os.path.basename(jd), "from": src, "programme": _rel(prog),
            "sfx_enabled": store["sfx_enabled"], "voice_enabled": store["voice_enabled"], "register": reg, "quiet": bool(why), "quiet_reason": why,
            "moments": len(ms), "moments_without_sound": sum(1 for r in cues if r.get("empty")),
            "cues": cues, "music": _music_row(jd, music, ovm, prog, bd),
            "orphans": sorted([k for k in ov if k not in known] + orphans)}
    if bad:
        plan["problem"] = f"Your sound changes couldn't be read ({bad}). The plan is shown as the engine made it."
    _flush()
    return plan


def _music_file(jd, ref):
    if not ref:
        return None
    ref = str(ref)
    if os.path.isabs(ref):
        return ref if os.path.isfile(ref) else None
    for c in (os.path.join(jd, "audio", ref), os.path.join(jd, ref), os.path.join(ROOT, ref)):
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def _music_row(jd, music, edits, prog, bd=None):
    """The bed as the plan has it, with her edits (`edits`: on, a swapped song, level_db number or "auto") on top."""
    m = music or {}
    f = _music_file(jd, m.get("file"))
    choice, source, name = describe(jd, f)
    row = {"on": bool(f), "name": name, "file": _rel(f), "source": source, "choice": choice,
           "at": float(m.get("at", 0) or 0), "swapped": False, "missing": bool(m.get("file")) and f is None}
    if "gain_db" in m:
        row.update(level_db=float(m["gain_db"]), level_how="set")
    else:
        row.update(level_db=auto_bed_gain(f, prog, bd) if f else None, level_how="auto")
    nf = _abs(edits.get("file")) if edits.get("file") else None
    if nf and os.path.isfile(nf):
        row.update(swapped=True, file=_rel(nf), name=edits.get("name"), source=edits.get("source"),
                   choice=edits.get("choice"), level_db=auto_bed_gain(nf, prog, bd), level_how="auto", missing=False,
                   on=True)
    elif nf:
        row["swap_missing"] = edits.get("file")
    if "on" in edits:
        row["on"] = bool(edits["on"]) and bool(row.get("file"))
    lv = edits.get("level_db")
    if isinstance(lv, (int, float)) and row.get("file"):
        row.update(level_db=float(lv), level_how="set")
    elif lv == "auto" and row.get("file"):
        row.update(level_db=auto_bed_gain(_abs(row["file"]), prog, bd), level_how="auto")
    row["edits"] = dict(edits)
    return row


# ── choices ───────────────────────────────────────────────────────────────────────────────────────────────
def _durations_of(paths):
    return {p: _measure(p, "duration") for p in paths}


def choices(kind="sfx", job=None):
    """A Swap menu, hers first: her favorites folder ("favorite"), her CapCut favorites shelf ("capcut"), the
    Epidemic Sound files already on her computer ("epidemic"), this reel's own sounds ("hers"), then the engine's
    library ("library": capcut_sfx.selectable(), her switched-off sounds never offered). Each row:
    {"id", "name", "file" (engine-relative or absolute), "source", "duration"} (+ "tags" for library sounds)."""
    if kind not in ("sfx", "music"):
        raise Refuse(f"A Swap menu is for 'sfx' or 'music', not {kind!r}.")
    out, seen = [], set()

    def add(cid, name, path, source, dur=None, tags=None):
        real = os.path.realpath(path)
        if real in seen or not os.path.isfile(path):
            return
        if dur is None:
            dur = _measure(path, "duration")
        if dur is not None and ((kind == "sfx" and dur > SFX_MAX_S) or (kind == "music" and dur <= SFX_MAX_S)):
            return
        seen.add(real)
        row = {"id": cid, "name": name, "file": _rel(path), "source": source, "duration": dur}
        if tags:
            row["tags"] = tags
        if source == "library" and cid.startswith("lib:") and _lib_about(cid[4:]) not in (None, name):
            row["about"] = _lib_about(cid[4:])
        out.append(row)

    for e in favorites_folder.sounds(use=kind):
        add(e["id"], e["name"], e["file"], "favorite", e.get("duration"))
    if kind == "sfx":
        for s in _shelf():
            p = s["file"]
            add(f"fav:{os.path.splitext(os.path.basename(p))[0]}", _clean_title(s.get("title")) or s.get("name"),
                p, "capcut", s.get("seconds"))
    for cid, p, name in _epidemic_files():
        add(cid, name, p, "epidemic")
    if job:
        jd = job_dir(job)
        for p in _job_sounds(jd, kind):
            add(f"job:{os.path.relpath(p, jd).replace(os.sep, '/')}",
                favorites_folder._pretty(os.path.splitext(os.path.basename(p))[0]), p, "hers")
    if kind == "sfx":
        pal = capcut_sfx.selectable()
        fav_dir = capcut_sfx.FAVORITES_DIR
        by_file = {}
        for k, p in pal.items():
            if _under(p, fav_dir):
                continue                                  # her shelf, listed above as a favorite
            by_file.setdefault(os.path.realpath(p), []).append(k)
        ix = _index()
        rows = []
        for real, keys in by_file.items():
            stem = os.path.splitext(os.path.basename(real))[0]
            k = stem if stem in keys else sorted(keys)[0]
            meta = ix.get(k) or {}
            if meta.get("same_as") and meta["same_as"] in pal:
                k = meta["same_as"]; meta = ix.get(k) or meta
            tags = {t: meta[t] for t in ("job", "mood", "material") if meta.get(t)}
            rows.append((_lib_name(k).lower(), k, pal[k], tags))
        for _n, k, p, tags in sorted(rows):
            add(f"lib:{k}", _lib_name(k), p, "library", None, tags or None)
    _flush()
    return out


def _job_sounds(jd, kind):
    """This reel's own sound files: its sfx/ folders and audio/ (a song she dropped in, a pulled sound)."""
    out = []
    for d in (os.path.join(jd, "sfx"), os.path.join(jd, "audio")):
        if not os.path.isdir(d):
            continue
        for dp, dirs, files in os.walk(d):
            dirs[:] = sorted(x for x in dirs if not x.startswith(".") and "unused" not in x)
            for fn in sorted(files):
                if fn.lower().endswith(AUDIO_EXT) and not fn.startswith("."):
                    out.append(os.path.join(dp, fn))
    return out


def resolve_choice(choice_id, kind="sfx", job=None):
    """One Swap-menu id -> {"id", "name", "file" (absolute), "source", "duration"}. Raises Refuse with the reason."""
    cid = str(choice_id or "")
    jd = job_dir(job) if job else None
    path = name = source = None
    if cid.startswith("lib:"):
        k = cid[4:]
        pal = capcut_sfx.palette()
        if k not in pal:
            raise Refuse(f"The engine's library has no sound called {k!r}.")
        if k in capcut_sfx.disabled():
            raise Refuse(f"{_lib_name(k)} is switched off in your sound library, so it isn't offered.")
        path, name, source = pal[k], _lib_name(k), "library"
    elif cid.startswith("fav:"):
        stem = cid[4:]
        s = next((s for s in _shelf() if os.path.splitext(os.path.basename(s["file"]))[0] == stem), None)
        if not s:
            raise Refuse(f"{stem!r} isn't on your favorites shelf any more.")
        path, name, source = s["file"], _clean_title(s.get("title")) or stem, "capcut"
    elif cid.startswith("epi:"):
        prefix, _s, rel = cid[4:].partition("/")
        root = {"home": EPIDEMIC_HOME, "projects": PROJECTS_DIR}.get(prefix)
        p = os.path.realpath(os.path.join(root, rel)) if root and rel else None
        if not p or _epi_id(p) != f"epi:{prefix}/{os.path.relpath(p, os.path.realpath(root)).replace(os.sep, '/')}":
            raise Refuse("That isn't one of your Epidemic Sound downloads.")
        path, name, source = p, _epi_name(os.path.basename(p)), "epidemic"
    elif cid.startswith("folder:"):
        e = favorites_folder.entry(cid)
        if not e or e.get("kind") != "sound":
            raise Refuse(f"{cid[7:]!r} isn't a sound in your favorites folder (any more).")
        path, name, source = e["file"], e["name"], "favorite"
    elif cid.startswith("job:"):
        if not jd:
            raise Refuse("That sound belongs to a reel; open it from that reel.")
        p = os.path.realpath(os.path.join(jd, cid[4:]))
        if not p.startswith(os.path.realpath(jd) + os.sep):
            raise Refuse("That isn't one of this reel's sounds.")
        path, name, source = p, favorites_folder._pretty(os.path.splitext(os.path.basename(p))[0]), "hers"
    elif cid.startswith("file:"):
        p = os.path.realpath(os.path.join(ROOT, cid[5:]))
        if not p.startswith(os.path.realpath(ROOT) + os.sep):
            raise Refuse("That sound isn't inside the engine folder.")
        _c, source, name = describe(jd, p)
        path = p
    else:
        raise Refuse(f"{cid!r} isn't a sound from the Swap menu.")
    if not path or not os.path.isfile(path):
        raise Refuse(f"{name or cid} isn't on this computer any more.")
    if not path.lower().endswith(AUDIO_EXT):
        raise Refuse(f"{name} isn't a sound file.")
    dur = _measure(path, "duration")
    if dur is None:
        raise Refuse(f"{name} won't open. Drop in a fresh copy.")
    if kind == "sfx" and dur > SFX_MAX_S:
        pass                                                 # a long one as an effect: it plays its moment (trimmed), her call
    if kind == "music" and dur <= SFX_MAX_S:
        pass                                                 # a short one as a bed: it loops under her, her call
    return {"id": cid, "name": name, "file": path, "source": source, "duration": dur}


# ── edits ─────────────────────────────────────────────────────────────────────────────────────────────────
NONE_IDS = ("none", "no-sound", "silent")
ORIGINAL_IDS = ("original", "orig", "planned")


def _save(jd, plan, added=None, sfx_enabled=None, voice_enabled=None):
    """Write her sound.json: the planned cues' rows (what the page reads and the builds honor), the music, the sounds
    she added and the reel-wide switch. `added` / `sfx_enabled` None keep what the file already holds."""
    raw = _store(jd)
    keep = {"version": 1, "from": plan.get("from"),
            "cues": [c for c in plan["cues"] if c.get("origin", "plan") in ("plan", "own")], "music": plan["music"],
            "added": raw["added"] if added is None else added,
            "sfx_enabled": raw["sfx_enabled"] if sfx_enabled is None else bool(sfx_enabled),
            "voice_enabled": raw["voice_enabled"] if voice_enabled is None else bool(voice_enabled)}
    keep["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _atomic_json(sound_json(jd), keep)


def _cue(plan, cue_id):
    c = next((c for c in plan["cues"] if c["id"] == cue_id), None)
    if not c:
        raise Refuse(f"This reel has no sound {cue_id!r} (the sound plan may have changed; reopen the Sound section).")
    return c


def _stored(added, row):
    """The "added" entry behind a look / free row, created (empty) for a look that has none yet."""
    a = next((a for a in added if a.get("id") == row["id"]), None)
    if a is None:
        if row["origin"] != "look":
            raise Refuse("That sound isn't one you added (reopen the Sound section).")
        a = {"id": row["id"], "anchor": {"layer": row["anchor"]["layer"], "at": "entrance"}, "nudge": 0.0}
        added.append(a)
    return a


def _set_sound(a, ch, how):
    a.update(choice=ch["id"], file=_rel(ch["file"]), name=ch["name"], source=ch["source"], on=True, none=False,
             how=how)
    a.pop("gain_db", None)                                   # a new sound is leveled the engine's way, like any swap


def _motion_pick(jd, layer, plan):
    """The motion-matched sound for one look (ignoring the register: she asked for it), varied against the cues
    around it. None when no source has one."""
    ms = {m["layer"]: m for m in moments(jd)}
    m = ms.get(layer)
    if not m:
        return None
    used, prev, prev_t = {}, None, -1.0
    for r in plan["cues"]:
        if r.get("file") and r["id"] != f"look:{layer}":
            real = os.path.realpath(_abs(r["file"]))
            used[real] = used.get(real, 0) + 1
            if r["t"] <= m["t"] and r["t"] >= prev_t:
                prev, prev_t = real, r["t"]
    p = _pick(_pools(), m, used, prev, {})
    return {"id": p["choice"], "name": p["name"], "file": p["file"], "source": p["source"]} if p else None


def swap(job, cue_id, choice_id):
    """Swap one cue's sound. choice_id from choices('sfx', job); 'original' puts the planned sound back (on a look:
    the sound that matches its motion); 'none' makes that moment silent ("No sound here"). A new sound is leveled
    the way the engine levels every cue (auto), so it lands as loud as any other."""
    cid = str(choice_id or "")
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        c = _cue(plan, cue_id)
        if c["origin"] == "own":
            raise Refuse(OWN_SAYS)
        if c["origin"] == "plan":
            if cid in NONE_IDS:
                c.update(on=False, none=True)
            elif cid in ORIGINAL_IDS:
                o = c["original"]
                c.update(swapped=False, file=o["file"], name=o["name"], choice=o["choice"])
                if c.get("none"):
                    c.update(on=True, none=False)
            else:
                ch = resolve_choice(cid, "sfx", jd)
                c.update(swapped=True, file=_rel(ch["file"]), name=ch["name"], source=ch["source"], choice=ch["id"],
                         gain_db=auto_sfx_gain(ch["file"], _programme(jd), c.get("trim"), _ducks(jd)[0]),
                         gain_how="auto", missing=False)
                if c.get("none"):
                    c.update(on=True, none=False)
            _save(jd, plan)
            return read(jd)
        added = _store(jd)["added"]
        a = _stored(added, c)
        if cid in NONE_IDS:
            a.update(none=True, on=False, how="hers")
            for k in ("choice", "file", "name", "source"):
                a.pop(k, None)
        elif cid in ORIGINAL_IDS:
            if c["origin"] != "look":
                raise Refuse("A sound you added has no planned sound to go back to. Pick one, or remove it.")
            ch = _motion_pick(jd, c["anchor"]["layer"], plan)
            if not ch:
                raise Refuse("None of your sounds or the engine's fit this look's motion. Pick one from the list.")
            _set_sound(a, ch, "default")
        else:
            _set_sound(a, resolve_choice(cid, "sfx", jd), "hers")
        _save(jd, plan, added=added)
        return read(jd)


def toggle(job, cue_id, on):
    """Switch one cue on or off. `on` must be a real yes/no. Off on a look with no sound yet = "No sound here"
    (so the engine's defaults leave it silent)."""
    if not isinstance(on, bool):
        raise Refuse("On or off has to be a yes or a no.")
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        c = _cue(plan, cue_id)
        if c["origin"] in ("plan", "own"):                    # a look's own sound switches like a planned cue
            c["on"] = on
            if on:
                c["none"] = False
            _save(jd, plan)
            return read(jd)
        added = _store(jd)["added"]
        if c.get("empty") and not on:
            a = _stored(added, c)
            a.update(none=True, on=False, how="hers")
        else:
            if on and (c.get("empty") or c.get("none") or not c.get("file")):
                raise Refuse("There's no sound here yet. Pick one first.")
            if c.get("missing") and on:
                raise Refuse(f"{c.get('name')} isn't on this computer any more. Pick another sound.")
            a = _stored(added, c)
            a["on"] = on
            if on:
                a.pop("word_cut", None)                  # she turned it on: it plays where it is, her call
        _save(jd, plan, added=added)
        return read(jd)


def apply_defaults(job, register=None):
    """Give every look that moves and has no sound yet the sound that matches its motion, from her sources first
    (favorites folder, CapCut shelf, Epidemic downloads, then the engine's library), varied so nothing repeats back
    to back. Never touches a moment that has a sound, one she made silent, or a planned cue. Idempotent. A
    confessional (or somber) reel gets none. Returns the plan, with "applied": how many were filled."""
    with _LOCK:
        jd = job_dir(job)
        reg, mood = _register(jd, register)
        plan = read(jd)
        why = _quiet(reg, mood)
        todo = [r for r in plan["cues"] if r.get("empty")]
        if why or not todo:
            plan.update(applied=0, applied_note=why)
            return plan
        added = _store(jd)["added"]
        pools, cache, used = _pools(), {}, {}
        ms = {m["layer"]: m for m in moments(jd)}
        for r in plan["cues"]:
            if r.get("file") and not r.get("empty"):
                real = os.path.realpath(_abs(r["file"]))
                used[real] = used.get(real, 0) + 1
        prev, n = None, 0
        for r in plan["cues"]:                       # in cut order: each pick knows the sound just before it
            if not r.get("empty"):
                if r.get("file") and r.get("on"):
                    prev = os.path.realpath(_abs(r["file"]))
                continue
            m = ms.get(r["anchor"]["layer"])
            p = _pick(pools, m, used, prev, cache) if m else None
            if not p:
                continue
            a = _stored(added, r)
            _set_sound(a, {"id": p["choice"], "name": p["name"], "file": p["file"], "source": p["source"]}, "default")
            real = os.path.realpath(p["file"])
            used[real] = used.get(real, 0) + 1
            prev = real
            n += 1
        if n:
            _save(jd, plan, added=added)
        out = read(jd)
        out["applied"] = n
        return out


def _cut_length(jd):
    prog = _programme(jd)
    return _measure(prog, "duration") if prog else None


def retime_added(jd, times):
    """Her cut changed: each sound she added at a word moves with that word ({word index: (start, end)} in her new
    cut). A sound whose word she cut rests with its word ("word_cut"), never left on a stranger's moment, and plays
    again the moment her word is back. Her own on/off is never touched. Sounds on looks already follow their look.
    Returns how many changed."""
    with _LOCK:
        plan = read(jd)
        added = _store(jd)["added"]
        moved = 0
        for a in added:
            if a.get("anchor") or a.get("word") is None:
                continue
            w = int(a["word"])
            if w in times:
                nt = round(float(times[w][0]), 3)
                if abs(nt - float(a.get("t") or 0)) > 0.01:
                    a["t"] = nt; moved += 1
                if a.pop("word_cut", None):              # her word is back: so is its sound
                    moved += 1
            elif not a.get("word_cut"):
                a["word_cut"] = True; moved += 1
        if moved:
            _save(jd, plan, added=added)
        return moved


def add_cue(job, choice_id, t=None, layer=None, word=None):
    """A new sound: at the playhead (`t`, cut seconds; `word` = the index of the word she was on, kept for later
    re-timing) or on a look's entrance (`layer`: it then moves with the look). Exactly one of t / layer. A look that
    already has a sound is refused (swap it instead). Returns the plan, with "added_id"."""
    if (t is None) == (layer is None):
        raise Refuse("Add a sound either at the playhead or on a look, one or the other.")
    if word is not None and (isinstance(word, bool) or not isinstance(word, int) or word < 0):
        raise Refuse("The word has to be a word number from the script.")
    with _LOCK:
        jd = job_dir(job)
        ch = resolve_choice(choice_id, "sfx", jd)
        plan = read(jd)
        added = _store(jd)["added"]
        if layer is not None:
            row = next((r for r in plan["cues"] if r.get("anchor") and r["anchor"].get("layer") == layer), None)
            if not row:
                raise Refuse(f"There's no look called {layer!r} on this reel (or it doesn't move).")
            if row["origin"] == "plan" or not (row.get("empty") or row.get("none")):
                t, layer = row["t"], None                     # it has one already: hers plays too, at the same moment
            else:
                a = _stored(added, row)
                _set_sound(a, ch, "hers")
                a["nudge"] = 0.0
                new_id = a["id"]
        if layer is None:
            if isinstance(t, bool):
                raise Refuse("The playhead time has to be a number of seconds.")
            try:
                t = float(t)
            except (TypeError, ValueError):
                raise Refuse("The playhead time has to be a number of seconds.")
            length = _cut_length(jd)
            if not math.isfinite(t):
                raise Refuse("The playhead time has to be a number of seconds.")
            t = max(0.0, min(t, length)) if length else max(0.0, t)   # past either end: at that end, never refused
            nums = [int(m.group(1)) for a in added for m in [re.fullmatch(r"add-(\d+)", str(a.get("id")))] if m]
            new_id = f"add-{max(nums, default=0) + 1}"
            a = {"id": new_id, "anchor": None, "t": round(t, 3), "nudge": 0.0}
            if word is not None:
                a["word"] = word
            _set_sound(a, ch, "hers")
            added.append(a)
        _save(jd, plan, added=added)
        out = read(jd)
        out["added_id"] = new_id
        return out


def remove_cue(job, cue_id):
    """Take a sound off. One she added (or a look's sound) goes: a look goes back to "no sound yet". A planned cue
    is switched off (the plan itself is the engine's; switch it back on any time)."""
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        c = _cue(plan, cue_id)
        if c["origin"] in ("plan", "own"):
            c["on"] = False
            _save(jd, plan)
            return read(jd)
        added = _store(jd)["added"]
        keep = [a for a in added if a.get("id") != cue_id]
        if len(keep) == len(added):
            raise Refuse("There's no sound on that look to remove.")
        _save(jd, plan, added=keep)
        return read(jd)


def nudge(job, cue_id, delta_s):
    """Move one sound earlier (-) or later (+): the ⋯ menu's small steps, or a drag on the timeline. It never leaves
    her cut: the sound lands between 0 and the cut's end (and the total stays within +-NUDGE_MAX seconds)."""
    if isinstance(delta_s, bool):
        raise Refuse("A nudge is a number of seconds, like 0.1 or -0.1.")
    try:
        delta = float(delta_s)
    except (TypeError, ValueError):
        raise Refuse("A nudge is a number of seconds, like 0.1 or -0.1.")
    if not math.isfinite(delta):
        raise Refuse("A nudge is a number of seconds, like 0.1 or -0.1.")
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        c = _cue(plan, cue_id)
        if c.get("empty"):
            raise Refuse("There's no sound here to move yet.")
        cur = c.get("nudge") or 0.0
        base = c["t_plan"] if c["origin"] == "plan" and c.get("t_plan") is not None else (c.get("t") or 0.0) - cur
        new = max(-NUDGE_MAX, -max(0.0, base), min(NUDGE_MAX, cur + delta))                # never before 0:00
        end = _cut_length(jd)
        if end:
            new = min(new, max(0.0, end - base))                                          # never past her cut's end
        new = round(new, 3)
        if c["origin"] == "plan":
            c["nudge"] = new
            _save(jd, plan)
        else:
            added = _store(jd)["added"]
            _stored(added, c)["nudge"] = new
            _save(jd, plan, added=added)
        return read(jd)


def set_sfx_enabled(job, on):
    """The reel-wide Sound effects switch: off = no sound effects in any build (the music bed is its own switch)."""
    if not isinstance(on, bool):
        raise Refuse("On or off has to be a yes or a no.")
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        _save(jd, plan, sfx_enabled=on)
        return read(jd)


def set_voice_enabled(job, on):
    """Her clip's own sound: off = a muted clip (no voice on the CapCut main track, in the MP4 export or in the page's
    preview). The sound effects and music bed keep their own switches and levels."""
    if not isinstance(on, bool):
        raise Refuse("On or off has to be a yes or a no.")
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        _save(jd, plan, voice_enabled=on)
        return read(jd)


def music_step(job, step_db):
    """Louder / Quieter on her music bed: this reel moves by step_db, and how far under her voice it now sits is
    remembered (learned `sound.music_under_voice_db`) so every reel after this one starts there. Never fixed twice."""
    jd = job_dir(job)
    step_db = float(step_db)
    if not -12 <= step_db <= 12 or step_db != step_db:
        raise Refuse("A music step is a few dB, like 3 or -3.")
    M = read(job).get("music") or {}
    f = _abs(M.get("file")) if M.get("file") else None
    if not f or not os.path.isfile(f):
        raise Refuse("This reel has no song yet. Pick one first.")
    prog = _programme(jd)
    cur = float(M["level_db"]) if M.get("level_db") is not None else auto_bed_gain(f, prog)
    new = round(audio_levels._clamp(cur + step_db), 1)
    out = set_music(job, level_db=new)
    sm, pm = _measure(f, "mean"), (_measure(prog, "mean") if prog else None)
    taught = False
    if sm is not None and pm is not None:
        try:
            import learned
            learned.add("sound.music_under_voice_db", round(min(24.0, max(4.0, pm - (sm + new))), 1),
                        note="set with Louder / Quieter on a reel")
            taught = True
        except Exception:
            pass                                             # the reel's own level is saved either way
    return dict(out, taught=taught)


def set_music(job, on=None, choice_id=None, level_db=None):
    """The music bed: on/off, a different song (choices('music', job)), and its level in dB of gain ("auto" puts the
    engine's measured level back). A new song starts at the auto level, unless she set a level on the old one: then it
    keeps her level (the same step from the engine's own level), or a level comes with it."""
    if on is not None and not isinstance(on, bool):
        raise Refuse("On or off has to be a yes or a no.")
    if level_db is not None and level_db != "auto":
        try:
            level_db = float(level_db)
        except (TypeError, ValueError):
            raise Refuse(f"{level_db!r} isn't a level. Use a number of dB, like -6, or 'auto'.")
        if level_db != level_db:
            raise Refuse(f"{level_db!r} isn't a level. Use a number of dB, like -6, or 'auto'.")
        level_db = max(audio_levels.GAIN_MIN_DB, min(audio_levels.GAIN_MAX_DB, level_db))   # her level, held to the range
    with _LOCK:
        jd = job_dir(job)
        plan = read(jd)
        edits = dict((plan.get("music") or {}).get("edits") or {})
        has_file = bool((plan.get("music") or {}).get("file"))
        if choice_id is not None:
            ch = resolve_choice(choice_id, "music", jd)
            lv, of = edits.get("level_db"), (plan.get("music") or {}).get("file")
            off = None                                  # the level she set: how far she moved it from the engine's own
            if isinstance(lv, (int, float)) and of and os.path.isfile(_abs(of)):
                bd = _ducks(jd)[1]
                off = float(lv) - auto_bed_gain(_abs(of), _programme(jd), bd)
            edits.update(file=_rel(ch["file"]), name=ch["name"], source=ch["source"], choice=ch["id"], on=True)
            if off is None:
                edits.pop("level_db", None)             # no level of hers: the new song starts at the engine's measured level
            else:                                       # her level carries over: the new song sits where she put the old one
                edits["level_db"] = round(audio_levels._clamp(auto_bed_gain(ch["file"], _programme(jd), _ducks(jd)[1]) + off), 1)
            has_file = True
        if on is not None:
            if on and not has_file:
                raise Refuse("This reel has no song yet. Pick one from the Swap menu first.")
            edits["on"] = on
        if level_db is not None:
            if not has_file:
                raise Refuse("This reel has no song yet, so there's no level to set. Pick one first.")
            edits["level_db"] = "auto" if level_db == "auto" else round(level_db, 1)
        plan["music"] = dict(plan.get("music") or {}, edits=edits)
        _save(jd, plan)
        return read(jd)


# ── what the builds read ──────────────────────────────────────────────────────────────────────────────────
def for_build(jd, plan_sfx, plan_music, say=print):
    """The caption plan's sfx list and music entry with her Sound edits applied, in the SAME shape the builders
    already read (so build-reel-mp4.py and capcut_handoff.py change by one line). No sound.json: both come back
    exactly as given. A cue she switched off (or made "No sound here") is left out; a swapped cue gets her file
    (absolute) and no gain_db, so the builder auto-levels it like any cue; a nudged cue plays that much earlier or
    later; a cue she didn't touch is the plan's own dict, unchanged. Then the sounds on her looks (resolved to the
    look's entrance in looks.json NOW, so a look that moved takes its sound along) and the ones she added at a
    time: {"file" (absolute), "at", "trim" (the motion's length), "_sound": "look"|"added", "_why"}, no gain_db
    (auto-leveled) unless she set one on it ("gain_db" in sound.json "added"), which then plays exactly as set. The reel-wide Sound effects switch off: no sound effects at all; the music bed is untouched."""
    sfx = list(plan_sfx or [])
    jd = os.path.abspath(jd)

    def own(ov):                                             # each look's own sound, unless she switched it off
        prog, (sd, _bd) = _programme(jd), _ducks(jd)
        return [{"file": o["file"], "at": o["at"], **({"trim": o["trim"]} if o["trim"] else {}),
                 "gain_db": _own_gain(o["file"], prog, o["trim"], sd, o["volume"]), "_sound": "own",
                 "_why": f"the {o['look_name']}'s own sound"}
                for o in look_sounds(jd) if (ov.get(o["id"]) or {}).get("on") is not False]
    if not os.path.isfile(sound_json(jd)):
        return sfx + own({}), plan_music
    ov, ovm, bad = _overrides(jd)
    if bad:
        say(f"[sound] ⚠ {bad}: building the sound exactly as planned, without her Sound edits. Reopen the Sound "
            f"section to save them again.")
        return sfx + own({}), plan_music
    store = _store(jd)
    entries = [e for e in sfx if isinstance(e, dict) and e.get("file")]
    out, swapped, off, moved = [], 0, 0, 0
    for e, cid in zip(entries, _ids(entries, "at")):
        o = ov.get(cid)
        if not o:
            out.append(e); continue
        if o.get("on") is False or o.get("none"):
            off += 1; continue
        n = e
        if o.get("swapped") and o.get("file"):
            nf = _abs(o["file"])
            if os.path.isfile(nf):
                n = {k: v for k, v in e.items() if k not in ("gain_db", "volume")}
                n.update(file=nf, _sound="swapped")
                swapped += 1
            else:
                say(f"[sound] ⚠ her swap for {cid} points at a file that's gone ({o['file']}): using the planned sound.")
        nud = _nudge_of(o)
        if nud:
            n = dict(n, at=round(max(0.0, float(e.get("at", 0) or 0) + nud), 3))
            moved += 1
        out.append(n)
    # the sounds on her looks and the ones she added
    extra, gone = [], []
    if not store["bad"] and store["added"]:
        ml = moments(jd)
        ms = {m["layer"]: m for m in ml}
        hers = {a["anchor"]["layer"] for a in store["added"] if isinstance(a.get("anchor"), dict) and a["anchor"].get("layer")
                and a.get("how") != "default"}
        taken = set(_link([m for m in ml if m["layer"] not in hers],   # a planned cue sits there (never on a look whose
                          [{"t_plan": float(e.get("at", 0) or 0)} for e in entries]))   # sound she set: hers plays)
        for a in store["added"]:
            if a.get("on") is False or a.get("none") or a.get("word_cut") or not a.get("file"):
                continue
            f = _abs(a["file"])
            if not os.path.isfile(f):
                say(f"[sound] ⚠ {a.get('name') or a['id']} isn't on this computer any more ({a['file']}): left out.")
                continue
            anc = a.get("anchor") if isinstance(a.get("anchor"), dict) else None
            if anc:
                m = ms.get(anc.get("layer"))
                if not m or m["layer"] in taken:
                    gone.append(a["id"]); continue
                at, trim = m["t"], _trim_for(m["kind"], m["motion_s"], _measure(f, "duration"), f)
                why, kind = f"voices the {m['look_name']}", "look"
            else:
                at = _num(a.get("t"))
                if at is None:
                    gone.append(a["id"]); continue
                trim, why, kind = (_num(a.get("trim")) or None), "a sound she added", "added"
            cue = {"file": f, "at": round(max(0.0, at + _nudge_of(a)), 3), "_sound": kind, "_why": why}
            if trim:
                cue["trim"] = trim
            if _her_gain(a) is not None:                     # her set level, exactly as the Sound tab and preview play it
                cue["gain_db"] = _her_gain(a)
            extra.append(cue)
        extra.sort(key=lambda c: c["at"])
    out += extra
    music = _music_for_build(jd, plan_music, ovm or {})
    ids = set(_ids(entries, "at"))
    orphans = sorted(k for k, o in ov.items() if k not in ids and (o.get("on") is False or o.get("swapped")
                                                                    or o.get("none") or _nudge_of(o)))
    bits = []
    if swapped: bits.append(f"{swapped} swapped")
    if off: bits.append(f"{off} switched off")
    if moved: bits.append(f"{moved} nudged")
    n_look = sum(1 for c in extra if c["_sound"] == "look")
    if n_look: bits.append(f"{n_look} on her looks")
    if len(extra) - n_look: bits.append(f"{len(extra) - n_look} added")
    if ovm:
        bits.append("music " + ("off" if not music else os.path.basename(str(music.get("file")))
                                 + (f" at {music['gain_db']:+.1f} dB" if "gain_db" in music else " (auto level)")))
    if not store["sfx_enabled"]:
        bits.append(f"sound effects OFF ({len(out)} cue(s) not played)")
        out = []
    mine = own(ov)                                          # a look's own sound is the look, not a sound effect: the
    out += mine                                             # Sound effects switch leaves it; its own row switches it off
    if mine: bits.append(f"{len(mine)} look sound(s)")
    if bits:
        say(f"[sound] her Sound edits: {', '.join(bits)}")
    if orphans:
        say(f"[sound] {len(orphans)} of her Sound edits no longer match a cue in this plan (it changed since): "
            f"{', '.join(orphans)}. Left out.")
    if gone:
        say(f"[sound] {len(gone)} sound(s) she set on a look that's no longer on the reel (or now has a planned cue): "
            f"{', '.join(gone)}. Left out.")
    _flush()
    return out, music


def _music_for_build(jd, plan_music, edits):
    """The plan's music entry with her edits: off -> None; a swapped song -> its absolute file, auto level; a level
    she set -> gain_db; "auto" -> no gain_db (the builder measures it)."""
    if not edits:
        return plan_music
    m = dict(plan_music) if isinstance(plan_music, dict) else {}
    nf = _abs(edits.get("file")) if edits.get("file") else None
    if nf and os.path.isfile(nf):
        m["file"] = nf
        m.pop("gain_db", None)
    if edits.get("on") is False or not m.get("file"):
        return None if edits.get("on") is False else plan_music
    lv = edits.get("level_db")
    if isinstance(lv, (int, float)):
        m["gain_db"] = float(lv)
    elif lv == "auto":
        m.pop("gain_db", None)
    return m


def cues_for_build(job):
    """For a driver that places sound itself (raw / Super Yap): the cues to place, with her edits, as
    [{"id", "file" (absolute), "t", "trim", "volume" (linear, or None = auto-level)}] and the music entry or None."""
    jd = job_dir(job)
    src, entries, tkey, music = base(jd)
    plan_sfx = [dict(e, at=e.get(tkey, e.get("at", e.get("t", 0)))) for e in entries]
    sfx, m = for_build(jd, plan_sfx, music, say=lambda *_: None)
    out = []
    for e in sfx:
        f = e["file"] if os.path.isabs(str(e["file"])) else resolve_ref(jd, e["file"])
        if not f:
            continue
        vol = (audio_levels.to_linear(e["gain_db"]) if "gain_db" in e
               else float(e["volume"]) if e.get("volume") is not None else None)
        out.append({"id": cue_id(e["at"], e["file"]), "file": f, "t": float(e["at"]), "trim": e.get("trim"),
                    "volume": vol})
    if m and m.get("file"):
        m = dict(m, file=_music_file(jd, m["file"]) or m["file"])
    return out, (m or None)


# ── preview ───────────────────────────────────────────────────────────────────────────────────────────────
def preview_path(choice_id, job=None):
    """A file on her disk the page can play for this Swap-menu id. Already-playable files come back as they are;
    anything else (.aif, .flac, .ogg, .caf) is converted ONCE to .m4a under _local/sound-preview/ and reused."""
    cid = str(choice_id or "")
    kind = "music"
    try:
        src = resolve_choice(cid, "sfx", job)["file"]
    except Refuse:
        src = resolve_choice(cid, kind, job)["file"]
    if src.lower().endswith(PLAYABLE):
        return src
    st = os.stat(src)
    h = hashlib.sha1(f"{os.path.abspath(src)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:12]
    out = os.path.join(PREVIEW_DIR, f"{_slug(os.path.splitext(os.path.basename(src))[0])}-{h}.m4a")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    tmp = out[:-4] + ".part.m4a"
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-map", "0:a:0?", "-vn",
                        "-c:a", "aac", "-b:a", "192k", tmp], capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not os.path.isfile(tmp):
        raise Refuse(f"{os.path.basename(src)} couldn't be made playable for the preview.")
    os.replace(tmp, out)
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────────────────
def _print_plan(p):
    print(f"{p['job']}: sounds from {p['from'] or 'nowhere yet'}"
          + (f"  ({len(p['orphans'])} old edit(s) no longer match)" if p["orphans"] else ""))
    if p.get("problem"):
        print("  " + p["problem"])
    if not p.get("sfx_enabled", True):
        print("  Sound effects are switched OFF for this reel (the music bed is separate).")
    if not p.get("voice_enabled", True):
        print("  Your clip is muted for this reel: none of its own sound goes into the export.")
    if p.get("quiet_reason"):
        print("  " + p["quiet_reason"])
    if p.get("moments"):
        print(f"  {p['moments']} look(s) move; {p['moments_without_sound']} without a sound yet")
    for c in p["cues"]:
        g = f"{c['gain_db']:+.1f} dB {c['gain_how']}" if c.get("gain_db") is not None else "no file"
        state = "ON " if c["on"] else ("-- " if c.get("empty") else "off")
        look = f"  on {c['on_look']}" if c.get("on_look") else ""
        extra = f"  ({c['kind']}, {c['motion_s']}s)" if c.get("moment") else ""
        nud = f"  nudged {c['nudge']:+.2f}s" if c.get("nudge") else ""
        print(f"  {state} {c['t']:7.2f}s  {str(c['name'])[:34]:34}  {str(c['source'] or ''):8}  {g}"
              f"{'  [swapped]' if c['swapped'] else ''}{look}{extra}{nud}  [{c['id']}]")
    m = p["music"]
    if m.get("file"):
        lv = f"{m['level_db']:+.1f} dB {m['level_how']}" if m.get("level_db") is not None else ""
        print(f"  music: {'ON' if m['on'] else 'off'}  {m['name']}  {lv}{'  [swapped]' if m['swapped'] else ''}")
    else:
        print("  music: none")


def _opt(a, flag):
    return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else None



def playback(job):
    """What the visual editor plays in sync with her preview: every sound at its final time (nudges included), at
    the level the build gives it, and the music bed. The lean preview's voice is made at her cut's level
    (visual_editor._level_preview); voice_gain_db is what is left of the gated-loudness gap. The page plays her voice
    from the video itself (never through Web Audio, which ran late against her lips), so it can lower her voice but
    not raise it past 100%: what it can't raise comes off every sound instead, and the balance is the render's.
    (So the preview copy is made at her cut's level: pushing every sound down to a quiet voice buried short
    whooshes.) Switched-off, silenced, empty and
    missing sounds are left out; the reel-wide switch leaves out all."""
    jd = job_dir(job)
    d = read(job)
    prog = _programme(jd)
    sd = _ducks(jd)[0]
    prev = os.path.join(jd, "review", "preview.mp4")
    off = 0.0
    pm = _measure(prog, "lufs") if prog else None
    vm = _measure(prev, "lufs") if os.path.isfile(prev) else None
    if pm is None or vm is None:                             # no loudness meter: the plain average, as before
        pm = _measure(prog, "mean") if prog else None
        vm = _measure(prev, "mean") if os.path.isfile(prev) else None
    if pm is not None and vm is not None:
        off = round(max(-24.0, min(24.0, vm - pm)), 1)
    cues = []
    if d.get("sfx_enabled", True):
        for c in d.get("cues", []):
            if c.get("empty") or c.get("none") or not c.get("on") or c.get("missing") or not c.get("file"):
                continue
            f = _abs(c["file"])
            if not f or not os.path.isfile(f):
                continue
            # a set level plays as set; the rest at the level the build gives them, the plan's own duck included
            g = c.get("gain_db") if c.get("gain_how") == "set" and c.get("gain_db") is not None else auto_sfx_gain(f, prog, c.get("trim"), sd)
            cues.append({"id": c["id"], "t": round(float(c["t"]), 3), "src": c.get("choice") or ("file:" + c["file"]),
                         "trim": c.get("trim"), "gain_db": round(float(g or 0), 1)})
    music = None
    M = d.get("music") or {}
    if M.get("on") and M.get("file"):
        f = _abs(M["file"])
        if f and os.path.isfile(f):
            g = M.get("level_db") if M.get("level_how") == "set" and M.get("level_db") is not None else auto_bed_gain(f, prog)
            music = {"src": M.get("choice") or ("file:" + M["file"]), "at": float(M.get("at") or 0), "gain_db": round(float(g or 0), 1),
                     "fade_in": 0.0, "fade_out": 2.5, "loop": True}
    return {"cues": cues, "music": music, "voice_gain_db": round(-off, 1), "voice_muted": not d.get("voice_enabled", True)}

def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(a) >= 2 and a[0] == "show":
            _print_plan(read(a[1])); return 0
        if len(a) >= 2 and a[0] == "moments":
            for m in moments(a[1]):
                print(f"  {m['t']:7.2f}s  {m['kind']:7} {m['motion_s']:.2f}s  {m['timing']:6}  {m['layer']}  ({m['look_name']})")
            return 0
        if len(a) >= 2 and a[0] == "defaults":
            d = defaults_for(a[1], a[2] if len(a) > 2 else None)
            if d["reason"]:
                print(d["reason"])
            for m in d["moments"]:
                dd = m["default"]
                print(f"  {m['t']:7.2f}s  {m['kind']:7} {m['layer']:24}  "
                      + (f"{dd['name']} ({dd['source']}, {dd['trim']}s)" if dd else "no sound"))
            return 0
        if len(a) >= 2 and a[0] == "apply-defaults":
            p = apply_defaults(a[1], a[2] if len(a) > 2 else None)
            print(f"{p.get('applied', 0)} look(s) given a sound." + (f" {p['applied_note']}" if p.get("applied_note") else ""))
            _print_plan(p); return 0
        if len(a) >= 2 and a[0] == "choices":
            rows = choices(a[1], a[2] if len(a) > 2 else None)
            for r in rows:
                d = f"{r['duration']:.1f}s" if r.get("duration") else "?"
                print(f"  {r['source']:8}  {r['name'][:40]:40}  {d:>7}  {r['id']}")
            return 0
        if len(a) == 4 and a[0] == "swap":
            _print_plan(swap(a[1], a[2], a[3])); return 0
        if len(a) == 4 and a[0] == "toggle" and a[3] in ("on", "off"):
            _print_plan(toggle(a[1], a[2], a[3] == "on")); return 0
        if len(a) >= 3 and a[0] == "add":
            at, look, word = _opt(a, "--at"), _opt(a, "--look"), _opt(a, "--word")
            if word is not None and not word.isdigit():
                raise Refuse("--word is a word number.")
            _print_plan(add_cue(a[1], a[2], t=at, layer=look, word=int(word) if word else None)); return 0
        if len(a) == 3 and a[0] == "remove":
            _print_plan(remove_cue(a[1], a[2])); return 0
        if len(a) == 4 and a[0] == "nudge":
            _print_plan(nudge(a[1], a[2], a[3])); return 0
        if len(a) == 3 and a[0] == "sfx" and a[2] in ("on", "off"):
            _print_plan(set_sfx_enabled(a[1], a[2] == "on")); return 0
        if len(a) == 3 and a[0] == "voice" and a[2] in ("on", "off"):
            _print_plan(set_voice_enabled(a[1], a[2] == "on")); return 0
        if len(a) >= 2 and a[0] == "music":
            on = True if "--on" in a else False if "--off" in a else None
            _print_plan(set_music(a[1], on=on, choice_id=_opt(a, "--choice"), level_db=_opt(a, "--level"))); return 0
    except Refuse as e:
        print(str(e), file=sys.stderr); return 2
    print(__doc__.strip().split("\n")[0])
    print("Usage: sound_plan.py show <job> | moments <job> | defaults <job> [register] | apply-defaults <job> [register]"
          " | choices sfx|music [<job>] | swap <job> <cue> <choice|none|original> | toggle <job> <cue> on|off"
          " | add <job> <choice> (--at S | --look LAYER) [--word N] | remove <job> <cue> | nudge <job> <cue> <+-s>"
          " | sfx <job> on|off | voice <job> on|off | music <job> [--on|--off] [--choice ID] [--level DB|auto]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
