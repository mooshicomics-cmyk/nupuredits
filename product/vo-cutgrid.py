# /// script
# requires-python = ">=3.10"
# dependencies = ["faster-whisper"]
# ///
"""
vo-cutgrid.py — turn a Voiceover Reel's VO audio into a CUT GRID + word-timed caption source.

A VO reel is cut to the VOICE, not to filler-dedup like the Yaps. This transcribes the VO with
word-level timing, then derives the beats a shot should change on: sentence/phrase boundaries and
natural pauses. The same word timings feed the karaoke-build captions (words appear as spoken).

Output: projects/<job>/vo-grid.json
  { "duration": s, "transcript": "...",
    "words":   [{"w","a","b"}...],                     # every word, start/end seconds
    "phrases": [{"text","a","b"}...],                  # grouped on pauses / sentence ends
    "cuts":    [t...] }                                # shot-change times (phrase starts)

Usage:
  uv run product/vo-cutgrid.py --job <job>            # reads projects/<job>/audio/vo.*
  uv run product/vo-cutgrid.py --audio path/to/vo.m4a --job <job>
  options: --model auto|small|medium|large-v3 (default auto) · --pause 0.35 (min gap = a cut, seconds)

--model auto: if the rough-cut lane's WhisperX venv is already installed (set-me-up builds it), transcribe
with WhisperX large-v3 + wav2vec2 word alignment — the same word timing the Yap captions get, so karaoke
captions land ON the word instead of near it. Otherwise fall back to faster-whisper small (self-contained,
downloads once). Name a model explicitly to force faster-whisper.

LANGUAGE is detected from the voice, the same way the rough cut does it, never assumed. Told the audio
was English, Whisper translates a Spanish voiceover instead of transcribing it, and every caption is then
words she never said. REELS_ENGINE_LANGUAGE=<code> (es, fr, ...) forces one when detection gets it wrong.
"""
import argparse, json, os, glob, sys, subprocess, tempfile

# The creator's override, exactly as the rough cut reads it. Empty means detect, which is the default.
FORCED_LANG = os.environ.get("REELS_ENGINE_LANGUAGE", "").strip().lower() or None


def _venv_py(venv):
    """Interpreter inside a venv, whatever this OS named it (bin/ on mac+linux, Scripts/ on Windows).
    Checks what EXISTS rather than guessing by os.name, then falls back to the historic bin/python."""
    for _c in ("Scripts/python.exe", "bin/python", "bin/python3", "Scripts/python3.exe"):
        _p = os.path.join(venv, _c)
        if os.path.exists(_p):
            return _p
    return os.path.join(venv, "bin/python")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _venv_home(leaf):
    """Where the transcription venv lives, including one built under an earlier cache layout.

    A prior build is found by the engine's own completion marker rather than by folder name: the leaf
    is this engine's, so anything carrying it under ~/.cache is ours. That way no past layout has to be
    written down, nobody re-downloads a finished 3-5 GB build, and a fresh install matches nothing and
    gets the current path."""
    import glob
    new = os.path.expanduser(f"~/.cache/reels-editing-engine/{leaf}")
    if os.path.isdir(new):
        return new
    cands = [d for d in glob.glob(os.path.expanduser(f"~/.cache/*/{leaf}")) if os.path.isdir(d)]
    finished = [d for d in cands if any(os.path.exists(os.path.join(d, m)) for m in (".speech-tools-ready", ".deps-ok"))]
    return finished[0] if finished else (cands[0] if cands else new)


