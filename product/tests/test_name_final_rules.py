#!/usr/bin/env python3
"""Guard: scripts/name-final.sh promotes the right pass, never deletes a clean cut, and never loses a final.

Each case builds a throwaway engine folder (a copy of name-final.sh and the path shim, plus one job's outputs/)
and runs `name-final.sh <job> --apply` there, so the real projects/ and Downloads are never touched.

What broke, one case each:
  - a job name holding "final" or "draft" (final-cut, draft-day, first-draft-tips) made every pass look final
    or like a draft: draft-day promoted a stranger's file, final-cut kept every pass it should have cleared
  - a job folder renamed after its cut (_kajabi holding kajabi.mp4 + kajabi.transcript.json) had its clean cut
    deleted as a leftover, and a job name holding [ ] made find treat it as a pattern and do the same
  - a newer pass replaced an existing <job>.final.mp4 with no copy kept
  - a short preview (an 11-second cold open, a 6-second hook test) was promoted as "the reel"

Run: python3 product/tests/test_name_final_rules.py
"""
import os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []
T0 = time.time() - 86400          # a fixed "yesterday" every file's age is counted from


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-400:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def engine(tmp):
    eng = os.path.join(tmp, "engine")
    os.makedirs(os.path.join(eng, "scripts"))
    for name in ("name-final.sh", "_path-shim.sh"):
        shutil.copy(os.path.join(ROOT, "scripts", name), os.path.join(eng, "scripts", name))
    return eng


def put(eng, job, files):
    """files: [(name, minutes after T0, text or None for 'a real video already written there')]"""
    out = os.path.join(eng, "projects", job, "outputs")
    os.makedirs(out, exist_ok=True)
    for name, minute, body in files:
        p = os.path.join(out, name)
        if body is not None:
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
        os.utime(p, (T0 + minute * 60, T0 + minute * 60))
    return out


