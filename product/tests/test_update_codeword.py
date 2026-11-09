#!/usr/bin/env python3
"""Guard: an early-access codeword opens a hidden feed, and its testers rejoin the regular updates on their own.

The creator puts a coming version on <update_url>/early/<32 hex>/ (make-update.py --codeword WORD); a tester
types `/update WORD`. Pinned here, against the real scripts/apply-update.py in a throwaway engine folder (no
network: urlopen serves a dict per URL, and the signature check is a stand-in that passes feeds marked signed):
  1. the codeword's folder comes from the word alone, ignores case and spaces, and matches make-update.py's
     (a fixed answer, so the check also runs in a buyer's engine, which has no make-update.py);
  2. a right codeword installs the early version from the early folder, and is remembered;
  3. a wrong (or closed) codeword is never a dead end: the regular update runs, and nothing is saved;
  4. --check with a codeword saves nothing;
  5. a remembered codeword keeps a plain update on the early feed while it is ahead;
  6. once the regular feed passes the early one, the regular release is installed (the testers move along);
  7. a remembered codeword whose feed is gone is no fault: the regular feed answers alone;
  8. an early feed that fails the signature check installs nothing;
  9. a tester ahead of the regular feed is told she is up to date, never pointed backwards;
 10. --code off forgets it.

Run: python3 product/tests/test_update_codeword.py   (Windows: python)
"""
import contextlib, importlib.util, io, json, os, shutil, sys, tempfile, types, urllib.error
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BASE = "https://feed.invalid/v2"
KNOWN_SUNFLOWER = "bd39bf201954e2e998af37b7982e0fe4"   # sha256("reels-editing-engine/early-access/sunflower")[:32]
fails = []

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-600:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def engine(tmp, version):
    eng = Path(tmp) / "engine"
    (eng / "scripts").mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "scripts", "apply-update.py"), eng / "scripts" / "apply-update.py")
    (eng / "product.json").write_text(json.dumps(
        {"engine": "ai-edit-engine", "version": version, "update_url": BASE}), encoding="utf-8")
    mod = load(eng / "scripts" / "apply-update.py", f"apply_update_{os.path.basename(tmp)}")
    mod.FEED_RETRY_WAIT = 0
    mod._signature_module = lambda: types.SimpleNamespace(
        check_feed=lambda f: "" if f.get("signed") else "it carries no signature", clean_summary=lambda s, n: s)
    return eng, mod


def feed(version, signed=True):
    return {"engine": "ai-edit-engine", "version": version, "file": f"ai-edit-engine-update-v{version}.zip",
            "sha256": "0" * 64, "signed": signed}


class Site:
    """Stand-in urlopen: a dict per feed URL; anything else is a not-found. Zip downloads are recorded."""
    def __init__(self, feeds):
        self.feeds, self.downloads = feeds, []

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url in self.feeds:
            return contextlib.nullcontext(io.BytesIO(json.dumps(self.feeds[url]).encode("utf-8")))
        if url.endswith(".zip"):
            self.downloads.append(url)
            return contextlib.nullcontext(io.BytesIO(b"zip"))
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


def run(mod, site, code=None, dry_run=False):
    """(exit code or None, everything said, the zip URLs downloaded) for one fetch()."""
    mod.urllib.request.urlopen = site
    mod.sha256 = lambda p: "0" * 64
    mod.apply = lambda pkg, dry_run=False, verified=False: None
    out, rc = io.StringIO(), None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            mod.fetch(dry_run=dry_run, code=code)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), site.downloads


