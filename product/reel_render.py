#!/usr/bin/env python3
"""reel_render.py — the ONE way to render a composition: GATED + CACHED + incremental.

  render    <comp_dir | index.html> -o out.mov [--strict] [--force]
      1) hashes the composition's source files; if unchanged since the last CLEAN render and the output still
         exists, SKIPS both the check and the render (instant no-op, says so).
      2) otherwise runs HyperFrames' native `check --at-transitions --frame-check` and REFUSES to render on
         errors. The gate is ENFORCED here, not advisory. --strict also fails on warnings — use it for any
         composition where every word must read (a transcript animation, captions).
      3) renders (mov = transparent overlay) and records the hash so the next identical run is a no-op.
         A caption layer whose builder left a render plan (render-spans.json, product/render_spans.py) is
         rendered only where it is on screen, one time-shifted copy per stretch, stitched back into the same
         full-length file with <out>.spans.json beside it; anything off falls back to the full render.
         REEL_FULL_RENDER=1 always renders full length.

  composite --base <footage> [--layers a.mov b.mov ...] [--audio x.mp3] -o final.mp4
      the cheap ffmpeg stack: base + transparent layers in order (+ optional audio track). Change ONE layer →
      re-render only that layer (cached by `render`) and re-run this (~15s). Never re-render the whole reel.

WHY (measured on a 30s 1080x1920 composition): check ≈ 40s, render ≈ 60s, and neither `-q draft` nor
`--gpu` changes that (the cost is frame CAPTURE). The only real speedups are to not repeat work that hasn't
changed, and to never re-render a full reel to change one layer. This wrapper makes both the default, and
makes the gate impossible to skip on the way to a render.
"""
import argparse, hashlib, json, os, platform, subprocess, sys, time
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame; frame.adopt()   # a wide composition measures against the wide frame
from npx_run import npx_argv, hf_check_argv, hf_check_env, hf_version, run_hf_check, offline_env
import npx_run as _npx_run
from npx_run import _fb as _fallbacks   # fallbacks.py's note / remember / remembered, or no-ops without it
from video_grade import grade_filter   # optional footage grade for `composite --grade`; never applied unasked
from video_encoder import pick_encoder, graph_args, remove_graph  # NVENC on a Windows GPU box; libx264 kept on Mac for this quality path
import render_spans   # caption layers render only where they are on screen, back into one full-length file
import render_browser   # the localhost wrapper around the render browser (ISS-77), shared with render-check.py


def _npx_path_here():
    """Where `npx` is, or None when Node is missing. npx.cmd on Windows: `cmd /c npx` runs that, and `cmd`
    itself always exists, so a missing npx never raises there."""
    import shutil
    return shutil.which("npx.cmd" if os.name == "nt" else "npx")


# Shared with reel_gate.py through npx_run, so a missing Node reads the same wherever it surfaces. An
# npx_run.py from before these two existed gets the same check and the same words from here.
npx_path = getattr(_npx_run, "npx_path", _npx_path_here)
NO_NODE = getattr(_npx_run, "NO_NODE",
                  "Node is not installed on this computer, or this terminal was opened before it was installed "
                  "(a new install stays invisible until the terminal is closed and opened again). HyperFrames runs "
                  "on Node's `npx` command. Close the terminal and open a new one, then run this again; if it is "
                  "still missing, run ./check-setup.sh, which prints the install command for this machine.")


def _sz_box():
    """The safe box as a string, read from product/safe_zones.py — the numbers were hardcoded into two
    messages here and went stale the moment the band changed."""
    try:
        import safe_zones as SZ
        return f"x {SZ.LEFT}..{SZ.RIGHT}, y {SZ.TOP}..{SZ.BOTTOM}"
    except Exception:
        return "the safe zone in product/safe_zones.py"


def _write_render_diagnostics(d, *, cached, check_seconds=None, render_seconds=None,
                               fmt=None, ok=None):
    """Real observed render timing on THIS machine — same 'get real data, don't guess' flywheel
    as .transcribe-diagnostics.json. Written into the composition's own .reel_render/ state dir
    (already exists for the render cache; no new folder convention needed). The hardware-diagnostic
    report (product/make-handoff.py) reads this alongside the transcribe one, best-effort — a
    write failure here must never fail a real render."""
    try:
        diag = {
            "cached": cached, "check_seconds": check_seconds, "render_seconds": render_seconds,
            "format": fmt, "ok": ok, "cpu_logical_cores": os.cpu_count(),
            "platform": sys.platform, "machine": platform.machine(),
        }
        path = os.path.join(d, STATE_DIR, "render-diagnostics.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(diag, f, indent=2)
    except Exception:
        pass

STALL_SECONDS = int(os.environ.get("REELS_RENDER_STALL_SECONDS", "600") or 0)


def _stall_human(seconds):
    """'12 minutes' / '45 seconds'. The default threshold is 10 minutes, but a shorter one set by hand
    must not print '0 minutes', which reads like a bug in the thing reporting the bug."""
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{seconds // 60} minutes"


def _stall_descendants(pid):
    """Every process under pid, depth-first. The renderer itself is node; the work is in the browser
    it spawns, and that is the tree worth sampling."""
    out = []
    try:
        kids = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, timeout=10).stdout.split()
    except Exception:   # noqa: BLE001
        return out
    for k in kids:
        try:
            out.append(int(k)); out.extend(_stall_descendants(int(k)))
        except ValueError:
            pass
    return out


def _write_stall_report(pid, quiet_for, last_frame, last_phase, argv):
    """Write down what a hang used to destroy. Never raises: a stall report that fails must not also
    take down the render it is reporting on."""
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "_handoff", f"render-stall-{stamp}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        home = os.path.expanduser("~")
        lines = [
            "# Render stall report",
            "",
            f"Written {time.strftime('%Y-%m-%d %H:%M:%S')} because the renderer stopped producing output",
            f"for {_stall_human(quiet_for)}. **The render was NOT stopped** and may still finish.",
            "",
            f"- last progress seen: {last_frame or 'none — it never started producing frames'}",
            f"- last phase seen: {last_phase or 'unknown'}",
            f"- command: {' '.join(argv).replace(home, '~')}",
            "",
        ]
        machine = os.path.join(root, "_local", "machine.txt")
        if os.path.exists(machine):
            lines += ["## This machine", "", "```", open(machine, encoding="utf-8", errors="replace").read().strip(), "```", ""]
        if sys.platform == "darwin" and os.path.exists("/usr/bin/sample"):
            lines += ["## Where it is stuck", ""]
            for target in [pid] + _stall_descendants(pid)[:4]:
                try:
                    s = subprocess.run(["/usr/bin/sample", str(target), "2", "-mayDie"],
                                       capture_output=True, text=True, timeout=90).stdout
                except Exception as e:   # noqa: BLE001
                    s = f"(could not sample {target}: {e})"
                lines += [f"### pid {target}", "", "```", (s or "").replace(home, "~")[:20000].strip(), "```", ""]
        else:
            lines += ["## Where it is stuck", "", "(stack sampling is macOS only; not collected here)", ""]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path
    except Exception:   # noqa: BLE001
        return None


# HyperFrames from 0.8.152 ends every render with a line advertising its own desktop app. The toolkit is never named
# to her (CLAUDE.md), so that line is the one thing kept out of the render's output; everything else passes
# through as the renderer wrote it, progress bars (\r) included.
import re
_PROMO = re.compile(rb"Keep editing by chatting with Framey|hyperframes\.dev/studio")
_PROMO_START = b"Keep editing by chatting with Framey"


def _without_promo(buf):
    """(bytes to show now, the unfinished line held back). Whole lines (ended by \n or \r) go out at once, except
    the renderer's ad; the unfinished tail waits for its end so the ad can never slip out in pieces."""
    out, start = [], 0
    for m in re.finditer(rb"[^\r\n]*[\r\n]", buf):
        if not _PROMO.search(m.group(0)):
            out.append(m.group(0))
        start = m.end()
    rest = buf[start:]
    # an unfinished line that cannot be the start of the ad goes out now, so nothing else waits for a line end
    head = rest.lstrip()
    if head and not (_PROMO_START.startswith(head[:len(_PROMO_START)]) or _PROMO.search(rest)):
        out.append(rest); rest = b""
    return b"".join(out), rest


# ── A macOS too old for the graphics renderer ────────────────────────────────────────────────────────────
# HyperFrames draws every frame in a headless Chrome. The one 0.8.43 pinned needs macOS 13: on macOS 12.7.6 it
# aborted at launch (dyld "Symbol not found" in VideoToolbox), so no graphics render could run below 13. Since
# 0.8.158, HyperFrames installs Chrome 150 by itself when the Mac's kernel is older than macOS 13's (Darwin
# < 22), and that build should start there. Nobody here has a macOS 12 Mac to prove it, so this stays as the
# net: when a render (or its check) on macOS 12 or older dies the way that crash looks, she hears it in one
# plain line with the CapCut route that works on any Mac, and this computer remembers it with its macOS version
# and the pin, so the next render says it at once instead of trying for minutes. A macOS update, or a new pin,
# forgets it and the renderer is simply tried again.
OS_UNSUPPORTED_KEY = "render.os-unsupported"
OLDEST_RENDER_MACOS = 13
# A line that can only be the browser failing to load against this macOS: the dynamic loader's own words, or
# the macOS 13 VideoToolbox symbol HyperFrames itself looks for (its macosOldChromeCrash check).
_OS_CRASH_LINE = re.compile(r"[^\r\n]*(?:Symbol not found|dyld\[\d*\]|dyld:|_kVTCompressionPropertyKey)[^\r\n]*",
                            re.I)
# Weaker signs, read only together with an old macOS: the browser would not start, or the process aborted.
_OS_LAUNCH_FAIL = re.compile(r"Failed to launch the browser process", re.I)
_ABORT_CODES = {134, -6}   # SIGABRT, as a shell reports it (128 + 6) and as Python reports a signalled child
# The page the render captures did not load (ISS-77): puppeteer's own "Navigation timeout of N ms exceeded", or
# Chrome refusing the connection to the render page's server. With the check already passed (it loads its page
# by number), the usual cause is the name `localhost` being broken on this computer, which the localhost wrapper
# (product/render_browser.py) takes out of it. Kept as a flag, because the stack trace after it can push the
# line out of the tail that is kept. Not the renderer's plain "page.goto start ... timeoutMs=60000" log line: HyperFrames
# release 0.9.5 repeats it in the failure summary of a render stopped by a failed page script, and that page loaded.
_NAV_FAIL = re.compile(r"Navigation timeout|navigation timed out|page\.goto(?! start)[^\r\n]*(?:timeout(?!Ms)|timed out)"
                       r"|net::ERR_(?:CONNECTION_REFUSED|CONNECTION_RESET|CONNECTION_CLOSED|PROXY_CONNECTION_FAILED"
                       r"|NAME_NOT_RESOLVED|TIMED_OUT|ADDRESS_UNREACHABLE)", re.I)
_LAST_RENDER = {"text": "", "marks": "", "nav": False}


def _macos_version():
    """This Mac's macOS version ("12.7.6"), or None when this is not a Mac. sw_vers is the true answer;
    Python's own platform.mac_ver() is the fallback (an old Python build can report 10.16 on a newer macOS)."""
    if sys.platform != "darwin":
        return None
    try:
        v = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True,
                           timeout=10).stdout.strip()
    except Exception:   # noqa: BLE001
        v = ""
    return v or platform.mac_ver()[0] or None


def _old_macos():
    """The macOS version when this is a Mac older than OLDEST_RENDER_MACOS, else None."""
    v = _macos_version()
    try:
        return v if int(str(v).split(".")[0]) < OLDEST_RENDER_MACOS else None
    except (TypeError, ValueError):
        return None


def _os_crash(rc, text, definite_only=False):
    """Does this failure look like the renderer's browser dying at launch against the macOS? Only ever asked
    on a Mac older than 13. definite_only: the loader's own line only, the one sign no retry can change."""
    text = text or ""
    if _OS_CRASH_LINE.search(text):
        return True
    return not definite_only and (rc in _ABORT_CODES or bool(_OS_LAUNCH_FAIL.search(text)))


def _os_unsupported_known():
    """The macOS version when this computer already learned its macOS cannot run the renderer, else None.
    A different macOS (an update) or a different HyperFrames pin forgets it, so the renderer is tried again."""
    fb = _fallbacks()
    got = fb.remembered(OS_UNSUPPORTED_KEY)
    if not got:
        return None
    mac, hf = (got.get("macos"), got.get("hyperframes")) if isinstance(got, dict) else (str(got), HF_VERSION)
    now = _macos_version()
    if mac and now == mac and hf == HF_VERSION:
        return now
    forget = getattr(fb, "forget", None)
    if forget:
        forget(OS_UNSUPPORTED_KEY)
    return None


