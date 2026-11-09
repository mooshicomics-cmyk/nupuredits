#!/usr/bin/env python3
"""Guards: Claude's page watcher never races her export for the reel's lock (a buyer, 2026-10-22).

Her export makes her full-quality cut (a new cut id) and then moves her looks onto it. The watcher
(`visual_editor.py wait`, its own process) calls todo() every few seconds, and todo() retimes her looks whenever the
cut moved under them, so it took the reel's lock first and the export failed with "Your reel is busy saving another
change. Try again in a moment."

  exporting   finish.json "running" with a live owner is an export; a dead owner, "done" or no file is not
  todo        the watcher's todo() retimes her looks on a moved cut, but never while her export runs (the list still
              comes back)
  patient     a retime another process started a moment before is waited out under patient(), and still refuses
              plainly without it
  server      a look change from her page while an export typed in the chat runs is held, like a page export

Run: python3 product/tests/test_export_watcher_race.py
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, time
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _finish(rv, **kv):
    json.dump(kv, open(os.path.join(rv, "finish.json"), "w", encoding="utf-8"))


def test_exporting(jd, rv):
    check("exporting: no finish.json is no export", not ve.exporting(jd))
    _finish(rv, state="running", owner=os.getpid())
    check("exporting: running with a live owner is an export", ve.exporting(jd))
    _finish(rv, state="running", owner=_dead_pid())
    check("exporting: running whose owner died is not (a crashed export never blocks her)", not ve.exporting(jd))
    _finish(rv, state="done", owner=os.getpid())
    check("exporting: a finished export is not", not ve.exporting(jd))
    _finish(rv, state="running")
    check("exporting: running with no owner is not", not ve.exporting(jd))
    os.remove(os.path.join(rv, "finish.json"))


def test_todo(jd, rv):
    json.dump({"layers": [{"name": "h01-hook"}]}, open(os.path.join(rv, "looks.json"), "w", encoding="utf-8"))
    json.dump({"cut_id": "new"}, open(os.path.join(rv, "script.json"), "w", encoding="utf-8"))
    calls = []
    real = (ve.job_dir, ve.notes, ve.looks_to_redo, ve.look_requests, ve.looks_cut, ve.retime_adds)
    ve.job_dir = lambda job: jd
    ve.notes = lambda job: [{"id": "n1", "text": "trim this", "w": 0}]
    ve.looks_to_redo = lambda _jd: []
    ve.look_requests = lambda job, **k: []
    ve.looks_cut = lambda _jd: "old"                     # her looks are timed to the cut before the export's
    ve.retime_adds = lambda job: calls.append(job) or {}
    try:
        ve.todo("x")
        check("todo: her cut moved under her looks, so the watcher moves them (as before)", calls == ["x"], calls)
        del calls[:]
        _finish(rv, state="running", owner=os.getpid(), step="Matching your looks to your latest cut")
        items = ve.todo("x")
        check("todo: never while her export runs (the export moves them itself)", calls == [], calls)
        check("todo: the list still comes back during her export", [t["kind"] for t in items] == ["cut-note"], items)
        _finish(rv, state="running", owner=_dead_pid())
        ve.todo("x")
        check("todo: an export that crashed never stops her looks following her cut", calls == ["x"], calls)
    finally:
        ve.job_dir, ve.notes, ve.looks_to_redo, ve.look_requests, ve.looks_cut, ve.retime_adds = real
        try:
            os.remove(os.path.join(rv, "finish.json"))
        except OSError:
            pass


def test_patient(jd, rv):
    """Another process (the watcher, or her page's server) holds the reel's lock for a moment, as a retime does."""
    lf = os.path.join(rv, ".write.lock")
    holder = ("import os, sys, time\n"
              "fd = os.open(sys.argv[1], os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd)\n"
              "print('held', flush=True); time.sleep(float(sys.argv[2])); os.remove(sys.argv[1])\n")
    real = ve.job_dir
    ve.job_dir = lambda job: jd
    work = ve._locked(lambda job: "moved")
    try:
        p = subprocess.Popen([sys.executable, "-c", holder, lf, "1.5"], stdout=subprocess.PIPE, text=True)
        p.stdout.readline()
        try:
            with ve.patient(0.3):
                work("x")
            refused = None
        except ve.Refuse as e:
            refused = str(e)
        check("patient: a short wait still refuses plainly while another process holds the reel", refused and "busy" in refused, refused)
        t0 = time.time()
        try:
            with ve.patient(20):
                got = work("x")
        except ve.Refuse as e:
            got = f"refused: {e}"
        check("patient: the export waits out a retime someone else started, then does its own", got == "moved", got)
        check("patient: and it waited for that retime, not past it", time.time() - t0 < 10, round(time.time() - t0, 2))
        p.wait(timeout=10)
        check("patient: the wait is the thread's own, back to a minute after", getattr(ve._HELD, "wait", None) is None)
        check("patient: the lock is let go after", not os.path.exists(lf))
    finally:
        ve.job_dir = real


def test_server(tmp):
    import visual_editor_server as srv
    proj = os.path.join(tmp, "projects"); jd = os.path.join(proj, "racejob"); rv = os.path.join(jd, "review")
    os.makedirs(rv, exist_ok=True)
    real_proj, real_jd = srv.PROJECTS, srv.ve.job_dir
    srv.PROJECTS = proj
    srv.ve.job_dir = lambda job: jd if os.path.basename(str(job)) == "racejob" else real_jd(job)
    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def req(path, body):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("POST", path, body=body, headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json",
                                                     "Content-Length": str(len(body))})
        r = c.getresponse(); data = r.read(); c.close()
        return r.status, data
    try:
        _finish(rv, state="running", owner=os.getppid())   # a live process that isn't this server: the chat's export
        st, data = req("/retime?job=racejob", "{}")
        check("server: her page's retime during an export typed in the chat is held (it would race the export)",
              st == 409 and "export is running" in json.loads(data).get("error", ""), (st, data))
        st, data = req("/swap?job=racejob", "{}")
        check("server: a look change then is held the same", st == 409 and "export is running" in json.loads(data).get("error", ""), (st, data))
        _finish(rv, state="done", owner=os.getppid())
        st, data = req("/retime?job=racejob", "{}")
        check("server: once the export is done her page's changes go through again", st != 409, (st, data))
    finally:
        httpd.shutdown()
        srv.PROJECTS, srv.ve.job_dir = real_proj, real_jd


def main():
    tmp = tempfile.mkdtemp(prefix="export-race-")
    jd = os.path.join(tmp, "reel"); rv = os.path.join(jd, "review")
    os.makedirs(rv)
    try:
        test_exporting(jd, rv)
        test_todo(jd, rv)
        test_patient(jd, rv)
        test_server(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_export_watcher_race: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_export_watcher_race: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
