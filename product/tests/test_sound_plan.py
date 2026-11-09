#!/usr/bin/env python3
"""Guard: the visual editor's Sound section reads a reel's real sounds, her edits stick, and the build honors them.

Every case runs on a throwaway reel in a temp folder (an absolute job path), with sound_plan's _local/ paths and
the favorites folder pointed at temp dirs, so her real projects/, _local/ and favorites/ are never touched. The
engine's bundled library is read (never written).

What it holds:
  - read(): a reel's cues come from caption-plan.json "sfx" (else an older sfx-plan.json), each with a stable id,
    its time in the cut, its source (library / hers), the graphic it sits on (review/looks.json), and its level:
    a plan's own gain is "set", everything else "auto" at exactly the gain audio_levels gives it
  - choices(): favorites first (her CapCut shelf, then her favorites folder), then this reel's own sounds, then the
    library; switched-off library sounds are never offered; songs never in the sound-effect menu and back
  - swap(): the new sound is leveled the engine's way (auto, its peak under the cut's), so a loud and a quiet pick
    land at the same level; a swap on a hand-set cue makes it auto; "original" puts the planned sound back;
    a song, an unknown id or an unknown cue is refused with a reason
  - toggle() / set_music(): on/off, a different song, a level in dB or back to "auto"; bad values refused
  - sound.json is written atomically (no temp files left), and holds what the page reads
  - for_build(): with no sound.json the plan comes back untouched; with edits, off cues are left out, swapped
    cues play her file with no fixed gain (the builder levels them), untouched cues are the plan's own dicts;
    an edit whose cue left the plan is reported, never moved onto another cue; an unreadable sound.json builds
    the plan as made and says so
  - cues_for_build(): the list a raw / Super Yap driver places, with linear volumes (None = auto-level)
  - preview_path(): a playable file as it is; an .aiff converted once into _local/sound-preview/ and reused
  - moments(): every look that moves (never the captions or a switched-off look) timed to its composition's own
    entrance tween: a two-part hook (its first part), a breakaway (the fade-in, not the slow settle), a pop-in, a
    money count-up (to the end of the counting), a type-on (to its last letter), a fade, a slide, lines timed in a
    forEach loop and by named constants; no readable tween -> the look's start, said ("timing": "start")
  - defaults: by kind, from her favorites folder, then her CapCut shelf, then her Epidemic downloads (temp stand-ins,
    never her real ones), then the shipped CC0 library; never the same sound back to back; trimmed to the motion;
    a confessional reel gets none
  - apply_defaults fills only empty looks (a planned cue on a look's entrance IS its sound), is idempotent, and stores
    each sound ANCHORED: move the look in looks.json and the sound (and the build's cue) moves with it
  - swap "none" / "original", add at the playhead or on a look, nudge (held to +-1 s), remove, the reel-wide Sound
    effects switch; bad input refused in plain words; for_build's look / added cues: absolute file, auto level, the
    motion's trim; a look taken off the reel leaves its sound out, said
  - THE BAKE HONORS IT: build-reel-mp4.py, run for real in a scratch engine, plays a cue and a bed, then drops the
    cue she switched off and the bed she turned off, and follows a music level she set; plays a look's sound at its
    entrance and moves it when the look moves; plays no sound effects with the switch off

Run: python3 product/tests/test_sound_plan.py
"""
import glob, io, json, os, re, shutil, subprocess, sys, tempfile, time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
JOB = "my-reel"                 # a reel name for paths that must be refused (no such folder is made)
PRODUCT = os.path.join(ROOT, "product")
sys.path.insert(0, PRODUCT)
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-700:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def tone(path, secs, freq=660, db=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ff("-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}", "-af", f"volume={db}dB", path)


def refused(fn, *a, **k):
    import sound_plan
    try:
        fn(*a, **k)
    except sound_plan.Refuse as e:
        return str(e)
    return None


def rms_db(path, start, end):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-af", f"atrim={start}:{end},astats", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"RMS level dB:\s*(-?inf|-?[\d.]+)", r.stderr)
    if not m:
        return None
    return -999.0 if "inf" in m[-1] else float(m[-1])


def make_reel(jd, name, sfx, music=None, extra=None):
    """A tiny reel: a 4 s cut with her voice (a tone) and a caption plan."""
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    ff("-f", "lavfi", "-i", "color=gray:s=108x192:d=4:r=30", "-f", "lavfi", "-i", "sine=frequency=200:duration=4",
       "-af", "volume=-6dB", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       os.path.join(jd, "outputs", f"{name}.mp4"))
    plan = {"sfx": sfx}
    if music:
        plan["music"] = music
    plan.update(extra or {})
    json.dump(plan, open(os.path.join(jd, "caption-plan.json"), "w", encoding="utf-8"))


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("test_sound_plan: skipped (ffmpeg/ffprobe not installed)")
        return 0
    import audio_levels, capcut_sfx, favorites_folder as F, sound_plan as SP
    check("added sounds: follow their word after a cut change; a cut word's sound rests with it, her on/off untouched",
          test_added_sounds_follow_their_word())
    tmp = tempfile.mkdtemp(prefix="sound-plan-")
    saved = (SP.LOCAL, SP.LEVELS, SP.PREVIEW_DIR, F.FOLDER, F.CACHE, capcut_sfx.FAVORITES_DIR, SP.EPIDEMIC_HOME,
             SP.PROJECTS_DIR)
    try:
        SP.LOCAL = os.path.join(tmp, "_local")
        SP.LEVELS = os.path.join(SP.LOCAL, "sound-levels.json")
        SP.PREVIEW_DIR = os.path.join(SP.LOCAL, "sound-preview")
        SP._levels_mem = None
        F.FOLDER = os.path.join(tmp, "favorites")
        F.CACHE = os.path.join(SP.LOCAL, "favorites-cache")
        capcut_sfx.FAVORITES_DIR = os.path.join(SP.LOCAL, "sounds")
        SP.EPIDEMIC_HOME = os.path.join(tmp, "Documents", "Epidemic Sound")      # never her real downloads
        SP.PROJECTS_DIR = os.path.join(tmp, "projects")

        # her Epidemic downloads: the app's folder (a sound effect and a song) and one reel's pull
        tone(os.path.join(SP.EPIDEMIC_HOME, "SFX", "ES_100001_Impacts, Thud, Body Hit 01.mp3"), 0.5, 120, -6)
        tone(os.path.join(SP.EPIDEMIC_HOME, "Music", "ES_100002_Sunny Days - Someone.mp3"), 16, 300, -14)
        tone(os.path.join(SP.EPIDEMIC_HOME, "Voiceover", "my-voice.mp3"), 2, 300, -14)
        tone(os.path.join(SP.PROJECTS_DIR, "older-reel", "sfx", "epidemic", "keyboard-typing.wav"), 1.0, 2000, -12)

        # her CapCut shelf (favorites.py) and her favorites folder
        tone(os.path.join(SP.LOCAL, "sounds", "soft-pop.mp3"), 0.3, 990, -20)
        tone(os.path.join(SP.LOCAL, "sounds", "whoosh-fast.mp3"), 0.6, 500, -12)
        json.dump({"draft": "My Sounds", "sounds": [{"name": "soft-pop", "title": "Soft pop(123)",
                                                    "file": "_local/sounds/soft-pop.mp3", "seconds": 0.3},
                                                   {"name": "whoosh-fast", "title": "Whoosh fast(456)",
                                                    "file": "_local/sounds/whoosh-fast.mp3", "seconds": 0.6}]},
                  open(os.path.join(SP.LOCAL, "favorites.json"), "w", encoding="utf-8"))
        tone(os.path.join(F.FOLDER, "sounds", "loud-ding.mp3"), 0.4, 1200, 0)
        tone(os.path.join(F.FOLDER, "sounds", "quiet-tick.wav"), 0.4, 1500, -10)   # 10 dB under the ding, inside the gain range
        tone(os.path.join(F.FOLDER, "sounds", "warm-song.m4a"), 18, 330, -10)
        look_own_sound(SP, tmp)
        tone(os.path.join(F.FOLDER, "sounds", "vintage.aiff"), 0.5, 700, -6)

        pal = capcut_sfx.selectable()
        canon = [k for k in sorted(pal) if os.path.splitext(os.path.basename(pal[k]))[0] == k]
        lib = next((k for k in ("comedic-pop", "hit-1", "ding", "chime", "whoosh") if k in canon), canon[0])
        jd = os.path.join(tmp, "projects", "my-reel")
        tone(os.path.join(jd, "sfx", "mine.wav"), 0.5, 440, -3)
        tone(os.path.join(jd, "audio", "her-song.mp3"), 20, 260, -12)
        make_reel(jd, "my-reel", [{"file": lib, "at": 1.0, "trim": 0.3, "_why": "hook lands"},
                                  {"file": "mine.wav", "at": 2.5, "gain_db": -3}],
                  music={"file": "her-song.mp3", "at": 0.0})
        os.makedirs(os.path.join(jd, "review"))
        json.dump({"layers": [{"name": "hook-card", "offset": 0.8, "dur": 1.0},
                              {"name": "captions", "captions": True, "offset": 0, "dur": 4}]},
                  open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
        prog = os.path.join(jd, "outputs", "my-reel.mp4")
        ppeak = audio_levels.peak_dbfs(prog)

        print("read: the reel's real sounds")
        p = SP.read(jd)
        ids = [c["id"] for c in p["cues"]]
        check("two cues, from the caption plan, in cut order", p["from"] == "caption-plan.json" and len(ids) == 2
              and p["cues"][0]["t"] == 1.0 and p["cues"][1]["t"] == 2.5, p)
        c1, c2 = p["cues"]
        check("ids name the sound and the moment", c1["id"] == f"{lib}@1.000" and c2["id"] == "mine@2.500", ids)
        check("a library cue says library, the reel's own says hers", c1["source"] == "library" and c2["source"] == "hers")
        check("it knows the graphic the cue sits on (never the captions)", c1["on_look"] == "hook-card"
              and c2["on_look"] is None, (c1["on_look"], c2["on_look"]))
        lib_file = pal[lib]
        want = audio_levels.sfx_gain_for(lib_file, prog, 0.3)           # the north star rule every route shares
        check("an auto cue shows exactly the gain the build gives it", c1["gain_how"] == "auto"
              and abs(c1["gain_db"] - want) < 0.05, (c1["gain_db"], want))
        check("a cue the plan set by hand shows its own level", c2["gain_how"] == "set" and c2["gain_db"] == -3.0)
        check("the beat note comes along", c1["beat"] == "hook lands")
        check("the music bed is read, on, at its auto level", p["music"]["on"] and p["music"]["source"] == "hers"
              and p["music"]["level_how"] == "auto" and p["music"]["level_db"] is not None, p["music"])
        check("reading never writes sound.json", not os.path.exists(SP.sound_json(jd)))

        print("choices: her favorites first")
        ch = SP.choices("sfx", jd)
        srcs = [r["source"] for r in ch]
        first_lib = srcs.index("library")
        check("her favorites folder first, then her CapCut shelf, her Epidemic downloads, hers, then the library",
              srcs[:5] == ["favorite"] * 3 + ["capcut"] * 2 and srcs[5:7] == ["epidemic"] * 2
              and srcs[first_lib:] == ["library"] * (len(srcs) - first_lib) and "hers" in srcs[7:first_lib], srcs[:10])
        check("her CapCut shelf comes next, by its own name, tagged capcut", ch[3]["id"] == "fav:soft-pop"
              and ch[3]["name"] == "Soft pop" and ch[3]["source"] == "capcut", ch[3])
        epi = [r for r in ch if r["source"] == "epidemic"]
        check("her Epidemic files are offered by their own names, never her voiceovers or songs",
              [r["name"] for r in epi] == ["Impacts, Thud, Body Hit 01", "Keyboard typing"]
              and epi[0]["id"] == "epi:home/SFX/ES_100001_Impacts, Thud, Body Hit 01.mp3", [(r["id"], r["name"]) for r in epi])
        check("an Epidemic id from the menu resolves; one that climbs out is refused",
              SP.resolve_choice(epi[1]["id"], "sfx", jd)["source"] == "epidemic"
              and refused(SP.resolve_choice, "epi:home/../../../etc/hosts") is not None
              and refused(SP.resolve_choice, f"epi:projects/{JOB}/sfx/mine.wav", "sfx", jd) is not None)
        check("her folder's sounds are offered", {"folder:sounds/loud-ding.mp3", "folder:sounds/quiet-tick.wav"}
              <= {r["id"] for r in ch})
        check("no song in the sound-effect menu", all((r["duration"] or 0) <= 15 for r in ch)
              and "folder:sounds/warm-song.m4a" not in {r["id"] for r in ch})
        off = {f"lib:{k}" for k in capcut_sfx.disabled()}
        check("a sound she switched off is never offered", not (off & {r["id"] for r in ch}), off & {r["id"] for r in ch})
        check("the library comes from the engine's own listing", f"lib:{lib}" in {r["id"] for r in ch})
        check("every row has id, name, file, source, duration",
              all({"id", "name", "file", "source", "duration"} <= set(r) for r in ch))
        mus = SP.choices("music", jd)
        check("the music menu: her folder's song, her Epidemic song, then the reel's song, no sound effects",
              [r["id"] for r in mus][:3] == ["folder:sounds/warm-song.m4a", "epi:home/Music/ES_100002_Sunny Days - Someone.mp3",
                                            "job:audio/her-song.mp3"]
              and all(r["duration"] > 15 for r in mus), [r["id"] for r in mus])

        print("swap: leveled like every cue")
        p = SP.swap(jd, c1["id"], "folder:sounds/loud-ding.mp3")
        s1 = p["cues"][0]
        loud = os.path.join(F.FOLDER, "sounds", "loud-ding.mp3")
        want = audio_levels.sfx_gain_for(loud, prog, 0.3)          # the north star rule every route shares
        check("the swap shows her pick, as a favorite", s1["swapped"] and s1["source"] == "favorite"
              and s1["choice"] == "folder:sounds/loud-ding.mp3", s1)
        check("the swapped sound gets the engine's auto level", s1["gain_how"] == "auto"
              and abs(s1["gain_db"] - want) < 0.05, (s1["gain_db"], want))
        check("sound.json is written, with no temp files left", os.path.isfile(SP.sound_json(jd))
              and not [f for f in os.listdir(os.path.join(jd, "review")) if f.endswith(".tmp")])
        p = SP.swap(jd, c2["id"], "folder:sounds/quiet-tick.wav")
        s2 = p["cues"][1]
        quiet = os.path.join(F.FOLDER, "sounds", "quiet-tick.wav")
        check("a hand-set cue swapped becomes auto", s2["gain_how"] == "auto" and s2["gain_db"] != -3.0, s2)
        cap = audio_levels.SFX_PEAK_CAP_DBFS                         # same loudness under her voice, unless a peak hits the cap
        t1, t2 = s1.get("trim"), s2.get("trim")                       # each measured over the stretch its cue plays
        m1, m2 = audio_levels.momentary_max_lufs(loud, t1), audio_levels.momentary_max_lufs(quiet, t2)
        if m1 is None or m2 is None:                                 # loudness unreadable: the peak fallback, by peaks
            m1, m2 = audio_levels.peak_dbfs(loud, t1), audio_levels.peak_dbfs(quiet, t2)
        lands1, lands2 = m1 + s1["gain_db"], m2 + s2["gain_db"]
        capped = any(abs(audio_levels.peak_dbfs(f, t) + g - cap) < 0.15 for f, t, g in ((loud, s1.get("trim"), s1["gain_db"]), (quiet, s2.get("trim"), s2["gain_db"])))
        check("a loud pick and a quiet pick land at the same loudness (or a peak at the cap)", abs(lands1 - lands2) < 0.5 or capped,
              (lands1, lands2))
        check("the original is remembered", s1["original"]["choice"] == f"lib:{lib}")
        p = SP.swap(jd, c2["id"], "original")
        check("'original' puts the planned sound back, with its own level", not p["cues"][1]["swapped"]
              and p["cues"][1]["gain_db"] == -3.0 and p["cues"][1]["source"] == "hers", p["cues"][1])
        was = next(c for c in p["cues"] if c["id"] == c1["id"])["choice"]
        p = SP.swap(jd, c1["id"], "folder:sounds/warm-song.m4a")   # her pick: a song on an effect plays its moment, trimmed
        check("a song on a sound effect is hers to use (it plays its moment, trimmed)",
              next(c for c in p["cues"] if c["id"] == c1["id"])["choice"] == "folder:sounds/warm-song.m4a", p["cues"][0])
        SP.swap(jd, c1["id"], was)                                   # back to her earlier pick for the checks below
        check("an unknown sound is refused", refused(SP.swap, jd, c1["id"], "lib:no-such-sound-xyz") is not None)
        check("an unknown cue is refused", refused(SP.swap, jd, "nope@9.000", f"lib:{lib}") is not None)
        if off:
            check("a switched-off library sound can't be swapped in",
                  "switched off" in (refused(SP.swap, jd, c1["id"], sorted(off)[0]) or ""))
        check("a made-up id is refused", refused(SP.swap, jd, c1["id"], "../../etc/passwd") is not None)
        check("a path outside the reel is refused", refused(SP.swap, jd, c1["id"], "job:../../x.mp3") is not None)

        print("toggle and the music bed")
        p = SP.toggle(jd, c2["id"], False)
        check("a cue switches off", p["cues"][1]["on"] is False and p["cues"][0]["swapped"])
        check("on/off must be a yes or no", refused(SP.toggle, jd, c2["id"], "off") is not None)
        p = SP.set_music(jd, level_db=-9)
        check("a music level she sets sticks", p["music"]["level_db"] == -9.0 and p["music"]["level_how"] == "set")
        p = SP.set_music(jd, level_db=40)
        check("a level out of range is held to the range (never refused); a word that isn't a level still is",
              p["music"]["level_db"] == audio_levels.GAIN_MAX_DB and refused(SP.set_music, jd, level_db="loud") is not None, p["music"])
        p = SP.set_music(jd, level_db="auto")
        check("'auto' puts the measured level back", p["music"]["level_how"] == "auto")
        p = SP.set_music(jd, choice_id="folder:sounds/warm-song.m4a")
        check("a different song, at its auto level", p["music"]["swapped"] and p["music"]["source"] == "favorite"
              and p["music"]["level_how"] == "auto", p["music"])
        check("a short sound as the bed is hers to use (it loops)", SP.set_music(jd, choice_id="folder:sounds/loud-ding.mp3")["music"]["swapped"])
        SP.set_music(jd, choice_id="folder:sounds/warm-song.m4a")
        p = SP.set_music(jd, on=False)
        check("the bed switches off", p["music"]["on"] is False)
        jd2 = os.path.join(tmp, "projects", "no-music")
        make_reel(jd2, "no-music", [{"file": lib, "at": 0.5}])
        check("no song yet: turning the bed on is refused with what to do",
              "Pick one" in (refused(SP.set_music, jd2, on=True) or ""))

        print("for_build: what the builds read")
        plan = json.load(open(os.path.join(jd, "caption-plan.json"), encoding="utf-8"))
        sfx, music = SP.for_build(jd2, plan["sfx"], plan["music"], say=lambda *_: None)
        check("no sound.json: the plan comes back untouched", sfx == plan["sfx"] and music is plan["music"])
        said = []
        sfx, music = SP.for_build(jd, plan["sfx"], plan["music"], say=said.append)
        check("the cue she switched off is left out", len(sfx) == 1, sfx)
        check("the swapped cue plays her file, absolute, no fixed gain", sfx[0]["file"] == loud and "gain_db" not in sfx[0]
              and sfx[0]["at"] == 1.0 and sfx[0]["trim"] == 0.3, sfx)
        check("the bed she turned off is gone", music is None)
        check("the build says what it applied", any("her Sound edits" in s for s in said), said)
        SP.set_music(jd, on=True)
        SP.set_music(jd, level_db=-12)
        _s, music = SP.for_build(jd, plan["sfx"], plan["music"], say=lambda *_: None)
        check("the bed comes back with her song and her level", music and music["file"].endswith("warm-song.m4a")
              and music["gain_db"] == -12.0 and music["at"] == 0.0, music)
        SP.toggle(jd, c2["id"], True)
        sfx, _m = SP.for_build(jd, plan["sfx"], plan["music"], say=lambda *_: None)
        check("an untouched cue is the plan's own entry", sfx[1] is plan["sfx"][1])
        moved = [dict(plan["sfx"][0], at=1.2), plan["sfx"][1]]
        said = []
        sfx, _m = SP.for_build(jd, moved, plan["music"], say=said.append)
        check("a cue that moved in the plan isn't guessed: her swap is reported, the plan's cue plays",
              sfx[0]["file"] == lib and any("no longer match" in s and c1["id"] in s for s in said), (sfx, said))

        print("cues_for_build: what a raw / Super Yap driver places")
        cues, m = SP.cues_for_build(jd)
        check("each cue has a real file, its time, and a volume (None = auto)", len(cues) == 2
              and cues[0]["file"] == loud and cues[0]["volume"] is None
              and abs(cues[1]["volume"] - audio_levels.to_linear(-3)) < 1e-6 and os.path.isfile(cues[1]["file"]), cues)
        check("the bed comes with it", m and m["file"].endswith("warm-song.m4a"))
        jd3 = os.path.join(tmp, "projects", "old-reel")
        tone(os.path.join(jd3, "audio", "sfx-norm", "01-tap.wav"), 0.3)
        os.makedirs(os.path.join(jd3, "outputs"), exist_ok=True)
        json.dump({"cues": [{"file": "audio/sfx-norm/01-tap.wav", "t": 0.5, "volume": 0.5, "beat": "lands"}]},
                  open(os.path.join(jd3, "sfx-plan.json"), "w", encoding="utf-8"))
        p3 = SP.read(jd3)
        check("an older reel's sfx-plan.json is read, its volume shown as a set level", p3["from"] == "sfx-plan.json"
              and p3["cues"][0]["gain_how"] == "set" and abs(p3["cues"][0]["gain_db"] - (-6.0)) < 0.1, p3)
        cues3, _m = SP.cues_for_build(jd3)
        check("...and its driver gets the same list", cues3 and cues3[0]["t"] == 0.5 and abs(cues3[0]["volume"] - 0.5) < 1e-6)

        print("unreadable sound.json")
        good = open(SP.sound_json(jd), encoding="utf-8").read()
        open(SP.sound_json(jd), "w", encoding="utf-8").write("{broken")
        p = SP.read(jd)
        check("the page is told, and shows the plan as made", "couldn't be read" in (p.get("problem") or "")
              and not p["cues"][0]["swapped"])
        said = []
        sfx, music = SP.for_build(jd, plan["sfx"], plan["music"], say=said.append)
        check("the build plays the plan as made and says why", sfx == plan["sfx"] and music == plan["music"]
              and said and "without her Sound edits" in said[0], said)
        open(SP.sound_json(jd), "w", encoding="utf-8").write(good)

        print("moments: every look that moves, timed to its motion")
        moments_checks(tmp, SP, F, lib)

        print("the CapCut builds honor it (VectCut stubbed: the calls are recorded, nothing is sent)")
        capcut_checks(tmp, SP, jd, lib, loud)

        print("preview")
        check("a playable favorite previews as itself", SP.preview_path("folder:sounds/loud-ding.mp3") == loud)
        pv = SP.preview_path("folder:sounds/vintage.aiff")
        check("an .aiff is made playable once, under _local/sound-preview", pv.endswith(".m4a")
              and pv.startswith(SP.PREVIEW_DIR) and os.path.getsize(pv) > 0, pv)
        mt = os.stat(pv).st_mtime_ns
        time.sleep(0.05)
        check("...and reused after that", SP.preview_path("folder:sounds/vintage.aiff") == pv and os.stat(pv).st_mtime_ns == mt)
        check("a library sound previews from the library", SP.preview_path(f"lib:{lib}") == lib_file)
        check("the reel's own song previews", SP.preview_path("job:audio/her-song.mp3", jd).endswith("her-song.mp3"))

        print("the well-done bake honors it (real build-reel-mp4.py, scratch engine)")
        bake_checks(tmp, SP, lib)
    finally:
        (SP.LOCAL, SP.LEVELS, SP.PREVIEW_DIR, F.FOLDER, F.CACHE, capcut_sfx.FAVORITES_DIR, SP.EPIDEMIC_HOME,
         SP.PROJECTS_DIR) = saved
        SP._levels_mem = None
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("all good: the Sound section reads the reel's real sounds, her edits stick, and the bake plays what she chose")
    return 0


# ── moments: real-looking builder pages ───────────────────────────────────────────────────────────────────
TL_HEAD = 'window.__timelines=window.__timelines||{};\nconst tl=gsap.timeline({paused:true});\n'
PAGES = {
    # a two-part hook: the eyebrow blurs in at 0.20, the headline at 0.62 (the builder's hook page)
    "hook": TL_HEAD + 'tl.fromTo("#hk0",{autoAlpha:0,filter:"blur(8px)",y:6},{autoAlpha:1,filter:"blur(0px)",y:0,'
            'duration:0.5,ease:"power2.out"},0.20);\ntl.fromTo("#hk1",{autoAlpha:0,filter:"blur(8px)",y:6},{autoAlpha:1,'
            'filter:"blur(0px)",y:0,duration:0.5,ease:"power2.out"},0.62);\ntl.to("#hookwrap",{autoAlpha:0,duration:0.4},'
            '1.27);tl.set("#hookwrap",{autoAlpha:0},1.67);\nwindow.__timelines["hook"]=tl;',
    # a pop-in card (scale .55, back ease)
    "pop1": TL_HEAD + 'tl.fromTo("#card",{autoAlpha:0,scale:.55,rotation:0,y:60},{autoAlpha:1,scale:1,rotation:-3,y:0,'
            'duration:.45,ease:"back.out(1.5)",immediateRender:true},0.04);tl.to("#card",{autoAlpha:0,duration:.24},1.5);'
            'tl.set("#card",{autoAlpha:0},1.8);\ntl.set({},{},1.9);\nwindow.__timelines["pop1"]=tl;',
    "pop2": TL_HEAD + 'tl.fromTo("#w0",{autoAlpha:0,scale:.55},{autoAlpha:1,scale:1,duration:.24,ease:"back.out(2.2)"},0.040);'
            '\nwindow.__timelines["pop2"]=tl;',
    "pop3": TL_HEAD + 'tl.fromTo("#w0",{autoAlpha:0,scale:.5},{autoAlpha:1,scale:1,duration:.3,ease:"back.out(2)"},0.04);'
            '\nwindow.__timelines["pop3"]=tl;',
    # a breakaway: hidden by a set, faded in by a to() while a slow settle runs from the same moment
    "breakaway": TL_HEAD + 'tl.set("#bk0",{autoAlpha:0},0);tl.to("#bk0",{autoAlpha:1,duration:0.16,ease:"power2.inOut"},0.05);'
                 'tl.fromTo("#bk0",{scale:1.06},{scale:1,duration:5.70,ease:"power1.out"},0.05);\ntl.set("#bk0l0",{autoAlpha:0,'
                 'y:52,scale:0.8},0);tl.to("#bk0l0",{autoAlpha:1,y:0,scale:1,duration:0.55,ease:"back.out(1.7)"},0.27);'
                 '\nwindow.__timelines["breakaway"]=tl;',
    # a count-up of money: the card at 0.10, the number counting 0.20 -> 1.60
    "counter": TL_HEAD + 'tl.fromTo("#el0",{autoAlpha:0,scale:0.92,y:18},{autoAlpha:1,scale:1,y:0,duration:0.45,'
               'ease:"back.out(1.6)",immediateRender:false},0.10);var o_el0={v:0.0};tl.to(o_el0,{v:1000.0,duration:1.40,'
               'ease:"power2.out",onUpdate:function(){var v=o_el0.v;document.getElementById("el0n").textContent="$"+'
               '(Math.round(v).toLocaleString("en-US"))+"";}},0.20);\nwindow.__timelines["counter"]=tl;',
    # a type-on: one letter at a time, 0.10 -> 0.40
    "typer": TL_HEAD + 'tl.set("#c0",{autoAlpha:1},0.10);tl.set("#c1",{autoAlpha:1},0.20);tl.set("#c2",{autoAlpha:1},0.30);'
             'tl.set("#c3",{autoAlpha:1},0.40);\nwindow.__timelines["typer"]=tl;',
    # a plain fade (the karaoke builder's line)
    "fade": TL_HEAD + 'tl.fromTo("#c0",{opacity:0},{opacity:1,duration:.08,ease:"power1.out",immediateRender:true},0.12);'
            '\nwindow.__timelines["fade"]=tl;',
    "slider": TL_HEAD + 'tl.fromTo("#card",{autoAlpha:0,x:-240},{autoAlpha:1,x:0,duration:0.35,ease:"power3.out"},0.15);'
              '\nwindow.__timelines["slider"]=tl;',
    # a page that times its lines in a loop
    "looped": TL_HEAD + '[["#L0",0.73],["#L1",1.23],["#L2",1.59]].forEach(([s,t])=>tl.fromTo(s,{autoAlpha:0,y:26,scale:.96},'
              '{autoAlpha:1,y:0,scale:1,duration:.2,ease:"back.out(2)",immediateRender:true},t));\n'
              'window.__timelines["looped"]=tl;',
    # a page that times by named constants (her own designs do this)
    "named": TL_HEAD + 'const T={put:0.09,three:1.57};\ntl.fromTo("#C",{y:70,scale:.96,autoAlpha:0},{y:0,scale:1,autoAlpha:1,'
             'duration:.42,ease:"back.out(1.4)",immediateRender:true},T.put+.2);\nwindow.__timelines["named"]=tl;',
    # a hand-animated page with no GSAP tweens at all
    "orbit": 'window.__timelines=window.__timelines||{};function frame(t){}\nwindow.__timelines["orbit"]=null;',
}
OFFSETS = {"hook": 1.0, "pop1": 3.0, "pop2": 3.5, "pop3": 4.0, "breakaway": 5.0, "counter": 7.0, "typer": 9.0,
           "fade": 11.0, "slider": 13.0, "looped": 15.0, "named": 16.5, "orbit": 18.0}
# every motion gets its own sound: the looped page's three lines (0.73, 1.23, 1.59) are three moments
MOMENTS = set(OFFSETS) | {"looped#2", "looped#3"}
N_MOMENTS = len(MOMENTS)
LOOK_OF = {"hook": ("hook", "Hook"), "breakaway": ("breakaway", "Breakaway card"), "counter": ("counter", "Count-up"),
           "typer": ("typewriter", "Typewriter")}


def write_looks(jd, offsets, extra=None):
    layers = []
    for name, off in offsets.items():
        look, look_name = LOOK_OF.get(name, ("_original", "Your original"))
        layers.append({"name": name, "dir": f"hf-graphics/_looks/{name}/{look}", "id": f"{name}-{look}",
                       "offset": off, "dur": 1.9, "look": look, "look_name": look_name, "captions": False})
    layers += extra or []
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    json.dump({"version": 1, "layers": layers}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))


def moments_checks(tmp, SP, F, lib):
    import audio_levels
    jd = os.path.join(tmp, "projects", "moving-reel")
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)
    ff("-f", "lavfi", "-i", "color=gray:s=108x192:d=20:r=30", "-f", "lavfi", "-i", "sine=frequency=200:duration=20",
       "-af", "volume=-6dB", "-t", "20", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       os.path.join(jd, "outputs", "moving-reel.mp4"))
    for name, js in PAGES.items():
        look = LOOK_OF.get(name, ("_original",))[0]
        d = os.path.join(jd, "hf-graphics", "_looks", name, look)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(
            f'<!doctype html><html><body><div id="root" data-composition-id="{name}"></div>'
            f'<script src="gsap.min.js"></script><script>\n{js}\n</script></body></html>')
    write_looks(jd, OFFSETS, extra=[
        {"name": "captions", "dir": "hf-graphics/captions", "offset": 0, "dur": 20, "captions": True},
        {"name": "gone-look", "dir": "hf-graphics/_looks/pop2/_original", "offset": 6.0, "dur": 1, "off": True}])
    # a planned cue already sits on pop1's entrance (3.04): it IS that look's sound
    json.dump({"sfx": [{"file": lib, "at": 3.05, "trim": 0.3}], "music": {"file": "bed.mp3", "at": 0.0}},
              open(os.path.join(jd, "caption-plan.json"), "w", encoding="utf-8"))
    tone(os.path.join(jd, "audio", "bed.mp3"), 20, 260, -12)
    tone(os.path.join(F.FOLDER, "sounds", "my-pop.wav"), 0.35, 1100, -6)

    ms = {m["layer"]: m for m in SP.moments(jd)}
    near = lambda a, b: a is not None and b is not None and abs(a - b) < 0.002
    check("every look that moves is a moment; the captions and a switched-off look are not",
          set(ms) == MOMENTS, sorted(ms))
    h = ms["hook"]
    check("two-part hook: the entrance is the FIRST part (offset + 0.20), its motion 0.5 s, a blur",
          near(h["t"], 1.2) and near(h["motion_s"], 0.5) and h["kind"] == "blur" and h["timing"] == "motion", h)
    check("a pop-in card: scale-up with a back ease is a pop", ms["pop1"]["kind"] == "pop" and near(ms["pop1"]["t"], 3.04)
          and near(ms["pop1"]["motion_s"], 0.45), ms["pop1"])
    b = ms["breakaway"]
    check("breakaway: the fade-in at 0.05 (not the slow 5.7 s settle) is the entrance, and it's a card",
          near(b["t"], 5.05) and near(b["motion_s"], 0.16) and b["kind"] == "card", b)
    c = ms["counter"]
    check("count-up: a count, money, its motion runs to the end of the counting (0.10 -> 1.60)",
          c["kind"] == "count" and c["money"] and near(c["t"], 7.1) and near(c["motion_s"], 1.5), c)
    check("type-on: from its first letter to its last", ms["typer"]["kind"] == "type" and near(ms["typer"]["t"], 9.1)
          and near(ms["typer"]["motion_s"], 0.3), ms["typer"])
    check("a plain fade is a reveal; a sideways entrance is a slide",
          ms["fade"]["kind"] == "reveal" and near(ms["fade"]["t"], 11.12)
          and ms["slider"]["kind"] == "slide" and near(ms["slider"]["t"], 13.15), (ms["fade"], ms["slider"]))
    check("lines timed in a forEach loop: the first pass is the entrance, a small rise",
          near(ms["looped"]["t"], 15.73) and ms["looped"]["kind"] == "rise" and near(ms["looped"]["motion_s"], 0.2),
          ms["looped"])
    check("a position written with named constants (T.put+.2) is read", near(ms["named"]["t"], 16.79)
          and ms["named"]["kind"] == "slide", ms["named"])
    check("no readable tween: the look's start, and it says so", near(ms["orbit"]["t"], 18.0)
          and ms["orbit"]["timing"] == "start", ms["orbit"])
    lp = [ms.get(k) for k in ("looped", "looped#2", "looped#3")]
    check("every motion gets its own sound: a list's three lines are three moments, each at its own time, parts of one look",
          all(lp) and [round(m["t"], 2) for m in lp] == [15.73, 16.23, 16.59]
          and all(m["look_layer"] == "looped" and m["parts"] == 3 for m in lp) and [m["part"] for m in lp] == [1, 2, 3], lp)
    check("a burst closer than PART_GAP_S is one motion (a breakaway card and its title 0.22 s later); a hook's lines "
          "and a type-on's letters stay one", not any(k.startswith(("breakaway#", "hook#", "typer#")) for k in ms), sorted(ms))
    # her Sandbox sketch (2026-10-18): four cards pop in one by one, timed by a loop over a constant, then orbit her
    # (a plain-object tween that is motion, not a count-up); its in-front and behind halves pop on the same frames
    sk = ('<div id="root"><span id="notes">@a @b @c @d</span><div class="clip" id="clip-cards"></div></div><script>\n'
          'window.__timelines=window.__timelines||{};\nconst D=10.19, SIDE="front", T0=2.0;\n'
          'const names=document.getElementById("notes").textContent.trim().split(/\\s+/);\n'
          'document.querySelectorAll(".pop .h").forEach((el,i)=>{el.textContent=names[i]||"";});\n'
          'const ring={a:0.6};\nfunction place(){ for(let i=0;i<4;i++){ const th=ring.a+i; gsap.set("#c"+i,{x:th}); } }\n'
          'const tl=gsap.timeline({paused:true,onUpdate:place});\n'
          '[0,1,2,3].forEach(i=>{ tl.fromTo("#p"+i,{autoAlpha:0,scale:0.15},{autoAlpha:1,scale:1,duration:0.55,'
          'ease:"back.out(1.8)"},T0+i*0.45); });\ntl.to(ring,{a:3.4,duration:Math.max(1,D-(T0+1.6)),ease:"sine.inOut"},T0+1.6);\n'
          '[0,1,2,3].forEach(i=>{ tl.to("#p"+i,{autoAlpha:0,duration:0.3},D-0.35); });\n'
          'window.__timelines["sk"]=tl;\n</script>')
    sj = os.path.join(tmp, "projects", "sketch-reel")
    for name in ("add-w2", "add-w2-2"):
        d = os.path.join(sj, "hf-graphics", "_looks", name, "my-sketch")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(sk)
    os.makedirs(os.path.join(sj, "review"), exist_ok=True)
    json.dump({"version": 1, "layers": [
        {"name": n, "dir": f"hf-graphics/_looks/{n}/my-sketch", "offset": 0.0, "dur": 10.19, "look": "my-sketch",
         "look_name": ln, "captions": False} for n, ln in (("add-w2", "Card pop orbit"), ("add-w2-2", "Card pop orbit (behind you)"))]},
        open(os.path.join(sj, "review", "looks.json"), "w", encoding="utf-8"))
    sm = SP.moments(sj)
    check("a sketch's four cards popping at 2.0 / 2.45 / 2.9 / 3.35 are four moments, each a pop (never a count-up)",
          [m["t"] for m in sm] == [2.0, 2.45, 2.9, 3.35] and all(m["kind"] == "pop" and m["look_layer"] == "add-w2" for m in sm)
          and [m["layer"] for m in sm] == ["add-w2", "add-w2#2", "add-w2#3", "add-w2#4"], sm)
    check("its in-front and behind halves pop on the same frames: one sound each, never two stacked",
          [m.get("with") for m in sm] == [["add-w2-2"], ["add-w2-2#2"], ["add-w2-2#3"], ["add-w2-2#4"]], sm)
    rp = SP.read(sj)
    pr = [r for r in rp["cues"] if r.get("moment")]
    check("the Sound tab gets one row per pop, each on the look itself, saying which part it is",
          [(r["id"], r["on_look"], r["part"], r["parts"]) for r in pr]
          == [("look:add-w2", "add-w2", 1, 4), ("look:add-w2#2", "add-w2", 2, 4), ("look:add-w2#3", "add-w2", 3, 4),
              ("look:add-w2#4", "add-w2", 4, 4)], pr)
    # Any reel on this machine with a Butter hook look the builder made (none on a fresh install: then skipped).
    real_hooks = sorted(glob.glob(os.path.join(ROOT, "projects", "*", "hf-graphics", "_looks", "*", "hook",
                                               "hf-reel-type-butter", "index.html")))
    if real_hooks:
        look_name = real_hooks[0].split(os.sep)[-4]
        e = SP.entrance(open(real_hooks[0], encoding="utf-8").read(), {"name": look_name, "look": "hook"})
        check("a real builder hook page parses the same way", e[:3] == (0.2, 0.5, "blur"), (real_hooks[0], e))

    print("defaults: follow the motion, her sources first")
    d = SP.defaults_for(jd)
    dm = {m["layer"]: m["default"] for m in d["moments"]}
    src = {k: (v or {}).get("source") for k, v in dm.items()}
    check("a pop gets her favorites-folder pop (source a)", dm["pop1"]["choice"] == "folder:sounds/my-pop.wav", dm["pop1"])
    check("the next pop right after it isn't the same sound: her CapCut shelf's pop instead (source b)",
          dm["pop2"]["choice"] == "fav:soft-pop" and src["pop2"] == "capcut"
          and dm["pop3"]["choice"] == "folder:sounds/my-pop.wav", (dm["pop2"], dm["pop3"]))
    check("a blur gets her CapCut shelf's whoosh (source b, nothing in her folder fits)",
          dm["hook"]["choice"] == "fav:whoosh-fast", dm["hook"])
    check("a card gets her Epidemic thud (source c), trimmed to the motion but never under a hit's length",
          dm["breakaway"]["choice"].startswith("epi:home/SFX/") and dm["breakaway"]["trim"] == SP.MIN_HIT_S, dm["breakaway"])
    check("a type-on gets her Epidemic keyboard, trimmed to EXACTLY the type-on (0.3 s)",
          src["typer"] == "epidemic" and "keyboard" in dm["typer"]["choice"] and dm["typer"]["trim"] == 0.3, dm["typer"])
    check("a count-up gets a tick from her folder, never longer than the sound itself",
          dm["counter"]["choice"] == "folder:sounds/quiet-tick.wav" and dm["counter"]["trim"] == 0.4, dm["counter"])
    check("a plain fade falls through to the engine's shipped CC0 library (source d)",
          dm["fade"]["choice"] == "lib:studio-open" and src["fade"] == "library"
          and "/cc0/" in dm["fade"]["file"].replace(os.sep, "/"), dm["fade"])
    check("every default is a sound effect (never a song) with a trim", all(v and v["trim"] > 0 for v in dm.values()), dm)

    print("confessional: no default sounds")
    json.dump({"register": "confessional"}, open(os.path.join(jd, "review", "choices.json"), "w", encoding="utf-8"))
    d = SP.defaults_for(jd)
    check("a confessional reel's defaults are all 'no sound', with the reason in plain words",
          d["quiet"] and d["register"] == "confessional" and all(m["default"] is None for m in d["moments"])
          and "confessional" in (d["reason"] or ""), d["reason"])
    p = SP.apply_defaults(jd)
    check("apply_defaults adds nothing on a confessional reel; its looks show 'no sound'", p["applied"] == 0
          and p["moments_without_sound"] == N_MOMENTS - 1 and p["quiet"] and not os.path.exists(SP.sound_json(jd)), p)
    check("teaching passed in outranks nothing she recorded: defaults_for(job, 'teaching') does give sounds",
          all(m["default"] for m in SP.defaults_for(jd, "teaching")["moments"]))
    check("a register that isn't one is refused", refused(SP.defaults_for, jd, "loud") is not None)
    os.remove(os.path.join(jd, "review", "choices.json"))

    print("apply_defaults: fill the empty looks, never overwrite")
    p = SP.read(jd)
    rows = {r["id"]: r for r in p["cues"]}
    pl = next(r for r in p["cues"] if r["origin"] == "plan")
    check("the planned cue on pop1's entrance IS pop1's sound (a moment, anchored, no empty row for pop1)",
          pl["moment"] and pl["anchor"] == {"layer": "pop1", "at": "entrance"} and "look:pop1" not in rows, pl)
    check("every other look shows an empty 'no sound' row, counted", p["moments"] == N_MOMENTS
          and p["moments_without_sound"] == N_MOMENTS - 1
          and all(rows[f"look:{k}"]["empty"] for k in MOMENTS if k != "pop1"), p["moments_without_sound"])
    p = SP.apply_defaults(jd)
    rows = {r["id"]: r for r in p["cues"]}
    check("apply_defaults fills every empty look and nothing else", p["applied"] == N_MOMENTS - 1
          and p["moments_without_sound"] == 0 and len([r for r in p["cues"] if r["origin"] == "plan"]) == 1, p["applied"])
    hk = rows["look:hook"]
    check("a look's row: moment, anchor, kind, motion, source, its own trim and the engine's auto level",
          hk["moment"] and hk["anchor"] == {"layer": "hook", "at": "entrance"} and hk["kind"] == "blur"
          and hk["motion_s"] == 0.5 and hk["source"] == "capcut" and hk["trim"] == 0.5 and hk["gain_how"] == "auto"
          and hk["on"] and hk["nudge"] == 0.0 and hk["origin"] == "look", hk)
    check("pop2 follows the planned pop on pop1 with a different sound (her folder's)",
          rows["look:pop2"]["choice"] == "folder:sounds/my-pop.wav", rows["look:pop2"]["choice"])
    stored = json.load(open(SP.sound_json(jd), encoding="utf-8"))
    check("looks' sounds are stored ANCHORED to the look, never a time", all(
        a["anchor"]["at"] == "entrance" and "t" not in a for a in stored["added"]) and stored["sfx_enabled"] is True,
          stored["added"][:2])
    before = open(SP.sound_json(jd), encoding="utf-8").read()
    p2 = SP.apply_defaults(jd)
    check("apply_defaults twice changes nothing (idempotent)", p2["applied"] == 0
          and json.loads(open(SP.sound_json(jd), encoding="utf-8").read())["added"] == json.loads(before)["added"])

    print("a sound follows its look")
    write_looks(jd, dict(OFFSETS, hook=2.0), extra=[
        {"name": "captions", "dir": "hf-graphics/captions", "offset": 0, "dur": 20, "captions": True}])
    p = SP.read(jd)
    hk = next(r for r in p["cues"] if r["id"] == "look:hook")
    check("the hook moved 1 s later in looks.json: its sound moved with it (2.2 s)", near(hk["t"], 2.2), hk["t"])
    plan = json.load(open(os.path.join(jd, "caption-plan.json"), encoding="utf-8"))
    sfx, _m = SP.for_build(jd, plan["sfx"], plan["music"], say=lambda *_: None)
    hook_cue = [c for c in sfx if c.get("_sound") == "look" and c["file"].endswith("whoosh-fast.mp3")]
    check("...and the build plays it there", hook_cue and near(hook_cue[0]["at"], 2.2), hook_cue)

    print("edits: none, original, add, nudge, remove, the reel-wide switch")
    p = SP.swap(jd, "look:breakaway", "none")
    br = next(r for r in p["cues"] if r["id"] == "look:breakaway")
    check("'none' makes that look silent: No sound here (not empty, so defaults leave it alone)",
          br["none"] and not br["on"] and not br["empty"] and br["name"] == "No sound here" and br["file"] is None, br)
    check("...apply_defaults won't refill it", SP.apply_defaults(jd)["applied"] == 0)
    sfx, _m = SP.for_build(jd, plan["sfx"], plan["music"], say=lambda *_: None)
    check("...and the build plays nothing on it", not [c for c in sfx if near(c["at"], 5.05)], sfx)
    p = SP.swap(jd, "look:breakaway", "original")
    br = next(r for r in p["cues"] if r["id"] == "look:breakaway")
    check("'original' puts the motion-matched sound back", br["on"] and br["source"] == "epidemic" and not br["none"], br)
    p = SP.swap(jd, "look:breakaway", "folder:sounds/loud-ding.mp3")
    br = next(r for r in p["cues"] if r["id"] == "look:breakaway")
    check("a sound she picks for a look is hers (swapped), still anchored", br["swapped"] and br["source"] == "favorite"
          and br["anchor"]["layer"] == "breakaway", br)
    p2 = SP.add_cue(jd, "folder:sounds/my-pop.wav", layer="breakaway")   # a look that has one: hers plays too, same moment
    two = next(r for r in p2["cues"] if r["id"] == p2["added_id"])
    check("a second sound on a look that has one plays with it, at the look's moment (never refused)",
          two["origin"] == "free" and abs(two["t"] - br["t"]) < 1e-3, two)
    SP.remove_cue(jd, p2["added_id"])
    p = SP.add_cue(jd, "folder:sounds/loud-ding.mp3", t=6.5, word=12)
    nid = p["added_id"]
    fr = next(r for r in p["cues"] if r["id"] == nid)
    check("a sound at the playhead: stored at its cut time, with the word she was on", nid == "add-1"
          and fr["origin"] == "free" and fr["t"] == 6.5 and fr["word"] == 12 and not fr["moment"] and fr["on"], fr)
    p = SP.nudge(jd, nid, 0.3)
    check("nudge moves it later", next(r for r in p["cues"] if r["id"] == nid)["t"] == 6.8)
    end = SP._cut_length(jd)
    p = SP.nudge(jd, nid, 600)                                       # a drag far past the end of the timeline
    fr = next(r for r in p["cues"] if r["id"] == nid)
    check("a drag past her cut's end lands the sound at the end (never past it)", near(fr["t"], end), (fr, end))
    p = SP.nudge(jd, nid, -600)
    fr = next(r for r in p["cues"] if r["id"] == nid)
    check("a drag before 0:00 lands it at 0:00 (its nudge is exactly that far, nothing hidden)",
          fr["t"] == 0.0 and near(fr["nudge"], -6.5), fr)
    p = SP.nudge(jd, nid, 7.5)
    fr = next(r for r in p["cues"] if r["id"] == nid)
    check("a drag moves a sound more than a second at once", near(fr["t"], 7.5) and near(fr["nudge"], 1.0), fr)
    plan_id = next(r["id"] for r in p["cues"] if r["origin"] == "plan")
    p = SP.nudge(jd, plan_id, -0.2)
    check("a planned cue nudges too (its id stays)", next(r for r in p["cues"] if r["id"] == plan_id)["t"] == 2.85)
    sfx, _m = SP.for_build(jd, plan["sfx"], plan["music"], say=lambda *_: None)
    check("the build plays the nudged planned cue earlier and her added sound at its nudged time",
          near(sfx[0]["at"], 2.85) and any(near(c["at"], 7.5) and c["_sound"] == "added" and "trim" not in c for c in sfx),
          [(c["at"], c.get("_sound")) for c in sfx])
    p = SP.nudge(jd, "look:hook", -0.1)
    check("a look's sound nudges off its entrance, and still follows the look",
          near(next(r for r in p["cues"] if r["id"] == "look:hook")["t"], 2.1))
    check("a nudge must be a number", refused(SP.nudge, jd, nid, "later") is not None)
    check("add needs the playhead OR a look, not both, not neither",
          refused(SP.add_cue, jd, "folder:sounds/my-pop.wav") is not None
          and refused(SP.add_cue, jd, "folder:sounds/my-pop.wav", t=1.0, layer="hook") is not None)
    pe = SP.add_cue(jd, "folder:sounds/my-pop.wav", t=99); ps = SP.add_cue(jd, "folder:sounds/my-pop.wav", t=-1)
    te = next(r for r in pe["cues"] if r["id"] == pe["added_id"])["t"]; ts = next(r for r in ps["cues"] if r["id"] == ps["added_id"])["t"]
    check("a time past either end lands at that end (never refused)", ts == 0.0 and te <= SP._cut_length(jd) + 1e-6 and te > 1, (ts, te))
    SP.remove_cue(jd, pe["added_id"]); SP.remove_cue(jd, ps["added_id"])
    pw = SP.add_cue(jd, "folder:sounds/warm-song.m4a", t=1.0)
    check("a song added as a sound effect is hers to use", any(r["id"] == pw["added_id"] for r in pw["cues"]))
    SP.remove_cue(jd, pw["added_id"])
    p = SP.remove_cue(jd, nid)
    check("remove takes a sound she added away", nid not in {r["id"] for r in p["cues"]})
    p = SP.remove_cue(jd, "look:orbit")
    check("remove on a look puts it back to 'no sound yet'", next(r for r in p["cues"] if r["id"] == "look:orbit")["empty"])
    p = SP.add_cue(jd, "folder:sounds/my-pop.wav", layer="orbit")
    ob = next(r for r in p["cues"] if r["id"] == "look:orbit")
    check("add on a look fills it, anchored", p["added_id"] == "look:orbit" and ob["on"] and ob["swapped"], ob)
    check("removing a look's sound that isn't there is refused", refused(SP.remove_cue, jd, "look:nope") is not None)
    p = SP.toggle(jd, "look:pop3", False)
    check("a look's sound switches off and back on", not next(r for r in p["cues"] if r["id"] == "look:pop3")["on"]
          and next(r for r in SP.toggle(jd, "look:pop3", True)["cues"] if r["id"] == "look:pop3")["on"])

    p = SP.set_sfx_enabled(jd, False)
    sfx, music = SP.for_build(jd, plan["sfx"], plan["music"], say=lambda *_: None)
    check("Sound effects off: no sound effects in the build, the music bed untouched", p["sfx_enabled"] is False
          and sfx == [] and music == plan["music"], (sfx, music))
    check("the switch must be a yes or no", refused(SP.set_sfx_enabled, jd, "off") is not None)
    SP.set_sfx_enabled(jd, True)

    print("for_build: what the builds get from her looks")
    said = []
    sfx, _m = SP.for_build(jd, plan["sfx"], plan["music"], say=said.append)
    looks = [c for c in sfx if c.get("_sound") == "look"]
    ms = {m["layer"]: m for m in SP.moments(jd)}
    check("one cue per look that has a sound, in time order, after the plan's own cue",
          sfx[0]["file"] == lib and len(looks) == N_MOMENTS - 1 and [c["at"] for c in looks] == sorted(c["at"] for c in looks),
          len(looks))
    check("each: an absolute file that exists, no fixed gain (auto-leveled), a trim matching its motion",
          all(os.path.isabs(c["file"]) and os.path.isfile(c["file"]) and "gain_db" not in c and c["trim"] > 0 for c in looks))
    ty = next(c for c in looks if near(c["at"], ms["typer"]["t"]))
    check("the type-on's sound is trimmed to exactly its motion", ty["trim"] == 0.3, ty)
    check("the build log names her look sounds", any("on her looks" in s for s in said), said)
    cues, _m = SP.cues_for_build(jd)
    check("a raw / Super Yap driver gets them too, auto-leveled", len(cues) == len(sfx)
          and all(c["volume"] is None for c in cues[1:]), len(cues))
    write_looks(jd, {k: v for k, v in dict(OFFSETS, hook=2.0).items() if k != "slider"})
    said = []
    p = SP.read(jd)
    sfx, _m = SP.for_build(jd, plan["sfx"], plan["music"], say=said.append)
    check("a look taken off the reel: its sound is an orphan on the page and left out of the build, said plainly",
          "look:slider" in p["orphans"] and not any(near(c["at"], 13.15) for c in sfx)
          and any("no longer on the reel" in s for s in said), (p["orphans"], said))
    write_looks(jd, dict(OFFSETS, hook=2.0))


