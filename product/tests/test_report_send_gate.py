#!/usr/bin/env python3
"""Guards: nothing the buyer sees tells her to email a report until it passes the send test in /report-a-problem
(2026-10-27: too many reports. 2026-10-28: "make sure before sending out future problem reports that the user
is on the latest version", and "only for mass fixes across all engines. Individual problems machines can patch
themselves.")

  gate      product/report_gate.py refuses while a newer engine is out or the feed can't be read, refuses a
            missing reason, and only then stamps the report "Ready to send"
  skill     the send test names all three conditions and runs the gate; her machine's problem is patched, never
            sent; a failed test means no mention of a report or an email
  editor    the visual editor's Report a problem sends her to the chat, never straight to the inbox
  file      the editor's report file says to run /report-a-problem first
  scripts   the stall note and the setup smoke test point to Claude, not to the inbox
  homebase  the closing line no longer promises a report to email

Run: python3 product/tests/test_report_send_gate.py
"""
import os, sys, tempfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)

fails, total = [], 0


def check(name, ok, detail=""):
    global total
    total += 1
    if not ok:
        fails.append(name)
        print(f"  ✗ {name}  {detail}")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


skill = read(".claude", "skills", "report-a-problem", "SKILL.md")
check("skill: the send test exists", "the send test" in skill)
check("skill: test 1, her engine is the newest", "Her engine is the newest one" in skill)
check("skill: test 2, her machine is patched, never sent", "It is not her machine, her file or her setup" in skill
      and "Never a report." in skill)
check("skill: test 3, every engine needs the fix", "Every engine needs the fix" in skill)
check("skill: the gate stamps before she is asked to send", "report_gate.py --send" in skill and "SEND-READY" in skill)
check("skill: a failed test never mentions a report or email", "do not mention a report or an email" in skill)
check("skill: a fix to engine code is no longer sent in",
      "ask her, in one\nline, to send it in" not in skill and "the engine patched itself" in skill)
check("skill: one report per problem", "One report per problem" in skill)

html = read("product", "visual-editor", "editor.html")
i = html.find('$("reportBtn").onclick')
block = html[i:i + 4000]
check("editor: the Report a problem button is there", i > 0)
check("editor: the ready sheet no longer says to email the file", "Email this file" not in block, block[:200])
check("editor: the ready sheet sends her to /report-a-problem", "type <b>/report-a-problem</b>. I'll read it" in block)
check("editor: the first sheet no longer says she emails it", "you email it" not in block)

import editor_errors as ee  # noqa: E402
tmp = tempfile.mkdtemp(prefix="ree-send-gate-")
ee.ROOT = tmp
ee.HANDOFF = os.path.join(tmp, "_handoff")   # its report file lands in the temp folder, never the engine's
try:
    path = ee.bundle(job=None, note="the play button stopped")
    body = open(path, encoding="utf-8").read()
    check("file: says run /report-a-problem first", "Type /report-a-problem in the chat first" in body, body[:300])
    check("file: no bare 'Send this file to'", "Send this file to" not in body)
except Exception as e:
    check("file: the editor report still builds", False, repr(e))

render = read("product", "reel_render.py")
check("stall note: no 'send me that file'", "send me that file" not in render)
smoke = read("scripts", "smoke-test.sh")
check("smoke test: no 'email it to'", "email it to:" not in smoke)
check("smoke test: Claude fixes it first", "Claude fixes it first" in smoke)
home = read(".claude", "skills", "homebase", "SKILL.md")
check("homebase: no promise of a report to email", "show you how to email it" not in home)

handoff = read("product", "make-handoff.py")
check("handoff: no 'If you're good with it, email it to'", "If you're good with it, email it to" not in handoff)
check("intel diagnostic: no 'email it to'", "then email it to" not in read("product", "intel-render-diagnostic.py"))
check("CLAUDE.md: the rule names the gate", "report_gate.py --send" in read("CLAUDE.md"))

# The gate itself, against a stand-in for the updater (no network)
import report_gate as rg  # noqa: E402


class FakeUpdater:
    def __init__(self, cur, feeds, channel=""):
        self.cur, self.feeds, self.channel = cur, feeds, channel

    def load_product(self):
        return {"version": self.cur}

    def _update_url(self):
        return "https://feed.example"

    def _saved_channel(self):
        return self.channel

    def _read_feed(self, url):
        v = self.feeds.get(url)
        return (None, OSError("offline")) if v is None else ({"version": v}, None)

    def _signature_module(self):
        class _S:
            @staticmethod
            def check_feed(feed):
                return ""
        return _S

    @staticmethod
    def semver(v):
        return tuple(int(x) for x in v.split("."))


main = "https://feed.example/latest.json"
st, *_ = rg.newest_check(FakeUpdater("2.3.16", {main: "2.3.17"}))
check("gate: behind when the feed is newer", st == rg.BEHIND, st)
st, *_ = rg.newest_check(FakeUpdater("2.3.17", {main: "2.3.17"}))
check("gate: newest when it matches", st == rg.NEWEST, st)
st, *_ = rg.newest_check(FakeUpdater("2.3.17", {}))
check("gate: can't tell when the feed is down", st == rg.UNKNOWN, st)
st, *_ = rg.newest_check(FakeUpdater("2.3.17", {main: "2.3.17", "https://feed.example/early/x/latest.json": "2.3.18"},
                                     channel="early/x"))
check("gate: an early-access feed ahead of hers counts as behind", st == rg.BEHIND, st)

rep = os.path.join(tmp, "problem-report.md")
with open(rep, "w", encoding="utf-8") as f:
    f.write("## Problem report\n\n### What happened\n\nIt broke.\n")
real = rg.newest_check
try:
    rg.newest_check = lambda updater=None: (rg.BEHIND, "2.3.16", "2.3.17", "v2.3.17 is out")
    check("gate: --send refuses an engine that is behind",
          rg.main(["--send", "every engine cuts this word in half on a normal clip", "--report", rep]) == rg.BEHIND)
    check("gate: nothing stamped while behind", "Ready to send" not in open(rep, encoding="utf-8").read())
    rg.newest_check = lambda updater=None: (rg.NEWEST, "2.3.17", "2.3.17", "v2.3.17 is the newest")
    check("gate: --send refuses a missing reason", rg.main(["--send", "her mac", "--report", rep]) == 4)
    check("gate: --send stamps when both pass",
          rg.main(["--send", "every engine cuts this word in half on a normal clip", "--report", rep]) == 0)
    rg.main(["--send", "every engine cuts this word in half on a normal clip", "--report", rep])
    body = open(rep, encoding="utf-8").read()
    check("gate: the stamp names the version and the reason",
          "### Ready to send" in body and "v2.3.17" in body and "cuts this word in half" in body, body[-300:])
    check("gate: stamping twice leaves one block", body.count("### Ready to send") == 1)
finally:
    rg.newest_check = real

print(f"{total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
