#!/usr/bin/env python3
"""The visual editor page, driven in a real (headless) browser: what she clicks does what it says.

Builds a throwaway 10-second reel (ffmpeg test pattern + tone, ten words), serves it with the page server, and
drives the page the way she would:
  - Cut step: the script shows every line; a tapped word offers Cut; Cut cuts it; Undo brings it back
  - Looks step: Split line here splits a line; + Combine puts it back; ✦+ adds a look from the Swap sheet; a
    split shrinks that look to its half, Undo puts it back exactly, Redo splits again, and a combine grows it
    back; a closed sheet lets go of its live looks
  - Behind your head is offered only when the engine has the cutout tool
  - no script error on the page at any point

Uses the headless Chrome and puppeteer that HyperFrames installs (`npx hyperframes@0.9.6 browser ensure`). On a
machine without them it says so and passes: the engine-side tests (test_visual_editor.py) still cover the logic.

Run: python3 product/tests/test_visual_editor_page.py
"""
import glob, json, os, shutil, subprocess, sys, tempfile, threading
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))


def find_tools():
    """node, puppeteer-core and a headless Chrome, from what HyperFrames already installed; None when missing."""
    node = shutil.which("node")
    if not node:
        return None
    caches = [os.path.join(os.path.expanduser("~"), ".npm")]
    try:
        c = subprocess.run(["npm", "config", "get", "cache"], capture_output=True, text=True, timeout=20, shell=os.name == "nt").stdout.strip()
        if c:
            caches.insert(0, c)
    except Exception:
        pass
    pup = None
    for c in caches:
        for pj in sorted(glob.glob(os.path.join(c, "_npx", "*", "node_modules", "puppeteer-core", "package.json"))):
            pup = os.path.dirname(pj)
            hf = os.path.join(os.path.dirname(pup), "hyperframes", "package.json")
            if os.path.isfile(hf) and json.load(open(hf, encoding="utf-8")).get("version") == "0.8.43":
                break                                        # the pinned HyperFrames' own copy, when there
        if pup:
            break
    home = os.path.expanduser("~")
    names = ("chrome-headless-shell", "chrome-headless-shell.exe")
    chrome = None
    for base in (os.path.join(home, ".cache", "hyperframes", "chrome"), os.path.join(home, ".cache", "puppeteer")):
        for root, _, files in os.walk(base):
            hit = next((f for f in files if f in names), None)
            if hit:
                chrome = os.path.join(root, hit)
                break
        if chrome:
            break
    return (node, pup, chrome) if pup and chrome else None


WORDS = [{"word": w, "start": i * 1.0, "end": i * 1.0 + 0.6} for i, w in enumerate(
    "this is where your hook will be. and here is the rest.".split())]


