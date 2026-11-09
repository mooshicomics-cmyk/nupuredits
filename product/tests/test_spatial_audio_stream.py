#!/usr/bin/env python3
"""test_spatial_audio_stream.py — an iPhone clip with spatial audio is heard from its first audio stream.

A newer iPhone records two audio streams: stereo AAC first, then a 4-channel spatial one (codec "apac") that is
flagged as the DEFAULT and that ffmpeg has no decoder for. An ffmpeg read with no stream map takes the default,
stops ("no decoder found"), and exits 234. On a real clip that cost three things in one rough cut: WhisperX
stopped with an error and the machine was marked as one WhisperX cannot run on (every later reel went to
faster-whisper), restamp_words.py printed a traceback, and snap-to-sound.py read no sound at all, so it snapped
nothing without saying so. Every engine read of her audio now asks for the first audio stream ("-map 0:a:0?").

Checked here, on a made-up clip with that exact stream layout (video, stereo AAC not default, 4-channel "apac"
default), so no footage of hers is needed:
  - the fixture really trips a plain ffmpeg read (said, not failed, if a future ffmpeg stops tripping on it)
  - restamp_words.decode, snap-to-sound's level reader, sync_camera.decode, the loudness readers in
    audio_levels / voice_level / capcut_tail all read the AAC stream
  - the WhisperX listener in word-timings.sh uses its own first-stream loader, never whisperx.load_audio
  - a clip with no audio at all: the loudness readers say "nothing measured" (None) instead of raising, and
    restamp_words strays skips a wordless clip without reading it
  - every other engine audio read fixed alongside still carries its stream map

Run:  python3 product/tests/test_spatial_audio_stream.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRODUCT = os.path.join(ROOT, "product")
SCRIPTS = os.path.join(ROOT, "scripts")
ROUGH = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
sys.path.insert(0, PRODUCT)
sys.path.insert(0, SCRIPTS)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ff(*args):
    return subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], capture_output=True)


def spatial_clip(path):
    """1 s: gray video, a 440 Hz stereo AAC stream (not default), then a 4-channel stream (default) re-tagged
    "apac" with its decoder config renamed away, the layout an iPhone spatial-audio clip shows ffprobe."""
    tmp = path + ".src.mov"
    r = ff("-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30:d=1", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=1",
           "-f", "lavfi", "-i", "anoisesrc=r=48000:d=1:a=0.1", "-filter_complex",
           "[1:a]aformat=channel_layouts=stereo[s];[2:a]aformat=channel_layouts=quad[q]",
           "-map", "0:v", "-map", "[s]", "-map", "[q]", "-c:v", "libx264", "-c:a", "aac",
           "-disposition:a:0", "0", "-disposition:a:1", "default", "-shortest", tmp)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace"))
    b = bytearray(open(tmp, "rb").read())
    stsd, i = [], -1
    while (i := b.find(b"stsd", i + 1)) != -1:
        stsd.append(i)
    p = stsd[2]                                       # video, stereo, then the 4-channel track
    end = p - 4 + int.from_bytes(b[p - 4:p], "big")
    assert b[p + 16:p + 20] == b"mp4a", b[p + 16:p + 20]
    b[p + 16:p + 20] = b"apac"                        # the sample entry: what ffprobe reports as the tag
    e = b.find(b"esds", p, end)
    b[e:e + 4] = b"dapa"                              # no decoder config left, so no decoder: codec "unknown"
    with open(path, "wb") as f:
        f.write(b)
    os.remove(tmp)


def silent_clip(path):
    r = ff("-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30:d=1", "-c:v", "libx264", path)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace"))


if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    print("test_spatial_audio_stream: ffmpeg is not on this computer, nothing to check")
    sys.exit(0)

work = tempfile.mkdtemp(prefix="spatial-audio-")
try:
    clip = os.path.join(work, "IMG_0001.mov")
    mute = os.path.join(work, "IMG_0002.mov")
    spatial_clip(clip)
    silent_clip(mute)

    # ── the fixture is the real layout ──────────────────────────────────────────────────────────────────
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                            "stream=codec_name,codec_tag_string,channels:stream_disposition=default",
                            "-of", "json", clip], capture_output=True, text=True)
    streams = json.loads(probe.stdout or "{}").get("streams", [])
    check("fixture: two audio streams", len(streams) == 2, streams)
    if len(streams) == 2:
        check("fixture: first is stereo AAC, not default",
              streams[0]["codec_name"] == "aac" and streams[0]["channels"] == 2
              and streams[0]["disposition"]["default"] == 0, streams[0])
        check("fixture: second is 4-channel apac, default, no decoder",
              streams[1]["codec_tag_string"] == "apac" and streams[1]["channels"] == 4
              and streams[1].get("codec_name", "unknown") in ("unknown", "none") and streams[1]["disposition"]["default"] == 1,
              streams[1])
    plain = ff("-i", clip, "-vn", "-af", "pan=mono|c0=c0", "-ar", "16000", "-f", "f32le", "-")
    if plain.returncode == 0:
        print("  note: this ffmpeg no longer trips on the spatial stream by itself; the checks below still hold")

    # ── restamp_words (the reported traceback) ──────────────────────────────────────────────────────────
    import restamp_words as rw
    try:
        samples = rw.decode(clip)
        check("restamp_words.decode reads the AAC stream", abs(len(samples) - rw.RATE) < rw.RATE * 0.1, len(samples))
        check("restamp_words.decode hears the tone", max(rw.envelope(samples) or [-200]) > -30)
    except subprocess.CalledProcessError as e:
        check("restamp_words.decode reads the AAC stream", False, e.stderr)

    words = {"clips": [{"clip": os.path.basename(mute), "path": mute, "words": [], "silent": True}]}
    wpath, opath = os.path.join(work, "words.json"), os.path.join(work, "words.out.json")
    with open(wpath, "w", encoding="utf-8") as f:
        json.dump(words, f)
    try:
        rc = rw.place_strays(wpath, work, opath)
        check("strays: a wordless clip with no audio is skipped (nothing to do)", rc == 3, rc)
    except Exception as e:
        check("strays: a wordless clip with no audio is skipped (nothing to do)", False, repr(e))

    # ── snap-to-sound: it read no sound and snapped nothing, silently ───────────────────────────────────
    snap = load(os.path.join(ROUGH, "snap-to-sound.py"), "snap_to_sound")
    t0, readings = snap._levels(clip, 0.0, 1.0)
    check("snap-to-sound reads the AAC stream", len(readings) > 0.8 / snap.FRAME, len(readings))
    check("snap-to-sound hears the tone", readings and max(readings) > -30, readings[:5])

    # ── the WhisperX listener ────────────────────────────────────────────────────────────────────────────
    wt = open(os.path.join(ROUGH, "word-timings.sh"), encoding="utf-8").read()
    check("word-timings: the listener never calls whisperx.load_audio", "whisperx.load_audio(" not in wt)
    check("word-timings: its own loader asks for the first audio stream",
          "def load_audio(" in wt and '"-map", "0:a:0?"' in wt.split("def load_audio(", 1)[-1].split("\ndef ", 1)[0])

    # ── second camera, loudness readers ──────────────────────────────────────────────────────────────────
    try:
        import numpy  # noqa: F401
        import sync_camera
        pcm = sync_camera.decode(clip)
        check("sync_camera.decode reads the AAC stream", abs(len(pcm) - sync_camera.RATE) < sync_camera.RATE * 0.1,
              len(pcm))
    except ImportError:
        print("  note: numpy is not in this python, the second-camera reader is checked by source only")
    except subprocess.CalledProcessError as e:
        check("sync_camera.decode reads the AAC stream", False, e.stderr)

    import audio_levels
    import voice_level
    capcut_tail = load(os.path.join(PRODUCT, "capcut_tail.py"), "capcut_tail")
    check("audio_levels.mean_dbfs reads the AAC stream", audio_levels.mean_dbfs(clip) is not None)
    check("audio_levels.loudness_lufs reads the AAC stream", audio_levels.loudness_lufs(clip) is not None)
    check("audio_levels.momentary_max_lufs reads the AAC stream", audio_levels.momentary_max_lufs(clip) is not None)
    check("voice_level.measure reads the AAC stream", voice_level.measure(clip)[0] is not None)
    check("capcut_tail reads the AAC stream", capcut_tail._rms_db(clip) is not None)
    check("no audio at all: mean_dbfs says nothing measured", audio_levels.mean_dbfs(mute) is None)
    check("no audio at all: loudness_lufs says nothing measured", audio_levels.loudness_lufs(mute) is None)
    check("no audio at all: voice_level says nothing measured", voice_level.measure(mute) == (None, None))

    # ── the reads fixed alongside, which need a whole job or heavy tools to run ─────────────────────────
    for rel, needed in [
        (".claude/skills/rough-cut/scripts/trim-restarts.py", 1),
        (".claude/skills/rough-cut/scripts/check-pauses.py", 1),
        (".claude/skills/rough-cut/scripts/sound-check.py", 1),
        (".claude/skills/rough-cut/scripts/verify-cut.py", 1),
        ("product/sound_plan.py", 2),
        ("product/capcut_handoff.py", 1),
        ("product/build-music.py", 1),
        ("product/reel-fingerprint.py", 1),
        ("product/vo-ambience.py", 2),
        ("product/vo-cutgrid.py", 1),
        ("product/vo-splice.py", 3),
        ("product/vo-listen.py", 1),
        ("product/visual_editor.py", 1),
    ]:
        if not os.path.isfile(os.path.join(ROOT, rel)):      # a seller-only tool make-ship leaves out (check-pauses.py)
            continue                                         # is not in the buyer's package this guard runs in
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        got = src.count('"0:a:0?"') + src.count('"1:a:0?"')
        check(f"{rel}: its audio reads keep the first-stream map", got >= needed, f"{got} of {needed}")
finally:
    shutil.rmtree(work, ignore_errors=True)

if fails:
    print(f"test_spatial_audio_stream: {len(fails)} of {total} FAILED")
    for f in fails:
        print(f"  FAIL {f}")
    sys.exit(1)
print(f"test_spatial_audio_stream: ✓ {total} checks — a spatial-audio iPhone clip is heard from its first stream")
