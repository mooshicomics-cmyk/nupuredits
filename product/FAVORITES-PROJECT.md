# The Favorites Project — teach the engine your taste by showing it

> _Status: SOUNDS BUILT, plus text animations + sound density from a reel she loves (`favorites.py learn-style`, tests in `product/tests/test_favorites_style.py`).
> Still spec: applying type (fonts/sizes) automatically, and video effects._
>
> _Built decisions: she points at any project by name (open decision 1); re-reading replaces the shelf, so
> it grows and shrinks with the project (2); Windows paths go through `draft_safety` (4). Sounds are copied
> to `_local/sounds/` and recorded in `_local/favorites.json`, NOT `creative-vault/sfx/mine/` + the
> shipped `sfx-index.json` as first written below, because `_local/` is the folder updates are guaranteed
> not to touch. Her "don'ts" are saved with them as rules._
> _The creator's words for it: "a dummy file in CapCut with all of their favorite effects."_

## The problem it solves

A creator told the engine her reel was for corporate executives and needed to be "really high class."
The engine had nowhere to put that. It has exactly two questions it can ask (register and finish route)
and neither carries taste, so the reel came back with bloop sounds and whooshes. She was not prompting
wrong. There was no field for what she knew.

Adjectives do not survive the trip. "High class," "warm," "punchy" mean something to a person and
nothing to a builder. **Examples survive.** A creator who cannot describe her taste can always point at
it.

So: she builds ONE CapCut project full of things she likes, and the engine reads it.

## The creator flow

1. Open CapCut, make a new project, name it **`MY FAVORITES`**.
2. Drop in anything she likes, on any track, in any order. It does not need to look like a reel — it is
   a shelf, not an edit. Sounds she reaches for. Text with the animation she likes on it. A title in her
   font at her size in her colors. A clip with the effect she likes.
3. Say **"learn my favorites."**
4. The engine reads the draft and writes her profile. From then on it builds from her shelf.

Nothing is installed, nothing is uploaded, no file leaves her machine. She is using CapCut, and the
engine is reading choices she already made in it.

## What is actually readable (verified against a real draft)

`draft_info.json` is plaintext. A styled project exposes:

| Bucket | Count in a real draft | What it teaches |
|---|---|---|
| `audios` | 13 | every sound she chose, with its real CapCut name and its cache path |
| `material_animations` | 17 | her in/out animations BY NAME — "Cheeky Bounce", "Chalky Scribble", "Hyper Retreat", "Surprise Jump", "Fade Out" |
| `texts` | 16 | the full type treatment: `font.path`, `size`, `fill.content.solid.color`, `border_color` / `border_width`, `background_*`, `alignment`, `bold_width` |
| `text_templates` | 12 | designed text presets she has applied |
| `effects` | 13 | video effects she reaches for |
| `speeds`, `canvases`, `material_colors` | 15 / 2 / 2 | speed ramps, canvas treatment, colors |

The sound half of this is already proven: the engine imported 53 sounds out of a project named
`APPROVED SFX`, with names and durations intact.

## What it writes

`_local/favorites.json`. Per category: what she picked, how often, and the
raw CapCut identifiers needed to rebuild it.

- **sounds** — copied into `creative-vault/sfx/mine/`, tagged into `sfx-index.json` the same way the
  bundled library is, and marked `source: "mine"`. **Hers always outrank the bundled set**, exactly as
  the vault already outranks the fallback.
- **text animations** — the CapCut animation names, which the engine already builds with. This is the
  one that most directly fixes an "it animates nothing like me" complaint.
- **type** — font file, size, fill, stroke, background. Feeds the pack's `hook` / `caption` / `subhead`
  roles rather than overriding the pack wholesale.
- **effects / speeds** — recorded, applied only when asked. Lower confidence than the other three.

## How the engine uses it

Read at the same moment as Part C of the brand kit: **before planning or building any reel.**

Precedence, lowest to highest: **bundled default → style pack → her favorites → what she says in this
reel.** Her favorites narrow the choices. They never override a direct instruction, and they never
override the mood rules — a somber reel still gets no sound even if her shelf is full of them.

## What it does NOT do

- It does not read her other projects. Only the one she named. Her work stays her work.
- It does not copy anything to another machine or to us. Sounds are copied inside her own install.
- It does not replace the style pack. A pack sets structure; favorites set taste within it.
- It does not make the engine stop asking. Register and finish route are still asked.

## Open decisions

1. **Naming.** Fixed project name `MY FAVORITES`, or does she point at any project by name? Fixed is
   less to explain; pointing is less to get wrong.
2. **Re-reading.** Once, at onboarding? Or every time she says the phrase, so the shelf can grow? Growing
   is better and costs nothing, since the read is fast and idempotent.
3. **Confidence.** One instance of a thing on the shelf is a preference. Is three instances a stronger
   one? Counting is cheap and would let the engine rank rather than treat every pick as equal.
4. **Windows.** The draft path and font paths differ. `draft_safety.py` already handles the draft folder;
   the font-path side needs the same treatment.
5. **The empty case.** A creator who never builds one must lose nothing. The bundled library and pack stay
   the default, and the engine should mention the shelf once, warmly, not nag.
