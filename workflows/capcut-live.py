#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyobjc-framework-ApplicationServices; sys_platform == 'darwin'",
#   "pyobjc-framework-Quartz; sys_platform == 'darwin'",
#   "pillow",   # `text` measures the pack's font to wrap the line (packbuild, capcut_text)
# ]
# ///
"""capcut-live.py: where every reel that finishes in CapCut gets put together, and the one tool that touches
her drafts. CapCut offers no API, so this works on the draft files while CapCut is closed and on the screen
while it is open, and it keeps the engine's CapCut promises on both sides. The file is laid out by those
promises, in this order:

  1. CapCut is closed for every write. A draft is a folder of plain JSON in CapCut's drafts folder (~/Movies on
      a Mac, %LOCALAPPDATA% on Windows). CapCut holds an open draft in memory and saves that copy over the files
      when it quits, so anything written while it runs is lost without a word. close_for_write() asks CapCut to
      quit on a Mac (it saves first) and reopens it after; on Windows it refuses until she has closed CapCut
      herself, because the only close that fully ends it there is a forced kill, which loses unsaved work.
      draft_safety.require_capcut_quit() has the last word either way. All of this runs on Windows too.

  2. Her hand edits are built on, never regenerated over, and the magnet holds. `layer`, `text`, `move`,
      `remove`, `place-plan` and `pip` read the draft as she left it and add to it (building_on). A from-scratch
      rebuild goes to the next version name (draft_safety.next_version). CapCut's first open of a draft rebuilds
      its Timelines/ cache and resets the main-track anchor; `fix-magnet` writes the anchor back into every copy
      after that open, and `check-magnet` exits non-zero if any copy is still broken. The capcut skill runs both
      after every build.

  3. Building and layering. `new-draft` lays a job's transcript/cuts.json down as a brand-new draft (the
      timeline JSON, draft_meta_info.json and the registry row that shows it on CapCut's home screen), one clip
      per cut, source times in microseconds, and refuses a folder that already exists. `--track` picks tracks by
      what they hold (footage = her footage, overlay = any other video track, text = text), because a draft
      built through VectCut carries the same flag on every track. `text` is set in her style pack.

  4. Driving the open app (Mac only). CapCut's QML interface exposes its own automation ids to the macOS
      accessibility tree (the playhead readout, each clip, each toolbar button). A command reads the windows
      once (Screen), finds what it needs by id, clicks it with a synthesized mouse event at its middle, and
      reads CapCut's own readouts back to confirm. Every id this depends on sits in the live map at the top of
      that section (every place clicked is read off CapCut's own boxes); the ids are private to CapCut and move
      with its updates, so `ids --map` checks them against the running CapCut before a command is trusted. No
      step sleeps a set time: each one reads CapCut (for the export, the folder) until what it needs is there,
      and goes on that moment (until()). This takes over her mouse and keyboard for a few seconds at a time. On
      Windows these commands say they are Mac-only; everything done with CapCut closed still works.

  5. Reading what CapCut shows: the playhead, the clips on screen, the timeline as JSON, a picture of the window.

Run it with no arguments for the commands. Driving the export for her stays an open product question: it
takes her mouse for the length of the dialog, and gates any further work on that side.
"""
import sys as _sys, os as _os_ds
for _stream in (_sys.stdout, _sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "../product"))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific

import importlib.util, json, os, platform, re, shutil, subprocess, sys, time, uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "product"))
from capcut_ripple import enforce_maintrack_ripple, snap_draft_dir, verify_draft_dir  # the ONE magnet anchor
import capcut_media  # owns the root_meta_info.json row, including a brand-new install's empty registry

USAGE = """capcut-live: every write happens with CapCut closed; the open app is only ever driven, never written to.

A new draft (fresh only; an existing name is refused, so a rebuild takes the next version, <base> 1.1 -> 1.2):
  new-draft <job> [--name <draft>]       her cut list as a new draft, one clip per cut
  drafts                                 every draft CapCut has on its home screen

Layering on top of her draft (a Mac closes and reopens CapCut around each call; on Windows, she closes it first):
  place-plan <draft> <job>               every graphic the job's graphics plan places, in one call
  pip <draft> <job> [--scale S]          her second camera as a picture-in-picture over every synced clip, its
                                         mic on the lines it carries (run product/sync_camera.py first)
  layer <draft> <mov> --at <s> [--dur <s>] [--layer N] [--force]
                                         no --layer: lowest free layer; --layer N: that place in the stack
  text <draft> "<text>" --at <s> [--dur <s>] [--pack <pack>] [--role caption|headline|thought|takeover|accent] [--force]
                                         set in the pack's font, size, color and case for that role
                                         (no --pack: STYLE_PACK, else her saved default pack)
  move <draft> [--track footage|text|overlay] [--index N], then any of: --x X --y Y --scale S --rotate R --opacity O
  remove <draft> [--track footage|text|overlay] [--index N]

After her first open (the magnet):
  fix-magnet <draft> · check-magnet <draft>

Driving the open app (Mac only; it takes her mouse and keyboard for a few seconds):
  start · open <draft> · quit
  go-to <seconds> [--draft <name>]       park on the exact frame, then read it back to be sure
  select <i> · delete <i> · split [seconds] · trim-left · trim-right
  undo · redo · save · marker · fit-timeline · play
  export [--to <dir>] [--timeout <s>]    run the export dialog, then wait for the file to land

Reading what CapCut shows:
  playhead · clips · timeline [--draft <name>]   timeline prints the app and the draft file side by side as JSON
  screenshot [out.png]

When a CapCut update moves things (read only, nothing is clicked):
  ids --map [--depth N] [--save <file.json>]     which ids this CapCut still answers to, and what to measure next
  ids [needle] [--depth N] · click-id <id> · click-at <x> <y> · key <combo>"""

APP_NAME = "CapCut"
ON_WINDOWS = os.name == "nt"
# The same root every draft writer uses: CapCut's own folder, or the engine's staging folder when a Microsoft
# Store Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
DRAFTS = Path(_ds.CAP)
REPO = Path(__file__).resolve().parent.parent
TEXT_SHELLS = Path(__file__).resolve().parent / "capcut-shells"

# How every wait in this file works: a step names what it needs (CapCut gone, an id on its screen, the playhead
# where it was sent, a file that stopped growing), checks for it every POLL_SECONDS and goes on the moment it
# holds. A limit never sets how long a step takes; it is only how long she waits before hearing what never came.
POLL_SECONDS = 0.5     # a step goes on at most half a second after its condition holds; each check of CapCut's
                       # screen walks its whole accessibility tree, so checking much faster would mostly be walking
LIVE_LIMITS = {        # seconds, upper bounds only (a value in _local/capcut-live-map.json overrides one)
    "settle": 1.0,     # CapCut answering a click or key on what is already on screen (a readout moving, a panel
                       # closing, a control being drawn): past a second a person sees the screen did not respond
    "load": 60.0,      # CapCut doing real work: starting, quitting, opening a draft with its media, opening the
                       # export dialog. One minute for all of them, so a slow machine is never called broken and
                       # she still hears within the minute when something is wrong
}
INPUT_GAP = 2 / 60     # between synthesized mouse and key events: two frames of a 60 Hz display, so each event
                       # lands in a frame of its own and CapCut never takes two of them as one
EXPORT_QUIET = 10.0    # an export counts as written once its file has not grown for this long: many times what
                       # CapCut spends on any one frame of an export. Waiting it out costs her seconds; calling it
                       # early would send the closing Escape into an export that is still running


def until(check, limit, gone=None):
    """Ask `check()` every POLL_SECONDS until it gives something, and give that back the moment it does. When
    `limit` seconds pass first: stop with `gone`, the plain sentence for what never came, or give back None to
    a caller that has its own next move."""
    began = time.time()
    while True:
        got = check()
        if got:
            return got
        waited = time.time() - began
        if waited >= limit:
            if gone:
                sys.exit(gone)
            return None
        time.sleep(min(POLL_SECONDS, limit - waited))


# ============================================================ 1. closing CapCut safely
def tell_capcut(verb):
    """AppleScript's polite form: 'activate' brings CapCut forward, 'quit' asks it to save and close. A Mac has
    AppleScript and a PC does not, so on Windows this does nothing: calling osascript there crashed a draft edit
    that had already saved, on its way to reopening the draft."""
    if ON_WINDOWS:
        return
    subprocess.run(["osascript", "-e", f'tell application "{APP_NAME}" to {verb}'], check=False)


def capcut_process():
    """CapCut's process id, or None when it is not running."""
    if ON_WINDOWS:
        return _windows_capcut_process()
    try:
        listed = subprocess.check_output(["pgrep", "-x", APP_NAME])
    except subprocess.CalledProcessError:
        return None                                      # pgrep's own way of saying "no match"
    return int(listed.split()[0])


def _windows_capcut_process():
    """tasklist rather than pgrep on Windows. CapCut runs as a main process plus helpers, so several rows can
    match and any one of them proves it is open. A tasklist that fails, or a row that will not parse, counts as
    'not running'."""
    try:
        rows = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
                              capture_output=True, text=True).stdout.splitlines()
        return next((int(cols[1]) for cols in (row.split() for row in rows)
                     if len(cols) >= 2 and cols[0].lower().startswith("capcut")), None)
    except Exception:
        return None


def close_capcut(timeout=None):
    """Close CapCut and wait until it is really gone (up to the load limit, or `timeout` seconds). On Windows it
    is a forced kill of the whole process tree, because the helper processes outlive a polite close, so only the
    `quit` command she types herself uses it there. A draft write never does: see close_for_write."""
    if capcut_process() is None:
        return
    if ON_WINDOWS:
        subprocess.run(["taskkill", "/IM", "CapCut.exe", "/F", "/T"], capture_output=True, check=False)
    else:
        tell_capcut("quit")
    limit = LIVE_LIMITS["load"] if timeout is None else timeout
    until(lambda: capcut_process() is None, limit,
          gone=f"CapCut was still running {limit:g}s after being asked to quit. "
               f"Close it by hand, then run this again.")


def open_capcut():
    if ON_WINDOWS:
        subprocess.run(["cmd", "/c", "start", "", "capcut:"], check=False)   # CapCut's URL scheme
        return
    subprocess.run(["open", "-a", APP_NAME], check=True)
    tell_capcut("activate")


def close_for_write(action):
    """Get CapCut out of the way of a draft write, or refuse the write.

    On a Mac it is asked to quit, which saves whatever she has open, and waited for. On Windows nothing is closed
    for her: the only close that reliably ends CapCut's helper processes there is a forced kill, and a forced kill
    throws away anything she had not saved yet, so the write is refused instead and she closes CapCut herself,
    exactly as the builders ask. Either way draft_safety has the last word before anything is written. It also
    catches a CapCut that `pgrep -x` alone does not see, and it counts "could not tell" as open."""
    if not ON_WINDOWS:
        close_capcut()
    _ds.require_capcut_quit(action)


# ============================================================ 2. her draft stays hers
# Every change to a draft she has is read from the draft as she left it and written back in place, inside
# building_on(). A refusal writes nothing. The magnet is fixed in every copy after her first open.
def existing_draft(name):
    # On a Mac that keeps the engine out of Movies, a draft she has is changed as a copy in the staging folder
    # and goes into CapCut as a new version (capcut_store_redirect.stage_existing). Everywhere else: DRAFTS/name.
    draft_dir = Path(__import__("capcut_store_redirect").stage_existing(name, str(DRAFTS)))
    if not draft_dir.exists():
        sys.exit(f"there is no draft named {name}")
    return draft_dir


@contextmanager
def building_on(name):
    """Open an existing draft for a change on disk: `with building_on(name) as (draft, folder): ...`.

    The draft is read as it stands, so whatever she changed by hand (CapCut saved it as it quit) is kept and built
    on. When the block finishes, the draft is written back and CapCut's caches for it are cleared, because CapCut
    only re-reads the JSON once they are gone; leave them and it quietly keeps what it already had, so the change
    never shows. If the block stops early (a refusal), nothing is written, and a CapCut this closed is opened again
    rather than left shut on her. CapCut is closed the way close_for_write says: asked to quit on a Mac, never
    killed on Windows (there a write while it is open is refused)."""
    folder = existing_draft(name)
    was_open = capcut_process() is not None
    closed_it = was_open and not ON_WINDOWS             # a Mac closes it for the write; Windows refuses instead
    try:
        close_for_write("change this draft")

        timeline = _ds.draft_json(str(folder))
        draft = json.loads(Path(timeline).read_text(encoding="utf-8"))
        yield draft, folder

        # A text clip CapCut has saved carries a null source range. The cache clear below makes CapCut import the
        # timeline again, and on that import a null range stops the export encoder, so each one is given the
        # clip's own length.
        for track in draft["tracks"]:
            for seg in track["segments"]:
                if seg.get("source_timerange") is None:
                    seg["source_timerange"] = {"start": 0, "duration": seg["target_timerange"]["duration"]}
        ends = [seg["target_timerange"]["start"] + seg["target_timerange"]["duration"]
                for track in draft["tracks"] for seg in track["segments"]]
        draft["duration"] = max(ends, default=0)
        write_compact(timeline, draft)
        Path(timeline + ".bak").unlink(missing_ok=True)
        # The prerender cache is keyed by the timeline ids, which exist only as Timelines/ folder names, so they
        # are read before Timelines/ is removed; with the cache left behind, a replaced graphic shows its old
        # picture.
        timeline_ids = _ds.draft_timeline_ids(str(folder))
        shutil.rmtree(folder / "Timelines", ignore_errors=True)
        cleared = _ds.clear_draft_caches(str(folder), timeline_ids)
        if cleared:
            print(f"  cleared {len(cleared)} stale prerender cache folder(s) for this draft")
    except BaseException:
        if closed_it:
            open_capcut()                               # stopped part-way: give her back the CapCut she had open
        raise

    if closed_it:
        open_capcut()
        open_draft(name)                                # waits for CapCut's home screen, then for the editor


