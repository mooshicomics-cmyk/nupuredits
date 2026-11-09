#!/usr/bin/env python3
"""reel_recipe.py — "turn this into a prompt I can reuse": hand back the recipe behind a finished reel.

When she nails a reel she wants the next one built the same way without re-explaining it. This reads the
decisions the job actually RECORDED (its plan, its shot plan, what was exported, her default pack) and writes
them as one paste-ready prompt, with the parts that belong to the NEXT reel (topic, the tension the hook
names) left as [brackets]. Nothing is guessed: a line only appears when a file backs it.

It deliberately does NOT copy:
  * the hook copy (a hook is measured per reel and never reused; the recipe keeps the hook's SHAPE),
  * timestamps, placement numbers or exact text (they belong to that footage),
  * her saved preferences (`/learn`, favorites): those already apply to every build on their own.

  python3 product/reel_recipe.py <job>          # print the prompt and save projects/<job>/reuse-prompt.md
  python3 product/reel_recipe.py <job> --print  # print only, write nothing

Read-only on everything but that one .md. Stdlib only.
"""
import argparse, json, os, sys

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _capcut_versions(job):
    """CapCut drafts built for this job (named after it). Empty when CapCut isn't on this machine."""
    try:
        import draft_safety as ds
        key = job.lower().replace("-", " ")
        return [n for n in ds._drafts() if key in n.lower().replace("-", " ")]
    except Exception:
        return []


def _default_pack():
    import user_style
    path = os.path.join(ROOT, "product", "creative-vault", "user-style.json")
    st = _json(path) or {}
    return st.get("pack") or user_style.default_pack(path) or st.get("style_pack")


def facts(job):
    """Every decision this job recorded, as plain values. Missing files simply contribute nothing."""
    jd = os.path.join(ROOT, "projects", job)
    if not os.path.isdir(jd):
        raise SystemExit(f"There is no job called \"{job}\" in projects/. Which reel did you mean?")
    plan = _json(os.path.join(jd, "caption-plan.json")) or {}
    shots = _json(os.path.join(jd, "shot-plan.json"))
    out = os.path.join(jd, "outputs")
    rendered = os.path.isfile(os.path.join(out, f"{job}.final.mp4"))
    vo = shots is not None or os.path.isfile(os.path.join(out, f"{job}.vo.mp4"))
    capcut = _capcut_versions(job)

    # the pack a rendered build used is in its build folder's name (hf-reel-type-<pack>); one folder = one answer
    built = sorted(n[len("hf-reel-type-"):] for n in os.listdir(jd) if n.startswith("hf-reel-type-"))
    pack = plan.get("pack") or (built[0].capitalize() if len(built) == 1 else None) or _default_pack()
    f = {"job": job, "format": "voiceover" if vo else "talking", "register": plan.get("register"),
         "pack": pack, "rendered": rendered, "capcut": bool(capcut),
         "seconds": plan.get("duration")}
    em = plan.get("hook_emphasis")
    if plan.get("hook") or plan.get("hook_long") or em:
        f["hook_shape"] = ("a small line over a big one" if em == "second" else
                           "a big line over a small one" if em == "first" else "a single line")
        f["hook_hold"] = "the whole reel" if plan.get("hook_persist") else (
            f"about {round(plan['hook_end'])} seconds" if plan.get("hook_end") else None)
    mode = plan.get("caption_mode") or ("single" if plan else None)   # the builder's own default
    f["captions"] = {"build": "building word by word as I say them", "single": "one word at a time"}.get(mode)
    f["takeovers"] = len(plan.get("takeover_keys") or [])
    f["karaoke_lines"] = sum(1 for t in plan.get("caption_treatments") or [] if t.get("mode") == "build")
    f["keywords"] = bool(plan.get("keywords"))
    kinds = [e.get("kind") for e in plan.get("elements") or [] if isinstance(e, dict)]
    f["counters"] = kinds.count("counter")
    f["breakaways"] = len(plan.get("breakaways") or [])
    f["vibe"] = bool(plan.get("vibe"))
    punch = plan.get("punch") or {}
    f["punches"] = len(punch.get("windows") or []) if isinstance(punch, dict) else 0
    sfx = plan.get("sfx") or []
    secs = plan.get("duration") or 0
    if sfx and secs:
        per10 = len(sfx) / secs * 10
        f["sfx"] = "light" if per10 <= 1 else "busy" if per10 > 3 else "moderate"
    elif "sfx" in plan:
        f["sfx"] = "none"
    f["music"] = bool(plan.get("music"))
    if vo and isinstance(shots, dict):
        f["shots"] = len(shots.get("shots") or shots.get("plan") or [])
    return f


