#!/usr/bin/env python3
"""problem_evidence.py — the half of /report-a-problem that looks at what HAPPENED, not what is installed.

    python3 product/problem_evidence.py            # a few seconds: what ran, how far, what is running now
    python3 product/problem_evidence.py --render   # also the renderer's own checks and a timed test render
                                                   # (a few minutes; a 1-second test in a temp folder)
(On Windows: `python`, never `python3`, which can be the Microsoft Store decoy.)

WHY THIS EXISTS. scripts/collect-report.sh was built for setup: versions, paths, which tools are missing.
That answers "is this machine set up?", which is one kind of problem. Most of the others are "it did
something wrong": a render that ran all night, a build that says the engine is down, a finish that never
finished. For those, a list of installed versions comes back clean and says nothing, and a hardware
report says what the computer IS but not what it was DOING. What actually says something is the evidence
the engine leaves behind: how far the last render got and how fast (product/render_log.py), whether
anything is still running, how much memory is free right now, whether the build engine is up, and the
renderer's own health check. This collects that, and collect-report.sh folds it into the one report.

Report-only. Installs nothing, changes nothing, sends nothing, and touches no footage, transcripts or
captions. Only process NAMES are read, never what is in them. Every probe runs on a timer, and anything a
timer stops is stopped with its whole process tree, so a check can never leave a browser running.
Paths inside the engine are shown relative; the home folder becomes ~.
"""
import argparse, glob, importlib.util, json, os, re, signal, socket, subprocess, sys, time

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))
HOME = os.path.expanduser("~")
WIN = os.name == "nt"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LOW_FREE_GB = 2.0      # below this, a render (several browsers at ~256 MB each) is starved
LOW_FREE_PCT = 15


def tilde(s):
    s = s or ""
    return s.replace(HOME, "~") if HOME and HOME != os.sep else s


def rel(p):
    try:
        a = os.path.abspath(p)
        return os.path.relpath(a, ROOT).replace(os.sep, "/") if a.startswith(ROOT + os.sep) else tilde(a)
    except Exception:   # noqa: BLE001
        return tilde(str(p))


def clock(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def kill_tree(p):
    """Stop a process AND everything it started. On Windows p.kill() ends only the top process (often
    `cmd /c npx`), which leaves the render browser running and eating the machine. taskkill /T is the
    tree kill; elsewhere the child runs in its own process group."""
    try:
        if WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=30)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception:   # noqa: BLE001
        try:
            p.kill()
        except Exception:   # noqa: BLE001
            pass


def run(argv, timeout, cwd=None):
    """(status, seconds, output). Never raises, never outlives its timer."""
    t0 = time.time()
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", start_new_session=not WIN)
    except FileNotFoundError:
        return "not found", 0.0, ""
    except Exception as e:   # noqa: BLE001
        return "error", 0.0, str(e)
    try:
        out, _ = p.communicate(timeout=timeout)
        return ("ok" if p.returncode == 0 else f"exit {p.returncode}"), round(time.time() - t0, 1), out or ""
    except subprocess.TimeoutExpired:
        kill_tree(p)
        try:
            out, _ = p.communicate(timeout=20)
        except Exception:   # noqa: BLE001
            out = ""
        return "TIMED OUT", float(timeout), out or ""


def _make_handoff():
    """make-handoff.py already knows how to read the processor on every OS. The hyphen in its name means
    it cannot be imported normally, so load it by path. Its CLI sits behind __main__, so this runs nothing."""
    try:
        spec = importlib.util.spec_from_file_location("make_handoff", os.path.join(ROOT, "product", "make-handoff.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:   # noqa: BLE001
        return None


# ── this computer, right now ─────────────────────────────────────────────────
def memory_now():
    """(total GB, free GB) at this moment, or (None, None). Free means available to a new program."""
    try:
        if WIN:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullTotalPhys / 2 ** 30, m.ullAvailPhys / 2 ** 30
            return None, None
        if sys.platform == "darwin":
            total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                       timeout=10).stdout.strip() or 0) / 2 ** 30
            out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, timeout=20).stdout
            m = re.search(r"free percentage:\s*(\d+)%", out)
            return (total, total * int(m.group(1)) / 100) if total and m else (total or None, None)
        vals = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                k, _, v = line.partition(":")
                vals[k] = int(v.split()[0]) if v.split() else 0
        return vals.get("MemTotal", 0) / 2 ** 20 or None, vals.get("MemAvailable", 0) / 2 ** 20 or None
    except Exception:   # noqa: BLE001
        return None, None


