#!/usr/bin/env python3
"""Guards: a count-up card's count can climb at a steady pace (a buyer, 2026-10-26: her $300 count-up looked like a
static card, because the default power2.out does most of its climb early, while the card is still coming in).

  default       a counter with no count_ease counts with power2.out, exactly as before
  her pick      "count_ease": "none" (or any GSAP ease name, numbers included) is the ease the count runs on
  only a name   anything that isn't an ease name (a typo, or text that would break out of the page's script) never
                reaches the page: the build says so and counts with the default

Run: python3 product/tests/test_counter_ease_2026_10_26.py   (or python3 -m pytest <this file> -q)
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)
BUILDER = os.path.join(PRODUCT, "build-reel-type.py")


def _drawn():
    """A count-up card drawn the engine's way (lookbook draw), so the plan and words are the real ones."""
    import lookbook
    d = os.path.join(tempfile.mkdtemp(prefix="counter-ease-"), "cnt")
    lookbook.draw("counter", d, "I made 300 dollars", 3.0, "Butter")
    return d


def _build(d, ease=None, drop=False):
    """Build the card again from its plan with count_ease set (or left out). Returns (page html, what it said)."""
    cp = os.path.join(d, "caption-plan.json")
    plan = json.load(open(cp, encoding="utf-8"))
    el = next(e for e in plan["elements"] if e.get("kind") == "counter")
    el.pop("count_ease", None)
    if not drop:
        el["count_ease"] = ease
    json.dump(plan, open(cp, "w", encoding="utf-8"))
    import graphics_python
    env = dict(os.environ, JOB_DIR=d, STYLE_PACK="Butter", LAYER="elements", COMP="cnt", SIZE_SCALE="6.000", HOOK_SPLIT="0")
    env.pop("DUR_OVERRIDE", None); env.pop("REEL_JOB_DIR", None)
    r = subprocess.run([graphics_python.python(), BUILDER], env=env, capture_output=True, text=True, timeout=180)
    page = os.path.join(d, "hf-reel-type-butter", "index.html")
    assert r.returncode == 0 and os.path.isfile(page), (r.stdout + r.stderr)[-800:]
    return open(page, encoding="utf-8").read(), r.stdout + r.stderr


def _count_ease_in(html):
    i = html.find("var o_el0=")
    assert i >= 0, "no count in the page"
    seg = html[i:i + 400]
    a = seg.index('ease:"') + 6
    return seg[a:seg.index('"', a)]


def test_counter_ease():
    d = _drawn()
    try:
        html, _ = _build(d, drop=True)
        assert _count_ease_in(html) == "power2.out", "a counter with no count_ease changed its count"
        html, _ = _build(d, "none")
        assert _count_ease_in(html) == "none", "count_ease none did not reach the count"
        html, _ = _build(d, "back.out(1.7)")
        assert _count_ease_in(html) == "back.out(1.7)"
        bad = 'none",onUpdate:function(){alert(1)},x:"'
        html, said = _build(d, bad)
        assert _count_ease_in(html) == "power2.out" and "alert(1)" not in html, "a non-ease reached the page's script"
        assert "count_ease" in said and "power2.out" in said, said[-400:]
        html, said = _build(d, "bouncy")
        assert _count_ease_in(html) == "power2.out" and "'bouncy'" in said, said[-400:]
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def main():
    try:
        test_counter_ease()
    except AssertionError as e:
        print(f"  FAIL  counter ease: {str(e)[-600:]}")
        print("test_counter_ease_2026_10_26: FAIL")
        return 1
    print("  PASS  counter ease: default unchanged, her pick reaches the count, only an ease name gets in")
    print("test_counter_ease_2026_10_26: all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
