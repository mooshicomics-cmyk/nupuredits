#!/usr/bin/env python3
"""choices.py — what she chose on each reel, and what autopilot does from that.

Every reel records its choices in ONE place, projects/<job>/review/choices.json (pack, route, register, format),
whether she walked through each phase or ran it on autopilot. Older reels kept them in their graphics plan or beat
sheet under different names; those are read too, so her history starts with the reels she has already made.

Autopilot ("just edit it") builds straight to the end from:
  * pack     the one on her most recent reel (the one she has been choosing lately)
  * route    the finish she picked most across her recent reels (ties go to the most recent)
  * register NEVER carried from another reel (it's about THIS video): phase by phase it's asked right before her visual
             editor opens (review_gate.py), Claude's read marked; on autopilot it's read from her words (register_guess)
  * the rest is already automatic: learned.py preferences, her lookbook first, favorites.py sounds
Nothing is guessed from nothing: with no past reels there are no autopilot defaults, and she walks through once.

    python3 product/choices.py defaults                 # what autopilot would use, and why (JSON + plain lines)
    python3 product/choices.py record <job> pack=Butter route=medium register=teaching mode=autopilot
    python3 product/choices.py register <job>           # the teaching / confessional lean in her words (evidence)
    python3 product/choices.py mode [walk|autopilot]    # how she ran her last reel (the default next time)
Stdlib only; every reader degrades to "no default" rather than raising.
"""
import json, os, re, sys, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROUTES = ("raw", "medium", "well-done", "hands-off", "capcut", "mp4")   # the page's Finish routes too
REGISTERS = ("teaching", "confessional")
MODES = ("walk", "autopilot")
KEYS = ("pack", "route", "register", "format", "mode")
RECENT = 8                                   # how many recent reels autopilot learns from


def _projects():
    return os.path.join(ROOT, "projects")


def _job_dir(job):
    return job if os.path.isabs(job) else os.path.join(_projects(), job)


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _clean(d):
    """One reel's choices in the one shape, from any of the places a reel has kept them."""
    out = {}
    pack = d.get("pack") or d.get("style_pack")
    if isinstance(pack, str) and pack.strip():
        out["pack"] = pack.strip()
    route = d.get("route") or d.get("doneness")
    if route in ROUTES:
        out["route"] = route
    if d.get("register") in REGISTERS:
        out["register"] = d["register"]
    if isinstance(d.get("format"), str):
        out["format"] = d["format"]
    if d.get("mode") in MODES:
        out["mode"] = d["mode"]
    return out


def read(job):
    """This reel's choices: its choices.json first, then what its plan and beat sheet recorded."""
    jd = _job_dir(job)
    got = {}
    for rel in ("beat-sheet/beats.json", "graphics-plan.json", "review/choices.json"):   # later wins
        d = _load(os.path.join(jd, rel))
        if isinstance(d, dict):
            got.update(_clean(d))
    return got


