#!/usr/bin/env node
// hf_npx.cjs: the engine's pinned HyperFrames, for the vendored HyperFrames scripts that run their CLI as
// `node <cli.js> <args>` (embedded-captions: hf-cli.cjs hands this file out, and render-and-composite.sh,
// matte.cjs and transcribe.cjs call it). Upstream those scripts look for a HyperFrames source checkout or a
// plugin install; this engine has neither, it runs HyperFrames through npx at the version product.json pins,
// so without this the skill could not start at all.
//
//   node product/hf_npx.cjs render --dir <project> -o out.mp4      (any HyperFrames subcommand)
//
// Same argv as product/npx_run.py npx_argv(): `cmd /c npx` on Windows (npx is npx.cmd there), plain npx
// elsewhere. Tracking stays off, and `init` never installs HyperFrames' skills into the computer's global
// Claude folder (the engine carries its own pinned copies), whatever shell this runs from. The exit code is
// HyperFrames' own; 4 when npx itself could not start (no Node on PATH), with the engine's plain reason.
//
// `render` (and only render: snapshots and checks never count frames) holds the computer's one render lock
// first, the same lock every Python render takes (product/render_lock.py owns the protocol and its reasons;
// this is the same protocol in Node, so the two respect each other): the file render.lock in
// ~/.cache/reels-editing-engine (REEL_RENDER_LOCK_DIR moves it), made with O_CREAT|O_EXCL ("wx"), holding
// {"pid", "started" (epoch seconds), "what", "host"}. A second render waits, never stops the first, saying
// so once and then once a minute; a lock whose owner is gone is taken over with a note; Ctrl-C while
// waiting stops (130) and leaves the other render's lock alone; a lock folder that cannot be made means the
// render goes ahead without one, said in one line. A lock whose pid is alive but started after the lock was
// written belongs to a dead render (the pid was handed out again): its start time comes from ps, or from
// PowerShell on Windows. No time ceiling, as in render_lock.py: a real render can run all night.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const cp = require("node:child_process");

const ROOT = path.resolve(__dirname, "..");

function pin() {
  try {
    const v = JSON.parse(fs.readFileSync(path.join(ROOT, "product.json"), "utf8")).hyperframes;
    if (v) return String(v).trim();
  } catch (_) { /* fall through to the last resort, as npx_run.hf_version() does */ }
  return "0.9.6";
}

// ── the render lock (same protocol as product/render_lock.py) ─────────────────────────────────────────────
const UNREADABLE_GRACE = 30;   // seconds an unreadable record may still be being written
const REUSED_SLACK = 120;      // a pid this much younger than its lock is someone else's
let heldLock = null;

function setting(name, dflt) {
  const v = parseFloat(process.env[name] || "");
  return Number.isFinite(v) ? v : dflt;
}

function lockPath() {
  const base = process.env.REEL_RENDER_LOCK_DIR || path.join(os.homedir(), ".cache", "reels-editing-engine");
  return path.join(base, "render.lock");
}

function noteFallback(step, message) {   // one line in _local/fallbacks.log, as product/fallbacks.py writes it
  try {
    const dir = process.env.REELS_ENGINE_LOCAL || path.join(ROOT, "_local");
    fs.mkdirSync(dir, { recursive: true });
    const stamp = new Date().toISOString().slice(0, 16).replace("T", " ") + "Z";
    fs.appendFileSync(path.join(dir, "fallbacks.log"), `${stamp}  ${step}: ${String(message).split(/\s+/).join(" ")}\n`);
  } catch (_) { /* a log that cannot be written never stops a render */ }
}

function readRecord(p) {   // a record, {} while unreadable, null when gone
  try {
    const rec = JSON.parse(fs.readFileSync(p, "utf8"));
    return rec && typeof rec === "object" && !Array.isArray(rec) ? rec : {};
  } catch (e) {
    return e && e.code === "ENOENT" ? null : {};
  }
}

