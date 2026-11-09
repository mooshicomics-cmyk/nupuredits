#!/usr/bin/env python3
"""Guards: the boundary snap reads each clip's sound once, and a stuck read can never hold up "Send my cut".

Buyer report (2026-10-21, Windows 10, a ~65-piece cut of one 5.5 min 4K phone clip): "Send my cut" ran past its
15 minutes every time and stopped, so "Lock in my cut" never came. snap-to-sound.py started its own ffmpeg on the
raw 4K clip for every boundary it measured (onset, offset, fold, and twice more in the fail-safe), several hundred
in all, with no time limit on any of them; SNAP=0 got her through.

  once      a 40-piece plan from one clip decodes that clip's sound ONCE (it used to be two to five ffmpeg runs a piece)
  same      a reading sliced from that one decode matches a reading decoded on its own, so no edge moves
  pauses    the dead-air pass (close-pauses.py), which reads through the same code, also decodes the clip once
  stuck     an ffmpeg that never returns: the snap still finishes inside its budget, every piece keeps the edges as
            written, and the report says why

Made-up clips (voice-like noise between quiet), nothing real is touched. Not run on Windows: the ffmpeg stand-in
is a bash script, which Windows' Python cannot start.

Run: python3 product/tests/test_snap_one_decode.py
"""
import array, importlib.util, json, math, os, random, shutil, stat, struct, subprocess, sys, tempfile, time, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
SNAP = os.path.join(SCRIPTS, "snap-to-sound.py")
PAUSES = os.path.join(SCRIPTS, "close-pauses.py")
FFMPEG = shutil.which("ffmpeg")

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond or not detail else f"  -- {detail}"))
    if not cond:
        fails.append(name)


def executable(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


PIECES = 40
STEP = 0.9          # one word every 0.9 s: 0.35 s of voice, then quiet


def make_clip(tmp):
    """A 37 s AAC clip (the way a phone clip's sound comes): one voiced word every STEP seconds."""
    rate, length = 16000, PIECES * STEP + 1.0
    rnd = random.Random(11)
    out = []
    for k in range(int(length * rate)):
        t = k / rate
        voiced = (t % STEP) >= 0.30 and (t % STEP) < 0.65
        amp = 10 ** ((-20.0 if voiced else -62.0) / 20) * math.sqrt(3)
        out.append(max(-32767, min(32767, int(rnd.uniform(-amp, amp) * 32767))))
    wav = os.path.join(tmp, "a.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(out)}h", *out))
    raw = os.path.join(tmp, "raw"); os.makedirs(raw)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", wav, "-c:a", "aac", "-b:a", "128k",
                    os.path.join(raw, "a.m4a")], check=True)
    words = [{"word": f"w{i}", "start": round(i * STEP + 0.33, 3), "end": round(i * STEP + 0.60, 3), "score": 0.9}
             for i in range(PIECES)]
    segs = [{"clip": "a.m4a", "start": round(i * STEP + 0.20, 3), "end": round(i * STEP + 0.75, 3), "transcript": f"w{i}"}
            for i in range(0, PIECES, 1)]
    wj, pj = os.path.join(tmp, "words.json"), os.path.join(tmp, "cuts.json")
    json.dump({"clips": [{"clip": "a.m4a", "words": words}]}, open(wj, "w", encoding="utf-8"))
    json.dump({"segments": segs}, open(pj, "w", encoding="utf-8"))
    return raw, wj, pj, segs


def stand_in(tmp):
    """An ffmpeg on PATH that logs every run, then runs the real one; HANG=1 makes it never return."""
    bindir = os.path.join(tmp, "bin"); os.makedirs(bindir)
    log = os.path.join(tmp, "ffmpeg-runs.log")
    executable(os.path.join(bindir, "ffmpeg"), "#!/bin/bash\n"
               f"echo run >> {log!r}\n"
               "if [ -n \"${HANG:-}\" ]; then exec sleep 600; fi\n"
               f"exec {FFMPEG!r} \"$@\"\n")
    return bindir, log


def runs(log):
    try:
        return sum(1 for _ in open(log, encoding="utf-8"))
    except OSError:
        return 0