def already_placed(draft, at_us, text=None, file_name=None):
    """Is this exact edit already in the draft? A run stopped after its write (on the relaunch, say) has already
    made its change, and running it again must not make it twice."""
    for track in draft["tracks"]:
        for seg in track["segments"]:
            if seg["target_timerange"]["start"] != at_us:
                continue
            if text is not None:
                material = _pooled(draft, "texts", seg["material_id"])
                if material and json.loads(material["content"]).get("text", "").split() == text.split():
                    return True
            if file_name is not None:
                material = _pooled(draft, "videos", seg["material_id"])
                if material and material["material_name"] == file_name:
                    return True
    return False


def _pooled(draft, pool, material_id):
    return next((entry for entry in draft["materials"][pool] if entry["id"] == material_id), None)


def media_into(folder, source):
    """A media file's copy inside the draft folder, where CapCut's sandbox (~/Movies) lets it read. A different
    file already holding that name keeps it; this one takes the next free name (media_slot)."""
    source = Path(source).expanduser().resolve()
    if not source.exists():
        sys.exit(f"can't find the media file: {source}")
    local, there = _ds.media_slot(folder / "Resources" / source.name, source)
    local = Path(local)
    if not there:
        local.parent.mkdir(exist_ok=True)
        copy_in(source, local)
    return local


def copy_in(source, into):
    """Hardlink `source` into a draft folder (no bytes move on one APFS volume), copying if linking fails."""
    try:
        into.hardlink_to(source)
    except OSError:
        shutil.copy2(source, into)


def write_compact(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def fix_magnet(name):
    """THE magnet fix and its fail-safe. On a draft's first import CapCut rebuilds its Timelines/ cache and resets
    the main-track anchor there, which silently kills the magnet; the anchor written into the draft at build time
    is ignored from then on. This writes it back into every copy AFTER that import. Run it once, after the fresh
    draft has been opened. capcut_ripple.py explains it in full ("THE TIMELINES RESET")."""
    folder = existing_draft(name)
    if not _ds.draft_jsons_under(str(folder), "Timelines/*"):
        sys.exit(f"'{name}' has no Timelines cache yet — open it in CapCut once (so CapCut builds the "
                 f"cache), then run: fix-magnet \"{name}\"")
    close_for_write("fix the magnet in this draft")      # CapCut rewrites the draft when it saves
    patched, problems = snap_draft_dir(str(folder))
    if problems:
        print("✗ MAGNET STILL BROKEN after snap:")
        _list_problems(problems)
        sys.exit(1)
    print(f"✓ magnet snapped into {patched} draft copies (top-level + Timelines) — every copy anchored.")
    open_capcut()
    if not ON_WINDOWS:
        # CapCut starts on its home screen; the draft is opened again so the next live command (export) finds the
        # editor. The magnet is fixed by now, so a draft that will not open is reported, not a failure.
        try:
            open_draft(name)
        except SystemExit as why:
            print(f"  could not open '{name}' by itself ({why}). Open it from CapCut's home screen before "
                  f"the next live command.")
    print(f"reopened '{name}' — trim/delete any main cut and the timeline ripples.")


def check_magnet(name):
    """FAIL-SAFE: check the anchor in EVERY copy of the timeline JSON, top level and Timelines/ alike, and exit
    non-zero if any is broken. A reset Timelines/ copy cannot be seen from the top-level file."""
    folder = existing_draft(name)
    try:
        problems = verify_draft_dir(str(folder))
    except RuntimeError as refusal:
        # verify_draft_dir refuses to call zero files clean; that means this folder has no timeline JSON at all.
        sys.exit(f"cannot verify '{name}': {refusal}")
    if problems:
        print(f"✗ magnet BROKEN in '{name}':")
        _list_problems(problems)
        sys.exit(1)
    print(f"✓ magnet OK in '{name}' — all draft copies anchored.")


def _list_problems(problems):
    for copy, what in problems.items():
        print("  ", copy, "->", what)


# ============================================================ 3. building and layering a draft


# Each shape below is an object this writes into a draft, field for field, in a fixed order. Keep that order when
# editing a shape: the self-heal playbook starts by diffing a draft from here against one CapCut made itself, and
# a stable order keeps that diff readable. A bare type stands for that type's blank value (str "", int 0,
# float 0.0, bool False, list []), NULL is JSON null, and anything else is written exactly as it is.

NULL = None


def blank(shape):
    """A fresh object built from a shape, nested dicts and lists included. Nothing is shared between two calls,
    so no two segments can ever end up holding the same list."""
    if isinstance(shape, type):
        return shape()
    if isinstance(shape, dict):
        return {field: blank(value) for field, value in shape.items()}
    if isinstance(shape, list):
        return [blank(item) for item in shape]
    return shape


def new_id():
    return str(uuid.uuid4()).upper()


def _corners(**points):
    """A crop box the way CapCut stores it: each named corner's x, then its y, as fractions of the frame."""
    return {f"{corner}_{axis}": value for corner, (x, y) in points.items() for axis, value in (("x", x), ("y", y))}


# One source file in the draft's media pool, uncropped.
MEDIA_SHAPE = {
    "id": str, "unique_id": str, "type": "video", "duration": int, "path": str, "media_path": str,
    "local_id": str, "has_audio": bool, "reverse_path": str, "intensifies_path": str,
    "reverse_intensifies_path": str, "intensifies_audio_path": str, "cartoon_path": str, "width": int,
    "height": int, "category_id": str, "category_name": str, "material_id": str, "material_name": str,
    "material_url": str,
    "crop": _corners(upper_left=(0.0, 0.0), upper_right=(1.0, 0.0), lower_left=(0.0, 1.0), lower_right=(1.0, 1.0)),
    "crop_ratio": "free", "audio_fade": NULL, "crop_scale": 1.0, "extra_type_option": int,
    "stable": {"stable_level": int, "matrix_path": str, "time_range": {"start": int, "duration": int}},
    "matting": {"flag": int, "path": str, "interactiveTime": list, "has_use_quick_brush": bool, "strokes": list,
                "has_use_quick_eraser": bool, "expansion": int, "feather": int, "reverse": bool,
                "custom_matting_id": str, "enable_matting_stroke": bool, "is_clould": bool,
                "mask_video_path": str, "cloud_product_fps": float},
    "source": int, "source_platform": int, "formula_id": str, "check_flag": 62978047,
    "video_algorithm": {"algorithms": list, "time_range": NULL, "path": str, "gameplay_configs": list,
                        "ai_in_painting_config": list, "complement_frame_config": NULL,
                        "motion_blur_config": NULL, "deflicker": NULL, "noise_reduction": NULL,
                        "quality_enhance": NULL, "super_resolution": NULL, "ai_background_configs": list,
                        "smart_complement_frame": NULL, "aigc_generate": NULL, "aigc_generate_list": list,
                        "mouth_shape_driver": NULL, "ai_expression_driven": NULL, "ai_motion_driven": NULL,
                        "image_interpretation": NULL,
                        "story_video_modify_video_config": {"task_id": str, "is_overwrite_last_video": bool,
                                                            "tracker_task_id": str, "generate_id": str,
                                                            "generate_card_id": str},
                        "skip_algorithm_index": list},
    "is_unified_beauty_mode": bool, "is_set_beauty_mode": bool, "object_locked": NULL, "smart_motion": NULL,
    "multi_camera_info": NULL, "freeze": NULL, "picture_from": "none", "picture_set_category_id": str,
    "picture_set_category_name": str, "team_id": str, "local_material_id": str, "origin_material_id": str,
    "request_id": str, "has_sound_separated": bool, "is_text_edit_overdub": bool,
    "is_ai_generate_content": bool, "aigc_type": "none", "is_copyright": bool, "aigc_history_id": str,
    "aigc_item_id": str, "local_material_from": str, "smart_match_info": NULL, "beauty_face_preset_infos": list,
    "beauty_body_preset_id": str,
    "beauty_face_auto_preset": {"preset_id": str, "name": str, "rate_map": str, "scene": str},
    "beauty_face_auto_preset_infos": list, "beauty_body_auto_preset": NULL, "live_photo_timestamp": -1,
    "live_photo_cover_path": str, "content_feature_info": NULL, "corner_pin": NULL, "surface_trackings": list,
    "video_mask_stroke": {"resource_id": str, "path": str, "type": str, "color": str, "size": float,
                          "alpha": float, "distance": float, "texture": float, "horizontal_shift": float,
                          "vertical_shift": float},
    "video_mask_shadow": {"resource_id": str, "path": str, "color": str, "alpha": float, "blur": float,
                          "distance": float, "angle": float},
}


# One clip on a track: the part of a source it plays and where on the timeline it plays it.
SEGMENT_SHAPE = {
    "id": str,
    "source_timerange": {"start": int, "duration": int},
    "target_timerange": {"start": int, "duration": int},
    "render_timerange": {"start": int, "duration": int},
    "desc": str, "state": int, "speed": 1.0, "is_loop": bool, "is_tone_modify": bool, "reverse": bool,
    "intensifies_audio": bool, "cartoon": bool, "volume": 1.0, "last_nonzero_volume": 1.0,
    "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": float, "transform": {"x": float, "y": float},
             "flip": {"vertical": bool, "horizontal": bool}, "alpha": 1.0},
    "uniform_scale": {"on": True, "value": 1.0}, "material_id": str, "extra_material_refs": list,
    "render_index": int, "keyframe_refs": list,
    "enable_lut": True, "enable_adjust": True, "enable_hsl": bool, "visible": True, "group_id": str,
    "enable_color_curves": True, "enable_hsl_curves": True, "track_render_index": int,
    # Born SDR, never HDR: new_draft refuses an HDR clip (product/hdr.py converts it first), so footage reaching
    # CapCut is bt709 by now and mode 1 renders it washed out.
    # product/capcut_color.py owns that decision; product/tests/test_capcut_color.py reads this literal.
    "hdr_settings": {"mode": 0, "intensity": 1.0, "nits": 203},
    "enable_color_wheels": True, "track_attribute": int, "is_placeholder": bool, "template_id": str,
    "enable_smart_color_adjust": bool, "template_scene": "default", "common_keyframes": list,
    "caption_info": NULL,
    "responsive_layout": {"enable": bool, "target_follow": str, "size_layout": int,
                          "horizontal_pos_layout": int, "vertical_pos_layout": int},
    "enable_color_match_adjust": bool, "enable_color_correct_adjust": bool, "enable_adjust_mask": bool,
    "raw_segment_id": str, "lyric_keyframes": NULL, "enable_video_mask": True,
    "digital_human_template_group_id": str, "color_correct_alg_result": str, "source": "segmentsourcenormal",
    "enable_mask_stroke": bool, "enable_mask_shadow": bool, "enable_color_adjust_pro": bool,
}


# The six helper materials CapCut hangs off every clip it makes, keyed by the pool each one lives in.
SEGMENT_HELPERS = {
    "speeds": {"type": "speed", "mode": int, "speed": 1.0, "curve_speed": NULL},
    "placeholder_infos": {"type": "placeholder_info", "meta_type": "none", "res_path": str, "res_text": str,
                          "error_path": str, "error_text": str},
    "canvases": {"type": "canvas_color", "color": str, "blur": float, "image": str, "album_image": str,
                 "image_id": str, "image_name": str, "source_platform": int, "team_id": str},
    "sound_channel_mappings": {"type": str, "audio_channel_mapping": int, "is_config_open": bool},
    "material_colors": {"is_color_clip": bool, "is_gradient": bool, "solid_color": str, "gradient_colors": list,
                        "gradient_percents": list, "gradient_angle": 90.0, "width": float, "height": float},
    "vocal_separations": {"type": "vocal_separation", "choice": int, "removed_sounds": list, "time_range": NULL,
                          "production_path": str, "final_algorithm": str, "enter_from": str},
}


# One track. flag is its role to CapCut: 0 the main track, 1 text, 2 an overlay above the main track.
TRACK_SHAPE = {"id": str, "type": str, "segments": list, "flag": int, "attribute": int, "name": str,
               "is_default_name": True}


