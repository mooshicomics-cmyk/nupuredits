# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""
broll-select.py — pick the best usable moments from an EXISTING b-roll library, for a VO Reel.

The headline promise of the Voiceover Reel: the creator dumps the footage she already has (messy, long,
more than she needs) and the engine finds the good parts. She does not hand-curate or shoot to a shot list.
This is that engine — the same family as cover-frame.py (stills), extended to clips.

For every clip it slides a window across the whole thing and scores each window on what's actually
computable — no guessing:
  • sharpness   — Laplacian variance (rejects motion-blur / soft focus)
  • exposure    — mean luma near mid (rejects crushed-dark / blown-out)
  • stability   — frame-to-frame motion (rejects shaky / whip-pan sections)
  • FLICKER     — measured as OSCILLATION (rapid back-and-forth) of whole-frame mean AND horizontal-band
                  (row-std) brightness, at NATIVE fps. Oscillation is the discriminator: real flicker
                  (LED / fluorescent / dappled tree light) alternates frame to frame; motion and cuts are
                  smooth/single-step and do NOT oscillate, so they don't false-positive. Flicker is a HARD
                  REJECT — do NOT try to deflicker-rescue: ffmpeg deflicker only fixes the whole-frame
                  average and can leave (or worsen) LOCAL band flicker while the whole-frame check reads
                  "clean." Learned the hard way on a real clip (locked). If a window flickers, drop it.
                  Every window is checked over its WHOLE length, a hold as much as a burst.
  • energy      — motion magnitude, tagged calm/still vs active/busy, to match a window to a beat's mood.
It keeps the best FEW windows per clip (not one), at two lengths — short BURST windows (--win, default 2s)
for the opener and longer HOLD windows (--hold, default 4s) for the beats that sit on a shot — so a shot plan
can pair every moment of the voiceover with the best part of a clip, not just the single best 2 seconds of
it. Writes broll-select.json (one entry per clip, `windows` inside, the top-level fields = its best window
for backward compatibility) + a labeled contact sheet with one tile PER WINDOW.

What it does NOT do — and says so honestly: it does not understand CONTENT. Which shot suits which line
(baby vs laptop vs kitchen) is a human/Claude call — read the contact sheet, because catalog/clip labels
are per-clip and often wrong for a given timestamp (a "holding toddler" clip can be an outdoor path or a
screen-grab at another moment). Sample the window, look, then pair.

A dropped clip says WHY (too dark, too bright, too soft, or flicker), so it is clear whether --allow-flicker
would bring it back. iPhone Cinematic mode imports as a pair: IMG_1234.MOV is the raw capture (a flat
picture plus a depth track only Photos can read) and IMG_E1234.MOV the rendered one with the blur baked in.
When both are in the library the raw one is skipped and the E twin is scored; a raw one on its own is kept
and named, so its flat look is never a surprise.

Usage:
  uv run product/broll-select.py --lib ~/my-footage --job my-reel
  uv run product/broll-select.py --lib projects/<job>/broll --job <job> --need 8

  --lib DIR     folder of clips (default: projects/<job>/broll)
  --job NAME    writes projects/<job>/broll-select.json + broll-candidates.jpg
  --need N      cap on how many CLIPS to surface (default 0 = every usable clip; a prepped grabs folder is
                already curated, dropping its 9th-best clip loses a moment the plan may need)
  --win S       BURST window length in seconds (default 2.0)
  --hold S      HOLD window length in seconds (default 4.0; beats that sit on one shot)
  --per-clip K  best clean windows to keep per clip, per length (default 3)
  --json        also print the selection to stdout
  --allow-flicker  keep a clip whose only flaw is flicker. Use when the oscillation is an
                intentional look (sun glare, lens flare, dappled light), not a defect.
