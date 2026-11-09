#!/usr/bin/env python3
"""finish.py — the Finish step, run from the visual editor: her locked looks rendered and handed over.

Three ways out, the same renders behind each:
  * capcut  every look rendered once (the engine's own checked renderer), then her CapCut draft built with
            product/capcut_handoff.py: her cut on the main track, each look on its own named track at its own
            time, each sound cue its own clip. A new version every time (1.1 → 1.2), never over one she opened.
  * mp4     the same renders burned into her full-quality cut (product/burn_layers.py), at the footage's own
            size: outputs/<job>.final.mp4, plus a small phone copy to check it like a viewer would.
  * resolve a whole DaVinci Resolve kit (product/resolve_export.py writes outputs/<job> resolve/): her cut one
            clip per kept line, each look its own track, each sound its own clip, her music bed, her voice alone
            on its own track. Two ways in: a one-click Workspace > Scripts build (.lua) or a hand-imported FCPXML
            (overlay = her rendered captions; native = real captions from the .srt). Her Filter and covered faces
            are baked into the cut. No Resolve and no DaVinci scripting needed to produce the kit.

What it renders is exactly what the page plays: review/looks.json (her swaps, adds, moves and removals included).
Each look goes through `reel_render.py render`, so `hyperframes check`, the off-frame text check and the
"never over her face" check all run, and renders are cached by content (an unchanged look is not rendered again).
Never two renders at once. Nothing here changes quality: same renderer, same settings, same checks as the chat.

Progress for the page lives in review/finish.json: {state, step, progress, done, of, route, result, made_for, message}.
`progress` (0..1) weighs every step this export runs by its rough cost and moves inside each one (_Bar); it reaches
1 only when the export is done. done/of still count the look renders, for anything that read them before.
`made_for` is a fingerprint of her looks, so the page can say "your looks changed since this render".

    python3 product/finish.py run <job> capcut|mp4|resolve
    python3 product/finish.py status <job>
"""
import hashlib, json, math, os, re, shutil, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import export_progress
ROUTES = ("capcut", "mp4", "resolve", "edits")
_LOCK = threading.RLock()                                     # the bar's ticker and the export both write finish.json
_HERE = threading.local()                                     # this export's progress file, for the children it starts


class Refuse(Exception):
    """A plain-words reason the finish can't run right now (what to do is in the words)."""



def _trim_to(path, dur):
    """A look plays exactly as long as her page plays it: the manifest can end a look early (the next word look
    starts there, so two caption styles never share a frame), while its page was drawn longer. Trimmed in place,
    stream copy, only when it really runs long."""
    try:
        if dur <= 0 or not os.path.isfile(path):
            return
        got = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                   capture_output=True, text=True).stdout.strip() or 0)
        if got - dur < 0.04:
            return
        tmp = path + ".trim" + os.path.splitext(path)[1]
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-t", f"{dur:.3f}", "-c", "copy", tmp])
        if r.returncode == 0 and os.path.isfile(tmp):
            os.replace(tmp, path)
    except Exception:
        pass                                                  # never stops an export: the look plays its full length


def _probe_dur(path):
    try:
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                    capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        return 0.0


def _looks_doc(jd):
    """Her looks list. A reel with no looks at all (a short one, or every look removed) has none on disk: it still
    exports, as her cut with its sounds."""
    try:
        return json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))
    except FileNotFoundError:
        return {"layers": []}

def _ve():
    import visual_editor
    return visual_editor


def _path(jd):
    return os.path.join(jd, "review", "finish.json")


def status(jd):
    try:
        return json.load(open(_path(jd), encoding="utf-8"))
    except Exception:
        return {}


def _save(jd, **kv):
    with _LOCK:
        d = dict(status(jd), **kv, at=time.strftime("%Y-%m-%d %H:%M:%S"))
        if d.get("state") == "done":
            d["progress"] = 1.0
        p = _path(jd)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        _ve()._atomic_json(p, d)                              # a unique temp file + retry: the page reading it never fails a save
        return d


def _sub_path(jd):
    return os.path.join(jd, "review", "finish-progress.json")


def _render_frames(pid):
    """How far a look render is (reel_render.py's own log, named by its pid), 0..1, or 0 when it hasn't said."""
    import glob
    for f in sorted(glob.glob(os.path.join(ROOT, "_local", "render-log", f"*-{pid}-*.json")), reverse=True):
        try:
            d = json.load(open(f, encoding="utf-8"))
            if d.get("frames_total"):
                return min(1.0, float(d.get("frames_done") or 0) / float(d["frames_total"]))
        except Exception:
            pass
    return 0.0


class _Bar:
    """The Finish tab's bar: every step this export runs, each weighted by its rough cost (export_progress.*_cost),
    moving inside a step with what the step says of itself (an encode's out_time, a render's frames, a builder's
    stretches), else a slow creep by its expected time so a long step never sits frozen. It never goes back and holds
    under 100% until the export is done (2026-10-23: "100% should only happen when truly done")."""
    TICK = 1.0

    def __init__(self, jd, steps):
        self.jd, self.steps = jd, [(k, max(1.0, float(c))) for k, c in steps]
        self.total = sum(c for _k, c in self.steps) or 1.0
        self.best, self.key, self.t0, self.child0, self.label = 0.0, None, time.time(), None, None
        self._stop, self._th = threading.Event(), None

    def _base(self, key):
        before = 0.0
        for k, c in self.steps:
            if k == key:
                return before, c
            before += c
        return None, None

    def _put(self, v, **kv):
        with _LOCK:
            if status(self.jd).get("state") not in (None, "running"):
                return                                        # done, stopped or failed: the bar is the export's to set
            v = min(0.99, max(self.best, v))
            if v - self.best >= 0.002 or kv:
                self.best = v
                _save(self.jd, progress=round(v, 4), **kv)

    def go(self, key, **kv):
        """A step starts (kv: its label and anything else finish.json carries)."""
        export_progress.reset(_sub_path(self.jd))
        self.key, self.t0, self.child0 = key, time.time(), status(self.jd).get("child")
        self.label = kv.get("step") or self.label
        b, _c = self._base(key)
        self._put(b / self.total if b is not None else self.best, **kv)

    def inner(self):
        """(how far through the current step, 0..1; the child's own label or None)."""
        got, label = export_progress.read(_sub_path(self.jd))
        f = got or 0.0
        child = status(self.jd).get("child")
        if child and child != self.child0:
            f = max(f, _render_frames(child))
        if f <= 0:
            _b, c = self._base(self.key)
            f = 0.9 * (1 - math.exp(-(time.time() - self.t0) / max(5.0, c or 5.0)))
        return min(1.0, f), label

    def tick(self):
        if not self.key:
            return
        b, c = self._base(self.key)
        if b is None:
            return
        f, label = self.inner()
        kv = {}
        if label and self.label and status(self.jd).get("step") != f"{self.label}: {label}":
            kv["step"] = f"{self.label}: {label}"
        self._put((b + c * f) / self.total, **kv)

    def _loop(self):
        while not self._stop.wait(self.TICK):
            try:
                self.tick()
            except Exception:
                pass                                          # the bar is a courtesy: it never stops an export

    def __enter__(self):
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()
        return self

    def close(self):
        self._stop.set()
        if self._th and self._th is not threading.current_thread():
            self._th.join(5)

    def __exit__(self, *a):
        self.close()


