#!/usr/bin/env python3
"""edits_mcp_shim.py — a tiny LOCAL bridge that lets Claude Code load the Edits app's tools.

WHY THIS EXISTS (the bug it works around)
-----------------------------------------
Instagram's Edits app exposes its editing tools over a local MCP server (metapilot-native, Streamable HTTP on
127.0.0.1:19501). Its `tools/list` answer carries a non-standard top-level `resultType` key. Claude Code
**2.1.301** reads `resultType` as a "cached result" marker and then REQUIRES two companion fields the Edits
server never sends (`ttlMs`, `cacheScope`), so its validator throws out the whole tool list:

    tools fetch failed — Invalid result for tools/list:
      ttlMs: expected number, received undefined
      cacheScope: expected one of "public" | "private"

The connection is fine; the server answers correctly over curl. It is purely a client↔server mismatch on that
one combination (Claude Code 2.1.301 + Edits ~454). We can't patch Claude Code or the Edits binary, so the
engine ships THIS: a stdio⇄HTTP pass-through that forwards every message to the real Edits server unchanged and
only strips the offending `resultType` key off the way back, so Claude Code sees a clean, spec-compliant result
and loads the Edits tools. Everything else is relayed byte-for-byte.

TOOL-LIST TRIM (token cost, 2026-11-07)
---------------------------------------
Once connected, the Edits app advertises ~270 tools (every effect, sticker, transition, font and audio clip in
its catalog). Claude Code keeps that whole menu resident, so it is re-read on EVERY turn of EVERY session the
connection lives in — even a rough cut that never touches Edits. The engine only ever drives Edits as an EXPORT
destination (build a project, import the cut, stack the rendered looks as overlays, save; see the edits-export
skill), which touches ~a dozen tools. So this shim also trims the `tools/list` answer down to the exact
project / media / clip / overlay / export tools the handoff uses (see `_ALLOW_NAMES`), dropping the catalog.
Verified against a live Edits `tools/list` on 2026-11-07: **38 of 274 tools kept, 236 dropped (~86%)** — that
much less tool-menu tax on EVERY turn, for every Edits Kit buyer, with no loss of the export flow.

Three safety nets keep the trim from ever stranding an export:
  * if the allowlist would match NOTHING in a given `tools/list` (e.g. the Edits app renamed everything), the
    full list is passed through unchanged — the trim can only ever remove tools it is sure are off-path;
  * `EDITS_MCP_TOOLS=all` (or `EDITS_MCP_ALL_TOOLS=1`) turns the trim off entirely, restoring the full menu;
  * the edits-export skill already degrades to CapCut if an Edits tool it needs isn't there, so the worst case
    is the existing, tested fallback — never a dead end.
Only `tools/list` is ever filtered; a `tools/call` is always forwarded, so nothing the model does is blocked
here. Everything else is still relayed byte-for-byte.

WHAT IT IS
----------
A **stdio** MCP server (what `claude mcp add -- python3 edits_mcp_shim.py` launches) that is also an HTTP MCP
**client** to the Edits app. It is a transparent proxy: protocol-version negotiation, the session id, tool
calls and errors all come from the real server. The ONLY mutation is removing `resultType` from each result.

- Localhost only. It talks to 127.0.0.1:19501 and nothing else. Her footage, project names and transcripts
  never leave the machine; this process has no network reach beyond the Edits app's own local port.
- Pure standard library (no pip installs), so any Python 3.8+ runs it on Mac, Windows (Git Bash) or Intel.

CONNECT (the engine's edits-kit prints the exact line; `edits_connect.py` fills in the path + token):
    claude mcp add metapilot-native --scope user -e EDITS_MCP_TOKEN=<token> -- \
        python3 /abs/path/product/edits_mcp_shim.py

Config (all optional, read from the environment Claude Code passes in):
    EDITS_MCP_TOKEN   the Bearer token from the Edits app's kit (required to drive the app)
    EDITS_MCP_URL     full endpoint; overrides host/port/path (default http://127.0.0.1:19501/mcp)
    EDITS_MCP_HOST    default 127.0.0.1
    EDITS_MCP_PORT    default 19501
    EDITS_MCP_PATH    default /mcp
"""
import json
import os
import sys
import urllib.error
import urllib.request

# The one non-spec key that trips Claude Code 2.1.301's tools/list validator. Stripping it makes every result
# parse as an ordinary (non-cached) result, which is what the Edits server actually means by resultType:"complete".
_STRIP_KEYS = ("resultType",)

# The exact tools the export handoff uses (edits-export skill), VERIFIED against a live Edits tools/list
# (~274 tools) on 2026-11-07: this keeps 38, drops 236 (~86%). Comparison is case- and separator-insensitive,
# so a future rename between camelCase / snake_case / kebab-case still matches. Everything NOT here is bulk
# catalog the engine never calls (effects, filters, stickers, transitions, fonts, stock, audio/music/SFX,
# teleprompter, voiceover, text, catalog browse/search, playback, panel UI). To keep another tool, add its
# exact name. (Captions are baked into the rendered looks on a medium build, so the caption tools are
# deliberately dropped — see the edits-export skill.)
_ALLOW_NAMES = (
    # project lifecycle + inspection
    "newProject", "openProject", "closeProject", "renameProject", "saveProject", "deleteProject", "projects",
    "appState", "state", "getCapabilities",
    # frame / canvas
    "setAspectRatio", "setCanvas", "getCanvas", "setFrameRate",
    # media import (the staged cut)
    "importMedia",
    # cutting the main track, only when base.cut is true: split + ripple-delete
    "clips", "clipMetadata", "split", "splitAt", "splitClip", "delete", "rippleState", "setRippleTiers",
    # the looks as their own overlay layers, trimmed flush
    "addOverlay", "convertToOverlay", "moveToLayer", "setLayerVisibility",
    "trim", "trimClip", "trimStart", "trimEnd",
    # verify the composite
    "captureFrame", "captureSourceFrames", "frameSheet",
    # export (finish)
    "export", "exportStatus", "setExportSettings", "cancelExport",
)
_ALLOW_NORM = frozenset(k.replace("_", "").replace("-", "").lower() for k in _ALLOW_NAMES)