"""
import argparse, json, os, subprocess, tempfile, statistics, glob, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

FLICKER_OSC    = 2      # oscillation count (whole-frame or band) at/above this in a window = flicker → reject
SHARP_FLOOR    = 12.0   # Laplacian var below this = too soft to use
EXPO_LO, EXPO_HI = 45, 215
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probe(v):
    # DISPLAYED size, not stored: phone footage is stored sideways with a rotation flag, and the whole
    # point of this selector is finding the VERTICAL clips with room for text. (product/probe.py)
    import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from probe import probe as _hf_probe
    p = _hf_probe(v)
    return int(p["width"]), int(p["height"]), float(p["duration"])


_HW = {"ok": None}
def ffdecode(args_after_ss, out_pattern):
    """Run an ffmpeg decode for frames. Tries the Mac's hardware decoder first (4K HEVC phone b-roll is
    ~5-10x faster through videotoolbox), falls back to software once if the hardware path refuses."""
    def run(hw):
        pre = ["ffmpeg", "-v", "error"] + (["-hwaccel", "videotoolbox"] if hw else [])
        r = subprocess.run(pre + args_after_ss + ["-y", out_pattern], capture_output=True)
        return r.returncode == 0
    if _HW["ok"] is not False and run(True):
        _HW["ok"] = True; return True
    _HW["ok"] = False
    return run(False)


def flicker_score(grays):
    """Real flicker = OSCILLATION of whole-frame mean AND band (row-std) at native fps. Motion/cuts are
    smooth or single-step, so they don't oscillate and don't false-positive. Returns an osc count."""
    import numpy as np
    if len(grays) < 5: return 0
    def osc(series, amp):
        d = [series[i]-series[i-1] for i in range(1, len(series))]
        return sum(1 for i in range(1, len(d)) if abs(d[i])>amp and abs(d[i-1])>amp and d[i]*d[i-1] < 0)
    whole = [float(g.mean()) for g in grays]
    band  = [float(np.std(g.mean(axis=1))) for g in grays]
    return max(osc(whole, 3), osc(band, 1.5))


def extract_frames(v, fps=2.0, cap=240):
    """ONE ffmpeg pass -> [(t, gray_uint8)] across the whole clip (for quality ranking; 2fps is fine here)."""
    import cv2
    tmp = tempfile.mkdtemp()
    ffdecode(["-i",v,"-vf",f"fps={fps},scale=128:-2",
                    "-frames:v",str(cap),], f"{tmp}/f%04d.png")
    out = []
    for i, f in enumerate(sorted(os.listdir(tmp))):
        im = cv2.imread(f"{tmp}/{f}", cv2.IMREAD_GRAYSCALE)
        if im is not None: out.append((i/fps, im))
    return out


def score_slice(grays):
    # sharpness / exposure / motion only — flicker is measured separately at native fps (2fps can't see it)
    import cv2, numpy as np
    if len(grays) < 3: return None
    sharp = statistics.mean(float(cv2.Laplacian(g, cv2.CV_64F).var()) for g in grays)
    expo  = statistics.mean(float(g.mean()) for g in grays)
    motion = statistics.mean(float(np.abs(grays[i].astype(np.int16)-grays[i-1].astype(np.int16)).mean())
                             for i in range(1, len(grays)))
    return {"sharpness": sharp, "exposure": expo, "motion": motion}


def _window_scores(frames, dur, win):
    """(start, scores) for every window of `win` seconds across the clip, half a window apart (0.75 s at least)."""
    step = max(0.75, win/2); t = 0.0
    while t + win <= max(win, dur):
        yield t, score_slice([g for ft, g in frames if t <= ft < t + win + 1e-6])
        t += step


def rank_windows(frames, dur, win):
    scored = []
    for t, m in _window_scores(frames, dur, win):
        if m and m["sharpness"] >= SHARP_FLOOR and EXPO_LO <= m["exposure"] <= EXPO_HI:
            m["t"] = round(t, 1); m["dur"] = win
            m["quality"] = round(min(1.0, m["sharpness"]/150) * (1.0 - min(1.0, abs(m["exposure"]-120)/120)), 3)
            m["energy"] = "active" if m["motion"] >= 6 else "calm"
            scored.append(m)
    return sorted(scored, key=lambda m: -m["quality"])


def why_dropped(frames, dur, win):
    """Why a clip came out with no usable window, in words that say what to do about it. The drop line used
    to read "soft/dark/flicker" whatever the cause, so nobody could tell whether --allow-flicker would bring
    the clip back. Same windows and floors as rank_windows; a clip whose windows pass on light and focus was
    dropped for flicker."""
    ms = [m for _t, m in _window_scores(frames, dur, win) if m]
    if not ms:
        return "no frames could be read from it"
    lit = [m for m in ms if EXPO_LO <= m["exposure"] <= EXPO_HI]
    if not lit:
        dark = sum(1 for m in ms if m["exposure"] < EXPO_LO)
        return "too dark in every window" if dark * 2 >= len(ms) else "too bright (blown out) in every window"
    if not any(m["sharpness"] >= SHARP_FLOOR for m in lit):
        return "too soft (blurred or out of focus) in every window"
    return ("flicker in every window checked (if the flicker is a look you want, like sun glare, "
            "run again with --allow-flicker)")


def window_flicker(v, t0, win):
    """Measure flicker (oscillation) at NATIVE fps on one window — the only way to see 30fps strobe."""
    import cv2
    tmp = tempfile.mkdtemp()
    ffdecode(["-ss",f"{t0:.2f}","-i",v,"-t",f"{win:.2f}","-an","-vf","scale=160:-2","-fps_mode","passthrough"], f"{tmp}/f%03d.png")
    gs = [cv2.imread(f"{tmp}/{f}", cv2.IMREAD_GRAYSCALE) for f in sorted(os.listdir(tmp))]
    return flicker_score([g for g in gs if g is not None])


def pick_clip_windows(v, frames, dur, win, per_clip=3, allow_flicker=False, kind="burst", clean_spans=()):
    """Rank windows by quality (2fps), then verify flicker at native fps on the best candidates and keep up
    to `per_clip` CLEAN, NON-OVERLAPPING windows (so a long clip offers several distinct moments, not one).
    Flicker = reject the window and move on (NO deflicker — it can't be trusted). Returns [] if none are clean.

    allow_flicker: the detector cannot tell a defect from an INTENTIONAL look. Sun glare, golden-hour
    flare and dappled light all oscillate exactly like LED strobe, so a clip the creator shot on purpose
    gets silently dropped. With this on, an all-flickering clip keeps its best window, flagged not rejected.
    Off by default: an unwanted strobe should still fail loudly."""
    ws = rank_windows(frames, dur, win)
    if not ws: return []
    kept = []; probed = 0
    for cand in ws:
        if len(kept) >= per_clip or probed >= per_clip + 2: break       # hard decode budget per clip per length
        if any(abs(cand["t"] - k["t"]) < win for k in kept): continue   # a distinct moment, not a re-slice
        # A burst window already proved the stretch it covers clean, so measure only what lies past it. This
        # used to skip the measurement for any hold that merely STARTED inside a clean burst, and measured the
        # rest for just 2 s, so a 4 s hold went in unchecked from the moment the burst ended.
        t0, t1 = cand["t"], cand["t"] + win
        proven = max((sp[1] for sp in clean_spans if sp[0] - 0.01 <= t0 <= sp[1] + 0.01), default=None)
        if proven is not None and proven >= t1 - 0.01:
            fl = 0                                                       # wholly inside a stretch proven clean
        else:
            start = t0 if proven is None else max(t0, proven)
            probed += 1
            fl = window_flicker(v, start, t1 - start)                    # the whole window, at native fps
        if fl < FLICKER_OSC:
            cand["flicker"] = fl; cand["flicker_status"] = "ok"; cand["kind"] = kind
            kept.append(_round(cand))
    if not kept and allow_flicker:
        ws[0]["flicker"] = window_flicker(v, ws[0]["t"], win)
        ws[0]["flicker_status"] = "flicker-kept"; ws[0]["kind"] = kind
        kept.append(_round(ws[0]))
    return kept


def pick_clip_window(v, dur, win, allow_flicker=False):
    """Back-compat: the single best window (what older callers expect)."""
    ws = pick_clip_windows(v, extract_frames(v), dur, win, per_clip=1, allow_flicker=allow_flicker)
    return ws[0] if ws else None


def _round(w):
    for k in ("sharpness","exposure","motion"): w[k] = round(w[k], 1)
    return w


def _has_depth_track(v):
    """True when a clip carries iPhone Cinematic mode's depth/disparity track ('dish'): the RAW capture,
    whose picture is flat. Probed, never guessed: both halves of the pair run the same length."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_tag_string",
                              "-of", "csv=p=0", v], capture_output=True, text=True).stdout
    except Exception:
        return False
    return "dish" in out.lower()


