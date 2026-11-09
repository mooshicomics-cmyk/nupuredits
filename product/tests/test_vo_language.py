#!/usr/bin/env python3
"""The voiceover transcriber hears the creator's language instead of assuming English.

THE BUG THIS EXISTS FOR. vo-cutgrid.py passed language="en" to WhisperX three times over (loading the
model, transcribing, loading the aligner) before hearing a second of audio. Whisper does not argue with
that: told a Spanish voiceover is English, it TRANSLATES it, and the karaoke captions then show words the
creator never said. REELS_ENGINE_LANGUAGE, the override the rough cut honours, was ignored on both routes.
Now the language is detected (or forced by that override), the words are aligned with THAT language's
model, a language with no aligner falls back to faster-whisper (which times words itself), and anything
other than English is said out loud. The rough cut's own guard (test_language_never_pinned.py) does not
cover this file.

How it is checked: a copy of vo-cutgrid.py runs against stand-in `whisperx` and `faster_whisper` modules
that record the language every call was given and answer in the language they "heard". No model, no
download, about a second per case. The source is also checked for a literal language on any call.

Run: python3 product/tests/test_vo_language.py
"""
import json, os, re, shutil, subprocess, sys, tempfile, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "product", "vo-cutgrid.py")
JOB = "j"          # the throwaway job's folder name
fails = []

