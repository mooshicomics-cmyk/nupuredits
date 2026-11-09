#!/usr/bin/env python3
"""Guard: the visual editor's preview plays a sound that is already under way where she presses play or lands
(two buyers, 2026-10-22).

The preview used to fire a sound only when its timer tick crossed the sound's START, so pressing play (or resuming,
or landing after a skip) inside a long sound (a song under a stretch, a typing burst) skipped it, a sound whose file
arrived late missed its entrance, and a skip left the old sounds playing. This runs the page's own preview-sound code
(editor.html, from `const PB = {` up to `function start()`) in node against a stand-in audio clock, and holds:

  inside     play inside a long sound: it plays from that spot in it (the rest of it, not from its start)
  short      play just after a short hit started: the rest of it plays; on its last sliver (under PB_TAIL_S) or
             after it ended: nothing (a hit is never replayed, and never a stray click)
  trim       a sound cut short (trim) counts as over where its trim ends, not where its file does
  crossing   a sound whose start the playhead crosses while playing fires once, as before
  once       a sound already sounding never fires again over itself (resume and the next tick)
  pause      pause and play again inside a sound: it picks up where she is
  skip       a skip stops what was playing; landing inside a sound plays its rest; a sound ended before the
             landing spot stays silent
  late       she pressed play before the sound plan or its files arrived: each sound joins where the playhead is
             the moment its file lands
  quiet      on Cut and Visuals (sounds are heard on Sound and Finish only) nothing plays

Run: python3 product/tests/test_preview_sound_start.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR = os.path.join(os.path.dirname(HERE), "visual-editor", "editor.html")

STUBS = r"""
let sec = "sound", playing = false, userRate = 1, spans = [{}], pos = 0, D = { job: "test-reel" }, PLAN = null;
const total = () => 60, cutPos = () => pos;
const v = { addEventListener() {}, muted: false };
const STARTED = [], STOPPED = [];
let NOW = 0;
const param = () => ({ value: 1, setValueAtTime() {}, linearRampToValueAtTime() {}, cancelScheduledValues() {} });
class FakeCtx {
  get currentTime() { return NOW; }
  get destination() { return {}; }
  resume() {}
  createDynamicsCompressor() { return { threshold: {}, knee: {}, ratio: {}, attack: {}, release: {}, connect() {} }; }
  createMediaElementSource() { throw new Error("no media element here"); }
  createGain() { return { gain: param(), connect(x) { return x; } }; }
  createBufferSource() {
    const s = { buffer: null, loop: false, playbackRate: { value: 1 }, onended: null, connect(x) { return x; },
      start(when, off, dur) { s.off = off || 0; s.dur = dur; STARTED.push(s); },
      stop() { STOPPED.push(s); } };
    return s;
  }
  decodeAudioData(a) { return Promise.resolve(a); }
}
const window = { AudioContext: FakeCtx };
const LENS = { song: 10, hit: 0.5, typing: 1.2 };
let HELD = {};                                  // files that have not arrived yet: id -> release()
const fetch = (url) => { const id = decodeURIComponent(url.split("id=")[1]);
  const body = { arrayBuffer: () => ({ duration: LENS[id] }) };
  if (HELD[id] === true) return new Promise(res => { HELD[id] = () => res(body); });
  return Promise.resolve(body); };
const post = async (url) => url === "/sound-playback" ? { ok: true, j: PLAN } : { ok: false };
"""

TESTS = r"""
const out = [];
const check = (name, ok, detail) => out.push({ name, ok: !!ok, detail: ok ? "" : JSON.stringify(detail) });
const fired = id => STARTED.filter(s => s.cue === id);
const reset = () => { pbStop(); playing = false; STARTED.length = 0; STOPPED.length = 0; PB.live = []; };
const play = c => { pos = c; playing = true; pbStart(c); };
const tickTo = c => { pos = c; pbTick(c); };
const near = (a, b) => Math.abs(a - b) < 1e-6;
PLAN = { cues: [ { id: "song@1", t: 1, src: "song", trim: null, gain_db: -6 },
                 { id: "hit@20", t: 20, src: "hit", trim: null, gain_db: 0 },
                 { id: "type@30", t: 30, src: "typing", trim: 0.8, gain_db: 0 } ],
         music: null, voice_gain_db: 0, voice_muted: false };

