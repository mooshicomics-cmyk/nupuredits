#!/usr/bin/env python3
"""Assemble the post-ready system from the WORKING FOLDER's HOOK-MAP.tsv + captions.py + clips-final/.
Output (all in the working folder):
  POST/NN-<clip>.mp4     numbered reel in trial order (copy of the baked final)
  POST/NN-<clip>.txt     caption ready to paste (body + CTA + hashtags)
  POST-THESE.md          master posting sheet (index + full captions)
Only includes clips whose baked FINAL exists. Idempotent.

USAGE:  build-posts.py [WORKDIR]   (WORKDIR = the buyer's per-run folder; defaults to the current dir)
captions.py is the PER-BATCH caption data: copy tools/captions.py into the working folder and fill it,
so a buyer's captions never live in the shipped skill. If the working folder has no captions.py, the
tools/ template (empty) is used and captions come out blank for you to fill.
"""
import os, shutil, csv, sys

HERE = os.path.dirname(os.path.abspath(__file__))                      # the shipped skill's tools/ dir
WORKDIR = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
# per-batch captions live in the working folder; fall back to the tools/ template if not filled yet
sys.path.insert(0, HERE)          # template fallback
sys.path.insert(0, WORKDIR)       # working folder wins
try:
    from captions import CAPTIONS, CTA
except ImportError:
    CAPTIONS, CTA = {}, {"DEFAULT": ""}
try:
    from captions import HASHTAGS
except ImportError:
    HASHTAGS = "#yourniche #yourtopic #yourcommunity"

FINAL = os.path.join(WORKDIR, "clips-final")
POST = os.path.join(WORKDIR, "POST")
os.makedirs(POST, exist_ok=True)

hookmap = os.path.join(WORKDIR, "HOOK-MAP.tsv")
if not os.path.isfile(hookmap):
    sys.exit(f"build-posts: no HOOK-MAP.tsv in '{WORKDIR}' — is this the buyer's working folder?")

rows = []
with open(hookmap) as f:
    r = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)   # keep quotes literal, matching the bash tools
    header = next(r)
    for row in r:
        if not row or not row[0].strip():
            continue
        clip, hook, aside, keyword, pos = (row + ["", "", "", "", "top"])[:5]
        rows.append((clip, hook, aside, keyword, pos))

lines_md = ["# POST THESE — trial reels, in order\n",
            "Each reel below has a matching file + caption in the `POST/` folder.",
            "To post: open Instagram, pick `NN-<name>.mp4`, paste the caption from `NN-<name>.txt`, "
            "toggle **Trial Reel** on, post. Work top to bottom.\n",
            "On-screen hook is already baked in. Caption never repeats the hook. The CTA keyword maps "
            "to whatever funnel the buyer uses (DM keyword, link in bio, comment prompt).\n",
            "| # | file | on-screen hook | CTA | keyword |",
            "|---|------|----------------|-----|---------|"]

n = 0
made = 0
for clip, hook, aside, keyword, pos in rows:
    final = os.path.join(FINAL, f"{clip}-FINAL.mp4")
    if not os.path.exists(final):
        continue
    n += 1
    num = f"{n:02d}"
    # copy numbered reel
    shutil.copy(final, os.path.join(POST, f"{num}-{clip}.mp4"))
    # caption file
    body = CAPTIONS.get(clip, "").strip()
    cta = CTA.get(keyword, CTA.get("DEFAULT", ""))
    caption = f"{body}\n\n{cta}\n\n{HASHTAGS}\n"
    with open(os.path.join(POST, f"{num}-{clip}.txt"), "w") as cf:
        cf.write(caption)
    made += 1
    hook_disp = hook.replace("|", " ")
    aside_disp = f" + “{aside}”" if aside not in ("-", "") else ""
    lines_md.append(f"| {num} | {num}-{clip}.mp4 | {hook_disp}{aside_disp} | {body[:60]}... | {keyword} |")

# full captions section
lines_md.append("\n---\n\n## Full captions (copy-paste)\n")
n = 0
for clip, hook, aside, keyword, pos in rows:
    if not os.path.exists(os.path.join(FINAL, f"{clip}-FINAL.mp4")):
        continue
    n += 1
    num = f"{n:02d}"
    body = CAPTIONS.get(clip, "").strip()
    cta = CTA.get(keyword, CTA.get("DEFAULT", ""))
    hook_disp = hook.replace("|", " ")
    aside_disp = f"  ({aside})" if aside not in ("-", "") else ""
    lines_md.append(f"### {num} · {clip}")
    lines_md.append(f"**On screen:** {hook_disp}{aside_disp}")
    lines_md.append("")
    lines_md.append("```")
    lines_md.append(f"{body}\n\n{cta}\n\n{HASHTAGS}")
    lines_md.append("```")
    lines_md.append("")

with open(os.path.join(WORKDIR, "POST-THESE.md"), "w") as mf:
    mf.write("\n".join(lines_md))

print(f"posting system built: {made} reels + captions in {POST}, index in POST-THESE.md")