WHISPERX = r'''
import json, os
def _log(**kw):
    with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f: f.write(json.dumps(kw) + "\n")
class _Model:
    def transcribe(self, audio, batch_size=8, language=None, **kw):
        _log(call="transcribe", language=language)
        return {"language": language or os.environ["STUB_HEARD"], "segments": [{"start": 0.0, "end": 1.0, "text": "x"}]}
def load_model(name, device, compute_type=None, language=None, **kw):
    _log(call="load_model", language=language); return _Model()
def load_audio(path): return [0.0] * 16000
def load_align_model(language_code=None, device=None, **kw):
    _log(call="load_align_model", language=language_code)
    if language_code in os.environ.get("STUB_NO_ALIGN", "").split(","):
        raise ValueError(f"No default align-model for language: {language_code}")
    return ("model", {"language": language_code})
WORDS = {"es": ["hola", "mundo."], "en": ["hello", "world."], "fr": ["bonjour", "monde."]}
def align(segments, model, meta, audio, device, return_char_alignments=False):
    ws = WORDS.get(meta["language"], ["??", "??."])
    return {"segments": [{"words": [{"word": ws[0], "start": 0.1, "end": 0.4}, {"word": ws[1], "start": 0.5, "end": 0.9}]}]}
'''
FASTER_WHISPER = r'''
import json, os
def _log(**kw):
    with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f: f.write(json.dumps(kw) + "\n")
class _W:
    def __init__(s, w, a, b): s.word, s.start, s.end = w, a, b
class _S:
    def __init__(s, words): s.words = words
class _I:
    def __init__(s, lang): s.language = lang
class WhisperModel:
    def __init__(self, name, device=None, compute_type=None, **kw): _log(call="fw_model", name=name)
    def transcribe(self, wav, word_timestamps=True, beam_size=5, language=None, **kw):
        _log(call="fw_transcribe", language=language)
        return iter([_S([_W(" hola", 0.1, 0.4), _W(" mundo.", 0.5, 0.9)])]), _I(language or os.environ["STUB_HEARD"])
'''


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def run(heard, forced=None, no_align="", model_args=()):
    """Run a copy of vo-cutgrid.py on one second of silence. Returns (calls, grid, output text, exit code)."""
    t = tempfile.mkdtemp()
    try:
        for d in (("eng", "product"), ("eng", "projects", JOB, "audio"), ("stubs",), ("venv", "bin")):
            os.makedirs(os.path.join(t, *d))
        shutil.copy(SRC, os.path.join(t, "eng", "product", "vo-cutgrid.py"))
        with wave.open(os.path.join(t, "eng", "projects", JOB, "audio", "vo.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0" * 16000)
        for name, body in (("whisperx.py", WHISPERX), ("faster_whisper.py", FASTER_WHISPER)):
            with open(os.path.join(t, "stubs", name), "w", encoding="utf-8") as fh:
                fh.write(body)
        # a stand-in WhisperX venv: its "python" is this interpreter with the stubs on the path
        with open(os.path.join(t, "venv", ".deps-ok"), "w", encoding="utf-8") as fh:
            fh.write("ok")
        py = os.path.join(t, "venv", "bin", "python")
        with open(py, "w", encoding="utf-8") as fh:
            fh.write(f'#!/bin/sh\nPYTHONPATH="{t}/stubs" exec "{sys.executable}" "$@"\n')
        os.chmod(py, 0o755)
        log = os.path.join(t, "log.jsonl")
        open(log, "w", encoding="utf-8").close()
        env = dict(os.environ, STUB_LOG=log, STUB_HEARD=heard, STUB_NO_ALIGN=no_align, HOME=t,
                   REELS_ENGINE_WHISPERX_VENV=os.path.join(t, "venv"), PYTHONPATH=os.path.join(t, "stubs"))
        env.pop("REELS_ENGINE_LANGUAGE", None)
        if forced:
            env["REELS_ENGINE_LANGUAGE"] = forced
        r = subprocess.run([sys.executable, os.path.join(t, "eng", "product", "vo-cutgrid.py"), "--job", JOB,
                            *model_args], capture_output=True, text=True, env=env)
        with open(log, encoding="utf-8") as fh:
            calls = [json.loads(line) for line in fh if line.strip()]
        gp = os.path.join(t, "eng", "projects", JOB, "vo-grid.json")
        grid = {}
        if os.path.exists(gp):
            with open(gp, encoding="utf-8") as fh:
                grid = json.load(fh)
        return calls, grid, r.stdout + r.stderr, r.returncode
    finally:
        shutil.rmtree(t, ignore_errors=True)


def langs(calls, name):
    return [c.get("language") for c in calls if c["call"] == name]


def main():
    if os.name == "nt":
        print("SKIP: the stand-in WhisperX venv is a shell script (Mac/Linux); the logic under test is the same")
        sys.exit(0)

    calls, grid, out, rc = run("es")
    check("a Spanish voiceover: the model is loaded without a language", langs(calls, "load_model") == [None], str(calls))
    check("a Spanish voiceover: transcription detects the language", langs(calls, "transcribe") == [None], str(calls))
    check("a Spanish voiceover: words are aligned with the Spanish model", langs(calls, "load_align_model") == ["es"], str(calls))
    check("a Spanish voiceover: the grid holds the Spanish words", grid.get("transcript") == "hola mundo.", str(grid.get("transcript")))
    check("a Spanish voiceover: it says it heard Spanish", "heard es, not English" in out, out[-400:])

    calls, grid, out, rc = run("es", forced="fr")
    check("REELS_ENGINE_LANGUAGE forces every call", langs(calls, "load_model") == ["fr"]
          and langs(calls, "transcribe") == ["fr"] and langs(calls, "load_align_model") == ["fr"], str(calls))
    check("REELS_ENGINE_LANGUAGE is announced", "language forced to fr by REELS_ENGINE_LANGUAGE" in out, out[-400:])

    calls, grid, out, rc = run("en")
    check("an English voiceover: aligned in English, English words", langs(calls, "load_align_model") == ["en"]
          and grid.get("transcript") == "hello world.", str(calls))
    check("an English voiceover: nothing extra is said about language", "not English" not in out and "forced" not in out, out[-400:])

    calls, grid, out, rc = run("xx", no_align="xx")
    check("a language with no aligner falls back to faster-whisper (which times words itself)",
          rc == 0 and [c["call"] for c in calls][-2:] == ["fw_model", "fw_transcribe"]
          and grid.get("transcript") == "hola mundo.", str(calls) + out[-300:])

    calls, grid, out, rc = run("es", forced="de", model_args=("--model", "small"))
    check("the faster-whisper route honours REELS_ENGINE_LANGUAGE", langs(calls, "fw_transcribe") == ["de"], str(calls))
    calls, grid, out, rc = run("es", model_args=("--model", "small"))
    check("the faster-whisper route detects when nothing is forced", langs(calls, "fw_transcribe") == [None], str(calls))

    # source-level: no call carries a literal language any more (comments explain the old bug on purpose)
    with open(SRC, encoding="utf-8") as fh:
        code = [line.split("#", 1)[0] for line in fh]
    pinned = [line.strip() for line in code if re.search(r"""language(?:_code)?\s*=\s*['"][a-z]{2}['"]""", line)]
    check("vo-cutgrid.py pins no language anywhere", not pinned, str(pinned))

    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
