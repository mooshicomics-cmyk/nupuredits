#!/usr/bin/env python3
"""Guards: buyer reports on the visual editor PAGE, 2026-10-23 to 2026-10-26, each driven in a real (headless) browser.

  script.json     the page's own data failing to load once (the engine restarting) is tried again, and one that never
                  comes is written down for /report-a-problem, with a Reload button (the safety panel had no cause)
  stops by itself Play past the end of a preview copy shorter than her cut: the page said "playing" over a still
                  video at 0:00 (pressed play, it ran 0.1 s and paused itself); now it stops, says why, writes it down
  her voice       in every browser (Chrome and Safari both) her voice plays from the video itself, never through the
                  Web Audio graph: there it ran late against her picture by the graph's output delay (Safari, a buyer
                  2026-10-23; her lips ahead of her words while her stitched cut played in sync, a buyer 2026-10-26).
                  What her voice is still owed past 100% comes off her effects and music (the render's balance), and a
                  piece's edge mutes her voice on its own timer, back once the jump lands
  busy, logged    a "hold on, your last change is still being made" (409) is written down, never silent
  clean view      the eye (V) hides the "sits behind your head" note too, not only the tool bar, Snap and Preview
  every file      Add new and drag-and-drop take every file she gives, not just the first
  GIFs keep going several GIFs added at once: one that fails never stops the rest, the ones that landed show, and
                  she is told which one didn't go on
  Sandbox Back    Back from her waiting sketches never promises "fresh sketches" (the engine keeps them); it offers
                  Cancel this idea instead

Uses the same headless Chrome, puppeteer and throwaway reel as test_visual_editor_page.py; without them it says so
and passes.

Run: python3 product/tests/test_editor_page_reports_2026_10_26.py
"""
import base64, json, os, shutil, subprocess, sys, tempfile, threading
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
import test_visual_editor_page as base  # noqa: E402  (find_tools, make_reel)

GIF = base64.b64decode("R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")