# A whole draft. The materials pools are listed in CapCut's order; the last seven are the ones new-draft fills.
DRAFT_SHAPE = {
    "id": str, "version": 360000, "new_version": "175.0.0", "name": str, "duration": int, "create_time": int,
    "update_time": int, "fps": 30.0, "is_drop_frame_timecode": bool, "color_space": int,
    "config": {"video_mute": bool, "record_audio_last_index": 1, "extract_audio_last_index": 1,
               "original_sound_last_index": 1, "subtitle_recognition_id": str, "subtitle_taskinfo": list,
               "lyrics_recognition_id": str, "lyrics_taskinfo": list, "subtitle_sync": True, "lyrics_sync": True,
               "voice_change_sync": bool, "sticker_max_index": 1, "adjust_max_index": 1,
               "material_save_mode": int, "export_range": NULL, "maintrack_adsorb": True,
               "combination_max_index": 1, "attachment_info": list, "zoom_info_params": NULL,
               "system_font_list": list, "multi_language_mode": "none", "multi_language_main": "none",
               "multi_language_current": "none", "multi_language_list": list, "subtitle_keywords_config": NULL,
               "use_float_render": bool},
    "canvas_config": {"ratio": "original", "width": int, "height": int, "background": NULL},
    "tracks": list, "group_container": NULL,
    "materials": {
        "flowers": list, "tail_leaders": list, "audios": list, "images": list, "texts": list, "effects": list,
        "stickers": list, "transitions": list, "audio_effects": list, "audio_fades": list, "beats": list,
        "material_animations": list, "placeholders": list, "common_mask": list, "chromas": list,
        "text_templates": list, "realtime_denoises": list, "audio_pannings": list, "audio_pitch_shifts": list,
        "video_trackings": list, "hsl": list, "drafts": list, "color_curves": list, "hsl_curves": list,
        "primary_color_wheels": list, "log_color_wheels": list, "video_effects": list, "ai_text_effects": list,
        "audio_balances": list, "handwrites": list, "manual_deformations": list, "manual_beautys": list,
        "plugin_effects": list, "green_screens": list, "shapes": list, "digital_humans": list,
        "digital_human_model_dressing": list, "smart_crops": list, "ai_translates": list,
        "audio_track_indexes": list, "loudnesses": list, "vocal_beautifys": list, "smart_relights": list,
        "time_marks": list, "multi_language_refs": list, "video_shadows": list, "video_strokes": list,
        "video_radius": list,
        "videos": list, "canvases": list, "speeds": list, "placeholder_infos": list,
        "sound_channel_mappings": list, "material_colors": list, "vocal_separations": list,
    },
    "keyframes": {"videos": list, "audios": list, "texts": list, "stickers": list, "filters": list,
                  "adjusts": list, "handwrites": list, "effects": list},
    "keyframe_graph_list": list, "platform": dict, "last_modified_platform": dict, "mutable_config": NULL,
    "cover": NULL, "retouch_cover": NULL, "extra_info": NULL, "relationships": list,
    "mixed_track_mode_on": bool, "render_index_track_mode_on": True, "free_render_index_mode_on": bool,
    "static_cover_image_path": str, "source": "default", "time_marks": NULL, "path": str,
    "lyrics_effects": list,
    "uneven_animation_template_info": {"composition": str, "content": str, "order": str,
                                       "sub_template_info_list": list},
    "draft_type": "video", "smart_ads_info": {"page_from": str, "routine": str, "draft_url": str},
}


# The platform block every draft carries (platform and last_modified_platform), field for field.
PLATFORM_SHAPE = {"os": str, "os_version": str, "app_id": int, "app_version": str, "app_source": str,
                  "device_id": str, "hard_disk_id": str, "mac_address": str}


# draft_meta_info.json, checked field by field against one CapCut wrote itself. It is a different schema from
# the registry row (capcut_media owns that one): this file carries draft_enterprise_info as a nested object next
# to the flat draft_cloud_* fields, plus the imported-media list. Do not flatten it.
META_SHAPE = {
    "cloud_draft_cover": bool, "cloud_draft_sync": bool, "cloud_package_completed_time": str,
    "draft_cloud_capcut_purchase_info": str, "draft_cloud_last_action_download": bool,
    "draft_cloud_package_type": str, "draft_cloud_purchase_info": str, "draft_cloud_template_id": str,
    "draft_cloud_tutorial_info": str, "draft_cloud_videocut_purchase_info": str,
    "draft_cover": "draft_cover.jpg", "draft_deeplink_url": str,
    "draft_enterprise_info": {"draft_enterprise_extra": str, "draft_enterprise_id": str,
                              "draft_enterprise_name": str, "enterprise_material": list},
    "draft_fold_path": str, "draft_has_unfinished_aigc_video_effect": bool, "draft_id": str,
    "draft_is_ae_produce": bool, "draft_is_ai_packaging_used": bool, "draft_is_ai_shorts": bool,
    "draft_is_ai_translate": bool, "draft_is_article_video_draft": bool, "draft_is_cloud_temp_draft": bool,
    "draft_is_from_deeplink": "false", "draft_is_infinite_canvas_draft": bool, "draft_is_invisible": bool,
    "draft_is_pippit_draft": bool, "draft_is_web_article_video": bool, "draft_materials": list,
    "draft_materials_copied_info": list, "draft_name": str, "draft_need_rename_folder": bool,
    "draft_new_version": str, "draft_removable_storage_device": str, "draft_root_path": str,
    "draft_segment_extra_info": list, "draft_timeline_materials_size_": int, "draft_type": str,
    "draft_web_article_video_enter_from": str, "pippit_avatar_url": str, "pippit_extra_info": str,
    "pippit_id": str, "pippit_user_name": str, "tm_draft_cloud_completed": str, "tm_draft_cloud_entry_id": -1,
    "tm_draft_cloud_modified": int, "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
    "tm_draft_cloud_user_id": -1, "tm_draft_create": int, "tm_draft_modified": int, "tm_draft_removed": int,
    "tm_duration": int,
}


# One row of the meta file's imported-media list (group type 0).
IMPORTED_SHAPE = {
    "ai_group_type": str, "create_time": int, "duration": int, "enter_from": int, "extra_info": str,
    "file_Path": str, "height": int, "id": str, "import_time": int, "import_time_ms": int, "item_source": 1,
    "md5": str, "metetype": "video", "roughcut_time_range": {"duration": int, "start": int},
    "sub_time_range": {"duration": -1, "start": -1}, "type": int, "width": int,
}


# ---- a new draft from her cut list

def new_track(kind, flag, segments=None):
    track = blank(TRACK_SHAPE)
    track.update(id=new_id(), type=kind, flag=flag)
    if segments is not None:
        track["segments"] = segments
    return track


def probe_video(path):
    """(width, height, duration in microseconds, has an audio stream) of a video file, via ffprobe."""
    listing = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                       "stream=codec_type,width,height,duration", "-of", "json", str(path)])
    streams = json.loads(listing)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    has_sound = any(stream["codec_type"] == "audio" for stream in streams)
    return int(video["width"]), int(video["height"]), int(float(video["duration"]) * 1e6), has_sound


def source_rotation(path):
    """How far a player turns this file's picture on playback, in degrees; 0 when the file says nothing. A phone
    filming upright stores the picture on its side (3840x2160) and records a -90 here, so the stored width and
    height alone call an upright reel landscape."""
    try:
        listing = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                           "stream_side_data=rotation:stream_tags=rotate", "-of", "json",
                                           str(path)])
        stream = (json.loads(listing).get("streams") or [{}])[0]
    except (subprocess.CalledProcessError, OSError, ValueError):
        return 0
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            return int(float(side["rotation"]))
    try:
        return int(float((stream.get("tags") or {}).get("rotate", 0)))
    except (TypeError, ValueError):
        return 0


def canvas_for(probed, rotation):
    """The draft's canvas, shaped like the footage as it plays: an upright 9:16 clip gets a 9:16 canvas and a
    landscape one gets 1920x1080, as before. The short side is 1080, the size every builder in the engine uses."""
    width, height = probed[0], probed[1]
    if rotation % 180:
        width, height = height, width
    if width <= 0 or height <= 0:
        return 1920, 1080
    scale = 1080 / min(width, height)
    return round(width * scale / 2) * 2, round(height * scale / 2) * 2


def media_entry(material_id, path, probed):
    width, height, length_us, has_sound = probed
    media = blank(MEDIA_SHAPE)
    media.update(id=material_id, path=str(path), material_name=Path(path).name, width=width, height=height,
                 duration=length_us, has_audio=has_sound)
    return media


def attach_helpers(pools):
    """Give one new clip its six helper materials; their ids, in order, become its extra_material_refs."""
    refs = []
    for pool, shape in SEGMENT_HELPERS.items():
        helper = {"id": new_id(), **blank(shape)}
        pools.setdefault(pool, []).append(helper)   # a VectCut-built draft can lack a pool (placeholder_infos)
        refs.append(helper["id"])
    return refs


def clip_segment(pools, material_id, source_start, length, timeline_start):
    """A clip playing `length` microseconds of a source from `source_start`, placed at `timeline_start`."""
    refs = attach_helpers(pools)
    segment = blank(SEGMENT_SHAPE)
    segment["id"] = new_id()
    segment["source_timerange"] = {"start": source_start, "duration": length}
    segment["target_timerange"] = {"start": timeline_start, "duration": length}
    segment["material_id"] = material_id
    segment["extra_material_refs"] = refs
    return segment


def installed_capcut_version():
    """The version of the CapCut installed here, read from its own records; nothing is run or opened. A Mac
    reads the app's Info.plist; Windows reads the uninstall entry CapCut's installer registers, then the
    version folder the desktop CapCut runs from. None when none of them can be read."""
    if ON_WINDOWS:
        return _windows_capcut_version()
    import plistlib
    for app in (Path("/Applications/CapCut.app"), Path.home() / "Applications" / "CapCut.app"):
        try:
            with open(app / "Contents" / "Info.plist", "rb") as plist:
                return str(plistlib.load(plist)["CFBundleShortVersionString"])
        except (OSError, KeyError, ValueError, plistlib.InvalidFileException):
            continue
    return None


def _windows_capcut_version():
    try:
        import winreg
        uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, uninstall) as entries:
            for number in range(winreg.QueryInfoKey(entries)[0]):
                with winreg.OpenKey(entries, winreg.EnumKey(entries, number)) as entry:
                    try:
                        if str(winreg.QueryValueEx(entry, "DisplayName")[0]).startswith("CapCut"):
                            return str(winreg.QueryValueEx(entry, "DisplayVersion")[0])
                    except OSError:
                        continue
    except (ImportError, OSError):
        pass
    apps = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps"
    versions = [folder.name for folder in apps.glob("*") if re.fullmatch(r"\d+(\.\d+)+", folder.name)
                and (folder / "CapCut.exe").exists()] if os.environ.get("LOCALAPPDATA") else []
    return max(versions, key=lambda name: tuple(int(part) for part in name.split(".")), default=None)


def _vectcut_platform():
    """The platform block the engine's VectCut builders stamp on every draft they make (draft_profiles), which
    her CapCut opens as its own; {} if the vendored engine cannot be read."""
    profiles = REPO / "product" / "engine" / "VectCutAPI" / "draft_profiles.py"
    try:
        spec = importlib.util.spec_from_file_location("_vectcut_draft_profiles", profiles)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return dict(module.CAPCUT_PLATFORM)
    except Exception:
        return {}


def platform_stamp():
    """The platform block for a new draft: the VectCut builders' own, with this computer's system and the
    installed CapCut's version written in wherever they can be read."""
    stamp = blank(PLATFORM_SHAPE)
    stamp.update(_vectcut_platform())
    stamp["os"] = "windows" if ON_WINDOWS else "mac"
    system = platform.win32_ver()[1] if ON_WINDOWS else platform.mac_ver()[0]
    stamp["os_version"] = system or stamp["os_version"]
    stamp["app_version"] = installed_capcut_version() or stamp["app_version"]
    return stamp


def lay_cut_list(footage, cut_list, clip_of):
    """A complete draft playing the cut list: clips butt-joined in order on the main track, each one playing the
    source file its own cut names. `footage` maps each clip name to its copy inside the draft, in the order the
    cut list first uses them; `clip_of(cut)` names a cut's clip, so a reel filmed in two takes plays each take
    where the cut list puts it."""
    probes = {clip: probe_video(path) for clip, path in footage.items()}
    first = next(iter(footage))
    canvas = canvas_for(probes[first], source_rotation(footage[first]))
    stamp = platform_stamp()
    draft = blank(DRAFT_SHAPE)
    pools = draft["materials"]
    material_of = {}
    for clip, path in footage.items():
        material_of[clip] = new_id()
        pools["videos"].append(media_entry(material_of[clip], path, probes[clip]))
    main, timeline_at = [], 0
    for cut in cut_list["segments"]:
        source_at = round(cut["start"] * 1e6)
        length = round((cut["end"] - cut["start"]) * 1e6)
        main.append(clip_segment(pools, material_of[clip_of(cut)], source_at, length, timeline_at))
        timeline_at += length
    draft["id"] = new_id()
    draft["duration"] = timeline_at
    draft["canvas_config"]["width"], draft["canvas_config"]["height"] = canvas
    draft["tracks"] = [new_track("video", 0, main)]
    draft["platform"] = draft["last_modified_platform"] = stamp
    return draft, probes


def meta_for(name, folder, draft_id, footage, probes, total_us, stamp_us):
    """draft_meta_info.json for a new draft: one imported-media row per source file it plays."""
    stamp_s = stamp_us // 1_000_000
    rows = []
    for clip, path in footage.items():
        width, height, raw_us, _ = probes[clip]
        imported = blank(IMPORTED_SHAPE)
        imported.update(id=str(uuid.uuid4()), file_Path=str(path), extra_info=Path(path).name, width=width,
                        height=height, duration=raw_us, create_time=stamp_s, import_time=stamp_s,
                        import_time_ms=stamp_us)
        imported["roughcut_time_range"]["duration"] = raw_us
        rows.append(imported)
    meta = blank(META_SHAPE)
    meta.update(draft_id=draft_id, draft_name=name, draft_fold_path=str(folder), draft_root_path=str(DRAFTS),
                tm_duration=total_us, tm_draft_create=stamp_us, tm_draft_modified=stamp_us)
    meta["draft_materials"] = ([{"type": 0, "value": rows}]
                               + [{"type": group, "value": []} for group in (1, 2, 3, 6, 7)])
    return meta


