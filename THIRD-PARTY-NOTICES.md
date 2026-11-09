# Third-Party Notices

The Reels Editing Engine is built and sold by Homewell LLC. It bundles or builds upon the open-source
components listed below, each used under its own license and credited here as those licenses require.
Nothing in this file limits your rights under those upstream licenses. Components that install on your
own machine at runtime (and are therefore not redistributed inside this package) are listed at the end
for completeness.

---

## Bundled components

### HyperFrames
- Source: https://github.com/heygen-com/hyperframes
- Copyright 2026 HeyGen, Inc.
- License: Apache License 2.0 (HyperFrames' own copy is included at `.claude/skills/hyperframes/LICENSE`,
  and the full text is available at https://www.apache.org/licenses/LICENSE-2.0).
- The Effects Library (`product/effects-library.html`) lists the HyperFrames 0.9.6 catalog (names, titles and
  descriptions) and plays its demos through the HyperFrames player (`@hyperframes/player`, Apache License 2.0),
  loaded from a public CDN, with the previews HyperFrames publishes. `product/library-stills/` holds one frame
  captured from each of HyperFrames' own catalog demos that publishes no still; only demos with no outside images
  (photos, artwork, footage) are captured.
- The engine runs version 0.9.6 of the HyperFrames tool. The seven skills HyperFrames still publishes
  (`hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use`, `figma`, `slideshow`,
  `remotion-to-hyperframes`) carry every skill file of theirs that changed or was added through its 0.9.6 release,
  including `hyperframes`' new references/ (captions, film, format, look, motion, overlays, review, runtimes, sound,
  spec, story, storyboard, types/), scripts/bake-basemap.mjs, scripts/locate.mjs and assets/frame-presets/, and
  `media-use`'s new references/local.md, references/mixing.md and audio/scripts/ (carve.mjs, extract-audio-data.py);
  files HyperFrames removed from them stay, because the skills below still use them. HyperFrames retired its workflow
  skills in 0.8.185; this engine keeps them (`hyperframes-core`, `hyperframes-animation`, `hyperframes-keyframes`,
  `hyperframes-creative`, `hyperframes-audio`, `embedded-captions`, `general-video`, `motion-graphics`,
  `faceless-explainer`, `talking-head-recut`, `product-launch-video`, `pr-to-video`, `music-to-video`) as they were in
  its 0.8.181 release. Those copies, and the files of the seven above that did not change after 0.8.181, come from
  its 0.8.158 release, with the skill files that changed through 0.8.181 brought up to that release
  (`hyperframes-cli`: TOOLKIT.md, references/beats.md, references/cloud.md, references/lint-validate-inspect.md and
  references/upgrade-info-misc.md; `hyperframes-animation`: TOOLKIT.md, blueprints-index.md, rules-index.md and the
  files under adapters/, blueprints/ (kinetic-type-beats.md, logo-assemble-lockup.md), references/motion-blur.md,
  rules/ and transitions/TRANSITION-REGISTRY.md; `hyperframes-core`: TOOLKIT.md; `hyperframes`: TOOLKIT.md and
  references/skill-lifecycle.md; `motion-graphics`: TOOLKIT.md; `media-use`: TOOLKIT.md, references/audio.md,
  references/operations.md, references/resolve.md, references/setup-providers.md, scripts/lib/manifest.mjs, scripts/lib/recipe-store.mjs and, under audio/, references/requirements.md,
  references/sfx.md, scripts/audio.mjs, scripts/lib/media-record.mjs, scripts/lib/sfx.mjs, scripts/lib/openverse.mjs
  and their tests; `faceless-explainer`, `pr-to-video` and `product-launch-video`: TOOLKIT.md and scripts/audio.mjs;
  `slideshow`: references/standalone-harness.md; `embedded-captions`: scripts/hf-cli.cjs, scripts/hf-cli.test.mjs,
  scripts/check-overflow.cjs, scripts/check-rail-climax.cjs, scripts/measure-layout.cjs and scripts/preview-frames.cjs). Twenty-eight files are modified, and each carries a notice at its top saying what changed:
  - `.claude/skills/media-use/TOOLKIT.md`, `audio/references/sfx.md` and `audio/scripts/lib/sfx.mjs` keep sound
    effects on the bundled library and search Openverse only when asked (`HYPERFRAMES_SFX_OPENVERSE=1`), because a
    CC BY sound must be credited wherever a reel is posted.
  - `.claude/skills/hyperframes-cli/TOOLKIT.md` adds the rule that this engine never sends HyperFrames feedback
    reports, never runs `hyperframes usage` (it reads the Claude sign-in saved on the computer) and never hands a
    project to the HyperFrames desktop app; `references/preview-render.md`, `references/feedback.md` and
    `references/upgrade-info-misc.md` beside it carry the same rules.
  - `.claude/skills/hyperframes-cli/references/cloud.md` and `references/preview-render.md` keep renders on her
    computer instead of making the cloud the final render on a paid plan; `.claude/skills/media-use/TOOLKIT.md` and
    `references/setup-providers.md` never run `media-use generate` or `transcribe --engine heygen`, never bring sign-in
    up on their own and say what a paid call costs first. HyperFrames' `reverse-any-video` skill and media-use's
    `references/heygen.md` are not included.
  - `.claude/skills/hyperframes/TOOLKIT.md` never runs `hyperframes usage`, never presents the HyperFrames desktop
    app (the `hyperframes-studio` skill is not included), and names where the retired workflow skills live here;
    `references/skill-lifecycle.md` beside it never moves the HyperFrames pin inside a job.
  - `.claude/skills/general-video/TOOLKIT.md` never runs `hyperframes usage`.
  - `.claude/skills/hyperframes-registry/TOOLKIT.md` and `references/search.md`,
    `.claude/skills/motion-graphics/catalog-map.md` and
    `.claude/skills/motion-graphics/agents/builder.md` never send a catalog search-miss report.
  - In `.claude/skills/embedded-captions/`: `scripts/hf-cli.cjs` hands out the engine's pinned HyperFrames;
    `scripts/render-and-composite.sh` runs the engine's check before each pass and renders the passes one after
    the other; `scripts/prepare.sh` installs the caption helpers when missing and says ready only once
    safe-zones.json exists; `scripts/make-theme.cjs`, `scripts/make-cinematic.cjs`, `modes/cinematic/engine.html`
    and `modes/cinematic/cinematic-cream/template.html` give the footage a start time, size a project from its
    video and keep a portrait reel's top and bottom bands clear; `TOOLKIT.md` says `init` leaves the computer's
    global skills alone here. `scripts/source-size.cjs` is the engine's own addition, not a HyperFrames file.
  - `.claude/skills/hyperframes/references/intent-interview.md`,
    `.claude/skills/hyperframes-core/references/tracks-and-clips.md`,
    `.claude/skills/embedded-captions/references/aesthetic-principles.md` and
    `.claude/skills/embedded-captions/references/rail.md` state in place what their pointers to the
    `hyperframes-studio` skill said.
