#!/usr/bin/env python3
"""The visual editor, walked end to end the way a person clicks it: the JOURNEY test.

Why it exists: the unit tests (test_visual_editor.py) and the page checks (test_visual_editor_page.py) prove each
feature on its own, mostly by calling the page's functions. Features that each pass on their own still broke real
clicks once they met on one page (Move jumped the playhead, a redrawn look played a stale copy, two Lock in buttons
disagreed, a quiet stretch was refused). This test drives the page with the mouse and the keyboard, on one reel, one
step after another, and after EVERY step checks what a person would notice:
  - no page error (script errors, console errors, errors the page reported to the engine)
  - the playhead moved only when the step should move it
  - the look she grabbed is the one selected
  - her captions are hidden exactly while a word look plays (never two caption styles at once)
  - "Lock in" says the same thing everywhere it appears
  - the task queue shows the rows it should

The reel (editor_journey_fixture.py) has a plain clip, a sped-up clip, a quiet piece, a long-stamped word, a zoom and
a speed ramp. The page server is the real one (visual_editor_server), on the real engine (visual_editor), in a
throwaway folder; three stand-ins only: the lean stitch (fake_stitch: the cut plan becomes the cut, no venv, no
encode), the background full-quality cut (off), and Claude (test-only doors that do what the chat would: take her
notes, finish them, make her looks, watch the page). Nothing touches her real reels, settings or logs.

The steps are in editor_journey.js; every bug a creator reports becomes one (see "REPORTED" there).

Runs in about a minute and a half on the headless Chrome HyperFrames installs (`npx hyperframes@0.9.6 browser
ensure`); without one it says so and passes (test_visual_editor.py still ran).

Run:   python3 product/tests/test_editor_journey.py            (the ship gate runs exactly this)
       python3 product/tests/test_editor_journey.py --until "quiet line"   (stop after the step whose name has those words)
       python3 product/tests/test_editor_journey.py --serve    (the fixture reel on a live page, to click by hand)
       VE_SHOTS=/some/dir python3 product/tests/test_editor_journey.py   (a screenshot after every step)
Dev rule (dev-tools/EDITOR-JOURNEY.md): an editor change lands on a worktree branch and this passes before it merges.
"""
import json, os, shutil, subprocess, sys, tempfile, threading, time
os.environ.setdefault("REE_EDITOR", "1")                     # the editor is on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
sys.path.insert(0, HERE)
import editor_journey_fixture as fx                          # noqa: E402

BUDGET_S = 180                                               # the whole run, browser included: fast enough for every change


def find_tools():
    """node, puppeteer-core and a headless Chrome: the same ones the page checks use (test_visual_editor_page)."""
    from test_visual_editor_page import find_tools as ft
    return ft()


def sandbox(tmp):
    """Point every place the engine reads or writes her own things at the throwaway folder. Returns (ve, srv, jd)."""
    tempfile.tempdir = tmp                                   # apply's scratch plan lands here, never in the shared scratch
    proj = os.path.join(tmp, "projects")
    jd = fx.make_reel(proj)
    import visual_editor as ve
    import visual_editor_server as srv
    real_dir = ve.job_dir
    ve.job_dir = lambda job: jd if os.path.basename(str(job)) == fx.JOB else real_dir(job)
    ve.can_behind = lambda: False
    ve.USER_STYLE = os.path.join(tmp, "user-style.json")
    ve.TOUR_FILE = os.path.join(tmp, "_local", "editor-tour.json")
    ve._stitch = fx.fake_stitch(ve)
    import sound_plan, favorites_folder, capcut_sfx, lookbook
    sound_plan.job_dir = lambda job: jd if os.path.basename(str(job)) == fx.JOB else job
    sound_plan.LOCAL = os.path.join(tmp, "_local")
    sound_plan.LEVELS = os.path.join(sound_plan.LOCAL, "sound-levels.json")
    sound_plan.PREVIEW_DIR = os.path.join(sound_plan.LOCAL, "sound-preview")
    sound_plan._levels_mem = None
    sound_plan.EPIDEMIC_HOME = os.path.join(tmp, "Documents", "Epidemic Sound")
    sound_plan.PROJECTS_DIR = proj
    favorites_folder.FOLDER = os.path.join(tmp, "favorites")
    favorites_folder.CACHE = os.path.join(sound_plan.LOCAL, "favorites-cache")
    capcut_sfx.FAVORITES_DIR = os.path.join(sound_plan.LOCAL, "sounds")
    lookbook.ROOT = tmp
    srv.ve, srv.PROJECTS = ve, proj
    srv._premake = lambda what, job: False                   # no full-quality cut cooking in the background
    import editor_says
    editor_says.CHIMES = []
    editor_says.chime = lambda: editor_says.CHIMES.append(time.time()) or True   # counted, never played out loud
    ve.prepare(jd, log=lambda *a: None)
    return ve, srv, jd


