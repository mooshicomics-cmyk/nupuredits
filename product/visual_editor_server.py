#!/usr/bin/env python3
"""visual_editor_server.py — serves the style plan's visual editor to her own browser, from this computer only.

Started by `product/visual_editor.py open <job>`; nothing to run by hand. It:
  * listens on 127.0.0.1 only (nothing off this computer can reach it) and writes its port to
    _local/visual-editor-server.json;
  * serves only the page (product/visual-editor/) and each reel's review/ folder (the preview copy and the
    script), with byte ranges so the player can jump around in every browser (Safari needs them);
  * accepts TWO writes, only from its own page (Host and Origin must be this server, so no website she visits
    can write to her engine):
      POST /save?job=<job>   her edits, checked word by word, written atomically to transcript/script-review.json,
                             then the LEAN round runs right here (seconds), so she never has to say "sent";
      POST /ready?job=<job>  "My cut's ready": the one full-quality cut (or nothing at all when the rough-cut
                             video already matches), then review/phase.json says the cut is locked in;
    one job runs at a time per reel; a problem is kept in review/last-problem.json for the page to say plainly;
  * answers GET /ping (the page's "still connected" check) and quits on its own after two quiet hours.
"""
import http.server, json, os, re, shutil, subprocess, sys, threading, time
from urllib.parse import urlsplit, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product"))
import visual_editor as ve  # noqa: E402
import editor_errors  # noqa: E402
import editor_says  # noqa: E402
import editor_announce  # noqa: E402

PAGE = os.path.join(ROOT, "product", "visual-editor")
PROJECTS = os.path.join(ROOT, "projects")
STATE = ve.SERVER_STATE
IDLE_SECONDS = 2 * 3600
MAX_BODY = 2_000_000
# A Sound tab cue id, and the look a sound sits on: "#" belongs in both, since a look that brings things in at
# separate moments has one sound row per motion, "look:<layer>#2", "#3" ... (sound_plan.moments). Without it, every
# swap / switch / nudge on a look's second motion was refused before it reached the sound plan (a buyer, 2026-10-25).
SOUND_CUE_ID = re.compile(r"^[A-Za-z0-9_.@:+#-]{1,160}$")
SOUND_LAYER_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.#-]{0,79}$")
_last = [time.time()]
VERSION = ve.code_version()
_LAST_SEEN = [time.time()]   # her page's last request: a server she is using is never restarted under her
_STARTED = time.time()      # a reel no page has asked about yet counts as quiet since the server started
_SEEN_JOB = {}               # each reel's page, its last request: a reel's watcher stops when THAT page is closed
_SAYS_JOB = {}               # each reel's page, its last quiet check for Claude's messages (a tab in the background)


def _seen(path):
    """Note which reel's page just asked for something (every page request carries ?job=)."""
    try:
        job = (parse_qs(urlsplit(path).query).get("job") or [""])[0]
        if job:
            _SEEN_JOB[job] = time.time()
    except Exception:
        pass


def _job(job):
    """The reel's folder if `job` names a real reel inside projects/ (any language), else None."""
    if not job or "/" in job or "\\" in job or job.startswith("."):
        return None
    base = os.path.realpath(PROJECTS)
    p = os.path.realpath(os.path.join(base, job))
    return p if os.path.dirname(p) == base and os.path.isdir(p) else None


def _review_file(job, name, sub="review"):
    """projects/<job>/<sub>/<name>, or None when the request reaches outside that folder."""
    if not _job(job) or "/" in name or "\\" in name or name.startswith("."):
        return None
    base = os.path.realpath(os.path.join(PROJECTS, job, sub))
    full = os.path.realpath(os.path.join(base, name))
    return full if full.startswith(base + os.sep) and os.path.isfile(full) else None


# ── Cover a face (product/face_cover.py): finding runs through uv (OpenCV), saving is plain JSON + her cover PNGs ──
_face_running = set()


