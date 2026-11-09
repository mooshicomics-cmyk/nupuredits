#!/usr/bin/env python3
"""capcut_alpha.py — every transparent overlay reaches CapCut as STRAIGHT-alpha ProRes 4444, edges cleaned.

WHAT CAPCUT DOES. CapCut composites the alpha in a ProRes 4444 clip as STRAIGHT, exactly how HyperFrames renders
(out = colour x a + under x (1 - a)). Measured twice, side by side in real drafts on her own CapCut: 2026-10-02
(white at 35%: straight a faint haze, premultiplied a dark grey disc) and 2026-10-28 on CapCut 9.5.0, Apple chip
(a 60% beige veil, a 35% white patch, a pink glow and a card shadow over warm and cool footage: the straight
copy matched the reference picture exactly; the premultiplied copy came out grey and muddy, with a dark ring round
the patch). A premultiplied default (v2.3.16 pre-release, from buyer screenshots of a veil drawn white, never an
A/B) darkened every soft edge, so it was taken back before it shipped. A white veil seen in a buyer's draft has
another cause: look at the clip's own pixels before touching this default.
CAPCUT_ALPHA_PREMULT=1 premultiplies everything instead, for a computer whose CapCut is SHOWN, side by side, to
read premultiplied.

A WebM with transparency (VP9/VP8 alpha, which is what HyperFrames' remove-background writes) is worse: CapCut
drops its alpha entirely, so everything clear turns solid black. So a transparent clip in any other container is
converted to ProRes 4444 on its way in, the format CapCut keeps the transparency of.

  for_capcut(path)        -> a path that shows correctly in CapCut (the file itself, or a cached copy)
  fix_in_place(path)      -> put the CapCut-ready pixels into a file already inside a FRESH draft
  install(src, dst)       -> put a prepared copy in place of a draft asset, atomically
  straight_evidence(path) -> True straight / False colour never exceeds alpha / None (nothing to judge by)
  looped_clip(path, secs) -> a moving GIF / WebP as a looping straight ProRes 4444 .mov CapCut plays (cached)

WHAT IT CHANGES, AND WHAT IT NEVER DOES.
  * Every render (straight ProRes/QuickTime) goes in as a straight copy with its faint edges' hue noise greyed
    (the rainbow ring rule); hard edges and every other colour are kept as rendered.
  * A copy tagged premultiplied (made by the opt-in route, or the v2.3.16 pre-release) is turned back to straight.
  * A copy already tagged straight is left as it is.
  * A transparent WebM/MKV/etc. is converted to straight ProRes 4444.
  * Stills (PNG stickers) and opaque clips are left exactly as they are. A GIF that moves is not a still: it goes
    in as a looping ProRes 4444 clip (looped_clip, called from capcut_media.ensure_shippable).
  * The render itself is never modified: changes are written to a cached COPY with the SAME file name (and
    extension: VectCut copies an overlay in as video_<id>.mp4, QuickTime inside, and that stays its name).
  Decided by probing the stream, never by the file name. A copy is keyed by the source's CONTENT, so an unchanged
  layer is prepared once however many drafts it goes into; entries unused for CACHE_DAYS are pruned.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, time

RECIPE = "v10-grey-only"                   # bump when the ffmpeg recipe changes: invalidates the cache
TAG = "capcut-alpha:premultiplied"              # a premultiplied copy (the CAPCUT_ALPHA_PREMULT=1 route)
STRAIGHT_TAG = "capcut-alpha:straight"          # a straight copy (what this module writes by default)
# ffmpeg 8 tracks whether a frame is premultiplied and its unpremultiply filter does NOTHING to a frame not marked
# so, which a ProRes file never is: mark it first. ffmpeg before 8 has no such option (and no such check), so the
# plain chain is the fallback there. Both are tried in order; the first that runs is used.
UNPREMULT_VFS = ("setparams=alpha_mode=premultiplied,format=gbrap16le,unpremultiply=inplace=1,format=yuva444p12le",
                 "format=gbrap16le,unpremultiply=inplace=1,format=yuva444p12le")
# The numpy-free premultiply: a WebM cutout's conversion, and the fallback when the edge clean can't run here (so a
# layer never goes into CapCut straight, which is the white veil). Same filter source as unpremultiply in every build.
PREMULT_VFS = ("setparams=alpha_mode=straight,format=gbrap16le,premultiply=inplace=1,format=yuva444p12le",
               "format=gbrap16le,premultiply=inplace=1,format=yuva444p12le")
CONVERT_VF = "format=yuva444p12le"
# A browser render keeps colour premultiplied in 8 bits, so a pixel only a few percent opaque (the far edge of a soft
# shadow or glow) comes back with a random hue once un-premultiplied: (36,0,0) red and (20,21,0) yellow inside one
# dark-brown shadow. CapCut draws those as a rainbow ring around every card (2026-10-18, three looks). So below
# EDGE_A the colour fades to its own grey (the hue is noise there), back to full colour by EDGE_FULL. Measured on her
# renders: hue noise at alpha <= 16/255, true colour from ~40/255.
EDGE_A, EDGE_FULL = 24, 48
# That greying is the only colour this route changes. Rules that also scaled dark and faint pixels by their alpha
# (2026-10-18 and 10-21, for white rings and halos seen in drafts) are gone: they darkened the outline of every letter
# ((0,97,204) to (0,39,82) on a blue bubble, choppy edges in CapCut) and put a dark halo round soft looks. Measured in
# her real CapCut 2K exports (2026-11-01, drafts "Edge test old then new" and "Edge test dark shadows"): without
# them a plum shadow, a pink glow and a 35% white patch match the same look painted on the footage, on light and on
# dark, with no ring.
# The greying is about SOFT pixels (a shadow's or a glow's slow fade). The smoothing pixels on the edge of type and
# shapes are see-through for a different reason and keep their real colour. The two are told apart by slope: a hard
# edge's alpha jumps between neighbouring pixels, a soft fade's barely moves. So a pixel with a jump of HARD_STEP/255
# beside it keeps its colour, down to KEEP_A/255, under which the hue noise is back and it is too faint to shape the
# edge anyway.
HARD_STEP = 40
KEEP_A = 16
CACHE_DAYS = 14
_TOL = 3                                        # 8-bit rounding through yuva 4:4:4 can put colour 1-2 over alpha


def cache_root():
    return os.environ.get("REEL_CAPCUT_ALPHA_CACHE") or os.path.expanduser(
        "~/.cache/reels-editing-engine/capcut-alpha")


def has_alpha(pix_fmt):
    p = (pix_fmt or "").lower()
    return p.startswith("yuva") or p.startswith("ya") or "rgba" in p or "argb" in p or "bgra" in p or "abgr" in p


def _probe(path):
    """-> dict(pix, dur, w, h, comment, fmt, codec, vpx_alpha). vpx_alpha: a VP8/VP9 stream whose alpha rides
    in a side channel (ffprobe reports yuv420p plus an ALPHA_MODE=1 tag, so pix_fmt alone never shows it)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=pix_fmt,width,height,codec_name,r_frame_rate:stream_tags:format=duration,format_name"
                              ":format_tags=comment", "-of", "json", path], capture_output=True, text=True).stdout
        o = json.loads(out or "{}")
        st = (o.get("streams") or [{}])[0]
        fmt = o.get("format") or {}
        stags = {k.lower(): v for k, v in (st.get("tags") or {}).items()}
        codec = st.get("codec_name") or ""
        return dict(pix=st.get("pix_fmt") or "", dur=float(fmt.get("duration") or 0),
                    w=int(st.get("width") or 0), h=int(st.get("height") or 0),
                    comment=(fmt.get("tags") or {}).get("comment", ""), fmt=fmt.get("format_name") or "",
                    codec=codec, fps=st.get("r_frame_rate") or "30", vpx_alpha=codec in ("vp8", "vp9") and str(stags.get("alpha_mode", "")) == "1")
    except Exception:
        return dict(pix="", dur=0.0, w=0, h=0, comment="", fmt="", codec="", fps="30", vpx_alpha=False)


