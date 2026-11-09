# Starter type

A reel takes its type from its style pack, by job. This page records the one font that stands in before any
pack is chosen: the headline font for designed type. Part B of the brand kit writes her own headline font
here, and the updater puts it back after every update by reading the heading and the set line below, so keep
their shape (`product/settings_persist.py`).

## Type: Inter, the starter headline

- **The set:** `assets/fonts/Inter-{Black,Bold,Regular}.otf`, three weights, heaviest first.
- **Headline:** the heaviest weight, case as written, the font's own letter spacing, lines about 1.1 apart.
- **The line beside it** (eyebrow, subhead, kicker): the Bold weight at about half the headline's size, and
  never so small it reads as a footnote.
- **A quiet line** with no pack face to take: the Regular weight.

The size is never typed. It is fitted to the safe width (`product/safe_zones.py`): on the rendered routes by
`fitSize` (`product/reel-graphics-base/fit-size.js`, CLAUDE.md rule 9), and in Clean Captions by its own
measured `fit()`. Once a pack is chosen, the pack's face, tracking and leading replace all of this.
