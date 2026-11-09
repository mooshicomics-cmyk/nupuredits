// The visual editor's JOURNEY: one reel, walked tab by tab with the mouse and the keyboard, the way a person edits.
// Started by test_editor_journey.py (which serves the reel and plays Claude's side); prints {ok, bad} as one JSON line.
//
// Every step is  step(name, act, want)  : `act` clicks and types; then the SAME checks run after every step:
//   errors    no script error, no console error, no failed request, nothing the page told the engine went wrong
//   playhead  it stays put unless the step says it moves (want.moves: true, or the cut second it lands on)
//   captions  her captions hide exactly while a word look plays; never two caption styles on screen at once
//   lock in   the dock's button, the card above her preview and the tabs agree on whether she can lock in
//   queue     the "With Claude" rows match what she sent and how far each got (want.queue)
//   frames    every look on the preview is the copy on disk right now (no stale cached page)
// want.sweep runs the captions check across the whole reel, not just at the playhead; want.wrap checks no word on a
// look breaks across two lines ("THI / S").
//
// REPORTED: every bug a creator reports becomes a step named "REPORTED <date>: <what she saw>". Never delete one.
// Add the next one in the tab it happened on, and make it fail on the old page before you fix the page.
"use strict";
const { createRequire } = require("module");
const puppeteer = createRequire(process.env.PUP + "/")(process.env.PUP);
const BASE = process.env.BASE, URL = process.env.URL, UNTIL = (process.env.UNTIL || "").toLowerCase();   // stop after that step
const MOD = process.env.PLAT === "darwin" ? "Meta" : "Control";
const ok = [], bad = [], open = [], fixed = [], T0 = Date.now();
// KNOWN: reported, reproduced here, and not fixed yet (each needs the creator's call on what the page should do). A
// known check that fails prints as OPEN and doesn't fail the gate; once it passes it prints NOW PASSES: take it off
// this list then, so it guards like every other check from there on. Never add a check here to get a release out.
const KNOWN = {
  // (empty: every reported bug passes)
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => process.stderr.write(`[${((Date.now() - T0) / 1000).toFixed(1)}s] ${a.join(" ")}\n`);
let page, errs = [], http = [], stepN = 0, stopNow = false;
class Stop extends Error {}

const check = (name, cond, detail) => {
  const known = KNOWN[name];
  if (known && cond) { fixed.push(name); return; }
  (cond ? ok : known ? open : bad).push(cond ? name : `${name}  -- ${known ? known + " -- " : ""}${detail === undefined ? "" : JSON.stringify(detail).slice(0, 700)}`);
  if (!cond) log(known ? "OPEN" : "FAIL", name, JSON.stringify(detail === undefined ? "" : detail).slice(0, 400));
};
const ev = (fn, ...a) => page.evaluate(fn, ...a);
const claude = async (op, q = "") => { const r = await fetch(`${BASE}/__claude?do=${op}${q}`); const j = await r.json(); if (!r.ok) throw new Error(`claude ${op}: ${j.error}\n${j.trace || ""}`); return j; };
// Waits are on the page's real state, with a generous ceiling: a busy machine only makes a step slower, never wrong
// (2026-10-18: a busy machine failed a release build on a menu a late reload closed, and on a look still being drawn).
const JOB = decodeURIComponent((/[?&]job=([^&]+)/.exec(URL) || [, ""])[1]);
const inflight = new Set(); let netAt = 0;                      // the page's own requests to the engine, still on the way
const engineReq = r => r.url().startsWith(BASE) && !/__claude/.test(r.url()) && !/\.(mp4|mov|m4a|wav|mp3|jpg|png|webp)(\?|$)/.test(r.url()) && r.resourceType() !== "document";
async function netIdle(ms = 30000) {                            // everything the page sent has its answer
  const end = Date.now() + ms;
  while (inflight.size && Date.now() < end) await wait(50);
  return !inflight.size;
}
const beat = async () => { await netIdle(); return ev(() => heartbeat()); };   // the page's own 3 s status beat, now (not a click: a wait)
const status = async () => { try { const r = await fetch(`${BASE}/status?job=${encodeURIComponent(JOB)}`); return r.ok ? await r.json() : null; } catch (e) { return null; } };
// Quiet: the engine has finished (no cut being made, nothing the page sent still on the way), the page shows the looks
// the engine has on disk right now (same list, same page versions), and every look frame on screen is drawn. A step
// starts from quiet and its checks read quiet, so a late reload can never land in the middle of a click.
async function quiet(ms = 30000) {
  const end = Date.now() + ms; let nudged = 0, last = null;
  while (Date.now() < end) {
    await netIdle(Math.max(0, end - Date.now()));
    const st = await status();
    const pg = await ev(() => ({ at: typeof looksAt === "undefined" ? null : looksAt, held: !!moving || document.body.classList.contains("sheet-open"),
      vs: LOOKS ? Object.fromEntries(LOOKS.layers.map(L => [L.name, L.v || null])) : null,
      drawn: !looksOn || !LOOKS || lookFrames.every(f => !f.el || f.ready || f.broken) })).catch(() => null);
    const behind = !!st && !!pg && !pg.held && (st.looks_at ?? null) !== (pg.at ?? null);
    const stale = !!st && !!pg && !!pg.vs && Object.entries(st.looks_v || {}).some(([n, v]) => n in pg.vs && v && pg.vs[n] !== v);
    if (st && pg && !st.making && !behind && !stale && pg.drawn && !inflight.size && Date.now() - netAt > 150) return true;
    last = { making: st && st.making, behind, stale, drawn: pg && pg.drawn, inflight: [...inflight].map(r => r.url().replace(BASE, "")) };
    if ((behind || stale) && Date.now() - nudged > 1000) { nudged = Date.now(); await beat().catch(() => {}); }   // catch up now, not in 3 s
    else await wait(100);
  }
  log("not quiet after", ms, "ms:", JSON.stringify(last));
  return false;
}
async function stillThere(path, ms = 15000) {                  // a look's still the page asked for early: drawn yet?
  const end = Date.now() + ms;
  do { try { const r = await fetch(BASE + path, { cache: "no-store" }); if (r.ok) return true; } catch (e) {} await wait(250); } while (Date.now() < end);
  return false;
}
async function until(fn, ms = 15000, arg) {                     // wait for the page to get there, like a person would
  const end = Date.now() + ms; let v;
  while (Date.now() < end) { v = await ev(fn, arg).catch(() => null); if (v) return v; await wait(120); }
  return v;
}

// ── a person's hands ──────────────────────────────────────────────────────────────────────────────────────────────
async function box(sel, ms = 15000) {                           // the thing she reaches for, once it is on screen
  const end = Date.now() + ms;
  for (;;) {
    const h = typeof sel === "string" ? await page.$(sel) : sel;
    let b = null;
    if (h) { await h.evaluate(el => el.scrollIntoView({ block: "center", inline: "center" })).catch(() => {}); b = await h.boundingBox().catch(() => null); }
    if (b && b.width) return b;
    if (Date.now() >= end || typeof sel !== "string") throw new Error(h ? `${sel} is not visible` : `nothing on the page matches ${sel}`);
    await wait(100);
  }
}
async function click(sel, o = {}) { const b = await box(sel); await page.mouse.click(b.x + b.width * (o.fx ?? 0.5), b.y + b.height * (o.fy ?? 0.5), o); await wait(o.after ?? 180); }
async function dblclick(sel) { const b = await box(sel); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { clickCount: 2 }); await wait(250); }
const word = i => click(`.w[data-i="${i}"]`);
const pop = a => click(`.pop [data-a="${a}"]`);
const tab = s => click(`.secs .sec[data-sec="${s}"]`, { after: 450 });
async function key(k, mod) { if (mod) await page.keyboard.down(mod); await page.keyboard.press(k); if (mod) await page.keyboard.up(mod); await wait(250); }
async function drag(from, to, steps = 8) { await page.mouse.move(from.x, from.y); await page.mouse.down(); await page.mouse.move(to.x, to.y, { steps }); await page.mouse.up(); await wait(300); }
async function seekTo(c) {                                     // a click on the ruler, at that second of her cut
  const b = await box("#ruler"), len = await ev(() => total(spans));
  await page.mouse.click(b.x + Math.max(1, Math.min(b.width - 1, c / len * b.width)), b.y + b.height / 2); await wait(200);
}
async function pickTile(name) {                                 // a look in the Swap sheet, by its name
  await until(() => document.querySelectorAll("#swGrid .sw-tile:not(.off)").length, 30000);
  const h = await page.evaluateHandle(n => [...document.querySelectorAll("#swGrid .sw-tile:not(.off)")].find(t => t.querySelector(".sw-name")?.textContent.trim() === n), name);
  if (!h.asElement()) throw new Error(`no ${name} in the Swap sheet`);
  await click(h.asElement(), { after: 400 });
}
async function looksReload(act, ms = 30000) {                  // a change the engine redraws: the page reloads her looks
  const v0 = await ev(() => looksVer); await act();
  await until(v => looksVer > v, ms, v0); return looksSettled();
}
async function looksSettled(ms = 30000) {                       // her looks reloaded and every frame on screen is drawn
  return until(() => looksOn && LOOKS && lookFrames.length && lookFrames.every(f => !f.el || f.ready || f.broken), ms);
}

