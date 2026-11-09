#!/usr/bin/env python3
"""verify-cut.py — FAIL-SAFE: re-listen to the RENDERED cut and confirm it actually says what the
plan intends. Catches the class of bug where WhisperX mis-stamps a stumbled/repeated take, so the
transcript reads clean but the cut's word-timestamps point at the wrong audio (the cut plays a
stumble / different words than the plan). transcribe-once alignment can't catch this — only re-hearing
the finished cut can. (Root-caused 2026-08-12: two stumbles cut into a reel this way.)

WHAT IT DOES: re-transcribes outputs/<job>.mp4 with an INDEPENDENT ASR pass (its own timestamps),
then runs two detectors against it:
  A) MISALIGNMENT — the rendered audio diverges (multi-token) from the INTENDED text (the transcript
     field of each cuts.json segment). Catches a cut that plays different words than the plan.
  B) STUMBLE — an immediate repeat in the rendered audio itself ("the thing thing", "everything
     everything"), regardless of whether the plan text also carries it. Intentional spaced repeats
     ("closer and closer") do NOT trigger; the two occurrences must be ADJACENT. Nor does a repeat the
     plan wrote as one hyphenated word ("bye-bye", Bulgarian "много-много").

Usage: python3 verify-cut.py <job_dir> [--model base|small] [--again]
Exit 0 = clean; exit 3 = at least one likely stumble/mismatch to review.
Uses the shared whisperx venv's faster_whisper (already installed for word-timings.sh) — no new deps.

The model, unless --model names one: base on English, small otherwise, but one already downloaded to this
computer is preferred over a download, and a computer with 8 GB of memory or less never gets more than small
(a bigger model there swaps, and one re-listen took the better part of an hour). It says which in one line.

At most MAX_LISTENS full re-listens per script: a fix-and-listen-again loop stops there, and the cut goes to
her with the spots still flagged listed. A later run on the same script skips itself and lists them again.
--again starts a fresh count (a change she asked for after her review is a new script).
"""
import json, os, sys, re, glob, subprocess, difflib, tempfile, unicodedata
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


# The shared record of backup routes (product/fallbacks.py): one log line per switch, and what this computer has
# learned works. A copy of the engine without it still listens back; it only keeps no record.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "product"))
try:
    from fallbacks import note, remember, remembered, forget
except Exception:
    def note(step, message): pass
    def remember(key, value=True, why=""): pass
    def remembered(key, default=None): return default
    def forget(key): pass
try:
    import venv_spawn   # starts the speech tools' Python the way that works here (the Store Python case)
except Exception:
    venv_spawn = None

PY_KEY = "verify-cut.python"   # the interpreter that last heard a cut on this computer
PROBE_TIMEOUT = 90             # seconds for "can this interpreter load faster_whisper?" (a cold start on a PC
                               # with a virus scanner reading every file takes a while; a working one says yes fast)
FFMPEG_TIMEOUT = 300           # seconds to pull the cut's sound out: seconds of work, so past this ffmpeg is stuck
ASR_TIMEOUT = 900              # seconds for the listen-back itself, model download included. A 90 s reel is heard
                               # in well under a minute; the first run on a computer also downloads the model
                               # (~140 MB, ~460 MB for small), and a stalled download used to hold the stitch forever.
MAX_LISTENS = 2                # full re-listens of one script before the cut is handed over with what is left
SAME_SCRIPT = 0.9              # a fix that changes under a tenth of the plan's words is still the same script
LOW_RAM_GB = 8.5               # an "8 GB" computer reports 7.8-8.0; 16 GB ones report 15.x


def _venv_py(venv):
    """Interpreter inside a venv, whatever this OS named it (bin/ on mac+linux, Scripts/ on Windows).
    Checks what EXISTS rather than guessing by os.name, then falls back to the historic bin/python."""
    for _c in ("Scripts/python.exe", "bin/python", "bin/python3", "Scripts/python3.exe"):
        _p = os.path.join(venv, _c)
        if os.path.exists(_p):
            return _p
    return os.path.join(venv, "bin/python")



# common spoken contractions the ASR expands (or doesn't) — normalize both sides so they never false-mismatch
_CONTRACT = {"gonna": "going to", "wanna": "want to", "gotta": "got to", "gimme": "give me",
             "kinda": "kind of", "sorta": "sort of", "outta": "out of", "lemme": "let me",
             "tryna": "trying to", "dunno": "do not know", "gotcha": "got you"}
