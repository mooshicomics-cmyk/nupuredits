---
name: broll-reels
description: Turn a folder of the creator's OWN filmed b-roll into finished, post-ready text-over-b-roll REACH reels — organized, hooked, and baked with their chosen style pack's fonts + color (headline + accent turn). NO AI footage generation (that is the Content Crafting Engine's Higgsfield side). Use when the creator says "make b-roll reels", "turn my b-roll into reels", "make reels from my footage", "hook my b-roll", "broll reels", or points at a folder of clips they filmed. Runs the whole pipeline, in order. Ask their style, label/organize the clips, workshop niche-fit hooks WITH the creator (approve before baking), sample one reel for her yes, bake the rest, output a numbered posting queue with captions.
user-invocable: true
argument-hint: "[path to the folder of filmed b-roll clips]"
---

# B-Roll Reels — the builder (bring your own footage)

Take a folder of the creator's **own filmed b-roll** and turn it into finished **text-over-b-roll REACH reels**: her hook baked into the negative space, a numbered posting queue with captions ready to paste. **No filming and NO AI generation here** — the footage is hers. (The Content Crafting Engine's `ai-broll` skill is the AI-avatar version that *generates* footage; this skill only *dresses* footage the creator already shot.)

> This is the EDIT ENGINE. It owns pixels. This skill = organize footage → workshop hooks WITH the creator (she approves) → bake text → package for posting. Posting stays manual.

## Inputs
- **The creator's EXISTING filmed b-roll** (mp4/mov), the footage they already shot — vertical 9:16, ~5s each, framed with negative space for text. **Default source = the repo-root `inbox/` folder**, the same drop spot the rest of the engine uses. The creator drops their b-roll clips into `inbox/` (a batch, not one clip), then says "make b-roll reels" — the skill takes **all** the clips there as the batch. Also accepts a pointed folder path (e.g. `~/Downloads/my-broll`). **Where to look, in order:** `inbox/b-roll/grabs/` (prepped clips), then `inbox/b-roll/` (the creator's b-roll folder), then a pointed folder, then loose clips in `inbox/`. **If there is a `grabs/` folder from b-roll prep** (`inbox/b-roll/grabs/` or `<pointed folder>/grabs/`, made by the `broll-prep` skill), the batch is the grabs ONLY, never the long originals beside them. Long unprepped footage (clips well over ~15s) with no `grabs/` yet: offer to run `broll-prep` first ("these are long, want me to chop them into the best 6-second moments first?"). If `inbox/` is empty and no path is given, say so warmly and tell them to drop clips in. **This skill never asks them to film anything and never generates footage** — it uses what they already have.

