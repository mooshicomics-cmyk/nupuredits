#!/usr/bin/env python3
"""capcut_media.py — MEDIA GUARDRAIL for CapCut drafts.

Guarantees every clip on the timeline will LINK and IMPORT in CapCut. The failure this prevents: media
placed by referencing an external absolute path shows as "not linked" and never appears in the media
panel, because CapCut only auto-registers media that lives INSIDE the draft folder — and a ProRes 4444
overlay triggers "couldn't import some of the files". Both silently ship a broken reel.

So, for every clip a build puts on the timeline this makes sure it is:
  1. PROJECT-LOCAL  — copied into the draft's own `assets/video` | `assets/audio` and referenced by the
     draft placeholder path (never an external absolute path). A byte copy, NEVER a re-encode, so
     source footage color is untouched.
  2. REGISTERED     — has an entry in `draft_meta_info.json` so CapCut links it and lists it.
  3. VALID DURATION — a zero/absent duration reads as "-" and won't play; probe + set it.
  4. IMPORTABLE     — an OPAQUE clip must be an H.264/HEVC MP4 (a big opaque ProRes is what "couldn't
     import"). A TRANSPARENT overlay is the one exception: render it as ProRes 4444 with alpha (yuva) —
     CapCut imports that fine once it is registered (this is how the reel's Claude-UI overlay ships).

`ensure_shippable(d, draft_dir)` mutates the loaded draft_info dict + writes draft_meta_info, and RETURNS
a list of unfixable problems (empty == shippable) so the caller can refuse the build. Whitelabel-clean:
operates only on the draft dir + media handed to it; no personal names or paths.
"""
import os, time, json, shutil, subprocess, re, time
from capcut_ripple import enforce_maintrack_ripple   # re-assert the main-track magnet on any draft we re-save

