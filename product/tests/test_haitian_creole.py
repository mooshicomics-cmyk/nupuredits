#!/usr/bin/env python3
"""Haitian Creole (Kreyòl ayisyen, Whisper code "ht"): heard, cut and put on screen in Kreyòl.

1. HEARD. WhisperX transcribes ht but has no word aligner for it, and no openly licensed one exists (the Kreyòl
   CTC models are MMS, CC BY-NC). The listener used to stop with exit 1 on such a language, which the shell side
   reads as "WhisperX cannot run on this computer": it marked the machine and sent every later reel, English ones
   too, to faster-whisper. Now the listener stops with its own code (NO_ALIGNER, 4) and leaves the language it
   heard and the model it was using; the shell side hears that reel alone with faster-whisper (which times each
   word itself) in that language and on that model, and marks nothing.
2. CUT. Kreyòl fillers (eee, ehm, enben, alò, donk, anfen, antouka...) go when a fragment is ALL filler, Kreyòl
   slate talk ("oke, en de twa, aksyon") goes before the first line, and real short lines stay.
3. ON SCREEN. A Kreyòl transcript reads as not English; a Kreyòl hook does not read as English (it used to: few
   accents, and no Kreyòl function word was known), an English hook on a Kreyòl reel is named, and the reel's
   language is said as "Haitian Creole". The letters themselves (è ò à) are checked in test_script_fonts.py.

Stand-ins only: no model, no download, no network. The listener part needs ffmpeg and numpy and is skipped (said)
without them. Not proven on a real Kreyòl clip.

Run: python3 product/tests/test_haitian_creole.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

for stream in (sys.stdout, sys.stderr):   # ✓ and ò need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ROUGH = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
WT = os.path.join(ROUGH, "word-timings.sh")
sys.path.insert(0, os.path.join(ROOT, "product"))
sys.path.insert(0, ROUGH)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[:400]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wt_source():
    with open(WT, encoding="utf-8") as fh:
        return fh.read()


def pieces(*names):
    """Each `name() {...}` function or `NAME=` line, exactly as written in word-timings.sh."""
    src = wt_source()
    out = []
    for name in names:
        if name.endswith("()"):
            i = src.index("\n" + name + " {") + 1
            out.append(src[i:src.index("\n}\n", i) + 3])
        else:
            i = src.index("\n" + name) + 1
            out.append(src[i:src.index("\n", i) + 1])
    return "\n".join(out)


# ── 1a. the shell side: exit 4 hears this reel with faster-whisper and marks nothing ─────────────────────────

def shell_part():
    if not shutil.which("bash"):
        print("  (shell part skipped: no bash here)")
        return
    tmp = tempfile.mkdtemp(prefix="ht-listen-")
    try:
        venv = os.path.join(tmp, "whisperx-venv")
        os.makedirs(venv)
        log = os.path.join(tmp, "calls.log")
        scratch = os.path.join(tmp, "words.json")

        def listen(sidecar, rc=4, can_hear=True, env_model=""):
            if os.path.exists(log):
                os.remove(log)
            stubs = f'''
VENV="{venv}"; LOG="{log}"; SCRATCH_WORDS="{scratch}"; NOFW=0
{"export REELS_ENGINE_WHISPER_MODEL=" + env_model if env_model else "unset REELS_ENGINE_WHISPER_MODEL"}
call() {{ echo "$*" >> "$LOG"; }}
listen_whisperx() {{ call whisperx; printf '{sidecar}' > "$SCRATCH_WORDS.no-aligner"; return {rc}; }}
listen_faster_whisper() {{ call "faster-whisper heard=$REELS_ENGINE_HEARD_LANGUAGE model=$REELS_ENGINE_WHISPER_MODEL reason=$REELS_ENGINE_NOFW_REASON"; return 0; }}
pivot_to_faster_whisper() {{ call "pivot: $1"; return 0; }}
can_hear_without_whisperx() {{ return {0 if can_hear else 1}; }}
retry_on_measured_set() {{ return 1; }}
note_newer_set_heard() {{ :; }}
note_fallback() {{ call "log: $1"; }}
'''
            script = stubs + pieces("FW_ONLY_MARK=", "listen_faster_whisper_here()", "listen()") + "listen\n"
            r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
            calls = []
            if os.path.exists(log):
                with open(log, encoding="utf-8") as fh:
                    calls = fh.read().split("\n")[:-1]
            return r.returncode, calls, r.stderr

        rc, calls, err = listen("ht\\nlarge-v3\\n")
        check("exit 4 (no aligner): the reel is heard with faster-whisper and the cut goes on", rc == 0, err[-300:])
        check("it is heard in the language WhisperX heard, on the model WhisperX was using",
              any(c.startswith("faster-whisper heard=ht model=large-v3 reason=no word aligner for ht") for c in calls),
              str(calls))
        check("the computer is NOT marked: the next reel gets WhisperX again",
              not os.path.exists(os.path.join(venv, ".whisperx-crashed")) and not any(c.startswith("pivot") for c in calls),
              str(calls))
        check("one line goes in the fallbacks log, naming the language",
              any(c.startswith("log: no word aligner for ht") and "not marked" in c for c in calls), str(calls))
        check("it says what happens in plain words", "faster-whisper" in err and "same cut" in err, err[-400:])

        rc, calls, err = listen("ht\\r\\nlarge-v3\\r\\n")
        check("a Windows-written note (CRLF) reads the same",
              any(c.startswith("faster-whisper heard=ht model=large-v3 ") for c in calls), str(calls))

        rc, calls, err = listen("ht\\n\\n")
        check("on a GPU (no model in the note) faster-whisper picks its own processor model",
              any(c.startswith("faster-whisper heard=ht model= ") for c in calls), str(calls))

        rc, calls, err = listen("ht\\nlarge-v3\\n", env_model="medium")
        check("a model she set herself (REELS_ENGINE_WHISPER_MODEL) still wins",
              any(c.startswith("faster-whisper heard=ht model=medium ") for c in calls), str(calls))

        rc, calls, err = listen("ht\\nlarge-v3\\n", can_hear=False)
        check("with no faster-whisper here, exit 4 stops as it is (never marks the computer)",
              rc == 4 and not os.path.exists(os.path.join(venv, ".whisperx-crashed")), f"{rc} {calls}")

        rc, calls, err = listen("", rc=1)
        check("exit 1 (a real WhisperX error) still marks the computer, as before",
              rc == 0 and os.path.exists(os.path.join(venv, ".whisperx-crashed")), f"{rc} {calls}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 1b. the listener itself: ht has no aligner, so it stops with NO_ALIGNER and leaves its note ─────────────────

STUB_WHISPERX = r'''
import json, os
def _log(**kw):
    with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f: f.write(json.dumps(kw) + "\n")
class _Model:
    def transcribe(self, audio, batch_size=8, language=None, **kw):
        _log(call="transcribe", language=language)
        return {"language": language or os.environ["STUB_HEARD"],
                "segments": [{"start": 0.0, "end": 0.9, "text": "bonjou tout moun"}]}
def load_model(name, device, compute_type=None, language=None, **kw):
    _log(call="load_model", model=name); return _Model()
def load_align_model(language_code=None, device=None, model_name=None, **kw):
    _log(call="load_align_model", language=language_code)
    if language_code not in ("en", "fr", "es"):     # WhisperX's own refusal for a language it has no aligner for
        raise ValueError(f"No default align-model for language: {language_code}")
    return object(), {"language": language_code}
def align(segments, model, meta, audio, device, return_char_alignments=False):
    return {"segments": [{"words": [{"word": "hello", "start": 0.1, "end": 0.4, "score": 0.9}]}]}
'''

STUB_TORCH = "class cuda:\n    @staticmethod\n    def is_available(): return False\n"


def listener_source():
    src = wt_source()
    start = src.index("\n", src.index('"$PYBIN" - "$SCRATCH_WORDS" "${CLIPS[@]}"')) + 1
    return src[start:src.index("\nPY\n", start) + 1]


def listener_part():
    if not shutil.which("ffmpeg"):
        print("  (listener part skipped: ffmpeg not installed)")
        return
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("  (listener part skipped: numpy not installed for this Python)")
        return
    tmp = tempfile.mkdtemp(prefix="ht-listener-")
    try:
        stubs = os.path.join(tmp, "stubs")
        os.makedirs(stubs)
        with open(os.path.join(stubs, "whisperx.py"), "w", encoding="utf-8") as fh:
            fh.write(STUB_WHISPERX)
        with open(os.path.join(stubs, "torch.py"), "w", encoding="utf-8") as fh:
            fh.write(STUB_TORCH)
        clip = os.path.join(tmp, "take.wav")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=1",
                        "-ar", "16000", "-ac", "1", clip], check=True)
        code = listener_source()

        def run(heard, forced=""):
            out = os.path.join(tmp, "out", "words.json")
            shutil.rmtree(os.path.dirname(out), ignore_errors=True)
            os.makedirs(os.path.dirname(out))
            slog = os.path.join(tmp, "stub.log")
            if os.path.exists(slog):
                os.remove(slog)
            env = dict(os.environ, PYTHONPATH=stubs, STUB_LOG=slog, STUB_HEARD=heard,
                       REELS_ENGINE_WHISPER_DEVICE="cpu", REELS_ENGINE_WHISPER_MODEL="stand-in-model",
                       REELS_ENGINE_LANGUAGE=forced)
            r = subprocess.run([sys.executable, "-", out, clip], input=code, capture_output=True, text=True,
                               env=env, timeout=120, encoding="utf-8")
            calls = []
            if os.path.exists(slog):
                with open(slog, encoding="utf-8") as fh:
                    calls = [json.loads(line) for line in fh if line.strip()]
            note = None
            if os.path.exists(out + ".no-aligner"):
                with open(out + ".no-aligner", encoding="utf-8", newline="") as fh:
                    note = fh.read()
            return r.returncode, calls, note, os.path.exists(out), r.stderr

        rc, calls, note, wrote, err = run("ht")
        check("listener: a clip heard as ht stops with NO_ALIGNER (4), not 1", rc == 4, f"rc {rc} {err[-400:]}")
        check("listener: it leaves the language and the model it was using, one per line (\\n even on Windows)",
              note == "ht\nstand-in-model\n", repr(note))
        check("listener: no untimed words.json is written", not wrote)
        check("listener: it says why in one plain line", "no word-alignment model for ht" in err
              and "faster-whisper hears this reel instead" in err, err[-400:])

        rc, calls, note, wrote, err = run("ht", forced="ht")
        check("listener: ht forced by her stops before hearing the clip twice",
              rc == 4 and not any(c["call"] == "transcribe" for c in calls) and note == "ht\nstand-in-model\n",
              f"rc {rc} {calls} {note!r}")

        rc, calls, note, wrote, err = run("en")
        check("listener: an English clip is aligned and written as before", rc == 0 and wrote and note is None,
              f"rc {rc} {err[-400:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 1c. faster-whisper hears the whole clip in the language WhisperX heard ───────────────────────────────────

def nofw_part():
    keys = ("REELS_ENGINE_LANGUAGE", "REELS_ENGINE_HEARD_LANGUAGE")
    saved = {k: os.environ.get(k) for k in keys}
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = object
    sys.modules["faster_whisper"] = fake

    class Model:
        def __init__(self):
            self.kw = None

        def transcribe(self, path, **kw):
            self.kw = kw
            return iter([]), types.SimpleNamespace(duration=1.0, language=kw.get("language"))

    def heard_with(forced, heard):
        for k, v in zip(keys, (forced, heard)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        mod = load("transcribe_nofw_ht", os.path.join(ROOT, "scripts", "transcribe-nofw.py"))
        m = Model()
        mod.transcribe(m, "clip.mov")
        return m.kw

    try:
        kw = heard_with(None, "ht")
        check("faster-whisper: a reel handed over as ht is heard in ht, the whole clip",
              kw.get("language") == "ht" and not kw.get("multilingual"), str(kw))
        kw = heard_with(None, None)
        check("faster-whisper: with nothing handed over it still decides per segment",
              kw.get("language") is None and kw.get("multilingual") is True, str(kw))
        kw = heard_with("fr", "ht")
        check("faster-whisper: the language she named wins over the one handed over", kw.get("language") == "fr", str(kw))
    finally:
        sys.modules.pop("faster_whisper", None)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── 1d. no aligner is pinned for ht, and the reason is written down ──────────────────────────────────────────

def source_part():
    src = wt_source()
    block = src[src.index("_EXTRA_ALIGNERS = {"):src.index("\n}\n", src.index("_EXTRA_ALIGNERS = {"))]
    check("no ht aligner is pinned (none is openly licensed)", '"ht":' not in block)
    check("why there is none is written beside the pinned ones", "Haitian Creole" in block and "CC BY-NC" in block)


# ── 2. the cut ───────────────────────────────────────────────────────────────────────────────────────────────

def cut_part():
    tc = load("transcript_cut_ht", os.path.join(ROUGH, "transcript-cut.py"))

    def drops(lines):
        S, t = [], 0.0
        for line in lines:
            sent = []
            for w in line.split():
                sent.append((w, t, t + 0.3))
                t += 0.35
            S.append(sent)
            t += 1.0
        T = [tc.toks(s) for s in S]
        d = tc.drop_set(S, T)
        return [lines[i] for i in sorted(d)]

    lines = ["Oke, en de twa, aksyon.",                 # slate before the first line: goes
             "An nou pale de lajan jodi a.",             # her first real line: stays
             "Ehm, enben.",                              # all filler: goes
             "Mwen la.",                                 # a real two-word line ("I'm here"): stays
             "Alò, donk.",                               # all filler: goes
             "Alò nou kòmanse ak premye leson an.",      # starts with a filler word, but real: stays
             "Eee.",                                     # hesitation: goes
             "Anfen, antouka.",                          # "anyway": goes
             "Wi, dakò.",                                # "yeah, okay": goes, like the English pair
             "Pa fè erè sa a.",                          # real: stays
             "Li bon."]                                  # real ("it's good"): stays
    got = drops(lines)
    check("Kreyòl: slate talk, filler-only fragments and hesitations go",
          got == ["Oke, en de twa, aksyon.", "Ehm, enben.", "Alò, donk.", "Eee.", "Anfen, antouka.", "Wi, dakò."], str(got))
    nfd = "Alo\u0300, ehm."                          # o + a combining grave, as some keyboards write it
    check("Kreyòl: a filler written with a combining accent is the same filler", drops(["Mwen la.", nfd]) == [nfd],
          str(drops(["Mwen la.", nfd])))
    check("Kreyòl: a real opener made of common words is never taken for a slate",
          drops(["Nou pral pale de bagay sa a.", "Mwen la."]) == [])


# ── 3. on screen ─────────────────────────────────────────────────────────────────────────────────────────────

KREYOL = ("Bonjou tout moun. Jodi a mwen vle pale avèk nou sou yon bagay ki enpòtan anpil. Paske anpil moun pa "
          "konnen kijan pou yo kòmanse. Mwen te konn panse menm jan an tou, men kounye a mwen konnen sa pou nou fè. "
          "Premye bagay la se chak jou, ou dwe pran yon ti tan pou ou menm. Epi apre sa, n ap wè kòman pou nou "
          "jwenn lajan pou fanmi nou.")
ENGLISH = ("Today I want to talk to you about something that really matters, because a lot of moms do not know "
           "where to start. I used to think the same way, but now I know what we need to do. The first thing is "
           "every single day you take a little time for yourself, and after that we look at how to bring money in.")


def screen_part():
    import transcript_language as TL
    import plan_language as PL
    r = TL.classify(KREYOL.split(), dictionary=set())
    check("a Kreyòl transcript reads as not English", r["verdict"] == "non_english" and not r["english_only_checks_ok"],
          str(r))
    r = TL.classify(ENGLISH.split(), dictionary=set())
    check("an English transcript still reads as English (the Kreyòl words do not trip it)",
          r["verdict"] == "english", str(r))
    check("a Kreyòl hook with no accent does not read as English",
          not TL.copy_reads_as_english(["Sa ou pa konnen sou lajan"]))
    check("nor does a Kreyòl card with accents", not TL.copy_reads_as_english(["Kòman pou w kòmanse"]))
    check("an English hook still reads as English", TL.copy_reads_as_english(["The money secret nobody tells you"]))
    check("the reel's language is said as Haitian Creole", PL.language_name("ht") == "Haitian Creole")

    tmp = tempfile.mkdtemp(prefix="ht-plan-")
    try:
        job = os.path.join(tmp, "kreyol-test")
        os.makedirs(os.path.join(job, "outputs"))
        with open(os.path.join(job, "outputs", "kreyol-test.transcript.json"), "w", encoding="utf-8") as fh:
            json.dump({"language_code": "ht", "language_verdict": "non_english",
                       "words": [{"text": w} for w in KREYOL.split()]}, fh, ensure_ascii=False)

        def plan(*copy):
            with open(os.path.join(job, "graphics-plan.json"), "w", encoding="utf-8") as fh:
                json.dump({"beats": [{"on_screen": c} for c in copy]}, fh, ensure_ascii=False)
            return PL.check(job)

        check("a Kreyòl reel with Kreyòl cards says nothing",
              plan("Sa ou pa konnen sou lajan", "Kòman pou w kòmanse") is None)
        warn = plan("The money secret nobody tells you", "How to start today")
        check("a Kreyòl reel with English cards is named, in plain words", bool(warn) and "Haitian Creole" in warn, warn)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("1a. shell side"); shell_part()
    print("1b. listener"); listener_part()
    print("1c. faster-whisper"); nofw_part()
    print("1d. aligners"); source_part()
    print("2. the cut"); cut_part()
    print("3. on screen"); screen_part()
    if fails:
        print(f"\nFAIL: {len(fails)} of {total} check(s) failed")
        sys.exit(1)
    print(f"\n✓ Haitian Creole: heard (faster-whisper times the words, nothing marked), cut, and on screen in Kreyòl "
          f"({total} checks)")


if __name__ == "__main__":
    main()