def _rendered_twin(raw, clips):
    """The rendered twin of a raw Cinematic capture in the same folder (IMG_1234.MOV -> IMG_E1234.MOV), or None."""
    d, stem = os.path.dirname(raw), os.path.splitext(os.path.basename(raw))[0].lower()
    names = {stem + "-e", stem + "_e"}
    if stem.startswith("img_"):
        names.add("img_e" + stem[4:])
    return next((c for c in clips if c != raw and os.path.dirname(c) == d
                 and os.path.splitext(os.path.basename(c))[0].lower() in names), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=None)
    ap.add_argument("--job", required=True)
    ap.add_argument("--need", type=int, default=0, help="cap on CLIPS surfaced; 0 = every usable clip (default)")
    ap.add_argument("--win", type=float, default=2.0, help="burst window length, seconds")
    ap.add_argument("--hold", type=float, default=4.0, help="hold window length, seconds (beats that sit on a shot)")
    ap.add_argument("--per-clip", type=int, default=3, help="best clean windows to keep per clip, per length")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-flicker", action="store_true",
                    help="keep clips whose only flaw is flicker (intentional sun glare / flare), flagged not dropped")
    args = ap.parse_args()

    lib = args.lib or f"{REPO}/projects/{args.job}/broll"
    lib = os.path.expanduser(lib)
    # RECURSIVE: a real library is organised into folders (broll/kids/, broll/work/, ...), so scan the
    # whole tree, not just the top level. Set-based + lowercased suffix so a clip is never listed twice.
    _EXTS = (".mp4", ".mov", ".m4v")
    # skip any folder or file whose name starts with "_" — broll-prep parks sub-3s scraps in `_too-short/`,
    # and that convention means "not a candidate" everywhere in this engine
    clips = sorted({p for p in glob.glob(f"{lib}/**/*", recursive=True)
                    if os.path.isfile(p) and os.path.splitext(p)[1].lower() in _EXTS
                    and not any(seg.startswith("_") for seg in os.path.relpath(p, lib).split(os.sep))})
    if not clips:
        sys.exit(f"no clips in {lib}")
    import cv2  # trigger install

    # iPhone Cinematic mode imports as a PAIR: the raw capture (a depth track beside a FLAT picture) and the
    # rendered E twin with the blur baked in. Scoring both put the flat one up as a clip of its own. When the
    # twin is here, score the twin; a raw capture on its own stays, named on its line.
    raw_cine = {c for c in clips if _has_depth_track(c)}
    twins = {c: _rendered_twin(c, clips) for c in raw_cine}
    picks = []
    for c in clips:
        if twins.get(c):
            print(f"  skip {os.path.basename(c):34} — raw Cinematic-mode capture (flat picture); scoring its "
                  f"rendered twin {os.path.basename(twins[c])} instead")
            continue
        try: w, h, dur = probe(c)
        except Exception: continue
        frames = extract_frames(c)                      # sampled once, scored at both window lengths
        wins = pick_clip_windows(c, frames, dur, args.win, args.per_clip, args.allow_flicker, kind="burst")
        hold = min(args.hold, dur)
        if hold >= args.win * 1.5:                      # a clip shorter than that has no separate "hold" moment
            spans = [(w["t"], w["t"] + w["dur"]) for w in wins if w["flicker_status"] == "ok"]
            wins += pick_clip_windows(c, frames, dur, hold, args.per_clip, args.allow_flicker, kind="hold", clean_spans=spans)
        if not wins:
            print(f"  drop {os.path.basename(c):34} — {why_dropped(frames, dur, args.win)}, no usable window")
            continue
        wins.sort(key=lambda m: -m["quality"])
        b = dict(wins[0])                               # top-level = the best window (back-compat for older readers)
        b["clip"] = os.path.basename(c); b["path"] = c; b["src_dur"] = round(dur,1)
        b["windows"] = wins
        picks.append(b)
        note = "  [FLICKER KEPT — glare?]" if b["flicker_status"]=="flicker-kept" else ""
        if c in raw_cine:
            note += ("  [raw Cinematic-mode capture: the picture is flat, the blur is only in its rendered E "
                     "version, which is not in this folder]")
        nb = sum(1 for m in wins if m["kind"]=="burst"); nh = sum(1 for m in wins if m["kind"]=="hold")
        print(f"  keep {b['clip']:34} best @{b['t']:>5}s q={b['quality']:.2f} {b['energy']:6}  ({nb} burst + {nh} hold windows){note}")

    picks.sort(key=lambda p: -p["quality"])
    if args.need > 0: picks = picks[:args.need]

    outdir = f"{REPO}/projects/{args.job}"; os.makedirs(outdir, exist_ok=True)
    json.dump({"lib": lib, "count": len(picks), "picks": picks},
              open(f"{outdir}/broll-select.json","w", encoding="utf-8"), indent=2)

    # contact sheet for content-verify: ONE TILE PER WINDOW (a human/Claude pairs beats to windows by content),
    # labelled clip · kind · in-point · energy on a dark strip so the label reads over any footage
    import numpy as np
    tiles = [(p, m) for p in picks for m in p["windows"]]
    cw, ch = 300, 168; cols = min(4, max(1, len(tiles))); rows = (len(tiles)+cols-1)//cols
    sheet = np.full((max(rows,1)*ch, cols*cw, 3), 25, np.uint8)
    for i, (p, m) in enumerate(tiles):
        tmp = tempfile.mkdtemp()
        ffdecode(["-ss",f"{m['t']+m['dur']/2:.2f}","-i",p["path"],"-an","-frames:v","1",
                  "-vf",f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch}"], f"{tmp}/c.png")
        im = cv2.imread(f"{tmp}/c.png")
        if im is None: continue
        cv2.rectangle(im, (0,0), (cw,26), (0,0,0), -1)
        cv2.putText(im, f"{i+1}. {p['clip'][:14]} {m['kind']} @{m['t']:.0f}s {m['energy']}", (6,18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,255), 1)
        r,cc = divmod(i, cols); sheet[r*ch:(r+1)*ch, cc*cw:(cc+1)*cw] = im
    cv2.imwrite(f"{outdir}/broll-candidates.jpg", sheet)

    nwin = len(tiles)
    print(f"\n{len(picks)} usable clips, {nwin} windows -> {os.path.relpath(outdir, REPO)}/broll-select.json")
    print(f"contact sheet -> {os.path.relpath(outdir, REPO)}/broll-candidates.jpg  (READ IT — pair shots to beats by content; labels/timestamps lie)")
    if args.json: print(json.dumps(picks, indent=2))


if __name__ == "__main__":
    main()
