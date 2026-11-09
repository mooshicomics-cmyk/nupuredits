---
name: epidemic-sound-design
description: "Sound-designs a CapCut reel with Epidemic Sound: reads the reel's beats, pulls VARIED sounds (never the same one twice), sets a warm music bed, and lays matched SFX on their own track — additively, never touching existing edits. Triggers: sound design, add sound effects, epidemic sound, sfx pass, add sfx, score this reel, add a music bed, make the sound dynamic."
---

# Epidemic Sound Design — varied, dynamic, additive

Turns a cut reel into a full soundscape using the creator's **Epidemic Sound** connector: a warm music
bed underneath, an opener that pulls you in, and spot SFX matched to every beat. Built on the reusable
engine pieces (`product/capcut_sfx.py`, `product/audio_levels.py`, `product/capcut_media.py`).

## 🚦 THE #0 GATE: the REGISTER decides IF sound happens at all (locked).

Before any of the rules below, check the reel's **register** (the same teaching-vs-confessional call the
graphics step makes). It gates the ENTIRE sound pass:

- **Confessional → near-silent.** This is the highest-reach register and it is deliberately bare. Place a
  sound ONLY on a genuine emphasis **landing** you can point to: a thought-bubble/graphic HITTING the
  screen, a spoken money or number beat ("$2,000"), the hook reveal, the emotional close. If a beat has no
  real landing, place **nothing**. A typical confessional reel gets **0–2** sounds total, often zero.
- **Teaching → the full soundscape below** (varied bed + spot SFX on every real beat).

**🔴 NEVER put a sound on a bare cut, and NEVER on the engine's default jump-cut punches.** `capcut_motion.py`
adds a gentle scale bump AT most cuts automatically — that is ambient camera motion, **not** an emphasis
moment, and it must stay silent. A sound belongs on a deliberate LANDING (something arrives on screen, a
number lands, a thought bubble pops), never on "there was a cut here" or "the footage nudged in." Cutting
from a silence is not a beat. This is the exact failure to avoid: soft "matched" whooshes appearing at every
cut point on a confessional reel. (When the matching table below says "punch-in zoom → whoosh," it means a
DELIBERATE emphasis zoom you placed, not the automatic ambient punches.)

If you are unsure of the register, ask one line — "teaching or confessional?" — before placing a single
sound. Never default to teaching.

## 🔴 THE #1 RULE: VARIED + DYNAMIC. Never repeat a sound (locked).

Repetition is what makes sound design feel cheap. **Every hit gets a DISTINCT sound.** The ONLY time the
same file repeats is for the **same on-screen action** (e.g. keyboard clatter on two different typing
shots). Otherwise: pull a fresh whoosh for each transition, a different pop for each text reveal, a
distinct sound for each cutaway. When you need N of a kind, search Epidemic for N variations
(`SearchSoundEffects` returns many) and assign one per beat — do not grab one and reuse it.

Keep a running set of sound-ids already placed; before assigning a sound to a new beat, if it's in the
set and the action isn't identical, pick another. Build the reel's SFX so a viewer never hears the same
effect twice in a row.

## The connector

Sound + music come from the **Epidemic Sound** MCP connector (the creator's licensed library). Its tools:
`SearchSoundEffects`, `SearchRecordings` (music), `DownloadSoundEffect`, `DownloadRecording`,
`SearchSimilarToSoundEffect`. If the tools aren't loaded, the connector was added mid-session — it only
registers at session start, so **restart** (`claude --continue`) to load them. To set it up the first
time: add the Epidemic Sound connector in Claude's connector settings and authorize it (free trial link
in the course bonus), then restart.

Download URLs are signed — use them **verbatim** (editing the filename breaks the signature → 401).

## Fallback — no Epidemic connector (ships clean, never errors)

If the Epidemic tools are not available (the creator never connected it), do **not** skip the sound pass
and do **not** error. Fall back automatically to the **bundled SFX set** that ships with the engine.

🔴 **ASK THE ENGINE what sounds exist. NEVER glob for them.** One command, from any directory:

```bash
python3 product/capcut_sfx.py --list          # every cue name (add --paths for the files, --json for a script)
```

`palette()` resolves both bundled libraries from the engine's own location, so this answers correctly no
matter where the working directory has drifted to. A relative glob does not: on one real build a long run
of directory changes had left the shell three folders inside a job, `product/creative-vault/sfx/` matched
nothing, and a finished reel was handed over SILENT with "no sound effects available" while 239 files sat
exactly where they belong. **A zero from a glob means you asked from the wrong folder. A zero from
`--list` is a real fault and it says so on stderr.** If you ever see an empty library, run the command
above before telling the creator anything is missing.

