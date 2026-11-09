#!/usr/bin/env python3
"""Course guide: which lesson covers what, and what each lesson actually says.

The `which-lesson` skill runs this. The guide (every published lesson's page text plus its video
transcript, English and Spanish) lives on the update server, not in this folder, so it is always the
newest course. It is cached in _local/course-guide.json and refreshed once a day; offline, the cached
copy is used.

    python3 scripts/course_guide.py index [--lang es]          every module and lesson, one block each
    python3 scripts/course_guide.py lesson <2.6 | id | words>   one lesson in full (page + timed video)
    python3 scripts/course_guide.py find <words> [--lang es]    where in the course something is said
    python3 scripts/course_guide.py refresh                     fetch the newest guide now

On Windows use `python`, not `python3` (see the update skill).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "_local" / "course-guide.json"
MAX_AGE = 24 * 3600

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # accents + curly quotes on a Windows console
except (AttributeError, ValueError):
    pass


def _guide_url():
    try:
        prod = json.loads((ROOT / "product.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(prod.get("course_guide_url") or "").strip()


def _download(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "engine-course-guide"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # A Python without its certificate bundle fails here on SSL; curl carries the system's own.
        curl = shutil.which("curl")
        if curl:
            p = subprocess.run([curl, "-fsSL", "--max-time", "30", url], capture_output=True)
            if p.returncode == 0 and p.stdout:
                return p.stdout.decode("utf-8")
        raise RuntimeError(str(e)) from e


def load(force=False):
    fresh = CACHE.exists() and time.time() - CACHE.stat().st_mtime < MAX_AGE
    if fresh and not force:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    url = _guide_url()
    err = "no guide address in product.json"
    if url:
        try:
            body = _download(url)
            guide = json.loads(body)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(body, encoding="utf-8")
            return guide
        except (RuntimeError, ValueError) as e:
            err = str(e)
    if CACHE.exists():
        print("(Couldn't reach the course guide online, so this is the copy saved on this computer.)\n")
        return json.loads(CACHE.read_text(encoding="utf-8"))
    sys.exit("COURSE GUIDE UNAVAILABLE: couldn't download it and there's no saved copy yet "
             f"({err}). Answer from what you know, and point her to the course home page.")


def lessons(guide):
    for m in guide["modules"]:
        for les in m["lessons"]:
            yield m, les


def _lang(les, field, lang):
    d = les.get(field) or {}
    return d.get(lang) or d.get("en") or ([] if field == "video" else "")


def cmd_index(guide, lang):
    print(f"{guide['course']}  (guide built {guide.get('built', '?')})")
    print(f"Course home: {guide.get('course_home', '')}\n")
    for m in guide["modules"]:
        print(f"MODULE {m['number']}: {m['title']}")
        for les in m["lessons"]:
            kind = f"video {les.get('video_minutes', '?')} min + page" if les.get("has_video") else "page"
            print(f"  {les['number']} {les['title']}  [{kind}]  id {les['id']}")
            if les.get("covers"):
                print(f"      covers: {les['covers']}")
            if les.get("asks"):
                print(f"      asked as: {' | '.join(les['asks'])}")
            print(f"      {les['url']}")
        print()
    print("Spanish: every video has Spanish subtitles (tap CC, choose Español) and every page has an "
          "Español switch at the top." if lang == "es" else "")


def pick(guide, query):
    q = query.strip().lower()
    all_ = list(lessons(guide))
    for m, les in all_:
        if q in (les["number"], les["id"], les["title"].lower()):
            return les
    words = [w for w in re.findall(r"\w+", q) if len(w) > 2]
    scored = sorted(((sum(w in les["title"].lower() for w in words), les) for _, les in all_),
                    key=lambda s: -s[0])
    if scored and scored[0][0]:
        return scored[0][1]
    sys.exit(f"No lesson matches {query!r}. Run `index` to see them all.")


def cmd_lesson(guide, query, lang):
    les = pick(guide, query)
    print(f"LESSON {les['number']}: {les['title']}  (module: {les['module']})")
    print(f"Link: {les['url']}")
    if les.get("covers"):
        print(f"Covers: {les['covers']}")
    print("\n--- LESSON PAGE ---\n")
    print(_lang(les, "page", lang))
    video = _lang(les, "video", lang)
    if les.get("has_video"):
        print(f"\n--- VIDEO ({les.get('video_minutes', '?')} min), what is said, with where it starts ---\n")
        if video:
            for c in video:
                print(f"[{c['at']}] {c['text']}\n")
        else:
            print("(No transcript for this video yet. Work from the page text above.)")
        if lang == "es" and not (les.get("video") or {}).get("es"):
            print("(This video has no Spanish subtitles yet; the transcript above is the English one.)")


STOP = set("""the and for you your how what where does can with that this from into about when which
lesson video show tell want need make get are was its it's have has one los las una unos con por para que
como cómo donde dónde esta está este esto cual cuál qué hago puedo quiero tengo del mis mi""".split())


def _score(text, words):
    """Distinct words matched dominate, raw repeats only break ties: 'como conecto apify' ranks the
    Apify paragraph above one that just says 'como' five times."""
    t = text.lower()
    return sum(10 + t.count(w) for w in words if w in t)


def cmd_find(guide, query, lang):
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2 and w not in STOP]
    if not words:
        sys.exit("Give me a few words to look for.")
    hits = []
    for _, les in lessons(guide):
        page = _lang(les, "page", lang)
        for para in [p for p in page.split("\n\n") if p.strip()]:
            s = _score(para, words)
            if s:
                hits.append((s, les, "page", para))
        for c in _lang(les, "video", lang):
            s = _score(c["text"], words)
            if s:
                hits.append((s, les, f"video at {c['at']}", c["text"]))
    if not hits:
        print(f"Nothing in the course mentions {query!r}. Try other words, or run `index`.")
        return
    hits.sort(key=lambda h: -h[0])
    for s, les, where, text in hits[:8]:
        snippet = text if len(text) < 420 else text[:420].rsplit(" ", 1)[0] + "..."
        print(f"{les['number']} {les['title']}  ({where})\n  {les['url']}\n  {snippet}\n")


def main():
    ap = argparse.ArgumentParser(description="Which lesson covers what.")
    ap.add_argument("command", choices=["index", "lesson", "find", "refresh"])
    ap.add_argument("query", nargs="*")
    ap.add_argument("--lang", choices=["en", "es"], default="en")
    a = ap.parse_args()
    guide = load(force=a.command == "refresh")
    q = " ".join(a.query)
    if a.command == "refresh":
        n = sum(1 for _ in lessons(guide))
        print(f"Course guide is current: {n} lessons, built {guide.get('built', '?')}.")
    elif a.command == "index":
        cmd_index(guide, a.lang)
    elif a.command == "lesson":
        cmd_lesson(guide, q, a.lang)
    else:
        cmd_find(guide, q, a.lang)


if __name__ == "__main__":
    main()
