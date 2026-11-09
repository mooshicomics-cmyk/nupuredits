#!/usr/bin/env python3
"""Guard: a computer with no Python can still receive an update, and nothing pokes Apple's placeholder.

Measured on a tester's fresh Intel Mac (2026-09-18). The updater is Python. A fresh Mac's only `python3`
is Apple's placeholder at /usr/bin/python3, which does not run Python: it opens the "install the developer
tools?" dialog and exits 1. "update me" ran that placeholder, the dialog popped, and the update never
happened, so the setup route her chip needed (already on the feed) could not reach her. Four things pin it:

  1. scripts/_python3-shim.sh recognises the placeholder by path + `xcode-select -p` and never EXECUTES it,
     and still finds a real interpreter elsewhere on disk (uv's ~/.local/bin shim, first).
  2. scripts/ensure-python.sh --check reports "none" without installing and without poking.
  3. scripts/ensure-python.sh (no flag) installs through uv when there is none, and prints the interpreter.
     (uv is stood in by a fake here; the real download is exercised by hand, never in a ship gate.)
  4. The Intel route's own step log no longer quotes JSON through python3 (json_str, pure shell), and its
     two download lookups (ffmpeg's release info, Node's release index) are read without Python too: on a
     simulated fresh Intel Mac `intel-mac-install.sh ffmpeg` and `node` install end to end and the
     placeholder never runs.

Run: python3 product/tests/test_python_bootstrap.py
"""
import json, os, re, stat, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-400:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def write_exec(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def fresh_mac(tmp, with_real_python=False, with_fake_uv=False):
    """A PATH that looks like a Mac with no developer tools: the only python3 is a placeholder that records
    every execution, xcode-select says the tools are missing, and uname says Darwin. Optionally a real
    python3 sits where uv's --default shim would, or a fake uv that installs one."""
    home = os.path.join(tmp, "home")
    fakebin = os.path.join(tmp, "fakebin")
    poked = os.path.join(tmp, "POKED")
    write_exec(os.path.join(fakebin, "python3"), f"#!/bin/sh\necho poked >> '{poked}'\nexit 1\n")
    write_exec(os.path.join(fakebin, "xcode-select"), "#!/bin/sh\nexit 2\n")
    write_exec(os.path.join(fakebin, "uname"), "#!/bin/sh\ncase \"$1\" in -s) echo Darwin;; -m) echo x86_64;; *) echo Darwin;; esac\n")
    # the shell still needs its basics
    for tool in ("sh", "bash", "dirname", "cat", "printf", "tr", "sed", "grep", "cut", "mkdir", "chmod", "ls", "readlink",
                 "basename", "date", "sw_vers", "sysctl", "cygpath"):
        real = None
        for d in ("/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"):
            if os.path.exists(os.path.join(d, tool)):
                real = os.path.join(d, tool); break
        if real:
            os.symlink(real, os.path.join(fakebin, tool))
    os.makedirs(home, exist_ok=True)
    if with_real_python:
        write_exec(os.path.join(home, ".local", "bin", "python3"), f"#!/bin/sh\nexec '{sys.executable}' \"$@\"\n")
    if with_fake_uv:
        # a stand-in uv where the engine's own setup would have put it (~/.local/bin), which
        # ensure-python.sh prefers over any system-wide uv this laptop happens to have:
        # `python install 3.11 --default` drops the shim, `python find 3.11` names it
        write_exec(os.path.join(home, ".local", "bin", "uv"), f"""#!/bin/sh
case "$1 $2" in
  "python install") mkdir -p '{home}/.local/bin'; printf '#!/bin/sh\\nexec "{sys.executable}" "$@"\\n' > '{home}/.local/bin/python3'; chmod +x '{home}/.local/bin/python3'; echo installed >&2 ;;
  "python find")    echo '{home}/.local/bin/python3' ;;
  *) echo "fake uv: $*" >&2; exit 1 ;;
esac
""")
    env = {"PATH": fakebin, "HOME": home, "_P3_APPLE_PY": os.path.join(fakebin, "python3"),
           "_P3_SYS_ROOT": os.path.join(tmp, "no-such-root"),   # hide this laptop's Homebrew / python.org Pythons
           "UV_INSTALL_DIR": os.path.join(home, ".local", "bin"), "LANG": "C"}
    return env, poked


def sh(script, env, cwd=ROOT):
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env=env)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


# What the two download indexes the Intel route reads look like, built here so nothing touches the network.
# evermeet.cx's release info (every "/" written as "\/", which JSON allows) and nodejs.org's dist/index.json
# (newest first; "lts" is false or a codename; the newest release here is not LTS and one LTS has no .pkg).
def _evermeet(tool, ver="8.0"):
    base = f"https:\\/\\/evermeet.cx\\/ffmpeg\\/{tool}-{ver}"
    return ('{"name":"%s","type":"release","version":"%s","size":25.9,"download":{'
            '"7z":{"url":"%s.7z","size":17.2,"sig":"%s.7z.sig"},'
            '"zip":{"url":"%s.zip","size":24.7,"sig":"%s.zip.sig"}}}' % (tool, ver, base, base, base, base))