def transcribe_whisperx(wav):
    """Word timing from the rough-cut lane's WhisperX venv (large-v3 + wav2vec2 alignment). Returns
    ([{"w","a","b"}, ...], language) or (None, None) when the venv is absent or anything fails — the caller
    falls back. The language is detected from the audio unless REELS_ENGINE_LANGUAGE forces one, and the
    words are aligned with THAT language's model (an English aligner cannot place Spanish words)."""
    venv = os.path.expanduser(os.environ.get("REELS_ENGINE_WHISPERX_VENV", _venv_home("whisperx-venv")))
    py = _venv_py(venv)
    if not (os.path.exists(py) and any(os.path.exists(f"{venv}/{m}") for m in (".speech-tools-ready", ".deps-ok"))):
        return None, None
    out = f"{tempfile.mkdtemp()}/words.json"
    code = r"""
import json, sys, warnings, logging
warnings.filterwarnings("ignore", message=r".*(?i:torchcodec|libtorchcodec|FFmpeg is not properly).*")
for _n in ("torchcodec", "torio", "torio._extension", "torio._extension.utils", "torchaudio", "torchaudio._extension", "torchaudio.utils"):
    logging.getLogger(_n).setLevel(logging.ERROR)
logging.getLogger("whisperx").setLevel(logging.WARNING)      # its INFO chatter (pyannote VAD etc.) is noise to the creator
logging.getLogger("pyannote").setLevel(logging.WARNING)
import whisperx

# Detecting the language makes WhisperX log what it heard, and warn that detection on audio under 30 s "may
# be inaccurate": normal for a voiceover, alarming on a creator's screen. vo-cutgrid names a non-English
# voice itself (with the override to use), so only those lines are held back; the rest prints as before.
class _QuietDetection(logging.Filter):
    def filter(self, rec):
        return not rec.getMessage().startswith(("No language specified", "Audio is shorter than 30s", "Detected language"))
logging.getLogger("whisperx.asr").addFilter(_QuietDetection())

wav, out = sys.argv[1], sys.argv[2]
forced = sys.argv[3] or None            # REELS_ENGINE_LANGUAGE, or "" to detect from the audio
print("[vo-cutgrid] loading whisperx large-v3 (first load of a session takes a few minutes; nothing is stuck)", file=sys.stderr)
model = whisperx.load_model("large-v3", "cpu", compute_type="int8", language=forced)
audio = whisperx.load_audio(wav)
res = model.transcribe(audio, batch_size=8, language=forced)
lang = (forced or res.get("language") or "en").lower()
try:
    am, meta = whisperx.load_align_model(language_code=lang, device="cpu")
except Exception as e:
    print(f"[vo-cutgrid] no word-alignment model for {lang} here ({e})", file=sys.stderr)
    sys.exit(3)
al = whisperx.align(res["segments"], am, meta, audio, "cpu", return_char_alignments=False)
words = []
for seg in al.get("segments", []):
    for w in seg.get("words", []):
        if "start" in w and "end" in w:
            words.append({"w": str(w.get("word", "")).strip(), "a": round(float(w["start"]), 2), "b": round(float(w["end"]), 2)})
json.dump({"language": lang, "words": words}, open(out, "w", encoding="utf-8"))
"""
    # venv_spawn starts it the way that works here: from the Microsoft Store Python the venv's own launcher can
    # stop with "No Python at ..." (exit 103).
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    args = ["-c", code, wav, out, FORCED_LANG or ""]
    # On Windows a torch newer than the pin refuses WhisperX's own voice-detection checkpoint ("Weights only load
    # failed"); the models come from known sources, so torch loads them the way it always did, for this run only
    # (the same as word-timings.sh). A Mac is left as it is.
    env = dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1") if os.name == "nt" else None
    try:
        import venv_spawn
        r = venv_spawn.run(py, args, runner=subprocess.run, step="vo-cutgrid", stderr=subprocess.PIPE, text=True, env=env)
    except ImportError:   # a copy of the engine without the helper starts it directly, as before
        r = subprocess.run([py, *args], stderr=subprocess.PIPE, text=True, env=env)
    if r.returncode != 0 or not os.path.exists(out):
        keep = [l for l in (r.stderr or "").splitlines() if "[vo-cutgrid]" in l or "Error" in l][-3:]
        print("[vo-cutgrid] whisperx path unavailable, falling back to faster-whisper" + (": " + " | ".join(keep) if keep else ""), file=sys.stderr)
        return None, None
    try:
        got = json.load(open(out, encoding="utf-8"))
    except Exception:
        return None, None
    words = got.get("words") if isinstance(got, dict) else got
    return (words or None), (got.get("language") if isinstance(got, dict) else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--model", default="auto")
    ap.add_argument("--pause", type=float, default=0.35)   # gap >= this between words = a cut boundary
    args = ap.parse_args()

    audio = args.audio
    if not audio:
        hits = sum(([*glob.glob(f"{REPO}/projects/{args.job}/audio/vo.{e}")] for e in ("m4a","wav","mp3","aac","mov","mp4","caf")), [])
        if not hits: sys.exit(f"no vo audio in projects/{args.job}/audio/ (expected vo.m4a etc.) — pass --audio")
        audio = hits[0]
    audio = os.path.expanduser(audio)
    if FORCED_LANG:
        print(f"[vo-cutgrid] language forced to {FORCED_LANG} by REELS_ENGINE_LANGUAGE")

    # 16k mono wav for the recognizer
    tmp = tempfile.mkdtemp(); wav = f"{tmp}/vo.wav"
    subprocess.run(["ffmpeg","-v","error","-i",audio,"-map","0:a:0?","-ar","16000","-ac","1","-y",wav], check=True)

    words = []
    lang = None
    engine = "faster-whisper"
    if args.model == "auto":
        words, lang = transcribe_whisperx(wav)            # aligned word timing when the venv exists
        if words: engine = "whisperx large-v3 + alignment"
    if not words:
        words = []
        from faster_whisper import WhisperModel
        model = "small" if args.model == "auto" else args.model
        try:   # cached first: no network question on every load (a broken IPv6 route hangs it)
            m = WhisperModel(model, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            m = WhisperModel(model, device="cpu", compute_type="int8")
        segs, info = m.transcribe(wav, word_timestamps=True, beam_size=5, language=FORCED_LANG)
        for s in segs:
            for w in (s.words or []):
                words.append({"w": w.word.strip(), "a": round(float(w.start), 2), "b": round(float(w.end), 2)})
        engine = f"faster-whisper {model}"
        lang = FORCED_LANG or getattr(info, "language", None)
    if not words:
        sys.exit("no speech detected in the VO")
    print(f"[vo-cutgrid] transcribed with {engine}")
    if lang and lang != "en" and not FORCED_LANG:
        # Say it out loud: a voiceover that came back in the wrong language is otherwise only noticed when
        # the creator reads captions she never said.
        print(f"[vo-cutgrid] heard {lang}, not English — transcribed in {lang}. "
              f"(Wrong? re-run with REELS_ENGINE_LANGUAGE=<code> to force one.)")

    # phrases: break on a pause >= --pause, a sentence end, OR a clause comma/semicolon
    phrases = []; cur = []
    for i, w in enumerate(words):
        if cur:
            gap = w["a"] - words[i-1]["b"]
            brk = words[i-1]["w"][-1:] in ".?!,;:"
            if gap >= args.pause or brk:
                phrases.append(cur); cur = []
        cur.append(w)
    if cur: phrases.append(cur)
    phrases = [{"text": " ".join(x["w"] for x in p), "a": float(p[0]["a"]), "b": float(p[-1]["b"]), "words": p} for p in phrases]
    cuts = [round(float(p["a"]), 2) for p in phrases]

    dur = round(float(words[-1]["b"]), 2)
    out = {"duration": dur, "transcript": " ".join(w["w"] for w in words),
           "words": words, "phrases": phrases, "cuts": cuts}
    outdir = f"{REPO}/projects/{args.job}"; os.makedirs(outdir, exist_ok=True)
    json.dump(out, open(f"{outdir}/vo-grid.json", "w", encoding="utf-8"), indent=2)

    print(f"transcript: {out['transcript']}")
    print(f"\n{len(words)} words · {len(phrases)} phrases · {dur:.1f}s · cut grid at: {cuts}")
    for p in phrases:
        print(f"  {p['a']:>5.2f}-{p['b']:>5.2f}  {p['text']}")
    print(f"\n-> projects/{args.job}/vo-grid.json  (feeds the assembler's cut grid + the karaoke captions)")


if __name__ == "__main__":
    main()
