#!/usr/bin/env python3
"""your-turn.py — pull a creator's hand-trimmed cut back OUT of a CapCut draft.

The round trip: the engine hands the creator a rough-cut CapCut draft. She fixes the
one snag by hand on the timeline (trims a clip, drops a stumble the tools missed),
saves, and quits CapCut. This reads her trimmed timeline back and rewrites the job's
`cuts.json` to match, so the FULL styled build (zooms, punch-ins, SFX) can rebuild on
top of HER cut, clean, in one pass, to a new draft version.

Why this is safe: the Yap builders (cleanyap/superyap) place each footage segment as
`add_video(video_url=raw_clip, start=..., end=...)`, so a segment's `source_timerange`
is already in RAW-CLIP seconds, the same space as `cuts.json`. Her trim needs no
time-base conversion, it is read straight off the draft.

It ONLY supports a draft whose footage is the job's raw clips (the Yap rough-cut draft).
A draft built from a pre-rendered base (a *.NOTEXT.mp4 render, a baked MP4) is refused
with a clear message, because its source ranges are not raw-clip time.

usage:
  python3 your-turn.py <job> [--draft <name-or-dir>] [--apply]
    (dry run by default: prints what it read and how it differs from the current cut.
     --apply backs up cuts.json, writes the new one, and re-derives the transcript.)
"""
import json, os, sys, glob, subprocess, shutil, tempfile
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "../../../../product"))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
HERE = os.path.dirname(os.path.abspath(__file__))
# One answer for every draft writer: CapCut's own folder, or the staging folder when a Microsoft Store
# Claude app would hide new drafts from CapCut (product/capcut_store_redirect.py).
CAPCUT_ROOT = __import__("capcut_store_redirect").drafts_root()

def die(msg): print(f"✗ {msg}", file=sys.stderr); sys.exit(1)

def capcut_running():
    # The shared check: bytes-safe on a non-English Windows (tasklist prints in the OEM codepage), and
    # "could not tell" counts as open, never as closed.
    return _ds.capcut_running() is not False

def load_words(jobdir):
    """words.json -> {clip_basename: [{w,start,end}, ...]} plus the set of raw clip names."""
    wp = os.path.join(jobdir, "transcript", "words.json")
    if not os.path.exists(wp): die(f"no transcript/words.json in {jobdir} (run the rough cut first)")
    d = json.load(open(wp, encoding="utf-8"))
    by_clip = {}
    for c in d.get("clips", []):
        by_clip[os.path.basename(c.get("clip") or c.get("path", ""))] = c.get("words", [])
    return by_clip

def resolve_path(path, draft_dir):
    """CapCut stores media as a ##_draftpath_placeholder_<token>_## path or an absolute path."""
    if path and path.startswith("##"):
        i = path.find("_##")
        if i != -1: return draft_dir + path[i+3:]
    return path or ""

def _probe(path):
    """A content fingerprint (size, (width,height,duration)) for a media file. The engine copies each raw
    clip INTO the draft under a hashed name (video_<hash>.mp4), so the footage filename no longer matches
    the raw clip — but the bytes do (it's a byte copy), and duration+resolution survive even a rewrap. This
    is what lets us recognize a rough-cut draft by CONTENT instead of a filename that never survives."""
    if not path or not os.path.exists(path):
        return None
    try: size = os.path.getsize(path)
    except OSError: return None
    try:
        out = tuple(subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path], text=True, stderr=subprocess.DEVNULL).split())
    except Exception:
        out = ()
    return (size, out)

def _raw_fingerprints(jobdir, raw_clips):
    """{raw_clip_basename: fingerprint} for the job's raw clips in projects/<job>/raw/."""
    rawdir = os.path.join(jobdir, "raw")
    fp = {}
    for name in raw_clips:
        f = _probe(os.path.join(rawdir, name))
        if f: fp[name] = f
    return fp

