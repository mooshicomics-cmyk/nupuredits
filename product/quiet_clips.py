#!/usr/bin/env python3
"""quiet_clips.py: a clip she filmed with no talking in it (her kids in the store, a b-roll moment, a vlog bit).

The transcriber always returns SOMETHING, even from a clip with no one talking: store noise once came back as
"Stavros Stavros", and another time as a subtitle credit in Norwegian. Left alone, that phantom text cut the clip
down to the 1 s around it, put words she never said in her captions, and kept the clip out of the visual editor
(a piece of the cut "with no words under it" can't be shown). This module is the one place that decides a clip has
no talking, and what each step does about it:

  the transcript   word-timings.sh runs `mark`: a quiet clip is saved with "silent": true, no words, and what
                   the transcriber thought it heard kept aside as "heard_in_noise" (nothing reads it; it's there
                   so a wrong call can be seen and undone)
  the rough cut    transcript-cut.py keeps a quiet clip whole: there are no lines to choose between
  the editor       visual_editor.words_of shows it as a line of one-second beats (`quiet_beats`), so she can cut
                   seconds from it like words, and every tool on the page (Cover a face, Filter, looks) reaches it

How it decides (`is_silent`), measured on her own reels: real talking runs 0.9 to 2 words a second at a median
alignment score of 0.69 or more; the two noise clips came back at 0.09 and 0.4 words a second, scored 0.44 and
0.23. A clip is quiet only when it is BOTH sparse and unsure, so a real sentence said once in a long clip, or said
softly, is never thrown away. A clip with no words at all is quiet.

    python3 product/quiet_clips.py mark <words.json>    mark quiet clips in a transcript (idempotent)
    python3 product/quiet_clips.py check <job>           which of a reel's clips have no talking
"""
import json, os, statistics, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPARSE = 0.5        # words a second: real talking is at least 0.9
UNSURE = 0.6        # median alignment score: real talking is at least 0.69
BEAT = 1.0          # seconds per beat on the editor's "No talking" line


def is_silent(clip):
    """True when this clip (a words.json "clips" entry) has no talking in it."""
    if clip.get("silent"):
        return True
    words = [w for w in clip.get("words", []) if str(w.get("word", w.get("w", ""))).strip()]
    if not words:
        return True
    dur = float(clip.get("duration") or 0)
    if dur <= 0:
        return False                                  # can't measure how sparse: trust the words
    scores = [float(w["score"]) for w in words if "score" in w]
    if not scores:
        return False                                  # an older transcript without scores: trust the words
    return len(words) / dur < SPARSE and statistics.median(scores) < UNSURE


def mark(path):
    """Mark every quiet clip in a words.json: "silent": true, words set aside. Returns the clips it marked."""
    d = json.load(open(path, encoding="utf-8"))
    marked = []
    for c in d.get("clips", []):
        if c.get("silent") or not is_silent(c):
            continue
        c["silent"] = True
        c["heard_in_noise"] = c.get("words", [])
        c["words"] = []
        marked.append(c.get("clip"))
    if marked:
        tmp = path + ".quiet.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    return marked


def duration(clip):
    """A clip's length: the transcript's own record, else its last heard word."""
    d = float(clip.get("duration") or 0)
    if d > 0:
        return d
    heard = clip.get("words", []) + clip.get("heard_in_noise", [])
    return max((float(w.get("end", w.get("e", 0)) or 0) for w in heard), default=0.0)


def quiet_beats(clip, ci):
    """The editor's words for a quiet clip: one beat per second (the last one short), text left empty (the page
    draws a beat, never a word she didn't say). Same shape as visual_editor.words_of; `q` marks a beat."""
    d, out, s = duration(clip), [], 0.0
    while s < d - 0.05:
        e = d if d - s < BEAT * 1.5 else s + BEAT       # no sliver at the end: the last beat takes what's left
        out.append({"t": "", "c": ci, "s": round(s, 3), "e": round(e, 3), "q": True})
        s = e
    return out


def main(argv):
    if len(argv) == 2 and argv[0] == "mark":
        got = mark(argv[1])
        for name in got:
            print(f"[quiet] no talking in {name}: kept whole, no captions from its background sound")
        return 0
    if len(argv) == 2 and argv[0] == "check":
        p = os.path.join(ROOT, "projects", argv[1], "transcript", "words.json")
        d = json.load(open(p, encoding="utf-8"))
        for c in d.get("clips", []):
            print(f"{c.get('clip')}: {'no talking' if is_silent(c) else 'talking'}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
