#!/usr/bin/env python3
"""Guards: her preview copy (review/preview.mp4) keeps her lips on her words, and plays at her cut's level (a buyer,
2026-10-26: "my lips aren't syncing to the words" in the visual editor, while her stitched cut played in sync).

The page now plays her voice from the video element itself in every browser (editor.html pbVoice; the page side is
held by test_editor_page_reports_2026_10_26.py). An element's volume stops at 100%, and her unmastered phone voice sits
about 15 dB under her cut, so the preview copy is made at her cut's level, and a copy made the old way is made again
on the next open after the update.

  in step       an iPhone-like clip (variable frame timing, the picture's second frame 0.23 s after its first, AAC
                with its priming skipped by an edit list) comes out of the preview build with every flash and its beep
                within one frame of each other, for one clip and for two clips back to back
  her level     a quiet phone voice comes out at her cut's level (the north star, -16 LUFS), still in step
  made again    a copy on disk from the old recipe (the stamp has no recipe) is made again on the next open, then left
                alone; --force still makes it again

Run: python3 product/tests/test_preview_sync_2026_10_26.py   (or python3 -m pytest <this file> -q)
"""
import json, math, os, shutil, struct, subprocess, sys, tempfile, wave

os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402
import audio_levels  # noqa: E402
import voice_level  # noqa: E402

EVENTS = [1.0, 2.5, 4.1, 5.6, 7.2]
FRAME = 1 / 30 + 0.002


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if r.returncode:
        raise RuntimeError(r.stderr[-1500:])
    return r.stdout


def _aac():
    enc = _run(["ffmpeg", "-hide_banner", "-encoders"])
    return "aac_at" if " aac_at " in enc else "aac"        # AudioToolbox primes 2112 samples, as an iPhone does


def _flashes(path):
    # by name from its own folder: a Windows path's drive colon would break the filter's own syntax
    out = json.loads(_run(["ffprobe", "-v", "error", "-f", "lavfi", "-i", f"movie='{os.path.basename(path)}',signalstats",
                           "-show_entries", "frame=pts_time:frame_tags=lavfi.signalstats.YAVG", "-of", "json"],
                          cwd=os.path.dirname(os.path.abspath(path))))
    got, prev = [], False
    for f in out["frames"]:
        hi = float(f["tags"]["lavfi.signalstats.YAVG"]) > 140
        if hi and not prev:
            got.append(float(f["pts_time"]))
        prev = hi
    return got


def _beeps(path, floor=-30):
    out = json.loads(_run(["ffprobe", "-v", "error", "-f", "lavfi", "-i",
                           f"amovie='{os.path.basename(path)}',silencedetect=n={floor}dB:d=0.1",
                           "-show_entries", "frame_tags=lavfi.silence_end", "-of", "json"],
                          cwd=os.path.dirname(os.path.abspath(path))))
    return [float(f["tags"]["lavfi.silence_end"]) for f in out["frames"] if (f.get("tags") or {}).get("lavfi.silence_end")]