def match_material_to_raw(draft, draft_dir, raw_clips, raw_fp):
    """Map each footage MATERIAL id in the draft to a raw clip of this job. Tries, in order: the filename
    still matching (older/direct-reference drafts), then a content match (size, or duration+resolution),
    then a single-clip fallback (if the job has exactly one raw clip, all footage must be it). Returns
    {material_id: raw_clip_basename} — empty only if the footage really isn't this job's raw clips."""
    mats = {m["id"]: m for m in draft.get("materials", {}).get("videos", [])}
    out = {}
    for mid in {s.get("material_id") for s in main_video_track(draft)["segments"]}:
        rp = resolve_path(mats.get(mid, {}).get("path", ""), draft_dir)
        base = os.path.basename(rp)
        if base in raw_clips:
            out[mid] = base; continue
        fp = _probe(rp)
        hit = None
        if fp:
            for name, rf in raw_fp.items():
                if fp[0] == rf[0] or (fp[1] and fp[1] == rf[1]):
                    hit = name; break
        if hit is None and len(raw_clips) == 1:
            hit = next(iter(raw_clips))
        if hit: out[mid] = hit
    return out

def main_video_track(draft):
    vids = [t for t in draft.get("tracks", []) if t.get("type") == "video" and t.get("segments")]
    if not vids: die("draft has no video segments")
    return max(vids, key=lambda t: len(t["segments"]))

def draft_clips(draft, draft_dir):
    mats = {m["id"]: m for m in draft.get("materials", {}).get("videos", [])}
    out = {}
    for seg in main_video_track(draft)["segments"]:
        m = mats.get(seg.get("material_id"), {})
        out[seg.get("material_id")] = os.path.basename(resolve_path(m.get("path", ""), draft_dir))
    return out

def find_draft(job, jobdir, raw_clips, raw_fp):
    """Pick the most recent CapCut draft whose footage is this job's raw clips — matched by CONTENT, since
    the engine renames footage into the draft. Content-probing every draft is costly, so scan newest-first
    and stop at the first match (the target is always a recent build)."""
    # Her trimmed draft may sit in CapCut's own folder even when the engine builds elsewhere (a Mac that keeps
    # the engine out of Movies): look in every place a draft of hers can be. Reading only.
    _found = [p for r in __import__("capcut_store_redirect").lookup_roots(CAPCUT_ROOT) for p in _ds.draft_jsons_under(r)]
    for info in sorted(_found, key=os.path.getmtime, reverse=True):
        ddir = os.path.dirname(info)
        try: d = json.load(open(info, encoding="utf-8"))
        except Exception: continue
        try:
            if match_material_to_raw(d, ddir, raw_clips, raw_fp):
                return ddir
        except SystemExit:
            continue
    return None

LOW_CONFIDENCE = "⚠ low-confidence timestamps — verify against the clip, don't trust this label"


def transcript_for(clip, st, en, by_clip):
    """-> (the words this range keeps, whether their timestamps can be trusted as a label)."""
    words = by_clip.get(clip, [])
    kept = [w for w in words if st <= (w["start"] + w["end"]) / 2 <= en]
    text = " ".join(w.get("word", w.get("w", "")) for w in kept).strip()
    # Bug #4: this label is a naive midpoint lookup against RAW words.json — the same forced-alignment
    # timestamps that collapse across a repeated phrase (Bug #2). When confidence there is low the label can
    # be plain wrong (it once made a reviewer nearly "fix" audio that was actually correct). So flag it rather
    # than presenting it as certain — the fix is to trust the clip, not this preview label. The flag is
    # printed beside the line and never written INTO the label: cuts.json's "transcript" is read back as the
    # words the cut says (verify-cut compares the audio against it, the style plan shows it), and a warning
    # stored there reads as speech.
    probs = [float(w.get("score", w.get("prob", 1.0))) for w in kept]
    return text, not (probs and sum(probs) / len(probs) < 0.5)

