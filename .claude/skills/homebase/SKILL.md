---
name: homebase
description: Builds, syncs, or updates the Brand Homebase for the Edit Engine — the guided Q&A that fills brand-kit.md (who she is and who she helps, her voice and rules, her style pack and fonts) so every reel looks and sounds like the creator. Use when the creator says "build my homebase", "start my homebase", "homebase interview", "set up my homebase", "do my homebase", "redo my homebase", "update my homebase", "sync my homebase", "pull in my homebase", or during first-run setup. Claude finds any Homebase she made in another Startup Mom product or another copy of this engine, and asks whether it is the same brand before reusing her voice + identity, so a second engine for a client or another business never wears the first brand's words. This is Step 1 of the whole system. Same command as the Content Crafting Engine's homebase; here it fills the Edit Engine's brand-kit.
---

# Homebase — the Brand Homebase interview (Edit Engine)

The Homebase is the foundation the whole Edit Engine reads from. It lives in **`brand-kit.md`** and drives
your captions' voice, on-screen copy, colors, and fonts. This skill runs the interview that fills it — warm,
one question at a time, about ten to fifteen minutes.

**Trigger command (teach this in the course):** the creator just says **"build my homebase."** Same command
as the Content Crafting Engine, so a bundle creator uses one phrase across both.

## Step 0 — Look for another Homebase, then ASK before using any of it (search SILENTLY, never copy silently)
She may own other Startup Mom products, or a second copy of this engine for a different brand, another business
or a client. So you search her computer before any question (she never hunts for a file), but **nothing comes into
this engine until she says it's the same brand.** Pulling another brand's voice in without asking would make this
engine sound like someone else.

**Already filled in here?** If `brand-kit.md` Part A has no blank `{{...}}` / `<<...>>` fields left, this is an
update, not a new build: work from what's there and skip the search, unless she said "sync my homebase".

**Search (silently):**
```bash
find .. ~ -maxdepth 5 \( -name Library -o -name node_modules -o -name .Trash -o -name worktrees -o -name dist -o -name releases \) -prune -o \( -name 'brand-homebase.md' -o -name 'voice-dna.md' -o -name 'brand-kit.md' \) -print 2>/dev/null
```
- **Another Reels Editing Engine** → its `brand-kit.md` (a second engine for another brand counts).
- **Another Startup Mom product** → `voice-dna.md` + `backbone/*.md` (her voice + identity + offer).
- **Brand Deal Studio** → `brand-homebase.md`.

Then tidy the list: resolve each to its full path and drop duplicates; drop THIS engine's own `brand-kit.md`;
drop any file whose identity and voice are still blank `{{...}}` / `<<...>>` fields (an unfinished template is
not a Homebase); drop any path listed in this engine's `brand-kit.md` line
`<!-- homebase-kept-separate: ... -->` (she already said those are a different brand), unless she names that one
now. Read just enough of each to name it: the brand, her @handle, the folder it sits in. Several files for the same
@handle are one Homebase; keep the newest (by its "Last updated" header, else file date).

**Product-name rule (never reveal an unreleased name):** the product names above are INTERNAL, used only to find
her files. The **AI Content Crafting Engine**'s creator-facing name has not been announced yet (that product is not
live), so **NEVER say it to the creator.** In anything she reads or hears, call it **"another Startup Mom
product."** (Brand Deal Studio and the Reels Editing Engine are public, so naming them is fine.) Say a folder by its
name and where it sits ("reels-2, in Documents"), never a full path.

**If you find one, ask as a CLICKABLE pick-one (she taps, does not type), everything inside the question:**
"I found another Homebase on your computer, for **@handle** (Brand Name), in your **reels-2** folder. Is this
engine for the same brand?"
- **Same brand, use it** — your voice and brand details come over, so you don't answer them twice.
- **A different brand or business** — keep this one separate. I'll set it up fresh, and nothing comes over from
  the other one.
- **Not sure, show me what's in it** — then show its brand, who it helps and how it sounds in plain words, and ask
  again with the first two options.

**Found more than one?** One option per Homebase ("**@handle** (Brand Name), same brand, use it"), then
**None of these, it's a different brand or business**, then **Not sure, show me what's in them**.

**She picks same brand:** copy her **voice + identity** from that one Homebase into `brand-kit.md` Part A (Voice
DNA → section 2, How you sound; audience/offer → section 1, You and your people). Never mix in a second Homebase.
Copy only; never write anything into the folder it came from. Tell her in one line: "If you change your voice
in one of them later, just say **sync my homebase** in the other to bring it across." If a synced field is thin and
you truly need more, OFFER the easy path first ("want me to pull it from your Instagram, or would you rather tell
me?") rather than making her write it out cold. **Only ask fresh for the two Edit-specific pieces** (which style
pack she wants, and whether her reels lean teaching or confessional); never re-ask the voice questions she already
answered.

