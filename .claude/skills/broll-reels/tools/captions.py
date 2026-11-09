"""Per-run caption data for build-posts.py. The skill fills these in for each batch.

Keep captions in the buyer's brand voice and niche (pull from their Brand Homebase / brand-kit.md).
Rule: the caption NEVER repeats or spoils the on-screen hook — it creates the reason to watch, then
points to the video / CTA. No fonts, no personal data here; this is text only.

  CAPTIONS  clip name (matches HOOK-MAP.tsv `clip`) -> caption body (no CTA, no hashtags)
  CTA       keyword (HOOK-MAP.tsv `keyword`) -> the call-to-action line for that reel
            (set up whatever funnel the buyer uses — a DM keyword, a link in bio, a comment prompt;
            "DEFAULT" is used when a row's keyword has no specific CTA)
  HASHTAGS  one space-joined string appended to every caption — swap in the buyer's niche tags
"""

CAPTIONS = {
    # "reel-01-scene": "caption body in the buyer's voice, never repeating the on-screen hook",
}

CTA = {
    "DEFAULT": "Comment the keyword and I'll send it your way.",
    # "GUIDE": "Comment GUIDE and I'll DM you the free guide.",
}

# Replace with the buyer's niche hashtags (or pull from their brand-kit). Placeholder, edit per run.
HASHTAGS = "#yourniche #yourtopic #yourcommunity"
