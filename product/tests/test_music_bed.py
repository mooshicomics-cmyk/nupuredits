#!/usr/bin/env python3
"""Regression guard: a voiceover reel never loses its music bed without saying so.

The bug this locks down: vo-build.py laid a bed only when --music pointed at a file that existed from
wherever the build ran, and otherwise built voice-only without a word. Buyers had no way to generate a
bed either, because gen-music.py only ran inside a hand-built venv that setup never creates. So reels
shipped with no music and nobody could tell why.

  1. resolve_music finds a bare track name in the job's audio/ folder, and STOPS on a name that is not there.
  2. gen-music.py needs no venv of its own: --check finds the WhisperX venv, and with no torch venv at all
     it exits 3 with the plain "drop your own track" message rather than a traceback.

Run: python3 product/tests/test_music_bed.py
"""
import os, sys, shutil, subprocess, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def load_vo_build():
    spec = importlib.util.spec_from_file_location("vo_build", os.path.join(PRODUCT, "vo-build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    vb = load_vo_build()
    with tempfile.TemporaryDirectory() as jd:
        os.makedirs(os.path.join(jd, "audio"))
        track = os.path.join(jd, "audio", "bed.wav")
        open(track, "wb").close()
        check("no --music means no bed, and no error", vb.resolve_music(None, jd) is None)
        check("bare name resolves from the job's audio/", vb.resolve_music("bed.wav", jd) == os.path.abspath(track))
        check("a wrong folder still finds the file by name",
              vb.resolve_music("some/other/dir/bed.wav", jd) == os.path.abspath(track))
        try:
            vb.resolve_music("missing.mp3", jd)
            check("a track that is not there stops the build", False, "returned instead of exiting")
        except SystemExit as e:
            check("a track that is not there stops the build", "not found" in str(e.code), str(e.code))

    # gen-music in a buyer-shaped copy: no product/engine/musicgen-venv, WhisperX venv pointed nowhere.
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "product"))
        for f in ("gen-music.py", "clean_cut.py"):
            shutil.copy(os.path.join(PRODUCT, f), os.path.join(root, "product", f))
        env = dict(os.environ, REELS_ENGINE_WHISPERX_VENV=os.path.join(root, "no-such-venv"))
        r = subprocess.run([sys.executable, os.path.join(root, "product", "gen-music.py"), "--check"],
                           capture_output=True, text=True, env=env)
        has_torch = subprocess.run([sys.executable, "-c", "import torch, transformers"],
                                   capture_output=True).returncode == 0
        if has_torch:
            check("gen-music runs on the current python when it already has torch", r.returncode == 0, r.stdout + r.stderr)
        else:
            check("no torch venv exits 3", r.returncode == 3, f"exit {r.returncode}: {r.stderr[-300:]}")
            check("no torch venv explains the own-track route", "audio/" in r.stdout and "Traceback" not in r.stderr,
                  r.stdout + r.stderr)

    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