def _is_movie(format_name):
    """A QuickTime-family container (.mov, or the same thing named .mp4/.m4v). Stills (png_pipe, image2, gif,
    webp_pipe) are not, and neither is WebM/Matroska."""
    return "mov" in (format_name or "").split(",")


def _is_still(format_name):
    f = (format_name or "").lower()
    return any(k in f for k in ("png", "image2", "gif", "webp", "jpeg", "bmp", "tiff"))


def _plan(path):
    """What this file needs before CapCut sees it: None, "unpremultiply" or "convert"."""
    p = _probe(path)
    if _is_still(p["fmt"]):
        return None
    if p["vpx_alpha"]:
        return "convert"                        # CapCut drops VP8/VP9 alpha: it would show black
    if not has_alpha(p["pix"]):
        return None                             # opaque
    if _is_movie(p["fmt"]):
        if premult_all():
            return None if p["comment"] == TAG else "clean"    # a render, or an old straight copy: premultiply it
        if p["comment"] == TAG:
            return "unpremultiply"
        return "clean" if p["comment"] != STRAIGHT_TAG else None   # every render: its faint edges' hue noise cleaned
    return "convert"                            # a transparent clip in a container CapCut is not given overlays in


def needs_preparing(path):
    return bool(path and os.path.isfile(path) and _plan(path))


