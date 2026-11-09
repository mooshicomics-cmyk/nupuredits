#!/usr/bin/env python3
"""sound-check's limiter line names a gain that is enough, and never one that makes the reel too quiet.

Built sound, no ffmpeg: 10 ms windows, a set share of them peaking at the ceiling (held by the limiter), the rest
sounding well under it, at a set mean level. hear_master() is then asked what to do.

  1. Under the bar: nothing to do.
  2. Over it: the dB named is the share over the bar divided by the least the share was measured to fall per dB,
     rounded up, so one re-stitch is enough.
  3. When that many dB would take the reel under the quietest measured reel, it names only what fits, and says so.
  4. A reel already that quiet: no gain is suggested, the cut stands.

Run:  python3 product/tests/test_sound_check_gain.py
"""
import contextlib, importlib.util, io, math, os, sys
from array import array

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location(
    "sound_check", os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "sound-check.py"))
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


def sound(held_pct, mean_dbfs, master="voice", windows=1000):
    """windows of LIMIT_WIN samples; held_pct of them touch the ceiling once; all at one RMS giving mean_dbfs."""
    rms = 10 ** (mean_dbfs / 20)
    ceiling = sc.CEILINGS[master]
    pcm = array("f")
    held = round(windows * held_pct / 100)
    for i in range(windows):
        block = [rms * (1 if k % 2 else -1) for k in range(sc.LIMIT_WIN)]
        if i < held:
            block[0] = ceiling
        pcm.extend(block)
    return pcm


def advice(held_pct, mean_dbfs, master="voice", gain=None):
    env = {"WARM_MASTER": "0" if master == "flat" else "1"}
    if gain is not None:
        env["VOICE_GAIN_DB"] = str(gain)
    saved = {k: os.environ.get(k) for k in ("WARM_MASTER", "VOICE_GAIN_DB")}
    os.environ.pop("VOICE_GAIN_DB", None)
    os.environ.update(env)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            sc.hear_master(sound(held_pct, mean_dbfs, master), "/jobs/my-reel")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return out.getvalue()


out = advice(sc.LIMIT_BAR["voice"] - 6, -12.0)
check("1: under the bar there is nothing to do", "✓ limiter" in out and "VOICE_GAIN_DB=" not in out, out)

bar, per = sc.LIMIT_BAR["voice"], sc.HELD_PER_DB["voice"]
out = advice(bar + 4, -10.0)
want = math.ceil(4 / per)
check(f"2: {bar + 4:g}% held at +10 names {want} dB lower", f"stitch again {want} dB lower:  VOICE_GAIN_DB={10 - want:g} " in out, out)
check("2: and it all fits, so no 'as far down' note", "as far down" not in out, out)

bar_f, per_f = sc.LIMIT_BAR["flat"], sc.HELD_PER_DB["flat"]
out = advice(bar_f + 5, -18.0, master="flat", gain=12)
want = math.ceil(5 / per_f)
check(f"2: flat master, +12: names {want} dB lower", f"VOICE_GAIN_DB={12 - want:g} " in out, out)

quiet = sc.QUIETEST_DBFS["voice"]
out = advice(bar + 20, quiet + 3.5)
check("3: only the dB that fit over the quietest reel (3)", "stitch again 3 dB lower:  VOICE_GAIN_DB=7 " in out, out)
check("3: and it says some pressure stays", "as far down as it goes" in out, out)

out = advice(bar + 10, quiet + 0.5)
check("4: a reel already that quiet gets no lower gain", "VOICE_GAIN_DB=" not in out and "the cut stands" in out, out)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "sound-check gain: enough in one re-stitch, never too quiet"))
sys.exit(1 if fails else 0)
