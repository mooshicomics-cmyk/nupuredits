#!/usr/bin/env python3
"""test_capcut_live.py — the CapCut bridge's decisions, checked without CapCut, a screen or pyobjc.

workflows/capcut-live.py drives a real app, so its full behaviour is proven elsewhere against a recorded
fake CapCut. This pins the decisions inside it that each broke once:
  • `--track` picks tracks by what they hold. A VectCut-built draft carries flag 0 on every track, so a flag
    test found no text or overlay there and let `remove --track footage` delete a caption or a sound.
  • `open` matches a draft's exact name ("Reel 1.1" double-clicked "Reel 1.12").
  • `new-draft` gives the draft a canvas shaped like the footage as it plays (an upright phone clip is 9:16).
  • `place-plan` counts a graphic planned at 0 s and puts overlapping graphics on separate layers.
  • `layer --layer N` onto a track already playing a clip then gets a NEW track at that place in the stack
    (it used to drop the clip onto the busy track: two clips at one moment on one track, which CapCut can't show),
    with render_index / track_render_index kept in step and nothing lifted over her grade.
  • Two different files sharing a name (a graphic and her cutout, both l09-editor.mov) become two Resources files
    and two materials; one copy used to stand in for both, so her cutout never appeared.
  • On Windows a draft write never force-kills CapCut (it refuses instead) and nothing calls osascript.
  • A write that stops part-way opens CapCut again if it was the bridge that closed it.
  • Every older command name runs the same handler as its new one, and `--track main` still means her footage.
  • A live wait returns the moment its condition holds and stops with a plain sentence at its limit; the export
    presses its dialog's controls by id, and a dialog without them stops the export instead of a guessed click.
Run: python3 product/tests/test_capcut_live.py
"""
import importlib.util, json, os, subprocess, sys, tempfile, types
from pathlib import Path

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.name != "nt":   # the bridge imports the Mac accessibility frameworks at load; stand-ins keep it importable
    for mod, names in (("ApplicationServices", ["AXUIElementCopyAttributeValue", "AXUIElementCreateApplication",
                                                "AXValueGetValue", "kAXValueCGPointType", "kAXValueCGSizeType"]),
                       ("Quartz", ["CGEventCreateKeyboardEvent", "CGEventCreateMouseEvent", "CGEventPost",
                                   "CGEventSetFlags", "CGEventSetIntegerValueField", "kCGEventFlagMaskCommand",
                                   "kCGEventFlagMaskShift", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp",
                                   "kCGEventMouseMoved", "kCGHIDEventTap", "kCGMouseButtonLeft",
                                   "kCGMouseEventClickState"])):
        if mod not in sys.modules:
            m = types.ModuleType(mod)
            for n in names:
                setattr(m, n, (lambda *a, **k: None) if n[0] != "k" else 0)
            sys.modules[mod] = m
