#!/usr/bin/env python3
"""capcut_compound.py — write CapCut COMPOUND clips, so the creator gets a slip tool CapCut does not ship.

CapCut has no slip tool. Once a shot is on the timeline you cannot change which part of the source plays
without dragging its edges, which shifts everything after it. A compound clip solves it: the compound holds
the WHOLE clip inside, the timeline shows only a window of it, and opening the compound lets the inside be
moved while the outer clip keeps its position and length. That is a slip.

THE FORMAT (decoded from a compound the creator made by hand — per CAPCUT-SELF-HEAL-PLAYBOOK, derive it
from a real draft, never invent it). Four things have to line up or the timeline comes up EMPTY:

  1. `subdraft/<inner-id>/` on disk, holding `draft_content.json` (the nested draft),
     `sub_draft_config.json` and `draft_cover.jpg`.
  2. A `materials.drafts[]` entry: {id, type:"combination", combination_id, combination_type:"none",
     precompile_combination:false, draft:<the nested draft, ALSO inline>, and draft_file_path /
     draft_cover_path / draft_config_path pointing into that subdraft folder}.
  3. A SYNTHETIC entry in `materials.videos[]` — `path:""`, `media_path:""`,
     `material_name:"Compound clipN"`, `extra_type_option:2`, duration = the compound's length.
     The timeline segment's `material_id` points at THIS, not at the real footage.
  4. The segment's `extra_material_refs` must contain the drafts[] entry id (CapCut writes it first).
     This is the actual link between clip and compound, and missing it is why a hand-built draft opens
     with nothing on the timeline.

Media paths are never absolute: CapCut stores `##_draftpath_placeholder_<constant-uuid>_##/assets/...`
and resolves it to wherever the draft currently lives. Absolute paths break the moment a draft is renamed
("media not found in the project"). All times are microseconds.
"""
import copy
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capcut_color  # the nested draft is a draft too: its one clip goes in SDR, like every other segment

US = 1_000_000
PATH_TOKEN = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"


def uid():
    return str(uuid.uuid4()).upper()


def tokenise_paths(node):
    """Rewrite absolute media paths to CapCut's placeholder token. Returns how many were rewritten.

    On Windows the editing engine writes these paths with backslashes (C:\\...\\assets\\video\\clip.mp4), so they
    are read with every backslash turned forward first. Matching "/assets/" alone found none of them there: the
    draft folder was renamed anyway, and every clip went on pointing into the folder that no longer existed."""
    n = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("path", "media_path") and isinstance(v, str) and "/assets/" in v.replace("\\", "/"):
                node[k] = PATH_TOKEN + "/assets/" + v.replace("\\", "/").split("/assets/", 1)[1]
                n += 1
            else:
                n += tokenise_paths(v)
    elif isinstance(node, list):
        for v in node:
            n += tokenise_paths(v)
    return n


def _cover(clip_path, at_seconds, out_path):
    """A 180x320 poster frame, the size CapCut writes for a subdraft cover."""
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(max(0.0, at_seconds)), "-i", clip_path,
                        "-frames:v", "1", "-vf", "scale=180:320", "-y", out_path], check=True)
    except Exception:
        pass


