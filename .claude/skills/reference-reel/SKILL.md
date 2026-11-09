---
name: reference-reel
description: Pull an inspo Instagram Reel / TikTok BY LINK via Apify (the creator's own key, BYOK), download the actual video + audio, and analyze its editing STYLE — cut cadence, hook-burst pacing, rhythm, caption/animation feel — then use that to inform the creator's own edit. Use when the creator pastes a reel/TikTok link, or says "reference this reel", "study this reel", "match this style", "edit like this reel", "what's this reel's editing style", "recreate this pacing", "analyze this reel's edit". Research capability, shared with the Content Crafting Engine. NEVER open Instagram in the in-app browser to "watch" it (it login-walls) — always pull it via Apify.
---

# Reference a reel — study an inspo edit, then make it yours

Takes "I love how this reel is edited" and turns it into a real style read you can build from. You pull the
reel by link, read its editing fingerprint, then carry that pacing and energy into the creator's OWN reel.
Their footage. Their voice. **We study the FORMAT, never copy the concept.**

## BYOK — the creator's own Apify key
This runs on **Apify** — the same research tool the Content Crafting Engine uses, one capability shared across
both engines. The creator plugs in their **own free Apify key** at setup. The free tier (~$5/mo credit) covers
normal use, and each pull costs pennies. Public data only, no Instagram login. If no key is connected, tell them to connect it
(same key as the content side) and continue.

> 🚫 **NEVER use the in-app browser to "watch" Instagram** — it login-walls and shows nothing. Always pull
> the video via Apify. (This is the capability I habitually forget — don't.)

## Flow (what you do)
1. **Pull the reel by link via Apify** — the public post URL → download the actual **video + audio** into
   `projects/<job>/references/` (name it neutrally, e.g. `ref-001.mp4`). Public data only.
2. **Fingerprint the edit:** `python3 product/reel-fingerprint.py projects/<job>/references/ref-001.mp4 --json`
   → prints the **editing fingerprint**: cut cadence (cuts/sec), hook-burst pattern (rapid opener cuts),
   rhythm shape, and source-music BPM (BPM needs `librosa`; without it the rest still works).
3. **Read the visual style too:** ffmpeg a contact sheet + listen — note caption style, animation feel,
   font energy, zoom/motion habits, where the hook lands.
4. **Translate it into a plan for THEIR reel** — "this one cuts fast for the first 2 seconds then settles,
   captions are big single words, punchy zoom on the hook." Apply that pacing/energy to the creator's own
   footage + words. Never their footage, never their identity.

## Analyze-only vs build-from
- **Analyze-only:** just report the style read (great for "why does this one work / what's the pattern").
- **Build-from:** feed the fingerprint into the creator's own reel build (cut cadence, hook-burst, caption
  energy) so their reel carries the same *rhythm* with their *content*.

## Rules
- Public data only, via Apify (BYOK). Never log in, never scrape private accounts.
- Study the FORMAT (pacing, structure, caption energy), NEVER the concept/words. The creator's story is theirs.
- Reference clips + any source ledger stay local and neutral-coded; never name the original creator in
  anything that ships or gets posted.
- Same research capability lives in the Content Crafting Engine (`decode` / `research-ig-inspo`); here it feeds the EDIT.