def process_names():
    """What is running, as lower-cased executable names (full paths where the OS gives them). Names only:
    nothing about what any program has open. None when the list could not be read."""
    try:
        if WIN:
            # bytes, then a forgiving decode: tasklist prints in the OEM codepage, never UTF-8
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                                 timeout=30).stdout.decode("utf-8", "replace")
            return [ln.split('","')[0].strip().strip('"').lower() for ln in out.splitlines() if ln.strip()]
        out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, timeout=30).stdout
        return [ln.strip().lower() for ln in out.splitlines() if ln.strip()]
    except Exception:   # noqa: BLE001
        return None


def classify(names):
    """Counts of the processes that matter to a render. The render browser is chrome-headless-shell, which
    is never the Chrome she browses with, so counting it cannot mistake her own windows for a render."""
    base = [os.path.basename(n.replace("\\", "/")) for n in names]
    return {
        "render_browsers": sum(1 for n, b in zip(names, base)
                               if "chrome-headless-shell" in b or "/.cache/hyperframes/" in n),
        "ffmpeg": sum(1 for b in base if b in ("ffmpeg", "ffmpeg.exe")),
        "capcut": any(b in ("capcut", "capcut.exe") for b in base),
    }


def build_engine_up():
    """The CapCut build engine (VectCut) listens on this machine's port 9001. A connection is the whole
    test; nothing is sent to it and nothing leaves the computer."""
    try:
        with socket.create_connection(("127.0.0.1", 9001), timeout=2):
            return True
    except Exception:   # noqa: BLE001
        return False


def section_now():
    L = ["### This computer right now", ""]
    mh = _make_handoff()
    cpu = None
    try:
        cpu = mh._chip_name() if mh else None
    except Exception:   # noqa: BLE001
        pass
    phys = None
    try:
        phys = mh._physical_cores() if mh else None
    except Exception:   # noqa: BLE001
        pass
    cores = f"{phys} physical / {os.cpu_count()} logical" if phys else f"{os.cpu_count()} logical"
    L.append(f"- **Processor:** {cpu or 'could not read'} · {cores} cores")
    total, free = memory_now()
    if total and free is not None:
        pct = round(100 * free / total)
        line = f"- **Memory:** {total:.0f} GB total, {free:.1f} GB free right now ({pct}% free)"
        if free < LOW_FREE_GB or pct < LOW_FREE_PCT:
            line += (". **Low.** A render opens several browsers at once (about 256 MB each), so on this much"
                     " free memory it slows to a crawl. Close CapCut and other apps before rendering")
        L.append(line)
    elif total:
        L.append(f"- **Memory:** {total:.0f} GB total (free memory could not be read)")
    else:
        L.append("- **Memory:** could not read")
    names = process_names()
    if names is None:
        L.append("- **Running now:** could not read the process list")
    else:
        c = classify(names)
        rb = c["render_browsers"]
        line = f"- **Render-browser processes running:** {rb}"
        if rb:
            # One healthy render is several of these (a browser per worker, plus its helpers), so the count
            # alone proves nothing. What matters is whether a render is actually running right now.
            live = False
            try:
                import render_log
                live = any(render_log.verdict(r) == "still running right now" for r in render_log.recent(8))
            except Exception:   # noqa: BLE001
                pass
            line += (" (a render is running right now)" if live else
                     ". No render is recorded as running, so these are probably left over from a render"
                     " that was stopped. They keep using memory and processor until they are closed or"
                     " the computer restarts")
        L.append(line)
        L.append(f"- **ffmpeg running:** {c['ffmpeg']}")
        L.append(f"- **CapCut open:** {'yes' if c['capcut'] else 'no'}")
    L.append("- **Build engine (VectCut, port 9001):** " + (
        "running" if build_engine_up() else
        "not running (normal unless a CapCut draft is being built; start-editor starts it)"))
    try:   # this report runs as `python` on Windows, so the interpreter running it is the one `python` is
        import venv_spawn
        if WIN and venv_spawn.is_store_python():
            L.append("- **Python:** `python` here is the Microsoft Store Python (it cannot see uv's Python in"
                     " AppData; product/venv_spawn.py starts the speech tools around that)")
    except Exception:   # noqa: BLE001
        pass
    return L