**She picks a different brand or business:** read nothing from those files. Add one line at the very end of
`brand-kit.md`: `<!-- homebase-kept-separate: <full path>; <full path> -->` (so "update my homebase" never asks
again about the same ones), then run the full interview below as this new brand. When it asks her name and
Instagram, she answers as this brand.

**If you find nothing:** run the full interview below from scratch. (A Content-only creator who never installed
this engine simply won't reach this skill.)

## Voice (hold this the whole way)
Big sister across the table. Warm, plain words, short sentences, lead with hope. No
guru talk. Reassure often: no wrong answers, she can't break anything, she can redo any part later.

## What you're filling — `brand-kit.md` Part A
Write her answers into `brand-kit.md` (never make her touch it). Fill every blank `{{...}}` field (an older
copy's kit may still show them as `<<...>>`):
- **Identity** (section 1) — name / brand, niche (who she helps + the outcome), handles (just her @handle). **Do NOT
  pull or ask for her follower count.** It plays no part in building reels, so never run a profile/stats pull
  here. Her handle alone is all this needs.
- **Voice & tone** (section 2; her hard rules go in section 3) — how her captions should sound. **Protect this, and OFFER THE EASY PATH FIRST — do not
  default to copy/paste.** This is where the Instagram pull pays off, so present it as a **CLICKABLE
  multiple-choice** (the pick-one selector, not a typed request), two options:
  - **Pull from my Instagram (Recommended)** — I read a few of your recent captions automatically.
  - **I'll paste a few examples** — you give me 3–5 things you've written.
  - **If Instagram (the easy path):** if Apify is already connected (she did it in setup, or in another
    Startup Mom product), just use it. If she deferred it in setup, THIS is the moment it earns its keep, so
    warmly connect it now the same quick way — help her make a free Apify account, then `/mcp` → add Apify
    (`https://mcp.apify.com`) → connect, pasting her own Personal API token if asked (Settings > Integrations
    > API tokens). Reassure her it's free ($5 of monthly credit covers this, the pull costs pennies). Then
    pull her recent captions with the Apify Instagram scraper against her handle. If she'd rather not connect
    it after all, no pressure — fall straight to paste. **Reassure her on cost, clearly:** show that it runs
    a quick Apify pull (a few cents of Apify
    credit) BUT that Apify includes free monthly credits that cover it, so it costs her nothing. Say it like:
    *"This runs a quick Apify pull, about 2-5 cents of Apify credit, and it's covered by Apify's free monthly
    credits, so it won't cost you anything."* (scraping use apify — state the run, but make the free
    credits the headline so she never worries about a charge.) Then derive the voice patterns FROM those real
    captions and confirm them with her. She barely has to type.
  - **If paste:** she gives 3–5 real things she's written. (Same as before — still fine, just no longer the
    only option.)
  - **Either way, mine the samples WITH her** into concrete patterns, not adjectives. Include her hard rules
    (e.g. "no em dashes") and voice DNA (recurring phrases, how she opens/closes).
