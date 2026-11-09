#!/usr/bin/env python3
"""library-server.py — serve the Effects Library to her own browser at http://127.0.0.1, so its sounds play.

WHY: Safari will not let a page opened as a file (file://) play the sound files beside it. Every play button
failed and the page blamed "the preview window" while she was already in her own browser (a buyer on Safari,
2026-10-06). Chrome allowed it, Safari did not. Served over http from this computer, the page and its sounds
come from one place and every browser plays them.

What it serves: only the files the library page reads (product/ and the bundled sound folder). Nothing else in
the engine folder, so her brand kit and projects are never reachable, and only from this computer (127.0.0.1).
It writes its port to _local/library-server.json and exits on its own after an hour with no requests.
Started by scripts/open-library.sh; nothing to run by hand.

Her hearts: GET /favorites reads and POST /favorites writes favorites/effects.json, the effects she hearted, by
name. Her favorites folder is hers: no update touches it and it never ships, so a heart survives every update and
every HyperFrames refresh. A write is accepted only from the page this server serves (same origin), never from a
web page elsewhere that happens to know the port.
"""
import functools, http.server, json, os, sys, tempfile, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = ("/product/", "/.claude/skills/media-use/audio/assets/", "/assets/fonts/")
STATE = os.path.join(ROOT, "_local", "library-server.json")
FAVS = os.path.join(ROOT, "favorites", "effects.json")
IDLE_SECONDS = 3600
_ALLOWED_REAL = tuple(os.path.realpath(os.path.join(ROOT, p.strip("/"))) + os.sep for p in ALLOWED)
_last = [time.time()]


def read_favorites():
    try:
        data = json.load(open(FAVS, encoding="utf-8"))
        return [str(n) for n in data.get("effects", []) if isinstance(n, str)], True
    except FileNotFoundError:
        return [], False
    except Exception:
        return [], True                  # unreadable: never let the page overwrite it with an empty list


def write_favorites(names):
    os.makedirs(os.path.dirname(FAVS), exist_ok=True)
    names = sorted({n.strip() for n in names if isinstance(n, str) and n.strip() and len(n) < 120})
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(FAVS), prefix=".effects-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"effects": names, "about": "Effects she hearted in the Effects Library. Hers: updates never touch it."},
                  fh, indent=1)
        fh.write("\n")
    os.replace(tmp, FAVS)               # all at once, so a crash mid-write never leaves half a file
    return names


class Handler(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, body):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path.split("?")[0] != "/favorites":
            self.send_error(404)
            return
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin", "")
        if origin != f"http://{host}" or not host.startswith("127.0.0.1:"):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 200_000:
                raise ValueError("too large")
            names = json.loads(self.rfile.read(length).decode("utf-8")).get("effects")
            if not isinstance(names, list):
                raise ValueError("no list")
        except Exception:
            self.send_error(400)
            return
        _last[0] = time.time()
        self._json(200, {"effects": write_favorites(names), "saved": True})

    def do_GET(self):
        if self.path.split("?")[0] == "/favorites":
            _last[0] = time.time()
            names, exists = read_favorites()
            self._json(200, {"effects": names, "exists": exists})
            return
        # Judge the file the request would actually reach (decoded, resolved), never the raw path text:
        # "product/%2e%2e/brand-kit.md" reads as inside product/ and resolves to the engine folder.
        full = os.path.realpath(self.translate_path(self.path))
        if not any(full == r.rstrip(os.sep) or full.startswith(r) for r in _ALLOWED_REAL):
            self.send_error(404)
            return
        _last[0] = time.time()
        super().do_GET()

    do_HEAD = do_GET

    def log_message(self, *a):          # quiet: nobody reads these
        pass


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=ROOT))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump({"port": srv.server_address[1], "pid": os.getpid()}, fh)

    def watchdog():
        while time.time() - _last[0] < IDLE_SECONDS:
            time.sleep(30)
        srv.shutdown()

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        srv.serve_forever()
    finally:
        try:
            if json.load(open(STATE, encoding="utf-8")).get("pid") == os.getpid():
                os.remove(STATE)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
