#!/usr/bin/env python3
"""resolve_export.py — the Finish step's DaVinci Resolve route.

One finished visual-editor reel, ready for DaVinci Resolve, two ways out, from the same pieces as the CapCut
export: her finished cut, one clip per kept line, each look on its own track, each sound on its own clip, her
music bed, her voice alone on its own track.

    projects/<job>/outputs/<job> resolve/
      media/                         her cut, the looks, the sounds, the music (copy-on-write clones)
      <job> overlay.fcpxml           hand import: everything on the timeline, her rendered captions ON
      <job> native.fcpxml            hand import: same, rendered captions OFF (real captions instead)
      <job> native captions.srt      hand import: her captions, real and retypeable
      Build <job> overlay.lua        one click: the whole reel in a new project, rendered captions ON
      Build <job> native.lua         one click: the same, with real captions
      project settings.fcpxml        a one-frame seed that sets the project's rate and size
      plan.json                      what every route was built from

Captions default to her exact look (the rendered overlay); native (real, retypeable) captions are the alternative
in the same folder. FCPXML + a Workspace > Scripts one-click, so this needs no DaVinci scripting and no Resolve
installed to produce it (free Resolve blocks external scripting). Ported from the tested prototype.

    python3 product/resolve_export.py <job>
"""
import json, math, os, re, shutil, subprocess, sys
import xml.sax.saxutils as sx
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(HERE))
import audio_levels, sound_plan, voice_level  # noqa: E402
from cut_placement import played_length  # noqa: E402

FPS_NAMES = {Fraction(24000, 1001): "23.976", Fraction(24): "24", Fraction(25): "25", Fraction(30000, 1001): "29.97",
             Fraction(30): "30", Fraction(50): "50", Fraction(60000, 1001): "59.94", Fraction(60): "60"}
MAX_CAPTION_CHARS = 18          # a line that stays on a tall frame at Resolve's default caption size


def run(*a):
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout


def probe(path, entries, stream="v:0"):
    out = run("ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={entries}", "-of", "json", str(path))
    return (json.loads(out).get("streams") or [{}])[0]


def dur(path):
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)).strip())


def rate(path):
    return Fraction(probe(path, "r_frame_rate")["r_frame_rate"])


def clone(src, dst):
    dst = Path(dst)
    if dst.exists() and dst.stat().st_size == Path(src).stat().st_size:
        return dst
    if subprocess.run(["cp", "-c", str(src), str(dst)], capture_output=True).returncode:
        shutil.copy2(src, dst)
    return dst