def extract(draft, draft_dir, by_clip, raw_clips, raw_fp):
    track = main_video_track(draft)
    # map each footage material -> its raw clip by content (filename no longer survives the build)
    mat_raw = match_material_to_raw(draft, draft_dir, raw_clips, raw_fp)
    if not mat_raw:
        die("this draft's footage is not the job's raw clips (looks like a rendered base, "
            "e.g. a .NOTEXT.mp4). Pull-back only supports the raw rough-cut draft.")
    segs = sorted(track["segments"], key=lambda s: s.get("target_timerange", {}).get("start", 0))
    cuts, doubtful = [], set()
    for s in segs:
        clip = mat_raw.get(s.get("material_id"))         # the RAW clip name, for word lookup
        if not clip:                                     # a segment whose material didn't map — skip safely
            continue
        sr = s.get("source_timerange", {})
        st = sr.get("start", 0) / 1e6
        en = st + sr.get("duration", 0) / 1e6
        text, trusted = transcript_for(clip, st, en, by_clip)
        if not trusted:
            doubtful.add(len(cuts))
        cut = {"clip": clip, "start": st, "end": en, "transcript": text}
        cut.update(_her_settings(s, draft, clip, raw_fp))
        cuts.append(cut)
    return cuts, doubtful


def _her_settings(seg, draft, clip, raw_fp):
    """What she set on this clip in CapCut beyond its in and out points, so the rebuild reproduces it exactly:
    its speed, her zoom and framing, and whether she split its sound off onto its own audio clip."""
    out = {}
    sp = float(seg.get("speed", 1.0) or 1.0)
    if abs(sp - 1.0) > 1e-4: out["speed"] = sp
    c = seg.get("clip") or {}
    sc = float((c.get("scale") or {}).get("x", 1.0))
    tx = float((c.get("transform") or {}).get("x", 0.0))
    ty = float((c.get("transform") or {}).get("y", 0.0))
    if abs(sc - 1.0) > 1e-4: out["scale"] = round(sc, 6)
    if abs(tx) > 1e-4: out["x"] = round(tx, 6)
    if abs(ty) > 1e-4: out["y"] = round(ty, 6)
    mats = {m["id"]: m for m in draft.get("materials", {}).get("videos", [])}
    if mats.get(seg.get("material_id"), {}).get("has_sound_separated"): out["audio_detached"] = True
    # A clip she muted on the timeline (volume 0, the way a music-and-text build lays its silent b-roll) stays
    # silent: the cut carries the same flag the stitch and the CapCut builder already read as "no sound here".
    elif seg.get("volume") is not None and float(seg["volume"]) <= 1e-4: out["audio_detached"] = True
    return out


def audio_overlays(draft, draft_dir, raw_clips, raw_fp):
    """The audio clips she laid on audio tracks that come from this job's raw clips (a split-off sound, a
    lead-in under the clip before). Music or a sound effect she added from elsewhere is not part of the cut
    and is left out; the count of those is returned so it can be said out loud."""
    mats = {m["id"]: m for k in ("audios", "videos") for m in draft.get("materials", {}).get(k, [])}
    out, other = [], 0
    for t in draft.get("tracks", []):
        if t.get("type") != "audio":
            continue
        for seg in t.get("segments", []):
            path = resolve_path(mats.get(seg.get("material_id"), {}).get("path", ""), draft_dir)
            name = os.path.basename(path)
            if name not in raw_clips:
                fp = _probe(path)
                name = next((n for n, rf in raw_fp.items() if fp and (fp[0] == rf[0] or (fp[1] and fp[1] == rf[1]))), None)
            if not name:
                other += 1
                continue
            sr, tr = seg.get("source_timerange", {}), seg.get("target_timerange", {})
            out.append({"clip": name, "start": sr.get("start", 0) / 1e6,
                        "end": (sr.get("start", 0) + sr.get("duration", 0)) / 1e6,
                        "target_start": tr.get("start", 0) / 1e6, "volume": seg.get("volume", 1.0)})
    return sorted(out, key=lambda o: o["target_start"]), other

