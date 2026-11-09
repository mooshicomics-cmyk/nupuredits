#!/usr/bin/env python3
"""review_gate.py — the step after EVERY rough cut, walk-through and autopilot alike: "Your rough cut is done."

The rough cut's last line hands off here, the way "next phase" did in the old build. It prints the exact
clickable question to ask (AskUserQuestion, never a question she types an answer to), and records her pick, so
the order can't drift and her choice sticks.

    python3 product/review_gate.py start                          BEFORE the cut: phase by phase or autopilot, or nothing to ask
    python3 product/review_gate.py start phase|autopilot          record her pick
    python3 product/review_gate.py <job>                          AFTER the cut: what to ask now (or where her default goes)
    python3 product/review_gate.py <job> editor                   she picked the visual editor
    python3 product/review_gate.py <job> widget                   she picked the original widget
    python3 product/review_gate.py <job> --default always|once    after the editor pick: her new default, or just this once
    python3 product/review_gate.py <job> --register teaching      her answer to "teaching or confessional?" (editor road)
    add --json for the same thing as JSON

Before the cut: autopilot runs off the reels she finished in the visual editor, so it is offered only once she has
finished one (or already used it). Until then nothing is asked before the cut. The first time it is offered, the
question says what's new.
After the cut (phase by phase only; autopilot never stops here, it opens the editor on her Sound tab):
    ask (the default)  → "Your rough cut is done. Would you like to try the new visual editor?"  editor · original widget
        editor  → "make it your new default, or just try it this once?" (pick-one), then the register
                  always → her default from now on (learned review.style_plan_mode visual)
                  once   → this reel only, the question comes back next reel
        widget  → this reel on the widget, asked again next reel
    visual (saved)     → straight to "Before I open your editor: teaching or confessional?"
    text (saved)       → straight to the widget, with one SAY line: the editor is there anytime ("open my visual editor")
Early access: with the editor off in this engine (product/early_access.py), nothing is asked before the cut and the
rough cut always goes straight to the widget; the editor and autopilot are never offered or named.
"""
import json, os, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULT_Q = ("Before you switch over: do you want to make the visual editor your new default, or just try it out "
             "this one time?")
ALWAYS_OPT = {"label": "Make the visual editor my new default",
              "description": "Every rough cut opens in the visual editor. Ask for the original widget anytime to switch back."}
ONCE_OPT = {"label": "Let me try it once before deciding",
            "description": "The visual editor for this reel only. I'll ask again after your next rough cut."}
DEFAULTS = ("always", "once")
SWITCHED_TO_WIDGET = ("Switched you back to the original widget. The visual editor is there whenever you want it: just "
                      "type \"open my visual editor\".")
REVIEW_Q = ("Your rough cut is done. Would you like to try the new visual editor? It's an improved editing experience, "
            "giving you more visual control and faster results, and it uses fewer of your Claude tokens. Or would you like "
            "to continue with the original widget?")
EDITOR_OPT = {"label": "Try the new visual editor (Early access, in beta)",
              "description": "Your whole reel on one page in your browser: more visual control, faster results, fewer tokens. Bugs are still being worked out."}
WIDGET_OPT = {"label": "Continue with the original widget",
              "description": "The original Reels Editing Engine flow: the exact style plan from your course videos."}
PICKS = ("editor", "widget")
START_NEW = ("New: Autopilot. Now that you've finished a reel in the visual editor, I can edit a reel from the looks "
             "you've made there. How do you want to edit this one?")
START_Q = "How do you want to edit this one?"
PHASE_OPT = {"label": "Phase by phase (Recommended)",
             "description": "Recommended for precise results. You review your rough cut first, then we build your "
                            "visuals and sound step by step."}
AUTO_OPT = {"label": "Autopilot",
            "description": "A good option if you've made a reel like this before and want to repeat a past look from "
                           "your visual editor. Opens your finished draft in the visual editor."}
AUTO_INTRO_KEY = "autopilot-intro"


def _on():
    try:
        import early_access
        return early_access.editor_on()
    except Exception:
        return False


def _mode():
    try:
        import visual_editor
        return visual_editor.review_mode()
    except Exception:
        return "ask"


def _saved():
    try:
        import learned
        v = learned.value("review.style_plan_mode", "ask")
        return (v[0] if isinstance(v, tuple) else v) or "ask"
    except Exception:
        return "ask"


def _learn(v, note):
    import learned
    learned.add("review.style_plan_mode", v, note=note)


