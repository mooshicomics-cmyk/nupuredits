#!/usr/bin/env python3
"""Guards: her preview copy is never shorter than her cut (a buyer, 2026-10-25: Play ran 0.1 s, then paused itself,
because her cut started past the end of a short preview copy that the engine kept reusing).

  short copy     a preview copy shorter than her script and cut need is made again on open/prepare, even when her
                 clips haven't changed (.preview-of matches): the old check looked at her clips, never at the copy
  short encode   an encode that "finishes" short (ffmpeg exit 0) is retried with the software decoder on a Mac, never
                 trusted as whole; still short from her own clips, it is kept, said once and not redone every open
  short clip     a clip in raw/ that is itself shorter than its words is named in plain words, never rebuilt for ever
  never in place a stopped encode leaves her old copy as it was (made beside it, swapped in only once whole)
  rebuild path   `visual_editor.py preview <job> --force` makes it again for Claude, and says the lengths

Run: python3 -m pytest product/tests/test_preview_length_2026_10_26.py -q   (or python3 <this file>)
"""
import json, os, shutil, subprocess, sys, tempfile, types

os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402


def _clip(path, secs):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=180x320:rate=30:duration={secs}",
                    "-f", "lavfi", "-i", f"sine=frequency=300:duration={secs}", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", path], check=True)