**HER FAVORITES COME FIRST.** Run `python3 product/favorites.py show` before placing anything. If she has
read a favorites project, those sounds are her taste: reach for them before the bundled set or an
Epidemic pull, and obey every rule listed under them. The mood gate above still outranks her shelf.

**THE INDEX IS THE SOURCE OF TRUTH: `product/creative-vault/sfx/sfx-index.json`.** Read it before
placing a single cue. Every one of the 77 bundled sounds is tagged on three axes, plus a `description`
carrying the sound's real name ("Camera shutter sound", "Sound of tearing paper", "Hammer Strike"), so
you pick on MEANING and never on a guessed alias.

| Axis | Answers | Values |
|---|---|---|
| `mood` | what is this REEL like? | `somber` · `tender` · `tense` · `triumphant` · `playful` · `neutral` |
| `tactile` | is the sound DIEGETIC? | flag. true = only use it when the object is actually on screen |
| `job` | what happens on the TIMELINE? | `transition` `reveal` `emphasis` `money` `typing` `click` `notify` `error` `build` |
| `material` | what is literally ON SCREEN? | `camera` `paper` `pen` `keyboard` `coin` `bell` `glitter` `air` `impact` `glitch` |

🔴 **SKIP ANY CUE WITH `enabled: false`.** The creator switched it off by ear. Never place it, never offer it, never use it as a rotation alternate. It is still on disk only so it can be
switched back on.

**The lookup, in order:**
1. **Something real on screen? MATERIAL WINS and tone is ignored.** A keyboard on screen takes a
   keyboard sound on a somber reel and on a playful one. This is the creator's locked "sound mimics
   movement" rule. It is also why most empty tone-x-job cells do not matter.
