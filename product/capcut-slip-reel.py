#!/usr/bin/env python3
"""capcut-slip-reel.py — hand a whole reel to CapCut with every shot as a COMPOUND, so she can slip.

CapCut ships no slip tool: once a shot is placed you cannot change which part of the source plays without
dragging its edges, which shifts everything after it. This builds the reel so each beat is a compound clip
holding its WHOLE source, with only the chosen window on the timeline. Double-click into a compound, drag
the clip inside, and the beat keeps its position and length while a different moment plays. That is a slip,
and it is hers to do by hand — no round trip through the engine.

  product/engine/VectCutAPI/venv-capcut/bin/python product/capcut-slip-reel.py \
      --job my-reel --name "my-reel slip" \
      --plan shot-plan.capcut.json --graphics demos/graphics.mov

Run it with the VectCut venv python, and with CapCut QUIT.

Layout of the draft she gets:
  · the voiceover as ONE unbroken audio track, so nothing she does to the picture can pull it out of sync
  · every beat above it as a compound, each holding its full source clip
  · optionally the finished graphics as one overlay layer on its own track, timed to the VOICE rather than
    to the picture, so slipping a shot never moves a caption

Compound format: see product/capcut_compound.py (decoded from a compound the creator built by hand).
"""
import argparse
import json
import os
import subprocess
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import time

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
US = 1_000_000
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "product"))
BASE = "http://localhost:9001"
# The double-click starter is named per platform; point the buyer at the one they have.
_STARTER = "start-editor.bat" if os.name == "nt" else "start-editor.command"
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAP = __import__("capcut_store_redirect").drafts_root()

import capcut_compound as cc          # noqa: E402
from capcut_front import to_front, remember   # noqa: E402


def call(ep, _strict=True, **kw):
    import requests
    try:
        r = requests.post(f"{BASE}/{ep}", json=kw, timeout=600)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"The editor engine (VectCut) is not running at {BASE}. Start it with "
            f"product/engine/VectCutAPI/{_STARTER} (SETUP.md §1b), then re-run.") from None
    try:
        j = r.json()
    except ValueError:
        j = {"success": False, "error": f"non-JSON reply (HTTP {r.status_code}): {r.text[:120]!r}"}
    if not j.get("success") and _strict:
        raise RuntimeError(f"VectCut {ep} failed: {str(j.get('error'))[:200]}")
    return j


def dur_of(path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path]).strip())