FLOW = r"""
const { createRequire } = require("module");
const puppeteer = createRequire(process.env.PUP + "/")(process.env.PUP);
const ok = [], bad = [];
const check = (name, cond, detail) => (cond ? ok : bad).push(cond ? name : `${name}  -- ${detail === undefined ? "" : JSON.stringify(detail).slice(0, 600)}`);
const wait = ms => new Promise(r => setTimeout(r, ms));
const BASE = process.env.BASE, URL = process.env.URL;
const SAFARI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15";
(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell", args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required", "--disable-audio-output"] });
  const errors = [], logged = [];
  async function open(o = {}) {
    const page = await browser.newPage(); await page.setViewport({ width: 1280, height: 900 });
    page.on("pageerror", e => errors.push(String(e.message || e)));
    page.on("request", r => { if (r.url().includes("/log-error")) logged.push(String(r.postData() || "")); });
    if (o.ua) await page.setUserAgent(o.ua);
    await page.evaluateOnNewDocument(() => {                 // every element routed into Web Audio, by id
      window.__mes = []; const C = window.AudioContext || window.webkitAudioContext; if (!C) return;
      const f = C.prototype.createMediaElementSource;
      C.prototype.createMediaElementSource = function (el) { window.__mes.push(el.id || el.tagName); return f.call(this, el); };
    });
    if (o.intercept) { await page.setRequestInterception(true); page.on("request", r => { if (!o.intercept(r)) r.continue(); }); }
    await page.goto(URL, { waitUntil: "domcontentloaded" });
    if (o.ready !== false) { await page.waitForFunction(() => typeof ready !== "undefined" && ready, { timeout: 30000 }).catch(() => {}); await wait(600); }
    return page;
  }
  const until = async (page, fn, ms = 20000, arg) => { const end = Date.now() + ms; let v; while (Date.now() < end) { v = await page.evaluate(fn, arg).catch(() => null); if (v) return v; await wait(150); } return v; };
  const fail503 = r => r.respond({ status: 503, contentType: "text/plain", body: "restarting" });
  try {
    // ── script.json: once failed, tried again; never back, written down, with Reload ──
    let n = 0;
    const p1 = await open({ intercept: r => /\/script\.json/.test(r.url()) && n++ < 2 ? (fail503(r), true) : false });
    const up = await until(p1, () => !$("p-editor").hidden && $("safety").hidden, 15000);
    check("script.json: two failed loads (the engine restarting) are tried again and her editor opens", !!up, { tries: n });
    await p1.close();
    const before = logged.length;
    const p2 = await open({ ready: false, intercept: r => /\/script\.json/.test(r.url()) ? (fail503(r), true) : false });
    const safe = await until(p2, () => !$("safety").hidden, 30000);
    await wait(400);
    const why = logged.slice(before).join(" ");
    check("script.json: one that never loads shows the safety panel", !!safe);
    check("script.json: and the reason is written down for /report-a-problem", /script\.json/.test(why) && /503/.test(why), why);
    check("script.json: the safety panel offers Reload", await p2.evaluate(() => !!$("safetyReload") && !$("safetyReload").hidden).catch(() => false));
    await p2.close();

    // ── her voice in Chrome goes through the sound graph (the control), in Safari from the video itself ──
    const pc = await open();
    await pc.click("#play"); await wait(700);
    const cr = await pc.evaluate(() => { const r = { routed: window.__mes.slice(), playing, paused: v.paused, vol: v.volume }; stop(); return r; });
    check("Chrome: her voice plays from the video itself, never through the Web Audio graph", !cr.routed.includes("v") && cr.playing && !cr.paused && cr.vol > 0, cr);
    const bal = await pc.evaluate(async () => {                          // her voice owed +6 dB past 100%: off her sounds instead
      pbVoice(6); pbBus(); const up = { vol: v.volume, trim: PB.trim && PB.trim.gain.value };
      pbVoice(-6); const down = { vol: v.volume, trim: PB.trim && PB.trim.gain.value };
      pbVoice('mute'); const mute = { vol: v.volume, trim: PB.trim && PB.trim.gain.value }; pbVoice(0);
      return { up, down, mute }; });
    const near = (a, b) => Math.abs(a - b) < 0.01;
    check("balance: a voice owed more than 100% plays at 100% and her sounds come down by the rest",
          near(bal.up.vol, 1) && near(bal.up.trim, Math.pow(10, -6 / 20)), bal);
    check("balance: a voice louder than her cut is turned down and her sounds stay as built",
          near(bal.down.vol, Math.pow(10, -6 / 20)) && near(bal.down.trim, 1) && bal.mute.vol === 0 && near(bal.mute.trim, 1), bal);
    const edge = await pc.evaluate(async () => {                         // a piece's edge mutes her voice on its own timer
      playing = true; pbOpen(); pbEdge(0.06); const before = v.muted;
      await new Promise(r => setTimeout(r, 160)); const at = v.muted; pbOpen(); const back = v.muted; playing = false;
      return { before, at, back }; });
    check("edge: her voice is muted right at a piece's end and back once the jump lands", !edge.before && edge.at && !edge.back, edge);
    // ── busy (409) is written down ──
    await pc.setRequestInterception(true);
    pc.on("request", r => {
      if (r.url().includes("/sound-toggle")) return r.respond({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "Hold on a moment, your last change is still being made.", busy: true }) });
      if (r.url().includes("/sound-nudge")) return r.respond({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "Your export is running. Make this change when it's done, or stop the export first." }) });
      r.continue();
    });
    const b0 = logged.length;
    const said = await pc.evaluate(async () => [await post("/sound-toggle", {}), await post("/sound-nudge", {})]);
    await wait(500);
    const busyLog = logged.slice(b0).join(" ");
    check("busy: the page still hears the reason (shown by the caller)", said[0].busy && /Hold on/.test(said[0].why) && /export is running/.test(said[1].why), said);
    check("busy: a 'last change is still being made' 409 is written down", /busy/.test(busyLog) && /sound-toggle/.test(busyLog), busyLog);
    check("busy: an 'export is running' 409 is written down", /sound-nudge/.test(busyLog) && /export is running/.test(busyLog), busyLog);
    check("busy: and written down as something she was told, never as an error", logged.slice(b0).length >= 2 && logged.slice(b0).every(l => JSON.parse(l).kind === "told"), logged.slice(b0));
    await pc.close();
    const ps = await open({ ua: SAFARI });
    await ps.click("#play"); await wait(700);
    const sf = await ps.evaluate(() => { const r = { routed: window.__mes.slice(), playing, paused: v.paused, vol: v.volume }; stop(); return r; });
    check("Safari: her voice plays from the video itself, never through the Web Audio graph", !sf.routed.includes("v") && sf.playing && !sf.paused && sf.vol > 0, sf);
    await ps.close();

    // ── Play past the end of a preview shorter than her cut ──
    await (await fetch(BASE + "/__short_preview")).text();
    const pv = await open();
    await until(pv, () => v.readyState >= 1 && isFinite(v.duration));
    const dur = await pv.evaluate(() => v.duration);
    const l0 = logged.length;
    await pv.evaluate(() => seekCut(6)); await wait(400);
    await pv.click("#play"); await wait(4500);
    const st = await pv.evaluate(() => ({ playing, paused: v.paused, ended: v.ended, t: v.currentTime, head: cutPos(),
      said: [($("vidshort") || {}).textContent || "", $("toast").hidden ? "" : $("toast").textContent].join(" ") }));
    const stuckLog = logged.slice(l0).join(" ");
    check("stops by itself: the test preview is shorter than her cut", dur < 5, dur);
    check("stops by itself: never 'playing' over a stopped video", !(st.playing && st.paused), st);
    check("stops by itself: she is told her preview is shorter than her cut", /preview/i.test(st.said) && /shorter|ends/i.test(st.said), st.said);
    check("stops by itself: it is written down with the numbers", /preview/.test(stuckLog) && /long/.test(stuckLog), stuckLog);
    await pv.close();
    await (await fetch(BASE + "/__full_preview")).text();

    // ── Visuals ──
    await (await fetch(BASE + "/__phase_looks")).text();
    const page = await open();
    await until(page, () => sec === "visuals" && looksOn);
    const flag = await page.evaluate(() => {
      toolsShow(false); $("lookFlag").hidden = false; const off = getComputedStyle($("lookFlag")).display;
      toolsShow(true); const on = getComputedStyle($("lookFlag")).display; $("lookFlag").hidden = true; return { off, on }; });
    check("clean view: the eye hides the 'sits behind your head' note", flag.off === "none", flag);
    check("clean view: the note is back when the tools are", flag.on !== "none", flag);

    // every file she gives
    await page.evaluate(() => openMedia(0)); await until(page, () => !$("mediaSheet").hidden && $("mdGrid").children.length);
    const ups = [];
    page.on("request", r => { if (r.url().includes("/favorite-upload")) ups.push(r.url()); });
    check("every file: Add new lets her pick several files", await page.evaluate(() => $("mdFile").multiple));
    const inp = await page.$("#mdFile");
    await inp.uploadFile(process.env.GIF1, process.env.GIF2).catch(e => errors.push("uploadFile: " + e.message));
    await until(page, () => mdPicks.length >= 2, 10000);
    const picked = await page.evaluate(() => mdPicks.map(x => x.id));
    check("every file: Add new saves every file she picked, and picks them all", ups.length === 2 && picked.length === 2, { ups: ups.length, picked });
    ups.length = 0;
    await page.evaluate(gif => {
      const bin = Uint8Array.from(atob(gif), c => c.charCodeAt(0)), dt = new DataTransfer();
      ["drop-one.gif", "drop-two.gif"].forEach(n => dt.items.add(new File([bin], n, { type: "image/gif" })));
      $("mdGrid").dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    }, process.env.GIFB64);
    await until(page, () => mdPicks.some(x => /drop-two/.test(x.id)), 10000);
    check("every file: dropping two files saves both", ups.length === 2, ups.length);

    // GIFs keep going past one that fails
    const names = await page.evaluate(() => { mdPicks = mdPicks.filter(x => /drop-/.test(x.id)).slice(0, 2); mdPick = mdPicks[0]; mdMarks(); mdReady(); return mdPicks.map(x => x.name); });
    let placeN = 0;
    await page.setRequestInterception(true);
    page.on("request", r => {
      if (r.url().includes("/place-media") && placeN++ === 0) return r.respond({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "That one couldn't go on." }) });
      r.continue();
    });
    const layers0 = await page.evaluate(() => LOOKS.layers.length);
    await page.click("#mdGo");
    const landed = await until(page, l => LOOKS && looksOn && LOOKS.layers.length > l ? LOOKS.layers.length : null, 20000, layers0);
    const gifSaid = await page.evaluate(() => $("toast").hidden ? "" : $("toast").textContent);
    check("GIFs: one that fails never stops the next", placeN === 2, placeN);
    check("GIFs: the one that landed shows on her reel (looks reloaded)", !!landed, { layers0, landed });
    check("GIFs: she is told which one didn't go on", gifSaid.includes(names[0]) && /couldn't go on|didn't go on/.test(gifSaid), { gifSaid, names });

    // Sandbox: Back from waiting sketches
    const sb = await page.evaluate(() => {
      LOOKS.ideas = [{ id: "t1", mode: "sandbox", status: "takes", takes: ["sk-a", "sk-b", "sk-c"], idea: "a bouncing title", w: 0, start: 0, end: 1 }];
      closeSheets(); openSheet("sandboxSheet"); sbEditing = true; $("sbIdea").value = "a bouncing title"; sbGo("ask");
      const r = { sub: $("sbxSub").textContent, cancel: !$("sbCancel").hidden };
      LOOKS.ideas = []; closeSheets(); return r; });
    check("Sandbox Back: never promises fresh sketches while hers are waiting", !/fresh sketches/i.test(sb.sub) && /Remix/.test(sb.sub), sb);
    check("Sandbox Back: Cancel this idea is right there", sb.cancel, sb);
    check("no script error on the page", !errors.length, errors);
  } catch (e) { bad.push("the walk itself broke: " + (e.stack || e)); }
  await browser.close();
  console.log(JSON.stringify({ ok, bad }));
})();
"""


