#!/usr/bin/env python3
"""Guards: "Send my cut" lands, or says why, and "Lock in my cut" comes. Three buyers (2026-10-22 / 23) could not get
past the Cut tab:

  wordless   a piece of her cut with no words under it (b-roll inside a talking clip) is pinned (keep_edges + no_trim)
             on every Send and in a plan written in the chat, so the stitch's passes can't take it out
  fx         a clip carries ONE Speed / Zoom move: two words of one clip with opposite moves never flip it on every
             Send (the engine applies the lowest, the one her page plays; the page sends one per clip and says
             "speed or zoom change", never "edge trimmed")
  lock       a Send with nothing in it never reopens a cut she locked in (/save and apply both)
  stale      a Send from a page whose cut Claude has changed since is refused with `stale`, so the page reloads onto
             the newer cut instead of writing the old one back
  landed     /status carries the newest receipt that reached her cut (last_applied), the one /save handed her page
  page       (headless browser, when there is one) her draft replays only what she has NOT sent onto a new cut, keeps
             a second of no talking by its moment, says the changes the cut didn't take, never loops on a Send that
             came back the same, and says a Send that never arrived

Run: python3 product/tests/test_send_cut_lands.py
"""
import inspect, json, os, shutil, subprocess, sys, tempfile, threading, time
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
sys.path.insert(0, HERE)
import visual_editor as ve  # noqa: E402

fails, total = [], 0
TMP = tempfile.mkdtemp(prefix="send-lands-")
tempfile.tempdir = TMP                       # apply's scratch plan lands here, never in the real scratch folder
QUIET = lambda *a, **k: None


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[-400:]) if detail else ''}")


# talking at 0-4 s and 8-10 s; 5.2-7.6 s is b-roll inside the same clip: no words under it
WORDS = [{"word": f"w{i}", "start": float(i), "end": i + 0.6} for i in range(5)] + \
        [{"word": f"v{i}" + ("." if i == 2 else ""), "start": 8.0 + i, "end": 8.6 + i} for i in range(3)]
SEGS = [{"clip": "a.mov", "start": -0.04, "end": 4.64, "transcript": ""},
        {"clip": "a.mov", "start": 5.2, "end": 7.6, "transcript": ""},
        {"clip": "a.mov", "start": 7.96, "end": 10.64, "transcript": ""}]


