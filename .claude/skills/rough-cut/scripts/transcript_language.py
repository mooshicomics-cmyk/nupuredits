#!/usr/bin/env python3
"""transcript_language.py — is this transcript English, and should an English-only check run on it?

WHY THIS EXISTS. A tester filmed 43 seconds of Spanish. The transcriber was hardcoded to English, so
Whisper translated the first ~20 seconds instead of transcribing it, and the captions were built from
that translation. That root cause is fixed now (word-timings.sh detects the language). But two English-only
QA passes ALSO fired on her reel and made the damage look like her fault:

  1. verify-cut.py re-listened in English and printed her real Spanish beside an English rendering of
     it, labelled as what her cut plays — 17 times.
  2. flag-words.py checked her words against the English system dictionary and flagged 29
     "suspects", 28 of which were ordinary Spanish words.

Neither was the cause, and both stay wrong even with transcription fixed, because a checker that only
speaks English cannot judge a reel that is not in English. This module is how a checker asks "am I
qualified to judge these words?" before it opens its mouth.

WHY NOT JUST ASK WHISPER. Because this has to work on an already-written transcript, after the audio is
gone, in scripts that never load a model. It also has to work on a transcript written by an older
version of the engine, before any language was recorded. A text-level read costs nothing, downloads
nothing, and works identically on both transcription paths.

DELIBERATELY CONSERVATIVE. The default answer is "english", and it takes real evidence to move off it.
An English reel must behave exactly as it does today — that is the overwhelming majority of jobs, and
a false "this isn't English" would silently disable QA passes that are working correctly. A false
"this is English" only costs what we already have. So the thresholds below are set to be sure, not
sensitive: a stray "café" or "piñata" in an English reel will not trip it.

OTHER ALPHABETS. The accent and function-word signals only exist in languages written in the Latin
alphabet, so a Russian, Greek, Hindi, Arabic, Hebrew, Chinese or Japanese transcript used to score zero
on both and come back "english" (or "unknown", which callers also treat as English). The alphabet itself
is the evidence there: when a real share of the letters sits outside the Latin alphabet, the transcript
is not English, whatever the word-level signals say. English text never gets near that share; a quoted
name in another script is a handful of letters among thousands.

Usage:
    from transcript_language import classify
    verdict = classify(["Today", "I", "found", ...])
    if verdict["english_only_checks_ok"]: ...run the English-only pass...
"""
import re
import unicodedata

# Latin letters carrying a diacritic, plus the marks Spanish/Portuguese/French openers use. ASCII-only
# text scores 0 here. This is the strongest cheap signal: English essentially never uses these, and
# every Western European language leans on them constantly.
_ACCENTED = re.compile(r"[À-ÖØ-öø-ÿĀ-ſ]")
_INVERTED = re.compile(r"[¿¡]")

# Function words that are overwhelmingly non-English and extremely common in the languages they belong
# to. Presence of several of these in quantity is near-proof. Kept deliberately short and unambiguous:
# every entry here would be a strange thing to say in an English sentence.
_NON_EN_STOPWORDS = {
    # es
    "que", "para", "porque", "pero", "como", "cuando", "donde", "muy", "todo", "todos", "esto",
    "esta", "este", "eso", "ese", "mi", "tu", "su", "nos", "les", "del", "los", "una",
    "unos", "unas", "por", "más", "también", "ya", "aquí", "así", "yo", "ella",
    # pt
    "não", "você", "está", "mais", "muito", "isso", "aqui", "então",
    # fr
    "je", "vous", "nous", "pas", "mais", "pour", "avec", "dans", "cette", "tout", "plus",
    # it / de
    "sono", "questo", "perché", "molto", "anche",
    "nicht", "auch", "aber", "sehr", "dass", "eine", "einen", "ich", "sie", "wir",
    # ht (Haitian Creole). Written with few accents, so its function words carry the signal; without them a
    # Kreyòl hook ("Sa ou pa konnen sou lajan") read as English. "gen" (Gen Z) and "nan" (a grandmother) left out.
    "mwen", "nou", "pou", "yon", "sou", "paske", "anpil", "konnen", "moun", "bagay", "kounye", "kounya",
    "avèk", "kijan", "kòman", "poukisa", "sèlman", "toujou", "ankò", "menm", "epi", "vle", "konsa", "tankou",
    "chak", "pral", "lòt", "kote", "ou", "li", "ki", "ak",
}

