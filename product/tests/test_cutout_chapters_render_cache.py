#!/usr/bin/env python3
"""Guards: three fixes from a buyer's build of 2026-10-22.

  cutout    HyperFrames' remove-background waits forever (no CPU, no error) when the folder it writes into does not
            exist. product/bg_remove.py is the one way the engine runs it: the folder made first, the cutout written
            to a hidden partial file and moved into place only once whole, a run past the clip's time limit stopped
            with everything under it and said plainly, her Stop ending it too. No other engine file runs the tool
            itself.
  chapters  a song's own chapter (an Epidemic mp3 carries one) was copied into the music bed and the finished reel,
            so players showed a 2:08 text track on a 1:45 reel. Every mux that takes a song passes -map_chapters -1.
  cache     reel_render.py's content-hash cache handed back a file another composition had since rendered over (one
            reel in two style packs renders both to the same file). The record keeps the file's size and time, and
            a file written since renders again.

No network and no real renders: the remove-background command is swapped for a small stand-in program. The chapter
check runs ffmpeg on a one-second made-up clip when ffmpeg is installed.

Run: python3 product/tests/test_cutout_chapters_render_cache.py
"""
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
os.environ["REELS_ENGINE_LOCAL"] = tempfile.mkdtemp(prefix="cutout-local-")   # its notes never reach the real _local/
import bg_remove  # noqa: E402
import npx_run  # noqa: E402

fails, n = [], 0


def check(ok, what):
    global n
    n += 1
    if not ok:
        fails.append(what)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                   # a zombie is gone in all but name
        st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return bool(st) and not st.startswith("Z")
    except OSError:
        return True


# ---- cutout ------------------------------------------------------------------------------------------------------
TOOL = r'''
import os, subprocess, sys, time
args = sys.argv[1:]
mode, out = args[0], args[args.index("-o") + 1]
if mode == "write":                        # remove-background's habit: no folder, wait forever (here: 60 s)
    if not os.path.isdir(os.path.dirname(os.path.abspath(out))):
        time.sleep(60)
    open(out, "w", encoding="utf-8").write("cutout")
elif mode == "hang":                       # a stall, with a child under it the way node runs ffmpeg
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    open(args[args.index("--pidfile") + 1], "w", encoding="utf-8").write(str(child.pid))
    time.sleep(120)
elif mode == "fail":
    print("Error: could not read the input video")
    sys.exit(1)
'''

