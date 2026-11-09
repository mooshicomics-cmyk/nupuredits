#!/usr/bin/env python3
"""Guards: the step after every rough cut (product/review_gate.py) asks the same clickable question every time and
makes her pick stick.

  start     before the cut: nothing to ask until she has finished a reel in the editor; then phase by phase
            (recommended) or autopilot, saying what's new the first time
  ask       "Your rough cut is done. Would you like to try the new visual editor?" as a pick-one, the editor first
  editor    the reel locked to the editor, then "new default, or just this once?" as a pick-one; always = her default
            from now on (review.style_plan_mode visual), once = nothing saved; then "teaching or confessional?"
  widget    this reel on the widget only, asked again next reel
  saved     visual skips straight to the register question; text goes straight to the widget; asking for the widget
            while the editor is her default switches her back for good, said in her words
  autopilot no question after the cut; the editor opens on her visuals
  register  recorded on the reel; walk-through opens the editor next
  stitch    the rough cut's last line names this gate

Run: python3 product/tests/test_review_gate.py
"""
import json, os, shutil, sys, tempfile
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ENGINE = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import review_gate as rg, choices, first_use, review_route  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def main():
    tmp = tempfile.mkdtemp(prefix="review-gate-")
    real = (choices.ROOT, first_use.STATE, rg._mode, rg._saved, rg._learn, rg.autopilot_ready)
    state = {"mode": "ask", "saved": "ask", "learned": [], "finished": False}
    choices.ROOT = tmp
    first_use.STATE = os.path.join(tmp, "_local", "first-use.json")
    rg._mode = lambda: state["mode"]
    rg._saved = lambda: state["saved"]
    rg._learn = lambda v, note: state["learned"].append(v)
    rg.autopilot_ready = lambda: os.path.exists(rg._autopilot_file()) or state["finished"]
    job = os.path.join(tmp, "projects", "the-pricing-one")
    os.makedirs(os.path.join(job, "outputs"))
    json.dump({"text": "three steps to price your offer. step one, count your hours"},
              open(os.path.join(job, "outputs", "the-pricing-one.transcript.json"), "w", encoding="utf-8"))
    try:
        # before the cut: nothing to ask until she has finished a reel in the editor
        check("start: a buyer who never finished a reel in the editor goes straight to the cut", rg.start()["step"] == "cut", rg.start())
        state["finished"] = True
        g = rg.start()
        check("start: once she has, phase by phase (recommended) or autopilot, saying what's new the first time",
              g["step"] == "start" and g["ask"]["question"] == rg.START_NEW
              and [o["label"] for o in g["ask"]["options"]] == ["Phase by phase (Recommended)", "Autopilot"], g)
        rg.start_pick("phase")
        check("start: the intro shows once", rg.start()["ask"]["question"] == rg.START_Q)
        # after the cut, phase by phase: her words
        g = rg.gate(job)
        check("ask: her question, as one pick-one", g["step"] == "review" and g["ask"]["question"] == rg.REVIEW_Q
              and g["ask"]["question"].startswith("Your rough cut is done.") and g["ask"]["multiSelect"] is False, g)
        labels = [o["label"] for o in g["ask"]["options"]]
        check("ask: the new visual editor first, marked early access, then the original widget",
              labels == ["Try the new visual editor (Early access, in beta)", "Continue with the original widget"], labels)
        descs = [o["description"] for o in g["ask"]["options"]]
        check("ask: her exact descriptions (the editor's bugs line, the widget as the original flow)", descs == [
            "Your whole reel on one page in your browser: more visual control, faster results, fewer tokens. "
            "Bugs are still being worked out.",
            "The original Reels Editing Engine flow: the exact style plan from your course videos."], descs)
        # editor
        out = rg.pick(job, "editor")
        check("editor: nothing saved until she answers", state["learned"] == [], state)
        check("editor: the reel is locked to the editor", review_route.get(job) == "editor")
        check("editor: new default or just this once, as one pick-one in her words", out["step"] == "default"
              and out["ask"]["question"] == rg.DEFAULT_Q and out["ask"]["multiSelect"] is False
              and [o["label"] for o in out["ask"]["options"]] == ["Make the visual editor my new default", "Let me try it once before deciding"], out)
        check("editor: the default question's exact descriptions", [o["description"] for o in out["ask"]["options"]] == [
            "Every rough cut opens in the visual editor. Ask for the original widget anytime to switch back.",
            "The visual editor for this reel only. I'll ask again after your next rough cut."], out)
        out = rg.set_default(job, "once")
        check("once: nothing saved, the question comes back next reel", state["learned"] == [] and out["step"] == "register", (state, out))
        out = rg.set_default(job, "always")
        check("always: the visual editor becomes her default", state["learned"] == ["visual"], state)
        try:
            rg.set_default(job, "sometimes"); check("bad default answer refused", False)
        except ValueError:
            check("bad default answer refused", True)
        check("editor: teaching or confessional comes next, her words' lean recommended",
              out["step"] == "register" and out["ask"]["question"].startswith("Before I open your editor")
              and out["ask"]["options"][0]["label"] == "Teaching (Recommended)", out)
        # register, walk-through
        r = rg.register(job, "teaching")
        check("register: recorded on the reel", choices.read(job).get("register") == "teaching", choices.read(job))
        check("register: walk-through opens the editor next", r["step"] == "open" and "visual_editor.py open the-pricing-one" in r["then"], r)
        said = json.dumps([out, r]).lower()
        check("editor: never asked how done (the doneness pick-one is the original widget's)",
              not any(w in said for w in ("doneness", "well-done", "how done", "raw / medium")), said[:300])
        # saved visual: no review question, and no second message
        state.update(mode="visual", saved="visual", learned=[])
        check("saved visual: straight to the register question", rg.gate(job)["step"] == "register")
        check("saved visual: picking the editor by name never re-asks the default", rg.pick(job, "editor")["step"] == "register")
        # her words: the widget while the editor is her default = back for good
        out = rg.pick(job, "widget")
        check("widget while the editor is her default: switched back for good, said in her words",
              state["learned"] == ["text"] and out.get("say") == rg.SWITCHED_TO_WIDGET and review_route.get(job) == "widget", (state, out))
        # saved text
        state.update(mode="text", saved="text", learned=[])
        check("saved text: straight to the widget", rg.gate(job)["step"] == "widget")
        check("saved text: still says the editor is there anytime", rg.gate(job).get("say") == rg.EDITOR_ANYTIME
              and "open my visual editor" in rg.EDITOR_ANYTIME, rg.gate(job))
        # ask → widget = this reel only
        state.update(mode="ask", saved="ask", learned=[])
        out = rg.pick(job, "widget")
        check("widget from ask: this reel only, nothing saved", state["learned"] == [] and out["step"] == "widget" and not out.get("say"), (state, out))
        # the old keep-using-it question is gone: finishing a reel in the editor already made it her default
        state.update(mode="keep", saved="ask", learned=[])
        check("keep: no second question, the normal review pick", rg.gate(job)["step"] == "review")
        # autopilot: no stop after the cut, the editor opens on her visuals
        r = rg.start_pick("autopilot")
        check("autopilot: picked before the cut", r["step"] == "autopilot" and "--autopilot" in r["then"], r)
        g = rg.gate(job)
        check("autopilot: no question after the cut, the editor opens on her visuals", g["step"] == "autopilot" and "open the-pricing-one --autopilot" in g["then"], g)
        # bad input
        try:
            rg.pick(job, "sideways"); check("bad pick refused", False)
        except ValueError:
            check("bad pick refused", True)
        # the stitch names the gate
        sh = open(os.path.join(ENGINE, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh"), encoding="utf-8").read()
        tail = "\n".join(sh.strip().splitlines()[-4:])
        check("stitch: it ends by naming the review gate, until she has picked her review", "product/review_gate.py $JOB_NAME" in tail
              and 'review/route.json' in tail, tail)
    finally:
        choices.ROOT, first_use.STATE, rg._mode, rg._saved, rg._learn, rg.autopilot_ready = real
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_review_gate: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_review_gate: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
