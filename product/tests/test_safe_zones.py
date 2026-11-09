#!/usr/bin/env python3
"""Regression guard: nothing meaning-bearing may sit where the PLATFORM draws its own UI.

The bug: the engine documented a top band of 200px, so a persistent category label was placed at y201-263
and shipped sitting directly under Instagram's Reels header. Meta reserves the top 14% (269px of 1920).

Why it needs a guard rather than care: a UI collision is invisible in the render, in QuickTime, and in any
preview. It only appears in the app, on a phone, after posting. Nothing catches it except this.

The bottom band is a different story and this test encodes the actual policy: the engine default is the
creator's explicit call of 300px clear (BOTTOM = 1620), deliberately looser than every platform's published
band. So the default must (a) still be exactly that number, (b) still catch anything under it, and (c)
keep the per-platform table factual so a single-platform check still flags Instagram's real 384px band.

Run: python3 product/tests/test_safe_zones.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import safe_zones as SZ

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def main():
    print("safe zones\n")

    # TOP: the incident band. Must be at least as strict as every platform, and must never go back to 200.
    for p, v in SZ.PLATFORMS.items():
        check(f"default top is at least as strict as {p}", SZ.TOP >= v["top"], f"{SZ.TOP} < {v['top']}")
    check("top band is no longer the old 200", SZ.TOP > 200)

    # the exact placement that shipped broken must be flagged; the corrected one must pass
    bad = SZ.violations([("persistent label", 201, 263)])
    check("the y201-263 label that shipped IS caught", any(e == "top" for _, e, _, _ in bad))
    ok = SZ.violations([("persistent label", 279, 341)])
    check("the corrected y279-341 label passes", not ok)

    # BOTTOM: the creator's locked 300px call, and it must still be enforced as a band
    check("default bottom is the creator's locked 300px (y1620)", SZ.BOTTOM == SZ.H - 300, f"got {SZ.BOTTOM}")
    low = SZ.violations([("caption", 1600, 1700)])
    check("something under the 300px band IS caught by the default", any(e == "bottom" for _, e, _, _ in low))
    inside = SZ.violations([("caption", 1400, 1500)])
    check("y1400-1500 is inside the creator's default and passes", not inside)

    # the per-platform table must stay factual: the same element is inside the default but
    # inside Instagram's real 20% band, and a single-platform check must still say so
    reels = SZ.violations([("caption", 1560, 1600)], platform="reels")
    check("a single-platform check still flags Instagram's real 384px band", any(e == "bottom" for _, e, _, _ in reels))
    check("per-platform bottoms are still the published bands", SZ.PLATFORMS["reels"]["bottom"] == SZ.H - 384
          and SZ.PLATFORMS["tiktok"]["bottom"] == SZ.H - 480)

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
