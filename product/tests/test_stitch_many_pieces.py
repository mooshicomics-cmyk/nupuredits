#!/usr/bin/env python3
"""A cut of many pieces stitches in minutes, not hours, and comes out the same as before.

A buyer report (2026-10-28): an 8-minute take cut into 191 pieces stitched at about 2 s of finished cut a minute on
one core, so the rough cut and the export's full-quality cut each ran for hours (4K or a 1080 copy, the same). The
stitch made the whole cut in ONE ffmpeg graph: every frame decoded from the take went to every piece's chain, and
ffmpeg looks over every filter in the graph for each of those steps, so the work grew with the square of the pieces
(190 pieces of a 5-minute 1080 clip: 21 minutes, against 22 s now). Now a cut of more than STITCH_GROUP
pieces (16) is made a group at a time, each group its own small ffmpeg run reading only its own stretch of the take,
and the groups are joined without a second encode, their sound crossfaded at the same joints as always.

  1. a 40-piece cut (a cold open from late in the take, a sped piece, a zoom) is made in groups: no ffmpeg graph
     holds more than 16 pieces, and every group reads its take from a seek near its own pieces
  2. it passes the stitch's own checks, its sound and picture are the same length, it decodes clean, and its frame
     times only ever increase
  3. nothing of the groups is left in the scratch folder
  4. it is the same cut as the one-graph render (STITCH_GROUP=0): the same number of frames, every frame the same
     picture, the same sound, and the same saved cut plan
  5. a hardware encoder that fails on a grouped cut: every group is made again on the software encoder, then joined
  6. a joined cut whose sound comes out short heals the usual way: its sound is rebuilt from the groups' own sound
  7. a cut of 16 pieces or fewer is still one graph, exactly as before

Runs from a throwaway copy of the engine with a short generated clip; nothing real is touched.

Run:  python3 product/tests/test_stitch_many_pieces.py
"""
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def executable(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


JOB = "many-pieces"
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
# Not on Windows, like test_stitch_outputs.py: the stitch's Python there cannot run the bash ffmpeg wrapper below.
if os.name == "nt" or not FFMPEG or not FFPROBE or not shutil.which("bash"):
    print("stitch many pieces: skipped (needs bash, ffmpeg and ffprobe; not run on Windows)")
    sys.exit(0)

W, H, RATE = 144, 256, "30000/1001"     # an exact 9:16 frame, so no reframe filter joins the chains
tmp = os.path.realpath(tempfile.mkdtemp())
try:
    eng = os.path.join(tmp, "engine")
    for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh",
                "product/video_encoder.py", "product/hdr.py", "product/probe.py", "product/export_progress.py"):
        if os.path.exists(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
    scripts = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts")
    shutil.copytree(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts"), scripts,
                    ignore=shutil.ignore_patterns("__pycache__"))
    stitch = os.path.join(scripts, "stitch-cut.sh")

    # ffmpeg is wrapped to keep every graph and every input list the stitch hands it, and to play a hardware
    # encoder that will not start (exit 1 at the first h264_nvenc), the way an out-of-date NVIDIA driver does. With
    # FAULT set, the run that joins the groups comes out with its sound 0.5 s short (the 2026-10-19 fault).
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    log = os.path.join(tmp, "ffmpeg.log")
    executable(os.path.join(bindir, "ffmpeg"), "#!/bin/bash\n"
               f"echo \"RUN $*\" >> {log!r}\n"
               "join=0; out=\n"
               f"p=; for a in \"$@\"; do case \"$p\" in -/filter_complex|-filter_complex_script) "
               f"echo \"GRAPH $(cat \"$a\")\" >> {log!r};; esac; "
               "case \"$a\" in *groups.txt) join=1;; esac; "
               f"[ \"$p\" = -c:v ] && [ \"$a\" = h264_nvenc ] && {{ echo 'no nvenc here' >&2; exit 1; }}; p=\"$a\"; out=\"$a\"; done\n"
               f"{FFMPEG!r} \"$@\" || exit $?\n"
               "if [ \"$join\" = 1 ] && [ -n \"${FAULT:-}\" ] && [ \"${out%.mp4}\" != \"$out\" ]; then\n"
               f"  d=$({FFPROBE!r} -v error -select_streams a:0 -show_entries stream=duration -of default=nw=1:nk=1 \"$out\")\n"
               "  t=$(python3 -c \"print($d - 0.5)\")\n"
               f"  {FFMPEG!r} -v error -y -i \"$out\" -map 0:v -map 0:a -c:v copy -af \"atrim=0:$t\" -c:a aac \"$out.cut.mp4\" "
               "&& mv -f \"$out.cut.mp4\" \"$out\"\n"
               "fi\n")

    # A 60 s take: the moving test picture (every frame different from the next) and a slow sweep for sound.
    src = os.path.join(tmp, "take.mp4")
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate={RATE}:duration=60",
                    "-f", "lavfi", "-i", "aevalsrc='0.3*sin(2*PI*(200+10*t)*t)':s=48000:d=60",
                    "-c:v", "libx264", "-preset", "ultrafast", "-g", "60", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", "-y", src], check=True)

    # 40 pieces: a cold open from late in the take, then the take in filming order, one piece sped, one zoomed.
    segs = [{"clip": "take.mp4", "start": 57.0, "end": 58.2, "transcript": "cold open"}]
    for i in range(39):
        a = 0.5 + i * 1.4
        segs.append({"clip": "take.mp4", "start": round(a, 3), "end": round(a + 0.9, 3), "transcript": f"line {i}"})
    segs[7]["speed"] = 1.25
    segs[21]["zoom"] = {"from": 1.0, "to": 1.15}
    MANY = {"segments": segs}
    FEW = {"segments": segs[:16]}

    jd = os.path.join(eng, "projects", JOB)
    scratch_parent = os.path.join(tmp, "scratch")
    scratch = os.path.join(scratch_parent, "reels-editing-engine", JOB)
    mp4 = os.path.join(jd, "outputs", JOB + ".mp4")
    saved = os.path.join(jd, "transcript", "cuts.json")

    def job(plan):
        shutil.rmtree(jd, ignore_errors=True)
        shutil.rmtree(scratch_parent, ignore_errors=True)
        os.makedirs(os.path.join(jd, "raw"))
        os.makedirs(os.path.join(jd, "transcript"))
        os.makedirs(scratch)
        shutil.copy(src, os.path.join(jd, "raw", "take.mp4"))
        with open(os.path.join(scratch, "cuts.json"), "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1)
        if os.path.exists(log):
            os.remove(log)

    def run(**extra):
        # No transcript, so none of the listening passes runs: the plan goes straight to the render. A high bit rate
        # keeps two renders of the same frames all but identical, so a frame out of place shows plainly.
        env = dict(os.environ, TMPDIR=scratch_parent, PATH=bindir + os.pathsep + os.environ["PATH"],
                   REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv",
                   VERIFY_CUT="0", VENC="libx264", VBR="40M", TRIM_RESTARTS="0", SNAP="0", CLOSE_PAUSES="0")
        for k in ("VOICE_GAIN_DB", "FLAT_RENDER", "WARM_MASTER", "STITCH_GROUP"):
            env.pop(k, None)
        env.update(extra)
        return subprocess.run(["bash", stitch, "projects/" + JOB], cwd=eng, env=env, capture_output=True,
                              text=True, encoding="utf-8")

    def ffmpeg_log():
        if not os.path.exists(log):
            return [], []
        with open(log, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        return [l[4:] for l in lines if l.startswith("RUN ")], [l[6:] for l in lines if l.startswith("GRAPH ")]

    def stream_dur(path, kind):
        out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", f"{kind}:0", "-show_entries",
                              "stream=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
        try:
            return float(out.split()[0])
        except (IndexError, ValueError):
            return None

    def frames(path):
        """Every frame, small and grey: one bytes object per frame."""
        w, h = 36, 64
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo",
                              "-"], capture_output=True).stdout
        return [raw[i:i + w * h] for i in range(0, len(raw), w * h)]

    def sound(path):
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True).stdout
        return [int.from_bytes(raw[i:i + 2], "little", signed=True) for i in range(0, len(raw) - 1, 2)]

    def plan_of():
        with open(saved, encoding="utf-8") as fh:
            return json.load(fh)["segments"]

    print("1. a 40-piece cut is made in groups")
    job(MANY)
    r = run()
    runs, graphs = ffmpeg_log()
    check("the stitch says it made the cut in groups", "one after another, then joined" in r.stderr, r.stderr[-400:])
    renders = [g for g in graphs if "concat=n=" in g]
    biggest = max((int(m) for g in renders for m in re.findall(r"concat=n=(\d+):v=1", g)), default=0)
    check("no ffmpeg graph joins more than 16 pieces' pictures", 0 < biggest <= 16, f"largest join: {biggest} pieces")
    check("each piece's chain is in exactly one group", sum(g.count("trim=") - g.count("atrim=") - g.count("end_frame")
                                                            for g in renders) == len(segs),
          f"{[g.count('setpts=PTS-STARTPTS') for g in renders]}")
    check("there are three groups, one ffmpeg run each, then one join", len(renders) == 3
          and sum(1 for a in runs if "groups.txt" in a) == 1, f"{len(renders)} group graphs; {len(runs)} runs")
    seeks = [[int(x) for x in re.findall(r"-ss (\d+) -i ", a)] for a in runs if "group-" in a and "-ss" in a]
    check("every group reads the take from near its own pieces, never from the top of the take",
          len(seeks) == 3 and seeks[1] and min(seeks[1]) >= 15 and seeks[2] and min(seeks[2]) >= 33, f"{seeks}")
    check("the cold open, from late in the take, reads from its own seek in the first group",
          seeks and max(seeks[0]) >= 50 and min(seeks[0]) == 0, f"{seeks[:1]}")

    print("2. it passes the stitch's checks")
    check("it renders and passes the stitch's integrity check", r.returncode == 0 and os.path.exists(mp4),
          f"exit {r.returncode}: {r.stderr[-600:]}")
    grouped_frames, grouped_sound, grouped_plan = [], [], []
    if os.path.exists(mp4):
        vd, ad = stream_dur(mp4, "v"), stream_dur(mp4, "a")
        check("its sound and picture are the same length", vd and ad and abs(vd - ad) < 1024 / 48000 + 1 / 24,
              f"picture {vd} s, sound {ad} s")
        scan = subprocess.run([FFMPEG, "-v", "error", "-i", mp4, "-f", "null", "-"], capture_output=True, text=True)
        check("it decodes start to end without an error", scan.returncode == 0 and not scan.stderr.strip(),
              scan.stderr[-300:])
        times = [float(t) for t in subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                   "frame=pts_time", "-of", "default=nw=1:nk=1", mp4],
                                                  capture_output=True, text=True).stdout.split()
                 if t not in ("", "N/A")]
        check("its frame times only ever increase", len(times) > 500 and all(b > a for a, b in zip(times, times[1:])),
              f"{len(times)} frames")
        grouped_frames, grouped_sound, grouped_plan = frames(mp4), sound(mp4), plan_of()

    print("3. nothing of the groups is left behind")
    left = [f for f in os.listdir(scratch) if f.startswith("group-")] if os.path.isdir(scratch) else []
    check("no group file is left in the scratch folder", not left, f"{left}")

    print("4. the same cut as the one-graph render")
    job(MANY)
    r1 = run(STITCH_GROUP="0")
    _runs, graphs = ffmpeg_log()
    check("STITCH_GROUP=0 makes it in one graph (the way every cut used to be made)",
          r1.returncode == 0 and sum(1 for g in graphs if f"concat=n={len(segs)}:v=1" in g) == 1, r1.stderr[-400:])
    if r1.returncode == 0 and grouped_frames:
        one_frames, one_sound = frames(mp4), sound(mp4)
        check("the same number of frames", len(one_frames) == len(grouped_frames),
              f"grouped {len(grouped_frames)}, one graph {len(one_frames)}")
        # A frame out of place on the moving test picture differs by tens of levels; the same frame encoded twice
        # differs by a level or so.
        worst = max((sum(abs(x - y) for x, y in zip(a, b)) / len(a) for a, b in zip(grouped_frames, one_frames)),
                    default=99.0)
        neighbour = sum(abs(x - y) for x, y in zip(one_frames[100], one_frames[101])) / len(one_frames[100])
        check("every frame is the same picture", worst < 2.0 < neighbour,
              f"worst frame differs by {worst:.2f} levels (next-frame difference {neighbour:.2f})")
        n = min(len(one_sound), len(grouped_sound))
        rms = math.sqrt(sum((one_sound[i] - grouped_sound[i]) ** 2 for i in range(n)) / max(1, n))
        level = math.sqrt(sum(v * v for v in one_sound[:n]) / max(1, n))
        check("the same sound", abs(len(one_sound) - len(grouped_sound)) <= 8 and level > 1000 and rms < level / 100,
              f"difference {rms:.1f} against a level of {level:.1f}; {len(grouped_sound)} vs {len(one_sound)} samples")
        check("the same saved cut plan", plan_of() == grouped_plan)

    print("5. a hardware encoder that will not start, on a grouped cut")
    job(MANY)
    r = run(VENC="h264_nvenc")
    runs, _g = ffmpeg_log()
    check("it falls back to the software encoder and renders", r.returncode == 0 and os.path.exists(mp4)
          and "retrying on the software encoder" in r.stderr, f"exit {r.returncode}: {r.stderr[-500:]}")
    sw = [a for a in runs if "group-" in a and "libx264" in a and ".mp4" in a]
    check("every group is made again on the software encoder before the join", len(sw) == 3, f"{len(sw)} groups")
    if os.path.exists(mp4):
        check("and its picture is as long as before", len(frames(mp4)) == len(grouped_frames))

    print("6. the joined cut's sound comes out short: it is rebuilt from the groups' own sound")
    job(MANY)
    r = run(FAULT="1")
    check("the stitch rebuilds the sound and puts it under the picture",
          r.returncode == 0 and "sound rebuilt and put under the picture" in r.stderr, r.stderr[-500:])
    if os.path.exists(mp4):
        vd, ad = stream_dur(mp4, "v"), stream_dur(mp4, "a")
        check("and then its sound and picture are the same length", vd and ad and abs(vd - ad) < 1024 / 48000 + 1 / 24,
              f"picture {vd} s, sound {ad} s")

    print("7. a cut of 16 pieces is still one graph")
    job(FEW)
    r = run()
    _runs, graphs = ffmpeg_log()
    check("it renders in one graph, as always", r.returncode == 0 and "one after another, then joined" not in r.stderr
          and sum(1 for g in graphs if "concat=n=16:v=1" in g) == 1, r.stderr[-400:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "stitch many pieces: made in groups, the same cut, in minutes"))
sys.exit(1 if fails else 0)
