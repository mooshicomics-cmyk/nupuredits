#!/usr/bin/env python3
"""layer_probe.py — which kinds of element are in THIS reel, so the checkbox list is never a lie.

WHY THIS EXISTS. /separate-layers asks the creator to tick which layers she wants split out. Offering her
a fixed menu of six would be offering things her reel does not contain, and she would tick one and get
nothing. So the menu is built from her actual reel: this reads the already-generated overlay HTML and
reports only the groups that have clips in it, with how many and when they are on screen.

It does NOT render anything and does NOT cost a render. It reads `index.html`, which the type builder
writes in a fraction of a second. If that file is missing it builds it once (still no render).

  python3 product/layer_probe.py <JOB> <PACK>            # human-readable, for Claude to turn into a list
  python3 product/layer_probe.py <JOB> <PACK> --json     # machine-readable
  (leave <PACK> out to use her saved default pack; with none saved it asks for one instead of guessing)

Exit 0 with at least one group · exit 3 when the reel has no separable layers at all.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# Must stay in step with _GROUP_TRACKS in build-reel-type.py. Elements are any lane >= 7 (see _etrk).
GROUP_TRACKS = {"captions": (1,), "hook": (2,), "vibe": (3,), "label": (4,), "takeover": (5,),
                "breakaway": (6,)}
ELEMENTS_FROM = 7
BLURB = {
    "captions":  "the spoken-word captions",
    "hook":      "the opening hook",
    "vibe":      "the vibe element (sparkles, bubble, doodle)",
    "label":     "the corner label",
    "takeover":  "the full-screen word takeovers",
    "breakaway": "the breakaway card",
    "elements":  "stars, counters and badges",
}
# What to pre-tick. These are the two people actually reposition by hand; the rest are opt-in so a long
# reel does not quietly turn into six renders. (Cost is one render per ticked group, plus one more for
# everything left unticked, which separate_layers.sh hands over together as a "rest" layer — see the skill.)
DEFAULT_ON = ("captions", "hook")

CLIPRX = re.compile(
    r'data-start="(\d+(?:\.\d+)?)" data-duration="(\d+(?:\.\d+)?)" data-track-index="(\d+)"')


def group_of(track):
    for name, tracks in GROUP_TRACKS.items():
        if track in tracks:
            return name
    return "elements" if track >= ELEMENTS_FROM else None


def _crash(text):
    """(error line, "file:line") when `text` holds a Python crash (a traceback, or a SyntaxError, which
    Python reports without one), else None. The file is the last frame the traceback names, which is where
    it actually broke."""
    lines = [l.rstrip() for l in (text or "").splitlines()]
    err = next((l.strip() for l in reversed(lines)
                if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt)\b(:|$)", l.strip())), None)
    if not err or not any(l.startswith("Traceback") or l.lstrip().startswith("File \"") for l in lines):
        return None
    where = None
    for l in lines:
        m = re.match(r'^\s*File "([^"]+)", line (\d+)', l)
        if m:
            f = m.group(1)
            if os.path.isabs(f) and os.path.abspath(f).startswith(ROOT + os.sep):
                f = os.path.relpath(f, ROOT)
            where = f"{f}:{m.group(2)}"
    return err, where


def explain_build_failure(text, rc):
    """What to tell her when the graphics build did not produce a page, as printable lines.

    Two different things used to come out as one sentence. A builder that CRASHED (a bug in the engine, as
    when a newer-Python-only line reached an older Python and every build died with a SyntaxError) was
    reported as "this reel has no graphics to separate yet", with the real reason squeezed into a one-line
    "Why:" that read like a detail. That sent her off to build graphics that could not build. So a crash is
    named as a crash, with its error and where it happened; a builder that stopped on purpose with its own
    message is still a reason about the reel."""
    crash = _crash(text)
    if crash:
        err, where = crash
        out = ["  ⛔ the graphics builder crashed, so I could not read this reel's layers. This is a problem in "
               "the engine, not in your reel.",
               f"  Error: {err}"]
        if where:
            out.append(f"  Where: {where}")
        out.append("  Run /report-a-problem and include these lines. Building again will not get past it.")
        return out
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    why = lines[-1] if lines else "the graphics for this reel have not been built yet"
    return ["  ⛔ this reel has no graphics to separate yet.", f"  Why: {why}",
            "  Build the reel's graphics first, then ask again."]


def probe(job, pack):
    out_dir = os.path.join(ROOT, "projects", job, f"hf-reel-type-{pack.lower()}")
    index = os.path.join(out_dir, "index.html")
    if not os.path.exists(index):
        job_dir = os.path.join(ROOT, "projects", job)
        if not os.path.isdir(job_dir):
            # Name her the reels that DO exist rather than a traceback. A wrong or mistyped job name is
            # the likeliest way into this branch, and a buyer cannot act on a stack trace.
            try:
                have = sorted(d for d in os.listdir(os.path.join(ROOT, "projects"))
                              if not d.startswith(("_", ".")))
            except OSError:
                have = []
            listing = ("\n    ".join(have[:12]) or "(none yet)")
            sys.exit(f"  ⛔ I cannot find a reel called {job!r}.\n  Reels I can see:\n    {listing}")
        env = dict(os.environ, JOB=job, STYLE_PACK=pack, LAYER="all")
        r = subprocess.run([sys.executable, os.path.join(HERE, "build-reel-type.py")],
                           env=env, capture_output=True, text=True)
        if not os.path.exists(index):
            sys.exit("\n".join(explain_build_failure((r.stderr or "") + (r.stdout or ""), r.returncode)))

    found = {}
    for start, dur, track in CLIPRX.findall(open(index, encoding="utf-8").read()):
        g = group_of(int(track))
        if not g:
            continue          # track 0 is the preview background, not hers to move
        start, end = float(start), float(start) + float(dur)
        e = found.setdefault(g, {"group": g, "clips": 0, "start": start, "end": end})
        e["clips"] += 1
        e["start"] = min(e["start"], start)
        e["end"] = max(e["end"], end)

    order = list(GROUP_TRACKS) + ["elements"]
    rows = sorted(found.values(), key=lambda e: order.index(e["group"]))
    for e in rows:
        e["blurb"] = BLURB.get(e["group"], e["group"])
        e["default_on"] = e["group"] in DEFAULT_ON
    return rows


def _saved_pack():
    """Her saved default style pack (creative-vault/user-style.json "default_pack"), or None. The same field
    build-reel-type.py and the CapCut lanes (cleanyap.default_pack) read (user_style.py)."""
    try:
        sys.path.insert(0, HERE)
        import user_style
        return user_style.default_pack(os.path.join(HERE, "creative-vault", "user-style.json"))
    except Exception:
        return None


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--explain":
        # separate_layers.sh hands over a failed build's log so a crash is said the same way here and there.
        # usage: layer_probe.py --explain <log> [exit code] [what was being built]
        try:
            text = open(sys.argv[2], encoding="utf-8", errors="replace").read()
        except OSError:
            text = ""
        rc = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].lstrip("-").isdigit() else 1
        what = sys.argv[4] if len(sys.argv) > 4 else ""
        crash = _crash(text)
        if crash:
            lines = explain_build_failure(text, rc)
            if what:
                lines[0] = lines[0].replace("so I could not read this reel's layers",
                                            f"while building the {what} layer")
        else:
            tail = [l.strip() for l in text.strip().splitlines() if l.strip()][-6:]
            lines = [f"  ⛔ the {what or 'graphics'} build stopped (exit {rc}). What it said:"] + \
                    [f"       {l}" for l in (tail or ["(nothing)"])]
        print("\n".join(lines))
        sys.exit(0)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 1:
        sys.exit("usage: layer_probe.py <JOB> <PACK> [--json]")
    job = args[0]
    # The pack she names, else her saved default. Never a pack she did not pick: the layers are read off a
    # build in that pack, and a guessed pack builds (and lists) a reel in a look that is not hers.
    pack = (args[1] if len(args) > 1 else "") or _saved_pack()
    if not pack:
        sys.path.insert(0, HERE)
        try:
            import stylepack
            have = ", ".join(stylepack.names())
        except Exception:
            have = "Editorial, Butter, Playful"
        sys.exit(f"  ⛔ which style pack is this reel in? Name it (layer_probe.py {job} <PACK>, one of: {have}), "
                 f"or save a default pack first.")
    rows = probe(job, pack)

    if "--json" in sys.argv:
        print(json.dumps(rows, indent=1))
        sys.exit(0 if rows else 3)

    if not rows:
        print("  · this reel has no separable layers — there is nothing to tick.")
        sys.exit(3)
    print(f"  Layers available in {job} ({pack}):")
    for e in rows:
        tick = "x" if e["default_on"] else " "
        print(f"    [{tick}] {e['group']:<9} {e['blurb']:<42} "
              f"{e['clips']:>3} clip(s), {e['start']:.1f}s–{e['end']:.1f}s")
    print("\n  [x] = suggested default. Each ticked layer is one render, plus one more for the rest when anything "
          "is left unticked.")
    sys.exit(0)


if __name__ == "__main__":
    main()
