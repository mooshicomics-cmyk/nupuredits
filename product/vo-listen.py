#!/usr/bin/env python3
"""vo-listen.py — render a LISTENABLE follow-along MP4 of a spliced voiceover cut.

A Voiceover reel has no picture at the first style-plan gate, so there is nothing to watch — but the
creator still has to HEAR the cut before approving it, exactly the way she watches a Yap rough cut.
This renders the spliced VO as a 9:16 MP4 with the current line (number + text + beat tag) on screen,
so it plays in the chat's side-panel player via the normal markdown link and she can call out edits by
line number while listening.

Run it AFTER vo-splice.py and BEFORE the style-plan widget. Writes the canonical preview path so
`style_plan_link.py <job>` validates.

  python3 product/vo-listen.py --job <job> [--sections transcript/style-plan-sections.json]

Reads   projects/<job>/vo-grid.clean.json   (falls back to vo-grid.json)
        projects/<job>/audio/vo.clean.wav   (falls back to audio/vo.*)
Writes  projects/<job>/outputs/<job>.mp4

Text-only slides via PIL + the ffmpeg concat demuxer: no drawtext dependency (Homebrew ffmpeg often
ships without libfreetype) and no per-frame render, so a 90s VO takes a couple of seconds.
"""
import argparse, glob, json, os, subprocess, tempfile, textwrap
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1920
BG, INK, ACCENT, MUTED = (20, 19, 15), (245, 243, 238), (201, 162, 39), (138, 138, 133)


def _font(name, size):
    return ImageFont.truetype(f"{REPO}/assets/fonts/{name}", size)


def _centered(draw, y, text, font, color):
    for ln in text.split("\n"):
        w = draw.textbbox((0, 0), ln, font=font)[2]
        draw.text(((W - w) // 2, y), ln, font=font, fill=color)
        y += font.size + 18
    return y


def line_numbers(grid):
    """The line number to show on each slide: its line in the RAW grid (vo-grid.json), 1-based.

    That is how the style plan counts and what `vo-splice.py --cut` takes. A spliced grid holds only the
    kept lines, so numbering its slides 1..N put the wrong number on every slide after the first cut, and
    "cut line 7" then removed a different line. The spliced grid records which raw lines were cut."""
    cut = set(grid.get("cut_lines") or [])
    nums, n = [], 0
    while len(nums) < len(grid["phrases"]):
        n += 1
        if n not in cut:
            nums.append(n)
    return nums


def build(job, sections=None):
    jd = f"{REPO}/projects/{job}"
    grid_path = f"{jd}/vo-grid.clean.json"
    if not os.path.exists(grid_path):
        grid_path = f"{jd}/vo-grid.json"
    grid = json.load(open(grid_path, encoding="utf-8"))
    phrases, duration = grid["phrases"], grid["duration"]
    numbers = line_numbers(grid)

    audio = f"{jd}/audio/vo.clean.wav"
    if not os.path.exists(audio):
        hits = sum(([*glob.glob(f"{jd}/audio/vo.{e}")] for e in ("wav", "m4a", "mp3", "aac", "caf")), [])
        if not hits:
            raise SystemExit(f"no VO audio in {jd}/audio/")
        audio = hits[0]

    secs = {}
    if sections and os.path.exists(sections):
        secs = {int(k): v for k, v in json.load(open(sections, encoding="utf-8")).items()}

    f_sec, f_num = _font("Inter-Regular.otf", 36), _font("Inter-Regular.otf", 44)
    f_body = _font("Inter-Medium.ttf", 76)

    tmp = tempfile.mkdtemp()
    slides, tag = [], ""
    for i, p in enumerate(phrases):
        n = numbers[i]
        # the section a line sits in is the last one that started at or before it (a section can start on a
        # line that was cut, and the numbers skip cut lines)
        tag = next((secs[k] for k in sorted(secs, reverse=True) if k <= n), tag)
        end = phrases[i + 1]["a"] if i + 1 < len(phrases) else duration
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        _centered(d, 560, tag, f_sec, MUTED)
        _centered(d, 640, f"line {n}", f_num, ACCENT)
        body = "\n".join(textwrap.wrap(p["text"], 24))
        _centered(d, 860 - ((body.count("\n") + 1) * 94) // 2, body, f_body, INK)
        fp = f"{tmp}/{n:03d}.png"
        img.save(fp)
        slides.append((fp, max(0.2, end - p["a"] + (p["a"] if i == 0 else 0))))

    listfile = f"{tmp}/list.txt"
    with open(listfile, "w", encoding="utf-8") as fh:
        for fp, dur in slides:
            fh.write(f"file '{fp}'\nduration {dur:.3f}\n")
        fh.write(f"file '{slides[-1][0]}'\n")

    os.makedirs(f"{jd}/outputs", exist_ok=True)
    out = f"{jd}/outputs/{job}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                    "-i", audio, "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", out], check=True)
    return out, duration


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--sections", default=None, help="style-plan-sections.json for the beat tags")
    a = ap.parse_args()
    sections = a.sections or f"{REPO}/projects/{a.job}/transcript/style-plan-sections.json"
    out, dur = build(a.job, sections)
    print(f"wrote {out}  ({int(dur // 60)}:{round(dur % 60):02d})")
    print(f"link it with: python3 product/style_plan_link.py {a.job}")
