#!/usr/bin/env python3
"""Guards: two buyer reports on the visual editor's PLAYER, driven in a real (headless) browser.

  scroll away     while her reel plays, the script follows the word being said only while she reads along. She
                  scrolled up to watch her reel and the page pulled her straight back down to the words, again and
                  again (a wide reel, whose player sits above the script, v2.3.13). Her own scroll while it plays
                  holds the following until she presses play again or taps a word; a scroll the page makes itself
                  never counts; and a lit word is never chased when the word before it was already off her screen
  smooth zoom     a clip's Zoom move is set once for each frame the video shows, at that frame's own time, the way
                  the render gives every frame its own scale. It was set from the page's 25 ms timer (40 steps a
                  second against 30 frames and a 60 Hz screen, late whenever the timer was): a push-in smooth in her
                  export shook in her preview (v2.3.13)

Uses the same headless Chrome, puppeteer and throwaway reel as test_visual_editor_page.py; without them it says so
and passes.

Run: python3 product/tests/test_editor_follow_zoom_2026_10_28.py
"""
import json, os, shutil, subprocess, sys, tempfile, threading
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
import test_visual_editor_page as base  # noqa: E402  (find_tools, make_reel)

FLOW = r"""
const { createRequire } = require("module");
const puppeteer = createRequire(process.env.PUP + "/")(process.env.PUP);
const ok = [], bad = [];
const check = (name, cond, detail) => (cond ? ok : bad).push(cond ? name : `${name}  -- ${detail === undefined ? "" : JSON.stringify(detail).slice(0, 600)}`);
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell", args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required", "--disable-audio-output"] });
  const errors = [];
  try {
    const page = await browser.newPage(); await page.setViewport({ width: 1280, height: 700 });
    page.on("pageerror", e => errors.push(String(e.message || e)));
    await page.goto(process.env.URL, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => typeof ready !== "undefined" && ready, { timeout: 30000 }).catch(() => {});
    await wait(600);

    // ── the script follows only while she reads along ──
    const fol = await page.evaluate(() => {
      const calls = [], orig = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function () { calls.push(this.dataset && this.dataset.i); };
      const ids = Object.keys(wordEls).map(Number).sort((a, b) => a - b), a = ids[0], b = ids[1];
      const H = innerHeight, at = (el, y) => { el.getBoundingClientRect = () => ({ top: y, bottom: y + 20, left: 0, right: 50, width: 50, height: 20 }); };
      const out = {};
      followHeld = false;
      at(wordEls[a], H * 0.6); at(wordEls[b], H + 300); lit = b; calls.length = 0; followScroll(a);
      out.reading = calls.length;                                    // the word before on screen, the new one below it: follows
      at(wordEls[a], -900); calls.length = 0; followScroll(a);
      out.away = calls.length;                                        // she scrolled up and away: the word before is off screen
      at(wordEls[a], H * 0.6); followHeld = true; calls.length = 0; followScroll(a);
      out.held = calls.length;                                        // she scrolled by hand while it played
      followHeld = false; delete wordEls[a].getBoundingClientRect; delete wordEls[b].getBoundingClientRect;
      Element.prototype.scrollIntoView = orig; lit = -1;
      return out;
    });
    check("follow: reading along, the next word below her screen is scrolled to", fol.reading === 1, fol);
    check("follow: once she has scrolled away from the words, the page never pulls her back", fol.away === 0, fol);
    check("follow: held after her own scroll", fol.held === 0, fol);

    const hand = await page.evaluate(async () => {
      document.body.style.minHeight = "6000px"; scrollTo(0, 0); await new Promise(r => setTimeout(r, 500));
      const out = {}; playing = true; followHeld = false;
      scrollTo(0, 200); await new Promise(r => setTimeout(r, 120));   // the page scrolling itself
      out.self = followHeld;
      dispatchEvent(new WheelEvent("wheel", { deltaY: -300, bubbles: true })); scrollTo(0, 50); await new Promise(r => setTimeout(r, 120));
      out.wheel = followHeld;                                          // her wheel, and the page moved
      followHeld = false; await new Promise(r => setTimeout(r, 500));
      dispatchEvent(new KeyboardEvent("keydown", { key: "PageDown", bubbles: true })); scrollTo(0, 400); await new Promise(r => setTimeout(r, 120));
      out.key = followHeld;
      playing = false; followHeld = false; await new Promise(r => setTimeout(r, 500));
      dispatchEvent(new WheelEvent("wheel", { deltaY: 300, bubbles: true })); scrollTo(0, 600); await new Promise(r => setTimeout(r, 120));
      out.paused = followHeld;                                         // paused: nothing to hold
      followHeld = true; seekWord(Object.keys(wordEls).map(Number)[1]); out.tap = followHeld;
      followHeld = true; start(); out.play = followHeld; stop();
      scrollTo(0, 0); document.body.style.minHeight = "";
      return out;
    });
    check("follow: a scroll the page makes itself never holds it", hand.self === false, hand);
    check("follow: her wheel or trackpad scroll while it plays holds it", hand.wheel === true, hand);
    check("follow: her scroll keys while it plays hold it", hand.key === true, hand);
    check("follow: scrolling while paused holds nothing", hand.paused === false, hand);
    check("follow: tapping a word follows again", hand.tap === false, hand);
    check("follow: pressing play follows again", hand.play === false, hand);

    // ── her Zoom is set for each frame the video shows ──
    const zm = await page.evaluate(async () => {
      stop(); seekCut(0);
      spans.forEach(sp => { sp.z = { from: 1, to: 1.15, ease: "inOut" }; });
      const rec = [], f = fxView;
      fxView = function (at) { if (playing) rec.push({ at: at == null ? null : at, cur: v.currentTime }); return f(at); };
      start(); await new Promise(r => setTimeout(r, 1500));
      const scale = (v.style.transform.match(/scale\(([\d.]+)\)/) || [])[1];
      stop(); fxView = f; spans.forEach(sp => { delete sp.z; }); fxView();
      const timed = rec.filter(x => x.at != null), ats = timed.map(x => x.at);
      return { n: rec.length, timer: rec.length - timed.length, frames: timed.length, rising: ats.every((t, i) => !i || t >= ats[i - 1] - 1e-6),
               scale: scale ? +scale : null, cleared: !v.style.transform };
    });
    check("zoom: while it plays, the scale is set from each frame the video shows", zm.frames >= 10, zm);
    check("zoom: never from the page's timer while it plays", zm.timer === 0, zm);
    check("zoom: frame by frame in order, never a step back", zm.rising, zm);
    check("zoom: the push-in is on the picture", zm.scale > 1 && zm.scale <= 1.15, zm);
    check("zoom: a clip with no move shows no zoom", zm.cleared, zm);
    check("no script error on the page", errors.length === 0, errors);
  } catch (e) {
    bad.push("the browser run stopped: " + (e && e.stack || e));
  } finally {
    await browser.close();
    console.log(JSON.stringify({ ok, bad }));
  }
})();
"""