def register(draft_dir, name, draft):
    """Put the draft in CapCut's list through the same writer every builder's finalize uses. The copy that lived
    here gave up without a word when the list was empty (a CapCut that has never saved a draft), and the draft
    then built fine and stayed invisible, with to_front stopping on "not in CapCut's index"."""
    import capcut_media, uuid
    mpath = os.path.join(draft_dir, "draft_meta_info.json")
    try:
        meta = json.load(open(mpath, encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    # A FRESH draft_id for every draft, as cleanyap/superyap stamp since v2.2.24: the VectCut template carries one
    # fixed id, and CapCut keeps one project per id, so a newer voiceover version vanished from the grid beside the
    # older one. Written into the draft's own meta too, so the folder and the list agree.
    meta["draft_id"] = str(uuid.uuid4()).upper()
    if os.path.exists(mpath):
        meta["draft_name"] = name
        json.dump(meta, open(mpath, "w", encoding="utf-8"), ensure_ascii=False)
    capcut_media.register_draft(CAP, name, draft_dir, _ds.draft_json(draft_dir), meta["draft_id"],
                                draft.get("duration", 0), int(time.time()), US)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--name", required=True, help="CapCut draft name (never reuse an existing one)")
    ap.add_argument("--plan", default="shot-plan.capcut.json",
                    help="shot plan to build from, relative to the job folder")
    ap.add_argument("--graphics", default=None,
                    help="finished graphics layer (.mov) to lay over the picture, relative to the job")
    ap.add_argument("--beats", default="", help="comma-separated beat numbers, for a partial build")
    a = ap.parse_args()

    import draft_safety
    draft_safety.require_capcut_quit("build the slip draft")

    dst = f"{CAP}/{a.name}"
    if os.path.isdir(dst):
        raise SystemExit(f"REFUSING: a draft named {a.name!r} already exists. Pick a new name — CapCut has "
                         f"no version history, so building over it would wipe anything you changed in it.")

    jd = f"{REPO}/projects/{a.job}"
    plan_path = f"{jd}/{a.plan}"
    if not os.path.exists(plan_path):
        plan_path = f"{jd}/shot-plan.json"
    plan = json.load(open(plan_path, encoding="utf-8"))
    holds = plan["holds"]
    if a.beats:
        holds = [holds[int(x) - 1] for x in a.beats.replace(" ", "").split(",") if x]

    vo = f"{jd}/audio/vo.clean.wav"
    if not os.path.exists(vo):
        raise SystemExit(f"no spliced voiceover at {vo}")

    shots = []
    for h in holds:
        p = h["path"] if os.path.isabs(h["path"]) else f"{REPO}/{h['path']}"
        if not os.path.exists(p):
            raise SystemExit(f"missing clip: {p}")
        shots.append({"path": p, "full": dur_of(p), "win": float(h["in"]),
                      "shown": float(h["out"]) - float(h["in"])})

    print(f"[1/4] placing {len(shots)} beats ...")
    did = call("create_draft", width=1080, height=1920)["output"]["draft_id"]
    at = 0.0
    for s in shots:
        call("add_video", draft_id=did, video_url=s["path"], start=s["win"],
             end=s["win"] + s["shown"], target_start=at, track_name="main")
        at += s["shown"]

    print("[2/4] laying the voiceover as one unbroken track ...")
    call("add_audio", draft_id=did, audio_url=vo, start=0, end=dur_of(vo), target_start=0)

    gfx = None
    if a.graphics:
        gfx = a.graphics if os.path.isabs(a.graphics) else f"{jd}/{a.graphics}"
        if os.path.exists(gfx):
            print("[3/4] laying the graphics over the picture ...")
            import capcut_alpha             # straight ProRes 4444 in, edges cleaned, whatever the graphics file was
            gfx = capcut_alpha.for_capcut(gfx)
            call("add_video", draft_id=did, video_url=gfx, start=0, end=dur_of(gfx),
                 target_start=0, track_name="graphics")
        else:
            print(f"   (no graphics layer at {gfx}, skipping)")
            gfx = None

    call("save_draft", _strict=False, draft_id=did, draft_folder=CAP)
    src = f"{CAP}/{did}"
    info = _ds.draft_json(src)
    draft = json.load(open(info, encoding="utf-8"))

    # The picture is the track carrying one segment per beat. The graphics overlay, if present, is a single
    # segment on its own track and must NOT be wrapped — it is a finished layer, not a shot to slip.
    vtracks = [t for t in draft["tracks"] if t.get("type") == "video" and t.get("segments")]
    picture = None
    for t in vtracks:
        if len(t["segments"]) == len(shots):
            picture = t
            break
    if picture is None:
        vtracks.sort(key=lambda t: len(t["segments"]), reverse=True)
        picture = vtracks[0] if vtracks else None
    if picture is None or len(picture["segments"]) != len(shots):
        raise SystemExit(f"expected a track with {len(shots)} segments, found "
                         f"{[len(t['segments']) for t in vtracks]}")

    print(f"[4/4] wrapping {len(shots)} beats as compounds ...")
    segs = sorted(picture["segments"], key=lambda x: x["target_timerange"]["start"])
    for i, (seg, s) in enumerate(zip(segs, shots), 1):
        cc.make_compound(draft, seg, src, round(s["full"] * US), round(s["win"] * US), i,
                         source_clip=s["path"], window_seconds=s["win"])
    rewritten = cc.tokenise_paths(draft)

    from capcut_ripple import enforce_maintrack_ripple

    enforce_maintrack_ripple(draft)   # LOCKED: magnet every track to the main track before the draft is written

    json.dump(draft, open(info, "w", encoding="utf-8"))
    # LOCKED (see CLAUDE.md rule 7): NEVER replace a draft the creator may have opened. Her in-app edits
    # live only inside the CapCut draft and CapCut keeps no version history, so a rename landing on an
    # existing name destroys them irreversibly. Refuse and name the next safe version instead.
    if os.path.isdir(dst) and os.path.abspath(dst) != os.path.abspath(src):
        try:
            nxt = draft_safety.next_version(draft_safety.base_of(a.name))
        except Exception:
            nxt = f"{a.name} 1.1"
        raise SystemExit(
            f"REFUSING to overwrite the existing draft {a.name!r}: a rebuild would wipe any edits you made "
            f"to it in CapCut, and CapCut has no version history to get them back. Build to {nxt!r} instead "
            f"(never reuse a name), or slip the beats inside the draft you already have.")
    os.rename(src, dst)
    try:
        register(dst, a.name, draft)
    except BaseException:
        # Not registered, so CapCut cannot show it, yet the folder would own the name and the next build to it
        # would be refused as "existing work". Give the name back before the error surfaces. (discard_unfinished
        # itself refuses a draft that did get registered; the original error is the one worth showing.)
        try:
            draft_safety.discard_unfinished(dst)
        except Exception:
            pass
        raise
    remember(a.name)      # CapCut reshuffles its list on every launch; this keeps it at the top
    to_front(a.name)

    back = min(s["win"] for s in shots)
    fwd = min(s["full"] - s["win"] - s["shown"] for s in shots)
    print(f"\n✅ {a.name}  —  {len(shots)} compound beats + one unbroken voiceover"
          + (" + a graphics layer" if gfx else ""))
    print(f"   every shot holds its whole clip: at worst {back:.1f}s back and {fwd:.1f}s forward to slip into")
    print(f"   ({rewritten} media paths written as CapCut's own token)")
    print("\n   Double-click any beat to open it, drag the clip inside to pick a different moment.")
    print("   The beat keeps its place and its length, so the voiceover never drifts.")


if __name__ == "__main__":
    main()
