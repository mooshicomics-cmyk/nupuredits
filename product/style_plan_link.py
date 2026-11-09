#!/usr/bin/env python3
"""Emit / verify the rough-cut preview LINK for the style-plan review — the hardened way.

Kills the recurring "Couldn't load this preview / file may have been deleted or moved" failure. That bug
has ONE cause: the markdown video link must be RELATIVE TO THE ENGINE ROOT (the session's working dir),
e.g. `projects/<job>/outputs/<job>.mp4`. If it is prefixed with the engine folder name
(`ai-edit-engine/projects/...`) the app resolves it from INSIDE that folder and doubles it to
`.../ai-edit-engine/ai-edit-engine/projects/...`, which does not exist, so the preview fails.

Rather than trust anyone to type the path right, this tool computes it, VERIFIES the file exists, probes
the duration, and prints the exact markdown to paste. It REFUSES (nonzero exit) to emit a link to a
missing or wrongly-prefixed path, so a broken preview link can never go out. `--check` validates a link
you already wrote.

Usage:
  python product/style_plan_link.py <job>                # emit verified link for projects/<job>/outputs/<job>.mp4
  python product/style_plan_link.py <job> --file PATH    # emit for a specific mp4 (relative to engine root)
  python product/style_plan_link.py --check "HREF"       # validate an href; exit 1 if it would fail the preview
"""
import sys, os, subprocess, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # engine root = parent of product/
ENGINE = os.path.basename(ROOT)                                     # e.g. "ai-edit-engine"

def fmt(sec):
    m = int(sec // 60); s = int(round(sec % 60)); return f"{m}:{s:02d}"

def verify(href):
    """Return (rel_path, abs_path, [problems]). Empty problems == safe to paste."""
    raw = str(href).replace("\\", "/").strip()
    problems = []
    if raw.startswith(ENGINE + "/") or raw.startswith("/" + ENGINE + "/"):
        problems.append(f"href starts with '{ENGINE}/' — the session already runs from inside "
                        f"{ENGINE}, so this doubles the path; drop the prefix and use 'projects/...'")
    ap = os.path.abspath(raw) if os.path.isabs(raw) else os.path.abspath(os.path.join(ROOT, raw.lstrip("./")))
    try:
        rp = os.path.relpath(ap, ROOT).replace("\\", "/")
    except ValueError:
        rp = raw
    if rp.startswith("../"):
        problems.append("path escapes the engine root; the link must live under the engine folder")
    if not os.path.isfile(ap):
        problems.append(f"file not found at {ap}")
    return rp, ap, problems

def emit(job, file=None):
    rel = file or f"projects/{job}/outputs/{job}.mp4"
    rp, ap, problems = verify(rel)
    if problems:
        sys.stderr.write("REFUSED to emit preview link:\n  - " + "\n  - ".join(problems) + "\n")
        sys.exit(2)
    link = f"▶ [{os.path.basename(rp)}]({rp})"
    dur = duration(ap)
    # em dash is fine here: this is the chat review line, not creator-facing on-screen copy
    return f"{link} — {fmt(dur)}" if dur is not None else link

def duration(path):
    """Seconds, or None. The length is a nicety on the link: no ffprobe, or an mp4 it cannot read, still gets
    her the link (the file itself was existence-checked above), just without the length."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        return float(out.stdout.strip())
    except FileNotFoundError:
        try:
            sys.path.insert(0, os.path.join(ROOT, "product"))
            from fallbacks import note
            note("style-plan-link", "ffprobe is not installed; gave the preview link without its length")
        except Exception:
            pass
        return None
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("job", nargs="?")
    p.add_argument("--file")
    p.add_argument("--check")
    a = p.parse_args()
    if a.check:
        rp, ap, problems = verify(a.check)
        if problems:
            sys.stderr.write("LINK WOULD FAIL THE PREVIEW:\n  - " + "\n  - ".join(problems)
                             + f"\n  use href: {rp}\n"); sys.exit(1)
        print(f"OK (resolves + exists): {rp}"); sys.exit(0)
    if not a.job and not a.file:
        p.error("give a <job>, or --file PATH, or --check HREF")
    job = a.job or os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(a.file))))
    print(emit(job, a.file))
