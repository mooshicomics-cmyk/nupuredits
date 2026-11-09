#!/usr/bin/env python3
"""Guard: her favorites folder (favorites/sounds, gifs, graphics) is read right, and never leaves her computer.

Every case runs in a throwaway folder (favorites_folder.FOLDER and CACHE pointed at a temp dir), with small media
made by ffmpeg, so her real favorites/ and _local/ are never touched.

What it holds:
  - scan() sorts by what a file IS, not which drawer it sits in: a short sound is a sound effect, a long one a song,
    a .gif a GIF (even dropped in sounds/, with a note saying so), a see-through .png / .mov / .svg a graphic
  - files it can't use are REFUSED with a plain reason, never skipped silently: a .jpg, an .mp4, a .mov with no
    see-through background, an empty file, a damaged file, an unknown type, a fake .svg; READMEs are not files
  - a GIF's render copy is a ProRes 4444 .mov WITH alpha in _local/favorites-cache/, made once and reused;
    replacing the GIF makes a fresh copy and the old one is cleared; her original is byte-for-byte untouched
  - a still preview is made for a .mov graphic (a browser can't play ProRes); a .gif previews as itself
  - git ignores everything in favorites/ but the READMEs
  - the ship bundle gets only the READMEs (make-ship.sh's rsync filter AND its scrub, run here on a fake tree),
    and check-ship.sh has the gate for it
  - an update never creates, overwrites or deletes her files there (apply-update.py, make-update.py), only the
    READMEs; keep_changes never lists her drops as engine changes

Run: python3 product/tests/test_favorites_folder.py
"""
import hashlib, importlib.util, os, re, shutil, subprocess, sys, tempfile, time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-600:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def sha(p):
    return hashlib.sha1(open(p, "rb").read()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pix_fmt(p):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=codec_name,pix_fmt", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()


def make_media(fav):
    S, G, R = (os.path.join(fav, d) for d in ("sounds", "gifs", "graphics"))
    import favorites_folder
    for d in (os.path.join(fav, x) for x in favorites_folder.DRAWERS):   # every drawer the engine ships, each with its README
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "README.md"), "w", encoding="utf-8").write("# drawer\n")
    open(os.path.join(fav, "README.md"), "w", encoding="utf-8").write("# favorites\n")
    ff("-f", "lavfi", "-i", "sine=frequency=880:duration=0.4", os.path.join(S, "my pop.mp3"))
    ff("-f", "lavfi", "-i", "sine=frequency=220:duration=20", "-c:a", "aac", os.path.join(S, "cozy song.m4a"))
    ff("-f", "lavfi", "-i", "sine=frequency=500:duration=0.5", os.path.join(S, "old-sound.aiff"))
    # a moving GIF with a see-through background
    ff("-f", "lavfi", "-i", "color=c=red@0.0:s=64x48:d=1:r=10,format=rgba,drawbox=x=t*40:y=10:w=12:h=12:c=yellow@1:t=fill",
       "-filter_complex", "[0:v]split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=alpha_threshold=128",
       os.path.join(G, "sparkle.gif"))
    shutil.copy(os.path.join(G, "sparkle.gif"), os.path.join(S, "oops-a-gif.gif"))       # wrong drawer
    ff("-f", "lavfi", "-i", "color=c=blue@0.0:s=40x40:d=0.1,format=rgba,drawbox=x=5:y=5:w=10:h=10:c=white@1:t=fill",
       "-frames:v", "1", os.path.join(R, "sticker.png"))
    ff("-f", "lavfi", "-i", "color=c=green@0.5:s=64x64:d=1:r=10,format=yuva444p10le",
       "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", os.path.join(R, "glow.mov"))
    ff("-f", "lavfi", "-i", "color=c=green:s=64x64:d=1:r=10", "-c:v", "libx264", "-pix_fmt", "yuv420p",
       os.path.join(R, "flat.mov"))
    ff("-f", "lavfi", "-i", "color=c=green:s=64x64:d=0.1", "-frames:v", "1", os.path.join(R, "photo.jpg"))
    shutil.copy(os.path.join(R, "flat.mov"), os.path.join(R, "clip.mp4"))
    open(os.path.join(R, "doodle.svg"), "w", encoding="utf-8").write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
    open(os.path.join(R, "fake.svg"), "w", encoding="utf-8").write("not a drawing")
    open(os.path.join(R, "notes.txt"), "w", encoding="utf-8").write("hello")
    open(os.path.join(S, "empty.mp3"), "wb").close()
    open(os.path.join(S, "broken.wav"), "wb").write(b"RIFF....garbage" * 20)
    open(os.path.join(G, ".DS_Store"), "wb").write(b"x")


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_favorites_folder: skipped (ffmpeg/ffprobe not installed)")
        return 0
    import favorites_folder as F
    tmp = tempfile.mkdtemp(prefix="fav-folder-")
    real = (F.FOLDER, F.CACHE)
    try:
        F.FOLDER = os.path.join(tmp, "favorites")
        F.CACHE = os.path.join(tmp, "_local", "favorites-cache")
        make_media(F.FOLDER)

        print("scan: sorts by what a file is")
        res = F.scan()
        by = {e["rel"]: e for k in ("sounds", "gifs", "graphics") for e in res[k]}
        refused = {r["file"]: r["reason"] for r in res["refused"]}
        check("a short sound is a sound effect", by.get("favorites/sounds/my pop.mp3", {}).get("use") == "sfx", by.keys())
        check("a long sound is a song for the bed", by.get("favorites/sounds/cozy song.m4a", {}).get("use") == "music")
        check("a sound's length is measured", abs((by.get("favorites/sounds/my pop.mp3") or {}).get("duration", 0) - 0.4) < 0.1)
        g = by.get("favorites/gifs/sparkle.gif") or {}
        check("a GIF is a GIF, moving", g.get("kind") == "gif" and g.get("animated") is True, g)
        w = by.get("favorites/sounds/oops-a-gif.gif") or {}
        check("a GIF in the sounds drawer is still a GIF, and says so",
              w.get("kind") == "gif" and "sounds/" in (w.get("note") or "") and w in res["gifs"], w)
        check("a see-through png is a graphic", (by.get("favorites/graphics/sticker.png") or {}).get("alpha") is True)
        check("a see-through .mov is a graphic", (by.get("favorites/graphics/glow.mov") or {}).get("kind") == "graphic")
        check("an svg is a graphic, rendered routes only",
              (by.get("favorites/graphics/doodle.svg") or {}).get("routes") == ["medium", "well-done"])
        check("ids are stable and name the file", g.get("id") == "folder:gifs/sparkle.gif", g.get("id"))
        check("every usable entry is a favorite", all(e["source"] == "favorite" for e in by.values()))
        check("READMEs and .DS_Store are not files to use",
              not any(k.endswith(("README.md", ".DS_Store")) for k in list(by) + list(refused)))

        print("refused, each with a plain reason")
        for rel, word in (("favorites/graphics/photo.jpg", ".png"), ("favorites/graphics/clip.mp4", "b-roll"),
                          ("favorites/graphics/flat.mov", "see-through"), ("favorites/sounds/empty.mp3", "empty"),
                          ("favorites/sounds/broken.wav", "won't open"), ("favorites/graphics/notes.txt", ".txt"),
                          ("favorites/graphics/fake.svg", "SVG")):
            check(f"{rel.split('/')[-1]} refused with a reason that says what to do", word in (refused.get(rel) or ""),
                  refused.get(rel))
        check("nothing usable is refused and nothing refused is listed", not (set(refused) & set(by)))

        print("GIF -> transparent ProRes copy, cached, original untouched")
        src = os.path.join(F.FOLDER, "gifs", "sparkle.gif")
        before, mt = sha(src), os.stat(src).st_mtime_ns
        out = F.render_copy("folder:gifs/sparkle.gif")
        check("the copy lives in _local/favorites-cache", out.startswith(F.CACHE + os.sep) and out.endswith(".mov"), out)
        check("it is ProRes with an alpha plane", pix_fmt(out) == "prores,yuva444p10le" or
              ("prores" in pix_fmt(out) and "yuva" in pix_fmt(out)), pix_fmt(out))
        cmt = os.stat(out).st_mtime_ns
        time.sleep(0.05)
        again = F.render_copy("folder:gifs/sparkle.gif")
        check("asked again, the cached copy comes back unchanged", again == out and os.stat(out).st_mtime_ns == cmt)
        check("her original GIF is byte-for-byte untouched", sha(src) == before and os.stat(src).st_mtime_ns == mt)
        check("scan now names the render copy", (F.entry("folder:gifs/sparkle.gif") or {}).get("render_file") == out)
        check("a png needs no copy: it is used as it is",
              F.render_copy("folder:graphics/sticker.png") == os.path.join(F.FOLDER, "graphics", "sticker.png"))
        time.sleep(0.02)
        ff("-f", "lavfi", "-i", "color=c=red:s=32x32:d=0.5:r=10", src)          # she replaces it
        fresh = F.render_copy("folder:gifs/sparkle.gif")
        check("a replaced GIF gets a fresh copy", fresh != out and os.path.isfile(fresh))
        F.scan()
        check("and the stale copy is cleared", not os.path.exists(out))
        try:
            F.render_copy("folder:gifs/nope.gif"); ok = False
        except ValueError as e:
            ok = "favorites folder" in str(e)
        check("an unknown favorite is refused in plain words", ok)
        try:
            F.render_copy(os.path.join(tmp, "elsewhere.gif")); ok = False
        except ValueError:
            ok = True
        check("only files inside her favorites folder get copies", ok)

        print("previews the page can show")
        p = F.preview_path("folder:graphics/glow.mov")
        check("a .mov graphic previews as a still png in the cache", p.endswith(".png") and p.startswith(F.CACHE), p)
        check("a gif previews as itself", F.preview_path("folder:sounds/oops-a-gif.gif").endswith("oops-a-gif.gif"))

        try:
            from PIL import Image
            frames = [Image.new("RGBA", (16, 16), (255, 0, 0, a)) for a in (0, 128, 255)]
            wp = os.path.join(F.FOLDER, "gifs", "moving.webp")
            frames[0].save(wp, save_all=True, append_images=frames[1:], duration=100, loop=0)
            sp = os.path.join(F.FOLDER, "graphics", "still.webp")
            frames[2].save(sp)
            res = F.scan()
            ids = {e["id"]: e for k in ("gifs", "graphics") for e in res[k]}
            check("a moving .webp is a GIF", (ids.get("folder:gifs/moving.webp") or {}).get("kind") == "gif",
                  res["refused"])
            check("a still .webp is a graphic", (ids.get("folder:graphics/still.webp") or {}).get("kind") == "graphic")
            if "folder:gifs/moving.webp" in ids:
                m = F.render_copy("folder:gifs/moving.webp")
                check("a moving .webp gets a ProRes copy too", "yuva" in pix_fmt(m), pix_fmt(m))
        except ImportError:
            print("  (Pillow not installed here: the .webp cases are skipped)")

        print("never leaves her computer")
        top = subprocess.run(["git", "-C", ROOT, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        is_repo = top.returncode == 0 and os.path.realpath(top.stdout.strip()) == os.path.realpath(ROOT)
        if not is_repo:
            print("  (not the engine's own git checkout, e.g. the built bundle: the .gitignore cases are skipped)")
        cases = (("favorites/sounds/x.mp3", True), ("favorites/gifs/y.gif", True), ("favorites/graphics/deep/z.png", True),
                 ("favorites/README.md", False), ("favorites/sounds/README.md", False),
                 ("favorites/graphics/README.md", False))
        for rel, ignored in (cases if is_repo else ()):
            r = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", rel], capture_output=True)
            if r.returncode not in (0, 1):
                print("  (not a git checkout here: the .gitignore cases are skipped)"); break
            check(f"git {'ignores' if ignored else 'tracks'} {rel}", (r.returncode == 0) == ignored)
        READMES = sorted(["favorites/README.md"] + [f"favorites/{d}/README.md" for d in F.DRAWERS])   # every drawer
        for rel in READMES:
            check(f"{rel} exists in the engine", os.path.isfile(os.path.join(ROOT, rel)))

        ship = open(os.path.join(ROOT, "make-ship.sh"), encoding="utf-8").read() if os.path.isfile(
            os.path.join(ROOT, "make-ship.sh")) else None
        if ship is None:
            print("  (make-ship.sh is seller-side and not in this copy: the ship cases are skipped)")
        else:
            rules = re.findall(r"--(include|exclude)='(/favorites[^']*)'", ship)
            check("make-ship.sh filters favorites/ down to its READMEs", len(rules) == 4, rules)
            fav = (re.search(r'FAV_DRAWERS="([^"]*)"', ship) or [None, ""])[1].split()
            check("make-ship.sh ships every drawer the engine reads (a fresh copy and an update both get them all)",
                  sorted(fav) == sorted(F.DRAWERS), fav)
            src_tree, dst = os.path.join(tmp, "eng"), os.path.join(tmp, "stage")
            shutil.copytree(F.FOLDER, os.path.join(src_tree, "favorites"))
            os.makedirs(os.path.join(src_tree, "favorites", "sounds", "pack"))
            open(os.path.join(src_tree, "favorites", "sounds", "pack", "README.md"), "w", encoding="utf-8").write("x")
            open(os.path.join(src_tree, "favorites", "loose.mp3"), "w", encoding="utf-8").write("x")
            if shutil.which("rsync"):
                os.makedirs(dst)
                subprocess.run(["rsync", "-a", *[f"--{k}={v}" for k, v in rules], src_tree + "/", dst + "/"], check=True)
                got = sorted(os.path.relpath(os.path.join(dp, f), dst).replace(os.sep, "/")
                             for dp, _d, fs in os.walk(dst) for f in fs)
                check("the bundle copy holds only the READMEs, one per drawer", got == READMES, got)
                shutil.rmtree(dst)
            m = re.search(r"(# --- 3b2\..*?)\n\n# --- 3c", ship, re.S)
            check("make-ship.sh scrubs favorites/ after copying", bool(m))
            if m:
                shutil.copytree(src_tree, dst)
                subprocess.run(["bash", "-c", m.group(1)], env=dict(os.environ, STAGE=dst), check=True)
                got = sorted(os.path.relpath(os.path.join(dp, f), dst).replace(os.sep, "/")
                             for dp, _d, fs in os.walk(dst) for f in fs)
                check("the scrub leaves only the READMEs, one per drawer, at any depth", got == READMES, got)
            cs = open(os.path.join(ROOT, "check-ship.sh"), encoding="utf-8").read()
            check("check-ship.sh gates it (section 35)", "35. the favorites folder ships empty" in cs)
            check("check-ship.sh requires every drawer's README", all(r in cs for r in READMES))

        print("updates leave her files alone")
        au = load(os.path.join(ROOT, "scripts", "apply-update.py"), "apply_update_t")
        mu_path = os.path.join(ROOT, "make-update.py")
        mods = [("apply-update", au)] + ([("make-update", load(mu_path, "make_update_t"))] if os.path.isfile(mu_path) else [])
        for nm, mod in mods:
            check(f"{nm}: her sound is protected", mod.is_protected("favorites/sounds/my pop.mp3"))
            check(f"{nm}: her nested file is protected", mod.is_protected("favorites/gifs/pack/README.md"))
            check(f"{nm}: the folder itself is protected", mod.is_protected("favorites"))
            check(f"{nm}: the READMEs can be refreshed", not mod.is_protected("favorites/README.md")
                  and not mod.is_protected("favorites/graphics/README.md"))
        kc = load(os.path.join(ROOT, "product", "keep_changes.py"), "keep_changes_t")
        check("keep_changes never reports her drops as engine changes", kc._skip_dir("favorites"))
        check("15 s is the sound-effect line, same as favorites.py",
              F.LONGEST_SFX_S == load(os.path.join(ROOT, "product", "favorites.py"), "favorites_t").LONGEST_SFX_S)
    finally:
        F.FOLDER, F.CACHE = real
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("all good: her favorites folder is read right, its copies are cached, and nothing in it ever leaves her computer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
