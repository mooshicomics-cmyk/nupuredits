#!/usr/bin/env python3
"""sound-check.py: listen back to the stitch, the way stitch-cut.sh built it, and say what to do about it.

stitch-cut.sh makes the sound in three moves, and this reads the finished file back in the same order.

1. The master. A static gain (VOICE_GAIN_DB, +10 by default) into the voice master and its limiter, with a
   -1 dBFS ceiling, or -6 dBFS with WARM_MASTER=0 (the same switch the stitch reads). Reported: how much of
   her speech the limiter is holding down. Over the bar, the line names the gain to stitch again with: as
   many dB under the one used as it takes to come back to the bar, and never so many that the reel would
   come out quieter than the quietest reel the bar was measured on.
2. The joints. At every cut the outgoing sound runs on for the stitch's crossfade (6 ms, or the segment's own
   "xfade" in cuts.json) and fades into the next. Each joint is heard once, for a click (a burst on the cut
   that the sound around it never makes), a dip (the sound falling away on the cut while both sides carry
   sound) and dead air (exact digital silence). One joint is fixed on the segment it leads into: "xfade": 0.030
   first, which the stitch gives such a joint on its own (hear_each, below, is how it hears them), then
   "keep_edges": true. The same fault across the reel means the crossfade itself stopped working, which no
   setting fixes: /report-a-problem.
3. The length. The sound should run exactly as long as the saved cut plan adds up to, plus at most the one
   AAC frame (1024 samples) the encoder may add at the end.

Each bar was measured on real stitched cuts, with the stitch's faults rebuilt on purpose, so a warning fires
where a fault is and stays quiet where none is. It only reports: it never fails a build or writes a file.

usage: sound-check.py <job_dir>     (stitch-cut.sh runs it after every rendered stitch)
Reads outputs/<job>.mp4 and transcript/cuts.json. Exit 0 when it listened (whatever it heard) or the file
was too short to judge; exit 2 when there was nothing to listen to, which is NOT CHECKED, not clean.
Standard library only.
"""
import json, math, os, statistics, subprocess, sys
from array import array

for stream in (sys.stdout, sys.stderr):   # a cp1252 Windows console cannot print the status symbols
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

RATE = 48000                 # the master's sample rate (stitch-cut.sh resamples everything to it)
MS = RATE // 1000

# The stitch's own numbers (stitch-cut.sh: XF, the 3 ms floor in joint_xfade, the two limiter ceilings).
STITCH_XF = 0.006
STITCH_XF_FLOOR = 0.003
CEILINGS = {"voice": 0.89, "flat": 0.501}
LONGER_XFADE = 0.030         # the per-segment "xfade" the stitch documents for a caught attack

# One cycle of the voice at its low regular pitch (172 Hz, 5.8 ms, rounded up): the shortest window whose
# level does not ripple with the voice itself. The stitch's crossfade is the same length for the same reason.
CYCLE = 6 * MS
# Below this a 6 ms window is a phone mic's gated quiet, not sound: the quietest 1 in 100 windows of real
# finished masters sit under it.
SOUNDING_DBFS = -61.0

# Clicks. A step left at a cut comes out of the master's lowpass and the AAC encoder as a short burst of
# high-frequency energy (the second difference of the waveform). The loudest 1 ms burst inside the joint's
# crossfade is weighed against the loudest one within 20 ms on either side. Over 2x is more than uncut
# speech shows 99 times in 100.
BURST_WIN = MS
CLICK_AROUND = 20 * MS
CLICK_RATIO = 2.0
# Dips. One cycle centred on the cut against one cycle just outside the crossfade on each side, both sides
# sounding. Deeper than 7 dB is more than uncut speech shows 99 times in 100.
DIP_DB = 7.0
# Dead air: a whole cycle of exact zeros near a cut. The master never makes one; padded silence does.
DEAD_AIR = CYCLE
# One joint can be speech being itself. The crossfade has failed when the same fault stacks up: clicks or
# dips at REEL_FAULT_MIN joints and at least REEL_FAULT_SHARE of the joints heard, or (dips only) the typical
# joint sitting REEL_MEDIAN_DB or more under its quieter side, read once at least REEL_MEDIAN_MIN joints have
# sound on both sides. Where the typical joint sits depends on the speaker's room and mic, not only on the
# stitch: a creator's gated phone mic reads +0.5 to +13 dB on every reel of hers, while steady room tone that
# never gates reads about +1 dB through a working crossfade and dips under 0 on 1 reel in 17 (18 joints).
# Under 0 dB told a buyer with a working stitch, 18 clean joints and a typical joint 1 dB under, to report a
# broken one (2026-10-28). 3 dB: no working stitch on either sound reaches it (steady tone, 18 joints: never in
# 4,000 reels), while the faded-edge fault this rule exists for reads about -8 dB on steady tone (-6.6 at the
# shallowest 1 in 100), and on her reels the two the dip count misses read -3.4 and -4.2, still past it
# (dev-tools/soundcheck/DERIVATION.md, "The typical joint").
REEL_FAULT_MIN = 3
REEL_FAULT_SHARE = 0.10
REEL_MEDIAN_MIN = 8
REEL_MEDIAN_DB = 3.0

