#!/usr/bin/env python3
"""sandbox.py — render ONE moment of the reel, in motion, without rendering the reel.

  python3 .claude/skills/beat-sheet/scripts/sandbox.py <job> --beat 3            # beat 3 from the beat sheet
  python3 .claude/skills/beat-sheet/scripts/sandbox.py <job> --from 71.5 --to 75  # any stretch, in seconds

Reads the same projects/<job>/beat-sheet/beats.json the beat sheet uses (base cut, layers, beats). Every built
layer is cut down to the stretch (render_spans.span_html: the page time-shifted so it starts there, the same
mechanism the caption renderer uses), rendered on its own, and stacked over that slice of her rough cut with
her audio. A layer that cannot be cut with certainty is rendered whole and trimmed. Writes
projects/<job>/beat-sheet/sandbox/beat-NN-vK.mp4 (K counts up, so every try is kept) and prints its link.

It is a preview: it skips the render gate the final render runs, and the final render is never touched.
Nothing to render on the raw route (CapCut animates that text), and it says so.

Never a dead end: a layer that will not render (cut down, then whole, once each) or has no index.html is left out
of the clip in one line and the rest are stacked. With no Node on this computer, or no layer rendering at all,
it hands back the beat's still from the beat sheet instead. Each switch is one line in _local/fallbacks.log.
"""
import argparse, json, os, re, shutil, signal, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "product"))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import render_spans as RS
from npx_run import npx_argv, npx_path, hf_version, NO_NODE
import render_lock   # one HyperFrames render at a time on this computer (product/render_lock.py)
try:
    from fallbacks import note
except Exception:   # the helper missing must not cost her the preview
    def note(step, message): pass

PAD = 1.5          # seconds either side of a beat's moment
MAX_GROW = 8.0     # a stretch may widen this far to take in a clip it would cut in half; beyond that, render whole
# A render is only stopped when it has gone completely quiet: no new output (the renderer prints every frame it
# streams) and no growth in the file it writes, for this long. A render still counting frames is never stopped,
# however long it takes. REELS_ENGINE_SANDBOX_STALL_S=0 turns the watch off.
STALL = float(os.environ.get("REELS_ENGINE_SANDBOX_STALL_S", "") or 900)


def clock(t):
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:04.1f}"


def layer_window(comp, a, b):
    """(span_dir_or_None, start, end) in the layer's own time. Widens [a, b] until no clip straddles an edge,
    so every word and card in it plays whole. None = render the composition whole."""
    html = open(os.path.join(comp, "index.html"), encoding="utf-8").read()
    rc = RS.read_clips(html)
    if rc is None:
        return None, 0.0, None
    dur, clips = rc
    a, b = max(0.0, a), min(dur, b)
    if b <= a:
        return "skip", a, b
    import math
    lo, hi = a, b
    for _ in range(40):
        # in whole frames, the way span_html cuts: start rounded down, end rounded up
        lo = math.floor(lo * RS.FPS + 1e-6) / RS.FPS
        hi = RS.frames_for(hi) / RS.FPS
        moved = False
        for s, d in clips:
            e = s + d
            if s < lo - 1e-6 < e - 2e-6:
                lo, moved = s, True
            if s + 2e-6 < hi + 1e-6 < e:
                hi, moved = e, True
        if not moved:
            break
    if a - lo > MAX_GROW or hi - b > MAX_GROW:
        return None, 0.0, None
    first, end = int(round(lo * RS.FPS)), int(round(hi * RS.FPS))
    if end <= first:
        return "skip", a, b
    return (first, end), first / RS.FPS, end / RS.FPS


