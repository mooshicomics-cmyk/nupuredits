#!/usr/bin/env python3
"""make-update.py (seller side): an update removes EVERY file the engine has retired, and carries originals
only from 2.0.0 on, each one held to the ship gate's blocklist.

1. Retired files. The delete list used to compare this release with ONE snapshot (the first release, by
   default), so a file added in a later 1.0.x and retired after that was never removed from any buyer's
   machine (242 of them by 1.0.94, the retired sound pack among them). Now it is every path any earlier
   release shipped, minus what ships now, minus the buyer's protected paths; and the table of every version
   the engine shipped of each (so her own file at such a path stays) still covers them all.
2. The originals archive (_updates/history/engine-originals.tar.xz, read by product/keep_changes.py) carries
   originals and an index ONLY from versions >= 2.0.0 (the lineage line). A release below 2.0.0 carries an
   empty file there, which keep_changes reads as "this update did not carry the originals" (an archive with
   no versions in it would instead call every file she has a change of hers).
3. Every original it would carry goes through the blocklist half of dev-tools/prose-guard.py, with the ship
   gate's own exemptions (vendored upstream skills, licence text), and one hit fails the build by name.

Runs make-update.py for real, in throwaway seller folders built from synthetic snapshots. make-update.py and
dev-tools/ never ship, so in a buyer's copy of the engine there is nothing to check and this says so.

Run: python3 product/tests/test_update_retired_files.py   (Windows: python)
"""
import base64, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENV = {**os.environ, "PYTHONUTF8": "1", "REELS_ENGINE_SKIP_BROWSER_ENSURE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
NEEDED = ["make-update.py", "product/keep_changes.py", "dev-tools/prose-guard.py", "dev-tools/prose-blocklist.txt",
          "dev-tools/update-signing/signing.py", "scripts/update_signature.py"]
# make-update.py signs every release. These sandboxes sign with a throwaway key (ENGINE_UPDATE_SIGNING_KEY), and
# each sandbox's copy of update_signature.py pins its public half; the publisher's real key is never touched.
TEST_SEED = hashlib.sha256(b"retired-files test key, never a real one").digest()
STORE = "_updates/history/engine-originals.tar.xz"
# A phrase the blocklist stops, assembled here so this file never carries it (the ship gate scans tests too).
HIT = "this paragraph was " + "crib" + "bed from somewhere else"
fails = []

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-700:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def sha(body):
    return hashlib.sha256(body if isinstance(body, bytes) else body.encode("utf-8")).hexdigest()


def seller(tmp, name, versions, zips=(), vendored=()):
    """A seller folder: make-update.py and what it reads. `versions` is {version: {path: body}}, oldest to newest;
    the newest is this release (its snapshot, its built package in dist/, its product.json). `zips` names the
    versions whose buyer zip sits in releases/history."""
    root = os.path.join(tmp, name)
    for rel in NEEDED:
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(root, rel))
    us_path = os.path.join(root, "scripts", "update_signature.py")
    with open(us_path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"PUBLIC_KEYS = \(.*?\n\)", f'PUBLIC_KEYS = (\n    "{verifier().public_from_seed(TEST_SEED).hex()}",\n)',
                  text, count=1, flags=re.S)
    write(us_path, text)
    current = list(versions)[-1]
    site = "https://updates.example.test"
    two = int(current.split(".")[0]) >= 2
    # a 2.x engine reads the private feed (<site>/u/<32 hex>/v2); every drop also carries the course guide
    write(os.path.join(root, "product.json"), json.dumps({"engine": "ai-edit-engine", "version": current,
                                                          "update_url": site + ("/u/" + "0" * 32 + "/v2" if two else ""),
                                                          "course_guide_url": site + "/cg/" + "1" * 32 + "/guide.json"}))
    write(os.path.join(root, "releases", "course-guide", "the-reels-editing-engine.json"), '{"schema": 1}')
    if two:                        # the site root keeps the last v1 feed, frozen (make-update puts v2 beside it)
        v1zip = b"the last v1 update"
        write(os.path.join(root, "releases", "feed-v1", "ai-edit-engine-update-v1.0.94.zip"), v1zip)
        write(os.path.join(root, "releases", "feed-v1", "latest.json"), json.dumps(
            {"engine": "ai-edit-engine", "version": "1.0.94", "file": "ai-edit-engine-update-v1.0.94.zip",
             "sha256": hashlib.sha256(v1zip).hexdigest()}))
    write(os.path.join(root, "skills-lock.json"), json.dumps({"version": 1, "skills": {n: {} for n in vendored}}))
    for v, files in versions.items():
        write(os.path.join(root, ".ship-state", f"manifest-v{v}.json"),
              json.dumps({"version": v, "files": {rel: sha(body) for rel, body in files.items()}}))
    for rel, body in versions[current].items():
        write(os.path.join(root, "dist", "ai-edit-engine", rel), body)
    for v in zips:
        zp = os.path.join(root, "releases", "history", f"Reels-Editing-Engine-v{v}-20260101-0000-abc1234.zip")
        os.makedirs(os.path.dirname(zp), exist_ok=True)
        with zipfile.ZipFile(zp, "w") as zf:
            for rel, body in versions[v].items():
                zf.writestr(f"Reels-Editing-Engine/{rel}", body)
    return root


