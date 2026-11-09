#!/usr/bin/env python3
"""plan_language.py — is the copy about to go on screen in the language she speaks?

Captions are built from her transcript, so they follow her language on their own. Hook, card and label copy is
written fresh, and its writer's default is English: a Spanish reel shipped with an English hook card. The
graphics plan has a check for that (.claude/skills/graphics-plan/scripts/check-plan-language.py), but it only ran
when a planner remembered to run it. This is the same judgment, called by the code that BUILDS the copy:

  build-reel-type.py   the rendered type layer (hook, labels, breakaway lines, the bubble)
  beat-sheet.py        every route, before anything renders or the draft is written
  cleanyap / superyap  the CapCut builders, on every text they placed
  capcut-live.py       place-plan, the graphics plan laid on a draft
  visual_editor.py     a hook placed on her page (hers or Claude's)

It WARNS, one plain line naming the strings and her language, and never stops a build: she always gets her reel,
and a bilingual reel can mean its English card. An English reel, or one whose language was never found, says
nothing at all.

    python3 product/plan_language.py <job>     the warning, or a quiet "reads in <language>" (exit 1 = warned)
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _root in (os.path.dirname(os.path.dirname(os.path.realpath(__file__))), ROOT):   # a linked copy finds the real one
    sys.path.insert(0, os.path.join(_root, ".claude", "skills", "rough-cut", "scripts"))
try:
    from transcript_language import classify, copy_reads_as_english
except Exception:                                       # the classifier missing is no reason to stop a build
    classify = copy_reads_as_english = None

NAMES = {"es": "Spanish", "pt": "Portuguese", "fr": "French", "it": "Italian", "de": "German", "nl": "Dutch",
         "ca": "Catalan", "ro": "Romanian", "pl": "Polish", "cs": "Czech", "hu": "Hungarian", "sv": "Swedish",
         "da": "Danish", "no": "Norwegian", "nb": "Norwegian", "fi": "Finnish", "tr": "Turkish", "el": "Greek",
         "ru": "Russian", "uk": "Ukrainian", "ar": "Arabic", "he": "Hebrew", "hi": "Hindi", "ja": "Japanese",
         "ko": "Korean", "zh": "Chinese", "id": "Indonesian", "vi": "Vietnamese", "tl": "Tagalog",
         "ht": "Haitian Creole"}


def language_name(code):
    """'es' -> 'Spanish'. An unknown code is said as itself; no code at all is None."""
    if not code:
        return None
    code = str(code).lower().split("-")[0]
    return NAMES.get(code, code)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def job_dir(job):
    """projects/<job>, or None for no job."""
    return os.path.join(ROOT, "projects", job) if job else None


def transcript_path(job_dir):
    job = os.path.basename(os.path.normpath(job_dir))
    return os.path.join(job_dir, "outputs", f"{job}.transcript.json")


def reel_language(job_dir, plan=None):
    """{"code", "verdict"} for the reel: the plan's own stamp (beat-lines.py) when it has one, else the job
    transcript. A transcript from before language detection carries a bare "en" on every job, Spanish ones too, so
    with no verdict beside it the words are re-read rather than trusted (as beat-lines.resolve_language does)."""
    stamp = (plan or {}).get("language") or {}
    if stamp.get("verdict"):
        return {"code": stamp.get("code"), "verdict": stamp["verdict"]}
    tr = _read(transcript_path(job_dir))
    verdict, code = tr.get("language_verdict"), tr.get("language_code")
    if verdict:
        return {"code": code, "verdict": verdict}
    if code and str(code).lower() != "en":
        return {"code": code, "verdict": "non_english"}
    words = [str(w.get("text", "")) for w in tr.get("words") or [] if isinstance(w, dict)]
    if words and classify is not None:
        fresh = classify(words)
        return {"code": fresh.get("language_code"), "verdict": fresh["verdict"]}
    return {"code": None, "verdict": "unknown"}


def _strs(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strs(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strs(v)]
    return []


def graphics_plan_strings(plan):
    """The `on_screen` copy of every beat (never `idea`, which is prose ABOUT the graphic)."""
    return [s for b in (plan or {}).get("beats") or [] if isinstance(b, dict) for s in _strs(b.get("on_screen"))]


def caption_plan_strings(cp):
    """The authored copy in a caption plan: the hook (every pack's), the long hook, the persistent label, the
    breakaway lines, the bubble's words and the card labels. Captions and takeovers are her own words: skipped."""
    cp = cp or {}
    out = _strs(cp.get("hook")) + _strs(cp.get("hook_by_pack")) + _strs(cp.get("hook_long")) \
        + _strs(cp.get("persistent_label"))
    for bk in cp.get("breakaways") or []:
        if isinstance(bk, dict):
            out += _strs(bk.get("lines")) or _strs(bk.get("text"))
    vibe = cp.get("vibe") or {}
    if isinstance(vibe, dict) and vibe.get("kind") == "bubble":
        out += _strs(vibe.get("text"))
    for el in cp.get("elements") or []:
        if isinstance(el, dict):
            out += _strs(el.get("label"))
    return out


def check(job_dir, texts=(), plans=True):
    """One plain warning line when the reel is not in English and the copy reads as English, else None.
    texts: copy the caller is placing itself. plans: also read the job's graphics-plan.json and caption-plan.json.
    Never raises: a check that cannot run says nothing, it never breaks the build that called it."""
    try:
        if copy_reads_as_english is None or not job_dir:
            return None
        plan = _read(os.path.join(job_dir, "graphics-plan.json")) if plans else {}
        strings = [str(t).strip() for t in texts if str(t or "").strip()]
        if plans:
            strings += graphics_plan_strings(plan) + caption_plan_strings(_read(os.path.join(job_dir, "caption-plan.json")))
        strings = list(dict.fromkeys(s.strip() for s in strings if s.strip()))   # each once, in order
        if not strings:
            return None
        lang = reel_language(job_dir, plan)
        if lang["verdict"] in ("english", "unknown", None):
            return None
        if not copy_reads_as_english(strings):
            return None
        name = language_name(lang.get("code"))
        quoted = ", ".join(f'"{s}"' for s in strings[:6]) + (f" and {len(strings) - 6} more" if len(strings) > 6 else "")
        where = f"in {name}" if name else "not in English"
        return (f"This reel is {where}, but this on-screen copy reads as English: {quoted}. It is built as written; "
                f"rewrite it {'in ' + name if name else 'in her language'} if it should match her voice.")
    except Exception:
        return None


def warn(job_dir, texts=(), plans=True, prefix="  ⚠ "):
    """check(), printed as one line when it has something to say. Returns the line (or None)."""
    line = check(job_dir, texts, plans)
    if line:
        print(prefix + line, flush=True)
    return line


def hook_note(job_dir, copy):
    """The short version for her editor page (a card she closes): a hook she or Claude placed, in English on a
    reel that is not. Her words stay exactly as written: her click is final."""
    if not check(job_dir, [copy], plans=False):
        return None
    name = language_name(reel_language(job_dir).get("code"))
    return (f"Your hook reads as English, and this reel is in {name}. It's kept as you wrote it; change its words "
            f"on the card if you'd like it in {name}." if name else
            "Your hook reads as English, and this reel isn't in English. It's kept as you wrote it; change its words "
            "on the card if you'd like it to match.")


def main(argv):
    if not argv:
        sys.exit("usage: plan_language.py <job>")
    job_dir = argv[0] if os.path.isdir(argv[0]) else os.path.join(ROOT, "projects", argv[0])
    line = check(job_dir)
    if line:
        print(line)
        return 1
    lang = reel_language(job_dir)
    print(f"on-screen copy: nothing to flag (reel language: {language_name(lang.get('code')) or lang['verdict']})")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
