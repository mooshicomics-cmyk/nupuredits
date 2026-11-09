#!/usr/bin/env python3
"""Guards the END of her CapCut draft (2026-10-16): no black after her last clip, and her last clip can be extended.

  ends      every overlay and sound ends with her footage: a captions layer rendered a beat longer than the cut ran on
            past her last clip and CapCut played black there
  extends   her clips are cut from a copy of her cut with her own footage after the last line (capcut_tail.py), so the
            last clip has room to drag longer, like every other clip; the clips keep exactly their times
  matches   that copy is her cut, frame for frame and at her voice level, until the extra footage begins
  safe      a cut with nothing after it in her clip, or a base that isn't her plain cut, just hands the cut back

Builds a tiny reel (a test clip with tone, cut into two lines), runs the real handoff with the CapCut build engine
replaced by a recorder (nothing reaches CapCut).

Run: python3 product/tests/test_handoff_end.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}  -- {detail}")


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout or 0)


def main():
    tmp = tempfile.mkdtemp(prefix="handoff-end-")
    try:
        root = os.path.join(tmp, "engine"); jd = os.path.join(root, "projects", "tiny")
        for d in ("raw", "transcript", "outputs", "layers"):
            os.makedirs(os.path.join(jd, d))
        raw = os.path.join(jd, "raw", "clip.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=8",
                        "-f", "lavfi", "-i", "sine=frequency=220:duration=8", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", raw], check=True)
        segs = [{"clip": "clip.mp4", "start": 1.0, "end": 2.5, "keep_edges": True, "transcript": "one"},
                {"clip": "clip.mp4", "start": 3.0, "end": 5.0, "keep_edges": True, "transcript": "two"}]
        json.dump({"segments": segs}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
        base = os.path.join(jd, "outputs", "tiny.mp4")       # her cut: the two lines, back to back
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-filter_complex",
                        "[0:v]trim=1:2.5,setpts=PTS-STARTPTS[v0];[0:a]atrim=1:2.5,asetpts=PTS-STARTPTS[a0];"
                        "[0:v]trim=3:5,setpts=PTS-STARTPTS[v1];[0:a]atrim=3:5,asetpts=PTS-STARTPTS[a1];"
                        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", base], check=True)
        bdur = dur(base)
        cap = os.path.join(jd, "layers", "captions.mov")    # a captions layer rendered longer than the cut
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=white@0.0:size=360x640:rate=30:duration={bdur + 0.6:.2f},format=rgba",
                        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", cap], check=True)

        import capcut_tail
        path, tail = capcut_tail.tailed_base(jd, base, bdur)
        check("extends: there is footage after her last clip", tail >= 1.0 and os.path.isfile(path), (path, tail))
        check("extends: the copy is her cut plus that footage", abs(dur(path) - (bdur + tail)) < 0.12, (dur(path), bdur, tail))
        frame = lambda p, t: subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", p, "-frames:v", "1", "-vf",
                                             "scale=36:64,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        a, b = frame(base, 2.6), frame(path, 2.6)
        check("matches: the same picture as her cut before the extra footage", a and b and sum(abs(x - y) for x, y in zip(a, b)) / len(a) < 6)
        again, _ = capcut_tail.tailed_base(jd, base, bdur)
        check("matches: made once, then reused", again == path)
        check("safe: a base that isn't her plain cut gets no tail", capcut_tail.tailed_base(jd, base, bdur + 3)[1] == 0.0)

        import types
        sys.modules.setdefault("requests", types.ModuleType("requests"))   # the CapCut engine is replaced below
        import capcut_handoff as H, draft_safety, cleanyap
        calls = []

        def rec(ep, **kw):
            calls.append((ep, kw))
            return {"draft_id": "test"} if ep == "create_draft" else {}
        H.call, H.ROOT = rec, root
        draft_safety.require_capcut_quit = lambda *a, **k: None
        draft_safety.next_version = lambda *a, **k: "tiny 1.1"
        cleanyap.finalize = lambda *a, **k: "tiny 1.1"
        argv = sys.argv
        sys.argv = ["capcut_handoff.py", "tiny", "--no-overlay", "--pack", "Butter", "--layer", f"captions={cap}@0"]
        try:
            H.main()
        except SystemExit:
            pass
        except Exception as e:
            check("the handoff ran", False, repr(e))
        finally:
            sys.argv = argv
        main_clips = [kw for ep, kw in calls if ep == "add_video" and kw.get("track_name") == "main"]
        others = [kw for ep, kw in calls if ep in ("add_video", "add_audio") and kw.get("track_name") != "main"]
        check("extends: every clip comes from the copy with footage after it", main_clips and all(k["video_url"] == path for k in main_clips), main_clips)
        check("extends: the clips keep their times, the last ending with her cut", main_clips and abs(main_clips[-1]["end"] - bdur) < 0.05, main_clips[-1:] if main_clips else None)
        check("ends: no overlay or sound outlasts her footage", others and all(k["target_start"] + (k["end"] - k["start"]) <= bdur + 0.01 for k in others),
              [(k.get("track_name"), k["target_start"], k["end"]) for k in others])

        short = os.path.join(tmp, "s"); os.makedirs(os.path.join(short, "transcript")); os.makedirs(os.path.join(short, "raw"))
        shutil.copy(raw, os.path.join(short, "raw", "clip.mp4"))
        json.dump({"segments": [{"clip": "clip.mp4", "start": 6.0, "end": 7.98}]}, open(os.path.join(short, "transcript", "cuts.json"), "w", encoding="utf-8"))
        check("safe: a last line that ends with her clip gets no tail", capcut_tail.tailed_base(short, base, 1.98, log=lambda *a: None)[1] == 0.0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_handoff_end: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f[:500])
        return 1
    print(f"test_handoff_end: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
