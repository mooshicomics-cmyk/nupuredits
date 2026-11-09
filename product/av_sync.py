#!/usr/bin/env python3
"""av_sync.py — her clip's sound and picture on one clock, before anything is heard or cut.

A phone clip can carry its sound starting later than its picture: an iPhone clip copied out of Photos had its audio
start at 0.703 s with the video at 0 (a buyer's report, 2026-10-21). The listener writes each word on the SOUND's
own clock (its first sample is 0 s); the stitch trims on the FILE's clock. So every cut landed 0.703 s early: the
end of each line clipped, a sliver of the line before it leaking in, and the cut's sound came out 703 ms short.

So at intake, right after the HDR step, each clip in projects/<job>/raw/ whose sound starts more than LEAD_LIMIT
after the file does is rewritten in place: the picture copied untouched (never re-encoded, its rotation kept), and
silence laid in front of the sound so it starts at 0 with the picture. The words are then written on the file's
clock, and every later step (the cut, the snap, the captions, CapCut) agrees with them.

Her original (inbox/, Photos, wherever she named it) is never touched: raw/ holds the job's own copy.

A job heard BEFORE this existed (engine 2.3.6 and earlier) has its words, and the cut made from them, on the old
clock, and handing that transcript back kept the reel choppy after the update (a buyer, 2026-10-22). Listening
again would throw away her hand fixes and every cut decision keyed to her words, so `catch_up` lines the clip up and
moves what was measured on the SOUND's clock by the same lead, once: the file's clock never moves (silence goes in
front of the sound, so every sound plays at the same moment of the file as before), and after the silence a word
heard at t plays at t + lead. Only the late clips move. What moves and what stays:

  transcript/words.json       every word of that clip (start, end, the "was" a re-stamp kept, the words a quiet clip
                              set aside); the clip is marked "sound_lined_up" so it is never moved twice
  transcript/cuts.json        each piece of that clip, and the scratch copy the stitch reads first. A piece the snap
  + the scratch cuts.json     moved goes back to the edges it was planned on (_snapped_from: her words, so the
                              sound's clock) plus the lead, and the next stitch snaps it again on one clock: the
                              snap had measured the file's sound near a stamp 0.7 s off, so its edges were noise.
                              A piece whose edges are hers (keep_edges: her trims on the visual editor, her cuts by
                              time, a your-turn cut) moves by the lead as it is, so it keeps its place against her
                              words, as her page showed it. A clip with no talking stays put: its pieces are seconds
                              of the file, never words.
  her visual editor           review/script.json and the preview are made again from the files above. A cut she
                              sent from a page made before the line-up carries the old transcript's id: the record
                              below lets visual_editor.apply_edits move its trims and time cuts by the same lead
                              instead of refusing it.
  stays as it is              everything on the CUT's clock (captions, looks, sounds, graphics, accents, notes keyed
                              to a word), the audio pieces a your-turn cut laid from CapCut (CapCut placed them on
                              the picture's clock), the CapCut drafts already made, transcript/history/.

Both files go to transcript/history/ first (word-timings.sh's keep_previous_transcript naming). Every step is written
whole and marked, so a run cut off halfway finishes on the next one and never moves anything twice; the record of
what moved is transcript/.sound-lined-up.json. A clip that cannot be lined up is said once, logged for
/report-a-problem, and left as it is (it is tried again only when the file changes). word-timings.sh runs it before
handing a heard job back, stitch-cut.sh before every stitch, product/clean_cut.py before its passes and the visual
editor when it opens, when her cut arrives and before Finish, so every re-cut and every export reaches it.

    python3 product/av_sync.py <job>              which clips start their sound late (nothing changes)
    python3 product/av_sync.py <job> --apply      line them up (a heard job: and move its words and cut with them)
    ... --apply --relisten                        line up only: a new listen follows (word-timings.sh --force)
    ... --quiet                                   say nothing when there is nothing to do (the stitch's call)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hdr import videos  # noqa: E402  (the same "which files are her clips" rule as the HDR step)
try:
    from swap import replace as swap_in  # noqa: E402
except ImportError:
    swap_in = os.replace

LEAD_LIMIT = 0.05      # s. Under this the two clocks already agree to within the snap's own reach (AAC's priming
                       # alone puts a normal clip's sound 21-24 ms either side of 0)


def _job_dir(arg):
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    return os.path.join(os.path.dirname(HERE), "projects", arg)


def media_dir(job_dir):
    """raw/ when the job has one; a job from before intake keeps its clips at the top of the folder."""
    raw = os.path.join(job_dir, "raw")
    return raw if os.path.isdir(raw) else job_dir


def _starts(path):
    """(format start, first video stream's start, first audio stream's start), each None when unknown."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time:format=start_time",
                              "-of", "json", path], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60).stdout
        d = json.loads(out or "{}")
    except Exception:
        return None, None, None

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    first = {}
    for st in d.get("streams") or []:
        first.setdefault(st.get("codec_type"), num(st.get("start_time")))
    return num((d.get("format") or {}).get("start_time")), first.get("video"), first.get("audio")


