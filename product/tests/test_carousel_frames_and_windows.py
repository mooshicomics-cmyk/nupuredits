# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "opencv-python-headless", "numpy",
#   "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]
# ///
"""Guards two carousel buyer reports (workflows/carousel/carousel.py).

  windows   On Windows every headless browser draw gets its own throwaway profile (removed afterwards), and the
            strips draw one at a time. Parallel strips sharing her own Chrome/Edge profile drew some slides before
            their fonts and photos loaded (a stand-in serif, a missing photo). A Mac keeps her own profile (a fresh
            one hangs headless there) and still draws side by side.
  frames    `carousel.py frames` reads the clip through ffmpeg, never OpenCV's own decoder: an 83 s iPhone HEVC clip
            sat inside OpenCV at 0% CPU for 5+ minutes. Here OpenCV's decoder is replaced by one that hangs, and the
            stills must still come out, from an HEVC clip.
  browser   a browser that has stopped dead on a Mac (no CPU) gets one more go on the HyperFrames browser; a slow one
            is never stopped. ffmpeg 9 removed -vsync, and nothing may still pass it.
  stall     a decode that stops making progress is stopped after FRAME_STALL seconds with a plain message, instead
            of sitting there forever.

Run: uv run product/tests/test_carousel_frames_and_windows.py   (or pytest under uv with opencv-python-headless)
"""
import importlib.util, os, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent.parent
CAROUSEL = ENGINE / "workflows" / "carousel" / "carousel.py"


def load():
    os.environ["CAROUSEL_SIMULATE_BUYER"] = "1"
    spec = importlib.util.spec_from_file_location("carousel_fw", CAROUSEL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _draws(m, platform):
    """The browser command lines two draws would run on `platform`, and whether each profile existed during its draw."""
    seen = []
    def fake_run(cmd, **kw):
        prof = next((c.split("=", 1)[1] for c in cmd if c.startswith("--user-data-dir=")), None)
        seen.append((cmd, prof, bool(prof and os.path.isdir(prof))))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    real_platform, real_run = sys.platform, m.subprocess.run
    m.chrome = lambda: ("chrome.exe", False)
    m.intel_mac = lambda: False
    m.physical_cores = lambda: 8
    try:
        sys.platform = platform
        m.subprocess.run = fake_run
        m._draw = fake_run
        m.run_chrome(["--dump-dom"], "http://127.0.0.1:1/a")
        m.run_chrome(["--dump-dom"], "http://127.0.0.1:1/b")
        workers = m.draw_workers() if hasattr(m, "draw_workers") else None
    finally:
        sys.platform, m.subprocess.run = real_platform, real_run
    return seen, workers


def test_windows_own_profile_per_draw():
    seen, workers = _draws(load(), "win32")
    profs = [p for _c, p, _e in seen]
    assert all(profs), f"a Windows draw ran on her own browser profile: {[c for c, _p, _e in seen]}"
    assert len(set(profs)) == 2, f"two draws shared one profile: {profs}"
    assert all(e for _c, _p, e in seen), "the throwaway profile did not exist while the browser drew"
    assert not any(os.path.exists(p) for p in profs), "a throwaway profile was left behind"
    assert workers == 1, f"Windows strips drew {workers} at a time"


def test_mac_keeps_own_profile():
    seen, workers = _draws(load(), "darwin")
    assert not any(p for _c, p, _e in seen), "a Mac draw got a fresh profile (that hangs headless on a Mac)"
    assert workers == 4, f"an Apple-chip Mac drew {workers} strips at a time"


class _HangingCapture:
    """OpenCV's decoder as it behaved on her HEVC clip: opens, reports frames, then never returns a frame."""
    def __init__(self, *a, **k): pass
    def get(self, prop): return 30.0 if prop == 5 else 180.0      # 5 = CAP_PROP_FPS, 7 = CAP_PROP_FRAME_COUNT
    def isOpened(self): return True
    def grab(self): time.sleep(3600); return False
    def read(self): time.sleep(3600); return False, None
    def retrieve(self): return False, None
    def set(self, *a): return True
    def release(self): pass


def _reel(tmp):
    raw = Path(tmp) / "projects" / "the-reel" / "raw"; raw.mkdir(parents=True)
    clip = raw / "IMG_0001.MOV"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=6",
                    "-c:v", "libx265", "-tag:v", "hvc1", "-pix_fmt", "yuv420p", "-x265-params", "log-level=error",
                    str(clip)], check=True)
    return clip


def _run_frames(m, timeout):
    box = {}
    def go():
        try: m.cmd_frames("the-job", "the-reel", 3); box["ok"] = True
        except SystemExit as e: box["exit"] = str(e)
        except Exception as e: box["error"] = repr(e)
    t = threading.Thread(target=go, daemon=True); t.start(); t.join(timeout)
    return t.is_alive(), box


def _needs_cv2():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        try:
            import pytest; pytest.skip("needs opencv (run under uv)")
        except ImportError:
            print("  SKIP  needs opencv (run under uv)")
        return False


