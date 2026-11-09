#!/usr/bin/env python3
"""edits_handoff.py — hand a finished visual-editor reel to Instagram's **Edits** app, as a MEDIUM build.

The Edits counterpart to product/capcut_handoff.py and product/resolve_export.py. Same idea as the DaVinci
Resolve kit: her cut goes in as the footage, and every look rides on top as its own MOVABLE layer she can
nudge, hide or retime. Edits adds nothing creative; it is a destination, exactly like CapCut and Resolve.

MEDIUM ONLY, on purpose. The style packs were authored for CapCut's fonts, so their exact look only survives
when it is RENDERED and carried in as a layer (medium). A "raw" (native, retypeable) export in Edits would
drop the pack styling, because Edits' own text uses Edits' own fonts. So raw-in-Edits is never offered here;
the finish route explains that at the handoff and points at CapCut (or a future Edits-native pack) for raw.
Raw in Resolve is off for the same reason.

WHY THIS IS PREP-ONLY (not a one-shot like CapCut/Resolve). CapCut is driven over HTTP and Resolve is written
as an .fcpxml file — both things a plain Python process can do. The Edits app can only be driven live through
its local MCP tools, and its project-archive format (.mcomp) is turned off in public MCP mode, so there is no
file we can author offline. This module therefore does every DETERMINISTIC step — render the looks, stage the
media where the sandboxed app can read it, and write a build MANIFEST — and the `edits-export` skill replays
the manifest through the live MCP tools (new project -> import the cut -> overlay each look -> save).

THE MANIFEST (projects/<job>/outputs/edits/manifest.json) is the contract the skill drives:
    {
      "job", "project_name", "export": "medium",
      "canvas": {"w", "h"},
      "base":   {"media": "<staged cut>.mp4", "cut": false},   # a pre-cut clip: one main-track clip, no splits
      "overlays": [ {"name", "path": "<staged>.mov", "startSeconds", "x":0.5,"y":0.5,"scale":1.0,
                     "endSeconds", "durationSeconds", "hasAudio"}... ],   # each look, in stacking order
      "cut_total":   <seconds>,
      "staging_dir": "<dir the app must be able to read>"
    }
The drive (skill): newProject -> importMedia(base.media) -> for each overlay addOverlay(path, startSeconds,
x, y, scale) and trim any tail past cut_total -> renameProject(project_name) -> saveProject. Overlays are full
canvas (1080x1920) with alpha, so x/y/scale are centre 0.5,0.5 / 1.0 and need no transform.

Staging: the app (com.burbn.basel.mac) is sandboxed and cannot read arbitrary paths ("Sandbox bookmark
unavailable"), so media is copied into an app-reachable folder first. Default ~/Movies/reels-edits/<job>/
(~/Movies reads cleanly; override with $EDITS_STAGING_DIR). Copies only; the job folder is never touched.

CLI (standalone, renders looks + uses outputs/<job>.mp4 as the cut):
    python3 product/edits_handoff.py <job> [--base <cut.mp4>] [--name <project name>]
Normally finish.py imports build() and passes the cut + already-rendered looks it shares across routes.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _slug(s):
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(s)).strip("-") or "reel"


def staging_dir(job):
    base = os.environ.get("EDITS_STAGING_DIR") or os.path.join(os.path.expanduser("~"), "Movies", "reels-edits")
    d = os.path.join(base, _slug(job))
    os.makedirs(d, exist_ok=True)
    return d


def _stage(src, dst_dir, as_name):
    """Copy src into the app-reachable staging dir under a stable name; return the staged path. Copy only."""
    if not src or not os.path.isfile(src):
        raise SystemExit(f"  ⛔ edits_handoff: missing file to stage: {src!r}")
    ext = os.path.splitext(src)[1] or ".mov"
    dst = os.path.join(dst_dir, _slug(as_name) + ext)
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copy2(src, dst)
    return dst


def _probe(path, *entries):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", ",".join(entries),
             "-of", "default=noprint_wrappers=1", path],
            capture_output=True, text=True, timeout=30).stdout
        got = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                got[k] = v
        return got
    except Exception:
        return {}


def _canvas(path):
    g = _probe(path, "stream=width,height")
    try:
        return int(g.get("width") or 1080), int(g.get("height") or 1920)
    except Exception:
        return 1080, 1920


def _dur(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", path],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def _has_audio(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                              "stream=index", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return bool(out)
    except Exception:
        return False


def edits_reachable(timeout=1.5):
    """Can the Edits app's local MCP be reached? A TCP connect to the metapilot port (default 127.0.0.1:19501;
    override with $EDITS_MCP_HOST / $EDITS_MCP_PORT). The finish route uses this to DEGRADE to CapCut instead
    of dead-ending when Edits isn't running or connected — the engine's "no route is a dead end" law. (The
    other failure mode, the app up but its MCP tools not loaded in the Claude Code client, is caught agent-side
    by the edits-export skill, which can't be probed from here.)"""
    import socket
    host = os.environ.get("EDITS_MCP_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("EDITS_MCP_PORT", "19501"))
    except ValueError:
        port = 19501
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _looks_layers(jd):
    """The live look layers from her page (review/looks.json), in stacking order: (name, comp_dir, start, dur)."""
    try:
        doc = json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    except Exception:
        return []
    out = []
    for L in doc.get("layers", []):
        if L.get("off") or not L.get("dir"):
            continue
        start = float(L.get("offset") or (L.get("span") or [0])[0] or 0)
        out.append((L["name"], os.path.join(jd, L["dir"]), start, float(L.get("dur") or 0)))
    return out


def _render_look(comp_dir, out_mov):
    """Render one look comp to a transparent .mov via the engine's gated renderer. Cached: a no-op if unchanged."""
    os.makedirs(os.path.dirname(out_mov), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(HERE, "reel_render.py"), "render", comp_dir, "-o", out_mov],
                   check=True)
    return out_mov


def build(job, jd, source=None, rendered=None, stage_dir=None, name=None):
    """Prep a MEDIUM Edits build and write the manifest the edits-export skill drives. Mirror of
    resolve_export.build(job, jd, source): `source` is her finished cut (footage, her filter + covered faces
    baked in). `rendered` is finish.py's shared look list [(name, mov, start)]; when omitted (standalone CLI),
    the looks are rendered here from review/looks.json. Returns (manifest_path, overlay_count)."""
    name = name or os.path.basename(jd.rstrip("/"))
    sdir = stage_dir or staging_dir(job)
    os.makedirs(sdir, exist_ok=True)

    # 1) the cut (one pre-cut clip) -> staged where the app can read it
    base = source or os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")
    if not os.path.isfile(base):
        raise SystemExit(f"  ⛔ edits_handoff: no cut to export. Expected {base} (pass --base, or finish the cut first).")
    staged_base = _stage(base, sdir, f"{_slug(job)}--cut")
    cw, ch = _canvas(base)
    cut_total = _dur(base)

    # 2) the looks -> rendered transparent .movs -> staged, each an overlay at its start
    if rendered is None:
        rendered = []
        layers = _looks_layers(jd)                            # editor road: her page's looks (review/looks.json)
        if layers:
            out_dir = os.path.join(jd, "outputs", "edits")
            for lname, comp_dir, start, _d in layers:
                mov = _render_look(comp_dir, os.path.join(out_dir, _slug(lname) + ".mov"))
                rendered.append((lname, mov, start))
        else:                                                 # widget / chat road (the original CapCut path): no
            import glob as _g                                 # per-page looks, so lay the same transparent graphics
            hits = sorted(_g.glob(os.path.join(jd, "renders", "*.mov")),   # overlay CapCut uses (newest renders/*.mov)
                          key=os.path.getmtime, reverse=True)              # as one Edits layer over the footage
            if hits:
                rendered.append(("graphics", hits[0], 0.0))

    overlays = []
    for lname, mov, start in rendered:
        staged = _stage(mov, sdir, f"{_slug(job)}--{_slug(lname)}")
        d = _dur(staged)
        overlays.append({
            "name": lname,
            "path": staged,
            "startSeconds": round(float(start), 3),
            "x": 0.5, "y": 0.5, "scale": 1.0,
            "durationSeconds": round(d, 3),
            "endSeconds": round(float(start) + d, 3),
            "hasAudio": _has_audio(staged),
        })

    manifest = {
        "job": job,
        "project_name": name,
        "export": "medium",
        "canvas": {"w": cw, "h": ch},
        "aspect": "16:9" if cw > ch else "9:16",   # the Edits project frame: horizontal (YouTube) vs vertical (reel)
        "base": {"media": staged_base, "cut": False},
        "overlays": overlays,
        "cut_total": round(cut_total, 3),
        "staging_dir": sdir,
        "note": "MEDIUM export: look layers are preserved as movable overlays. Raw is not offered in Edits "
                "(pack fonts are CapCut-native and would be lost); use CapCut for a styled raw.",
    }
    mpath = os.path.join(jd, "outputs", "edits", "manifest.json")
    os.makedirs(os.path.dirname(mpath), exist_ok=True)
    json.dump(manifest, open(mpath, "w", encoding="utf-8"), indent=1)
    return mpath, len(overlays)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):   # ⛔ needs UTF-8; a cp1252 Windows console cannot print it
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Prep a MEDIUM Edits-app build (staged media + manifest).")
    ap.add_argument("job")
    ap.add_argument("--base", default=None, help="the clean footage cut (default: outputs/<JOB>.mp4)")
    ap.add_argument("--name", default=None, help="Edits project name (default: <JOB>)")
    a = ap.parse_args(argv)
    jd = os.path.join(ROOT, "projects", a.job)
    if not os.path.isdir(jd):
        sys.exit(f"  ⛔ no job at {jd}")
    mpath, n = build(a.job, jd, source=a.base, name=a.name)
    rel = os.path.relpath(mpath, ROOT)
    # the sentinel the finish route / skill parse for:
    print(f"Edits build ready: {rel}  ({n} look layer{'s' if n != 1 else ''} + cut)")
    print("  Next: the edits-export skill drives it into the Edits app from this manifest.")


if __name__ == "__main__":
    main()
