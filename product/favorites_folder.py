#!/usr/bin/env python3
"""favorites_folder.py — the folder she drops her favorite sounds, GIFs and graphics into, read for the engine.

`favorites/` at the engine root has three drawers: `sounds/`, `gifs/` and `graphics/`. She drags files in from
Finder; the visual editor's Swap menus list them FIRST, ahead of the engine's own library. This is the plain-file
twin of the CapCut favorites project (`product/favorites.py`, which reads a CapCut project she points at): no
CapCut needed, nothing to learn. Both are hers, and both outrank the bundled library.

What scan() does with each file (the drawer she used is a hint, never a rule: a GIF dropped in sounds/ is still a
GIF, and is listed with her GIFs):
  * audio (.mp3 .wav .m4a .aac .aif/.aiff .flac .ogg .caf)  -> a sound. Up to 15 s is a sound effect (`use: sfx`),
    longer is a song for the music bed (`use: music`), the same line favorites.py draws (LONGEST_SFX_S).
  * .gif, and a .webp that moves                            -> a GIF
  * .png, .svg, a .webp that holds still, and a .mov/.webm with a see-through background -> a graphic
  * anything else is REFUSED with a plain reason she can act on (a .jpg can't be see-through, an .mp4 is footage,
    a file that won't open is named as one that won't open). Nothing is ever silently skipped.
Each file is checked: readable, opens in ffprobe, under the size and length limits below.

Rendered routes need motion graphics as transparent video, so a GIF (or a moving .webp, or a .webm graphic, whose
see-through background CapCut drops) gets a ProRes 4444 copy with alpha the first time it is needed:
render_copy(id). Copies live in `_local/favorites-cache/`, named by the file's size and timestamp, so a second ask
is instant and a file she replaces gets a fresh copy. Her originals are NEVER modified, moved or renamed. A GIF
placed for longer than one play asks for render_copy(id, seconds): looped to fill that stretch (one play alone
held its last frame, a still, for the rest of it).

Her files never leave her computer and never ship: `.gitignore` ignores everything in `favorites/` but the
READMEs, make-ship.sh copies only the READMEs into the buyer bundle (check-ship.sh section 35 holds it), and an
update never creates, overwrites or deletes anything in it but the READMEs (scripts/apply-update.py PROTECTED,
make-update.py, product/keep_changes.py SKIP_DIRS).

    python3 product/favorites_folder.py scan            # what's in her folder, what each is for, what was refused
    python3 product/favorites_folder.py scan --json     # the same, for a script or the page
    python3 product/favorites_folder.py prepare <id> [seconds]   # the render-ready copy of one GIF / graphic
                                                                 # (cached); a GIF looped to fill [seconds]
    python3 product/favorites_folder.py where           # the folder's path, to open it for her

Stdlib + ffmpeg/ffprobe (already required by the engine). Pillow is used only as a fallback for a moving .webp an
older ffmpeg cannot read; without either, that one file is refused with the reason.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

for _s in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print every character in her file names
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FOLDER = os.path.join(ROOT, "favorites")
DRAWERS = ("sounds", "music", "gifs", "graphics", "photos", "broll", "fonts")
NOT_SWAPPABLE = ("photos", "broll", "fonts")   # kept organized here for covers, carousels, cutaways (Media)
                                                #   and her own style packs, not Swap menus
CACHE = os.path.join(ROOT, "_local", "favorites-cache")

AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".aif", ".aiff", ".flac", ".ogg", ".caf")
GIF_EXT = (".gif",)
WEBP_EXT = (".webp",)
GRAPHIC_EXT = (".png", ".svg", ".mov", ".webm")
LONGEST_SFX_S = 15.0          # same line as favorites.LONGEST_SFX_S: longer than this is a song, not a sound effect
MAX_BYTES = {"sound": 200 * 2**20, "gif": 50 * 2**20, "graphic": 500 * 2**20}
MAX_SECONDS = {"sound": 15 * 60.0, "gif": 60.0, "graphic": 120.0}
SKIP_NAMES = {"README.md", ".gitkeep", ".DS_Store", "Thumbs.db", "desktop.ini"}

# Plain reasons for the file types people most often drop in, said the way she would fix them.
REFUSE_EXT = {
    (".jpg", ".jpeg", ".heic", ".heif"): "a photo file can't have a see-through background, so it would sit on her "
                                         "video as a box. Save it as a .png with a transparent background instead.",
    (".mp4", ".m4v"): "an .mp4 can't carry a see-through background, so it's footage rather than a graphic. Put "
                      "b-roll in favorites/broll/, or export the graphic as a .mov with transparency "
                      "(ProRes 4444).",
    (".psd", ".ai", ".pdf", ".eps", ".sketch", ".fig", ".key"): "design files have to be exported first. Export it "
                                                               "as a .png (still) or a .gif (moving).",
    (".zip", ".rar", ".7z"): "it's a zipped folder. Unzip it and drop the files themselves in.",
}


# ── probing ────────────────────────────────────────────────────────────────────────────────────────────────
def _key(path):
    """The file as it is now: size + modification time. A replaced file gets a new key, so nothing goes stale."""
    st = os.stat(path)
    return f"{st.st_size}-{st.st_mtime_ns}"


def _hash(path):
    return hashlib.sha1(f"{os.path.abspath(path)}|{_key(path)}".encode("utf-8")).hexdigest()[:12]


def _index_path():
    return os.path.join(CACHE, "index.json")


def _load_index():
    try:
        with open(_index_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_index(ix):
    os.makedirs(CACHE, exist_ok=True)
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ix, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, _index_path())


def ffprobe(path):
    """What ffprobe says about a file, or None when it cannot open it."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,nb_frames,duration"
                            ":stream_tags=alpha_mode", "-of", "json", path],
                           capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return None