def main():
    tools = base.find_tools()
    if not tools or not shutil.which("ffmpeg"):
        print("test_editor_follow_zoom_2026_10_28: skipped (no headless browser or ffmpeg here).")
        return 0
    node, pup, chrome = tools
    tmp = tempfile.mkdtemp(prefix="ve-follow-zoom-")
    try:
        import visual_editor as ve
        import visual_editor_server as srv
        import sound_plan, lookbook
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
        sound_plan.PROJECTS_DIR = proj
        lookbook.ROOT = tmp
        ve.USER_STYLE = os.path.join(tmp, "user-style.json")
        ve.TOUR_FILE = os.path.join(tmp, "_local", "editor-tour.json")
        srv.ve, srv.PROJECTS = ve, proj
        ve.prepare(jd, log=lambda *a: None)
        httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        script = os.path.join(tmp, "flow.js")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(FLOW)
        env = dict(os.environ, PUP=pup, CHROME=chrome, URL=f"http://127.0.0.1:{port}/editor/?job=pagejob")
        r = subprocess.run([node, script], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300, cwd=tmp)
        httpd.shutdown()
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            print("test_editor_follow_zoom_2026_10_28: the browser run didn't finish\n", r.stdout[-2000:], r.stderr[-2000:])
            return 1
        for name in res["ok"]:
            print("  PASS ", name)
        for name in res["bad"]:
            print("  FAIL ", name)
        total = len(res["ok"]) + len(res["bad"])
        if res["bad"]:
            print(f"test_editor_follow_zoom_2026_10_28: {len(res['bad'])} of {total} checks FAILED")
            return 1
        print(f"test_editor_follow_zoom_2026_10_28: all {total} checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_editor_follow_zoom_2026_10_28():                         # pytest entry
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
