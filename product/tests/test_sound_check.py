#!/usr/bin/env python3
"""sound-check hears what the stitch can get wrong, at the joint where it happened, and names the fix.

  1. Its copies of the stitch's numbers (crossfade, its floor, the two limiter ceilings) match stitch-cut.sh.
  2. A cut whose sound carries straight through every joint: every joint is clean, the length matches.
  3. A step left right on a cut is a click at that joint; the fix offered is a longer crossfade on the segment
     it leads into, then "keep_edges", then a hand trim, as the segment already carries each.
  4. Sound faded to silence right on a cut, with sound on both sides, is a dip at that joint.
  5. The same fault at most joints is the stitch broken, not one cut: /report-a-problem.
  6. A render longer than its plan with no dead air is a stale plan (stitch again); dead air at the joints is
     padded silence (/report-a-problem).
  7. Nothing to hear is NOT CHECKED (exit 2); under a second is skipped (exit 0).

Everything runs on generated sound in a temporary folder.

Run:  python3 product/tests/test_sound_check.py
"""
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
SC = os.path.join(SCRIPTS, "sound-check.py")
RATE = 48000
fails = []


def check(label, cond, detail=""):
    if not cond:
        print(f"  FAIL {label}" + (f"  {detail}" if detail else ""))
        fails.append(label)


# ------------------------------------------------------------ 1: the stitch's numbers
with open(os.path.join(SCRIPTS, "stitch-cut.sh"), encoding="utf-8") as fh:
    stitch = fh.read()
with open(SC, encoding="utf-8") as fh:
    src = fh.read()


def const(text, name):
    m = re.search(rf"^{name}\s*=\s*([0-9.]+)", text, re.M)
    return float(m.group(1)) if m else None


check("1: the crossfade is the stitch's XF", const(src, "STITCH_XF") == const(stitch, "XF"))
check("1: the crossfade floor is joint_xfade's", f"max({const(src, 'STITCH_XF_FLOOR')}, " in stitch)
check("1: the voice master's ceiling", 'limiter("0.89")' in stitch and '"voice": 0.89' in src)
check("1: the flat master's ceiling", 'limiter("0.501")' in stitch and '"flat": 0.501' in src)
check("1: the longer crossfade it offers is the one the stitch documents", "e.g. 0.030" in stitch
      and const(src, "LONGER_XFADE") == 0.030)

FFMPEG = shutil.which("ffmpeg")
if not FFMPEG:
    print("sound check: 1 only (the rest needs ffmpeg)")
    sys.exit(1 if fails else 0)


def voice(n):
    """A steady, voice-like sound: a 220 Hz tone with two overtones, around -22 dBFS."""
    return [0.06 * math.sin(2 * math.pi * 220 * k / RATE) + 0.03 * math.sin(2 * math.pi * 440 * k / RATE + 0.3)
            + 0.015 * math.sin(2 * math.pi * 880 * k / RATE + 1.1) for k in range(n)]


