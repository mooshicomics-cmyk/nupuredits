#!/usr/bin/env python3
"""render-check.py — ONE run that says why the graphics renderer cannot load its page on this Mac.

    python3 product/render-check.py            # full run, about 10-20 minutes on an older Intel Mac
    python3 product/render-check.py --quick    # machine facts + browser tests only, skips the renders

WHY THIS EXISTS (2026-10-03). On some Intel Macs every HyperFrames render stops with "Navigation timeout"
at page.goto, even a 1-second plain-text composition, while chrome-headless-shell started by hand works.
So the browser starts, and the page never finishes loading. HyperFrames (measured on 0.8.43, the same in 0.8.158) has two things in that path
that a particular Mac can trip over, and this tells them apart:

  GPU      on a Mac it can launch Chrome on the Metal graphics path. An older or dual-graphics GPU can
           stall there. PRODUCER_BROWSER_GPU_MODE=software makes Chrome draw on the processor instead.
  LOOPBACK its page server listens on 127.0.0.1 but hands Chrome the name `localhost`. A VPN, proxy,
           content filter or security tool can break the name while the number still works. A browser
           wrapper with --host-resolver-rules="MAP localhost 127.0.0.1" takes the name out of it.

THE EXPERIMENT. The same 1-second system-font composition is rendered four ways: as normal, software
drawing, the localhost wrapper, and both. Before that, the bare browser loads one tiny local page by
number and by name, with no GPU flags, Metal flags and software flags. Whichever variants work name the
cause and the fix.

SAFETY. Report-only: installs nothing, changes no setting, touches no footage, brand kit or project, needs
no password and sends nothing anywhere. Everything runs in a temp folder with a hard timeout in its own
process group, so a stuck step is killed rather than left running. Home paths become ~ in the report.
"""
import argparse, http.server, os, platform, re, shutil, signal, socket, subprocess, sys
import tempfile, threading, time

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))
HOME = os.path.expanduser("~")
REPORT = os.path.join(ROOT, "_handoff", "render-check-report.md")
MARK = "render-check-page-loaded"

# What HyperFrames passes for each drawing mode (read from 0.8.43's cli.js; unchanged in 0.8.158) on a Mac (getBrowserGpuArgs in its cli.js).
GPU_FLAGS = {
    "no GPU flags": [],
    "Metal (hardware)": ["--use-gl=angle", "--use-angle=metal", "--enable-gpu-rasterization",
                         "--ignore-gpu-blocklist", "--enable-unsafe-webgpu"],
    "software": ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
}


def tilde(s):
    return (s or "").replace(HOME, "~")


def run(argv, timeout, env=None, cwd=None):
    """Hard timeout, own process group, killed whole on expiry. Never raises."""
    out = {"seconds": 0}
    t0 = time.time()
    try:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", start_new_session=True)
    except FileNotFoundError:
        return {"status": "not-found", "seconds": 0, "output": ""}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "seconds": 0, "output": str(e)}
    try:
        so, _ = p.communicate(timeout=timeout)
        out.update(status="ok" if p.returncode == 0 else f"exit {p.returncode}", output=so or "")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            p.kill()
        so, _ = p.communicate()
        out.update(status=f"TIMED OUT after {timeout}s", output=so or "")
    out["seconds"] = round(time.time() - t0, 1)
    out["output"] = tilde(out["output"])
    return out


def sh(cmd, timeout=60):
    return run(["/bin/sh", "-c", cmd], timeout).get("output", "").strip()


def tail(text, n=12):
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return "\n".join(lines[-n:]) or "(no output)"


# ── 1. the machine ─────────────────────────────────────────────────────────────────────────────────
def machine():
    hw = sh("system_profiler SPHardwareDataType SPDisplaysDataType 2>/dev/null", 90)
    keep = re.compile(r"^\s*(Model Name|Model Identifier|Processor Name|Chip|Memory|Chipset Model|Type|Bus|"
                      r"VRAM.*|Metal.*|Vendor|Automatic Graphics Switching|gpu-switching.*):", re.I)
    picked = [l.strip() for l in hw.splitlines() if keep.match(l) and "Serial" not in l and "UUID" not in l]
    engine = "?"
    try:
        import json
        engine = json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("version", "?")
    except Exception:  # noqa: BLE001
        pass
    return {
        "macOS": sh("sw_vers -productVersion"),
        "kernel arch (uname -m)": platform.machine(),
        "this Python under Rosetta": sh("sysctl -n sysctl.proc_translated 2>/dev/null") or "n/a",
        "node": sh("node -p 'process.version + \" \" + process.arch' 2>/dev/null") or "not found",
        "engine version": engine,
        "hardware": picked,
    }


