#!/usr/bin/env python3
"""Guard: when Python can't get through to the update server, the updater asks again through curl.

A buyer on a Mac said "update me" twice, five days apart. The session-start check (curl) saw the newer version both
times, but the updater (Python) got "not found" the first time and "couldn't reach the update server" the second,
so she stayed on an old version (buyer report, 2026-10-19). Python's requests follow the Mac's proxy settings and a
security or VPN app's filter; curl does not. Whatever curl brings back is still checked against the publisher's
signature and the feed's checksum, so the fallback can't let anything unsigned in.

Pinned here, against the real scripts/apply-update.py in a throwaway engine folder (no network: Python's urlopen is
a stand-in that always fails, and curl reads local file:// addresses):
  1. the feed is read through curl when Python fails, and the feed is still asked a second time if curl fails too;
  2. the update file is downloaded through curl when Python fails;
  3. with no curl on the computer, Python's own error comes back unchanged;
  4. a curl that fails leaves no half-written file behind;
  5. when Python gets through, curl is never run.

Run: python3 product/tests/test_update_curl_fallback.py   (Windows: python)
"""
import importlib.util, io, json, os, shutil, sys, tempfile, urllib.error
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []

for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print every character
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-600:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def engine(tmp):
    """A throwaway engine folder with the real updater, loaded as a module."""
    eng = Path(tmp) / "engine"
    (eng / "scripts").mkdir(parents=True)
    for f in ("apply-update.py", "update_signature.py"):
        shutil.copy(os.path.join(ROOT, "scripts", f), eng / "scripts" / f)
    (eng / "product.json").write_text(json.dumps(
        {"engine": "ai-edit-engine", "version": "2.2.2", "update_url": "https://feed.invalid/v2"}), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"apply_update_{os.path.basename(tmp)}", eng / "scripts" / "apply-update.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.FEED_RETRY_WAIT = 0
    return eng, mod


class Blocked:
    """Stand-in urlopen that never gets through, the way a proxy or filter answers Python on her Mac."""
    def __init__(self):
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        raise urllib.error.HTTPError(getattr(req, "full_url", str(req)), 404, "Not Found", {}, None)


class Works:
    def __call__(self, req, timeout=None):
        return io.BytesIO(b'{"version": "2.3.0"}')


def main():
    print("updater: curl when Python can't get through\n")
    if not shutil.which("curl"):
        print("  skip  no curl on this computer (macOS and Windows 10+ always have one)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        eng, mod = engine(tmp)
        feed = {"engine": "ai-edit-engine", "version": "2.3.0", "file": "ai-edit-engine-update-v2.3.0.zip"}
        feed_file = Path(tmp) / "latest.json"
        feed_file.write_text(json.dumps(feed), encoding="utf-8")
        blocked = Blocked()
        mod.urllib.request.urlopen = blocked
        latest, err = mod._read_feed(feed_file.as_uri())
        check("the feed is read through curl when Python is blocked", err is None and latest == feed, err)
        check("Python was tried first", blocked.calls == 1, f"calls={blocked.calls}")

        blocked = Blocked()
        mod.urllib.request.urlopen = blocked
        latest, err = mod._read_feed((Path(tmp) / "missing.json").as_uri())
        check("when curl can't get it either, the error is Python's own", isinstance(err, urllib.error.HTTPError), err)
        check("and the feed is still asked a second time", blocked.calls == 2, f"calls={blocked.calls}")

        payload = os.urandom(300_000)
        src = Path(tmp) / "pkg.zip"
        src.write_bytes(payload)
        dest = eng / "_updates" / "pkg.zip"
        dest.parent.mkdir()
        mod.urllib.request.urlopen = Blocked()
        mod._http_get(src.as_uri(), 60, dest=dest)
        check("the update file is downloaded through curl when Python is blocked",
              dest.exists() and dest.read_bytes() == payload)

        gone = eng / "_updates" / "gone.zip"
        raised = None
        try:
            mod._http_get((Path(tmp) / "nope.zip").as_uri(), 60, dest=gone)
        except urllib.error.HTTPError as e:
            raised = e
        check("a failed download raises Python's error", raised is not None)
        check("and leaves no half-written file", not gone.exists())

        real_which = mod.shutil.which
        mod.shutil.which = lambda name, *a, **k: None if name == "curl" else real_which(name, *a, **k)
        raised = None
        try:
            mod._http_get(feed_file.as_uri(), 20)
        except urllib.error.HTTPError as e:
            raised = e
        mod.shutil.which = real_which
        check("with no curl, Python's own error comes back unchanged", raised is not None and raised.code == 404, raised)

        ran = []
        mod._curl_get = lambda *a, **k: ran.append(a)
        mod.urllib.request.urlopen = Works()
        body = mod._http_get("https://feed.invalid/v2/latest.json", 20)
        check("when Python gets through, curl is never run", body == b'{"version": "2.3.0"}' and not ran, ran)

    print()
    if fails:
        print(f"FAILED: {len(fails)} check(s): {', '.join(fails)}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