def _num(v):
    try:
        f = float(v)
        return f if f == f and f >= 0 else None      # NaN and negatives are "unknown"
    except (TypeError, ValueError):
        return None


def _webp_animated(path):
    """True when a .webp moves. Read from its own header (the VP8X animation flag), so it costs nothing and does not
    depend on the ffmpeg version: older ffmpeg builds cannot decode a moving WebP at all."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except OSError:
        return False
    if head[:4] != b"RIFF" or head[8:12] != b"WEBP":
        return False
    return head[12:16] == b"VP8X" and bool(head[20] & 0x02)


def _has_alpha(stream):
    pf = str(stream.get("pix_fmt") or "")
    if (stream.get("tags") or {}).get("alpha_mode") == "1":          # a .webm made with transparency
        return True
    return bool(re.search(r"(yuva|rgba|bgra|argb|abgr|gbrap|ya8|ya16|pal8)", pf))


def _svg_ok(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096).decode("utf-8", "replace").lower()
    except OSError:
        return False
    return "<svg" in head


# ── one file ───────────────────────────────────────────────────────────────────────────────────────────────
def _pretty(stem):
    s = re.sub(r"[_\-]+", " ", stem).strip()
    return s[:1].upper() + s[1:] if s else stem


def examine(path, drawer=None):
    """One file -> (entry, None) when the engine can use it, (None, reason) when it cannot. Never raises."""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    rel = os.path.relpath(path, FOLDER).replace(os.sep, "/")
    for exts, why in REFUSE_EXT.items():
        if ext in exts:
            return None, why
    if ext in AUDIO_EXT:
        kind = "sound"
    elif ext in GIF_EXT:
        kind = "gif"
    elif ext in WEBP_EXT:
        kind = "gif" if _webp_animated(path) else "graphic"
    elif ext in GRAPHIC_EXT:
        kind = "graphic"
    else:
        return None, (f"the engine doesn't know what to do with a {ext or 'file with no extension'} file. Sounds can "
                      f"be .mp3, .wav or .m4a; GIFs .gif; graphics .png, .svg or a see-through .mov.")
    if not os.access(path, os.R_OK):
        return None, "your computer won't let the engine open it. Check the file's permissions, or copy it in again."
    size = os.path.getsize(path)
    if size == 0:
        return None, "the file is empty (0 bytes). It may still be downloading; drop it in again once it's finished."
    if size > MAX_BYTES[kind]:
        return None, (f"it's {size / 2**20:.0f} MB, more than the {MAX_BYTES[kind] // 2**20} MB a favorite "
                      f"{kind} can be. Trim it or export it smaller.")

    entry = {"id": f"folder:{rel}", "kind": kind, "name": _pretty(os.path.splitext(name)[0]), "file": path,
             "rel": f"favorites/{rel}", "source": "favorite", "size": size, "duration": None,
             "w": None, "h": None, "alpha": None, "animated": False, "note": None}
    if drawer and drawer not in {"sound": ("sounds", "music"), "gif": ("gifs",), "graphic": ("graphics",)}[kind]:
        entry["note"] = f"It's in {drawer}/, but it's a {kind}, so it's listed with your {kind}s."

    if ext == ".svg":
        if not _svg_ok(path):
            return None, "it's named .svg but it isn't an SVG drawing inside. Export it again as an SVG or a .png."
        entry.update(alpha=True, routes=["medium", "well-done"])
        note = "An SVG shows on the rendered routes; for a CapCut draft, export it as a .png."
        entry["note"] = (entry["note"] + " " + note) if entry["note"] else note
        return entry, None

    if ext in WEBP_EXT and kind == "gif":
        probe = ffprobe(path)      # newer ffmpeg reads a moving WebP; older ones get the Pillow fallback in render_copy
        vs = next((s for s in (probe or {}).get("streams", []) if s.get("codec_type") == "video"), {})
        entry.update(w=vs.get("width"), h=vs.get("height"), alpha=True, animated=True,
                     duration=_num((probe or {}).get("format", {}).get("duration")))
        if not probe and not _pillow_webp():
            return None, ("it's a moving .webp, and this computer can't read those yet. Save it as a .gif instead.")
        entry["routes"] = ["raw", "medium", "well-done"]
        return entry, None

    probe = ffprobe(path)
    if not probe:
        return None, "it won't open. The file may be damaged or only partly downloaded; drop in a fresh copy."
    streams = probe.get("streams", []) or []
    dur = _num((probe.get("format") or {}).get("duration"))
    if kind == "sound":
        if not any(s.get("codec_type") == "audio" for s in streams):
            return None, "there's no sound in it."
        if dur is None or dur <= 0:
            return None, "the engine can't tell how long it is, so it can't place it. Export it again as an .mp3."
        if dur > MAX_SECONDS["sound"]:
            return None, f"it's {dur / 60:.0f} minutes long, longer than a reel could use. Trim it under 15 minutes."
        entry.update(duration=round(dur, 3), use="sfx" if dur <= LONGEST_SFX_S else "music",
                     routes=["raw", "medium", "well-done"])
        return entry, None

    vs = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not vs:
        return None, "there's no picture in it."
    entry.update(w=vs.get("width"), h=vs.get("height"), alpha=_has_alpha(vs))
    frames = _num(vs.get("nb_frames"))
    if kind == "gif":
        entry.update(animated=bool((dur or 0) > 0.05 or (frames or 0) > 1), duration=round(dur, 3) if dur else None,
                     routes=["raw", "medium", "well-done"])
        if dur and dur > MAX_SECONDS["gif"]:
            return None, f"it runs {dur:.0f} seconds, longer than a GIF on a reel should. Trim it under a minute."
        return entry, None
    # a graphic
    if ext in (".mov", ".webm"):
        if not entry["alpha"]:
            return None, ("it's a video with no see-through background, so it would cover her whole frame. Export it "
                          "with transparency (a .mov in ProRes 4444), or put it in favorites/broll/ to cut away to it as b-roll.")
        if dur and dur > MAX_SECONDS["graphic"]:
            return None, f"it runs {dur:.0f} seconds, longer than a graphic on a reel should. Trim it under 2 minutes."
        entry.update(animated=True, duration=round(dur, 3) if dur else None, routes=["raw", "medium", "well-done"])
        return entry, None
    entry["routes"] = ["raw", "medium", "well-done"]
    if not entry["alpha"]:
        note = "It has no see-through background, so it will show as a box."
        entry["note"] = (entry["note"] + " " + note) if entry["note"] else note
    return entry, None


def _pillow_webp():
    try:
        from PIL import features
        return bool(features.check("webp"))
    except Exception:
        return False


# ── the whole folder ───────────────────────────────────────────────────────────────────────────────────────
def ensure_folder():
    """Make favorites/ and its three drawers if a fresh copy is missing one. Never touches what is in them."""
    for d in DRAWERS:
        os.makedirs(os.path.join(FOLDER, d), exist_ok=True)
    return FOLDER


def _files():
    """(path, drawer) for every file she dropped in, any depth, in a stable order."""
    out = []
    if not os.path.isdir(FOLDER):
        return out
    for dp, dirs, files in os.walk(FOLDER):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        rel = os.path.relpath(dp, FOLDER)
        drawer = None if rel == "." else rel.replace(os.sep, "/").split("/")[0]
        if drawer in NOT_SWAPPABLE:
            continue
        for fn in sorted(files):
            if fn in SKIP_NAMES or fn.startswith(".") or fn.startswith("~$"):
                continue
            out.append((os.path.join(dp, fn), drawer))
    return out


def scan():
    """Everything in her favorites folder, sorted into what the Swap menus use:
    {"sounds": [...], "gifs": [...], "graphics": [...], "refused": [{"file", "reason"}]}.
    Each usable entry: {"id", "kind", "name", "file" (absolute), "rel", "source": "favorite", "size", "duration",
    "w", "h", "alpha", "animated", "routes", "note", and for sounds "use": "sfx"|"music"}. A GIF's "render_file" is
    its ProRes copy once render_copy() has made one (None until then). Probe results are cached by size + time."""
    ix, seen = _load_index(), {}
    out = {"sounds": [], "gifs": [], "graphics": [], "refused": []}
    for path, drawer in _files():
        rel = os.path.relpath(path, FOLDER).replace(os.sep, "/")
        try:
            k = _key(path)
        except OSError:
            out["refused"].append({"file": f"favorites/{rel}", "reason": "it vanished while being read. Try again."})
            continue
        hit = ix.get(rel)
        if hit and hit.get("key") == k and hit.get("drawer") == drawer:
            entry, reason = hit.get("entry"), hit.get("reason")
            if entry:
                entry = dict(entry, file=path)
        else:
            entry, reason = examine(path, drawer)
        seen[rel] = {"key": k, "drawer": drawer, "entry": entry, "reason": reason}
        if entry:
            if entry["kind"] in ("gif",) or (entry["kind"] == "graphic" and path.lower().endswith(".webm")):
                cached = _cache_file(path, ".mov")
                entry["render_file"] = cached if os.path.isfile(cached) else None
            out[{"sound": "sounds", "gif": "gifs", "graphic": "graphics"}[entry["kind"]]].append(entry)
        else:
            out["refused"].append({"file": f"favorites/{rel}", "reason": reason})
    if seen != ix:
        try:
            _save_index(seen)
        except OSError:
            pass                     # a read-only _local/ costs only speed, never the listing
    _prune(seen)
    return out


def _prune(seen):
    """Drop cached copies of files she has since removed or replaced (they are named by the file's key)."""
    if not os.path.isdir(CACHE):
        return
    live = set()
    for rel, v in seen.items():
        p = os.path.join(FOLDER, rel)
        try:
            live.add(_hash(p))
        except OSError:
            pass
    for fn in os.listdir(CACHE):
        m = re.match(r".*-([0-9a-f]{12})\.(mov|png|m4a)$", fn)
        if m and m.group(1) not in live:
            try:
                os.remove(os.path.join(CACHE, fn))
            except OSError:
                pass


def entry(fid):
    """The scanned entry for one id ('folder:gifs/wave.gif'), or None."""
    if not str(fid).startswith("folder:"):
        return None
    rel = str(fid)[len("folder:"):]
    p = os.path.realpath(os.path.join(FOLDER, rel))
    if not p.startswith(os.path.realpath(FOLDER) + os.sep) or not os.path.isfile(p):
        return None
    for group in scan().values():
        for e in group:
            if e.get("id") == fid:
                return e
    return None


# ── render-ready copies (never her original) ───────────────────────────────────────────────────────────────
def _cache_file(path, ext):
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.splitext(os.path.basename(path))[0]).strip("-")[:40] or "fav"
    return os.path.join(CACHE, f"{stem}-{_hash(path)}{ext}")