(async () => {
  await pbLoad();
  check("setup: every file loaded", Object.keys(PB.bufs).length === 3, Object.keys(PB.bufs));

  reset(); play(5);
  check("inside: play inside a long sound plays it from there", fired("song@1").length === 1 && near(fired("song@1")[0].off, 4), fired("song@1"));
  tickTo(5.025); tickTo(5.05);
  check("once: the next ticks never fire it again over itself", fired("song@1").length === 1, fired("song@1").length);

  reset(); play(20.1);
  check("short: just after a short hit started, the rest of it plays", fired("hit@20").length === 1 && near(fired("hit@20")[0].off, 0.1), fired("hit@20"));
  reset(); play(20 + 0.5 - (typeof PB_TAIL_S === "undefined" ? 0.25 : PB_TAIL_S) / 2);
  check("short: its last sliver alone never plays", fired("hit@20").length === 0, fired("hit@20"));
  reset(); play(21);
  check("short: a hit that already ended is never replayed", fired("hit@20").length === 0, fired("hit@20"));

  reset(); play(30.7);
  check("trim: a trimmed sound is over where its trim ends", fired("type@30").length === 0, fired("type@30"));
  reset(); play(30.3);
  check("trim: inside its trim, its rest plays (to the trim)", fired("type@30").length === 1 && near(fired("type@30")[0].dur, 0.5), fired("type@30"));

  reset(); play(19.9); tickTo(19.925); tickTo(19.95); tickTo(19.975); tickTo(20.0); tickTo(20.025);
  check("crossing: a start crossed while playing fires once", fired("hit@20").length === 1, fired("hit@20").length);

  reset(); play(3); tickTo(3.025); pbStop(); playing = false; STARTED.length = 0; play(4);
  check("pause: play again inside a sound picks it up where she is", fired("song@1").length === 1 && near(fired("song@1")[0].off, 3), fired("song@1"));

  reset(); play(2); tickTo(2.025); const was = fired("song@1")[0];
  tickTo(15);
  check("skip: a skip stops what was playing", STOPPED.includes(was), STOPPED.length);
  check("skip: a sound that ended before the landing spot stays silent", fired("song@1").length === 1, fired("song@1").length);
  tickTo(6);
  check("skip: landing back inside a sound plays its rest", fired("song@1").length === 2 && near(fired("song@1")[1].off, 5), fired("song@1"));

  reset(); sec = "cut"; play(5);
  check("quiet: on Cut nothing plays", STARTED.length === 0, STARTED.length);
  sec = "sound";

  // late: she pressed play before the plan and its files arrived
  reset(); PB.bufs = {}; PB.plan = null; HELD = { song: true };
  play(4);
  check("late: nothing plays before the plan is here", STARTED.length === 0, STARTED.length);
  const loading = pbLoad(); await new Promise(r => setTimeout(r, 0));
  check("late: still nothing while its file is on the way", fired("song@1").length === 0, fired("song@1"));
  pos = 6; HELD.song(); await loading;
  check("late: the sound joins where the playhead is when its file lands", fired("song@1").length === 1 && near(fired("song@1")[0].off, 5), fired("song@1"));
  check("late: the timer runs again after a plan that came late", PB.last != null, PB.last);
  console.log(JSON.stringify(out));
})().catch(e => { console.log(JSON.stringify([{ name: "the harness ran", ok: false, detail: String(e && e.stack || e) }])); });
"""


def main():
    node = shutil.which("node")
    if not node:
        print("test_preview_sound_start: skipped (node not installed)")
        return 0
    with open(EDITOR, encoding="utf-8") as fh:
        html = fh.read()
    a, b = html.find("const PB = {"), html.find("function start() {")
    if a < 0 or b < a:
        print("  FAIL  the preview's sound code wasn't found in editor.html (const PB ... function start)")
        return 1
    tmp = tempfile.mkdtemp(prefix="preview-sound-")
    try:
        js = os.path.join(tmp, "run.js")
        with open(js, "w", encoding="utf-8") as fh:
            fh.write(STUBS + "\n" + html[a:b] + "\n" + TESTS)
        r = subprocess.run([node, js], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        res = json.loads((r.stdout.strip().splitlines() or ["[]"])[-1])
    except ValueError:
        res = [{"name": "the harness ran", "ok": False, "detail": (r.stdout + r.stderr)[-800:]}]
    if not res:
        res = [{"name": "the harness ran", "ok": False, "detail": (r.stdout + r.stderr)[-800:]}]
    fails = [x for x in res if not x["ok"]]
    for x in res:
        print(f"  {'PASS' if x['ok'] else 'FAIL'}  {x['name']}{('  -- ' + x['detail'][-400:]) if x['detail'] else ''}")
    print(f"test_preview_sound_start: {'FAIL ' + str(len(fails)) if fails else 'all passed'} ({len(res)} checks)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
