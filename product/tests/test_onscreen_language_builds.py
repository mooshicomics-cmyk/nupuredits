#!/usr/bin/env python3
"""The code that builds her on-screen copy says so when that copy is in the wrong language (ISS-14).

A Spanish reel got an English hook. The graphics plan's language check existed, but only SKILL.md told a planner to
run it, so nothing in code ever did. Now the builders call it themselves, as a WARNING (she always gets her reel,
and a bilingual reel can mean its English card):

  * plan_language.check: a reel not in English whose hook / card copy reads as English gets one plain line naming
    the strings and her language; Spanish copy, an English reel, or an unknown language say nothing
  * build-reel-type.py (the rendered type layer) prints it and still builds
  * the visual editor: a hook placed with English copy on a Spanish reel keeps her words and says so (place_at's
    `warn`, and on her page a card from the swap path)
  * the beat sheet, the CapCut builders and place-plan call it

Run: python3 product/tests/test_onscreen_language_builds.py
"""
import importlib.util, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {str(detail)[:400]}")


SPANISH = ("Hoy les quiero contar por qué dejé mi trabajo. Fue la mejor decisión que tomé, pero también la más "
           "difícil, porque tenía miedo de todo lo que podía pasar con mi familia y con el dinero.").split()
ENGLISH = ("Today I want to tell you why I quit my job. It was the best decision I made, and also the hardest one, "
           "because I was scared of everything that could happen with my family and with money.").split()


def make_job(base, name, words, code, verdict, caption_plan=None, graphics_plan=None):
    jd = os.path.join(base, "projects", name)
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    t, out = 0.3, []
    for w in words:
        out.append({"text": w, "start": round(t, 2), "end": round(t + 0.3, 2)}); t += 0.4
    tr = {"words": out}
    if code is not None:
        tr["language_code"] = code
    if verdict is not None:
        tr["language_verdict"] = verdict
    with open(os.path.join(jd, "outputs", f"{name}.transcript.json"), "w", encoding="utf-8") as fh:
        json.dump(tr, fh, ensure_ascii=False)
    for fname, body in (("caption-plan.json", caption_plan), ("graphics-plan.json", graphics_plan)):
        if body is not None:
            with open(os.path.join(jd, fname), "w", encoding="utf-8") as fh:
                json.dump(body, fh, ensure_ascii=False)
    return jd


def load_plan_language():
    try:
        import plan_language
        return plan_language
    except Exception as e:                                   # noqa: BLE001 (the old engine had no such module)
        check("plan_language loads", False, f"{type(e).__name__}: {e}")
        return None