_PRORES = ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-vendor", "apl0", "-an"]
_EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos,format=yuva444p10le"


def _ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, timeout=600)
    return r.returncode == 0, (r.stderr or "")[-400:]


def _webp_frames_to_mov(src, out):
    """Moving WebP an older ffmpeg cannot read: Pillow unpacks the frames, ffmpeg wraps them as ProRes 4444."""
    try:
        from PIL import Image, ImageSequence
    except Exception:
        return False, "Pillow is not available"
    tmp = tempfile.mkdtemp(prefix="fav-webp-")
    try:
        im = Image.open(src)
        durs = []
        for i, fr in enumerate(ImageSequence.Iterator(im)):
            fr.convert("RGBA").save(os.path.join(tmp, f"f{i:05d}.png"))
            durs.append(max(10, int(fr.info.get("duration", 100) or 100)))
        if not durs:
            return False, "no frames"
        fps = max(1.0, min(60.0, 1000.0 / (sum(durs) / len(durs))))
        return _ffmpeg(["-framerate", f"{fps:.3f}", "-i", os.path.join(tmp, "f%05d.png"), "-vf", _EVEN, *_PRORES, out])
    except Exception as e:      # noqa: BLE001 — a file Pillow can't read is refused with the reason, never a crash
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_copy(fid_or_path, seconds=None):
    """The file a rendered route (and CapCut) should use for this favorite. A GIF, a moving .webp, or a .webm graphic
    is converted ONCE into a transparent ProRes 4444 .mov in _local/favorites-cache/ and reused after that; a .png,
    .svg or see-through .mov is already usable and comes back as it is. `seconds`: how long a GIF is on screen, so
    its copy loops to fill it (cached per length). Raises ValueError with a plain reason when the file is not one of
    hers or cannot be converted. Her original is never written to."""
    if str(fid_or_path).startswith("folder:"):
        e = entry(fid_or_path)
        if not e:
            raise ValueError(f"There's no favorite called {fid_or_path!r} in your favorites folder (any more).")
    else:
        p = os.path.abspath(str(fid_or_path))
        if not p.startswith(os.path.realpath(FOLDER) + os.sep) and not p.startswith(FOLDER + os.sep):
            raise ValueError("Only files in your favorites folder get render copies here.")
        e, why = examine(p)
        if not e:
            raise ValueError(f"{os.path.basename(p)}: {why}")
    src = e["file"]
    ext = os.path.splitext(src)[1].lower()
    if e["kind"] == "sound" or ext in (".png", ".svg", ".mov"):
        return src
    out = _cache_file(src, ".mov")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return _looped(out, src, seconds) if seconds and e["kind"] == "gif" else out
    os.makedirs(CACHE, exist_ok=True)
    tmp = out[:-4] + ".part.mov"
    if ext == ".webm":       # read with libvpx so the alpha plane survives (ffmpeg's native vp9 decoder drops it)
        ok, err = _ffmpeg(["-c:v", "libvpx-vp9", "-i", src, "-vf", _EVEN, *_PRORES, tmp])
        if not ok:
            ok, err = _ffmpeg(["-i", src, "-vf", _EVEN, *_PRORES, tmp])
    else:
        ok, err = _ffmpeg(["-i", src, "-vf", _EVEN, *_PRORES, tmp])
        if not ok and ext in WEBP_EXT:
            ok, err = _webp_frames_to_mov(src, tmp)
    if not ok or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ValueError(f"{os.path.basename(src)} couldn't be turned into a see-through video ({err.strip() or 'no output'}). "
                         f"Save it again as a .gif and drop it in.")
    os.replace(tmp, out)
    return _looped(out, src, seconds) if seconds and e["kind"] == "gif" else out