def new_draft(job, name=None):
    """Lay a job's rough cut down as a brand-new draft. Fresh drafts only: a draft she has already worked on in
    CapCut is built on with the add-* commands, never regenerated over."""
    job_dir = REPO / "projects" / job
    edl = job_dir / "transcript" / "cuts.json"
    if not edl.exists():
        sys.exit(f"no cut list at {edl}. Make the rough cut first (FLAT_RENDER=0: a CapCut job needs no flat render).")
    cut_list = json.loads(edl.read_text(encoding="utf-8"))
    first = cut_list["segments"][0]
    source_clip = job_dir / "raw" / first["clip"]

    def clip_of(cut):                                    # a cut that names no clip plays the first cut's
        return cut.get("clip") or first["clip"]
    clips = list(dict.fromkeys(clip_of(cut) for cut in cut_list["segments"]))
    for clip in clips:
        if not (job_dir / "raw" / clip).exists():
            sys.exit(f"the raw clip the cut list names is not there: {job_dir / 'raw' / clip}")
    from hdr import hdr_kind                              # every segment is marked SDR below, so it must be
    for clip in clips:
        if hdr_kind(str(job_dir / "raw" / clip)) in ("hlg", "pq"):
            import capcut_color
            sys.exit(capcut_color.CONVERT_FIRST.format(name=clip).replace("<job>", job))
    name = name or job
    draft_dir = DRAFTS / name
    if draft_dir.exists():
        sys.exit(f"{draft_dir} already exists. Give the new draft a different --name.")

    was_open = capcut_process() is not None
    if was_open and not ON_WINDOWS:                      # Windows refuses rather than kill it (close_for_write)
        print("closing CapCut first (it rewrites its list of drafts as it quits)...")
        close_capcut()
    _ds.require_capcut_quit("add a new draft to CapCut's list")

    # CapCut's sandbox grants it assets.movies.read-write and nothing more, so it cannot read a file in the repo:
    # the footage has to sit inside the draft folder, under ~/Movies. One copy per source file the cut list plays.
    (draft_dir / "Resources").mkdir(parents=True)
    footage, taken = {}, set()
    for number, clip in enumerate(clips):
        local_name = Path(clip).name
        if local_name in taken:                          # two clips from different folders sharing a file name
            local_name = f"{number}-{local_name}"
        taken.add(local_name)
        footage[clip] = draft_dir / "Resources" / local_name
        copy_in(job_dir / "raw" / clip, footage[clip])

    draft, probes = lay_cut_list(footage, cut_list, clip_of)
    enforce_maintrack_ripple(draft)
    stamp_us = time.time_ns() // 1000
    draft_id = new_id()
    write_compact(_ds.draft_json(str(draft_dir)), draft)
    write_compact(draft_dir / "draft_meta_info.json",
                  meta_for(name, draft_dir, draft_id, footage, probes, draft["duration"], stamp_us))
    # the home-screen tile's picture: the first kept frame. Cosmetic, so a failure here is ignored.
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(first["start"]), "-i", str(source_clip), "-frames:v", "1",
                    "-vf", "scale=480:-2", str(draft_dir / "draft_cover.jpg")], check=False)
    # The registry row comes from the same writer the builders' finalize() uses. A second hand-rolled copy of that
    # schema once lived here and drifted from what CapCut really writes.
    capcut_media.register_draft(str(DRAFTS), name, str(draft_dir), _ds.draft_json(str(draft_dir)), draft_id,
                                draft["duration"], stamp_us // 1_000_000)

    print(f"'{name}' holds {len(cut_list['segments'])} segments over {draft['duration'] / 1e6:.2f}s, in {draft_dir}")
    if was_open:
        open_capcut()
        print("CapCut is open again")


# ---- tracks, by what they hold

# The words --track takes, and the role each one picks. "main": older name, still accepted.
TRACK_WORDS = {"footage": "main", "main": "main", "overlay": "overlay", "text": "text"}


def main_track(draft):
    """The footage track: the one the magnet anchors every other track to. CapCut marks an overlay flag 2, but a
    draft the builders made through VectCut carries flag 0 on EVERY track, so the flag alone cannot tell main from
    overlay there. What can is the anchor (is_default_name False) and then the clip count, which is how
    capcut_ripple picks the main track when it anchors one."""
    videos = [track for track in draft["tracks"] if track["type"] == "video"]
    candidates = [track for track in videos if track.get("flag") != 2] or videos
    return max(candidates, key=lambda track: (track.get("is_default_name") is False, len(track["segments"])),
               default=None)


def role_tracks(draft, role):
    """The tracks playing one role, in draft order, chosen by what they hold rather than by flag. Choosing by flag
    found no text or overlay at all in a VectCut-built draft (flag 0 everywhere), and the footage role reached into
    its text and sound tracks, so `remove --track footage` could delete a caption or a sound."""
    main = main_track(draft)
    if TRACK_WORDS.get(role, role) == "main":
        return [main] if main is not None else []
    if role == "overlay":
        return [track for track in draft["tracks"] if track["type"] == "video" and track is not main]
    return [track for track in draft["tracks"] if track["type"] == "text"]


# ---- layering graphics and text on top

def _overlay_stack(draft):
    return [track for track in draft["tracks"] if track["type"] == "video" and track["flag"] == 2]


GRADE_TRACKS = ("filter", "adjust", "effect")   # a grade layer grades every clip whose render_index is below its own


def _busy(track, at_us, length_us):
    """Does anything on this track play between at_us and at_us + length_us? Clips that only touch do not count."""
    return any(seg["target_timerange"]["start"] < at_us + length_us
               and at_us < seg["target_timerange"]["start"] + seg["target_timerange"]["duration"]
               for seg in track["segments"])


def _render_index_at(draft, position):
    """The render_index a new clip at `position` in the track list stacks with: one above every video clip on a
    track before it. A draft whose graphics were lifted over her grade keeps the new one lifted too."""
    below = [seg.get("render_index") or 0 for track in draft["tracks"][:position] if track["type"] == "video"
             for seg in track["segments"]]
    return max(below, default=0) + 1


def _insert_track(draft, position):
    """A new overlay track at `position` in the track list, with every clip's indexes kept in step. Tracks after
    it move one place along, so each clip's track_render_index (CapCut saves it as the track's place in the list)
    moves with them. A video clip above it that already holds the new clip's render_index is lifted by one, with
    everything above it up to the next grade layer, so the stacking order stays the same and nothing crosses
    from under her grade to over it."""
    tracks = draft["tracks"]
    render_index = _render_index_at(draft, position)
    ceiling = min((seg.get("render_index") or 0 for track in tracks if track["type"] in GRADE_TRACKS
                   for seg in track["segments"] if (seg.get("render_index") or 0) >= render_index),
                  default=float("inf"))
    above = [seg for track in tracks[position:] if track["type"] == "video" for seg in track["segments"]
             if render_index <= (seg.get("render_index") or 0) < ceiling]
    if any(seg["render_index"] == render_index for seg in above):
        for seg in above:
            seg["render_index"] += 1
    for track in tracks[position:]:
        for seg in track["segments"]:
            if (seg.get("track_render_index") or 0) >= position:
                seg["track_render_index"] = (seg.get("track_render_index") or 0) + 1
    track = new_track("video", 2)
    tracks.insert(position, track)
    return track


def track_for_layer(draft, layer, at_us=None, length_us=None):
    """The overlay track for `layer`, counting up from 1 = just above the main track, and how it was found:
    "existing", "new" (on top) or "inserted" (put in at that place). `layer` is a place in the stack, never "the
    Nth track whatever it holds": when that track already plays something between at_us and at_us + length_us, a
    new track goes in at that place and the tracks above move up one, because one CapCut track cannot hold two
    clips at the same moment. A draft with fewer overlay tracks than `layer` gets a new one on top."""
    stacked = _overlay_stack(draft)
    if len(stacked) < layer:
        track = new_track("video", 2)
        draft["tracks"].append(track)
        return track, "new"
    track = stacked[layer - 1]
    if at_us is None or not _busy(track, at_us, length_us):
        return track, "existing"
    below = stacked[layer - 2] if layer > 1 else main_track(draft)
    position = draft["tracks"].index(below) + 1 if below is not None else 0
    return _insert_track(draft, position), "inserted"


def free_layer(draft, at_us, length_us):
    """The lowest overlay layer with nothing on it between at_us and at_us + length_us. One CapCut track cannot
    hold two clips at the same moment, so a graphic that would land on top of another goes a layer up instead of
    being stacked onto the same track."""
    stacked = _overlay_stack(draft)
    for layer, track in enumerate(stacked, 1):
        if not _busy(track, at_us, length_us):
            return layer
    return len(stacked) + 1


def lay_graphic(draft, folder, media, at_us, layer, length_us=None):
    """Put one graphic file on the overlay track for `layer`, starting at `at_us`; its full length when
    `length_us` is None. `layer=None` takes the lowest layer that is free for the graphic's whole span; a given
    layer that is busy then gets a new track at that place (overlay_track). The clip takes the render_index and
    track_render_index its track already uses, so one track never mixes two. Returns (layer, how overlay_track
    found the track)."""
    if layer is not None and layer < 1:
        sys.exit(f"--layer counts up from 1 (just above the footage), not {layer}")
    local = media_into(folder, media)
    probed = probe_video(local)
    material_id = new_id()
    draft["materials"]["videos"].append(media_entry(material_id, local, probed))
    length = probed[2] if length_us is None else length_us
    segment = clip_segment(draft["materials"], material_id, 0, length, at_us)
    if layer is None:
        layer = free_layer(draft, at_us, length)
    track, how = track_for_layer(draft, layer, at_us, length)
    if track["segments"]:
        held = [(seg.get("render_index") or 0, seg.get("track_render_index") or 0) for seg in track["segments"]]
        segment["render_index"], segment["track_render_index"] = max(set(held), key=held.count)
    else:
        position = draft["tracks"].index(track)
        segment["render_index"] = _render_index_at(draft, position)
        segment["track_render_index"] = position
    track["segments"].append(segment)
    return layer, how


def layer_on(draft_name, media, at, layer=None, duration=None, force=False):
    """An alpha graphic (a ProRes 4444 .mov) laid over the cut, which is how step-3 graphics reach the timeline.
    `layer` None = the lowest layer free for its whole span."""
    shown_as = Path(media).name
    with building_on(draft_name) as (draft, folder):
        if not force and already_placed(draft, round(at * 1e6), file_name=shown_as):
            sys.exit(f"{shown_as} is already on the timeline at {at}s. Add --force to place a second copy.")
        layer, how = lay_graphic(draft, folder, media, round(at * 1e6), layer,
                                 round(duration * 1e6) if duration else None)
    said = f"overlay: {shown_as} at {at:.2f}s on layer {layer}"
    if how == "inserted":
        said += (f" (layer {layer} already had a clip playing then, so this one has a new track of its own there and "
                 "the layers above it moved up one)")
    return said


# ---- text, set in her style pack

TEXT_ROLES = ("caption", "headline", "thought", "takeover", "accent")      # packbuild's roles
TEXT_SHELL_FILES = ("text-look.json", "text-clip.json", "text-motion.json")


def active_pack(named=None):
    """The style pack text is set in: the one named for this call, else STYLE_PACK, else her saved default pack
    (product/creative-vault/user-style.json). None when there is none."""
    if named:
        return named
    if os.environ.get("STYLE_PACK", "").strip():
        return os.environ["STYLE_PACK"].strip()
    import user_style
    return user_style.default_pack(str(REPO / "product" / "creative-vault" / "user-style.json"))


def text_look(pack, role="caption"):
    """How text in `role` looks in `pack`, all from the pack: the font file (where CapCut can read it), size,
    fill (white; the accent role takes her accent color), letter case, height on the canvas, weight."""
    if role not in TEXT_ROLES:
        sys.exit(f"--role is one of {', '.join(TEXT_ROLES)}, not {role}")
    import packbuild                                    # loaded only here: it needs pillow, and only text uses it
    try:
        spec = packbuild.role(pack, role)
    except KeyError as why:
        sys.exit(why.args[0] if why.args else str(why))
    fill = (packbuild.accent_color(pack) if role == "accent" else packbuild.WHITE).lstrip("#")
    return {"pack": pack, "role": role, "font": spec["font_path"], "size": spec["size"],
            "rgb": tuple(int(fill[i:i + 2], 16) / 255 for i in (0, 2, 4)), "case": spec["case"], "y": spec["y"],
            "bold": spec["bold"]}


def text_shells():
    """A fresh copy of the blank text clip: the material, the clip, and its (empty) animation slot. Their keys
    are the ones CapCut writes for a text clip; every value that makes up a look is blank until text_look fills
    it (dev-tools/capcut-shells/make-shells.py writes them)."""
    missing = [name for name in TEXT_SHELL_FILES if not (TEXT_SHELLS / name).exists()]
    if missing:
        sys.exit(f"the blank text clip is incomplete: {', '.join(missing)} is missing from {TEXT_SHELLS}")
    return {name: json.loads((TEXT_SHELLS / name).read_text(encoding="utf-8")) for name in TEXT_SHELL_FILES}


def lay_text(draft, shown, at_us, length_us, look, shells=None):
    """One text clip reading `shown`, in `look`, from at_us for length_us. It goes on the first text track with
    nothing on it then; when every text track is busy, on a new one on top. Returns "existing", "first" (the
    draft's first text track) or "new" (every other text track shows text then)."""
    import capcut_text
    shells = shells or text_shells()
    material = capcut_text.make_text_material(shells["text-look.json"], shown, look["font"], look["size"],
                                              look["rgb"])
    content = json.loads(material["content"])
    for run in content["styles"]:
        run["bold"] = look["bold"]
    material.update(id=new_id(), content=json.dumps(content, ensure_ascii=False))
    slot = dict(shells["text-motion.json"], id=new_id())
    clip = shells["text-clip.json"]
    clip.update(id=new_id(), material_id=material["id"], extra_material_refs=[slot["id"]],
                target_timerange={"start": at_us, "duration": length_us})
    clip["clip"]["transform"]["y"] = look["y"]
    draft["materials"].setdefault("texts", []).append(material)
    draft["materials"].setdefault("material_animations", []).append(slot)
    track = next((track for track in draft["tracks"] if track["type"] == "text"
                  and not _busy(track, at_us, length_us)), None)
    how = "existing"
    if track is None:
        how = "new" if any(track["type"] == "text" for track in draft["tracks"]) else "first"
        track = new_track("text", 1)
        draft["tracks"].append(track)
    clip["track_render_index"] = draft["tracks"].index(track)
    track["segments"].append(clip)
    return how


def text_on(draft_name, text, at, duration=3.0, force=False, pack=None, role="caption"):
    """Text on the timeline in her style pack: the pack's font, size, color and letter case for `role`, at the
    pack's height for it. With no pack named or saved it stops and asks, before CapCut is touched."""
    shells = text_shells()
    chosen = active_pack(pack)
    if not chosen:
        import stylepack
        sys.exit(f"Which style pack is this text in? Add --pack <name> ({', '.join(stylepack.names())}), or save "
                 f"her default pack first. Text is only ever set in a pack's fonts.")
    look = text_look(chosen, role)
    import packbuild
    # The reel's language, from the job the draft was built for (<job> 1.2 -> projects/<job>): on a reel that is not
    # in English a lowercase pack keeps her capitals, the same as every builder (lowercase misspells German nouns).
    lang, jd = None, None
    try:
        import draft_safety, stylepack
        job_dir = REPO / "projects" / draft_safety.base_of(draft_name)
        jd = str(job_dir) if job_dir.is_dir() else None
        lang = stylepack.job_language(jd) if jd else None
    except Exception:
        lang = None
    shown = packbuild.caseit(text, look["case"], lang=lang, job_dir=jd)   # her brand spellings keep their capitals too
    at_us, length_us = round(at * 1e6), round(duration * 1e6)
    with building_on(draft_name) as (draft, _):
        if not force and already_placed(draft, at_us, text=shown):
            sys.exit(f"{shown!r} already starts at {at}s in {draft_name}. --force places it a second time.")
        how = lay_text(draft, shown, at_us, length_us, look, shells)
    said = f"text in {chosen} ({role}): {shown!r} from {at:.2f}s to {at + duration:.2f}s"
    return said + (" on a new text track (the others show text then)" if how == "new" else "")


def take_out(draft_name, role, index):
    """Take one clip out, plus any video or text material nothing plays any more. The closed-CapCut twin of the driven
    `delete`: the one to use when the removal must be exact, or when there are many. `role` is a --track word, and
    the messages say it back the way she wrote it."""
    kind = TRACK_WORDS[role]                             # an unknown word stops here, before CapCut is touched
    with building_on(draft_name) as (draft, _):
        # Overlapping clips of one role sit on separate tracks, so --index counts that role's clips across all
        # of its tracks, in track order.
        slots = [(track, i) for track in role_tracks(draft, kind) for i in range(len(track["segments"]))]
        if index >= len(slots):
            sys.exit(f"there is no {role} segment {index}: the draft holds {len(slots)}")
        track, position = slots[index]
        del track["segments"][position]
        playing = {seg["material_id"] for other in draft["tracks"] for seg in other["segments"]}
        for pool in ("videos", "texts"):
            draft["materials"][pool] = [entry for entry in draft["materials"][pool] if entry["id"] in playing]
        if kind != "main" and not track["segments"]:
            draft["tracks"].remove(track)
    return f"removed {role}[{index}]"


def move_clip(draft_name, role, index, scale=None, x=None, y=None, rotation=None, opacity=None):
    """Scale, position, rotation and opacity of one clip, written into the draft exactly with CapCut closed
    (CapCut's inspector fields do not take synthesized keystrokes). x and y are CapCut's own units, half the
    canvas per 1.0 with up positive, so y=-0.25 moves the clip down an eighth of the frame; scale is a plain
    multiplier."""
    kind = TRACK_WORDS[role]                             # an unknown word stops here, before CapCut is touched
    with building_on(draft_name) as (draft, _):
        tracks = role_tracks(draft, kind)
        if not tracks:
            sys.exit(f"no {role} track in this draft")
        segments = tracks[0]["segments"]
        if index >= len(segments):
            sys.exit(f"{role} track has {len(segments)} segments, no index {index}")
        segment = segments[index]
        clip = segment["clip"]
        if scale is not None:
            clip["scale"] = {"x": scale, "y": scale}
            segment["uniform_scale"] = {"on": True, "value": scale}
        if x is not None:
            clip["transform"]["x"] = x
        if y is not None:
            clip["transform"]["y"] = y
        if rotation is not None:
            clip["rotation"] = rotation
        if opacity is not None:
            clip["alpha"] = opacity
    asked = {"scale": scale, "x": x, "y": y, "rotation": rotation, "opacity": opacity}
    applied = {field: value for field, value in asked.items() if value is not None}
    return f"{role}[{index}] move: {applied}"


def planned_graphics(job_dir):
    """Every graphic a job's plan puts on screen, in plan order, as (rendered file name, start in seconds). A
    beat counts unless it stays on her face (`element: "face"`). Its file is the beat's `file`, else <id>.mov;
    its start is `start`. Older plans list `graphics` rather than `beats` and may give the start as `t` or `time`."""
    plan = json.loads((job_dir / "graphics-plan.json").read_text(encoding="utf-8"))
    for beat in plan.get("beats") or plan.get("graphics") or []:
        if beat.get("element") == "face" or beat.get("graphic") is False:
            continue
        name = beat.get("file") or (f"{beat['id']}.mov" if beat.get("id") else None)
        start = next((beat[key] for key in ("start", "t", "time") if beat.get(key) is not None), None)
        if name and start is not None:                   # a start of 0 is a start
            yield name, float(start)


def place_plan(draft_name, job):
    """Every rendered graphic in a job's graphics plan, laid on the draft in one write (CapCut rebuilds its
    caches once, not once per graphic), each on the lowest layer free for its whole length."""
    job_dir = REPO / "projects" / job
    if not (job_dir / "graphics-plan.json").exists():
        sys.exit(f"{job} has no graphics plan yet ({job_dir / 'graphics-plan.json'}). Make the creative plan first.")
    import plan_language                                 # her card copy in her language: a warning, never a stop
    plan_language.warn(str(job_dir))
    ready, waiting = [], []
    for name, start in planned_graphics(job_dir):
        (ready if (job_dir / "assets" / name).exists() else waiting).append((name, start))
    for name, start in waiting:
        print(f"  {name} ({start:g}s) is not rendered yet; the next place-plan picks it up")
    if not ready:
        sys.exit(f"none of the graphics in {job}'s plan are rendered yet" if waiting
                 else f"{job}'s plan has no graphics to place")
    with building_on(draft_name) as (draft, folder):
        layers = [lay_graphic(draft, folder, job_dir / "assets" / name, round(start * 1e6), None)[0]
                  for name, start in ready]
    said = f"{len(ready)} graphic(s) from {job}'s plan on {draft_name}, layer(s) {', '.join(map(str, sorted(set(layers))))}"
    return said + (f"; {len(waiting)} not rendered yet" if waiting else "")


# ---- a second camera as a picture-in-picture

PIP_SCALE = 0.9            # the most of the frame's width a PIP takes, so it never touches the frame's edge
PIP_MIN_US = 250_000       # a stretch the second camera covers for less than this gets no PIP clip
PIP_DIR = Path("assets") / "pip"


def synced_clip(material, offsets):
    """The main clip a footage material plays, by file name, when the second camera covers it. A copy that took
    the next free name inside the draft (stem-2.mp4, media_slot) still counts as its clip."""
    if material is None:
        return None
    name = Path(material["path"]).name
    if name in offsets:
        return name
    stem, ext = os.path.splitext(name)
    base = stem.rsplit("-", 1)[0] + ext if stem.rsplit("-", 1)[-1].isdigit() else None
    return base if base in offsets else None


def pip_mic(report, clip, start_s, end_s):
    """Whose mic carries this stretch of `clip`: "pip" or "main", from the mic-report line it overlaps most. The
    lines are matched by source time, not by place in the cut list, so a draft she trimmed still finds its own."""
    best, most = None, 0.0
    for row in (report or {}).get("lines", []):
        if row.get("clip") != clip:
            continue
        overlap = min(row["end"], end_s) - max(row["start"], start_s)
        if overlap > most:
            best, most = row, overlap
    return (best or {}).get("mic", "main")


def pip_placement(zones, canvas, shown_size, scale=None):
    """(scale, transform_y, band) for the PIP: centred in the open band below her, or above her when only that one
    has room, and as large as fits that band up to PIP_SCALE. CapCut fits a clip into the canvas at scale 1, so the
    PIP's height on screen is its fitted height times the scale; the bands are measured in subject-zones' 1080x1920
    authoring frame. None when neither band is usable."""
    for band in ("below", "above"):
        zone = (zones.get("zones") or {}).get(band) or {}
        if zone.get("usable") and zone.get("center_y_norm") is not None:
            break
    else:
        return None
    width, height = shown_size
    fitted_height = height * min(canvas[0] / width, canvas[1] / height) / canvas[1]
    room = zone["room_px"] / 1920
    if scale is None:
        scale = min(PIP_SCALE, room / fitted_height)
    return round(scale, 4), zone["center_y_norm"], band


def lay_pip(draft_name, job, scale=None):
    """Her second camera (synced by product/sync_camera.py) as a picture-in-picture: one clip over every footage
    clip that comes from a synced main clip, on its own track just above her footage (so the graphics stay on top),
    playing the same moment (source = her clip's source + the clip's offset) for the same length at the same place.
    Built from the footage track as it stands, so a draft she trimmed by hand stays frame-matched. Sound follows
    the mic report: where the second camera's mic carries a line, its clip plays and hers goes quiet; everywhere
    else the PIP is muted."""
    job_dir = REPO / "projects" / job
    pip_dir = job_dir / PIP_DIR
    sync_file = pip_dir / "sync.json"
    if not sync_file.exists():
        sys.exit(f"this job's second camera is not synced yet. Run: uv run product/sync_camera.py {job} "
                 "<second-camera file>")
    sync = json.loads(sync_file.read_text(encoding="utf-8"))
    offsets = {clip: offset for clip, offset in sync["offsets"].items() if offset is not None}
    if not offsets:
        sys.exit("none of her clips is synced to the second camera (every offset in sync.json is null). Nothing written.")
    report_file = pip_dir / "mic-report.json"
    report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else None
    zones_file = job_dir / "subject-zones.json"
    if not zones_file.exists():
        sys.exit(f"the PIP's place comes from her footage, and this job has no subject-zones.json yet. Run: "
                 f"uv run workflows/subject-zones.py projects/{job}/outputs/{job}.mp4")
    zones = json.loads(zones_file.read_text(encoding="utf-8"))
    pip_file = pip_dir / sync["pip"]

    with building_on(draft_name) as (draft, folder):
        if any(Path(v["path"]).name == pip_file.name for v in draft["materials"]["videos"]):
            sys.exit(f"{pip_file.name} is already in this draft. Nothing written.")
        main = main_track(draft)
        if main is None:
            sys.exit("this draft has no footage track. Nothing written.")
        materials = {entry["id"]: entry for entry in draft["materials"]["videos"]}
        local = media_into(folder, pip_file)
        probed = probe_video(local)
        shown = probed[:2] if source_rotation(local) % 180 == 0 else (probed[1], probed[0])
        canvas = (draft["canvas_config"]["width"], draft["canvas_config"]["height"])
        placed_at = pip_placement(zones, canvas, shown, scale)
        if placed_at is None:
            sys.exit("there is no open band above or below her in this framing (subject-zones.json), so a PIP would "
                     "sit on her. Give a size with --scale and move it in CapCut, or reframe. Nothing written.")
        scale, y, band = placed_at

        laid, partial, sped = [], 0, 0
        for seg in sorted(main["segments"], key=lambda s: s["target_timerange"]["start"]):
            clip = synced_clip(materials.get(seg["material_id"]), offsets)
            if clip is None:
                continue
            if abs((seg.get("speed") or 1.0) - 1.0) > 1e-6:
                sped += 1                                # a sped-up clip would need the PIP sped to match
                continue
            source, length = seg["source_timerange"]["start"], seg["target_timerange"]["duration"]
            pip_at = source + round(offsets[clip] * 1e6)
            first, last = max(pip_at, 0), min(pip_at + length, probed[2])
            if last - first < PIP_MIN_US:
                continue
            partial += (first, last) != (pip_at, pip_at + length)
            mic = pip_mic(report, clip, source / 1e6, (source + length) / 1e6)
            laid.append((seg, first, last - first, seg["target_timerange"]["start"] + first - pip_at, mic))
        if not laid:
            sys.exit("no clip on her footage track comes from a moment the second camera filmed. Nothing written.")

        material_id = new_id()
        draft["materials"]["videos"].append(media_entry(material_id, local, probed))
        position = draft["tracks"].index(main) + 1
        pip_track = _insert_track(draft, position)
        render_index = _render_index_at(draft, position)
        heard = 0
        for seg, source, length, at, mic in laid:
            pip = clip_segment(draft["materials"], material_id, source, length, at)
            pip["clip"]["scale"] = {"x": scale, "y": scale}
            pip["uniform_scale"] = {"on": True, "value": scale}
            pip["clip"]["transform"]["y"] = y
            pip["render_index"], pip["track_render_index"] = render_index, position
            pip["volume"] = 1.0 if mic == "pip" else 0.0
            if mic == "pip":
                seg["last_nonzero_volume"] = seg.get("volume") or seg.get("last_nonzero_volume") or 1.0
                seg["volume"] = 0.0
                heard += 1
            pip_track["segments"].append(pip)

    said = (f"second camera: {len(laid)} clip(s) on their own layer just above her footage, {scale:.0%} size, "
            f"centred in the open band {band} her (transform_y {y}); its mic carries {heard} of them")
    if report is None:
        said += ". There is no mic report, so her mic carries every line"
    if partial:
        said += f". {partial} clip(s) reach outside the second camera's recording, so their PIP covers only part"
    if sped:
        said += f". {sped} sped-up clip(s) got no PIP (it would play out of step)"
    return said


# ============================================================ 4. driving the open app (Mac)
#
# THE LIVE MAP: every CapCut-specific id the live commands depend on, and nothing else. No distance on screen is
# stored: every place clicked is read off CapCut's own boxes, and how long a step waits is not CapCut-specific
# either (see until() at the top). The ids were read off CapCut 9.5.0 itself on
# 2026-10-07 (home screen, editor, export dialog): every id below is present there. The export dialog's own
# controls are pressed by their ids; a CapCut that shows them under other names stops the export with a pointer
# to `ids --map`, rather than clicking where a control might be. `ids --map` reads the running CapCut and says
# which ids it still answers to, at what depth, and what to look at next. A value measured on her machine can be
# tried without touching this file: _local/capcut-live-map.json, e.g. {"export_ok": "<new label>"}.
#
# Every live command reads CapCut through macOS accessibility, which works only once the app Claude runs in has
# Accessibility permission (System Settings > Privacy & Security > Accessibility). Without it CapCut reads as
# empty, so capcut_root() checks first and says that, instead of reporting a draft or button as missing.

LIVE_IDS = {                       # what a command looks for -> the label CapCut gives it (title or description)
    "draft_title": "HomePageDraftTitle:",    # followed by the draft's name, one per tile on the home screen
    "draft_tile": "HomePageDraft",           # the tile the double-click opens
    "editor": "MainTimeLineRoot",            # present once the editor is open
    "export_button": "MainWindowTitleBarExportBtn",
    "playhead": "currentProgress",           # its description ends in |HH:MM:SS:FF
    "length": "totalProgress",
    "clip": "MTLSVideoP",                    # one per clip on the timeline
    "split": "cutoff", "trim_left": "cutLeft", "trim_right": "cutRight", "delete": "del",
    "undo": "undo", "redo": "redo", "marker": "mark", "fit": "quicklyAdjustZoomFit",
    "play": "PlayerPlayBtn", "pause": "PlayerPauseBtn",
    "export_ok": "ExportOkBtn",              # the export dialog's Export button
    "sync_toggle": "automationbackupCheckBox",   # the dialog's "sync exported videos to space" checkbox
    "export_cancel": "automationcancel",     # the dialog's Cancel button
    "window": "CapCut",                      # the main window's title
}
TOOLBAR = ("undo", "redo", "split", "trim_left", "trim_right", "delete", "marker", "fit")   # the timeline's buttons
LIVE_GEOMETRY = {
    "ruler_probes": [0.2, 0.6],               # where along the clips (as shares of their span) the ruler is clicked
}
LIVE_WALK = {
    # The most elements one reading walks. CapCut 9.5.0 showed 83 labelled elements in its editor window and 27
    # on its home screen; fifty editors' worth leaves room for the unlabelled containers around each one and a
    # timeline many times longer, and still ends a walk over a tree that never does (a runaway list).
    "walk_budget": 50 * 83,
}


def _apply_local_map():
    """Values from _local/capcut-live-map.json over the live map above and the wait limits."""
    try:
        local = json.loads((REPO / "_local" / "capcut-live-map.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        local = {}
    for table in (LIVE_IDS, LIVE_GEOMETRY, LIVE_WALK, LIVE_LIMITS):
        table.update({key: value for key, value in (local if isinstance(local, dict) else {}).items()
                      if key in table})


_apply_local_map()


# ApplicationServices and Quartz are macOS frameworks, loaded on the Mac only so the closed-CapCut half of this
# file (the half a PC needs) still loads on Windows. There every accessibility and input call is a stand-in
# that stops with a plain message about what does work.
if not ON_WINDOWS:
    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateApplication,  # noqa: E402
                                     AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType)
    try:
        from ApplicationServices import AXIsProcessTrusted  # noqa: E402
    except ImportError:                 # a build of the framework without it: let the reads speak for themselves
        def AXIsProcessTrusted():
            return True
    from Quartz import (CGEventCreateKeyboardEvent, CGEventCreateMouseEvent, CGEventPost,  # noqa: E402
                        CGEventSetFlags, CGEventSetIntegerValueField, kCGEventFlagMaskCommand,
                        kCGEventFlagMaskShift, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventMouseMoved,
                        kCGHIDEventTap, kCGMouseButtonLeft, kCGMouseEventClickState)
else:
    def _mac_only(*_args, **_kwargs):
        sys.exit("Driving the CapCut window directly is macOS only. Building and handing over a draft "
                 "works on this computer, so use that instead.")
    AXUIElementCreateApplication = AXUIElementCopyAttributeValue = AXValueGetValue = _mac_only
    AXIsProcessTrusted = _mac_only
    kAXValueCGPointType = kAXValueCGSizeType = None
    CGEventCreateKeyboardEvent = CGEventCreateMouseEvent = CGEventPost = _mac_only
    CGEventSetFlags = CGEventSetIntegerValueField = _mac_only
    kCGEventFlagMaskCommand = kCGEventFlagMaskShift = 0          # read before the first event is made
    kCGEventLeftMouseDown = kCGEventLeftMouseUp = kCGEventMouseMoved = None
    kCGHIDEventTap = kCGMouseButtonLeft = kCGMouseEventClickState = None


# macOS virtual key codes for the keys the live commands send.
KEYCODES = {"a": 0, "s": 1, "z": 6, "c": 8, "v": 9, "b": 11,
            "return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53,
            "left": 123, "right": 124, "down": 125, "up": 126}


# ---- reading CapCut's windows

def capcut_root():
    pid = capcut_process()
    if pid is None:
        sys.exit("CapCut is not open. Start it first with: start")
    if not AXIsProcessTrusted():
        sys.exit("This Mac has not given the app Claude runs in permission to read CapCut's window, so CapCut "
                 "looks empty from here. Open System Settings > Privacy & Security > Accessibility, switch it on "
                 "for that app (Claude, or Terminal if you run Claude there), then quit and reopen that app. "
                 "Building drafts with CapCut closed does not need this.")
    return AXUIElementCreateApplication(pid)


def ax(element, attribute):
    """One accessibility attribute, or None when the element does not carry it."""
    status, value = AXUIElementCopyAttributeValue(element, attribute, None)
    return value if status == 0 else None


class Seen:
    """One labelled element from a walk: its label, how deep it sat, and the nearest labelled element it sits
    inside (`holder`). Its box on screen, (x, y, width, height) or None, is read the first time it is asked for."""
    __slots__ = ("element", "label", "depth", "holder", "_box")

    def __init__(self, element, label, depth, holder):
        self.element, self.label, self.depth, self.holder, self._box = element, label, depth, holder, False

    @property
    def box(self):
        if self._box is False:
            has_origin, origin = AXValueGetValue(ax(self.element, "AXPosition"), kAXValueCGPointType, None)
            has_size, size = AXValueGetValue(ax(self.element, "AXSize"), kAXValueCGSizeType, None)
            self._box = (origin.x, origin.y, size.width, size.height) if has_origin and has_size else None
        return self._box

    @property
    def centre(self):
        x, y, width, height = self.box
        return x + width / 2, y + height / 2


class Screen:
    """One reading of every CapCut window: each element with a label, breadth first (the window, then what is
    directly inside it, and so on down), with the nearest labelled element it sits inside. The walk goes as deep
    as the tree does, up to WALK_BUDGET elements in all; `needs` (labels) ends it as soon as each has been met
    with a place on screen, which can only drop elements the walk would have met after those. `depth` caps the
    levels read, for `ids --depth` only. The box of every element whose label holds one of the live map's ids is
    read during the walk; any other box when asked."""

    def __init__(self, depth=None, needs=()):
        self.depth = depth
        self.seen, self.walked, self.deepest, self.cut_short = [], 0, 0, False
        self._known = [label.lower() for label in LIVE_IDS.values()]
        self._wanted = {needle.lower() for needle in needs}
        pending = deque((window, 0, None) for window in ax(capcut_root(), "AXWindows") or [])
        while pending and not (needs and not self._wanted):
            if self.walked >= LIVE_WALK["walk_budget"]:
                self.cut_short = True
                break
            element, level, holder = pending.popleft()
            self.walked += 1
            self.deepest = max(self.deepest, level)
            label = ax(element, "AXTitle") or ax(element, "AXDescription") or ""
            if label:
                holder = Seen(element, label, level, holder)
                self.seen.append(holder)
                lowered = label.lower()
                if any(known in lowered for known in self._known):
                    _ = holder.box
                met = {needle for needle in self._wanted if needle in lowered}
                if met and holder.box:
                    self._wanted -= met
            if self.depth is None or level < self.depth:
                pending.extend((child, level + 1, holder) for child in ax(element, "AXChildren") or [])

    def labelled(self, needle=None):
        """Every element whose label contains `needle` (any case); all of them with no needle."""
        if needle is None:
            return list(self.seen)
        wanted = needle.lower()
        return [seen for seen in self.seen if wanted in seen.label.lower()]

    def first(self, needle):
        """The first element labelled with `needle` that has a place on screen."""
        return next((seen for seen in self.labelled(needle) if seen.box), None)

    def part(self, key):
        """The first element on screen with the live map's id for `key` (a LIVE_IDS name)."""
        return self.first(LIVE_IDS[key])

    def draft_title(self, name):
        """The home-screen title of exactly this draft: the whole name, forgiving only letter case and spaces at
        the ends, so "Reel 1.1" never finds "Reel 1.12"."""
        wanted = LIVE_IDS["draft_title"] + name
        titles = [seen for seen in self.labelled(wanted) if seen.box]
        same = [seen for seen in titles if seen.label == wanted]
        return (same or [seen for seen in titles if seen.label.strip().lower() == wanted.strip().lower()]
                or [None])[0]

    def tile_of(self, title):
        """The tile a title sits inside (its nearest holder labelled as a tile), or None."""
        holder = title.holder
        while holder is not None and holder.label != LIVE_IDS["draft_tile"]:
            holder = holder.holder
        return holder if holder is not None and holder.box else None

    def clips(self):
        """Every clip on the timeline, main track and overlays together, top row first, left to right: the order
        `select` and `delete` count in."""
        placed = [seen for seen in self.labelled(LIVE_IDS["clip"]) if seen.box]
        return sorted(placed, key=lambda seen: (seen.box[1], seen.box[0]))

    def readout(self, key):
        """The timecode CapCut shows on its playhead or length readout ('?' when it is not on screen)."""
        shown = self.first(LIVE_IDS[key])
        return (ax(shown.element, "AXDescription") or "").split("|")[-1] if shown else "?"


def on_screen(find, limit, gone=None, needs=()):
    """Read CapCut's windows until `find(screen)` gives something (until() above, with a fresh Screen per
    check), and give that back. `needs`: the labels `find` looks up with first()/part(), so each reading can
    end as soon as it has met them."""
    return until(lambda: find(Screen(needs=needs)), limit, gone)


def held_still(find, limit, first=None):
    """Where `find(screen)` puts something, once two readings a poll apart agree, so a window or dialog still
    moving into place is clicked where it ends up. `first` is a reading the caller already has. Past `limit`,
    the last place read (None if it was never found)."""
    last = [first]
    if first is not None:
        time.sleep(POLL_SECONDS)                        # the next reading is one poll after the caller's

    def agrees(screen):
        now = find(screen)
        same = now is not None and now == last[0]
        if now is not None:
            last[0] = now
        return same
    until(lambda: agrees(Screen()), limit)
    return last[0]


# ---- her pointer and keys

def press(x, y, clicks=1):
    """Move to (x, y), then press and release `clicks` times. Each press carries its count, so a double-click
    reaches CapCut as one gesture."""
    point = (x, y)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, kCGMouseButtonLeft))
    time.sleep(INPUT_GAP)
    for count in range(1, clicks + 1):
        for phase in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
            event = CGEventCreateMouseEvent(None, phase, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event, kCGMouseEventClickState, count)
            CGEventPost(kCGHIDEventTap, event)
            time.sleep(INPUT_GAP)