# A word this short is noise: "a", "I", "to" carry no language signal and Spanish "y"/"e" collide with
# English initials. Matches flag-words.py's own len < 3 floor.
_MIN_LEN = 3

# Thresholds. Reaching EITHER of these marks the transcript as not-safely-English.
# Accents ALONE are weak evidence and this was measured, not guessed: an otherwise-English script
# saying "cafe\u0301, jalapen\u0303o, pin\u0303ata" scored 5% accented and would have been marked mixed,
# silently disabling QA on a perfectly English reel. Borrowed nouns carry diacritics; borrowed GRAMMAR
# does not. So accents must be overwhelming to trip on their own, while function words — which you
# cannot speak a sentence of Spanish without — trip at a much lower bar. Measured on the real tester
# transcript: Spanish half 12.8% accented / 29.8% function words, her bilingual reel 6.1% / 14.3%,
# English-with-loanwords 5.1% / 0%.
_ACCENT_RATIO_TRIP = 0.10       # no English text reaches this; loanword-sprinkled English sits near 5%
_STOPWORD_RATIO_TRIP = 0.06     # 6% non-English function words means sentences, not borrowed nouns
# Above this, it is not merely "contains another language" but "is substantially another language".
_MIXED_FLOOR = 0.18

# Letters outside the Latin alphabet. Counted per LETTER, not per word, and before the short-word floor
# above: Chinese and Japanese come back one character per word, so a word-based count sees nothing at all.
_OTHER_ALPHABET_MIN_LETTERS = 20   # fewer letters than this cannot say what a transcript is
_OTHER_ALPHABET_TRIP = 0.10        # a tenth of the letters in another alphabet is language, not a quoted name
_OTHER_ALPHABET_MOSTLY = 0.5       # more than half: substantially another language, not a mix


def other_alphabet_letters(text):
    """(letters, letters outside the Latin alphabet) in a string. Accented Latin (é, ñ, ß) counts as
    Latin; Cyrillic, Greek, Devanagari, Arabic, Hebrew, CJK, Hangul and every other script do not."""
    letters = other = 0
    for ch in str(text):
        if ch.isalpha():
            letters += 1
            if "LATIN" not in unicodedata.name(ch, "").split():
                other += 1
    return letters, other


# The system's English wordlist, at the one place Unix keeps it: macOS ships it, and on Debian or Ubuntu
# (WSL too) `apt install wamerican` puts it there. Windows has none.
WORDLIST = "/usr/share/dict/words"


def english_wordlist():
    """Every word of the system wordlist, lowercased; empty where there is none. flag-words.py reads it too."""
    try:
        with open(WORDLIST, encoding="utf-8", errors="ignore") as f:
            return {w.strip().lower() for w in f if w.strip()}
    except OSError:
        return set()


def _core(raw):
    return re.sub(r"^\W+|\W+$", "", str(raw), flags=re.UNICODE)