def _looped(once, src, seconds):
    """The one-play copy, looped to fill `seconds` (ProRes is all key frames, so the loop is a straight copy)."""
    out = _cache_file(src, f"-loop{int(round(float(seconds) * 1000))}.mov")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    tmp = out[:-4] + ".part.mov"
    ok, err = _ffmpeg(["-stream_loop", "-1", "-i", once, "-t", f"{float(seconds):.3f}", "-c", "copy", tmp])
    if not ok or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ValueError(f"{os.path.basename(src)} couldn't be looped to {float(seconds):g} seconds "
                         f"({err.strip() or 'no output'}).")
    os.replace(tmp, out)
    return out


def preview_path(fid):
    """A file the page can show in a browser: GIF / PNG / SVG / WebP as they are; a .mov or .webm graphic as a still
    (a .png poster from its middle, cached), since a browser cannot play ProRes. Sounds: sound_plan.preview_path."""
    e = entry(fid)
    if not e:
        raise ValueError(f"There's no favorite called {fid!r} in your favorites folder (any more).")
    src = e["file"]
    ext = os.path.splitext(src)[1].lower()
    if e["kind"] == "sound":
        import sound_plan
        return sound_plan.preview_path(fid)
    if ext not in (".mov", ".webm"):
        return src
    out = _cache_file(src, ".png")
    if os.path.isfile(out):
        return out
    os.makedirs(CACHE, exist_ok=True)
    at = max(0.0, (e.get("duration") or 0) / 2)
    dec = ["-c:v", "libvpx-vp9"] if ext == ".webm" else []
    tmp = out[:-4] + ".part.png"
    ok, _err = _ffmpeg(["-ss", f"{at:.3f}", *dec, "-i", src, "-frames:v", "1", tmp])
    if not ok and dec:
        ok, _err = _ffmpeg(["-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", tmp])
    if not ok or not os.path.isfile(tmp):
        raise ValueError(f"{os.path.basename(src)}: couldn't make a still to show it.")
    os.replace(tmp, out)
    return out