# ── what the engine was doing ────────────────────────────────────────────────
def section_renders():
    L = ["### Renders and bakes (newest first)", ""]
    try:
        import render_log
        recs = render_log.recent(8)
        L += render_log.summarize(recs)
    except Exception as e:   # noqa: BLE001
        recs = []
        L.append(f"- could not read the render records ({e})")
    stalls = sorted(glob.glob(os.path.join(ROOT, "_handoff", "render-stall-*.md")),
                    key=os.path.getmtime, reverse=True)[:3]
    for s in stalls:
        got = {}
        try:
            with open(s, encoding="utf-8", errors="replace") as f:
                for line in f:
                    for key in ("last progress seen", "last phase seen"):
                        if line.startswith(f"- {key}:"):
                            got[key] = line.split(":", 1)[1].strip()
        except Exception:   # noqa: BLE001
            pass
        L.append(f"- **Stall report** `{rel(s)}` written {clock(os.path.getmtime(s))}: the renderer went silent"
                 f" at {got.get('last progress seen', '?')} (phase {got.get('last phase seen', '?')})")
    if not recs:
        diags = sorted(glob.glob(os.path.join(ROOT, "projects", "**", ".reel_render", "render-diagnostics.json"),
                                 recursive=True), key=os.path.getmtime, reverse=True)
        if diags:
            try:
                with open(diags[0], encoding="utf-8") as f:
                    d = json.load(f)
                L.append(f"- Last render that ENDED (older record, `{rel(os.path.dirname(os.path.dirname(diags[0])))}`,"
                         f" {clock(os.path.getmtime(diags[0]))}): check {d.get('check_seconds')}s,"
                         f" render {d.get('render_seconds')}s, {'ok' if d.get('ok') else 'did not pass'}")
            except Exception:   # noqa: BLE001
                pass
    if len(L) == 2:
        L.append("- none recorded yet (normal before the first graphics render on this engine version)")
    elif not stalls:
        L.append("- No stall report. Normal: one is only written when the renderer prints nothing for"
                 " 10 minutes, so a render that kept counting frames, however slowly, never writes one")
    return L