def fingerprint(jd):
    """Her looks as they'll render: which layers, where, from which drawing. Changes when any look changes."""
    try:
        looks = _looks_doc(jd)
    except Exception:
        return None
    sig = [(L.get("name"), L.get("dir"), round(float(L.get("offset") or 0), 3), L.get("dur"), bool(L.get("off")), L.get("nudge"))
           for L in looks.get("layers", [])]
    extra = ""
    extra += str(_ve()._cut_id(jd) or "")                      # a cut change makes an older export out of date too
    for f in ("review/swaps.json", "review/sound.json", "review/grade.json", "transcript/accents.json",
              "review/face-cover.json"):
        p = os.path.join(jd, f)
        if os.path.isfile(p):
            extra += hashlib.sha256(open(p, "rb").read()).hexdigest()
    import glob as _g                                       # her pictures: a new entrance or file redraws them in place
    for p in sorted(_g.glob(os.path.join(jd, "hf-graphics", "_looks", "*", "media.json"))):
        extra += hashlib.sha256(open(p, "rb").read()).hexdigest()
    return hashlib.sha256((json.dumps(sig, sort_keys=True) + extra).encode()).hexdigest()[:16]


def plan(jd):
    """The layers to render, in stacking order (her b-roll cutaways first, right on her footage, so every card and her
    captions play over them; her captions last, on top): [(name, composition dir, start)]."""
    looks = _looks_doc(jd)
    out = []
    for L in sorted(looks.get("layers", []), key=lambda L: (bool(L.get("captions")), "cutaway" not in L, float(L.get("offset") or 0))):
        if L.get("off") or not L.get("dir"):
            continue
        comp = os.path.join(jd, L["dir"])
        if os.path.isfile(os.path.join(comp, "index.html")):
            out.append((L["name"], comp, round(float(L.get("offset") or 0), 3)))
    return out


class Stopped(Refuse):
    """She pressed stop on the page: the render ends, nothing of hers changes."""


class Busy(Refuse):
    """An export of this reel is already running: the second one says so and leaves the running one's finish.json
    (its state, its bar, her page) exactly as it is."""


def _stop_path(jd):
    return os.path.join(jd, "review", "finish.stop")


def stop(job, starting=False):
    """Her stop button: the render in progress ends at once (a CapCut draft being written is let finish, so a draft
    is never left half-built). True when there was a render to stop."""
    jd = _ve().job_dir(job)
    st = status(jd)
    if st.get("state") != "running" and not starting:
        return False
    if str(st.get("step", "")).startswith("Building your CapCut draft"):
        raise Refuse("Your CapCut draft is being written right now. It's seconds from done, so it can't be stopped.")
    open(_stop_path(jd), "w", encoding="utf-8").write(time.strftime("%Y-%m-%d %H:%M:%S"))
    return True


class _Awake:
    """Keeps her computer from sleeping while a render runs (she walks away; it finishes). Mac: caffeinate, tied to
    this process so it can never outlive it. Windows: the system's own keep-awake flag for this thread. Elsewhere,
    or if either is missing: nothing, and the render runs as before."""
    def __enter__(self):
        self.p = None
        try:
            if sys.platform == "darwin" and shutil.which("caffeinate"):
                self.p = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM_REQUIRED
        except Exception:
            pass
        return self

    def __exit__(self, *a):
        try:
            if self.p:
                self.p.terminate()
            elif os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass


def end_orphan(jd):
    """The editor restarted mid-render: its render processes kept going in their own session. End them, so the next
    render never runs beside an old one that can still write files. True when there was one to end."""
    pid = status(jd).get("child")
    if not pid:
        return False
    try:                                                     # only ever one of the engine's own render steps
        if os.name == "nt":
            q = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        else:                                                # -ww: the whole line, never cut at a terminal's width
            q = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(int(pid))], capture_output=True, text=True).stdout
        if not re.search(r"reel_render|burn_layers|capcut_handoff|hyperframes|ffmpeg", q or ""):
            return False
    except Exception:
        return False
    try:
        if os.name == "nt":
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            return r.returncode == 0
        os.killpg(int(pid), 9)
        return True
    except Exception:
        return False


def _hair_only(jd):
    """A close-up with no room above your head, where the hook still fits above her FACE (the builder caps it there):
    the only overlap is her hair. True only then; anything nearer her face is never waved through."""
    try:
        z = json.load(open(os.path.join(jd, "subject-zones.json"), encoding="utf-8"))
        s, r = z.get("subject") or {}, z.get("subject_src_px") or {}
        k = (float(s["chin_bottom"]) - float(s["head_top"])) / max(1.0, float(r["chin_bottom"]) - float(r["head_top"]))
        face = float(s["head_top"]) + (float(r["face_top"]) - float(r["head_top"])) * k
        return face - 10 - 280 >= 110
    except Exception:
        return False


def _no_room_above(jd):
    try:
        z = json.load(open(os.path.join(jd, "subject-zones.json"), encoding="utf-8"))
        return not ((z.get("zones") or {}).get("above") or {}).get("usable", True)
    except Exception:
        return False


def _learned(field):
    try:
        import learned
        return bool(learned.value(field, False))
    except Exception:
        return False


def _stopped(jd):
    return os.path.exists(_stop_path(jd))


def _kill(p):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            os.killpg(p.pid, 9)                               # the renderer and the browser it started
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _run(cmd, jd, what, stoppable=True, env=None):
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    sub = getattr(_HERE, "sub", None)                         # the bar follows the child (export_progress)
    import frame
    env = dict(frame.env(jd), **(env or {}))                  # a wide video's tools draw and measure on the wide frame
    if env or sub:
        kw["env"] = dict(os.environ, **env, **({export_progress.ENV: sub} if sub else {}))
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kw)
    _save(jd, child=p.pid)                                  # so an editor restart can end it (end_orphan), never run two
    while True:
        try:
            out, err = p.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if stoppable and _stopped(jd):
                _kill(p); p.communicate()
                raise Stopped("You stopped the export. Nothing changed; press Export whenever you're ready.")
    r = subprocess.CompletedProcess(cmd, p.returncode, out, err)
    if r.returncode != 0:
        tail = [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip()]
        why = next((l for l in reversed(tail) if "⛔" in l or "CapCut" in l or "engine" in l.lower()), tail[-1] if tail else "it stopped")
        raise Refuse(f"{what} stopped: {why.lstrip('⛔ ').strip()}")
    return r.stdout