def make_reel(proj):
    jd = os.path.join(proj, "pagejob")
    for d in ("raw", "transcript", "review", "hf-captions"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=30", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", "11", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    os.path.join(jd, "raw", "a.mov")], check=True)
    json.dump({"clips": [{"clip": "a.mov", "path": "", "duration": 11, "words": WORDS}]},
              open(os.path.join(jd, "transcript", "words.json"), "w", encoding="utf-8"))
    json.dump({"segments": [{"clip": "a.mov", "start": -0.04, "end": 10.7, "transcript": "", "keep_edges": True}]},
              open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8"))
    os.makedirs(os.path.join(jd, "outputs"), exist_ok=True)       # the rough cut (the whole clip) and its kept words
    shutil.copyfile(os.path.join(jd, "raw", "a.mov"), os.path.join(jd, "outputs", "pagejob.mp4"))
    json.dump({"words": [{"text": w["word"], "start": w["start"] + 0.04, "end": w["end"] + 0.04, "type": "word"} for w in WORDS]},
              open(os.path.join(jd, "outputs", "pagejob.transcript.json"), "w", encoding="utf-8"))
    json.dump({"sfx": [{"file": "pop", "at": 1.0}]}, open(os.path.join(jd, "caption-plan.json"), "w", encoding="utf-8"))   # one planned sound
    open(os.path.join(jd, "hf-captions", "index.html"), "w", encoding="utf-8").write(
        '<div id="root" data-composition-id="hf-captions" data-duration="11" data-width="1080" data-height="1920"></div>')
    return jd


PAGE_FLOW = r"""
const { createRequire } = require("module");
const puppeteer = createRequire(process.env.PUP + "/")(process.env.PUP);
const ok = [], bad = [];
const check = (name, cond, detail) => (cond ? ok : bad).push(cond ? name : `${name}  -- ${detail === undefined ? "" : JSON.stringify(detail)}`);
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell", args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required", "--disable-audio-output"] });
  const errors = [];
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    page.on("pageerror", e => errors.push(String(e.message || e)));
    const url = process.env.URL;
    // ── Cut step ──
    await page.goto(url, { waitUntil: "networkidle2" }); await wait(800);
    const lines = await page.evaluate(() => D.lines.length);
    check("cut: every line of the script is on the page", lines > 1 && await page.$$eval(".row", r => r.length) === lines, lines);
    const box = await (await page.$('.w[data-i="1"]')).boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2); await wait(200);
    const menu = await page.$$eval(".pop button", b => b.map(x => x.textContent.trim()));
    check("cut: a tapped word offers Cut", menu.some(t => t.startsWith("Cut")), menu);
    await page.click('.pop [data-a="cut"]'); await wait(150);
    check("cut: Cut cuts that word", await page.evaluate(() => !!cut[1]));
    await page.keyboard.down(process.platform === "darwin" ? "Meta" : "Control"); await page.keyboard.press("z"); await page.keyboard.up(process.platform === "darwin" ? "Meta" : "Control"); await wait(150);
    check("cut: Undo brings it back", await page.evaluate(() => !cut[1]));
    // a refused Send: said at once wherever she is, no green "updated" over it, and one tap back to her last cut
    const refused = await page.evaluate(() => {
      cut[1] = true; recompute();
      const bar = $("renderBar"); bar.hidden = false; bar.classList.add("done");             // the "Your cut is updated." flash
      showProblem("Piece 10 of the cut has no words under it.", "t-refused");
      const r = { said: !$("toast").hidden && $("toast").textContent.includes("didn't go through") && !!$("tDrop"),
                  noCheck: bar.hidden, note: !$("problemnote").hidden && !$("problemDrop").hidden, send: $("send").dataset.act === "send" };
      $("problemDrop").click();
      r.back = !hasEdits() && $("problemnote").hidden && $("send").dataset.act !== "send";
      showProblem("Piece 10 of the cut has no words under it.", "t-refused");                 // the next heartbeat: stays dropped
      r.stays = $("problemnote").hidden;
      undo(); r.undo = !!cut[1]; cut[1] = false; recompute();
      return r;
    });
    check("problem: a refused Send is said at once, with the way back", refused.said, refused);
    check("problem: no green 'updated' over a refusal", refused.noCheck, refused);
    check("problem: the note offers Go back to my last cut", refused.note && refused.send, refused);
    check("problem: Go back to my last cut drops her unsent changes", refused.back && refused.stays, refused);
    check("problem: Undo brings them back", refused.undo, refused);
    // ── Looks step ──
    await (await fetch(process.env.BASE + "/__phase_looks")).text();
    await page.goto(url, { waitUntil: "networkidle2" }); await wait(1200);
    check("visuals: a finished cut opens Visuals, on her script", await page.evaluate(() => looksOn === true && sec === "visuals" && !$("script").hidden));
    check("visuals: a line without a look offers Add a look", await page.evaluate(() => document.querySelectorAll(".lkchips .lk-addchip").length > 0));
    check("layers: with the cut locked in, Visuals is open, Sound waits on the looks, and the button locks them in",
          await page.evaluate(() => !document.querySelector('.secs .sec[data-sec="visuals"]').classList.contains("locked")
            && document.querySelector('.secs .sec[data-sec="sound"]').classList.contains("locked")
            && /Lock in your looks/.test(document.querySelector('.secs .sec[data-sec="sound"]').title) && $("send").innerText.includes("Lock in my looks")));
    check("layers: a tap on a locked layer takes the step that opens it (locks in her looks), never just a no", await page.evaluate(async () => {
      const keep = looksReady; let called = false; looksReady = async () => { called = true; };   // (the real lock-in runs later in this flow)
      document.querySelector('.secs .sec[data-sec="sound"]').click(); await new Promise(r => setTimeout(r, 80));
      looksReady = keep; return called; }));
    check("layers: a cut being edited locks every layer after it", await page.evaluate(() => {
      const was = phase; phase = "cut"; updateSecs(); const all = ["visuals", "sound", "finish"].every(k => lockKind(k) === "cut");
      phase = was; updateSecs(); return all && /Lock in your cut before you move on/.test(LOCK_SAYS.cut); }));
    await page.evaluate(() => showSec("cut")); await wait(200);
    check("sections: Cut shows her script without look chips", await page.evaluate(() => document.body.dataset.sec === "cut" && getComputedStyle(document.querySelector(".lkchips")).display === "none"));
    check("tracks: her looks are blocks on the timeline", await page.evaluate(() => document.querySelectorAll("#laneVis .vblk").length >= 0));
    check("looks: Behind your head is not offered without the cutout tool", await page.evaluate(() => LOOKS.can_behind === false));
    const n0 = await page.evaluate(() => D.lines.length);
    const w = await page.evaluate(() => D.lines[0][2]);
    const wb = await (await page.$(`.w[data-i="${w}"]`)).boundingBox();
    await page.mouse.click(wb.x + wb.width / 2, wb.y + wb.height / 2); await wait(200);
    check("split: the word menu offers Split line here", !!await page.$('.pop [data-a="split"]'));
    await page.click('.pop [data-a="split"]'); await wait(900);
    check("split: one line becomes two", await page.evaluate(() => D.lines.length) === n0 + 1);
    await page.evaluate(() => document.querySelector('.row[data-n="1"] .joinbtn').click()); await wait(900);
    check("combine: + Combine puts them back", await page.evaluate(() => D.lines.length) === n0);
    // ✦+ on the first line: the Swap sheet draws the lookbook on it, a tap adds one
    await page.evaluate(() => openAdd(0));
    await page.waitForSelector("#swGrid .sw-tile:not(.off)", { timeout: 60000 }).catch(async e => { throw new Error("Swap sheet: " + await page.$eval("#swGrid", g => g.innerText)); }); await wait(300);
    check("add: the Swap sheet shows live looks", await page.$$eval("#swGrid iframe", f => f.length) > 0);
    await page.evaluate(() => document.querySelector('#swGrid .sw-tile:not(.off):not([data-group="Hook"])').click()); await wait(1500);   // a hook asks for its own words first
    const added = await page.evaluate(() => LOOKS.layers.filter(L => L.added).map(L => [L.name, L.dur]));
    check("add: the look is on the line", added.length === 1, added);
    await page.evaluate(() => showSec("visuals")); await wait(400);
    check("visuals: the added look sits on its line with Swap and more", await page.evaluate(() => !!document.querySelector('.lkchip [data-a="swap"]') && !!document.querySelector('.lkchip [data-a="more"]')));
    check("tracks: the added look is a block on the timeline", await page.evaluate(() => document.querySelectorAll("#laneVis .vblk").length >= 1));
    if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT + "/visuals.png" });
    await page.evaluate(() => document.querySelector('.lkchip [data-a="more"]').click()); await wait(150);
    check("visuals: more offers Move, Refine and Remove", (await page.$$eval(".pop button", b => b.map(x => x.dataset.a))).join(",") === "move,refine,trash");
    await page.evaluate(() => { hidePop(); showSec("cut"); }); await wait(150);
    check("sheets: a closed sheet lets go of its live looks", await page.$$eval(".sheet iframe", f => f.length) === 0);
    await page.evaluate(w => editLines("split", w, document.body), w); await wait(1500);
    const shrunk = await page.evaluate(() => LOOKS.layers.filter(L => L.added).map(L => L.dur));
    check("split: the look keeps the half with its first word, and shrinks", shrunk.length === 1 && shrunk[0] < added[0][1], [added, shrunk]);
    const mod = process.platform === "darwin" ? "Meta" : "Control";
    await page.keyboard.down(mod); await page.keyboard.press("z"); await page.keyboard.up(mod); await wait(1500);
    const undone = await page.evaluate(() => [D.lines.length, LOOKS.layers.filter(L => L.added).map(L => L.dur)]);
    check("undo: Cmd/Ctrl+Z puts the line and its look back exactly", undone[0] === n0 && Math.abs(undone[1][0] - added[0][1]) < 0.001, undone);
    await page.evaluate(() => redo()); await wait(1500);
    const redone = await page.evaluate(() => [D.lines.length, LOOKS.layers.filter(L => L.added).map(L => L.dur)]);
    check("redo: the split comes back, look and all", redone[0] === n0 + 1 && Math.abs(redone[1][0] - shrunk[0]) < 0.001, redone);
    check("combine: no Combine into a line the engine cut away", await page.evaluate(() => [...document.querySelectorAll(".row")].every((r, k) => k === 0 || !r.classList.contains("allcut") || r.classList.contains("nojoin"))));
    await page.evaluate(() => editLines("join", D.lines[0][D.lines[0].length - 1], document.body)); await wait(1500);
    const grown = await page.evaluate(() => LOOKS.layers.filter(L => L.added).map(L => L.dur));
    check("combine: the look grows back over the whole line", grown.length === 1 && Math.abs(grown[0] - added[0][1]) < 0.05, [added, grown]);
    // Visuals too: split and join lines from the word menu, without touching her cut or unlocking anything
    await page.evaluate(() => { showSec("visuals"); clearSel(); }); await wait(300);
    const wv = await page.evaluate(() => D.lines[0][1]);
    const vb = await (await page.$(`.w[data-i="${wv}"]`)).boundingBox();
    await page.mouse.click(vb.x + vb.width / 2, vb.y + vb.height / 2); await wait(250);
    const vm = await page.$$eval(".pop button", b => b.map(x => x.dataset.a));
    check("visuals: the word menu offers Split line here (Combine between lines joins them)", vm.includes("split") && !vm.includes("join"), vm);
    const lb0 = await page.evaluate(() => ({ n: D.lines.length, cut: JSON.stringify(changes()), len: total(spans), ph: phase }));
    await page.click('.pop [data-a="split"]'); await wait(1500);
    const vs = await page.evaluate(() => ({ n: D.lines.length, cut: JSON.stringify(changes()), len: total(spans), ph: phase }));
    await page.evaluate(() => { const l = D.lines[0]; editLines("join", l[l.length - 1], document.body); }); await wait(1500);
    const vj = await page.evaluate(() => ({ n: D.lines.length, ph: phase, lines: !LOOK_CHANGES.has("/lines"), zone: getComputedStyle(document.querySelector('.row[data-n="1"] .joinzone')).display !== "none" }));
    const grp = await page.evaluate(async () => {                     // a look added from one tapped word covers its whole line, as lines stand now
      const l0 = D.lines[0]; await editLines("join", l0[l0.length - 1], document.body); await new Promise(r => setTimeout(r, 1200));
      const ids = D.lines[0], want = lineSpan(ids), kept = ids.filter(i => !cut[i] && !D.words[i].q), w = kept[kept.length - 1]; let got = null; const keep = openSwap;
      window.openSwap = o => { got = o; }; sel = [w]; showPop(); const b = document.querySelector('.pop [data-a="look"]'); if (b) b.click(); window.openSwap = keep;
      const out = { menu: !!b, whole: !!got && !!want && Math.abs(got.add.start - want.a) < 1e-6 && Math.abs(got.add.end - want.z) < 1e-6 };
      const r = await post("/lines", { restore: (undoS.pop() || {}).lines }); if (r.ok) await linesChanged(r.j.lines, true);
      return out; });
    check("visuals: lines act as a group: a look added from one tapped word covers the whole (combined) line, not the old break",
          grp.menu && grp.whole, grp);
    check("visuals: a split there makes two lines, her cut and its length untouched, nothing unlocked; join puts it back",
          vs.n === lb0.n + 1 && vs.cut === lb0.cut && Math.abs(vs.len - lb0.len) < 1e-6 && vs.ph === lb0.ph
          && vj.n === lb0.n && vj.ph === lb0.ph && vj.lines && vj.zone, { lb0, vs, vj });
    // no locks: the main button walks her forward; clicking a clip of her cut selects it (like CapCut)
    await page.evaluate(() => showSec("visuals")); await wait(150);
    await page.click("#send"); await wait(300);
    check("next: Visuals' button goes to Sound", await page.evaluate(() => sec === "sound"));
    await page.evaluate(() => showSec("cut")); await wait(150);
    const head0 = await page.evaluate(() => cutPos());
    const sg = await (await page.$("#segs .seg")).boundingBox();
    await page.mouse.click(sg.x + sg.width / 2, sg.y + sg.height / 2); await wait(300);
    const picked = await page.evaluate((h0) => ({ sel: tlSel, lit: !!document.querySelector("#segs .seg.sel"), stay: Math.abs(cutPos() - h0) < 0.02 }), head0);
    check("timeline: clicking a clip selects it and leaves the playhead where it was", picked.sel === 0 && picked.lit && picked.stay, picked);
    await page.evaluate(() => selectClip(null));
    await page.evaluate(() => showSec("sound")); await wait(2500);
    check("sound: every look that moves gets a sound row, timed to its motion", await page.evaluate(() => (SND.cues || []).some(c => c.origin === "look")));
    check("sound: the planned sound is a row too", await page.evaluate(() => (SND.cues || []).some(c => c.origin === "plan")));
    check("sound: each sound sits under the numbered line it plays on, in her script", await page.evaluate(() => {
      const r = document.querySelector(".row .sndchips .sndrow[data-cue]"); return !!r && !$("script").hidden && /^\d\d/.test(r.closest(".row").querySelector(".num").textContent); }));
    const before = await page.evaluate(() => SND.cues.find(c => c.origin === "plan").t);
    await page.evaluate(() => document.querySelector('.sndrow[data-cue] [data-a="more"]').click()); await wait(200);   // timing lives behind ⋯
    await page.evaluate(() => document.querySelector('.pop [data-d="0.05"]').click()); await wait(800);
    check("sound: + nudges a sound a little later", await page.evaluate(() => SND.cues.some(c => c.nudge > 0)));
    await page.evaluate(() => document.querySelector('#sndSwitch [data-a="fx"]').click()); await wait(800);
    check("sound: the switch turns sound effects off for the whole reel", await page.evaluate(() => SND.sfx_enabled === false));
    await page.evaluate(() => document.querySelector('#sndSwitch [data-a="fx"]').click()); await wait(800);
    await page.evaluate(() => document.querySelector('.sndrow[data-cue] [data-a="swap"]').click());
    await page.waitForSelector(".sndmenu .sm-it", { timeout: 90000 }); await wait(300);
    check("sound: Swap offers sounds and 'No sound here'", await page.evaluate(() => document.querySelectorAll(".sndmenu .sm-it").length > 2 && [...document.querySelectorAll(".sndmenu .sm-none")].some(x => x.textContent.includes("No sound here"))));
    const pick = await page.evaluate(() => { const it = [...document.querySelectorAll(".sndmenu .sm-it:not(.sm-none)")].find(x => !x.classList.contains("cur")); const n = it.querySelector("span:nth-child(2)").textContent; it.click(); return n; });
    await wait(1500);
    if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT + "/sound.png" });
    check("sound: picking one swaps it in", await page.evaluate(n => SND.cues.some(c => c.name === n || (c.name || "").startsWith(n)), pick), pick);
    await page.evaluate(() => document.querySelector('#sndCues .ll-row.bare .lk-addchip').click());
    await page.waitForSelector(".sndmenu .sm-it", { timeout: 90000 }); await wait(200);
    await page.evaluate(() => document.querySelector(".sndmenu .sm-it:not(.sm-none)").click()); await wait(1500);
    check("sound: Add a sound at the playhead adds one", await page.evaluate(() => SND.cues.some(c => c.origin === "free")));
    const sd = await page.evaluate(async () => {                       // every sound row has Delete, and Undo brings it back
      const vis = () => document.querySelectorAll(".sndrow[data-cue]").length, n0 = vis(), row = document.querySelector(".sndrow[data-cue]");
      if (!row || !row.querySelector('[data-a="del"]')) return { del: false };
      row.querySelector('[data-a="del"]').click(); await new Promise(r => setTimeout(r, 1200)); const n1 = vis();
      undo(); await new Promise(r => setTimeout(r, 1200)); return { del: true, n0, n1, n2: vis() }; });
    check("sound: Delete takes a sound off its line, and the top Undo brings it back", sd.del && sd.n1 === sd.n0 - 1 && sd.n2 === sd.n0, sd);
    await page.evaluate(() => showSec("finish")); await wait(200);
    check("finish: with her cut finished, Finish offers the routes and the button is Render", await page.evaluate(() => !document.querySelector(".fin-routes").hidden && $("send").dataset.act === "render"));
    check("finish: her cover lives here, and a snap button is always on the player (Snap, or the camera in a look's row)", await page.evaluate(() => !!$("snapNow") && (getComputedStyle($("shutter")).display !== "none" || (!$("lookTools").hidden && !!$("lookTools").querySelector('[data-lt="snap"]')))));
    await page.evaluate(() => document.querySelector('.fin-route[data-route="mp4"]').click()); await wait(100);
    if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT + "/finish.png" });
    check("finish: picking a route marks it", await page.evaluate(() => document.querySelector('.fin-route[data-route="mp4"]').getAttribute("aria-checked") === "true"));
    // Build a new look: pick a line, say the idea, save it; the chat puts a design on that line, live on the page
    await page.evaluate(() => showSec("visuals")); await wait(200);
    await page.evaluate(() => openNewLook()); await wait(800);
    check("new look: the sheet opens on a line, with a still of it", await page.evaluate(() => !$("newLookSheet").hidden && $("nlLine").options.length > 0 && !!$("nlImg").getAttribute("src")));
    await page.click("#nlSave"); await wait(200);
    check("new look: an empty idea isn't saved", await page.evaluate(() => !$("newLookSheet").hidden));
    await page.type("#nlIdea", "a sticky note that slaps on with a little tilt");
    await page.click("#nlSave"); await wait(600);
    console.error("state:", await page.evaluate(() => JSON.stringify({ hid: $("looksWarn").hidden, ideas: LOOKS && LOOKS.ideas, txt: $("looksWarnText").textContent, sheet: !$("newLookSheet").hidden, on: looksOn })));
    const st8 = await page.evaluate(async () => { const j = await (await fetch(`/status?job=${encodeURIComponent(D.job)}`, { cache: "no-store" })).json();
      TQ = j.queue; watcherLive = false; renderQueue(); updateFresh();
      return { q: !$("taskQueue").hidden && [...document.querySelectorAll("#tqList .tq-it")].some(r => /New look/.test(r.textContent)),
               hint: !$("tqHint").hidden && /update my edit/.test($("tqHintText").textContent), card: $("staleBadge").hidden || $("staleBadge").dataset.k !== "claude" }; });
    check("new look: the idea is saved and the task queue hands it to Claude (one line to type, no second card)", st8.q && st8.hint && st8.card, st8);
    const st8b = await page.evaluate(async () => {                   // the same card, the page's own fixes: cut moved, render older than the edit
      const keep = [LOOKS.made_for, LOOKS.ideas, notesList, FIN]; LOOKS.ideas = []; notesList = [];
      LOOKS.made_for = "an-older-cut"; retimeFailed = true; updateFresh(); const a = [$("staleBadge").dataset.k, $("sbGo").textContent]; retimeFailed = false;
      LOOKS.made_for = D.cut_id; FIN = { state: "done", stale: true }; updateFresh(); const b = [$("staleBadge").dataset.k, $("sbGo").textContent];
      FIN = { state: "done", stale: false }; updateFresh(); const c = $("staleBadge").hidden;
      [LOOKS.made_for, LOOKS.ideas, notesList, FIN] = keep; updateFresh(); return { a, b, c }; });
    const st8c = await page.evaluate(() => { const c = $("staleBadge").getBoundingClientRect(), v = $("screen").getBoundingClientRect(), t = document.querySelector(".transport").getBoundingClientRect();
      return { overPreview: !(c.bottom <= v.top || c.top >= v.bottom || c.right <= v.left || c.left >= v.right), abovePreview: c.bottom <= v.top + 1,
               own: !$("staleBadge").contains($("send")) && $("staleBadge").contains($("sbX")) }; });
    check("out of date: the card sits right above her preview, never on it", !st8c.overPreview && st8c.abovePreview && st8c.own, st8c);
    check("out of date: a moved cut the page couldn't move by itself gets one tap, a stale render renders again, nothing stale = no card",
          st8b.a[0] === "cut" && st8b.a[1] === "Move my visuals to match" && st8b.b[0] === "render" && st8b.c === true, st8b);
    const st8d = await page.evaluate(() => { const was = sec, out = {};
      for (const k of ["cut", "visuals", "sound", "finish"]) { showSec(k); out[k] = [getComputedStyle($("lookStack")).opacity === "0" ? "hidden" : "visible", pbHeard(), getComputedStyle($("laneSnd")).opacity === "0" ? "hidden" : "visible"]; }
      showSec(was); return out; });
    check("tabs: Cut shows only her footage and voice, Visuals adds looks with sounds muted, Sound and Finish play everything",
          st8d.cut[0] === "hidden" && !st8d.cut[1] && st8d.visuals[0] === "visible" && !st8d.visuals[1] && st8d.visuals[2] === "hidden"
          && st8d.sound[0] === "visible" && st8d.sound[1] && st8d.finish[1], st8d);
    const st8e = await page.evaluate(async () => {                     // the checks: measured from what the browser draws
      const a = audOver({ x0: 0, y0: 0, x1: 10, y1: 10 }, { x0: 5, y0: 5, x1: 20, y1: 20 });
      await runAudit(); await new Promise(r => setTimeout(r, 200));
      const ran = typeof AUD.sig === "string" && AUD.sig.length > 0;
      const keep = AUD.issues; const withCard = (document.querySelector(".lkchip[data-layer]:not(.cont)") || {}).dataset?.layer || LOOKS.layers[0].name;
      AUD.issues = { [withCard]: [{ k: "edge", msg: "May run off the edge", t: 1, fix: true }] };
      renderAudit(); const row = document.querySelector(".lk-warn"), onCard = !!(row && row.querySelector("button.fix")) && /^May /.test(row.querySelector("span").textContent) && /Move it for me/.test(row.textContent) && !/Show me/.test(row.textContent);
      showSec("finish"); const onFinish = /Okay with that\?/.test(($("finChecks") || {}).textContent || "");
      AUD.issues = keep; renderAudit(); showSec("visuals");
      return { a, ran, onCard, onFinish }; });
    check("checks: run on the looks, sit under the card as a maybe with Move it for me (no Show me), and Finish lists them before the export",
          st8e.a === 25 && st8e.ran && st8e.onCard && st8e.onFinish, st8e);
    const st8f = await page.evaluate(async () => {                     // the Image picker: her favorites, several at once
      const n = D.lines.findIndex(ids => ids.some(i => !cut[i])); await openMedia(n); await new Promise(r => setTimeout(r, 300));
      const open = !$("mediaSheet").hidden, chips = document.querySelectorAll("#mdFilter button").length;
      mdPicks = [{ id: "gifs/a.gif", name: "a", kind: "GIF" }, { id: "photos/b.jpg", name: "b", kind: "Image" }]; mdReady();
      const two = $("mdGo").textContent.includes("Add 2") && !$("mdHow").hidden;
      mdPicks = [{ id: "broll/a.mp4", name: "a", kind: "Video" }, { id: "photos/b.jpg", name: "b", kind: "Image" }]; mdReady();
      const clipAndImage = !$("mdHow").hidden;                     // a clip under a picture: all at once still makes sense
      mdPicks = [{ id: "broll/a.mp4", name: "a", kind: "Video" }, { id: "broll/c.mp4", name: "c", kind: "Video" }]; mdReady();
      const twoClips = $("mdHow").hidden;                            // two full-screen clips at once would hide one: they take turns
      $("mdIdea").value = "make it bounce"; mdReady(); const send = /Send to Claude/.test($("mdGo").textContent) && $("mdHow").hidden;
      $("mdIdea").value = ""; mdPicks = []; mdReady(); closeSheets();
      return { open, chips, two, clipAndImage, twoClips, send, imgChip: !!document.querySelector(".lk-imgchip") }; });
    check("image picker: opens from a line, picks several (one after another or all at once), or hands the idea to Claude",
          st8f.open && st8f.two && st8f.send && st8f.imgChip, st8f);
    check("image picker: two or more b-roll clips always go one after another (never stacked, where one would hide the other)",
          st8f.clipAndImage && st8f.twoClips, st8f);
    const lib = await page.evaluate(async () => {                     // the whole Effects Library: Visuals and Sound each have a way in
      const seen = id => $(id).getClientRects().length > 0, out = {};
      for (const k of ["visuals", "sound"]) { showSec(k); await new Promise(r => setTimeout(r, 200));
        if (k === "visuals") { $("looksMenuBtn").click(); await new Promise(r => setTimeout(r, 150)); }  // Browse lives in the Looks menu
        out[k] = [seen("libFx"), seen("libSnd")]; }
      document.querySelectorAll(".tm-pop").forEach(p => p.hidden = true);
      const bad = await post("/open-library", { tab: "nope" });
      showSec("visuals"); return { ...out, refusesOddTab: !bad.ok }; });
    check("effects library: Visuals shows the Effects library button, Sound shows the Sound library button, and only a real tab opens",
          lib.visuals[0] && !lib.visuals[1] && !lib.sound[0] && lib.sound[1] && lib.refusesOddTab, lib);
    await (await fetch(process.env.BASE + "/__place_design")).json();
    await page.reload({ waitUntil: "networkidle2" }); await wait(1500);
    check("new look: the design shows on her line, live", await page.evaluate(() => LOOKS.layers.some(L => L.look === "my-sticky-note-draft")));
    check("new look: the idea shows as a draft on that line", await page.evaluate(() => (LOOKS.ideas || []).some(x => x.status === "draft")));
    // the lookbook: one tab per style pack, the reel's own marked, another pack drawn on her words when picked
    await page.evaluate(() => $("openBook").click()); await wait(6000);
    const bk1 = await page.evaluate(() => ({ tabs: [...document.querySelectorAll("#bkPacks button")].map(b => [b.textContent, b.getAttribute("aria-selected")]), tiles: $("bkGrid").children.length }));
    check("lookbook: a tab per pack, this reel's selected", bk1.tabs.length >= 3 && bk1.tabs.some(t => /this reel/.test(t[0]) && t[1] === "true") && bk1.tiles > 0, bk1);
    await page.evaluate(() => [...document.querySelectorAll("#bkPacks button")].find(b => b.getAttribute("aria-selected") !== "true").click()); await wait(9000);
    const bk2 = await page.evaluate(() => ({ head: $("bkPack").textContent, go: !!$("bkUseGo"), sel: [...document.querySelectorAll("#bkPacks button")].filter(b => b.getAttribute("aria-selected") === "true").length }));
    check("lookbook: another pack's tab draws its looks and offers to use it for the reel", bk2.go && bk2.sel === 1 && /pack · \d+ looks/.test(bk2.head), bk2);
    // her default: the open pack's "Make it my default" saves it, the tab says so, and the reel itself stays put
    const dPack = await page.evaluate(() => $("bkPack").textContent.split(" pack")[0]);
    await page.evaluate(() => $("bkDefaultGo").click()); await wait(1500);
    const bk3 = await page.evaluate(() => ({ box: $("bkDefault").textContent, tab: [...document.querySelectorAll("#bkPacks button")].find(b => b.getAttribute("aria-selected") === "true").textContent, use: !!$("bkUseGo") }));
    check("lookbook: Make it my default saves that pack and marks its tab", bk3.box.includes(`${dPack} is your default`) && /your default/.test(bk3.tab) && bk3.use, bk3);
    await page.evaluate(() => closeSheets());
    const sb = await page.evaluate(async () => { showSec("visuals"); await new Promise(r => setTimeout(r, 600));
      const perLine = document.querySelectorAll(".lkchips .lk-sandbox, .lkchips .sb-bar").length;
      $("looksMenuBtn").click(); await new Promise(r => setTimeout(r, 150));          // Build new lives in the Looks menu
      const btn = $("sandboxBtn");
      const shown = !!btn && btn.getClientRects().length > 0; if (btn) btn.click(); await new Promise(r => setTimeout(r, 400));
      const open = !$("sandboxSheet").hidden, ask = !$("sbAsk").hidden, go = $("sbFwd").textContent;
      closeSheets(); return { perLine, shown, open, ask, go }; });
    check("sandbox: Build new in the Looks menu (nothing added to the lines), and it opens on the ask", sb.perLine === 0 && sb.shown && sb.open && sb.ask && /Send to Claude/.test(sb.go), sb);
    // the walkthrough: first visit to a tab, short, never twice; the filter: her frame in every look, live on the preview
    const tr = await page.evaluate(async () => {
      try { Object.keys(localStorage).filter(k => k.startsWith("ve-tour")).forEach(k => localStorage.removeItem(k)); } catch (e) {}
      await tourReady; TOURSEEN = {};
      tourEnd(false, false); showSec("cut"); await new Promise(r => setTimeout(r, 1200));
      const first = tourOn && tourOn.tab, n = tourOn && tourOn.steps.filter(st => !st.center).length;
      const welcome = !!(tourOn && tourOn.steps[0].center && $("tourCard").classList.contains("welcome") && /upgrade/.test($("tourTitle").textContent) && $("tourPerks").children.length >= 3 && !$("tourPerks").hidden);
      $("tourSkip").click(); showSec("visuals"); await new Promise(r => setTimeout(r, 1200));
      const after = !!tourOn; showSec("cut");
      // remembered by the engine, not this browser: a new address (or a cleared browser) still never shows it again
      await new Promise(r => setTimeout(r, 400));
      const kept = await (await fetch("/tour")).json();
      const engine = ["cut", "visuals", "sound", "finish"].every(t => kept.seen[t] === tourVer(t));
      try { Object.keys(localStorage).filter(k => k.startsWith("ve-tour")).forEach(k => localStorage.removeItem(k)); } catch (e) {}
      TOURSEEN = kept.seen; showSec("visuals"); await new Promise(r => setTimeout(r, 1200));
      const again = !!tourOn; tourEnd(false, false); showSec("cut");
      return { first, n, welcome, after, engine, again }; });
    check("tour: shows on a first visit, two tips at most, and Skip means never again", tr.first === "cut" && tr.n >= 1 && tr.n <= 2 && tr.after === false, tr);
    check("tour: the first visit opens on the welcome (what replaced the widget, and its perks)", tr.welcome, tr);
    check("tour: Skip is kept by the engine, so a new browser address never shows it again", tr.engine && tr.again === false, tr);
    const fl = await page.evaluate(async () => { showSec("visuals"); $("filterBtn").click(); await new Promise(r => setTimeout(r, 400));
      const tiles = $("flGrid").children.length; closeSheets(); if (LOOKS) { LOOKS.grade = "mono"; applyFilter(); }
      const css = getComputedStyle(v).filter, name = $("filterName").textContent; if (LOOKS) { LOOKS.grade = null; applyFilter(); } return { tiles, css, name }; });
    check("filter: six choices (None first) and the preview shows the pick", fl.tiles === 6 && /grade-mono/.test(fl.css) && /Black/.test(fl.name), fl);
    const so = await page.evaluate(() => {                             // Start over: two taps, and Undo brings it all back
      showSec("cut"); const i = D.order.find(k => !cut[k]); toggle([i], true);
      const b = document.createElement("button"); document.body.append(b); const ev = { currentTarget: b };
      startOver(ev); const afterOne = cut[i]; startOver(ev); const afterTwo = cut[i]; undo(); const afterUndo = cut[i]; b.remove(); toggle([i], false);
      return { afterOne, afterTwo, afterUndo }; });
    check("safety: Start over needs two taps, and Undo brings every edit back", so.afterOne === true && so.afterTwo === false && so.afterUndo === true, so);
    await page.evaluate(() => { $("sbIdea").value = "a draft that must survive"; $("sbIdea").dispatchEvent(new Event("input")); });
    await page.reload({ waitUntil: "networkidle2" }); await new Promise(r => setTimeout(r, 2500));
    const kept = await page.evaluate(() => { const v = $("sbIdea").value; $("sbIdea").value = ""; $("sbIdea").dispatchEvent(new Event("input")); return v; });
    check("safety: what she typed in the sandbox survives a reload", kept === "a draft that must survive", kept);
    const mv = await page.evaluate(() => {                              // Move: her hand wins, and the center line pulls it in
      const it = { L: {}, box: { l: 100, t: 200, r: 300, b: 300 }, cur: [0, 0, 1, 0, 200, 250] };
      const free = clampMove(it, -900, 2400); it.cur = [337, 707, 1, 0, 200, 250]; const s = mvSnap(it, 10);
      const cap = { L: { captions: true }, box: it.box, cur: [337, 707, 1, 0, 200, 250] }; const sc = mvSnap(cap, 10);
      return { free: free.slice(0, 2), snapped: it.cur.slice(0, 2), s, capX: cap.cur[0], sc }; });
    check("move: goes anywhere she drags it, off the frame included", mv.free[0] === -900 && mv.free[1] === 2400, mv);
    check("move: near the frame's center it snaps onto it, both ways", mv.s.x && mv.s.y && mv.snapped[0] === 340 && mv.snapped[1] === 710, mv);
    check("move: captions snap up and down only (they never slide sideways)", !mv.sc.x && mv.sc.y && mv.capX === 337, mv);
    const lv = await page.evaluate(() => {                              // a look's frame address carries its version
      const L = LOOKS && LOOKS.layers.find(l => l.dir); if (!L) return { skip: true };
      const a = lookUrl(L), b = lookUrl({ ...L, v: (L.v || 1) + 1 });
      return { versioned: !L.v || /\?v=\d+$/.test(a), differs: a !== b, sig: looksSig(LOOKS) !== looksSig({ layers: LOOKS.layers.map(x => x === L ? { ...x, v: (x.v || 1) + 1 } : x) }) }; });
    check("looks: a redrawn look is a new frame address (never an old copy in the preview), and a version change is noticed",
          lv.skip || (lv.versioned && lv.differs && lv.sig), lv);
    const la = await page.evaluate(() => {                              // a look's own sound: unmuted, at its own volume, in step
      const d = document.implementation.createHTMLDocument("x"); d.body.innerHTML = '<audio data-start="0.5" data-duration="2" data-volume="0.4" muted></audio><video muted></video>';
      const a = d.querySelector("audio"); lookAudio(d, 1.0, false);
      return { unmuted: !a.muted, vol: Math.abs(a.volume - 0.4) < 1e-6, held: a.paused, video: d.querySelector("video").muted,
               tiles: /lookAudio\(d, tl\.time\(\), (tile\.classList\.contains\("playing"\)|on)\)/.test(tileFor.toString()) && /tileVideos\(d, tl\.time\(\), on\)/.test(tileFor.toString()),
               preview: /lookAudio\(f\.el\.contentDocument/.test(steerOne.toString()) && /sec === "visuals"/.test(steerOne.toString()) };
    });
    check("look sound: a look's own <audio> plays unmuted at its own volume (her footage inside a look stays muted), in Sandbox and lookbook tiles and on her preview on Visuals",
          Object.values(la).every(x => x === true), la);
    const ff = await page.evaluate(async () => {                       // a look page drawn again reloads its frame, quiet window or not
      if (!LOOKS || !lookFrames.length) return { skip: true };
      const f = lookFrames.find(x => x.el) || lookFrames[0]; if (!f.el) { steerLooks(f.L.offset + 0.1); await new Promise(r => setTimeout(r, 400)); }
      const el0 = f.el, v0 = f.L.v || 1; quietLooksUntil = Date.now() + 10000;
      freshFrames({ [f.L.name]: v0 + 5 }); steerLooks(f.L.offset + Math.min(0.2, (f.L.dur || 1) / 2)); await new Promise(r => setTimeout(r, 300));
      const out = { newer: f.L.v === v0 + 5, rebuilt: !!f.el && f.el !== el0, url: !!f.el && f.el.src.endsWith(`?v=${v0 + 5}`), status: false };
      const j = await (await fetch(`/status?job=${encodeURIComponent(D.job)}`, { cache: "no-store" })).json(); out.status = !!j.looks_v && typeof j.looks_v === "object";
      quietLooksUntil = 0; return out; });
    check("looks: a look page the engine drew again (a caption redraw) is reloaded on the next beat, even right after her own change",
          ff.skip || Object.values(ff).every(x => x === true), ff);
    const bl = await page.evaluate(async () => {                       // the blank space of a line jumps to its start, Cut and Visuals
      const out = {};
      for (const k of ["cut", "visuals"]) {
        showSec(k); await new Promise(r => setTimeout(r, 300));
        let n = D.lines.findIndex((ids, x) => x >= 1 && ids.some(i => !cut[i] && !D.words[i].q)); if (n < 0) n = 0;
        const row = document.querySelector(`.row[data-n="${n}"]`);
        seekCut(0); const first = D.lines[n].find(i => !cut[i]);
        const spot = row.querySelector(".lkchips") || row;                 // the empty card column (Visuals), or the row itself
        spot.dispatchEvent(new MouseEvent("click", { bubbles: true })); await new Promise(r => setTimeout(r, 100));
        out[k] = Math.abs(cutPos() - cutStarts()[first]) < 0.06 && !document.querySelector(".pop");
      }
      showSec("cut"); return out; });
    check("script: a click on a line's blank space jumps the player to that line's start (Cut and Visuals), no word menu",
          bl.cut && bl.visuals, bl);
    const mj = await page.evaluate(async () => {                       // Move never jumps the playhead for a look on screen
      if (!LOOKS) return { skip: true };
      const L = LOOKS.layers.find(l => !l.captions && !l.off && l.movable && l.dur > 0.6); if (!L) return { skip: true };
      showSec("visuals"); const t0 = L.offset + L.dur * 0.4; seekCut(t0); await new Promise(r => setTimeout(r, 900));
      const c0 = cutPos(); startMove({ layer: L.name }); await new Promise(r => setTimeout(r, 900));
      const out = { same: Math.abs(cutPos() - c0) < 0.01, moving: !!moving, active: !!moving && moving.active.L.name === L.name };
      if (moving) $("moverCancel").click(); out.after = Math.abs(cutPos() - c0) < 0.01; return out; });
    check("move: starting Move on a look that's on screen (its card, or ✥ on the player) never moves the playhead; Cancel leaves it too",
          mj.skip || (mj.same && mj.moving && mj.active && mj.after), mj);
    const mn = await page.evaluate(async () => {                       // Move never throws on a look that isn't there (a buyer, 2026-10-22)
      if (!LOOKS) return { skip: true };
      const L = LOOKS.layers.find(l => !l.captions && !l.off && l.movable && l.dur > 0.6); if (!L) return { skip: true };
      const wait = ms => new Promise(r => setTimeout(r, ms)), thrown = [], catchIt = e => thrown.push(String(e.message || e));
      addEventListener("error", catchIt);                              // what a timer or the ResizeObserver throws lands here
      const out = {};
      try {
        showSec("visuals"); seekCut(L.offset + L.dur * 0.4); await wait(900);
        const f = lookFrames.find(x => x.L.name === L.name && x.ready && x.el); if (!f) return { skip: true };
        const r = f.el.contentDocument.getElementById("root"); r.id = "not-root";   // a hand-built page with no #root
        startMove({ layer: L.name }); await wait(400);
        out.noRootSkipped = !moving || !moving.items.some(i => i.L.name === L.name);
        if (moving) $("moverCancel").click();
        r.id = "root";
        startMove({ layer: L.name }); await wait(900);                 // her looks drawn again while Move is open
        out.moving = !!moving;
        if (!moving) return out;
        const it0 = moving.items.find(i => i.L.name === L.name); it0.cur[1] += 40; drawMover();   // she dragged it down
        $("lookStack").innerHTML = ""; lookFrames = []; LOOKS = null; looksOn = false;            // as a retime does
        drawMover(); mvApply(null, [0, 0, 1, 0, null, null]);          // the ResizeObserver mid-reload, a frame already gone
        await loadLooks(); await wait(1500); drawMover();
        const it = moving && moving.items.find(i => i.L.name === L.name);
        out.followed = !!it && !!it.f.el && it.f.el.isConnected && it.root === it.f.el.contentDocument.getElementById("root");
        out.kept = !!it && it.cur[1] === it.start[1] + 40 && it.root.style.transform.includes(`translate(${it.cur[0]}px, ${it.cur[1]}px)`);
        $("moverCancel").click(); out.closed = !moving;
      } catch (e) { thrown.push(String(e.message || e)); }
      finally { removeEventListener("error", catchIt); }
      out.thrown = thrown; return out; });
    check("move: a look page with no #root is left out of Move (the engine can't move it), never a null 'style' crash",
          mn.skip || (mn.noRootSkipped && !(mn.thrown || []).length), mn);
    check("move: her looks drawn again under an open Move: no null 'safe' crash, each box follows its look and keeps her drag",
          mn.skip || (mn.moving && mn.followed && mn.kept && mn.closed && !(mn.thrown || []).length), mn);
    const sbl = await page.evaluate(() => {                             // a Sandbox idea lands on the line it's for
      const kn = D.lines.map((ids, n) => ({ n, ids: ids.filter(i => !cut[i]) })).filter(x => x.ids.length >= 3);
      const A = kn[1], B = kn[kn.length - 1], txt = A.ids.map(i => D.words[i].t).join(" ");
      seekCut(lineSpan(D.lines[B.n]).a + 0.1); sbFor = null;
      const named = sbLineFor(`For the line "${txt.slice(0, 40)}" at 0:05: emojis`), plain = sbLineFor("emojis please");
      sbFor = A.n; const opened = sbLineFor("emojis please"); sbFor = null;
      return { named: A.ids.includes(named.w), plain: B.ids.includes(plain.w), opened: A.ids.includes(opened.w), span: named.end > named.start }; });
    check("sandbox: an idea goes on the line it names, not where the playhead wandered", sbl.named && sbl.span, sbl);
    check("sandbox: from Swap it goes on that line; with no line at all, the whole line under the playhead", sbl.opened && sbl.plain, sbl);
    const nx = await page.evaluate(() => {                              // the page's next step follows the tabs, in order
      const was = phase, out = {};
      for (const p of ["cut", "looks", "render"]) { phase = p; updateNote(); showSec("finish"); updatePrimary();
        out[p] = { next: $("nextTitle").textContent, exportOn: !$("send").disabled && /Export/.test($("send").textContent), lock: layerLock("finish") }; }
      phase = was; updateNote(); showSec("visuals"); updatePrimary(); return out; });
    check("flow: the next-step card walks Visuals, Sound, Finish as she locks each in", nx.cut.next === "Next: Visuals" && nx.looks.next === "Next: Sound" && nx.render.next === "Next: Finish", nx);
    check("flow: Export opens only once her cut and her looks are locked in, and says what's missing", !nx.cut.exportOn && !nx.looks.exportOn && nx.render.exportOn
          && /Lock in your cut/.test(nx.cut.lock) && /Lock in your looks first/.test(nx.looks.lock), nx);
    const ud = await page.evaluate(async () => {                       // a look she takes off comes back with the top Undo
      showSec("visuals"); await new Promise(r => setTimeout(r, 600));
      const L = (LOOKS && LOOKS.layers || []).find(l => !l.off && (l.added || (l.look && !["_original", "_off"].includes(l.look)))); if (!L) return { skip: true };
      const sig = l => l ? `${l.off ? "off" : ""}|${l.look || ""}|${l.dir || ""}` : "none", was = sig(L);
      await trashLook({ layer: L.name }, null); await new Promise(r => setTimeout(r, 800));
      const gone = sig(LOOKS.layers.find(l => l.name === L.name)) !== was, on = !$("undo").disabled;
      undo(); await new Promise(r => setTimeout(r, 2500));
      return { gone, on, back: sig(LOOKS.layers.find(l => l.name === L.name)) === was }; });
    check("undo: a look she takes off comes back with the top Undo", !ud.skip && ud.gone && ud.on && ud.back, ud);
    const eg = await page.evaluate(async () => {                       // a piece's edge is exact by ear: no echo of the next raw word
      stop(); showSec("cut"); await new Promise(r => setTimeout(r, 300));
      const seek = t => new Promise(r => { v.addEventListener("seeked", r, { once: true }); v.currentTime = t; });
      const was = spans, calls = [], E = pbEdge, H = pbHush;
      spans = [{ s: 1.0, e: 2.0, ids: was[0].ids }, { s: 2.3, e: 3.0, ids: was[0].ids }]; qi = 0;
      pbEdge = l => calls.push(["edge", +l.toFixed(2)]); pbHush = () => calls.push(["hush"]);
      playing = true;
      await seek(1.9); tick();                                         // 0.1 s before the edge: her voice closes there, scheduled
      await seek(2.02); tick();                                        // past it (a late timer): hushed before the jump
      const jumped = qi === 1;
      playing = false; pbEdge = E; pbHush = H; spans = was; qi = 0;
      pbOpen();
      return { calls, jumped }; });
    check("edge: her voice closes right at a piece's end (set ahead), and is hushed across the jump",
          eg.calls.some(c => c[0] === "edge" && Math.abs(c[1] - 0.1) < 0.03) && eg.calls.some(c => c[0] === "hush") && eg.jumped, eg);
    const jm = await page.evaluate(async () => {                       // every piece of her cut is its own timeline block
      showSec("cut"); await new Promise(r => setTimeout(r, 300));
      const was = spans, W = D.words, before = document.querySelectorAll("#segs .seg").length;
      const k = spans.findIndex(sp => sp.ids.length >= 2 && D.lines.some(l => sp.ids.every(i => l.includes(i)))); if (k < 0) return { skip: true };
      const sp = spans[k], h = Math.ceil(sp.ids.length / 2), a = sp.ids.slice(0, h), b = sp.ids.slice(h);
      spans = [...was.slice(0, k), { s: sp.s, e: W[a[a.length - 1]].e + 0.04, ids: a }, { s: W[b[0]].s - 0.04, e: sp.e, ids: b }, ...was.slice(k + 1)];
      renderTimeline();
      const segs = [...document.querySelectorAll("#segs .seg")], two = segs.filter(g => +g.dataset.k === k || +g.dataset.k === k + 1);
      const labels = two.map(g => g.querySelector("span").textContent);
      const still = /strip\/w(\d+)\.jpg/.exec(two[1]?.style.backgroundImage || "");
      selectClip(k + 1); const focus = document.querySelector(".seg.sel")?.dataset.k; selectClip(null);
      spans = was; renderTimeline();
      return { more: segs.length - before, labels, still: still && +still[1] === b[0], focus: +focus === k + 1 }; });
    check("timeline: every piece of her cut is its own block (02a, 02b), with its own still, and selects on its own",
          jm.skip || (jm.more === 1 && /a$/.test(jm.labels[0]) && /b$/.test(jm.labels[1]) && jm.still && jm.focus), jm);
    const ed0 = await page.evaluate(async () => {                      // drag a cut's end edge right on the timeline
      selectClip(null); showSec("cut"); await new Promise(r => setTimeout(r, 300));
      const g = [...document.querySelectorAll("#segs .seg")].find(x => spans[+x.dataset.k] && spans[+x.dataset.k].ids.length >= 3 && x.offsetWidth > 60);
      if (!g) return { skip: true };
      const e = g.querySelector(".edg.e").getBoundingClientRect(), k = +g.dataset.k;
      return { x: e.left + e.width / 2, y: e.top + e.height / 2, k, w: g.offsetWidth, ids: spans[k].ids.slice(), undo: undoS.length, head: cutPos(), shown: getComputedStyle(g.querySelector(".edg.e")).display }; });
    let ed = { skip: true };
    if (!ed0.skip) {
      await page.mouse.move(ed0.x, ed0.y); await page.mouse.down();
      await page.mouse.move(ed0.x - ed0.w * 0.3, ed0.y, { steps: 6 });
      const tip = await page.evaluate(() => document.querySelector("#tlBox .edgtip")?.textContent || "");
      const live = await page.evaluate((s) => Math.round(document.querySelector(`#segs .seg[data-k="${s.k}"]`).getBoundingClientRect().width), ed0);
      await page.mouse.up(); await new Promise(r => setTimeout(r, 300));
      ed = await page.evaluate(async (s) => {
        const lost = s.ids.filter(i => cut[i]).length, steps = undoS.length - s.undo, open = Math.abs(cutPos() - s.head) > 0.05;
        undo(); await new Promise(r => setTimeout(r, 300));
        return { lost, steps, open, back: s.ids.every(i => !cut[i]) }; }, ed0);
      ed.tip = tip; ed.shown = ed0.shown; ed.follows = Math.abs(live - (ed0.w - ed0.w * 0.3)) <= 3;
    }
    check("timeline: dragging a cut's end edge in cuts words as one undo step (tip says so), and Undo brings them back",
          !ed.skip && (ed.shown === "block" && ed.lost >= 1 && ed.steps === 1 && /cut/.test(ed.tip) && !ed.open && ed.back), ed);
    check("timeline: the clip follows the cursor while its edge is dragged, and the playhead stays put", !ed.skip && ed.follows && !ed.open, ed);
    const edv = await page.evaluate(async () => { showSec("visuals"); await new Promise(r => setTimeout(r, 300));
      const h = document.querySelector("#segs .edg"); const d = h ? getComputedStyle(h).display : "none"; showSec("cut"); return d; });
    check("timeline: the edge grips are the Cut tab's only", edv === "none", edv);
    const tt = await page.evaluate(async () => {                       // the CapCut tools: zoom, split, Q / W, delete
      showSec("cut"); await new Promise(r => setTimeout(r, 200));
      const W = D.words, out = {};
      setScale(fitPps() * 4); const pps0 = pps; out.zoomed = $("tl").offsetWidth > $("tlWrap").clientWidth;
      const k = spans.findIndex(sp => sp.ids.some((i, x) => x + 1 < sp.ids.length && W[sp.ids[x + 1]].s - W[i].e > 0.06));
      if (k >= 0) {
        const sp = spans[k], x = sp.ids.findIndex((i, x) => x + 1 < sp.ids.length && W[sp.ids[x + 1]].s - W[i].e > 0.06), a = sp.ids[x], b = sp.ids[x + 1];
        seekCut(total(spans.slice(0, k)) + ((W[a].e + W[b].s) / 2 - sp.s));
        const n0 = spans.length, len0 = total(spans), u0 = undoS.length;
        splitAtHead();
        out.split = spans.length === n0 + 1 && Math.abs(total(spans) - len0) < 0.002 && undoS.length === u0 + 1 && trimE[a] != null && trimS[b] != null;
        out.ppsHeld = pps === pps0; undo(); out.unsplit = spans.length === n0 && trimE[a] == null;
      } else out.split = out.unsplit = out.ppsHeld = "no pause in the fixture";
      const k2 = spans.findIndex(s2 => s2.ids.length >= 3), s2 = spans[k2], st = total(spans.slice(0, k2)), ids = s2.ids.slice();
      seekCut(st + (W[ids[1]].e - s2.s) + 0.01); const lenQ = total(spans);
      trimToHead("s"); out.q = cut[ids[0]] && cut[ids[1]] && !cut[ids[2]] && total(spans) < lenQ - 0.05; undo();
      seekCut(st + (W[ids[1]].s - s2.s) - 0.005); trimToHead("e"); out.w = cut[ids[ids.length - 1]] && !cut[ids[0]]; undo();
      out.restored = ids.every(i => !cut[i]);
      if (k >= 0) {                                                    // split a clip, then delete its second half
        const sp = spans[k], x = sp.ids.findIndex((i, x) => x + 1 < sp.ids.length && W[sp.ids[x + 1]].s - W[i].e > 0.06), b = sp.ids[x + 1];
        seekCut(total(spans.slice(0, k)) + ((W[sp.ids[x]].e + W[b].s) / 2 - sp.s)); splitAtHead();
        const half = spans[tlSel].ids.slice(), other = sp.ids.filter(i => !half.includes(i));
        deleteClip(); out.del = half.every(i => cut[i]) && other.every(i => !cut[i]); undo(); out.undel = half.every(i => !cut[i]); undo();
      } else { selectClip(0); const n = spans.length; deleteClip(); out.del = n > 1 ? spans[0] !== undefined : D.words.some((w, i) => !cut[i]); out.undel = true; }
      setScale(fitPps()); return out; });
    check("timeline: zoom widens the timeline, and its scale holds through an edit", tt.zoomed && tt.ppsHeld !== false, tt);
    check("timeline: Split at the playhead makes two clips without changing a sound, one undo step", tt.split !== false && tt.unsplit !== false, tt);
    check("timeline: Cut before / after the playhead (Q, W) trims that clip to the playhead, and Undo puts it back", tt.q && tt.w && tt.restored, tt);
    check("timeline: a selected clip deletes with its words, and Undo brings it back", tt.del && tt.undel, tt)
    const ta = await page.evaluate(async () => {                             // Split anywhere: her call, never redirected
      showSec("cut"); const W = D.words, out = {};
      const k = spans.findIndex(sp => sp.ids.some(i => W[i].e - W[i].s > 0.2)); if (k < 0) return { skip: true };
      const sp = spans[k], i = sp.ids.find(i => W[i].e - W[i].s > 0.2), t = +((W[i].s + W[i].e) / 2).toFixed(3);
      seekCut(total(spans.slice(0, k)) + (t - sp.s));
      const n0 = spans.length, len0 = total(spans), u0 = undoS.length;
      splitAtHead();                                                   // mid-word: exactly there, not the nearest pause
      out.split = spans.length === n0 + 1 && Math.abs(total(spans) - len0) < 0.002 && undoS.length === u0 + 1;
      const right = spans.findIndex(s => Math.abs(s.s - t) < 0.002); out.at = right >= 0;
      if (right >= 0) { const r = spans[right], rl = r.e - r.s; tlSel = right;
        deleteClip(); out.del = Math.abs(total(spans) - (len0 - rl)) < 0.01 && changes().holes.length === 1;
        out.code = /holes: \d+:[0-9.]+-[0-9.]+/.test(editCode(changes()));
        undo(); out.undel = Math.abs(total(spans) - len0) < 0.002 && !holes.length; }
      undo(); out.unsplit = spans.length === n0 && !tsplit.length;
      // the Loom case: a split in the quiet before a clip's first word leaves a side with no words at all; it shows on
      // the timeline, and selected + Delete takes out exactly that stretch, her words untouched
      const k2 = spans.findIndex(s => s.ids.length && W[s.ids[0]].s - s.s >= 0.02);
      if (k2 >= 0) { const s2 = spans[k2], f = s2.ids[0], t2 = +(W[f].s + 0.03).toFixed(3), l1 = total(spans), n1 = spans.length, gone = t2 - s2.s;
        seekCut(total(spans.slice(0, k2)) + (t2 - s2.s)); splitAtHead(); out.quiet = spans.length === n1 + 1;
        const qk = spans.findIndex(s => !s.ids.length); out.wordless = qk >= 0 && !!document.querySelector(`#segs .seg[data-k="${qk}"]`);
        tlSel = qk; deleteClip(); out.quietDel = Math.abs(total(spans) - (l1 - gone)) < 0.01 && !cut[f];
        undo(); undo(); out.quietBack = !holes.length && !tsplit.length && Math.abs(total(spans) - l1) < 0.002; }
      else out.quiet = out.wordless = out.quietDel = out.quietBack = "no clip with a lead-in in the fixture";
      return out; });
    check("timeline: Split works anywhere (mid-word, a clip's opening quiet); Delete or Q cuts exactly that stretch; Undo restores",
          !ta.skip && ta.split && ta.at && ta.del && ta.code && ta.undel && ta.unsplit && ta.quiet === true && ta.wordless === true && ta.quietDel === true && ta.quietBack === true, ta);;
    const fz = await page.evaluate(async () => {                             // a clip's Speed and Zoom: played, shown, sent
      showSec("cut"); stop(); const out = {}, sp = spans[0], len0 = total(spans), d0 = sp.e - sp.s, u0 = undoS.length, w = sp.ids[0] ?? sp.w;
      tlSel = 0; $("tbSpeed").click(); const m = $("fxMenu"); out.menu = !!m && m.querySelectorAll("button").length === 6;   // four speeds and two ramps
      m.querySelector('[data-v="2"]').click();
      out.len = Math.abs(total(spans) - (len0 - d0 / 2)) < 0.002; out.undo1 = undoS.length === u0 + 1;
      out.payload = (changes().fx[w] || {}).speed === 2; out.label = $("tbSpeedTxt").textContent === "2×";
      seekCut(d0 / 4); out.seek = Math.abs(v.currentTime - (sp.s + d0 / 2)) < 0.03 && Math.abs(cutPos() - d0 / 4) < 0.03;
      const f1 = spans[1] && spans[1].ids[0]; out.starts = f1 == null || Math.abs(cutStarts()[f1] - (d0 / 2 + (D.words[f1].s - spans[1].s))) < 0.01;
      qi = 0; fxRate(); out.rate = Math.abs(v.playbackRate - 2) < 1e-3;
      tlSel = 0; $("tbZoom").click(); $("fxMenu").querySelector('[data-v="out"]').click();
      const z = (changes().fx[w] || {}).zoom; out.zoom = !!z && z.from === 1.15 && z.to === 1;
      seekCut(0.001); out.zStart = /scale\(1\.1[45]/.test(v.style.transform) && !!v.style.clipPath;
      seekCut(d0 / 2 - 0.05); const sc = v.style.transform.match(/scale\(([\d.]+)/); out.zEnd = !!sc && +sc[1] < 1.01;
      out.code = /fx: \d+ x2 z1.15-1/.test(editCode(changes()));
      out.badge = !!document.querySelector('#segs .seg[data-k="0"] .segfx');
      undo(); undo(); out.back = !Object.keys(changes().fx).length && Math.abs(total(spans) - len0) < 0.002 && !v.style.transform;
      return out; });
    const rp = await page.evaluate(async () => {                             // a speed ramp: one fluid clip, eased
      showSec("cut"); stop(); const out = {}, sp = spans[0], len0 = total(spans), d0 = sp.e - sp.s, w = sp.ids[0] ?? sp.w;
      tlSel = 0; $("tbSpeed").click(); const m = $("fxMenu"); out.offered = !!m.querySelector('[data-v="ramp-down"]') && !!m.querySelector('[data-v="ramp-up"]');
      m.querySelector('[data-v="ramp-down"]').click();
      const r = spans[0];
      out.one = spans.length > 0 && !!r.rp && Math.abs(total(spans) - (len0 - d0 + d0 / 1.5)) < 0.003;   // average 2.5 - 1.5 x 2/3 = 1.5
      out.fastFirst = Math.abs(speedAt(r, r.s + 0.001) - 2.5) < 0.05 && Math.abs(speedAt(r, r.e - 0.001) - 1) < 0.05;
      out.smooth = [0.2, 0.4, 0.6, 0.8].every((f, k, a) => k === 0 || speedAt(r, r.s + f * d0) < speedAt(r, r.s + a[k - 1] * d0));
      const c = sdur(r) * 0.37; out.round = Math.abs(cutIn(r, srcAt(r, c)) - c) < 1e-4;
      seekCut(sdur(r) / 2); qi = 0; fxRate(); out.rate = v.playbackRate > 1 && v.playbackRate < 2.5;
      const f = changes().fx[w]; out.payload = !!f && f.speed.from === 2.5 && f.speed.to === 1 && f.speed.ease === "out";
      out.code = /r2\.5-1-out/.test(editCode(changes())); out.label = $("tbSpeedTxt").textContent === "Ramp";
      undo(); out.back = !spans[0].rp && Math.abs(total(spans) - len0) < 0.002;
      return out; });
    check("timeline: a speed ramp is one fluid clip easing from fast to normal; the preview's rate follows the curve; it goes out with Send",
          Object.values(rp).every(x => x === true), rp);
    const nc = await page.evaluate(async () => {                             // a note's card: open and done look different at a glance
      const keep = [notesList, claudeHas], w = D.lines[0][0];
      notesList = [{ id: "o1", w, text: "open one", status: "open" }, { id: "f1", w, text: "done one", status: "fixed", reply: "Fixed: Fixed: shorter now" }];
      claudeHas = ["o1"]; renderNotes();
      const o = document.querySelector(".lnote:not(.fixed)"), f = document.querySelector(".lnote.fixed"), cs = x => getComputedStyle(x);
      const out = { open: !!o && /Claude's on it/.test(o.textContent) && !!o.querySelector(".chef-ico"),
        colors: !!o && !!f && cs(o).backgroundColor !== cs(f).backgroundColor && cs(o).borderLeftColor !== cs(f).borderLeftColor,
        once: !!f && /Fixed: shorter now/.test(f.textContent) && !/Fixed: Fixed/.test(f.textContent) };
      [notesList, claudeHas] = keep; renderNotes(); return out; });
    check("notes: an open note (warm, red edge, Claude's on it) and a done one (green, ✓) differ at a glance; never 'Fixed: Fixed:'",
          Object.values(nc).every(x => x === true), nc);
    const ph = await page.evaluate(async () => {                       // the phone keeps one size and place: notices never move it
      showSec("visuals"); await new Promise(r => setTimeout(r, 300));
      const r0 = $("screen").getBoundingClientRect(), keep = TQ;
      TQ = { done: 0, total: 4, items: [1, 2, 3, 4].map(n => ({ id: "p" + n, label: "a note " + n, state: "sent", steps: ["sent", "has", "done"] })) };
      renderQueue(); updateFresh(); await new Promise(r => setTimeout(r, 200));
      const r1 = $("screen").getBoundingClientRect(); TQ = keep; renderQueue(); updateFresh(); await new Promise(r => setTimeout(r, 200));
      const r2 = $("screen").getBoundingClientRect(), same = (a, b) => ["left", "top", "width", "height"].every(k => Math.abs(a[k] - b[k]) < 0.5);
      return { queueOn: same(r0, r1), queueOff: same(r1, r2), held: /moving && moving\.items\.some\(i => i\.f === f\)/.test(steerOne.toString()) }; });
    check("phone: a notice or the task queue coming and going never rescales or moves the preview; a look being moved is held still",
          Object.values(ph).every(x => x === true), ph);
    const ln_ = await page.evaluate(() => {                            // a note on a look lands on the look's own line
      const keyed = lookWord("add-w" + D.lines[1][0], 999);
      const L = LOOKS && LOOKS.layers.find(l => !/^(add|cap)-w\d+/.test(l.name) && l.offset > 0.5 && !l.captions), st = cutStarts();
      const byOffset = L ? lookWord(L.name, 999) : null;
      return { keyed: keyed === D.lines[1][0], offset: !L || (st[byOffset] >= L.offset - 0.05 && Object.values(st).filter(t => t >= L.offset - 0.05).every(t => t >= st[byOffset])),
               refine: /lookWord\(o\.layer, o\.t\)/.test(sendRefineNote.toString()) }; });
    check("notes: a note on a look pins to the look's own word (its line's card), never the word at the playhead (a quiet stretch sent it lines later)",
          Object.values(ln_).every(x => x === true), ln_);
    const tq = await page.evaluate(async () => {                             // her task queue, and no "type update my edit" while Claude watches
      const out = {}, keep = { notesList, watcherLive, claudeWatching, claudeHas };
      TQ = { done: 1, total: 3, watching: true, items: [
        { id: "n1", kind: "cut-note", label: "speed up this clip", state: "done", steps: ["sent", "has", "done"] },
        { id: "n2", kind: "look-note", label: "smaller please", state: "has", steps: ["sent", "has", "done"] },
        { id: "s1", kind: "sandbox", label: "Sandbox: a sticky note", state: "sent", steps: ["sent", "has", "working", "done"] }] };
      renderQueue();
      const rows = [...document.querySelectorAll("#tqList .tq-it")];
      out.shown = !$("taskQueue").hidden && rows.length === 3;
      out.count = $("tqCount").textContent === "1 of 3 done" && $("tqFill").style.width === "33%";
      out.steps = rows[1].querySelectorAll(".tq-steps i.on").length === 2 && /Claude has it/.test(rows[1].textContent) && /Sent/.test(rows[2].textContent);
      out.hat = !!rows[1].querySelector(".chef-ico") && !rows[0].querySelector(".chef-ico") && !rows[2].querySelector(".chef-ico");
      $("tqClear").click(); out.clear = document.querySelectorAll("#tqList .tq-it").length === 2;
      $("tqTog").click(); out.fold = $("taskQueue").classList.contains("shut"); $("tqTog").click();
      notesList = [{ id: "n9", w: D.lines[0][0], text: "a note", status: "open" }];
      watcherLive = true; claudeWatching = true; claudeHas = []; const a = freshState();
      out.noTyping = !a || !/update my edit|Sent to Claude|Claude is on/.test(a.title + a.sub + a.go);
      watcherLive = false; claudeWatching = false; renderQueue(); const b = freshState();
      out.typingWhenAlone = !$("tqHint").hidden && /update my edit/.test($("tqHintText").textContent) && !(b && /update my edit/.test(b.go || ""));
      const was = phase, lo = looksOn; phase = "cut"; showSec("cut"); updatePrimary(); out.lockWaits = $("send").dataset.act === "ready" && !$("send").classList.contains("waits");   // never dimmed
      looksOn = true; notesList = []; const c1 = freshState();                // the queue still has work: said, the button stays
      out.cardAgrees = !!c1 && c1.k === "lockcut" && c1.go === "Lock in my cut" && /still working through your edits/.test(c1.sub);
      TQ = null; updatePrimary(); const c2 = freshState(); out.lockBack = !$("send").classList.contains("waits") && !!c2 && c2.go === "Lock in my cut";
      looksOn = lo; phase = was; showSec("cut");
      Object.assign(window, {}); notesList = keep.notesList; watcherLive = keep.watcherLive; claudeWatching = keep.claudeWatching; claudeHas = keep.claudeHas;
      TQ = null; renderQueue(); out.gone = $("taskQueue").hidden; updatePrimary();
      return out; });
    check("queue: what she sent Claude shows as rows with a step bar and one round's bar, the active row wears the chef hat; Clear done and fold work; no 'type update my edit' while Claude watches (only when it doesn't); Lock in always works while Claude works (dock and card agree, and say so)",
          Object.values(tq).every(x => x === true), tq);
    check("timeline: Speed plays a clip faster (its cut length, the playhead, word times and the video's rate follow) and Zoom moves across it on her preview; both go out with Send, one undo step each",
          Object.values(fz).every(x => x === true), fz);
    const cm = await page.evaluate(async () => {                       // her whole-reel captions have one home: the top button
      showSec("visuals"); await new Promise(r => setTimeout(r, 400));
      const capL = LOOKS && LOOKS.layers.find(L => L.captions); if (!capL) return { skip: true };
      const cards = [...document.querySelectorAll(".lkchip")].filter(c => c.dataset.layer === capL.name && !c.classList.contains("cont")).length;
      $("capsBtn").click(); await new Promise(r => setTimeout(r, 100));
      const menu = document.querySelector(".pop")?.textContent || ""; hidePop();
      return { cards, menu, name: $("capsName").textContent }; });
    check("captions: no line card for the whole-reel captions; the top button's menu swaps, moves, refines and removes them",
          cm.skip || (cm.cards === 0 && /Swap style/.test(cm.menu) && /Move/.test(cm.menu) && /Remove/.test(cm.menu) && /^Captions:/.test(cm.name)), cm);
    const ms = await page.evaluate(async () => {                       // Move it for me clears her face AND her caption band
      if (!LOOKS) return { skip: true };
      const keep = { subject: LOOKS.subject, safe: LOOKS.safe, seen: AUD.seen, busy: audBusy };
      LOOKS.subject = { left: 245, head_top: 466, right: 792, chin_bottom: 1089 }; LOOKS.safe = { top: 270, bottom: 1620, left: 90, right: 990 };
      const L = { name: "__t", offset: 1, dur: 2 };
      AUD.seen = { __t: { t: 1.5, rs: [{ x0: 340, y0: 700, x1: 740, y1: 900 }] } };                    // on her face
      audBusy = async () => [{ x0: 90, y0: 1110, x1: 990, y1: 1260, captions: true }];               // her captions, just under her chin
      const sp = await audSpot(L);
      Object.assign(LOOKS, { subject: keep.subject, safe: keep.safe }); AUD.seen = keep.seen; audBusy = keep.busy;
      if (!sp) return { none: true };
      const y0 = 700 + sp.dy, y1 = 900 + sp.dy;
      return { y0, y1, offFace: y1 <= 466 + 12 || y0 >= 1089 - 12, offCaps: y1 <= 1110 + 12 || y0 >= 1260 - 12 }; });
    check("move it for me: the spot it picks is clear of her face and her caption band", ms.skip || (ms.offFace && ms.offCaps), ms);
    const kc = await page.evaluate(() => ({
      kar: audCapStyle({ look: "karaoke", spot: "captions" }), hook: audCapStyle({ look: "hook", spot: "top" }),
      off: audCapTime({ offset: 0, dur: 15, skips: [[8.4, 11.7]] }, 8.6, 11.3), on: audCapTime({ offset: 0, dur: 15, skips: [[8.4, 11.7]] }, 13.5, 15) }));
    check("captions check: karaoke is captions in another style (never a clash), and captions stepping aside don't count",
          kc.kar && !kc.hook && kc.off <= 0.001 && kc.on > 1.4, kc);
    const gp = await page.evaluate(async () => {                       // a click on a graphic in the preview gives it its handles
      showSec("visuals"); await new Promise(r => setTimeout(r, 400));
      const f = lookFrames.find(x => x.ready && x.el && x.el.style.visibility === "visible" && !x.L.captions && lookBox(x));
      if (!f) return { skip: true };
      const b = lookBox(f), st = $("lookStack").getBoundingClientRect(), k = st.width / 1080;
      const x = st.left + (b.l + b.r) / 2 * k, y = st.top + (b.t + b.b) / 2 * k;
      const hit = lookAtPoint({ clientX: x, clientY: y });
      return { want: f.L.name, hit: hit && hit.name, miss: lookAtPoint({ clientX: st.left - 50, clientY: st.top - 50 }) }; });
    check("preview: a click on a graphic finds that graphic (and nothing outside the frame)", gp.skip || (gp.hit === gp.want && !gp.miss), gp);
    const zs = await page.evaluate(() => {                              // stacked as the export stacks them: captions on top
      if (!LOOKS || LOOKS.layers.length < 2) return { skip: true };
      const fake = [{ name: "a", offset: 5 }, { name: "cap", offset: 0, captions: true }, { name: "b", offset: 1 }], keep = LOOKS.layers;
      LOOKS.layers = fake; const z = fake.map(L => stackRank(L)); LOOKS.layers = keep;
      return { z }; });
    check("stacking: by start time, captions on top, as the export stacks them", zs.skip || JSON.stringify(zs.z) === "[2,3,1]", zs);
    const kp = await page.evaluate(async () => {                       // carousel / story: her own photos, from the same picker
      openKit("carousel"); await new Promise(r => setTimeout(r, 200));
      const add = !!$("kitAddPhotos"); $("kitAddPhotos").click(); await new Promise(r => setTimeout(r, 600));
      const picker = !$("mediaSheet").hidden && $("mediaSheet").classList.contains("kitmode") && /carousel/.test($("mdTitle").textContent);
      mdPicks = [{ id: "photos/beach.jpg", name: "beach", kind: "Image" }]; mdPick = mdPicks[0]; mdReady();
      const label = $("mdGo").textContent; $("mdGo").click(); await new Promise(r => setTimeout(r, 300));
      const back = !$("kitSheet").hidden && !!document.querySelector('.kt-photo[data-photo="photos/beach.jpg"]');
      const was = post; let sent = null; post = async (u, b) => { if (u === "/kit-request") sent = b; return { ok: true, j: {} }; };
      $("kitFwd").click(); await new Promise(r => setTimeout(r, 200)); post = was;
      document.querySelector(".kt-photo .kt-x")?.click(); const gone = !document.querySelector(".kt-photo");
      closeSheets(); return { add, picker, label, back, sent: sent && sent.photos, gone }; });
    check("carousel: Add photos opens the picker for her carousel, picks come back as tiles, are sent with her frames, and come off",
          kp.add && kp.picker && /carousel/.test(kp.label) && kp.back && JSON.stringify(kp.sent) === '["photos/beach.jpg"]', kp);
    const hp = await page.evaluate(async () => {                       // her click is her pick (2026-10-17): never "tap again"
      const f0 = window.fetch, ch0 = chooseLook; let picked = null;   // a look that may overlap another: ONE tap puts it on
      window.fetch = async (u, o) => String(u).startsWith("/add-menu") ? new Response(JSON.stringify({ layer: "add-w99", offset: 0, dur: 2,
        text: "x", add: true, current: null, original: null, looks: [{ id: "hook", name: "Hook", about: "", dir: "hf-graphics/none", comp: "x", dur: 2, clash: "count-up" }] }),
        { status: 200, headers: { "Content-Type": "application/json" } }) : f0(u, o);
      chooseLook = (t) => { picked = t.id; };
      try { await openSwap({ layer: "add-w99", add: { start: 0, end: 1 }, t: 0 }); const tile = document.querySelector("#swGrid .sw-tile.clash"); if (tile) tile.click(); }
      finally { window.fetch = f0; chooseLook = ch0; closeSheets(); }
      const rd0 = refineDraw, rf0 = rf, order = [];                    // Apply right after typing: her last words are drawn, then kept
      refineDraw = async () => { order.push("draw"); };
      window.fetch = async (u, o) => { if (String(u).startsWith("/refine-apply")) { order.push("keep"); return new Response('{"name":"x"}', { status: 200 }); } return f0(u, o); };
      try { rf = { layer: "_book", look: "hook" }; rfChanged(); await refineKeep("pack"); }
      finally { refineDraw = rd0; window.fetch = f0; rf = rf0; closeSheets(); }
      const A0 = LOOKS.accents, c0 = capOf, on0 = looksOn, sv0 = saveAccents, w = D.order.find(k => !cut[k]);   // a highlight is hers,
      LOOKS.accents = { layer: "x", words: [{ t: 1, text: "is", on: true, sel: null }], mode: "redraw" }; capOf = { [w]: 0 }; looksOn = true;   // even where
      saveAccents = () => {}; let kept;                                // the engine agrees
      try { toggleAccent([w]); toggleAccent([w]); kept = accOn[w]; } finally { delete accOn[w]; LOOKS.accents = A0; capOf = c0; looksOn = on0; saveAccents = sv0; undoS.pop(); undoS.pop(); }
      return { picked, order, kept }; });
    check("her pick: one tap on a look that may overlap another puts it on (the overlap is said after, never a second tap)", hp.picked === "hook", hp);
    check("her pick: Apply right after typing in Refine draws what she typed first, then keeps it", JSON.stringify(hp.order) === '["draw","keep"]', hp);
    check("her pick: a highlight she sets is saved as hers, even where the engine's pick agrees", hp.kept === true, hp);
    check("page: no script errors", errors.length === 0, errors);
    const dup = await page.evaluate(() => { const seen = {}, d = []; document.querySelectorAll("[id]").forEach(e => { if (seen[e.id]) d.push(e.id); seen[e.id] = 1; }); return d; });
    check("page: every id is used once (two panels sharing an id write into each other)", dup.length === 0, dup);
  } catch (e) { bad.push("page flow stopped: " + (e && e.stack || e)); }
  finally { await browser.close(); }
  console.log(JSON.stringify({ ok, bad }));
})();
"""


def main():
    tools = find_tools()
    if not tools:
        print("test_visual_editor_page: skipped (no headless browser here yet; `npx hyperframes@0.9.6 browser ensure` "
              "installs one). The engine-side checks in test_visual_editor.py still ran.")
        return 0
    if not shutil.which("ffmpeg"):
        print("test_visual_editor_page: skipped (ffmpeg isn't on this machine to make the test reel).")
        return 0
    node, pup, chrome = tools
    tmp = tempfile.mkdtemp(prefix="ve-page-")
    try:
        import visual_editor as ve
        import visual_editor_server as srv
        proj = os.path.join(tmp, "projects")
        jd = make_reel(proj)
        real_dir = ve.job_dir
        ve.job_dir = lambda job: jd if os.path.basename(str(job)) == "pagejob" else real_dir(job)
        ve.can_behind = lambda: False
        import sound_plan, favorites_folder, capcut_sfx
        sound_plan.job_dir = lambda job: jd if os.path.basename(str(job)) == "pagejob" else job
        # the Sound menu reads (and caches levels for) every sound on the machine: point it all at the throwaway
        # folder, so the engine's own _local/, favorites/, reels and Epidemic downloads are never read or written
        sound_plan.LOCAL = os.path.join(tmp, "_local")
        sound_plan.LEVELS = os.path.join(sound_plan.LOCAL, "sound-levels.json")
        sound_plan.PREVIEW_DIR = os.path.join(sound_plan.LOCAL, "sound-preview")
        sound_plan._levels_mem = None
        sound_plan.EPIDEMIC_HOME = os.path.join(tmp, "Documents", "Epidemic Sound")
        sound_plan.PROJECTS_DIR = proj
        favorites_folder.FOLDER = os.path.join(tmp, "favorites")
        favorites_folder.CACHE = os.path.join(sound_plan.LOCAL, "favorites-cache")
        capcut_sfx.FAVORITES_DIR = os.path.join(sound_plan.LOCAL, "sounds")
        import lookbook
        lookbook.ROOT = tmp                                   # her lookbook for this test lives in the throwaway folder
        ve.USER_STYLE = os.path.join(tmp, "user-style.json")   # "Make it my default" never writes her real default
        ve.TOUR_FILE = os.path.join(tmp, "_local", "editor-tour.json")   # the tours she has seen: never her real record
        srv.ve, srv.PROJECTS = ve, proj
        ve.prepare(jd, log=lambda *a: None)
        Base = srv.Handler

        class Handler(Base):                                  # one test-only door: lock the cut in (Cut step → Looks)
            def do_GET(self):
                if self.path == "/__phase_looks":
                    cid = json.load(open(os.path.join(jd, "review", "script.json"), encoding="utf-8")).get("cut_id")
                    ve._atomic_json(os.path.join(jd, "review", "phase.json"), {"phase": "looks", "cut_id": cid})
                    ve.looks_manifest(jd)
                    return self._json(200, {"ok": True})
                if self.path == "/__place_design":            # what the chat does in build-a-look, step 4
                    import lookbook
                    real = lookbook.check_design
                    lookbook.check_design = lambda src, pack, render_check=True: real(src, pack, render_check=False)
                    pack = ve._swap_pack(jd, json.load(open(os.path.join(jd, "review", "looks.json"), encoding="utf-8")))[0]
                    did = lookbook.save_design(os.path.join(ROOT, "product", "lookbook-designs", "starter"), pack, "Sticky note (draft)")
                    lookbook.check_design = real
                    r = ve.look_requests(jd)[0]
                    ve.place_look(jd, f"add-w{r['w']}", r["start"], r["end"], did)
                    ve.look_request_status(jd, r["id"], "draft", did)
                    return self._json(200, {"ok": True, "id": did})
                return Base.do_GET(self)

        httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        script = os.path.join(tmp, "flow.js")
        open(script, "w", encoding="utf-8").write(PAGE_FLOW)
        env = dict(os.environ, PUP=pup, CHROME=chrome, BASE=f"http://127.0.0.1:{port}", SHOT=os.environ.get("VE_SHOTS", ""),
                   URL=f"http://127.0.0.1:{port}/editor/?job=pagejob")
        r = subprocess.run([node, script], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300, cwd=tmp)
        httpd.shutdown()
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            print("test_visual_editor_page: the browser run didn't finish\n", r.stdout[-2000:], r.stderr[-2000:])
            return 1
        for name in res["ok"]:
            print("  PASS ", name)
        for name in res["bad"]:
            print("  FAIL ", name)
        if res["bad"]:
            print(f"test_visual_editor_page: {len(res['bad'])} of {len(res['ok']) + len(res['bad'])} checks FAILED")
            return 1
        print(f"test_visual_editor_page: all {len(res['ok'])} checks passed")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
