# /studio recipe — build your own style pack (design it visually, then I build it)

The `style-pack` skill ("build my own style pack") is the quick version: name 3 fonts + an accent color and
it swaps them into a pack. **`/studio recipe` is the pro version**, and there are two doors into it:

**Door 1 — DESIGN IT VISUALLY FIRST (the default, recommend this).** The creator designs their look on
**https://www.hyperframes.dev/design**, downloads the frame pack, and hands the zip over. You read its
`FRAME.md` and build the pack from its real colors and fonts with `product/frame_to_pack.py`.

**Door 2 — DESCRIBE IT.** No site, no zip. They give 2 colors + mood words and `product/pack_recipe.py`
derives a palette. Use this when they already know their colors, or the site is not an option.

Either way the result is a COMPLETE pack: a contrast-checked palette AND a designed card theme, so it works
everywhere the 3 launch packs do (raw, medium, well-done, Hands-Off, Animation), not just as fonts.

Invoke: `/studio recipe`, or the creator says "build my own pack", "make my own look (the good version)",
"design me a style pack", or hands over a frame pack zip.

## Voice
Big sister across the table. Warm, plain, ONE question at a time, lead with hope. This should
feel like picking paint colors with a friend, never like filling a form.

---

## DOOR 1 — the frame-pack flow (proven; this is how the 3 launch packs were made)

### Step 1 — get the name FIRST
Ask this before anything else, so you can call it by name for the rest of the build and they hear their own
pack referred to as a real thing from the start.
> Let's build you a look that is unmistakably yours. First, what do you want to call it?
>
> Whatever you name it is what you say from now on. "Make this one in Broadside." Every reel will wear it.

Hold the name. Use it in every line that follows ("let's get Broadside's fonts in", "Broadside is built").

### Step 2 — send them to the site
> Perfect. Now let's design what <Name> actually looks like.
>
> The fastest way in is to design it visually first. Go to **https://www.hyperframes.dev/design**
>
> Pick a template that feels close to you. There are twelve. Then hit Fine-tune and make it yours: swap the
> colors, swap the fonts, watch it update live. When you like what you see, click **Download frame pack**.
>
> Then come back and drop that zip right here in the chat. I will take it from there.

### Step 3 — read their pack, tell them what is in it
A downloaded frame pack is three files. **`FRAME.md` is the only one that matters** (the showcase html is
preview-only). Unzip anywhere and point the tool at the `FRAME.md`.

```
python3 product/frame_to_pack.py --frame <path/to/FRAME.md> --name "<PackName>"
```

Read the result back in plain language — colors first, fonts second, then the `case:` line. The case comes
from the frame itself (caps when its headlines are set in caps, otherwise the way she types them), never from
the base layout. If she wants the other one, re-run with `--case upper` or `--case as-written`.
> Got it. Here is what your pack is made of:
>
> Ground is a warm cream, `#F0ECE5`. Ink is near black. Your accent is that fire orange, `#E85D26`.
> Fonts are Barlow for the loud stuff and IBM Plex Mono for the small labels. Headlines are set the way
> you type them.
>
> Two quick things and then I will build it.

### Step 4 — fonts (the one real gate)
The tool prints `✓ every font resolved to a real file`, or names exactly what is missing. **Never fake a
font.** Fonts resolve only from what CAPCUT can see, on purpose: if the engine could render a font CapCut
cannot, the rendered output and the CapCut timeline would diverge.

Frame fonts are Google Fonts, so they are free. Install them yourself, do not hand over a chore:

```
brew install --cask font-barlow font-ibm-plex-mono      # cask name = lowercased, hyphenated family
```

Then the one-time CapCut add, which the Mac install does NOT replace. It happens HERE, before the build
writes anything, never mid-job: CapCut must be closed for every write, so if a build is still running or has
writes left, finish it and hand it over first, then ask for the font.
> Barlow and IBM Plex Mono are not on your Mac yet. Both are free. I will install them for you now, one
> second.
>
> Done. Now one last step, and it is the same one you did with Bloop in setup. CapCut needs to see a font
> before I can build with it. Open CapCut, new project, Text, drag Default text onto the timeline, then
> search **Barlow** in the font box and click it. Do the same for **IBM Plex Mono**. Then quit CapCut fully
> (Cmd+Q), because I can only build while it is closed.
>
> Tell me to go when CapCut is closed.

**If they want their own font, say yes warmly.** It is usually the better look.
> Want to use a font you already love instead? Totally fine, and honestly it is the better move if you have
> one.
>
> Any font works. One you bought, one off DaFont, one that came with something else. Install it on your Mac
> first, then add it in CapCut that same one time. Then just tell me its name and I will use it. If I cannot
> find it I will say so and wait. I will never quietly swap in something else.

