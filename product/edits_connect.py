#!/usr/bin/env python3
"""edits_connect.py — connect (or reconnect) the Edits app THROUGH the shim, in one step.

The creator's Bearer token lives in the Instagram Edits Kit in her library at yourbrand.com (she logs in,
opens her portal, opens the kit, and follows its connect steps) — not from the seller directly. Historically the
kit also showed a direct `claude mcp add --transport http …` command. On Claude Code 2.1.301 that direct connection loads zero Edits tools (see edits_mcp_shim.py
for the why). This routes the connection through product/edits_mcp_shim.py, which cleans the response so Claude
Code accepts it.

    python3 product/edits_connect.py                 # prints the command with a <token> placeholder
    python3 product/edits_connect.py --token abc123   # prints it ready to paste, token filled in
    python3 product/edits_connect.py --reconnect      # FIX an already-connected-but-broken setup, in place
    python3 product/edits_connect.py --remove         # print the disconnect command

**--reconnect is the one-phrase fix** for a creator who connected Edits the old (direct) way before this
version and now sees "tools fetch failed". It reads the token already in her Claude Code config (whether it's
sitting in a Bearer header from the old direct add, or in EDITS_MCP_TOKEN from a previous shim add), removes the
server, and re-adds it through the shim with that same token — so she never has to find the token again. Then it
checks the connection and says plainly whether the tools load now. If it can't find the token, it prints the
manual line to paste instead, so it never dead-ends.

It resolves the shim's absolute path and picks `python`/`python3` for the platform (Windows engines run under
Git Bash, where the interpreter is `python`), so the creator never has to edit the line.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "edits_mcp_shim.py")
NAME = "metapilot-native"


def _python_cmd():
    # Windows engines run natively under Git Bash, where the interpreter is `python` (python3 is a Store decoy).
    return "python" if sys.platform.startswith("win") or os.name == "nt" else "python3"


def command(token=None):
    tok = token or "<token>"
    py = _python_cmd()
    return (
        f'claude mcp add {NAME} --scope user '
        f'-e EDITS_MCP_TOKEN={tok} '
        f'-- {py} "{SHIM}"'
    )


def _run(args):
    """Run a `claude …` command, returning (ok, combined_output). Never raises on a non-zero exit."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return False, "the `claude` command isn't on your PATH"
    except Exception as e:  # timeout, etc.
        return False, str(e)


def _current_token():
    """The Edits token already in the Claude Code config, from either shape: the old direct add's
    `Authorization: Bearer <tok>` header, or a prior shim add's `EDITS_MCP_TOKEN=<tok>` env. None if absent."""
    ok, out = _run(["claude", "mcp", "get", NAME])
    if not ok and not out:
        return None
    m = re.search(r"EDITS_MCP_TOKEN=([A-Za-z0-9._\-]+)", out) or re.search(r"Bearer\s+([A-Za-z0-9._\-]+)", out)
    return m.group(1) if m else None


def _tools_ok():
    """Does Claude Code load the Edits tools now? Reads status; True only when connected AND not tools-failed."""
    ok, out = _run(["claude", "mcp", "get", NAME])
    low = out.lower()
    if "tools fetch failed" in low or "invalid result for tools/list" in low:
        return False
    return ("connected" in low) or ok


def reconnect():
    """Swap a broken direct connection for the shim, keeping the existing token. Never dead-ends."""
    tok = _current_token()
    _run(["claude", "mcp", "remove", NAME, "-s", "user"])  # ignore "not found"
    if not tok:
        print("I couldn't find your Edits token in the current connection.")
        print("Your token is in the Instagram Edits Kit in your library at yourbrand.com (log in, open your")
        print("portal, open the kit, follow its connect steps). Paste that token into this line and run it:")
        print("  " + command())
        return 1
    ok, out = _run(["claude", "mcp", "add", NAME, "--scope", "user",
                    "-e", f"EDITS_MCP_TOKEN={tok}", "--", _python_cmd(), SHIM])
    if not ok:
        print("Reconnect didn't go through. Paste this line to do it by hand:")
        print("  " + command(tok))
        return 1
    if _tools_ok():
        print("Edits is reconnected and the tools are loading. You're good to go.")
        return 0
    print("Reconnected. If Edits is open and the tools still don't show, quit and reopen the Edits app, "
          "then try your edit again.")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Connect or reconnect the Edits app through the shim.")
    ap.add_argument("--token", default=None, help="the Bearer token from the Edits app's kit")
    ap.add_argument("--reconnect", action="store_true",
                    help="fix an already-connected-but-broken setup in place (keeps the existing token)")
    ap.add_argument("--remove", action="store_true", help="instead print the command to disconnect it")
    a = ap.parse_args(argv)
    if a.remove:
        print(f"claude mcp remove {NAME} --scope user")
        return
    if a.reconnect:
        sys.exit(reconnect())
    print(command(a.token))


if __name__ == "__main__":
    main()