def record(job, **choices):
    """Save what she chose on this reel (validated; unknown values are dropped, never guessed at)."""
    jd = _job_dir(job)
    p = os.path.join(jd, "review", "choices.json")
    cur = _load(p) or {}
    if choices.get("pack"):
        try:
            sys.path.insert(0, HERE)
            import stylepack
            if choices["pack"] not in stylepack.names():
                choices.pop("pack")
        except Exception:
            pass
    cur.update(_clean(choices))
    cur["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    json.dump(cur, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, p)
    return cur


def history(limit=RECENT, skip=()):
    """Her recent reels' choices, newest first (by when each reel was last worked on). A reel that carries the
    review/.test-reel marker (a copy made to test the engine) is not hers to learn from, and neither is a trial reel
    (review/trial-of.json, product/trial_edits.py): it is a copy of a reel already counted."""
    root = _projects()
    if not os.path.isdir(root):
        return []
    rows = []
    for name in os.listdir(root):
        jd = os.path.join(root, name)
        if not os.path.isdir(jd) or name.startswith((".", "_")) or name in skip \
                or os.path.exists(os.path.join(jd, "review", ".test-reel")) \
                or os.path.exists(os.path.join(jd, "review", "trial-of.json")):   # a test copy, or a trial reel of another reel
            continue
        c = read(jd)
        if not c:
            continue
        when = max((os.path.getmtime(os.path.join(jd, f)) for f in ("review/choices.json", "graphics-plan.json", "beat-sheet/beats.json")
                    if os.path.exists(os.path.join(jd, f))), default=0)
        rows.append((when, name, c))
    rows.sort(reverse=True)
    return [dict(c, job=n) for _, n, c in rows[:limit]]


def defaults(skip=()):
    """What autopilot uses, each with the reason in plain words. A choice with no history behind it is left out."""
    h = history(skip=skip)
    out, why = {}, {}
    packs = [r for r in h if r.get("pack")]
    if packs:
        try:
            sys.path.insert(0, HERE)
            import stylepack
            have = set(stylepack.names())
        except Exception:
            have = None
        for r in packs:                                    # the most recent pack that still exists in this engine
            if have is None or r["pack"] in have:
                out["pack"] = r["pack"]
                why["pack"] = f"the pack on your most recent reel ({r['job']})"
                break
    routes = [r["route"] for r in h if r.get("route")]
    if routes:
        n = Counter(routes)
        top = max(n.values())
        pick = next(x for x in routes if n[x] == top)        # most picked; a tie goes to the most recent
        out["route"] = pick
        why["route"] = f"what you picked on {top} of your last {len(routes)} reels"
    modes = [r["mode"] for r in h if r.get("mode")]
    out["mode"] = modes[0] if modes else "walk"
    return {"defaults": out, "why": why, "from_reels": [r["job"] for r in h]}


# ── teaching or confessional, from her own words ────────────────────────────────────────────────────────────
_TEACH = re.compile(r"\b(step|steps|tip|tips|how to|here's how|here is how|first|second|third|number one|"
                    r"\d+|percent|dollars?|framework|mistake|mistakes|you need|you should|you can|do this|"
                    r"the secret|the reason|three|four|five|list)\b", re.I)
_CONFESS = re.compile(r"\b(i felt|i feel|i was|i didn't|i couldn't|i cried|honestly|i remember|my (mom|kids?|"
                      r"husband|son|daughter|heart)|scared|afraid|lonely|ashamed|guilt|i used to|i never thought|"
                      r"i'm not proud|truth is)\b", re.I)


def register_guess(text):
    """('teaching' | 'confessional' | None, why): a LEAN from her words, the evidence Claude checks its own read
    against (it reads the whole transcript and decides; this keeps that decision honest and explainable).
    None = no clear lean either way."""
    t = text or ""
    teach, conf = len(_TEACH.findall(t)), len(_CONFESS.findall(t))
    if teach >= 3 and conf * 3 <= teach:
        return "teaching", f"it walks through things to do ({teach} teaching signals, {conf} personal-story signals)"
    if conf >= 3 and teach * 3 <= conf:
        return "confessional", f"it's a personal story ({conf} personal-story signals, {teach} teaching signals)"
    return None, f"no clear lean from the words alone ({teach} teaching signals, {conf} personal-story signals)"


def register_for(job):
    jd = _job_dir(job)
    tr = _load(os.path.join(jd, "outputs", os.path.basename(os.path.abspath(jd)) + ".transcript.json"))
    if isinstance(tr, dict):
        text = tr.get("text") or " ".join(w.get("text", "") for w in tr.get("words", []))
    else:
        w = _load(os.path.join(jd, "transcript", "words.json")) or {}
        text = " ".join(x.get("word", x.get("w", "")) for c in w.get("clips", []) for x in c.get("words", []))
    return register_guess(text)


def main(argv):
    if not argv or argv[0] not in ("defaults", "record", "register", "mode", "read"):
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "defaults":
        d = defaults()
        print(json.dumps(d, indent=1))
        for k, v in d["defaults"].items():
            if k in d["why"]:
                print(f"  {k}: {v} — {d['why'][k]}")
        if not d["from_reels"]:
            print("  No past reels to learn from yet: walk through this one, and autopilot learns from it.")
        return 0
    if cmd == "read":
        print(json.dumps(read(argv[1]), indent=1))
        return 0
    if cmd == "record":
        kv = dict(a.split("=", 1) for a in argv[2:] if "=" in a)
        print(json.dumps(record(argv[1], **kv), indent=1))
        return 0
    if cmd == "register":
        reg, why = register_for(argv[1])
        print(f"lean: {reg or 'none'} ({why})")
        return 0
    if cmd == "mode":
        if len(argv) > 1:
            if argv[1] not in MODES:
                print("mode is walk or autopilot")
                return 2
            p = os.path.join(ROOT, "_local", "autopilot.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            json.dump({"mode": argv[1], "at": time.strftime("%Y-%m-%d %H:%M:%S")}, open(p, "w", encoding="utf-8"))
            print(argv[1])
            return 0
        d = _load(os.path.join(ROOT, "_local", "autopilot.json")) or {}
        print(d.get("mode") or defaults()["defaults"].get("mode", "walk"))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