def _refresh_stale(job, jd):
    """A look drawn before the engine's builder last improved is drawn again on the same words, the way the page
    draws it, so what renders is current (an old drawing can fail today's render check). Her locked-in state stays
    exactly as it was: redrawing is not a change she made."""
    ve = _ve()
    import lookbook
    ph = os.path.join(jd, "review", "phase.json")
    keep = open(ph, encoding="utf-8").read() if os.path.isfile(ph) else None
    try:
        looks = _looks_doc(jd)
        pack = ve._swap_pack(jd, looks)[0]
        special = (None, "_original", "_off")
        for key, e in ve._adds(jd).items():
            d = e.get("dir") or ""
            if e.get("look") in special or e.get("look") == "media" or "/refined-" in d:   # her picture: drawn from its file
                continue
            l = lookbook.find(e["look"], pack)
            if ve._stale_look(os.path.join(jd, d), lookbook.design_dir(l.get("home") or pack, l["id"]) if l.get("design") else None):
                s0, e0 = e.get("span") or (float(e["offset"]) + 0.12, float(e["offset"]) + float(e["dur"]) - 0.35)
                ve.place_look(job, key, s0, max(s0 + 0.3, e0), e["look"])
        for layer, e in ve._swaps(jd).items():
            d = e.get("dir") or ""
            if e.get("look") in special or "/refined-" in d:
                continue
            if ve._stale_look(os.path.join(jd, d)):
                try:                                  # drawn again from its own record: her words, size, animation and
                    rec = json.load(open(os.path.join(jd, d, "look.json"), encoding="utf-8"))   # highlights stay hers
                    cid = re.search(r'data-composition-id="([^"]+)"', open(os.path.join(jd, d, "index.html"), encoding="utf-8").read())
                except Exception:
                    rec, cid = None, None
                if rec and rec.get("look") and cid:
                    zp = os.path.join(jd, "subject-zones.json")
                    zones = json.load(open(zp, encoding="utf-8")) if os.path.isfile(zp) else None
                    lookbook.draw(rec["look"], os.path.dirname(os.path.join(jd, d)), rec.get("text") or "", float(rec.get("dur") or 1),
                                  rec.get("pack") or pack, zones, words=rec.get("words"), comp_id=cid.group(1),
                                  size=rec.get("size"), effect=rec.get("effect"), accents=rec.get("accents") and [{"w": w, "t": t} for w, t in rec["accents"]])
                else:
                    ve.swap_menu(job, layer)          # an older page with no record: that line's looks drawn again (in the
                    ve._adopt_menu(jd, layer, e.get("look"))   # menu's folder), and her look takes the fresh drawing
                if e.get("nudge"):                    # where she moved it stays where she moved it
                    ve._apply_nudge(jd, d, e["nudge"])
                # her restyled captions still step aside where a look shows her words: a drawing made fresh here has
                # none of the page's step-asides, so her captions and the look's words played together in the export
                # while the page showed one at a time (2026-10-28)
                capL = next((x for x in (_looks_doc(jd).get("layers") or [])
                             if x.get("name") == layer and x.get("captions") and x.get("skips")), None)
                if capL:
                    ve._apply_skips(jd, d, capL.get("id") or (cid.group(1) if cid else ""), capL["skips"],
                                    offset=capL.get("offset"))
    except lookbook.Refuse:
        pass                                          # a look that can't be redrawn renders as it was drawn
    finally:
        if keep is not None:                          # put her locked-in state back, written whole (never half a file)
            tmp = ph + ".tmp"
            open(tmp, "w", encoding="utf-8").write(keep); os.replace(tmp, ph)


def _vectcut_up():
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:9001/get_mask_types", timeout=3) as r:
            return b"success" in r.read()
    except Exception:
        return False


