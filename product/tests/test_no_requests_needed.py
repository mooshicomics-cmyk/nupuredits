#!/usr/bin/env python3
"""Guards: the CapCut builders work on a Python without the `requests` package.

Buyer reports 2026-10-19 (Mac and Windows): setting a default pack imports cleanyap.py, whose unused top-level
`import requests` died with "No module named 'requests'" under plain python3. Both of their Claudes patched the line
out by hand. Now:

  import     cleanyap and superyap import with `requests` blocked
  post       vectcut_engine.post talks to a VectCut stand-in through urllib when `requests` is missing: a JSON
             reply comes back, a 4xx reply still comes back as VectCut's own envelope, a dead port is a
             ConnectionError, a slow reply is a Timeout

Run: python3 product/tests/test_no_requests_needed.py
"""
import http.server, json, os, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)


class _Block:
    """Makes `import requests` fail the way it does on a machine that never installed it."""
    def find_spec(self, name, path=None, target=None):
        if name == "requests" or name.startswith("requests."):
            raise ModuleNotFoundError("No module named 'requests'")
        return None


for m in [m for m in sys.modules if m == "requests" or m.startswith("requests.")]:
    del sys.modules[m]
sys.meta_path.insert(0, _Block())

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}: {detail}")


try:
    import cleanyap, superyap  # noqa: F401
    check("import", True)
except ModuleNotFoundError as e:
    check("import", False, str(e))

import vectcut_engine as ve

check("fallback", ve._http() is ve._StdlibHTTP, "requests is blocked, so _http() must be the urllib stand-in")


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/slow":
            time.sleep(1.5)
        code = 404 if self.path == "/missing" else 200
        out = json.dumps({"success": code == 200, "output": {"echo": body}, "error": "" if code == 200 else "nope"})
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
ve._STATE["checked"] = True                      # the stand-in is up; skip the VectCut launcher

j = ve.post(base, "add_text", {"text": "hi"})
check("post", j.get("success") and j["output"]["echo"] == {"text": "hi"}, repr(j))

r = ve._StdlibHTTP.post(f"{base}/missing", json={})
check("4xx", r.status_code == 404 and r.json().get("error") == "nope", f"{r.status_code} {r.text!r}")

H_ = ve._StdlibHTTP
try:
    H_.post("http://127.0.0.1:9/x", json={}, timeout=2)
    check("dead port", False, "no error raised")
except H_.exceptions.ConnectionError:
    check("dead port", True)
except Exception as e:
    check("dead port", False, f"{type(e).__name__}: {e}")

try:
    H_.post(f"{base}/slow", json={}, timeout=0.3)
    check("timeout", False, "no error raised")
except H_.exceptions.Timeout:
    check("timeout", True)
except Exception as e:
    check("timeout", False, f"{type(e).__name__}: {e}")

srv.shutdown()
print(f"{total - len(fails)}/{total} passed")
for f in fails:
    print("  FAIL", f)
sys.exit(1 if fails else 0)
