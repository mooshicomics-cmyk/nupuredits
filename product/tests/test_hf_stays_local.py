#!/usr/bin/env python3
"""Guard: a HyperFrames skill sync never teaches the engine to send her work away or spend her credits.

HyperFrames releases 0.8.216 to 0.8.230 added `billing` (reads her HyperFrames sign-in), `media-use generate` and
`transcribe --engine heygen` (send her photos, voice or footage to HeyGen and spend credits), and skill text that
makes `cloud render` the final render on a paid plan and says never to tell the person a price. Release 0.9.6 added
`audio --read` through her HeyGen sign-in (uploads her audio stems) and `reverse start` (notes a run with HeyGen). Upstream's text comes
back on every sync, so this holds the engine's side of it: the commands stay denied, in .claude/settings.json and in
the list that survives an update, and the guidance stays out.

Run: python3 product/tests/test_hf_stays_local.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from settings_persist import ENGINE_PERMISSIONS

fails = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


FORMS = ("npx hyperframes {}", "npx hyperframes@* {}", "npx --yes hyperframes {}", "npx --yes hyperframes@* {}",
         "npx.cmd hyperframes {}", "npx.cmd hyperframes@* {}")
COMMANDS = ("usage*", "feedback*", "billing*", "media-use generate*", "transcribe*--engine*heygen*", "audio*--read*",
            "reverse*")

deny = json.loads(read(".claude/settings.json"))["permissions"]["deny"]
for cmd in COMMANDS:
    rules = [f"Bash({form.format(cmd)})" for form in FORMS]
    check(f"denied in .claude/settings.json: {cmd}", all(r in deny for r in rules))
    check(f"denied after an update: {cmd}", all(r in ENGINE_PERMISSIONS["deny"] for r in rules))

SKILLS = ".claude/skills/"
for rel, gone in (
    ("hyperframes-cli/TOOLKIT.md", "paid plan: `cloud render"),
    ("hyperframes-cli/references/cloud.md", "Final renders on a paid plan"),
    ("hyperframes-cli/references/preview-render.md", "for the final render on a paid HyperFrames plan"),
    ("media-use/TOOLKIT.md", "Never tell the person prices"),
    ("media-use/TOOLKIT.md", "| `references/heygen.md` |"),
    ("media-use/references/setup-providers.md", "the Credits rule"),
):
    check(f"{rel} leaves out: {gone}", gone not in read(SKILLS + rel))
check("the paid-plan guide is not carried", not os.path.exists(os.path.join(ROOT, SKILLS, "media-use/references/heygen.md")))
check("the paid reverse-a-video skill is not carried", not os.path.exists(os.path.join(ROOT, SKILLS, "reverse-any-video")))
# HyperFrames release 0.9.3 names that skill in three guides the engine carries, which would send Claude looking for it.
for rel in ("hyperframes/TOOLKIT.md", "hyperframes/references/skill-lifecycle.md",
            "hyperframes-cli/references/init-and-scaffold.md"):
    check(f"{rel} does not route to the paid reverse-a-video skill", "reverse-any-video" not in read(SKILLS + rel))

print("test_hf_stays_local:", "FAILED" if fails else "OK")
sys.exit(1 if fails else 0)