- **Your look — pick ONE style pack. This is the only visual question. Do NOT ask for a separate accent
  color or a palette.** Each pack ships with its own fonts AND its own color palette, so choosing a pack
  sets her whole look in one step. **Present this as a CLICKABLE multiple-choice prompt she taps — the
  pick-one selector (the AskUserQuestion / clickable-options UI), the SAME way Brand Deal Studio does it —
  NOT a plain bulleted list she has to read and type a reply to.** Put **Butter FIRST and label it
  "(Recommended)"** so the recommended choice is obvious. The three options, each with its one-line
  description:
  - **Butter (Recommended) — all free.** Soft and clean. Works on free CapCut. Nothing extra to buy.
  - **Editorial** — classic. Uses a couple of CapCut Pro fonts.
  - **Playful** — bold. Uses a couple of CapCut Pro fonts.
  (These same three go in the clickable prompt's options, in this order.) Say plainly which need CapCut Pro
  so there is no surprise later. **When she picks, reflect the look back to her in one warm line so the
  choice feels like a little win, not a form field** (e.g. "Butter it is. Soft, clean, a touch editorial.
  That one tap just set your whole look, fonts and colors together."). Then lock the chosen pack (its fonts
  and its palette) by saving it as her default, which every build route and the visual editor open in:
  `python3 -c "import sys; sys.path.insert(0, 'product'); import cleanyap; cleanyap.set_default_pack('<Pack>')"`.
  Then move on. The pack's own palette (`product/creative-vault/style-packs.json`) IS her color
  look — there is no separate color step and she never types a hex, so onboarding completes from the pack
  alone. **Reassure her in one line:** she can fine-tune fonts or colors anytime later by
  saying **"let's customize my style pack."** Keeping this tight is how she gets a great first reel fast, so
  do not open a colors conversation now.
  - **AFTER she locks a pack, check that pack's CapCut fonts.** Editorial and Playful use CapCut Pro fonts;
    **Butter's main text (Inter) is bundled and instant, and its one accent font, Bloop, is FREE** and just
    needs the same one-time first-use as any pack font. **The timing is flexible and both are fine:** a free
    accent like Bloop can set up here at pack-selection OR the first time it actually appears at build. Either
    way, present it the SAME intentional way (below), never a backtrack. Run `python3
    product/capcut_font_doctor.py <HerPack>` (her pack only, never all packs — checking packs she did not pick
    is exactly the confusing, mistimed prompt to avoid). If a font shows **"not downloaded to CapCut yet,"**
    that is NORMAL and NOT an error, and it is **NOT a mistake, a backtrack, or a surprise:** these fonts live in CapCut's cloud and only save to your computer the first time you actually
    use one, so the fix is a one-time, one-minute thing she does once. **RECOMMEND she do the one-minute setup
    NOW — do NOT recommend skipping.** A stand-in font means her finished reel won't have her pack's real look,
    and this is her first reel, so the right nudge is to get it right. Keep it **short and delightful**, and
    name HER pack's font(s) (**Butter uses Bloop, which is free**; Editorial uses **Prosecco and Baguette**;
    Playful uses **Soup Du Jour** and **Ugly Dave**).
    **"Prosecco and Baguette" is ONE font, not two.** That whole phrase is the typeface's real family
    name, which is a strange name for one font and reads like a list. A tester went looking for a
    second font called Baguette and thought she had missed a download. Say "one font, that is
    genuinely its name" when you name it, so nobody goes hunting.
    **CapCut search-name (critical):** in CapCut's font search, **Soup Du Jour is listed as "Solid"** — so
    tell a Playful creator to search **solid** in the CapCut font panel, NOT "Soup Du Jour," or she won't find
    it. (Prosecco and Baguette and Ugly Dave search by their own names.) Say
    something like:
    > "Ooh, this is your first time ever using [font name]. So fun. Let's get CapCut to find it. Just open
    > CapCut and use [font name] once (new project, drop in a text box, pick it from the font list, type a
    > couple words), then close CapCut. That's it. This engine will be able to use it forever."
    Then present it as a **CLICKABLE pick-one she taps, recommended option FIRST:**
    - **Set up my font now (Recommended)** — the one-minute step above, so your reel gets your pack's exact look.
    - **Use a stand-in for now** — I'll build with a clean fill-in font this time. Your reel won't have the
      pack's real font until you do that quick step.
    Lead with doing it now; only fall back to the stand-in if she taps it. **Never show a red ✗ or the word "missing" for a pack font** — it is a one-time
    setup step, not a failure. See `product/capcut_font_doctor.py` (reframed) and `stylepack.delivery_font_note`.
  - **🔴 NEVER frame an uncached pack font as a mistake, a backtrack, or a licensing surprise.** Do NOT say
    "sorry, that was my mistake," "not bundled free like I told you at setup," or call a font "licensed" or
    imply it costs money. Every time a pack font is not cached yet — whether here, or later at build time —
    it is the SAME simple, positive, first-time-use step: "Looks like this is your first time using [font].
    Let's set it up now (or use a stand-in). It's really simple: start a new project, add a text layer, use
    [font] once, and I'll be able to find it and build with it." **Bloop (Butter's accent font) is FREE — a
    free CapCut font, no Pro, nothing to buy.** Because Butter is now checked up front (above), Bloop is
    handled at pack-selection and never comes back later as an apology.
