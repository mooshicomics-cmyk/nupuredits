#!/usr/bin/env python3
"""The speech tools' finished-build record, and the stitch step's flat-render switch, answer to their names and
to their older ones.

  1. A venv that carries only .deps-ok (every install made before .speech-tools-ready existed) is a finished
     build: word-timings.sh uses it as it is. No uv call, nothing deleted, the old record untouched. A 3-5 GB
     venv must never download again because its record has the older name.
  2. A venv with the new record is used as it is too.
  3. A venv with no record (or a blank one) whose listener imports is kept, and gets both records.
  4. A machine with no venv builds one, and the finished build carries both records, same content.
  5. stitch-cut.sh writes the EDL only for FLAT_RENDER=0. Its toggles line names FLAT_RENDER.

Everything runs from a throwaway copy of the engine with stand-ins for uv and the venv interpreter, so no
model loads and nothing is downloaded.

Run:  python3 product/tests/test_speech_tools_record.py
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

JOB = "st-job"   # stand-in job folders the test builds
TX_JOB = "tx-job"

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


def executable(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if os.name == "nt" or not shutil.which("bash"):
    print("speech tools record: skipped (needs bash and a POSIX shell for the stand-ins)")
    sys.exit(0)

# The venv interpreter stand-in: logs every call, writes an empty transcript for the listener step, answers
# "yes" to an import probe and "no GPU" to the torch.cuda probe.
VENV_PY = """#!/bin/bash
printf '%s\\n' "$*" >> "$CALL_LOG"
case "$1" in
  -) cat >/dev/null; printf '{"clips": []}\\n' > "$2"; exit 0 ;;
  */transcribe-nofw.py) printf '{"clips": []}\\n' > "$2"; exit 0 ;;
  -c) case "$2" in *torch.cuda*) exit 1 ;; esac; [ "${FAKE_IMPORT_FAIL:-0}" = 1 ] && exit 1; exit 0 ;;
esac
exit 0
"""

tmp = tempfile.mkdtemp()
try:
    eng = os.path.join(tmp, "engine")
    for rel in ("scripts/_python3-shim.sh", "scripts/_path-shim.sh", "scripts/_mac-arch.sh",
                "scripts/transcribe-nofw.py", "product/video_encoder.py", "product/hdr.py", "product/probe.py"):
        os.makedirs(os.path.dirname(os.path.join(eng, rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(eng, rel))
    shutil.copytree(SCRIPTS, os.path.join(eng, ".claude", "skills", "rough-cut", "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    wt = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
    stitch = os.path.join(eng, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")

    fake_bin = os.path.join(tmp, "bin")
    executable(os.path.join(tmp, "venvpy"), VENV_PY)
    # uv: logs the call; `uv venv <dir>` makes a venv holding the interpreter stand-in.
    executable(os.path.join(fake_bin, "uv"), f"""#!/bin/bash
