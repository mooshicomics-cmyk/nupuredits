#!/usr/bin/env python3
"""Regression guard for catalog_caption — a HyperFrames catalog caption style, used by name.

What this locks down (2026-09-29): the course promises buyers that any HyperFrames catalog item works when
they ask for it, captions included. Every catalog caption style ships as a 1920x1080 demo with its own sample
words, so the adapter has to (1) swap in her transcript and nothing else, (2) leave out the words a takeover
owns the screen over, (3) key the style's highlights on HER keywords whether the demo keyed them by index
or by word, (4) narrow every line-fit width to the 1080 frame without shrinking the type, and (5) refuse,
with a reason, a style it cannot adapt, rather than quietly handing back the pack captions.
No network: the fixtures below mirror the real catalog shapes (Kinetic Slam, Emoji Pop, Pill Karaoke,
Camera Follow Captions in HyperFrames' catalog; the same 16 caption styles from 0.8.43 through 0.8.158).

Run: python3 product/tests/test_catalog_caption.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import catalog_caption as CC

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


SLAM = '''<meta name="viewport" content="width=1920, height=1080" />
<style>html, body { width: 1920px; height: 1080px; } #kinetic-slam { width: 1920px; }</style>
<div id="kinetic-slam" data-composition-id="caption-kinetic-slam" data-duration="8" data-width="1920" data-height="1080">
<script>
  var WORDS = [
    { text: "Every", start: 0.0, end: 0.3 },
    { text: "great", start: 0.3, end: 0.55 },
  ];
  var KEYWORDS = new Set([8, 12, 15]);
  el.style.fontSize = fitFontSize(w.text.toUpperCase(), 220, "400", "'Anton', sans-serif", 1720) + "px";
  tl.set(l2El, { opacity: 0, x: -1920 }, start);
</script>'''

EMOJI = '''<div data-composition-id="caption-emoji-pop" data-duration="8">
<script>
  var FONT_SIZE = 72;
  var SAFE_ZONE_WIDTH = 1400;
  var PILL_MAX_WIDTH = 1400;
  var KEYWORDS = new Set(["hyperframes", "html", "cinema"]);
  var TRANSCRIPT = [
    { text: "Every", start: 0.0, end: 0.3 },
  ];
</script>'''

UNTIMED = '''<div data-composition-id="caption-camera-follow" data-duration="9">
<script>
  var WORDS = [
    { text: "write" },
    { text: "the" },
  ];
</script>'''

GROUPED = """<div data-composition-id="caption-gradient-fill" data-duration="8">
<script>
  var WORDS = [
    { text: "Every", start: 0.0, end: 0.3 },
  ];
  var GROUPS = [
    { wordStart: 0, wordEnd: 3, start: 0.0, end: 1.05 },
  ];
</script>"""

BLOCKS_EDITORIAL = """<script>
  var W = [
    { text: "Every", start: 0.0, end: 0.3 },
  ];
  var BLOCKS = [
    { line1: [[0, "n"], [1, "n"]], line2: [[27, "e"]] },
  ];
</script>"""

def nest(n):
    """A doubly bracketed index, built at runtime: make-ship strips wikilink-shaped text from the package."""
    return "[" * 2 + str(n) + "]" * 2


BLOCKS_PARALLAX = """<script>
  var W = [
    { text: "Every", start: 0.0, end: 0.3 },
  ];
  var BLOCKS = [
    { behind: %s, front: [[23], [25]] },
  ];