2. **Otherwise filter by `job`, then by the reel's `mood`.**
3. Never the same file twice in a row (the #1 rule above still governs). 🔴 **Two cue names can be the SAME FILE** — the index marks those with `same_as`. Treat a `same_as` pair as ONE sound: `fuwa_swipe` after `fuwa-short-wind-noise-swipe-etc` is a REPEAT, not variety. Prefer the canonical name.

🔴 **`density` IS A CEILING, NOT A TARGET — and on `somber` it is ZERO (locked, creator).**
The index carries the budget per tone; obey it over any urge to fill beats:

| mood | budget for the WHOLE reel | |
|---|---|---|
| **somber** | **ZERO — opt-in only** | 🔴 LOCKED. Grief, loss, a death, a diagnosis, a hard truth: place NOTHING. Not one cue, not a soft one, not on the hook. Sound on grief reads as production value applied to someone's pain. The only exception is the creator asking BY NAME — and do not offer it either. Silence is the finished treatment, not a gap. |
| **tender** | 0-3 | Warm and low-energy. Soft, single, never stacked. |
| **tense** | 1-2 | Alarm, failure, a hard turn. One hit IS the effect; a second cancels the first. |
| **triumphant** | 2-4 | A win, a number, a reveal. A win announced four times stops being a win. |
| **playful** | the full soundscape | Spot SFX on every real beat. |

**Register gates this further and always wins when stricter:** a confessional reel stays near-silent
whatever its mood (the #0 gate above). `confessional` + `somber` means ZERO, full stop.

**INFER the mood from the SCRIPT first — do not ask by default (creator's call).** The transcript
almost always says plainly which it is: a death, a diagnosis or a loss is `somber`; a number she hit
or a win is `triumphant`; a deadline or a near-miss is `tense`. Read the rough-cut transcript and
decide. Only when the script genuinely will not resolve it, ask ONE line alongside the register
question: *"is this one somber, tender, tense, triumphant, or playful?"* Never assume playful. Guessing playful on a somber reel is the exact
failure this index exists to prevent. A single "serious" used to mean both a big win and a death, which is why
mood is now valence x energy and those two sit in opposite corners.

- Music bed falls back to the engine's bundled warm bed; the warm master is applied the same way.

Same skill, same output shape (a matched `sfx` track added additively) — only the source library changes.
Detect once at the start: Epidemic tools present → licensed library; absent → bundled set, no prompt.

## The flow

1. **Read the beats.** From the cut transcript + the draft, map every moment worth a sound: the hook /
   opener, each text/graphic reveal, punch-in zooms, spoken money moments, typing/laptop shots, b-roll
   cutaway INs, the emotional close. Time each to the exact word (use `words.json` mapped through the cut
   list, not eyeballing).
2. **Pick VARIED sounds** (see the matching table). Search Epidemic, audition by title, assign one
   distinct sound per beat. Money → `cash register / cha-ching`. Typing → `keyboard`. Text/thought pops →
   a *different* `cartoon pop / bubble pop` each time. Transitions/cutaways → a *different*
   `whoosh / swoosh / swish` each time. UI / logo reveal → `bloop / notification / bright chord`. Send →
   `whoosh`. Emotional / "just a mom" section → **warm** (`bright chord warm`, `soft swell`, soft
   whooshes), never dry FX. Opener → something that **pulls you in** (a rising/mids whoosh), NEVER a
   dark/creepy bass riser.
3. **Music bed.** `SearchRecordings` with `vocals:false`, mood matched to the register (warm/hopeful for
   this creator — not epic/cinematic). Trim to the reel length, bake a fade in/out, lay it under
   EVERYTHING at a low bed level.
4. **Levels.** Normalize every SFX file to an even peak (≈ −6 dBFS) so the library's loudness spread
   doesn't make some inaudible, then place with **role-based volumes** (music bed ≈ 0.13; cutaway whooshes
   soft ≈ 0.5; punches ≈ 0.85; the money hit ≈ 1.0). `product/audio_levels.py` has the helpers.
5. **Lock it on-beat + non-repeating, then place.** Run the placements through
   `capcut_sfx.plan_sfx(placements, onsets=<word-onset times, timeline seconds>, alternates=<same-role
   map>)` FIRST — this is a required step, not optional. It snaps every cue to the nearest emphasis onset
   (so nothing lands "just dropped in" between words), drops cues that stack too close, and rotates any
   file that would repeat back-to-back to a same-role alternate. Pass `onsets` = the kept words' start
   times (words.json mapped through the cut list, the same list from step 1) and `alternates` = a small map
   of interchangeable sounds you actually pulled (e.g. `{"woosh": ["pop_whoosh", "fuwa_swipe"]}`) so a
   repeat has somewhere to rotate to. Print its notes line. THEN place the cleaned list, and ONLY this way
   when the draft already exists (a finished build, or one she has worked on). All the cleaned cues go on
   ONE new audio track together; nothing already in the draft moves or goes:
   ```python
   import json, sys; sys.path.insert(0, "product")
   import capcut_media, capcut_sfx, draft_safety
   from capcut_ripple import enforce_maintrack_ripple
   draft_safety.require_capcut_quit("add sound effects to this draft")  # written under an open CapCut, they vanish
   ready = []
   for path in draft_safety.draft_json_copies(draft_dir):               # the draft file AND every Timelines copy
       d = json.load(open(path, encoding="utf-8"))
       capcut_sfx.add_sfx(d, draft_dir, cleaned, keep_existing=True)     # additive: her sounds stay
       problems = capcut_media.ensure_shippable(d, draft_dir)            # every sound links in the media panel
       if problems:
           sys.exit("these sounds would not link, nothing was written:\n" + "\n".join(problems))
       enforce_maintrack_ripple(d)                                       # the magnet, as every build sets it
       ready.append((path, d))
   for path, d in ready:                                                 # written only once every copy is ready
       json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
   ```
   Never rebuild or reorder the creator's existing audio. If she said a prior sound was bad, remove just
   that segment and replace it; keep everything else. (`keep_existing=True` is what makes this additive:
   without it, add_sfx replaces every `sfx_` sound an earlier pass placed, which is right inside a builder's
   own one-pass build and wrong on a draft she already has.)
6. **Guardrail.** The block above runs `capcut_media.ensure_shippable` on every copy, so every sound file is
   project-local + registered (links in the media panel), and it refuses before writing if anything won't
   link. Keep that line whenever you adapt the block.

## Sound → beat matching (defaults; always vary within a kind)

| beat | pick | note |
|------|------|------|
| opener / hook reveal | rising "mids" whoosh (+ optional light riser) | pull-you-in, never a dark bass riser |
| text / thought-bubble reveal | cartoon/bubble pop — a **different one each time** | |
| punch-in zoom | whoosh / swoosh — **varied** | ONLY a deliberate emphasis zoom, NEVER the engine's ambient default jump-cut punches (see the #0 gate) |
| spoken money ("$2,000") | cash register / cha-ching | the loudest hit |
| typing / laptop shot | keyboard clatter | reuse OK across typing shots (same action) |
| b-roll cutaway IN | whoosh / swish — **a different one per cut** | soft under warm b-roll |
| UI / app / logo reveal | bloop / notification / bright warm chord | |
| emotional close | warm chord + soft swell | warm, not dry FX |

## Rules
- **Register gate first (rule #0, see top).** Confessional = near-silent, sound only on a real landing;
  never on a bare cut or the engine's ambient jump-cut punches. Teaching = the full soundscape.
- **Additive only.** New track for the SFX; never touch the creator's cuts, text, kept sounds, or music.
- **Vary relentlessly** (rule #1). Reuse a file only for the identical action.
- **Brand-neutral.** Match the sound to the register of the reel, not to any one creator's taste. State the
  Epidemic run intent before firing (downloads are quick/free on the connector, but be deliberate).
