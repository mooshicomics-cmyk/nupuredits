#!/usr/bin/env python3
"""bg_remove.py — the ONE way the engine runs HyperFrames' remove-background (her cutout).

remove-background does not fail when the folder it is told to write into does not exist: it waits forever, with
the ffmpeg feeding it blocked and nothing printed (measured: a build sat at 0% CPU for hours on a reel whose
broll/ folder had never been made). Every caller goes through here, so that can never happen again:

  * the output's folder is made first;
  * the tool writes to a hidden partial file beside the output, moved into place only once it finished, so a
    stopped run never leaves half a cutout where a later run would take it as done;
  * it runs under a time limit sized to the clip (TIME_BASE_S + TIME_PER_FRAME_S a frame, generous on purpose:
    the first run downloads the model and loads it with no output), in its own process group, and a run past
    that limit is stopped whole (npx, node, the ffmpeg under them) and said in plain words, never a hang;
  * a caller that can be stopped (the visual editor's Finish) hands in should_stop, and a stop ends the tool too.

  run(src, out, extra=(), should_stop=None, on_start=None, limit=None) -> out    raises CutoutFailed / Stopped
  time_limit(src)                                                         -> seconds this clip may take
  argv(src, out, extra=())                                                -> the npx command, at the pinned version

  python3 product/bg_remove.py <in> <out> [remove-background options...]     (exit 0 done, 1 failed, 130 stopped)

REELS_ENGINE_BG_REMOVE_SECONDS sets the limit by hand (a tester's slow machine). HyperFrames stays at the pin in
product.json (npx_run.hf_version), never @latest.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TIME_BASE_S = 180          # the model's first download and load, with no output, plus starting npx and node
TIME_PER_FRAME_S = 1.5     # a slow PC on the processor runs about 0.5 s a frame; three times that is a stall
TIME_UNKNOWN_S = 30 * 60   # a clip whose length cannot be read
STILLS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic")


class CutoutFailed(Exception):
    """remove-background did not make the cutout. The message is plain words, ready to say to her."""


class Stopped(Exception):
    """The caller's should_stop said stop (her Stop button); the tool was ended with it."""