# The limiter. A 10 ms window peaking within 3 dB of the ceiling is a window the limiter is pulling down.
# Measured on one creator's real takes (18 reels), each rebuilt through this master at every whole gain from
# +4 to +16:
#   LIMIT_BAR      the most any of them is held at the default +10: past it, this take is hotter than all of them
#   HELD_PER_DB    the least the held share fell for each dB taken off above the bar, so the gain named is
#                  always enough to come back to it
#   QUIETEST_DBFS  the quietest reel's mean level at +10; the mean never fell more than 1 dB per dB taken
#                  off, so a reel suggested down by the dB its mean sits over this cannot come out quieter
LIMIT_WIN = 10 * MS
LIMIT_REACH_DB = 3.0
DEFAULT_GAIN = 10.0
LIMIT_BAR = {"voice": 56.0, "flat": 57.8}        # % of sounding windows
HELD_PER_DB = {"voice": 1.98, "flat": 2.94}      # percentage points per dB
QUIETEST_DBFS = {"voice": -17.4, "flat": -26.4}  # whole-file mean

AAC_FRAME = 1024             # samples the encoder may add after the last one
STREAM_SLACK = AAC_FRAME / RATE + 1 / 24   # sound vs picture track: one AAC frame and one video frame (as the stitch)
STITCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stitch-cut.sh")


def _say(line):
    print(line)


def _db(v):
    return 20 * math.log10(v) if v > 0 else -180.0


def _rms(pcm, lo, hi):
    lo, hi = max(0, lo), min(len(pcm), hi)
    if hi <= lo:
        return 0.0
    return math.sqrt(math.fsum(s * s for s in pcm[lo:hi]) / (hi - lo))