def is_tagged(path):
    """True when the file carries the premultiplied tag."""
    return _probe(path)["comment"] == TAG


def straight_evidence(path, samples=8):
    """Sample frames across the clip. True as soon as any pixel's colour exceeds its alpha (straight alpha, the
    correct form for CapCut); False when semi-transparent pixels were seen and every one is <= alpha (consistent
    with premultiplied); None when the samples held no semi-transparent pixel at all (nothing to judge by)."""
    p = _probe(path)
    w, h, dur = p["w"], p["h"], p["dur"]
    if not w or not h:
        return None
    dec = _decoder(p)
    seen_semi = False
    for i in range(samples):
        t = dur * (i + 0.5) / samples if dur > 0 else 0
        buf = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}"] + dec + ["-i", path, "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True).stdout
        if len(buf) < w * h * 4:
            continue
        a = buf[3::4]
        for c in range(3):
            if any(x > y + _TOL for x, y in zip(buf[c::4], a)):
                return True
        if not seen_semi:
            seen_semi = any(0 < y < 255 for y in a)
    return False if seen_semi else None


def _decoder(p):
    """ffmpeg's native VP8/VP9 decoders ignore the alpha side channel; libvpx reads it."""
    if p.get("vpx_alpha"):
        return ["-c:v", "libvpx-vp9" if p["codec"] == "vp9" else "libvpx"]
    return []


def _content_key(path):
    h = hashlib.sha256((RECIPE + ("" if premult_all() else "+straight")).encode())
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()[:24]


def _prune(root, keep):
    cutoff = time.time() - CACHE_DAYS * 86400
    try:
        for e in os.listdir(root):
            p = os.path.join(root, e)
            if e != keep and os.path.isdir(p) and os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def premult_all():
    """False by default, Mac and Windows: CapCut reads straight alpha (measured side by side, 2026-10-02 and
    2026-10-28). CAPCUT_ALPHA_PREMULT=1 (or true/yes/on) premultiplies every pixel instead, for a CapCut shown,
    side by side, to read premultiplied."""
    return os.environ.get("CAPCUT_ALPHA_PREMULT", "").strip().lower() in ("1", "true", "yes", "on")


def _hard_edge(a):
    """True where a pixel sits on a hard edge (type, a card's corner) rather than in a soft fade: see HARD_STEP."""
    import numpy as np
    step = np.zeros_like(a)
    for axis in (0, 1):
        d = np.abs(np.diff(a, axis=axis))
        pad = [(0, 0), (0, 0)]
        pad[axis] = (1, 0)
        step = np.maximum(step, np.pad(d, pad))
        pad[axis] = (0, 1)
        step = np.maximum(step, np.pad(d, pad))
    return (step >= HARD_STEP * 257.0) & (a >= KEEP_A * 257.0)