def _start_vectcut():
    """Turn the CapCut build engine on if it's off (it stops when the computer sleeps). Detached, like setup does."""
    d = os.path.join(ROOT, "product", "engine", "VectCutAPI")
    if os.name == "nt":
        bat = os.path.join(d, "start-editor.bat")
        if os.path.isfile(bat):
            subprocess.Popen(["cmd", "/c", "start", "", bat], cwd=d)
    else:
        cmd = os.path.join(d, "start-editor.command")
        if os.path.isfile(cmd):
            subprocess.Popen(["bash", cmd], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(15):
        time.sleep(2)
        if _vectcut_up():
            return True
    return False


def allowed(jd):
    """Looks she said are over her face ON PURPOSE (the engine's deliberate-overlap opt-out, per look)."""
    try:
        return set(json.load(open(os.path.join(jd, "review", "finish-allow.json"), encoding="utf-8")).get("layers", []))
    except Exception:
        return set()


def hair_ok(jd):
    """She said it's on purpose when this reel's shot had no room above your head: every look that only touches her
    hair is fine on this reel (her face still stops a render, look by look)."""
    try:
        return bool(json.load(open(os.path.join(jd, "review", "finish-allow.json"), encoding="utf-8")).get("hair_ok"))
    except Exception:
        return False


def allow(job, layer, hair=False):
    jd = _ve().job_dir(job)
    a = allowed(jd) | {layer}
    p = os.path.join(jd, "review", "finish-allow.json")
    _ve()._atomic_json(p, {"layers": sorted(a), "hair_ok": hair or hair_ok(jd)})
    return sorted(a)


def run(job, route, log=print, clear_stop=True):
    """Render her looks and hand the reel over. Writes progress to review/finish.json as it goes; a stop is saved
    there too, in plain words (and, when a look sits on her face, which look and when)."""
    jd = _ve().job_dir(job)
    os.environ["REE_EDITOR_FINISH"] = "1"   # the editor's own export: the route lock (review_route.py) lets its builders run
    # one export at a time, whoever started it (page or chat): checked before anything is written, so a second run
    # never clears the running one's stop, marks it failed or tells her page it stopped (2026-10-23)
    cur = status(jd)
    if cur.get("state") == "running" and cur.get("owner") and int(cur["owner"]) != os.getpid() and _ve()._alive(cur["owner"]):
        raise Busy("An export of this reel is already running. Let it finish, or stop it from your page, then export again.")
    try:
        if clear_stop and os.path.exists(_stop_path(jd)):
            os.remove(_stop_path(jd))
        _save(jd, owner=os.getpid())
        with _Awake():
            out = _run_finish(job, route, log)
        _tell_done(jd, out)
        try:                                                  # her route, learned for next time (autopilot reads it)
            import choices
            choices.record(jd, route=route)
        except Exception:
            pass
        return out
    except Stopped as e:
        import glob
        for f in glob.glob(os.path.join(jd, "outputs", "*.part.mp4")) + glob.glob(os.path.join(jd, "outputs", "*.tmp.mp4")):
            try:
                os.remove(f)                                  # half-written files from the step she stopped
            except OSError:
                pass
        _save(jd, state="stopped", message=str(e), blocked=None)
        raise
    except Refuse as e:
        _save(jd, state="failed", message=str(e))
        _tell(jd, "Your export stopped before it finished. Your Finish tab says why.")
        raise


def _tell(jd, text):
    """Her page pops it (a long export: she is often in another tab by the end)."""
    import editor_says
    editor_says.told(jd, text, kind="finish", go="finish", group="finish")


def _tell_done(jd, st):
    r = (st or {}).get("result") or {}
    if r.get("route") == "capcut":
        _tell(jd, "Your CapCut draft is ready. Your Finish tab shows the one double-click that brings it in." if r.get("staged")
              else "Your reel is in CapCut, ready to polish.")
    elif r.get("route") == "mp4":
        _tell(jd, "Your reel is exported. Watch it on your Finish tab.")
    elif r.get("route") == "resolve":
        _tell(jd, "Your DaVinci Resolve timeline is ready. Your Finish tab shows where to find the .fcpxml.")
    elif r.get("route") == "edits":
        _tell(jd, "Your Edits build is staged, going in as medium so your look holds. Claude is bringing your "
                  "cut and its looks into the Edits app now.")


def _steps(jd, route, need_cut):
    """Every step this export runs, in order, with its rough cost (export_progress): what the bar is made of."""
    cut_c, out_s, m = export_progress.cut_cost(jd)
    live = [L for L in _looks_doc(jd).get("layers", []) if not L.get("off") and L.get("dir")]
    steps = ([("cut", cut_c)] if need_cut else []) + [("check", 3.0)]
    # a caption layer rendered in stretches costs only the stretches not in the cache (render_spans.pending_share):
    # a one-word fix is a short bar, its CapCut copy too (an unchanged stretch's copy is cached as well)
    share = {}
    for L in live:
        try:
            import render_spans, reel_render
            share[L["name"]] = render_spans.pending_share(os.path.join(jd, L["dir"]), reel_render.HF_VERSION)
        except Exception:
            share[L["name"]] = None
    def _d(L):
        sh = share.get(L["name"])
        return float(L.get("dur") or 0) * (1.0 if sh is None else sh)
    steps += [(f"look:{L['name']}", export_progress.render_cost(_d(L))) for L in live]
    behind = sum(0.15 * 30 * float(L.get("dur") or 0) for L in live if L.get("behind"))
    if route == "capcut":
        steps += ([("behind", behind)] if behind else []) + [("capcut", export_progress.tail_cost(jd, out_s, m) + 15.0
                                                               + sum(export_progress.alpha_cost(_d(L)) for L in live))]
    elif route == "resolve":
        # the cut isn't re-encoded (the timeline references it); only her filter, if she has one, is baked once, and
        # a look behind her needs the same cut-out as the MP4 route
        steps += ([("copy1080", export_progress.reencode_cost(out_s)), ("behind", behind)] if behind else []) \
            + [("resolve", 0.5 * export_progress.reencode_cost(out_s) + 6.0)]
    elif route == "edits":
        # medium only: her cut + already-rendered looks are just staged (file copies) and a manifest written;
        # the edits-export skill replays it live into the Edits app
        steps += [("edits", 8.0)]
    else:
        steps += [("copy1080", export_progress.reencode_cost(out_s))] + ([("behind", behind)] if behind else []) \
            + [("burn", 1.5 * export_progress.reencode_cost(out_s) + 10.0), ("phone", 0.3 * out_s)]
    return steps


def _run_finish(job, route, log):
    if route not in ROUTES:                                   # no route named: the kit's default (Edits when on), else MP4
        import edits_mode
        route = edits_mode.default_route("mp4")
    ve = _ve()
    jd = ve.job_dir(job)
    need_cut = not os.path.isfile(os.path.join(jd, "outputs", os.path.basename(jd) + ".mp4")) or ve.base_is_stale(job)
    bar = _Bar(jd, _steps(jd, route, need_cut))
    _save(jd, state="running", route=route, progress=0.0, step="Starting", done=0, of=0, result=None, message=None,
          blocked=None, placed=None, sound_notes=None)
    _HERE.sub = _sub_path(jd)
    try:
        with bar:
            return _finish_steps(job, route, log, ve, jd, bar, need_cut)
    finally:
        _HERE.sub = None
        export_progress.reset(_sub_path(jd))


def _finish_steps(job, route, log, ve, jd, bar, need_cut):
    name = os.path.basename(jd)
    base = os.path.join(jd, "outputs", name + ".mp4")
    if need_cut:
        # the one render: her cut is made here, exactly as she set it on her page, along with everything on top
        bar.go("cut", state="running", route=route, step="Making your full-quality cut", done=0, of=0, result=None,
               message=None, blocked=None, placed=None, sound_notes=None)
        was = os.environ.get(export_progress.ENV)
        os.environ[export_progress.ENV] = _sub_path(jd)       # the stitch runs in this process: its encode says how far
        try:
            ve.finish_cut(job, log=lambda *a: None, exact=True, stoppable=True)   # her Stop ends this step too
        except ve.Stopped as e:
            raise Stopped(str(e))
        except ve.Refuse as e:
            raise Refuse(str(e))
        finally:
            if was is None:
                os.environ.pop(export_progress.ENV, None)
            else:
                os.environ[export_progress.ENV] = was
    bar.go("check", state="running", route=route, step="Checking your looks are current", done=0, of=0, result=None,
           message=None, blocked=None, placed=None, notice=None, sound_notes=None)
    # the final pass: her cut changed after her looks were made (a word cut, a line trimmed). Her added looks, her
    # lookbook captions and the sounds she added follow her words now; anything only Claude can redo stops here.
    if (ve.looks_cut(jd) and ve._cut_id(jd) and ve.looks_cut(jd) != ve._cut_id(jd)) or ve.drifted_adds(jd):
        _save(jd, step="Matching your looks to your latest cut")
        php = os.path.join(jd, "review", "phase.json")
        kept_phase = open(php, encoding="utf-8").read() if os.path.isfile(php) else None
        with ve.patient(600):                                # a retime already under way elsewhere is waited out, never "busy"
            ve.retime_adds(job)
        if kept_phase is not None:                           # the export moving her looks onto their words isn't her changing
            open(php, "w", encoding="utf-8").write(kept_phase)   # them: her layers stay locked in as she left them
    redo = ve.looks_to_redo(jd)
    if redo:
        def _named(n):                                        # which look, in her words: "your Hook at 0:00"
            L = next((l for l in _looks_doc(jd).get("layers", []) if l["name"] == n), {})
            rec = ve._orig_record(jd, L) if L else None
            what = "captions" if L.get("captions") else (L.get("look_name") or ((rec or {}).get("look") or "look").replace("-", " ").capitalize())
            at = float(L.get("offset") or 0)
            return f"your {what} at {int(at // 60)}:{int(at % 60):02d}"
        names = [_named(n) for n in redo]
        said = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        # her Export is her call: those looks go out where they sat on her page, said once (never a stop)
        _save(jd, notice=f"{said[0].upper() + said[1:]} {'was' if len(names) == 1 else 'were'} made for your earlier cut and "
                         f"{'is' if len(names) == 1 else 'are'} exported where {'it sat' if len(names) == 1 else 'they sat'}. "
                         "Say update my edit in the chat for a fresh pass.")
    try:
        behind = [L["name"] for L in _looks_doc(jd).get("layers", [])
                  if L.get("behind") and not L.get("off")]
    except Exception:
        behind = []
    behind = set(behind)                                      # behind her: rendered as usual, her cutout laid over it below
    _refresh_stale(job, jd)
    layers = plan(jd)
    fp = fingerprint(jd)
    _save(jd, state="running", route=route, done=0, of=len(layers), result=None,
          message=None, blocked=None, placed=None, made_for=fp)
    rendered, ok_over = [], allowed(jd)
    out_dir = os.path.join(jd, "hf-graphics", "finish")
    os.makedirs(out_dir, exist_ok=True)
    _ll = _looks_doc(jd).get("layers", [])
    caps = {L["name"] for L in _ll if L.get("captions")}
    durs = {L["name"]: float(L.get("dur") or 0) for L in _ll}
    order = sorted(range(len(layers)), key=lambda i: (layers[i][0] in caps, durs.get(layers[i][0], 0)))   # quick ones first
    done_by, on_her, left_out = {}, [], []                    # looks that sit on her (said once); looks left out
    for k, i in enumerate(order, 1):
        lname, comp, start = layers[i]
        if _stopped(jd):
            raise Stopped("You stopped the export. Nothing changed; press Export whenever you're ready.")
        # captions run the whole reel, so they take the longest: the page says so, so a long wait never looks stuck
        bar.go(f"look:{lname}", step=f"Rendering {'your captions' if lname in caps else f'look {k} of {len(layers)}'}", done=k - 1,
               slow=lname in caps)
        cut = ve.cutaway_file(jd, os.path.relpath(comp, jd))
        if cut:                                               # her b-roll: already the exact frames it plays, her footage
            mov = os.path.join(out_dir, f"{lname}.mp4")       # pixel for pixel, so it goes in as footage, not a render
            _cutaway_out(jd, cut, mov, ve.grade_of(jd))
            done_by[i] = (lname, mov, start)
            continue
        mov = os.path.join(out_dir, f"{lname}.mov")
        cmd = [sys.executable, os.path.join(HERE, "reel_render.py"), "render", comp, "-o", mov]
        if lname in ok_over or lname in behind:
            cmd.append("--no-subject")                # over her face on purpose, or behind her (her cutout covers it)
        try:
            try:
                said = _run(cmd, jd, f"Rendering {lname}") or ""
                if "sits on her face" in said or "sits on her" in said:   # rendered as placed: named after, never a stop
                    on_her.append({"layer": lname, "t": round(start, 2)})
            except Refuse as e:
                if "OPAQUE" not in str(e).upper() and "frames/%05d.png" not in str(e):
                    raise
                # a full-frame designed card (a breakaway) has its own ground: the renderer's rule is to render it
                # as a solid clip, not a see-through overlay. Same look, same checks.
                mov = os.path.join(out_dir, f"{lname}.mp4")
                cmd[cmd.index("-o") + 1] = mov
                _run(cmd, jd, f"Rendering {lname}")
        except Refuse as e:
            import re
            # Her placement is her call: the export renders what she set and says so after, never stops on it.
            # (The page flags these as maybes before she exports; a look on her or text past the edge renders as placed.)
            if "on her face" in str(e) or "sits on her" in str(e):
                m = re.search(r"at t=([\d.]+)s", str(e))
                on_her.append({"layer": lname, "t": round(start + (float(m.group(1)) if m else 0.0), 2)})
                if "--no-subject" not in cmd:
                    cmd.append("--no-subject")
                _run(cmd, jd, f"Rendering {lname}")
            elif "OFFFRAME" in str(e).upper() or "off the edge" in str(e):
                on_her.append({"layer": lname, "t": round(start, 2), "edge": True})
                _run(cmd, jd, f"Rendering {lname}", env={"REEL_ALLOW_OFFFRAME_TEXT": "1"})
            else:
                # She always gets her export (you: "it should still give me an export. No matter what."): a look that
                # still won't render goes out without that one look, named in one line after, never a failed export.
                left_out.append({"layer": lname, "t": round(start, 2), "why": str(e).strip().splitlines()[-1][:200]})
                print(f"NOTE: {lname} at {start:.1f}s couldn't be rendered and was left out of this export: {e}")
                continue
        _trim_to(mov, durs.get(lname, 0))                     # a look cut short so the next word look owns its moment
        done_by[i] = (lname, mov, start)
    if on_her:                                                # said once, after: what she placed on herself or past the edge
        _save(jd, placed=on_her, blocked=None)
    if left_out:                                              # said once, plainly: which look isn't in this export
        import re as _re                                      # "08-gif-library" -> "gif library"
        _nm = lambda x: _re.sub(r"^(?:add-w\d+|\d+[a-z]?)-?", "", x["layer"]).replace("-", " ").strip() or "one look"
        _ve_names = ", ".join(f"{_nm(x)} ({int(x['t'] // 60)}:{int(x['t'] % 60):02d})" for x in left_out)
        _save(jd, notice=f"Heads up: {_ve_names} didn't come through this time, so {'it sits' if len(left_out) == 1 else 'they sit'} "
                         "out of this export. Everything else is in. Ask Claude to take a look.", left_out=left_out)
    else:                                                     # a look left out of an earlier try is in this one
        _save(jd, left_out=[])
    rendered = [done_by[i] for i in sorted(done_by)]              # stacked in her order, captions on top
    base = _covered_base(jd, base)                            # her kids' faces covered, before her filter and any cutout
    ebase, slow_note = base, None                             # the cut her looks are burned onto (MP4: at 1080 wide)
    if route == "edits":                                      # no dead end: Edits unreachable -> CapCut, the same medium look
        import edits_handoff
        if not edits_handoff.edits_reachable():
            _save(jd, notice="The Edits app isn't connected yet, so your reel went to CapCut instead (same medium "
                             "look). To connect it, log into your course hub here: https://www.yourbrand.com/login "
                             "and open the Instagram Edits Kit. It walks you through getting your access token. Then "
                             "pick Edits again to send it there.")
            route = "capcut"
    if route == "mp4" or (route == "resolve" and behind and rendered):   # resolve references the cut, so it needs the 1080 copy only to cut her out
        bar.go("copy1080", step="Making a 1080 copy of your cut")
        ebase, slow_note = _export_base(jd, base)
    if behind and rendered:                                   # a look behind her: it goes under everything, she goes over it
        bar.go("behind", step="Cutting you out for the look behind you")
        under = [r for r in rendered if r[0] in behind]
        rendered = under + _behind_cutouts(jd, ebase, under, ve.grade_of(jd)) + [r for r in rendered if r[0] not in behind]
    _save(jd, done=len(layers), slow=False)
    if route == "resolve":
        # the whole reel as a DaVinci Resolve kit (product/resolve_export.py): her cut one clip per kept line, each look
        # on its own track, each sound its own clip, her music bed, her voice alone on its own track. Two ways in: a
        # one-click Workspace > Scripts build, or a hand-imported FCPXML. Captions default to her exact look; a native
        # (real, retypeable) caption version sits in the same folder. The cut's Filter and covered faces are baked in.
        bar.go("resolve", step="Building your Resolve kit")
        import resolve_export
        source = _graded_base(jd, base, ve.grade_of(jd)) or base
        kit_path, installed = resolve_export.build(job, jd, source)   # installs the one-click builds into Resolve's menu
        kit = str(kit_path)
        bar.close()
        rel = os.path.relpath(kit, ROOT).replace(os.sep, "/")
        return _save(jd, state="done", step="Resolve kit ready",
                     result={"route": "resolve", "tag": _tag_line(), "file": f"{rel}/{job} overlay.fcpxml", "dir": rel,
                             "installed": bool(installed), "script": f"Build {job} overlay"})
    if route == "capcut":
        bar.go("capcut", step="Building your CapCut draft")
        if not _vectcut_up() and not _start_vectcut():
            raise Refuse("The CapCut build engine didn't start. Open product/engine/VectCutAPI/"
                         + ("start-editor.bat" if os.name == "nt" else "start-editor.command")
                         + ", leave that window open, then press Export again.")
        uv = shutil.which("uv") or "uv"
        cmd = [uv, "run", os.path.join(HERE, "capcut_handoff.py"), name, "--no-overlay"]   # her looks only, never an old render
        graded = _graded_base(jd, base, ve.grade_of(jd))           # her filter, baked into the footage only
        if graded:
            cmd += ["--base", graded, "--grade", ve.grade_of(jd)]   # her footage after the last clip gets it too
        elif base != os.path.join(jd, "outputs", name + ".mp4"):
            cmd += ["--base", base]                           # her covered footage (Cover a face), split line by line as ever
        try:                                                  # the reel's pack, as the page shows it (switched or built)
            pk = ve._swap_pack(jd, _looks_doc(jd))[0]
            cmd += ["--pack", pk]
        except Exception:
            pass
        try:                                                  # each look's own name, for her cut-out tracks' labels
            _nm = {l["name"]: l.get("look_name") or "" for l in (_looks_doc(jd) or {}).get("layers", [])}
        except Exception:
            _nm = {}
        for lname, mov, start in rendered:
            # her cutout over a look behind her is labeled "cut out" in CapCut, with the look it covers, so she finds it
            # at a glance (you: "label all the cutout layers in CapCut as cut out")
            if lname.startswith("behind-"):
                what = "".join(" " if ch in "=@" else ch for ch in (_nm.get(lname[7:]) or lname[7:])).strip()   # (no re: a later local import shadows it)
                lname = f"cut out · {what}" if what else "cut out"
            cmd += ["--layer", f"{lname}={mov}@{start}"]
        try:
            out = _run(cmd, jd, "Building your CapCut draft", stoppable=False)
        except Refuse as e:
            if "CapCut is open" in str(e):                    # the guard that keeps her draft safe, said for the page
                raise Refuse("CapCut is open. Quit it fully (Cmd+Q on a Mac, or close it on Windows), then press Export "
                             "again. Your looks are already rendered, so it's quick.")
            raise
        draft = next((l.split("CapCut project ready:", 1)[1].strip() for l in out.splitlines() if "CapCut project ready:" in l), None)
        staged = None
        try:                                                  # the Store app or a protected Movies folder: the draft waits in
            import capcut_store_redirect as _csr              # staging for her one double-click (never "it's in CapCut"),
            if _csr.is_staging(_csr.drafts_root()) and _csr.AUTO_DONE_LINE not in out:   # unless the engine added it
                staged = _csr.BAT_NAME if os.name == "nt" else _csr.COMMAND_NAME
        except Exception:
            pass
        bar.close()
        return _save(jd, state="done", step="In CapCut", result={"route": "capcut", "draft": draft, "tag": _tag_line(),
                                                                 **({"staged": staged} if staged else {})})
    if route == "edits":
        # MEDIUM only: her cut goes in as the footage, each look rides on top as its own movable layer. The Edits
        # app can only be driven live over its MCP (its .mcomp archive is off in public MCP mode), so this stages
        # the media where the sandboxed app can read it and writes the build manifest; the edits-export skill
        # replays it into the app. Raw is never offered here: the pack fonts are CapCut-native and would be lost.
        bar.go("edits", step="Staging your Edits build")
        import edits_handoff
        source = _graded_base(jd, base, ve.grade_of(jd)) or base       # her filter, baked into the footage only
        mpath, n = edits_handoff.build(job, jd, source, rendered)      # the shared, already-rendered looks
        bar.close()
        rel = os.path.relpath(mpath, ROOT).replace(os.sep, "/")
        import edits_mode
        # After a one-off export to Edits (the kit isn't her default yet, and she hasn't said no before), tell the
        # edits-export skill to offer making it her default — a faster path next time. See the skill for the ask.
        offer = edits_mode.should_offer_default()
        # A drive-pending marker so the agent's todo/watcher reliably picks up the LIVE import (the edits-export
        # skill drives the metapilot MCP from the manifest) instead of the reel sitting staged. The skill clears it
        # once the project is built + saved in the Edits app.
        try:
            pend = os.path.join(jd, "outputs", "edits", "drive-pending.json")
            json.dump({"manifest": rel, "project_name": name, "looks": n, "at": time.time()}, open(pend, "w", encoding="utf-8"))
        except Exception:
            pass
        return _save(jd, state="done", step="Staged for Edits",
                     result={"route": "edits", "tag": _tag_line(), "file": rel, "looks": n,
                             "project_name": name,
                             **({"offer_default": True} if offer else {})})
    bar.go("burn", step=slow_note or "Putting your looks on your cut")
    final = os.path.join(jd, "outputs", name + ".final.mp4")
    tmp = final + ".part.mp4"
    cmd = [sys.executable, os.path.join(HERE, "burn_layers.py"), "--base", ebase]
    if ve.grade_of(jd):                                       # her filter, on the footage only
        cmd += ["--grade", ve.grade_of(jd)]
    for _, mov, start in rendered:
        cmd += ["--layer", f"{mov}@{start}"]
    if rendered:
        _run(cmd + ["-o", tmp], jd, "Exporting your reel")
    else:                                                     # every look off: her cut itself (graded when she picked one)
        import video_grade
        g = video_grade.grade_filter(ve.grade_of(jd)) if ve.grade_of(jd) else None
        _run(["ffmpeg", "-v", "error", "-y", "-i", ebase] + (["-vf", g + ",format=yuv420p", "-c:v", "libx264", "-crf", "14", "-preset", "slow"] if g else ["-c:v", "copy"])
             + ["-c:a", "copy", "-movflags", "+faststart", tmp], jd, "Exporting your reel")
    mixed = _mix_sound(jd, tmp, extra=[(mov, start) for _n, mov, start in rendered if _has_audio(mov)])   # her b-roll's own sound
    os.replace(mixed or tmp, final)
    bar.go("phone", step="Making a phone copy")
    phone = os.path.join(jd, "outputs", name + ".phone.mp4")
    _run(["ffmpeg", "-v", "error", "-y", *export_progress.ffmpeg_args(_probe_dur(final), getattr(_HERE, "sub", None)), "-i", final, "-vf", "scale=720:-2", "-c:v", "libx264", "-crf", "24",
          "-preset", "veryfast", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", phone + ".tmp.mp4"], jd, "The phone copy")
    os.replace(phone + ".tmp.mp4", phone)
    bar.close()
    return _save(jd, state="done", step="Exported", result={"route": "mp4", "tag": _tag_line(), "file": f"projects/{name}/outputs/{os.path.basename(final)}",
                                                            "phone": f"projects/{name}/outputs/{os.path.basename(phone)}"})


def _export_base(jd, base):
    """The cut an MP4 export burns her looks onto: a 1080-wide copy of her cut, the size Instagram plays and her looks
    are drawn at. Burning 21 looks onto a 1728x3072 phone recording took about 29 minutes for no visible gain on a phone.
    Her own outputs/<job>.mp4 is never touched (CapCut keeps the full-size footage to punch in and reframe). Kept as
    outputs/<job>.1080.mp4 and remade only when her cut changes. Encoded the PC-safe way: the shared encoder (NVENC on a
    Windows GPU, VideoToolbox on a Mac, libx264 veryfast otherwise, with the bt709 tags a browser needs), a software
    retry, a temp name swapped in with visual_editor._replace (Windows refuses a swap while the page streams the file).
    REE_FULL_RES_EXPORT=1 burns onto the full-size cut as before. Returns (path, a plain line when it fell back)."""
    if os.environ.get("REE_FULL_RES_EXPORT") == "1" or not os.path.isfile(base):
        return base, None
    try:
        from probe import display_dims
        w, h = display_dims(base)
    except Exception:
        return base, None
    import frame
    wide = frame.is_wide(jd)
    if not w or int(w) >= 1920 and wide or int(w) <= 1080 and not wide:   # a wide video exports at its own size at 1080p or 4K; under 1080p it's brought up to it
        return base, None
    ve = _ve()
    out = base[:-len(".mp4")] + ".1080.mp4"
    stamp = out[:-len(".mp4")] + ".json"
    st = os.stat(base)
    want = {"size": st.st_size, "mtime": int(st.st_mtime)}
    try:
        if os.path.isfile(out) and json.load(open(stamp, encoding="utf-8")) == want:
            return out, None                                  # her cut hasn't changed since: reused as is
    except Exception:
        pass
    import video_encoder
    tmp = out + ".part.mp4"
    _pg = export_progress.ffmpeg_args(_probe_dur(base), getattr(_HERE, "sub", None))   # the bar follows this encode
    cmd = lambda enc: ["ffmpeg", "-v", "error", "-y", *_pg, "-i", base, "-vf", f"scale={1920 if wide else 1080}:-2:flags=lanczos", *enc,
                       "-c:a", "copy", "-movflags", "+faststart", tmp]
    venc = video_encoder.pick_encoder(vbr="12M", crf=16, preset="veryfast")
    r = subprocess.run(cmd(venc), capture_output=True, text=True)
    if r.returncode != 0 and video_encoder.is_hardware(venc):  # a hardware encoder that won't start: software, every build has it
        r = subprocess.run(cmd(video_encoder.software_encoder(crf=16, preset="veryfast")), capture_output=True, text=True)
    if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
        ve._replace(tmp, out)
        ve._atomic_json(stamp, want)
        return out, None
    if os.path.exists(tmp):
        os.remove(tmp)
    return base, "Putting your looks on your full-size cut (the quicker 1080 copy didn't make, so this takes a little longer)"


def _has_audio(path):
    try:
        return bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                    "-of", "csv=p=0", path], capture_output=True, text=True, timeout=30).stdout.strip())
    except Exception:
        return False