function pidRunning(pid) {   // true / false, or null when this computer will not say
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; }   // signal 0 only tests, on Windows too (Node emulates it there)
  catch (e) { return e.code === "ESRCH" ? false : e.code === "EPERM" ? true : null; }
}

// What this asks the computer, kept swappable so a test can stand in for Windows on any machine.
const hooks = { platform: () => process.platform, spawnSync: (...a) => cp.spawnSync(...a) };

// How long process `pid` has been running, in seconds, or null when this computer will not say. It tells a
// lock's owner from a newer program that was handed the same pid after the owner died (render_lock.py makes
// the same comparison; on Windows it asks the kernel, here PowerShell does, since Git Bash's ps cannot see
// Windows programs). Unknown (no answer within 10 s, or any error) is never read as "still the owner
// forever": it only means this look cannot tell, and the pid check still runs on every look.
function pidAgeSeconds(pid) {
  if (hooks.platform() === "win32") {
    try {
      const r = hooks.spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-Command",
        `(Get-Process -Id ${Number(pid)} -ErrorAction Stop).StartTime.ToUniversalTime().ToString('o')`],
        { encoding: "utf8", timeout: 10000, windowsHide: true });
      if (!r || r.error || r.status !== 0) return null;
      // 'o' gives seven fractional digits (2026-10-14T09:15:02.1234567Z); a Date reads three.
      const stamp = String(r.stdout || "").trim().replace(/(\.\d{3})\d+/, "$1");
      const started = Date.parse(stamp);
      return Number.isFinite(started) ? Math.max(0, (Date.now() - started) / 1000) : null;
    } catch (_) { return null; }
  }
  try {
    const etime = cp.execFileSync("ps", ["-o", "etime=", "-p", String(pid)], { encoding: "utf8", timeout: 5000 }).trim();
    if (!etime) return null;
    const dash = etime.lastIndexOf("-");
    const days = dash >= 0 ? parseInt(etime.slice(0, dash), 10) : 0;
    let secs = 0;
    for (const part of etime.slice(dash + 1).split(":")) secs = secs * 60 + parseInt(part, 10);
    return Number.isFinite(secs) ? secs + days * 86400 : null;
  } catch (_) { return null; }
}

function staleReason(rec, p) {
  const pid = rec.pid;
  if (!Object.keys(rec).length) {
    try { return Date.now() / 1000 - fs.statSync(p).mtimeMs / 1000 < UNREADABLE_GRACE ? "" : "its record was never finished"; }
    catch (_) { return ""; }
  }
  const running = pidRunning(pid);
  if (running === false) return `the render that held it (process ${pid}) is no longer running`;
  if (running && typeof rec.started === "number") {
    const age = pidAgeSeconds(pid);
    if (age !== null && age + REUSED_SLACK < Date.now() / 1000 - rec.started)
      return `the render that held it (process ${pid}) is gone; that number now belongs to another program`;
  }
  return "";
}