def _clean_edges(src, tmp):
    """ProRes 4444 with the hue noise in its faintest soft pixels greyed (see EDGE_A), tagged STRAIGHT_TAG; on the
    CAPCUT_ALPHA_PREMULT=1 route also premultiplied (every colour scaled by its alpha, tagged TAG). Frames go through
    numpy a frame at a time over pipes, so a full-length captions layer never sits in memory. Its sound is copied."""
    import numpy as np
    p = _probe(src)
    w, h = p["w"], p["h"]
    fps = p.get("fps") or "30"
    every = premult_all()
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt",
                            "rgba64le", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba64le", "-s", f"{w}x{h}",
                            "-r", str(fps), "-i", "-", "-i", src, "-map", "0:v:0", "-map", "1:a?", "-vf", CONVERT_VF,
                            "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-c:a", "copy",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                            "-metadata", f"comment={TAG if every else STRAIGHT_TAG}", "-f", "mov", tmp],
                           stdin=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    n = w * h * 8
    lo, hi = EDGE_A * 257.0, EDGE_FULL * 257.0
    try:                                                      # the Finish tab's bar counts these frames (no-op otherwise)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import export_progress
        num, _, den = str(fps).partition("/")
        frames = max(1.0, p["dur"] * float(num) / float(den or 1))
    except Exception:
        export_progress, frames = None, 1.0
    nf = 0                                                    # frames done (not `k`: the loop's edge blend uses k)
    try:
        while True:
            buf = dec.stdout.read(n)
            if len(buf) < n:
                break
            nf += 1
            if export_progress and nf % 15 == 0:
                export_progress.inner(nf / frames)
            f = np.frombuffer(buf, dtype="<u2").reshape(h, w, 4).astype(np.float32)
            a = f[..., 3]
            soft = ~_hard_edge(a)
            m = (a < hi) & soft
            if m.any():
                rgb = f[..., :3]
                grey = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
                k = np.clip((a - lo) / (hi - lo), 0.0, 1.0)[..., None]       # 0 = all grey, 1 = its own colour
                f[..., :3] = np.where(m[..., None], grey[..., None] + (rgb - grey[..., None]) * k, rgb)
            if every:
                f[..., :3] = f[..., :3] * (a / 65535.0)[..., None]
            enc.stdin.write(f.astype("<u2").tobytes())
        enc.stdin.close()
    except BaseException:
        # never wait on a pipe nobody reads: an exception mid-loop once left dec blocked on a full stdout and her
        # export frozen at 0% CPU (2026-10-23). Both ffmpegs end here; the error goes up as it is.
        for pr in (dec, enc):
            try:
                pr.kill()
            except Exception:
                pass
        enc.wait()
        raise
    finally:
        dec.wait()
    err = enc.stderr.read().decode(errors="replace")
    return enc.wait(), err


def _have_numpy():
    import importlib.util
    return importlib.util.find_spec("numpy") is not None


def _uv():
    exe = "uv.exe" if os.name == "nt" else "uv"
    found = shutil.which("uv") or os.path.join(os.path.expanduser("~"), ".local", "bin", exe)
    return found if os.path.isfile(found) else None


# The interpreter a builder runs under (plain python3 from a job's driver, say) may not have numpy, and then the
# clean never ran: every layer went in as rendered, faint edges and all. uv is on every setup, so it brings numpy
# for this one step (the same pins capcut_handoff.py asks for: numpy<2 on an Intel Mac, which has no newer wheel).
NUMPY_WITH = ("numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'", "numpy")