def _os_unsupported_stop(d, ver, *, learned=False, check_seconds=None, render_seconds=None, fmt=None):
    """Say it once, plainly, with the route that works; log it and remember it for this computer. Exit 4:
    nothing could run here, and nothing says the composition is wrong."""
    print(f"\n  This Mac's macOS ({ver}) can't run the graphics renderer, so no graphics can render on it. Your "
          f"reel can still finish as an editable CapCut draft: say \"keep it raw\".")
    fb = _fallbacks()
    if learned:
        print("  (Learned on an earlier render here. After a macOS update the renderer is tried again by itself.)")
        fb.note("render", f"macOS {ver} cannot run the graphics renderer (learned earlier); pointed at the CapCut "
                          f"route (keep it raw) without trying")
    else:
        fb.note("render", f"the graphics renderer's browser aborted at launch on macOS {ver} (hyperframes@"
                          f"{HF_VERSION}); pointed at the CapCut route (keep it raw)")
        fb.remember(OS_UNSUPPORTED_KEY, {"macos": ver, "hyperframes": HF_VERSION},
                    why=f"the graphics renderer's browser aborted at launch on macOS {ver}")
    _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, render_seconds=render_seconds,
                              fmt=fmt, ok=False)
    return 4


def _keep_render_words(tail):
    """Keep what the running render last said, for cmd_render to read if it fails. The tail is short and moves
    on; a browser that died at launch on an old macOS says so once, then a stack trace and advice follow it, so
    the telling line itself is kept as well (see _os_crash)."""
    text = tail.decode("utf-8", "replace")
    _LAST_RENDER["text"] = text
    if _NAV_FAIL.search(text):
        _LAST_RENDER["nav"] = True
    for ln in _OS_CRASH_LINE.findall(text):
        if ln not in _LAST_RENDER["marks"]:
            _LAST_RENDER["marks"] = (_LAST_RENDER["marks"] + ln + "\n")[-2000:]


def _run_render_watched(argv, comp_dir=None, env=None):
    """Run the renderer, pass its output straight through, and notice if it goes silent.

    WHY THIS IS NOT A TIMEOUT. A long clip can legitimately render for a very long time, and that is
    truest on exactly the slow machines the caption hang lives on, so a deadline would abort real work.
    This never imposes one and never kills anything. What it does is notice silence.

    WHY IT READS THE STREAM. Measured 2026-09-22 on a real render: NOTHING changes on disk while a
    render runs. No frame directory appears, the renderer's cache does not move, and the output file
    does not grow — it appears complete only at the end. A filesystem watchdog would call every healthy
    render stuck. The renderer's stdout is the only continuous progress signal ("Streaming frame 13/55",
    plus [Render:trace] lines carrying framesCompleted/totalFrames/phase), so that is what is watched.

    Output is captured and written straight back out in raw chunks, never line by line, so the progress
    bar (which redraws with \\r and no newline) still animates exactly as before.

    Set REELS_RENDER_STALL_SECONDS=0 to turn the watcher off and run bare.

    THE TRAIL. Everything this watches also goes into a record in _local/render-log/ (product/render_log.py),
    rewritten every few seconds, so a render that is cancelled after running all night still says how far
    it got, how fast, and whether it froze or crawled. The timing file above is only written when a render
    ENDS; this is the part that survives a render that never does. /report-a-problem reads it.
    """
    import re, threading
    try:
        from render_log import Trail
        _shape = _comp_shape(comp_dir) if comp_dir else None   # its size feeds the next render's time estimate
        trail = Trail("graphics render", comp_dir, size=_shape[1:] if _shape else None)
    except Exception:   # noqa: BLE001 — the record is evidence, never a reason to fail a render
        trail = None

    def _close(result):
        if trail:
            trail.finish(result)

    _LAST_RENDER["text"] = _LAST_RENDER["marks"] = ""   # what THIS render said; read by cmd_render on a failure
    _LAST_RENDER["nav"] = False
    if STALL_SECONDS <= 0:
        # The switch turns off the stall watcher, nothing else. The output still passes through chunk by chunk
        # (only the renderer's own ad is held back, as on the watched path), and the last of it is kept, so a
        # failure here is read the same way.
        try:
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, env=env)
            tail = b""
            shown = b""
            while True:
                chunk = p.stdout.read(1024)
                if not chunk:
                    break
                out, shown = _without_promo(shown + chunk)
                sys.stdout.buffer.write(out); sys.stdout.buffer.flush()
                tail = (tail + chunk)[-4096:]
                _keep_render_words(tail)
            if shown and not _PROMO.search(shown):
                sys.stdout.buffer.write(shown); sys.stdout.buffer.flush()
            rc = p.wait()
        except KeyboardInterrupt:
            _close("stopped")
            raise
        _close("ok" if rc == 0 else f"failed (exit {rc})")
        return rc

    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, env=env)
    state = {"last": time.monotonic(), "frame": "", "phase": "", "fired": False}

    def watch():
        while p.poll() is None:
            time.sleep(15)
            quiet = int(time.monotonic() - state["last"])
            if state["fired"] or quiet < STALL_SECONDS or p.poll() is not None:
                continue
            state["fired"] = True
            if trail:
                trail.stalled(quiet)
            where = state["frame"] or "before the first frame"
            print(f"\n  ⏳ the renderer has not said anything for {_stall_human(quiet)}, stopped at {where}.",
                  flush=True)
            print("     Still waiting — a long clip on an older machine can take a while and nothing has been "
                  "stopped.", flush=True)
            path = _write_stall_report(p.pid, quiet, state["frame"], state["phase"], argv)
            if path:
                print(f"     Wrote what it is doing to {os.path.relpath(path)}. If this never finishes, type "
                      f"/report-a-problem and I'll take it from there.", flush=True)

    threading.Thread(target=watch, daemon=True).start()

    tail = b""
    shown = b""   # the part of the current line not yet written: the renderer's own ad is held back by the line
    try:
        while True:
            chunk = p.stdout.read(1024)
            if not chunk:
                break
            out, shown = _without_promo(shown + chunk)
            sys.stdout.buffer.write(out); sys.stdout.buffer.flush()
            state["last"] = time.monotonic()
            tail = (tail + chunk)[-4096:]
            try:
                text = tail.decode("utf-8", "replace")
            except Exception:   # noqa: BLE001
                continue
            _keep_render_words(tail)
            done = total = None
            m = None
            for m in re.finditer(r"(?:Streaming|Capturing|Rendering) frame (\d+)/(\d+)", text):
                pass
            if m:
                state["frame"] = f"frame {m.group(1)} of {m.group(2)}"
                done, total = int(m.group(1)), int(m.group(2))
            else:   # the [Render:trace] lines carry the same count as JSON
                fc = re.findall(r'"framesCompleted"\s*:\s*(\d+)', text)
                tf = re.findall(r'"totalFrames"\s*:\s*(\d+)', text)
                if fc and tf:
                    done, total = int(fc[-1]), int(tf[-1])
                    state["frame"] = f"frame {done} of {total}"
            m = None
            for m in re.finditer(r'"phase"\s*:\s*"([^"]+)"', text):
                pass
            if m:
                state["phase"] = m.group(1)
            if trail:
                trail.output(done, total, state["phase"])
                # HOW it is rendering, in the renderer's own words. "software" drawing and a worker count
                # cut to 1 are the two facts that turn a minutes-long render into an hours-long one.
                # Wording taken from HyperFrames itself: "browserGpuMode probe → hardware|software (...)"
                # early on, and the closing summary "<mode> capture · hardware|software gpu · <stages>".
                g = re.findall(r"browserGpuMode probe\W+(hardware|software)", text)
                w = re.findall(r'"workerCount"\s*:\s*(\d+)', text)
                st = re.findall(r"(?:\w+ capture · )?(hardware|software) gpu · ([^\r\n]+)", text)
                trail.facts(gpu=g[-1] if g else (st[-1][0] if st else None),
                            workers=int(w[-1]) if w else None,
                            stages=re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", st[-1][1]).strip() if st else None)
        if shown and not _PROMO.search(shown):
            sys.stdout.buffer.write(shown); sys.stdout.buffer.flush()
        rc = p.wait()
    except KeyboardInterrupt:
        _close("stopped")
        raise
    _close("ok" if rc == 0 else f"failed (exit {rc})")
    return rc


HF_VERSION = hf_version()   # single source: product.json "hyperframes"
RENDER_EXT = (".mov", ".mp4", ".webm", ".gif", ".png", ".jpg", ".jpeg", ".mp3", ".wav", ".m4a", ".DS_Store")
STATE_DIR = ".reel_render"


def _comp_shape(d):
    """(frames, width, height) of the composition in d, read from its root (data-duration, data-fps, data-width,
    data-height), or None when it cannot be read. Only for the time estimate and the render log: never a gate."""
    import re
    try:
        with open(os.path.join(d, "index.html"), encoding="utf-8", errors="ignore") as fh:
            html = fh.read()
        tag = re.search(r"<[^>]*\bdata-composition-id=[^>]*>", html)
        if not tag:
            return None
        def attr(name):
            m = re.search(r"\b" + name + r"=[\"']([^\"']*)[\"']", tag.group(0))
            return m.group(1) if m else None
        dur = float(attr("data-duration"))
        fps = float(attr("data-fps") or render_spans.FPS)
        w, h = int(float(attr("data-width") or 1080)), int(float(attr("data-height") or 1920))
        return render_spans.frames_for(dur, fps), w, h
    except Exception:   # noqa: BLE001
        return None


def _say_estimate(d, spans=None, cached=False):
    """The one line before a render: about how long on this computer, and that it is free (render_log.estimate,
    from this computer's own past renders). Says nothing when the composition's length cannot be read."""
    try:
        import render_log
        if cached:
            print(f"  {render_log.estimate_line(cached=True)}", flush=True)
            return
        shape = _comp_shape(d)
        if not shape:
            return
        frames, w, h = shape
        renders = 1
        if spans:
            frames, renders = sum(b - a for a, b in spans), len(spans)
        print(f"  {render_log.estimate_line(frames, w, h, renders=renders)}", flush=True)
    except Exception:   # noqa: BLE001 — a time estimate is never a reason to stop a render
        pass


def comp_dir_of(target):
    """`hyperframes check/render` read <dir>/index.html — accept a dir OR an index.html and normalize."""
    t = os.path.abspath(target)
    if os.path.isfile(t) or (not os.path.isdir(t) and t.endswith(".html")):
        t = os.path.dirname(t)
    return t


def comp_hash(d, extra="", skip=None):
    """Content hash of EVERY file in the composition dir (fonts, images, audio, video assets included — any of
    them changing must invalidate the cache) + the HF version. Excluded: the state dir and the output file
    itself (so a render written into the dir cannot invalidate its own cache in a loop)."""
    h = hashlib.sha256(f"hf={HF_VERSION}|{extra}".encode())
    skip = os.path.abspath(skip) if skip else None
    for root, dirs, files in os.walk(d):
        # skip the cache, deps, and a renders/ subdir (outputs by convention): hashing our own outputs would make
        # every render change the hash and re-render forever. Everything else — fonts, images, audio, clips — counts.
        # .hyperframes/ is the check's own working folder (HyperFrames from 0.8.152 writes a fresh record into it on
        # every check), so hashing it would make every render look new.
        dirs[:] = sorted(x for x in dirs if x not in (STATE_DIR, "node_modules", "renders", ".hyperframes"))
        for f in sorted(files):
            p = os.path.join(root, f)
            if f == ".DS_Store" or (skip and os.path.abspath(p) == skip):
                continue
            h.update(os.path.relpath(p, d).encode()); h.update(b"\0")
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def _state_path(d): return os.path.join(d, STATE_DIR, "state.json")
def _load(d):
    try: return json.load(open(_state_path(d), encoding="utf-8"))
    except Exception: return {}
def _save(d, st):
    os.makedirs(os.path.join(d, STATE_DIR), exist_ok=True)
    json.dump(st, open(_state_path(d), "w", encoding="utf-8"), indent=1)


def _out_stamp(out):
    """The rendered file's size and time, kept with its cache record, so a reuse can tell the file is still the one this
    composition wrote. {} when it cannot be read (the record then stands as before)."""
    try:
        st = os.stat(out)
        return {"out_size": st.st_size, "out_mtime": st.st_mtime}
    except OSError:
        return {}


def _out_rewritten(d, prev, out):
    """True when the file a clean record points at was written by something else since: two compositions can render
    to the same file (one reel built in two style packs renders both to renders/<job>.type.mov), and a record keyed
    by this composition alone handed back the OTHER one's titles. Then it renders again, said in one line.

    A record with the file's size and time compares them; an older record (written before they were kept) holds
    while the file is no newer than this composition's own state file, which is saved right after its render."""
    try:
        if prev.get("out_mtime") is not None:
            now = os.stat(out)
            changed = now.st_size != prev.get("out_size") or abs(now.st_mtime - float(prev["out_mtime"])) > 0.001
        else:
            changed = os.path.getmtime(out) > os.path.getmtime(_state_path(d)) + 2
    except (OSError, TypeError, ValueError):
        return False
    if changed:
        try:
            shown = os.path.relpath(out)
        except ValueError:                                   # Windows: another drive than the one it runs from
            shown = out
        print(f"  {shown} was written by another render since this composition's clean render, so it renders again.")
    return changed


_NOISE_KINDS = {  # editor-tooling hints the check emits per clip; safe to ignore for a render (never a defect)
    "studio_missing_editable_id": "editor hint, safe",
    "timeline_track_too_dense": "style hint, safe",
    "composition_file_too_large": "style hint, safe",
    "nested_structure_needs_subcomposition": "editor hint, safe",
    # 0.8.19x's craft pass judges a composition as a whole film; a layer of a reel is not one
    "line_unread": "a whole film's closing-line hold, safe for a layer",
    "first_frame_empty": "a layer that enters after its first frame, safe",
}

def _summarize_check(text):
    """A 90s reel emits ~240 warnings, ~236 of them the same per-clip editor hint — a real contrast/overlap/
    overflow item drowns in that. Collapse warnings by kind and surface every ✗ (contrast fail, overlap,
    overflow) as a REVIEW line so the signal is visible in one glance."""
    import re, collections
    kinds = collections.Counter(re.findall(r"^\s*⚠ ([a-z_]+):", text, flags=re.M))
    flags = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("✗")]
    if kinds:
        parts = [f"{n} {k}" + (f" ({_NOISE_KINDS[k]})" if k in _NOISE_KINDS else "") for k, n in kinds.most_common()]
        print("[gate summary] warnings by kind: " + " · ".join(parts))
    # The transition-sample cap (npx_run.hf_check_max_transition_samples) is how a caption-heavy layer's check
    # finishes in time. HyperFrames marks the moments it left out with ⚠; that is the cap working, said plainly.
    m = re.search(r"(\d+) transition sample\(s\) omitted", text or "")
    if m:
        print(f"[gate summary] the check sampled an even spread of this layer's transitions and left out {m.group(1)} "
              f"(the cap that keeps a check on a busy caption layer inside its time; nothing is wrong)")
    if flags:
        print(f"[gate summary] ⚠ REVIEW — {len(flags)} flagged item(s) (contrast / overlap / overflow):")
        for ln in flags[:8]:
            print("    " + ln)
        if len(flags) > 8:
            print(f"    … and {len(flags) - 8} more (see the full check output above)")