def _stop(p):
    """Stop a render and everything it started (npx runs node, node runs the browser)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        p.kill()
    p.wait()


def render(comp_dir, out):
    # The moving preview is a real render, so it waits its turn behind any other render on this computer
    # (render_lock: a second render waits, never stops the first). The stall watch starts once it is ours.
    with render_lock.held("beat-sheet sandbox"):
        _render(comp_dir, out)


def _render(comp_dir, out):
    # Output goes to a file, not a pipe: a pipe nobody reads fills up and freezes the render, and the file's
    # size is how the stall watch below sees the render is still working.
    log_path = out + ".log"
    with open(log_path, "w+", encoding="utf-8", errors="replace") as log:
        try:
            p = subprocess.Popen(npx_argv("--yes", f"hyperframes@{hf_version()}", "render", comp_dir,
                                          "--format", "mov", "--output", out),
                                 stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 start_new_session=(os.name != "nt"))
        except OSError as e:
            raise RuntimeError(f"npx would not start: {e}")
        seen, quiet_since = None, time.monotonic()
        try:
            while p.poll() is None:
                time.sleep(2)
                now = (os.path.getsize(log_path), os.path.getsize(out) if os.path.exists(out) else -1)
                if now != seen:
                    seen, quiet_since = now, time.monotonic()
                elif STALL > 0 and time.monotonic() - quiet_since > STALL:
                    _stop(p)
                    raise RuntimeError(f"the render went quiet for {int(STALL // 60)} minutes and was stopped")
        except KeyboardInterrupt:
            _stop(p)   # her Ctrl-C stops the render too, then stops the sandbox
            raise
        log.seek(0)
        text = log.read()
    if p.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(text.strip()[-400:] or f"the render exited {p.returncode}")


def still_instead(job_dir, beats, w0, w1, beat, why, log_line):
    """The beat sheet's still for the beat she named (or every beat in the stretch she named), when nothing can
    move. Returns False when the beat sheet has no still for it."""
    hits = [b for b in beats if b["n"] == beat] if beat is not None else [b for b in beats if w0 <= float(b["t"]) <= w1]
    stills = [os.path.join(job_dir, "beat-sheet", "beats", f"{b['n']:02d}.jpg") for b in hits]
    stills = [p for p in stills if os.path.exists(p)]
    if not stills:
        return False
    note("sandbox", log_line)
    print(f"No moving preview this time: {why}. Here is the still from the beat sheet instead; the full render "
          f"shows the motion.")
    for p in stills:
        print(f"▶ [{os.path.basename(p)}]({os.path.relpath(p, ROOT).replace(os.sep, '/')})")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job")
    ap.add_argument("--beat", type=int)
    ap.add_argument("--from", dest="t0", type=float)
    ap.add_argument("--to", dest="t1", type=float)
    a = ap.parse_args()

    job_dir = os.path.join(ROOT, "projects", a.job)
    spec_path = os.path.join(job_dir, "beat-sheet", "beats.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"No {os.path.relpath(spec_path, ROOT)}. The sandbox reads the beat sheet's file; make the "
                         f"beat sheet first.")
    spec = json.load(open(spec_path, encoding="utf-8"))
    beats = sorted(spec.get("beats") or [], key=lambda b: float(b["t"]))
    for i, b in enumerate(beats, 1):
        b.setdefault("n", i)
    if a.beat is not None:
        hit = [b for b in beats if b["n"] == a.beat]
        if not hit:
            raise SystemExit(f"There is no beat {a.beat} on this beat sheet (it has {len(beats)}).")
        w0, w1 = float(hit[0]["t"]) - PAD, float(hit[0]["t"]) + PAD
        tag = f"beat-{a.beat:02d}"
    elif a.t0 is not None and a.t1 is not None and a.t1 > a.t0:
        w0, w1 = a.t0, a.t1
        tag = f"at-{int(a.t0)}s"
    else:
        raise SystemExit("Say which moment: --beat N, or --from <seconds> --to <seconds>.")
    w0 = max(0.0, w0)

    layers = spec.get("layers") or []
    if not layers:
        raise SystemExit("Nothing to sandbox on this reel: its text is CapCut's own (the raw route), so CapCut "
                         "animates it. Open the draft in CapCut to see it move.")
    if not npx_path():
        if still_instead(job_dir, beats, w0, w1, a.beat, "Node, which renders the graphics, is not on this computer",
                         "Node (npx) is missing; handed back the beat sheet's still instead of a moving preview"):
            return
        raise SystemExit(NO_NODE)
    base = os.path.join(ROOT, spec.get("base") or os.path.join("projects", a.job, "outputs", f"{a.job}.mp4"))
    if not os.path.exists(base):
        raise SystemExit(f"No rough cut at {os.path.relpath(base, ROOT)}.")

    out_dir = os.path.join(job_dir, "beat-sheet", "sandbox")
    os.makedirs(out_dir, exist_ok=True)
    k = 1
    while os.path.exists(os.path.join(out_dir, f"{tag}-v{k}.mp4")):
        k += 1
    out = os.path.join(out_dir, f"{tag}-v{k}.mp4")

    overlays = []   # (mov, reel_start)
    dropped = 0     # layers left out because they would not render
    with tempfile.TemporaryDirectory() as tmp:
        for i, lay in enumerate(layers):
            comp = os.path.join(job_dir, lay["dir"])
            off = float(lay.get("offset", 0))
            try:
                how, lo, hi = layer_window(comp, w0 - off, w1 - off)
            except OSError:
                print(f"  ⚠ {lay['dir']} has no index.html, so it is left out of this clip")
                note("sandbox", f"{lay['dir']} has no index.html; stacked the clip without that layer")
                dropped += 1
                continue
            if how == "skip":
                continue
            mov = os.path.join(tmp, f"layer-{i}.mov")
            try:
                if how is None:
                    render(comp, mov)
                    overlays.append((mov, off))
                    continue
                span = RS.span_comp(comp, os.path.join(tmp, f"span-{i}"), how[0], how[1])
                render(span, mov)
                overlays.append((mov, off + lo))
                continue
            except (RuntimeError, ValueError) as e:
                if how is not None:
                    # The cut-down copy failed; the whole layer is the one other try.
                    print(f"  ⚠ {lay['dir']} could not be cut to this moment ({str(e)[:160]}); rendering it whole")
                    try:
                        if os.path.exists(mov):
                            os.remove(mov)   # never stack a half-written file from the failed try
                        render(comp, mov)
                        overlays.append((mov, off))
                        continue
                    except (RuntimeError, ValueError) as e2:
                        e = e2
                print(f"  ⚠ {lay['dir']} would not render ({str(e)[:160]}), so it is left out of this clip")
                note("sandbox", f"{lay['dir']} would not render ({str(e)[:160]}); stacked the clip without that layer")
                dropped += 1

        if dropped and not overlays:
            if still_instead(job_dir, beats, w0, w1, a.beat, "none of this moment's graphics layers would render",
                             "no layer would render for this moment; handed back the beat sheet's still instead"):
                return

        dur = w1 - w0
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{w0:.3f}", "-t", f"{dur:.3f}", "-i", base]
        for mov, start in overlays:
            if start >= w0:
                cmd += ["-itsoffset", f"{start - w0:.3f}", "-i", mov]
            else:
                cmd += ["-ss", f"{w0 - start:.3f}", "-i", mov]
        chain = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v0]"
        for j in range(1, len(overlays) + 1):
            chain += f";[v{j-1}][{j}:v]overlay=0:0:eof_action=pass[v{j}]"
        cmd += ["-filter_complex", chain, "-map", f"[v{len(overlays)}]", "-map", "0:a?", "-t", f"{dur:.3f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"Could not stack the sandbox clip: {r.stderr.strip()[-300:]}")

    print(f"✓ sandbox: {clock(w0)} to {clock(w1)} ({dur:.1f}s), {len(overlays)} layer(s) rendered for just this moment")
    print(f"▶ [{os.path.basename(out)}]({os.path.relpath(out, ROOT).replace(os.sep, '/')})")


if __name__ == "__main__":
    main()
