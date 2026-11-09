#!/usr/bin/env python3
"""Guard: an update refreshes the ENGINE's instructions in CLAUDE.md and keeps the creator's own block.

The bug this prevents: CLAUDE.md is protected from updates because it holds the creator's applied brand
kit. That protection also meant that every change to the engine's instructions in that file never reached
an existing install: the code updated, the rules Claude reads did not (an install could keep reading
"bottom 480 px" or "doctor downloads the browser" for ever). scripts/merge-claude-md.py is the fix, and
this proves the three things it must do.

Run: python3 product/tests/test_claude_md_merge.py
"""
import importlib.util, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "merge-claude-md.py")

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("mcm", SCRIPT)
mcm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mcm)

OLD_RULE = "no key visuals in the **top 270 px** or **bottom 480 px**"
NEW_RULE = "no key visuals in the **top 270 px** or **bottom 300 px**"
PROFILE = ["### Applied — Jane Doe / Doe Bakery (2026-08-01)", "", "**Creator:** Jane Doe. Voice: warm and direct.", ""]
BLANK = ["### Applied - nothing yet (fresh install)", "", "**No creator is applied to this engine.**", ""]
LOOK_SET = ["**🎨 LOOK IS SET — the Editorial pack is live.** Playfair Display headline, Poppins caption.",
            "Her pack accent is Prosecco and Baguette."]
LOOK_BLANK = ["**🎨 LOOK IS NOT SET YET.** Only voice and identity above are applied. Colors and fonts are the",
              "**starter defaults** on purpose."]


def doc(profile, rule, extra_engine_line="- rule A", look=None):
    return "\n".join(["# CLAUDE.md", "", "## Brand Kit", ""] + profile +
                     ["**⚠️ ASK THE REGISTER AT THE GRAPHICS STEP**", ""] + (look or LOOK_BLANK) +
                     ["", "## Rules", extra_engine_line, rule, ""])


def main():
    print("CLAUDE.md merge\n")
    buyer = doc(PROFILE, OLD_RULE)
    template = doc(BLANK, NEW_RULE, "- rule A\n- rule B (new)")
    merged, note = mcm.merge(buyer, template)
    check("merge produces a result", merged is not None, str(note))
    if merged:
        check("the creator's profile block is kept word for word", "\n".join(PROFILE) in merged)
        check("the blank fresh-install stub is NOT what she ends up with", "nothing yet (fresh install)" not in merged)
        check("the new engine rule arrives", NEW_RULE in merged)
        check("the old engine rule is gone", OLD_RULE not in merged)
        check("a brand-new engine rule arrives too", "rule B (new)" in merged)
        again, _ = mcm.merge(merged, template)
        check("running it again changes nothing (idempotent)", again == merged)

    m2, note2 = mcm.merge("# CLAUDE.md\n\nno markers here\n", template)
    check("a CLAUDE.md without the markers is refused, never overwritten", m2 is None and bool(note2))

    # The regression a real Windows install hit: onboarding set the look banner, an update refreshed
    # CLAUDE.md, and the banner silently went back to "NOT SET YET" while the profile block survived.
    # Nobody would notice until a reel came out in the starter colors.
    personalised = doc(PROFILE, OLD_RULE, look=LOOK_SET)
    m3, note3 = mcm.merge(personalised, template)
    check("the creator's look banner survives an update", m3 is not None and "\n".join(LOOK_SET) in m3, str(note3))
    check("the update does not revert her to 'LOOK IS NOT SET YET'", m3 is not None and "LOOK IS NOT SET YET" not in m3)
    check("the engine rule still arrives alongside it", m3 is not None and NEW_RULE in m3)
    check("keeping the banner does not disturb the profile block", m3 is not None and "\n".join(PROFILE) in m3)
    again3, _ = mcm.merge(m3, template)
    check("look-banner merge is idempotent too", again3 == m3)

    # A creator file with no look banner at all (an older install) must still merge, not refuse.
    no_look = "\n".join(l for l in personalised.split("\n") if not l.startswith("**🎨 LOOK IS"))
    m4, note4 = mcm.merge(no_look, template)
    check("a CLAUDE.md with no look banner still merges", m4 is not None and "\n".join(PROFILE) in m4, str(note4))


    # end to end through the script, in a throwaway engine folder
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "scripts")); os.makedirs(os.path.join(d, "product", "templates"))
        import shutil; shutil.copy(SCRIPT, os.path.join(d, "scripts", "merge-claude-md.py"))
        open(os.path.join(d, "CLAUDE.md"), "w", encoding="utf-8").write(buyer)
        open(os.path.join(d, "product", "templates", "CLAUDE.engine.md"), "w", encoding="utf-8").write(template)
        r = subprocess.run([sys.executable, os.path.join(d, "scripts", "merge-claude-md.py")],
                           capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})
        out = open(os.path.join(d, "CLAUDE.md"), encoding="utf-8").read()
        check("the script runs cleanly", r.returncode == 0, r.stdout + r.stderr)
        check("the script writes the merged file", NEW_RULE in out and "\n".join(PROFILE) in out)
        bdir = os.path.join(d, "_update-backups", "claude-md")
        check("the previous CLAUDE.md is backed up first", os.path.isdir(bdir) and any(f.endswith(".bak") for f in os.listdir(bdir)))
        r2 = subprocess.run([sys.executable, os.path.join(d, "scripts", "merge-claude-md.py")],
                            capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})
        check("a second run reports 'already current' and adds no backup",
              "already current" in r2.stdout and len(os.listdir(bdir)) == 1, r2.stdout)

    print()
    if fails:
        print(f"FAILED: {len(fails)} -- {', '.join(fails)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
