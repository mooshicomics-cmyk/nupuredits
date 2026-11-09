#!/usr/bin/env python3
"""Guard: an Apple-chip Mac on a macOS older than Homebrew supports gets a setup that works.

Reported on launch day (2026-09-30): an Apple-chip buyer on macOS 13 (Ventura) ran the Homebrew installer
the setup handed her and it "stays there" at "Installing Command Line Tools for Xcode-14.3 / Finding
available software". Homebrew's floor is macOS 15 now (MACOS_OLDEST_SUPPORTED="15.0"), it ships ready-made
arm64 packages for 15 and newer only, and past that line every `brew install` would compile for hours.
Three things broke on those Macs, and each is pinned here:

  1. ROUTE. scripts/_mac-arch.sh mac_install_route sends an arm64 Mac below MAC_BREW_OLDEST down the
     no-Homebrew route (`direct`), keeps 15+ on `brew`, and leaves Intel and Rosetta exactly as before.
     check-setup.sh then prints only no-Homebrew lines on that Mac.
  2. INSTALLER. scripts/intel-mac-install.sh runs on that Mac, fetches Apple-chip ffmpeg/ffprobe (not
     Intel ones), and still refuses on an Apple-chip Mac Homebrew does support.
  3. NODE + PyAV. Node 24 needs macOS 13.5, so below it Node 22 is installed (on Intel too). PyAV's arm64
     wheels need macOS 14, so the transcriber install forces a wheel (`--only-binary av`) on a Mac instead
     of letting the resolver pick a source build that cannot compile there.

Added 2026-10-02: an Apple-chip Mac on 15+ whose Homebrew install died at Apple's Command Line Tools
download ("not currently available from the Software Update server"). The fallback is the same route, forced
with MAC_DIRECT_ROUTE=1 and then pinned; sections 7 to 9 pin it, the developer-tool placeholder checks, and
a bash 3.2 locale crash the real-machine run of that fallback turned up.

Run: python3 product/tests/test_mac_route.py
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


# The installer's download pins, read from the script itself so a later pin bump never needs this file edited.
_SRC = open(os.path.join(ROOT, "scripts", "intel-mac-install.sh"), encoding="utf-8").read()
EVERMEET_VER = re.search(r'^EVERMEET_FFMPEG_VERSION="([^"]+)"', _SRC, re.M).group(1)
def _pins(fn):
    body = _SRC[_SRC.index(fn + "() {"):]
    return dict(re.findall(r'^\s*(ffmpeg|ffprobe)\)\s+echo "([0-9a-f]{64})"', body[:body.index("\n}\n")], re.M))
PINS = _pins("_evermeet_sha256")
OX_PINS = _pins("_osxexperts_sha256")   # the second Intel source (osxexperts.net), tried when evermeet fails
OXA_PINS = _pins("_osxexperts_arm_sha256")   # the second Apple-chip source (osxexperts.net), when martin-riedl fails
ARM_TEAM = re.search(r'^FFMPEG_ARM_TEAM="([^"]+)"', _SRC, re.M).group(1)


def fake_integrity_tools(fake):
    """Stand-ins for openssl and codesign. The fake zips are stored uncompressed, so their markers are readable:
    PINNED-OK makes openssl report the pinned sha256 (anything else hashes to zeros, i.e. a tampered zip; PINNED-OX
    reports the second Intel source's pin, PINNED-ARMOX the second Apple-chip source's), and
    SIGNED-BY-<team> is the Developer ID signature codesign reports (no marker = unsigned)."""
    write_exec(os.path.join(fake, "openssl"), f"""#!/bin/sh
f=""; for a; do f="$a"; done
case "$f" in *ffprobe*) h={PINS["ffprobe"]} ;; *) h={PINS["ffmpeg"]} ;; esac
grep -q PINNED-OK "$f" || h={"0" * 64}
if grep -q PINNED-OX "$f"; then case "$f" in *ffprobe*) h={OX_PINS["ffprobe"]} ;; *) h={OX_PINS["ffmpeg"]} ;; esac; fi
if grep -q PINNED-ARMOX "$f"; then case "$f" in *ffprobe*) h={OXA_PINS["ffprobe"]} ;; *) h={OXA_PINS["ffmpeg"]} ;; esac; fi
echo "SHA256($f)= $h"
""")
    write_exec(os.path.join(fake, "codesign"), """#!/bin/sh
f=""; for a; do f="$a"; done
grep -q SIGNED-BY- "$f" || { echo "$f: code object is not signed at all" >&2; exit 1; }
team="$(sed -n 's/.*SIGNED-BY-\\([A-Z0-9]*\\).*/\\1/p' "$f" | head -1)"
case "$*" in
  *--test-requirement=*) case "$*" in *"\\"$team\\""*) exit 0 ;; *) exit 3 ;; esac ;;
  *-dv*) echo "TeamIdentifier=$team" >&2 ;;
