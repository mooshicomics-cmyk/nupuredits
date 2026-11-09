#!/usr/bin/env python3
"""first_use.py — the first time a buyer meets a new tool in her engine, say hello ONCE.

Buyers update from older courses, so a new tool can appear in an engine whose owner has never heard of it. The
first time a skill is about to use one, it asks this script; on that first time it prints the introduction to
say (fun, short, honest), and the skill marks it seen once it has been said. It is never shown twice.

    python3 product/first_use.py visual-editor          exit 0 and print the introduction if she has never seen it; exit 1 (silent) otherwise
    python3 product/first_use.py visual-editor --seen   mark it said
    python3 product/first_use.py --list                 every tool and whether it has been introduced
    python3 product/first_use.py visual-editor --reset  forget it was said (to hear it again)

Rules for every introduction (2026-10-13): it opens like an upgrade ("Your engine just got an upgrade!"),
says what the tool does in a sentence, offers to try it, points to the lesson, says "optional" ONLY when it truly
is, and always invites questions. State lives in _local/ (kept through every update, never shipped).
"""
import json, os, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "_local", "first-use.json")
ASK = "If you're not sure what something is, ask me. I'll help you figure it out."

# optional=True only when the old way still works and nothing is lost by skipping it.
TOOLS = {
    "visual-editor": {
        "name": "the visual editor",
        "beta": True,
        # it replaces the widget the course videos show, so it is introduced as that widget's upgrade
        "hello": "Your widget just got an upgrade! ✨ Meet the visual editor (beta).",
        "hello_fresh": "New since the course videos: the visual editor (beta). It replaces the widget you'll see in them.",
        "what": "Your whole reel on one page in your browser: tap a word and press Cut, hear every edit instantly, swap "
                "looks and sounds line by line, and export to CapCut or an MP4. No waiting on a render to see a change.",
        "lesson": "which lesson covers the visual editor",
        "optional": "Prefer the original widget? It works just like the course videos show, and it's always here. "
                    "Just ask for it.",
    },
    "beat-sheet": {
        "name": "the beat sheet",
        "what": "Every key moment of your reel as a numbered still, before anything renders, so you can give "
                "notes by beat number.",
        "lesson": "which lesson covers the beat sheet",
        "optional": "You can skip it any time and render straight away.",
    },
    "lookbook": {
        "name": "your lookbook",
        "what": "A menu of the looks you've approved, the layouts your engine reaches for first on every reel.",
        "lesson": "which lesson covers the lookbook",
        "optional": None,
    },
}


def _load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, STATE)


def _fresh_install():
    """No reel edited before this one: nothing was 'upgraded' for her, it's simply new."""
    import glob
    return len(glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", "*", "transcript", "cuts.json"))) <= 1


def intro(tool):
    t = TOOLS[tool]
    fresh = _fresh_install()
    beta = " (in beta)" if t.get("beta") else ""
    hello = (t.get("hello_fresh") or f"Meet the {t['name']}{beta}.") if fresh else \
        (t.get("hello") or f"Your engine just got an upgrade! ✨ NEW{beta}: {t['name']}.")
    lines = [hello, t["what"],
             f"Want a walkthrough first? Ask me “{t['lesson']}” and I'll take you straight to it."]
    if t.get("optional"):
        lines.append(t["optional"])
    if t.get("beta"):
        lines.append("It's in beta, so if anything looks off, tell me and I'll sort it out.")
    lines.append(ASK)
    return "\n".join(lines)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    if argv[0] == "--list":
        d = _load()
        for k in TOOLS:
            print(f"{k:14s} {'introduced ' + d[k] if k in d else 'not yet'}")
        return 0
    tool = argv[0]
    if tool not in TOOLS:
        print(f"unknown tool {tool!r}; known: {', '.join(TOOLS)}", file=sys.stderr); return 2
    d = _load()
    if "--seen" in argv:
        import time
        d[tool] = time.strftime("%Y-%m-%d"); _save(d); return 0
    if "--reset" in argv:
        d.pop(tool, None); _save(d); return 0
    if tool in d:
        return 1
    print(intro(tool))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