def make(tmp, name, samples, segments):
    jd = os.path.join(tmp, name)
    os.makedirs(os.path.join(jd, "outputs"))
    os.makedirs(os.path.join(jd, "transcript"))
    wav = os.path.join(tmp, name + ".wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(round(s * 32767))))) for s in samples))
    subprocess.run([FFMPEG, "-v", "error", "-i", wav, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-y",
                    os.path.join(jd, "outputs", name + ".mp4")], check=True)
    with open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": segments}, fh)
    return jd


def listen(jd, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("VOICE_GAIN_DB", "WARM_MASTER")}
    e.update(env)
    r = subprocess.run([sys.executable, SC, jd], capture_output=True, text=True, env=e, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def segs(lengths, extra=None):
    out, t = [], 0.0
    for i, d in enumerate(lengths):
        s = {"clip": "take.mov", "start": round(t, 6), "end": round(t + d, 6), "transcript": f"line {i} goes here"}
        s.update((extra or {}).get(i, {}))
        out.append(s)
        t += d
    return out


def fade_to_silence(x, c, w=288):
    for k in range(w):
        g = k / w
        x[c - 1 - k] *= g
        x[c + k] *= g


tmp = tempfile.mkdtemp()
try:
    # ------------------------------------------------------------ 2: clean
    x = voice(3 * RATE)
    jd = make(tmp, "clean", x, segs([1.0, 1.0, 1.0]))
    rc, out = listen(jd)
    check("2: clean joints", rc == 0 and "✓ joints: 2 heard" in out, out)
    check("2: the length matches", "✓ length" in out, out)
    check("2: the master is reported with its ceiling", "ceiling -1.0 dBFS" in out, out)
    check("2: nothing to listen to", "listen:" not in out and "⚠" not in out, out)

    # ------------------------------------------------------------ 3: a click, and the fix ladder
    x = voice(3 * RATE)
    c = RATE
    for k in range(c, 3 * RATE):
        x[k] += 0.25                       # the sound jumps right on the first cut
    for name, extra, want in (
            ("click", {}, 'give segments[1] in transcript/cuts.json "xfade": 0.030 and stitch again'),
            ("click-xfaded", {1: {"xfade": 0.03}}, '"keep_edges": true (the snap moved that edge)'),
            ("click-pinned", {1: {"xfade": 0.03, "keep_edges": True}}, "trim that edge by hand in CapCut")):
        jd = make(tmp, name, x, segs([1.0, 1.0, 1.0], extra))
        rc, out = listen(jd)
        check(f"3: {name}: the click is at joint 1", rc == 0 and "listen: joint 1 at 1.00s" in out
              and "a click right on the cut" in out, out)
        check(f"3: {name}: it names the segment and its words", 'into segments[1] ("line 1 goes here…")' in out, out)
        check(f"3: {name}: the fix", want in out, out)
        check(f"3: {name}: the other joint is fine", "joint 2" not in out, out)

    # ------------------------------------------------------------ 4: a dip
    x = voice(3 * RATE)
    fade_to_silence(x, 2 * RATE)
    jd = make(tmp, "dip", x, segs([1.0, 1.0, 1.0]))
    rc, out = listen(jd)
    check("4: the dip is at joint 2", rc == 0 and "listen: joint 2 at 2.00s" in out and "the sound drops" in out, out)
    check("4: one dip is not the stitch broken", "/report-a-problem" not in out, out)

    # ------------------------------------------------------------ 5: the same fault everywhere
    lengths = [0.5] * 12
    x = voice(6 * RATE)
    for j in range(1, 12):
        fade_to_silence(x, int(j * 0.5 * RATE))
    jd = make(tmp, "broken", x, segs(lengths))
    rc, out = listen(jd)
    check("5: every joint dips", out.count("listen: joint") == 11, out)
    check("5: the stitch is broken, not the cut", "⚠ joints: dips at 11 of 11 joints" in out
          and "/report-a-problem" in out, out)

    # ------------------------------------------------------------ 6: length
    x = voice(3 * RATE)
    jd = make(tmp, "stale", x, segs([1.0, 1.0, 0.5]))
    rc, out = listen(jd)
    check("6: a stale plan says stitch again", rc == 0 and "⚠ length" in out and "Stitch again" in out
          and "/report-a-problem" not in out, out)
    check("6: with the stitch's real path", os.path.join(SCRIPTS, "stitch-cut.sh") in out, out)
    x = voice(3 * RATE)
    x[RATE:RATE] = [0.0] * int(0.04 * RATE)   # 40 ms of padding where the segments meet
    x = x[:3 * RATE + int(0.04 * RATE)]
    jd = make(tmp, "padded", x, segs([1.0, 1.0, 1.0]))
    rc, out = listen(jd)
    check("6: padded silence is dead air at that joint", "dead air" in out and "joint 1 at 1.00s" in out, out)
    check("6: and no crossfade is offered for it", "came from the stitch" in out and '"xfade"' not in out, out)
    check("6: and the length line sends it to /report-a-problem", "⚠ length" in out and "/report-a-problem" in out, out)

    # ------------------------------------------------------------ 7: nothing / too little
    os.makedirs(os.path.join(tmp, "empty", "outputs"))
    rc, out = listen(os.path.join(tmp, "empty"))
    check("7: nothing to hear is NOT CHECKED, exit 2", rc == 2 and "NOT CHECKED" in out, out)
    jd = make(tmp, "short", voice(RATE // 2), segs([0.25, 0.25]))
    rc, out = listen(jd)
    check("7: under a second is skipped", rc == 0 and "too short" in out, out)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(fails)) if fails else "sound check: every fault heard where it is, with its fix")
sys.exit(1 if fails else 0)
