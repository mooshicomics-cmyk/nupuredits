#!/usr/bin/env python3
"""Guards: "my gifs only show as still images" (a buyer, 2026-10-28). A GIF plays, and loops for as long as it is on
screen, wherever she places it, see-through kept.

  capcut picture  a GIF a CapCut build added as a picture (VectCut's add_image: every builder's add_png) landed in
                  the draft byte for byte as a photo material, image_<id>.png, and CapCut held its first frame for
                  the whole stretch. finalize (capcut_media.ensure_shippable, fresh) now makes it a video material:
                  a looping straight ProRes 4444 .mov covering its longest stretch, its transparency kept
  capcut clip     a GIF added as a clip (a --layer, a b-roll call) landed as GIF bytes named .mp4: the same fix
  opened draft    a GIF already inside a draft she may have opened is left exactly as it is (a media change there
                  belongs in a new version)
  drop-ins        gif_dropins.py made an opaque mp4 looped at most five times: a see-through GIF sat in a black box
                  and a long drop-in ended early. Now the same looping see-through clip; "loop": false plays once
  favorites copy  favorites_folder.render_copy(id, seconds) loops a GIF's render copy to fill its stretch (one play
                  held its last frame, a still, for the rest of it)
  editor          the visual editor's GIF stays a looping clear video as long as its line (the route that worked)

Run: python3 product/tests/test_buyer_reports_2026_10_28.py
"""
import json, os, shutil, subprocess, sys, tempfile

os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {str(detail)[:600]}"))
    if not cond:
        fails.append(name)


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,pix_fmt:stream_tags=alpha_mode:format=duration", "-of", "json", path],
                         capture_output=True, text=True).stdout
    o = json.loads(out or "{}")
    st = (o.get("streams") or [{}])[0]
    return {"codec": st.get("codec_name") or "", "pix": st.get("pix_fmt") or "",
            "alpha_mode": str((st.get("tags") or {}).get("alpha_mode") or (st.get("tags") or {}).get("ALPHA_MODE") or ""),
            "dur": float((o.get("format") or {}).get("duration") or 0)}


def _frames(path, vpx=False):
    """Every frame's checksum, in order (decoded as RGBA, so the alpha plane counts)."""
    out = subprocess.run(["ffmpeg", "-v", "error"] + (["-c:v", "libvpx-vp9"] if vpx else []) + ["-i", path,
                          "-map", "0:v:0", "-pix_fmt", "rgba", "-f", "framemd5", "-"], capture_output=True, text=True).stdout
    return [ln.rsplit(",", 1)[-1].strip() for ln in out.splitlines() if ln and not ln.startswith("#")]


def _alpha_range(path, at):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at}", "-i", path, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgba", "-"], capture_output=True).stdout
    a = raw[3::4]
    return (min(a), max(a)) if a else (None, None)