def press_on(needle, clicks=1):
    """Click the middle of the first element labelled `needle`; the label it clicked comes back."""
    target = on_screen(lambda screen: screen.first(needle), LIVE_LIMITS["settle"],
                       gone=f"nothing on CapCut's screen is labelled {needle}", needs=(needle,))
    press(*target.centre, clicks)
    return target.label


_brought_forward = False


def capcut_in_front():
    """Is CapCut the frontmost app? An accessibility reading that does not carry the answer counts as yes:
    there is nothing to wait for then."""
    front = ax(capcut_root(), "AXFrontmost")
    return True if front is None else bool(front)


def bring_forward():
    """Keys go to the frontmost app, so CapCut is activated once per run before the first one, and the key waits
    until macOS has put it in front. Clicks land by position and need no activation."""
    global _brought_forward
    if not _brought_forward:
        tell_capcut("activate")
        if not ON_WINDOWS:                              # no keys are sent there: key() says it is Mac-only
            until(capcut_in_front, LIVE_LIMITS["load"],
                  gone="CapCut did not come to the front, so a key sent now would reach another app. Click on "
                       "CapCut's window once, then run this again.")
        _brought_forward = True


def key(combo):
    """Press a key such as 'space', 'escape' or 'cmd+shift+z'. cmd and shift are the modifiers it reads."""
    bring_forward()
    parts = combo.lower().split("+")
    if parts[-1] not in KEYCODES:
        sys.exit(f"'{parts[-1]}' is not a key this can press. It knows: {', '.join(sorted(KEYCODES))}")
    flags = (kCGEventFlagMaskCommand if "cmd" in parts else 0) | (kCGEventFlagMaskShift if "shift" in parts else 0)
    for down in (True, False):
        event = CGEventCreateKeyboardEvent(None, KEYCODES[parts[-1]], down)
        if flags:
            CGEventSetFlags(event, flags)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(INPUT_GAP)


