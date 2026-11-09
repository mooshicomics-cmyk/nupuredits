#!/usr/bin/env python3
"""A reel she films in Spanish (or French, or Portuguese) hears its spoken effect cues too.

ISS-99: the cue reader's pointing words and effect names were English only, and nothing read the reel's language,
so a Spanish first-reel script ("Aquí va el gancho", "Y esto es una pantalla completa") built no effects at all.
What this pins:

  * the reel's language comes from her transcript (language_code), English when it is unknown
  * Spanish pointing words and effect names are heard, the English effect names are heard on a Spanish reel too
    ("esto es un hook"), and an ordinary Spanish sentence stays talk ("está" is not "esta")
  * a list asked for in one breath ("quiero ver un gancho, ... y una pantalla completa") is heard
  * French and Portuguese lines are heard
  * the rough cut's "this one-word fragment names an effect" exemption knows the other languages' names
  * `spoken_cues.py <job>` itself listens in the transcript's language, end to end

Run: python3 product/tests/test_spoken_cues_language.py
"""
import contextlib, importlib.util, io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
_spec = importlib.util.spec_from_file_location("spoken_cues", os.path.join(ROOT, "product", "spoken_cues.py"))
sc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sc)

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok:
        fails.append(f"{name}  -- {detail}")


def words_for(lines):
    t, out = 0.2, []
    for line in lines:
        for w in line.split():
            out.append({"text": w, "start": round(t, 3), "end": round(t + 0.28, 3)}); t += 0.33
        t += 0.3
    return out


def effects(lines, lang):
    try:
        return [c[0] for c in sc.detect(words_for(lines), lang)]
    except Exception as e:                                   # the old reader took no language at all
        return f"{type(e).__name__}: {e}"


SPANISH_SCRIPT = [
    "Aquí va el gancho.",
    "Aquí abajo van subtítulos de una palabra, una palabra a la vez.",
    "Esta línea es un subtítulo karaoke, así cada palabra se ilumina cuando la digo.",
    "Y esto es una pantalla completa.",
    "Aquí va un contador hasta 300 dólares.",
    "Esto es un zoom rápido para la frase que importa.",
    "Esta se separa en una tarjeta diseñada.",
    "Ese es todo el menú. Ahora haz el tuyo.",
]


def job_with(tmp, name, code, verdict, lines):
    jd = os.path.join(tmp, "projects", name)
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    with open(os.path.join(jd, "outputs", f"{name}.transcript.json"), "w", encoding="utf-8") as fh:
        json.dump({"language_code": code, "language_verdict": verdict, "words": words_for(lines)}, fh, ensure_ascii=False)
    return jd


def test_language_from_transcript():
    tmp = tempfile.mkdtemp(prefix="cue-lang-")
    try:
        got = sc.cue_language(job_with(tmp, "es-job", "es", "non_english", ["Hola."]))
    except Exception as e:
        got = f"{type(e).__name__}: {e}"
    check("language: a Spanish transcript listens in Spanish", got == "es", got)
    got = getattr(sc, "cue_language", lambda jd: None)(job_with(tmp, "en-job", "en", "english", ["Hello."]))
    check("language: an English transcript listens in English", got == "en", got)
    got = getattr(sc, "cue_language", lambda jd: None)(os.path.join(tmp, "projects", "no-such-job"))
    check("language: no transcript falls back to English", got == "en", got)
    got = getattr(sc, "cue_language", lambda jd: None)(job_with(tmp, "de-job", "de", "non_english", ["Hallo."]))
    check("language: a language without its own cue words falls back to English", got == "en", got)