esac
exit 0
""")


def _lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


# The Node release index, newest first, the way nodejs.org lists it: a Current release that is not LTS, the
# newest LTS (24, which needs macOS 13.5), then the 22 line.
NODE_RELEASES = [
    {"version": "v25.1.0", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": False},
    {"version": "v24.21.0", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": "Krypton"},
    {"version": "v22.23.3", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": "Jod"},
    {"version": "v22.22.0", "files": ["osx-arm64-tar", "osx-x64-pkg"], "lts": "Jod"},
    {"version": "v20.19.5", "files": ["osx-x64-pkg"], "lts": "Iron"},
]


def fake_mac(tmp, machine="arm64", hw_arm64="1", macos="13.4"):
    """A copy of the route scripts on a simulated Mac. uname/sysctl/sw_vers say what we tell them, `file`
    reports whatever arch the downloaded zip says, and curl serves the indexes and small fake downloads,
    recording every URL. Returns (engine dir, env, record dir)."""
    eng, home, fake, rec, idx = (os.path.join(tmp, d) for d in ("eng", "home", "fakebin", "rec", "idx"))
    for d in (os.path.join(eng, "scripts"), home, fake, rec, idx, os.path.join(tmp, "t")):
        os.makedirs(d, exist_ok=True)
    for name in ("intel-mac-install.sh", "_mac-arch.sh", "_fallbacks.sh"):
        with open(os.path.join(ROOT, "scripts", name), encoding="utf-8") as src, \
             open(os.path.join(eng, "scripts", name), "w", encoding="utf-8") as dst:
            dst.write(src.read())
    arch_word = "arm64" if machine == "arm64" else "x86_64"
    for tool in ("ffmpeg", "ffprobe"):
        # the "download": a stand-in binary that answers -version, tagged with the arch it was built for
        with zipfile.ZipFile(os.path.join(idx, f"{tool}.zip"), "w") as z:
            z.writestr(tool, f"#!/bin/sh\n# ARCH=ARM64BUILD SIGNED-BY-{ARM_TEAM} PINNED-OK\necho '{tool} version 9.0.2 Copyright (c) the FFmpeg developers'\n")
        with zipfile.ZipFile(os.path.join(idx, f"{tool}-intel.zip"), "w") as z:
            z.writestr(tool, f"#!/bin/sh\n# ARCH=X86BUILD PINNED-OK\necho '{tool} version {EVERMEET_VER} Copyright (c) the FFmpeg developers'\n")
        with zipfile.ZipFile(os.path.join(idx, f"{tool}-ox.zip"), "w") as z:
            z.writestr(tool, f"#!/bin/sh\n# ARCH=X86BUILD PINNED-OX\necho '{tool} version 8.0 Copyright (c) the FFmpeg developers'\n")
        with zipfile.ZipFile(os.path.join(idx, f"{tool}-oxarm.zip"), "w") as z:   # osxexperts arm64: ad-hoc, unsigned by a team
            z.writestr(tool, f"#!/bin/sh\n# ARCH=ARM64BUILD PINNED-ARMOX\necho '{tool} version 9.0 Copyright (c) the FFmpeg developers'\n")
        with open(os.path.join(idx, f"{tool}.json"), "w", encoding="utf-8") as f:
            f.write('{"download":{"zip":{"url":"https:\\/\\/evermeet.cx\\/ffmpeg\\/%s-8.0.zip"}}}' % tool)
    with open(os.path.join(idx, "index.json"), "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(r, separators=(",", ":")) for r in NODE_RELEASES) + "\n]\n")
    write_exec(os.path.join(fake, "uname"), f"#!/bin/sh\ncase \"$1\" in -m) echo {machine};; *) echo Darwin;; esac\n")
    write_exec(os.path.join(fake, "sysctl"), "#!/bin/sh\ncase \"$2\" in "
               f"hw.optional.arm64) [ '{hw_arm64}' = 1 ] && echo 1 || exit 1;; machdep.cpu.brand_string) echo 'Test CPU';; "
               "hw.physicalcpu) echo 8;; hw.logicalcpu) echo 8;; *) exit 1;; esac\n")
    write_exec(os.path.join(fake, "sw_vers"), f"#!/bin/sh\necho {macos}\n")
    # `file` reads the marker the fake zip wrote, so a wrong-arch download is caught like the real thing
    write_exec(os.path.join(fake, "file"), """#!/bin/sh