# ---- the timeline ruler and the playhead

def seconds_from_timecode(stamp, fps):
    hours, minutes, seconds, frames = (int(part) for part in stamp.split(":"))
    return hours * 3600 + minutes * 60 + seconds + frames / fps


def draft_fps(name=None):
    """The frame rate the named draft was saved with, read from its file; 30.0 without one."""
    if name:
        try:
            return json.loads(Path(_ds.draft_json(str(DRAFTS / name))).read_text(encoding="utf-8"))["fps"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return 30.0


def playhead_at(fps):
    shown = Screen(needs=(LIVE_IDS["playhead"],)).readout("playhead")
    return None if shown == "?" else seconds_from_timecode(shown, fps)


def ruler_row(screen):
    """The height to click the ruler at, from CapCut's own boxes: the ruler is the band directly under the
    timeline's button row (TOOLBAR) and above the first track. The band is taken as one button tall and clicked
    through its middle; where a track starts sooner than that, through the middle of what is left. Only buttons
    level with the split (or undo) button count as the row, so a label elsewhere that shares an id never moves
    it. Ruler.learn checks the result: two clicks that leave the playhead where it was stop the command."""
    anchor = screen.part("split") or screen.part("undo")
    if anchor is None:
        sys.exit("there is no timeline toolbar on CapCut's screen. Open a draft first.")
    row = [button for button in (screen.part(key) for key in TOOLBAR) if button
           and button.box[1] <= anchor.box[1] + anchor.box[3] / 2 <= button.box[1] + button.box[3]]
    bottom = max(button.box[1] + button.box[3] for button in row)
    tall = sorted(button.box[3] for button in row)[len(row) // 2]
    band_ends = min([bottom + tall] + [clip.box[1] for clip in screen.clips() if clip.box[1] >= bottom])
    return (bottom + band_ends) / 2


class Ruler:
    """The ruler above the timeline, read through CapCut's own playhead readout. Its row is found from the
    toolbar's boxes on every click (ruler_row), and its scale is learned fresh each time from two clicks on it,
    so nothing is assumed about the zoom, the scroll position or where the timeline starts."""

    def __init__(self, fps):
        self.fps = fps

    def click(self, x):
        """Click the ruler at x, then wait for the playhead readout to leave where it was (a click on the spot
        it already marks leaves it there, and the settle limit ends the wait)."""
        screen = Screen()
        y = ruler_row(screen)
        was = screen.readout("playhead")
        press(x, y)
        on_screen(lambda now: now.readout("playhead") != was, LIVE_LIMITS["settle"],
                  needs=(LIVE_IDS["playhead"],))

    def learn(self):
        """Click the ruler at two points across the clips and read the playhead after each: the line through
        those two (x, seconds) pairs maps any time to an x."""
        clips = Screen().clips()
        if not clips:
            sys.exit("the timeline shows no clips, so there is nothing to read the ruler against")
        left = min(clip.box[0] for clip in clips)
        right = max(clip.box[0] + clip.box[2] for clip in clips)
        probes = []
        for share in LIVE_GEOMETRY["ruler_probes"]:
            x = left + (right - left) * share
            self.click(x)
            probes.append((x, playhead_at(self.fps)))
        (x0, t0), (x1, t1) = probes
        if t0 is None or t1 is None or abs(t1 - t0) < 1e-6:
            sys.exit("two clicks on the ruler left the playhead where it was, so the ruler could not be read. "
                     "Something may be covering it: `screenshot` shows what is on screen.")
        self.x0, self.t0, self.seconds_per_px = x0, t0, (t1 - t0) / (x1 - x0)
        return self

    def x_for(self, seconds):
        return self.x0 + (seconds - self.t0) / self.seconds_per_px


def park_playhead(seconds, fps=30.0, within_frames=0):
    """Put the playhead on one exact frame: a click where the ruler says that time is, then frame steps with the
    arrow keys for whatever is left. Steps go in rounds of one second of frames, and the playhead is read after
    each round once it shows where the round should have left it; it stops on the frame, or as soon as a round
    brings it no closer (CapCut not taking the steps), so no count of rounds is needed."""
    ruler = Ruler(fps).learn()
    ruler.click(ruler.x_for(seconds))
    per_round = max(1, round(fps))
    landed = playhead_at(fps)
    while landed is not None:
        frames_off = round((seconds - landed) * fps)
        if abs(frames_off) <= within_frames:
            return landed
        steps = min(abs(frames_off), per_round) * (1 if frames_off > 0 else -1)
        for _ in range(abs(steps)):
            key("right" if steps > 0 else "left")
        aim = round(landed * fps) + steps
        on_screen(lambda screen: screen.readout("playhead") != "?" and
                  round(seconds_from_timecode(screen.readout("playhead"), fps) * fps) == aim, LIVE_LIMITS["settle"],
                  needs=(LIVE_IDS["playhead"],))
        now = playhead_at(fps)
        if now is None or abs(round((seconds - now) * fps)) >= abs(frames_off):
            return now
        landed = now
    return landed


def pick_clip(index):
    """Click clip `index` (the numbering `clips` prints); its label comes back. CapCut handles input in the
    order it arrives, so whatever is pressed next lands on the clip this selected."""
    clips = Screen().clips()
    if index >= len(clips):
        sys.exit(f"the timeline shows {len(clips)} clips (0 to {len(clips) - 1}), so there is no clip {index}")
    press(*clips[index].centre)
    return clips[index].label


# ---- opening a draft and exporting it

def open_draft(name):
    """Open a draft from CapCut's home screen with a double-click on its tile, and wait for the editor.

    Each reading asks one question: is the editor up, or the home screen, and is this draft's tile on it? A
    CapCut showing neither within the settle limit has a panel over its home screen (or is still starting), so
    once its window is up Escape closes the panel and the wait goes on to the load limit. The tile is clicked
    where two readings agree, since the window can still be moving into place just after launch."""
    if capcut_process() is None:
        open_capcut()
    tell_capcut("activate")

    def spot(screen):
        title = screen.draft_title(name)
        if title is None:
            return None
        tile = screen.tile_of(title)
        return tile.centre if tile else "no tile"

    def look(screen):
        if screen.part("editor"):
            return "editor", None
        here = spot(screen)
        return ("home", here) if here or screen.part("draft_tile") else None
    shown = on_screen(look, LIVE_LIMITS["settle"])
    if shown is None:
        on_screen(lambda screen: screen.part("window"), LIVE_LIMITS["load"],
                  gone="CapCut is running but never showed its window")
        key("escape")                                   # a panel CapCut shows after launch can cover the home screen
        shown = on_screen(look, LIVE_LIMITS["load"]) or ("home", None)
    if shown[0] == "editor":
        sys.exit(f"CapCut is showing a draft's editor, not its home screen, so {name} can't be picked from it. "
                 f"Go back to the home screen, then run open again.")
    target = held_still(spot, LIVE_LIMITS["settle"], first=shown[1])
    if target is None:
        sys.exit(f"there is no draft called {name} on CapCut's home screen")
    if target == "no tile":
        sys.exit(f"{name} is on CapCut's home screen, but its title sits in no draft tile, so nothing was "
                 f"double-clicked. Run `ids --map` on the home screen to see what this CapCut calls its tiles.")
    press(*target, clicks=2)
    on_screen(lambda screen: screen.part("editor"), LIVE_LIMITS["load"],
              gone=f"'{name}' was double-clicked, but CapCut's editor did not open")
    print(f"'{name}' is open in CapCut's editor, {Screen().readout('length')} long")


def mp4s_in(folder):
    return {mp4: mp4.stat().st_mtime for mp4 in folder.glob("*.mp4")}


def wait_for_export(folder, before, timeout):
    """Watch `folder` for the export: the newest mp4 that is new or changed since `before`. It is done once it
    is above zero and has not grown for EXPORT_QUIET seconds (EXPORT_QUIET / POLL_SECONDS readings in a row).
    Returns (file or None, its size, done)."""
    seen = {"file": None, "size": -1, "since": None}

    def written():
        changed = [mp4 for mp4, stamp in mp4s_in(folder).items() if mp4 not in before or stamp > before[mp4]]
        if not changed:
            return False
        newest = max(changed, key=lambda mp4: mp4.stat().st_mtime)
        size = newest.stat().st_size
        if (newest, size) != (seen["file"], seen["size"]) or size == 0:
            seen.update(file=newest, size=size, since=time.time())
            return False
        return time.time() - seen["since"] >= EXPORT_QUIET
    done = bool(until(written, timeout))
    return seen["file"], seen["size"], done


DIALOG_UNREAD = ("CapCut's export dialog did not show its {what} ({id}) to accessibility, so {outcome}. With the "
                 "export dialog open, run `ids --map`: it lists what this CapCut calls the dialog's controls.")


def run_export(to=None, timeout=900, toggle_sync=False):
    """Export the open draft through CapCut's own export dialog, then wait for the file and report it.

    The dialog's own defaults are kept: the draft's name, into ~/Downloads unless --to names a folder. Its
    "sync exported videos" checkbox is left exactly as she last set it; --toggle-sync is the only thing that
    clicks it. Both controls are pressed by their ids (LIVE_IDS export_ok / sync_toggle), once the dialog has
    stopped moving; a dialog that does not show them stops the export with a pointer to `ids --map`."""
    folder = Path(to).expanduser() if to else Path.home() / "Downloads"
    before = mp4s_in(folder)
    key("escape")                                       # a share screen left by the last export blocks this one
    button = on_screen(lambda screen: screen.part("export_button"), LIVE_LIMITS["settle"],
                       gone="CapCut's Export button is not on screen. Open a draft first.",
                       needs=(LIVE_IDS["export_button"],))
    press(*button.centre)

    export_at = held_still(lambda screen: (lambda ok: ok.centre if ok else None)(screen.part("export_ok")),
                           LIVE_LIMITS["load"])
    if export_at is None:
        sys.exit(DIALOG_UNREAD.format(what="Export button", id=LIVE_IDS["export_ok"],
                                      outcome="the export was not started"))
    if toggle_sync:
        box = Screen().part("sync_toggle")
        if box is None:
            sys.exit(DIALOG_UNREAD.format(what="sync checkbox", id=LIVE_IDS["sync_toggle"],
                                          outcome="nothing was clicked and the export was not started"))
        was = ax(box.element, "AXValue")
        press(*box.centre)
        if was is not None:                             # a checkbox that reports its state: wait for it to flip
            on_screen(lambda screen: (lambda now: now is not None and ax(now.element, "AXValue") != was)(
                screen.part("sync_toggle")), LIVE_LIMITS["settle"])
    press(*export_at)

    landed, size, done = wait_for_export(folder, before, timeout)
    key("escape")                                       # leave the share screen; clicking through it posts the video
    if landed is None:
        sys.exit(f"no video reached {folder} from that export. CapCut's export dialog may still be open.")
    if not done:
        sys.exit(f"{landed} was still being written when the {timeout}s wait ended "
                 f"({max(size, 0) / 1048576:.1f} MB so far). Let CapCut finish, or run export again with a longer "
                 f"--timeout.")
    length = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                             str(landed)], capture_output=True, text=True).stdout.strip() or "?"
    print(f"exported {landed.name} into {landed.parent}: {size / 1048576:.1f} MB, {length} s long")
    return landed