def _clean_edges_via_uv(src, tmp):
    uv = _uv()
    if not uv:
        return 1, "numpy isn't installed for this Python, and uv (which would bring it) wasn't found"
    cmd = [uv, "run", "--no-project", "--quiet"]
    for spec in NUMPY_WITH:
        cmd += ["--with", spec]
    cmd += ["python", os.path.abspath(__file__), "--clean-edges", src, tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        return 1, f"numpy isn't installed for this Python, and uv could not run: {e}"
    return r.returncode, (r.stderr or "").strip() or ("" if r.returncode == 0 else "uv could not bring numpy")


def prepare(src, dst, how):
    """Encode src to dst as CapCut-ready ProRes 4444, tagged. how = "clean" (a render: edge clean + premultiply,
    via numpy), "premultiply" (the same without numpy), "convert" (re-wrap a WebM/other transparent clip,
    premultiplied by default) or "unpremultiply" (straight route: undo a premultiplied copy).
    Atomic: dst is either the finished file or absent."""
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".mov", dir=os.path.dirname(os.path.abspath(dst)))
    os.close(fd)
    if how == "clean":
        try:
            rc, err = _clean_edges(src, tmp) if _have_numpy() else _clean_edges_via_uv(src, tmp)
        except Exception as e:
            rc, err = 1, str(e) or type(e).__name__
        if rc != 0 or not os.path.getsize(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError(f"could not clean {os.path.basename(src)}'s edges for CapCut: {err.strip()[-300:]}")
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
        return
    if how == "unpremultiply":
        vfs, tag = UNPREMULT_VFS, STRAIGHT_TAG
    elif how == "premultiply" or (how == "convert" and premult_all()):
        vfs, tag = PREMULT_VFS, TAG
    else:
        vfs, tag = (CONVERT_VF,), STRAIGHT_TAG
    # Any sound the clip carries comes through (copied when QuickTime can hold it, else re-encoded to PCM).
    a_codec = "pcm_s16le" if how == "convert" else "copy"
    for vf in vfs:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + _decoder(_probe(src)) + ["-i", src, "-map", "0:v:0",
                            "-map", "0:a?", "-vf", vf, "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits",
                            "16", "-c:a", a_codec, "-metadata", f"comment={tag}", "-f", "mov", tmp],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.getsize(tmp):
            break
    if r.returncode != 0 or not os.path.getsize(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(f"could not prepare {os.path.basename(src)} for CapCut's transparency: "
                           f"{(r.stderr or '').strip()[-300:]}")
    os.chmod(tmp, 0o644)                        # mkstemp makes it owner-only
    os.replace(tmp, dst)


def ready(path):
    """True when for_capcut(path) would hand back at once (nothing to prepare, or its copy is already cached): the
    Finish bar counts only the layers still to prepare."""
    try:
        if not path or not os.path.isfile(path) or not _plan(path):
            return True
        out = os.path.join(cache_root(), _content_key(path), os.path.basename(path))
        return os.path.isfile(out) and os.path.getsize(out) > 0
    except Exception:
        return False


def for_capcut(path):
    """A path to hand CapCut for this clip. Stills, opaque clips and an already-premultiplied copy come back
    unchanged; a render, a straight copy an earlier version made, or a transparent WebM comes back as a cached
    premultiplied ProRes 4444 copy with the SAME file name. The source is never modified."""
    if not path or not os.path.isfile(path):
        return path
    how = _plan(path)
    if not how:
        return path
    root = cache_root()
    key = _content_key(path)
    entry = os.path.join(root, key)
    out = os.path.join(entry, os.path.basename(path))
    if os.path.isfile(out) and os.path.getsize(out):
        os.utime(entry)                         # keep a used entry out of the prune
        return out
    os.makedirs(entry, exist_ok=True)
    print(f"  · preparing {os.path.basename(path)} for CapCut's transparency (once per layer, kept for next time)",
          flush=True)
    try:
        try:
            prepare(path, out, how)
        except Exception:
            if how != "clean" or not premult_all():
                raise
            # No numpy here (and no uv to bring it), or the clean hit a decode hiccup: premultiply with ffmpeg alone,
            # so the layer still composites right in CapCut. Only its faintest edge pixels keep their hue noise.
            prepare(path, out, "premultiply")
    except Exception as e:
        if how != "clean":
            raise
        # The edge clean is polish: when it can't run here (no numpy and no uv, a decode hiccup), the render goes in
        # as it is, exactly as before. Never a missing layer for it, and never silent: one line here, one in the log.
        why = str(e).strip().splitlines()[-1][:160] if str(e).strip() else type(e).__name__
        print(f"  · {os.path.basename(path)} went into CapCut as rendered, without its edge clean-up, so a faint ring "
              f"can show around its soft edges ({why})", flush=True)
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from fallbacks import note
            note("capcut-alpha", f"{os.path.basename(path)}: the edge clean-up could not run ({why}); "
                                 f"put the layer in as rendered")
        except Exception:
            pass
        shutil.rmtree(entry, ignore_errors=True)
        return path
    _prune(root, key)
    return out


# ── a picture that moves (an animated GIF, or a moving WebP) ─────────────────────────────────────────────────────
# CapCut plays a GIF only as a clip. Added as a picture (VectCut's add_image, every builder's add_png) it is a photo
# material and CapCut holds its first frame for the whole stretch (a buyer, 2026-10-28: "my gifs only show as still
# images"); added as a clip it lands as GIF bytes under a .mp4 name, played once if at all. So a moving picture goes
# in as straight ProRes 4444 at the reel's frame rate, looped to fill its stretch, see-through kept (a GIF's edge
# is all or nothing, so straight and premultiplied are the same pixels). Judged by its bytes, never its name:
# VectCut renames it image_<id>.png or video_<id>.mp4 on the way in.
LOOP_FPS = 30


def moving_image(path):
    """True when the file is a picture with more than one frame: a GIF, or a WebP whose header says it moves."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(32)
    except OSError:
        return False
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return head[12:16] == b"VP8X" and len(head) > 20 and bool(head[20] & 0x02)
    if head[:6] not in (b"GIF87a", b"GIF89a"):
        return False
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    try:
        return int((out or "0").strip().split(",")[0] or 0) > 1
    except ValueError:
        return False


def looped_clip(path, seconds=None):
    """A moving picture as CapCut plays it: straight ProRes 4444 at LOOP_FPS, looped to fill `seconds` (one play
    when None), named <its name>.mov. Cached by content and length like every copy here; the source is never
    modified. Raises RuntimeError with the reason when it can't be made."""
    h = hashlib.sha256(f"{RECIPE}|loop|{LOOP_FPS}|{seconds or 0:.3f}|{premult_all()}".encode())
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    key = "loop-" + h.hexdigest()[:24]
    entry = os.path.join(cache_root(), key)
    out = os.path.join(entry, os.path.splitext(os.path.basename(path))[0] + ".mov")
    if os.path.isfile(out) and os.path.getsize(out):
        os.utime(entry)
        return out
    os.makedirs(entry, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".mov", dir=entry)
    os.close(fd)
    src, once = path, None
    try:
        with open(path, "rb") as fh:
            webp = fh.read(12)[8:12] == b"WEBP"
        if webp:                                  # most ffmpeg builds can't read a moving WebP: Pillow unpacks it once
            once = tmp[:-4] + ".once.mov"
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import favorites_folder
            ok, err = favorites_folder._webp_frames_to_mov(path, once)
            if not ok:
                raise RuntimeError(f"could not read the moving picture {os.path.basename(path)} ({err.strip()[-200:]}). "
                                   "Save it as a .gif and add it again.")
            src = once
        vf = (f"fps={LOOP_FPS},format=rgba,pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=black@0,format=yuva444p12le")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + (["-stream_loop", "-1"] if seconds else []) + ["-i", src]
                           + (["-t", f"{float(seconds):.3f}"] if seconds else [])
                           + ["-map", "0:v:0", "-an", "-vf", vf, "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits",
                              "16", "-metadata", f"comment={TAG if premult_all() else STRAIGHT_TAG}", "-f", "mov", tmp],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.getsize(tmp):
            raise RuntimeError(f"could not make {os.path.basename(path)} into a clip CapCut plays: "
                               f"{(r.stderr or '').strip()[-300:]}")
        os.chmod(tmp, 0o644)
        os.replace(tmp, out)
    finally:
        for p in (tmp, once):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
    _prune(cache_root(), key)
    return out


def fix_in_place(path):
    """Prepare a transparent clip that already sits in a FRESH draft's assets folder (VectCut copies media in
    byte-for-byte, so by finalize the overlay is local). Never call this on a draft she may have opened: a media
    change there goes to a new version. Returns True when the file was replaced."""
    src = for_capcut(path)
    if src == path:
        return False
    install(src, path)
    return True


def install(src, dst):
    """Copy src over dst atomically (a new file, never a write into the old one, so a hard link to dst
    elsewhere keeps its original pixels)."""
    fd, tmp = tempfile.mkstemp(suffix=".mov", dir=os.path.dirname(os.path.abspath(dst)))
    os.close(fd)
    shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o644)
    os.replace(tmp, dst)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--clean-edges":     # the uv route above: numpy is here, clean one file
        _rc, _err = _clean_edges(sys.argv[2], sys.argv[3])
        sys.stderr.write(_err)
        raise SystemExit(_rc)
    if len(sys.argv) < 2:
        print("usage: python3 product/capcut_alpha.py <overlay.mov|.mp4|.webm> ...   # prints the CapCut-ready path")
        raise SystemExit(2)
    for p in sys.argv[1:]:
        q = for_capcut(p)
        print(q if q != p else f"{p}  (already fine for CapCut)")