def make_gif(path, frames=12, rate=10):
    """A see-through animated GIF: a moving test pattern inside a circle, clear around it (1.2 s, 12 frames)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=s=120x96:r={rate}:d={frames / rate},format=rgba,"
                    "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(hypot(X-60,Y-48),40),255,0)'",
                    "-filter_complex", "[0]split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=alpha_threshold=128",
                    "-loop", "0", path], check=True)


def capcut_routes(tmp, gif, still):
    import capcut_alpha, capcut_media
    check("moving picture: a GIF with frames moves", capcut_alpha.moving_image(gif))
    check("moving picture: a one-frame GIF is a still", not capcut_alpha.moving_image(still))
    disguised = os.path.join(tmp, "image_3f2a.png")                  # how VectCut names the copy in the draft
    shutil.copyfile(gif, disguised)
    check("moving picture: judged by its bytes, not its name", capcut_alpha.moving_image(disguised))

    clip = capcut_alpha.looped_clip(gif, 4.0)
    p = _probe(clip)
    fr = _frames(clip)
    check("looped clip: ProRes 4444 with its alpha", p["codec"] == "prores" and capcut_alpha.has_alpha(p["pix"]), p)
    check("looped clip: fills the whole stretch, not one play", abs(p["dur"] - 4.0) < 0.1, p["dur"])
    check("looped clip: moves (more than one picture)", len(set(fr)) > 1, len(set(fr)))
    check("looped clip: plays its loop again (frame 0 comes back after 1.2 s)", len(fr) > 40 and fr[0] == fr[36], (len(fr), fr[:1], fr[36:37]))
    check("looped clip: see-through kept", _alpha_range(clip, 0.5) == (0, 255), _alpha_range(clip, 0.5))
    check("looped clip: tagged straight, so the CapCut pass leaves it as it is", not capcut_alpha.needs_preparing(clip))
    check("looped clip: one play when no length is given", abs(_probe(capcut_alpha.looped_clip(gif))["dur"] - 1.2) < 0.1)

    def draft(name, kind, rel, fresh, from_outside=None):
        D = os.path.join(tmp, name)
        os.makedirs(os.path.join(D, "assets", "image"), exist_ok=True)
        os.makedirs(os.path.join(D, "assets", "video"), exist_ok=True)
        with open(os.path.join(D, "draft_meta_info.json"), "w", encoding="utf-8") as f:
            json.dump({"draft_materials": []}, f)
        tok = capcut_media.DEFAULT_TOKEN
        if from_outside:
            path = from_outside
        else:
            shutil.copyfile(gif, os.path.join(D, rel))
            path = f"##_draftpath_placeholder_{tok}_##/{rel}"
        d = {"materials": {"videos": [{"id": "g1", "type": kind, "path": path, "material_name": os.path.basename(rel),
                                       "duration": 10800000000 if kind == "photo" else 1200000, "width": 120, "height": 96}],
                           "audios": []},
             "tracks": [{"type": "video", "segments": [{"material_id": "g1",
                                                         "source_timerange": {"start": 0, "duration": 3_500_000},
                                                         "target_timerange": {"start": 2_000_000, "duration": 3_500_000}}]}]}
        probs = capcut_media.ensure_shippable(d, D, fresh=fresh)
        return D, d["materials"]["videos"][0], probs

    D, m, probs = draft("pic", "photo", "assets/image/image_3f2a.png", True)
    real = capcut_media.real_path(m["path"], D, capcut_media.DEFAULT_TOKEN)
    check("capcut picture: the draft ships", probs == [], probs)
    check("capcut picture: the photo material is a video now", m["type"] == "video", m["type"])
    check("capcut picture: its file is a .mov in assets/video", m["path"].endswith(".mov") and "/assets/video/" in m["path"]
          and os.path.isfile(real), m["path"])
    check("capcut picture: long enough for its whole stretch", m["duration"] >= 3_500_000, m["duration"])
    check("capcut picture: and it moves", len(set(_frames(real))) > 1)
    check("capcut picture: see-through kept", _alpha_range(real, 2.0) == (0, 255), _alpha_range(real, 2.0))
    meta = json.load(open(os.path.join(D, "draft_meta_info.json"), encoding="utf-8"))
    reg = [it for g in meta["draft_materials"] for it in g["value"] if it.get("id") == "g1"]
    check("capcut picture: registered under its new file", reg and reg[0]["file_Path"].endswith(".mov"), reg)

    D, m, probs = draft("clip", "video", "assets/video/video_9c1d.mp4", True)
    check("capcut clip: GIF bytes named .mp4 become a looping .mov", probs == [] and m["path"].endswith(".mov")
          and m["duration"] >= 3_500_000, (probs, m))

    D, m, probs = draft("opened", "photo", "assets/image/image_3f2a.png", False)
    check("opened draft: a GIF already in her draft is left as it is", m["type"] == "photo"
          and m["path"].endswith("image_3f2a.png"), m)

    D, m, probs = draft("outside", "photo", "x", False, from_outside=gif)
    check("capcut picture from outside the draft: brought in as a looping clip", probs == [] and m["type"] == "video"
          and os.path.isfile(capcut_media.real_path(m["path"], D, capcut_media.DEFAULT_TOKEN)), (probs, m))


def drop_ins(tmp, gif):
    import gif_dropins
    out = os.path.join(tmp, "gif_0.mov")
    gif_dropins._to_clip(gif, 3.0, True, out)
    p = _probe(out)
    import capcut_alpha
    check("drop-ins: see-through, not an opaque mp4", p["codec"] == "prores" and capcut_alpha.has_alpha(p["pix"]), p)
    check("drop-ins: loops for its whole stretch", abs(p["dur"] - 3.0) < 0.1, p["dur"])
    once = os.path.join(tmp, "gif_1.mov")
    gif_dropins._to_clip(gif, 3.0, False, once)
    check('drop-ins: "loop": false plays once', abs(_probe(once)["dur"] - 1.2) < 0.1, _probe(once)["dur"])


def favorites_copy(tmp, gif):
    import favorites_folder as F
    was = F.FOLDER, F.CACHE
    F.FOLDER, F.CACHE = os.path.join(tmp, "favorites"), os.path.join(tmp, "fav-cache")
    try:
        os.makedirs(os.path.join(F.FOLDER, "gifs"))
        shutil.copyfile(gif, os.path.join(F.FOLDER, "gifs", "wave.gif"))
        one = F.render_copy("folder:gifs/wave.gif")
        check("favorites copy: one play when no length is given", abs(_probe(one)["dur"] - 1.2) < 0.15, _probe(one)["dur"])
        long = F.render_copy("folder:gifs/wave.gif", 5.0)
        fr = _frames(long)
        check("favorites copy: looped to fill its stretch", abs(_probe(long)["dur"] - 5.0) < 0.15, _probe(long)["dur"])
        check("favorites copy: still moving at the end", len(set(fr[len(fr) // 2:])) > 1)
        check("favorites copy: the same length again comes from the cache", F.render_copy("folder:gifs/wave.gif", 5.0) == long)
    finally:
        F.FOLDER, F.CACHE = was


def editor(tmp, gif):
    import visual_editor as ve
    jd = os.path.join(tmp, "projects", "gif-reel")
    os.makedirs(os.path.join(jd, "assets", "media"))
    os.makedirs(os.path.join(jd, "hf-graphics", "_looks", "w3"))
    shutil.copyfile(gif, os.path.join(jd, "assets", "media", "w3-wave.gif"))
    with open(os.path.join(jd, "hf-graphics", "_looks", "w3", "media.json"), "w", encoding="utf-8") as f:
        json.dump({"media": "gifs/wave.gif", "file": "assets/media/w3-wave.gif", "kind": "GIF",
                   "box": {"left": 340, "top": 600, "w": 400, "h": 320}}, f)
    page = os.path.join(tmp, "page")
    ve._draw_media(jd, "w3", "gifs/wave.gif", 3.0, page=page)
    clip = os.path.join(page, "assets", "media.webm")
    p = _probe(clip)
    fr = _frames(clip, vpx=True)
    html = open(os.path.join(page, "index.html"), encoding="utf-8").read()
    check("editor: the GIF is a clip on its page, not a picture", '<video id="mv"' in html and "<img" not in html)
    check("editor: the clip runs the whole line", abs(p["dur"] - 3.0) < 0.1, p["dur"])
    check("editor: see-through (VP9 alpha)", p["alpha_mode"] == "1", p)
    check("editor: loops (more frames than one play, and it moves)", len(fr) > 12 and len(set(fr)) > 1, len(fr))


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_buyer_reports_2026_10_28: skipped (ffmpeg/ffprobe not installed)")
        return 0
    tmp = tempfile.mkdtemp(prefix="buyer-1028-")
    was = os.environ.get("REEL_CAPCUT_ALPHA_CACHE")
    os.environ["REEL_CAPCUT_ALPHA_CACHE"] = os.path.join(tmp, "alpha-cache")
    try:
        gif, still = os.path.join(tmp, "wave.gif"), os.path.join(tmp, "dot.gif")
        make_gif(gif)
        make_gif(still, frames=1)
        for name, fn, args in (("capcut", capcut_routes, (tmp, gif, still)), ("drop-ins", drop_ins, (tmp, gif)),
                               ("favorites copy", favorites_copy, (tmp, gif)), ("editor", editor, (tmp, gif))):
            print(name)
            try:
                fn(*args)
            except Exception as e:                           # one part breaking never hides the others' results
                check(f"{name}: ran to the end", False, repr(e))
    finally:
        if was is None:
            os.environ.pop("REEL_CAPCUT_ALPHA_CACHE", None)
        else:
            os.environ["REEL_CAPCUT_ALPHA_CACHE"] = was
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_buyer_reports_2026_10_28: {len(fails)} of {total} checks FAILED")
        return 1
    print(f"test_buyer_reports_2026_10_28: all {total} checks passed")
    return 0


def test_buyer_reports_2026_10_28():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