def capcut_checks(tmp, SP, jd, lib, loud):
    """Raw / Super Yap (cleanyap.add_sound_plan) and the handoff beside a well-done or medium reel
    (capcut_handoff.main), each with VectCut's calls recorded instead of sent."""
    import types
    sys.modules.setdefault("requests", types.ModuleType("requests"))
    import audio_levels
    try:
        import cleanyap
    except Exception as e:          # noqa: BLE001 — a bare environment without the builder's own deps
        print(f"  SKIP  the CapCut builders aren't importable here ({type(e).__name__}: {e})")
        return
    prog = os.path.join(jd, "outputs", "my-reel.mp4")
    calls = []
    real_call = cleanyap.call
    cleanyap.call = lambda ep, _strict=True, **kw: calls.append((ep, kw)) or {"success": True, "output": {}}
    try:
        placed, bed = cleanyap.add_sound_plan("d1", jd)
    finally:
        cleanyap.call = real_call
    audio = [kw for ep, kw in calls if ep == "add_audio"]
    sfx = [kw for kw in audio if kw["track_name"].startswith("sfx")]
    check("raw route: every cue that's on is placed, her swap included", placed == 2 and len(sfx) == 2
          and sfx[0]["audio_url"] == loud and sfx[0]["target_start"] == 1.0, sfx)
    want = audio_levels.sfx_volume_for(loud, prog, 0.3)                 # the north star rule every route shares
    check("raw route: her swapped sound is auto-leveled against the cut", abs(sfx[0]["volume"] - want) < 1e-3,
          (sfx[0]["volume"], want))
    check("raw route: the plan's hand-set level is kept", abs(sfx[1]["volume"] - audio_levels.to_linear(-3)) < 1e-3)
    mus = [kw for kw in audio if kw["track_name"] == "music"]
    check("raw route: her song goes on its own track at her level", len(mus) == 1 and mus[0]["audio_url"].endswith(
        "warm-song.m4a") and abs(mus[0]["volume"] - audio_levels.to_linear(-12)) < 1e-3, mus)
    SP.toggle(jd, "mine@2.500", False)
    calls.clear()
    cleanyap.call = lambda ep, _strict=True, **kw: calls.append((ep, kw)) or {"success": True, "output": {}}
    try:
        placed, _b = cleanyap.add_sound_plan("d1", jd)
    finally:
        cleanyap.call = real_call
    check("raw route: a cue she switched off is not placed", placed == 1)

    import importlib, draft_safety
    handoff = importlib.import_module("capcut_handoff")
    overlay = os.path.join(tmp, "ov.mov")
    ff("-f", "lavfi", "-i", "color=black@0.0:s=108x192:d=1:r=30,format=yuva444p10le",
       "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", overlay)
    saved = (handoff.ROOT, handoff.call, draft_safety.require_capcut_quit, draft_safety.next_version,
             cleanyap.finalize, sys.argv, os.environ.get("REEL_NO_DEFAULT_MOTION"))
    hcalls = []
    try:
        handoff.ROOT = tmp
        handoff.call = lambda ep, **kw: hcalls.append((ep, kw)) or {"draft_id": "d2"}
        draft_safety.require_capcut_quit = lambda *a, **k: None
        draft_safety.next_version = lambda base: f"{base} 1.1"
        cleanyap.finalize = lambda *a, **k: None
        sys.argv = ["capcut_handoff.py", "my-reel", "--overlay", overlay, "--pack", "Butter", "--one-clip"]
        out = io.StringIO()
        _stdout, sys.stdout = sys.stdout, out
        try:
            handoff.main()
        finally:
            sys.stdout = _stdout
    finally:
        (handoff.ROOT, handoff.call, draft_safety.require_capcut_quit, draft_safety.next_version,
         cleanyap.finalize, sys.argv, _env) = saved
        if _env is None:
            os.environ.pop("REEL_NO_DEFAULT_MOTION", None)
        else:
            os.environ["REEL_NO_DEFAULT_MOTION"] = _env
    ha = [kw for ep, kw in hcalls if ep == "add_audio"]
    hs = [kw for kw in ha if kw["track_name"].startswith("sfx")]
    her = lambda u: u == loud or (os.path.basename(os.path.dirname(u)) == "capcut"             # her swap, cut to its motion
                                  and os.path.basename(u).startswith(os.path.splitext(os.path.basename(loud))[0] + "-"))
    check("handoff: the cue she switched off is left out, her swap plays", len(hs) == 1 and her(hs[0]["audio_url"]),
          (hs, out.getvalue()[-500:]))
    check("handoff: each cue at the level the finished video gives it", hs and abs(hs[0]["volume"] - want) < 1e-3,
          hs)
    hm = [kw for kw in ha if kw["track_name"] == "music"]
    check("handoff: her music bed on its own track, at her level", len(hm) == 1 and hm[0]["audio_url"].endswith(
        "warm-song.m4a") and abs(hm[0]["volume"] - audio_levels.to_linear(-12)) < 1e-3, (hm, out.getvalue()[-400:]))
    SP.toggle(jd, "mine@2.500", True)


