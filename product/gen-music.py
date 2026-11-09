#!/usr/bin/env python3
"""gen-music.py — generate background-music OPTIONS locally with MusicGen (free, no account, no cloud),
to try a vibe. The model (facebook/musicgen-small) is licensed CC BY-NC 4.0, non-commercial, so these are
for auditioning a mood, not a clearance for a posted reel. Writes short seed clips to projects/<job>/audio/ to audition; the background-music skill and
vo-build.py loop the chosen one to the reel length.

Run it with any python:  python3 product/gen-music.py <job> [seconds] [--vibe "..."] [--check]

It needs no install of its own. MusicGen runs on torch + transformers, which the rough-cut lane's WhisperX
venv already carries on every machine that transcribes with WhisperX, so this script finds that venv and
re-runs itself inside it. (A dedicated product/engine/musicgen-venv, if one exists, is still honored.)
The only first-use cost is the model itself: facebook/musicgen-small, about 2.2 GB, downloaded once.

Where no torch venv exists (the Intel Mac route transcribes with faster-whisper and has no torch), it says
so plainly and exits 3: the creator drops her own track in projects/<job>/audio/ instead.

  --check   report only: which python would run it, and whether the model is already downloaded. Exit 0 =
            ready to generate (model may still need its one-time download), 3 = cannot run on this machine.
  --vibe    describe the mood in words ("bright upbeat acoustic, cozy morning"); three takes of that vibe.
            Without it, three soft/chill defaults that sit under a voice.
"""
import sys, os, argparse, subprocess
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = "facebook/musicgen-small"
MODEL_GB = 2.2
NO_TORCH_EXIT = 3


def _has_torch_here():
    try:
        import torch, transformers  # noqa: F401
        from transformers import MusicgenForConditionalGeneration  # noqa: F401
        return True
    except Exception:
        return False


