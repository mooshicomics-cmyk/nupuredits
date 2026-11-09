#!/usr/bin/env python3
"""Guards where each --layer lands in her CapCut draft (ISS-12, 2026-10-19).

A buyer's graphics "all launched on top of each other in CapCut, every one visible at the same time". A --layer
with no @START went in at 0, so a handful of short graphics handed over without their starts all stacked at the
top of the reel.

  starts    two short layers handed over with different @STARTs land at those two different starts
  page      a short layer with no @START takes its start from her page (review/looks.json "offset")
  warns     a short layer with no start anywhere still goes in (she always gets her reel), and is named in one line
  full      a full-length transparent layer with no @START starts at 0, with no note, exactly as before

Runs the real handoff with the CapCut build engine replaced by a recorder (nothing reaches CapCut).

Run: python3 product/tests/test_handoff_layer_starts.py
"""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
sys.path.insert(0, PRODUCT)

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}  -- {detail}")


def clear_mov(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=white@0.0:size=180x320:rate=30:duration={seconds:.2f},format=rgba",
                    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", path], check=True)


def main():
    tmp = tempfile.mkdtemp(prefix="handoff-starts-")
    try:
        root = os.path.join(tmp, "engine"); jd = os.path.join(root, "projects", "tiny")
        for d in ("outputs", "layers", "review"):
            os.makedirs(os.path.join(jd, d))
        base = os.path.join(jd, "outputs", "tiny.mp4")       # her cut: 8 s
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=30:duration=8",
                        "-f", "lavfi", "-i", "sine=frequency=220:duration=8", "-shortest", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", base], check=True)
        L = lambda n: os.path.join(jd, "layers", n)
        for n in ("hook.mov", "card.mov", "stat.mov", "loose.mov"):
            clear_mov(L(n), 1.5)                              # short graphics
        clear_mov(L("captions.mov"), 8.0)                    # a full-length transparent layer
        json.dump({"layers": [{"name": "stat", "offset": 4.25, "dir": "hf-graphics/stat"}]},
                  open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))

        import types
        sys.modules.setdefault("requests", types.ModuleType("requests"))   # the CapCut engine is replaced below
        import capcut_handoff as H, draft_safety, cleanyap, capcut_tail, capcut_alpha
        calls = []

        def rec(ep, **kw):
            calls.append((ep, kw))
            return {"draft_id": "test"} if ep == "create_draft" else {}
        H.call, H.ROOT = rec, root
        draft_safety.require_capcut_quit = lambda *a, **k: None
        draft_safety.next_version = lambda *a, **k: "tiny 1.1"
        cleanyap.finalize = lambda *a, **k: "tiny 1.1"
        capcut_tail.tailed_base = lambda jd, base, bdur, *a, **k: (base, 0.0)
        capcut_alpha.for_capcut = lambda p: p

        argv, out = sys.argv, io.StringIO()
        sys.argv = ["capcut_handoff.py", "tiny", "--no-overlay", "--pack", "Butter", "--one-clip",
                    "--layer", f"captions={L('captions.mov')}",
                    "--layer", f"hook={L('hook.mov')}@2.0",
                    "--layer", f"card={L('card.mov')}@5.0",
                    "--layer", f"stat={L('stat.mov')}",
                    "--layer", f"loose={L('loose.mov')}"]
        try:
            with contextlib.redirect_stdout(out):
                H.main()
        except SystemExit as e:
            check("the handoff ran to the end", not e.code, f"exit {e.code}: {out.getvalue()[-400:]}")
        except Exception as e:
            check("the handoff ran to the end", False, repr(e))
        finally:
            sys.argv = argv
        said = out.getvalue()
        at = {kw.get("track_name"): kw.get("target_start") for ep, kw in calls if ep == "add_video"}

        check("starts: the hook lands at its @START", abs((at.get("hook") or -1) - 2.0) < 1e-6, at)
        check("starts: the card lands at its @START", abs((at.get("card") or -1) - 5.0) < 1e-6, at)
        check("starts: the two short layers land at different starts", at.get("hook") != at.get("card"), at)
        check("page: a short layer with no @START takes its start from her page", abs((at.get("stat") or -1) - 4.25) < 1e-6, at)
        check("warns: a short layer with no start anywhere is still laid in", "loose" in at, at)
        check("warns: it goes in at the top of the reel", at.get("loose") == 0.0, at)
        warn = [ln for ln in said.splitlines() if "no start time" in ln]
        check("warns: one plain line names it", len(warn) == 1 and "loose" in warn[0], said)
        check("warns: the line names only the layer with no start", warn and not any(n in warn[0] for n in ("hook", "card", "stat", "captions")), warn)
        check("warns: plain words, no alarm symbols", warn and not any(ch in warn[0] for ch in "⛔⚠❌"), warn)
        check("full: a full-length layer with no @START starts at 0", at.get("captions") == 0.0, at)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_handoff_layer_starts: {len(fails)} of {total} checks FAILED")
        for f in fails:
            print("  FAIL", f[:500])
        return 1
    print(f"test_handoff_layer_starts: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
