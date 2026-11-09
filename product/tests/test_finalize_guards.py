#!/usr/bin/env python3
"""test_finalize_guards.py — the builders' finalize(), past the point where the draft gets its name.

Three things it pins, on BOTH builders (cleanyap.py and superyap.py):
  1. A CapCut opened while finalize was busy (the face measurement can take many minutes per clip) is caught
     again right before the draft is written, and the half-built folder does not keep the name.
  2. A CapCut that has never been opened has no root_meta_info.json yet. That is an empty list, not a crash:
     the build registers into a new one. And any failure after the rename hands the name back, so the next
     build to it is not refused as "existing work".
  3. Thought-bubble line spacing reaches a buyer's pack thought font (and a spacing taught with /learn), while
     the creator's own reels, which pass her personal marker font, come out exactly as before.

Everything runs in a temp HOME with VectCut and the CapCut process check stubbed, so the real CapCut, its
drafts and the network are never touched. Needs ffmpeg/ffprobe (it makes a two-second clip); skips without.
Run: python3 product/tests/test_finalize_guards.py
"""
import json, os, shutil, subprocess, sys, tempfile, types

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
    print("· finalize guards: skipped (needs ffmpeg and ffprobe)")
    sys.exit(0)

HOME = tempfile.mkdtemp(prefix="finalize-guards-")
os.environ["HOME"] = HOME                                   # every CapCut path below resolves in here
os.environ["LOCALAPPDATA"] = os.path.join(HOME, "AppData", "Local")
os.environ["REEL_NO_DEFAULT_MOTION"] = "1"                  # no face measurement: motion is not under test
PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
for name in ("requests",):                                  # VectCut's HTTP client: stubbed, never called
    sys.modules.setdefault(name, types.ModuleType(name))
if "PIL" not in sys.modules:
    try:
        import PIL.Image  # noqa: F401
    except Exception:
        pil = types.ModuleType("PIL"); pil.Image = types.ModuleType("PIL.Image")
        sys.modules["PIL"], sys.modules["PIL.Image"] = pil, pil.Image

import draft_safety
STATE = {"open": False}
draft_safety.capcut_running = lambda: STATE["open"]
draft_safety._snap_file = lambda: os.path.join(HOME, ".draft-snapshots.json")   # not the engine's own record
import capcut_front
capcut_front.capcut_running = lambda: STATE["open"]
import learned
learned.STORE = os.path.join(HOME, "learned.json")          # none of her taught values: they would change the result
import cleanyap, superyap, packbuild, capcut_media, capcut_motion, capcut_color

MEDIA = os.path.join(HOME, "media")
os.makedirs(MEDIA)
CLIP = os.path.join(MEDIA, "clip.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=108x192:d=2:r=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", CLIP], check=True)

TEXTS = ["why your\nreels are stuck", "start with a cold\nopen instead"]
failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