def norm_tokens(s):
    s = s.lower()
    for k, v in _CONTRACT.items():
        s = re.sub(r"\b" + k + r"\b", v, s)
    # Letters, marks and digits of ANY alphabet are word characters. [a-z0-9] alone turned every word of a
    # Russian, Hindi or Chinese plan into spaces, leaving nothing to hold the audio against (a match on
    # nothing, or a "mismatch" against an empty plan), and split an accented word in two ("más" -> "m",
    # "s"). On ASCII text this is exactly the old [^a-z0-9' ] -> space.
    return [t for t in "".join(c if c in "' " or unicodedata.category(c)[0] in "LMN" else " " for c in s).split()
            if t]


def line_at(t, bounds):
    for end, ln in bounds:
        if t <= end + 0.25:
            return ln
    return bounds[-1][1] if bounds else "?"


def find_problems(intended, itag, rtok, bounds, allowed=()):
    """Pure detector — no I/O. intended = [token], itag = [line#] parallel to intended,
    rtok = [(token, start, end)] from the rendered ASR, bounds = [(cum_end_sec, line#)],
    allowed = repeats not to report as stumbles (see hyphen_repeats).
    Returns a list of flag dicts. Kept pure so it can be unit-tested without running ASR."""
    flags = []
    # DETECTOR A — misalignment (multi-token divergence from the plan)
    rlist = [t for t, _, _ in rtok]
    sm = difflib.SequenceMatcher(None, intended, rlist, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        rspan = rtok[j1:j2]; ispan = intended[i1:i2]
        if len(rspan) < 2 and len(ispan) < 2:
            continue                                    # single-token wobble = ASR noise (Detector B gets real dups)
        istr = " ".join(ispan); rstr = " ".join(t for t, _, _ in rspan)
        if difflib.SequenceMatcher(None, istr, rstr).ratio() > 0.72:
            continue                                    # near-homophone ASR mishear ("what you're"/"what's your"), not a wrong cut
        t0 = rspan[0][1] if rspan else (rtok[j1 - 1][2] if 0 < j1 <= len(rtok) else 0.0)
        flags.append({"line": itag[i1] if i1 < len(itag) else "?", "t": t0, "kind": "mismatch",
                      "intended": " ".join(ispan), "rendered": " ".join(t for t, _, _ in rspan)})
    # DETECTOR B — stumble (adjacent word / bigram / trigram repeat in the rendered audio). The one
    # exception is `allowed`: repeats the plan wrote as ONE hyphenated word ("bye-bye", Bulgarian
    # "много-много"), which norm_tokens splits into two identical tokens but she said on purpose.
    for k, hit in _repeats([t for t, _, _ in rtok]):
        if hit in allowed:
            continue
        t0 = rtok[k][1]
        flags.append({"line": line_at(t0, bounds), "t": t0, "kind": "stumble",
                      "intended": "(spoken once)", "rendered": '"' + hit + '" repeated'})
    return flags


def hyphen_repeats(words):
    """Repeats written as one hyphenated word in the plan ("bye-bye", "много-много"): said on purpose."""
    return {hit for w in words if "-" in w for _, hit in _repeats(norm_tokens(w))}


def _repeats(rt):
    """(index, repeated text) for each adjacent word / bigram / trigram repeat in a token list."""
    out, seen = [], set()
    for k in range(len(rt) - 1):
        hit = None
        if rt[k] == rt[k + 1]:
            hit = rt[k]
        elif k + 3 < len(rt) and rt[k:k+2] == rt[k+2:k+4]:
            hit = " ".join(rt[k:k+2])
        elif k + 5 < len(rt) and rt[k:k+3] == rt[k+3:k+6]:
            hit = " ".join(rt[k:k+3])
        if hit and k not in seen:
            seen.update(range(k, k + 6))
            out.append((k, hit))
    return out


from transcript_language import classify


def _speech_venv_py():
    """The interpreter that has faster_whisper, whichever venv this machine actually built.

    An Intel Mac never builds the whisperx venv — WhisperX needs a torch version with no Intel
    build — so word-timings.sh builds a faster-whisper venv instead, at a different path. This file
    only ever needed faster_whisper, so it works fine there; it just has to LOOK there. Hardcoding
    the whisperx path meant the cut listen-back silently found nothing on an Intel Mac and every
    cut in the job went unchecked, which is the exact failure this script exists to prevent.
    Env overrides win, in the same order word-timings.sh applies them."""
    candidates = [
        os.environ.get("REELS_ENGINE_WHISPERX_VENV"),
        os.environ.get("REELS_ENGINE_NOFW_VENV"),
        os.path.expanduser("~/.cache/reels-editing-engine/whisperx-venv"),
        os.path.expanduser("~/.cache/reels-editing-engine/fasterwhisper-venv"),
        # then any build from an earlier cache layout, found by the engine's ready marker (.speech-tools-ready, or .deps-ok on an older build)
        # rather than by folder name, so nothing has to be re-downloaded and no past name is written
        # down here.
        *[d for leaf in ("whisperx-venv", "fasterwhisper-venv")
          for d in sorted(glob.glob(os.path.expanduser(f"~/.cache/*/{leaf}")))
          if any(os.path.exists(os.path.join(d, m)) for m in (".speech-tools-ready", ".deps-ok"))],
    ]
    found = []
    for venv in candidates:
        if not venv:
            continue
        py = _venv_py(venv)
        if os.path.exists(py) and py not in found:
            found.append(py)
    # The one that heard a cut here before, without asking again, while it is still one of this machine's venvs
    # (an env override or a removed venv takes it out of the running). _retranscribe forgets it if it fails.
    known = remembered(PY_KEY)
    if known in found:
        return known
    # Otherwise the first that can actually load faster_whisper. A venv can exist and still not carry it (a
    # WhisperX build cut off partway, a venv whose torch will not load on this processor), and the old "first
    # one that exists" handed the listen-back an interpreter that failed every time.
    for py in found:
        if _can_listen(py):
            if py != found[0]:
                note("verify-cut", f"{found[0]} could not load faster_whisper; listened back with {py}")
            remember(PY_KEY, py, why="the first interpreter that could load faster_whisper")
            return py
    return None


def _spawn(py, args, **kw):
    """Start the speech tools' Python. Through venv_spawn: from the Microsoft Store Python the venv's own
    launcher can stop with "No Python at ..." (exit 103) before anything is heard."""
    if venv_spawn:
        return venv_spawn.run(py, args, runner=subprocess.run, step="verify-cut", **kw)
    return subprocess.run([py, *args], **kw)


def _can_listen(py):
    try:
        return _spawn(py, ["-c", "import faster_whisper"], capture_output=True,
                      timeout=PROBE_TIMEOUT).returncode == 0
    except Exception:          # timed out, or would not start at all: either way not this one
        return False


# faster-whisper's own names for its models, and where each one is fetched from (its utils._MODELS). The
# transcription step loads the same names (word-timings.sh: large-v3 / medium / small; the Intel Mac route:
# medium / small), into the same Hugging Face cache, so a model it used is already here for the listen-back.
_FW_REPOS = {
    "tiny": "Systran/faster-whisper-tiny", "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small", "medium": "Systran/faster-whisper-medium",
    "large-v2": "Systran/faster-whisper-large-v2", "large-v3": "Systran/faster-whisper-large-v3",
}


def _hub_dir():
    return os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")


def model_cached(name):
    """Is this model fully downloaded here? A finished download has model.bin in a snapshot; a broken-off
    one does not."""
    repo = _FW_REPOS.get(name)
    if not repo:
        return False
    snaps = os.path.join(_hub_dir(), "models--" + repo.replace("/", "--"), "snapshots")
    return bool(glob.glob(os.path.join(snaps, "*", "model.bin")))


def total_ram_gb():
    """This computer's memory in GB, or None. Mac (Apple chip or Intel), Windows and Linux."""
    try:
        if os.name == "nt":
            import ctypes

            class _MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _MEM()
            m.dwLength = ctypes.sizeof(_MEM)
            return m.ullTotalPhys / 2 ** 30 if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=10).stdout
            return int(out.strip()) / 2 ** 30 if out.strip() else None
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except Exception:
        return None