def dur(cuts): return sum((c["end"] - c["start"]) / float(c.get("speed", 1.0) or 1.0) for c in cuts)

def main():
    args = sys.argv[1:]
    if not args: die("usage: your-turn.py <job> [--draft <name-or-dir>] [--apply]")
    job = args[0]; apply = "--apply" in args
    draft_arg = None
    if "--draft" in args: draft_arg = args[args.index("--draft") + 1]

    jobdir = job if os.path.isdir(job) else os.path.join("projects", job)
    if not os.path.isdir(jobdir): die(f"no such job dir: {jobdir}")
    cuts_path = os.path.join(jobdir, "transcript", "cuts.json")
    by_clip = load_words(jobdir)
    raw_clips = set(by_clip.keys())
    raw_fp = _raw_fingerprints(jobdir, raw_clips)   # content fingerprints of the raw clips (name-independent match)

    # unknown (None) counts as open: guessing "closed" here is how a trim gets clobbered.
    if capcut_running() is not False:
        die("CapCut is open, or I could not tell whether it is. Save your trim, then QUIT CapCut (it clobbers "
            "the draft file while open), then re-run.")

    # resolve the draft
    if draft_arg and os.path.isdir(draft_arg):
        ddir = draft_arg
    elif draft_arg:
        ddir = __import__("capcut_store_redirect").find_draft(draft_arg, CAPCUT_ROOT)   # read only
        if not os.path.isdir(ddir): die(f"no CapCut draft named {draft_arg}")
    else:
        ddir = find_draft(job, jobdir, raw_clips, raw_fp)
        if not ddir: die("could not find a CapCut draft using this job's raw clips. "
                         "Pass --draft <name> (the folder name under CapCut's Projects dir).")
    draft = json.load(open(_ds.draft_json(ddir), encoding="utf-8"))

    new_cuts, doubtful = extract(draft, ddir, by_clip, raw_clips, raw_fp)
    overlays, other_audio = audio_overlays(draft, ddir, raw_clips, raw_fp)
    # cuts.json is canonically {"segments":[...]}; tolerate an old bare-list file too (never crash reading it)
    if os.path.exists(cuts_path):
        _old = json.load(open(cuts_path, encoding="utf-8"))
        old_cuts = _old["segments"] if isinstance(_old, dict) else _old
    else:
        old_cuts = []

    print(f"draft:      {os.path.basename(ddir)}")
    print(f"was:        {len(old_cuts)} segments, {dur(old_cuts):.1f}s")
    print(f"your cut:   {len(new_cuts)} segments, {dur(new_cuts):.1f}s")
    delta = len(old_cuts) - len(new_cuts)
    print(f"change:     {'-' if delta>0 else '+' if delta<0 else '±'}{abs(delta)} segments, "
          f"{dur(new_cuts)-dur(old_cuts):+.1f}s")
    print("--- your cut ---")
    for i, c in enumerate(new_cuts, 1):
        extras = " ".join(f"{k}={v}" for k, v in c.items() if k in ("speed", "scale", "x", "y", "audio_detached"))
        print(f"  {i:>2}. {c['clip']}  {c['start']:.2f}-{c['end']:.2f}  {c['transcript'][:52]}"
              + (f"   [{extras}]" if extras else ""))
        if i - 1 in doubtful:
            print(f"      {LOW_CONFIDENCE}")

    for o in overlays:
        print(f"  audio clip: {o['clip']}  {o['start']:.2f}-{o['end']:.2f}  at {o['target_start']:.2f}s")
    if other_audio:
        print(f"  ({other_audio} other audio clip(s), music or sound effects, are not part of the cut; "
              f"the build adds its own sound design)")

    if not apply:
        print("\n(dry run) re-run with --apply to write cuts.json + re-derive the transcript.")
        return
    # apply: back up, write in the canonical {"segments":[...]} shape (a bare list TypeErrors every
    # downstream reader — clean_cut / trim-restarts / splice all do json.load(...)["segments"]).
    if os.path.exists(cuts_path):
        shutil.copy2(cuts_path, cuts_path.replace(".json", ".pre-your-turn.json"))
    with open(cuts_path, "w", encoding="utf-8") as fh:
        json.dump({"segments": new_cuts, "audio_overlays": overlays} if overlays else {"segments": new_cuts},
                  fh, indent=2)
    # stitch-cut.sh stitches the SCRATCH copy of the plan, not this one, and then saves what it stitched over
    # this file. Left alone, that scratch copy still holds the cut from before her trim, so the next splice
    # quietly put the old cut back. Mirror it the way transcript-cut.py and trim-restarts.py do.
    _scratch = os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(os.path.abspath(jobdir)))
    os.makedirs(_scratch, exist_ok=True)
    shutil.copy(cuts_path, os.path.join(_scratch, "cuts.json"))
    # Bug #3: mark this as the creator's authoritative trim BEFORE cleaning, so clean_cut AND the next
    # stitch-cut.sh skip the restart-detector and never re-cut over her trim (her trim wins — enforced, not just
    # documented). Cleared by a fresh rough cut. snap-to-sound still runs (boundary snapping, no content removal).
    try:
        marker = os.path.join(jobdir, "transcript", ".your-turn-cut")
        json.dump({"source": "your-turn", "t": __import__("time").time()}, open(marker, "w", encoding="utf-8"))
        print("  ✓ marked as your-turn cut — trim-restarts won't run over it")
    except Exception as _e:
        print(f"  ⚠ could not write the your-turn marker ({_e}); pass TRIM_RESTARTS=0 to the rebuild to be safe")
    # rule 8: a hand-edited cuts.json must pass through clean_cut before any stitch. With the marker set above,
    # clean_cut leaves her cut exactly as set: no restart trim, no boundary snap. Best-effort — never silently skip.
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "product")))
        from clean_cut import clean_cut
        clean_cut(os.path.basename(jobdir))
        if getattr(clean_cut, "failed", None):
            # clean_cut records a crashed step instead of raising, so success has to be read, not assumed
            print(f"  ⚠ clean_cut: {', '.join(clean_cut.failed)} did not finish (reason above), so the cut is NOT "
                  f"cleaned yet. Fix that, then run the rule-8 gate before stitching:  "
                  f"python3 product/clean_cut.py {os.path.basename(jobdir)}")
        else:
            print("  ✓ clean_cut: your edges kept exactly as you set them (no restart trim, no boundary snap)")
    except Exception as _e:
        print(f"  ⚠ run the rule-8 gate before stitching:  python3 product/clean_cut.py {os.path.basename(jobdir)}  ({_e})")
    words_p = os.path.join(jobdir, "transcript", "words.json")
    out_t = os.path.join(jobdir, "outputs", f"{os.path.basename(jobdir)}.transcript.json")
    os.makedirs(os.path.dirname(out_t), exist_ok=True)
    corr = "presets/caption-corrections.json"
    cmd = [sys.executable, os.path.join(HERE, "kept-words.py"), words_p, cuts_path, out_t]
    if os.path.exists(corr): cmd.append(corr)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("\n✓ wrote cuts.json (backup: cuts.pre-your-turn.json) + re-derived transcript." if r.returncode == 0
          else f"\n⚠ cuts.json written, but kept-words failed:\n{r.stderr[:400]}")
    print("Next: rebuild the styled reel (cleanyap/superyap) — it goes to a NEW draft version, "
          "your trimmed draft is left untouched.")

if __name__ == "__main__":
    main()