spec = importlib.util.spec_from_file_location("capcut_live", os.path.join(ENGINE, "workflows", "capcut-live.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


def track(kind, flag, n, default=True):
    return {"type": kind, "flag": flag, "is_default_name": default, "segments": [{"i": i} for i in range(n)]}


# 1) --track by what a track holds
vectcut_tracks = [track("video", 0, 3, default=False), track("video", 0, 1), track("audio", 0, 7),
                  track("text", 0, 2), track("text", 0, 1)]
vectcut = {"tracks": vectcut_tracks}
check(bridge.role_tracks(vectcut, "main") == [vectcut_tracks[0]], "main must be the footage track only")
check(bridge.role_tracks(vectcut, "overlay") == [vectcut_tracks[1]], "overlay must be the other video track")
check(bridge.role_tracks(vectcut, "text") == vectcut_tracks[3:], "text must be both text tracks")
check([bridge.track_label(vectcut, t) for t in vectcut_tracks] == ["footage", "overlay", "audio", "text", "text"],
      "timeline must label tracks the way --track names them")
native_tracks = [track("video", 0, 1, default=False), track("video", 2, 5), track("audio", 0, 2)]
check(bridge.main_track({"tracks": native_tracks}) is native_tracks[0], "a flag-2 overlay with more clips is still not main")

# 2) canvas shaped like the footage as it plays
for probed, rotation, want in (((3840, 2160, 1, True), -90, (1080, 1920)), ((1920, 1080, 1, True), 0, (1920, 1080)),
                               ((1080, 1920, 1, True), 0, (1080, 1920)), ((1728, 3072, 1, True), 0, (1080, 1920)),
                               ((2160, 3840, 1, True), 90, (1920, 1080)), ((0, 0, 1, True), 0, (1920, 1080))):
    got = bridge.canvas_for(probed, rotation)
    check(got == want, f"canvas for {probed[:2]} turned {rotation}: {got}, wanted {want}")

# 3) overlapping graphics go up a layer; touching ones share it
stacked = {"tracks": [track("video", 0, 1, default=False),
                      {"type": "video", "flag": 2, "segments": [{"target_timerange": {"start": 0, "duration": 2_000_000}}]}]}
check(bridge.free_layer(stacked, 1_000_000, 500_000) == 2, "an overlapping graphic must take the next layer")
check(bridge.free_layer(stacked, 2_000_000, 500_000) == 1, "a graphic that only touches may share the layer")
check(bridge.free_layer({"tracks": []}, 0, 1) == 1, "with no overlay tracks, layer 1")

# 4) open matches the exact name, and a title's tile is the one it sits inside
def seen(label, box, holder=None, depth=3):
    s_ = bridge.Seen(label, label, depth, holder)
    s_._box = box
    return s_


screen = object.__new__(bridge.Screen)
tile_a, tile_b = seen("HomePageDraft", (0, 0, 100, 100)), seen("HomePageDraft", (120, 0, 100, 100))
screen.seen = [tile_a, seen("HomePageDraftTitle:Reel 1.12", (130, 90, 10, 10), tile_a),
               tile_b, seen("HomePageDraftTitle:Reel 1.1", (20, 90, 10, 10), tile_b)]
hit = screen.draft_title("Reel 1.1")
check(hit is not None and hit.label == "HomePageDraftTitle:Reel 1.1", f"open 'Reel 1.1' must pick that tile, got {hit}")
check(screen.draft_title("Reel 1") is None, "a partial name must not open the first draft that contains it")
check(screen.tile_of(hit) is tile_b, "a title's tile is the tile it sits inside, even where another tile spans it")
loose = seen("HomePageDraftTitle:Loose", (30, 90, 10, 10))
check(screen.tile_of(loose) is None, "a title inside no tile has no tile: nothing is guessed from where it sits")

# 5) a graphic planned at 0 s is placed; overlapping ones are given free layers
tmp = tempfile.mkdtemp(prefix="bridge-test-")
job = Path(tmp, "projects", "gfx")
(job / "assets").mkdir(parents=True)
for f in ("a.mov", "b.mov"):
    (job / "assets" / f).write_bytes(b"x")
with open(job / "graphics-plan.json", "w", encoding="utf-8") as fh:
    json.dump({"graphics": [{"file": "a.mov", "start": 0}, {"file": "b.mov", "t": 0.0, "start": None}]}, fh)
laid = []
real_repo, real_editing, real_lay = bridge.REPO, bridge.building_on, bridge.lay_graphic
bridge.REPO = Path(tmp)
import contextlib


@contextlib.contextmanager
def fake_editing(name):
    yield {"tracks": []}, Path(tmp)


bridge.building_on = fake_editing
bridge.lay_graphic = lambda d, folder, media, at_us, layer, length_us=None: laid.append((Path(media).name, at_us, layer)) or (1, "existing")
try:
    bridge.place_plan("Draft", "gfx")
finally:
    bridge.REPO, bridge.building_on, bridge.lay_graphic = real_repo, real_editing, real_lay
check(laid == [("a.mov", 0, None), ("b.mov", 0, None)], f"graphics at 0 s must be placed, each on a free layer: {laid}")

# 6) Windows: no osascript, and a write refuses instead of killing CapCut
os.environ.pop("CAPCUT_ALLOW_OPEN", None)
ran = []
real_run = subprocess.run
subprocess.run = lambda args, *a, **k: ran.append(list(args)) or subprocess.CompletedProcess(args, 0, "", "")
real_win = bridge.ON_WINDOWS
real_running = bridge._ds.capcut_running
try:
    bridge.ON_WINDOWS = True
    bridge.tell_capcut("activate")
    check(not any(r[0] == "osascript" for r in ran), "on Windows nothing may call osascript")
    bridge._ds.capcut_running = lambda: True
    try:
        bridge.close_for_write("change this draft")
        check(False, "on Windows a write with CapCut open must refuse")
    except bridge._ds.CapCutOpen:
        pass
    check(not any(r[0] == "taskkill" for r in ran), f"on Windows a write must never kill CapCut: {ran}")
finally:
    subprocess.run = real_run
    bridge.ON_WINDOWS = real_win
    bridge._ds.capcut_running = real_running

# 7) a write that stops part-way gives her CapCut back (Mac: the bridge closed it, so it opens it again)
folder = Path(tmp, "Draft")
folder.mkdir()
with open(bridge._ds.draft_json(str(folder)), "w", encoding="utf-8") as fh:
    json.dump({"tracks": [], "duration": 0}, fh)
events = []
saved = (bridge.existing_draft, bridge.capcut_process, bridge.close_capcut, bridge.open_capcut, bridge.ON_WINDOWS,
         bridge._ds.require_capcut_quit)
bridge.existing_draft = lambda name: folder
bridge.capcut_process = lambda: 4321
bridge.close_capcut = lambda timeout=20: events.append("quit")
bridge.open_capcut = lambda: events.append("start")
bridge.ON_WINDOWS = False
bridge._ds.require_capcut_quit = lambda action="": None
try:
    with bridge.building_on("Draft") as (_d, _f):
        raise SystemExit("that overlay is already on the timeline")
except SystemExit:
    pass
finally:
    (bridge.existing_draft, bridge.capcut_process, bridge.close_capcut, bridge.open_capcut, bridge.ON_WINDOWS,
     bridge._ds.require_capcut_quit) = saved
check(events == ["quit", "start"], f"a refused edit must reopen the CapCut it closed: {events}")

# 8) an explicit --layer never lands on a busy track: a new track goes in at that place in the stack
US = 1_000_000


def seg(start, end, ri, tri):
    return {"target_timerange": {"start": round(start * US), "duration": round((end - start) * US)},
            "render_index": ri, "track_render_index": tri}


def busy_draft():
    """Laid out like the draft the bug was seen on: footage, her grade, cards on layer 1, a long clip on layer 2,
    a third layer, then text and sound."""
    tracks = [{"type": "video", "flag": 0, "is_default_name": False, "segments": [seg(0, 50, 0, 0), seg(50, 112.57, 0, 0)]},
              {"type": "filter", "flag": 0, "segments": [seg(0, 112.57, 10000, 1)]},
              {"type": "adjust", "flag": 0, "segments": [seg(0, 112.57, 0, 2)]},
              {"type": "video", "flag": 2, "segments": [seg(15.3, 26, 2, 3), seg(51.07, 55.77, 2, 3), seg(70, 80, 2, 3)]},
              {"type": "video", "flag": 2, "segments": [seg(0, 7.27, 3, 4), seg(55.8, 112.37, 3, 4)]},
              {"type": "video", "flag": 2, "segments": [seg(15.43, 55.8, 4, 5)]},
              {"type": "text", "flag": 0, "segments": [seg(0.8, 13.47, 14000, 6)]},
              {"type": "audio", "flag": 0, "segments": [seg(8.9, 112.57, 0, 7)]}]
    return {"tracks": tracks, "materials": {k: [] for k in ("videos", *bridge.SEGMENT_HELPERS)}}


def overlaps(draft):
    for t in draft["tracks"]:
        spans = sorted((x["target_timerange"]["start"], x["target_timerange"]["start"] + x["target_timerange"]["duration"])
                       for x in t["segments"])
        if any(b[0] < a[1] for a, b in zip(spans, spans[1:])):
            return True
    return False


def indexes_follow_track_order(draft):
    return all(x["track_render_index"] == i for i, t in enumerate(draft["tracks"]) for x in t["segments"])


def stacked_order(draft):
    """Each overlay track's render_index, bottom to top; one value per track, or the track mixes two."""
    return [sorted({x["render_index"] for x in t["segments"]}) for t in bridge._overlay_stack(draft)]


real_into, real_probe = bridge.media_into, bridge.probe_video
bridge.media_into = lambda folder, source: Path(source)
bridge.probe_video = lambda path: (1080, 1920, round(7.4 * US), False)
try:
    # --layer 2 at 66.15 s: layer 2 holds 55.8-112.37, so a new layer 2 goes in right above the cards track
    d = busy_draft()
    layer_2_before = d["tracks"][4]
    got = bridge.lay_graphic(d, Path(tmp), "lesson-scroll.mov", round(66.15 * US), 2)
    check(got == (2, "inserted"), f"--layer 2 on a busy track must insert a new layer 2: {got}")
    check(not overlaps(d), "no track may hold two clips at the same moment")
    check(len(layer_2_before["segments"]) == 2, "the busy track must keep only its own clips")
    check(d["tracks"][4]["segments"][0]["material_id"] == d["materials"]["videos"][-1]["id"],
          "the new track must sit directly above layer 1 (the cards)")
    check(bridge._overlay_stack(d)[1] is d["tracks"][4] and bridge._overlay_stack(d)[2] is layer_2_before,
          "the old layer 2 must move up to layer 3")
    check(indexes_follow_track_order(d), "every clip's track_render_index must follow its track's place")
    check(stacked_order(d) == [[2], [3], [4], [5]], f"stacking must run bottom to top, one value per track: {stacked_order(d)}")
    check(d["tracks"][1]["segments"][0]["render_index"] == 10000, "her grade layer must not move")
    check(d["tracks"][7]["type"] == "text" and d["tracks"][7]["segments"][0]["render_index"] == 14000,
          "text must keep its render_index")

    # --layer 1 at 66.15 s: the cards track plays 70-80, so a new layer 1 goes in right above the footage
    d = busy_draft()
    got = bridge.lay_graphic(d, Path(tmp), "cutout.mov", round(66.15 * US), 1)
    check(got == (1, "inserted"), f"--layer 1 on a busy track must insert a new layer 1: {got}")
    check(d["tracks"][1]["type"] == "video" and d["tracks"][1]["flag"] == 2, "the new layer 1 sits right above the footage")
    check(not overlaps(d) and indexes_follow_track_order(d), "layer 1: no overlaps, track indexes in order")
    check(stacked_order(d) == [[1], [2], [3], [4]], f"layer 1 must stack under the cards: {stacked_order(d)}")
    check(all(x["render_index"] < 10000 for t in bridge._overlay_stack(d) for x in t["segments"]),
          "nothing may be lifted over her grade")

    # a render_index already taken above is lifted with everything above it, so the order holds
    d = busy_draft()
    d["tracks"][3]["segments"] = [dict(x, render_index=1) for x in d["tracks"][3]["segments"]]
    d["tracks"][4]["segments"] = [dict(x, render_index=2) for x in d["tracks"][4]["segments"]]
    d["tracks"][5]["segments"] = [dict(x, render_index=3) for x in d["tracks"][5]["segments"]]
    bridge.lay_graphic(d, Path(tmp), "scroll.mov", round(66.15 * US), 2)
    check(stacked_order(d) == [[1], [2], [3], [4]], f"a taken render_index must lift the layers above: {stacked_order(d)}")

    # an explicit layer that is free then joins that track, taking the track's own indexes
    d = busy_draft()
    got = bridge.lay_graphic(d, Path(tmp), "early.mov", round(30 * US), 2)
    check(got == (2, "existing") and len(d["tracks"]) == 8, f"a free layer 2 must be used as it is: {got}")
    check(d["tracks"][4]["segments"][-1]["render_index"] == 3 and d["tracks"][4]["segments"][-1]["track_render_index"] == 4,
          "a clip joining a track takes that track's render_index and track_render_index")

    # no --layer: the free_layer path is unchanged (lowest free layer, never a new track in the middle)
    d = busy_draft()
    check(bridge.free_layer(d, round(66.15 * US), round(7.4 * US)) == 3, "free_layer must still pick layer 3 here")
    got = bridge.lay_graphic(d, Path(tmp), "auto.mov", round(66.15 * US), None)
    check(got == (3, "existing") and len(d["tracks"]) == 8 and not overlaps(d), f"no --layer takes the lowest free layer: {got}")
    d = busy_draft()
    got = bridge.lay_graphic(d, Path(tmp), "auto.mov", round(52 * US), None)   # every layer plays something then
    check(got == (4, "new") and d["tracks"][-1]["flag"] == 2 and not overlaps(d), f"all busy: a new layer on top: {got}")
    check(d["tracks"][-1]["segments"][0]["render_index"] == 5, "a new top layer stacks above every overlay")
finally:
    bridge.media_into, bridge.probe_video = real_into, real_probe

# 9) two DIFFERENT files sharing a name land as two Resources files and two materials (a graphic and her cutout,
#    both l09-editor.mov, once played the same picture); the same file laid twice is copied once
job9 = Path(tmp, "projects", "same-name")
for sub, body in (("hf-graphics", b"the graphic"), ("cutouts", b"her cutout, a different file")):
    (job9 / sub).mkdir(parents=True)
    (job9 / sub / "l09-editor.mov").write_bytes(body)
draft9_dir = Path(tmp, "Draft9")
draft9_dir.mkdir()
d = busy_draft()
bridge.probe_video = lambda path: (1080, 1920, round(2 * US), False)
try:
    bridge.lay_graphic(d, draft9_dir, job9 / "hf-graphics" / "l09-editor.mov", round(90 * US), None)
    bridge.lay_graphic(d, draft9_dir, job9 / "cutouts" / "l09-editor.mov", round(90 * US), None)
    bridge.lay_graphic(d, draft9_dir, job9 / "cutouts" / "l09-editor.mov", round(100 * US), None)
finally:
    bridge.probe_video = real_probe
paths = [Path(m["path"]) for m in d["materials"]["videos"]]
check(len(paths) == 3 and paths[0] != paths[1], f"two different files with one name must get two materials: {paths}")
check(sorted(p.name for p in (draft9_dir / "Resources").iterdir()) == ["l09-editor-2.mov", "l09-editor.mov"],
      f"two different files with one name must be two Resources files: {sorted(os.listdir(draft9_dir / 'Resources'))}")
check(paths[0].read_bytes() == b"the graphic" and paths[1].read_bytes() == b"her cutout, a different file",
      "each material must play its own file")
check(paths[2] == paths[1], "the same file laid twice must reuse its one copy")
taken, there = bridge._ds.media_slot(draft9_dir / "Resources" / "l09-editor.mov", job9 / "cutouts" / "l09-editor.mov")
check(there and Path(taken).name == "l09-editor-2.mov", f"media_slot must find the cutout's own copy: {taken}")
check((draft9_dir / "Resources" / "l09-editor.mov").read_bytes() == b"the graphic", "the graphic must never be overwritten")

# 10) older command names run the same handler as their new names; USAGE lists only the new ones
older = {"replay": "new-draft", "ls": "drafts", "graphics": "place-plan", "add-overlay": "layer", "add-text": "text",
         "transform": "move", "magnet": "fix-magnet", "verify-magnet": "check-magnet", "launch": "start",
         "seek": "go-to", "del": "delete", "zoomfit": "fit-timeline", "state": "timeline", "shot": "screenshot",
         "dump": "ids", "click": "click-id", "clickxy": "click-at"}
check(bridge.OLDER_NAMES == older, f"the older-name table changed: {bridge.OLDER_NAMES}")
for old, new in older.items():
    check(new in bridge.COMMANDS and bridge.COMMANDS.get(old) is bridge.COMMANDS[new],
          f"{old} must run the same handler as {new}")
usage_words = {part.split()[0] for line in bridge.USAGE.splitlines() if line.startswith("  ") and line.strip()
               for part in line.split(" · ") if part.strip() and not part.strip().startswith(("no --", "[", "-"))}
check(not usage_words & set(older), f"USAGE must list only the new names: {sorted(usage_words & set(older))}")
check(all(new in usage_words for new in older.values()), "USAGE must list every new name")
for kept in ("open", "quit", "select", "split", "delete", "trim-left", "trim-right", "undo", "redo", "save", "marker",
             "play", "export", "playhead", "clips", "remove", "key"):
    check(kept in bridge.COMMANDS, f"{kept} must still be a command")

# 11) --track main still means her footage, through remove and move; an unknown word still stops with KeyError
said = []


@contextlib.contextmanager
def footage_draft(name):
    d = {"tracks": [track("video", 0, 2, default=False), track("video", 2, 1), track("text", 1, 1)],
         "materials": {"videos": [], "texts": []}}
    for t_ in d["tracks"]:
        for s_ in t_["segments"]:
            s_.update(material_id="", clip={"scale": {"x": 1, "y": 1}, "transform": {"x": 0, "y": 0}})
    said.append(d)
    yield d, Path(tmp)


real_building = bridge.building_on
bridge.building_on = footage_draft
try:
    for word in ("main", "footage"):
        check(bridge.COMMANDS["remove"](["D", "--track", word, "--index", "1"]) == f"removed {word}[1]",
              f"remove --track {word} must say it back")
        check(len(said[-1]["tracks"][0]["segments"]) == 1 and len(said[-1]["tracks"]) == 3,
              f"remove --track {word} must take a clip off her footage track and keep the track")
        got = bridge.COMMANDS["transform"](["D", "--track", word, "--index", "0", "--y", "-0.25"])
        check(got == f"{word}[0] move: {{'y': -0.25}}" and said[-1]["tracks"][0]["segments"][0]["clip"]["transform"]["y"] == -0.25,
              f"move --track {word} must move her footage: {got}")
    check(bridge.COMMANDS["remove"](["D"]) == "removed footage[0]", "remove with no --track works on her footage")
    for handler in ("remove", "move"):
        try:
            bridge.COMMANDS[handler](["D", "--track", "bogus"])
            check(False, f"{handler} --track bogus must refuse")
        except KeyError as why:
            check(why.args == ("bogus",), f"{handler} --track bogus must raise KeyError('bogus'): {why!r}")
    check(bridge.role_tracks(vectcut, "footage") == bridge.role_tracks(vectcut, "main"), "footage and main are one role")
finally:
    bridge.building_on = real_building

# 12) text is set in her style pack: the pack's font, size, color and case, from shells that carry no look
#     and no machine path; text that would overlap other text gets its own track; with no pack it stops first
import packbuild, capcut_userfonts
real_font_path, real_resolve = packbuild.capcut_font_path, capcut_userfonts.resolve_font_file
packbuild.capcut_font_path = lambda src: src                 # never copy a font into CapCut's folder from a test
capcut_userfonts.resolve_font_file = lambda *a, **k: None    # never read CapCut's font cache from a test
try:
    for name in bridge.TEXT_SHELL_FILES:
        raw = (bridge.TEXT_SHELLS / name).read_text(encoding="utf-8")
        check("/Users/" not in raw and "\\Users\\" not in raw and ".otf" not in raw and ".ttf" not in raw,
              f"{name} must carry no machine path and no font")
    shells = bridge.text_shells()
    look = bridge.text_look("Butter", "headline")
    pack_spec = packbuild.role("Butter", "headline")
    d = {"tracks": [track("video", 0, 0, default=False)], "materials": {"videos": [], "texts": []}}
    shown = packbuild.caseit("Show up anyway", look["case"])
    check(bridge.lay_text(d, shown, 1_000_000, 2_000_000, look) == "first", "the first text clip makes a text track")
    material = d["materials"]["texts"][-1]
    content = json.loads(material["content"])
    run = content["styles"][0]
    check(" ".join(content["text"].split()) == "SHOW UP ANYWAY", f"the pack's case must apply: {content['text']!r}")
    check(run["font"]["path"] == pack_spec["font_path"] and material["font_path"] == pack_spec["font_path"],
          "the font must be the pack's")
    check(run["size"] == pack_spec["size"] and material["font_size"] == float(pack_spec["size"]), "the size must be the pack's")
    check(run["fill"]["content"]["solid"]["color"] == [1.0, 1.0, 1.0], "headline text is white")
    check(run["range"] == [0, len(content["text"])], "one style run over the whole text")
    check(set(material) == set(shells["text-look.json"]), "the material carries exactly the shell's keys")
    clip = d["tracks"][-1]["segments"][-1]
    check(set(clip) == set(shells["text-clip.json"]), "the clip carries exactly the shell's keys")
    check(clip["clip"]["transform"]["y"] == pack_spec["y"], "the clip sits at the pack's height for the role")
    check(clip["track_render_index"] == 1 and clip["extra_material_refs"] == [d["materials"]["material_animations"][-1]["id"]],
          "the clip knows its track's place and its animation slot")
    accent = bridge.text_look("Butter", "accent")
    want = packbuild.accent_color("Butter").lstrip("#")
    check(accent["rgb"] == tuple(int(want[i:i + 2], 16) / 255 for i in (0, 2, 4)), "the accent role takes the accent color")
    check(bridge.lay_text(d, "second", 3_000_000, 1_000_000, look) == "existing", "text after the first shares its track")
    check(bridge.lay_text(d, "overlap", 1_500_000, 1_000_000, look) == "new" and len(d["tracks"]) == 3,
          "text that would overlap other text gets a track of its own")
    check(bridge.already_placed(d, 1_000_000, text="SHOW UP ANYWAY"), "a wrapped line still counts as already placed")

    os.environ.pop("STYLE_PACK", None)
    touched = []
    real_active, real_building = bridge.active_pack, bridge.building_on
    bridge.active_pack = lambda named=None: named
    bridge.building_on = lambda name: touched.append(name)
    try:
        bridge.text_on("D", "hi", 1.0)
        check(False, "text with no pack must stop")
    except SystemExit as why:
        check("--pack" in str(why) and not touched, f"no pack: stop and ask, before CapCut is touched: {why}")
    finally:
        bridge.active_pack, bridge.building_on = real_active, real_building
    os.environ["STYLE_PACK"] = "Playful"
    check(bridge.active_pack() == "Playful" and bridge.active_pack("Butter") == "Butter", "--pack, then STYLE_PACK")
    os.environ.pop("STYLE_PACK", None)
finally:
    packbuild.capcut_font_path, capcut_userfonts.resolve_font_file = real_font_path, real_resolve

# 13) a new draft's platform block: the VectCut builders' own, with the installed CapCut's version when it can be read
real_version = bridge.installed_capcut_version
try:
    bridge.installed_capcut_version = lambda: "9.5.0"
    stamp = bridge.platform_stamp()
    check(stamp["app_version"] == "9.5.0" and stamp["os"] == ("windows" if bridge.ON_WINDOWS else "mac") and set(stamp) == set(bridge.PLATFORM_SHAPE),
          f"the stamp takes the installed version: {stamp}")
    vectcut = bridge._vectcut_platform()
    check(vectcut and stamp["app_id"] == vectcut["app_id"] and stamp["app_source"] == vectcut["app_source"],
          "app id and source come from the VectCut builders' block")
    bridge.installed_capcut_version = lambda: None
    check(bridge.platform_stamp()["app_version"] == vectcut["app_version"], "no readable version: the builders' own")
finally:
    bridge.installed_capcut_version = real_version
plist_home = Path(tmp, "home")
(plist_home / "Applications" / "CapCut.app" / "Contents").mkdir(parents=True)
import plistlib
with open(plist_home / "Applications" / "CapCut.app" / "Contents" / "Info.plist", "wb") as fh:
    plistlib.dump({"CFBundleShortVersionString": "9.9.1"}, fh)
real_home = Path.home
Path.home = classmethod(lambda cls: plist_home)
real_open = open
import builtins
builtins.open = lambda f, *a, **k: real_open(f, *a, **k) if not str(f).startswith("/Applications/") else (_ for _ in ()).throw(OSError("not here"))
try:
    if not bridge.ON_WINDOWS:
        check(bridge.installed_capcut_version() == "9.9.1", "the version is read from the app's Info.plist")
finally:
    builtins.open, Path.home = real_open, real_home
check("8.9.0" not in Path(bridge.__file__).read_text(encoding="utf-8"), "no CapCut version is written into the bridge")

# 14) a beat that stays on her face is never placed, even when a file with its id exists
job14 = Path(tmp, "projects", "plain")
(job14 / "assets").mkdir(parents=True)
for f in ("1.mov", "2.mov", "3.mov"):
    (job14 / "assets" / f).write_bytes(b"x")
with open(job14 / "graphics-plan.json", "w", encoding="utf-8") as fh:
    json.dump({"beats": [{"id": 1, "start": 0.5, "element": "word-card"}, {"id": 2, "start": 3.0, "element": "face"},
                         {"id": 3, "start": 4.0, "graphic": False}]}, fh)
check(list(bridge.planned_graphics(job14)) == [("1.mov", 0.5)], "a plain beat is never placed")

# 15) the live map: the walk reads the whole tree breadth first under its budget, ends early once a command's ids
#     are met, and `ids --map` reports each id's level and tells "renamed" ("missing") apart
class Node:
    def __init__(self, desc=None, kids=(), box=(1.0, 1.0, 10.0, 10.0)):
        self.desc, self.kids, self.box = desc, list(kids), box


chain = Node("MainWindowTitleBarExportBtn")
for _ in range(24):
    chain = Node(kids=[chain])
window = Node(kids=[Node("HomePageDraft", kids=[Node("HomePageDraftTitle:Reel 1.1")]), chain])
window.title = "CapCut"


class Point:
    def __init__(self, a, b):
        self.x = self.width = a
        self.y = self.height = b


def fake_ax(element, attribute):
    if attribute == "AXWindows":
        return [window]
    if attribute == "AXChildren":
        return element.kids or None
    if attribute == "AXTitle":
        return getattr(element, "title", None)
    if attribute == "AXDescription":
        return element.desc
    if attribute in ("AXPosition", "AXSize"):
        return (element.box[:2] if attribute == "AXPosition" else element.box[2:]) if element.box else None
    return None


saved_live = (bridge.ax, bridge.capcut_root, bridge.AXValueGetValue, bridge.installed_capcut_version,
              dict(bridge.LIVE_WALK), bridge.REPO)
bridge.ax = fake_ax
bridge.capcut_root = lambda: "app"
bridge.AXValueGetValue = lambda value, kind, out: (value is not None, Point(*value) if value else None)
bridge.installed_capcut_version = lambda: "9.5.0"
import io, contextlib as _cl
try:
    whole = bridge.Screen()
    check(whole.part("export_button") is not None and whole.deepest == 25 and whole.walked == 28,
          f"the walk has no depth limit: an id 25 levels down is read ({whole.deepest}, {whole.walked} elements)")
    check([seen.label for seen in whole.seen][:3] == ["CapCut", "HomePageDraft", "HomePageDraftTitle:Reel 1.1"],
          "breadth first: the window, then what is in it, then what is in that")
    early = bridge.Screen(needs=("HomePageDraft",))
    check(early.walked < whole.walked and early.part("draft_tile") is not None,
          f"a reading ends once its ids are met ({early.walked} of {whole.walked} elements)")
    check(bridge.Screen(depth=18).part("export_button") is None, "`ids --depth N` still caps what it lists")
    check(bridge.Screen().draft_title("Reel 1.1").holder.label == "HomePageDraft", "a title knows the tile it is in")
    report = io.StringIO()
    with _cl.redirect_stdout(report):
        bridge.COMMANDS["ids"](["--map"])
    text = report.getvalue()
    check("home screen" in text and "found    draft_title" in text and "level 2" in text,
          f"ids --map names the screen, what it found and at what level: {text}")
    bridge.LIVE_IDS["draft_title"] = "RenamedTitle:"
    report = io.StringIO()
    with _cl.redirect_stdout(report):
        bridge.COMMANDS["ids"](["--map", "--save", str(Path(tmp, "ids.json"))])
    check("missing  draft_title" in report.getvalue() and Path(tmp, "ids.json").exists(),
          f"a renamed id is reported missing, and --save keeps the walk: {report.getvalue()}")
    bridge.LIVE_IDS["draft_title"] = "HomePageDraftTitle:"
    window_kids = window.kids
    window.kids = [Node("MainTimeLineRoot"), chain]
    report = io.StringIO()
    with _cl.redirect_stdout(report):
        bridge.map_report()
    check("found    export_button" in report.getvalue() and "level 25" in report.getvalue(),
          f"an id deep in the tree is found and its level reported: {report.getvalue()}")
    report = io.StringIO()
    with _cl.redirect_stdout(report):
        bridge.map_report(depth=18)
    check("below    export_button" in report.getvalue(), f"--depth flags an id below it: {report.getvalue()}")
    window.kids = window_kids
    bridge.LIVE_WALK["walk_budget"] = 3
    short = bridge.Screen()
    check(short.walked == 3 and short.cut_short and short.part("export_button") is None,
          "the walk stops at its budget")
    report = io.StringIO()
    with _cl.redirect_stdout(report):
        bridge.map_report()
    check("budget of 3 elements" in report.getvalue(), f"ids --map says when the budget cut a walk short: {report.getvalue()}")
    (Path(tmp, "_local")).mkdir(exist_ok=True)
    Path(tmp, "_local", "capcut-live-map.json").write_text('{"walk_budget": 99}', encoding="utf-8")
    bridge.REPO = Path(tmp)
    bridge._apply_local_map()
    check(bridge.LIVE_WALK["walk_budget"] == 99, "a walk_budget in _local/capcut-live-map.json is used")
finally:
    bridge.ax, bridge.capcut_root, bridge.AXValueGetValue, bridge.installed_capcut_version, walk, bridge.REPO = saved_live
    bridge.LIVE_WALK.clear()
    bridge.LIVE_WALK.update(walk)

# 16) the live commands say plainly when macOS has not given this app Accessibility permission (CapCut then
# reads as empty, which used to come out as "can't see a draft" / "can't find the Export button"), and the export
# dialog's own ids are part of the live map
saved_trust = (bridge.AXIsProcessTrusted, bridge.capcut_process)
try:
    bridge.capcut_process = lambda: 4242
    bridge.AXIsProcessTrusted = lambda: False
    try:
        bridge.capcut_root()
        said = ""
    except SystemExit as e:
        said = str(e)
    check("Accessibility" in said and "System Settings" in said,
          f"a missing Accessibility permission is named as the cause, got {said!r}")
finally:
    bridge.AXIsProcessTrusted, bridge.capcut_process = saved_trust
check(all(k in bridge.LIVE_IDS for k in ("export_ok", "sync_toggle", "export_cancel")),
      "the export dialog's ids are in the live map")

# 17) every live wait is for a condition: it returns the moment the condition holds, stops with a plain sentence
#     when it never does, and the export presses the dialog's controls by id only (never at a guessed spot)
clock = {"t": 0.0, "slept": []}


def fake_sleep(seconds):
    clock["slept"].append(seconds)
    clock["t"] += seconds
    for hook in list(clock.get("hooks", [])):
        hook()


real_sleep, real_time = bridge.time.sleep, bridge.time.time
bridge.time.sleep, bridge.time.time = fake_sleep, (lambda: clock["t"])
try:
    answers = iter([None, 0, "", "there"])
    check(bridge.until(lambda: next(answers), 30) == "there" and clock["slept"] == [bridge.POLL_SECONDS] * 3,
          f"a wait returns on the first check its condition holds, one poll apart: {clock['slept']}")
    clock.update(t=0.0, slept=[])
    check(bridge.until(lambda: "at once", 30) == "at once" and clock["slept"] == [],
          "a condition that already holds costs no wait at all")
    clock.update(t=0.0, slept=[])
    check(bridge.until(lambda: None, 1.2) is None and abs(clock["t"] - 1.2) < 1e-9,
          f"with no sentence, a wait that never holds gives None at its limit, not past it: {clock['t']}")
    clock.update(t=0.0, slept=[])
    try:
        bridge.until(lambda: False, bridge.LIVE_LIMITS["load"], gone="CapCut's editor did not open")
        said = ""
    except SystemExit as stop:
        said = str(stop)
    check(said == "CapCut's editor did not open" and abs(clock["t"] - bridge.LIVE_LIMITS["load"]) < 1e-9,
          f"a wait that never holds stops with its plain sentence at the limit: {said!r} after {clock['t']}s")
    check(all(s <= bridge.POLL_SECONDS for s in clock["slept"]), "no single sleep is longer than one poll")

    # the export, against a dialog that shows its ids and a file that grows, then goes quiet
    class Part:
        def __init__(self, x, y):
            self.centre, self.element, self.box, self.label = (x, y), None, (x - 5, y - 5, 10, 10), "part"

    world = {"dialog": False, "ok": True, "sync": True, "pressed": [], "keys": [], "started": None}
    PLACES = {"export_button": Part(1400, 56), "export_ok": Part(1000, 800), "sync_toggle": Part(760, 750)}

    class FakeScreen:
        def __init__(self, depth=None, needs=()):
            pass

        def part(self, key):
            if key in ("export_ok", "sync_toggle"):
                return PLACES[key] if world["dialog"] and world["ok" if key == "export_ok" else "sync"] else None
            return PLACES.get(key)

    out_dir = Path(tmp, "exports")
    out_dir.mkdir()
    (out_dir / "older.mp4").write_bytes(b"an older export")
    os.utime(out_dir / "older.mp4", (1, 1))

    def fake_press(x, y, clicks=1):
        world["pressed"].append((x, y))
        if (x, y) == PLACES["export_button"].centre:
            world["dialog"] = True
        elif (x, y) == PLACES["export_ok"].centre:
            world["dialog"], world["started"] = False, clock["t"]

    def grow():                                   # CapCut writing: 1 MB a second for 4 s, then the file is closed
        if world["started"] is None:
            return
        size = min(4, int(clock["t"] - world["started"])) * 1_000_000
        target = out_dir / "Reel 1.1.mp4"
        if size and (not target.exists() or target.stat().st_size != size):
            target.write_bytes(b"\0" * size)
            os.utime(target, (clock["t"], clock["t"]))
    clock["hooks"] = [grow]

    saved_export = (bridge.Screen, bridge.press, bridge.key, bridge.ax, bridge.subprocess.run)
    bridge.Screen, bridge.press, bridge.ax = FakeScreen, fake_press, (lambda element, attribute: None)
    bridge.key = lambda combo: world["keys"].append(combo)
    bridge.subprocess.run = lambda args, *a, **k: subprocess.CompletedProcess(args, 0, "4.0\n", "")
    try:
        clock.update(t=100.0, slept=[])
        report = io.StringIO()
        with _cl.redirect_stdout(report):
            landed = bridge.run_export(str(out_dir), timeout=120)
        check(landed == out_dir / "Reel 1.1.mp4" and "4.0 s long" in report.getvalue(),
              f"export reports the new file, not the older one: {landed} {report.getvalue()!r}")
        check(world["pressed"] == [PLACES["export_button"].centre, PLACES["export_ok"].centre],
              f"export presses the Export button, then the dialog's own Export button by id, nothing else: {world['pressed']}")
        quiet_for = clock["t"] - (world["started"] + 4)
        check(bridge.EXPORT_QUIET <= quiet_for <= bridge.EXPORT_QUIET + bridge.POLL_SECONDS,
              f"the file counts as written once it has been quiet for EXPORT_QUIET, and no later: {quiet_for:.2f}s")
        check(world["keys"] == ["escape", "escape"], f"Escape before (old share screen) and after (new one): {world['keys']}")

        # a dialog that shows its controls under other names: a plain stop, no click at a guessed place
        world.update(dialog=False, ok=False, pressed=[], keys=[], started=None)
        clock.update(t=500.0, slept=[])
        try:
            bridge.run_export(str(out_dir), timeout=120)
            said = ""
        except SystemExit as stop:
            said = str(stop)
        check("ExportOkBtn" in said and "ids --map" in said and "not started" in said,
              f"no ExportOkBtn: stop and point at ids --map: {said!r}")
        check(world["pressed"] == [PLACES["export_button"].centre],
              f"no ExportOkBtn: nothing is clicked after the title bar's Export button: {world['pressed']}")
        check(abs(clock["t"] - 500.0 - bridge.LIVE_LIMITS["load"]) < 1e-6,
              f"the dialog is waited for up to the load limit: {clock['t'] - 500.0}s")

        world.update(dialog=False, ok=True, sync=False, pressed=[], keys=[], started=None)
        try:
            bridge.run_export(str(out_dir), timeout=120, toggle_sync=True)
            said = ""
        except SystemExit as stop:
            said = str(stop)
        check("automationbackupCheckBox" in said and "ids --map" in said and len(world["pressed"]) == 1,
              f"--toggle-sync with no checkbox id: stop before any dialog click: {said!r} {world['pressed']}")

        world.update(dialog=False, ok=True, sync=True, pressed=[], keys=[], started=None)
        clock.update(t=900.0, slept=[])
        with _cl.redirect_stdout(io.StringIO()):
            bridge.run_export(str(out_dir), timeout=120, toggle_sync=True)
        check(world["pressed"] == [PLACES["export_button"].centre, PLACES["sync_toggle"].centre,
                                   PLACES["export_ok"].centre], f"--toggle-sync presses the checkbox by id: {world['pressed']}")
    finally:
        bridge.Screen, bridge.press, bridge.key, bridge.ax, bridge.subprocess.run = saved_export
        clock["hooks"] = []

    # press_on: a control already expected on screen is looked for for the settle limit, then a plain sentence
    class Empty:
        def __init__(self, depth=None, needs=()):
            pass

        def first(self, needle):
            return None
    real_screen = bridge.Screen
    bridge.Screen = Empty
    clock.update(t=0.0, slept=[])
    try:
        bridge.press_on("NotAThing")
        said = ""
    except SystemExit as stop:
        said = str(stop)
    finally:
        bridge.Screen = real_screen
    check(said == "nothing on CapCut's screen is labelled NotAThing" and abs(clock["t"] - bridge.LIVE_LIMITS["settle"]) < 1e-9,
          f"press_on gives up after the settle limit with a plain sentence: {said!r} after {clock['t']}s")
finally:
    bridge.time.sleep, bridge.time.time = real_sleep, real_time

# 18) the ruler row comes from CapCut's own boxes: the band under the timeline's button row, above the first track
def editor_screen(*extra, toolbar=True, clip_tops=(668, 720)):
    board = object.__new__(bridge.Screen)
    buttons = [seen(label, (20 + 34 * k, 610, 24, 22)) for k, label in enumerate(
        ["undo", "redo", "cutoff", "cutLeft", "cutRight", "del", "mark", "quicklyAdjustZoomFit"])] if toolbar else []
    board.seen = list(extra) + buttons + [seen(f"MTLSVideoP:{n}", (180, top, 150, 40)) for n, top in enumerate(clip_tops)]
    return board


check(bridge.ruler_row(editor_screen()) == 643, f"the ruler is clicked half a button below the 22 px row: "
      f"{bridge.ruler_row(editor_screen())}")
check(bridge.ruler_row(editor_screen(clip_tops=(640, 720))) == 636,
      "a track that starts sooner narrows the band, and the click stays above it")
check(bridge.ruler_row(editor_screen(seen("ModelPanel", (0, 100, 300, 300)))) == 643,
      "a label elsewhere that shares a button's id does not move the row")
try:
    bridge.ruler_row(editor_screen(toolbar=False))
    said = ""
except SystemExit as stop:
    said = str(stop)
check("no timeline toolbar" in said, f"no toolbar: a plain stop: {said!r}")

# 19) open double-clicks only a draft tile CapCut reports; a title in no tile stops with a plain sentence
home = object.__new__(bridge.Screen)
home.seen = [seen("CapCut", (0, 38, 1512, 944)), seen("HomePageDraft", (220, 300, 1116, 42)),
             seen("HomePageDraftTitle:Reel 1.1", (282, 315, 200, 14))]
saved_open = (bridge.Screen, bridge.capcut_process, bridge.tell_capcut, bridge.press, bridge.key)
pressed = []
bridge.Screen = lambda depth=None, needs=(): home
bridge.capcut_process, bridge.tell_capcut = (lambda: 4242), (lambda verb: None)
bridge.press = lambda x, y, clicks=1: pressed.append((x, y, clicks))
bridge.key = lambda combo: pressed.append(combo)
bridge.time.sleep, bridge.time.time = fake_sleep, (lambda: clock["t"])
try:
    try:
        bridge.open_draft("Reel 1.1")
        said = ""
    except SystemExit as stop:
        said = str(stop)
    check("sits in no draft tile" in said and "ids --map" in said and pressed == [],
          f"a title in no tile: stop, nothing double-clicked: {said!r} {pressed}")
    home.seen[2].holder = home.seen[1]
    try:
        bridge.open_draft("Reel 1.1")
    except SystemExit:
        pass                                            # the editor never opens in this still picture
    check(pressed == [(778.0, 321.0, 2)], f"a title inside its row: the row's middle is double-clicked: {pressed}")
finally:
    bridge.Screen, bridge.capcut_process, bridge.tell_capcut, bridge.press, bridge.key = saved_open
    bridge.time.sleep, bridge.time.time = real_sleep, real_time

source = Path(bridge.__file__).read_text(encoding="utf-8")
check(not any(old in source for old in ("LIVE_WAITS", "LIVE_COUNTS", "_from_centre", "walk_depth",
                                        "ruler_below_toolbar", "tile_above_title")),
      "no set waits, export-dialog offsets, fixed walk depth, ruler offset or guessed tile spot are left")

if failures:
    print("✗ capcut bridge: " + "; ".join(failures))
    sys.exit(1)
print("✓ capcut bridge: --track picks by what a track holds, open matches the exact name, the canvas follows the "
      "footage, graphics at 0 s and overlapping ones are placed, --layer onto a busy track gets a new track there, "
      "Windows never kills CapCut or calls osascript, a refused edit reopens CapCut, every older command name "
      "and --track main still work, text is set in her pack, a new draft takes the installed CapCut's version, "
      "plain beats are never placed, ids --map works, a missing Accessibility "
      "permission is named as the cause, and every live wait returns once its condition holds, stops plainly when "
      "it never does, the export presses its dialog by id only, the walk reads the whole tree under its budget, the "
      "ruler row comes from the toolbar's boxes and only a reported tile is double-clicked")
