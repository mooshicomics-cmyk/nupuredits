#!/usr/bin/env python3
"""check-plan-language.py — refuse a graphics plan whose on-screen copy is in the wrong language.

WHY THIS EXISTS. Captions are built from the transcript, so they follow the speaker on their own.
On-screen copy — hooks, cards, checklists, takeovers, labels — is written fresh by whoever plans the
reel, and their default is English. A real reel shipped with Spanish captions under an English hook
card. The rule against that has been written down, correctly and with the exact file paths, in the
repo CLAUDE.md and in graphics-plan/SKILL.md since. It kept being skipped, because a rule that only
lives in prose depends on somebody remembering it at the moment it matters.

This is that rule with teeth. It reads the language the plan was born with (beat-lines.py stamps
it) and the literal `on_screen` strings, and it fails the plan when the reel is not English and the
copy is.

WHAT IT DELIBERATELY DOES NOT DO. It never guesses a language code, and it never fails an English
reel. classify() needs a real run of words to judge, and on-screen copy is short by nature, so for
short copy this falls back to asking a narrower question: does ANY of the on-screen text carry a
mark of the language being spoken? For a Spanish reel with several cards and not one accent,
inverted mark or Spanish function word anywhere, the answer is near-certainly that it was written in
English. That is a weaker test than classify() and it is scoped to match: it only ever runs when the
transcript has already been judged non-English.

    check-plan-language.py <plan.json>        exit 0 pass · 1 wrong language · 2 cannot check
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "rough-cut", "scripts"))
try:
    from transcript_language import copy_reads_as_english
except Exception as exc:
    print(f"[check-plan-language] cannot load the language classifier: {exc}", file=sys.stderr)
    sys.exit(2)


def on_screen_strings(plan):
    """Only the copy that is actually rendered. `idea` is prose about the graphic and is skipped:
    an English description of a Spanish card is not a defect, and flagging it would be."""
    out = []
    for beat in plan.get("beats", []) or []:
        value = beat.get("on_screen")
        if isinstance(value, str) and value.strip():
            out.append((beat.get("id"), value.strip()))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str) and item.strip():
                    out.append((beat.get("id"), item.strip()))
    return out


def shows_a_graphic(beat):
    """True when the beat puts something on screen besides her: its `element` is anything but "face"."""
    element = beat.get("element")
    if element is not None:
        return element not in ("face", "", False)
    marked = beat.get("graphic")
    return bool(marked) and marked != "plain"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: check-plan-language.py <plan.json>")
    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as fh:
            plan = json.load(fh)
    except Exception as exc:
        print(f"[check-plan-language] cannot read {path}: {exc}", file=sys.stderr)
        return 2

    language = plan.get("language") or {}
    verdict = language.get("verdict", "unknown")

    # An English reel is the overwhelming majority and has nothing to check. Say so quietly and stop:
    # a check that cannot fire is not a warning, and printing one would read like a fault.
    if verdict == "english":
        print("[check-plan-language] reel is English · nothing to check")
        return 0

    if verdict == "unknown":
        print("[check-plan-language] the reel's language was never determined, so on-screen copy "
              "cannot be checked. If this reel is not in English, confirm the copy yourself before "
              "building.", file=sys.stderr)
        return 2

    spoken = language.get("code") or verdict
    strings = on_screen_strings(plan)

    if not strings:
        planned = sum(1 for b in plan.get("beats", []) or [] if shows_a_graphic(b))
        if planned:
            beats_word = "beat carries" if planned == 1 else "beats carry"
            print(f"[check-plan-language] this reel is {spoken} and {planned} {beats_word} a graphic, "
                  f"but no beat records its `on_screen` copy, so the language of what lands in frame "
                  f"cannot be verified. Fill in `on_screen` for every graphic that shows words.",
                  file=sys.stderr)
            return 2
        print("[check-plan-language] no on-screen copy in this plan · nothing to check")
        return 0

    if copy_reads_as_english(text for _id, text in strings):
        print(f"[check-plan-language] REFUSED. This reel is {spoken}, but the on-screen copy reads "
              f"as English. Captions will follow the speaker and the graphics will not, which is the "
              f"reel that shipped Spanish captions under an English hook card.", file=sys.stderr)
        print(f"[check-plan-language] rewrite these in {spoken}:", file=sys.stderr)
        for beat_id, text in strings:
            print(f"    beat {beat_id}: {text}", file=sys.stderr)
        return 1

    print(f"[check-plan-language] on-screen copy reads as {spoken} across "
          f"{len(strings)} strings · pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
