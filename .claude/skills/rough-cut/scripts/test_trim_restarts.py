#!/usr/bin/env python3
"""test_trim_restarts.py — regression guard for the low-confidence-segment detector (Bug #2).

WhisperX forced-alignment word scores collapse across a repeated phrase (probs seen as low as 0.0) — which
is exactly where a restart boundary lands wrong. low_confidence_segments() flags any KEPT segment whose
average word probability is below the threshold so the mis-fire is caught before a render. This proves it
fires on a low-confidence (repeat-region) segment and stays quiet on clean speech and on a genuinely empty
segment. Pure — no audio, no torch. Run: python3 test_trim_restarts.py
"""
import os, importlib.util
import sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

_spec = importlib.util.spec_from_file_location(
    "trim_restarts", os.path.join(os.path.dirname(os.path.abspath(__file__)), "trim-restarts.py"))
tr = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(tr)   # torch import is soft -> loads bare

lc = tr.low_confidence_segments


def run():
    # words: [(start, end, prob)] — a clean opener, then a collapsed-timestamp repeat region (low probs)
    clean = [(0.0, 0.4, 0.95), (0.4, 0.8, 0.92), (0.8, 1.2, 0.97)]
    repeat = [(2.0, 2.3, 0.10), (2.3, 2.6, 0.05), (2.6, 2.9, 0.32), (2.9, 3.2, 0.20)]
    wp = clean + repeat

    # 1. a segment over the clean opener -> NOT flagged
    assert lc([{"start": 0.0, "end": 1.2}], wp) == [], "clean speech must not flag"

    # 2. a segment over the low-confidence repeat region -> flagged, with the right averaged prob
    hit = lc([{"start": 2.0, "end": 3.2}], wp)
    assert len(hit) == 1 and hit[0][0] == 2.0 and hit[0][1] == 3.2, f"repeat region must flag once, got {hit}"
    assert hit[0][2] < 0.5, f"reported avg prob must be sub-threshold, got {hit[0][2]}"

    # 3. mixed batch: only the low-confidence one comes back
    both = lc([{"start": 0.0, "end": 1.2}, {"start": 2.0, "end": 3.2}], wp)
    assert [ (a, b) for a, b, _ in both ] == [(2.0, 3.2)], f"only the repeat segment flags, got {both}"

    # 4. a segment with NO words in range -> treated as confident (avg 1.0), not a false alarm
    assert lc([{"start": 10.0, "end": 11.0}], wp) == [], "a wordless segment must not flag"

    # 5. threshold is the boundary: avg exactly at/above thr does not fire
    edge = [(0.0, 0.4, 0.5), (0.4, 0.8, 0.5)]
    assert lc([{"start": 0.0, "end": 0.8}], edge) == [], "avg == thr must not fire (strict <)"

    print("✓ trim-restarts: low-confidence guard flags repeat/restart regions, ignores clean + empty segments")

    # --- drop_cut_slivers: a creator's own short cut must SURVIVE; only cut debris goes ---------------
    # Reproduces a tester's report: she cut ONE stumbled word out of continuous speech, which leaves a
    # very short segment. The next splice printed "0 restart(s) cut" and still merged her edit away,
    # because the old filter dropped every segment of 0.12s or less whether or not a cut produced it.
    dcs = tr.drop_cut_slivers

    # 6. no restarts found: nothing is tagged, so NOTHING may be dropped, however short
    authored = [{"start": 0.0, "end": 2.40}, {"start": 2.52, "end": 2.60}, {"start": 2.71, "end": 5.0}]
    assert dcs(authored) == authored, f"an untouched short segment must survive, got {dcs(authored)}"

    # 7. a sliver a cut produced (_retrim) under the minimum IS debris and goes
    debris = [{"start": 0.0, "end": 2.0}, {"start": 2.0, "end": 2.05, "_retrim": True}]
    assert dcs(debris) == [{"start": 0.0, "end": 2.0}], f"cut debris must be dropped, got {dcs(debris)}"

    # 8. a cut-produced piece that is long enough is real content and stays
    kept = [{"start": 3.0, "end": 4.0, "_retrim": True}]
    assert dcs(kept) == kept, "a long cut-produced piece must be kept"

    print("✓ trim-restarts: a creator's short word-level cut survives a splice; only cut debris is removed")

    # --- words_agree: two lines that SOUND alike are not a restart unless they open on the same words ---
    # Reproduces a French test clip ("Tu n'as pas besoin de plus de temps. / Tu as besoin d'un système.",
    # sim 0.79) and the English lines an earlier reel lost the same way.
    wa = tr.words_agree
    # 9. real restarts: take-2 opens with take-1's words (one inserted word allowed)
    assert wa("how much to", "how much to charge"), "a clean restart must agree"
    assert wa("I'm a mom who", "I'm a mom working from home"), "a restart that diverges late must agree"
    assert wa("Personne ne te dit ça.", "Personne ne te dit ça quand tu deviens maman."), "French restart"
    assert wa("so how much to", "how much to charge"), "a leading filler on take-1 must not block it"
    # 10. different lines that open alike: must NOT agree
    assert not wa("? Tu n'as pas besoin de plus de temps.", "Tu as besoin d'un système."), \
        "you-don't-need / you-need is two lines"
    assert not wa("maybe I can earn online", "Maybe I could do this"), "a rephrase is not a restart"
    # 11. nothing to compare -> defer to the sound (never blocks a collapsed restart)
    assert wa("how much to", ""), "an empty take-2 must defer to the sound"
    assert wa("?", "charge"), "a punctuation-only take-1 must defer to the sound"
    print("✓ trim-restarts: a restart needs the same opening words; look-alike lines are kept")

    # --- take2_heard: the text only overrules the sound when the transcript heard take-2 begin ---
    th = tr.take2_heard
    words = [("temps.", 9.654, 10.094), ("Tu", 10.134, 10.274), ("as", 10.314, 10.414)]
    # 12. a word starts right at the resume point -> heard
    assert th(words, 10.10), "a word starting at the resume point counts as heard"
    # 13. collapsed restart: the repeat is folded into an over-long word, the next word starts late
    collapsed = [("how", 0.0, 0.2), ("much", 0.2, 0.4), ("to", 0.4, 1.54), ("charge", 1.6, 2.0)]
    assert not th(collapsed, 0.75), "a collapsed restart was not heard as a fresh start"
    # 14. a punctuation token at the resume point is not a word
    assert not th([("?", 5.0, 5.02)], 5.0), "punctuation alone is not a heard phrase"
    print("✓ trim-restarts: text only overrules the sound where the transcript heard take-2 start")

    # --- folded_repeat: a repeat folded into one over-long word leaves the text blind -> sound decides ---
    fr = tr.folded_repeat
    # 15. "The number— the number that you actually need": 'number' stamped 1.28s (a real reel)
    folded = [("The", 254.23, 254.35), ("number", 254.39, 255.67), ("that", 256.51, 256.93)]
    assert fr(folded, 254.20, 256.45), "an over-long word before the resume point is a folded repeat"
    # 16. the French look-alike lines: no word over 1s, so the words get their say
    fr_words = [("plus", 9.334, 9.494), ("de", 9.534, 9.614), ("temps.", 9.654, 10.094), ("Tu", 10.134, 10.274)]
    assert not fr(fr_words, 8.23, 10.10), "ordinary word lengths are not a folded repeat"
    # 17. a long word AFTER the resume point does not count
    assert not fr([("a", 1.0, 1.2), ("système.", 3.0, 4.4)], 0.9, 2.0), "only words before the resume point count"
    print("✓ trim-restarts: a repeat folded into an over-long word is left to the sound")


if __name__ == "__main__":
    run()
