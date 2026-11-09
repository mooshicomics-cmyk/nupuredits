#!/usr/bin/env python3
"""test_second_camera.py: a second camera synced by sound and laid over her cut as a picture-in-picture.

Two halves, both checked without CapCut, ffmpeg or real footage:
  1. product/sync_camera.py (needs numpy; skipped without it)
     • a clip that starts inside the second camera's recording, and one that starts before it (a negative
       offset), lock to the right offset; a clip the second camera never heard gets null, never a guess
     • a distant second mic (its copy of the room buried under its own noise) still locks chunk by chunk
     • a line where the second camera is 10 dB+ hotter than usual is carried by its mic; a line marked
       "pip_audio" in the cut list is her call and wins; --pip-mic gives a whole clip to the second mic
     • a line that changes speaker part-way is split at the word gap (contiguous, keep_edges); one loud word
       never splits a line
  2. `pip` in workflows/capcut-live.py
     • one PIP clip per footage clip from a synced file, on a new track just ABOVE her footage (graphics stay
       on top, render indexes kept in step), same moment (source + offset), same place, same length
     • built from the footage track as it stands: a file renamed inside the draft (stem-2.mp4) still matches,
       a clip past the end of the second camera's recording gets a PIP for the part it covers, a sped-up clip
       gets none, an unsynced clip gets none
     • the mic report decides the sound by source time: the PIP plays and her clip goes quiet where its mic
       carries the line; elsewhere the PIP is muted
     • placed from subject-zones (the open band below her, sized to fit), never a typed number; a second run
       refuses rather than doubling the layer
Run: python3 product/tests/test_second_camera.py   (Windows: python)
"""
import contextlib, importlib.util, json, os, sys, tempfile, types
from pathlib import Path

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ENGINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:240]})"))
    if not cond:
        fails.append(name)


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ENGINE, rel))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ════ 1. sync_camera.py ════════════════════════════════════════════════════════════════════════════════════
try:
    import numpy as np
except ImportError:
    np = None
    print("sync_camera half skipped (numpy is not installed for this Python)")

