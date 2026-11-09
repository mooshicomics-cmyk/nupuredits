#!/usr/bin/env python3
"""intel-render-diagnostic.py — ONE run that answers "why do rendered captions hang on this Mac?"

    python3 product/intel-render-diagnostic.py            # full run, writes one report to _handoff/
    python3 product/intel-render-diagnostic.py --comp <dir>   # use a specific composition's fonts
    python3 product/intel-render-diagnostic.py --quick        # skip the render probe (checks only)

WHY THIS EXISTS. The graphics renderer bakes kinetic captions by loading each pack font into a headless
Chromium through `@font-face`. On an older Intel Mac that render HANGS with no error and no timeout
(`subprocess.run` in reel_render.py never returns), so nothing is written down and the creator can only
report "it hung". There is no Intel Mac on the seller side, so one buyer run has to carry every fact a
fix needs. That is what this collects.

THE EXPERIMENT (self-validating). Two compositions are rendered, identical except for the font:
    A  system font, no @font-face at all
    B  the same composition with one real pack font loaded via @font-face
A is the control. If A renders and B hangs, the fault is font loading in the renderer and nothing else
(not the machine, not the graphics card, not the composition, not the pack). If A hangs too, the
renderer is not starting at all on this machine, which is a different bug, and the report says so
rather than blaming fonts.

SAFETY. Every subprocess has a hard timeout and runs in its own process group, which is killed on
expiry, so this can never hang the machine the way the real render does. On a hang the stuck process is
sampled first (`/usr/bin/sample`), because that stack is what makes the bug fixable. Nothing is
transmitted: it writes a file and prints the path. The creator reads it and decides whether to send it.
"""
import argparse, glob, json, os, platform, re, shutil, signal, subprocess, sys, time
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))
HOME = os.path.expanduser("~")
REPORT_DIR = os.path.join(ROOT, "_handoff")


def tilde(s):
    """Never collect the account name: $HOME always becomes ~ before anything is written."""
    return (s or "").replace(HOME, "~")


def run(argv, timeout, cwd=None, sample_on_timeout=False):
    """Run argv with a HARD timeout in its own process group. Returns a dict, never raises, never
    leaves the child (or its children) alive. On timeout, optionally sample the process tree first."""
    out = {"argv": [tilde(a) for a in argv], "timeout_s": timeout}
    t0 = time.time()
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", start_new_session=(os.name != "nt"))
    except FileNotFoundError:
        out.update(status="not-found", seconds=0)
        return out
    except Exception as e:                                     # noqa: BLE001
        out.update(status="error", error=str(e), seconds=0)
        return out
    try:
        stdout, _ = p.communicate(timeout=timeout)
        out.update(status="ok" if p.returncode == 0 else "nonzero", exit=p.returncode,
                   seconds=round(time.time() - t0, 1), output=tilde((stdout or "").strip())[-4000:])
    except subprocess.TimeoutExpired:
        out.update(status="HUNG", seconds=timeout)
        if sample_on_timeout and sys.platform == "darwin":
            out["stacks"] = sample_tree(p.pid)
        elif sample_on_timeout:
            out["stacks"] = "stack sampling is macOS only; not collected here"
        try:
            if os.name == "nt":
                # No process groups on Windows, and p.kill() ends only the top process (`cmd /c npx`),
                # which leaves the render browser running and eating the machine. /T takes the whole tree.
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=30)
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:                                      # noqa: BLE001
            p.kill()
        try:
            stdout, _ = p.communicate(timeout=20)
            out["output"] = tilde((stdout or "").strip())[-4000:]
        except Exception:                                      # noqa: BLE001
            out["output"] = "(no output recovered after the hang)"
    return out


def descendants(pid):
    """Every pid under pid, via ps. Pure stdlib; macOS ps has no --forest worth parsing."""
    try:
        raw = subprocess.run(["ps", "-eo", "pid=,ppid=,comm="], capture_output=True, text=True,
                             timeout=20).stdout
    except Exception:                                          # noqa: BLE001
        return []
    kids, names = {}, {}
    for line in raw.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            cpid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        kids.setdefault(ppid, []).append(cpid)
        names[cpid] = parts[2]
    found, stack = [], [pid]
    while stack:
        cur = stack.pop()
        for k in kids.get(cur, []):
            found.append((k, names.get(k, "?")))
            stack.append(k)
    return found