def audio_lead(path):
    """Seconds the clip's sound starts after the file does (ffmpeg's clock: the file's own start is 0 there), or None
    when it has no sound or no picture. Positive = the sound starts late: the case that cuts early."""
    fmt, v, a = _starts(path)
    if v is None or a is None:
        return None
    return a - (fmt if fmt is not None else min(v, a))


def late_clips(folder):
    """[{path, name, lead}] for every clip whose sound starts more than LEAD_LIMIT late."""
    out = []
    for p in videos(folder):
        lead = audio_lead(p)
        if lead is not None and lead > LEAD_LIMIT:
            out.append({"path": p, "name": os.path.basename(p), "lead": lead})
    return out


def _frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=600).stdout.strip()
    try:
        return int(out.split(",")[0])
    except ValueError:
        return None


def line_up(path):
    """Rewrite one clip so its sound starts with its picture: picture copied, silence padded in front of the sound.
    Atomic (a temp file next to it, then one swap). Raises RuntimeError and leaves the clip as it was when the copy
    does not come out right."""
    stem, ext = os.path.splitext(path)
    tmp = f"{os.path.join(os.path.dirname(path), '.' + os.path.basename(stem))}.sync{ext}"
    # FIRST audio stream only: a newer iPhone .mov also carries a spatial-audio track (APAC) ffmpeg cannot decode
    # (product/hdr.py found the same). Every video stream is copied when the container takes them (a Cinematic clip's
    # depth track keeps the "cut the E twin" check true); otherwise the picture alone.
    base = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", path]
    tail = ["-map", "0:a:0", "-c:v", "copy", "-af", "aresample=async=1:first_pts=0", "-c:a", "aac", "-b:a", "320k",
            "-map_metadata", "0", "-movflags", "+faststart", tmp]
    err = ""
    for vmap in (["-map", "0:v"], ["-map", "0:v:0"]):
        r = subprocess.run(base + vmap + tail, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp):
            break
        err = (r.stderr or "ffmpeg failed").strip()[-300:]
        _drop(tmp)
    else:
        raise RuntimeError(f"could not line up the sound of {os.path.basename(path)}: {err}")
    lead = audio_lead(tmp)
    if lead is None or abs(lead) > LEAD_LIMIT or _frames(tmp) != _frames(path):
        _drop(tmp)
        raise RuntimeError(f"the lined-up copy of {os.path.basename(path)} did not come out right "
                           f"(sound starts {lead if lead is not None else '?'} s); the clip is left as it was")
    try:
        swap_in(tmp, path)
    except OSError:
        _drop(tmp)
        raise


def _drop(p):
    try:
        os.remove(p)
    except OSError:
        pass


def heard(job_dir):
    return os.path.isfile(os.path.join(job_dir, "transcript", "words.json"))


# ── a job heard before the line-up existed ─────────────────────────────────────────────────────────────────────
LINED_UP = "sound_lined_up"       # on a words.json clip: the seconds its words moved (never moved again)
CUT_MARK = "_sound_lined_up"      # on a cut plan: {clip: seconds} already moved in THIS file (a run cut off halfway)
RECORD = ".sound-lined-up.json"   # transcript/: what moved (for her page's older cuts) and what could not be lined up


