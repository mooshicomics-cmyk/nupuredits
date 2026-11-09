---
name: video-toolkit
description: "The HyperFrames video toolkit underneath the engine's graphics. Use when any engine skill or CLAUDE.md says to use a HyperFrames skill (hyperframes, general-video, motion-graphics, media-use, embedded-captions, hyperframes-audio, hyperframes-registry, and the rest), or when she asks for a catalog effect, transition, caption style or overlay by name, a slideshow, an explainer, a product launch video, a Figma import, a Remotion port, a music video, or a talking-head recut."
---

# Video toolkit

The 20 HyperFrames toolkit skills are stored as reference files, not as auto-loaded skills, so their menus do
not sit in every conversation. Each one lives at `.claude/skills/<name>/TOOLKIT.md` with all its scripts,
references and assets beside it, exactly as upstream ships them.

**To use one: Read `.claude/skills/<name>/TOOLKIT.md` and follow it as that skill.** Relative paths inside it
(`references/...`, `scripts/...`) resolve from its own folder. When a toolkit file tells you to use another
toolkit skill (`/hyperframes-core`, "the media-use skill"), Read that one's `TOOLKIT.md` the same way. There is
no slash command for them; never tell her one is missing.

| Need | Read |
|---|---|
| Entry point, any composition work | `hyperframes` |
| Composition contract, timing, tracks | `hyperframes-core` |
| Motion rules, transitions, runtime adapters | `hyperframes-animation` |
| Punch-ins, Ken Burns, keyframes | `hyperframes-keyframes` |
| Palettes, type, beat planning | `hyperframes-creative` |
| Mixing, fades, ducking, effects on audio | `hyperframes-audio` |
| CLI: lint, check, render, preview | `hyperframes-cli` |
| A named catalog effect / transition / overlay / chart | `hyperframes-registry` |
| Sourcing SFX, music, images, TTS, transcription | `media-use` |
| A named caption style, embedded captions | `embedded-captions` |
| Freeform multi-scene build | `general-video` |
| Kinetic type, stat hits, short motion pieces | `motion-graphics` |
| Scene-per-line explainer | `faceless-explainer` |
| Overlay cards on a talking head | `talking-head-recut` |
| Slideshow or deck | `slideshow` |
| Promo built from a website | `product-launch-video` |
| Video from a GitHub PR | `pr-to-video` |
| Porting a Remotion project | `remotion-to-hyperframes` |
| Importing a Figma design | `figma` |
| Video cut to a music track | `music-to-video` |

Everything else about HyperFrames in this engine still holds: the pin in `skills-lock.json` and `product.json`,
the rendered-routes-only rule for catalog items, and the engine's own looks as the default.