# ============================================================ 5. reading what CapCut shows

def track_label(draft, track):
    """What `timeline` calls a track, in the words --track takes; a sound or effect track goes by its type."""
    if track["type"] == "video":
        return "footage" if track is main_track(draft) else "overlay"
    return track["type"]


def clip_shows(draft, clip):
    """What a clip plays: its media file's name, or its text on one line."""
    material = _pooled(draft, "videos", clip["material_id"])
    if material is not None:
        return material["material_name"]
    material = _pooled(draft, "texts", clip["material_id"])
    if material is None:
        return "?"
    return " / ".join(json.loads(material["content"]).get("text", "").splitlines())


def as_seconds(us):
    return round(us / 1e6, 3)


def timeline_report(name=None):
    """What CapCut shows, next to what the named draft's file holds. The clip times come from the file, because
    that is what CapCut plays and exports. An edit made in the app reaches the file only when CapCut saves, so
    when the app shows a different number of clips than the file holds, the difference is unsaved work."""
    screen = Screen()
    showing = len(screen.clips())
    report = {"draft": name, "in_app": {"playhead": screen.readout("playhead"), "length": screen.readout("length"),
                                        "clips_showing": showing}}
    file = Path(_ds.draft_json(str(DRAFTS / name))) if name else None
    if file and file.exists():
        draft = json.loads(file.read_text(encoding="utf-8"))
        report["in_file"] = {"length_s": as_seconds(draft["duration"]), "tracks": [
            {"track": number, "holds": track_label(draft, track), "clips": [
                {"clip": i, "plays": clip_shows(draft, clip), "at_s": as_seconds(clip["target_timerange"]["start"]),
                 "for_s": as_seconds(clip["target_timerange"]["duration"]),
                 # a text clip CapCut has saved has no source range
                 "from_source_s": as_seconds(clip["source_timerange"]["start"]) if clip.get("source_timerange") else None}
                for i, clip in enumerate(track["segments"])]}
            for number, track in enumerate(draft["tracks"])]}
        in_file = sum(len(track["segments"]) for track in draft["tracks"] if track["type"] == "video")
        report["saved"] = in_file == showing
        if not report["saved"]:
            report["unsaved"] = (f"CapCut shows {showing} clips and the file holds {in_file}: save in CapCut "
                                 f"(cmd+s) before trusting these times")
    print(json.dumps(report, indent=1, ensure_ascii=False))


