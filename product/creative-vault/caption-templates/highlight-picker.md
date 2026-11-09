# Highlight captions — the accent word picker

**She picks the accent words, not you.** Guessing them cost a round of "the words you've chosen are
not good"; the widget settled it in one pass and she asked for it to be the standing method. So when
the style is `highlight` and a section needs accents, BUILD THE PICKER AND SHOW IT before rendering.

## Build it

1. Read the aligned transcript (`projects/<job>/outputs/<job>.transcript.json` → `words`), take the
   span being accented, and group the words into spoken lines (break after `.`/`?`/`!`).
2. Emit one `<button class="w" data-t="<start>" data-w="<word>">` per word, one row per line.
   Mark the current picks with `class="w on"` so she is editing what exists, not starting blank.
3. Render `highlight-picker.template.html` with those rows through `show_widget`.

The template already carries the look (butter chip, serif italic on the picked words — so the chip
previews the actual treatment), the live count, Clear all, and a Send button that posts the picks
back as `<time> <word>` lines. Like the style plan, it saves her picks so a reload never loses them,
shows what it sent in a copy box, and shares the picks with the app: if a send never arrives, call
`read_widget_context` for the show_widget tool before asking her to pick again.

## Apply it

Match each returned time to the caption clip with `abs(start - t) < 0.02` and add `acc` to its class.
Never re-derive the word from the text — two clips can hold the same word, and the TIME is the key.

## What not to do

- Do not silently keep your own picks alongside hers. Clear every `acc` first, then apply her list.
- Do not drop a pick because two of them are adjacent: `real business`, `film strip`, `little nudge`
  and `Hair line` are phrases she picked deliberately.