if np is not None:
    print("sync_camera.py")
    sc = load("sync_camera", "product/sync_camera.py")
    R = sc.RATE
    rng = np.random.default_rng(7)

    def talk(seconds):
        """Speech-shaped noise: bursts of a syllable or two with pauses between, never steady."""
        out, t = [], 0
        while t < seconds * R:
            on, off = int(rng.uniform(0.15, 0.6) * R), int(rng.uniform(0.05, 0.4) * R)
            out += [rng.standard_normal(on) * rng.uniform(0.05, 0.3), np.zeros(off)]
            t += on + off
        return np.concatenate(out)[:int(seconds * R)].astype(np.float32)

    room = talk(80)
    ref = sc.Reference(room)
    inside = room[int(12.345 * R):int(42.345 * R)] * 0.4 + rng.standard_normal(30 * R).astype(np.float32) * 0.003
    before = np.concatenate([talk(3), room[:int(25 * R)] * 0.4])
    stranger = talk(30)
    offset, info = sc.sync_clip(inside.astype(np.float32), ref)
    check("a clip inside the recording locks to its offset", offset is not None and abs(offset - 12.345) < 0.002,
          (offset, info))
    offset, info = sc.sync_clip(before.astype(np.float32), ref)
    check("a clip that starts before the second camera does locks to a negative offset",
          offset is not None and abs(offset + 3.0) < 0.002, (offset, info))
    offset, info = sc.sync_clip(stranger, ref)
    check("a clip the second camera never heard gets null, with the reason", offset is None and info.get("why"),
          (offset, info))
    distant = room[int(30 * R):int(70 * R)] * 0.05 + talk(40) * 1.0
    offset, info = sc.sync_clip(distant.astype(np.float32), ref)
    check("a distant second mic still locks chunk by chunk", offset is not None and abs(offset - 30.0) < 0.002,
          (offset, info))
    check("densest() finds the fullest 13 ms window, not the median's",
          sc.densest([1.000, 1.002, 1.011, 1.012, 1.013, 1.5], 0.013) == [1.000, 1.002, 1.011, 1.012, 1.013])

    # whose mic: her clip and the second camera hear the same room (offset 2.0); the second camera's own
    # speaker is 20 dB up on its copy where they talk. Most lines are hers, as in a real cut: "usual" is hers.
    base = (rng.standard_normal(20 * R) * 0.1).astype(np.float32)
    hers = base.copy()
    theirs = np.concatenate([np.zeros(2 * R, np.float32), base.copy()])
    for a, b in ((4.0, 5.5), (11.0, 12.0)):           # line 1, and the second half of line 4
        theirs[int((a + 2) * R):int((b + 2) * R)] *= 10
    cuts = [{"clip": "a.mp4", "start": 1.0, "end": 3.0, "transcript": "first"},
            {"clip": "a.mp4", "start": 4.0, "end": 5.5, "transcript": "theirs"},
            {"clip": "a.mp4", "start": 6.0, "end": 7.0, "transcript": "hers but marked", "pip_audio": True},
            {"clip": "a.mp4", "start": 7.5, "end": 9.5, "transcript": "one loud word"},
            {"clip": "a.mp4", "start": 10.0, "end": 12.0, "transcript": "mine then theirs", "_refine": {}},
            {"clip": "b.mp4", "start": 0.0, "end": 1.0, "transcript": "not covered"}]
    cuts += [{"clip": "a.mp4", "start": 13.0 + i * 1.5, "end": 14.0 + i * 1.5, "transcript": "hers"} for i in range(4)]
    words = [{"word": "mine", "start": 10.0, "end": 10.4}, {"word": "then", "start": 10.45, "end": 10.9},
             {"word": "their", "start": 11.1, "end": 11.5}, {"word": "words.", "start": 11.55, "end": 11.95},
             {"word": "one", "start": 7.5, "end": 7.9}, {"word": "loud", "start": 8.0, "end": 8.2},
             {"word": "word", "start": 8.3, "end": 9.4}]
    theirs[int((8.0 + 2) * R):int((8.2 + 2) * R)] *= 10    # one loud word inside line 3
    offsets = {"a.mp4": 2.0, "b.mp4": None}
    report = sc.mic_report(cuts, offsets, {"a.mp4": hers}, theirs, lambda clip: words if clip == "a.mp4" else [])
    lines = report["lines"]
    check("a line the second camera is far hotter on is carried by its mic", lines[1]["mic"] == "pip", lines[1])
    check("an ordinary line stays on her mic", lines[0]["mic"] == "main" and abs(lines[0]["hotter_db"]) < 1, lines[0])
    check("pip_audio in the cut list wins over the measurement",
          lines[2]["mic"] == "pip" and lines[2]["why"] == "set in the cut list", lines[2])
    check("a line the second camera does not cover stays hers", lines[5]["covered"] == "none"
          and lines[5]["mic"] == "main", lines[5])
    check("one loud word never makes a line mixed", "mixed" not in lines[3], lines[3].get("mixed"))
    mixed = lines[4].get("mixed") or {}
    check("a line that changes speaker is split at the word gap",
          mixed.get("split_at") == 11.0 and mixed.get("first") == "main" and mixed.get("second") == "pip"
          and mixed.get("second_words") == "their words.", mixed)
    whole = sc.mic_report(cuts, offsets, {"a.mp4": hers}, theirs, lambda clip: [], pip_mic_clips={"a.mp4"})
    check("--pip-mic gives every covered line of that clip to the second mic",
          [r["mic"] for r in whole["lines"]] == ["pip"] * 5 + ["main"] + ["pip"] * 4, [r["mic"] for r in whole["lines"]])
    new, split = sc.split_mixed(cuts, report)
    first, second = new[4], new[5]
    check("split_mixed writes two contiguous keep_edges lines in place of the mixed one",
          split == 1 and len(new) == len(cuts) + 1 and first["end"] == second["start"] == 11.0
          and first["start"] == 10.0 and second["end"] == 12.0 and first["keep_edges"] and second["keep_edges"]
          and first["transcript"] == "mine then" and "_refine" not in first, new[4:6])

# ════ 2. `pip` in capcut-live.py ═══════════════════════════════════════════════════════════════════════════
print("capcut-live.py pip")
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
bridge = load("capcut_live", "workflows/capcut-live.py")

