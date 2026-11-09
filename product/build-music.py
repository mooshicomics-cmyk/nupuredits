#!/usr/bin/env python3
"""build-music.py — lay the chosen background-music bed into the migrated CapCut draft as ONE editable
audio track "Background Music" at a quiet -18 dB bed (volume ~0.126), spanning the whole reel. Loops the
approved seed clip to the draft length with a gentle tail fade. Confessional default = FLAT bed, no ducking.
CapCut MUST be quit. Reuses an existing draft's audio template (CAPCUT_TEMPLATE).
Job/target: JOB env var = project slug under projects/ (required); CAPCUT_DRAFT env var = the draft
folder to build into (required); CAPCUT_TEMPLATE env var = the draft to borrow the audio-material
template from (required). Seed clip = argv[1], else projects/<JOB>/audio/chill1-mellow-keys.wav.
"""
import json, os, glob, copy, uuid, shutil, re, subprocess, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
def _require_env(name, hint):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"[build-music] Set {name}=<{hint}> before running "
                 f"(e.g. {name}=MyProject python3 product/build-music.py). "
                 f"Refusing to silently fall back to a bundled sample reel.")
    return v

JOB      = _require_env("JOB", "your project slug under projects/")   # projects/<JOB>
DRAFT    = _require_env("CAPCUT_DRAFT", "the CapCut draft folder to build into")  # CapCut draft to build into
TEMPLATE = _require_env("CAPCUT_TEMPLATE", "the draft to borrow the audio template from")  # draft to borrow audio template from
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()
KD = f"{CAP}/{DRAFT}"; NA = f"{CAP}/{TEMPLATE}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = sys.argv[1] if len(sys.argv) > 1 else f"{ROOT}/projects/{JOB}/audio/chill1-mellow-keys.wav"
BED_NAME = "Background Music"
US = 1_000_000
VOL = 0.126   # -18 dB flat bed

def NID(): return str(uuid.uuid4()).upper()
def nid(): return uuid.uuid4().hex

if __name__ == "__main__":
    import draft_safety
    draft_safety.require_capcut_quit("lay music under the draft")   # else CapCut's next save wipes it
    _ed, _why = draft_safety.edited_in_capcut(DRAFT, why=True)      # rule-7 net (warn, not block — additive)
    if _ed:
        _nv = draft_safety.next_version(draft_safety.base_of(DRAFT))
        print(f"⚠ {DRAFT!r} looks edited in CapCut since it was built ({_why}). This add is additive/safe, "
              f"but for a clean version history build to {_nv!r} instead.")
    kd = json.load(open(_ds.draft_json(KD), encoding="utf-8"))
    total = kd["duration"]                      # µs — the full reel length
    secs = total / US
    # loop the approved seed to reel length + gentle 0.8s in / 2.5s tail-out
    os.makedirs(f"{KD}/assets/audio", exist_ok=True)
    bed = f"{KD}/assets/audio/bed-minimal-ambient.mp3"
    # -map_chapters -1: a song's own chapter (an Epidemic mp3 carries one) never rides into the bed, where it would
    # outlast the reel
    subprocess.run(["ffmpeg","-y","-stream_loop","-1","-i",SEED,"-map","0:a:0?","-map_chapters","-1","-t",f"{secs:.3f}",
                    "-af",f"afade=t=in:st=0:d=0.8,afade=t=out:st={max(0,secs-2.5):.3f}:d=2.5",
                    "-codec:a","libmp3lame","-q:a","3",bed], check=True, capture_output=True)
    beddur = int(round(float(subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",bed]))*US))
    # footage media-path scheme: old template drafts carry a ##_draftpath_placeholder_<UUID>_## token;
    # VectCutAPI drafts (cleanyap/superyap, current engine) use ABSOLUTE paths into the draft's assets/.
    # Support both — ph is the token if present, else None (→ the bed gets an absolute path into KD).
    ph = None
    for m in kd["materials"]["videos"]:
        mm = re.search(r'placeholder_([0-9A-F-]+)_', m.get("path", ""))
        if mm:
            ph = mm.group(1); break
    na = json.load(open(_ds.draft_json(NA), encoding="utf-8"))
    aud_t = na["materials"]["audios"][0]
    seg_t = next(s for t in na["tracks"] if t["type"]=="audio" for s in t["segments"])
    naidx = {m["id"]:(cat,m) for cat,l in na["materials"].items() if isinstance(l,list) for m in l if isinstance(m,dict) and "id" in m}
    helpers = [naidx[r] for r in seg_t["extra_material_refs"]]

    for path in _ds.draft_json_copies(KD, require=False):
        d = json.load(open(path, encoding="utf-8"))
        # REPLACE any prior Background Music track (don't stack); KEEP her SFX track + all her edits
        amap = {mm["id"]: mm for mm in d["materials"].get("audios", [])}
        d["tracks"] = [t for t in d["tracks"] if not (t["type"] == "audio" and t["segments"]
                       and amap.get(t["segments"][0]["material_id"], {}).get("name") == BED_NAME)]
        m = copy.deepcopy(aud_t); mid = nid()
        # match the footage media-path scheme so CapCut resolves the bed (placeholder token vs absolute).
        bedpath = (f"##_draftpath_placeholder_{ph}_##/assets/audio/bed-minimal-ambient.mp3" if ph
                   else f"{KD}/assets/audio/bed-minimal-ambient.mp3")
        m.update(id=mid, unique_id="", music_id=mid, local_material_id=mid, name=BED_NAME,
                 path=bedpath, duration=beddur, wave_points=[])
        d["materials"]["audios"].append(m)
        refs = []
        for cat, ht in helpers:
            hh = copy.deepcopy(ht); hh["id"] = NID() if "-" in ht["id"] else nid()
            d["materials"][cat].append(hh); refs.append(hh["id"])
        s = copy.deepcopy(seg_t); s["id"]=NID(); s["material_id"]=mid; s["extra_material_refs"]=refs
        s["source_timerange"]={"start":0,"duration":min(beddur,total)}
        s["target_timerange"]={"start":0,"duration":min(beddur,total)}
        s["volume"]=VOL; s["last_nonzero_volume"]=VOL; s["common_keyframes"]=[]; s["keyframe_refs"]=[]
        track = {"type":"audio","attribute":0,"flag":0,"id":NID(),"is_default_name":True,"name":"","segments":[s]}
        d["tracks"].append(track)
        from capcut_ripple import enforce_maintrack_ripple
        enforce_maintrack_ripple(d)             # magnet ALL tracks (overlays/text/b-roll) + audio to main track
        json.dump(d, open(path,"w", encoding="utf-8"), ensure_ascii=False)
        print(f"laid '{BED_NAME}' bed ({secs:.1f}s, vol {VOL}) -> {path}")
    print("done — minimal-ambient flat bed at -18 dB under the voice; editable in CapCut.")
