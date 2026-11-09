#!/usr/bin/env python3
"""beat-sheet.py — the beat sheet: every key moment of a reel as a still, numbered, with a legend stamped
on each, BEFORE any motion is rendered. She marks it up by beat number ("beat 12, make that bigger");
Claude fixes only the beats she names and runs this again with --only.

  python3 .claude/skills/beat-sheet/scripts/beat-sheet.py <job>                 # every beat
  python3 .claude/skills/beat-sheet/scripts/beat-sheet.py <job> --only 3,7      # re-stamp just these
  python3 .claude/skills/beat-sheet/scripts/beat-sheet.py --which                # ask / always / skip

Reads projects/<job>/beat-sheet/beats.json (Claude writes it from the approved creative plan; the shape is
in the beat-sheet skill). For each beat:
  1. the frame of her rough cut at that moment (ffmpeg),
  2. every built HyperFrames layer at that moment, as a transparent still (`hyperframes snapshot --at`, a
     few seconds per layer, never a render), stacked on the frame in layer order,
  3. or, on the raw route where nothing is rendered, a mock of the CapCut text in her pack's fonts,
  4. a numbered badge on the frame and a legend under it: beat, time, what it is, the words, the motion.
Writes projects/<job>/beat-sheet/beat-sheet.html (the beat sheet she reviews, a director's cut for the app's side
browser), beats/NN.jpg (each beat full size), beat-sheet.md (the same beats as a table) and beat-sheet.jpg (a
single-image fallback for when there is no side browser). Prints the page path under projects/ and the fallback.

Never a dead end: beat-sheet.md is written first, straight from beats.json. A layer whose stills cannot be taken
(no Node on this computer, a snapshot that hangs) leaves that layer off the stills and says so in one line. If the
stills cannot be made at all (no Pillow, or anything breaking after the beats are read), it prints a line starting
"TEXT BEAT SHEET" and the beat-sheet.md path, and her review goes ahead on that table. Each switch is one line in
_local/fallbacks.log (product/fallbacks.py).
"""
import argparse, base64, html, io, json, os, pathlib, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "product"))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    Image = None   # no stills without Pillow; main() gives her the text beat sheet instead

try:
    from fallbacks import note, remember, remembered, forget
except Exception:   # the helper missing must not cost her the review
    def note(step, message): pass
    def remember(key, value=True, why=""): pass
    def remembered(key, default=None): return default
    def forget(key): pass

NO_NODE_KEY = "beat-sheet.no-node"
SNAPSHOT_TIMEOUT = 300   # seconds; a snapshot takes a few, so this only catches one that has hung

W, H = 1080, 1920
LEGEND_PAD = 44
BADGE = "#e8442e"          # the beat number; loud on purpose, it is a proofing mark, not part of the design
INK, PAPER, MUTED = "#141414", "#ffffff", "#b9b4ab"
BODY_FONT = os.path.join(ROOT, "assets", "fonts", "Inter-Medium.ttf")
BOLD_FONT = os.path.join(ROOT, "assets", "fonts", "Inter-Bold.otf")
# Bundled faces to fall back on when a named font file is missing or will not open, before Pillow's own tiny
# default. Only faces that ship with the engine.
SPARE_FONTS = ["Inter-Bold.otf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Regular.otf", "Inter-VF.ttf",
               "Poppins-Bold.ttf", "Poppins-Regular.ttf", "DMSans-Variable.ttf"]

# Raw-route mocks: where each role sits and how big, when beats.json does not say. CapCut sets the real type.
MOCK_DEFAULTS = {
    "headline":       {"px": 92,  "y": 0.30},
    "takeover":       {"px": 150, "y": 0.50},
    "caption":        {"px": 56,  "y": 0.70},
    "accent_caption": {"px": 62,  "y": 0.70},
    "thought_bubble": {"px": 60,  "y": 0.40},
}