def classify(words, dictionary=None):
    """Read a list of word strings and report whether English-only checks are safe to run.

    Returns a dict:
      verdict                 "english" | "mixed" | "non_english" | "unknown"
      english_only_checks_ok  bool — the one field a caller usually needs
      language_code           "en" when confidently English, else None (never guess a code we did
                              not detect; asserting "es" from a heuristic is the same class of lie
                              as the hardcoded "en" this whole change exists to remove)
      accented_ratio / stopword_ratio / unknown_word_ratio / examples / reason
      non_latin_ratio         only when another alphabet decided it (the Latin measures are then 0.0,
                              not computed: they have nothing to say about those letters)
    """
    letters = other = 0
    other_words = []
    for w in words:
        n, k = other_alphabet_letters(w)
        letters += n
        other += k
        if k and len(other_words) < 12 and str(w) not in other_words:
            other_words.append(str(w))
    if letters >= _OTHER_ALPHABET_MIN_LETTERS and other / letters >= _OTHER_ALPHABET_TRIP:
        share = other / letters
        return {"verdict": "non_english" if share >= _OTHER_ALPHABET_MOSTLY else "mixed",
                "english_only_checks_ok": False, "language_code": None,
                "accented_ratio": 0.0, "stopword_ratio": 0.0, "unknown_word_ratio": 0.0,
                "non_latin_ratio": round(share, 4), "examples": other_words,
                "words_considered": sum(1 for w in words if other_alphabet_letters(w)[0]),
                "reason": (f"{other} of its {letters} letters are outside the Latin alphabet — this "
                           f"transcript is not all English")}

    cores = [c for c in (_core(w) for w in words) if len(c) >= _MIN_LEN]
    total = len(cores)
    if total < 20:
        # Too little text to judge. Say so rather than guessing; callers keep today's behaviour.
        return {"verdict": "unknown", "english_only_checks_ok": True, "language_code": None,
                "accented_ratio": 0.0, "stopword_ratio": 0.0, "unknown_word_ratio": 0.0,
                "examples": [], "words_considered": total,
                "reason": f"only {total} scorable words — not enough to judge"}

    accented, stop_hits, examples = 0, 0, []
    for c in cores:
        low = c.lower()
        is_acc = bool(_ACCENTED.search(c) or _INVERTED.search(c))
        is_stop = low in _NON_EN_STOPWORDS
        if is_acc:
            accented += 1
        if is_stop:
            stop_hits += 1
        if (is_acc or is_stop) and len(examples) < 12 and c not in examples:
            examples.append(c)

    accent_ratio = accented / total
    stop_ratio = stop_hits / total

    d = english_wordlist() if dictionary is None else dictionary
    if d:
        unknown = sum(1 for c in cores if c.lower() not in d)
        unknown_ratio = unknown / total
    else:
        unknown_ratio = 0.0

    tripped = accent_ratio >= _ACCENT_RATIO_TRIP or stop_ratio >= _STOPWORD_RATIO_TRIP
    if not tripped:
        return {"verdict": "english", "english_only_checks_ok": True, "language_code": "en",
                "accented_ratio": round(accent_ratio, 4), "stopword_ratio": round(stop_ratio, 4),
                "unknown_word_ratio": round(unknown_ratio, 4), "examples": examples,
                "words_considered": total, "reason": "reads as English"}

    strength = max(accent_ratio, stop_ratio)
    verdict = "non_english" if strength >= _MIXED_FLOOR else "mixed"
    return {"verdict": verdict, "english_only_checks_ok": False, "language_code": None,
            "accented_ratio": round(accent_ratio, 4), "stopword_ratio": round(stop_ratio, 4),
            "unknown_word_ratio": round(unknown_ratio, 4), "examples": examples,
            "words_considered": total,
            "reason": (f"{accented} accented and {stop_hits} non-English function words out of "
                       f"{total} — this transcript is not all English")}


def carries_a_mark(texts):
    """Does any of these strings show a non-English signal at all: an accent, an inverted mark, letters from
    another alphabet, or a non-English function word? A Russian or Hindi card has no accents and no Spanish
    function words to find, so the alphabet counts too."""
    for text in texts:
        text = str(text)
        if _ACCENTED.search(text) or _INVERTED.search(text) or other_alphabet_letters(text)[1]:
            return True
        for word in text.lower().replace(",", " ").replace(".", " ").split():
            if word in _NON_EN_STOPWORDS:
                return True
    return False


def copy_reads_as_english(texts):
    """Does this ON-SCREEN copy (hooks, cards, labels) read as English? Only meaningful once the reel itself has
    been judged not English. Copy is short by nature, so classify() usually cannot judge it ("unknown"); then the
    narrower question is asked: does any of it carry a mark of another language? Several cards with not one
    accent, inverted mark or non-English function word were near-certainly written in English."""
    texts = [str(t).strip() for t in texts if str(t or "").strip()]
    if not texts:
        return False
    reading = classify(" ".join(texts).split())
    return reading["verdict"] == "english" or (reading["verdict"] == "unknown" and not carries_a_mark(texts))


def classify_transcript_file(path):
    """Convenience: read either transcript shape and classify it.

    words.json (raw)      -> {"clips":[{"words":[{"word": ...}]}]}  (older jobs: "w")
    <job>.transcript.json -> {"words":[{"text": ...}]}
    """
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data.get("clips"), list):
        words = [w.get("word", w.get("w", "")) for c in data["clips"] for w in c.get("words", [])]
    else:
        words = [w.get("text", "") for w in data.get("words", [])]
    return classify(words)


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: transcript_language.py <words.json | *.transcript.json>")
    print(json.dumps(classify_transcript_file(sys.argv[1]), indent=2, ensure_ascii=False))