- Added beside the copies, not modified from them: `.claude/skills/hyperframes/LICENSE` (HyperFrames' own license)
  and the font license texts listed under "Fonts inside the HyperFrames skills" below.
- Used by the HyperFrames-family skills under `.claude/skills/` (hyperframes, hyperframes-core,
  hyperframes-animation, hyperframes-cli, hyperframes-creative, hyperframes-keyframes,
  hyperframes-registry, hyperframes-audio, media-use, faceless-explainer, general-video,
  product-launch-video, motion-graphics, slideshow, and related video-authoring skills).

### VectCutAPI and pyJianYingDraft
- Sources: VectCutAPI, https://github.com/sun-guannan/VectCutAPI (copyright its contributors), which
  includes pyJianYingDraft, https://github.com/GuanYixuan/pyJianYingDraft (copyright its contributors).
- Bundled at `product/engine/VectCutAPI/` (its own `LICENSE` file is retained there).
- License: Apache License 2.0.
- Modified by Homewell LLC. Each changed file carries a notice at the top saying so; files added by
  Homewell LLC (the setup and launcher scripts) are not part of the original.
- The bundled copy is modified: the original's unused cloud upload/download code was removed (`oss.py`
  and its Aliyun OSS `oss2` dependency, the remote draft-download path, and the default remote draft host,
  which now points at this computer), and a loopback-only request guard was added to the local server.
  A save that could not copy a clip into the draft now reports failure with the reason (the original logged it
  and reported success), and on Windows the server runs the engine's Microsoft Store app check when it starts.
- Used as the CapCut / JianYing draft-building engine. This package is not affiliated with or endorsed
  by the VectCutAPI or pyJianYingDraft authors, or by CapCut.

### talking-head-recut (adapted from vtake-skills)
- Source: https://github.com/notedit/vtake-skills
- Copyright (c) 2026 leeoxiang.
- License: MIT (full text below; the original notice is retained at
  `.claude/skills/talking-head-recut/NOTICE.md`).