def prompt(f):
    L = [f"Build my next reel the same way as \"{f['job']}\". Here is the recipe, so you don't have to ask:", ""]
    L.append("WHAT IT IS")
    L.append("- Format: " + ("a voiceover reel over my b-roll" if f["format"] == "voiceover" else "me talking to camera"))
    if f.get("register"):
        L.append(f"- Type: {f['register']}")
    L.append("- Topic: [what this one is about]")
    if f["format"] == "voiceover":
        L.append("- The feeling: [punchy / emotional]")
    if f.get("seconds"):
        lo = max(15, int(f["seconds"] // 15 * 15)); L.append(f"- Length: around {lo // 60}:{lo % 60:02d} to "
                                                              f"{(lo + 15) // 60}:{(lo + 15) % 60:02d}")
    L += ["", "HOW FINISHED"]
    if f["rendered"] and f["capcut"]:
        L.append("- Doneness: well-done, in CapCut too")
    elif f["rendered"]:
        L.append("- Doneness: well-done, just the finished video")
    elif f["capcut"]:
        L.append("- Doneness: [raw / medium], in CapCut")
    else:
        L.append("- Doneness: [raw / medium / well-done / hands-off]")
    if f.get("pack"):
        L.append(f"- Look: my {f['pack']} pack")
    if f.get("hook_shape"):
        L += ["", "THE HOOK"]
        L.append(f"- Shape: {f['hook_shape']}" + (f", on screen for {f['hook_hold']}" if f.get("hook_hold") else ""))
        L.append("- It names: [the tension or promise in this reel, in one line]. Never my first sentence.")
    on = []
    if f.get("captions"):
        on.append(f"- Captions {f['captions']}" + (", with key words highlighted" if f.get("keywords") else ""))
    if f.get("takeovers"):
        on.append(f"- About {f['takeovers']} full-screen word moment{'s' if f['takeovers'] != 1 else ''} on the lines that matter most")
    if f.get("karaoke_lines"):
        on.append(f"- About {f['karaoke_lines']} line{'s' if f['karaoke_lines'] != 1 else ''} lighting up word by word")
    if f.get("counters"):
        on.append("- Numbers I say pop on as a card that counts up")
    if f.get("breakaways"):
        on.append("- One breakaway card for the big line")
    if f.get("vibe"):
        on.append("- One small personal touch where it earns it")
    if f.get("punches"):
        on.append("- Punch-in zooms on the lines that land")
    if on:
        L += ["", "ON SCREEN"] + on
    snd = []
    if f.get("sfx") == "none":
        snd.append("- No sound effects")
    elif f.get("sfx"):
        snd.append(f"- Sound effects: {f['sfx']}, each one matched to the motion it goes with")
    if f.get("music") is not None and ("sfx" in f or f.get("music")):
        snd.append("- A soft music bed under my voice" if f["music"] else "- No music bed")
    if snd:
        L += ["", "SOUND"] + snd
    L += ["", ("Show me the shot plan once, line by line, then build it all in one pass." if f["format"] == "voiceover"
               else "Show me the rough cut to trim, then the plan once, then build it all in one pass.")]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("job")
    ap.add_argument("--print", action="store_true", help="print only, write nothing")
    a = ap.parse_args()
    text = prompt(facts(a.job))
    print(text)
    if not a.print:
        dest = os.path.join(ROOT, "projects", a.job, "reuse-prompt.md")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(f"# Reuse prompt for \"{a.job}\"\n\nCopy everything below into the chat for your next reel.\n\n"
                     f"```\n{text}\n```\n")
        print(f"\nSaved to projects/{a.job}/reuse-prompt.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