import sys as _sys, os as _os_ds
for _stream in (_sys.stdout, _sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
DEFAULT_TOKEN = "0E685133-18CE-45ED-8CB8-2904A212EC80"   # pyJianYingDraft draft-path placeholder
# Opaque ProRes -> "couldn't import" (re-export MP4). ProRes 4444 WITH alpha (yuva) is allowed: it is the
# CapCut transparent-overlay format and imports once registered. See has_alpha() + the codec gate below.

def _out(*a): return subprocess.run(a, capture_output=True, text=True).stdout.strip()

def probe_video(path):
    """-> (duration_us, width, height, codec_name, pix_fmt)."""
    j = _out("ffprobe","-v","error","-select_streams","v:0","-show_entries",
             "stream=codec_name,width,height,pix_fmt:format=duration","-of","json",path)
    try:
        o = json.loads(j); st = (o.get("streams") or [{}])[0]
        dur = float(o.get("format",{}).get("duration") or 0)
        return (int(round(dur*1e6)), int(st.get("width") or 0), int(st.get("height") or 0),
                (st.get("codec_name") or ""), (st.get("pix_fmt") or ""))
    except Exception:
        return 0,0,0,"",""

from capcut_alpha import has_alpha   # one definition, shared with the transparency step below
import capcut_alpha

def probe_dur_us(path):
    v = _out("ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path)
    try: return int(round(float(v)*1e6))
    except Exception: return 0

def token_of(d):
    for m in d["materials"].get("videos",[]) + d["materials"].get("audios",[]):
        mm = re.search(r"##_draftpath_placeholder_([0-9A-Za-z-]+)_##", m.get("path","") or "")
        if mm: return mm.group(1)
    return DEFAULT_TOKEN

def real_path(path, draft_dir, token):
    ph = f"##_draftpath_placeholder_{token}_##"
    return path.replace(ph, draft_dir) if path and path.startswith("##") else (path or "")

def write_cover(d, draft_dir):
    """Generate the draft's cover thumbnail (draft_dir/draft_cover.jpg). CapCut's drafts list points every
    entry at a draft_cover.jpg; finalize() names that file in the registry but nothing was CREATING it, so a
    fresh build had a cover path aimed at a file that never existed — one of the two reasons a new draft
    could be INVISIBLE in the drafts grid with no error. Grab one frame from the first footage clip, sized
    to the 1080x1920 JPG the app expects. Best-effort: returns True on success, False if it can't (never
    raises — a missing cover must not fail an otherwise-good build). Whitelabel-clean: only the draft dir."""
    try:
        token = token_of(d)
        vids = [t for t in d.get("tracks", []) if t.get("type") == "video" and t.get("segments")]
        if not vids:
            return False
        foot = max(vids, key=lambda t: len(t["segments"]))
        seg0 = foot["segments"][0]
        mid = seg0.get("material_id")
        mat = next((m for m in d["materials"].get("videos", []) if m.get("id") == mid), None)
        if not mat:
            return False
        src = real_path(mat.get("path", ""), draft_dir, token)
        if not src or not os.path.isfile(src):
            return False
        # a few seconds into the kept portion (clamped small so a short first clip still yields a frame)
        ss = max(0.0, seg0.get("source_timerange", {}).get("start", 0) / 1_000_000) + 0.5
        out = os.path.join(draft_dir, "draft_cover.jpg")
        subprocess.run(["ffmpeg", "-y", "-ss", f"{ss:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                        out], capture_output=True, text=True)
        return os.path.isfile(out) and os.path.getsize(out) > 0
    except Exception:
        return False

# A REAL, captured CapCut registry-entry shape (root_meta_info.json -> all_draft_store[i]),
# with every per-draft + machine/cloud-identifying value neutralized. Used ONLY as the template
# for a NEW entry when the registry is empty (brand-new CapCut install: all_draft_store == []).
# Captured field-for-field from a real CapCut-written registry (not hand-guessed) so a fresh
# buyer's first-ever draft registers with the exact shape CapCut's drafts grid expects.
# register_draft() overwrites the identifying fields (name/paths/ids/timestamps/duration) anyway;
# this only supplies the SHAPE + the cloud/pippit defaults CapCut fills in itself.
_EMPTY_REGISTRY_ENTRY = {
    "cloud_draft_cover": False, "cloud_draft_sync": False,
    "draft_cloud_last_action_download": False, "draft_cloud_purchase_info": "",
    "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
    "draft_cloud_videocut_purchase_info": "", "draft_cover": "", "draft_fold_path": "",
    "draft_id": "", "draft_is_ai_shorts": False, "draft_is_cloud_temp_draft": False,
    "draft_is_infinite_canvas_draft": False, "draft_is_invisible": False,
    "draft_is_pippit_draft": False, "draft_is_web_article_video": False, "draft_json_file": "",
    "draft_name": "", "draft_new_version": "", "draft_root_path": "",
    "draft_timeline_materials_size": 0, "draft_type": "", "draft_web_article_video_enter_from": "",
    "pippit_avatar_url": "", "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
    "streaming_edit_draft_ready": True, "tm_draft_cloud_completed": "",
    "tm_draft_cloud_entry_id": -1, "tm_draft_cloud_modified": 0,
    "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
    "tm_draft_cloud_user_id": -1, "tm_draft_create": 0, "tm_draft_modified": 0,
    "tm_draft_removed": 0, "tm_duration": 0,
}


def register_draft(cap, name, draft_dir, draft_json_file, draft_id, duration, now, us=1_000_000):
    """Insert/replace this draft's entry in CapCut's root_meta_info.json — the registry the drafts GRID
    reads to list, sort, and cover every draft. Shared by cleanyap.py + superyap.py finalize().

    On a brand-new CapCut install `all_draft_store` is `[]`, so the old `all_draft_store[0]` clone
    raised IndexError and crashed the buyer's FIRST-EVER build. Fall back to the real-schema template
    above when the store is empty; clone an existing entry's shape when it isn't (unchanged behavior).
    `now` is threaded in from the caller (not computed here) so it MATCHES the timestamp already stamped
    into the sibling draft_meta_info.json write — CapCut sorts the grid off both and they must agree."""
    rp = f"{cap}/root_meta_info.json"
    started = False
    try:
        r = json.load(open(rp, encoding="utf-8"))
    except FileNotFoundError:
        # A CapCut that has never been opened has not written its list yet. That is an empty list, not an error:
        # raising here came AFTER finalize had renamed the draft into place, so the build failed and the
        # unregistered folder kept the name, and the next build to that name was refused. Start the list in
        # the shape CapCut writes it (the drafts, how many, and where they live).
        os.makedirs(cap, exist_ok=True)
        r, started = {"all_draft_store": [], "draft_ids": 0, "root_path": cap}, True
    store = r.get("all_draft_store") or []
    tmpl = store[0] if store else _EMPTY_REGISTRY_ENTRY
    e = dict(tmpl)
    e.update(
        draft_name=name, draft_fold_path=draft_dir, draft_id=draft_id, draft_json_file=draft_json_file,
        draft_root_path=cap, draft_cover=f"{draft_dir}/draft_cover.jpg",
        tm_draft_create=now * us, tm_draft_modified=now * us, tm_draft_removed=0, tm_duration=duration)
    r["all_draft_store"] = [x for x in store if x.get("draft_name") != name]
    r["all_draft_store"].insert(0, e)
    if started:                                   # a list this started: count the draft it now holds
        r["draft_ids"] = len(r["all_draft_store"])
    json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)

    # AND KEEP IT AT THE TOP — permanently, for every caller (locked 2026-09-19, creator: "when you make
    # something for me in CapCut, it always needs to be at the top ... I do not want to go hunting for your
    # drafts, and I always am").
    #
    # The insert(0) above only wins until CapCut's NEXT session: CapCut rebuilds this file from its own
    # records and re-sorts by tm_draft_modified, so a draft placed at the top while CapCut was quit sinks
    # back into a 160+ deep list the moment she opens the app. That is the hunting. capcut_front owns the
    # durable answer (a remembered pin its LaunchAgent re-applies after every session).
    #
    # It lives HERE, in register_draft, and NOT in each builder's finalize, because this is the single
    # chokepoint every draft passes through to become visible in CapCut at all. Wiring it per-builder means
    # the next build path that gets written forgets it, and she goes hunting again. Registering a draft and
    # putting it on top are one action now, and cannot come apart.
    #
    # Never fatal: a draft that built fine must not fail because the list could not be reordered.
    try:
        import capcut_front
        capcut_front.remember(name)
        capcut_front.ensure()
    except Exception as _e:
        print(f"  \u26a0 built and registered, but could not pin it to the top of the list "
              f"({type(_e).__name__}). Run: python3 product/capcut_front.py \"{name}\"")

    # A Microsoft Store Claude app, or a Mac that refuses the engine any write in ~/Movies: this draft was built
    # in the engine's staging folder, because CapCut could not see (Windows) or receive (Mac) it otherwise. It
    # is handed over here, at the one place every draft passes through, so no build path can forget it. On
    # Windows the engine runs "Add to CapCut" itself when this build ends (through Explorer, outside the Store
    # app) and falls back to her double-click when that does not finish; on a Mac she gets the double-click.
    try:
        import capcut_store_redirect as _store
        if _store.is_staging(cap):
            _store.after_build(name)
    except Exception:
        pass
    # Two CapCuts on one PC (desktop + Microsoft Store) keep two separate lists, and only the desktop one shows
    # what the engine builds. Say so after the build, once per run, so she never hunts in the wrong one.
    try:
        import capcut_installs
        capcut_installs.say_once()
    except Exception:
        pass


def _used_ids(d):
    ids = set()
    for t in d["tracks"]:
        for s in t.get("segments",[]):
            ids.add(s.get("material_id"))
    return ids

def _register(draft_dir, mat_id, rel_path, metetype, dur_us, w, h, name):
    """Add or refresh the draft_meta_info entry so CapCut links + shows the clip."""
    mp = f"{draft_dir}/draft_meta_info.json"
    meta = json.load(open(mp, encoding="utf-8"))
    grp = None
    for g in meta.get("draft_materials", []):
        if isinstance(g, dict) and isinstance(g.get("value"), list) and g.get("type", 0) == 0:
            grp = g; break
    if grp is None:
        grp = {"type": 0, "value": []}; meta.setdefault("draft_materials", []).append(grp)
    now = int(time.time())
    fields = dict(ai_group_type="", create_time=now, duration=dur_us, enter_from=0, extra_info=name,
                  file_Path=rel_path, height=h, id=mat_id, import_time=now, import_time_ms=now*1000000,
                  item_source=1, material_color_tag="", md5="", metetype=metetype,
                  roughcut_time_range={"duration": dur_us, "start": 0},
                  sub_time_range={"duration": -1, "start": -1}, type=0, width=w)
    existing = next((it for it in grp["value"] if it.get("id") == mat_id), None)
    if existing: existing.update(fields)
    else: grp["value"].append(fields)
    json.dump(meta, open(mp, "w", encoding="utf-8"), ensure_ascii=False)

def _moving_to_clip(d, m, rp, draft_dir, token):
    """A GIF (or moving WebP) on her timeline as a clip CapCut plays, looped for as long as it is on screen. VectCut
    copies a GIF in byte for byte, as a photo material (CapCut holds its first frame: a still) or as GIF bytes named
    .mp4; either way it becomes a looping ProRes 4444 .mov in assets/video and the material a video. The longest
    stretch any segment plays of it sets the length, plus a frame so CapCut never runs past its end."""
    need = 0
    for t in d.get("tracks", []):
        for s in t.get("segments", []):
            if s.get("material_id") == m.get("id"):
                st = s.get("source_timerange") or {}
                need = max(need, int(st.get("start") or 0) + int(st.get("duration") or 0))
    secs = (need / 1e6 + 1.0 / capcut_alpha.LOOP_FPS) if need else None
    src = capcut_alpha.looped_clip(rp, secs)
    local, there = _ds.media_slot(f"{draft_dir}/assets/video/{os.path.basename(src)}", src)
    if not there:
        os.makedirs(os.path.dirname(local), exist_ok=True)
        shutil.copy2(src, local)
    dur_us, w, h, _codec, _pix = probe_video(local)
    m.update(type="video", path=f"##_draftpath_placeholder_{token}_##/assets/video/{os.path.basename(local)}",
             material_name=os.path.basename(local), duration=dur_us, width=w, height=h)
    return local

def ensure_shippable(d, draft_dir, token=None, fresh=False):
    """Make every timeline clip link + import, or return the reasons it can't. Mutates d (localizes +
    repaths + fixes durations) and writes draft_meta_info registrations. Empty list == shippable.

    TRANSPARENCY: CapCut composites overlay alpha as STRAIGHT, as the engine renders it, so every transparent
    clip goes in as a straight copy with its faint edges cleaned, from capcut_alpha.py (cached by content): a
    render, a premultiplied copy the opt-in route made, and a WebM with transparency (CapCut drops its alpha:
    black), which is converted to ProRes 4444 on the way. Media copied in from outside the draft always is. Media
    ALREADY inside the draft is fixed only when `fresh` (a build's own finalize, where VectCut has just copied
    the render in); on a draft she may have opened, a media change belongs in a new version, so it is left.

    A GIF (or moving WebP) goes in as a looping clip, never a picture: CapCut holds a picture's first frame, so a
    GIF any builder added as an image (add_png) or a clip came out a still (_moving_to_clip)."""
    token = token or token_of(d)
    used = _used_ids(d)
    problems = []
    for kind, pool, metetype in (("video","videos","video"), ("audio","audios","music")):
        for m in d["materials"].get(pool, []):
            if m.get("id") not in used: continue
            rp = real_path(m.get("path",""), draft_dir, token)
            if not rp or not os.path.exists(rp):
                problems.append(f"{metetype} '{os.path.basename(m.get('path','') or m['id'])}' file missing: {rp}")
                continue
            if kind == "video" and capcut_alpha.moving_image(rp) and (
                    fresh or not os.path.abspath(rp).startswith(os.path.abspath(draft_dir) + os.sep)):
                try:
                    rp = _moving_to_clip(d, m, rp, draft_dir, token)
                except RuntimeError as e:                   # never a refused draft for it: it goes in as it came, said once
                    print(f"  · a moving picture went into CapCut as it came, so it may hold still there ({e})", flush=True)
            if kind == "video":
                dur_us, w, h, codec, pix = probe_video(rp)
                # ProRes is only valid as a TRANSPARENT overlay (ProRes 4444, alpha/yuva) — CapCut imports
                # that when it's registered. Opaque ProRes must be an MP4 (a big opaque ProRes is what "couldn't
                # import"). So refuse ProRes ONLY when it carries no alpha.
                if "prores" in codec.lower() and not has_alpha(pix):
                    problems.append(f"video '{os.path.basename(rp)}' is opaque ProRes ({pix}) — re-export as an "
                                    f"H.264/HEVC MP4 (ProRes is only for transparent overlays: ProRes 4444/yuva)")
                    continue
            else:
                dur_us, w, h = probe_dur_us(rp), 0, 0
            # 1) project-local
            sub = "video" if kind == "video" else "audio"
            local = f"{draft_dir}/assets/{sub}/{os.path.basename(rp)}"
            outside = os.path.abspath(rp) != os.path.abspath(local)
            src = rp
            if kind == "video" and (outside or fresh) and capcut_alpha.needs_preparing(rp):
                try:
                    src = capcut_alpha.for_capcut(rp)   # straight ProRes 4444, edges cleaned: what CapCut shows correctly
                except RuntimeError as e:
                    problems.append(str(e))
                    continue
            if outside:
                if src != rp and os.path.splitext(rp)[1].lower() not in (".mov", ".mp4", ".m4v"):
                    # a converted WebM is QuickTime now: give its draft copy a name that says so
                    local = os.path.splitext(local)[0] + ".mov"
                os.makedirs(os.path.dirname(local), exist_ok=True)
                local, there = _ds.media_slot(local, src)   # a different file of that name is never reused or overwritten
                if not there:
                    shutil.copy2(src, local)
                m["path"] = f"##_draftpath_placeholder_{token}_##/assets/{sub}/{os.path.basename(local)}"
            elif src != rp:
                capcut_alpha.install(src, rp)           # same name, same material: only the pixels change
            # 3) valid duration + dims
            if not m.get("duration"): m["duration"] = dur_us
            if kind == "video":
                if w and not m.get("width"):  m["width"]  = w
                if h and not m.get("height"): m["height"] = h
            # 2) register
            _register(draft_dir, m["id"], f"./assets/{sub}/{os.path.basename(local)}", metetype,
                      m.get("duration") or dur_us, m.get("width") or w, m.get("height") or h,
                      os.path.basename(local))
    return problems

def harden_draft(draft, fix=True):
    """Standalone entry: run the guardrail on a finished draft folder (or draft name under the default
    CapCut projects dir). Loads draft_info, ensures shippable, saves. Returns problems. CapCut must be quit."""
    if os.path.isdir(draft):
        D = draft
    else:
        # One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
        # Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
        _cap_root = __import__("capcut_store_redirect").drafts_root()
        D = os.path.join(_cap_root, draft)
    if os.name == "nt":
        _running = _ds.capcut_running() is not False   # bytes-safe on any Windows language; unknown = open
    else:
        _running = subprocess.run(["pgrep","-f","CapCut.app/Contents/MacOS/CapCut"], capture_output=True).returncode == 0
    if _running:
        raise SystemExit("CapCut is open — quit it first (editing draft JSON while open gets clobbered).")
    p = _ds.draft_json(D); d = json.load(open(p, encoding="utf-8"))
    problems = ensure_shippable(d, D)
    if fix:
        enforce_maintrack_ripple(d)   # a re-saved draft must never ship a dead magnet — re-anchor before writing
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return problems, D

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python capcut_media.py \"<Draft Name>\" | <draft_dir>"); raise SystemExit(2)
    probs, D = harden_draft(sys.argv[1])
    if probs:
        print("✗ NOT shippable — media that won't link/import:")
        for pr in probs: print("   -", pr)
        raise SystemExit(1)
    print(f"✓ shippable — every clip is project-local, registered, valid, and importable\n  {D}")