def pick_model(asr_lang, ram_gb=None, cached=None):
    """(model, why) for the listen-back. base is fast and plenty for English; other languages get small, since
    base mishears them so often that most of what it flags is its own ear (9 false spots on a clean 28 s
    Bulgarian cut, 3 with small). A model already on this computer beats a download (the download is what
    failed on a PC whose medium was sitting right there), and 8 GB of memory or less caps it at small."""
    cached = cached or model_cached
    low = ram_gb is not None and ram_gb <= LOW_RAM_GB
    default = "base" if asr_lang == "en" else "small"
    order = ["base", "small", "medium"] if asr_lang == "en" else ["small", "medium"]
    if low:
        order = [m for m in order if m != "medium"]
    for m in order:
        if cached(m):
            if m == default:
                why = "already on this computer"
            else:
                why = f"already on this computer, so nothing to download ({default} is not)"
            break
    else:
        m, why = default, "downloaded once, the first time"
    if low:
        why += f"; {ram_gb:.0f} GB of memory here, so a lighter model keeps this quick"
    return m, why


def _state_path(job_dir):
    return os.path.join(job_dir, "transcript", ".verify-cut-listens.json")


def _load_state(job_dir):
    try:
        with open(_state_path(job_dir), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(job_dir, state):
    try:
        tmp = _state_path(job_dir) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, _state_path(job_dir))
    except Exception:
        pass   # a count that cannot be kept only means the next run listens again