</script>""" % nest(24)

WORDS = [{"w": "The", "t": 0.1, "e": 0.3}, {"w": "tension", "t": 0.3, "e": 0.8},
         {"w": "\"can", "t": 5.1, "e": 5.4}, {"w": "husband.", "t": 9.0, "e": 9.6}]


def main():
    src, notes = CC.adapt(SLAM, WORDS, duration=77.9, keywords=["Tension", "husband"], windows=[(5.0, 6.0)])
    check("demo words are gone", "Every" not in src and "great" not in src)
    check("her words are in, quotes escaped safely", '"The"' in src and '"husband."' in src and '"\\"can"' not in src)
    check("a word under a takeover is left out", "can" not in src and any("left out" in n for n in notes))
    check("index-keyed highlights point at HER keywords (tension=1, husband.=2 after the drop)",
          "KEYWORDS = new Set([1, 2])" in src, re.search(r"KEYWORDS = new Set\([^)]*\)", src).group(0))
    check("canvas narrowed to the reel frame", "width: 1920px" not in src and 'data-width="1080"' in src
          and "width=1080" in src)
    check("line-fit width narrowed, type size kept", ", 960)" in src and "220," in src)
    check("an off-frame slide-in (-1920) is not reported as a leftover", not any("widescreen" in n for n in notes))
    check("length follows the reel", 'data-duration="77.90"' in src)
    check("big type sits lower than small type", CC.line_half(SLAM) > CC.line_half(EMOJI))

    src, notes = CC.adapt(EMOJI, WORDS, duration=12, keywords=["tension"])
    check("word-keyed highlights become her keywords", 'KEYWORDS = new Set(["tension"])' in src)
    check("every *WIDTH = 14xx constant narrowed", "1400" not in src and "SAFE_ZONE_WIDTH = 960" in src
          and "PILL_MAX_WIDTH = 960" in src)
    check("a TRANSCRIPT-named word list is swapped too", '"tension"' in src and '"Every"' not in src)


    long = [{"w": f"w{i}" + ("." if i % 7 == 6 else ""), "t": i * 0.4, "e": i * 0.4 + 0.3} for i in range(40)]
    src, notes = CC.adapt(GROUPED, long, duration=16)
    ends = [int(x) for x in re.findall(r"wordEnd: (\d+)", src)]
    check("hand-picked demo GROUPS are rebuilt to cover EVERY word, not the first ~20",
          ends and max(ends) == 39 and "wordEnd: 3, start: 0.0, end: 1.05" not in src)
    src, _ = CC.adapt(BLOCKS_EDITORIAL, long, duration=16, keywords=["w10"])
    check("editorial blocks cover every word, keyword in the huge slot",
          "[39, " in src and '[10, "e"]' in src and "[27, \"e\"]" not in src)
    src, _ = CC.adapt(BLOCKS_PARALLAX, long, duration=16, keywords=["w10"])
    check("parallax: a keyword LEADS its block (the style times a block from its behind word)",
          "behind: " + nest(10) in src and "[39]" in src and "behind: " + nest(24) not in src)
    try:
        CC.adapt(UNTIMED, WORDS, duration=12)
        check("an untimed demo is refused, not faked", False)
    except CC.Unsupported as e:
        check("an untimed demo is refused with a reason", "timings" in str(e))

    styles = [("caption-kinetic-slam", "Kinetic Slam"), ("caption-pill-karaoke", "Pill Karaoke"),
              ("caption-highlight", "Highlight")]
    check("spoken names resolve", CC.resolve("kinetic slam captions", styles) == "caption-kinetic-slam"
          and CC.resolve("Pill Karaoke", styles) == "caption-pill-karaoke"
          and CC.resolve("caption-highlight", styles) == "caption-highlight")
    try:
        CC.resolve("Sparkle Rain", styles)
        check("an unknown name is refused", False)
    except LookupError as e:
        check("an unknown name lists what exists", "Kinetic Slam" in str(e))

    clip = CC.clip_html("caption-kinetic-slam", "compositions/components/caption-kinetic-slam.html", 12.0, 1170)
    check("the clip rides the captions lane, centred where asked", 'data-track-index="1"' in clip
          and "top:630px" in clip and 'id="clip-catcap"' in clip)

    print(f"\n{'OK' if not fails else f'{len(fails)} FAILED'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
