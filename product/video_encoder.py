#!/usr/bin/env python3
"""video_encoder.py — SHARED cross-platform video encoder choice for every ffmpeg render in this
engine. One correction lands everywhere, instead of four separate copies drifting apart.

Mac: Apple's videotoolbox (hardware, always available, no GPU check needed — it's the integrated
media engine on every Mac this ships to).

Windows/Linux: an NVIDIA GPU gets h264_nvenc (hardware) — checked for real, not assumed: an
NVIDIA GPU present (nvidia-smi) AND this machine's actual ffmpeg build actually has nvenc
compiled in (`ffmpeg -encoders`), because a GPU alone doesn't guarantee the ffmpeg binary a
buyer installed was built with NVENC support. No NVIDIA GPU (or the check fails for any reason)
→ libx264 software, which every ffmpeg build ships and needs no GPU — today's already-working,
never-removed floor. VENC/VBR env vars still override on any platform, same as before.

Was 4 near-identical copies (stitch-cut.sh, cut-shorts.py, build-reel-mp4.py, clean-captions/build.py)
before this module — the Mac-vs-everyone-else split existed everywhere, but Windows/Linux never
had a hardware path at all, only ever libx264. This is additive: nothing that worked before stops
working, it just now has a faster path when the hardware is actually there.
"""
import os
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import platform
import re
import subprocess

_nvenc_cache = None

# Every delivery render in this engine is SDR h264 in a .mp4. If the OUTPUT stream carries no
# color tags, a player has to guess — and the guess goes wrong on footage shot by a phone, which
# often tags itself full-range (pc). Chrome's decoder in particular then renders EVERY FRAME PURE
# BLACK while the audio plays normally: no ffmpeg error, no nonzero exit, nothing in any log. The
# file looks fine to ffprobe and plays fine in VLC, so the failure only shows up when a buyer (or
# a preview pane) opens it in a browser.
#
# Stamping the standard bt709/limited set on every render removes the guess. This is a TAG on the
# output stream, so callers whose filter chain ingests raw phone footage should also normalize the
# actual pixels to limited range before this point (stitch-cut.sh does, via its per-segment
# scale=out_range=tv + setparams) — tag and data then agree instead of merely being declared.
#
# Not Windows-specific, and not GPU-specific: it reproduces anywhere the source is full-range.
COLOR_FLAGS = ["-colorspace", "bt709", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-color_range", "tv"]


def _nvenc_available():
    """True only if an NVIDIA GPU is present, this ffmpeg build has nvenc compiled in, AND a real
    nvenc encode actually runs. Cached per-process — this gets called once per render, cheap enough
    either way, but no reason to shell out twice in a script that calls pick_encoder() more than once.

    The test encode is the part that matters. A stock OEM NVIDIA driver lagging the ffmpeg build the
    buyer installed passes the first two checks and then refuses every encode ("Driver does not
    support the required nvenc API version"). Only stitch-cut.sh had a software retry for that, so
    every other render (the well-done bake, Voiceover, Clean Captions, pull-reels, the b-roll hook,
    the composite) died on it, or left a 0-byte file where the reel should be. Asking the encoder to
    encode a tenth of a second up front sends all of them to libx264 instead."""
    global _nvenc_cache
    if _nvenc_cache is not None:
        return _nvenc_cache
    try:
        gpu = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        if gpu.returncode != 0 or not gpu.stdout.strip():
            _nvenc_cache = False
            return False
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                              capture_output=True, text=True, timeout=10)
        if "h264_nvenc" not in enc.stdout:
            _nvenc_cache = False
            return False
        # 256x256: nvenc refuses very small frames, so a tiny probe would fail on a healthy card.
        probe = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-f", "lavfi",
                                "-i", "color=c=black:s=256x256:r=30:d=0.1", "-c:v", "h264_nvenc",
                                "-pix_fmt", "yuv420p", "-f", "null", "-"],
                               capture_output=True, text=True, timeout=30)
        _nvenc_cache = probe.returncode == 0
        if not _nvenc_cache:
            sys.stderr.write("[encoder] this NVIDIA card's driver can't run the hardware encoder this ffmpeg "
                             "asks for, so renders use the software encoder (same look, slower). Updating the "
                             "NVIDIA driver brings the fast path back.\n")
    except Exception:
        _nvenc_cache = False
    return _nvenc_cache