printf 'uv %s\\n' "$*" >> "$CALL_LOG"
if [ "$1" = venv ]; then mkdir -p "$2/bin"; cp "{tmp}/venvpy" "$2/bin/python"; fi
exit 0
""")
    executable(os.path.join(fake_bin, "nvidia-smi"), "#!/bin/bash\nexit 1\n")   # no NVIDIA card on any test machine

    def venv(state):
        """A fresh venv folder: a big file standing in for torch, and the record(s) named."""
        v = os.path.join(tmp, "home", ".cache", "reels-editing-engine", "whisperx-venv")
        shutil.rmtree(os.path.dirname(v), ignore_errors=True)
        if state == "none":
            return v
        executable(os.path.join(v, "bin", "python"), VENV_PY)
        with open(os.path.join(v, "torch-weights.bin"), "w", encoding="utf-8") as fh:
            fh.write("3-5 GB of her installed speech tools\n")
        for name, body in state.items():
            with open(os.path.join(v, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        return v

    def transcribe(v, **env_extra):
        job = os.path.join(eng, "projects", TX_JOB)
        shutil.rmtree(job, ignore_errors=True)
        os.makedirs(os.path.join(job, "raw"))
        open(os.path.join(job, "raw", "IMG_0001.MOV"), "w", encoding="utf-8").close()
        log = os.path.join(tmp, "calls.log")
        if os.path.exists(log):
            os.remove(log)
        env = dict(os.environ, HOME=os.path.join(tmp, "home"), TMPDIR=os.path.join(tmp, "scratch"),
                   PATH=fake_bin + os.pathsep + os.environ["PATH"], CALL_LOG=log,
                   REELS_ENGINE_WHISPERX_VENV=v, REELS_ENGINE_NOFW_VENV=v)
        for k in ("REELS_ENGINE_FORCE_NOFW", "REELS_ENGINE_LANGUAGE"):
            env.pop(k, None)
        env.update(env_extra)
        os.makedirs(env["TMPDIR"], exist_ok=True)
        r = subprocess.run(["bash", wt, f"projects/{TX_JOB}"], cwd=eng, env=env, capture_output=True, text=True,
                           encoding="utf-8")
        calls = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        return r, calls

    def read(v, name):
        p = os.path.join(v, name)
        return open(p, encoding="utf-8").read() if os.path.exists(p) else None

    # ── 1. only the older record: used as it is ───────────────────────────────────────────────────────────
    for mode in ("cpu\n", "cuda\n"):
        v = venv({".deps-ok": mode})
        r, calls = transcribe(v)
        tag = mode.strip()
        check(f"1 ({tag}): transcribes", r.returncode == 0, r.stderr[-500:])
        check(f"1 ({tag}): no uv call at all", not [c for c in calls if c.startswith("uv ")], calls)
        check(f"1 ({tag}): her installed venv is still there", read(v, "torch-weights.bin") is not None)
        check(f"1 ({tag}): .deps-ok is untouched", read(v, ".deps-ok") == mode, read(v, ".deps-ok"))
        check(f"1 ({tag}): no rebuild announced", "setting up the speech tools" not in r.stderr
              and "Rebuilding" not in r.stderr, r.stderr[-500:])
        check(f"1 ({tag}): no probe of the venv was needed", not [c for c in calls if c.startswith("-c ")], calls)
        check(f"1 ({tag}): the transcript was saved",
              os.path.exists(os.path.join(eng, "projects", TX_JOB, "transcript", "words.json")))

    # ── 2. only the new record: used as it is ─────────────────────────────────────────────────────────────
    v = venv({".speech-tools-ready": "cpu\n"})
    r, calls = transcribe(v)
    check("2: transcribes", r.returncode == 0, r.stderr[-500:])
    check("2: no uv call", not [c for c in calls if c.startswith("uv ")], calls)
    check("2: venv kept", read(v, "torch-weights.bin") is not None)

    # ── 3. no record, or a blank one, but the listener imports: kept, both records written ───────────────
    for state, tag in (({}, "no record"), ({".deps-ok": ""}, "blank .deps-ok")):
        v = venv(state)
        r, calls = transcribe(v)
        check(f"3 ({tag}): transcribes", r.returncode == 0, r.stderr[-500:])
        check(f"3 ({tag}): no uv call", not [c for c in calls if c.startswith("uv ")], calls)
        check(f"3 ({tag}): venv kept", read(v, "torch-weights.bin") is not None)
        check(f"3 ({tag}): both records say cpu", read(v, ".speech-tools-ready") == "cpu\n"
              and read(v, ".deps-ok") == "cpu\n", (read(v, ".speech-tools-ready"), read(v, ".deps-ok")))
        check(f"3 ({tag}): said it kept them", "keeping them, no rebuild" in r.stderr, r.stderr[-500:])

    # a venv whose listener does NOT import is rebuilt (that is what an unfinished build looks like)
    v = venv({})
    r, calls = transcribe(v, FAKE_IMPORT_FAIL="1")
    check("3 (broken venv): rebuilt", any(c.startswith("uv venv ") for c in calls), calls)

    # ── 4. no venv: built once, both records ──────────────────────────────────────────────────────────────
    v = venv("none")
    r, calls = transcribe(v)
    check("4: transcribes", r.returncode == 0, r.stderr[-500:])
    check("4: uv built the venv", any(c.startswith("uv venv ") for c in calls), calls)
    check("4: both records, same content", read(v, ".speech-tools-ready") == "cpu\n"
          and read(v, ".deps-ok") == "cpu\n", (read(v, ".speech-tools-ready"), read(v, ".deps-ok")))
    r2, calls2 = transcribe(v)
    check("4: the next run builds nothing", not [c for c in calls2 if c.startswith("uv ")], calls2)

    # ── 5. stitch-cut.sh: FLAT_RENDER ──────────────────────────────────────────────────────────────────
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        print("  (part 5 skipped: needs ffmpeg and ffprobe)")
    else:
        clip = os.path.join(tmp, "clip.mp4")
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=3",
                        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", clip], check=True)
        words = {"clips": [{"clip": "clip.mp4", "words": [{"word": "hello", "start": 1.0, "end": 1.9, "score": 0.9}]}]}
        seg = {"clip": "clip.mp4", "start": 0.9, "end": 2.0, "transcript": "hello"}

        def stitch_run(**env_extra):
            jd = os.path.join(eng, "projects", JOB)
            shutil.rmtree(jd, ignore_errors=True)
            os.makedirs(os.path.join(jd, "raw"))
            os.makedirs(os.path.join(jd, "transcript"))
            shutil.copy(clip, os.path.join(jd, "raw", "clip.mp4"))
            json.dump(words, open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
            json.dump({"segments": [seg]}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
            scratch = os.path.join(tmp, "st-scratch")
            shutil.rmtree(scratch, ignore_errors=True)
            os.makedirs(scratch)
            env = dict(os.environ, TMPDIR=scratch, TRIM_RESTARTS="0", VERIFY_CUT="0", SNAP="0",
                       REELS_ENGINE_WHISPERX_VENV="/nonexistent-venv", REELS_ENGINE_NOFW_VENV="/nonexistent-venv")
            for k in ("FLAT_RENDER", "VOICE_GAIN_DB", "WARM_MASTER", "VENC"):
                env.pop(k, None)
            env.update(env_extra)
            r = subprocess.run(["bash", stitch, f"projects/{JOB}"], cwd=eng, env=env, capture_output=True,
                               text=True, encoding="utf-8")
            return r, os.path.exists(os.path.join(jd, "outputs", f"{JOB}.mp4"))

        for label, env_extra, rendered, shown in (
                ("FLAT_RENDER=0 writes the EDL only", {"FLAT_RENDER": "0"}, False, "FLAT_RENDER=0"),
                ("FLAT_RENDER=1 renders", {"FLAT_RENDER": "1"}, True, "FLAT_RENDER=1"),
                ("nothing set renders", {}, True, "FLAT_RENDER=1")):
            r, mp4 = stitch_run(**env_extra)
            check(f"5: {label}: runs clean", r.returncode == 0, r.stderr[-600:])
            check(f"5: {label}: {'rendered' if rendered else 'no render'}", mp4 == rendered, r.stderr[-600:])
            check(f"5: {label}: the EDL was saved",
                  os.path.exists(os.path.join(eng, "projects", JOB, "transcript", "cuts.json")))
            check(f"5: {label}: toggles line shows {shown}", f" {shown} VERIFY_CUT=" in r.stderr, r.stderr[:400])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else
      "speech tools record: older installs are kept as they are; FLAT_RENDER=0 writes the EDL only")
sys.exit(1 if fails else 0)
