#!/usr/bin/env python3
"""Regression guard: text stuck past the edge of the video is caught (said and rendered, or refused with --strict).

The bug this locks down: HyperFrames reports text past the frame edge as a `canvas_overflow` WARNING, and a
warning passes the check, so the gate printed "safe to render" over a takeover word running 207px off the
right edge and the render would have shipped it cut off. reel_render.py and reel_gate.py now refuse on it.

What must hold: a lasting overflow (⚠) is caught, once per element at its furthest; a word only sliding
through the edge as it animates in (ℹ) is not; the other warning kinds are not; and the message names the
word, the edge and the way out. Uses the check's real output format, no browser.

Run: python3 product/tests/test_offframe_text.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import reel_render as RR

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


FIX = ("        Fix: Move the text inward, reduce its size, or mark intentional off-canvas animation with "
       "data-layout-allow-overflow.\n")
STUCK = ('Layout\n'
         '  ⚠ t=16.4-18.07s (12 samples) canvas_overflow #tk0w0 inside #root overflowed right 206.55px "РАЗЛИЧНИ" '
         '— Text extends outside the composition canvas.\n' + FIX +
         '  ⚠ t=16.87-16.88s (2 samples) canvas_overflow #tk0w1 inside #root overflowed right 134.15px "ПОДОБНИ" '
         '— Text extends outside the composition canvas.\n' + FIX +
         '  ⚠ t=17.13-18.07s (4 samples) canvas_overflow #tk0w1 inside #root overflowed right 125.5px "ПОДОБНИ" '
         '— Text extends outside the composition canvas.\n' + FIX)
PASSING = ('  ℹ t=16.15s canvas_overflow #tk0w0 inside #root overflowed right 249.03px "РАЗЛИЧНИ" '
           '— Text extends outside the composition canvas.\n' + FIX)
OTHER = ('  ⚠ timeline_track_too_dense: Track 1 has 47 timed elements in this HTML file.\n'
         '  0 error(s), 1 warning(s), 0 info(s)\n◇  Check passed\n')


def main():
    items = RR._offframe_text(STUCK + PASSING + OTHER)
    check("a lasting overflow is caught, once per element", [i[1] for i in items] == ["#tk0w0", "#tk0w1"], str(items))
    # ПОДОБНИ's 134px reading is two samples at one instant (a seam), so its furthest LASTING reading is 126px
    check("each is reported at its furthest lasting reading", [round(i[3]) for i in items] == [207, 126], str(items))
    check("the word, time and edge come through", items and items[0][0] == 16.4 and items[0][2] == "right"
          and items[0][4] == "РАЗЛИЧНИ", str(items))
    check("a word only sliding through the edge (ℹ) is not caught", RR._offframe_text(PASSING + OTHER) == [])
    check("other warnings are not caught", RR._offframe_text(OTHER) == [])
    SEAM = ('  ⚠ t=3.65-3.66s (2 samples) canvas_overflow div.t inside #root overflowed left 83.57px "and most '
            'importantly" — Text extends outside the composition canvas.\n' + FIX)
    check("a panel sliding out on purpose (two samples at one instant) is not caught", RR._offframe_text(SEAM) == [])
    TWO_EDGES = ('  ⚠ t=8.75-10.44s (8 samples) canvas_overflow p.head-lead inside #root overflowed left 502.62px, '
                 'bottom 119.89px "This is one raw phone clip" — Text extends outside the composition canvas.\n' + FIX)
    got = RR._offframe_text(TWO_EDGES)
    check("text past two edges at once is caught", len(got) == 1 and got[0][4] == "This is one raw phone clip", str(got))
    # HyperFrames from 0.8.152 lists every sample time instead of a range; the gate reads both the same way
    LISTED = ('  ⚠ t=0.1, 0.15, 0.2, 0.275, 8.5, 8.525, 9s canvas_overflow #ovf inside #root overflowed right '
              '1064.75px "OVERFLOWING" — Text extends outside the composition canvas.\n' + FIX)
    got = RR._offframe_text(LISTED)
    check("the 0.8.152+ sample list is caught too", len(got) == 1 and got[0][4] == "OVERFLOWING" and got[0][0] == 0.1,
          str(got))
    LISTED_SEAM = ('  ⚠ t=4.9, 4.91s canvas_overflow #p inside #root overflowed left 300px "BYE" — Text extends '
                   'outside the composition canvas.\n' + FIX)
    check("a two-sample seam in the listed form is still let through", RR._offframe_text(LISTED_SEAM) == [])
    msg = RR._offframe_message(items)
    check("the message says it refuses and names the word and edge",
          "REFUSING" in msg and '"РАЗЛИЧНИ"' in msg and "207px past the right edge" in msg, msg)
    check("the message gives both ways out",
          "data-layout-allow-overflow" in msg and "REEL_ALLOW_OFFFRAME_TEXT=1" in msg, msg)

    if fails:
        print(f"\nFAIL: {len(fails)} check(s) failed")
        sys.exit(1)
    print("\n✓ off-frame text: a word stuck past the edge is caught (said, or refused with --strict); a word sliding through is not")


if __name__ == "__main__":
    main()