def test_frames_never_decode_through_opencv():
    if not _needs_cv2(): return
    import cv2
    m = load()
    with tempfile.TemporaryDirectory() as tmp:
        _reel(tmp); m.ENGINE = Path(tmp)
        real = cv2.VideoCapture
        cv2.VideoCapture = _HangingCapture
        try:
            stuck, box = _run_frames(m, 90)
        finally:
            cv2.VideoCapture = real
        assert not stuck, "frames sat inside OpenCV's decoder and never finished"
        assert box.get("ok"), box
        got = sorted((Path(tmp) / "projects" / "the-job" / "carousel" / "photos").glob("frame-*.jpg"))
        assert len(got) == 3, got
        assert cv2.imread(str(got[0])).shape[:2] == (640, 360), "the still is not her clip at full size"


def test_frames_stall_is_stopped_plainly():
    if not _needs_cv2(): return
    m = load()
    with tempfile.TemporaryDirectory() as tmp:
        _reel(tmp); m.ENGINE = Path(tmp)
        fake = Path(tmp) / "fake_ffmpeg.py"
        fake.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        m.FFMPEG, m.FRAME_STALL = [sys.executable, str(fake)], 1
        t0 = time.monotonic()
        stuck, box = _run_frames(m, 30)
        assert not stuck, "a stalled read was never stopped"
        assert time.monotonic() - t0 < 20, "stopping a stalled read took far too long"
        msg = box.get("exit") or ""
        assert "stopped making progress" in msg and "Traceback" not in msg, box


def _script(tmp, name, body):
    p = Path(tmp) / name
    p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def test_browser_stopped_dead_gets_one_more_go():
    """A Brand Kit preview's second look: the browser sat at no CPU for 10 minutes, and the same draw took 10 s alone."""
    if sys.platform == "win32":
        return
    m = load()
    m.BROWSER_STALL = 2
    if m._cpu_seconds(os.getpgrp()) is None:          # no reading here (ps is refused in a sandbox): the browser just runs
        print("  ..   ps can't run here: skipping the stopped-dead leg")
        return
    with tempfile.TemporaryDirectory() as tmp:
        dead = _script(tmp, "dead", "sleep 600")
        spare = _script(tmp, "spare", "echo drawn")
        m.chrome = lambda: (dead, False)
        m._hf_browser = lambda: spare
        t0 = time.monotonic()
        done = m.run_chrome(["--dump-dom"], "http://127.0.0.1:1/a")
        assert done.stdout.strip() == "drawn", f"the second go did not draw: {done.stdout!r}"
        assert time.monotonic() - t0 < 60, "a browser stopped dead was waited on too long"
        m._hf_browser = lambda: None
        m.chrome = lambda: (dead, False)
        try:
            m.run_chrome(["--dump-dom"], "http://127.0.0.1:1/a")
            raise AssertionError("two dead draws in a row were not stopped")
        except SystemExit:
            pass


def test_slow_browser_is_never_stopped():
    """A browser that is working, however long it takes, runs to the end."""
    if sys.platform == "win32":
        return
    m = load()
    m.BROWSER_STALL = 2
    with tempfile.TemporaryDirectory() as tmp:
        busy = _script(tmp, "busy", f'"{sys.executable}" -c "import time;t=time.time()\nwhile time.time()-t<6: pass\nprint(\'drawn\')"')
        m.chrome = lambda: (busy, False)
        m._hf_browser = lambda: _script(tmp, "spare", "echo spare")
        done = m.run_chrome(["--dump-dom"], "http://127.0.0.1:1/a")
        assert done.stdout.strip() == "drawn", f"a working browser was stopped: {done.stdout!r}"


def test_no_option_ffmpeg_9_removed():
    """ffmpeg 9 removed -vsync, so carousel stills and the b-roll flicker check failed at once on every buyer on it."""
    hits = []
    for root in ("product", "workflows", "scripts", ".claude/skills"):
        for p in (ENGINE / root).rglob("*"):
            if p.suffix in (".py", ".sh", ".js", ".cjs", ".mjs") and p.is_file() and "tests" not in p.parts \
                    and "engine" not in p.parts and "node_modules" not in p.parts:
                try:
                    if '"-vsync"' in p.read_text(encoding="utf-8", errors="ignore"):
                        hits.append(str(p.relative_to(ENGINE)))
                except OSError:
                    pass
    assert not hits, f"-vsync is gone in ffmpeg 9, still used in: {hits}"


if __name__ == "__main__":
    bad = 0
    tests = [test_windows_own_profile_per_draw, test_mac_keeps_own_profile, test_frames_never_decode_through_opencv,
             test_frames_stall_is_stopped_plainly, test_browser_stopped_dead_gets_one_more_go,
             test_slow_browser_is_never_stopped, test_no_option_ffmpeg_9_removed]
    for fn in tests:
        try:
            fn(); print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  FAIL  {fn.__name__}: {str(e)[:500]}")
    print(f"test_carousel_frames_and_windows: {'all %d passed' % len(tests) if not bad else f'{bad} of {len(tests)} FAILED'}")
    sys.exit(1 if bad else 0)
