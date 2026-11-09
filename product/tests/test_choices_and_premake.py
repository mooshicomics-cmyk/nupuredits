#!/usr/bin/env python3
"""Guards: autopilot's defaults come from her real past reels (product/choices.py), and a quietly premade
full-quality cut is only ever used when it is exactly the cut she's locking (product/premake.py).

  choices: old reels' plans are read under their old names (route/doneness, pack/style_pack); the pack is the
           most recent one that still exists; the route is the one picked most (ties: most recent); test and
           copy reels (review/.test-reel) are never learned from; no history = no defaults; record() keeps only valid values;
           the register lean reads her words and gives "none" when they don't lean
  premake: adopt() refuses a premade video when the cut changed after it was made, when the shadow stitch moved
           the cut, or when it didn't finish; it moves the video in only when everything matches

Run: python3 product/tests/test_choices_and_premake.py
"""
import json, os, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
import choices, premake  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name} {detail}")


def reel(root, name, rel, data, age):
    p = os.path.join(root, "projects", name, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(data, open(p, "w", encoding="utf-8"))
    t = time.time() - age
    os.utime(p, (t, t))


def test_choices(tmp):
    choices.ROOT = tmp
    check("choices: no reels at all = no defaults", choices.defaults()["defaults"] == {"mode": "walk"}, choices.defaults())
    reel(tmp, "a-old", "graphics-plan.json", {"doneness": "well-done", "style_pack": "Butter", "register": "teaching"}, 500)
    reel(tmp, "b-mid", "graphics-plan.json", {"route": "medium", "pack": "Editorial"}, 300)
    reel(tmp, "c-new", "beat-sheet/beats.json", {"route": "medium", "pack": "Playful"}, 100)
    reel(tmp, "test-reel", "review/choices.json", {"route": "raw", "pack": "Butter"}, 1)
    reel(tmp, "test-reel", "review/.test-reel", {}, 1)
    d = choices.defaults()
    check("choices: older names are read (doneness, style_pack)", choices.read(os.path.join(tmp, "projects", "a-old")) == {"route": "well-done", "pack": "Butter", "register": "teaching"})
    check("choices: a reel marked review/.test-reel is never learned from", "test-reel" not in d["from_reels"], d)
    check("choices: the pack is the most recent reel's", d["defaults"].get("pack") == "Playful", d)
    check("choices: the route is the one picked most", d["defaults"].get("route") == "medium" and "2 of your last 3" in d["why"]["route"], d)
    reel(tmp, "d-newest", "review/choices.json", {"pack": "No Such Pack", "route": "raw"}, 10)
    d = choices.defaults()
    check("choices: a pack this engine no longer has is skipped", d["defaults"].get("pack") == "Playful", d)
    reel(tmp, "e-tie", "review/choices.json", {"route": "raw"}, 5)
    d = choices.defaults()
    check("choices: a tie goes to the most recent", d["defaults"].get("route") == "raw", d)
    jd = os.path.join(tmp, "projects", "f-rec")
    os.makedirs(jd)
    out = choices.record(jd, pack="Butter", route="sideways", register="teaching", mode="autopilot")
    check("choices: record keeps valid values and drops the rest", out.get("pack") == "Butter" and "route" not in out and out.get("mode") == "autopilot", out)
    check("choices: a clear teaching lean", choices.register_guess("here's how. step one, step two, then you need three tips")[0] == "teaching")
    check("choices: a clear story lean", choices.register_guess("i felt scared. honestly i was afraid and i cried. i remember")[0] == "confessional")
    check("choices: no lean when the words don't lean", choices.register_guess("we went to the park today")[0] is None)


def test_premake(tmp):
    premake.ROOT = tmp
    ve = premake._ve()
    jd = os.path.join(tmp, "projects", "pm")
    for d in ("transcript", "outputs", "review"):
        os.makedirs(os.path.join(jd, d), exist_ok=True)
    open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8").write('{"segments": [1]}')
    real_dir, real_stale, real_stamp = ve.job_dir, ve.base_is_stale, ve._stamp_base
    ve.job_dir = lambda job: jd
    stamped = []
    ve._stamp_base = lambda j: stamped.append(j)
    ve.base_is_stale = lambda job: not stamped
    try:
        sh = premake.shadow(jd)
        os.makedirs(os.path.join(sh, "outputs"), exist_ok=True); os.makedirs(os.path.join(sh, "transcript"), exist_ok=True)
        mp4 = os.path.join(sh, "outputs", os.path.basename(sh) + ".mp4")
        open(mp4, "wb").write(b"video")
        shutil.copyfile(os.path.join(jd, "transcript", "cuts.json"), os.path.join(sh, "transcript", "cuts.json"))
        sig = premake._sha(os.path.join(jd, "transcript", "cuts.json"))
        premake._save_state(jd, status="running", cut=sig)
        check("premake: not used while it's still running", premake.adopt("pm") is False)
        premake._save_state(jd, status="ready", cut="someothercut")
        check("premake: not used when her cut changed after it was made", premake.adopt("pm") is False)
        premake._save_state(jd, status="ready", cut=sig)
        open(os.path.join(sh, "transcript", "cuts.json"), "w", encoding="utf-8").write('{"segments": [2]}')
        check("premake: not used when the shadow stitch moved the cut", premake.adopt("pm") is False)
        open(os.path.join(sh, "transcript", "cuts.json"), "w", encoding="utf-8").write('{"segments": [1]}')
        open(os.path.join(jd, "transcript", "cuts.json"), "w", encoding="utf-8").write('{"segments": [{"start": 1, "end": 2, "_snapped_from": {"start": 0.9}}]}')
        open(os.path.join(sh, "transcript", "cuts.json"), "w", encoding="utf-8").write('{"segments": [{"start": 1, "end": 2, "_snapped_from": {"start": 1.0}}]}')
        sig = premake._sha(os.path.join(jd, "transcript", "cuts.json"))
        premake._save_state(jd, status="ready", cut=sig)
        check("premake: the stitch's bookkeeping alone never counts as a different cut", premake._sha(os.path.join(sh, "transcript", "cuts.json")) == sig)
        check("premake: her job has no video before adopting", not os.path.exists(os.path.join(jd, "outputs", "pm.mp4")))
        ok = premake.adopt("pm")
        check("premake: used when everything matches", ok is True and open(os.path.join(jd, "outputs", "pm.mp4"), "rb").read() == b"video" and stamped, ok)
        check("premake: the shadow copy is cleared after use", not os.path.exists(sh))
        check("premake: a lock with nothing premade just goes the normal way", premake.adopt("pm") is False)
    finally:
        ve.job_dir, ve.base_is_stale, ve._stamp_base = real_dir, real_stale, real_stamp


def main():
    tmp = tempfile.mkdtemp(prefix="choices-premake-")
    real = (choices.ROOT, premake.ROOT)
    try:
        test_choices(tmp)
        test_premake(tmp)
    finally:
        choices.ROOT, premake.ROOT = real
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_choices_and_premake: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"test_choices_and_premake: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