def vectcut_draft(mod, did):
    """A draft as VectCut leaves it after save_draft: absolute asset paths inside its own id-named folder."""
    folder = os.path.join(mod.CAP, did)
    os.makedirs(os.path.join(folder, "assets", "video"))
    clip = os.path.join(folder, "assets", "video", "clip.mp4")
    shutil.copyfile(CLIP, clip)
    texts = [{"id": f"T{i}", "type": "text", "line_spacing": 0.02, "alignment": 0,
              "content": json.dumps({"text": t, "styles": [{"range": [0, len(t)], "size": 12,
                                                            "font": {"path": "Inter_Black", "id": ""}}]})}
             for i, t in enumerate(TEXTS)]
    seg = {"id": "S0", "material_id": "V0", "extra_material_refs": [], "render_index": 0,
           "source_timerange": {"start": 0, "duration": 2_000_000},
           "target_timerange": {"start": 0, "duration": 2_000_000},
           "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}},
           "uniform_scale": {"on": True, "value": 1.0}, "common_keyframes": []}
    tsegs = [{"id": f"TS{i}", "material_id": f"T{i}", "extra_material_refs": [], "render_index": 15000,
              "source_timerange": {"start": 0, "duration": 900_000},
              "target_timerange": {"start": i * 1_000_000, "duration": 900_000},
              "clip": {"scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.5}}} for i in range(2)]
    d = {"id": did, "duration": 2_000_000, "fps": 30.0, "config": {}, "canvas_config": {"width": 1080, "height": 1920},
         "materials": {"videos": [{"id": "V0", "path": clip, "material_name": "clip.mp4", "duration": 2_000_000,
                                   "width": 108, "height": 192, "type": "video"}],
                       "audios": [], "texts": texts, "material_animations": []},
         "tracks": [{"id": "MAIN", "type": "video", "flag": 0, "name": "", "is_default_name": True, "segments": [seg]},
                    {"id": "TXT", "type": "text", "flag": 0, "name": "", "is_default_name": True, "segments": tsegs}]}
    with open(draft_safety.draft_json(folder), "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    with open(os.path.join(folder, "draft_meta_info.json"), "w", encoding="utf-8") as fh:
        json.dump({"draft_id": "META-ID", "draft_materials": []}, fh)
    return folder


def run(mod, name, fonts, registry=True, **kw):
    """finalize() one fresh draft; returns (error or None, final folder, {text: line_spacing})."""
    shutil.rmtree(mod.CAP, ignore_errors=True)
    os.makedirs(mod.CAP)
    capcut_front.CAP = mod.CAP
    capcut_front.META = os.path.join(mod.CAP, "root_meta_info.json")
    capcut_front.STATE_DIR = HOME
    capcut_front.STATE = os.path.join(HOME, "capcut-front.json")
    if registry:
        with open(os.path.join(mod.CAP, "root_meta_info.json"), "w", encoding="utf-8") as fh:
            json.dump({"all_draft_store": [], "draft_ids": 0, "root_path": mod.CAP}, fh)
    did = "dfd_cat_1790000000_guard"
    vectcut_draft(mod, did)
    mod.call = lambda ep, _strict=True, **k: {"success": True, "output": {}}
    err = None
    try:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            mod.finalize(did, name, dict(zip(TEXTS, fonts)), fallback_font=fonts[0], **kw)
    except BaseException as e:  # noqa: BLE001
        err = e
    folder = os.path.join(mod.CAP, name)
    spacing = {}
    if os.path.exists(draft_safety.draft_json(folder)):
        d = json.load(open(draft_safety.draft_json(folder), encoding="utf-8"))
        spacing = {json.loads(m["content"])["text"]: m.get("line_spacing") for m in d["materials"]["texts"]}
    return err, folder, spacing


def registered(mod, name):
    p = os.path.join(mod.CAP, "root_meta_info.json")
    if not os.path.exists(p):
        return False
    return any(e.get("draft_name") == name for e in json.load(open(p, encoding="utf-8")).get("all_draft_store", []))


personal = [f"{cleanyap.FONTS_DIR}/Advercase-Bold.otf", cleanyap.FONT_THOUGHT]   # the creator's own pair
butter = [packbuild.role("Butter", "headline")["font_path"], packbuild.role("Butter", "thought")["font_path"]]

for mod in (cleanyap, superyap):
    tag = mod.__name__

    # 1) CapCut opened while finalize was busy: refused before the draft is written, name handed back
    # The trigger is a step every build takes (the SDR sweep, right before the final check), not the default
    # motion: a build can skip motion on purpose (a your-turn cut, a baked reel), and then CapCut never "opened".
    real_sdr = capcut_color.enforce_sdr
    def opened_meanwhile(d, *a, **k):
        STATE["open"] = True
        return real_sdr(d, *a, **k)
    capcut_color.enforce_sdr = opened_meanwhile
    err, folder, _ = run(mod, "Opened Meanwhile 1.1", butter)
    capcut_color.enforce_sdr = real_sdr
    STATE["open"] = False
    check(isinstance(err, draft_safety.CapCutOpen), f"{tag}: a CapCut opened mid-build must stop it, got {err!r}")
    check(not os.path.isdir(folder), f"{tag}: the refused build left a folder squatting its name")
    check(not registered(mod, "Opened Meanwhile 1.1"), f"{tag}: the refused build was registered")

    # 2a) no root_meta_info.json yet (CapCut never opened): builds and registers into a new list
    err, folder, _ = run(mod, "First Ever 1.1", butter, registry=False)
    check(err is None, f"{tag}: a first build on a CapCut with no list yet failed: {err!r}")
    check(registered(mod, "First Ever 1.1"), f"{tag}: the first build did not land in CapCut's list")

    # 2b) anything failing after the rename hands the name back
    real_cover = capcut_media.write_cover
    def disk_gone(*a, **k):
        raise OSError("disk went away")
    capcut_media.write_cover = disk_gone
    err, folder, _ = run(mod, "Fails Late 1.1", butter)
    capcut_media.write_cover = real_cover
    check(isinstance(err, OSError), f"{tag}: the late failure should surface as itself, got {err!r}")
    check(not os.path.isdir(folder), f"{tag}: a build that failed after the rename kept the name")

    # 3) thought spacing: the buyer's pack thought font gets it; the hook in another font does not
    for how, kw in (("recorded", {}), ("pack=", {"pack": "Butter"})):
        if how == "recorded":
            cleanyap.thought_font("Butter")                 # a driver taking its fonts the documented way
        else:
            getattr(cleanyap, "_THOUGHT_FONTS", set()).clear()
        try:
            err, folder, spacing = run(mod, f"Thought Spacing {how} 1.1", butter, **kw)
        except TypeError as e:                          # an engine whose finalize takes no pack=
            err, folder, spacing = e, "", {}
        check(err is None, f"{tag}: buyer build ({how}) failed: {err!r}")
        check(spacing.get(TEXTS[1]) == -0.15, f"{tag}: the pack's thought font did not get the tight spacing ({how}): {spacing}")
        check(spacing.get(TEXTS[0]) == 0.02, f"{tag}: the hook's spacing changed ({how}): {spacing}")
    getattr(cleanyap, "_THOUGHT_FONTS", set()).clear()

    # 3b) the creator's own reels: exactly as before (cleanyap applies it to her marker font; superyap never did)
    err, folder, spacing = run(mod, "Her Own 1.1", personal)
    check(err is None, f"{tag}: her own build failed: {err!r}")
    want = -0.15 if mod is cleanyap else 0.02
    check(spacing.get(TEXTS[1]) == want, f"{tag}: her own thought font spacing changed: {spacing}")
    check(spacing.get(TEXTS[0]) == 0.02, f"{tag}: her own hook spacing changed: {spacing}")

shutil.rmtree(HOME, ignore_errors=True)
if failures:
    print("✗ finalize guards: " + "; ".join(failures))
    sys.exit(1)
print("✓ finalize guards: a CapCut opened mid-build is caught before the write, a first-ever CapCut gets a new "
      "list, a late failure hands the name back, and thought spacing reaches the pack's font (her own reels unchanged)")