def _cutaway_out(jd, src, out, grade):
    """One b-roll cutaway for the export: its exact frames (and its sound, only when she turned it on, already set
    under her voice), with her filter on it like the rest of her footage."""
    import video_grade
    g = video_grade.grade_filter(grade) if grade else None
    tmp = out + ".part.mp4"
    if g:
        _run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", g + ",format=yuv420p", "-c:v", "libx264", "-crf", "14",
              "-preset", "slow", "-c:a", "copy", "-movflags", "+faststart", tmp], jd, "Your b-roll")
    else:
        shutil.copyfile(src, tmp)
    os.replace(tmp, out)


def _cutout(seg, mov, jd):
    """HyperFrames' remove-background through product/bg_remove.py, the one way the engine runs it: its folder made
    first (without it the tool waits forever), a run past the clip's time limit stopped whole with a plain reason,
    and her Stop on the page ending the tool too."""
    import bg_remove
    try:
        bg_remove.run(seg, mov, should_stop=lambda: _stopped(jd), on_start=lambda pid: _save(jd, child=pid))
    except bg_remove.Stopped:
        raise Stopped("You stopped the export. Nothing changed; press Export whenever you're ready.")
    except bg_remove.CutoutFailed as e:
        raise Refuse(f"Cutting you out stopped: {e}")


