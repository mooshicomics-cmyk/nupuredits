#!/usr/bin/env python3
"""test_sfx_additive.py — sound added to a draft she already has must leave her sounds alone.

capcut_sfx.add_sfx() replaces every 'sfx_' sound an earlier pass placed. That is right inside a builder's own
one-pass build (a rebuild never doubles its cues), and it was also the only mode there was, so the sound-design
skill's "additive only" pass quietly deleted the sounds already on the draft. keep_existing=True is the
additive mode; the default must stay exactly as it was for every builder that calls it.

Works in a temp folder only. Run: python3 product/tests/test_sfx_additive.py
"""
import json, os, shutil, sys, tempfile

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capcut_sfx

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


pal = capcut_sfx.selectable()
if len(pal) < 2 or not shutil.which("ffprobe"):
    print("· sfx additive: skipped (needs two bundled sounds and ffprobe on this machine)")
    sys.exit(0)
a, b = sorted(pal)[:2]


def fresh():
    tmp = tempfile.mkdtemp(prefix="sfx-additive-")
    d = {"materials": {"audios": [], "videos": []},
         "tracks": [{"type": "video", "flag": 0, "id": "MAIN", "segments": []}]}
    return tmp, d


def sfx_segments(d):
    return [s for t in d["tracks"] if t["type"] == "audio" for s in t["segments"]]


import io, contextlib
quiet = contextlib.redirect_stdout(io.StringIO())

# 1) default: a second pass REPLACES the first pass's cues (unchanged behaviour every builder relies on)
tmp, d = fresh()
with quiet:
    capcut_sfx.add_sfx(d, tmp, [(a, 1.0, 0.3, 0.8)])
    capcut_sfx.add_sfx(d, tmp, [(b, 2.0, 0.3, 0.8)])
names = [m["name"] for m in d["materials"]["audios"]]
check(len(sfx_segments(d)) == 1, f"default mode should leave only the latest pass's cue, got {len(sfx_segments(d))}")
check(names == [f"sfx_{b}{os.path.splitext(pal[b])[1].lower() or '.mp3'}"], f"default mode materials: {names}")
shutil.rmtree(tmp, ignore_errors=True)

# 2) keep_existing=True: the first pass's cue and track stay exactly as they were; the new cues get one new track
tmp, d = fresh()
with quiet:
    capcut_sfx.add_sfx(d, tmp, [(a, 1.0, 0.3, 0.8)])
first_track = json.dumps([t for t in d["tracks"] if t["type"] == "audio"], sort_keys=True)
first_mats = json.dumps(d["materials"]["audios"], sort_keys=True)
with quiet:
    placed = capcut_sfx.add_sfx(d, tmp, [(b, 2.0, 0.3, 0.8), (a, 3.0, 0.3, 0.8)], keep_existing=True)
audio_tracks = [t for t in d["tracks"] if t["type"] == "audio"]
check(placed == 2, f"additive pass should place 2 cues, placed {placed}")
check(len(audio_tracks) == 2, f"additive pass should add ONE new track next to the old one, got {len(audio_tracks)}")
check(json.dumps(audio_tracks[:1], sort_keys=True) == first_track, "additive pass changed the earlier sound's track")
check(json.dumps(d["materials"]["audios"][:1], sort_keys=True) == first_mats, "additive pass changed an earlier sound")
check(len(sfx_segments(d)) == 3, f"all three cues should be on the draft, got {len(sfx_segments(d))}")
shutil.rmtree(tmp, ignore_errors=True)

# 3) keep_existing=True never overwrites a DIFFERENT file that already has the name it would take
tmp, d = fresh()
ext = os.path.splitext(pal[a])[1].lower() or ".mp3"
aud = os.path.join(tmp, "assets", "audio")
os.makedirs(aud)
taken = os.path.join(aud, f"sfx_{a}{ext}")
shutil.copyfile(pal[b], taken)                # her earlier sound sits under the name cue `a` would use
before = open(taken, "rb").read()
with quiet:
    capcut_sfx.add_sfx(d, tmp, [(a, 1.0, 0.3, 0.8)], keep_existing=True)
check(open(taken, "rb").read() == before, "additive pass overwrote a different sound that already had that name")
m = d["materials"]["audios"][-1]
check(m["name"] == f"sfx_{a}_2{ext}" and os.path.exists(os.path.join(aud, m["name"])),
      f"the new cue should get its own file name, got {m['name']!r}")
# ...and the same file again is simply reused, not copied a second time under a new name
with quiet:
    capcut_sfx.add_sfx(d, tmp, [(a, 5.0, 0.3, 0.8)], keep_existing=True)
check(d["materials"]["audios"][-1]["name"] == f"sfx_{a}_2{ext}", "an identical file was copied again under a new name")
shutil.rmtree(tmp, ignore_errors=True)

if failures:
    print("✗ sfx additive: " + "; ".join(failures))
    sys.exit(1)
print("✓ sfx additive: the default still replaces an earlier pass's cues, keep_existing=True leaves every sound "
      "already on the draft alone on its own track, and never overwrites a different file of the same name")