NODE_RELEASES = [
    {"version": "v25.1.0", "files": ["linux-x64", "osx-arm64-tar", "osx-x64-pkg", "win-x64-msi"], "lts": False},
    {"version": "v24.11.0", "files": ["linux-x64", "osx-arm64-tar", "win-x64-msi"], "lts": "Krypton"},
    {"version": "v22.21.1", "files": ["linux-x64", "osx-arm64-tar", "osx-x64-pkg", "win-x64-msi"], "lts": "Jod"},
    {"version": "v20.19.5", "files": ["linux-x64", "osx-x64-pkg", "win-x64-msi"], "lts": "Iron"},
]


# The Intel ffmpeg pin, read from the installer itself so a later pin bump never needs this file edited.
_SRC = open(os.path.join(ROOT, "scripts", "intel-mac-install.sh"), encoding="utf-8").read()
EVERMEET_VER = re.search(r'^EVERMEET_FFMPEG_VERSION="([^"]+)"', _SRC, re.M).group(1)
_EVERMEET_PINS = _SRC[_SRC.index("_evermeet_sha256() {"):]                    # evermeet's pins, not the second source's
PINS = dict(re.findall(r'^\s*(ffmpeg|ffprobe)\)\s+echo "([0-9a-f]{64})"', _EVERMEET_PINS[:_EVERMEET_PINS.index("\n}\n")], re.M))


def fresh_intel_mac(tmp, evermeet_style="compact", node_style="lines"):
    """A copy of the Intel route on a simulated FRESH Intel Mac: the only python3 is Apple's placeholder (it
    records every execution), and curl is a stand-in that serves the two indexes and hands back small fake
    downloads, recording every URL it is asked for. Returns (engine dir, env, record dir)."""
    eng, home, fake, rec = (os.path.join(tmp, d) for d in ("eng", "home", "fakebin", "rec"))
    for d in (os.path.join(eng, "scripts"), home, fake, rec, os.path.join(tmp, "t")):
        os.makedirs(d, exist_ok=True)
    for name in ("intel-mac-install.sh", "_mac-arch.sh"):
        with open(os.path.join(ROOT, "scripts", name), encoding="utf-8") as src, \
             open(os.path.join(eng, "scripts", name), "w", encoding="utf-8") as dst:
            dst.write(src.read())
    idx = os.path.join(tmp, "idx")
    os.makedirs(idx, exist_ok=True)
    for tool in ("ffmpeg", "ffprobe"):
        body = _evermeet(tool)
        if evermeet_style == "pretty":   # the same document, indented, with plain slashes
            body = json.dumps(json.loads(body), indent=4)
        with open(os.path.join(idx, f"{tool}.json"), "w", encoding="utf-8") as f:
            f.write(body)
        # the "download": a zip holding a stand-in binary that answers -version
        with zipfile.ZipFile(os.path.join(idx, f"{tool}.zip"), "w") as z:
            # PINNED-OK: the stand-in openssl below reports the pinned sha256 for it (the zip is stored, not
            # compressed, so the marker is readable); a zip without it hashes to zeros, i.e. tampered.
            z.writestr(tool, f"#!/bin/sh\n# PINNED-OK\necho '{tool} version {EVERMEET_VER} Copyright (c) the FFmpeg developers'\n")
    with open(os.path.join(idx, "index.json"), "w", encoding="utf-8") as f:
        if node_style == "lines":        # how nodejs.org writes it: one release per line
            f.write("[\n" + ",\n".join(json.dumps(r, separators=(",", ":")) for r in NODE_RELEASES) + "\n]\n")
        else:                            # the same list on a single line
            f.write(json.dumps(NODE_RELEASES, separators=(",", ":")))
    write_exec(os.path.join(fake, "python3"), f"#!/bin/sh\necho \"$*\" >> '{rec}/POKED'\nexit 1\n")
    write_exec(os.path.join(fake, "uname"), "#!/bin/sh\ncase \"$1\" in -m) echo x86_64;; *) echo Darwin;; esac\n")
    write_exec(os.path.join(fake, "sysctl"), "#!/bin/sh\ncase \"$2\" in machdep.cpu.brand_string) echo 'Intel(R) Core(TM) i5';;"
                                             " hw.physicalcpu) echo 4;; hw.logicalcpu) echo 8;; *) exit 1;; esac\n")
    write_exec(os.path.join(fake, "sw_vers"), "#!/bin/sh\necho 13.6.9\n")
    write_exec(os.path.join(fake, "file"), "#!/bin/sh\n[ \"$1\" = -b ] && shift && echo 'Mach-O 64-bit executable x86_64' && exit 0\n"
                                           "echo \"$1: Mach-O 64-bit executable x86_64\"\n")
    write_exec(os.path.join(fake, "xattr"), "#!/bin/sh\nexit 0\n")
    write_exec(os.path.join(fake, "openssl"), f"""#!/bin/sh
f=""; for a; do f="$a"; done
case "$f" in *ffprobe*) h={PINS["ffprobe"]} ;; *) h={PINS["ffmpeg"]} ;; esac
grep -q PINNED-OK "$f" || h={"0" * 64}
echo "SHA256($f)= $h"
""")
    write_exec(os.path.join(fake, "open"), f"#!/bin/sh\necho \"$*\" >> '{rec}/OPENED'\n")
    write_exec(os.path.join(fake, "curl"), f"""#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift ;; -m) shift ;; -*) ;; *) url="$1" ;; esac; shift; done
if [ -n "$out" ]; then
  echo "$url" >> '{rec}/DOWNLOADS'
  case "$url" in
    *ffmpeg-*.zip) cp '{idx}/ffmpeg.zip' "$out" ;;
    *ffprobe-*.zip) cp '{idx}/ffprobe.zip' "$out" ;;
    *.pkg) echo pkg > "$out" ;;
    *) exit 22 ;;
  esac
  exit 0
fi
case "$url" in
  */info/ffmpeg/release) cat '{idx}/ffmpeg.json' ;;
  */info/ffprobe/release) cat '{idx}/ffprobe.json' ;;
  */dist/index.json) cat '{idx}/index.json' ;;
  *) exit 6 ;;
esac
""")
    for tool in ("sh", "bash", "dirname", "basename", "mktemp", "date", "sed", "tr", "grep", "cut", "head", "mkdir",
                 "rm", "cat", "chmod", "mv", "cp", "unzip", "wc", "printf"):
        for d in ("/bin", "/usr/bin"):
            if os.path.exists(os.path.join(d, tool)):
                os.symlink(os.path.join(d, tool), os.path.join(fake, tool))
                break
    env = {"PATH": fake, "HOME": home, "TMPDIR": os.path.join(tmp, "t"), "LANG": "C", "INTEL_FETCH_WAIT": "0"}
    return eng, env, rec


