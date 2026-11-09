---
name: learn
description: Teach the editor something so it carries into the NEXT reel — a size, a spacing, how heavy the sound design gets, which open zone text prefers, or a text animation she names herself. Use when the creator says "learn my pattern for the next reel", "remember that", "always do it like that", "I like my captions a little higher", "keep the sound effects lighter", "call that one <name>", "learn this style, start incorporating it", "learn the style of my CapCut project <name>", "make this my default", "from now on", "/learn", "/learn list", "/learn forget", "teach my style from this reel", "turn my notes into rules", "what did you learn from this one", or has just finished nudging a draft in CapCut and wants the changes kept. Also runs at the END OF EVERY REEL (CapCut handoff or final), where her notes from the reel come back as a pick-many checklist of rules for the next reel (product/teach_style.py). Writes BOTH halves, the plain bullet in brand-kit.md Part C and the record the builders actually apply.
user-invocable: true
argument-hint: "[what she changed · list · forget <n> · effect <name>]"
---

# Learn: make a preference stick

The creator's draft comes back fully populated and she nudges it to taste. This is how a nudge she liked
stops being something she has to redo every reel.

**The promise in `brand-kit.md` Part C is that what she teaches is read before the next reel is built.**
That promise is only kept if BOTH halves get written:

| half | where | who reads it |
|---|---|---|
| the plain bullet, in her words | `brand-kit.md` Part C → Learned preferences | her, and you |
| the record | `_local/learned.json` (via `product/learned.py`) | **the builders**, every build |

Writing only the bullet is the old failure: a markdown file a future session might not open. Writing only
the record leaves her nothing to read. Write both, every time.

## Invoking

- **"learn my pattern for the next reel"** / **"remember that"** / **"always do that"** → save what changed.
- **`/learn list`** → show what she has taught.
- **`/learn forget <n>`** → drop one.
- **`/learn effect <name>`** → name a text animation (see below).
- **"learn this style, start incorporating it"** (about a CapCut project she made and loves) → see
  "Learning a whole reel's style" below. Ask for the project's exact CapCut name if she did not give it.

## Teach my style from this reel (the end of every reel)

The notes she gave on a reel fixed THAT reel. Whether they should be how every reel comes out is hers to
decide, so at the end of every workflow (the CapCut handoff or the final, right before the hashtag line) she
gets them back as a checklist. Also runs any time she says **"teach my style from this reel"**,
**"what did you learn from this one"** or **"turn my notes into rules"** (then `collect`, which ignores
whether the reel was already asked).

1. `python3 product/teach_style.py offer <job>`. **Exit 1 prints nothing**: no notes, already asked on this
   reel, or she switched it off. Say nothing about it and carry on. Exit 0 prints her notes from this reel:
   editor notes, looks she asked for, looks she switched off, a music level she set by hand, and chat notes
   skills logged with `teach_style.py note`. Add any change she asked for in this conversation.
2. **Turn them into rules, in her words** (up to 4 per checkbox set, more than one set when there are more), the ones that would hold on her NEXT reel. Leave one-offs
   out: "move this line 40 px lower", "this card is wrong", a named moment. Several notes saying the same thing
   ("captions higher" three times) are ONE rule, and the strongest. Skip a rule that is already in
   `python3 product/learned.py list` or Part C. No rule survives → `done <job>` and say nothing.
3. **For each rule, know where it would be kept**, and say it on its checklist line:
   - a learnable value (`python3 product/learned.py fields`) → "the engine applies it" (`--field/--value`);
   - a sound rule ("never a whoosh") → `favorites.py rule "..."`, its real owner;
   - anything else creative ("comment collages sit behind my head") → "I'll read it before planning".
   Scope it to this reel's register or format unless it is clearly global (see "Scope it, or it leaks").
   Never a placement number, hook copy, register or route (see "What deliberately cannot").
