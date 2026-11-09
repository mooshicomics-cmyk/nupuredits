#!/usr/bin/env python3
"""make-handoff.py — turn a real-machine failure into a support report the buyer can email in.

Used by `scripts/smoke-test.sh` (a failed fresh-Mac validation) and by the `pc-conversion` skill. The whole point:
a report from a real machine is exactly what makes the engine bulletproof, so every major failure becomes a
message to the engine's support inbox instead of a dead end.

HOW IT SENDS: honestly and simply. It writes the report to a local file and shows the buyer the support
email address to send it to (plus a one-click "open my mail app" convenience). THE BUYER sends it — there
is no automatic/background upload, because a reliable auto-send is not something the environment can promise
(sending data out to an endpoint can be flagged or blocked, which would be a false sense of security). The
plain address ALWAYS works: they copy the file into an email to that address from whatever mail they use.

SUPPORT_EMAIL is the engine's support pointer, not brand identity — like the community name, it is kept
whole through packaging (see make-ship.sh protect/restore) so a buyer's report actually reaches the team.

CLI:  python3 make-handoff.py <kind> "<failure>" ["<failure>" ...]  [--log <file>]  [--out <dir>]
"""
import os, sys, glob, json, platform, subprocess, datetime, urllib.parse, shutil
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

SUPPORT_EMAIL = "it@thestartupmom.com"


def _run(*a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _chip_name():
    """Best-effort friendly CPU name, one path per OS, never a raw error string."""
    if sys.platform == "darwin":
        return _run("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor()
    if sys.platform.startswith("win"):
        # Pure stdlib on Windows — no wmic/PowerShell dependency, which may not be on PATH
        # from Git Bash and is slower/flakier than a direct registry read.
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return name.strip()
        except Exception:
            return platform.processor() or "unknown"
    # Linux
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def _ram_gb():
    """Total physical RAM in GB, best-effort, pure stdlib where possible."""
    try:
        if sys.platform == "darwin":
            b = int(_run("sysctl", "-n", "hw.memsize") or 0)
            return round(b / (1024 ** 3), 1) if b else None
        if sys.platform.startswith("win"):
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        # Linux
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 ** 2), 1)
    except Exception:
        pass
    return None


def _gpu_info():
    """NVIDIA GPU name + VRAM if present (any OS); Apple Silicon reports its integrated GPU via
    the chip name already, so an explicit miss there just means 'none' rather than an error."""
    out = _run("nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader")
    if out:
        return out.splitlines()[0].strip()
    if sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64"):
        return "Apple Silicon integrated GPU (see chip)"
    return "none detected"


def _home_forms():
    """The home folder in every spelling a path on this machine can carry, longest first. On a Mac that is
    one. On Windows the same folder shows up as C:\\Users\\your-name (what Python reports, and USERPROFILE),
    C:/Users/your-name, and Git Bash's /c/Users/your-name, and replacing only one of them left the account name in."""
    forms = set()
    for base in (os.path.expanduser("~"), os.environ.get("USERPROFILE") or "", os.environ.get("HOME") or ""):
        if not base or base in ("/", "\\"):
            continue
        forms.add(base)
        forms.add(base.replace("\\", "/"))
        if len(base) > 2 and base[1] == ":" and base[0].isalpha():
            forms.add("/" + base[0].lower() + base[2:].replace("\\", "/"))
    return sorted((f for f in forms if f not in ("", "/")), key=len, reverse=True)


def _redact(path):
    """Home directory out, "~" in. This report is scoped to hardware and performance only, and a
    raw path carries the person's account name. Tool LOCATIONS still matter (they say which install
    route a machine actually took), so redact rather than drop."""
    if not path:
        return path
    for home in _home_forms():
        path = path.replace(home, "~")
    return path


def _mac_arch_class():
    """arm64 | rosetta | intel — the three Macs that need three different setup routes.

    Homebrew's installer now aborts unless `uname -m` is arm64, so this is no longer a curiosity:
    it decides whether a machine could install anything at all. `uname -m` alone cannot tell an
    Intel Mac from an Apple Silicon Mac running translated (both say x86_64), and those two want
    opposite advice — one unticks a checkbox, the other takes a whole different route.
    hw.optional.arm64 reports the real HARDWARE regardless of translation; it is absent on a true
    Intel Mac. Same discrimination _mac-arch.sh does for the shell side."""
    if sys.platform != "darwin":
        return None
    if platform.machine() in ("arm64", "aarch64"):
        return "arm64"
    return "rosetta" if _run("sysctl", "-n", "hw.optional.arm64") == "1" else "intel"