def test_spanish():
    got = effects(SPANISH_SCRIPT, "es")
    check("Spanish: every effect in the script is heard, in order",
          got == ["hook", "single", "karaoke", "takeover", "counter", "punch", "breakaway"], got)
    check("Spanish: the English effect name is heard too", effects(["Esto es un hook."], "es") == ["hook"],
          effects(["Esto es un hook."], "es"))
    check("Spanish: an English punch-in on a Spanish line", effects(["Aquí va un punch-in."], "es") == ["punch"],
          effects(["Aquí va un punch-in."], "es"))
    check("Spanish: a listener that drops the accents still points (aqui)",
          effects(["aqui va una estrella"], "es") == ["star"], effects(["aqui va una estrella"], "es"))
    plain = ["La estrella está brillando hoy.", "Mi marido se fue a trabajar temprano.", "Todo está bien en casa."]
    check("Spanish: ordinary talk stays talk ('está' is not 'esta')", effects(plain, "es") == [], effects(plain, "es"))
    lst = ["Quiero ver un gancho arriba de mi cabeza, subtítulos karaoke y una pantalla completa."]
    check("Spanish: a list asked for in one breath", effects(lst, "es") == ["hook", "karaoke", "takeover"], effects(lst, "es"))
    try:
        w = words_for(SPANISH_SCRIPT)
        plan, _n, _s = sc.build_plan("t", w, sc.detect(w, "es"), None)
        check("Spanish: the hook is her own line", plan.get("hook") == ["Aquí va el gancho"], plan.get("hook"))
        check("Spanish: the full screen is a takeover on her line", plan.get("takeover_keys") == ["y esto es una pantalla completa"],
              plan.get("takeover_keys"))
    except Exception as e:
        check("Spanish: the plan builds", False, f"{type(e).__name__}: {e}")


def test_english_on_an_english_reel_only():
    check("English reel: a Spanish line is not read as a cue", effects(["Aquí va el gancho."], "en") == [],
          effects(["Aquí va el gancho."], "en"))
    check("English reel: the English script is unchanged",
          effects(["This is where the hook goes.", "And this is a full-screen takeover."], "en") == ["hook", "takeover"])


def test_french_and_portuguese():
    fr = ["Voici l'accroche.", "Et ceci est un plein écran.", "Voici une étoile."]
    check("French: hook, takeover, star", effects(fr, "fr") == ["hook", "takeover", "star"], effects(fr, "fr"))
    pt = ["Aqui vai o gancho.", "E isto é uma tela cheia.", "Olha, um balão de pensamento."]
    check("Portuguese: hook, takeover, bubble", effects(pt, "pt") == ["hook", "takeover", "bubble"], effects(pt, "pt"))


def test_rough_cut_exemption():
    reader = getattr(sc, "names_an_effect", None)
    check("rough cut: 'pantalla completa' names an effect", bool(reader and reader("pantalla completa")))
    check("rough cut: 'takeover' still names an effect", bool(reader and reader("takeover")))
    check("rough cut: 'hola' names nothing", bool(reader) and not reader("hola"))
    spec = importlib.util.spec_from_file_location(
        "transcript_cut", os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "transcript-cut.py"))
    tc = importlib.util.module_from_spec(spec)
    argv = sys.argv
    try:
        sys.argv = ["transcript-cut.py"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(tc)
        got = tc.names_an_effect([("estrella", 0.0, 0.3)])
    except BaseException as e:                               # noqa: BLE001
        got = f"{type(e).__name__}: {e}"
    finally:
        sys.argv = argv
    check("rough cut: the cutter keeps a one-word 'estrella'", got is True, got)


def test_main_end_to_end():
    tmp = tempfile.mkdtemp(prefix="cue-main-")
    job_with(tmp, "mi-reel", "es", "non_english", SPANISH_SCRIPT)
    real_root, argv, out = sc.ROOT, sys.argv, io.StringIO()
    try:
        sc.ROOT = tmp
        sys.argv = ["spoken_cues.py", "mi-reel"]
        with contextlib.redirect_stdout(out):
            rc = sc.main()
    except BaseException as e:                               # noqa: BLE001
        rc = f"{type(e).__name__}: {e}"
    finally:
        sc.ROOT, sys.argv = real_root, argv
    text = out.getvalue()
    # six placed; the count-up waits for her footage to be measured (no subject-zones.json here) and says so
    check("main: a Spanish reel's cues are heard", rc == 0 and "6 line(s) name an effect" in text
          and "pantalla completa" in text and "Heard but not placed" in text and "contador" in text, f"{rc} {text[:400]}")
    check("main: says it listened in Spanish", "Spanish" in text, text[:300])


if __name__ == "__main__":
    test_language_from_transcript()
    test_spanish()
    test_english_on_an_english_reel_only()
    test_french_and_portuguese()
    test_rough_cut_exemption()
    test_main_end_to_end()
    if fails:
        print(f"test_spoken_cues_language: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  - " + f)
        sys.exit(1)
    print(f"test_spoken_cues_language: all {total} checks passed")