def _phone_clip(path, amp=20000, gap=0.23, secs=8.5):
    """Grey frames with a white flash at each event, a 1 kHz beep under each flash. The picture's frames are stamped
    one by one: the first at 0, the second `gap` later, then about 29.8 fps with a wobble (a phone's variable timing)."""
    d = tempfile.mkdtemp(prefix="phone-", dir=os.path.dirname(path))
    try:
        n = int(secs * 29.8)
        ts = [0.0] + [gap + (k - 1) / 29.8 + 0.006 * math.sin(1.7 * k) for k in range(1, n)]
        flash = sorted({min(range(n), key=lambda i: abs(ts[i] - e)) for e in EVENTS})
        vid = os.path.join(d, "v.mov")
        stamp = f"if(eq(N,0),0,({gap}+(N-1)/29.8+0.006*sin(1.7*N))/TB)"
        _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x282828:s=180x320:r=30:d={n / 30 + 1:.3f}",
              "-vf", "geq=lum='if(" + "+".join(f"eq(N,{i})" for i in flash) + ",235,40)':cb=128:cr=128,format=yuv420p",
              "-frames:v", str(n), "-c:v", "libx264", "-bf", "0", "-enc_time_base", "1/600", "-video_track_timescale", "600",
              "-bsf:v", f"setts=ts='{stamp}'", vid])
        at = _flashes(vid)                                # where each flash really sits: the beep goes right there
        sr, pcm = 44100, [0] * int(secs * 44100)
        for e in at:
            s0 = int(round(e * sr))
            for k in range(int(0.06 * sr)):
                if s0 + k < len(pcm):
                    pcm[s0 + k] = int(amp * math.sin(2 * math.pi * 1000 * k / sr))
        wav = os.path.join(d, "a.wav")
        with wave.open(wav, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))
        _run(["ffmpeg", "-v", "error", "-y", "-i", vid, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
              "-c:a", _aac(), "-b:a", "64k", "-ac", "1", path])
        return at
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _reel(clips):
    """A reel whose raw/ holds the given phone clips (words over each, a cut through each)."""
    jd = tempfile.mkdtemp(prefix="ve-sync-")
    for d in ("raw", "transcript", "review"):
        os.makedirs(os.path.join(jd, d))
    meta = []
    for i, kw in enumerate(clips):
        name = f"IMG_{i:04d}.MOV"
        _phone_clip(os.path.join(jd, "raw", name), **kw)
        dur = ve._duration(os.path.join(jd, "raw", name))
        meta.append({"clip": name, "path": "", "duration": dur,
                     "words": [{"word": "w", "start": 0.5, "end": round(dur - 0.6, 3)}]})
    json.dump({"clips": meta}, open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    json.dump({"segments": [{"clip": c["clip"], "start": 0.0, "end": round(c["duration"] - 0.4, 3), "transcript": ""}
                            for c in meta]}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    return jd


def _pv(jd):
    return os.path.join(jd, "review", "preview.mp4")


def _in_step(path, n, floor=-30):
    f, b = _flashes(path), _beeps(path, floor)
    assert len(f) == n and len(b) == n, (f, b)
    off = [round(bb - ff, 3) for ff, bb in zip(f, b)]
    assert all(abs(o) <= FRAME for o in off), f"sound vs picture (s) per flash: {off}"
    return off


def test_a_phone_clip_stays_in_step_in_the_preview():
    jd = _reel([{}, {"gap": 0.1}])
    try:
        src = os.path.join(jd, "raw", "IMG_0000.MOV")
        _in_step(src, len(EVENTS))                        # the clip itself is in step (the fixture is right)
        ve.make_preview(jd, log=lambda *_: None)
        _in_step(_pv(jd), 2 * len(EVENTS))                # one clip, and the second one after it
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_a_quiet_phone_voice_comes_out_at_her_cuts_level():
    jd = _reel([{"amp": 1200}])
    try:
        before, _ = voice_level.measure(os.path.join(jd, "raw", "IMG_0000.MOV"))
        ve.make_preview(jd, log=lambda *_: None)
        after, peak = voice_level.measure(_pv(jd))
        assert before is not None and before < audio_levels.VOICE_TARGET_LUFS - 10, before
        assert after is not None and abs(after - audio_levels.VOICE_TARGET_LUFS) <= 1.0, (before, after)
        assert peak is None or peak <= audio_levels.TRUE_PEAK_CEILING_DBTP + 0.5, peak
        _in_step(_pv(jd), len(EVENTS))                    # levelled, still in step
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_a_copy_from_the_old_recipe_is_made_again_once():
    jd = _reel([{"amp": 1200}])
    try:
        ve.make_preview(jd, log=lambda *_: None)
        paths = [os.path.join(jd, "raw", "IMG_0000.MOV")]
        old = json.dumps([[os.path.basename(p), os.path.getsize(p), int(os.path.getmtime(p))] for p in paths])
        open(os.path.join(jd, "review", ".preview-of"), "w", encoding="utf-8").write(old)   # stamped before this update
        calls, real = [], ve._watched_ffmpeg

        def counting(cmd, total, log, **k):
            calls.append(cmd)
            return real(cmd, total, log, **k)
        ve._watched_ffmpeg = counting
        try:
            said = []
            ve.make_preview(jd, log=said.append)
            assert len(calls) == 1, "a preview copy made by the old recipe was kept after the update"
            assert any("earlier version of the engine" in x for x in said), said
            ve.make_preview(jd, log=lambda *_: None)
            assert len(calls) == 1, "a copy from this recipe was made again for nothing"
            ve.make_preview(jd, force=True, log=lambda *_: None)
            assert len(calls) == 2, "--force no longer makes it again"
        finally:
            ve._watched_ffmpeg = real
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def main():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("test_preview_sync_2026_10_26: skipped (no ffmpeg here)")
        return 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            bad += 1
            print(f"  FAIL  {t.__name__}: {str(e)[-600:]}")
    print(f"test_preview_sync_2026_10_26: {'FAIL ' + str(bad) if bad else 'all passed'} ({len(tests)} checks)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