def section_rough_cut():
    cands = glob.glob(os.path.join(ROOT, "projects", "*", "transcript", ".transcribe-diagnostics.json"))
    if not cands:
        return []
    newest = max(cands, key=os.path.getmtime)
    try:
        with open(newest, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:   # noqa: BLE001
        return []
    job = os.path.basename(os.path.dirname(os.path.dirname(newest)))
    keep = ("device", "model", "compute_type", "wall_seconds", "total_clip_seconds", "realtime_ratio",
            "is_weak_cpu", "fallback_tiers_that_failed", "detected_languages")
    bits = [f"{k}={d[k]}" for k in keep if k in d and d[k] not in (None, [], "")]
    return ["### Last transcription", "",
            f"- `{job}` ({clock(os.path.getmtime(newest))}): " + (", ".join(bits) or "no details recorded")]


def section_handoff():
    files = [f for f in glob.glob(os.path.join(ROOT, "_handoff", "*")) if os.path.isfile(f)]
    if not files:
        return []
    files.sort(key=os.path.getmtime, reverse=True)
    L = ["### Reports already on this computer (`_handoff/`, newest first)", ""]
    for f in files[:6]:
        L.append(f"- `{os.path.basename(f)}` ({clock(os.path.getmtime(f))}, {max(1, os.path.getsize(f) // 1024)} KB)")
    return L


def section_her_changes():
    """What the last update did with her own changes to the engine (product/keep_changes.py)."""
    doc = os.path.join(ROOT, "_local", "my-changes.md")
    if not os.path.exists(doc):
        return []
    try:
        with open(doc, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    sections = re.split(r"^## ", text, flags=re.M)
    if len(sections) < 2:
        return []
    newest = sections[1]
    head = newest.splitlines()[0].strip()
    counts = {k: (re.search(rf"\*\*{k} \((\d+)\)", newest) or [None, "0"])[1]
              for k in ("Came through the update on their own", "Needs a hand", "No longer part of the engine")}
    return ["### Her changes to the engine (`_local/my-changes.md`)", "",
            f"- Last update: {head}",
            f"- Came through on their own: {counts['Came through the update on their own']} · needs a hand: "
            f"{counts['Needs a hand']} · removed by the update (hers saved): {counts['No longer part of the engine']}"]


def section_update():
    try:
        with open(os.path.join(ROOT, "product.json"), encoding="utf-8") as f:
            ver = json.load(f).get("version")
    except Exception:   # noqa: BLE001
        return []
    if ver and os.path.isdir(os.path.join(ROOT, "_update-backups")) and \
            not os.path.exists(os.path.join(ROOT, "_local", f"post-update-{ver}.ok")):
        return ["### Update", "",
                f"- The update to v{ver} has not run its finishing step yet. Normal right after an update;"
                f" `/update` finishes it"]
    return []


# ── the renderer, tested (only with --render) ────────────────────────────────
def _newest_comp():
    """The composition behind the most recent render: from the render record when there is one (that is
    exactly what ran), else the newest composition that has ever been rendered."""
    try:
        import render_log
        for r in render_log.recent(8):
            if r.get("step") == "graphics render" and r.get("target"):
                p = os.path.join(ROOT, r["target"]) if not r["target"].startswith("~") else \
                    r["target"].replace("~", HOME, 1)
                if os.path.isfile(os.path.join(p, "index.html")):
                    return p
    except Exception:   # noqa: BLE001
        pass
    states = glob.glob(os.path.join(ROOT, "projects", "**", ".reel_render"), recursive=True)
    comps = [os.path.dirname(s) for s in states if os.path.isfile(os.path.join(os.path.dirname(s), "index.html"))]
    return max(comps, key=os.path.getmtime) if comps else None


def _tail(text, n=18):
    lines = [tilde(ANSI.sub("", ln)).rstrip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    return lines[-n:]


def section_render_checks():
    L = ["### Render checks (renderer health, the composition, a timed test render)", ""]
    try:
        from npx_run import hf_version, npx_argv
        hf = hf_version()
    except Exception:   # noqa: BLE001
        hf, npx_argv = "0.9.6", (lambda *x: ["npx", *x])
    comp = _newest_comp()
    if comp:
        st, secs, out = run(npx_argv(f"hyperframes@{hf}", "info", comp), 120)
        L.append(f"- **The last composition** `{rel(comp)}` (HyperFrames `info`, {st}, {secs}s):")
        L += ["```"] + _tail(out, 20) + ["```"]
    else:
        L.append("- **The last composition:** none found to describe")
    print("  running a short timed test render (a few minutes; nothing of hers is touched)…", file=sys.stderr, flush=True)
    t0 = time.time()
    argv = [sys.executable, os.path.join(ROOT, "product", "intel-render-diagnostic.py")]
    if comp:
        argv += ["--comp", comp]
    st, secs, out = run(argv, 1800, cwd=ROOT)
    reps = [p for p in glob.glob(os.path.join(ROOT, "_handoff", "RENDER-DIAGNOSTIC-*.json"))
            if os.path.getmtime(p) >= t0 - 1]
    if not reps:
        L.append(f"- **Test render:** did not produce its report ({st} after {secs}s). Its last words:")
        L += ["```"] + _tail(out, 15) + ["```"]
        return L
    rp = max(reps, key=os.path.getmtime)
    try:
        with open(rp, encoding="utf-8") as f:
            rep = json.load(f)
    except Exception:   # noqa: BLE001
        L.append(f"- **Test render:** report `{rel(rp)}` could not be read")
        return L
    doc = rep.get("hf_doctor") or {}
    L.append(f"- **Renderer health (HyperFrames `doctor`, the lines that matter to a render):**")
    L += ["```"] + doctor_render_lines(doc.get("output")) + ["```"]
    L.append("  (Left out on purpose: HyperFrames extras this engine never uses, like Docker, voice and music,"
             " and its newer-version notice. The engine pins its HyperFrames version; never upgrade it here.)")
    ok = []
    for label, name in (("A_system_font", "plain font"), ("B_pack_font", "style-pack font")):
        pr = (rep.get("probe") or {}).get(label)
        if not pr:
            continue
        r = pr.get("render") or {}
        how = probe_speed(r.get("output"))
        L.append(f"- **Test render, {name}:** {r.get('status')} in {r.get('seconds')}s{how}"
                 f" (a 1-second, 30-frame test composition)")
        ok.append(r.get("status") == "ok")
    if ok and all(ok):
        # The diagnostic's own verdict is written for a Mac that hangs; for everything else, say what a
        # clean test actually rules out.
        L.append("- **What the test says:** the renderer starts and draws on this computer, with a style-pack font"
                 " too, so a render that ran for hours was not the renderer failing to start or a font failing"
                 " to load. A long render normally runs FASTER than this short test (the test's 30 frames include"
                 " warm-up). So if the real render's frames/s in its record above is far BELOW the test's,"
                 " something was slowing it: another render at the same time, leftover processes, low memory. If"
                 " it is about the same or higher, that composition was simply long or heavy for this machine")
    else:
        L.append(f"- **Verdict:** {rep.get('verdict')}")
    L.append(f"- Full test report: `{rel(rp)}`")
    return L


DOCTOR_KEEP = ("node", "cpu", "memory", "disk", "frames cache", "ffmpeg", "ffprobe", "chrome", "browser", "gpu")


def doctor_render_lines(text):
    """HyperFrames doctor, trimmed to what bears on rendering. Its optional extras (Docker, voice, music)
    show a ✗ on every machine that does not use them, which reads as a fault in a report, and its
    'newer version available, run hyperframes upgrade' line invites exactly what this engine forbids."""
    out, keep = [], False
    for raw in (text or "").splitlines():
        ln = tilde(ANSI.sub("", raw)).rstrip()
        m = re.match(r"\s*([✓✗!])\s+(\S.*?)\s{2,}", ln + "  ")
        if m:
            keep = m.group(2).strip().lower().startswith(DOCTOR_KEEP)
            if keep:
                out.append(ln.strip())
        elif keep and ln.strip() and raw.startswith(" "):
            out.append("    " + ln.strip())     # the hint under a kept check
    return out or ["(doctor printed nothing readable)"]


def probe_speed(text):
    """How the test render drew its frames, from HyperFrames' closing summary: hardware vs software
    drawing and the capture time for its 30 frames."""
    m = re.search(r"(hardware|software) gpu · .*?capture ([\d.]+)s", text or "")
    if not m:
        return ""
    gpu, cap = m.group(1), float(m.group(2))
    rate = f", {30 / cap:.1f} frames/s" if cap > 0 else ""
    return f" · {gpu} drawing{rate}" + (" (SOFTWARE: the processor is drawing every frame)" if gpu == "software" else "")


def main():
    ap = argparse.ArgumentParser(description="What the engine was doing, for /report-a-problem. Report-only.")
    ap.add_argument("--render", action="store_true",
                    help="also run the renderer's own checks and a timed test render (a few minutes)")
    a = ap.parse_args()
    out = []
    for fn in (section_now, section_renders, section_rough_cut, section_handoff, section_her_changes, section_update):
        try:
            part = fn()
        except Exception as e:   # noqa: BLE001 — one unreadable section must not hide the others
            part = [f"### {fn.__name__}", "", f"- could not collect ({e})"]
        if part:
            out += part + [""]
    if a.render:
        try:
            out += section_render_checks() + [""]
        except Exception as e:   # noqa: BLE001
            out += ["### Render checks", "", f"- could not run ({e})", ""]
    print("\n".join(out).rstrip())


if __name__ == "__main__":
    main()