def _physical_cores():
    """PHYSICAL cores, which is not what os.cpu_count() answers.

    This matters more than it looks. The engine's weak-machine test was `os.cpu_count() <= 4`, and
    os.cpu_count() counts hyperthreads: a 1.4 GHz quad-core i5 (the 2019 13" MacBook Pro, our first
    confirmed Intel buyer) reports 8, sails past the test, and gets handed a model its chip cannot
    carry. Report both numbers so that threshold can be tuned against real machines instead of
    guessed at again."""
    try:
        if sys.platform == "darwin":
            return int(_run("sysctl", "-n", "hw.physicalcpu") or 0) or None
        if sys.platform.startswith("linux"):
            import re
            txt = open("/proc/cpuinfo", encoding="utf-8").read()
            ids = set(re.findall(r"core id\s*:\s*(\d+)", txt))
            return len(ids) or None
    except Exception:
        pass
    return None


def _tool_origins():
    """Where each prerequisite actually resolves from, redacted.

    On a Mac this is the single most informative line in the whole report. /opt/homebrew means
    Apple Silicon Homebrew, /usr/local means Intel-era Homebrew, ~/.local/bin means the
    no-Homebrew Intel route, and a blank means the tool is missing or not on PATH in this shell —
    which is itself the most common "it didn't work" on a fresh machine."""
    out = {}
    for tool in ("ffmpeg", "ffprobe", "node", "npx", "uv", "python3"):
        try:
            out[tool] = _redact(shutil.which(tool) or "")
        except Exception:
            out[tool] = ""
    return out


def install_route():
    """How this machine got its tools. Written by the installer when one ran; inferred from where
    the tools actually live when it did not (an older install, or a hand-installed machine).
    Inference is labelled as inference — a guess presented as a record is worse than no record."""
    try:
        with open(os.path.join("_local", "install-route.json"), encoding="utf-8") as f:
            data = json.load(f)
        data["_source"] = "recorded by the installer"
        return data
    except Exception:
        pass
    origins = _tool_origins()
    if not any(origins.values()):
        return None
    def _where(pth):
        if not pth:
            return "missing"
        if pth.startswith("~/.local/bin"):
            return "intel-route (no Homebrew)"
        if pth.startswith("/opt/homebrew"):
            return "homebrew (Apple Silicon)"
        if pth.startswith("/usr/local"):
            return "homebrew or pkg (/usr/local)"
        return "system"
    return {"_source": "inferred from tool locations, not recorded",
            "by_tool": {k: _where(v) for k, v in origins.items()}}


def system_info():
    disk_free_gb = None
    try:
        disk_free_gb = round(shutil.disk_usage(".").free / (1024 ** 3), 1)
    except Exception:
        pass
    return {
        "when": datetime.datetime.now().isoformat(timespec="seconds"),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "mac_arch_class": _mac_arch_class(),      # arm64 | rosetta | intel — decides the setup route
        "macos_version": _run("sw_vers", "-productVersion") if sys.platform == "darwin" else None,
        "mac_model": _run("sysctl", "-n", "hw.model"),
        "chip": _chip_name(),
        "cpu_logical_cores": os.cpu_count(),
        "cpu_physical_cores": _physical_cores(),
        "ram_gb": _ram_gb(),
        "gpu": _gpu_info(),
        "free_disk_gb": disk_free_gb,
        "python": platform.python_version(),
        "ffmpeg": (_run("ffmpeg", "-version").splitlines() or [""])[0],
        "ffprobe": (_run("ffprobe", "-version").splitlines() or [""])[0],
        "node": _run("node", "-v"),
        "uv": _run("uv", "--version"),
        "tool_origins": _tool_origins(),
        "install_route": install_route(),
    }


def latest_transcribe_diagnostics():
    """Real observed WhisperX device/model/timing from the most recently transcribed job, if any
    — the part of a hardware report that's actually diagnostic (specs alone don't say how slow
    a machine really was). Best-effort: no jobs yet, or the field's missing, is a normal outcome."""
    candidates = glob.glob("projects/*/transcript/.transcribe-diagnostics.json")
    if not candidates:
        return None
    newest = max(candidates, key=os.path.getmtime)
    try:
        with open(newest, encoding="utf-8") as f:
            data = json.load(f)
        data["_from_job"] = os.path.basename(os.path.dirname(os.path.dirname(newest)))
        return data
    except Exception:
        return None


def latest_render_diagnostics():
    """Real observed HyperFrames check/render timing from the most recently rendered composition,
    if any — same flywheel as the transcribe one, for the SEPARATE graphics-render step (browser
    frame capture, not ML inference — a different cost shape, so it needs its own real data rather
    than assuming the transcribe numbers say anything about it)."""
    candidates = glob.glob("projects/**/.reel_render/render-diagnostics.json", recursive=True)
    if not candidates:
        return None
    newest = max(candidates, key=os.path.getmtime)
    try:
        with open(newest, encoding="utf-8") as f:
            data = json.load(f)
        # variable-depth path (projects/<job>/hf-graphics/compositions/<name>/.reel_render/...) —
        # pull the job name out by position relative to "projects", not a fixed dirname() depth.
        parts = os.path.normpath(newest).split(os.sep)
        if "projects" in parts:
            i = parts.index("projects")
            if i + 1 < len(parts):
                data["_from_job"] = parts[i + 1]
        return data
    except Exception:
        return None