### GSAP, the GreenSock Animation Platform (v3.15.0)
- Source: https://gsap.com
- Copyright (c) GreenSock, Inc.
- License: GreenSock standard "no charge" license (https://gsap.com/standard-license), free for use in
  commercial products. The license header is retained inside the bundled `gsap.min.js`.

### Bundled sound effects (fallback set, in `.claude/skills/media-use/audio/assets/sfx/`)
- Source: Pixabay (https://pixabay.com). Each file is credited in that folder's `CREDITS.md`.
- License: Pixabay Content License (https://pixabay.com/service/license-summary/), free for commercial
  use with no attribution required. Provided only as a fallback; you may replace them with your own.

### Bundled public-domain sound effects (`product/creative-vault/sfx/cc0/`)
- Sources: uisfx (https://uisfx.com), synthesized by its author; and "100 CC0 SFX #2" by rubberduck
  (https://opengameart.org/content/100-cc0-sfx-2).
- License: Creative Commons CC0 1.0 Universal (public domain), free for any use including commercial,
  with no attribution required. Each file's origin is listed in `product/creative-vault/sfx/cc0/SOURCES.md`.

### Bundled fonts (open-license, in `assets/fonts/`)
- **SIL Open Font License 1.1** (full text in `assets/fonts/OFL.txt`, plus `OFL-Inter.txt`,
  `OFL-SpaceGrotesk.txt`, `OFL-Caveat.txt`, `OFL-Mynerve.txt`, `OFL-NotoSerifDisplay.txt`, `OFL-NotoSansKR.txt`,
  `OFL-NanumMyeongjo.txt` and `OFL-Gaegu.txt`): Inter, Space Grotesk, Caveat, Mynerve, Noto Serif Display,
  Noto Sans KR, Nanum Myeongjo, Gaegu, DM Sans, Instrument Serif, Julius Sans One,
  Noto Sans Adlam, Pinyon Script, Playfair Display, Poppins, Shrikhand. Each font keeps its own
  copyright notice inside the font file. Copies of Inter, Playfair Display, Poppins and Noto Sans Adlam
  also sit under short file names in `product/creative-vault/hands-off/<pack>/`, under the same license.
- The style packs' display faces (Prosecco, Soup Du Jour, Ugly Dave, Bloop) are NOT bundled and never
  redistributed by this package; CapCut resolves them by name from its own font library on your machine.

### Fonts inside the HyperFrames skills
These web fonts come with the HyperFrames skills that use them. Each one keeps its copyright notice inside
the font file, and its license text sits in the same folder as the font.
- `.claude/skills/embedded-captions/modes/standard/fonts/files/` (the same faces are also inlined in that
  folder's `fonts.css`):
  - **SIL Open Font License 1.1** (`OFL-<family>.txt`): Anton, Audiowide, Baloo 2, Bangers, Bodoni Moda,
    Caveat, Chakra Petch, Cinzel, Cormorant Garamond, Creepster, Fredoka, Inter, Monoton, Orbitron,
    Press Start 2P, Rajdhani, Saira Stencil One, Shippori Mincho, Sora, Space Grotesk, Teko, VT323.
  - **Apache License 2.0** (`LICENSE-<family>.txt`): Permanent Marker, Special Elite.
- `.claude/skills/talking-head-recut/assets/fonts/`, **SIL Open Font License 1.1**: Caveat, Inter,
  LXGW WenKai TC, and Virgil (copyright Ellinor Rapp, from https://github.com/excalidraw/virgil; its license
  is `OFL-virgil.md`).
- `.claude/skills/music-to-video/references/templates/logo-split-lockup-pulse/assets/`, **SIL Open Font
  License 1.1**: Fredoka.
- `.claude/skills/hyperframes-creative/frame-presets/code-editorial/fonts/` and
  `.claude/skills/hyperframes/assets/frame-presets/code-editorial/fonts/` (the same files), **SIL Open Font License
  1.1**: EB Garamond, Inter, JetBrains Mono (license texts already in each folder).

### Face detection model (`assets/models/face_detection_yunet_2023mar.onnx`)
- **YuNet**, from the OpenCV Model Zoo (https://github.com/opencv/opencv_zoo). Copyright (c) 2020 Shiqi Yu.
  MIT License; the full text ships beside the model, at `assets/models/YUNET-LICENSE.txt`.

---

## Installed at runtime on your own machine (NOT redistributed in this package)

These tools are downloaded and installed onto your own computer the first time you run the engine. They
are not included in this package and remain under their own licenses:

- HyperFrames CLI (`npx hyperframes`) — Apache-2.0
- WhisperX and its models (faster-whisper, wav2vec2) — BSD / MIT
- Word aligners for languages WhisperX has none for, downloaded only the first time a reel in that language is
  cut: Bulgarian (`infinitejoy/wav2vec2-large-xls-r-300m-bulgarian`) — Apache-2.0; Icelandic
  (`language-and-voice-lab/wav2vec2-large-xlsr-53-icelandic-ep30-967h`, Language and Voice Lab, Reykjavik
  University) — CC BY 4.0
- FFmpeg — LGPL / GPL, as installed on your machine: through Homebrew on a Mac, through winget on Windows, and
  as the static evermeet.cx build on an Intel Mac
- MusicGen (`facebook/musicgen-small`), downloaded only if you use generated background music: the model is
  licensed **CC BY-NC 4.0, non-commercial**. Tracks it makes are for trying a vibe; for anything you post or
  sell, use music you have the rights to.
- Python packages installed during setup ("set me up"; `check-setup.sh` only reports what is missing), for
  example Pillow — their own licenses

---

## MIT License (for talking-head-recut / vtake-skills)

```
MIT License

Copyright (c) 2026 leeoxiang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The Apache License 2.0 is included in full in this package for HyperFrames at
`.claude/skills/hyperframes/LICENSE` and for VectCutAPI at `product/engine/VectCutAPI/LICENSE`.
