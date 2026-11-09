# Writing the hook

_On-screen hook copy rules for every reel and every route. Read this before writing a single word of on-screen
copy. (Split out of `workflows/capcut-export/README.md` so a hook read is ~8 KB, not 20.)_

## ✍️ Writing the hook (MEASURED — read before writing a single word of on-screen copy)

These rules come from performance data measured across 44 reels and 18 transcripts on a real account. This is
data, not taste. Re-read this section when in doubt.

### 🚫 The #1 mistake: mirroring the spoken line

**Never write the hook card as a transcription of what she says in the first breath.** If the card
repeats the audio, it buys nothing: the scroller gets the same information twice and no reason to
stay. The card must do a DIFFERENT job than the voice.

### The mechanic that actually won

The best-performing talking head in the reference set did not win on its spoken opener. It won on
**text that named the category on screen early**, while the spoken opener stayed a slow confessional
burn and the name did not arrive in the audio until ~60s.

> **The rule: name the unnamed thing FAST where the scroller can SEE it, and hold it.**
> When the text names it, the spoken opener is free to be a slow burn.

**That job belongs to the hook block, not to a separate bar.** A talking head gets **ONE** text block
at the top of the frame, and it has two lines:
1. **Headline** — names the tension. Opens a loop and refuses to close it.
2. **Subhead** — the quieter line under it. Says WHO it is for, or turns the knife.

**Three shapes are allowed, and nothing else. They are the same mechanic, so this is one decision,
not three:**

| Shape | How | When |
|---|---|---|
| **Hook card** | plain `hook` | one line is enough. Shortest, hardest. |
| **Eyebrow + headline** | `HOOK_SPLIT=1` + `hook_long`, `hook_emphasis: "second"` _(default)_ | small line ABOVE sets the frame, big line below lands it. |
| **Headline + subhead** | `HOOK_SPLIT=1` + `hook_long`, `hook_emphasis: "first"` | big line lands first, quiet line under it turns the knife or names WHO. |

The last two are **one shape with the sizes flipped** — `hook_emphasis` picks which half is big, and
the other half becomes the quiet line. Give `hook_halves` when the break should land on meaning
rather than on length. Both lines come from the pack's own fonts and move as ONE block.

It holds **~8s** by default (`hook_end` — the top of the frame is no longer shared, so the block
gets the room the old bar was taking), and `hook_persist: true` holds it the whole reel.

> 🔴 **NEVER build a separate persistent category chip, bar, or banner** (locked). It is not a second
> text system, it is a duplicate of the job the hook block already does, and with nothing approved to
> put in it the engine invents a line the creator never wrote and runs it for the full runtime. The
> renderer still accepts `persistent_label` for anyone who asks for one BY NAME, and nothing authors
> it otherwise. Two text systems never compete for the top of the frame.

### What a good label does: hand her a word she can repeat

The winners give the viewer **a label for an experience she has lived but never had words for**:

| Views | Line |
|---|---|
| 151,913 | "Why does nobody talk about the **a phrase from your own transcript** that hits in the middle of maternity leave?" |
| 32,305 | "I spent 10 years climbing a ladder. **Maternity leave is when I finally looked up.**" |

"Career crash out" is adoptable. She can say it to a friend. Aim for that.
**Best source for the label is her own transcript** — a phrase she already repeats in the reel.

### ⚠️ The label must name WHO, not just the feeling

A poetic phrase that doesn't say who it's for fails to capture the audience. **Every one of her
biggest reels names the audience in the TEXT:**

| Views | Text |
|---|---|
| 1,458,854 | "**Moms** at 2am: thinking… how do I re-start my career" |
| 642K | "Dear Algorithm, please introduce me to **moms born between 1985-1999**" |
| 463,878 | "**Millennial Mom** Career Crisis" |

**Formula: WHO + the condition.** That one does both in three words, so a scroller self-identifies
instantly. Put it in the hook block — as the headline, or as the quiet line under it. Never in a
separate bar.

**Important distinction:** the "never a category of person" ban applies to **SPOKEN** openers
("For women who would call themselves high-achieving" → 5.5K). In **on-screen text the opposite
holds** — naming the demographic is exactly what drives self-selection. Those spoken flops failed
for being abstract and flattering rather than a lived pain, not for naming a group.

**Don't build the label out of a word the reel argues against.** On `an example reel`, an
"Ambitious Mom…" label would contradict the entire thesis.

### Banned in the hook (each pattern is measured, not a hunch)

| Pattern | Evidence |
|---|---|
| Announcing that value is coming: "I'm about to…", "Let me show you…" | The three worst reels of 18 all do this (6.8K, 4.7K, **2.2K worst of all**) |
| Leading with her own numbers or credentials | 8.5K, 6.6K, 3.6K. Proof belongs in the MIDDLE, never the hook |
| Abstract with no concrete image; a category of person | "For women who would call themselves high-achieving" → 5.5K |
| **Em dashes** | Not in on-screen reel copy (the creator's copy rule). A writing rule only, never a building rule |
| ALL CAPS on a hook in the pack's hook font | Her explicit call, 2026-07-23 |

⚠️ **This contradicts the "Caption Formula" page** ("hook from personal results, authority not pain
point"). That is right for CAPTIONS and backwards for talking heads. Authority works in text, where
the viewer already stopped scrolling. It does not buy the stop.

### Match the hook to the reel's JOB (three-engine model)

| Engine | Format | Hook job |
|---|---|---|
| **REACH** | short text-over-b-roll | identity statement, widest net |
| **GROWTH** | **tension talking head, confessional** | **name the tension, open the loop, NEVER resolve** |
| **FUNNEL** | teaching / solution + comment-CTA | name the problem the lesson solves |

**Growth reels are the follow engine** (12–54% follow-per-like vs ~1% for a viral short). Their
contract: no lesson, no resolution, no pivot to hope. If the urge to add "here's what to do about
it" shows up in the copy, cut it. **Teaching without tension does not grow** — that is precisely
what caused her follower drop.

### Checklist before shipping a hook

1. Does the hook block name **WHO it's for** as well as the condition? (A feeling with no
   audience in it does not capture anyone.) Either line can carry the WHO.
2. Is the hook block saying something DIFFERENT from the first spoken line?
3. Does it open a loop rather than promise to close one?
4. Concrete in the first breath: a picture, a moment, a room. Not a category of person.
5. No "I'm about to" / "Let me show you" / any number about the creator / any em dash / any all-caps.
6. Confessional reel? Then no hopeful pivot anywhere in the on-screen copy either.

### Worked example — `an example reel` (confessional, 2026-07-24)

- ❌ First attempt: `"everyone keeps / calling it ambition"` — a verbatim mirror of her spoken
  opener. Named nothing and added nothing.
- ❌ Second attempt: `"The Quiet Pull"` — her own phrase and adoptable, but it names **no audience**.
  Stripped of context it could be faith, a relationship, an addiction. Poetic, poor targeting.
- ✅ **Eyebrow + headline**, one block (`hook_emphasis: "second"`):
  - eyebrow — **"moms who can't turn it off"** — WHO + the condition, taken from her own line
    ("I cannot shake it… it will not leave me alone"). Repeatable as an identity. Avoids "ambition"
    (the word the reel rejects) and "calling" (would close the loop and read preachy).
  - headline — **"there's a word for this. / ambition isn't it."** — opens the loop the whole reel
    sits inside, without repeating the audio.
  One block, two jobs, one voice. Earlier versions of this spec put the first line in a separate
  bar running the whole reel; that is the thing this page now forbids.