b=0; [ "$1" = -b ] && b=1 && shift
if grep -q ARM64BUILD "$1"; then a='Mach-O 64-bit executable arm64'; else a='Mach-O 64-bit executable x86_64'; fi
[ $b = 1 ] && echo "$a" || echo "$1: $a"
""")
    write_exec(os.path.join(fake, "xattr"), "#!/bin/sh\nexit 0\n")
    fake_integrity_tools(fake)
    write_exec(os.path.join(fake, "open"), f"#!/bin/sh\necho \"$*\" >> '{rec}/OPENED'\n")
    write_exec(os.path.join(fake, "python3"), f"#!/bin/sh\necho \"$*\" >> '{rec}/POKED'\nexit 1\n")
    write_exec(os.path.join(fake, "curl"), f"""#!/bin/sh
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift ;; -m|-w) shift ;; -*) ;; *) url="$1" ;; esac; shift; done
if [ -n "$out" ]; then
  echo "$url" >> '{rec}/DOWNLOADS'
  # RATE_LIMITED=<host> answers that host with HTTP 429, the way evermeet did for over an hour (2026-10-21)
  case "$url" in *"${{RATE_LIMITED:-no-such-host}}"*) printf 429; exit 22 ;; esac
  # SERVER_DOWN=<host> answers that host with HTTP 521, the way martin-riedl did all afternoon (2026-10-21)
  case "$url" in *"${{SERVER_DOWN:-no-such-host}}"*) printf 521; exit 22 ;; esac
  case "$url" in
    https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip) cp '{idx}/ffmpeg.zip' "$out" ;;
    https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip) cp '{idx}/ffprobe.zip' "$out" ;;
    *evermeet.cx/ffmpeg/ffmpeg-*.zip) cp '{idx}/ffmpeg-intel.zip' "$out" ;;
    *evermeet.cx/ffmpeg/ffprobe-*.zip) cp '{idx}/ffprobe-intel.zip' "$out" ;;
    https://www.osxexperts.net/ffmpeg80intel.zip) cp '{idx}/ffmpeg-ox.zip' "$out" ;;
    https://www.osxexperts.net/ffprobe80intel.zip) cp '{idx}/ffprobe-ox.zip' "$out" ;;
    https://www.osxexperts.net/ffmpeg9arm.zip) cp '{idx}/ffmpeg-oxarm.zip' "$out" ;;
    https://www.osxexperts.net/ffprobe9arm.zip) cp '{idx}/ffprobe-oxarm.zip' "$out" ;;
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
                 "rm", "cat", "chmod", "mv", "cp", "unzip", "wc", "printf", "id"):
        for d in ("/bin", "/usr/bin"):
            if os.path.exists(os.path.join(d, tool)):
                os.symlink(os.path.join(d, tool), os.path.join(fake, tool))
                break
    # _MA_SYS_ROOT keeps the developer's own /opt/homebrew out of the simulated Mac: with it unset, a test
    # run on a Mac that has Homebrew would see a brew the fake Mac does not have.
    env = {"PATH": fake, "HOME": home, "TMPDIR": os.path.join(tmp, "t"), "LANG": "C", "INTEL_FETCH_WAIT": "0",
           "_MA_SYS_ROOT": os.path.join(tmp, "sysroot")}
    return eng, env, rec


def sh(script, env, cwd):
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env=env)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def ask(fn, **mac):
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, **mac)
        return sh(f". scripts/_mac-arch.sh; {fn}", env, eng)[1]


