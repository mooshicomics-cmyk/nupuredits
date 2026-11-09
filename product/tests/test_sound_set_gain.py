#!/usr/bin/env python3
"""Guard: a level she set on a sound she added keeps that level everywhere (two buyers, 2026-10-22).

A sound in sound.json "added" that carries its own "gain_db" (Claude set it in the chat: a song under a stretch
with no voice, a typing burst brought up) used to be re-leveled by the engine on the Sound tab, in the preview and in
every build. Now:

  row       read() shows it at her level, "gain_how": "set"; an added sound without one stays "auto"
  preview   playback() plays it at her level
  build     for_build() hands the builders her gain_db (the bake, the CapCut handoff and the Finish mix all read it);
            cues_for_build() gives the raw / Super Yap drivers the same level as a linear volume
  agree     preview and build give every sound the same level, set and auto alike (a plan's own sfx_duck_db
            included: the preview used to level an auto sound with the default duck)
  swap      swapping it for another sound levels the new one the engine's way (auto), as every swap does

Runs on generated tones in a temp folder, with sound_plan's _local/ paths pointed there too.
Run: python3 product/tests/test_sound_set_gain.py
"""
import json, os, shutil, subprocess, sys, tempfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-500:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def tone(path, secs, freq=660, db=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ff("-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}", "-af", f"volume={db}dB", path)


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_sound_set_gain: skipped (ffmpeg/ffprobe not installed)")
        return 0
    import audio_levels, capcut_sfx, sound_plan as SP
    tmp = tempfile.mkdtemp(prefix="sound-set-gain-")
    saved = (SP.LOCAL, SP.LEVELS, SP.PREVIEW_DIR, SP._levels_mem)
    try:
        SP.LOCAL = os.path.join(tmp, "_local")
        SP.LEVELS = os.path.join(SP.LOCAL, "sound-levels.json")
        SP.PREVIEW_DIR = os.path.join(SP.LOCAL, "sound-preview")
        SP._levels_mem = None
        jd = os.path.join(tmp, "test-reel")
        os.makedirs(os.path.join(jd, "outputs"))
        os.makedirs(os.path.join(jd, "review"))
        ff("-f", "lavfi", "-i", "color=gray:s=108x192:d=6:r=30", "-f", "lavfi", "-i", "sine=frequency=200:duration=6",
           "-af", "volume=-6dB", "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
           os.path.join(jd, "outputs", "test-reel.mp4"))
        with open(os.path.join(jd, "caption-plan.json"), "w", encoding="utf-8") as fh:
            json.dump({"sfx": [], "sfx_duck_db": audio_levels.SFX_DUCK_DB + 4}, fh)   # a plan with its own duck
        song, typing = os.path.join(tmp, "snd", "song.wav"), os.path.join(tmp, "snd", "typing.wav")
        tone(song, 4, 330, -14)
        tone(typing, 1, 2000, -20)
        added = [{"id": "add-1", "anchor": None, "t": 1.0, "nudge": 0.0, "file": song, "name": "Song", "source": "hers",
                  "on": True, "how": "hers", "gain_db": -9.5},
                 {"id": "add-2", "anchor": None, "t": 3.0, "nudge": 0.0, "file": typing, "name": "Typing",
                  "source": "hers", "on": True, "how": "hers"}]
        with open(SP.sound_json(jd), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "cues": [], "added": added}, fh)

        rows = {c["id"]: c for c in SP.read(jd)["cues"]}
        r1, r2 = rows.get("add-1") or {}, rows.get("add-2") or {}
        check("row: her set level shows as set", r1.get("gain_db") == -9.5 and r1.get("gain_how") == "set", r1)
        check("row: a sound with no level of hers stays auto", r2.get("gain_how") == "auto" and r2.get("gain_db") is not None, r2)

        pb = {c["id"]: c for c in SP.playback(jd)["cues"]}
        check("preview: plays her set level", (pb.get("add-1") or {}).get("gain_db") == -9.5, pb)

        sfx, _m = SP.for_build(jd, [], None, say=lambda *_: None)
        by = {os.path.basename(c["file"]): c for c in sfx}
        check("build: her gain_db reaches the builders", (by.get("song.wav") or {}).get("gain_db") == -9.5, sfx)
        check("build: an auto sound carries no gain_db (the builder levels it)", "gain_db" not in (by.get("typing.wav") or {}), sfx)

        vol = {os.path.basename(c["file"]): c["volume"] for c in SP.cues_for_build(jd)[0]}
        check("raw / Super Yap: her level as a linear volume",
              abs((vol.get("song.wav") or 0) - audio_levels.to_linear(-9.5)) < 1e-6, vol)
        check("raw / Super Yap: an auto sound is left to auto-level", vol.get("typing.wav", 0) is None, vol)

        # agree: the build's auto level (audio_levels, the plan's duck) is the level the preview plays
        auto = SP.auto_sfx_gain(typing, SP._programme(jd), None, SP._ducks(jd)[0])
        check("agree: preview and build give an auto sound the same level",
              abs((pb.get("add-2") or {}).get("gain_db", 99) - round(auto, 1)) < 0.051, (pb.get("add-2"), auto))

        lib = next(iter(sorted(k for k in capcut_sfx.palette() if k not in capcut_sfx.disabled())), None)
        if lib:
            SP.swap(jd, "add-1", f"lib:{lib}")
            with open(SP.sound_json(jd), encoding="utf-8") as fh:
                a1 = next(a for a in json.load(fh)["added"] if a["id"] == "add-1")
            r1 = next(c for c in SP.read(jd)["cues"] if c["id"] == "add-1")
            check("swap: the new sound is leveled the engine's way", "gain_db" not in a1 and r1.get("gain_how") == "auto",
                  (a1, r1))
        else:
            print("  skip  swap (no library sound on this machine)")
    finally:
        SP.LOCAL, SP.LEVELS, SP.PREVIEW_DIR, SP._levels_mem = saved
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"test_sound_set_gain: {'FAIL ' + ', '.join(fails) if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