# ── 2. anything that can get between Chrome and a local page ───────────────────────────────────────
def network():
    proxy = [l.strip() for l in sh("scutil --proxy").splitlines()
             if re.search(r"Enable|ProxyAutoConfig|Exceptions|Proxy\s*:|Port", l)]
    envp = sorted(k for k in os.environ if "proxy" in k.lower())
    ext = [l.strip() for l in sh("systemextensionsctl list 2>/dev/null").splitlines()
           if re.search(r"\[activated|enabled", l)]
    hosts = [l.strip() for l in open("/etc/hosts", encoding="utf-8", errors="replace")
             if l.strip() and not l.lstrip().startswith("#")] if os.path.exists("/etc/hosts") else []
    return {
        "system proxy settings": proxy or ["(none)"],
        "proxy variables set in this terminal": envp or ["(none)"],
        "active system extensions (VPN, filters, security tools show here)": ext or ["(none)"],
        "/etc/hosts": hosts or ["(empty)"],
        "localhost resolves to": sh("dscacheutil -q host -a name localhost | grep address") or "(nothing)",
    }


# ── 3. the render browser ──────────────────────────────────────────────────────────────────────────
# Found, and wrapped, by product/render_browser.py: reel_render.py retries a render whose page did not load
# with the same localhost wrapper this experiment proves, so both share the one helper.
from render_browser import find_browser, write_localhost_wrapper  # noqa: E402


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(folder):
    """A tiny page server bound the way HyperFrames binds its own: 127.0.0.1 only."""
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><title>t</title><p id=m>{MARK}</p>")
    handler = lambda *a, **k: _Quiet(*a, directory=folder, **k)  # noqa: E731
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def browser_tests(browser, tmp):
    srv = serve(tmp)
    port = srv.server_address[1]
    rows = []
    for host in ("127.0.0.1", "localhost"):
        for label, flags in GPU_FLAGS.items():
            r = run([browser, "--headless", "--no-sandbox", "--no-first-run", *flags,
                     f"--user-data-dir={os.path.join(tmp, 'profile-' + host + '-' + str(len(rows)))}",
                     "--dump-dom", f"http://{host}:{port}/"], 45)
            ok = MARK in r.get("output", "")
            rows.append((host, label, "loaded" if ok else r["status"] if r["status"] != "ok" else "no page",
                         r["seconds"]))
            print(f"     {host:9}  {label:17} {'loaded' if ok else 'FAILED'}  ({r['seconds']}s)", flush=True)
    srv.shutdown()
    return rows


# ── 4. the real renderer, four ways ────────────────────────────────────────────────────────────────
def renders(browser, tmp, timeout):
    try:
        from npx_run import hf_version, npx_argv
        hf = hf_version()
    except Exception:  # noqa: BLE001
        hf, npx_argv = "0.9.6", (lambda *x: ["npx", *x])
    try:
        from importlib import util
        spec = util.spec_from_file_location("ird", os.path.join(ROOT, "product", "intel-render-diagnostic.py"))
        ird = util.module_from_spec(spec)
        spec.loader.exec_module(ird)
        build_probe = ird.build_probe
    except Exception as e:  # noqa: BLE001
        return hf, [("all", f"could not build the test composition: {e}", 0, "")]

    wrapper = write_localhost_wrapper(tmp, browser)
    if not wrapper:
        return hf, [("all", "could not write the localhost wrapper into the temp folder", 0, "")]

    variants = [
        ("1. as normal", {}),
        ("2. software drawing", {"PRODUCER_BROWSER_GPU_MODE": "software"}),
        ("3. localhost wrapper", {"HYPERFRAMES_BROWSER_PATH": wrapper}),
        ("4. software + wrapper", {"PRODUCER_BROWSER_GPU_MODE": "software", "HYPERFRAMES_BROWSER_PATH": wrapper}),
    ]
    rows = []
    for label, extra in variants:
        d = build_probe(os.path.join(tmp, "comp-" + label.split(".")[0]))
        env = dict(os.environ, **extra)
        print(f"     {label}: rendering (up to {timeout}s)…", flush=True)
        import render_lock   # one render at a time on this computer (product/render_lock.py); the timeout starts once it is ours
        with render_lock.held("render check"):
            r = run(npx_argv(f"hyperframes@{hf}", "render", d, "--format", "mov", "--output",
                             os.path.join(d, "out.mov")), timeout, env=env)
        made = os.path.exists(os.path.join(d, "out.mov")) and os.path.getsize(os.path.join(d, "out.mov")) > 0
        status = "RENDERED" if (made and r["status"] == "ok") else r["status"]
        gpu = re.findall(r"browserGpuMode[^\n]*", r.get("output", ""))
        rows.append((label, status, r["seconds"], tail(r.get("output"), 8) + ("\n" + gpu[0] if gpu else "")))
        print(f"       {status} ({r['seconds']}s)", flush=True)
    return hf, rows


