#!/usr/bin/env python3
"""cut-shorts.py: the reels she picked from a long video, each one set up and built as a job of its own.

    cut-shorts.py set-up <job> [<reel> ...]
    cut-shorts.py build  <job> [<reel> ...] [--framing fill|fit] [--captions pack|clean] [--pack <Pack>]

<job> is the job that holds the long video (its name under projects/, or its folder), and its reels-plan.json
is what both commands read. Naming reels after the job limits the run to those; naming none takes every reel
in the plan.

set-up gives each reel an ordinary job folder at projects/<job>/reels/<reel>/: the long video linked into
raw/ (a copy when a link cannot be made), the long video's words.json, and the reel's cut in
transcript/cuts.from-plan.json. Any tool in the engine can then open a reel like any other job.

build sets each reel up the same way and then makes it, start to finish:
  the cut      stitch-cut.sh, the rough cut's own stitch and sound -> outputs/<reel>.mp4 and its transcript,
               still in the long video's shape
  the frame    1080x1920. fill (the default): cropped full height around her face where
               workflows/head-framing.py finds it, around the middle when it finds none (a shared screen).
               fit: the whole shot scaled into the frame over a blurred copy of itself. Footage that is
               already vertical is only sized. The wide cut stays beside it as outputs/<reel>.wide.mp4.
  the type     pack (the default, beta): captions and the plan's hook card in her style pack, through
               build-reel-type.py, reel_render.py and build-reel-mp4.py, as a single finished reel gets them.
               clean: the Clean Captions preset. A reel the pack route cannot finish, for any reason, gets
               Clean Captions instead and one line says why, so no reel comes out uncaptioned.
  the export   outputs/<reel>.final.mp4, copied to ~/Downloads or to REELS_EXPORT_DIR

A reel's own "framing" or "captions" in the plan wins over the batch setting. --pack names the style pack
for this batch; without it her saved default pack is used. VOICE_GAIN_DB passes straight through to
stitch-cut.sh: when sound-check says the limiter is working hard on one reel, rebuild just that reel with
VOICE_GAIN_DB set to the gain sound-check names.

A reel that fails is named where it fails and again at the end (exit 1); the reels after it still run.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
for stream in (sys.stdout, sys.stderr):   # ✓ and ✗ need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ENGINE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ENGINE / "product"))
from video_encoder import pick_encoder   # the engine's one encoder decision, shared with every other render

SPLICE_SH = ENGINE / ".claude" / "skills" / "rough-cut" / "scripts" / "stitch-cut.sh"
FACE_FRAME_PY = ENGINE / "workflows" / "head-framing.py"
SUBJECT_ZONES_PY = ENGINE / "workflows" / "subject-zones.py"
CLEANCAP_BUILD = ENGINE / "presets" / "clean-captions" / "build.py"
REEL_TYPE_PY = ENGINE / "product" / "build-reel-type.py"     # the single-reel pack route, reused per reel
REEL_RENDER_PY = ENGINE / "product" / "reel_render.py"
REEL_MP4_PY = ENGINE / "product" / "build-reel-mp4.py"
USER_STYLE = ENGINE / "product" / "creative-vault" / "user-style.json"   # her saved default pack
FRAMINGS = ("fill", "fit")
CAPTION_ROUTES = ("pack", "clean")
JOB_LAYOUT = ("raw", "transcript", "outputs")      # the folders every job has
REEL = (1080, 1920)


def _quit(msg):
    sys.exit(f"cut-shorts: {msg}")


def _need(path, why):
    """`path` when it exists; otherwise stop, with `why` naming it."""
    if not path.exists():
        _quit(why.format(path))
    return path


def _run(cmd, env=None):
    """Echo the command, then run it on the shared console so what it prints (sound-check's warnings above
    all) shows up while it still matters instead of after the fact. `env` adds variables for this one step."""
    argv = [str(c) for c in cmd]
    print("  $ " + " ".join(argv), flush=True)
    return subprocess.run(argv, env=({**os.environ, **{k: str(v) for k, v in env.items()}} if env else None)).returncode


def _even(v):
    return round(v / 2) * 2


def _stored_size(video):
    """(width, height) of the first video stream, as ffprobe reports it."""
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "csv=p=0", str(video)])
    # Side data on a phone file can leave a trailing comma on the row ("1920,1080,"): empty fields are skipped.
    fields = [f for f in raw.decode("utf-8", "replace").strip().split(",") if f.strip()]
    return int(fields[0]), int(fields[1])


def _link_or_copy(src, dst):
    """A hard link when both sit on one volume (not a byte moves); a real copy when they cannot share one."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


