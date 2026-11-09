#!/usr/bin/env python3
"""workflows/head-framing.py and workflows/subject-zones.py measure her where she really is, and leave nothing
behind but their answer.

  shown_size  reads the DISPLAYED size. A phone filmed upright is often stored 1920x1080 with a rotation tag;
              the stored size made the face detector refuse the upright frames ffmpeg decodes.
  hair        on a source that is not 1080x1920 the hair search ran with the reframed frame's coordinates on
              the source frames, so it looked in the wrong place and fell back to the face centre. It now
              searches in source pixels beside the face it found, then converts to the 1080x1920 frame.
  stills      every frame sample left a temp folder of PNGs behind; stills now come off ffmpeg's pipe.
  zones       a run over one graphic's window (--range, --cuts) overwrote the whole-reel
              subject-zones.json that the subject check and every placement read.

The detector, the frame grabs and the crown search are stood in for where a case is about the arithmetic
around them, so this runs without OpenCV; the size reading and the stills run on a real two-second clip.

Run: python3 product/tests/test_head_framing_zones.py
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ff = load("head_framing_under_test", os.path.join("workflows", "head-framing.py"))
sz = load("subject_zones_under_test", os.path.join("workflows", "subject-zones.py"))


def quiet(fn, *a, **k):
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def main():
    tmp = tempfile.mkdtemp(prefix="head-framing-zones-")
    try:
        # ---- probe: displayed size, on real files ----------------------------------------------------------
        upright = os.path.join(tmp, "upright.mp4")
        stored = os.path.join(tmp, "stored-sideways.mp4")
        tagged = os.path.join(tmp, "tagged.mp4")
        ok = all(subprocess.run(a, capture_output=True).returncode == 0 for a in (
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=108x192:rate=10", "-t", "2",
             "-pix_fmt", "yuv420p", upright],
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", upright, "-vf", "transpose=1", "-pix_fmt", "yuv420p", stored],
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-display_rotation", "90", "-i", stored, "-c", "copy", tagged]))
        if ok:
            w, h, dur = ff.shown_size(upright)
            check("shown_size: an upright clip reads as stored", (w, h) == (108, 192) and abs(dur - 2.0) < 0.2, (w, h, dur))
            w, h, _d = ff.shown_size(tagged)
            check("shown_size: a rotation-tagged clip reads at its displayed size", (w, h) == (108, 192), (w, h))
            # ---- stills: read off ffmpeg's pipe, nothing written to disk -----------------------------------
            scratch = os.path.join(tmp, "scratch")
            os.makedirs(scratch)
            real_tmp = tempfile.tempdir
            tempfile.tempdir = scratch
            try:
                frames = ff.stills(tagged, ff.shown_size(tagged), count=3)
            finally:
                tempfile.tempdir = real_tmp
            check("stills returns the stills, upright", len(frames) == 3 and all(f.shape == (192, 108, 3) for f in frames),
                  [getattr(f, "shape", f) for f in frames])
            check("stills writes nothing to a scratch folder", os.listdir(scratch) == [], os.listdir(scratch))
        else:
            check("ffmpeg could build the test clips", False, "ffmpeg missing or failed")

        # ---- hair: searched in source pixels, reported in the 1080x1920 frame ----------------------------
        seen = {}
        def fake_rows(imgs, face):
            seen["args"] = (face.cx, face.top)
            return [1250] * len(imgs)
        for (w, h) in ((2160, 3840), (1080, 1920)):
            real = (ff.shown_size, ff.stills, ff.her_boxes, ff.crown_rows)
            ff.shown_size = lambda v, w=w, h=h: (w, h, 10.0)
            ff.stills = lambda v, size, **k: ["frame"] * 12
            ff.her_boxes = lambda imgs: [(900.0, 1400.0, 400.0, 400.0)] * len(imgs)
            ff.crown_rows = fake_rows
            try:
                rec = quiet(ff.measure, os.path.join(tmp, "not-a-job.mp4"))
            finally:
                ff.shown_size, ff.stills, ff.her_boxes, ff.crown_rows = real
            k = 1920 / h
            check(f"{w}x{h}: the crown is searched beside the face found in the source",
                  seen.get("args") == (1100.0, 1400.0), seen.get("args"))
            check(f"{w}x{h}: hair_top is reported in the 1080x1920 frame", rec.get("hair_top") == round(1250 * k), rec)
            # The 9:16 crop pull-reels reads from head-framing.json: only a source that is not 1080x1920 needs one,
            # and it is centred on the face found in the source (slid back inside the frame at an edge).
            crop = (rec.get("reframe") or {}).get("ffmpeg")
            if (w, h) == (1080, 1920):
                check(f"{w}x{h}: an already-vertical cut gets no crop", crop is None, rec.get("reframe"))
            else:
                cw = round(h * 9 / 16 / 2) * 2
                x = max(0, min(w - cw, round(1100.0 - cw / 2)))
                check(f"{w}x{h}: the 9:16 crop is centred on her face", crop == f"crop={cw}:{h}:{x}:0,scale=1080:1920",
                      crop)

        # ---- zones: only a whole-reel measurement writes the job's subject-zones.json --------------------
        out = os.path.join(tmp, "job", "outputs")
        os.makedirs(out)
        video = os.path.join(out, "job.mp4")
        zones = os.path.join(tmp, "job", "subject-zones.json")
        edl = os.path.join(tmp, "cuts.json")
        with open(edl, "w", encoding="utf-8") as fh:
            json.dump({"segments": [{"start": 0.0, "end": 10.0}]}, fh)
        # ---- the cut's clock: a moment on the cut lands on the same moment of the raw -------------------
        spans = os.path.join(tmp, "spans.json")
        with open(spans, "w", encoding="utf-8") as fh:
            json.dump({"segments": [{"start": 10.0, "end": 12.0}, {"start": 20.0, "end": 25.0}]}, fh)
        check("cuts.json maps the cut's seconds onto the raw",
              sz.timeline_to_raw(spans, [0.0, 1.5, 2.0, 6.9, 7.0]) == [10.0, 11.5, 20.0, 24.9, None],
              sz.timeline_to_raw(spans, [0.0, 1.5, 2.0, 6.9, 7.0]))
        check("the cut is as long as its kept spans", sz.timeline_length(spans) == 7.0)

        fz = sz.head_framing
        real = (fz.shown_size, fz.stills, fz.box_per_still, fz.crown_rows, sz._frames_on_timeline)
        fz.shown_size = lambda v: (1080, 1920, 10.0)
        fz.stills = lambda v, size, **k: ["frame"] * 16
        fz.box_per_still = lambda imgs: [(400.0, 500.0, 280.0, 300.0)] * len(imgs)
        fz.crown_rows = lambda imgs, face: [420] * len(imgs)
        sz._frames_on_timeline = lambda v, size, a, b, e, n: ["frame"] * n
        try:
            for label, kw, writes in (("whole reel", {}, True), ("a window that ends early", {"t1": 5.0}, False),
                                      ("a window that starts late", {"t0": 2.0}, False), ("--range", {"t0": 1.0, "t1": 3.0}, False),
                                      ("--cuts", {"cuts": edl, "t0": 0.0, "t1": 4.0}, False)):
                if os.path.exists(zones):
                    os.remove(zones)
                quiet(sz.measure, video, **kw)
                check(f"subject-zones.json {'written' if writes else 'left alone'} for {label}",
                      os.path.exists(zones) == writes)
            quiet(sz.measure, video)
            with open(zones, encoding="utf-8") as fh:
                whole = fh.read()
            quiet(sz.measure, video, t0=0.0, t1=5.0)
            with open(zones, encoding="utf-8") as fh:
                check("a window run leaves the whole-reel file exactly as it was", fh.read() == whole)
        finally:
            fz.shown_size, fz.stills, fz.box_per_still, fz.crown_rows, sz._frames_on_timeline = real
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_head_framing_zones: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_head_framing_zones: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