def _note(step, message):
    try:
        from fallbacks import note
    except Exception:
        return
    note(step, message)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write(path, data):
    """Whole or not at all: a reader never sees half a transcript or half a cut."""
    tmp = f"{path}.av-sync.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    try:
        swap_in(tmp, path)
    except OSError:
        _drop(tmp)
        raise


def _sha10(path):
    """The id the visual editor gives a transcript (visual_editor.load: sha1 of the file, 10 characters)."""
    with open(path, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:10]


def _keep_previous(job_dir, path, kind):
    """transcript/history/<kind>.<UTC time>.json: the name word-timings.sh and stitch-cut.sh give the copy they keep."""
    hist = os.path.join(job_dir, "transcript", "history")
    try:
        os.makedirs(hist, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        prev = os.path.join(hist, f"{kind}.{stamp}.json")
        if os.path.exists(prev):                      # a same-second re-run keeps both
            prev = os.path.join(hist, f"{kind}.{stamp}.{os.getpid()}.json")
        shutil.copy2(path, prev)
    except OSError:
        return None
    return prev


def scratch_dir(job_dir):
    """The scratch folder the stitch reads its plan from (stitch-cut.sh's scratch_root asks Python the same thing)."""
    return os.path.join(tempfile.gettempdir(), "reels-editing-engine", os.path.basename(os.path.abspath(job_dir)))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _later(value, lead):
    return round(float(value) + lead, 4)


def shift_words(clip, lead):
    """Every timed word of one words.json clip, `lead` seconds later: its words, the words a quiet clip set aside
    ("heard_in_noise"), and the [start, end] a re-stamp kept as "was". Its "duration" is the file's own and stays."""
    moved = 0
    for value in clip.values():
        if not isinstance(value, list):
            continue
        for w in value:
            if not isinstance(w, dict) or not _num(w.get("start")):
                continue
            w["start"] = _later(w["start"], lead)
            if _num(w.get("end")):
                w["end"] = _later(w["end"], lead)
            was = w.get("was")
            if isinstance(was, list) and was and all(_num(x) for x in was):
                w["was"] = [_later(x, lead) for x in was]
            moved += 1
    return moved


def shift_cut(plan, leads, her_edges=False, lengths=None):
    """Each piece of `plan` (a cuts.json) from a clip in `leads` {name: seconds}, onto the file's clock. A piece the
    snap moved goes back to the edges it was planned on, later by the lead (the snap read the file's sound around a
    stamp on the other clock, so where it put those edges means nothing); one whose edges are hers (keep_edges, or
    her_edges for a your-turn cut) moves as it is. `lengths` {name: seconds} keeps an end inside its clip. The plan
    carries CUT_MARK afterwards, so this file is never moved twice. Returns how many pieces moved."""
    done = plan.setdefault(CUT_MARK, {})
    leads = {n: l for n, l in leads.items() if n not in done}
    moved = 0
    for seg in plan.get("segments") or []:
        if not isinstance(seg, dict) or not (_num(seg.get("start")) and _num(seg.get("end"))):
            continue
        name = os.path.basename(str(seg.get("clip", "")))
        lead = leads.get(name)
        if not lead:
            continue
        was = seg.get("_snapped_from") if isinstance(seg.get("_snapped_from"), dict) else None
        ref = seg.get("_refine") if isinstance(seg.get("_refine"), dict) else None      # the older name for it
        planned = None
        if was and _num(was.get("start")) and _num(was.get("end")):
            planned = (was["start"], was["end"])
        elif ref and _num(ref.get("orig_start")) and _num(ref.get("orig_end")):
            planned = (ref["orig_start"], ref["orig_end"])
        if her_edges or seg.get("keep_edges") or planned is None:
            planned = (seg["start"], seg["end"])
        seg["start"], seg["end"] = _later(planned[0], lead), _later(planned[1], lead)
        if was:
            seg["_snapped_from"] = {k: (_later(v, lead) if _num(v) else v) for k, v in was.items()}
        if ref:
            seg["_refine"] = {k: (_later(v, lead) if k in ("orig_start", "orig_end") and _num(v) else v)
                              for k, v in ref.items()}
        top = (lengths or {}).get(name)
        if top and float(seg["end"]) > top:
            seg["end"] = round(top, 4)
        moved += 1
    done.update({n: round(l, 4) for n, l in leads.items()})
    return moved


def _is_silent(clip):
    try:
        import quiet_clips
        return quiet_clips.is_silent(clip)
    except Exception:
        return bool(clip.get("silent"))


def _sig(path):
    try:
        return [os.path.getsize(path), int(os.path.getmtime(path))]
    except OSError:
        return None


def catch_up(job_dir, say=print, quiet=False):
    """Line up every late clip of a job that was already heard, and move its words and its cut with it (the module
    docstring says what moves and what stays). Returns {clip name: seconds moved}; {} when there was nothing to do."""
    job_dir = os.path.abspath(job_dir)
    tdir = os.path.join(job_dir, "transcript")
    wp = os.path.join(tdir, "words.json")
    data = _read(wp)
    if not isinstance(data, dict) or not isinstance(data.get("clips"), list):
        return {}
    rec_path = os.path.join(tdir, RECORD)
    rec = _read(rec_path)
    rec = rec if isinstance(rec, dict) else {}
    pending, could_not = rec.setdefault("pending", {}), rec.setdefault("could_not", {})
    late = {c["name"]: c for c in late_clips(media_dir(job_dir))}
    clips = {os.path.basename(str(c.get("clip", ""))): c for c in data["clips"] if isinstance(c, dict)}
    todo, tidy = {}, False
    for name, clip in clips.items():
        if LINED_UP in clip:                        # moved already; only a record a cut-off run left needs tidying
            tidy = pending.pop(name, None) is not None or tidy
            continue
        if name in late:
            c = late[name]
            if could_not.get(name) == _sig(c["path"]):
                continue                            # said once already; tried again only when the file changes
            # written down first, so a run cut off right after the swap still moves the words next time
            pending[name] = round(float(pending.get(name, c["lead"])), 4)
            _write(rec_path, rec)
            try:
                line_up(c["path"])
            except (RuntimeError, OSError) as e:
                pending.pop(name, None)
                could_not[name] = _sig(c["path"])
                _write(rec_path, rec)
                # The clip still cuts as it did, early by its lead: said once, and left for /report-a-problem.
                say(f"[av-sync] ⚠ {e}. Its words were heard {c['lead']:.2f} s ahead of the picture, so each cut on "
                    f"that clip may still land that much early.")
                _note("av-sync", f"{name}: already heard with its sound {c['lead']:.3f} s after the picture, and it "
                                 f"could not be lined up ({e}); cut on it as it is, so each cut may land early by that much")
                continue
            could_not.pop(name, None)
            todo[name] = pending[name]
        elif name in pending:                       # lined up by a run cut off before it moved the words
            todo[name] = float(pending[name])
    if not todo:
        if tidy:
            _write(rec_path, rec)
        if not quiet and not late:
            say("[av-sync] every clip's sound starts with its picture; nothing to line up")
        return {}

    old_id = _sha10(wp)
    # The cut follows her words in a clip she talks in. A clip with no talking is cut in seconds of the file
    # (product/quiet_clips.py's beats), the same clock before and after, so its cut stays where it is.
    cut_leads = {n: l for n, l in todo.items() if not _is_silent(clips[n])}
    lengths = {n: float(clips[n]["duration"]) for n in todo if _num(clips[n].get("duration")) and clips[n]["duration"] > 0}
    her_edges = os.path.exists(os.path.join(tdir, ".your-turn-cut"))
    # The cuts first and the words last: the words' mark is what says "done", so a run cut off in between finishes
    # the rest next time, and each cut file's own mark (CUT_MARK) keeps it from moving twice.
    for cp, keep in ((os.path.join(tdir, "cuts.json"), True), (os.path.join(scratch_dir(job_dir), "cuts.json"), False)):
        plan = _read(cp)
        if not isinstance(plan, dict) or not cut_leads:
            continue
        if keep and not set(cut_leads) <= set(plan.get(CUT_MARK) or {}):
            prev = _keep_previous(job_dir, cp, "cuts")
            if prev:
                say(f"[av-sync] previous cut plan kept at {prev}")
        shift_cut(plan, cut_leads, her_edges=her_edges, lengths=lengths)
        _write(cp, plan)
    prev = _keep_previous(job_dir, wp, "words")
    if prev:
        say(f"[av-sync] previous transcript kept at {prev}")
    for name, lead in todo.items():
        shift_words(clips[name], lead)
        clips[name][LINED_UP] = round(lead, 4)
    _write(wp, data)
    scratch_words = os.path.join(scratch_dir(job_dir), "words.json")
    if os.path.isfile(scratch_words):                # the scratch copy word-timings.sh hands the stitch
        try:
            shutil.copyfile(wp, scratch_words)
        except OSError:
            pass
    rec.setdefault("ids", {})[old_id] = {"to": _sha10(wp), "leads": {n: round(l, 4) for n, l in cut_leads.items()},
                                         "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    for name in todo:
        pending.pop(name, None)
    _write(rec_path, rec)
    for name, lead in todo.items():
        what = "its words and the cut moved with it" if name in cut_leads else "its words moved with it"
        say(f"[av-sync] ✓ {name}: its sound started {lead * 1000:.0f} ms after the picture; lined up, and {what}, so "
            f"every cut lands on the words (the picture is untouched)")
        _note("av-sync", f"{name}: already heard with its sound {lead:.3f} s after the picture; lined up, and its "
                         f"stored word and cut times moved {lead:.3f} s later (the copies before are in transcript/history/)")
    return todo


def moved_since(job_dir, page_id, now_id):
    """For a cut her visual editor page sent: {clip name: seconds} to move its times by, when the page was made from
    a transcript catch_up has moved since (its id, then each move after it, ending at today's `now_id`). {} when the
    page is from today's transcript, None when it is from neither (the editor refuses it, as before)."""
    pid = str(page_id or "")[:6]
    if not pid or str(now_id).startswith(pid):
        return {}
    rec = _read(os.path.join(os.path.abspath(job_dir), "transcript", RECORD))
    ids = rec.get("ids") if isinstance(rec, dict) else None
    if not isinstance(ids, dict):
        return None
    key = next((k for k in ids if k.startswith(pid)), None)
    leads, seen = {}, set()
    while key and key not in seen:
        seen.add(key)
        hop = ids.get(key) if isinstance(ids.get(key), dict) else {}
        for name, lead in (hop.get("leads") or {}).items():
            leads[name] = round(leads.get(name, 0.0) + float(lead), 4)
        to = str(hop.get("to", ""))
        if to and str(now_id).startswith(to[:6]):
            return leads
        key = to if to in ids else None
    return None


def main(argv):
    for stream in (sys.stdout, sys.stderr):   # ✓ needs UTF-8; a cp1252 Windows console cannot print it
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("usage: av_sync.py <job> [--apply [--relisten]] [--quiet]   (without --apply: say which clips start "
                 "their sound late)")
    job = _job_dir(args[0])
    quiet = "--quiet" in argv
    if "--apply" in argv and heard(job) and "--relisten" not in argv:
        catch_up(job, quiet=quiet)
        return 0
    late = late_clips(media_dir(job))
    if not late:
        if not quiet:
            print("[av-sync] every clip's sound starts with its picture; nothing to line up")
        return 0
    names = ", ".join(f"{c['name']} ({c['lead'] * 1000:.0f} ms)" for c in late)
    if "--apply" not in argv:
        then = ", and moves their words and cut with them" if heard(job) else " before the transcript"
        print(f"[av-sync] sound starts after the picture in: {names}. `--apply` lines them up{then}.")
        return 0
    for c in late:
        try:
            line_up(c["path"])
        except (RuntimeError, OSError) as e:
            # The clip still cuts, only early by its lead: say it, and leave it for /report-a-problem.
            print(f"[av-sync] ⚠ {e}", file=sys.stderr)
            _note("av-sync", f"{c['name']}: sound starts {c['lead']:.3f} s after the picture and could not be lined "
                             f"up ({e}); cut on it as it is, so each cut may land early by that much")
            continue
        print(f"[av-sync] ✓ {c['name']}: its sound started {c['lead'] * 1000:.0f} ms after the picture; lined up "
              f"(the picture is untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