- **Reel style — a CLICKABLE multiple-choice, no jargon.** Ask what her reels are usually like, and present
  it as the pick-one selector she taps (never a prose question), with these options:
  - **Teaching / how-tos** — tips, lessons, walking people through something.
  - **Confessional / personal** — honest, sitting in a real feeling, telling a story.
  - **B-roll or voiceover reels** — faceless: footage or a voiceover, not you on camera talking.
  - **Other** — let her type what she usually makes (the clickable prompt's built-in "Other" free-text).
  Keep every label plain. Do NOT quote internal rules or on-screen-copy mechanics at her (e.g. "never mirror
  the spoken line") — she will not know what those mean, and they are not hers to carry. Her answer is a
  DEFAULT/hint, not a lock: the register (teaching vs confessional) is still confirmed per reel at build
  time, and picking "b-roll / voiceover" just tells you her usual format so you can steer to those flows.

## How to run it (one question at a time, conversational)
Ask ONE question, wait, reflect it back so she feels heard, then move on. Never dump the whole list. If an
answer is thin, one gentle follow-up, then move on.

**Every OPEN question comes WITH a good pretyped example she can copy or tweak — never leave her facing a
blank box.** Having an example to react to is the single biggest thing that keeps a beginner from freezing.
So on anything she has to TYPE an answer to (her niche, her voice samples, a "type your own / Other" option,
any freeform field), put a warm, on-brand EXAMPLE answer right there, on its own line so she can grab it, and
invite her to use it or make it hers.

**The example must be about a MADE-UP creator in a niche that is not the engine author's and not the creator's real data.**
This matters: she is building HER brand, not a copy of anyone else's. So never offer the engine author's
own niche, signature phrases, or voice DNA as the starting point, and never reuse a phrase you have seen in
this engine's own docs or sample frames as her example. The WRAPPER around the example stays warm and
in your voice; the example CONTENT belongs to an invented creator. **Rotate the niche from question to
question** so no single world dominates the interview. A working set to pull from, and feel free to invent
others: sourdough baking, dog training, bookkeeping for freelancers, running after an injury, ceramics,
thrift flipping, houseplants, budget travel, teaching guitar. Where a question has real room for
interpretation, give **two or three** examples from different niches rather than one, so she sees the shape
instead of a script to copy.

For instance, the niche question:
> "Who do you help, and what do they walk away with? Here are a few shapes you could borrow and tweak:
> *I help first-time owners of a reactive dog get through the first ninety days.* Or *I help freelancers
> stop dreading their own bookkeeping.* Or *I help beginner bakers finally get an open crumb.* Yours, in
> your own words."

## The gut-check for voice
Every voice pattern you record should pass: *"Would she actually text this to a friend?"* If not, it's not her.

## Finish
- **Do not finish while `brand-kit.md` still has any blank `{{...}}` or `<<...>>` field.** If she's low on energy,
  save what you have and tell her exactly what's left.
- When it's full, apply it per `brand-kit.md` Part B (voice and rules into CLAUDE.md, her pack saved as the default, etc.),
  then confirm warmly: "That's your Homebase. Every reel now looks and sounds like you." Offer a tiny win:
  "want to run one real clip through so you can see your look?"
- **Last, one warm line about what to do if something ever glitches (NOT a question, no opt-in, no
  consent prompt).** Nothing is auto-sent anywhere, ever. If a real problem comes up, Claude fixes it right
  there; only something the engine cannot fix, and that other creators would hit too, becomes a report she
  emails (the `report-a-problem` send test). Just set the expectation kindly so a future glitch never feels scary:
  > "and if anything ever acts up on you, don't worry. Just say 'something glitched' and I'll look at what
  > your computer is telling me and fix it with you. Nothing is ever sent without you."
  (More detail lives in the course FAQ, "What do I do if there's a glitch?") Do NOT ask a yes/no here and do
  NOT write any consent file — the old opt-in auto-report was removed because a reliable background send
  can't be promised, and offering it would be a false sense of security. See `product/make-handoff.py`.

## Rules
- ONE question at a time. Reflect back. No form-dumping.
- **Every open (typed) question comes WITH a pretyped example she can copy or adapt.** Never a blank box. The example is always an INVENTED creator in a niche that is not the engine author's, rotated question to question, and two or three of them where the question is open-ended. Never hand her the engine author's niche, signature phrases, or voice lines as the starting point (see "How to run it").
- **Every either/or choice is a CLICKABLE multiple-choice prompt she taps (the pick-one selector /
  AskUserQuestion UI), the SAME as Brand Deal Studio — NEVER a bulleted list she has to type a reply to.**
  This covers the style pack, the voice source (Apify pull vs paste), and teaching vs confessional. Mark the
  recommended option **"(Recommended)"** and put it first (e.g. Butter for the style pack). A plain prose
  list for a real choice is the exact thing to avoid. (The old bug-report opt-in question was removed — the
  glitch note at the end of Finish is a plain reassurance, not a choice.)
- **What she reacts to goes INSIDE the choice, never above it.** The Claude app hides text written right before a choice box, so her three rules, her voice examples or a draft shown just above the box never reach her: she sees only the short question and cannot tell what she is agreeing to. Put the content in the question itself (and in each option's description), short enough to read there. If it is too long for the box, show it in a plain message and ask in plain text at the very end of that message, with no choice box after it; she answers in her own words.
- Voice always comes from REAL samples, never invented. Offer to pull her recent Instagram captions via
  Apify FIRST (it's connected by now), or she pastes a few. Mine whatever you get WITH her.
- You write the file; she just talks.
- Bundle creator with a Content Homebase already? Reuse the voice/identity, only ask the visual extras.
- **"Update my homebase"** redoes any part she names. When she has edited `brand-kit.md` by hand instead, it
  writes her Part A into the places Part B lists, without re-asking anything already filled.
- This is Step 1 — nothing looks or sounds like her until `brand-kit.md` is filled.