def _frames(src):
    """How many frames remove-background works through, or None when the clip cannot be read."""
    if os.path.splitext(src)[1].lower() in STILLS:
        return 1
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_frames,avg_frame_rate,r_frame_rate:format=duration", "-of", "json", src],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        doc = json.loads(r.stdout or "{}")
    except Exception:   # noqa: BLE001  (no ffprobe, a clip it cannot read: the generous limit instead)
        return None
    st = (doc.get("streams") or [{}])[0]
    try:
        n = int(st.get("nb_frames") or 0)
        if n > 0:
            return n
    except (TypeError, ValueError):
        pass
    try:
        dur = float((doc.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        dur = 0.0
    fps = 0.0
    for k in ("avg_frame_rate", "r_frame_rate"):
        try:
            a, _, b = str(st.get(k) or "0/0").partition("/")
            fps = float(a) / float(b or 1)
        except (TypeError, ValueError, ZeroDivisionError):
            fps = 0.0
        if fps > 0:
            break
    if dur <= 0:
        return None
    return int(dur * (fps if 0 < fps < 241 else 30)) + 1


def time_limit(src):
    """Seconds this clip may take before the run counts as stalled."""
    v = os.environ.get("REELS_ENGINE_BG_REMOVE_SECONDS", "").strip()
    if v.isdigit() and int(v) > 0:
        return int(v)
    n = _frames(src)
    return TIME_UNKNOWN_S if n is None else int(TIME_BASE_S + TIME_PER_FRAME_S * n)


def argv(src, out, extra=()):
    """`npx hyperframes@<pin> remove-background <src> -o <out> [extra]`, the way this OS runs npx."""
    import npx_run
    return npx_run.npx_argv(f"hyperframes@{npx_run.hf_version()}", "remove-background", src, "-o", out, *extra)


def _partial(out):
    """The hidden file the tool writes before it is moved to `out`. Same extension: the format follows it."""
    d, name = os.path.split(os.path.abspath(out))
    stem, ext = os.path.splitext(name)
    return os.path.join(d, f".{stem}.partial-{os.getpid()}{ext}")


def _stop_tree(p):
    """End the tool and everything under it (npx, node, the ffmpeg feeding node), not just npx."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=30)
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:   # noqa: BLE001
        pass
    try:
        p.kill()
    except Exception:   # noqa: BLE001
        pass
    try:
        p.communicate(timeout=10)
    except Exception:   # noqa: BLE001
        pass


def _words(s):
    return f"{int(s)} seconds" if s < 120 else f"{int(round(s / 60.0))} minutes"


def run(src, out, extra=(), should_stop=None, on_start=None, limit=None):
    """Cut her out of `src` into `out` (its extension picks the format: .mov ProRes 4444, .webm VP9, .png a still).
    Returns `out`. Raises CutoutFailed (said plainly: why, and that nothing was changed) or Stopped."""
    src, out = os.path.abspath(src), os.path.abspath(out)
    if not os.path.isfile(src):
        raise CutoutFailed(f"the clip to make the cutout from is not there ({os.path.basename(src)}).")
    import npx_run
    if not npx_run.npx_path():
        raise CutoutFailed(npx_run.NO_NODE)
    os.makedirs(os.path.dirname(out), exist_ok=True)       # THE fix: without its folder the tool waits forever
    part = _partial(out)
    try:
        os.remove(part)
    except OSError:
        pass
    limit = int(limit or time_limit(src))
    kw = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)} if os.name == "nt" \
        else {"start_new_session": True}                  # its own group, so a stall is stopped whole
    try:
        p = subprocess.Popen(argv(src, part, extra), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **kw)
    except OSError as e:
        raise CutoutFailed(f"HyperFrames could not start ({e}). {npx_run.NO_NODE}")
    if on_start:
        try:
            on_start(p.pid)
        except Exception:   # noqa: BLE001  (a record that cannot be written never stops the cutout)
            pass
    t0, text = time.time(), ""
    try:
        while True:
            try:
                text, _ = p.communicate(timeout=0.5)        # reads as it waits, so a chatty tool never blocks
                break
            except subprocess.TimeoutExpired:
                if should_stop and should_stop():
                    _stop_tree(p)
                    raise Stopped("stopped")
                if time.time() - t0 > limit:
                    _stop_tree(p)
                    npx_run._fb().note("remove-background", f"stopped after {limit}s on {os.path.basename(src)} "
                                                            f"(no finish inside the clip's limit); nothing was changed")
                    raise CutoutFailed(
                        f"the cutout of {os.path.basename(src)} did not finish in {_words(limit)} (the limit for a "
                        f"clip this long), so it was stopped rather than left waiting. Nothing was changed. Run it "
                        f"again; if it stops the same way, /report-a-problem.")
    except BaseException as e:                              # a stall, her stop, Ctrl-C: no half cutout left behind
        if not isinstance(e, (CutoutFailed, Stopped)):
            _stop_tree(p)
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    if p.returncode != 0 or not os.path.isfile(part) or os.path.getsize(part) == 0:
        try:
            os.remove(part)
        except OSError:
            pass
        tail = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        why = tail[-1] if tail else (f"it exited {p.returncode}" if p.returncode else "it wrote nothing")
        raise CutoutFailed(f"the cutout of {os.path.basename(src)} did not finish: {why}. Nothing was changed.")
    os.replace(part, out)
    return out


def main(args):
    if len(args) < 2 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args and args[0] in ("-h", "--help") else 2
    def _term(*_):
        raise KeyboardInterrupt()                           # a stopped caller ends the tool too, never orphans it
    try:
        import signal
        signal.signal(signal.SIGTERM, _term)
    except (AttributeError, ValueError, OSError):
        pass
    try:
        run(args[0], args[1], extra=args[2:])
    except CutoutFailed as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, Stopped):
        print("stopped: the cutout was not made, and nothing was changed.", file=sys.stderr)
        return 130
    print(f"cutout -> {args[1]}")
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):                     # a cp1252 console on Windows can't print the status marks
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
