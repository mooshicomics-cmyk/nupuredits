#!/usr/bin/env python3
"""Fail-safe: text must render CORRECTLY in every style pack. Run before every ship.

This does not inspect config and hope. It BUILDS a real composition for each pack, in each hook mode,
against a synthetic job, then parses the emitted HTML and checks what would actually appear on screen.

The failures it exists to catch are all SILENT — the build succeeds, the reel renders, and it is only
wrong when a human looks at it on a phone:

  * text too small to read. Sizes are COMPUTED (fitted to a band, scaled off an anchor, shrunk to fit a
    width), so one can collapse without erroring. Measured: captions rendered at 43px instead of the pack's
    own 61px because they were anchored to a hook that had shrunk. The engine's floor was `max(20, ...)`,
    far below readable, so nothing caught it.
  * text under the platform's own UI. A persistent label shipped sitting beneath Instagram's Reels header.
    Invisible in the render, invisible in QuickTime; visible only in the app, after posting.
  * text in the wrong font. The paid faces live in CapCut and do NOT ship as files, so a missing face used
    to fall through to a browser default.

Self-contained: builds its own job in a temp dir, so it works from a fresh buyer unzip where projects/
does not exist.

Run: python3 product/tests/test_text_renders.py
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
import stylepack, safe_zones as SZ

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def make_job(tmp, plan):
    """A minimal job: a word-timed transcript and a caption plan. Enough to drive a real build."""
    job = os.path.join(tmp, "projects", "qa-job")
    os.makedirs(os.path.join(job, "outputs"), exist_ok=True)
    words, t = [], 0.30
    for w in ("this", "is", "a", "line", "of", "caption", "text", "for", "the", "render", "check", "here"):
        words.append({"text": w, "start": round(t, 2), "end": round(t + 0.28, 2)})
        t += 0.36
    json.dump({"words": words}, open(os.path.join(job, "outputs", "qa-job.transcript.json"), "w", encoding="utf-8"))
    json.dump(plan, open(os.path.join(job, "caption-plan.json"), "w", encoding="utf-8"))
    return job


def build(tmp, pack, plan, split=False):
    """Run the real builder and return the emitted HTML."""
    make_job(tmp, plan)
    env = {**os.environ, "JOB": "qa-job", "STYLE_PACK": pack}
    if split:
        env["HOOK_SPLIT"] = "1"
    # the builder resolves paths from its own location, so run it against a repo whose projects/ is ours
    link = os.path.join(tmp, "product")
    if not os.path.exists(link):
        os.symlink(PRODUCT, link)
    for extra in ("assets", ".claude"):
        tgt = os.path.join(tmp, extra)
        if not os.path.exists(tgt) and os.path.exists(os.path.join(ROOT, extra)):
            os.symlink(os.path.join(ROOT, extra), tgt)
    r = subprocess.run([sys.executable, os.path.join(tmp, "product", "build-reel-type.py")],
                       capture_output=True, text=True, env=env, cwd=tmp)
    out = os.path.join(tmp, "projects", "qa-job", f"hf-reel-type-{pack.lower()}", "index.html")
    if not os.path.exists(out):
        return None, (r.stdout + r.stderr)[-400:]
    return open(out, encoding="utf-8").read(), (r.stdout + r.stderr)


def sizes(html, selector):
    """Every font-size that a given class actually renders at."""
    out = []
    for m in re.finditer(re.escape(selector) + r"\{[^}]*?font-size:(\d+)px", html):
        out.append(int(m.group(1)))
    for m in re.finditer(r'class="' + selector.lstrip(".") + r'"[^>]*font-size:(\d+)px', html):
        out.append(int(m.group(1)))
    return out


def main():
    print("text renders correctly in every pack\n")
    packs = [p for p in stylepack.names() if stylepack.load(p).get("in_launch_kit")]
    base_plan = {
        "duration": 6.0, "caption_mode": "single",
        "hook": ["a short hook line"], "hook_end": 3.0,
    }
    persist_plan = {
        "duration": 6.0, "caption_mode": "single",
        "hook": [], "hook_long": "for the person who feels like they do not fit",
        "hook_halves": ["for the person who", "feels like they do not fit"],
        "hook_persist": True, "hook_end": 0.0,
    }

    for pack in packs:
        for label, plan, split in (("hook card", base_plan, False), ("persistent hook", persist_plan, True)):
            tmp = tempfile.mkdtemp()
            try:
                html, log = build(tmp, pack, plan, split)
                if html is None:
                    check(f"{pack} / {label}: builds", False, log)
                    continue
                check(f"{pack} / {label}: builds", True)

                # 1. every caption is legible
                caps = sizes(html, ".capword")
                if caps:
                    check(f"{pack} / {label}: captions >= {SZ.MIN_PX['caption']}px",
                          min(caps) >= SZ.MIN_PX["caption"], f"smallest {min(caps)}px")

                # 2. hook / headline is legible
                heads = sizes(html, ".hkhead") + sizes(html, ".hkline")
                if heads:
                    check(f"{pack} / {label}: headline >= {SZ.MIN_PX['headline']}px",
                          min(heads) >= SZ.MIN_PX["headline"], f"smallest {min(heads)}px")

                # 3. nothing renders in a browser default — every family is a real loaded face
                fams = set(re.findall(r"font-family:([A-Za-z0-9_-]+)", html))
                declared = set(re.findall(r"@font-face\{font-family:'([^']+)'", html))
                unloaded = {f for f in fams if f not in declared and f not in ("inherit",)}
                check(f"{pack} / {label}: every font is a real loaded face",
                      not unloaded, f"not declared: {sorted(unloaded)}")

                # 4. the font FILES the pack asked for were actually copied next to the composition
                fdir = os.path.join(tmp, "projects", "qa-job", f"hf-reel-type-{pack.lower()}", "fonts")
                got = set(os.listdir(fdir)) if os.path.isdir(fdir) else set()
                check(f"{pack} / {label}: font files present beside the composition", len(got) > 0)

                # 5. top-anchored text clears the platform UI band
                tops = [int(m) for m in re.findall(r"#hook(?:split|wrap|arc)\{[^}]*?top:(\d+)px", html)]
                if tops:
                    check(f"{pack} / {label}: hook clears the {SZ.TOP}px platform band",
                          min(tops) >= SZ.TOP, f"top at {min(tops)}px")

                # 6. captions sit inside the safe box
                ctops = [int(m) for m in re.findall(r'class="capword"[^>]*top:(\d+)px', html)]
                if ctops:
                    check(f"{pack} / {label}: captions inside the safe box",
                          min(ctops) >= SZ.TOP and max(ctops) <= SZ.BOTTOM,
                          f"range {min(ctops)}-{max(ctops)}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED: {len(fails)}")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