def _decode(mp4):
    """The left channel of the stitch's sound, as floats. Every bar below was measured on that one channel as
    it is; a mix of the two would move every level."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mp4, "-map", "0:a:0?", "-vn", "-ac", "2", "-f", "f32le", "-"],
                         capture_output=True).stdout
    both = array("f")
    both.frombytes(raw[:len(raw) // 8 * 8])
    return both[0::2]


# ── the plan ──────────────────────────────────────────────────────────────────────────────────────────────

def plan_joints(segs):
    """[(timeline seconds, index of the segment it leads into, its crossfade in seconds)], planned length.
    A clip sped up in CapCut plays (end - start) / speed long; the stitch records that as "played"."""
    def length(s):
        if "played" in s:
            return float(s["played"])
        return (float(s["end"]) - float(s["start"])) / float(s.get("speed", 1.0) or 1.0)
    joints, t = [], 0.0
    for i, s in enumerate(segs):
        if i:
            joints.append((t, i, max(STITCH_XF_FLOOR, float(s.get("xfade", STITCH_XF)))))
        t += length(s)
    return joints, t


def _words(seg, n=4):
    text = " ".join(str(seg.get("transcript", "")).split()[:n])
    return f' ("{text}…")' if text else ""


# ── the master ────────────────────────────────────────────────────────────────────────────────────────────

def hear_master(pcm, job_dir):
    master = "flat" if os.environ.get("WARM_MASTER", "1") == "0" else "voice"
    ceiling = CEILINGS[master]
    reach = ceiling * 10 ** (-LIMIT_REACH_DB / 20)
    sounding = held = 0
    for lo in range(0, len(pcm) - LIMIT_WIN + 1, LIMIT_WIN):
        block = pcm[lo:lo + LIMIT_WIN]
        if _db(math.sqrt(math.fsum(s * s for s in block) / LIMIT_WIN)) <= SOUNDING_DBFS:
            continue
        sounding += 1
        if max(max(block), -min(block)) >= reach:
            held += 1
    share = 100 * held / sounding if sounding else 0.0
    peak = max(max(pcm), -min(pcm))
    mean = _rms(pcm, 0, len(pcm))
    label = "voice master" if master == "voice" else "flat master (WARM_MASTER=0)"
    _say(f"[sound-check] master: {label}, ceiling {_db(ceiling):.1f} dBFS · mean {_db(mean):.1f} dBFS"
         f" · peak {_db(peak):.2f} dBFS")

    raw_gain = os.environ.get("VOICE_GAIN_DB") or f"{DEFAULT_GAIN:g}"
    try:
        gain = float(raw_gain)
    except ValueError:
        gain = DEFAULT_GAIN
    if share <= LIMIT_BAR[master]:
        _say(f"[sound-check] ✓ limiter: holding down {share:.0f}% of her speech, inside the range this master is"
             f" tuned for. Nothing to do.")
        return
    if not math.isfinite(gain):
        # inf and its kind get past ffmpeg and slam every sample into the ceiling
        _say(f"[sound-check] ⚠ limiter: VOICE_GAIN_DB is {raw_gain!r}, which is not a level in dB, so the limiter is"
             f" holding down {share:.0f}% of her speech. Stitch again without it (the default is"
             f" +{DEFAULT_GAIN:g}):  env -u VOICE_GAIN_DB bash {STITCH} {job_dir}")
        return
    needed = max(1, math.ceil((share - LIMIT_BAR[master]) / HELD_PER_DB[master]))
    room = math.floor(_db(mean) - QUIETEST_DBFS[master])   # dB to lose before the quietest measured reel
    step = min(needed, room)
    if step < 1:
        _say(f"[sound-check] limiter: at +{gain:g} dB it holds down {share:.0f}% of her speech, and this reel is"
             f" already as quiet as the quietest the bar was measured on, so less gain is not the fix and the cut"
             f" stands. A squashed stressed word, if you hear one, comes from here.")
        return
    short = "" if step == needed else (" That is as far down as it goes without coming out quieter than the quietest"
                                       " reel the bar was measured on, so some pressure stays.")
    _say(f"[sound-check] ⚠ limiter: the limiter is working hard. At +{gain:g} dB it holds down {share:.0f}% of"
         f" her speech (the bar is {LIMIT_BAR[master]:g}%), so stressed words can come out a little squashed."
         f" The cut is usable as it is. To give it headroom, stitch again {step} dB lower:  VOICE_GAIN_DB={gain - step:g} bash {STITCH} {job_dir}{short}")


# ── the joints ────────────────────────────────────────────────────────────────────────────────────────────

def _bursts(pcm, lo, hi, hop):
    """RMS of the second difference over each BURST_WIN window starting lo..hi (hop apart)."""
    out = []
    for a in range(max(1, lo), min(len(pcm) - 1, hi) - BURST_WIN + 1, hop):
        e = math.fsum((pcm[k + 1] - 2 * pcm[k] + pcm[k - 1]) ** 2 for k in range(a, a + BURST_WIN))
        out.append(math.sqrt(e / BURST_WIN))
    return out


def click_at(pcm, c, xf):
    """How far the loudest burst on the cut stands over the loudest within CLICK_AROUND either side."""
    on = _bursts(pcm, c - BURST_WIN // 2, c + xf + BURST_WIN // 2, BURST_WIN // 4)
    guard = 2 * MS
    around = (_bursts(pcm, c - CLICK_AROUND, c - guard, BURST_WIN // 2)
              + _bursts(pcm, c + xf + guard, c + xf + CLICK_AROUND + BURST_WIN, BURST_WIN // 2))
    if not on or not around:
        return 0.0
    return max(on) / max(max(around), 1e-12)


def dip_at(pcm, c, xf):
    """dB the cycle centred on the cut sits under the quieter side, or None when a side is gated quiet."""
    left = _db(_rms(pcm, c - 2 * CYCLE, c - CYCLE))
    right = _db(_rms(pcm, c + xf + CYCLE, c + xf + 2 * CYCLE))
    if min(left, right) <= SOUNDING_DBFS:
        return None
    return _db(_rms(pcm, c - CYCLE // 2, c + CYCLE // 2)) - min(left, right)


def dead_air_at(pcm, c, xf):
    """The longest run of exact zeros on the cut and within CLICK_AROUND of it."""
    best = run = 0
    for s in pcm[max(0, c - CLICK_AROUND):min(len(pcm), c + xf + CLICK_AROUND)]:
        run = run + 1 if s == 0.0 else 0
        best = max(best, run)
    return best


def hear_each(pcm, joints):
    """Every joint far enough from the ends of the file to have sound on both sides, heard once:
    [(n, timeline seconds, segment index, click ratio, dip depth or None, longest run of zeros, what was found)].
    The stitch hears its own joints with this too, before it hands the cut over."""
    reach = 2 * CYCLE + int(LONGER_XFADE * RATE) + CLICK_AROUND + BURST_WIN
    out = []
    for n, (t, i, xf_s) in enumerate(joints, 1):
        c, xf = int(round(t * RATE)), int(round(xf_s * RATE))
        if c - reach < 0 or c + reach > len(pcm):
            continue   # too close to an end of the file to have sound on both sides
        found = []
        ratio = click_at(pcm, c, xf)
        if ratio > CLICK_RATIO:
            found.append(f"a click right on the cut ({ratio:.1f}x the sound around it)")
        depth = dip_at(pcm, c, xf)
        if depth is not None and depth < -DIP_DB:
            found.append(f"the sound drops {-depth:.0f} dB right on the cut with sound on both sides")
        zeros = dead_air_at(pcm, c, xf)
        if zeros >= DEAD_AIR:
            found.append(f"{zeros / MS:.0f} ms of dead air (digital silence)")
        out.append((n, t, i, ratio, depth, zeros, found))
    return out


def stitch_broken(each):
    """What the joints say about the crossfade itself across the reel ([] when it is working)."""
    heard = len(each)
    clicks = sum(1 for e in each if e[3] > CLICK_RATIO)
    dips = sum(1 for e in each if e[4] is not None and e[4] < -DIP_DB)
    depths = [e[4] for e in each if e[4] is not None]
    pattern = []
    if clicks >= REEL_FAULT_MIN and clicks >= REEL_FAULT_SHARE * heard:
        pattern.append(f"clicks at {clicks} of {heard} joints")
    if dips >= REEL_FAULT_MIN and dips >= REEL_FAULT_SHARE * heard:
        pattern.append(f"dips at {dips} of {heard} joints")
    if len(depths) >= REEL_MEDIAN_MIN and statistics.median(depths) <= -REEL_MEDIAN_DB:
        pattern.append(f"the typical cut sits {-statistics.median(depths):.0f} dB under its quieter side")
    return pattern


def hear_joints(pcm, segs, joints):
    """Hear every joint; returns the timeline times of joints with dead air (the length check uses them)."""
    each = hear_each(pcm, joints)
    if not each:
        _say("[sound-check] joints: none far enough from the ends of the file to hear")
        return []
    faults = [e for e in each if e[6]]
    dead = [e[1] for e in each if e[5] >= DEAD_AIR]
    pattern = stitch_broken(each)
    if faults:
        _say(f"[sound-check] joints: {len(each)} heard, {len(faults)} worth a listen")
        for n, t, i, _r, _d, zeros, found in faults:
            fix = ("That silence came from the stitch, not the cut (see the length line)." if zeros >= DEAD_AIR
                   else _joint_fix(segs[i], i))
            _say(f"[sound-check]   listen: joint {n} at {t:.2f}s, into segments[{i}]{_words(segs[i])}: {'; '.join(found)}."
                 f" {fix}")
    if pattern:
        _say(f"[sound-check] ⚠ joints: {'; '.join(pattern)}. A working crossfade never leaves that pattern: the"
             f" stitch itself is broken here, not the cut. Run /report-a-problem before changing any segment.")
    elif not faults:
        _say(f"[sound-check] ✓ joints: {len(each)} heard, every crossfade carries the sound through")
    return dead


def _joint_fix(seg, i):
    """The next thing to try on the segment a faulty joint leads into, in the order the stitch offers them:
    a longer crossfade, then the segment's own edges instead of the snapped ones, then her hands."""
    where = f"segments[{i}] in transcript/cuts.json"
    if float(seg.get("xfade", 0) or 0) < LONGER_XFADE and not seg.get("_xfade_worse"):
        return f'If you hear it, give {where} "xfade": {LONGER_XFADE:.3f} and stitch again.'
    if not seg.get("keep_edges"):
        if seg.get("_xfade_worse"):   # the stitch tried the longer crossfade there and it made the joint worse
            return (f'If you hear it, give {where} "keep_edges": true (the snap moved that edge; the stitch tried a'
                    f' longer crossfade there and it made it worse) and stitch again.')
        return f'If you hear it, also give {where} "keep_edges": true (the snap moved that edge) and stitch again.'
    return "It already has a longer crossfade and its own edges, so if you hear it, trim that edge by hand in CapCut."