def bake_checks(tmp, SP, lib):
    eng = os.path.join(tmp, "engine")
    os.makedirs(os.path.join(eng, "product"))
    for f in os.listdir(PRODUCT):
        if f.endswith(".py"):
            shutil.copy(os.path.join(PRODUCT, f), os.path.join(eng, "product", f))
    job = os.path.join(eng, "projects", "job")
    os.makedirs(os.path.join(job, "outputs"))
    base = os.path.join(job, "outputs", "job.mp4")
    ff("-f", "lavfi", "-i", "color=gray:s=108x192:d=4:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
       "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", base)
    tone(os.path.join(job, "audio", "bed.wav"), 4, 440, -12)
    cue = os.path.join(job, "audio", "cue.wav")
    tone(cue, 0.6, 1000, -3)
    overlay = os.path.join(tmp, "overlay.mov")
    ff("-f", "lavfi", "-i", "color=black@0.0:s=108x192:d=1:r=30,format=yuva444p10le",
       "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", overlay)
    plan = {"sfx": [{"file": cue, "at": 0.2, "gain_db": 0}],
            "music": {"file": "bed.wav", "at": 2.0, "fade_in": 0.05, "fade_out": 0.1, "gain_db": 0, "loop": False}}
    json.dump(plan, open(os.path.join(job, "caption-plan.json"), "w", encoding="utf-8"))

    def bake(name):
        out = os.path.join(tmp, name)
        env = dict(os.environ, JOB="job", OVERLAY=overlay, OUT=out, VENC="libx264", PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, os.path.join(eng, "product", "build-reel-mp4.py")],
                           capture_output=True, text=True, env=env, timeout=600)
        return r.returncode, r.stdout + r.stderr, out

    rc, said, out = bake("as-planned.mp4")
    cue_on, bed_on = rms_db(out, 0.25, 0.7), rms_db(out, 2.5, 3.6)
    check("as planned: the cue and the bed both play", rc == 0 and cue_on > -60 and bed_on > -60, (rc, cue_on, bed_on, said[-600:]))
    cid = SP.read(job)["cues"][0]["id"]
    SP.toggle(job, cid, False)
    SP.set_music(job, on=False)
    rc, said, out = bake("her-edits.mp4")
    cue_off, bed_off = rms_db(out, 0.25, 0.7), rms_db(out, 2.5, 3.6)
    check("her edits: the cue she switched off is silent", rc == 0 and cue_off < -80, (rc, cue_off, said[-600:]))
    check("her edits: the bed she turned off is silent", bed_off < -80, bed_off)
    check("the bake log says it applied her edits", "her Sound edits" in said, said[-600:])
    SP.toggle(job, cid, True)
    SP.set_music(job, on=True, level_db=-20)
    rc, said, out = bake("quieter-bed.mp4")
    bed_low = rms_db(out, 2.5, 3.6)
    check("a music level she set is the level the bake uses (20 dB down)", rc == 0 and abs((bed_on - bed_low) - 20) < 1.5,
          (bed_on, bed_low, said[-400:]))

    # a sound on a look plays at the look's entrance, and moves with the look
    tone(os.path.join(job, "audio", "pop2.wav"), 0.6, 1500, -3)
    comp = os.path.join(job, "hf-graphics", "L1")
    os.makedirs(comp)
    open(os.path.join(comp, "index.html"), "w", encoding="utf-8").write(
        '<script>window.__timelines=window.__timelines||{};const tl=gsap.timeline({paused:true});'
        'tl.fromTo("#w",{autoAlpha:0,scale:.5},{autoAlpha:1,scale:1,duration:.45,ease:"back.out(2)"},0.5);'
        'window.__timelines["L1"]=tl;</script>')

    def looks(off):
        os.makedirs(os.path.join(job, "review"), exist_ok=True)
        json.dump({"layers": [{"name": "L1", "dir": "hf-graphics/L1", "offset": off, "dur": 1.0}]},
                  open(os.path.join(job, "review", "looks.json"), "w", encoding="utf-8"))
    looks(1.0)
    SP.set_music(job, on=False)
    SP.add_cue(job, "job:audio/pop2.wav", layer="L1")
    rc, said, out = bake("on-a-look.mp4")
    at_look = rms_db(out, 1.55, 1.85)
    # (the scratch cut is silent, so auto-level sets the cue low: present = well above digital silence)
    check("the bake plays her look's sound at its entrance (1.0 + 0.5 s)", rc == 0 and at_look > -85,
          (rc, at_look, said[-600:]))
    looks(2.5)
    rc, said, out = bake("look-moved.mp4")
    old_spot, new_spot = rms_db(out, 1.55, 1.85), rms_db(out, 3.05, 3.35)
    check("the look moved 1.5 s later: the bake plays its sound there, and nothing where it was",
          rc == 0 and old_spot < -95 and new_spot > -85, (old_spot, new_spot, said[-600:]))
    SP.set_sfx_enabled(job, False)
    rc, said, out = bake("sfx-off.mp4")
    check("Sound effects off: the bake plays no sound effects at all", rc == 0 and rms_db(out, 0.25, 0.7) < -95
          and rms_db(out, 3.05, 3.35) < -95, said[-400:])