4. **ONE question box, up to 4 checkbox sets she cycles through, each `multiSelect: true`** (you: "let us cycle
   through a couple of checkboxes"; never cap her at four things):
   - **Her rules**: "Want me to keep any of these for your next reels?", one option per rule (label = the rule,
     short; description = where it is kept and the note it came from). More than 4 rules → a second rules set.
   - **Her looks from this reel**: `python3 product/lookbook.py one-offs --pack <pack> --job <job>` lists the looks
     she kept for this reel only (Sandbox and new looks). When there are any: "Keep any of these looks in your
     lookbook for every reel?", one option per look (label = its name, description = its one-line about).
   - When the hashtag's first-time pick-one is due, it takes one of the four sets.
   Nothing is pre-ticked, nothing is kept unless she ticks it, and "Other" lets her reword one.
5. Each ticked rule: `python3 product/teach_style.py keep <job> "<rule>" [--field F --value V] [--scope register=confessional]`
   (it writes BOTH halves for a field, the Part C bullet for the rest, and prints the line to say). A sound rule
   goes through `favorites.py rule` instead. Each ticked look: `python3 product/lookbook.py keep-everywhere <look-id> --pack <pack>`.
   Then ALWAYS `python3 product/teach_style.py done <job> --kept <n>`,
   ticked or not, so this reel is never asked again.
6. Say what was kept in ONE line ("Kept 2: captions sit a bit higher, fewer sound effects on confessional
   reels."), or nothing if she ticked none. Then the hashtag line, last.

"Stop offering that" → `teach_style.py --off` (and `--on` brings it back). A skill that takes a note in the
chat (the beat sheet's notes by beat number, a CapCut fix) logs it with
`python3 product/teach_style.py note <job> "<her words>" --from "beat sheet"`, so the checklist sees it.

## Learning a whole reel's style (a CapCut project she loves)

`python3 product/favorites.py learn-style "<project name>"`. Read-only on CapCut, so it can stay open. It:

- folds her TEXT ANIMATIONS in: the ones on her hook and on her other text become the default in/out on
  hooks and other text in CapCut builds (`cleanyap` / `superyap` `add_text`), whenever the reel's own plan
  names none. Newer CapCut animations the editor engine has no name for are placed as a stand-in and
  swapped for hers at finalize, from CapCut's own files on this computer. Takeover words never get one.
- sets `sfx.density` from how busy that reel's sound was (it writes the `learned.py` record; add the Part C
  bullet in her words as usual).
- REPORTS her fonts and colors with the offer "save this as my pack". It does not swap her look by itself:
  a pack is its own decision (`style-pack` / `/studio recipe`).
- never touches her sounds shelf (`favorites.py learn`) and never reads any project but the one she named.

Say plainly what it folded in (the tool prints it), and name anything it left out. It is the CapCut routes
(raw / medium) that take her animations; the rendered well-done type uses the engine's named effects, so for
those offer `/learn effect` with the closest catalog effect instead. `favorites.py forget-style` stops it.

## Saving a preference

1. **Know the concrete change.** If she just edited a draft, read what actually differs rather than
   guessing — `draft_safety.edited_in_capcut` tells you a draft was touched, and the draft's text layers
   carry the real sizes and spacing. If you cannot tell, **ask one crisp question**. Never save a guess:
   a wrong preference applies itself to every future reel.
2. **Save the record**, which validates and clamps:
   ```bash
   python3 product/learned.py add thought.size 13 "15 read oversized"
   ```
   In a session with Python already open, `learned.add(field, value, note=..., scope=..., from_job=...)`.
3. **Append the bullet** to `brand-kit.md` Part C, in plain language, dated and naming the reel it came
   from. Append only — never delete an earlier one; refine it by teaching the field again.
4. **Say it back in one line**: what was saved, and that it applies from the next reel.

### Scope it, or it leaks
`scope={"register": "confessional"}` / `{"format": "yap"}` / `{"pack": "Butter"}`. A preference learned on a
confessional reel is usually not wanted on a teaching reel — **a lean sound design is the confessional
register doing its job, not a global taste.** When in doubt, scope it narrow: widening later costs one
sentence, and a preference that silently spread costs a reel.

### What can be learned
**Which sounds she likes is not a learned.py field.** "These are my go-to sounds" or "use the sounds in my
CapCut project" goes to `python3 product/favorites.py learn "<project>"` (with `--rule` for each don't), or
`python3 product/favorites.py rule "..."` for a rule on its own. How MANY sounds (`sfx.density`) stays here.

`python3 product/learned.py fields` prints the live list. Sizes, spacing, caption scale, SFX density, the
opener push-in, which measured open zone text prefers, and a text animation per role. "Never hide/remove my
captions" is `caption.never_hide` (true): her captions then stay on under every card, label or hook that shows
the same words, on every reel; only a caption style she picks for a line still replaces them there.

**"Always use <pack>" is not one of them, and that is deliberate** — her chosen pack already lives in
`creative-vault/user-style.json`. Route it to its real owner instead, so there is one answer to the
question: `cleanyap.set_default_pack("Butter")` (or `/studio` / "make Butter my default"). Two places that
both claim to hold her pack is how one of them goes stale.

### What deliberately cannot, and what to say instead
- **Register and finish route** — asked fresh every reel, because they are decisions about THIS video.
- **Hook copy** — measured, and never a mirror of the spoken line. A remembered hook is a wrong hook.
- **A placement number** — where she is in frame is MEASURED per reel (`workflows/subject-zones.py` →
  `subject_place`). A number that was right on one reel lands on her forehead in the next. If she says
  "captions a bit higher", save **`caption.zone`** (`above` / `below` / `left` / `right`) — the preference
  is which measured open zone to prefer, and the number still comes from THIS footage. Tell her that
  plainly; it is the engine protecting her, not refusing her.

If she asks for something outside the list, say what you CAN save that gets closest, and save that.

## `/learn list` and `/learn forget`

```bash
python3 product/learned.py list
python3 product/learned.py forget 3
```

Offer `forget` whenever a reel needed a correction that undoes something taught — a stale preference is
worse than none, because she cannot see it working. Every record carries the reel and date it came from,
so a regression is traceable to what taught it.

If `list` or `forget` says the saved file is **damaged**, say so plainly: nothing in it was changed or lost,
builds use the shipped defaults meanwhile, and the next thing she teaches moves the damaged file aside (kept
as it is, `_local/learned.json.damaged-<time>`) and starts a fresh one. Her Part C bullets still say what she
had taught. A damaged `creative-vault/user-effects.json` works the same way: announced when the engine
loads, and moved to `_local/` by the next `/learn effect`.

## `/learn effect <name>` — naming an animation

She points at a look the engine can already produce and names it:

```python
import text_effects
text_effects.teach("the snap", base="spring-scale-in", dur=0.28, gran="word", stagger=0.06)
```

It is **derived from a shipped effect**, then overridden — `base` plus any of `dur`, `gran`
(element/char/word), `stagger`, `ease`, `frm`, `to`, `mask`. It saves to
`creative-vault/user-effects.json` (protected; an update never touches it) and from then on it works
anywhere a shipped effect works, including the library wall and `/learn effects.hook <name>`.

**Be honest about the ceiling.** This names and reuses looks the engine can already produce. It does not
invent new motion from a reel she liked. If she shows you a reel and wants its animation, use
`/studio inspo <link>` to read what it is doing, build the closest thing from the catalog, then name THAT.

## Two rules that outrank being helpful here

- **Never say something was learned when only the bullet was written.** That exact sentence was said to a
  tester once and it was not true of a single build afterwards.
- **Never apply a preference silently.** Every build prints what it took from her saved preferences
  (`learned.report()`), so she can always see why a reel looks the way it does.
