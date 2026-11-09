# DESIGN.md: bring your own design system, get a style pack and new looks

A creator who already has a design system (a brand guide, a Figma handoff, or a DESIGN.md from another tool)
brings it in once. This format is the native one; a DESIGN.md in the common web shape imports too (see "A DESIGN.md
from another tool" below). The engine turns it into:

1. **A style pack** (required): her fonts by job, her colors by role, her type rules. Every look in the lookbook
   draws in it, the Lookbook shows it as its own tab, and "Use this pack for this reel" switches any reel to it.
2. **New looks** (optional): designs of her own (a card, a hook, a full-screen moment), built as lookbook designs
   that wear the pack, so they work in every reel and survive every update.

This file is the contract: every field below maps to something the engine already does. Anything outside it is
listed under "What a DESIGN.md can't set", with the reason, so nobody writes a field that silently does nothing.

## Where it goes

```
favorites/designs/<pack name>/
  DESIGN.md          this format (or the common web shape)
  fonts/             optional: a font file she wants used that isn't installed on her computer
```

**Fonts go by name.** A font installed on her computer (her own, or a downloaded Google Font) is a font CapCut
has, so the DESIGN.md names it by `family` and nothing else is needed. On Windows, install it **for all users**
(right-click > Install for all users): a per-user install can stay invisible to CapCut.

Then in the chat: **"make a pack from my design"** (the `style-pack` skill runs "How the import runs" below).

## Part 1: the pack (front matter, required)

YAML between `---` lines at the top of the file. Plain words in, engine keys out.

| Field | Required | Allowed | Becomes |
|---|---|---|---|
| `name` | yes | 2 to 30 characters, not a shipped pack's name | the pack's name (tab, picker, `pack.json`) |
| `mood` | yes | 2 or 3 words ("warm playful bold") | card structure: block / editorial / minimal (`pack_recipe.MOOD_STRUCTURE`) |
| `base` | no | `Butter`, `Editorial`, `Playful` (default `Editorial`) | the locked sizes, positions and timings it starts from |
| `fonts.headline` | yes | `{family}`, `file` optional | `fonts.main` + `elements.headline` / `elements.takeover` (`PkHeadline`, `PkTakeover`) |
| `fonts.caption` | yes | `{family}`, `file` optional | `fonts.caption` + `elements.caption`, karaoke font, and labels/kickers (`PkCaption`) |
| `fonts.accent` | yes | `{family}`, `file` optional | `fonts.accent` + `elements.accent_caption`, thought bubbles, subhead (`PkAccent`) |
| `fonts.label` | no | `{family}` | `elements.label`: the eyebrow over a hook, breakaway kickers (`PkLabel`); none = the caption font |
| `fonts.detail` | no | `{family}` | `elements.detail`: the count-up card's number (`PkDetail`); none = as before |
| `colors` | yes | **either** seeds **or** a full palette (below) | `pack_palettes.PALETTE`, `GROUNDS`, `HANDS_OFF_ACCENT`, `CARD_THEME` |
| `type.hook_case` | no | `upper`, `lower`, `title`, `sentence` | the hook's headline: `elements.headline.case` (`--pk-case-headline`) |
| `type.card_case` | no | `upper`, `lower`, `title`, `sentence` | the headline on cards and full-screen moments: `CARD_THEME.headline_case` |
| `type.caption_case` | no | `upper`, `lower`, `title`, `sentence` | `elements.caption.case` |
| `type.hook_tracking` | no | -0.08 to 0.10 (em) | `welldone.headline_tracking` (`--pk-track-headline`) |
| `type.card_tracking` | no | -0.08 to 0.10 (em) | `CARD_THEME.headline_tracking` |
| `type.emphasis` | no | `italic`, `accent` (default `accent`) | the key word: `CARD_THEME.emphasis_italic` or the accent color |
| `type.label_case` | no | `upper`, `lower`, `title`, `sentence` | `elements.label.case` (`--pk-case-label`) |
| `type.label_tracking` | no | 0 to 0.3 (em) | `elements.label.tracking` (`--pk-track-label`); the eyebrow is fitted at its real, spaced-out width |
| `type.emphasis_words`, `type.emphasis_punctuation` | no | `1` to `3` words (`2-3`); `true` / `false` | the pack's `copy` rules, for whoever writes the hook and card copy |
| `hook_color` | no | `white`, `accent`, or a `#hex` | `welldone.hook_color` (`--pk-hook`) |
| `shadow` | no | `soft`, `strong` | `welldone.text_shadow` (never none: text over footage always gets one) |
| `card.ground` | no | `light`, `dark`, `accent`, `pop2` | `CARD_THEME.ground`, full-screen card background |
| `card.ink` | no | `light`, `dark` | `CARD_THEME.ink` |
| `card.rule` | no | `true` / `false` | `CARD_THEME.rule`: a hairline under the headline |
| `colors.extra` | no | at most 3 named `#hex` (`{ brass: "#9C7C4D" }`) | `extra_colors`: `var(--pk-extra-<name>)` in her own looks only, never a default role |
| `colors.apart` | no | two roles (`"accent/muted"`) | `apart`: those two never touch. The import refuses a card that puts them together, the builder swaps an accent word on that ground to the ink (and says so), `check_design` refuses a look that does it |
| `rounded.card` / `.label` / `.frame` | no | 0 to 80 reel px, 999 = a pill | `shape.radius_*`: the count-up card's corners, the label pill (`--pk-radius-card` / `-label` / `-frame`) |
| `spacing.card_pad` | no | 24 to 120 reel px | `shape.pad_card`: inside the count-up card (`--pk-pad-card`); the safe area still wins |
| `elevation.card` | no | `none`, `soft`, `lift` | `shape.shadow_card`: one of three engine-owned shadows, never raw CSS (`--pk-shadow-card`) |
| `elevation.rule` | no | `none`, `hairline` | `shape.rule` (`--pk-rule`, 2px at 1080) |
| `motion.ease` | no | one `cubic-bezier(x1, y1, x2, y2)` | `motion.ease`: every entrance of the count-up card and breakaway lines (`--pk-ease`, `window.pkEase`) |
| `motion.numbers` | no | `count-up`, `still` | `motion.numbers`: the count-up card counts or shows the number still |
| `motion.pace` | no | `unhurried`, `steady`, `quick` | kept on the pack (`motion.pace`) |
| `motion.hook`, `motion.takeover` | no | a text effect's name | her learned `effects.hook` / `effects.takeover`, for this pack only |
| `motion.sfx` | no | `none`, `lighter`, `standard`, `heavy` | her learned `sfx.density` for this pack (none = the lightest) |
| `motion.opener_zoom` | no | `true` / `false` | her learned `motion.opener_zoom` for this pack |
| `description` | no | one sentence | `description` on the pack |

`sentence` case puts a capital on the first word of a hook, card or label and leaves every other letter as written (`title` keeps a word with an apostrophe whole: I'd, Mom's). Captions and takeover words go one word at a time, so on them `sentence` keeps her words exactly as said: her transcript already starts each sentence with a capital.

Every slot from `fonts.label` down is optional and bounded (`product/pack_shape.py` owns the limits). A pack that
sets none of them draws exactly as before: each reader falls back to the value it always used.

Hooks and cards are set separately on purpose: a pack can shout UPPERCASE on its cards while its hooks stay in her
own case. A DESIGN.md that wants both the same sets both.

**Colors, two ways.** Seeds are the quick route; a full palette is for a creator with exact hexes.

```yaml
colors:            # seeds: the engine designs the rest and checks every pairing
  primary: "#E8502E"
  secondary: "#F5C518"
  dark_ground: false
```

```yaml
colors:            # a full palette: these five roles, exactly
  light: "#FFFDD7"   # grounds, cards
  dark: "#317AE1"    # ink, borders
  muted: "#5C91E6"   # quiet text, secondary marks
  accent: "#FDC341"  # the pop: key word, karaoke highlight
  pop2: "#FDC341"    # a second pop, used sparingly
```

### What the import enforces (it refuses, in plain words, rather than ship a broken pack)

- **Legibility floors.** Meaning-bearing text clears 4.5:1 on its ground and graphic text 3:1. With seeds the
  engine adjusts the shade until it passes. With a full palette it refuses and names the failing pair and the
  nearest passing hex.
- **Size floors.** No role is drawn below `safe_zones.MIN_PX` (caption 58, karaoke 58, headline 54, takeover 60,
  label 30, subhead 28). A pack can be bigger, never smaller.
- **Safe zones.** Everything that matters stays inside x 90 to 990 and y 270 to 1620 on a 1080 x 1920 frame.
  Placement around her face comes from her footage, never from the pack.
- **Fonts are real.** Each family is found on her computer (`capcut_userfonts.resolve_font_file`), or in the
  folder's `fonts/` when she put a file there. A font that can't be found is named and the import waits for it;
  it is never swapped for a lookalike. Her fonts stay on her machine and never ship to anyone.
- **Her language's letters.** Each font is checked for the letters her reels use (`product/script_fonts.py`):
  Polish ą ę ł, Spanish ñ, Haitian Creole è ò, accented Latin, Cyrillic, Greek, Korean. A font missing them is named at import, before a reel ever
  mixes two fonts on screen.
- **New name, every time.** A shipped pack is never edited. "Butter but pink" is a new pack started from Butter.

## Part 2: new looks (optional, one section each)

Each look is a `## Look: <name>` section. The engine builds it as a lookbook design (`design.json` +
`index.html`, the same shape as `product/lookbook-designs/starter/`), dressed in the pack from Part 1.

```markdown
## Look: Receipt card
kind: Card                 # Hook, Card, or Full screen
slots: number, label       # text | line1, line2 | number, label
fits: label up to 4 words; number up to 7 characters
layout: a torn-paper receipt, centered; the number big on top, the label small under it in caps
motion: slides up and settles; the number counts up; exits by sliding back down
colors: card in light, number in dark, label in muted
fonts: number in headline, label in caption
```

| Field | Allowed | Becomes |
|---|---|---|
| `kind` | `Hook`, `Card`, `Full screen` | `design.json kind` (where it can go; full screen steps captions aside) |
| `slots` | `text` · `line1, line2` · `number, label` · `emoji` | `design.json slots`; the page fills `__TEXT__`, `__LINE1__`/`__LINE2__`, `__NUMBER__`/`__LABEL__`, `__EMOJI__` (picked from the moment's words, so one emoji-pop look gives each line its own) |
| `fits` | how many words or lines each slot takes | `design.json first_max` and `fit` (box width, max px, max lines); long lines shrink to fit, never below the floors |
| `layout` | plain words | the page Claude draws in the `build-a-look` workshop, on her footage |
| `motion` | plain words: in, during, out | a GSAP timeline; entrances with `fromTo`, every exit ends in a `tl.set` |
| `colors` | the pack's roles only: `light`, `dark`, `muted`, `accent`, `pop2`, `hook` | `var(--pk-<role>)` |
| `fonts` | the pack's roles only: `headline`, `takeover`, `caption`, `accent`, `label`, `detail` | `PkHeadline`, `PkTakeover`, `PkCaption`, `PkAccent`, `PkLabel`, `PkDetail` |
| `shape` | the pack's corners, padding, card shadow, rule, ease, extras | `var(--pk-radius-card)`, `var(--pk-pad-card)`, `var(--pk-shadow-card)`, `var(--pk-rule)`, `var(--pk-ease)` (CSS) or `window.pkEase` (GSAP), `var(--pk-extra-<name>, <fallback>)` |

A look joins the lookbook only when `lookbook.check_design` passes: colors come from the pack (no hexes in the
look), fonts from the pack's roles (no `@font-face`), nothing loads from the web, her words sit in the page (not
in a script), and the look is drawn short and long and passes the render check both ways. Because the look
wears the pack instead of carrying its own colors, it also works in any other pack she switches to.

## What a DESIGN.md can't set, and why

| Not settable | Why |
|---|---|
| Positions and sizes of the shipped looks | measured per reel from her footage (`subject-zones.json`) and the safe zones; a fixed number would sit on her face |
| Gradients, textures, photos or logos inside a pack | a pack is fonts, colors and type rules; images live in her favorites and are placed per reel |
| Per-word colors beyond the one accent | one accent is what keeps a pack coherent; a look can still use `pop2` sparingly |
| Custom caption animations | captions use the builder's named text effects; a new look can have its own motion |
| A shadow of "none" | text over moving footage needs a real shadow to read |
| Editing Butter, Editorial or Playful | every update resets the shipped packs; hers is always a new pack that survives |

## A DESIGN.md from another tool

A design system written for a website (front matter like `name, description, colors, typography, rounded,
spacing, components`) imports through this map. What has no place in a reel is dropped, all of it named in ONE
line, and only what is truly missing is asked.

| Their field | Becomes |
|---|---|
| `name` | `name` (asked only if it is a shipped pack's name) |
| `colors.primary`, `colors.secondary` (or `accent`) | the seed colors |
| `colors.background` / `surface` light or dark | `dark_ground` |
| colors named by what they are (`accent-red`, `sage-forest`, `warm-cream`, `text-ink`) | the five roles by name AND value: `*accent*`/`*brand*`/`*primary*` = accent, the darkest `*ink*`/`*text*` = dark, a tinted `*cream*`/`*canvas*`/`*background*` over pure white = light, `*sage*`/`*secondary*` = muted, `*wheat*`/`*highlight*` = pop2; the rest (up to 3, never pure white or black) = `colors.extra`; an `rgba(...)` is left out; can't decide = ONE question naming her colors |
| a "never touch" rule in the prose ("Red and green never touch") | `colors.apart` |
| `typography.display`, `heading`, `h1`, or the largest of `display-xl` / `display-lg` ... | `fonts.headline` |
| `typography.body` (or `body-*`) `.fontFamily` | `fonts.caption` |
| a script, handwritten or accent family, if any | `fonts.accent`; none = ONE question |
| `typography.eyebrow` / `label` / `kicker` | `fonts.label` (its bold face when the weight is 600+), `letterSpacing` = `type.label_tracking`, caps (or wide spacing) = `type.label_case: upper` |
| `typography.mono` / `numeral` / `detail` | `fonts.detail` (optional: not installed = a note, never a stop) |
| `rounded.card`, `rounded.pill` (px) | `rounded.card` at twice the value, `rounded.label: 999` |
| `components.card.padding` | `spacing.card_pad` at twice the side value |
| a "card lift" in the shadow prose, a 1px hairline, a `cubic-bezier(...)` | `elevation.card: lift`, `elevation.rule: hairline`, `motion.ease` |
| `description`, brand adjectives | `mood` (the look words, never her voice words); none = ONE question |
| other size tiers of a font already used (`display-sm`, `body-sm`) | read, nothing to drop |
| `spacing` (section padding), `components`, dark mode, breakpoints, buttons, inputs, nav | dropped: web layout, no place in a 9:16 reel |

## How the import runs (for Claude)

`python3 product/design_md.py favorites/designs/<name>` is the import: it reads the file (either shape), checks
every rule above and prints the plan; `--write` makes the pack through `pack_write` (recorded, update-safe). The
steps it runs, for reference:

1. Read the front matter. A field from the map above is translated; a web-only field is dropped (named in the one
   summary line); anything else outside this spec is a question for her, never a silent drop.
2. Fonts: resolve each family (`capcut_userfonts.resolve_font_file`); a file she put in `fonts/` is registered with
   `pack_write.py --system-font "Family=/abs/path"`. Not found: name it and wait. Check each against her language
   (`script_fonts.py`).
3. Seeds: `python3 product/pack_recipe.py --name ... --main ... --caption ... --accent ... --primary ...
   --secondary ... --mood ... --base ... [--dark-ground] --write`.
   Full palette: `python3 product/pack_write.py --name ... --from <base> --set palette.light=... (each role)`.
   Then each optional field as one more `--set` (`elements.headline.case=upper`, `card.headline_case=upper`,
   `welldone.hook_color=#...`). Then `python3 product/capcut_font_doctor.py <Pack>` to confirm CapCut sees every font.
4. Show her the pack: the Lookbook's new tab draws every look on her own words.
5. Each `## Look:` goes through the `build-a-look` skill: draft on her footage, her notes, then
   `lookbook.save_design` once `check_design` passes. Nothing joins her lookbook unchecked.
6. Say what's next: "Open the Lookbook and pick the tab, or say 'switch my reel to <name>'."

## Template

```markdown
---
name: My Pack
mood: warm calm clean
base: Butter
fonts:
  headline: { family: My Display }
  caption:  { family: My Text }
  accent:   { family: My Script }
colors:
  primary: "#C2527A"
  secondary: "#F4C2C2"
type:
  hook_case: lower
  card_case: upper
  card_tracking: -0.03
  emphasis: italic
hook_color: white
shadow: soft
card: { ground: dark, ink: light, rule: true }
---

## Look: My card
kind: Card
slots: line1, line2
fits: line1 up to 4 words; line2 up to 3 lines
layout: a small line over big words on a card, centered
motion: rises in, holds, fades out
colors: card in dark, words in light, the key word in accent
fonts: line1 in accent, line2 in headline
```

The `favorites/designs/` folder is made for her the first time she brings a design in.
