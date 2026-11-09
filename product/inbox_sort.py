#!/usr/bin/env python3
"""inbox_sort.py — she drops anything in inbox/; the engine files a copy of it where it belongs.

One place to drop things, and an engine folder that stays organized without her doing it:

    a sound effect (audio up to 15 s)       -> favorites/sounds/
    a song for a music bed (longer audio)   -> favorites/music/
    a see-through .mov graphic              -> favorites/graphics/
    a .heic / .heif photo, an .svg graphic  -> favorites/photos/, favorites/graphics/ (the picker can't place these)
    a font (.ttf, .otf)                     -> favorites/fonts/      (her own style packs)
    an image or GIF (.gif .png .jpg .webp)  -> stays in inbox/: the visual editor's Image > Inbox puts
                                               one on a line as a one-off (copied into that reel only); to keep one
                                               in her library she drops it on Image > Favorites
    footage (a video with no see-through)   -> stays in inbox/ until she edits it: intake copies it into that
                                               reel's raw/ folder (rough-cut), and then it's saved too

It always COPIES, never moves or changes her files. Each copy is checked (same size) before the inbox file is
called safe to delete, and a copy is never made twice: the same file dropped again is recognized and skipped. A
name already used by a different file gets " 2", " 3"... so nothing of hers is ever written over.

The sorting rules for sounds, GIFs and graphics are favorites_folder.examine()'s, so what the inbox files is exactly
what the Swap menus can use; a file that can't be used anywhere is named with the reason and left where it is.

    python3 product/inbox_sort.py            # sort, then say what went where and what's safe to delete
    python3 product/inbox_sort.py --dry-run  # say what it would do
    python3 product/inbox_sort.py --json
"""
import hashlib, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PHOTO_EXT = (".jpg", ".jpeg", ".heic", ".heif")
FONT_EXT = (".ttf", ".otf")
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".avi", ".mkv")
SKIP = {"README.md", ".gitkeep", ".DS_Store", "Thumbs.db", "desktop.ini"}
DRAWER = {"sfx": "sounds", "music": "music", "gif": "gifs", "graphic": "graphics", "photo": "photos", "font": "fonts"}


def inbox():
    return os.path.join(ROOT, "inbox")


def favorites():
    return os.path.join(ROOT, "favorites")


def _ledger_path():
    return os.path.join(ROOT, "_local", "inbox-sorted.json")


def _ledger():
    try:
        return json.load(open(_ledger_path(), encoding="utf-8"))
    except Exception:
        return {}


def _fingerprint(p):
    st = os.stat(p)
    h = hashlib.sha1()
    with open(p, "rb") as f:
        h.update(f.read(1 << 20))                     # the first MB + size: fast, and enough to tell files apart
    return f"{st.st_size}-{h.hexdigest()[:16]}"


def _has_alpha_video(p):
    """A video with a see-through background is a graphic (a sticker, a lower third), not footage."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt,codec_name",
                              "-of", "json", p], capture_output=True, text=True, timeout=30).stdout
        s = (json.loads(out).get("streams") or [{}])[0]
        fmt = str(s.get("pix_fmt", ""))
        return any(k in fmt for k in ("yuva", "rgba", "argb", "bgra", "abgr", "gbrap")) or s.get("codec_name") in ("qtrle", "png")
    except Exception:
        return False


def classify(path):
    """(drawer key or 'footage', None) for a file the engine can use; (None, reason) for one it can't."""
    ext = os.path.splitext(path)[1].lower()
    if ext in FONT_EXT:
        return "font", None
    if ext in PHOTO_EXT:
        return "photo", None
    if ext in VIDEO_EXT and not (ext in (".mov",) and _has_alpha_video(path)):
        return "footage", None
    import favorites_folder as ff
    entry, why = ff.examine(path)
    if entry:
        if entry["kind"] == "sound":
            return ("music" if (entry.get("duration") or 0) > ff.LONGEST_SFX_S else "sfx"), None
        if entry["kind"] == "graphic" and ext == ".webp":
            return "photo" if not entry.get("alpha") else "graphic", None
        return entry["kind"], None
    return None, why


def _dest_for(kind, name):
    d = os.path.join(favorites(), DRAWER[kind])
    os.makedirs(d, exist_ok=True)
    stem, ext = os.path.splitext(name)
    p, n = os.path.join(d, name), 2
    while os.path.exists(p):
        p = os.path.join(d, f"{stem} {n}{ext}"); n += 1
    return p