tmp = tempfile.mkdtemp(prefix="cutout-chapters-cache-")
real = (bg_remove.argv, npx_run.npx_path)
try:
    tool = os.path.join(tmp, "tool.py")
    with open(tool, "w", encoding="utf-8") as fh:
        fh.write(TOOL)
    src = os.path.join(tmp, "clip.mp4")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write("clip")
    npx_run.npx_path = lambda: "/usr/bin/npx"
    mode = {"m": "write", "extra": []}
    bg_remove.argv = lambda s, o, extra=(): [sys.executable, tool, mode["m"], s, "-o", o, *mode["extra"]]

    # the real command: HyperFrames at the pin, never @latest
    pin = json.loads(read("product.json"))["hyperframes"]
    av = real[0]("in.mp4", "out.mov")
    check(f"hyperframes@{pin}" in av and "remove-background" in av and av[av.index("-o") + 1] == "out.mov",
          f"cutout: remove-background at the pinned HyperFrames ({pin}), got {av}")

    # a missing folder is made first, and the cutout lands whole
    out = os.path.join(tmp, "job", "broll", ".wcut-1.mov")
    t0 = time.time()
    try:
        got = bg_remove.run(src, out, limit=30)
    except Exception as e:  # noqa: BLE001
        got = f"raised {e}"
    check(got == os.path.abspath(out) and os.path.isfile(out) and time.time() - t0 < 20,
          f"cutout: a missing output folder is made first and the cutout finishes, got {got!r} in {time.time() - t0:.1f}s")
    left = [f for f in os.listdir(os.path.dirname(out)) if ".partial-" in f]
    check(not left, f"cutout: no partial file left beside the cutout, found {left}")

    # a stall is stopped whole, said plainly, and leaves nothing behind
    mode["m"], pidfile = "hang", os.path.join(tmp, "child.pid")
    mode["extra"] = ["--pidfile", pidfile]
    out2 = os.path.join(tmp, "job", "finish", "behind-a.mov")
    t0 = time.time()
    err = None
    try:
        bg_remove.run(src, out2, limit=2)
    except bg_remove.CutoutFailed as e:
        err = str(e)
    took = time.time() - t0
    check(err is not None and "stopped" in err and took < 25,
          f"cutout: a stalled run ends in a plain error inside its limit, got {err!r} after {took:.1f}s")
    check(not os.path.exists(out2) and not [f for f in os.listdir(os.path.dirname(out2)) if ".partial-" in f],
          "cutout: a stalled run leaves no cutout and no partial file")
    try:
        cpid = int(open(pidfile, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        cpid = None
    if cpid:
        for _ in range(20):
            if not alive(cpid):
                break
            time.sleep(0.25)
        check(not alive(cpid), "cutout: a stall stops everything under the tool too (the ffmpeg feeding node)")
    else:
        check(False, "cutout: the stand-in tool never started its child")
    mode["extra"] = []

    # her Stop ends the tool
    calls = []
    try:
        bg_remove.run(src, out2, limit=60, should_stop=lambda: True, on_start=calls.append)
        stopped = False
    except bg_remove.Stopped:
        stopped = True
    check(stopped and len(calls) == 1 and isinstance(calls[0], int), f"cutout: Stop ends the run, on_start got {calls}")

    # a tool that fails says its own last line
    mode["m"] = "fail"
    try:
        bg_remove.run(src, out2, limit=30)
        err = None
    except bg_remove.CutoutFailed as e:
        err = str(e)
    check(err and "could not read the input video" in err and not os.path.exists(out2),
          f"cutout: a failed run says why and writes nothing, got {err!r}")

    # no Node: said plainly, nothing started
    npx_run.npx_path = lambda: None
    try:
        bg_remove.run(src, out2)
        err = None
    except bg_remove.CutoutFailed as e:
        err = str(e)
    check(err == npx_run.NO_NODE, f"cutout: no Node says the engine's own Node line, got {err!r}")
finally:
    bg_remove.argv, npx_run.npx_path = real

# the limit is sized to the clip
real_frames = bg_remove._frames
try:
    os.environ.pop("REELS_ENGINE_BG_REMOVE_SECONDS", None)
    bg_remove._frames = lambda s: 300
    check(bg_remove.time_limit("x.mp4") == int(bg_remove.TIME_BASE_S + 300 * bg_remove.TIME_PER_FRAME_S),
          "cutout: the limit is the base plus a set time a frame")
    bg_remove._frames = lambda s: None
    check(bg_remove.time_limit("x.mp4") == bg_remove.TIME_UNKNOWN_S, "cutout: a clip it cannot read gets the long limit")
    os.environ["REELS_ENGINE_BG_REMOVE_SECONDS"] = "45"
    check(bg_remove.time_limit("x.mp4") == 45, "cutout: REELS_ENGINE_BG_REMOVE_SECONDS sets the limit by hand")
finally:
    os.environ.pop("REELS_ENGINE_BG_REMOVE_SECONDS", None)
    bg_remove._frames = real_frames
check(real_frames("portrait.png") == 1, "cutout: a still is one frame")

# every engine caller goes through bg_remove.py: none runs remove-background itself
try:
    vendored = set(json.loads(read("skills-lock.json"))["skills"])
except Exception:  # noqa: BLE001
    vendored = set()
direct = []
for top in ("product", "workflows", "scripts", os.path.join(".claude", "skills"), ".claude"):
    base = os.path.join(ROOT, top)
    for dp, dns, fns in os.walk(base):
        rel = os.path.relpath(dp, ROOT).replace(os.sep, "/")
        dns[:] = [x for x in dns if x not in ("node_modules", "tests", "__pycache__", "worktrees", "engine")
                  and not (rel == ".claude/skills" and x in vendored)
                  and not (rel == ".claude" and x == "skills")]
        for f in fns:
            if not f.endswith((".py", ".sh", ".js", ".mjs", ".cjs")) or f == "bg_remove.py":
                continue
            p = os.path.join(dp, f)
            try:
                lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
            except OSError:
                continue
            for i, ln in enumerate(lines, 1):
                s = ln.strip()
                if s.startswith(("#", "//", "*")):
                    continue
                if re.search(r"""["']remove-background["']""", s) or re.search(r"(npx|hyperframes)\S*\s.*remove-background", s):
                    direct.append(f"{os.path.relpath(p, ROOT)}:{i}")
check(not direct, f"cutout: these run remove-background themselves instead of through product/bg_remove.py: {direct}")
check("bg_remove.py" in read("product/studio_behind.sh"), "cutout: studio_behind.sh cuts her out through bg_remove.py")
sys.path.insert(0, PRODUCT)
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
import finish  # noqa: E402
check("bg_remove.run(" in inspect.getsource(finish._cutout) and "_cutout(" in inspect.getsource(finish._behind_cutouts),
      "cutout: Finish's cutout for a look behind her goes through bg_remove.run, with her Stop")

# ---- chapters ----------------------------------------------------------------------------------------------------
NOCH = re.compile(r"""-map_chapters["',\s]+-1""")
for rel, where in (("product/build-reel-mp4.py", "the well-done bake"),
                   (".claude/skills/background-music/scripts/lay-bed.sh", "the music bed under her cut"),
                   ("product/build-music.py", "the CapCut music bed"),
                   ("product/vo-build.py", "the voiceover reel's mux"),
                   ("product/reel_render.py", "composite with --audio")):
    check(bool(NOCH.search(read(rel))), f"chapters: {where} ({rel}) passes -map_chapters -1")
check(bool(NOCH.search(inspect.getsource(finish._mix_sound))), "chapters: Finish's MP4 sound mix passes -map_chapters -1")

if shutil.which("ffmpeg") and shutil.which("ffprobe"):
    d = tempfile.mkdtemp(prefix="chapters-")
    try:
        meta = os.path.join(d, "meta.txt")
        with open(meta, "w", encoding="utf-8") as fh:
            fh.write(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=5000\ntitle=song\n")
        song = os.path.join(d, "song.m4a")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=5", "-i", meta,
                        "-map_metadata", "1", "-c:a", "aac", song], check=True, capture_output=True)

        def chapters_after(flag):
            out = os.path.join(d, f"reel{len(flag)}.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1:r=30",
                            "-i", song, "-map", "0:v", "-map", "1:a", *flag, "-t", "1", "-c:v", "libx264",
                            "-c:a", "aac", out], check=True, capture_output=True)
            r = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", out],
                               capture_output=True, text=True, encoding="utf-8")
            return len(json.loads(r.stdout or "{}").get("chapters") or [])
        had, has = chapters_after([]), chapters_after(["-map_chapters", "-1"])
        check(had >= 1 and has == 0,
              f"chapters: ffmpeg copies a song's chapter into the reel unless told not to (without: {had}, with: {has})")
    except subprocess.CalledProcessError as e:
        check(False, f"chapters: the made-up clip could not be made ({e})")
    finally:
        shutil.rmtree(d, ignore_errors=True)