def _dead_animation_targets(text):
    """Selectors an animation drives that match NOTHING in the DOM, pulled from HyperFrames' own check output.

    HyperFrames reports these, correctly, as runtime console warnings ("GSAP target <sel> not found"). Warnings
    do not fail a check unless --strict is passed, and that is right for most of them. This one is different:
    a selector that resolves to zero elements is never what anybody meant. The animation simply does not run,
    the render succeeds, the video is watchable, and the effect is just missing. A real build shipped a
    word-by-word caption highlight that never fired and cost about a dozen seven-minute render cycles before a
    human watching the output noticed, because nothing on the way there treated it as a fault.

    So this promotes that ONE warning class to a refusal. It reads HyperFrames' own finding rather than
    re-deriving it -- nothing here parses the composition or reimplements a check.

    Returns the distinct selector strings, best-effort; an unnamed target is reported as "(unnamed target)"."""
    import re
    out, seen = [], set()
    for sel in re.findall(r"GSAP target (.*?) not found", text):
        sel = sel.strip() or "(unnamed target)"
        if sel not in seen:
            seen.add(sel); out.append(sel)
    return out


HOLD_S = 0.1   # how long text must sit past the frame edge, unmoved, to stop a render (see _offframe_text)


def _offframe_text(text):
    """Text that stays past the edge of the video, pulled from HyperFrames' own check output.

    HyperFrames reports it as a `canvas_overflow` WARNING, and warnings pass without --strict, so a word cut off
    at the frame edge rendered and shipped with nothing but a line in the terminal. It is never the intent: a
    word meant to hang off the edge carries data-layout-allow-overflow, which HyperFrames already honours, and
    a word only sliding through the edge as it animates in is reported as ℹ, not ⚠. So, like a dead animation
    target, the ⚠ kind is promoted to a refusal. Nothing here measures anything; it reads HyperFrames' finding.

    One more filter, from a survey of 106 real compositions: HyperFrames also merges the two samples it takes
    at the instant an animation ends (0.01s apart) into a ⚠ range, so a panel sliding out of frame on purpose
    reads like a stuck word. Only a range at least HOLD_S long counts: text sitting past the edge, unmoved, for
    longer than a frame. That is still shorter than any caption word stays on screen.

    The sample times come two ways: a range (`t=0.1-8.53s (51 samples)`, HyperFrames up to 0.8.151) or every
    sample listed (`t=0.1, 0.15, 0.2, …, 9s`, from 0.8.152). Either way the hold is first to last.

    Returns [(seconds, selector, direction, px, word)], one per element, the furthest it goes out."""
    import re
    worst = {}
    for times, sel, direction, px, word in re.findall(
            r"^\s*⚠ t=([\d.]+(?:(?:-|, )[\d.]+)*)s[^\n]*?canvas_overflow (\S+) [^\n]*?overflowed (\w+) ([\d.]+)px[^\"\n]*\"([^\"]*)\"",
            text, flags=re.M):
        ts = [float(x) for x in re.split(r"-|, ", times)]
        t0, t1 = ts[0], ts[-1]
        if t1 - t0 < HOLD_S:
            continue
        t, px = t0, float(px)
        if px > worst.get(sel, (0, 0, "", 0.0))[3]:
            worst[sel] = (float(t), sel, direction, px, word)
    return sorted(worst.values())


def _offframe_message(items):
    """The plain explanation printed when off-frame text stops a render."""
    lines = [f"\n  ⛔ {len(items)} piece(s) of text run off the edge of the video — REFUSING to render. "
             f"They would come out cut off:"]
    for t, _sel, direction, px, word in items[:8]:
        lines.append(f"       \"{word}\" at {t:.1f}s, {round(px)}px past the {direction} edge")
    if len(items) > 8:
        lines.append(f"       … and {len(items) - 8} more")
    lines.append("     Make it fit: shorten the line, let it wrap, or bring the size down. Meant to hang off the "
                 "edge? Mark that element data-layout-allow-overflow. To render it anyway: REEL_ALLOW_OFFFRAME_TEXT=1.")
    return "\n".join(lines)


def _safe_zone_check(out):
    """LAYER 2 on the FINAL ARTIFACT. `hyperframes check` validates the composition against the CANVAS; it has
    no concept of Instagram's UI safe zone (product/safe_zones.py) — a caption sitting inside the bottom UI band
    passes it (measured: a lower-third at y=1559 passed with 0 errors). So after a transparent render, read the
    alpha plane in ONE native ffmpeg pass and take each frame's SOLID-ink bbox (alpha >= 128; a drop-shadow spill
    is not a key visual); assert it sits inside the safe zone. Full-bleed frames (ink >= 90% of the frame) are
    designed backgrounds, not overlays, and are skipped.
    Measurer notes (validated against a hand-measured card: x 70..1009, y 1295..1559): the ProRes 4444 alpha
    plane is 12-bit, so it is forced to 8-bit gray before thresholding; and ffmpeg's cropdetect judges a row/column
    by its AVERAGE, not its max, so the alpha is binarized at 128 FIRST and cropdetect runs at limit=1 on the
    binary mask (a sparse column of real ink still averages > 1; a transparent frame reports YMAX=0 and an
    inverted bbox, both ignored).
    Returns (status, breaches): status "ok" = measured; "fullbleed" = solid ink in frames, but only full-frame
    ones (a takeover or designed card that owns the screen), so there is nothing to hold to the bands; "empty" =
    no solid ink in ANY frame (a fully transparent overlay is usually a broken render, never silently "clean");
    "skipped: <why>" = the tool could not measure.
    A full-bleed frame is real content. It used to count as no ink at all, so a layer made only of a
    full-screen takeover was reported as a fully transparent, probably broken render (2026-10-07).
    A skipped or empty measurement is NEVER reported as clean (the silent-no-op trap the audit named)."""
    import re
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import safe_zones as SZ
        L, R, T, B = int(SZ.LEFT), int(SZ.RIGHT), int(SZ.TOP), int(SZ.BOTTOM)
    except Exception as e:
        return (f"skipped: product/safe_zones.py not importable ({e})", [])
    try:
        w, h = (int(x) for x in subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", out]).decode().strip().split(",")[:2])
        vf = ("alphaextract,format=gray,signalstats,lutyuv=y='if(gte(val\\,128)\\,255\\,0)',"
              "cropdetect=limit=1:round=1:reset=1:skip=0,metadata=print:file=-")
        pr = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-vf", vf, "-f", "null", "-"],
                            capture_output=True, text=True)
        meta = pr.stdout
        if pr.returncode != 0 or "frame:" not in meta:
            return (f"skipped: ffmpeg could not read the alpha plane ({(pr.stderr or '').strip()[-160:] or 'no frames'})", [])
    except FileNotFoundError as e:
        return (f"skipped: {e.filename or 'ffmpeg/ffprobe'} not installed", [])
    except subprocess.CalledProcessError:
        return (f"skipped: ffprobe could not read {os.path.relpath(out)} (missing, or not a video)", [])
    except Exception as e:
        return (f"skipped: {type(e).__name__}: {str(e)[:160]}", [])
    x1 = y1 = 10**9; x2 = y2 = -1; solid = 0; fullbleed = 0; cur = {}
    def flush():
        nonlocal x1, y1, x2, y2, solid, fullbleed
        if cur.get("YMAX", 0) >= 128 and all(k in cur for k in ("x1", "x2", "y1", "y2")):
            fx1, fx2, fy1, fy2 = cur["x1"], cur["x2"], cur["y1"], cur["y2"]
            if fx2 < fx1 or fy2 < fy1:                                     # inverted = nothing detected
                return
            if (fx2 - fx1 + 1) * (fy2 - fy1 + 1) < 0.9 * w * h:        # not a full-bleed designed frame
                solid += 1
                x1, y1, x2, y2 = min(x1, fx1), min(y1, fy1), max(x2, fx2), max(y2, fy2)
            else:                                                          # real ink, just full-frame by design
                fullbleed += 1
    for ln in meta.splitlines():
        if ln.startswith("frame:"):
            flush(); cur = {}
            continue
        m = re.match(r"\s*lavfi\.(?:signalstats\.(YMAX)|cropdetect\.(x1|x2|y1|y2))=(-?\d+)", ln)
        if m:
            cur[m.group(1) or m.group(2)] = int(m.group(3))
    flush()
    if not solid:
        return ("fullbleed", []) if fullbleed else ("empty", [])
    # The box's TOP is the strictest edge across platforms; its BOTTOM is the creator's 300px call, looser than
    # every platform's band (safe_zones.PLATFORMS). Say which platform(s) actually bind so the message is true.
    def _plat(edge, v):
        hits = []
        for p, z in getattr(SZ, "PLATFORMS", {}).items():
            lim = z["top"] if edge == "top" else z["bottom"]
            over = (lim - v) if edge == "top" else (v - lim)
            if over > 0:
                hits.append(f"{p} by {over}px")
        return "; ".join(hits) if hits else "inside every platform's own band (strictest-box margin only)"
    br = []
    if x1 < L:     br.append(f"LEFT: ink starts at x={x1} (safe ≥ {L}) — {L - x1}px into the side margin")
    if x2 + 1 > R: br.append(f"RIGHT: ink ends at x={x2 + 1} (safe ≤ {R}) — {x2 + 1 - R}px into the side margin")
    if y1 < T:     br.append(f"TOP: ink starts at y={y1} (safe ≥ {T}) — under the header band: {_plat('top', y1)}")
    if y2 + 1 > B: br.append(f"BOTTOM: ink ends at y={y2 + 1} (safe ≤ {B}) — into the bottom UI band: {_plat('bottom', y2 + 1)}")
    return ("ok", br)