# ── the length ────────────────────────────────────────────────────────────────────────────────────────────

def hear_length(pcm, planned, n_segs, dead, job_dir, drift=None):
    over = len(pcm) - planned * RATE                 # samples past the plan
    slack = n_segs / 2                               # each segment's sound is trimmed to the nearest sample
    ms = over / MS
    # One AAC frame either way. A phone clip's sound track often ends a few ms before its picture, so a cut
    # that runs to the end of a clip comes out that much short; a cut plan that really changed is off by at
    # least a video frame (33 ms at 30 fps), past this either way. Short-only by a sample once read -3 ms as a
    # changed plan.
    if -(AAC_FRAME + slack) <= over <= AAC_FRAME + slack and not dead:
        _say(f"[sound-check] ✓ length: the sound matches the saved cut plan ({ms:+.1f} ms, inside one AAC frame)")
        return
    if dead:
        where = ", ".join(f"{t:.2f}s" for t in dead)
        _say(f"[sound-check] ⚠ length: the sound runs {len(pcm) / RATE:.3f}s against {planned:.3f}s planned"
             f" ({ms:+.0f} ms), with dead air at the joints at {where}. Silence was padded in where segments"
             f" meet, so the picture and her words drift apart from there on: run /report-a-problem.")
        return
    if drift is not None and drift < -STREAM_SLACK and over < 0:
        # The sound track itself ends before the picture: the render lost sound, the plan did not change. The
        # stitch measures this and rebuilds the sound on its own, so a cut still here was made before that.
        _say(f"[sound-check] ⚠ length: the sound track ends {-drift * 1000:.0f} ms before the picture, with no dead air"
             f" at any joint, so the sound came out short in the render (the cut plan is fine). Stitching again"
             f" rebuilds the sound under the picture:  bash {STITCH} {job_dir}   If this line comes back after"
             f" that, run /report-a-problem.")
        return
    _say(f"[sound-check] ⚠ length: the sound runs {len(pcm) / RATE:.3f}s against {planned:.3f}s planned ({ms:+.0f} ms)"
         f" and no joint has dead air, so this render and transcript/cuts.json describe different cuts (the"
         f" plan changed after the render). Stitch again so they agree:  bash {STITCH} {job_dir}")