def sample_tree(pid):
    """THE MONEY SHOT. A hang has no error message; its stack is the only evidence of where it is stuck.
    /usr/bin/sample ships with macOS. Sample the renderer process itself and any browser under it."""
    stacks = []
    targets = [(pid, "renderer")] + [d for d in descendants(pid)
                                     if re.search(r"chrome|Chromium|node|helper", d[1], re.I)][:4]
    for tpid, name in targets:
        try:
            r = subprocess.run(["/usr/bin/sample", str(tpid), "3", "-mayDie"],
                               capture_output=True, text=True, timeout=60)
            txt = (r.stdout or "") + (r.stderr or "")
            # The top of the "Call graph" is where it is wedged; the whole dump is far too big to email.
            i = txt.find("Call graph")
            stacks.append({"pid": tpid, "process": name,
                           "stack": tilde(txt[i:i + 6000] if i >= 0 else txt[:3000])})
        except Exception as e:                                 # noqa: BLE001
            stacks.append({"pid": tpid, "process": name, "stack_error": str(e)})
    return stacks


def which_arch(name):
    """A tool's path AND the architecture it was built for. On an Intel Mac an arm64 binary (or the
    reverse) is a whole class of failure that never names itself."""
    path = shutil.which(name)
    if not path:
        return {"present": False}
    info = {"present": True, "path": tilde(path)}
    real = os.path.realpath(path)
    try:
        f = subprocess.run(["file", "-b", real], capture_output=True, text=True, timeout=20).stdout.strip()
        info["file"] = f
        info["arch"] = ("arm64" if "arm64" in f else "x86_64" if "x86_64" in f else
                        "universal" if "universal" in f.lower() else "script/unknown")
    except Exception:                                          # noqa: BLE001
        pass
    for flag in ("--version", "-version"):
        r = run([path, flag], 30)
        if r.get("status") == "ok":
            info["version"] = (r.get("output") or "").splitlines()[0][:120]
            break
    return info


FONT_MAGIC = {b"ttcf": "TrueType COLLECTION (.ttc) — a browser @font-face CANNOT load this",
              b"OTTO": "OpenType/CFF", b"wOFF": "WOFF", b"wOF2": "WOFF2",
              b"\x00\x01\x00\x00": "TrueType", b"true": "TrueType (legacy)"}


def font_facts(path):
    d = {"path": tilde(path), "exists": os.path.exists(path)}
    if not d["exists"]:
        return d
    d["bytes"] = os.path.getsize(path)
    d["ext"] = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
        d["magic"] = head.hex()
        d["format"] = FONT_MAGIC.get(head, "unrecognised")
    except Exception as e:                                     # noqa: BLE001
        d["read_error"] = str(e)
    return d


def probe_font(comp_fonts):
    """A real font file for case B, in order of how faithful it is to her actual failure:
      1. a font from the composition that hung (exactly what the renderer was loading),
      2. a pack font that ships inside the engine (present on every machine, so case B ALWAYS runs),
      3. any font the renderer itself cached.
    Without (2) the experiment silently degraded to the control alone on a machine that had not built a
    composition yet, which is the one outcome that teaches nothing."""
    for f in comp_fonts:
        if os.path.isfile(f):
            return f, "the composition that hung"
    shipped = sorted(glob.glob(os.path.join(ROOT, "product", "creative-vault", "hands-off", "*", "*.ttf")) +
                     glob.glob(os.path.join(ROOT, "product", "creative-vault", "hands-off", "*", "*.otf")))
    if shipped:
        return shipped[0], "a style-pack font shipped with the engine"
    cached = sorted(glob.glob(os.path.join(HOME, ".cache", "hyperframes", "fonts", "*", "*.woff2")))
    if cached:
        return cached[0], "a font cached by the renderer"
    return None, None