// ── the checks that run after every step (inside the page: what she sees, measured) ─────────────────────────────────
function pageState(at) {
  const vis = f => f.el && f.ready && f.el.style.visibility === "visible";
  const shows = f => {                                          // the frame draws something right now (root shown, ink in it)
    try { const d = f.el.contentDocument, r = d.getElementById("root"); if (!r) return false;
      const cs = d.defaultView.getComputedStyle(r); if (+cs.opacity < 0.02 || cs.visibility === "hidden") return false;
      return f.clips.some(n => n.style.visibility !== "hidden" && n.textContent.trim() && +d.defaultView.getComputedStyle(n).opacity > 0.02) || !f.clips.length && !!r.textContent.trim();
    } catch (e) { return false; } };
  const c = at == null ? cutPos() : at, capL = LOOKS && LOOKS.layers.find(l => l.captions);
  const capish = f => f.L.captions || /^cap-/.test(f.L.name);
  const inSkip = (t, m) => !!capL && (capL.skips || []).some(([a, b]) => t > a + m && t < b - m);
  const showing = looksOn ? lookFrames.filter(f => vis(f) && shows(f)) : [];
  const card = $("staleBadge");
  return {
    head: +c.toFixed(3), playing, sec, phase, making, looksOn, moving: !!moving, active: moving && moving.active && moving.active.L.name,
    lt: $("lookTools").hidden ? null : $("lookTools").dataset.layer,
    caps: showing.filter(capish).map(f => f.L.name), words: showing.filter(f => !capish(f)).map(f => f.L.name),
    capWhole: !!capL && showing.some(f => f.L === capL || f.L.name === capL.name), skipHere: inSkip(c, 0.06), nearSkip: inSkip(c, -0.06) !== inSkip(c, 0.06),
    send: { act: $("send").dataset.act, waits: $("send").classList.contains("waits"), text: $("send").innerText.trim(), disabled: $("send").disabled },
    card: card.hidden ? null : { k: card.dataset.k, title: $("sbTitle").textContent, sub: $("sbSub").textContent, go: $("sbGo").hidden ? "" : $("sbGoText").textContent },
    lockWait: typeof lockWait === "function" ? lockWait() : null, openNotes: openNotes().length, edits: hasEdits(),
    queue: $("taskQueue").hidden ? [] : [...document.querySelectorAll("#tqList .tq-it")].map(li => li.querySelector(".tq-lab").textContent.trim() + " | " + li.querySelector(".tq-st").textContent.trim()),
    toast: $("toast").hidden ? "" : $("toast").textContent.trim(), problem: $("problemnote").hidden ? "" : $("problemText").textContent,
    says: $("saysBox").hidden ? null : { title: $("saysBox").querySelector(".says-title")?.textContent || "", text: $("saysBox").querySelector(".says-line")?.textContent || "",
      go: $("saysBox").querySelector(".says-go")?.textContent || "", more: $("saysBox").querySelector(".says-more")?.textContent || "" },
  };
}
async function framesFresh() {                                  // each look on the preview IS the page on disk now
  const out = [];
  for (const f of lookFrames) {
    if (!f.el || !f.ready) continue;
    const want = new URL(lookUrl(f.L), location.href).pathname, got = new URL(f.el.src, location.href).pathname;
    if (want !== got) { out.push(`${f.L.name}: shows ${got}, the look is ${want}`); continue; }
    const disk = await (await fetch(lookUrl(f.L), { cache: "no-store" })).text();
    const sk = h => ((h.match(/<script id="ve-skips">[\s\S]*?<\/script>/) || [""])[0]);
    const live = f.el.contentDocument.documentElement.outerHTML;
    if (sk(disk) !== sk(live)) out.push(`${f.L.name}: an old copy (its caption step-asides differ from the file)`);
    const tx = h => (h.match(/data-composition-id="[^"]+"/) || [""])[0];
    if (tx(disk) !== tx(live)) out.push(`${f.L.name}: an old copy (another composition)`);
  }
  return out;
}
async function sweepCaptions() {                                // the captions check at every 0.1 s of her cut
  const len = total(spans), bad = [], was = cutPos();
  lookFrames.forEach(f => { if (!f.el && !f.L.off) makeFrame(f); });
  for (let k = 0; k < 100 && !lookFrames.every(f => f.L.off || f.ready || f.broken); k++) await new Promise(r => setTimeout(r, 100));
  for (let c = 0.05; c < len; c += 0.1) {
    steerLooks(c); qi = Math.max(0, spans.findIndex((s, k) => total(spans.slice(0, k + 1)) > c));
    const s = window.__ps(c);
    if (s.nearSkip) continue;                                   // within a frame of an edge: either is right
    if (s.caps.length > 1) bad.push(`${c.toFixed(1)}s: two caption styles at once (${s.caps.join(", ")})`);
    if (s.skipHere && s.capWhole) bad.push(`${c.toFixed(1)}s: her captions show under a word look`);
    if (s.words.some(n => LOOKS.layers.find(l => l.name === n && l.look && /^(karaoke|single-word|phrase|spotlight|takeover)$/.test(l.look))) && !s.skipHere)
      bad.push(`${c.toFixed(1)}s: a word look plays and her captions were never told to step aside (${s.words.join(", ")})`);
  }
  seekCut(was); steerLooks(was);
  return bad;
}
function wrapCheck() {                                         // no word's letters on two lines in any look on screen
  const out = [];
  lookFrames.forEach(f => { if (!f.el || !f.ready) return; const d = f.el.contentDocument;
    d.querySelectorAll(".tfxw").forEach(w => { const tops = [...w.querySelectorAll("i.tfx")].map(i => i.offsetTop);   // layout, not the animation's transform
      if (tops.length > 1 && Math.max(...tops) - Math.min(...tops) > 4) out.push(`${f.L.name}: "${w.textContent}" breaks across lines`); });
    d.querySelectorAll("i.tfx").forEach(i => { if (!i.closest(".tfxw") && /\w/.test(i.textContent) && i.textContent.length === 1 && i.parentElement && !i.parentElement.closest(".tfxw")) {
      const p = i.parentElement; if (getComputedStyle(p).whiteSpace !== "nowrap") out.push(`${f.L.name}: letters of a word sit loose (no unbreakable box)`); } });
  });
  return [...new Set(out)];
}

async function step(name, act, want = {}) {
  stepN++;
  if (stopNow) throw new Stop();
  if (UNTIL && name.toLowerCase().includes(UNTIL)) stopNow = true;
  log(`step ${stepN}: ${name}`);
  await quiet();                                                // the last step's work has all landed before this one starts
  const e0 = errs.length, h0 = http.length;
  const before = await ev(() => window.__ps());
  let res, threw = null;
  try { res = await act(before); } catch (e) { threw = e; }
  if (want.settle !== false) { await wait(want.wait ?? 250); await quiet(); }
  const s = await ev(() => window.__ps()).catch(e => ({ broken: String(e) }));
  if (threw) { check(`${name}: the step ran`, false, String(threw && threw.stack || threw).slice(0, 600)); }
  // errors
  const frames = await ev(() => (LOOKS && LOOKS.moments || []).map(m => m.frame).filter(Boolean)).catch(() => []);
  const newErr = errs.slice(e0), newHttp = [];
  for (const h of http.slice(h0)) {
    if ((want.http || []).some(rx => rx.test(h))) continue;
    const m = /^404 GET (\S*\/review\/(look-\d+\.jpg))/.exec(h);
    if (m && !frames.includes(m[2])) continue;                  // a superseded list's still
    if (m && await stillThere(m[1])) continue;                  // asked for while the engine was still drawing it: it's there now
    newHttp.push(h);                                            // a still her list names that never got made: a real fault
  }
  check(`${name}: no page errors`, !newErr.length && !newHttp.length, newErr.concat(newHttp));
  check(`${name}: no problem said on the page`, !s.problem, s.problem);
  // playhead
  if (want.moves === undefined || want.moves === false) {
    if (!before.playing && !s.playing) check(`${name}: the playhead stayed put`, Math.abs(s.head - before.head) < 0.06, { before: before.head, after: s.head });
  } else if (typeof want.moves === "number") check(`${name}: the playhead lands at ${want.moves.toFixed(2)}s`, Math.abs(s.head - want.moves) < 0.15, { before: before.head, after: s.head });
  // the look she grabbed
  if (want.active) check(`${name}: the look she grabbed is the one selected`, s.active === want.active, { active: s.active, want: want.active });
  // captions at the playhead
  if (s.looksOn && !s.nearSkip) {
    check(`${name}: one caption style at a time on the preview`, s.caps.length <= 1, s.caps);
    check(`${name}: her captions are hidden while a word look plays`, !(s.skipHere && s.capWhole), s);
  }
  // Lock in agrees everywhere
  if (s.phase === "cut" && s.sec === "cut" && !s.edits && !s.making && s.send.act === "ready") {
    check(`${name}: Lock in is never dimmed (her call, notes or no notes)`, !s.send.waits, s);
    if (s.card && s.card.k === "lockcut")
      check(`${name}: the card and the dock's Lock in agree`, /Claude is working/.test(s.card.title) === s.send.waits && !(s.send.waits && /Lock in/.test(s.card.go)), { card: s.card, send: s.send });
  }
  if (s.card) check(`${name}: never 'type update my edit' while Claude is watching`, !(want.watching && /update my edit/.test(s.card.title + s.card.go)), s.card);
  // queue
  if (want.queue !== undefined) {
    const q = s.queue;
    const okq = typeof want.queue === "function" ? want.queue(q) : Array.isArray(want.queue) ? want.queue.length === q.length && want.queue.every((rx, i) => rx.test(q[i])) : q.length === want.queue;
    check(`${name}: the task queue shows the right rows`, okq, q);
  }
  if (want.fresh) { const st = await ev(framesFresh); check(`${name}: every look on the preview is the current one (no stale copy)`, !st.length, st); }
  if (want.sweep) { const sw = await ev(sweepCaptions); check(`${name}: captions step aside exactly for word looks, across the whole reel`, !sw.length, sw.slice(0, 6)); }
  if (want.wrap) { const wr = await ev(wrapCheck); check(`${name}: no word breaks across two lines on any look`, !wr.length, wr); }
  if (want.then) await want.then(s, res, before);
  if (process.env.SHOT) await page.screenshot({ path: `${process.env.SHOT}/${String(stepN).padStart(2, "0")}.png` }).catch(() => {});
  return s;
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell",
    args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required", "--mute-audio", "--disable-audio-output"] });
  try {
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    page.on("pageerror", e => errs.push("script error: " + String(e.message || e).slice(0, 300)));
    page.on("console", m => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push("console: " + m.text().slice(0, 300)); });
    page.on("requestfailed", r => { const u = r.url(); if (!/\.(mp4|mov|m4a|wav|mp3)(\?|$)/.test(u) && !/net::ERR_ABORTED/.test(r.failure()?.errorText || "")) http.push(`request failed: ${u.replace(BASE, "")} ${r.failure()?.errorText}`); });
    page.on("response", r => { if (r.status() >= 400 && !/__claude/.test(r.url()) && !(r.status() === 404 && /\/review\/(faces|looks)\.json(\?|$)/.test(r.url()))) http.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, "")}`); });
    page.on("dialog", d => { errs.push("a browser dialog: " + d.message()); d.dismiss(); });
    page.on("request", r => { if (engineReq(r)) inflight.add(r); });
    const landed = r => { if (inflight.delete(r)) netAt = Date.now(); };
    page.on("requestfinished", landed); page.on("requestfailed", landed); page.on("response", r => landed(r.request()));   // an answer's headers are its landing (a 404 may never "finish")
    page.on("framenavigated", f => { if (f === page.mainFrame()) inflight.clear(); });   // a reload drops what the old page asked
    const boot = async () => {
      await page.goto(URL, { waitUntil: "networkidle2" });
      await until(() => typeof D !== "undefined" && D && spans.length, 30000);
      await ev(new Function(`window.__ps = ${pageState.toString()};`));
      await ev(src => { eval(src); }, `${framesFresh.toString()}; ${sweepCaptions.toString()}; ${wrapCheck.toString()}; window.framesFresh = framesFresh; window.sweepCaptions = sweepCaptions; window.wrapCheck = wrapCheck;`);
      if (await ev(() => !$("tour").hidden)) await click("#tourSkip", { after: 400 });   // her first visit: the tour, skipped
    };
    page.on("framenavigated", f => { if (f === page.mainFrame()) page.__reloaded = (page.__reloaded || 0) + 1; });
    await boot();
    const reboot = async () => {                               // the page reloads itself onto a new cut: re-arm the checks
      await until(() => typeof D !== "undefined" && D && spans.length, 30000);
      await ev(new Function(`window.__ps = ${pageState.toString()};`));
      await ev(src => { eval(src); }, `${framesFresh.toString()}; ${sweepCaptions.toString()}; ${wrapCheck.toString()}; window.framesFresh = framesFresh; window.sweepCaptions = sweepCaptions; window.wrapCheck = wrapCheck;`);
    };
    const reloadsTo = async (ms = 30000) => { const n = page.__reloaded || 0; const end = Date.now() + ms;
      while (Date.now() < end && (page.__reloaded || 0) === n) await wait(150);
      await page.waitForFunction(() => document.readyState === "complete", { timeout: 30000 }).catch(() => {}); await reboot(); return (page.__reloaded || 0) > n; };
    const W = await ev(() => D.words.map((w, i) => ({ i, t: w.t, k: w.k, q: !!w.q })));
    const idx = (t, n = 0) => W.filter(w => w.t === t)[n].i;

    // ═══ CUT ══════════════════════════════════════════════════════════════════════════════════════════════════════
    await step("cut: the page opens on her cut, every line and clip there", async () => {}, { then: async s => {
      const n = await ev(() => ({ rows: document.querySelectorAll(".row").length, lines: D.lines.length, segs: document.querySelectorAll("#segs .seg").length, spans: spans.length,
        sped: spans.filter(x => x.sp && !x.rp).length, ramp: spans.filter(x => x.rp).length, zoom: spans.filter(x => x.z).length, quiet: spans.filter(x => x.ids.every(i => D.words[i].q)).length }));
      check("cut: every line and every clip is on the page (a sped clip, a ramp, a zoom, a quiet piece)",
        n.rows === n.lines && n.segs === n.spans && n.sped === 1 && n.ramp === 1 && n.zoom === 1 && n.quiet === 1 && s.sec === "cut" && s.phase === "cut", n);
      check("REPORTED 2026-10-17: a word stamped over a pause shows as kept in her script ('internet' was struck through)",
        await ev(i => !wordEls[i].classList.contains("x"), idx("internet.")), idx("internet.")); } });
    await step("REPORTED 2026-10-21: a lone '?' the transcriber heard rides on the word before it (it was a word she could cut but never cut away: Lock in never came back)", async () => {}, { then: async () => {
      const d = await ev(() => ({ lone: D.words.filter(w => w.t && !/[\p{L}\p{N}]/u.test(w.t)).map(w => w.t), up: D.words.filter(w => w.t === "up?").length,
        shown: [...document.querySelectorAll(".w")].map(e => e.textContent.trim()).filter(t => t && !/[\p{L}\p{N}]/u.test(t)) }));
      check("REPORTED 2026-10-21: no word on her page is only punctuation, and 'up?' is one word", !d.lone.length && !d.shown.length && d.up === 1, d); } });

    const hook = idx("hook");
    await step("cut: tap a word: the playhead jumps to it and the menu offers Cut", () => word(hook), { moves: await ev(i => cutStarts()[i], hook),
      then: async () => check("cut: a tapped word offers Cut and Add a note", await ev(() => !!document.querySelector('.pop [data-a="cut"]') && !!document.querySelector('.pop [data-a="note"]'))) });
    await step("cut: Cut cuts the word, and Send my cut appears", () => pop("cut"), { then: async s => {
      check("cut: the word is cut and the dock offers Send", await ev(i => cut[i], hook) && s.send.act === "send", s.send); } });
    await step("cut: Cmd/Ctrl+Z brings it back, Shift+Cmd/Ctrl+Z cuts it again, Undo again", async () => {
      await key("z", MOD); const a = await ev(i => cut[i], hook);
      await page.keyboard.down(MOD); await page.keyboard.down("Shift"); await page.keyboard.press("z"); await page.keyboard.up("Shift"); await page.keyboard.up(MOD); await wait(250);
      const b = await ev(i => cut[i], hook); await key("z", MOD); return { a, b, c: await ev(i => cut[i], hook) };
    }, { moves: true, then: (s, r) => check("cut: undo / redo / undo land where they should", r.a === false && r.b === true && r.c === false, r) });
    await step("cut: a double-click on a word does one thing (selects it), never two", () => dblclick(`.w[data-i="${idx("second")}"]`), { moves: true,
      then: async () => { check("cut: the double-click left the word as it was", await ev(i => !cut[i], idx("second"))); await key("Escape"); } });
    const um = idx("um");
    await step("cut: Bring back the word the engine cut ('um')", async () => { await word(um); await pop("back"); }, { moves: true,
      then: async () => check("cut: 'um' is back in her cut", await ev(i => !cut[i] && spans.some(s => s.ids.includes(i)), um)) });
    await step("cut: Undo puts 'um' back out", () => key("z", MOD), { moves: true, then: async () => check("cut: 'um' is cut again", await ev(i => cut[i], um)) });

    // the timeline: a clip's edge, Split, Speed, Zoom, a ramp, the quiet piece
    await step("timeline: drag the first clip's end edge left: words cut, one undo step, playhead stays", async () => {
      await ev(() => { stop(); seekCut(0.05); });
      const e = await box('#segs .seg[data-k="0"] .edg.e'), w = (await box('#segs .seg[data-k="0"]')).width;
      const n0 = await ev(() => undoS.length);
      await drag({ x: e.x + e.width / 2, y: e.y + e.height / 2 }, { x: e.x + e.width / 2 - w * 0.45, y: e.y + e.height / 2 });
      return { n0 };
    }, { moves: true, then: async (s, r) => {
      const d = await ev(n0 => ({ steps: undoS.length - n0, lost: D.lines[0].filter(i => cut[i]).map(i => D.words[i].t) }), r.n0);
      check("timeline: the edge drag cut the words at the end of line 1, as one undo step", d.steps === 1 && d.lost.length >= 1, d);
      await key("z", MOD);
      check("timeline: Undo restores the edge", await ev(() => D.lines[0].every(i => !cut[i])));
    } });
    const segAt = k => ev(k => { let a = 0; for (let j = 0; j < k; j++) a += sdur(spans[j]); return { a, d: sdur(spans[k]) }; }, k);
    const s3 = await segAt(3);
    await step("timeline: click the ruler inside clip 4: the playhead goes there", () => seekTo(s3.a + s3.d * 0.3), { moves: s3.a + s3.d * 0.3 });
    await step("timeline: Split at the playhead: two clips, same sound, the playhead stays", () => click("#tbSplit"), { then: async () => {
      check("timeline: Split made one more clip", await ev(() => spans.length) === 6, await ev(() => spans.length)); } });
    await step("timeline: Undo the split", () => key("z", MOD), { then: async () => check("timeline: back to five clips", await ev(() => spans.length) === 5) });
    await step("REPORTED 2026-10-21: tap a line number, B to split, click the narrow after piece (on its handle), Delete: only that piece goes (the whole clip went)", async () => {
      const n = await ev(() => D.lines.findIndex(L => L.includes(spans[3].ids[0])));
      await click(`.row[data-n="${n}"] .num`);                          // the whole line selected, the playhead jumps there
      await ev(() => { stop(); let a = 0; for (let j = 0; j < 3; j++) a += sdur(spans[j]); seekCut(a + sdur(spans[3]) * 0.5); });
      await wait(300); await key("b");
      await click('#segs .seg[data-k="4"] .edg.s'); await key("Delete");
      return { n };
    }, { moves: true, then: async (s, r) => {
      const d = await ev(n => ({ clips: spans.length, before: spans[3].ids.length, line: D.lines[n].filter(i => !cut[i]).length }), r.n);
      check("REPORTED 2026-10-21: Delete took the after piece only; the before piece and the rest of the line stay", d.clips === 5 && d.before > 0 && d.line > 0, d);
      await key("z", MOD); await key("z", MOD);
      check("REPORTED 2026-10-21: two Undos put the clip back whole", await ev(() => spans.length) === 5 && await ev(() => spans[3].ids.every(i => !cut[i])));
    } });
    const s1 = await segAt(1);
    await step("timeline: select the sped-up clip and set its Speed to 2x: it plays shorter, from its start", async () => {
      await click('#segs .seg[data-k="1"]'); await click("#tbSpeed"); await click('#fxMenu [data-v="2"]');
    }, { moves: s1.a, then: async () => {
      const d = await ev(() => ({ sp: spans[1].sp, badge: document.querySelector('#segs .seg[data-k="1"] .segfx')?.textContent, btn: $("tbSpeedTxt").textContent, len: total(spans) }));
      check("timeline: the clip plays at 2x, its badge and the Speed button say so", d.sp === 2 && d.badge === "2×" && d.btn === "2×", d); } });
    await step("timeline: Zoom in on the same clip", async () => { await click("#tbZoom"); await click('#fxMenu [data-v="in"]'); }, { moves: s1.a,
      then: async () => check("timeline: the clip zooms in", await ev(() => !!spans[1].z && spans[1].z.to > spans[1].z.from && $("tbZoomTxt").textContent === "Zoom in")) });
    await step("REPORTED 2026-10-17: the quiet piece takes a Speed like any clip (quiet stretches were refused)", async () => {
      await click('#segs .seg[data-k="2"]'); await click("#tbSpeed"); await click('#fxMenu [data-v="1.5"]');
    }, { moves: true, then: async () => {
      const d = await ev(() => ({ sp: spans[2].sp, quiet: spans[2].ids.every(i => D.words[i].q), toast: ($("toastAt") && !$("toastAt").hidden) ? $("toastAt").textContent : "" }));
      check("quiet piece: sped to 1.5x, nothing refused", d.quiet && d.sp === 1.5 && !/can't|couldn't|refus|nothing/i.test(d.toast), d); } });
    await step("timeline: a ramp on the last clip (normal, speeding up)", async () => {
      await click('#segs .seg[data-k="4"]'); await click("#tbSpeed"); await click('#fxMenu [data-v="ramp-up"]');
    }, { moves: true, then: async () => check("timeline: the last clip ramps 1 -> 2.5", await ev(() => !!spans[4].rp && spans[4].rp.from === 1 && spans[4].rp.to === 2.5)) });
    await step("rapid: Cmd/Ctrl+Z five times fast, then redo five times fast: back exactly where she was", async () => {
      const sig = () => ev(() => JSON.stringify([cut, spans.map(x => [x.s, x.e, x.sp || 1, !!x.rp, !!x.z])]));
      const a = await sig();
      for (let k = 0; k < 5; k++) { await page.keyboard.down(MOD); await page.keyboard.press("z"); await page.keyboard.up(MOD); }
      await wait(300); const mid = await sig();
      for (let k = 0; k < 5; k++) { await page.keyboard.down(MOD); await page.keyboard.down("Shift"); await page.keyboard.press("z"); await page.keyboard.up("Shift"); await page.keyboard.up(MOD); }
      await wait(400); return { same: (await sig()) === a, moved: mid !== a };
    }, { moves: true, then: (s, r) => check("rapid: undo then redo, fast, lands on the same cut", r.same && r.moved, r) });
    await step("timeline: play across the sped clip: the video's rate follows the clip, the head moves forward", async () => {
      await ev(() => { selectClip(null); seekCut(0.2); }); await click("#play", { after: 1600 }); const r = await ev(() => ({ rate: v.playbackRate, head: cutPos(), qi })); await click("#play"); return r;
    }, { moves: true, then: (s, r) => check("playback: playing moves the head and plays a sped clip faster", r.head > 0.9 && (r.qi !== 1 || r.rate >= 1.9), r) });

    // Send: once, then twice fast
    let saves = 0; page.on("request", r => { if (r.method() === "POST" && /\/save\?/.test(r.url())) saves++; });
    await step("send: Send my cut: the engine takes it, the page shows it working, then reloads onto the new cut", async () => {
      const n = saves; await click("#send"); const working = await until(() => making || $("send").dataset.act === "wait", 30000);
      const re = await reloadsTo(); return { posts: saves - n, working, re };
    }, { moves: true, then: async (s, r) => {
      const st = await claude("state");
      const segs = st.cuts.segments, two = segs.filter(x => +x.speed === 2), q = segs.find(x => +x.speed === 1.5 && !x.ramp);
      check("send: one save, the page said it was working, and it came back on the new cut", r.posts === 1 && r.working && r.re && !s.edits, r);
      check("send: the new cut carries 2x, the zoom, the quiet piece at 1.5x and the ramp", two.length === 1 && !!two[0].zoom && !!q && segs.some(x => x.ramp && x.ramp.to === 2.5), segs.map(x => [x.start, x.end, x.speed, !!x.zoom, x.ramp && x.ramp.to]));
      check("send: the page shows the engine's clips (sp / rp / z come back from the cut)", await ev(() => spans.some(x => x.sp === 2 && x.z) && spans.some(x => x.rp)));
    } });
    await step("send: Send twice fast: one cut goes out, the second press waits its turn, nothing breaks", async () => {
      await word(idx("about")); await pop("cut");
      const n = saves; const b = await box("#send");
      await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2); await wait(40); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
      const re = await reloadsTo(); return { posts: saves - n, re };
    }, { moves: true, http: [/409 POST \/save/], then: async (s, r) => {
      const st = await claude("state");
      check("send twice: at most one cut was applied, and the page is on it", r.posts >= 1 && r.re && !s.edits && !st.cuts.segments.some(x => / about /.test(" " + x.transcript + " ")), { r, segs: st.cuts.segments.map(x => x.transcript) });
    } });

    // a note, Claude, and Lock in
    const note = idx("check");
    await step("note: Add a note on a word: it shows as waiting, and the queue lists it", async () => {
      await word(note); await pop("note"); await page.type("#cmpText", "this word sounds clipped"); await click("#cmpSave", { after: 400 }); await beat();
    }, { moves: true, queue: [/sounds clipped \| *Sent/], then: async s => {
      check("note: the note is on her line, waiting for Claude", await ev(() => !!document.querySelector(".lnote:not(.fixed)") && /Waiting for Claude/.test(document.querySelector(".lnote .ln-state")?.textContent || "")));
      check("note: Lock in stays on while her note is open (her call)", !s.send.waits && s.lockWait && s.send.act === "ready", s.send);
    } });
    await step("note: with a note open, nothing on the page tells her she can't lock in", () => beat(), { then: async s => {
      check("lock in: on, nothing locked behind her back", s.phase === "cut" && !s.send.waits && (await claude("state")).phase === null, s.phase);
      check("lock in: no 'notes come first' wall anywhere", await ev(() => !/come first|can't lock|before you can lock/i.test(document.body.innerText))); } });
    await step("REPORTED 2026-10-17: Claude is watching: no 'type update my edit' anywhere, and Lock in says Claude is on it", async () => {
      await claude("watch"); await beat(); await wait(200);
    }, { watching: true, queue: [/sounds clipped \| *Sent/], then: async s => {
        const txt = await ev(() => [...document.querySelectorAll("#staleBadge, .lnote, #taskQueue, #nextcard, #lockednote, #toastAt")].filter(e => !e.hidden && e.getClientRects().length && getComputedStyle(e).visibility !== "hidden").map(e => e.innerText).join(" | "));   // what she can see
        check("watching: no card, note, queue row or Lock in answer asks her to type 'update my edit'", !/update my edit/i.test(txt), txt.slice(0, 500));
        check("watching: Lock in stays on while Claude works", s.phase === "cut" && !s.send.waits, s.send); } });
    await step("queue: Claude takes the note: the row and the note say Claude has it", async () => { await claude("take"); await beat(); }, { watching: true,
      queue: [/sounds clipped \| *Claude has it/], then: async () => check("note: says Claude's on it", await ev(() => /Claude's on it/.test(document.querySelector(".lnote .ln-state")?.textContent || ""))) });
    await step("rapid: editing her cut while Claude works on her note: the queue and the note hold", async () => {
      await word(idx("then")); await pop("cut"); await beat(); const mid = await ev(() => window.__ps()); await key("z", MOD); await beat(); return mid;
    }, { moves: true, watching: true, queue: [/Claude has it/], then: (s, mid) => check("rapid: the queue kept its row through the edit, Lock in stays on", mid.queue.length === 1 && !s.send.waits, { mid: mid.queue, send: s.send }) });
    await step("queue: Claude finishes: the note turns done, Lock in turns back on everywhere", async () => { await claude("done"); await beat(); await wait(300); await beat(); },
      { watching: true, queue: q => q.length <= 1 && q.every(r => /Done/.test(r)), then: async s => {
        check("note: done (green, ✓) with Claude's reply", await ev(() => !!document.querySelector(".lnote.fixed") && /Fixed: trimmed that breath/.test(document.querySelector(".lnote.fixed").textContent)));
        check("lock in: back on", !s.send.waits && !s.lockWait, s.send); } });
    await step("REPORTED 2026-11-07: a fixed note lands as a plain message in her CHAT (not a card over her phone, and never the bell)", () => beat(), { watching: true, then: async s => {
      const r = await ev(() => {
        const msg = [...document.querySelectorAll("#cpThread .cp-msg.claude")].find(d => /trimmed that breath/.test(d.textContent));
        return { text: msg ? msg.textContent : "",
          overlay: !$("saysBox").hidden && $("saysBox").getBoundingClientRect().height > 0,
          bellN: $("bellN").hidden ? 0 : +$("bellN").textContent,
          hasGo: !!(msg && msg.querySelector(".cp-go")) };
      });
      check("chat: the fixed note is a plain message in her thread, in Claude's words ('Done: ...')", /trimmed that breath/.test(r.text) && /done/i.test(r.text), r);
      check("chat: it sits in her chat thread, not a card over her phone", !!r.text && !r.overlay, r);
      check("chat: no 'see my notes' button on the message", !r.hasGo, r);
      check("bell: a Claude message never counts in the bell (the bell is engine + you announcements only)", r.bellN === 0, r); } });
    await step("says: Claude asks her something: it joins her chat thread, and still never the bell", async () => {
      await claude("tell", "&chat=1&text=" + encodeURIComponent("Teaching or confessional? Pick one in the chat.")); await beat(); },
      { watching: true, then: async s => {
        const r = await ev(() => ({ inThread: [...document.querySelectorAll("#cpThread .cp-msg.claude")].some(d => /Teaching or confessional/.test(d.textContent)),
          bellN: $("bellN").hidden ? 0 : +$("bellN").textContent }));
        check("chat: her question is in the thread", r.inThread, r);
        check("bell: the bell still counts no chat messages", r.bellN === 0, r); } });
    await step("REPORTED 2026-11-07: her messages live in the chat, and the bell is not a chat inbox", async () => {
      await click("#bellBtn", { after: 250 });
      const r = await ev(() => ({ overlay: !$("saysBox").hidden && $("saysBox").getBoundingClientRect().height > 0,
        bellEmpty: /no new updates/i.test($("bellList").textContent),
        inThread: [...document.querySelectorAll("#cpThread .cp-msg.claude")].some(d => /trimmed that breath/.test(d.textContent)) }));
      await click(".hero-top h1", { after: 200 }); return r;
    }, { watching: true, then: async (s, r) => {
      check("chat: nothing stacks above her phone", !r.overlay, r);
      check("chat: her messages are in her thread", r.inThread, r);
      check("bell: the bell holds no chat messages (it says 'No new updates')", r.bellEmpty, r); } });
    await step("REPORTED 2026-11-07: more messages land in her chat, every one in the thread, none in the bell", async () => {
      for (const t of ["One.", "Two.", "Three."]) { await claude("tell", "&text=" + encodeURIComponent(t)); await beat(); }
      const mid = await ev(() => ({ overlay: !$("saysBox").hidden && $("saysBox").getBoundingClientRect().height > 0,
        bellN: $("bellN").hidden ? 0 : +$("bellN").textContent,
        inThread: ["One.", "Two.", "Three."].every(t => [...document.querySelectorAll("#cpThread .cp-msg.claude")].some(d => d.textContent.includes(t))) }));
      return mid;
    }, { watching: true, then: async (s, mid) => {
      check("chat: nothing stacks above her phone", !mid.overlay, mid);
      check("chat: her three new messages are in her thread", mid.inThread, mid);
      check("bell: none of them reached the bell", mid.bellN === 0, mid); } });
    await step("says: in another tab, the tab's title says Claude has something, the soft chime plays, and it clears when she's back", async () => {
      await ev(() => Object.defineProperty(document, "hidden", { configurable: true, get: () => true }));
      await claude("tell", "&text=" + encodeURIComponent("Your three sketches are in your Sandbox.") + "&go=sandbox"); await beat(); await wait(300);
      const t = await ev(() => document.title); const chimes = (await claude("state")).chimes;
      await ev(() => { delete document.hidden; document.dispatchEvent(new Event("visibilitychange")); });
      return { t, chimes };
    }, { watching: true, then: async (s, mid) => {
      check("says: the tab's title says it while she's away", /^\(1\) A note from Claude · /.test(mid.t), mid.t);
      check("says: the engine's soft chime was asked for", mid.chimes >= 1, mid.chimes);
      check("says: back on the page, the title is hers again and the card waits for her", !/^\(\d\)/.test(await ev(() => document.title)) && s.says && /Sandbox/.test(s.says.go), s.says);
      await click("#bellBtn", { after: 200 }); await click("#bellAll", { after: 300 }); await click(".hero-top h1", { after: 150 }); } });
    await step("lock in: Lock in my cut: her cut is locked in at once and Visuals opens", async () => { await click("#send", { after: 800 }); await beat(); },
      { watching: true, then: async s => check("lock in: phase looks, on Visuals, and Claude is cooking her looks", s.phase === "looks" && s.sec === "visuals"
        && (await claude("state")).phase?.phase === "looks" && await ev(() => !$("lockednote").hidden && /Chef Claude|looks/.test($("lockedText").textContent)), s) });
    await step("visuals: Claude makes her looks (Phrase captions + a takeover on line 2): they show up on the preview", async () => {
      await claude("looks"); await beat(); await looksSettled();
    }, { watching: true, fresh: true, sweep: true, then: async s => check("visuals: two looks, captions in Phrase", await ev(() => LOOKS.layers.length === 2 && /Phrase/.test($("capsName").textContent))) });
    await step("REPORTED 2026-10-17: a quiet line's + Add a look leads somewhere (quiet stretches were refused)", async () => {
      const n = await ev(() => D.lines.findIndex(l => l.every(i => D.words[i].q)));
      await click(`.lkchips .lk-addchip[aria-label="Add a look to line ${n + 1}"]`);
      await until(() => document.querySelectorAll("#swGrid .sw-tile").length || /nothing to put a look on|no words/i.test($("swGrid").textContent), 30000);
      await until(() => [...document.querySelectorAll("#swGrid .sw-tile iframe")].every(f => f.contentDocument?.getElementById("root")?.textContent.trim()));   // tiles drawn
      const r = await ev(() => ({ tiles: [...document.querySelectorAll("#swGrid .sw-tile:not(.off)")].map(t => t.querySelector(".sw-name").textContent.trim()), line: $("swLine").textContent,
        words: [...document.querySelectorAll("#swGrid .sw-tile iframe")].map(f => f.contentDocument?.getElementById("root")?.textContent.trim().toLowerCase() || "") }));
      if (r.tiles.includes("Hook")) { await pickTile("Hook"); await until(() => !!$("swCopyText"));
        await page.type("#swCopyText", "the pause says it all"); await looksReload(() => click("#swCopyGo")); }
      return r;
    }, { moves: true, then: async (s, r) => {
      const borrowed = r.words.filter(t => !t.replace(/[^a-z]/g, "").includes("yourhook"));   // every tile: the sample, never anyone's words
      const placed = await ev(() => LOOKS.layers.some(L => L.look === "hook" && L.added));
      check("REPORTED 2026-10-17: a quiet line's + Add a look leads somewhere (quiet stretches were refused)",
        r.tiles.length > 0 && r.tiles.every(t => /Hook|headline|subhead/i.test(t)) && !borrowed.length && /quiet/i.test(r.line) && placed, { r, borrowed, placed });
      if (placed) await looksReload(() => key("z", MOD));
    } });
    await claude("unwatch");
    // her b-roll reel with no talking (2026-10-18): a Sandbox sketch locked in on a quiet stretch, named for the look
    await step("REPORTED 2026-10-18: Sandbox, Lock it in on a line with no talking: the name it suggests says what the look is", async () => {
      const was = await ev(() => LOOKS.layers.map(l => `${l.name}=${l.look}`).sort().join(" "));
      await click("#looksMenuBtn", { after: 200 });               // Build new lives in the Looks menu now
      await click("#sandboxBtn", { after: 300 });                 // her idea, in her words (the first words are no name)
      await page.type("#sbIdea", "So I'm gonna be editing this in CapCut this needs to be a muted clip and I want cards popping up around me");
      await click("#sbFwd", { after: 600 });
      const sk = await claude("sketch"); await beat();
      await until(() => { const x = activeSandbox(); return x && x.status === "takes"; }, 30000);   // her page hears the sketch is in
      if (await ev(() => $("sandboxSheet").hidden)) { await click("#looksMenuBtn", { after: 200 }); await click("#sandboxBtn", { after: 300 }); }
      const drawn = await until(() => document.querySelector("#sbGrid .sw-tile") || /couldn't|isn't/.test($("sbGrid").textContent) && $("sbGrid").textContent, 30000);
      if (!drawn || typeof drawn === "string") throw new Error("the sketches didn't draw: " + JSON.stringify(await ev(() => ({ x: activeSandbox() || null,
        ideas: (LOOKS && LOOKS.ideas) || null, hidden: $("sandboxSheet").hidden, step: sbStep, grid: $("sbGrid").innerHTML.slice(0, 300) }))));
      await click("#sbGrid .sw-tile", { after: 200 }); await click("#sbFwd", { after: 300 });
      const name = await ev(() => $("kpName").value);
      await click('#sbKeep .fin-route[data-keep="oneoff"]', { after: 150 });
      await looksReload(() => click("#sbFwd"));
      return { sk, name, was, toast: await ev(() => $("toast").hidden ? "" : $("toast").textContent.trim()) };
    }, { moves: true, then: async (s, r) => {
      check("REPORTED 2026-10-18: Lock it in suggests a name for the LOOK ('Card pop orbit'), never the first words of her idea",
        r.name === "Card pop orbit", r.name);
      const L = await ev(() => (LOOKS.layers.find(l => /^my-card-pop-orbit-/.test(l.look || "")) || {}).look || null);
      check("REPORTED 2026-10-18: a sketch whose words are its own note locks in on a stretch with no talking (it was refused: 'no words left')",
        !!L && !/no words/i.test(r.toast), { look: L, toast: r.toast });
      if (await ev(() => !!document.getElementById("tBack"))) await looksReload(() => click("#tBack"));   // her Undo: the reel as it was
      const now = await ev(() => LOOKS.layers.map(l => `${l.name}=${l.look}`).sort().join(" "));
      check("REPORTED 2026-10-18: Undo after Lock it in leaves the line as it was (it brought back a hook she had taken off that line)",
        now === r.was, { was: r.was, now });
    } });

    // ═══ VISUALS ══════════════════════════════════════════════════════════════════════════════════════════════════
    let tk = await ev(() => { const L = LOOKS.layers.find(l => !l.captions); return { name: L.name, a: L.offset, d: L.dur }; });
    const capName = await ev(() => LOOKS.layers.find(l => l.captions).name);
    const grabAt = async (name) => {                             // where the look is drawn on the preview, in page px
      return ev(n => { const f = lookFrames.find(x => x.L.name === n); const b = lookBox(f), st = $("lookStack").getBoundingClientRect(), k = st.width / 1080;
        return { x: st.left + (b.l + b.r) / 2 * k, y: st.top + (b.t + b.b) / 2 * k, k }; }, name);
    };
    const activeBox = async () => box(await page.evaluateHandle(() => moving.active.el));
    const mid = tk.a + Math.max(0.6, tk.d - 0.45);
    await step("move: put the playhead where the takeover is on screen", () => seekTo(mid), { moves: mid });
    await step("REPORTED 2026-10-17: Move (paused): click the takeover on the preview: its handles, right here, the playhead stays", async () => {
      await ev(() => $("screen").scrollIntoView({ block: "center" })); const g = await grabAt(tk.name); await page.mouse.click(g.x, g.y); await wait(300);
    }, { active: tk.name, then: s => check("move: the mover is open", s.moving, s) });
    let dragged;
    await step("move: drag it down 120 px and to the right: it follows the hand", async () => {
      const b = await activeBox();
      const c0 = await ev(() => moving.active.cur.slice(0, 2));
      await drag({ x: b.x + b.width / 2, y: b.y + b.height / 2 }, { x: b.x + b.width / 2 + 37, y: b.y + b.height / 2 + 120 });
      dragged = await ev(() => moving.active.cur.slice(0, 2)); return { c0 };
    }, { active: tk.name, then: (s, r) => check("move: the look moved with her drag", dragged[1] > r.c0[1] + 100 && s.moving, { from: r.c0, to: dragged }) });
    await step("move: Center left to right (the icon): the look's center lands on the frame's center line", () => click("#moverCX"), { active: tk.name, then: async () => {
      const c = await ev(() => { const b = mvBox(moving.active); return Math.round((b.l + b.r) / 2); });
      check("move: centered left to right", Math.abs(c - 540) <= 2, c); } });
    await step("move: Cancel: everything goes back, nothing is saved, the playhead stays", () => click("#moverCancel", { after: 500 }), { then: async s => {
      const st = await claude("state");
      check("move: Cancel saved nothing and closed the mover", !s.moving && !((st.swaps || {}).adds || {})[tk.name]?.nudge, st.swaps); } });
    await step("REPORTED 2026-10-20: a short window: the Move bar stays above the timeline, and Center top to bottom centers the look", async () => {
      await page.setViewport({ width: 1280, height: 760 }); await wait(300);   // a realistically short laptop window: the preview shrinks to fit (never scrolls) but stays usably sized
      await ev(() => { $("monitor").scrollTop = 0; scrollTo(0, 0); });
      const g = await grabAt(tk.name); await page.mouse.click(g.x, g.y); await wait(400);          // Move: the takeover, on the preview
      const grabbed = await ev(() => moving && moving.active.L.name);
      for (let i = 0; i < 5; i++) await key("ArrowDown", "Shift");                                  // off center: 120 px down
      const m = await ev(() => { const r = $("monitor").getBoundingClientRect(); return { x: r.left + 6, y: r.top + r.height / 2 }; });
      await page.mouse.move(m.x, m.y); await page.mouse.wheel({ deltaY: -2000 }); await wait(300);   // she scrolls the panel back up to her look
      const at = await ev(() => { const b = $("moverCY").getBoundingClientRect(), x = b.left + b.width / 2, y = b.top + b.height / 2, top = document.elementFromPoint(x, y);
        return { x, y, reach: !!top && top.closest("button") === $("moverCY"), under: top ? (top.closest("button") || top).id || top.className : null, scrolled: $("monitor").scrollTop }; });
      const c0 = await ev(() => { const b = mvBox(moving.active); return Math.round((b.t + b.b) / 2); });
      await page.mouse.click(at.x, at.y); await wait(250);                                           // her click, right where she sees it
      const c1 = await ev(() => { const b = mvBox(moving.active); return Math.round((b.t + b.b) / 2); });
      await key("Escape"); await page.setViewport({ width: 1280, height: 900 }); await wait(300);
      return { at, c0, c1, grabbed };
    }, { then: (s, r) => {
      check("short window: the takeover she clicked is the one selected", r.grabbed === tk.name, r.grabbed);
      check("short window: Center top to bottom is on screen and nothing covers it", r.at.reach, r.at);
      check("short window: her click centers the look top to bottom", Math.abs(r.c1 - 960) <= 2 && Math.abs(r.c0 - 960) > 2, r); } });
    await step("REPORTED 2026-10-21: safe zones on, notices stacking up: the phone holds its size and place, and Move still grabs and drags the look", async () => {
      await page.setViewport({ width: 1280, height: 800 }); await wait(300);
      const rect = () => ev(() => { const r = $("screen").getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; });
      await click("#szBtn", { after: 200 });                              // safe zones on (the Bigger-phone toggle is retired: the phone auto-fits its panel now)
      await ev(() => { $("monitor").scrollTop = 0; scrollTo(0, 0); });
      const base = await rect();
      await ev(() => { const t = document.createElement("div"); t.id = "jnStack"; t.style.cssText = "flex:none; height:900px"; $("notices").appendChild(t); });
      await wait(250); const stacked = await rect(); await ev(() => $("jnStack").remove());
      const g = await grabAt(tk.name); await page.mouse.click(g.x, g.y); await wait(400);
      const grabbed = await ev(() => moving && moving.active.L.name);
      const b = await activeBox(), c0 = await ev(() => moving.active.cur.slice(0, 2));
      await drag({ x: b.x + b.width / 2, y: b.y + b.height / 2 }, { x: b.x + b.width / 2, y: b.y + b.height / 2 + 60 });
      const c1 = await ev(() => moving.active.cur.slice(0, 2));
      const zones = await ev(() => ({ on: !$("safeZones").hidden, top: Math.round($("safeZones").querySelector(".sz-top").getBoundingClientRect().height) }));
      await key("Escape"); await wait(250);
      await click("#szBtn", { after: 200 }); await page.setViewport({ width: 1280, height: 900 }); await wait(300);
      return { base, stacked, grabbed, c0, c1, zones };
    }, { then: (s, r) => {
      check("safe zones: a tall stack of notices never moves or rescales the phone", JSON.stringify(r.base) === JSON.stringify(r.stacked), r);
      check("safe zones: they show over the preview", r.zones.on && r.zones.top > 10, r.zones);
      check("safe zones: the takeover she clicked is the one selected", r.grabbed === tk.name, r.grabbed);
      check("safe zones: her drag moves the look", r.c1[1] > r.c0[1] + 40, r); } });
    await step("REPORTED 2026-10-21: a look moved down low (where captions sit): the Move bar sits under the phone and its note above it, off the look, so she can still grab it", async () => {
      await ev(() => { $("monitor").scrollTop = 0; scrollTo(0, 0); });
      const g = await grabAt(tk.name); await page.mouse.click(g.x, g.y); await wait(400);
      const sc = await ev(() => { const r = $("screen").getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; });
      const at = () => ev(() => { const a = moving.active.el.getBoundingClientRect(), s = $("screen").getBoundingClientRect(),
        d = $("moverDock").getBoundingClientRect(), b = document.querySelector(".mover-bar").getBoundingClientRect(), w = $("moverWarn");
        const ab = Math.min(a.bottom, s.bottom);                                     // the part of the look ON the phone
        return { lap: Math.max(0, Math.min(ab, d.bottom) - Math.max(a.top, d.top)), under: Math.round(d.top - s.bottom),
                 bar: b.height > 0, warn: !w.hidden, play: $("play").offsetParent !== null,
                 warnLap: (r => Math.max(0, Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top)))(w.getBoundingClientRect()) }; });
      const b = await activeBox();
      await drag({ x: b.x + b.width / 2, y: b.y + b.height / 2 }, { x: b.x + b.width / 2, y: sc.bottom - 30 });   // down where captions sit
      const low = await at();
      await key("Escape"); await wait(250);
      return { low, after: await ev(() => $("play").offsetParent !== null && $("moverDock").offsetParent === null) };
    }, { then: (s, r) => {
      check("low look: the Move bar is under the phone, not over the look", r.low.bar && r.low.lap <= 4 && r.low.under >= -4, r.low);   // a few px of sub-pixel/rounding drift is not the bar covering the look
      check("low look: the 'Your call' note shows (Instagram's caption covers that spot) in the notices above the phone, never over it", r.low.warn && r.low.warnLap === 0, r.low);
      check("Move open: the bar takes the play controls' place; after Move, the play controls are back", !r.low.play && r.after, r); } });
    await step("REPORTED 2026-10-21: the eye hides the tools on the phone (a look's tool bar, Snap, Preview); a click on the look still opens Move", async () => {
      await seekTo(mid); await click("#toolsBtn", { after: 250 });
      const off = await ev(() => ({ cls: document.body.classList.contains("tools-off"),
        shown: ["#lookTools", "#shutter", ".leanpill"].filter(q => { const e = document.querySelector(q); return e && getComputedStyle(e).display !== "none"; }) }));
      await ev(() => { $("monitor").scrollTop = 0; scrollTo(0, 0); });
      const g = await grabAt(tk.name); await page.mouse.click(g.x, g.y); await wait(400);
      const grabbed = await ev(() => moving && moving.active.L.name);
      await key("Escape"); await wait(250); await key("V"); await wait(250);
      const back = await ev(() => !document.body.classList.contains("tools-off") && getComputedStyle(document.querySelector(".leanpill")).display !== "none");
      return { off, grabbed, back };
    }, { then: (s, r) => {
      check("eye: the tools step off the phone", r.off.cls && !r.off.shown.length, r.off);
      check("eye: with the tools hidden, a click on the look still opens Move on it", r.grabbed === tk.name, r.grabbed);
      check("eye: V brings the tools back", r.back, r); } });
    await step("move (playing): press play, then grab the takeover while it plays: the player stops, that look is selected, the head holds", async () => {
      await seekTo(tk.a + 0.1); await click("#play", { after: 350 });
      const g = await grabAt(tk.name); const at = await ev(() => cutPos()); await page.mouse.click(g.x, g.y); await wait(400);
      return { at };
    }, { moves: true, active: tk.name, then: (s, r) => check("move while playing: stopped, mover on the takeover, the head where she clicked", !s.playing && s.moving && Math.abs(s.head - r.at) < 0.3, { s: s.head, at: r.at, moving: s.moving }) });
    await step("move: drag, Center top to bottom, Done: it saves, the looks reload, the playhead stays", async () => {
      const b = await activeBox();
      await drag({ x: b.x + b.width / 2, y: b.y + b.height / 2 }, { x: b.x + b.width / 2 - 30, y: b.y + b.height / 2 + 60 });
      const moved = await ev(() => moving && moving.active.cur.slice(0, 2));
      await click("#moverCY"); await click("#moverDone", { after: 600 }); await looksSettled(); return { moved };
    }, { fresh: true, then: async (s, r) => {
      check("move: the drag right after grabbing it mid-play moved it", !!r.moved && r.moved[0] < -20, r);
      const st = await claude("state"), nd = (((st.swaps || {}).adds || {})[tk.name] || {}).nudge;
      check("move: Done saved where she put it", !!nd && Math.abs(nd[0]) > 5, nd);
      check("move: the reloaded preview shows the takeover where she put it", await ev(n => { const f = lookFrames.find(x => x.L.name === n); return !!f && JSON.stringify(f.L.nudge || []).length > 2; }, tk.name)); } });
    await step("move: from the preview's look bar (Move): the look she has on screen is the one selected", async () => {
      await seekTo(mid); await until(n => $("lookTools").dataset.layer === n, 15000, tk.name); await click('#lookTools [data-lt="move"]', { after: 700 });
    }, { moves: true, active: tk.name, then: async s => {
      check("move from the bar: the head is on that look's moment", s.head >= tk.a && s.head <= tk.a + tk.d, { head: s.head, look: tk });
      await key("Escape"); await wait(300);
      check("move: Escape cancels", !(await ev(() => !!moving))); } });

    // ═══ the cut again, under her looks ═══════════════════════════════════════════════════════════════════════════
    await step("back to Cut with her looks on: the tab opens, her looks wait", () => tab("cut"), { then: s => check("cut tab: Cut is open", s.sec === "cut", s.sec) });
    await step("REPORTED 2026-10-17: a change to her first clip (2x) never drops her captions", async () => {
      await click('#segs .seg[data-k="0"]'); await click("#tbSpeed"); await click('#fxMenu [data-v="2"]');
      await click("#send"); await reloadsTo(); await beat(); await looksSettled();
      await until(() => !retiming && (!$("staleBadge").hidden ? $("staleBadge").dataset.k !== "sync" : true), 30000);
      if (await ev(() => !$("staleBadge").hidden && $("staleBadge").dataset.k === "cut")) { await click("#sbGo", { after: 800 }); await looksSettled(); }
    }, { moves: true, fresh: true, sweep: true, then: async () => {
      const r = await ev(() => { const st = cutStarts(), first = D.order.find(i => !cut[i] && !D.words[i].q), capL = LOOKS.layers.find(l => l.captions);
        const t = st[first] + 0.12; steerLooks(t); const f = lookFrames.find(x => x.L === capL); const shown = window.__ps().caps; steerLooks(cutPos());
        return { first: D.words[first].t, at: +t.toFixed(2), capOffset: capL && capL.offset, shown }; });
      check("captions: still on her first word after the first clip changed", r.capOffset != null && r.capOffset <= r.at && r.shown.length === 1, r); } });
    await step("lock in again: with a note open the dock and the card agree, then agree again when it's done", async () => {
      await word(idx("hook")); await pop("note"); await page.type("#cmpText", "breath here"); await click("#cmpSave", { after: 400 }); await claude("watch"); await beat();
      const mid = await ev(() => window.__ps()); await claude("take"); await claude("done"); await beat(); await wait(300); await beat(); await claude("unwatch"); return mid;
    }, { moves: true, then: (s, mid) => {
      check("lock in (note open): the dock stays on", !mid.send.waits, mid.send);
      check("lock in (note open): the card offers Lock in and says Claude is still working", !mid.card || mid.card.k !== "lockcut" || (mid.card.go === "Lock in my cut" && /still working/.test(mid.card.sub)), mid.card);
      check("lock in (done): both ready", !s.send.waits && (!s.card || s.card.k !== "lockcut" || /Lock in your cut/.test(s.card.title)), { send: s.send, card: s.card }); } });
    await step("lock in: Lock in my cut again: Visuals opens with her looks", async () => {
      await click("#send", { after: 900 }); await beat(); await looksSettled();
      if (await ev(() => sec !== "visuals")) await tab("visuals");
      tk = await ev(n => { const L = LOOKS.layers.find(l => l.name === n); return { name: L.name, a: L.offset, d: L.dur }; }, tk.name);
    }, { moves: true, fresh: true, then: async s => check("lock in: phase looks, on Visuals, her looks on", (await claude("state")).phase?.phase === "looks" && s.sec === "visuals" && s.looksOn, s) });

    // split / join lines on Visuals (never a cut change)
    const l2 = await ev(n => D.lines.findIndex(l => l.includes(n)), idx("thought"));
    const nLines = await ev(() => D.lines.length);
    await step("visuals: Split line here on line 2: two lines, her cut untouched, nothing to lock in again", async () => { await word(idx("thought")); await pop("split"); await wait(900); },
      { moves: true, then: async s => {
        const st = await claude("state"), n = await ev(() => D.lines.length);
        check("lines: one more line, phase still looks, no 'you updated your cut'", n === nLines + 1 && st.phase?.phase === "looks" && s.card?.k !== "cutedit" && !s.edits, { n, nLines, phase: st.phase, card: s.card }); } });
    await step("visuals: + Combine puts the two lines back together", async () => {
      const n = await ev(i => D.lines.findIndex(l => l.includes(i)), idx("thought")); await click(`.row[data-n="${n}"] .joinbtn`); await wait(900);
    }, { moves: true, fresh: true,
      then: async () => check("lines: back to the same lines", await ev(n => D.lines.findIndex(l => l.includes(n)), idx("pricing.")) === l2) });

    // add a look, swap, captions here, highlight, refine
    const l4w = idx("speed");
    await step("REPORTED 2026-10-17: the hook card never copies her spoken line", async () => {
      await word(l4w); await pop("look"); await until(() => document.querySelectorAll("#swGrid .sw-tile:not(.off)").length, 30000);
      await until(() => [...document.querySelectorAll("#swGrid .sw-tile")].find(x => x.querySelector(".sw-name")?.textContent.trim() === "Hook")?.querySelector("iframe")?.contentDocument?.getElementById("root")?.textContent.trim());
      const tile = await ev(() => { const t = [...document.querySelectorAll("#swGrid .sw-tile")].find(x => x.querySelector(".sw-name")?.textContent.trim() === "Hook");
        return t?.querySelector("iframe")?.contentDocument?.getElementById("root")?.textContent.trim() || ""; });
      await pickTile("Hook"); const boxOpen = await until(() => !!$("swCopyText"));
      await click("#swCopyGo", { after: 300 }); const emptyRefused = await ev(() => !$("swapSheet").hidden);
      await page.type("#swCopyText", "nobody tells you this part"); await looksReload(() => click("#swCopyGo"));
      return { tile, boxOpen, emptyRefused };
    }, { moves: true, then: async (s, st) => {
      const r = await ev(async w => { const norm = t => String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
        const said = D.lines.find(l => l.includes(w)).map(i => D.words[i].t).join(" ");
        const L = LOOKS.layers.find(x => x.look === "hook"); if (!L) return { placed: false, said };
        const rec = await (await fetch(lookUrl(L).replace(/index\.html(\?.*)?$/, "look.json"), { cache: "no-store" })).json().catch(() => ({}));
        return { placed: true, said, shown: rec.text, same: norm(rec.text) === norm(said) || norm(said).includes(norm(rec.text)) }; }, l4w);
      const said = r.said.toLowerCase().replace(/[^a-z]/g, "");
      check("hook: its tile shows a sample, never her line; picking it asks for the hook's own words (an empty box goes nowhere)",
        st.boxOpen && st.emptyRefused && !st.tile.toLowerCase().replace(/[^a-z]/g, "").includes(said.slice(4)), st);
      check("REPORTED 2026-10-17: the hook card never copies her spoken line", r.placed && r.shown === "nobody tells you this part" && !r.same, r);
      await looksReload(() => key("z", MOD));
    } });
    await step("swap: the takeover's Swap -> Phrase: the new look plays, and her captions step aside for it (not a stale copy)", async () => {
      await ev(n => document.querySelector(`.lkchip[data-layer="${n}"]`)?.scrollIntoView({ block: "center" }), tk.name);
      await click(`.lkchip[data-layer="${tk.name}"] [data-a="swap"]`); await pickTile("Phrase"); await looksSettled();
    }, { moves: true, fresh: true, sweep: true, then: async () => check("swap: the line's look is Phrase now", await ev(n => LOOKS.layers.find(l => l.name === n)?.look === "phrase", tk.name)) });
    await step("rapid: a double-click on a Swap tile puts one look on the line, not two", async () => {
      await ev(n => document.querySelector(`.lkchip[data-layer="${n}"]`)?.scrollIntoView({ block: "center" }), tk.name);
      await click(`.lkchip[data-layer="${tk.name}"] [data-a="swap"]`);
      await until(() => document.querySelectorAll("#swGrid .sw-tile:not(.off)").length, 30000);
      const h = await page.evaluateHandle(() => [...document.querySelectorAll("#swGrid .sw-tile:not(.off)")].find(t => t.querySelector(".sw-name")?.textContent.trim() === "Takeover"));
      const b = await box(h.asElement()); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { clickCount: 2 }); await wait(500); await looksSettled();
    }, { moves: true, fresh: true, sweep: true, http: [/409 POST \/swap/], then: async () => {
      const r = await ev(n => { const L = LOOKS.layers.find(l => l.name === n); return { look: L && L.look, onLine: LOOKS.layers.filter(l => !l.captions && L && Math.abs(l.offset - L.offset) < 0.05).length }; }, tk.name);
      check("rapid: the line has exactly one look, the one she double-clicked", r.look === "takeover" && r.onLine === 1, r); } });
    await step("REPORTED 2026-10-17: Captions here on line 4 (Single word): never two caption styles on screen at once", async () => {
      await word(idx("we")); await pop("caps"); await pickTile("Single word"); await looksSettled();
    }, { moves: true, fresh: true, sweep: true });
    await step("highlight: Highlight a word: the captions redraw with it, live (no stale copy)", async () => {
      await looksReload(async () => { await word(idx("pricing.")); await pop("acc"); });
    }, { moves: true, fresh: true, http: [/409 POST/], then: async () => check("highlight: the word is her highlight", await ev(i => typeof isAccent === "function" && isAccent(i), idx("pricing."))) });
    // her error log 2026-10-20 (Visuals tab, phase looks): "Cannot read properties of null (reading 'accents')": the
    // highlight saves 400 ms after her tap, and a looks reload (Move, a redraw, the engine's beat) had LOOKS empty then
    let hl2;
    await step("REPORTED 2026-10-20: Highlight a word right before her looks reload: no page error, and the highlight saves", async () => {
      hl2 = await ev(p => Object.keys(capOf).map(Number).find(i => i !== p && !cut[i] && !isAccent(i)), idx("pricing."));
      if (hl2 === undefined) throw new Error("no word left to highlight on the captions");
      await ev(() => { const f0 = window.fetch; window.__f0 = f0;          // a busy machine: her looks take 1.5 s to come back
        window.fetch = (u, o) => /looks\.json/.test(String(u)) ? new Promise(r => setTimeout(r, 1500)).then(() => f0(u, o)) : f0(u, o); });
      await click(`.w[data-i="${hl2}"]`, { after: 60 }); await click('.pop [data-a="acc"]', { after: 0 });
      await ev(() => { quietLooksUntil = Date.now() + 10000; $("lookStack").innerHTML = ""; lookFrames = []; LOOKS = null; looksOn = false;   // the reload, as the page does it
        document.body.classList.remove("looks"); loadLooks(); });
      await wait(2000); await ev(() => { window.fetch = window.__f0; }); await netIdle(); await looksSettled();
    }, { moves: true, fresh: true, http: [/409 POST/], then: async () => {
      const saved = await (await fetch(`${BASE}/accents?job=${encodeURIComponent(JOB)}`, { cache: "no-store" })).json().catch(() => ({}));
      check("highlight across a reload: the highlight is saved", (saved.items || []).some(x => x.i === hl2 && x.on), saved.items);
      check("highlight across a reload: the page still shows it", await ev(i => isAccent(i), hl2)); } });
    await step("refine: Letters rise on the line-2 look: every word's letters stay together", async () => {
      await ev(n => document.querySelector(`.lkchip[data-layer="${n}"]`)?.scrollIntoView({ block: "center" }), tk.name);
      await click(`.lkchip[data-layer="${tk.name}"] [data-a="more"]`); await pop("refine");
      await until(() => !$("refineSheet").hidden && $("rfAnim").options.length > 1, 30000);
      await page.select("#rfAnim", "per-character-rise");
      await click("#rfHere", { after: 100 });                     // at once, the way a quick hand does (rapid input)
      const early = await ev(() => !$("refineSheet").hidden);
      if (early) await looksReload(async () => { await until(() => !$("rfHere").disabled && $("rfBusy").hidden, 30000); await click("#rfHere"); });
      else await looksSettled();
      await seekTo(tk.a + tk.d * 0.6);
    }, { moves: true, fresh: true, wrap: true, sweep: true, then: async () => {
      const n = await ev(n => { const f = lookFrames.find(x => x.L.name === n); return f && f.el ? f.el.contentDocument.querySelectorAll(".tfxw").length : -1; }, tk.name);
      check("refine: the per-letter animation is on the look, each word in one unbreakable box", n > 0, n); } });

    await step("lock in: Lock in my looks: Sound opens", async () => { await click("#send", { after: 1200 }); await beat(); },
      { moves: true, then: async s => check("lock in looks: phase render", (await claude("state")).phase?.phase === "render", s) });

    // ═══ SOUND, FINISH ════════════════════════════════════════════════════════════════════════════════════════════
    await step("sound: the Sound tab lists a sound under each look that moves", async () => { await tab("sound"); await until(() => SND && (SND.cues || []).length, 30000); }, { moves: true,
      then: async () => check("sound: rows on her lines", await ev(() => document.querySelectorAll(".sndrow[data-cue]").length > 0)) });
    await step("sound: nudge a sound later (⋯ then +)", async () => {
      await click('.sndrow[data-cue] [data-a="more"]'); await click('.pop [data-d="0.05"]', { after: 900 });
    }, { moves: true, then: async () => check("sound: the nudge is kept", await ev(() => SND.cues.some(c => c.nudge > 0))) });
    // her ask 2026-10-18: "click and drag a sound effect, so I could retime it earlier or later"
    const dotPick = await ev(() => { const len = total(spans); const c = (SND.cues || []).filter(c => !c.empty && !c.none && c.origin !== "own" && (c.choice || c.file)).find(c => c.t + 0.8 < len);
      return c && { id: c.id, t: c.t, nudge: c.nudge || 0, len, w: $("laneSnd").getBoundingClientRect().width }; });
    const dotSel = () => `#laneSnd .sdot.mv[data-cue="${dotPick.id}"]`;
    const cueNow = () => ev(id => SND.cues.find(c => c.id === id), dotPick.id);
    await step("sound: a tap on a sound's dot plays it and leaves it where it is", () => click(dotSel(), { after: 500 }), { then: async () => {
      const c = await cueNow(); check("sound: the tap moved nothing", c && Math.abs(c.t - dotPick.t) < 1e-3, { before: dotPick, after: c }); } });
    await step("sound: drag a sound's dot later on the timeline: it lands there, on a frame, and the nudge is kept", async () => {
      const b = await box(dotSel()), dx = 0.5 / dotPick.len * dotPick.w, y = b.y + b.height / 2, x = b.x + b.width / 2;
      await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + dx / 2, y, { steps: 4 }); await wait(120);
      const mid = await ev(() => ({ tip: document.querySelector("#tl .sdtip")?.textContent || "", ghost: !!document.querySelector("#laneSnd .sdot.ghost") }));
      await page.mouse.move(x + dx, y, { steps: 4 }); await page.mouse.up(); await wait(1500);
      return { mid };
    }, { moves: true, then: async (s, r) => {
      check("sound: while dragging, a ghost stays where it was and the readout says how far (+0.25s)", r.mid.ghost && /^\+0\.\d\ds · /.test(r.mid.tip), r.mid);
      const c = await cueNow();
      check("sound: the dragged sound plays ~0.5 s later, on a frame, and its nudge is kept", c && Math.abs(c.t - (dotPick.t + 0.5)) < 0.08 && c.nudge > dotPick.nudge + 0.4
        && Math.abs(c.t * 30 - Math.round(c.t * 30)) < 0.03, { before: dotPick, after: c });
      check("sound: the drag left no ghost or readout behind", await ev(() => !document.querySelector("#laneSnd .sdot.ghost, #tl .sdtip")));
    } });
    let tKey;
    await step("sound: arrow keys on a focused dot: a frame each, Shift a tenth of a second, as one move", async () => {
      tKey = (await cueNow()).t; await ev(sel => document.querySelector(sel).focus(), dotSel());
      await page.keyboard.press("ArrowLeft"); await page.keyboard.press("ArrowLeft");
      await page.keyboard.down("Shift"); await page.keyboard.press("ArrowLeft"); await page.keyboard.up("Shift"); await wait(1500);
    }, { moves: true, then: async () => {
      const c = await cueNow();
      check("sound: two frames and a tenth of a second earlier", c && Math.abs(c.t - (tKey - 2 / 30 - 0.1)) < 0.01, { before: tKey, after: c && c.t });
      check("sound: the dot keeps her focus after it moves", await ev(id => document.activeElement?.dataset?.cue === id, dotPick.id));
    } });
    await step("sound: ⋯ Back to its moment puts the dragged sound back", async () => {
      await click(`.sndrow[data-cue="${dotPick.id}"] [data-a="more"]`); await click('.pop [data-d="reset"]', { after: 900 });
    }, { then: async () => { const c = await cueNow(); check("sound: back where it was, no nudge", c && !c.nudge && Math.abs(c.t - (dotPick.t - dotPick.nudge)) < 0.01, { before: dotPick, after: c }); } });
    await step("REPORTED 2026-10-18: a Note for Claude on a sound (⋯ then Note for Claude): the note box opens on screen, the note reaches Claude naming that sound", async () => {
      await click('.sndrow[data-cue] [data-a="more"]'); await click('.pop [data-d="note"]', { after: 300 });
      check("sound note: the note box opens where she can see it", await ev(() => { const c = document.getElementById("composer"), r = c.getBoundingClientRect();
        return !c.hidden && r.width > 0 && r.bottom > 0 && r.top < innerHeight; }));
      await page.type("#cmpText", "softer whoosh here"); await click("#cmpSave", { after: 400 }); await beat();
    }, { moves: true, then: async () => check("sound note: tagged with the sound and its moment", await ev(() => notesList.some(n => /^\[Sound: .+ at \d+:\d\d\] softer whoosh here$/.test(n.text)))) });
    await step("sound: each line has a Note for Claude, like Visuals", async () => {
      await click(".sndchips .lk-notechip", { after: 300 });
    }, { moves: true, then: async () => { check("sound line note: the note box opens", await ev(() => !document.getElementById("composer").hidden));
      await click("#cmpCancel"); } });
    await step("REPORTED 2026-10-18: an export that stopped says so on every tab (calmly), until she opens Finish", async () => {
      await tab("sound");
      await ev(() => { FIN = { state: "failed", at: "2026-10-18 01:32:20", step: "Rendering look 30 of 31", route: "capcut", message: "x" }; updateRenderBar(); });
      check("stopped export: the bar across the top says it, with no alarm words", await ev(() => { const b = document.getElementById("renderBar");
        return !b.hidden && /stopped partway/.test(b.textContent) && !/REFUS|issue|error|fail/i.test(b.textContent); }));
      await tab("finish");
      check("stopped export: opening Finish clears the bar", await ev(() => document.getElementById("renderBar").hidden));
      await ev(() => { FIN = null; updateRenderBar(); });
    }, { moves: true });
    await step("finish: the Finish tab offers the routes and Export (not pressed)", async () => { await tab("finish"); await click('.fin-route[data-route="mp4"]'); },
      { moves: true, then: async s => check("finish: MP4 picked, Export ready", s.send.act === "render" && !s.send.disabled && await ev(() => document.querySelector('.fin-route[data-route="mp4"]').getAttribute("aria-checked") === "true"), s.send) });
    await step("page: every id is used once", async () => {}, { then: async () => {
      const dup = await ev(() => { const seen = {}, d = []; document.querySelectorAll("[id]").forEach(e => { if (seen[e.id]) d.push(e.id); seen[e.id] = 1; }); return d; });
      check("page: no id used twice", !dup.length, dup); } });
  } catch (e) { if (!(e instanceof Stop)) bad.push("the journey stopped: " + String(e && e.stack || e).slice(0, 1500)); }
  finally { await browser.close(); }
  console.log(JSON.stringify({ ok, bad, open, fixed, secs: (Date.now() - T0) / 1000 }));
})();