def font(path, px):
    for p in [path] + [os.path.join(ROOT, "assets", "fonts", f) for f in SPARE_FONTS]:
        try:
            return ImageFont.truetype(p, px)
        except (OSError, TypeError, ValueError):
            continue
    try:
        return ImageFont.load_default(size=px)   # Pillow 10.1+: a scalable default
    except TypeError:
        return ImageFont.load_default()          # older Pillow: a small bitmap face with no .size


def size_of(fnt, px=40):
    """A font's pixel size. Old Pillow's bitmap default has no .size, so fall back to the size asked for."""
    return getattr(fnt, "size", None) or px


def clock(t):
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:04.1f}"


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in str(text).split():
        trial = (line + " " + word).strip()
        if line and draw.textlength(trial, font=fnt) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines or [""]


def cover(im):
    """Fit any frame to 1080x1920 the way the reel shows it: fill, centre crop."""
    im = im.convert("RGBA")
    scale = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


_NO_FFMPEG = []   # said once per sheet, not once per beat


def base_frame(video, t, tmp):
    out = os.path.join(tmp, f"base-{t:.3f}.png")
    try:
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video,
                            "-frames:v", "1", out], capture_output=True, text=True, timeout=120)
        why = r.stderr.strip()[:120] if r.returncode != 0 or not os.path.exists(out) else None
    except FileNotFoundError:
        if not _NO_FFMPEG:
            _NO_FFMPEG.append(1)
            print("  ffmpeg is not on this computer, so the beats show on black; the design and legends are all there")
            note("beat-sheet", "ffmpeg is not installed; drew every beat on a black frame instead of her footage")
        return Image.new("RGBA", (W, H), "#000000")
    except subprocess.TimeoutExpired:
        why = "ffmpeg took over two minutes on one frame"
    if why is None:
        try:
            return cover(Image.open(out))
        except Exception as e:
            why = f"the frame would not open: {e}"
    print(f"  ⚠ no footage frame at {clock(t)} ({why}); the beat shows on black")
    return Image.new("RGBA", (W, H), "#000000")


def layer_duration(comp_dir):
    try:
        html = open(os.path.join(comp_dir, "index.html"), encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r'data-duration="([\d.]+)"', html)
    return float(m.group(1)) if m else None


_NODE = {}   # asked once per sheet


def node_ready():
    """True when npx is here to take stills of the HyperFrames layers. Without it the sheet still comes out:
    her footage, every mock, the numbers and legends, minus the graphics layers. This computer is remembered
    (beat-sheet.no-node) so the report shows it, and forgotten the moment Node turns up."""
    if "ok" not in _NODE:
        from npx_run import npx_path
        _NODE["ok"] = bool(npx_path())
        if _NODE["ok"]:
            forget(NO_NODE_KEY)
        else:
            print("  The graphics layers are not on these stills: Node, which takes stills of them, is not on this "
                  "computer (or this terminal opened before it was installed). Her footage, the beat numbers and "
                  "the legends are all there, and the render itself needs Node, so ./check-setup.sh is the fix.")
            if not remembered(NO_NODE_KEY):
                note("beat-sheet", "Node (npx) is missing; made the stills without the graphics layers")
                remember(NO_NODE_KEY, True, why="npx was not found when the beat sheet took its stills")
    return _NODE["ok"]