function sameRecord(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function acquireLock(what) {
  const p = lockPath();
  try { fs.mkdirSync(path.dirname(p), { recursive: true }); }
  catch (e) {
    console.log(`  (could not make the render lock folder, ${e.message}; rendering without waiting for any other render)`);
    return false;
  }
  const poll = setting("REEL_RENDER_LOCK_POLL", 2) * 1000;
  const sayEvery = setting("REEL_RENDER_LOCK_SAY_EVERY", 60) * 1000;
  let waitedFrom = null, said = 0;
  // Ctrl-C while waiting is a stop. Nothing is held yet, so the other render's lock is left exactly as it was.
  const onStop = () => {
    console.log("\n  Stopped while waiting for the other render. Nothing was rendered; that render carries on.");
    process.exit(130);
  };
  process.on("SIGINT", onStop);
  try {
    for (;;) {
      let fd;
      try {
        fd = fs.openSync(p, "wx", 0o644);
      } catch (e) {
        if (e.code !== "EEXIST") {
          console.log(`  (could not make the render lock, ${e.message}; rendering without waiting for any other render)`);
          return false;
        }
        const rec = readRecord(p);
        if (rec === null) continue;                       // released between the two looks: try again now
        if (rec.pid === process.pid) { heldLock = p; return true; }
        const stale = staleReason(rec, p);
        if (stale) {
          const aside = `${p}.stale.${process.pid}`;
          try { fs.renameSync(p, aside); } catch (_) { continue; }
          if (!sameRecord(readRecord(aside), rec) && !fs.existsSync(p)) {
            try { fs.renameSync(aside, p); } catch (_) { /* gone already */ }
            continue;
          }
          try { fs.unlinkSync(aside); } catch (_) { /* gone already */ }
          console.log(`  A render lock was left behind (${stale}), so this render takes it over.`);
          noteFallback("render-lock", `took over a render lock left behind: ${stale}`);
          continue;
        }
        const now = Date.now();
        if (waitedFrom === null) {
          waitedFrom = said = now;
          const owner = rec.what ? ` (${rec.what})` : "";
          console.log(`  Another render is running on this computer${owner}; this one starts when it finishes.`);
        } else if (now - said >= sayEvery) {
          said = now;
          console.log(`  Still waiting for the other render to finish (${Math.floor((now - waitedFrom) / 60000)} min so far).`);
        }
        await sleep(poll);
        continue;
      }
      try {
        fs.writeSync(fd, JSON.stringify({ pid: process.pid, started: Date.now() / 1000, what, host: os.hostname() }));
      } finally {
        fs.closeSync(fd);
      }
      heldLock = p;
      if (waitedFrom !== null)
        console.log(`  The other render finished; rendering now (waited ${Math.floor((Date.now() - waitedFrom) / 1000)} s).`);
      return true;
    }
  } finally {
    process.removeListener("SIGINT", onStop);   // during the render itself, Ctrl-C behaves exactly as before
  }
}

function releaseLock() {   // only a lock this process holds is removed, never someone else's
  if (!heldLock) return;
  const p = heldLock;
  heldLock = null;
  const rec = readRecord(p);
  if (rec && rec.pid === process.pid) {
    try { fs.unlinkSync(p); } catch (_) { /* gone already */ }
  }
}
process.on("exit", releaseLock);   // a render that stops on an error still lets the next one go

function renderWhat(args) {   // a short name for what is rendering: the project folder, never a full path
  const i = args.indexOf("--dir");
  const dir = i >= 0 ? args[i + 1] : args.slice(1).find((a) => !a.startsWith("-"));
  return dir ? path.basename(path.resolve(dir)) : "render";
}

function main(args) {
  const win = process.platform === "win32";
  const argv = ["--yes", `hyperframes@${pin()}`, ...args];
  const env = { ...process.env, HYPERFRAMES_NO_TELEMETRY: "1", DO_NOT_TRACK: "1", HYPERFRAMES_SKIP_SKILLS: "1" };
  const r = win
    ? cp.spawnSync("cmd", ["/c", "npx", ...argv], { stdio: "inherit", env })
    : cp.spawnSync("npx", argv, { stdio: "inherit", env });
  if (r.error) {
    process.stderr.write("[hyperframes] npx would not start: Node is not installed on this computer, or this " +
      "terminal was opened before it was. Close the terminal, open a new one and run this again; if it is " +
      "still missing, run ./check-setup.sh.\n");
    return 4;
  }
  if (r.status === null) return r.signal === "SIGINT" ? 130 : 143;
  return r.status;
}

async function run(args) {
  if (args[0] !== "render") return main(args);
  const took = await acquireLock(renderWhat(args));
  try { return main(args); }
  finally { if (took) releaseLock(); }
}

module.exports = { pin, lockPath, acquireLock, releaseLock, staleReason, pidAgeSeconds, hooks };
if (require.main === module) run(process.argv.slice(2)).then((code) => process.exit(code));