def sounds(use=None):
    """Her favorite-folder sounds, optionally only the sound effects (use='sfx') or only the songs (use='music')."""
    return [e for e in scan()["sounds"] if use is None or e.get("use") == use]


# ── CLI ────────────────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    cmd = a[0] if a else "scan"
    if cmd == "where":
        print(ensure_folder())
        return 0
    if cmd == "scan":
        res = scan()
        if "--json" in a:
            print(json.dumps(res, indent=1, ensure_ascii=False))
            return 0
        if not any(res[k] for k in res):
            print(f"Your favorites folder is empty. Drop sounds, GIFs or graphics into {FOLDER} and they show up "
                  f"first in every Swap menu.")
            return 0
        for k, label in (("sounds", "Sounds"), ("gifs", "GIFs"), ("graphics", "Graphics")):
            if res[k]:
                print(f"{label}:")
                for e in res[k]:
                    bits = [f"{e['duration']:.1f}s" if e.get("duration") else None,
                            ("song" if e.get("use") == "music" else "sound effect") if k == "sounds" else None,
                            f"{e['w']}x{e['h']}" if e.get("w") else None]
                    print(f"  {e['name']}  ({', '.join(b for b in bits if b)})  [{e['id']}]"
                          + (f"\n    {e['note']}" if e.get("note") else ""))
        if res["refused"]:
            print("Not used, and why:")
            for r in res["refused"]:
                print(f"  {r['file']}: {r['reason']}")
        return 0
    if cmd == "prepare" and len(a) > 1:
        try:
            print(render_copy(a[1], float(a[2]) if len(a) > 2 else None))
            return 0
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
    print(__doc__.strip().split("\n")[0])
    print("Usage: favorites_folder.py scan [--json] | prepare <id> [seconds] | where")
    return 2


if __name__ == "__main__":
    sys.exit(main())
