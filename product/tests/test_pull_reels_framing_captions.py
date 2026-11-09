#!/usr/bin/env python3
"""pull-reels' cut-shorts.py: fill vs fit framing, and the style-pack caption route with its automatic fallback.

  framing   fill (the default) is the same face-or-middle crop as before; fit puts the WHOLE wide shot inside
            1080x1920 over a blurred fill. A reel's own "framing" in the plan wins over --framing.
  route     captions go through the style pack by default; --captions clean (or a reel's "captions": "clean")
            goes straight to Clean Captions.
  fallback  when the pack route fails for a reel, for any reason, Clean Captions runs for that reel and one line
            says so. A reel is never left uncaptioned.

The framing checks run real ffmpeg on a two-second synthetic wide clip (a red bar down the left edge, a blue one
down the right), so they take a few seconds. Every caption step is stood in for.

Run: python3 product/tests/test_pull_reels_framing_captions.py
"""
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


spec = importlib.util.spec_from_file_location(
    "cut_shorts_framing_under_test", os.path.join(ROOT, ".claude", "skills", "pull-reels", "scripts", "cut-shorts.py"))
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)


def quiet(fn, *a, **k):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            r = fn(*a, **k)
        except SystemExit as e:
            r = e
    return r, out.getvalue()


def pixel(video, x, y):
    """(r, g, b) of one pixel of the first frame."""
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(video), "-frames:v", "1",
                                   "-vf", f"crop=2:2:{x // 2 * 2}:{y // 2 * 2}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return tuple(raw[:3])


def reddish(p):
    return p[0] > 150 and p[1] < 90 and p[2] < 90


def bluish(p):
    return p[2] > 150 and p[0] < 90 and p[1] < 90