def verdict(btests, rrows):
    ok = {label: status == "RENDERED" for label, status, *_ in rrows}
    normal, soft, wrap, both = (ok.get(k, False) for k in
                                ("1. as normal", "2. software drawing", "3. localhost wrapper", "4. software + wrapper"))
    b = {(h, l): s == "loaded" for h, l, s, _ in btests}
    if not rrows:
        return "Render tests skipped (--quick)."
    if normal:
        return ("RENDERS NOW. The normal render worked on this run, so this Mac is compatible as it stands. "
                "If her reels still fail, the problem is in a specific reel, not the renderer.")
    if soft and wrap:
        return ("COMPATIBLE, fix known: either software drawing OR the localhost wrapper works on its own. "
                "Prefer the localhost wrapper (keeps the faster GPU path).")
    if soft:
        return ("COMPATIBLE, cause = GPU. Chrome's Metal graphics path stalls on this Mac. Fix: render with "
                "PRODUCER_BROWSER_GPU_MODE=software on this machine (slower, but it renders).")
    if wrap:
        return ("COMPATIBLE, cause = LOOPBACK. Something on this Mac breaks the name `localhost` for Chrome "
                "(see network section: VPN, proxy, filter). Fix: the localhost wrapper via HYPERFRAMES_BROWSER_PATH, "
                "or turn that tool off while rendering.")
    if both:
        return ("COMPATIBLE, cause = BOTH. It renders only with software drawing AND the localhost wrapper. "
                "Fix: both settings on this machine.")
    if b and not any(b.values()):
        return ("NOT COMPATIBLE as it is set up: the render browser cannot load even a one-line page from this "
                "Mac itself, by number or by name. Something on the machine (see the network section) blocks "
                "local connections for it. The renderer cannot work until that is allowed or removed.")
    return ("UNRESOLVED: none of the four renders worked although the bare browser can load a local page. "
            "Send this whole report; the render output below shows where it stops.")


def main():
    ap = argparse.ArgumentParser(description="Why the graphics renderer cannot load its page on this Mac.")
    ap.add_argument("--quick", action="store_true", help="skip the four renders")
    ap.add_argument("--render-timeout", type=int, default=240)
    a = ap.parse_args()
    if sys.platform != "darwin":
        sys.exit("render-check is for Macs.")
    print("Render check: report-only, sends nothing, changes nothing. Every step stops itself on a timer,")
    print("so a step that looks stuck is fine. Let it finish.\n")

    print("1/4  this Mac", flush=True)
    m = machine()
    print("2/4  network settings that can block a local page", flush=True)
    n = network()
    browser = find_browser()
    tmp = tempfile.mkdtemp(prefix="render-check-")
    btests, rrows, hf, bfile = [], [], "?", "not found"
    try:
        print("3/4  the render browser loading a local page", flush=True)
        if browser:
            bfile = tilde(sh(f'file "{browser}"')) + "\n" + sh(f'"{browser}" --version 2>/dev/null', 30)
            btests = browser_tests(browser, tmp)
        else:
            print("     render browser not found (it downloads on the first render)")
        if a.quick or not browser:
            print("4/4  renders SKIPPED")
        else:
            print("4/4  the real renderer, four ways (the slow part)", flush=True)
            hf, rrows = renders(browser, tmp, a.render_timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    v = verdict(btests, rrows)
    L = ["# Render check report", "", f"_{time.strftime('%Y-%m-%d %H:%M')} · HyperFrames {hf}_", "",
         "## Verdict", "", v, "", "## This Mac", ""]
    for k, val in m.items():
        if isinstance(val, list):
            L += [f"- **{k}:**"] + [f"  - {x}" for x in val]
        else:
            L.append(f"- **{k}:** {val}")
    L += ["", "## Network (anything between Chrome and a local page)", ""]
    for k, val in n.items():
        L += [f"- **{k}:**"] + [f"  - {x}" for x in (val if isinstance(val, list) else [val])]
    L += ["", "## Render browser", "", "```", tilde(browser) if browser else "not found", bfile, "```", ""]
    if btests:
        L += ["## Bare browser loading a one-line local page", "", "| address | drawing | result | seconds |",
              "|---|---|---|---|"] + [f"| {h} | {l} | {s} | {t} |" for h, l, s, t in btests] + [""]
    if rrows:
        L += ["## The real renderer, 1-second test, four ways", "", "| variant | result | seconds |", "|---|---|---|"]
        L += [f"| {lbl} | {st} | {sec} |" for lbl, st, sec, _ in rrows] + [""]
        for lbl, st, sec, out in rrows:
            L += [f"<details><summary>{lbl} output</summary>", "", "```", out, "```", "</details>", ""]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"\nVERDICT: {v}\n\nReport saved: {tilde(REPORT)}")


if __name__ == "__main__":
    main()
