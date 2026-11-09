# 🏡 Your Homebase: what every reel is edited from

<!-- SETUP CHECK: every blank below is a fill-in field wrapped in double curly braces, and the engine calls an
     install "fresh" while any of those (or a field in the older double-angle-bracket form) is left. So never
     type either mark in prose or notes in this file, or a finished kit will still read as "not set up." -->

This is your **Brand Homebase**, kept where the engine can read it: who your reels are for, how you sound,
the rules your copy keeps, and the few defaults that make an edit yours. Every hook, thought bubble and card
the engine writes for you start here.

**The easy way is to talk, not type.** Say **"build my homebase"** and Claude asks one question at a time,
writes your answers in here and applies them. Already built a Homebase in another Startup Mom product? Say
**"sync my homebase"** and it asks whether this is the same brand before pulling it in. Rather do it by hand? Replace every field in double curly
braces with your own words, then say **"update my homebase"**. Part B says where each answer goes.

Recommended, never required. While a field is still blank, Claude suggests setting this up when a session
starts, and edits whatever you ask for regardless: a reel builds as soon as you have picked a style pack.
Until you fill this in, your reels carry no personal voice (never anyone else's), and no field text ever
reaches the screen.

---

# Part A — your Homebase

Six short sections, filled by the interview or by you.

## 1. You, and the people your reels are for

- **You and your brand:** `{{your name, then your brand (yourbrand.com)}}`
- **Who you help, and what they walk away with:** `{{one sentence: who you help and the outcome}}`
- **Where you post:**
  - Instagram: `{{@yourhandle}}`
  - TikTok: `{{@yourhandle, or "none"}}`
  - YouTube Shorts: `{{channel name, or "not used"}}`

> Specific beats broad, every time. "People who keep killing their sourdough starter," "first-time owners
> of a reactive rescue dog," "freelancers who dread their own bookkeeping" and "runners coming back from an
> injury" all give a hook something to aim at. "Busy people" gives it nothing.

## 2. How you sound

The section worth the most care: every word the engine puts on screen is written to it. Describe how you
talk the way a friend would: the energy, how long your sentences run, whether you write in lowercase, how
much slang. Finish with the one question you would ask of any line before you post it.

```
{{two or three lines on how you talk, ending with your gut-check. Three made-up creators, to show the shape:
  · "Calm and exact, like a shop teacher who likes you. Short sentences. No hype words. Gut check: would
    I say this with my hands in the dough?"
  · "Fast, funny, a little chaotic. Lowercase, lots of fragments, one joke per post. Gut check: would
    this make my group chat laugh?"
  · "Warm and unhurried. Plain words, no jargon, never rushed. Gut check: would a nervous beginner feel
    calmer after reading this?"
Now yours, in your own words.}}
```

### Your voice DNA: the lines you actually say (optional, and it pays off)

Three to six real lines lift your copy from "in your style" to "sounds like you." The interview can pull
them from your own Instagram captions.

- `{{a sentence shape you keep coming back to, like "you'd think X. it's actually Y." or "three things nobody tells you about X."}}`
- `{{two or three phrases you really say out loud, like "here's the part nobody mentions," "quick one," "okay so"}}`
- `{{how you tend to finish: "that's it, go try it." / "save this for the weekend." / no sign-off at all}}`

## 3. Your rules

The things your copy never does, checked on every caption, hook and card. Swap the samples for your own.

- `{{a punctuation or formatting rule. One worth having: "No em dashes. Periods and short sentences." It is among the clearest signs a machine wrote the line.}}`
- `{{the words and phrases you never want to see, like "game-changer," "unlock," "level up," "crushing it"}}`
- `{{the line your tone never crosses, like "never imply the viewer is doing it wrong" or "never fake urgency"}}`

## 4. Your reels

Two choices are never stored here, because they belong to each video: whether a reel is **teaching or
confessional** (teaching gets the full graphics, confessional stays almost bare) and **how done** you want
it (raw, medium, well-done or hands-off). Claude asks both, fresh, on every reel.

What does carry over is the opener rule: the first sentence you say predicts the whole reel, so proof and
numbers wait for the middle. The hook card does a different job from your voice and never repeats your
spoken opener. Two small defaults for that card:

- **A hook you reuse on every reel:** `{{your default on-screen hook, or "blank" to write one per reel}}`
  - "blank" is the usual answer. A fixed hook only helps when your reels share one recurring opener.
- **A word you say to close the hook out loud:** `{{that word, like "okay", or "blank"}}`
  - With "blank" the card holds for about 8 seconds and leaves at the sentence break nearest that. One
    reel can set its own moment with `--hook-end`.

## 5. Your look

You never type a color here. Your look is the **style pack** you pick in the interview (Butter, Editorial or
Playful): its fonts, each with its own job (captions, hook, takeover, thoughts), and its palette, chosen in
one tap. Change it later by saying **"let's customize my style pack."** Your captions are set in your pack's
caption font. One font line remains, for the graphics the engine draws before a pack is in play:

- **Headline font** (titles and graphics): `{{a font name, or "Inter" to keep the bundled one}}`
  - Inter ships with the engine, so keeping it means nothing to install. To use your own, add a Regular, a
    Bold and a Black weight of it (`.otf` or `.ttf`) to `assets/fonts/` and write its name here.

## 6. The words the transcriber mishears

The transcriber (WhisperX) gets some names wrong, usually a product or a brand. Write each as
`what it hears → how it is spelled` and your captions come out right every time.

```
{{one per line, e.g.
canva → Canva
yourbrandname → YourBrandName
}}
```

> ⚠️ **One word on the left of each arrow.** Corrections are matched one transcribed word at a time, so
> `canva pro → Canva Pro` can never fire: it arrives as two words. A name heard as several words goes under
> the table's `phrases` instead, or into one job's `projects/<job>/word-fixes.json`.

---

# Part B — how your answers reach a reel

"Build my homebase" ends by doing all of this, and **"update my homebase"** does it again after you edit
Part A by hand. Each answer has one place the engine actually reads, and an update never undoes any of it:

| Your answer | Where it lives | What reads it |
|---|---|---|
| You, who you help, how you sound, your rules | the profile block under **Homebase** in `CLAUDE.md` | Claude, every session: every hook, thought and card is written in that voice and checked against those rules. An update carries the block into the new instructions. |
| Your style pack | your saved default pack, `product/creative-vault/user-style.json` | every build: fonts by job and the palette all resolve from it, and a build with no pack stops and asks instead of guessing. "Let's customize my style pack" saves a NEW pack of yours (`product/pack_write.py`) in a protected copy updates never touch; a shipped pack is never edited in place. |
| Headline font, if not Inter | `presets/type-and-look.md` (its files in `assets/fonts/`) | your own graphics; every update carries it over |
| Hook card defaults | the two hook settings near the top of `presets/clean-captions/build.py` (both ship empty) | the Clean Captions build |
| Words the transcriber mishears | `"words"` in `presets/caption-corrections.json` for a quiet fix; `"check"` for a word that is also a real word, listed on every run so you can check it | the rough cut, when it writes the kept-words transcript your captions come from |
| Logos (no field: just add the files) | `assets/logos/` | anything you place on screen |

The headline font and hook defaults sit inside files the engine ships, so an update saves your values first
(`_local/kept-settings.json`) and puts them back after. Nothing for the reel cover either: the
`cover-thumbnail` skill picks it from your own footage.

**How you'll know it took.** Run one real clip through. Titles should be in your pack's fonts and its accent
color should land on the emphasis word. `./check-setup.sh` confirms the fonts are found.

---

# Part C — Reel style memory (Claude learns your pattern)

You do not fill this in. **Claude does, as you go.** This is how the editor gets more "you" with every reel
instead of starting from scratch each time.

Here is the whole idea, and it is the good part: your editable CapCut draft always comes back **fully
populated** — every caption, sticker, sound, and clip already placed. Your job is just to **nudge the layout
to perfection**: move a word up, resize a sticker, shift a beat, swap a sound. When you have it how you like
it, say the magic sentence:

> **"Learn my pattern for the next reel."**

Claude writes what you changed into the log below (in plain words), and **reads it before building your next
reel** — so next time those choices are already baked in. Each reel needs fewer tweaks than the last. The
more you use the flow, the more it edits like you would.

You can also just tell it a preference out loud anytime — "my captions sit a little higher," "I like the
punch-in zoom on the first line," "keep sound effects lighter" — and say "remember that." Same result.

### How it actually works now

Saying the sentence writes the preference **twice**: the bullet below, in plain language for you, and a
record the builders read on every build (`_local/learned.json`, via `product/learned.py`). The bullet is
what you read; the record is what makes the next reel come out different. Both, every time — a bullet on
its own is a note, not a setting.

Two things you can always do:

- **"/learn list"** — everything you have taught it, with the reel and date each one came from.
- **"/learn forget 3"** — drop one. Do this the moment a reel needs a correction that undoes something you
  taught; a stale preference is worse than none, because you cannot see it working.

Every build prints what it took from this list, so a reel is never quietly different for reasons you cannot
see.

**Some things are deliberately NOT learnable**, and the engine will say so and offer the nearest thing:

- **Teaching vs confessional, and how done you want it** — asked fresh each reel, because they are
  decisions about THAT video.
- **Your hook** — it is written against what the reel is doing, and it must never just repeat your spoken
  opener. A remembered hook is a wrong hook.
- **An exact position on screen** — where you are in frame is measured on YOUR footage every reel. A number
  that sat perfectly above your head in one video lands on your forehead in the next. So "I like my captions
  a little higher" is saved as *which open space to prefer*, and the number still comes from the footage in
  front of it.

### Learned preferences (Claude appends here — leave it empty to start)

```
(empty for now — this fills in as you say "learn my pattern for the next reel")
```

> _For Claude:_ **load the `learn` skill** — it owns this, and it is the only thing that keeps the promise
> above. Saving a preference means writing BOTH halves: `python3 product/learned.py add <field> <value>
> "<her words>"` (what the builders apply, validated and clamped) AND a short plain-language bullet here
> (what she reads). Run `python3 product/learned.py fields` for what is learnable. Scope a preference to the
> register or format it came from unless it is genuinely global. Never delete an earlier bullet; refine it by
> teaching the field again. And never tell her something was learned when only the bullet was written — that
> sentence was said once and was not true of a single build afterwards.