def sort(dry_run=False):
    """Copy everything in inbox/ to where it belongs. Returns {"filed": [...], "footage": [...], "skipped": [...],
    "refused": [...]} with plain paths relative to the engine, for the message to her."""
    out = {"filed": [], "footage": [], "images": [], "skipped": [], "refused": []}
    src_root = inbox()
    if not os.path.isdir(src_root):
        return out
    led = _ledger()
    for dp, dirs, files in os.walk(src_root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in sorted(files):
            if fn in SKIP or fn.startswith((".", "~$")):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
            try:
                fp = _fingerprint(p)
            except OSError:
                out["refused"].append({"file": rel, "why": "your computer won't let the engine open it."})
                continue
            done = led.get(fp)
            if done and os.path.isfile(os.path.join(ROOT, done)):
                out["skipped"].append({"file": rel, "to": done})          # already filed, same file
                continue
            kind, why = classify(p)
            if kind is None:
                out["refused"].append({"file": rel, "why": why})
                continue
            if kind == "footage":
                out["footage"].append({"file": rel})
                continue
            if kind in ("gif", "photo", "graphic") and os.path.splitext(fn)[1].lower() in (".gif", ".png", ".jpg", ".jpeg", ".webp"):   # one-offs:
                                                             # they stay (the picker's Inbox tab can use exactly these; .heic/.svg file as before)
                out["images"].append({"file": rel, "kind": kind})
                continue
            dest = _dest_for(kind, fn)
            to = os.path.relpath(dest, ROOT).replace(os.sep, "/")
            if not dry_run:
                tmp = dest + ".part"
                shutil.copy2(p, tmp)
                if os.path.getsize(tmp) != os.path.getsize(p):
                    os.remove(tmp)
                    out["refused"].append({"file": rel, "why": "the copy didn't come out whole. Try again in a moment."})
                    continue
                os.replace(tmp, dest)
                led[fp] = to
            out["filed"].append({"file": rel, "to": to, "kind": kind})
    if not dry_run and out["filed"]:
        os.makedirs(os.path.dirname(_ledger_path()), exist_ok=True)
        tmp = _ledger_path() + ".tmp"
        json.dump(led, open(tmp, "w", encoding="utf-8"), indent=1)
        os.replace(tmp, _ledger_path())
    return out


WORDS = {"sfx": "sound effect", "music": "song", "gif": "GIF", "graphic": "graphic", "photo": "photo", "font": "font"}


def say(r):
    """The message to her, in plain words."""
    lines = []
    if r["filed"]:
        lines.append(f"Filed {len(r['filed'])} thing{'s' if len(r['filed']) > 1 else ''} from your inbox into your engine folder:")
        for f in r["filed"]:
            lines.append(f"  · {os.path.basename(f['file'])} ({WORDS[f['kind']]}) → {f['to']}")
    if r["filed"] or r["skipped"]:
        lines.append("Those are safe to delete from your inbox whenever you like; your engine has its own copy.")
    if r.get("images"):
        n = len(r["images"])
        lines.append(f"{n} image{'s' if n > 1 else ''} and GIF{'s' if n > 1 else ''} stay{'' if n > 1 else 's'} in your inbox for one-offs: "
                     f"add one to a line with Image, then the Inbox tab (it's copied into that reel only). To keep one in your "
                     f"library, drop it on the Favorites tab there.") if n > 1 else lines.append(
                     "1 image stays in your inbox for a one-off: add it to a line with Image, then the Inbox tab (it's copied "
                     "into that reel only). To keep it in your library, drop it on the Favorites tab there.")
    if r["footage"]:
        n = len(r["footage"])
        lines.append(f"{n} video{'s' if n > 1 else ''} stay{'' if n > 1 else 's'} in your inbox: each one is copied into "
                     f"its reel's own folder when you edit it.")
    for f in r["refused"]:
        lines.append(f"  · {os.path.basename(f['file'])} stays where it is: {f['why']}")
    return "\n".join(lines) or "Your inbox has nothing new to file."


def main(argv):
    r = sort(dry_run="--dry-run" in argv)
    print(json.dumps(r, indent=1) if "--json" in argv else say(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
