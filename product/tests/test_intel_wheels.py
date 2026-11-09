#!/usr/bin/env python3
"""The Intel-Mac wheel traps in the engine's requirements stay closed after future edits.

Two things are guarded: the VectCutAPI requirements no longer pull in `cryptography` at all, and the
background-music (MusicGen) stack keeps its Intel caps. Both exist for the same reason -- a package
dropped its macOS x86_64 wheel and an Intel Mac then has nothing to install.

WHY: cryptography 49.0.0 dropped its macOS universal2 wheel and now publishes arm64 ONLY. It used to
arrive transitively (oss2 -> aliyun-python-sdk-core -> cryptography), so on an Intel Mac pip fell
through to the sdist and tried to COMPILE it, which needs Rust and Apple's Command Line Tools, and
`setup-editor-engine.sh` died partway through -- reported live by a buyer on an Intel Mac. oss2 was
only there for upstream VectCutAPI's unused Aliyun cloud upload, which has been removed, so the whole
chain is gone. This guard keeps it gone: if oss2 (or anything from that chain) is added back, the
Intel trap reopens. If `cryptography` is ever needed again, it must carry the Intel-only <49 cap.
Offline -- it reads the files and evaluates markers, it installs nothing.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
REQ = os.path.join(ROOT, "product", "engine", "VectCutAPI", "requirements.txt")
LOCK = os.path.join(ROOT, "product", "engine", "VectCutAPI", "requirements-lock.txt")
fails = []


def check(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        fails.append(label)


# packaging is not in a stock python3; pip vendors it. Either is fine, and if neither is importable
# the textual checks below still run rather than the guard reporting a pass it did not make.
Requirement = None
for _mod in ("packaging.requirements", "pip._vendor.packaging.requirements"):
    try:
        Requirement = __import__(_mod, fromlist=["Requirement"]).Requirement
        break
    except Exception:
        continue

INTEL = {"sys_platform": "darwin", "platform_machine": "x86_64"}
SILICON = {"sys_platform": "darwin", "platform_machine": "arm64"}
WINDOWS = {"sys_platform": "win32", "platform_machine": "AMD64"}


def req_names(path):
    out = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.split("#", 1)[0].strip()
        if ln:
            out.append(ln)
    return out


def name_of(line):
    for sep in ("==", ">=", "<=", "~=", "!=", "<", ">", ";", "[", " "):
        line = line.split(sep, 1)[0]
    return line.strip().lower().replace("_", "-")


CHAIN = {"oss2", "aliyun-python-sdk-core", "aliyun-python-sdk-kms"}

lines = req_names(REQ)
names = {name_of(ln) for ln in lines}
check("requirements.txt does not pull in oss2 / the Aliyun SDK (the cryptography chain)",
      not (names & CHAIN))
if os.path.exists(LOCK):
    lock_names = {name_of(ln) for ln in req_names(LOCK)}
    check("requirements-lock.txt does not pin oss2 / the Aliyun SDK either", not (lock_names & CHAIN))
    check("requirements-lock.txt does not pin cryptography (nothing needs it now)",
          "cryptography" not in lock_names)

crypto = [ln for ln in lines if name_of(ln) == "cryptography"]
if crypto:
    # Only acceptable if it is the Intel-gated cap: an ungated or uncapped cryptography reopens the trap.
    line = crypto[0]
    check("a cryptography line, if present, is capped below 49", "<49" in line.replace(" ", ""))
    check("...and gated by a marker", ";" in line)
    if Requirement is not None and ";" in line:
        req = Requirement(line)
        check("...that hits an Intel Mac", req.marker.evaluate(INTEL))
        check("...and leaves Apple Silicon alone", not req.marker.evaluate(SILICON))
        check("...and leaves Windows alone", not req.marker.evaluate(WINDOWS))

if Requirement is None:
    print("\nSKIPPED the marker checks: no packaging module importable (textual checks ran)")
    sys.exit(1 if fails else 0)

# --- the background-music (MusicGen) stack -------------------------------------------------------
# torch's last macOS x86_64 wheel is 2.2.2. transformers 5.x demands torch>=2.5, and numpy 2.x
# breaks torch 2.2.2's ABI. Unpinned, an Intel buyer asking for a music bed gets a FAILED INSTALL,
# not a slow one. Each cap is marker-gated so every other machine stays on current releases.
MUSIC_REQ = os.path.join(ROOT, "product", "requirements-music.txt")

print("\n  -- background music (MusicGen) --")
check("product/requirements-music.txt exists", os.path.exists(MUSIC_REQ))
if os.path.exists(MUSIC_REQ):
    mlines = [ln.split("#", 1)[0].strip() for ln in open(MUSIC_REQ, encoding="utf-8")]
    mlines = [ln for ln in mlines if ln]

    # Each package needs BOTH an Intel-capped line and an uncapped line for everyone else, so the
    # cap can never become a global downgrade and the feature can never vanish off Apple Silicon.
    for name, cap, allowed, blocked in (
        ("torch", "<2.3", "2.2.2", "2.3.0"),
        ("transformers", "<5", "4.56.0", "5.0.0"),
        ("numpy", "<2", "1.26.4", "2.0.0"),
    ):
        pins = [Requirement(ln) for ln in mlines if Requirement(ln).name == name]
        intel = [r for r in pins if r.marker is not None and r.marker.evaluate(INTEL)]
        silicon = [r for r in pins if r.marker is not None and r.marker.evaluate(SILICON)]

        check(f"{name}: an Intel Mac gets exactly one pin", len(intel) == 1)
        check(f"{name}: Apple Silicon gets exactly one, separate line", len(silicon) == 1)
        if len(intel) == 1:
            spec = str(intel[0].specifier).replace(" ", "")
            check(f"{name}: the Intel line is capped {cap}", cap.replace(" ", "") in spec)
            check(f"{name}: {allowed} (has an Intel wheel) is allowed",
                  intel[0].specifier.contains(allowed))
            check(f"{name}: {blocked} (no Intel wheel) is excluded",
                  not intel[0].specifier.contains(blocked))
        if len(silicon) == 1:
            check(f"{name}: Apple Silicon is NOT capped",
                  not str(silicon[0].specifier).strip())

print("\n" + ("FAILED: " + "; ".join(fails) if fails
             else "the Intel wheel pins hold, and only on the machines that need them"))
sys.exit(1 if fails else 0)
