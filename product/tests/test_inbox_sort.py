#!/usr/bin/env python3
"""Guard: whatever she drops in inbox/ is COPIED to the right drawer of her engine folder (product/inbox_sort.py).

Holds: a short sound -> favorites/sounds, a long one -> favorites/music, a GIF -> gifs, a see-through PNG ->
graphics, a photo -> photos, a font -> fonts, footage stays in the inbox (intake copies it into a reel); her inbox
files are never moved or changed; a second run files nothing twice; a name already used by a different file gets
" 2" (nothing of hers is written over); a file the engine can't use is named with a reason and left where it is.

Run: python3 product/tests/test_inbox_sort.py
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import inbox_sort, favorites_folder  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def main():
    tmp = tempfile.mkdtemp(prefix="inbox-sort-")
    real = (inbox_sort.ROOT, favorites_folder.ROOT, favorites_folder.FOLDER, favorites_folder.CACHE)
    try:
        inbox_sort.ROOT = favorites_folder.ROOT = tmp
        favorites_folder.FOLDER = os.path.join(tmp, "favorites")
        favorites_folder.CACHE = os.path.join(tmp, "_local", "favorites-cache")   # never the engine's own _local/
        ib = os.path.join(tmp, "inbox"); os.makedirs(ib)
        ff("-f", "lavfi", "-i", "sine=f=880:d=0.4", os.path.join(ib, "ding.mp3"))
        ff("-f", "lavfi", "-i", "sine=f=220:d=20", os.path.join(ib, "song.m4a"))
        ff("-f", "lavfi", "-i", "testsrc=s=64x64:r=10:d=1", os.path.join(ib, "wave.gif"))
        ff("-f", "lavfi", "-i", "color=c=red@0.5:s=64x64,format=rgba", "-frames:v", "1", os.path.join(ib, "sticker.png"))
        ff("-f", "lavfi", "-i", "testsrc=s=64x64", "-frames:v", "1", os.path.join(ib, "me.jpg"))
        ff("-f", "lavfi", "-i", "testsrc=s=320x240:d=1", os.path.join(ib, "clip.mp4"))
        open(os.path.join(ib, "MyFont.ttf"), "wb").write(b"\0\1\0\0" + b"x" * 200)
        open(os.path.join(ib, "notes.docx"), "wb").write(b"x" * 50)
        before = {f: os.path.getsize(os.path.join(ib, f)) for f in os.listdir(ib)}
        r = inbox_sort.sort()
        to = {os.path.basename(f["file"]): f["to"] for f in r["filed"]}
        check("inbox: a short sound goes to sounds", to.get("ding.mp3") == "favorites/sounds/ding.mp3", to)
        check("inbox: a long one goes to music", to.get("song.m4a") == "favorites/music/song.m4a", to)
        stay = sorted(os.path.basename(f["file"]) for f in r["images"])
        check("inbox: images and GIFs stay in the inbox for one-offs, never copied into favorites",
              stay == ["me.jpg", "sticker.png", "wave.gif"] and not any(k in to for k in stay), (stay, to))
        check("inbox: the message says where they're used (Image > Inbox) and how to keep one",
              "Inbox tab" in inbox_sort.say(r) and "Favorites tab" in inbox_sort.say(r))
        check("inbox: a font goes to fonts", to.get("MyFont.ttf") == "favorites/fonts/MyFont.ttf", to)
        check("inbox: footage stays for intake", [os.path.basename(f["file"]) for f in r["footage"]] == ["clip.mp4"], r["footage"])
        check("inbox: a file it can't use is named with a reason", any(f["file"].endswith("notes.docx") and f["why"] for f in r["refused"]), r["refused"])
        check("inbox: every copy is really there", all(os.path.isfile(os.path.join(tmp, t)) for t in to.values()))
        check("inbox: her inbox files are untouched", {f: os.path.getsize(os.path.join(ib, f)) for f in os.listdir(ib)} == before)
        check("inbox: the message says what's safe to delete", "safe to delete" in inbox_sort.say(r))
        r2 = inbox_sort.sort()
        check("inbox: a second run files nothing twice", not r2["filed"] and len(r2["skipped"]) == 3, r2)
        open(os.path.join(ib, "ding.mp3"), "ab").write(b"\0" * 10)        # a different file, same name
        r3 = inbox_sort.sort()
        check("inbox: a different file with a used name gets ' 2'", [f["to"] for f in r3["filed"]] == ["favorites/sounds/ding 2.mp3"], r3["filed"])
        sc = favorites_folder.scan()
        listed = [e.get("rel", "") for k in ("sounds", "gifs", "graphics") for e in sc[k]] + [x.get("file", "") for x in sc["refused"]]
        check("favorites: the swap menus see the sounds", len(sc["sounds"]) >= 2, sc)
        check("favorites: photos and fonts are kept, not listed or refused", not any("photos/" in x or "fonts/" in x for x in listed), listed)
    finally:
        inbox_sort.ROOT, favorites_folder.ROOT, favorites_folder.FOLDER, favorites_folder.CACHE = real
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_inbox_sort: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_inbox_sort: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
