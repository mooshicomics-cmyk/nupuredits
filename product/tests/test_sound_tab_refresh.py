#!/usr/bin/env python3
"""Guard: an open Sound tab sees a sound plan changed from the chat (a buyer, 2026-10-22).

When Claude edited sound.json in the chat, an already-open Sound tab kept the plan it opened with, so her preview
played the old sounds. Now the server's /status carries `sound_at` (a stamp of review/sound.json and the plan under
it, caption-plan.json or sfx-plan.json) and the page refreshes its Sound plan when the stamp moves:

  server    /status has sound_at; it changes when sound.json changes, and when caption-plan.json changes
  wired     the page's status beat hands sound_at to sndFresh
  first     the first beat only remembers the stamp (nothing fetched)
  fresh     a new stamp with a changed plan: the Sound tab redraws (and the preview reloads with it), said once on Sound
  hers      her own edit (the plan comes back the same): nothing redraws, nothing is said
  waits     a sheet, a Swap menu or a sound she is dragging is open: nothing changes under her, and the next beat
            (once it is closed) brings the new plan
  race      an edit she made while it was fetching wins over the fetched plan

The page half runs editor.html's own sndFresh in node with stand-ins (skipped without node).
Run: python3 product/tests/test_sound_tab_refresh.py
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
EDITOR = os.path.join(PRODUCT, "visual-editor", "editor.html")
sys.path.insert(0, PRODUCT)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-400:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def write(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def bump(path, data):
    """Write it again with a clearly later mtime (some filesystems keep whole seconds)."""
    write(path, data)
    t = time.time() + 5
    os.utime(path, (t, t))


def test_server():
    import visual_editor_server as srv
    tmp = tempfile.mkdtemp(prefix="sound-at-")
    saved = srv.PROJECTS
    httpd = None
    try:
        jd = os.path.join(tmp, "projects", "test-reel")
        os.makedirs(os.path.join(jd, "review"))
        srv.PROJECTS = os.path.join(tmp, "projects")
        srv._premake_seen.add("test-reel")               # no background full-quality cut for a test reel
        httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def status():
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", "/status?job=test-reel", headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse(); data = r.read(); c.close()
            return json.loads(data) if r.status == 200 else {}

        s0 = status()
        check("server: status carries sound_at", "sound_at" in s0, s0)
        bump(os.path.join(jd, "review", "sound.json"), {"version": 1, "cues": [], "added": []})
        s1 = status().get("sound_at")
        check("server: sound_at moves when sound.json changes", s1 is not None and s1 != s0.get("sound_at"), (s0.get("sound_at"), s1))
        bump(os.path.join(jd, "caption-plan.json"), {"sfx": []})
        s2 = status().get("sound_at")
        check("server: sound_at moves when the plan under it changes", s2 != s1, (s1, s2))
        check("server: sound_at holds still while nothing changes", status().get("sound_at") == s2)
    finally:
        if httpd:
            httpd.shutdown()
        srv.PROJECTS = saved
        shutil.rmtree(tmp, ignore_errors=True)


STUBS = r"""
let SND = null, sec = "sound", RENDERS = 0, TOASTS = [], FETCHES = 0, NEXT = null, DURING = null;
const OPEN = { sheet: false, menu: false };
const document = { body: { classList: { contains: c => c === "sheet-open" && OPEN.sheet } },
                   querySelector: s => OPEN.menu && s.includes(".sndmenu") ? {} : null };
const renderSound = async () => { RENDERS++; };
const toast = m => TOASTS.push(m);
const post = async url => { FETCHES++; if (DURING) DURING(); return url === "/sound" ? { ok: true, j: JSON.parse(JSON.stringify(NEXT)) } : { ok: false }; };
"""

TESTS = r"""
const out = [];
const check = (name, ok, detail) => out.push({ name, ok: !!ok, detail: ok ? "" : JSON.stringify(detail) });
(async () => {
  SND = { cues: [{ id: "a", t: 1 }] }; NEXT = SND;
  await sndFresh("s1");
  check("first: the first beat only remembers the stamp", FETCHES === 0 && soundAt === "s1", { FETCHES, soundAt });
  NEXT = { cues: [{ id: "a", t: 1 }, { id: "b", t: 2 }] };
  await sndFresh("s2");
  check("fresh: a changed plan redraws the Sound tab", RENDERS === 1 && SND.cues.length === 2 && soundAt === "s2", { RENDERS, SND, soundAt });
  check("fresh: said once, on the Sound tab", TOASTS.length === 1, TOASTS);
  NEXT = SND; await sndFresh("s3");
  check("hers: her own edit (the same plan back) redraws nothing", RENDERS === 1 && TOASTS.length === 1 && soundAt === "s3", { RENDERS, TOASTS });
  OPEN.sheet = true; NEXT = { cues: [] }; const f0 = FETCHES;
  await sndFresh("s4");
  check("waits: an open sheet is never changed under her", FETCHES === f0 && SND.cues.length === 2 && soundAt === "s3", { FETCHES, soundAt });
  OPEN.sheet = false; OPEN.menu = true; await sndFresh("s4");
  check("waits: nor an open Swap menu", FETCHES === f0 && soundAt === "s3", { FETCHES, soundAt });
  OPEN.menu = false; await sndFresh("s4");
  check("waits: once it is closed, the next beat brings the new plan", SND.cues.length === 0 && soundAt === "s4" && RENDERS === 2, { SND, soundAt, RENDERS });
  NEXT = { cues: [{ id: "c", t: 3 }] }; DURING = () => { SND = { cues: [{ id: "mine", t: 4 }] }; };
  await sndFresh("s5"); DURING = null;
  check("race: an edit she made while it was fetching wins", SND.cues[0].id === "mine" && RENDERS === 2, SND);
  sec = "visuals"; NEXT = { cues: [{ id: "d", t: 5 }] }; const t0 = TOASTS.length;
  await sndFresh("s6");
  check("fresh: off the Sound tab it updates quietly", SND.cues[0].id === "d" && TOASTS.length === t0, TOASTS);
  console.log(JSON.stringify(out));
})().catch(e => console.log(JSON.stringify([{ name: "the harness ran", ok: false, detail: String(e && e.stack || e) }])));
"""


def test_page():
    with open(EDITOR, encoding="utf-8") as fh:
        html = fh.read()
    check("wired: the status beat hands sound_at to the Sound tab",
          "j.sound_at !== soundAt) sndFresh(j.sound_at)" in html)
    node = shutil.which("node")
    if not node:
        print("  skip  page: node not installed")
        return
    a = html.find("let soundAt, sndFreshing")
    b = html.find("\n", html.find("} finally { sndFreshing = false; }", a))
    b = html.find("}", b) + 1 if b > 0 else -1
    if a < 0 or b <= a:
        check("page: sndFresh found in editor.html", False)
        return
    tmp = tempfile.mkdtemp(prefix="sound-fresh-")
    try:
        js = os.path.join(tmp, "run.js")
        with open(js, "w", encoding="utf-8") as fh:
            fh.write(STUBS + "\n" + html[a:b] + "\n" + TESTS)
        r = subprocess.run([node, js], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        res = json.loads((r.stdout.strip().splitlines() or ["[]"])[-1]) or []
    except ValueError:
        res = []
    if not res:
        check("page: the harness ran", False, r.stdout + r.stderr)
    for x in res:
        check(x["name"], x["ok"], x["detail"])


def main():
    test_server()
    test_page()
    print(f"test_sound_tab_refresh: {'FAIL ' + ', '.join(fails) if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