# ---- the plan and the reel folders --------------------------------------------------------------------------

PLAN = "reels-plan.json"
REELS = "reels"              # projects/<job>/reels/<reel>/
# A job pulled by an earlier engine keeps its plan in that engine's file and keys (below). It is read as it is,
# and its reels rebuild where they already are, so her earlier builds and word fixes stay with them.
EARLIER = ("clips-plan.json", "clips", "hook_text")


def read_plan(parent):
    """(plan, source recording, the parent's words.json, the folder its reels build in), or a plain reason to
    stop. The plan comes back in this engine's shape: its reels under "reels", each card under "hook"."""
    if (parent / PLAN).exists():
        plan, folder = json.loads((parent / PLAN).read_text(encoding="utf-8")), REELS
    elif (parent / EARLIER[0]).exists():
        plan, folder = json.loads((parent / EARLIER[0]).read_text(encoding="utf-8")), EARLIER[1]
        plan[REELS] = [dict(r, hook=r.get(EARLIER[2])) if isinstance(r, dict) and "hook" not in r else r
                       for r in plan.get(EARLIER[1]) or []]
    else:
        _quit(f"there is no {parent / PLAN} yet: the pull-reels pass writes it once she has picked")
    source = _need(parent / plan["source"], "the long video the plan names is not there: {}")
    words = _need(parent / "transcript" / "words.json", "{} is not there yet: transcribe the long video first (word-timings.sh)")
    return plan, source, words, folder


def _hook_lines(reel):
    """The hook card's lines: the plan's "hook", a list of lines or one string with line breaks. Empty or null
    means no card."""
    hook = reel.get("hook")
    if isinstance(hook, (list, tuple)):
        lines = [str(ln) for ln in hook if ln is not None]
    else:
        lines = (hook or "").splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


def _with_source(seg, source_name):
    """A copy of one plan segment with the file it cuts from (the cut's "clip") filled in. The plan may leave
    that out."""
    out = dict(seg)
    out.setdefault("clip", source_name)
    return out


def set_up_reel(parent, name, reel, source, words, folder=REELS):
    """The reel's job folder, laid out like any other job, with its cut list already written."""
    job = parent / folder / name
    for sub in JOB_LAYOUT:
        (job / sub).mkdir(parents=True, exist_ok=True)
    if not (job / "raw" / source.name).exists():
        _link_or_copy(source, job / "raw" / source.name)
    if not (job / "transcript" / "words.json").exists():
        shutil.copy2(words, job / "transcript" / "words.json")

    segments = [_with_source(seg, source.name) for seg in reel["segments"]]
    cuts = json.dumps({"segments": segments}, indent=1) + "\n"
    # Written twice, on purpose. The job folder's copy is the lasting record; the scratch copy is the one
    # stitch-cut.sh reads, and the OS is free to empty the temp directory whenever it likes.
    (job / "transcript" / "cuts.from-plan.json").write_text(cuts, encoding="utf-8")
    scratch = Path(tempfile.gettempdir()) / "reels-editing-engine" / name
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "cuts.json").write_text(cuts, encoding="utf-8")

    seconds = sum(s["end"] - s["start"] for s in segments)
    print(f"  {folder}/{name}: set up, {len(segments)} piece(s) of the long video, {seconds:.1f} s in all")
    return job


# ---- the lane -------------------------------------------------------------------------------------------------

def _fit_filter(w, h):
    """The fit framing as one ffmpeg filter: the whole frame scaled to sit inside 1080x1920, centred, over a
    blurred, slightly darkened copy of the same footage that fills the rest. Nothing is cut. The blur is done
    small and scaled up, which looks the same and costs a fraction of blurring at full size."""
    W, H = REEL
    return (f"split=2[bg][fg];"
            f"[bg]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
            f"gblur=sigma=10,scale={W}:{H},eq=brightness=-0.06,setsar=1[b];"
            f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1[f];"
            f"[b][f]overlay=(W-w)/2:(H-h)/2")


