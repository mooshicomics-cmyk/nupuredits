#!/usr/bin/env python3
"""The b-roll tools say what they did, check what they claim to check, and never drop a row.

THE BUGS THIS EXISTS FOR (one review of the b-roll path):
  1. broll-reels/tools/build-all.sh and reconcile.sh read HOOK-MAP.tsv with a plain `while read`, which
     skips a last line that has no newline, so the last reel of a hand-edited map was silently never baked.
  2. bake-hook.py drew the hook over iPhone HLG footage without converting it, so the output stayed tagged
     HDR and the white text landed at HDR peak or washed out, depending on the player.
  3. bake-hook.py's face check (--pos auto, the default) needs OpenCV, which setup never puts in python3, so
     every hook quietly went to the top. The check now borrows OpenCV through uv when python3 has none
     (the text itself is still drawn by python3's own Pillow, so it looks exactly as before).
  4. broll-select.py dropped clips as "soft/dark/flicker" without saying which, checked a 4 s hold window
     for flicker over its first 2 s only (and not at all when it merely started inside a clean burst), and
     scored an iPhone Cinematic raw capture (flat picture + depth track) beside its rendered IMG_E twin.

Run: python3 product/tests/test_broll_checks.py      (synthetic clips; about a minute, most of it part 4)
Parts 3 and 4 need uv (and its cached OpenCV); without uv they are skipped and say so.
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOLS = os.path.join(ROOT, ".claude", "skills", "broll-reels", "tools")
FONT = os.path.join(ROOT, "assets", "fonts", "Inter-Black.otf")
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def ff(*a):
    return subprocess.run(["ffmpeg", "-v", "error", "-y", *a], capture_output=True).returncode == 0


def tags(p):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=color_transfer,color_primaries", "-of", "csv=p=0", p],
                          capture_output=True, text=True).stdout.strip()


def main():
    tmp = tempfile.mkdtemp()
    try:
        # 1. the last HOOK-MAP row bakes (and survives reconcile) with no trailing newline
        work = os.path.join(tmp, "work")
        os.makedirs(os.path.join(work, "clips"))
        for n in ("reel-01-a", "reel-02-b"):
            ff("-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=1", "-c:v", "libx264", "-preset", "ultrafast",
               "-pix_fmt", "yuv420p", os.path.join(work, "clips", n + ".mp4"))
        with open(os.path.join(work, "HOOK-MAP.tsv"), "w", encoding="utf-8", newline="") as fh:
            fh.write("clip\thook\taside\tkeyword\tpos\nreel-01-a\tfirst hook\t-\tone\ttop\nreel-02-b\tlast hook\t-\ttwo\ttop")
        env = dict(os.environ, HEADLINE_FONT=FONT, ACCENT_FONT=FONT, TEXT_COLOR="#ffffff")
        r = subprocess.run(["bash", os.path.join(TOOLS, "build-all.sh"), work], capture_output=True, text=True, env=env)
        final = os.path.join(work, "clips-final")
        check("build-all bakes the last row even without a trailing newline",
              os.path.exists(os.path.join(final, "reel-02-b-FINAL.mp4")) and "of 2 rows" in r.stdout, r.stdout[-300:] + r.stderr[-300:])
        os.remove(os.path.join(final, "reel-01-a-FINAL.mp4"))
        with open(os.path.join(work, "HOOK-MAP.tsv"), "w", encoding="utf-8", newline="") as fh:
            fh.write("clip\thook\taside\tkeyword\tpos\nreel-01-a\tfirst hook\t-\tone\ttop\nreel-02-b\tlast hook\t-\ttwo\ttop")
        subprocess.run(["bash", os.path.join(TOOLS, "reconcile.sh"), work], capture_output=True, text=True)
        with open(os.path.join(work, "HOOK-MAP.tsv"), encoding="utf-8") as fh:
            kept = fh.read()
        check("reconcile keeps the last row even without a trailing newline", "reel-02-b\tlast hook" in kept
              and "reel-01-a" not in kept, repr(kept))

        # 2. HLG footage bakes as SDR; SDR footage is untouched
        hlg, sdr = os.path.join(tmp, "hlg.mov"), os.path.join(tmp, "sdr.mp4")
        have_hlg = ff("-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=1",
                      "-vf", "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc",
                      "-c:v", "libx265", "-preset", "ultrafast", "-x265-params",
                      "log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc", hlg)
        ff("-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=1", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", sdr)
        if have_hlg:
            out = os.path.join(tmp, "hlg-FINAL.mp4")
            subprocess.run([sys.executable, os.path.join(TOOLS, "bake-hook.py"), hlg, out, "a hook", "--pos", "top",
                            "--headline-font", FONT], capture_output=True, text=True)
            check("an HLG clip bakes to SDR (bt709), not a file still tagged HDR", tags(out).startswith("bt709"), tags(out))
        else:
            print("  SKIP  HLG bake (this ffmpeg has no libx265 to make the fixture)")
        out = os.path.join(tmp, "sdr-FINAL.mp4")
        subprocess.run([sys.executable, os.path.join(TOOLS, "bake-hook.py"), sdr, out, "a hook", "--pos", "top",
                        "--headline-font", FONT], capture_output=True, text=True)
        check("an SDR clip keeps its tags", "arib" not in tags(out) and "bt2020" not in tags(out), tags(out))

        uv = shutil.which("uv")
        if not uv:
            print("  SKIP  parts 3 and 4: uv is not installed here")
        else:
            # 3. with no OpenCV in this python, the face check still runs (through uv): a faceless clip is
            #    "no face" (an empty band), not "could not check" (None)
            probe = ("import sys, importlib.util; sys.modules['cv2'] = None\n"
                     f"spec = importlib.util.spec_from_file_location('bh', {os.path.join(TOOLS, 'bake-hook.py')!r})\n"
                     "bh = importlib.util.module_from_spec(spec); spec.loader.exec_module(bh)\n"
                     f"print('BAND', repr(bh.face_band({sdr!r}, n=2)))")
            r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
            check("no OpenCV in python3: the face check borrows uv's and reports 'no face' for a faceless clip",
                  "BAND ()" in r.stdout, (r.stdout + r.stderr)[-400:])

            # 4. broll-select: named drop reasons, full-length flicker checks, Cinematic pairs scored once
            lib = os.path.join(tmp, "lib")
            os.makedirs(lib)
            enc = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"]
            ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=6",
               "-vf", "geq=lum='clip(p(X,Y)+if(gt(T,2.5),if(mod(N,2),30,-30),0),0,255)':cb='p(X,Y)':cr='p(X,Y)'",
               *enc, os.path.join(lib, "flicker-tail.mp4"))
            ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4", "-vf", "lutyuv=y='16+val*0.12':u=128:v=128",
               *enc, os.path.join(lib, "dark.mp4"))
            ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4", "-vf", "gblur=sigma=40", *enc, os.path.join(lib, "soft.mp4"))
            ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4",
               "-vf", "geq=lum='clip(p(X,Y)+if(mod(N,2),30,-30),0,255)':cb='p(X,Y)':cr='p(X,Y)'", *enc,
               os.path.join(lib, "strobe.mp4"))
            ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4", "-f", "lavfi", "-i", "color=c=gray:s=160x284:r=30:d=4",
               "-map", "0:v", "-map", "1:v", *enc, "-tag:v:1", "dish", "-strict", "-2", os.path.join(lib, "IMG_1234.MOV"))
            ff("-f", "lavfi", "-i", "testsrc2=s=320x568:r=30:d=4", *enc, os.path.join(lib, "IMG_E1234.MOV"))
            eng = os.path.join(tmp, "eng")
            os.makedirs(os.path.join(eng, "product"))
            for f in ("broll-select.py", "probe.py"):
                shutil.copy(os.path.join(ROOT, "product", f), os.path.join(eng, "product", f))
            r = subprocess.run([uv, "run", "--quiet", os.path.join(eng, "product", "broll-select.py"), "--lib", lib,
                                "--job", "t"], capture_output=True, text=True)
            out = r.stdout
            # the selector's own line for a clip: "  keep|drop|skip <clip> ..."
            line = lambda clip: next((l for l in out.splitlines() if l.split()[1:2] == [clip]), "")
            check("broll-select ran", r.returncode == 0, (r.stdout + r.stderr)[-500:])
            check("a dark clip's drop line says it is too dark", "too dark" in line("dark.mp4"), line("dark.mp4"))
            check("a soft clip's drop line says it is too soft", "too soft" in line("soft.mp4"), line("soft.mp4"))
            check("a strobing clip's drop line says flicker and names --allow-flicker",
                  "flicker" in line("strobe.mp4") and "--allow-flicker" in line("strobe.mp4"), line("strobe.mp4"))
            check("the raw Cinematic capture is skipped for its rendered E twin",
                  line("IMG_1234.MOV").lstrip().startswith("skip") and "IMG_E1234.MOV" in line("IMG_1234.MOV")
                  and line("IMG_E1234.MOV").lstrip().startswith("keep"), line("IMG_1234.MOV") + " | " + line("IMG_E1234.MOV"))
            sel = os.path.join(eng, "projects", "t", "broll-select.json")
            picks = {}
            if os.path.exists(sel):
                with open(sel, encoding="utf-8") as fh:
                    picks = {p["clip"]: p for p in json.load(fh)["picks"]}
            ft = picks.get("flicker-tail.mp4", {}).get("windows", [])
            bad = [(w["kind"], w["t"], w["dur"]) for w in ft if w["t"] + w["dur"] > 2.5 + 0.2 and w["flicker_status"] == "ok"]
            check("no window reaching into the strobing part of a clip is kept as clean", not bad and bool(ft), str(ft))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