def verifier(root=ROOT):
    spec = importlib.util.spec_from_file_location("update_signature", os.path.join(root, "scripts", "update_signature.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build(root):
    r = subprocess.run([sys.executable, "make-update.py", "test release", "--change", "a change"], cwd=root,
                       capture_output=True, text=True, env=ENV, encoding="utf-8", errors="replace")
    with open(os.path.join(root, "product.json"), encoding="utf-8") as fh:
        v = json.load(fh)["version"]
    pkg = os.path.join(root, "dist", "updates", f"ai-edit-engine-update-v{v}")
    man = None
    if r.returncode == 0 and os.path.exists(os.path.join(pkg, "update.json")):
        with open(os.path.join(pkg, "update.json"), encoding="utf-8") as fh:
            man = json.load(fh)
    return r.returncode, r.stdout + r.stderr, man, pkg


def originals(path):
    sys.path.insert(0, os.path.join(ROOT, "product"))
    try:
        import keep_changes
    finally:
        sys.path.pop(0)
    return keep_changes.Originals(path)


def main():
    missing = [rel for rel in NEEDED if not os.path.exists(os.path.join(ROOT, rel))]
    if missing:
        print(f"make-update.py and dev-tools/ are seller-side and do not ship ({', '.join(missing)} not here): "
              "nothing to check in this copy of the engine.")
        return 0
    print("an update removes every retired file, and carries originals only from 2.0.0 on\n")
    with tempfile.TemporaryDirectory() as tmp:
        key = os.path.join(tmp, "test-signing.key")
        der = bytes.fromhex("302e020100300506032b657004220420") + TEST_SEED
        write(key, "-----BEGIN " + "PRIVATE KEY-----\n" + base64.b64encode(der).decode("ascii") + "\n-----END PRIVATE KEY-----\n")
        ENV["ENGINE_UPDATE_SIGNING_KEY"] = key
        print("1. retired files: every one any earlier release shipped")
        sound = "product/creative-vault/sfx/pack/click.mp3"
        v100 = {"a.py": "a = 0\n", "b.py": "b = 0\n", "old/tool.py": "tool = 0\n", "CHANGELOG.md": "# c 1.0.0\n"}
        v101 = dict(v100, **{sound: b"ID3 an engine sound", "tmp/helper.py": "helper = 1\n",
                             "presets/caption-corrections.json": "{}\n"})
        v102 = dict(v101, **{"tmp/helper.py": "helper = 2\n"})
        del v102[sound], v102["old/tool.py"], v102["presets/caption-corrections.json"]
        v103 = dict(v102, **{"a.py": "a = 3\n", "CHANGELOG.md": "# c 1.0.3\n"})
        del v103["tmp/helper.py"]
        s = seller(tmp, "s1", {"1.0.0": v100, "1.0.1": v101, "1.0.2": v102, "1.0.3": v103})
        rc, out, man, pkg = build(s)
        check("the package builds", rc == 0 and man is not None, out)
        man = man or {}
        check("it removes the file added after the first release and retired later (the old list missed it)",
              sound in man.get("deletes", []), man.get("deletes"))
        check("and one added later, changed, then retired", "tmp/helper.py" in man.get("deletes", []), man.get("deletes"))
        check("and, as before, one the first release shipped", "old/tool.py" in man.get("deletes", []))
        check("never a protected path of hers, whichever release shipped it",
              "presets/caption-corrections.json" not in man.get("deletes", []), man.get("deletes"))
        check("nothing that still ships", not set(man.get("deletes", [])) & set(v103), man.get("deletes"))
        hashes = man.get("delete_hashes", {})
        check("every version the engine shipped of each is listed, so her own file at that path stays",
              hashes.get("tmp/helper.py") == sorted([sha("helper = 1\n"), sha("helper = 2\n")])
              and hashes.get(sound) == [sha(b"ID3 an engine sound")], hashes)
        table = os.path.join(pkg, "files", "product", "templates", "update-deletes.json")
        with open(table, encoding="utf-8") if os.path.exists(table) else open(os.devnull, encoding="utf-8") as fh:
            tab = (json.loads(fh.read() or "{}")).get("files", {})
        check("post-update's copy of that table has them too", tab == hashes, tab)
        check("the summary says how many retired files it removes, and how many came after v1.0.0",
              "removed:       3 file(s), 2 of them added after v1.0.0 and retired since" in out, out)

        print("\n2. a release below 2.0.0 carries no originals")
        entry = [f for f in man.get("files", []) if f.get("path") == STORE]
        store = os.path.join(pkg, "files", STORE)
        check("the originals file is there, and empty", os.path.exists(store) and os.path.getsize(store) == 0
              and entry and entry[0].get("sha256") == sha(b""), entry)
        check("keep_changes reads it as 'this update did not carry the originals'",
              os.path.exists(store) and not originals(store).ok)
        check("the summary says so", "originals: none" in out, out)
        buyer = os.path.join(tmp, "buyer")
        for rel in ("scripts/apply-update.py", "scripts/post-update.py", "product/keep_changes.py"):
            os.makedirs(os.path.dirname(os.path.join(buyer, rel)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), os.path.join(buyer, rel))
        shutil.copy2(os.path.join(s, "scripts", "update_signature.py"), os.path.join(buyer, "scripts"))  # pins the test key
        for rel, body in v100.items():
            write(os.path.join(buyer, rel), body)
        write(os.path.join(buyer, "product.json"), json.dumps({"engine": "ai-edit-engine", "version": "1.0.0"}))
        r = subprocess.run([sys.executable, os.path.join(buyer, "scripts", "apply-update.py"), pkg], cwd=buyer,
                           capture_output=True, text=True, env=ENV, encoding="utf-8", errors="replace")
        check("a buyer's real update from it says plainly that it did not carry the originals",
              r.returncode == 0 and "did not carry the originals" in r.stdout + r.stderr, r.stdout + r.stderr)
        check("...and removes the retired files her engine had", not os.path.exists(os.path.join(buyer, "old", "tool.py")))

        print("\n3. a 2.0.x release carries originals from 2.0.0 on, and nothing older")
        vend = ".claude/skills/upstream-kit/SKILL.md"
        w100 = {"a.py": "a = 0\n", "legacy.md": "# legacy\n\n" + HIT + "\n"}
        w200 = {"a.py": "a = 20\n", "b.py": "b = 20\n", "docs/guide.md": "# guide\n"}
        w201 = dict(w200, **{"a.py": "a = 21\n", vend: "# upstream\n\n" + HIT + "\n",
                             "LICENSE.md": "# License\n\nCopyright upstream\n" + HIT + "\n"})
        w200_retiring = dict(w200, **{"docs/retired.md": "# retired in 2.0.1\n"})
        s = seller(tmp, "s3", {"1.0.0": w100, "2.0.0": w200_retiring, "2.0.1": w201}, zips=("1.0.0", "2.0.0"),
                   vendored=("upstream-kit",))
        rc, out, man, pkg = build(s)
        check("the package builds (a vendored upstream skill and licence text are exempt, as in the ship gate; "
              "a 1.0.x release is never read)", rc == 0 and man is not None, out)
        check("a file a 2.0.x release retired is removed", "docs/retired.md" in (man or {}).get("deletes", []),
              (man or {}).get("deletes"))
        pub = os.path.join(s, "dist", "updates", "publish")
        priv = os.path.join(pub, "u", "0" * 32, "v2")
        check("the private feed gets the update: its latest.json and the zip, at <site>/u/<code>/v2",
              os.path.isfile(os.path.join(priv, "latest.json")) and os.path.isfile(os.path.join(priv, "ai-edit-engine-update-v2.0.1.zip")),
              sorted(os.listdir(priv)) if os.path.isdir(priv) else "no private feed folder")
        us = verifier(s)
        zname = "ai-edit-engine-update-v2.0.1.zip"
        try:
            with open(os.path.join(priv, "latest.json"), encoding="utf-8") as fh:
                feed = json.load(fh)
        except (OSError, ValueError):
            feed = {}
        check("the feed is signed, over its version, file name and the zip's sha256",
              us.check_feed(feed) == "" and feed.get("file") == zname
              and feed.get("sha256") == sha(open(os.path.join(priv, zname), "rb").read()), feed)
        check("the package carries update.json.sig, valid over update.json's exact bytes",
              os.path.isfile(os.path.join(pkg, "update.json.sig")) and us.check_manifest(
                  open(os.path.join(pkg, "update.json"), "rb").read(),
                  open(os.path.join(pkg, "update.json.sig"), encoding="utf-8").read()) == "")
        zp = os.path.join(s, "dist", "updates", zname)
        check("the zip gets a detached .sig, beside it in dist/ and in the private feed",
              os.path.isfile(zp + ".sig") and os.path.isfile(os.path.join(priv, zname + ".sig"))
              and us.check_zip(zp, open(zp + ".sig", encoding="utf-8").read()) == "")
        check("search engines are told to keep off it", "/u/*" in (open(os.path.join(pub, "_headers"), encoding="utf-8").read() if os.path.isfile(os.path.join(pub, "_headers")) else ""))
        shipped_text = ""
        if man:
            with open(os.path.join(pkg, "update.json"), encoding="utf-8") as fh:
                shipped_text = fh.read()
            with open(os.path.join(pkg, "files", "product", "templates", "update-deletes.json"), encoding="utf-8") as fh:
                shipped_text += fh.read()
        check("no 1.x path appears anywhere a 2.x package ships (a 2.x install never held one)",
              bool(shipped_text) and "legacy.md" not in shipped_text, (man or {}).get("deletes"))
        o = originals(os.path.join(pkg, "files", STORE)) if man else None
        check("the archive opens", bool(o and o.ok))
        if o and o.ok:
            check("its index lists only 2.0.0 and 2.0.1", sorted(o.versions) == ["2.0.0", "2.0.1"], sorted(o.versions))
            check("it carries the 2.0.0 and 2.0.1 originals",
                  {sha("a = 20\n"), sha("b = 20\n"), sha("a = 21\n"), sha("# guide\n")} <= set(o.blobs), len(o.blobs))
            check("and nothing from before 2.0.0", sha("a = 0\n") not in o.blobs and sha(w100["legacy.md"]) not in o.blobs)
        first = sha(open(os.path.join(pkg, "files", STORE), "rb").read()) if man else ""
        rc, out2, man2, pkg2 = build(s)
        again = sha(open(os.path.join(pkg2, "files", STORE), "rb").read()) if man2 else "(not built)"
        check("building it again gives the same archive, byte for byte", rc == 0 and first and again == first)
        pub = os.path.join(s, "dist", "updates", "publish")
        feeds = {}
        for rel in ("latest.json", "v2/latest.json"):
            try:
                with open(os.path.join(pub, *rel.split("/")), encoding="utf-8") as fh:
                    feeds[rel] = json.load(fh).get("version")
            except (OSError, ValueError):
                feeds[rel] = None
        check("the site root keeps the frozen v1 feed's message, and 2.x goes up in v2/ beside it",
              feeds == {"latest.json": "1.0.94", "v2/latest.json": "2.0.1"}
              and os.path.exists(os.path.join(pub, "v2", "ai-edit-engine-update-v2.0.1.zip")), feeds)
        check("the retired v1 zip is never published (only its latest.json goes up)",
              not os.path.exists(os.path.join(pub, "ai-edit-engine-update-v1.0.94.zip")))

        # The v1 bridge (dev-tools/v1-bridge/) DOES go up beside the root latest.json: it carries no engine
        # code, only what makes "update me" on a beta install show the way to the new engine. A v1 zip that
        # carries anything more still stays local.
        def v1_feed(root, extra=()):
            files = {".claude/skills/update/SKILL.md": "# update\n", "scripts/move-to-new-engine.py": "print()\n",
                     "scripts/post-update.py": "print()\n", **{p: "x\n" for p in extra}}
            top = "ai-edit-engine-update-v1.0.96"
            man = {"engine": "ai-edit-engine", "version": "1.0.96", "min_version": "1.0.0", "deletes": [],
                   "files": [{"path": p, "sha256": sha(b)} for p, b in files.items()]}
            zp = os.path.join(root, "releases", "feed-v1", top + ".zip")
            with zipfile.ZipFile(zp, "w") as zf:
                zf.writestr(f"{top}/update.json", json.dumps(man))
                for p, b in files.items():
                    zf.writestr(f"{top}/files/{p}", b)
            with open(zp, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            write(os.path.join(root, "releases", "feed-v1", "latest.json"), json.dumps(
                {"engine": "ai-edit-engine", "version": "1.0.96", "file": top + ".zip", "sha256": digest}))
        v1_feed(s)
        rc_b, out_b, _m, _p = build(s)
        check("the v1 bridge zip is published at the site root, beside its latest.json",
              rc_b == 0 and os.path.isfile(os.path.join(pub, "ai-edit-engine-update-v1.0.96.zip"))
              and json.load(open(os.path.join(pub, "latest.json"), encoding="utf-8")).get("version") == "1.0.96",
              out_b[-400:])
        check("...and 2.x still goes up only in v2/", os.path.isfile(os.path.join(pub, "v2", "latest.json"))
              and json.load(open(os.path.join(pub, "v2", "latest.json"), encoding="utf-8")).get("version") == "2.0.1")
        v1_feed(s, extra=("product/engine.py",))
        rc_e, out_e, _m, _p = build(s)
        check("a v1 zip carrying anything beyond the bridge is never published",
              rc_e == 0 and not os.path.exists(os.path.join(pub, "ai-edit-engine-update-v1.0.96.zip")), out_e[-400:])
        with open(os.path.join(s, "product.json"), encoding="utf-8") as fh:
            prod = json.load(fh)
        write(os.path.join(s, "product.json"), json.dumps(dict(prod, update_url="https://updates.example.test")))
        rc_root, out_root, _m, _p = build(s)
        check("a 2.x engine pointed at the site root is refused (it would read the frozen v1 feed)",
              rc_root != 0 and "/v2" in out_root, out_root[-300:])
        write(os.path.join(s, "product.json"), json.dumps(prod))
        # A 1.x install moves to 2.0 by a fresh download plus "bring over my old engine", never an update:
        # keep_changes holds no 1.x originals, and every updater (the 1.x ones too) enforces min_version.
        check("a 2.x package is for 2.x installs only: min_version 2.0.0, so a 1.x updater turns it away",
              (man or {}).get("min_version") == "2.0.0", (man or {}).get("min_version"))
        r = subprocess.run([sys.executable, "make-update.py", "test release", "--change", "a change", "--from", "1.0.0"],
                           cwd=s, capture_output=True, text=True, env=ENV, encoding="utf-8", errors="replace")
        check("a 2.x package is never built from a 1.x base", r.returncode != 0 and "1.x release" in r.stdout + r.stderr,
              (r.stdout + r.stderr)[-400:])
        s0 = seller(tmp, "s3-first", {"1.0.0": w100, "2.0.0": w200}, zips=("1.0.0",))
        rc0, out0, man0, _pkg0 = build(s0)
        check("2.0.0 itself is not an update: it ships as a fresh download", rc0 != 0 and man0 is None
              and "fresh download" in out0, out0[-400:])

        print("\n4. one blocklisted line: in this release it fails the build by name; in an older release it is left out")
        s = seller(tmp, "s4-release", {"2.0.0": w200, "2.0.1": dict(w200, **{"docs/guide.md": "# guide\n\n" + HIT + "\n"})},
                   zips=("2.0.0",))
        rc, out, man, pkg = build(s)
        check("in this release: the build stops", rc != 0, out)
        check("in this release: naming the file and the pattern", "docs/guide.md" in out and ("crib" + "bed") in out, out)
        check("in this release: no update file was made",
              not any(f.endswith(".zip") for f in os.listdir(os.path.join(s, "dist", "updates")))
              if os.path.isdir(os.path.join(s, "dist", "updates")) else True)
        old = "# notes\n\n" + HIT + "\n"
        s = seller(tmp, "s4-older", {"2.0.0": dict(w200, **{"docs/old-notes.md": old}), "2.0.1": w200}, zips=("2.0.0",))
        rc, out, man, pkg = build(s)
        check("in a 2.0.x release's zip: the build still succeeds", rc == 0 and man is not None, out)
        o = originals(os.path.join(pkg, "files", STORE)) if man else None
        check("in a 2.0.x release's zip: that older original is left out of the archive",
              bool(o and o.ok) and sha(old) not in o.blobs, sorted(o.blobs)[:5] if (o and o.ok) else out)
        check("in a 2.0.x release's zip: the build says it left an older original out", "left out" in out, out)

        print("\n4b. no signing key, no release")
        s = seller(tmp, "s4b", {"2.0.0": w200, "2.0.1": dict(w200, **{"a.py": "a = 21\n"})}, zips=("2.0.0",))
        missing = os.path.join(tmp, "no-such-dir", "engine-update-signing.key")
        r = subprocess.run([sys.executable, "make-update.py", "test release"], cwd=s, capture_output=True, text=True,
                           env={**ENV, "ENGINE_UPDATE_SIGNING_KEY": missing}, encoding="utf-8", errors="replace")
        check("make-update.py stops, names the missing key's path, and builds nothing",
              r.returncode != 0 and missing in (r.stdout + r.stderr)
              and not os.path.exists(os.path.join(s, "dist", "updates")), r.stdout + r.stderr)
        other = os.path.join(tmp, "other.key")
        write(other, "-----BEGIN " + "PRIVATE KEY-----\n" + base64.b64encode(bytes.fromhex(
            "302e020100300506032b657004220420") + b"\x07" * 32).decode("ascii") + "\n-----END PRIVATE KEY-----\n")
        r = subprocess.run([sys.executable, "make-update.py", "test release"], cwd=s, capture_output=True, text=True,
                           env={**ENV, "ENGINE_UPDATE_SIGNING_KEY": other}, encoding="utf-8", errors="replace")
        check("a key the engine does not pin is refused (its releases would be refused by every engine)",
              r.returncode != 0 and "not pinned" in (r.stdout + r.stderr), r.stdout + r.stderr)

        print("\n5. a check that cannot run is not a pass")
        s = seller(tmp, "s5", {"2.0.0": w200, "2.0.1": dict(w200, **{"a.py": "a = 21\n"})}, zips=("2.0.0",))
        os.remove(os.path.join(s, "dev-tools", "prose-blocklist.txt"))
        rc, out, man, pkg = build(s)
        check("with no blocklist to check against, the build stops and says why", rc != 0 and "blocklist" in out, out)

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed: every retired file goes, and originals start at 2.0.0, blocklist-clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