def snapshot_layer(comp_dir, times, tmp, tag):
    """{time: RGBA image} for one HyperFrames layer, one browser boot for every time asked. {} when the stills
    could not be taken: that layer is left off and the sheet carries on."""
    from npx_run import npx_argv, hf_version
    if not node_ready():
        return {}
    out = os.path.join(tmp, f"snap-{tag}")
    shutil.rmtree(out, ignore_errors=True)
    at = ",".join(f"{t:.3f}" for t in times)
    rel = os.path.relpath(comp_dir, ROOT)
    limit = max(SNAPSHOT_TIMEOUT, 20 * len(times))
    try:
        r = subprocess.run(npx_argv("--yes", f"hyperframes@{hf_version()}", "snapshot", comp_dir, "--at", at,
                                    "--no-end", "--describe", "false", "-o", out),
                           capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        # Not remembered: a hang says something about this layer or this moment, not about the computer.
        print(f"  ⚠ the stills of {rel} took over {limit // 60} minutes; that layer is left off these stills")
        note("beat-sheet", f"the snapshot of {rel} hung; made the stills without that layer")
        return {}
    except FileNotFoundError:
        _NODE["ok"] = False
        print(f"  ⚠ npx would not start for {rel}; that layer is left off these stills")
        note("beat-sheet", f"npx would not start for {rel}; made the stills without that layer")
        return {}
    files = sorted(f for f in os.listdir(out) if f.startswith("frame-") and f.endswith(".png")) if os.path.isdir(out) else []
    # HyperFrames release 0.9.4 exits 1 when a video on screen could not be read, with every still saved. Those stills
    # still show the layer's graphics, so they stay on the sheet and she hears about the video.
    unread_video = "video frame(s) could not be read" in (r.stderr or "") + (r.stdout or "")
    if (r.returncode != 0 and not unread_video) or len(files) != len(times):
        print(f"  ⚠ could not take stills of {os.path.relpath(comp_dir, ROOT)}: "
              f"{(r.stderr or r.stdout).strip()[-300:]}")
        return {}
    if r.returncode != 0:
        print(f"  ⚠ a video in {rel} could not be read, so it shows black or out of date on these stills")
        note("beat-sheet", f"a video in {rel} could not be read; its stills were kept")
    return {t: cover(Image.open(os.path.join(out, f))) for t, f in zip(times, files)}


def draw_mock(frame, items, pack):
    """Raw route: her CapCut text, drawn in her pack's fonts where it will sit. A preview, not the render."""
    try:
        import stylepack
        spec = stylepack.load(pack) if pack else None
    except Exception:
        stylepack, spec = None, None
    accent = (spec or {}).get("accent_color", "#fdc341")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for it in items or []:
        role = it.get("role", "headline")
        dflt = MOCK_DEFAULTS.get(role, MOCK_DEFAULTS["headline"])
        path, case = BOLD_FONT, None
        if spec and stylepack:
            try:
                el = stylepack.element(pack, role)
                path, case = el["file"], el.get("case")
            except Exception:
                pass
        text = str(it.get("text", ""))
        if case == "upper":
            text = text.upper()
        elif case == "lower":
            text = text.lower()
        fnt = font(it.get("font_file") or path, int(it.get("px", dflt["px"])))
        color = accent if it.get("color") == "accent" else it.get("color", "#ffffff")
        lines = wrap(d, text, fnt, 900)
        lh = int(size_of(fnt, int(it.get("px", dflt["px"]))) * 1.08)
        y = int(H * float(it.get("y", dflt["y"]))) - lh * len(lines) // 2
        for ln in lines:
            d.text((W // 2, y), ln, font=fnt, fill=color, anchor="ma")
            y += lh
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), mask=layer.split()[-1])
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    frame.alpha_composite(shadow, (0, 8))
    frame.alpha_composite(layer)
    return frame


def legend_lines(d, beat, label_f, body_f, width):
    head = f"BEAT {beat['n']}   ·   {clock(beat['t'])}   ·   {str(beat.get('kind', '')).upper()}"
    rows = [(head, label_f, PAPER)]
    if beat.get("says"):
        rows += [(ln, body_f, PAPER) for ln in wrap(d, f"“{beat['says']}”", body_f, width)]
    if beat.get("motion"):
        rows += [(ln, body_f, MUTED) for ln in wrap(d, "Motion: " + str(beat["motion"]), body_f, width)]
    return rows


def stamp(frame, beat, legend_h):
    label_f, body_f, badge_f = font(BOLD_FONT, 58), font(BODY_FONT, 50), font(BOLD_FONT, 76)
    out = Image.new("RGB", (W, H + legend_h), INK)
    out.paste(frame.convert("RGB"), (0, 0))
    d = ImageDraw.Draw(out)
    # The badge sits in the top band Instagram keeps for its own UI, so it never hides the design.
    r = 66
    d.ellipse((40, 40, 40 + 2 * r, 40 + 2 * r), fill=BADGE, outline=PAPER, width=5)
    d.text((40 + r, 40 + r), str(beat["n"]), font=badge_f, fill=PAPER, anchor="mm")
    y = H + LEGEND_PAD
    for text, fnt, color in legend_lines(d, beat, label_f, body_f, W - 2 * LEGEND_PAD):
        d.text((LEGEND_PAD, y), text, font=fnt, fill=color)
        y += int(size_of(fnt) * 1.3)
    return out


def legend_height(beats):
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    label_f, body_f = font(BOLD_FONT, 58), font(BODY_FONT, 50)
    tallest = 0
    for b in beats:
        tallest = max(tallest, sum(int(size_of(f) * 1.3) for _, f, _ in legend_lines(d, b, label_f, body_f, W - 2 * LEGEND_PAD)))
    return tallest + 2 * LEGEND_PAD


def contact_sheet(tiles, job, path):
    n = len(tiles)
    cols = n if n <= 4 else 3 if n in (5, 6, 9) else 4   # full rows where possible, never a lone tile on 4
    tw = 360
    th = round(tiles[0].height * tw / tiles[0].width)
    gap, head = 24, 150
    rows = -(-n // cols)
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * gap, head + rows * th + (rows + 1) * gap), "#f3efe7")
    d = ImageDraw.Draw(sheet)
    d.text((gap, 34), f"Beat sheet · {job} · {n} beat{'s' if n != 1 else ''}", font=font(BOLD_FONT, 40), fill=INK)
    d.text((gap, 92), "Nothing is rendered yet. Reply with notes by beat number.", font=font(BODY_FONT, 26), fill="#6b665e")
    for i, tile in enumerate(tiles):
        x = gap + (i % cols) * (tw + gap)
        y = head + gap + (i // cols) * (th + gap)
        sheet.paste(tile.resize((tw, th), Image.LANCZOS), (x, y))
    sheet.save(path, quality=90)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("job", nargs="?")
    ap.add_argument("--only", help="comma-separated beat numbers to re-stamp; the rest are reused")
    ap.add_argument("--which", action="store_true",
                    help="print ask / always / skip: what she chose about being offered the beat sheet")
    a = ap.parse_args()
    if a.which:
        try:
            import learned
            print(learned.get("review.beat_sheet", "ask"))
        except Exception:
            print("ask")
        return
    if not a.job:
        ap.error("name the job: beat-sheet.py <job>")

    job_dir = os.path.join(ROOT, "projects", a.job)
    sheet_dir = os.path.join(job_dir, "beat-sheet")
    spec_path = os.path.join(sheet_dir, "beats.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"No {os.path.relpath(spec_path, ROOT)} yet. Write it from the approved creative plan "
                         f"(the beat-sheet skill has the shape), then run this again.")
    spec = json.load(open(spec_path, encoding="utf-8"))
    beats = sorted(spec.get("beats") or [], key=lambda b: float(b["t"]))
    if not beats:
        raise SystemExit("beats.json has no beats.")
    for i, b in enumerate(beats, 1):
        b.setdefault("n", i)
    base = os.path.join(ROOT, spec.get("base") or os.path.join("projects", a.job, "outputs", f"{a.job}.mp4"))
    if not os.path.exists(base):
        raise SystemExit(f"No rough cut at {os.path.relpath(base, ROOT)}; the beat sheet is drawn on it. "
                         f"Set \"base\" in beats.json to the cut this reel is built on.")

    # Every route passes here before anything renders: the one place to say her hook or card copy is in the wrong
    # language while it is still a plan. A warning line, never a stop.
    try:
        import plan_language
        plan_language.warn(job_dir)
    except Exception:
        pass

    # The text beat sheet first, straight from beats.json: whatever happens to the stills after this, her review
    # still has something to go on.
    md_path = write_md(sheet_dir, beats, a.job)
    if Image is None:
        return text_fallback(md_path, "Pillow, the image kit the stills are drawn with, is not installed here",
                             "Pillow is not installed; gave her the text beat sheet instead of the stills")
    try:
        sheet, html_path, done = make_stills(a, job_dir, sheet_dir, spec, beats, base)
    except SystemExit:
        raise   # a stop it means (a beat never stamped under --only), said in its own words
    except Exception as e:
        return text_fallback(md_path, f"the stills broke ({type(e).__name__}: {str(e)[:120]})",
                             f"the stills broke ({type(e).__name__}: {str(e)[:160]}); gave her the text beat sheet instead")

    print(f"✓ beat sheet: {done}, {len(beats)} on the sheet")
    print(f"page (the beat sheet; open it in the side browser): {os.path.relpath(html_path, os.path.join(ROOT, 'projects')).replace(os.sep, '/')}")
    if sheet:
        print(f"fallback image, only when there is no side browser: {os.path.relpath(sheet, ROOT).replace(os.sep, '/')}")


def make_stills(a, job_dir, sheet_dir, spec, beats, base):
    only = {int(x) for x in a.only.split(",")} if a.only else None
    todo = [b for b in beats if only is None or b["n"] in only]
    beats_dir = os.path.join(sheet_dir, "beats")
    os.makedirs(beats_dir, exist_ok=True)
    legend_h = legend_height(beats)

    with tempfile.TemporaryDirectory() as tmp:
        frames = {b["n"]: base_frame(base, float(b["t"]), tmp) for b in todo}
        for k, lay in enumerate(spec.get("layers") or []):
            comp = os.path.join(job_dir, lay["dir"])
            off, dur = float(lay.get("offset", 0)), layer_duration(comp)
            want = {b["n"]: float(b["t"]) - off for b in todo}
            want = {n: lt for n, lt in want.items() if lt >= 0 and (dur is None or lt <= dur)}
            if not want:
                continue
            try:
                stills = snapshot_layer(comp, sorted(set(want.values())), tmp, k)
            except Exception as e:
                # One layer's stills breaking leaves that layer off; the rest of the sheet carries on.
                print(f"  ⚠ could not take stills of {lay['dir']} ({type(e).__name__}); that layer is left off these stills")
                note("beat-sheet", f"stills of {lay['dir']} broke ({type(e).__name__}: {str(e)[:120]}); made the sheet without that layer")
                stills = {}
            for n, lt in want.items():
                if lt in stills:
                    frames[n].alpha_composite(stills[lt])
        for b in todo:
            if b.get("mock"):
                draw_mock(frames[b["n"]], b["mock"], spec.get("pack"))
            stamp(frames[b["n"]], b, legend_h).save(os.path.join(beats_dir, f"{b['n']:02d}.jpg"), quality=90)

    for b in beats:
        if not os.path.exists(os.path.join(beats_dir, f"{b['n']:02d}.jpg")):
            raise SystemExit(f"Beat {b['n']} has never been stamped; run without --only once.")

    # The page before the single image: the page is the beat sheet, the image only its fallback, so the image
    # breaking can never cost her the page.
    html_path = write_html(sheet_dir, beats, a.job)
    sheet = os.path.join(sheet_dir, "beat-sheet.jpg")
    try:
        contact_sheet([Image.open(os.path.join(beats_dir, f"{b['n']:02d}.jpg")) for b in beats], a.job, sheet)
    except Exception as e:
        note("beat-sheet", f"the single-image sheet broke ({type(e).__name__}: {str(e)[:120]}); the page was made without it")
        sheet = None

    done = f"{len(todo)} beat{'s' if len(todo) != 1 else ''}" + (f" re-stamped ({a.only})" if only else "")
    return sheet, html_path, done


def write_md(sheet_dir, beats, job):
    rows = ["| # | time | what | on screen | motion |", "|---|---|---|---|---|"]
    cell = lambda v: str(v or "").replace("|", "/").replace("\n", " ")
    for b in beats:
        rows.append(f"| {b['n']} | {clock(b['t'])} | {cell(b.get('kind'))} | {cell(b.get('says'))} | {cell(b.get('motion'))} |")
    os.makedirs(sheet_dir, exist_ok=True)
    path = os.path.join(sheet_dir, "beat-sheet.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Beat sheet: {job}\n\n" + "\n".join(rows) + "\n")
    return path


def text_fallback(md_path, why, log_line):
    """No stills this time: the table in beat-sheet.md is her beat sheet. The SKILL shows it in the chat and
    the review goes on by beat number, exactly as with the page."""
    note("beat-sheet", log_line)
    print(f"The stills could not be made this time: {why}.")
    print(f"TEXT BEAT SHEET (show this table in the chat; notes by beat number work the same): "
          f"{os.path.relpath(md_path, ROOT).replace(os.sep, '/')}")


def write_html(sheet_dir, beats, job):
    """beat-sheet.html, the director's cut for the app's side browser: the stills three to a row (just the frame,
    cropped off the stamped legend), each with its beat, time, words and motion as text under it. Notes come in
    the chat by beat number. Stills are embedded, not linked: the side browser can open a local page as a
    self-contained snapshot."""
    esc = lambda v: html.escape(str(v or ""))
    def data_uri(im, w):
        im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    cards = []
    for b in beats:
        im = Image.open(os.path.join(sheet_dir, "beats", f"{b['n']:02d}.jpg")).convert("RGB")
        frame = im.crop((0, 0, im.width, min(im.height, round(im.width * 16 / 9))))   # the 9:16 frame, no legend
        cards.append(
            f'<article data-n="{b["n"]}"><img src="{data_uri(frame, 540)}" alt="Beat {b["n"]}" data-full="{data_uri(frame, 960)}">'
            f'<div class="cap"><div class="hd"><b>{b["n"]}</b><span class="t">{clock(b["t"])}</span><span class="k">{esc(b.get("kind"))}</span></div>'
            f'<p class="s">{esc(b.get("says"))}</p><p class="m">{esc(b.get("motion"))}</p></div></article>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Beat sheet: {esc(job)}</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{margin:0;font:14px/1.5 -apple-system,system-ui,sans-serif;background:#0f0f0f;color:#eee}}
header{{position:sticky;top:0;background:#0f0f0f;padding:12px 18px;border-bottom:1px solid #262626;z-index:2}}
header h1{{font-size:16px;margin:0;font-weight:600}}header .sub{{color:#999;font-size:12px}}
main{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:14px}}
article{{background:#171717;border:1px solid #262626;border-radius:12px;overflow:hidden}}
img{{width:100%;aspect-ratio:9/16;object-fit:cover;display:block;cursor:zoom-in;background:#000}}
.cap{{padding:8px 9px 10px;font-size:12px}}.hd{{display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px}}
.hd b{{min-width:24px;height:24px;line-height:24px;text-align:center;border-radius:12px;background:#e0483e;color:#fff;font-size:13px}}
.t{{color:#aaa;font-variant-numeric:tabular-nums}}.k{{color:#ddd}}
.s{{margin:6px 0 0;color:#FFEB7D;font-size:13px}}.m{{margin:4px 0 0;color:#b5b5b5;font-size:12px}}
#big{{position:fixed;inset:0;background:rgba(0,0,0,.92);display:flex;align-items:center;justify-content:center;z-index:3;cursor:zoom-out;padding:14px}}
#big img{{max-height:94vh;width:auto;max-width:94vw;aspect-ratio:auto;cursor:zoom-out}}[hidden]{{display:none!important}}
</style></head><body>
<header><h1>Beat sheet: {esc(job)}</h1><div class="sub">{len(beats)} beats · nothing rendered yet · notes by beat number in the chat · tap a still to enlarge</div></header>
<main>{''.join(cards)}</main><div id="big" hidden><img alt=""></div>
<script>
const big=document.getElementById('big'),bi=big.querySelector('img');
document.querySelectorAll('article img').forEach(i=>i.onclick=()=>{{bi.src=i.dataset.full;big.hidden=false;}});
big.onclick=()=>{{big.hidden=true;}};
</script></body></html>"""
    path = os.path.join(sheet_dir, "beat-sheet.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path


if __name__ == "__main__":
    main()