def list_clips():
    clips = Screen().clips()
    for number, clip in enumerate(clips):
        x, y, width, height = clip.box
        print(f"{number:>3}  {clip.label}  at {x:.0f},{y:.0f}  {width:.0f}x{height:.0f}")
    print(f"{len(clips)} clips showing (the number on the left is what select and delete take)")


def capture_window(destination):
    """A picture of CapCut's largest on-screen window (the first of two the same size), for checking where a
    graphic landed. screencapture takes the window server's number for that window."""
    if ON_WINDOWS:
        _mac_only()
    from Quartz import CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListOptionOnScreenOnly
    windows = [window for window in CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
               if window.get("kCGWindowOwnerName") == APP_NAME]
    if not windows:
        sys.exit("CapCut has no window on screen to capture")
    area = [window["kCGWindowBounds"]["Width"] * window["kCGWindowBounds"]["Height"] for window in windows]
    largest = windows[area.index(max(area))]
    picture = Path(destination).expanduser().resolve()
    subprocess.run(["screencapture", "-x", "-o", "-l", str(largest["kCGWindowNumber"]), str(picture)], check=True)
    return picture


# ---- re-mapping after a CapCut update (read only: nothing is clicked or pressed)

HOME_PARTS = ("draft_title", "draft_tile")
DIALOG_PARTS = ("export_ok", "sync_toggle", "export_cancel")      # shown only while the export dialog is open
SHOWN_ONE_AT_A_TIME = {"play": "pause", "pause": "play"}     # the transport button is one or the other


def _words(label):
    """The words in an id ('MainWindowTitleBarExportBtn' -> main, window, title, bar, export, btn)."""
    import re
    return {word.lower() for word in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", label) if len(word) >= 3}


def print_ids(needle=None, depth=None):
    """Every labelled element on screen, with the level it sits at and its box."""
    for seen in Screen(depth).labelled(needle):
        box = seen.box
        where = f"  {box[0]:.0f},{box[1]:.0f} {box[2]:.0f}x{box[3]:.0f}" if box else ""
        print(f"{seen.depth:>3}  {seen.label}{where}")


def map_report(depth=None, save=None):
    """Which of the live map's ids the running CapCut answers to: each one found, with the level it sits at (for
    diagnosis; the walk itself has no depth limit), or missing (renamed, or not on this screen), with the labels
    that look like it. --depth N flags ids that sit below level N. Ends with the next thing to look at."""
    deep = Screen()
    found = {name: [seen for seen in deep.labelled(label) if seen.box] for name, label in LIVE_IDS.items()}
    on_home = any(found[name] for name in HOME_PARTS)
    on_dialog = any(found[name] for name in DIALOG_PARTS)
    on_editor = any(found[name] for name in ("editor", "clip", "playhead", "export_button"))
    where = ("export dialog" if on_dialog else "home screen" if on_home else "editor" if on_editor
             else "neither the home screen nor the editor")
    print(f"CapCut {installed_capcut_version() or '(version not readable)'}, {where}: {deep.walked} elements, "
          f"down to level {deep.deepest}")
    if deep.cut_short:
        print(f"  the walk stopped at its budget of {LIVE_WALK['walk_budget']} elements: try a larger walk_budget "
              f"in _local/capcut-live-map.json")
    expected = (DIALOG_PARTS if on_dialog else HOME_PARTS if on_home
                else tuple(name for name in LIVE_IDS if name not in HOME_PARTS + DIALOG_PARTS))
    missing = []
    for name in expected:
        hits = found[name]
        twin = SHOWN_ONE_AT_A_TIME.get(name)
        if not hits and twin and found[twin]:
            continue                                    # play and pause swap places; one showing is right
        level = min((seen.depth for seen in hits), default=None)
        if hits and (depth is None or level <= depth):
            print(f"  found    {name:<14} {LIVE_IDS[name]}  level {level}, {len(hits)} on screen")
        elif hits:
            print(f"  below    {name:<14} {LIVE_IDS[name]}  level {level}, under the --depth {depth} asked for")
        else:
            print(f"  missing  {name:<14} {LIVE_IDS[name]}  in all {deep.walked} elements read")
            missing.append(name)
    known = {seen.label for hits in found.values() for seen in hits}
    for name in missing:
        words = _words(LIVE_IDS[name])
        alike = sorted(((len(words & _words(seen.label)), seen) for seen in deep.seen
                        if seen.label not in known and words & _words(seen.label)),
                       key=lambda pair: (-pair[0], pair[1].depth))[:5]
        for _, seen in alike:
            print(f"    like {name}: {seen.label}  level {seen.depth}")
    if on_dialog:
        print("next: close the export dialog with its Cancel button; every screen the live commands use is checked")
    elif on_home:
        print("next: open a draft in CapCut yourself (any one you can spare), then run `ids --map` again in the editor")
    elif on_editor:
        print("next: open the export dialog by hand (CapCut's Export button), then run `ids --map` again to check "
              "the dialog's own controls")
    if save:
        Path(save).expanduser().write_text(json.dumps({
            "capcut": installed_capcut_version(), "screen": where, "walked": deep.walked,
            "walk_budget": LIVE_WALK["walk_budget"],
            "elements": [{"label": seen.label, "level": seen.depth, "box": seen.box,
                          "inside": seen.holder.label if seen.holder else None} for seen in deep.seen]},
            indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"saved every labelled element to {save}")


# ============================================================ the command line
# Each handler takes the words after the command's name. What it returns is the line the command ends on;
# handlers that print as they go return nothing.

def value_after(args, name, cast=str, default=None):
    """The value after `name` in args, cast; `default` (as given, never cast) when the flag is absent."""
    if name not in args:
        return default
    return cast(args[args.index(name) + 1])


def first_word(args):
    """The first word that is not a flag or a flag's value, or None."""
    skip = False
    for word in args:
        if skip:
            skip = False
        elif word.startswith("--"):
            skip = word not in ("--map", "--force", "--toggle-sync")
        else:
            return word
    return None


COMMANDS = {}


def command(name):
    def register(handler):
        COMMANDS[name] = handler
        return handler
    return register


# ---- 2 and 3: CapCut closed

@command("new-draft")
def _new_draft(args):
    new_draft(args[0], value_after(args, "--name"))


@command("drafts")
def _drafts(args):
    registry = json.loads((DRAFTS / "root_meta_info.json").read_text(encoding="utf-8"))
    for row in registry["all_draft_store"]:
        print(f"{row['draft_name']} — {row['tm_duration'] / 1e6:.2f}s — {row['draft_fold_path']}")


@command("place-plan")
def _place_plan(args):
    return place_plan(args[0], args[1])


@command("pip")
def _pip(args):
    return lay_pip(args[0], args[1], value_after(args, "--scale", float))


@command("layer")
def _layer(args):
    return layer_on(args[0], args[1], value_after(args, "--at", float, 0.0), value_after(args, "--layer", int),
                    value_after(args, "--dur", float), force="--force" in args)


@command("text")
def _text(args):
    return text_on(args[0], args[1], value_after(args, "--at", float, 0.0), value_after(args, "--dur", float, 3.0),
                   force="--force" in args, pack=value_after(args, "--pack"),
                   role=value_after(args, "--role", str, "caption"))


@command("move")
def _move(args):
    return move_clip(args[0], value_after(args, "--track", str, "footage"), value_after(args, "--index", int, 0),
                     scale=value_after(args, "--scale", float), x=value_after(args, "--x", float),
                     y=value_after(args, "--y", float), rotation=value_after(args, "--rotate", float),
                     opacity=value_after(args, "--opacity", float))


@command("remove")
def _remove(args):
    return take_out(args[0], value_after(args, "--track", str, "footage"), value_after(args, "--index", int, 0))


@command("fix-magnet")
def _fix_magnet(args):
    fix_magnet(args[0])


@command("check-magnet")
def _check_magnet(args):
    check_magnet(args[0])


# ---- 4: driving the open app

@command("start")
def _start(args):
    open_capcut()


@command("open")
def _open(args):
    open_draft(args[0])


@command("quit")
def _quit(args):
    close_capcut()


@command("go-to")
def _go_to(args):
    wanted = float(args[0])
    landed = park_playhead(wanted, draft_fps(value_after(args, "--draft")))
    return f"playhead on {landed:.3f}s (asked for {wanted:.3f}s)"


@command("select")
def _select(args):
    return f"selected clip {args[0]}: {pick_clip(int(args[0]))}"


@command("delete")
def _delete(args):
    pick_clip(int(args[0]))
    press_on(LIVE_IDS["delete"])
    return f"deleted clip {args[0]}"


@command("split")
def _split(args):
    if args and not args[0].startswith("--"):          # a leading time means "go there first"; -- starts a flag
        park_playhead(float(args[0]), draft_fps(value_after(args, "--draft")))
    press_on(LIVE_IDS["split"])
    return "split at the playhead"


def _toolbar(part, said):
    def handler(args):
        press_on(LIVE_IDS[part])
        return said
    return handler


COMMANDS.update({"trim-left": _toolbar("trim_left", "trimmed left of the playhead"),
                 "trim-right": _toolbar("trim_right", "trimmed right of the playhead"),
                 "undo": _toolbar("undo", "undone"), "redo": _toolbar("redo", "redone"),
                 "marker": _toolbar("marker", "marker added at the playhead"),
                 "fit-timeline": _toolbar("fit", "timeline zoomed to fit")})


def draft_written_since(moment):
    """Has CapCut written any draft's timeline file (top level or Timelines/) since `moment`?"""
    for timeline in _ds.draft_jsons_under(str(DRAFTS), "*") + _ds.draft_jsons_under(str(DRAFTS), "*/Timelines/*"):
        try:
            if os.stat(timeline).st_mtime >= moment:
                return True
        except OSError:
            pass
    return False


@command("save")
def _save(args):
    asked = time.time()
    key("cmd+s")
    if until(lambda: draft_written_since(asked), LIVE_LIMITS["settle"]):
        return "saved"
    return "sent cmd+s to CapCut; no draft file changed, so there was likely nothing new to save"


@command("play")
def _play(args):
    # The transport button is named for what it does next (play while paused, pause while playing).
    screen = Screen()
    button = screen.part("play") or screen.part("pause")
    if button is None:
        sys.exit("CapCut's play button is not on screen. Open a draft first.")
    press(*button.centre)


@command("export")
def _export(args):
    run_export(value_after(args, "--to"), value_after(args, "--timeout", int, 900),
               toggle_sync="--toggle-sync" in args)


# ---- 5: reading what CapCut shows

@command("playhead")
def _playhead(args):
    screen = Screen()
    return f"{screen.readout('playhead')} of {screen.readout('length')}"


@command("clips")
def _clips(args):
    list_clips()


@command("timeline")
def _timeline(args):
    timeline_report(value_after(args, "--draft"))


@command("screenshot")
def _screenshot(args):
    return f"wrote {capture_window(args[0] if args else 'capcut-window.png')}"


# ---- when a CapCut update moves the accessibility ids

@command("ids")
def _ids(args):
    depth = value_after(args, "--depth", int)
    if "--map" in args:
        map_report(depth, value_after(args, "--save"))
    else:
        print_ids(first_word(args), depth)


@command("click-id")
def _click_id(args):
    return f"clicked {press_on(args[0])}"


@command("click-at")
def _click_at(args):
    # For anything CapCut keeps out of its accessibility tree, a position is the only way in.
    press(float(args[0]), float(args[1]), clicks=value_after(args, "--clicks", int, 1))
    return f"clicked {args[0]},{args[1]}"


@command("key")
def _key(args):
    key(args[0])


# Older command names, still accepted.
OLDER_NAMES = {"replay": "new-draft", "ls": "drafts", "graphics": "place-plan", "add-overlay": "layer",
               "add-text": "text", "transform": "move", "magnet": "fix-magnet", "verify-magnet": "check-magnet",
               "launch": "start", "seek": "go-to", "del": "delete", "zoomfit": "fit-timeline", "state": "timeline",
               "shot": "screenshot", "dump": "ids", "click": "click-id", "clickxy": "click-at"}
for _older, _name in OLDER_NAMES.items():
    COMMANDS[_older] = COMMANDS[_name]

# Older function names, still accepted.
capcut_pid, quit_capcut, start_capcut, editing = capcut_process, close_capcut, open_capcut, building_on


def main():
    if len(sys.argv) < 2:
        raise SystemExit(USAGE)
    name, args = sys.argv[1], sys.argv[2:]
    handler = COMMANDS.get(name)
    if handler is None:
        raise SystemExit(f"unknown command: {name}")
    said = handler(args)
    if said is not None:
        print(said)


if __name__ == "__main__":
    main()