def make_compound(draft, seg, draft_dir, clip_dur_us, window_start_us, index,
                  source_clip=None, window_seconds=0.0):
    """Turn one timeline segment into a compound holding its WHOLE clip.

    `clip_dur_us` is the full source length — that extra footage either side of the visible window is the
    entire point, since without it there is nothing to slip to.
    """
    mats = draft["materials"]
    real = next((v for v in mats["videos"] if v["id"] == seg["material_id"]), None)
    if real is None:
        raise RuntimeError(f"segment {seg.get('id')} points at no video material")

    shown_us = seg["target_timerange"]["duration"]
    name = f"Compound clip{index}"
    inner_id = uid()

    # --- the nested draft: the whole clip, untrimmed, on its own one-track timeline
    inner_seg = copy.deepcopy(seg)
    inner_seg["id"] = uid()
    inner_seg["source_timerange"] = {"start": 0, "duration": clip_dur_us}
    inner_seg["target_timerange"] = {"start": 0, "duration": clip_dur_us}
    inner_seg["extra_material_refs"] = list(seg.get("extra_material_refs", []))

    inner = {k: copy.deepcopy(draft[k]) for k in
             ("canvas_config", "color_space", "config", "fps", "version", "new_version",
              "is_drop_frame_timecode", "free_render_index_mode_on", "platform",
              "last_modified_platform", "mutable_config", "keyframe_graph_list") if k in draft}
    inner.update({
        "id": inner_id, "name": "", "duration": clip_dur_us,
        "create_time": 0, "update_time": 0, "path": "", "draft_type": "",
        "materials": {k: (copy.deepcopy(v) if not isinstance(v, list) else []) for k, v in mats.items()},
        "tracks": [{"id": uid(), "type": "video", "attribute": 0, "flag": 0,
                    "is_default_name": True, "name": "", "segments": [inner_seg]}],
        "keyframes": copy.deepcopy(draft.get("keyframes", {})),
        "relationships": [], "extra_info": None, "cover": None, "retouch_cover": None,
        "static_cover_image_path": "", "time_marks": None, "lyrics_effects": [],
        "group_container": None, "source": "default",
    })
    inner["materials"]["videos"] = [copy.deepcopy(real)]
    capcut_color.enforce_sdr(inner)   # inner_seg is a copy of the footage segment; never carry an HDR tag inside
    inner["materials"]["drafts"] = []
    for bucket in ("canvases", "speeds", "sound_channel_mappings", "vocal_separations",
                   "material_colors", "placeholder_infos", "material_animations"):
        inner["materials"].setdefault(bucket, [])
        for ref in seg.get("extra_material_refs", []):
            hit = next((m for m in mats.get(bucket, []) if m.get("id") == ref), None)
            if hit:
                inner["materials"][bucket].append(copy.deepcopy(hit))

    # --- write the subdraft folder CapCut expects beside the draft
    sub = os.path.join(draft_dir, "subdraft", inner_id)
    os.makedirs(sub, exist_ok=True)
    json.dump(inner, open(os.path.join(sub, "draft_content.json"), "w", encoding="utf-8"))
    now = int(time.time())
    json.dump({
        "audio_path": "", "cover_height": 320, "cover_width": 180, "cover_path": "draft_cover.jpg",
        "create_time": now, "draft_json_file": "draft_content.json", "id": inner_id,
        "import_time_ms": now * 1000, "is_from_multi_timeline": False, "is_from_sub_draft": True,
        "name": name, "project_id": inner_id, "rough_cut_duration": clip_dur_us,
        "rough_cut_start": 0, "source": "timeline", "type": "video",
    }, open(os.path.join(sub, "sub_draft_config.json"), "w", encoding="utf-8"))
    if source_clip:
        _cover(source_clip, window_seconds, os.path.join(sub, "draft_cover.jpg"))

    # --- the drafts[] entry
    comp_id = uid()
    base = f"{PATH_TOKEN}/subdraft/{inner_id}"
    mats.setdefault("drafts", []).append({
        "id": comp_id, "type": "combination", "name": "", "category_id": "", "category_name": "",
        "formula_id": "", "combination_id": uid(), "combination_type": "none",
        "aimusic_mv_template_info": None, "precompile_combination": False,
        "draft": inner,
        "draft_file_path": f"{base}/draft_content.json",
        "draft_cover_path": f"{base}/draft_cover.jpg",
        "draft_config_path": f"{base}/sub_draft_config.json",
    })

    # --- the synthetic video material the timeline actually points at
    stand_in = copy.deepcopy(real)
    stand_in.update({
        "id": uid(), "path": "", "media_path": "", "local_id": "", "material_id": "",
        "material_name": name, "material_url": "", "extra_type_option": 2, "source": 0,
        "duration": clip_dur_us, "has_audio": True, "reverse_path": "", "intensifies_path": "",
        "reverse_intensifies_path": "", "intensifies_audio_path": "", "cartoon_path": "",
        "local_material_id": "", "origin_material_id": "", "unique_id": "",
    })
    stand_in["width"] = draft["canvas_config"]["width"]
    stand_in["height"] = draft["canvas_config"]["height"]
    mats["videos"].append(stand_in)

    # --- repoint the timeline segment: synthetic material + the compound in extra_material_refs
    seg["material_id"] = stand_in["id"]
    refs = [r for r in seg.get("extra_material_refs", [])]
    seg["extra_material_refs"] = [comp_id] + refs
    seg["source_timerange"] = {"start": window_start_us, "duration": shown_us}
    return comp_id