def _reel(clip_s=4, words_to=3.6):
    """A reel with one clip of clip_s seconds and words (and a cut) running to words_to seconds."""
    jd = tempfile.mkdtemp(prefix="ve-prevlen-")
    for d in ("raw", "transcript", "review"):
        os.makedirs(os.path.join(jd, d))
    _clip(os.path.join(jd, "raw", "a.mp4"), clip_s)
    n = 6
    words = [{"word": f"w{i}", "start": round(i * words_to / n, 3), "end": round((i + 0.8) * words_to / n, 3)} for i in range(n)]
    words[-1]["end"] = words_to
    json.dump({"clips": [{"clip": "a.mp4", "path": "", "duration": clip_s, "words": words}]},
              open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    json.dump({"segments": [{"clip": "a.mp4", "start": 0.0, "end": words_to, "transcript": ""}]},
              open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    return jd


def _pv(jd):
    return os.path.join(jd, "review", "preview.mp4")


def _counting(monkeypatch, short_s=None):
    """Count the preview encodes; with short_s, each one "finishes" (exit 0) with only short_s seconds of video."""
    calls, real = [], ve._watched_ffmpeg

    def fake(cmd, total, log, **k):
        calls.append(cmd)
        if short_s is None:
            return real(cmd, total, log, **k)
        _clip(cmd[-1], short_s)
        return types.SimpleNamespace(returncode=0, stderr="", stalled=False, done=short_s)
    monkeypatch.setattr(ve, "_watched_ffmpeg", fake)
    return calls


def test_a_short_copy_is_made_again_though_her_clips_did_not_change(monkeypatch):
    jd = _reel()
    try:
        ve.make_preview(jd, log=lambda *_: None)
        _clip(_pv(jd), 1)                               # her copy came out short once; .preview-of still matches
        calls, said = _counting(monkeypatch), []
        ve.make_preview(jd, log=said.append)
        assert calls, "a preview copy 3 s shorter than her cut was reused as it was"
        assert ve._duration(_pv(jd)) >= 3.6, ve._duration(_pv(jd))
        assert any("making it again" in s for s in said), said
        n = len(calls)
        ve.make_preview(jd, log=lambda *_: None)        # whole now: left alone
        assert len(calls) == n
        assert not ve.preview_length(jd)["short"]
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_an_unreadable_copy_is_made_again(monkeypatch):
    jd = _reel()
    try:
        ve.make_preview(jd, log=lambda *_: None)
        open(_pv(jd), "wb").write(b"\0" * 4000)          # a copy cut off before its index: nothing plays
        calls = _counting(monkeypatch)
        ve.make_preview(jd, log=lambda *_: None)
        assert calls and ve._duration(_pv(jd)) >= 3.6
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_an_encode_that_finishes_short_is_not_trusted(monkeypatch):
    jd = _reel()
    try:
        calls, said = _counting(monkeypatch, short_s=1), []
        ve.make_preview(jd, log=said.append)
        assert len(calls) == (2 if sys.platform == "darwin" else 1), len(calls)   # a Mac retries in software
        if sys.platform == "darwin":
            assert "-hwaccel" in calls[0] and "-hwaccel" not in calls[1]
        assert any("came out" in s and "needs" in s for s in said), said
        n = len(calls)
        ve.make_preview(jd, log=lambda *_: None)        # same clips, same short result: said, not redone every open
        assert len(calls) == n
        ve.make_preview(jd, force=True, log=lambda *_: None)
        assert len(calls) > n                           # --force always makes it again
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_a_stopped_encode_leaves_her_copy_as_it_was(monkeypatch):
    jd = _reel()
    try:
        ve.make_preview(jd, log=lambda *_: None)
        before = open(_pv(jd), "rb").read()

        def stopped(cmd, total, log, **k):
            open(cmd[-1], "wb").write(b"\0" * 5000)      # half a file, then killed
            return types.SimpleNamespace(returncode=-9, stderr="", stalled=True, done=1.0)
        monkeypatch.setattr(ve, "_watched_ffmpeg", stopped)
        try:
            ve.make_preview(jd, force=True, log=lambda *_: None)
            raise AssertionError("a stopped encode was not said")
        except ve.Refuse:
            pass
        assert open(_pv(jd), "rb").read() == before
        assert not os.path.exists(_pv(jd) + ".part.mp4")
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_a_clip_shorter_than_its_words_is_named_not_rebuilt_for_ever(monkeypatch):
    jd = _reel(clip_s=3, words_to=8.0)                  # a different, shorter file in raw/ under her clip's name
    try:
        said = []
        ve.make_preview(jd, log=said.append)
        assert any("'a.mp4'" in s and "shorter file" in s for s in said), said
        calls = _counting(monkeypatch)
        ve.make_preview(jd, log=lambda *_: None)
        assert not calls, "a copy as long as her clip allows was made again"
        assert ve.preview_length(jd)["clips"] == ["a.mp4"]
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_preview_force_on_the_command_line(monkeypatch, capsys):
    jd = _reel()
    try:
        ve.make_preview(jd, log=lambda *_: None)
        calls = _counting(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["visual_editor.py", "preview", jd, "--force"])
        ve.main()
        out = capsys.readouterr().out
        assert calls and "preview: 0:04 of footage, her cut needs 0:03 (ok)" in out, out
    finally:
        shutil.rmtree(jd, ignore_errors=True)


class _MonkeyPatch:
    """Just enough of pytest's monkeypatch to run this file with plain python3 (the ship gate has no pytest)."""
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)


class _Capsys:
    def __init__(self):
        import io
        self._buf, self._real = io.StringIO(), sys.stdout
        sys.stdout = self._buf

    def readouterr(self):
        out = self._buf.getvalue(); self._buf.seek(0); self._buf.truncate()
        return types.SimpleNamespace(out=out, err="")

    def close(self):
        sys.stdout = self._real


if __name__ == "__main__":
    import inspect
    failed = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        mp, cap = _MonkeyPatch(), None
        args = []
        for p_ in inspect.signature(fn).parameters:
            if p_ == "monkeypatch":
                args.append(mp)
            elif p_ == "capsys":
                cap = _Capsys(); args.append(cap)
        try:
            fn(*args)
            ok = True
        except Exception as e:  # noqa: BLE001
            ok, failed = False, failed + 1
            err = f"{type(e).__name__}: {e}"
        finally:
            if cap:
                cap.close()
            mp.undo()
        print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  " + err))
    print(f"{failed} failed" if failed else "preview length checks hold")
    sys.exit(1 if failed else 0)