def _autopilot():
    try:
        import choices
        d = choices._load(os.path.join(choices.ROOT, "_local", "autopilot.json")) or {}
        return d.get("mode") == "autopilot"
    except Exception:
        return False


def _autopilot_file():
    import choices
    return os.path.join(choices.ROOT, "_local", "autopilot.json")


def autopilot_ready():
    """Autopilot edits from the reels she finished in the visual editor: offered once she has one (or used it)."""
    if not _on():
        return False
    if os.path.exists(_autopilot_file()):
        return True
    try:
        import visual_editor
        return visual_editor._finished_in_editor()
    except Exception:
        return False


def start():
    """The one question before the cut, or none."""
    if not autopilot_ready():
        return {"step": "cut", "then": "no question before the cut: straight to the rough cut (phase by phase)"}
    try:
        import first_use
        new = AUTO_INTRO_KEY not in first_use._load()
    except Exception:
        new = False
    return {"step": "start",
            "ask": {"header": "Mode", "question": START_NEW if new else START_Q, "options": [PHASE_OPT, AUTO_OPT], "multiSelect": False},
            "note": "Ask it as ONE clickable multiple choice (AskUserQuestion), before the cut.",
            "then": "python3 product/review_gate.py start phase|autopilot"}


def start_pick(choice):
    if choice not in ("phase", "autopilot"):
        raise ValueError(f"the pick is phase or autopilot, not {choice!r}")
    if not _on():
        return start()
    import time
    try:
        import first_use
        d = first_use._load()
        if AUTO_INTRO_KEY not in d:
            d[AUTO_INTRO_KEY] = time.strftime("%Y-%m-%d"); first_use._save(d)
    except Exception:
        pass
    p = _autopilot_file(); os.makedirs(os.path.dirname(p), exist_ok=True)
    mode = "autopilot" if choice == "autopilot" else "walk"
    json.dump({"mode": mode, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, open(p, "w", encoding="utf-8"))
    if mode == "autopilot":
        return {"step": "autopilot", "then": "load the autopilot skill: the rough cut, then everything built, then "
                                             "python3 product/visual_editor.py open <job> --autopilot (no stop after the cut)"}
    return {"step": "cut", "then": "the rough cut (rough-cut skill); after it, python3 product/review_gate.py <job>"}


def _mark_intro_seen():
    try:
        import first_use, time
        d = first_use._load()
        if "visual-editor" not in d:
            d["visual-editor"] = time.strftime("%Y-%m-%d"); first_use._save(d)
    except Exception:
        pass


def _register_step(job):
    try:
        import choices
        reg, why = choices.register_for(job)
    except Exception:
        reg, why = None, ""
    rec = reg if reg in ("teaching", "confessional") else None
    opts = []
    for r, d in (("teaching", "Steps, numbers, a how-to: more looks on it."),
                 ("confessional", "Her story, a feeling: lean, almost no graphics.")):
        opts.append({"label": r.capitalize() + (" (Recommended)" if r == rec else ""), "description": d})
    if rec == "confessional":
        opts.reverse()
    name = os.path.basename(os.path.normpath(job))
    return {"step": "register",
            "ask": {"header": "Reel type", "question": "Before I open your editor: is this a teaching or a confessional reel?",
                    "options": opts, "multiSelect": False},
            "lean": {"register": reg, "why": why},
            "note": "Read the kept words yourself too; mark your read (Recommended). Her answer is the register.",
            "then": f"python3 product/review_gate.py {name} --register <teaching|confessional>"}


EDITOR_ANYTIME = "Your visual editor is here anytime: type 'open my visual editor'."


def _widget_step(job, say=None):
    name = os.path.basename(os.path.normpath(job))
    out = {"step": "widget", "then": "the original widget: rough-cut's style plan, steps 1-4 (her notes, then the creative plan)"}
    if say:
        out["say"] = say
    if _autopilot() and _on():
        out["autopilot"] = "Autopilot ends here: the widget is the walk-through's road. Say so in one line."
    out["route"] = f"python3 product/review_route.py {name}  → widget"
    return out


def gate(job):
    """What to ask right after the rough cut. Never records anything."""
    name = os.path.basename(os.path.normpath(job))
    if not _on():
        return _widget_step(job)
    if _autopilot():
        return {"step": "autopilot", "then": f"no question: autopilot carries on (creative plan, looks), then "
                                             f"python3 product/visual_editor.py open {name} --autopilot"}
    m = _mode()
    if m == "text":                              # her saved choice skips the question, never the editor itself
        return _widget_step(job, EDITOR_ANYTIME)
    if m == "visual":
        return _register_step(job)
    return {"step": "review",
            "ask": {"header": "Review", "question": REVIEW_Q, "options": [EDITOR_OPT, WIDGET_OPT], "multiSelect": False},
            "note": "Ask it as ONE clickable multiple choice (AskUserQuestion), walk-through and autopilot alike. "
                    "Nothing written before the box shows, so everything she needs is inside the question.",
            "then": f"python3 product/review_gate.py {name} editor | widget"}


def pick(job, choice):
    """Record her pick and say what comes next."""
    import review_route
    if choice not in PICKS:
        raise ValueError(f"the pick is editor or widget, not {choice!r}")
    if not _on():
        review_route.set_route(job, "widget")
        return _widget_step(job)
    m, saved = _mode(), _saved()
    _mark_intro_seen()
    if choice == "widget":
        review_route.set_route(job, "widget")
        say = None
        if saved == "visual":
            _learn("text", "she asked for the original widget back")
            say = SWITCHED_TO_WIDGET
        if _autopilot():
            import choices
            p = os.path.join(choices.ROOT, "_local", "autopilot.json")
            out = _widget_step(job, say)
            json.dump({"mode": "walk", "at": __import__("time").strftime("%Y-%m-%d %H:%M:%S")}, open(p, "w", encoding="utf-8"))
            return out
        return _widget_step(job, say)
    review_route.set_route(job, "editor")
    if saved == "visual":
        return _register_step(job)
    return {"step": "default",
            "ask": {"header": "Default", "question": DEFAULT_Q, "options": [ALWAYS_OPT, ONCE_OPT], "multiSelect": False},
            "note": "Ask it as ONE clickable multiple choice (AskUserQuestion), then the register question.",
            "then": f"python3 product/review_gate.py {os.path.basename(os.path.normpath(job))} --default always|once"}


def set_default(job, choice):
    """Her answer to "new default, or just this once?" after picking the editor; then the register question."""
    if choice not in DEFAULTS:
        raise ValueError(f"the answer is always or once, not {choice!r}")
    if not _on():
        return _widget_step(job)
    if choice == "always" and _saved() != "visual":
        _learn("visual", "she made the visual editor her default after her rough cut")
    return _register_step(job)


def register(job, reg):
    import choices
    if reg not in choices.REGISTERS:
        raise ValueError(f"the register is teaching or confessional, not {reg!r}")
    choices.record(job, register=reg)
    if not _on():
        return _widget_step(job)
    name = os.path.basename(os.path.normpath(job))
    if _autopilot():
        return {"step": "autopilot", "register": reg,
                "then": "autopilot step 4: the creative plan and the looks (no approval stop), then step 5 opens her editor"}
    return {"step": "open", "register": reg, "then": f"python3 product/visual_editor.py open {name}"}


def _print(out, as_json):
    if as_json:
        print(json.dumps(out, indent=1, ensure_ascii=False)); return
    if out.get("say"):
        print(f"SAY: {out['say']}")
    if out.get("autopilot"):
        print(f"SAY: {out['autopilot']}")
    if "ask" in out:
        a = out["ask"]
        print(f"ASK (one clickable multiple choice, AskUserQuestion), header {a['header']!r}:")
        print(f"  question: {a['question']}")
        for o in a["options"]:
            print(f"  - {o['label']}: {o['description']}")
        if out.get("lean", {}).get("register"):
            print(f"  her words lean {out['lean']['register']} ({out['lean']['why']})")
    if out.get("note"):
        print(f"NOTE: {out['note']}")
    if out.get("route"):
        print(f"ROUTE: {out['route']}")
    print(f"NEXT: {out['then']}")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    job = argv[0]
    try:
        if job == "start":
            out = start_pick(argv[1]) if len(argv) > 1 else start()
        elif "--default" in argv:
            i = argv.index("--default")
            out = set_default(job, argv[i + 1] if i + 1 < len(argv) else "")
        elif "--register" in argv:
            i = argv.index("--register")
            out = register(job, argv[i + 1] if i + 1 < len(argv) else "")
        elif len(argv) > 1:
            out = pick(job, argv[1])
        else:
            out = gate(job)
    except ValueError as e:
        print(e, file=sys.stderr); return 2
    _print(out, as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