def find_comp(explicit):
    """The composition whose fonts we test: the one given, else the newest hf-graphics build."""
    if explicit:
        return explicit if os.path.isdir(explicit) else None
    cands = sorted(glob.glob(os.path.join(ROOT, "projects", "*", "hf-graphics")),
                   key=lambda p: os.path.getmtime(p), reverse=True)
    return cands[0] if cands else None


MIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<style>
%(faces)s
*{margin:0;padding:0;box-sizing:border-box;}
html,body{width:1080px;height:1920px;overflow:hidden;background:transparent;}
#root{position:absolute;inset:0;}
.cap{position:absolute;left:110px;right:110px;top:960px;text-align:center;
     font-family:%(family)s;font-weight:700;font-size:96px;color:#fff;}
</style></head>
<body>
<div id="root" data-composition-id="probe" data-no-timeline data-start="0" data-duration="1" data-width="1080" data-height="1920">
  <div class="clip cap" data-start="0" data-duration="1">probe</div>
</div>
</body></html>
"""


# data-no-timeline (on the root above): the probe has no animation, and without this marker HyperFrames
# polls for a timeline for 45 SECONDS before giving up, on every render. That wait used to be most of what
# this probe measured (a "49s" 1-second render was ~45s of waiting), which made the timing useless as a
# speed reading. HyperFrames' own lint names this fix (missing_data_no_timeline).


def build_probe(dirpath, font_file=None):
    os.makedirs(dirpath, exist_ok=True)
    if font_file:
        os.makedirs(os.path.join(dirpath, "fonts"), exist_ok=True)
        base = "ProbeFont" + (os.path.splitext(font_file)[1] or ".ttf")
        shutil.copy(font_file, os.path.join(dirpath, "fonts", base))
        faces = "@font-face{font-family:'ProbeFont';src:url('fonts/%s');}" % base
        family = "'ProbeFont'"
    else:
        faces, family = "", "Helvetica, Arial, sans-serif"
    with open(os.path.join(dirpath, "index.html"), "w", encoding="utf-8") as f:
        f.write(MIN_HTML % {"faces": faces, "family": family})
    return dirpath


def main():
    ap = argparse.ArgumentParser(description="Collect everything needed to fix a hung caption render.")
    ap.add_argument("--comp", help="composition dir to take a real pack font from")
    ap.add_argument("--quick", action="store_true", help="skip the render probe")
    # A 1-second probe takes ~5s on an Apple Silicon laptop (it measured ~50s before data-no-timeline removed
    # HyperFrames' 45s timeline wait); an older Intel Mac is several times slower,
    # and calling a slow render a "hang" would send the fix in the wrong direction entirely.
    ap.add_argument("--render-timeout", type=int, default=420)
    a = ap.parse_args()

    try:
        from npx_run import hf_version, npx_argv
        HF = hf_version()
    except Exception:                                          # noqa: BLE001
        HF, npx_argv = "0.9.6", lambda *x: ["npx", *x]

    print("Running the render diagnostic. Nothing is sent anywhere; it writes one file at the end.")
    print("This takes a few minutes, and a step that HANGS is the one we most want to catch, so please")
    print("let it run even when it looks stuck. Every step stops itself on a timer.\n")

    rep = {"what": "intel-render-diagnostic", "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "engine_version": None, "hyperframes_pin": HF}
    try:
        rep["engine_version"] = json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("version")
    except Exception:                                          # noqa: BLE001
        pass

    # ── 1. the machine ──────────────────────────────────────────────────────
    print("1/6  the machine")
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:                                      # noqa: BLE001
            return ""
    mac = sys.platform == "darwin"
    chip = ("arm64" if platform.machine() == "arm64" else
            "rosetta" if sysctl("hw.optional.arm64") == "1" else "intel") if mac else platform.machine()
    try:
        du = shutil.disk_usage(ROOT); free_gb = round(du.free / 1e9)
    except Exception:                                          # noqa: BLE001
        free_gb = None
    if mac:
        rep["machine"] = {
            "chip_class": chip, "cpu": sysctl("machdep.cpu.brand_string") or platform.processor(),
            "python_reports_machine": platform.machine(), "os": platform.platform(),
            "macos": sysctl("kern.osproductversion") or None,
            "cores_physical": sysctl("hw.physicalcpu") or None, "cores_logical": sysctl("hw.logicalcpu") or None,
            "ram_gb": round(int(sysctl("hw.memsize") or 0) / 1e9) or None, "free_disk_gb": free_gb,
        }
    else:
        # Not a Mac: sysctl does not exist, so read the processor and memory the way make-handoff.py does
        # on every OS (it cannot be imported by name because of the hyphen, so load it by path).
        cpu_name, ram = None, None
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("make_handoff", os.path.join(ROOT, "product", "make-handoff.py"))
            mh = importlib.util.module_from_spec(spec); spec.loader.exec_module(mh)
            cpu_name, ram = mh._chip_name(), mh._ram_gb()
        except Exception:                                      # noqa: BLE001
            pass
        rep["machine"] = {
            "chip_class": chip, "cpu": cpu_name or platform.processor(), "python_reports_machine": platform.machine(),
            "os": platform.platform(), "cores_logical": os.cpu_count(), "ram_gb": ram, "free_disk_gb": free_gb,
        }
    print(f"     {chip} · {rep['machine']['cpu']} · "
          + (f"macOS {rep['machine']['macos']}" if mac else rep['machine']['os'])
          + f" · {rep['machine']['ram_gb']}GB · {free_gb}GB free")

    # ── 2. the tools, and what architecture each was built for ──────────────
    print("2/6  the tools")
    rep["tools"] = {t: which_arch(t) for t in ("node", "npx", "python3", "ffmpeg")}
    for t, i in rep["tools"].items():
        print(f"     {t:8} {'missing' if not i.get('present') else i.get('arch','?') + '  ' + i.get('version','')[:40]}")

    # ── 3. the render browser: present? right architecture? does it start? ──
    print("3/6  the render browser")
    cache = os.path.join(HOME, ".cache", "hyperframes", "chrome")
    bins = [b for b in (sorted(glob.glob(os.path.join(cache, "**", "chrome-headless-shell"), recursive=True)) +
                        sorted(glob.glob(os.path.join(cache, "**", "chrome-headless-shell.exe"), recursive=True)) +
                        sorted(glob.glob(os.path.join(cache, "**", "Chromium"), recursive=True)))
            if os.path.isfile(b) and os.access(b, os.X_OK)]
    browsers = []
    for b in bins[:4]:
        e = {"path": tilde(b)}
        try:
            e["file"] = subprocess.run(["file", "-b", b], capture_output=True, text=True, timeout=20).stdout.strip()
            e["arch"] = ("arm64" if "arm64" in e["file"] else "x86_64" if "x86_64" in e["file"] else "?")
        except Exception:                                      # noqa: BLE001
            pass
        if mac:
            try:   # a quarantined binary can stall on first launch instead of failing outright
                q = subprocess.run(["xattr", "-p", "com.apple.quarantine", b],
                                   capture_output=True, text=True, timeout=20)
                e["quarantined"] = (q.returncode == 0)
            except Exception:                                  # noqa: BLE001
                pass
        e["starts"] = run([b, "--version"], 60)
        browsers.append(e)
    rep["render_browser"] = {"cache_dir": tilde(cache), "found": len(bins), "binaries": browsers,
                             "expected_for_this_chip": "x86_64" if chip in ("intel", "rosetta") else "arm64"}
    if not bins:
        print("     NONE found — it has never been downloaded on this machine")
    for e in browsers:
        print(f"     {e.get('arch','?')}  starts={e['starts'].get('status')}  {e['path']}")

    # ── 4. the fonts this composition actually loads ────────────────────────
    print("4/6  the fonts")
    comp = find_comp(a.comp)
    fonts = sorted(glob.glob(os.path.join(comp, "fonts", "*"))) if comp else []
    rep["composition"] = {"dir": tilde(comp) if comp else None, "font_count": len(fonts)}
    rep["fonts"] = [font_facts(f) for f in fonts[:12]]
    for f in rep["fonts"]:
        print(f"     {f.get('format','?')}  {f.get('bytes','?')}B  {os.path.basename(f['path'])}")
    if not fonts:
        print("     no composition fonts found — the probe will use a system font only")

    # ── 5. HyperFrames' own report ──────────────────────────────────────────
    print("5/6  the renderer's own report (doctor)")
    rep["hf_doctor"] = run(npx_argv(f"hyperframes@{HF}", "doctor"), 180)
    print(f"     {rep['hf_doctor'].get('status')} in {rep['hf_doctor'].get('seconds')}s")

    # ── 6. THE EXPERIMENT ───────────────────────────────────────────────────
    rep["probe"] = {}
    if a.quick:
        print("6/6  render probe SKIPPED (--quick)")
    else:
        print("6/6  the experiment: the same 1-second composition, system font vs pack font")
        import tempfile
        tmp = tempfile.mkdtemp(prefix="render-probe-")
        pack_font, font_origin = probe_font([f["path"].replace("~", HOME) for f in rep["fonts"]
                                             if f.get("exists")])
        rep["probe_font_origin"] = font_origin
        cases = [("A_system_font", None)]
        if pack_font:
            print(f"     custom font for the test: {os.path.basename(pack_font)} ({font_origin})")
            cases.append(("B_pack_font", pack_font))
        else:
            print("     no font file anywhere on this machine — case B cannot run")
        for label, font in cases:
            d = build_probe(os.path.join(tmp, label), font)
            print(f"     {label}: checking…", flush=True)
            chk = run(npx_argv(f"hyperframes@{HF}", "check", d, "--timeout=20000"), 180)
            print(f"       check {chk.get('status')} ({chk.get('seconds')}s) · rendering…", flush=True)
            import render_lock   # one render at a time on this computer (product/render_lock.py); the check above does not wait
            with render_lock.held("render diagnostic"):
                rnd = run(npx_argv(f"hyperframes@{HF}", "render", d, "--format", "mov",
                                   "--output", os.path.join(d, "out.mov")),
                          a.render_timeout, sample_on_timeout=True)
            print(f"       render {rnd.get('status')} ({rnd.get('seconds')}s)")
            rep["probe"][label] = {"font": tilde(font) if font else "system (no @font-face)",
                                   "check": chk, "render": rnd}
        shutil.rmtree(tmp, ignore_errors=True)

    # ── the verdict ─────────────────────────────────────────────────────────
    A = rep["probe"].get("A_system_font", {}).get("render", {}).get("status")
    B = rep["probe"].get("B_pack_font", {}).get("render", {}).get("status")
    if A == "ok" and B == "HUNG":
        verdict = ("CONFIRMED: font loading in the renderer. The identical composition renders with a "
                   "system font and hangs with a pack font, so the machine, the graphics card and the "
                   "composition are all ruled out.")
    elif A == "HUNG":
        verdict = ("The renderer hangs even with NO custom font, so this is not a font problem. The "
                   "renderer is not running on this machine at all — check the browser architecture above.")
    elif A == "ok" and B == "ok":
        verdict = ("Both rendered here. The hang did not reproduce in a 1-second composition, so it needs "
                   "the real reel: re-run with --comp pointed at the composition that actually hung.")
    elif A == "ok" and B is None:
        verdict = ("The control rendered, but the custom-font case never ran because no font file was "
                   "found. Re-run with --comp pointed at the composition that hung.")
    elif A is None:
        verdict = "Render probe not run (--quick)."
    else:
        verdict = f"Inconclusive: control={A}, pack font={B}. Read the two probe blocks below."
    rep["verdict"] = verdict

    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    jpath = os.path.join(REPORT_DIR, f"RENDER-DIAGNOSTIC-{stamp}.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)

    print("\n" + "=" * 70)
    print(verdict)
    print("=" * 70)
    print(f"\nSaved: {tilde(jpath)}")
    print("Nothing was sent. Type /report-a-problem: Claude reads it, fixes what it can here, and says if the team "
          "needs it.")


if __name__ == "__main__":
    main()
