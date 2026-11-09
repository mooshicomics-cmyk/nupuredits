---
name: graphics-plan
description: "The creative plan, once her rough cut is approved and before the build: decides line by line what her finished script puts on screen. The register sets the load (teaching carries cards, lists and cutaways; confessional keeps the hook card and little else), the lines where she named an effect out loud keep that effect, and every other line stays her face unless it hands the viewer something to see. Each graphic gets a kind, a place and an idea in her style pack. Writes graphics-plan.json (what the build and the CapCut placement read) and graphics-plan.md (what the second pass edits). Plans only, never renders. Triggers: make the creative plan, what's the creative plan, which lines get a card, where do the count-ups go, dress it up with graphics, load up this teaching reel, plan my cards and cutaways."
---

# Graphics Plan: the creative plan, line by line

This is the **creative plan** phase (CLAUDE.md, "From her phone to a finished reel"). The rough cut is approved,
its kept-words transcript is the finished script, and nothing has been built yet. This skill walks that script
line by line and settles what each line gets on screen: her face alone, or a graphic with a kind, a place and an
idea. The build reads the result; the second pass edits it. **It plans and stops:** no rendering, no HTML.

---

## Which road this reel is on

`python3 product/review_route.py <job>`. **`editor`** = she opted into the visual editor for this reel and it stays
there: ask the register only (where it goes is her Finish tab, so never the doneness pick-one), and the plan becomes
looks on her page (`rough-cut`'s "looks": `visual_editor.py place` / `captions` / `looks`), never the widget, a
plan table she approves in the chat, or a CapCut build. The widget builder and the Clean/Super Yap builders refuse
an editor reel on purpose. Only her words switch it back ("the original widget" for this reel; `rough-cut` has the
step). **`widget`** or **`unset`** = the original road below, exactly as before.

## The register comes first

Every later call depends on it, so settle it before reading a single line. If she already answered
*"teaching or confessional?"* (right before her visual editor opened: `python3 product/choices.py read <job>` shows
`register`), use that answer. On autopilot, never ask: read it from her words (`python3 product/choices.py register
<job>` and the kept words) and say which in the final message. Otherwise ask it now as the one pick-one
(CLAUDE.md rule 1). Never default to teaching.

The register picks the plan's `format`, and the format sets how many graphics the reel carries and where they
may sit:

| | **Teaching** → `reel-teaching` | **Confessional** → `reel-clean` |
|---|---|---|
| **What it carries** | The loaded treatment CLAUDE.md names: stat cards and count-ups, checklists and ranked lists, diagrams, b-roll cutaways, a summary card, takeovers. | Hook card, maybe one held word, captions. Never a summary card, never a closing takeaway. |
| **How many** | Visuals carry half the story, so **most beats get one** (roughly half to two-thirds): the hook, every concrete claim, every stat, the payoff. Quality over coverage; the connecting lines stay plain. | **One: the hook card up front.** A second only when a single stat is too big to leave out. |
| **Where** | `open`: the open space around her, read from this job's `subject-zones.json` (`workflows/subject-zones.py`), never over her face. Captions arrive later and keep their own band. | `top`: the hook card alone, inside the safe zone, gone again after ~2–4s. |

If the register leaves the load unclear, ask the one-liner: *"graphics through it, or just the hook card?"*
"Richer" on a confessional is motion and polish, never teaching structure (`product/CAPABILITY-OFFERS.md`).

> **Safe zone:** every graphic's readable content stays inside y `270 → 1620`, read from
> `product/safe_zones.py`, never typed (`workflows/short-form.md`).

---

## Lines where she named the effect keep it

Before planning anything, run `python3 product/spoken_cues.py <job>`. A line where she names an effect and points
at it ("this is a takeover", "here's a count-up to five thousand dollars") already has its answer: that effect,
on that line, with the kind she named. Don't second-guess those. Everything below is for the lines left over.

---

## Which lines carry a graphic

**Her face is the default.** Plain lines give a reel its rhythm, and covering the whole script is the surest
way to get the plan wrong. A line moves off her face only when it hands the viewer something to look at, and
the thing it hands them decides the element. Beat 1 is always the hook and always gets the hook card.

| The line hands the viewer… | She calls it | `element` |
|---|---|---|
| the opening promise (beat 1, always) | the hook card, in her pack's hook job | `word-card` |
| the line worth underlining: the payoff, the punchline | a held word or a takeover | `word-card` |
| one number | a stat card / count-up | `number-card` |
| numbers that move: a ranking, a jump, an outlier | an animated chart | `data-viz` |
| several things at once: steps, what you get, a top three | a checklist or ranked list, revealed one by one | `list` |
| how something works: steps, a pipeline, a before/after | a diagram, drawn on while she explains | `diagram` / `flow` |
| an idea best shown as movement: a scan, a fan-out, a build-up | a motion card in her pack's look | `motion-graphic` |
| the real thing working on her screen | a screen recording | `screen-rec` |
| her real artifact as a still: a post, a report, a DM | a screenshot she moves over (zoom, pan, annotate), never parked | `screenshot` |
| someone else's words as proof: a comment, a DM, a testimonial | a quote card | `quote` / `comment` |
| footage that shows what she's describing while she keeps talking | a b-roll cutaway | `b-roll` |
| a name, a title, a label for that beat | a lower third (never a persistent label unless she asks for one by name) | `lower-third` |
| a pointer at part of another graphic | an arrow, a circle, a highlight | `annotation` |

**Lines that stay on her face:** the ones that connect ("anyway, that's the easy part"), transitions, personal
asides, the emotional delivery and the setup before a point. Her delivery is the whole point of those. Two
graphics on short lines back to back step on each other: fold them into one, or drop one so the other breathes.

**Show it, don't spell it.** Most graphics are motion, not type. When a line could be words or a picture, it
gets the picture, and the kinds that show the thing moving (a recording, her b-roll, a drawn diagram, moving
numbers) come first. Type-led cards are for the hook and punchlines only, and even those animate and carry a
visual element. Never a still wall of type: the captions arrive later and need the room.

### A line that wants b-roll

The cutaway is **her own footage**, never generated and never stock (rule 4; "never invent a moment"). Look in
`projects/<job>/broll/`; long clips get cut into short grabs with `broll-prep` first. The build lays the cutaway
muted, from a good moment inside the clip and never from its first frame (`product/superyap.py`, `add_broll`).
If she has nothing for that line, ask for one clip in one line, or keep the line plain. A `motion-graphic` is
built from type, shapes and her own art in her pack; it is never a generated illustration or a generated clip.

---

## Record her choices (every reel)

Once the plan is approved (or decided, on autopilot), save what this reel uses so autopilot can learn from it:
`python3 product/choices.py record <job> pack=<pack> route=<route> register=<teaching|confessional> format=<format>`.

## Her lookbook first

Before inventing a graphic for a beat, reach for a look she already has: `python3 product/lookbook.py list --pack <pack>`
lists her saved looks first (her own refinements, `_local/lookbooks/<pack>.json`), then the looks every pack has
(hook, eyebrow + headline, headline + subhead, takeover, breakaway card, count-up card, karaoke, single word). When one
fits the beat, name it in the beat's `look` field (its id) and build that beat with
`python3 product/lookbook.py draw <look> <out_dir> --text "<her words>" --dur <seconds> --pack <pack> --job <job>`: the engine's
own builder, in her pack, exactly as the visual editor previews it (list its folder in `hf-graphics/windows.json`). Only when nothing in her lookbook fits does a beat get a bespoke graphic,
and the plan says so in one line ("new: none of your looks does a side-by-side"). The more looks she saves, the more of
every reel is already hers.

## The place and the idea

**`zone`** follows the register: `open` on a teaching reel (whichever open zone this job's `subject-zones.json`
has room in), `top` for the confessional hook card, always inside the safe zone. When the idea needs one
particular side of her, name that zone instead: `above`, `below`, `left` or `right`, as `subject-zones.json`
names them.

**`idea`** is the creative direction, written so the build can make it without guessing: what the frame
shows, which element leads and what the eye reads first, and **the motion**: which parts move, and in which order. A still description
isn't enough for a visual-heavy reel. Any literal on-screen words go in `on_screen`, in her language.

**The motion and the ornament come from her pack.** Before the first idea, read the pack's design brief,
`product/creative-vault/design/<Pack>.design.md` (a pack of hers follows the brief of the shipped pack it
started from). Its Motion section says how a graphic arrives: it animates on, lands just after the line it
answers, takes about 0.3 to 0.5 s and never loops. Its Structural elements section says which ornament the
pack allows: Editorial keeps to thin rules and subtle fills with no hard shadows, Playful takes solid blocks,
ink borders and hard offset shadows, and Butter sits between with blocks and hairlines. One featured element
per frame, one accent, every color from the pack palette (`reel_layout.LayoutContext.palette()`), no gradient
and no blur halo.

**Every graphic takes its fonts by job and its colors from her style pack.** Design each one for its own line
rather than stamping out the same card.

---

## Running it

### What it reads

1. **The finished script:** `projects/<job>/outputs/<job>.transcript.json`, written by the rough cut. If it
   isn't there, the rough cut hasn't run: stop and say so.
2. **The reel's language:** `beat-lines.py` stamps it into the scaffold as a `language` block. **Every
   `on_screen` word is written in her language, not yours** (your default is English); step 4 checks it.
3. **The register**, and through it the `format` (above).

### 1. Break the script into beats

```bash
python3 .claude/skills/graphics-plan/scripts/beat-lines.py <job> --out /tmp/reels-editing-engine/<job>/graphics-plan.scaffold.json
```

The scaffold is the plan file below with every decision left blank: `job`, `duration` and `language` filled in,
`format` empty, and one beat per sentence (`id`, `start`, `end`, `line`) with `element`, `zone`, `idea`,
`on_screen` and `why` empty. It prints the same beats as a sheet to read. A sentence longer than nearly all of
hers (the limits at the top of `beat-lines.py`) arrives already divided at her longest pause inside it. The beats
follow sentences, not ideas: **join two** when one graphic spans them, and **split one** when it needs two
visuals.

### 2. Decide every beat

In the order this page runs: register, her named effects, which lines carry a graphic, then place and idea.

### 3. Write both files and hand it over

Both go in the job folder. They are reviewed work, not scratch:

- **`projects/<job>/graphics-plan.json`**: what the build and the CapCut placement read (fields below).
- **`projects/<job>/graphics-plan.md`**: the same plan for her to read, one table row per beat (#, time, line,
  element, idea), graphic beats marked. The second pass edits against it.

**🔴 The whole plan goes in the chat, inline, every time.** For the creative plan's one approval, show the full
table, every beat including the `face` ones (#, time, line, what goes on screen), as a markdown table in the
turn's FINAL message, after the last tool call (text written before a tool call is folded away in the app).
Graphic beats in bold with their `on_screen` words and how they move; `face` beats read "your face". Above the
table, one line with the totals (beats, how many carry a graphic, the % on short-form); under it, the 2–3
strongest ideas and anything marked `⚠️` for her to call. **Never a link to `graphics-plan.md` in place of the
table**: she reviews the plan where she is reading, never behind a click. The `.md` file is still written, for
the second pass to edit against.

### 4. Check the language

```bash
python3 .claude/skills/graphics-plan/scripts/check-plan-language.py projects/<job>/graphics-plan.json
```

- **Exit `0`:** passes.
- **Exit `1`:** the reel isn't in English and the on-screen copy is. Rewrite the strings it names and run it again.
- **Exit `2`:** it couldn't check, usually because graphics that show words have no `on_screen` recorded, or the
  reel's language was never determined. Fill those in rather than skipping past it.

The builds run the same judgment on their own (`product/plan_language.py`: the beat sheet, the rendered type layer,
the CapCut builders, place-plan, a hook placed in the visual editor). There it is one warning line and the build
goes on as written, so a line saying her copy reads as English means rewrite it now, not after the render.

---

## The plan file

```json
{
  "job": "the-pricing-one", "format": "reel-teaching", "duration": 41.30,
  "language": { "code": "en", "verdict": "english", "source": "transcript" },
  "beats": [
    {
      "id": 1, "start": 0.00, "end": 3.52,
      "line": "you're charging by the hour and it's capping you.",
      "element": "word-card", "zone": "open",
      "idea": "Hook card in her pack's hook font: 'the hourly CEILING' builds a fragment at a time, 'ceiling' lands last in the pack accent and a thin rule drops under it.",
      "on_screen": "the hourly CEILING",
      "why": "the hook; beat 1 always carries the hook card"
    },
    {
      "id": 2, "start": 3.80, "end": 5.10,
      "line": "i did this for two years.",
      "element": "face",
      "why": "told to camera about herself; there is nothing to show but her"
    },
    {
      "id": 3, "start": 5.40, "end": 9.05,
      "line": "forty hours at fifty dollars is two thousand, and that's the most it will ever be.",
      "element": "number-card", "zone": "open",
      "idea": "Count-up: '$2,000' ticks up from $0 as she says it, a bar under it fills to a hard stop, and the card freezes the moment she finishes the line.",
      "on_screen": "$2,000",
      "why": "one number worth seeing"
    }
  ]
}
```

- **Top level:** `job`, `format` (`reel-teaching` / `reel-clean`), `duration`, the `language` block from the
  scaffold, and `beats`.
- **Every beat:** `id`, `start`, `end`, `line` from the scaffold, then `element`: the kind of graphic from the
  table above, or `face` when the line stays on her. A graphic beat adds `zone`, `idea`, `on_screen` when it
  shows words, and `why`. The CapCut placement (`capcut-live.py place-plan <draft> <job>`) lays each rendered
  `assets/<id>.mov` at its beat's `start`.
- **Every beat stays in the file, `face` ones included, each with its `why`.** The ids then match the beat sheet
  one for one, and when she asks for a card on a line that was left plain, the reason it was left plain is
  right there to weigh.
- **`idea` is the direction; `on_screen` is the copy.** `idea` is for a human and may say whatever helps.
  `on_screen` is the literal text rendered into the frame, and it is kept separate because it is the only field
  whose language can be checked: an English sentence *describing* a Spanish card looks exactly like an English
  card. Fill in `on_screen` for every beat whose graphic shows words; leave it out when the graphic has no text.

---

## Where the plan goes next

**The build** makes each beat whose `element` is not `face` from its `start` to its `end`, inside its `zone`,
following its `idea`, in her style pack: the HyperFrames skills (`general-video`/`hyperframes`, `motion-graphics`,
`talking-head-recut`) on the rendered routes, while **on the CapCut route** the `capcut` skill places the same
plan on the timeline as alpha overlays, each on its own track above the footage. Then the **second pass**
adjusts it part by part, and **captions** come last on short-form. Between the build and the render sits the
**beat sheet** (`beat-sheet` skill): every graphic beat here becomes a numbered still she approves before
anything renders.

Deciding is this skill's whole job; the build renders.
