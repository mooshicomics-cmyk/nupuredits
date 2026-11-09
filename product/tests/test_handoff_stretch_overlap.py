#!/usr/bin/env python3
"""Guards a caption layer laid as stretches in her CapCut draft: no stretch may overlap the next one.

A buyer's CapCut export stopped with "add_video failed: New segment overlaps with existing segment [start:
40033333, end: 50500000]". Her caption layer went in as 7 stretches (render_spans parts). Each stretch's start and
length were rounded to 6 decimals on their own, so at 30 fps stretch 4 (at 30.466667, dur 9.566667) ended at
40.033334, 1 microsecond past stretch 5's start (40.033333), and CapCut refuses any overlap on one track.

  grid      stretch_spots puts every edge on whole microseconds and ends each stretch at or before the next start
  more      two more buyers' exact refusals (a layer starting at 0.107 s and at 1.044 s) place cleanly too
  handoff   the real handoff, fed her sidecar's numbers (old sidecars stay on buyers' disks), lays every stretch with
            no overlap as CapCut counts it, and still covers the whole layer (no gap opened between stretches)
  sidecar   a new sidecar writes each length as end minus start, so at + dur is exactly the next at

Runs the real handoff with the CapCut build engine replaced by a recorder (nothing reaches CapCut).

Run: python3 product/tests/test_handoff_stretch_overlap.py   (or with pytest)
"""
import contextlib, importlib.util, io, os, shutil, subprocess, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)

FPS = 30
# Her caption stretches, in frames at 30 fps (stretch 4 then 5 are the pair CapCut refused).
FRAMES = [(27, 210), (240, 480), (510, 880), (914, 1201), (1201, 1515), (1530, 1700), (1720, 1850)]


def old_parts(path):
    """The sidecar as the engine wrote it before the fix: at and dur each rounded on their own."""
    return [(path, round(a / FPS, 6), round((b - a) / FPS, 6)) for a, b in FRAMES]


def _capcut_tim():
    """CapCut's own seconds -> microseconds (the vendored pyJianYingDraft), else the same rule written out."""
    tu = os.path.join(PRODUCT, "engine", "VectCutAPI", "pyJianYingDraft", "time_util.py")
    if os.path.isfile(tu):
        spec = importlib.util.spec_from_file_location("_cc_time_util", tu)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m.tim
    return lambda s: int(round(float(s.rstrip("s")) * 1_000_000))


def capcut_ranges(adds):
    """[(start_us, end_us)] the way add_video_track builds them: trange(f"{target_start}s", f"{end - start}s")."""
    tim = _capcut_tim()
    out = []
    for kw in adds:
        s = tim(f"{kw['target_start']}s")
        out.append((s, s + tim(f"{kw['end'] - kw['start']}s")))
    return out


def overlaps(rs):
    rs = sorted(rs)
    return [(a, b) for a, b in zip(rs, rs[1:]) if b[0] < a[1]]


def test_grid():
    import capcut_handoff as H
    spots = H.stretch_spots(0.0, old_parts("c.mov"))
    rs = [(round(t * H.US), round((t + d) * H.US)) for _p, t, d in spots]
    assert not overlaps(rs), overlaps(rs)
    for _p, t, d in spots:
        assert abs(t * H.US - round(t * H.US)) < 1e-6 and abs(d * H.US - round(d * H.US)) < 1e-6, (t, d)
    # an offset layer start must not reopen the overlap
    spots = H.stretch_spots(2.123457, old_parts("c.mov"))
    rs = [(round(t * H.US), round((t + d) * H.US)) for _p, t, d in spots]
    assert not overlaps(rs), overlaps(rs)
    # footage ending inside a stretch still trims it
    spots = H.stretch_spots(0.0, old_parts("c.mov"), lambda at, ln: max(0.0, min(ln, 45.0 - at)))
    assert abs(spots[4][1] + spots[4][2] - 45.0) < 1e-6 and spots[5][2] == 0.0, spots


# Two more buyers' exact refusals (2026-10-26), each a caption layer starting a little after 0:00, its sidecar written
# the old way. (layer start, [(at, dur) of the stretch pair], CapCut's refused range in microseconds)
MORE = [(0.107, [(20.866667, 9.466667), (30.333333, 10.166667)], (30440333, 40607000)),
        (1.044, [(round(611 / FPS, 6), round(296 / FPS, 6)), (round(907 / FPS, 6), round(311 / FPS, 6))], (31277333, 41644000))]