tmp = Path(tempfile.mkdtemp(prefix="pip-test-"))
job = tmp / "projects" / "two-cams"
(job / "assets" / "pip").mkdir(parents=True)
(job / "assets" / "pip" / "cam2.mov").write_bytes(b"x")
(job / "assets" / "pip" / "sync.json").write_text(json.dumps(
    {"pip": "cam2.mov", "offsets": {"a.mp4": None, "b.mp4": -3.949, "c.mp4": 309.589}}), encoding="utf-8")
(job / "assets" / "pip" / "mic-report.json").write_text(json.dumps({"lines": [
    {"clip": "b.mp4", "start": 39.98, "end": 43.02, "mic": "pip"},       # frame-snapped differently: still found
    {"clip": "b.mp4", "start": 1.9, "end": 5.0, "mic": "main"},
    {"clip": "c.mp4", "start": 10.0, "end": 13.0, "mic": "main"}]}), encoding="utf-8")
zones = {"zones": {"above": {"usable": False, "center_y_norm": 0.72, "room_px": -2},
                   "below": {"usable": True, "center_y_norm": -0.2938, "room_px": 756}}}
(job / "subject-zones.json").write_text(json.dumps(zones), encoding="utf-8")

US = 1_000_000


def make_draft():
    draft = bridge.blank(bridge.DRAFT_SHAPE)
    draft["canvas_config"]["width"], draft["canvas_config"]["height"] = 1080, 1920
    pools = draft["materials"]
    for mid, path in (("ma", "/d/Resources/a.mp4"), ("mb", "/d/Resources/b.mp4"),
                      ("mc", "/d/Resources/c-2.mp4"), ("mg", "/d/Resources/hook.mov")):
        pools["videos"].append({"id": mid, "path": path, "material_name": Path(path).name})
    main = [bridge.clip_segment(pools, "ma", 1 * US, 3 * US, 0),               # unsynced clip
            bridge.clip_segment(pools, "mb", 2 * US, 3 * US, 3 * US),          # PIP starts 1.949 s in
            bridge.clip_segment(pools, "mb", 40 * US, 3 * US, 6 * US),         # his mic
            bridge.clip_segment(pools, "mc", 10 * US, 3 * US, 9 * US),         # renamed inside the draft
            bridge.clip_segment(pools, "mc", 120 * US, 3 * US, 12 * US)]       # past his recording's end
    sped = bridge.clip_segment(pools, "mc", 20 * US, 2 * US, 15 * US)
    sped["speed"] = 2.0
    main.append(sped)
    for seg in main:
        seg["render_index"], seg["track_render_index"] = 0, 0
    footage = bridge.new_track("video", 0, main)
    footage["is_default_name"] = False
    graphic = bridge.clip_segment(pools, "mg", 0, 5 * US, 0)
    graphic["render_index"], graphic["track_render_index"] = 1, 1
    draft["tracks"] = [footage, bridge.new_track("video", 2, [graphic]), bridge.new_track("text", 1, [])]
    return draft


state = {"draft": make_draft()}


@contextlib.contextmanager
def fake_building_on(name):
    yield state["draft"], tmp