def software_encoder(crf=17, preset="veryfast"):
    """The libx264 args pick_encoder() falls back to: the encoder every ffmpeg build ships, no GPU needed."""
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"] + COLOR_FLAGS


def is_hardware(venc):
    """True when encoder args from pick_encoder() name a hardware encoder, the kind worth a software retry."""
    return any(e in " ".join(venc) for e in ("nvenc", "videotoolbox", "qsv", "amf", "vaapi"))


def _ffmpeg_major():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return None
    m = re.match(r"ffmpeg version n?(\d+)\.", out)
    return int(m.group(1)) if m else None   # a git build ("N-12345-g...") has no number: treat it as current


def filter_complex_args(graph, path):
    """Writes a filter graph to `path` and returns the ffmpeg args that read it from there, in place of
    ["-filter_complex", graph]. Windows refuses any command line over 32,767 characters (WinError 206),
    and an inline graph grows with every kept line: a long cut passed it at about 90 segments. A graph
    in a file has no length limit. ffmpeg 7 and later spell it -/filter_complex (the old
    -filter_complex_script is deprecated and may be gone); older builds only know the old spelling."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(graph)
    major = _ffmpeg_major()
    return ["-filter_complex_script", path] if major is not None and major < 7 else ["-/filter_complex", path]


# Past this many characters a filter graph goes to ffmpeg in a file. Windows' whole command line stops at 32,767,
# and the graph shares it with every input path (a OneDrive or long-username path is ~150 characters each), so
# the graph alone is held well under it. A short graph stays inline, exactly as it always ran.
GRAPH_INLINE_MAX = 8000


def graph_args(graph, path):
    """["-filter_complex", graph] while the graph is short; once it grows past GRAPH_INLINE_MAX (one chain per
    clip, sound or layer, so a long reel gets there), filter_complex_args(graph, path): the graph written to
    `path` and read from there, as the stitch does. The caller removes `path` when it is done (remove_graph)."""
    if len(graph) <= GRAPH_INLINE_MAX:
        return ["-filter_complex", graph]
    return filter_complex_args(graph, path)


def remove_graph(path):
    """Removes a graph file graph_args may have written (nothing when it stayed inline)."""
    try:
        os.remove(path)
    except OSError:
        pass


def pick_encoder(vbr="16M", crf=17, preset="veryfast", hw_on_mac=True):
    """Returns ffmpeg -c:v ... args for the calling script's cmd list. `vbr` is the hardware-path
    bitrate target (videotoolbox/nvenc); `crf`/`preset` are the software-path (libx264) quality
    knobs — each caller passes its own already-tuned values, this only decides WHICH encoder.
    `hw_on_mac=False` keeps libx264 on a Mac for a path whose look was tuned on it (the cinematic
    Voiceover finish, the composite re-stack): NVENC still kicks in on a Windows GPU box, where the
    speed matters most, and nothing changes on the machine the look was locked on."""
    venc = os.environ.get("VENC")
    if venc:
        return ["-c:v", venc, "-b:v", os.environ.get("VBR", vbr)] + COLOR_FLAGS
    if platform.system() == "Darwin":
        if not hw_on_mac:
            return software_encoder(crf, preset)
        return ["-c:v", "h264_videotoolbox", "-b:v", os.environ.get("VBR", vbr)] + COLOR_FLAGS
    if _nvenc_available():
        return ["-c:v", "h264_nvenc", "-b:v", os.environ.get("VBR", vbr)] + COLOR_FLAGS
    return software_encoder(crf, preset)


if __name__ == "__main__":
    print("encoder:", " ".join(pick_encoder()))
    print("nvenc available:", _nvenc_available())