def listens_so_far(job_dir, intended, again=False):
    """How many full re-listens THIS script has had. A fix that moves a segment to the clean take keeps the
    plan's words (or nearly), so it counts toward the same script; a rewritten plan, or --again, starts over."""
    st = _load_state(job_dir)
    if again or not st.get("plan"):
        return 0
    if difflib.SequenceMatcher(None, st["plan"], intended, autojunk=False).ratio() < SAME_SCRIPT:
        return 0
    return int(st.get("listens", 0))


def _flag_lines(flags):
    out = []
    for f in sorted(flags, key=lambda x: x["t"]):
        mark = "STUMBLE (repeated words)" if f["kind"] == "stumble" else "mismatch (audio != plan)"
        out.append(f"  line {f['line']} @ {f['t']:.1f}s [{mark}]")
        out.append(f"      plan says : {f['intended'] or '(nothing here)'}")
        out.append(f"      cut plays : {f['rendered'] or '(missing/dropped)'}")
    return out


def _retranscribe(mp4, model_size, asr_lang="en"):
    """asr_lang is None when the job is not confidently English.

    This listen-back used to force `language="en"` unconditionally. On a Spanish reel that made the
    small `base` model TRANSLATE the audio, and the mismatch report then printed the creator's real
    Spanish beside an English rendering of it, labelled as what her cut plays — 17 times. Every one of
    those 17 was a false alarm about words she had said correctly.
    `multilingual=True` asks faster-whisper to decide per segment instead of once per file; older
    builds lack the argument, hence the TypeError fallback."""
    py = _speech_venv_py()
    wav = os.path.join(tempfile.gettempdir(), f"verify-{os.path.basename(mp4)}.wav")
    # -nostdin: run from a script, ffmpeg otherwise waits on the terminal for keystrokes it never gets.
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", mp4, "-map", "0:a:0?", "-ac", "1", "-ar", "16000", wav],
                   check=True, timeout=FFMPEG_TIMEOUT)
    env = dict(os.environ)
    if os.name == "nt":
        # The model download links files into its cache, and a link on Windows needs Developer Mode or admin
        # rights (WinError 1314): word-timings.sh sets the same. Copies work for everyone.
        env["HF_HUB_DISABLE_SYMLINKS"] = "1"
    code = f'''
import json
from faster_whisper import WhisperModel
try:   # cached first: no network question on every load (a broken IPv6 route hangs it)
    m = WhisperModel({model_size!r}, device="cpu", compute_type="int8", local_files_only=True)
except Exception:
    m = WhisperModel({model_size!r}, device="cpu", compute_type="int8")
_lang = {asr_lang!r}
try:
    segs,_ = m.transcribe({wav!r}, language=_lang, multilingual=(_lang is None), word_timestamps=True)
except TypeError:
    segs,_ = m.transcribe({wav!r}, language=_lang, word_timestamps=True)
out=[]
for s in segs:
    for w in (s.words or []):
        out.append([w.word, round(w.start,3), round(w.end,3)])
print(json.dumps(out))
'''
    asr = (_spawn(py, ["-c", code], capture_output=True, text=True, timeout=ASR_TIMEOUT, env=env) if py else
           subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=ASR_TIMEOUT, env=env))
    if asr.returncode != 0:
        forget(PY_KEY)   # it stopped working: the next listen-back asks every venv again
        raise RuntimeError(f"re-transcribe failed:\n{asr.stderr[-800:]}")
    raw = json.loads(asr.stdout.strip().splitlines()[-1])
    rtok = []
    for word, s, e in raw:
        n = norm_tokens(word)
        if n:
            rtok.append((n[0], s, e))
    return rtok


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: verify-cut.py <job_dir> [--model base|small] [--again]")
    job_dir = os.path.abspath(sys.argv[1]); job = os.path.basename(job_dir.rstrip("/"))
    model_size = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else None
    mp4 = f"{job_dir}/outputs/{job}.mp4"; cuts = f"{job_dir}/transcript/cuts.json"
    for p in (mp4, cuts):
        if not os.path.exists(p):
            sys.exit(f"[verify-cut] missing {p}")
    segs = json.load(open(cuts, encoding="utf-8"))["segments"]
    intended, itag, bounds, acc = [], [], [], 0.0
    for i, s in enumerate(segs, start=1):
        for tok in norm_tokens(s.get("transcript", "")):
            intended.append(tok); itag.append(i)
        acc += (s["end"] - s["start"]) / float(s.get("speed", 1.0) or 1.0); bounds.append((acc, i))
    # Ask the plan's own words what language this job is in before re-listening in English. Use the
    # raw segment text, not `intended` — norm_tokens() has already dropped the ¿ ¡ marks and expanded
    # the contractions, and both are part of the signal.
    _plan_words = " ".join(str(s.get("transcript", "")) for s in segs).split()
    _lang = classify(_plan_words)
    _asr_lang = "en" if _lang["english_only_checks_ok"] else None
    if _asr_lang is None:
        print(f"[verify-cut] transcript is {_lang['verdict']} — re-listening WITHOUT forcing English "
              f"(detecting per segment), so your own words are not reported back as mismatches.",
              file=sys.stderr)
    # The cap: at most MAX_LISTENS full re-listens of one script. Past that the loop (flag, fix, stitch,
    # listen again) only costs her time, so the cut goes over with what is still flagged named for her.
    done = listens_so_far(job_dir, intended, again="--again" in sys.argv)
    if done >= MAX_LISTENS:
        left = _load_state(job_dir).get("flags") or []
        print(f"[verify-cut] this script has had its {MAX_LISTENS} full re-listens, so this one is skipped and the"
              f" cut goes to her as it is." + (" Spots still flagged at the last listen, to name for her:" if left
                                               else " The last listen was clean."))
        for line in left:
            print(line)
        return 3 if left else 0
    if model_size:
        why = "asked for"
    else:
        model_size, why = pick_model(_asr_lang, total_ram_gb())
    print(f"[verify-cut] listening back with the {model_size} model ({why})", file=sys.stderr)
    try:
        rtok = _retranscribe(mp4, model_size, _asr_lang)
    except subprocess.TimeoutExpired as e:
        # Most often the first-time model download on a slow or stalled connection. The cut is already made and
        # this check never holds it back, so it is skipped this once; the next stitch tries again.
        print(f"[verify-cut] the listen-back took longer than {int(e.timeout)} s (usually the first-time model "
              f"download), so it was skipped this time. Your cut is unaffected.", file=sys.stderr)
        note("verify-cut", f"the listen-back of {job} took longer than {int(e.timeout)} s; skipped it, the cut stands")
        return 0
    except Exception as e:
        print(f"[verify-cut] could not re-listen ({e}) — SKIPPED", file=sys.stderr); return 0
    flags = find_problems(intended, itag, rtok, bounds, hyphen_repeats(_plan_words))
    lines = _flag_lines(flags)
    done += 1
    _save_state(job_dir, {"plan": intended, "listens": done, "flags": lines})
    if not flags:
        print(f"[verify-cut] ✓ rendered cut matches the plan, no stumbles ({len(segs)} segments re-heard, model={model_size})")
        return 0
    print(f"[verify-cut] {len(flags)} spot(s) worth a listen (model={model_size}). Most of the time this is the"
          f" transcriber mishearing a word rather than anything wrong with your cut, so check before changing it:")
    for line in lines:
        print(line)
    if done >= MAX_LISTENS:
        print(f"[verify-cut] that was full re-listen {done} of {MAX_LISTENS} for this script, the last one: hand"
              f" the cut over and name these spots for her rather than fixing and listening again.")
    else:
        print("[verify-cut] if one of these really is a stumble: listen to the raw audio at that spot, correct the"
              " cut time, re-splice, and run this again. If it is just a misheard word, nothing needs changing.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