def main():
    tools = base.find_tools()
    if not tools or not shutil.which("ffmpeg"):
        print("test_editor_page_reports_2026_10_26: skipped (no headless browser or ffmpeg here).")
        return 0
    node, pup, chrome = tools
    tmp = tempfile.mkdtemp(prefix="ve-page-1026-")
    try:
        import visual_editor as ve
        import visual_editor_server as srv
        import sound_plan, favorites_folder, capcut_sfx, lookbook
        proj = os.path.join(tmp, "projects")
        jd = base.make_reel(proj)
        real_dir = ve.job_dir
        ve.job_dir = lambda job: jd if os.path.basename(str(job)) == "pagejob" else real_dir(job)
        ve.can_behind = lambda: False
        sound_plan.job_dir = lambda job: jd if os.path.basename(str(job)) == "pagejob" else job
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
        ve.USER_STYLE = os.path.join(tmp, "user-style.json")
        ve.TOUR_FILE = os.path.join(tmp, "_local", "editor-tour.json")
        srv.ve, srv.PROJECTS = ve, proj
        ve.prepare(jd, log=lambda *a: None)
        pv = os.path.join(jd, "review", "preview.mp4")
        shutil.copyfile(pv, pv + ".full")
        gifs = []
        for nm in ("pick-one.gif", "pick-two.gif"):
            gifs.append(os.path.join(tmp, nm))
            open(gifs[-1], "wb").write(GIF)
        Base = srv.Handler

        class Handler(Base):                                  # test-only doors
            def do_GET(self):
                if self.path == "/__phase_looks":             # lock the cut in (Cut step -> Visuals)
                    cid = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")).get("cut_id")
                    ve._atomic_json(os.path.join(jd, "review", "phase.json"), {"phase": "looks", "cut_id": cid})
                    ve.looks_manifest(jd)
                    return self._json(200, {"ok": True})
                if self.path == "/__short_preview":           # a preview copy shorter than her cut (3 s of 11)
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pv + ".full", "-t", "3", "-c", "copy",
                                    "-movflags", "+faststart", pv + ".short.mp4"], check=True)
                    os.replace(pv + ".short.mp4", pv)
                    return self._json(200, {"ok": True})
                if self.path == "/__full_preview":
                    shutil.copyfile(pv + ".full", pv)
                    return self._json(200, {"ok": True})
                return Base.do_GET(self)

        httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        script = os.path.join(tmp, "flow.js")
        open(script, "w", encoding="utf-8").write(FLOW)
        env = dict(os.environ, PUP=pup, CHROME=chrome, BASE=f"http://127.0.0.1:{port}",
                   URL=f"http://127.0.0.1:{port}/editor/?job=pagejob", GIF1=gifs[0], GIF2=gifs[1],
                   GIFB64=base64.b64encode(GIF).decode())
        r = subprocess.run([node, script], capture_output=True, text=True, encoding="utf-8", env=env, timeout=400, cwd=tmp)
        httpd.shutdown()
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            print("test_editor_page_reports_2026_10_26: the browser run didn't finish\n", r.stdout[-2000:], r.stderr[-2000:])
            return 1
        for name in res["ok"]:
            print("  PASS ", name)
        for name in res["bad"]:
            print("  FAIL ", name)
        total = len(res["ok"]) + len(res["bad"])
        if res["bad"]:
            print(f"test_editor_page_reports_2026_10_26: {len(res['bad'])} of {total} checks FAILED")
            return 1
        print(f"test_editor_page_reports_2026_10_26: all {total} checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_editor_page_reports_2026_10_26():                       # pytest entry
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
