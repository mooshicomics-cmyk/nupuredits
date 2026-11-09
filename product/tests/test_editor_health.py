#!/usr/bin/env python3
"""Guards: her visual editor page never opens with a hole in it. A brand-new reel once opened with no waveform and
no line stills (they were made before its preview existed), so the page's pieces are checked from the files
themselves, from three sides:

  engine    editor_health finds a missing waveform, missing / empty stills and a waveform older than the preview,
            and rebuilds each from the preview; a reel with nothing missing is left alone
  server    asking the page server for a missing waveform or still makes it on the spot and serves it
  page      the page asks again for a waveform or still that didn't come (checked in its source here; the
            headless page test drives the page itself)

Run: python3 product/tests/test_editor_health.py
"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
os.environ.setdefault("REE_EDITOR", "1")   # guards for an engine with the editor on (product/early_access.py)
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)   # never into the real editor log

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def make_reel(root, name):
    jd = os.path.join(root, name)
    rv = os.path.join(jd, "review")
    os.makedirs(rv, exist_ok=True)
    words = [{"t": f"w{i}", "s": i * 1.0, "e": i * 1.0 + 0.6} for i in range(4)]
    json.dump({"job": name, "words": words, "lines": [[0, 1], [2, 3]], "segs": [{"s": 0, "e": 1.6, "w": [0, 1]}, {"s": 2.9, "e": 3.7, "w": [3]}]}, open(os.path.join(rv, "script.json"), "w", encoding="utf-8"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", os.path.join(rv, "preview.mp4")], check=True)
    return jd


def main():
    tmp = tempfile.mkdtemp(prefix="editor-health-")
    try:
        jd = make_reel(tmp, "fresh")
        rv = os.path.join(jd, "review")
        h = ve.editor_health(jd, repair=False)
        check("engine: a brand-new reel shows its waveform and stills missing",
              "waveform" in h["missing"] and "still w0" in h["missing"] and "still w2" in h["missing"], h)
        check("engine: and a still for every piece's first word, not only each line's", "still w3" in h["missing"], h)
        h = ve.editor_health(jd, preview=False)
        check("engine: and makes them from the preview", not h["still_missing"] and set(h["fixed"]) == set(h["missing"]), h)
        check("engine: the waveform has sound in it", len(json.load(open(os.path.join(rv, "peaks.json"), encoding="utf-8"))["peaks"]) > 50)
        check("engine: nothing missing = nothing touched", ve.editor_health(jd, preview=False)["missing"] == [])
        open(os.path.join(rv, "strip", "w2.jpg"), "wb").close()                      # an empty still
        old = time.time() - 60
        os.utime(os.path.join(rv, "peaks.json"), (old, old))                       # a waveform older than the preview
        h = ve.editor_health(jd, preview=False)
        check("engine: an empty still and an out-of-date waveform are caught and remade",
              {"still w2", "waveform"} <= set(h["missing"]) and not h["still_missing"], h)

        # the server: a missing piece is made when the page asks for it
        import visual_editor_server as srv
        srv.PROJECTS = tmp
        JOB = "served"
        jd2 = make_reel(tmp, JOB)
        httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]

        def get(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=60) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, b""
        st, body = get(f"/projects/{JOB}/review/peaks.json")
        check("server: a missing waveform is made and served", st == 200 and json.loads(body)["peaks"], st)
        st, body = get(f"/projects/{JOB}/review/strip/w2.jpg")
        check("server: a missing line still is made and served", st == 200 and body[:2] == b"\xff\xd8", st)
        st, body = get(f"/projects/{JOB}/review/strip/w1.jpg")
        check("server: a still for any piece's first word (not only a line's) is made and served", st == 200 and body[:2] == b"\xff\xd8", st)
        check("server: a still for a word the reel doesn't have stays a 404", get(f"/projects/{JOB}/review/strip/w9.jpg")[0] == 404)
        httpd.shutdown()

        page = open(os.path.join(PRODUCT, "visual-editor", "editor.html"), encoding="utf-8").read()
        check("page: asks again for a waveform that didn't come", "function loadPeaks(tries)" in page and "loadPeaks(3)" in page)
        check("page: asks again for a line still that didn't load", "function checkStills()" in page and "stripV" in page)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_editor_health: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_editor_health: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