class Claude:
    """What the chat does to her reel, on cue: the test's stand-in for Claude. Each returns what it did."""

    def __init__(self, ve, jd):
        self.ve, self.jd, self.watch = ve, jd, False
        threading.Thread(target=self._beat, daemon=True).start()

    def _beat(self):                                         # a live watcher writes a heartbeat; so does this one
        while True:
            if self.watch:
                self.ve._atomic_json(os.path.join(self.jd, "review", "claude-watching.json"), {"pid": os.getpid(), "at": time.time()})
            time.sleep(5)

    def do(self, op, q):
        ve, jd, job = self.ve, self.jd, fx.JOB
        rv = os.path.join(jd, "review")
        if op == "watch":                                    # the `wait` watcher starts
            self.watch = True
            ve._atomic_json(os.path.join(rv, "claude-watching.json"), {"pid": os.getpid(), "at": time.time()})
            return {"watching": True}
        if op == "unwatch":
            self.watch = False
            for f in ("claude-watching.json", "claude-working.json"):
                try:
                    os.remove(os.path.join(rv, f))
                except OSError:
                    pass
            return {"watching": False}
        if op == "take":                                     # Claude claims everything waiting on it
            items = ve.todo(job)
            ve.claim(job, items)
            return {"took": [ve._todo_id(t) for t in items]}
        if op == "done":                                     # every open note fixed
            notes = (json.load(open(ve._notes_path(jd), encoding="utf-8")) if os.path.exists(ve._notes_path(jd)) else {}).get("notes", [])
            done = [n["id"] for n in notes if n.get("status") != "fixed"]
            for nid in done:
                ve.resolve(job, nid, "Done: trimmed that breath")
            return {"fixed": done}
        if op == "looks":                                    # "show me my looks": Phrase captions + a word look on line 2
            return self.looks(q)
        if op == "sketch":                                   # "sandbox": her idea on the quiet line, one sketch in
            return self.sketch()
        if op == "tell":                                     # `visual_editor.py tell <job> "..." [--chat]`
            import editor_says
            m = editor_says.tell(jd, (q.get("text") or ["A note"])[0], chat=bool(q.get("chat")), kind="chat" if q.get("chat") else "note",
                                 go=(q.get("go") or [None])[0])
            return {"id": m["id"]}
        if op == "state":                                    # the files, for checks the page can't see
            rd = lambda p: (json.load(open(os.path.join(jd, p), encoding="utf-8")) if os.path.exists(os.path.join(jd, p)) else None)
            return {"phase": rd("review/phase.json"), "review": rd("transcript/script-review.json"), "cuts": rd("transcript/cuts.json"),
                    "notes": rd("transcript/script-notes.json"), "swaps": rd("review/swaps.json"), "looks": rd("review/looks.json"),
                    "queue": ve.task_queue(job), "chimes": len(getattr(__import__("editor_says"), "CHIMES", []))}
        raise ValueError(op)

    def looks(self, q):
        ve, jd, job = self.ve, self.jd, fx.JOB
        ve.set_captions(job, (q.get("caps") or ["phrase"])[0])
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
        times = ve.word_cut_times(jd)
        line = next(ids for ids in sc["lines"] if len(ids) >= 5 and not sc["words"][ids[0]].get("q") and ids[0] != 0)
        kept = [i for i in line if i in times]
        a, b = times[kept[0]][0], times[kept[-1]][1]
        ve.place_look(job, f"add-w{kept[0]}", a, b, (q.get("look") or ["takeover"])[0])
        ve.looks_manifest(jd)
        return {"layers": [L["name"] for L in json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8"))["layers"]]}


    SKETCH = """<!doctype html><html><head><meta charset="UTF-8"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>html,body{width:1080px;height:1920px;overflow:hidden;background:transparent;margin:0}#root{position:absolute;inset:0}
.pop{position:absolute;top:700px;width:300px;height:420px;border-radius:24px;background:var(--pk-light)}#p0{left:140px}#p1{left:640px}
#notes{position:absolute;left:0;right:0;top:1200px;text-align:center;font-family:PkLabel;font-size:54px;color:var(--pk-light)}</style></head>
<body><div id="root" data-composition-id="__COMP__" data-start="0" data-duration="__DUR__" data-width="1080" data-height="1920">
<div class="clip" id="clip-cards" data-start="0" data-duration="__DUR__" data-track-index="2"><div class="pop" id="p0"></div><div class="pop" id="p1"></div>
<span id="notes">__NOTE__</span></div></div>
<script>window.__timelines=window.__timelines||{};const D=__DUR__;const tl=gsap.timeline({paused:true});
[0,1].forEach(i=>{ tl.fromTo("#p"+i,{autoAlpha:0,scale:0.2},{autoAlpha:1,scale:1,duration:0.35,ease:"back.out(1.8)"},0.1+i*0.5); });
tl.set("#root",{autoAlpha:0},Math.max(0.9,D-0.04));window.__timelines["__COMP__"]=tl;</script></body></html>"""

    def sketch(self):
        """"sandbox" in the chat: her open Sandbox idea gets one sketch on the reel's quiet line (no talking there): two
        cards popping in, the handles she wants on them in its note (her words never say them), named for what it is."""
        import lookbook
        ve, jd, job = self.ve, self.jd, fx.JOB
        sc = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8"))
        times = ve.word_cut_times(jd)
        line = next(ids for ids in sc["lines"] if ids and all(sc["words"][i].get("q") for i in ids))
        kept = [i for i in line if i in times]
        a, b = times[kept[0]][0], times[kept[-1]][1]
        r = next(x for x in ve._requests(jd) if x.get("mode") == "sandbox" and x.get("status") == "open")   # the idea she sent
        d = os.path.join(os.path.dirname(jd), "_sketch", r["id"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(self.SKETCH)
        json.dump({"name": "Card pop orbit", "about": "Two cards pop up beside you, your handles under them.", "kind": "Card",
                   "slots": ["note"], "note": "@one @two"}, open(os.path.join(d, "design.json"), "w", encoding="utf-8"))
        sid = f"my-sandbox-{r['id']}-r1-1"
        lookbook.save_design(d, ve._reel_pack_for(jd), "Sketch 1", sample=r["id"], design_id=sid)
        ve.sandbox_takes(job, r["id"], [sid], start=a, end=b)
        return {"id": r["id"], "a": a, "b": b}


def serve(ve, srv, jd):
    claude = Claude(ve, jd)
    Base = srv.Handler

    class Handler(Base):
        def do_GET(self):
            if self.path.startswith("/__claude"):            # test-only: Claude's side of the conversation
                from urllib.parse import urlsplit, parse_qs
                u = urlsplit(self.path)
                q = parse_qs(u.query)
                try:
                    return self._json(200, claude.do(q.get("do", [""])[0], q))
                except Exception as e:
                    import traceback
                    return self._json(500, {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]})
            return Base.do_GET(self)

    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, claude


def main(argv):
    until = argv[argv.index("--until") + 1] if "--until" in argv else ""
    if not shutil.which("ffmpeg"):
        print("test_editor_journey: skipped (ffmpeg isn't on this machine to make the test reel).")
        return 0
    tools = None if "--serve" in argv else find_tools()
    if "--serve" not in argv and not tools:
        print("test_editor_journey: skipped (no headless browser here yet; `npx hyperframes@0.9.6 browser ensure` "
              "installs one). test_visual_editor.py still ran.")
        return 0
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="ve-journey-")
    errlog = os.path.join(tmp, "editor-errors.jsonl")
    os.environ["REE_EDITOR_ERRORS_LOG"] = errlog             # errors the page reports to the engine: read back below
    try:
        import editor_errors
        if hasattr(editor_errors, "LOG"):
            editor_errors.LOG = errlog
    except Exception:
        pass
    try:
        ve, srv, jd = sandbox(tmp)
        httpd, claude = serve(ve, srv, jd)
        port = httpd.server_address[1]
        base, url = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{port}/editor/?job={fx.JOB}"
        if "--serve" in argv:
            print(f"the journey reel, live: {url}\n  Claude's side: {base}/__claude?do=watch|unwatch|take|done|looks|sketch|tell|state\n"
                  f"  folder: {jd}\n  Ctrl+C to stop", flush=True)
            import signal
            signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))   # stopped: still tidy up
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                return 0
        node, pup, chrome = tools
        env = dict(os.environ, PUP=pup, CHROME=chrome, BASE=base, URL=url, UNTIL=until, SHOT=os.environ.get("VE_SHOTS", ""),
                   PLAT=sys.platform)
        r = subprocess.run([node, os.path.join(HERE, "editor_journey.js")], capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=BUDGET_S + 60, cwd=tmp)
        httpd.shutdown()
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            print("test_editor_journey: the browser run didn't finish\n", r.stdout[-3000:], r.stderr[-3000:])
            return 1
        logged = []
        if os.path.exists(errlog):                           # what the page told the engine went wrong
            for line in open(errlog, encoding="utf-8"):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("kind") != "told":                  # a plain-words refusal is the page doing its job
                    logged.append(f"{e.get('where', '')}: {e.get('msg') or e.get('error') or ''}"[:300])
        for name in res["ok"]:
            print("  PASS ", name)
        for name in res["bad"]:
            print("  FAIL ", name)
        for name in res.get("open", []):
            print("  OPEN ", name)                           # reported, reproduced, not fixed yet (KNOWN in editor_journey.js)
        for name in res.get("fixed", []):
            print("  NOW PASSES  (take it off KNOWN in editor_journey.js) ", name)
        if logged:
            print("  FAIL  the engine logged errors during the walk:\n      " + "\n      ".join(logged[:8]))
        secs = time.time() - t0
        slow = secs > BUDGET_S
        if slow:
            print(f"  FAIL  the walk took {secs:.0f}s; it must stay under {BUDGET_S}s so it runs on every editor change")
        if os.environ.get("VE_JOURNEY_LOG") or res["bad"]:
            sys.stderr.write(r.stderr[-6000:])
        n_bad = len(res["bad"]) + (1 if logged else 0) + (1 if slow else 0)
        if n_bad:
            print(f"test_editor_journey: {n_bad} of {len(res['ok']) + n_bad} checks FAILED ({secs:.0f}s)")
            return 1
        opened = f"; {len(res.get('open', []))} reported bug(s) still OPEN" if res.get("open") else ""
        print(f"test_editor_journey: all {len(res['ok'])} checks passed ({secs:.0f}s){opened}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