def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def main():
    print("a machine with no Python still gets its update, and Apple's placeholder is never run\n")

    print("1. the python3 shim recognises the placeholder without executing it")
    with tempfile.TemporaryDirectory() as tmp:
        env, poked = fresh_mac(tmp)
        rc, out, err = sh('. scripts/_python3-shim.sh; echo "ok=$_P3_OK"', env)
        check("shim sources cleanly on a fresh Mac", rc == 0, err)
        check("shim reports no usable Python", out.endswith("ok=0"), out)
        check("the placeholder was never executed", not os.path.exists(poked))
    with tempfile.TemporaryDirectory() as tmp:
        env, poked = fresh_mac(tmp, with_real_python=True)
        rc, out, err = sh('. scripts/_python3-shim.sh; echo "ok=$_P3_OK"; python3 -c "import sys; print(sys.executable)"', env)
        check("shim finds uv's ~/.local/bin/python3 on a Mac", rc == 0 and "ok=1" in out and sys.executable in out, out + err)
        check("...and still never executed the placeholder", not os.path.exists(poked))

    print("2. ensure-python.sh --check reports without installing")
    with tempfile.TemporaryDirectory() as tmp:
        env, poked = fresh_mac(tmp)
        rc, out, err = sh("bash scripts/ensure-python.sh --check", env)
        check("exit 3 = none, nothing installed", rc == 3, f"rc={rc} {out} {err}")
        check("nothing on stdout (stdout is only ever the path)", out == "", out)
        check("the placeholder was never executed", not os.path.exists(poked))
        check("no uv was installed", not os.path.exists(os.path.join(env["HOME"], ".local", "bin", "uv")))

    print("3. ensure-python.sh installs a Python through uv when there is none")
    with tempfile.TemporaryDirectory() as tmp:
        env, poked = fresh_mac(tmp, with_fake_uv=True)
        rc, out, err = sh("bash scripts/ensure-python.sh", env)
        shim = os.path.join(env["HOME"], ".local", "bin", "python3")
        check("exit 0", rc == 0, f"rc={rc} {out} {err}")
        check("stdout is exactly the interpreter path", out == shim, out)
        check("that interpreter runs", os.path.exists(shim) and subprocess.run([shim, "-c", "print(1)"], capture_output=True, text=True).stdout.strip() == "1")
        check("the placeholder was never executed", not os.path.exists(poked))
        # second run: instant, same answer, no reinstall message
        rc2, out2, err2 = sh("bash scripts/ensure-python.sh", env)
        # the second run answers with sys.executable of whatever the shim resolved (the real interpreter
        # behind ~/.local/bin/python3), which is a different spelling of the same Python
        check("a second run finds it without installing again",
              rc2 == 0 and out2 and os.path.exists(out2) and "helper" not in err2, f"{out2} {err2}")

    print("4. a machine that already has Python is untouched")
    rc, out, err = sh("bash scripts/ensure-python.sh --check", dict(os.environ))
    check("prints the current interpreter and exits 0", rc == 0 and out and os.path.exists(out), f"rc={rc} {out} {err}")

    print("5. the Intel route's step log needs no Python")
    src = open(os.path.join(ROOT, "scripts", "intel-mac-install.sh"), encoding="utf-8").read()
    check("_route_step no longer shells out to python3", "json.dumps" not in src and "json_str" in src)
    rc, out, err = sh(r""". scripts/_mac-arch.sh; json_str "$(printf 'a"b\\c\td\ne')" """, dict(os.environ))
    try:
        val = json.loads(out)
    except Exception as e:  # noqa: BLE001
        val = e
    check("json_str emits valid JSON for quotes, backslashes, tabs and newlines", val == 'a"b\\c d e', repr(val))
    # Nothing in the route may run python3 itself: ffmpeg is its FIRST step and node can be asked for alone,
    # both before any real Python exists. Only the interpreter uv just installed ("$_py") may run Python.
    code = [ln.split("#", 1)[0] for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    bare = [ln.strip() for ln in code if re.search(r"(^|[|;&(`]|\$\()\s*python3?\s+[-\w./\"'$<]", ln)]
    check("no bare python3 call anywhere in the Intel route", not bare, bare)
    for evermeet_style, node_style in (("compact", "lines"), ("pretty", "one-line")):
        label = f"({evermeet_style} evermeet info, {node_style} node index)"
        with tempfile.TemporaryDirectory() as tmp:
            eng, env, rec = fresh_intel_mac(tmp, evermeet_style, node_style)
            rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, cwd=eng)
            check(f"ffmpeg + ffprobe install on a fresh Intel Mac {label}", rc == 0, f"rc={rc} {out} {err}")
            check(f"...from the pinned evermeet zips, checksum-verified {label}", _lines(os.path.join(rec, "DOWNLOADS")) == [
                f"https://evermeet.cx/ffmpeg/ffmpeg-{EVERMEET_VER}.zip", f"https://evermeet.cx/ffmpeg/ffprobe-{EVERMEET_VER}.zip"],
                _lines(os.path.join(rec, "DOWNLOADS")))
            landed = [os.path.join(env["HOME"], ".local", "bin", t) for t in ("ffmpeg", "ffprobe")]
            check(f"...and both run from ~/.local/bin {label}", all(os.access(p, os.X_OK) for p in landed))
            rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, cwd=eng)
            pkg = os.path.join(env["HOME"], "Downloads", "node-v22.21.1.pkg")
            check(f"node picks the newest LTS that has a macOS installer {label}",
                  rc == 0 and _lines(os.path.join(rec, "DOWNLOADS"))[-1:] == ["https://nodejs.org/dist/v22.21.1/node-v22.21.1.pkg"],
                  f"rc={rc} {_lines(os.path.join(rec, 'DOWNLOADS'))} {err}")
            check(f"...saves it to Downloads and opens it {label}",
                  os.path.exists(pkg) and _lines(os.path.join(rec, "OPENED")) == [pkg], _lines(os.path.join(rec, "OPENED")))
            check(f"Apple's placeholder never ran {label}", not os.path.exists(os.path.join(rec, "POKED")),
                  _lines(os.path.join(rec, "POKED")))
            try:
                with open(os.path.join(eng, "_local", "install-route.json"), encoding="utf-8") as f:
                    steps = json.load(f)["steps"]
            except (OSError, ValueError, KeyError) as e:
                steps = e
            check(f"the step log records the node step as done {label}",
                  isinstance(steps, list) and [(s["tool"], s["exit"]) for s in steps] == [("node", 0)], steps)

    print("6. the setup checker and the update skill never run bare python3 on a fresh Mac")
    cs = open(os.path.join(ROOT, "check-setup.sh"), encoding="utf-8").read()
    check("check-setup.sh carries the placeholder guard", "_cs_apple_stub" in cs and '"${_P3_OK:-0}" -eq 1' in cs)
    sk = open(os.path.join(ROOT, ".claude", "skills", "update", "SKILL.md"), encoding="utf-8").read()
    check("the update skill bootstraps Python first", "ensure-python.sh" in sk and "python3 scripts/apply-update.py" not in sk)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails)); sys.exit(1)
    print("all good: a fresh machine can update itself, and Apple's dialog stays closed")


if __name__ == "__main__":
    main()
