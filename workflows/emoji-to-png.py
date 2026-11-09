#!/usr/bin/env python3
"""emoji-to-png.py: small transparent images of emoji, for a reel graphic to place.

    python3 workflows/emoji-to-png.py <name>=<emoji> [<name>=<emoji> ...] [--out DIR | --job JOB] [--px N]

For a job whose cards want a coffee cup and an alarm clock:

    python3 workflows/emoji-to-png.py coffee=☕ alarm=⏰ --job <job>

Each pair becomes <name>.png (in ./assets/emoji, the folder --out names, or the job's graphics assets with
--job): the glyph from this computer's color-emoji font, cut to its ink and centred on a transparent square
the size of its em, so placing it at a width shows it as large as that font size would. A graphic places
that image where the emoji would have gone; the renderer is never handed an emoji character itself
(graphics-part-by-part.md, "In a composition", says why).
"""
import os
import sys

for _stream in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ENGINE = Path(__file__).resolve().parent.parent

# The engine runs on macOS and Windows, and each ships one color-emoji face at a fixed place.
MAC_EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"
WINDOWS_EMOJI = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "seguiemj.ttf")

# The em every emoji is drawn at. Apple Color Emoji only draws at its fixed bitmap sizes and 160 is the
# largest; Windows draws at that same em, so a PNG made on either machine comes out the same size.
EM = 160

# Where a graphic puts the image. A reel graphic sizes an emoji by its font size: build-reel-type's vibe
# element writes `font-size:<size>px; line-height:1` (78 by default), and a composition's emoji line does the
# same. That glyph fills its em square, so the image is that square: the ink set in the middle of an EM-wide
# canvas. Placed at `width:<size>px` it shows the emoji exactly as large as `font-size:<size>px` would have,
# with only the room the font itself leaves around it.
VIBE_DEFAULT_PX = 78

USAGE = """usage: python3 workflows/emoji-to-png.py <name>=<emoji> [<name>=<emoji> ...] [--out DIR | --job JOB] [--px N]

  --out DIR   where the PNGs go (default: ./assets/emoji)
  --job JOB   put them in projects/JOB/hf-graphics/assets/emoji, beside the job's graphics
  --px N      make each PNG N pixels square: the size the graphic places it at
              (the vibe emoji's default is %d). Without it, each is %d square.""" % (VIBE_DEFAULT_PX, EM)


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def read_args(argv):
    """-> ([(name, emoji), ...], folder, px). --out, --job and --px each take the word after them; a later
    one of the same kind wins. Every other word is name=emoji, split at its first '='."""
    pairs, folder, px = [], Path("assets/emoji"), None
    words = list(argv)
    while words:
        word = words.pop(0)
        if word in ("-h", "--help"):
            print(USAGE)
            sys.exit(0)
        if word in ("--out", "--job", "--px"):
            if not words:
                fail(f"{word} needs a value after it.\n\n{USAGE}")
            value = words.pop(0)
            if word == "--out":
                folder = Path(value)
            elif word == "--job":
                job = ENGINE / "projects" / value
                if "/" in value or "\\" in value or not job.is_dir():
                    fail(f"There is no job called '{value}' in projects/.")
                folder = job / "hf-graphics" / "assets" / "emoji"
            else:
                if not value.isdigit() or int(value) < 1:
                    fail(f"--px takes a whole number of pixels, not {value!r}.")
                px = int(value)
            continue
        name, eq, emoji = word.partition("=")
        if not eq:
            fail(f"'{word}' is not name=emoji (for example coffee=☕).\n\n{USAGE}")
        pairs.append((name, emoji))
    if not pairs:
        fail(USAGE)
    return pairs, folder, px


def emoji_font():
    """This machine's color-emoji face, or None."""
    for path in (MAC_EMOJI,) if sys.platform == "darwin" else (WINDOWS_EMOJI,) if os.name == "nt" else ():
        if os.path.exists(path):
            return path
    return None


def draw(emoji, font):
    """The emoji in color, cut to its ink, centred on its em square. None when it draws nothing."""
    x0, y0, x1, y1 = font.getbbox(emoji, anchor="ls")   # the run as the font lays it out from its baseline
    if x1 <= x0 or y1 <= y0:
        return None
    sheet = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).text((-x0, -y0), emoji, font=font, anchor="ls", embedded_color=True)
    box = sheet.getbbox()
    if box is None:
        return None
    ink = sheet.crop(box)
    side = max(EM, ink.width, ink.height)   # wider only for a sequence that lays out as several glyphs
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(ink, ((side - ink.width) // 2, (side - ink.height) // 2), ink)
    return square


def main():
    pairs, folder, px = read_args(sys.argv[1:])
    font_path = emoji_font()
    if font_path is None:
        fail("Emoji are drawn with the color-emoji face macOS and Windows ship (Apple Color Emoji, Segoe UI\n"
             "Emoji), and it is not here. Draw the shape in the pack's own display face instead\n"
             "(graphics-part-by-part.md, \"In a composition\").")
    font = ImageFont.truetype(font_path, EM)
    folder.mkdir(parents=True, exist_ok=True)
    if px and px > EM:
        print(f"Drawn at {EM} (the largest this emoji face draws) and enlarged to {px}: they will look softer.")
    for name, emoji in pairs:
        image = draw(emoji, font)
        if image is None:
            fail(f"{name}: {emoji!r} drew nothing. It is not an emoji this face has in color.")
        if px and image.width != px:
            image = image.resize((px, px), Image.LANCZOS)
        image.save(folder / f"{name}.png")
        print(f"  ✓ {name}.png  {emoji}  {image.width}×{image.height}")
    size = px or EM
    print(f"{len(pairs)} PNG(s) in {folder}. Place each with width:{size}px where the emoji would have had "
          f"font-size:{size}px.")


if __name__ == "__main__":
    main()