def wide_clip(path):
    """1920x1080, grey, a 60px red bar down the left edge and a 60px blue bar down the right."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=1920x1080:d=2:r=30",
                    "-vf", "drawbox=x=0:y=0:w=60:h=ih:color=red:t=fill,drawbox=x=iw-60:y=0:w=60:h=ih:color=blue:t=fill",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(path)], check=True)


def test_parse():
    verb, p, only, opts = mc.read_command(["build", "/x"])
    check("defaults: fill framing, pack captions, every reel", (verb, only, opts["framing"], opts["captions"])
          == ("build", None, "fill", "pack"), (verb, only, opts))
    _, _, only, opts = mc.read_command(["build", "/x", "a", "--framing", "fit", "--captions", "clean", "--pack",
                                        "Butter", "b"])
    check("--framing / --captions / --pack are read", (opts["framing"], opts["captions"], opts["pack"])
          == ("fit", "clean", "Butter"), opts)
    check("the words after the job are the reels, settings anywhere among them", only == ["a", "b"], only)
    verb, _, only, _ = mc.read_command(["set-up", "/x", "a"])
    check("set-up names its reels the same way", verb == "set-up" and only == ["a"], (verb, only))
    r, _ = quiet(mc.read_command, ["build", "/x", "--framing", "sideways"])
    check("an unknown framing stops with a plain reason", isinstance(r, SystemExit) and "fill, fit" in str(r.code), r)
    r, _ = quiet(mc.read_command, ["build", "/x", "--fast"])
    check("a setting it does not take stops instead of being ignored",
          isinstance(r, SystemExit) and "--fast" in str(r.code), r)
    for argv in ([], ["/x"], ["build"]):
        r, _ = quiet(mc.read_command, argv)
        check(f"no verb or no job prints the usage line ({argv})",
              isinstance(r, SystemExit) and "usage: cut-shorts.py set-up|build <job>" in str(r.code), r)


def test_choice():
    r, _ = quiet(mc._choice, {"framing": "fit"}, "framing", "fill", mc.FRAMINGS, "c")
    check("a reel's own framing wins over the batch", r == "fit", r)
    r, _ = quiet(mc._choice, {}, "framing", "fit", mc.FRAMINGS, "c")
    check("no reel framing: the batch's", r == "fit", r)
    r, said = quiet(mc._choice, {"framing": "zoomed"}, "framing", "fill", mc.FRAMINGS, "c")
    check("an unknown reel framing uses the batch's and says so", r == "fill" and "not one of" in said, said)


def test_framing(tmp):
    job = Path(tmp) / "job"
    (job / "outputs").mkdir(parents=True)
    src = Path(tmp) / "wide.mp4"
    wide_clip(src)
    real_run = mc._run
    ran = []

    def run_no_face(cmd, env=None):          # head-framing finds no face; ffmpeg really runs
        argv = [str(c) for c in cmd]
        ran.append(argv)
        if argv[:2] == ["uv", "run"]:
            return 1
        return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode

    mc._run = run_no_face
    try:
        # fill: exactly the old centre crop, and the edges are cut away
        shutil.copy2(src, job / "outputs" / "c.mp4")
        quiet(mc._vertical, job, "c")
        ff = [a for a in ran if a[0] == "ffmpeg"][-1]
        want = f"crop={mc._even(1080 * 9 / 16)}:1080:{max(0, (1920 - mc._even(1080 * 9 / 16)) // 4 * 2)}:0,scale=1080:1920"
        check("fill (the default) is the same middle crop as before", ff[ff.index("-vf") + 1] == want, ff)
        out = job / "outputs" / "c.mp4"
        check("fill: 1080x1920", mc._stored_size(out) == (1080, 1920), mc._stored_size(out))
        check("fill: the wide cut is kept beside it", (job / "outputs" / "c.wide.mp4").exists())
        check("fill: the side edges are trimmed", not reddish(pixel(out, 4, 960)) and not bluish(pixel(out, 1075, 960)),
              (pixel(out, 4, 960), pixel(out, 1075, 960)))

        # fit: the whole width is inside the frame, blurred fill above and below
        for f in (job / "outputs").iterdir():
            f.unlink()
        shutil.copy2(src, job / "outputs" / "c.mp4")
        ran.clear()
        quiet(mc._vertical, job, "c", "fit")
        check("fit does not ask head-framing (nothing is cropped)", not any(a[:2] == ["uv", "run"] for a in ran), ran)
        out = job / "outputs" / "c.mp4"
        check("fit: 1080x1920", mc._stored_size(out) == (1080, 1920), mc._stored_size(out))
        check("fit: the wide cut is kept beside it", (job / "outputs" / "c.wide.mp4").exists())
        check("fit: the left edge of the shot is visible", reddish(pixel(out, 8, 960)), pixel(out, 8, 960))
        check("fit: the right edge of the shot is visible", bluish(pixel(out, 1071, 960)), pixel(out, 1071, 960))

        top = pixel(out, 540, 200)
        check("fit: the band above is filled (blurred footage, not black)", sum(top) > 120, top)
        ran.clear()
        quiet(mc._measure_subject, job, "c", "fit")
        zc = [a for a in ran if a[:2] == ["uv", "run"]]
        check("fit: she is measured on a stand-in without the blurred copy of her face",
              zc and zc[0][3].endswith("fit-measure.mp4") and "--out" in zc[0], zc)
        ran.clear()
        quiet(mc._measure_subject, job, "c", "fill")
        zc = [a for a in ran if a[:2] == ["uv", "run"]]
        check("fill: she is measured on the base itself, as before", zc and zc[0][3].endswith("c.mp4"), zc)

        # vertical footage is used as is: sized only, never fitted over a blur
        for f in (job / "outputs").iterdir():
            f.unlink()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=720x1280:d=1:r=30",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                        str(job / "outputs" / "v.mp4")], check=True)
        ran.clear()
        quiet(mc._vertical, job, "v", "fit")
        ff = [a for a in ran if a[0] == "ffmpeg"][-1]
        check("fit on vertical footage only sizes it", ff[ff.index("-vf") + 1].startswith("scale=1080:1920"), ff)

        # a frame that does not encode leaves the cut exactly where and as it was, and nothing half-written
        for f in (job / "outputs").iterdir():
            f.unlink()
        shutil.copy2(src, job / "outputs" / "c.mp4")
        before = (job / "outputs" / "c.mp4").read_bytes()
        mc._run = lambda cmd, env=None: 1 if str(cmd[0]) == "ffmpeg" else 0
        r, _ = quiet(mc._vertical, job, "c", "fit")
        check("a failed frame stops that reel with a plain reason",
              isinstance(r, SystemExit) and "did not encode" in str(r.code), r)
        check("a failed frame leaves the cut untouched and no wide or framing file behind",
              (job / "outputs" / "c.mp4").read_bytes() == before
              and sorted(f.name for f in (job / "outputs").iterdir()) == ["c.mp4"],
              sorted(f.name for f in (job / "outputs").iterdir()))
        mc._run = run_no_face
    finally:
        mc._run = real_run


def test_routes(tmp):
    job = Path(tmp) / "rj"
    (job / "outputs").mkdir(parents=True)
    deliverable = job / "outputs" / "r.final.mp4"
    calls = []
    real = (mc._pack_captions, mc._clean_captions)
    clean_packs = []
    def clean_stub(j, n, c, d, framing="fill", pack=None, measured=False):
        calls.append("clean"); clean_packs.append(pack)
    mc._clean_captions = clean_stub
    try:
        def pack_ok(j, n, c, d, pack, framing="fill"):
            calls.append(("pack", pack)); return None
        mc._pack_captions = pack_ok
        calls.clear(); quiet(mc._captions, job, "r", {}, deliverable, "pack", "Butter")
        check("the default route is the style pack, and a pack success runs nothing else",
              calls == [("pack", "Butter")], calls)
        calls.clear(); quiet(mc._captions, job, "r", {}, deliverable, "clean", "Butter")
        check("--captions clean goes straight to Clean Captions", calls == ["clean"], calls)
        check("Clean Captions wears the batch's pack", clean_packs[-1:] == ["Butter"], clean_packs)

        # build_reel: the default route with no options is pack
        seen = {}
        real_b = (mc._run, mc._vertical, mc._captions, mc._export_copy)
        mc._run = lambda cmd, env=None: 0
        mc._vertical = lambda j, n, framing="fill": seen.__setitem__("framing", framing)
        mc._captions = lambda j, n, c, d, route="pack", pack=None, framing="fill": seen.update(route=route, pack=pack)
        mc._export_copy = lambda d, n: None
        try:
            quiet(mc.build_reel, job, "r", {})
            check("build_reel with no options: fill + pack", seen.get("framing") == "fill" and seen.get("route") == "pack",
                  seen)
            quiet(mc.build_reel, job, "r", {"framing": "fit", "captions": "clean"}, {"framing": "fill", "pack": "Butter"})
            check("a reel's plan fields pick its framing and caption route", seen.get("framing") == "fit"
                  and seen.get("route") == "clean", seen)
        finally:
            mc._run, mc._vertical, mc._captions, mc._export_copy = real_b

        # fallback: an exception, a reason, and a real step failure all end in Clean Captions
        def pack_raises(j, n, c, d, pack, framing="fill"):
            raise RuntimeError("renderer crashed")
        mc._pack_captions = pack_raises
        calls.clear(); _, said = quiet(mc._captions, job, "r", {}, deliverable, "pack", "Butter")
        check("a pack route that raises falls back to Clean Captions", calls == ["clean"], calls)
        check("the fallback is said in one plain line", said.count("gets Clean Captions instead") == 1
              and "renderer crashed" in said, said)
    finally:
        mc._pack_captions, mc._clean_captions = real

    # the real _pack_captions, with the render step failing: Clean Captions runs, deliverable path unchanged
    (job / "outputs" / "r.transcript.json").write_text(json.dumps({"words": [
        {"text": "the", "start": 0.1, "end": 0.3}, {"text": "hook", "start": 0.3, "end": 0.7},
        {"text": "rest", "start": 0.8, "end": 1.4}]}), encoding="utf-8")
    ran = []
    def fake_run(cmd, env=None):
        argv = [str(c) for c in cmd]
        ran.append((argv, dict(env or {})))
        return 1 if any(a.endswith("reel_render.py") for a in argv) else 0
    real_run = mc._run
    mc._run = fake_run
    try:
        _, said = quiet(mc._captions, job, "r", {"hook": ["the hook"]}, deliverable, "pack", "Butter")
    finally:
        mc._run = real_run
    typ = [e for a, e in ran if a[-1].endswith("build-reel-type.py")]
    check("the pack route builds the overlay for THIS reel folder in the chosen pack",
          typ and str(typ[0].get("JOB_DIR")) == str(job) and typ[0].get("STYLE_PACK") == "Butter", typ)
    clean = [a for a, _ in ran if any(x.endswith(os.path.join("clean-captions", "build.py")) for x in a)]
    check("a failed pack render runs the Clean Captions builder for that reel", len(clean) == 1, ran)
    check("the fallback builder writes the same deliverable", clean and clean[0][clean[0].index("--out") + 1]
          == str(deliverable), clean)
    check("the fallback line names why", "the pack overlay did not render" in said, said)
    plan = json.loads((job / "caption-plan.json").read_text(encoding="utf-8"))
    check("the reel's hook becomes the pack's hook", plan.get("hook") == ["the hook"], plan)
    check("with no hook_end, the hook ends after the words it covers", abs(plan.get("hook_end", 0) - 1.0) < 1e-6, plan)

    # no pack chosen: straight to Clean Captions, said once
    ran.clear()
    mc._run = fake_run
    try:
        _, said = quiet(mc._captions, job, "r", {}, deliverable, "pack", None)
    finally:
        mc._run = real_run
    check("no pack chosen: Clean Captions, and the line says why", "no style pack is chosen yet" in said
          and any(any(x.endswith(os.path.join("clean-captions", "build.py")) for x in a) for a, _ in ran), said)


def test_hook_placement(tmp):
    job = Path(tmp) / "hp"
    job.mkdir()
    keys, line = mc._hook_placement(job, 2.0)
    check("no measurement: the hook keeps its usual place", keys == {} and line is None, keys)
    def zones(above, below):
        (job / "subject-zones.json").write_text(json.dumps({"zones": {"above": above, "below": below}}),
                                                 encoding="utf-8")
    zones({"usable": True, "bottom": 700}, {"usable": True, "top": 1300})
    keys, _ = mc._hook_placement(job, 2.0)
    check("room above your head: the hook stays at the top", keys == {}, keys)
    zones({"usable": False, "bottom": 189}, {"usable": True, "top": 931, "bottom": 1620})
    keys, line = mc._hook_placement(job, 2.0)
    check("framed high: the hook moves to the open room under her chin",
          keys.get("hook_lift_px") == mc.HOOK_TOP_Y - 931 and line, keys)
    check("framed high: the captions wait out the hook", keys.get("caption_skip") == [[0.0, 2.0]], keys)
    zones({"usable": False, "bottom": 189}, {"usable": True, "top": 1561, "bottom": 1620})
    keys, _ = mc._hook_placement(job, 2.0)
    check("too little open room under her chin for the hook: nothing is moved", keys == {}, keys)
    zones({"usable": False, "bottom": 189}, {"usable": False, "top": 1500})
    keys, _ = mc._hook_placement(job, 2.0)
    check("no open room anywhere: nothing is moved (the render's own check decides)", keys == {}, keys)


def main():
    tmp = tempfile.mkdtemp(prefix="pull-reels-framing-")
    try:
        test_hook_placement(tmp)
        test_parse()
        test_choice()
        test_framing(tmp)
        test_routes(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_pull_reels_framing_captions: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_pull_reels_framing_captions: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