def _behind_cutouts(jd, base, under, grade):
    """Her, cut out of her own footage for each look that sits behind her: HyperFrames' remove-background on that
    stretch of her cut (graded the way her footage is), a clear ProRes 4444 clip at her footage's own size, laid over
    the look so she covers it. Final-only, the way the chat render always did it (studio_behind.sh): the page previews
    the look in front. Made once per stretch; a new cut or filter makes it again."""
    looks = {L["name"]: L for L in _looks_doc(jd).get("layers", [])}
    out_dir = os.path.join(jd, "hf-graphics", "finish")
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for lname, _mov, start in under:
        dur = float(looks.get(lname, {}).get("dur") or 0)
        if dur <= 0:
            continue
        _save(jd, step="Cutting you out for the look behind you")
        mov = os.path.join(out_dir, f"behind-{lname}.mov")
        key = f"{os.path.getmtime(base)}|{start}|{dur}|{grade or ''}"
        try:
            fresh = os.path.isfile(mov) and open(mov + ".key", encoding="utf-8").read() == key
        except OSError:
            fresh = False
        if not fresh:
            seg = os.path.join(out_dir, f"behind-{lname}.src.mp4")
            vf = []
            if grade:
                import video_grade
                g = video_grade.grade_filter(grade)
                if g:
                    vf = ["-vf", g + ",format=yuv420p"]
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", base, "-t", f"{dur:.3f}", "-an"] + vf
                 + ["-c:v", "libx264", "-crf", "12", "-preset", "fast", seg], jd, "Cutting you out")
            _cutout(seg, mov, jd)
            open(mov + ".key", "w", encoding="utf-8").write(key)
            try:
                os.remove(seg)
            except OSError:
                pass
        made.append((f"behind-{lname}", mov, start))
    return made


