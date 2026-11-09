#!/usr/bin/env python3
"""Guards: the visual editor writes down what went wrong (product/editor_errors.py), and her page turns it into one
file she emails.

  record    an error inside `except` keeps its trace; a plain-words message is kept as "told her"; her home folder
            is written as ~; a long message is cut short; the log keeps the last 300
  report    collect-report's "Visual editor" section lists them, newest last
  bundle    one file in _handoff/ with her words, the reel's state and only that reel's entries, and the address
  server    a failed page write is written down; a page error is written down a few times, not thousands; Report a
            problem makes the file; Show me the file only reveals a file the server made; all of it only from her page

Run: python3 product/tests/test_editor_errors.py
"""
import http.client, json, os, shutil, sys, tempfile, threading
os.environ.setdefault("REE_EDITOR", "1")

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
TMP = tempfile.mkdtemp(prefix="ree-ve-errors-")
os.environ["REE_EDITOR_ERRORS_LOG"] = os.path.join(TMP, "_local", "editor-errors.log")
import editor_errors as ee  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(name)
        print(f"  FAIL {name} {str(detail)[-300:]}")


try:
    ee.HANDOFF = os.path.join(TMP, "_handoff")
    ee.ROOT_PROJECTS = None

    # record
    try:
        raise ValueError("boom at " + os.path.join(os.path.expanduser("~"), "Projects", "x.py"))
    except ValueError:
        ee.record("page /save", job="reel-a")
    ee.record("page /retime", "That line moved. Reload the page first.", job="reel-a", kind="told")
    ee.record("background lean", "x" * 900, job="reel-b")
    es = ee.recent(10)
    check("record: three written", len(es) == 3, es)
    check("record: trace kept", "ValueError" in (es[0].get("trace") or ""), es[0])
    check("record: home folder as ~", os.path.expanduser("~") not in json.dumps(es) and "~" in es[0]["msg"], es[0]["msg"])
    check("record: told her kept as told", es[1]["kind"] == "told" and "trace" not in es[1], es[1])
    check("record: long message cut short", len(es[2]["msg"]) <= 300)
    check("record: version stamped", bool(es[0].get("v")))
    for i in range(450):
        ee.record("spam", f"n{i}")
    lines = open(ee.LOG, encoding="utf-8").read().splitlines()
    check("record: the log is trimmed", len(lines) <= ee.TRIM_AT, len(lines))
    check("record: newest kept", json.loads(lines[-1])["msg"] == "n449")
    os.remove(ee.LOG)
    ee.record("page /save", "first", job="reel-a"); ee.record("background finish", "second", job="reel-b")

    # report
    sec = ee.report_section()
    check("report: section titled", sec.startswith("### Visual editor"), sec)
    check("report: newest last", sec.index("first") < sec.index("second"), sec)

    # bundle
    jd = os.path.join(TMP, "projects", "reel-a", "review"); os.makedirs(jd)
    json.dump({"phase": "looks"}, open(os.path.join(jd, "phase.json"), "w", encoding="utf-8"))
    json.dump({"state": "failed", "route": "mp4", "message": "Render broke"}, open(os.path.join(jd, "finish.json"), "w", encoding="utf-8"))
    ee.ROOT = TMP
    f = ee.bundle("reel-a", "I pressed Export and nothing came out", {"tab": "finish", "browser": "Safari"})
    t = open(f, encoding="utf-8").read()
    check("bundle: in _handoff", os.path.dirname(f) == ee.HANDOFF)
    check("bundle: her words", "I pressed Export" in t)
    check("bundle: the reel's state", "phase: looks" in t and "last export: failed (mp4): Render broke" in t, t)
    check("bundle: only this reel's entries", "first" in t and "second" not in t, t)
    check("bundle: the address", ee.SUPPORT_EMAIL in t)
    check("bundle: the page's tab", "tab open: finish" in t)

    # server
    import visual_editor_server as srv
    srv.PROJECTS = os.path.join(TMP, "projects")
    srv.ve.ROOT = TMP
    revealed = []
    srv.editor_errors.reveal = lambda p: revealed.append(p)
    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(path, body, origin=True, host=None):
        b = json.dumps(body)
        h = {"Host": host or f"127.0.0.1:{port}", "Content-Type": "application/json", "Content-Length": str(len(b))}
        if origin:
            h["Origin"] = f"http://127.0.0.1:{port}"
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", path, body=b, headers=h)
        r = c.getresponse(); d = r.read(); c.close()
        return r.status, (json.loads(d) if d else {})

    os.remove(ee.LOG)
    st, _ = post("/save?job=reel-a", {"job": "reel-a", "id": "nope"})
    es = ee.recent(5)
    check("server: a failed page write is written down", any(e["where"] in ("page /save", "page write /save") for e in es), (st, es))
    for i in range(10):
        post("/log-error?job=reel-a", {"msg": "TypeError: x is undefined", "stack": "at a (editor.html:10)", "tab": "sound"})
    page = [e for e in ee.recent(50) if e["where"] == "page script"]
    check("server: a page error is written down", page and page[0].get("tab") == "sound", page[:1])
    check("server: a repeating page error is written a few times only", len(page) == 3, len(page))
    held = "held, not made (409 busy) /sound-toggle: Hold on a moment, your last change is still being made."
    post("/log-error?job=reel-a", {"msg": held, "stack": "", "kind": "told", "tab": "sound"})
    post("/log-error?job=reel-a", {"msg": "a kind the page made up", "kind": "fine"})
    page = {e["msg"]: e for e in ee.recent(50) if e["where"] == "page script"}
    check("server: a busy hold the page sends as told is written down as told, not as an error",
          page.get(held, {}).get("kind") == "told" and "trace" not in page.get(held, {}), page.get(held))
    check("server: any other kind from the page is an error", page.get("a kind the page made up", {}).get("kind") == "error")
    sec = ee.report_section(2)
    check("report: a busy hold isn't counted among her errors", "(1 errors, 1 plain-words" in sec and "told her in page script" in sec, sec)
    st, j = post("/report?job=reel-a", {"note": "the Sound tab froze", "tab": "sound"})
    check("server: Report a problem makes the file", st == 200 and j.get("file", "").startswith("visual-editor-report-") and j.get("email") == ee.SUPPORT_EMAIL, (st, j))
    made = os.path.join(ee.HANDOFF, j.get("file", ""))
    check("server: the file holds her words", os.path.isfile(made) and "the Sound tab froze" in open(made, encoding="utf-8").read())
    st, _ = post("/report-show?job=reel-a", {"file": j.get("file")})
    check("server: Show me the file reveals that file", st == 200 and revealed == [made], (st, revealed))
    st, _ = post("/report-show?job=reel-a", {"file": "../../brand-kit.md"})
    check("server: Show me the file reveals nothing else", st == 404 and len(revealed) == 1, st)
    st, _ = post("/report?job=reel-a", {"note": "x"}, host="evil.example:80")
    check("server: only her page can make a report", st == 403, st)
    httpd.shutdown()
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"test_editor_errors: {total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