def main():
    print("early-access codeword: a hidden feed, and the testers rejoin everyone\n")

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.20")
        ch = mod.code_channel("sunflower")
        check("the codeword's folder is the one make-update.py publishes to (a fixed answer: buyers' engines "
              "and the seller's build must never drift apart)", ch == "early/" + KNOWN_SUNFLOWER, ch)
        check("case and spaces don't matter", mod.code_channel("  Sun Flower ") == ch)
        check("a different word opens a different folder", mod.code_channel("daisy") != ch)
        seller = os.path.join(ROOT, "make-update.py")   # the seller's build tool; not in a buyer's engine
        if os.path.exists(seller):
            mu = load(seller, "make_update_for_codeword_test")
            check("make-update.py publishes to the same folder the engine looks in", mu.code_channel("sunflower") == ch)
        check("the word itself is nowhere in the folder name", "sunflower" not in ch)

    early_url = f"{BASE}/{mod.code_channel('sunflower')}"

    # what a buyer really types around the word: a version number never picks a version, and filler is dropped
    for typed in ("v2.2.26 sunflower", "/update v2.2.26 Sunflower", "sunflower update", "update me to the sunflower version"):
        with tempfile.TemporaryDirectory() as tmp:
            eng, mod = engine(tmp, "2.2.20")
            site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.21")})
            rc, said, got = run(mod, site, code=typed)
            check(f"{typed!r} opens the codeword's feed and installs its newest",
                  rc is None and got == [f"{early_url}/ai-edit-engine-update-v2.2.21.zip"]
                  and mod._saved_channel() == mod.code_channel("sunflower"), f"rc={rc} got={got} {said}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.20")
        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.21")})
        rc, said, got = run(mod, site, code="v2.2.26 daisy")
        check("a wrong word around a version number gets the regular update and saves nothing",
              rc is None and not got and not mod._saved_channel() and "no codeword needed" in said, f"rc={rc} {said}")

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.20")
        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.21")})
        rc, said, got = run(mod, site, code="Sunflower")
        check("a right codeword downloads the early version from the early folder",
              rc is None and got == [f"{early_url}/ai-edit-engine-update-v2.2.21.zip"], f"rc={rc} got={got} {said}")
        check("it says the codeword opened the early version", "codeword opened v2.2.21" in said, said)
        check("the codeword is remembered (as its folder, not the word)",
              mod._saved_channel() == mod.code_channel("sunflower")
              and "unflower" not in (eng / "_local" / "update-code.json").read_text(encoding="utf-8"))

        # later, a plain update with the codeword remembered: still on the early feed while it is ahead
        (eng / "product.json").write_text(json.dumps(
            {"engine": "ai-edit-engine", "version": "2.2.20", "update_url": BASE}), encoding="utf-8")
        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.22")})
        rc, said, got = run(mod, site)
        check("a remembered codeword keeps a plain update on the early feed",
              got == [f"{early_url}/ai-edit-engine-update-v2.2.22.zip"], f"{got} {said}")

        # the release for everyone passes the test version: the tester moves to it
        (eng / "product.json").write_text(json.dumps(
            {"engine": "ai-edit-engine", "version": "2.2.22", "update_url": BASE}), encoding="utf-8")
        site = Site({f"{BASE}/latest.json": feed("2.2.23"), f"{early_url}/latest.json": feed("2.2.22")})
        rc, said, got = run(mod, site)
        check("once the regular release is newer, the tester gets the regular release",
              got == [f"{BASE}/ai-edit-engine-update-v2.2.23.zip"], f"{got} {said}")

        # a codeword typed when she is already past the test version: the check says it is not saved yet,
        # and the real run still remembers it (the codeword is also a switch, not only a feed; buyer report 10/17)
        mod.forget_code()
        (eng / "product.json").write_text(json.dumps(
            {"engine": "ai-edit-engine", "version": "2.2.23", "update_url": BASE}), encoding="utf-8")
        site = Site({f"{BASE}/latest.json": feed("2.2.23"), f"{early_url}/latest.json": feed("2.2.22")})
        rc, said, got = run(mod, site, code="sunflower", dry_run=True)
        check("an up-to-date check with a codeword says the real run is still needed to save it",
              not mod._saved_channel() and "not saved yet" in said, said)
        rc, said, got = run(mod, site, code="sunflower")
        check("the real run remembers the codeword even with nothing new to install",
              not got and mod._saved_channel() == mod.code_channel("sunflower") and "is saved" in said,
              f"{got} {said}")

        # the test is over (early feed dropped): no fault, the regular feed answers
        site = Site({f"{BASE}/latest.json": feed("2.2.24")})
        rc, said, got = run(mod, site)
        check("a remembered codeword whose feed is gone is no fault",
              rc is None and got == [f"{BASE}/ai-edit-engine-update-v2.2.24.zip"], f"rc={rc} {got} {said}")

        # ahead of the regular feed: up to date, never pointed backwards
        (eng / "product.json").write_text(json.dumps(
            {"engine": "ai-edit-engine", "version": "2.2.22", "update_url": BASE}), encoding="utf-8")
        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.22")})
        rc, said, got = run(mod, site)
        check("a tester ahead of the regular feed is told she is up to date",
              rc is None and not got and "already up to date" in said and "ahead of" in said, f"{got} {said}")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mod.forget_code()
        check("--code off forgets it", not mod._saved_channel() and "forgotten" in out.getvalue(), out.getvalue())

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.20")
        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.21")})
        rc, said, got = run(mod, site, code="sunflowr")
        check("a wrong codeword is never a dead end", rc is None, f"rc={rc} {said}")
        check("a wrong codeword downloads nothing early and is not saved", not got and not mod._saved_channel(), got)
        check("it says no codeword is needed", "no codeword needed" in said, said)

    # the closed christmas test: an old word whose feed is gone installs the regular release (buyer reports 2026-10-19)
    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.20")
        rc, said, got = run(mod, Site({f"{BASE}/latest.json": feed("2.2.23")}), code="christmas")
        check("a word whose feed is gone installs the regular update",
              rc is None and got == [f"{BASE}/ai-edit-engine-update-v2.2.23.zip"] and not mod._saved_channel(),
              f"rc={rc} got={got} {said}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp, "2.2.20")
        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.21")})

        rc, said, got = run(mod, site, code="sunflower", dry_run=True)
        check("--check with a codeword downloads and saves nothing",
              not got and not mod._saved_channel() and "v2.2.21" in said, f"{got} {said}")

        site = Site({f"{BASE}/latest.json": feed("2.2.20"), f"{early_url}/latest.json": feed("2.2.21", signed=False)})
        rc, said, got = run(mod, site, code="sunflower")
        check("an early feed that fails the signature check installs nothing",
              rc == 1 and not got and "could not be verified" in said, f"rc={rc} {got} {said}")

    print()
    if fails:
        print(f"FAILED: {len(fails)} check(s): {', '.join(fails)}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