def _subject_box(comp_dir):
    """The measured subject box for this job, or None when her footage was never measured."""
    try:
        import subject_guard
        zp = subject_guard.find_zones(comp_dir)
        return subject_guard.box_from_zones(zp) if zp else None
    except SystemExit:
        # box_from_zones raises SystemExit on a malformed measurement. SystemExit is a BaseException, so a
        # bare `except Exception` lets it through and a bad JSON file kills the render before it starts.
        return None
    except Exception:
        return None


def _subject_check(out, comp_dir, max_cov=None):
    """LAYER 2, SUBJECT-RELATIVE, on the FINAL ARTIFACT. The safe-zone check asks whether ink is inside the
    PLATFORM's band; this asks whether it is on HER. Nothing else in the pipeline can: the overlay renders
    transparent and the footage is not in the composition, so `hyperframes check` measures a canvas with no
    person in it and passes a hook sitting on a forehead.

    Returns (status, lines). "ok" = measured and clear; "breach" = it lands on her; "skipped: <why>" = her
    footage was never measured, which is reported as NOT MEASURED and never as clean."""
    try:
        import subject_guard
    except Exception as e:
        return (f"skipped: product/subject_guard.py not importable ({e})", [])
    zp = subject_guard.find_zones(comp_dir)
    if not zp:
        return ("skipped: her footage was never measured for this job — run "
                "`uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4`", [])
    try:
        box = subject_guard.box_from_zones(zp)
        # owns_from: the takeover windows are looked up from the COMPOSITION (its builder writes a copy of
        # owns-screen.json there). Walking up from the output alone found nothing whenever -o pointed outside
        # the job folder, so a takeover that covers her by design was refused as a stray graphic.
        rc, lines = subject_guard.report(out, box, max_cov if max_cov is not None else subject_guard.DEFAULT_MAX,
                                         owns_from=comp_dir)
    except SystemExit as e:
        return (f"skipped: {e}", [])
    except Exception as e:
        return (f"skipped: {type(e).__name__}: {str(e)[:160]}", [])
    return ("breach" if rc else "ok", lines)


def _ink_vf(out):
    """The ffmpeg filter that turns "is anything visible here" into a gray plane: the ALPHA channel for
    an overlay, the luma for a baked file."""
    try:
        pf = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                      "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", out],
                                     text=True).strip()
    except Exception:
        return None
    alpha = pf.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya"))
    return ("alphaextract," if alpha else "format=gray,") + "scale=96:-1"