def _face_find(job, again=False):
    jd = ve.job_dir(job)
    rv = os.path.join(jd, "review")
    if job in _face_running:
        return {"started": False, "running": True}
    found = _read(os.path.join(rv, "faces.json"))
    if found and not again:
        return {"started": False, "ready": True}
    _face_running.add(job)
    with open(os.path.join(rv, "faces-status.json"), "w", encoding="utf-8") as f:
        json.dump({"state": "running", "done": 0, "total": 0, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, f)

    def go():
        try:
            uv = shutil.which("uv") or "uv"
            r = subprocess.run([uv, "run", "-q", os.path.join(ROOT, "product", "face_cover.py"), "find", job],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                why = (r.stderr or r.stdout or "").strip().splitlines()
                with open(os.path.join(rv, "faces-status.json"), "w", encoding="utf-8") as f:
                    json.dump({"state": "failed", "message": (why[-1] if why else "The face search stopped.")[:300]}, f)
                editor_errors.record("face find", "\n".join(why[-6:]), job=job)
        finally:
            _face_running.discard(job)
    threading.Thread(target=go, daemon=True).start()
    return {"started": True}


def _face_cover_save(job, body):
    import base64
    jd = ve.job_dir(job)
    rv = os.path.join(jd, "review")
    found = _read(os.path.join(rv, "faces.json")) or {}
    ids = {f["id"] for f in found.get("faces", [])}
    faces = {}
    for fid, c in (body.get("faces") or {}).items():
        if not str(fid).isdigit() or int(fid) not in ids:
            continue
        kind = c.get("kind") if c.get("kind") in ("blur", "pixel", "emoji", "img") else "blur"
        fixes = {str(int(k)): [float(v[0]), float(v[1])] for k, v in (c.get("fixes") or {}).items()
                 if str(k).lstrip("-").isdigit() and isinstance(v, list) and len(v) == 2}
        faces[str(int(fid))] = {"on": bool(c.get("on")), "kind": kind, "emoji": str(c.get("emoji") or "")[:16],
                                "size": max(1.0, min(3.0, float(c.get("size") or 1.65))), "fixes": fixes,
                                "checked": [int(x) for x in (c.get("checked") or []) if str(x).isdigit()]}
    for fid, url in (body.get("stickers") or {}).items():    # the picture each emoji or sticker cover is, as the page drew it
        if str(fid) in faces and isinstance(url, str) and url.startswith("data:image/png;base64,"):
            png = base64.b64decode(url.split(",", 1)[1])
            if png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) < 1_500_000:
                tmp = os.path.join(rv, f"face-cover-{fid}.png.part")
                open(tmp, "wb").write(png)
                os.replace(tmp, os.path.join(rv, f"face-cover-{fid}.png"))
    doc = {"version": 1, "made_for": found.get("made_for"), "faces": faces, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    tmp = os.path.join(rv, "face-cover.json.part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    os.replace(tmp, os.path.join(rv, "face-cover.json"))
    return {"ok": True, "covered": sum(1 for c in faces.values() if c["on"])}


_heal_lock, _healed = threading.Lock(), {}


def _stale_peaks(job, name):
    """The waveform was made from an older preview (her cut was re-made since)."""
    if name != "peaks.json":
        return False
    try:
        rv = os.path.join(PROJECTS, job, "review")
        return os.path.getmtime(os.path.join(rv, "peaks.json")) < os.path.getmtime(os.path.join(rv, "preview.mp4"))
    except OSError:
        return False


def _heal(job):
    """The page asked for a waveform or a line still that isn't there: make every missing piece from her preview,
    once (the many stills the page asks for at the same moment wait on the one repair, then are served). The quick
    repair only: the preview itself is rebuilt by the engine when the page opens, never inside a request."""
    jd = _job(job)
    if not jd:
        return
    with _heal_lock:
        if time.time() - _healed.get(job, 0) < 15:
            return
        try:
            ve.editor_health(jd, repair=True, preview=False)
        except Exception:
            pass
        _healed[job] = time.time()


_GSAP_CDN = re.compile(r'<script[^>]+src="https://(?:cdn\.jsdelivr\.net/npm/gsap@[^"/]+/dist|cdnjs\.cloudflare\.com/ajax/libs/gsap/[^"/]+)/gsap(?:\.min)?\.js"[^>]*>\s*</script>')


def _mtime(path):
    try:
        return round(os.path.getmtime(path), 3)
    except OSError:
        return None


def _sound_at(jd):
    """A stamp of what her Sound tab reads: her sound edits (review/sound.json) and the plan under them
    (caption-plan.json, else sfx-plan.json). Claude changing any of them in the chat changes it, and an open Sound
    tab refreshes; before, it kept the plan it opened with (a buyer, 2026-10-22)."""
    return "|".join(str(_mtime(os.path.join(jd, *p))) for p in (("review", "sound.json"), ("caption-plan.json",),
                                                                  ("sfx-plan.json",)))


def _graphics_file(job, rel):
    """A file inside one of the reel's graphics folders (hf-graphics, hf-captions, hf-reel-type-*), never outside."""
    if not _job(job) or "\\" in rel or any(p in ("", ".", "..") or p.startswith(".") for p in rel.split("/")):
        return None
    top = rel.split("/")[0]
    base = os.path.realpath(os.path.join(PROJECTS, job, top))
    full = os.path.realpath(os.path.join(PROJECTS, job, rel))
    return full if full.startswith(base + os.sep) and os.path.isfile(full) else None


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "VisualEditor"

    def log_message(self, *a):
        pass

    # ── reads ─────────────────────────────────────────────────────────────────────────────────────────────────
    def _mine(self):
        """Only this server's own address may talk to it (stops a rebinding page reading her transcript)."""
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_address[1]}"

    def do_GET(self):
        try:
            return self._get()
        except ConnectionError:   # broken pipe, reset, or Windows' aborted (10053): the browser let go of a read
            raise
        except Exception:
            editor_errors.record("page read " + urlsplit(self.path).path, job=(parse_qs(urlsplit(self.path).query).get("job") or [""])[0] or None)
            raise

    def _get(self):
        _last[0] = time.time()
        if not self._mine():
            return self._send(403, b"forbidden", "text/plain")
        u = urlsplit(self.path)
        if u.path == "/ping":                              # idle: seconds since her page last asked for anything
            job = (parse_qs(u.query).get("job") or [""])[0]   # ?job=: since THAT reel's page did (two reels open at once)
            now = time.time()                              # pages: every reel whose page is open, even in a background tab
            pages = {j: round(now - max(_SEEN_JOB.get(j, 0), _SAYS_JOB.get(j, 0))) for j in set(_SEEN_JOB) | set(_SAYS_JOB)}
            return self._send(200, json.dumps({"ok": True, "v": VERSION, "busy": bool(_running),
                                               "idle": round(now - _LAST_SEEN[0]),
                                               **({"idle_job": round(now - _SEEN_JOB.get(job, _STARTED))} if job else {}),
                                               "pages": {j: t for j, t in pages.items() if t <= editor_says.OPEN_S}}).encode(), "application/json")
        if u.path == "/says":                              # a page in a background tab: only Claude's messages, and it never
            job = (parse_qs(u.query).get("job") or [""])[0]   # counts as her using the page (the watcher's "page closed" holds)
            jd = _job(job)
            if not jd:
                return self._send(404, b"not found", "text/plain")
            _SAYS_JOB[job] = time.time()
            return self._send(200, json.dumps({"ok": True, "says": editor_says.pending(jd)}).encode(), "application/json")
        _LAST_SEEN[0] = time.time()
        _seen(self.path)
        if u.path == "/tour":                              # which page tours she has finished or skipped (and which version)
            return self._send(200, json.dumps({"seen": ve.tour_seen()}).encode(), "application/json")
        if u.path == "/status":
            job = (parse_qs(u.query).get("job") or [""])[0]
            jd = _job(job)
            if not jd:
                return self._send(404, b"not found", "text/plain")
            if job not in _premake_seen:                   # the page is open on this reel: make its full cut quietly
                _premake_seen.add(job); _premake("schedule", job)
            rv = os.path.join(jd, "review")
            try:
                cut_id = json.load(open(os.path.join(rv, "script.json"), encoding="utf-8")).get("cut_id")
            except Exception:
                cut_id = None
            kind = ve.making_now(jd)                       # a dead update's flag is cleared here, never shown forever
            # a cut round is "making" until it has fully ended: its flag goes before her script is rebuilt, and a
            # refusal there (written to last-problem.json) once arrived AFTER the page had said "Your cut is updated."
            kind = kind or ("lean" if _bg_kind.get(job) == "lean" else "")
            phase, problem = _read(os.path.join(rv, "phase.json")), _read(os.path.join(rv, "last-problem.json"))
            notes = (_read(os.path.join(jd, "transcript", "script-notes.json")) or {}).get("notes", [])
            return self._send(200, json.dumps({"ok": True, "v": VERSION, "cut_id": cut_id, "making": bool(kind),
                                                "kind": kind, "phase": (phase or {}).get("phase", "cut"),
                                                "problem": (problem or {}).get("message"), "problem_at": (problem or {}).get("at"),
                                                "applied": ve.last_applied(jd),   # the newest Send that reached her cut
                                                "notes": notes, "looks_at": _mtime(os.path.join(rv, "looks.json")),
                                                "sound_at": _sound_at(jd),        # her sound plan changed (in the chat too)
                                                "ui": _mtime(os.path.join(ROOT, "product", "visual-editor", "editor.html")),   # the page knows when it was updated
                                                "finish": _finish_status(jd),
                                                "claude_has": (_read(os.path.join(rv, "claude-working.json")) or {}).get("ids") or [],
                                                "claude_age": _claim_age(rv),
                                                "queue": _queue(job),             # her task queue: what she sent Claude, and how far each got
                                                "looks_v": _looks_v(jd),          # each look page's version NOW: a frame drawn again is reloaded
                                                "watching": ve.watching(jd),
                                                "chat": ve.chat_messages(jd),     # her own messages to Claude, from the chat panel
                                                "says": editor_says.pending(jd),   # Claude's messages for her (in the chat)
                                                "announce": editor_announce.pending(jd)}).encode(), "application/json")   # the bell: REE updates + you note
        if u.path == "/favorite-file":                   # a thumbnail in the Image picker: her own favorites file
            q = parse_qs(u.query)
            try:
                return self._file(ve.media_path((q.get("id") or [""])[0]))
            except Exception:
                return self._send(404, b"not found", "text/plain")
        if u.path == "/favorite-poster":                 # a still of her b-roll clip, for its tile in the Media picker
            q = parse_qs(u.query)
            try:
                return self._file(ve.media_poster((q.get("id") or [""])[0]))
            except Exception:
                return self._send(404, b"not found", "text/plain")
        if u.path == "/trials":                          # her Finish tab's Trial reels section
            job = (parse_qs(u.query).get("job") or [""])[0]
            if not _job(job):
                return self._send(404, b"not found", "text/plain")
            try:
                return self._json(200, ve.trials_view(job))
            except ve.Refuse as e:
                return self._json(409, {"error": str(e)})
        if u.path == "/trial-still":                     # a reel's opening shot, for its trial tile
            job = (parse_qs(u.query).get("job") or [""])[0]
            return self._file(ve.trial_still(job)) if _job(job) else self._send(404, b"not found", "text/plain")
        if u.path == "/trial-file":                      # a finished trial (or her reel), to watch on its tile
            job = (parse_qs(u.query).get("job") or [""])[0]
            jd = _job(job)
            if not jd:
                return self._send(404, b"not found", "text/plain")
            out = os.path.join(jd, "outputs")
            f = os.path.join(out, job + ".final.mp4")
            return self._file(f) if os.path.isfile(f) else self._send(404, b"not found", "text/plain")
        if u.path == "/cutaway-source":                  # a cutaway's whole clip (the copy kept with her reel), to slip it
            q = parse_qs(u.query)
            job, layer = (q.get("job") or [""])[0], (q.get("layer") or [""])[0]
            jd = _job(job)
            if not jd or not re.match(r"^(add|cap)-[A-Za-z0-9_-]{1,40}$", layer):
                return self._send(404, b"not found", "text/plain")
            m = ve.media_of(jd, layer) or {}
            f = os.path.realpath(os.path.join(jd, m.get("file") or ""))
            if m.get("kind") != "Video" or not f.startswith(os.path.realpath(os.path.join(jd, "assets", "media")) + os.sep):
                return self._send(404, b"not found", "text/plain")
            return self._file(f)
        if u.path == "/sound-preview":                   # a sound from her Sound section, by its engine id
            q = parse_qs(u.query)
            job, cid = (q.get("job") or [""])[0], (q.get("id") or [""])[0]
            if not _job(job) or not re.match(r"^(lib|fav|folder|job|file|epi):[^\x00]{1,300}$", cid) or ".." in cid:
                return self._send(404, b"not found", "text/plain")
            try:
                import sound_plan
                f = sound_plan.preview_path(cid, job)
            except Exception:
                return self._send(404, b"not found", "text/plain")
            return self._file(f)
        if u.path in ("/editor", "/editor/"):
            return self._file(os.path.join(PAGE, "editor.html"))
        if u.path == "/accents":
            job = (parse_qs(u.query).get("job") or [""])[0]
            if not _job(job):
                return self._send(404, b"not found", "text/plain")
            return self._send(200, json.dumps(_read(os.path.join(ve.job_dir(job), "transcript", "accents.json")) or {"items": []}).encode(), "application/json")
        if u.path == "/page-draft":                          # her unsent edits, kept server-side, for a refresh to pick up
            job = (parse_qs(u.query).get("job") or [""])[0]
            if not _job(job):
                return self._send(404, b"not found", "text/plain")
            return self._send(200, json.dumps(_read(os.path.join(ve.job_dir(job), "review", "page-draft.json")) or {}).encode(), "application/json")
        if u.path == "/snaps":
            job = (parse_qs(u.query).get("job") or [""])[0]
            return self._send(200, json.dumps(ve.snaps(job)).encode(), "application/json") if _job(job) else self._send(404, b"not found", "text/plain")
        if u.path == "/vendor/gsap.min.js":
            return self._file(os.path.join(PAGE, "vendor", "gsap.min.js"))
        m = re.match(r"^/projects/([^/]+)/((?:hf-graphics|hf-captions|hf-reel-type-[A-Za-z0-9_.-]+)/.+)$", u.path)
        if m:                                              # the reel's graphics, played live in the looks step
            from urllib.parse import unquote
            f = _graphics_file(unquote(m.group(1)), unquote(m.group(2)))
            if f and f.endswith(".html"):
                html = open(f, encoding="utf-8", errors="replace").read()
                html = _GSAP_CDN.sub('<script src="/vendor/gsap.min.js"></script>', html)   # works offline
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return self._file(f) if f else self._send(404, b"not found", "text/plain")
        m = re.match(r"^/projects/([^/]+)/snaps/([^/]+)$", u.path)
        if m:
            from urllib.parse import unquote
            f = _review_file(unquote(m.group(1)), unquote(m.group(2)), os.path.join("thumbnails", "snaps"))
            return self._file(f) if f else self._send(404, b"not found", "text/plain")
        m = re.match(r"^/projects/([^/]+)/review/(?:(strip)/)?([^/]+)$", u.path)   # strip/ = the timeline's line stills
        if m:
            from urllib.parse import unquote
            job, name, sub = unquote(m.group(1)), unquote(m.group(3)), os.path.join("review", "strip") if m.group(2) else "review"
            f = _review_file(job, name, sub)
            if m.group(2) and _job(job):                       # a still for any piece's first word: made on the spot, and
                                                               # remade when it came from an older cut (make_still checks)
                wm = re.fullmatch(r"w(\d+)\.jpg", name)
                if wm:
                    try:
                        jd = _job(job)
                        ve.make_still(jd, json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")), int(wm.group(1)))
                    except Exception:
                        pass
                    f = _review_file(job, name, sub)
            if (m.group(2) or name == "peaks.json") and (not f or _stale_peaks(job, name)):
                _heal(job)                                     # a missing or out-of-date waveform or still: made now
                f = _review_file(job, name, sub)
            return self._file(f) if f else self._send(404, b"not found", "text/plain")
        return self._send(404, b"not found", "text/plain")

    do_HEAD = do_GET

    def _file(self, path):
        if not path or not os.path.isfile(path):
            return self._send(404, b"not found", "text/plain")
        size = os.path.getsize(path)
        ctype = {".html": "text/html; charset=utf-8", ".json": "application/json", ".mp4": "video/mp4",
                 ".jpg": "image/jpeg", ".png": "image/png", ".js": "text/javascript", ".css": "text/css",
                 ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2", ".svg": "image/svg+xml",
                 ".webp": "image/webp", ".gif": "image/gif", ".mov": "video/quicktime", ".m4v": "video/mp4", ".webm": "video/webm",
                 ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".jpeg": "image/jpeg"}.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        start, end = 0, size - 1
        if m:
            if m.group(1):
                start = int(m.group(1)); end = min(int(m.group(2)), size - 1) if m.group(2) else end
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        if m:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start); left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk); left -= len(chunk)
            except ConnectionError:   # broken pipe, reset, or Windows' aborted (10053): the browser let go of a read
                pass

    # ── the one write ────────────────────────────────────────────────────────────────────────────────────────
    def do_POST(self):
        _LAST_SEEN[0] = time.time()                                     # counted, so an update never restarts the editor mid-write
        _seen(self.path)
        with _guard:
            _inflight[0] += 1
        try:
            return self._post()
        except ConnectionError:   # broken pipe, reset, or Windows' aborted (10053): the browser let go of a read
            raise
        except Exception:
            editor_errors.record("page write " + urlsplit(self.path).path, job=(parse_qs(urlsplit(self.path).query).get("job") or [""])[0] or None)
            raise
        finally:
            with _guard:
                _inflight[0] -= 1

    def _post(self):
        _last[0] = time.time()
        u = urlsplit(self.path)
        if u.path not in ("/log-error", "/report", "/report-show", "/save", "/ready", "/looks-ready", "/finish", "/finish-stop", "/finish-allow", "/retime", "/open-outputs", "/open-capcut", "/open-edits", "/open-staging", "/open-favorites", "/open-library", "/favorite-media", "/favorite-upload", "/favorite-keep", "/check-ok", "/footage-folders", "/broll-fill", "/place-media", "/cutaway", "/sound", "/sound-choices", "/sound-swap", "/sound-toggle", "/sound-music", "/sound-add", "/sound-remove", "/sound-nudge", "/sound-switch", "/sound-defaults", "/sound-playback", "/back", "/notes", "/snap", "/snap-mark", "/snap-folder", "/accents",
                          "/swap-menu", "/swap", "/lookbook", "/reel-pack", "/default-pack", "/tour-seen", "/grade", "/hashtag-off", "/add-menu", "/nudge", "/refine", "/refine-apply", "/behind", "/captions-redraw", "/lines", "/look-frame", "/look-request", "/sandbox-try", "/sandbox-keep", "/sandbox-drop", "/sandbox-sketches", "/sandbox-remix", "/look-restore", "/kit-request", "/face-find", "/face-cover", "/trial-request", "/trials-export", "/trial-won", "/says-seen", "/announce-seen", "/chime", "/page-draft", "/chat"):
            return self._json(404, {"error": "not found"})
        me = f"127.0.0.1:{self.server.server_address[1]}"
        origin = self.headers.get("Origin")
        if self.headers.get("Host") != me or (origin and origin != f"http://{me}"):
            return self._json(403, {"error": "This page can only be saved from the visual editor itself."})
        job = (parse_qs(u.query).get("job") or [""])[0]
        if u.path in ("/log-error", "/report", "/report-show"):
            return self._report(u.path, job)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        held = _job(job) and u.path in _HOLD_WHILE_EXPORTING and _running_kind(ve.job_dir(job))
        if _job(job) and u.path in _HOLD_WHILE_EXPORTING and not held and ve.exporting(ve.job_dir(job)):
            held = "finish"                               # an export typed in the chat runs in its own process: held the same
        if held in _EXPORT_KINDS:                         # one export = one set of looks
            return self._json(409, {"error": "Your export is running. Make this change when it's done, or stop the export first."})
        if held:                                          # her cut still updating (a second Send, a change mid-update): wait a moment
            return self._json(409, {"error": "Hold on a moment, your last change is still being made.", "busy": True})
        if not _job(job) or n <= 0 or n > (max(ve.MEDIA_MAX_BYTES, ve.VIDEO_MAX_BYTES) * 4 // 3 + 4096 if u.path == "/favorite-upload" else MAX_BODY):
            return self._json(400, {"error": "That save didn't look right. Try “Send my cut” again."})
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if u.path == "/says-seen":                     # she closed Claude's message: it never pops again
                return self._json(200, {"closed": editor_says.seen(_job(job), [str(i) for i in (body.get("ids") or [])][:20])})
            if u.path == "/announce-seen":                 # she dismissed a bell announcement (REE update / you note)
                return self._json(200, {"seen": editor_announce.seen(_job(job), [str(i) for i in (body.get("ids") or [])][:20])})
            if u.path == "/chime":                         # a message landed while her page was in another tab
                return self._json(200, {"played": editor_says.chime()})
            if u.path == "/ready":
                return self._json(200, ready(job, body))
            if u.path == "/accents":
                return self._json(200, save_accents(job, body))
            if u.path == "/page-draft":                    # her unsent edits, kept server-side too so a refresh never loses
                p = os.path.join(ve.job_dir(job), "review", "page-draft.json")   # them when the browser won't keep a local draft
                if body.get("draft"):
                    ve._atomic_json(p, {"draft": body["draft"]})
                elif os.path.isfile(p):
                    os.remove(p)
                return self._json(200, {"ok": True})
            if u.path == "/lookbook":
                return self._json(200, ve.with_hearts(ve.lookbook_view(job, body.get("pack"))))
            if u.path == "/tour-seen":                     # she finished or skipped a tour: never again until its words change
                return self._json(200, ve.tour_mark(str(body.get("tab") or ""), str(body.get("v") or "")))
            if u.path == "/hashtag-off":
                import hashtag
                hashtag.set_off(True)
                return self._json(200, {"off": True})
            if u.path == "/grade":
                return self._json(200, ve.set_grade(job, body.get("look")))
            if u.path == "/face-find":                     # Cover a face: follow every face in her clips (a minute or so)
                return self._json(200, _face_find(job, bool(body.get("again"))))
            if u.path == "/face-cover":                    # Cover a face: who's hidden, under what, and her fixes
                return self._json(200, _face_cover_save(job, body))
            if u.path == "/reel-pack":
                return self._json(200, ve.set_pack(job, str(body.get("pack") or "")))
            if u.path == "/default-pack":                  # Lookbook: this pack for every new reel
                return self._json(200, ve.set_default_pack(str(body.get("pack") or "")))
            if u.path == "/look-frame":                    # the still for "Build a new look" (the line she picked)
                t = float(body.get("t"))
                if not 0 <= t < 36000:
                    raise ValueError
                return self._json(200, {"frame": ve._frame_at(ve.job_dir(job), t, "newlook", width=540)})
            if u.path == "/look-request":                  # her idea for a new look, kept for the chat
                w = body.get("w")
                return self._json(200, ve.new_look_request(job, int(w) if w is not None else None,
                                                           float(body["start"]) if body.get("start") is not None else None,
                                                           float(body["end"]) if body.get("end") is not None else None,
                                                           str(body.get("text", "")),
                                                           mode=str(body.get("mode") or "build"),
                                                           at=float(body["at"]) if body.get("at") is not None else None,
                                                           media=str(body["media"]) if body.get("media") else None))
            if u.path == "/check-ok":                      # "it's okay": a finding she meant, kept quiet and let through Finish
                return self._json(200, ve.check_ok(job, str(body.get("layer", "")), str(body.get("kind", ""))))
            if u.path == "/favorite-media":                # her images and GIFs, for the Image picker
                return self._json(200, {"items": ve.favorite_media(), "inbox": ve.inbox_media(job)})
            if u.path == "/favorite-keep":                 # an inbox one-off she wants in her library after all
                return self._json(200, {"kept": [ve.favorite_keep(str(i)) for i in (body.get("ids") or [])[:20]]})
            if u.path == "/favorite-upload":               # a file she dropped on the picker: into her favorites
                return self._json(200, ve.favorite_upload(body.get("name"), body.get("data")))
            if u.path == "/footage-folders":               # Fill with my b-roll: her inbox folders with clips in them
                return self._json(200, {"folders": ve.footage_folders(), "folder": ve._fill_folder(ve.job_dir(job)),
                                        "asked": ve._read_json(os.path.join(ve.job_dir(job), "review", "broll-fill.json"))})
            if u.path == "/broll-fill":                    # her pick of folder (and what she wants), kept for Claude
                return self._json(200, ve.broll_fill_request(job, str(body.get("folder") or ""), str(body.get("text") or ""),
                                                             lines=(body.get("lines") or [])[:400]))
            if u.path == "/place-media":                   # her image or GIF on a line, as an overlay
                return self._json(200, ve.place_media(job, float(body["start"]), float(body["end"]), str(body.get("id", ""))))
            if u.path == "/cutaway":                       # her b-roll cutaway: slip it, move it, sound on or off
                f = lambda k: float(body[k]) if body.get(k) is not None else None
                return self._json(200, ve.cutaway_set(job, str(body.get("layer", "")), slip=f("slip"), start=f("start"),
                                                      end=f("end"), sound=body.get("sound"), effect=body.get("effect"),
                                                      best=bool(body.get("best"))))
            if u.path == "/sandbox-try":                   # she tapped a take: it plays on her line
                return self._json(200, ve.sandbox_try(job, str(body.get("id")), str(body.get("look"))))
            if u.path == "/sandbox-keep":                  # commit: her lookbook (every reel) or this reel only
                return self._json(200, ve.sandbox_keep(job, str(body.get("id")), str(body.get("keep")), body.get("name"),
                                                       str(body["look"]) if body.get("look") else None))
            if u.path == "/look-restore":                  # Bring back / Undo: what was on that line before
                return self._json(200, ve.bring_back(job, str(body.get("layer")), phase=body.get("phase")))
            if u.path == "/sandbox-sketches":              # her three sketches, drawn on their moment, for the panel
                return self._json(200, ve.sandbox_sketches(job, str(body.get("id"))))
            if u.path == "/sandbox-remix":                 # another round: what to change, from which sketch
                return self._json(200, ve.sandbox_remix(job, str(body.get("id")), str(body.get("text", "")),
                                                        str(body["look"]) if body.get("look") else None))
            if u.path == "/sandbox-drop":                  # cancel: the takes go, her line goes back
                return self._json(200, ve.sandbox_drop(job, str(body.get("id"))))
            if u.path == "/lines" and "restore" in body:   # Undo / Redo of a split or combine
                sid = str(body["restore"])
                if not re.match(r"^[0-9a-f]{8}$", sid):
                    raise ValueError
                return self._json(200, ve.restore_lines(job, sid))
            if u.path == "/lines":                         # split or combine lines (and the looks on them follow)
                op, w = body.get("op"), int(body.get("w"))
                keyok = lambda k: isinstance(k, str) and re.match(r"^(add|cap)-[A-Za-z0-9_-]{1,40}$", k)
                looks = [{"layer": x["layer"], "start": float(x["start"]), "end": float(x["end"])} for x in body.get("looks", [])]
                drop = list(body.get("drop", []))
                if op not in ("split", "join") or not all(keyok(x["layer"]) for x in looks) or not all(keyok(d) for d in drop) or len(looks) + len(drop) > 8:
                    raise ValueError
                return self._json(200, ve.edit_lines(job, op, w, looks, drop))
            if u.path == "/captions-redraw":
                return self._json(200, ve.redraw_captions(job))
            if u.path == "/behind":
                layer = str(body.get("layer", ""))
                if not re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$", layer) or ".." in layer:
                    raise ValueError
                return self._json(200, ve.set_behind(job, layer, bool(body.get("on"))))
            if u.path in ("/nudge", "/refine", "/refine-apply"):    # moving and refining a look she placed
                layer = str(body.get("layer", ""))
                if not re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$", layer) or ".." in layer:
                    raise ValueError
                if u.path == "/nudge":
                    opt = lambda k: float(body[k]) if body.get(k) is not None else None
                    return self._json(200, ve.nudge(job, layer, float(body.get("dx", 0)), float(body.get("dy", 0)),
                                                    opt("s"), opt("r"), opt("ox"), opt("oy"), on_face=bool(body.get("on_face"))))
                if u.path == "/refine":
                    look = str(body.get("look", ""))
                    eff = body.get("effect") or None
                    if not re.match(r"^[a-z0-9-]{1,60}$", look) or (eff and not re.match(r"^[a-z0-9-]{1,60}$", str(eff))):
                        raise ValueError
                    txt = str(body.get("text") or "")[:300] or None
                    pk = str(body["pack"])[:60] if body.get("pack") else None
                    font = str(body.get("font") or "")[:80] or None     # her font override (one of her own fonts); None keeps the pack
                    frole = str(body.get("font_role") or "")[:20] or None
                    return self._json(200, ve.refine(job, layer, look, txt, float(body.get("size", 1.0)), eff, pk, font=font, font_role=frole))
                scope = body.get("scope")
                if scope not in ("moment", "pack"):
                    raise ValueError
                return self._json(200, ve.refine_apply(job, layer, scope, str(body.get("name") or "")[:40]))
            if u.path == "/add-menu":
                key = str(body.get("key", ""))
                if not re.match(r"^(add|cap)-[A-Za-z0-9_-]{1,40}$", key):
                    raise ValueError
                return self._json(200, ve.with_hearts(ve.add_menu(job, key, float(body["start"]), float(body["end"]), "caption" if body.get("kind") == "caption" else None)))
            if u.path in ("/swap-menu", "/swap"):             # swapping one line's look (drawn in seconds, never a render)
                layer = str(body.get("layer", ""))
                if not re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$", layer) or ".." in layer:
                    raise ValueError
                if u.path == "/swap-menu":
                    return self._json(200, ve.with_hearts(ve.swap_menu(job, layer)))
                look = body.get("look")
                if look is not None and look != "_off" and not re.match(r"^[a-z0-9-]{1,60}$", str(look)):
                    raise ValueError
                return self._json(200, ve.swap(job, layer, look, from_menu=True, copy=str(body.get("copy") or "")[:400] or None))   # her pick from the menu (a hook: with its own words)
            if u.path == "/back":
                return self._json(200, back_to(job, body))
            if u.path.startswith("/sound"):              # her Sound section: every cue and the music bed
                import sound_plan
                cue = str(body.get("cue", ""))
                if cue and not SOUND_CUE_ID.match(cue):
                    raise ValueError
                try:
                    if u.path == "/sound":
                        return self._json(200, sound_plan.read(job))
                    if u.path == "/sound-choices":
                        return self._json(200, {"choices": sound_plan.choices(str(body.get("kind", "sfx")), job)})
                    if u.path == "/sound-swap":
                        return self._json(200, sound_plan.swap(job, cue, str(body.get("choice", ""))))
                    if u.path == "/sound-toggle":
                        return self._json(200, sound_plan.toggle(job, cue, bool(body.get("on"))))
                    if u.path == "/sound-add":                 # a sound at the playhead, or on a look's entrance
                        t, layer, word = body.get("t"), body.get("layer"), body.get("word")
                        if layer is not None and (not SOUND_LAYER_ID.match(str(layer)) or ".." in str(layer)):
                            raise ValueError
                        return self._json(200, sound_plan.add_cue(job, str(body.get("choice", "")), t=None if t is None else float(t),
                                                                  layer=layer, word=None if word is None else int(word)))
                    if u.path == "/sound-remove":
                        return self._json(200, sound_plan.remove_cue(job, cue))
                    if u.path == "/sound-nudge":
                        return self._json(200, sound_plan.nudge(job, cue, float(body.get("delta", 0))))
                    if u.path == "/sound-switch":              # the reel-wide "Sound effects" switch
                        return self._json(200, sound_plan.set_sfx_enabled(job, bool(body.get("on"))))
                    if u.path == "/sound-playback":            # what the preview plays in sync: times + render levels
                        return self._json(200, sound_plan.playback(job))
                    if u.path == "/sound-defaults":            # a sound on every look that has none yet (never over hers)
                        return self._json(200, sound_plan.apply_defaults(job))
                    if u.path == "/sound-music" and body.get("step") is not None:   # Louder / Quieter (remembered)
                        return self._json(200, sound_plan.music_step(job, float(body["step"])))
                    if u.path == "/sound-music":
                        kw = {k: body[k] for k in ("on", "level_db") if k in body}
                        if body.get("choice"):
                            kw["choice_id"] = str(body["choice"])
                        return self._json(200, sound_plan.set_music(job, **kw))
                except sound_plan.Refuse as e:
                    raise ve.Refuse(str(e))
                raise ValueError
            if u.path == "/open-favorites":               # her favorites folder, in Finder / Explorer
                folder = os.path.join(ve.ROOT, "inbox" if body.get("which") == "inbox" else "favorites")
                os.makedirs(folder, exist_ok=True)
                opener = ["open", folder] if sys.platform == "darwin" else (["explorer", os.path.normpath(folder)] if os.name == "nt" else ["xdg-open", folder])
                subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._json(200, {"ok": True})
            if u.path == "/open-library":                 # the whole Effects Library, in her own browser (served, so sounds play)
                tab = str(body.get("tab", ""))
                if tab not in ("effects", "sounds"):
                    raise ValueError
                subprocess.Popen([ve._bash(), os.path.join(ve.ROOT, "scripts", "open-library.sh"), tab], cwd=ve.ROOT,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                return self._json(200, {"ok": True})
            if u.path == "/retime":                       # her cut changed: the looks she added follow their words
                return self._json(200, ve.retime_adds(job))
            if u.path == "/finish-allow":                 # "it's on purpose": this look may sit over her face
                import finish
                layer = str(body.get("layer", ""))
                more = [str(x) for x in (body.get("layers") or [])][:60]          # "they're on purpose": every look listed
                for x in [layer] + more:
                    if not re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$", x) or ".." in x:
                        raise ValueError
                for x in more:
                    finish.allow(job, x)
                if body.get("always"):                       # "always fine on a close-up like this": her taught default
                    import learned
                    learned.add("hook.on_hair", True, note="said on the Finish tab", from_job=os.path.basename(ve.job_dir(job)))
                # on a shot with no room above your head, "it's on purpose" covers every look on her hair in this reel,
                # so one tap, not one render per look (her face still asks look by look)
                hair = "no room above your head" in str((finish.status(ve.job_dir(job)) or {}).get("message", ""))
                return self._json(200, {"allowed": finish.allow(job, layer, hair=hair)})
            if u.path == "/finish":
                return self._json(200, start_finish(job, body))
            if u.path == "/finish-stop":
                import finish
                return self._json(200, {"stopped": finish.stop(job, starting=_rendering(ve.job_dir(job)))})
            if u.path == "/looks-ready":
                return self._json(200, looks_ready(job, body))
            if u.path == "/notes":
                return self._json(200, {"notes": save_notes(job, body)})
            if u.path == "/chat":                              # a message she typed in the chat panel, for Claude's watcher to pick up
                return self._json(200, ve.chat_send(job, str(body.get("text") or "")))
            if u.path == "/snap":
                t, at = float(body.get("t")), body.get("at")
                if not 0 <= t < 36000:
                    raise ValueError
                return self._json(200, {"snap": ve.snap(job, t, float(at) if at is not None else None), **ve.snaps(job)})
            if u.path == "/open-outputs":                 # her exported reel, in Finder / Explorer (this machine only)
                folder = os.path.join(ve.job_dir(job), "outputs")
                opener = ["open", folder] if sys.platform == "darwin" else (["explorer", os.path.normpath(folder)] if os.name == "nt" else ["xdg-open", folder])
                subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._json(200, {"ok": True})
            if u.path == "/open-staging":                 # a draft waiting for her one double-click into CapCut
                import capcut_store_redirect
                capcut_store_redirect.open_folder(force=True)
                return self._json(200, {"ok": True})
            if u.path == "/open-capcut":                  # her export is in CapCut: open the app (the desktop one), nothing more
                subprocess.Popen([sys.executable, os.path.join(ROOT, "product", "capcut_installs.py"), "--open"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._json(200, {"ok": True})
            if u.path == "/open-edits":                   # her reel is in the Edits app: bring the app forward
                subprocess.Popen([sys.executable, os.path.join(ROOT, "product", "edits_open.py")],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._json(200, {"ok": True})
            if u.path == "/snap-folder":                  # open her snaps in Finder / Explorer (this machine only)
                folder = os.path.join(ve.job_dir(job), "thumbnails", "snaps")
                os.makedirs(folder, exist_ok=True)
                opener = ["open", folder] if sys.platform == "darwin" else (["explorer", os.path.normpath(folder)] if os.name == "nt" else ["xdg-open", folder])
                subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._json(200, {"ok": True})
            if u.path == "/trial-request":                 # Make trial reels, on her finished reel
                return self._json(200, ve.trial_request(job))
            if u.path == "/trials-export":                 # Export all trials, from her page, one at a time
                return self._json(200, start_trials_export(job, body))
            if u.path == "/trial-won":                     # This one won: Claude keeps that trial's angle as a rule
                return self._json(200, ve.trial_won(job, str(body.get("id", "")).lower()))
            if u.path == "/kit-request":                   # Make a carousel / Make a story, with the snaps she ticked
                frames, photos = body.get("frames") or [], body.get("photos") or []
                if not isinstance(frames, list) or len(frames) > 60 or not isinstance(photos, list) or len(photos) > 20:
                    raise ValueError
                return self._json(200, ve.kit_request(job, str(body.get("kind", "")), [str(f) for f in frames],
                                                      [str(x) for x in photos]))
            if u.path == "/snap-mark":
                name = str(body.get("name", ""))
                if not re.match(r"^snap-\d+-[0-9a-z]+\.jpg$", name):
                    raise ValueError
                return self._json(200, ve.snap_mark(job, name, cover=body.get("cover"), remove=bool(body.get("remove"))))
            with _guard:                                   # check BEFORE writing anything: never a half-taken send
                if job in _running or ve.making_now(ve.job_dir(job)):
                    raise Busy()
            saved = save(job, body)
            run_in_background(job, "lean", lambda: ve.apply(job, log=lambda *a: None), after=lambda: _premake("schedule", job))
            saved["updating"] = True
        except (Busy, ve.Busy):
            return self._json(409, {"error": "Hold on a moment, your last change is still being made.", "busy": True})
        except Stale as e:                                 # her page reloads onto the newer cut (never the old one sent)
            editor_errors.record("page " + u.path, str(e), job=job, kind="told")
            return self._json(409, {"error": str(e), "stale": True})
        except ve.Refuse as e:
            editor_errors.record("page " + u.path, str(e), job=job, kind="told")
            return self._json(409, {"error": str(e)})
        except Exception as e:
            if type(e).__name__ == "Refuse":                 # the lookbook's own plain-words reasons
                editor_errors.record("page " + u.path, str(e), job=job, kind="told")
                return self._json(409, {"error": str(e)})
            editor_errors.record("page " + u.path, job=job)
            if u.path == "/save":
                return self._json(400, {"error": "That save didn't look right. Try “Send my cut” again."})
            return self._json(400, {"error": "That didn't go through. Try again in a moment."})
        return self._json(200, saved)

    def _report(self, path, job):
        """The page's problem reporting: an error in the page itself, written down; "Report a problem", one file in
        _handoff/ for her to email; and that file shown in Finder / Explorer. Nothing leaves this computer."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8")) if 0 < n <= 64_000 else {}
        except Exception:
            body = {}
        job = job if _job(job) else None
        if path == "/log-error":
            key = str(body.get("msg", ""))[:200]
            _page_errors[key] = _page_errors.get(key, 0) + 1
            if _page_errors[key] <= 3 and len(_page_errors) <= 100:   # a page error in a loop is written down a few times, not thousands
                # "told" = a plain-words hold she was shown (409 "still being made" / "export is running"): written
                # down, never counted as an error in her problem report. Anything else the page sends is an error.
                kind = "told" if body.get("kind") == "told" else "error"
                editor_errors.record("page script", key, job=job, kind=kind,
                                     trace=(str(body.get("stack", ""))[:2000] or None) if kind == "error" else None,
                                     tab=body.get("tab"), phase=body.get("phase"), browser=self.headers.get("User-Agent"),
                                     page=body.get("page"))
            return self._json(200, {"ok": True})
        if path == "/report":
            page = {"browser": self.headers.get("User-Agent"), "tab": body.get("tab"), "phase": body.get("phase"), "page": body.get("page")}
            f = editor_errors.bundle(job, str(body.get("note", "")), page)
            _reports[os.path.basename(f)] = f
            return self._json(200, {"file": os.path.basename(f), "email": editor_errors.SUPPORT_EMAIL})
        f = _reports.get(str(body.get("file", "")))
        if not f or not os.path.isfile(f):
            return self._json(404, {"error": "That report isn't here any more. Press Make my report again."})
        editor_errors.reveal(f)
        return self._json(200, {"ok": True})

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


class Busy(Exception):
    """A stitch for this reel is already running."""


class Stale(ve.Refuse):
    """Her page shows a cut that has changed since (Claude's fix from the chat): it reloads, then she sends again."""


_running, _guard = set(), threading.Lock()
_bg_kind = {}                                # job -> the kind of background job running for it ("lean", "finish", ...)
_inflight = [0]                                            # page writes being handled right now
_page_errors, _reports = {}, {}                            # page errors written down this run; report files made
_premake_seen = set()


def _premake(what, job):
    """The full-quality cut made quietly in the background (product/premake.py). Never able to break the page:
    any trouble there just means "Lock in my cut" makes it the normal way."""
    try:
        import premake
        if what == "adopt":
            return premake.adopt(job)
        if what == "cancel":
            premake.cancel(job)
        elif what == "schedule":
            premake.schedule(job)
    except Exception:
        return False
    return False


def _read(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def run_in_background(job, kind, fn, after=None):
    """Run one engine job for this reel off the request thread; never two at once. A Refuse is kept for the page
    in plain words; anything else becomes a plain "something went wrong" with the way out."""
    with _guard:
        if job in _running:
            raise Busy()
        _running.add(job)
        _bg_kind[job] = kind
    rv = os.path.join(ve.job_dir(job), "review")
    prob = os.path.join(rv, "last-problem.json")
    if os.path.exists(prob):
        os.remove(prob)

    def work():
        try:
            fn()
            if after:
                after()
        except ve.Refuse as e:
            editor_errors.record("background " + kind, str(e), job=job, kind="told")
            ve._atomic_json(prob, {"message": str(e), "at": time.strftime("%Y-%m-%d %H:%M:%S"), "busy": isinstance(e, ve.Busy)})
        except Exception:
            editor_errors.record("background " + kind, job=job)
            ve._atomic_json(prob, {"message": "Something went wrong updating your cut. Your edits are safe. Tell me "
                                              "in the chat and I'll take it from there.", "at": time.strftime("%Y-%m-%d %H:%M:%S")})
        finally:
            with _guard:
                _running.discard(job)
                _bg_kind.pop(job, None)

    threading.Thread(target=work, daemon=True).start()


def ready(job, body):
    """"Lock in my cut": phase 1 done, at once. Her cut is the plan she set on the page; its video is made at Finish."""
    jd = ve.job_dir(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if body.get("id") != script["id"]:
        raise ve.Refuse("This page is from before the transcript changed. Reload the page first.")
    # her call: Lock in locks in, even with notes still open. A fix Claude makes after keeps her lock and her looks
    # follow it (visual_editor._keep_lock), so nothing is lost by not waiting
    open_notes = [n for n in (_read(os.path.join(jd, "transcript", "script-notes.json")) or {}).get("notes", []) if n.get("status") != "fixed"]
    with _guard:
        if job in _running or ve.making_now(jd):
            raise Busy()
    phase = os.path.join(jd, "review", "phase.json")
    mark = lambda: ve._atomic_json(phase, {"phase": "looks", "cut_locked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                           "cut_id": json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")).get("cut_id")})
    # Locking in is instant: what she set on the page IS her cut. The video itself is made once, at Finish, with
    # her looks and sounds (finish.py), so she never waits between layers. A background cut already made is kept.
    if ve.base_is_stale(job):
        _premake("adopt", job)
    _premake("cancel", job)
    mark()
    if ve.voiceover_of(jd):                               # a voiceover: Visuals opens now, for her clips
        ve.looks_manifest(jd)
    return {"locked": True, "instant": True, **({"notes_open": len(open_notes)} if open_notes else {})}


def back_to(job, body):
    """She steps back a phase from the page (Looks → Cut, Render → Looks). Her looks stay; only the phase moves."""
    jd = ve.job_dir(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if body.get("id") != script["id"]:
        raise ve.Refuse("This page is from before the transcript changed. Reload the page first.")
    ph = os.path.join(jd, "review", "phase.json")
    cur = _read(ph) or {}
    to = body.get("to")
    if to == "cut":
        if os.path.exists(ph):
            os.remove(ph)
    elif to == "looks" and cur.get("phase") == "render":
        ve._atomic_json(ph, dict(cur, phase="looks"))
    # already there: nothing to move, nothing to refuse
    return {"phase": to}


def _rendering(jd):
    """True while this server is really running a job for that reel."""
    with _guard:
        return any(os.path.realpath(ve.job_dir(j)) == os.path.realpath(jd) for j in _running)


_EXPORT_KINDS = {"finish", "trials"}                     # background jobs that ARE an export (a "lean" cut update is not)


def _running_kind(jd):
    """The kind of job this server is running for that reel right now ("lean", "finish", "trials"), or "" for none."""
    with _guard:
        return next((_bg_kind.get(j) or "lean" for j in _running if os.path.realpath(ve.job_dir(j)) == os.path.realpath(jd)), "")


_HOLD_WHILE_EXPORTING = {"/swap", "/nudge", "/refine-apply", "/behind", "/captions-redraw", "/lines", "/look-restore", "/sandbox-keep",
                         "/place-media", "/cutaway", "/trials-export", "/retime", "/grade", "/reel-pack", "/accents", "/sound-swap", "/sound-toggle", "/sound-music",
                         "/sound-add", "/sound-remove", "/sound-nudge", "/sound-switch", "/sound-defaults", "/save", "/looks-ready"}


def _claim_age(rv):
    try:
        return round(time.time() - float((_read(os.path.join(rv, "claude-working.json")) or {}).get("at") or time.time()))
    except (TypeError, ValueError):
        return 0


def _finish_status(jd):
    """The Finish step for the page: how the last render went, and whether her looks changed since."""
    try:
        import finish
        st = finish.status(jd)
        owner = st.get("owner")                                     # a "render" typed in the chat runs in its own process:
        if st.get("state") == "running" and not _rendering(jd) and (not owner or int(owner) == os.getpid() or not ve._alive(owner)):   # never ours to end
            finish.end_orphan(jd)                                     # and the render it started goes with it
            st = finish._save(jd, state="stopped", blocked=None, child=None,
                              message="That export was interrupted, so nothing changed. Press Export to start it again.")
        if st:
            st["stale"] = st.get("made_for") != finish.fingerprint(jd)
            d = (st.get("result") or {}).get("draft")
            if d:                                                     # the real next number (recycled ones counted), for the page
                try:
                    import draft_safety
                    st["next_version"] = draft_safety.next_version(draft_safety.base_of(d))
                except Exception:
                    pass
        return st or None
    except Exception:
        return None


def start_trials_export(job, body):
    """Export all her prepared trials from the page (no Claude needed), one at a time, never beside another render."""
    import finish
    jd = ve.job_dir(job)
    route = body.get("route") or "mp4"
    if route in ("resolve", "edits"):
        route = "mp4"                                  # a trial reel is a postable file, not a Resolve timeline or an Edits app project
    if route not in finish.ROUTES:
        raise ValueError
    with _guard:
        if _running:
            raise ve.Refuse("Another export is running. Start the trials when it's done.")
    only = [str(x).lower() for x in (body.get("only") or [])][:6] or None
    run_in_background(job, "trials", lambda: ve.trials_export(job, to=route, only=only, log=lambda *a: None))
    return {"started": True, "route": route}


def _trials_running_for(job):
    """The reel whose trials are exporting right now, when `job` is one of those trials (or that reel)."""
    of = (ve.trial_of(job) or {}).get("of") or job
    st = ve._trials_export_state(ve.job_dir(of)) if _job(of) else {}
    return of if st.get("state") == "running" and ve._alive(int(st.get("pid") or 0)) else None


def start_finish(job, body):
    """Render from the page: her looks locked in, her notes handled, then CapCut or an MP4 (product/finish.py)."""
    import finish
    jd = ve.job_dir(job)
    if _trials_running_for(job):
        raise ve.Refuse("Your trial reels are exporting. Export this when they're done (one render at a time).")
    route = body.get("route")
    if route not in finish.ROUTES:
        raise ValueError
    # Export means export: her press is her call. A cut she hadn't locked in is locked in now; notes still open are
    # said in one line (the export is what her page shows right now) and never stop it
    ph = os.path.join(jd, "review", "phase.json")
    cur = _read(ph) or {}
    if cur.get("phase") not in ("looks", "render"):
        ve._atomic_json(ph, {"phase": "render", "cut_locked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "looks_locked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "cut_id": ve._cut_id(jd)})
    waiting = [n for n in (_read(os.path.join(jd, "transcript", "script-notes.json")) or {}).get("notes", []) if n.get("status") != "fixed"]
    said = (f"Exporting what your page shows now: your {len(waiting)} open note{'s' if len(waiting) > 1 else ''} "
            f"{'aren' if len(waiting) > 1 else 'isn'}'t in it yet.") if waiting else None

    def go():
        try:
            finish.run(job, route, log=lambda *a: None, clear_stop=False)
        except finish.Stopped:
            return
        except finish.Busy as e:                              # another export of this reel is running: leave its state be
            raise ve.Refuse(str(e))
        except finish.Refuse as e:
            finish._save(jd, state="failed", message=str(e))
            raise ve.Refuse(str(e))
        except Exception:
            finish._save(jd, state="failed", message="Something went wrong rendering. Your looks are safe. Tell me in the chat and I'll take it from there.")
            raise
    with _guard:
        if job in _running or ve.making_now(jd):
            raise Busy()
    try:                                                     # a stop left from an earlier render never ends this one
        os.remove(finish._stop_path(jd))
    except OSError:
        pass
    run_in_background(job, "finish", go)
    return {"started": True, "route": route, **({"said": said} if said else {})}


def looks_ready(job, body):
    """"My looks are ready": phase 2 done. The render itself is phase 3, run from the chat ("render")."""
    jd = ve.job_dir(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if body.get("id") != script["id"]:
        raise ve.Refuse("This page is from before the transcript changed. Reload the page first.")
    ph = os.path.join(jd, "review", "phase.json")
    cur = _read(ph) or {}
    # Lock in my looks locks in her cut too when it wasn't yet: her press is the answer to both
    ve._atomic_json(ph, dict(cur, phase="render", looks_locked_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                             **({} if cur.get("phase") in ("looks", "render") else {"cut_locked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "cut_id": ve._cut_id(jd)})))
    return {"locked": True}


def save_accents(job, body):
    """Her accent choices, word by word: the words she turned the pack's accent ON or OFF, against the engine's
    own picks. Tied to transcript words (they survive later cuts), with each word's place in the cut for the build."""
    jd = ve.job_dir(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if body.get("id") != script["id"]:
        raise ve.Refuse("This page is from before the transcript changed. Reload the page first.")
    ve.reopen_looks(jd)                              # a highlight is a change to her looks: unlocks them
    n = len(script.get("words", []))
    items = []
    for x in (body.get("items") or [])[:5000]:
        try:
            i, t, on = int(x["i"]), round(float(x["t"]), 3), bool(x["on"])
        except Exception:
            continue
        if 0 <= i < n and 0 <= t < 36000:
            items.append({"i": i, "text": str(x.get("text", ""))[:60], "t": t, "on": on})
    out = {"job": script["job"], "id": script["id"], "items": sorted(items, key=lambda x: x["t"]),
           "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    ve._atomic_json(os.path.join(jd, "transcript", "accents.json"), out)
    return {"saved": len(items)}


def save_notes(job, body):
    """Her notes on lines ("this word sounds clipped"). The page sends every note it shows; Claude's fixes (status,
    reply) are kept unless she rewrites the note, which opens it again. A note she deletes goes."""
    jd = ve.job_dir(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if body.get("id") != script["id"]:
        raise ve.Refuse("This page is from before the transcript changed. Reload the page first.")
    path = os.path.join(jd, "transcript", "script-notes.json")
    old = {n["id"]: n for n in (_read(path) or {}).get("notes", [])}
    n_words, out = len(script["words"]), []
    for n in (body.get("notes") or [])[:60]:
        nid, w, text = str(n.get("id", ""))[:24], n.get("w"), str(n.get("text", "")).strip()[:500]
        if not re.match(r"^[A-Za-z0-9_-]+$", nid) or not isinstance(w, int) or not 0 <= w < n_words or not text:
            continue
        prev = old.get(nid)
        keep = prev and prev.get("text") == text
        layer = str(n.get("layer") or (prev or {}).get("layer") or "")[:80]   # a note left on a look stays with that look
        # Stamp the WORD she tapped (its text), kept for the note's life. If the cut later re-indexes, notes() heals
        # the stale index back to this word instead of dropping it on a line-start (#2, index drift).
        wt = (prev.get("wt") if prev and prev.get("wt") else None) or str(script["words"][w].get("t", ""))
        out.append({"id": nid, "w": w, "wt": wt, "text": text, "status": prev.get("status", "open") if keep else "open",
                    "reply": prev.get("reply", "") if keep else "", "at": prev.get("at") if prev else time.strftime("%Y-%m-%d %H:%M:%S"),
                    **({"layer": layer} if re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$", layer) else {})})
    ve._atomic_json(path, {"notes": out})
    return out


def _looks_v(jd):
    """{layer: its page file's time (ms)} for every look on her reel, read fresh each beat (a few stats): a look page
    written again after the list (a caption redraw with new skips) is a new version her page reloads by itself."""
    try:
        layers = (_read(os.path.join(jd, "review", "looks.json")) or {}).get("layers") or []
    except Exception:
        return {}
    out = {}
    for L in layers:
        try:
            out[L["name"]] = int(os.stat(os.path.join(jd, L["dir"], "index.html")).st_mtime_ns // 1_000_000)
        except (OSError, KeyError, TypeError):
            pass
    return out


def _queue(job):
    try:
        return ve.task_queue(job)
    except Exception:                               # a status beat never fails over the queue
        return None


def save(job, body):
    """Check her edits against this reel, word by word, then write them where `apply` reads them."""
    jd = ve.job_dir(job)
    script = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
    if body.get("job") != os.path.basename(jd):
        raise ve.Refuse("These edits are for a different reel.")
    if body.get("id") != script["id"]:
        raise ve.Refuse("This page is from before the transcript changed. Reload the page to get the current "
                        "script; your edits there will be kept where they still fit.")
    if body.get("cut_id") and script.get("cut_id") and body["cut_id"] != script["cut_id"]:
        # Claude changed her cut (a note fixed, a restitch) after this page loaded: a Send from the old page would
        # write the old cut back over it (a buyer, 2026-10-23). Her page loads the new cut, keeps only what she
        # hasn't sent yet on top of it, and she presses Send again.
        raise Stale("Your cut was just updated, so your page is loading it now. Your unsent changes stay on top "
                    "of it: press Send my cut again.")
    n = len(script["words"])
    cut = sorted({int(i) for i in body.get("cut", [])})
    back = sorted({int(i) for i in body.get("back", [])})
    if any(not 0 <= i < n for i in cut + back):
        raise ve.Refuse("Some of these edits point past the end of the transcript.")
    kept = [w["k"] for w in script["words"]]
    cut = [i for i in cut if kept[i]]            # "cut" only means anything for a word the engine kept,
    back = [i for i in back if not kept[i]]      # "bring back" only for a word it cut
    trims = {"s": {}, "e": {}}
    for side in ("s", "e"):
        for k, v in ((body.get("trims") or {}).get(side) or {}).items():
            try:
                w, t = int(k), float(v)
            except (TypeError, ValueError):
                continue
            if 0 <= w < n and 0 <= t < 36000 and len(trims[side]) < 2000:
                trims[side][str(w)] = round(t, 3)
    holes = []                                      # stretches she cut by time (a split anywhere, then a side deleted)
    for h in (body.get("holes") or [])[:2000]:
        try:
            c, a, b = int(h["c"]), float(h["s"]), float(h["e"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= c < len(script.get("clips") or []) and 0 <= a < b < 36000:
            holes.append({"c": c, "s": round(a, 3), "e": round(b, 3)})
    fx = {str(w): e for w, e in ve.fx_of(body).items() if w < n}   # a clip's Speed and Zoom, checked (ve.fx_of)
    payload = {"job": script["job"], "id": script["id"], "cut_id": script.get("cut_id"), "cut": cut, "back": back,
               "trims": trims, **({"holes": holes} if holes else {}), **({"fx": fx} if fx else {}),
               "length": str(body.get("length", ""))[:12], "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    payload["receipt"] = ve.receipt(payload)
    ve._atomic_json(os.path.join(jd, "transcript", "script-review.json"), payload)
    ph = os.path.join(jd, "review", "phase.json")
    if ve.edits_in(payload) and os.path.exists(ph):
        os.remove(ph)                               # she changed the cut again: phase 1 is open until she says ready
    return {"receipt": payload["receipt"], "cut": len(cut), "back": len(back), "trims": len(trims["s"]) + len(trims["e"]),
            "at": round(time.time(), 3)}             # her page waits for THIS receipt to land (last_applied, in /status)


DEFAULT_PORT = 47815


def _bind():
    """The SAME address every time (her browser keeps her unsent edits per address): the one asked for, else the
    last one used, else the engine's usual port; a random free one only if all of those are taken."""
    tries = []
    if os.environ.get("VISUAL_EDITOR_PORT"):
        tries.append(int(os.environ["VISUAL_EDITOR_PORT"]))
    last = _read(STATE)
    if last and last.get("port"):
        tries.append(int(last["port"]))
    tries += [DEFAULT_PORT, 0]
    for port in tries:
        try:
            return http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError:
            continue
    raise SystemExit("no free port")


def _owns_state():
    """True unless the state file names a DIFFERENT editor server that is alive and answering: then that one is the
    address her open page uses, and a second server (an old one restarting itself, a session's leftover) must not
    hijack the state file and send the next 'open my editor' somewhere else (2026-10-17)."""
    try:
        st = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return True
    if int(st.get("pid") or 0) == os.getpid():
        return True
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{int(st['port'])}/ping", timeout=1.5) as r:
            return r.status != 200
    except Exception:
        return True


def main():
    import early_access
    early_access.refuse_if_off()
    srv = _bind()
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    if _owns_state():                                        # another live editor server already holds the address her
        ve._atomic_json(STATE, {"port": srv.server_address[1], "pid": os.getpid()})   # page uses: never point it elsewhere

    def watchdog():
        while time.time() - _last[0] < IDLE_SECONDS or _running:      # never idle out in the middle of a render
            time.sleep(30)
        srv.shutdown()

    def leave_state():
        try:
            if json.load(open(STATE, encoding="utf-8")).get("pid") == os.getpid():
                os.remove(STATE)
        except Exception:
            pass

    def closing(signum, frame):                              # told to close: end the render it started, then go
        _end_renders()
        leave_state()
        os._exit(0)

    import signal
    for name in ("SIGTERM", "SIGHUP", "SIGINT"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), closing)
            except (ValueError, OSError):
                pass
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=_restart_when_updated, args=(srv,), daemon=True).start()
    try:
        srv.serve_forever()
    finally:
        _end_renders()
        leave_state()


def _code_stamp():
    out = []
    for f in ve.CODE_FILES:
        try:
            out.append(os.path.getmtime(os.path.join(ROOT, f)))
        except OSError:
            out.append(None)
    return out


def _restart_when_updated(srv):
    """The engine changed under a running editor (an update, a fix): start again on the new code by itself, so the
    page never draws a look with yesterday's engine. Waits while anything is running; her page reconnects on its own."""
    first = _code_stamp()
    while True:
        time.sleep(3)
        if _code_stamp() == first:
            continue
        time.sleep(2)                                        # let the update finish writing every file
        with _guard:
            busy = bool(_running) or _inflight[0] > 0
        if busy:
            continue
        os.environ["VISUAL_EDITOR_PORT"] = str(srv.server_address[1])   # come back on THIS address: her open page keeps
        try:                                                 # calling it (reading the shared state file could hand back
            srv.server_close()                               # another server's port, and her page lost the engine)
        except Exception:
            pass
        if os.name == "nt":                                  # Windows' execv doesn't quote: a space in a path ("Jane Doe",
            subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:],   # "OneDrive - Company") broke the
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            os._exit(0)                                      # restart; a fresh process takes over the same port
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])


def _end_renders():
    """The editor is closing: a render it started ends with it (its processes run in their own session, so they
    would otherwise keep going and write files with nobody watching). Saved as interrupted, so the page says so."""
    try:
        import finish
        with _guard:
            jobs = list(_running)
        for j in jobs:
            jd = ve.job_dir(j)
            if finish.status(jd).get("state") == "running":
                finish.end_orphan(jd)
                finish._save(jd, state="stopped", blocked=None, child=None,
                             message="That export was interrupted, so nothing changed. Press Export to start it again.")
    except Exception:
        pass


if __name__ == "__main__":
    # Everything this server draws runs on its own Python, so it has to be one with Pillow: started by Apple's 3.9
    # (first on PATH beside the Command Line Tools), every Lookbook look failed on "No module named 'PIL'".
    import graphics_python
    graphics_python.reexec_if_needed()
    for _s in (sys.stdout, sys.stderr):     # a PC console that is not UTF-8 would choke on the status symbols
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    main()
