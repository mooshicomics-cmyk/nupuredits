#!/usr/bin/env python3
"""test_no_audio_clip.py — a clip whose sound cannot be read is the clip's problem, never the computer's.

word-timings.sh used to read ANY WhisperX exit 1 as "WhisperX cannot run on this computer": it wrote the
.whisperx-crashed mark beside the venv, and every later reel on that machine skipped WhisperX for good. On a real
iPhone clip that fired because of the MEDIA (a spatial-audio stream ffmpeg cannot decode; fixed by the first-stream
map, test_spatial_audio_stream.py). A clip with no audio stream at all still made the listener's loader raise, exit
1, and mark the machine; faster-whisper's own decoder then raised on it too, so the reel failed anyway.

Checked here, on made-up clips (video only, video + a tone, a file that is not a video), no footage of hers needed:
  - the WhisperX listener's own reader (pulled out of word-timings.sh and run): a clip with no audio stream reads
    as None (no talking) with its real length, a clip with sound reads its samples, and a file whose sound cannot
    be read stops with CLIP_UNREADABLE (3), never 1
  - the listener's loop writes a no-sound clip as a clip with no words and moves on
  - listen() in word-timings.sh (pulled out and run with stand-ins): exit 3 hears that reel with faster-whisper and
    writes NO mark; exit 1 still marks the machine, as before
  - the faster-whisper listener (scripts/transcribe-nofw.py): a no-audio clip comes back with no words and its
    length instead of raising; a clip that HAS sound and fails is not swallowed
  - product/quiet_clips.py marks that entry silent, so the cut keeps the clip whole

Run:  python3 product/tests/test_no_audio_clip.py
"""
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRODUCT = os.path.join(ROOT, "product")
SCRIPTS = os.path.join(ROOT, "scripts")
WORD_TIMINGS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
sys.path.insert(0, PRODUCT)
sys.path.insert(0, SCRIPTS)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def ff(*args):
    return subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], capture_output=True)


def make(path, *args):
    r = ff(*args, path)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace"))


def listener_source():
    """The WhisperX listener: the Python heredoc inside listen_whisperx()."""
    sh = open(WORD_TIMINGS, encoding="utf-8").read()
    body = sh.split("\nlisten_whisperx() {", 1)[1].split("<<'PY'", 1)[1].split("\n", 1)[1].split("\nPY\n", 1)[0]
    return sh, body


def listener_reader(body):
    """The listener's clip reader and what it needs, run on their own (the rest of the listener imports whisperx)."""
    tree = ast.parse(body)
    keep = {"load_audio", "audio_stream_count", "clip_seconds", "read_clip"}
    nodes = [n for n in tree.body
             if (isinstance(n, ast.FunctionDef) and n.name in keep)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "CLIP_UNREADABLE" for t in n.targets))]
    ns = {"os": os, "sys": sys, "say": lambda line: None}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "word-timings.sh:listener", "exec"), ns)
    return ns


LISTEN_HARNESS = r'''
set -euo pipefail
VENV="$1"; LOG="$2"; WX_RC="$3"; FW_ONLY_MARK=".whisperx-crashed"; NOFW=0
listen_whisperx() { return "$WX_RC"; }
retry_on_measured_set() { return 1; }
note_newer_set_heard() { :; }
can_hear_without_whisperx() { return 0; }
note_fallback() { echo "fallback: $1" >> "$LOG"; }
listen_faster_whisper() { echo "faster-whisper (${REELS_ENGINE_NOFW_REASON:-})" >> "$LOG"; }
pivot_to_faster_whisper() { echo "pivot" >> "$LOG"; return 0; }
eval "$4"
listen
'''


def run_listen(listen_fn, work, rc):
    venv = os.path.join(work, f"venv-{rc}")
    os.makedirs(venv, exist_ok=True)
    log = os.path.join(work, f"listen-{rc}.log")
    open(log, "w", encoding="utf-8").close()
    r = subprocess.run(["bash", "-c", LISTEN_HARNESS, "harness", venv, log, str(rc), listen_fn],
                       capture_output=True, text=True)
    return r, os.path.exists(os.path.join(venv, ".whisperx-crashed")), open(log, encoding="utf-8").read()


if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    print("test_no_audio_clip: ffmpeg is not on this computer, nothing to check")
    sys.exit(0)