real = (bridge.REPO, bridge.building_on, bridge.media_into, bridge.probe_video, bridge.source_rotation)
bridge.REPO, bridge.building_on = tmp, fake_building_on
bridge.media_into = lambda folder, source: Path("/d/Resources") / Path(source).name
bridge.probe_video = lambda path: (1920, 1080, 125 * US, True)                   # his recording: 125 s
bridge.source_rotation = lambda path: 0
try:
    said = bridge.lay_pip("Two Cams 1.1", "two-cams")
    draft = state["draft"]
    kinds = [(t["type"], t["flag"]) for t in draft["tracks"]]
    check("the PIP gets its own track just above her footage, under the graphics",
          kinds == [("video", 0), ("video", 2), ("video", 2), ("text", 1)], kinds)
    pip = draft["tracks"][1]["segments"]
    main = draft["tracks"][0]["segments"]
    graphic = draft["tracks"][2]["segments"][0]
    starts = [(p["source_timerange"]["start"], p["target_timerange"]["start"], p["target_timerange"]["duration"])
              for p in pip]
    want = [(0, 3 * US + 1_949_000, 1_051_000),                              # only the part his camera covers
            (36_051_000, 6 * US, 3 * US)]                                    # 40 s - 3.949 s
    check("one PIP clip per covered footage clip: same moment, same place, same length (none for unsynced, "
          "sped-up or uncovered clips)", starts == want, starts)
    check("a clip past the end of his recording gets no PIP", len(pip) == 2, len(pip))
    check("the PIP sits in the open band below her at 90%",
          all(p["clip"]["scale"] == {"x": 0.9, "y": 0.9} and p["clip"]["transform"]["y"] == -0.2938 for p in pip),
          [(p["clip"]["scale"], p["clip"]["transform"]["y"]) for p in pip])
    check("his mic plays on the line it carries and her clip goes quiet there",
          [p["volume"] for p in pip] == [0.0, 1.0] and main[2]["volume"] == 0.0
          and main[2]["last_nonzero_volume"] == 1.0 and main[1]["volume"] == 1.0, [p["volume"] for p in pip])
    check("render indexes stay in step: PIP above her footage, the graphic still above the PIP",
          all(p["render_index"] == 1 and p["track_render_index"] == 1 for p in pip)
          and graphic["render_index"] == 2 and graphic["track_render_index"] == 2,
          ([(p["render_index"], p["track_render_index"]) for p in pip], graphic["render_index"]))
    check("the summary says what was laid and why some clips have none",
          "2 clip(s)" in said and "carries 1" in said and "1 clip(s) reach outside" in said and "1 sped-up" in said, said)
    try:
        bridge.lay_pip("Two Cams 1.1", "two-cams")
        check("a second run refuses instead of doubling the layer", False)
    except SystemExit as stop:
        check("a second run refuses instead of doubling the layer", "already in this draft" in str(stop), stop)

    # the clip past his recording's end: extend the recording and it gets its PIP (c-2.mp4 still matches c.mp4)
    state["draft"] = make_draft()
    bridge.probe_video = lambda path: (1920, 1080, 500 * US, True)
    bridge.lay_pip("Two Cams 1.1", "two-cams")
    srcs = [p["source_timerange"]["start"] for p in state["draft"]["tracks"][1]["segments"]]
    check("a footage file renamed inside the draft (c-2.mp4) still matches its clip",
          srcs[2:] == [319_589_000, 429_589_000], srcs)

    # a phone filming upright stores 1920x1080 with a -90 rotation: it PLAYS 1080x1920, so it is sized as
    # portrait (fit to the 756 px band below her), never as the landscape clip its stored size claims
    state["draft"] = make_draft()
    bridge.source_rotation = lambda path: -90
    said = bridge.lay_pip("Two Cams 1.1", "two-cams")
    scales = {p["clip"]["scale"]["x"] for p in state["draft"]["tracks"][1]["segments"]}
    check("a rotated (upright) second camera is sized by how it plays, not by its stored size",
          scales == {0.3937} and "39% size" in said, (scales, said))
finally:
    bridge.REPO, bridge.building_on, bridge.media_into, bridge.probe_video, bridge.source_rotation = real

check("synced_clip: exact name, a media_slot rename, and an unsynced file",
      [bridge.synced_clip({"path": p}, {"b.mp4": 1.0, "my-clip.mp4": 2.0})
       for p in ("/x/b.mp4", "/x/b-3.mp4", "/x/my-clip.mp4", "/x/a.mp4")] == ["b.mp4", "b.mp4", "my-clip.mp4", None])
portrait = bridge.pip_placement(zones, (1080, 1920), (1080, 1920))
check("an upright second camera is sized to fit the band, not 90%", portrait == (0.3937, -0.2938, "below"), portrait)
check("no open band above or below her means no placement",
      bridge.pip_placement({"zones": {"below": {"usable": False}, "above": {"usable": False}}},
                           (1080, 1920), (1920, 1080)) is None)
check("pip_mic matches by source time and defaults to her mic",
      bridge.pip_mic({"lines": [{"clip": "b.mp4", "start": 1.0, "end": 2.0, "mic": "pip"}]}, "b.mp4", 1.03, 2.0)
      == "pip" and bridge.pip_mic(None, "b.mp4", 0, 1) == "main")

print(f"\n{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
