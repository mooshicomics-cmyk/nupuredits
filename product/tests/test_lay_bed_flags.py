#!/usr/bin/env python3
"""lay-bed.sh: the music bed's settings are named, in any order.

The level (--bed-db), the lift in her pauses (--lift) and the fade-in (--fade-in) are named; a bare value or an
unknown setting stops with the usage line before ffmpeg runs. The level can also come from MUSIC_BED_DB; anything
typed on the command line wins over the environment. Left unset, the level is measured; a stand-in ffmpeg
measures nothing, so here it lands on the -18 dB fallback and says so. --lift raises the music in the pauses her
transcript shows, and never touches it while she talks.

ffmpeg and ffprobe are stand-ins here that only record what they were asked, so this runs in a second.

Run:  python3 product/tests/test_lay_bed_flags.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LAY_BED = os.path.join(ROOT, ".claude", "skills", "background-music", "scripts", "lay-bed.sh")
fails = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


tmp = tempfile.mkdtemp()
try:
    shims = os.path.join(tmp, "bin")
    os.makedirs(shims)
    log = os.path.join(tmp, "argv.log")
    with open(os.path.join(shims, "ffmpeg"), "w", encoding="utf-8") as fh:
        fh.write('#!/bin/bash\nprintf "%s\\n" "$@" > "$ARGV_LOG"\n')
    with open(os.path.join(shims, "ffprobe"), "w", encoding="utf-8") as fh:
        fh.write("#!/bin/bash\necho 12.5\n")
    for name in ("ffmpeg", "ffprobe"):
        os.chmod(os.path.join(shims, name), 0o755)
    video, music = os.path.join(tmp, "cut.mp4"), os.path.join(tmp, "track.wav")
    for f in (video, music):
        open(f, "wb").close()
    out = os.path.join(tmp, "cut-music.mp4")
    base_env = {k: v for k, v in os.environ.items() if k != "MUSIC_BED_DB"}
    base_env.update(PATH=shims + os.pathsep + base_env.get("PATH", ""), ARGV_LOG=log)

    def run(*args, **env):
        if os.path.exists(log):
            os.remove(log)
        r = subprocess.run(["bash", LAY_BED, video, music, out, *args], capture_output=True, text=True,
                           env=dict(base_env, **env))
        argv = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
        return r, argv

    # Settings are named, in any order; the two spellings of a value agree.
    _, a = run("--bed-db", "-24")
    _, b = run("--bed-db=-24")
    check("--bed-db N and --bed-db=N set the same level", a and a == b and "volume=-24.0dB" in a, f"\n{a}\nvs\n{b}")
    _, a = run("--fade-in", "1.5", "--lift", "--bed-db", "-20")
    _, b = run("--bed-db", "-20", "--lift", "--fade-in", "1.5")
    check("named settings in any order lay the same bed", a and a == b and "afade=t=in:st=0:d=1.5" in a, a)
    # A bare value after the three paths is refused, before ffmpeg runs: settings are named.
    for extra in (["-18"], ["--bed-db", "-18", "on"], ["--duck"]):
        r, a = run(*extra)
        check(f"an unnamed or unknown setting {extra} stops with the usage line",
              r.returncode != 0 and not a and "usage: lay-bed.sh" in r.stderr, r.stderr)

    r, plain = run()
    check("unmeasurable, the house bed falls back to -18 dB, steady, no fade-in, and says so",
          "volume=-18.0dB" in plain and "eval=frame" not in plain and "afade=t=in" not in plain
          and "(fallback)" in r.stderr, plain + r.stderr)
    check("no compressor anywhere in the mix", "sidechaincompress" not in plain and "loudnorm" not in plain, plain)
    check("the sum goes through the rough cut's own limiter, its look-ahead taken back out",
          "alimiter=limit=0.89:level=false:latency=true" in plain, plain)
    check("the sound is written like every other engine pass: AAC 256k, 48 kHz, stereo, picture copied",
          "\n".join(("-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2")) in plain, plain)
    _, a = run(MUSIC_BED_DB="-22")
    check("MUSIC_BED_DB sets the level", "volume=-22.0dB" in a, a)
    _, a = run("--bed-db", "-30", MUSIC_BED_DB="-22")
    check("a level typed on the command line wins over the environment", "volume=-30.0dB" in a, a)

    # The lift: talk 0.5-3.0, a pause, talk 5.0-9.0, then quiet to the end (ffprobe says 12.5).
    tr = os.path.join(tmp, "cut.transcript.json")
    with open(tr, "w", encoding="utf-8") as fh:
        json.dump({"words": [{"text": "a", "start": 0.5, "end": 3.0}, {"text": "b", "start": 5.0, "end": 9.0}]}, fh)
    r, a = run("--bed-db", "-18", "--lift")
    check("--lift finds the transcript beside the cut and lifts in its pauses",
          "eval=frame" in a and "clip((t-3.000)" in a and "clip((t-9.000)" in a and "clip((t-0.000)" not in a,
          a + r.stderr)
    check("the log says the music rises in her pauses", "rising in her pauses" in r.stderr, r.stderr)
    os.remove(tr)
    r, a = run("--bed-db", "-18", "--lift")
    check("--lift with no transcript lays one level and says why",
          "eval=frame" not in a and "no transcript of this cut" in r.stderr, r.stderr)
    r, a = run("--bed-db")
    check("--bed-db with no value stops before ffmpeg", r.returncode != 0 and not a, r.stderr)
    r = subprocess.run(["bash", LAY_BED], capture_output=True, text=True, env=base_env)
    check("no arguments still prints the usage line", r.returncode != 0 and "usage: lay-bed.sh" in r.stderr, r.stderr)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else "lay-bed: named settings lay the bed, in any order")
sys.exit(1 if fails else 0)
