#!/usr/bin/env python3
"""Guards: the visual editor and autopilot are on in every engine (product/early_access.py), since launch.

  everyone   an engine with no codeword: on, the editor question is asked, the editor's commands run
  codeword   an old saved codeword (the closed christmas test, or any other): still on, nothing changes
  off        REE_EDITOR=0 (tests only): nothing asked before the cut; the rough cut goes straight to the widget;
             picking the editor or autopilot anyway lands on the widget; the editor's commands refuse; a reel once
             locked to the editor is no longer refused by the widget road

Run: python3 product/tests/test_early_access.py
"""
import importlib, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ENGINE = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
os.environ.pop("REE_EDITOR", None)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(name)
        print(f"  FAIL {name} {detail}")


tmp = tempfile.mkdtemp(prefix="ree-early-")
try:
    import early_access
    import review_gate as rg, review_route
    rg_root = getattr(rg, "ROOT", None)

    # everyone: no codeword at all
    check("everyone: on", early_access.editor_on())
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "early_access.py")], capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if k != "REE_EDITOR"})
    check("everyone: the CLI says on", r.returncode == 0 and r.stdout.strip() == "on", r.stdout)
    job2 = os.path.join(tmp, "projects", "b-reel"); os.makedirs(job2)
    check("everyone: the editor question is asked", rg.gate(job2).get("step") in ("review", "register"), str(rg.gate(job2)))

    # an old saved codeword changes nothing
    sys.path.insert(0, os.path.join(ENGINE, "scripts"))
    au = importlib.import_module("apply-update")
    for w in ("christmas", "someotherword"):
        os.makedirs(os.path.join(tmp, "_local"), exist_ok=True)
        json.dump({"channel": au.code_channel(w)}, open(os.path.join(tmp, "_local", "update-code.json"), "w", encoding="utf-8"))
        check(f"codeword {w}: still on", early_access.editor_on())

    # REE_EDITOR=0: the widget-only road still holds together (tests, and what an engine without the editor did)
    os.environ["REE_EDITOR"] = "0"
    check("off: off", not early_access.editor_on())
    check("off: nothing before the cut", rg.start().get("step") == "cut")
    check("off: autopilot pick lands on the cut", rg.start_pick("autopilot").get("step") == "cut")
    job = os.path.join(tmp, "projects", "a-reel"); os.makedirs(job)
    check("off: straight to the widget", rg.gate(job).get("step") == "widget", str(rg.gate(job)))
    check("off: never names the editor", "editor" not in json.dumps(rg.gate(job)).replace("review_route", ""))
    check("off: picking the editor lands on the widget", rg.pick(job, "editor").get("step") == "widget")
    check("off: reel recorded on the widget", review_route.get(job) == "widget")
    review_route.set_route(job, "editor")
    try:
        review_route.refuse_if_editor(job, "the widget"); ok = True
    except SystemExit:
        ok = False
    check("off: a reel once on the editor takes the widget road", ok)
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "visual_editor.py"), "open", "a-reel", "--no-browser"],
                       capture_output=True, text=True, env=dict(os.environ, REE_EDITOR="0"))
    check("off: the editor's commands refuse", r.returncode != 0 and "isn't switched on" in (r.stderr + r.stdout))
    r = subprocess.run([sys.executable, os.path.join(PRODUCT, "visual_editor.py"), "mode"],
                       capture_output=True, text=True, env=dict(os.environ, REE_EDITOR="0"))
    check("off: review mode is the widget", r.stdout.strip() == "text", r.stdout + r.stderr)
    os.environ.pop("REE_EDITOR", None)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