def main():
    if os.name == "nt" or not FFMPEG or not shutil.which("bash"):
        print("snap one decode: skipped (needs bash and ffmpeg; not run on Windows)")
        return 0
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="snap-once-"))
    try:
        raw, wj, pj, segs = make_clip(tmp)
        bindir, log = stand_in(tmp)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        env.pop("HANG", None); env.pop("SNAP_BUDGET_S", None)

        print("1. a 40-piece plan from one clip")
        out = os.path.join(tmp, "cuts.edges.json")
        r = subprocess.run([sys.executable, SNAP, raw, wj, pj, out], env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=300)
        check("the snap finishes", r.returncode == 0 and os.path.exists(out), r.stderr[-400:])
        check(f"it reads the clip's sound once ({runs(log)} ffmpeg runs for {PIECES} pieces)", runs(log) == 1,
              r.stderr[-300:])
        placed = json.load(open(out, encoding="utf-8"))["segments"] if os.path.exists(out) else []
        moved = [p for p in placed if "_snapped_from" in p]
        check("and still places the edges on her voice", len(moved) >= PIECES // 2, f"{len(moved)} moved")

        print("2. the edges land where a read per boundary put them")
        # The same snap twice in this process: once as shipped (one decode, sliced), once with every reading
        # decoded on its own, the way it was before. Every edge must land within one reading (6 ms) of the other.
        def fresh():
            spec = importlib.util.spec_from_file_location("snap_to_sound", SNAP)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            return mod
        sliced, alone = fresh(), fresh()

        def per_read(path, t_from, t_to):                  # the old reader: one ffmpeg per reading
            t0 = max(0.0, t_from)
            pcm = alone._decode(path, t0, t_to - t0)
            width = int(alone.FRAME * alone.RATE)
            return t0, [alone._dbfs(pcm[k * width:(k + 1) * width]) for k in range(len(pcm) // width)]
        alone._levels = per_read
        tr = json.load(open(wj, encoding="utf-8"))
        a_segs, _, a_moved = sliced.snap(segs, raw, sliced._transcript_lookup(tr)[0])
        b_segs, _, b_moved = alone.snap(segs, raw, alone._transcript_lookup(tr)[0])
        worst = max(max(abs(a["start"] - b["start"]), abs(a["end"] - b["end"])) for a, b in zip(a_segs, b_segs))
        check(f"every edge within one reading of the old way (furthest apart {worst * 1000:.0f} ms)",
              worst <= sliced.FRAME + 1e-9)
        check(f"the same pieces move ({a_moved} and {b_moved})", a_moved == b_moved)

        print("3. the dead-air pass reads through the same code")
        os.remove(log)
        out2 = os.path.join(tmp, "cuts.tight.json")
        long_plan = os.path.join(tmp, "cuts.long.json")     # pieces long enough for it to listen to (over 0.7 s)
        json.dump({"segments": [{"clip": "a.m4a", "start": round(a, 3), "end": round(a + 8 * STEP, 3), "transcript": ""}
                                for a in (0.2, 9.2, 18.2, 27.2)]}, open(long_plan, "w", encoding="utf-8"))
        r = subprocess.run([sys.executable, PAUSES, raw, wj, long_plan, out2], env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=300)
        check("close-pauses finishes", r.returncode == 0 and os.path.exists(out2), r.stderr[-400:])
        check(f"and reads the clip's sound once for its 4 pieces ({runs(log)} ffmpeg runs)", runs(log) == 1, r.stderr[-300:])

        print("4. an ffmpeg that never returns")
        os.remove(out)
        env_hang = dict(env, HANG="1", SNAP_BUDGET_S="4")
        t = time.monotonic()
        try:
            r = subprocess.run([sys.executable, SNAP, raw, wj, pj, out], env=env_hang, capture_output=True, text=True,
                               encoding="utf-8", timeout=90)
            took = time.monotonic() - t
            hung = False
        except subprocess.TimeoutExpired:
            took, hung = time.monotonic() - t, True
        check(f"the snap still ends inside its budget ({took:.1f} s for a 4 s budget)", not hung and took < 30)
        if not hung:
            check("it exits 0 with a plan written", r.returncode == 0 and os.path.exists(out), r.stderr[-400:])
            got = json.load(open(out, encoding="utf-8"))["segments"] if os.path.exists(out) else []
            check("every piece keeps the edges as written",
                  len(got) == len(segs) and all(abs(g["start"] - s["start"]) < 1e-6 and abs(g["end"] - s["end"]) < 1e-6
                                                for g, s in zip(got, segs)), str(got[:2]))
            check("the report says the clip's sound could not be read", "could not be read" in r.stderr, r.stderr[-400:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nsnap one decode: {total - len(fails)} of {total} checks passed" + (f"; FAILED: {fails}" if fails else ""))
    return 1 if fails else 0


def test_snap_one_decode():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