**What CapCut has may not match what the frame names** (a frame says "Barlow"; CapCut has "Barlow
Condensed"). CapCut wins. Override it:

```
--main-font "Barlow Condensed" --caption-font "Barlow Condensed" --accent-font "IBM Plex Sans"
```

**A frame often names only two fonts** (display + mono) while a pack has three roles. Say so, and offer a
third rather than letting one font do double duty silently.

### Step 5 — write it in
**Use `--write`. Do not paste by hand.**

```bash
python3 product/pack_recipe.py  ... --write        # or frame_to_pack.py --write
```

It writes both files in one step: the pack block into `product/creative-vault/style-packs.json` with
`"in_launch_kit": false`, and all **six** one-line entries into `product/pack_palettes.py` (`GROUNDS`,
`HANDS_OFF_ACCENT`, `PALETTE`, `TREATMENTS`, `PACK_ELEMENTS`, `CARD_THEME`).

Why it stopped being a paste step: that is six entries across two files, and missing one does not error.
The pack silently falls back to **another pack's** values in the designed lanes, which reads as a broken
new pack rather than a missing line, and you go looking in the wrong place. `pack_write.py` refuses to
touch a launch pack, needs `--force` to replace an existing name, keeps a `.bak` of each file, and
re-reads both afterwards to confirm every other pack survived byte-identical. Both files are written or
neither.

### Step 6 — preview, adjust, THEN lock
Render ONE beat so they SEE it before it is locked. Do not promise one-shot: every launch pack took a few
rounds, so treat adjust-and-show-again as the normal path, not a failure.
> Broadside is built and it is yours.
>
> Your layout does not move, that is the part that keeps reels clean. Your colors, your fonts, your accent,
> those are yours to change any time.
>
> Let me put it on one caption so you can actually see it before you commit. If anything feels off, say it
> plain. Bigger hook. Warmer orange. Swap the caption font. I will adjust and show you again.

### Step 7 — the CapCut fine-tune fallback
When they want to tune the raw CapCut route by hand:
> Want to tune it by hand in CapCut? Go for it. Get it looking how you want, then screenshot the text panel
> on the right and send me the screenshot. I can read your exact settings off it, the size, the spacing, the
> stroke, the shadow, and bake them into your pack so you never set them again.

---

## DOOR 2 — the describe-it flow (no site)

Gather, one question at a time, **the name first** · **three fonts** (main loud / caption quiet / accent
personality — read them `product/creative-vault/font-picking-guardrails.md` in your own words first) ·
**two colors** (primary pop + secondary) · **two or three mood words** · **case**, one pick-one: headlines and
takeovers in ALL CAPS, or the way she types them. Then:

```
python3 product/pack_recipe.py --name "Sunrise" \
  --main "<main>" --caption "<caption>" --accent "<accent>" \
  --primary "#RRGGBB" --secondary "#RRGGBB" --mood "warm playful bold" \
  --case as-written [--base Playful] [--dark-ground]
```

`--base` is the pack whose LOCKED sizes/positions get cloned (Playful for bold, Editorial for refined,
Butter for clean). `--case` is hers (`upper` = ALL CAPS, `as-written` = the way she types it, the default;
`sentence` = a capital on the first word of a hook or card, when she asks for sentence case);
the base pack's case never comes along, so a pack cloned from Butter does not come out in caps she never chose. It prints the same two paste-ready blocks + a contrast report. Then Steps 5-7 above. Ask the NAME first there too.

---

## Rules (hold these)
- **The LAYOUT never changes.** Only fonts, colors, case, and treatment are theirs. Sizes and positions are
  the locked pattern that keeps reels clean. A frame supplies colors and type, never reel craft; landing it
  inside the locked layout is what makes it come out a reel instead of a poster.
- **Legibility is a gate, not a preference.** The tools enforce it: body ink clears 7:1 on the ground,
  the accent clears 3:1 (it only ever sets kickers and emphasis words at display size). Do not override a
  floor to get a prettier-but-unreadable pairing.
- **One font is loud.** Enforce the guardrails kindly.
- **A custom pack gets its face MEASURED; a launch pack does not.** The three launch packs were hand-tuned
  against their own faces over many real reels, so their numbers are deliberate and their output must not
  move (`in_launch_kit: true` means trust the tuning). A pack built here clones a base pack's numbers onto
  a face those numbers never saw, so the font-metric floors apply to it instead. Do not "fix" a launch
  pack by measuring it.
- **Line-height comes from the face, never a constant.** Stacked display type needs a line box at least as
  tall as that font's own `(ascent + descent) / size`, or adjacent word boxes overlap and the gate fails
  with `content_overlap`. The ratio is a property of the FONT: Soup Du Jour 1.00, Inter 1.22, Playfair
  1.34, Anton 1.51. A floor that looks fine on one face collides silently under a taller one.
  `stylepack.font_box_ratio()` measures it, so never hardcode one. The same mismatch produced FOUR
  separate visible defects, and the floors land in all four: the takeover word-stack line-height (was a
  flat 1.06), the count-up card's label gap (was a flat 14px, now 14px plus the face's real box
  overflow), the breakaway block rows (was 0.72) and the headline block line-height (was 0.92). The last
  two floor at INK height, `stylepack.font_ink_ratio()`, not box height.
- **Check the treatment string against the pack's real hexes.** `frame_to_pack` wrote the treatment prose
  from its own COMPUTED ground/ink instead of the frame's actual ones, so `TREATMENTS` advertised a ground
  nothing else rendered. That string feeds the Hands-Off design brief, which is the one lane with nobody
  looking at it, so a wrong hex there goes unnoticed for a long time.
- **Believe the font doctor only after this fix.** It used to report a pack font as "bundled (ships)"
  whenever the element carried an absolute path, which every pack built here does. It now confirms the
  file really sits inside the bundled font dir. If it says machine-local, it means it: that font will not
  reach a creator, and the pack needs a bundled face or an explicit add.
- **The preview has to tell the truth.** `build-pack-showcase` applies the same in-feed size floors the
  real builder applies. If a preview ever shows a caption smaller than the finished reel, that is a bug in
  the preview, not a smaller pack.
- **Never fake a font.** Resolve every one to a real file or help them add it. Saying "I cannot find it
  yet" is always better than a silent substitution.
- **Refine through impeccable.** The helpers give a SAFE, legible starting point; the impeccable design
  system makes it beautiful. Nudge a hue or a role if it says so, then keep the floors intact.
- **Maintenance:** a new pack is a real, permanent addition. After building, run `/studio document` so
  `STUDIO-SYSTEM.md` re-syncs. `/studio reset` keeps custom packs (it only reverts the built-in ones).

## Then hand off to glow
End every recipe by running `glow` (the ship pass) on the preview so the very first render of their new
pack is already clean.