# ---- cache -------------------------------------------------------------------------------------------------------
import reel_render  # noqa: E402
comp = os.path.join(tmp, "comp")
os.makedirs(comp)
out = os.path.join(tmp, "renders", "reel.type.mov")
os.makedirs(os.path.dirname(out))
with open(out, "wb") as fh:
    fh.write(b"pack one titles")
rec = {"out": out, "ok": True, **reel_render._out_stamp(out)}
check(rec.get("out_size") == 15 and rec.get("out_mtime"), f"cache: the record keeps the file's size and time, got {rec}")
check(reel_render._out_rewritten(comp, rec, out) is False, "cache: an untouched file is reused")
time.sleep(0.05)
with open(out, "wb") as fh:
    fh.write(b"pack two titles, longer")
check(reel_render._out_rewritten(comp, rec, out) is True, "cache: a file another composition rendered over renders again")
with open(out, "wb") as fh:
    fh.write(b"pack one titles")
os.utime(out, (rec["out_mtime"] + 30, rec["out_mtime"] + 30))
check(reel_render._out_rewritten(comp, rec, out) is True, "cache: same size, written later, still renders again")
# a record from before the size and time were kept: the file may be no newer than this composition's state file
reel_render._save(comp, {"k": {"out": out, "ok": True}})
sp = reel_render._state_path(comp)
t = os.path.getmtime(sp)
os.utime(out, (t - 10, t - 10))
check(reel_render._out_rewritten(comp, {"out": out, "ok": True}, out) is False, "cache: an older record still reuses its own file")
os.utime(out, (t + 60, t + 60))
check(reel_render._out_rewritten(comp, {"out": out, "ok": True}, out) is True,
      "cache: an older record renders again when the file was written after its own render")
src = inspect.getsource(reel_render.cmd_render)
check("_out_rewritten(d, prev, out)" in src and "**_out_stamp(out)" in src,
      "cache: the render's reuse asks _out_rewritten, and a clean render keeps the file's stamp")

try:
    with open(os.path.join(os.environ["REELS_ENGINE_LOCAL"], "fallbacks.log"), encoding="utf-8") as fh:
        noted = fh.read()
except OSError:
    noted = ""
check("remove-background: stopped after 2s" in noted, "cutout: a stall is noted for /report-a-problem (fallbacks.log)")
shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(os.environ["REELS_ENGINE_LOCAL"], ignore_errors=True)
if fails:
    print("test_cutout_chapters_render_cache: FAILED")
    for f in fails:
        print(f"  FAIL {f}")
    sys.exit(1)
print(f"test_cutout_chapters_render_cache: all {n} checks passed")
