#!/usr/bin/env python3
"""Re-reading her favorites never loses what she already has.

Three ways it did:
  * a re-read of her sounds shelf rebuilt the saved state from scratch and dropped the "style" she had
    folded in from a reel she loves (`learn-style`), so her CapCut builds quietly stopped using it;
  * `forget` (drop the SHELF) took that style with it too, although `forget-style` is how she drops a style;
  * a re-read while CapCut did not have a shelf sound on this computer (its cache cleared, or not downloaded
    yet) DELETED the copy saved last time, which is the whole reason sounds are copied, and then printed
    both "doesn't have any sound effects in it yet" and a list of the sounds it has.

Runs against a fake CapCut drafts folder and a fake engine folder; nothing real is read or written.

Run: python3 product/tests/test_favorites_keep.py
"""
import contextlib, importlib.util, io, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
STYLE = {"draft": "my best reel", "learned_at": "2026-09-01T10:00:00",
         "animations": {"hook.in": {"name": "Pop Up", "api": "Pop_Up"}}, "density": "normal"}
fails = []


def check(name, cond, detail=""):
    if not cond:
        fails.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def text(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


class Shelf:
    """A fresh favorites module pointed at a fake CapCut and a fake engine folder."""

    def __init__(self, tmp):
        spec = importlib.util.spec_from_file_location("favorites_keep", os.path.join(PRODUCT, "favorites.py"))
        self.fav = fav = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fav)
        fav.ds.CAP = os.path.join(tmp, "drafts")
        fav.ROOT = os.path.join(tmp, "engine")
        fav.LOCAL = os.path.join(fav.ROOT, "_local")
        fav.SOUNDS = os.path.join(fav.LOCAL, "sounds")
        fav.STATE = os.path.join(fav.LOCAL, "favorites.json")
        self.cache = os.path.join(tmp, "capcut-cache")
        os.makedirs(self.cache)

    def project(self, titles, name="my sound palette"):
        """Her shelf in CapCut: one audio material per title, each cached as capcut-cache/<title>.mp3."""
        d = os.path.join(self.fav.ds.CAP, name)
        os.makedirs(d, exist_ok=True)
        mats, segs = [], []
        for i, t in enumerate(titles):
            p = os.path.join(self.cache, f"{t}.mp3")
            if not os.path.exists(p):
                text(p, f"ID3 {t}")
            mats.append({"id": f"m{i}", "name": t, "type": "sound", "path": p, "duration": 400000})
            segs.append({"material_id": f"m{i}", "target_timerange": {"start": i * 1_000_000}})
        with open(os.path.join(d, self.fav.ds.draft_json_name(d)), "w", encoding="utf-8") as fh:
            json.dump({"materials": {"audios": mats}, "tracks": [{"type": "audio", "segments": segs}]}, fh)

    def clear_cache(self, *titles):
        for t in titles:
            os.remove(os.path.join(self.cache, f"{t}.mp3"))

    def learn(self, rules=()):
        return self.fav.learn("my sound palette", list(rules))

    def cli(self, *args):
        buf = io.StringIO()
        argv = sys.argv
        sys.argv = ["favorites.py", *args]
        try:
            with contextlib.redirect_stdout(buf):
                code = self.fav.main()
        finally:
            sys.argv = argv
        return code, buf.getvalue()

    def names(self):
        return [s["name"] for s in self.fav.load().get("sounds", [])]

    def on_disk(self):
        return sorted(os.listdir(self.fav.SOUNDS)) if os.path.isdir(self.fav.SOUNDS) else []


def main():
    tmp = tempfile.mkdtemp()
    try:
        # ---- a re-read keeps the style she folded in ----
        s = Shelf(os.path.join(tmp, "a"))
        s.project(["Soft pop", "Keyboard clack"])
        s.learn(["vary these"])
        s.fav.save({**s.fav.load(), "style": STYLE})
        msg, code = s.learn()
        check("a re-read of the shelf keeps the style she folded in", s.fav.load().get("style") == STYLE,
              json.dumps(s.fav.load())[:300])
        check("a re-read keeps her rules and sounds", s.fav.load().get("rules") == ["vary these"]
              and s.names() == ["soft-pop", "keyboard-clack"], json.dumps(s.fav.load())[:300])

        # ---- CapCut no longer has the sounds on this computer: the saved copies stay ----
        before = {f: read(os.path.join(s.fav.SOUNDS, f)) for f in s.on_disk()}
        s.clear_cache("Soft pop", "Keyboard clack")
        msg, code = s.learn()
        check("a re-read with CapCut's cache cleared keeps every saved copy",
              s.names() == ["soft-pop", "keyboard-clack"]
              and {f: read(os.path.join(s.fav.SOUNDS, f)) for f in s.on_disk()} == before,
              f"state {s.names()}, on disk {s.on_disk()}")
        check("it never says a shelf with sounds on it has none", "doesn't have any sound effects" not in msg, msg)
        check("it says the saved copies are what it is using", "kept the copies I saved last time" in msg, msg)

        # ---- one sound comes off the shelf while another is missing from the cache ----
        s.project(["Soft pop"])                  # Keyboard clack taken off the shelf in CapCut
        s.clear_cache("Soft pop")
        s.learn()
        check("a sound she took off the shelf still leaves the library",
              s.names() == ["soft-pop"] and s.on_disk() == ["soft-pop.mp3"], f"{s.names()} {s.on_disk()}")

        # ---- a new sound never lands on a kept copy with the same name ----
        s.project(["Soft pop", "Soft pop!"])
        s.clear_cache("Soft pop")
        kept_body = read(os.path.join(s.fav.SOUNDS, "soft-pop.mp3"))
        s.learn()
        check("a new copy never overwrites a kept one",
              kept_body is not None and read(os.path.join(s.fav.SOUNDS, "soft-pop.mp3")) == kept_body
              and s.names() == ["soft-pop", "soft-pop-2"], f"{s.names()} {s.on_disk()}")

        # ---- the very first read, while CapCut has none of them here ----
        s = Shelf(os.path.join(tmp, "b"))
        s.project(["Soft pop", "Keyboard clack"])
        s.clear_cache("Soft pop", "Keyboard clack")
        msg, code = s.learn()
        check("a first read with nothing in CapCut's cache says the shelf HAS sounds, and why none were copied",
              "has 2 sounds in it" in msg and "doesn't have any sound effects" not in msg
              and msg.count("Soft pop") == 1, msg)

        # ---- forget drops the shelf and keeps the style ----
        s = Shelf(os.path.join(tmp, "c"))
        s.project(["Soft pop"])
        s.learn(["no whooshes"])
        s.fav.save({**s.fav.load(), "style": STYLE})
        code, out = s.cli("forget")
        st = s.fav.load()
        check("forget drops the shelf's sounds and rules", not st.get("sounds") and not st.get("rules")
              and not s.on_disk(), json.dumps(st)[:300])
        check("forget keeps the style she folded in, and says so", st.get("style") == STYLE
              and "forget that style" in out, out)
        code, out = s.cli("show")
        check("show reads plainly with a style and no shelf", "None" not in out and "Pop Up" in out, out)
        code, out = s.cli("forget-style")
        code, out = s.cli("forget")
        check("forget with no style left removes the saved state, as before", not os.path.exists(s.fav.STATE))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    if fails:
        print(f"favorites keep: FAILED {len(fails)}: {'; '.join(fails)}")
        sys.exit(1)
    print("favorites keep: re-reading or forgetting the shelf never loses her saved sounds or her style")