def look_own_sound(SP, tmp):
    """A look that carries its own sound (an <audio> in its page, like a Sandbox echo): a row on her Sound tab she can
    mute (never swap), played by her preview, laid into every build at the look's offset + data-start, trimmed to its
    data-duration, at the engine's level against her voice with its data-volume on top; muted, it's left out."""
    jd = os.path.join(tmp, "projects", "own-sound")
    make_reel(jd, "own-sound", [])
    look = os.path.join(jd, "hf-graphics", "_looks", "add-w3", "echo")
    tone(os.path.join(look, "assets", "chamber.wav"), 2.0, 440, -6)
    os.makedirs(look, exist_ok=True)
    open(os.path.join(look, "index.html"), "w", encoding="utf-8").write(
        '<div data-composition-id="echo-1" data-duration="1.5"><audio id="echo" class="clip" src="assets/chamber.wav" '
        'data-start="0.25" data-duration="3.44" data-volume="0.5"></audio><audio src="https://example.com/x.mp3"></audio></div>')
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    json.dump({"layers": [{"name": "add-w3", "dir": "hf-graphics/_looks/add-w3/echo", "id": "echo-1", "offset": 1.0, "dur": 1.5,
                           "look_name": "Echo"}]}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    os_ = SP.look_sounds(jd)
    check("own sound: a look's <audio> is found (a web address never is)", len(os_) == 1 and os_[0]["at"] == 1.25
          and abs(os_[0]["trim"] - 1.25) < 1e-6 and os_[0]["volume"] == 0.5, os_)
    rows = [c for c in SP.read(jd)["cues"] if c["origin"] == "own"]
    check("own sound: a row on her Sound tab, on, part of its look", len(rows) == 1 and rows[0]["on"] and rows[0]["on_look"] == "add-w3"
          and rows[0]["name"] == "Echo's own sound", rows)
    full = SP.auto_sfx_gain(os_[0]["file"], SP._programme(jd), 1.25, SP._ducks(jd)[0])
    check("own sound: leveled against her voice, then its own volume (0.5 = -6 dB)", abs(rows[0]["gain_db"] - round(full - 6.0206, 1)) < 0.11, (rows[0]["gain_db"], full))
    check("own sound: her preview plays it", any(c["id"] == rows[0]["id"] for c in SP.playback(jd)["cues"]))
    sfx, _m = SP.for_build(jd, [], None, say=lambda *_: None)
    own = [c for c in sfx if c.get("_sound") == "own"]
    check("own sound: every build lays it in at its moment, trimmed, at that level", len(own) == 1 and own[0]["at"] == 1.25
          and abs(own[0]["trim"] - 1.25) < 1e-6 and own[0]["gain_db"] == rows[0]["gain_db"], own)
    check("own sound: it can't be swapped (it's the look), only muted", refused(SP.swap, jd, rows[0]["id"], "original") is not None)
    SP.set_sfx_enabled(jd, False)
    check("own sound: the Sound effects switch leaves it (it's the look, not an effect)",
          any(c.get("_sound") == "own" for c in SP.for_build(jd, [], None, say=lambda *_: None)[0]))
    SP.set_sfx_enabled(jd, True)
    SP.toggle(jd, rows[0]["id"], False)
    check("own sound: muted on her Sound tab, no build plays it", not any(c.get("_sound") == "own" for c in SP.for_build(jd, [], None, say=lambda *_: None)[0])
          and not [c for c in SP.read(jd)["cues"] if c["origin"] == "own"][0]["on"])
    SP.toggle(jd, rows[0]["id"], True)
    import finish
    out = finish._mix_sound(jd, os.path.join(jd, "outputs", "own-sound.mp4"))
    def band(path, a0, b0):                                  # the echo's own pitch (440 Hz), apart from her voice (200 Hz)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                            f"atrim={a0}:{b0},bandpass=f=440:width_type=h:w=30,astats", "-f", "null", "-"], capture_output=True, text=True)
        m = re.findall(r"RMS level dB:\s*(-?inf|-?[\d.]+)", r.stderr)
        return -999.0 if not m or "inf" in m[-1] else float(m[-1])
    check("own sound: the MP4 export mixes it in at its moment (its pitch there, not before it)",
          bool(out) and band(out, 1.4, 2.2) > band(out, 0.3, 1.1) + 15, (out and band(out, 1.4, 2.2), out and band(out, 0.3, 1.1)))


def test_added_sounds_follow_their_word():
    """Her cut changed: a sound she added on a word moves with it; one whose word she cut rests with its word (her own
    on/off untouched) and plays again when her word comes back."""
    import sound_plan as SP_
    store = {"added": [{"id": "add-1", "anchor": None, "t": 5.0, "word": 12, "on": True},
                       {"id": "add-2", "anchor": None, "t": 9.0, "word": 30, "on": True},
                       {"id": "add-3", "anchor": {"layer": "x"}, "t": 2.0, "word": 4, "on": True}],
             "bad": None}
    saved = {}
    real = (SP_.read, SP_._store, SP_._save)
    SP_.read = lambda jd: {"cues": [], "music": {}}
    SP_._store = lambda jd: store
    SP_._save = lambda jd, plan, added=None, sfx_enabled=None: saved.update(added=added)
    try:
        n = SP_.retime_added("/nowhere", {12: (3.2, 3.5), 4: (1.0, 1.2)})
    finally:
        SP_.read, SP_._store, SP_._save = real
    a = {x["id"]: x for x in saved.get("added", [])}
    first = n == 2 and a["add-1"]["t"] == 3.2 and a["add-2"].get("word_cut") is True and a["add-2"]["on"] is True \
        and a["add-3"]["t"] == 2.0
    store["added"] = saved["added"]
    SP_.read = lambda jd: {"cues": [], "music": {}}
    SP_._store = lambda jd: store
    SP_._save = lambda jd, plan, added=None, sfx_enabled=None: saved.update(added=added)
    try:                                                     # her word is back: so is its sound
        SP_.retime_added("/nowhere", {12: (3.2, 3.5), 30: (7.0, 7.4), 4: (1.0, 1.2)})
    finally:
        SP_.read, SP_._store, SP_._save = real
    a = {x["id"]: x for x in saved.get("added", [])}
    return first and "word_cut" not in a["add-2"] and a["add-2"]["on"] is True and a["add-2"]["t"] == 7.0

if __name__ == "__main__":
    sys.exit(main())