def test_check():
    pl = load_plan_language()
    if pl is None:
        return
    base = tempfile.mkdtemp(prefix="onscreen-lang-")
    try:
        jd = make_job(base, "es-english-hook", SPANISH, "es", "non_english",
                      caption_plan={"hook": ["Three things nobody tells you"], "persistent_label": "my story"})
        line = pl.check(jd)
        check("Spanish reel, English hook: one warning line", bool(line) and "\n" not in line, line)
        check("the warning names her language", bool(line) and "Spanish" in line, line)
        check("the warning names the strings", bool(line) and "Three things nobody tells you" in line and "my story" in line, line)
        check("the warning says it built as written (never a stop)", bool(line) and "built as written" in line, line)

        jd = make_job(base, "es-spanish-hook", SPANISH, "es", "non_english",
                      caption_plan={"hook": ["Lo que nadie te dice"]})
        check("Spanish reel, Spanish hook: nothing to say", pl.check(jd) is None, pl.check(jd))

        jd = make_job(base, "en-reel", ENGLISH, "en", "english", caption_plan={"hook": ["Three things nobody tells you"]})
        check("English reel: nothing to say", pl.check(jd) is None, pl.check(jd))

        jd = make_job(base, "unknown-reel", ["Hola"], None, "unknown", caption_plan={"hook": ["Three things"]})
        check("a reel whose language was never found: nothing to say", pl.check(jd) is None, pl.check(jd))

        jd = make_job(base, "legacy-reel", SPANISH, "en", None, caption_plan={"hook": ["I quit my job"]})
        check("a legacy transcript's bare 'en' is not trusted: the words are re-read", bool(pl.check(jd)), pl.check(jd))

        jd = make_job(base, "plan-reel", SPANISH, "es", "non_english",
                      graphics_plan={"language": {"code": "es", "verdict": "non_english"},
                                     "beats": [{"id": 1, "element": "word-card", "on_screen": "I quit my job",
                                                "idea": "a big kinetic card"}]})
        line = pl.check(jd)
        check("graphics plan: its on_screen copy is read (never its idea)", bool(line) and "I quit my job" in line
              and "kinetic" not in line, line)

        jd = make_job(base, "es-texts", SPANISH, "es", "non_english")
        check("copy the caller places itself is read too", bool(pl.check(jd, texts=["Three things nobody tells you"])))
        check("the editor's short note names her language",
              "Spanish" in (pl.hook_note(jd, "Three things nobody tells you") or ""), pl.hook_note(jd, "Three things"))
        check("the editor's note fits on her page's card", len(pl.hook_note(jd, "Three things nobody tells you") or "") <= 220)
        check("no job folder: nothing, never an error", pl.check(None) is None)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_build_reel_type():
    spec = importlib.util.spec_from_file_location("rtm", os.path.join(HERE, "test_reel_type_matching.py"))
    rtm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rtm)
    base = tempfile.mkdtemp(prefix="onscreen-lang-build-")
    try:
        tmp = os.path.join(base, "e"); rtm.shadow(tmp)
        make_job(tmp, "qa-job", SPANISH, "es", "non_english", caption_plan={"caption_mode": "single", "hook": ["Three things nobody tells you"]})
        r, html = rtm.build(tmp)
        check("build-reel-type: an English hook on a Spanish reel still builds", r.returncode == 0 and "hook=yes" in r.stdout,
              r.stderr[-300:])
        check("build-reel-type: and says so, naming the hook and her language",
              "reads as English" in r.stdout and "Three things nobody tells you" in r.stdout and "Spanish" in r.stdout, r.stdout[-600:])
        make_job(tmp, "qa-job", SPANISH, "es", "non_english", caption_plan={"caption_mode": "single", "hook": ["Lo que nadie te dice"]})
        r, _ = rtm.build(tmp)
        check("build-reel-type: a Spanish hook says nothing", r.returncode == 0 and "reads as English" not in r.stdout, r.stdout[-400:])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_visual_editor():
    import visual_editor as ve
    base = tempfile.mkdtemp(prefix="onscreen-lang-ve-")
    real = (ve.job_dir, ve.word_cut_times, ve._reel_pack, ve.place_look, ve._free_add_key)
    placed = []
    try:
        jd = make_job(base, "mi-reel", SPANISH, "es", "non_english")
        ve.job_dir = lambda job: jd
        ve.word_cut_times = lambda jd: {0: (1.7, 1.85), 1: (1.89, 2.09)}
        ve._reel_pack = lambda jd: "Butter"
        ve._free_add_key = lambda jd, first, look_id=None: f"add-w{first}"
        ve.place_look = lambda job, key, s, e, look, copy=None: placed.append((key, look, copy)) or {"layer": "hook"}
        r = ve.place_at("mi-reel", "hook", 1.7, 2.1, copy="Three things nobody tells you")
        check("place_at: her copy is drawn exactly as written", placed[-1] == ("add-w0", "hook", "Three things nobody tells you"), placed)
        check("place_at: an English hook on a Spanish reel says so", "Spanish" in str((r or {}).get("warn")), r)
        r = ve.place_at("mi-reel", "hook", 1.7, 2.1, copy="Lo que nadie te dice")
        check("place_at: a Spanish hook says nothing", not (r or {}).get("warn"), r)
        r = ve.place_at("mi-reel", "takeover", 1.7, 2.1)
        check("place_at: a look of her own words is never checked", not (r or {}).get("warn"), r)

        menu = os.path.join(jd, "hf-graphics", "_looks", "add-w0", "_menu")
        os.makedirs(os.path.join(menu, "hook"))
        with open(os.path.join(menu, "hook", "look.json"), "w", encoding="utf-8") as fh:
            json.dump({"layer": "hook"}, fh)
        with open(os.path.join(menu, "line.json"), "w", encoding="utf-8") as fh:
            json.dump({"offset": 1.6, "dur": 1.0, "span": [1.7, 2.1]}, fh)
        r = ve.swap("mi-reel", "add-w0", "hook", from_menu=True, copy="Three things nobody tells you")
        check("page swap: her hook is drawn as she typed it", placed[-1] == ("add-w0", "hook", "Three things nobody tells you"), placed)
        says = os.path.join(jd, "review", "claude-says.json")
        msgs = json.load(open(says, encoding="utf-8")).get("messages", []) if os.path.isfile(says) else []
        check("page swap: her page gets one card saying so", len(msgs) == 1 and "Spanish" in msgs[0]["text"], msgs)
    finally:
        ve.job_dir, ve.word_cut_times, ve._reel_pack, ve.place_look, ve._free_add_key = real
        shutil.rmtree(base, ignore_errors=True)


def test_wiring():
    for rel in (".claude/skills/beat-sheet/scripts/beat-sheet.py", "product/cleanyap.py", "product/superyap.py",
                "workflows/capcut-live.py", "product/build-reel-type.py"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            src = fh.read()
        check(f"{rel} checks her on-screen copy's language", "plan_language.warn(" in src)


if __name__ == "__main__":
    test_check()
    test_build_reel_type()
    test_visual_editor()
    test_wiring()
    if fails:
        print(f"test_onscreen_language_builds: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  - " + f)
        sys.exit(1)
    print(f"test_onscreen_language_builds: all {total} checks passed")