def _visible_fraction(out, t, vf):
    """Fraction of pixels that are actually visible in the frame at t, or None if unreadable."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", out, "-vf", vf,
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    return (sum(1 for b in raw if b > 8) / len(raw)) if raw else None


def _plan_visual_items(comp_dir):
    """(kind, index, at) for every item the job's caption-plan says should be ON SCREEN: the list it sits
    in, its place in that list, and its time. Discovered by walking up to the job folder, so no caller has
    to pass them. Any dict with a numeric "at" counts, which survives the plan growing new element kinds."""
    d = os.path.abspath(comp_dir)
    for _ in range(4):
        d = os.path.dirname(d)
        cand = os.path.join(d, "caption-plan.json")
        if not os.path.exists(cand):
            continue
        try:
            plan = json.load(open(cand, encoding="utf-8"))
        except Exception:
            return []
        # ONLY the containers that hold TIMED VISUAL elements. A caption-plan also times SOUND
        # (`sfx`, `music`) and carries style blocks, and every one of those has an `at` too — so
        # collecting every `at` in the file demands a picture at the moment of a whoosh. On a reel
        # where that whoosh lands over bare footage the frame is legitimately empty, and a perfectly
        # good render gets refused. Verified against the real plans on this machine: they carry `at`
        # under elements, breakaways, sfx, music AND persistent_label_style.
        #
        # An ALLOWLIST, deliberately, because the two mistakes are not equal: missing a check lets one
        # bad render through, while a false refusal blocks a buyer from finishing work that is fine.
        # A visual kind that is not listed here is simply not checked — add it when it is confirmed
        # visual, never by assuming.
        VISUAL = ("elements", "breakaways", "graphics", "beats", "cards", "notes", "takeovers")
        items = []
        for key in VISUAL:
            node = plan.get(key)
            for i, item in enumerate(node if isinstance(node, list) else []):
                if isinstance(item, dict) and isinstance(item.get("at"), (int, float)):
                    items.append((key, i, float(item["at"])))
        return items
    return []


def _plan_expect_times(comp_dir):
    """Timestamps the job's caption-plan says something should be ON SCREEN (every visual item's `at`)."""
    return sorted(set(t for _k, _i, t in _plan_visual_items(comp_dir)))


def _comp_clips(comp_dir):
    """Every timed element in the composition as (start, end, lane), or None when that cannot be read
    with certainty. HyperFrames' own rules: an element carrying data-start is a clip; it shows while
    start <= t < start + data-duration; with no data-duration it stays for the rest of the composition;
    data-track-index is its lane. The composition root is the canvas, not a clip, and <audio> draws
    nothing. None (so every plan time is checked, as before) when there is no index.html, no clip in it,
    a sub-composition (its clips run on their own clock), or a start or duration that is not a plain
    number (a clip reference such as "intro + 2")."""
    from html.parser import HTMLParser
    try:
        with open(os.path.join(comp_dir, "index.html"), encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except OSError:
        return None
    clips, unsure = [], []

    class _Clips(HTMLParser):
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "template" or a.get("data-composition-src") is not None:
                unsure.append(tag)
            if a.get("data-start") is None or tag == "audio":
                return
            if a.get("data-composition-id") is not None:
                return                                   # the root: the whole canvas, not a clip
            try:
                s = float(a["data-start"])
                d = a.get("data-duration")
                e = s + float(d) if d not in (None, "") else float("inf")
                lane = a.get("data-track-index")
                clips.append((s, e, int(lane) if lane not in (None, "") else None))
            except ValueError:
                unsure.append(tag)

    try:
        _Clips(convert_charrefs=True).feed(src)
    except Exception:
        return None
    return None if (unsure or not clips) else clips


# The lanes build-reel-type.py puts the plan's own items on: a breakaway card is lane 6 and element i is
# lane 7 + i (its `_etrk`; product/layer_probe.py keeps the same map). The plan's other visual kinds are not
# tied to a lane, so for them any clip on screen at that moment counts.
_PLAN_LANES = {"breakaways": lambda i: {6}, "elements": lambda i: {7 + i}}
_PLAN_LAYER = {"breakaways": lambda lane: lane == 6, "elements": lambda lane: lane >= 7}   # any lane of that layer
_CLIP_SLACK = 0.05   # data-start/data-duration are written to 2 decimals: never lose a plan time to that rounding


def _render_expect_times(comp_dir):
    """The plan's on-screen times that THIS composition holds.

    A render of only some of the reel's layers (LAYER=<group> for separate layers, the hook / front split
    behind mode renders, a one-style caption overlay) holds only some of the plan's items. Asking it for all
    of them refused renders that were right ("EMPTY where the plan says..." at a moment that layer never
    draws). So a plan time is kept when the composition has a clip on that item's own lane whose window
    covers it. A full composition holds every item, so it is checked exactly as before, and when the
    composition cannot be read with certainty every plan time is checked, as before."""
    items = _plan_visual_items(comp_dir)
    clips = _comp_clips(comp_dir) if items else None
    if clips is None:
        return sorted(set(t for _k, _i, t in items))
    held = set()
    present = {lane for _s, _e, lane in clips}
    for kind, i, t in items:
        lanes = _PLAN_LANES[kind](i) if kind in _PLAN_LANES else None
        if lanes is not None and any(_PLAN_LAYER[kind](lane) for lane in present):
            # This composition draws that kind of item (every element is one layer, "elements"; the card is
            # "breakaway"), so it draws them ALL: one without its lane here was dropped by the builder, never
            # left out on purpose, and its moment is checked like any other.
            held.add(t)
            continue
        if any(s - _CLIP_SLACK <= t < e + _CLIP_SLACK for s, e, lane in clips if lanes is None or lane in lanes):
            held.add(t)
    return sorted(held)


EMPTY = 0.0005      # below this fraction of visible pixels, a frame is blank
_MAX_CLIP_SAMPLES = 48   # cap on the per-clip looks, so a reel with hundreds of caption clips stays quick


def _clip_sample_groups(comp_dir, dur):
    """For each clip window in the composition that falls inside the rendered file, (start, end, moments):
    a few moments inside it, the middle, plus the quarter points for a clip over a second, plus one every 4 s for a long one
    (a whole-reel clip whose words come and go). In time order, at most _MAX_CLIP_SAMPLES looks in all
    (clips spread evenly when there are more). [] when the composition cannot be read with certainty,
    so the caller keeps its evenly spaced samples. Lane 0 is the preview background some builds add,
    never something a layer is judged on."""
    clips = _comp_clips(comp_dir) if comp_dir else None
    if not clips or dur <= 0:
        return []
    groups, seen = [], set()
    for s, e, lane in sorted(clips):
        if lane == 0:
            continue
        a, b = max(0.0, s), min(e, dur - 0.05)
        if b - a <= 0.02 or (round(a, 2), round(b, 2)) in seen:
            continue
        seen.add((round(a, 2), round(b, 2)))
        length = b - a
        fracs = [0.5] if length <= 1.0 else [0.25, 0.5, 0.75]
        n_long = min(8, int(length // 4.0))
        fracs += [(k + 0.5) / n_long for k in range(n_long)] if n_long > len(fracs) else []
        groups.append((a, b, sorted({round(a + f * length, 3) for f in fracs})))
    while groups and sum(len(g[2]) for g in groups) > _MAX_CLIP_SAMPLES and len(groups) > 1:
        groups = groups[::2]                      # thin evenly, keeping time order
    while groups and sum(len(g[2]) for g in groups) > _MAX_CLIP_SAMPLES:
        groups = [(a, b, ts[::2]) for a, b, ts in groups]
    return groups


def _clip_sample_times(comp_dir, dur):
    """Every moment _clip_sample_groups would look at, flattened."""
    return sorted(t for _a, _b, ts in _clip_sample_groups(comp_dir, dur) for t in ts)


def _verify_render_has_content(out, comp_dir, strict=False, samples=16):
    """Check the RENDERED FILE, not the composition. Returns (ok, lines).

    This is the hole the gate never covered: `check` validates the composition and passes BEFORE a
    single frame exists, so a render that silently drops elements goes straight through it. A real
    incident (2026-09-16) produced an overlay holding only the hook, captions and takeover — every
    note and graphic missing — and the engine reported it built and good without a frame ever being
    looked at. Alpha was real and the safe zones were clean, so the two existing output checks passed
    as well. Reading what is actually in the file is the only thing that catches this."""
    vf = _ink_vf(out)
    dur = _dur(out) or 0
    if not vf or dur <= 0:
        return True, []
    msgs = []

    # 1) HARD: empty exactly where the plan says an element is showing (of the elements this composition
    #    holds: a render of one layer is never asked for another layer's elements).
    empty_at = []
    for t in [t for t in _render_expect_times(comp_dir) if 0 < t < dur]:
        f = _visible_fraction(out, min(t + 0.25, dur - 0.05), vf)
        if f is not None and f < EMPTY:
            empty_at.append(t)
    if empty_at:
        msgs.append("  \u26d4 the render is EMPTY where the plan says an element is on screen: "
                    + ", ".join(f"{t:.2f}s" for t in empty_at[:8])
                    + (f" (+{len(empty_at) - 8} more)" if len(empty_at) > 8 else ""))
        msgs.append("     The composition passed the gate, so this is the RENDER losing content, not a bad plan.")
        msgs.append("     Re-run it once; if it repeats, render the same comp with a bare "
                    f"`npx hyperframes@{HF_VERSION} render <comp> --format mov` and compare the two.")
        return False, msgs

    # 2) SOFT: mostly-blank output. Legitimate for a sparse overlay, and also what a dropped-element
    #    render looks like, so it is said out loud rather than assumed either way.
    #
    #    WHERE to look. Evenly spaced samples alone miss a layer that is on screen briefly: a takeover layer
    #    on a 60 s reel draws for two seconds, all 16 evenly spaced frames land outside it, and a correct
    #    render was refused as containing NOTHING (2026-10-07, Intel tester). So when the composition can be
    #    read, every clip window it holds is looked at too (_clip_sample_groups). The file is called empty
    #    only when the evenly spaced frames AND those moments are all blank; the "mostly blank" warning then
    #    counts the clips that never showed any ink, which is what a dropped element looks like.
    prof = [(t, _visible_fraction(out, t, vf))
            for t in (dur * (i + 0.5) / samples for i in range(samples))]
    prof = [(t, f) for t, f in prof if f is not None]
    # Each clip is judged on its own moments plus any evenly spaced frame that fell inside its window.
    groups = [[f for f in (_visible_fraction(out, t, vf) for t in ts) if f is not None]
              + [f for t, f in prof if a <= t <= b]
              for a, b, ts in _clip_sample_groups(comp_dir, dur)]
    groups = [g for g in groups if g]
    if not prof and not groups:
        return True, []
    if all(f < EMPTY for _t, f in prof) and all(f < EMPTY for g in groups for f in g):
        where = ("every sampled frame, and every moment the composition draws something, is empty" if groups
                 else "every sampled frame is empty")
        return False, [f"  \u26d4 the render contains NOTHING — {where}."]
    if groups:
        blank, looked, unit = sum(1 for g in groups if all(f < EMPTY for f in g)), len(groups), "clips"
    else:
        blank, looked, unit = sum(1 for _t, f in prof if f < EMPTY), len(prof), "sampled frames"
    if blank > looked * 0.6:
        msgs.append(f"  \u26a0 {blank} of {looked} {unit} are completely empty. That can be normal for "
                    f"a sparse overlay, but it is also what a render that dropped its elements looks like. "
                    f"Look at a frame before shipping it.")
        if strict:
            return False, msgs
    return True, msgs


def _alpha_is_real(out, samples=5):
    """True if this overlay actually has transparent pixels, False if it is uniformly opaque,
    None if the question does not apply (no alpha channel) or ffmpeg could not answer.

    WHY this is not just a pix_fmt check: a broken transparent render still writes a yuva pix_fmt
    AND the container's alpha_mode tag, so every piece of metadata says "transparent" while every
    pixel decodes solid. The only honest test is to read the alpha plane itself. Sampled across the
    timeline because an overlay may legitimately be opaque during one full-frame beat — only a file
    that is opaque EVERYWHERE is the bug. Set REEL_SKIP_ALPHA_CHECK=1 to bypass."""
    if os.environ.get("REEL_SKIP_ALPHA_CHECK") == "1":
        return None
    try:
        pf = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                      "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", out],
                                     text=True).strip()
        if not pf.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")):
            return None                                    # not an alpha format: nothing to verify
        dur = _dur(out) or 0
        if dur <= 0:
            return None
        lo = 255
        for i in range(samples):
            t = dur * (i + 0.5) / samples
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", out,
                                  "-vf", "alphaextract,scale=64:-1", "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                 capture_output=True).stdout
            if raw:
                lo = min(lo, min(raw))
            if lo < 250:
                return True                                # found real transparency, done
        return False if lo >= 250 else True
    except Exception:
        return None


def _render_by_spans(d, out, plan, extra, env=None):
    """Render each on-screen stretch of a caption layer from its own time-shifted copy (isolated, like every
    render here), then stitch them into the full-length `out`. (True, "") on success; (False, reason) on
    anything off, so the caller can fall back to the full render. Stretches render one after another, never
    at the same time."""
    import tempfile, shutil
    work = tempfile.mkdtemp(prefix="reel-render-spans-")
    _render_by_spans.parts = []
    try:
        files = []
        n = len(plan["spans"])
        # Each stretch is kept by what it shows (render_spans.stretch_keys: its own page, the comp's fonts, the
        # renderer's version), so a caption edit renders only the stretch it touches; the rest come from the cache.
        try:
            keys = render_spans.stretch_keys(d, plan, HF_VERSION)
        except Exception:   # noqa: BLE001 — no keys: every stretch renders, exactly as before
            keys = [None] * n
        reused = 0
        try:
            html = open(os.path.join(d, "index.html"), encoding="utf-8").read()
        except OSError:
            html = ""
        for i, (first, end) in enumerate(plan["spans"]):
            hit = render_spans.cached_stretch(keys[i], end - first)
            if hit and render_spans.stretch_is_blank(hit, html, first, end, plan["fps"]):
                # a stretch kept blank where its captions show is never reused: dropped, and rendered fresh below
                try:
                    os.remove(hit)
                except OSError:
                    pass
                hit = None
            if hit:
                files.append(hit); reused += 1
                continue
            try:
                comp = render_spans.span_comp(d, os.path.join(work, f"span{i + 1}"), first, end, plan["fps"],
                                              local=bool(keys[i]))
            except Exception as e:   # noqa: BLE001 — any reason at all means the full render instead
                return False, f"stretch {i + 1} could not be prepared: {e}"
            f = os.path.join(work, f"span{i + 1}.mov")
            rnd = npx_argv(f"hyperframes@{HF_VERSION}", "render", comp, "--format", "mov", "--output", f, *extra)
            print(f"[render] stretch {i + 1}/{n}: {first / plan['fps']:.2f}s-{end / plan['fps']:.2f}s (isolated copy)")
            try:
                rc = _run_render_watched(rnd, comp_dir=d, env=env)
            except Exception as e:   # noqa: BLE001 — the renderer would not even start: full render instead
                return False, f"stretch {i + 1} did not start ({type(e).__name__})"
            if rc != 0 or not os.path.exists(f):
                return False, f"stretch {i + 1} did not render"
            if render_spans.stretch_is_blank(f, html, first, end, plan["fps"]):
                # never kept, never stitched: the whole layer renders full length instead (it has every caption)
                return False, f"stretch {i + 1} came out blank where its captions show"
            if render_spans.count_frames(f) == end - first:  # only a whole stretch is kept (a short one fails assembly)
                f = render_spans.store_stretch(keys[i], f)
            files.append(f)
        try:
            render_spans.assemble(files, plan, out, os.path.join(work, "assemble"))
        except Exception as e:   # noqa: BLE001
            return False, str(e)
        if reused:
            print(f"  ✓ {n - reused} of {n} stretches rendered; {reused} unchanged came from the cache")
        print(f"  ✓ {n} stretch{'es' if n != 1 else ''} stitched into one full-length layer "
              f"({plan['frames']} frames, the same file a full render makes)")
        _render_by_spans.parts = [f if f.startswith(render_spans.cache_root()) else None for f in files]
        return True, ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_whole_again(d, out, fmt, extra, env, html):
    """One more full render after the first attempt has let go of the render lock: it waits its turn like any other."""
    _take_render_lock(os.path.basename(os.path.normpath(d)))
    try:
        return _render_full(d, out, fmt, extra, env, html)
    finally:
        _release_render_lock(all_levels=True)


def _render_full(d, out, fmt, extra, env, html):
    """One full-length render of the composition: the exit code, or None when the renderer would not even
    start. Every call isolates afresh, because a FAILED render can delete the copy it rendered (below)."""
    import tempfile, shutil
    work = None; src = d
    if "../" in html:
        print("  ⚠ composition references paths outside its dir (`../`) — rendering IN PLACE (no isolation).")
    else:
        work = tempfile.mkdtemp(prefix="reel-render-")
        src = os.path.join(work, "comp")
        shutil.copytree(d, src, ignore=shutil.ignore_patterns(".reel_render", "renders", ".hyperframes", ".DS_Store"))
    rnd = npx_argv(f"hyperframes@{HF_VERSION}", "render", src, "--format", fmt, "--output", out, *extra)
    print("[render]", " ".join(rnd[1:]), "" if work is None else "(isolated copy; job dir untouched)")
    try:
        return _run_render_watched(rnd, comp_dir=d, env=env)
    except OSError:   # npx found but would not start (the spans path treats it the same way)
        return None
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)


def _stage_missing_fonts(d, refs):
    """Pull licensed pack fonts the composition names but its folder lacks from her own CapCut
    (stage_hands_off_fonts.stage, the step that was skipped), then copy each into the composition folder
    under the name its @font-face asks for. Returns the refs STILL missing: those keep the refusal, because
    a render in a substitute typeface is never the route around a missing font."""
    try:
        import shutil
        import stage_hands_off_fonts as shf
    except Exception:   # noqa: BLE001
        return refs
    pack_of = {f.lower(): pack for pack, files in shf.RESTRICTED.items() for f in files}
    packs = sorted({pack_of[os.path.basename(r).lower()] for r in refs if os.path.basename(r).lower() in pack_of})
    if not packs:
        return refs
    print(f"  {len(refs)} font file(s) are missing from the composition folder; fetching them from your CapCut.")
    try:
        shf.stage(packs)
    except (Exception, SystemExit):   # noqa: BLE001 — the resolver missing or failing leaves the refusal as it was
        pass
    still, got = [], []
    for ref in refs:
        dest = os.path.join(d, ref)
        pack = pack_of.get(os.path.basename(ref).lower())
        src = os.path.join(shf.HANDS_OFF, pack, os.path.basename(ref)) if pack else ""
        if not os.path.exists(dest) and src and os.path.isfile(src):
            try:
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                shutil.copyfile(src, dest)
            except OSError:
                pass
        (got if os.path.exists(dest) else still).append(ref)
    if got:
        _fallbacks().note("render-fonts", f"{', '.join(sorted(got))} missing from the composition folder; "
                             f"staged from this computer's CapCut")
        print(f"  ✓ staged {', '.join(sorted(got))} from your CapCut into the composition folder.")
    return still


# ─── ONE RENDER AT A TIME ON THIS COMPUTER ─────────────────────────────────────────────────────────────────
# Two renders at once each get half the memory and the browser, and on a 16 GB Mac that is how both die
# partway. So the HyperFrames render itself (the full render, every stretch of a caption layer, and the
# retries) holds the one lock every HyperFrames render on the computer shares: product/render_lock.py, which
# owns the protocol (a second render waits, never stops the first; a lock left by a render that is gone is
# taken over; Ctrl-C while waiting is a stop). A cache hit never gets that far, so it never waits.
import render_lock


def _wrapper_route_open(env=None):
    """The localhost wrapper can be tried: a Mac or Linux, and nobody already chose the render browser
    (HYPERFRAMES_BROWSER_PATH, or PRODUCER_HEADLESS_SHELL_PATH, which HyperFrames reads first)."""
    env = env or os.environ
    return render_browser.supported() and not env.get("HYPERFRAMES_BROWSER_PATH") \
        and not env.get("PRODUCER_HEADLESS_SHELL_PATH")


def _take_render_lock(what=""):
    return render_lock.acquire(what)


def _release_render_lock(all_levels=False):
    render_lock.release(all_levels)


def cmd_render(a):
    d = comp_dir_of(a.target)
    if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "index.html")):
        print(f"  ⛔ composition not found (need <dir>/index.html): {d}"); return 2
    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)   # a missing output dir is never a reason to fail late
    # Follow the OUTPUT EXTENSION unless --format was given explicitly. Asking for `-o preview.mp4` and
    # silently getting a transparent-overlay mov is the trap: a full-frame composition (a pack preview, a
    # designed card, anything with its own ground) then trips the opaque-overlay guard, and the error talks
    # about alpha when the real answer is "you wanted an mp4". An explicit --format always wins.
    if a.format is None:
        a.format = {".mp4": "mp4", ".webm": "webm", ".mov": "mov"}.get(os.path.splitext(out)[1].lower(), "mov")
    # FAIL LOUD on a missing font FILE: compositions load fonts by RELATIVE url('x.ttf'). If the file is absent the
    # browser silently substitutes a system font, `check` cannot know the intended face, and the render ships in
    # the wrong typography. Refuse before spending a minute on it. (Premium faces are staged into the comp dir
    # from the buyer's CapCut cache by stage_hands_off_fonts — this catches a skipped staging step.)
    import re
    html_src = open(os.path.join(d, "index.html"), encoding="utf-8", errors="ignore").read()
    missing = []
    for ref in set(re.findall(r"url\(\s*['\"]?([^'\")]+\.(?:ttf|otf|woff2?))['\"]?\s*\)", html_src, flags=re.I)):
        if "://" in ref or ref.startswith("/"):
            continue                                            # absolute / remote: not a co-located file
        if not os.path.exists(os.path.join(d, ref)):
            missing.append(ref)
    if missing:
        missing = _stage_missing_fonts(d, missing)
    if missing:
        print("  ⛔ REFUSING to render: font file(s) referenced by the composition are missing from its folder — "
              "the render would silently use the wrong typeface:\n" + "".join(f"     • {m}\n" for m in sorted(missing))
              + "     Stage them first (python3 product/stage_hands_off_fonts.py <pack>) or fix the @font-face path.")
        return 3
    # A composition built outside the reel builders (a hands-off template with her words typed in) gets the
    # same Cyrillic companions they add. A page with no Cyrillic, or one already done, is left untouched.
    import script_fonts
    script_fonts.patch_dir(d)
    sz_mode = "off" if a.no_safe_zone else ("strict" if a.safe_zone_strict else "report")
    # The subject measurement lives in the JOB folder, outside the composition comp_hash covers. Fold the
    # measured box into the key so re-measuring her footage invalidates a cached "clean" instead of
    # reusing a verdict that was reached against the old numbers.
    subj_key = "off" if a.no_subject else str(_subject_box(d))
    # Every setting that loosens or retunes a check is in the key too. Without them a render that passed
    # with a check switched off (--no-contrast, --subject-max, REEL_ALLOW_DEAD_TARGETS=1,
    # REEL_SKIP_ALPHA_CHECK=1) was handed back as "gated clean" to a later run that asked for the full gate.
    # Only a setting actually in force adds to the key, so a run with none keeps the key it always had.
    relaxed = "".join(f"|{k}" for k, on in (
        ("contrast=off", a.no_contrast),
        (f"subject_max={a.subject_max!r}", a.subject_max is not None),
        ("dead_targets=allowed", os.environ.get("REEL_ALLOW_DEAD_TARGETS") == "1"),
        ("offframe_text=allowed", os.environ.get("REEL_ALLOW_OFFFRAME_TEXT") == "1"),
        ("alpha_check=skipped", os.environ.get("REEL_SKIP_ALPHA_CHECK") == "1"),
    ) if on)
    # A layer rendered in stretches keys on how it was stitched back together, so a layer assembled before a fix
    # to that (render_spans.ASSEMBLY) is rendered again rather than handed back. Every other layer's key is as before.
    if a.format == "mov" and os.environ.get("REEL_FULL_RENDER") != "1" and render_spans.load_plan(d):
        relaxed += f"|spans_assembly={render_spans.ASSEMBLY}"
    key = comp_hash(d, extra=f"strict={int(a.strict)}|format={a.format}|sz={sz_mode}|subj={subj_key}{relaxed}",
                    skip=out)
    st = _load(d)
    prev = st.get(key)
    if not a.force and prev and prev.get("out") == out and prev.get("ok") and os.path.exists(out) \
            and not _out_rewritten(d, prev, out):
        _say_estimate(d, cached=True)
        print(f"  ✅ unchanged since last clean render — reusing {os.path.relpath(out)} (no check, no render).")
        if prev.get("sz"):   # a report-mode breach is re-said on every reuse, never a one-shot warning
            print("  ⚠ SAFE-ZONE (from that render — still true, the file is unchanged):")
            for b in prev["sz"]:
                print(f"     • {b}")
        for ln in prev.get("subject") or []:   # and so is a look on her face, rendered as placed
            print(f"  {ln}")
        _write_render_diagnostics(d, cached=True, fmt=a.format, ok=True)
        return 0

    # This Mac already showed its macOS cannot run the renderer (same macOS, same pin): say so now instead of
    # spending minutes on a check and a render that end the same way (see _os_unsupported_known).
    _ver = _os_unsupported_known()
    if _ver:
        return _os_unsupported_stop(d, _ver, learned=True, fmt=a.format)

    # Node first. Without it the check never runs, and that must not read as a fault in the composition: on
    # Windows the check runs as `cmd /c npx ...`, and `cmd` always exists, so a missing npx came back as an
    # ordinary exit 1 and this said "Fix the composition" (most often Node installed, Git Bash not reopened).
    if not npx_path():
        print(f"  ⛔ the check could not run. {NO_NODE}\n"
              f"     Nothing was checked, and nothing here says the composition is wrong."); return 4
    # `check` waits for scripts and media to settle before it measures (default 3000 ms). That default was
    # measured on Apple Silicon; an Intel Mac or a budget PC can miss it and fail a composition that is fine,
    # and this gate REFUSES to render on a failed check. Give slow hardware headroom; the env override is
    # for a tester whose machine needs more. The check's page-load budget gets the same headroom
    # (npx_run.hf_check_env): its 10 s floor refused clean compositions on a loaded 8 GB Intel Mac.
    chk = hf_check_argv(HF_VERSION, d, strict=a.strict, contrast=not a.no_contrast)   # order is load-bearing; see npx_run.hf_check_argv
    print("[gate]", " ".join(chk[1:]))
    _t_check = time.monotonic()
    # npx_run.run_hf_check runs it with the backup routes (npm's cache when offline, a longer page-load budget,
    # one more try when the checking tool itself crashed or hung) and prints each attempt's output. None of
    # them skips the gate: only HyperFrames' own verdict below ever lets a render through.
    res = run_hf_check(chk, step="render-check")
    check_seconds = round(time.monotonic() - _t_check, 1)
    if res.status == "would-not-start":   # npx found but would not start: the same plain answer, never a traceback
        print(f"  ⛔ the check could not run. {NO_NODE}\n"
              f"     Nothing was checked, and nothing here says the composition is wrong."); return 4
    if res.status == "stopped":
        return res.rc
    chk_rc = res.rc
    text = res.text
    _summarize_check(text)
    if res.status != "ran":
        # npx itself can fail before HyperFrames ever starts (it could not get the package: offline with
        # nothing cached, a proxy, a cache it may not write). npm then prints its own "npm error code ..."
        # and HyperFrames never gives a verdict, so nothing was checked and the composition is not at fault.
        # npm's cache was already tried (run_hf_check); this is the case where HyperFrames was never cached.
        if res.status == "npm":
            print(f"\n  ⛔ the check could not run: npx could not start HyperFrames {HF_VERSION} (npm said "
                  f"{res.npm_code}, above). Nothing was checked, and nothing here says the composition is wrong.\n"
                  f"     With an internet connection, run `npx hyperframes@{HF_VERSION} browser ensure` once "
                  f"(it downloads HyperFrames), then run this again.")
            return 4
        # The check's own browser page did not finish loading in time, even after the longer budget. That is
        # this machine being busy or slow, not a finding about the composition, so it is never reported as one.
        if res.status == "nav":
            _nav = int(res.nav_ms) if str(res.nav_ms or "").isdigit() else 10000
            _routes = [w for k, w in (("gpu-software", "software drawing"),
                                      ("localhost-wrapper", "opening the page by number")) if k in getattr(res, "tried", ())]
            _also = f" {' and '.join(_routes).capitalize()} {'were' if len(_routes) > 1 else 'was'} tried too." \
                if _routes else ""
            _more = (f"{_also.strip()} If it still runs out of time, run /report-a-problem so the cause can be found."
                     .strip() if _nav >= _npx_run.NAV_RETRY_MS else
                     "If it still runs out of time, give it longer: REELS_ENGINE_HF_NAV_TIMEOUT_MS=120000 in "
                     "front of the same command.")
            print(f"\n  ⛔ the check could not start in time: its browser page took longer than "
                  f"{_nav // 1000} s to load on this computer. Nothing was checked, and nothing here says "
                  f"the composition is wrong.\n"
                  f"     Close other apps that are using memory and run this again. {_more}")
            _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
            return 4
        # The check draws in the same browser as the render, so on a macOS too old for it the check is what
        # dies first. Nothing renders either way; this says why, and what still finishes her reel.
        _ver = _old_macos() if res.status == "crashed" and res.how != "hung" else None
        if _ver and _os_crash(chk_rc, text):
            return _os_unsupported_stop(d, _ver, check_seconds=check_seconds, fmt=a.format)
        # The checking tool itself crashed or hung, twice. Nothing was checked, so nothing renders: the gate is
        # never skipped. But it is said as what it is, a tool that would not run here, not a composition fault.
        _what = (f"gave no answer for {_npx_run.hang_words()}" if res.how == "hung"
                 else f"stopped without a verdict (exit {chk_rc})")
        print(f"\n  ⛔ the checking tool could not run on this computer: it {_what}, twice. Nothing was checked, "
              f"so nothing is rendered, and nothing here says the composition is wrong.\n"
              f"     Run /report-a-problem: it collects what is needed to fix the tool on this computer.")
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 4
    _check_flagged = False                                   # the check flagged something and it rendered anyway
    if chk_rc != 0:
        # A "Check failed" whose real cause is the browser not loading against an old macOS is not a finding
        # about the composition: say that instead, and do not mark the composition as failed.
        _ver = _old_macos() if _OS_CRASH_LINE.search(text or "") else None
        if _ver:
            return _os_unsupported_stop(d, _ver, check_seconds=check_seconds, fmt=a.format)
        if a.strict:
            print("\n  ⛔ check found issues — REFUSING to render (--strict). Fix the composition (see above), then "
                  "re-run. Packs may only change dressing; layout, motion and overflow are HyperFrames' job.")
            st[key] = {"out": out, "ok": False}; _save(d, st)
            _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
            return 1
        # She always gets her reel: a check is a warning, never a wall (2026-10-18: "this should look more like
        # a warning"). Said once, then rendered as placed; --strict still refuses.
        if getattr(_npx_run, "check_ran_out_of_time", lambda _t: False)(text):
            # HyperFrames' own 120 s ran out (check_runtime_failure). That is the time the check had here, not a
            # finding, so it is never said as "fix the composition".
            print("\n  ⚠ the check ran out of its time on this computer before it finished; rendering anyway, as "
                  "placed. That is about the time it had, not the composition.")
        else:
            print("\n  ⚠ check flagged the issues above; rendering anyway, as placed. Fix the composition and render "
                  "again if they show.")
        _check_flagged = True

    # An animation aimed at nothing is a silent no-op, not a style choice: the render succeeds and the effect
    # is just absent. HyperFrames names it as a warning, which passes without --strict; refuse on it anyway.
    _dead = _dead_animation_targets(text)
    if _dead and (os.environ.get("REEL_ALLOW_DEAD_TARGETS") == "1" or not a.strict):   # a warning, never a wall
        _check_flagged = True
        print(f"\n  ⚠ {len(_dead)} animation target(s) match nothing; rendering anyway "
              f"(a check is a warning; --strict refuses). Those animations will not appear: {', '.join(_dead[:4])}")
        _dead = []
    if _dead:
        print(f"\n  ⛔ {len(_dead)} animation target(s) match nothing in this composition — REFUSING to render. "
              f"These animations would not run and the render would come out silently missing them:")
        for sel in _dead[:8]:
            print(f"       {sel}")
        if len(_dead) > 8:
            print(f"       … and {len(_dead) - 8} more")
        print("     Usually the selector and the element's real id/attribute have drifted apart (a built id gets "
              "a prefix the selector was not given). Fix the selector, or the element, then re-run.")
        print("     If the element really is created later and this is deliberate, set REEL_ALLOW_DEAD_TARGETS=1.")
        st[key] = {"out": out, "ok": False}; _save(d, st)
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 1

    # A line drawn on with round caps the old way paints a dot at each end before it draws (svg_draw.py): the two
    # dots on every arrowhead. Never intended, and the check above cannot see it, so refuse here.
    import svg_draw
    _dots = svg_draw.check_comp(d)
    if _dots:
        print(svg_draw.message(_dots))
        st[key] = {"out": out, "ok": False}; _save(d, st)
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 1

    # Text stuck past the edge of the video would render cut off. HyperFrames names it as a warning, which passes
    # without --strict; refuse on it anyway (see _offframe_text).
    _off = _offframe_text(text)
    if _off and (os.environ.get("REEL_ALLOW_OFFFRAME_TEXT") == "1" or not a.strict):
        # She always gets her reel: text past the edge is said loudly and rendered as placed (--strict still refuses,
        # for the builds that must prove every word reads). Fix the fit and re-render that one layer to change it.
        print(_offframe_message(_off).replace("⛔", "⚠").replace("REFUSING to render", "rendering anyway, as placed")
              .replace(" To render it anyway: REEL_ALLOW_OFFFRAME_TEXT=1.", ""))
        _off = []
    if _off:
        print(_offframe_message(_off))
        st[key] = {"out": out, "ok": False}; _save(d, st)
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 1

    # ISOLATED render (locked): on a FAILED render HyperFrames (seen on 0.8.43) rolls its transaction back and has DELETED
    # the composition dir and sibling job files (a real incident: it took the job's outputs/ and cut backups with
    # it, and reverted cuts.json). So render a scratch COPY outside projects/; a failure there can only harm the
    # copy. A comp that reaches outside its own dir (`../`) cannot be isolated and renders in place, said out loud.
    import tempfile, shutil
    _idx = os.path.join(d, "index.html")
    _html = open(_idx, errors="ignore", encoding="utf-8").read() if os.path.exists(_idx) else ""
    _rnd_extra = ["--low-memory-mode"] if getattr(a, "low_memory", False) else []
    _fb = _fallbacks()
    # What this computer has learned it needs to render (the retries below) applies up front, so a later
    # render goes straight to what works instead of failing first every time.
    if not _rnd_extra and _fb.remembered("render.low-memory"):
        _rnd_extra = ["--low-memory-mode"]
        print("  streaming frames instead of buffering them to disk (--low-memory-mode), the way this "
              "computer renders.")
    elif _rnd_extra:
        print("  streaming frames instead of buffering them to disk (--low-memory-mode).")
    _rnd_env = None
    if _fb.remembered("render.gpu-software") and not os.environ.get("PRODUCER_BROWSER_GPU_MODE"):
        _rnd_env = dict(os.environ, PRODUCER_BROWSER_GPU_MODE="software")
        print("  drawing in software, the way this computer renders (its graphics drawing stalled the renderer).")
    if _fb.remembered("render.localhost-wrapper") and _wrapper_route_open():
        _wrap = render_browser.write_localhost_wrapper()
        if _wrap:
            _rnd_env = dict(_rnd_env or os.environ, HYPERFRAMES_BROWSER_PATH=_wrap)
            print("  opening the render page by number (127.0.0.1), the way this computer renders (something here "
                  "blocks the name localhost).")
    if res.offline:   # the check ran from npm's cache, so the render must too, or it goes looking online
        _rnd_env = offline_env(_rnd_env)
    # A fresh render replaces the file, so a sidecar from an earlier render no longer describes it.
    render_spans.drop_sidecar(out)
    # CAPTION LAYERS RENDER ONLY WHERE THEY ARE ON SCREEN (product/render_spans.py). The check above ran on the
    # whole composition as always; this renders one time-shifted copy per on-screen stretch and stitches them
    # back into the same full-length file. Anything off and it is the ordinary full render below, said once.
    sp_plan = None
    if a.format == "mov" and os.environ.get("REEL_FULL_RENDER") != "1" and "../" not in _html:
        sp_plan = render_spans.load_plan(d)
    rc = None
    _say_estimate(d, spans=sp_plan["spans"] if sp_plan else None)
    # One render at a time on this computer: wait here for any other render to finish (see _take_render_lock).
    # Held through the stretches and both retries below, and let go as soon as the renderer is done.
    _take_render_lock(os.path.basename(os.path.normpath(d)))
    _t_render = time.monotonic()
    if sp_plan:
        print(f"  captions {render_spans.describe(sp_plan)}.")
        ok_sp, why = _render_by_spans(d, out, sp_plan, _rnd_extra, env=_rnd_env)
        if ok_sp:
            rc = 0
        else:
            sp_plan = None
            print(f"  Rendering only the on-screen stretches did not work here ({why}), so this layer renders "
                  f"full length, the way it always has.")
            _fb.note("render-spans", f"rendering only the on-screen stretches did not work ({why}); "
                                     f"rendered the layer full length")
    tried = []
    os_crashed, _old_mac = False, None
    if rc is None:
        rc = _render_full(d, out, a.format, _rnd_extra, _rnd_env, _html)
        # A render that FAILED (its process has exited: a running render is never stopped) gets the two
        # routes known to work on hard machines, one at a time, never two renders at once: streaming frames
        # (--low-memory-mode, one worker through 0.8.158), then software drawing (PRODUCER_BROWSER_GPU_MODE=software,
        # what product/render-check.py proves on a Mac whose graphics path stalls Chrome), and, only when the
        # page itself did not load, the localhost wrapper (below). Whichever works is
        # remembered. Not on her Ctrl-C, not when it would not start, and not when a failed IN-PLACE render
        # took the composition with it.
        def _failed(code):
            return code is not None and code not in _npx_run.STOP_CODES and (code != 0 or not os.path.exists(out)) \
                and os.path.exists(os.path.join(d, "index.html"))
        # On a macOS older than 13, note whether the latest attempt died the way a browser too new for it
        # does. The loader's own "Symbol not found" line is certain and no flag changes it, so the two retries
        # are skipped; an abort alone could still be memory, so those still get them (see _os_crash).
        _old_mac = _old_macos() if _failed(rc) else None
        def _os_seen(code):
            return bool(_old_mac) and _failed(code) and \
                _os_crash(code, _LAST_RENDER["marks"] + _LAST_RENDER["text"])
        os_crashed = _os_seen(rc)
        _no_retry = bool(_old_mac) and _failed(rc) and _os_crash(rc, _LAST_RENDER["marks"], definite_only=True)
        if _failed(rc) and "--low-memory-mode" not in _rnd_extra and not _no_retry:
            tried.append("low-memory")
            print(f"\n  The render stopped (exit {rc}). Rendering once more, streaming frames instead of "
                  f"buffering them (--low-memory-mode).")
            _fb.note("render", f"HyperFrames render failed (exit {rc}); rendered again with --low-memory-mode")
            rc = _render_full(d, out, a.format, _rnd_extra + ["--low-memory-mode"], _rnd_env, _html)
            os_crashed = _os_seen(rc)
            if rc == 0 and os.path.exists(out):
                _fb.remember("render.low-memory", True,
                             why="renders here only failed until frames were streamed (--low-memory-mode)")
        if _failed(rc) and (_rnd_env or os.environ).get("PRODUCER_BROWSER_GPU_MODE") != "software" \
                and not _no_retry:
            tried.append("gpu-software")
            print(f"\n  The render stopped (exit {rc}). Rendering once more with software drawing "
                  f"(slower, but it renders where the graphics path stalls).")
            _fb.note("render", f"HyperFrames render failed (exit {rc}); rendered again with "
                               f"PRODUCER_BROWSER_GPU_MODE=software")
            rc = _render_full(d, out, a.format, _rnd_extra,
                              dict(_rnd_env or os.environ, PRODUCER_BROWSER_GPU_MODE="software"), _html)
            os_crashed = _os_seen(rc)
            if rc == 0 and os.path.exists(out):
                _fb.remember("render.gpu-software", True,
                             why="renders here only worked with software drawing (PRODUCER_BROWSER_GPU_MODE=software)")
        # The third route, only when the page itself did not load (ISS-77): open it by number through the
        # localhost wrapper, the fix product/render-check.py proves. Drawing as it was before the software retry
        # (the wrapper keeps the faster graphics path). Mac and Linux only: render_browser returns None on
        # Windows, so nothing changes there. Remembered as render.localhost-wrapper and applied up front later.
        if _failed(rc) and _LAST_RENDER["nav"] and _wrapper_route_open(_rnd_env) and not _no_retry:
            _wrap = render_browser.write_localhost_wrapper()
            if _wrap:
                tried.append("localhost-wrapper")
                print(f"\n  The render page did not load (exit {rc}). Rendering once more, opening it by number "
                      f"(127.0.0.1) instead of by the name localhost, which something on this computer can block.")
                _fb.note("render", f"HyperFrames render failed (exit {rc}) before its page loaded; rendered again "
                                   f"through the localhost wrapper (HYPERFRAMES_BROWSER_PATH, MAP localhost 127.0.0.1)")
                rc = _render_full(d, out, a.format, _rnd_extra,
                                  dict(_rnd_env or os.environ, HYPERFRAMES_BROWSER_PATH=_wrap), _html)
                os_crashed = _os_seen(rc)
                if rc == 0 and os.path.exists(out):
                    _fb.remember("render.localhost-wrapper", True,
                                 why="the render page only loaded by number here (localhost wrapper, "
                                     "HYPERFRAMES_BROWSER_PATH)")
    _release_render_lock(all_levels=True)   # the renderer is done; the checks below only read the file, so the next render can go
    if rc is None:
        print(f"  ⛔ the renderer could not start. {NO_NODE}\n"
              f"     Nothing was rendered, and nothing here says the composition is wrong.")
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 4
    render_seconds = round(time.monotonic() - _t_render, 1)
    if rc != 0 or not os.path.exists(out):
        # The last attempt died the way a browser too new for this macOS does: say that, and the route that works,
        # instead of the disk-space and reinstall advice below, which would change nothing here.
        if os_crashed and _old_mac and os.path.exists(os.path.join(d, "index.html")):
            return _os_unsupported_stop(d, _old_mac, check_seconds=check_seconds,
                                        render_seconds=render_seconds, fmt=a.format)
        # The renderer prints its own reason directly above; do not talk over it with a guess. This
        # line used to assert the cause was a browser that failed to start, which sent anyone whose
        # render died of a full disk off to reinstall a browser that was working fine.
        _free_gb = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free / 1e9
        print("\n  ⛔ render failed. The reason is in the renderer's own output just above.")
        print(f"     Two things worth checking first — free disk here: {_free_gb:.1f} GB.")
        print("     • Out of temporary space? A minute of transparent 1080x1920 runs to roughly 15 GB of")
        if "low-memory" in tried or "--low-memory-mode" in _rnd_extra:
            print("       frames. Streaming them (--low-memory-mode) was already tried; free some space.")
        else:
            print("       frames. Re-run with --low-memory to stream them instead of buffering.")
        print(f"     • HyperFrames did not start? `npx hyperframes@{HF_VERSION} browser ensure` once, then "
              f"`npx hyperframes@{HF_VERSION} doctor`.")
        if tried:
            print(f"     It was already rendered again ({' and '.join(tried)}) and still failed. Run "
                  f"/report-a-problem so the cause on this computer can be found.")
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                   render_seconds=render_seconds, fmt=a.format, ok=False)
        return rc or 1
    if a.format in ("mov", "webm"):
        verdict = _alpha_is_real(out)
        if verdict is False:
            print(f"\n  ⛔ this overlay rendered FULLY OPAQUE. The file says it carries alpha and the container "
                  f"tag agrees, but every pixel is solid — dropped on the footage it would black the reel out.\n"
                  f"     Cause: some HyperFrames builds only apply the transparent-background capture when the\n"
                  f"     output format is png, so mov/webm come back opaque while still LOOKING correct in\n"
                  f"     ffprobe. This engine pins {HF_VERSION}, which renders alpha correctly; an unpinned\n"
                  f"     `npx hyperframes render` picks up whatever is latest and can hit it.\n"
                  f"     Fix: render the frames, then encode them yourself —\n"
                  f"       npx hyperframes@{HF_VERSION} render <comp> --format png-sequence --output frames/\n"
                  f"       ffmpeg -framerate 30 -i frames/%05d.png -c:v prores_ks -profile:v 4 "
                  f"-pix_fmt yuva444p10le {out}")
            _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                       render_seconds=render_seconds, fmt=a.format, ok=False)
            return 1
    # THE RENDER MUST PROVE ITSELF. Everything above this line checked the composition or the file's
    # metadata; none of it opens the rendered video and looks. That is how a render with every note
    # missing was reported as finished and good.
    _ok, _lines = _verify_render_has_content(out, d, strict=a.strict)
    if not _ok and sp_plan:
        # A layer stitched from stretches that reads as empty is never the last word: its page may show words the
        # stretches lost, and the full render is the route that has them (2026-10-31: a buyer's whole captions layer
        # was left out of her draft, and setting REEL_FULL_RENDER=1 by hand brought it back). A full render that is
        # empty too is the real answer, and goes on as before.
        print("  The stitched layer came out empty, so this layer renders full length instead.")
        _fb.note("render-spans", "the stitched layer came out empty; rendered the layer full length")
        sp_plan = None
        if _render_whole_again(d, out, a.format, _rnd_extra, _rnd_env, _html) == 0 and os.path.exists(out):
            _ok, _lines = _verify_render_has_content(out, d, strict=a.strict)
    for _l in _lines:
        print(_l)
    if not _ok:
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                   render_seconds=render_seconds, fmt=a.format, ok=False)
        st[key] = {"out": out, "ok": False}; _save(d, st)
        return 1

    sz_report = []
    if a.format == "mov" and not a.no_safe_zone:
        status, br = _safe_zone_check(out)
        sz_report = list(br)
        if status == "fullbleed":
            print("  ✓ safe zone: this layer only draws full-frame moments (a takeover or card that owns the "
                  "screen by design), so there is no overlay to hold to the bands.")
        elif status != "ok":
            # never a silent pass: say plainly that nothing was measured (or that the overlay is fully transparent)
            why = ("the overlay has NO solid ink in any frame — a fully transparent render is usually a broken one "
                   "(fonts? timeline?); inspect it before using it" if status == "empty" else status)
            print(f"\n  ⚠ SAFE-ZONE: not measured — {why}. This is NOT evidence of a clean overlay.")
        elif br:
            # REPORT mode by default (locked): this is a Layer-2 measurement of the FINAL alpha — `hyperframes check`
            # validates the canvas and has no concept of the platforms' UI bands. It never blocks a render that the
            # native check passed unless the caller opts into --safe-zone-strict, so an existing working build keeps
            # working while the breach is made visible.
            tag = "⛔" if a.safe_zone_strict else "⚠"
            print(f"\n  {tag} SAFE-ZONE: solid ink in the rendered overlay sits outside the safe zone "
                  "(product/safe_zones.py, strictest across Reels/TikTok/Shorts; measured on the final alpha — "
                  "the native check validates the canvas only):")
            for b in br:
                print(f"     • {b}")
            print(f"     Fix = move/fit the element inside safe_zones ({_sz_box()}) and re-render. "
                  "--safe-zone-strict makes this refuse; --no-safe-zone skips it for a deliberate full-canvas design.")
            if a.safe_zone_strict:
                print("     REFUSING (--safe-zone-strict). The file was kept for inspection but is NOT marked clean.")
                st[key] = {"out": out, "ok": False}; _save(d, st)
                _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                           render_seconds=render_seconds, fmt=a.format, ok=False)
                return 5
        else:
            print(f"  ✓ safe zone: every frame's solid ink is inside {_sz_box()}")

    # SUBJECT CHECK — said loudly, never a refusal: she always gets her reel (her rule). A layer on her face is
    # reported with where to move it, the file is delivered as placed, and fixing it is one layer re-rendered.
    # --no-subject skips the measure for a deliberate over/behind-the-subject treatment.
    subj_said = []
    if a.format == "mov" and not a.no_subject:
        s_status, s_lines = _subject_check(out, d, a.subject_max)
        if s_status.startswith("skipped"):
            print(f"\n  ⚠ SUBJECT: not measured — {s_status[9:]}.\n"
                  "     This is NOT evidence the layer is clear of her face.")
        elif s_status == "breach":
            print("")
            for ln in s_lines:
                print(f"  {ln}")
            print("     Fix = move it into an open zone (subject-zones.json → zones.above / below / left / "
                  "right, each already inside the platform band) and re-render that layer.")
            subj_said = [ln for ln in s_lines] + ["     (rendered as placed: she always gets her reel)"]
            print("     Rendered anyway, as placed: she always gets her reel. Tell her which look sits on her face and "
                  "offer to move it (one layer re-rendered).")
        else:
            for ln in s_lines:
                print(f"  {ln}")
    if sp_plan:
        # Where each stretch sits on the reel, for the consumers that lay one clip per stretch. A failed write
        # only means they use the whole file, which is exactly right too.
        try:
            _parts = getattr(_render_by_spans, "parts", None) or []
            render_spans.write_sidecar(out, sp_plan, parts=_parts if _parts and all(_parts) else None)
        except Exception:
            render_spans.drop_sidecar(out)
    st[key] = {"out": out, "ok": True, "sz": sz_report, **({"subject": subj_said} if subj_said else {}), **_out_stamp(out)}
    _save(d, st)
    print(f"\n  ✅ rendered → {os.path.relpath(out)}  ({'with the warnings above' if subj_said or _check_flagged else 'gated clean'}; cached — an identical re-run is a no-op)")
    _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                               render_seconds=render_seconds, fmt=a.format, ok=True)
    return 0


def _dur(path):
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", path]).strip())
    except Exception:
        return 0.0


def cmd_composite(a):
    base = os.path.abspath(a.base); layers = [os.path.abspath(x) for x in (a.layers or [])]
    out = os.path.abspath(a.output)
    for p in [base] + layers + ([os.path.abspath(a.audio)] if a.audio else []):
        if not os.path.exists(p):
            print(f"  ⛔ missing input: {p}"); return 2
    vdur = _dur(base)
    # The layers ARE the reel canvas (rendered at the composition size). If the base footage is a different
    # size (a 4K phone clip, a landscape source), overlay=0:0 pins the layer top-left unscaled — silently
    # misaligned (measured on a 2160x3840 base). Scale the base to the first layer's size and say so.
    cw = ch = None
    if layers:
        try:
            cw, ch = (int(x) for x in subprocess.check_output(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", layers[0]]).decode().strip().split(",")[:2])
        except Exception:
            cw = ch = None
    bw = bh = None
    try:
        import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from probe import display_dims as _display_dims   # the base is real footage: use its DISPLAYED size
        bw, bh = _display_dims(base)
        if not bw: bw = bh = None
    except Exception:
        pass
    if not bw:   # no video stream (an audio file, a corrupt clip) — say so instead of leaving a junk output behind
        print(f"  ⛔ --base has no video stream: {os.path.relpath(base)}  (pass the footage, not an audio file)")
        return 2
    base_fix = ""
    if cw and bw and (bw, bh) != (cw, ch):
        base_fix = f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},setsar=1,"
        print(f"  ⚠ base footage is {bw}x{bh} but the layers are {cw}x{ch}: scaling the base to the reel canvas "
              f"(cover + center-crop) so the graphics line up. Reframe the footage upstream for full control.")
    # VARIABLE frame rate (every raw phone clip: r=30/1 but avg=52000/1733) keeps variable timing through the
    # composite unless normalized; the spliced rough-cut is already CFR, but raw footage fed straight in is not.
    # Lock the base to the layers' constant rate so frame timing is deterministic.
    try:
        rfr, afr = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate",
             "-of", "csv=p=0", base]).decode().strip().split(",")[:2]
        # exact fraction compare: an iPhone grab reports r=30/1 vs avg=52000/1733 (30.006) — a float threshold
        # missed it; any mismatch between nominal and actual rate IS variable timing
        if rfr.strip() != afr.strip():
            lfr = "30"
            if layers:
                try: lfr = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                    "stream=r_frame_rate", "-of", "csv=p=0", layers[0]]).decode().strip() or "30"
                except Exception: pass
            base_fix += f"fps={lfr},"
            print(f"  ⚠ base footage is variable frame rate (nominal {rfr}, actual {afr}): locking it to {lfr} fps "
                  f"so the graphics stay frame-accurate. (Footage that went through the rough cut is already constant.)")
    except Exception:
        pass
    # OPTIONAL grade, footage only: goes into the base chain, so every transparent layer composited on top
    # keeps its pack colors exactly. Never applied unless --grade was passed (locked: optional, not built in).
    if a.grade:
        try:
            _g = grade_filter(a.grade)   # None for "none"/"off"/"no": an explicit no-grade is not an error
        except ValueError as e:
            sys.exit(f"  ✗ {e}")
        if _g:
            base_fix += _g + ","
            print(f"  ✓ grade '{a.grade}' on the footage only (layers untouched)")
    # A layer with NO alpha channel is not an overlay — it will fully cover the base and every layer under it.
    for l in layers:
        try:
            pf = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                          "stream=pix_fmt", "-of", "csv=p=0", l]).decode().strip()
            if pf and not pf.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")):   # the alpha-carrying families
                print(f"  ⚠ layer {os.path.relpath(l)} has no alpha channel ({pf}) — it is not transparent and will "
                      f"fully cover the base. Render overlays with --format mov (ProRes 4444) if that isn't intended.")
        except Exception:
            pass
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", base]
    for l in layers: cmd += ["-i", l]
    if a.audio: cmd += ["-i", a.audio]
    # stack: base, then each transparent layer on top in order. eof_action=pass: when a layer ENDS before the
    # base, release it (default 'repeat' FREEZES the layer's last frame over the rest of the reel — measured).
    fc, prev = "", "[0:v]"
    if base_fix:
        fc += f"[0:v]{base_fix.rstrip(',')}[b0];"; prev = "[b0]"
    for i in range(len(layers)):
        o = f"[v{i}]"; fc += f"{prev}[{i+1}:v]overlay=0:0:format=auto:eof_action=pass{o};"; prev = o
    fc += f"{prev}format=yuv420p[vout]"
    # One overlay per layer: a long graph goes to ffmpeg in a file (WinError 206 past 32,767 characters on Windows).
    gfile = out + ".graph.txt"
    cmd += [*graph_args(fc, gfile), "-map", "[vout]"]
    # Audio is ALWAYS transcoded to AAC (as the shipped build-reel-mp4.py does). `-c:a copy` wrote a PCM stream
    # into the .mp4 when the source was a ProRes/PCM export — non-standard, and Instagram/QuickTime reject or
    # mute it — while reporting success (measured).
    if a.audio:
        # NEVER let a short audio cut the video (-shortest did exactly that, silently). The VIDEO governs length;
        # a shorter audio simply ends (silent tail) and we say so.
        adur = _dur(a.audio)
        if adur and vdur and adur < vdur - 0.25:
            print(f"  ⚠ audio ({adur:.1f}s) is shorter than the video ({vdur:.1f}s): the last {vdur - adur:.1f}s "
                  f"will be silent. No video was cut.")
        cmd += ["-map", f"{len(layers)+1}:a:0"]
    else:
        # FIRST audio stream only: an iPhone .mov carries a timed-metadata stream (codec "none") that ffmpeg
        # classes as audio, and a broad `0:a?` selected it -> "no decoder found for: none" (measured).
        cmd += ["-map", "0:a:0?"]
    # No chapters from any input: a song given as --audio can carry its own (an Epidemic mp3 does), which outlasting
    # the reel made players show a longer reel with an empty stretch.
    cmd += ["-map_chapters", "-1", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    cmd += pick_encoder(vbr="16M", crf=a.crf, preset="medium", hw_on_mac=False)
    if vdur: cmd += ["-t", f"{vdur:.3f}"]      # video length governs; never -shortest
    cmd += [out]
    print("[composite]", os.path.relpath(base), "+", len(layers), "layer(s)", "+ audio" if a.audio else "", "→", os.path.relpath(out))
    try:
        rc = subprocess.run(cmd).returncode
    except FileNotFoundError:
        print("  ⛔ ffmpeg not found on PATH — run ./check-setup.sh (it prints the install command)."); return 4
    finally:
        remove_graph(gfile)
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        print("  ✅ composited"); return 0
    # never leave a junk / partial output behind that a later step could mistake for a finished reel
    try: os.remove(out)
    except OSError: pass
    print("  ⛔ composite failed (see ffmpeg error above) — no output written.")
    return rc or 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("render", help="gated + cached render of one composition")
    r.add_argument("target", help="composition dir or its index.html")
    r.add_argument("-o", "--output", required=True)
    r.add_argument("--format", default=None,
                   help="mov (transparent overlay) | mp4 (opaque) | webm. Default: inferred from the output extension.")
    r.add_argument("--strict", action="store_true", help="fail on check WARNINGS too (every-word-must-read comps)")
    r.add_argument("--no-contrast", action="store_true",
        help="skip the WCAG contrast pass — for a plate that reproduces a site "
             "verbatim, where the styling is not authored here")
    r.add_argument("--low-memory", action="store_true",
                   help="stream frames instead of buffering them to disk — slower, but a long transparent "
                        "comp needs ~15 GB of scratch per minute and will otherwise die partway through")
    r.add_argument("--force", action="store_true", help="ignore the cache; re-check + re-render")
    r.add_argument("--no-safe-zone", action="store_true",
                   help="skip the post-render Instagram safe-zone measurement (only for a deliberate full-canvas design)")
    r.add_argument("--safe-zone-strict", action="store_true",
                   help="REFUSE (exit 5) when the rendered overlay's solid ink leaves the safe zone (default: report only)")
    r.set_defaults(fn=cmd_render)
    r.add_argument("--no-subject", action="store_true",
                   help="skip the subject check (a deliberate over-the-subject or behind-the-subject treatment)")
    r.add_argument("--subject-max", type=float, default=None,
                   help="allowed fraction of the measured subject box a layer may cover (default 0.01)")
    c = sp.add_parser("composite", help="cheap ffmpeg stack: base + transparent layers (+ audio)")
    c.add_argument("--base", required=True); c.add_argument("--layers", nargs="*")
    c.add_argument("--audio"); c.add_argument("-o", "--output", required=True)
    c.add_argument("--crf", type=int, default=20)
    c.add_argument("--grade", default=None,
                   help="optional footage color grade, only when asked for: cinematic | warm | cool | film | mono")
    c.set_defaults(fn=cmd_composite)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
