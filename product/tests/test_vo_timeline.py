#!/usr/bin/env python3
"""A voiceover reel keeps every shot, sound and line number where the plan put it.

THE BUGS THIS EXISTS FOR (all found in one review of the voiceover path):
  1. Ken Burns holds read one input frame per output frame, so a 2 s hold played 1 s of a 60 fps clip at
     double speed and 2.5 s of a 24 fps one. The picture now runs at 30 fps before the zoom.
  2. vo-ambience.py cut every sound to the planned length, while vo-build.py renders whole frames (a 0.55 s
     shot is 17 frames), holds a clip's last frame when a shot asks for more than the clip has, and uses the
     pace's burst length (0.55 s on an emotional reel) when the plan names none; the ambience read 0.35 s
     there. Every sound drifted further off its shot down the reel. Each piece is now exactly its shot.
  3. vo-listen.py numbered its slides 1..N from the spliced grid, but vo-splice.py --cut counts the lines of
     the original grid, so after one cut "cut line 7" removed a different line. Slides now carry the original
     line numbers.
  4. A .caf voiceover was accepted at intake but no voiceover script would open one.

Run: python3 product/tests/test_vo_timeline.py      (small synthetic clips, about 20 s)
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PRODUCT = os.path.join(ROOT, "product")
sys.path.insert(0, PRODUCT)
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), os.path.join(PRODUCT, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", p]))


def src_frames(path):
    """Which source frame each output frame shows: the source's luma is 20 + 2*frame index."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "crop=64:64:(iw-64)/2:(ih-64)/2",
                          "-pix_fmt", "yuv420p", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return [round((sum(raw[i * 6144:i * 6144 + 4096]) / 4096 - 20) / 2) for i in range(len(raw) // 6144)]


def main():
    tmp = tempfile.mkdtemp()
    try:
        vb, amb, listen = load("vo-build.py"), load("vo-ambience.py"), load("vo-listen.py")

        # 1. a 2 s Ken Burns hold covers 2 s of its clip at any frame rate
        for fps in (24, 30, 60):
            src = os.path.join(tmp, f"idx{fps}.mp4")
            ff("-f", "lavfi", "-i", f"color=c=gray:s=640x360:r={fps}:d=3", "-vf", "geq=lum='min(250,20+2*N)':cb=128:cr=128",
               "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv420p", src)
            out = os.path.join(tmp, f"kb{fps}.mp4")
            vb.reframe(src, 0.0, 1.5, out, kb="in")
            ns = src_frames(out)
            span = (ns[-1] - ns[0] + 1) / fps
            check(f"a 1.5 s Ken Burns hold on a {fps} fps clip plays 1.5 s of it", abs(span - 1.5) <= 1.5 / fps + 0.01,
                  f"played {span:.2f}s (source frames {ns[0]}..{ns[-1]})")

        # 2. every ambience piece is exactly as long as the shot vo-build renders
        clip = os.path.join(tmp, "a30.mp4")
        ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4:sample_rate=48000",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip)
        for d, kb in ((0.35, None), (0.55, None), (1.4, "in"), (2.37, "out")):
            out = os.path.join(tmp, f"shot{d}.mp4")
            vb.reframe(clip, 0.2, d, out, kb=kb)
            check(f"a {d} s shot ({kb or 'still'}): the ambience piece matches the picture vo-build renders ({dur(out):.3f}s)",
                  abs(amb._shot_len(d) - dur(out)) < 0.002, f"ambience {amb._shot_len(d):.4f}s")

        jd = os.path.join(tmp, "eng", "projects", "j")
        os.makedirs(os.path.join(jd, "audio"))
        amb.REPO = os.path.join(tmp, "eng")
        holds = [{"path": clip, "in": 0.2, "out": 1.6}, {"path": clip, "in": 2.0, "out": 5.0}]  # the second asks past the end
        for pace, stab in (("emotional", 0.55), ("punchy", 0.35)):
            with open(os.path.join(jd, "shot-plan.json"), "w", encoding="utf-8") as fh:
                json.dump({"burst": [{"path": clip, "in": 0.0}, {"path": clip, "in": 1.0}], "holds": holds}, fh)
            a, _mixed, _silent, _n = amb.build("j", pace=pace)
            want = 2 * amb._shot_len(stab) + amb._shot_len(1.4) + amb._shot_len(3.0)
            check(f"{pace} pace, no burst_stab in the plan: ambience runs {want:.3f}s like the picture (short hold padded)",
                  abs(dur(a) - want) < 0.001, f"got {dur(a):.4f}s")

        # 3. slides carry the ORIGINAL line numbers (what vo-splice --cut takes)
        g = {"phrases": [{"text": str(i)} for i in range(5)], "cut_lines": [2, 4]}
        check("after cutting lines 2 and 4, the slides read 1, 3, 5, 6, 7", listen.line_numbers(g) == [1, 3, 5, 6, 7],
              str(listen.line_numbers(g)))
        check("an unspliced grid numbers 1..N", listen.line_numbers({"phrases": g["phrases"]}) == [1, 2, 3, 4, 5])

        # 4. a .caf voiceover opens in the splice and the listenable cut
        eng = os.path.join(tmp, "caf")
        cjd = os.path.join(eng, "projects", "c")
        os.makedirs(os.path.join(cjd, "audio")); os.makedirs(os.path.join(eng, "product"))
        for f in ("vo-splice.py", "vo-listen.py"):
            shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
        os.makedirs(os.path.join(eng, "assets", "fonts"))
        for f in ("Inter-Regular.otf", "Inter-Medium.ttf"):             # the two faces the listenable cut draws with
            shutil.copy(os.path.join(ROOT, "assets", "fonts", f), os.path.join(eng, "assets", "fonts", f))
        ff("-f", "lavfi", "-i", "sine=f=300:d=1.5:sample_rate=48000", "-c:a", "pcm_s16le", os.path.join(cjd, "audio", "vo.caf"))
        with open(os.path.join(cjd, "vo-grid.json"), "w", encoding="utf-8") as fh:
            json.dump({"duration": 1.4, "phrases": [{"text": "one", "a": 0.1, "b": 0.6, "words": [{"w": "one", "a": 0.1, "b": 0.6}]},
                                                    {"text": "two", "a": 0.8, "b": 1.4, "words": [{"w": "two", "a": 0.8, "b": 1.4}]}]}, fh)
        r = subprocess.run([sys.executable, os.path.join(eng, "product", "vo-listen.py"), "--job", "c"], capture_output=True, text=True)
        check("vo-listen opens a .caf voiceover", r.returncode == 0, (r.stdout + r.stderr)[-300:])
        r = subprocess.run([sys.executable, os.path.join(eng, "product", "vo-splice.py"), "--job", "c"], capture_output=True, text=True)
        check("vo-splice opens a .caf voiceover", r.returncode == 0 and os.path.exists(os.path.join(cjd, "audio", "vo.clean.wav")),
              (r.stdout + r.stderr)[-300:])
        for f in ("vo-cutgrid.py", "vo-build.py"):
            with open(os.path.join(PRODUCT, f), encoding="utf-8") as fh:
                src = fh.read()
            check(f"{f} looks for vo.caf", '"caf"' in src)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