def make_job(name, segs=SEGS, words=WORDS):
    jd = os.path.join(TMP, name)
    for d in ("transcript", "review"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    json.dump({"clips": [{"clip": "a.mov", "path": "", "duration": 11, "words": words}]},
              open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    json.dump({"segments": segs}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    return jd


def _fake_sub(run):
    """A stand-in subprocess whose stitch answers through run(cmd, **k) (the stitch is started with Popen)."""
    import subprocess as _sp

    class _P:
        def __init__(self, cmd, **k):
            k = {key: v for key, v in k.items() if key not in ("stdout", "stderr", "stdin", "text", "encoding", "errors",
                                                             "start_new_session", "creationflags")}
            self.returncode, self.stdout, self.pid = run(cmd, **k).returncode, iter(()), 0

        def wait(self, timeout=None):
            return self.returncode

    return type("S", (), {"run": staticmethod(run), "Popen": _P, "PIPE": _sp.PIPE, "STDOUT": _sp.STDOUT,
                          "DEVNULL": _sp.DEVNULL, "TimeoutExpired": _sp.TimeoutExpired})


def test_wordless():
    jd = make_job("wordless")
    _, clips, segs, wid, _ = ve.load(jd)
    words = ve.kept_quiet(ve.words_of(clips), clips, segs)
    beats = [i for i, w in enumerate(words) if w.get("q")]
    check("wordless: the b-roll piece comes in as seconds of no talking", len(beats) >= 2, words)
    base = {"job": "wordless", "id": wid}
    out = ve.apply_edits(jd, {**base, "cut": [], "back": []}, stitch=False, log=QUIET)
    mid = [p for p in out if abs(float(p["start"]) - 5.2) < 1e-6]
    check("wordless: a Send with no edits keeps the piece", len(out) == 3 and len(mid) == 1, out)
    check("wordless: ... pinned, so no stitch pass moves or drops it", mid and mid[0].get("keep_edges") and mid[0].get("no_trim"), mid)
    check("wordless: a talking piece is not pinned by it", not out[0].get("no_trim") and not out[0].get("keep_edges"), out[0])
    out = ve.apply_edits(jd, {**base, "cut": [1], "back": []}, stitch=False, log=QUIET)
    mid = [p for p in out if abs(float(p["start"]) - 5.2) < 1e-6]
    check("wordless: a word cut elsewhere leaves the piece in, pinned", len(mid) == 1 and mid[0].get("no_trim"), out)
    out = ve.apply_edits(jd, {**base, "cut": [beats[0]], "back": []}, stitch=False, log=QUIET)
    rest = [p for p in out if 5.2 < float(p["start"]) < 7.6]
    check("wordless: cutting one of its seconds keeps the rest, pinned", len(rest) == 1 and rest[0].get("no_trim")
          and rest[0].get("keep_edges"), out)
    pinned = ve.pin_wordless(jd, SEGS)
    check("wordless: a plan from the chat gets the same pin (restitch)", [bool(p.get("no_trim")) for p in pinned] == [False, True, False]
          and "pin_wordless(" in inspect.getsource(ve.restitch), pinned)
    # the stitch's passes leave a pinned piece exactly as it is
    import importlib.util
    spec = importlib.util.spec_from_file_location("close_pauses", os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "close-pauses.py"))
    cp = importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
    got, _, _ = cp.tighten([pinned[1]], os.path.join(TMP, "no-media"), lambda c: [])
    check("wordless: the dead-air pass passes a pinned piece over", got == [pinned[1]], got)
    tr = open(os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "trim-restarts.py"), encoding="utf-8").read()
    check("wordless: the double-take pass passes a no_trim piece over", 'if seg.get("no_trim"): return [seg]' in tr)


def test_fx_one_per_clip():
    one = [{"clip": "a.mov", "start": -0.04, "end": 4.64, "transcript": ""}]
    jd = make_job("fxjob", segs=one, words=WORDS[:5])
    wid = ve.load(jd)[3]
    base = {"job": "fxjob", "id": wid, "cut": [], "back": []}
    zin = {"from": 1.0, "to": 1.15}
    out = ve.apply_edits(jd, {**base, "fx": {"0": {"zoom": zin}, "2": {"zoom": None}}}, stitch=False, log=QUIET)
    check("fx: two opposite moves on one clip: the lowest word's move wins", len(out) == 1 and out[0].get("zoom") == zin, out)
    out = ve.apply_edits(jd, {**base, "fx": {"2": {"zoom": None}, "0": {"zoom": zin}}}, stitch=False, log=QUIET)
    check("fx: ... whatever order they arrive in", out[0].get("zoom") == zin, out)
    out = ve.apply_edits(jd, {**base, "fx": {"2": {"zoom": zin, "speed": 1.5}}}, stitch=False, log=QUIET)
    check("fx: one move on any word of the clip lands on the clip", out[0].get("zoom") == zin and out[0].get("speed") == 1.5, out)
    page = open(os.path.join(ROOT, "product", "visual-editor", "editor.html"), encoding="utf-8").read()
    check("fx: the page plays the lowest word's move too (fxk)", "p.fxk = k" in page and "p.ids.find(i => fxE[i])" in page)
    check("fx: the page says a move as a speed or zoom change, never a trimmed edge", "speed or zoom change" in page)


def test_edits_in():
    check("edits: an empty Send changes nothing", not ve.edits_in({"cut": [], "back": [], "trims": {"s": {}, "e": {}}}))
    for k, v in (("cut", [1]), ("back", [2]), ("trims", {"s": {"3": 1.0}, "e": {}}), ("holes", [{"c": 0, "s": 1, "e": 2}]),
                 ("fx", {"1": {"zoom": None}})):
        check(f"edits: {k} is a change", ve.edits_in({k: v}))


def test_server_save_and_land():
    import visual_editor_server as srv
    jd = make_job("savejob")
    _, clips, segs, wid, cid = ve.load(jd)
    words = ve.kept_quiet(ve.words_of(clips), clips, segs)
    seg_of = ve.membership(words, clips, segs)
    ve._atomic_json(os.path.join(jd, "review", "script.json"),
                    {"job": "savejob", "id": wid, "cut_id": cid, "words": [{"k": s is not None} for s in seg_of], "clips": [{}]})
    ph = os.path.join(jd, "review", "phase.json")
    ve._atomic_json(ph, {"phase": "looks", "cut_id": cid})
    out = srv.save(jd, {"job": "savejob", "id": wid, "cut_id": cid, "cut": [], "back": []})
    check("lock: a Send with nothing in it keeps her cut locked in", os.path.exists(ph), out)
    check("landed: /save hands the page its receipt and when", out.get("receipt") and abs(out.get("at", 0) - time.time()) < 60, out)
    try:
        srv.save(jd, {"job": "savejob", "id": wid, "cut_id": "an-older-cut", "cut": [1], "back": []})
        check("stale: a Send from a page with an older cut is refused", False)
    except srv.Stale as e:
        check("stale: ... in plain words that say the page reloads", "Your cut was just updated" in str(e), str(e))
    check("stale: the refusal reaches the page as stale (it reloads)", '"stale": True' in inspect.getsource(srv.Handler._post))
    check("stale: an older cut's Send never wrote anything", os.path.exists(ph))
    # a real Send: phase 1 reopens, apply lands it, and /status's receipt is the one her page waits for
    real_sub, real_build = ve.subprocess, ve.build_script
    ve.subprocess = _fake_sub(lambda *a, **k: type("R", (), {"returncode": 0})()); ve.build_script = lambda job: None
    try:
        ve._atomic_json(ph, {"phase": "looks", "cut_id": cid})
        out = srv.save(jd, {"job": "savejob", "id": wid, "cut_id": cid, "cut": [1], "back": []})
        check("lock: a real edit reopens the Cut step", not os.path.exists(ph))
        ve.apply(jd, log=QUIET)
        la = ve.last_applied(jd)
        check("landed: the newest receipt is the one /save gave her page", la and la["receipt"] == out["receipt"], (la, out))
        check("landed: ... stamped no earlier than the save", la and la["at"] >= out["at"] - 2, (la, out))
        ve._atomic_json(ph, {"phase": "looks", "cut_id": cid})
        srv.save(jd, {"job": "savejob", "id": wid, "cut": [], "back": []})
        ve.apply(jd, log=QUIET)
        check("lock: an empty Send through apply keeps her lock too", os.path.exists(ph))
    finally:
        ve.subprocess, ve.build_script = real_sub, real_build
    check("landed: /status carries it", '"applied": ve.last_applied(jd)' in inspect.getsource(srv.Handler._get))
    check("landed: no receipt yet reads as none", ve.last_applied(make_job("fresh")) is None)


PAGE_FLOW = r"""
const { createRequire } = require("module");
const puppeteer = createRequire(process.env.PUP + "/")(process.env.PUP);
const ok = [], bad = [];
const check = (name, cond, detail) => (cond ? ok : bad).push(cond ? name : `${name}  -- ${detail === undefined ? "" : JSON.stringify(detail)}`);
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell", args: ["--no-sandbox"] });
  const errors = [];
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    page.on("pageerror", e => errors.push(String(e.message || e)));
    page.on("dialog", d => d.accept().catch(() => {}));       // "leave this page?" before a reload
    await page.goto(process.env.URL, { waitUntil: "networkidle2" }); await wait(800);
    check("page: the b-roll piece shows as seconds of no talking", await page.evaluate(() => D.words.filter(w => w.q).length >= 2));

    // fx: two words of one clip with opposite moves
    let r = await page.evaluate(() => { const p = spans[0], a = p.ids[0], b = p.ids[2];
      fxE = { [a]: { zoom: { from: 1, to: 1.15 } }, [b]: { zoom: null } }; recompute();
      const ch = changes(); return { keys: Object.keys(ch.fx), a, chips: $("changesSub").textContent }; });
    check("fx: one move per clip is sent (the one the preview plays)", r.keys.length === 1 && +r.keys[0] === r.a, r);
    check("fx: the chip says a speed or zoom change, not a trimmed edge", /1 speed or zoom change/.test(r.chips) && !/edge/.test(r.chips), r.chips);
    // once the engine's cut carries that zoom, the other word's older "no zoom" is never a change to send
    r = await page.evaluate(() => { const g = D.segs.find(x => x.w.includes(spans[0].ids[0])), was = g.z; g.z = { from: 1, to: 1.15 }; recompute();
      const n = Object.keys(changes().fx).length, act = $("send").dataset.act; if (was) g.z = was; else delete g.z; recompute(); return { n, act }; });
    check("fx: with the move landed, nothing is left to send (no flip-flop, Lock in shows)", r.n === 0 && r.act === "ready", r);
    r = await page.evaluate(() => { const p = spans[0], b = p.ids[2]; setFx(b, { zoom: null }, "No zoom");
      const keys = Object.keys(fxE).map(Number), sent = Object.keys(changes().fx).length; undo(); return { keys, b, sent, back: Object.keys(fxE).length }; });
    check("fx: a move set on another word of the clip replaces the clip's move", r.keys.length === 1 && r.keys[0] === r.b && r.sent === 0, r);
    check("fx: Undo brings back what was there", r.back === 2, r);
    await page.evaluate(() => { fxE = {}; recompute(); });

    // her draft on a NEW cut: what she sent is answered; only unsent changes carry; a quiet second goes by its moment
    r = await page.evaluate(() => {
      const i = D.words.findIndex(w => w.k && !w.q), j = D.words.findIndex((w, x) => x > i + 1 && w.k && !w.q), qi = D.words.findIndex(w => w.q && w.k);
      localStorage.setItem(KEY(), JSON.stringify({ v: 2, cut_id: "an-older-cut", keep: [[i, true], [j, true]], qk: [[D.words[qi].c, D.words[qi].s + 0.05, true]],
        fx: {}, sentSnap: { keep: [[i, true]], qk: [], fx: {} } }));
      dirty = false; return { i, j, qi }; });
    await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForFunction(() => typeof ready !== "undefined" && ready === true, { timeout: 20000 }); await wait(500);
    let s = await page.evaluate(({ i, j, qi }) => ({ ci: cut[i], cj: cut[j], cq: cut[qi], toast: $("toast").textContent }), r);
    check("draft: a change she sent that the new cut doesn't carry is never replayed", s.ci === false, s);
    check("draft: a change she hadn't sent rides onto the new cut", s.cj === true, s);
    check("draft: a second of no talking is matched by its moment, not its number", s.cq === true, s);
    check("draft: the page says which sent change the cut didn't take", /didn't take one change/.test(s.toast), s.toast);
    // an older draft (before this fix): its quiet seconds were numbered for a cut that's gone, so they stay off
    r = await page.evaluate(() => { const qi = D.words.findIndex(w => w.q && w.k);
      localStorage.setItem(KEY(), JSON.stringify({ cut_id: "an-older-cut", keep: [[qi, true]], fx: {} })); dirty = false; return { qi }; });
    await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForFunction(() => typeof ready !== "undefined" && ready === true, { timeout: 20000 }); await wait(500);
    s = await page.evaluate(({ qi }) => ({ cq: cut[qi] }), r);
    check("draft: an older draft's numbered quiet second is not replayed on a new cut", s.cq === false, s);

    // a Send that came back as the same cut: said, and the page offers Lock in, never Send again
    s = await page.evaluate(() => { cut = D.words.map(w => !w.k); fxE = {}; trimS = {}; trimE = {}; holes = []; tsplit = []; recompute();
      const i = D.words.findIndex(w => w.k && !w.q); cut[i] = true; recompute(); sentSnap = snapSent(); sentReceipt = sigOf(changes());
      sendLanded(); return { edits: hasEdits(), act: $("send").dataset.act, toast: $("toast").textContent }; });
    check("landed: a Send the cut didn't take leaves nothing to send", !s.edits && s.act === "ready", s);
    check("landed: ... and says so in plain words", /didn't take one change/.test(s.toast), s.toast);

    // a Send that never arrives (no receipt, no problem): said, never a silent loop
    s = await page.evaluate(async () => { const i = D.words.findIndex(w => w.k && !w.q); cut[i] = true; recompute();
      pendingSend = { rid: "ZZZZZZ", at: Date.now() / 1000, miss: 0, t0: Date.now() - 10000 };
      await heartbeat(); await heartbeat();
      return { shown: !$("problemnote").hidden, text: $("problemText").textContent, pend: pendingSend, act: $("send").dataset.act }; });
    check("lost: a Send that never reached her cut is said on the page", s.shown && /didn't reach your cut/.test(s.text) && s.pend === null, s);
    check("lost: ... and Send is offered again", s.act === "send", s);

    // a Send from a page whose cut Claude has changed since: refused as stale, so the page reloads onto the new cut
    s = await page.evaluate(async () => post("/save", { job: D.job, id: D.id, cut_id: "an-older-cut", cut: [], back: [] }));
    check("stale: an older page's Send is refused as stale, in plain words", !s.ok && s.stale && /Your cut was just updated/.test(s.why), s);

    // a real Send lands: the page sees its receipt arrive and switches onto the new cut
    s = await page.evaluate(async () => { localProblem = null; cut = D.words.map(w => !w.k); const i = D.words.findIndex(w => w.k && !w.q); cut[i] = true; recompute();
      const was = D.cut_id; await sendCut(); return { pend: pendingSend && pendingSend.rid, was }; });
    check("send: the page waits for the receipt /save gave it", !!s.pend, s);
    const t0 = Date.now(); let moved = false;
    while (Date.now() - t0 < 20000 && !moved) { await wait(500); moved = await page.evaluate(was => !!D && D.cut_id !== was && !hasEdits(), s.was).catch(() => false); }
    check("send: it lands, and the page is on the new cut with nothing left to send", moved);
    check("page: no script errors", errors.length === 0, errors);
  } catch (e) { bad.push("page flow stopped: " + (e && e.stack || e) + " " + JSON.stringify(errors)); }
  await browser.close();
  console.log(JSON.stringify({ ok, bad }));
})();
"""


def test_page():
    try:
        import test_visual_editor_page as tvp
    except Exception as e:
        check("page: the page test's tools load", False, e)
        return
    tools = tvp.find_tools()
    if not tools or not shutil.which("ffmpeg"):
        print("test_send_cut_lands: browser part skipped (no headless browser or ffmpeg here); the engine checks ran.")
        return
    node, pup, chrome = tools
    import visual_editor_server as srv
    proj = os.path.join(TMP, "projects")
    jd = os.path.join(proj, "landjob")
    for d in ("raw", "transcript", "review", "outputs"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=30", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", "11", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    os.path.join(jd, "raw", "a.mov")], check=True)
    json.dump({"clips": [{"clip": "a.mov", "path": "", "duration": 11, "words": WORDS}]},
              open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    json.dump({"segments": SEGS}, open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    shutil.copyfile(os.path.join(jd, "raw", "a.mov"), os.path.join(jd, "outputs", "landjob.mp4"))
    real_dir, real_sub = ve.job_dir, ve.subprocess
    ve.job_dir = lambda job: jd if os.path.basename(str(job)) == "landjob" else real_dir(job)
    ve.USER_STYLE = os.path.join(TMP, "user-style.json")
    ve.TOUR_FILE = os.path.join(TMP, "_local", "editor-tour.json")

    def stitch(cmd, **k):                                   # the lean stitch: the plan apply wrote becomes her cut
        if not any("stitch-cut" in str(c) for c in cmd):
            return real_sub.run(cmd, **k)                   # ffmpeg for the page's stills: the real thing
        plan = os.path.join(TMP, "reels-editing-engine", "landjob", "cuts.json")
        if os.path.isfile(plan):
            shutil.copyfile(plan, os.path.join(jd, "transcript", "cuts.json"))
        return type("R", (), {"returncode": 0})()
    srv.ve, srv.PROJECTS = ve, proj
    import premake
    real_sched = premake.schedule
    premake.schedule = lambda job, delay=0: None          # no background full-quality cut in a test
    httpd = None
    try:
        ve.prepare(jd, log=QUIET)
        ve.subprocess = _fake_sub(stitch)
        httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        script = os.path.join(TMP, "flow.js")
        open(script, "w", encoding="utf-8").write(PAGE_FLOW)
        env = dict(os.environ, PUP=pup, CHROME=chrome, URL=f"http://127.0.0.1:{port}/editor/?job=landjob")
        r = subprocess.run([node, script], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300, cwd=TMP)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            check("page: the browser run finished", False, (r.stdout[-1500:], r.stderr[-1500:]))
            return
        global total
        total += len(res["ok"])
        for name in res["bad"]:
            fails.append(name); total += 1
    finally:
        if httpd:
            httpd.shutdown()
        ve.job_dir, ve.subprocess, premake.schedule = real_dir, real_sub, real_sched


def main():
    try:
        test_wordless()
        test_fx_one_per_clip()
        test_edits_in()
        test_server_save_and_land()
        test_page()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if fails:
        print(f"test_send_cut_lands: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_send_cut_lands: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