work = tempfile.mkdtemp(prefix="no-audio-clip-")
try:
    mute = os.path.join(work, "IMG_0001.mov")
    voiced = os.path.join(work, "IMG_0002.mov")
    broken = os.path.join(work, "IMG_0003.mov")
    make(mute, "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30:d=2", "-c:v", "libx264")
    make(voiced, "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30:d=1", "-f", "lavfi", "-i",
         "sine=f=440:r=48000:d=1", "-c:v", "libx264", "-c:a", "aac", "-shortest")
    with open(broken, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypqt  not a real movie" + os.urandom(2048))

    # ── the fixture really is what tripped the listener ────────────────────────────────────────────────
    plain = ff("-i", mute, "-map", "0:a:0?", "-f", "s16le", "-ac", "1", "-ar", "16000", "-")
    check("fixture: a first-stream read of a video-only clip fails (what the listener raised on)",
          plain.returncode != 0, plain.returncode)

    # ── the WhisperX listener's reader ───────────────────────────────────────────────────────────────────
    sh, body = listener_source()
    ns = listener_reader(body)
    missing = sorted({"load_audio", "audio_stream_count", "clip_seconds", "read_clip"} - set(ns))
    check("listener: has its clip reader (read_clip, audio_stream_count, clip_seconds)", not missing, missing)
    for name in missing:   # stand-ins that fail every check below instead of stopping the test
        ns[name] = lambda *a, _n=name: (_ for _ in ()).throw(RuntimeError(f"{_n} is missing"))
    check("listener: CLIP_UNREADABLE is 3, not WhisperX's own exit 1", ns.get("CLIP_UNREADABLE") == 3,
          ns.get("CLIP_UNREADABLE"))
    if not missing:
        check("listener: a clip with no audio stream counts 0 streams", ns["audio_stream_count"](mute) == 0)
        check("listener: a clip with sound counts its stream", ns["audio_stream_count"](voiced) == 1)
        check("listener: a no-audio clip keeps its real length", abs(ns["clip_seconds"](mute) - 2.0) < 0.2,
              ns["clip_seconds"](mute))
    try:
        got = ns["read_clip"](mute)
        check("listener: a clip with no audio stream reads as no talking (None)", got is None, type(got))
    except BaseException as e:
        check("listener: a clip with no audio stream reads as no talking (None)", False, repr(e))
    try:
        import numpy  # noqa: F401
        pcm = ns["read_clip"](voiced)
        check("listener: a clip with sound reads its samples", pcm is not None and abs(len(pcm) - 16000) < 1600,
              None if pcm is None else len(pcm))
    except ImportError:
        print("  note: numpy is not in this python, the read of a clip with sound is not run here")
    except BaseException as e:
        check("listener: a clip with sound reads its samples", False, repr(e))
    try:
        ns["read_clip"](broken)
        check("listener: a file whose sound cannot be read stops with code 3", False, "it read")
    except SystemExit as e:
        check("listener: a file whose sound cannot be read stops with code 3", e.code == 3, e.code)
    except BaseException as e:
        check("listener: a file whose sound cannot be read stops with code 3", False, repr(e))

    loop = body.split("for clip_path in clip_paths:", 1)[-1].split("\nresult = ", 1)[0]
    check("listener: the loop reads through read_clip, not load_audio",
          "read_clip(clip_path)" in loop and "load_audio(" not in loop)
    check("listener: a no-sound clip is written with no words and the loop moves on",
          "if pcm is None:" in loop and '"words": []' in loop and "continue" in loop)

    # ── listen(): 3 is this reel only, 1 is still this computer ────────────────────────────────────────
    listen_fn = sh.split("\nlisten() {", 1)[1]
    listen_fn = "listen() {" + listen_fn.split("\n}\n", 1)[0] + "\n}\n"
    here_fn = sh.split("\nlisten_faster_whisper_here() {", 1)[1]   # listen() hands faster-whisper runs to it
    listen_fn = "listen_faster_whisper_here() {" + here_fn.split("\n}\n", 1)[0] + "\n}\n" + listen_fn
    r, marked, log = run_listen(listen_fn, work, 3)
    check("listen: exit 3 finishes the reel", r.returncode == 0, r.stderr[-300:])
    check("listen: exit 3 writes NO .whisperx-crashed mark", not marked)
    check("listen: exit 3 hears the reel with faster-whisper once", sum(ln.startswith("faster-whisper (") for ln in log.splitlines()) == 1, log)
    check("listen: exit 3 never pivots the computer", "pivot" not in log, log)
    r, marked, log = run_listen(listen_fn, work, 1)
    check("listen: exit 1 (WhisperX itself) still marks the computer", r.returncode == 0 and marked,
          (r.returncode, r.stderr[-300:]))

    # ── the faster-whisper listener ────────────────────────────────────────────────────────────────────
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = object
    real = sys.modules.get("faster_whisper")
    sys.modules["faster_whisper"] = fake
    try:
        spec = importlib.util.spec_from_file_location("transcribe_nofw", os.path.join(SCRIPTS, "transcribe-nofw.py"))
        nofw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nofw)
    finally:
        if real is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = real

    class DecoderRaises:
        """What faster-whisper does on a clip with no audio stream: PyAV's decode(audio=0) has nothing to pick."""
        def transcribe(self, path, **kw):
            raise IndexError("tuple index out of range")

    try:
        entry, seconds = nofw.hear(DecoderRaises(), mute)
        check("faster-whisper: a no-audio clip comes back with no words", entry.get("words") == [], entry)
        check("faster-whisper: a no-audio clip keeps its real length", abs(seconds - 2.0) < 0.2, seconds)
        check("faster-whisper: same keys as a heard clip",
              set(entry) == {"clip", "path", "duration", "languages", "words", "restamped"}, sorted(entry))
    except BaseException as e:
        check("faster-whisper: a no-audio clip comes back with no words", False, repr(e))
        entry = None
    try:
        nofw.hear(DecoderRaises(), voiced)
        check("faster-whisper: a clip WITH sound that fails is not swallowed", False, "it returned")
    except IndexError:
        check("faster-whisper: a clip WITH sound that fails is not swallowed", True)

    # ── quiet_clips: the no-sound clip is a clip with no talking ────────────────────────────────────────
    if entry is not None:
        import quiet_clips
        wpath = os.path.join(work, "words.json")
        with open(wpath, "w", encoding="utf-8") as f:
            json.dump({"clips": [entry]}, f)
        check("quiet_clips: the no-sound clip is marked silent", quiet_clips.mark(wpath) == [entry["clip"]])
        saved = json.load(open(wpath, encoding="utf-8"))["clips"][0]
        check("quiet_clips: saved silent with its length, for the editor's beats",
              saved.get("silent") is True and len(quiet_clips.quiet_beats(saved, 0)) == 2, saved)
finally:
    shutil.rmtree(work, ignore_errors=True)

if fails:
    print(f"test_no_audio_clip: {len(fails)} of {total} FAILED")
    for f in fails:
        print(f"  FAIL {f}")
    sys.exit(1)
print(f"test_no_audio_clip: ✓ {total} checks — a clip with no readable sound never marks the computer")