def _is_vertical(w, h):
    """Footage already shaped 9:16 (a phone held upright), within a hair."""
    return h > 0 and abs(w / h - REEL[0] / REEL[1]) < 0.02


def _vertical(job, name, framing="fill"):
    """Turn the reel's cut into the 1080x1920 base. fill (the default): cropped around her face, or around the
    middle when there is no face to find. fit: the whole frame over a blurred fill. Either way the wide cut is
    kept beside it as <reel>.wide.mp4."""
    cut = job / "outputs" / f"{name}.mp4"
    if not cut.exists():
        _quit(f"{name}: the cut left no {cut} to frame")
    w, h = _stored_size(cut)
    if (w, h) == REEL:
        print(f"  {name}: already 1080x1920, used as it is")
        return

    if framing == "fit":
        if _is_vertical(w, h):
            vf = f"scale={REEL[0]}:{REEL[1]},setsar=1"      # vertical footage is used as is, only sized
            said = "already vertical, sized to 1080x1920"
        else:
            vf = _fit_filter(w, h)
            said = "the whole shot fitted into 1080x1920 over a blurred fill"
    else:
        vf = None
        measured = job / "head-framing.json"          # where head-framing.py leaves its answer for a job's outputs/
        if _run(["uv", "run", FACE_FRAME_PY, cut]) == 0 and measured.exists():
            vf = json.loads(measured.read_text(encoding="utf-8")).get("reframe", {}).get("ffmpeg")
        if vf is None:
            cw = _even(h * 9 / 16)                   # full height, 9:16 wide, both even for the encoder
            x = max(0, (w - cw) // 4 * 2)            # half the spare width, floored to an even number
            vf = f"crop={cw}:{h}:{x}:0,scale=1080:1920"
            print(f"  {name}: no face to measure, so taking the middle")
        said = f"cropped to 1080x1920 ({vf})"

    # The frame is written to a file of its own first, and only a finished one takes the cut's name: a failed
    # encode leaves the cut exactly as it was, and the wide cut is never rewritten in place (a hardlink to it
    # elsewhere would change with it).
    wide = job / "outputs" / f"{name}.wide.mp4"
    framed = job / "outputs" / f"{name}.framing.mp4"
    if _run(["ffmpeg", "-y", "-v", "error", "-i", cut, "-vf", vf,
             *pick_encoder(vbr="10M", crf=18, preset="veryfast"),
             "-c:a", "copy", "-movflags", "+faststart", framed]) != 0:
        if framed.exists():
            framed.unlink()
        _quit(f"{name}: the 9:16 frame did not encode")
    os.replace(cut, wide)
    os.replace(framed, cut)
    print(f"  {name}: {said}")


def _measure_subject(job, name, framing="fill"):
    """Where she is in THIS reel's vertical base -> the job's subject-zones.json, which places the captions under
    her chin and is what the render's check holds every layer against. A fit base carries a blurred, much larger
    copy of her face in the fill, and a face detector finds that one too; so for fit, the measurement is taken on
    a stand-in that has the same picture in the same place over a plain fill, and never sees the blurred face."""
    base = job / "outputs" / f"{name}.mp4"
    wide = job / "outputs" / f"{name}.wide.mp4"
    if framing == "fit" and wide.exists():
        try:
            w, h = _stored_size(wide)
        except Exception:
            w = h = 0
        if w and not _is_vertical(w, h):
            proxy = job / "fit-measure.mp4"
            W, H = REEL
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,"
                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=gray,setsar=1")
            if _run(["ffmpeg", "-y", "-v", "error", "-i", wide, "-vf", vf, "-an", "-c:v", "libx264",
                     "-preset", "ultrafast", "-crf", "30", proxy]) == 0:
                rc = _run(["uv", "run", SUBJECT_ZONES_PY, proxy, "--out", job / "subject-zones.json"])
                try:
                    proxy.unlink()
                except OSError:
                    pass
                return rc
    return _run(["uv", "run", SUBJECT_ZONES_PY, base])


def _clean_captions(job, name, reel, deliverable, framing="fill", pack=None, measured=False):
    """The clean-captions pass, which writes the deliverable itself, in the batch's pack (or her saved default,
    or the starter look when there is none: the preset decides and says which)."""
    # sys.executable, not the name "python3": on Windows that name can be the Microsoft Store stub, and the
    # shell shim that normally gets past it never sees a child started from here.
    # A plan that says "hook": null means no hook card, the same as leaving the key out.
    # Passed through as it was, the null reached the command line as the word "None" and was drawn as the hook.
    hook = "\n".join(_hook_lines(reel))
    if not measured:
        # Where she is in THIS reel: the captions sit under her chin and the hook card is checked against her
        # head (the preset reads the job's subject-zones.json). A failed measurement is said by the preset.
        _measure_subject(job, name, framing)
    argv = [sys.executable, CLEANCAP_BUILD, job, "--hook-text", hook, "--out", deliverable]
    if pack:
        argv += ["--pack", pack]
    hook_end = reel.get("hook_end")
    if hook_end is not None:
        argv += ["--hook-end", str(hook_end)]
    if _run(argv) != 0:
        _quit(f"{name}: caption build failed")


def saved_pack():
    """Her saved default style pack (product/creative-vault/user-style.json "default_pack", or _local/ in the
    copy the engine ships from: user_style.py), or None."""
    import user_style
    return user_style.default_pack(str(USER_STYLE))


def _hook_end_for(reel, words):
    """When the pack's hook comes down, in reel seconds: the plan's hook_end, else the end of the spoken words
    the hook text covers (as many words as the card has), else 3 seconds in. Always a number, so the pack
    route never falls back to a default meant for a full-length reel."""
    if reel.get("hook_end") is not None:
        return float(reel["hook_end"])
    n = len(" ".join(_hook_lines(reel)).split())
    if n and len(words) >= n:
        return round(float(words[n - 1].get("end", 3.0)) + 0.3, 2)
    return 3.0


HOOK_TOP_Y = 280        # where the pack's hook starts (build-reel-type.py HOOK_TOP): just under the platform band
HOOK_BOTTOM_Y = 536     # where a full-size hook ends (build-reel-type.py HOOK_MAXH comment: top ~206 -> ~536)
HOOK_ROOM = 330         # the hook's height budget (build-reel-type.py HOOK_MAXH): the room a moved hook needs


def _hook_placement(job, hook_end):
    """Plan keys that keep the pack's hook off her. Normally none: the hook sits at the top, above your head.
    When THIS reel frames her so high that the hook would land on her head (subject-zones.json: the open room
    above her ends before a full-size hook does) and there is open room under her chin, the hook moves down into
    that room and the captions wait until it has gone, so the two never share the spot. Returns (keys, line)."""
    try:
        zones = json.loads((job / "subject-zones.json").read_text(encoding="utf-8")).get("zones") or {}
    except (OSError, ValueError, AttributeError):
        return {}, None
    above, below = zones.get("above") or {}, zones.get("below") or {}
    if above.get("usable") and float(above.get("bottom", 0)) >= HOOK_BOTTOM_Y:
        return {}, None
    if not below.get("usable") or float(below.get("bottom", 0)) - float(below.get("top", 0)) < HOOK_ROOM:
        return {}, None      # nowhere better: the render's own check decides, and Clean Captions is the fallback
    top = int(below["top"])
    return ({"hook_lift_px": HOOK_TOP_Y - top, "caption_skip": [[0.0, round(float(hook_end), 2)]]},
            f"no room above your head in this reel, so the hook sits under her chin and the captions start after it")


def write_caption_plan(job, name, reel):
    """The reel's caption-plan.json for the pack route, from the reels plan: its hook becomes the pack's hook
    (one line per line of the card) and hook_end its exit; a reel framed too high for a hook above your head
    gets it under her chin instead (_hook_placement). Rewritten on every build, like everything else in a reel
    folder."""
    tr = json.loads((job / "outputs" / f"{name}.transcript.json").read_text(encoding="utf-8"))
    words = tr.get("words") or []
    hook = _hook_lines(reel)
    plan = {"_doc": "Written by pull-reels (cut-shorts.py) from the reels plan. Edit that plan, not this.",
            "hook": hook}
    if hook:
        plan["hook_end"] = _hook_end_for(reel, words)
        keys, line = _hook_placement(job, plan["hook_end"])
        plan.update(keys)
        if line:
            print(f"  {name}: {line}")
    (job / "caption-plan.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    return plan


def _pack_captions(job, name, reel, deliverable, pack, framing="fill"):
    """Captions and hook in her style pack, the way a finished single reel gets them: build-reel-type.py writes
    the overlay, reel_render.py renders it (with its checks), build-reel-mp4.py bakes it onto the vertical base.
    Returns None when the deliverable is written, else a plain reason it was not."""
    if not pack:
        return "no style pack is chosen yet"
    base = job / "outputs" / f"{name}.mp4"
    if not (job / "outputs" / f"{name}.transcript.json").exists():
        return "the cut left no transcript to caption from"
    # Where she is in THIS reel, so the captions sit under her chin (build-reel-type reads subject-zones.json)
    # and the hook stays off her head. Measured first: the caption plan is written from it.
    _measure_subject(job, name, framing)
    write_caption_plan(job, name, reel)
    env = {"JOB_DIR": job, "STYLE_PACK": pack, "REEL_NO_HANDOFF_ASK": "1"}   # a batch reel is not asked about CapCut
    if _run([sys.executable, REEL_TYPE_PY], env=env) != 0:
        return "the pack overlay did not build"
    overlay = job / "outputs" / f"{name}.captions.mov"
    if _run([sys.executable, REEL_RENDER_PY, "render", job / f"hf-reel-type-{pack.lower()}", "-o", overlay]) != 0:
        return "the pack overlay did not render"
    if deliverable.exists():
        deliverable.unlink()                     # so only a file THIS bake wrote can count as done
    if _run([sys.executable, REEL_MP4_PY], env={**env, "OVERLAY": overlay, "BASE": base, "OUT": deliverable}) != 0:
        return "the bake onto the footage did not finish"
    if not deliverable.exists() or deliverable.stat().st_size == 0:
        return "the bake wrote no video"
    return None


def _captions(job, name, reel, deliverable, route="pack", pack=None, framing="fill"):
    """Caption the reel into the deliverable: the style-pack route by default, Clean Captions on request, and
    Clean Captions automatically whenever the pack route cannot finish, so a reel is never left uncaptioned."""
    if route == "pack":
        try:
            why = _pack_captions(job, name, reel, deliverable, pack, framing)
        except Exception as e:                   # anything at all: this reel still gets captions
            why = f"{type(e).__name__}: {e}"
        if why is None:
            print(f"  {name}: captions in the {pack} style pack")
            return
        print(f"  {name}: style-pack captions did not finish ({why}), so this reel gets Clean Captions instead")
    measured = route == "pack" and (job / "subject-zones.json").exists()   # the pack route measured this reel already
    _clean_captions(job, name, reel, deliverable, framing, pack, measured)


def _export_copy(deliverable, name):
    dest = Path(os.environ.get("REELS_EXPORT_DIR") or Path.home() / "Downloads")
    if not dest.is_dir():
        print(f"  {name}: no export copy made, {dest} does not exist")
        return
    shutil.copy2(deliverable, dest / deliverable.name)
    print(f"  {name}: export copy saved to {dest / deliverable.name}")


def _choice(reel, key, batch, allowed, name):
    """The reel's own setting for `key` when the plan gives one it understands, else the batch's."""
    own = reel.get(key)
    if own is None:
        return batch
    if str(own).lower() in allowed:
        return str(own).lower()
    print(f"  {name}: \"{key}\": {own!r} is not one of {', '.join(allowed)}, so using {batch}")
    return batch


def build_reel(job, name, reel, opts=None):
    """The cut, the frame, the type and the export copy, for one reel folder. Returns the finished file."""
    opts = opts or {}
    framing = _choice(reel, "framing", opts.get("framing", "fill"), FRAMINGS, name)
    route = _choice(reel, "captions", opts.get("captions", "pack"), CAPTION_ROUTES, name)
    deliverable = job / "outputs" / f"{name}.final.mp4"
    # The bash on PATH, found the way a shell would find it. A bare "bash" handed to Windows is looked up in
    # System32 first, which is WSL's bash, not the Git Bash this engine runs under.
    if _run([shutil.which("bash") or "bash", SPLICE_SH, job]) != 0:
        raise RuntimeError("the cut step stopped; its message is just above")
    _vertical(job, name, framing)
    _captions(job, name, reel, deliverable, route, opts.get("pack"), framing)
    _export_copy(deliverable, name)
    return deliverable


def _try_build(job, name, reel, opts=None):
    """Build one reel and say how it went. A failure is reported here rather than raised, so one reel going
    wrong never costs the others their turn: a step that fails, and anything else that goes wrong on the way
    (a file ffprobe cannot read, say), is this reel's failure and not the whole batch's."""
    try:
        deliverable = build_reel(job, name, reel, opts)
    except (RuntimeError, SystemExit) as e:
        print(f"  ✗ {name} stopped: {e}")
        return False
    except Exception as e:
        print(f"  ✗ {name} stopped: {type(e).__name__}: {e}")
        return False
    print(f"  ✓ {name} is done: {deliverable}")
    return True


# ---- command line ---------------------------------------------------------------------------------------------

VERBS = ("set-up", "build")
USAGE = ("usage: cut-shorts.py set-up|build <job> [<reel> ...] "
         "[--framing fill|fit] [--captions pack|clean] [--pack <Pack>]")
SETTINGS = {"--framing": FRAMINGS, "--captions": CAPTION_ROUTES, "--pack": None}   # None: any value


def job_folder(job):
    """The long video's job folder: a folder given as a path, else projects/<job>."""
    given = Path(job)
    if not given.is_dir() and (ENGINE / "projects" / job).is_dir():
        return ENGINE / "projects" / job
    return given.resolve()


def read_command(argv):
    """(verb, job folder, the reels named or None for all, settings). Words that are not settings are the job
    and then the reels; a setting is refused when it is not one of SETTINGS or its value is not allowed."""
    if not argv or argv[0] not in VERBS:
        _quit(USAGE)
    opts = {"framing": "fill", "captions": "pack", "pack": None}
    named, words = [], list(argv[1:])
    while words:
        word = words.pop(0)
        if word in SETTINGS:
            if not words:
                _quit(f"{word} needs a value. " + USAGE)
            value, allowed = words.pop(0), SETTINGS[word]
            if allowed is not None and value.lower() not in allowed:
                _quit(f"{word} takes one of: {', '.join(allowed)} (got {value!r})")
            opts[word[2:]] = value if allowed is None else value.lower()
        elif word.startswith("-"):
            _quit(f"{word} is not a setting cut-shorts.py takes. " + USAGE)
        else:
            named.append(word)
    if not named:
        _quit(USAGE)
    if not opts["pack"]:
        opts["pack"] = saved_pack()           # a reel's own "captions": "pack" needs it even in a clean batch
    return argv[0], job_folder(named[0]), named[1:] or None, opts


def main():
    verb, parent, only, opts = read_command(sys.argv[1:])
    build = verb == "build"
    plan, source, words, folder = read_plan(parent)
    chosen = [c for c in plan.get(REELS) or [] if only is None or (isinstance(c, dict) and c.get("name") in only)]
    if not chosen:
        _quit("no reel in the plan matched")

    if build:
        caps = ("Clean Captions" if opts["captions"] == "clean" else
                f"{opts['pack']} style pack (beta), Clean Captions if it cannot finish" if opts["pack"] else
                "style pack (beta), but no pack is chosen yet, so Clean Captions")
        print(f"framing: {opts['framing']} · captions: {caps}")
    failed = []
    for n, reel in enumerate(chosen, start=1):
        # A reel the plan left without a name or without segments cannot be set up. That is this reel's
        # failure: the others still get their turn, and it is named at the end with them.
        name = reel.get("name") if isinstance(reel, dict) else None
        if not name:
            print(f"\n=== reel #{n} ===")
            print(f"  ✗ reel #{n}: the plan gives it no name")
            failed.append(f"#{n}")
            continue
        print(f"\n=== reel {name} ===")
        try:
            job = set_up_reel(parent, name, reel, source, words, folder)
        except Exception as e:
            why = f"the plan gives it no {e.args[0]!r}" if isinstance(e, KeyError) else f"{type(e).__name__}: {e}"
            print(f"  ✗ {name}: could not set up its folder, {why}")
            failed.append(name)
            continue
        if build and not _try_build(job, name, reel, opts):
            failed.append(name)

    if failed:
        _quit(f"these reels failed: {', '.join(failed)}")
    print(f"\nBuilt all {len(chosen)} reel(s)." if build
          else f"\nThe folders are ready. Build them with:  cut-shorts.py build {parent.name}")


if __name__ == "__main__":
    main()