def name_final(eng, job):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.path.join(eng, "home"),
           "REELS_EXPORT_DIR": os.path.join(eng, "no-such-export-dir"), "LC_ALL": "C"}
    r = subprocess.run(["bash", "scripts/name-final.sh", job, "--apply"], cwd=eng, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def read(p):
    """A file's text, or None when it is not there (so a regression reads as a FAIL, not a crash)."""
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def video(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True, capture_output=True)


def main():
    print("name-final.sh: the right pass, no lost cut, no lost final\n")

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        out = put(eng, "final-cut", [("final-cut.mp4", 0, "cut"), ("final-cut-music.mp4", 10, "m"),
                                     ("final-cut-v2.mp4", 20, "v2")])
        rc, log = name_final(eng, "final-cut")
        check("final-cut: the newest pass becomes the reel", rc == 0 and read(os.path.join(out, "final-cut.final.mp4")) == "v2", log)
        check("final-cut: the pass it replaced is cleared, not kept as 'also final'",
              not os.path.exists(os.path.join(out, "final-cut-music.mp4")), log)

        out = put(eng, "with-bed", [("with-bed.mp4", 0, "cut"), ("with-bed-graphics.mp4", 10, "g"),
                                    ("with-bed.bed.mp4", 20, "bed")])
        rc, log = name_final(eng, "with-bed")
        check("with-bed: the music bed (<job>.bed.mp4), laid last, becomes the reel",
              rc == 0 and read(os.path.join(out, "with-bed.final.mp4")) == "bed"
              and not os.path.exists(os.path.join(out, "with-bed-graphics.mp4")), log)

        out = put(eng, "draft-day", [("draft-day.mp4", 0, "cut"), ("draft-day-music.mp4", 10, "m"), ("other.mp4", -5, "o")])
        rc, log = name_final(eng, "draft-day")
        check("draft-day: its own pass becomes the reel, not a stranger's file",
              rc == 0 and read(os.path.join(out, "draft-day.final.mp4")) == "m", log)

        out = put(eng, "first-draft-tips", [("first-draft-tips.mp4", 0, "cut"), ("first-draft-tips-music.mp4", 10, "m"),
                                            ("first-draft-tips-draft.mp4", 20, "d")])
        rc, log = name_final(eng, "first-draft-tips")
        check("first-draft-tips: a pass is not a draft just because the job's name says draft",
              rc == 0 and read(os.path.join(out, "first-draft-tips.final.mp4")) == "m", log)
        check("first-draft-tips: a real draft pass still never wins",
              "first-draft-tips-draft.mp4" in log and read(os.path.join(out, "first-draft-tips.final.mp4")) != "d", log)

        out = put(eng, "_kajabi", [("kajabi.mp4", 0, "clean"), ("kajabi.transcript.json", 0, "{}"),
                                   ("kajabi.final.mp4", 30, "reel"), ("caption-demo.mp4", 10, "demo")])
        rc, log = name_final(eng, "_kajabi")
        check("_kajabi: the renamed job's clean cut survives --apply",
              rc == 0 and os.path.exists(os.path.join(out, "kajabi.mp4")) and read(os.path.join(out, "kajabi.mp4")) == "clean", log)
        check("_kajabi: its final becomes the deliverable", read(os.path.join(out, "_kajabi.final.mp4")) == "reel", log)

        out = put(eng, "job[1]", [("job[1].mp4", 0, "cut"), ("job[1]-music.mp4", 20, "m"), ("job1.mp4", 10, "x")])
        rc, log = name_final(eng, "job[1]")
        check("job[1]: a bracket in the job name never exposes the clean cut",
              rc == 0 and read(os.path.join(out, "job[1].mp4")) == "cut" and read(os.path.join(out, "job[1].final.mp4")) == "m", log)

        out = put(eng, "keep-final", [("keep-final.mp4", 0, "cut"), ("keep-final.final.mp4", 10, "first reel"),
                                      ("keep-final-v2.mp4", 20, "second reel")])
        rc, log = name_final(eng, "keep-final")
        backups = sorted(os.listdir(os.path.join(out, "earlier-finals"))) if os.path.isdir(os.path.join(out, "earlier-finals")) else []
        check("an existing final replaced by a newer pass is kept in earlier-finals/",
              rc == 0 and read(os.path.join(out, "keep-final.final.mp4")) == "second reel" and len(backups) == 1
              and read(os.path.join(out, "earlier-finals", backups[0])) == "first reel", f"{backups} {log}")

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        out = put(eng, "look-first", [("look-first.final.mp4", 0, "old reel"), ("other-pass.mp4", 10, "b"),
                                      ("look-first-v2.mp4", 20, "new reel")])
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.path.join(eng, "home"), "LC_ALL": "C"}
        look = subprocess.run(["bash", "scripts/name-final.sh", "look-first"], cwd=eng, env=env,
                              capture_output=True, text=True, encoding="utf-8").stdout
        rc, log = name_final(eng, "look-first")
        said_cleared = "\nCleared\n  other-pass.mp4" in look
        check("the look names a pass as cleared exactly when --apply clears it (a pass between the old final and the new pick)",
              rc == 0 and said_cleared and not os.path.exists(os.path.join(out, "other-pass.mp4")), look + log)

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        with tempfile.TemporaryDirectory() as tmp:
            eng = engine(tmp)
            out = put(eng, "short-bits", [])
            video(os.path.join(out, "short-bits.mp4"), 4)
            video(os.path.join(out, "hook-preview.mp4"), 1)
            put(eng, "short-bits", [("short-bits.mp4", 0, None), ("hook-preview.mp4", 10, None)])
            rc, log = name_final(eng, "short-bits")
            check("a 1-second preview of a 4-second reel is never promoted as the reel",
                  rc == 0 and not os.path.exists(os.path.join(out, "short-bits.final.mp4"))
                  and os.path.exists(os.path.join(out, "hook-preview.mp4")), log)
            video(os.path.join(out, "FULL-REEL.mp4"), 4)
            put(eng, "short-bits", [("FULL-REEL.mp4", 5, None), ("hook-preview.mp4", 10, None)])
            rc, log = name_final(eng, "short-bits")
            check("...and a full-length pass beats a NEWER preview",
                  rc == 0 and os.path.exists(os.path.join(out, "short-bits.final.mp4"))
                  and "FULL-REEL.mp4 becomes short-bits.final.mp4" in log, log)
    else:
        print("  SKIP  the preview-length cases (no ffmpeg/ffprobe on this machine)")

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("all good: name-final picks the reel, keeps every clean cut, and never loses a final")
    return 0


if __name__ == "__main__":
    sys.exit(main())