def _covered_base(jd, base):
    """Cover a face: the footage with her covers built in (product/face_cover.py bake), made once per set of covers
    and never rewritten (a draft she opened may link it). Everything after it (her filter, a cutout of her for a
    look behind her, the CapCut clips, the MP4) starts from this copy, so a covered face stays covered on every
    route. No covers = her footage as it was."""
    import face_cover
    if not face_cover.covers_on(jd):
        return base
    out = os.path.join(jd, "hf-graphics", "finish", f"footage-covered-{face_cover.signature(jd)}-{int(os.path.getmtime(base))}.mp4")
    if os.path.isfile(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    _save(jd, step="Covering faces")
    uv = shutil.which("uv") or "uv"
    _run([uv, "run", "-q", os.path.join(HERE, "face_cover.py"), "bake", os.path.basename(jd), base, out], jd, "Covering faces")
    return out


def _graded_base(jd, base, look):
    """Her filter on the CapCut route: the footage graded once into its own file (graphics never touched), which
    the handoff then splits one clip per line exactly as before, so every clip stays its own. One file per filter,
    written once and never rewritten (a draft she opened may link it); a newer cut makes a new one. None = no filter."""
    if not look:
        return None
    import video_grade
    out = os.path.join(jd, "hf-graphics", "finish", f"footage-{look}-{int(os.path.getmtime(base))}.mp4")
    if os.path.isfile(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    _save(jd, step="Adding your filter")
    tmp = out + ".part.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-i", base, "-vf", video_grade.grade_filter(look) + ",format=yuv420p", "-c:v", "libx264",
          "-crf", "14", "-preset", "slow", "-c:a", "copy", "-movflags", "+faststart", tmp], jd, "Adding your filter")
    os.replace(tmp, out)
    return out


