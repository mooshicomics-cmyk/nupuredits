#!/usr/bin/env python3
"""test_unpunctuated_transcript.py — a transcript with no punctuation still splits into sentences.

The Intel route's transcriber can return bare words with no sentence punctuation at all. Every sentence split
in the engine looked only for ".", "!" or "?", so such a transcript was one long sentence: the first-reel
script's spoken cues collapsed to a single cue (the reader takes one effect per sentence), and a takeover,
which runs "to the end of its sentence", would have held to the end of the reel.

Now a transcript with no sentence punctuation anywhere splits at the speaker's pauses, measured against her
own rhythm (beat-lines.py, the one home of sentence splitting). A punctuated transcript splits exactly as before.

Run:  python3 product/tests/test_unpunctuated_transcript.py
"""
import importlib.util
import os
import re
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


seg = load("beat_lines", os.path.join(ROOT, ".claude", "skills", "graphics-plan", "scripts", "beat-lines.py"))
sc = load("spoken_cues", os.path.join(ROOT, "product", "spoken_cues.py"))

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def script_lines():
    with open(os.path.join(ROOT, "product", "FIRST-REEL-SCRIPT.md"), encoding="utf-8") as fh:
        return re.findall(r"^\d+\. (.+)$", fh.read(), re.M)


def words_for(lines, bare=False, word_gap=0.05, line_gap=0.35):
    """Timed words the way a transcriber writes them. bare=True strips every punctuation mark and the
    capitals, as the Intel transcriber's output came back."""
    t, out = 0.2, []
    for line in lines:
        for w in line.split():
            if bare:
                w = re.sub(r"[^\w'-]", "", w).lower()
            out.append({"text": w, "start": round(t, 3), "end": round(t + 0.28, 3)})
            t += 0.28 + word_gap
        t += line_gap - word_gap
    return out


def main():
    lines = script_lines()
    punct = words_for(lines)
    bare = words_for(lines, bare=True)
    check("the bare transcript really has no sentence punctuation (the test is meaningful)",
          not seg.is_punctuated(bare))
    check("the punctuated one is recognised as punctuated", seg.is_punctuated(punct))

    runs = list(seg.sentences_from(bare))
    check("a bare transcript splits into one sentence per spoken line", len(runs) == len(lines),
          [" ".join(w["text"] for w in r) for r in runs])
    stops = sum(1 for w in punct if seg.ends_a_sentence(w))
    check("a punctuated transcript splits exactly as before (once per full stop, pauses ignored)",
          len(list(seg.sentences_from(punct))) == stops, (len(list(seg.sentences_from(punct))), stops))

    want = [c[0] for c in sc.detect(punct)]
    got = [c[0] for c in sc.detect(bare)]
    check("every spoken cue is heard on a bare transcript, the same as on a punctuated one", got == want,
          (got, want))
    check("that is all seven effects the script names", len(got) == 7, got)

    # A pause is relative to her own rhythm: a slow speaker's gaps between words are not sentence breaks.
    slow = words_for(lines, bare=True, word_gap=0.12, line_gap=0.6)
    check("a slower speaker still splits per line, not per word",
          len(list(seg.sentences_from(slow))) == len(lines), len(list(seg.sentences_from(slow))))
    # A cut that left no pauses at all is no worse than before: one run, never a crash.
    flat = words_for(lines, bare=True, word_gap=0.0, line_gap=0.0)
    check("a transcript with no pauses at all stays one run instead of failing",
          len(list(seg.sentences_from(flat))) == 1)
    check("the threshold is bounded", seg.PAUSE_MIN <= seg.pause_threshold(slow) <= seg.PAUSE_MAX)

    # The beat sheet stays within its length rules on a bare transcript too.
    beats = seg.build_beats(bare)
    check("beats on a bare transcript follow the spoken lines", len(beats) == len(lines), len(beats))

    # build-reel-type.py extends a takeover to the end of its sentence; on a bare transcript that has to stop
    # at the next pause, which it reads from the same threshold.
    src = open(os.path.join(ROOT, "product", "build-reel-type.py"), encoding="utf-8").read()
    check("the takeover sentence-end uses the shared pause rule on an unpunctuated transcript",
          "pause_threshold(" in src and "_sentence_goes_on" in src)

    if fails:
        print(f"test_unpunctuated_transcript: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_unpunctuated_transcript: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