_STATE = {"session": None, "protocol": None, "trim_noted": False}


def _trim_off():
    """True when the operator has asked for the full (untrimmed) Edits tool menu."""
    return (os.environ.get("EDITS_MCP_TOOLS", "").strip().lower() == "all"
            or os.environ.get("EDITS_MCP_ALL_TOOLS", "").strip() not in ("", "0", "false", "no"))


def _tool_on_path(name):
    return str(name or "").replace("_", "").replace("-", "").lower() in _ALLOW_NORM


def _filter_tools(result):
    """Trim a tools/list result down to the export-path family. Mutates `result` in place.

    Safety: if NOTHING matches (the app renamed everything), leave the list untouched — the trim only ever
    removes tools it is confident are off-path, so it can never strand an export by hiding the whole menu."""
    if _trim_off():
        return
    tools = result.get("tools")
    if not isinstance(tools, list) or not tools:
        return
    kept = [t for t in tools if isinstance(t, dict) and _tool_on_path(t.get("name"))]
    if not kept or len(kept) == len(tools):
        return  # no match (failsafe) or nothing to drop: leave it exactly as the server sent it
    result["tools"] = kept
    if not _STATE["trim_noted"]:
        _STATE["trim_noted"] = True
        sys.stderr.write(
            f"[edits-shim] trimmed the Edits tool menu to the export family: {len(kept)} of {len(tools)} tools "
            f"kept (set EDITS_MCP_TOOLS=all to restore the full menu).\n")
        sys.stderr.flush()


def _endpoint():
    url = os.environ.get("EDITS_MCP_URL")
    if url:
        return url
    host = os.environ.get("EDITS_MCP_HOST", "127.0.0.1")
    port = os.environ.get("EDITS_MCP_PORT", "19501")
    path = os.environ.get("EDITS_MCP_PATH", "/mcp")
    if not path.startswith("/"):
        path = "/" + path
    return f"http://{host}:{port}{path}"


def _token():
    return os.environ.get("EDITS_MCP_TOKEN") or os.environ.get("EDITS_TOKEN") or ""


def _clean(message):
    """Strip the non-spec result marker so Claude Code accepts the result, and trim the tools/list menu to the
    export-path family. Mutates in place, returns message."""
    if isinstance(message, dict):
        result = message.get("result")
        if isinstance(result, dict):
            for k in _STRIP_KEYS:
                result.pop(k, None)
            if "tools" in result:
                _filter_tools(result)
    return message


def _parse_sse(body):
    """Pull every JSON-RPC object out of an SSE body (one per `data:` payload)."""
    out = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        data = "".join(
            line[len("data:"):].lstrip()
            for line in block.split("\n")
            if line.startswith("data:")
        )
        if not data:
            continue
        try:
            out.append(json.loads(data))
        except ValueError:
            pass
    return out


def _forward(message):
    """POST one JSON-RPC message to the Edits server; return a list of JSON-RPC objects it answered with.

    A notification (no id) normally comes back as 202 with an empty body -> []. Captures and reuses the
    Mcp-Session-Id and the negotiated protocol version so the handshake behaves like a direct connection."""
    data = json.dumps(message).encode("utf-8")
    req = urllib.request.Request(_endpoint(), data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    tok = _token()
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    if _STATE["session"]:
        req.add_header("Mcp-Session-Id", _STATE["session"])
    if _STATE["protocol"]:
        req.add_header("MCP-Protocol-Version", _STATE["protocol"])

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        status = resp.getcode()
        headers = resp.headers
        body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        headers = e.headers
        body = e.read().decode("utf-8", "replace") if e.fp else ""
    except Exception as e:  # connection refused, timeout, DNS, etc.
        raise _ForwardError(str(e))

    sid = headers.get("Mcp-Session-Id") if headers else None
    if sid:
        _STATE["session"] = sid

    if status == 202 or not body.strip():
        return []
    ctype = (headers.get("Content-Type", "") if headers else "").lower()
    objs = _parse_sse(body) if "text/event-stream" in ctype else [_one(body)]
    objs = [o for o in objs if o is not None]

    # Remember the protocol version the server negotiated, to echo on later requests.
    for o in objs:
        res = o.get("result") if isinstance(o, dict) else None
        if isinstance(res, dict) and res.get("protocolVersion"):
            _STATE["protocol"] = res["protocolVersion"]
    return objs


def _one(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


class _ForwardError(Exception):
    pass


def _emit(obj):
    sys.stdout.write(json.dumps(_clean(obj)) + "\n")
    sys.stdout.flush()


def main():
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    while True:
        line = sys.stdin.readline()
        if line == "":  # EOF: Claude Code closed the pipe
            break
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue

        has_id = isinstance(message, dict) and message.get("id") is not None
        try:
            answers = _forward(message)
        except _ForwardError as err:
            # Surface a clean JSON-RPC error to Claude Code for a request; swallow it for a notification.
            if has_id:
                _emit({
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {
                        "code": -32000,
                        "message": f"edits shim could not reach the Edits app at {_endpoint()}: {err}. "
                                   f"Open the Edits app and check the token, then reconnect.",
                    },
                })
            continue
        for ans in answers:
            _emit(ans)


if __name__ == "__main__":
    main()