def _tag_line():
    """The end-of-workflow hashtag line (product/hashtag.py), or "" once she has said don't remind me."""
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "hashtag.py"), "--peek"], capture_output=True, text=True, encoding="utf-8", timeout=20)
        return r.stdout.strip()
    except Exception:
        return ""


def _mix_sound(jd, video, extra=()):
    """Her sound effects and music bed into the exported file, leveled exactly the way the engine's finished-video
    build levels them (the north star in product/audio_levels.py: each cue's loudest moment under her voice's
    loudness, the bed under her voice, a level she set wins), with her Sound edits applied (product/sound_plan.py).
    None when there's nothing to mix: her voice stays exactly as the full-quality cut made it. `extra`: [(file, at)]
    sounds already set to their level (her b-roll's own sound, when she turned it on), laid in at their times as they are."""
    import audio_levels as al
    notes = []                                                # what of her sound didn't make it, said once after the export

    def _say(m):
        m = str(m)
        if "⚠" in m or "Left out" in m:
            notes.append(re.sub(r"^\[sound\]\s*(⚠\s*)?", "", m))
    try:
        import sound_plan
        src, entries, tkey, music = sound_plan.base(jd)
        plan_sfx = [dict(e, at=e.get(tkey, e.get("at", e.get("t", 0)))) for e in entries]
        sfx, music = sound_plan.for_build(jd, plan_sfx, music, say=_say)
    except Exception as e:
        notes.append(f"her Sound edits couldn't be read for this export ({type(e).__name__}: {e}), so it went out without "
                     "her sound effects and music bed. Reopen the Sound tab and export again.")
        sfx, music = [], None
    _save(jd, sound_notes=notes or None)
    try:
        muted = sound_plan.voice_muted(jd)                    # she muted her clip: none of its own sound goes out
    except Exception:
        muted = False
    if not sfx and not music and not extra and not muted:
        return None
    cues = []
    for c in sfx or []:
        f = sound_plan.resolve_ref(jd, c.get("file"))
        if f and os.path.isfile(f):
            cues.append(dict(c, _f=f))
    mf = sound_plan.resolve_ref(jd, (music or {}).get("file")) if music and music.get("file") else None
    if not cues and not mf and not extra and not muted:
        return None
    try:
        cpj = json.load(open(os.path.join(jd, "caption-plan.json"), encoding="utf-8")) or {}
    except Exception:
        cpj = {}
    sduck, mduck = float(cpj.get("sfx_duck_db", al.SFX_DUCK_DB)), cpj.get("music_duck_db")   # the plan's own, as the bake reads them
    inputs, fc, labels = ["-i", video], [], ["[0:a]"]
    if muted:                                                 # her muted clip: its track stays as the mix's clock, silent
        fc.append("[0:a]volume=0[v0]"); labels = ["[v0]"]
    for k, c in enumerate(cues):
        g = float(c["gain_db"]) if "gain_db" in c else al.sfx_gain_for(c["_f"], video, c.get("trim"), sduck)
        ch = []
        if c.get("trim"):
            t = float(c["trim"]); ch += [f"atrim=0:{t:.3f}", f"afade=t=out:st={max(0, t - 0.12):.3f}:d=0.12"]
        ms = int(round(float(c.get("at", 0)) * 1000))
        ch += ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo", f"volume={g:.1f}dB", f"adelay={ms}|{ms}"]
        inputs += ["-i", c["_f"]]
        fc.append(f"[{k + 1}:a]{','.join(ch)}[s{k}]"); labels.append(f"[s{k}]")
    if mf:
        n = len(cues) + 1
        total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                                     capture_output=True, text=True).stdout.strip() or 0)
        at, fi, fo = float(music.get("at", 0)), float(music.get("fade_in", 0.0)), float(music.get("fade_out", 2.5))
        mlen = max(0.1, total - at)
        g = float(music["gain_db"]) if "gain_db" in music else al.bed_gain_for(mf, video, mduck)
        ch = [f"atrim=0:{mlen:.3f}", "asetpts=PTS-STARTPTS", "aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo",
              *([f"afade=t=in:st=0:d={fi:.2f}"] if fi > 0 else []), f"afade=t=out:st={max(0, mlen - fo):.3f}:d={fo:.2f}", f"volume={g:.1f}dB"]
        ms = int(round(at * 1000))
        if ms:
            ch.append(f"adelay={ms}|{ms}")
        inputs += (["-stream_loop", "-1"] if music.get("loop", True) else []) + ["-i", mf]
        fc.append(f"[{n}:a]{','.join(ch)}[bed]"); labels.append("[bed]")
    for k, (f, at) in enumerate(extra):
        n = inputs.count("-i")                            # its input number (the bed may carry -stream_loop)
        ms = int(round(float(at) * 1000))
        inputs += ["-i", f]
        fc.append(f"[{n}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay={ms}|{ms}[x{k}]")
        labels.append(f"[x{k}]")
    fc.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0,"
              "aresample=192000,alimiter=level_in=1:level_out=1:limit=0.8414:attack=5:release=50:level=disabled,"   # true peak
              "aresample=48000[aout]")                         # <= -1.5 dBTP after the encode (the north star, audio_levels)
    out = video + ".mixed.mp4"
    # One chain per sound: a long graph goes in a file, never inline (a Windows command line stops at 32,767
    # characters, WinError 206), the way the stitch hands over its graph.
    from video_encoder import graph_args, remove_graph
    gfile = video + ".mix-graph.txt"
    try:
        # -map_chapters -1: no chapter from her song (an Epidemic mp3 carries one) in her reel, where players read it
        # as a longer reel with an empty stretch at the end
        r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + graph_args(";".join(fc), gfile) + ["-map", "0:v", "-c:v", "copy",
                            "-map", "[aout]", "-map_chapters", "-1", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out],
                           capture_output=True, text=True)
    finally:
        remove_graph(gfile)
    if r.returncode != 0 or not os.path.isfile(out):          # she still gets her reel: her voice as cut, said once
        try:
            _save(jd, notice="Your reel exported with your voice only: the sound effects and music didn't mix in this time. "
                             "Press Export again to try the mix once more.")
        except Exception:
            pass
        return None
    os.remove(video)
    return out


def main(argv):
    if len(argv) >= 2 and argv[0] == "status":
        print(json.dumps(status(_ve().job_dir(argv[1])), indent=1))
        return 0
    if len(argv) >= 3 and argv[0] == "run":
        try:
            d = run(argv[1], argv[2])
            print(json.dumps(d, indent=1))
            for x in status(_ve().job_dir(argv[1])).get("placed") or []:   # Claude says these once, plainly, after the delivery
                print(f"NOTE: {x['layer']} at {x['t']:.1f}s may sit on her face (rendered as placed). Tell her, and offer to move it.")
            for x in status(_ve().job_dir(argv[1])).get("sound_notes") or []:
                print(f"NOTE: sound: {x} Tell her once, plainly.")
            return 0
        except Refuse as e:
            print(str(e), file=sys.stderr)
            return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):     # a PC console that is not UTF-8 would choke on the status symbols
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
