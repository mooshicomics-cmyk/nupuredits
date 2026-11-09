#!/usr/bin/env python3
"""The stitch's dead-air pass (close-pauses.py): no kept piece of a cut holds a long silence, however the cut
was made, and her own edges are never touched.

Builds a 20 s clip of "voice" (a tone) and true silence, a transcript for it and a cut plan that keeps the whole
thing as ONE piece (as a cut written by hand, or a transcript that stretched a word over a pause, would), then
checks what the pass makes of it:
  - a 4.5 s silence before the first line (her reading her notes) comes off the head
  - silences between lines are closed, each leaving a short natural beat
  - a silence the aligner hid inside one long word stamp is closed too
  - a silence holding a real (soft) word, or sitting beside a spoken amount, stays
  - pieces marked keep_edges (her editor edges) or no_trim (words she brought back) are left exactly as planned
  - every line it keeps is still in the plan, with its words

Run: python3 product/tests/test_close_pauses.py
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "close-pauses.py")
FAILS = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {detail}"))
    if not ok:
        FAILS.append(name)


# voice at these stretches, silence everywhere else (seconds in the clip)
VOICE = [(4.5, 5.4), (7.0, 7.4), (7.6, 8.0), (10.5, 11.2), (13.5, 14.0), (14.3, 14.6), (16.0, 17.0)]
WORDS = [
    {"word": "That's", "start": 0.3, "end": 4.9},     # stretched back over the 4.5 s of notes (the Loom case)
    {"word": "too", "start": 4.95, "end": 5.1}, {"word": "much.", "start": 5.1, "end": 5.4},
    {"word": "Hmm.", "start": 7.0, "end": 7.4}, {"word": "Maybe.", "start": 7.6, "end": 8.0},
    {"word": "Oh,", "start": 8.0, "end": 10.9},       # stamp stretched across the 8.0 -> 10.5 silence
    {"word": "okay.", "start": 10.9, "end": 11.2},
    {"word": "$300", "start": 13.5, "end": 14.0},     # an amount: the pause after it stays
    {"word": "a", "start": 14.3, "end": 14.6},
    {"word": "month.", "start": 16.0, "end": 17.0},
]


def make_clip(path):
    expr = "+".join(f"between(t,{a},{b})" for a, b in VOICE)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=20",
                    "-af", f"volume='if({expr},1,0)':eval=frame", "-c:a", "pcm_s16le", path], check=True)


def run(plan, d):
    cuts, out = os.path.join(d, "cuts.json"), os.path.join(d, "out.json")
    json.dump({"segments": plan}, open(cuts, "w", encoding="utf-8"))
    r = subprocess.run([sys.executable, SCRIPT, d, os.path.join(d, "words.json"), cuts, out], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr)
    return json.load(open(out, encoding="utf-8"))["segments"], r.stderr


def main():
    if not shutil.which("ffmpeg"):
        print("test_close_pauses: no ffmpeg on this computer, skipped"); return 0
    d = tempfile.mkdtemp(prefix="close-pauses-")
    try:
        make_clip(os.path.join(d, "take.wav"))
        json.dump({"clips": [{"clip": "take.wav", "words": WORDS}]}, open(os.path.join(d, "words.json"), "w", encoding="utf-8"))
        whole = {"clip": "take.wav", "start": 0.0, "end": 17.1, "transcript": " ".join(w["word"] for w in WORDS)}
        segs, log = run([whole], d)
        span = [(s["start"], s["end"]) for s in segs]
        total = sum(e - s for s, e in span)
        check("the notes before her first line come off the head", segs[0]["start"] > 4.2 and segs[0]["start"] < 4.5, span)
        check("a long pause between lines is closed", not any(s < 6.5 < e for s, e in span) and not any(s < 9.5 < e for s, e in span), span)
        check("a pause hidden inside a stretched word stamp is closed", not any(s < 9.0 < e for s, e in span), span)
        check("each closed pause keeps a short beat after her voice", any(abs(e - 5.52) < 0.03 for _, e in span), span)
        check("the pause beside a spoken amount stays", any(s <= 14.6 and e >= 16.0 for s, e in span), span)
        check("every word she says is still in the plan", all(any(s <= (w["start"] + w["end"]) / 2 <= e for s, e in span)
              or w["word"] in ("That's", "Oh,") for w in WORDS), span)
        check("the pieces carry their own words", segs[0]["transcript"].startswith("That's too much"), segs[0])
        check("about 9 s of dead air out", 7.0 < 17.1 - total < 11.0, round(17.1 - total, 2))
        check("it says what it took out", "dead air out" in log and "beside the amount" in log, log)
        # her edges and her restored words are hers
        pinned = dict(whole, keep_edges=True)
        segs, _ = run([pinned], d)
        check("keep_edges: her piece stays exactly as planned", segs == [pinned], segs)
        back = dict(whole, no_trim=True)
        segs, _ = run([back], d)
        check("no_trim: words she brought back stay exactly as planned", segs == [back], segs)
        # a soft real word inside a quiet stretch keeps that stretch
        soft = WORDS + [{"word": "hmm", "start": 2.0, "end": 2.3}]
        json.dump({"clips": [{"clip": "take.wav", "words": soft}]}, open(os.path.join(d, "words.json"), "w", encoding="utf-8"))
        segs, log = run([whole], d)
        check("a silence holding a real word stays", segs[0]["start"] == 0.0 and '"hmm" is said in it' in log, (segs[0], log))
        # a tight cut is left alone
        json.dump({"clips": [{"clip": "take.wav", "words": WORDS}]}, open(os.path.join(d, "words.json"), "w", encoding="utf-8"))
        tight = [{"clip": "take.wav", "start": 4.46, "end": 5.46, "transcript": "too much."}]
        segs, log = run(tight, d)
        check("a cut with no dead air is unchanged", segs == tight and "no dead air" in log, (segs, log))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"test_close_pauses: {'all checks passed' if not FAILS else f'{len(FAILS)} FAILED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