def srt_time(s):
    ms = round(max(0.0, s) * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def caption_rows(jd, job, cap, bdur):
    """[(start, end, text)] on the cut's clock. A single-word look keeps its own words and times; any other style, and a
    reel with no caption look at all, gets short phrases from her kept-words transcript."""
    jd = Path(jd)
    skips = (cap or {}).get("skips") or []
    off = float((cap or {}).get("offset") or 0)
    hidden = lambda t: any(a <= t < b for a, b in skips)
    rows = []
    if cap and cap.get("look") == "single-word":
        comp = jd / cap["dir"] / "index.html"
        if comp.exists():
            html = comp.read_text(encoding="utf-8")
            for a, d, w in re.findall(r'data-start="([\d.]+)" data-duration="([\d.]+)"[^>]*><div class="capword[^"]*"[^>]*><span id="cw\d+">([^<]*)<', html):
                a, d = float(a) + off, float(d)
                if w.strip() and not hidden(a):
                    rows.append((a, a + d, w.strip()))
    tfile = jd / f"outputs/{job}.transcript.json"
    if not rows and tfile.exists():
        words = [w for w in json.load(open(tfile, encoding="utf-8"))["words"] if w.get("type") == "word"]
        cur = []
        groups = []
        for i, w in enumerate(words):
            cur.append(w)
            text = " ".join(x["text"] for x in cur)
            nxt = words[i + 1] if i + 1 < len(words) else None
            over = nxt and len(text) + 1 + len(nxt["text"]) > MAX_CAPTION_CHARS
            if w["text"][-1] in ".?!" or (nxt and nxt["start"] - w["end"] > 0.35) or over or not nxt:
                groups.append(cur)
                cur = []
        for g in groups:
            a = max(0.0, g[0]["start"] - 0.08)
            if not hidden(a):
                rows.append((a, g[-1]["end"], " ".join(x["text"] for x in g)))
    fixed = []
    for k, (a, b, t) in enumerate(rows):
        nxt = rows[k + 1][0] if k + 1 < len(rows) else bdur
        fixed.append((round(a, 3), round(min(max(b, a + 0.1), nxt, bdur), 3), t))
    return fixed


def build_plan(job, jd, source, kit):
    """Everything a route is built from. `source` is her finished cut with her Filter and covered faces already baked
    in (the engine computes it); `jd` the job dir; `kit` the output folder. Writes media/ (clones), the SRT, plan.json."""
    jd, kit = Path(jd), Path(kit)
    media = kit / "media"
    media.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    bdur = dur(source)
    base = clone(source, media / f"{job} cut.mp4")
    before, _peak = voice_level.measure(str(base))        # an older reel's voice is hotter than today's target, so her
    moved = 0.0                                           # effects would clip on top of it; the kit's copy is levelled, hers isn't
    if before is not None and before > -30:
        moved = voice_level.level(str(base)).get("gain_db", 0.0)     # levels she set by hand move with her voice
    picture, voice = media / f"{job} picture.mp4", media / f"{job} voice.wav"     # Resolve ignores "picture only" on a clip
    run("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(base), "-map", "0:v:0", "-c", "copy", "-movflags", "+faststart", str(picture))
    run("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(base), "-map", "0:a:0", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(voice))
    fps = rate(base)
    if fps not in FPS_NAMES:
        fps = min(FPS_NAMES, key=lambda f: abs(f - fps))
    w, h = (lambda s: (int(s["width"]), int(s["height"])))(probe(base, "width,height"))
    tw, th = (1080, 1920) if h > w else (1920, 1080)

    segs = json.load(open(jd / "transcript/cuts.json", encoding="utf-8"))["segments"]
    lens = [played_length(x) for x in segs if "start" in x and "end" in x]
    if len(lens) >= 2 and abs(sum(lens) - bdur) <= 0.1:          # one clip per kept line, as the CapCut export
        marks = [0.0]
        for d in lens[:-1]:
            marks.append(marks[-1] + d)
        marks.append(bdur)
        pieces = [[round(a, 4), round(b, 4)] for a, b in zip(marks, marks[1:]) if b - a > 0.02]
    else:
        pieces = [[0.0, round(bdur, 4)]]

    doc = json.load(open(jd / "review/looks.json", encoding="utf-8")) if (jd / "review/looks.json").exists() else {"layers": []}
    looks = [L for L in doc.get("layers", []) if not L.get("off")]
    looks.sort(key=lambda L: (not L.get("behind"), bool(L.get("captions"))))     # behind her first, captions on top
    finish = jd / "hf-graphics/finish"
    layers, left_out, cap = [], [], None
    for L in looks:
        if L.get("captions"):
            cap = L
        src = next((finish / f"{L['name']}{e}" for e in (".mov", ".mp4") if (finish / f"{L['name']}{e}").exists()), None)
        if not src:
            left_out.append(L["name"])
            continue
        at = float(L.get("offset") or 0)
        length = min(float(L.get("dur") or 1e9), dur(src), bdur - at)
        if length <= 0.02:
            continue
        f = clone(src, media / src.name)
        layers.append({"name": L["name"], "file": f.name, "at": round(at, 4), "len": round(length, 4), "captions": bool(L.get("captions"))})
        out = finish / f"behind-{L['name']}.mov"
        if L.get("behind") and out.exists():
            g = clone(out, media / out.name)
            layers.append({"name": out.stem, "file": g.name, "at": round(at, 4), "len": round(min(length, dur(out)), 4), "captions": False})

    if not looks:                                         # the original widget road: its rendered overlay, when it has one
        renders = sorted((jd / "renders").glob("*.mov"), key=os.path.getmtime) if (jd / "renders").is_dir() else []
        if renders:
            f = clone(renders[-1], media / renders[-1].name)
            layers.append({"name": f.stem, "file": f.name, "at": 0.0, "len": round(min(dur(f), bdur), 4), "captions": False})

    # the sounds, each its own file at the level the finished video gives it
    cues, music = sound_plan.cues_for_build(job)
    sounds, lanes = [], []
    for i, c in enumerate(sorted(cues, key=lambda x: x["t"])):
        if c["t"] >= bdur - 0.02:
            continue
        trim = float(c.get("trim") or 0) or None
        vol = c["volume"] * 10 ** (moved / 20) if c.get("volume") is not None else audio_levels.sfx_volume_for(c["file"], str(base), trim, audio_levels.SFX_DUCK_DB)
        name = f"sfx-{i + 1:03d}-{Path(c['file']).stem[:32]}.wav"
        af = ([f"atrim=0:{trim:.3f}", f"afade=t=out:st={max(0.0, trim - 0.12):.3f}:d=0.12"] if trim else []) + [f"volume={vol:.5f}"]
        run("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", c["file"], "-map", "0:a:0", "-af", ",".join(af), "-ar", "48000", "-ac", "2", str(media / name))
        length = min(dur(media / name), bdur - c["t"])
        lane = next((k for k, free in enumerate(lanes) if c["t"] >= free), len(lanes))
        if lane == len(lanes):
            lanes.append(0.0)
        lanes[lane] = c["t"] + length + 0.02
        sounds.append({"file": name, "at": round(c["t"], 4), "len": round(length, 4), "lane": lane})
    bed = None
    if isinstance(music, dict) and music.get("file") and os.path.exists(music["file"]):
        at = float(music.get("at") or 0)
        length = bdur - at
        gain = float(music["gain_db"]) + moved if "gain_db" in music else audio_levels.bed_gain_for(music["file"], str(base), None)
        run("ffmpeg", "-nostdin", "-y", "-v", "error", "-stream_loop", "-1", "-i", music["file"], "-t", f"{length:.3f}", "-map", "0:a:0",
            "-af", f"volume={gain}dB", "-ar", "48000", "-ac", "2", str(media / "music.wav"))
        bed = {"file": "music.wav", "at": round(at, 4), "len": round(length, 4)}

    rows = caption_rows(jd, job, cap, bdur)
    srt = kit / f"{job} native captions.srt"
    with open(srt, "w", encoding="utf-8") as f:
        for n, (a, b, t) in enumerate(rows, 1):
            f.write(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n")
    plan = {"job": job, "cut_seconds": round(bdur, 4), "fps": [fps.numerator, fps.denominator], "fps_name": FPS_NAMES[fps], "width": tw, "height": th,
            "base": base.name, "picture": picture.name, "voice": voice.name, "voice_muted": bool(sound_plan.voice_muted(str(jd))), "pieces": pieces, "layers": layers, "left_out": left_out,
            "sounds": sounds, "music": bed, "captions": len(rows), "caption_look": (cap or {}).get("look"), "media": str(media), "kit": str(kit)}
    (kit / "plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    return plan


def fcpxml(plan, captions_on, voice_first=False):
    """Hand import: every track laid out. Her voice is its own audio clip per kept line, on the lane Resolve maps to its
    own track, so no sound effect shares it."""
    fps = Fraction(*plan["fps"])
    frame = 1 / fps
    n = lambda sec: math.floor(Fraction(sec).limit_denominator(10 ** 6) * fps + Fraction(4999, 10000))
    t = lambda k: f"{k * frame.numerator}/{frame.denominator}s" if k else "0s"
    media = Path(plan["media"])
    res = [f'<format id="r0" frameDuration="{frame.numerator}/{frame.denominator}s" width="{plan["width"]}" height="{plan["height"]}"/>']
    ids = {}

    def asset(name, video, audio):
        if name in ids:
            return ids[name]
        aid = f"a{len(ids) + 1}"
        ids[name] = aid
        p = media / name
        extra = ' audioSources="1" audioChannels="2" audioRate="48000"' if audio else ""
        res.append(f'<asset id="{aid}" name={sx.quoteattr(name)} src={sx.quoteattr(p.as_uri())} start="0s" duration="{t(n(dur(p)))}" hasVideo="{int(video)}" hasAudio="{int(audio)}"'
                   + (' format="r0"' if video else "") + extra + "/>")
        return aid

    base = asset(plan["picture"], True, False)
    vo = asset(plan["voice"], False, True)
    spine = []
    for a, b in plan["pieces"]:
        s, e = n(a), n(b)
        spine.append({"rec": s, "src": s, "n": e - s, "children": []})
    total = spine[-1]["rec"] + spine[-1]["n"]

    def hang(at, make):
        host = next((c for c in spine if c["rec"] <= at < c["rec"] + c["n"]), spine[-1])
        host["children"].append(make(host["src"] + (at - host["rec"])))

    sound_tracks = max([s["lane"] for s in plan["sounds"]], default=-1) + 1 + (1 if plan["music"] else 0)
    voice_lane = -1 if voice_first else -(sound_tracks + 1)
    fx_lane = (lambda k: -(k + 2)) if voice_first else (lambda k: -(sound_tracks - k))
    if not plan["voice_muted"]:
        for c in spine:
            c["children"].append(f'<asset-clip ref="{vo}" name={sx.quoteattr(plan["voice"])} lane="{voice_lane}" offset="{t(c["src"])}" start="{t(c["src"])}" duration="{t(c["n"])}"/>')
    for k, L in enumerate(plan["layers"], 1):
        ref = asset(L["file"], True, False)
        at, ln = n(L["at"]), min(n(L["len"]), total - n(L["at"]))
        off = ' enabled="0"' if L["captions"] and not captions_on else ""
        hang(at, lambda o, ref=ref, L=L, ln=ln, k=k, off=off: f'<asset-clip ref="{ref}" name={sx.quoteattr(L["file"])} lane="{k}" offset="{t(o)}" start="0s" duration="{t(ln)}"{off}/>')
    # Resolve fills audio tracks in file order, first free track wins, ignoring lanes. So every voice clip comes first,
    # and the sounds hang off the last clip: the cut's clock is the clip's clock, so their times still hold.
    last = spine[-1]

    def hang_sound(at, make):
        last["children"].append(make(at))

    for s in plan["sounds"]:
        ref = asset(s["file"], False, True)
        hang_sound(n(s["at"]), lambda o, ref=ref, s=s: f'<asset-clip ref="{ref}" name={sx.quoteattr(s["file"])} lane="{fx_lane(s["lane"])}" offset="{t(o)}" start="0s" duration="{t(max(1, n(s["len"])))}"/>')
    if plan["music"]:
        ref = asset(plan["music"]["file"], False, True)
        m = plan["music"]
        hang_sound(n(m["at"]), lambda o, ref=ref, m=m: f'<asset-clip ref="{ref}" name="music.wav" lane="{fx_lane(sound_tracks - 1)}" offset="{t(o)}" start="0s" duration="{t(n(m["len"]))}"/>')
    body = "".join(f'<asset-clip ref="{base}" name={sx.quoteattr(plan["picture"])} offset="{t(c["rec"])}" start="{t(c["src"])}" duration="{t(c["n"])}">' + "".join(c["children"]) + "</asset-clip>\n" for c in spine)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n<resources>\n' + "\n".join(res)
            + f'\n</resources>\n<library><event name={sx.quoteattr(plan["job"])}><project name={sx.quoteattr(plan["job"] + (" overlay" if captions_on else " native"))}>'
            + f'<sequence format="r0" duration="{t(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k"><spine>\n' + body
            + "</spine></sequence></project></event></library>\n</fcpxml>\n")


def settings_fcpxml(plan):
    """A one-frame timeline: importing it sets the project's frame rate, playback rate and size, which a script can't."""
    fps = Fraction(*plan["fps"])
    d = f"{fps.denominator}/{fps.numerator}s"
    src = (Path(plan["media"]) / plan["picture"]).as_uri()
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9"><resources><format id="r0" frameDuration="{d}" width="{plan["width"]}" height="{plan["height"]}"/>'
            f'<asset id="a1" name="settings" src={sx.quoteattr(src)} start="0s" duration="{d}" hasVideo="1" format="r0"/></resources><library><event name="settings"><project name="settings">'
            f'<sequence format="r0" duration="{d}" tcStart="0s" tcFormat="NDF"><spine><asset-clip ref="a1" name="settings" offset="0s" start="0s" duration="{d}"/></spine></sequence></project></event></library></fcpxml>\n')


def lua_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua_build(plan, native):
    """One click: a new project with the whole reel on it. Times are seconds; frames are worked out from what Resolve
    itself reads for each file, so a file at another frame rate still lands on the right frame."""
    kit = Path(plan["kit"])
    media = Path(plan["media"])
    files = [plan["base"]] + [L["file"] for L in plan["layers"]] + [s["file"] for s in plan["sounds"]] + ([plan["music"]["file"]] if plan["music"] else [])
    tabl = lambda rows: "{" + ",".join("{" + ",".join(lua_str(v) if isinstance(v, str) else str(v).lower() for v in r) + "}" for r in rows) + "}"
    layers = [(L["file"], L["at"], L["len"], k + 2, L["captions"]) for k, L in enumerate(plan["layers"])]
    sounds = [(s["file"], s["at"], s["len"], s["lane"] + 2) for s in plan["sounds"]]
    if plan["music"]:
        m = plan["music"]
        sounds.append((m["file"], m["at"], m["len"], max([s["lane"] for s in plan["sounds"]], default=-1) + 3))
    srt = kit / f"{plan['job']} native captions.srt"
    has_caps = str(plan["captions"] > 0).lower()
    return f'''-- Builds {plan["job"]} in a new DaVinci Resolve project, {"with real captions" if native else "with its rendered captions layer"}.
local JOB, NATIVE = {lua_str(plan["job"])}, {str(native).lower()}
local MEDIA, SRT = {lua_str(str(media) + "/")}, {lua_str(srt)}
local FILES = {{{",".join(lua_str(f) for f in files)}}}
local PIECES = {tabl([tuple(p) for p in plan["pieces"]])}
local LAYERS = {tabl(layers)}
local SOUNDS = {tabl(sounds)}
local CUT = {plan["pieces"][-1][1]}
local BASE, MUTED, VIDEO_TRACKS, AUDIO_TRACKS = {lua_str(plan["base"])}, {str(plan["voice_muted"]).lower()}, {len(plan["layers"]) + 1}, {max([s[3] for s in sounds], default=1)}
local pm = resolve:GetProjectManager()
local name, k = JOB .. (NATIVE and " native" or " overlay"), 1
local p = pm:CreateProject(name)
while not p and k < 50 do k = k + 1; p = pm:CreateProject(name .. " " .. k) end
assert(p, "could not make a project")
local mp = p:GetMediaPool()
local seed = mp:ImportTimelineFromFile({lua_str(kit / "project settings.fcpxml")}, {{timelineName = "settings", importSourceClips = false}})   -- sets frame rate, playback rate and size together
if seed then mp:DeleteTimelines({{seed}}); for _, c in ipairs(mp:GetRootFolder():GetClipList() or {{}}) do mp:DeleteClips({{c}}) end end
p:SetSetting("timelineResolutionWidth", "{plan["width"]}"); p:SetSetting("timelineResolutionHeight", "{plan["height"]}")
local paths = {{}}
for i, f in ipairs(FILES) do paths[i] = MEDIA .. f end
local by = {{}}
for _, it in ipairs(mp:ImportMedia(paths) or {{}}) do by[it:GetName()] = it end
local missing = {{}}
for _, f in ipairs(FILES) do if not by[f] then missing[#missing + 1] = f end end
if #missing > 0 then mp:AddSubFolder(mp:GetRootFolder(), "Missing " .. table.concat(missing, ", ")) end
local tl = mp:CreateEmptyTimeline(name); p:SetCurrentTimeline(tl)
local T0, TF = tl:GetStartFrame(), tonumber(p:GetSetting("timelineFrameRate")) or 30
if TF > 29.9 and TF < 29.98 then TF = 30000 / 1001 elseif TF > 23.9 and TF < 23.98 then TF = 24000 / 1001 elseif TF > 59.9 and TF < 59.95 then TF = 60000 / 1001 end
local function rec(s) return math.floor(s * TF + 0.4999) end
local function native_frames(f, s)                           -- seconds on this file's own frame clock
  local r = tonumber(by[f]:GetClipProperty("FPS")) or TF
  if r > 29.9 and r < 29.98 then r = 30000 / 1001 end
  return math.floor(s * r + 0.4999)
end
if NATIVE then                                               -- subtitles go first: on a timeline with clips Resolve lays them after its end
  local s = {has_caps} and mp:ImportMedia({{SRT}})
  if s and s[1] then tl:AddTrack("subtitle") end
  if s and s[1] then mp:AppendToTimeline({{{{mediaPoolItem = s[1], startFrame = 0, recordFrame = T0, trackIndex = 1, mediaType = 3}}}}) end
end
while tl:GetTrackCount("video") < VIDEO_TRACKS do tl:AddTrack("video") end
while tl:GetTrackCount("audio") < AUDIO_TRACKS do tl:AddTrack("audio", "stereo") end
local v = {{}}
for _, r in ipairs(PIECES) do
  local one = {{mediaPoolItem = by[BASE], startFrame = native_frames(BASE, r[1]), endFrame = native_frames(BASE, r[2]), recordFrame = T0 + rec(r[1]), trackIndex = 1}}
  if MUTED then one.mediaType = 1 end
  v[#v + 1] = one
end
mp:AppendToTimeline(v)
local capclips = {{}}
for _, r in ipairs(LAYERS) do
  local fr = by[r[1]] and (tonumber(by[r[1]]:GetClipProperty("FPS")) or TF)
  local e = fr and math.ceil(r[3] * fr - 0.001)
  if e then
    e = math.min(e, math.ceil((rec(CUT) - rec(r[2])) * fr / TF - 0.001))       -- nothing runs past her last frame
    local got = mp:AppendToTimeline({{{{mediaPoolItem = by[r[1]], startFrame = 0, endFrame = e, recordFrame = T0 + rec(r[2]), trackIndex = r[4], mediaType = 1}}}})
    if r[5] and got then for _, it in ipairs(got) do capclips[#capclips + 1] = it end end
  end
end
if NATIVE then for _, it in ipairs(capclips) do it:SetClipEnabled(false) end end
local a = {{}}
for _, r in ipairs(SOUNDS) do
  if by[r[1]] then a[#a + 1] = {{mediaPoolItem = by[r[1]], startFrame = 0, endFrame = math.max(1, native_frames(r[1], r[3])), recordFrame = T0 + rec(r[2]), trackIndex = r[4], mediaType = 2}} end
end
if #a > 0 then mp:AppendToTimeline(a) end
pm:SaveProject()
resolve:OpenPage("edit")
'''


def resolve_scripts_dir():
    """This user's DaVinci Resolve Fusion Scripts folder, if Resolve has made it (so its one-click builds can go in
    the Workspace > Scripts menu). None when Resolve isn't installed: the hand-import FCPXML still works without it."""
    home = Path.home()
    if sys.platform == "darwin":
        cands = [home / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts"]
    elif os.name == "nt":
        base = os.environ.get("APPDATA")
        cands = [Path(base) / "Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts"] if base else []
    else:
        cands = [home / ".local/share/DaVinciResolve/Fusion/Scripts", Path("/opt/resolve/Fusion/Scripts")]
    return next((c for c in cands if c.is_dir()), None)


def install_scripts(kit, job):
    """Copy the kit's one-click Build scripts into Resolve's Scripts > Utility folder, so she runs them from
    Workspace > Scripts with no setup. Returns the list of menu names installed, or [] when Resolve isn't found."""
    root = resolve_scripts_dir()
    if not root:
        return []
    util = root / "Utility"
    done = []
    try:
        util.mkdir(parents=True, exist_ok=True)
        for which in ("overlay", "native"):
            src = Path(kit) / f"Build {job} {which}.lua"
            if src.exists():
                shutil.copy2(src, util / src.name)
                done.append(f"Build {job} {which}")
    except Exception:
        return done
    return done


def build(job, jd, source, install=True):
    """Build the whole Resolve kit for a visual-editor reel into projects/<job>/outputs/<job> resolve/. `source` is her
    finished cut with her Filter and covered faces already baked in. When `install`, the one-click Build scripts also go
    straight into Resolve's Workspace > Scripts menu. Returns (kit folder path, [installed menu names])."""
    jd = Path(jd)
    kit = jd / "outputs" / f"{job} resolve"
    kit.mkdir(parents=True, exist_ok=True)
    plan = build_plan(job, jd, source, kit)
    (kit / "project settings.fcpxml").write_text(settings_fcpxml(plan), encoding="utf-8")
    (kit / f"{job} overlay.fcpxml").write_text(fcpxml(plan, True), encoding="utf-8")
    (kit / f"{job} native.fcpxml").write_text(fcpxml(plan, False), encoding="utf-8")
    (kit / f"Build {job} overlay.lua").write_text(lua_build(plan, False), encoding="utf-8")
    (kit / f"Build {job} native.lua").write_text(lua_build(plan, True), encoding="utf-8")
    installed = install_scripts(kit, job) if install else []
    return kit, installed


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python3 product/resolve_export.py <job>", file=sys.stderr)
        return 2
    job = argv[0]
    jd = ENGINE / "projects" / job
    # the finished cut as her export has it: a graded copy if she has a Filter, else the covered/plain cut
    finished = sorted((jd / "hf-graphics/finish").glob("footage-*.mp4"), key=os.path.getmtime) if (jd / "hf-graphics/finish").is_dir() else []
    source = finished[-1] if finished else (jd / "outputs" / f"{job}.mp4")
    kit, installed = build(job, jd, source)
    print(f"Resolve kit ready: {kit}")
    if installed:
        print("In Resolve, Workspace > Scripts: " + ", ".join(installed))
    else:
        print("Resolve not found; import the overlay.fcpxml by hand (File > Import > Timeline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