def build_report(kind, failures, extra=None, log_text=None, out_dir="_handoff"):
    """Write the report and return (path, mailto_url). failures = list[str].

    kind == "hardware-diagnostic" is a DIFFERENT thing from every other kind here: nothing failed,
    the buyer (or beta tester) chose to run this to help diagnose device-performance issues.
    Scoped ON PURPOSE to hardware + observed performance only — never content, files, or anything
    about the person — and it ends the same way every handoff does: written to a local file,
    nothing auto-sent, the human decides whether to email it.
    """
    os.makedirs(out_dir, exist_ok=True)
    is_diagnostic = (kind == "hardware-diagnostic")
    info = system_info()
    transcribe_diag = latest_transcribe_diagnostics() if is_diagnostic else None
    render_diag = latest_render_diagnostics() if is_diagnostic else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(out_dir, f"HANDOFF-{kind}-{stamp}.md")

    if is_diagnostic:
        L = [f"# Hardware diagnostic report", "",
             "Voluntary — you chose to run this. It's hardware and performance information only: no",
             "content, no files, nothing about you beyond your machine's specs and how fast a rough cut",
             "ran on it. It stays on your computer as a file; you decide whether to email it in.", "",
             "## Why this helps",
             "The engine automatically picks a lighter/faster setup on older or GPU-less machines, but",
             "that threshold is a starting guess. Real numbers from real machines are what let it get",
             "tuned correctly instead of staying a guess.", "",
             "## Machine"]
    else:
        L = [f"# {kind} handoff report", "",
             "A check failed on a real machine. Emailing this to the engine team is exactly what turns a one-off",
             "into a permanent fix, so thank you. Nothing here is private beyond your machine specs.", "",
             "## What failed"]
        L += [f"- {f}" for f in failures]
        L += ["", "## Machine"]
    L += [f"- **{k}:** {v}" for k, v in info.items()]
    if transcribe_diag:
        job = transcribe_diag.pop("_from_job", "")
        L += ["", f"## Most recent rough cut ({job})" if job else "## Most recent rough cut"]
        L += [f"- **{k}:** {v}" for k, v in transcribe_diag.items()]
    if render_diag:
        job = render_diag.pop("_from_job", "")
        L += ["", f"## Most recent graphics render ({job})" if job else "## Most recent graphics render"]
        L += [f"- **{k}:** {v}" for k, v in render_diag.items()]
    if extra:
        L += ["", "## Details"] + [f"- **{k}:** {v}" for k, v in extra.items()]
    if log_text:
        L += ["", "## Log tail", "```", _redact(log_text.strip()[-4000:]), "```"]
    report = "\n".join(L) + "\n"
    open(path, "w", encoding="utf-8").write(report)

    subject = ("[hardware-diagnostic] Reels Editing Engine — machine report"
               if is_diagnostic else f"[{kind}] Reels Editing Engine issue")
    short = "Voluntary hardware diagnostic — see attached." if is_diagnostic else "\n".join(failures)
    body = (report if len(report) < 1400
            else f"{short}\n\nFull report is attached from: {path}\n(Please attach that file when you send this.)")
    mailto = f"mailto:{SUPPORT_EMAIL}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
    return path, mailto


def announce(path, mailto, is_diagnostic=False):
    print("")
    print("  ────────────────────────────────────────────────────────")
    if is_diagnostic:
        print("  Report written. Nothing has been sent, and nothing is wrong with your setup. It stays")
        print(f"  on your computer:  {path}")
    else:
        print(f"  Something didn't check out. A report is saved here:  {path}")
        print("  Type /report-a-problem: Claude fixes what it can on your computer first. It goes to the")
        print(f"  team at {SUPPORT_EMAIL} only if Claude says it is ready to send.")
    print("  ────────────────────────────────────────────────────────")


if __name__ == "__main__":
    args = sys.argv[1:]
    out_dir = "_handoff"
    log_text = None
    if "--out" in args:
        i = args.index("--out"); out_dir = args[i + 1]; del args[i:i + 2]
    if "--log" in args:
        i = args.index("--log"); lp = args[i + 1]; del args[i:i + 2]
        try:
            log_text = open(lp, encoding="utf-8").read()
        except Exception:
            log_text = None
    kind = args[0] if args else "smoke-test"
    failures = args[1:] or (["voluntary diagnostic"] if kind == "hardware-diagnostic" else ["(unspecified failure)"])
    p, m = build_report(kind, failures, log_text=log_text, out_dir=out_dir)
    announce(p, m, is_diagnostic=(kind == "hardware-diagnostic"))