def main():
    print("1. which route each Mac gets")
    cases = [
        (dict(machine="arm64", macos="13.4"), "direct", "Apple chip, macOS 13.4 (the launch-day buyer)"),
        (dict(machine="arm64", macos="14.7.1"), "direct", "Apple chip, macOS 14"),
        (dict(machine="arm64", macos="15.0"), "brew", "Apple chip, macOS 15.0"),
        (dict(machine="arm64", macos="26.6.2"), "brew", "Apple chip, macOS 26"),
        (dict(machine="x86_64", hw_arm64="0", macos="15.7"), "direct", "true Intel Mac on 15"),
        (dict(machine="x86_64", hw_arm64="1", macos="13.4"), "rosetta", "Apple chip in a Rosetta terminal"),
        (dict(machine="arm64", macos=""), "brew", "unreadable macOS version never forces the slow route"),
    ]
    for mac, want, label in cases:
        got = ask("mac_install_route", **mac)
        check(f"{label} -> {want}", got == want, got)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, machine="arm64", macos="26.6.2")
        env["MAC_DIRECT_ROUTE"] = "1"
        got = sh(". scripts/_mac-arch.sh; mac_install_route", env, eng)[1]
        check("MAC_DIRECT_ROUTE=1 forces direct on a current Apple-chip Mac", got == "direct", got)

    print("2. which Node line each macOS gets")
    for macos, want in (("11.7.10", "22"), ("13.4", "22"), ("13.5", "lts"), ("13.7.8", "lts"), ("26.6.2", "lts")):
        got = ask("mac_node_line", machine="arm64", macos=macos)
        check(f"macOS {macos} -> {want}", got == want, got)

    print("3. the installer on an Apple-chip Mac below Homebrew's floor")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("ffmpeg + ffprobe install", rc == 0, f"rc={rc} {out} {err}")
        check("...from the Apple-chip builds, not evermeet's Intel ones", _lines(os.path.join(rec, "DOWNLOADS")) == [
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip",
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip"],
            _lines(os.path.join(rec, "DOWNLOADS")))
        landed = [os.path.join(env["HOME"], ".local", "bin", t) for t in ("ffmpeg", "ffprobe")]
        check("...and both run from ~/.local/bin", all(os.access(p, os.X_OK) for p in landed))
        rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, eng)
        pkg = os.path.join(env["HOME"], "Downloads", "node-v22.23.3.pkg")
        check("node below 13.5 is the newest 22, not the newest LTS (24 will not start there)",
              rc == 0 and _lines(os.path.join(rec, "DOWNLOADS"))[-1:] == ["https://nodejs.org/dist/v22.23.3/node-v22.23.3.pkg"],
              f"rc={rc} {_lines(os.path.join(rec, 'DOWNLOADS'))} {err}")
        check("...saved to Downloads and opened", os.path.exists(pkg) and _lines(os.path.join(rec, "OPENED")) == [pkg],
              _lines(os.path.join(rec, "OPENED")))
        check("Apple's python3 placeholder never ran", not os.path.exists(os.path.join(rec, "POKED")),
              _lines(os.path.join(rec, "POKED")))
        try:
            with open(os.path.join(eng, "_local", "install-route.json"), encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, ValueError) as e:
            log = e
        check("the step log records arm64 and the node step", isinstance(log, dict) and log.get("arch_class") == "arm64"
              and [(s["tool"], s["exit"]) for s in log["steps"]] == [("node", 0)], log)

    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="14.7.1")
        rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, eng)
        check("macOS 14 gets the newest LTS", rc == 0 and _lines(os.path.join(rec, "DOWNLOADS"))[-1:] ==
              ["https://nodejs.org/dist/v24.21.0/node-v24.21.0.pkg"], f"{_lines(os.path.join(rec, 'DOWNLOADS'))} {err}")

    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="15.1")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("still refuses on an Apple-chip Mac Homebrew supports", rc == 2 and not _lines(os.path.join(rec, "DOWNLOADS")),
              f"rc={rc} {err}")

    print("4. Intel is unchanged, except Node on old macOS")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="13.4")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg && bash scripts/intel-mac-install.sh node", env, eng)
        got = _lines(os.path.join(rec, "DOWNLOADS"))
        check("Intel ffmpeg still comes from evermeet, at the pinned version", rc == 0 and got[:2] == [
            f"https://evermeet.cx/ffmpeg/ffmpeg-{EVERMEET_VER}.zip", f"https://evermeet.cx/ffmpeg/ffprobe-{EVERMEET_VER}.zip"],
            f"rc={rc} {got} {err}")
        check("Intel on 13.4 also gets Node 22", got[-1:] == ["https://nodejs.org/dist/v22.23.3/node-v22.23.3.pkg"], got)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="13.4")
        # an Apple-chip zip handed to an Intel Mac must be refused, not installed
        with open(os.path.join(tmp, "fakebin", "curl"), encoding="utf-8") as f:
            body = f.read().replace("ffmpeg-intel.zip", "ffmpeg.zip")
        write_exec(os.path.join(tmp, "fakebin", "curl"), body)
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("a wrong-chip download is refused", rc != 0 and "not an x86_64 binary" in err, f"rc={rc} {err}")

    print("4a. evermeet rate-limits (HTTP 429, a buyer 2026-10-21): the second Intel source, pinned, logged")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="11.7.10")
        env["RATE_LIMITED"] = "evermeet.cx"
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        got = _lines(os.path.join(rec, "DOWNLOADS"))
        check("ffmpeg + ffprobe install anyway", rc == 0, f"rc={rc} {out} {err}")
        check("...evermeet asked twice, then osxexperts; ffprobe goes straight there (one release for both)", got == [
            f"https://evermeet.cx/ffmpeg/ffmpeg-{EVERMEET_VER}.zip", f"https://evermeet.cx/ffmpeg/ffmpeg-{EVERMEET_VER}.zip",
            "https://www.osxexperts.net/ffmpeg80intel.zip", "https://www.osxexperts.net/ffprobe80intel.zip"], got)
        check("...she is told evermeet is busy, in plain words", "evermeet.cx is busy" in out, out)
        landed = [os.path.join(env["HOME"], ".local", "bin", t) for t in ("ffmpeg", "ffprobe")]
        check("...both run from ~/.local/bin", all(os.access(p, os.X_OK) for p in landed))
        log = "\n".join(_lines(os.path.join(eng, "_local", "fallbacks.log")))
        check("...the switch is in _local/fallbacks.log, once, naming the 429",
              log.count("intel-mac-install:") == 1 and "HTTP 429" in log and "osxexperts" in log, log)
        try:
            with open(os.path.join(eng, "_local", "install-route.json"), encoding="utf-8") as f:
                steps = json.load(f)["steps"]
        except (OSError, ValueError, KeyError) as e:
            steps = e
        check("...the step log names the source that served each tool", isinstance(steps, list)
              and [(s["tool"], s["source"], s["exit"]) for s in steps] == [("ffmpeg", "osxexperts.net", 0),
                                                                         ("ffprobe", "osxexperts.net", 0)], steps)
        check("Apple's python3 placeholder never ran", not os.path.exists(os.path.join(rec, "POKED")))
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="13.4")
        env["RATE_LIMITED"] = ".zip"               # every download site refuses
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("both sources down: a plain failure, nothing installed, both named", rc != 0
              and "neither Intel source" in err and not os.path.exists(os.path.join(env["HOME"], ".local", "bin", "ffmpeg")),
              f"rc={rc} {err}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="x86_64", hw_arm64="0", macos="13.4")
        env["RATE_LIMITED"] = "evermeet.cx"
        _ox = os.path.join(tmp, "idx", "ffmpeg-ox.zip")
        with zipfile.ZipFile(_ox) as z:
            _body = z.read("ffmpeg").decode()
        with zipfile.ZipFile(_ox, "w") as z:
            z.writestr("ffmpeg", _body.replace("PINNED-OX", "TAMPERED"))
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("the second source is checksum-pinned too (fail closed)", rc != 0 and "did not match the exact copy" in err
              and not os.path.exists(os.path.join(env["HOME"], ".local", "bin", "ffmpeg")), f"rc={rc} {err}")

    print("4c. martin-riedl is down (HTTP 521, every Apple-chip buyer 2026-10-21): the second Apple-chip source, pinned, logged")
    for label, mac in (("macOS 13.4 (the reporting buyer)", dict(machine="arm64", macos="13.4")),
                       ("macOS 12.7 (osxexperts' floor is 12.0)", dict(machine="arm64", macos="12.7.6"))):
        with tempfile.TemporaryDirectory() as tmp:
            eng, env, rec = fake_mac(tmp, **mac)
            env["SERVER_DOWN"] = "martin-riedl.de"
            rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
            got = _lines(os.path.join(rec, "DOWNLOADS"))
            mr = "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip"
            check(f"{label}: ffmpeg + ffprobe install anyway", rc == 0, f"rc={rc} {out} {err}")
            check(f"{label}: martin-riedl asked twice, then osxexperts; ffprobe goes straight there", got == [
                mr, mr, "https://www.osxexperts.net/ffmpeg9arm.zip", "https://www.osxexperts.net/ffprobe9arm.zip"], got)
            landed = [os.path.join(env["HOME"], ".local", "bin", t) for t in ("ffmpeg", "ffprobe")]
            check(f"{label}: both run from ~/.local/bin", all(os.access(p, os.X_OK) for p in landed))
            log = "\n".join(_lines(os.path.join(eng, "_local", "fallbacks.log")))
            check(f"{label}: the switch is in _local/fallbacks.log, once, naming the 521",
                  log.count("intel-mac-install:") == 1 and "HTTP 521" in log and "osxexperts" in log, log)
            try:
                with open(os.path.join(eng, "_local", "install-route.json"), encoding="utf-8") as f:
                    steps = json.load(f)["steps"]
            except (OSError, ValueError, KeyError) as e:
                steps = e
            check(f"{label}: the step log names osxexperts for both", isinstance(steps, list)
                  and [(s["tool"], s["source"], s["exit"]) for s in steps] == [("ffmpeg", "osxexperts.net", 0),
                                                                             ("ffprobe", "osxexperts.net", 0)], steps)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        _p = os.path.join(tmp, "idx", "ffmpeg.zip")
        with zipfile.ZipFile(_p) as z:
            _body = z.read("ffmpeg").decode()
        with zipfile.ZipFile(_p, "w") as z:
            z.writestr("ffmpeg", _body.replace(f"SIGNED-BY-{ARM_TEAM}", ""))
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("an unsigned martin-riedl download moves on to the pinned second source instead of stopping setup",
              rc == 0 and _lines(os.path.join(rec, "DOWNLOADS"))[-2:] == [
                  "https://www.osxexperts.net/ffmpeg9arm.zip", "https://www.osxexperts.net/ffprobe9arm.zip"],
              f"rc={rc} {_lines(os.path.join(rec, 'DOWNLOADS'))} {err}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        env["SERVER_DOWN"] = "martin-riedl.de"
        _p = os.path.join(tmp, "idx", "ffmpeg-oxarm.zip")
        with zipfile.ZipFile(_p) as z:
            _body = z.read("ffmpeg").decode()
        with zipfile.ZipFile(_p, "w") as z:
            z.writestr("ffmpeg", _body.replace("PINNED-ARMOX", "TAMPERED"))
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("the second Apple-chip source is checksum-pinned (fail closed)", rc != 0 and "did not match the exact copy" in err
              and not os.path.exists(os.path.join(env["HOME"], ".local", "bin", "ffmpeg")), f"rc={rc} {err}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        env["SERVER_DOWN"] = ".zip"                # every download site down
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("both Apple-chip sources down: a plain failure, nothing installed", rc != 0
              and "neither Apple-chip source" in err and not os.path.exists(os.path.join(env["HOME"], ".local", "bin", "ffmpeg")),
              f"rc={rc} {err}")

    print("4b. a download that fails its integrity check never reaches her PATH (fail closed)")
    def _rewrite_fixture(tmp, name, old_marker, new_marker):
        path = os.path.join(tmp, "idx", name)
        tool = name.split(".")[0].split("-")[0]
        with zipfile.ZipFile(path) as z:
            body = z.read(tool).decode()
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(tool, body.replace(old_marker, new_marker))
    cases = (
        ("Intel zip that is not the pinned one", "x86_64", "13.4", "ffmpeg-intel.zip", "PINNED-OK", "TAMPERED",
         "did not match the exact copy"),
        ("Apple-chip binary with no signature", "arm64", "13.4", "ffmpeg.zip", f"SIGNED-BY-{ARM_TEAM}", "",
         "not signed by its publisher"),
        ("Apple-chip binary signed by another team", "arm64", "13.4", "ffmpeg.zip", f"SIGNED-BY-{ARM_TEAM}",
         "SIGNED-BY-ABCDE12345", "not signed by its publisher"),
    )
    for label, machine, macos, fixture, old_m, new_m, msg in cases:
        with tempfile.TemporaryDirectory() as tmp:
            eng, env, rec = fake_mac(tmp, machine=machine, hw_arm64="1" if machine == "arm64" else "0", macos=macos)
            _rewrite_fixture(tmp, fixture, old_m, new_m)
            if machine == "x86_64":                # the second Intel source is pinned too: both must refuse
                _rewrite_fixture(tmp, "ffmpeg-ox.zip", "PINNED-OX", "TAMPERED")
            else:                                  # the second Apple-chip source out of reach: the signature is the story
                env["RATE_LIMITED"] = "osxexperts.net"
            rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
            landed = os.path.join(env["HOME"], ".local", "bin", "ffmpeg")
            check(f"{label}: refused with a plain message", rc != 0 and msg in err, f"rc={rc} {out} {err}")
            check(f"{label}: nothing installed", not os.path.exists(landed))
            try:
                with open(os.path.join(eng, "_local", "install-route.json"), encoding="utf-8") as f:
                    steps = json.load(f)["steps"]
            except (OSError, ValueError, KeyError) as e:
                steps = e
            check(f"{label}: the step log records the failure", isinstance(steps, list) and steps
                  and steps[0]["tool"] == "ffmpeg" and steps[0]["exit"] == 1, steps)

    print("5. the checklist and the setup skill tell that Mac the truth")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, machine="arm64", macos="13.4")
        cs = open(os.path.join(ROOT, "check-setup.sh"), encoding="utf-8").read()
        # install_cmd, extracted and run against the simulated Mac, the same function check-setup.sh uses
        start = cs.index("install_cmd() {")
        fn = cs[start:cs.index("\n}\n", start) + 3]
        script = (". scripts/_mac-arch.sh; MACCLASS=$(mac_arch_class); MACROUTE=$(mac_install_route); OS=mac; "
                  "winget_line(){ echo winget; }\n" + fn + "\nfor t in ffmpeg uv node python3 pillow; do install_cmd $t; done")
        rc, out, err = sh(script, env, eng)
        check("no brew line for any tool", rc == 0 and "brew install" not in out and out.count("\n") == 4, f"{out} {err}")
        check("ffmpeg's line is the no-Homebrew installer", "intel-mac-install.sh ffmpeg" in out, out)
    check("check-setup routes on the install route, not the chip", '"$MACROUTE" = direct' in cs and "mac_install_route" in cs)
    sk = open(os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md"), encoding="utf-8").read()
    check("set-me-up asks for the route before handing over Homebrew", "mac_install_route" in sk and "`direct`" in sk)
    d = sk[sk.index("`direct` → an Apple-chip Mac"):]
    d = d[:d.index("- **`rosetta`")] if "- **`rosetta`" in d else d
    check("...and offers updating macOS as an OPTIONAL first choice, with the keep-going route beside it",
          "Offer her the choice FIRST" in d and "Software Update" in d and "Option 2, keep" in d
          and "Never push the update" in d and "intel-mac-install.sh all" in d)
    hook = open(os.path.join(ROOT, ".claude", "hooks", "machine-fingerprint.sh"), encoding="utf-8").read()
    check("the session hook warns Claude on that Mac", "mac_install_route" in hook)

    print("6. the transcriber never builds PyAV from source on a Mac")
    wt = open(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh"), encoding="utf-8").read()
    check("--only-binary av is set on Darwin", 'AV_WHEEL="--only-binary av"' in wt and '= "Darwin" ] && AV_WHEEL' in wt)
    installs = [ln.strip() for ln in wt.splitlines()
                if "uv pip install" in ln and not ln.strip().startswith("#") and ("whisperx" in ln or "faster-whisper" in ln)
                and "torch" not in ln]
    cpu = [ln for ln in installs if "$AV_WHEEL" not in ln]
    # the CUDA (NVIDIA, so never a Mac) installs carry it too: it is empty off a Mac
    check("every Mac-reachable whisper install carries it", len(installs) >= 3 and len(cpu) == 0, installs)

    print("7. the Command Line Tools fallback on a Mac Homebrew supports (2026-10-02)")
    pin_rel = os.path.join(".local", "share", "reels-editing-engine", "mac-route")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="15.1")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("the refusal points at the fallback", rc == 2 and "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all" in out,
              f"rc={rc} {out} {err}")
        env2 = dict(env, MAC_DIRECT_ROUTE="1")
        rc, out, err = sh("bash scripts/intel-mac-install.sh ffmpeg", env2, eng)
        check("MAC_DIRECT_ROUTE=1 installs the Apple-chip builds on 15+", rc == 0 and _lines(os.path.join(rec, "DOWNLOADS")) == [
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip",
            "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip"], f"rc={rc} {err}")
        pin = os.path.join(env["HOME"], pin_rel)
        check("...and pins this Mac (no Homebrew here)", os.path.exists(pin) and _lines(pin)[:1] == ["direct"], _lines(pin))
        got = sh(". scripts/_mac-arch.sh; mac_install_route", env, eng)[1]
        check("later checks, WITHOUT the variable, say direct", got == "direct", got)
        rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, eng)
        check("...so the plain installer runs there afterwards", rc == 0, f"rc={rc} {err}")
        write_exec(os.path.join(env["_MA_SYS_ROOT"], "opt", "homebrew", "bin", "brew"), "#!/bin/sh\nexit 0\n")
        got = sh(". scripts/_mac-arch.sh; mac_install_route", env, eng)[1]
        check("a Homebrew that later works takes the Mac back to brew", got == "brew", got)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="26.6.2")
        write_exec(os.path.join(env["_MA_SYS_ROOT"], "opt", "homebrew", "bin", "brew"), "#!/bin/sh\nexit 0\n")
        rc, out, err = sh("MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("a Mac WITH Homebrew (a developer's test run) is never pinned",
              rc == 0 and not os.path.exists(os.path.join(env["HOME"], pin_rel)), f"rc={rc} {err}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        sh("bash scripts/intel-mac-install.sh ffmpeg", env, eng)
        check("a Mac below 15 is never pinned (it is direct anyway)", not os.path.exists(os.path.join(env["HOME"], pin_rel)))

    print("8. Apple's developer-tool placeholders are recognised, even half-installed")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, _ = fake_mac(tmp, machine="arm64", macos="15.1")
        q = ". scripts/_mac-arch.sh; mac_clt_stub /usr/bin/git && echo STUB || echo REAL"
        check("no tools at all: /usr/bin/git is a placeholder", sh(q, env, eng)[1] == "STUB")
        dev = os.path.join(tmp, "CommandLineTools")
        # a failed install: the folder is configured (xcode-select -p answers, exit 0) but holds nothing
        write_exec(os.path.join(tmp, "fakebin", "xcode-select"), f"#!/bin/sh\necho '{dev}'\n")
        check("configured but empty (the failed-download state): still a placeholder", sh(q, env, eng)[1] == "STUB")
        write_exec(os.path.join(dev, "usr", "bin", "git"), "#!/bin/sh\nexit 0\n")
        check("tools really installed: /usr/bin/git is real", sh(q, env, eng)[1] == "REAL")
        check("a path outside /usr/bin is never a placeholder",
              sh(". scripts/_mac-arch.sh; mac_clt_stub /opt/homebrew/bin/git && echo STUB || echo REAL", env, eng)[1] == "REAL")
        # uv tidies a downloaded Python with install_name_tool, itself one of Apple's placeholders
        q = ". scripts/_mac-arch.sh; mac_clt_shield \"$TMPDIR/sh\""
        rm = os.path.join(dev, "usr", "bin", "git")
        os.remove(rm)
        got = sh(q, env, eng)[1]
        check("no tools: the shield puts a quiet stand-in install_name_tool in front",
              got.endswith("/sh") and os.access(os.path.join(got, "install_name_tool"), os.X_OK), got)
        write_exec(os.path.join(dev, "usr", "bin", "install_name_tool"), "#!/bin/sh\nexit 0\n")
        check("tools installed: no shield, the real one is used", sh(q, env, eng)[1] == "")
    for rel in ("scripts/intel-mac-install.sh", "scripts/ensure-python.sh", ".claude/skills/rough-cut/scripts/word-timings.sh"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        check(f"{rel} shields uv's Python download", "mac_clt_shield" in src)

    print("8b. a quiet git stand-in where git is Apple's placeholder (hyperframes runs git ls-remote)")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="15.1")
        env["MAC_DIRECT_ROUTE"] = "1"
        rc, out, err = sh("bash scripts/intel-mac-install.sh git", env, eng)
        g = os.path.join(env["HOME"], ".local", "bin", "git")
        check("no tools: ~/.local/bin/git is placed", rc == 0 and os.access(g, os.X_OK), f"rc={rc} {err}")
        rc, out, err = sh(f"'{g}' ls-remote https://example.invalid/x.git", env, eng)
        check("...and answers quietly with a failure, never reaching /usr/bin/git", rc == 1 and "not installed" in err, f"rc={rc} {err}")
        dev = os.path.join(tmp, "CLT")
        write_exec(os.path.join(dev, "usr", "bin", "git"), "#!/bin/sh\nexit 0\n")
        write_exec(os.path.join(tmp, "fakebin", "xcode-select"), f"#!/bin/sh\necho '{dev}'\n")
        body = open(g, encoding="utf-8").read()
        check("...and hands over to Apple's git once real tools exist", 'exec /usr/bin/git "$@"' in body)
        rc, out, err = sh("bash scripts/intel-mac-install.sh git", env, eng)
        check("with real tools the step leaves things alone", rc == 0, f"rc={rc} {err}")
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.4")
        g = os.path.join(env["HOME"], ".local", "bin", "git")
        write_exec(g, "#!/bin/sh\necho real-git\n")
        sh("bash scripts/intel-mac-install.sh git", env, eng)
        check("a real git already in ~/.local/bin is never overwritten", open(g, encoding="utf-8").read() == "#!/bin/sh\necho real-git\n")
    check("`all` places it before anything can call git", "install_git_guard || rc=1" in
          open(os.path.join(ROOT, "scripts", "intel-mac-install.sh"), encoding="utf-8").read())

    print("9. no `$name…` in a script: bash 3.2 in a UTF-8 Terminal reads the glyph into the name")
    import glob, re
    bad = []
    for f in glob.glob(os.path.join(ROOT, "scripts", "*.sh")) + [os.path.join(ROOT, "check-setup.sh")] \
             + glob.glob(os.path.join(ROOT, ".claude", "skills", "*", "scripts", "*.sh")):
        for n, ln in enumerate(open(f, encoding="utf-8"), 1):
            if not ln.lstrip().startswith("#") and re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", ln):
                bad.append(f"{os.path.relpath(f, ROOT)}:{n}")
    check("every variable before a non-ASCII glyph is braced", not bad, bad)
    with tempfile.TemporaryDirectory() as tmp:
        eng, env, rec = fake_mac(tmp, machine="arm64", macos="13.7")
        env["LANG"] = env["LC_ALL"] = "en_US.UTF-8"
        rc, out, err = sh("bash scripts/intel-mac-install.sh node", env, eng)
        check("the Node step finishes in a UTF-8 terminal (it died at 'ver?: unbound variable')",
              rc == 0 and "unbound" not in err and "v24.21.0" in out, f"rc={rc} {err}")

    shim = open(os.path.join(ROOT, "scripts", "_python3-shim.sh"), encoding="utf-8").read()
    check("the python3 shim needs python3 IN the developer folder, not just a configured path",
          '[ -x "$_p3_dev/usr/bin/python3" ]' in shim)
    cs = open(os.path.join(ROOT, "check-setup.sh"), encoding="utf-8").read()
    check("check-setup uses the same placeholder test", "mac_clt_stub /usr/bin/python3" in cs)
    check("check-setup names the fallback under the Homebrew line", "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all" in cs)
    check("...and has a pinned-Mac message that does not call her macOS old",
          'mac_os_at_least "$MAC_BREW_OLDEST" 0; then' in cs and "could not be downloaded" in cs)
    cr = open(os.path.join(ROOT, "scripts", "collect-report.sh"), encoding="utf-8").read()
    check("the problem report never runs a placeholder (git --version opened Apple's dialog)",
          '_clt_stub "$_vp" && return 0' in cr and '_clt_stub "$PY" && PY=""' in cr)
    sk = open(os.path.join(ROOT, ".claude", "skills", "set-me-up", "SKILL.md"), encoding="utf-8").read()
    check("set-me-up documents the fallback", "Software Update server" in sk
          and "MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all" in sk and "invalid developer directory" in sk)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails)); sys.exit(1)
    print("all good: an Apple-chip Mac below Homebrew's floor sets up without Homebrew, and nothing else moved")


if __name__ == "__main__":
    main()