def stream_drift(mp4):
    """The file's sound track length minus its picture length, in seconds (None when either can't be read)."""
    def one(kind):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", f"{kind}:0", "-show_entries",
                            "stream=duration", "-of", "default=nw=1:nk=1", mp4], capture_output=True, text=True)
        try:
            return float(r.stdout.split()[0])
        except (IndexError, ValueError):
            return None
    v, a = one("v"), one("a")
    return None if v is None or a is None else a - v


def main(argv):
    if len(argv) < 2:
        _say("usage: sound-check.py <job_dir>")
        return 2
    job_dir = os.path.abspath(argv[1])
    name = os.path.basename(job_dir)
    mp4 = os.path.join(job_dir, "outputs", name + ".mp4")
    cuts = os.path.join(job_dir, "transcript", "cuts.json")
    missing = [p for p in (mp4, cuts) if not os.path.exists(p)]
    if missing:
        _say(f"[sound-check] ⚠ NOT CHECKED: there is no {missing[0]} (is the job path right? has the cut been"
             f" stitched?)")
        return 2
    pcm = _decode(mp4)
    if len(pcm) < RATE:
        _say("[sound-check] under a second of sound, too short to judge: skipped")
        return 0
    if not any(pcm):
        # every sample exactly zero: there is no level to take a log of and no joint to hear
        _say("[sound-check] ⚠ SILENT: this cut's sound is digital silence from start to end, so there is nothing"
             " to listen to. Check that the raw clips have sound and that VOICE_GAIN_DB is a normal number of dB.")
        return 0
    with open(cuts, encoding="utf-8") as f:
        segs = json.load(f)["segments"]
    joints, planned = plan_joints(segs)
    hear_master(pcm, job_dir)
    dead = hear_joints(pcm, segs, joints)
    hear_length(pcm, planned, len(segs), dead, job_dir, stream_drift(mp4))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