## The flow
The tools live in the shipped skill (`tools/`) and are always referenced by their own path; the creator's
clips + all per-run data live in a **working folder** you create for the batch, **named by its content, never a date** (e.g. `projects/broll-laundry-flowers-crepes/`) — the same job-naming rule as the rest of the engine (`CLAUDE.md`: name a job by what's in it, never a date).
Every data tool takes that working folder as its argument (or run from inside it). Creator footage never lands
in the skill.

0. **Pick the style (ask first).** Before baking anything, ask the creator: *"Do you have a specific style you want to match, or should I use one of your style packs?"* Show the real options with `python3 tools/resolve-pack.py --list` (don't hardcode a pack list). Packs whose fonts come from CapCut print as **"<Pack> (CapCut Pro required)"** — those display fonts live in the creator's CapCut and CapCut Pro carries them, so a creator on the free plan won't have them (call this out when they pick one). Their pack resolves to its **headline font + accent font + hook color** (see **Style pack** below). There is no default — a pack must be resolved first.
1. **Organize + label.** Make a working folder `$WORK` for this batch, **named by its content, never a date** (e.g. `projects/broll-laundry-flowers-crepes/`) — same rule as every other job folder. Take the clips from `inbox/` (or the pointed folder) and **copy** them into `$WORK/clips/` — never move or touch the originals in `inbox/`, same rule as the rest of the engine. Scan each clip (first-frame preview) and rename by scene into `$WORK/clips/reel-NN-<scene>.mp4` (e.g. `reel-03-couch-laptop.mp4`). Keep a `$WORK/stills/` frame per clip for static/carousel use. Sort out the strong candidates using `reference/clip-selection.md`.
2. **Hooks — do this WITH the creator, and get a yes BEFORE anything bakes (approval gate).** The clip batching is automatic; the hooks are not. The creator is the creator, so the words on her reels are a decision she makes with you, never a batch you hand her finished. Read **Hooks** below first (the 8 proven structures and the craft standard). Then run this small workshop:
   - **Write the hooks in HER language.** These are the words on her reels. If she is speaking or
     writing to you in something other than English, or her brand kit is, draft in that language and
     say so. Your default is English and hers may not be. (See the on-screen-language rule in `CLAUDE.md`.)
   - **a. Ask first, and invite inspiration:** *"Do you already have hooks in mind for these, or want to workshop a few together? Either way, if there are hooks, captions, or reels you love, paste them in (your own words or links) and I'll pull them in as inspiration so these sound like you."* Wait for the answer. Do NOT write the map or bake before this.
     - **Why this matters:** the Brand Homebase gives a real starting point on her voice, but it is NOT deep enough to nail her voice on its own. So a first draft is a *starting point that needs her*, never a finished read on how she sounds. The workshop and any inspiration she pastes are how the voice actually gets dialed. Say this plainly if she seems to expect finished hooks: "This first pass gets us close. You'll shape it so it sounds like you."
     - **If she pastes inspiration:** pasted TEXT (hooks/captions she likes) → study it directly. Pasted REEL LINKS → pull the on-screen hook + caption with the engine's reference-reel tooling and study those. **Borrow the FORMAT and voice, never the concept or exact words** (same rule as `/studio inspo`). Fold what you learn into the drafts.
   - **a2. Offer real hook research (Apify), every time:** *"Want me to look at what's actually working first? I can start with your own Instagram and see which of your past hooks did best, and I can also pull top reels from 2 or 3 creators in your niche."* Two sources, offer both, do her own account first:
     - **Her own Instagram (start here).** Her handle is in `brand-kit.md` / the Brand Homebase; if it's missing, ask. Her best past reels show the hooks her audience already responds to AND her existing content strategy (her topics, her pillars, how she talks), so new hooks extend what works instead of starting over. Draft some hooks that re-angle her proven winners onto these clips.
     - **Creators in her niche.** She names 2 or 3 (or you suggest some and she confirms).
     Then:
     1. **State the cost before you run it** (a few cents on her own Apify key, BYOK, same key as `reference-reel`). No key connected: tell her to connect it and write from the frameworks meanwhile.
     2. Pull each account's recent reels with `apify/instagram-reel-scraper` (by username, about 30 each; about 50 for her own account), rank by views relative to that account's own median (so one big account doesn't swamp the rest), keep the top 10 to 15 per source.
     3. **Read the hook ON SCREEN**, not just the caption: look at each top reel's cover/first frame image from the scrape. The words baked on the video are the hook a text-over-b-roll reel is copying the shape of. Use the caption's first line as a fallback.
     4. Show her a short list: the hook SHAPES that keep winning (e.g. "POV: [specific scene]", "The [thing] nobody tells you about [topic]"), each with one of her own drafts in that shape. **Borrow the shape, never the words or the idea.** Never name the creators in anything that gets baked or posted.
     These drafts feed step c; she still approves every hook.
   - **b. If she HAS hooks:** use hers. Offer, don't impose, a light tighten to the craft standard ("want me to sharpen any of these, or use them as is?"). Confirm the final set, then go to step 3.
   - **c. If she wants to workshop (or is not sure):** draft about **5** strong starter hooks to her niche in varied formats (a POV, a statement, a question, a confessional, a proof/list), pulling in any inspiration she pasted, and show them as a short numbered list for her to react to. Offer more if she wants a wider range ("want a few more angles to pick from?"). Present them as a first pass, not a finished voice read. **Refine together:** she keeps the ones that land, redirects the tone or angle on the rest, and you rework until she approves a handful that sound like her. Those set the voice for the batch.
   - **d. Then generate the rest to fill the batch:** once she has approved the direction, generate however many more hooks the batch needs (one per clip, so total = clip count), matching the approved voice and mixing formats. Show the full set mapped clip → hook for a final quick yes.
   - **e. Only on her yes:** map one built-out hook + optional accent turn to each clip in `$WORK/HOOK-MAP.tsv` (cols: `clip⇥hook⇥aside⇥keyword⇥pos`; `-` = no aside). Write to the **creator's niche** (baker, music teacher, home designer, coach, whatever their Brand Homebase says — her world, not any other). **Never bake a hook she has not seen and approved.**
3. **Sample ONE first, then the batch (approval gate).** Never bake the whole batch blind. Write the full
   `HOOK-MAP.tsv`, then bake a single sample: put the header + ONE row in a temp map, run the bake on it,
   and show her that one finished reel (open it). She checks font, placement, text length, the accent turn.
   Adjust (pack, `--pos`, hook wording) and re-sample until she says it looks right. Only then run the full
   bake below. `build-all.sh` skips anything already in `clips-final/`, so delete the sample's FINAL first if
   anything about the look changed, or keep it if she approved it as is.
   Say it plainly: *"Here's one. If you like this format, I'll run the rest exactly like it."*
4. **Bake the text** — `PACK=<name> tools/build-all.sh "$WORK"` reads `$WORK/HOOK-MAP.tsv` and bakes every clip to `$WORK/clips-final/<clip>-FINAL.mp4` using `tools/bake-hook.py`, in the resolved pack's fonts + color (see below).
5. **Package** — copy `tools/captions.py` into `$WORK/`, fill it per batch (caption bodies in the creator's voice, CTA per keyword, niche hashtags), then `python3 tools/build-posts.py "$WORK"` writes numbered `$WORK/POST/NN-<clip>.mp4` (trial order) + a paste-ready `$WORK/POST/NN-<clip>.txt` caption + `$WORK/POST-THESE.md`. **Deliver so she never hunts for it:** print the ABSOLUTE path to `$WORK/POST/`, give her a clickable `open "<absolute path>"` in its OWN fenced shell block (Claude Code renders a Run button on it), AND actually run `open "$WORK/POST"` so Finder opens right to the finished reels.
6. **Curate** — creator deletes reels they don't like from `$WORK/clips-final/`, then `tools/reconcile.sh "$WORK"` renumbers cleanly.

## Style pack (drives the text look — ask before baking)
This is a native Edit Engine feature: it uses the **same style packs as the rest of the engine**, read straight from `product/creative-vault/style-packs.json`. The pack sets the fonts + color; the baking *formula* (fit, wrap, placement, finish) never changes.
- **Turnkey resolve.** `python3 tools/resolve-pack.py <Pack>` reads the engine's `style-packs.json` and emits that pack's headline font + accent/subhead font + hook color. `python3 tools/resolve-pack.py --list` shows the packs the engine actually defines (ask the resolver, don't hardcode a pack list). Nothing is bundled or duplicated in this skill.
- **Two ways to run the bake:**
  - By pack name (turnkey): `PACK=Butter tools/build-all.sh "$WORK"` — it calls `resolve-pack.py` and sets the fonts for you.
  - Match a specific style outside the packs: set `HEADLINE_FONT` / `ACCENT_FONT` / `TEXT_COLOR` explicitly (from the reference they name or their Brand Homebase).
- **No fonts ship with this skill and there is no default** — a run without a resolved pack errors on purpose. Font licensing is the engine's concern and already handled: restricted display fonts are excluded from ship and the creator resolves them via CapCut, same as every other format.

## The LOCKED text-baking formula (`tools/bake-hook.py`)
Do NOT re-invent the formula. Only the FONTS + COLOR change (per the chosen style pack); the fit / wrap /
placement / finish are locked. Signature:
`python3 tools/bake-hook.py IN.mp4 OUT.mp4 "hook" [--aside "turn"] [--pos top|center|auto] --headline-font PATH [--accent-font PATH] [--color "#hex"]`:
- **Headline** in the pack's **headline font**, **flat solid color** (native Instagram-Edits look). The shadow is **ADAPTIVE, not fixed**: the baker samples the background behind the text and adds a **soft blurred halo only when the ground is bright or busy** (a sunlit window, a light/cluttered scene) so the text stays legible; on a mid-tone or dark ground it stays flat (a shadow there would look over-produced). **Accent turn** (`--aside`) in the pack's **accent font** = the small reframe/payoff below it. Fonts + color come from the creator's style pack via `--headline-font` / `--accent-font` / `--color`. **`--headline-font` is REQUIRED** and there is **no default font** — this skill ships none (see Style pack). Single-font packs may omit `--accent-font` (the turn reuses the headline face).
- **Auto-fit to width** (font scales so the widest line ≈ 80% of frame) + **balanced line-wrap** (equal-width lines; pass plain text, no manual `|`). The turn also wraps + fits.
- **HDR phone footage** (HLG / PQ) is converted to SDR before the text goes on, the same conversion the voiceover builder uses, so white text stays white.
- **IG-safe placement**: never top ~14% (profile/sound UI) or bottom ~20% (caption/actions). **`--pos auto` is the default and preferred**: it samples the subject's face across the whole clip (vendored YuNet detector) and picks top vs center so the text clears the head, and warns on stderr if nothing clears (shorten the hook or re-trim). The face check needs OpenCV; when `python3` has none (setup installs none), it borrows OpenCV through `uv`, and only when neither is there does every hook go to the top, which `build-all.sh` says once. Use an explicit `--pos top|center` only to override. Never cover the face/subject — that is now enforced, not just a note.
- Mild grain + flatten finishing pass folded in (keeps it from reading too HD / too polished).

## Hooks — read the frameworks FIRST (required)
1. **Read `reference/hook-frameworks.md`** — the 8 proven hook structures + the craft standard. This ships with the Edit Engine. NEVER write a hook without reading it.

**Hook craft standard (non-negotiable):** a b-roll hook is BUILT OUT and instantly legible to a stranger, in her brand voice. Do ONE of: name a **specific painful scenario** she recognizes, open a **curiosity loop**, or promise a **concrete payoff** (number / list / how / story). NEVER a soft affirmation ("you're allowed / you can / you don't need X"). Mix formats (some `POV:`, some statement, some question, some confessional). Add the **accent turn** (the pack's accent font) only where a line earns the reframe. On teaching/proof/list hooks, end the turn with a caption-pointer ("here's how...", "5 signs it's you..."). Carry the creator's DIFFERENTIATOR (never a bare category word — the specific thing that sets them apart, from their niche); never martyr framing; write to the creator's niche and audience. Pull voice + differentiator from the creator's **Brand Homebase** (`homebase` skill / `brand-kit.md`). (See `reference/hook-frameworks.md` for the niche-driven detail; the mom examples there are illustration only.)

## Carousel → reel repurpose (bonus play)
If the creator has an existing carousel, slide 1's copy = the reel's on-screen hook, and slides 2-to-end = the caption. The slide format (big statement + small subhead) maps 1:1 to our headline + accent turn.

## Working folder (per run — you create it; creator footage never touches the shipped skill)
```
$WORK/               a per-run folder named by content (e.g. projects/broll-laundry-flowers/), NEVER by date; NOT the skill's tools/
  clips/            raw filmed b-roll, renamed reel-NN-<scene>.mp4
  stills/           one frame per clip (static/carousel posts)
  clips-final/      baked reels (footage + hook text)
  POST/             NN-<scene>.mp4 + NN-<scene>.txt  (the posting queue)
  HOOK-MAP.tsv      clip -> hook/aside/keyword/pos
  captions.py       per-batch caption/CTA/hashtags (copied from tools/captions.py, filled per run)
  POST-THESE.md     master posting sheet
```

## Ship notes
- Self-contained: the baker uses ffmpeg + Pillow, plus OpenCV for the face check (borrowed through `uv` when `python3` has none; the text is always drawn by `python3`'s own Pillow). No Higgsfield, no HyperFrames dependency for the text bake. **No fonts ship** — fonts come from the creator's resolved style pack (licensed brand fonts are never distributed). Keep the skill free of any dependency on `projects/`, a personal footage folder, or a bundled licensed font (the creator brings their own footage; the pack supplies the fonts).
- See `HANDOFF.md` for the full architecture and the small open items for the agent finishing this.