def test_more_buyers():
    import capcut_handoff as H
    tim = _capcut_tim()
    for at, pair, refused in MORE:
        parts = [(f"s{i}.mov", pa, d) for i, (pa, d) in enumerate(pair)]
        old = [(round((at + pa) * H.US), round((at + pa) * H.US) + round(d * H.US)) for _p, pa, d in parts]
        assert overlaps(old) and old[1] == refused, ("the old placement reproduces her refusal", old, refused)
        rs = []
        for _p, t, d in H.stretch_spots(at, parts):
            s = tim(f"{t}s"); rs.append((s, s + tim(f"{d}s")))
        assert not overlaps(rs), f"CapCut would refuse: {overlaps(rs)}"
        assert rs[0][1] == rs[1][0], ("the stretches still meet, no gap opened", rs)


def _mov(path, seconds, alpha=False):
    src = (f"color=c=white@0.0:size=180x320:rate={FPS}:duration={seconds:.2f},format=rgba" if alpha
           else f"testsrc2=size=180x320:rate={FPS}:duration={seconds:.2f}")
    enc = (["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"] if alpha
           else ["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, *enc, path], check=True)


def test_handoff():
    tmp = tempfile.mkdtemp(prefix="handoff-stretch-")
    try:
        root = os.path.join(tmp, "engine"); jd = os.path.join(root, "projects", "tiny")
        for d in ("outputs", "layers", "review"):
            os.makedirs(os.path.join(jd, d))
        base = os.path.join(jd, "outputs", "tiny.mp4")
        _mov(base, 63.0)
        cap = os.path.join(jd, "layers", "captions.mov")
        _mov(cap, 63.0, alpha=True)

        sys.modules.setdefault("requests", types.ModuleType("requests"))
        import capcut_handoff as H, draft_safety, cleanyap, capcut_tail, capcut_alpha, render_spans
        calls = []

        def rec(ep, **kw):
            calls.append((ep, kw))
            return {"draft_id": "test"} if ep == "create_draft" else {}
        saved = (H.call, H.ROOT, render_spans.parts, capcut_alpha.for_capcut, capcut_alpha.ready)
        H.call, H.ROOT = rec, root
        draft_safety.require_capcut_quit = lambda *a, **k: None
        draft_safety.next_version = lambda *a, **k: "tiny 1.1"
        cleanyap.finalize = lambda *a, **k: "tiny 1.1"
        capcut_tail.tailed_base = lambda jd, base, bdur, *a, **k: (base, 0.0)
        capcut_alpha.for_capcut = lambda p: p
        capcut_alpha.ready = lambda p: True
        render_spans.parts = lambda fp: old_parts(fp) if fp == cap else None

        argv, out = sys.argv, io.StringIO()
        sys.argv = ["capcut_handoff.py", "tiny", "--no-overlay", "--pack", "Butter", "--one-clip",
                    "--layer", f"captions={cap}"]
        try:
            with contextlib.redirect_stdout(out):
                H.main()
        except SystemExit as e:
            assert not e.code, f"exit {e.code}: {out.getvalue()[-400:]}"
        finally:
            sys.argv = argv
            H.call, H.ROOT, render_spans.parts, capcut_alpha.for_capcut, capcut_alpha.ready = saved
        adds = [kw for ep, kw in calls if ep == "add_video" and kw.get("track_name") == "captions"]
        assert len(adds) == len(FRAMES), adds
        rs = capcut_ranges(adds)
        assert not overlaps(rs), f"CapCut would refuse: {overlaps(rs)}"
        for (a, b), (s, e) in zip(FRAMES, sorted(rs)):          # each stretch still where it was, to the microsecond
            assert abs(s - a / FPS * 1e6) <= 1 and abs(e - b / FPS * 1e6) <= 1, ((a, b), (s, e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sidecar():
    import render_spans as R
    with tempfile.TemporaryDirectory() as t:
        mov = os.path.join(t, "captions.mov")
        open(mov, "wb").write(b"x" * 10)
        doc = R.write_sidecar(mov, {"fps": FPS, "frames": 1900, "spans": [list(f) for f in FRAMES]})
        sp = doc["spans"]
        for x, y in zip(sp, sp[1:]):
            if x["frames"][1] == y["frames"][0]:
                assert round(x["at"] + x["dur"], 6) == y["at"], (x, y)


if __name__ == "__main__":
    bad = 0
    for fn in (test_grid, test_more_buyers, test_handoff, test_sidecar):
        try:
            fn(); print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  FAIL  {fn.__name__}: {str(e)[:500]}")
    print(f"test_handoff_stretch_overlap: {'all 4 passed' if not bad else f'{bad} of 4 FAILED'}")
    sys.exit(1 if bad else 0)