def _candidate_pythons():
    """Interpreters that can run MusicGen, best first. Uses the same venv lookup the rough-cut lane uses."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from clean_cut import _venv_home, _venv_py
    out = []
    legacy = os.path.join(ROOT, "product", "engine", "musicgen-venv")
    if os.path.isdir(legacy):
        out.append(_venv_py(legacy))
    wx = os.path.expanduser(os.environ.get("REELS_ENGINE_WHISPERX_VENV", _venv_home("whisperx-venv")))
    out.append(_venv_py(wx))
    return [p for p in out if os.path.exists(p)]


def _model_cached():
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    snap = os.path.join(hub, "models--" + MODEL.replace("/", "--"), "snapshots")
    return os.path.isdir(snap) and any(os.scandir(snap))


def _no_torch_message():
    return ("Music generation is not available on this machine: it needs the transcription engine's WhisperX "
            "setup, and this machine does not have it (an Intel Mac uses a lighter transcriber that cannot run "
            "the music model).\nThat is a known limit, not a broken install. Drop any music track you have the "
            "rights to (.mp3, .wav or .m4a) into projects/<job>/audio/ and it will be laid under the voice.")


def main():
    ap = argparse.ArgumentParser(description="Generate background-music options with MusicGen.")
    ap.add_argument("job", nargs="?")
    ap.add_argument("seconds", nargs="?", type=float, default=18.0)
    ap.add_argument("--vibe", default=None)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--_inner", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if not args._inner and not _has_torch_here():
        pys = _candidate_pythons()
        if not pys:
            print(_no_torch_message())
            sys.exit(NO_TORCH_EXIT)
        if args.check:
            print(f"ready: runs on {pys[0]}")
            print(f"model: {'downloaded' if _model_cached() else f'not downloaded yet (one time, about {MODEL_GB} GB)'}")
            sys.exit(0)
        # venv_spawn starts it the way that works here: from the Microsoft Store Python the venv's own launcher
        # can stop with "No Python at ..." (exit 103).
        args = [os.path.abspath(__file__), *sys.argv[1:], "--_inner"]
        try:
            import venv_spawn
        except ImportError:   # a copy of the engine without the helper starts it directly, as before
            sys.exit(subprocess.call([pys[0], *args]))
        sys.exit(venv_spawn.call(pys[0], args, runner=subprocess.run, step="gen-music"))

    if args.check:
        print(f"ready: runs on {sys.executable}")
        print(f"model: {'downloaded' if _model_cached() else f'not downloaded yet (one time, about {MODEL_GB} GB)'}")
        sys.exit(0)
    if not args.job:
        raise SystemExit('Usage: gen-music.py <job> [seconds] [--vibe "..."]   (job = your reel folder under projects/)')
    generate(args.job, args.seconds, args.vibe)


# SOFT / CHILL / FEELSY but LIGHT (round 1 read too gloomy; the ask was soft, chill, emotional but not heavy).
# Warm + airy + relaxed + tender, light on its feet — NOT sad, NOT dark, NOT dramatic/heavy. Major-ish,
# gentle, soft. Holds under a voice.
DEFAULT_PROMPTS = {
    "chill1-mellow-keys":  "soft chill mellow electric piano, warm and gentle, emotional but light and airy, relaxed, tender, easy, cozy, major key, soft, no drums, no percussion",
    "chill2-soft-lofi":    "soft chill lo-fi, warm and mellow, gentle, emotional but light, airy, relaxed, cozy, tender, soft keys, easygoing, very light brushed texture, not heavy",
    "chill3-airy-guitar":  "soft chill warm acoustic guitar, gentle and airy, emotional but light, relaxed, tender, mellow, easy, warm, hopeful glow, no drums, no percussion",
}


def _write_wav(path, samples, sr):
    """16-bit mono WAV with the stdlib: no soundfile dependency, so any torch venv can write it."""
    import wave
    import numpy as np
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)


def generate(job, secs, vibe):
    import torch
    from transformers import MusicgenForConditionalGeneration, AutoProcessor

    out = os.path.join(ROOT, "projects", job, "audio")
    os.makedirs(out, exist_ok=True)
    if vibe:
        base = "".join(c if c.isalnum() else "-" for c in vibe.lower()).strip("-")[:32].strip("-") or "vibe"
        prompts = {f"music{i}-{base}": f"{vibe}, instrumental, no vocals, sits under a speaking voice"
                   for i in (1, 2, 3)}
    else:
        prompts = DEFAULT_PROMPTS

    if not _model_cached():
        print(f"First time making music on this machine: downloading the music model once "
              f"(about {MODEL_GB} GB). After this it starts right away.", flush=True)
    print(f"loading {MODEL} …", flush=True)
    proc  = AutoProcessor.from_pretrained(MODEL)
    model = MusicgenForConditionalGeneration.from_pretrained(MODEL)
    device = "cuda" if torch.cuda.is_available() else "cpu"   # MPS has unsupported ops for MusicGen
    model.to(device)
    sr = model.config.audio_encoder.sampling_rate          # 32000
    max_new = int(secs * 50)                                # ~50 tokens/sec

    for name, prompt in prompts.items():
        print(f"generating {name} … ({secs:.0f}s of music)", flush=True)
        inputs = proc(text=[prompt], padding=True, return_tensors="pt").to(device)
        with torch.no_grad():
            audio = model.generate(**inputs, max_new_tokens=max_new, do_sample=True, guidance_scale=3.0)
        wav = audio[0, 0].cpu().numpy()
        path = os.path.join(out, f"{name}.wav")
        _write_wav(path, wav, sr)
        print(f"  ✓ wrote {path}  ({len(wav)/sr:.1f}s)", flush=True)

    print(f"DONE — {len(prompts)} options in projects/{job}/audio/ to audition. The build loops the one you "
          f"pick to the length of the reel.", flush=True)


if __name__ == "__main__":
    main()
